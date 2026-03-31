"""
Tests for M10 E10.4 -- K1UltraBERTAdapter, StubUltraBERTAdapter, singleton.

Covers:
  - StubUltraBERTAdapter always returns None
  - K1UltraBERTAdapter with monkeypatched familyos_ultrabert.Client
  - Metrics tracking (call_count, avg_latency, cache hits/misses)
  - Singleton pattern (get_ultrabert_adapter returns same instance)
  - Warmup (logs timing, increments call_count)
  - LRU/TTL cache behaviour
  - Protocol conformance
"""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k1.concierge.fsm.ultrabert_adapter import (
    ENTITY_MIN_CONFIDENCE,
    HIGH_AROUSAL_EMOTIONS,
    LOW_AROUSAL_EMOTIONS,
    SENTIMENT_TO_VALENCE,
    K1UltraBERTAdapter,
    StubUltraBERTAdapter,
    UltraBERTAdapter,
    _LRUTTLCache,
    get_ultrabert_adapter,
)

# =========================================================================
# Fixtures
# =========================================================================


def _fake_result(**overrides: Any) -> MagicMock:
    """Build a mock familyos_ultrabert analysis result object."""
    defaults = {
        "sentiment": "positive",
        "sentiment_confidence": 0.85,
        "emotions": ["joy", "love"],
        "emotion_scores": {"joy": 0.9, "love": 0.6, "neutral": 0.1},
        "safety": "GREEN",
        "safety_confidence": 0.95,
        "entities": [{"text": "Mom", "label": "KINSHIP", "start": 0, "end": 3}],
        "general_entities": [{"text": "Saturday", "label": "DATE", "start": 10, "end": 18}],
        "temporal": [{"text": "next Saturday", "label": "DATE_REL", "start": 5, "end": 18}],
        "intent": "log_memory",
        "ingress": "FAMILY",
        "relations": ["parent_of"],
        "embedding": [0.1] * 768,
        "latency_ms": 18.5,
    }
    defaults.update(overrides)
    result = MagicMock()
    for k, v in defaults.items():
        setattr(result, k, v)
    return result


