"""
K1 Circuit Breaker Finite State Machine

3-state FSM implementation providing state transitions, guards, event handling, and
thread-safe concurrent failure tracking for circuit breaker resilience.

**Architecture Context:**
- Layer 5 (Infrastructure): Resilience primitives
- Implements ADR-0009a (FSM Implementation) state transition logic
- Provides atomic state transitions with asyncio.Lock for thread safety
- Tracks failure/success counts with sliding time windows

**State Machine Design:**
```
    CLOSED (Normal Operation)
      ├─ Track failure_count in time_window_ms
      ├─ Reset failure_count on success
      └─ [failure_count ≥ failure_threshold] → OPEN

    OPEN (Fail-Fast Mode)
      ├─ Reject all requests immediately (<1ms)
      ├─ Invoke fallback (DEFAULT_VALUE, CACHED_RESULT, ALTERNATE_SERVICE, RAISE_ERROR)
      ├─ Wait timeout_duration_ms
      └─ [timeout elapsed] → HALF_OPEN

    HALF_OPEN (Testing Recovery)
      ├─ Allow 1 probe request (first caller wins, others fail-fast)
      ├─ [probe success AND success_count ≥ success_threshold] → CLOSED
      └─ [probe failure] → OPEN
```

**State Transition Matrix (ADR-0009a):**

| From State | Event | Condition | To State | Actions |
|-----------|-------|-----------|----------|---------|
| CLOSED | failure | failure_count ≥ threshold | OPEN | Set open_time, export metric |
| CLOSED | success | - | CLOSED | Reset failure_count |
| OPEN | timeout_elapsed | timeout_duration_ms passed | HALF_OPEN | Allow probe, export metric |
| HALF_OPEN | success | success_count ≥ threshold | CLOSED | Reset counters, export metric |
| HALF_OPEN | failure | - | OPEN | Set open_time, export metric |

**Performance Budgets (ADR-0009a):**
- State check: <0.1ms (target 0.05ms) - lock acquisition + state read
- State transition: <1ms (target 0.5ms) - state update + metric + logging
- Failure recording: <0.5ms (target 0.3ms) - counter update + time window check
- Success recording: <0.5ms (target 0.3ms) - counter update
- Memory per FSM: <1KB (target 512B) - state + counters + timers

**Thread Safety (ADR-0009a):**
- All state transitions protected by asyncio.Lock
- Concurrent failure/success recording is thread-safe
- Time window calculations use atomic timestamp comparisons
- HALF_OPEN probe uses lock to ensure only 1 caller wins

**ADR References:**
- ADR-0009: Circuit Breaker Pattern (3-state FSM overview)
- ADR-0009a: FSM Implementation (state transitions, concurrency, performance)
- ADR-0009b: Per-Service Configuration (threshold tuning)
- ADR-0009c: Metrics & Observability (state gauge, transition counter)

**Issue:** Epic 4.1.2 - Milestone 4 (Circuit Breaker) - P1 Important for Reliability
**Status:** STUB - Implementation by @resilience-team
**Last Updated:** 2025-10-13
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# K1 imports (stub references - actual imports validated during implementation)
# from k1.obs.metrics import export_gauge, export_counter
# from k1.obs.tracing import get_trace_id

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================


class CircuitBreakerState(Enum):
    """
    Circuit breaker FSM states (ADR-0009, ADR-0009a).

    **State Descriptions:**
    - CLOSED: Normal operation, track failure_count, allow all requests
    - OPEN: Fail-fast mode, reject requests <1ms, invoke fallback, wait timeout
    - HALF_OPEN: Testing recovery, allow 1 probe request, others fail-fast

    **State Values:**
    - CLOSED = 0 (for Prometheus gauge: circuit_breaker_state{service="X"} = 0)
    - OPEN = 1 (for Prometheus gauge: circuit_breaker_state{service="X"} = 1)
    - HALF_OPEN = 2 (for Prometheus gauge: circuit_breaker_state{service="X"} = 2)
    """

    CLOSED = 0  # Normal operation, all requests pass through
    OPEN = 1  # Fail-fast mode, reject all requests
    HALF_OPEN = 2  # Testing recovery, allow 1 probe request


@dataclass
class FailureRecord:
    """
    Individual failure record for sliding time window (ADR-0009a).

    **Sliding Window Implementation:**
    - Deque of failure timestamps (epoch seconds)
    - Prune entries older than time_window_ms
    - Count failures in window with len(deque)
    - Memory efficient: 8 bytes per failure (timestamp float)

    **Example:**
    ```python
    # 3 failures in last 60s
    failures = deque([
        FailureRecord(timestamp=1697123456.123, failure_type="timeout"),
        FailureRecord(timestamp=1697123470.456, failure_type="exception"),
        FailureRecord(timestamp=1697123480.789, failure_type="slow_call")
    ])
    ```
    """

    timestamp: float  # Epoch seconds (time.time())
    failure_type: str  # "timeout", "exception", "slow_call"


# ============================================================================
# CIRCUIT BREAKER FSM
# ============================================================================


class CircuitBreakerFSM:
    """
    Finite state machine for circuit breaker with thread-safe state transitions.

    **Responsibilities:**
    1. Manage 3-state FSM (CLOSED → OPEN → HALF_OPEN → CLOSED)
    2. Track failure/success counts with sliding time windows
    3. Enforce state transition guards (failure threshold, timeout, success threshold)
    4. Provide thread-safe concurrent access (asyncio.Lock)
    5. Export state metrics to Prometheus

    **State Transition Logic:**

    **CLOSED State:**
    - Allow all requests
    - Track failure_count in sliding time_window_ms
    - On failure: failure_count++ → if ≥ failure_threshold → OPEN
    - On success: failure_count = 0 (reset counter)

    **OPEN State:**
    - Reject all requests (fail-fast <1ms)
    - Wait timeout_duration_ms
    - Check timeout elapsed: if time.time() - open_time ≥ timeout → HALF_OPEN

    **HALF_OPEN State:**
    - Allow 1 probe request (first caller wins with lock)
    - Subsequent callers fail-fast (rejected)
    - On probe success: success_count++ → if ≥ success_threshold → CLOSED
    - On probe failure: → OPEN

    **Example Usage:**
    ```python
    fsm = CircuitBreakerFSM(
        service_name="tool_runner",
        failure_threshold=5,
        timeout_duration_ms=30000,
        success_threshold=2,
        slow_call_threshold_ms=5000,
        time_window_ms=60000
    )

    # Check if request allowed
    if await fsm.can_attempt_request():
        try:
            result = await call_service()
            await fsm.record_success()
        except Exception as e:
            await fsm.record_failure(exception=e, latency_ms=1500)
    else:
        # Circuit OPEN, use fallback
        result = await invoke_fallback()
    ```

    **Performance:**
    - State check: <0.1ms (lock + read)
    - State transition: <1ms (update + metric + log)
    - Failure recording: <0.5ms (counter + time window)
    - Memory: <1KB per FSM (state + deque + timers)

    **Thread Safety:**
    - All state transitions use self._state_lock (asyncio.Lock)
    - Failure deque updates protected by lock
    - Time window pruning atomic (single critical section)

    **TODO (@resilience-team):**
    1. Implement __init__() with state initialization
    2. Implement _transition_to_open() with metric export
    3. Implement _transition_to_closed() with metric export
    4. Implement _transition_to_half_open() with metric export
    5. Implement record_failure() with sliding window
    6. Implement record_success() with state-specific logic
    7. Implement can_attempt_request() with guards
    8. Add WARD tests for all state transitions
    9. Add WARD tests for concurrency (10 simultaneous failures)
    10. Document integration with CircuitBreakerManager
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        timeout_duration_ms: int = 30000,
        success_threshold: int = 2,
        slow_call_threshold_ms: int = 3000,
        time_window_ms: int = 60000,
    ):
        """
        Initialize Circuit Breaker FSM.

        **Initialization Steps:**
        1. Set initial state to CLOSED
        2. Initialize failure deque for sliding window
        3. Initialize counters (failure_count, success_count)
        4. Initialize timers (open_time, last_transition_time)
        5. Store configuration thresholds
        6. Create asyncio.Lock for state transitions
        7. Export initial state metric (circuit_breaker_state = 0)

        **Configuration Parameters (ADR-0009b):**
        - failure_threshold: Failures to trigger CLOSED → OPEN (tool_runner=5, k0_bridge=3)
        - timeout_duration_ms: Time in OPEN before → HALF_OPEN (tool_runner=30s, k0_bridge=5s)
        - success_threshold: Successes to trigger HALF_OPEN → CLOSED (tool_runner=2, k0_bridge=1)
        - slow_call_threshold_ms: Latency threshold for slow call (tool_runner=5s, k0_bridge=100ms)
        - time_window_ms: Sliding window for failure counting (tool_runner=60s, k0_bridge=30s)

        **Default Values:**
        - failure_threshold: 5 (moderate tolerance)
        - timeout_duration_ms: 30000 (30s standard recovery)
        - success_threshold: 2 (2 successes to trust recovery)
        - slow_call_threshold_ms: 3000 (3s typical UX threshold)
        - time_window_ms: 60000 (60s window)

        **Sliding Window Implementation:**
        - Use collections.deque for efficient FIFO operations
        - Store FailureRecord(timestamp, failure_type)
        - Prune entries older than time_window_ms on each failure
        - Count = len(deque) (O(1) operation)

        **Thread Safety:**
        - Create asyncio.Lock() for all state transitions
        - Lock protects: state, failure_count, success_count, open_time

        **Performance:**
        - Initialization: <1ms (allocate deque, lock, counters)
        - Memory: ~500B (state + counters + deque + lock)

        **TODO (@resilience-team):**
        1. Set self.state = CircuitBreakerState.CLOSED
        2. Create self.failures = deque() for sliding window
        3. Initialize self.failure_count = 0, self.success_count = 0
        4. Initialize self.open_time = None, self.last_transition_time = time.time()
        5. Store config: self.failure_threshold, self.timeout_duration_ms, etc.
        6. Create self._state_lock = asyncio.Lock()
        7. Export circuit_breaker_state.labels(service=service_name).set(0)
        8. Log INFO "circuit_breaker_fsm_initialized"
        9. Add WARD tests for initialization, config validation

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, k0_bridge, etc.)
            failure_threshold: Failures before CLOSED → OPEN (default: 5)
            timeout_duration_ms: Milliseconds in OPEN before → HALF_OPEN (default: 30000 = 30s)
            success_threshold: Successes in HALF_OPEN before → CLOSED (default: 2)
            slow_call_threshold_ms: Latency threshold for slow call detection (default: 3000 = 3s)
            time_window_ms: Sliding window for failure counting (default: 60000 = 60s)

        Raises:
            ValueError: If thresholds are invalid (e.g., failure_threshold <= 0)
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.timeout_duration_ms = timeout_duration_ms
        self.success_threshold = success_threshold
        self.slow_call_threshold_ms = slow_call_threshold_ms
        self.time_window_ms = time_window_ms

        # State variables
        self.state = CircuitBreakerState.CLOSED
        self.failures: deque[FailureRecord] = deque()
        self.failure_count = 0
        self.success_count = 0
        self.open_time: Optional[float] = None
        self.last_transition_time = time.time()
        self.last_failure_time: Optional[float] = None

        # Concurrency
        self._state_lock = asyncio.Lock()
        self._probe_in_progress = False  # For HALF_OPEN state (only 1 probe allowed)

        # TODO: Export initial metric
        # TODO: Log initialization

        logger.info(
            "circuit_breaker_fsm_initialized",
            service_name=service_name,
            initial_state=self.state.name,
        )

    async def record_success(self, latency_ms: float = 0.0) -> None:
        """
        Record successful call with state-specific logic.

        **State-Specific Behavior:**

        **CLOSED State:**
        - Clear all failures from deque
        - Reset failure_count = 0
        - No state transition

        **OPEN State:**
        - Should not happen (requests rejected in OPEN)
        - Log WARNING "success recorded in OPEN state"

        **HALF_OPEN State:**
        - Increment success_count
        - Check if success_count ≥ success_threshold
        - If threshold met: _transition_to_closed()
        - Clear probe_in_progress flag

        **Performance:**
        - CLOSED: <0.3ms (clear deque + reset counter)
        - HALF_OPEN: <0.5ms (counter + conditional transition)

        **Concurrency:**
        - Acquire self._state_lock for atomic update
        - Multiple simultaneous successes handled correctly

        **Structured Logging (ADR-0009c):**
        ```python
        logger.debug(
            "circuit_breaker_success",
            service=self.service_name,
            state=self.state.name,
            success_count=self.success_count,
            latency_ms=latency_ms
        )
        ```

        **WARD Test Example:**
        ```python
        @test("success in CLOSED resets failure count")
        async def _():
            fsm = CircuitBreakerFSM("test", failure_threshold=3)

            # Record 2 failures
            await fsm.record_failure(Exception(), 100)
            await fsm.record_failure(Exception(), 100)
            assert fsm.failure_count == 2

            # Record success
            await fsm.record_success(50)
            assert fsm.failure_count == 0
            assert fsm.state == CircuitBreakerState.CLOSED
        ```

        **TODO (@resilience-team):**
        1. Acquire self._state_lock
        2. Check current state (CLOSED, OPEN, HALF_OPEN)
        3. CLOSED: Clear self.failures, reset failure_count
        4. HALF_OPEN: Increment success_count, check threshold
        5. HALF_OPEN: If threshold met, call _transition_to_closed()
        6. Clear self._probe_in_progress flag (HALF_OPEN only)
        7. Log DEBUG "circuit_breaker_success"
        8. Release lock
        9. Add WARD tests for all states

        Args:
            latency_ms: Call latency in milliseconds (for logging/metrics)

        Raises:
            None (errors logged, not raised)
        """
        async with self._state_lock:
            # TODO: Implement state-specific success logic
            # TODO: Clear failures in CLOSED
            # TODO: Increment success_count in HALF_OPEN
            # TODO: Check success_threshold, transition if met
            # TODO: Clear probe_in_progress flag

            logger.debug(
                "circuit_breaker_success",
                service_name=self.service_name,
                state=self.state.name,
                latency_ms=latency_ms,
            )

    async def record_failure(
        self, exception: Exception, latency_ms: float = 0.0
    ) -> bool:
        """
        Record failed call with sliding window and state transitions.

        **Failure Classification (ADR-0009a):**
        1. TimeoutError → "timeout"
        2. latency_ms > slow_call_threshold_ms → "slow_call"
        3. Other exceptions → "exception"

        **Sliding Window Logic:**
        1. Create FailureRecord(timestamp=time.time(), failure_type)
        2. Append to self.failures deque
        3. Prune entries older than time_window_ms:
           ```python
           now = time.time()
           window_start = now - (self.time_window_ms / 1000)
           while self.failures and self.failures[0].timestamp < window_start:
               self.failures.popleft()
           ```
        4. Update failure_count = len(self.failures)

        **State-Specific Behavior:**

        **CLOSED State:**
        - Add failure to sliding window
        - Check if failure_count ≥ failure_threshold
        - If threshold met: _transition_to_open() → return True
        - Otherwise: return False

        **OPEN State:**
        - Do nothing (already open)
        - return False

        **HALF_OPEN State:**
        - Probe failed, immediately _transition_to_open()
        - Clear probe_in_progress flag
        - return True

        **Performance:**
        - Failure recording: <0.5ms (deque append + prune + count)
        - State transition: <1ms (if triggered)

        **Concurrency:**
        - Acquire self._state_lock for atomic sliding window + state transition
        - Multiple concurrent failures handled correctly

        **Structured Logging (ADR-0009c):**
        ```python
        logger.warning(
            "circuit_breaker_failure",
            service=self.service_name,
            state=self.state.name,
            failure_type=failure_type,
            failure_count=self.failure_count,
            latency_ms=latency_ms
        )
        ```

        **WARD Test Example:**
        ```python
        @test("5 failures in CLOSED opens circuit")
        async def _():
            fsm = CircuitBreakerFSM("test", failure_threshold=5)

            # Record 4 failures (below threshold)
            for i in range(4):
                opened = await fsm.record_failure(Exception(), 100)
                assert not opened
                assert fsm.state == CircuitBreakerState.CLOSED

            # 5th failure opens circuit
            opened = await fsm.record_failure(Exception(), 100)
            assert opened
            assert fsm.state == CircuitBreakerState.OPEN
        ```

        **TODO (@resilience-team):**
        1. Classify failure type (timeout/slow_call/exception)
        2. Acquire self._state_lock
        3. Create FailureRecord, append to self.failures deque
        4. Prune old entries (older than time_window_ms)
        5. Update self.failure_count = len(self.failures)
        6. Update self.last_failure_time = time.time()
        7. Check state-specific transition logic
        8. CLOSED: If failure_count ≥ threshold, _transition_to_open()
        9. HALF_OPEN: Always _transition_to_open() (probe failed)
        10. Log WARNING "circuit_breaker_failure"
        11. Release lock, return True if transitioned to OPEN
        12. Add WARD tests for sliding window, state transitions

        Args:
            exception: Exception that caused failure
            latency_ms: Call latency in milliseconds

        Returns:
            bool: True if circuit transitioned to OPEN, False otherwise

        Raises:
            None (errors logged, not raised)
        """
        # Classify failure type
        if isinstance(exception, asyncio.TimeoutError):
            failure_type = "timeout"
        elif latency_ms > self.slow_call_threshold_ms:
            failure_type = "slow_call"
        else:
            failure_type = "exception"

        async with self._state_lock:
            # TODO: Create FailureRecord and append to deque
            # TODO: Prune old failures (sliding window)
            # TODO: Update failure_count
            # TODO: Check state-specific transition logic
            # TODO: Call _transition_to_open() if threshold met

            logger.warning(
                "circuit_breaker_failure",
                service_name=self.service_name,
                state=self.state.name,
                failure_type=failure_type,
                failure_count=self.failure_count,
                latency_ms=latency_ms,
            )

            return False  # TODO: Return True if transitioned to OPEN

    async def record_timeout(self, latency_ms: float) -> bool:
        """
        Record timeout (convenience method wrapping record_failure).

        **Behavior:**
        - Create TimeoutError exception
        - Call record_failure(exception, latency_ms)
        - Timeout counts as failure for state transitions

        **Use Case:**
        ```python
        try:
            result = await asyncio.wait_for(call_service(), timeout=5.0)
        except asyncio.TimeoutError:
            opened = await fsm.record_timeout(latency_ms=5000)
        ```

        **TODO (@resilience-team):**
        1. Create asyncio.TimeoutError()
        2. Call record_failure(timeout_error, latency_ms)
        3. Return result from record_failure

        Args:
            latency_ms: Timeout duration in milliseconds

        Returns:
            bool: True if circuit transitioned to OPEN, False otherwise
        """
        return await self.record_failure(asyncio.TimeoutError(), latency_ms)

    async def can_attempt_request(self) -> bool:
        """
        Check if request can be attempted (state guard).

        **State-Specific Guards:**

        **CLOSED State:**
        - Always return True (allow all requests)

        **OPEN State:**
        - Check if timeout elapsed: time.time() - open_time ≥ timeout_duration_ms
        - If timeout elapsed: _transition_to_half_open(), return True (allow probe)
        - Otherwise: return False (fail-fast, reject request)

        **HALF_OPEN State:**
        - If probe_in_progress: return False (only 1 probe allowed, reject others)
        - Otherwise: Set probe_in_progress = True, return True (allow probe)

        **Performance:**
        - CLOSED: <0.05ms (no lock, immediate return True)
        - OPEN: <0.1ms (lock + time check + conditional transition)
        - HALF_OPEN: <0.1ms (lock + flag check)

        **Concurrency:**
        - Acquire self._state_lock for OPEN/HALF_OPEN states
        - CLOSED state fast path (no lock needed)
        - HALF_OPEN probe_in_progress prevents race condition

        **Example Scenarios:**

        **CLOSED (normal):**
        ```python
        # All requests allowed
        assert await fsm.can_attempt_request() == True
        ```

        **OPEN (timeout not elapsed):**
        ```python
        # Circuit opened 10s ago, timeout is 30s
        # 20s remaining before probe
        assert await fsm.can_attempt_request() == False  # Fail-fast
        ```

        **OPEN (timeout elapsed):**
        ```python
        # Circuit opened 30s ago, timeout is 30s
        # Timeout elapsed, transition to HALF_OPEN
        assert await fsm.can_attempt_request() == True  # Allow probe
        assert fsm.state == CircuitBreakerState.HALF_OPEN
        ```

        **HALF_OPEN (first caller):**
        ```python
        # First caller gets probe
        assert await fsm.can_attempt_request() == True
        assert fsm._probe_in_progress == True
        ```

        **HALF_OPEN (subsequent callers):**
        ```python
        # Probe already in progress
        assert await fsm.can_attempt_request() == False  # Rejected
        ```

        **TODO (@resilience-team):**
        1. Check if state is CLOSED, return True (fast path, no lock)
        2. Acquire self._state_lock for OPEN/HALF_OPEN
        3. OPEN: Check if timeout elapsed
        4. OPEN: If elapsed, _transition_to_half_open(), return True
        5. OPEN: Otherwise return False
        6. HALF_OPEN: Check probe_in_progress flag
        7. HALF_OPEN: If probe in progress, return False
        8. HALF_OPEN: Otherwise set probe_in_progress = True, return True
        9. Add WARD tests for all states, timeout edge cases

        Returns:
            bool: True if request can be attempted, False if rejected (fail-fast)

        Raises:
            None (errors logged, not raised)
        """
        # Fast path for CLOSED state (no lock needed)
        if self.state == CircuitBreakerState.CLOSED:
            return True

        async with self._state_lock:
            # TODO: Handle OPEN state (check timeout)
            # TODO: Handle HALF_OPEN state (check probe_in_progress)
            pass

        return False  # TODO: Return proper result based on state

    def get_state(self) -> CircuitBreakerState:
        """
        Get current FSM state (thread-safe read).

        **Performance:**
        - <0.01ms (atomic read, no lock needed in Python due to GIL)

        **Note:**
        - Python GIL makes single attribute reads atomic
        - No lock needed for read-only access

        **Usage:**
        ```python
        state = fsm.get_state()
        if state == CircuitBreakerState.OPEN:
            print("Circuit is OPEN, use fallback")
        ```

        Returns:
            CircuitBreakerState: Current state (CLOSED, OPEN, HALF_OPEN)
        """
        return self.state

    async def _transition_to_open(self) -> None:
        """
        Transition to OPEN state (internal method, lock already held).

        **Transition Actions:**
        1. Set self.state = CircuitBreakerState.OPEN
        2. Set self.open_time = time.time() (for timeout calculation)
        3. Set self.last_transition_time = time.time()
        4. Export circuit_breaker_state.labels(service=service_name).set(1)
        5. Export circuit_breaker_transitions_total.labels(service, from_state, to_state).inc()
        6. Log WARNING "circuit_breaker_opened"

        **Structured Logging (ADR-0009c):**
        ```python
        logger.warning(
            "circuit_breaker_opened",
            service=self.service_name,
            failure_count=self.failure_count,
            failure_threshold=self.failure_threshold,
            time_window_ms=self.time_window_ms
        )
        ```

        **Performance:**
        - <1ms (state update + 2 metrics + log)

        **TODO (@resilience-team):**
        1. Set self.state = CircuitBreakerState.OPEN
        2. Set self.open_time = time.time()
        3. Update self.last_transition_time
        4. Export circuit_breaker_state metric (set to 1)
        5. Export circuit_breaker_transitions_total counter
        6. Log WARNING "circuit_breaker_opened"
        7. Add WARD tests for metric export, logging

        Raises:
            None (errors logged, not raised)
        """
        old_state = self.state
        self.state = CircuitBreakerState.OPEN
        self.open_time = time.time()
        self.last_transition_time = time.time()

        # TODO: Export metrics
        # TODO: Log warning

        logger.warning(
            "circuit_breaker_opened",
            service_name=self.service_name,
            from_state=old_state.name,
            failure_count=self.failure_count,
        )

    async def _transition_to_half_open(self) -> None:
        """
        Transition to HALF_OPEN state (internal method, lock already held).

        **Transition Actions:**
        1. Set self.state = CircuitBreakerState.HALF_OPEN
        2. Reset self.success_count = 0 (prepare for probe)
        3. Clear self._probe_in_progress = False
        4. Set self.last_transition_time = time.time()
        5. Export circuit_breaker_state.labels(service=service_name).set(2)
        6. Export circuit_breaker_transitions_total.labels(service, from_state, to_state).inc()
        7. Log INFO "circuit_breaker_half_open"

        **Performance:**
        - <1ms (state update + 2 metrics + log)

        **TODO (@resilience-team):**
        1. Set self.state = CircuitBreakerState.HALF_OPEN
        2. Reset self.success_count = 0
        3. Clear self._probe_in_progress = False
        4. Update self.last_transition_time
        5. Export circuit_breaker_state metric (set to 2)
        6. Export circuit_breaker_transitions_total counter
        7. Log INFO "circuit_breaker_half_open"

        Raises:
            None (errors logged, not raised)
        """
        old_state = self.state
        self.state = CircuitBreakerState.HALF_OPEN
        self.success_count = 0
        self._probe_in_progress = False
        self.last_transition_time = time.time()

        # TODO: Export metrics

        logger.info(
            "circuit_breaker_half_open",
            service_name=self.service_name,
            from_state=old_state.name,
        )

    async def _transition_to_closed(self) -> None:
        """
        Transition to CLOSED state (internal method, lock already held).

        **Transition Actions:**
        1. Set self.state = CircuitBreakerState.CLOSED
        2. Clear self.failures.clear() (reset sliding window)
        3. Reset self.failure_count = 0
        4. Reset self.success_count = 0
        5. Clear self.open_time = None
        6. Set self.last_transition_time = time.time()
        7. Export circuit_breaker_state.labels(service=service_name).set(0)
        8. Export circuit_breaker_transitions_total.labels(service, from_state, to_state).inc()
        9. Log INFO "circuit_breaker_closed"

        **Performance:**
        - <1ms (state update + deque clear + 2 metrics + log)

        **TODO (@resilience-team):**
        1. Set self.state = CircuitBreakerState.CLOSED
        2. Clear self.failures.clear()
        3. Reset counters (failure_count, success_count)
        4. Clear self.open_time
        5. Update self.last_transition_time
        6. Export circuit_breaker_state metric (set to 0)
        7. Export circuit_breaker_transitions_total counter
        8. Log INFO "circuit_breaker_closed"

        Raises:
            None (errors logged, not raised)
        """
        old_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failures.clear()
        self.failure_count = 0
        self.success_count = 0
        self.open_time = None
        self.last_transition_time = time.time()

        # TODO: Export metrics

        logger.info(
            "circuit_breaker_closed",
            service_name=self.service_name,
            from_state=old_state.name,
        )


# ============================================================================
# EXPECTED LINT ERRORS (STUB FILE)
# ============================================================================
"""
**Expected Errors (will be resolved during implementation):**

