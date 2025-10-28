"""
Hot Tier (L1 RAM) - In-Memory SessionState Storage.

This module implements the hot tier for K1's multi-tier storage architecture.
Provides <1ms access to active SessionState using in-memory LRU cache.

Use Cases (ADR-0020a):
    - Active conversation turns (last 60 minutes)
    - Fast SessionState access (<1ms, no I/O)
    - LRU eviction when capacity exceeded (56MB)
    - Idle timeout eviction (60 minutes inactive)
    - Automatic migration to warm tier

Performance:
    - Lookup: O(1), <1ms P95 (direct memory access)
    - Insert: O(1), <1ms P95 (dict insert)
    - Remove: O(1), <1ms P95 (dict delete)
    - Eviction: O(1), <5ms P95 (LRU pop)
    - Capacity check: <100ms P95 (scan all sessions)

Trade-offs:
    ✅ Sub-millisecond access (<1ms for hot path)
    ✅ Zero I/O latency (pure in-memory)
    ✅ Simple LRU eviction (OrderedDict)
    ✅ Automatic warm tier migration
    ⚠️ Limited capacity (56MB = 1000 sessions)
    ⚠️ Memory cost ($100/GB/month)
    ⚠️ No persistence (requires checkpointing)

Integration Points:
    - TierManager: Coordinates tier operations
    - WarmTier: Receives evicted sessions
    - K0Checkpointer: Persists to WAL every 5 minutes
    - LifecycleManager: Monitors idle sessions

Related ADRs:
    - ADR-0020: Multi-Tier Storage (Hot/Warm/Cold architecture)
    - ADR-0020a: Hot Tier (L1 RAM in-memory management)
    - ADR-0018: 3-Tier Eviction Strategy (LRU eviction)

Author: @storage-team
Created: 2025-10-27
Status: STUB (Implementation Required)
"""

