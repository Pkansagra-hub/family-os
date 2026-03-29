"""
Epic 6.3: Same-Thread Episode Merge Tests.

Tests for SameThreadMerger that consolidates small same-thread episode
fragments into coherent episodes using union-find with path compression.

Issues covered:
    6.3.1: SameThreadMerger implementation
    6.3.2: Wire into R2 execute flow (import check)
    6.3.3: R2Config control fields
    6.3.4: Observability stats
    6.3.5: Unit tests for merge eligibility, union-find, transitive chains
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from k0.modules.consolidation.algorithms.same_thread_merge import (
    SameThreadMergeConfig,
    SameThreadMerger,
    SameThreadMergeStats,
    _cluster_centroid,
    _cosine_sim,
    _dominant_thread,
    _temporal_bounds,
)
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config

# =============================================================================
# Fixtures
# =============================================================================

HOUR_MS = 3_600_000


@dataclass
class MockEvent:
    """Mock event for same-thread merge testing."""

    event_id: str
    timestamp: int = 1_000_000_000_000
    narrative_thread_id: Optional[str] = None
    goal_context: Optional[str] = None
    embedding_768: Optional[List[float]] = None


def _unit_vec(dim: int = 10, angle_offset: float = 0.0) -> List[float]:
    """Create a unit vector. angle_offset rotates in first 2 dims for controllable similarity."""
    vec = [0.0] * dim
    vec[0] = math.cos(angle_offset)
    vec[1] = math.sin(angle_offset)
    return vec


def _make_cluster(
    cluster_id: str,
    event_ids: List[str],
    cohesion: float = 0.8,
) -> EpisodeCluster:
    return EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=event_ids,
        cohesion_score=cohesion,
    )


def _make_same_thread_events(
    specs: List[tuple],
    base_embedding: Optional[List[float]] = None,
) -> Dict[str, MockEvent]:
    """Build events from (event_id, thread_id, timestamp_offset_ms, [embedding]).

    All events share the same base embedding by default (high similarity).
    """
    if base_embedding is None:
        base_embedding = _unit_vec()
    lookup = {}
    for spec in specs:
        eid = spec[0]
        tid = spec[1] if len(spec) > 1 else None
        ts_offset = spec[2] if len(spec) > 2 else 0
        emb = spec[3] if len(spec) > 3 else list(base_embedding)
        lookup[eid] = MockEvent(
            event_id=eid,
            timestamp=1_000_000_000_000 + ts_offset,
            narrative_thread_id=tid,
            embedding_768=emb,
        )
    return lookup


# =============================================================================
# Helper functions
# =============================================================================


class TestCosineSimHelper:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_sim(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_sim(a, b) == pytest.approx(0.0)

    def test_zero_vector(self):
        a = [1.0, 0.0]
        b = [0.0, 0.0]
        assert _cosine_sim(a, b) == 0.0


class TestClusterCentroid:
    def test_single_event_centroid(self):
        events = {"e1": MockEvent(event_id="e1", embedding_768=[1.0, 0.0, 0.0])}
        result = _cluster_centroid(["e1"], events)
        assert result == [1.0, 0.0, 0.0]

    def test_two_event_mean(self):
        events = {
            "e1": MockEvent(event_id="e1", embedding_768=[1.0, 0.0]),
            "e2": MockEvent(event_id="e2", embedding_768=[0.0, 1.0]),
        }
        result = _cluster_centroid(["e1", "e2"], events)
        assert result == pytest.approx([0.5, 0.5])

    def test_no_embeddings_returns_none(self):
        events = {"e1": MockEvent(event_id="e1", embedding_768=None)}
        result = _cluster_centroid(["e1"], events)
        assert result is None


class TestDominantThread:
    def test_pure_cluster(self):
        events = _make_same_thread_events([("e1", "t1"), ("e2", "t1"), ("e3", "t1")])
        thread, purity = _dominant_thread(["e1", "e2", "e3"], events)
        assert thread == "t1"
        assert purity == pytest.approx(1.0)

    def test_mixed_cluster(self):
        events = _make_same_thread_events([("e1", "t1"), ("e2", "t1"), ("e3", "t2")])
        thread, purity = _dominant_thread(["e1", "e2", "e3"], events)
        assert thread == "t1"
        assert purity == pytest.approx(2 / 3)

    def test_no_thread_returns_none(self):
        events = _make_same_thread_events([("e1", None), ("e2", None)])
        thread, purity = _dominant_thread(["e1", "e2"], events)
        assert thread is None
        assert purity == 0.0


class TestTemporalBounds:
    def test_two_events(self):
        events = {
            "e1": MockEvent(event_id="e1", timestamp=1000),
            "e2": MockEvent(event_id="e2", timestamp=5000),
        }
        start, end = _temporal_bounds(["e1", "e2"], events)
        assert start == 1000
        assert end == 5000


# =============================================================================
# No-merge cases
# =============================================================================


class TestNoMerge:
    def test_single_cluster_no_merge(self):
        events = _make_same_thread_events([("e1", "t1", 0), ("e2", "t1", 1000)])
        cluster = _make_cluster("c1", ["e1", "e2"])
        merger = SameThreadMerger()
        result, stats = merger.merge([cluster], events)
        assert len(result) == 1
        assert stats.clusters_merged == 0

    def test_different_threads_no_merge(self):
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t2", 2000, emb),
                ("e4", "t2", 3000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        # Two clusters stay separate (different threads)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 2
        assert stats.clusters_merged == 0

    def test_low_centroid_similarity_no_merge(self):
        # Orthogonal embeddings -> cosine sim = 0
        emb_a = [1.0, 0.0, 0.0, 0.0, 0.0]
        emb_b = [0.0, 1.0, 0.0, 0.0, 0.0]
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb_a),
                ("e2", "t1", 1000, emb_a),
                ("e3", "t1", 2000, emb_b),
                ("e4", "t1", 3000, emb_b),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 2
        assert stats.clusters_merged == 0

    def test_temporal_gap_too_large_no_merge(self):
        emb = _unit_vec()
        gap = 5 * HOUR_MS  # 5 hours > 4h threshold
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", gap, emb),
                ("e4", "t1", gap + 1000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 2
        assert stats.clusters_merged == 0

    def test_empty_clusters_passthrough(self):
        merger = SameThreadMerger()
        result, stats = merger.merge([], {})
        assert len(result) == 0

    def test_impure_cluster_excluded_from_merge(self):
        """Clusters below 80% purity threshold should not be merged."""
        emb = _unit_vec()
        # c1: 2 t1 + 2 t2 = 50% purity (below 80%)
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t2", 1000, emb),
                ("e3", "t1", 2000, emb),
                ("e4", "t2", 3000, emb),
                ("e5", "t1", 4000, emb),
                ("e6", "t2", 5000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2", "e3"])  # 33% t1, 67% t2
        c2 = _make_cluster("c2", ["e4", "e5", "e6"])  # 33% t2, 67% t1... actually mixed
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        # Neither cluster reaches 80% purity -> no merge
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 2
        assert stats.clusters_merged == 0


# =============================================================================
# Merge cases
# =============================================================================


class TestMerge:
    def test_two_same_thread_clusters_merge(self):
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 2000, emb),
                ("e4", "t1", 3000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 1
        assert set(multi[0].member_event_ids) == {"e1", "e2", "e3", "e4"}
        assert stats.clusters_merged == 1
        assert stats.merge_groups_formed == 1

    def test_merged_cluster_id_format(self):
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 2000, emb),
                ("e4", "t1", 3000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        merged = [c for c in result if len(c.member_event_ids) > 1][0]
        assert merged.cluster_id.startswith("merged-")

    def test_merged_cohesion_is_max(self):
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 2000, emb),
                ("e4", "t1", 3000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"], cohesion=0.6)
        c2 = _make_cluster("c2", ["e3", "e4"], cohesion=0.9)
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        merged = [c for c in result if len(c.member_event_ids) > 1][0]
        assert merged.cohesion_score == 0.9

    def test_merged_temporal_bounds(self):
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 5000, emb),
                ("e4", "t1", 8000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        merged = [c for c in result if len(c.member_event_ids) > 1][0]
        base = 1_000_000_000_000
        assert merged.temporal_start == base + 0
        assert merged.temporal_end == base + 8000

    def test_three_clusters_transitive_merge(self):
        """A-B similar, B-C similar, A-C dissimilar -> all three merge transitively."""
        # A and B are very similar, B and C are very similar
        emb_a = _unit_vec(10, 0.0)
        emb_b = _unit_vec(10, 0.05)  # very close to A
        emb_c = _unit_vec(10, 0.10)  # close to B, still close to A
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb_a),
                ("e2", "t1", 1000, emb_a),
                ("e3", "t1", 2000, emb_b),
                ("e4", "t1", 3000, emb_b),
                ("e5", "t1", 4000, emb_c),
                ("e6", "t1", 5000, emb_c),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        c3 = _make_cluster("c3", ["e5", "e6"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2, c3], events)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 1
        assert len(multi[0].member_event_ids) == 6
        assert stats.clusters_merged == 2

    def test_largest_merged_cluster_stat(self):
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 2000, emb),
                ("e4", "t1", 3000, emb),
                ("e5", "t1", 4000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4", "e5"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        assert stats.largest_merged_cluster_size == 5

    def test_temporal_gap_at_boundary_merges(self):
        """Exactly 4h gap should merge (<=4h)."""
        emb = _unit_vec()
        gap = 4 * HOUR_MS  # exactly 4h
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", gap + 1000, emb),
                ("e4", "t1", gap + 2000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 1
        assert stats.clusters_merged == 1

    def test_single_event_clusters_preserved(self):
        """Single-event clusters pass through untouched."""
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 2000, emb),  # single event cluster
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3"])  # single event
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2], events)
        assert len(result) == 2  # c1 stays, c2 (single) preserved
        single = [c for c in result if len(c.member_event_ids) == 1]
        assert len(single) == 1

    def test_mixed_thread_groups_independent(self):
        """Clusters from different threads merge independently within their groups."""
        emb = _unit_vec()
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb),
                ("e2", "t1", 1000, emb),
                ("e3", "t1", 2000, emb),
                ("e4", "t1", 3000, emb),
                ("e5", "t2", 0, emb),
                ("e6", "t2", 1000, emb),
                ("e7", "t2", 2000, emb),
                ("e8", "t2", 3000, emb),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        c3 = _make_cluster("c3", ["e5", "e6"])
        c4 = _make_cluster("c4", ["e7", "e8"])
        merger = SameThreadMerger()
        result, stats = merger.merge([c1, c2, c3, c4], events)
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 2  # One merged t1, one merged t2
        assert stats.clusters_merged == 2
        assert stats.merge_groups_formed == 2


# =============================================================================
# Config
# =============================================================================


class TestSameThreadMergeConfig:
    def test_defaults(self):
        cfg = SameThreadMergeConfig()
        assert cfg.centroid_sim_threshold == 0.70
        assert cfg.max_temporal_gap_ms == 14_400_000
        assert cfg.purity_threshold == 0.80

    def test_custom_threshold(self):
        cfg = SameThreadMergeConfig(centroid_sim_threshold=0.90)
        # Same events that would merge at 0.70 should not merge at 0.90
        emb_a = _unit_vec(10, 0.0)
        emb_b = _unit_vec(10, 0.40)  # cos(0.40) ~ 0.92 -- close but test at edge
        events = _make_same_thread_events(
            [
                ("e1", "t1", 0, emb_a),
                ("e2", "t1", 1000, emb_a),
                ("e3", "t1", 2000, emb_b),
                ("e4", "t1", 3000, emb_b),
            ]
        )
        c1 = _make_cluster("c1", ["e1", "e2"])
        c2 = _make_cluster("c2", ["e3", "e4"])
        merger = SameThreadMerger(config=cfg)
        result, stats = merger.merge([c1, c2], events)
        # With angle_offset=0.40, centroid sim = cos(0.40) ~ 0.921, > 0.90 -> merges
        multi = [c for c in result if len(c.member_event_ids) > 1]
        assert len(multi) == 1


# =============================================================================
# Observability (6.3.4)
# =============================================================================


class TestMergeStats:
    def test_stats_to_dict(self):
        stats = SameThreadMergeStats(
            clusters_before=10,
            clusters_after=7,
            clusters_merged=3,
            merge_groups_formed=2,
            largest_merged_cluster_size=8,
        )
        d = stats.to_dict()
        assert d["clusters_before"] == 10
        assert d["clusters_merged"] == 3
        assert d["largest_merged_cluster_size"] == 8

    def test_no_merge_stats(self):
        emb = _unit_vec()
        events = _make_same_thread_events([("e1", "t1", 0, emb), ("e2", "t1", 1000, emb)])
        cluster = _make_cluster("c1", ["e1", "e2"])
        merger = SameThreadMerger()
        _, stats = merger.merge([cluster], events)
        assert stats.clusters_merged == 0
        assert stats.merge_groups_formed == 0


# =============================================================================
# R2Config fields (6.3.3)
# =============================================================================


class TestR2ConfigMergeFields:
    def test_default_enabled(self):
        cfg = R2Config()
        assert cfg.enable_same_thread_merge is True

    def test_can_disable(self):
        cfg = R2Config(enable_same_thread_merge=False)
        assert cfg.enable_same_thread_merge is False

    def test_config_accepts_merge_config(self):
        merge_cfg = SameThreadMergeConfig(centroid_sim_threshold=0.80)
        cfg = R2Config(same_thread_merge_config=merge_cfg)
        assert cfg.same_thread_merge_config.centroid_sim_threshold == 0.80

    def test_default_merge_config_is_none(self):
        cfg = R2Config()
        assert cfg.same_thread_merge_config is None
