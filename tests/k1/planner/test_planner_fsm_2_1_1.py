"""Tests for Epic 2.1 issue 2.1.1 -- PlanState enum (10+1 states).

Coverage:
- PlanState is (str, Enum) with exactly 11 members (SS18.1)
- Exact member values match SS18.1 state catalog
- Member ordering matches declaration order
- is_terminal property: COMPLETED, FAILED, CANCELLED -> True; all others -> False
- is_micro property: MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE -> True; all others -> False
- is_active property: all non-IDLE, non-terminal -> True; IDLE + terminals -> False
- string-enum compatibility (== string, .value, JSON serialisation)
- Pre-computed frozensets _TERMINAL_STATES, _MICRO_STATES
- Layer 0: imports only from stdlib (no internal deps)
- __all__ export, importable from package __init__

Validates against planner.md SS18.1, SS18.4, SS30.5.1 F04.
"""

from __future__ import annotations

import enum
import json

import pytest

# ===================================================================
# 2.1.1a -- PlanState enum membership
# ===================================================================


class TestPlanStateEnumMembership:
    """PlanState has exactly 11 members matching SS18.1 State Catalog."""

    def test_exactly_11_members(self):
        """SS18.1 lists 5 transient + 3 micro + 3 terminal = 11 states."""
        from k1.planner.plan_fsm import PlanState

        assert len(PlanState) == 11

    def test_is_str_enum(self):
        """PlanState(str, Enum) for JSON serialisation compatibility."""
        from k1.planner.plan_fsm import PlanState

        assert issubclass(PlanState, str)
        assert issubclass(PlanState, enum.Enum)

    def test_all_member_names(self):
        """Every member from SS18.1 is present."""
        from k1.planner.plan_fsm import PlanState

        expected = {
            "IDLE",
            "SKETCHING",
            "EXPANDING",
            "VALIDATING",
            "COMMITTING",
            "MICRO_SKETCH",
            "MICRO_EXPAND",
            "MICRO_VALIDATE",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
        }
        actual = {s.name for s in PlanState}
        assert actual == expected

    def test_member_values_equal_names(self):
        """Each member's value equals its name (e.g., PlanState.IDLE.value == 'IDLE')."""
        from k1.planner.plan_fsm import PlanState

        for state in PlanState:
            assert state.value == state.name, f"{state.name} value mismatch"

    def test_member_ordering(self):
        """Declaration order: transient, micro, terminal -- per SS18.1."""
        from k1.planner.plan_fsm import PlanState

        ordered = [s.value for s in PlanState]
        assert ordered == [
            "IDLE",
            "SKETCHING",
            "EXPANDING",
            "VALIDATING",
            "COMMITTING",
            "MICRO_SKETCH",
            "MICRO_EXPAND",
            "MICRO_VALIDATE",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
        ]


# ===================================================================
# 2.1.1b -- PlanState string-enum compatibility
# ===================================================================


class TestPlanStateStringCompatibility:
    """PlanState(str, Enum) enables direct string comparison and JSON."""

    def test_equality_with_plain_string(self):
        from k1.planner.plan_fsm import PlanState

        assert PlanState.SKETCHING == "SKETCHING"
        assert PlanState.IDLE == "IDLE"
        assert PlanState.FAILED == "FAILED"

    def test_string_operations(self):
        """Can use str methods on PlanState members."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.MICRO_SKETCH.startswith("MICRO_")
        assert PlanState.COMMITTING.lower() == "committing"

    def test_json_serialisable(self):
        """PlanState values serialise to JSON without custom encoder."""
        from k1.planner.plan_fsm import PlanState

        data = {"state": PlanState.EXPANDING}
        dumped = json.dumps(data)
        parsed = json.loads(dumped)
        assert parsed["state"] == "EXPANDING"

    def test_construct_from_string(self):
        """Can construct PlanState from a string value."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState("VALIDATING") is PlanState.VALIDATING
        assert PlanState("MICRO_EXPAND") is PlanState.MICRO_EXPAND

    def test_invalid_string_raises_valueerror(self):
        from k1.planner.plan_fsm import PlanState

        with pytest.raises(ValueError):
            PlanState("NONEXISTENT")

    def test_hashable(self):
        """PlanState can be used as dict key / set member."""
        from k1.planner.plan_fsm import PlanState

        d = {PlanState.IDLE: "resting", PlanState.FAILED: "error"}
        assert d[PlanState.IDLE] == "resting"


