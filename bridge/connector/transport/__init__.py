"""bridge/connector/transport — wire-level transports for MCP children.

PR#2 ships :class:`MCPStdioTransport`, a thin wrapper around
``fastmcp.client.transports.StdioTransport`` plus ``fastmcp.Client``.
Future PRs may add HTTP / WebSocket transports for adapters that
cannot run as local subprocesses (e.g. cloud-only IFL connectors).

The transport object is owned by an :class:`MCPChild`; the connector
gateway never touches transports directly — it goes through the
process manager Protocol.
"""

from __future__ import annotations

from .mcp_stdio import MCPStdioTransport

__all__ = ["MCPStdioTransport"]
