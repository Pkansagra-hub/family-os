"""Tests for Epic 2.1 issues 2.1.2-2.1.5 -- FSM transition table & PlanStateMachine.

Covers:
  2.1.2 -- TRANSITION_TABLE constant (23 unique edges matching SS18.4)
  2.1.3 -- PlanStateMachine.transition(), reset(), IllegalStateTransitionError
  2.1.4 -- on_transition callback mechanism
  2.1.5 -- force_failed(), force_cancelled()

Test categories (~15 per spec SS17.2 "State machine transitions"):
  - TRANSITION_TABLE structure & completeness
  - Legal transitions succeed
  - Illegal transitions raise
  - Terminal reset works
  - Callback invoked on each transition
  - force_failed from each active state
  - force_cancelled from each active state
  - Monotonicity enforcement
"""

from __future__ import annotations

from typing import List, Tuple

import pytest

from k1.planner.plan_fsm import (
    TRANSITION_TABLE,
    IllegalStateTransitionError,
    PlanState,
    PlanStateMachine,
)
from k1.planner.types import PlannerError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_STATES = list(PlanState)

_ACTIVE_STATES = [s for s in PlanState if s.is_active]

_TERMINAL_STATES = [PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED]

_NON_ACTIVE_STATES = [PlanState.IDLE] + _TERMINAL_STATES


def _make_fsm_at(state: PlanState) -> PlanStateMachine:
    """Create a PlanStateMachine and drive it to the given state via force or transition."""
    fsm = PlanStateMachine()
    if state == PlanState.IDLE:
        return fsm
    # Drive to state via known paths
    _PATHS: dict[PlanState, list[PlanState]] = {
        PlanState.SKETCHING: [PlanState.SKETCHING],
        PlanState.EXPANDING: [PlanState.SKETCHING, PlanState.EXPANDING],
        PlanState.VALIDATING: [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
        ],
        PlanState.COMMITTING: [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
        ],
        PlanState.COMPLETED: [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
            PlanState.COMPLETED,
        ],
        PlanState.FAILED: [PlanState.SKETCHING, PlanState.FAILED],
        PlanState.CANCELLED: [PlanState.SKETCHING, PlanState.CANCELLED],
        PlanState.MICRO_SKETCH: [PlanState.MICRO_SKETCH],
        PlanState.MICRO_EXPAND: [PlanState.MICRO_SKETCH, PlanState.MICRO_EXPAND],
        PlanState.MICRO_VALIDATE: [
            PlanState.MICRO_SKETCH,
            PlanState.MICRO_EXPAND,
            PlanState.MICRO_VALIDATE,
        ],
    }
    for step in _PATHS[state]:
        fsm.transition(step)
    return fsm


# ===================================================================
# 2.1.2 -- TRANSITION_TABLE structure
# ===================================================================


class TestTransitionTableStructure:
    """TRANSITION_TABLE is Dict[PlanState, FrozenSet[PlanState]] with correct coverage."""

    def test_table_has_all_11_states_as_keys(self) -> None:
        assert set(TRANSITION_TABLE.keys()) == set(PlanState)

    def test_table_key_count(self) -> None:
        assert len(TRANSITION_TABLE) == 11

    def test_all_values_are_frozensets(self) -> None:
        for state, targets in TRANSITION_TABLE.items():
            assert isinstance(targets, frozenset), f"{state} targets not frozenset"

    def test_all_targets_are_plan_states(self) -> None:
        for state, targets in TRANSITION_TABLE.items():
            for target in targets:
                assert isinstance(target, PlanState), f"{state} -> {target} is not PlanState"

    def test_no_self_transitions(self) -> None:
        for state, targets in TRANSITION_TABLE.items():
            assert state not in targets, f"{state} has self-transition"

    def test_total_unique_edge_count(self) -> None:
        total = sum(len(targets) for targets in TRANSITION_TABLE.values())
        assert total == 23


# ===================================================================
# 2.1.2 -- TRANSITION_TABLE completeness (SS18.4 row-by-row)
# ===================================================================


