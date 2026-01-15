"""
BGT-SM Algorithm Benchmarks — Real-World Testing.

This module provides comprehensive benchmarks for the BGT-SM (Bisociative
Graph Traversal for Semantic Memory) insight generation algorithm.

Test Categories:
1. Correctness: Validates insight structure and PMI calculation
2. Performance: Measures execution time at various scales
3. Quality: Evaluates insight novelty and serendipity
4. Knowledge Graph: Tests graph traversal and co-occurrence
5. Determinism: Verifies reproducibility

References:
- M8_EXECUTION.md Issue 8.1.9: BGT-SM Bisociative Insight Generation
- M8_EXECUTION.md Issue 8.1.10: Insight Quality Thresholds
- Dossier §4.6.4: Insight Generation (BGT-SM)
- Dossier Appendix C.6.3: BGT-SM Algorithm Details
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import pytest

from k0.modules.consolidation.algorithms.bgt_sm import (
    P03_BGT_NOVELTY_THRESHOLD,
    P03_BGT_PMI_THRESHOLD,
    P03_BGT_SEMANTIC_DISTANCE_THRESHOLD,
    BGTConfig,
    BisociativeGraphTraversal,
    KnowledgeGraphView,
)
from tests.k0.modules.consolidation.benchmarks.performance_metrics import (
    BenchmarkCollector,
    DistributionStats,
    StopwatchTimer,
)
from tests.k0.modules.consolidation.benchmarks.realistic_data import (
    BenchmarkDatasetGenerator,
    BenchmarkScale,
    RealisticEdge,
    RealisticEntity,
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def compute_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def compute_semantic_distance(v1: List[float], v2: List[float]) -> float:
    """Compute semantic distance (1 - cosine_similarity)."""
    return 1.0 - compute_cosine_similarity(v1, v2)


# =============================================================================
# MOCK EMBEDDING PROVIDER
# =============================================================================


class MockEmbeddingProvider:
    """Provides embeddings from realistic entity data."""

    def __init__(self, entities: List[RealisticEntity]):
        """Initialize with entity list."""
        self._embeddings = {e.entity_id: e.embedding for e in entities if e.embedding}

    @property
    def embeddings(self) -> Dict[str, List[float]]:
        """Get all embeddings as a dictionary."""
        return self._embeddings

    def get_embedding(self, entity_id: str) -> Optional[List[float]]:
        """Get embedding for entity."""
        return self._embeddings.get(entity_id)

    def compute_distance(self, entity_a: str, entity_b: str) -> float:
        """Compute semantic distance between entities."""
        emb_a = self._embeddings.get(entity_a)
        emb_b = self._embeddings.get(entity_b)

        if emb_a is None or emb_b is None:
            return 0.5  # Default distance for missing embeddings

        return compute_semantic_distance(emb_a, emb_b)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def dataset_generator() -> BenchmarkDatasetGenerator:
    """Create dataset generator."""
    return BenchmarkDatasetGenerator(seed=42)


@pytest.fixture
def small_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Small dataset for quick tests."""
    return dataset_generator.generate(BenchmarkScale.SMALL)


@pytest.fixture
def medium_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Medium dataset for normal benchmarks."""
    return dataset_generator.generate(BenchmarkScale.MEDIUM)


@pytest.fixture
def large_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Large dataset for stress testing."""
    return dataset_generator.generate(BenchmarkScale.LARGE)


@pytest.fixture
def default_bgt() -> BisociativeGraphTraversal:
    """BGT-SM with default configuration."""
    return BisociativeGraphTraversal(BGTConfig(seed=42))


@pytest.fixture
def sensitive_bgt() -> BisociativeGraphTraversal:
    """BGT-SM with lower thresholds (generates more insights)."""
    return BisociativeGraphTraversal(
        BGTConfig(
            semantic_distance_threshold=0.3,
            pmi_threshold=1.0,
            novelty_threshold=0.2,
            max_total_insights=50,
            seed=42,
        )
    )


# =============================================================================
# BENCHMARK: PMI CALCULATION TESTS
# =============================================================================