1. Incomplete implementations with TODO comments:
   - record_success() body incomplete
   - record_failure() body incomplete
   - can_attempt_request() body incomplete
   - _transition_to_open() metric export missing
   - _transition_to_half_open() metric export missing
   - _transition_to_closed() metric export missing

2. Missing metric imports:
   - export_gauge, export_counter from k1.obs.metrics
   - Prometheus client metrics need to be imported

3. Return value inconsistencies:
   - record_failure() always returns False (should return True when transitioning)
   - can_attempt_request() always returns False (should return based on state)

4. TODO comments:
   - 40+ TODO markers for @resilience-team implementation

**Implementation Dependencies:**
- Epic 4.1.1: circuit_breaker_manager.py (CircuitBreakerManager, Prometheus metrics)
- K1 Core: obs.metrics (metric export), obs.tracing (trace_id)

**Testing Requirements:**
- WARD framework with 100% coverage target
- Test categories:
  1. State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
  2. Sliding window (failure pruning, time window edge cases)
  3. Concurrency (10 simultaneous failures, race conditions)
  4. Guards (can_attempt_request in all states, timeout edge cases)
  5. Probe logic (HALF_OPEN first caller wins, subsequent rejected)
  6. Metric export (state gauge, transition counter)
  7. Performance (state check <0.1ms, transition <1ms)
"""
