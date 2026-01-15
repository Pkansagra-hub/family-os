"""
Tests for EpisodicDBSCAN — DBSCAN clustering for episodic memory.

Issue 4.2.3: Implement DBSCAN clustering with configurable eps/min_samples

Tests:
    1. test_cluster_similar_events: High cos_sim + close time → same cluster
    2. test_separate_dissimilar_events: Low cos_sim → different clusters
    3. test_noise_handling: Singleton events marked is_noise=True
    4. test_event_state_updated: cluster_id, cluster_label set on events
    5. test_cohesion_score_computed: Clusters have valid cohesion [0, 1]
    6. test_temporal_bounds_correct: temporal_start ≤ timestamps ≤ temporal_end
    7. test_min_samples_below_threshold: All events become noise if < min_samples
    8. test_empty_input: Empty list produces empty result
    9. test_single_event: Single event becomes noise cluster
    10. test_cluster_stats: Statistics computed correctly
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.composite_distance import MS_PER_HOUR, DBSCANParams
from k0.modules.consolidation.algorithms.episodic_dbscan import EpisodicDBSCAN

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for testing."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]]
    sentiment_score: float = 0.5
    importance_score: float = 0.5


def make_embedding(seed: int, dim: int = 768) -> List[float]:
    """Create deterministic embedding from seed."""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / norm).tolist()


def make_similar_embedding(base: List[float], noise_level: float = 0.1) -> List[float]:
    """Create embedding similar to base with small perturbation."""
    arr = np.asarray(base, dtype=np.float32)
    noise = np.random.randn(len(arr)).astype(np.float32) * noise_level
    result = arr + noise
    norm = np.linalg.norm(result)
    return (result / norm).tolist()


# =============================================================================
# EpisodicDBSCAN Tests — Basic Cases
# =============================================================================


class TestEpisodicDBSCANBasic:
    """Test EpisodicDBSCAN basic functionality."""

    def test_empty_input(self) -> None:
        """Empty list produces empty result."""
        dbscan = EpisodicDBSCAN()
        result = dbscan.cluster([])

        assert result.total_events == 0
        assert result.cluster_count == 0
        assert result.noise_count == 0
        assert result.clusters == []
        assert result.labels == []

    def test_single_event(self) -> None:
        """Single event becomes noise cluster."""
        event = MockEvent("e1", 1000, make_embedding(1))

        params = DBSCANParams(min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster([event])

        assert result.total_events == 1
        assert result.cluster_count == 0
        assert result.noise_count == 1
        assert len(result.clusters) == 1
        assert result.clusters[0].cluster_id.startswith("noise-")

    def test_min_samples_below_threshold(self) -> None:
        """All events become noise if total < min_samples."""
        events = [
            MockEvent("e1", 1000, make_embedding(1)),
            MockEvent("e2", 2000, make_embedding(2)),
        ]

        params = DBSCANParams(min_samples=3)  # Need 3, only have 2
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        assert result.total_events == 2
        assert result.cluster_count == 0
        assert result.noise_count == 2
        # Each event becomes its own noise cluster
        for cluster in result.clusters:
            assert cluster.cluster_id.startswith("noise-")


# =============================================================================
# EpisodicDBSCAN Tests — Clustering Behavior
# =============================================================================


class TestEpisodicDBSCANClustering:
    """Test EpisodicDBSCAN clustering behavior."""

    def test_cluster_similar_events(self) -> None:
        """High cosine similarity + close time → same cluster."""
        base_ts = 1000000000000
        base_emb = make_embedding(42)

        # 3 similar events close in time (within 1 hour)
        events = [
            MockEvent("e1", base_ts, base_emb),
            MockEvent("e2", base_ts + 10 * 60 * 1000, make_similar_embedding(base_emb, 0.05)),
            MockEvent("e3", base_ts + 20 * 60 * 1000, make_similar_embedding(base_emb, 0.05)),
        ]

        params = DBSCANParams(eps=0.5, min_samples=2, temporal_weight=0.3)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # Should form one cluster (all similar + close in time)
        assert result.cluster_count >= 1
        # Find the non-noise cluster
        non_noise = [c for c in result.clusters if not c.cluster_id.startswith("noise-")]
        assert len(non_noise) >= 1
        # At least 2 events should cluster together
        assert any(c.event_count >= 2 for c in non_noise)

    def test_separate_dissimilar_events(self) -> None:
        """Low cosine similarity → different clusters or noise."""
        base_ts = 1000000000000

        # Create orthogonal embeddings (maximally different)
        emb1 = [0.0] * 768
        emb1[0] = 1.0
        emb2 = [0.0] * 768
        emb2[1] = 1.0
        emb3 = [0.0] * 768
        emb3[2] = 1.0

        events = [
            MockEvent("e1", base_ts, emb1),
            MockEvent("e2", base_ts + 1000, emb2),
            MockEvent("e3", base_ts + 2000, emb3),
        ]

        # Use very tight eps to prevent clustering
        params = DBSCANParams(eps=0.1, min_samples=2, temporal_weight=0.0)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # All should be noise (too dissimilar)
        assert result.noise_count == 3
        assert result.cluster_count == 0

    def test_temporal_separation_prevents_clustering(self) -> None:
        """Events too far apart in time don't cluster."""
        base_ts = 1000000000000
        base_emb = make_embedding(42)

        # Same embedding but 5 hours apart (beyond 4h limit)
        events = [
            MockEvent("e1", base_ts, base_emb),
            MockEvent("e2", base_ts + 5 * MS_PER_HOUR, base_emb),
        ]

        params = DBSCANParams(eps=0.5, min_samples=2, max_temporal_gap_hours=4.0)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # Should not cluster (distance = inf beyond temporal gap)
        assert result.noise_count == 2