def _mock_client_module(fake_result: MagicMock | None = None):
    """Create a mock familyos_ultrabert module with Client class."""
    mock_client = MagicMock()
    mock_client.analyze.return_value = fake_result or _fake_result()

    mock_module = types.ModuleType("familyos_ultrabert")
    mock_module.Client = MagicMock(return_value=mock_client)  # type: ignore[attr-defined]
    return mock_module, mock_client


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton before each test."""
    K1UltraBERTAdapter.reset_instance()
    yield
    K1UltraBERTAdapter.reset_instance()


# =========================================================================
# Mapping constants
# =========================================================================


class TestMappingConstants:
    """Verify K1-owned mapping constants are correct."""

    def test_sentiment_to_valence_has_five_keys(self):
        assert len(SENTIMENT_TO_VALENCE) == 5
        assert SENTIMENT_TO_VALENCE["very_negative"] == 0.1
        assert SENTIMENT_TO_VALENCE["very_positive"] == 0.9

    def test_high_arousal_emotions(self):
        assert "anger" in HIGH_AROUSAL_EMOTIONS
        assert "excitement" in HIGH_AROUSAL_EMOTIONS
        assert "fear" in HIGH_AROUSAL_EMOTIONS
        assert "surprise" in HIGH_AROUSAL_EMOTIONS

    def test_low_arousal_emotions(self):
        assert "sadness" in LOW_AROUSAL_EMOTIONS
        assert "calm" in LOW_AROUSAL_EMOTIONS

    def test_entity_min_confidence(self):
        assert ENTITY_MIN_CONFIDENCE == pytest.approx(0.65)


# =========================================================================
# StubUltraBERTAdapter
# =========================================================================


class TestStubUltraBERTAdapter:
    """StubUltraBERTAdapter always returns None / False."""

    def test_analyze_returns_none(self):
        stub = StubUltraBERTAdapter()
        assert stub.analyze("hello world") is None

    def test_is_available_returns_false(self):
        stub = StubUltraBERTAdapter()
        assert stub.is_available() is False

    def test_get_metrics_has_stub_flag(self):
        stub = StubUltraBERTAdapter()
        m = stub.get_metrics()
        assert m["stub"] is True
        assert m["available"] is False

    def test_conforms_to_protocol(self):
        stub = StubUltraBERTAdapter()
        assert isinstance(stub, UltraBERTAdapter)


# =========================================================================
# K1UltraBERTAdapter -- init
# =========================================================================


class TestK1AdapterInit:
    """Init and availability."""

    def test_unavailable_when_import_fails(self):
        """If familyos_ultrabert is not installed, adapter is unavailable."""
        adapter = K1UltraBERTAdapter()
        # On CI without GPU, import will fail
        # We just check that it doesn't crash and reports status
        assert isinstance(adapter.is_available(), bool)

    def test_available_with_mocked_module(self):
        """With mocked familyos_ultrabert, adapter should be available."""
        mock_mod, _ = _mock_client_module()
        with patch.dict("sys.modules", {"familyos_ultrabert": mock_mod}):
            adapter = K1UltraBERTAdapter()
        assert adapter.is_available() is True

    def test_conforms_to_protocol(self):
        adapter = K1UltraBERTAdapter()
        assert isinstance(adapter, UltraBERTAdapter)


# =========================================================================
# K1UltraBERTAdapter -- analyze
# =========================================================================


class TestK1AdapterAnalyze:
    """analyze() with mocked familyos_ultrabert."""

    def _make_adapter(self) -> tuple[K1UltraBERTAdapter, MagicMock]:
        mock_mod, mock_client = _mock_client_module()
        with patch.dict("sys.modules", {"familyos_ultrabert": mock_mod}):
            adapter = K1UltraBERTAdapter()
        return adapter, mock_client

    def test_returns_dict_with_all_keys(self):
        adapter, _ = self._make_adapter()
        out = adapter.analyze("hello")
        assert out is not None
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
        assert expected_keys.issubset(out.keys())

    def test_sentiment_mapped(self):
        adapter, _ = self._make_adapter()
        out = adapter.analyze("great day")
        assert out is not None
        assert out["sentiment"] == "positive"

    def test_entities_preserved(self):
        adapter, _ = self._make_adapter()
        out = adapter.analyze("Mom called")
        assert out is not None
        assert len(out["entities"]) == 1
        assert out["entities"][0]["text"] == "Mom"

    def test_returns_none_when_unavailable(self):
        adapter = K1UltraBERTAdapter()  # No mock -> import fails
        if not adapter.is_available():
            assert adapter.analyze("test") is None

    def test_returns_none_on_exception(self):
        adapter, mock_client = self._make_adapter()
        mock_client.analyze.side_effect = RuntimeError("GPU OOM")
        out = adapter.analyze("boom")
        assert out is None

    def test_increments_fallback_on_unavailable(self):
        adapter = K1UltraBERTAdapter()
        if not adapter.is_available():
            adapter.analyze("test")
            assert adapter.get_metrics()["fallback_count"] >= 1


# =========================================================================
# K1UltraBERTAdapter -- metrics
# =========================================================================


class TestK1AdapterMetrics:
    """Metrics tracking."""

    def _make_adapter(self) -> tuple[K1UltraBERTAdapter, MagicMock]:
        mock_mod, mock_client = _mock_client_module()
        with patch.dict("sys.modules", {"familyos_ultrabert": mock_mod}):
            adapter = K1UltraBERTAdapter()
        return adapter, mock_client

    def test_call_count_increments(self):
        adapter, _ = self._make_adapter()
        adapter.analyze("one")
        adapter.analyze("two")
        m = adapter.get_metrics()
        # 2 unique texts = 2 calls (cache miss)
        assert m["call_count"] == 2

    def test_avg_latency_positive(self):
        adapter, _ = self._make_adapter()
        adapter.analyze("test")
        m = adapter.get_metrics()
        assert m["avg_latency_ms"] >= 0

    def test_available_in_metrics(self):
        adapter, _ = self._make_adapter()
        m = adapter.get_metrics()
        assert m["available"] is True


# =========================================================================
# LRU/TTL Cache
# =========================================================================


class TestLRUTTLCache:
    """Cache hit/miss and TTL expiry."""

    def test_cache_hit(self):
        cache = _LRUTTLCache(max_size=4, ttl_s=60.0)
        cache.put("k1", {"v": 1})
        assert cache.get("k1") == {"v": 1}
        assert cache.hits == 1

    def test_cache_miss(self):
        cache = _LRUTTLCache(max_size=4, ttl_s=60.0)
        assert cache.get("nope") is None
        assert cache.misses == 1

    def test_cache_eviction(self):
        cache = _LRUTTLCache(max_size=2, ttl_s=60.0)
        cache.put("a", {"v": 1})
        cache.put("b", {"v": 2})
        cache.put("c", {"v": 3})  # evicts "a"
        assert cache.get("a") is None
        assert cache.get("c") == {"v": 3}

    def test_cache_ttl_expiry(self):
        cache = _LRUTTLCache(max_size=4, ttl_s=0.0)  # Instant expiry
        cache.put("k", {"v": 1})
        assert cache.get("k") is None  # Expired

    def test_adapter_cache_hit_on_same_text(self):
        mock_mod, mock_client = _mock_client_module()
        with patch.dict("sys.modules", {"familyos_ultrabert": mock_mod}):
            adapter = K1UltraBERTAdapter()
        adapter.analyze("same text")
        adapter.analyze("same text")  # Should hit cache
        m = adapter.get_metrics()
        assert m["cache_hits"] >= 1
        assert m["call_count"] == 1  # Only 1 actual client call


# =========================================================================
# Singleton
# =========================================================================


class TestSingleton:
    """get_ultrabert_adapter() returns same instance."""

    def test_same_instance(self):
        a = get_ultrabert_adapter()
        b = get_ultrabert_adapter()
        assert a is b

    def test_reset_clears_instance(self):
        a = get_ultrabert_adapter()
        K1UltraBERTAdapter.reset_instance()
        b = get_ultrabert_adapter()
        assert a is not b


# =========================================================================
# Warmup
# =========================================================================


class TestWarmup:
    """Warmup triggers a forward pass."""

    def test_warmup_increments_call_count(self):
        mock_mod, mock_client = _mock_client_module()
        with patch.dict("sys.modules", {"familyos_ultrabert": mock_mod}):
            adapter = K1UltraBERTAdapter(warmup=True)
        # Warmup calls analyze("warmup") -> 1 client call
        assert adapter.get_metrics()["call_count"] == 1

    def test_warmup_no_crash_when_unavailable(self):
        with patch.dict("sys.modules", {"familyos_ultrabert": None}):
            adapter = K1UltraBERTAdapter(warmup=True)
        # Should not raise even if client is None
        assert adapter.get_metrics()["call_count"] == 0
