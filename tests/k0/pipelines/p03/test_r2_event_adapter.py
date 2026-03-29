"""
Tests for EventAdapter signal passthrough (Epic 1.1).

Issue 1.1.7: Integration tests validating that EventAdapter exposes
all MW v2 signals from P03EventState to downstream algorithms.

Tests:
    Signal Passthrough (1.1.1-1.1.6):
        - test_geohash_passthrough: geohash + geohash_6 from P03EventState.geohash_6
        - test_geohash_empty_returns_none: Empty geohash_6 returns None
        - test_activity_type_passthrough: activity_type from P03EventState
        - test_activity_type_ultrabert_passthrough: UltraBERT 12-type
        - test_activity_empty_returns_none: Empty activity returns None
        - test_social_context_passthrough: social_context, social_intimacy
        - test_participants_json_passthrough: Non-empty participants_json
        - test_participants_json_empty_returns_none: "[]" returns None
        - test_narrative_thread_id_passthrough: narrative_thread_id
        - test_narrative_arc_position_passthrough: narrative_arc_position
        - test_narrative_empty_returns_none: Empty narrative returns None
        - test_affect_valence_passthrough: affect_valence float
        - test_affect_arousal_passthrough: affect_arousal float
        - test_affect_dominance_passthrough: affect_dominance float
        - test_sentiment_score_passthrough: sentiment_score float
        - test_salience_score_passthrough: salience_score float
        - test_temporal_orientation_passthrough: temporal_orientation
        - test_temporal_resolved_epoch_ms_passthrough: temporal_resolved_epoch_ms float
        - test_temporal_anchor_json_passthrough: Non-empty anchor JSON
        - test_temporal_anchor_json_empty_returns_none: "{}" returns None

    Original Properties (preserved):
        - test_event_id_passthrough: event_id
        - test_timestamp_passthrough: timestamp
        - test_embedding_768_passthrough: embedding_768
        - test_ner_entities_passthrough: ner_entities parsed from JSON
        - test_importance_score_passthrough: importance_score when computed

    Protocol Compliance:
        - test_satisfies_splittable_event_protocol: SplittableEvent protocol
        - test_satisfies_event_like_protocol: EventLike protocol
        - test_satisfies_clusterable_event_protocol: ClusterableEvent protocol

    Splitter Integration:
        - test_splitter_location_change_fires: geohash_6 triggers LOCATION_CHANGE
        - test_splitter_activity_change_fires: activity_type triggers ACTIVITY_CHANGE
        - test_splitter_no_split_same_signals: Same signals = no split
"""

from __future__ import annotations

from k0.modules.consolidation.algorithms.episode_splitter import EpisodeSplitter, SplitConfig
from k0.pipelines.p03.event_state import P03EventState
from k0.pipelines.p03.phases.r2_episodic_integrator import EventAdapter

# =============================================================================
# Fixtures
# =============================================================================


def _make_event(**overrides) -> P03EventState:
    """Factory for P03EventState with sensible defaults for testing."""
    defaults = dict(
        event_id="evt-test-001",
        hipp_event_id="hipp-001",
        content_text="Test event content",
        content_type="CHAT",
        content_hash="abc123",
        simhash_hex="0" * 16,
        timestamp=1700000000000,
        channel_id="ch-01",
        embedding_id="emb-001",
        embedding_768=[0.1] * 768,
        sentiment_score=0.5,
        sentiment_label="positive",
        ner_entities_json='[{"text": "Mom", "label": "PERSON"}]',
        # Affect & salience
        affect_valence=0.6,
        affect_arousal=0.4,
        affect_dominance=0.3,
        salience_score=0.7,
        # Social
        social_context="nuclear_family",
        social_intimacy="HIGH",
        participants_json='["actor-mom", "actor-dad"]',
        # Activity
        activity_type="meal",
        activity_type_ultrabert="DIARY",
        # Location
        geohash_6="9q8yyz",
        # Narrative
        narrative_thread_id="thread-abc",
        narrative_arc_position="MIDDLE",
        # Temporal
        temporal_orientation="PRESENT",
        temporal_resolved_epoch_ms=1700000500000.0,
        temporal_anchor_json='{"day_of_week": "Monday"}',
        # Importance (mark as computed so importance_score passes through)
        importance_score=0.85,
        importance_computed=True,
    )
    defaults.update(overrides)
    return P03EventState(**defaults)  # type: ignore[arg-type]


