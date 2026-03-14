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
# Recency Exponential Strategy Tests (M4-RSCH-01 winner)
# =============================================================================


class TestRecencyExpStrategy:
    """Test recency_exp weighting strategy (M4-RSCH-01: MRR=0.9006)."""

    def test_recency_exp_recent_events_weighted_higher(self) -> None:
        """Most recent event gets highest weight with exponential decay."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),  # Oldest
            MockEvent("e2", 2000, make_embedding(2)),
            MockEvent("e3", 3000, make_embedding(3)),  # Most recent
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="recency_exp")

        assert weights[2] > weights[1] > weights[0]
        assert weights.sum() == pytest.approx(1.0)

    def test_recency_exp_equal_timestamps_uniform(self) -> None:
        """Equal timestamps produce uniform weights."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 1000, make_embedding(2)),
            MockEvent("e3", 1000, make_embedding(3)),
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="recency_exp")

        expected = np.ones(3) / 3
        np.testing.assert_array_almost_equal(weights, expected)

    def test_recency_exp_bounded_ratio(self) -> None:
        """Weight ratio between newest and oldest is bounded by e (~2.718)."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),  # Oldest
            MockEvent("e2", 5000, make_embedding(2)),  # Most recent
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="recency_exp")

        # exp(0)=1, exp(1)=e, ratio = e/1 = 2.718
        ratio = weights[1] / weights[0]
        assert ratio == pytest.approx(np.e, rel=0.01)

    def test_recency_exp_does_not_collapse_like_linear(self) -> None:
        """Oldest event still has meaningful weight (unlike linear collapse)."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),  # Very old
            MockEvent("e2", 50000, make_embedding(2)),
            MockEvent("e3", 100000, make_embedding(3)),  # Very recent
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy="recency_exp")

        # Oldest event should still have > 5% weight (not collapsed)
        assert weights[0] > 0.05
        assert weights.sum() == pytest.approx(1.0)

    def test_recency_exp_compute_full_result(self) -> None:
        """recency_exp works through the full compute() path."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
            MockEvent("e3", 3000, make_embedding(3)),
        ]

        calc = CentroidCalculator(default_strategy="recency_exp")
        result = calc.compute(events)

        assert isinstance(result, CentroidResult)
        assert result.strategy == "recency_exp"
        assert result.event_count == 3
        assert len(result.centroid) == 768
        assert np.linalg.norm(result.centroid) == pytest.approx(1.0, abs=1e-6)

    def test_recency_exp_via_enum(self) -> None:
        """Strategy works when passed as WeightingStrategy enum."""
        from k0.modules.consolidation.algorithms.centroid_calculator import WeightingStrategy

        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 3000, make_embedding(2)),
        ]

        calc = CentroidCalculator()
        weights = calc.compute_weights(events, strategy=WeightingStrategy.RECENCY_EXP)

        assert weights[1] > weights[0]
        assert weights.sum() == pytest.approx(1.0)


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


# =============================================================================
# Secondary Centroid Selector Tests (M4-RSCH-02: best_of_all MRR=0.9627)
# =============================================================================


@dataclass
class RichMockEvent:
    """Mock event with affect and narrative fields for secondary centroid selection."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]]
    importance_score: float = 0.5
    sentiment_score: float = 0.5
    affect_valence: Optional[float] = None
    affect_arousal: Optional[float] = None
    narrative_thread_id: Optional[str] = None


