"""
Circuit Breaker - K0 Unavailability Protection

Layer: L5 Infrastructure
Component: K0 Bridge → Circuit Breaker
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Communication Protocol (Circuit Breaker: 3 failures → open 60s)
    - ADR-0009: Circuit Breaker Pattern (if exists)
    - ADR-0024: Graceful Degradation Strategies

Dependencies:
    Internal:
        - k1.l5_infrastructure.event_bus (EventBus for circuit state events)
    External:
        - asyncio (async runtime, health check timer)
        - time (timestamps, recovery timeout)

Connects To:
    Upstream:
        - k1.bridge_k0.command_client (protect command requests)
        - k1.bridge_k0.ports.query_port (protect query requests)
    Downstream:
        - K0 ports (all external K0 communication)

Performance Budgets:
    - State check overhead: <0.1ms P95
    - State transition: <1ms P95
    - Recovery health check: <50ms P95

Observability:
    Metrics:
        - k1_k0_bridge_circuit_breaker_state{gauge} (0=closed, 1=open, 2=half_open)
        - k1_k0_bridge_circuit_breaker_failures_total{counter}
        - k1_k0_bridge_circuit_breaker_trips_total{counter}
    Traces:
        - Span: k0_bridge.circuit_breaker.trip
        - Span: k0_bridge.circuit_breaker.recover
    Logs:
        - WARNING: circuit opened (consecutive_failures, total_trips)
        - INFO: circuit closed (recovery successful, total_recoveries)
        - ERROR: recovery failed (health_check_result)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Bridge Circuit Breaker)
    - Test: tests/k1/bridge_k0/test_circuit_breaker.py
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Callable, Optional

# Third-party imports
# None

# Internal imports
# from k1.l5_infrastructure.event_bus import EventBus, Event, EventTopic

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.3.2
DEFAULT_CONFIG = {
    "failure_threshold": 3,  # 3 consecutive failures → open circuit
    "recovery_timeout_ms": 60000,  # 60s timeout before HALF_OPEN
    "health_check_interval_ms": 5000,  # 5s health check in HALF_OPEN
    "success_threshold": 1,  # 1 success in HALF_OPEN → close circuit
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class CircuitState(Enum):
    """Circuit breaker state machine"""

    CLOSED = "CLOSED"  # Normal operation (requests allowed)
    OPEN = "OPEN"  # Fail fast (no requests allowed)
    HALF_OPEN = "HALF_OPEN"  # Testing recovery (single health check)


class FailureReason(Enum):
    """Request failure reasons"""

    CONNECTION_ERROR = "CONNECTION_ERROR"  # Cannot connect to K0
    TIMEOUT = "TIMEOUT"  # Request timeout
    SERVER_ERROR = "SERVER_ERROR"  # 5xx HTTP error
    UNKNOWN = "UNKNOWN"  # Unknown error


@dataclass
class CircuitBreakerConfig:
    """
    Circuit breaker configuration.

    Fields:
        failure_threshold: Consecutive failures to open circuit (default: 3)
        recovery_timeout_ms: Wait time before HALF_OPEN (default: 60s)
        health_check_interval_ms: Health check interval in HALF_OPEN (default: 5s)
        success_threshold: Successes in HALF_OPEN to close (default: 1)
    """

    failure_threshold: int = DEFAULT_CONFIG["failure_threshold"]
    recovery_timeout_ms: int = DEFAULT_CONFIG["recovery_timeout_ms"]
    health_check_interval_ms: int = DEFAULT_CONFIG["health_check_interval_ms"]
    success_threshold: int = DEFAULT_CONFIG["success_threshold"]


@dataclass
class CircuitBreakerStats:
    """
    Circuit breaker statistics.

    Fields:
        current_state: Current circuit state (CLOSED | OPEN | HALF_OPEN)
        consecutive_failures: Consecutive failure count
        total_trips: Total circuit trips (CLOSED → OPEN)
        total_recoveries: Total successful recoveries (HALF_OPEN → CLOSED)
        last_failure_time: Last failure timestamp
        opened_at: Circuit opened timestamp (if OPEN)
    """

    current_state: CircuitState
    consecutive_failures: int
    total_trips: int
    total_recoveries: int
    last_failure_time: Optional[float]
    opened_at: Optional[float]


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class CircuitBreaker:
    """
    Circuit breaker for K0 unavailability protection.

    Purpose:
        Tracks K0 request failures (connection errors, timeouts, 5xx errors),
        opens circuit after 3 consecutive failures (fail fast), waits 60s
        recovery timeout, tests with health check in HALF_OPEN state, closes
        circuit on successful health check (resume normal operation).

    State Machine (ADR-0001a):
        CLOSED: Normal operation
        ├─ (3 consecutive failures) → OPEN

        OPEN: Fail fast (no requests allowed)
        ├─ (60s timeout) → HALF_OPEN

        HALF_OPEN: Testing recovery (single health check)
        ├─ (health check success) → CLOSED
        └─ (health check failure) → OPEN

    Responsibilities:
        1. Track K0 request failures (record_failure)
        2. Open circuit after 3 consecutive failures
        3. Wait 60s recovery timeout before testing HALF_OPEN
        4. Perform health check in HALF_OPEN state
        5. Close circuit on successful health check

    Lifecycle:
        INIT → CLOSED → [OPEN → HALF_OPEN] → CLOSED → TERMINATED

    Thread Safety: Yes (async-safe with lock)
    Async Safe: Yes (fully async/await compatible)

    Performance Budget (P95):
        - State check overhead: <0.1ms
        - State transition: <1ms
        - Recovery health check: <50ms

    Examples:
        >>> config = CircuitBreakerConfig(failure_threshold=3)
        >>> circuit = CircuitBreaker(config, health_check_fn=lambda: check_k0_health())
        >>>
        >>> # Check if requests allowed
        >>> if await circuit.is_request_allowed():
        ...     # Send request to K0
        ...     try:
        ...         response = await send_to_k0(request)
        ...         await circuit.record_success()
        ...     except Exception as e:
        ...         await circuit.record_failure(FailureReason.CONNECTION_ERROR)
        ... else:
        ...     # Circuit OPEN, fail fast
        ...     raise CircuitBreakerOpenError('K0 unavailable')

    References:
        - ADR-0001a: K0 Bridge Circuit Breaker (3 failures → open 60s)
        - Research: Release It! (Michael Nygard 2007) - Circuit Breaker pattern
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(
        self,
        config: CircuitBreakerConfig,
        health_check_fn: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        Initialize CircuitBreaker.

        Args:
            config: CircuitBreakerConfig with thresholds and timeouts
            health_check_fn: Health check function (returns True if K0 healthy)

        Raises:
            ValueError: If configuration is invalid

        Side Effects:
            - Initializes internal state (failure count, state)
            - Does NOT start health check timer (call initialize())

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Validate config (check failure_threshold, recovery_timeout_ms)
        # 2. Initialize state machine (start in CLOSED)
        # 3. Initialize counters (consecutive_failures, total_trips, total_recoveries)
        # 4. Initialize health check function
        self.config = config
        self.health_check_fn = health_check_fn
        self.state = CircuitState.CLOSED
        self._logger = logger
        self._consecutive_failures = 0
        self._total_trips = 0
        self._total_recoveries = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._state_lock = asyncio.Lock()
        self._recovery_task: Optional[asyncio.Task] = None
        pass

    async def is_request_allowed(self) -> bool:
        """
        Check if request is allowed (circuit state check).

        Returns:
            True if circuit CLOSED or HALF_OPEN, False if OPEN

        Performance:
            - Target: <0.1ms P95 (state check overhead)

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement is_request_allowed (ADR-0001a)
        # 1. Check current state
        # 2. If CLOSED: return True (normal operation)
        # 3. If HALF_OPEN: return True (testing recovery)
        # 4. If OPEN: Check if recovery timeout elapsed
        #    - If timeout elapsed: transition to HALF_OPEN, return True
        #    - Otherwise: return False (fail fast)
        async with self._state_lock:
            if self.state == CircuitState.CLOSED:
                return True
            elif self.state == CircuitState.HALF_OPEN:
                return True
            elif self.state == CircuitState.OPEN:
                # Check if recovery timeout elapsed
                if self._opened_at is not None:
                    elapsed_ms = (time.time() - self._opened_at) * 1000
                    if elapsed_ms >= self.config.recovery_timeout_ms:
                        # Transition to HALF_OPEN
                        await self._transition_to_half_open()
                        return True
                return False

    async def record_success(self) -> None:
        """
        Record successful request.

        This method resets failure counter in CLOSED state, or closes circuit
        in HALF_OPEN state after successful health check.

        Side Effects:
            - Resets consecutive_failures to 0 (in CLOSED)
            - Transitions HALF_OPEN → CLOSED (if success_threshold met)

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement record_success (ADR-0001a)
        # 1. Acquire state lock
        # 2. If state == CLOSED: Reset consecutive_failures to 0
        # 3. If state == HALF_OPEN:
        #    - Increment success count
        #    - If success_count >= success_threshold: transition to CLOSED
        # 4. Log success event
        async with self._state_lock:
            if self.state == CircuitState.CLOSED:
                self._consecutive_failures = 0
            elif self.state == CircuitState.HALF_OPEN:
                # Transition to CLOSED after success
                await self._transition_to_closed()
        pass

    async def record_failure(self, reason: FailureReason) -> None:
        """
        Record failed request.

        This method increments failure counter, opens circuit if threshold met.

        Args:
            reason: Failure reason (CONNECTION_ERROR | TIMEOUT | SERVER_ERROR)

        Side Effects:
            - Increments consecutive_failures
            - Transitions CLOSED → OPEN (if failure_threshold met)
            - Transitions HALF_OPEN → OPEN (if health check fails)

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement record_failure (ADR-0001a)
        # 1. Acquire state lock
        # 2. Increment consecutive_failures
        # 3. Update last_failure_time
        # 4. If state == CLOSED and consecutive_failures >= failure_threshold:
        #    - Transition to OPEN
        # 5. If state == HALF_OPEN:
        #    - Transition to OPEN (health check failed)
        # 6. Log failure event
        async with self._state_lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.time()

            if self.state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.config.failure_threshold:
                    await self._transition_to_open()
            elif self.state == CircuitState.HALF_OPEN:
                # Health check failed, back to OPEN
                await self._transition_to_open()
        pass

    def get_stats(self) -> CircuitBreakerStats:
        """
        Get circuit breaker statistics.

        Returns:
            CircuitBreakerStats with current state and counters

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        return CircuitBreakerStats(
            current_state=self.state,
            consecutive_failures=self._consecutive_failures,
            total_trips=self._total_trips,
            total_recoveries=self._total_recoveries,
            last_failure_time=self._last_failure_time,
            opened_at=self._opened_at,
        )

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Cancel recovery task
            - Finalize metrics

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0001a)
        # 1. Cancel recovery task (if running)
        # 2. Flush metrics (Prometheus)
        if self._recovery_task:
            self._recovery_task.cancel()
        self._logger.info("circuit_breaker_shutdown_complete")
        pass

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    async def _transition_to_open(self) -> None:
        """
        Transition circuit to OPEN state.

        Side Effects:
            - Sets state to OPEN
            - Records opened_at timestamp
            - Increments total_trips counter
            - Logs WARNING
            - Emits metrics

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement transition to OPEN (ADR-0001a)
        # 1. Set state to OPEN
        # 2. Record opened_at timestamp
        # 3. Increment total_trips
        # 4. Log WARNING: circuit opened
        # 5. Emit metric: k1_k0_bridge_circuit_breaker_state = 1
        # 6. Emit metric: k1_k0_bridge_circuit_breaker_trips_total += 1
        self.state = CircuitState.OPEN
        self._opened_at = time.time()
        self._total_trips += 1
        self._logger.warning(
            "circuit_opened",
            consecutive_failures=self._consecutive_failures,
            total_trips=self._total_trips,
        )
        pass

    async def _transition_to_half_open(self) -> None:
        """
        Transition circuit to HALF_OPEN state.

        Side Effects:
            - Sets state to HALF_OPEN
            - Starts health check timer
            - Logs INFO
            - Emits metrics

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement transition to HALF_OPEN (ADR-0001a)
        # 1. Set state to HALF_OPEN
        # 2. Start health check timer (5s interval)
        # 3. Log INFO: circuit half_open
        # 4. Emit metric: k1_k0_bridge_circuit_breaker_state = 2
        self.state = CircuitState.HALF_OPEN
        self._logger.info("circuit_half_open", recovery_timeout_ms=self.config.recovery_timeout_ms)
        pass

    async def _transition_to_closed(self) -> None:
        """
        Transition circuit to CLOSED state.

        Side Effects:
            - Sets state to CLOSED
            - Resets consecutive_failures to 0
            - Increments total_recoveries counter
            - Logs INFO
            - Emits metrics

        ADR: ADR-0001a (K0 Bridge Circuit Breaker)
        Assigned to: Issue #L5-1.3.2
        """
        # TODO(@infrastructure-team): Implement transition to CLOSED (ADR-0001a)
        # 1. Set state to CLOSED
        # 2. Reset consecutive_failures to 0
        # 3. Increment total_recoveries
        # 4. Log INFO: circuit closed
        # 5. Emit metric: k1_k0_bridge_circuit_breaker_state = 0
        # 6. Emit metric: k1_k0_bridge_circuit_breaker_recoveries_total += 1
        self.state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._total_recoveries += 1
        self._logger.info("circuit_closed", total_recoveries=self._total_recoveries)
        pass


