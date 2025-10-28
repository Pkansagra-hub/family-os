"""
K1 Circuit Breaker Call Wrapper

Wraps service calls with circuit breaker protection, providing state checking, timeout
enforcement, fallback invocation, and comprehensive error handling.

**Architecture Context:**
- Layer 5 (Infrastructure): Resilience primitives
- Implements ADR-0009 (Circuit Breaker Pattern) call protection wrapper
- Integrates with CircuitBreakerFSM for state checking
- Provides fallback strategies for graceful degradation

**Call Protection Flow:**
```
1. Check circuit state (can_attempt_request)
   ├─ CLOSED: Proceed to step 2
   ├─ OPEN: Jump to step 6 (fallback/raise)
   └─ HALF_OPEN: Allow probe (first caller), reject others (step 6)

2. Start timer (measure latency)

3. Execute operation with timeout
   └─ asyncio.wait_for(operation(), timeout_ms)

4. Calculate latency

5. On success:
   ├─ Record success (fsm.record_success(latency_ms))
   ├─ Export metrics (circuit_breaker_calls_total{result="success"})
   └─ Return result

6. On failure/timeout/rejected:
   ├─ Record failure (fsm.record_failure(exception, latency_ms))
   ├─ Export metrics (circuit_breaker_calls_total{result="failure"/"rejected"})
   ├─ Check fallback_strategy:
   │   ├─ DEFAULT_VALUE → return default value
   │   ├─ CACHED_RESULT → Redis lookup
   │   ├─ ALTERNATE_SERVICE → call alternate circuit
   │   └─ RAISE_ERROR → raise CircuitOpenError/exception
   └─ Return fallback or raise
```

**Fallback Strategies (ADR-0009a):**
1. **DEFAULT_VALUE**: Return empty list/None (<1ms)
   - Use case: Optional operations (tool results, MCP responses)
   - Example: `fallback_value=[]` for tool_runner

2. **CACHED_RESULT**: Redis lookup with cache_key (<10ms)
   - Use case: LLM responses (5min TTL)
   - Example: `cache_key="llm:gpt4o:prompt_hash:abc123"`

3. **ALTERNATE_SERVICE**: Call different circuit (<500ms)
   - Use case: Local → remote LLM failover
   - Example: `alternate_service="model_hub_remote"`

4. **RAISE_ERROR**: No fallback, explicit error
   - Use case: Critical path (K0 Bridge, streaming)
   - Raises: `CircuitOpenError` with service details

**Performance Budgets (ADR-0009a):**
- State check: <0.1ms (can_attempt_request)
- Timeout setup: <0.1ms (asyncio.wait_for)
- Metric export: <0.1ms (Prometheus counter)
- Fallback (default): <1ms
- Fallback (cached): <10ms (Redis)
- Fallback (alternate): <500ms (remote service)
- Total overhead CLOSED: <5ms (target 3ms)
- Total overhead OPEN: <1ms (target 0.5ms)

**Latency Budget Impact (ADR-0009):**
- TTFT baseline: 140ms → 142ms with circuit breaker (+2ms, 1.4% overhead)
- E2E baseline: 1850ms → 1860ms with circuit breaker (+10ms, 0.5% overhead)
- Tool call baseline: 2800ms → 2810ms with circuit breaker (+10ms, 0.4% overhead)
- **Fail-fast benefit**: Tool call failure: 2800ms → 10ms (-2790ms, 99.6% faster!)

**ADR References:**
- ADR-0009: Circuit Breaker Pattern (wrapper architecture)
- ADR-0009a: FSM Implementation (fallback strategies)
- ADR-0009c: Metrics & Observability (call metrics, latency histogram)

**Issue:** Epic 4.1.3 - Milestone 4 (Circuit Breaker) - P1 Important for Reliability
**Status:** STUB - Implementation by @resilience-team
**Last Updated:** 2025-10-13
"""

import logging
from typing import Any, Awaitable, Callable, Optional, TypeVar

# K1 imports (stub references - actual imports validated during implementation)
# from k1.l5_infrastructure.resilience.circuit_fsm import CircuitBreakerFSM, CircuitBreakerState
# from k1.l5_infrastructure.resilience.exceptions import CircuitOpenError
# from k1.l4_runtime.session_state.state_manager import get_redis_client
# from k1.obs.metrics import export_counter, export_histogram
# from k1.obs.tracing import start_span, get_trace_id

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================================
# EXCEPTIONS
# ============================================================================


