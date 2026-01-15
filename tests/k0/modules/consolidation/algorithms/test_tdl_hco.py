"""
Tests for TDL-HCO — Temporal Difference Learning for Habit/Cognitive Optimization.

Issue 8.1.11: TDL-HCO Motor Rehearsal for Habits

Tests cover:
- TD(0) learning with gamma=0.9, alpha=0.1
- Value function updates and convergence
- Bottleneck detection (delta_V < -2.0)
- Optimization suggestion generation
- Routine extraction from episodes
- Integration with DreamExplorer
"""

from __future__ import annotations

import random
import time
from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.algorithms.tdl_hco import (
    P03_TDL_BOTTLENECK_THRESHOLD,
    P03_TDL_DISCOUNT_FACTOR,
    P03_TDL_LEARNING_RATE,
    Bottleneck,
    RoutineExecution,
    RoutineStepData,
    RoutineTemplate,
    TDLConfig,
    TDLOptimization,
    TemporalDifferenceLearning,
    ValueFunction,
    extract_routines_from_episodes,
)


# =============================================================================
# HELPER FIXTURES
# =============================================================================


def create_sample_routine_steps():
    """Create sample routine steps."""
    return [
        RoutineStepData(step_id="step_0", step_name="wake_up", step_index=0, success=True, duration_ms=5000),
        RoutineStepData(step_id="step_1", step_name="shower", step_index=1, success=True, duration_ms=15000),
        RoutineStepData(step_id="step_2", step_name="breakfast", step_index=2, success=True, duration_ms=20000),
        RoutineStepData(step_id="step_3", step_name="commute", step_index=3, success=True, duration_ms=30000),
        RoutineStepData(step_id="step_4", step_name="arrive_work", step_index=4, success=True, duration_ms=1000),
    ]


def create_sample_routine_execution():
    """Create sample routine execution."""
    return RoutineExecution(
        execution_id="exec_001",
        routine_id="routine_morning",
        routine_name="Morning Routine",
        steps=create_sample_routine_steps(),
        total_duration_ms=71000,
        completed=True,
        success=True,
    )


def create_sample_routine_template():
    """Create sample routine template with executions."""
    execution = create_sample_routine_execution()
    return RoutineTemplate(
        routine_id="routine_morning",
        routine_name="Morning Routine",
        canonical_steps=["wake_up", "shower", "breakfast", "commute", "arrive_work"],
        execution_count=5,
        avg_duration_ms=71000,
        success_rate=0.9,
        executions=[execution, execution, execution],  # 3 executions
    )


def create_bottleneck_routine_steps():
    """Create routine steps with a bottleneck (step 2 fails often)."""
    return [
        RoutineStepData(step_id="step_0", step_name="prepare", step_index=0, success=True, reward=1.0),
        RoutineStepData(step_id="step_1", step_name="start", step_index=1, success=True, reward=0.5),
        RoutineStepData(step_id="step_2", step_name="difficult_step", step_index=2, success=False, reward=-3.0),
        RoutineStepData(step_id="step_3", step_name="recover", step_index=3, success=True, reward=-0.5),
        RoutineStepData(step_id="step_4", step_name="complete", step_index=4, success=True, reward=1.0),
    ]


# =============================================================================
# TESTS: CONFIGURATION
# =============================================================================


