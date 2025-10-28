"""
K1 Circuit Breaker Manager

Core orchestrator managing circuit breaker instances per service, coordinating FSM state
transitions, tracking failure counts/timers, and exporting observability metrics.

**Architecture Context:**
- Layer 5 (Infrastructure): Resilience primitives providing failure isolation
- Implements ADR-0009 (Circuit Breaker Pattern) 3-state FSM design
- Coordinates with Tool Runner, Model Hub, K0 Bridge, MCP Gateway, Streaming Engine
- Prevents cascading failures (retry storms, thread exhaustion, latency violations)

**Failure Scenarios Prevented:**
1. Retry storms: 100 sessions × 5 retries = 500 wasted requests → 3 failures then fail-fast
2. Thread exhaustion: 32 threads blocked on 30s timeouts → freed in <1ms
3. Latency violations: 5s timeout blocks TTFT 150ms budget → fail-fast maintains budget
4. Saga timeouts: Compensation times out on tool failure → abort gracefully with fallback

**State Machine (ADR-0009, ADR-0009a):**
- CLOSED: Normal operation, track failure_count, transition to OPEN when threshold reached
- OPEN: Reject all requests immediately (<1ms), invoke fallback, transition to HALF_OPEN after timeout
- HALF_OPEN: Allow 1 probe request, transition to CLOSED on success or OPEN on failure

**Performance Budgets:**
- Circuit lookup: <1ms (target 0.5ms)
- State transition: <1ms (target 0.5ms)
- Operation overhead CLOSED: <5ms (target 3ms)
- Operation overhead OPEN: <1ms (target 0.5ms)
- Metric emission: <1ms (target 0.7ms)

**ADR References:**
- ADR-0009: Circuit Breaker Pattern (3-state FSM, failure scenarios, protected services)
- ADR-0009a: FSM Implementation (state transitions, concurrency, fallback strategies)
- ADR-0009b: Per-Service Configuration (6 services, different thresholds, hot-reload)
- ADR-0009c: Metrics & Observability (Prometheus metrics, alerts, Grafana dashboards)

**Related ADRs:**
- ADR-0008: Saga Pattern (compensation handling when circuit OPEN)
- ADR-0011: Tool Runner Architecture (per-tool circuit breakers)
- ADR-0015: Model Hub Architecture (per-model circuit breakers)

**Issue:** Epic 4.1.1 - Milestone 4 (Circuit Breaker) - P1 Important for Reliability
**Status:** STUB - Implementation by @resilience-team
**Last Updated:** 2025-10-13
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

from prometheus_client import Counter, Gauge, Histogram

# K1 imports (stub references - actual imports will be validated during implementation)
# from k1.l5_infrastructure.resilience.circuit_fsm import CircuitBreakerFSM, CircuitBreakerState
# from k1.l5_infrastructure.resilience.call_wrapper import call_with_protection
# from k1.l5_infrastructure.resilience.state_persistence import StatePersistence
# from k1.l4_runtime.session_state.state_manager import get_redis_client
# from k1.obs.tracing import start_span, get_trace_id

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================


class FallbackStrategy(Enum):
    """
    Fallback strategies when circuit is OPEN (ADR-0009a).

    **Strategy Selection:**
    - DEFAULT_VALUE: Optional operations (tools, MCP), return empty list/None
    - CACHED_RESULT: LLM responses with Redis 5min TTL, graceful degradation
    - ALTERNATE_SERVICE: Local → remote LLM, maintains functionality
    - RAISE_ERROR: Critical path (K0 Bridge), no silent failures, abort saga
    """

    DEFAULT_VALUE = "default_value"  # Return empty list/None (<1ms)
    CACHED_RESULT = "cached_result"  # Redis lookup (<10ms, 5min TTL)
    ALTERNATE_SERVICE = "alternate_service"  # Fallback endpoint (<500ms)
    RAISE_ERROR = "raise_error"  # No fallback, explicit error


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for a single circuit breaker (ADR-0009b).

    **Configuration Sources:**
    - YAML: k1/config/circuit_breakers.yml (per-service configs)
    - Defaults: Provided by ConfigManager for missing services
    - Hot-reload: File watcher triggers reload_configs() on YAML changes

    **Per-Service Tuning (ADR-0009b):**
    - tool_runner: 5 failures, 30s timeout, 5s slow, default_value fallback
    - model_hub_local: 3 failures, 10s timeout, 1s slow, alternate_model fallback
    - model_hub_remote: 5 failures, 60s timeout, 10s slow, cached_result fallback
    - k0_bridge: 3 failures, 5s timeout, 100ms slow, raise_error (critical path)
    - mcp_gateway: 5 failures, 30s timeout, 3s slow, default_value fallback
    - streaming_engine: 3 failures, 10s timeout, 5s slow, raise_error (stateful)
    """

    service_name: str
    failure_threshold: int  # Failures to trigger CLOSED → OPEN
    timeout_duration_ms: int  # Timeout before OPEN → HALF_OPEN (ms)
    success_threshold: int  # Successes to trigger HALF_OPEN → CLOSED
    slow_call_threshold_ms: int  # Latency threshold for slow call detection (ms)
    time_window_ms: int  # Time window for failure counting (ms)
    fallback_strategy: FallbackStrategy
    alternate_service: Optional[str] = None  # For ALTERNATE_SERVICE strategy
    cache_ttl_ms: Optional[int] = None  # For CACHED_RESULT strategy (5min = 300000ms)
    enabled: bool = True  # Circuit breaker enabled flag