class CircuitOpenError(Exception):
    """
    Raised when circuit breaker is OPEN and no fallback available.

    **Attributes:**
    - service_name: Service that circuit protects
    - failure_count: Number of failures that triggered OPEN
    - open_time: Timestamp when circuit opened (epoch seconds)
    - timeout_remaining_ms: Milliseconds until HALF_OPEN probe

    **Example:**
    ```python
    try:
        result = await call_with_protection(circuit, operation)
    except CircuitOpenError as e:
        logger.error(
            "Circuit open, no fallback available",
            service=e.service_name,
            failures=e.failure_count,
            timeout_remaining=e.timeout_remaining_ms
        )
    ```
    """

    def __init__(
        self,
        service_name: str,
        failure_count: int,
        open_time: float,
        timeout_remaining_ms: int,
    ):
        self.service_name = service_name
        self.failure_count = failure_count
        self.open_time = open_time
        self.timeout_remaining_ms = timeout_remaining_ms

        super().__init__(
            f"Circuit breaker OPEN for {service_name}: "
            f"{failure_count} failures, "
            f"retry in {timeout_remaining_ms}ms"
        )


# ============================================================================
# CALL WRAPPER
# ============================================================================


async def call_with_protection(
    circuit_breaker: Any,  # CircuitBreakerFSM when implemented
    operation: Callable[[], Awaitable[T]],
    timeout_ms: int = 5000,
    fallback_fn: Optional[Callable[[], Awaitable[T]]] = None,
    fallback_value: Optional[T] = None,
    cache_key: Optional[str] = None,
    alternate_service: Optional[str] = None,
    cognitive_trace_id: Optional[str] = None,
) -> T:
    """
    Execute operation with circuit breaker protection.

    **Execution Flow:**
    1. Start trace span with cognitive_trace_id
    2. Check circuit.can_attempt_request()
       - If False (OPEN/rejected): Jump to fallback (step 8)
       - If True (CLOSED/HALF_OPEN): Proceed
    3. Start latency timer (time.time())
    4. Execute operation with asyncio.wait_for(operation(), timeout_ms/1000)
    5. Calculate latency_ms = (end - start) * 1000
    6. On success:
       - Record success: await circuit.record_success(latency_ms)
       - Export metric: circuit_breaker_calls_total{service, result="success"}
       - Export histogram: circuit_breaker_latency_ms{service, state}
       - Log DEBUG: "circuit_breaker_call_success"
       - Return result
    7. On exception (timeout/failure):
       - Record failure: await circuit.record_failure(exception, latency_ms)
       - Export metric: circuit_breaker_calls_total{service, result="failure"}
       - Export histogram: circuit_breaker_latency_ms{service, state}
       - Log WARNING: "circuit_breaker_call_failure"
       - Proceed to fallback (step 8)
    8. Invoke fallback based on configuration:
       - fallback_fn provided: Execute fallback_fn()
       - fallback_value provided: Return fallback_value
       - cache_key provided: Redis lookup with cache_key
       - alternate_service provided: Call alternate circuit
       - No fallback: Raise CircuitOpenError or propagate exception

    **Fallback Strategy Examples:**

    **DEFAULT_VALUE (tool_runner):**
    ```python
    result = await call_with_protection(
        circuit_breaker=circuit,
        operation=call_weather_api,
        fallback_value=[]  # Empty list for missing tool results
    )
    ```

    **CACHED_RESULT (model_hub_remote):**
    ```python
    result = await call_with_protection(
        circuit_breaker=circuit,
        operation=call_llm,
        cache_key=f"llm:gpt4o:{prompt_hash}"  # Redis lookup
    )
    ```

    **ALTERNATE_SERVICE (model_hub_local):**
    ```python
    result = await call_with_protection(
        circuit_breaker=circuit,
        operation=call_local_llm,
        alternate_service="model_hub_remote"  # Fallback to remote
    )
    ```

    **RAISE_ERROR (k0_bridge):**
    ```python
    try:
        result = await call_with_protection(
            circuit_breaker=circuit,
            operation=write_to_k0_wal,
            # No fallback parameters → raises CircuitOpenError
        )
    except CircuitOpenError:
        # Abort saga, alert operator
        await saga.abort()
    ```

    **Performance:**
    - CLOSED state: operation latency + <5ms overhead
    - OPEN state (fallback): <1ms (default) to <500ms (alternate service)
    - HALF_OPEN state: operation latency + <10ms overhead (probe validation)

    **Observability (ADR-0009c):**
    - Metric: circuit_breaker_calls_total{service, result="success"/"failure"/"rejected"}
    - Metric: circuit_breaker_latency_ms{service, state} histogram
    - Trace: span circuit_breaker.call with attributes (service, state, result, latency_ms)
    - Log DEBUG: "circuit_breaker_call_success" with latency
    - Log WARNING: "circuit_breaker_call_failure" with exception, latency

    **Concurrency:**
    - Multiple simultaneous calls to same circuit are thread-safe
    - HALF_OPEN probe uses lock (only 1 caller wins, others rejected)

    **Error Handling:**
    - TimeoutError: Recorded as failure, fallback invoked
    - Exception: Recorded as failure, fallback invoked
    - CircuitOpenError: Raised only if no fallback available

    **WARD Test Examples:**
    ```python
    @test("call succeeds in CLOSED state")
    async def _():
        circuit = CircuitBreakerFSM("test", failure_threshold=5)

        result = await call_with_protection(
            circuit_breaker=circuit,
            operation=lambda: asyncio.sleep(0.1) or "success"
        )

        assert result == "success"
        assert circuit.get_state() == CircuitBreakerState.CLOSED

    @test("call uses fallback in OPEN state")
    async def _():
        circuit = CircuitBreakerFSM("test", failure_threshold=3)

        # Open circuit with 3 failures
        for i in range(3):
            try:
                await call_with_protection(
                    circuit_breaker=circuit,
                    operation=lambda: asyncio.sleep(0.01) or (_ for _ in ()).throw(Exception())
                )
            except:
                pass

        # Circuit now OPEN, use fallback
        result = await call_with_protection(
            circuit_breaker=circuit,
            operation=lambda: "should not execute",
            fallback_value="fallback result"
        )

        assert result == "fallback result"
        assert circuit.get_state() == CircuitBreakerState.OPEN

    @test("call raises CircuitOpenError without fallback")
    async def _():
        circuit = CircuitBreakerFSM("test", failure_threshold=3)

        # Open circuit
        for i in range(3):
            try:
                await call_with_protection(
                    circuit_breaker=circuit,
                    operation=lambda: (_ for _ in ()).throw(Exception())
                )
            except:
                pass

        # No fallback provided, should raise
        with raises(CircuitOpenError) as exc_info:
            await call_with_protection(
                circuit_breaker=circuit,
                operation=lambda: "should not execute"
            )

        assert exc_info.raised.service_name == "test"
        assert exc_info.raised.failure_count == 3
    ```

    **TODO (@resilience-team):**
    1. Start trace span with start_span("circuit_breaker.call", cognitive_trace_id)
    2. Check await circuit_breaker.can_attempt_request()
    3. If rejected (False), jump to fallback logic
    4. Start timer: start_time = time.time()
    5. Execute: result = await asyncio.wait_for(operation(), timeout=timeout_ms/1000)
    6. Calculate: latency_ms = (time.time() - start_time) * 1000
    7. On success: await circuit_breaker.record_success(latency_ms)
    8. On exception: await circuit_breaker.record_failure(exception, latency_ms)
    9. Export metrics: circuit_breaker_calls_total, circuit_breaker_latency_ms
    10. Implement fallback logic (fallback_fn, fallback_value, cache_key, alternate_service)
    11. Log structured events (DEBUG success, WARNING failure)
    12. Add WARD tests for all fallback strategies, timeout, concurrency

    Args:
        circuit_breaker: CircuitBreakerFSM instance for state checking
        operation: Async function to execute (e.g., call_weather_api)
        timeout_ms: Operation timeout in milliseconds (default: 5000ms = 5s)
        fallback_fn: Optional async fallback function (executed if circuit OPEN)
        fallback_value: Optional fallback value (returned if circuit OPEN)
        cache_key: Optional Redis cache key (for CACHED_RESULT strategy)
        alternate_service: Optional alternate service name (for ALTERNATE_SERVICE strategy)
        cognitive_trace_id: Optional trace ID for OpenTelemetry spans

    Returns:
        T: Result from operation() or fallback

    Raises:
        CircuitOpenError: If circuit OPEN and no fallback provided
        TimeoutError: If operation exceeds timeout_ms (after fallback attempts)
        Exception: Any exception from operation() (after fallback attempts)

    Examples:
        # Simple call with default value fallback
        result = await call_with_protection(
            circuit_breaker=tool_circuit,
            operation=lambda: call_weather_api("SF"),
            fallback_value=[]
        )

        # Call with cached result fallback
        result = await call_with_protection(
            circuit_breaker=llm_circuit,
            operation=lambda: call_llm(prompt),
            cache_key=f"llm:gpt4o:{hash(prompt)}"
        )

        # Call with custom fallback function
        result = await call_with_protection(
            circuit_breaker=service_circuit,
            operation=lambda: call_service(),
            fallback_fn=lambda: call_backup_service()
        )
    """
    service_name = getattr(circuit_breaker, "service_name", "unknown")

    # TODO: Start trace span
    # TODO: Check can_attempt_request()
    # TODO: If rejected, jump to fallback
    # TODO: Start timer
    # TODO: Execute operation with timeout
    # TODO: Calculate latency
    # TODO: Record success/failure
    # TODO: Export metrics
    # TODO: Invoke fallback if needed
    # TODO: Log structured events

    logger.debug(
        "call_with_protection",
        service_name=service_name,
        timeout_ms=timeout_ms,
        has_fallback=fallback_fn is not None
        or fallback_value is not None
        or cache_key is not None,
    )

    raise NotImplementedError("call_with_protection not yet implemented")


