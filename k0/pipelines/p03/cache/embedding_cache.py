"""
P03 LRU embedding cache with K0 metrics.

Caches embeddings to reduce pgvector query load.
Reports hit/miss/eviction metrics to K0.

Dossier Reference: Section 15.6.2 Embedding Caching with K0 Metrics
K0 Reference: k0/obs/metrics.py: MetricsExporter.counter()

Issue 6.4.9 - Learning batch processing optimization
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from prometheus_client import Counter

    from k0.obs.metrics import MetricsExporter


# Cache priority levels from dossier Section 15.6.2
P03_CACHE_PRIORITIES: dict[str, str] = {
    "cluster_centroids": "HIGH",  # Always cache
    "recent_patterns": "MEDIUM",  # Cache for 1 hour
    "archived_patterns": "LOW",  # Don't cache
}


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cache entry with timestamp and priority."""

    value: np.ndarray
    timestamp: float
    priority: str


class P03EmbeddingCache:
    """
    LRU cache for embeddings with K0 metrics.

    Implements LRU eviction with TTL expiration.
    Reports cache metrics to K0 MetricsExporter.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for hit/miss

    Attributes:
        metrics: K0 MetricsExporter instance
        max_size: Maximum cache entries
        ttl_seconds: TTL in seconds (default 1 hour)
        pipeline_id: Pipeline identifier for labels
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        max_size: int = 10000,
        ttl_seconds: int = 3600,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize embedding cache.

        Args:
            metrics: K0 MetricsExporter instance
            max_size: Maximum cache entries
            ttl_seconds: TTL in seconds (default 1 hour)
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.pipeline_id = pipeline_id

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # K0 metrics
        self._hit_counter: Counter = metrics.counter(
            name="p03_embedding_cache_hit",
            description="Cache hits",
            labelnames=["cache", "pipeline_id"],
        )
        self._miss_counter: Counter = metrics.counter(
            name="p03_embedding_cache_miss",
            description="Cache misses",
            labelnames=["cache", "pipeline_id"],
        )
        self._eviction_counter: Counter = metrics.counter(
            name="p03_embedding_cache_eviction",
            description="LRU evictions",
            labelnames=["cache", "pipeline_id"],
        )
        self._expired_counter: Counter = metrics.counter(
            name="p03_embedding_cache_expired",
            description="TTL expirations",
            labelnames=["cache", "pipeline_id"],
        )

    async def get(self, key: str) -> np.ndarray | None:
        """
        Get embedding from cache with K0 metrics.

        Args:
            key: Cache key

        Returns:
            Embedding array or None if miss/expired
        """
        if key not in self._cache:
            self._miss_counter.labels(
                cache="embedding",
                pipeline_id=self.pipeline_id,
            ).inc()
            return None

        entry = self._cache[key]

        # Check TTL (except HIGH priority)
        if entry.priority != "HIGH" and self._is_expired(entry):
            del self._cache[key]
            self._expired_counter.labels(
                cache="embedding",
                pipeline_id=self.pipeline_id,
            ).inc()
            return None

        # Hit - move to end for LRU
        self._cache.move_to_end(key)
        self._hit_counter.labels(
            cache="embedding",
            pipeline_id=self.pipeline_id,
        ).inc()

        return entry.value

    async def set(
        self,
        key: str,
        value: np.ndarray,
        priority: str = "MEDIUM",
    ) -> None:
        """
        Set embedding in cache.

        Args:
            key: Cache key
            value: Embedding array
            priority: Cache priority (HIGH/MEDIUM/LOW)
        """
        # Skip LOW priority
        if priority == "LOW":
            return

        # Evict if full
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._eviction_counter.labels(
                cache="embedding",
                pipeline_id=self.pipeline_id,
            ).inc()

        self._cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            priority=priority,
        )

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if entry is expired."""
        age = time.time() - entry.timestamp
        return age > self.ttl_seconds

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Current cache size."""
        return len(self._cache)

    def get_priority(self, pattern_type: str) -> str:
        """
        Get cache priority for pattern type.

        Args:
            pattern_type: Type of pattern

        Returns:
            Priority level
        """
        return P03_CACHE_PRIORITIES.get(pattern_type, "MEDIUM")

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with size, max_size, ttl_seconds
        """
        return {
            "size": self.size,
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "pipeline_id": self.pipeline_id,
        }
