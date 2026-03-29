"""Tests for M9.10 fragment absorption algorithm.

Validates that micro-fragment episodes (<= absorb_max_events) are absorbed
into nearby compatible scenes based on temporal proximity, thread
compatibility, and centroid similarity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate
from k0.modules.consolidation.algorithms.fragment_absorber import (
    FragmentAbsorptionConfig,
    absorb_fragments,
)
from k0.pipelines.p03.phase_outputs import EpisodeCluster

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

HOUR_MS = 3_600_000
BASE_TS = 1_700_000_000_000


def _vec(seed: int = 1, dim: int = 768) -> List[float]:
    """Deterministic L2-normalized random vector."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float64)
    v /= np.linalg.norm(v)
    return v.tolist()


def _similar_vec(base: List[float], similarity: float = 0.9) -> List[float]:
    """Create a vector with approximately target cosine similarity to base."""
    rng = np.random.RandomState(42)
    base_arr = np.array(base, dtype=np.float64)
    noise = rng.randn(len(base)).astype(np.float64)
    noise /= np.linalg.norm(noise)
    # Spherical interpolation approximation
    result = similarity * base_arr + (1 - similarity) * noise
    result /= np.linalg.norm(result)
    return result.tolist()


@dataclass
class FakeEvent:
    event_id: str = ""
    timestamp: int = 0
    embedding_768: Optional[List[float]] = None
    place_id: Optional[str] = None
    narrative_thread_id: str = ""
    participants_json: str = "[]"
    sentiment_score: float = 0.0
    salience_score: float = 0.5
    activity_type: str = ""
    activity_type_ultrabert: str = ""
    social_context: str = ""
    social_intimacy: str = ""
    geohash_6: Optional[str] = None
    ner_entities_json: str = "[]"
    importance_score: float = 0.5
    importance_computed: bool = True
    affect_valence: float = 0.0
    affect_arousal: float = 0.0
    affect_dominance: float = 0.0
    narrative_arc_position: str = ""
    entities_json: str = "[]"
    emotions_json: str = "[]"


@dataclass
class FakeAdapter:
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
    thread_id: str = "",
) -> List[FakeAdapter]:
    events = []
    for i in range(n):
        evt = FakeEvent(
            event_id=f"evt-{seed}-{i:03d}",
            timestamp=start_ts + i * gap_ms,
            embedding_768=_vec(seed * 1000 + i),
            narrative_thread_id=thread_id,
        )
        events.append(FakeAdapter(event=evt))
    return events