class TestTDLConfig:
    """Tests for TDLConfig dataclass."""

    def test_config_defaults(self):
        """TDLConfig creates with default values per Issue 8.1.11."""
        config = TDLConfig()

        assert config.learning_rate == 0.1  # alpha = 0.1
        assert config.discount_factor == 0.9  # gamma = 0.9
        assert config.bottleneck_threshold == -2.0  # delta_V < -2.0
        assert config.min_routine_length == 3
        assert config.min_routine_occurrences == 3

    def test_config_learning_rate_validation_valid(self):
        """Valid learning_rate values accepted."""
        TDLConfig(learning_rate=0.1)
        TDLConfig(learning_rate=1.0)
        TDLConfig(learning_rate=0.5)

    def test_config_learning_rate_validation_zero(self):
        """learning_rate of 0 raises ValueError."""
        with pytest.raises(ValueError, match="learning_rate"):
            TDLConfig(learning_rate=0.0)

    def test_config_learning_rate_validation_over_one(self):
        """learning_rate > 1 raises ValueError."""
        with pytest.raises(ValueError, match="learning_rate"):
            TDLConfig(learning_rate=1.5)

    def test_config_discount_factor_validation_valid(self):
        """Valid discount_factor values accepted."""
        TDLConfig(discount_factor=0.9)
        TDLConfig(discount_factor=1.0)

    def test_config_discount_factor_validation_zero(self):
        """discount_factor of 0 raises ValueError."""
        with pytest.raises(ValueError, match="discount_factor"):
            TDLConfig(discount_factor=0.0)


# =============================================================================
# TESTS: VALUE FUNCTION
# =============================================================================


class TestValueFunction:
    """Tests for ValueFunction dataclass."""

    def test_value_function_init(self):
        """ValueFunction initializes with empty values."""
        vf = ValueFunction()

        assert vf.values == {}
        assert vf.visit_counts == {}
        assert vf.learning_rate == 0.1
        assert vf.discount_factor == 0.9

    def test_value_function_state_key(self):
        """ValueFunction.get_state_key generates deterministic keys."""
        vf = ValueFunction()

        key1 = vf.get_state_key("routine_A", 0, "step_1")
        key2 = vf.get_state_key("routine_A", 0, "step_1")
        key3 = vf.get_state_key("routine_A", 1, "step_1")

        assert key1 == key2  # Same inputs = same key
        assert key1 != key3  # Different step_index = different key
        assert "routine_A" in key1
        assert "step_1" in key1

    def test_value_function_unknown_state(self):
        """ValueFunction.get_value returns 0 for unknown states."""
        vf = ValueFunction()

        value = vf.get_value("unknown_state")

        assert value == 0.0

    def test_value_function_td_update(self):
        """
        ValueFunction.td_update implements TD(0) correctly.

        TD(0) update: V(s) <- V(s) + alpha * [r + gamma * V(s') - V(s)]

        With alpha=0.1, gamma=0.9:
        Initial: V(s) = 0, V(s') = 0
        Update: V(s) = 0 + 0.1 * (1.0 + 0.9 * 0 - 0) = 0.1
        """
        vf = ValueFunction(learning_rate=0.1, discount_factor=0.9)

        # First update with reward=1.0
        td_error = vf.td_update(state="s1", reward=1.0, next_state="s2")

        # TD error = r + gamma*V(s') - V(s) = 1.0 + 0.9*0 - 0 = 1.0
        assert td_error == 1.0

        # New value = 0 + 0.1 * 1.0 = 0.1
        assert vf.get_value("s1") == 0.1
        assert vf.get_visit_count("s1") == 1

    def test_value_function_td_update_terminal(self):
        """ValueFunction.td_update handles terminal states (next_state=None)."""
        vf = ValueFunction(learning_rate=0.1, discount_factor=0.9)

        # Terminal state: next_state is None
        td_error = vf.td_update(state="terminal", reward=5.0, next_state=None)

        # TD error = r + gamma*V(None) - V(s) = 5.0 + 0 - 0 = 5.0
        assert td_error == 5.0

        # New value = 0 + 0.1 * 5.0 = 0.5
        assert vf.get_value("terminal") == 0.5

    def test_value_function_gradient(self):
        """ValueFunction.compute_value_gradient calculates delta_V correctly."""
        vf = ValueFunction()
        vf.values["s1"] = 3.0
        vf.values["s2"] = 1.0  # Gradient is negative (bottleneck)

        gradient = vf.compute_value_gradient("s1", "s2")

        # delta_V = V(s2) - V(s1) = 1.0 - 3.0 = -2.0
        assert gradient == -2.0


# =============================================================================
# TESTS: ROUTINE DATA MODELS
# =============================================================================


