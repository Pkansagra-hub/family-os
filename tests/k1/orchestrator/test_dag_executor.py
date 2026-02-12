"""
Tests for DAGExecutor.build_waves() -- Topological Sort (Issue 2.2.1).

Validates: Kahn's algorithm correctness, cycle detection, step/wave limit
enforcement, dependency reference validation, edge cases (single step,
empty deps, fully independent, wide/deep DAGs), deterministic wave
ordering, and DAGExecutor constructor/state initialization.

Test classes:
  TestBuildWavesLinear        -- Linear chains (s1 -> s2 -> s3).
  TestBuildWavesParallel      -- All steps independent -> single wave.
  TestBuildWavesDiamond       -- Diamond DAG (s1 -> s2+s3 -> s4).
  TestBuildWavesComplex       -- Multi-wave complex DAGs.
  TestCycleDetection          -- Cycle error cases.
  TestLimitEnforcement        -- Step/wave count validation.
  TestDependencyValidation    -- Invalid dependency references.
  TestEdgeCases               -- Single step, no deps, wide/deep.
  TestDeterminism             -- Reproducible wave ordering.
  TestConstructor             -- DAGExecutor init and state.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from k1.orchestrator.orchestration.dag_executor import (
    MAX_STEPS,
    MAX_WAVES,
    CycleError,
    DAGExecutor,
    StepLimitExceeded,
    WaveLimitExceeded,
)
from k1.orchestrator.types import PlanStep, Wave

# ===========================================================================
# Helpers
# ===========================================================================


def _step(step_id: str, capability: str = "cap.test") -> PlanStep:
    """Create a minimal PlanStep for testing."""
    return PlanStep(id=step_id, capability=capability)


def _steps(*ids: str) -> List[PlanStep]:
    """Create multiple PlanSteps from sequential IDs."""
    return [_step(sid) for sid in ids]


def _wave_ids(wave: Wave) -> List[str]:
    """Extract sorted step IDs from a Wave."""
    return [s.id for s in wave.steps]


# ===========================================================================
# Fake ports for constructor
# ===========================================================================


class FakePort:
    """Minimal fake for all port protocols in constructor."""

    pass


def _make_executor(**overrides: Any) -> DAGExecutor:
    """Create a DAGExecutor with fake deps for constructor testing."""
    defaults: Dict[str, Any] = {
        "fabric_port": FakePort(),
        "planner_port": FakePort(),
        "delta_port": FakePort(),
        "state_port": FakePort(),
        "bridge_port": FakePort(),
        "step_runner": FakePort(),
        "error_router": FakePort(),
    }
    defaults.update(overrides)
    return DAGExecutor(**defaults)


# ===========================================================================
# TestBuildWavesLinear
# ===========================================================================


class TestBuildWavesLinear:
    """Linear chain topologies: s1 -> s2 -> s3 etc."""

    def test_two_step_chain(self) -> None:
        """s1 -> s2 produces 2 waves."""
        steps = _steps("s1", "s2")
        deps = {"s2": ["s1"]}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 2
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2"]

    def test_three_step_chain(self) -> None:
        """s1 -> s2 -> s3 produces 3 waves."""
        steps = _steps("s1", "s2", "s3")
        deps = {"s2": ["s1"], "s3": ["s2"]}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 3
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2"]
        assert _wave_ids(waves[2]) == ["s3"]

    def test_wave_indices_are_sequential(self) -> None:
        """Wave indices are 0-based and sequential."""
        steps = _steps("a", "b", "c")
        deps = {"b": ["a"], "c": ["b"]}

        waves = DAGExecutor.build_waves(steps, deps)

        for i, wave in enumerate(waves):
            assert wave.wave_index == i

    def test_resolved_params_empty(self) -> None:
        """Waves start with empty resolved_params."""
        steps = _steps("s1", "s2")
        deps = {"s2": ["s1"]}

        waves = DAGExecutor.build_waves(steps, deps)

        for wave in waves:
            assert wave.resolved_params == {}


# ===========================================================================
# TestBuildWavesParallel
# ===========================================================================


class TestBuildWavesParallel:
    """All steps independent -- single wave."""

    def test_two_independent_steps(self) -> None:
        """Two independent steps -> one wave."""
        steps = _steps("s1", "s2")
        deps: Dict[str, List[str]] = {}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 1
        assert _wave_ids(waves[0]) == ["s1", "s2"]

    def test_five_independent_steps(self) -> None:
        """Five independent steps -> one wave with all five."""
        steps = _steps("a", "b", "c", "d", "e")
        deps: Dict[str, List[str]] = {}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 1
        assert _wave_ids(waves[0]) == ["a", "b", "c", "d", "e"]

    def test_ten_independent_concurrent(self) -> None:
        """Ten independent steps (max per wave) -> one wave."""
        ids = [f"s{i}" for i in range(10)]
        steps = _steps(*ids)
        deps: Dict[str, List[str]] = {}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 1
        assert len(waves[0].steps) == 10


# ===========================================================================
# TestBuildWavesDiamond
# ===========================================================================


class TestBuildWavesDiamond:
    """Diamond: s1 -> (s2, s3) -> s4."""

    def test_classic_diamond(self) -> None:
        """Diamond DAG produces 3 waves."""
        steps = _steps("s1", "s2", "s3", "s4")
        deps = {"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 3
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2", "s3"]  # parallel
        assert _wave_ids(waves[2]) == ["s4"]

    def test_double_diamond(self) -> None:
        """Two diamonds chained: (s1->s2+s3->s4) then (s4->s5+s6->s7)."""
        steps = _steps("s1", "s2", "s3", "s4", "s5", "s6", "s7")
        deps = {
            "s2": ["s1"],
            "s3": ["s1"],
            "s4": ["s2", "s3"],
            "s5": ["s4"],
            "s6": ["s4"],
            "s7": ["s5", "s6"],
        }

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 5
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2", "s3"]
        assert _wave_ids(waves[2]) == ["s4"]
        assert _wave_ids(waves[3]) == ["s5", "s6"]
        assert _wave_ids(waves[4]) == ["s7"]

    def test_wide_fan_out_fan_in(self) -> None:
        """s1 fans out to 5 steps, all converge on s7."""
        steps = _steps("s1", "s2", "s3", "s4", "s5", "s6", "s7")
        deps = {
            "s2": ["s1"],
            "s3": ["s1"],
            "s4": ["s1"],
            "s5": ["s1"],
            "s6": ["s1"],
            "s7": ["s2", "s3", "s4", "s5", "s6"],
        }

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 3
        assert _wave_ids(waves[0]) == ["s1"]
        assert len(waves[1].steps) == 5
        assert _wave_ids(waves[2]) == ["s7"]


# ===========================================================================
# TestBuildWavesComplex
# ===========================================================================


class TestBuildWavesComplex:
    """Multi-wave complex DAGs that exercise parallel + serial combos."""

    def test_mixed_serial_parallel(self) -> None:
        """s1, s2 independent; s3 depends on s1; s4 depends on s1+s2."""
        steps = _steps("s1", "s2", "s3", "s4")
        deps = {"s3": ["s1"], "s4": ["s1", "s2"]}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 2
        assert _wave_ids(waves[0]) == ["s1", "s2"]
        assert _wave_ids(waves[1]) == ["s3", "s4"]

    def test_staggered_dependencies(self) -> None:
        """s1 -> s2 -> s4; s1 -> s3 -> s5; s4+s5 -> s6."""
        steps = _steps("s1", "s2", "s3", "s4", "s5", "s6")
        deps = {
            "s2": ["s1"],
            "s3": ["s1"],
            "s4": ["s2"],
            "s5": ["s3"],
            "s6": ["s4", "s5"],
        }

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 4
        assert _wave_ids(waves[0]) == ["s1"]
        assert _wave_ids(waves[1]) == ["s2", "s3"]
        assert _wave_ids(waves[2]) == ["s4", "s5"]
        assert _wave_ids(waves[3]) == ["s6"]

    def test_two_independent_chains(self) -> None:
        """Two parallel chains: a1->a2->a3 and b1->b2->b3."""
        steps = _steps("a1", "a2", "a3", "b1", "b2", "b3")
        deps = {
            "a2": ["a1"],
            "a3": ["a2"],
            "b2": ["b1"],
            "b3": ["b2"],
        }

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 3
        assert set(_wave_ids(waves[0])) == {"a1", "b1"}
        assert set(_wave_ids(waves[1])) == {"a2", "b2"}
        assert set(_wave_ids(waves[2])) == {"a3", "b3"}

    def test_realistic_plan_schedule_event(self) -> None:
        """Realistic scenario: search calendar -> search contacts -> book venue."""
        steps = [
            _step("search_calendar", "tool.calendar.search"),
            _step("search_contacts", "tool.contacts.search"),
            _step("find_venue", "agent.venue.search"),
            _step("book_venue", "agent.venue.book"),
        ]
        deps = {
            "find_venue": ["search_calendar"],
            "book_venue": ["find_venue", "search_contacts"],
        }

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 3
        # Wave 0: search_calendar + search_contacts (independent)
        assert set(_wave_ids(waves[0])) == {"search_calendar", "search_contacts"}
        # Wave 1: find_venue (depends on search_calendar only)
        assert _wave_ids(waves[1]) == ["find_venue"]
        # Wave 2: book_venue (depends on find_venue + search_contacts)
        assert _wave_ids(waves[2]) == ["book_venue"]


# ===========================================================================
# TestCycleDetection
# ===========================================================================


class TestCycleDetection:
    """Cycle detection raises CycleError with involved step IDs."""

    def test_self_loop(self) -> None:
        """Step depending on itself is a cycle."""
        steps = _steps("s1")
        deps = {"s1": ["s1"]}

        with pytest.raises(CycleError) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        assert "s1" in exc_info.value.remaining_steps

    def test_two_step_cycle(self) -> None:
        """s1 -> s2 -> s1 is a cycle."""
        steps = _steps("s1", "s2")
        deps = {"s1": ["s2"], "s2": ["s1"]}

        with pytest.raises(CycleError) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        assert exc_info.value.remaining_steps == {"s1", "s2"}

    def test_three_step_cycle(self) -> None:
        """s1 -> s2 -> s3 -> s1 is a cycle."""
        steps = _steps("s1", "s2", "s3")
        deps = {"s2": ["s1"], "s3": ["s2"], "s1": ["s3"]}

        with pytest.raises(CycleError) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        assert exc_info.value.remaining_steps == {"s1", "s2", "s3"}

    def test_cycle_in_subset(self) -> None:
        """Cycle in a subgraph: s1 independent, s2<->s3 cycle."""
        steps = _steps("s1", "s2", "s3")
        deps = {"s2": ["s3"], "s3": ["s2"]}

        with pytest.raises(CycleError) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        # s1 is NOT in the cycle
        assert "s1" not in exc_info.value.remaining_steps
        assert exc_info.value.remaining_steps == {"s2", "s3"}

    def test_cycle_error_message_contains_step_ids(self) -> None:
        """CycleError message includes involved step IDs."""
        steps = _steps("alpha", "beta")
        deps = {"alpha": ["beta"], "beta": ["alpha"]}

        with pytest.raises(CycleError, match="alpha.*beta|beta.*alpha"):
            DAGExecutor.build_waves(steps, deps)

    def test_large_cycle(self) -> None:
        """Long cycle: s1->s2->s3->s4->s5->s1."""
        ids = [f"s{i}" for i in range(1, 6)]
        steps = _steps(*ids)
        deps = {
            "s2": ["s1"],
            "s3": ["s2"],
            "s4": ["s3"],
            "s5": ["s4"],
            "s1": ["s5"],
        }

        with pytest.raises(CycleError) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        assert len(exc_info.value.remaining_steps) == 5


# ===========================================================================
# TestLimitEnforcement
# ===========================================================================


class TestLimitEnforcement:
    """Step and wave count limit validation."""

    def test_max_steps_exact_pass(self) -> None:
        """Exactly MAX_STEPS (50) steps is allowed."""
        ids = [f"s{i}" for i in range(MAX_STEPS)]
        steps = _steps(*ids)
        deps: Dict[str, List[str]] = {}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 1
        assert len(waves[0].steps) == MAX_STEPS

    def test_max_steps_exceeded(self) -> None:
        """51 steps raises StepLimitExceeded."""
        ids = [f"s{i}" for i in range(MAX_STEPS + 1)]
        steps = _steps(*ids)
        deps: Dict[str, List[str]] = {}

        with pytest.raises(StepLimitExceeded) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        assert exc_info.value.step_count == MAX_STEPS + 1
        assert exc_info.value.max_steps == MAX_STEPS

    def test_max_waves_exact_pass(self) -> None:
        """Exactly MAX_WAVES (20) waves -- long chain of 20 steps."""
        ids = [f"s{i}" for i in range(MAX_WAVES)]
        steps = _steps(*ids)
        deps: Dict[str, List[str]] = {}
        for i in range(1, MAX_WAVES):
            deps[f"s{i}"] = [f"s{i - 1}"]

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == MAX_WAVES

    def test_max_waves_exceeded(self) -> None:
        """21-step linear chain exceeds MAX_WAVES."""
        count = MAX_WAVES + 1
        ids = [f"s{i}" for i in range(count)]
        steps = _steps(*ids)
        deps: Dict[str, List[str]] = {}
        for i in range(1, count):
            deps[f"s{i}"] = [f"s{i - 1}"]

        with pytest.raises(WaveLimitExceeded) as exc_info:
            DAGExecutor.build_waves(steps, deps)

        assert exc_info.value.wave_count == count
        assert exc_info.value.max_waves == MAX_WAVES

    def test_step_limit_error_str(self) -> None:
        """StepLimitExceeded has descriptive message."""
        err = StepLimitExceeded(55)
        assert "55" in str(err)
        assert "50" in str(err)

    def test_wave_limit_error_str(self) -> None:
        """WaveLimitExceeded has descriptive message."""
        err = WaveLimitExceeded(25)
        assert "25" in str(err)
        assert "20" in str(err)


# ===========================================================================
# TestDependencyValidation
# ===========================================================================


class TestDependencyValidation:
    """Invalid dependency references raise ValueError."""

    def test_dep_key_not_in_steps(self) -> None:
        """Dependency key references a step that does not exist."""
        steps = _steps("s1")
        deps = {"s_unknown": ["s1"]}

        with pytest.raises(ValueError, match="s_unknown.*not found"):
            DAGExecutor.build_waves(steps, deps)

    def test_dep_value_not_in_steps(self) -> None:
        """Dependency value references a step that does not exist."""
        steps = _steps("s1", "s2")
        deps = {"s2": ["s_missing"]}

        with pytest.raises(ValueError, match="s_missing.*not in"):
            DAGExecutor.build_waves(steps, deps)

    def test_dep_key_and_value_both_invalid(self) -> None:
        """Both dependency key and value are invalid."""
        steps = _steps("s1")
        deps = {"ghost": ["phantom"]}

        with pytest.raises(ValueError):
            DAGExecutor.build_waves(steps, deps)


# ===========================================================================
# TestEdgeCases
# ===========================================================================


class TestEdgeCases:
    """Edge cases: single step, empty input, unusual topologies."""

    def test_single_step_no_deps(self) -> None:
        """Single step with no dependencies -> one wave."""
        steps = _steps("only")
        deps: Dict[str, List[str]] = {}

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 1
        assert _wave_ids(waves[0]) == ["only"]
        assert waves[0].wave_index == 0

    def test_empty_dep_list_for_step(self) -> None:
        """Step explicitly listed in deps with empty list -> no deps."""
        steps = _steps("s1", "s2")
        deps: Dict[str, List[str]] = {"s2": []}

        waves = DAGExecutor.build_waves(steps, deps)

        # Both steps have zero in-degree -> single wave
        assert len(waves) == 1
        assert _wave_ids(waves[0]) == ["s1", "s2"]

    def test_step_fields_preserved_in_wave(self) -> None:
        """PlanStep fields (capability, params, etc.) are preserved."""
        step = PlanStep(
            id="s1",
            capability="cap.test",
            params={"key": "value"},
            timeout_ms=5000,
        )
        waves = DAGExecutor.build_waves([step], {})

        assert waves[0].steps[0].capability == "cap.test"
        assert waves[0].steps[0].params == {"key": "value"}
        assert waves[0].steps[0].timeout_ms == 5000

    def test_deep_then_wide(self) -> None:
        """Chain of 3 -> fan out to 5 independent -> converge."""
        steps = _steps("a", "b", "c", "d1", "d2", "d3", "d4", "d5", "e")
        deps = {
            "b": ["a"],
            "c": ["b"],
            "d1": ["c"],
            "d2": ["c"],
            "d3": ["c"],
            "d4": ["c"],
            "d5": ["c"],
            "e": ["d1", "d2", "d3", "d4", "d5"],
        }

        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 5
        assert _wave_ids(waves[0]) == ["a"]
        assert _wave_ids(waves[1]) == ["b"]
        assert _wave_ids(waves[2]) == ["c"]
        assert len(waves[3].steps) == 5
        assert _wave_ids(waves[4]) == ["e"]


# ===========================================================================
# TestDeterminism
# ===========================================================================


class TestDeterminism:
    """Verify deterministic wave ordering for reproducibility."""

    def test_same_input_same_output(self) -> None:
        """Calling build_waves twice with same input produces identical output."""
        steps = _steps("c", "a", "b")
        deps = {"c": ["a"], "b": ["a"]}

        waves1 = DAGExecutor.build_waves(steps, deps)
        waves2 = DAGExecutor.build_waves(steps, deps)

        assert len(waves1) == len(waves2)
        for w1, w2 in zip(waves1, waves2):
            assert _wave_ids(w1) == _wave_ids(w2)

    def test_alphabetical_within_wave(self) -> None:
        """Steps within a wave are sorted alphabetically by ID."""
        steps = _steps("zeta", "alpha", "mu", "beta")
        deps: Dict[str, List[str]] = {}

        waves = DAGExecutor.build_waves(steps, deps)

        assert _wave_ids(waves[0]) == ["alpha", "beta", "mu", "zeta"]

    def test_input_order_does_not_affect_output(self) -> None:
        """Changing step list order does not affect wave composition."""
        steps_order1 = _steps("s1", "s2", "s3", "s4")
        steps_order2 = _steps("s4", "s3", "s2", "s1")
        deps = {"s2": ["s1"], "s3": ["s1"], "s4": ["s2", "s3"]}

        waves1 = DAGExecutor.build_waves(steps_order1, deps)
        waves2 = DAGExecutor.build_waves(steps_order2, deps)

        assert len(waves1) == len(waves2)
        for w1, w2 in zip(waves1, waves2):
            assert _wave_ids(w1) == _wave_ids(w2)


# ===========================================================================
# TestConstructor
# ===========================================================================


class TestConstructor:
    """DAGExecutor constructor and initial state."""

    def test_initial_state(self) -> None:
        """Fresh DAGExecutor has correct initial state."""
        dag = _make_executor()

        assert dag.interrupt_flag is False
        assert dag.merged_results == {}
        assert dag._cancelled_steps == set()

    def test_guards_default_empty(self) -> None:
        """Guards default to empty list when not provided."""
        dag = _make_executor()

        assert dag._guards == []

    def test_guards_injected(self) -> None:
        """Custom guards list is stored."""
        guards = [FakePort(), FakePort()]
        dag = _make_executor(guards=guards)

        assert dag._guards is guards
        assert len(dag._guards) == 2

    def test_repr(self) -> None:
        """repr includes guard count and state info."""
        dag = _make_executor()

        r = repr(dag)
        assert "DAGExecutor" in r
        assert "guards=0" in r
        assert "interrupt=False" in r

    def test_ports_stored(self) -> None:
        """Constructor stores all port references."""
        fp = FakePort()
        pp = FakePort()
        dp = FakePort()
        sp = FakePort()
        bp = FakePort()
        sr = FakePort()
        er = FakePort()

        dag = DAGExecutor(
            fabric_port=fp,
            planner_port=pp,
            delta_port=dp,
            state_port=sp,
            bridge_port=bp,
            step_runner=sr,
            error_router=er,
        )

        assert dag._fabric_port is fp
        assert dag._planner_port is pp
        assert dag._delta_port is dp
        assert dag._state_port is sp
        assert dag._bridge_port is bp
        assert dag._step_runner is sr
        assert dag._error_router is er

    def test_build_waves_is_static(self) -> None:
        """build_waves can be called without an instance."""
        steps = _steps("s1", "s2")
        deps = {"s2": ["s1"]}

        # Call as static method (no instance needed)
        waves = DAGExecutor.build_waves(steps, deps)

        assert len(waves) == 2


# ===========================================================================
# TestBuildWavesPurity
# ===========================================================================


class TestBuildWavesPurity:
    """Verify build_waves is a pure function with no side effects."""

    def test_input_steps_not_mutated(self) -> None:
        """Input steps list is not modified."""
        steps = _steps("s1", "s2", "s3")
        original_ids = [s.id for s in steps]
        deps = {"s2": ["s1"], "s3": ["s2"]}

        DAGExecutor.build_waves(steps, deps)

        assert [s.id for s in steps] == original_ids

    def test_input_deps_not_mutated(self) -> None:
        """Input dependencies dict is not modified."""
        steps = _steps("s1", "s2", "s3")
        deps = {"s2": ["s1"], "s3": ["s2"]}
        original_deps = {"s2": ["s1"], "s3": ["s2"]}

        DAGExecutor.build_waves(steps, deps)

        assert deps == original_deps

    def test_no_instance_state_mutation(self) -> None:
        """Calling build_waves on an instance does not mutate state."""
        dag = _make_executor()
        steps = _steps("s1", "s2")
        deps = {"s2": ["s1"]}

        dag.build_waves(steps, deps)

        assert dag.merged_results == {}
        assert dag._cancelled_steps == set()
        assert dag.interrupt_flag is False
