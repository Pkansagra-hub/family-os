"""
k1.concierge.orchestrator.degradation -- Tier degradation cascade.

V2 Design Ref: Section 11.6 (degradation cascade: HIGH->MEDIUM->LOW->canned)

When circuit breakers trip, the system degrades gracefully through tiers:

    HIGH  (CB_PLANNER open)       -> degrade to MEDIUM
    MEDIUM (CB_ORCHESTRATOR open) -> degrade to LOW
    LOW   (CB_FABRIC open)        -> canned response

The cascade is TRANSPARENT to the user. The FSM receives the same result
events regardless of which tier executed. Degradation affects execution
quality (fewer optimization steps), not the system's ability to respond.

Uses Fabric's 3-state circuit breaker pattern:
    CLOSED    -- Normal operation; requests pass through.
    OPEN      -- Failing; reject ALL requests immediately.
    HALF_OPEN -- Trying ONE request to test recovery.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional

from k1.concierge.orchestrator.routing import DispatchRecord, EmitFn, route_task
from k1.concierge.orchestrator.types import CannedResponse
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.fabric.circuit_breaker import CircuitBreakerState

log = logging.getLogger(__name__)


# =========================================================================
# 3-state Circuit Breaker (production-grade, per Fabric pattern)
# =========================================================================


class CircuitBreaker:
    """Per-tier circuit breaker with CLOSED/OPEN/HALF_OPEN state machine.

    Follows the Fabric ``k1.fabric.circuit_breaker.breaker.CircuitBreaker``
    pattern (3.4.1) adapted for tier degradation:

      - Sliding-window failure counting: failures within ``failure_window_ms``
        are tracked. When count reaches ``failure_threshold`` the breaker opens.
      - After ``half_open_after_ms`` the breaker transitions to HALF_OPEN and
        allows a single probe request.
      - A successful probe resets to CLOSED; a failed probe re-opens.

    Thread-safe: all mutable state protected by ``threading.Lock``.
    """

    __slots__ = (
        "name",
        "_lock",
        "_state",
        "_failures",
        "_opened_at_ms",
        "_failure_threshold",
        "_failure_window_ms",
        "_half_open_after_ms",
    )

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        failure_window_ms: int = 60_000,
        half_open_after_ms: int = 30_000,
    ) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._state = CircuitBreakerState.CLOSED
        self._failures: List[float] = []  # monotonic timestamps (ms)
        self._opened_at_ms: float = 0.0
        self._failure_threshold = failure_threshold
        self._failure_window_ms = failure_window_ms
        self._half_open_after_ms = half_open_after_ms

    # -----------------------------------------------------------------
    # State queries
    # -----------------------------------------------------------------

    @property
    def state(self) -> CircuitBreakerState:
        """Current state, auto-transitioning OPEN → HALF_OPEN on timeout."""
        with self._lock:
            self._maybe_half_open()
            return self._state

    def is_open(self) -> bool:
        """True when the breaker is OPEN (requests should be rejected).

        HALF_OPEN is NOT considered open — it allows a single probe.
        """
        return self.state == CircuitBreakerState.OPEN

    def is_half_open(self) -> bool:
        """True when the breaker is in HALF_OPEN (probe) state."""
        return self.state == CircuitBreakerState.HALF_OPEN

    def is_closed(self) -> bool:
        """True when the breaker is CLOSED (normal operation)."""
        return self.state == CircuitBreakerState.CLOSED

    @property
    def failure_count(self) -> int:
        """Number of failures in the current sliding window."""
        with self._lock:
            self._prune_failures()
            return len(self._failures)

    # -----------------------------------------------------------------
    # State mutations
    # -----------------------------------------------------------------

    def record_failure(self) -> None:
        """Record a failure. Opens the breaker if threshold reached."""
        with self._lock:
            now = self._now_ms()
            self._failures.append(now)
            self._prune_failures()
            if self._state == CircuitBreakerState.HALF_OPEN:
                # Probe failed → re-open
                self._state = CircuitBreakerState.OPEN
                self._opened_at_ms = now
                log.warning("CB[%s] probe failed, re-opening", self.name)
            elif (
                self._state == CircuitBreakerState.CLOSED
                and len(self._failures) >= self._failure_threshold
            ):
                self._state = CircuitBreakerState.OPEN
                self._opened_at_ms = now
                log.warning(
                    "CB[%s] failure threshold reached (%d), opening",
                    self.name,
                    len(self._failures),
                )

    def record_success(self) -> None:
        """Record a success. Resets to CLOSED if in HALF_OPEN."""
        with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.CLOSED
                self._failures.clear()
                self._opened_at_ms = 0.0
                log.info("CB[%s] probe succeeded, closing", self.name)

    def trip(self) -> None:
        """Force-open the breaker (e.g., from health checker)."""
        with self._lock:
            self._state = CircuitBreakerState.OPEN
            self._opened_at_ms = self._now_ms()

    def reset(self) -> None:
        """Force-reset the breaker to CLOSED."""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._failures.clear()
            self._opened_at_ms = 0.0

    # Backward-compat aliases used by tests
    force_open = trip
    force_closed = reset

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    def _prune_failures(self) -> None:
        """Remove failures outside the sliding window (caller holds lock)."""
        cutoff = self._now_ms() - self._failure_window_ms
        self._failures = [t for t in self._failures if t > cutoff]

    def _maybe_half_open(self) -> None:
        """Transition OPEN → HALF_OPEN if recovery timeout elapsed (caller holds lock)."""
        if self._state == CircuitBreakerState.OPEN and self._opened_at_ms > 0:
            elapsed = self._now_ms() - self._opened_at_ms
            if elapsed >= self._half_open_after_ms:
                self._state = CircuitBreakerState.HALF_OPEN
                log.info("CB[%s] recovery timeout elapsed, entering HALF_OPEN", self.name)

    @staticmethod
    def _now_ms() -> float:
        return time.monotonic() * 1000


# =========================================================================
# Named circuit breakers (per design doc Section 11.6)
# =========================================================================

cb_planner = CircuitBreaker("CB_PLANNER")
cb_orchestrator = CircuitBreaker("CB_ORCHESTRATOR")
cb_fabric = CircuitBreaker("CB_FABRIC")


# =========================================================================
# Degradation-aware routing
# =========================================================================


async def route_task_with_degradation(
    task: TaskDispatch,
    tier: ComplexityTier,
    *,
    emit_fn: Optional[EmitFn] = None,
    dispatch_fn=None,
) -> DispatchRecord | CannedResponse:
    """Route a task with automatic tier degradation on circuit breaker trip.

    V2 Design Ref: Section 11.6

    Degradation cascade:
      HIGH  (CB_PLANNER open)       -> MEDIUM
      MEDIUM (CB_ORCHESTRATOR open) -> LOW
      LOW   (CB_FABRIC open)        -> CannedResponse

    Args:
        task: The TaskDispatch payload.
        tier: Original complexity tier before degradation.
        emit_fn: Bus emit function for LOW tier.
        dispatch_fn: Dispatch function for MEDIUM/HIGH tier.

    Returns:
        DispatchRecord if task was routed, CannedResponse if all tiers failed.
    """
    effective_tier = tier

    # HIGH -> MEDIUM degradation
    if effective_tier == ComplexityTier.HIGH and cb_planner.is_open():
        log.warning(
            "CB_PLANNER open, degrading HIGH -> MEDIUM (task_id=%s)",
            task.task_id,
        )
        effective_tier = ComplexityTier.MEDIUM

    # MEDIUM -> LOW degradation
    if effective_tier == ComplexityTier.MEDIUM and cb_orchestrator.is_open():
        log.warning(
            "CB_ORCHESTRATOR open, degrading MEDIUM -> LOW (task_id=%s)",
            task.task_id,
        )
        effective_tier = ComplexityTier.LOW

    # LOW -> canned response
    if effective_tier == ComplexityTier.LOW and cb_fabric.is_open():
        from k1.concierge.config import get_config

        log.warning(
            "CB_FABRIC open, returning canned response (task_id=%s)",
            task.task_id,
        )
        return CannedResponse(
            text=get_config().orchestrator.canned_response_text,
            reason="CB_FABRIC_OPEN",
        )

    return await route_task(
        task,
        effective_tier,
        emit_fn=emit_fn,
        dispatch_fn=dispatch_fn,
    )


def get_effective_tier(tier: ComplexityTier) -> ComplexityTier | None:
    """Determine the effective tier after degradation checks.

    Returns None if all tiers are exhausted (canned response needed).

    V2 Design Ref: Section 11.6
    """
    effective = tier

    if effective == ComplexityTier.HIGH and cb_planner.is_open():
        effective = ComplexityTier.MEDIUM

    if effective == ComplexityTier.MEDIUM and cb_orchestrator.is_open():
        effective = ComplexityTier.LOW

    if effective == ComplexityTier.LOW and cb_fabric.is_open():
        return None  # All tiers exhausted

    return effective
