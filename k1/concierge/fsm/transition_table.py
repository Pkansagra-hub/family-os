"""
k1.concierge.fsm.transition_table -- Legal FSM transitions & guard matrix.

V2 Design Ref: Section 4 (State Diagram, FrontLock)
V3 M2 E2.1.1: Full guard matrix covering all subscribed topics.

Format: TRANSITION_TABLE[from_state][trigger] = to_state | None
        FULL_GUARD_TABLE[from_state][topic]  = (GuardAction, target_state | None)

Triggers are bus topic strings OR internal synthetic events
prefixed with a dot-free token (e.g. "phase1.complete",
"pending_results.non_empty", "interrupt.routed", "proactive.routed",
"clarification.detected").
"""

from __future__ import annotations

from enum import Enum

from k1.concierge.bus.topics import (
    TOPIC_AFFECT_UPDATE,
    TOPIC_ARTIFACT_CREATED,
    TOPIC_BACKPOOL_WORKER_ACQUIRED,
    TOPIC_BACKPOOL_WORKER_RELEASED,
    TOPIC_DAG_COMPLETED,
    TOPIC_FINAL_RESPONSE,
    TOPIC_FINDINGS_READY,
    TOPIC_HIL_REQUEST,
    TOPIC_HITL_BLOCKED_RED,
    TOPIC_HITL_REQUESTED,
    TOPIC_HITL_RESOLVED,
    TOPIC_HITL_TIMED_OUT,
    TOPIC_INTENT_ARBITRATED,
    TOPIC_PROACTIVE_FILL,
    TOPIC_TASK_CANCEL,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_LEASED,
    TOPIC_TASK_MODIFY,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_UI_TYPING,
    TOPIC_USER_INPUT,
    TOPIC_WEAVE_BATCH,
    TOPIC_WEAVE_DECIDED,
    TOPIC_WEAVE_METRICS,
)
from k1.concierge.fsm.states import ConciergeState

# ---------------------------------------------------------------------------
# M2 E2.1.1: Guard action enum
# ---------------------------------------------------------------------------


class GuardAction(str, Enum):
    """Action the FSM guard gate takes for a (state, topic) pair.

    TRANSITION  -- Validate via transition table and change state.
    PASSTHROUGH -- Forward to handler without state change (findings, clarification, weave).
    OBSERVE     -- Log/history only, no routing or state change (artifact, affect).
    QUEUE       -- Queue in FrontLock or pending_results for later processing.
    DEAD_LETTER -- Reject: event is invalid in this state.
    """

    TRANSITION = "transition"
    PASSTHROUGH = "passthrough"
    OBSERVE = "observe"
    QUEUE = "queue"
    DEAD_LETTER = "dead_letter"


# Synthetic (internal) trigger constants -- not real bus topics.
TRIGGER_CLARIFICATION_DETECTED = "clarification.detected"
TRIGGER_PENDING_RESULTS_NON_EMPTY = "pending_results.non_empty"
TRIGGER_INTERRUPT_ROUTED = "interrupt.routed"
TRIGGER_PROACTIVE_ROUTED = "proactive.routed"
TRIGGER_SAME_TURN_COMPLETE = "same_turn.task.complete"
TRIGGER_DEFERRED_HITL = "deferred_hitl.surface"

