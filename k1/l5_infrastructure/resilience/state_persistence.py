"""
K1 Circuit Breaker State Persistence

Redis-backed state persistence for circuit breaker recovery across restarts, providing
state storage, recovery on startup, and periodic cleanup of stale state.

**Architecture Context:**
- Layer 5 (Infrastructure): Resilience primitives
- Implements ADR-0009 (Circuit Breaker Pattern) state persistence
- Uses Redis for distributed state storage (shared across K1 instances)
- Enables circuit state recovery after K1 restarts

**Persistence Strategy:**
- **State Storage**: Circuit state (CLOSED/OPEN/HALF_OPEN) persisted to Redis
- **Failure Tracking**: Failure count and timestamps persisted for sliding window
- **TTL Management**: State expires after 24 hours of inactivity (stale cleanup)
- **Atomic Operations**: Redis transactions ensure consistency

**Redis Key Schema:**
```
circuit:state:{service_name}        → Hash {state, failure_count, open_time, last_update}
circuit:failures:{service_name}     → List [timestamp1, timestamp2, ...]
circuit:config:{service_name}       → Hash {failure_threshold, timeout_ms, ...}
```

**State Recovery Flow:**
```
1. K1 Startup
   └─ CircuitBreakerManager.__init__()

2. For each service (tool_runner, model_hub_local, etc.):
   ├─ Call StatePersistence.recover_state(service_name)
   ├─ Redis GET circuit:state:{service_name}
   ├─ Parse state, failure_count, open_time
   ├─ Set FSM state from persisted data
   └─ Log INFO "circuit_breaker_state_recovered"

3. If Redis unavailable:
   ├─ Log WARNING "redis_unavailable_starting_fresh"
   └─ Start with CLOSED state (default)

4. Background cleanup task:
   ├─ Every 1 hour: scan circuit:* keys
   ├─ Delete entries with last_update > 24h ago
   └─ Log INFO "circuit_breaker_state_cleanup"
```

**Performance Budgets:**
- State save: <5ms (Redis HSET + LPUSH)
- State recovery: <10ms (Redis HGET + LRANGE)
- Cleanup scan: <100ms (SCAN + DEL for stale entries)
- Memory per circuit: ~1KB in Redis (state + failures list)

**High Availability:**
- Redis sentinel for failover (production)
- Redis cluster for horizontal scaling (future)
- Fall back to in-memory if Redis unavailable

**ADR References:**
- ADR-0009: Circuit Breaker Pattern (state persistence requirements)
- ADR-0009a: FSM Implementation (state recovery on startup)

**Issue:** Epic 4.1.4 - Milestone 4 (Circuit Breaker) - P1 Important for Reliability
**Status:** STUB - Implementation by @resilience-team
**Last Updated:** 2025-10-13
"""

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

# K1 imports (stub references - actual imports validated during implementation)
# from k1.l4_runtime.session_state.state_manager import get_redis_client
# from k1.l5_infrastructure.resilience.circuit_fsm import CircuitBreakerState

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class PersistedCircuitState:
    """
    Serializable circuit breaker state for Redis storage.

    **Fields:**
    - service_name: Service identifier (tool_runner, model_hub_local, etc.)
    - state: FSM state ("CLOSED", "OPEN", "HALF_OPEN")
    - failure_count: Current failure count in sliding window
    - success_count: Current success count (for HALF_OPEN → CLOSED)
    - open_time: Timestamp when circuit opened (epoch seconds, None if not OPEN)
    - last_transition_time: Timestamp of most recent state transition
    - last_update: Timestamp when state was last persisted (for TTL)
    - failures: List of failure timestamps (for sliding window recovery)

    **Redis Storage Format (Hash):**
    ```
    HSET circuit:state:tool_runner
        state "OPEN"
        failure_count "5"
        success_count "0"
        open_time "1697123456.789"
        last_transition_time "1697123456.790"
        last_update "1697123460.000"

    LPUSH circuit:failures:tool_runner
        1697123450.123
        1697123451.456
        1697123452.789
        1697123454.012
        1697123456.345
    ```

    **Memory Footprint:**
    - Hash: ~200B (7 fields × ~30B per field)
    - Failures list: ~8B × failure_count (e.g., 5 failures = 40B)
    - Total: ~240B per circuit in Redis
    """

    service_name: str
    state: str  # "CLOSED", "OPEN", "HALF_OPEN"
    failure_count: int
    success_count: int
    open_time: Optional[float]
    last_transition_time: float
    last_update: float
    failures: List[float]  # Failure timestamps


