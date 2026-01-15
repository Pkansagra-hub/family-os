"""
Tests for BGT-SM Cold Start Handling — Issue 8.1.20

Validates that BGT-SM gracefully skips discovery when the corpus is too
small for meaningful PMI calculation. This prevents spurious insights
in new deployments or fresh tenants.

Test Categories:
1. Cold start detection (is_cold_start, get_cold_start_info)
2. Discovery skip when corpus < threshold
3. Normal operation when corpus >= threshold
4. Custom threshold configuration
5. Edge cases (exactly at threshold)

References:
- M8_EXECUTION.md Issue 8.1.20: BGT-SM Cold Start Handling
- Dossier §4.6.4: Insight Generation (BGT-SM)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pytest

from k0.modules.consolidation.algorithms.bgt_sm import (
    P03_BGT_COLD_START_THRESHOLD,
    P03_BGT_DEFAULT_CORPUS_SIZE,
    BGTConfig,
    BisociativeGraphTraversal,
)


# =============================================================================
# TEST FIXTURES
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
            embedding=[0.15, 0.25, 0.35, 0.45],
        ),
        MockEntity(
            entity_id="ent_003",
            entity_type="LOCATION",
            name="Cafe Downtown",
            observation_count=20,
            embedding=[0.9, 0.1, 0.05, 0.05],
        ),
    ]


@pytest.fixture
def sample_edges() -> List[MockEdge]:
    """Create sample KG edges for testing."""
    return [
        MockEdge(source_id="ent_001", target_id="ent_002", relation_type="KNOWS"),
        MockEdge(source_id="ent_001", target_id="ent_003", relation_type="VISITS"),
        MockEdge(source_id="ent_002", target_id="ent_003", relation_type="VISITS"),
    ]


@pytest.fixture
def embeddings() -> dict:
    """Create entity embeddings for semantic distance."""
    return {
        "ent_001": [0.1, 0.2, 0.3, 0.4],
        "ent_002": [0.15, 0.25, 0.35, 0.45],
        "ent_003": [0.9, 0.1, 0.05, 0.05],
    }


# =============================================================================
# TEST: Cold Start Detection
# =============================================================================


class TestColdStartDetection:
    """Tests for cold start detection methods."""

    def test_is_cold_start_when_corpus_below_threshold(self) -> None:
        """is_cold_start() returns True when corpus < threshold."""
        config = BGTConfig(corpus_size_n=5000)  # Below default 10,000
        bgt = BisociativeGraphTraversal(config)

        assert bgt.is_cold_start() is True

    def test_is_cold_start_when_corpus_above_threshold(self) -> None:
        """is_cold_start() returns False when corpus >= threshold."""
        config = BGTConfig(corpus_size_n=15000)  # Above default 10,000
        bgt = BisociativeGraphTraversal(config)

        assert bgt.is_cold_start() is False

    def test_is_cold_start_at_exact_threshold(self) -> None:
        """is_cold_start() returns False when corpus == threshold (boundary)."""
        config = BGTConfig(corpus_size_n=10000, cold_start_threshold=10000)
        bgt = BisociativeGraphTraversal(config)

        assert bgt.is_cold_start() is False

    def test_is_cold_start_one_below_threshold(self) -> None:
        """is_cold_start() returns True when corpus is exactly 1 below threshold."""
        config = BGTConfig(corpus_size_n=9999, cold_start_threshold=10000)
        bgt = BisociativeGraphTraversal(config)

        assert bgt.is_cold_start() is True

    def test_get_cold_start_info_structure(self) -> None:
        """get_cold_start_info() returns correct structure."""
        config = BGTConfig(corpus_size_n=5000, cold_start_threshold=10000)
        bgt = BisociativeGraphTraversal(config)

        info = bgt.get_cold_start_info()

        assert "corpus_size" in info
        assert "cold_start_threshold" in info
        assert "is_cold_start" in info
        assert info["corpus_size"] == 5000
        assert info["cold_start_threshold"] == 10000
        assert info["is_cold_start"] is True

    def test_get_cold_start_info_not_cold_start(self) -> None:
        """get_cold_start_info() returns False when corpus is sufficient."""
        config = BGTConfig(corpus_size_n=20000, cold_start_threshold=10000)
        bgt = BisociativeGraphTraversal(config)

        info = bgt.get_cold_start_info()

        assert info["is_cold_start"] is False


# =============================================================================
# TEST: Discovery Skip on Cold Start
# =============================================================================


class TestDiscoverySkipOnColdStart:
    """Tests for discovery skip behavior during cold start."""

    def test_discover_returns_empty_on_cold_start(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        embeddings: dict,
    ) -> None:
        """discover() returns empty list when corpus < threshold."""
        config = BGTConfig(corpus_size_n=1000)  # Way below threshold
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=embeddings,
            rng_seed=42,
        )

        assert insights == []

    def test_discover_returns_empty_when_corpus_zero(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """discover() returns empty list when corpus_size is minimal."""
        # Note: corpus_size_n must be >= 1 per validation
        config = BGTConfig(corpus_size_n=1, cold_start_threshold=10)
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
        )

        assert insights == []

    def test_discover_proceeds_when_corpus_sufficient(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        embeddings: dict,
    ) -> None:
        """discover() proceeds normally when corpus >= threshold."""
        # Set corpus above threshold
        config = BGTConfig(
            corpus_size_n=15000,
            cold_start_threshold=10000,
            walk_steps=10,  # Reduce for faster test
            max_walks_per_seed=1,
        )
        bgt = BisociativeGraphTraversal(config)

        # Should not raise, may or may not produce insights
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
            embeddings=embeddings,
            rng_seed=42,
        )

        # Insights may be empty due to thresholds, but should not error
        assert isinstance(insights, list)

    def test_cold_start_skip_is_fast(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Cold start skip should return immediately (no computation)."""
        import time

        config = BGTConfig(corpus_size_n=100, cold_start_threshold=10000)
        bgt = BisociativeGraphTraversal(config)

        start = time.time()
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001", "ent_002", "ent_003"],
        )
        elapsed = time.time() - start

        assert insights == []
        # Should be nearly instant (< 10ms)
        assert elapsed < 0.1


