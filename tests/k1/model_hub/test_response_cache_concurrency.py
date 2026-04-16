"""
I-0.5.8.2 -- ResponseCache concurrency stress tests.

Validates that ResponseCache is thread-safe under concurrent access:
  - 100 concurrent get/put operations with no KeyError or corruption
  - Mixed read/write workload across threads
  - Eviction under contention
  - Stats consistency after concurrent operations
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock

from k1.model_hub.services.response_cache import ResponseCache
from k1.model_hub.types import (
    CapabilityType,
    ChatResult,
    FinishReason,
    HubResponse,
    ResponseMetadata,
    TokenUsage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(max_entries: int = 100, ttl_s: int = 300) -> MagicMock:
    cfg = MagicMock()
    cfg.cache_max_entries = max_entries
    cfg.cache_ttl_s = ttl_s
    return cfg


def _make_response(text: str = "cached") -> HubResponse:
    return HubResponse(
        result=ChatResult(text=text),
        metadata=ResponseMetadata(
            request_id="r1",
            model_id="m1",
            provider_id="p1",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
            cost_usd=0.0,
            latency_ms=10,
            cache_hit=False,
            capability=CapabilityType.CHAT,
            trace_id="t1",
            finish_reason=FinishReason.STOP,
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConcurrentGetPut:
    """100 concurrent get/put operations must not raise or corrupt data."""

    def test_100_concurrent_puts_no_error(self) -> None:
        """100 threads each putting a unique key -- no exception."""
        cache = ResponseCache(_make_config(max_entries=200))
        errors: list[str] = []

        def _put(i: int) -> None:
            try:
                cache.put(f"key-{i}", _make_response(f"val-{i}"))
            except Exception as exc:
                errors.append(f"put({i}): {exc}")

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_put, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Errors during concurrent puts: {errors}"
        assert cache.size == 100

    def test_100_concurrent_gets_no_error(self) -> None:
        """100 threads reading from pre-populated cache -- no exception."""
        cache = ResponseCache(_make_config(max_entries=200))
        for i in range(50):
            cache.put(f"key-{i}", _make_response(f"val-{i}"))

        errors: list[str] = []

        def _get(i: int) -> None:
            try:
                cache.get(f"key-{i % 50}")
            except Exception as exc:
                errors.append(f"get({i}): {exc}")

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_get, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Errors during concurrent gets: {errors}"

    def test_mixed_read_write_no_corruption(self) -> None:
        """50 writers + 50 readers running simultaneously -- no corruption."""
        cache = ResponseCache(_make_config(max_entries=200))
        errors: list[str] = []
        barrier = threading.Barrier(100)

        def _writer(i: int) -> None:
            barrier.wait()
            try:
                cache.put(f"key-{i}", _make_response(f"val-{i}"))
            except Exception as exc:
                errors.append(f"write({i}): {exc}")

        def _reader(i: int) -> None:
            barrier.wait()
            try:
                result = cache.get(f"key-{i % 50}")
                # Result should be either hit or miss, never error
                assert isinstance(result.hit, bool)
            except Exception as exc:
                errors.append(f"read({i}): {exc}")

        with ThreadPoolExecutor(max_workers=100) as pool:
            futures = []
            for i in range(50):
                futures.append(pool.submit(_writer, i))
            for i in range(50):
                futures.append(pool.submit(_reader, i))
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Errors during mixed workload: {errors}"

    def test_eviction_under_contention(self) -> None:
        """Cache with max_entries=10, 100 concurrent puts triggers eviction safely."""
        cache = ResponseCache(_make_config(max_entries=10))
        errors: list[str] = []

        def _put(i: int) -> None:
            try:
                cache.put(f"key-{i}", _make_response(f"val-{i}"))
            except Exception as exc:
                errors.append(f"put({i}): {exc}")

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_put, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Errors during eviction contention: {errors}"
        assert cache.size <= 10, f"Cache size {cache.size} exceeds max 10"

    def test_concurrent_invalidate_no_error(self) -> None:
        """Concurrent invalidations do not raise KeyError."""
        cache = ResponseCache(_make_config(max_entries=200))
        for i in range(50):
            cache.put(f"key-{i}", _make_response(f"val-{i}"))

        errors: list[str] = []

        def _invalidate(i: int) -> None:
            try:
                cache.invalidate(f"key-{i % 50}")
            except Exception as exc:
                errors.append(f"invalidate({i}): {exc}")

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_invalidate, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Errors during concurrent invalidate: {errors}"

    def test_stats_consistency_after_concurrent_ops(self) -> None:
        """total_hits + total_misses == total get() calls after concurrency."""
        cache = ResponseCache(_make_config(max_entries=200))
        # Pre-populate half the keys
        for i in range(50):
            cache.put(f"key-{i}", _make_response(f"val-{i}"))

        n_gets = 200

        def _get(i: int) -> None:
            cache.get(f"key-{i % 100}")  # half hit, half miss

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_get, i) for i in range(n_gets)]
            for f in as_completed(futures):
                f.result()

        assert (
            cache.total_hits + cache.total_misses == n_gets
        ), f"hits({cache.total_hits}) + misses({cache.total_misses}) != {n_gets}"

    def test_concurrent_clear_with_readers(self) -> None:
        """clear() during concurrent reads does not raise."""
        cache = ResponseCache(_make_config(max_entries=200))
        for i in range(50):
            cache.put(f"key-{i}", _make_response(f"val-{i}"))

        errors: list[str] = []
        barrier = threading.Barrier(21)

        def _reader(i: int) -> None:
            barrier.wait()
            try:
                for j in range(10):
                    cache.get(f"key-{(i * 10 + j) % 50}")
            except Exception as exc:
                errors.append(f"read({i}): {exc}")

        def _clearer() -> None:
            barrier.wait()
            try:
                cache.clear()
            except Exception as exc:
                errors.append(f"clear: {exc}")

        with ThreadPoolExecutor(max_workers=21) as pool:
            futures = [pool.submit(_reader, i) for i in range(20)]
            futures.append(pool.submit(_clearer))
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Errors during clear+read: {errors}"

    def test_lock_attribute_exists(self) -> None:
        """ResponseCache must have a threading.Lock instance."""
        cache = ResponseCache(_make_config())
        assert hasattr(cache, "_lock")
        assert isinstance(cache._lock, type(threading.Lock()))
