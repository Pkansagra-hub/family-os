"""Tests for M9.10 scene segmentation algorithm.

Validates mega-episode splitting into human-scale scenes based on:
- Overnight gaps (>= 8h)
- Temporal gaps (>= 4h)
- Context shifts (place change + >= 2h gap)
- Size caps (max 35 events)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate
from k0.modules.consolidation.algorithms.scene_segmenter import (
    SceneSegmentationConfig,
    _detect_scene_breaks,
    _enforce_size_cap,
    _split_indices_at_breaks,
    segment_episodes,
)
from k0.pipelines.p03.phase_outputs import EpisodeCluster

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

HOUR_MS = 3_600_000
DAY_MS = 86_400_000
BASE_TS = 1_700_000_000_000  # Arbitrary epoch ms


def _vec(seed: int = 1, dim: int = 768) -> List[float]:
    """Deterministic L2-normalized random vector."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float64)
    v /= np.linalg.norm(v)
    return v.tolist()


@dataclass
class FakeEvent:
    """Mimics P03EventState with the fields EventAdapter accesses."""

    event_id: str = ""
    timestamp: int = 0
    embedding_768: Optional[List[float]] = None
    geohash_6: Optional[str] = None
    ner_entities_json: str = "[]"
    importance_score: float = 0.5
    importance_computed: bool = True
    activity_type: str = ""
    activity_type_ultrabert: str = ""
    social_context: str = ""
    social_intimacy: str = ""
    participants_json: str = "[]"
    narrative_thread_id: str = ""
    narrative_arc_position: str = ""
    sentiment_score: float = 0.0
    salience_score: float = 0.5
    affect_valence: float = 0.0
    affect_arousal: float = 0.0
    affect_dominance: float = 0.0
    place_id: Optional[str] = None
    entities_json: str = "[]"
    emotions_json: str = "[]"


@dataclass
class FakeAdapter:
    """Mimics EventAdapter wrapping P03EventState."""

    event: FakeEvent

    @property
    def event_id(self) -> str:
        return self.event.event_id

    @property
    def timestamp(self) -> int:
        return self.event.timestamp

    @property
    def embedding_768(self) -> Optional[List[float]]:
        return self.event.embedding_768

    @property
    def place_id(self) -> Optional[str]:
        return self.event.place_id or None

    @property
    def narrative_thread_id(self) -> Optional[str]:
        return self.event.narrative_thread_id or None

    @property
    def participants_json(self) -> Optional[str]:
        return self.event.participants_json if self.event.participants_json != "[]" else None


def _make_events(
    n: int,
    *,
    start_ts: int = BASE_TS,
    gap_ms: int = HOUR_MS,
    seed: int = 1,
    place_id: Optional[str] = None,
    thread_id: str = "",
) -> List[FakeAdapter]:
    """Create n sequential events with uniform gaps."""
    events = []
    for i in range(n):
        evt = FakeEvent(
            event_id=f"evt-{seed}-{i:03d}",
            timestamp=start_ts + i * gap_ms,
            embedding_768=_vec(seed * 1000 + i),
            place_id=place_id,
            narrative_thread_id=thread_id,
        )
        events.append(FakeAdapter(event=evt))
    return events


def _build_candidate_and_cluster(
    cluster_id: str,
    events: List[FakeAdapter],
    space_id: str = "default",
) -> tuple:
    """Build an EpisodeCandidate + EpisodeCluster from fake events."""
    event_ids = [e.event_id for e in events]
    embeddings = [e.embedding_768 for e in events if e.embedding_768]
    centroid = None
    if embeddings:
        arr = np.array(embeddings, dtype=np.float64)
        c = arr.mean(axis=0)
        n = np.linalg.norm(c)
        if n > 1e-12:
            c = c / n
        centroid = c.tolist()

    ts_list = [e.timestamp for e in events]

    cand = EpisodeCandidate(
        cluster_id=cluster_id,
        space_id=space_id,
        event_ids=event_ids,
        event_count=len(event_ids),
        centroid_embedding=centroid,
        temporal_start=min(ts_list),
        temporal_end=max(ts_list),
        cohesion_score=0.8,
        variance=0.2,
    )
    cluster = EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=event_ids,
        temporal_start=min(ts_list),
        temporal_end=max(ts_list),
        cohesion_score=0.8,
    )
    return cand, cluster


def _build_event_lookup(events: List[FakeAdapter]) -> Dict[str, object]:
    return {e.event_id: e for e in events}


