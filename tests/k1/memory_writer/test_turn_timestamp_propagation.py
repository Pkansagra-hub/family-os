"""
Epic 1.1: K1 Turn Timestamp Propagation -- Test Suite
======================================================

Tests for GAP-002 Epic 1.1 changes:
  - Issue 1.1.1: turn_timestamp_ms on ExtractionContext
  - Issue 1.1.3: conversation_anchor_ms on MemoryAtom
  - Issue 1.1.4: MentionedTime/MentionedLocation on TurnCompletePayload

VALIDATES:
- k1/memory_writer/types.py (ExtractionContext, MemoryAtom)
- k1/memory_writer/events.py (TurnCompletePayload)
- k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json

COVERAGE REQUIREMENTS:
- Field existence and defaults
- Frozen immutability enforcement
- Backward compatibility (existing construction unchanged)
- Race condition T7 mitigation (payload carries temporal/spatial)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.types import ExtractionContext, MemoryAtom

# ===========================================================================
# Issue 1.1.1 -- ExtractionContext.turn_timestamp_ms
# ===========================================================================


class TestExtractionContextTurnTimestamp:
    """Verify turn_timestamp_ms on ExtractionContext (Issue 1.1.1)."""

    def test_field_exists_with_value(self):
        ctx = ExtractionContext(turn_timestamp_ms=1700000000000)
        assert ctx.turn_timestamp_ms == 1700000000000

    def test_default_is_zero(self):
        ctx = ExtractionContext()
        assert ctx.turn_timestamp_ms == 0

    def test_frozen_rejects_mutation(self):
        ctx = ExtractionContext(turn_timestamp_ms=1700000000000)
        with pytest.raises(AttributeError):
            ctx.turn_timestamp_ms = 9999

    def test_backward_compat_existing_fields_unchanged(self):
        ctx = ExtractionContext(
            session_id="s1",
            conversation_turn=5,
        )
        assert ctx.session_id == "s1"
        assert ctx.conversation_turn == 5
        assert ctx.turn_timestamp_ms == 0


# ===========================================================================
# Issue 1.1.3 -- MemoryAtom.conversation_anchor_ms
# ===========================================================================


class TestMemoryAtomConversationAnchor:
    """Verify conversation_anchor_ms on MemoryAtom (Issue 1.1.3)."""

    def test_field_exists_with_value(self):
        atom = MemoryAtom(conversation_anchor_ms=1700000000000)
        assert atom.conversation_anchor_ms == 1700000000000

    def test_default_is_zero(self):
        atom = MemoryAtom()
        assert atom.conversation_anchor_ms == 0

    def test_frozen_rejects_mutation(self):
        atom = MemoryAtom(conversation_anchor_ms=1700000000000)
        with pytest.raises(AttributeError):
            atom.conversation_anchor_ms = 9999

    def test_backward_compat_existing_fields_unchanged(self):
        atom = MemoryAtom(
            text="Had dinner with Mom",
            session_id="s1",
            conversation_turn=3,
            confidence=0.85,
        )
        assert atom.text == "Had dinner with Mom"
        assert atom.session_id == "s1"
        assert atom.conversation_turn == 3
        assert atom.confidence == 0.85
        assert atom.conversation_anchor_ms == 0

    def test_coexists_with_temporal(self):
        from k1.memory_writer.types import Temporal

        atom = MemoryAtom(
            conversation_anchor_ms=1700000000000,
            temporal=Temporal(
                mentioned_time="yesterday evening",
                resolved_epoch_ms=1699920000000,
                is_backdated=True,
            ),
        )
        assert atom.conversation_anchor_ms == 1700000000000
        assert atom.temporal.resolved_epoch_ms == 1699920000000


# ===========================================================================
# Issue 1.1.4 -- TurnCompletePayload temporal/spatial fields
# ===========================================================================


class TestTurnCompletePayloadTemporalSpatial:
    """Verify TurnCompletePayload carries temporal/spatial context (Issue 1.1.4)."""

    def _make_base_payload(self, **overrides):
        defaults = dict(
            turn_id="t1",
            session_id="s1",
            cognitive_trace_id="ct1",
            user_message="Had dinner yesterday",
            assistant_response="That sounds nice!",
            timestamp_ms=1700000000000,
            turn_number=1,
        )
        defaults.update(overrides)
        return TurnCompletePayload(**defaults)

    def test_mentioned_time_fields(self):
        payload = self._make_base_payload(
            mentioned_time_raw="yesterday evening",
            mentioned_time_resolved_ms=1699920000000,
            mentioned_time_confidence=0.9,
            mentioned_time_is_relative=True,
        )
        assert payload.mentioned_time_raw == "yesterday evening"
        assert payload.mentioned_time_resolved_ms == 1699920000000
        assert payload.mentioned_time_confidence == 0.9
        assert payload.mentioned_time_is_relative is True

    def test_mentioned_location_fields(self):
        payload = self._make_base_payload(
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="restaurant",
            mentioned_location_entity_id="ent_123",
            mentioned_location_confidence=0.95,
        )
        assert payload.mentioned_location_raw == "Olive Garden"
        assert payload.mentioned_location_type == "restaurant"
        assert payload.mentioned_location_entity_id == "ent_123"
        assert payload.mentioned_location_confidence == 0.95

    def test_defaults_empty_when_no_temporal_spatial(self):
        payload = self._make_base_payload()
        assert payload.mentioned_time_raw == ""
        assert payload.mentioned_time_resolved_ms == 0
        assert payload.mentioned_time_confidence == 0.0
        assert payload.mentioned_time_is_relative is True
        assert payload.mentioned_location_raw == ""
        assert payload.mentioned_location_type == ""
        assert payload.mentioned_location_entity_id == ""
        assert payload.mentioned_location_confidence == 0.0

    def test_backward_compat_original_seven_fields(self):
        payload = self._make_base_payload()
        assert payload.turn_id == "t1"
        assert payload.session_id == "s1"
        assert payload.cognitive_trace_id == "ct1"
        assert payload.user_message == "Had dinner yesterday"
        assert payload.assistant_response == "That sounds nice!"
        assert payload.timestamp_ms == 1700000000000
        assert payload.turn_number == 1

    def test_frozen_rejects_mutation(self):
        payload = self._make_base_payload(mentioned_time_raw="yesterday")
        with pytest.raises(AttributeError):
            payload.mentioned_time_raw = "today"

    def test_race_condition_t7_payload_carries_data(self):
        """Simulate T7: Concierge snapshots temporal/spatial BEFORE start_new_turn()."""
        payload = self._make_base_payload(
            mentioned_time_raw="yesterday evening",
            mentioned_time_resolved_ms=1699920000000,
            mentioned_time_confidence=0.9,
            mentioned_location_raw="Olive Garden",
            mentioned_location_type="restaurant",
        )
        # Even if beliefs_active.start_new_turn() clears _mentioned_time/_mentioned_location,
        # the payload still carries the data -- MW reads from payload first.
        assert payload.mentioned_time_raw == "yesterday evening"
        assert payload.mentioned_location_raw == "Olive Garden"


# ===========================================================================
# Issue 1.1.3 -- JSON Schema validation
# ===========================================================================


class TestMemoryAtomSchemaConversationAnchor:
    """Verify conversation_anchor_ms in memory_atom.v2.schema.json."""

    @pytest.fixture()
    def schema(self):
        schema_path = (
            Path(__file__).resolve().parents[3]
            / "k1"
            / "contracts"
            / "schemas"
            / "memory_writer"
            / "memory_atom.v2.schema.json"
        )
        with open(schema_path) as f:
            return json.load(f)

    def test_conversation_anchor_ms_in_properties(self, schema):
        assert "conversation_anchor_ms" in schema["properties"]

    def test_conversation_anchor_ms_type_is_integer(self, schema):
        prop = schema["properties"]["conversation_anchor_ms"]
        assert prop["type"] == "integer"

    def test_conversation_anchor_ms_not_required(self, schema):
        assert "conversation_anchor_ms" not in schema["required"]

    def test_conversation_anchor_ms_has_default_zero(self, schema):
        prop = schema["properties"]["conversation_anchor_ms"]
        assert prop["default"] == 0


# ===========================================================================
# M1-TIME-01 -- assemble_temporal_spatial propagates turn_timestamp_ms
# ===========================================================================


class TestAssembleTemporalSpatialTurnTimestamp:
    """Verify assemble_temporal_spatial includes turn_timestamp_ms from payload."""

    def _make_payload(self, **overrides):
        defaults = dict(
            turn_id="t1",
            session_id="s1",
            cognitive_trace_id="ct1",
            user_message="Had dinner yesterday",
            assistant_response="That sounds nice!",
            timestamp_ms=1700000000000,
            turn_number=1,
        )
        defaults.update(overrides)
        return TurnCompletePayload(**defaults)

    def test_turn_timestamp_ms_propagated(self):
        """assemble_temporal_spatial must include turn_timestamp_ms from payload.timestamp_ms."""
        from k1.memory_writer.context_assembly import assemble_temporal_spatial

        payload = self._make_payload(timestamp_ms=1700000000000)
        result = assemble_temporal_spatial(payload)
        assert result["turn_timestamp_ms"] == 1700000000000

    def test_turn_timestamp_ms_zero_when_payload_zero(self):
        """turn_timestamp_ms should be 0 when payload.timestamp_ms is 0."""
        from k1.memory_writer.context_assembly import assemble_temporal_spatial

        payload = self._make_payload(timestamp_ms=0)
        result = assemble_temporal_spatial(payload)
        assert result["turn_timestamp_ms"] == 0

    def test_result_has_ten_keys(self):
        """assemble_temporal_spatial must return exactly 10 keys (9 spatial/temporal + turn_timestamp_ms)."""
        from k1.memory_writer.context_assembly import assemble_temporal_spatial

        payload = self._make_payload()
        result = assemble_temporal_spatial(payload)
        assert len(result) == 10
        assert "turn_timestamp_ms" in result