# =============================================================================
# SECTION 5: HELPER FUNCTIONS & EXCEPTIONS
# =============================================================================


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is OPEN (fail fast)"""

    pass


def create_circuit_breaker(
    config: Optional[CircuitBreakerConfig] = None,
    health_check_fn: Optional[Callable[[], bool]] = None,
) -> CircuitBreaker:
    """
    Create CircuitBreaker with default or provided configuration.

    Args:
        config: CircuitBreakerConfig (default: 3 failures, 60s timeout)
        health_check_fn: Health check function

    Returns:
        CircuitBreaker instance

    ADR: ADR-0001a (K0 Bridge Circuit Breaker)
    Assigned to: Issue #L5-1.3.2
    """
    if config is None:
        config = CircuitBreakerConfig()

    return CircuitBreaker(config, health_check_fn)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerStats",
    "CircuitState",
    "FailureReason",
    "CircuitBreakerOpenError",
    "create_circuit_breaker",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_bridge_circuit_breaker_state{gauge} (0=closed, 1=open, 2=half_open)
#   - k1_k0_bridge_circuit_breaker_failures_total{counter}
#   - k1_k0_bridge_circuit_breaker_trips_total{counter}
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.circuit_breaker.trip
#   - Span name: k0_bridge.circuit_breaker.recover
#   - Attributes: state, consecutive_failures, total_trips
#
# Logs to emit (structured logging):
#   - Level: WARNING (circuit opened), INFO (circuit closed), ERROR (recovery failed)
#   - Fields: component='circuit_breaker', state, consecutive_failures, total_trips
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_circuit_breaker.py
#   - Test state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
#   - Test failure threshold (3 failures → OPEN)
#   - Test recovery timeout (60s → HALF_OPEN)
#   - Test health check (HALF_OPEN → CLOSED on success)
#   - Test fail fast (requests blocked in OPEN state)
#
# No simulation code allowed:
#   - Use real K0 mock server with health check endpoint
#   - Test all state transitions with real timing
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert state check overhead <0.1ms P95
#   - Assert state transition <1ms P95
#   - Assert recovery health check <50ms P95
#
# =============================================================================