# ===================================================================
# 2.1.1c -- is_terminal property
# ===================================================================


class TestPlanStateIsTerminal:
    """is_terminal: COMPLETED, FAILED, CANCELLED -> True; all others -> False."""

    @pytest.mark.parametrize(
        "state_name",
        ["COMPLETED", "FAILED", "CANCELLED"],
    )
    def test_terminal_states_are_terminal(self, state_name: str):
        from k1.planner.plan_fsm import PlanState

        assert PlanState(state_name).is_terminal is True

    @pytest.mark.parametrize(
        "state_name",
        [
            "IDLE",
            "SKETCHING",
            "EXPANDING",
            "VALIDATING",
            "COMMITTING",
            "MICRO_SKETCH",
            "MICRO_EXPAND",
            "MICRO_VALIDATE",
        ],
    )
    def test_non_terminal_states_are_not_terminal(self, state_name: str):
        from k1.planner.plan_fsm import PlanState

        assert PlanState(state_name).is_terminal is False

    def test_exactly_three_terminal_states(self):
        from k1.planner.plan_fsm import PlanState

        terminals = [s for s in PlanState if s.is_terminal]
        assert len(terminals) == 3


# ===================================================================
# 2.1.1d -- is_micro property
# ===================================================================


class TestPlanStateIsMicro:
    """is_micro: MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE -> True; others -> False."""

    @pytest.mark.parametrize(
        "state_name",
        ["MICRO_SKETCH", "MICRO_EXPAND", "MICRO_VALIDATE"],
    )
    def test_micro_states_are_micro(self, state_name: str):
        from k1.planner.plan_fsm import PlanState

        assert PlanState(state_name).is_micro is True

    @pytest.mark.parametrize(
        "state_name",
        [
            "IDLE",
            "SKETCHING",
            "EXPANDING",
            "VALIDATING",
            "COMMITTING",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
        ],
    )
    def test_non_micro_states_are_not_micro(self, state_name: str):
        from k1.planner.plan_fsm import PlanState

        assert PlanState(state_name).is_micro is False

    def test_exactly_three_micro_states(self):
        from k1.planner.plan_fsm import PlanState

        micros = [s for s in PlanState if s.is_micro]
        assert len(micros) == 3


# ===================================================================
# 2.1.1e -- is_active property
# ===================================================================


class TestPlanStateIsActive:
    """is_active: True for all states except IDLE and terminal states."""

    @pytest.mark.parametrize(
        "state_name",
        [
            "SKETCHING",
            "EXPANDING",
            "VALIDATING",
            "COMMITTING",
            "MICRO_SKETCH",
            "MICRO_EXPAND",
            "MICRO_VALIDATE",
        ],
    )
    def test_active_states(self, state_name: str):
        from k1.planner.plan_fsm import PlanState

        assert PlanState(state_name).is_active is True

    @pytest.mark.parametrize(
        "state_name",
        ["IDLE", "COMPLETED", "FAILED", "CANCELLED"],
    )
    def test_inactive_states(self, state_name: str):
        from k1.planner.plan_fsm import PlanState

        assert PlanState(state_name).is_active is False

    def test_exactly_seven_active_states(self):
        from k1.planner.plan_fsm import PlanState

        actives = [s for s in PlanState if s.is_active]
        assert len(actives) == 7

    def test_active_equals_not_idle_and_not_terminal(self):
        """is_active == (self != IDLE and not is_terminal) for ALL states."""
        from k1.planner.plan_fsm import PlanState

        for state in PlanState:
            expected = state != PlanState.IDLE and not state.is_terminal
            assert (
                state.is_active is expected
            ), f"{state}: is_active={state.is_active}, expected={expected}"


# ===================================================================
# 2.1.1f -- Property classification exhaustiveness
# ===================================================================