@dataclass
class CircuitHealth:
    """
    Health information for a circuit breaker.

    **Metrics Included:**
    - state: Current FSM state (CLOSED=0, OPEN=1, HALF_OPEN=2)
    - failure_count: Current failure count in time window
    - success_count: Current success count (for HALF_OPEN → CLOSED)
    - last_failure_time: Timestamp of most recent failure (epoch seconds)
    - last_transition_time: Timestamp of most recent state transition (epoch seconds)
    - total_calls: Total calls through circuit (lifetime)
    - total_failures: Total failures recorded (lifetime)
    - total_fallbacks: Total fallback invocations (lifetime)
    - success_rate: Success rate in last 5 minutes (0.0-1.0)
    """

    service_name: str
    state: str  # "CLOSED", "OPEN", "HALF_OPEN"
    failure_count: int
    success_count: int
    last_failure_time: Optional[float]
    last_transition_time: float
    total_calls: int
    total_failures: int
    total_fallbacks: int
    success_rate: float  # 0.0 to 1.0


# ============================================================================
# PROMETHEUS METRICS (ADR-0009c)
# ============================================================================

# Metric 1: Circuit Breaker State (Gauge)
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["service"],
)

# Metric 2: Circuit Breaker Transitions (Counter)
circuit_breaker_transitions_total = Counter(
    "circuit_breaker_transitions_total",
    "Total circuit breaker state transitions",
    ["service", "from_state", "to_state"],
)

# Metric 3: Circuit Breaker Calls (Counter)
circuit_breaker_calls_total = Counter(
    "circuit_breaker_calls_total",
    "Total calls through circuit breaker",
    ["service", "result"],  # result = success|failure|rejected
)

# Metric 4: Circuit Breaker Failures (Counter)
circuit_breaker_failures_total = Counter(
    "circuit_breaker_failures_total",
    "Total failures detected by circuit breaker",
    ["service", "failure_type"],  # failure_type = timeout|exception|slow_call
)

# Metric 5: Circuit Breaker Fallbacks (Counter)
circuit_breaker_fallbacks_total = Counter(
    "circuit_breaker_fallbacks_total",
    "Total fallback invocations",
    ["service", "fallback_strategy"],
)

# Metric 6: Circuit Breaker Latency (Histogram)
circuit_breaker_latency_ms = Histogram(
    "circuit_breaker_latency_ms",
    "Circuit breaker call latency in milliseconds",
    ["service", "state"],
    buckets=[0.1, 1, 10, 50, 100, 500, 1000, 5000, 10000],
)


# ============================================================================
# CIRCUIT BREAKER MANAGER
# ============================================================================