def _build(
    cluster_id: str,
    events: List[FakeAdapter],
    centroid_seed: Optional[int] = None,
) -> tuple:
    event_ids = [e.event_id for e in events]
    # Use explicit centroid_seed or compute from events
    if centroid_seed is not None:
        centroid = _vec(centroid_seed)
    else:
        embeddings = [e.embedding_768 for e in events if e.embedding_768]
        if embeddings:
            arr = np.array(embeddings, dtype=np.float64)
            c = arr.mean(axis=0)
            n = np.linalg.norm(c)
            if n > 1e-12:
                c /= n
            centroid = c.tolist()
        else:
            centroid = None

    ts_list = [e.timestamp for e in events]
    cand = EpisodeCandidate(
        cluster_id=cluster_id,
        space_id="default",
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


def _lookup(*groups: List[FakeAdapter]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for events in groups:
        for e in events:
            result[e.event_id] = e
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAbsorbFragments:

    def test_no_fragments_passthrough(self):
        """No episodes with <= absorb_max_events -> all pass through."""
        events = _make_events(10, seed=1)
        cand, cluster = _build("scene-1", events)
        lookup = _lookup(events)

        config = FragmentAbsorptionConfig(absorb_max_events=4)
        new_cands, new_clusters, stats = absorb_fragments(
            [cand],
            [cluster],
            lookup,
            config,
        )

        assert len(new_cands) == 1
        assert stats.fragments_found == 0
        assert stats.fragments_absorbed == 0

    def test_fragment_absorbed_into_nearby_scene(self):
        """A 2-event fragment close to a 10-event scene -> absorbed."""
        scene_events = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        # Fragment 2h after scene ends -> within 6h gap
        frag_events = _make_events(
            2,
            start_ts=BASE_TS + 12 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=1,  # Same seed = similar embeddings
        )

        scene_cand, scene_cluster = _build("scene-1", scene_events, centroid_seed=1)
        frag_cand, frag_cluster = _build("frag-1", frag_events, centroid_seed=1)
        lookup = _lookup(scene_events, frag_events)

        config = FragmentAbsorptionConfig(
            absorb_max_events=4,
            absorb_max_gap_hours=6.0,
            absorb_min_similarity=0.30,  # Low threshold for test
        )
        new_cands, new_clusters, stats = absorb_fragments(
            [scene_cand, frag_cand],
            [scene_cluster, frag_cluster],
            lookup,
            config,
        )

        assert stats.fragments_found == 1
        assert stats.fragments_absorbed == 1
        assert len(new_cands) == 1  # Fragment gone, merged into scene
        assert new_cands[0].cluster_id == "scene-1"
        assert new_cands[0].event_count == 12  # 10 + 2

    def test_fragment_too_far_not_absorbed(self):
        """Fragment > absorb_max_gap_hours away -> orphaned."""
        scene_events = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        frag_events = _make_events(
            2,
            start_ts=BASE_TS + 100 * HOUR_MS,  # Way too far
            gap_ms=HOUR_MS,
            seed=1,
        )

        scene_cand, scene_cluster = _build("scene-1", scene_events, centroid_seed=1)
        frag_cand, frag_cluster = _build("frag-1", frag_events, centroid_seed=1)
        lookup = _lookup(scene_events, frag_events)

        config = FragmentAbsorptionConfig(absorb_max_gap_hours=6.0)
        new_cands, new_clusters, stats = absorb_fragments(
            [scene_cand, frag_cand],
            [scene_cluster, frag_cluster],
            lookup,
            config,
        )

        assert stats.fragments_found == 1
        assert stats.fragments_orphaned == 1
        assert len(new_cands) == 2  # Both survive

    def test_thread_incompatibility_blocks_absorption(self):
        """Fragment on thread-A won't absorb into scene on thread-B."""
        scene_events = _make_events(
            10,
            start_ts=BASE_TS,
            gap_ms=HOUR_MS,
            seed=1,
            thread_id="thread-A",
        )
        frag_events = _make_events(
            2,
            start_ts=BASE_TS + 12 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=1,
            thread_id="thread-B",
        )

        scene_cand, scene_cluster = _build("scene-1", scene_events, centroid_seed=1)
        frag_cand, frag_cluster = _build("frag-1", frag_events, centroid_seed=1)
        lookup = _lookup(scene_events, frag_events)

        config = FragmentAbsorptionConfig(
            absorb_max_events=4,
            absorb_max_gap_hours=6.0,
            absorb_min_similarity=0.1,
        )
        new_cands, new_clusters, stats = absorb_fragments(
            [scene_cand, frag_cand],
            [scene_cluster, frag_cluster],
            lookup,
            config,
        )

        assert stats.fragments_orphaned == 1
        assert len(new_cands) == 2

    def test_similarity_threshold_blocks_absorption(self):
        """Fragment with dissimilar centroid -> not absorbed."""
        scene_events = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        frag_events = _make_events(
            2,
            start_ts=BASE_TS + 12 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=999,  # Very different embeddings
        )

        scene_cand, scene_cluster = _build("scene-1", scene_events, centroid_seed=1)
        frag_cand, frag_cluster = _build("frag-1", frag_events, centroid_seed=999)
        lookup = _lookup(scene_events, frag_events)

        config = FragmentAbsorptionConfig(
            absorb_max_events=4,
            absorb_max_gap_hours=20.0,
            absorb_min_similarity=0.95,  # Very high threshold
        )
        new_cands, new_clusters, stats = absorb_fragments(
            [scene_cand, frag_cand],
            [scene_cluster, frag_cluster],
            lookup,
            config,
        )

        assert stats.fragments_orphaned == 1

    def test_no_scenes_available(self):
        """All episodes are fragments (no scenes) -> all orphaned."""
        frag1_events = _make_events(2, start_ts=BASE_TS, seed=1)
        frag2_events = _make_events(3, start_ts=BASE_TS + 5 * HOUR_MS, seed=2)

        frag1_cand, frag1_cluster = _build("frag-1", frag1_events)
        frag2_cand, frag2_cluster = _build("frag-2", frag2_events)
        lookup = _lookup(frag1_events, frag2_events)

        config = FragmentAbsorptionConfig(absorb_max_events=4)
        new_cands, new_clusters, stats = absorb_fragments(
            [frag1_cand, frag2_cand],
            [frag1_cluster, frag2_cluster],
            lookup,
            config,
        )

        assert stats.fragments_found == 2
        assert stats.fragments_orphaned == 2
        assert len(new_cands) == 2

    def test_empty_input(self):
        """Empty input -> empty output."""
        config = FragmentAbsorptionConfig()
        new_cands, new_clusters, stats = absorb_fragments([], [], {}, config)
        assert new_cands == []
        assert new_clusters == []
        assert stats.fragments_found == 0

    def test_absorbed_cluster_has_merged_event_ids(self):
        """After absorption, scene cluster contains fragment's event IDs."""
        scene_events = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        frag_events = _make_events(
            3,
            start_ts=BASE_TS + 12 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=1,
        )

        scene_cand, scene_cluster = _build("scene-1", scene_events, centroid_seed=1)
        frag_cand, frag_cluster = _build("frag-1", frag_events, centroid_seed=1)
        lookup = _lookup(scene_events, frag_events)

        config = FragmentAbsorptionConfig(
            absorb_max_events=4,
            absorb_max_gap_hours=6.0,
            absorb_min_similarity=0.30,
        )
        new_cands, new_clusters, stats = absorb_fragments(
            [scene_cand, frag_cand],
            [scene_cluster, frag_cluster],
            lookup,
            config,
        )

        if stats.fragments_absorbed > 0:
            merged = new_clusters[0]
            frag_ids = set(frag_cluster.member_event_ids)
            assert frag_ids.issubset(set(merged.member_event_ids))

    def test_stats_accuracy(self):
        """Stats fields match actual behavior."""
        scene_events = _make_events(10, start_ts=BASE_TS, gap_ms=HOUR_MS, seed=1)
        frag1_events = _make_events(
            2,
            start_ts=BASE_TS + 12 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=1,
        )
        frag2_events = _make_events(
            2,
            start_ts=BASE_TS + 200 * HOUR_MS,
            gap_ms=HOUR_MS,
            seed=999,
        )

        scene_cand, scene_cluster = _build("scene-1", scene_events, centroid_seed=1)
        frag1_cand, frag1_cluster = _build("frag-1", frag1_events, centroid_seed=1)
        frag2_cand, frag2_cluster = _build("frag-2", frag2_events, centroid_seed=999)
        lookup = _lookup(scene_events, frag1_events, frag2_events)

        config = FragmentAbsorptionConfig(
            absorb_max_events=4,
            absorb_max_gap_hours=6.0,
            absorb_min_similarity=0.30,
        )
        new_cands, new_clusters, stats = absorb_fragments(
            [scene_cand, frag1_cand, frag2_cand],
            [scene_cluster, frag1_cluster, frag2_cluster],
            lookup,
            config,
        )

        assert stats.fragments_found == 2
        assert stats.fragments_absorbed + stats.fragments_orphaned == 2
