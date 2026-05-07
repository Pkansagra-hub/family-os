"""M4 Resilience & Cost -- Test ResponseCache [F47].

Tests LRU response cache with TTL, capability-aware keying, skip rules,
and cache statistics.

Covers:
  - CacheResult: construction, frozen
  - build_cache_key: deterministic, unique for different inputs
  - should_cache: skip rules (TOOL_CALL, BATCH, MODERATE, high temp, streaming)
  - get / put: hit, miss, TTL expiry, LRU eviction, move-to-end
  - invalidate / clear
  - Stats: size, total_hits, total_misses, hit_rate
  - Re-exports from services/__init__.py
"""

from __future__ import annotations

import time

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.services.response_cache import CacheResult, ResponseCache
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    HubRequest,
    HubResponse,
    Message,
    RequestConstraints,
    ResponseMetadata,
    TokenUsage,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_config(
    cache_max_entries: int = 100,
    cache_ttl_s: int = 300,
) -> ModelHubConfig:
    return ModelHubConfig(
        cache_max_entries=cache_max_entries,
        cache_ttl_s=cache_ttl_s,
    )


def _make_response(result: str = "hello") -> HubResponse:
    return HubResponse(
        result=result,
        metadata=ResponseMetadata(
            request_id="r-1",
            model_id="gpt-4o",
            provider_id="openai",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost_usd=0.01,
            latency_ms=100,
            cache_hit=False,
            capability=CapabilityType.CHAT,
            trace_id="t-1",
        ),
    )


def _make_request(
    capability: CapabilityType = CapabilityType.CHAT,
    temperature: float = 0.7,
) -> HubRequest:
    return HubRequest(
        capability=capability,
        payload=ChatPayload(messages=[Message(role="user", content="hi")]),
        trace_id="t-1",
        constraints=RequestConstraints(temperature=temperature),
    )


@pytest.fixture
def cache() -> ResponseCache:
    return ResponseCache(_make_config())


@pytest.fixture
def small_cache() -> ResponseCache:
    return ResponseCache(_make_config(cache_max_entries=3, cache_ttl_s=300))


# ===========================================================================
# CacheResult Tests
# ===========================================================================


class TestCacheResult:
    def test_miss(self) -> None:
        r = CacheResult(hit=False)
        assert r.hit is False
        assert r.response is None
        assert r.cache_key == ""
        assert r.age_ms == 0

    def test_hit(self) -> None:
        resp = _make_response()
        r = CacheResult(hit=True, response=resp, cache_key="abc", age_ms=500)
        assert r.hit is True
        assert r.response is resp

    def test_frozen(self) -> None:
        r = CacheResult(hit=False)
        with pytest.raises(AttributeError):
            r.hit = True  # type: ignore[misc]


# ===========================================================================
# build_cache_key Tests
# ===========================================================================


class TestBuildCacheKey:
    def test_deterministic(self) -> None:
        k1 = ResponseCache.build_cache_key(CapabilityType.CHAT, "payload", "m1", 0.7)
        k2 = ResponseCache.build_cache_key(CapabilityType.CHAT, "payload", "m1", 0.7)
        assert k1 == k2

    def test_different_capability(self) -> None:
        k1 = ResponseCache.build_cache_key(CapabilityType.CHAT, "p", "m1", 0.7)
        k2 = ResponseCache.build_cache_key(CapabilityType.EMBED, "p", "m1", 0.7)
        assert k1 != k2

    def test_different_payload(self) -> None:
        k1 = ResponseCache.build_cache_key(CapabilityType.CHAT, "a", "m1", 0.7)
        k2 = ResponseCache.build_cache_key(CapabilityType.CHAT, "b", "m1", 0.7)
        assert k1 != k2

    def test_different_model(self) -> None:
        k1 = ResponseCache.build_cache_key(CapabilityType.CHAT, "p", "m1", 0.7)
        k2 = ResponseCache.build_cache_key(CapabilityType.CHAT, "p", "m2", 0.7)
        assert k1 != k2

    def test_different_temperature(self) -> None:
        k1 = ResponseCache.build_cache_key(CapabilityType.CHAT, "p", "m1", 0.5)
        k2 = ResponseCache.build_cache_key(CapabilityType.CHAT, "p", "m1", 0.9)
        assert k1 != k2

    def test_returns_hex_string(self) -> None:
        k = ResponseCache.build_cache_key(CapabilityType.CHAT, "p", "m1", 0.7)
        assert len(k) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in k)


# ===========================================================================
# should_cache Tests (MH-09 skip rules)
# ===========================================================================


class TestShouldCache:
    def test_chat_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(CapabilityType.CHAT)) is True

    def test_embed_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(CapabilityType.EMBED)) is True

    def test_tool_call_not_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(CapabilityType.TOOL_CALL)) is False

    def test_batch_not_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(CapabilityType.BATCH)) is False

    def test_moderate_not_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(CapabilityType.MODERATE)) is False

    def test_high_temperature_not_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(temperature=1.0)) is False

    def test_boundary_temperature_cacheable(self) -> None:
        """temperature=0.9 is at the threshold, should still be cacheable."""
        assert ResponseCache.should_cache(_make_request(temperature=0.9)) is True

    def test_streaming_not_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(), streaming=True) is False

    def test_streaming_false_cacheable(self) -> None:
        assert ResponseCache.should_cache(_make_request(), streaming=False) is True