class CircuitBreakerManager:
    """
    Core circuit breaker orchestrator managing FSM instances per service.

    **Responsibilities:**
    1. Load configuration from circuit_breakers.yml (6 services)
    2. Create/manage CircuitBreakerFSM instances per service
    3. Provide call_with_circuit_breaker() API for protected operations
    4. Track service health (state, failures, success rate)
    5. Support admin operations (reset, pause, resume)
    6. Export Prometheus metrics (6 metrics per ADR-0009c)
    7. Persist state to Redis for recovery across restarts

    **Protected Services (ADR-0009b):**
    - tool_runner: External tool APIs (1-5s latency, transient failures)
    - model_hub_local: On-device LLM (100-500ms, permanent failures)
    - model_hub_remote: Cloud LLM (300-800ms, network failures)
    - k0_bridge: Local kernel (<10ms, critical path)
    - mcp_gateway: External MCP servers (100-3000ms, low reliability)
    - streaming_engine: SSE stream (50-5000ms, stateful connections)

    **Integration Points:**
    - Tool Runner: Wraps all external tool calls with tool_runner circuit
    - Model Hub: Wraps LLM calls with model_hub_local/remote circuits
    - K0 Bridge: Wraps WAL writes with k0_bridge circuit (no fallback)
    - MCP Gateway: Wraps MCP calls with mcp_gateway circuit (default_value fallback)
    - Streaming Engine: Wraps SSE streams with streaming_engine circuit (no fallback)

    **Thread Safety (ADR-0009a):**
    - All state transitions use asyncio.Lock for atomic updates
    - Concurrent calls through same circuit are thread-safe
    - ConfigManager reload is thread-safe with asyncio.Lock

    **Example Usage:**
    ```python
    manager = CircuitBreakerManager(config_path="k1/config/circuit_breakers.yml")

    # Wrap tool call with circuit breaker
    result = await manager.call_with_circuit_breaker(
        service_name="tool_runner",
        func=call_weather_api,
        args=("San Francisco",),
        kwargs={"units": "metric"}
    )

    # Get service health
    health = await manager.get_service_health("tool_runner")
    print(f"State: {health.state}, Success Rate: {health.success_rate:.2%}")

    # Reset circuit to CLOSED (admin operation)
    await manager.reset_service("tool_runner")
    ```

    **Performance:**
    - Circuit lookup: <1ms (dict lookup)
    - call_with_circuit_breaker() overhead: <5ms (CLOSED), <1ms (OPEN)
    - get_service_health(): <1ms (read FSM state)
    - reset_service(): <2ms (state transition + metric)

    **TODO (@resilience-team):**
    1. Implement __init__() to load configs and create FSM instances
    2. Implement get_circuit_breaker() with lazy initialization
    3. Implement call_with_circuit_breaker() with state check + timeout + fallback
    4. Implement get_service_health() to aggregate FSM state + metrics
    5. Implement reset_service() for admin circuit reset
    6. Add ConfigManager integration for hot-reload
    7. Add StatePersistence integration for Redis recovery
    8. Add structured logging for all state transitions (ADR-0009c)
    9. Add WARD tests for all methods (100% coverage target)
    10. Document integration patterns with Tool Runner, Model Hub, K0 Bridge
    """

    def __init__(self, config_path: str = "k1/config/circuit_breakers.yml"):
        """
        Initialize CircuitBreakerManager.

        **Initialization Steps:**
        1. Load circuit_breakers.yml configuration
        2. Parse per-service configs (6 services)
        3. Create CircuitBreakerFSM instance for each service
        4. Initialize Redis client for state persistence
        5. Recover circuit state from Redis (if exists)
        6. Start ConfigManager file watcher for hot-reload
        7. Export initial metrics (circuit_breaker_state = 0 for all)
        8. Log initialization complete

        **Configuration Loading:**
        - YAML file: k1/config/circuit_breakers.yml
        - Schema: services[service_name] = {failure_threshold, timeout_duration_ms, ...}
        - Validation: Ensure all required fields present, use defaults if missing
        - Example:
          ```yaml
          services:
            tool_runner:
              failure_threshold: 5
              timeout_duration_ms: 30000
              success_threshold: 2
              slow_call_threshold_ms: 5000
              time_window_ms: 60000
              fallback_strategy: default_value
              enabled: true
          ```

        **State Recovery (ADR-0009, StatePersistence):**
        - Redis keys: circuit:state:{service_name}, circuit:failures:{service_name}
        - Load state for each service, set FSM state
        - If Redis unavailable, start with CLOSED state
        - Log recovery: "Circuit breaker state recovered from Redis for {service}"

        **Performance:**
        - Initialization time: <100ms (6 services, Redis check)
        - Memory overhead: <10KB (6 FSM instances, config objects)

        **Error Handling:**
        - YAML parse error: Log error, fall back to default configs
        - Redis unavailable: Log warning, continue with CLOSED state
        - Invalid config: Log error, use default thresholds

        **TODO (@resilience-team):**
        1. Load YAML with yaml.safe_load()
        2. Parse services section, create CircuitBreakerConfig objects
        3. Create CircuitBreakerFSM(config) for each service
        4. Initialize StatePersistence(redis_client)
        5. Call state_persistence.recover_state(service_name) for each service
        6. Start ConfigManager file watcher (watchdog library)
        7. Export circuit_breaker_state.labels(service=name).set(0) for each
        8. Add WARD tests for init, config loading, state recovery

        Args:
            config_path: Path to circuit_breakers.yml (relative or absolute)

        Raises:
            FileNotFoundError: If config file not found (TODO: fallback to defaults)
            yaml.YAMLError: If config file invalid (TODO: log + use defaults)
        """
        self.config_path = Path(config_path)
        self.configs: Dict[str, CircuitBreakerConfig] = {}
        self.circuits: Dict[str, Any] = (
            {}
        )  # Dict[str, CircuitBreakerFSM] when implemented
        self.state_persistence: Optional[Any] = (
            None  # StatePersistence when implemented
        )
        self._config_lock = asyncio.Lock()

        # TODO: Load configs from YAML
        # TODO: Create CircuitBreakerFSM instances
        # TODO: Initialize StatePersistence
        # TODO: Recover state from Redis
        # TODO: Start file watcher for hot-reload
        # TODO: Export initial metrics

        logger.info(
            "circuit_breaker_manager_initialized",
            config_path=str(self.config_path),
            service_count=len(self.configs),
        )

    async def get_circuit_breaker(
        self, service_name: str
    ) -> Any:  # Returns CircuitBreakerFSM
        """
        Get or create circuit breaker for a service.

        **Lazy Initialization:**
        - If circuit exists in self.circuits, return it (<1ms dict lookup)
        - If circuit missing, create new CircuitBreakerFSM with default config
        - Lock self._config_lock to prevent race conditions (concurrent creates)
        - Export initial circuit_breaker_state = 0 (CLOSED) metric

        **Default Configuration (if service not in YAML):**
        - failure_threshold: 5 (moderate tolerance)
        - timeout_duration_ms: 30000 (30s standard recovery)
        - success_threshold: 2 (2 successes to close)
        - slow_call_threshold_ms: 3000 (3s typical UX threshold)
        - time_window_ms: 60000 (60s window)
        - fallback_strategy: DEFAULT_VALUE (safest option)
        - enabled: True

        **Performance:**
        - Circuit exists: <1ms (dict lookup)
        - Circuit missing: <10ms (create FSM, export metric)

        **Concurrency:**
        - Uses asyncio.Lock to prevent multiple creates for same service
        - Multiple calls to get_circuit_breaker("tool_runner") safe

        **Logging:**
        - Log INFO when creating new circuit: "Circuit breaker created for {service}"
        - Log DEBUG when returning existing circuit (not needed in production)

        **TODO (@resilience-team):**
        1. Check if service_name in self.circuits, return if exists
        2. Acquire self._config_lock
        3. Double-check service_name not in self.circuits (race condition)
        4. Get config from self.configs or create default CircuitBreakerConfig
        5. Create CircuitBreakerFSM(config)
        6. Store in self.circuits[service_name]
        7. Export circuit_breaker_state.labels(service=service_name).set(0)
        8. Log INFO "circuit_breaker_created"
        9. Release lock
        10. Add WARD tests for lazy init, default config, concurrency

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)

        Returns:
            CircuitBreakerFSM: Circuit breaker instance for service

        Raises:
            ValueError: If service_name is empty or None (TODO: add validation)
        """
        # TODO: Check if circuit exists in self.circuits
        # TODO: Lazy create with default config if missing
        # TODO: Use asyncio.Lock to prevent race conditions
        # TODO: Export initial metric
        # TODO: Log circuit creation

        logger.debug("get_circuit_breaker", service_name=service_name)
        raise NotImplementedError("get_circuit_breaker not yet implemented")

    async def call_with_circuit_breaker(
        self,
        service_name: str,
        func: Callable[..., T],
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> T:
        """
        Execute operation with circuit breaker protection.

        **Execution Flow (ADR-0009, ADR-0009a):**
        1. Get circuit breaker for service (<1ms)
        2. Check if circuit allows request (can_attempt_request)
           - CLOSED: Allow request
           - OPEN: Reject immediately, invoke fallback (<1ms)
           - HALF_OPEN: Allow only 1 request (first caller wins)
        3. Execute operation with timeout (asyncio.wait_for)
           - Measure latency (start_time to end_time)
           - Detect slow call (latency > slow_call_threshold_ms)
        4. Record result:
           - Success: circuit.record_success(latency_ms)
           - Failure: circuit.record_failure(exception, latency_ms)
           - Timeout: circuit.record_timeout(latency_ms)
        5. Export metrics:
           - circuit_breaker_calls_total{service, result}
           - circuit_breaker_latency_ms{service, state}
        6. Return result or raise exception

        **Fallback Invocation (when circuit OPEN):**
        - DEFAULT_VALUE: Return empty list/None (<1ms)
        - CACHED_RESULT: Redis lookup with cache_key (call_weather_api_SF) (<10ms)
        - ALTERNATE_SERVICE: Call alternate_service circuit (model_hub_remote) (<500ms)
        - RAISE_ERROR: Raise CircuitOpenError, no fallback

        **Timeout Handling:**
        - Use asyncio.wait_for(func(*args, **kwargs), timeout=30.0)
        - Timeout value from config.timeout_duration_ms / 1000
        - On TimeoutError: record_timeout(), increment circuit_breaker_failures_total{failure_type="timeout"}

        **Performance (ADR-0009a):**
        - CLOSED state: Operation latency + <5ms overhead (target 3ms)
        - OPEN state: <1ms fail-fast + fallback latency (target 0.5ms + fallback)
        - HALF_OPEN state: Operation latency + <10ms overhead (probe validation)

        **Latency Budget Impact (ADR-0009):**
        - Baseline TTFT: 140ms → 142ms with CB (+2ms, 1.4% overhead)
        - Fail-fast E2E: 1850ms → 10ms with CB (-1840ms, 99.5% faster!)
        - Tool call fail-fast: 2800ms → 10ms with CB (-2790ms, 99.6% faster!)

        **Structured Logging (ADR-0009c):**
        - DEBUG: "circuit_breaker_call", service, state, allowed
        - INFO: "circuit_breaker_success", service, latency_ms
        - WARNING: "circuit_breaker_failure", service, failure_type, latency_ms
        - WARNING: "circuit_breaker_fallback", service, fallback_strategy, state

        **TODO (@resilience-team):**
        1. Get circuit breaker with get_circuit_breaker(service_name)
        2. Check can_attempt_request(), if False invoke fallback
        3. Start timer (start_time = time.time())
        4. Execute func with asyncio.wait_for(func(*args, **kwargs), timeout)
        5. Calculate latency_ms = (time.time() - start_time) * 1000
        6. Record success/failure/timeout on circuit
        7. Export circuit_breaker_calls_total, circuit_breaker_latency_ms
        8. Add trace span with OpenTelemetry (trace_id, service_name, state)
        9. Add WARD tests for CLOSED/OPEN/HALF_OPEN, fallback strategies, timeout
        10. Document integration with Tool Runner (example code)

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)
            func: Async function to call (e.g., call_weather_api)
            args: Positional arguments for func
            kwargs: Keyword arguments for func

        Returns:
            T: Result from func() or fallback

        Raises:
            CircuitOpenError: If circuit OPEN and fallback_strategy=RAISE_ERROR
            TimeoutError: If operation exceeds timeout_duration_ms
            Exception: Any exception from func() (unless circuit OPEN with fallback)
        """
        kwargs = kwargs or {}

        # TODO: Get circuit breaker
        # TODO: Check can_attempt_request()
        # TODO: If rejected, invoke fallback
        # TODO: Execute func with timeout
        # TODO: Record success/failure
        # TODO: Export metrics
        # TODO: Add trace span

        logger.debug(
            "call_with_circuit_breaker",
            service_name=service_name,
            func=func.__name__,
        )
        raise NotImplementedError("call_with_circuit_breaker not yet implemented")

    async def get_service_health(self, service_name: str) -> CircuitHealth:
        """
        Get health information for a circuit breaker.

        **Health Metrics Collected:**
        1. state: Current FSM state (CLOSED/OPEN/HALF_OPEN)
        2. failure_count: Current failures in time window
        3. success_count: Current successes (for HALF_OPEN → CLOSED)
        4. last_failure_time: Timestamp of most recent failure (epoch seconds)
        5. last_transition_time: Timestamp of most recent state transition
        6. total_calls: Lifetime total calls (from Prometheus counter)
        7. total_failures: Lifetime total failures (from Prometheus counter)
        8. total_fallbacks: Lifetime total fallback invocations
        9. success_rate: Success rate in last 5 minutes (0.0-1.0)

        **Success Rate Calculation:**
        ```python
        # Query Prometheus for last 5 minutes
        success_count = circuit_breaker_calls_total{service=service_name, result="success"}[5m]
        total_count = circuit_breaker_calls_total{service=service_name}[5m]
        success_rate = success_count / total_count if total_count > 0 else 1.0
        ```

        **Performance:**
        - Read FSM state: <1ms (no lock needed, atomic read)
        - Query Prometheus counters: <10ms (in-memory registry)
        - Total: <15ms (target 10ms)

        **Use Cases:**
        - Admin dashboard: Display circuit health for all services
        - Alerting: Check success_rate <50% → trigger alert
        - Debugging: Identify which service caused circuit to open

        **Example Output:**
        ```python
        CircuitHealth(
            service_name="tool_runner",
            state="OPEN",
            failure_count=5,
            success_count=0,
            last_failure_time=1697123456.789,
            last_transition_time=1697123456.790,
            total_calls=1234,
            total_failures=56,
            total_fallbacks=10,
            success_rate=0.92
        )
        ```

        **TODO (@resilience-team):**
        1. Get circuit with get_circuit_breaker(service_name)
        2. Read circuit.state, circuit.failure_count, circuit.success_count
        3. Read circuit.last_failure_time, circuit.last_transition_time
        4. Query Prometheus counters for total_calls, total_failures, total_fallbacks
        5. Calculate success_rate from circuit_breaker_calls_total{result="success"}
        6. Return CircuitHealth dataclass
        7. Add WARD tests for all states, edge cases (no failures yet)

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)

        Returns:
            CircuitHealth: Health information including state, metrics, success rate

        Raises:
            KeyError: If service_name not found in self.circuits (TODO: handle gracefully)
        """
        # TODO: Get circuit breaker
        # TODO: Read FSM state and counters
        # TODO: Query Prometheus for lifetime metrics
        # TODO: Calculate success rate
        # TODO: Return CircuitHealth

        logger.debug("get_service_health", service_name=service_name)
        raise NotImplementedError("get_service_health not yet implemented")

    async def reset_service(self, service_name: str) -> None:
        """
        Reset circuit breaker to CLOSED state (admin operation).

        **Reset Actions:**
        1. Force circuit state to CLOSED (regardless of current state)
        2. Reset failure_count to 0
        3. Reset success_count to 0
        4. Clear last_failure_time
        5. Export circuit_breaker_state.labels(service=service_name).set(0)
        6. Log WARNING: "circuit_breaker_reset", service, previous_state
        7. Optionally clear Redis persisted state

        **Use Cases:**
        - Manual recovery: Operator knows service is healthy, force circuit CLOSED
        - Testing: Reset circuit between test runs
        - Deployment: Reset all circuits after service deployment

        **Performance:**
        - State reset: <2ms (state transition + metric export)

        **Authorization (Future):**
        - TODO: Add admin role check (only operators can reset circuits)
        - TODO: Add audit logging to security events

        **Structured Logging (ADR-0009c):**
        ```python
        logger.warning(
            "circuit_breaker_reset",
            service=service_name,
            previous_state=circuit.state.value,
            operator="admin@example.com",
            reason="manual recovery"
        )
        ```

        **WARD Test Example:**
        ```python
        @test("reset_service forces circuit to CLOSED")
        async def _():
            manager = CircuitBreakerManager()

            # Open circuit with 5 failures
            for i in range(5):
                try:
                    await manager.call_with_circuit_breaker(
                        "tool_runner", failing_func
                    )
                except:
                    pass

            # Verify circuit is OPEN
            health = await manager.get_service_health("tool_runner")
            assert health.state == "OPEN"

            # Reset circuit
            await manager.reset_service("tool_runner")

            # Verify circuit is CLOSED
            health = await manager.get_service_health("tool_runner")
            assert health.state == "CLOSED"
            assert health.failure_count == 0
        ```

        **TODO (@resilience-team):**
        1. Get circuit with get_circuit_breaker(service_name)
        2. Read current state for logging
        3. Force circuit._transition_to_closed()
        4. Reset circuit.failure_count = 0, circuit.success_count = 0
        5. Clear circuit.last_failure_time = None
        6. Export circuit_breaker_state.labels(service=service_name).set(0)
        7. Log WARNING "circuit_breaker_reset"
        8. Optionally call state_persistence.clear_state(service_name)
        9. Add WARD tests for reset from each state (CLOSED, OPEN, HALF_OPEN)

        Args:
            service_name: Service identifier (tool_runner, model_hub_local, etc.)

        Raises:
            KeyError: If service_name not found in self.circuits (TODO: handle gracefully)
        """
        # TODO: Get circuit breaker
        # TODO: Read current state
        # TODO: Force transition to CLOSED
        # TODO: Reset counters
        # TODO: Export metric
        # TODO: Log WARNING

        logger.warning("reset_service", service_name=service_name)
        raise NotImplementedError("reset_service not yet implemented")


# ============================================================================
# MODULE-LEVEL API (SINGLETON PATTERN)
# ============================================================================

# Global singleton instance (initialized on first import)
_manager_instance: Optional[CircuitBreakerManager] = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """
    Get global CircuitBreakerManager singleton.

    **Singleton Pattern:**
    - Initialize _manager_instance on first call
    - Subsequent calls return cached instance
    - Thread-safe (Python GIL protects initialization)

    **Usage:**
    ```python
    from k1.l5_infrastructure.resilience.circuit_breaker_manager import (
        get_circuit_breaker_manager
    )

    manager = get_circuit_breaker_manager()
    result = await manager.call_with_circuit_breaker("tool_runner", call_api)
    ```

    **TODO (@resilience-team):**
    1. Check if _manager_instance is None
    2. If None, create CircuitBreakerManager()
    3. Cache in _manager_instance
    4. Return _manager_instance
    5. Add WARD tests for singleton behavior (same instance returned)

    Returns:
        CircuitBreakerManager: Global singleton instance
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = CircuitBreakerManager()
    return _manager_instance


# ============================================================================
# EXPECTED LINT ERRORS (STUB FILE)
# ============================================================================
"""
**Expected Errors (will be resolved during implementation):**

1. NotImplementedError in all methods:
   - get_circuit_breaker()
   - call_with_circuit_breaker()
   - get_service_health()
   - reset_service()

2. Type: Any for CircuitBreakerFSM references:
   - self.circuits: Dict[str, Any] should be Dict[str, CircuitBreakerFSM]
   - get_circuit_breaker() returns Any should return CircuitBreakerFSM

3. Missing imports:
   - CircuitBreakerFSM, CircuitBreakerState from circuit_fsm.py
   - call_with_protection from call_wrapper.py
   - StatePersistence from state_persistence.py
   - get_redis_client from session_state

4. TODO comments:
   - 30+ TODO markers for @resilience-team implementation

**Implementation Dependencies:**
- Epic 4.1.2: circuit_fsm.py (CircuitBreakerFSM class)
- Epic 4.1.3: call_wrapper.py (call_with_protection function)
- Epic 4.1.4: state_persistence.py (StatePersistence class)
- K1 Core: session_state (Redis client), obs (tracing, metrics)

**Testing Requirements:**
- WARD framework with 100% coverage target
- Test categories:
  1. Configuration loading (YAML parse, defaults, validation)
  2. Circuit lifecycle (get, call, reset)
  3. State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
  4. Fallback strategies (all 4 types)
  5. Metrics export (all 6 Prometheus metrics)
  6. Concurrency (multiple simultaneous calls, lazy init race condition)
  7. State persistence (Redis save/recover)
  8. Hot-reload (config file changes)
"""
