"""
Tests for CentroidCalculator — Episode centroid embedding computation.

Issue 4.2.4: Write episode candidates to staged writes container

Tests:
    1. test_centroid_uniform_weighting: All events contribute equally
    2. test_centroid_importance_weighting: High importance = higher weight
    3. test_centroid_recency_weighting: Recent events = higher weight
    4. test_centroid_hybrid_weighting: 70% importance + 30% recency
    5. test_centroid_l2_normalized: Centroid has unit norm
    6. test_variance_computed: Variance in [0, 1] range
    7. test_episode_candidate_created: All fields populated
    8. test_staged_output_metadata: cluster_count, noise_count correct
    9. test_finalize_computes_aggregates: avg_cluster_size, cohesion_avg
    10. test_weighting_strategies: All strategies produce valid output
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.centroid_calculator import (
    CentroidCalculator,
    CentroidResult,
    EpisodeCandidate,
    R2StagedOutput,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]]
    importance_score: float = 0.5
    sentiment_score: float = 0.5


def make_embedding(seed: int, dim: int = 768) -> List[float]:
    """Create deterministic embedding from seed."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / norm).tolist()


# =============================================================================
# Weighting Strategy Tests
# =============================================================================


class TestWeightingStrategies:
    """Test CentroidCalculator weighting strategies."""

    def test_centroid_uniform_weighting(self) -> None:
        """Uniform: all events contribute equally (1/n each)."""
        events = [
            MockEvent("e1", 1000, make_embedding(1), importance_score=0.1),
            MockEvent("e2", 2000, make_embedding(2), importance_score=0.9),
            MockEvent("e3", 3000, make_embedding(3), importance_score=0.5),
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="uniform")

        # All weights should be equal (1/3)
        expected = np.ones(3) / 3
        np.testing.assert_array_almost_equal(weights, expected)

    def test_centroid_importance_weighting(self) -> None:
        """Importance: weight by importance_score."""
        events = [
            MockEvent("e1", 1000, make_embedding(1), importance_score=0.1),
            MockEvent("e2", 2000, make_embedding(2), importance_score=0.9),
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="importance")

        # Higher importance should have higher weight
        assert weights[1] > weights[0]
        # Weights should sum to 1
        assert weights.sum() == pytest.approx(1.0)

    def test_centroid_recency_weighting(self) -> None:
        """Recency: recent events have higher weight."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),  # Oldest
            MockEvent("e2", 2000, make_embedding(2)),
            MockEvent("e3", 3000, make_embedding(3)),  # Most recent
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="recency")

        # Most recent should have highest weight
        assert weights[2] > weights[0]
        # Weights should sum to 1
        assert weights.sum() == pytest.approx(1.0)

    def test_centroid_hybrid_weighting(self) -> None:
        """Hybrid: 70% importance + 30% recency."""
        events = [
            MockEvent("e1", 1000, make_embedding(1), importance_score=0.9),  # High importance, old
            MockEvent(
                "e2", 3000, make_embedding(2), importance_score=0.1
            ),  # Low importance, recent
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="hybrid")

        # Weights should sum to 1
        assert weights.sum() == pytest.approx(1.0)
        # Both factors matter
        assert 0 < weights[0] < 1
        assert 0 < weights[1] < 1

    def test_weighting_same_timestamps(self) -> None:
        """Recency weighting with same timestamps falls back to uniform."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 1000, make_embedding(2)),  # Same timestamp
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="recency")

        # Should be uniform when all timestamps are equal
        expected = np.ones(2) / 2
        np.testing.assert_array_almost_equal(weights, expected)


# =============================================================================
# Centroid Computation Tests
# =============================================================================


