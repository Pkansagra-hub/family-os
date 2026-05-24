"""
k1.concierge.fsm.response_final_table -- Response-final decision table.

M2 E2.3.1: Externalizes the 217-line _on_response_final branching logic
into a pure function with zero side effects. All 13 state/condition
combinations produce an explicit ResponseFinalDecision.

The decision table covers:
  - 6 FSM states that can receive response.final
  - Conditions: has_pending_results, has_active_tasks, is_fallback, weave_flush_running
  - Actions: transition, stay, ignore, dead-letter
  - Side-effect flags: emit_turn_completed, drain_front_lock, schedule_weave

V2 Design Ref: Section 4 (FSM: Event Router & State Machine)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from k1.concierge.fsm.states import ConciergeState


class ResponseFinalAction(str, Enum):
    """Action the controller should execute after response.final."""

    TRANSITION_LISTENING = "transition_listening"
    TRANSITION_WEAVING = "transition_weaving"
    TRANSITION_COMPANIONING = "transition_companioning"
    STAY = "stay"
    IGNORE = "ignore"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True, slots=True)
class ResponseFinalDecision:
    """Immutable decision returned by decide_response_final().

    Attributes:
        action: What the controller should do.
        target_state: New FSM state (None if STAY/IGNORE/DEAD_LETTER).
        emit_turn_completed: Whether to emit turn.completed event.
        drain_front_lock: Whether to drain FrontLock queue.
        schedule_weave: Whether to schedule a weave flush.
        release_front_lock: Whether to set front_lock.busy = False.
        entry_type: History entry type for this response.
    """

    action: ResponseFinalAction
    target_state: ConciergeState | None
    emit_turn_completed: bool
    drain_front_lock: bool
    schedule_weave: bool
    release_front_lock: bool
    entry_type: str  # "final", "weave", "proactive", "proactive_fallback"


def decide_response_final(
    fsm_state: ConciergeState,
    has_pending_results: bool,
    has_active_tasks: bool,
    is_fallback: bool,
    weave_flush_running: bool,
) -> ResponseFinalDecision:
    """Pure function: given FSM state + conditions, return the decision.

    Covers all 13 branches from the response-final truth table:

    | # | State            | Condition                          | Action                 | Target        |
    |---|------------------|------------------------------------|------------------------|---------------|
    | 1 | DISPATCHING      | has_pending_results                | weave flush            | WEAVING       |
    | 2 | DISPATCHING      | has_active_tasks                   | wait for tasks         | COMPANIONING  |
    | 3 | DISPATCHING      | no pending, no active              | turn done              | LISTENING     |
    | 4 | DELIVERING       | has_pending_results                | weave transition       | WEAVING       |
    | 5 | WEAVING          | has_pending + no flush running     | re-weave               | WEAVING       |
    | 6 | WEAVING          | has_pending + flush running        | skip (flush handles)   | WEAVING (stay)|
    | 7 | DELIVERING       | no pending                         | turn done              | LISTENING     |
    | 8 | WEAVING          | no pending                         | turn done              | LISTENING     |
    | 9 | COMPANIONING     | has_active_tasks                   | stay, wait             | COMPANIONING  |
    |10 | COMPANIONING     | no active tasks                    | race-safe exit         | LISTENING     |
    |11 | CLARIFYING_WORKER| has_active_tasks                   | wait for HITL answer    | CLARIFYING_WORKER |
    |12 | CLARIFYING_WORKER| no active tasks                    | turn done              | LISTENING     |
    |13 | LISTENING        | spurious final                     | ignore                 | LISTENING     |

    Args:
        fsm_state: Current FSM state.
        has_pending_results: Whether turn_state has pending results.
        has_active_tasks: Whether active_task_ids is non-empty.
        is_fallback: Whether the response text is a budget/degenerate fallback.
        weave_flush_running: Whether a weave flush task is currently running.

    Returns:
        ResponseFinalDecision with action, target_state, and side-effect flags.
    """
    # Resolve history entry_type from state
    entry_type = _resolve_entry_type(fsm_state, is_fallback)

    # -- DISPATCHING ---------------------------------------------------
    if fsm_state == ConciergeState.DISPATCHING:
        if has_pending_results:
            # Branch 1: pending results -> weave flush
            return ResponseFinalDecision(
                action=ResponseFinalAction.TRANSITION_WEAVING,
                target_state=ConciergeState.WEAVING,
                emit_turn_completed=False,
                drain_front_lock=False,
                schedule_weave=True,
                release_front_lock=True,
                entry_type=entry_type,
            )
        if has_active_tasks:
            # Branch 2: active tasks -> wait in COMPANIONING
            return ResponseFinalDecision(
                action=ResponseFinalAction.TRANSITION_COMPANIONING,
                target_state=ConciergeState.COMPANIONING,
                emit_turn_completed=False,
                drain_front_lock=False,
                schedule_weave=False,
                release_front_lock=True,
                entry_type=entry_type,
            )
        # Branch 3: no pending, no active -> conversational-only turn done
        return ResponseFinalDecision(
            action=ResponseFinalAction.TRANSITION_LISTENING,
            target_state=ConciergeState.LISTENING,
            emit_turn_completed=True,
            drain_front_lock=True,
            schedule_weave=False,
            release_front_lock=False,
            entry_type=entry_type,
        )

    # -- DELIVERING ----------------------------------------------------
    if fsm_state == ConciergeState.DELIVERING:
        if has_pending_results:
            # Branch 4: pending results -> weave
            return ResponseFinalDecision(
                action=ResponseFinalAction.TRANSITION_WEAVING,
                target_state=ConciergeState.WEAVING,
                emit_turn_completed=False,
                drain_front_lock=False,
                schedule_weave=True,
                release_front_lock=True,
                entry_type=entry_type,
            )
        # Branch 7: no pending -> turn done
        return ResponseFinalDecision(
            action=ResponseFinalAction.TRANSITION_LISTENING,
            target_state=ConciergeState.LISTENING,
            emit_turn_completed=True,
            drain_front_lock=True,
            schedule_weave=False,
            release_front_lock=False,
            entry_type=entry_type,
        )

    # -- WEAVING -------------------------------------------------------
    if fsm_state == ConciergeState.WEAVING:
        if has_pending_results:
            if weave_flush_running:
                # Branch 6: flush already running -> stay, it will drain
                return ResponseFinalDecision(
                    action=ResponseFinalAction.STAY,
                    target_state=None,
                    emit_turn_completed=False,
                    drain_front_lock=False,
                    schedule_weave=False,
                    release_front_lock=True,
                    entry_type=entry_type,
                )
            # Branch 5: re-weave
            return ResponseFinalDecision(
                action=ResponseFinalAction.TRANSITION_WEAVING,
                target_state=ConciergeState.WEAVING,
                emit_turn_completed=False,
                drain_front_lock=False,
                schedule_weave=True,
                release_front_lock=True,
                entry_type=entry_type,
            )
        # Branch 8: no pending -> turn done
        return ResponseFinalDecision(
            action=ResponseFinalAction.TRANSITION_LISTENING,
            target_state=ConciergeState.LISTENING,
            emit_turn_completed=True,
            drain_front_lock=True,
            schedule_weave=False,
            release_front_lock=False,
            entry_type=entry_type,
        )

    # -- COMPANIONING --------------------------------------------------
    if fsm_state == ConciergeState.COMPANIONING:
        if has_active_tasks:
            # Branch 9: stay, wait for tasks
            return ResponseFinalDecision(
                action=ResponseFinalAction.STAY,
                target_state=None,
                emit_turn_completed=False,
                drain_front_lock=False,
                schedule_weave=False,
                release_front_lock=True,
                entry_type=entry_type,
            )
        # Branch 10: race-condition safe exit
        return ResponseFinalDecision(
            action=ResponseFinalAction.TRANSITION_LISTENING,
            target_state=ConciergeState.LISTENING,
            emit_turn_completed=True,
            drain_front_lock=True,
            schedule_weave=False,
            release_front_lock=False,
            entry_type=entry_type,
        )

    # -- CLARIFYING_WORKER ---------------------------------------------
    if fsm_state == ConciergeState.CLARIFYING_WORKER:
        if has_active_tasks:
            # Branch 11: HITL question delivered; stay open for the user's answer.
            # Drain the FrontLock so an answer typed while HITL_RELAY was rendering
            # can immediately enter HITL_RESOLVE.
            return ResponseFinalDecision(
                action=ResponseFinalAction.STAY,
                target_state=None,
                emit_turn_completed=False,
                drain_front_lock=True,
                schedule_weave=False,
                release_front_lock=True,
                entry_type=entry_type,
            )
        # Branch 12: no active tasks -> turn done
        return ResponseFinalDecision(
            action=ResponseFinalAction.TRANSITION_LISTENING,
            target_state=ConciergeState.LISTENING,
            emit_turn_completed=True,
            drain_front_lock=True,
            schedule_weave=False,
            release_front_lock=False,
            entry_type=entry_type,
        )

    # -- LISTENING -----------------------------------------------------
    if fsm_state == ConciergeState.LISTENING:
        # Branch 13: spurious final -> ignore
        return ResponseFinalDecision(
            action=ResponseFinalAction.IGNORE,
            target_state=None,
            emit_turn_completed=False,
            drain_front_lock=False,
            schedule_weave=False,
            release_front_lock=False,
            entry_type=entry_type,
        )

    # -- Any other state -> dead-letter --------------------------------
    return ResponseFinalDecision(
        action=ResponseFinalAction.DEAD_LETTER,
        target_state=None,
        emit_turn_completed=False,
        drain_front_lock=False,
        schedule_weave=False,
        release_front_lock=False,
        entry_type=entry_type,
    )


def _resolve_entry_type(fsm_state: ConciergeState, is_fallback: bool) -> str:
    """Determine history entry type from FSM state.

    Returns one of: "weave", "proactive_fallback", "proactive", "final".
    """
    if fsm_state == ConciergeState.WEAVING:
        return "weave"
    if fsm_state == ConciergeState.DELIVERING and is_fallback:
        return "proactive_fallback"
    if fsm_state == ConciergeState.DELIVERING:
        return "proactive"
    return "final"


__all__ = [
    "ResponseFinalAction",
    "ResponseFinalDecision",
    "decide_response_final",
]