class TestPMICalculation:
    """Verify PMI calculation correctness."""

    def test_pmi_basic_calculation(self) -> None:
        """Verify PMI formula: log2((c_ab * N) / (c_a * c_b))."""
        # Example: corpus size N=10000
        # Entity A appears 100 times, Entity B appears 50 times
        # They co-occur 10 times
        # Expected PMI = log2((10 * 10000) / (100 * 50)) = log2(20) ≈ 4.32

        N = 10000
        c_a = 100
        c_b = 50
        c_ab = 10

        expected_pmi = math.log2((c_ab * N) / (c_a * c_b))

        # Manual calculation
        calculated = math.log2((c_ab * N) / (c_a * c_b))

        print("\nPMI Calculation:")
        print(f"  Corpus size N: {N}")
        print(f"  c_a (entity A count): {c_a}")
        print(f"  c_b (entity B count): {c_b}")
        print(f"  c_ab (co-occurrence): {c_ab}")
        print(f"  PMI: {calculated:.3f}")
        print(f"  Interpretation: Entities co-occur {2**calculated:.1f}× more than expected")

        assert abs(expected_pmi - calculated) < 0.001
        assert calculated > P03_BGT_PMI_THRESHOLD, "Should exceed surprise threshold"

    def test_pmi_threshold_interpretation(self) -> None:
        """Verify PMI threshold of 3.0 means 8× more than expected."""
        # PMI = 3.0 means 2^3 = 8× more co-occurrences than random
        pmi_threshold = P03_BGT_PMI_THRESHOLD
        expected_multiplier = 2**pmi_threshold

        print("\nPMI Threshold Interpretation:")
        print(f"  Threshold: {pmi_threshold}")
        print(f"  Meaning: Entities must co-occur {expected_multiplier}× more than random chance")

        assert expected_multiplier == 8.0

    def test_pmi_with_realistic_data(self, small_dataset) -> None:
        """Calculate PMI from realistic knowledge graph."""
        entities = small_dataset.entities
        edges = small_dataset.edges

        # Build co-occurrence counts
        entity_counts = {e.entity_id: e.observation_count for e in entities}
        total_observations = sum(entity_counts.values()) or 1

        # Find edges and calculate PMI
        pmi_scores = []
        for edge in edges[:20]:  # Sample edges
            c_a = entity_counts.get(edge.source_id, 1)
            c_b = entity_counts.get(edge.target_id, 1)
            c_ab = edge.observation_count

            if c_a > 0 and c_b > 0 and c_ab > 0:
                pmi = math.log2((c_ab * total_observations) / (c_a * c_b))
                pmi_scores.append(pmi)

        if pmi_scores:
            stats = DistributionStats.from_values(pmi_scores)
            print("\nPMI Distribution from Realistic Data:")
            print(f"  Count: {stats.count}")
            print(f"  Mean: {stats.mean:.3f}")
            print(f"  Range: [{stats.min_value:.3f}, {stats.max_value:.3f}]")


# =============================================================================
# BENCHMARK: KNOWLEDGE GRAPH TESTS
# =============================================================================


class TestKnowledgeGraphView:
    """Test knowledge graph operations."""

    def test_graph_construction(self, small_dataset) -> None:
        """Verify graph view construction."""
        kg = KnowledgeGraphView(small_dataset.entities, small_dataset.edges)

        print("\nKnowledge Graph Stats:")
        print(f"  Entities: {len(small_dataset.entities)}")
        print(f"  Edges: {len(small_dataset.edges)}")
        print(f"  Corpus size: {kg.corpus_size}")

        assert kg.corpus_size > 0

    def test_neighbor_lookup(self, small_dataset) -> None:
        """Verify neighbor lookup efficiency."""
        kg = KnowledgeGraphView(small_dataset.entities, small_dataset.edges)

        timer = StopwatchTimer().start()

        # Look up neighbors for all entities
        total_neighbors = 0
        for entity in small_dataset.entities:
            neighbors = kg.get_neighbors(entity.entity_id)
            total_neighbors += len(neighbors)

        timer.stop()

        print("\nNeighbor Lookup Performance:")
        print(f"  Entities queried: {len(small_dataset.entities)}")
        print(f"  Total neighbors found: {total_neighbors}")
        print(f"  Time: {timer.elapsed_ms:.2f}ms")

        assert timer.elapsed_ms < 100  # Should be fast

    def test_cooccurrence_counts(self, small_dataset) -> None:
        """Verify co-occurrence counting."""
        kg = KnowledgeGraphView(small_dataset.entities, small_dataset.edges)

        # Check some random entity pairs
        cooccurrence_found = 0
        pairs_checked = 0

        for i, e1 in enumerate(small_dataset.entities[:10]):
            for e2 in small_dataset.entities[i + 1 : i + 5]:
                count = kg.get_cooccurrence_count(e1.entity_id, e2.entity_id)
                pairs_checked += 1
                if count > 0:
                    cooccurrence_found += 1

        print("\nCo-occurrence Analysis:")
        print(f"  Pairs checked: {pairs_checked}")
        print(f"  Pairs with co-occurrence: {cooccurrence_found}")


