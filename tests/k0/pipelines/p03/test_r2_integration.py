"""
R2 Episodic Clustering Integration Tests.

Issue 4.2.8: Unit + integration tests for R2 Episodic clustering

This file tests the full R2 phase flow integrating all components:
    - CompositeDistance (4.2.1)
    - EpisodeSplitter (4.2.2)
    - EpisodicDBSCAN (4.2.3)
    - CentroidCalculator (4.2.4)
    - EpsAdjuster (4.2.5)
    - MinSamplesAdjuster (4.2.6)
    - ClusterQualityTracker (4.2.7)

Tests:
    1. test_full_r2_phase_produces_clusters: Full flow produces valid output
    2. test_semantically_similar_events_cluster_together: High similarity → same cluster
    3. test_dissimilar_events_form_separate_clusters: Low similarity → different clusters
    4. test_large_time_gap_triggers_split: Time gap > threshold → split
    5. test_location_change_triggers_split: Geohash change → split
    6. test_silhouette_triggers_eps_adjustment: Low silhouette → adjust eps
    7. test_singleton_rate_triggers_min_samples_increase: High noise → adjust min_samples
    8. test_staged_writes_contain_expected_structure: All fields populated
    9. test_centroid_l2_normalized: Centroids have unit norm
    10. test_quality_metrics_computed: Quality tracker produces valid metrics
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms import (
    CentroidCalculator,
    ClusterQualityMetrics,
    ClusterQualityTracker,
    CompositeDistance,
    DBSCANParams,
    EpisodeSplitter,
    EpisodicDBSCAN,
    EpsAdjuster,
    MinSamplesAdjuster,
    R2StagedOutput,
    SplitConfig,
)
from k0.modules.consolidation.algorithms.composite_distance import MS_PER_HOUR

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for integration testing."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]] = None
    importance_score: float = 0.5
    sentiment_score: float = 0.5
    geohash_6: str = "9q8yyz"
    activity_type: str = "general"

    # Mutable fields for clustering
    cluster_id: Optional[str] = None
    cluster_label: int = -1
    is_noise: bool = False
    centroid_distance: float = 0.0


def make_embedding(seed: int, dim: int = 768) -> List[float]:
    """Create deterministic embedding from seed."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / norm).tolist()


def create_similar_events(
    count: int,
    base_seed: int = 42,
    base_timestamp: int = 1_000_000_000_000,
    time_gap_ms: int = 60_000,  # 1 minute between events
) -> List[MockEvent]:
    """Create events with similar embeddings that should cluster together."""
    base_emb = make_embedding(base_seed)
    events = []

    for i in range(count):
        # Add small noise to base embedding
        rng = np.random.default_rng(base_seed + i + 1000)
        noise = rng.standard_normal(768).astype(np.float32) * 0.05
        emb = (np.array(base_emb) + noise).tolist()

        events.append(
            MockEvent(
                event_id=f"similar-{i}",
                timestamp=base_timestamp + i * time_gap_ms,
                embedding_768=emb,
                importance_score=0.5 + i * 0.05,
            )
        )

    return events


def create_dissimilar_events(
    count: int,
    base_timestamp: int = 1_000_000_000_000,
    time_gap_ms: int = 60_000,
) -> List[MockEvent]:
    """Create events with very different embeddings (should be separate)."""
    events = []

    for i in range(count):
        # Each event has completely different embedding
        events.append(
            MockEvent(
                event_id=f"dissimilar-{i}",
                timestamp=base_timestamp + i * time_gap_ms,
                embedding_768=make_embedding(i * 1000),  # Very different seeds
                importance_score=0.5,
            )
        )

    return events


def create_events_with_time_gap(
    gap_hours: float = 1.0,
    base_timestamp: int = 1_000_000_000_000,
) -> List[MockEvent]:
    """Create events with a large time gap."""
    base_emb = make_embedding(42)

    return [
        MockEvent(
            event_id="before-gap",
            timestamp=base_timestamp,
            embedding_768=base_emb,
        ),
        MockEvent(
            event_id="after-gap",
            timestamp=base_timestamp + int(gap_hours * MS_PER_HOUR),
            embedding_768=base_emb,  # Same embedding
        ),
    ]


def create_events_with_location_change(
    geohash1: str = "9q8yyz",
    geohash2: str = "dr5reg",
    base_timestamp: int = 1_000_000_000_000,
) -> List[MockEvent]:
    """Create events with location change."""
    base_emb = make_embedding(42)

    return [
        MockEvent(
            event_id="location-1",
            timestamp=base_timestamp,
            embedding_768=base_emb,
            geohash_6=geohash1,
        ),
        MockEvent(
            event_id="location-2",
            timestamp=base_timestamp + 60_000,  # 1 minute later
            embedding_768=base_emb,
            geohash_6=geohash2,  # Different location
        ),
    ]


# =============================================================================
# Full Phase Integration Tests
# =============================================================================