class TestPlanStateClassificationExhaustive:
    """Every state has exactly one classification bucket."""

    def test_idle_is_unique_bucket(self):
        """IDLE: not terminal, not micro, not active."""
        from k1.planner.plan_fsm import PlanState

        s = PlanState.IDLE
        assert not s.is_terminal
        assert not s.is_micro
        assert not s.is_active

    def test_transient_states_bucket(self):
        """SKETCHING..COMMITTING: active=True, terminal=False, micro=False."""
        from k1.planner.plan_fsm import PlanState

        transients = [
            PlanState.SKETCHING,
            PlanState.EXPANDING,
            PlanState.VALIDATING,
            PlanState.COMMITTING,
        ]
        for s in transients:
            assert s.is_active is True
            assert s.is_terminal is False
            assert s.is_micro is False

    def test_micro_states_bucket(self):
        """MICRO_*: active=True, micro=True, terminal=False."""
        from k1.planner.plan_fsm import PlanState

        micros = [
            PlanState.MICRO_SKETCH,
            PlanState.MICRO_EXPAND,
            PlanState.MICRO_VALIDATE,
        ]
        for s in micros:
            assert s.is_active is True
            assert s.is_micro is True
            assert s.is_terminal is False

    def test_terminal_states_bucket(self):
        """COMPLETED/FAILED/CANCELLED: terminal=True, active=False, micro=False."""
        from k1.planner.plan_fsm import PlanState

        terminals = [PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED]
        for s in terminals:
            assert s.is_terminal is True
            assert s.is_active is False
            assert s.is_micro is False

    def test_total_coverage(self):
        """idle(1) + transient(4) + micro(3) + terminal(3) = 11."""
        from k1.planner.plan_fsm import PlanState

        idle = [s for s in PlanState if s == PlanState.IDLE]
        transient = [s for s in PlanState if s.is_active and not s.is_micro and s != PlanState.IDLE]
        micro = [s for s in PlanState if s.is_micro]
        terminal = [s for s in PlanState if s.is_terminal]

        assert len(idle) == 1
        assert len(transient) == 4
        assert len(micro) == 3
        assert len(terminal) == 3
        assert len(idle) + len(transient) + len(micro) + len(terminal) == 11


# ===================================================================
# 2.1.1g -- Pre-computed frozensets
# ===================================================================


class TestPlanStateFrozensets:
    """Internal _TERMINAL_STATES and _MICRO_STATES frozensets."""

    def test_terminal_frozenset_contents(self):
        from k1.planner.plan_fsm import _TERMINAL_STATES, PlanState

        assert _TERMINAL_STATES == frozenset(
            {PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED}
        )

    def test_terminal_frozenset_type(self):
        from k1.planner.plan_fsm import _TERMINAL_STATES

        assert isinstance(_TERMINAL_STATES, frozenset)

    def test_micro_frozenset_contents(self):
        from k1.planner.plan_fsm import _MICRO_STATES, PlanState

        assert _MICRO_STATES == frozenset(
            {PlanState.MICRO_SKETCH, PlanState.MICRO_EXPAND, PlanState.MICRO_VALIDATE}
        )

    def test_micro_frozenset_type(self):
        from k1.planner.plan_fsm import _MICRO_STATES

        assert isinstance(_MICRO_STATES, frozenset)


# ===================================================================
# 2.1.1h -- Layer 0 import constraints
# ===================================================================


class TestPlanFsmLayer0Imports:
    """plan_fsm.py is Layer 0: imports only from stdlib and k1.planner.types."""

    def test_no_internal_imports(self):
        """plan_fsm.py may import from k1.planner.types (PlannerError) but nothing else."""
        import pathlib

        src = pathlib.Path("k1/planner/plan_fsm.py").read_text()
        # Allow: stdlib, k1.planner.types (Layer 0 peer)
        _ALLOWED_K1 = {"from k1.planner.types import PlannerError"}
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                if "from __future__" in stripped:
                    continue
                if "from enum" in stripped or "import enum" in stripped:
                    continue
                if "from typing" in stripped or "import typing" in stripped:
                    continue
                if stripped in _ALLOWED_K1:
                    continue
                # Disallow k1 or any other internal import
                assert (
                    "k1." not in stripped
                ), f"Layer 0 violation: plan_fsm.py imports from k1: {stripped}"
                assert (
                    "k0." not in stripped
                ), f"Layer 0 violation: plan_fsm.py imports from k0: {stripped}"


