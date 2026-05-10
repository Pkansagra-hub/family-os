"""
k1.concierge.bus.builders -- Envelope builder functions for the 28 POC topics.

Each builder produces a ready-to-publish Envelope with:
    - Correct topic string
    - Correct Priority per V2 Section 3 table
    - JSON-serialized payload (PayloadFormat.JSON)
    - parent_id from the causal chain (caller-provided)

Builders are thin: they serialize the payload dict to JSON bytes and
set the topic/priority/parent_id.  The bus stamps envelope_id, sequence,
and created_ns at publish time.

Usage::

    from k1.concierge.bus.builders import build_user_input

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

import itertools
import json
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, NamedTuple

from k1.bus.envelope import Envelope, PayloadFormat, Priority

# Thread-safe counter for synthetic envelope IDs (envelopes that bypass the
# bus and are delivered directly to a mailbox).  Uses high positive values
# (starting at 1_000_000_000) to avoid collisions with bus-stamped IDs
# which start from 1 and count upward.
SYNTHETIC_ID_START = 1_000_000_000
_synthetic_id_counter = itertools.count(start=SYNTHETIC_ID_START)


def next_synthetic_envelope_id() -> int:
    """Return a unique envelope_id for synthetic envelopes."""
    return next(_synthetic_id_counter)


from k1.concierge.bus.topics import (
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_BACKPOOL_WORKER_ACQUIRED,
    TOPIC_BACKPOOL_WORKER_RELEASED,
    TOPIC_CLARIFICATION_OUT,
    TOPIC_CLARIFICATION_REQUEST,
    TOPIC_CLARIFICATION_RESPONSE,
    TOPIC_CONCIERGE_CONFIG_UPDATE,
    TOPIC_DAG_COMPLETED,
    TOPIC_DEAD_LETTER,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_HIL_RESPONSE,
    TOPIC_HITL_BLOCKED_RED,
    TOPIC_HITL_REQUESTED,
    TOPIC_HITL_RESOLVED,
    TOPIC_HITL_TIMED_OUT,
    TOPIC_INTENT_ARBITRATED,
    TOPIC_METRIC_ALERT,
    TOPIC_METRIC_EMITTED,
    TOPIC_METRIC_SESSION_SUMMARY,
    TOPIC_ORCHESTRATION_DELTA,
    TOPIC_PHASE1_CLASSIFIED,
    TOPIC_PLAN_READY,
    TOPIC_PROACTIVE_FILL,
    TOPIC_RESPONSE_STREAM,
    TOPIC_STATE_UPDATED,
    TOPIC_TASK_ACCEPTED,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_LEASED,
    TOPIC_TASK_MODIFY,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_ROUTED,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_TURN_COMPLETED,
    TOPIC_TURN_STARTED,
    TOPIC_UI_TYPING,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
    TOPIC_WEAVE_DECIDED,
    TOPIC_WEAVE_METRICS,
)

# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def _serialize(payload: "dict[str, Any] | Any") -> bytes:
    """Serialize payload to compact JSON bytes.

    Accepts either a plain dict or a CanonicalEventMeta subclass.
    When given a canonical event, calls to_payload() first.
    Legacy dict payloads are auto-enriched with canonical metadata
    (event_id, ts_utc, payload_schema_version) for ledger compatibility.
    """
    # Import here to avoid circular dependency at module load
    from k1.concierge.events.base import CanonicalEventMeta

    if isinstance(payload, CanonicalEventMeta):
        data = payload.to_payload()
    elif isinstance(payload, dict):
        # M1 E1.4.5: Auto-enrich legacy dicts with canonical metadata
        if "event_id" not in payload:
            payload["event_id"] = str(_uuid.uuid4())
        if "ts_utc" not in payload:
            payload["ts_utc"] = datetime.now(timezone.utc).isoformat()
        if "payload_schema_version" not in payload:
            payload["payload_schema_version"] = "0.1.0"  # pre-migration marker
        data = payload
    else:
        data = payload  # type: ignore[assignment]
    return json.dumps(data, separators=(",", ":"), default=str).encode("utf-8")


def _build(
    topic: str,
    priority: Priority,
    payload: "dict[str, Any] | Any",
    parent_id: int = 0,
) -> Envelope:
    """Build an Envelope with JSON payload.

    Accepts both raw dict payloads (legacy) and CanonicalEventMeta
    subclass instances (V3).

    When ``bus.validate_canonical_events`` is enabled in config, canonical
    event payloads are validated against their schema before serialization.
    Validation errors are logged as warnings but never block publishing
    (soft validation, same philosophy as TopicValidationMiddleware).
    """
    # Optional canonical event validation (M1 E1.3)
    from k1.concierge.events.base import CanonicalEventMeta

    if isinstance(payload, CanonicalEventMeta):
        try:
            from k1.concierge.config.loader import get_config

            if get_config().bus.validate_canonical_events:
                from k1.concierge.events.validator import validate_event

                ok, errors = validate_event(payload.to_payload())
                if not ok:
                    logger.warning(
                        "_build: canonical validation errors for topic=%s event_type=%s: %s",
                        topic,
                        payload.event_type,
                        "; ".join(errors),
                    )
        except Exception:
            # Config not loaded yet (e.g. during test bootstrap) -- skip
            pass

    env = Envelope(
        topic=topic,
        priority=priority,
        payload=_serialize(payload),
        parent_id=parent_id,
        payload_format=PayloadFormat.JSON,
    )
    logger.debug("_build: topic=%s priority=%s parent_id=%d", topic, priority.name, parent_id)
    return env


# ---------------------------------------------------------------------------
# BuilderEntry -- enriched registry entry per topic
# ---------------------------------------------------------------------------


class BuilderEntry(NamedTuple):
    """Registry entry for a bus topic builder.

    Attributes:
        builder_fn:     The builder function (payload, parent_id) -> Envelope.
        canonical_type:  The expected V3 canonical event class, or None for topics
                        that do not yet have a canonical schema.
        priority:       The bus priority for this topic.
    """

    builder_fn: Any  # Callable[[dict | CanonicalEventMeta, int], Envelope]
    canonical_type: type | None
    priority: Priority


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


def build_task_modify(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Task modification request from Arbiter -- adjust running task parameters."""
    return _build(TOPIC_TASK_MODIFY, Priority.INTERACTIVE, payload, parent_id)


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
# HITL lifecycle topics (M6 E6.3) -- observability/audit events
# ===================================================================


