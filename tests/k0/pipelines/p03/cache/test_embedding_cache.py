"""Tests for P03 embedding cache.

Issue 6.4.9 - Learning batch processing optimization

Tests LRU eviction, TTL expiration, priority handling,
and K0 metrics integration.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import numpy as np
import pytest


class TestP03EmbeddingCache:
    """Test LRU embedding cache."""

    @pytest.fixture
    def metrics_exporter(self) -> MagicMock:
        """Create mock metrics exporter."""
        mock = MagicMock()
        # Mock counter returns a mock with labels method
        mock_counter = MagicMock()
        mock_counter.labels.return_value.inc = MagicMock()
        mock.counter.return_value = mock_counter
        return mock

    @pytest.fixture
    def cache(self, metrics_exporter: MagicMock):
        """Create embedding cache."""
        from k0.pipelines.p03.cache.embedding_cache import P03EmbeddingCache

        return P03EmbeddingCache(metrics_exporter, max_size=100, ttl_seconds=3600)

    @pytest.mark.asyncio
    async def test_cache_hit(self, cache) -> None:
        """Cache hit returns value and records metric."""
        embedding = np.array([1.0, 2.0, 3.0])
        await cache.set("key1", embedding)

        result = await cache.get("key1")

        assert result is not None
        np.testing.assert_array_equal(result, embedding)

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache) -> None:
        """Cache miss returns None and records metric."""
        result = await cache.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_size(self, cache) -> None:
        """Cache size tracks entries."""
        assert cache.size == 0

        await cache.set("key1", np.array([1.0]))
        assert cache.size == 1

        await cache.set("key2", np.array([2.0]))
        assert cache.size == 2

    @pytest.mark.asyncio
    async def test_lru_eviction(self, metrics_exporter: MagicMock) -> None:
        """LRU eviction when cache full."""
        from k0.pipelines.p03.cache.embedding_cache import P03EmbeddingCache

        cache = P03EmbeddingCache(metrics_exporter, max_size=2)

        await cache.set("key1", np.array([1.0]))
        await cache.set("key2", np.array([2.0]))
        await cache.set("key3", np.array([3.0]))  # Evicts key1

        assert await cache.get("key1") is None
        assert await cache.get("key2") is not None
        assert await cache.get("key3") is not None

    @pytest.mark.asyncio
    async def test_lru_order_on_access(self, metrics_exporter: MagicMock) -> None:
        """LRU order updates on access."""
        from k0.pipelines.p03.cache.embedding_cache import P03EmbeddingCache

        cache = P03EmbeddingCache(metrics_exporter, max_size=2)

        await cache.set("key1", np.array([1.0]))
        await cache.set("key2", np.array([2.0]))

        # Access key1 to move it to end
        await cache.get("key1")

        # Now key2 is oldest
        await cache.set("key3", np.array([3.0]))  # Evicts key2

        assert await cache.get("key1") is not None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is not None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, metrics_exporter: MagicMock) -> None:
        """TTL expiration removes stale entries."""
        from k0.pipelines.p03.cache.embedding_cache import CacheEntry, P03EmbeddingCache

        cache = P03EmbeddingCache(metrics_exporter, ttl_seconds=1)

        await cache.set("key1", np.array([1.0]))

        # Simulate time passing by replacing entry with old timestamp
        old_entry = cache._cache["key1"]
        cache._cache["key1"] = CacheEntry(
            value=old_entry.value,
            timestamp=time.time() - 2,  # 2 seconds ago
            priority=old_entry.priority,
        )

        result = await cache.get("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_high_priority_no_ttl(self, metrics_exporter: MagicMock) -> None:
        """HIGH priority entries don't expire."""
        from k0.pipelines.p03.cache.embedding_cache import CacheEntry, P03EmbeddingCache

        cache = P03EmbeddingCache(metrics_exporter, ttl_seconds=1)

        await cache.set("key1", np.array([1.0]), priority="HIGH")

        # Simulate time passing
        old_entry = cache._cache["key1"]
        cache._cache["key1"] = CacheEntry(
            value=old_entry.value,
            timestamp=time.time() - 2,  # 2 seconds ago
            priority="HIGH",
        )

        result = await cache.get("key1")

        assert result is not None  # HIGH priority doesn't expire

    @pytest.mark.asyncio
    async def test_low_priority_skipped(self, cache) -> None:
        """LOW priority entries not cached."""
        await cache.set("key1", np.array([1.0]), priority="LOW")

        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_medium_priority_cached(self, cache) -> None:
        """MEDIUM priority entries are cached."""
        await cache.set("key1", np.array([1.0]), priority="MEDIUM")

        assert cache.size == 1

    def test_get_priority(self, cache) -> None:
        """Priority levels map correctly."""
        assert cache.get_priority("cluster_centroids") == "HIGH"
        assert cache.get_priority("recent_patterns") == "MEDIUM"
        assert cache.get_priority("archived_patterns") == "LOW"
        assert cache.get_priority("unknown") == "MEDIUM"

    def test_clear(self, cache) -> None:
        """Clear removes all entries."""
        asyncio.run(cache.set("key1", np.array([1.0])))
        asyncio.run(cache.set("key2", np.array([2.0])))

        cache.clear()

        assert cache.size == 0

    def test_get_stats(self, cache) -> None:
        """Get stats returns correct values."""
        stats = cache.get_stats()

        assert stats["size"] == 0
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 3600
        assert stats["pipeline_id"] == "p03_consolidation"