# ============================================================================
# STATE PERSISTENCE
# ============================================================================


class StatePersistence:
    """
    Redis-backed state persistence for circuit breakers.

    **Responsibilities:**
    1. Save circuit state to Redis on state transitions
    2. Recover circuit state from Redis on K1 startup
    3. Periodic cleanup of stale state (>24h old)
    4. Handle Redis unavailability gracefully

    **Integration with CircuitBreakerFSM:**
    - FSM calls save_state() on each state transition
    - CircuitBreakerManager calls recover_state() on startup
    - Background task calls cleanup_stale_state() every 1 hour

    **Redis Connection:**
    - Use get_redis_client() from session_state
    - Connection pooling for performance
    - Sentinel support for HA (production)

    **Example Usage:**
    ```python
    # Initialize persistence
    persistence = StatePersistence(redis_client)

    # Save state on transition
    await persistence.save_state(
        service_name="tool_runner",
        fsm=circuit_fsm
    )

    # Recover state on startup
    state = await persistence.recover_state("tool_runner")
    if state:
        circuit_fsm.state = CircuitBreakerState[state.state]
        circuit_fsm.failure_count = state.failure_count
        circuit_fsm.open_time = state.open_time
        # ... restore other fields
    ```

    **Performance:**
    - save_state(): <5ms (Redis HSET + LPUSH)
    - recover_state(): <10ms (Redis HGET + LRANGE)
    - cleanup_stale_state(): <100ms (SCAN + DEL)

    **Error Handling:**
    - Redis unavailable: Log warning, continue with in-memory state
    - Redis timeout: Retry with exponential backoff (3 attempts)
    - Serialization error: Log error, skip persistence

    **TODO (@resilience-team):**
    1. Implement __init__() to initialize Redis client
    2. Implement save_state() to persist FSM state
    3. Implement recover_state() to load FSM state
    4. Implement clear_state() for admin reset
    5. Implement cleanup_stale_state() background task
    6. Add retry logic with exponential backoff
    7. Add WARD tests for save/recover, Redis unavailability
    8. Document integration with CircuitBreakerManager
    """

    def __init__(self, redis_client: Any = None):
        """
        Initialize State Persistence.

        **Initialization Steps:**
        1. Store redis_client or get_redis_client() if None
        2. Verify Redis connection with PING
        3. Start background cleanup task (every 1 hour)
        4. Log initialization complete

        **Redis Client:**
        - If redis_client provided: Use it (testing)
        - If None: Call get_redis_client() from session_state
        - Verify connection: redis_client.ping()

        **Background Cleanup:**
        - asyncio.create_task(self._cleanup_loop())
        - Runs every 3600s (1 hour)
        - Scans circuit:* keys, deletes stale entries

        **Performance:**
        - Initialization: <50ms (Redis PING + task creation)

        **Error Handling:**
        - Redis unavailable: Log WARNING, set self.redis_client = None
        - Continue without persistence (in-memory only)

        **TODO (@resilience-team):**
        1. Get redis_client or call get_redis_client()
        2. Test connection with redis_client.ping()
        3. Start background cleanup task
        4. Log INFO "state_persistence_initialized"
        5. Add WARD tests for init, Redis unavailable

        Args:
            redis_client: Optional Redis client (for testing, defaults to get_redis_client())

        Raises:
            None (errors logged, not raised)
        """
        self.redis_client = redis_client
        self._cleanup_interval = 3600  # 1 hour
        self._stale_threshold = 86400  # 24 hours

        # TODO: Get redis_client if None
        # TODO: Verify connection with PING
        # TODO: Start background cleanup task

        logger.info(
            "state_persistence_initialized",
            redis_available=self.redis_client is not None,
        )

    async def save_state(
        self, service_name: str, fsm: Any  # CircuitBreakerFSM when implemented
    ) -> bool:
        """
        Save circuit breaker state to Redis.

        **Persistence Steps:**
        1. Check if Redis available (self.redis_client is not None)
        2. Create PersistedCircuitState from FSM
           - state: fsm.state.name ("CLOSED", "OPEN", "HALF_OPEN")
           - failure_count: fsm.failure_count
           - success_count: fsm.success_count
           - open_time: fsm.open_time
           - last_transition_time: fsm.last_transition_time
           - last_update: time.time()
           - failures: [f.timestamp for f in fsm.failures]
        3. Redis transaction (MULTI/EXEC):
           - HSET circuit:state:{service_name} (state hash)
           - DEL circuit:failures:{service_name} (clear old failures)
           - LPUSH circuit:failures:{service_name} (new failures)
           - EXPIRE circuit:state:{service_name} 86400 (24h TTL)
           - EXPIRE circuit:failures:{service_name} 86400 (24h TTL)
        4. Log DEBUG "circuit_breaker_state_saved"
        5. Return True on success

        **Redis Commands:**
        ```python
        # Save state hash
        await redis.hset(
            f"circuit:state:{service_name}",
            mapping={
                "state": "OPEN",
                "failure_count": "5",
                "success_count": "0",
                "open_time": "1697123456.789",
                "last_transition_time": "1697123456.790",
                "last_update": "1697123460.000"
            }
        )

        # Save failures list
        await redis.delete(f"circuit:failures:{service_name}")
        if failures:
            await redis.lpush(f"circuit:failures:{service_name}", *failures)

        # Set TTL (24 hours)
        await redis.expire(f"circuit:state:{service_name}", 86400)
        await redis.expire(f"circuit:failures:{service_name}", 86400)
        ```

        **Performance:**
        - Redis available: <5ms (HSET + LPUSH + EXPIRE × 2)
        - Redis unavailable: <0.1ms (skip persistence)

        **Error Handling:**
        - Redis unavailable: Log DEBUG, return False
        - Redis timeout: Retry with backoff (3 attempts)
        - Serialization error: Log ERROR, return False

        **WARD Test Example:**
        ```python
        @test("save_state persists FSM to Redis")
        async def _():
            redis = FakeRedis()
            persistence = StatePersistence(redis)
            fsm = CircuitBreakerFSM("test", failure_threshold=5)

            # Open circuit
            for i in range(5):
                await fsm.record_failure(Exception(), 100)

            # Save state
            success = await persistence.save_state("test", fsm)
            assert success

            # Verify Redis
            state = await redis.hgetall("circuit:state:test")
            assert state["state"] == "OPEN"
            assert state["failure_count"] == "5"

            failures = await redis.lrange("circuit:failures:test", 0, -1)
            assert len(failures) == 5
        ```

        **TODO (@resilience-team):**
        1. Check if self.redis_client is None, return False
        2. Create PersistedCircuitState from FSM
        3. Redis HSET circuit:state:{service_name}
        4. Redis DEL + LPUSH circuit:failures:{service_name}
        5. Redis EXPIRE both keys (24h TTL)
        6. Log DEBUG "circuit_breaker_state_saved"
        7. Add retry logic with exponential backoff
        8. Add WARD tests for save, Redis unavailable, retry

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)
            fsm: CircuitBreakerFSM instance to persist

        Returns:
            bool: True if saved successfully, False if Redis unavailable or error

        Raises:
            None (errors logged, not raised)
        """
        if self.redis_client is None:
            logger.debug("skip_state_save_redis_unavailable", service_name=service_name)
            return False

        # TODO: Create PersistedCircuitState
        # TODO: Redis HSET
        # TODO: Redis DEL + LPUSH
        # TODO: Redis EXPIRE
        # TODO: Log save complete

        logger.debug("save_state", service_name=service_name)
        return False  # TODO: Return True on success

    async def recover_state(self, service_name: str) -> Optional[PersistedCircuitState]:
        """
        Recover circuit breaker state from Redis.

        **Recovery Steps:**
        1. Check if Redis available (self.redis_client is not None)
        2. Redis HGETALL circuit:state:{service_name}
           - If key doesn't exist: Return None (fresh start)
        3. Redis LRANGE circuit:failures:{service_name} 0 -1 (all failures)
        4. Parse state hash:
           - state: str → "CLOSED"/"OPEN"/"HALF_OPEN"
           - failure_count: str → int
           - success_count: str → int
           - open_time: str → float (or None)
           - last_transition_time: str → float
           - last_update: str → float
        5. Check if state is stale (last_update > 24h ago):
           - If stale: Delete keys, return None
        6. Create PersistedCircuitState with parsed data + failures
        7. Log INFO "circuit_breaker_state_recovered"
        8. Return PersistedCircuitState

        **Redis Commands:**
        ```python
        # Load state hash
        state_data = await redis.hgetall(f"circuit:state:{service_name}")
        if not state_data:
            return None  # Fresh start

        # Load failures list
        failures = await redis.lrange(f"circuit:failures:{service_name}", 0, -1)

        # Parse and return
        return PersistedCircuitState(
            service_name=service_name,
            state=state_data["state"],
            failure_count=int(state_data["failure_count"]),
            success_count=int(state_data["success_count"]),
            open_time=float(state_data["open_time"]) if state_data["open_time"] else None,
            last_transition_time=float(state_data["last_transition_time"]),
            last_update=float(state_data["last_update"]),
            failures=[float(f) for f in failures]
        )
        ```

        **Performance:**
        - Redis available: <10ms (HGETALL + LRANGE)
        - Redis unavailable: <0.1ms (return None)

        **Stale State Detection:**
        - Check: time.time() - last_update > 86400 (24h)
        - If stale: Delete keys, return None (fresh start)
        - Prevents using outdated circuit state after long downtime

        **Error Handling:**
        - Redis unavailable: Log DEBUG, return None
        - Redis timeout: Retry with backoff (3 attempts)
        - Parse error: Log ERROR, delete keys, return None

        **WARD Test Example:**
        ```python
        @test("recover_state loads FSM from Redis")
        async def _():
            redis = FakeRedis()
            persistence = StatePersistence(redis)

            # Pre-populate Redis with OPEN state
            await redis.hset("circuit:state:test", mapping={
                "state": "OPEN",
                "failure_count": "5",
                "success_count": "0",
                "open_time": str(time.time()),
                "last_transition_time": str(time.time()),
                "last_update": str(time.time())
            })
            await redis.lpush("circuit:failures:test", *[
                str(time.time() - i) for i in range(5)
            ])

            # Recover state
            state = await persistence.recover_state("test")

            assert state is not None
            assert state.state == "OPEN"
            assert state.failure_count == 5
            assert len(state.failures) == 5
        ```

        **TODO (@resilience-team):**
        1. Check if self.redis_client is None, return None
        2. Redis HGETALL circuit:state:{service_name}
        3. If empty, return None (fresh start)
        4. Redis LRANGE circuit:failures:{service_name}
        5. Parse state_data fields (str → int/float)
        6. Check if stale (last_update > 24h ago)
        7. Create PersistedCircuitState
        8. Log INFO "circuit_breaker_state_recovered"
        9. Add WARD tests for recovery, fresh start, stale state

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)

        Returns:
            Optional[PersistedCircuitState]: Recovered state or None if not found/stale

        Raises:
            None (errors logged, not raised)
        """
        if self.redis_client is None:
            logger.debug(
                "skip_state_recovery_redis_unavailable", service_name=service_name
            )
            return None

        # TODO: Redis HGETALL
        # TODO: Check if key exists
        # TODO: Redis LRANGE
        # TODO: Parse state_data
        # TODO: Check if stale
        # TODO: Create PersistedCircuitState
        # TODO: Log recovery

        logger.debug("recover_state", service_name=service_name)
        return None  # TODO: Return PersistedCircuitState

    async def clear_state(self, service_name: str) -> bool:
        """
        Clear persisted state for a service (admin operation).

        **Clear Steps:**
        1. Check if Redis available
        2. Redis DEL circuit:state:{service_name}
        3. Redis DEL circuit:failures:{service_name}
        4. Log INFO "circuit_breaker_state_cleared"
        5. Return True on success

        **Use Cases:**
        - Admin reset: Operator clears state for fresh start
        - Testing: Clear state between test runs
        - Stale cleanup: Background task removes old state

        **Performance:**
        - <2ms (DEL × 2)

        **TODO (@resilience-team):**
        1. Check if self.redis_client is None, return False
        2. Redis DEL circuit:state:{service_name}
        3. Redis DEL circuit:failures:{service_name}
        4. Log INFO "circuit_breaker_state_cleared"
        5. Add WARD tests for clear

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)

        Returns:
            bool: True if cleared successfully, False if Redis unavailable

        Raises:
            None (errors logged, not raised)
        """
        if self.redis_client is None:
            return False

        # TODO: Redis DEL circuit:state:{service_name}
        # TODO: Redis DEL circuit:failures:{service_name}
        # TODO: Log clear

        logger.info("clear_state", service_name=service_name)
        return False  # TODO: Return True on success

    async def cleanup_stale_state(self) -> int:
        """
        Clean up stale circuit breaker state (>24h old).

        **Cleanup Steps:**
        1. Redis SCAN circuit:state:* (cursor-based iteration)
        2. For each key:
           - Redis HGET {key} last_update
           - Check if time.time() - last_update > 86400 (24h)
           - If stale: Redis DEL {key}, Redis DEL circuit:failures:{service_name}
        3. Log INFO "circuit_breaker_state_cleanup", stale_count
        4. Return count of deleted entries

        **SCAN Pattern:**
        ```python
        cursor = 0
        stale_count = 0

        while True:
            cursor, keys = await redis.scan(
                cursor,
                match="circuit:state:*",
                count=100
            )

            for key in keys:
                last_update = await redis.hget(key, "last_update")
                if last_update and time.time() - float(last_update) > 86400:
                    service_name = key.split(":")[-1]
                    await redis.delete(key)
                    await redis.delete(f"circuit:failures:{service_name}")
                    stale_count += 1

            if cursor == 0:
                break

        return stale_count
        ```

        **Performance:**
        - <100ms for 100 circuits (SCAN + HGET + DEL)
        - Cursor-based iteration prevents blocking

        **Background Task:**
        - Called by _cleanup_loop() every 1 hour
        - Runs in background, doesn't block main event loop

        **TODO (@resilience-team):**
        1. Redis SCAN circuit:state:* with cursor
        2. For each key, check last_update
        3. Delete stale keys (>24h old)
        4. Log INFO "circuit_breaker_state_cleanup"
        5. Add WARD tests for cleanup

        Returns:
            int: Number of stale entries deleted

        Raises:
            None (errors logged, not raised)
        """
        if self.redis_client is None:
            return 0

        # TODO: Redis SCAN circuit:state:*
        # TODO: Check last_update for each key
        # TODO: Delete stale keys
        # TODO: Log cleanup

        logger.info("cleanup_stale_state", stale_count=0)
        return 0  # TODO: Return actual count

    async def _cleanup_loop(self) -> None:
        """
        Background task for periodic state cleanup.

        **Loop Logic:**
        ```python
        while True:
            await asyncio.sleep(self._cleanup_interval)  # 1 hour
            try:
                stale_count = await self.cleanup_stale_state()
                logger.info("cleanup_loop_completed", stale_count=stale_count)
            except Exception as e:
                logger.error("cleanup_loop_error", error=str(e))
        ```

        **Error Handling:**
        - Exception in cleanup: Log error, continue loop
        - Redis unavailable: Skip cleanup, continue loop

        **TODO (@resilience-team):**
        1. Implement infinite loop with sleep
        2. Call cleanup_stale_state()
        3. Handle exceptions, continue loop
        4. Add WARD tests for loop (with short interval)

        Raises:
            None (runs indefinitely, errors logged)
        """
        # TODO: Implement cleanup loop
        pass


