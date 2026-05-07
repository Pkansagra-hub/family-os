"""
k1.concierge.task.envelope_bridge -- Bridge between task dataclasses and bus envelopes.

V2 Design Ref: Section 3 (Event Taxonomy, envelope fields)
V2 Design Ref: Section 8.2 (TaskDispatch, TaskComplete, TaskFailed payloads)

In the full K1 system, this would use the FlatBuffers Envelope from
k1.bus.envelope.  In the POC, we use a lightweight dict-based envelope
that mirrors the canonical fields.

The bus stamps envelope_id, sequence, and created_ns at publish time
via Envelope.with_bus_fields() -- we don't set those here.

Priority mapping follows k1.bus.envelope.Priority:
    URGENT=0, REALTIME=1, INTERACTIVE=2, BACKGROUND=3

Urgency-to-priority mapping (from V2 Section 8.2 TaskIntent.urgency):
    "urgent"     -> Priority.URGENT (0)
    "normal"     -> Priority.INTERACTIVE (2)
    "background" -> Priority.BACKGROUND (3)
"""

from __future__ import annotations

from typing import Any

from k1.concierge.task.dispatch import TaskComplete, TaskDispatch, TaskFailed
from k1.concierge.task.topics import TASK_COMPLETE, TASK_DISPATCH, TASK_FAILED

# =========================================================================
# Urgency -> Priority mapping (mirrors k1.bus.envelope.Priority values)
# =========================================================================

_URGENCY_PRIORITY: dict[str, int] = {
    "urgent": 0,  # Priority.URGENT
    "normal": 2,  # Priority.INTERACTIVE
    "background": 3,  # Priority.BACKGROUND
}


def _resolve_dispatch_priority(dispatch: TaskDispatch) -> int:
    """Determine envelope priority from the highest-urgency intent.

    If any intent is "urgent", the whole dispatch is URGENT.
    Otherwise, if any is "background" and rest are "normal", use BACKGROUND.
    Default: INTERACTIVE.
    """
    max_urgency = "normal"
    for intent in dispatch.intents:
        if intent.urgency == "urgent":
            return _URGENCY_PRIORITY["urgent"]
        if intent.urgency == "background" and max_urgency == "normal":
            max_urgency = "background"
    return _URGENCY_PRIORITY.get(max_urgency, 2)


# =========================================================================
# Dispatch -> Envelope
# =========================================================================


def dispatch_to_envelope(
    dispatch: TaskDispatch,
    session_id: str,
    request_id: str,
    cognitive_trace_id: str,
    parent_envelope_id: int = 0,
) -> dict[str, Any]:
    """Create a bus envelope dict for a TaskDispatch.

    The envelope carries the TaskDispatch as an opaque JSON payload.
    The parent_envelope_id enables causal ordering in the TimingChain:
    for chained tasks, set parent_envelope_id to the envelope_id of
    the parent task's dispatch envelope.

    Args:
        dispatch:             The TaskDispatch to wrap.
        session_id:           Session scope.
        request_id:           Request scope within session.
        cognitive_trace_id:   Cross-K0/K1 correlation key.
        parent_envelope_id:   Causal parent (0 = root / no parent).

    Returns:
        Dict with canonical envelope fields ready for bus publish.
    """
    return {
        "topic": TASK_DISPATCH,
        "priority": _resolve_dispatch_priority(dispatch),
        "cognitive_trace_id": cognitive_trace_id,
        "session_id": session_id,
        "request_id": request_id,
        "parent_id": parent_envelope_id,
        "payload": dispatch.to_payload(),
        "payload_format": 1,  # PayloadFormat.JSON
    }


# =========================================================================
# Complete -> Envelope
# =========================================================================


def complete_to_envelope(
    complete: TaskComplete,
    session_id: str,
    request_id: str,
    cognitive_trace_id: str,
    parent_envelope_id: int = 0,
) -> dict[str, Any]:
    """Create a bus envelope dict for a TaskComplete.

    Args:
        complete:             The TaskComplete to wrap.
        session_id:           Session scope.
        request_id:           Request scope within session.
        cognitive_trace_id:   Cross-K0/K1 correlation key.
        parent_envelope_id:   Causal parent (dispatch envelope_id).

    Returns:
        Dict with canonical envelope fields ready for bus publish.
    """
    return {
        "topic": TASK_COMPLETE,
        "priority": 2,  # Priority.INTERACTIVE
        "cognitive_trace_id": cognitive_trace_id,
        "session_id": session_id,
        "request_id": request_id,
        "parent_id": parent_envelope_id,
        "payload": complete.to_payload(),
        "payload_format": 1,  # PayloadFormat.JSON
    }


# =========================================================================
# Failed -> Envelope
# =========================================================================


def failed_to_envelope(
    failed: TaskFailed,
    session_id: str,
    request_id: str,
    cognitive_trace_id: str,
    parent_envelope_id: int = 0,
) -> dict[str, Any]:
    """Create a bus envelope dict for a TaskFailed.

    Args:
        failed:               The TaskFailed to wrap.
        session_id:           Session scope.
        request_id:           Request scope within session.
        cognitive_trace_id:   Cross-K0/K1 correlation key.
        parent_envelope_id:   Causal parent (dispatch envelope_id).

    Returns:
        Dict with canonical envelope fields ready for bus publish.
    """
    return {
        "topic": TASK_FAILED,
        "priority": 2,  # Priority.INTERACTIVE
        "cognitive_trace_id": cognitive_trace_id,
        "session_id": session_id,
        "request_id": request_id,
        "parent_id": parent_envelope_id,
        "payload": failed.to_payload(),
        "payload_format": 1,  # PayloadFormat.JSON
    }
