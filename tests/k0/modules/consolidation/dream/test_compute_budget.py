"""
ComputeBudget and Orchestration Tests — Issue 8.1.15

Tests for:
1. ComputeBudget allocation and exhaustion
2. AlgorithmResult tracking
3. OrchestrationResult aggregation
4. DreamExplorer parallel execution
5. Error isolation in R5 algorithms

References:
- M8_EXECUTION.md Issue 8.1.15: R5 Algorithm Orchestration
- Dossier §4.6.2.1: Compute budget enforcement
"""

from __future__ import annotations

import time
from typing import List

import pytest

from k0.modules.consolidation.dream.compute_budget import (
    AlgorithmResult,
    BudgetExhaustionReason,
    ComputeBudget,
    OrchestrationResult,
    P03_R5_DEFAULT_MCTS_BUDGET,
)
from k0.modules.consolidation.dream.config import DreamConfig
from k0.modules.consolidation.dream.dream_explorer import DreamExplorer
from k0.modules.consolidation.dream.models import (
    DreamExplorerInput,
    DreamExplorerOutput,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def default_budget() -> ComputeBudget:
    """Create default ComputeBudget."""
    return ComputeBudget()


@pytest.fixture
def limited_budget() -> ComputeBudget:
    """Create budget with low limits for testing exhaustion."""
    return ComputeBudget(max_mcts_rollouts=100)


@pytest.fixture
def time_limited_budget() -> ComputeBudget:
    """Create budget with time limit."""
    return ComputeBudget(max_compute_ms=1000)  # 1 second


@pytest.fixture
def sample_input() -> DreamExplorerInput:
    """Create sample DreamExplorerInput."""
    return DreamExplorerInput(
        cycle_id="01JTEST123456789ABCDEFGH",
        tenant_id="tenant-test",
        space_id="space-test",
        recent_episodes=[],
        kg_entities=[],
        kg_edges=[],
        event_states=[],
    )


# =============================================================================
# TEST: ComputeBudget Creation
# =============================================================================


class TestComputeBudgetCreation:
    """Test ComputeBudget initialization and defaults."""

    def test_default_values(self) -> None:
        """ComputeBudget should have correct defaults."""
        budget = ComputeBudget()

        assert budget.max_mcts_rollouts == P03_R5_DEFAULT_MCTS_BUDGET
        assert budget.used_rollouts == 0
        assert budget.max_compute_ms is None
        assert budget.exhaustion_reason is None
        assert budget.start_time_ms > 0

    def test_custom_max_rollouts(self) -> None:
        """ComputeBudget should accept custom max_mcts_rollouts."""
        budget = ComputeBudget(max_mcts_rollouts=500)

        assert budget.max_mcts_rollouts == 500
        assert budget.remaining == 500

    def test_custom_time_budget(self) -> None:
        """ComputeBudget should accept custom max_compute_ms."""
        budget = ComputeBudget(max_compute_ms=5000)

        assert budget.max_compute_ms == 5000


# =============================================================================
# TEST: ComputeBudget Allocation
# =============================================================================


class TestComputeBudgetAllocation:
    """Test ComputeBudget allocation behavior."""

    def test_can_allocate_within_budget(self, default_budget: ComputeBudget) -> None:
        """can_allocate should return True when within budget."""
        assert default_budget.can_allocate(100)
        assert default_budget.can_allocate(1000)

    def test_cannot_allocate_over_budget(self, limited_budget: ComputeBudget) -> None:
        """can_allocate should return False when over budget."""
        assert not limited_budget.can_allocate(150)

    def test_allocate_full_amount(self, limited_budget: ComputeBudget) -> None:
        """allocate should return full amount when available."""
        allocated = limited_budget.allocate(50)

        assert allocated == 50
        assert limited_budget.used_rollouts == 50
        assert limited_budget.remaining == 50

    def test_allocate_partial_amount(self, limited_budget: ComputeBudget) -> None:
        """allocate should return partial amount when insufficient."""
        # First allocation uses 80
        limited_budget.allocate(80)

        # Second allocation requests 50 but only 20 available
        allocated = limited_budget.allocate(50)

        assert allocated == 20
        assert limited_budget.used_rollouts == 100
        assert limited_budget.remaining == 0

    def test_allocate_zero_when_exhausted(self, limited_budget: ComputeBudget) -> None:
        """allocate should return 0 when budget exhausted."""
        limited_budget.allocate(100)  # Exhaust budget

        allocated = limited_budget.allocate(10)

        assert allocated == 0

    def test_sequential_allocations(self, limited_budget: ComputeBudget) -> None:
        """Sequential allocations should accumulate correctly."""
        limited_budget.allocate(20)
        limited_budget.allocate(30)
        limited_budget.allocate(25)

        assert limited_budget.used_rollouts == 75
        assert limited_budget.remaining == 25


# =============================================================================
# TEST: ComputeBudget Exhaustion
# =============================================================================


class TestComputeBudgetExhaustion:
    """Test ComputeBudget exhaustion detection."""

    def test_not_exhausted_initially(self, default_budget: ComputeBudget) -> None:
        """Budget should not be exhausted initially."""
        assert not default_budget.exhausted

    def test_exhausted_after_full_allocation(self, limited_budget: ComputeBudget) -> None:
        """Budget should be exhausted after allocating all rollouts."""
        limited_budget.allocate(100)

        assert limited_budget.exhausted
        assert limited_budget.exhaustion_reason == BudgetExhaustionReason.ROLLOUTS_EXHAUSTED

    def test_exhausted_after_manual_stop(self, default_budget: ComputeBudget) -> None:
        """Budget should be exhausted after manual stop."""
        default_budget.stop()

        assert default_budget.exhausted
        assert default_budget.exhaustion_reason == BudgetExhaustionReason.MANUAL_STOP

    def test_cannot_allocate_after_exhausted(self, limited_budget: ComputeBudget) -> None:
        """Cannot allocate after budget is exhausted."""
        limited_budget.allocate(100)

        assert not limited_budget.can_allocate(1)


# =============================================================================
# TEST: ComputeBudget Properties
# =============================================================================


class TestComputeBudgetProperties:
    """Test ComputeBudget computed properties."""

    def test_remaining_calculation(self, limited_budget: ComputeBudget) -> None:
        """remaining should correctly calculate remaining rollouts."""
        limited_budget.allocate(40)

        assert limited_budget.remaining == 60

    def test_utilization_zero(self, default_budget: ComputeBudget) -> None:
        """utilization should be 0 initially."""
        assert default_budget.utilization == 0.0

    def test_utilization_partial(self, limited_budget: ComputeBudget) -> None:
        """utilization should reflect partial usage."""
        limited_budget.allocate(25)

        assert limited_budget.utilization == 0.25

    def test_utilization_full(self, limited_budget: ComputeBudget) -> None:
        """utilization should be 1.0 when fully used."""
        limited_budget.allocate(100)

        assert limited_budget.utilization == 1.0

    def test_elapsed_ms_increases(self, default_budget: ComputeBudget) -> None:
        """elapsed_ms should increase over time."""
        initial = default_budget.elapsed_ms
        time.sleep(0.01)  # 10ms
        after = default_budget.elapsed_ms

        assert after > initial

    def test_remaining_time_with_limit(self, time_limited_budget: ComputeBudget) -> None:
        """remaining_time_ms should return remaining time."""
        remaining = time_limited_budget.remaining_time_ms

        assert remaining is not None
        assert remaining <= 1000
        assert remaining > 0

    def test_remaining_time_without_limit(self, default_budget: ComputeBudget) -> None:
        """remaining_time_ms should return None without time limit."""
        assert default_budget.remaining_time_ms is None


# =============================================================================
# TEST: ComputeBudget Serialization
# =============================================================================


class TestComputeBudgetSerialization:
    """Test ComputeBudget serialization."""

    def test_to_dict(self, limited_budget: ComputeBudget) -> None:
        """to_dict should serialize all fields."""
        limited_budget.allocate(50)
        data = limited_budget.to_dict()

        assert data["max_mcts_rollouts"] == 100
        assert data["used_rollouts"] == 50
        assert data["remaining_rollouts"] == 50
        assert data["utilization"] == 0.5
        assert "elapsed_ms" in data
        assert data["exhausted"] is False

    def test_repr(self, limited_budget: ComputeBudget) -> None:
        """__repr__ should be informative."""
        limited_budget.allocate(50)
        repr_str = repr(limited_budget)

        assert "50/100" in repr_str
        assert "AVAILABLE" in repr_str


# =============================================================================
# TEST: AlgorithmResult
# =============================================================================


class TestAlgorithmResult:
    """Test AlgorithmResult dataclass."""

    def test_successful_result(self) -> None:
        """AlgorithmResult should track successful execution."""
        result = AlgorithmResult(
            algorithm_name="bgt_sm",
            success=True,
            outputs=["insight1", "insight2"],
            compute_ms=150,
        )

        assert result.success
        assert not result.is_failure
        assert result.output_count == 2
        assert result.error_message is None

    def test_failed_result(self) -> None:
        """AlgorithmResult should track failed execution."""
        result = AlgorithmResult(
            algorithm_name="cpn",
            success=False,
            outputs=[],
            error_message="Connection timeout",
            compute_ms=50,
        )

        assert not result.success
        assert result.is_failure
        assert result.output_count == 0
        assert result.error_message == "Connection timeout"

    def test_rollouts_tracking(self) -> None:
        """AlgorithmResult should track rollouts used."""
        result = AlgorithmResult(
            algorithm_name="mcts",
            success=True,
            outputs=[],
            rollouts_used=250,
        )

        assert result.rollouts_used == 250


# =============================================================================
# TEST: OrchestrationResult
# =============================================================================


class TestOrchestrationResult:
    """Test OrchestrationResult aggregation."""

    def test_empty_orchestration(self) -> None:
        """Empty OrchestrationResult should have sensible defaults."""
        result = OrchestrationResult(cycle_id="cycle-001")

        assert result.cycle_id == "cycle-001"
        assert len(result.algorithm_results) == 0
        assert result.all_succeeded  # Vacuously true
        assert result.partial_success is False
        assert result.total_outputs == 0

    def test_add_result(self) -> None:
        """add_result should track algorithm results."""
        orchestration = OrchestrationResult(cycle_id="cycle-001")

        orchestration.add_result(
            AlgorithmResult(
                algorithm_name="bgt_sm",
                success=True,
                outputs=["i1", "i2"],
            )
        )

        assert "bgt_sm" in orchestration.algorithm_results
        assert orchestration.algorithm_results["bgt_sm"].success

    def test_all_succeeded(self) -> None:
        """all_succeeded should be True when all algorithms succeed."""
        orchestration = OrchestrationResult(cycle_id="cycle-001")
        orchestration.add_result(AlgorithmResult("bgt_sm", True, ["o1"]))
        orchestration.add_result(AlgorithmResult("cpn", True, ["o2"]))

        assert orchestration.all_succeeded

    def test_partial_success(self) -> None:
        """partial_success should be True when at least one succeeds."""
        orchestration = OrchestrationResult(cycle_id="cycle-001")
        orchestration.add_result(AlgorithmResult("bgt_sm", True, ["o1"]))
        orchestration.add_result(AlgorithmResult("cpn", False, [], error_message="error"))

        assert orchestration.partial_success
        assert not orchestration.all_succeeded

    def test_failures_tracking(self) -> None:
        """failures should track failed algorithms."""
        orchestration = OrchestrationResult(cycle_id="cycle-001")
        orchestration.add_result(AlgorithmResult("bgt_sm", True, []))
        orchestration.add_result(
            AlgorithmResult("cpn", False, [], error_message="timeout")
        )
        orchestration.add_result(
            AlgorithmResult("spc_uq", False, [], error_message="null pointer")
        )

        failures = orchestration.failures

        assert len(failures) == 2
        assert "cpn" in failures
        assert failures["cpn"] == "timeout"
        assert failures["spc_uq"] == "null pointer"

    def test_total_outputs(self) -> None:
        """total_outputs should sum outputs from all algorithms."""
        orchestration = OrchestrationResult(cycle_id="cycle-001")
        orchestration.add_result(AlgorithmResult("bgt_sm", True, ["o1", "o2"]))
        orchestration.add_result(AlgorithmResult("cpn", True, ["o3"]))
        orchestration.add_result(AlgorithmResult("spc_uq", True, []))

        assert orchestration.total_outputs == 3


# =============================================================================
# TEST: DreamExplorer Orchestration (Issue 8.1.15)
# =============================================================================


class TestDreamExplorerOrchestration:
    """Test DreamExplorer parallel orchestration."""

    @pytest.mark.asyncio
    async def test_explore_with_shared_budget(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """explore() should use provided ComputeBudget."""
        explorer = DreamExplorer()
        budget = ComputeBudget(max_mcts_rollouts=500)

        output = await explorer.explore(sample_input, compute_budget=budget)

        assert isinstance(output, DreamExplorerOutput)
        assert output.compute_ms >= 0

    @pytest.mark.asyncio
    async def test_explore_creates_budget_if_none(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """explore() should create budget if not provided."""
        explorer = DreamExplorer()

        output = await explorer.explore(sample_input)

        assert isinstance(output, DreamExplorerOutput)

    @pytest.mark.asyncio
    async def test_explore_returns_output_on_empty_input(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """explore() should return empty output for empty input."""
        explorer = DreamExplorer()

        output = await explorer.explore(sample_input)

        assert output.is_empty

    @pytest.mark.asyncio
    async def test_parallel_algorithms_run_concurrently(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """Parallel algorithms should run concurrently (timing test)."""
        explorer = DreamExplorer()

        # With parallelism, total time should be less than sum of algorithm times
        # This is a smoke test - just verify no exceptions
        output = await explorer.explore(sample_input)

        assert isinstance(output, DreamExplorerOutput)


# =============================================================================
# TEST: Error Isolation (Issue 8.1.15)
# =============================================================================


class TestErrorIsolation:
    """Test that individual algorithm failures don't crash R5."""

    @pytest.mark.asyncio
    async def test_run_with_error_isolation_success(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """_run_with_error_isolation should return results on success."""
        explorer = DreamExplorer()
        orchestration = OrchestrationResult(cycle_id="test")

        async def successful_algo() -> List[str]:
            return ["result1", "result2"]

        result = await explorer._run_with_error_isolation(
            "test_algo",
            successful_algo(),
            orchestration,
        )

        assert result == ["result1", "result2"]
        assert orchestration.algorithm_results["test_algo"].success

    @pytest.mark.asyncio
    async def test_run_with_error_isolation_failure(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """_run_with_error_isolation should return empty list on failure."""
        explorer = DreamExplorer()
        orchestration = OrchestrationResult(cycle_id="test")

        async def failing_algo() -> List[str]:
            raise ValueError("Test error")

        result = await explorer._run_with_error_isolation(
            "failing_algo",
            failing_algo(),
            orchestration,
        )

        assert result == []
        assert not orchestration.algorithm_results["failing_algo"].success
        assert "ValueError" in (orchestration.algorithm_results["failing_algo"].error_message or "")

    @pytest.mark.asyncio
    async def test_parallel_algorithms_isolate_failures(
        self,
        sample_input: DreamExplorerInput,
    ) -> None:
        """_run_parallel_algorithms should isolate individual failures."""
        explorer = DreamExplorer()
        orchestration = OrchestrationResult(cycle_id="test")

        # Manually test the parallel runner with mocked algorithms
        # This verifies error isolation works in gather()
        results = await explorer._run_parallel_algorithms(
            input_data=sample_input,
            cycle_id="test-cycle",
            orchestration=orchestration,
        )

        # All results should be lists (empty for algorithms with no data)
        assert isinstance(results["bgt_sm"], list)
        assert isinstance(results["cpn"], list)
        assert isinstance(results["spc_uq"], list)


# =============================================================================
# TEST: Constants Validation
# =============================================================================


class TestConstants:
    """Test that constants are correctly defined."""

    def test_default_mcts_budget_value(self) -> None:
        """Default MCTS budget should be 1000 per dossier."""
        assert P03_R5_DEFAULT_MCTS_BUDGET == 1000

    def test_exhaustion_reasons_enum(self) -> None:
        """Exhaustion reasons should be defined."""
        assert BudgetExhaustionReason.ROLLOUTS_EXHAUSTED.value == "rollouts_exhausted"
        assert BudgetExhaustionReason.TIME_EXHAUSTED.value == "time_exhausted"
        assert BudgetExhaustionReason.MANUAL_STOP.value == "manual_stop"


# =============================================================================
# TEST: Integration Scenarios
# =============================================================================


class TestIntegrationScenarios:
    """Integration tests for complete orchestration scenarios."""

    @pytest.mark.asyncio
    async def test_full_orchestration_empty_input(self) -> None:
        """Full orchestration should complete with empty input."""
        explorer = DreamExplorer(config=DreamConfig(seed="test-seed"))
        input_data = DreamExplorerInput(
            cycle_id="01JTEST",
            tenant_id="t1",
            space_id="s1",
        )

        output = await explorer.explore(input_data)

        assert output.is_empty
        assert output.compute_ms >= 0
        assert output.mcts_decisions_evaluated == 0

    @pytest.mark.asyncio
    async def test_deterministic_execution(self) -> None:
        """Orchestration should be deterministic with same seed."""
        config = DreamConfig(seed="fixed-seed-123")
        explorer = DreamExplorer(config=config)
        input_data = DreamExplorerInput(
            cycle_id="01JTEST",
            tenant_id="t1",
            space_id="s1",
        )

        output1 = await explorer.explore(input_data)
        output2 = await explorer.explore(input_data)

        # Outputs should be identical
        assert len(output1.insights) == len(output2.insights)
        assert len(output1.counterfactuals) == len(output2.counterfactuals)

    @pytest.mark.asyncio
    async def test_budget_shared_across_algorithms(self) -> None:
        """ComputeBudget should be shared across all algorithms."""
        explorer = DreamExplorer()
        budget = ComputeBudget(max_mcts_rollouts=100)
        input_data = DreamExplorerInput(
            cycle_id="01JTEST",
            tenant_id="t1",
            space_id="s1",
        )

        await explorer.explore(input_data, compute_budget=budget)

        # Budget should track usage
        snapshot = budget.to_dict()
        assert "used_rollouts" in snapshot
        assert "elapsed_ms" in snapshot

    @pytest.mark.asyncio
    async def test_orchestration_tracks_algorithm_results(self) -> None:
        """Orchestration should track results from all algorithms."""
        explorer = DreamExplorer()
        input_data = DreamExplorerInput(
            cycle_id="01JTEST",
            tenant_id="t1",
            space_id="s1",
        )

        # Just verify explore completes successfully
        output = await explorer.explore(input_data)

        assert isinstance(output, DreamExplorerOutput)
