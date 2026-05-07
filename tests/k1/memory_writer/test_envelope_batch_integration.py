"""Tests for Phase 3 full pipeline integration (E-MW-3.4).

18 tests in 4 classes covering:
  - Full pipeline GREEN band: atom→FieldMapper→EnvelopeBuilder→PrivacyEnforcer→DeltaAggregator→BatchEmitter→FakeBridge
  - Privacy bands end-to-end: AMBER, RED, unknown
  - Batching: dedup, causal ordering, flush-reuse, empty, config
  - Error recovery: bridge error, MW-10 violation, null fields, place resolver miss
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

import pytest

from k1.memory_writer.batch.batch_emitter import BatchEmitter
from k1.memory_writer.batch.delta_aggregator import DeltaAggregator
from k1.memory_writer.config import MWConfig
from k1.memory_writer.envelope.envelope_builder import EnvelopeBuilder
from k1.memory_writer.envelope.field_mapper import FieldMapper
from k1.memory_writer.envelope.privacy_enforcer import PrivacyEnforcer
from k1.memory_writer.invariants import InvariantViolation
from k1.memory_writer.place_resolver import PlaceResolver
from k1.memory_writer.types import (
    ActivityType,
    Affect,
    ElaborationDepth,
    ExtractionContext,
    LocationType,
    MemoryAtom,
    NoveltyLevel,
    SentimentLabel,
    SourceType,
    TemporalOrientation,
)

# ===========================================================================
# Test adapters
# ===========================================================================


class StubPlaceResolver(PlaceResolver):
    """PlaceResolver that returns canned results without entity lookup."""

    def __init__(
        self,
        place_id: Optional[str] = None,
        geohash: Optional[str] = None,
    ) -> None:
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


class FakeBridgePort:
    """Fake IBridgeCommandPort that captures submit_batch calls."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._calls: list[list[dict]] = []
        self._raises = raises

    async def submit(self, topic: str, schema_uri: str, body: Dict) -> None:
        pass  # pragma: no cover

    async def submit_batch(self, envelopes: List[Dict]) -> None:
        if self._raises:
            raise self._raises
        self._calls.append(list(envelopes))

    @property
    def calls(self) -> list[list[dict]]:
        return self._calls


# ===========================================================================
# Helpers
# ===========================================================================


def _cfg() -> MWConfig:
    return MWConfig(batch_window_ms=250, max_batch_size=10)


def _default_ctx(band: str = "GREEN") -> ExtractionContext:
    return ExtractionContext(
        session_id="sess-001",
        conversation_turn=5,
        turn_timestamp_ms=1_700_000_000_000,
        control_context={
            "safety_band": band,
            "tenant_id": "t1",
            "space_id": "s1",
        },
    )


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


def _build_pipeline(
    bridge: FakeBridgePort | None = None,
    place_id: str | None = "place_olive_garden",
    geohash: str | None = "9q8yyz",
) -> tuple[EnvelopeBuilder, PrivacyEnforcer, DeltaAggregator, BatchEmitter, FakeBridgePort]:
    """Assemble the full Phase 3 pipeline."""
    resolver = StubPlaceResolver(place_id=place_id, geohash=geohash)
    config = _cfg()
    mapper = FieldMapper(place_resolver=resolver, config=config)
    builder = EnvelopeBuilder(field_mapper=mapper)
    enforcer = PrivacyEnforcer()
    aggregator = DeltaAggregator(config=config)
    port = bridge or FakeBridgePort()
    emitter = BatchEmitter(bridge_port=port)
    return builder, enforcer, aggregator, emitter, port


def _run_pipeline(
    atoms: list[MemoryAtom],
    band: str = "GREEN",
    bridge: FakeBridgePort | None = None,
    place_id: str | None = "place_olive_garden",
    geohash: str | None = "9q8yyz",
) -> tuple[list[dict], FakeBridgePort]:
    """Run atoms through the full pipeline synchronously (except emit)."""
    builder, enforcer, aggregator, emitter, port = _build_pipeline(
        bridge=bridge, place_id=place_id, geohash=geohash
    )
    ctx = _default_ctx(band=band)
    trace_id = "trace-xyz"

    envelopes = builder.build(atoms, ctx, trace_id)

    for env in envelopes:
        enforcer.enforce(env["body"], band)
        aggregator.add(env)

    batch = aggregator.flush()
    return batch, port


# ===========================================================================
# Tests
# ===========================================================================


class TestFullPipelineGreenBand:
    """Full pipeline with GREEN band — no privacy stripping."""

    @pytest.mark.asyncio
    async def test_single_atom_to_bridge(self) -> None:
        batch, port = _run_pipeline([_default_atom()])
        emitter = BatchEmitter(bridge_port=port)
        count = await emitter.emit(batch)
        assert count == 1
        assert len(port.calls) == 1
        assert len(port.calls[0]) == 1

    @pytest.mark.asyncio
    async def test_multi_atom_to_bridge(self) -> None:
        atoms = [
            _default_atom(topics=["a"], participants=["p1"], conversation_turn=1),
            _default_atom(topics=["b"], participants=["p2"], conversation_turn=2),
            _default_atom(topics=["c"], participants=["p3"], conversation_turn=3),
        ]
        batch, port = _run_pipeline(atoms)
        emitter = BatchEmitter(bridge_port=port)
        count = await emitter.emit(batch)
        assert count == 3

    def test_derived_fields_present(self) -> None:
        batch, _ = _run_pipeline([_default_atom()])
        body = batch[0]["body"]
        assert "sentiment_score" in body
        assert "dominant_emotion" in body
        assert "affect_valence" in body
        assert "num_participants" in body

    def test_headers_complete(self) -> None:
        batch, _ = _run_pipeline([_default_atom()])
        headers = batch[0]["headers"]
        assert headers["cognitive_trace_id"] == "trace-xyz"
        assert headers["tenant_id"] == "t1"
        assert headers["band"] == "GREEN"
        assert headers["topic"] == "memory.delta"
        assert headers["schema_uri"] == "schema://memory.delta"

    def test_body_json_serializable(self) -> None:
        batch, _ = _run_pipeline([_default_atom()])
        for env in batch:
            serialized = json.dumps(env["body"])
            assert isinstance(serialized, str)


