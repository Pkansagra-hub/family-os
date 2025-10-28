"""
Circuit Breaker Default Value Fallback Strategy.

This module implements the default value fallback strategy for circuit breakers.
When a circuit is OPEN (service unavailable), this strategy returns a predefined
default value (None, [], {}, "") to maintain graceful degradation for optional
operations.

Use Cases (ADR-0009a):
    - Tool Runner: Optional search/file operations (return [])
    - MCP Gateway: Optional MCP server tools (return {})
    - Read-only operations: Non-critical data queries (return None)
    - Best-effort operations: Features that can degrade gracefully

Performance:
    - Invocation: <1ms (immediate return, no I/O)
    - Memory: ~50B (reference to default value)
    - No external dependencies (Redis, network, etc.)

Trade-offs:
    ✅ Simple, no external dependencies
    ✅ Fast (<1ms), predictable behavior
    ✅ Zero infrastructure requirements
    ⚠️ Degraded user experience (empty results)
    ❌ Not suitable for critical operations

Integration Points:
    - Called by call_wrapper.py when circuit OPEN
    - Used by CircuitBreakerManager for optional services
    - Configured in circuit_breakers.yml per service

Related ADRs:
    - ADR-0009: Circuit Breaker Pattern (fallback strategies)
    - ADR-0009a: FSM Implementation (Section "Fallback Strategies - Default Value")
    - ADR-0009b: Per-Service Configuration (fallback_strategy field)

Author: @resilience-team
Created: 2025-10-27
Status: STUB (Implementation Required)
"""

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class DefaultValueFallback:
    """
    Default Value Fallback Strategy for Circuit Breaker.

    Returns a predefined default value when the circuit is OPEN, providing
    graceful degradation for optional operations. This is the simplest fallback
    strategy with minimal overhead and no external dependencies.

    Strategy Characteristics:
        - Use Case: Optional, non-critical operations
        - Performance: <1ms (immediate return)
        - Dependencies: None (no Redis, no network)
        - User Experience: Degraded (empty results)
        - Complexity: Low (single return statement)

    Typical Default Values:
        - None: For single optional values
        - []: For list results (search, queries)
        - {}: For dict results (metadata, config)
        - "": For string results (descriptions, names)
        - 0: For numeric results (counts, scores)

    Example Usage:
        ```python
        from k1.l5_infrastructure.resilience.fallbacks.default_value import DefaultValueFallback

        # Tool runner with empty list fallback
        fallback = DefaultValueFallback(default_value=[])

        # Circuit opens, fallback invoked
        result = await fallback.invoke(
            service_name="search_tool",
            operation_name="search_files"
        )
        assert result == []  # Empty list returned
        ```

    Configuration (circuit_breakers.yml):
        ```yaml
        tool_runner:
          fallback_strategy: DEFAULT_VALUE
          fallback_config:
            default_value: []  # Empty list for tool results
        ```

    ADR References:
        - ADR-0009a: "Return default value for optional operations"
        - ADR-0009b: "Tool runner uses DEFAULT_VALUE fallback"

    WARD Test Example:
        ```python
        from ward import test
        from k1.l5_infrastructure.resilience.fallbacks.default_value import DefaultValueFallback

        @test("default value fallback returns configured value")
        async def _():
            fallback = DefaultValueFallback(default_value=[])
            result = await fallback.invoke(
                service_name="test_service",
                operation_name="test_op"
            )
            assert result == []

        @test("default value fallback returns None when no value configured")
        async def _():
            fallback = DefaultValueFallback()
            result = await fallback.invoke(
                service_name="test_service",
                operation_name="test_op"
            )
            assert result is None

        @test("default value fallback logs invocation")
        async def _():
            fallback = DefaultValueFallback(default_value={})
            result = await fallback.invoke(
                service_name="mcp_gateway",
                operation_name="call_tool"
            )
            assert result == {}
            # Verify log emitted with service_name, operation_name
        ```
    """

    def __init__(self, default_value: Any = None):
        """
        Initialize default value fallback strategy.

        Args:
            default_value: Value to return when circuit OPEN
                          Default: None
                          Common: [], {}, "", 0

        Performance:
            - Initialization: <0.01ms (simple assignment)
        """
        # TODO(@resilience-team): Initialize fallback strategy
        # 1. Store default_value for reuse
        # 2. Create logger for observability
        self.default_value = default_value
        self.logger = logger.bind(fallback_strategy="default_value")

    async def invoke(
        self, service_name: str, operation_name: Optional[str] = None, **kwargs
    ) -> Any:
        """
        Invoke default value fallback strategy.

        Returns the configured default value immediately without any I/O.
        This is the fastest fallback strategy (<1ms).

        Execution Flow:
            1. Log fallback invocation (warning level)
            2. Return self.default_value
            3. No external calls, no waiting

        Args:
            service_name: Name of the service whose circuit is OPEN
            operation_name: Optional operation name (for logging)
            **kwargs: Additional context (unused, for interface consistency)

        Returns:
            Any: The configured default_value (None, [], {}, "", 0, etc.)

        Performance:
            - Target: <1ms (immediate return)
            - No network I/O
            - No disk I/O
            - No cache lookup

        Side Effects:
            - Emits warning log (fallback invoked)
            - Increments circuit_breaker_fallbacks_total metric (via manager)

        Example Use Cases:
            ```python
            # Tool runner: Return empty list for search
            fallback = DefaultValueFallback(default_value=[])
            result = await fallback.invoke(
                service_name="search_tool",
                operation_name="search_files"
            )
            # result = [] (empty search results)

            # MCP gateway: Return empty dict for tool call
            fallback = DefaultValueFallback(default_value={})
            result = await fallback.invoke(
                service_name="mcp_gateway",
                operation_name="call_weather_tool"
            )
            # result = {} (empty tool response)

            # Optional metadata: Return None
            fallback = DefaultValueFallback(default_value=None)
            result = await fallback.invoke(
                service_name="metadata_service",
                operation_name="get_user_preferences"
            )
            # result = None (no preferences available)
            ```

        Logging Output:
            ```json
            {
                "event": "fallback_invoked",
                "fallback_strategy": "default_value",
                "service_name": "search_tool",
                "operation_name": "search_files",
                "default_value": [],
                "level": "warning"
            }
            ```

        ADR Reference:
            - ADR-0009a: "Default value fallback returns constant (<1ms)"
        """
        # TODO(@resilience-team): Implement fallback invocation
        # 1. Log warning:
        #    self.logger.warning(
        #        "fallback_invoked",
        #        service_name=service_name,
        #        operation_name=operation_name,
        #        default_value=self.default_value
        #    )
        # 2. Return default_value immediately
        #    return self.default_value
        return self.default_value

    def get_strategy_name(self) -> str:
        """
        Get human-readable strategy name.

        Returns:
            "DEFAULT_VALUE"

        Performance:
            - <0.001ms (constant return)
        """
        return "DEFAULT_VALUE"

    def get_default_value(self) -> Any:
        """
        Get configured default value.

        Useful for testing and observability.

        Returns:
            Any: The configured default_value

        Example:
            ```python
            fallback = DefaultValueFallback(default_value=[])
            assert fallback.get_default_value() == []
            ```
        """
        return self.default_value


# Expected Lint Errors (Intentional):
# 1. structlog import unused (TODO: use in invoke() logging)
# 2. logger parameter missing in structlog.bind (TODO: configure in __init__)
#
# These will be resolved when @resilience-team implements the TODOs.