class TestRoutineDataModels:
    """Tests for routine data models."""

    def test_routine_step_data(self):
        """RoutineStepData creates with expected fields."""
        step = RoutineStepData(
            step_id="step_1",
            step_name="do_something",
            step_index=2,
            duration_ms=5000,
            success=True,
            reward=1.5,
        )

        assert step.step_id == "step_1"
        assert step.step_name == "do_something"
        assert step.step_index == 2
        assert step.duration_ms == 5000
        assert step.success is True
        assert step.reward == 1.5

    def test_routine_execution(self):
        """RoutineExecution tracks routine execution."""
        steps = create_sample_routine_steps()
        execution = RoutineExecution(
            execution_id="exec_123",
            routine_id="routine_test",
            routine_name="Test Routine",
            steps=steps,
            total_duration_ms=60000,
            completed=True,
            success=True,
        )

        assert execution.execution_id == "exec_123"
        assert execution.routine_id == "routine_test"
        assert len(execution.steps) == 5
        assert execution.total_duration_ms == 60000

    def test_routine_template(self):
        """RoutineTemplate aggregates executions."""
        template = RoutineTemplate(
            routine_id="routine_daily",
            routine_name="Daily Routine",
            canonical_steps=["step_a", "step_b", "step_c"],
            execution_count=10,
            avg_duration_ms=30000,
            success_rate=0.85,
        )

        assert template.routine_id == "routine_daily"
        assert len(template.canonical_steps) == 3
        assert template.execution_count == 10
        assert template.success_rate == 0.85


# =============================================================================
# TESTS: BOTTLENECK DETECTION
# =============================================================================


class TestBottleneckDetection:
    """Tests for bottleneck detection."""

    def test_bottleneck_dataclass(self):
        """Bottleneck dataclass captures bottleneck info."""
        bottleneck = Bottleneck(
            routine_id="routine_1",
            routine_name="Morning Routine",
            step_index=2,
            step_name="shower",
            value_drop=-3.5,
            current_value=2.0,
            next_value=-1.5,
            severity=3.5,
        )

        assert bottleneck.routine_id == "routine_1"
        assert bottleneck.step_index == 2
        assert bottleneck.value_drop == -3.5
        assert bottleneck.severity == 3.5

    def test_detect_bottlenecks_finds_negative_gradients(self):
        """TemporalDifferenceLearning.detect_bottlenecks finds negative gradients."""
        sample_routine_template = create_sample_routine_template()
        tdl = TemporalDifferenceLearning(TDLConfig(bottleneck_threshold=-2.0))

        # Manually set value function to create bottleneck
        steps = sample_routine_template.canonical_steps
        for i, step in enumerate(steps):
            state_key = tdl.value_function.get_state_key(
                sample_routine_template.routine_id, i, step
            )
            if i == 2:  # Create bottleneck at step 2
                tdl.value_function.values[state_key] = 3.0
            elif i == 3:  # Value drops sharply after step 2
                tdl.value_function.values[state_key] = 0.5
            else:
                tdl.value_function.values[state_key] = 2.0

        bottlenecks = tdl.detect_bottlenecks(sample_routine_template)

        # Should detect bottleneck at step 2 (gradient = 0.5 - 3.0 = -2.5 < -2.0)
        assert len(bottlenecks) >= 1
        assert bottlenecks[0].step_index == 2
        assert bottlenecks[0].value_drop < -2.0

    def test_detect_bottlenecks_returns_empty_when_no_bottlenecks(self):
        """detect_bottlenecks returns empty list when no bottlenecks exist."""
        sample_routine_template = create_sample_routine_template()
        tdl = TemporalDifferenceLearning(TDLConfig(bottleneck_threshold=-2.0))

        # Set uniform positive gradient (no bottlenecks)
        steps = sample_routine_template.canonical_steps
        for i, step in enumerate(steps):
            state_key = tdl.value_function.get_state_key(
                sample_routine_template.routine_id, i, step
            )
            tdl.value_function.values[state_key] = float(i)  # Increasing values

        bottlenecks = tdl.detect_bottlenecks(sample_routine_template)

        assert len(bottlenecks) == 0

    def test_detect_bottlenecks_sorted_by_severity(self):
        """detect_bottlenecks sorts by severity descending."""
        tdl = TemporalDifferenceLearning(TDLConfig(bottleneck_threshold=-2.0))

        template = RoutineTemplate(
            routine_id="routine_multi",
            routine_name="Multi Bottleneck",
            canonical_steps=["s0", "s1", "s2", "s3", "s4"],
            execution_count=5,
        )

        # Create two bottlenecks with different severities
        tdl.value_function.values["routine_multi:0:s0"] = 2.0
        tdl.value_function.values["routine_multi:1:s1"] = -1.0  # Drop of 3.0 (severe)
        tdl.value_function.values["routine_multi:2:s2"] = -3.5  # Drop of 2.5 (less severe)
        tdl.value_function.values["routine_multi:3:s3"] = -5.0
        tdl.value_function.values["routine_multi:4:s4"] = -5.0

        bottlenecks = tdl.detect_bottlenecks(template)

        # Should have 2 bottlenecks, sorted by severity
        assert len(bottlenecks) == 2
        assert bottlenecks[0].severity >= bottlenecks[1].severity  # Most severe first