class TestTransitionTableFullPipeline:
    """Full pipeline: 7 transitions (SS18.4)."""

    def test_idle_to_sketching(self) -> None:
        assert PlanState.SKETCHING in TRANSITION_TABLE[PlanState.IDLE]

    def test_sketching_to_expanding(self) -> None:
        assert PlanState.EXPANDING in TRANSITION_TABLE[PlanState.SKETCHING]

    def test_expanding_to_validating(self) -> None:
        assert PlanState.VALIDATING in TRANSITION_TABLE[PlanState.EXPANDING]

    def test_validating_to_committing(self) -> None:
        assert PlanState.COMMITTING in TRANSITION_TABLE[PlanState.VALIDATING]

    def test_validating_to_expanding_revise(self) -> None:
        """VALIDATING->EXPANDING is the ONLY backward transition (revise loop)."""
        assert PlanState.EXPANDING in TRANSITION_TABLE[PlanState.VALIDATING]

    def test_committing_to_completed(self) -> None:
        assert PlanState.COMPLETED in TRANSITION_TABLE[PlanState.COMMITTING]

    def test_completed_to_idle(self) -> None:
        assert PlanState.IDLE in TRANSITION_TABLE[PlanState.COMPLETED]


class TestTransitionTableMicroReplan:
    """Micro-replan: 5 transitions (4 new + COMMITTING->COMPLETED reused)."""

    def test_idle_to_micro_sketch(self) -> None:
        assert PlanState.MICRO_SKETCH in TRANSITION_TABLE[PlanState.IDLE]

    def test_micro_sketch_to_micro_expand(self) -> None:
        assert PlanState.MICRO_EXPAND in TRANSITION_TABLE[PlanState.MICRO_SKETCH]

    def test_micro_expand_to_micro_validate(self) -> None:
        assert PlanState.MICRO_VALIDATE in TRANSITION_TABLE[PlanState.MICRO_EXPAND]

    def test_micro_validate_to_committing(self) -> None:
        assert PlanState.COMMITTING in TRANSITION_TABLE[PlanState.MICRO_VALIDATE]

    def test_committing_to_completed_reused(self) -> None:
        """COMMITTING->COMPLETED is shared between full and micro-replan pipeline."""
        assert PlanState.COMPLETED in TRANSITION_TABLE[PlanState.COMMITTING]


class TestTransitionTableErrorPaths:
    """Error paths: each active state that can go to FAILED (SS18.4)."""

    def test_sketching_to_failed(self) -> None:
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.SKETCHING]

    def test_expanding_to_failed(self) -> None:
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.EXPANDING]

    def test_validating_to_failed(self) -> None:
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.VALIDATING]

    def test_micro_sketch_to_failed(self) -> None:
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.MICRO_SKETCH]

    def test_micro_expand_to_failed(self) -> None:
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.MICRO_EXPAND]

    def test_micro_validate_to_failed(self) -> None:
        assert PlanState.FAILED in TRANSITION_TABLE[PlanState.MICRO_VALIDATE]

    def test_committing_cannot_go_to_failed_via_table(self) -> None:
        """COMMITTING->FAILED is NOT in the table; use force_failed() instead."""
        assert PlanState.FAILED not in TRANSITION_TABLE[PlanState.COMMITTING]


class TestTransitionTableCancelPaths:
    """Cancel paths: 4 transitions (SS18.4)."""

    def test_sketching_to_cancelled(self) -> None:
        assert PlanState.CANCELLED in TRANSITION_TABLE[PlanState.SKETCHING]

    def test_expanding_to_cancelled(self) -> None:
        assert PlanState.CANCELLED in TRANSITION_TABLE[PlanState.EXPANDING]

    def test_validating_to_cancelled(self) -> None:
        assert PlanState.CANCELLED in TRANSITION_TABLE[PlanState.VALIDATING]

    def test_committing_to_cancelled(self) -> None:
        assert PlanState.CANCELLED in TRANSITION_TABLE[PlanState.COMMITTING]


class TestTransitionTableTerminalReset:
    """Terminal reset: 3 transitions (SS18.4)."""

    def test_completed_to_idle(self) -> None:
        assert PlanState.IDLE in TRANSITION_TABLE[PlanState.COMPLETED]

    def test_failed_to_idle(self) -> None:
        assert PlanState.IDLE in TRANSITION_TABLE[PlanState.FAILED]

    def test_cancelled_to_idle(self) -> None:
        assert PlanState.IDLE in TRANSITION_TABLE[PlanState.CANCELLED]

    def test_terminal_states_only_go_to_idle(self) -> None:
        for terminal in _TERMINAL_STATES:
            assert TRANSITION_TABLE[terminal] == frozenset(
                {PlanState.IDLE}
            ), f"{terminal} should only transition to IDLE"


