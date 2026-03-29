"""
Unit tests for ObservationContext dataclass.

Tests the holistic context container for memory observations.
Covers factory methods, serialization, and edge cases.

Spec Reference: docs/plans/temporal_fix.md Issue 7.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from k0.modules.consolidation.algorithms.observation_context import ObservationContext

# =============================================================================
# Mock P03EventState for testing
# =============================================================================


@dataclass
class MockEventState:
    """Minimal mock of P03EventState for testing."""

    event_id: str = "evt_001"
    timestamp: int = 1704067200000  # 2024-01-01 00:00:00 UTC

    # Emotional context
    sentiment_score: float = 0.75
    sentiment_label: str = "positive"
    affect_valence: float = 0.5
    affect_arousal: float = 0.6
    emotions_json: str = '["joy", "anticipation"]'

    # Salience context
    salience_score: float = 0.8
    salience_band: Optional[str] = "HIGH"
    novelty_score: Optional[float] = 0.9

    # Modality context
    ingress_channel: Optional[str] = "voice"
    ingress_source: Optional[str] = "alexa"
    device_kind: Optional[str] = "speaker"

    # Physical context
    location_name: Optional[str] = "Kitchen"
    location_type: Optional[str] = "home"
    geohash_6: Optional[str] = "9q8yy"

    # Social context
    social_context: Optional[str] = "family"
    social_intimacy: Optional[str] = "HIGH"
    is_solo_event: Optional[bool] = False
    num_participants: Optional[int] = 3

    # Temporal context
    time_of_day_bucket: Optional[str] = "MORNING"
    circadian_slot: Optional[str] = "ACTIVE"
    is_weekend: Optional[bool] = False
    day_of_week: Optional[str] = "Monday"


@dataclass
class MinimalEventState:
    """Event state with only required fields."""

    event_id: str = "evt_minimal"
    timestamp: int = 1704067200000


# =============================================================================
# Factory Method Tests
# =============================================================================


class TestFromEvent:
    """Tests for ObservationContext.from_event() factory."""

    def test_extracts_temporal_context(self) -> None:
        """from_event extracts temporal fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.observed_at == 1704067200000
        assert ctx.time_of_day_bucket == "MORNING"
        assert ctx.circadian_slot == "ACTIVE"
        assert ctx.is_weekend is False
        assert ctx.day_of_week == "Monday"

    def test_extracts_emotional_context(self) -> None:
        """from_event extracts emotional fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.sentiment_score == 0.75
        assert ctx.sentiment_label == "positive"
        assert ctx.affect_valence == 0.5
        assert ctx.affect_arousal == 0.6
        assert ctx.dominant_emotion == "joy"

    def test_extracts_salience_context(self) -> None:
        """from_event extracts salience fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.salience_score == 0.8
        assert ctx.salience_band == "HIGH"
        assert ctx.novelty_score == 0.9

    def test_extracts_modality_context(self) -> None:
        """from_event extracts modality fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.ingress_channel == "voice"
        assert ctx.ingress_source == "alexa"
        assert ctx.device_kind == "speaker"

    def test_extracts_physical_context(self) -> None:
        """from_event extracts physical context fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.location_name == "Kitchen"
        assert ctx.location_type == "home"
        assert ctx.geohash_6 == "9q8yy"

    def test_extracts_social_context(self) -> None:
        """from_event extracts social context fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.social_context == "family"
        assert ctx.social_intimacy == "HIGH"
        assert ctx.is_solo_event is False
        assert ctx.num_participants == 3

    def test_sets_provenance(self) -> None:
        """from_event sets provenance fields."""
        event = MockEventState(event_id="evt_prov_test")
        ctx = ObservationContext.from_event(event)

        assert ctx.source_event_id == "evt_prov_test"
        assert ctx.observation_type == "REINFORCEMENT"
        assert ctx.confidence == 1.0

    def test_handles_minimal_event(self) -> None:
        """from_event works with minimal event (only required fields)."""
        event = MinimalEventState()
        ctx = ObservationContext.from_event(event)

        assert ctx.observed_at == 1704067200000
        assert ctx.source_event_id == "evt_minimal"
        # Optional fields should be None
        assert ctx.sentiment_score is None
        assert ctx.location_name is None
        assert ctx.social_context is None

    def test_handles_empty_emotions_json(self) -> None:
        """from_event handles empty emotions JSON."""
        event = MockEventState(emotions_json="[]")
        ctx = ObservationContext.from_event(event)

        assert ctx.dominant_emotion is None

    def test_handles_invalid_emotions_json(self) -> None:
        """from_event handles invalid emotions JSON."""
        event = MockEventState(emotions_json="not json")
        ctx = ObservationContext.from_event(event)

        assert ctx.dominant_emotion is None

    def test_handles_null_emotions_json(self) -> None:
        """from_event handles None emotions JSON."""
        event = MockEventState(emotions_json=None)  # type: ignore
        ctx = ObservationContext.from_event(event)

        assert ctx.dominant_emotion is None


class TestFromTimestamp:
    """Tests for ObservationContext.from_timestamp() factory."""

    def test_creates_minimal_context(self) -> None:
        """from_timestamp creates context with only observed_at."""
        ctx = ObservationContext.from_timestamp(1704067200000)

        assert ctx.observed_at == 1704067200000
        assert ctx.observation_type == "REINFORCEMENT"
        assert ctx.confidence == 1.0

    def test_all_optional_fields_none(self) -> None:
        """from_timestamp leaves all optional fields None."""
        ctx = ObservationContext.from_timestamp(1704067200000)

        # Check all optional fields are None
        assert ctx.sentiment_score is None
        assert ctx.sentiment_label is None
        assert ctx.location_name is None
        assert ctx.social_context is None
        assert ctx.ingress_channel is None
        assert ctx.source_event_id is None


# =============================================================================
# Serialization Tests
# =============================================================================


class TestToDict:
    """Tests for to_dict() serialization."""

    def test_includes_required_fields(self) -> None:
        """to_dict includes required fields."""
        ctx = ObservationContext.from_timestamp(1704067200000)
        d = ctx.to_dict()

        assert "observed_at" in d
        assert d["observed_at"] == 1704067200000

    def test_excludes_none_values(self) -> None:
        """to_dict excludes None values."""
        ctx = ObservationContext.from_timestamp(1704067200000)
        d = ctx.to_dict()

        # None values should not be in dict
        assert "sentiment_score" not in d
        assert "location_name" not in d

    def test_includes_non_none_values(self) -> None:
        """to_dict includes non-None optional values."""
        ctx = ObservationContext(
            observed_at=1704067200000,
            sentiment_score=0.8,
            location_name="Kitchen",
        )
        d = ctx.to_dict()

        assert d["sentiment_score"] == 0.8
        assert d["location_name"] == "Kitchen"


class TestToDbRow:
    """Tests for to_db_row() database serialization."""

    def test_includes_required_db_fields(self) -> None:
        """to_db_row includes required database columns."""
        ctx = ObservationContext.from_timestamp(1704067200000)
        row = ctx.to_db_row()

        assert row["observed_at"] == 1704067200000
        assert row["observation_type"] == "REINFORCEMENT"
        assert row["observation_weight"] == 1.0

    def test_maps_confidence_to_weight(self) -> None:
        """to_db_row maps confidence to observation_weight."""
        ctx = ObservationContext(observed_at=1704067200000, confidence=0.85)
        row = ctx.to_db_row()

        assert row["observation_weight"] == 0.85

    def test_excludes_none_optional_fields(self) -> None:
        """to_db_row excludes None optional columns."""
        ctx = ObservationContext.from_timestamp(1704067200000)
        row = ctx.to_db_row()

        # These should not be in row since they're None
        assert "sentiment_score" not in row
        assert "location_name" not in row

    def test_includes_all_non_none_fields(self) -> None:
        """to_db_row includes all non-None optional fields."""
        event = MockEventState()
        ctx = ObservationContext.from_event(event)
        row = ctx.to_db_row()

        # Check emotional context
        assert row["sentiment_score"] == 0.75
        assert row["sentiment_label"] == "positive"
        assert row["dominant_emotion"] == "joy"

        # Check physical context
        assert row["location_name"] == "Kitchen"
        assert row["location_type"] == "home"

        # Check social context
        assert row["social_context"] == "family"
        assert row["num_participants"] == 3


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestExtractFirstEmotion:
    """Tests for _extract_first_emotion helper."""

    def test_extracts_first_from_array(self) -> None:
        """Extracts first emotion from JSON array."""
        result = ObservationContext._extract_first_emotion('["joy", "anticipation"]')
        assert result == "joy"

    def test_returns_none_for_empty_array(self) -> None:
        """Returns None for empty array."""
        result = ObservationContext._extract_first_emotion("[]")
        assert result is None

    def test_returns_none_for_none_input(self) -> None:
        """Returns None for None input."""
        result = ObservationContext._extract_first_emotion(None)
        assert result is None

    def test_returns_none_for_invalid_json(self) -> None:
        """Returns None for invalid JSON."""
        result = ObservationContext._extract_first_emotion("not json")
        assert result is None

    def test_returns_none_for_object_json(self) -> None:
        """Returns None for JSON object (not array)."""
        result = ObservationContext._extract_first_emotion('{"emotion": "joy"}')
        assert result is None


class TestWithType:
    """Tests for with_type() immutable update."""

    def test_returns_new_instance(self) -> None:
        """with_type returns new instance."""
        ctx1 = ObservationContext.from_timestamp(1704067200000)
        ctx2 = ctx1.with_type("FIRST_SEEN")

        assert ctx1 is not ctx2
        assert ctx1.observation_type == "REINFORCEMENT"
        assert ctx2.observation_type == "FIRST_SEEN"

    def test_preserves_other_fields(self) -> None:
        """with_type preserves all other fields."""
        ctx1 = ObservationContext(
            observed_at=1704067200000,
            sentiment_score=0.8,
            location_name="Kitchen",
        )
        ctx2 = ctx1.with_type("FIRST_SEEN")

        assert ctx2.observed_at == 1704067200000
        assert ctx2.sentiment_score == 0.8
        assert ctx2.location_name == "Kitchen"


class TestWithProvenance:
    """Tests for with_provenance() immutable update."""

    def test_updates_source_event_id(self) -> None:
        """with_provenance updates source_event_id."""
        ctx1 = ObservationContext.from_timestamp(1704067200000)
        ctx2 = ctx1.with_provenance(source_event_id="evt_new")

        assert ctx1.source_event_id is None
        assert ctx2.source_event_id == "evt_new"

    def test_updates_cycle_id(self) -> None:
        """with_provenance updates consolidation_cycle_id."""
        ctx1 = ObservationContext.from_timestamp(1704067200000)
        ctx2 = ctx1.with_provenance(cycle_id="cycle_001")

        assert ctx1.consolidation_cycle_id is None
        assert ctx2.consolidation_cycle_id == "cycle_001"

    def test_updates_both(self) -> None:
        """with_provenance can update both fields."""
        ctx1 = ObservationContext.from_timestamp(1704067200000)
        ctx2 = ctx1.with_provenance(source_event_id="evt_new", cycle_id="cycle_001")

        assert ctx2.source_event_id == "evt_new"
        assert ctx2.consolidation_cycle_id == "cycle_001"


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_zero_timestamp(self) -> None:
        """Handles zero timestamp."""
        ctx = ObservationContext.from_timestamp(0)
        assert ctx.observed_at == 0

    def test_large_timestamp(self) -> None:
        """Handles large timestamp (year 3000)."""
        future_ts = 32503680000000  # Year 3000
        ctx = ObservationContext.from_timestamp(future_ts)
        assert ctx.observed_at == future_ts

    def test_negative_sentiment_score(self) -> None:
        """Handles negative sentiment score."""
        ctx = ObservationContext(observed_at=1704067200000, sentiment_score=-0.5)
        assert ctx.sentiment_score == -0.5

    def test_unicode_location_name(self) -> None:
        """Handles unicode in location name."""
        ctx = ObservationContext(
            observed_at=1704067200000,
            location_name="東京 カフェ ☕",
        )
        assert ctx.location_name == "東京 カフェ ☕"

    def test_empty_string_fields(self) -> None:
        """Empty strings are preserved (not converted to None)."""
        ctx = ObservationContext(
            observed_at=1704067200000,
            location_name="",
            social_context="",
        )
        assert ctx.location_name == ""
        assert ctx.social_context == ""
        # Empty strings should appear in to_dict (not None)
        d = ctx.to_dict()
        assert d["location_name"] == ""