TRANSITION_TABLE: dict[ConciergeState, dict[str, ConciergeState | None]] = {
    ConciergeState.LISTENING: {
        TOPIC_USER_INPUT: ConciergeState.DISPATCHING,
        TOPIC_TASK_COMPLETE: ConciergeState.PROACTIVE_WAKE,
        TRIGGER_DEFERRED_HITL: ConciergeState.CLARIFYING_WORKER,
    },
    ConciergeState.DISPATCHING: {
        TOPIC_TASK_DISPATCH: ConciergeState.COMPANIONING,
        TOPIC_FINAL_RESPONSE: ConciergeState.LISTENING,
        TOPIC_TASK_CANCEL: ConciergeState.CANCELLING,
        TRIGGER_CLARIFICATION_DETECTED: ConciergeState.CLARIFYING_USER,
        # Back tasks may complete while front is processing in DISPATCHING.
        # Pending results must be flushed via WEAVING, not orphaned.
        TRIGGER_PENDING_RESULTS_NON_EMPTY: ConciergeState.WEAVING,
    },
    ConciergeState.COMPANIONING: {
        TOPIC_TASK_COMPLETE: ConciergeState.DELIVERING,
        TOPIC_TASK_FAILED: ConciergeState.DELIVERING,
        TOPIC_TASK_SUSPENDED: ConciergeState.CLARIFYING_WORKER,
        TOPIC_HIL_REQUEST: ConciergeState.CLARIFYING_WORKER,  # M6 unified HIL gate request
        TOPIC_USER_INPUT: ConciergeState.INTERRUPT_HANDLING,
        TOPIC_TOOL_STARTED: ConciergeState.PROGRESSING,
        TOPIC_TASK_CANCEL: ConciergeState.CANCELLING,
        TOPIC_TASK_DISPATCH: ConciergeState.COMPANIONING,  # idempotent multi-dispatch
        # Front may emit response.final alongside task dispatches.
        # This happens when Front gives an immediate text answer AND
        # dispatches background tasks. The response closes the user-
        # facing turn; dispatched tasks continue asynchronously.
        TOPIC_FINAL_RESPONSE: ConciergeState.LISTENING,
        # Same-turn completion: task dispatched and completed in the
        # same turn -- Front STANDARD already presented the result,
        # so skip DELIVERING and go straight to LISTENING.
        TRIGGER_SAME_TURN_COMPLETE: ConciergeState.LISTENING,
    },
    ConciergeState.PROGRESSING: {
        TOPIC_TOOL_COMPLETED: ConciergeState.COMPANIONING,
        TOPIC_TASK_COMPLETE: ConciergeState.DELIVERING,
        TOPIC_TASK_FAILED: ConciergeState.DELIVERING,
        TOPIC_TASK_SUSPENDED: ConciergeState.CLARIFYING_WORKER,
        TOPIC_HIL_REQUEST: ConciergeState.CLARIFYING_WORKER,  # M6 unified HIL gate request
        TOPIC_USER_INPUT: ConciergeState.INTERRUPT_HANDLING,
        TOPIC_TASK_CANCEL: ConciergeState.CANCELLING,
    },
    ConciergeState.DELIVERING: {
        TOPIC_FINAL_RESPONSE: ConciergeState.LISTENING,
        TRIGGER_PENDING_RESULTS_NON_EMPTY: ConciergeState.WEAVING,
    },
    ConciergeState.CLARIFYING_USER: {
        TOPIC_USER_INPUT: ConciergeState.DISPATCHING,
    },
    ConciergeState.CLARIFYING_WORKER: {
        TOPIC_USER_INPUT: ConciergeState.CLARIFYING_WORKER,
        TOPIC_TASK_RESUME: ConciergeState.COMPANIONING,
        TOPIC_FINAL_RESPONSE: None,
    },
    ConciergeState.CANCELLING: {
        TOPIC_TASK_FAILED: ConciergeState.DELIVERING,
    },
    ConciergeState.INTERRUPT_HANDLING: {
        TRIGGER_INTERRUPT_ROUTED: ConciergeState.DISPATCHING,
    },
    ConciergeState.PROACTIVE_WAKE: {
        TRIGGER_PROACTIVE_ROUTED: ConciergeState.DELIVERING,
    },
    ConciergeState.WEAVING: {
        TOPIC_FINAL_RESPONSE: ConciergeState.LISTENING,
        TRIGGER_PENDING_RESULTS_NON_EMPTY: ConciergeState.WEAVING,
    },
}


