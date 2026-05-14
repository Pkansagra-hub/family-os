"""Tests for MemoryWriterPipeline (E-MW-4.1).

34 tests in 7 classes covering:
  - Happy path: full pipeline, result fields, trace_id, events, privacy band
  - Filter skip: short-circuit, no context/LLM, error fallthrough
  - Context errors: snapshot fail, build fail
  - Extraction errors: empty, validator drops, no envelope/bridge, partial
  - Circuit breaker: open skip, no LLM, event, closed allows
  - Batch flush: add/flush/emit, flush_pending
  - Observability: all events published, trace_ids, errors, publish failure
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.memory_writer.config import MWConfig
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.pipeline.pipeline import MemoryWriterPipeline
from k1.memory_writer.place_resolver import PlaceResolver
from k1.memory_writer.types import (
    ExtractionContext,
    FilterDecision,
    SkipReason,
    Subscription,
)

# ===========================================================================
# Fakes — duck-typed replacements for real pipeline components
# ===========================================================================


class FakeRelevanceFilter:
    """Returns configurable FilterDecision."""

    def __init__(
        self,
        passed: bool = True,
        skip_reason: Optional[SkipReason] = None,
        raises: Optional[Exception] = None,
    ) -> None:
        self.passed = passed
        self.skip_reason = skip_reason
        self.raises = raises
        self.call_count = 0

    def evaluate(
        self,
        user_message: str = "",
        assistant_response: str = "",
        entities: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        turn_id: str = "",
        timestamp_ms: int = 0,
        turn_metadata: Optional[Dict[str, Any]] = None,
    ) -> FilterDecision:
        self.call_count += 1
        if self.raises:
            raise self.raises
        return FilterDecision(
            passed=self.passed,
            skip_reason=self.skip_reason,
            turn_id=turn_id,
        )


class FakeSessionReader:
    """Returns canned snapshot or raises."""

    def __init__(
        self,
        snapshot: Optional[Dict[str, Any]] = None,
        raises: Optional[Exception] = None,
    ) -> None:
        self.snapshot_data = snapshot or {}
        self.raises = raises
        self.call_count = 0
        self.enriched_call_count = 0
        self.last_enriched_session_id: Optional[str] = None

    async def read_snapshot(self) -> Dict[str, Any]:
        self.call_count += 1
        if self.raises:
            raise self.raises
        return self.snapshot_data

    async def read_snapshot_enriched(
        self,
        session_id: str,
        history_limit: int = 50,
    ) -> Dict[str, Any]:
        self.enriched_call_count += 1
        self.last_enriched_session_id = session_id
        if self.raises:
            raise self.raises
        return self.snapshot_data


class FakeContextBuilder:
    """Returns canned ExtractionContext or raises."""

    def __init__(
        self,
        context: Optional[ExtractionContext] = None,
        raises: Optional[Exception] = None,
    ) -> None:
        self.context = context
        self.raises = raises
        self.call_count = 0

    def build(self, snapshot: Dict[str, Any], payload: TurnCompletePayload) -> ExtractionContext:
        self.call_count += 1
        if self.raises:
            raise self.raises
        return self.context  # type: ignore[return-value]


class FakeWriterAgent:
    """Returns canned RawExtractions or raises."""

    def __init__(
        self,
        extractions: Optional[List[Any]] = None,
        raises: Optional[Exception] = None,
    ) -> None:
        self.extractions = extractions if extractions is not None else []
        self.raises = raises
        self.call_count = 0

    async def extract(self, context: Any, trace_id: str) -> List[Any]:
        self.call_count += 1
        if self.raises:
            raise self.raises
        return self.extractions


class FakeExtractionValidator:
    """Returns canned MemoryAtom list and dropped-confidence count."""

    def __init__(self, atoms: Optional[List[Any]] = None, dropped_confidence: int = 0) -> None:
        self.atoms = atoms if atoms is not None else []
        self.dropped_confidence = dropped_confidence
        self.call_count = 0

    def validate(self, extractions: List[Any], context: Any) -> tuple[List[Any], int]:
        self.call_count += 1
        return self.atoms, self.dropped_confidence


class FakeCircuitBreaker:
    """Controllable circuit breaker."""

    def __init__(self, is_open: bool = False) -> None:
        self.is_open = is_open
        self.successes = 0
        self.failures = 0

    def record_success(self) -> None:
        self.successes += 1

    def record_failure(self) -> None:
        self.failures += 1


class FakeEnvelopeBuilder:
    """Returns canned envelope dicts."""

    def __init__(self, envelopes: Optional[List[dict]] = None) -> None:
        self.envelopes = envelopes if envelopes is not None else []
        self.call_count = 0

    def build(self, atoms: List[Any], context: Any, trace_id: str) -> List[dict]:
        self.call_count += 1
        return list(self.envelopes)


class FakePrivacyEnforcer:
    """Tracks enforce calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, str]] = []

    def enforce(self, body: dict, band: str) -> dict:
        self.calls.append((body, band))
        return body