# ===================================================================
# 2.1.1i -- Module exports and package integration
# ===================================================================


class TestPlanFsmModuleExports:
    """plan_fsm.py __all__ and package __init__.py integration."""

    def test_module_has_all(self):
        from k1.planner import plan_fsm

        assert hasattr(plan_fsm, "__all__")

    def test_planstate_in_module_all(self):
        from k1.planner import plan_fsm

        assert "PlanState" in plan_fsm.__all__

    def test_importable_from_plan_fsm(self):
        from k1.planner.plan_fsm import PlanState

        assert PlanState.IDLE == "IDLE"

    def test_importable_from_package_init(self):
        from k1.planner import PlanState

        assert PlanState.IDLE == "IDLE"

    def test_planstate_in_package_all(self):
        import k1.planner

        assert "PlanState" in k1.planner.__all__


# ===================================================================
# 2.1.1j -- Spec cross-reference: SS18.1 exact state descriptions
# ===================================================================


class TestPlanStateSpecCrossRef:
    """Each state maps to its SS18.1 description."""

    def test_idle_is_initial_resting(self):
        """SS18.1: IDLE -- Initial and resting state. No plan in progress."""
        from k1.planner.plan_fsm import PlanState

        s = PlanState.IDLE
        assert s.value == "IDLE"
        assert not s.is_active
        assert not s.is_terminal
        assert not s.is_micro

    def test_sketching_is_stage_1(self):
        """SS18.1: SKETCHING -- Stage 1 active (discovery tools + LLM sketch)."""
        from k1.planner.plan_fsm import PlanState

        s = PlanState.SKETCHING
        assert s.is_active
        assert not s.is_micro

    def test_expanding_is_stage_2(self):
        """SS18.1: EXPANDING -- Stage 2 active (tool mapping + LLM expand)."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.EXPANDING.is_active
        assert not PlanState.EXPANDING.is_micro

    def test_validating_is_stage_3(self):
        """SS18.1: VALIDATING -- Stage 3 active (deterministic checks + LLM arbiter + HIL)."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.VALIDATING.is_active
        assert not PlanState.VALIDATING.is_micro

    def test_committing_is_stage_4(self):
        """SS18.1: COMMITTING -- Stage 4 active (plan assembly + WAL persist + event emit).
        Also reused for micro-replan Stage 4."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.COMMITTING.is_active
        assert not PlanState.COMMITTING.is_micro  # Not a micro state itself

    def test_micro_sketch_is_micro_stage_1(self):
        """SS18.1: MICRO_SKETCH -- re-sketch remaining steps."""
        from k1.planner.plan_fsm import PlanState

        s = PlanState.MICRO_SKETCH
        assert s.is_micro
        assert s.is_active

    def test_micro_expand_is_micro_stage_2(self):
        """SS18.1: MICRO_EXPAND -- re-map tools for replacement steps."""
        from k1.planner.plan_fsm import PlanState

        s = PlanState.MICRO_EXPAND
        assert s.is_micro
        assert s.is_active

    def test_micro_validate_is_micro_stage_3(self):
        """SS18.1: MICRO_VALIDATE -- validate replacement steps."""
        from k1.planner.plan_fsm import PlanState

        s = PlanState.MICRO_VALIDATE
        assert s.is_micro
        assert s.is_active

    def test_completed_is_success_terminal(self):
        """SS18.1: COMPLETED -- plan committed and delivered."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.COMPLETED.is_terminal
        assert not PlanState.COMPLETED.is_active

    def test_failed_is_error_terminal(self):
        """SS18.1: FAILED -- unrecoverable after retry."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.FAILED.is_terminal
        assert not PlanState.FAILED.is_active

    def test_cancelled_is_cancel_terminal(self):
        """SS18.1: CANCELLED -- cancelled by Orchestrator via send_cancel()."""
        from k1.planner.plan_fsm import PlanState

        assert PlanState.CANCELLED.is_terminal
        assert not PlanState.CANCELLED.is_active
