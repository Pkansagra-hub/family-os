"""Tests for EnvelopeBuilder (E-MW-3.1).

14 tests in 3 classes covering:
  - Build: single/multi/empty atom → envelope dicts, topic, schema_uri, trace_id
  - Headers: cognitive_trace_id, tenant_id, band, schema_version, MW-10
  - Integration: all required fields, derived fields, JSON serializable
"""

from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.envelope.envelope_builder import EnvelopeBuilder
from k1.memory_writer.envelope.field_mapper import FieldMapper
from k1.memory_writer.invariants import InvariantViolation
from k1.memory_writer.place_resolver import PlaceResolver
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ExtractionContext,
    LocationType,
    MemoryAtom,
    SentimentLabel,
    SourceType,
    TemporalOrientation,
)

# ===========================================================================
# Helpers
# ===========================================================================


class StubPlaceResolver(PlaceResolver):
    """PlaceResolver that returns canned results."""

    def __init__(self) -> None:
        object.__init__(self)

    def resolve_with_geohash(
        self,
        name: Optional[str],
        known_geohashes: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        if not name:
            return (None, None)
        return ("place_test", "9q8yyz")


def _make_builder(config: Optional[MWConfig] = None) -> EnvelopeBuilder:
    cfg = config or MWConfig()
    resolver = StubPlaceResolver()
    mapper = FieldMapper(place_resolver=resolver, config=cfg)
    return EnvelopeBuilder(field_mapper=mapper)


def _default_ctx(**overrides) -> ExtractionContext:
    defaults = dict(
        session_id="sess-001",
        conversation_turn=5,
        turn_timestamp_ms=1_700_000_000_000,
        control_context={
            "safety_band": "GREEN",
            "tenant_id": "tenant-abc",
            "space_id": "space-xyz",
            "user_id": "user-123",
            "device_id": "device-456",
        },
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
        emotion_tags=["contentment"],
        affect=Affect(valence=0.6, arousal=0.3, dominance=0.5),
        temporal_orientation=TemporalOrientation.PAST,
        source_type=SourceType.USER_STATED,
        confidence=0.95,
        session_id="sess-001",
        conversation_turn=5,
        language="en",
        conversation_anchor_ms=1_700_000_000_000,
    )
    defaults.update(overrides)
    return MemoryAtom(**defaults)


# ===========================================================================
# TestEnvelopeBuilderBuild — 6 tests
# ===========================================================================


class TestEnvelopeBuilderBuild:
    """Envelope construction from atom list."""

    def test_single_atom_produces_one_envelope(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        assert len(envelopes) == 1

    def test_multi_atom_produces_multiple_envelopes(self):
        builder = _make_builder()
        atoms = [
            _default_atom(),
            _default_atom(text="Dentist tomorrow"),
            _default_atom(text="Dad promoted"),
        ]
        envelopes = builder.build(atoms, _default_ctx(), "trace-1")
        assert len(envelopes) == 3

    def test_empty_atoms_produces_empty(self):
        builder = _make_builder()
        envelopes = builder.build([], _default_ctx(), "trace-1")
        assert envelopes == []

    def test_envelope_has_topic(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        assert envelopes[0]["topic"] == "memory.delta"

    def test_envelope_has_schema_uri(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        assert envelopes[0]["schema_uri"] == "schema://memory.delta"

    def test_envelope_has_trace_id(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-xyz")
        assert envelopes[0]["trace_id"] == "trace-xyz"


# ===========================================================================
# TestEnvelopeBuilderHeaders — 5 tests
# ===========================================================================


class TestEnvelopeBuilderHeaders:
    """MW-side headers injected from ExtractionContext."""

    def test_headers_include_cognitive_trace_id(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-abc")
        headers = envelopes[0]["headers"]
        assert headers["cognitive_trace_id"] == "trace-abc"

    def test_headers_include_tenant_id(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        headers = envelopes[0]["headers"]
        assert headers["tenant_id"] == "tenant-abc"

    def test_headers_include_band(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        headers = envelopes[0]["headers"]
        assert headers["band"] == "GREEN"

    def test_headers_schema_version(self):
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        headers = envelopes[0]["headers"]
        assert headers["schema_version"] == "1.0"

    def test_mw10_missing_trace_id_raises(self):
        builder = _make_builder()
        with pytest.raises(InvariantViolation, match="MW-10"):
            builder.build([_default_atom()], _default_ctx(), "")


# ===========================================================================
# TestEnvelopeBuilderIntegration — 3 tests
# ===========================================================================


class TestEnvelopeBuilderIntegration:
    """Integration: body fields, derived fields, JSON serialization."""

    def test_body_has_all_required_fields(self):
        """Body contains all 14 required K0 fields."""
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        body = envelopes[0]["body"]

        required = [
            "text",
            "operation",
            "topics",
            "sentiment_label",
            "affect",
            "source_type",
            "novelty",
            "elaboration_depth",
            "temporal_orientation",
            "confidence",
            "session_id",
            "conversation_turn",
            "language",
            "cognitive_trace_id",
        ]
        for key in required:
            assert key in body, f"Missing required field: {key}"

    def test_body_has_derived_fields(self):
        """Body contains K0 gap-fix derived fields."""
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        body = envelopes[0]["body"]

        assert "sentiment_score" in body
        assert "dominant_emotion" in body
        assert "affect_valence" in body
        assert "num_participants" in body
        assert "geohash_6" in body

    def test_body_serializable_as_json(self):
        """json.dumps(body) succeeds — no frozen dataclasses leak."""
        builder = _make_builder()
        envelopes = builder.build([_default_atom()], _default_ctx(), "trace-1")
        body = envelopes[0]["body"]

        serialized = json.dumps(body)
        assert isinstance(serialized, str)
        # Round-trip
        parsed = json.loads(serialized)
        assert parsed["text"] == "Had dinner with Mom at Olive Garden"