# =============================================================================
# EpisodicDBSCAN Tests — Cluster Properties
# =============================================================================


class TestEpisodicDBSCANClusterProperties:
    """Test EpisodicDBSCAN cluster property computation."""

    def test_cohesion_score_computed(self) -> None:
        """Clusters have valid cohesion score [0, 1]."""
        base_ts = 1000000000000
        base_emb = make_embedding(42)

        events = [
            MockEvent("e1", base_ts, base_emb),
            MockEvent("e2", base_ts + 1000, make_similar_embedding(base_emb, 0.02)),
            MockEvent("e3", base_ts + 2000, make_similar_embedding(base_emb, 0.02)),
        ]

        params = DBSCANParams(eps=0.5, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        for cluster in result.clusters:
            assert 0.0 <= cluster.cohesion_score <= 1.0

    def test_temporal_bounds_correct(self) -> None:
        """temporal_start ≤ all timestamps ≤ temporal_end."""
        base_ts = 1000000000000

        events = [
            MockEvent("e1", base_ts, make_embedding(1)),
            MockEvent("e2", base_ts + 5000, make_embedding(1)),
            MockEvent("e3", base_ts + 10000, make_embedding(1)),
        ]

        dbscan = EpisodicDBSCAN()
        result = dbscan.cluster(events)

        for cluster in result.clusters:
            # temporal_start should be min
            assert cluster.temporal_start <= cluster.temporal_end

            # All member events should be within bounds
            member_ids = set(cluster.member_event_ids)
            member_events = [e for e in events if e.event_id in member_ids]
            for event in member_events:
                assert cluster.temporal_start <= event.timestamp <= cluster.temporal_end

    def test_dominant_sentiment_computed(self) -> None:
        """Dominant sentiment is average of member events."""
        base_ts = 1000000000000
        base_emb = make_embedding(42)

        events = [
            MockEvent("e1", base_ts, base_emb, sentiment_score=0.8),
            MockEvent("e2", base_ts + 1000, make_similar_embedding(base_emb), sentiment_score=0.6),
        ]

        params = DBSCANParams(eps=0.5, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        for cluster in result.clusters:
            if cluster.event_count > 1:
                # Average of 0.8 and 0.6 = 0.7
                assert cluster.dominant_sentiment == pytest.approx(0.7, abs=0.1)


# =============================================================================
# EpisodicDBSCAN Tests — Event Update
# =============================================================================


class TestEpisodicDBSCANEventUpdate:
    """Test EpisodicDBSCAN event state updates."""

    def test_cluster_and_update_events(self) -> None:
        """cluster_and_update_events mutates event objects."""

        @dataclass
        class MutableEvent:
            event_id: str
            timestamp: int
            embedding_768: Optional[List[float]]
            sentiment_score: float = 0.5
            importance_score: float = 0.5
            cluster_id: Optional[str] = None
            cluster_label: int = -1
            is_noise: bool = False
            centroid_distance: float = 0.0

            def assign_cluster(self, cluster_id: str, label: int, distance: float) -> None:
                self.cluster_id = cluster_id
                self.cluster_label = label
                self.is_noise = label == -1
                self.centroid_distance = distance

        base_ts = 1000000000000
        base_emb = make_embedding(42)

        events = [
            MutableEvent("e1", base_ts, base_emb),
            MutableEvent("e2", base_ts + 1000, make_similar_embedding(base_emb)),
        ]

        params = DBSCANParams(eps=0.5, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster_and_update_events(events)
        assert result is not None

        # Events should be updated
        for event in events:
            assert event.cluster_id is not None or event.is_noise


# =============================================================================
# EpisodicDBSCAN Tests — Statistics
# =============================================================================


class TestEpisodicDBSCANStats:
    """Test EpisodicDBSCAN statistics computation."""

    def test_singleton_rate(self) -> None:
        """Singleton rate computed correctly."""
        base_ts = 1000000000000

        # 3 events, all become noise
        events = [
            MockEvent("e1", base_ts, make_embedding(1)),
            MockEvent("e2", base_ts + 1000, make_embedding(2)),
            MockEvent("e3", base_ts + 2000, make_embedding(3)),
        ]

        # Use tight eps so all become noise
        params = DBSCANParams(eps=0.01, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        # All noise → singleton_rate = 1.0
        assert result.singleton_rate == 1.0

    def test_get_cluster_stats(self) -> None:
        """get_cluster_stats returns valid statistics."""
        base_ts = 1000000000000
        base_emb = make_embedding(42)

        events = [
            MockEvent("e1", base_ts, base_emb),
            MockEvent("e2", base_ts + 1000, make_similar_embedding(base_emb)),
            MockEvent("e3", base_ts + 2000, make_similar_embedding(base_emb)),
        ]

        params = DBSCANParams(eps=0.5, min_samples=2)
        dbscan = EpisodicDBSCAN(params)
        result = dbscan.cluster(events)

        stats = dbscan.get_cluster_stats(result)

        assert "total_events" in stats
        assert "cluster_count" in stats
        assert "noise_count" in stats
        assert "singleton_rate" in stats
        assert "avg_cluster_size" in stats
        assert "avg_cohesion" in stats

    def test_get_cluster_stats_empty(self) -> None:
        """Statistics for empty result."""
        dbscan = EpisodicDBSCAN()
        result = dbscan.cluster([])

        stats = dbscan.get_cluster_stats(result)

        assert stats["total_events"] == 0
        assert stats["cluster_count"] == 0
        assert stats["avg_cluster_size"] == 0.0
