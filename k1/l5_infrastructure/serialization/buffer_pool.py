"""
Buffer Pool - Reusable Buffer Management for FlatBuffers Serialization

Layer: L5 Infrastructure
Component: Serialization (Memory Management)
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0011c: Serialization Performance & Zero-Copy
      * Buffer pooling for allocation reuse (1.4× speedup, 200× fewer allocations)
      * Thread-local pool management (avoid lock contention)
      * 5 size classes (256B, 1KB, 4KB, 16KB, 64KB) for efficient memory usage
      * Section: "Buffer Pooling" (Per-Thread Buffer Pools, Pool Eviction Policy)
      * Performance: Hit rate target >80%, speedup 1.4× vs allocation

Dependencies:
    Internal:
        None (lowest-level memory management)

    External:
        - threading (thread-local storage)
        - collections (deque for LRU eviction)
        - typing (type hints)

Connects To:
    Used By:
        - k1.l5_infrastructure.serialization.serializer.Serializer (buffer acquisition)
        - k1.l5_infrastructure.serialization.serializer.get_builder (builder pooling)

Performance Budgets:
    - Buffer acquisition (hit): <0.1ms P95
    - Buffer acquisition (miss): <1ms P95 (allocation overhead)
    - Buffer release: <0.1ms P95
    - Hit rate target: >80% (buffer reuse)
    - Speedup vs allocation: 1.4× (average hit+miss)

Observability:
    - Metrics:
        * k1_buffer_pool_acquire_total{size_class, result} (counter: hit/miss)
        * k1_buffer_pool_hit_rate{size_class} (gauge: hit rate 0.0-1.0)
        * k1_buffer_pool_memory_bytes{size_class} (gauge: total memory in pool)
        * k1_buffer_pool_evictions_total{size_class} (counter: LRU evictions)

    - Logs:
        * DEBUG: buffer_acquired (size_class, result, pool_depth)
        * DEBUG: buffer_released (size_class, pool_depth)
        * WARNING: pool_full_eviction (size_class, evicted_count)
        * INFO: pool_stats (hit_rate, total_memory, evictions)

References:
    - ADR-0011c: Serialization Performance & Zero-Copy (Buffer Pooling section)
    - Test: tests/k1/l5_infrastructure/serialization/test_buffer_pool.py
"""

import logging
import threading
from collections import deque

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Size classes (powers of 2)
SIZE_CLASSES = [256, 1024, 4096, 16384, 65536]

# Maximum buffers per size class
MAX_BUFFERS_PER_CLASS = {
    256: 100,  # 25KB total
    1024: 100,  # 100KB total
    4096: 100,  # 400KB total
    16384: 50,  # 800KB total
    65536: 20,  # 1.2MB total
}

# Total pool memory limit (across all size classes)
MAX_TOTAL_POOL_MEMORY = 2621440  # 2.5MB


# =============================================================================
# SECTION 3: BUFFER POOL CLASS
# =============================================================================