# =============================================================================
# TESTS: TD LEARNING FROM EXECUTIONS
# =============================================================================


class TestTDLearning:
    """Tests for TD learning from executions."""

    def test_learn_from_execution_updates_value_function(self):
        """learn_from_execution updates value function."""
        execution = create_sample_routine_execution()
        tdl = TemporalDifferenceLearning(TDLConfig(seed=42))

        td_errors = tdl.learn_from_execution(execution)

        assert len(td_errors) == 5  # One per step
        assert all(isinstance(e, float) for e in td_errors)

        # Check that value function was updated
        for i, step in enumerate(execution.steps):
            state_key = tdl.value_function.get_state_key(
                execution.routine_id, i, step.step_name
            )
            assert tdl.value_function.get_visit_count(state_key) == 1

    def test_learn_from_execution_handles_failed_steps(self):
        """learn_from_execution handles failed steps with negative rewards."""
        bottleneck_steps = create_bottleneck_routine_steps()
        tdl = TemporalDifferenceLearning()

        execution = RoutineExecution(
            execution_id="exec_fail",
            routine_id="routine_fail",
            routine_name="Failing Routine",
            steps=bottleneck_steps,
            total_duration_ms=50000,
        )

        tdl.learn_from_execution(execution)

        # The failed step should have lower value
        failed_key = tdl.value_function.get_state_key("routine_fail", 2, "difficult_step")
        success_key = tdl.value_function.get_state_key("routine_fail", 0, "prepare")

        # After learning, failed step value should be lower
        assert tdl.value_function.get_value(failed_key) < tdl.value_function.get_value(success_key)


# =============================================================================
# TESTS: OPTIMIZATION SUGGESTIONS
# =============================================================================