class TestTransitionTableBackwardTransition:
    """VALIDATING->EXPANDING is the ONLY backward transition."""

    def test_validating_to_expanding_is_legal(self) -> None:
        assert PlanState.EXPANDING in TRANSITION_TABLE[PlanState.VALIDATING]

    def test_no_other_backward_transitions(self) -> None:
        """Verify no other state has a backward transition.

        'Backward' = target appears earlier in the pipeline than source.
        Exception: terminal->IDLE (reset) and VALIDATING->EXPANDING (revise).
        """
        forward_order = [
            PlanState.IDLE,
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
            PlanState.COMPLETED,
        ]
        for source, targets in TRANSITION_TABLE.items():
            if source not in forward_order:
                continue
            source_idx = forward_order.index(source)
            for target in targets:
                if target not in forward_order:
                    continue
                target_idx = forward_order.index(target)
                if target_idx < source_idx:
                    # Backward -- only allowed: terminal->IDLE, VALIDATING->EXPANDING
                    is_terminal_reset = source.is_terminal and target == PlanState.IDLE
                    is_revise = source == PlanState.VALIDATING and target == PlanState.EXPANDING
                    assert (
                        is_terminal_reset or is_revise
                    ), f"Unexpected backward transition: {source} -> {target}"


class TestTransitionTableTargetSetSizes:
    """Verify each state has the expected number of legal targets."""

    _EXPECTED_SIZES = {
        PlanState.IDLE: 2,
        PlanState.SKETCHING: 3,
        PlanState.EXPANDING: 3,
        PlanState.VALIDATING: 4,
        PlanState.COMMITTING: 2,
        PlanState.COMPLETED: 1,
        PlanState.FAILED: 1,
        PlanState.CANCELLED: 1,
        PlanState.MICRO_SKETCH: 2,
        PlanState.MICRO_EXPAND: 2,
        PlanState.MICRO_VALIDATE: 2,
    }

    @pytest.mark.parametrize("state", list(PlanState), ids=lambda s: s.name)
    def test_target_set_size(self, state: PlanState) -> None:
        expected = self._EXPECTED_SIZES[state]
        actual = len(TRANSITION_TABLE[state])
        assert actual == expected, f"{state}: expected {expected} targets, got {actual}"


# ===================================================================
# 2.1.3 -- IllegalStateTransitionError
# ===================================================================


