"""
Epic 1.3 (GAP-002) -- Race Condition Fix: Temporal/Spatial in TurnCompletePayload

Tests that MW context assembly reads temporal/spatial from TurnCompletePayload
FIRST (race-free source), falling back to SessionState beliefs_active ONLY when
payload fields are empty.

Race condition T7: Concierge calls beliefs_active.start_new_turn() which clears
_mentioned_time and _mentioned_location. If MW reads beliefs_active AFTER this
clear (but before the next turn populates new values), temporal/spatial is lost.

The fix: TurnCompletePayload carries temporal/spatial snapshotted BEFORE
start_new_turn(). MW reads from payload first.

Test coverage:
  - Payload has temporal, SessionState cleared -> MW gets temporal from payload
  - Payload empty, SessionState has temporal -> MW gets temporal from SessionState
  - Both have temporal -> payload wins (more reliable)
  - Same pattern for spatial (mentioned_location)
  - ExtractionContext carries 8 new fields
  - assemble_temporal_spatial returns correct dict
"""

import pytest

from k1.memory_writer.context_assembly import (
    assemble_temporal_spatial,
    resolve_mentioned_location,
    resolve_mentioned_time,
)
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.types import ExtractionContext

# ============================================================================
# Helpers
# ============================================================================


def _payload(**overrides) -> TurnCompletePayload:
    """Build a TurnCompletePayload with defaults."""
    defaults = {
        "turn_id": "turn-001",
        "session_id": "sess-001",
        "cognitive_trace_id": "ct-001",
        "user_message": "We went to Olive Garden yesterday evening",
        "assistant_response": "That sounds nice!",
        "timestamp_ms": 1704067200000,
        "turn_number": 1,
    }
    defaults.update(overrides)
    return TurnCompletePayload(**defaults)


def _beliefs_with_temporal() -> dict:
    """Simulate a beliefs_active snapshot WITH mentioned_time."""
    return {
        "mentioned_time": {
            "raw_text": "yesterday evening",
            "resolved_ms": 1703980800000,
            "confidence": 0.85,
            "is_relative": True,
        },
    }


def _beliefs_with_location() -> dict:
    """Simulate a beliefs_active snapshot WITH mentioned_location."""
    return {
        "mentioned_location": {
            "raw_text": "Olive Garden",
            "location_type": "restaurant",
            "entity_id": "ent-olive-garden",
            "confidence": 0.92,
        },
    }


def _beliefs_with_both() -> dict:
    """Simulate a beliefs_active snapshot WITH both temporal and spatial."""
    return {**_beliefs_with_temporal(), **_beliefs_with_location()}


def _beliefs_cleared() -> dict:
    """Simulate beliefs_active AFTER start_new_turn() cleared everything."""
    return {
        "mentioned_time": None,
        "mentioned_location": None,
    }


# ============================================================================
# resolve_mentioned_time: payload-first pattern
# ============================================================================