def _make_adapter(**overrides) -> EventAdapter:
    """Create EventAdapter wrapping a P03EventState with given overrides."""
    return EventAdapter(event=_make_event(**overrides))


# =============================================================================
# Issue 1.1.1: geohash / geohash_6 passthrough
# =============================================================================


class TestGeohashPassthrough:
    """Issue 1.1.1: geohash and geohash_6 from P03EventState.geohash_6."""

    def test_geohash_passthrough(self) -> None:
        adapter = _make_adapter(geohash_6="9q8yyz")
        assert adapter.geohash == "9q8yyz"

    def test_geohash_6_passthrough(self) -> None:
        adapter = _make_adapter(geohash_6="9q8yyz")
        assert adapter.geohash_6 == "9q8yyz"

    def test_geohash_empty_returns_none(self) -> None:
        adapter = _make_adapter(geohash_6="")
        assert adapter.geohash is None
        assert adapter.geohash_6 is None


# =============================================================================
# Issue 1.1.2: activity_type / activity_type_ultrabert passthrough
# =============================================================================


class TestActivityPassthrough:
    """Issue 1.1.2: activity_type and activity_type_ultrabert."""

    def test_activity_type_passthrough(self) -> None:
        adapter = _make_adapter(activity_type="meal")
        assert adapter.activity_type == "meal"

    def test_activity_type_ultrabert_passthrough(self) -> None:
        adapter = _make_adapter(activity_type_ultrabert="DIARY")
        assert adapter.activity_type_ultrabert == "DIARY"

    def test_activity_empty_returns_none(self) -> None:
        adapter = _make_adapter(activity_type="", activity_type_ultrabert="")
        assert adapter.activity_type is None
        assert adapter.activity_type_ultrabert is None


# =============================================================================
# Issue 1.1.3: social_context / social_intimacy / participants_json
# =============================================================================


class TestSocialPassthrough:
    """Issue 1.1.3: Social context signals."""

    def test_social_context_passthrough(self) -> None:
        adapter = _make_adapter(social_context="nuclear_family")
        assert adapter.social_context == "nuclear_family"

    def test_social_intimacy_passthrough(self) -> None:
        adapter = _make_adapter(social_intimacy="HIGH")
        assert adapter.social_intimacy == "HIGH"

    def test_participants_json_passthrough(self) -> None:
        adapter = _make_adapter(participants_json='["actor-mom", "actor-dad"]')
        assert adapter.participants_json == '["actor-mom", "actor-dad"]'

    def test_participants_json_empty_returns_none(self) -> None:
        adapter = _make_adapter(participants_json="[]")
        assert adapter.participants_json is None

    def test_social_empty_returns_none(self) -> None:
        adapter = _make_adapter(social_context="", social_intimacy="")
        assert adapter.social_context is None
        assert adapter.social_intimacy is None


# =============================================================================
# Issue 1.1.4: narrative_thread_id / narrative_arc_position
# =============================================================================


class TestNarrativePassthrough:
    """Issue 1.1.4: Narrative signals."""

    def test_narrative_thread_id_passthrough(self) -> None:
        adapter = _make_adapter(narrative_thread_id="thread-abc")
        assert adapter.narrative_thread_id == "thread-abc"

    def test_narrative_arc_position_passthrough(self) -> None:
        adapter = _make_adapter(narrative_arc_position="MIDDLE")
        assert adapter.narrative_arc_position == "MIDDLE"

    def test_narrative_empty_returns_none(self) -> None:
        adapter = _make_adapter(narrative_thread_id="", narrative_arc_position="")
        assert adapter.narrative_thread_id is None
        assert adapter.narrative_arc_position is None


# =============================================================================
# Issue 1.1.5: Affective signals
# =============================================================================


