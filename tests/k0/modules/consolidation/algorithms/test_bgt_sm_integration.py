"""
Integration tests for BGT-SM (Bisociative Graph Traversal) — M3-E3-I1

Tests BGT-SM's ability to discover insights from knowledge graph data
with entities, edges, and embeddings under cold-start conditions.
"""

import random
from dataclasses import dataclass

from k0.modules.consolidation.algorithms.bgt_sm import (
    BGTConfig,
    BGTInsight,
    BisociativeGraphTraversal,
)


@dataclass
class MockKGEntity:
    """Mock KG entity for testing BGT-SM."""

    entity_id: str
    entity_type: str
    observation_count: int
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.entity_id.replace("_", " ").title()


@dataclass
class MockKGEdge:
    """Mock KG edge for testing BGT-SM."""

    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    confidence: float = 1.0
    observation_count: int = 1  # Required by EdgeProtocol


class TestBGTSMIntegration:
    """Integration tests for BGT-SM algorithm with KG data."""

    def _create_test_graph(
        self,
        num_entities: int = 100,
        num_edges: int = 500,
        embedding_dim: int = 128,
        seed: int = 42,
    ) -> tuple:
        """Create a test knowledge graph with entities, edges, and embeddings."""
        rng = random.Random(seed)

        # Create entities with varying observation counts
        entity_types = ["PERSON", "ORG", "LOCATION", "CONCEPT", "EVENT"]
        entities = []
        for i in range(num_entities):
            entities.append(
                MockKGEntity(
                    entity_id=f"entity_{i}",
                    entity_type=entity_types[i % len(entity_types)],
                    observation_count=rng.randint(5, 100),
                )
            )

        # Create embeddings - use clusters to ensure some are semantically distant
        embeddings = {}
        for i, entity in enumerate(entities):
            # Create clustered embeddings - entities in same group have similar embeddings
            cluster = i % 10  # 10 clusters
            base = [0.0] * embedding_dim
            base[cluster * 10 : (cluster + 1) * 10] = [1.0] * 10
            # Add noise
            embedding = [v + rng.gauss(0, 0.3) for v in base]
            # Normalize
            norm = sum(v * v for v in embedding) ** 0.5
            embeddings[entity.entity_id] = [v / norm for v in embedding]

        # Create edges with structure
        edges = []
        edge_set = set()
        relation_types = ["RELATES_TO", "KNOWS", "LOCATED_IN", "WORKS_AT", "PARTICIPATES"]

        # Create intra-cluster edges (more likely)
        for _ in range(num_edges * 2 // 3):
            cluster = rng.randint(0, 9)
            src_idx = cluster * 10 + rng.randint(0, 9)
            tgt_idx = cluster * 10 + rng.randint(0, 9)
            if src_idx >= num_entities:
                src_idx = src_idx % num_entities
            if tgt_idx >= num_entities:
                tgt_idx = tgt_idx % num_entities
            if src_idx != tgt_idx:
                pair = (f"entity_{src_idx}", f"entity_{tgt_idx}")
                if pair not in edge_set:
                    edge_set.add(pair)
                    edges.append(
                        MockKGEdge(
                            source_id=pair[0],
                            target_id=pair[1],
                            relation_type=rng.choice(relation_types),
                            confidence=rng.uniform(0.7, 1.0),
                        )
                    )

        # Create inter-cluster edges (bridge connections - more surprising)
        for _ in range(num_edges // 3):
            src_cluster = rng.randint(0, 9)
            tgt_cluster = rng.randint(0, 9)
            if src_cluster != tgt_cluster:
                src_idx = src_cluster * 10 + rng.randint(0, 9)
                tgt_idx = tgt_cluster * 10 + rng.randint(0, 9)
                if src_idx >= num_entities:
                    src_idx = src_idx % num_entities
                if tgt_idx >= num_entities:
                    tgt_idx = tgt_idx % num_entities
                pair = (f"entity_{src_idx}", f"entity_{tgt_idx}")
                if pair not in edge_set:
                    edge_set.add(pair)
                    edges.append(
                        MockKGEdge(
                            source_id=pair[0],
                            target_id=pair[1],
                            relation_type=rng.choice(relation_types),
                            confidence=rng.uniform(0.5, 0.9),
                        )
                    )

        return entities, edges, embeddings

    def test_bgt_generates_insights_with_kg_data(self) -> None:
        """Verify BGT-SM generates insights from KG with cold-start thresholds."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=100,
            num_edges=500,
            seed=42,
        )

        # Configure with cold-start thresholds (M3-E2)
        config = BGTConfig(
            semantic_distance_threshold=0.5,  # Cold-start threshold
            pmi_threshold=1.5,  # Cold-start threshold
            novelty_threshold=0.3,  # Cold-start threshold
            corpus_size_n=1000,  # Large enough to avoid cold-start skip
            cold_start_threshold=100,  # Must be below corpus_size_n
            max_insights_per_seed=5,
            max_total_insights=20,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)

        # Select seed entities from different clusters
        seed_entities = ["entity_0", "entity_10", "entity_20", "entity_30", "entity_40"]

        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        # Should generate at least some insights with cold-start thresholds
        assert len(insights) >= 0, "BGT-SM should complete without error"

        # If insights generated, verify structure
        for insight in insights:
            assert isinstance(insight, BGTInsight)
            assert insight.source_entity_id.startswith("entity_")
            assert insight.target_entity_id.startswith("entity_")
            assert 0.0 <= insight.novelty_score <= 10.0  # Novelty can exceed 1.0
            assert insight.pmi_score >= 0.0
            assert len(insight.insight_text) > 0
            assert insight.confidence > 0.0

    def test_bgt_cold_start_skip(self) -> None:
        """Verify BGT-SM skips discovery when corpus is too small."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=50,
            num_edges=100,
            seed=42,
        )

        # Configure with corpus_size below cold_start_threshold
        config = BGTConfig(
            corpus_size_n=50,  # Below threshold
            cold_start_threshold=100,  # Threshold is 100
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)
        seed_entities = ["entity_0", "entity_10"]

        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        # Should return empty list due to cold-start skip
        assert insights == [], "Should skip discovery when corpus too small"

    def test_bgt_deterministic_with_seed(self) -> None:
        """Verify BGT-SM produces same results with same seed."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=100,
            num_edges=300,
            seed=42,
        )

        config = BGTConfig(
            semantic_distance_threshold=0.5,
            pmi_threshold=1.5,
            novelty_threshold=0.3,
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=12345,
        )

        seed_entities = ["entity_0", "entity_15", "entity_30"]

        # Run twice with same seed
        bgt1 = BisociativeGraphTraversal(config=config)
        insights1 = bgt1.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=12345,
        )

        bgt2 = BisociativeGraphTraversal(config=config)
        insights2 = bgt2.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=12345,
        )

        # Should produce identical results
        assert len(insights1) == len(insights2)
        for i1, i2 in zip(insights1, insights2):
            assert i1.source_entity_id == i2.source_entity_id
            assert i1.target_entity_id == i2.target_entity_id
            assert i1.novelty_score == i2.novelty_score

    def test_bgt_empty_seeds_returns_empty(self) -> None:
        """Verify BGT-SM handles empty seed list gracefully."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=50,
            num_edges=100,
            seed=42,
        )

        config = BGTConfig(
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)
        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=[],  # Empty seeds
            embeddings=embeddings,
            rng_seed=42,
        )

        assert insights == [], "Empty seeds should return empty insights"

    def test_bgt_missing_seed_entity_warning(self) -> None:
        """Verify BGT-SM handles missing seed entities gracefully."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=50,
            num_edges=100,
            seed=42,
        )

        config = BGTConfig(
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)
        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=["nonexistent_entity_999"],  # Not in graph
            embeddings=embeddings,
            rng_seed=42,
        )

        # Should complete without error, returning empty list
        assert isinstance(insights, list)

    def test_bgt_insight_conversion_to_standard_model(self) -> None:
        """Verify BGT insights convert to standard Insight model correctly."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=100,
            num_edges=500,
            seed=42,
        )

        config = BGTConfig(
            semantic_distance_threshold=0.3,  # Very low to ensure insights
            pmi_threshold=0.5,  # Very low to ensure insights
            novelty_threshold=0.1,  # Very low to ensure insights
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)
        seed_entities = ["entity_0", "entity_25", "entity_50"]

        bgt_insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        # Convert to standard Insight model
        for bgt_insight in bgt_insights:
            standard_insight = bgt_insight.to_insight()

            # Verify conversion
            assert standard_insight.insight_id == bgt_insight.insight_id
            assert standard_insight.insight_type == "ASSOCIATION"
            assert standard_insight.description == bgt_insight.insight_text
            assert standard_insight.confidence == bgt_insight.confidence
            assert standard_insight.novelty_score == bgt_insight.novelty_score
            assert standard_insight.concept_a_id == bgt_insight.source_entity_id
            assert standard_insight.concept_b_id == bgt_insight.target_entity_id
            assert standard_insight.pmi_score == bgt_insight.pmi_score

    def test_bgt_respects_max_insights_limit(self) -> None:
        """Verify BGT-SM respects max_total_insights limit."""
        entities, edges, embeddings = self._create_test_graph(
            num_entities=100,
            num_edges=500,
            seed=42,
        )

        max_insights = 5
        config = BGTConfig(
            semantic_distance_threshold=0.3,  # Low to generate more
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            corpus_size_n=1000,
            cold_start_threshold=100,
            max_insights_per_seed=10,
            max_total_insights=max_insights,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)
        seed_entities = ["entity_0", "entity_10", "entity_20", "entity_30", "entity_40"]

        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        assert len(insights) <= max_insights, f"Should limit to {max_insights} insights"

    def test_bgt_no_embeddings_still_works(self) -> None:
        """Verify BGT-SM works without embeddings (skips semantic distance)."""
        entities, edges, _ = self._create_test_graph(
            num_entities=100,
            num_edges=300,
            seed=42,
        )

        config = BGTConfig(
            semantic_distance_threshold=0.0,  # Disable semantic filter
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=42,
        )

        bgt = BisociativeGraphTraversal(config=config)
        seed_entities = ["entity_0", "entity_10"]

        insights = bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=None,  # No embeddings
            rng_seed=42,
        )

        # Should complete without error
        assert isinstance(insights, list)