class TestOptimizationSuggestions:
    """Tests for optimization suggestion generation."""

    def test_generate_suggestions_creates_optimization(self):
        """generate_suggestions creates TDLOptimization for bottlenecks."""
        tdl = TemporalDifferenceLearning()
        rng = random.Random(42)

        bottleneck = Bottleneck(
            routine_id="routine_test",
            routine_name="Test Routine",
            step_index=2,
            step_name="difficult_task",
            value_drop=-3.5,
            current_value=2.0,
            next_value=-1.5,
            severity=3.5,
        )

        template = RoutineTemplate(
            routine_id="routine_test",
            routine_name="Test Routine",
            canonical_steps=["step_a", "step_b", "difficult_task", "step_d"],
            execution_count=10,
        )

        suggestions = tdl.generate_suggestions([bottleneck], template, rng)

        assert len(suggestions) == 1
        assert isinstance(suggestions[0], TDLOptimization)
        assert suggestions[0].bottleneck == bottleneck
        assert suggestions[0].expected_improvement > 0
        assert 0 < suggestions[0].confidence <= 1.0
        assert len(suggestions[0].suggested_action) > 0

    def test_tdl_optimization_conversion_to_model(self):
        """TDLOptimization.to_routine_optimization converts to model."""
        from k0.modules.consolidation.dream.models import RoutineOptimization

        bottleneck = Bottleneck(
            routine_id="routine_1",
            routine_name="Test Routine",
            step_index=1,
            step_name="slow_step",
            value_drop=-2.5,
            current_value=1.0,
            next_value=-1.5,
            severity=2.5,
        )

        optimization = TDLOptimization(
            optimization_id="OPT001",
            routine_id="routine_1",
            routine_name="Test Routine",
            bottleneck=bottleneck,
            suggested_action="Speed up slow_step",
            expected_improvement=1.2,
            confidence=0.8,
            rationale="This step is slow",
            created_at_ms=int(time.time() * 1000),
        )

        result = optimization.to_routine_optimization()

        assert isinstance(result, RoutineOptimization)
        assert result.routine_id == "routine_1"
        assert result.routine_name == "Test Routine"
        assert result.bottleneck_step == "slow_step"
        assert result.bottleneck_position == 1
        assert result.value_drop == -2.5
        assert result.expected_improvement == 1.2
        assert result.confidence == 0.8


# =============================================================================
# TESTS: MAIN OPTIMIZE ENTRY POINT
# =============================================================================


class TestOptimizeEntryPoint:
    """Tests for the main optimize entry point."""

    def test_optimize_returns_empty_list_for_empty_routines(self):
        """optimize returns empty list for empty routines."""
        tdl = TemporalDifferenceLearning()

        result = tdl.optimize(routines=[], rng_seed=42)

        assert result == []

    def test_optimize_filters_short_routines(self):
        """optimize filters routines by min_routine_length."""
        tdl = TemporalDifferenceLearning(TDLConfig(min_routine_length=5))

        short_routine = RoutineTemplate(
            routine_id="short",
            routine_name="Short Routine",
            canonical_steps=["a", "b"],  # Only 2 steps, below threshold
            execution_count=10,
        )

        result = tdl.optimize(routines=[short_routine], rng_seed=42)

        assert result == []  # Filtered out

    def test_optimize_filters_rare_routines(self):
        """optimize filters routines by min_routine_occurrences."""
        tdl = TemporalDifferenceLearning(TDLConfig(min_routine_occurrences=5))

        rare_routine = RoutineTemplate(
            routine_id="rare",
            routine_name="Rare Routine",
            canonical_steps=["a", "b", "c", "d", "e"],
            execution_count=2,  # Only 2 occurrences, below threshold
        )

        result = tdl.optimize(routines=[rare_routine], rng_seed=42)

        assert result == []  # Filtered out

    def test_optimize_limits_output_to_max_optimizations(self):
        """optimize limits output to max_optimizations."""
        tdl = TemporalDifferenceLearning(TDLConfig(
            max_optimizations=2,
            min_routine_length=3,
            min_routine_occurrences=1,
            bottleneck_threshold=-0.1,  # Very sensitive threshold
        ))

        # Create routine with alternating good/bad steps
        steps = [RoutineStepData(
            step_id=f"step_{i}",
            step_name=f"step_{i}",
            step_index=i,
            reward=1.0 if i % 2 == 0 else -2.0,
            success=i % 2 == 0,
        ) for i in range(10)]

        execution = RoutineExecution(
            execution_id="exec_1",
            routine_id="routine_many",
            routine_name="Many Bottleneck Routine",
            steps=steps,
            total_duration_ms=100000,
        )

        template = RoutineTemplate(
            routine_id="routine_many",
            routine_name="Many Bottleneck Routine",
            canonical_steps=[f"step_{i}" for i in range(10)],
            execution_count=5,
            executions=[execution],
        )

        result = tdl.optimize(routines=[template], rng_seed=42)

        assert len(result) <= 2  # Respects max_optimizations

    def test_optimize_reset(self):
        """optimize resets value function between calls."""
        tdl = TemporalDifferenceLearning()

        # Learn something
        execution = RoutineExecution(
            execution_id="e1",
            routine_id="r1",
            routine_name="R1",
            steps=[RoutineStepData("s0", "step", 0, reward=1.0)],
        )
        tdl.learn_from_execution(execution)

        # Reset and verify empty
        tdl.reset()

        assert tdl.value_function.values == {}
        assert tdl.value_function.visit_counts == {}