class TestAffectivePassthrough:
    """Issue 1.1.5: affect_valence, affect_arousal, affect_dominance, sentiment_score, salience_score."""

    def test_affect_valence_passthrough(self) -> None:
        adapter = _make_adapter(affect_valence=0.6)
        assert adapter.affect_valence == 0.6

    def test_affect_arousal_passthrough(self) -> None:
        adapter = _make_adapter(affect_arousal=0.4)
        assert adapter.affect_arousal == 0.4

    def test_affect_dominance_passthrough(self) -> None:
        adapter = _make_adapter(affect_dominance=0.3)
        assert adapter.affect_dominance == 0.3

    def test_sentiment_score_passthrough(self) -> None:
        adapter = _make_adapter(sentiment_score=0.5)
        assert adapter.sentiment_score == 0.5

    def test_salience_score_passthrough(self) -> None:
        adapter = _make_adapter(salience_score=0.7)
        assert adapter.salience_score == 0.7

    def test_affect_defaults_zero(self) -> None:
        """Default P03EventState values (0.0) pass through as 0.0, not None."""
        adapter = _make_adapter(
            affect_valence=0.0,
            affect_arousal=0.0,
            affect_dominance=0.0,
            sentiment_score=0.0,
            salience_score=0.0,
        )
        assert adapter.affect_valence == 0.0
        assert adapter.affect_arousal == 0.0
        assert adapter.affect_dominance == 0.0
        assert adapter.sentiment_score == 0.0
        assert adapter.salience_score == 0.0

    def test_affect_negative_valence(self) -> None:
        """Negative valence passes through correctly."""
        adapter = _make_adapter(affect_valence=-0.8)
        assert adapter.affect_valence == -0.8


# =============================================================================
# Issue 1.1.6: Temporal signals
# =============================================================================


class TestTemporalPassthrough:
    """Issue 1.1.6: temporal_orientation, temporal_resolved_epoch_ms, temporal_anchor_json."""

    def test_temporal_orientation_passthrough(self) -> None:
        adapter = _make_adapter(temporal_orientation="PAST")
        assert adapter.temporal_orientation == "PAST"

    def test_temporal_resolved_epoch_ms_passthrough(self) -> None:
        adapter = _make_adapter(temporal_resolved_epoch_ms=1700000500000.0)
        assert adapter.temporal_resolved_epoch_ms == 1700000500000.0

    def test_temporal_anchor_json_passthrough(self) -> None:
        adapter = _make_adapter(temporal_anchor_json='{"day_of_week": "Monday"}')
        assert adapter.temporal_anchor_json == '{"day_of_week": "Monday"}'

    def test_temporal_anchor_json_empty_returns_none(self) -> None:
        adapter = _make_adapter(temporal_anchor_json="{}")
        assert adapter.temporal_anchor_json is None

    def test_temporal_orientation_empty_returns_none(self) -> None:
        adapter = _make_adapter(temporal_orientation="")
        assert adapter.temporal_orientation is None

    def test_temporal_resolved_epoch_ms_zero(self) -> None:
        """Zero epoch passes through as 0.0 (not None)."""
        adapter = _make_adapter(temporal_resolved_epoch_ms=0.0)
        assert adapter.temporal_resolved_epoch_ms == 0.0


# =============================================================================
# Original property passthrough (regression guard)
# =============================================================================


class TestOriginalPassthrough:
    """Verify original EventAdapter properties still work."""

    def test_event_id_passthrough(self) -> None:
        adapter = _make_adapter(event_id="evt-xyz")
        assert adapter.event_id == "evt-xyz"

    def test_timestamp_passthrough(self) -> None:
        adapter = _make_adapter(timestamp=1700000000000)
        assert adapter.timestamp == 1700000000000

    def test_embedding_768_passthrough(self) -> None:
        emb = [0.5] * 768
        adapter = _make_adapter(embedding_768=emb)
        assert adapter.embedding_768 == emb

    def test_embedding_768_none(self) -> None:
        adapter = _make_adapter(embedding_768=None)
        assert adapter.embedding_768 is None

    def test_ner_entities_passthrough(self) -> None:
        adapter = _make_adapter(ner_entities_json='[{"text": "Mom", "label": "PERSON"}]')
        assert adapter.ner_entities == ["Mom"]

    def test_ner_entities_empty(self) -> None:
        adapter = _make_adapter(ner_entities_json="[]")
        assert adapter.ner_entities == []

    def test_ner_entities_invalid_json(self) -> None:
        adapter = _make_adapter(ner_entities_json="not-json")
        assert adapter.ner_entities is None

    def test_importance_score_when_computed(self) -> None:
        adapter = _make_adapter(importance_score=0.85, importance_computed=True)
        assert adapter.importance_score == 0.85

    def test_importance_score_when_not_computed(self) -> None:
        adapter = _make_adapter(importance_score=0.85, importance_computed=False)
        assert adapter.importance_score is None