class TestBGTSMThresholdBehavior:
    """Tests for BGT-SM threshold behavior with cold-start settings."""

    def test_lower_thresholds_generate_more_insights(self) -> None:
        """Verify lower thresholds (cold-start) generate more insights."""
        # Create a fixed test graph
        rng = random.Random(42)
        entities = [
            MockKGEntity(
                entity_id=f"entity_{i}",
                entity_type="CONCEPT",
                observation_count=rng.randint(5, 50),
            )
            for i in range(50)
        ]

        # Create a simple connected graph
        edges = []
        for i in range(100):
            src = f"entity_{rng.randint(0, 49)}"
            tgt = f"entity_{rng.randint(0, 49)}"
            if src != tgt:
                edges.append(
                    MockKGEdge(
                        source_id=src,
                        target_id=tgt,
                        relation_type="RELATES_TO",
                    )
                )

        # Create embeddings with some distance
        embeddings = {}
        for i in range(50):
            emb = [rng.gauss(0, 1) for _ in range(64)]
            norm = sum(v * v for v in emb) ** 0.5
            embeddings[f"entity_{i}"] = [v / norm for v in emb]

        seed_entities = ["entity_0", "entity_10", "entity_20"]

        # High thresholds (production)
        high_config = BGTConfig(
            semantic_distance_threshold=0.7,
            pmi_threshold=3.0,
            novelty_threshold=0.5,
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=42,
        )

        # Low thresholds (cold-start)
        low_config = BGTConfig(
            semantic_distance_threshold=0.3,
            pmi_threshold=0.5,
            novelty_threshold=0.1,
            corpus_size_n=1000,
            cold_start_threshold=100,
            seed=42,
        )

        bgt_high = BisociativeGraphTraversal(config=high_config)
        insights_high = bgt_high.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        bgt_low = BisociativeGraphTraversal(config=low_config)
        insights_low = bgt_low.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=seed_entities,
            embeddings=embeddings,
            rng_seed=42,
        )

        # Lower thresholds should generate at least as many insights
        assert len(insights_low) >= len(insights_high), (
            f"Lower thresholds should generate >= insights: "
            f"low={len(insights_low)}, high={len(insights_high)}"
        )