class TestResolveMentionedTime:
    """Temporal resolution: payload > SessionState > empty."""

    def test_payload_wins_over_cleared_session(self):
        """RACE CONDITION T7: payload has temporal, SessionState cleared."""
        p = _payload(
            mentioned_time_raw="yesterday evening",
            mentioned_time_resolved_ms=1703980800000,
            mentioned_time_confidence=0.9,
            mentioned_time_is_relative=True,
        )
        raw, resolved_ms, confidence, is_relative = resolve_mentioned_time(
            p, beliefs_snapshot=_beliefs_cleared()
        )

        assert raw == "yesterday evening"
        assert resolved_ms == 1703980800000
        assert confidence == 0.9
        assert is_relative is True

    def test_payload_wins_over_session_with_data(self):
        """Both have data -> payload wins (more reliable source)."""
        p = _payload(
            mentioned_time_raw="last Tuesday",
            mentioned_time_resolved_ms=1703635200000,
            mentioned_time_confidence=0.95,
            mentioned_time_is_relative=True,
        )
        raw, resolved_ms, confidence, _ = resolve_mentioned_time(
            p, beliefs_snapshot=_beliefs_with_temporal()
        )

        assert raw == "last Tuesday"  # Payload value, not SessionState
        assert resolved_ms == 1703635200000

    def test_session_fallback_when_payload_empty(self):
        """Payload empty -> falls back to SessionState."""
        p = _payload()  # No temporal fields set (defaults to empty)
        raw, resolved_ms, confidence, is_relative = resolve_mentioned_time(
            p, beliefs_snapshot=_beliefs_with_temporal()
        )

        assert raw == "yesterday evening"
        assert resolved_ms == 1703980800000
        assert confidence == 0.85
        assert is_relative is True

    def test_no_temporal_anywhere(self):
        """Neither payload nor SessionState has temporal -> empty defaults."""
        p = _payload()
        raw, resolved_ms, confidence, is_relative = resolve_mentioned_time(
            p, beliefs_snapshot=_beliefs_cleared()
        )

        assert raw == ""
        assert resolved_ms == 0
        assert confidence == 0.0
        assert is_relative is True

    def test_no_session_snapshot(self):
        """No SessionState snapshot at all -> only payload matters."""
        p = _payload(mentioned_time_raw="tomorrow")
        raw, _, _, _ = resolve_mentioned_time(p, beliefs_snapshot=None)

        assert raw == "tomorrow"

    def test_empty_payload_no_session(self):
        """Empty payload, no session -> all defaults."""
        p = _payload()
        raw, resolved_ms, confidence, is_relative = resolve_mentioned_time(p, beliefs_snapshot=None)

        assert raw == ""
        assert resolved_ms == 0


# ============================================================================
# resolve_mentioned_location: payload-first pattern
# ============================================================================


class TestResolveMentionedLocation:
    """Spatial resolution: payload > SessionState > empty."""

    def test_payload_wins_over_cleared_session(self):
        """RACE CONDITION T7: payload has location, SessionState cleared."""
        p = _payload(
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="restaurant",
            mentioned_location_entity_id="ent-og",
            mentioned_location_confidence=0.88,
        )
        raw, loc_type, entity_id, confidence = resolve_mentioned_location(
            p, beliefs_snapshot=_beliefs_cleared()
        )

        assert raw == "Olive Garden"
        assert loc_type == "restaurant"
        assert entity_id == "ent-og"
        assert confidence == 0.88

    def test_payload_wins_over_session_with_data(self):
        """Both have data -> payload wins."""
        p = _payload(
            mentioned_location_raw="Central Park",
            mentioned_location_type="park",
            mentioned_location_entity_id="ent-cp",
            mentioned_location_confidence=0.95,
        )
        raw, loc_type, _, _ = resolve_mentioned_location(
            p, beliefs_snapshot=_beliefs_with_location()
        )

        assert raw == "Central Park"
        assert loc_type == "park"

    def test_session_fallback_when_payload_empty(self):
        """Payload empty -> falls back to SessionState."""
        p = _payload()
        raw, loc_type, entity_id, confidence = resolve_mentioned_location(
            p, beliefs_snapshot=_beliefs_with_location()
        )

        assert raw == "Olive Garden"
        assert loc_type == "restaurant"
        assert entity_id == "ent-olive-garden"
        assert confidence == 0.92

    def test_no_location_anywhere(self):
        """Neither payload nor SessionState has location -> empty defaults."""
        p = _payload()
        raw, loc_type, entity_id, confidence = resolve_mentioned_location(
            p, beliefs_snapshot=_beliefs_cleared()
        )

        assert raw == ""
        assert loc_type == ""
        assert entity_id == ""
        assert confidence == 0.0


# ============================================================================
# assemble_temporal_spatial: combined assembly
# ============================================================================