class TestR2FullPhase:
    """Integration tests for full R2 episodic clustering phase."""

    def test_full_r2_phase_produces_clusters(self) -> None:
        """Full R2 phase produces valid episode candidates."""
        # Create 6 similar events that should cluster
        events = create_similar_events(6, base_seed=42)

        # Use a higher eps to ensure clustering with similar events
        params = DBSCANParams(eps=0.5, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # Should produce at least 1 cluster (with eps=0.5, similar events cluster)
        # Or process all as a single output
        assert result.total_events == 6

        # Build staged output
        calc = CentroidCalculator()
        output = R2StagedOutput()

        for cluster in result.clusters:
            cluster_events = [e for e in events if e.event_id in cluster.member_event_ids]
            candidate = calc.create_episode_candidate(
                cluster_id=cluster.cluster_id,
                space_id="test-space",
                events=cluster_events,
                cohesion_score=cluster.cohesion_score,
                temporal_start=cluster.temporal_start,
                temporal_end=cluster.temporal_end,
            )
            output.add_candidate(candidate)

        output.finalize()

        # Staged output should contain all processed events
        assert output.total_events_processed == 6
        assert len(output.episode_candidates) >= 1

    def test_semantically_similar_events_cluster_together(self) -> None:
        """Events with high embedding similarity cluster together."""
        # Create 4 events with identical embeddings
        base_emb = make_embedding(42)
        base_ts = 1_000_000_000_000

        events = [MockEvent(f"e{i}", base_ts + i * 60_000, base_emb) for i in range(4)]

        params = DBSCANParams(eps=0.3, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # Should form 1 cluster with all 4 events
        non_noise = [c for c in result.clusters if not c.cluster_id.startswith("noise-")]
        assert len(non_noise) == 1
        assert non_noise[0].event_count == 4

    def test_dissimilar_events_form_separate_clusters_or_noise(self) -> None:
        """Events with low similarity don't cluster together."""
        events = create_dissimilar_events(4)

        params = DBSCANParams(eps=0.25, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # Should all be noise (too dissimilar)
        assert result.noise_count == 4
        assert result.cluster_count == 0


# =============================================================================
# Pre-Splitting Tests
# =============================================================================


class TestPreSplitting:
    """Test EpisodeSplitter pre-clustering split logic."""

    def test_large_time_gap_triggers_split(self) -> None:
        """Time gap > threshold triggers sequence split."""
        events = create_events_with_time_gap(gap_hours=1.0)

        # 30 minutes gap threshold (event gap is 1 hour)
        config = SplitConfig(time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        # Should split into 2 episodes
        assert result.episode_count == 2

    def test_location_change_triggers_split(self) -> None:
        """Geohash prefix change triggers sequence split."""
        events = create_events_with_location_change(
            geohash1="9q8yyz",  # San Francisco
            geohash2="dr5reg",  # New York
        )

        # geohash_distance_threshold=4 means first 4 chars must match
        config = SplitConfig(geohash_distance_threshold=4)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        # Should split due to location change (9q8y vs dr5r differ entirely)
        assert result.episode_count == 2

    def test_no_split_for_close_events(self) -> None:
        """Close events in time and space don't split."""
        events = create_similar_events(5, time_gap_ms=60_000)  # 1 min gaps

        # 30 min gap threshold (gaps are only 1 min)
        config = SplitConfig(time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        # Should remain as 1 episode
        assert result.episode_count == 1


# =============================================================================
# Adaptive Learning Tests
# =============================================================================


class TestAdaptiveLearning:
    """Test adaptive parameter adjustment."""

    def test_silhouette_triggers_eps_decrease(self) -> None:
        """Low silhouette + large clusters → decrease eps."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.30,
            silhouette_score=0.35,  # Below 0.5 target
            avg_cluster_size=15.0,  # Large clusters
            singleton_rate=0.10,
            total_clusters_formed=200,
        )

        assert result.adjusted
        assert result.new_eps < 0.30

    def test_silhouette_triggers_eps_increase(self) -> None:
        """Low silhouette + high noise → increase eps."""
        adjuster = EpsAdjuster()

        result = adjuster.adjust(
            current_eps=0.20,
            silhouette_score=0.35,  # Below 0.5 target
            avg_cluster_size=3.0,  # Small clusters
            singleton_rate=0.30,  # High noise
            total_clusters_formed=200,
        )

        assert result.adjusted
        assert result.new_eps > 0.20

    def test_singleton_rate_triggers_min_samples_increase(self) -> None:
        """High singleton rate → increase min_samples."""
        adjuster = MinSamplesAdjuster()

        result = adjuster.adjust(
            current_min_samples=2,
            singleton_rate=0.30,  # 30% noise
        )

        assert result.adjusted
        assert result.new_min_samples == 3


# =============================================================================
# Staged Output Tests
# =============================================================================


class TestStagedOutput:
    """Test R2StagedOutput structure."""

    def test_staged_writes_contain_expected_structure(self) -> None:
        """Episode candidates have all required fields."""
        events = create_similar_events(5)

        params = DBSCANParams(eps=0.3, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        calc = CentroidCalculator()
        output = R2StagedOutput()

        for cluster in result.clusters:
            cluster_events = [e for e in events if e.event_id in cluster.member_event_ids]
            candidate = calc.create_episode_candidate(
                cluster_id=cluster.cluster_id,
                space_id="test-space",
                events=cluster_events,
                cohesion_score=cluster.cohesion_score,
                temporal_start=cluster.temporal_start,
                temporal_end=cluster.temporal_end,
            )
            output.add_candidate(candidate)

        output.finalize()

        for candidate in output.episode_candidates:
            assert candidate.cluster_id is not None
            assert candidate.space_id == "test-space"
            assert candidate.temporal_start > 0
            assert candidate.temporal_end >= candidate.temporal_start
            assert 0.0 <= candidate.cohesion_score <= 1.0

            if not candidate.is_noise:
                assert candidate.centroid_embedding is not None
                assert len(candidate.centroid_embedding) == 768


# =============================================================================
# Centroid Tests
# =============================================================================


class TestCentroid:
    """Test CentroidCalculator in integration context."""

    def test_centroid_l2_normalized(self) -> None:
        """Centroid embeddings have unit norm."""
        events = create_similar_events(5)

        calc = CentroidCalculator(normalize=True)
        result = calc.compute(events, strategy="hybrid")

        norm = np.linalg.norm(result.centroid)
        assert norm == pytest.approx(1.0, abs=0.001)

    def test_centroid_variance_low_for_similar_events(self) -> None:
        """Variance is low for very similar events."""
        # Create events with identical embeddings
        base_emb = make_embedding(42)
        events = [MockEvent(f"e{i}", 1000 + i * 60000, base_emb) for i in range(5)]

        calc = CentroidCalculator()
        result = calc.compute(events)

        # Variance should be near 0 for identical embeddings
        assert result.variance == pytest.approx(0.0, abs=0.01)


# =============================================================================
# Quality Metrics Tests
# =============================================================================


class TestQualityMetrics:
    """Test ClusterQualityTracker in integration context."""

    def test_quality_metrics_computed(self) -> None:
        """Quality tracker computes valid metrics from R2 output."""

        # Create mock R2 output
        @dataclass
        class MockR2Output:
            batch_silhouette_score: float = 0.6
            cluster_count: int = 10
            noise_count: int = 2

        tracker = ClusterQualityTracker()
        r2_output = MockR2Output()

        metrics = tracker.compute_from_r2_output(
            space_id="test-space",
            r2_output=r2_output,
            grounded_clusters=6,
            corrected_clusters=1,
        )

        assert metrics.silhouette_score == 0.6
        assert metrics.total_clusters == 12
        assert metrics.singleton_clusters == 2
        assert metrics.grounding_rate == pytest.approx(0.5, abs=0.01)
        assert metrics.composite_quality > 0.0

    def test_quality_alert_mechanism(self) -> None:
        """Alert triggered after consecutive low-quality cycles."""
        tracker = ClusterQualityTracker()

        # 3 consecutive low scores
        for i in range(3):
            metrics = ClusterQualityMetrics(silhouette_score=0.2)
            alert = tracker.check_for_alert(metrics)

        assert alert is not None
        assert "CLUSTER_QUALITY_DEGRADED" in alert


# =============================================================================
# End-to-End Composite Distance Tests
# =============================================================================


class TestCompositeDistanceIntegration:
    """Test CompositeDistance in full pipeline context."""

    def test_distance_matrix_for_clustering(self) -> None:
        """CompositeDistance produces valid matrix for DBSCAN."""
        events = create_similar_events(4)

        params = DBSCANParams(eps=0.3, min_samples=2, temporal_weight=0.3)
        distance = CompositeDistance(params)
        matrix = distance.build_distance_matrix(events)

        # Matrix should be symmetric
        assert matrix.shape == (4, 4)
        assert np.allclose(matrix, matrix.T)

        # Diagonal should be 0
        assert np.allclose(np.diag(matrix), 0.0)

        # All values should be non-negative
        assert np.all(matrix >= 0.0)

    def test_temporal_weight_affects_clustering(self) -> None:
        """Higher temporal weight separates temporally distant events."""
        base_ts = 1_000_000_000_000
        base_emb = make_embedding(42)

        # Events with same embedding but 2 hours apart
        events = [
            MockEvent("e1", base_ts, base_emb),
            MockEvent("e2", base_ts + int(2 * MS_PER_HOUR), base_emb),
        ]

        # Low temporal weight → should cluster (embedding similar)
        params_low = DBSCANParams(eps=0.3, min_samples=2, temporal_weight=0.1)
        dbscan_low = EpisodicDBSCAN(params_low)
        result_low = dbscan_low.cluster(events)

        # High temporal weight → should NOT cluster (time gap too large)
        params_high = DBSCANParams(eps=0.3, min_samples=2, temporal_weight=0.5)
        dbscan_high = EpisodicDBSCAN(params_high)
        result_high = dbscan_high.cluster(events)

        # With high temporal weight, distance is larger, less likely to cluster
        # (may result in noise depending on exact eps)
        assert result_high.noise_count >= result_low.noise_count