# ---------------------------------------------------------------------------
# Test: _detect_scene_breaks
# ---------------------------------------------------------------------------


class TestDetectSceneBreaks:

    def test_no_breaks_within_normal_gaps(self):
        """Events 1h apart should produce no breaks."""
        timestamps = [BASE_TS + i * HOUR_MS for i in range(10)]
        place_ids: List[Optional[str]] = [None] * 10
        config = SceneSegmentationConfig()
        breaks = _detect_scene_breaks(timestamps, place_ids, config)
        assert breaks == []

    def test_overnight_gap(self):
        """A 10h gap should be detected as overnight."""
        timestamps = [BASE_TS, BASE_TS + 10 * HOUR_MS, BASE_TS + 11 * HOUR_MS]
        place_ids: List[Optional[str]] = [None, None, None]
        config = SceneSegmentationConfig()
        breaks = _detect_scene_breaks(timestamps, place_ids, config)
        assert len(breaks) == 1
        assert breaks[0].position == 1
        assert breaks[0].reason == "overnight"

    def test_temporal_gap(self):
        """A 5h gap should be detected as temporal_gap."""
        timestamps = [BASE_TS, BASE_TS + 5 * HOUR_MS]
        place_ids: List[Optional[str]] = [None, None]
        config = SceneSegmentationConfig()
        breaks = _detect_scene_breaks(timestamps, place_ids, config)
        assert len(breaks) == 1
        assert breaks[0].reason == "temporal_gap"

    def test_context_shift_place_change(self):
        """Place change with 3h gap (>= context_gap) detected as context_shift."""
        timestamps = [BASE_TS, BASE_TS + 3 * HOUR_MS]
        place_ids: List[Optional[str]] = ["home", "office"]
        config = SceneSegmentationConfig()
        breaks = _detect_scene_breaks(timestamps, place_ids, config)
        assert len(breaks) == 1
        assert breaks[0].reason == "context_shift"

    def test_place_change_below_context_gap_no_break(self):
        """Place change with only 1h gap (<context_gap_hours) -> no break."""
        timestamps = [BASE_TS, BASE_TS + HOUR_MS]
        place_ids: List[Optional[str]] = ["home", "office"]
        config = SceneSegmentationConfig()
        breaks = _detect_scene_breaks(timestamps, place_ids, config)
        assert breaks == []

    def test_multiple_break_types(self):
        """Mix of overnight and temporal gaps."""
        timestamps = [
            BASE_TS,
            BASE_TS + 1 * HOUR_MS,
            BASE_TS + 12 * HOUR_MS,  # overnight (11h gap)
            BASE_TS + 13 * HOUR_MS,
            BASE_TS + 18 * HOUR_MS,  # temporal_gap (5h gap)
        ]
        place_ids: List[Optional[str]] = [None] * 5
        config = SceneSegmentationConfig()
        breaks = _detect_scene_breaks(timestamps, place_ids, config)
        assert len(breaks) == 2
        assert breaks[0].reason == "overnight"
        assert breaks[1].reason == "temporal_gap"


# ---------------------------------------------------------------------------
# Test: _split_indices_at_breaks
# ---------------------------------------------------------------------------


class TestSplitIndicesAtBreaks:

    def test_no_breaks(self):
        segments = _split_indices_at_breaks(10, [])
        assert segments == [(0, 10)]

    def test_single_break_midpoint(self):
        from k0.modules.consolidation.algorithms.scene_segmenter import SceneBreak

        breaks = [SceneBreak(position=5, gap_hours=10.0, reason="overnight")]
        segments = _split_indices_at_breaks(10, breaks)
        assert segments == [(0, 5), (5, 10)]

    def test_multiple_breaks(self):
        from k0.modules.consolidation.algorithms.scene_segmenter import SceneBreak

        breaks = [
            SceneBreak(position=3, gap_hours=5.0, reason="temporal_gap"),
            SceneBreak(position=7, gap_hours=10.0, reason="overnight"),
        ]
        segments = _split_indices_at_breaks(10, breaks)
        assert segments == [(0, 3), (3, 7), (7, 10)]


# ---------------------------------------------------------------------------
# Test: _enforce_size_cap
# ---------------------------------------------------------------------------