class TestAssembleTemporalSpatial:
    """Combined temporal + spatial assembly for ExtractionContext."""

    def test_returns_9_keys(self):
        """assemble_temporal_spatial returns dict with exactly 10 keys (8 + place_id + turn_timestamp_ms)."""
        p = _payload()
        result = assemble_temporal_spatial(p)

        assert len(result) == 10
        assert "turn_timestamp_ms" in result
        assert "mentioned_time_raw" in result
        assert "mentioned_time_resolved_ms" in result
        assert "mentioned_time_confidence" in result
        assert "mentioned_time_is_relative" in result
        assert "mentioned_location_raw" in result
        assert "mentioned_location_type" in result
        assert "mentioned_location_entity_id" in result
        assert "mentioned_location_confidence" in result
        assert "place_id" in result

    def test_full_payload_assembly(self):
        """Full payload with both temporal and spatial."""
        p = _payload(
            mentioned_time_raw="yesterday",
            mentioned_time_resolved_ms=1703980800000,
            mentioned_time_confidence=0.9,
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="restaurant",
            mentioned_location_confidence=0.88,
        )
        result = assemble_temporal_spatial(p)

        assert result["mentioned_time_raw"] == "yesterday"
        assert result["mentioned_location_raw"] == "Olive Garden"

    def test_mixed_sources(self):
        """Temporal from payload, spatial from SessionState."""
        p = _payload(
            mentioned_time_raw="last Friday",
            mentioned_time_resolved_ms=1703721600000,
            mentioned_time_confidence=0.85,
        )
        beliefs = _beliefs_with_location()
        result = assemble_temporal_spatial(p, beliefs_snapshot=beliefs)

        assert result["mentioned_time_raw"] == "last Friday"  # From payload
        assert result["mentioned_location_raw"] == "Olive Garden"  # From SessionState

    def test_can_unpack_into_extraction_context(self):
        """assemble_temporal_spatial output can be unpacked into ExtractionContext."""
        p = _payload(
            mentioned_time_raw="tomorrow morning",
            mentioned_time_resolved_ms=1704153600000,
            mentioned_time_confidence=0.92,
            mentioned_time_is_relative=True,
            mentioned_location_raw="the park",
            mentioned_location_type="park",
            mentioned_location_entity_id="ent-park",
            mentioned_location_confidence=0.75,
        )
        fields = assemble_temporal_spatial(p)
        ctx = ExtractionContext(**fields)

        assert ctx.mentioned_time_raw == "tomorrow morning"
        assert ctx.mentioned_time_resolved_ms == 1704153600000
        assert ctx.mentioned_time_confidence == 0.92
        assert ctx.mentioned_time_is_relative is True
        assert ctx.mentioned_location_raw == "the park"
        assert ctx.mentioned_location_type == "park"
        assert ctx.mentioned_location_entity_id == "ent-park"
        assert ctx.mentioned_location_confidence == 0.75
        assert ctx.place_id is None  # No entities in beliefs -> no place_id


# ============================================================================
# ExtractionContext: new fields
# ============================================================================


class TestExtractionContextTemporalSpatial:
    """Verify ExtractionContext has the 8 new temporal/spatial fields."""

    def test_default_values(self):
        """All 9 fields default to empty/zero/None."""
        ctx = ExtractionContext()

        assert ctx.mentioned_time_raw == ""
        assert ctx.mentioned_time_resolved_ms == 0
        assert ctx.mentioned_time_confidence == 0.0
        assert ctx.mentioned_time_is_relative is True
        assert ctx.mentioned_location_raw == ""
        assert ctx.mentioned_location_type == ""
        assert ctx.mentioned_location_entity_id == ""
        assert ctx.mentioned_location_confidence == 0.0
        assert ctx.place_id is None

    def test_frozen_rejects_mutation(self):
        """ExtractionContext is frozen -- no mutations allowed."""
        ctx = ExtractionContext(mentioned_time_raw="yesterday")
        with pytest.raises(AttributeError):
            ctx.mentioned_time_raw = "today"

    def test_coexists_with_turn_timestamp(self):
        """New fields coexist with turn_timestamp_ms from Epic 1.1."""
        ctx = ExtractionContext(
            turn_timestamp_ms=1704067200000,
            mentioned_time_raw="yesterday evening",
            mentioned_time_resolved_ms=1703980800000,
            mentioned_location_raw="Olive Garden",
        )

        assert ctx.turn_timestamp_ms == 1704067200000
        assert ctx.mentioned_time_raw == "yesterday evening"
        assert ctx.mentioned_location_raw == "Olive Garden"