from collections import OrderedDict
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class HotTier:
    """
    Hot Tier: In-Memory LRU Cache for SessionState.

    Stores active SessionState in RAM using OrderedDict for LRU tracking.
    Automatically evicts least recently used sessions when capacity (56MB) exceeded.

    Features:
        - <1ms access latency (direct memory lookup)
        - LRU eviction policy (capacity-based)
        - Idle timeout eviction (60 minutes)
        - Automatic warm tier migration
        - Thread-safe operations
        - Memory tracking

    LRU Mechanics:
        - OrderedDict maintains insertion order
        - move_to_end() on access (O(1) operation)
        - popitem(last=False) for LRU eviction
        - Most recently used at end, LRU at beginning

    Capacity Management:
        - Max capacity: 56MB (1000 sessions × 56KB average)
        - Size calculation: sum of all SessionState sizes
        - Eviction trigger: current_size > 56MB
        - Eviction target: Remove LRU session

    Example Usage:
        ```python
        from k1.l4_runtime.storage.hot_tier import HotTier

        # Initialize hot tier
        hot_tier = HotTier(capacity_mb=56)

        # Store session
        session_state = {
            "session_id": "abc123",
            "turn_count": 5,
            "beliefs": {"recent_turns": [...], ...},
            # ... other sections
        }
        evicted = hot_tier.put("abc123", session_state)
        if evicted:
            print(f"Evicted session: {evicted['session_id']}")

        # Retrieve session (updates LRU)
        state = hot_tier.get("abc123")
        if state:
            print(f"Found session with {state['turn_count']} turns")

        # Check if session exists
        if hot_tier.contains("abc123"):
            print("Session in hot tier")

        # Remove session
        removed = hot_tier.remove("abc123")
        if removed:
            print("Session removed")

        # Get statistics
        stats = hot_tier.get_stats()
        print(f"Sessions: {stats['sessions']}")
        print(f"Size: {stats['size_mb']:.1f}MB / {stats['capacity_mb']}MB")
        print(f"Hit rate: {stats['hit_rate']:.2%}")
        ```

    ADR References:
        - ADR-0020a: "HotTier uses OrderedDict for O(1) LRU tracking"
        - ADR-0020a: "Evict LRU session when capacity exceeded"
        - ADR-0020a: "Idle timeout eviction (60 minutes)"

    WARD Test Example:
        ```python
        from ward import test
        from k1.l4_runtime.storage.hot_tier import HotTier

        @test("hot tier stores and retrieves session")
        def _():
            hot_tier = HotTier(capacity_mb=56)

            # Store session
            test_state = {"session_id": "test123", "turn_count": 5}
            evicted = hot_tier.put("test123", test_state)
            assert evicted is None  # No eviction yet

            # Retrieve session
            result = hot_tier.get("test123")
            assert result == test_state

        @test("hot tier evicts LRU session when capacity exceeded")
        def _():
            hot_tier = HotTier(capacity_mb=0.001)  # 1KB capacity for testing

            # Store first session
            state1 = {"session_id": "session1", "data": "x" * 500}
            hot_tier.put("session1", state1)

            # Store second session (should evict first)
            state2 = {"session_id": "session2", "data": "y" * 500}
            evicted = hot_tier.put("session2", state2)

            assert evicted is not None
            assert evicted["session_id"] == "session1"  # LRU evicted

        @test("hot tier updates LRU on access")
        def _():
            hot_tier = HotTier(capacity_mb=0.001)

            # Store two sessions
            hot_tier.put("session1", {"data": "a" * 400})
            hot_tier.put("session2", {"data": "b" * 400})

            # Access session1 (moves to end)
            hot_tier.get("session1")

            # Store third session (should evict session2, not session1)
            evicted = hot_tier.put("session3", {"data": "c" * 400})

            assert evicted["session_id"] == "session2"  # session1 was accessed
        ```
    """

    MAX_CAPACITY_MB = 56  # 1000 sessions × 56KB average
    INACTIVE_TIMEOUT_SEC = 3600  # 60 minutes

    def __init__(
        self,
        capacity_mb: int = 56,
        warm_tier=None,
    ):
        """
        Initialize hot tier.

        Args:
            capacity_mb: Total capacity in MB (default: 56MB)
            warm_tier: WarmTier instance for eviction (optional)

        Performance:
            - Initialization: <0.1ms (no I/O, simple assignment)
        """
        # TODO(@storage-team): Initialize hot tier
        # 1. Create OrderedDict for LRU tracking:
        #    self.sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        # 2. Track last access time per session:
        #    self.last_access: Dict[str, float] = {}
        # 3. Store capacity limits:
        #    self.capacity_mb = capacity_mb
        # 4. Store warm tier reference (for eviction):
        #    self.warm_tier = warm_tier
        # 5. Initialize metrics counters:
        #    self.metrics = {"hits": 0, "misses": 0, "evictions": 0}
        self.sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.last_access: Dict[str, float] = {}
        self.capacity_mb = capacity_mb
        self.warm_tier = warm_tier
        self.metrics = {"hits": 0, "misses": 0, "evictions": 0}
        self.logger = logger.bind(component="hot_tier")

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve SessionState from Hot Tier.

        Performs O(1) dict lookup and updates LRU order (move to end).

        Args:
            session_id: Session identifier

        Returns:
            SessionState dict or None if not found

        Performance:
            - Lookup: O(1), <1ms P95 (dict access + move_to_end)

        Side Effects:
            - Updates LRU order (move to end)
            - Updates last_access timestamp
            - Increments hit/miss metrics

        Example:
            ```python
            # Retrieve active session
            state = hot_tier.get("abc123")
            if state:
                print(f"Found session with {state['turn_count']} turns")
            else:
                print("Session not in hot tier (check warm tier)")
            ```

        ADR Reference:
            - ADR-0020a: "move_to_end() updates LRU on access"
        """
        # TODO(@storage-team): Implement get with LRU update
        # 1. Start timer:
        #    start_ns = time.perf_counter_ns()
        # 2. Check if session exists:
        #    if session_id in self.sessions:
        #        # Move to end (most recently used)
        #        self.sessions.move_to_end(session_id)
        #        # Update last access time
        #        self.last_access[session_id] = time.time()
        #        # Increment hit counter
        #        self.metrics["hits"] += 1
        #        # Get session
        #        session = self.sessions[session_id]
        #        # Log
        #        latency_ms = (time.perf_counter_ns() - start_ns) / 1e6
        #        self.logger.debug("hot_tier_get", session_id=session_id, latency_ms=latency_ms)
        #        return session
        # 3. Session not found:
        #    self.metrics["misses"] += 1
        #    return None
        return None

    def put(
        self,
        session_id: str,
        state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Store SessionState in Hot Tier.

        Inserts session into OrderedDict and checks capacity. If capacity exceeded,
        evicts LRU session and migrates to warm tier.

        Args:
            session_id: Session identifier
            state: SessionState dict

        Returns:
            Evicted session (if any) or None

        Execution Flow:
            1. Insert/update session in OrderedDict
            2. Update LRU order (move to end)
            3. Calculate current capacity
            4. If capacity exceeded: evict LRU session
            5. Return evicted session (if any)

        Performance:
            - Insert: O(1), <1ms P95 (dict insert + move_to_end)
            - Eviction: O(1), <5ms P95 (popitem + capacity check)

        Side Effects:
            - Updates LRU order
            - Updates last_access timestamp
            - May evict LRU session (capacity management)
            - May trigger warm tier write (eviction)

        Example:
            ```python
            # Store session (may evict LRU)
            state = {"session_id": "abc123", "turn_count": 5}
            evicted = hot_tier.put("abc123", state)

            if evicted:
                print(f"Evicted LRU session: {evicted['session_id']}")
                # Evicted session migrated to warm tier automatically
            ```

        ADR Reference:
            - ADR-0020a: "Evict LRU when capacity exceeded"
            - ADR-0020a: "Migrate evicted sessions to warm tier"
        """
        # TODO(@storage-team): Implement put with capacity check
        # 1. Start timer:
        #    start_ns = time.perf_counter_ns()
        # 2. Insert or update session:
        #    if session_id in self.sessions:
        #        self.sessions.move_to_end(session_id)
        #    self.sessions[session_id] = state
        #    self.last_access[session_id] = time.time()
        # 3. Check capacity:
        #    current_size_mb = self._calculate_size_mb()
        #    evicted_session = None
        #    if current_size_mb > self.capacity_mb:
        #        evicted_session = self._evict_lru()
        # 4. Log:
        #    latency_ms = (time.perf_counter_ns() - start_ns) / 1e6
        #    self.logger.debug("hot_tier_put", session_id=session_id,
        #                     evicted=evicted_session is not None, latency_ms=latency_ms)
        # 5. Return evicted session:
        #    return evicted_session
        return None

    def remove(self, session_id: str) -> bool:
        """
        Remove Session from Hot Tier.

        Args:
            session_id: Session to remove

        Returns:
            True if removed, False if not found

        Performance:
            - Remove: O(1), <1ms P95 (dict delete)

        Example:
            ```python
            # Remove session
            removed = hot_tier.remove("abc123")
            if removed:
                print("Session removed from hot tier")
            else:
                print("Session not found in hot tier")
            ```

        ADR Reference:
            - ADR-0020a: "O(1) removal from hot tier"
        """
        # TODO(@storage-team): Implement remove
        # 1. Check if session exists:
        #    if session_id in self.sessions:
        #        del self.sessions[session_id]
        #        del self.last_access[session_id]
        #        self.logger.debug("hot_tier_remove", session_id=session_id)
        #        return True
        # 2. Not found:
        #    return False
        return False

    def contains(self, session_id: str) -> bool:
        """
        Check if Session Exists in Hot Tier.

        Args:
            session_id: Session to check

        Returns:
            True if exists, False otherwise

        Performance:
            - Check: O(1), <0.1ms (dict membership test)

        Example:
            ```python
            if hot_tier.contains("abc123"):
                print("Session in hot tier")
            else:
                print("Session not in hot tier (check warm tier)")
            ```
        """
        # TODO(@storage-team): Implement contains
        # return session_id in self.sessions
        return False

    def evict_inactive(self) -> int:
        """
        Evict Sessions Idle for >60 Minutes.

        Scans all sessions and evicts those with last_access > 60 minutes ago.
        Evicted sessions migrated to warm tier automatically.

        Returns:
            Number of sessions evicted

        Performance:
            - Scan: O(n), <100ms P95 (1000 sessions)
            - Eviction: O(k), <5ms per session (k = inactive count)

        Triggers:
            - Background task (every 5 minutes)
            - Manual invocation (administrative command)

        Example:
            ```python
            # Evict idle sessions (background task)
            evicted_count = hot_tier.evict_inactive()
            print(f"Evicted {evicted_count} idle sessions")
            ```

        ADR Reference:
            - ADR-0020a: "Evict sessions idle >60 minutes"
        """
        # TODO(@storage-team): Implement idle eviction
        # 1. Get current time:
        #    now = time.time()
        # 2. Find idle sessions:
        #    idle_sessions = [
        #        sid for sid, last_access in self.last_access.items()
        #        if now - last_access > self.INACTIVE_TIMEOUT_SEC
        #    ]
        # 3. Evict idle sessions:
        #    for session_id in idle_sessions:
        #        session = self.sessions.pop(session_id)
        #        del self.last_access[session_id]
        #        # Migrate to warm tier
        #        if self.warm_tier:
        #            self.warm_tier.put(session_id, session)
        #        self.metrics["evictions"] += 1
        # 4. Log:
        #    self.logger.info("evicted_inactive_sessions", count=len(idle_sessions))
        # 5. Return count:
        #    return len(idle_sessions)
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get Hot Tier Statistics.

        Returns comprehensive metrics for monitoring and debugging:
        - Session count and size
        - Hit/miss rates
        - Eviction counts
        - Capacity utilization

        Returns:
            Dict with keys:
                - sessions: Current session count
                - size_mb: Current size usage
                - capacity_mb: Total capacity
                - utilization: size_mb / capacity_mb
                - hit_rate: hits / (hits + misses)
                - miss_rate: misses / (hits + misses)
                - evictions: Total evictions

        Performance:
            - Stats calculation: <5ms (aggregate metrics + size calculation)

        Example:
            ```python
            stats = hot_tier.get_stats()
            print(f"Sessions: {stats['sessions']}")
            print(f"Size: {stats['size_mb']:.1f}MB / {stats['capacity_mb']}MB")
            print(f"Utilization: {stats['utilization']:.1%}")
            print(f"Hit rate: {stats['hit_rate']:.2%}")
            print(f"Evictions: {stats['evictions']}")
            ```

        ADR Reference:
            - ADR-0020a: "Hot tier statistics for observability"
        """
        # TODO(@storage-team): Implement stats collection
        # 1. Calculate current size:
        #    size_mb = self._calculate_size_mb()
        # 2. Calculate hit rate:
        #    total_accesses = self.metrics["hits"] + self.metrics["misses"]
        #    hit_rate = self.metrics["hits"] / total_accesses if total_accesses > 0 else 0.0
        #    miss_rate = self.metrics["misses"] / total_accesses if total_accesses > 0 else 0.0
        # 3. Return stats:
        #    return {
        #        "sessions": len(self.sessions),
        #        "size_mb": size_mb,
        #        "capacity_mb": self.capacity_mb,
        #        "utilization": size_mb / self.capacity_mb if self.capacity_mb > 0 else 0.0,
        #        "hit_rate": hit_rate,
        #        "miss_rate": miss_rate,
        #        "evictions": self.metrics["evictions"],
        #    }
        return {
            "sessions": 0,
            "size_mb": 0.0,
            "capacity_mb": self.capacity_mb,
            "utilization": 0.0,
            "hit_rate": 0.0,
            "miss_rate": 0.0,
            "evictions": 0,
        }

    def _evict_lru(self) -> Optional[Dict[str, Any]]:
        """
        Evict Least Recently Used Session.

        Removes first item from OrderedDict (LRU) and migrates to warm tier.

        Returns:
            Evicted session or None if no sessions

        Performance:
            - Eviction: O(1), <5ms P95 (popitem + warm tier write)

        ADR Reference:
            - ADR-0020a: "popitem(last=False) for LRU eviction"
        """
        # TODO(@storage-team): Implement LRU eviction
        # 1. Check if sessions exist:
        #    if not self.sessions:
        #        return None
        # 2. Pop LRU session (first item):
        #    session_id, session = self.sessions.popitem(last=False)
        #    del self.last_access[session_id]
        # 3. Migrate to warm tier:
        #    if self.warm_tier:
        #        self.warm_tier.put(session_id, session)
        # 4. Update metrics:
        #    self.metrics["evictions"] += 1
        # 5. Log:
        #    self.logger.warning("evicted_lru_session", session_id=session_id)
        # 6. Return evicted session:
        #    return session
        return None

    def _calculate_size_mb(self) -> float:
        """
        Calculate Current Hot Tier Size in MB.

        Sums sizes of all SessionState objects in memory.

        Returns:
            Total size in MB

        Performance:
            - Calculation: O(n), <10ms (1000 sessions)

        Note:
            Uses sys.getsizeof() for approximate size calculation.
            Actual memory usage may vary due to Python overhead.
        """
        # TODO(@storage-team): Implement size calculation
        # 1. Sum sizes of all sessions:
        #    total_bytes = sum(sys.getsizeof(session) for session in self.sessions.values())
        # 2. Convert to MB:
        #    return total_bytes / (1024 * 1024)
        return 0.0


# Expected Lint Errors (Intentional):
# 1. time import unused (TODO: use in latency tracking and idle checks)
# 2. sys import unused (TODO: use in _calculate_size_mb)
# 3. structlog import unused (TODO: use in logging)
#
# These will be resolved when @storage-team implements the TODOs.