class TestSecondaryCentroidSelector:
    """Test SecondaryCentroidSelector for multi-centroid episode representation."""

    def test_select_start_picks_earliest(self) -> None:
        """Start centroid is the event with earliest timestamp."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent("e2", 2000, make_embedding(2)),
            RichMockEvent("e1", 1000, make_embedding(1)),
            RichMockEvent("e3", 3000, make_embedding(3)),
        ]

        selector = SecondaryCentroidSelector()
        result = selector._select_start(events)

        assert result is not None
        assert result["event_id"] == "e1"

    def test_select_end_picks_latest(self) -> None:
        """End centroid is the event with latest timestamp."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent("e2", 2000, make_embedding(2)),
            RichMockEvent("e3", 3000, make_embedding(3)),
            RichMockEvent("e1", 1000, make_embedding(1)),
        ]

        selector = SecondaryCentroidSelector()
        result = selector._select_end(events)

        assert result is not None
        assert result["event_id"] == "e3"

    def test_emotional_peak_uses_affect_intensity(self) -> None:
        """Emotional peak selects event with highest abs(valence) + arousal."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent("calm", 1000, make_embedding(1), affect_valence=0.1, affect_arousal=0.2),
            RichMockEvent(
                "intense", 2000, make_embedding(2), affect_valence=-0.9, affect_arousal=0.8
            ),
            RichMockEvent("mild", 3000, make_embedding(3), affect_valence=0.3, affect_arousal=0.1),
        ]

        selector = SecondaryCentroidSelector()
        result = selector._select_emotional_peak(events)

        assert result is not None
        assert result["event_id"] == "intense"

    def test_emotional_peak_falls_back_to_sentiment(self) -> None:
        """When affect fields missing, use sentiment distance from neutral."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent("neutral", 1000, make_embedding(1), sentiment_score=0.5),
            RichMockEvent("sad", 2000, make_embedding(2), sentiment_score=0.05),
            RichMockEvent("mild", 3000, make_embedding(3), sentiment_score=0.6),
        ]

        selector = SecondaryCentroidSelector()
        result = selector._select_emotional_peak(events)

        assert result is not None
        assert result["event_id"] == "sad"  # Most distant from 0.5 neutral

    def test_narrative_anchor_picks_dominant_thread(self) -> None:
        """Narrative anchor picks event from most common thread."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent(
                "e1", 1000, make_embedding(1), narrative_thread_id="thread-A", importance_score=0.3
            ),
            RichMockEvent(
                "e2", 2000, make_embedding(2), narrative_thread_id="thread-A", importance_score=0.9
            ),
            RichMockEvent(
                "e3", 3000, make_embedding(3), narrative_thread_id="thread-B", importance_score=0.8
            ),
        ]

        selector = SecondaryCentroidSelector()
        result = selector._select_narrative_anchor(events)

        assert result is not None
        assert result["event_id"] == "e2"  # thread-A dominant, highest importance

    def test_narrative_anchor_none_without_threads(self) -> None:
        """Narrative anchor is None when no events have thread IDs."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent("e1", 1000, make_embedding(1)),
            RichMockEvent("e2", 2000, make_embedding(2)),
        ]

        selector = SecondaryCentroidSelector()
        result = selector._select_narrative_anchor(events)

        assert result is None

    def test_select_all_returns_all_roles(self) -> None:
        """select_all returns start, end, emotional_peak, narrative_anchor."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent(
                "e1",
                1000,
                make_embedding(1),
                affect_valence=-0.9,
                affect_arousal=0.8,
                narrative_thread_id="t1",
            ),
            RichMockEvent(
                "e2",
                2000,
                make_embedding(2),
                affect_valence=0.1,
                affect_arousal=0.1,
                narrative_thread_id="t1",
            ),
            RichMockEvent(
                "e3",
                3000,
                make_embedding(3),
                affect_valence=0.2,
                affect_arousal=0.2,
                narrative_thread_id="t2",
            ),
        ]

        selector = SecondaryCentroidSelector()
        result = selector.select_all(events)

        assert "start" in result
        assert "end" in result
        assert "emotional_peak" in result
        assert "narrative_anchor" in result
        assert result["start"]["event_id"] == "e1"
        assert result["end"]["event_id"] == "e3"
        assert result["emotional_peak"]["event_id"] == "e1"  # highest intensity
        assert result["narrative_anchor"]["event_id"] in ("e1", "e2")  # thread t1 dominant

    def test_select_all_skips_no_embedding_events(self) -> None:
        """Events without embeddings are excluded from all selectors."""
        from k0.modules.consolidation.algorithms.centroid_calculator import (
            SecondaryCentroidSelector,
        )

        events = [
            RichMockEvent("no_emb", 500, None, affect_valence=1.0, affect_arousal=1.0),
            RichMockEvent("has_emb", 1000, make_embedding(1)),
        ]

        selector = SecondaryCentroidSelector()
        result = selector.select_all(events)

        assert result["start"]["event_id"] == "has_emb"
        assert result["end"]["event_id"] == "has_emb"

    def test_candidate_centroid_metadata_populated(self) -> None:
        """create_episode_candidate populates centroid_metadata for multi-event clusters."""
        events = [
            RichMockEvent("e1", 1000, make_embedding(1), affect_valence=-0.8, affect_arousal=0.9),
            RichMockEvent("e2", 2000, make_embedding(2), affect_valence=0.1, affect_arousal=0.1),
            RichMockEvent("e3", 3000, make_embedding(3), affect_valence=0.2, affect_arousal=0.2),
        ]

        calc = CentroidCalculator()
        candidate = calc.create_episode_candidate(
            cluster_id="c1",
            space_id="s1",
            events=events,
            cohesion_score=0.8,
            temporal_start=1000,
            temporal_end=3000,
        )

        assert candidate.centroid_metadata is not None
        assert candidate.centroid_metadata["version"] == 1
        centroids = candidate.centroid_metadata["centroids"]
        assert "start" in centroids
        assert "end" in centroids
        assert "emotional_peak" in centroids
        assert centroids["start"]["event_id"] == "e1"
        assert centroids["end"]["event_id"] == "e3"
        assert centroids["emotional_peak"]["event_id"] == "e1"

    def test_candidate_noise_has_no_centroid_metadata(self) -> None:
        """Noise/singleton candidates do not have centroid_metadata."""
        events = [RichMockEvent("e1", 1000, make_embedding(1))]

        calc = CentroidCalculator()
        candidate = calc.create_episode_candidate(
            cluster_id="noise-1",
            space_id="s1",
            events=events,
            cohesion_score=0.0,
            temporal_start=1000,
            temporal_end=1000,
            is_noise=True,
        )

        assert candidate.centroid_metadata is None

    def test_candidate_single_event_no_centroid_metadata(self) -> None:
        """Single-event clusters (< 2 events) do not get centroid_metadata."""
        events = [RichMockEvent("e1", 1000, make_embedding(1))]

        calc = CentroidCalculator()
        candidate = calc.create_episode_candidate(
            cluster_id="c1",
            space_id="s1",
            events=events,
            cohesion_score=0.5,
            temporal_start=1000,
            temporal_end=1000,
        )

        assert candidate.centroid_metadata is None