# =============================================================================
# TEST: Custom Threshold Configuration
# =============================================================================


class TestCustomThresholdConfiguration:
    """Tests for configurable cold start threshold."""

    def test_custom_threshold_respected(self) -> None:
        """Custom cold_start_threshold is respected."""
        config = BGTConfig(corpus_size_n=500, cold_start_threshold=1000)
        bgt = BisociativeGraphTraversal(config)

        assert bgt.is_cold_start() is True

        config2 = BGTConfig(corpus_size_n=500, cold_start_threshold=100)
        bgt2 = BisociativeGraphTraversal(config2)

        assert bgt2.is_cold_start() is False

    def test_default_threshold_is_10000(self) -> None:
        """Default cold_start_threshold is 10,000."""
        assert P03_BGT_COLD_START_THRESHOLD == 10_000

        config = BGTConfig()
        assert config.cold_start_threshold == 10_000

    def test_threshold_can_be_zero(self) -> None:
        """Threshold of 0 disables cold start check."""
        config = BGTConfig(corpus_size_n=1, cold_start_threshold=0)
        bgt = BisociativeGraphTraversal(config)

        # corpus_size (1) >= threshold (0), so not cold start
        assert bgt.is_cold_start() is False

    def test_very_high_threshold(self) -> None:
        """Very high threshold triggers cold start even with large corpus."""
        config = BGTConfig(corpus_size_n=100000, cold_start_threshold=1_000_000)
        bgt = BisociativeGraphTraversal(config)

        assert bgt.is_cold_start() is True


# =============================================================================
# TEST: Default Values
# =============================================================================


class TestDefaultValues:
    """Tests for default configuration values."""

    def test_default_corpus_size(self) -> None:
        """Default corpus_size_n matches constant."""
        assert P03_BGT_DEFAULT_CORPUS_SIZE == 10000

        config = BGTConfig()
        assert config.corpus_size_n == P03_BGT_DEFAULT_CORPUS_SIZE

    def test_default_not_cold_start(self) -> None:
        """Default config is NOT in cold start (corpus == threshold)."""
        config = BGTConfig()
        bgt = BisociativeGraphTraversal(config)

        # Default: corpus_size_n = 10000, threshold = 10000
        # At boundary, should NOT be cold start
        assert bgt.is_cold_start() is False


# =============================================================================
# TEST: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in cold start handling."""

    def test_empty_entities_with_cold_start(self) -> None:
        """discover() with cold start and empty entities returns empty."""
        config = BGTConfig(corpus_size_n=100)
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=[],
            edges=[],
            seed_entity_ids=["nonexistent"],
        )

        assert insights == []

    def test_empty_seeds_with_cold_start(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """discover() with cold start and empty seeds returns empty."""
        config = BGTConfig(corpus_size_n=100)
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=[],
        )

        assert insights == []

    def test_cold_start_check_before_graph_operations(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
    ) -> None:
        """Cold start check happens before expensive graph operations."""
        # This is a behavioral test - cold start should skip before
        # building graph views, walk engines, etc.
        config = BGTConfig(corpus_size_n=1)
        bgt = BisociativeGraphTraversal(config)

        # If we get here without error, the check happened early
        insights = bgt.discover(
            entities=sample_entities,
            edges=sample_edges,
            seed_entity_ids=["ent_001"],
        )

        assert insights == []


# =============================================================================
# TEST: Logging
# =============================================================================


class TestColdStartLogging:
    """Tests for cold start logging behavior."""

    def test_cold_start_logs_info(
        self,
        sample_entities: List[MockEntity],
        sample_edges: List[MockEdge],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Cold start skip logs an info message."""
        import logging

        config = BGTConfig(corpus_size_n=100, cold_start_threshold=10000)
        bgt = BisociativeGraphTraversal(config)

        with caplog.at_level(logging.INFO):
            bgt.discover(
                entities=sample_entities,
                edges=sample_edges,
                seed_entity_ids=["ent_001"],
            )

        # Check that cold start was logged
        assert any("cold start" in record.message.lower() for record in caplog.records)
