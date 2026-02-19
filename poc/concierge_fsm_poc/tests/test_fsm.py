"""TEST-001: FSM Transition Tests -- 22 tests covering all 14 transition types.

Aligned to ``concierge_fsm_flows.md`` Part 3.
"""

from __future__ import annotations

import pytest

from poc.concierge_fsm_poc.fsm.controller import (
    Action,
    Event,
    FSMController,
    InvalidTransitionError,
    State,
)


@pytest.fixture()
def fsm() -> FSMController:
    return FSMController()


# ---------------------------------------------------------------------------
# Helper: drive FSM to a target state via valid transitions
# ---------------------------------------------------------------------------
def _drive_to(fsm: FSMController, target: State) -> None:
    """Drive FSM from LISTENING to *target* via shortest valid path."""
    if target == State.LISTENING:
        return
    # LISTENING -> ACKING
    fsm.transition(Event.MESSAGE_RECEIVED)
    if target == State.ACKING:
        return
    if target == State.CLARIFYING:
        fsm.transition(Event.GAPS_DETECTED)
        return
    if target == State.DELIVERING:
        fsm.transition(Event.CRISIS_DETECTED)
        return
    # ACKING -> DISPATCHING
    fsm.transition(Event.PHASE1_COMPLETE)
    if target == State.DISPATCHING:
        return
    if target == State.COMPANIONING:
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        return
    if target == State.PROGRESSING:
        fsm.transition(Event.PRELIMINARY_ACK_SENT)
        fsm.transition(Event.PROGRESS_RECEIVED)
        return
    if target == State.INTERRUPT_HANDLING:
        fsm.transition(Event.INTERRUPT_DETECTED)
        return


# ---------------------------------------------------------------------------
# T1-T14: All 14 transition types (18 table entries)
# ---------------------------------------------------------------------------


class TestTransitions:
    """Every transition from the TRANSITION_TABLE."""

    def test_t1_listening_to_acking(self, fsm: FSMController) -> None:
        new, actions = fsm.transition(Event.MESSAGE_RECEIVED)
        assert new is State.ACKING
        assert actions == [Action.ACQUIRE_LOCK, Action.RUN_PHASE1]
        assert fsm.state is State.ACKING

    def test_t2_crisis_bypass(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.ACKING)
        new, actions = fsm.transition(Event.CRISIS_DETECTED)
        assert new is State.DELIVERING
        assert actions == [Action.CRISIS_RESPONSE]

    def test_t3_phase1_complete(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.ACKING)
        new, actions = fsm.transition(Event.PHASE1_COMPLETE)
        assert new is State.DISPATCHING
        assert actions == [Action.ROUTE_BY_TIER]

    def test_t4_gaps_detected(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.ACKING)
        new, actions = fsm.transition(Event.GAPS_DETECTED)
        assert new is State.CLARIFYING
        assert actions == [Action.SEND_CLARIFICATION]

    def test_t5_clarification_received(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.CLARIFYING)
        new, actions = fsm.transition(Event.CLARIFICATION_RECEIVED)
        assert new is State.ACKING
        assert actions == [Action.MERGE_CLARIFICATION]

    def test_t6_max_rounds_reached(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.CLARIFYING)
        new, actions = fsm.transition(Event.MAX_ROUNDS_REACHED)
        assert new is State.DISPATCHING
        assert actions == [Action.FORCE_PROCEED, Action.ROUTE_BY_TIER]

    def test_t7_preliminary_ack(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.DISPATCHING)
        new, actions = fsm.transition(Event.PRELIMINARY_ACK_SENT)
        assert new is State.COMPANIONING
        assert actions == [Action.SEND_ACKNOWLEDGE, Action.START_TOOL_LOOP]

    def test_t8_low_direct_deliver(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.DISPATCHING)
        new, actions = fsm.transition(Event.DISPATCH_COMPLETE)
        assert new is State.DELIVERING
        assert actions == [Action.ASSEMBLE_RESPONSE]

    def test_t9_progress_received(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.COMPANIONING)
        new, actions = fsm.transition(Event.PROGRESS_RECEIVED)
        assert new is State.PROGRESSING
        assert actions == [Action.STREAM_PROGRESS]

    def test_t10_companion_dispatch_complete(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.COMPANIONING)
        new, actions = fsm.transition(Event.DISPATCH_COMPLETE)
        assert new is State.DELIVERING
        assert actions == [Action.ASSEMBLE_RESPONSE]

    def test_t11_progress_dispatch_complete(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.PROGRESSING)
        new, actions = fsm.transition(Event.DISPATCH_COMPLETE)
        assert new is State.DELIVERING
        assert actions == [Action.ASSEMBLE_RESPONSE]

    def test_t12_response_delivered(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.DELIVERING)
        new, actions = fsm.transition(Event.RESPONSE_DELIVERED)
        assert new is State.LISTENING
        assert actions == [Action.FLUSH_AND_CHECKPOINT]

    def test_t13a_interrupt_dispatching(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.DISPATCHING)
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert actions == [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]

    def test_t13b_interrupt_companioning(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.COMPANIONING)
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert actions == [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]

    def test_t13c_interrupt_progressing(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.PROGRESSING)
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert actions == [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]

    def test_t13d_interrupt_clarifying(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.CLARIFYING)
        new, actions = fsm.transition(Event.INTERRUPT_DETECTED)
        assert new is State.INTERRUPT_HANDLING
        assert actions == [Action.CANCEL_INFLIGHT, Action.PARTIAL_FLUSH]

    def test_t14_interrupt_handled(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.INTERRUPT_HANDLING)
        new, actions = fsm.transition(Event.INTERRUPT_HANDLED)
        assert new is State.ACKING
        assert actions == [Action.REENTER_ACKING]


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    """Verify correct rejection of impossible state+event pairs."""

    def test_invalid_from_listening(self, fsm: FSMController) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            fsm.transition(Event.DISPATCH_COMPLETE)
        assert exc_info.value.state is State.LISTENING
        assert exc_info.value.event is Event.DISPATCH_COMPLETE

    def test_invalid_from_delivering(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.DELIVERING)
        with pytest.raises(InvalidTransitionError) as exc_info:
            fsm.transition(Event.INTERRUPT_DETECTED)
        assert exc_info.value.state is State.DELIVERING
        assert exc_info.value.event is Event.INTERRUPT_DETECTED