class TestP03CachePriorities:
    """Test cache priority constants."""

    def test_priorities_defined(self) -> None:
        """All priority levels defined."""
        from k0.pipelines.p03.cache.embedding_cache import P03_CACHE_PRIORITIES

        assert "cluster_centroids" in P03_CACHE_PRIORITIES
        assert "recent_patterns" in P03_CACHE_PRIORITIES
        assert "archived_patterns" in P03_CACHE_PRIORITIES

    def test_priority_values(self) -> None:
        """Priority values are HIGH/MEDIUM/LOW."""
        from k0.pipelines.p03.cache.embedding_cache import P03_CACHE_PRIORITIES

        assert P03_CACHE_PRIORITIES["cluster_centroids"] == "HIGH"
        assert P03_CACHE_PRIORITIES["recent_patterns"] == "MEDIUM"
        assert P03_CACHE_PRIORITIES["archived_patterns"] == "LOW"


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_cache_entry_frozen(self) -> None:
        """CacheEntry is immutable."""
        from k0.pipelines.p03.cache.embedding_cache import CacheEntry

        entry = CacheEntry(
            value=np.array([1.0]),
            timestamp=time.time(),
            priority="MEDIUM",
        )

        with pytest.raises(AttributeError):
            entry.priority = "HIGH"

    def test_cache_entry_slots(self) -> None:
        """CacheEntry uses slots for memory efficiency."""
        from k0.pipelines.p03.cache.embedding_cache import CacheEntry

        entry = CacheEntry(
            value=np.array([1.0]),
            timestamp=time.time(),
            priority="MEDIUM",
        )

        assert hasattr(entry, "__slots__")


class TestMetricsIntegration:
    """Test K0 metrics integration."""

    def test_counter_registered(self) -> None:
        """Counters registered on init."""
        from k0.pipelines.p03.cache.embedding_cache import P03EmbeddingCache

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()

        P03EmbeddingCache(mock_metrics)

        # 4 counters should be registered
        assert mock_metrics.counter.call_count == 4

    def test_counter_names(self) -> None:
        """Counter names match spec."""
        from k0.pipelines.p03.cache.embedding_cache import P03EmbeddingCache

        mock_metrics = MagicMock()
        mock_metrics.counter.return_value = MagicMock()

        P03EmbeddingCache(mock_metrics)

        counter_names = [call[1]["name"] for call in mock_metrics.counter.call_args_list]
        assert "p03_embedding_cache_hit" in counter_names
        assert "p03_embedding_cache_miss" in counter_names
        assert "p03_embedding_cache_eviction" in counter_names
        assert "p03_embedding_cache_expired" in counter_names