# =============================================================================
# Protocol Compliance
# =============================================================================


class TestProtocolCompliance:
    """Verify EventAdapter satisfies downstream algorithm protocols."""

    def test_satisfies_splittable_event_protocol(self) -> None:
        """SplittableEvent requires: event_id, timestamp."""
        adapter = _make_adapter()
        # SplittableEvent protocol checks (episode_splitter.py L118-130)
        assert isinstance(adapter.event_id, str)
        assert isinstance(adapter.timestamp, int)

    def test_satisfies_event_like_protocol(self) -> None:
        """EventLike requires: event_id, timestamp, embedding_768."""
        adapter = _make_adapter()
        # EventLike protocol checks (composite_distance.py L131-150)
        assert isinstance(adapter.event_id, str)
        assert isinstance(adapter.timestamp, int)
        assert isinstance(adapter.embedding_768, list)

    def test_satisfies_clusterable_event_protocol(self) -> None:
        """ClusterableEvent requires: event_id, timestamp, embedding_768, sentiment_score."""
        adapter = _make_adapter()
        # ClusterableEvent protocol checks (episodic_hdbscan.py L136-155)
        assert isinstance(adapter.event_id, str)
        assert isinstance(adapter.timestamp, int)
        assert isinstance(adapter.embedding_768, list)
        assert isinstance(adapter.sentiment_score, float)

    def test_getattr_geohash_6_works(self) -> None:
        """EpisodeSplitter uses getattr(prev, 'geohash_6', None)."""
        adapter = _make_adapter(geohash_6="9q8yyz")
        assert getattr(adapter, "geohash_6", None) == "9q8yyz"

    def test_getattr_activity_type_works(self) -> None:
        """EpisodeSplitter uses getattr(prev, 'activity_type', None)."""
        adapter = _make_adapter(activity_type="meal")
        assert getattr(adapter, "activity_type", None) == "meal"


# =============================================================================
# Splitter Integration
# =============================================================================


class TestSplitterIntegration:
    """Verify EpisodeSplitter signals fire with real EventAdapter objects.

    Epic 3.3: Updated from _detect_break (first-match-wins) to
    _boundary_decision (accumulated scoring). Individual signals no longer
    cause splits alone; they contribute to an accumulated score.
    """

    def test_splitter_location_change_fires(self) -> None:
        """Different geohash_6 registers place_change channel contribution."""
        splitter = EpisodeSplitter(SplitConfig())
        prev = _make_adapter(
            event_id="e1",
            timestamp=1700000000000,
            geohash_6="9q8yyz",
        )
        curr = _make_adapter(
            event_id="e2",
            timestamp=1700000001000,
            geohash_6="u4pru",
        )
        decision = splitter._boundary_decision([prev], curr)
        assert "place_change" in decision.channel_contributions

    def test_splitter_activity_change_fires(self) -> None:
        """Different activity_type registers activity_change channel contribution."""
        splitter = EpisodeSplitter(SplitConfig())
        prev = _make_adapter(
            event_id="e1",
            timestamp=1700000000000,
            geohash_6="9q8yyz",
            activity_type="meal",
        )
        curr = _make_adapter(
            event_id="e2",
            timestamp=1700000001000,
            geohash_6="9q8yyz",
            activity_type="work",
        )
        decision = splitter._boundary_decision([prev], curr)
        assert "activity_change" in decision.channel_contributions

    def test_splitter_no_split_same_signals(self) -> None:
        """Same geohash_6 + same activity_type + small time gap = no split."""
        splitter = EpisodeSplitter(SplitConfig())
        prev = _make_adapter(
            event_id="e1",
            timestamp=1700000000000,
            geohash_6="9q8yyz",
            activity_type="meal",
        )
        curr = _make_adapter(
            event_id="e2",
            timestamp=1700000001000,
            geohash_6="9q8yyz",
            activity_type="meal",
        )
        decision = splitter._boundary_decision([prev], curr)
        assert decision.split is False


