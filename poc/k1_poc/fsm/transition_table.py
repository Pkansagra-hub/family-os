"""
poc.k1_poc.fsm.transition_table -- Legal FSM transitions.

V2 Design Ref: Section 4 (State Diagram, FrontLock)

Format: TRANSITION_TABLE[from_state][trigger] = to_state

Triggers are bus topic strings OR internal synthetic events
prefixed with a dot-free token (e.g. "phase1.complete",
"pending_results.non_empty", "interrupt.routed", "proactive.routed",
"clarification.detected").
"""

from __future__ import annotations

from poc.k1_poc.bus.topics import (
    TOPIC_FINAL_RESPONSE,
    TOPIC_TASK_COMPLETE,
    TOPIC_TASK_DISPATCH,
    TOPIC_TASK_FAILED,
    TOPIC_TASK_RESUME,
    TOPIC_TASK_SUSPENDED,
    TOPIC_TOOL_COMPLETED,
    TOPIC_TOOL_STARTED,
    TOPIC_USER_INPUT,
)
from poc.k1_poc.fsm.states import ConciergeState

# Synthetic (internal) trigger constants -- not real bus topics.
TRIGGER_PHASE1_COMPLETE = "phase1.complete"
TRIGGER_CLARIFICATION_DETECTED = "clarification.detected"
TRIGGER_PENDING_RESULTS_NON_EMPTY = "pending_results.non_empty"
TRIGGER_INTERRUPT_ROUTED = "interrupt.routed"
TRIGGER_PROACTIVE_ROUTED = "proactive.routed"
TRIGGER_SAME_TURN_COMPLETE = "same_turn.task.complete"

TRANSITION_TABLE: dict[ConciergeState, dict[str, ConciergeState]] = {
    ConciergeState.LISTENING: {
        TOPIC_USER_INPUT: ConciergeState.DISPATCHING,
        TOPIC_TASK_COMPLETE: ConciergeState.PROACTIVE_WAKE,
    },
    ConciergeState.DISPATCHING: {
        TOPIC_TASK_DISPATCH: ConciergeState.COMPANIONING,
        TOPIC_FINAL_RESPONSE: ConciergeState.LISTENING,
        TRIGGER_CLARIFICATION_DETECTED: ConciergeState.CLARIFYING_USER,
        # Back tasks may complete while front is processing in DISPATCHING.
        # Pending results must be flushed via WEAVING, not orphaned.
        TRIGGER_PENDING_RESULTS_NON_EMPTY: ConciergeState.WEAVING,
    },
    ConciergeState.COMPANIONING: {
        TOPIC_TASK_COMPLETE: ConciergeState.DELIVERING,
        TOPIC_TASK_FAILED: ConciergeState.DELIVERING,
        TOPIC_TASK_SUSPENDED: ConciergeState.CLARIFYING_WORKER,
        TOPIC_USER_INPUT: ConciergeState.INTERRUPT_HANDLING,
        TOPIC_TOOL_STARTED: ConciergeState.PROGRESSING,
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
        TOPIC_USER_INPUT: ConciergeState.INTERRUPT_HANDLING,
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
    """Return the target state for a transition, or None if illegal."""
    state_table = TRANSITION_TABLE.get(from_state)
    if state_table is None:
        return None
    return state_table.get(trigger)
