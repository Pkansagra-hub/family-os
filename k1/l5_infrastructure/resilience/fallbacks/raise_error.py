"""
Circuit Breaker Raise Error Fallback Strategy.

This module implements the raise error fallback strategy for circuit breakers.
When a circuit is OPEN (service unavailable), this strategy immediately raises
a CircuitOpenError exception, forcing the caller to handle the failure explicitly.
This is used for critical operations where failure must be visible and no fallback
is acceptable.

Use Cases (ADR-0009a):
    - K0 Bridge: Critical WAL writes (no fallback for memory kernel)
    - Streaming Engine: Stateful SSE streams (cannot fallback)
    - Required operations: Features that cannot degrade gracefully
    - Transactional operations: Operations requiring atomicity

Performance:
    - Invocation: <1ms (immediate error raise)
    - Memory: ~200B (exception object)
    - No external dependencies

Trade-offs:
    ✅ Explicit error handling (no silent failures)
    ✅ Forces caller to handle degradation
    ✅ Prevents cascading failures (fail-fast)
    ⚠️ User-visible error (degraded experience)
    ⚠️ Requires error handling in caller
    ❌ May abort in-progress operations

Integration Points:
    - Called by call_wrapper.py when circuit OPEN
    - Used by CircuitBreakerManager for critical services
    - Configured in circuit_breakers.yml per service
    - Caller must catch CircuitOpenError and handle

Related ADRs:
    - ADR-0009: Circuit Breaker Pattern (fallback strategies)
    - ADR-0009a: FSM Implementation (Section "Fallback Strategies - Raise Error")
    - ADR-0009b: Per-Service Configuration (fallback_strategy field)

Author: @resilience-team
Created: 2025-10-27
Status: STUB (Implementation Required)
"""

from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class CircuitOpenError(Exception):
    """
    Exception raised when circuit breaker is OPEN and no fallback available.

    This exception indicates that a service is unavailable and the circuit
    breaker has opened to prevent cascading failures. The caller must handle
    this exception and implement appropriate error handling (abort operation,
    retry later, notify user, etc.).

    Attributes:
        service_name: Name of the unavailable service
        failure_count: Number of failures that opened the circuit
        opened_at: Timestamp when circuit opened (seconds since epoch)
        timeout_remaining_ms: Milliseconds until circuit tests recovery

    Example:
        ```python
        try:
            await k0_bridge.write(event)
        except CircuitOpenError as e:
            logger.error(
                "k0_unavailable",
                service=e.service_name,
                failure_count=e.failure_count,
                timeout_remaining_ms=e.timeout_remaining_ms
            )
            # Abort saga, notify user, etc.
            await saga_coordinator.abort(saga_id)
        ```

    ADR Reference:
        - ADR-0009a: "Raise CircuitOpenError for critical operations"
    """

    def __init__(
        self,
        service_name: str,
        failure_count: int,
        opened_at: float,
        timeout_remaining_ms: float,
    ):
        """
        Initialize CircuitOpenError.

        Args:
            service_name: Name of the unavailable service
            failure_count: Number of failures that opened circuit
            opened_at: Timestamp when circuit opened
            timeout_remaining_ms: Milliseconds until recovery test
        """
        self.service_name = service_name
        self.failure_count = failure_count
        self.opened_at = opened_at
        self.timeout_remaining_ms = timeout_remaining_ms

        message = (
            f"Circuit breaker OPEN for service '{service_name}'. "
            f"Failures: {failure_count}. "
            f"Retry in {timeout_remaining_ms:.0f}ms."
        )
        super().__init__(message)