async def _invoke_fallback(
    service_name: str,
    fallback_fn: Optional[Callable[[], Awaitable[T]]] = None,
    fallback_value: Optional[T] = None,
    cache_key: Optional[str] = None,
    alternate_service: Optional[str] = None,
) -> T:
    """
    Invoke fallback based on configuration (internal helper).

    **Fallback Priority:**
    1. fallback_fn (highest priority, custom logic)
    2. fallback_value (simple default value)
    3. cache_key (Redis lookup)
    4. alternate_service (call different circuit)
    5. None (raise CircuitOpenError)

    **Performance:**
    - fallback_fn: <operation latency> (custom)
    - fallback_value: <1ms (immediate return)
    - cache_key: <10ms (Redis GET)
    - alternate_service: <500ms (remote call)

    **TODO (@resilience-team):**
    1. Check fallback_fn, execute if provided
    2. Check fallback_value, return if provided
    3. Check cache_key, Redis GET if provided
    4. Check alternate_service, call alternate circuit if provided
    5. No fallback: raise CircuitOpenError
    6. Export circuit_breaker_fallbacks_total{service, strategy}
    7. Log WARNING "circuit_breaker_fallback_invoked"

    Args:
        service_name: Service identifier (for logging, metrics)
        fallback_fn: Optional custom fallback function
        fallback_value: Optional default value
        cache_key: Optional Redis cache key
        alternate_service: Optional alternate service name

    Returns:
        T: Fallback result

    Raises:
        CircuitOpenError: If no fallback provided
    """
    # TODO: Implement fallback priority logic
    # TODO: Export fallback metric
    # TODO: Log fallback invocation

    logger.warning(
        "circuit_breaker_fallback_invoked",
        service_name=service_name,
        has_fallback_fn=fallback_fn is not None,
        has_fallback_value=fallback_value is not None,
        has_cache_key=cache_key is not None,
        has_alternate_service=alternate_service is not None,
    )

    raise NotImplementedError("_invoke_fallback not yet implemented")


