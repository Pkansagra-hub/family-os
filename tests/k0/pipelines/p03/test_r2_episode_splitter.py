"""
Tests for EpisodeSplitter -- accumulated boundary scoring (Epic 3.3).

Covers all 7 issues:
    3.3.0: SplittableEvent protocol extension
    3.3.1: Accumulated penalty/bonus model replacing first-match-wins
    3.3.2: Narrative, social, semantic, spatial, activity channels
    3.3.3: Sort verification (assert timestamp ordering)
    3.3.4: Calibrated thresholds (ResearchSplitConfig port)
    3.3.5: Narrative veto (same_thread_bonus)
    3.3.6: Weak boundary markers (sub-threshold scoring)

Research Reference:
    R2_RESEARCH_FINAL.md Section 2.1: research_balanced_v1 winner
    Phase 1 results: 31 sequences from 1360 events, proxy=0.8068
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import pytest

from k0.modules.consolidation.algorithms.episode_splitter import (
    MS_PER_HOUR,
    MS_PER_MINUTE,
    EpisodeSplitter,
    SplitConfig,
    SplitReason,
    _cosine_similarity,
    _dominant_thread,
    _geohash_distance,
    _parse_participants,
    _participant_jaccard,
    _recent_centroid,
)

# =============================================================================
# Test Fixtures
# =============================================================================

BASE_TS = 1_000_000_000_000  # ~2001-09-09 in ms


@dataclass
class MockEvent:
    """Mock event satisfying enriched SplittableEvent protocol."""

    event_id: str
    timestamp: int
    embedding_768: Optional[List[float]] = None
    place_id: Optional[str] = None
    geohash_6: Optional[str] = None
    narrative_thread_id: Optional[str] = None
    goal_context: Optional[str] = None
    participants_json: Optional[str] = None
    social_context: Optional[str] = None
    activity_type: Optional[str] = None


def make_events(
    count: int,
    start_ts: int = BASE_TS,
    gap_ms: int = 60_000,
    **kwargs,
) -> list[MockEvent]:
    """Create a sequence of events with consistent gaps."""
    return [MockEvent(f"e{i}", start_ts + i * gap_ms, **kwargs) for i in range(count)]


def _unit_embedding(dim: int = 768, seed: float = 0.1) -> List[float]:
    """Create a simple non-zero embedding for testing."""
    vec = [math.sin(seed * (i + 1)) for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm > 0 else vec


# =============================================================================
# Issue 3.3.4: SplitConfig Tests (calibrated thresholds)
# =============================================================================


class TestSplitConfig:
    """Test SplitConfig with research-calibrated defaults."""

    def test_research_defaults(self) -> None:
        """Defaults match research_balanced_v1 from R2_RESEARCH_FINAL.md Section 2.1."""
        cfg = SplitConfig()
        assert cfg.hard_time_gap_minutes == 480.0
        assert cfg.hard_episode_span_minutes == 1080.0
        assert cfg.hard_context_gap_minutes == 180.0
        assert cfg.hard_context_semantic_threshold == 0.55
        assert cfg.soft_split_threshold == 0.45
        assert cfg.thread_mismatch_penalty == 0.35
        assert cfg.same_thread_bonus == 0.45
        assert cfg.semantic_low_penalty == 0.30
        assert cfg.semantic_mid_penalty == 0.15
        assert cfg.strong_semantic_bonus == 0.20
        assert cfg.participant_zero_penalty == 0.15
        assert cfg.participant_overlap_bonus == 0.15
        assert cfg.place_change_penalty == 0.15
        assert cfg.activity_change_penalty == 0.10
        assert cfg.theta_soft == 0.15

    def test_legacy_aliases(self) -> None:
        """Legacy properties compute correctly from new params."""
        cfg = SplitConfig()
        assert cfg.max_episode_hours == 1080.0 / 60.0
        assert cfg.time_gap_minutes == 480.0
        assert cfg.max_episode_ms == int(1080 * MS_PER_MINUTE)
        assert cfg.time_gap_ms == int(480 * MS_PER_MINUTE)

    def test_validation_hard_time_gap(self) -> None:
        with pytest.raises(ValueError, match="hard_time_gap_minutes"):
            SplitConfig(hard_time_gap_minutes=0).validate()

    def test_validation_hard_episode_span(self) -> None:
        with pytest.raises(ValueError, match="hard_episode_span_minutes"):
            SplitConfig(hard_episode_span_minutes=0).validate()

    def test_validation_soft_split_threshold(self) -> None:
        with pytest.raises(ValueError, match="soft_split_threshold"):
            SplitConfig(soft_split_threshold=0).validate()
        with pytest.raises(ValueError, match="soft_split_threshold"):
            SplitConfig(soft_split_threshold=1.5).validate()

    def test_validation_theta_soft_below_threshold(self) -> None:
        with pytest.raises(ValueError, match="theta_soft"):
            SplitConfig(theta_soft=0.50, soft_split_threshold=0.45).validate()

    def test_validation_geohash_threshold(self) -> None:
        with pytest.raises(ValueError, match="geohash_distance_threshold"):
            SplitConfig(geohash_distance_threshold=0).validate()
        with pytest.raises(ValueError, match="geohash_distance_threshold"):
            SplitConfig(geohash_distance_threshold=13).validate()

    def test_serialization_round_trip(self) -> None:
        cfg = SplitConfig(
            soft_split_threshold=0.50,
            same_thread_bonus=0.40,
            theta_soft=0.20,
        )
        data = cfg.to_dict()
        restored = SplitConfig.from_dict(data)
        assert restored.soft_split_threshold == 0.50
        assert restored.same_thread_bonus == 0.40
        assert restored.theta_soft == 0.20

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {"soft_split_threshold": 0.50, "unknown_key": 999}
        cfg = SplitConfig.from_dict(data)
        assert cfg.soft_split_threshold == 0.50


# =============================================================================
# Issue 3.3.0: SplittableEvent Protocol Tests
# =============================================================================


class TestSplittableEventProtocol:
    """Test that MockEvent satisfies the enriched SplittableEvent protocol."""

    def test_core_fields(self) -> None:
        e = MockEvent("e1", BASE_TS)
        assert e.event_id == "e1"
        assert e.timestamp == BASE_TS

    def test_optional_fields_default_none(self) -> None:
        e = MockEvent("e1", BASE_TS)
        assert e.embedding_768 is None
        assert e.place_id is None
        assert e.geohash_6 is None
        assert e.narrative_thread_id is None
        assert e.goal_context is None
        assert e.participants_json is None
        assert e.social_context is None
        assert e.activity_type is None

    def test_enriched_fields_populated(self) -> None:
        e = MockEvent(
            "e1",
            BASE_TS,
            embedding_768=[0.1] * 768,
            place_id="home",
            narrative_thread_id="thread_1",
            participants_json="alice,bob",
            social_context="family",
            activity_type="conversation",
        )
        assert e.place_id == "home"
        assert e.narrative_thread_id == "thread_1"
        assert e.participants_json == "alice,bob"


# =============================================================================
# Issue 3.3.1: Basic Splitting Tests (accumulated model)
# =============================================================================


class TestEpisodeSplitterBasic:
    """Test basic splitting behavior."""

    def test_empty_input(self) -> None:
        result = EpisodeSplitter().split([])
        assert result.episodes == []
        assert result.split_count == 0
        assert result.total_events == 0

    def test_single_event(self) -> None:
        event = MockEvent("e1", BASE_TS)
        result = EpisodeSplitter().split([event])
        assert len(result.episodes) == 1
        assert result.episodes[0][0].event_id == "e1"
        assert result.split_count == 0

    def test_no_splits_within_threshold(self) -> None:
        """Events 1 minute apart with no signal changes stay together."""
        events = make_events(10, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1
        assert len(result.episodes[0]) == 10

    def test_simplified_interface(self) -> None:
        events = make_events(5, gap_ms=1000)
        episodes = EpisodeSplitter().split_long_sequences(events)
        assert len(episodes) == 1
        assert len(episodes[0]) == 5


# =============================================================================
# Issue 3.3.1: Tier 1 Hard Boundary Tests
# =============================================================================


class TestTier1HardBoundaries:
    """Test Tier 1 hard boundaries that bypass accumulation."""

    def test_hard_time_gap_8h(self) -> None:
        """Gap >= 480 min (8h) triggers instant split."""
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 5 * MS_PER_MINUTE),
            MockEvent("e3", BASE_TS + int(485.5 * MS_PER_MINUTE)),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2
        assert result.split_reasons.get(SplitReason.HARD_TIME_GAP) == 1

    def test_hard_episode_span_18h(self) -> None:
        """Episode spanning >= 1080 min (18h) triggers split."""
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 6 * MS_PER_HOUR),
            MockEvent("e3", BASE_TS + 12 * MS_PER_HOUR),
            MockEvent("e4", BASE_TS + int(18.1 * MS_PER_HOUR)),
        ]
        cfg = SplitConfig(hard_time_gap_minutes=1200)
        result = EpisodeSplitter(cfg).split(events)
        assert len(result.episodes) == 2
        assert result.split_reasons.get(SplitReason.HARD_EPISODE_SPAN) == 1

    def test_hard_context_jump(self) -> None:
        """Place change + 3h gap + low semantic + different thread = instant split."""
        emb_a = _unit_embedding(seed=0.1)
        emb_b = _unit_embedding(seed=5.0)
        events = [
            MockEvent(
                "e1", BASE_TS, embedding_768=emb_a, place_id="home", narrative_thread_id="t1"
            ),
            MockEvent(
                "e2",
                BASE_TS + int(181 * MS_PER_MINUTE),
                embedding_768=emb_b,
                place_id="office",
                narrative_thread_id="t2",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2
        assert result.split_reasons.get(SplitReason.HARD_CONTEXT_JUMP) == 1

    def test_hard_context_jump_not_triggered_same_thread(self) -> None:
        """Context jump does NOT fire when same thread (narrative coherence)."""
        emb_a = _unit_embedding(seed=0.1)
        emb_b = _unit_embedding(seed=5.0)
        events = [
            MockEvent(
                "e1", BASE_TS, embedding_768=emb_a, place_id="home", narrative_thread_id="t1"
            ),
            MockEvent(
                "e2",
                BASE_TS + int(181 * MS_PER_MINUTE),
                embedding_768=emb_b,
                place_id="office",
                narrative_thread_id="t1",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert result.split_reasons.get(SplitReason.HARD_CONTEXT_JUMP, 0) == 0

    def test_hard_time_gap_overrides_same_thread(self) -> None:
        """Tier 1 hard time gap fires even for same-thread events."""
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1"),
            MockEvent("e2", BASE_TS + 9 * MS_PER_HOUR, narrative_thread_id="t1"),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2
        assert result.split_reasons.get(SplitReason.HARD_TIME_GAP) == 1


# =============================================================================
# Issue 3.3.1: Tier 2 Accumulated Scoring Tests
# =============================================================================


class TestTier2AccumulatedScoring:
    """Test accumulated penalty/bonus model."""

    def test_single_penalty_below_threshold_no_split(self) -> None:
        """Single thread_mismatch (0.35) minus participant_overlap_bonus (0.15)
        = net 0.20 < 0.45 threshold = no split."""
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, narrative_thread_id="t2"),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1

    def test_multiple_penalties_combine_to_split(self) -> None:
        """thread_mismatch (0.35) + semantic_low (0.30) - participant_overlap (0.15)
        = 0.50 >= 0.45 threshold = split."""
        emb_a = _unit_embedding(seed=0.1)
        emb_b = _unit_embedding(seed=5.0)
        sim = _cosine_similarity(emb_a, emb_b)
        assert sim is not None and sim < 0.55

        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1", embedding_768=emb_a),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, narrative_thread_id="t2", embedding_768=emb_b),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2
        assert result.split_reasons.get(SplitReason.SOFT_BOUNDARY) == 1

    def test_bonus_prevents_split(self) -> None:
        """thread_mismatch (0.35) + participant_zero (0.15)
        - strong_semantic (0.20) - participant_overlap_bonus (0.0, not applicable)
        = 0.30 < 0.45 = no split.

        Note: participant_zero fires because e1 has no participants but e2 does.
        participant_overlap = 0.0, so overlap_bonus does NOT fire (0.0 < 0.50).
        strong_semantic fires because identical embeddings -> cosine=1.0 >= 0.86.
        """
        emb = _unit_embedding(seed=0.1)
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1", embedding_768=emb),
            MockEvent(
                "e2",
                BASE_TS + MS_PER_MINUTE,
                narrative_thread_id="t2",
                embedding_768=emb,
                participants_json="alice",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1

    def test_boundary_decisions_populated(self) -> None:
        """BoundaryDecision objects are tracked for each pair."""
        events = make_events(3, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        assert len(result.boundary_decisions) == 2

    def test_channel_contributions_tracked(self) -> None:
        """Channel contributions recorded in BoundaryDecision."""
        events = [
            MockEvent("e1", BASE_TS, activity_type="work"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, activity_type="exercise"),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.boundary_decisions) == 1
        decision = result.boundary_decisions[0]
        assert "activity_change" in decision.channel_contributions
        assert decision.channel_contributions["activity_change"] == 0.10


# =============================================================================
# Issue 3.3.2: Channel-Specific Tests
# =============================================================================


class TestNarrativeChannel:
    """Test narrative thread mismatch/bonus channels."""

    def test_thread_mismatch_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, narrative_thread_id="t2"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("thread_mismatch") == 0.35

    def test_partial_thread_mismatch(self) -> None:
        """One event has thread, other doesn't."""
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("partial_thread_mismatch") == 0.10

    def test_no_thread_penalty_when_both_missing(self) -> None:
        """No thread info on either event = no penalty."""
        events = make_events(2, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "thread_mismatch" not in d.channel_contributions
        assert "partial_thread_mismatch" not in d.channel_contributions


class TestSemanticChannel:
    """Test semantic similarity penalty/bonus channels."""

    def test_semantic_low_penalty(self) -> None:
        """Cosine < 0.55 triggers semantic_low_penalty."""
        emb_a = _unit_embedding(seed=0.1)
        emb_b = _unit_embedding(seed=5.0)
        events = [
            MockEvent("e1", BASE_TS, embedding_768=emb_a),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, embedding_768=emb_b),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "semantic_low" in d.channel_contributions

    def test_strong_semantic_bonus(self) -> None:
        """Identical embeddings -> cosine ~1.0 -> strong semantic bonus."""
        emb = _unit_embedding(seed=0.1)
        events = [
            MockEvent("e1", BASE_TS, embedding_768=emb),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, embedding_768=emb),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "strong_semantic_bonus" in d.channel_contributions
        assert d.channel_contributions["strong_semantic_bonus"] == -0.20

    def test_no_semantic_penalty_when_no_embeddings(self) -> None:
        """Missing embeddings produce neutral contribution."""
        events = make_events(2, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "semantic_low" not in d.channel_contributions
        assert "semantic_mid" not in d.channel_contributions
        assert "strong_semantic_bonus" not in d.channel_contributions


class TestSocialChannel:
    """Test participant and social context channels."""

    def test_participant_zero_penalty(self) -> None:
        """No participant overlap when both have participants."""
        events = [
            MockEvent("e1", BASE_TS, participants_json="alice"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, participants_json="bob"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("participant_zero") == 0.15

    def test_participant_overlap_bonus(self) -> None:
        """Strong participant overlap triggers bonus."""
        events = [
            MockEvent("e1", BASE_TS, participants_json="alice,bob"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, participants_json="alice,bob"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("participant_overlap_bonus") == -0.15

    def test_no_participant_penalty_when_both_missing(self) -> None:
        """No participants on either event = no participant_zero penalty.
        (Both empty -> jaccard=1.0 -> overlap bonus fires instead.)"""
        events = make_events(2, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "participant_zero" not in d.channel_contributions
        # Both empty -> jaccard 1.0 -> overlap bonus fires
        assert d.channel_contributions.get("participant_overlap_bonus") == -0.15

    def test_social_context_change_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, social_context="family"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, social_context="work"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("social_change") == 0.10


class TestSpatialChannel:
    """Test place change penalty and geohash fallback."""

    def test_place_change_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, place_id="home"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, place_id="office"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("place_change") == 0.15

    def test_same_place_no_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, place_id="home"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, place_id="home"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "place_change" not in d.channel_contributions

    def test_geohash_fallback_place_change(self) -> None:
        """When place_id is missing, use geohash_6 for spatial signal."""
        events = [
            MockEvent("e1", BASE_TS, geohash_6="u4pruy"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, geohash_6="gcpvj0"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("place_change") == 0.15

    def test_same_place_short_gap_bonus(self) -> None:
        """Same place + short gap triggers bonus."""
        events = [
            MockEvent("e1", BASE_TS, place_id="home"),
            MockEvent("e2", BASE_TS + 30 * MS_PER_MINUTE, place_id="home"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("same_place_short_gap_bonus") == -0.05

    def test_no_spatial_signal_when_both_missing(self) -> None:
        events = make_events(2, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "place_change" not in d.channel_contributions


class TestActivityChannel:
    """Test activity type change channel."""

    def test_activity_change_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, activity_type="work"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, activity_type="exercise"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("activity_change") == 0.10

    def test_same_activity_no_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, activity_type="work"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, activity_type="work"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "activity_change" not in d.channel_contributions

    def test_missing_activity_no_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS, activity_type="work"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "activity_change" not in d.channel_contributions


class TestTemporalGapTiers:
    """Test tiered time gap penalties."""

    def test_medium_gap_90_min(self) -> None:
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 91 * MS_PER_MINUTE),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("medium_gap") == 0.10

    def test_large_gap_180_min(self) -> None:
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 181 * MS_PER_MINUTE),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("large_gap") == 0.20

    def test_very_large_gap_360_min(self) -> None:
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 361 * MS_PER_MINUTE),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("very_large_gap") == 0.30

    def test_short_gap_no_penalty(self) -> None:
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 30 * MS_PER_MINUTE),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert "medium_gap" not in d.channel_contributions
        assert "large_gap" not in d.channel_contributions
        assert "very_large_gap" not in d.channel_contributions


# =============================================================================
# Issue 3.3.5: Narrative Veto Tests
# =============================================================================


class TestNarrativeVeto:
    """Test that same_thread_bonus suppresses splits (narrative veto)."""

    def test_same_thread_prevents_moderate_split(self) -> None:
        """Same thread + moderate penalties: place (0.15) + activity (0.10)
        - same_thread (0.45) - participant_overlap (0.15) = net -0.35 < 0.45."""
        events = [
            MockEvent(
                "e1", BASE_TS, narrative_thread_id="t1", place_id="home", activity_type="work"
            ),
            MockEvent(
                "e2",
                BASE_TS + MS_PER_MINUTE,
                narrative_thread_id="t1",
                place_id="office",
                activity_type="exercise",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1

    def test_same_thread_extreme_penalty_still_splits(self) -> None:
        """Same thread + extreme accumulated penalties > threshold = split.

        Scoring: semantic_low (0.30) + participant_zero (0.15) +
        place_change (0.15) + activity_change (0.10) + very_large_gap (0.30)
        - same_thread_bonus (0.45) = 0.55 >= 0.45.
        """
        emb_a = _unit_embedding(seed=0.1)
        emb_b = _unit_embedding(seed=5.0)
        events = [
            MockEvent(
                "e1",
                BASE_TS,
                narrative_thread_id="t1",
                embedding_768=emb_a,
                place_id="home",
                activity_type="work",
                participants_json="alice",
            ),
            MockEvent(
                "e2",
                BASE_TS + 361 * MS_PER_MINUTE,
                narrative_thread_id="t1",
                embedding_768=emb_b,
                place_id="office",
                activity_type="exercise",
                participants_json="bob",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2

    def test_same_thread_tier1_hard_gap_overrides_veto(self) -> None:
        """Hard time gap (8h) fires even with same thread."""
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1"),
            MockEvent("e2", BASE_TS + 9 * MS_PER_HOUR, narrative_thread_id="t1"),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2
        assert result.split_reasons.get(SplitReason.HARD_TIME_GAP) == 1

    def test_different_threads_with_enough_penalty_splits(self) -> None:
        """Different threads accumulate enough to split.

        Scoring: thread_mismatch (0.35) + place_change (0.15) +
        activity_change (0.10) + participant_zero (0.15) = 0.75 >= 0.45.
        Explicit participants prevent the empty-jaccard overlap bonus.
        """
        events = [
            MockEvent(
                "e1",
                BASE_TS,
                narrative_thread_id="t1",
                activity_type="work",
                place_id="home",
                participants_json="alice",
            ),
            MockEvent(
                "e2",
                BASE_TS + MS_PER_MINUTE,
                narrative_thread_id="t2",
                activity_type="exercise",
                place_id="office",
                participants_json="bob",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2

    def test_one_thread_missing_no_veto(self) -> None:
        """When one thread is missing, veto does not apply (neutral)."""
        events = [
            MockEvent(
                "e1", BASE_TS, narrative_thread_id="t1", activity_type="work", place_id="home"
            ),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, activity_type="exercise", place_id="office"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.same_thread is False
        assert "same_thread_bonus" not in d.channel_contributions


# =============================================================================
# Issue 3.3.3: Sort Verification Tests
# =============================================================================


class TestSortVerification:
    """Test timestamp ordering verification."""

    def test_sorted_events_ok(self) -> None:
        events = make_events(5, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        assert result.total_events == 5

    def test_equal_timestamps_ok(self) -> None:
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS),
            MockEvent("e3", BASE_TS),
        ]
        result = EpisodeSplitter().split(events)
        assert result.total_events == 3

    def test_unsorted_events_raises(self) -> None:
        events = [
            MockEvent("e1", BASE_TS + 1000),
            MockEvent("e2", BASE_TS),
        ]
        with pytest.raises(AssertionError, match="Events must be sorted"):
            EpisodeSplitter().split(events)

    def test_partially_unsorted_raises(self) -> None:
        events = [
            MockEvent("e1", BASE_TS),
            MockEvent("e2", BASE_TS + 1000),
            MockEvent("e3", BASE_TS + 500),
        ]
        with pytest.raises(AssertionError, match="Events must be sorted"):
            EpisodeSplitter().split(events)


# =============================================================================
# Issue 3.3.6: Weak Boundary Marker Tests
# =============================================================================


class TestWeakBoundaryMarkers:
    """Test sub-threshold weak boundary recording."""

    def test_weak_boundary_recorded(self) -> None:
        """Score between theta_soft (0.15) and threshold (0.45) = weak marker.

        activity_change (0.10) + medium_gap (0.10) + participant_zero (0.15)
        = 0.35. No overlap bonus since overlap=0.0.
        0.15 <= 0.35 < 0.45 -> weak boundary.
        """
        events = [
            MockEvent("e1", BASE_TS, activity_type="work", participants_json="alice"),
            MockEvent(
                "e2",
                BASE_TS + 91 * MS_PER_MINUTE,
                activity_type="exercise",
                participants_json="bob",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1
        assert len(result.weak_boundaries) == 1
        wb = result.weak_boundaries[0]
        assert wb.prev_event_id == "e1"
        assert wb.curr_event_id == "e2"
        assert 0.15 <= wb.score < 0.45

    def test_no_weak_boundary_below_theta_soft(self) -> None:
        """Score below theta_soft (0.15) = no marker.

        activity_change (0.10) - participant_overlap_bonus (0.15) = -0.05
        -> below theta_soft.
        """
        events = [
            MockEvent("e1", BASE_TS, activity_type="work"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, activity_type="exercise"),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.weak_boundaries) == 0

    def test_no_weak_boundary_above_threshold(self) -> None:
        """Score >= threshold causes split, not a weak marker."""
        emb_a = _unit_embedding(seed=0.1)
        emb_b = _unit_embedding(seed=5.0)
        events = [
            MockEvent("e1", BASE_TS, narrative_thread_id="t1", embedding_768=emb_a),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, narrative_thread_id="t2", embedding_768=emb_b),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2
        assert len(result.weak_boundaries) == 0

    def test_weak_boundary_channel_contributions(self) -> None:
        """Weak boundary records channel contributions for debugging."""
        events = [
            MockEvent("e1", BASE_TS, activity_type="work", participants_json="alice"),
            MockEvent(
                "e2",
                BASE_TS + 91 * MS_PER_MINUTE,
                activity_type="exercise",
                participants_json="bob",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.weak_boundaries) == 1
        wb = result.weak_boundaries[0]
        assert "activity_change" in wb.channel_contributions
        assert "medium_gap" in wb.channel_contributions
        assert "participant_zero" in wb.channel_contributions

    def test_weak_boundary_does_not_alter_splitting(self) -> None:
        """Weak markers are purely observational."""
        events = [
            MockEvent("e1", BASE_TS, activity_type="work", participants_json="alice"),
            MockEvent(
                "e2",
                BASE_TS + 91 * MS_PER_MINUTE,
                activity_type="exercise",
                participants_json="bob",
            ),
            MockEvent(
                "e3",
                BASE_TS + 92 * MS_PER_MINUTE,
                activity_type="exercise",
                participants_json="bob",
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1
        assert len(result.episodes[0]) == 3


# =============================================================================
# Multi-Signal Integration Tests
# =============================================================================


class TestMultiSignalIntegration:
    """Test realistic multi-signal scenarios."""

    def test_morning_routine_stays_together(self) -> None:
        """Same place, same participants, same thread, short gaps = one episode."""
        emb = _unit_embedding(seed=0.3)
        events = [
            MockEvent(
                "e1",
                BASE_TS,
                place_id="home",
                participants_json="alice,bob",
                narrative_thread_id="morning",
                embedding_768=emb,
            ),
            MockEvent(
                "e2",
                BASE_TS + 15 * MS_PER_MINUTE,
                place_id="home",
                participants_json="alice,bob",
                narrative_thread_id="morning",
                embedding_768=emb,
            ),
            MockEvent(
                "e3",
                BASE_TS + 30 * MS_PER_MINUTE,
                place_id="home",
                participants_json="alice,bob",
                narrative_thread_id="morning",
                embedding_768=emb,
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1

    def test_context_shift_work_to_home(self) -> None:
        """Multiple signals change simultaneously = strong split."""
        emb_work = _unit_embedding(seed=0.1)
        emb_home = _unit_embedding(seed=5.0)
        events = [
            MockEvent(
                "e1",
                BASE_TS,
                place_id="office",
                participants_json="colleague_a,colleague_b",
                narrative_thread_id="project",
                activity_type="work",
                social_context="professional",
                embedding_768=emb_work,
            ),
            MockEvent(
                "e2",
                BASE_TS + 91 * MS_PER_MINUTE,
                place_id="home",
                participants_json="spouse",
                narrative_thread_id="evening",
                activity_type="leisure",
                social_context="family",
                embedding_768=emb_home,
            ),
        ]
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 2

    def test_sparse_signals_only_bonuses(self) -> None:
        """Events with no enriched signals get participant_overlap bonus
        (both empty -> jaccard=1.0 -> bonus). Score is negative, no split."""
        events = make_events(5, gap_ms=MS_PER_MINUTE)
        result = EpisodeSplitter().split(events)
        assert len(result.episodes) == 1
        for d in result.boundary_decisions:
            assert d.score < 0.0

    def test_goal_context_bonus(self) -> None:
        """Same goal context provides bonus resisting split."""
        events = [
            MockEvent("e1", BASE_TS, goal_context="plan_vacation"),
            MockEvent("e2", BASE_TS + MS_PER_MINUTE, goal_context="plan_vacation"),
        ]
        result = EpisodeSplitter().split(events)
        d = result.boundary_decisions[0]
        assert d.channel_contributions.get("same_goal_bonus") == -0.10

    def test_split_stats_include_weak_boundaries(self) -> None:
        """get_split_stats reports weak boundary count."""
        events = [
            MockEvent("e1", BASE_TS, activity_type="work", participants_json="alice"),
            MockEvent(
                "e2",
                BASE_TS + 91 * MS_PER_MINUTE,
                activity_type="exercise",
                participants_json="bob",
            ),
        ]
        result = EpisodeSplitter().split(events)
        stats = EpisodeSplitter().get_split_stats(result)
        assert stats["weak_boundary_count"] == 1

    def test_split_stats_empty(self) -> None:
        result = EpisodeSplitter().split([])
        stats = EpisodeSplitter().get_split_stats(result)
        assert stats["episode_count"] == 0
        assert stats["weak_boundary_count"] == 0


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Test module-level helper functions."""

    def test_cosine_similarity_identical(self) -> None:
        emb = [1.0, 0.0, 0.0]
        assert _cosine_similarity(emb, emb) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_similarity_none(self) -> None:
        assert _cosine_similarity(None, [1.0]) is None
        assert _cosine_similarity([1.0], None) is None
        assert _cosine_similarity(None, None) is None

    def test_cosine_similarity_empty(self) -> None:
        assert _cosine_similarity([], [1.0]) is None
        assert _cosine_similarity([1.0], []) is None

    def test_geohash_distance_identical(self) -> None:
        assert _geohash_distance("u4pruyd", "u4pruyd") == 0

    def test_geohash_distance_one_char_diff(self) -> None:
        assert _geohash_distance("u4pruyd", "u4pruyc") == 1

    def test_geohash_distance_completely_different(self) -> None:
        assert _geohash_distance("u4pruyd", "gcpvj0d") == 7

    def test_geohash_distance_empty(self) -> None:
        assert _geohash_distance("", "abc") == 3
        assert _geohash_distance("abc", "") == 3
        assert _geohash_distance("", "") == 0

    def test_parse_participants(self) -> None:
        assert _parse_participants("alice,bob") == {"alice", "bob"}
        assert _parse_participants(None) == set()
        assert _parse_participants("") == set()
        assert _parse_participants(" alice , bob ") == {"alice", "bob"}

    def test_dominant_thread(self) -> None:
        events = [
            MockEvent("e1", 1, narrative_thread_id="t1"),
            MockEvent("e2", 2, narrative_thread_id="t1"),
            MockEvent("e3", 3, narrative_thread_id="t2"),
        ]
        assert _dominant_thread(events) == "t1"

    def test_dominant_thread_none(self) -> None:
        events = make_events(3, start_ts=1, gap_ms=1)
        assert _dominant_thread(events) is None

    def test_recent_centroid(self) -> None:
        events = [
            MockEvent("e1", 1, embedding_768=[1.0, 0.0]),
            MockEvent("e2", 2, embedding_768=[0.0, 1.0]),
        ]
        centroid = _recent_centroid(events)
        assert centroid is not None
        assert centroid[0] == pytest.approx(0.5)
        assert centroid[1] == pytest.approx(0.5)

    def test_recent_centroid_no_embeddings(self) -> None:
        events = make_events(3, start_ts=1, gap_ms=1)
        assert _recent_centroid(events) is None

    def test_participant_jaccard_full_overlap(self) -> None:
        seq = [MockEvent("e1", 1, participants_json="alice,bob")]
        event = MockEvent("e2", 2, participants_json="alice,bob")
        assert _participant_jaccard(seq, event) == pytest.approx(1.0)

    def test_participant_jaccard_no_overlap(self) -> None:
        seq = [MockEvent("e1", 1, participants_json="alice")]
        event = MockEvent("e2", 2, participants_json="bob")
        assert _participant_jaccard(seq, event) == pytest.approx(0.0)

    def test_participant_jaccard_both_empty(self) -> None:
        seq = [MockEvent("e1", 1)]
        event = MockEvent("e2", 2)
        assert _participant_jaccard(seq, event) == pytest.approx(1.0)


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Test that the rewritten splitter maintains backward-compatible interface."""

    def test_split_result_has_episodes(self) -> None:
        result = EpisodeSplitter().split(make_events(3, gap_ms=MS_PER_MINUTE))
        assert hasattr(result, "episodes")
        assert hasattr(result, "split_count")
        assert hasattr(result, "split_reasons")
        assert hasattr(result, "total_events")
        assert hasattr(result, "episode_count")

    def test_split_result_has_new_fields(self) -> None:
        result = EpisodeSplitter().split(make_events(3, gap_ms=MS_PER_MINUTE))
        assert hasattr(result, "weak_boundaries")
        assert hasattr(result, "boundary_decisions")

    def test_legacy_split_reasons_still_exist(self) -> None:
        assert SplitReason.NONE == "none"
        assert SplitReason.LOCATION_CHANGE == "location_change"
        assert SplitReason.ACTIVITY_CHANGE == "activity_change"
        assert SplitReason.TIME_GAP == "time_gap"
        assert SplitReason.HARD_LIMIT == "hard_limit"

    def test_new_split_reasons(self) -> None:
        assert SplitReason.HARD_TIME_GAP == "hard_time_gap"
        assert SplitReason.HARD_EPISODE_SPAN == "hard_episode_span"
        assert SplitReason.HARD_CONTEXT_JUMP == "hard_context_jump"
        assert SplitReason.SOFT_BOUNDARY == "soft_boundary"

    def test_geohash_distance_method(self) -> None:
        """Legacy _geohash_distance method still works."""
        splitter = EpisodeSplitter()
        assert splitter._geohash_distance("u4pruyd", "u4pruyd") == 0
        assert splitter._geohash_distance("u4pruyd", "gcpvj0d") == 7
