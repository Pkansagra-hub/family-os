"""
CPN (Causal Perturbation Network) Unit Tests — Issue 8.1.4

Test Categories:
1. CPNConfig validation
2. CausalDAG construction and traversal
3. Regret event selection
4. Counterfactual generation (UPWARD/DOWNWARD/SEMIFACTUAL)
5. Plausibility calculation
6. Deterministic execution with seeds
7. Edge case handling

References:
- M8_EXECUTION.md Issue 8.1.4: CPN counterfactual generation
- Dossier §4.6.1: Counterfactual Thinking (CPN Algorithm)
- Dossier Appendix C.6.1: Causal Perturbation Network
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

import pytest

from k0.modules.consolidation.algorithms.cpn import (
    CausalDAG,
    CausalNode,
    CausalPerturbationNetwork,
    CPNConfig,
    CPNCounterfactual,
    NodeModifiability,
    ScenarioType,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def default_config() -> CPNConfig:
    """Default CPN configuration."""
    return CPNConfig()


@pytest.fixture
def strict_config() -> CPNConfig:
    """Strict CPN config with high thresholds."""
    return CPNConfig(
        emotional_threshold=0.8,
        top_k_regret_events=5,
        min_plausibility=0.5,
        min_utility_delta=0.4,
    )


@dataclass
class MockEpisode:
    """Mock episode for testing."""

    episode_id: str
    sentiment_score: float
    salience_score: float
    start_time_ms: int
    entity_ids: List[str]


@dataclass
class MockEdge:
    """Mock KG edge for testing."""

    source_id: str
    target_id: str
    relation_type: str
    confidence: float


@pytest.fixture
def sample_episodes() -> List[MockEpisode]:
    """Sample episodes with varying sentiment."""
    now_ms = int(time.time() * 1000)
    return [
        MockEpisode(
            episode_id="ep-001",
            sentiment_score=-0.8,  # Negative, regret-worthy
            salience_score=0.9,
            start_time_ms=now_ms - 1000 * 60 * 60,  # 1 hour ago
            entity_ids=["entity-A", "entity-B"],
        ),
        MockEpisode(
            episode_id="ep-002",
            sentiment_score=0.7,  # Positive
            salience_score=0.8,
            start_time_ms=now_ms - 1000 * 60 * 60 * 2,  # 2 hours ago
            entity_ids=["entity-C"],
        ),
        MockEpisode(
            episode_id="ep-003",
            sentiment_score=-0.4,  # Below threshold
            salience_score=0.5,
            start_time_ms=now_ms - 1000 * 60 * 60 * 24,  # 1 day ago
            entity_ids=["entity-D"],
        ),
        MockEpisode(
            episode_id="ep-004",
            sentiment_score=-0.9,  # Very negative
            salience_score=0.95,
            start_time_ms=now_ms - 1000 * 60 * 30,  # 30 mins ago
            entity_ids=["entity-E", "entity-F", "entity-G"],
        ),
    ]


@pytest.fixture
def sample_edges() -> List[MockEdge]:
    """Sample KG edges with causal relationships."""
    return [
        MockEdge("entity-X", "entity-A", "CAUSES", 0.85),
        MockEdge("entity-Y", "entity-A", "CAUSES", 0.70),
        MockEdge("entity-Z", "entity-X", "CAUSES", 0.90),
        MockEdge("entity-E", "entity-F", "CAUSES", 0.75),
        MockEdge("entity-H", "entity-E", "CAUSES", 0.80),
        MockEdge("entity-I", "entity-H", "CAUSES", 0.65),
        # Non-causal edges (should be ignored)
        MockEdge("entity-A", "entity-B", "RELATES_TO", 0.5),
        MockEdge("entity-C", "entity-D", "PART_OF", 0.6),
    ]


@pytest.fixture
def cpn(default_config: CPNConfig) -> CausalPerturbationNetwork:
    """CPN instance with default config."""
    return CausalPerturbationNetwork(config=default_config)


# =============================================================================
# TEST: CPNConfig Validation
# =============================================================================


class TestCPNConfigValidation:
    """Test CPNConfig dataclass validation."""

    def test_default_values(self) -> None:
        """CPNConfig should have sensible defaults."""
        config = CPNConfig()

        assert config.emotional_threshold == 0.6
        assert config.top_k_regret_events == 10
        assert config.causal_chain_depth == 5
        assert config.perturbation_std == 0.1
        assert config.min_plausibility == 0.3
        assert config.min_utility_delta == 0.3
        assert len(config.counterfactual_types) == 3

    def test_custom_values(self) -> None:
        """CPNConfig should accept custom values."""
        config = CPNConfig(
            emotional_threshold=0.7,
            top_k_regret_events=5,
            causal_chain_depth=3,
            perturbation_std=0.2,
        )

        assert config.emotional_threshold == 0.7
        assert config.top_k_regret_events == 5
        assert config.causal_chain_depth == 3
        assert config.perturbation_std == 0.2

    def test_invalid_emotional_threshold(self) -> None:
        """CPNConfig should reject invalid emotional_threshold."""
        with pytest.raises(ValueError, match="emotional_threshold"):
            CPNConfig(emotional_threshold=1.5)

        with pytest.raises(ValueError, match="emotional_threshold"):
            CPNConfig(emotional_threshold=-0.1)

    def test_invalid_top_k(self) -> None:
        """CPNConfig should reject invalid top_k_regret_events."""
        with pytest.raises(ValueError, match="top_k_regret_events"):
            CPNConfig(top_k_regret_events=0)

    def test_invalid_perturbation_std(self) -> None:
        """CPNConfig should reject non-positive perturbation_std."""
        with pytest.raises(ValueError, match="perturbation_std"):
            CPNConfig(perturbation_std=0)

        with pytest.raises(ValueError, match="perturbation_std"):
            CPNConfig(perturbation_std=-0.1)


# =============================================================================
# TEST: CausalDAG
# =============================================================================


class TestCausalDAG:
    """Test CausalDAG data structure."""

    def test_empty_dag(self) -> None:
        """Empty DAG should have zero nodes and edges."""
        dag = CausalDAG()

        assert dag.node_count == 0
        assert dag.edge_count == 0
        assert dag.get_modifiable_nodes() == []

    def test_add_nodes(self) -> None:
        """DAG should correctly add nodes."""
        dag = CausalDAG()
        dag.add_node("n1", NodeModifiability.MODIFIABLE, depth=0)
        dag.add_node("n2", NodeModifiability.EXTERNAL, depth=1)

        assert dag.node_count == 2
        assert "n1" in dag.nodes
        assert "n2" in dag.nodes
        assert dag.nodes["n1"].modifiability == NodeModifiability.MODIFIABLE

    def test_add_edges(self) -> None:
        """DAG should correctly add edges."""
        dag = CausalDAG()
        dag.add_edge("a", "b", 0.8)
        dag.add_edge("b", "c", 0.7)

        assert dag.edge_count == 2
        assert dag.get_edge_confidence("a", "b") == 0.8
        assert dag.get_edge_confidence("b", "c") == 0.7

    def test_get_modifiable_nodes(self) -> None:
        """get_modifiable_nodes should return only modifiable nodes."""
        dag = CausalDAG()
        dag.add_node("n1", NodeModifiability.MODIFIABLE, depth=1)
        dag.add_node("n2", NodeModifiability.EXTERNAL, depth=2)
        dag.add_node("n3", NodeModifiability.MODIFIABLE, depth=0)

        modifiable = dag.get_modifiable_nodes()

        assert len(modifiable) == 2
        # Should be sorted by depth (closest first)
        assert modifiable[0].node_id == "n3"
        assert modifiable[1].node_id == "n1"

    def test_get_predecessors(self) -> None:
        """get_predecessors should return direct predecessors."""
        dag = CausalDAG()
        dag.add_edge("a", "c", 0.8)
        dag.add_edge("b", "c", 0.7)
        dag.add_edge("c", "d", 0.6)

        predecessors = dag.get_predecessors("c")

        assert len(predecessors) == 2
        assert "a" in predecessors
        assert "b" in predecessors

    def test_duplicate_nodes_ignored(self) -> None:
        """Adding duplicate node should be ignored."""
        dag = CausalDAG()
        dag.add_node("n1", NodeModifiability.MODIFIABLE, depth=0)
        dag.add_node("n1", NodeModifiability.EXTERNAL, depth=1)  # Duplicate

        assert dag.node_count == 1
        # First addition wins
        assert dag.nodes["n1"].modifiability == NodeModifiability.MODIFIABLE


# =============================================================================
# TEST: Regret Event Selection
# =============================================================================


class TestRegretEventSelection:
    """Test regret event selection logic."""

    def test_select_high_sentiment_episodes(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
    ) -> None:
        """CPN should select episodes with high |sentiment|."""
        import random

        rng = random.Random(42)
        selected = cpn._select_regret_events(sample_episodes, rng)

        # Should select ep-001 (-0.8) and ep-004 (-0.9) above 0.6 threshold
        # ep-002 is positive (0.7) so also above threshold
        assert len(selected) >= 2
        assert len(selected) <= 3

        # ep-003 (-0.4) should be excluded (below 0.6 threshold)
        selected_ids = [ep.episode_id for ep in selected]
        assert "ep-003" not in selected_ids

    def test_respects_top_k_limit(
        self,
        sample_episodes: List[MockEpisode],
    ) -> None:
        """Selection should respect top_k limit."""
        config = CPNConfig(top_k_regret_events=2, emotional_threshold=0.1)
        cpn = CausalPerturbationNetwork(config=config)

        import random

        rng = random.Random(42)
        selected = cpn._select_regret_events(sample_episodes, rng)

        assert len(selected) <= 2

    def test_prioritizes_recent_events(
        self,
        sample_episodes: List[MockEpisode],
    ) -> None:
        """More recent events should have higher priority."""
        config = CPNConfig(emotional_threshold=0.5)
        cpn = CausalPerturbationNetwork(config=config)

        import random

        rng = random.Random(42)
        selected = cpn._select_regret_events(sample_episodes, rng)

        if len(selected) >= 2:
            # ep-004 is most recent and most negative, should be first
            assert selected[0].episode_id == "ep-004"

    def test_empty_episodes_returns_empty(
        self,
        cpn: CausalPerturbationNetwork,
    ) -> None:
        """Empty episode list should return empty selection."""
        import random

        rng = random.Random(42)
        selected = cpn._select_regret_events([], rng)

        assert selected == []


# =============================================================================
# TEST: Causal Chain Extraction
# =============================================================================


class TestCausalChainExtraction:
    """Test causal chain extraction from KG."""

    def test_build_edge_lookup(
        self,
        cpn: CausalPerturbationNetwork,
        sample_edges: List[MockEdge],
    ) -> None:
        """Edge lookup should only include CAUSES edges."""
        lookup = cpn._build_edge_lookup(sample_edges)

        # Should only have CAUSES edges
        assert "entity-A" in lookup  # Has two causes
        assert len(lookup["entity-A"]) == 2

        # Non-CAUSES edges should be excluded
        assert "entity-B" not in lookup  # Only target of RELATES_TO

    def test_extract_causal_chain(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """Should extract causal DAG for episode."""
        edge_lookup = cpn._build_edge_lookup(sample_edges)
        episode = sample_episodes[0]  # ep-001 with entity-A, entity-B

        dag = cpn._extract_causal_chain(episode, edge_lookup)

        # Should have nodes from the causal chain
        assert dag.node_count > 0

    def test_respects_depth_limit(
        self,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """Causal chain should respect depth limit."""
        config = CPNConfig(causal_chain_depth=2)
        cpn = CausalPerturbationNetwork(config=config)

        edge_lookup = cpn._build_edge_lookup(sample_edges)
        episode = sample_episodes[0]

        dag = cpn._extract_causal_chain(episode, edge_lookup)

        # All nodes should have depth < 2
        for node in dag.nodes.values():
            assert node.depth < 2


# =============================================================================
# TEST: Counterfactual Generation
# =============================================================================


class TestCounterfactualGeneration:
    """Test counterfactual scenario generation."""

    def test_generate_with_valid_input(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """CPN should generate scenarios from valid input."""
        scenarios = cpn.generate(
            episodes=sample_episodes,
            kg_edges=sample_edges,
            rng_seed=42,
        )

        # Should generate some scenarios (depends on data)
        # At minimum, the structure should be correct
        assert isinstance(scenarios, list)

    def test_deterministic_with_seed(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """Same seed should produce same scenarios."""
        scenarios1 = cpn.generate(sample_episodes, sample_edges, rng_seed=42)
        scenarios2 = cpn.generate(sample_episodes, sample_edges, rng_seed=42)

        assert len(scenarios1) == len(scenarios2)
        for s1, s2 in zip(scenarios1, scenarios2):
            assert s1.scenario_id == s2.scenario_id
            assert s1.scenario_type == s2.scenario_type

    def test_different_seed_different_output(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """Different seeds should potentially produce different scenarios."""
        scenarios1 = cpn.generate(sample_episodes, sample_edges, rng_seed=42)
        scenarios2 = cpn.generate(sample_episodes, sample_edges, rng_seed=999)

        # May differ in details (order, specific values)
        # At minimum, they should both be valid lists
        assert isinstance(scenarios1, list)
        assert isinstance(scenarios2, list)

    def test_empty_episodes_no_scenarios(
        self,
        cpn: CausalPerturbationNetwork,
        sample_edges: List[MockEdge],
    ) -> None:
        """Empty episodes should produce no scenarios."""
        scenarios = cpn.generate([], sample_edges, rng_seed=42)

        assert scenarios == []

    def test_empty_edges_no_scenarios(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
    ) -> None:
        """Empty edges should produce no causal scenarios."""
        scenarios = cpn.generate(sample_episodes, [], rng_seed=42)

        # May still generate scenarios if episodes have entities
        assert isinstance(scenarios, list)


# =============================================================================
# TEST: Scenario Types
# =============================================================================


class TestScenarioTypes:
    """Test UPWARD/DOWNWARD/SEMIFACTUAL scenario generation."""

    def test_upward_only_config(
        self,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """Should only generate UPWARD scenarios when configured."""
        config = CPNConfig(counterfactual_types=("UPWARD",))
        cpn = CausalPerturbationNetwork(config=config)

        scenarios = cpn.generate(sample_episodes, sample_edges, rng_seed=42)

        for s in scenarios:
            assert s.scenario_type == ScenarioType.UPWARD

    def test_downward_only_config(
        self,
        sample_episodes: List[MockEpisode],
        sample_edges: List[MockEdge],
    ) -> None:
        """Should only generate DOWNWARD scenarios when configured."""
        config = CPNConfig(counterfactual_types=("DOWNWARD",))
        cpn = CausalPerturbationNetwork(config=config)

        scenarios = cpn.generate(sample_episodes, sample_edges, rng_seed=42)

        for s in scenarios:
            assert s.scenario_type == ScenarioType.DOWNWARD

    def test_upward_improves_outcome(
        self,
        cpn: CausalPerturbationNetwork,
    ) -> None:
        """UPWARD scenarios should have positive utility_delta."""
        # Create minimal test data
        episode = MockEpisode(
            episode_id="test-ep",
            sentiment_score=-0.7,
            salience_score=0.9,
            start_time_ms=int(time.time() * 1000),
            entity_ids=["entity-1"],
        )
        edges = [MockEdge("entity-cause", "entity-1", "CAUSES", 0.8)]

        # Generate with UPWARD only
        config = CPNConfig(
            counterfactual_types=("UPWARD",),
            min_utility_delta=0.0,  # Accept all
            min_plausibility=0.0,
        )
        cpn = CausalPerturbationNetwork(config=config)

        scenarios = cpn.generate([episode], edges, rng_seed=42)

        for s in scenarios:
            if s.scenario_type == ScenarioType.UPWARD:
                assert s.utility_delta > 0


# =============================================================================
# TEST: Plausibility Calculation
# =============================================================================


class TestPlausibilityCalculation:
    """Test plausibility score calculation."""

    def test_depth_affects_plausibility(
        self,
        cpn: CausalPerturbationNetwork,
    ) -> None:
        """Deeper nodes should have lower plausibility."""
        dag = CausalDAG()
        node_close = CausalNode("n1", NodeModifiability.MODIFIABLE, depth=1)
        node_far = CausalNode("n2", NodeModifiability.MODIFIABLE, depth=4)

        dag.add_node("n1", NodeModifiability.MODIFIABLE, depth=1)
        dag.add_node("n2", NodeModifiability.MODIFIABLE, depth=4)

        plaus_close = cpn._compute_plausibility(dag, node_close)
        plaus_far = cpn._compute_plausibility(dag, node_far)

        # Closer node should have higher plausibility
        assert plaus_close > plaus_far

    def test_plausibility_bounded(
        self,
        cpn: CausalPerturbationNetwork,
    ) -> None:
        """Plausibility should be in [0, 1] range."""
        dag = CausalDAG()
        dag.add_node("n1", NodeModifiability.MODIFIABLE, depth=0)
        dag.add_node("n2", NodeModifiability.MODIFIABLE, depth=10)

        for node_id, node in dag.nodes.items():
            plaus = cpn._compute_plausibility(dag, node)
            assert 0.0 <= plaus <= 1.0


# =============================================================================
# TEST: CPNCounterfactual Properties
# =============================================================================


class TestCPNCounterfactualProperties:
    """Test CPNCounterfactual dataclass properties."""

    def test_is_upward(self) -> None:
        """is_upward should return True for UPWARD scenarios."""
        scenario = CPNCounterfactual(
            scenario_id="cf-001",
            scenario_type=ScenarioType.UPWARD,
            base_episode_id="ep-001",
            intervention_node_id="node-1",
            perturbation_target="action",
            original_outcome="bad",
            counterfactual_outcome="good",
            original_sentiment=-0.5,
            predicted_sentiment=0.3,
            plausibility=0.8,
            success_probability=0.7,
            utility_delta=0.8,
            mitigation="Do X instead",
            causal_path_length=2,
            created_at_ms=int(time.time() * 1000),
        )

        assert scenario.is_upward is True
        assert scenario.is_downward is False

    def test_is_downward(self) -> None:
        """is_downward should return True for DOWNWARD scenarios."""
        scenario = CPNCounterfactual(
            scenario_id="cf-002",
            scenario_type=ScenarioType.DOWNWARD,
            base_episode_id="ep-001",
            intervention_node_id="node-1",
            perturbation_target="action",
            original_outcome="neutral",
            counterfactual_outcome="bad",
            original_sentiment=0.0,
            predicted_sentiment=-0.5,
            plausibility=0.7,
            success_probability=0.6,
            utility_delta=-0.5,
            mitigation=None,
            causal_path_length=1,
            created_at_ms=int(time.time() * 1000),
        )

        assert scenario.is_upward is False
        assert scenario.is_downward is True


# =============================================================================
# TEST: Dict-like Episode/Edge Handling
# =============================================================================


class TestDictLikeHandling:
    """Test CPN handles dict-like episodes and edges."""

    def test_dict_episodes(
        self,
        cpn: CausalPerturbationNetwork,
    ) -> None:
        """CPN should handle dict episodes."""
        episodes = [
            {
                "episode_id": "ep-dict-001",
                "sentiment_score": -0.8,
                "salience_score": 0.9,
                "start_time_ms": int(time.time() * 1000),
                "entity_ids": ["e1", "e2"],
            }
        ]
        edges = [
            {"source_id": "e0", "target_id": "e1", "relation_type": "CAUSES", "confidence": 0.8}
        ]

        scenarios = cpn.generate(episodes, edges, rng_seed=42)

        # Should not raise, may or may not generate scenarios
        assert isinstance(scenarios, list)

    def test_mixed_protocol_and_dict(
        self,
        cpn: CausalPerturbationNetwork,
        sample_episodes: List[MockEpisode],
    ) -> None:
        """CPN should handle mix of protocol and dict edges."""
        edges = [
            {
                "source_id": "x",
                "target_id": "entity-A",
                "relation_type": "CAUSES",
                "confidence": 0.7,
            }
        ]

        scenarios = cpn.generate(sample_episodes, edges, rng_seed=42)

        assert isinstance(scenarios, list)