# ============================================================================
# EXPECTED LINT ERRORS (STUB FILE)
# ============================================================================
"""
**Expected Errors (will be resolved during implementation):**

1. Incomplete implementations with TODO comments:
   - __init__() Redis client initialization incomplete
   - save_state() Redis HSET/LPUSH incomplete
   - recover_state() Redis HGETALL/LRANGE incomplete
   - clear_state() Redis DEL incomplete
   - cleanup_stale_state() Redis SCAN incomplete
   - _cleanup_loop() loop not implemented

2. Missing imports:
   - get_redis_client from k1.l4_runtime.session_state.state_manager
   - CircuitBreakerState from circuit_fsm.py

3. Type: Any for fsm parameter:
   - Should be CircuitBreakerFSM when implemented

4. Return value inconsistencies:
   - save_state() always returns False (should return True on success)
   - clear_state() always returns False (should return True on success)
   - cleanup_stale_state() always returns 0 (should return actual count)

5. TODO comments:
   - 30+ TODO markers for @resilience-team implementation

**Implementation Dependencies:**
- Epic 4.1.2: circuit_fsm.py (CircuitBreakerFSM, CircuitBreakerState)
- K1 Core: session_state.state_manager (get_redis_client, Redis connection pool)

**Testing Requirements:**
- WARD framework with 100% coverage target
- Test categories:
  1. Save state (Redis HSET + LPUSH, TTL set)
  2. Recover state (Redis HGETALL + LRANGE, parsing)
  3. Fresh start (no persisted state, return None)
  4. Stale state (last_update >24h, delete and return None)
  5. Clear state (Redis DEL, admin reset)
  6. Cleanup stale (SCAN + DELETE, background task)
  7. Redis unavailable (graceful fallback, no errors)
  8. Serialization (dataclass → Redis hash → dataclass)
  9. Concurrency (multiple saves/recovers, thread-safe)
  10. Performance (save <5ms, recover <10ms, cleanup <100ms)
"""
