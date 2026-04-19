"""
k1.concierge.bus.topics -- SINGLE SOURCE OF TRUTH for all POC topic constants.

This module is the authoritative definition site for every bus topic
string used in the K1 POC.  Do NOT define topic strings elsewhere.
All other modules must import from here (or re-export from here).

28 topics from V2 Section 3 topic taxonomy.  Every constant maps to a
topic string already governed by k1/bus/timing/defaults.py prefix rules.

Subscription groups partition topics by role:
    FRONT_SUBSCRIPTIONS  -- topics the Front half subscribes to
    BACK_SUBSCRIPTIONS   -- topics the Back half subscribes to

Classification sets for testing and introspection:
    ALL_TOPICS           -- all 28 topic strings
    STRICT_TOPICS        -- topics with DeliveryMode.STRICT (26)
    RELAXED_TOPICS       -- topics with DeliveryMode.RELAXED (2)
    URGENT_TOPICS        -- topics with Priority.URGENT (4)

SessionState events (k1.sessionstate.*) are NOT defined here.
They flow dynamically via SessionBusAdapter which maps event_type strings
to k1.session.{event_type} topics at runtime.

Infrastructure topics (k1.fabric.learning, k1.k0.sse, k1.agent.{id}.delta.v1)
are K1-level concerns, not POC-specific.  They exist in DEFAULT_RULES but
are not assigned constants here.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Session topics (prefix: k1.session -> STRICT)
# ---------------------------------------------------------------------------
TOPIC_USER_INPUT = "k1.session.user.input.v1"
TOPIC_ARTIFACT_CREATED = "k1.session.artifact.created.v1"
TOPIC_TURN_STARTED = "k1.session.turn.started.v1"
TOPIC_TURN_COMPLETED = "k1.session.turn.completed.v1"
TOPIC_STATE_UPDATED = "k1.session.state.updated.v1"

# ---------------------------------------------------------------------------
# Response topics (prefix: k1.response -> STRICT)
# ---------------------------------------------------------------------------
TOPIC_RESPONSE_STREAM = "k1.response.stream.v1"
TOPIC_FINAL_RESPONSE = "k1.response.final.v1"
TOPIC_CLARIFICATION_OUT = "k1.response.clarification.v1"

# ---------------------------------------------------------------------------
# Orchestration topics (prefix: k1.orchestration -> STRICT)
# ---------------------------------------------------------------------------
TOPIC_TASK_DISPATCH = "k1.orchestration.task.dispatch.v1"
TOPIC_TASK_COMPLETE = "k1.orchestration.task.complete.v1"
TOPIC_TASK_FAILED = "k1.orchestration.task.failed.v1"
TOPIC_TASK_CANCEL = "k1.orchestration.task.cancel.v1"
TOPIC_TASK_SUSPENDED = "k1.orchestration.task.suspended.v1"
TOPIC_TASK_RESUME = "k1.orchestration.task.resume.v1"
TOPIC_TASK_ACCEPTED = "k1.orchestration.task.accepted.v1"
TOPIC_TASK_MODIFY = "k1.orchestration.task.modify.v1"  # M5 E5.2.3
TOPIC_FINDINGS_READY = "k1.orchestration.findings.ready.v1"
TOPIC_CLARIFICATION_REQUEST = "k1.orchestration.clarification.request.v1"
TOPIC_CLARIFICATION_RESPONSE = "k1.orchestration.clarification.response.v1"
TOPIC_ORCHESTRATION_DELTA = "k1.orchestration.delta.v1"
TOPIC_DAG_COMPLETED = "k1.orchestration.dag.completed.v1"

# ---------------------------------------------------------------------------
# Tool topics (prefix: k1.capability -> STRICT)
# ---------------------------------------------------------------------------
TOPIC_TOOL_STARTED = "k1.tool.started.v1"
TOPIC_TOOL_COMPLETED = "k1.tool.completed.v1"

# ---------------------------------------------------------------------------
# HITL topics (prefix: k1.hil -> STRICT)
#
# ROUTING CLARIFICATION (V3 E0.1.3):
#   k1.orchestration.task.suspended / task.resume are FSM LIFECYCLE events.
#   They control state transitions (PROGRESSING -> CLARIFYING_WORKER, etc.).
#
#   k1.hil.request / hil.response are PROTOCOL-LEVEL detail events within
#   the suspension flow. They carry the actual HITL question/answer payload
#   between Front and Back.
#
#   When Back needs HITL:
#     1. Back emits task.suspended (FSM lifecycle -> state transition)
#     2. FSM routes to Front, which emits hil.request (protocol detail)
#     3. User answers, Front emits hil.response (protocol detail)
#     4. Front emits task.resume (FSM lifecycle -> state transition)
#
#   FRONT_SUBSCRIPTIONS includes TOPIC_HIL_REQUEST (line ~174).
#   BACK_SUBSCRIPTIONS includes TOPIC_HIL_RESPONSE (line ~185).
#   Both are correct and intentional.
# ---------------------------------------------------------------------------
TOPIC_HIL_REQUEST = "k1.hil.request.v1"
TOPIC_HIL_RESPONSE = "k1.hil.response.v1"

# ---------------------------------------------------------------------------
# M6 HITL Lifecycle topics -- observability events emitted by the FSM/
# coordinator at each HITL lifecycle boundary.  Distinct from the protocol-
# level TOPIC_HIL_REQUEST/RESPONSE which carry question/answer payloads.
# ---------------------------------------------------------------------------
TOPIC_HITL_REQUESTED = "k1.hitl.requested.v1"  # E6.3.1: sub-task created
TOPIC_HITL_RESOLVED = "k1.hitl.resolved.v1"  # E6.3.2: user answered
TOPIC_HITL_TIMED_OUT = "k1.hitl.timed_out.v1"  # E6.3.3: timeout auto-cancel
TOPIC_HITL_BLOCKED_RED = "k1.hitl.blocked_red.v1"  # E6.3.4: RED band block

# ---------------------------------------------------------------------------
# Planner topics (prefix: k1.planner -> STRICT)
# ---------------------------------------------------------------------------
TOPIC_PLAN_READY = "k1.planner.plan.ready.v1"

# ---------------------------------------------------------------------------
# Internal topics (prefix: k1.internal -> STRICT)
# ---------------------------------------------------------------------------
TOPIC_WEAVE_BATCH = "k1.internal.weave.batch.v1"
TOPIC_DEAD_LETTER = "k1.internal.dead_letter.v1"

# ---------------------------------------------------------------------------
# BackPool topics (prefix: k1.backpool -> STRICT) -- M7 E7.1.4
# ---------------------------------------------------------------------------
TOPIC_BACKPOOL_WORKER_ACQUIRED = "k1.backpool.worker.acquired.v1"
TOPIC_BACKPOOL_WORKER_RELEASED = "k1.backpool.worker.released.v1"
TOPIC_TASK_LEASED = "k1.backpool.task.leased.v1"

# ---------------------------------------------------------------------------
# Arbiter topics (prefix: k1.arbiter -> STRICT) -- M5 E5.1.5
# ---------------------------------------------------------------------------
TOPIC_INTENT_ARBITRATED = "k1.arbiter.intent.v1"

# ---------------------------------------------------------------------------
# Phase 1 & Routing observability topics -- M10 E10.3.4
# ---------------------------------------------------------------------------
TOPIC_PHASE1_CLASSIFIED = "k1.phase1.classified.v1"
TOPIC_TASK_ROUTED = "k1.task.routed.v1"

# ---------------------------------------------------------------------------
# Relaxed topics
# ---------------------------------------------------------------------------
TOPIC_AFFECT_UPDATE = "k1.affect.update.v1"  # k1.affect -> RELAXED
TOPIC_PROACTIVE_FILL = "k1.proactive.fill.v1"  # k1.proactive -> RELAXED
TOPIC_UI_TYPING = "k1.ui.typing.v1"  # M8 E8.1.2: user typing signal -> RELAXED
TOPIC_WEAVE_DECIDED = "k1.conversation.weave.decided.v1"  # M8 E8.2.4: weave decision -> RELAXED
TOPIC_WEAVE_METRICS = "k1.metrics.weave.v1"  # M8 E8.5.1: weave session metrics -> RELAXED

# ---------------------------------------------------------------------------
# M11 Observability topics (prefix: k1.metrics -> RELAXED)
# ---------------------------------------------------------------------------
TOPIC_METRIC_EMITTED = "k1.metrics.emitted.v1"  # M11 E11.1.3: raw metric envelope
TOPIC_METRIC_ALERT = "k1.metrics.alert.v1"  # M11 E11.5: alert engine trigger
TOPIC_METRIC_SESSION_SUMMARY = "k1.metrics.session_summary.v1"  # M11 E11.5.3: session summary


# ===================================================================
# Classification sets
# ===================================================================

ALL_TOPICS: frozenset[str] = frozenset(
    {
        TOPIC_USER_INPUT,
        TOPIC_ARTIFACT_CREATED,
        TOPIC_TURN_STARTED,
        TOPIC_TURN_COMPLETED,
        TOPIC_STATE_UPDATED,
        TOPIC_RESPONSE_STREAM,
        TOPIC_FINAL_RESPONSE,
        TOPIC_CLARIFICATION_OUT,
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_COMPLETE,
        TOPIC_TASK_FAILED,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_SUSPENDED,
        TOPIC_TASK_RESUME,
        TOPIC_TASK_ACCEPTED,
        TOPIC_TASK_MODIFY,
        TOPIC_FINDINGS_READY,
        TOPIC_CLARIFICATION_REQUEST,
        TOPIC_CLARIFICATION_RESPONSE,
        TOPIC_ORCHESTRATION_DELTA,
        TOPIC_DAG_COMPLETED,
        TOPIC_TOOL_STARTED,
        TOPIC_TOOL_COMPLETED,
        TOPIC_HIL_REQUEST,
        TOPIC_HIL_RESPONSE,
        TOPIC_HITL_REQUESTED,
        TOPIC_HITL_RESOLVED,
        TOPIC_HITL_TIMED_OUT,
        TOPIC_HITL_BLOCKED_RED,
        TOPIC_PLAN_READY,
        TOPIC_WEAVE_BATCH,
        TOPIC_DEAD_LETTER,
        TOPIC_BACKPOOL_WORKER_ACQUIRED,
        TOPIC_BACKPOOL_WORKER_RELEASED,
        TOPIC_TASK_LEASED,
        TOPIC_INTENT_ARBITRATED,
        TOPIC_AFFECT_UPDATE,
        TOPIC_PROACTIVE_FILL,
        TOPIC_UI_TYPING,
        TOPIC_WEAVE_DECIDED,
        TOPIC_WEAVE_METRICS,
        TOPIC_PHASE1_CLASSIFIED,
        TOPIC_TASK_ROUTED,
        TOPIC_METRIC_EMITTED,
        TOPIC_METRIC_ALERT,
        TOPIC_METRIC_SESSION_SUMMARY,
    }
)

STRICT_TOPICS: frozenset[str] = ALL_TOPICS - {
    TOPIC_AFFECT_UPDATE,
    TOPIC_PROACTIVE_FILL,
    TOPIC_UI_TYPING,
    TOPIC_WEAVE_DECIDED,
    TOPIC_WEAVE_METRICS,
    TOPIC_PHASE1_CLASSIFIED,
    TOPIC_TASK_ROUTED,
    TOPIC_METRIC_EMITTED,
    TOPIC_METRIC_ALERT,
    TOPIC_METRIC_SESSION_SUMMARY,
}

RELAXED_TOPICS: frozenset[str] = frozenset(
    {
        TOPIC_AFFECT_UPDATE,
        TOPIC_PROACTIVE_FILL,
        TOPIC_UI_TYPING,
        TOPIC_WEAVE_DECIDED,
        TOPIC_WEAVE_METRICS,
        TOPIC_PHASE1_CLASSIFIED,
        TOPIC_TASK_ROUTED,
        TOPIC_METRIC_EMITTED,
        TOPIC_METRIC_ALERT,
        TOPIC_METRIC_SESSION_SUMMARY,
    }
)

URGENT_TOPICS: frozenset[str] = frozenset(
    {
        TOPIC_USER_INPUT,
        TOPIC_RESPONSE_STREAM,
        TOPIC_FINAL_RESPONSE,
        TOPIC_CLARIFICATION_OUT,
        TOPIC_TASK_CANCEL,
        TOPIC_HIL_RESPONSE,
    }
)


# ===================================================================
# Subscription groups (by role)
# ===================================================================

# ---------------------------------------------------------------------------
# FSM-routed topics (V3 E0.1.5)
#
# ROUTING INVARIANT: FSM-routed topics MUST NOT appear in
# FRONT_SUBSCRIPTIONS.  The FSM is the sole routing authority for
# these topics -- it delivers them to Front via _deliver_to_front().
# Including them in FRONT_SUBSCRIPTIONS creates DUPLICATE delivery
# (one from bus subscription, one from FSM), causing front_handler
# to execute multiple times for the same event.
#
# Observability-only topics (turn.started, turn.completed,
# tool.started, tool.completed) are also excluded from
# FRONT_SUBSCRIPTIONS.  Routing them to front_handler causes an
# infinite loop: front emits FINAL_RESPONSE -> FSM emits
# turn.completed -> front processes turn.completed as STANDARD ->
# LLM call -> FINAL_RESPONSE -> turn.completed -> ... (infinite).
# These topics are handled by OutputChannel and FSM controller
# directly via their own subscriptions.
# ---------------------------------------------------------------------------

FSM_ROUTED_TOPICS: frozenset[str] = frozenset(
    {
        TOPIC_TASK_COMPLETE,
        TOPIC_TASK_FAILED,
        TOPIC_TASK_SUSPENDED,
        TOPIC_FINDINGS_READY,
        TOPIC_CLARIFICATION_REQUEST,
        TOPIC_DAG_COMPLETED,
        TOPIC_WEAVE_BATCH,
        TOPIC_PROACTIVE_FILL,
    }
)

FRONT_SUBSCRIPTIONS: frozenset[str] = frozenset(
    {
        TOPIC_TASK_ACCEPTED,
        TOPIC_ORCHESTRATION_DELTA,
        TOPIC_HIL_REQUEST,
        TOPIC_PLAN_READY,
    }
)

# Enforce routing invariant at import time (V3 E0.1.5)
assert FSM_ROUTED_TOPICS.isdisjoint(FRONT_SUBSCRIPTIONS), (
    f"ROUTING INVARIANT VIOLATION: FSM-routed topics must not appear in "
    f"FRONT_SUBSCRIPTIONS. Overlap: {FSM_ROUTED_TOPICS & FRONT_SUBSCRIPTIONS}"
)

# Topics the Back half subscribes to (inbound from Front, user actions)
BACK_SUBSCRIPTIONS: frozenset[str] = frozenset(
    {
        TOPIC_USER_INPUT,
        TOPIC_TASK_DISPATCH,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_RESUME,
        TOPIC_CLARIFICATION_RESPONSE,
        TOPIC_HIL_RESPONSE,
        TOPIC_AFFECT_UPDATE,
    }
)

# Priority mapping (topic -> Priority value) for envelope builders
# Mirrors V2 Section 3 table exactly
_TOPIC_PRIORITY: dict[str, int] = {
    # URGENT (Priority.URGENT = 0)
    TOPIC_USER_INPUT: 0,
    TOPIC_RESPONSE_STREAM: 0,
    TOPIC_FINAL_RESPONSE: 0,
    TOPIC_CLARIFICATION_OUT: 0,
    TOPIC_TASK_CANCEL: 0,
    TOPIC_HIL_RESPONSE: 0,
    # BACKGROUND (Priority.BACKGROUND = 3)
    TOPIC_STATE_UPDATED: 3,
    TOPIC_AFFECT_UPDATE: 3,
    TOPIC_PROACTIVE_FILL: 3,
    TOPIC_DEAD_LETTER: 3,
    TOPIC_BACKPOOL_WORKER_ACQUIRED: 3,
    TOPIC_BACKPOOL_WORKER_RELEASED: 3,
    TOPIC_TASK_LEASED: 3,
    TOPIC_UI_TYPING: 3,
    TOPIC_WEAVE_DECIDED: 3,
    TOPIC_WEAVE_METRICS: 3,
    TOPIC_PHASE1_CLASSIFIED: 3,
    TOPIC_TASK_ROUTED: 3,
    # M11 Observability (BACKGROUND)
    TOPIC_METRIC_EMITTED: 3,
    TOPIC_METRIC_ALERT: 3,
    TOPIC_METRIC_SESSION_SUMMARY: 3,
    # INTERACTIVE (Priority.INTERACTIVE = 2) -- everything else
}


def get_priority(topic: str) -> int:
    """Return the Priority int value for a topic.  Defaults to INTERACTIVE (2)."""
    return _TOPIC_PRIORITY.get(topic, 2)


__all__ = [
    # Individual topic constants
    "TOPIC_USER_INPUT",
    "TOPIC_ARTIFACT_CREATED",
    "TOPIC_TURN_STARTED",
    "TOPIC_TURN_COMPLETED",
    "TOPIC_STATE_UPDATED",
    "TOPIC_RESPONSE_STREAM",
    "TOPIC_FINAL_RESPONSE",
    "TOPIC_CLARIFICATION_OUT",
    "TOPIC_TASK_DISPATCH",
    "TOPIC_TASK_COMPLETE",
    "TOPIC_TASK_FAILED",
    "TOPIC_TASK_CANCEL",
    "TOPIC_TASK_SUSPENDED",
    "TOPIC_TASK_RESUME",
    "TOPIC_TASK_ACCEPTED",
    "TOPIC_TASK_MODIFY",
    "TOPIC_FINDINGS_READY",
    "TOPIC_CLARIFICATION_REQUEST",
    "TOPIC_CLARIFICATION_RESPONSE",
    "TOPIC_ORCHESTRATION_DELTA",
    "TOPIC_DAG_COMPLETED",
    "TOPIC_TOOL_STARTED",
    "TOPIC_TOOL_COMPLETED",
    "TOPIC_HIL_REQUEST",
    "TOPIC_HIL_RESPONSE",
    "TOPIC_HITL_REQUESTED",
    "TOPIC_HITL_RESOLVED",
    "TOPIC_HITL_TIMED_OUT",
    "TOPIC_HITL_BLOCKED_RED",
    "TOPIC_PLAN_READY",
    "TOPIC_WEAVE_BATCH",
    "TOPIC_DEAD_LETTER",
    "TOPIC_BACKPOOL_WORKER_ACQUIRED",
    "TOPIC_BACKPOOL_WORKER_RELEASED",
    "TOPIC_TASK_LEASED",
    "TOPIC_INTENT_ARBITRATED",
    "TOPIC_AFFECT_UPDATE",
    "TOPIC_PROACTIVE_FILL",
    "TOPIC_UI_TYPING",
    "TOPIC_WEAVE_DECIDED",
    "TOPIC_WEAVE_METRICS",
    # M11 Observability
    "TOPIC_METRIC_EMITTED",
    "TOPIC_METRIC_ALERT",
    "TOPIC_METRIC_SESSION_SUMMARY",
    # Sets
    "ALL_TOPICS",
    "STRICT_TOPICS",
    "RELAXED_TOPICS",
    "URGENT_TOPICS",
    "FSM_ROUTED_TOPICS",
    "FRONT_SUBSCRIPTIONS",
    "BACK_SUBSCRIPTIONS",
    # Utility
    "get_priority",
]
