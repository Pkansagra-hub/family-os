"""
k1.concierge.delta.emitters -- Back-side delta emitters.

V2 Design Ref: Section 5 (Single Writer Invariant, rule 2)
V2 Design Ref: Section 5, DeltaAggregator Write Pipeline

Back NEVER writes SS directly (V2 Section 5, Rule 2).  Instead, it
emits structured deltas to the bus, which the DeltaAggregator collects.

These functions are called by the Back actor when it produces outputs
that need to flow into SessionState:

    emit_artifact          -- invoke_capability produced a durable artifact
    emit_task_state_change -- task lifecycle transition

Both functions create a SessionDelta, publish it to the bus via the
injected publish_fn, and return the delta for observability.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from k1.concierge.delta.session_delta import SessionDelta
from k1.concierge.delta.topics import ARTIFACT_CREATED, TASK_STATE_CHANGED

logger = logging.getLogger(__name__)

# =========================================================================
# Valid task state transitions (V2 Section 5, TaskStateEntry Schema)
# =========================================================================

VALID_TASK_STATUSES: frozenset[str] = frozenset(
    {
        "DISPATCHED",
        "IN_PROGRESS",
        "SUSPENDED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }
)


async def emit_artifact(
    task_id: str,
    artifact_type: str,
    artifact_data: dict[str, Any],
    publish_fn: Callable[[str, SessionDelta], Awaitable[None]],
    parent_delta_id: str | None = None,
) -> SessionDelta:
    """Emit an artifact delta from Back.

    Called when Back's invoke_capability produces a durable artifact
    (booking confirmation, search results snapshot, etc.).

    The artifact flows through the bus to the DeltaAggregator, which
    batches it and forwards to FSM.apply_deltas() for writing to
    the task_artifacts SS section.

    Args:
        task_id:       Originating task ID.
        artifact_type: Type of artifact (booking, search_results, etc.).
        artifact_data: The artifact payload.
        publish_fn:    Async callback to publish delta to bus: (topic, delta).
        parent_delta_id: Optional causal parent delta ID for ordering.

    Returns:
        The emitted SessionDelta (for observability or chaining).
    """
    delta = SessionDelta(
        section="task_artifacts",
        key=f"{task_id}:{artifact_type}",
        operation="append",
        data={"type": artifact_type, "task_id": task_id, **artifact_data},
        source_task_id=task_id,
        parent_delta_id=parent_delta_id,
        timestamp_ns=time.monotonic_ns(),
    )
    await publish_fn(ARTIFACT_CREATED, delta)
    logger.info(
        "emit_artifact: task=%s type=%s delta=%s",
        task_id,
        artifact_type,
        delta.delta_id,
    )
    return delta


async def emit_task_state_change(
    task_id: str,
    new_status: str,
    metadata: dict[str, Any] | None = None,
    publish_fn: Callable[[str, SessionDelta], Awaitable[None]] | None = None,
    parent_delta_id: str | None = None,
) -> SessionDelta:
    """Emit a task state transition delta from Back.

    Called when a task transitions its lifecycle state:
        DISPATCHED -> IN_PROGRESS -> COMPLETED/FAILED/CANCELLED

    The delta flows through the bus to the DeltaAggregator, which
    batches it and forwards to FSM.apply_deltas() for writing to
    the task_state SS section.

    Args:
        task_id:    The task whose state changed.
        new_status: New status string (must be a valid task status).
        metadata:   Optional metadata (error message, tool_calls count, etc.).
        publish_fn: Async callback to publish delta to bus: (topic, delta).
                    If None, delta is created but not published (testing).
        parent_delta_id: Optional causal parent delta ID for ordering.

    Returns:
        The emitted SessionDelta.

    Raises:
        ValueError: If new_status is not a valid task status.
    """
    if new_status not in VALID_TASK_STATUSES:
        raise ValueError(
            f"Invalid task status '{new_status}', " f"must be one of {sorted(VALID_TASK_STATUSES)}"
        )
    delta = SessionDelta(
        section="task_state",
        key=task_id,
        operation="update",
        data={"status": new_status, **(metadata or {})},
        source_task_id=task_id,
        parent_delta_id=parent_delta_id,
        timestamp_ns=time.monotonic_ns(),
    )
    if publish_fn is not None:
        await publish_fn(TASK_STATE_CHANGED, delta)
    logger.info(
        "emit_task_state_change: task=%s status=%s delta=%s",
        task_id,
        new_status,
        delta.delta_id,
    )
    return delta