# ============================================================================
# Race Condition Simulation
# ============================================================================


class TestRaceConditionSimulation:
    """Simulate the T7 race condition and verify the fix.

    Sequence:
    1. User says "We went to Olive Garden yesterday"
    2. Concierge populates beliefs_active.mentioned_time + mentioned_location
    3. Concierge snapshots into TurnCompletePayload
    4. Concierge calls start_new_turn() -> clears beliefs_active
    5. MW receives TurnCompletePayload
    6. MW calls resolve_mentioned_time/location
    7. MW should get temporal/spatial from PAYLOAD, not empty SessionState
    """

    def test_fast_typing_race(self):
        """Simulate fast typing: start_new_turn() fires before MW reads.

        Even though SessionState is cleared, MW gets data from payload.
        """
        # Step 3: Concierge snapshots into payload BEFORE clearing
        p = _payload(
            mentioned_time_raw="yesterday evening",
            mentioned_time_resolved_ms=1703980800000,
            mentioned_time_confidence=0.9,
            mentioned_time_is_relative=True,
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="restaurant",
            mentioned_location_entity_id="ent-og",
            mentioned_location_confidence=0.88,
        )

        # Step 4: start_new_turn() clears SessionState
        beliefs_after_clear = _beliefs_cleared()

        # Step 6: MW resolves -- should get data from payload
        time_raw, time_ms, time_conf, _ = resolve_mentioned_time(
            p, beliefs_snapshot=beliefs_after_clear
        )
        loc_raw, loc_type, loc_eid, loc_conf = resolve_mentioned_location(
            p, beliefs_snapshot=beliefs_after_clear
        )

        # Step 7: Temporal survived the race
        assert time_raw == "yesterday evening"
        assert time_ms == 1703980800000
        assert time_conf == 0.9

        # Spatial survived the race
        assert loc_raw == "Olive Garden"
        assert loc_type == "restaurant"
        assert loc_eid == "ent-og"

    def test_pre_epic11_payload_uses_session(self):
        """Pre-Epic-1.1 payload (no temporal/spatial fields) -> SessionState fallback.

        Old payloads have empty defaults. If SessionState hasn't been cleared yet,
        MW can still read from it.
        """
        p = _payload()  # No temporal/spatial (pre-Epic-1.1)
        beliefs = _beliefs_with_both()

        time_raw, _, _, _ = resolve_mentioned_time(p, beliefs_snapshot=beliefs)
        loc_raw, _, _, _ = resolve_mentioned_location(p, beliefs_snapshot=beliefs)

        assert time_raw == "yesterday evening"
        assert loc_raw == "Olive Garden"

    def test_end_to_end_extraction_context(self):
        """Full E2E: payload -> assemble -> ExtractionContext with temporal/spatial."""
        p = _payload(
            mentioned_time_raw="last Tuesday",
            mentioned_time_resolved_ms=1703635200000,
            mentioned_time_confidence=0.87,
            mentioned_time_is_relative=True,
            mentioned_location_raw="Central Park",
            mentioned_location_type="park",
            mentioned_location_confidence=0.91,
        )

        fields = assemble_temporal_spatial(p, beliefs_snapshot=_beliefs_cleared())
        ctx = ExtractionContext(
            session_id=p.session_id,
            conversation_turn=p.turn_number,
            **fields,
        )

        assert ctx.turn_timestamp_ms == 1704067200000
        assert ctx.mentioned_time_raw == "last Tuesday"
        assert ctx.mentioned_time_resolved_ms == 1703635200000
        assert ctx.mentioned_location_raw == "Central Park"
        assert ctx.mentioned_location_type == "park"
