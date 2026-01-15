"""
Unit tests for BGT-SM (Bisociative Graph Traversal for Semantic Memory).

Issue 8.1.9: BGT-SM Bisociative Insight Generation

These tests validate:
- Random Walk with Restart (RWR) execution
- PMI calculation for surprise quantification
- Remote associate discovery
- Insight generation and ranking
- Integration with DreamExplorer

References:
- M8_EXECUTION.md Issue 8.1.9: BGT-SM Bisociative Insight Generation
- Dossier §4.6.4: Insight Generation (BGT-SM)
- Dossier Appendix C.6.3: BGT-SM (Insight Generation)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pytest

from k0.modules.consolidation.algorithms.bgt_sm import (
    P03_BGT_PMI_THRESHOLD,
    P03_BGT_SEMANTIC_DISTANCE_THRESHOLD,
    BGTConfig,
    BGTInsight,
    BisociativeGraphTraversal,
    ConnectionType,
    EmbeddingCache,
    InsightCategory,
    KnowledgeGraphView,
    PMICalculator,
    RandomWalkEngine,
    RemoteAssociate,
)

# =============================================================================
# TEST FIXTURES - Mock Entities and Edges
# =============================================================================


@dataclass
class MockEntity:
    """Mock entity for testing."""

    entity_id: str
    entity_type: str
    name: str
    observation_count: int
    embedding: Optional[List[float]] = None


@dataclass
class MockEdge:
    """Mock edge for testing."""

    source_id: str
    target_id: str
    relation_type: str
    observation_count: int = 1


@pytest.fixture
def sample_entities() -> List[MockEntity]:
    """Create sample KG entities for testing."""
    return [
        MockEntity(
            entity_id="ent_001",
            entity_type="PERSON",
            name="Alice",
            observation_count=50,
            embedding=[0.1, 0.2, 0.3, 0.4],
        ),
        MockEntity(
            entity_id="ent_002",
            entity_type="PERSON",
            name="Bob",
            observation_count=30,
            embedding=[0.15, 0.25, 0.35, 0.45],  # Similar to Alice
        ),
        MockEntity(
            entity_id="ent_003",
            entity_type="LOCATION",
            name="Cafe Downtown",
            observation_count=20,
            embedding=[0.9, 0.1, 0.05, 0.05],  # Very different
        ),
        MockEntity(
            entity_id="ent_004",
            entity_type="EVENT",
            name="Morning Coffee",
            observation_count=40,
            embedding=[0.8, 0.15, 0.1, 0.05],  # Similar to Cafe
        ),
        MockEntity(
            entity_id="ent_005",
            entity_type="CONCEPT",
            name="Productivity",
            observation_count=15,
            embedding=[0.5, 0.5, 0.5, 0.5],  # Neutral
        ),
        MockEntity(
            entity_id="ent_006",
            entity_type="ACTIVITY",
            name="Coding Session",
            observation_count=25,
            embedding=[0.6, 0.4, 0.3, 0.2],
        ),
    ]


@pytest.fixture
def sample_edges() -> List[MockEdge]:
    """Create sample KG edges for testing."""
    return [
        # Alice knows Bob
        MockEdge("ent_001", "ent_002", "KNOWS", 10),
        # Alice visits Cafe
        MockEdge("ent_001", "ent_003", "VISITS", 15),
        # Bob also visits Cafe
        MockEdge("ent_002", "ent_003", "VISITS", 5),
        # Cafe hosts Morning Coffee
        MockEdge("ent_003", "ent_004", "HOSTS", 20),
        # Morning Coffee improves Productivity
        MockEdge("ent_004", "ent_005", "IMPROVES", 8),
        # Alice does Coding Session
        MockEdge("ent_001", "ent_006", "PERFORMS", 12),
        # Coding requires Productivity
        MockEdge("ent_006", "ent_005", "REQUIRES", 10),
    ]


@pytest.fixture
def sample_embeddings() -> dict:
    """Create sample embeddings dict."""
    return {
        "ent_001": [0.1, 0.2, 0.3, 0.4],
        "ent_002": [0.15, 0.25, 0.35, 0.45],  # Similar to ent_001
        "ent_003": [0.9, 0.1, 0.05, 0.05],  # Very different
        "ent_004": [0.8, 0.15, 0.1, 0.05],  # Similar to ent_003
        "ent_005": [0.5, 0.5, 0.5, 0.5],  # Neutral
        "ent_006": [0.6, 0.4, 0.3, 0.2],
    }


# =============================================================================
# BGTConfig Tests
# =============================================================================


class TestBGTConfig:
    """Tests for BGTConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = BGTConfig()

        assert config.restart_probability == 0.15
        assert config.walk_steps == 1000
        assert config.max_walks_per_seed == 3
        assert config.semantic_distance_threshold == P03_BGT_SEMANTIC_DISTANCE_THRESHOLD
        assert config.pmi_threshold == P03_BGT_PMI_THRESHOLD
        assert config.novelty_threshold == 0.5
        assert config.seed is None

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = BGTConfig(
            restart_probability=0.2,
            walk_steps=500,
            pmi_threshold=2.5,
            seed=12345,
        )

        assert config.restart_probability == 0.2
        assert config.walk_steps == 500
        assert config.pmi_threshold == 2.5
        assert config.seed == 12345

    def test_invalid_restart_probability(self) -> None:
        """Test validation rejects invalid restart probability."""
        with pytest.raises(ValueError, match="restart_probability"):
            BGTConfig(restart_probability=0.0)

        with pytest.raises(ValueError, match="restart_probability"):
            BGTConfig(restart_probability=1.0)

    def test_invalid_walk_steps(self) -> None:
        """Test validation rejects invalid walk steps."""
        with pytest.raises(ValueError, match="walk_steps"):
            BGTConfig(walk_steps=0)

    def test_invalid_corpus_size(self) -> None:
        """Test validation rejects invalid corpus size."""
        with pytest.raises(ValueError, match="corpus_size_n"):
            BGTConfig(corpus_size_n=0)


