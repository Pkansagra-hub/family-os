"""
Circuit Breaker Alternate Service Fallback Strategy.

This module implements the alternate service fallback strategy for circuit breakers.
When a circuit is OPEN (service unavailable), this strategy routes the request to
an alternate service (e.g., local LLM → remote LLM, primary region → backup region),
providing transparent failover with minimal user experience degradation.

Use Cases (ADR-0009a):
    - Model Hub Local → Remote: Fallback from local gemma-2b to remote gpt4o-mini
    - Multi-region services: Primary region → backup region
    - Tiered services: Premium → standard → basic service tiers
    - Service mesh: Failed instance → healthy instance

Performance:
    - Invocation: <500ms (alternate service call)
    - Trade-off: Higher latency (local 150ms → remote 500ms)
    - Trade-off: Higher cost (local free → remote $0.0001/token)
    - Requires: Alternate service must be available

Trade-offs:
    ✅ Maintains functionality (user sees no degradation)
    ✅ Transparent to user (same interface)
    ✅ Supports hybrid local/remote deployment
    ⚠️ Alternate service may also fail (cascade risk)
    ⚠️ Higher latency (2-5× slower)
    ⚠️ Higher cost (local free → remote paid)

Integration Points:
    - Called by call_wrapper.py when circuit OPEN
    - Used by CircuitBreakerManager for tiered services
    - Configured in circuit_breakers.yml per service
    - Requires alternate service has circuit breaker too

Related ADRs:
    - ADR-0009: Circuit Breaker Pattern (fallback strategies)
    - ADR-0009a: FSM Implementation (Section "Fallback Strategies - Alternate Service")
    - ADR-0009b: Per-Service Configuration (fallback_strategy field)

Author: @resilience-team
Created: 2025-10-27
Status: STUB (Implementation Required)
"""

