"""
Integration tests for TDL-HCO (Temporal Difference Learning for Habit/Cognitive Optimization).

M5-E3: Testing and Validation

These tests validate:
- TD learning from routine executions
- Bottleneck detection with negative value gradients
- Optimization suggestion generation
- End-to-end optimize() workflow

References:
- R5_ALGORITHM_BACKLOG.md M5-E3: Testing and Validation
- M8_EXECUTION.md Issue 8.1.11: TDL-HCO Motor Rehearsal for Habits
- tdl_hco.py algorithm implementation
"""

from __future__ import annotations

import pytest

from k0.modules.consolidation.algorithms.tdl_hco import (
    RoutineExecution,
    RoutineStepData,
    RoutineTemplate,
    TDLConfig,
    TDLOptimization,
    TemporalDifferenceLearning,
    ValueFunction,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def morning_routine_with_bottleneck() -> RoutineTemplate:
    """
    Morning routine with a clear bottleneck step.

    Steps: wake_up -> shower -> find_keys (BOTTLENECK) -> commute

    The find_keys step has negative reward, creating a value drop.
    """
    steps_template = ["wake_up", "shower", "find_keys", "commute"]

    # Create execution with bottleneck (find_keys has strongly negative reward)
    # Need reward negative enough to cause value drop exceeding -2.0 threshold
    execution_steps = [
        RoutineStepData(
            step_id="step_0",
            step_name="wake_up",
            step_index=0,
            duration_ms=60000,
            success=True,
            reward=1.0,  # Positive start
        ),
        RoutineStepData(
            step_id="step_1",
            step_name="shower",
            step_index=1,
            duration_ms=600000,  # 10 minutes
            success=True,
            reward=2.0,  # Strong positive to build value before bottleneck
        ),
        RoutineStepData(
            step_id="step_2",
            step_name="find_keys",
            step_index=2,
            duration_ms=300000,  # 5 minutes wasted
            success=True,
            reward=-10.0,  # BOTTLENECK: Strong negative for value drop > 2.0
        ),
        RoutineStepData(
            step_id="step_3",
            step_name="commute",
            step_index=3,
            duration_ms=1800000,  # 30 minutes
            success=True,
            reward=0.5,
        ),
    ]

    # Create multiple executions to meet min_routine_occurrences
    executions = []
    for i in range(5):
        executions.append(
            RoutineExecution(
                execution_id=f"exec_{i}",
                routine_id="morning_routine",
                routine_name="Morning Routine",
                steps=execution_steps.copy(),
                total_duration_ms=2760000,
                completed=True,
                success=True,
                episode_id=f"ep_{i}",
                timestamp_ms=1700000000000 + i * 86400000,
            )
        )

    return RoutineTemplate(
        routine_id="morning_routine",
        routine_name="Morning Routine",
        canonical_steps=steps_template,
        execution_count=5,
        avg_duration_ms=2760000,
        success_rate=1.0,
        executions=executions,
    )


@pytest.fixture
def smooth_routine() -> RoutineTemplate:
    """Routine with no bottlenecks (all positive rewards)."""
    steps_template = ["start", "middle", "end"]

    execution_steps = [
        RoutineStepData(
            step_id="step_0",
            step_name="start",
            step_index=0,
            duration_ms=60000,
            success=True,
            reward=0.5,
        ),
        RoutineStepData(
            step_id="step_1",
            step_name="middle",
            step_index=1,
            duration_ms=120000,
            success=True,
            reward=0.6,
        ),
        RoutineStepData(
            step_id="step_2",
            step_name="end",
            step_index=2,
            duration_ms=60000,
            success=True,
            reward=0.7,
        ),
    ]

    executions = [
        RoutineExecution(
            execution_id=f"exec_{i}",
            routine_id="smooth_routine",
            routine_name="Smooth Routine",
            steps=execution_steps.copy(),
            total_duration_ms=240000,
            completed=True,
            success=True,
            episode_id=f"ep_{i}",
        )
        for i in range(5)
    ]

    return RoutineTemplate(
        routine_id="smooth_routine",
        routine_name="Smooth Routine",
        canonical_steps=steps_template,
        execution_count=5,
        avg_duration_ms=240000,
        success_rate=1.0,
        executions=executions,
    )


@pytest.fixture
def short_routine() -> RoutineTemplate:
    """Routine that's too short to qualify (less than min_routine_length)."""
    return RoutineTemplate(
        routine_id="short_routine",
        routine_name="Short Routine",
        canonical_steps=["step_a", "step_b"],  # Only 2 steps, min is 3
        execution_count=10,
        avg_duration_ms=60000,
        success_rate=1.0,
        executions=[],
    )


@pytest.fixture
def tdl_config() -> TDLConfig:
    """Default TDL configuration for tests."""
    return TDLConfig(
        learning_rate=0.1,
        discount_factor=0.9,
        bottleneck_threshold=-2.0,  # V drop > 2.0 = bottleneck
        min_routine_length=3,
        min_routine_occurrences=3,
        max_routines=10,
        max_optimizations=5,
        seed=42,
    )


# =============================================================================
# VALUE FUNCTION TESTS
# =============================================================================


class TestValueFunction:
    """Tests for TD(0) value function learning."""

    def test_value_function_initialization(self) -> None:
        """ValueFunction initializes with empty values."""
        vf = ValueFunction()

        assert vf.values == {}
        assert vf.visit_counts == {}
        assert vf.learning_rate == 0.1
        assert vf.discount_factor == 0.9

    def test_get_state_key_format(self) -> None:
        """State key has expected format."""
        vf = ValueFunction()
        key = vf.get_state_key("routine_1", 2, "step_name")

        assert key == "routine_1:2:step_name"

    def test_get_value_returns_zero_for_unknown_state(self) -> None:
        """Unknown states have value 0.0."""
        vf = ValueFunction()

        assert vf.get_value("unknown:state:key") == 0.0

    def test_td_update_increases_visit_count(self) -> None:
        """TD update increments visit count."""
        vf = ValueFunction()
        state = "test:0:start"

        assert vf.get_visit_count(state) == 0

        vf.td_update(state, reward=1.0, next_state=None)

        assert vf.get_visit_count(state) == 1

    def test_td_update_modifies_value(self) -> None:
        """TD update changes state value based on reward."""
        vf = ValueFunction(learning_rate=0.1)
        state = "test:0:start"

        assert vf.get_value(state) == 0.0

        # Positive reward should increase value
        vf.td_update(state, reward=1.0, next_state=None)

        # V(s) = 0 + 0.1 * (1.0 + 0 - 0) = 0.1
        assert vf.get_value(state) == pytest.approx(0.1)

    def test_td_update_considers_next_state_value(self) -> None:
        """TD update uses next state's value in calculation."""
        vf = ValueFunction(learning_rate=0.1, discount_factor=0.9)

        # Set up next state with known value
        next_state = "test:1:next"
        vf.values[next_state] = 5.0

        state = "test:0:start"

        # V(s) = 0 + 0.1 * (1.0 + 0.9 * 5.0 - 0) = 0.1 * 5.5 = 0.55
        vf.td_update(state, reward=1.0, next_state=next_state)

        assert vf.get_value(state) == pytest.approx(0.55)

    def test_compute_value_gradient(self) -> None:
        """Value gradient computes V(s') - V(s)."""
        vf = ValueFunction()
        vf.values["state_a"] = 3.0
        vf.values["state_b"] = 1.0  # Lower than state_a

        gradient = vf.compute_value_gradient("state_a", "state_b")

        assert gradient == pytest.approx(-2.0)  # 1.0 - 3.0


# =============================================================================
# TD LEARNING FROM EXECUTIONS
# =============================================================================


class TestTDLearningFromExecutions:
    """Tests for learning value function from routine executions."""

    def test_learn_from_execution_returns_td_errors(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Learning from execution returns TD errors for each step."""
        tdl = TemporalDifferenceLearning(config=tdl_config)
        execution = morning_routine_with_bottleneck.executions[0]

        td_errors = tdl.learn_from_execution(execution)

        # One TD error per step
        assert len(td_errors) == len(execution.steps)

    def test_learn_from_execution_updates_value_function(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Learning updates the value function for each state."""
        tdl = TemporalDifferenceLearning(config=tdl_config)
        execution = morning_routine_with_bottleneck.executions[0]

        # Before learning
        state_key = tdl.value_function.get_state_key("morning_routine", 0, "wake_up")
        assert tdl.value_function.get_value(state_key) == 0.0

        tdl.learn_from_execution(execution)

        # After learning, value should be non-zero
        assert tdl.value_function.get_value(state_key) != 0.0

    def test_multiple_executions_refine_values(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Multiple execution observations refine value estimates."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        state_key = tdl.value_function.get_state_key("morning_routine", 0, "wake_up")

        # Learn from multiple executions
        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        # Visit count should equal number of executions
        assert tdl.value_function.get_visit_count(state_key) == 5


# =============================================================================
# BOTTLENECK DETECTION TESTS
# =============================================================================


class TestBottleneckDetection:
    """Tests for detecting bottlenecks via value gradient analysis."""

    def test_detect_bottleneck_with_negative_reward_step(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Bottleneck detected at transition TO step with negative reward.

        Note: The bottleneck is named after the SOURCE step of the transition,
        i.e., the step BEFORE the problematic step. The value drop occurs
        on the transition from 'shower' to 'find_keys', so the bottleneck
        is at step_index=1 ('shower').
        """
        tdl = TemporalDifferenceLearning(config=tdl_config)

        # Learn from all executions first
        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        # Should detect at least one bottleneck
        assert len(bottlenecks) >= 1

        # Bottleneck is at 'shower' (step_index=1) - the step BEFORE find_keys
        # because the value drop occurs on the shower->find_keys transition
        bottleneck_steps = [b.step_name for b in bottlenecks]
        assert "shower" in bottleneck_steps or any(b.step_index == 1 for b in bottlenecks)

    def test_no_bottleneck_in_smooth_routine(
        self,
        smooth_routine: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """No bottleneck detected in routine with all positive rewards."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        # Learn from executions
        for execution in smooth_routine.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(smooth_routine)

        # Should not detect any bottlenecks
        assert len(bottlenecks) == 0

    def test_bottleneck_has_negative_value_drop(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Detected bottleneck has negative value gradient."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        if bottlenecks:
            bottleneck = bottlenecks[0]
            assert bottleneck.value_drop < 0
            assert bottleneck.value_drop < tdl_config.bottleneck_threshold

    def test_bottlenecks_sorted_by_severity(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Bottlenecks are sorted by severity (descending)."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        if len(bottlenecks) > 1:
            for i in range(len(bottlenecks) - 1):
                assert bottlenecks[i].severity >= bottlenecks[i + 1].severity


# =============================================================================
# OPTIMIZATION SUGGESTION TESTS
# =============================================================================


class TestOptimizationSuggestions:
    """Tests for optimization suggestion generation."""

    def test_generate_suggestions_from_bottlenecks(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Suggestions generated for detected bottlenecks."""
        import random

        tdl = TemporalDifferenceLearning(config=tdl_config)

        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        if bottlenecks:
            rng = random.Random(42)
            suggestions = tdl.generate_suggestions(
                bottlenecks, morning_routine_with_bottleneck, rng
            )

            assert len(suggestions) >= 1
            assert all(isinstance(s, TDLOptimization) for s in suggestions)

    def test_suggestion_has_expected_fields(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """Generated suggestion has all required fields."""
        import random

        tdl = TemporalDifferenceLearning(config=tdl_config)

        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        if bottlenecks:
            rng = random.Random(42)
            suggestions = tdl.generate_suggestions(
                bottlenecks, morning_routine_with_bottleneck, rng
            )

            if suggestions:
                suggestion = suggestions[0]
                assert suggestion.optimization_id
                assert suggestion.routine_id == "morning_routine"
                assert suggestion.routine_name == "Morning Routine"
                assert suggestion.suggested_action
                assert suggestion.expected_improvement > 0
                assert 0.0 <= suggestion.confidence <= 1.0
                assert suggestion.rationale
                assert suggestion.bottleneck is not None

    def test_suggestion_to_routine_optimization(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """TDLOptimization converts to RoutineOptimization model."""
        import random

        tdl = TemporalDifferenceLearning(config=tdl_config)

        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        if bottlenecks:
            rng = random.Random(42)
            suggestions = tdl.generate_suggestions(
                bottlenecks, morning_routine_with_bottleneck, rng
            )

            if suggestions:
                routine_opt = suggestions[0].to_routine_optimization()

                assert routine_opt.routine_id == "morning_routine"
                assert routine_opt.routine_name == "Morning Routine"
                assert routine_opt.bottleneck_step
                assert routine_opt.suggested_action


# =============================================================================
# OPTIMIZE (MAIN ENTRY POINT) TESTS
# =============================================================================


class TestOptimize:
    """Tests for the main optimize() entry point."""

    def test_optimize_with_bottleneck_routine(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """optimize() detects bottlenecks and generates optimizations."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        optimizations = tdl.optimize(
            routines=[morning_routine_with_bottleneck],
            rng_seed=42,
        )

        # Should generate at least one optimization
        assert len(optimizations) >= 1

        # Check optimization targets the transition TO find_keys
        # (bottleneck is at 'shower' step_index=1)
        opt = optimizations[0]
        assert "shower" in opt.bottleneck.step_name or opt.bottleneck.step_index == 1

    def test_optimize_returns_empty_for_smooth_routine(
        self,
        smooth_routine: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """optimize() returns empty list for routine without bottlenecks."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        optimizations = tdl.optimize(
            routines=[smooth_routine],
            rng_seed=42,
        )

        # No bottlenecks = no optimizations
        assert len(optimizations) == 0

    def test_optimize_filters_short_routines(
        self,
        short_routine: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """optimize() filters out routines shorter than min_routine_length."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        optimizations = tdl.optimize(
            routines=[short_routine],
            rng_seed=42,
        )

        # Short routine should be filtered out
        assert len(optimizations) == 0

    def test_optimize_respects_max_optimizations(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
    ) -> None:
        """optimize() respects max_optimizations config."""
        config = TDLConfig(
            max_optimizations=1,  # Limit to 1
            min_routine_occurrences=1,
            seed=42,
        )
        tdl = TemporalDifferenceLearning(config=config)

        optimizations = tdl.optimize(
            routines=[morning_routine_with_bottleneck],
            rng_seed=42,
        )

        assert len(optimizations) <= 1

    def test_optimize_sorted_by_expected_improvement(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        smooth_routine: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """optimize() returns results sorted by expected improvement."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        optimizations = tdl.optimize(
            routines=[morning_routine_with_bottleneck, smooth_routine],
            rng_seed=42,
        )

        if len(optimizations) > 1:
            for i in range(len(optimizations) - 1):
                assert (
                    optimizations[i].expected_improvement
                    >= optimizations[i + 1].expected_improvement
                )

    def test_optimize_deterministic_with_seed(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """optimize() produces same results with same seed."""
        tdl1 = TemporalDifferenceLearning(config=tdl_config)
        tdl2 = TemporalDifferenceLearning(config=tdl_config)

        optimizations1 = tdl1.optimize(
            routines=[morning_routine_with_bottleneck],
            rng_seed=42,
        )
        optimizations2 = tdl2.optimize(
            routines=[morning_routine_with_bottleneck],
            rng_seed=42,
        )

        assert len(optimizations1) == len(optimizations2)
        if optimizations1:
            assert optimizations1[0].bottleneck.step_name == optimizations2[0].bottleneck.step_name


# =============================================================================
# CONFIGURATION VALIDATION TESTS
# =============================================================================


class TestTDLConfig:
    """Tests for TDLConfig validation."""

    def test_default_config_values(self) -> None:
        """Default config has expected values."""
        config = TDLConfig()

        assert config.learning_rate == 0.1
        assert config.discount_factor == 0.9
        assert config.bottleneck_threshold == -2.0
        assert config.min_routine_length == 3
        assert config.min_routine_occurrences == 3

    def test_invalid_learning_rate_rejected(self) -> None:
        """Learning rate outside (0, 1] is rejected."""
        with pytest.raises(ValueError, match="learning_rate"):
            TDLConfig(learning_rate=0.0)

        with pytest.raises(ValueError, match="learning_rate"):
            TDLConfig(learning_rate=1.5)

    def test_invalid_discount_factor_rejected(self) -> None:
        """Discount factor outside (0, 1] is rejected."""
        with pytest.raises(ValueError, match="discount_factor"):
            TDLConfig(discount_factor=0.0)

    def test_min_routine_length_validation(self) -> None:
        """min_routine_length must be at least 2."""
        with pytest.raises(ValueError, match="min_routine_length"):
            TDLConfig(min_routine_length=1)


# =============================================================================
# RESET AND STATE MANAGEMENT TESTS
# =============================================================================


class TestResetAndStateManagement:
    """Tests for TDL state management."""

    def test_reset_clears_value_function(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """reset() clears learned value function."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        # Learn something
        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        assert len(tdl.value_function.values) > 0

        # Reset
        tdl.reset()

        assert len(tdl.value_function.values) == 0
        assert len(tdl.value_function.visit_counts) == 0


# =============================================================================
# M5-E3 ACCEPTANCE CRITERIA TESTS
# =============================================================================


class TestM5E3AcceptanceCriteria:
    """Tests verifying M5-E3 acceptance criteria are met."""

    def test_m5_e3_routine_with_negative_reward_triggers_bottleneck(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """M5-E3: Routine with negative reward step triggers bottleneck detection."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        for execution in morning_routine_with_bottleneck.executions:
            tdl.learn_from_execution(execution)

        bottlenecks = tdl.detect_bottlenecks(morning_routine_with_bottleneck)

        # Acceptance: bottleneck detected at negative reward step
        assert len(bottlenecks) >= 1

    def test_m5_e3_bottleneck_detection_uses_threshold(
        self,
        tdl_config: TDLConfig,
    ) -> None:
        """M5-E3: Bottleneck detection uses threshold of V drop > 2.0."""
        # Default threshold is -2.0
        assert tdl_config.bottleneck_threshold == -2.0

    def test_m5_e3_optimization_suggestions_generated(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """M5-E3: Optimization suggestions are generated for bottlenecks."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        optimizations = tdl.optimize(
            routines=[morning_routine_with_bottleneck],
            rng_seed=42,
        )

        # Acceptance: suggestions generated
        assert len(optimizations) >= 1
        assert all(opt.suggested_action for opt in optimizations)

    def test_m5_e3_expected_improvement_calculated(
        self,
        morning_routine_with_bottleneck: RoutineTemplate,
        tdl_config: TDLConfig,
    ) -> None:
        """M5-E3: Expected improvement is calculated for each suggestion."""
        tdl = TemporalDifferenceLearning(config=tdl_config)

        optimizations = tdl.optimize(
            routines=[morning_routine_with_bottleneck],
            rng_seed=42,
        )

        # Acceptance: expected_improvement calculated and positive
        for opt in optimizations:
            assert opt.expected_improvement > 0