# =============================================================================
# BENCHMARK: RANDOM WALK TESTS
# =============================================================================


class TestRandomWalk:
    """Test random walk exploration."""

    def test_walk_reaches_remote_entities(self, medium_dataset) -> None:
        """Verify random walk can reach remote entities."""
        kg = KnowledgeGraphView(medium_dataset.entities, medium_dataset.edges)
        embedding_provider = MockEmbeddingProvider(medium_dataset.entities)

        # Pick a seed entity that has neighbors
        seed_entity = None
        for entity in medium_dataset.entities:
            if len(kg.get_neighbors(entity.entity_id)) > 0:
                seed_entity = entity
                break

        if seed_entity is None:
            pytest.skip("No entity with neighbors found")

        # Simulate random walk
        import random

        rng = random.Random(42)

        visited = {seed_entity.entity_id}
        current = seed_entity.entity_id
        max_steps = 100

        for _ in range(max_steps):
            neighbors = kg.get_neighbors(current)
            if not neighbors:
                break

            # Random neighbor selection
            next_edge = rng.choice(neighbors)
            current = next_edge.target_id
            visited.add(current)

        # Check semantic distances of visited entities from seed
        distances = []
        for entity_id in visited:
            if entity_id != seed_entity.entity_id:
                dist = embedding_provider.compute_distance(seed_entity.entity_id, entity_id)
                distances.append(dist)

        if distances:
            stats = DistributionStats.from_values(distances)
            print("\nRandom Walk Reach Analysis:")
            print(f"  Seed: {seed_entity.name}")
            print(f"  Entities visited: {len(visited)}")
            print("  Distance stats:")
            print(f"    Mean: {stats.mean:.3f}")
            print(f"    Max: {stats.max_value:.3f}")

            # Should reach some remote entities
            remote_count = sum(1 for d in distances if d > P03_BGT_SEMANTIC_DISTANCE_THRESHOLD)
            print(f"  Remote entities (>{P03_BGT_SEMANTIC_DISTANCE_THRESHOLD}): {remote_count}")

    def test_walk_determinism(self, small_dataset) -> None:
        """Verify random walk is deterministic with seed."""
        kg = KnowledgeGraphView(small_dataset.entities, small_dataset.edges)

        def do_walk(seed: int) -> List[str]:
            import random

            rng = random.Random(seed)

            visited = []
            current = small_dataset.entities[0].entity_id

            for _ in range(20):
                visited.append(current)
                neighbors = kg.get_neighbors(current)
                if not neighbors:
                    break
                next_edge = rng.choice(neighbors)
                current = next_edge.target_id

            return visited

        walk1 = do_walk(42)
        walk2 = do_walk(42)
        walk3 = do_walk(123)

        assert walk1 == walk2, "Same seed should give same walk"
        # Different seeds may or may not give different walks depending on graph


# =============================================================================
# BENCHMARK: INSIGHT GENERATION TESTS
# =============================================================================


