"""
Epic 6.2: Thread Purity Correction Tests.

Tests for ThreadPurityCorrector that splits impure episode clusters
containing events from multiple narrative threads into thread-pure
sub-clusters.

Issues covered:
    6.2.1: ThreadPurityCorrector implementation
    6.2.2: Wire into R2 execute flow (import check)
    6.2.3: R2Config control field
    6.2.4: Observability stats
    6.2.5: Unit tests for all correction scenarios
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from k0.modules.consolidation.algorithms.thread_purity import (
    NO_THREAD,
    PurityCorrectionStats,
    ThreadPurityCorrector,
    _get_thread_group,
)
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config

# =============================================================================
# Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event for thread purity testing."""

    event_id: str
    timestamp: int = 1_000_000_000_000
    narrative_thread_id: Optional[str] = None
    goal_context: Optional[str] = None
    embedding_768: Optional[List[float]] = None
    sentiment_score: float = 0.5


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


def _make_events(specs: List[tuple]) -> Dict[str, MockEvent]:
    """Build event lookup from (event_id, thread_id) tuples."""
    lookup = {}
    for i, spec in enumerate(specs):
        eid = spec[0]
        tid = spec[1] if len(spec) > 1 else None
        ts = 1_000_000_000_000 + i * 60_000
        lookup[eid] = MockEvent(event_id=eid, timestamp=ts, narrative_thread_id=tid)
    return lookup


# =============================================================================
# _get_thread_group
# =============================================================================


class TestGetThreadGroup:
    def test_narrative_thread_id_primary(self):
        ev = MockEvent(event_id="e1", narrative_thread_id="morning_routine")
        assert _get_thread_group(ev) == "morning_routine"

    def test_goal_context_fallback(self):
        ev = MockEvent(event_id="e1", goal_context="prepare_lunch")
        assert _get_thread_group(ev) == "goal:prepare_lunch"

    def test_narrative_takes_priority_over_goal(self):
        ev = MockEvent(
            event_id="e1",
            narrative_thread_id="morning_routine",
            goal_context="prepare_lunch",
        )
        assert _get_thread_group(ev) == "morning_routine"

    def test_no_signal_returns_sentinel(self):
        ev = MockEvent(event_id="e1")
        assert _get_thread_group(ev) == NO_THREAD


# =============================================================================
# Pure clusters (no-op)
# =============================================================================