class FakeDeltaAggregator:
    """Collects adds, returns canned flush."""

    def __init__(self) -> None:
        self.added: list[dict] = []
        self._pending: list[dict] = []

    def add(self, envelope: dict) -> bool:
        self.added.append(envelope)
        self._pending.append(envelope)
        return True

    def flush(self) -> list[dict]:
        batch = list(self._pending)
        self._pending = []
        return batch

    @property
    def pending_count(self) -> int:
        return len(self._pending)


class FakeBatchEmitter:
    """Tracks emit calls, returns count."""

    def __init__(self, returns: int | None = None) -> None:
        self._returns = returns
        self.calls: list[list[dict]] = []

    async def emit(self, batch: list[dict]) -> int:
        self.calls.append(batch)
        if self._returns is not None:
            return self._returns
        return len(batch)


class FakeEventPort:
    """Captures published events."""

    def __init__(self, raises: Optional[Exception] = None) -> None:
        self.published: list[tuple[str, dict]] = []
        self.raises = raises

    async def subscribe(self, topic: str, handler: Any) -> Subscription:
        return Subscription(subscription_id="sub-1", topic=topic)

    async def unsubscribe(self, subscription_id: str) -> None:
        pass

    async def publish(self, topic: str, payload: dict) -> None:
        if self.raises:
            raise self.raises
        self.published.append((topic, payload))


# ===========================================================================
# Helpers
# ===========================================================================


def _payload(
    turn_id: str = "turn-1",
    trace_id: str = "trace-abc",
    user_message: str = "Mom called about dinner",
    **kwargs: Any,
) -> TurnCompletePayload:
    defaults = dict(
        turn_id=turn_id,
        session_id="sess-001",
        cognitive_trace_id=trace_id,
        user_message=user_message,
        assistant_response="That sounds nice!",
        timestamp_ms=1_700_000_000_000,
        turn_number=5,
    )
    defaults.update(kwargs)
    return TurnCompletePayload(**defaults)


def _default_context(band: str = "GREEN") -> ExtractionContext:
    return ExtractionContext(
        session_id="sess-001",
        conversation_turn=5,
        turn_timestamp_ms=1_700_000_000_000,
        control_context={"safety_band": band, "tenant_id": "t1", "space_id": "s1"},
    )


def _envelope(text: str = "test", turn: int = 1, seq: int = 0) -> dict:
    return {
        "topic": "memory.delta",
        "schema_uri": "schema://memory.delta",
        "body": {
            "text": text,
            "participants": ["person_mom"],
            "topics": ["dinner"],
            "conversation_turn": turn,
            "extraction_sequence": seq,
        },
        "trace_id": "trace-abc",
        "headers": {"cognitive_trace_id": "trace-abc", "band": "GREEN"},
    }


def _atom_stub() -> object:
    """Opaque stub — only used as passthrough to FakeEnvelopeBuilder."""
    return object()


