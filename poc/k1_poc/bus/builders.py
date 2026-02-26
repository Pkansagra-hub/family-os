"""
poc.k1_poc.bus.builders -- Envelope builder functions for the 28 POC topics.

Each builder produces a ready-to-publish Envelope with:
    - Correct topic string
    - Correct Priority per V2 Section 3 table
    - JSON-serialized payload (PayloadFormat.JSON)
    - parent_id from the causal chain (caller-provided)

Builders are thin: they serialize the payload dict to JSON bytes and
set the topic/priority/parent_id.  The bus stamps envelope_id, sequence,
and created_ns at publish time.

Usage::

    from poc.k1_poc.bus.builders import build_user_input

    env = build_user_input(
        payload={"text": "What is the weather?", "session_id": "s1"},
        parent_id=0,  # root -- no parent
    )
    bus.publish(env)

Causal chain rules (from V2 Section 3):
    - User input is always root (parent_id=0)
    - Task dispatch has parent_id = user input envelope_id
    - Task complete/failed have parent_id = task dispatch envelope_id
    - Final response has parent_id = task complete/dag completed envelope_id
    - Tool events chain: started -> completed (parent_id = started)
    - All other events: caller decides parent_id based on causal context
"""

from __future__ import annotations

import json
import logging
from typing import Any

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from poc.k1_poc.bus.topics import (
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_CLARIFICATION_OUT,
    TOPIC_CLARIFICATION_REQUEST,
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_DAG_COMPLETED,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_HIL_RESPONSE,
    TOPIC_ORCHESTRATION_DELTA,
    TOPIC_PLAN_READY,
    TOPIC_PROACTIVE_FILL,
    TOPIC_RESPONSE_STREAM,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_ACCEPTED,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
)

# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------


def _serialize(payload: dict[str, Any]) -> bytes:
    """Serialize payload dict to compact JSON bytes."""
    return json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")


logger = logging.getLogger(__name__)


def _build(
    topic: str,
    priority: Priority,
    payload: dict[str, Any],
    parent_id: int = 0,
) -> Envelope:
    """Build an Envelope with JSON payload."""
    env = Envelope(
        topic=topic,
        priority=priority,
        payload=_serialize(payload),
        parent_id=parent_id,
        payload_format=PayloadFormat.JSON,
    )
    logger.debug("_build: topic=%s priority=%s parent_id=%d", topic, priority.name, parent_id)
    return env


# ===================================================================
# Session topics (STRICT)
# ===================================================================


