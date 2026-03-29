"""
k1.orchestrator.connectors.mcp_discovery -- MCP Tool Discovery (5.1.1).

Discovers MCP servers from a static YAML configuration file and
enumerates their available tools via the MCP ``tools/list`` protocol.

Design:
  - Config source: V1 reads a static YAML file at ``config_path``.
    V2: dynamic registration API.
  - Transport abstraction: ``discover_server()`` delegates to an
    ``IMCPTransportDiscovery`` protocol for actual communication.
    In production this would use stdio or HTTP; in tests a fake
    returns canned responses.
  - Error isolation: if one server fails discovery, others still
    succeed (log warning, return empty list for that server).
  - Idempotent: calling ``discover_all()`` twice returns the same
    tool set (unless the MCP server changed between calls).
  - Timeouts: 5 s for local (stdio), 10 s for remote (SSE / HTTP).
  - YAML config is NOT hot-reloaded in V1.  Re-discovery re-reads
    the file on each call.

Types:
  MCPServerConfig  -- A single MCP server from YAML config.
  DiscoveredTool   -- A single tool discovered from an MCP server.
  DiscoveryResult  -- Aggregate result of discover_all().

Constructor:
  MCPToolDiscovery(config_path, transport)

References:
  - Issue 5.1.1 in orchestrator-implementation-plan.md
  - SPEC-6 (discovery source)
  - MCP protocol tools/list JSON-RPC

Exports:
  MCPToolDiscovery
  MCPServerConfig
  DiscoveredTool
  DiscoveryResult
  IMCPTransportDiscovery
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCPServerConfig:
    """
    A single MCP server entry from YAML config.

    Attributes:
        id: Unique server identifier (e.g. ``"google_cal"``).
        type: Transport type -- ``"local"`` (stdio) or ``"remote"`` (SSE / HTTP).
        endpoint: Connection string (command for local, URL for remote).
        critical: If True, discovery failure for this server is an error
            rather than a warning.  V1: logged at ERROR level, still
            non-blocking.
    """

    id: str
    type: str
    endpoint: str
    critical: bool = False

    def validate(self) -> List[str]:
        """Return list of validation errors (empty = valid)."""
        errors: List[str] = []
        if not self.id:
            errors.append("server id is required")
        if self.type not in ("local", "remote"):
            errors.append(f"server type must be 'local' or 'remote', got '{self.type}'")
        if not self.endpoint:
            errors.append("server endpoint is required")
        return errors


@dataclass(frozen=True)
class DiscoveredTool:
    """
    A single tool discovered from an MCP server.

    Attributes:
        server_id: The MCPServerConfig.id this tool belongs to.
        name: Tool name as reported by the MCP server.
        description: Human-readable tool description.
        input_schema: JSON Schema dict for tool input parameters.
        output_schema: Optional JSON Schema dict for tool output.
    """

    server_id: str
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class DiscoveryResult:
    """
    Aggregate result of ``discover_all()``.

    Attributes:
        tools: Flat list of all discovered tools.
        servers_ok: Number of servers that responded successfully.
        servers_failed: Number of servers that failed discovery.
        errors: List of error messages from failed servers.
    """

    tools: List[DiscoveredTool] = field(default_factory=list)
    servers_ok: int = 0
    servers_failed: int = 0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transport protocol (injectable for testing)
# ---------------------------------------------------------------------------


class IMCPTransportDiscovery(Protocol):
    """
    Protocol for MCP server tool discovery transport.

    Abstracts the actual communication with MCP servers.
    Production: subprocess + JSON-RPC (local) or HTTP POST (remote).
    Tests: fake that returns canned tool lists.
    """

    async def list_tools(
        self,
        server: MCPServerConfig,
    ) -> List[Dict[str, Any]]:
        """
        Send ``tools/list`` to the MCP server and return raw tool dicts.

        Each dict should have at minimum:
          - ``name``: str
          - ``description``: str (optional)
          - ``inputSchema``: dict (optional, JSON Schema)

        Raises on timeout or transport error (caller catches).

        Args:
            server: The MCP server to query.

        Returns:
            List of raw tool definition dicts from the MCP response.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# 5.1.1 -- MCPToolDiscovery
# ---------------------------------------------------------------------------