class TestCentroidComputation:
    """Test CentroidCalculator centroid computation."""

    def test_centroid_l2_normalized(self) -> None:
        """Centroid has unit norm (L2-normalized)."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
        ]

        calc = CentroidCalculator(normalize=True)
        centroid = calc.compute_centroid(events)

        norm = np.linalg.norm(centroid)
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_centroid_not_normalized(self) -> None:
        """Centroid without normalization."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
        ]

        calc = CentroidCalculator(normalize=False)
        centroid = calc.compute_centroid(events)

        # Not normalized, so norm may differ from 1
        assert centroid is not None
        assert len(centroid) == 768

    def test_centroid_single_event(self) -> None:
        """Centroid of single event equals that event's embedding."""
        emb = make_embedding(42)
        events = [MockEvent("e1", 1000, emb)]

        calc = CentroidCalculator()
        centroid = calc.compute_centroid(events)

        # Should be (almost) equal to the original embedding
        original = np.asarray(emb, dtype=np.float32)
        original = original / np.linalg.norm(original)
        np.testing.assert_array_almost_equal(centroid, original, decimal=5)

    def test_centroid_no_valid_embeddings(self) -> None:
        """Centroid computation fails with no valid embeddings."""
        events = [
            MockEvent("e1", 1000, None),
            MockEvent("e2", 2000, None),
        ]

        calc = CentroidCalculator()

        with pytest.raises(ValueError, match="No events with valid embeddings"):
            calc.compute_centroid(events)


# =============================================================================
# Variance Computation Tests
# =============================================================================


class TestVarianceComputation:
    """Test CentroidCalculator variance computation."""

    def test_variance_computed(self) -> None:
        """Variance in [0, 1] range."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
        ]

        calc = CentroidCalculator()
        result = calc.compute(events)

        # Variance should be in valid range
        assert 0.0 <= result.variance <= 1.0

    def test_variance_identical_embeddings(self) -> None:
        """Variance is 0 for identical embeddings."""
        emb = make_embedding(42)
        events = [
            MockEvent("e1", 1000, emb),
            MockEvent("e2", 2000, emb),  # Same embedding
        ]

        calc = CentroidCalculator()
        result = calc.compute(events)

        # Should be very close to 0
        assert result.variance == pytest.approx(0.0, abs=1e-5)

    def test_variance_single_event(self) -> None:
        """Variance is 0 for single event."""
        events = [MockEvent("e1", 1000, make_embedding(1))]

        calc = CentroidCalculator()
        result = calc.compute(events)

        assert result.variance == 0.0


# =============================================================================
# CentroidResult Tests
# =============================================================================


class TestCentroidResult:
    """Test CentroidResult dataclass."""

    def test_compute_returns_result(self) -> None:
        """compute() returns CentroidResult with all fields."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
        ]

        calc = CentroidCalculator()
        result = calc.compute(events, strategy="hybrid")

        assert isinstance(result, CentroidResult)
        assert len(result.centroid) == 768
        assert 0.0 <= result.variance <= 1.0
        assert len(result.weights) == 2
        assert result.strategy == "hybrid"
        assert result.event_count == 2

    def test_centroid_list_property(self) -> None:
        """centroid_list returns Python list."""
        events = [MockEvent("e1", 1000, make_embedding(1))]

        calc = CentroidCalculator()
        result = calc.compute(events)

        centroid_list = result.centroid_list
        assert isinstance(centroid_list, list)
        assert len(centroid_list) == 768

    def test_compute_empty_returns_zero(self) -> None:
        """compute() with no valid embeddings returns zero result."""
        events = [MockEvent("e1", 1000, None)]

        calc = CentroidCalculator()
        result = calc.compute(events)

        assert result.event_count == 0
        assert np.allclose(result.centroid, 0.0)


# =============================================================================
# EpisodeCandidate Tests
# =============================================================================


class TestEpisodeCandidate:
    """Test EpisodeCandidate dataclass."""

    def test_episode_candidate_created(self) -> None:
        """create_episode_candidate populates all fields."""
        events = [
            MockEvent("e1", 1000, make_embedding(1), sentiment_score=0.8),
            MockEvent("e2", 2000, make_embedding(2), sentiment_score=0.6),
        ]

        calc = CentroidCalculator()
        candidate = calc.create_episode_candidate(
            cluster_id="cluster-123",
            space_id="space-456",
            events=events,
            cohesion_score=0.9,
            temporal_start=1000,
            temporal_end=2000,
        )

        assert candidate.cluster_id == "cluster-123"
        assert candidate.space_id == "space-456"
        assert candidate.event_ids == ["e1", "e2"]
        assert candidate.event_count == 2
        assert candidate.centroid_embedding is not None
        assert len(candidate.centroid_embedding) == 768
        assert candidate.temporal_start == 1000
        assert candidate.temporal_end == 2000
        assert candidate.cohesion_score == 0.9
        assert candidate.variance >= 0.0
        assert candidate.dominant_sentiment == pytest.approx(0.7, abs=0.1)

    def test_duration_ms_property(self) -> None:
        """duration_ms computed correctly."""
        candidate = EpisodeCandidate(
            cluster_id="c1",
            space_id="s1",
            temporal_start=1000,
            temporal_end=5000,
        )

        assert candidate.duration_ms == 4000