def build_user_input(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """User input -- root of a causal chain (parent_id typically 0)."""
    return _build(TOPIC_USER_INPUT, Priority.URGENT, payload, parent_id)


def build_artifact_created(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Artifact created by back half or tool execution."""
    return _build(TOPIC_ARTIFACT_CREATED, Priority.INTERACTIVE, payload, parent_id)


def build_turn_started(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Turn started -- emitted by FSM on turn boundary."""
    return _build(TOPIC_TURN_STARTED, Priority.INTERACTIVE, payload, parent_id)


def build_turn_completed(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Turn completed -- emitted by FSM on turn end."""
    return _build(TOPIC_TURN_COMPLETED, Priority.INTERACTIVE, payload, parent_id)


def build_state_updated(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Session state updated -- background priority, observability."""
    return _build(TOPIC_STATE_UPDATED, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# Response topics (STRICT)
# ===================================================================


def build_response_stream(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Stream chunk -- incremental text for real-time display (Epic 4.2)."""
    return _build(TOPIC_RESPONSE_STREAM, Priority.URGENT, payload, parent_id)


def build_final_response(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Final response delivered to output channel."""
    return _build(TOPIC_FINAL_RESPONSE, Priority.URGENT, payload, parent_id)


def build_clarification_out(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Clarification sent to output channel (outbound to user)."""
    return _build(TOPIC_CLARIFICATION_OUT, Priority.URGENT, payload, parent_id)


# ===================================================================
# Orchestration topics (STRICT)
# ===================================================================


def build_task_dispatch(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task dispatched from Front to Back."""
    return _build(TOPIC_TASK_DISPATCH, Priority.INTERACTIVE, payload, parent_id)


def build_task_complete(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task completed by Back half."""
    return _build(TOPIC_TASK_COMPLETE, Priority.INTERACTIVE, payload, parent_id)


def build_task_failed(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task failed -- carries 7-field diagnostic payload."""
    return _build(TOPIC_TASK_FAILED, Priority.INTERACTIVE, payload, parent_id)


def build_task_cancel(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task cancellation from Front to Back -- URGENT priority."""
    return _build(TOPIC_TASK_CANCEL, Priority.URGENT, payload, parent_id)


def build_task_suspended(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task suspended by Back (waiting for HITL or external)."""
    return _build(TOPIC_TASK_SUSPENDED, Priority.INTERACTIVE, payload, parent_id)


def build_task_resume(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task resume from Front to Back."""
    return _build(TOPIC_TASK_RESUME, Priority.INTERACTIVE, payload, parent_id)


def build_task_accepted(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task accepted by Orchestrator -- confirms dispatch received."""
    return _build(TOPIC_TASK_ACCEPTED, Priority.INTERACTIVE, payload, parent_id)


def build_findings_ready(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Findings ready for presentation."""
    return _build(TOPIC_FINDINGS_READY, Priority.INTERACTIVE, payload, parent_id)


def build_clarification_request(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Clarification request from Back to Front."""
    return _build(TOPIC_CLARIFICATION_REQUEST, Priority.INTERACTIVE, payload, parent_id)


def build_clarification_response(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Clarification response from Front to Back."""
    return _build(TOPIC_CLARIFICATION_RESPONSE, Priority.INTERACTIVE, payload, parent_id)


def build_orchestration_delta(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Orchestration progress delta for FSM tracking."""
    return _build(TOPIC_ORCHESTRATION_DELTA, Priority.INTERACTIVE, payload, parent_id)


def build_dag_completed(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """DAG completed -- all tasks in plan finished."""
    return _build(TOPIC_DAG_COMPLETED, Priority.INTERACTIVE, payload, parent_id)


# ===================================================================
# Tool topics (STRICT, prefix k1.capability)
# ===================================================================


def build_tool_started(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Tool execution started."""
    return _build(TOPIC_TOOL_STARTED, Priority.INTERACTIVE, payload, parent_id)


def build_tool_completed(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Tool execution completed."""
    return _build(TOPIC_TOOL_COMPLETED, Priority.INTERACTIVE, payload, parent_id)


# ===================================================================
# HITL topics (STRICT)
# ===================================================================


def build_hil_request(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Human-in-the-loop request from Back to Front."""
    return _build(TOPIC_HIL_REQUEST, Priority.INTERACTIVE, payload, parent_id)


def build_hil_response(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Human-in-the-loop response -- URGENT, must follow request."""
    return _build(TOPIC_HIL_RESPONSE, Priority.URGENT, payload, parent_id)


# ===================================================================
# Planner topics (STRICT)
# ===================================================================


def build_plan_ready(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Plan ready -- planner has produced an execution plan."""
    return _build(TOPIC_PLAN_READY, Priority.INTERACTIVE, payload, parent_id)


# ===================================================================
# Internal topics (STRICT)
# ===================================================================


def build_weave_batch(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Weave batch -- timer-driven delta aggregation for streaming."""
    return _build(TOPIC_WEAVE_BATCH, Priority.INTERACTIVE, payload, parent_id)


# ===================================================================
# Relaxed topics
# ===================================================================


def build_affect_update(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Affect state update -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_AFFECT_UPDATE, Priority.BACKGROUND, payload, parent_id)


def build_proactive_fill(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Proactive fill suggestion -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_PROACTIVE_FILL, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# Builder registry (topic -> builder function)
# ===================================================================

BUILDERS: dict[str, Any] = {
    TOPIC_USER_INPUT: build_user_input,
    TOPIC_ARTIFACT_CREATED: build_artifact_created,
    TOPIC_TURN_STARTED: build_turn_started,
    TOPIC_TURN_COMPLETED: build_turn_completed,
    TOPIC_STATE_UPDATED: build_state_updated,
    TOPIC_RESPONSE_STREAM: build_response_stream,
    TOPIC_FINAL_RESPONSE: build_final_response,
    TOPIC_CLARIFICATION_OUT: build_clarification_out,
    TOPIC_TASK_DISPATCH: build_task_dispatch,
    TOPIC_TASK_COMPLETE: build_task_complete,
    TOPIC_TASK_FAILED: build_task_failed,
    TOPIC_TASK_CANCEL: build_task_cancel,
    TOPIC_TASK_SUSPENDED: build_task_suspended,
    TOPIC_TASK_RESUME: build_task_resume,
    TOPIC_TASK_ACCEPTED: build_task_accepted,
    TOPIC_FINDINGS_READY: build_findings_ready,
    TOPIC_CLARIFICATION_REQUEST: build_clarification_request,
    TOPIC_CLARIFICATION_RESPONSE: build_clarification_response,
    TOPIC_ORCHESTRATION_DELTA: build_orchestration_delta,
    TOPIC_DAG_COMPLETED: build_dag_completed,
    TOPIC_TOOL_STARTED: build_tool_started,
    TOPIC_TOOL_COMPLETED: build_tool_completed,
    TOPIC_HIL_REQUEST: build_hil_request,
    TOPIC_HIL_RESPONSE: build_hil_response,
    TOPIC_PLAN_READY: build_plan_ready,
    TOPIC_WEAVE_BATCH: build_weave_batch,
    TOPIC_AFFECT_UPDATE: build_affect_update,
    TOPIC_PROACTIVE_FILL: build_proactive_fill,
}


__all__ = [
    # Helpers
    "BUILDERS",
    # Session
    "build_user_input",
    "build_artifact_created",
    "build_turn_started",
    "build_turn_completed",
    "build_state_updated",
    # Response
    "build_response_stream",
    "build_final_response",
    "build_clarification_out",
    # Orchestration
    "build_task_dispatch",
    "build_task_complete",
    "build_task_failed",
    "build_task_cancel",
    "build_task_suspended",
    "build_task_resume",
    "build_task_accepted",
    "build_findings_ready",
    "build_clarification_request",
    "build_clarification_response",
    "build_orchestration_delta",
    "build_dag_completed",
    # Tool
    "build_tool_started",
    "build_tool_completed",
    # HITL
    "build_hil_request",
    "build_hil_response",
    # Planner
    "build_plan_ready",
    # Internal
    "build_weave_batch",
    # Relaxed
    "build_affect_update",
    "build_proactive_fill",
]