class TestFullPipelinePrivacyBands:
    """Privacy band enforcement end-to-end."""

    def test_amber_location_generalized(self) -> None:
        batch, _ = _run_pipeline([_default_atom()], band="AMBER")
        body = batch[0]["body"]
        assert body["location_name"] == "Restaurant"

    def test_red_location_stripped(self) -> None:
        batch, _ = _run_pipeline([_default_atom()], band="RED")
        body = batch[0]["body"]
        assert body["location_name"] is None
        assert body["place_id"] is None
        assert body["geohash_6"] is None

    def test_red_participants_masked(self) -> None:
        batch, _ = _run_pipeline([_default_atom()], band="RED")
        body = batch[0]["body"]
        assert body["participants"] == ["person_redacted_0"]

    def test_unknown_band_fails_secure(self) -> None:
        batch, _ = _run_pipeline([_default_atom()], band="INVALID")
        body = batch[0]["body"]
        assert body["location_name"] is None
        assert body["participants"] == ["person_redacted_0"]


class TestFullPipelineBatching:
    """DeltaAggregator batching within the pipeline."""

    def test_dedup_within_batch(self) -> None:
        atoms = [
            _default_atom(participants=["person_mom"], topics=["dinner"]),
            _default_atom(participants=["person_mom"], topics=["dinner"]),
        ]
        batch, _ = _run_pipeline(atoms)
        assert len(batch) == 1

    def test_causal_ordering(self) -> None:
        atoms = [
            _default_atom(
                participants=["a"], topics=["x"], conversation_turn=5, extraction_sequence=1
            ),
            _default_atom(
                participants=["b"], topics=["y"], conversation_turn=3, extraction_sequence=0
            ),
        ]
        batch, _ = _run_pipeline(atoms)
        turns = [e["body"]["conversation_turn"] for e in batch]
        assert turns == [3, 5]

    @pytest.mark.asyncio
    async def test_flush_then_reuse(self) -> None:
        builder, enforcer, aggregator, emitter, port = _build_pipeline()
        ctx = _default_ctx()

        # First batch
        atoms1 = [
            _default_atom(participants=["a"], topics=["x"]),
            _default_atom(participants=["b"], topics=["y"]),
        ]
        envs1 = builder.build(atoms1, ctx, "trace-1")
        for e in envs1:
            enforcer.enforce(e["body"], "GREEN")
            aggregator.add(e)
        batch1 = aggregator.flush()
        await emitter.emit(batch1)

        # Second batch
        atoms2 = [_default_atom(participants=["c"], topics=["z"])]
        envs2 = builder.build(atoms2, ctx, "trace-2")
        for e in envs2:
            enforcer.enforce(e["body"], "GREEN")
            aggregator.add(e)
        batch2 = aggregator.flush()
        await emitter.emit(batch2)

        assert len(port.calls) == 2
        assert len(port.calls[0]) == 2
        assert len(port.calls[1]) == 1

    @pytest.mark.asyncio
    async def test_empty_batch_not_submitted(self) -> None:
        _, _, aggregator, emitter, port = _build_pipeline()
        batch = aggregator.flush()
        count = await emitter.emit(batch)
        assert count == 0
        assert len(port.calls) == 0

    def test_batch_window_config(self) -> None:
        _, _, aggregator, _, _ = _build_pipeline()
        assert aggregator.window_ms == 250


class TestFullPipelineErrorRecovery:
    """Error handling across the pipeline."""

    @pytest.mark.asyncio
    async def test_bridge_error_no_crash(self) -> None:
        port = FakeBridgePort(raises=RuntimeError("offline"))
        batch, _ = _run_pipeline([_default_atom()], bridge=port)
        emitter = BatchEmitter(bridge_port=port)
        count = await emitter.emit(batch)
        assert count == 0

    def test_mw10_missing_trace_id_raises(self) -> None:
        builder, _, _, _, _ = _build_pipeline()
        with pytest.raises(InvariantViolation, match="MW-10"):
            builder.build([_default_atom()], _default_ctx(), "")

    def test_field_mapper_null_atom_fields(self) -> None:
        atom = _default_atom(
            location_name=None,
            location_type=None,
            affect=None,
            emotion_tags=[],
            activity_type=None,
            categories=None,
        )
        batch, _ = _run_pipeline([atom])
        body = batch[0]["body"]
        assert isinstance(body, dict)
        assert body["location_name"] is None
        assert body["activity_type"] is None

    def test_place_resolver_no_match(self) -> None:
        batch, _ = _run_pipeline(
            [_default_atom(location_name="Unknown Place")],
            place_id=None,
            geohash=None,
        )
        body = batch[0]["body"]
        assert body["place_id"] is None
        assert body["geohash_6"] is None
