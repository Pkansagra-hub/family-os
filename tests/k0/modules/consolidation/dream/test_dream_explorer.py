"""
DreamExplorer Unit Tests — Issue 8.1.3

Test Categories:
1. DreamConfig validation and creation
2. DreamConfig.derive_seed determinism
3. DreamExplorer.explore() basic execution
4. Output ranking and limiting
5. Model creation and validation
6. Deterministic execution with same seed

References:
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- Dossier section 4.6: R5 Dream-Like Exploration (REM)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from k0.modules.consolidation.dream.config import DreamConfig
from k0.modules.consolidation.dream.dream_explorer import DreamExplorer
from k0.modules.consolidation.dream.models import (
    CounterfactualScenario,
    DreamExplorerInput,
    DreamExplorerOutput,
    Insight,
    InsightType,
    ProspectiveMemory,
    RoutineOptimization,
    ScenarioType,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def default_config() -> DreamConfig:
    """Create default DreamConfig."""
    return DreamConfig()


@pytest.fixture
def custom_config() -> DreamConfig:
    """Create custom DreamConfig for testing."""
    return DreamConfig(
        depth=5,
        creativity=0.8,
        seed="test-seed-123",
        max_insights=5,
        max_counterfactuals=3,
        min_novelty_score=0.5,
        min_confidence=0.6,
    )


@pytest.fixture
def sample_input() -> DreamExplorerInput:
    """Create sample input for DreamExplorer."""
    return DreamExplorerInput(
        cycle_id="01JTEST123456789ABCDEFGH",
        tenant_id="tenant-test",
        space_id="space-test",
        recent_episodes=[],
        kg_entities=[],
        kg_edges=[],
        event_states=[],
    )


@pytest.fixture
def explorer(default_config: DreamConfig) -> DreamExplorer:
    """Create DreamExplorer with default config."""
    return DreamExplorer(config=default_config)


# =============================================================================
# TEST: DreamConfig Creation and Validation
# =============================================================================


class TestDreamConfigCreation:
    """Test DreamConfig dataclass creation and validation."""

    def test_default_values(self) -> None:
        """DreamConfig should have sensible defaults per Issue 8.1.10."""
        config = DreamConfig()

        assert config.depth == 3
        assert config.creativity == 0.5
        assert config.seed is None
        assert config.max_insights == 10
        assert config.max_counterfactuals == 5
        # Issue 8.1.10 thresholds
        assert config.min_novelty_score == 0.5
        assert config.min_confidence == 0.5
        assert config.semantic_distance_threshold == 0.7
        assert config.pmi_threshold == 3.0
        assert config.serendipity_threshold == 0.6

    def test_custom_values(self, custom_config: DreamConfig) -> None:
        """DreamConfig should accept custom values."""
        assert custom_config.depth == 5
        assert custom_config.creativity == 0.8
        assert custom_config.seed == "test-seed-123"
        assert custom_config.max_insights == 5
        assert custom_config.max_counterfactuals == 3

    def test_invalid_depth_raises(self) -> None:
        """DreamConfig should reject depth < 1."""
        with pytest.raises(ValueError, match="depth must be at least 1"):
            DreamConfig(depth=0)

    def test_invalid_creativity_raises(self) -> None:
        """DreamConfig should reject creativity outside [0, 1]."""
        with pytest.raises(ValueError, match="creativity must be between 0 and 1"):
            DreamConfig(creativity=1.5)

        with pytest.raises(ValueError, match="creativity must be between 0 and 1"):
            DreamConfig(creativity=-0.1)

    def test_invalid_max_insights_raises(self) -> None:
        """DreamConfig should reject negative max_insights."""
        with pytest.raises(ValueError, match="max_insights must be non-negative"):
            DreamConfig(max_insights=-1)

    def test_invalid_novelty_score_raises(self) -> None:
        """DreamConfig should reject min_novelty_score outside [0, 1]."""
        with pytest.raises(ValueError, match="min_novelty_score must be between 0 and 1"):
            DreamConfig(min_novelty_score=1.5)


# =============================================================================
# TEST: DreamConfig.derive_seed Determinism
# =============================================================================


class TestDeriveSeed:
    """Test DreamConfig.derive_seed determinism."""

    def test_same_inputs_same_seed(self, default_config: DreamConfig) -> None:
        """Same cycle_id and algorithm should produce same seed."""
        seed1 = default_config.derive_seed("cycle-abc", "bgt_sm")
        seed2 = default_config.derive_seed("cycle-abc", "bgt_sm")

        assert seed1 == seed2

    def test_different_cycle_different_seed(self, default_config: DreamConfig) -> None:
        """Different cycle_id should produce different seed."""
        seed1 = default_config.derive_seed("cycle-abc", "bgt_sm")
        seed2 = default_config.derive_seed("cycle-xyz", "bgt_sm")

        assert seed1 != seed2

    def test_different_algorithm_different_seed(self, default_config: DreamConfig) -> None:
        """Different algorithm should produce different seed."""
        seed1 = default_config.derive_seed("cycle-abc", "bgt_sm")
        seed2 = default_config.derive_seed("cycle-abc", "cpn")

        assert seed1 != seed2

    def test_config_seed_overrides_cycle_id(self) -> None:
        """Config seed should override cycle_id for determinism."""
        config = DreamConfig(seed="fixed-seed")

        seed1 = config.derive_seed("cycle-abc", "bgt_sm")
        seed2 = config.derive_seed("cycle-xyz", "bgt_sm")

        # Same config seed means same derived seed regardless of cycle_id
        assert seed1 == seed2


# =============================================================================
# TEST: DreamExplorer Creation
# =============================================================================


class TestDreamExplorerCreation:
    """Test DreamExplorer class creation."""

    def test_default_config(self) -> None:
        """DreamExplorer should create default config if none provided."""
        explorer = DreamExplorer()

        assert explorer.config is not None
        assert explorer.config.depth == 3

    def test_custom_config(self, custom_config: DreamConfig) -> None:
        """DreamExplorer should use provided config."""
        explorer = DreamExplorer(config=custom_config)

        assert explorer.config.depth == 5
        assert explorer.config.creativity == 0.8


# =============================================================================
# TEST: DreamExplorer.explore() Execution
# =============================================================================


class TestDreamExplorerExplore:
    """Test DreamExplorer.explore() method."""

    @pytest.mark.asyncio
    async def test_explore_returns_output(
        self,
        explorer: DreamExplorer,
        sample_input: DreamExplorerInput,
    ) -> None:
        """explore() should return DreamExplorerOutput."""
        output = await explorer.explore(sample_input)

        assert isinstance(output, DreamExplorerOutput)

    @pytest.mark.asyncio
    async def test_explore_output_structure(
        self,
        explorer: DreamExplorer,
        sample_input: DreamExplorerInput,
    ) -> None:
        """explore() output should have all required fields."""
        output = await explorer.explore(sample_input)

        assert hasattr(output, "insights")
        assert hasattr(output, "counterfactuals")
        assert hasattr(output, "prospective_memories")
        assert hasattr(output, "routine_optimizations")
        assert hasattr(output, "mcts_decisions_evaluated")
        assert hasattr(output, "compute_ms")

    @pytest.mark.asyncio
    async def test_explore_records_compute_time(
        self,
        explorer: DreamExplorer,
        sample_input: DreamExplorerInput,
    ) -> None:
        """explore() should record compute time."""
        output = await explorer.explore(sample_input)

        assert output.compute_ms >= 0

    @pytest.mark.asyncio
    async def test_explore_empty_input_succeeds(
        self,
        explorer: DreamExplorer,
    ) -> None:
        """explore() should succeed with empty input data."""
        input_data = DreamExplorerInput(
            cycle_id="01JTEST",
            tenant_id="t1",
            space_id="s1",
        )

        output = await explorer.explore(input_data)

        assert output.is_empty  # Stub returns empty lists


# =============================================================================
# TEST: Model Creation and Validation
# =============================================================================


class TestInsightModel:
    """Test Insight dataclass."""

    def test_insight_creation(self) -> None:
        """Insight.create() should create valid insight."""
        insight = Insight.create(
            insight_id="insight-001",
            insight_type=InsightType.PATTERN.value,
            description="Test insight description",
            confidence=0.8,
            supporting_evidence=["evt-1", "evt-2"],
            novelty_score=0.7,
        )

        assert insight.insight_id == "insight-001"
        assert insight.insight_type == "PATTERN"
        assert insight.confidence == 0.8
        assert insight.novelty_score == 0.7
        assert len(insight.supporting_evidence) == 2
        assert insight.created_at > 0

    def test_insight_invalid_confidence(self) -> None:
        """Insight should reject invalid confidence."""
        with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
            Insight.create(
                insight_id="i1",
                insight_type="PATTERN",
                description="test",
                confidence=1.5,
                supporting_evidence=[],
                novelty_score=0.5,
            )

    def test_insight_invalid_novelty(self) -> None:
        """Insight should reject invalid novelty_score."""
        with pytest.raises(ValueError, match="novelty_score must be between 0 and 1"):
            Insight.create(
                insight_id="i1",
                insight_type="PATTERN",
                description="test",
                confidence=0.5,
                supporting_evidence=[],
                novelty_score=-0.1,
            )

    def test_insight_frozen(self) -> None:
        """Insight should be immutable (frozen)."""
        insight = Insight.create(
            insight_id="i1",
            insight_type="PATTERN",
            description="test",
            confidence=0.5,
            supporting_evidence=[],
            novelty_score=0.5,
        )

        with pytest.raises(AttributeError):
            insight.confidence = 0.9  # type: ignore


class TestCounterfactualScenarioModel:
    """Test CounterfactualScenario dataclass."""

    def test_scenario_creation(self) -> None:
        """CounterfactualScenario.create() should create valid scenario."""
        scenario = CounterfactualScenario.create(
            scenario_id="cf-001",
            scenario_type=ScenarioType.UPWARD.value,
            base_episode_id="episode-001",
            perturbation_target="action",
            original_outcome="missed deadline",
            counterfactual_outcome="met deadline early",
            plausibility=0.75,
            success_probability=0.8,
            utility_delta=0.25,
        )

        assert scenario.scenario_id == "cf-001"
        assert scenario.scenario_type == "UPWARD"
        assert scenario.plausibility == 0.75
        assert scenario.created_at > 0

    def test_scenario_invalid_plausibility(self) -> None:
        """CounterfactualScenario should reject invalid plausibility."""
        with pytest.raises(ValueError, match="plausibility must be between 0 and 1"):
            CounterfactualScenario.create(
                scenario_id="cf-001",
                scenario_type="UPWARD",
                base_episode_id="ep-001",
                perturbation_target="action",
                original_outcome="a",
                counterfactual_outcome="b",
                plausibility=1.5,
                success_probability=0.5,
                utility_delta=0.0,
            )


class TestProspectiveMemoryModel:
    """Test ProspectiveMemory dataclass."""

    def test_prospective_creation(self) -> None:
        """ProspectiveMemory.create() should create valid memory."""
        memory = ProspectiveMemory.create(
            prosp_id="pm-001",
            intention_type="REMINDER",
            description="Call mom on birthday",
            trigger_condition="March 15",
            action_to_take="Call mom",
            importance=0.9,
            confidence=0.85,
        )

        assert memory.prosp_id == "pm-001"
        assert memory.intention_type == "REMINDER"
        assert memory.importance == 0.9
        assert memory.created_at > 0


class TestRoutineOptimizationModel:
    """Test RoutineOptimization dataclass."""

    def test_routine_creation(self) -> None:
        """RoutineOptimization.create() should create valid optimization."""
        routine = RoutineOptimization.create(
            routine_id="ro-001",
            routine_name="Morning routine",
            bottleneck_step="Find keys",
            bottleneck_position=3,
            value_drop=-0.2,
            suggested_action="Keep keys in consistent location",
            expected_improvement=0.15,
            confidence=0.7,
        )

        assert routine.routine_id == "ro-001"
        assert routine.bottleneck_position == 3
        assert routine.expected_improvement == 0.15


# =============================================================================
# TEST: Output Ranking and Limiting
# =============================================================================


class TestOutputRankingAndLimiting:
    """Test that DreamExplorer ranks and limits outputs correctly.

    Issue 8.1.10: Updated tests for comprehensive quality thresholds:
    - semantic_distance >= 0.7
    - pmi_score >= 3.0
    - novelty_score >= 0.5
    - serendipity_score >= 0.6
    """

    def test_rank_insights_by_serendipity(self) -> None:
        """Insights should be sorted by serendipity_score descending."""
        config = DreamConfig(
            max_insights=10,
            min_novelty_score=0.0,
            semantic_distance_threshold=0.0,
            pmi_threshold=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        # Create insights with varying serendipity (novelty * relevance * actionability)
        insights = [
            Insight.create(
                "i1",
                "PATTERN",
                "low serendipity",
                0.5,
                [],
                novelty_score=0.6,
                relevance_score=0.5,
                actionability_score=0.5,
            ),  # serendipity = 0.15
            Insight.create(
                "i2",
                "PATTERN",
                "high serendipity",
                0.5,
                [],
                novelty_score=0.9,
                relevance_score=0.9,
                actionability_score=0.9,
            ),  # serendipity = 0.729
            Insight.create(
                "i3",
                "PATTERN",
                "med serendipity",
                0.5,
                [],
                novelty_score=0.7,
                relevance_score=0.7,
                actionability_score=0.7,
            ),  # serendipity = 0.343
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert ranked[0].serendipity_score > ranked[1].serendipity_score
        assert ranked[1].serendipity_score > ranked[2].serendipity_score

    def test_filter_by_novelty_threshold(self) -> None:
        """Insights below min_novelty_score should be filtered."""
        config = DreamConfig(
            max_insights=10,
            min_novelty_score=0.5,
            semantic_distance_threshold=0.0,
            pmi_threshold=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create("i1", "PATTERN", "low", 0.5, [], novelty_score=0.3),  # Below
            Insight.create("i2", "PATTERN", "high", 0.5, [], novelty_score=0.9),
            Insight.create("i3", "PATTERN", "med", 0.5, [], novelty_score=0.6),
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert len(ranked) == 2
        assert all(i.novelty_score >= 0.5 for i in ranked)

    def test_limit_insights_to_max(self) -> None:
        """Insights should be limited to max_insights."""
        config = DreamConfig(
            max_insights=2,
            min_novelty_score=0.0,
            semantic_distance_threshold=0.0,
            pmi_threshold=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create(f"i{i}", "PATTERN", f"insight {i}", 0.5, [], novelty_score=0.5 + i * 0.1)
            for i in range(5)
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert len(ranked) == 2

        assert len(ranked) == 2

    def test_limit_counterfactuals(self) -> None:
        """Counterfactuals should be limited to max_counterfactuals."""
        config = DreamConfig(max_counterfactuals=2)
        explorer = DreamExplorer(config=config)

        scenarios = [
            CounterfactualScenario.create(
                f"cf{i}", "UPWARD", f"ep{i}", "action", "orig", "counter", 0.5 + i * 0.1, 0.5, 0.0
            )
            for i in range(5)
        ]

        limited = explorer._limit_counterfactuals(scenarios)

        assert len(limited) == 2


# =============================================================================
# TEST: Deterministic Execution
# =============================================================================


class TestDeterministicExecution:
    """Test that DreamExplorer produces deterministic outputs."""

    @pytest.mark.asyncio
    async def test_same_seed_same_output(self) -> None:
        """Same seed should produce same outputs."""
        config = DreamConfig(seed="fixed-seed-123")
        explorer = DreamExplorer(config=config)

        input_data = DreamExplorerInput(
            cycle_id="cycle-001",
            tenant_id="t1",
            space_id="s1",
        )

        output1 = await explorer.explore(input_data)
        output2 = await explorer.explore(input_data)

        # With stub implementation, both return empty
        # When algorithms are implemented, they should be identical
        assert output1.total_outputs == output2.total_outputs

    @pytest.mark.asyncio
    async def test_cycle_id_affects_seed(self) -> None:
        """Different cycle_id should derive different algorithm seeds."""
        config = DreamConfig()  # No fixed seed

        # Different cycle_ids
        input1 = DreamExplorerInput(
            cycle_id="cycle-abc",
            tenant_id="t1",
            space_id="s1",
        )
        input2 = DreamExplorerInput(
            cycle_id="cycle-xyz",
            tenant_id="t1",
            space_id="s1",
        )

        # Verify different seeds are derived
        seed1 = config.derive_seed(input1.cycle_id, "bgt_sm")
        seed2 = config.derive_seed(input2.cycle_id, "bgt_sm")

        assert seed1 != seed2


# =============================================================================
# TEST: DreamExplorerOutput Properties
# =============================================================================


class TestDreamExplorerOutput:
    """Test DreamExplorerOutput properties."""

    def test_total_outputs(self) -> None:
        """total_outputs should count all output types."""
        output = DreamExplorerOutput(
            insights=[Insight.create("i1", "PATTERN", "test", 0.5, [], 0.5)],
            counterfactuals=[
                CounterfactualScenario.create(
                    "cf1", "UPWARD", "ep1", "action", "a", "b", 0.5, 0.5, 0.0
                )
            ],
            prospective_memories=[
                ProspectiveMemory.create("pm1", "REMINDER", "test", "cond", "act", 0.5, 0.5)
            ],
            routine_optimizations=[
                RoutineOptimization.create("ro1", "routine", "step", 1, -0.1, "action", 0.1, 0.5)
            ],
        )

        assert output.total_outputs == 4

    def test_is_empty(self) -> None:
        """is_empty should be True when no outputs."""
        empty_output = DreamExplorerOutput()
        assert empty_output.is_empty is True

        non_empty = DreamExplorerOutput(
            insights=[Insight.create("i1", "PATTERN", "test", 0.5, [], 0.5)]
        )
        assert non_empty.is_empty is False


# =============================================================================
# TEST: Issue 8.1.10 Quality Thresholds
# =============================================================================


class TestQualityThresholds:
    """Test Issue 8.1.10 quality filtering for insight surfacing.

    Quality thresholds:
    - semantic_distance >= 0.7
    - pmi_score >= 3.0
    - novelty_score >= 0.5
    - serendipity_score >= 0.6
    """

    def test_filter_by_semantic_distance(self) -> None:
        """Insights below semantic_distance_threshold should be filtered."""
        config = DreamConfig(
            max_insights=10,
            semantic_distance_threshold=0.7,
            pmi_threshold=0.0,
            min_novelty_score=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create(
                "i1",
                "PATTERN",
                "close concepts",
                0.5,
                [],
                novelty_score=0.9,
                semantic_distance=0.3,
            ),  # Below 0.7
            Insight.create(
                "i2",
                "PATTERN",
                "distant concepts",
                0.5,
                [],
                novelty_score=0.8,
                semantic_distance=0.8,
            ),  # Above 0.7
            Insight.create(
                "i3",
                "PATTERN",
                "borderline",
                0.5,
                [],
                novelty_score=0.7,
                semantic_distance=0.7,
            ),  # Exactly at threshold
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert len(ranked) == 2
        assert all(i.semantic_distance >= 0.7 for i in ranked)

    def test_filter_by_pmi_threshold(self) -> None:
        """Insights below pmi_threshold should be filtered."""
        config = DreamConfig(
            max_insights=10,
            semantic_distance_threshold=0.0,
            pmi_threshold=3.0,
            min_novelty_score=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create(
                "i1",
                "PATTERN",
                "low pmi",
                0.5,
                [],
                novelty_score=0.9,
                pmi_score=2.0,
            ),  # Below 3.0
            Insight.create(
                "i2",
                "PATTERN",
                "high pmi",
                0.5,
                [],
                novelty_score=0.8,
                pmi_score=5.0,
            ),  # Above 3.0
            Insight.create(
                "i3",
                "PATTERN",
                "borderline pmi",
                0.5,
                [],
                novelty_score=0.7,
                pmi_score=3.0,
            ),  # Exactly at threshold
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert len(ranked) == 2
        assert all((i.pmi_score or 0) >= 3.0 for i in ranked)

    def test_filter_by_serendipity_threshold(self) -> None:
        """Insights below serendipity_threshold should be filtered."""
        config = DreamConfig(
            max_insights=10,
            semantic_distance_threshold=0.0,
            pmi_threshold=0.0,
            min_novelty_score=0.0,
            serendipity_threshold=0.6,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create(
                "i1",
                "PATTERN",
                "low serendipity",
                0.5,
                [],
                novelty_score=0.5,
                relevance_score=0.5,
                actionability_score=0.5,
            ),  # serendipity = 0.125 (below)
            Insight.create(
                "i2",
                "PATTERN",
                "high serendipity",
                0.5,
                [],
                novelty_score=0.9,
                relevance_score=0.9,
                actionability_score=0.9,
            ),  # serendipity = 0.729 (above)
            Insight.create(
                "i3",
                "PATTERN",
                "borderline serendipity",
                0.5,
                [],
                novelty_score=0.85,
                relevance_score=0.85,
                actionability_score=0.85,
            ),  # serendipity ~= 0.614 (above)
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert len(ranked) == 2
        assert all(i.serendipity_score >= 0.6 for i in ranked)

    def test_combined_thresholds(self) -> None:
        """All thresholds must be met for inclusion."""
        config = DreamConfig(
            max_insights=10,
            semantic_distance_threshold=0.7,
            pmi_threshold=3.0,
            min_novelty_score=0.5,
            serendipity_threshold=0.6,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            # Passes all
            Insight.create(
                "i1",
                "PATTERN",
                "passes all",
                0.5,
                [],
                novelty_score=0.9,
                semantic_distance=0.8,
                pmi_score=5.0,
                relevance_score=0.9,
                actionability_score=0.9,
            ),
            # Fails semantic_distance only
            Insight.create(
                "i2",
                "PATTERN",
                "fails distance",
                0.5,
                [],
                novelty_score=0.9,
                semantic_distance=0.5,
                pmi_score=5.0,
                relevance_score=0.9,
                actionability_score=0.9,
            ),
            # Fails pmi only
            Insight.create(
                "i3",
                "PATTERN",
                "fails pmi",
                0.5,
                [],
                novelty_score=0.9,
                semantic_distance=0.8,
                pmi_score=2.0,
                relevance_score=0.9,
                actionability_score=0.9,
            ),
            # Fails novelty only
            Insight.create(
                "i4",
                "PATTERN",
                "fails novelty",
                0.5,
                [],
                novelty_score=0.3,
                semantic_distance=0.8,
                pmi_score=5.0,
                relevance_score=0.9,
                actionability_score=0.9,
            ),
            # Fails serendipity only (low relevance/actionability)
            Insight.create(
                "i5",
                "PATTERN",
                "fails serendipity",
                0.5,
                [],
                novelty_score=0.9,
                semantic_distance=0.8,
                pmi_score=5.0,
                relevance_score=0.5,
                actionability_score=0.5,
            ),
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        assert len(ranked) == 1
        assert ranked[0].insight_id == "i1"

    def test_stable_ranking_determinism(self) -> None:
        """Top-N ranking should be stable and deterministic."""
        config = DreamConfig(
            max_insights=3,
            semantic_distance_threshold=0.0,
            pmi_threshold=0.0,
            min_novelty_score=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create(
                f"i{i}",
                "PATTERN",
                f"insight {i}",
                0.5,
                [],
                novelty_score=0.5 + i * 0.05,
                relevance_score=0.5 + i * 0.05,
                actionability_score=0.5 + i * 0.05,
            )
            for i in range(10)
        ]

        # Run multiple times to verify determinism
        results = [explorer._rank_and_limit_insights(insights) for _ in range(5)]

        # All runs should produce same order
        for result in results[1:]:
            assert [i.insight_id for i in result] == [i.insight_id for i in results[0]]

    def test_serendipity_calculation(self) -> None:
        """Serendipity should be novelty × relevance × actionability."""
        insight = Insight.create(
            "i1",
            "PATTERN",
            "test",
            0.5,
            [],
            novelty_score=0.8,
            relevance_score=0.7,
            actionability_score=0.9,
        )

        expected = 0.8 * 0.7 * 0.9  # 0.504
        assert abs(insight.serendipity_score - expected) < 0.001

    def test_default_thresholds_per_spec(self) -> None:
        """Default thresholds should match Issue 8.1.10 spec."""
        config = DreamConfig()

        assert config.semantic_distance_threshold == 0.7
        assert config.pmi_threshold == 3.0
        assert config.min_novelty_score == 0.5
        assert config.serendipity_threshold == 0.6

    def test_null_pmi_treated_as_zero(self) -> None:
        """None pmi_score should be treated as 0.0."""
        config = DreamConfig(
            max_insights=10,
            semantic_distance_threshold=0.0,
            pmi_threshold=3.0,
            min_novelty_score=0.0,
            serendipity_threshold=0.0,
        )
        explorer = DreamExplorer(config=config)

        insights = [
            Insight.create(
                "i1",
                "PATTERN",
                "no pmi",
                0.5,
                [],
                novelty_score=0.9,
            ),  # pmi_score = None (defaults to None)
            Insight.create(
                "i2",
                "PATTERN",
                "has pmi",
                0.5,
                [],
                novelty_score=0.8,
                pmi_score=5.0,
            ),
        ]

        ranked = explorer._rank_and_limit_insights(insights)

        # Only the insight with pmi >= 3.0 should pass
        assert len(ranked) == 1
        assert ranked[0].insight_id == "i2"