def is_legal(from_state: ConciergeState, trigger: str) -> bool:
    """Check if a transition is legal."""
    state_table = TRANSITION_TABLE.get(from_state)
    if state_table is None:
        return False
    return trigger in state_table


def target_state(from_state: ConciergeState, trigger: str) -> ConciergeState | None:
    """Return the static target state for a transition, or None.

    None means either:
        - the transition is illegal, or
        - the transition is legal but target is chosen dynamically by handler logic.
    """
    state_table = TRANSITION_TABLE.get(from_state)
    if state_table is None:
        return None
    return state_table.get(trigger)


# ---------------------------------------------------------------------------
# M2 E2.1.1: All 19 topics subscribed by ConciergeController._subscribe_all()
# ---------------------------------------------------------------------------

SUBSCRIBED_TOPICS: frozenset[str] = frozenset(
    {
        TOPIC_USER_INPUT,
        TOPIC_FINAL_RESPONSE,
        TOPIC_TASK_DISPATCH,
        TOPIC_DAG_COMPLETED,
        TOPIC_TASK_COMPLETE,
        TOPIC_TASK_FAILED,
        TOPIC_TASK_CANCEL,
        TOPIC_TASK_SUSPENDED,
        TOPIC_TASK_RESUME,
        TOPIC_FINDINGS_READY,
        TOPIC_ARTIFACT_CREATED,
        TOPIC_AFFECT_UPDATE,
        TOPIC_PROACTIVE_FILL,
        TOPIC_TOOL_STARTED,
        TOPIC_TOOL_COMPLETED,
        TOPIC_WEAVE_BATCH,
        # M5 E5.5.1: Arbiter topics
        TOPIC_INTENT_ARBITRATED,
        TOPIC_TASK_MODIFY,
        # M6 E6.5.1: HITL lifecycle observability topics
        TOPIC_HITL_REQUESTED,
        TOPIC_HITL_RESOLVED,
        TOPIC_HITL_TIMED_OUT,
        TOPIC_HITL_BLOCKED_RED,
        # M7 E7.5.1: BackPool / Lease observability topics
        TOPIC_BACKPOOL_WORKER_ACQUIRED,
        TOPIC_BACKPOOL_WORKER_RELEASED,
        TOPIC_TASK_LEASED,
        # M8 E8.1.2: User typing signal
        TOPIC_UI_TYPING,
        # M8 E8.2.4: Weave decision observability
        TOPIC_WEAVE_DECIDED,
        # M8 E8.5.1: Weave session metrics
        TOPIC_WEAVE_METRICS,
    }
)


# Aliases for readability
_T = GuardAction.TRANSITION
_P = GuardAction.PASSTHROUGH
_O = GuardAction.OBSERVE
_Q = GuardAction.QUEUE
_D = GuardAction.DEAD_LETTER

S = ConciergeState

# ---------------------------------------------------------------------------
# M2 E2.1.1: FULL_GUARD_TABLE -- 11 states x 18 subscribed topics = 198 cells
# (DAG_COMPLETED is normalizer, included as 19th topic for completeness)
#
# Each cell: (GuardAction, target_state_or_None)
#   TRANSITION  -> (T, target_state)   -- validated state change
#   PASSTHROUGH -> (P, None)           -- forward without state change
#   OBSERVE     -> (O, None)           -- log/history only
#   QUEUE       -> (Q, None)           -- queue for later delivery
#   DEAD_LETTER -> (D, None)           -- reject event
#
# Derivation: Every cell was read from the actual handler code in
# controller.py to match current runtime behavior.
# ---------------------------------------------------------------------------