def build_hitl_requested(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M6 E6.3.1: HILSubTask created -- observability passthrough."""
    return _build(TOPIC_HITL_REQUESTED, Priority.INTERACTIVE, payload, parent_id)


def build_hitl_resolved(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M6 E6.3.2: HILSubTask resolved -- observability with decision_branch."""
    return _build(TOPIC_HITL_RESOLVED, Priority.INTERACTIVE, payload, parent_id)


def build_hitl_timed_out(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M6 E6.3.3: HILSubTask timed out -- triggers auto-cancel."""
    return _build(TOPIC_HITL_TIMED_OUT, Priority.INTERACTIVE, payload, parent_id)


def build_hitl_blocked_red(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M6 E6.3.4: RED-band capability blocked -- audit proof."""
    return _build(TOPIC_HITL_BLOCKED_RED, Priority.INTERACTIVE, payload, parent_id)


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


def build_dead_letter(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Dead-letter event for rejected/orphan/expired envelopes (M2 E2.2)."""
    return _build(TOPIC_DEAD_LETTER, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# Relaxed topics
# ===================================================================


def build_affect_update(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Affect state update -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_AFFECT_UPDATE, Priority.BACKGROUND, payload, parent_id)


def build_proactive_fill(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Proactive fill suggestion -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_PROACTIVE_FILL, Priority.BACKGROUND, payload, parent_id)


def build_ui_typing(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M8 E8.1.2: User typing signal -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_UI_TYPING, Priority.BACKGROUND, payload, parent_id)


def build_weave_decided(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M8 E8.2.4: Weave decision event -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_WEAVE_DECIDED, Priority.BACKGROUND, payload, parent_id)


def build_weave_metrics(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M8 E8.5.1: Weave session metrics -- RELAXED delivery, BACKGROUND priority."""
    return _build(TOPIC_WEAVE_METRICS, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# Phase 1 & Routing observability (RELAXED) -- M10 E10.3.4
# ===================================================================


def build_phase1_classified(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M10 E10.3.4: Phase 1 classification result -- RELAXED, BACKGROUND."""
    return _build(TOPIC_PHASE1_CLASSIFIED, Priority.BACKGROUND, payload, parent_id)


def build_task_routed(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M10 E10.3.4: Task routing decision -- RELAXED, BACKGROUND."""
    return _build(TOPIC_TASK_ROUTED, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# M11 Observability topics (RELAXED) -- M11 E11.1.3
# ===================================================================


def build_metric_emitted(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M11 E11.1.3: Raw metric envelope -- RELAXED, BACKGROUND."""
    return _build(TOPIC_METRIC_EMITTED, Priority.BACKGROUND, payload, parent_id)


def build_metric_alert(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M11 E11.5: Alert engine trigger -- RELAXED, BACKGROUND."""
    return _build(TOPIC_METRIC_ALERT, Priority.BACKGROUND, payload, parent_id)


def build_metric_session_summary(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M11 E11.5.3: Session-end observability summary -- RELAXED, BACKGROUND."""
    return _build(TOPIC_METRIC_SESSION_SUMMARY, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# Concierge control plane (STRICT) -- M6 E6.4 (C06)
# ===================================================================


def build_concierge_config_update(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M6 E6.4: Runtime config update for concierge components.

    Payload schema: {"weave_policy": {"enabled": bool}, ...}
    Subscribed to by ConciergeController to apply runtime toggles
    (e.g. WeavePolicy.set_enabled) without session restart.
    """
    return _build(TOPIC_CONCIERGE_CONFIG_UPDATE, Priority.INTERACTIVE, payload, parent_id)


# ===================================================================
# Arbiter topics (STRICT) -- M5 E5.1.5
# ===================================================================


def build_intent_arbitrated(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """Arbiter decision emitted before FSM acts on user input (M5)."""
    return _build(TOPIC_INTENT_ARBITRATED, Priority.INTERACTIVE, payload, parent_id)


# ===================================================================
# BackPool topics (STRICT) -- M7 E7.1.4
# ===================================================================


def build_backpool_worker_acquired(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M7 E7.1.4: BackPool worker acquired -- observability event."""
    return _build(TOPIC_BACKPOOL_WORKER_ACQUIRED, Priority.BACKGROUND, payload, parent_id)


def build_backpool_worker_released(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M7 E7.1.4: BackPool worker released -- observability event."""
    return _build(TOPIC_BACKPOOL_WORKER_RELEASED, Priority.BACKGROUND, payload, parent_id)


def build_task_leased(payload: dict[str, Any], parent_id: int = 0) -> Envelope:
    """M7 E7.2.4: Task leased -- ownership record for task/worker binding."""
    return _build(TOPIC_TASK_LEASED, Priority.BACKGROUND, payload, parent_id)


# ===================================================================
# Builder registry (topic -> BuilderEntry)
# ===================================================================

# Lazy import to avoid circular dependency at module load.
# The registry is populated below; canonical_type is set to None for
# topics that do not yet have a V3 schema or where the schema is not
# a 1:1 mapping (e.g., multiple event types share one topic).


def _lazy_canonical_types() -> dict[str, type | None]:
    """Return topic -> canonical event class mapping.

    Imported lazily so the events package can import builders
    without circular dependency.
    """
    from k1.concierge.events.conversation import (  # noqa: F811
        IntentArbitrated,
        UserInputReceived,
    )
    from k1.concierge.events.hitl import (
        HILRequested,
        HILResolved,
        HITLBlockedRedEvent,
        HITLRequestedEvent,
        HITLResolvedEvent,
        HITLTimedOutEvent,
    )
    from k1.concierge.events.hitl import TaskResumed as TaskResumedEvt
    from k1.concierge.events.hitl import TaskSuspended as TaskSuspendedEvt
    from k1.concierge.events.task import (
        TaskCancelled,
        TaskCompleted,
        TaskCreated,
        TaskFailed,
    )

    return {
        TOPIC_USER_INPUT: UserInputReceived,
        TOPIC_TASK_DISPATCH: TaskCreated,
        TOPIC_TASK_COMPLETE: TaskCompleted,
        TOPIC_TASK_FAILED: TaskFailed,
        TOPIC_TASK_CANCEL: TaskCancelled,
        TOPIC_TASK_SUSPENDED: TaskSuspendedEvt,
        TOPIC_TASK_RESUME: TaskResumedEvt,
        TOPIC_HIL_REQUEST: HILRequested,
        TOPIC_HIL_RESPONSE: HILResolved,
        TOPIC_INTENT_ARBITRATED: IntentArbitrated,
        # M6 E6.3: HITL lifecycle canonical types
        TOPIC_HITL_REQUESTED: HITLRequestedEvent,
        TOPIC_HITL_RESOLVED: HITLResolvedEvent,
        TOPIC_HITL_TIMED_OUT: HITLTimedOutEvent,
        TOPIC_HITL_BLOCKED_RED: HITLBlockedRedEvent,
    }


# Legacy flat dict for backward compatibility -- all existing consumers
# that do ``BUILDERS[topic](payload, parent_id)`` continue to work.
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
    TOPIC_TASK_MODIFY: build_task_modify,
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
    TOPIC_DEAD_LETTER: build_dead_letter,
    TOPIC_AFFECT_UPDATE: build_affect_update,
    TOPIC_PROACTIVE_FILL: build_proactive_fill,
    TOPIC_INTENT_ARBITRATED: build_intent_arbitrated,
    # M6 E6.3: HITL lifecycle
    TOPIC_HITL_REQUESTED: build_hitl_requested,
    TOPIC_HITL_RESOLVED: build_hitl_resolved,
    TOPIC_HITL_TIMED_OUT: build_hitl_timed_out,
    TOPIC_HITL_BLOCKED_RED: build_hitl_blocked_red,
    # M7 E7.1.4: BackPool observability
    TOPIC_BACKPOOL_WORKER_ACQUIRED: build_backpool_worker_acquired,
    TOPIC_BACKPOOL_WORKER_RELEASED: build_backpool_worker_released,
    TOPIC_TASK_LEASED: build_task_leased,
    # M8 E8.1.2: User typing signal
    TOPIC_UI_TYPING: build_ui_typing,
    # M8 E8.2.4: Weave decision event
    TOPIC_WEAVE_DECIDED: build_weave_decided,
    # M8 E8.5.1: Weave session metrics
    TOPIC_WEAVE_METRICS: build_weave_metrics,
    # M10 E10.3.4: Phase 1 & routing observability
    TOPIC_PHASE1_CLASSIFIED: build_phase1_classified,
    TOPIC_TASK_ROUTED: build_task_routed,
    # M11 E11.1.3: Observability metrics
    TOPIC_METRIC_EMITTED: build_metric_emitted,
    TOPIC_METRIC_ALERT: build_metric_alert,
    TOPIC_METRIC_SESSION_SUMMARY: build_metric_session_summary,
    # M6 E6.4 (C06): concierge runtime config control plane
    TOPIC_CONCIERGE_CONFIG_UPDATE: build_concierge_config_update,
}


def get_builder_registry() -> dict[str, "BuilderEntry"]:
    """Return the enriched builder registry with canonical types.

    Lazy-loaded to avoid circular imports. Each entry maps a topic
    string to a BuilderEntry(builder_fn, canonical_type, priority).
    """
    canonical = _lazy_canonical_types()
    _priorities: dict[str, Priority] = {
        TOPIC_USER_INPUT: Priority.URGENT,
        TOPIC_ARTIFACT_CREATED: Priority.INTERACTIVE,
        TOPIC_TURN_STARTED: Priority.INTERACTIVE,
        TOPIC_TURN_COMPLETED: Priority.INTERACTIVE,
        TOPIC_STATE_UPDATED: Priority.BACKGROUND,
        TOPIC_RESPONSE_STREAM: Priority.URGENT,
        TOPIC_FINAL_RESPONSE: Priority.URGENT,
        TOPIC_CLARIFICATION_OUT: Priority.URGENT,
        TOPIC_TASK_DISPATCH: Priority.INTERACTIVE,
        TOPIC_TASK_COMPLETE: Priority.INTERACTIVE,
        TOPIC_TASK_FAILED: Priority.INTERACTIVE,
        TOPIC_TASK_CANCEL: Priority.URGENT,
        TOPIC_TASK_SUSPENDED: Priority.INTERACTIVE,
        TOPIC_TASK_RESUME: Priority.INTERACTIVE,
        TOPIC_TASK_ACCEPTED: Priority.INTERACTIVE,
        TOPIC_TASK_MODIFY: Priority.INTERACTIVE,
        TOPIC_FINDINGS_READY: Priority.INTERACTIVE,
        TOPIC_CLARIFICATION_REQUEST: Priority.INTERACTIVE,
        TOPIC_CLARIFICATION_RESPONSE: Priority.INTERACTIVE,
        TOPIC_ORCHESTRATION_DELTA: Priority.INTERACTIVE,
        TOPIC_DAG_COMPLETED: Priority.INTERACTIVE,
        TOPIC_TOOL_STARTED: Priority.INTERACTIVE,
        TOPIC_TOOL_COMPLETED: Priority.INTERACTIVE,
        TOPIC_HIL_REQUEST: Priority.INTERACTIVE,
        TOPIC_HIL_RESPONSE: Priority.URGENT,
        TOPIC_PLAN_READY: Priority.INTERACTIVE,
        TOPIC_WEAVE_BATCH: Priority.INTERACTIVE,
        TOPIC_AFFECT_UPDATE: Priority.BACKGROUND,
        TOPIC_PROACTIVE_FILL: Priority.BACKGROUND,
        TOPIC_INTENT_ARBITRATED: Priority.INTERACTIVE,
        # M6 E6.3: HITL lifecycle
        TOPIC_HITL_REQUESTED: Priority.INTERACTIVE,
        TOPIC_HITL_RESOLVED: Priority.INTERACTIVE,
        TOPIC_HITL_TIMED_OUT: Priority.INTERACTIVE,
        TOPIC_HITL_BLOCKED_RED: Priority.INTERACTIVE,
        # M7 E7.1.4: BackPool observability
        TOPIC_BACKPOOL_WORKER_ACQUIRED: Priority.BACKGROUND,
        TOPIC_BACKPOOL_WORKER_RELEASED: Priority.BACKGROUND,
        TOPIC_TASK_LEASED: Priority.BACKGROUND,
        # M8 E8.1.2: User typing signal
        TOPIC_UI_TYPING: Priority.BACKGROUND,
        # M8 E8.2.4: Weave decision event
        TOPIC_WEAVE_DECIDED: Priority.BACKGROUND,
        # M8 E8.5.1: Weave session metrics
        TOPIC_WEAVE_METRICS: Priority.BACKGROUND,
        # M11 E11.1.3: Observability metrics
        TOPIC_METRIC_EMITTED: Priority.BACKGROUND,
        TOPIC_METRIC_ALERT: Priority.BACKGROUND,
        TOPIC_METRIC_SESSION_SUMMARY: Priority.BACKGROUND,
        # M6 E6.4 (C06): concierge runtime config
        TOPIC_CONCIERGE_CONFIG_UPDATE: Priority.INTERACTIVE,
    }
    return {
        topic: BuilderEntry(
            builder_fn=builder_fn,
            canonical_type=canonical.get(topic),
            priority=_priorities.get(topic, Priority.INTERACTIVE),
        )
        for topic, builder_fn in BUILDERS.items()
    }


__all__ = [
    # Registry
    "BuilderEntry",
    "get_builder_registry",
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
    "build_task_modify",
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
    "build_dead_letter",
    # Relaxed
    "build_affect_update",
    "build_proactive_fill",
    # Arbiter (M5)
    "build_intent_arbitrated",
    # HITL lifecycle (M6)
    "build_hitl_requested",
    "build_hitl_resolved",
    "build_hitl_timed_out",
    "build_hitl_blocked_red",
    # BackPool (M7)
    "build_backpool_worker_acquired",
    "build_backpool_worker_released",
    "build_task_leased",
    # User typing (M8)
    "build_ui_typing",
    # Weave decision (M8)
    "build_weave_decided",
    # Weave metrics (M8 E8.5.1)
    "build_weave_metrics",
    # Phase 1 & routing observability (M10)
    "build_phase1_classified",
    "build_task_routed",
    # M11 Observability
    "build_metric_emitted",
    "build_metric_alert",
    "build_metric_session_summary",
    # M6 E6.4 (C06): concierge runtime config
    "build_concierge_config_update",
]