# ---------------------------------------------------------------------------
# is_interruptible
# ---------------------------------------------------------------------------


class TestInterruptible:
    """Verify is_interruptible() for all 8 states."""

    @pytest.mark.parametrize(
        "target",
        [State.DISPATCHING, State.COMPANIONING, State.PROGRESSING, State.CLARIFYING],
    )
    def test_is_interruptible_true(self, fsm: FSMController, target: State) -> None:
        _drive_to(fsm, target)
        assert fsm.is_interruptible() is True

    @pytest.mark.parametrize(
        "target",
        [State.LISTENING, State.ACKING, State.DELIVERING, State.INTERRUPT_HANDLING],
    )
    def test_is_interruptible_false(self, fsm: FSMController, target: State) -> None:
        _drive_to(fsm, target)
        assert fsm.is_interruptible() is False


# ---------------------------------------------------------------------------
# History tracking + reset
# ---------------------------------------------------------------------------


class TestHistoryAndReset:
    """History accumulates transitions; reset clears everything."""

    def test_history_tracking(self, fsm: FSMController) -> None:
        fsm.transition(Event.MESSAGE_RECEIVED)
        fsm.transition(Event.PHASE1_COMPLETE)
        fsm.transition(Event.DISPATCH_COMPLETE)
        assert len(fsm.history) == 3
        assert fsm.history[0] == (State.LISTENING, Event.MESSAGE_RECEIVED, State.ACKING)
        assert fsm.history[1] == (State.ACKING, Event.PHASE1_COMPLETE, State.DISPATCHING)
        assert fsm.history[2] == (State.DISPATCHING, Event.DISPATCH_COMPLETE, State.DELIVERING)

    def test_reset(self, fsm: FSMController) -> None:
        _drive_to(fsm, State.DISPATCHING)
        assert fsm.state is State.DISPATCHING
        assert len(fsm.history) > 0
        fsm.reset()
        assert fsm.state is State.LISTENING
        assert fsm.history == []

    def test_history_is_copy(self, fsm: FSMController) -> None:
        fsm.transition(Event.MESSAGE_RECEIVED)
        h = fsm.history
        h.clear()
        assert len(fsm.history) == 1  # internal list unaffected