class RaiseErrorFallback:
    """
    Raise Error Fallback Strategy for Circuit Breaker.

    Immediately raises CircuitOpenError when the circuit is OPEN, forcing
    the caller to handle the failure explicitly. This strategy is used for
    critical operations where no fallback is acceptable and failure must
    be visible.

    Strategy Characteristics:
        - Use Case: Critical operations (K0 WAL, required features)
        - Performance: <1ms (immediate exception)
        - Dependencies: None
        - User Experience: Poor (visible error)
        - Complexity: Low (simple raise)

    When to Use:
        - Critical path operations (K0 Bridge WAL writes)
        - Stateful operations (Streaming Engine SSE)
        - Transactional operations (saga coordinator)
        - Required features (no graceful degradation possible)

    Example Usage:
        ```python
        from k1.l5_infrastructure.resilience.fallbacks.raise_error import (
            RaiseErrorFallback,
            CircuitOpenError
        )

        # K0 Bridge with no fallback
        fallback = RaiseErrorFallback()

        # Circuit opens, error raised
        try:
            result = await fallback.invoke(
                service_name="k0_bridge",
                operation_name="wal_write",
                failure_count=5,
                opened_at=1698360000.0,
                timeout_remaining_ms=25000.0
            )
        except CircuitOpenError as e:
            # Handle critical failure
            logger.error("k0_unavailable", error=str(e))
            await saga_coordinator.abort(saga_id)
        ```

    Configuration (circuit_breakers.yml):
        ```yaml
        k0_bridge:
          fallback_strategy: RAISE_ERROR
          # No fallback_config needed (always raises)
        ```

    ADR References:
        - ADR-0009a: "Raise error for critical operations"
        - ADR-0009b: "K0 Bridge uses RAISE_ERROR fallback"

    WARD Test Example:
        ```python
        from ward import test, raises
        from k1.l5_infrastructure.resilience.fallbacks.raise_error import (
            RaiseErrorFallback,
            CircuitOpenError
        )

        @test("raise error fallback raises CircuitOpenError")
        async def _():
            fallback = RaiseErrorFallback()

            with raises(CircuitOpenError) as exc_info:
                await fallback.invoke(
                    service_name="k0_bridge",
                    operation_name="wal_write",
                    failure_count=5,
                    opened_at=1698360000.0,
                    timeout_remaining_ms=30000.0
                )

            assert exc_info.raised.service_name == "k0_bridge"
            assert exc_info.raised.failure_count == 5
            assert exc_info.raised.timeout_remaining_ms == 30000.0

        @test("CircuitOpenError has descriptive message")
        async def _():
            error = CircuitOpenError(
                service_name="k0_bridge",
                failure_count=5,
                opened_at=1698360000.0,
                timeout_remaining_ms=30000.0
            )

            assert "k0_bridge" in str(error)
            assert "5" in str(error)
            assert "30000" in str(error)
        ```
    """

    def __init__(self):
        """
        Initialize raise error fallback strategy.

        No configuration needed - this strategy always raises CircuitOpenError.

        Performance:
            - Initialization: <0.01ms (no I/O, simple assignment)
        """
        # TODO(@resilience-team): Initialize fallback strategy
        # 1. Create logger for observability
        self.logger = logger.bind(fallback_strategy="raise_error")

    async def invoke(
        self,
        service_name: str,
        operation_name: Optional[str] = None,
        failure_count: int = 0,
        opened_at: float = 0.0,
        timeout_remaining_ms: float = 0.0,
        **kwargs,
    ) -> None:
        """
        Invoke raise error fallback strategy.

        Immediately raises CircuitOpenError with service details. The caller
        MUST catch this exception and implement appropriate error handling.

        Execution Flow:
            1. Log error (error level)
            2. Create CircuitOpenError with service details
            3. Raise exception

        Args:
            service_name: Name of the service whose circuit is OPEN
            operation_name: Optional operation name (for logging)
            failure_count: Number of failures that opened circuit
            opened_at: Timestamp when circuit opened (seconds since epoch)
            timeout_remaining_ms: Milliseconds until recovery test
            **kwargs: Additional context (unused, for interface consistency)

        Raises:
            CircuitOpenError: Always raised (no fallback available)

        Performance:
            - Target: <1ms (immediate exception)
            - No network I/O
            - No disk I/O

        Side Effects:
            - Emits error log (circuit open, no fallback)
            - Increments circuit_breaker_fallbacks_total metric (via manager)
            - Raises exception (caller must handle)

        Example Use Cases:
            ```python
            # K0 Bridge: No fallback for WAL writes
            fallback = RaiseErrorFallback()
            try:
                await fallback.invoke(
                    service_name="k0_bridge",
                    operation_name="wal_write",
                    failure_count=3,
                    opened_at=1698360000.0,
                    timeout_remaining_ms=5000.0
                )
            except CircuitOpenError as e:
                # Abort saga, notify user
                logger.error("k0_unavailable", saga_id=saga_id)
                await saga_coordinator.abort(saga_id)

            # Streaming Engine: No fallback for SSE streams
            fallback = RaiseErrorFallback()
            try:
                await fallback.invoke(
                    service_name="streaming_engine",
                    operation_name="start_stream",
                    failure_count=3,
                    opened_at=1698360000.0,
                    timeout_remaining_ms=10000.0
                )
            except CircuitOpenError as e:
                # Close connection, notify client
                logger.error("streaming_unavailable", session_id=session_id)
                await session.close()
            ```

        Logging Output:
            ```json
            {
                "event": "circuit_open_no_fallback",
                "fallback_strategy": "raise_error",
                "service_name": "k0_bridge",
                "operation_name": "wal_write",
                "failure_count": 3,
                "timeout_remaining_ms": 5000.0,
                "level": "error"
            }
            ```

        Error Message Example:
            ```
            CircuitOpenError: Circuit breaker OPEN for service 'k0_bridge'.
            Failures: 3. Retry in 5000ms.
            ```

        ADR Reference:
            - ADR-0009a: "Raise CircuitOpenError for critical operations"
        """
        # TODO(@resilience-team): Implement fallback invocation
        # 1. Log error:
        #    self.logger.error(
        #        "circuit_open_no_fallback",
        #        service_name=service_name,
        #        operation_name=operation_name,
        #        failure_count=failure_count,
        #        timeout_remaining_ms=timeout_remaining_ms
        #    )
        # 2. Create and raise CircuitOpenError:
        #    raise CircuitOpenError(
        #        service_name=service_name,
        #        failure_count=failure_count,
        #        opened_at=opened_at,
        #        timeout_remaining_ms=timeout_remaining_ms
        #    )
        raise CircuitOpenError(
            service_name=service_name,
            failure_count=failure_count,
            opened_at=opened_at,
            timeout_remaining_ms=timeout_remaining_ms,
        )

    def get_strategy_name(self) -> str:
        """
        Get human-readable strategy name.

        Returns:
            "RAISE_ERROR"

        Performance:
            - <0.001ms (constant return)
        """
        return "RAISE_ERROR"


# Expected Lint Errors (Intentional):
# 1. structlog import unused (TODO: use in invoke() logging)
# 2. logger parameter missing in structlog.bind (TODO: configure in __init__)
#
# These will be resolved when @resilience-team implements the TODOs.