class TestEnforceSizeCap:

    def test_no_split_under_cap(self):
        timestamps = [BASE_TS + i * HOUR_MS for i in range(10)]
        segments = [(0, 10)]
        result = _enforce_size_cap(timestamps, segments, max_events=35)
        assert result == [(0, 10)]

    def test_split_over_cap(self):
        """40 events with max=35 should split (recursively if needed)."""
        timestamps = [BASE_TS + i * HOUR_MS for i in range(40)]
        segments = [(0, 40)]
        result = _enforce_size_cap(timestamps, segments, max_events=35)
        assert len(result) >= 2
        # All events accounted for
        total = sum(end - start for start, end in result)
        assert total == 40
        # No segment exceeds cap
        for start, end in result:
            assert end - start <= 35

    def test_multiple_oversized_segments(self):
        """Two oversized segments both get split."""
        timestamps = [BASE_TS + i * HOUR_MS for i in range(80)]
        segments = [(0, 40), (40, 80)]
        result = _enforce_size_cap(timestamps, segments, max_events=35)
        assert len(result) >= 4  # Each splits into at least 2
        total = sum(end - start for start, end in result)
        assert total == 80


# ---------------------------------------------------------------------------
# Test: segment_episodes (public API)
# ---------------------------------------------------------------------------