# ===========================================================================
# get / put Tests
# ===========================================================================


class TestGetPut:
    def test_miss_on_empty_cache(self, cache: ResponseCache) -> None:
        result = cache.get("nonexistent")
        assert result.hit is False

    def test_put_and_get_hit(self, cache: ResponseCache) -> None:
        resp = _make_response()
        cache.put("k1", resp)
        result = cache.get("k1")
        assert result.hit is True
        assert result.response is resp
        assert result.cache_key == "k1"

    def test_get_returns_age_ms(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response())
        result = cache.get("k1")
        assert result.age_ms >= 0

    def test_put_overwrites_existing(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response("first"))
        cache.put("k1", _make_response("second"))
        result = cache.get("k1")
        assert result.response.result == "second"

    def test_ttl_expiry(self, cache: ResponseCache) -> None:
        """Expired entries should be evicted on access."""
        cache.put("k1", _make_response(), ttl_s=10)

        # Within TTL -- shift created_at back 5s
        entry = cache._cache["k1"]
        entry.created_at = time.monotonic() - 5
        result = cache.get("k1")
        assert result.hit is True

        # After TTL -- shift created_at back 10s
        entry = cache._cache["k1"]
        entry.created_at = time.monotonic() - 10
        result = cache.get("k1")
        assert result.hit is False

    def test_custom_ttl(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response(), ttl_s=5)

        # Shift created_at back past TTL
        entry = cache._cache["k1"]
        entry.created_at = time.monotonic() - 5
        result = cache.get("k1")
        assert result.hit is False


# ===========================================================================
# LRU Eviction Tests
# ===========================================================================


class TestLRUEviction:
    def test_eviction_at_capacity(self, small_cache: ResponseCache) -> None:
        """When cache is full, oldest entry is evicted."""
        small_cache.put("k1", _make_response("first"))
        small_cache.put("k2", _make_response("second"))
        small_cache.put("k3", _make_response("third"))

        # Cache full (max 3), adding k4 should evict k1
        small_cache.put("k4", _make_response("fourth"))

        assert small_cache.get("k1").hit is False
        assert small_cache.get("k4").hit is True

    def test_lru_move_to_end_on_hit(self, small_cache: ResponseCache) -> None:
        """Accessing an entry moves it to end, preventing eviction."""
        small_cache.put("k1", _make_response("first"))
        small_cache.put("k2", _make_response("second"))
        small_cache.put("k3", _make_response("third"))

        # Access k1 (moves to end)
        small_cache.get("k1")

        # Add k4 -> should evict k2 (now oldest), not k1
        small_cache.put("k4", _make_response("fourth"))

        assert small_cache.get("k1").hit is True  # Still present
        assert small_cache.get("k2").hit is False  # Evicted

    def test_size_never_exceeds_max(self, small_cache: ResponseCache) -> None:
        for i in range(10):
            small_cache.put(f"k{i}", _make_response(f"v{i}"))
        assert small_cache.size <= 3


# ===========================================================================
# invalidate / clear Tests
# ===========================================================================


class TestInvalidateClear:
    def test_invalidate_existing(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response())
        assert cache.invalidate("k1") is True
        assert cache.get("k1").hit is False

    def test_invalidate_nonexistent(self, cache: ResponseCache) -> None:
        assert cache.invalidate("nonexistent") is False

    def test_clear(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response())
        cache.put("k2", _make_response())
        cache.clear()
        assert cache.size == 0
        assert cache.get("k1").hit is False


# ===========================================================================
# Stats Tests
# ===========================================================================


class TestStats:
    def test_size(self, cache: ResponseCache) -> None:
        assert cache.size == 0
        cache.put("k1", _make_response())
        assert cache.size == 1

    def test_max_entries(self, cache: ResponseCache) -> None:
        assert cache.max_entries == 100

    def test_hit_miss_counts(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response())
        cache.get("k1")  # hit
        cache.get("k2")  # miss
        assert cache.total_hits == 1
        assert cache.total_misses == 1

    def test_hit_rate_empty(self, cache: ResponseCache) -> None:
        assert cache.hit_rate == 0.0

    def test_hit_rate_all_hits(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response())
        cache.get("k1")
        assert cache.hit_rate == 1.0

    def test_hit_rate_mixed(self, cache: ResponseCache) -> None:
        cache.put("k1", _make_response())
        cache.get("k1")  # hit
        cache.get("k2")  # miss
        cache.get("k3")  # miss
        assert cache.hit_rate == pytest.approx(1 / 3)


# ===========================================================================
# Re-exports
# ===========================================================================


class TestResponseCacheReExports:
    def test_response_cache_reexport(self) -> None:
        from k1.model_hub.services import ResponseCache as Reexported

        assert Reexported is ResponseCache

    def test_cache_result_reexport(self) -> None:
        from k1.model_hub.services import CacheResult as Reexported

        assert Reexported is CacheResult