def _pipeline(
    filter_passed: bool = True,
    filter_skip_reason: Optional[SkipReason] = None,
    filter_raises: Optional[Exception] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    snapshot_raises: Optional[Exception] = None,
    context: Optional[ExtractionContext] = None,
    context_raises: Optional[Exception] = None,
    raw_extractions: Optional[List[Any]] = None,
    extraction_raises: Optional[Exception] = None,
    validated_atoms: Optional[List[Any]] = None,
    circuit_open: bool = False,
    envelopes: Optional[List[dict]] = None,
    emitter_returns: int | None = None,
    event_raises: Optional[Exception] = None,
) -> tuple[
    MemoryWriterPipeline,
    FakeRelevanceFilter,
    FakeSessionReader,
    FakeContextBuilder,
    FakeWriterAgent,
    FakeExtractionValidator,
    FakeCircuitBreaker,
    FakeEnvelopeBuilder,
    FakePrivacyEnforcer,
    FakeDeltaAggregator,
    FakeBatchEmitter,
    FakeEventPort,
]:
    """Build a pipeline with configurable fakes."""
    f = FakeRelevanceFilter(
        passed=filter_passed,
        skip_reason=filter_skip_reason,
        raises=filter_raises,
    )
    sr = FakeSessionReader(snapshot=snapshot, raises=snapshot_raises)
    cb_ctx = FakeContextBuilder(
        context=context or _default_context(),
        raises=context_raises,
    )
    wa = FakeWriterAgent(extractions=raw_extractions, raises=extraction_raises)
    ev = FakeExtractionValidator(atoms=validated_atoms)
    circuit = FakeCircuitBreaker(is_open=circuit_open)
    eb = FakeEnvelopeBuilder(envelopes=envelopes)
    pe = FakePrivacyEnforcer()
    da = FakeDeltaAggregator()
    be = FakeBatchEmitter(returns=emitter_returns)
    ep = FakeEventPort(raises=event_raises)

    p = MemoryWriterPipeline(
        relevance_filter=f,  # type: ignore[arg-type]
        session_reader=sr,  # type: ignore[arg-type]
        context_builder=cb_ctx,  # type: ignore[arg-type]
        place_resolver=PlaceResolver([]),
        writer_agent=wa,  # type: ignore[arg-type]
        extraction_validator=ev,  # type: ignore[arg-type]
        circuit_breaker=circuit,
        envelope_builder=eb,  # type: ignore[arg-type]
        privacy_enforcer=pe,  # type: ignore[arg-type]
        delta_aggregator=da,  # type: ignore[arg-type]
        batch_emitter=be,  # type: ignore[arg-type]
        event_port=ep,  # type: ignore[arg-type]
        config=MWConfig(),
    )
    return p, f, sr, cb_ctx, wa, ev, circuit, eb, pe, da, be, ep


# ===========================================================================
# Tests
# ===========================================================================