# =============================================================================
# TESTS: ROUTINE EXTRACTION FROM EPISODES
# =============================================================================


class TestRoutineExtraction:
    """Tests for routine extraction from episodes."""

    def test_extract_routines_handles_action_sequence(self):
        """extract_routines_from_episodes handles episodes with action_sequence."""
        # Create mock episodes with action sequences
        episode1 = MagicMock()
        episode1.episode_id = "ep_001"
        episode1.action_sequence = ["open_door", "enter", "sit_down"]
        episode1.start_time_ms = 1000000
        episode1.end_time_ms = 2000000

        episode2 = MagicMock()
        episode2.episode_id = "ep_002"
        episode2.action_sequence = ["open_door", "enter", "sit_down"]
        episode2.start_time_ms = 2000000
        episode2.end_time_ms = 3000000

        episode3 = MagicMock()
        episode3.episode_id = "ep_003"
        episode3.action_sequence = ["open_door", "enter", "sit_down"]
        episode3.start_time_ms = 3000000
        episode3.end_time_ms = 4000000

        routines = extract_routines_from_episodes(
            episodes=[episode1, episode2, episode3],
            min_routine_length=3,
            min_occurrences=2,
        )

        assert len(routines) == 1
        assert routines[0].execution_count == 3
        assert routines[0].canonical_steps == ["open_door", "enter", "sit_down"]

    def test_extract_routines_handles_events(self):
        """extract_routines_from_episodes handles episodes with events."""
        event1 = MagicMock()
        event1.event_type = "START"

        event2 = MagicMock()
        event2.event_type = "PROCESS"

        event3 = MagicMock()
        event3.event_type = "END"

        episode = MagicMock()
        episode.episode_id = "ep_events"
        episode.action_sequence = None
        episode.events = [event1, event2, event3]
        episode.start_time_ms = 1000000
        episode.end_time_ms = 2000000

        routines = extract_routines_from_episodes(
            episodes=[episode, episode, episode],
            min_routine_length=3,
            min_occurrences=2,
        )

        assert len(routines) >= 1

    def test_extract_routines_filters_by_min_length(self):
        """extract_routines_from_episodes filters by min_routine_length."""
        episode = MagicMock()
        episode.episode_id = "ep_short"
        episode.action_sequence = ["a", "b"]  # Only 2 steps
        episode.start_time_ms = 1000000
        episode.end_time_ms = 2000000

        routines = extract_routines_from_episodes(
            episodes=[episode, episode, episode],
            min_routine_length=3,
            min_occurrences=1,
        )

        assert len(routines) == 0  # Filtered out

    def test_extract_routines_filters_by_min_occurrences(self):
        """extract_routines_from_episodes filters by min_occurrences."""
        episode = MagicMock()
        episode.episode_id = "ep_rare"
        episode.action_sequence = ["a", "b", "c"]
        episode.start_time_ms = 1000000
        episode.end_time_ms = 2000000

        routines = extract_routines_from_episodes(
            episodes=[episode],  # Only 1 occurrence
            min_routine_length=3,
            min_occurrences=2,
        )

        assert len(routines) == 0  # Filtered out