class BufferPool:
    """
    Thread-local reusable buffer pool for FlatBuffers serialization

    Purpose:
        Reduce allocation overhead by reusing buffers across multiple
        serialization operations. Uses 5 size classes with LRU eviction.

    Size Classes (Powers of 2):
        - 256B: Small events, metadata (100 buffers max = 25KB)
        - 1KB: TaskAnnouncement, tool results (100 buffers max = 100KB)
        - 4KB: AgentState, intermediate deltas (100 buffers max = 400KB)
        - 16KB: Medium SessionState (50 buffers max = 800KB)
        - 64KB: Full SessionState snapshots (20 buffers max = 1.2MB)

    Benefits:
        - Reduces allocation overhead (malloc/free)
        - Improves locality (warm cache)
        - Reduces GC pressure (fewer allocations)
        - 1.4× speedup vs allocating new buffers

    Thread Safety:
        Thread-local storage (no locks required)

    Eviction Policy:
        LRU (Least Recently Used) when pool exceeds capacity

    Performance Targets (from ADR-0011c):
        - Hit rate: >80% (buffer reuse)
        - Speedup: 1.4× vs allocation
        - GC reduction: 7.5× fewer pauses

    ADR-0011c: Buffer pooling optimization (Section "Buffer Pooling")
    """

    def __init__(self):
        """
        Initialize buffer pool with thread-local storage

        TODO(@infrastructure-team): Initialize buffer pool
        Assigned to: Issue #L5-3.2.1

        Steps:
            1. Create thread-local storage
            2. Initialize 5 size class pools (as deques for LRU)
            3. Initialize stats (hits, misses, evictions)
            4. Log pool initialization
        """
        # Thread-local storage for pools
        self._local = threading.local()

        # Stats (global, aggregated across threads)
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0

        logger.info("buffer_pool_initialized", size_classes=SIZE_CLASSES)

    def _ensure_local_pools(self) -> None:
        """
        Ensure thread-local pools are initialized

        Called on first access from each thread to initialize
        thread-local storage.

        TODO(@infrastructure-team): Initialize thread-local pools
        Assigned to: Issue #L5-3.2.1
        """
        if not hasattr(self._local, "pools"):
            # Initialize pools (one deque per size class)
            self._local.pools: Dict[int, deque] = {
                size_class: deque(maxlen=MAX_BUFFERS_PER_CLASS[size_class])
                for size_class in SIZE_CLASSES
            }

            # Initialize per-thread stats
            self._local.hits = 0
            self._local.misses = 0
            self._local.evictions = 0
            self._local.total_memory = 0

    def _find_size_class(self, size: int) -> int:
        """
        Find appropriate size class for requested size

        Args:
            size: Requested buffer size in bytes

        Returns:
            Size class (power of 2) that fits requested size

        Example:
            _find_size_class(500) → 1024 (1KB)
            _find_size_class(3000) → 4096 (4KB)
            _find_size_class(70000) → 65536 (64KB)

        TODO(@infrastructure-team): Implement size class lookup
        Assigned to: Issue #L5-3.2.1
        """
        for size_class in SIZE_CLASSES:
            if size <= size_class:
                return size_class

        # If size exceeds largest class, return largest class
        return SIZE_CLASSES[-1]

    def acquire(self, size: int) -> bytearray:
        """
        Acquire buffer from pool or allocate new

        Args:
            size: Minimum buffer size in bytes

        Returns:
            Bytearray ready for use (zeroed if from pool, empty if new)

        Performance:
            - Hit (from pool): <0.1ms P95 (deque pop)
            - Miss (allocate): <1ms P95 (allocation overhead)
            - Average speedup: 1.4× faster (hit vs miss)

        Usage:
            # Acquire 1KB buffer for TaskAnnouncement
            buffer = pool.acquire(1024)
            # ... use buffer for serialization ...
            pool.release(buffer)

        ADR-0011c: Buffer acquisition with hit/miss tracking

        TODO(@infrastructure-team): Implement buffer acquisition
        Assigned to: Issue #L5-3.2.1

        Steps:
            1. Ensure thread-local pools initialized
            2. Find appropriate size class
            3. Try to pop from pool (hit)
            4. If empty, allocate new (miss)
            5. Update stats (hits/misses)
            6. Return buffer
        """
        self._ensure_local_pools()

        # Find size class
        size_class = self._find_size_class(size)

        # Try to acquire from pool (hit)
        pool = self._local.pools[size_class]
        if pool:
            buffer = pool.pop()
            self._local.hits += 1
            self._total_hits += 1

            logger.debug(
                "buffer_acquired_hit",
                size_class=size_class,
                pool_depth=len(pool),
            )

            return buffer

        # Allocate new (miss)
        buffer = bytearray(size_class)
        self._local.misses += 1
        self._total_misses += 1

        logger.debug(
            "buffer_acquired_miss",
            size_class=size_class,
            allocated=True,
        )

        return buffer

    def release(self, buffer: bytearray) -> None:
        """
        Return buffer to pool for reuse

        Args:
            buffer: Buffer to return

        Side Effects:
            - Adds buffer to appropriate pool
            - May trigger LRU eviction if pool full
            - Clears buffer contents (for security)

        Performance:
            - Release overhead: <0.1ms P95 (deque append)
            - Eviction overhead: <0.1ms P95 (deque auto-eviction)

        Usage:
            buffer = pool.acquire(1024)
            # ... use buffer ...
            pool.release(buffer)  # Return to pool

        ADR-0011c: Buffer release with LRU eviction

        TODO(@infrastructure-team): Implement buffer release
        Assigned to: Issue #L5-3.2.1

        Steps:
            1. Ensure thread-local pools initialized
            2. Determine size class from buffer length
            3. Clear buffer contents (security)
            4. Add to pool (deque handles LRU eviction automatically)
            5. If eviction occurred, update stats
        """
        self._ensure_local_pools()

        # Determine size class
        size_class = self._find_size_class(len(buffer))

        # Clear buffer (security: zero out sensitive data)
        for i in range(len(buffer)):
            buffer[i] = 0

        # Add to pool (deque auto-evicts if full)
        pool = self._local.pools[size_class]
        was_full = len(pool) == pool.maxlen

        pool.append(buffer)

        # Track eviction if pool was full
        if was_full:
            self._local.evictions += 1
            self._total_evictions += 1

            logger.debug(
                "buffer_pool_eviction",
                size_class=size_class,
                pool_depth=len(pool),
            )

        logger.debug(
            "buffer_released",
            size_class=size_class,
            pool_depth=len(pool),
        )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get buffer pool statistics for monitoring

        Returns:
            Dict with:
                - size_class_stats: {size_class → {pool_depth, hit_rate, evictions}}
                - total_memory_bytes: Sum of all buffers in pool
                - hit_rate_overall: Across all size classes (0.0-1.0)
                - total_hits: Lifetime hit count
                - total_misses: Lifetime miss count
                - total_evictions: Lifetime eviction count

        Performance:
            - Stats collection: <5ms (aggregate across threads)

        Usage:
            stats = pool.get_stats()
            print(f"Hit rate: {stats['hit_rate_overall']:.2%}")
            print(f"Total memory: {stats['total_memory_bytes'] / 1024:.1f} KB")

        TODO(@infrastructure-team): Implement stats collection
        Assigned to: Issue #L5-3.2.1

        Steps:
            1. Ensure thread-local pools initialized
            2. Calculate per-size-class stats (depth, hit rate)
            3. Calculate overall hit rate
            4. Calculate total memory usage
            5. Return aggregated stats
        """
        self._ensure_local_pools()

        # Per-size-class stats
        size_class_stats = {}
        total_memory = 0

        for size_class in SIZE_CLASSES:
            pool = self._local.pools[size_class]
            pool_depth = len(pool)
            pool_memory = pool_depth * size_class
            total_memory += pool_memory

            size_class_stats[size_class] = {
                "pool_depth": pool_depth,
                "max_buffers": MAX_BUFFERS_PER_CLASS[size_class],
                "memory_bytes": pool_memory,
            }

        # Overall hit rate
        total_requests = self._total_hits + self._total_misses
        hit_rate = self._total_hits / total_requests if total_requests > 0 else 0.0

        return {
            "size_class_stats": size_class_stats,
            "total_memory_bytes": total_memory,
            "hit_rate_overall": hit_rate,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "total_evictions": self._total_evictions,
        }

    async def shutdown(self) -> None:
        """
        Flush all pools and release memory

        Called during graceful shutdown to clean up resources.

        Side Effects:
            - Clears all pools
            - Logs final stats

        TODO(@infrastructure-team): Implement shutdown
        Assigned to: Issue #L5-3.2.1

        Steps:
            1. Get final stats
            2. Log stats
            3. Clear all pools
            4. Log shutdown complete
        """
        stats = self.get_stats()

        logger.info(
            "buffer_pool_shutdown",
            hit_rate=stats["hit_rate_overall"],
            total_memory_kb=stats["total_memory_bytes"] / 1024,
            total_hits=stats["total_hits"],
            total_misses=stats["total_misses"],
            total_evictions=stats["total_evictions"],
        )

        # Clear pools if initialized
        if hasattr(self._local, "pools"):
            for size_class in SIZE_CLASSES:
                self._local.pools[size_class].clear()

        logger.info("buffer_pool_shutdown_complete")


# =============================================================================
# SECTION 4: MODULE EXPORTS
# =============================================================================

__all__ = [
    "BufferPool",
    "SIZE_CLASSES",
    "MAX_BUFFERS_PER_CLASS",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_buffer_pool_acquire_total{size_class, result} (counter: hit/miss)
#   - k1_buffer_pool_hit_rate{size_class} (gauge: hit rate 0.0-1.0)
#   - k1_buffer_pool_memory_bytes{size_class} (gauge: total memory in pool)
#   - k1_buffer_pool_evictions_total{size_class} (counter: LRU evictions)
#
# Logs to emit:
#   - Level: DEBUG (acquire/release), WARNING (eviction), INFO (shutdown)
#   - Fields: component="serialization.buffer_pool", size_class, pool_depth, result
#   - Events: buffer_acquired_hit, buffer_acquired_miss, buffer_released, buffer_pool_eviction, buffer_pool_shutdown
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/serialization/test_buffer_pool.py
#   - Test: buffer acquisition (hit from pool, miss allocate new)
#   - Test: buffer release (return to pool, LRU eviction)
#   - Test: size class selection (correct class for requested size)
#   - Test: thread-local isolation (separate pools per thread)
#   - Test: hit rate tracking (>80% target in realistic workload)
#   - Test: memory limits (pool doesn't exceed MAX_TOTAL_POOL_MEMORY)
#   - Test: graceful shutdown (flush pools, log stats)
#   - Test: performance (acquire <0.1ms hit, <1ms miss)
#
# Benchmark tests required:
#   - pytest-benchmark for performance validation
#   - Measure hit rate (target >80%)
#   - Measure speedup (1.4× vs allocation)
#   - Compare with no pooling (baseline)
#
# No simulation code allowed:
#   - Use real buffer allocation (bytearray)
#   - Test with actual serialization workloads
#   - Integration tests > unit tests
#
# =============================================================================
