"""
poc.k1_poc.orchestrator.routing -- Dispatch routing for tier-based task execution.

V2 Design Ref: Section 11.2 (route_task: single dispatch point)
V2 Design Ref: Section 11.7 (invariant 8: single dispatch point)

route_task() is the SINGLE dispatch point for all task routing. The complexity
tier (determined by Front's cognitive analysis) controls which path the task
takes:

    LOW:    Emit Envelope to k1.orchestration.task.dispatch.v1 (Back handles)
    MEDIUM: Create TaskEnvelope -> dispatch to OrchestratorStub
    HIGH:   Create TaskEnvelope -> dispatch to Orchestrator (future)

All tiers ultimately produce results that arrive via
k1.orchestration.dag.completed and transition the FSM to
COMPANIONING -> DELIVERING.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from poc.k1_poc.orchestrator.types import Budget, TaskEnvelope
from poc.k1_poc.task.complexity import ComplexityTier
from poc.k1_poc.task.dispatch import TaskDispatch

log = logging.getLogger(__name__)


# =========================================================================
# Dispatch record -- tracks what was dispatched (for testing/observability)
# =========================================================================


@dataclass
class DispatchRecord:
    """Record of a dispatch action for observability.

    Captures what was dispatched and where, enabling tests to verify
    correct routing without coupling to the bus implementation.
    """

    tier: ComplexityTier
    topic: str = ""
    envelope: Optional[TaskEnvelope] = None
    payload: Any = None
    priority: str = "INTERACTIVE"


# =========================================================================
# Emitter callback type
# =========================================================================

# Type alias for the emit function passed to route_task.
# Signature: async emit(topic, payload, priority) -> None
EmitFn = Callable[..., Any]


# =========================================================================
# Tier budgets -- per design doc Section 11.2
# Module-level constants kept for backward compatibility.
# Runtime code reads from the central config singleton.
# =========================================================================

TIER_FABRIC_BUDGET: dict[ComplexityTier, int] = {
    ComplexityTier.LOW: 1,
    ComplexityTier.MEDIUM: 2,
    ComplexityTier.HIGH: 10,
}

TIER_PLANNER_TOKEN_BUDGET: dict[ComplexityTier, int] = {
    ComplexityTier.LOW: 0,
    ComplexityTier.MEDIUM: 0,
    ComplexityTier.HIGH: 3500,
}


def _get_fabric_budget(tier: ComplexityTier) -> int:
    """Return max Fabric calls for *tier* from central config."""
    from poc.k1_poc.config import get_config

    raw = get_config().orchestrator.tier_fabric_budget
    return raw.get(tier.name, TIER_FABRIC_BUDGET.get(tier, 2))


def _get_planner_token_budget(tier: ComplexityTier) -> int:
    """Return max Planner tokens for *tier* from central config."""
    from poc.k1_poc.config import get_config

    raw = get_config().orchestrator.tier_planner_token_budget
    return raw.get(tier.name, TIER_PLANNER_TOKEN_BUDGET.get(tier, 0))


# =========================================================================
# route_task -- single dispatch point
# =========================================================================


async def route_task(
    task: TaskDispatch,
    tier: ComplexityTier,
    *,
    emit_fn: Optional[EmitFn] = None,
    dispatch_fn: Optional[Callable] = None,
) -> DispatchRecord:
    """Route a task based on its complexity tier.

    V2 Design Ref: Section 11.2

    This is the SINGLE dispatch point (invariant 8). All task routing goes
    through this function. No alternate dispatch paths.

    Args:
        task: The TaskDispatch payload from Front.
        tier: Complexity classification (LOW/MEDIUM/HIGH).
        emit_fn: Async function to emit bus events (LOW tier).
                 Signature: async emit(topic, payload, priority) -> None
        dispatch_fn: Async function to dispatch TaskEnvelope (MEDIUM/HIGH tier).
                     Signature: async dispatch(envelope) -> None

    Returns:
        DispatchRecord documenting what was dispatched and where.
    """
    record = route_task_sync(task, tier)

    if record.tier == ComplexityTier.LOW and emit_fn is not None:
        await emit_fn(record.topic, task, record.priority)
    elif record.tier in (ComplexityTier.MEDIUM, ComplexityTier.HIGH):
        if dispatch_fn is not None and record.envelope is not None:
            await dispatch_fn(record.envelope)

    return record


def route_task_sync(
    task: TaskDispatch,
    tier: ComplexityTier,
) -> DispatchRecord:
    """Route a task synchronously based on complexity tier.

    This helper exists for synchronous callers (FSM event handlers) that need
    the same authoritative routing decision logic as async route_task().
    """
    if tier == ComplexityTier.LOW:
        return _route_low_sync(task)
    elif tier == ComplexityTier.MEDIUM:
        return _route_medium_sync(task)
    elif tier == ComplexityTier.HIGH:
        return _route_high_sync(task)
    else:
        raise ValueError(f"Unknown complexity tier: {tier}")


def _route_low_sync(task: TaskDispatch) -> DispatchRecord:
    """Build LOW-tier dispatch record (sync)."""
    topic = "k1.orchestration.task.dispatch.v1"
    priority = "INTERACTIVE"
    return DispatchRecord(
        tier=ComplexityTier.LOW,
        topic=topic,
        payload=task,
        priority=priority,
    )


def _route_medium_sync(task: TaskDispatch) -> DispatchRecord:
    """Build MEDIUM-tier dispatch record (sync)."""
    intent = task.intents[0].action if task.intents else ""
    envelope = TaskEnvelope(
        intent=intent,
        task_id=task.task_id,
        context=task.context_snapshot or {},
        tier=ComplexityTier.MEDIUM,
        budget=Budget(max_fabric_calls=_get_fabric_budget(ComplexityTier.MEDIUM)),
        session_id=getattr(task, "session_id", ""),
        trace_id=getattr(task, "trace_id", f"trace-{task.task_id}"),
    )
    return DispatchRecord(
        tier=ComplexityTier.MEDIUM,
        envelope=envelope,
    )


def _route_high_sync(task: TaskDispatch) -> DispatchRecord:
    """Build HIGH-tier dispatch record (sync)."""
    intent = task.intents[0].action if task.intents else ""
    envelope = TaskEnvelope(
        intent=intent,
        task_id=task.task_id,
        context=task.context_snapshot or {},
        tier=ComplexityTier.HIGH,
        budget=Budget(
            max_fabric_calls=_get_fabric_budget(ComplexityTier.HIGH),
            max_planner_tokens=_get_planner_token_budget(ComplexityTier.HIGH),
        ),
        session_id=getattr(task, "session_id", ""),
        trace_id=getattr(task, "trace_id", f"trace-{task.task_id}"),
    )
    return DispatchRecord(
        tier=ComplexityTier.HIGH,
        envelope=envelope,
    )


async def _route_low(
    task: TaskDispatch,
    emit_fn: Optional[EmitFn],
) -> DispatchRecord:
    """Route LOW tier: emit directly to Back via task.dispatch.v1.

    V2 Design Ref: Section 11.1 (LOW: Front -> task.dispatch.v1 -> Back)

    Back calls invoke_capability() directly via Fabric.
    No Orchestrator involvement.
    """
    record = _route_low_sync(task)

    if emit_fn is not None:
        await emit_fn(record.topic, task, record.priority)

    log.debug(
        "route_task LOW -> %s (task_id=%s)",
        record.topic,
        task.task_id,
    )
    return record


async def _route_medium(
    task: TaskDispatch,
    dispatch_fn: Optional[Callable],
) -> DispatchRecord:
    """Route MEDIUM tier: create TaskEnvelope and dispatch to OrchestratorStub.

    V2 Design Ref: Section 11.2 (MEDIUM: TaskEnvelope with Budget(max_fabric_calls=2))
    """
    record = _route_medium_sync(task)
    envelope = record.envelope

    if dispatch_fn is not None and envelope is not None:
        await dispatch_fn(envelope)

    log.debug(
        "route_task MEDIUM -> OrchestratorStub (task_id=%s, budget=%d)",
        envelope.task_id,
        envelope.budget.max_fabric_calls,
    )

    return record


async def _route_high(
    task: TaskDispatch,
    dispatch_fn: Optional[Callable],
) -> DispatchRecord:
    """Route HIGH tier: create TaskEnvelope and dispatch to Orchestrator.

    V2 Design Ref: Section 11.2 (HIGH: TaskEnvelope with Budget(max_fabric_calls=10,
    max_planner_tokens=3500))

    POC: interface only. The full Orchestrator + Planner pipeline is not
    implemented. This creates the correct TaskEnvelope so the interface
    is ready for HIGH tier plugging in without refactoring.
    """
    record = _route_high_sync(task)
    envelope = record.envelope

    if dispatch_fn is not None and envelope is not None:
        await dispatch_fn(envelope)

    log.debug(
        "route_task HIGH -> Orchestrator (task_id=%s, budget=%d/%d)",
        envelope.task_id,
        envelope.budget.max_fabric_calls,
        envelope.budget.max_planner_tokens,
    )

    return record
