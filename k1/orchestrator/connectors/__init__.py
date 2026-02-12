"""
k1.orchestrator.connectors -- MCP Connector Lifecycle (Milestone 5).

Re-exports for the connector subsystem:
  MCPToolDiscovery         -- Discover MCP tools from config (5.1.1)
  MCPServerConfig          -- Server config entry
  DiscoveredTool           -- Single discovered tool
  DiscoveryResult          -- Aggregate discovery result
  IMCPTransportDiscovery   -- Transport protocol for discovery

  MCPRegistrationBridge    -- Registration bridge to Fabric (5.1.2)
  RegistrationResult       -- Aggregate registration result
  build_capability_id      -- Naming convention helper
  infer_type               -- Tool type inference

  ConnectorLifecycleManager -- Lifecycle orchestrator (5.1.3)

  K0ProxyClient            -- K0 proxy client (5.1.4)
  ProxyRequest             -- Proxy request type
  ProxyResponse            -- Proxy response type
  ProxyUnavailableError    -- Proxy not configured error
  ProxyRateLimitedError    -- Rate limit error
"""

from k1.orchestrator.connectors.connector_lifecycle import ConnectorLifecycleManager
from k1.orchestrator.connectors.k0_proxy_client import (
    K0ProxyClient,
    ProxyRateLimitedError,
    ProxyRequest,
    ProxyResponse,
    ProxyUnavailableError,
)
from k1.orchestrator.connectors.mcp_discovery import (
    DiscoveredTool,
    DiscoveryResult,
    IMCPTransportDiscovery,
    MCPServerConfig,
    MCPToolDiscovery,
)
from k1.orchestrator.connectors.mcp_registrar import (
    MCPRegistrationBridge,
    RegistrationResult,
    build_capability_id,
    infer_type,
)

__all__ = [
    # 5.1.1 -- MCP Tool Discovery
    "MCPToolDiscovery",
    "MCPServerConfig",
    "DiscoveredTool",
    "DiscoveryResult",
    "IMCPTransportDiscovery",
    # 5.1.2 -- MCP Registration Bridge
    "MCPRegistrationBridge",
    "RegistrationResult",
    "build_capability_id",
    "infer_type",
    # 5.1.3 -- Connector Lifecycle Manager
    "ConnectorLifecycleManager",
    # 5.1.4 -- K0 Proxy Client
    "K0ProxyClient",
    "ProxyRequest",
    "ProxyResponse",
    "ProxyUnavailableError",
    "ProxyRateLimitedError",
]
