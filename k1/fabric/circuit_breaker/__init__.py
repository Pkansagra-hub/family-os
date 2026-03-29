"""
k1.fabric.circuit_breaker -- Circuit Breaker subsystem (Epic 3.4).

Provides per-provider circuit breakers with retry strategy and
per-provider-type configuration defaults.

Submodules:
  breaker        -- CircuitBreaker state machine + retry logic (3.4.1 + 3.4.3)
  breaker_config -- Per-provider default configs (3.4.2)

Usage::

    from k1.fabric.circuit_breaker import (
        CircuitBreaker,
        CircuitBreakerConfig,
        get_breaker_config,
    )

    config = get_breaker_config("MCP", provider_config=my_mcp_config)
    cb = CircuitBreaker("mcp-weather", config=config)
    result = await cb.call(provider.execute, request, context, trace_id)
"""

from k1.fabric.circuit_breaker.breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerOpen,
    CircuitBreakerState,
    FailureRecord,
    IStateChangeListener,
)
from k1.fabric.circuit_breaker.breaker_config import (
    AGENT_CONFIG,
    BRIDGE_CONFIG,
    CONCIERGE_CONFIG,
    DEFAULT_CONFIG,
    MCP_LOCAL_CONFIG,
    MCP_REMOTE_CONFIG,
    WASM_CONFIG,
    WORKFLOW_CONFIG,
    get_breaker_config,
)

__all__ = [
    # breaker.py
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitBreakerOpen",
    "CircuitBreakerState",
    "FailureRecord",
    "IStateChangeListener",
    # breaker_config.py
    "AGENT_CONFIG",
    "BRIDGE_CONFIG",
    "CONCIERGE_CONFIG",
    "DEFAULT_CONFIG",
    "MCP_LOCAL_CONFIG",
    "MCP_REMOTE_CONFIG",
    "WASM_CONFIG",
    "WORKFLOW_CONFIG",
    "get_breaker_config",
]