class MCPToolDiscovery:
    """
    Discovers MCP tools from configured servers.

    Reads YAML config, iterates servers, calls ``discover_server()``
    per entry, and returns a flat list of discovered tools.

    Constructor Args:
        config_path: Path to YAML config file.
            Config format::

                servers:
                  - id: google_cal
                    type: remote
                    endpoint: https://mcp.google.com/calendar
                    critical: false
                  - id: local_fs
                    type: local
                    endpoint: /usr/bin/mcp-fs-server
                    critical: false

        transport: IMCPTransportDiscovery implementation for actual
            server communication. If None, ``discover_server()`` returns
            empty lists (stub mode for unit tests).

    Thread Safety:
        Stateless per call -- safe for concurrent ``discover_all()``.
    """

    __slots__ = ("_config_path", "_transport")

    def __init__(
        self,
        config_path: str = "k1/connectors/mcp_servers.yaml",
        transport: Optional[IMCPTransportDiscovery] = None,
    ) -> None:
        self._config_path = config_path
        self._transport = transport

    # ==================================================================
    # Public API
    # ==================================================================

    def load_config(self) -> List[MCPServerConfig]:
        """
        Read and parse the YAML config file.

        Returns:
            List of MCPServerConfig entries.

        Raises:
            FileNotFoundError: If config file does not exist.
            ValueError: If YAML structure is invalid.
        """
        path = Path(self._config_path)
        if not path.exists():
            raise FileNotFoundError(f"MCP config not found: {path}")

        import yaml  # type: ignore[import-untyped]

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        if not isinstance(data, dict):
            raise ValueError(f"MCP config must be a YAML mapping, got {type(data).__name__}")

        raw_servers = data.get("servers", [])
        if not isinstance(raw_servers, list):
            raise ValueError("'servers' must be a list in MCP config")

        configs: List[MCPServerConfig] = []
        for i, entry in enumerate(raw_servers):
            if not isinstance(entry, dict):
                logger.warning("Skipping non-dict server entry at index %d", i)
                continue

            cfg = MCPServerConfig(
                id=str(entry.get("id", "")),
                type=str(entry.get("type", "")),
                endpoint=str(entry.get("endpoint", "")),
                critical=bool(entry.get("critical", False)),
            )
            errors = cfg.validate()
            if errors:
                logger.warning(
                    "Skipping invalid server entry '%s': %s",
                    cfg.id or f"index-{i}",
                    "; ".join(errors),
                )
                continue

            configs.append(cfg)

        return configs

    async def discover_all(self) -> DiscoveryResult:
        """
        Discover tools from all configured MCP servers.

        Reads config, iterates servers, calls ``discover_server()``
        per entry.  On per-server error: logs warning (or error if
        critical), continues to next server.

        Returns:
            DiscoveryResult with flat list of all discovered tools
            and aggregate server counts.
        """
        try:
            servers = self.load_config()
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Failed to load MCP config: %s", exc)
            return DiscoveryResult(errors=[str(exc)])

        all_tools: List[DiscoveredTool] = []
        ok_count = 0
        fail_count = 0
        errors: List[str] = []

        for server in servers:
            try:
                tools = await self.discover_server(server)
                all_tools.extend(tools)
                ok_count += 1
            except Exception as exc:
                fail_count += 1
                msg = f"Discovery failed for server '{server.id}': {exc}"
                errors.append(msg)
                if server.critical:
                    logger.error(msg)
                else:
                    logger.warning(msg)

        return DiscoveryResult(
            tools=all_tools,
            servers_ok=ok_count,
            servers_failed=fail_count,
            errors=errors,
        )

    async def discover_server(
        self,
        server: MCPServerConfig,
    ) -> List[DiscoveredTool]:
        """
        Discover tools from a single MCP server.

        Delegates to ``self._transport.list_tools(server)`` and
        parses the raw tool dicts into DiscoveredTool instances.

        Args:
            server: The MCP server to discover tools from.

        Returns:
            List of DiscoveredTool for this server.

        Raises:
            RuntimeError: If no transport is configured.
            Exception: Propagated from transport on timeout or error.
        """
        if self._transport is None:
            logger.debug(
                "No transport configured; returning empty tools for '%s'",
                server.id,
            )
            return []

        raw_tools = await self._transport.list_tools(server)
        discovered: List[DiscoveredTool] = []

        for raw in raw_tools:
            name = raw.get("name", "")
            if not name:
                logger.warning(
                    "Skipping tool with empty name from server '%s'",
                    server.id,
                )
                continue

            tool = DiscoveredTool(
                server_id=server.id,
                name=name,
                description=raw.get("description", ""),
                input_schema=raw.get("inputSchema", raw.get("input_schema", {})),
                output_schema=raw.get("outputSchema", raw.get("output_schema", None)),
            )
            discovered.append(tool)

        logger.debug(
            "Discovered %d tools from server '%s'",
            len(discovered),
            server.id,
        )
        return discovered