class TestPipelineHappyPath:
    """Full pipeline happy path — filter PASS → extraction → envelope → batch."""

    @pytest.mark.asyncio
    async def test_single_turn_full_pipeline(self) -> None:
        envs = [_envelope("a"), _envelope("b")]
        p, *_ = _pipeline(
            raw_extractions=["raw1", "raw2"],
            validated_atoms=[_atom_stub(), _atom_stub()],
            envelopes=envs,
        )
        result = await p.process(_payload())
        assert result.atoms_extracted == 2
        assert result.envelopes_submitted == 2
        assert not result.skipped

    @pytest.mark.asyncio
    async def test_pipeline_result_has_all_fields(self) -> None:
        envs = [_envelope()]
        p, *_ = _pipeline(
            raw_extractions=["raw1"],
            validated_atoms=[_atom_stub()],
            envelopes=envs,
        )
        result = await p.process(_payload())
        assert result.atoms_extracted == 1
        assert result.envelopes_submitted == 1
        assert result.trace_id == "trace-abc"
        assert result.error is None
        assert not result.skipped

    @pytest.mark.asyncio
    async def test_pipeline_result_trace_id(self) -> None:
        p, *_ = _pipeline(
            raw_extractions=["raw1"],
            validated_atoms=[_atom_stub()],
            envelopes=[_envelope()],
        )
        result = await p.process(_payload(trace_id="trace-xyz"))
        assert result.trace_id == "trace-xyz"

    @pytest.mark.asyncio
    async def test_observability_events_published(self) -> None:
        envs = [_envelope()]
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            raw_extractions=["raw1"],
            validated_atoms=[_atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload())
        topics = [t for t, _ in ep.published]
        assert "k1.mw.filter.decision.v1" in topics
        assert "k1.mw.extraction.complete.v1" in topics
        assert "k1.mw.batch.submitted.v1" in topics

    @pytest.mark.asyncio
    async def test_privacy_enforcer_called_with_correct_band(self) -> None:
        ctx = _default_context(band="AMBER")
        envs = [_envelope()]
        p, _, _, _, _, _, _, _, pe, _, _, _ = _pipeline(
            context=ctx,
            raw_extractions=["raw1"],
            validated_atoms=[_atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload())
        assert len(pe.calls) == 1
        assert pe.calls[0][1] == "AMBER"


class TestPipelineFilterSkip:
    """Filter SKIP — short-circuit before context read."""

    @pytest.mark.asyncio
    async def test_filter_skip_returns_skipped_result(self) -> None:
        p, *_ = _pipeline(
            filter_passed=False,
            filter_skip_reason=SkipReason.EMPTY,
        )
        result = await p.process(_payload())
        assert result.skipped is True
        assert result.skip_reason == "EMPTY"

    @pytest.mark.asyncio
    async def test_filter_skip_no_context_read(self) -> None:
        p, _, sr, *_ = _pipeline(
            filter_passed=False,
            filter_skip_reason=SkipReason.CLARIFICATION,
        )
        await p.process(_payload())
        assert sr.call_count == 0

    @pytest.mark.asyncio
    async def test_filter_skip_no_llm_call(self) -> None:
        p, _, _, _, wa, *_ = _pipeline(
            filter_passed=False,
            filter_skip_reason=SkipReason.SYSTEM_TURN,
        )
        await p.process(_payload())
        assert wa.call_count == 0

    @pytest.mark.asyncio
    async def test_filter_error_falls_through(self) -> None:
        """Filter raises → treated as PASS (allow turn)."""
        p, _, sr, *_ = _pipeline(
            filter_raises=RuntimeError("filter broke"),
            raw_extractions=[],
            validated_atoms=[],
        )
        result = await p.process(_payload())
        # Filter error → treated as PASS → context reader IS called
        assert sr.call_count == 1
        assert not result.skipped


class TestPipelineContextErrors:
    """Context assembly failures."""

    @pytest.mark.asyncio
    async def test_snapshot_read_fails_returns_error(self) -> None:
        p, *_ = _pipeline(snapshot_raises=RuntimeError("SS timeout"))
        result = await p.process(_payload())
        assert result.error == "context_read_failed"

    @pytest.mark.asyncio
    async def test_snapshot_read_fails_no_extraction(self) -> None:
        p, _, _, _, wa, *_ = _pipeline(
            snapshot_raises=RuntimeError("SS timeout"),
        )
        await p.process(_payload())
        assert wa.call_count == 0

    @pytest.mark.asyncio
    async def test_context_build_fails_returns_error(self) -> None:
        p, *_ = _pipeline(context_raises=ValueError("bad snapshot"))
        result = await p.process(_payload())
        assert result.error == "context_read_failed"


class TestPipelineExtractionErrors:
    """Extraction stage errors and edge cases."""

    @pytest.mark.asyncio
    async def test_writer_agent_returns_empty(self) -> None:
        p, *_ = _pipeline(raw_extractions=[], validated_atoms=[])
        result = await p.process(_payload())
        assert result.atoms_extracted == 0

    @pytest.mark.asyncio
    async def test_validator_drops_all(self) -> None:
        p, *_ = _pipeline(
            raw_extractions=["raw1", "raw2", "raw3"],
            validated_atoms=[],
        )
        result = await p.process(_payload())
        assert result.atoms_extracted == 0

    @pytest.mark.asyncio
    async def test_llm_empty_no_envelope_build(self) -> None:
        p, _, _, _, _, _, _, eb, *_ = _pipeline(
            raw_extractions=[],
            validated_atoms=[],
        )
        await p.process(_payload())
        assert eb.call_count == 0

    @pytest.mark.asyncio
    async def test_llm_empty_no_bridge_submit(self) -> None:
        p, _, _, _, _, _, _, _, _, _, be, _ = _pipeline(
            raw_extractions=[],
            validated_atoms=[],
        )
        await p.process(_payload())
        assert len(be.calls) == 0

    @pytest.mark.asyncio
    async def test_extraction_partial_valid(self) -> None:
        p, *_ = _pipeline(
            raw_extractions=["raw1", "raw2", "raw3"],
            validated_atoms=[_atom_stub()],
            envelopes=[_envelope()],
        )
        result = await p.process(_payload())
        assert result.atoms_extracted == 1


class TestPipelineCircuitBreaker:
    """Circuit breaker states."""

    @pytest.mark.asyncio
    async def test_circuit_open_skips_extraction(self) -> None:
        p, *_ = _pipeline(circuit_open=True)
        result = await p.process(_payload())
        assert result.error == "circuit_breaker_open"

    @pytest.mark.asyncio
    async def test_circuit_open_no_llm_call(self) -> None:
        p, _, _, _, wa, *_ = _pipeline(circuit_open=True)
        await p.process(_payload())
        assert wa.call_count == 0

    @pytest.mark.asyncio
    async def test_circuit_open_publishes_event(self) -> None:
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(circuit_open=True)
        await p.process(_payload())
        topics = [t for t, _ in ep.published]
        assert "k1.mw.circuit.open.v1" in topics

    @pytest.mark.asyncio
    async def test_circuit_closed_allows_extraction(self) -> None:
        p, _, _, _, wa, *_ = _pipeline(
            circuit_open=False,
            raw_extractions=["raw1"],
            validated_atoms=[_atom_stub()],
            envelopes=[_envelope()],
        )
        await p.process(_payload())
        assert wa.call_count == 1


class TestPipelineBatchFlush:
    """Batch add/flush/emit mechanics."""

    @pytest.mark.asyncio
    async def test_envelopes_added_to_aggregator(self) -> None:
        envs = [_envelope("a"), _envelope("b"), _envelope("c")]
        p, _, _, _, _, _, _, _, _, da, _, _ = _pipeline(
            raw_extractions=["r1", "r2", "r3"],
            validated_atoms=[_atom_stub(), _atom_stub(), _atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload())
        assert len(da.added) == 3

    @pytest.mark.asyncio
    async def test_flush_called_after_add(self) -> None:
        envs = [_envelope()]
        p, _, _, _, _, _, _, _, _, da, be, _ = _pipeline(
            raw_extractions=["r1"],
            validated_atoms=[_atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload())
        # After flush, pending should be empty
        assert da.pending_count == 0
        # Emitter received the batch
        assert len(be.calls) == 1

    @pytest.mark.asyncio
    async def test_emitter_receives_flush_result(self) -> None:
        envs = [_envelope("x"), _envelope("y")]
        p, _, _, _, _, _, _, _, _, _, be, _ = _pipeline(
            raw_extractions=["r1", "r2"],
            validated_atoms=[_atom_stub(), _atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload())
        assert len(be.calls[0]) == 2

    @pytest.mark.asyncio
    async def test_flush_pending_drains_aggregator(self) -> None:
        p, _, _, _, _, _, _, _, _, da, be, _ = _pipeline()
        # Manually add something to the aggregator
        da.add(_envelope())
        count = await p.flush_pending()
        assert count == 1
        assert len(be.calls) == 1

    @pytest.mark.asyncio
    async def test_flush_pending_empty_returns_zero(self) -> None:
        p, *_ = _pipeline()
        count = await p.flush_pending()
        assert count == 0


class TestPipelineObservability:
    """Event publishing across all code paths."""

    @pytest.mark.asyncio
    async def test_filter_pass_publishes_decision(self) -> None:
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            raw_extractions=[],
            validated_atoms=[],
        )
        await p.process(_payload())
        decisions = [(t, d) for t, d in ep.published if t == "k1.mw.filter.decision.v1"]
        assert len(decisions) == 1
        assert decisions[0][1]["action"] == "PASS"

    @pytest.mark.asyncio
    async def test_filter_skip_publishes_decision(self) -> None:
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            filter_passed=False,
            filter_skip_reason=SkipReason.EMPTY,
        )
        await p.process(_payload())
        decisions = [(t, d) for t, d in ep.published if t == "k1.mw.filter.decision.v1"]
        assert len(decisions) == 1
        assert decisions[0][1]["action"] == "SKIP"
        assert decisions[0][1]["rule_id"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_extraction_complete_publishes_count(self) -> None:
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            raw_extractions=["r1", "r2"],
            validated_atoms=[_atom_stub(), _atom_stub()],
            envelopes=[_envelope(), _envelope()],
        )
        await p.process(_payload())
        extractions = [(t, d) for t, d in ep.published if t == "k1.mw.extraction.complete.v1"]
        assert len(extractions) == 1
        assert extractions[0][1]["atom_count"] == 2

    @pytest.mark.asyncio
    async def test_batch_submitted_publishes_count(self) -> None:
        envs = [_envelope(), _envelope(), _envelope()]
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            raw_extractions=["r1", "r2", "r3"],
            validated_atoms=[_atom_stub(), _atom_stub(), _atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload())
        batches = [(t, d) for t, d in ep.published if t == "k1.mw.batch.submitted.v1"]
        assert len(batches) == 1
        assert batches[0][1]["submitted_count"] == 3

    @pytest.mark.asyncio
    async def test_error_publishes_pipeline_error(self) -> None:
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            snapshot_raises=RuntimeError("SS timeout"),
        )
        await p.process(_payload())
        errors = [(t, d) for t, d in ep.published if t == "k1.mw.pipeline.error.v1"]
        assert len(errors) == 1
        assert errors[0][1]["stage"] == "context_assembly"

    @pytest.mark.asyncio
    async def test_publish_failure_ignored(self) -> None:
        """Event port raises → pipeline continues (best-effort)."""
        p, *_ = _pipeline(
            event_raises=RuntimeError("bus down"),
            raw_extractions=["r1"],
            validated_atoms=[_atom_stub()],
            envelopes=[_envelope()],
        )
        # Should NOT raise
        result = await p.process(_payload())
        assert result.atoms_extracted == 1

    @pytest.mark.asyncio
    async def test_all_events_carry_trace_id(self) -> None:
        envs = [_envelope()]
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            raw_extractions=["r1"],
            validated_atoms=[_atom_stub()],
            envelopes=envs,
        )
        await p.process(_payload(trace_id="trace-unique"))
        for topic, payload_data in ep.published:
            assert "trace_id" in payload_data, f"Event {topic} missing trace_id"
            assert payload_data["trace_id"] == "trace-unique"

    @pytest.mark.asyncio
    async def test_zero_atoms_still_publishes_extraction_complete(self) -> None:
        p, _, _, _, _, _, _, _, _, _, _, ep = _pipeline(
            raw_extractions=[],
            validated_atoms=[],
        )
        await p.process(_payload())
        extractions = [(t, d) for t, d in ep.published if t == "k1.mw.extraction.complete.v1"]
        assert len(extractions) == 1
        assert extractions[0][1]["atom_count"] == 0