# =============================================================================
# Epic 3.6.0: Temporal support field passthrough
# =============================================================================


class TestTemporalSupportPassthrough:
    """Epic 3.6.0: temporal_links_json, time_of_day_bucket, circadian_slot,
    is_weekend, extraction_sequence on EventAdapter."""

    # --- temporal_links_json ---

    def test_temporal_links_json_passthrough(self) -> None:
        adapter = _make_adapter(temporal_links_json='[{"target": "evt-002", "relation": "before"}]')
        assert adapter.temporal_links_json == '[{"target": "evt-002", "relation": "before"}]'

    def test_temporal_links_json_empty_list_returns_none(self) -> None:
        adapter = _make_adapter(temporal_links_json="[]")
        assert adapter.temporal_links_json is None

    def test_temporal_links_json_empty_string_returns_none(self) -> None:
        adapter = _make_adapter(temporal_links_json="")
        assert adapter.temporal_links_json is None

    # --- time_of_day_bucket ---

    def test_time_of_day_bucket_passthrough(self) -> None:
        adapter = _make_adapter(time_of_day_bucket="MORNING")
        assert adapter.time_of_day_bucket == "MORNING"

    def test_time_of_day_bucket_empty_returns_none(self) -> None:
        adapter = _make_adapter(time_of_day_bucket="")
        assert adapter.time_of_day_bucket is None

    # --- circadian_slot ---

    def test_circadian_slot_passthrough(self) -> None:
        adapter = _make_adapter(circadian_slot="ACTIVE")
        assert adapter.circadian_slot == "ACTIVE"

    def test_circadian_slot_empty_returns_none(self) -> None:
        adapter = _make_adapter(circadian_slot="")
        assert adapter.circadian_slot is None

    # --- is_weekend ---

    def test_is_weekend_true(self) -> None:
        adapter = _make_adapter(is_weekend=True)
        assert adapter.is_weekend is True

    def test_is_weekend_false(self) -> None:
        adapter = _make_adapter(is_weekend=False)
        assert adapter.is_weekend is False

    def test_is_weekend_none(self) -> None:
        adapter = _make_adapter(is_weekend=None)
        assert adapter.is_weekend is None

    # --- extraction_sequence ---

    def test_extraction_sequence_passthrough(self) -> None:
        adapter = _make_adapter(extraction_sequence=3)
        assert adapter.extraction_sequence == 3

    def test_extraction_sequence_default_zero(self) -> None:
        adapter = _make_adapter(extraction_sequence=0)
        assert adapter.extraction_sequence == 0

    # --- Protocol compliance with new fields ---

    def test_event_like_has_temporal_context_fields(self) -> None:
        """EventLike protocol now includes temporal context fields."""
        adapter = _make_adapter(
            temporal_links_json='[{"target": "evt-002"}]',
            time_of_day_bucket="EVENING",
            circadian_slot="WIND_DOWN",
            is_weekend=True,
            extraction_sequence=2,
        )
        assert adapter.temporal_links_json is not None
        assert adapter.time_of_day_bucket == "EVENING"
        assert adapter.circadian_slot == "WIND_DOWN"
        assert adapter.is_weekend is True
        assert adapter.extraction_sequence == 2

    def test_splittable_event_has_temporal_context_fields(self) -> None:
        """SplittableEvent protocol now includes temporal context fields."""
        adapter = _make_adapter(
            time_of_day_bucket="MORNING",
            circadian_slot="WAKE",
            is_weekend=False,
            extraction_sequence=0,
        )
        assert adapter.time_of_day_bucket == "MORNING"
        assert adapter.circadian_slot == "WAKE"
        assert adapter.is_weekend is False
        assert adapter.extraction_sequence == 0
