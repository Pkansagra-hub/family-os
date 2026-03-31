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

Production Reference: k1/orchestrator/types.py CircuitBreakerState
(full CB implementation with CLOSED/OPEN/HALF_OPEN state machine).
POC uses a simplified CB that tracks open/closed state only.
"""

from __future__ import annotations

import logging
from typing import Optional

from k1.concierge.orchestrator.routing import DispatchRecord, EmitFn, route_task
from k1.concierge.orchestrator.types import CannedResponse
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch

log = logging.getLogger(__name__)


# =========================================================================
# Simplified Circuit Breaker (POC)
# =========================================================================


class CircuitBreaker:
    """Simplified circuit breaker for POC tier degradation.

    Production reference: k1/orchestrator/types.py CircuitBreakerState
    (CLOSED/OPEN/HALF_OPEN with failure counting, recovery timeout,
    half-open probes).

    POC version: tracks open/closed state only. Sufficient to demonstrate
    degradation cascade.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._open = False

    def is_open(self) -> bool:
        """Check if the circuit breaker is open (tripped)."""
        return self._open

    def force_open(self) -> None:
        """Force the circuit breaker open (for testing)."""
        self._open = True

    def force_closed(self) -> None:
        """Force the circuit breaker closed (reset)."""
        self._open = False

    def reset(self) -> None:
        """Alias for force_closed."""
        self._open = False


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