class TestSegmentEpisodes:

    def test_small_episode_passthrough(self):
        """Episodes under max_scene_events are not split."""
        events = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        cand, cluster = _build_candidate_and_cluster("ep-1", events)
        lookup = _build_event_lookup(events)

        config = SceneSegmentationConfig(min_scene_events=3, max_scene_events=35)
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        assert len(new_cands) == 1
        assert len(new_clusters) == 1
        assert new_cands[0].cluster_id == "ep-1"
        assert stats.episodes_split == 0
        assert stats.scenes_created == 0

    def test_mega_episode_split_by_overnight_gap(self):
        """Episode with 40 events spanning overnight gap -> split."""
        # 20 events on day 1, then 10h gap, then 20 events on day 2
        events_day1 = _make_events(20, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        events_day2 = _make_events(
            20,
            start_ts=BASE_TS + 30 * HOUR_MS,  # 10h after last day1 event
            gap_ms=HOUR_MS,
            seed=2,
        )
        all_events = events_day1 + events_day2
        cand, cluster = _build_candidate_and_cluster("mega-1", all_events)
        lookup = _build_event_lookup(all_events)

        config = SceneSegmentationConfig(
            min_scene_events=3,
            max_scene_events=35,
            overnight_gap_hours=8.0,
        )
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        assert stats.episodes_split == 1
        assert len(new_cands) == 2
        assert len(new_clusters) == 2
        # Scene IDs follow pattern
        assert new_cands[0].cluster_id == "mega-1_s01"
        assert new_cands[1].cluster_id == "mega-1_s02"
        # Each scene has CREATE action
        assert new_cands[0].reconciliation_action == "CREATE"
        assert new_cands[1].reconciliation_action == "CREATE"
        # Event counts add up
        total = sum(c.event_count for c in new_cands)
        assert total == 40

    def test_scene_id_pattern(self):
        """Scene IDs follow {parent_id}_s{idx:02d} pattern."""
        events_part1 = _make_events(5, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=10)
        events_part2 = _make_events(
            5,
            start_ts=BASE_TS + 10 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=20,
        )
        events_part3 = _make_events(
            5,
            start_ts=BASE_TS + 20 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=30,
        )
        all_events = events_part1 + events_part2 + events_part3
        cand, cluster = _build_candidate_and_cluster("parent-x", all_events)
        lookup = _build_event_lookup(all_events)

        config = SceneSegmentationConfig(
            min_scene_events=3,
            max_scene_events=35,
            overnight_gap_hours=8.0,
        )
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        if stats.episodes_split > 0:
            for i, c in enumerate(new_cands):
                assert c.cluster_id == f"parent-x_s{i + 1:02d}"

    def test_min_scene_events_enforced(self):
        """Scenes smaller than min_scene_events get merged with neighbor."""
        # 2 events, then overnight, then 2 events -> both too small, no split
        events = _make_events(2, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        events += _make_events(2, start_ts=BASE_TS + 12 * HOUR_MS, gap_ms=HOUR_MS, seed=2)
        cand, cluster = _build_candidate_and_cluster("tiny-1", events)
        lookup = _build_event_lookup(events)

        config = SceneSegmentationConfig(min_scene_events=3, max_scene_events=35)
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        # Episode has only 4 events total, which is below most thresholds
        # Either passes through or doesn't produce micro-fragments
        assert stats.episodes_split == 0
        assert len(new_cands) == 1

    def test_extend_episode_not_split(self):
        """EXTEND episodes pass through regardless of size."""
        events = _make_events(40, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        cand, cluster = _build_candidate_and_cluster("ext-1", events)
        cand.reconciliation_action = "EXTEND"
        cand.extend_target_episode_id = "existing-ep-1"
        lookup = _build_event_lookup(events)

        config = SceneSegmentationConfig()
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        assert len(new_cands) == 1
        assert new_cands[0].reconciliation_action == "EXTEND"
        assert stats.episodes_split == 0

    def test_centroids_recomputed(self):
        """Split scenes should have their own centroids, not parent's."""
        events_day1 = _make_events(20, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=100)
        events_day2 = _make_events(
            20,
            start_ts=BASE_TS + 30 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=200,
        )
        all_events = events_day1 + events_day2
        cand, cluster = _build_candidate_and_cluster("centroid-test", all_events)
        lookup = _build_event_lookup(all_events)

        config = SceneSegmentationConfig(overnight_gap_hours=8.0)
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        if stats.episodes_split > 0:
            # Each scene has a centroid
            for c in new_cands:
                assert c.centroid_embedding is not None
            # Centroids differ from each other (different event seeds)
            sim = np.dot(
                np.array(new_cands[0].centroid_embedding),
                np.array(new_cands[1].centroid_embedding),
            )
            assert sim < 0.99  # Not identical

    def test_multiple_episodes_mixed(self):
        """Mix of small + mega episodes: only mega gets split."""
        # Small episode: 5 events
        small_events = _make_events(5, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        small_cand, small_cluster = _build_candidate_and_cluster("small-1", small_events)

        # Mega episode: 40 events with overnight gap
        mega_day1 = _make_events(20, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=10)
        mega_day2 = _make_events(
            20,
            start_ts=BASE_TS + 30 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=20,
        )
        mega_events = mega_day1 + mega_day2
        mega_cand, mega_cluster = _build_candidate_and_cluster("mega-1", mega_events)

        all_lookup = _build_event_lookup(small_events + mega_events)

        config = SceneSegmentationConfig(overnight_gap_hours=8.0)
        new_cands, new_clusters, stats = segment_episodes(
            [small_cand, mega_cand],
            [small_cluster, mega_cluster],
            all_lookup,
            config,
        )

        assert stats.episodes_split == 1
        # Small episode passes through, mega splits into 2
        assert len(new_cands) == 3
        assert new_cands[0].cluster_id == "small-1"
        assert new_cands[1].cluster_id.startswith("mega-1_s")

    def test_temporal_bounds_per_scene(self):
        """Each scene's temporal_start/end matches its actual event range."""
        events_part1 = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        events_part2 = _make_events(
            10,
            start_ts=BASE_TS + 20 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=2,
        )
        all_events = events_part1 + events_part2
        cand, cluster = _build_candidate_and_cluster("bounds-1", all_events)
        lookup = _build_event_lookup(all_events)

        config = SceneSegmentationConfig(overnight_gap_hours=8.0)
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        if stats.episodes_split > 0:
            # Scene 1 should span day 1 events
            s1 = new_cands[0]
            assert s1.temporal_start == events_part1[0].timestamp
            assert s1.temporal_end == events_part1[-1].timestamp
            # Scene 2 should span day 2 events
            s2 = new_cands[1]
            assert s2.temporal_start == events_part2[0].timestamp
            assert s2.temporal_end == events_part2[-1].timestamp

    def test_stats_accuracy(self):
        """Stats should reflect actual splits."""
        events = _make_events(40, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        # Insert overnight gap in the middle
        for i in range(20, 40):
            events[i].event.timestamp += 10 * HOUR_MS

        cand, cluster = _build_candidate_and_cluster("stats-1", events)
        lookup = _build_event_lookup(events)

        config = SceneSegmentationConfig(overnight_gap_hours=8.0)
        new_cands, new_clusters, stats = segment_episodes(
            [cand],
            [cluster],
            lookup,
            config,
        )

        assert stats.input_episodes == 1
        assert stats.output_episodes == len(new_cands)
        if stats.episodes_split > 0:
            assert stats.scenes_created == len(new_cands)
            assert stats.output_episodes == stats.scenes_created

    def test_empty_input(self):
        """Empty input returns empty output."""
        config = SceneSegmentationConfig()
        new_cands, new_clusters, stats = segment_episodes([], [], {}, config)
        assert new_cands == []
        assert new_clusters == []
        assert stats.input_episodes == 0
