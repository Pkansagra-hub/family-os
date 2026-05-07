"""Tests for FieldMapper (E-MW-3.1).

28 tests in 6 classes covering:
  - Direct field copy (text, topics, participants, confidence, metadata, operation)
  - Enum serialization (sentiment, activity, location, None, temporal_orientation)
  - K0 derived fields G1-G8
  - Nested serialization (affect, narrative, temporal_links, temporal)
  - Correction signals passthrough
  - Edge cases (None location, empty emotion_tags, embedding_text)
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from k1.memory_writer.config import MWConfig
from k1.memory_writer.envelope.field_mapper import FieldMapper
from k1.memory_writer.place_resolver import PlaceResolver
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ArcPosition,
    ElaborationDepth,
    ExtractionContext,
    LocationType,
    MemoryAtom,
    Narrative,
    NoveltyLevel,
    SentimentLabel,
    SourceType,
    TemporalLink,
    TemporalOrientation,
)

# ===========================================================================
# Helpers
# ===========================================================================


class StubPlaceResolver(PlaceResolver):
    """PlaceResolver that returns canned results without entity lookup."""

    def __init__(
        self,
        place_id: Optional[str] = None,
        geohash: Optional[str] = None,
    ) -> None:
        # Bypass parent __init__ which expects entity list
        object.__init__(self)
        self._place_id = place_id
        self._geohash = geohash

    def resolve_with_geohash(
        self,
        name: Optional[str],
        known_geohashes: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        if not name:
            return (None, None)
        return (self._place_id, self._geohash)


def _make_mapper(
    place_id: Optional[str] = "place_olive_garden",
    geohash: Optional[str] = "9q8yyz",
    config: Optional[MWConfig] = None,
) -> FieldMapper:
    resolver = StubPlaceResolver(place_id=place_id, geohash=geohash)
    return FieldMapper(place_resolver=resolver, config=config or MWConfig())


def _default_ctx(**overrides) -> ExtractionContext:
    defaults = dict(
        session_id="sess-001",
        conversation_turn=5,
        turn_timestamp_ms=1_700_000_000_000,  # 2023-11-14T22:13:20Z (Tuesday evening)
        control_context={"safety_band": "GREEN", "tenant_id": "t1", "space_id": "s1"},
    )
    defaults.update(overrides)
    return ExtractionContext(**defaults)


def _default_atom(**overrides) -> MemoryAtom:
    defaults = dict(
        text="Had dinner with Mom at Olive Garden",
        topics=["family", "dining"],
        categories=["daily_life"],
        activity_type=ActivityType.MEAL,
        participants=["person_mom"],
        location_name="Olive Garden",
        location_type=LocationType.RESTAURANT,
        sentiment_label=SentimentLabel.POSITIVE,
        emotion_tags=["contentment", "joy"],
        affect=Affect(valence=0.6, arousal=0.3, dominance=0.5),
        temporal_orientation=TemporalOrientation.PAST,
        source_type=SourceType.USER_STATED,
        novelty=NoveltyLevel.EXPECTED,
        elaboration_depth=ElaborationDepth.MENTION,
        confidence=0.95,
        session_id="sess-001",
        conversation_turn=5,
        language="en",
        conversation_anchor_ms=1_700_000_000_000,
        correction_signal=False,
        contradiction_signal=False,
    )
    defaults.update(overrides)
    return MemoryAtom(**defaults)


# ===========================================================================
# TestFieldMapperDirectCopy — 6 tests
# ===========================================================================


class TestFieldMapperDirectCopy:
    """Direct field copy: atom field → body key, unchanged."""

    def test_text_copied(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["text"] == "Had dinner with Mom at Olive Garden"

    def test_topics_copied_as_list(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["topics"] == ["family", "dining"]
        assert isinstance(body["topics"], list)

    def test_participants_copied(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["participants"] == ["person_mom"]

    def test_confidence_copied(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["confidence"] == 0.95

    def test_session_metadata_copied(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["session_id"] == "sess-001"
        assert body["conversation_turn"] == 5
        assert body["language"] == "en"

    def test_operation_always_upsert(self):
        mapper = _make_mapper()
        atom = _default_atom(operation="DELETE")  # ignored, always UPSERT
        body = mapper.map_atom_to_body(atom, _default_ctx(), "trace-1")
        assert body["operation"] == "UPSERT"


# ===========================================================================
# TestFieldMapperEnumSerialization — 5 tests
# ===========================================================================


class TestFieldMapperEnumSerialization:
    """All enum values serialized to strings (not Enum objects)."""

    def test_sentiment_label_to_string(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["sentiment_label"] == "positive"
        assert isinstance(body["sentiment_label"], str)

    def test_activity_type_to_string(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["activity_type"] == "MEAL"
        assert isinstance(body["activity_type"], str)

    def test_location_type_to_string(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["location_type"] == "restaurant"
        assert isinstance(body["location_type"], str)

    def test_none_enum_to_null(self):
        mapper = _make_mapper()
        atom = _default_atom(activity_type=None)
        body = mapper.map_atom_to_body(atom, _default_ctx(), "trace-1")
        assert body["activity_type"] is None

    def test_temporal_orientation_to_string(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "trace-1")
        assert body["temporal_orientation"] == "PAST"
        assert isinstance(body["temporal_orientation"], str)


# ===========================================================================
# TestFieldMapperDerivedFields — 7 tests (K0 gaps)
# ===========================================================================


class TestFieldMapperDerivedFields:
    """K0-required derived fields: G1-G8."""

    def test_g1_sentiment_score(self):
        mapper = _make_mapper()
        # POSITIVE → 0.5
        body_pos = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "t")
        assert body_pos["sentiment_score"] == 0.5

        # VERY_NEGATIVE → -0.9
        atom_vn = _default_atom(sentiment_label=SentimentLabel.VERY_NEGATIVE)
        body_vn = mapper.map_atom_to_body(atom_vn, _default_ctx(), "t")
        assert body_vn["sentiment_score"] == -0.9

    def test_g2_dominant_emotion(self):
        mapper = _make_mapper()
        atom = _default_atom(emotion_tags=["joy", "contentment"])
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["dominant_emotion"] == "joy"

    def test_g2_dominant_emotion_empty(self):
        mapper = _make_mapper()
        atom = _default_atom(emotion_tags=[])
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["dominant_emotion"] == "neutral"

    def test_g3_dominant_emotions_json(self):
        mapper = _make_mapper()
        atom = _default_atom(emotion_tags=["joy", "contentment", "gratitude"])
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        expected = [
            {"emotion": "joy", "confidence": 0.8},
            {"emotion": "contentment", "confidence": 0.8},
            {"emotion": "gratitude", "confidence": 0.8},
        ]
        assert body["dominant_emotions_json"] == expected

    def test_g4_affect_valence_flattened(self):
        mapper = _make_mapper()
        atom = _default_atom(affect=Affect(valence=0.8, arousal=0.5, dominance=0.6))
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["affect_valence"] == 0.8

    def test_g5_geohash_from_place_resolver(self):
        mapper = _make_mapper(place_id="place_olive_garden", geohash="9q8yyz")
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "t")
        assert body["geohash_6"] == "9q8yyz"
        assert body["place_id"] == "place_olive_garden"

    def test_g8_num_participants(self):
        mapper = _make_mapper()
        atom = _default_atom(participants=["person_mom", "person_dad", "person_sis"])
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["num_participants"] == 3


# ===========================================================================
# TestFieldMapperNestedSerialization — 4 tests
# ===========================================================================


class TestFieldMapperNestedSerialization:
    """Frozen dataclasses serialized to plain dicts."""

    def test_affect_to_dict(self):
        mapper = _make_mapper()
        atom = _default_atom(affect=Affect(0.8, 0.5, 0.6))
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["affect"] == {"valence": 0.8, "arousal": 0.5, "dominance": 0.6}

    def test_narrative_to_dict(self):
        mapper = _make_mapper()
        atom = _default_atom(
            narrative=Narrative(
                thread_id="thread-dinner",
                arc_position=ArcPosition.RISING_ACTION,
                is_goal_event=False,
            )
        )
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["narrative"] == {
            "arc_label": "thread-dinner",
            "arc_position": "RISING_ACTION",
            "arc_salience": 0.5,
        }

    def test_temporal_links_to_list(self):
        mapper = _make_mapper()
        links = (
            TemporalLink("yesterday", 1_699_900_000_000, 86_400_000, "RETROSPECTIVE", 0.9),
            TemporalLink("next Friday", 1_700_500_000_000, 86_400_000, "PROSPECTIVE", 0.8),
            TemporalLink("right now", 1_700_000_000_000, 60_000, "CONCURRENT", 1.0),
        )
        atom = _default_atom(temporal_links=links)
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert len(body["temporal_links"]) == 3
        assert body["temporal_links"][0]["mentioned_time"] == "yesterday"
        assert body["temporal_links"][0]["link_type"] == "RETROSPECTIVE"
        assert body["temporal_links"][1]["link_type"] == "PROSPECTIVE"

    def test_temporal_from_timestamp(self):
        """turn_timestamp_ms=1700000000000 → 2023-11-14 22:13:20 UTC (Tuesday evening)."""
        mapper = _make_mapper()
        ctx = _default_ctx(turn_timestamp_ms=1_700_000_000_000)
        body = mapper.map_atom_to_body(_default_atom(), ctx, "t")
        temporal = body["temporal"]
        assert temporal is not None
        assert temporal["day_of_week"] == "Tuesday"
        assert temporal["time_of_day"] == "evening"
        assert temporal["is_recurring"] is False


# ===========================================================================
# TestFieldMapperCorrectionSignals — 3 tests
# ===========================================================================


class TestFieldMapperCorrectionSignals:
    """v2.2 correction signals passed through to body."""

    def test_correction_signal_passed(self):
        mapper = _make_mapper()
        atom = _default_atom(correction_signal=True)
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["correction_signal"] is True

    def test_supersedes_concept_passed(self):
        mapper = _make_mapper()
        atom = _default_atom(supersedes_concept="cuisine_preference:italian")
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["supersedes_concept"] == "cuisine_preference:italian"

    def test_correction_defaults_false(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "t")
        assert body["correction_signal"] is False
        assert body["contradiction_signal"] is False


# ===========================================================================
# TestFieldMapperEdgeCases — 3 tests
# ===========================================================================


class TestFieldMapperEdgeCases:
    """Edge cases: None location, empty emotion, embedding_text."""

    def test_none_location_no_geohash(self):
        mapper = _make_mapper(place_id=None, geohash=None)
        atom = _default_atom(location_name=None, location_type=None)
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["place_id"] is None
        assert body["geohash_6"] is None

    def test_empty_emotion_tags(self):
        mapper = _make_mapper()
        atom = _default_atom(emotion_tags=[])
        body = mapper.map_atom_to_body(atom, _default_ctx(), "t")
        assert body["dominant_emotion"] == "neutral"
        assert body["dominant_emotions_json"] == []

    def test_embedding_text_always_null(self):
        mapper = _make_mapper()
        body = mapper.map_atom_to_body(_default_atom(), _default_ctx(), "t")
        assert body["embedding_text"] is None
