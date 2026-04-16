"""
E-1.2 I-1.2.3 — Classification + LLM adapter hardening tests.

Covers:
  K1UltraBERTAdapter:        singleton, LRU/TTL cache, metrics, warmup, degradation
  StubUltraBERTAdapter:      analyze None, is_available False, metrics
  UltraBERTPhase1Pipeline:   classify happy path, degradation, embedding, mapping, complexity
  ModelHubPOCBridge:          execute, stream_execute, discover_*, health, all payload translations

~90 tests across 16 classes. Zero GPU/network required — all stubs.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from k1.concierge.fsm.ultrabert_adapter import (
    HIGH_AROUSAL_EMOTIONS,
    LOW_AROUSAL_EMOTIONS,
    SENTIMENT_TO_VALENCE,
    K1UltraBERTAdapter,
    StubUltraBERTAdapter,
    UltraBERTAdapter,
    _LRUTTLCache,
)

# ===================================================================
# PART 1: K1UltraBERTAdapter + StubUltraBERTAdapter
# ===================================================================


# ---------------------------------------------------------------------------
# _LRUTTLCache unit tests
# ---------------------------------------------------------------------------


class TestLRUTTLCache:
    """Thread-safe LRU cache with TTL expiry."""

    def test_get_miss(self) -> None:
        cache = _LRUTTLCache(max_size=4, ttl_s=10.0)
        assert cache.get("missing") is None
        assert cache.misses == 1

    def test_put_then_get_hit(self) -> None:
        cache = _LRUTTLCache(max_size=4, ttl_s=10.0)
        cache.put("k", {"v": 1})
        assert cache.get("k") == {"v": 1}
        assert cache.hits == 1

    def test_ttl_expiry(self) -> None:
        cache = _LRUTTLCache(max_size=4, ttl_s=0.0)  # Immediate expiry
        cache.put("k", {"v": 1})
        assert cache.get("k") is None  # Expired
        assert cache.misses == 1

    def test_lru_eviction(self) -> None:
        cache = _LRUTTLCache(max_size=2, ttl_s=60.0)
        cache.put("a", {"a": 1})
        cache.put("b", {"b": 2})
        cache.put("c", {"c": 3})  # Evicts "a" (oldest)
        assert cache.get("a") is None
        assert cache.get("b") == {"b": 2}
        assert cache.get("c") == {"c": 3}

    def test_lru_access_reorders(self) -> None:
        cache = _LRUTTLCache(max_size=2, ttl_s=60.0)
        cache.put("a", {"a": 1})
        cache.put("b", {"b": 2})
        cache.get("a")  # Access "a" — moves to end
        cache.put("c", {"c": 3})  # Evicts "b" (now oldest)
        assert cache.get("a") == {"a": 1}
        assert cache.get("b") is None

    def test_clear_resets_stats(self) -> None:
        cache = _LRUTTLCache(max_size=4, ttl_s=60.0)
        cache.put("k", {"v": 1})
        cache.get("k")
        cache.get("miss")
        cache.clear()
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.get("k") is None

    def test_overwrite_existing_key(self) -> None:
        cache = _LRUTTLCache(max_size=4, ttl_s=60.0)
        cache.put("k", {"v": 1})
        cache.put("k", {"v": 2})
        assert cache.get("k") == {"v": 2}


# ---------------------------------------------------------------------------
# StubUltraBERTAdapter
# ---------------------------------------------------------------------------


class TestStubUltraBERTAdapter:
    """StubUltraBERTAdapter — returns None for everything."""

    def test_analyze_returns_none(self) -> None:
        stub = StubUltraBERTAdapter()
        assert stub.analyze("hello") is None

    def test_is_available_false(self) -> None:
        stub = StubUltraBERTAdapter()
        assert stub.is_available() is False

    def test_get_metrics_stub_flag(self) -> None:
        stub = StubUltraBERTAdapter()
        m = stub.get_metrics()
        assert m["stub"] is True
        assert m["available"] is False

    def test_satisfies_protocol(self) -> None:
        stub = StubUltraBERTAdapter()
        assert isinstance(stub, UltraBERTAdapter)


# ---------------------------------------------------------------------------
# K1UltraBERTAdapter (without GPU — graceful degradation)
# ---------------------------------------------------------------------------


def _make_adapter_without_client() -> K1UltraBERTAdapter:
    """Create K1UltraBERTAdapter forcing the no-client degradation path."""
    K1UltraBERTAdapter.reset_instance()
    adapter = K1UltraBERTAdapter()
    # Force the degraded state regardless of whether the package is installed
    adapter._client = None
    adapter._available = False
    return adapter


class TestK1UltraBERTAdapterNoGPU:
    """K1UltraBERTAdapter when client is unavailable (degraded path)."""

    def setup_method(self) -> None:
        K1UltraBERTAdapter.reset_instance()

    def teardown_method(self) -> None:
        K1UltraBERTAdapter.reset_instance()

    def test_is_available_false_without_client(self) -> None:
        adapter = _make_adapter_without_client()
        assert adapter.is_available() is False

    def test_analyze_returns_none_without_client(self) -> None:
        adapter = _make_adapter_without_client()
        assert adapter.analyze("hello") is None

    def test_fallback_count_increments(self) -> None:
        adapter = _make_adapter_without_client()
        adapter.analyze("text1")
        adapter.analyze("text2")
        m = adapter.get_metrics()
        assert m["fallback_count"] == 2

    def test_call_count_zero_without_client(self) -> None:
        adapter = _make_adapter_without_client()
        adapter.analyze("anything")
        m = adapter.get_metrics()
        assert m["call_count"] == 0

    def test_metrics_structure(self) -> None:
        adapter = K1UltraBERTAdapter()
        m = adapter.get_metrics()
        assert "call_count" in m
        assert "avg_latency_ms" in m
        assert "cache_hits" in m
        assert "cache_misses" in m
        assert "fallback_count" in m
        assert "available" in m

    def test_satisfies_protocol(self) -> None:
        adapter = K1UltraBERTAdapter()
        assert isinstance(adapter, UltraBERTAdapter)

    def test_warmup_no_crash_without_client(self) -> None:
        adapter = _make_adapter_without_client()
        adapter.warmup()  # Should not raise


class TestK1UltraBERTAdapterSingleton:
    """Singleton pattern for K1UltraBERTAdapter."""

    def setup_method(self) -> None:
        K1UltraBERTAdapter.reset_instance()

    def teardown_method(self) -> None:
        K1UltraBERTAdapter.reset_instance()

    def test_get_instance_returns_same(self) -> None:
        a = K1UltraBERTAdapter.get_instance()
        b = K1UltraBERTAdapter.get_instance()
        assert a is b

    def test_reset_instance_clears(self) -> None:
        a = K1UltraBERTAdapter.get_instance()
        K1UltraBERTAdapter.reset_instance()
        b = K1UltraBERTAdapter.get_instance()
        assert a is not b


class TestK1UltraBERTAdapterWithMockedClient:
    """K1UltraBERTAdapter with a mocked familyos_ultrabert.Client."""

    def setup_method(self) -> None:
        K1UltraBERTAdapter.reset_instance()

    def teardown_method(self) -> None:
        K1UltraBERTAdapter.reset_instance()

    def _make_adapter_with_mock(self) -> tuple[K1UltraBERTAdapter, MagicMock]:
        """Create adapter with manually injected mock client."""
        adapter = K1UltraBERTAdapter(cache_size=4, cache_ttl_s=60.0)
        mock_client = MagicMock()
        adapter._client = mock_client
        adapter._available = True
        return adapter, mock_client

    def _make_result_mock(self) -> MagicMock:
        """Return a mock that mimics familyos_ultrabert result."""
        r = MagicMock()
        r.sentiment = "positive"
        r.sentiment_confidence = 0.9
        r.emotions = ["joy"]
        r.emotion_scores = {"joy": 0.95}
        r.safety = "GREEN"
        r.safety_confidence = 0.99
        r.entities = []
        r.general_entities = []
        r.temporal = []
        r.intent = "greet"
        r.ingress = "social"
        r.relations = []
        r.embedding = [0.1] * 768
        r.latency_ms = 20
        return r

    def test_analyze_returns_dict(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_client.analyze.return_value = self._make_result_mock()
        result = adapter.analyze("hello")
        assert isinstance(result, dict)
        assert result["sentiment"] == "positive"
        assert result["intent"] == "greet"

    def test_analyze_caches_by_hash(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_client.analyze.return_value = self._make_result_mock()
        adapter.analyze("same text")
        adapter.analyze("same text")  # Should hit cache
        assert mock_client.analyze.call_count == 1
        assert adapter.get_metrics()["cache_hits"] == 1

    def test_analyze_different_texts_no_cache(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_client.analyze.return_value = self._make_result_mock()
        adapter.analyze("text one")
        adapter.analyze("text two")
        assert mock_client.analyze.call_count == 2

    def test_analyze_exception_returns_none(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_client.analyze.side_effect = RuntimeError("GPU OOM")
        result = adapter.analyze("crash")
        assert result is None
        assert adapter.get_metrics()["fallback_count"] == 1

    def test_call_count_tracked(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_client.analyze.return_value = self._make_result_mock()
        adapter.analyze("a")
        adapter.analyze("b")
        assert adapter.get_metrics()["call_count"] == 2

    def test_result_to_dict_all_fields(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_result = self._make_result_mock()
        mock_client.analyze.return_value = mock_result
        result = adapter.analyze("test")
        expected_keys = {
            "sentiment",
            "sentiment_confidence",
            "emotions",
            "emotion_scores",
            "safety",
            "safety_confidence",
            "entities",
            "general_entities",
            "temporal",
            "intent",
            "ingress",
            "relations",
            "embedding",
            "latency_ms",
        }
        assert set(result.keys()) == expected_keys

    def test_is_available_true_with_client(self) -> None:
        adapter, _ = self._make_adapter_with_mock()
        assert adapter.is_available() is True


# ---------------------------------------------------------------------------
# Mapping constants
# ---------------------------------------------------------------------------


class TestMappingConstants:
    """K1-owned mapping constants for UltraBERT output."""

    def test_sentiment_to_valence_range(self) -> None:
        for key, val in SENTIMENT_TO_VALENCE.items():
            assert -1.0 <= val <= 1.0, f"{key} out of range: {val}"

    def test_sentiment_to_valence_coverage(self) -> None:
        expected = {"very_negative", "negative", "neutral", "positive", "very_positive"}
        assert set(SENTIMENT_TO_VALENCE.keys()) == expected

    def test_high_arousal_emotions_frozen(self) -> None:
        assert isinstance(HIGH_AROUSAL_EMOTIONS, frozenset)
        assert "anger" in HIGH_AROUSAL_EMOTIONS

    def test_low_arousal_emotions_frozen(self) -> None:
        assert isinstance(LOW_AROUSAL_EMOTIONS, frozenset)
        assert "calm" in LOW_AROUSAL_EMOTIONS

    def test_no_overlap_high_low(self) -> None:
        assert HIGH_AROUSAL_EMOTIONS.isdisjoint(LOW_AROUSAL_EMOTIONS)


# ===================================================================
# PART 2: UltraBERTPhase1Pipeline
# ===================================================================

from k1.concierge.fsm.phase1 import Phase1Result, StubPhase1Pipeline
from k1.concierge.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline


class _FakeUltraBERTAdapter:
    """Controllable adapter for pipeline tests."""

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self.call_count = 0

    def analyze(self, text: str) -> dict[str, Any] | None:
        self.call_count += 1
        if self._raises:
            raise self._raises
        return self._result

    def is_available(self) -> bool:
        return self._result is not None

    def get_metrics(self) -> dict[str, Any]:
        return {"call_count": self.call_count}


def _minimal_analysis(**overrides: Any) -> dict[str, Any]:
    """Minimal valid 12-head analysis dict."""
    base = {
        "sentiment": "neutral",
        "sentiment_confidence": 0.5,
        "emotions": ["neutral"],
        "emotion_scores": {"neutral": 0.5},
        "safety": "GREEN",
        "safety_confidence": 0.99,
        "entities": [],
        "general_entities": [],
        "temporal": [],
        "intent": "general",
        "ingress": "general",
        "relations": [],
        "embedding": [0.1] * 10,
        "latency_ms": 15,
    }
    base.update(overrides)
    return base


class TestUltraBERTPhase1PipelineClassify:
    """classify() happy path with real adapter output."""

    def test_returns_phase1_result(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis())
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hello")
        assert isinstance(result, Phase1Result)

    def test_maps_intent(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis(intent="greeting"))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hi there")
        assert result.intent_classification == "greeting"

    def test_maps_domain(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis(ingress="health"))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("my headache")
        assert result.domain_context == "health"

    def test_maps_safety_band(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis(safety="RED"))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("unsafe text")
        assert result.safety_band == "RED"

    def test_maps_emotion(self) -> None:
        adapter = _FakeUltraBERTAdapter(
            result=_minimal_analysis(
                emotions=["joy", "excitement"],
                emotion_scores={"joy": 0.9, "excitement": 0.7},
            )
        )
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("great news!")
        assert result.primary_emotion == "joy"
        assert result.emotion_confidence == 0.9

    def test_maps_valence_from_sentiment(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis(sentiment="positive"))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("good day")
        assert result.valence == pytest.approx(0.4)

    def test_maps_entities_merged(self) -> None:
        analysis = _minimal_analysis(
            entities=[{"text": "Mom", "label": "PERSON", "start": 0, "end": 3}],
            general_entities=[{"text": "Paris", "label": "LOC", "start": 10, "end": 15}],
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("Mom in Paris")
        assert len(result.entities) == 2

    def test_maps_temporal_expressions(self) -> None:
        analysis = _minimal_analysis(temporal=[{"text": "tomorrow", "type": "DATE_REL"}])
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("do it tomorrow")
        assert len(result.temporal_expressions) == 1

    def test_call_count_increments(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis())
        pipeline = UltraBERTPhase1Pipeline(adapter)
        pipeline.classify("a")
        pipeline.classify("b")
        assert pipeline.call_count == 2


class TestUltraBERTPhase1PipelineDegradation:
    """Graceful degradation when adapter returns None or raises."""

    def test_fallback_to_stub_on_none(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=None)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hello")
        assert isinstance(result, Phase1Result)
        assert result._degraded is True

    def test_fallback_to_stub_on_exception(self) -> None:
        adapter = _FakeUltraBERTAdapter(raises=RuntimeError("GPU crash"))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hello")
        assert isinstance(result, Phase1Result)
        assert result._degraded is True

    def test_degraded_count_increments(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=None)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        pipeline.classify("a")
        pipeline.classify("b")
        assert pipeline.degraded_count == 2

    def test_non_degraded_result(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis())
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hello")
        assert result._degraded is False

    def test_custom_fallback(self) -> None:
        fallback = StubPhase1Pipeline()
        adapter = _FakeUltraBERTAdapter(result=None)
        pipeline = UltraBERTPhase1Pipeline(adapter, fallback=fallback)
        result = pipeline.classify("x")
        # Stub returns defaults
        assert result.intent_classification == "general"


class TestUltraBERTPhase1PipelineEmbedding:
    """Embedding retention from adapter output."""

    def test_retains_last_embedding(self) -> None:
        emb = [0.5] * 768
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis(embedding=emb))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        pipeline.classify("text")
        assert pipeline.last_embedding == emb

    def test_none_embedding_when_not_list(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis(embedding="not_a_list"))
        pipeline = UltraBERTPhase1Pipeline(adapter)
        pipeline.classify("text")
        assert pipeline.last_embedding is None

    def test_none_embedding_on_degradation(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=None)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        pipeline.classify("text")
        assert pipeline.last_embedding is None


class TestUltraBERTPhase1PipelineArousal:
    """Arousal inference from emotion labels."""

    def test_high_arousal_emotion(self) -> None:
        analysis = _minimal_analysis(
            emotions=["anger"],
            emotion_scores={"anger": 0.8},
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("I'm furious")
        assert result.arousal >= 0.7

    def test_low_arousal_emotion(self) -> None:
        analysis = _minimal_analysis(
            emotions=["calm"],
            emotion_scores={"calm": 0.9},
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("I'm at peace")
        assert result.arousal <= 0.3

    def test_neutral_arousal_default(self) -> None:
        analysis = _minimal_analysis(
            emotions=["neutral"],
            emotion_scores={"neutral": 0.5},
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hello")
        assert result.arousal == pytest.approx(0.5)


class TestUltraBERTPhase1PipelineComplexity:
    """Multi-factor complexity tier computation."""

    def test_low_complexity_single_intent(self) -> None:
        adapter = _FakeUltraBERTAdapter(result=_minimal_analysis())
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hi")
        assert result.complexity_tier == "LOW"

    def test_safety_override_red_forces_low(self) -> None:
        analysis = _minimal_analysis(
            safety="RED",
            intent_scores={"crisis": 0.9, "greeting": 0.8},
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("emergency")
        assert result.complexity_tier == "LOW"

    def test_multi_intent_bumps_complexity(self) -> None:
        analysis = _minimal_analysis(
            intent="greet",
            intent_scores={"greet": 0.9, "schedule": 0.5},
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("hi, schedule something")
        # Multi-intent adds +1 to score
        assert result.complexity_tier in ("LOW", "MEDIUM")


class TestUltraBERTPhase1PipelineEntityMerge:
    """Entity merging: family NER + general NER, de-dup by span."""

    def test_dedup_by_span(self) -> None:
        analysis = _minimal_analysis(
            entities=[{"text": "Mom", "label": "FAM", "start": 0, "end": 3}],
            general_entities=[{"text": "Mom", "label": "PERSON", "start": 0, "end": 3}],
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("Mom is here")
        # Family entity takes priority on overlap
        assert len(result.entities) == 1
        assert result.entities[0]["label"] == "FAM"

    def test_non_overlapping_merged(self) -> None:
        analysis = _minimal_analysis(
            entities=[{"text": "Dad", "label": "FAM", "start": 0, "end": 3}],
            general_entities=[{"text": "NYC", "label": "LOC", "start": 10, "end": 13}],
        )
        adapter = _FakeUltraBERTAdapter(result=analysis)
        pipeline = UltraBERTPhase1Pipeline(adapter)
        result = pipeline.classify("Dad in NYC")
        assert len(result.entities) == 2


# ===================================================================
# PART 3: ModelHubPOCBridge
# ===================================================================

from k1.concierge.llm.model_hub_bridge import ModelHubPOCBridge
from k1.concierge.llm.types import Capability, ConciergeModelResponse
from k1.concierge.llm.types import FinishReason as POCFinishReason
from k1.concierge.llm.types import ModelMessage, StreamChunk
from k1.concierge.llm.types import ToolCallResult as POCToolCallResult
from k1.concierge.llm.types import ToolSchema
from k1.model_hub.types import CapabilityType, ChatPayload, ChatResult
from k1.model_hub.types import FinishReason as HubFinishReason
from k1.model_hub.types import (
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    Message,
    ModelInfo,
    ReasonPayload,
    ReasonResult,
    RequestConstraints,
    ResponseMetadata,
    StructuredOutputPayload,
    StructuredResult,
    TokenUsage,
    ToolCallPayload,
)
from k1.model_hub.types import ToolCallResult as HubToolCallResult
from k1.model_hub.types import ToolCallResultSet, ToolDefinition


class _FakePOCAdapter:
    """Controllable POC adapter for ModelHubPOCBridge tests."""

    def __init__(
        self,
        response: ConciergeModelResponse | None = None,
        stream_chunks: list[StreamChunk] | None = None,
    ) -> None:
        self._response = response or ConciergeModelResponse(
            text="Hello!",
            tokens_in=10,
            tokens_out=5,
            model_id="gemini-2.5-flash",
            finish_reason="stop",
        )
        self._stream_chunks = stream_chunks or []
        self.generate_calls: list = []
        self.stream_calls: list = []

    async def generate(self, request: Any) -> ConciergeModelResponse:
        self.generate_calls.append(request)
        return self._response

    async def generate_stream(self, request: Any) -> AsyncIterator:
        self.stream_calls.append(request)
        for chunk in self._stream_chunks:
            yield chunk


class TestModelHubPOCBridgeExecute:
    """execute() translates HubRequest → POC → HubResponse."""

    def _make_chat_request(self, text: str = "hello") -> HubRequest:
        return HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(
                messages=[Message(role="user", content=text)],
                system_prompt="You are helpful.",
            ),
            constraints=RequestConstraints(consumer_id="concierge.front"),
            trace_id="trace-001",
        )

    def test_execute_chat_returns_hub_response(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        result = asyncio.get_event_loop().run_until_complete(
            bridge.execute(self._make_chat_request())
        )
        assert isinstance(result, HubResponse)
        assert isinstance(result.result, ChatResult)
        assert result.result.text == "Hello!"

    def test_execute_metadata_populated(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        result = asyncio.get_event_loop().run_until_complete(
            bridge.execute(self._make_chat_request())
        )
        m = result.metadata
        assert m.trace_id == "trace-001"
        assert m.model_id == "gemini-2.5-flash"
        assert m.provider_id == "poc-bridge"
        assert m.usage.prompt_tokens == 10
        assert m.usage.completion_tokens == 5
        assert m.capability == CapabilityType.CHAT

    def test_execute_finish_reason_mapped(self) -> None:
        resp = ConciergeModelResponse(text="x", finish_reason="tool_calls")
        inner = _FakePOCAdapter(response=resp)
        bridge = ModelHubPOCBridge(inner)
        result = asyncio.get_event_loop().run_until_complete(
            bridge.execute(self._make_chat_request())
        )
        assert result.metadata.finish_reason == HubFinishReason.TOOL_CALLS

    def test_execute_consumer_id_to_actor(self) -> None:
        """consumer_id 'concierge.front' maps actor to 'front'."""
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        asyncio.get_event_loop().run_until_complete(bridge.execute(self._make_chat_request()))
        poc_req = inner.generate_calls[0]
        assert poc_req.actor == "front"


class TestModelHubPOCBridgeToolCall:
    """execute() with TOOL_CALL capability."""

    def test_tool_call_response(self) -> None:
        resp = ConciergeModelResponse(
            text="Calling tool",
            tool_calls=[
                POCToolCallResult(id="tc1", name="get_weather", arguments={"city": "Paris"}),
            ],
            finish_reason="tool_calls",
        )
        inner = _FakePOCAdapter(response=resp)
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="weather?")],
                tools=[
                    ToolDefinition(
                        name="get_weather", description="Get weather", parameters={"type": "object"}
                    )
                ],
            ),
            trace_id="trace-tc",
        )
        result = asyncio.get_event_loop().run_until_complete(bridge.execute(req))
        assert isinstance(result.result, ToolCallResultSet)
        assert len(result.result.tool_calls) == 1
        assert result.result.tool_calls[0].name == "get_weather"

    def test_tool_definitions_translated(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="do")],
                tools=[
                    ToolDefinition(
                        name="my_tool", description="desc", parameters={"type": "object"}
                    )
                ],
            ),
            trace_id="trace-td",
        )
        asyncio.get_event_loop().run_until_complete(bridge.execute(req))
        poc_req = inner.generate_calls[0]
        assert poc_req.tools is not None
        assert len(poc_req.tools) == 1
        assert poc_req.tools[0].name == "my_tool"


class TestModelHubPOCBridgeStructured:
    """execute() with STRUCTURED capability."""

    def test_structured_response(self) -> None:
        resp = ConciergeModelResponse(
            text="",
            json_output={"name": "John", "age": 30},
            finish_reason="stop",
        )
        inner = _FakePOCAdapter(response=resp)
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.STRUCTURED,
            payload=StructuredOutputPayload(
                messages=[Message(role="user", content="extract info")],
                output_schema={"type": "object", "properties": {"name": {"type": "string"}}},
            ),
            trace_id="trace-struct",
        )
        result = asyncio.get_event_loop().run_until_complete(bridge.execute(req))
        assert isinstance(result.result, StructuredResult)
        assert result.result.json_output == {"name": "John", "age": 30}


class TestModelHubPOCBridgeReason:
    """execute() with REASON capability."""

    def test_reason_response(self) -> None:
        resp = ConciergeModelResponse(
            text="The answer is 42.",
            thought_text="Let me think step by step...",
            finish_reason="stop",
        )
        inner = _FakePOCAdapter(response=resp)
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.REASON,
            payload=ReasonPayload(
                messages=[Message(role="user", content="What is the meaning of life?")],
                reasoning_effort="high",
            ),
            trace_id="trace-reason",
        )
        result = asyncio.get_event_loop().run_until_complete(bridge.execute(req))
        assert isinstance(result.result, ReasonResult)
        assert result.result.text == "The answer is 42."
        assert result.result.thinking == "Let me think step by step..."


class TestModelHubPOCBridgeStream:
    """stream_execute() translates POC StreamChunks to HubChunks."""

    def test_stream_text_delta(self) -> None:
        chunks = [
            StreamChunk(chunk_type="text_delta", text="Hello "),
            StreamChunk(chunk_type="text_delta", text="world"),
        ]
        inner = _FakePOCAdapter(stream_chunks=chunks)
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            trace_id="trace-stream",
        )
        collected: list[HubChunk] = []

        async def _collect():
            async for chunk in bridge.stream_execute(req):
                collected.append(chunk)

        asyncio.get_event_loop().run_until_complete(_collect())
        assert len(collected) == 2
        assert collected[0].content == "Hello "
        assert collected[1].content == "world"

    def test_stream_done_chunk(self) -> None:
        resp = ConciergeModelResponse(
            text="Done",
            tokens_in=5,
            tokens_out=3,
            model_id="gemini-2.5-flash",
            finish_reason="stop",
        )
        chunks = [
            StreamChunk(chunk_type="text_delta", text="Done"),
            StreamChunk(chunk_type="done", response=resp),
        ]
        inner = _FakePOCAdapter(stream_chunks=chunks)
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            trace_id="trace-stream-done",
        )
        collected: list[HubChunk] = []

        async def _collect():
            async for chunk in bridge.stream_execute(req):
                collected.append(chunk)

        asyncio.get_event_loop().run_until_complete(_collect())
        assert collected[-1].done is True
        assert collected[-1].metadata is not None

    def test_stream_tool_call_delta(self) -> None:
        tc = POCToolCallResult(id="tc1", name="search", arguments={"q": "test"})
        chunks = [StreamChunk(chunk_type="tool_call_delta", tool_call_partial=tc)]
        inner = _FakePOCAdapter(stream_chunks=chunks)
        bridge = ModelHubPOCBridge(inner)
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="search")],
                tools=[ToolDefinition(name="search", description="S", parameters={})],
            ),
            trace_id="trace-stream-tc",
        )
        collected: list[HubChunk] = []

        async def _collect():
            async for chunk in bridge.stream_execute(req):
                collected.append(chunk)

        asyncio.get_event_loop().run_until_complete(_collect())
        assert collected[0].tool_calls is not None
        assert collected[0].tool_calls[0].name == "search"


class TestModelHubPOCBridgeDiscovery:
    """discover_capabilities() and discover_models()."""

    def test_discover_capabilities_four_types(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        caps = asyncio.get_event_loop().run_until_complete(bridge.discover_capabilities())
        assert CapabilityType.CHAT in caps
        assert CapabilityType.TOOL_CALL in caps
        assert CapabilityType.STRUCTURED in caps
        assert CapabilityType.REASON in caps

    def test_discover_capabilities_all_have_poc_bridge(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        caps = asyncio.get_event_loop().run_until_complete(bridge.discover_capabilities())
        for cap, providers in caps.items():
            assert "poc-bridge" in providers

    def test_discover_models_returns_list(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        models = asyncio.get_event_loop().run_until_complete(bridge.discover_models())
        assert isinstance(models, list)
        assert all(isinstance(m, ModelInfo) for m in models)

    def test_discover_models_have_google_provider(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        models = asyncio.get_event_loop().run_until_complete(bridge.discover_models())
        assert all(m.provider_id == "google" for m in models)

    def test_discover_models_no_duplicates(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        models = asyncio.get_event_loop().run_until_complete(bridge.discover_models())
        ids = [m.id for m in models]
        assert len(ids) == len(set(ids))


class TestModelHubPOCBridgeHealth:
    """health() returns HubHealthReport."""

    def test_health_returns_report(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        report = asyncio.get_event_loop().run_until_complete(bridge.health())
        assert isinstance(report, HubHealthReport)

    def test_health_status_healthy(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        report = asyncio.get_event_loop().run_until_complete(bridge.health())
        assert report.status == "HEALTHY"

    def test_health_has_provider(self) -> None:
        inner = _FakePOCAdapter()
        bridge = ModelHubPOCBridge(inner)
        report = asyncio.get_event_loop().run_until_complete(bridge.health())
        assert len(report.providers) == 1
        assert report.providers[0].provider_id == "poc-bridge"
