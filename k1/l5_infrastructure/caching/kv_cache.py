"""
KV Cache - Main Key-Value Cache Interface

Layer: L5 Infrastructure
Component: Caching
Priority: 🔴 CRITICAL (Core caching abstraction)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0028d: Local In-Memory Cache with K0 Persistence

KV Cache Philosophy:
    - Abstract key-value storage interface
    - Multiple implementations: local, persistent, distributed
    - Async operations with sub-millisecond performance
    - TTL support with background cleanup
    - Thread-safe with asyncio.Lock

Interface Design:
    - get(key) -> value or None
    - set(key, value, ttl_seconds) -> None
    - delete(key) -> None
    - exists(key) -> bool
    - clear() -> None
    - get_statistics() -> dict

Implementations:
    - LocalKVCache: Pure in-memory (extends InMemoryCache)
    - PersistentCache: In-memory + K0 persistence
    - DistributedKVCache: Redis/memcached backend (future)

Performance Budgets:
    - get(): <0.1ms P95
    - set(): <0.1ms P95
    - exists(): <0.05ms P95
    - delete(): <0.05ms P95

Dependencies:
    Internal:
        - None (abstract interface)
    External:
        - typing (type hints)

Connects To:
    Upstream:
        - k1.l5_infrastructure.caching.persistent_cache (uses LocalKVCache)
        - k1.l5_infrastructure.caching.cache_integration (uses PersistentCache)
    Downstream:
        - k1.l5_infrastructure.caching.kv_cache_local (LocalKVCache implementation)
        - k1.l5_infrastructure.caching.persistent_cache (PersistentCache implementation)

Observability:
    - Metrics: k1_kv_cache_operations_total{operation, result}
    - Metrics: k1_kv_cache_operation_duration_seconds{operation}
    - Traces: Span kv_cache.get, kv_cache.set
    - Logs: DEBUG cache hit/miss, INFO cache cleared

References:
    - Whiteboard: docs/whiteboard.md (Section: KV Caching)
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 9, Epic 9.1)
    - Test: tests/k1/l5_infrastructure/caching/test_kv_cache.py
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 1: ABSTRACT KV CACHE INTERFACE
# =============================================================================


class KVCache(ABC):
    """
    Abstract Key-Value Cache Interface

    Defines the contract for all KV cache implementations.
    Provides async operations with TTL support and statistics.

    Thread Safety: Implementation-dependent (LocalKVCache uses asyncio.Lock)
    Async Safe: Yes

    Examples:
        >>> cache = LocalKVCache(max_size=10000)
        >>> await cache.start()
        >>> await cache.set("key", "value", ttl_seconds=300)
        >>> value = await cache.get("key")
        >>> print(value)
        'value'
        >>> await cache.stop()

    References:
        - ADR-0028d: Local In-Memory Cache with K0 Persistence
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start the cache (initialize background tasks, connections, etc.)

        Side Effects:
            - Starts background cleanup coroutine
            - Initializes metrics tracking
            - Logs cache startup

        Performance:
            - <1ms (task creation)

        ADR: ADR-0028d (Cache Lifecycle)
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the cache (cleanup background tasks, connections, etc.)

        Side Effects:
            - Cancels background cleanup task
            - Closes connections (if applicable)
            - Logs cache shutdown

        Performance:
            - <1ms (task cancellation)

        ADR: ADR-0028d (Cache Lifecycle)
        """
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value by key (with expiration check).

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise

        Behavior:
            1. Check if key exists in cache
            2. If exists: Check TTL, return value or None if expired
            3. If not exists: Return None
            4. Update hit/miss statistics

        Performance:
            - <0.1ms P95 (dict lookup + expiration check)

        ADR: ADR-0028d (Cache Get)
        """
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Store value with optional TTL.

        Args:
            key: Cache key
            value: Value to cache (any type)
            ttl_seconds: Time-to-live in seconds (optional)

        Behavior:
            1. Store (value, expire_time) in cache
            2. Handle LRU eviction if capacity exceeded
            3. Update statistics

        Performance:
            - <0.1ms P95 (dict insert + LRU eviction)

        ADR: ADR-0028d (Cache Set)
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Delete key immediately.

        Args:
            key: Cache key

        Behavior:
            - Remove key if exists
            - Update statistics

        Performance:
            - <0.05ms P95 (dict removal)

        ADR: ADR-0028d (Cache Delete)
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check key existence and validity.

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired, False otherwise

        Performance:
            - <0.05ms P95 (dict lookup + expiration check)

        ADR: ADR-0028d (Cache Exists)
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """
        Clear all cache entries.

        Side Effects:
            - Removes all keys
            - Resets cumulative statistics
            - Logs clear operation

        Performance:
            - <2ms P95 for 10000 entries

        ADR: ADR-0028d (Cache Clear)
        """
        pass

    @abstractmethod
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            {
                "hits": int,
                "misses": int,
                "entries_count": int,
                "hit_rate_pct": float,
                "max_size": int,
                # Implementation-specific fields...
            }

        Performance:
            - <0.1ms (simple aggregation)

        ADR: ADR-0028d (Cache Statistics)
        """
        pass


# =============================================================================
# SECTION 2: MODULE EXPORTS
# =============================================================================

__all__ = [
    "KVCache",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Prometheus Metrics Exported (by implementations):
#
# Counters:
#   - k1_kv_cache_operations_total{operation, result} (get/set/delete/exists/clear, success/error)
#
# Histograms:
#   - k1_kv_cache_operation_duration_seconds{operation} (get/set/delete/exists/clear)
#
# Gauges:
#   - k1_kv_cache_entries_count (current entries)
#   - k1_kv_cache_hit_rate_pct (rolling hit rate)
#
# Example Prometheus Queries:
#   - Hit rate: k1_kv_cache_operations_total{operation="get", result="hit"} / k1_kv_cache_operations_total{operation="get"}
#   - Operation latency P95: histogram_quantile(0.95, k1_kv_cache_operation_duration_seconds_bucket{operation="get"})
#   - Cache size: k1_kv_cache_entries_count
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Interface tests required:
#   - tests/k1/l5_infrastructure/caching/test_kv_cache.py
#   - Test interface compliance (all abstract methods implemented)
#   - Test async safety (concurrent operations)
#   - Test TTL behavior (expiration)
#   - Test statistics accuracy
#   - Test error handling
#
# Implementation tests in respective files:
#   - test_kv_cache_local.py (LocalKVCache)
#   - test_persistent_cache.py (PersistentCache)
#
# No simulation code allowed:
#   - Use real asyncio with ward fixtures
#   - Test actual TTL expiration with time.time()
#   - Integration tests > unit tests
#
# =============================================================================