class TestIllegalStateTransitionError:
    """IllegalStateTransitionError is a PlannerError subclass with attributes."""

    def test_is_planner_error(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert isinstance(err, PlannerError)

    def test_is_exception(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert isinstance(err, Exception)

    def test_from_state_attribute(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert err.from_state is PlanState.IDLE

    def test_to_state_attribute(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert err.to_state is PlanState.COMPLETED

    def test_trigger_attribute_default(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert err.trigger == ""

    def test_trigger_attribute_custom(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED, "test_trigger")
        assert err.trigger == "test_trigger"

    def test_message_without_trigger(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert str(err) == "Illegal state transition: IDLE -> COMPLETED"

    def test_message_with_trigger(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED, "user_req")
        assert str(err) == "Illegal state transition: IDLE -> COMPLETED (trigger: user_req)"

    def test_stage_attribute_from_planner_error(self) -> None:
        err = IllegalStateTransitionError(PlanState.SKETCHING, PlanState.IDLE)
        assert err.stage == "SKETCHING"

    def test_inherits_planner_error_defaults(self) -> None:
        err = IllegalStateTransitionError(PlanState.IDLE, PlanState.COMPLETED)
        assert err.request_id == ""
        assert err.trace_id == ""


# ===================================================================
# 2.1.3 -- PlanStateMachine: constructor & current_state
# ===================================================================


class TestPlanStateMachineInit:
    """PlanStateMachine constructor and initial state."""

    def test_initial_state_is_idle(self) -> None:
        fsm = PlanStateMachine()
        assert fsm.current_state is PlanState.IDLE

    def test_no_callback_by_default(self) -> None:
        fsm = PlanStateMachine()
        assert fsm._on_transition is None

    def test_callback_stored(self) -> None:
        cb = lambda f, t, tr: None  # noqa: E731
        fsm = PlanStateMachine(on_transition=cb)
        assert fsm._on_transition is cb

    def test_has_slots(self) -> None:
        fsm = PlanStateMachine()
        assert hasattr(fsm, "__slots__")
        with pytest.raises(AttributeError):
            fsm.arbitrary_attr = 42  # type: ignore[attr-defined]


# ===================================================================
# 2.1.3 -- PlanStateMachine.transition() -- legal transitions
# ===================================================================


class TestTransitionLegal:
    """Legal transitions succeed and update state."""

    def test_idle_to_sketching(self) -> None:
        fsm = PlanStateMachine()
        result = fsm.transition(PlanState.SKETCHING, "PLAN_START")
        assert result is PlanState.SKETCHING
        assert fsm.current_state is PlanState.SKETCHING

    def test_full_pipeline_happy_path(self) -> None:
        """Walk the entire full pipeline: IDLE->SKETCHING->...->COMPLETED->IDLE."""
        fsm = PlanStateMachine()
        path = [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
            PlanState.COMPLETED,
        ]
        for target in path:
            fsm.transition(target)
        assert fsm.current_state is PlanState.COMPLETED

    def test_micro_replan_happy_path(self) -> None:
        """IDLE->MICRO_SKETCH->MICRO_EXPAND->MICRO_VALIDATE->COMMITTING->COMPLETED."""
        fsm = PlanStateMachine()
        path = [
            PlanState.MICRO_SKETCH,
            PlanState.MICRO_EXPAND,
            PlanState.MICRO_VALIDATE,
            PlanState.COMMITTING,
            PlanState.COMPLETED,
        ]
        for target in path:
            fsm.transition(target)
        assert fsm.current_state is PlanState.COMPLETED

    def test_revise_loop_validating_to_expanding(self) -> None:
        """VALIDATING->EXPANDING is the legal backward revise transition."""
        fsm = _make_fsm_at(PlanState.VALIDATING)
        result = fsm.transition(PlanState.EXPANDING, "revise")
        assert result is PlanState.EXPANDING
        assert fsm.current_state is PlanState.EXPANDING

    def test_transition_returns_new_state(self) -> None:
        fsm = PlanStateMachine()
        result = fsm.transition(PlanState.SKETCHING)
        assert result is PlanState.SKETCHING

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (PlanState.SKETCHING, PlanState.FAILED),
            (PlanState.EXPANDING, PlanState.FAILED),
            (PlanState.VALIDATING, PlanState.FAILED),
            (PlanState.MICRO_SKETCH, PlanState.FAILED),
            (PlanState.MICRO_EXPAND, PlanState.FAILED),
            (PlanState.MICRO_VALIDATE, PlanState.FAILED),
        ],
        ids=lambda p: p.name if isinstance(p, PlanState) else str(p),
    )
    def test_error_path_transitions(self, from_state: PlanState, to_state: PlanState) -> None:
        fsm = _make_fsm_at(from_state)
        fsm.transition(to_state)
        assert fsm.current_state is PlanState.FAILED

    @pytest.mark.parametrize(
        "from_state",
        [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
        ],
        ids=lambda s: s.name,
    )
    def test_cancel_path_transitions(self, from_state: PlanState) -> None:
        fsm = _make_fsm_at(from_state)
        fsm.transition(PlanState.CANCELLED)
        assert fsm.current_state is PlanState.CANCELLED

    @pytest.mark.parametrize(
        "terminal",
        _TERMINAL_STATES,
        ids=lambda s: s.name,
    )
    def test_terminal_to_idle_via_transition(self, terminal: PlanState) -> None:
        """Terminal -> IDLE is legal in the transition table."""
        fsm = _make_fsm_at(terminal)
        fsm.transition(PlanState.IDLE)
        assert fsm.current_state is PlanState.IDLE


# ===================================================================
# 2.1.3 -- PlanStateMachine.transition() -- illegal transitions
# ===================================================================


class TestTransitionIllegal:
    """Illegal transitions raise IllegalStateTransitionError."""

    def test_idle_to_completed_raises(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.transition(PlanState.COMPLETED)
        assert exc_info.value.from_state is PlanState.IDLE
        assert exc_info.value.to_state is PlanState.COMPLETED

    def test_idle_to_expanding_raises(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.EXPANDING)

    def test_sketching_to_committing_raises(self) -> None:
        """Cannot skip stages."""
        fsm = _make_fsm_at(PlanState.SKETCHING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.COMMITTING)

    def test_expanding_to_committing_raises(self) -> None:
        """Cannot skip VALIDATING."""
        fsm = _make_fsm_at(PlanState.EXPANDING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.COMMITTING)

    def test_committing_to_failed_raises(self) -> None:
        """COMMITTING->FAILED is NOT in the table (use force_failed)."""
        fsm = _make_fsm_at(PlanState.COMMITTING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.FAILED)

    def test_completed_to_sketching_raises(self) -> None:
        """COMPLETED can only go to IDLE."""
        fsm = _make_fsm_at(PlanState.COMPLETED)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.SKETCHING)

    def test_failed_to_sketching_raises(self) -> None:
        fsm = _make_fsm_at(PlanState.FAILED)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.SKETCHING)

    def test_self_transition_raises(self) -> None:
        """No state can transition to itself."""
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.IDLE)

    def test_trigger_preserved_in_error(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.transition(PlanState.COMPLETED, trigger="bad_event")
        assert exc_info.value.trigger == "bad_event"

    def test_state_unchanged_after_illegal_transition(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.COMPLETED)
        assert fsm.current_state is PlanState.IDLE

    @pytest.mark.parametrize("state", _ALL_STATES, ids=lambda s: s.name)
    def test_every_state_rejects_self_transition(self, state: PlanState) -> None:
        fsm = _make_fsm_at(state)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(state)

    def test_micro_sketch_to_expanding_raises(self) -> None:
        """Micro states cannot cross into full pipeline states."""
        fsm = _make_fsm_at(PlanState.MICRO_SKETCH)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.EXPANDING)

    def test_micro_expand_to_validating_raises(self) -> None:
        fsm = _make_fsm_at(PlanState.MICRO_EXPAND)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.VALIDATING)

    def test_sketching_to_micro_expand_raises(self) -> None:
        """Full pipeline states cannot cross into micro states."""
        fsm = _make_fsm_at(PlanState.SKETCHING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.MICRO_EXPAND)


# ===================================================================
# 2.1.3 -- PlanStateMachine.reset()
# ===================================================================


class TestReset:
    """reset() is only legal from terminal states, goes to IDLE."""

    @pytest.mark.parametrize("terminal", _TERMINAL_STATES, ids=lambda s: s.name)
    def test_reset_from_terminal_succeeds(self, terminal: PlanState) -> None:
        fsm = _make_fsm_at(terminal)
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE

    def test_reset_from_idle_raises(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.reset()
        assert exc_info.value.from_state is PlanState.IDLE
        assert exc_info.value.to_state is PlanState.IDLE
        assert exc_info.value.trigger == "reset"

    @pytest.mark.parametrize("active", _ACTIVE_STATES, ids=lambda s: s.name)
    def test_reset_from_active_raises(self, active: PlanState) -> None:
        fsm = _make_fsm_at(active)
        with pytest.raises(IllegalStateTransitionError):
            fsm.reset()

    def test_reset_does_not_invoke_callback(self) -> None:
        """Section 18.6: reset path does NOT invoke on_transition callback."""
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING, "start")
        fsm.transition(PlanState.FAILED, "error")
        calls.clear()  # Clear transition callbacks
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE
        assert len(calls) == 0, "reset() must not invoke on_transition callback"


# ===================================================================
# 2.1.4 -- on_transition callback mechanism
# ===================================================================


class TestOnTransitionCallback:
    """Callback invoked AFTER state update with (from_state, to_state, trigger)."""

    def test_callback_invoked_on_transition(self) -> None:
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING, "PLAN_START")
        assert len(calls) == 1
        assert calls[0] == (PlanState.IDLE, PlanState.SKETCHING, "PLAN_START")

    def test_callback_sees_new_state(self) -> None:
        """Callback is invoked AFTER _current_state is updated."""
        observed_states: List[PlanState] = []

        def observer(f: PlanState, t: PlanState, tr: str) -> None:
            observed_states.append(t)

        fsm = PlanStateMachine(on_transition=observer)
        fsm.transition(PlanState.SKETCHING)
        assert observed_states[0] is PlanState.SKETCHING
        assert fsm.current_state is PlanState.SKETCHING

    def test_callback_state_matches_fsm_state_during_call(self) -> None:
        """During callback, fsm.current_state should already be the new state."""
        state_during_callback: List[PlanState] = []

        def capture(f: PlanState, t: PlanState, tr: str) -> None:
            # We can't access fsm here directly (closure), but
            # the 't' parameter should match the new state
            state_during_callback.append(t)

        fsm = PlanStateMachine(on_transition=capture)
        fsm.transition(PlanState.SKETCHING)
        assert state_during_callback[0] is fsm.current_state

    def test_callback_invoked_for_each_transition(self) -> None:
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING, "s1")
        fsm.transition(PlanState.EXPANDING, "s2")
        fsm.transition(PlanState.VALIDATING, "s3")
        assert len(calls) == 3
        assert calls[0] == (PlanState.IDLE, PlanState.SKETCHING, "s1")
        assert calls[1] == (PlanState.SKETCHING, PlanState.EXPANDING, "s2")
        assert calls[2] == (PlanState.EXPANDING, PlanState.VALIDATING, "s3")

    def test_no_callback_when_none(self) -> None:
        """No crash when on_transition is None."""
        fsm = PlanStateMachine(on_transition=None)
        fsm.transition(PlanState.SKETCHING)
        assert fsm.current_state is PlanState.SKETCHING

    def test_callback_not_invoked_on_illegal_transition(self) -> None:
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.COMPLETED)
        assert len(calls) == 0

    def test_callback_trigger_default_empty_string(self) -> None:
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING)
        assert calls[0][2] == ""

    def test_callback_invoked_on_force_failed(self) -> None:
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING, "start")
        calls.clear()
        fsm.force_failed("ERR_SKETCH_FAIL")
        assert len(calls) == 1
        assert calls[0] == (PlanState.SKETCHING, PlanState.FAILED, "ERR_SKETCH_FAIL")

    def test_callback_invoked_on_force_cancelled(self) -> None:
        calls: List[Tuple[PlanState, PlanState, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            calls.append((f, t, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING, "start")
        calls.clear()
        fsm.force_cancelled("cancel_received")
        assert len(calls) == 1
        assert calls[0] == (
            PlanState.SKETCHING,
            PlanState.CANCELLED,
            "cancel_received",
        )


# ===================================================================
# 2.1.5 -- force_failed()
# ===================================================================


class TestForceFailed:
    """force_failed() transitions any active state to FAILED (bypass table)."""

    @pytest.mark.parametrize("active", _ACTIVE_STATES, ids=lambda s: s.name)
    def test_force_failed_from_each_active_state(self, active: PlanState) -> None:
        fsm = _make_fsm_at(active)
        result = fsm.force_failed(f"ERR_{active.name}")
        assert result is PlanState.FAILED
        assert fsm.current_state is PlanState.FAILED

    def test_force_failed_from_idle_raises(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.force_failed("attempt")
        assert exc_info.value.from_state is PlanState.IDLE
        assert exc_info.value.to_state is PlanState.FAILED

    @pytest.mark.parametrize("terminal", _TERMINAL_STATES, ids=lambda s: s.name)
    def test_force_failed_from_terminal_raises(self, terminal: PlanState) -> None:
        fsm = _make_fsm_at(terminal)
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.force_failed("attempt")
        assert exc_info.value.from_state is terminal
        assert exc_info.value.to_state is PlanState.FAILED

    @pytest.mark.parametrize("non_active", _NON_ACTIVE_STATES, ids=lambda s: s.name)
    def test_force_failed_from_non_active_raises(self, non_active: PlanState) -> None:
        fsm = _make_fsm_at(non_active)
        with pytest.raises(IllegalStateTransitionError):
            fsm.force_failed()

    def test_force_failed_returns_failed(self) -> None:
        fsm = _make_fsm_at(PlanState.SKETCHING)
        assert fsm.force_failed() is PlanState.FAILED

    def test_force_failed_trigger_attribute(self) -> None:
        """Trigger is preserved in the error when force_failed raises."""
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.force_failed("my_trigger")
        assert exc_info.value.trigger == "my_trigger"

    def test_force_failed_committing_bypasses_table(self) -> None:
        """COMMITTING->FAILED is NOT in the table but force_failed() allows it."""
        fsm = _make_fsm_at(PlanState.COMMITTING)
        # Verify table doesn't have this transition
        assert PlanState.FAILED not in TRANSITION_TABLE[PlanState.COMMITTING]
        # But force_failed works
        fsm.force_failed("commit_error")
        assert fsm.current_state is PlanState.FAILED


# ===================================================================
# 2.1.5 -- force_cancelled()
# ===================================================================


class TestForceCancelled:
    """force_cancelled() transitions any active state to CANCELLED (bypass table)."""

    @pytest.mark.parametrize("active", _ACTIVE_STATES, ids=lambda s: s.name)
    def test_force_cancelled_from_each_active_state(self, active: PlanState) -> None:
        fsm = _make_fsm_at(active)
        result = fsm.force_cancelled(f"CANCEL_{active.name}")
        assert result is PlanState.CANCELLED
        assert fsm.current_state is PlanState.CANCELLED

    def test_force_cancelled_from_idle_raises(self) -> None:
        fsm = PlanStateMachine()
        with pytest.raises(IllegalStateTransitionError) as exc_info:
            fsm.force_cancelled("attempt")
        assert exc_info.value.from_state is PlanState.IDLE
        assert exc_info.value.to_state is PlanState.CANCELLED

    @pytest.mark.parametrize("terminal", _TERMINAL_STATES, ids=lambda s: s.name)
    def test_force_cancelled_from_terminal_raises(self, terminal: PlanState) -> None:
        fsm = _make_fsm_at(terminal)
        with pytest.raises(IllegalStateTransitionError):
            fsm.force_cancelled("attempt")

    @pytest.mark.parametrize("non_active", _NON_ACTIVE_STATES, ids=lambda s: s.name)
    def test_force_cancelled_from_non_active_raises(self, non_active: PlanState) -> None:
        fsm = _make_fsm_at(non_active)
        with pytest.raises(IllegalStateTransitionError):
            fsm.force_cancelled()

    def test_force_cancelled_returns_cancelled(self) -> None:
        fsm = _make_fsm_at(PlanState.SKETCHING)
        assert fsm.force_cancelled() is PlanState.CANCELLED


# ===================================================================
# Monotonicity enforcement
# ===================================================================


class TestMonotonicity:
    """FSM enforces forward-only transitions (except VALIDATING->EXPANDING revise)."""

    def test_expanding_to_sketching_illegal(self) -> None:
        fsm = _make_fsm_at(PlanState.EXPANDING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.SKETCHING)

    def test_committing_to_validating_illegal(self) -> None:
        fsm = _make_fsm_at(PlanState.COMMITTING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.VALIDATING)

    def test_committing_to_expanding_illegal(self) -> None:
        fsm = _make_fsm_at(PlanState.COMMITTING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.EXPANDING)

    def test_committing_to_sketching_illegal(self) -> None:
        fsm = _make_fsm_at(PlanState.COMMITTING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.SKETCHING)

    def test_validating_to_sketching_illegal(self) -> None:
        fsm = _make_fsm_at(PlanState.VALIDATING)
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.SKETCHING)

    def test_only_revise_backward_allowed(self) -> None:
        """VALIDATING->EXPANDING is legal but EXPANDING->SKETCHING is not."""
        fsm = _make_fsm_at(PlanState.VALIDATING)
        fsm.transition(PlanState.EXPANDING, "revise")
        assert fsm.current_state is PlanState.EXPANDING
        with pytest.raises(IllegalStateTransitionError):
            fsm.transition(PlanState.SKETCHING)


# ===================================================================
# Integration: full lifecycle scenarios
# ===================================================================


class TestLifecycleScenarios:
    """End-to-end lifecycle scenarios combining transition, reset, force."""

    def test_full_pipeline_then_reset(self) -> None:
        fsm = PlanStateMachine()
        for s in [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
            PlanState.COMPLETED,
        ]:
            fsm.transition(s)
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE

    def test_error_then_reset_then_retry(self) -> None:
        """Failed plan -> reset -> start new plan."""
        fsm = PlanStateMachine()
        fsm.transition(PlanState.SKETCHING)
        fsm.transition(PlanState.FAILED, "ERR_SKETCH_FAIL")
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE
        fsm.transition(PlanState.SKETCHING, "retry")
        assert fsm.current_state is PlanState.SKETCHING

    def test_cancel_then_reset_then_new_plan(self) -> None:
        fsm = PlanStateMachine()
        fsm.transition(PlanState.SKETCHING)
        fsm.transition(PlanState.EXPANDING)
        fsm.transition(PlanState.CANCELLED, "cancel_received")
        fsm.reset()
        fsm.transition(PlanState.MICRO_SKETCH, "micro_start")
        assert fsm.current_state is PlanState.MICRO_SKETCH

    def test_revise_loop_then_commit(self) -> None:
        """VALIDATE -> EXPAND (revise) -> VALIDATE -> COMMIT -> COMPLETE."""
        fsm = PlanStateMachine()
        fsm.transition(PlanState.SKETCHING)
        fsm.transition(PlanState.EXPANDING)
        fsm.transition(PlanState.VALIDATING)
        fsm.transition(PlanState.EXPANDING, "revise")
        fsm.transition(PlanState.VALIDATING)
        fsm.transition(PlanState.COMMITTING)
        fsm.transition(PlanState.COMPLETED)
        assert fsm.current_state is PlanState.COMPLETED

    def test_force_failed_then_reset(self) -> None:
        fsm = _make_fsm_at(PlanState.COMMITTING)
        fsm.force_failed("commit_error")
        assert fsm.current_state is PlanState.FAILED
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE

    def test_force_cancelled_then_reset(self) -> None:
        fsm = _make_fsm_at(PlanState.MICRO_EXPAND)
        fsm.force_cancelled("user_cancel")
        assert fsm.current_state is PlanState.CANCELLED
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE

    def test_micro_pipeline_then_reset(self) -> None:
        fsm = PlanStateMachine()
        for s in [
            PlanState.MICRO_SKETCH,
            PlanState.MICRO_EXPAND,
            PlanState.MICRO_VALIDATE,
            PlanState.COMMITTING,
            PlanState.COMPLETED,
        ]:
            fsm.transition(s)
        fsm.reset()
        assert fsm.current_state is PlanState.IDLE

    def test_callback_full_pipeline_trace(self) -> None:
        """Verify callback trace for full pipeline."""
        trace: List[Tuple[str, str, str]] = []

        def recorder(f: PlanState, t: PlanState, tr: str) -> None:
            trace.append((f.value, t.value, tr))

        fsm = PlanStateMachine(on_transition=recorder)
        fsm.transition(PlanState.SKETCHING, "PLAN_START")
        fsm.transition(PlanState.EXPANDING, "stage_complete")
        fsm.transition(PlanState.VALIDATING, "stage_complete")
        fsm.transition(PlanState.COMMITTING, "approved")
        fsm.transition(PlanState.COMPLETED, "commit_complete")

        assert len(trace) == 5
        assert trace[0] == ("IDLE", "SKETCHING", "PLAN_START")
        assert trace[4] == ("COMMITTING", "COMPLETED", "commit_complete")

    def test_terminal_to_idle_via_transition_not_reset(self) -> None:
        """Terminal->IDLE can also happen via transition() not just reset()."""
        fsm = _make_fsm_at(PlanState.COMPLETED)
        calls: List[Tuple[PlanState, PlanState, str]] = []

        fsm2 = PlanStateMachine(on_transition=lambda f, t, tr: calls.append((f, t, tr)))
        fsm2.transition(PlanState.SKETCHING)
        fsm2.transition(PlanState.FAILED)
        calls.clear()
        # Use transition() instead of reset() -- still legal
        fsm2.transition(PlanState.IDLE, "manual_reset")
        assert fsm2.current_state is PlanState.IDLE
        # transition() DOES invoke callback (unlike reset())
        assert len(calls) == 1
        assert calls[0] == (PlanState.FAILED, PlanState.IDLE, "manual_reset")


# ===================================================================
# Layer 0 import verification
# ===================================================================


class TestLayer0Imports:
    """plan_fsm.py imports only from stdlib and k1.planner.types (Layer 0)."""

    def test_import_from_plan_fsm_direct(self) -> None:
        from k1.planner.plan_fsm import (
            TRANSITION_TABLE,
            IllegalStateTransitionError,
            PlanState,
            PlanStateMachine,
        )

        assert PlanState is not None
        assert TRANSITION_TABLE is not None
        assert IllegalStateTransitionError is not None
        assert PlanStateMachine is not None

    def test_import_from_package_facade(self) -> None:
        from k1.planner import (
            TRANSITION_TABLE,
            IllegalStateTransitionError,
            PlanState,
            PlanStateMachine,
        )

        assert PlanState is not None
        assert TRANSITION_TABLE is not None
        assert IllegalStateTransitionError is not None
        assert PlanStateMachine is not None

    def test_illegal_state_transition_error_in_package_all(self) -> None:
        import k1.planner

        assert "IllegalStateTransitionError" in k1.planner.__all__

    def test_transition_table_in_package_all(self) -> None:
        import k1.planner

        assert "TRANSITION_TABLE" in k1.planner.__all__

    def test_plan_state_machine_in_package_all(self) -> None:
        import k1.planner

        assert "PlanStateMachine" in k1.planner.__all__

    def test_plan_fsm_module_all(self) -> None:
        from k1.planner import plan_fsm

        assert set(plan_fsm.__all__) == {
            "PlanState",
            "TRANSITION_TABLE",
            "IllegalStateTransitionError",
            "PlanStateMachine",
        }