class TestPureClusters:
    def test_single_thread_is_pure(self):
        events = _make_events([("e1", "t1"), ("e2", "t1"), ("e3", "t1")])
        cluster = _make_cluster("c1", ["e1", "e2", "e3"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert len(result) == 1
        assert result[0].cluster_id == "c1"  # unchanged
        assert stats.clusters_split == 0
        assert stats.clusters_pure == 1

    def test_all_unthreaded_is_pure(self):
        events = _make_events([("e1",), ("e2",), ("e3",)])
        cluster = _make_cluster("c1", ["e1", "e2", "e3"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert len(result) == 1
        assert stats.clusters_pure == 1
        assert stats.clusters_split == 0

    def test_empty_cluster_passthrough(self):
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([], {})
        assert len(result) == 0

    def test_single_event_cluster_passthrough(self):
        events = _make_events([("e1", "t1")])
        cluster = _make_cluster("c1", ["e1"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert len(result) == 1
        assert stats.clusters_before == 0  # single-event not counted


# =============================================================================
# Impure clusters (split)
# =============================================================================


class TestImpureClusters:
    def test_two_threads_split_into_two(self):
        events = _make_events(
            [
                ("e1", "morning_routine"),
                ("e2", "morning_routine"),
                ("e3", "work_meeting"),
                ("e4", "work_meeting"),
            ]
        )
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert len(result) == 2
        assert stats.clusters_split == 1
        assert stats.clusters_after == 2

        # Verify each sub-cluster is pure
        ids_per_cluster = [set(c.member_event_ids) for c in result]
        assert {"e1", "e2"} in ids_per_cluster
        assert {"e3", "e4"} in ids_per_cluster

    def test_three_threads_split_into_three(self):
        events = _make_events(
            [
                ("e1", "t1"),
                ("e2", "t1"),
                ("e3", "t2"),
                ("e4", "t2"),
                ("e5", "t3"),
                ("e6", "t3"),
            ]
        )
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4", "e5", "e6"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert len(result) == 3
        assert stats.clusters_split == 1

    def test_split_preserves_cohesion_score(self):
        events = _make_events([("e1", "t1"), ("e2", "t1"), ("e3", "t2"), ("e4", "t2")])
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4"], cohesion=0.95)
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        for c in result:
            assert c.cohesion_score == 0.95

    def test_split_generates_new_cluster_ids(self):
        events = _make_events([("e1", "t1"), ("e2", "t1"), ("e3", "t2"), ("e4", "t2")])
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        for c in result:
            assert c.cluster_id != "c1"
            assert c.cluster_id.startswith("ep-")

    def test_split_computes_temporal_bounds(self):
        events = {}
        events["e1"] = MockEvent(event_id="e1", timestamp=1000, narrative_thread_id="t1")
        events["e2"] = MockEvent(event_id="e2", timestamp=2000, narrative_thread_id="t1")
        events["e3"] = MockEvent(event_id="e3", timestamp=5000, narrative_thread_id="t2")
        events["e4"] = MockEvent(event_id="e4", timestamp=6000, narrative_thread_id="t2")

        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4"])
        corrector = ThreadPurityCorrector()
        result, _ = corrector.correct([cluster], events)

        # Find the t1 cluster
        t1_cluster = [c for c in result if "e1" in c.member_event_ids][0]
        assert t1_cluster.temporal_start == 1000
        assert t1_cluster.temporal_end == 2000


# =============================================================================
# Unthreaded events (majority assignment)
# =============================================================================


class TestUnthreadedAssignment:
    def test_unthreaded_assigned_to_majority(self):
        events = _make_events(
            [
                ("e1", "morning_routine"),
                ("e2", "morning_routine"),
                ("e3", "morning_routine"),
                ("e4", "work_meeting"),
                ("e5", "work_meeting"),
                ("e6", None),  # unthreaded
            ]
        )
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4", "e5", "e6"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)

        assert stats.events_reassigned == 1
        # e6 should be in the morning_routine cluster (majority = 3 events)
        morning_cluster = [c for c in result if "e1" in c.member_event_ids][0]
        assert "e6" in morning_cluster.member_event_ids

    def test_multiple_unthreaded_all_assigned(self):
        events = _make_events(
            [
                ("e1", "t1"),
                ("e2", "t1"),
                ("e3", "t1"),
                ("e4", "t2"),
                ("e5", "t2"),
                ("e6", None),
                ("e7", None),
            ]
        )
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4", "e5", "e6", "e7"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert stats.events_reassigned == 2
        # Both unthreaded go to t1 (majority)
        t1_cluster = [c for c in result if "e1" in c.member_event_ids][0]
        assert "e6" in t1_cluster.member_event_ids
        assert "e7" in t1_cluster.member_event_ids


# =============================================================================
# Edge cases
# =============================================================================


class TestEdgeCases:
    def test_min_split_size_filters_small_threads(self):
        events = _make_events(
            [
                ("e1", "t1"),
                ("e2", "t1"),
                ("e3", "t1"),
                ("e4", "t2"),  # Only 1 event in t2
            ]
        )
        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4"])
        corrector = ThreadPurityCorrector(min_split_size=2)
        result, stats = corrector.correct([cluster], events)
        # t2 has only 1 event -> below min_split_size, becomes noise
        assert len(result) == 1  # Only t1 cluster
        assert stats.noise_clusters_skipped == 1

    def test_missing_event_in_lookup(self):
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        cluster = _make_cluster("c1", ["e1", "e2", "e3"])  # e3 missing from lookup
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        # e3 gets __no_thread__ -> cluster is still pure (one thread + no-thread)
        assert len(result) == 1

    def test_goal_context_as_thread_signal(self):
        events = {}
        events["e1"] = MockEvent(event_id="e1", timestamp=1000, goal_context="cook_dinner")
        events["e2"] = MockEvent(event_id="e2", timestamp=2000, goal_context="cook_dinner")
        events["e3"] = MockEvent(event_id="e3", timestamp=3000, goal_context="fix_car")
        events["e4"] = MockEvent(event_id="e4", timestamp=4000, goal_context="fix_car")

        cluster = _make_cluster("c1", ["e1", "e2", "e3", "e4"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster], events)
        assert len(result) == 2
        assert stats.clusters_split == 1

    def test_multiple_clusters_mixed_purity(self):
        events = _make_events(
            [
                ("e1", "t1"),
                ("e2", "t1"),  # cluster 1: pure
                ("e3", "t1"),
                ("e4", "t1"),  # cluster 2: impure (2 x t1 + 2 x t2)
                ("e5", "t2"),
                ("e6", "t2"),
            ]
        )
        cluster1 = _make_cluster("c1", ["e1", "e2"])
        cluster2 = _make_cluster("c2", ["e3", "e4", "e5", "e6"])
        corrector = ThreadPurityCorrector()
        result, stats = corrector.correct([cluster1, cluster2], events)
        assert stats.clusters_pure == 1
        assert stats.clusters_split == 1
        assert len(result) == 3  # 1 pure + 2 from split


# =============================================================================
# Observability stats (6.2.4)
# =============================================================================


class TestObservabilityStats:
    def test_stats_to_dict(self):
        stats = PurityCorrectionStats(
            clusters_before=10,
            clusters_after=15,
            clusters_split=5,
            clusters_pure=5,
            events_reassigned=3,
            noise_clusters_skipped=2,
        )
        d = stats.to_dict()
        assert d["clusters_before"] == 10
        assert d["clusters_split"] == 5
        assert d["events_reassigned"] == 3

    def test_no_split_stats(self):
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        cluster = _make_cluster("c1", ["e1", "e2"])
        corrector = ThreadPurityCorrector()
        _, stats = corrector.correct([cluster], events)
        assert stats.clusters_split == 0
        assert stats.events_reassigned == 0


# =============================================================================
# R2Config field (6.2.3)
# =============================================================================


class TestR2ConfigPurityField:
    def test_default_enabled(self):
        cfg = R2Config()
        assert cfg.enable_thread_purity_correction is True

    def test_can_disable(self):
        cfg = R2Config(enable_thread_purity_correction=False)
        assert cfg.enable_thread_purity_correction is False