FULL_GUARD_TABLE: dict[
    ConciergeState,
    dict[str, tuple[GuardAction, ConciergeState | None]],
] = {
    # ------------------------------------------------------------------
    # LISTENING: idle, waiting for user input or proactive task.complete
    # ------------------------------------------------------------------
    S.LISTENING: {
        TOPIC_USER_INPUT: (_T, S.DISPATCHING),
        TOPIC_FINAL_RESPONSE: (_D, None),  # spurious final in LISTENING is logged & ignored
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),  # normalizes to task.complete/failed
        TOPIC_TASK_COMPLETE: (_T, S.PROACTIVE_WAKE),
        TOPIC_TASK_FAILED: (_Q, None),  # queue for later presentation
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),  # store context, defer HITL
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1: HITL lifecycle observe
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1: timeout can fire in any state
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1: pool observability
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2: user typing signal
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4: weave decision observe
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # DISPATCHING: Phase 1 classification running, Front processing
    # ------------------------------------------------------------------
    S.DISPATCHING: {
        TOPIC_USER_INPUT: (_D, None),  # re-entrant, drop
        TOPIC_FINAL_RESPONSE: (_T, S.LISTENING),  # also handles pending_results -> WEAVING
        TOPIC_TASK_DISPATCH: (_T, S.COMPANIONING),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),  # queue in pending_results
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_T, S.CANCELLING),
        TOPIC_TASK_SUSPENDED: (_O, None),  # store context, defer
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_O, None),  # Front react_loop executes tools during DISPATCHING
        TOPIC_TOOL_COMPLETED: (_O, None),  # Front react_loop completes tools during DISPATCHING
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # COMPANIONING: Front idle, waiting for Back task.complete
    # ------------------------------------------------------------------
    S.COMPANIONING: {
        TOPIC_USER_INPUT: (_T, S.INTERRUPT_HANDLING),
        TOPIC_FINAL_RESPONSE: (_T, S.LISTENING),
        TOPIC_TASK_DISPATCH: (_T, S.COMPANIONING),  # idempotent multi-dispatch
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_T, S.DELIVERING),
        TOPIC_TASK_FAILED: (_T, S.DELIVERING),
        TOPIC_TASK_CANCEL: (_T, S.CANCELLING),
        TOPIC_TASK_SUSPENDED: (_T, S.CLARIFYING_WORKER),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_T, S.PROGRESSING),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # PROGRESSING: Back executing a tool
    # ------------------------------------------------------------------
    S.PROGRESSING: {
        TOPIC_USER_INPUT: (_T, S.INTERRUPT_HANDLING),
        TOPIC_FINAL_RESPONSE: (_D, None),
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_T, S.DELIVERING),
        TOPIC_TASK_FAILED: (_T, S.DELIVERING),
        TOPIC_TASK_CANCEL: (_T, S.CANCELLING),
        TOPIC_TASK_SUSPENDED: (_T, S.CLARIFYING_WORKER),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_T, S.COMPANIONING),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # DELIVERING: Front presenting Back results
    # ------------------------------------------------------------------
    S.DELIVERING: {
        TOPIC_USER_INPUT: (_Q, None),  # queue in FrontLock
        TOPIC_FINAL_RESPONSE: (_T, S.LISTENING),  # also handles pending -> WEAVING
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),  # queue in pending_results
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_O, None),  # WEAVE runs tools during DELIVERING
        TOPIC_TOOL_COMPLETED: (_O, None),  # WEAVE runs tools during DELIVERING
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # CLARIFYING_USER: Front asking user for clarification
    # ------------------------------------------------------------------
    S.CLARIFYING_USER: {
        TOPIC_USER_INPUT: (_T, S.DISPATCHING),
        TOPIC_FINAL_RESPONSE: (_D, None),
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # CLARIFYING_WORKER: HITL -- user answering Back's question
    # ------------------------------------------------------------------
    S.CLARIFYING_WORKER: {
        TOPIC_USER_INPUT: (_T, S.CLARIFYING_WORKER),  # same-turn HITL
        TOPIC_FINAL_RESPONSE: (_T, None),  # target decided by response_final_table
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_T, S.COMPANIONING),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # CANCELLING: waiting for task.failed (cancelled)
    # ------------------------------------------------------------------
    S.CANCELLING: {
        TOPIC_USER_INPUT: (_Q, None),  # queue for after cancel resolves
        TOPIC_FINAL_RESPONSE: (_D, None),
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),  # late completion during cancel
        TOPIC_TASK_FAILED: (_T, S.DELIVERING),
        TOPIC_TASK_CANCEL: (_D, None),  # already cancelling
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # INTERRUPT_HANDLING: transient -- routing interrupt to DISPATCHING
    # ------------------------------------------------------------------
    S.INTERRUPT_HANDLING: {
        TOPIC_USER_INPUT: (_D, None),
        TOPIC_FINAL_RESPONSE: (_D, None),
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # PROACTIVE_WAKE: transient -- routing proactive completion to DELIVERING
    # ------------------------------------------------------------------
    S.PROACTIVE_WAKE: {
        TOPIC_USER_INPUT: (_Q, None),  # queue in FrontLock
        TOPIC_FINAL_RESPONSE: (_D, None),
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
    # ------------------------------------------------------------------
    # WEAVING: Front presenting batched weave results
    # ------------------------------------------------------------------
    S.WEAVING: {
        TOPIC_USER_INPUT: (_Q, None),  # queue in FrontLock
        TOPIC_FINAL_RESPONSE: (_T, S.LISTENING),  # also handles re-weave
        TOPIC_TASK_DISPATCH: (_D, None),
        TOPIC_DAG_COMPLETED: (_P, None),
        TOPIC_TASK_COMPLETE: (_Q, None),  # queue in pending_results
        TOPIC_TASK_FAILED: (_Q, None),
        TOPIC_TASK_CANCEL: (_D, None),
        TOPIC_TASK_SUSPENDED: (_O, None),
        TOPIC_TASK_RESUME: (_D, None),
        TOPIC_FINDINGS_READY: (_P, None),
        TOPIC_ARTIFACT_CREATED: (_O, None),
        TOPIC_AFFECT_UPDATE: (_O, None),
        TOPIC_PROACTIVE_FILL: (_O, None),
        TOPIC_TOOL_STARTED: (_D, None),
        TOPIC_TOOL_COMPLETED: (_D, None),
        TOPIC_WEAVE_BATCH: (_P, None),
        TOPIC_INTENT_ARBITRATED: (_O, None),  # M5 5.5.1: arbiter event, informational
        TOPIC_TASK_MODIFY: (_O, None),  # M5 5.5.1: modify-inflight event, informational
        TOPIC_HITL_REQUESTED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_RESOLVED: (_O, None),  # M6 6.5.1
        TOPIC_HITL_TIMED_OUT: (_O, None),  # M6 6.5.1
        TOPIC_HITL_BLOCKED_RED: (_O, None),  # M6 6.5.1
        TOPIC_BACKPOOL_WORKER_ACQUIRED: (_O, None),  # M7 7.5.1
        TOPIC_BACKPOOL_WORKER_RELEASED: (_O, None),  # M7 7.5.1
        TOPIC_TASK_LEASED: (_O, None),  # M7 7.5.1
        TOPIC_UI_TYPING: (_O, None),  # M8 8.1.2
        TOPIC_WEAVE_DECIDED: (_O, None),  # M8 8.2.4
        TOPIC_WEAVE_METRICS: (_O, None),  # M8 8.5.1: weave session metrics
    },
}


def get_guard_action(
    state: ConciergeState,
    topic: str,
) -> tuple[GuardAction, ConciergeState | None]:
    """Look up the guard action for a (state, topic) pair.

    Returns (DEAD_LETTER, None) for unknown topics (closed-world assumption).
    """
    state_row = FULL_GUARD_TABLE.get(state)
    if state_row is None:
        return (GuardAction.DEAD_LETTER, None)
    return state_row.get(topic, (GuardAction.DEAD_LETTER, None))
