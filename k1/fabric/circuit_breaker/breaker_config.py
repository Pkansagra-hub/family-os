"""
k1.fabric.circuit_breaker.breaker_config -- Per-provider CB configs (3.4.2).

Provides hardcoded default CircuitBreakerConfig per ProviderType, matching
the spec in ``fabric_discussion.md`` Section 19:

  | Provider Type  | Timeout | Threshold | Fallback              |
  |----------------|---------|-----------|-----------------------|
  | MCP (local)    | 10 s    | 3/min     | tool offline          |
  | MCP (remote)   | 15 s    | 3/min     | tool offline          |
  | WASM           |  5 s    | 5/min     | computation failed    |
  | Bridge (K0)    | 10 s    | 3/min     | LOCAL COLD fallback   |
  | Agent          | 30 s    | 2/min     | agent execution failed|
  | Workflow       | 60 s    | 1/min     | workflow failed       |
  | Default        | 30 s    | 5/min     | capability unavailable|

MCP has two sub-configs driven by ``ProviderConfig.transport``:
  - stdio (local)          -> 10 s timeout
  - sse / streamable-http  -> 15 s timeout

Override:
  Per-provider overrides can be supplied via ``policies.contract.yaml``
  (1.2.3) and passed as explicit ``CircuitBreakerConfig`` to the
  ``CircuitBreaker`` constructor.  The ``get_config()`` facade falls
  back to hardcoded defaults when no override is supplied.

References:
  - fabric_discussion.md Section 19 (Error Handling and Circuit Breakers)
  - policies.contract.yaml (per-provider override path)
  - Epic 3.4.2 in fabric-implementation-plan.md

Exports:
  get_breaker_config       -- Resolve config for a provider type
  DEFAULT_CONFIG           -- Global default config (30 s, 5/min)
  MCP_LOCAL_CONFIG         -- MCP local stdio (10 s, 3/min)
  MCP_REMOTE_CONFIG        -- MCP remote SSE/HTTP (15 s, 3/min)
  WASM_CONFIG              -- WASM sandboxed (5 s, 5/min)
  BRIDGE_CONFIG            -- Bridge K0 (10 s, 3/min)
  AGENT_CONFIG             -- Agent execution (30 s, 2/min)
  WORKFLOW_CONFIG          -- Workflow DAG (60 s, 1/min)
  CONCIERGE_CONFIG         -- Concierge FSM (5 s, 5/min)
"""

from __future__ import annotations

from typing import Dict, Optional

from k1.fabric.circuit_breaker.breaker import CircuitBreakerConfig
from k1.fabric.types import ProviderConfig, ProviderType, TransportType

# ---------------------------------------------------------------------------
# Hardcoded defaults per provider type
# ---------------------------------------------------------------------------


DEFAULT_CONFIG = CircuitBreakerConfig(
    timeout_ms=30000,
    failure_threshold=5,
    failure_window_ms=60000,
    half_open_after_ms=30000,
    max_retries=2,
    fallback_error_code="capability_unavailable",
)

MCP_LOCAL_CONFIG = CircuitBreakerConfig(
    timeout_ms=10000,
    failure_threshold=3,
    failure_window_ms=60000,
    half_open_after_ms=30000,
    max_retries=2,
    fallback_error_code="tool_offline",
)

MCP_REMOTE_CONFIG = CircuitBreakerConfig(
    timeout_ms=15000,
    failure_threshold=3,
    failure_window_ms=60000,
    half_open_after_ms=30000,
    max_retries=2,
    fallback_error_code="tool_offline",
)

WASM_CONFIG = CircuitBreakerConfig(
    timeout_ms=5000,
    failure_threshold=5,
    failure_window_ms=60000,
    half_open_after_ms=15000,
    max_retries=2,
    fallback_error_code="computation_failed",
)

BRIDGE_CONFIG = CircuitBreakerConfig(
    timeout_ms=10000,
    failure_threshold=3,
    failure_window_ms=60000,
    half_open_after_ms=30000,
    max_retries=2,
    fallback_error_code="bridge_offline",
)

AGENT_CONFIG = CircuitBreakerConfig(
    timeout_ms=30000,
    failure_threshold=2,
    failure_window_ms=60000,
    half_open_after_ms=30000,
    max_retries=2,
    fallback_error_code="agent_execution_failed",
)

WORKFLOW_CONFIG = CircuitBreakerConfig(
    timeout_ms=60000,
    failure_threshold=1,
    failure_window_ms=60000,
    half_open_after_ms=60000,
    max_retries=1,  # Workflows are expensive -- only 1 retry
    fallback_error_code="workflow_failed",
)

CONCIERGE_CONFIG = CircuitBreakerConfig(
    timeout_ms=5000,
    failure_threshold=5,
    failure_window_ms=60000,
    half_open_after_ms=10000,
    max_retries=2,
    fallback_error_code="concierge_state_failed",
)


# ---------------------------------------------------------------------------
# Lookup table: ProviderType -> default config
# ---------------------------------------------------------------------------


_TYPE_CONFIGS: Dict[str, CircuitBreakerConfig] = {
    ProviderType.WASM.value: WASM_CONFIG,
    ProviderType.BRIDGE.value: BRIDGE_CONFIG,
    ProviderType.AGENT.value: AGENT_CONFIG,
    ProviderType.WORKFLOW.value: WORKFLOW_CONFIG,
    ProviderType.CONCIERGE.value: CONCIERGE_CONFIG,
    # MCP handled separately (local vs remote)
}


def _is_mcp_remote(provider_config: Optional[ProviderConfig] = None) -> bool:
    """Determine if an MCP provider is remote (SSE or streamable-http)."""
    if provider_config is None:
        return False
    transport = (provider_config.transport or "").lower()
    return transport in (
        TransportType.SSE.value,
        TransportType.STREAMABLE_HTTP.value,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_breaker_config(
    provider_type: str,
    provider_config: Optional[ProviderConfig] = None,
    override: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreakerConfig:
    """
    Resolve the CircuitBreakerConfig for a provider.

    Resolution order:
      1. Explicit override (from policies.contract.yaml)
      2. Per-type hardcoded default
      3. Global DEFAULT_CONFIG

    For MCP providers, the transport field of ProviderConfig
    determines whether local (stdio, 10s) or remote (SSE/HTTP, 15s)
    config is used.

    Args:
        provider_type: ProviderType value string (e.g. "MCP", "WASM").
        provider_config: Optional ProviderConfig for transport detection.
        override: Explicit override from policy config (highest priority).

    Returns:
        CircuitBreakerConfig appropriate for the provider.
    """
    # 1. Explicit override wins
    if override is not None:
        return override

    # 2. MCP has sub-configs by transport
    if provider_type == ProviderType.MCP.value:
        if _is_mcp_remote(provider_config):
            return MCP_REMOTE_CONFIG
        return MCP_LOCAL_CONFIG

    # 3. Type-specific default
    if provider_type in _TYPE_CONFIGS:
        return _TYPE_CONFIGS[provider_type]

    # 4. Global default
    return DEFAULT_CONFIG
