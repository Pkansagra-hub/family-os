"""GAP-HIL-006 -- response-final decision must STAY in CLARIFYING_WORKER
whenever HIL state is still pending, even if the worker task already
went terminal. Branch 11 of the decision table now keys on
``pending_hitl or has_active_tasks`` instead of active tasks alone.
"""

from __future__ import annotations

from k1.concierge.fsm.response_final_table import (
    ResponseFinalAction,
    decide_response_final,
)
from k1.concierge.fsm.states import ConciergeState


def test_clarifying_worker_stays_when_only_pending_hitl() -> None:
    """No active tasks but HIL still pending -> STAY (the gap closure)."""
    decision = decide_response_final(
        fsm_state=ConciergeState.CLARIFYING_WORKER,
        has_pending_results=False,
        has_active_tasks=False,
        is_fallback=False,
        weave_flush_running=False,
        pending_hitl=True,
    )
    assert decision.action == ResponseFinalAction.STAY
    assert decision.target_state is None
    assert decision.emit_turn_completed is False


def test_clarifying_worker_listens_when_nothing_pending() -> None:
    """Branch 12 -- no active tasks, no pending HIL -> turn done."""
    decision = decide_response_final(
        fsm_state=ConciergeState.CLARIFYING_WORKER,
        has_pending_results=False,
        has_active_tasks=False,
        is_fallback=False,
        weave_flush_running=False,
        pending_hitl=False,
    )
    assert decision.action == ResponseFinalAction.TRANSITION_LISTENING
    assert decision.target_state == ConciergeState.LISTENING
    assert decision.emit_turn_completed is True


def test_clarifying_worker_stays_when_only_active_tasks() -> None:
    """Pre-existing Branch 11 behavior must still hold."""
    decision = decide_response_final(
        fsm_state=ConciergeState.CLARIFYING_WORKER,
        has_pending_results=False,
        has_active_tasks=True,
        is_fallback=False,
        weave_flush_running=False,
        pending_hitl=False,
    )
    assert decision.action == ResponseFinalAction.STAY


def test_pending_hitl_default_false_is_backwards_compatible() -> None:
    """Callers that haven't been updated yet should get legacy behavior."""
    decision = decide_response_final(
        fsm_state=ConciergeState.CLARIFYING_WORKER,
        has_pending_results=False,
        has_active_tasks=False,
        is_fallback=False,
        weave_flush_running=False,
    )
    assert decision.action == ResponseFinalAction.TRANSITION_LISTENING
