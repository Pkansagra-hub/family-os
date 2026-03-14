"""
Epic 6.4: Cross-Batch Episode Extension Matching Tests.

Tests for CrossBatchExtendMatcher that identifies newly-formed episodes
which should EXTEND existing episodes from previous consolidation batches.

Issues covered:
    6.4.1: EXTEND action in episode matching
    6.4.2: Cross-batch merge eligibility criteria
    6.4.3: Prevent duplicate episodes (consolidation_status update — downstream)
    6.4.4: Integration tests for cross-batch scenarios
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.centroid_calculator import EpisodeCandidate
from k0.modules.consolidation.algorithms.cross_batch_extend import (
    CrossBatchExtendConfig,
    CrossBatchExtendMatcher,
    CrossBatchExtendStats,
    _cosine_sim_lists,
    _cosine_sim_np,
    _dominant_thread_for_candidate,
)
from k0.pipelines.p03.phases.r2_episodic_integrator import R2Config

# =============================================================================
# Fixtures
# =============================================================================

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS


@dataclass
class MockEvent:
    """Mock event for cross-batch extend testing."""

    event_id: str
    narrative_thread_id: Optional[str] = None
    timestamp: int = 1_000_000_000_000


def _unit_vec(dim: int = 10, angle_offset: float = 0.0) -> List[float]:
    """Unit vector with controllable angle for similarity testing."""
    vec = [0.0] * dim
    vec[0] = math.cos(angle_offset)
    vec[1] = math.sin(angle_offset)
    return vec


def _make_candidate(
    cluster_id: str,
    event_ids: List[str],
    centroid: Optional[List[float]] = None,
    temporal_start: int = 1_000_000_000_000,
    temporal_end: int = 1_000_000_060_000,
) -> EpisodeCandidate:
    return EpisodeCandidate(
        cluster_id=cluster_id,
        space_id="default",
        event_ids=event_ids,
        event_count=len(event_ids),
        centroid_embedding=centroid,
        temporal_start=temporal_start,
        temporal_end=temporal_end,
    )


def _make_existing_episode(
    episode_id: str,
    embedding: Optional[List[float]] = None,
    narrative_thread_id: Optional[str] = None,
    start_time_utc: int = 1_000_000_000_000,
    end_time_utc: int = 1_000_000_060_000,
    version: int = 1,
) -> Dict[str, Any]:
    return {
        "episode_id": episode_id,
        "embedding": np.array(embedding, dtype=np.float64) if embedding else None,
        "narrative_thread_id": narrative_thread_id,
        "start_time_utc": start_time_utc,
        "end_time_utc": end_time_utc,
        "version": version,
    }


def _make_events(specs: List[tuple]) -> Dict[str, MockEvent]:
    """Build event lookup from (event_id, thread_id) tuples."""
    lookup = {}
    for spec in specs:
        eid = spec[0]
        tid = spec[1] if len(spec) > 1 else None
        lookup[eid] = MockEvent(event_id=eid, narrative_thread_id=tid)
    return lookup


# =============================================================================
# Helper functions
# =============================================================================


class TestCosineSimHelpers:
    def test_cosine_sim_lists_identical(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_sim_lists(v, v) == pytest.approx(1.0)

    def test_cosine_sim_lists_orthogonal(self):
        assert _cosine_sim_lists([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_cosine_sim_np_identical(self):
        v = np.array([1.0, 0.0, 0.0])
        assert _cosine_sim_np(v, [1.0, 0.0, 0.0]) == pytest.approx(1.0)

    def test_cosine_sim_np_orthogonal(self):
        assert _cosine_sim_np(np.array([1.0, 0.0]), [0.0, 1.0]) == pytest.approx(0.0)


class TestDominantThreadForCandidate:
    def test_single_thread(self):
        events = _make_events([("e1", "t1"), ("e2", "t1"), ("e3", "t1")])
        assert _dominant_thread_for_candidate(["e1", "e2", "e3"], events) == "t1"

    def test_majority_thread(self):
        events = _make_events([("e1", "t1"), ("e2", "t1"), ("e3", "t2")])
        assert _dominant_thread_for_candidate(["e1", "e2", "e3"], events) == "t1"

    def test_no_threads(self):
        events = _make_events([("e1", None), ("e2", None)])
        assert _dominant_thread_for_candidate(["e1", "e2"], events) is None


# =============================================================================
# No-extend cases
# =============================================================================


class TestNoExtend:
    def test_no_existing_episodes(self):
        emb = _unit_vec()
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [], events)
        assert matches[0] is None
        assert stats.candidates_extended == 0
        assert stats.candidates_new == 1

    def test_low_similarity_no_extend(self):
        emb_a = _unit_vec(10, 0.0)
        emb_b = _unit_vec(10, math.pi / 2)  # orthogonal -> sim = 0
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb_a)
        existing = _make_existing_episode("ep-1", embedding=emb_b, narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is None
        assert stats.candidates_new == 1

    def test_different_thread_no_extend(self):
        emb = _unit_vec()
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        existing = _make_existing_episode("ep-1", embedding=emb, narrative_thread_id="t2")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is None
        assert stats.candidates_extended == 0

    def test_temporal_gap_too_large(self):
        emb = _unit_vec()
        candidate = _make_candidate(
            "c1",
            ["e1", "e2"],
            centroid=emb,
            temporal_start=1_000_000_000_000,
            temporal_end=1_000_000_060_000,
        )
        # 8 days earlier -> beyond 7-day default
        gap = 8 * DAY_MS
        existing = _make_existing_episode(
            "ep-1",
            embedding=emb,
            narrative_thread_id="t1",
            start_time_utc=1_000_000_000_000 - gap,
            end_time_utc=1_000_000_000_000 - gap + 60_000,
        )
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is None

    def test_no_centroid_no_extend(self):
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=None)
        existing = _make_existing_episode("ep-1", embedding=_unit_vec(), narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is None
        assert stats.candidates_new == 1

    def test_empty_candidates(self):
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([], [], {})
        assert matches == []
        assert stats.candidates_checked == 0


# =============================================================================
# Extend cases
# =============================================================================


class TestExtend:
    def test_same_thread_high_similarity_extends(self):
        emb = _unit_vec()
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        existing = _make_existing_episode("ep-1", embedding=emb, narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is not None
        assert matches[0].target_episode_id == "ep-1"
        assert matches[0].similarity == pytest.approx(1.0, abs=0.01)
        assert stats.candidates_extended == 1

    def test_extend_at_threshold_boundary(self):
        """Similarity just above 0.60 should extend."""
        # cos(0.9200) ~ 0.6026 > 0.60
        emb_a = _unit_vec(10, 0.0)
        emb_b = _unit_vec(10, 0.9200)
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb_a)
        existing = _make_existing_episode("ep-1", embedding=emb_b, narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is not None
        assert stats.candidates_extended == 1

    def test_picks_best_matching_episode(self):
        emb = _unit_vec(10, 0.0)
        emb_close = _unit_vec(10, 0.1)  # cos(0.1) ~ 0.995
        emb_far = _unit_vec(10, 0.8)  # cos(0.8) ~ 0.697
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        ep_close = _make_existing_episode("ep-close", embedding=emb_close, narrative_thread_id="t1")
        ep_far = _make_existing_episode("ep-far", embedding=emb_far, narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [ep_far, ep_close], events)
        assert matches[0].target_episode_id == "ep-close"

    def test_extend_returns_target_version(self):
        emb = _unit_vec()
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        existing = _make_existing_episode(
            "ep-1", embedding=emb, narrative_thread_id="t1", version=3
        )
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, _ = matcher.match([candidate], [existing], events)
        assert matches[0].target_version == 3

    def test_thread_not_required_when_disabled(self):
        """When require_same_thread=False, different threads can extend."""
        emb = _unit_vec()
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        existing = _make_existing_episode("ep-1", embedding=emb, narrative_thread_id="t2")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        config = CrossBatchExtendConfig(require_same_thread=False)
        matcher = CrossBatchExtendMatcher(config=config)
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is not None
        assert stats.candidates_extended == 1

    def test_no_thread_info_on_existing_still_extends(self):
        """If existing episode has no thread info, thread check is skipped."""
        emb = _unit_vec()
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        existing = _make_existing_episode("ep-1", embedding=emb, narrative_thread_id=None)
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        # When existing has no thread, the thread check passes (thread_id is None)
        assert matches[0] is not None

    def test_overlapping_temporal_window_extends(self):
        """Candidates overlapping in time with existing episodes should extend."""
        emb = _unit_vec()
        candidate = _make_candidate(
            "c1",
            ["e1", "e2"],
            centroid=emb,
            temporal_start=1_000_000_000_000,
            temporal_end=1_000_000_120_000,
        )
        existing = _make_existing_episode(
            "ep-1",
            embedding=emb,
            narrative_thread_id="t1",
            start_time_utc=1_000_000_060_000,  # overlaps with candidate
            end_time_utc=1_000_000_180_000,
        )
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is not None

    def test_multiple_candidates_mixed(self):
        """Some candidates extend, others create new."""
        emb = _unit_vec()
        emb_different = _unit_vec(10, math.pi / 2)  # orthogonal
        c1 = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        c2 = _make_candidate("c2", ["e3", "e4"], centroid=emb_different)
        existing = _make_existing_episode("ep-1", embedding=emb, narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1"), ("e3", "t1"), ("e4", "t1")])
        matcher = CrossBatchExtendMatcher()
        matches, stats = matcher.match([c1, c2], [existing], events)
        assert matches[0] is not None  # c1 extends
        assert matches[1] is None  # c2 too different
        assert stats.candidates_extended == 1
        assert stats.candidates_new == 1


# =============================================================================
# EpisodeCandidate fields (6.4.1)
# =============================================================================


class TestEpisodeCandidateFields:
    def test_default_action_is_create(self):
        c = EpisodeCandidate(cluster_id="t", space_id="s")
        assert c.reconciliation_action == "CREATE"

    def test_extend_fields_default_none(self):
        c = EpisodeCandidate(cluster_id="t", space_id="s")
        assert c.extend_target_episode_id is None
        assert c.extend_similarity == 0.0

    def test_set_extend_fields(self):
        c = EpisodeCandidate(cluster_id="t", space_id="s")
        c.reconciliation_action = "EXTEND"
        c.extend_target_episode_id = "ep-123"
        c.extend_similarity = 0.75
        assert c.reconciliation_action == "EXTEND"
        assert c.extend_target_episode_id == "ep-123"


# =============================================================================
# Config
# =============================================================================


class TestCrossBatchExtendConfig:
    def test_defaults(self):
        cfg = CrossBatchExtendConfig()
        assert cfg.centroid_sim_threshold == 0.60
        assert cfg.require_same_thread is True
        assert cfg.max_temporal_gap_ms == 7 * 24 * 3_600_000

    def test_custom_threshold(self):
        cfg = CrossBatchExtendConfig(centroid_sim_threshold=0.80)
        emb = _unit_vec(10, 0.0)
        emb_mod = _unit_vec(10, 0.5)  # cos(0.5) ~ 0.877 > 0.80
        candidate = _make_candidate("c1", ["e1", "e2"], centroid=emb)
        existing = _make_existing_episode("ep-1", embedding=emb_mod, narrative_thread_id="t1")
        events = _make_events([("e1", "t1"), ("e2", "t1")])
        matcher = CrossBatchExtendMatcher(config=cfg)
        matches, stats = matcher.match([candidate], [existing], events)
        assert matches[0] is not None


# =============================================================================
# Stats (6.4 observability)
# =============================================================================


class TestExtendStats:
    def test_stats_to_dict(self):
        stats = CrossBatchExtendStats(
            candidates_checked=10,
            candidates_extended=3,
            candidates_new=7,
        )
        d = stats.to_dict()
        assert d["candidates_checked"] == 10
        assert d["candidates_extended"] == 3
        assert d["candidates_new"] == 7


# =============================================================================
# R2Config fields (6.4)
# =============================================================================


class TestR2ConfigExtendFields:
    def test_default_enabled(self):
        cfg = R2Config()
        assert cfg.enable_cross_batch_extend is True

    def test_can_disable(self):
        cfg = R2Config(enable_cross_batch_extend=False)
        assert cfg.enable_cross_batch_extend is False

    def test_config_accepts_extend_config(self):
        ext_cfg = CrossBatchExtendConfig(centroid_sim_threshold=0.70)
        cfg = R2Config(cross_batch_extend_config=ext_cfg)
        assert cfg.cross_batch_extend_config.centroid_sim_threshold == 0.70

    def test_existing_extend_threshold_still_present(self):
        """The episode_extend_threshold field predates Epic 6.4 and is preserved."""
        cfg = R2Config()
        assert cfg.episode_extend_threshold == 0.60