# =============================================================================
# TESTS: EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_handles_short_routine_filtered(self):
        """TDL filters short routines below min_routine_length."""
        tdl = TemporalDifferenceLearning(TDLConfig(min_routine_length=3))

        template = RoutineTemplate(
            routine_id="short",
            routine_name="Short Routine",
            canonical_steps=["a", "b"],  # Only 2 steps, below threshold
            execution_count=5,
        )

        # Short routines are filtered out in optimize()
        result = tdl.optimize(routines=[template], rng_seed=42)
        assert result == []  # Filtered out

    def test_handles_rare_executions_filtered(self):
        """TDL filters routines with few occurrences."""
        tdl = TemporalDifferenceLearning(TDLConfig(min_routine_occurrences=5))

        template = RoutineTemplate(
            routine_id="rare",
            routine_name="Rare Routine",
            canonical_steps=["a", "b", "c"],
            execution_count=2,  # Only 2 occurrences, below threshold
            executions=[],
        )

        result = tdl.optimize(routines=[template], rng_seed=42)
        assert result == []  # Filtered out due to low occurrences

    def test_handles_routines_with_all_successful_steps(self):
        """TDL handles routines with all successful steps."""
        tdl = TemporalDifferenceLearning(TDLConfig(min_routine_occurrences=1))

        steps = [RoutineStepData(
            step_id=f"s{i}",
            step_name=f"step_{i}",
            step_index=i,
            success=True,
            reward=1.0,
        ) for i in range(5)]

        execution = RoutineExecution(
            execution_id="e1",
            routine_id="success",
            routine_name="All Success",
            steps=steps,
        )

        template = RoutineTemplate(
            routine_id="success",
            routine_name="All Success",
            canonical_steps=[f"step_{i}" for i in range(5)],
            execution_count=1,
            executions=[execution],
        )

        result = tdl.optimize(routines=[template], rng_seed=42)

        # Just verify it runs without error
        assert isinstance(result, list)


# =============================================================================
# TESTS: INTEGRATION WITH DREAM EXPLORER
# =============================================================================


class TestDreamExplorerIntegration:
    """Tests for integration with DreamExplorer."""

    @pytest.mark.asyncio
    async def test_tdl_hco_integration(self):
        """TDL-HCO runs within DreamExplorer orchestration."""
        from k0.modules.consolidation.dream.config import DreamConfig
        from k0.modules.consolidation.dream.dream_explorer import DreamExplorer
        from k0.modules.consolidation.dream.models import DreamExplorerInput

        # Create mock episode with action sequence
        episode = MagicMock()
        episode.episode_id = "ep_integration"
        episode.action_sequence = ["step_1", "step_2", "step_3", "step_4"]
        episode.start_time_ms = 1000000
        episode.end_time_ms = 2000000
        episode.summary = None
        episode.events = None
        episode.entity_ids = []
        episode.salience_score = 0.5

        config = DreamConfig(
            seed="test_seed",
            max_routine_optimizations=5,
            tdl_learning_rate=0.1,
            tdl_discount_factor=0.9,
        )
        explorer = DreamExplorer(config)

        input_data = DreamExplorerInput(
            cycle_id="cycle_001",
            tenant_id="tenant_1",
            space_id="space_1",
            recent_episodes=[episode] * 5,
            kg_entities=[],
            kg_edges=[],
        )

        output = await explorer.explore(input_data)

        assert output is not None
        assert isinstance(output.routine_optimizations, list)


# =============================================================================
# TESTS: CONSTANTS VERIFICATION
# =============================================================================


class TestConstants:
    """Tests for TDL-HCO constants per Issue 8.1.11."""

    def test_learning_rate_constant(self):
        """Learning rate constant is 0.1 per Issue 8.1.11."""
        assert P03_TDL_LEARNING_RATE == 0.1

    def test_discount_factor_constant(self):
        """Discount factor constant is 0.9 per Issue 8.1.11."""
        assert P03_TDL_DISCOUNT_FACTOR == 0.9

    def test_bottleneck_threshold_constant(self):
        """Bottleneck threshold is -2.0 per Issue 8.1.11."""
        assert P03_TDL_BOTTLENECK_THRESHOLD == -2.0