# ============================================================================
# EXPECTED LINT ERRORS (STUB FILE)
# ============================================================================
"""
**Expected Errors (will be resolved during implementation):**

1. NotImplementedError in functions:
   - call_with_protection() body incomplete
   - _invoke_fallback() body incomplete

2. Missing imports:
   - CircuitBreakerFSM, CircuitBreakerState from circuit_fsm.py
   - get_redis_client from session_state
   - export_counter, export_histogram from obs.metrics
   - start_span, get_trace_id from obs.tracing

3. Type: Any for circuit_breaker parameter:
   - Should be CircuitBreakerFSM when implemented

4. Incomplete fallback logic:
   - Redis cache lookup not implemented
   - Alternate service call not implemented
   - CircuitOpenError construction incomplete

5. Missing metric exports:
   - circuit_breaker_calls_total counter
   - circuit_breaker_latency_ms histogram
   - circuit_breaker_fallbacks_total counter

6. TODO comments:
   - 30+ TODO markers for @resilience-team implementation

**Implementation Dependencies:**
- Epic 4.1.2: circuit_fsm.py (CircuitBreakerFSM, can_attempt_request, record_success/failure)
- Epic 4.1.1: circuit_breaker_manager.py (Prometheus metrics)
- Epic 4.1.4: state_persistence.py (Redis client for cached fallback)
- K1 Core: obs.metrics (counters, histograms), obs.tracing (spans)

**Testing Requirements:**
- WARD framework with 100% coverage target
- Test categories:
  1. Call success in CLOSED state (operation executed, success recorded)
  2. Call failure in CLOSED state (failure recorded, exception propagated)
  3. Call timeout (TimeoutError, timeout recorded)
  4. Fallback strategies (all 4: default_value, cached_result, alternate_service, raise_error)
  5. Circuit OPEN rejection (can_attempt_request returns False)
  6. HALF_OPEN probe (first caller wins, subsequent rejected)
  7. Metrics export (calls_total, latency_ms, fallbacks_total)
  8. Trace spans (circuit_breaker.call with attributes)
  9. Performance (overhead <5ms in CLOSED, <1ms in OPEN)
  10. Concurrency (10 simultaneous calls, thread-safe)
"""