# =============================================================================
# R2StagedOutput Tests
# =============================================================================


class TestR2StagedOutput:
    """Test R2StagedOutput container."""

    def test_add_candidate(self) -> None:
        """add_candidate updates metadata."""
        output = R2StagedOutput()

        candidate1 = EpisodeCandidate(
            cluster_id="c1",
            space_id="s1",
            event_count=3,
            is_noise=False,
        )
        candidate2 = EpisodeCandidate(
            cluster_id="noise-1",
            space_id="s1",
            event_count=1,
            is_noise=True,
        )

        output.add_candidate(candidate1)
        output.add_candidate(candidate2)

        assert output.cluster_count == 1
        assert output.noise_count == 1
        assert output.total_events_processed == 4

    def test_finalize_computes_aggregates(self) -> None:
        """finalize() computes avg_cluster_size and cohesion_avg."""
        output = R2StagedOutput()

        # Add two non-noise clusters
        output.add_candidate(
            EpisodeCandidate(
                cluster_id="c1",
                space_id="s1",
                event_count=4,
                cohesion_score=0.8,
                is_noise=False,
            )
        )
        output.add_candidate(
            EpisodeCandidate(
                cluster_id="c2",
                space_id="s1",
                event_count=2,
                cohesion_score=0.6,
                is_noise=False,
            )
        )

        output.finalize()

        # Average cluster size: (4 + 2) / 2 = 3.0
        assert output.avg_cluster_size == 3.0
        # Average cohesion: (0.8 + 0.6) / 2 = 0.7
        assert output.batch_cohesion_avg == pytest.approx(0.7)

    def test_singleton_rate(self) -> None:
        """singleton_rate computed correctly."""
        output = R2StagedOutput()

        # 2 noise, 3 total events
        output.add_candidate(
            EpisodeCandidate(cluster_id="noise-1", space_id="s1", event_count=1, is_noise=True)
        )
        output.add_candidate(
            EpisodeCandidate(cluster_id="noise-2", space_id="s1", event_count=1, is_noise=True)
        )
        output.add_candidate(
            EpisodeCandidate(cluster_id="c1", space_id="s1", event_count=1, is_noise=False)
        )

        # 2 noise / 3 total = 0.666...
        assert output.singleton_rate == pytest.approx(2 / 3, abs=0.01)

    def test_to_dict(self) -> None:
        """to_dict returns serializable dictionary."""
        output = R2StagedOutput()
        output.add_candidate(
            EpisodeCandidate(cluster_id="c1", space_id="s1", event_count=2, is_noise=False)
        )
        output.finalize()

        data = output.to_dict()

        assert "cluster_count" in data
        assert "noise_count" in data
        assert "avg_cluster_size" in data
        assert "total_events_processed" in data
        assert "batch_silhouette_score" in data
        assert "singleton_rate" in data


# =============================================================================
# Event Update Tests
# =============================================================================


class TestEventUpdate:
    """Test CentroidCalculator event updates."""

    def test_update_event_centroid_distances(self) -> None:
        """update_event_centroid_distances sets centroid_distance."""

        @dataclass
        class MutableEvent:
            event_id: str
            timestamp: int
            embedding_768: Optional[List[float]]
            importance_score: float = 0.5
            centroid_distance: float = 0.0

        emb = make_embedding(42)
        events = [
            MutableEvent("e1", 1000, emb),
            MutableEvent("e2", 2000, emb),
        ]

        calc = CentroidCalculator()
        centroid = calc.compute_centroid(events)
        calc.update_event_centroid_distances(events, centroid)

        # Both events should have centroid_distance set
        # Since embeddings are similar to centroid, distance should be low
        for event in events:
            assert 0.0 <= event.centroid_distance <= 1.0
