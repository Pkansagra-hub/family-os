"""
k1.orchestrator.degradation -- Tier-level circuit breakers for the orchestrator.

Provides the per-tier ``CircuitBreaker`` (3-state CLOSED/OPEN/HALF_OPEN
state machine) used by orchestrator adapters (planner, fabric gateway,
admin) for degradation-aware dispatch.

State machine:
    CLOSED    -- Normal operation; requests pass through.
    OPEN      -- Failing; reject ALL requests immediately.
    HALF_OPEN -- Trying ONE request to test recovery.

Reuses the ``CircuitBreakerState`` enum from ``k1.fabric.circuit_breaker``
to keep the state vocabulary consistent across the system.

Module-level singletons (``cb_planner``, ``cb_orchestrator``, ``cb_fabric``)
are provided for the canonical tier breakers per V2 Design Section 11.6.

Relocated from the deleted ``k1.concierge.orchestrator.degradation`` (and
the brief intermediate location ``k1.concierge.degradation``) as part of
P4B.4 (concierge orchestrator extraction).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import List

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


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerState",
    "cb_planner",
    "cb_orchestrator",
    "cb_fabric",
]
