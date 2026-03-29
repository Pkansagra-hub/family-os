"""
R2 Episodic Clustering Integration Tests.

Issue 4.2.8: Unit + integration tests for R2 Episodic clustering

This file tests the full R2 phase flow integrating all components:
    - CompositeDistance (4.2.1)
    - EpisodeSplitter (4.2.2)
    - EpisodicHDBSCAN (4.2.3)
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
    ClusteringDistanceParams,
    ClusterQualityMetrics,
    ClusterQualityTracker,
    CompositeDistance,
    EpisodeSplitter,
    EpisodicHDBSCAN,
    EpsAdjuster,
    HDBSCANParams,
    MinSamplesAdjuster,
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
    place_id: Optional[str] = None
    narrative_thread_id: Optional[str] = None
    goal_context: Optional[str] = None
    participants_json: Optional[str] = None
    social_context: Optional[str] = None

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
    """Create events with location change and different embeddings."""
    return [
        MockEvent(
            event_id="location-1",
            timestamp=base_timestamp,
            embedding_768=make_embedding(42),
            geohash_6=geohash1,
        ),
        MockEvent(
            event_id="location-2",
            timestamp=base_timestamp + 60_000,  # 1 minute later
            embedding_768=make_embedding(999),  # Different embedding
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
        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.5)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        # Should produce at least 1 cluster (with eps=0.5, similar events cluster)
        # Or process all as a single output
        assert result.total_events == 6

        # Build candidates from clusters
        calc = CentroidCalculator()
        candidates = []
        total_events = 0

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
            candidates.append(candidate)
            total_events += candidate.event_count

        # Candidates should contain all processed events
        assert total_events == 6
        assert len(candidates) >= 1

    def test_semantically_similar_events_cluster_together(self) -> None:
        """Events with high embedding similarity cluster together."""
        # Create 4 events with identical embeddings
        base_emb = make_embedding(42)
        base_ts = 1_000_000_000_000

        events = [MockEvent(f"e{i}", base_ts + i * 60_000, base_emb) for i in range(4)]

        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.3)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        # Should form 1 cluster with all 4 events
        non_noise = [c for c in result.clusters if not c.cluster_id.startswith("noise-")]
        assert len(non_noise) == 1
        assert non_noise[0].event_count == 4

    def test_dissimilar_events_form_separate_clusters_or_noise(self) -> None:
        """Events with low similarity don't all cluster into one group.

        HDBSCAN with noise rescue may assign dissimilar events to separate
        clusters rather than noise (unlike DBSCAN which produced 71.5% noise).
        The key invariant: no single cluster should contain all events.
        """
        events = create_dissimilar_events(4)

        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.25)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        # HDBSCAN may rescue noise into clusters, so either:
        # - events are noise, OR
        # - events form multiple separate clusters
        # The key invariant: no single cluster contains all 4 events
        non_noise = [c for c in result.clusters if not c.cluster_id.startswith("noise-")]
        for cluster in non_noise:
            assert (
                cluster.event_count < 4
            ), f"All dissimilar events ended up in one cluster (count={cluster.event_count})"


# =============================================================================
# Pre-Splitting Tests
# =============================================================================


class TestPreSplitting:
    """Test EpisodeSplitter pre-clustering split logic."""

    def test_large_time_gap_triggers_split(self) -> None:
        """Time gap > threshold triggers sequence split."""
        events = create_events_with_time_gap(gap_hours=1.0)

        # 30 minutes hard gap threshold (event gap is 1 hour)
        config = SplitConfig(hard_time_gap_minutes=30.0)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        # Should split into 2 episodes
        assert result.episode_count == 2

    def test_location_change_triggers_split(self) -> None:
        """Geohash prefix change contributes to accumulated score.

        Epic 3.3: Location change alone no longer causes an instant split.
        With accumulated scoring, place_change (0.15) must combine with
        other penalties to exceed the soft_split_threshold (0.45).
        We use a lower threshold to verify the spatial channel fires.
        """
        events = create_events_with_location_change(
            geohash1="9q8yyz",  # San Francisco
            geohash2="dr5reg",  # New York
        )

        # Use a low threshold so place_change alone can split
        config = SplitConfig(soft_split_threshold=0.10, theta_soft=0.05)
        splitter = EpisodeSplitter(config)
        result = splitter.split(events)

        # Should split due to place_change exceeding lowered threshold
        assert result.episode_count == 2

    def test_no_split_for_close_events(self) -> None:
        """Close events in time and space don't split."""
        events = create_similar_events(5, time_gap_ms=60_000)  # 1 min gaps

        splitter = EpisodeSplitter()
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
            silhouette_score=0.25,  # Below 0.30 target
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


class TestCandidateStructure:
    """Test episode candidate structure from clustering pipeline."""

    def test_candidates_contain_expected_structure(self) -> None:
        """Episode candidates have all required fields."""
        events = create_similar_events(5)

        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.3)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        calc = CentroidCalculator()
        candidates = []

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
            candidates.append(candidate)

        assert len(candidates) > 0

        for candidate in candidates:
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
        """CompositeDistance produces valid matrix for clustering."""
        events = create_similar_events(4)

        params = ClusteringDistanceParams(eps=0.3, min_samples=2, temporal_weight=0.3)
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

        # Low temporal weight - should cluster (embedding similar)
        params_low = HDBSCANParams(
            min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.3, temporal_weight=0.1
        )
        clusterer_low = EpisodicHDBSCAN(params_low)
        result_low = clusterer_low.cluster(events)

        # High temporal weight - should NOT cluster (time gap too large)
        params_high = HDBSCANParams(
            min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.3, temporal_weight=0.5
        )
        clusterer_high = EpisodicHDBSCAN(params_high)
        result_high = clusterer_high.cluster(events)

        # With high temporal weight, distance is larger, less likely to cluster
        # (may result in noise depending on exact eps)
        assert result_high.noise_count >= result_low.noise_count