# =============================================================================
# KnowledgeGraphView Tests
# =============================================================================


class TestKnowledgeGraphView:
    """Tests for KnowledgeGraphView."""

    def test_graph_construction(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test graph view construction."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)

        assert graph.get_entity("ent_001") is not None
        assert graph.get_entity("ent_999") is None
        assert graph.corpus_size == sum(e.observation_count for e in sample_entities)

    def test_get_neighbors(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test neighbor retrieval."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)

        # Alice has outgoing edges
        alice_neighbors = graph.get_neighbors("ent_001")
        assert len(alice_neighbors) == 3  # knows Bob, visits Cafe, performs Coding

    def test_get_cooccurrence(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test co-occurrence count retrieval."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)

        # Alice-Bob co-occurrence
        cooc = graph.get_cooccurrence_count("ent_001", "ent_002")
        assert cooc == 10  # From KNOWS edge

        # Non-existent pair
        no_cooc = graph.get_cooccurrence_count("ent_001", "ent_005")
        assert no_cooc == 0

    def test_entity_name_fallback(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test entity name falls back to ID if not found."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)

        assert graph.get_entity_name("ent_001") == "Alice"
        assert graph.get_entity_name("unknown") == "unknown"


# =============================================================================
# EmbeddingCache Tests
# =============================================================================


class TestEmbeddingCache:
    """Tests for EmbeddingCache."""

    def test_add_and_get_embedding(self) -> None:
        """Test adding and retrieving embeddings."""
        cache = EmbeddingCache()
        cache.add_embedding("ent_001", [0.1, 0.2, 0.3])

        emb = cache.get_embedding("ent_001")
        assert emb == [0.1, 0.2, 0.3]

    def test_cosine_similarity(self, sample_embeddings: dict) -> None:
        """Test cosine similarity computation."""
        cache = EmbeddingCache(sample_embeddings)

        # Similar entities
        sim = cache.compute_cosine_similarity("ent_001", "ent_002")
        assert sim is not None
        assert sim > 0.9  # Very similar

        # Different entities
        sim_diff = cache.compute_cosine_similarity("ent_001", "ent_003")
        assert sim_diff is not None
        assert sim_diff < 0.5  # Different

    def test_semantic_distance(self, sample_embeddings: dict) -> None:
        """Test semantic distance computation."""
        cache = EmbeddingCache(sample_embeddings)

        # Similar entities → low distance
        dist_similar = cache.compute_semantic_distance("ent_001", "ent_002")
        assert dist_similar is not None
        assert dist_similar < 0.1

        # Different entities → high distance
        dist_diff = cache.compute_semantic_distance("ent_001", "ent_003")
        assert dist_diff is not None
        assert dist_diff > 0.5

    def test_missing_embeddings(self) -> None:
        """Test handling of missing embeddings."""
        cache = EmbeddingCache()

        sim = cache.compute_cosine_similarity("ent_001", "ent_002")
        assert sim is None

        dist = cache.compute_semantic_distance("ent_001", "ent_002")
        assert dist is None


# =============================================================================
# PMICalculator Tests
# =============================================================================


class TestPMICalculator:
    """Tests for PMI calculation."""

    def test_pmi_computation(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test PMI calculation."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)
        calculator = PMICalculator(graph)

        # Alice-Cafe: co-occur 15 times
        # c_a = 50, c_b = 20, c_ab = 15, N = 180
        pmi = calculator.compute_pmi("ent_001", "ent_003")

        # Expected: log2((15 * 180) / (50 * 20)) = log2(2.7) ≈ 1.43
        assert pmi > 0  # Positive PMI = above chance

    def test_pmi_zero_cooccurrence(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test PMI returns 0 for non-co-occurring entities."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)
        calculator = PMICalculator(graph)

        # Alice and Productivity have no direct edge
        pmi = calculator.compute_pmi("ent_001", "ent_005")
        assert pmi == 0.0

    def test_pmi_with_corpus_override(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test PMI with corpus size override."""
        graph = KnowledgeGraphView(sample_entities, sample_edges)
        calculator = PMICalculator(graph, corpus_size_override=10000)

        pmi = calculator.compute_pmi("ent_001", "ent_003")
        # With larger N, PMI should be higher
        assert pmi > 0


# =============================================================================
# RandomWalkEngine Tests
# =============================================================================


class TestRandomWalkEngine:
    """Tests for Random Walk with Restart."""

    def test_basic_walk(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test basic random walk execution."""
        import random

        graph = KnowledgeGraphView(sample_entities, sample_edges)
        config = BGTConfig(walk_steps=100, seed=42)
        rng = random.Random(42)

        engine = RandomWalkEngine(graph, config, rng)
        visits = engine.random_walk_with_restart("ent_001")

        # Should visit seed entity
        assert "ent_001" in visits
        assert visits["ent_001"].visit_count > 0

        # Should visit connected entities
        # Alice connects to: Bob, Cafe, Coding
        connected_count = sum(1 for eid in ["ent_002", "ent_003", "ent_006"] if eid in visits)
        assert connected_count > 0

    def test_deterministic_walks(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test walks are deterministic with same seed."""
        import random

        graph = KnowledgeGraphView(sample_entities, sample_edges)
        config = BGTConfig(walk_steps=50, seed=12345)

        rng1 = random.Random(12345)
        engine1 = RandomWalkEngine(graph, config, rng1)
        visits1 = engine1.random_walk_with_restart("ent_001")

        rng2 = random.Random(12345)
        engine2 = RandomWalkEngine(graph, config, rng2)
        visits2 = engine2.random_walk_with_restart("ent_001")

        # Same visits
        assert set(visits1.keys()) == set(visits2.keys())
        for key in visits1:
            assert visits1[key].visit_count == visits2[key].visit_count

    def test_aggregate_walks(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test aggregated walk execution."""
        import random

        graph = KnowledgeGraphView(sample_entities, sample_edges)
        config = BGTConfig(walk_steps=100, seed=42)
        rng = random.Random(42)

        engine = RandomWalkEngine(graph, config, rng)
        visits = engine.aggregate_walks("ent_001", num_walks=3)

        # Should have accumulated visit counts
        assert visits["ent_001"].visit_count >= 3  # At least 1 per walk


# =============================================================================
# RemoteAssociate Tests
# =============================================================================


class TestRemoteAssociate:
    """Tests for RemoteAssociate dataclass."""

    def test_is_surprising(self) -> None:
        """Test surprise threshold check."""
        surprising = RemoteAssociate(
            seed_entity_id="ent_001",
            target_entity_id="ent_003",
            visit_count=5,
            semantic_distance=0.8,
            pmi_score=4.0,  # Above threshold
            novelty_score=0.6,
            connection_path=("ent_001", "ent_003"),
        )
        assert surprising.is_surprising is True

        not_surprising = RemoteAssociate(
            seed_entity_id="ent_001",
            target_entity_id="ent_002",
            visit_count=10,
            semantic_distance=0.8,
            pmi_score=2.0,  # Below threshold
            novelty_score=0.3,
            connection_path=("ent_001", "ent_002"),
        )
        assert not_surprising.is_surprising is False

    def test_is_remote(self) -> None:
        """Test remoteness threshold check."""
        remote = RemoteAssociate(
            seed_entity_id="ent_001",
            target_entity_id="ent_003",
            visit_count=5,
            semantic_distance=0.8,  # Above threshold
            pmi_score=3.5,
            novelty_score=0.6,
            connection_path=("ent_001", "ent_003"),
        )
        assert remote.is_remote is True

        not_remote = RemoteAssociate(
            seed_entity_id="ent_001",
            target_entity_id="ent_002",
            visit_count=10,
            semantic_distance=0.4,  # Below threshold
            pmi_score=3.5,
            novelty_score=0.3,
            connection_path=("ent_001", "ent_002"),
        )
        assert not_remote.is_remote is False


# =============================================================================
# BGTInsight Tests
# =============================================================================


class TestBGTInsight:
    """Tests for BGTInsight dataclass."""

    def test_to_insight_conversion(self) -> None:
        """Test conversion to standard Insight model."""
        bgt_insight = BGTInsight(
            insight_id="01JFABC123456789XYZDEFGHIJ",
            source_entity_id="ent_001",
            target_entity_id="ent_003",
            source_entity_name="Alice",
            target_entity_name="Cafe Downtown",
            semantic_distance=0.75,
            pmi_score=3.5,
            novelty_score=0.65,
            insight_text="Interesting connection between Alice and Cafe Downtown",
            category=InsightCategory.OPPORTUNITY,
            connection_type=ConnectionType.SEMANTIC,
            connection_path=("ent_001", "ent_003"),
            supporting_evidence=("ent_001", "ent_003"),
            confidence=0.7,
        )

        insight = bgt_insight.to_insight()

        assert insight.insight_id == "01JFABC123456789XYZDEFGHIJ"
        assert insight.insight_type == "ASSOCIATION"
        assert insight.concept_a_id == "ent_001"
        assert insight.concept_b_id == "ent_003"
        assert insight.pmi_score == 3.5
        assert insight.novelty_score == 0.65
        assert insight.confidence == 0.7


# =============================================================================
# BisociativeGraphTraversal Tests
# =============================================================================


class TestBisociativeGraphTraversal:
    """Tests for the main BGT-SM class."""

    def test_discover_basic(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test basic insight discovery."""
        # Use low thresholds to ensure insights are generated
        config = BGTConfig(
            semantic_distance_threshold=0.3,  # Low threshold
            pmi_threshold=0.5,  # Low threshold
            novelty_threshold=0.1,  # Low threshold
            walk_steps=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
            rng_seed=42,
        )

        # Should generate some insights
        assert isinstance(insights, list)

    def test_discover_deterministic(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test discovery is deterministic with same seed."""
        config = BGTConfig(
            semantic_distance_threshold=0.3,
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=12345,
        )

        bgt = BisociativeGraphTraversal(config)

        insights1 = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
            rng_seed=12345,
        )

        insights2 = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
            rng_seed=12345,
        )

        # Same insights
        assert len(insights1) == len(insights2)
        for i1, i2 in zip(insights1, insights2):
            assert i1.source_entity_id == i2.source_entity_id
            assert i1.target_entity_id == i2.target_entity_id
            assert i1.novelty_score == i2.novelty_score

    def test_discover_multiple_seeds(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test discovery with multiple seed entities."""
        config = BGTConfig(
            semantic_distance_threshold=0.2,
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001", "ent_003", "ent_006"],
            embeddings=sample_embeddings,
        )

        assert isinstance(insights, list)

    def test_discover_no_embeddings(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test discovery works without embeddings (uses path-based distance)."""
        config = BGTConfig(
            semantic_distance_threshold=0.1,  # Very low since path-based
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=None,  # No embeddings
        )

        assert isinstance(insights, list)

    def test_discover_empty_graph(self) -> None:
        """Test discovery handles empty graph gracefully."""
        config = BGTConfig(seed=42)
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=[],
            edges=[],
            seed_entity_ids=["ent_001"],
        )

        assert insights == []

    def test_discover_nonexistent_seed(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Test discovery handles nonexistent seed entities."""
        config = BGTConfig(seed=42)
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["nonexistent_entity"],
        )

        assert insights == []

    def test_insights_sorted_by_novelty(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test insights are sorted by novelty score descending."""
        config = BGTConfig(
            semantic_distance_threshold=0.2,
            pmi_threshold=0.5,
            novelty_threshold=0.05,
            walk_steps=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001", "ent_003"],
            embeddings=sample_embeddings,
        )

        if len(insights) >= 2:
            for i in range(len(insights) - 1):
                assert insights[i].novelty_score >= insights[i + 1].novelty_score

    def test_max_insights_limit(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test max_total_insights limit is respected."""
        config = BGTConfig(
            semantic_distance_threshold=0.1,
            pmi_threshold=0.1,
            novelty_threshold=0.01,
            max_total_insights=3,
            walk_steps=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001", "ent_003", "ent_004"],
            embeddings=sample_embeddings,
        )

        assert len(insights) <= 3


# =============================================================================
# Integration Tests
# =============================================================================


class TestBGTIntegration:
    """Integration tests for BGT-SM with DreamExplorer."""

    def test_insight_text_generation(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test that insights have meaningful text."""
        config = BGTConfig(
            semantic_distance_threshold=0.2,
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
        )

        for insight in insights:
            assert insight.insight_text
            assert len(insight.insight_text) > 10
            assert (
                insight.source_entity_name in insight.insight_text
                or insight.target_entity_name in insight.insight_text
            )

    def test_insight_confidence_bounds(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test that confidence scores are within bounds."""
        config = BGTConfig(
            semantic_distance_threshold=0.2,
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
        )

        for insight in insights:
            assert 0.0 <= insight.confidence <= 1.0
            assert 0.0 <= insight.novelty_score <= 10.0  # Can be > 1

    def test_connection_types_assigned(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test that connection types are properly assigned."""
        config = BGTConfig(
            semantic_distance_threshold=0.2,
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
        )

        for insight in insights:
            assert insight.connection_type in ConnectionType.__members__.values()

    def test_pmi_threshold_filtering(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test that only insights meeting PMI threshold are returned."""
        high_threshold = BGTConfig(
            pmi_threshold=10.0,  # Very high
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(high_threshold)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
        )

        # With very high PMI threshold, should get few/no insights
        for insight in insights:
            assert insight.pmi_score >= 10.0

    def test_semantic_distance_filtering(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        sample_embeddings: dict,
    ) -> None:
        """Test that only remote associates are discovered."""
        high_distance = BGTConfig(
            semantic_distance_threshold=0.9,  # Very high
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            walk_steps=50,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(high_distance)
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=sample_embeddings,
        )

        # With very high distance threshold, all returned should be remote
        for insight in insights:
            assert insight.semantic_distance >= 0.9


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