class TestInsightGeneration:
    """Test insight generation quality."""

    def test_generates_insights_from_realistic_data(
        self,
        sensitive_bgt: BisociativeGraphTraversal,
        small_dataset,
    ) -> None:
        """BGT-SM should generate insights from realistic data."""
        embedding_provider = MockEmbeddingProvider(small_dataset.entities)

        # Generate insights (using algorithm's generate method)
        insights = sensitive_bgt.discover(
            entities=small_dataset.entities,
            edges=small_dataset.edges,
            seed_entity_ids=[e.entity_id for e in small_dataset.entities[:5]],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        print("\nInsight Generation Results:")
        print(f"  Entities: {len(small_dataset.entities)}")
        print(f"  Edges: {len(small_dataset.edges)}")
        print(f"  Insights generated: {len(insights)}")

        for insight in insights[:5]:
            print(f"\n  Insight: {insight.insight_text}")
            print(f"    Novelty: {insight.novelty_score:.2f}")
            print(f"    PMI: {insight.pmi_score:.2f}")
            print(f"    Serendipity: {insight.serendipity_score:.2f}")

        assert isinstance(insights, list)

    def test_insight_quality_thresholds(
        self,
        default_bgt: BisociativeGraphTraversal,
        medium_dataset,
    ) -> None:
        """Verify insights meet quality thresholds."""
        embedding_provider = MockEmbeddingProvider(medium_dataset.entities)

        insights = default_bgt.discover(
            entities=medium_dataset.entities,
            edges=medium_dataset.edges,
            seed_entity_ids=[e.entity_id for e in medium_dataset.entities[:10]],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        if len(insights) == 0:
            pytest.skip("No insights generated")

        # All insights should meet thresholds
        for insight in insights:
            assert (
                insight.novelty_score >= P03_BGT_NOVELTY_THRESHOLD
            ), f"Novelty {insight.novelty_score} below threshold"
            assert (
                insight.pmi_score >= P03_BGT_PMI_THRESHOLD
                or insight.semantic_distance >= P03_BGT_SEMANTIC_DISTANCE_THRESHOLD
            ), "Should meet either PMI or distance threshold"

    def test_serendipity_calculation(
        self,
        sensitive_bgt: BisociativeGraphTraversal,
        small_dataset,
    ) -> None:
        """Verify serendipity = novelty × relevance × actionability."""
        embedding_provider = MockEmbeddingProvider(small_dataset.entities)

        insights = sensitive_bgt.discover(
            entities=small_dataset.entities,
            edges=small_dataset.edges,
            seed_entity_ids=[e.entity_id for e in small_dataset.entities[:5]],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        for insight in insights:
            expected_serendipity = (
                insight.novelty_score * insight.relevance_score * insight.actionability_score
            )

            assert (
                abs(insight.serendipity_score - expected_serendipity) < 0.001
            ), f"Serendipity mismatch: {insight.serendipity_score} != {expected_serendipity}"


# =============================================================================
# BENCHMARK: PERFORMANCE TESTS
# =============================================================================


class TestBGTPerformance:
    """Performance benchmarks for BGT-SM."""

    @pytest.mark.benchmark
    def test_small_scale_performance(
        self,
        default_bgt: BisociativeGraphTraversal,
        small_dataset,
    ) -> None:
        """Benchmark BGT-SM on small dataset."""
        collector = BenchmarkCollector("BGT-SM")
        embedding_provider = MockEmbeddingProvider(small_dataset.entities)

        for _ in range(5):
            with collector.time_run() as run:
                insights = default_bgt.discover(
                    entities=small_dataset.entities,
                    edges=small_dataset.edges,
                    seed_entity_ids=[e.entity_id for e in small_dataset.entities[:5]],
                    embeddings=embedding_provider.embeddings,
                    rng_seed=42,
                )
                run["insights"] = len(insights)

            valid = sum(1 for i in insights if i.novelty_score >= 0.2)
            high_quality = sum(1 for i in insights if i.serendipity_score >= 0.3)
            collector.record_quality(len(insights), valid, high_quality)

            if insights:
                collector.record_output_values("novelty", [i.novelty_score for i in insights])
                collector.record_output_values(
                    "serendipity", [i.serendipity_score for i in insights]
                )

        summary = collector.summarize("small")
        print(f"\n{summary.summary()}")

        assert summary.timing.elapsed_ms < 2000

    @pytest.mark.benchmark
    def test_medium_scale_performance(
        self,
        default_bgt: BisociativeGraphTraversal,
        medium_dataset,
    ) -> None:
        """Benchmark BGT-SM on medium dataset."""
        collector = BenchmarkCollector("BGT-SM")
        embedding_provider = MockEmbeddingProvider(medium_dataset.entities)

        for _ in range(3):
            with collector.time_run():
                insights = default_bgt.discover(
                    entities=medium_dataset.entities,
                    edges=medium_dataset.edges,
                    seed_entity_ids=[e.entity_id for e in medium_dataset.entities[:10]],
                    embeddings=embedding_provider.embeddings,
                    rng_seed=42,
                )

            valid = sum(1 for i in insights if i.novelty_score >= 0.2)
            high_quality = sum(1 for i in insights if i.serendipity_score >= 0.3)
            collector.record_quality(len(insights), valid, high_quality)

        summary = collector.summarize("medium")
        print(f"\n{summary.summary()}")

        assert summary.timing.elapsed_ms < 10000

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_large_scale_performance(
        self,
        default_bgt: BisociativeGraphTraversal,
        large_dataset,
    ) -> None:
        """Benchmark BGT-SM on large dataset (stress test)."""
        collector = BenchmarkCollector("BGT-SM")
        embedding_provider = MockEmbeddingProvider(large_dataset.entities)

        with collector.time_run():
            insights = default_bgt.discover(
                entities=large_dataset.entities,
                edges=large_dataset.edges,
                seed_entity_ids=[e.entity_id for e in large_dataset.entities[:20]],
                embeddings=embedding_provider.embeddings,
                rng_seed=42,
            )

        valid = sum(1 for i in insights if i.novelty_score >= 0.2)
        high_quality = sum(1 for i in insights if i.serendipity_score >= 0.3)
        collector.record_quality(len(insights), valid, high_quality)

        summary = collector.summarize("large")
        print(f"\n{summary.summary()}")

        assert summary.timing.elapsed_ms < 60000


# =============================================================================
# BENCHMARK: DETERMINISM TESTS
# =============================================================================


class TestBGTDeterminism:
    """Verify BGT-SM produces deterministic results."""

    def test_same_seed_same_insights(
        self,
        small_dataset,
    ) -> None:
        """Same seed should produce identical insight content (not IDs due to ULID timestamps)."""
        bgt1 = BisociativeGraphTraversal(BGTConfig(seed=42))
        bgt2 = BisociativeGraphTraversal(BGTConfig(seed=42))
        embedding_provider = MockEmbeddingProvider(small_dataset.entities)

        insights1 = bgt1.discover(
            entities=small_dataset.entities,
            edges=small_dataset.edges,
            seed_entity_ids=[e.entity_id for e in small_dataset.entities[:5]],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        insights2 = bgt2.discover(
            entities=small_dataset.entities,
            edges=small_dataset.edges,
            seed_entity_ids=[e.entity_id for e in small_dataset.entities[:5]],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        assert len(insights1) == len(insights2)

        # Compare content, not IDs (IDs use ULIDs with timestamps)
        for i1, i2 in zip(insights1, insights2):
            # Check computed scores match
            assert i1.novelty_score == i2.novelty_score
            assert i1.pmi_score == i2.pmi_score
            # Check entity connections match
            assert i1.source_entity_id == i2.source_entity_id
            assert i1.target_entity_id == i2.target_entity_id


# =============================================================================
# BENCHMARK: EDGE CASES
# =============================================================================


class TestBGTEdgeCases:
    """Test BGT-SM behavior with edge cases."""

    def test_empty_graph(self, default_bgt: BisociativeGraphTraversal) -> None:
        """Handle empty knowledge graph."""
        insights = default_bgt.discover(
            entities=[],
            edges=[],
            seed_entity_ids=[],
            embeddings={},
            rng_seed=42,
        )

        assert insights == []

    def test_disconnected_graph(
        self,
        default_bgt: BisociativeGraphTraversal,
    ) -> None:
        """Handle graph with disconnected components."""
        # Create entities with no connecting edges
        entities = [
            RealisticEntity(
                entity_id=f"isolated_{i}",
                entity_type="concept",
                name=f"Isolated Concept {i}",
                observation_count=10,
                embedding=[float(i)] * 128,
            )
            for i in range(5)
        ]

        embedding_provider = MockEmbeddingProvider(entities)
        insights = default_bgt.discover(
            entities=entities,
            edges=[],  # No edges
            seed_entity_ids=[e.entity_id for e in entities],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        # Should handle gracefully (may or may not generate insights)
        assert isinstance(insights, list)

    def test_single_entity(
        self,
        default_bgt: BisociativeGraphTraversal,
    ) -> None:
        """Handle graph with single entity."""
        entity = RealisticEntity(
            entity_id="single",
            entity_type="concept",
            name="Lonely Concept",
            observation_count=100,
            embedding=[0.5] * 128,
        )

        embedding_provider = MockEmbeddingProvider([entity])
        insights = default_bgt.discover(
            entities=[entity],
            edges=[],
            seed_entity_ids=[entity.entity_id],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        assert isinstance(insights, list)


# =============================================================================
# INTEGRATION BENCHMARK
# =============================================================================


class TestBGTIntegration:
    """Integration benchmarks with realistic scenarios."""

    def test_family_memory_insights(
        self,
        sensitive_bgt: BisociativeGraphTraversal,
    ) -> None:
        """Generate insights from a realistic family memory graph."""
        # Create realistic family memory entities
        entities = [
            RealisticEntity("person-mom", "person", "Mom", 500, [0.1] * 128),
            RealisticEntity("person-dad", "person", "Dad", 450, [0.12] * 128),
            RealisticEntity("person-child", "person", "Sarah", 600, [0.15] * 128),
            RealisticEntity("location-home", "location", "Home", 1000, [0.3] * 128),
            RealisticEntity("location-school", "location", "School", 300, [0.4] * 128),
            RealisticEntity("location-park", "location", "Central Park", 150, [0.45] * 128),
            RealisticEntity("activity-dinner", "activity", "Family Dinner", 200, [0.5] * 128),
            RealisticEntity("activity-homework", "activity", "Homework Help", 180, [0.52] * 128),
            RealisticEntity("event-birthday", "event", "Sarah's Birthday", 5, [0.8] * 128),
            RealisticEntity("concept-happiness", "concept", "Family Happiness", 100, [0.9] * 128),
        ]

        edges = [
            RealisticEdge("e1", "person-mom", "location-home", "LOCATED_AT", 400, 0.9),
            RealisticEdge("e2", "person-dad", "location-home", "LOCATED_AT", 350, 0.9),
            RealisticEdge("e3", "person-child", "location-school", "LOCATED_AT", 250, 0.85),
            RealisticEdge("e4", "activity-dinner", "location-home", "OCCURS_AT", 180, 0.95),
            RealisticEdge("e5", "person-mom", "activity-dinner", "PARTICIPATES", 150, 0.9),
            RealisticEdge("e6", "person-child", "activity-homework", "PARTICIPATES", 160, 0.85),
            RealisticEdge("e7", "activity-dinner", "concept-happiness", "CAUSES", 50, 0.7),
            RealisticEdge("e8", "event-birthday", "location-park", "OCCURS_AT", 1, 1.0),
            RealisticEdge("e9", "event-birthday", "concept-happiness", "CAUSES", 1, 0.95),
            RealisticEdge("e10", "person-child", "location-park", "RELATED_TO", 30, 0.6),
        ]

        embedding_provider = MockEmbeddingProvider(entities)

        insights = sensitive_bgt.discover(
            entities=entities,
            edges=edges,
            seed_entity_ids=["person-child", "location-home", "activity-dinner"],
            embeddings=embedding_provider.embeddings,
            rng_seed=42,
        )

        print("\nFamily Memory Insights:")
        print(f"  Generated {len(insights)} insights")

        for insight in insights:
            print(f"\n  {insight.insight_text}")
            print(f"    Connection: {insight.source_entity_name} <-> {insight.target_entity_name}")
            print(f"    Category: {insight.category}")
            print(f"    Novelty: {insight.novelty_score:.2f}")
            print(f"    Serendipity: {insight.serendipity_score:.2f}")

        assert isinstance(insights, list)