from typing import Any, Awaitable, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class AlternateServiceFallback:
    """
    Alternate Service Fallback Strategy for Circuit Breaker.

    Routes requests to an alternate service when the primary circuit is OPEN,
    providing transparent failover. This strategy maintains full functionality
    at the cost of higher latency and potentially higher cost.

    Strategy Characteristics:
        - Use Case: Tiered services, multi-region deployments
        - Performance: <500ms (alternate service call)
        - Dependencies: Alternate service must be available
        - User Experience: Excellent (transparent, no degradation)
        - Complexity: High (cascade risk, cost implications)

    Cascade Prevention:
        - Alternate service MUST have its own circuit breaker
        - Fallback depth limited to 1 (no recursive fallbacks)
        - Monitor alternate service health separately

    Example Usage:
        ```python
        from k1.l5_infrastructure.resilience.fallbacks.alternate_service import AlternateServiceFallback
        from k1.l5_infrastructure.resilience.circuit_breaker_manager import get_circuit_breaker_manager

        # Initialize with alternate service
        manager = get_circuit_breaker_manager()
        fallback = AlternateServiceFallback(
            circuit_breaker_manager=manager,
            alternate_service_name="gpt4o_mini"
        )

        # Primary circuit opens, fallback to alternate
        result = await fallback.invoke(
            service_name="gemma_2b",
            operation=lambda: model_hub.generate(model="gpt4o-mini", prompt=prompt),
            operation_name="llm_inference"
        )
        # result = gpt4o-mini response (transparent to user)
        ```

    Configuration (circuit_breakers.yml):
        ```yaml
        model_hub_local:
          fallback_strategy: ALTERNATE_SERVICE
          fallback_config:
            alternate_service_name: model_hub_remote
            alternate_model: gpt4o-mini
        ```

    ADR References:
        - ADR-0009a: "Invoke alternate service for transparent failover"
        - ADR-0009b: "Local Model Hub uses ALTERNATE_SERVICE fallback"

    WARD Test Example:
        ```python
        from ward import test, fixture
        from k1.l5_infrastructure.resilience.fallbacks.alternate_service import AlternateServiceFallback
        from k1.l5_infrastructure.resilience.circuit_breaker_manager import CircuitBreakerManager

        @fixture
        async def manager():
            return CircuitBreakerManager(config_path="test_config.yml")

        @test("alternate service fallback calls alternate on primary failure")
        async def _(manager=manager):
            fallback = AlternateServiceFallback(
                circuit_breaker_manager=manager,
                alternate_service_name="backup_service"
            )

            # Mock alternate service
            async def alternate_operation():
                return "backup_result"

            result = await fallback.invoke(
                service_name="primary_service",
                operation=alternate_operation,
                operation_name="test_op"
            )
            assert result == "backup_result"

        @test("alternate service fallback raises if alternate also fails")
        async def _(manager=manager):
            fallback = AlternateServiceFallback(
                circuit_breaker_manager=manager,
                alternate_service_name="backup_service"
            )

            # Mock failing alternate
            async def failing_operation():
                raise Exception("Alternate also down")

            with raises(Exception):
                await fallback.invoke(
                    service_name="primary_service",
                    operation=failing_operation,
                    operation_name="test_op"
                )
        ```
    """

    def __init__(self, circuit_breaker_manager: Any, alternate_service_name: str):
        """
        Initialize alternate service fallback strategy.

        Args:
            circuit_breaker_manager: CircuitBreakerManager instance
            alternate_service_name: Name of alternate service circuit

        Performance:
            - Initialization: <1ms (no I/O, simple assignment)
        """
        # TODO(@resilience-team): Initialize fallback strategy
        # 1. Store circuit_breaker_manager for alternate service access
        # 2. Store alternate_service_name for routing
        # 3. Create logger for observability
        self.circuit_breaker_manager = circuit_breaker_manager
        self.alternate_service_name = alternate_service_name
        self.logger = logger.bind(
            fallback_strategy="alternate_service",
            alternate_service=alternate_service_name,
        )

    async def invoke(
        self,
        service_name: str,
        operation: Callable[[], Awaitable[Any]],
        operation_name: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Invoke alternate service fallback strategy.

        Routes the request to the alternate service through its circuit breaker.
        The alternate service MUST have its own circuit breaker to prevent
        cascading failures.

        Execution Flow:
            1. Log fallback invocation (warning level)
            2. Get alternate service circuit breaker from manager
            3. Call operation through alternate's circuit breaker
            4. Return result or propagate exception

        Args:
            service_name: Name of the primary service whose circuit is OPEN
            operation: Async operation to perform on alternate service
            operation_name: Optional operation name (for logging)
            **kwargs: Additional context (unused, for interface consistency)

        Returns:
            Any: Result from alternate service

        Raises:
            Exception: If alternate service also fails or circuit OPEN

        Performance:
            - Target: <500ms (alternate service call)
            - Latency increase: 2-5× (local 150ms → remote 500ms)

        Side Effects:
            - Emits warning log (fallback invoked)
            - Calls alternate service through its circuit breaker
            - Increments circuit_breaker_fallbacks_total metric (via manager)

        Cascade Prevention:
            - Alternate service has its own circuit breaker
            - If alternate circuit OPEN, raises CircuitOpenError
            - No recursive fallbacks (depth limited to 1)

        Example Use Cases:
            ```python
            # Local LLM → Remote LLM
            fallback = AlternateServiceFallback(
                manager,
                alternate_service_name="gpt4o_mini"
            )

            async def remote_inference():
                return await model_hub.generate(
                    model="gpt4o-mini",
                    prompt=prompt
                )

            result = await fallback.invoke(
                service_name="gemma_2b",
                operation=remote_inference,
                operation_name="llm_inference"
            )
            # result = gpt4o-mini response (150ms → 500ms, +$0.0001)

            # Primary region → Backup region
            fallback = AlternateServiceFallback(
                manager,
                alternate_service_name="api_us_west"
            )

            async def backup_region_call():
                return await api_client.call(region="us-west")

            result = await fallback.invoke(
                service_name="api_us_east",
                operation=backup_region_call,
                operation_name="api_call"
            )
            # result = backup region response (100ms → 250ms)
            ```

        Logging Output:
            ```json
            {
                "event": "alternate_service_fallback",
                "fallback_strategy": "alternate_service",
                "primary_service": "gemma_2b",
                "alternate_service": "gpt4o_mini",
                "operation_name": "llm_inference",
                "level": "warning"
            }
            ```

        Cost Implications (LLM Example):
            - Local gemma-2b: Free (VRAM only)
            - Remote gpt4o-mini: $0.0001/token (~$0.10 per 1000 inferences)
            - Monthly cost increase: $0 → $3000 (30M inferences)

        ADR Reference:
            - ADR-0009a: "Alternate service fallback maintains functionality"
        """
        # TODO(@resilience-team): Implement fallback invocation
        # 1. Log fallback:
        #    self.logger.warning(
        #        "alternate_service_fallback",
        #        primary_service=service_name,
        #        alternate_service=self.alternate_service_name,
        #        operation_name=operation_name
        #    )
        # 2. Get alternate circuit breaker:
        #    alternate_circuit = self.circuit_breaker_manager.get_circuit_breaker(
        #        self.alternate_service_name
        #    )
        # 3. Call through alternate's circuit breaker:
        #    result = await alternate_circuit.call(operation)
        # 4. Return result (or propagate exception if alternate fails)
        #    return result
        raise NotImplementedError("Alternate service fallback not implemented")

    def get_strategy_name(self) -> str:
        """
        Get human-readable strategy name.

        Returns:
            "ALTERNATE_SERVICE"

        Performance:
            - <0.001ms (constant return)
        """
        return "ALTERNATE_SERVICE"

    def get_alternate_service_name(self) -> str:
        """
        Get configured alternate service name.

        Returns:
            str: Name of alternate service

        Example:
            ```python
            fallback = AlternateServiceFallback(manager, "gpt4o_mini")
            assert fallback.get_alternate_service_name() == "gpt4o_mini"
            ```
        """
        return self.alternate_service_name


# Expected Lint Errors (Intentional):
# 1. structlog import unused (TODO: use in invoke() logging)
# 2. logger parameter missing in structlog.bind (TODO: configure in __init__)
#
# These will be resolved when @resilience-team implements the TODOs.