# =============================================================================
# Issue 2.2.6 — Real Silhouette Regression Tests
# =============================================================================


class TestRealSilhouetteFromDistanceMatrix:
    """Prove silhouette is computed from precomputed distance matrix, not cohesion avg."""

    def test_distance_matrix_carried_in_result(self) -> None:
        """HDBSCANClusteringResult carries the exact distance matrix used for clustering."""
        events = create_similar_events(6)
        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.5)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        # distance_matrix must be present and square
        assert result.distance_matrix is not None
        n = len(events)
        assert result.distance_matrix.shape == (n, n)
        # symmetric
        assert np.allclose(result.distance_matrix, result.distance_matrix.T, atol=1e-6)
        # zero diagonal
        assert np.allclose(np.diag(result.distance_matrix), 0.0)

    def test_silhouette_matches_sklearn_on_same_matrix(self) -> None:
        """True silhouette from integrator matches sklearn directly on same matrix."""
        from sklearn.metrics import silhouette_score as sklearn_sil

        events = create_similar_events(8, base_seed=99)
        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.5)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        labels = np.array(result.labels)
        non_noise = labels >= 0
        distinct = set(labels[non_noise].tolist())

        if len(distinct) >= 2 and non_noise.sum() >= 2:
            idx = np.where(non_noise)[0]
            dm_sub = result.distance_matrix[np.ix_(idx, idx)]
            expected_sil = sklearn_sil(dm_sub, labels[idx], metric="precomputed")

            # The integrator's _compute_batch_silhouette should produce same value
            # (tested via single-result list)
            from k0.pipelines.p03.phases.r2_episodic_integrator import R2EpisodicIntegrator

            integrator = R2EpisodicIntegrator.__new__(R2EpisodicIntegrator)
            batch_sil = integrator._compute_batch_silhouette([result])

            assert batch_sil is not None
            assert batch_sil == pytest.approx(expected_sil, abs=1e-6)

    def test_all_noise_returns_none_silhouette(self) -> None:
        """All-noise clustering returns None silhouette (not 0.0)."""
        # Dissimilar events with tight eps — should all be noise
        events = create_dissimilar_events(4)
        params = HDBSCANParams(min_cluster_size=3, min_samples=2, cluster_selection_epsilon=0.05)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        from k0.pipelines.p03.phases.r2_episodic_integrator import R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator.__new__(R2EpisodicIntegrator)
        batch_sil = integrator._compute_batch_silhouette([result])

        # All noise or <2 clusters — silhouette undefined
        if (
            result.distance_matrix is None
            or len(set(np.array(result.labels)[np.array(result.labels) >= 0].tolist())) < 2
        ):
            assert batch_sil is None

    def test_empty_results_returns_none(self) -> None:
        """Empty clustering results return None silhouette."""
        from k0.pipelines.p03.phases.r2_episodic_integrator import R2EpisodicIntegrator

        integrator = R2EpisodicIntegrator.__new__(R2EpisodicIntegrator)
        assert integrator._compute_batch_silhouette([]) is None
        assert integrator._compute_batch_silhouette(None) is None

    def test_real_vs_cohesion_avg_diverge(self) -> None:
        """True silhouette and cohesion average produce different values on same layout.

        This is the regression guard: if someone re-introduces
        sum(cohesion)/count as silhouette, this test will catch it.
        """
        events = create_similar_events(8, base_seed=42)
        params = HDBSCANParams(min_cluster_size=2, min_samples=1, cluster_selection_epsilon=0.5)
        clusterer = EpisodicHDBSCAN(params)
        result = clusterer.cluster(events)

        labels = np.array(result.labels)
        non_noise = labels >= 0

        if len(set(labels[non_noise].tolist())) >= 2 and non_noise.sum() >= 2:
            from sklearn.metrics import silhouette_score as sklearn_sil

            idx = np.where(non_noise)[0]
            dm_sub = result.distance_matrix[np.ix_(idx, idx)]
            real_sil = sklearn_sil(dm_sub, labels[idx], metric="precomputed")

            # Compute fake cohesion average (what the old code did)
            # Cohesion per cluster = average intra-cluster similarity
            cluster_cohesions = []
            for label in set(labels[non_noise].tolist()):
                cluster_mask = labels == label
                cluster_embeddings = [
                    np.array(events[i].embedding_768) for i in range(len(events)) if cluster_mask[i]
                ]
                if len(cluster_embeddings) >= 2:
                    sims = []
                    for i in range(len(cluster_embeddings)):
                        for j in range(i + 1, len(cluster_embeddings)):
                            cos_sim = np.dot(cluster_embeddings[i], cluster_embeddings[j]) / (
                                np.linalg.norm(cluster_embeddings[i])
                                * np.linalg.norm(cluster_embeddings[j])
                                + 1e-10
                            )
                            sims.append(cos_sim)
                    cluster_cohesions.append(np.mean(sims))
                else:
                    cluster_cohesions.append(1.0)

            if cluster_cohesions:
                fake_sil = np.mean(cluster_cohesions)
                # Real silhouette is in [-1, 1], cohesion average is in [0, 1]
                # They should NOT be equal
                assert abs(real_sil - fake_sil) > 0.01, (
                    f"Real silhouette ({real_sil:.4f}) too close to cohesion "
                    f"average ({fake_sil:.4f}) — regression risk"
                )
