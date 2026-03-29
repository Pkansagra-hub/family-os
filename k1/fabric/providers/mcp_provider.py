"""
k1.fabric.providers.mcp_provider -- MCPProvider (3.3.2).

MCP tool execution via the Model Context Protocol.
Supports three transport types:
  - stdio:           Local MCP servers (same machine)
  - sse:             Remote MCP servers (cloud endpoints)
  - streamable-http: Remote MCP servers (HTTP streaming)

Execution flow (from fabric_discussion.md Section 11):
  1. Receive CapabilityRequest
  2. Look up MCP server connection (from ProviderConfig.endpoint)
  3. Build MCP tools/call message
  4. Send to MCP server via configured transport
  5. Await response (within timeout from config.max_execution_ms)
  6. Parse MCP tool_result
  7. Return CapabilityResult

Error handling:
  - Server not found -> MCPServerNotFoundError
  - Tool not found -> MCPToolNotFoundError
  - Transport failure -> MCPTransportError
  - Timeout -> ProviderTimeoutError (from base_provider)

Design:
  - Transport is injected via ``IMCPTransport`` port (Protocol).
    Concrete transports (StdioTransport, SSETransport, HttpTransport)
    are provided externally by FabricFactory during bootstrap.
  - MCPProvider does NOT depend on any external MCP library at import
    time -- only on the transport protocol.
  - Thread-safe: no mutable state after construction.

References:
  - fabric_discussion.md Section 11 (Provider Type 1: MCP Provider)
  - Epic 3.3.2 in fabric-implementation-plan.md
  - ProviderConfig.endpoint, ProviderConfig.transport (types.py 1.3.9)

Exports:
  MCPProvider           -- MCP tool execution provider
  IMCPTransport         -- Transport port protocol
  MCPRequest            -- Request message to MCP server
  MCPResponse           -- Response message from MCP server
  MCPProviderError      -- Base MCP exception
  MCPServerNotFoundError -- Server connection failed
  MCPToolNotFoundError  -- Tool not found on server
  MCPTransportError     -- Transport-level failure
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from k1.fabric.providers.base_provider import (
    BaseProvider,
    ProviderExecutionError,
    ProviderTimeoutError,
)
from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP message types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCPRequest:
    """
    MCP JSON-RPC request message for tools/call.

    Matches the MCP protocol specification::

        {
          "method": "tools/call",
          "params": {
            "name": "<tool_name>",
            "arguments": { ... }
          }
        }

    Attributes:
        method: JSON-RPC method (always "tools/call" for execution).
        tool_name: Name of the tool on the MCP server.
        arguments: Tool arguments from CapabilityRequest.params.
        timeout_ms: Execution timeout in milliseconds.
        trace_id: Cognitive trace ID for observability.
    """

    method: str = "tools/call"
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000
    trace_id: str = ""


@dataclass(frozen=True)
class MCPResponse:
    """
    MCP JSON-RPC response from tools/call.

    Attributes:
        success: True if the tool executed without error.
        content: Response content (list of content blocks per MCP spec).
            Each block typically has {"type": "text", "text": "..."}.
        error_message: Error description if success=False.
        latency_ms: Server-reported or measured execution time.
        raw: Optional raw response for debugging.
    """

    success: bool = True
    content: List[Dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    latency_ms: int = 0
    raw: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Transport port (Protocol)
# ---------------------------------------------------------------------------


class IMCPTransport(Protocol):
    """
    Transport port for MCP server communication.

    Concrete implementations handle the specifics of each transport
    type (stdio subprocess, SSE stream, HTTP POST).  Injected into
    MCPProvider by FabricFactory during bootstrap.

    Implementations:
      - StdioTransport: Subprocess stdio pipe (local MCP servers)
      - SSETransport: Server-Sent Events (remote MCP servers)
      - HttpTransport: Streamable HTTP (remote MCP servers)

    All methods are async to support non-blocking I/O.
    """

    async def send(self, request: MCPRequest) -> MCPResponse:
        """
        Send an MCP request and await the response.

        Args:
            request: The MCP request message.

        Returns:
            MCPResponse with tool execution result.

        Raises:
            Exception on transport-level failure (connection lost,
            server unreachable, etc.).
        """
        ...

    async def ping(self) -> bool:
        """
        Check if the MCP server is reachable and responsive.

        Returns:
            True if server responds to health probe, False otherwise.
        """
        ...

    def is_connected(self) -> bool:
        """Check if the transport has an active connection."""
        ...

    async def close(self) -> None:
        """Close the transport connection and release resources."""
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPProviderError(ProviderExecutionError):
    """Base exception for MCP provider operations."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
    ) -> None:
        super().__init__(
            provider_id,
            message,
            retriable=retriable,
            error_code="mcp_error",
        )


class MCPServerNotFoundError(MCPProviderError):
    """MCP server is not reachable or not configured."""

    def __init__(self, provider_id: str, endpoint: str) -> None:
        self.endpoint = endpoint
        super().__init__(
            provider_id,
            f"MCP server not found at endpoint: {endpoint}",
            retriable=True,
        )


class MCPToolNotFoundError(MCPProviderError):
    """Requested tool is not available on the MCP server."""

    def __init__(self, provider_id: str, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(
            provider_id,
            f"Tool '{tool_name}' not found on MCP server",
            retriable=False,
        )


class MCPTransportError(MCPProviderError):
    """Transport-level failure (connection lost, protocol error)."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = True,
    ) -> None:
        super().__init__(provider_id, message, retriable=retriable)


# ---------------------------------------------------------------------------
# MCPProvider
# ---------------------------------------------------------------------------


class MCPProvider(BaseProvider):
    """
    MCP tool execution provider (3.3.2).

    Handles capability execution via the Model Context Protocol.
    Supports stdio (local), SSE (remote), and streamable-http (remote)
    transports through the injected ``IMCPTransport`` port.

    Constructor Args:
        config: ProviderConfig with endpoint, transport type, and limits.
        transport: IMCPTransport implementation for the configured transport.
        capability_names: List of capability names this provider handles.
        tool_name_map: Optional mapping from fabric capability_name to
            the MCP server's tool name (when they differ).

    Usage::

        provider = MCPProvider(
            config=ProviderConfig(
                provider_id="weather_mcp",
                provider_type="MCP",
                endpoint="http://localhost:8080",
                transport="sse",
            ),
            transport=my_sse_transport,
            capability_names=["tool.execute.weather"],
        )
        result = await provider.execute(request, context, trace_id)

    Wrapped by CircuitBreaker (3.4.1) in the execution path:
      - Local MCP (stdio): 10s timeout, 3 failures/min
      - Remote MCP (SSE/HTTP): 15s timeout, 3 failures/min
    """

    __slots__ = ("_transport", "_capability_names", "_tool_name_map")

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: IMCPTransport,
        capability_names: Optional[List[str]] = None,
        tool_name_map: Optional[Dict[str, str]] = None,
        **_kwargs: Any,
    ) -> None:
        """
        Args:
            config: Provider configuration (endpoint, transport, limits).
            transport: MCP transport implementation.
            capability_names: Capabilities this provider handles.
                Defaults to empty list.
            tool_name_map: Optional mapping from fabric capability name
                to MCP server tool name.  When None, capability_name
                is used as-is.
            **_kwargs: Ignored (allows ProviderFactory port_deps pass-through).
        """
        super().__init__(config)
        self._transport = transport
        self._capability_names: List[str] = list(capability_names or [])
        self._tool_name_map: Dict[str, str] = dict(tool_name_map or {})

    # ======================================================================
    # CapabilityProvider interface
    # ======================================================================

    def capabilities(self) -> List[str]:
        """Return the list of capability names this MCP provider handles."""
        return list(self._capability_names)

    async def health_check(self) -> ProviderHealth:
        """
        Ping the MCP server to check health.

        Uses transport.ping() for connectivity check.  Returns
        HEALTHY/UNHEALTHY based on the result.
        """
        start = time.monotonic()
        try:
            reachable = await self._transport.ping()
            latency_ms = int((time.monotonic() - start) * 1000)
            if reachable:
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=ProviderStatus.HEALTHY.value,
                    latency_ms=latency_ms,
                )
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                latency_ms=latency_ms,
                error="ping returned false",
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning("[%s] health_check failed: %s", self.provider_id, exc)
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderStatus.UNHEALTHY.value,
                latency_ms=latency_ms,
                error=str(exc),
            )

    # ======================================================================
    # Internal execution (BaseProvider._execute)
    # ======================================================================

    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        MCP-specific execution logic.

        Flow:
          1. Check transport connectivity
          2. Resolve MCP tool name
          3. Build MCPRequest
          4. Send via transport
          5. Parse MCPResponse
          6. Return CapabilityResult
        """
        start = time.monotonic()

        # --- Step 1: Check transport ---
        if not self._transport.is_connected():
            endpoint = self.config.endpoint or "<no endpoint>"
            raise MCPServerNotFoundError(self.provider_id, endpoint)

        # --- Step 2: Resolve tool name ---
        tool_name = self._resolve_tool_name(request.capability_name)

        # --- Step 3: Build MCP request ---
        mcp_request = MCPRequest(
            method="tools/call",
            tool_name=tool_name,
            arguments=dict(request.params),
            timeout_ms=self.config.max_execution_ms,
            trace_id=trace_id,
        )

        logger.debug(
            "[%s] MCP call: tool=%s, endpoint=%s, trace=%s",
            self.provider_id,
            tool_name,
            self.config.endpoint,
            trace_id,
        )

        # --- Step 4: Send via transport ---
        try:
            mcp_response = await self._transport.send(mcp_request)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Check if it's a timeout
            if elapsed_ms >= self.config.max_execution_ms:
                raise ProviderTimeoutError(self.provider_id, self.config.max_execution_ms) from exc
            raise MCPTransportError(
                self.provider_id,
                f"Transport error during tools/call: {exc}",
                retriable=True,
            ) from exc

        # --- Step 5: Check timeout after transport ---
        self._check_timeout(start)

        # --- Step 6: Parse response and return ---
        return self._parse_response(request, mcp_response, trace_id, start)

    # ======================================================================
    # Private helpers
    # ======================================================================

    def _resolve_tool_name(self, capability_name: str) -> str:
        """
        Map Fabric capability name to MCP server tool name.

        If tool_name_map has an override, use it.  Otherwise,
        use the capability_name as-is.
        """
        return self._tool_name_map.get(capability_name, capability_name)

    def _parse_response(
        self,
        request: CapabilityRequest,
        response: MCPResponse,
        trace_id: str,
        start: float,
    ) -> CapabilityResult:
        """Convert MCPResponse to CapabilityResult."""
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if not response.success:
            # Check for tool-not-found pattern
            error_lower = response.error_message.lower()
            if "not found" in error_lower or "unknown tool" in error_lower:
                tool_name = self._resolve_tool_name(request.capability_name)
                raise MCPToolNotFoundError(self.provider_id, tool_name)

            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="mcp_tool_error",
                error_message=response.error_message or "MCP tool execution failed",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
                execution_time_ms=response.latency_ms,
            )

        # Extract data from content blocks
        data = self._extract_data(response.content)

        return CapabilityResult.success_result(
            request_id=request.request_id,
            data=data,
            provider_id=self.provider_id,
            trace_id=trace_id,
            duration_ms=elapsed_ms,
            execution_time_ms=response.latency_ms,
        )

    @staticmethod
    def _extract_data(content: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract structured data from MCP content blocks.

        MCP responses typically have content blocks like::

            [{"type": "text", "text": "..."}, {"type": "image", ...}]

        We extract:
          - Single text block containing JSON object -> parsed dict
          - Single text block (plain text) -> {"result": text_value}
          - Multiple blocks -> {"content": [all_blocks]}
          - Empty -> {"result": None}
        """
        if not content:
            return {"result": None}

        # Single text block: try JSON parse, fall back to string
        if len(content) == 1 and content[0].get("type") == "text":
            text_value = content[0].get("text", "")
            # Try to parse as JSON -- MCP tools commonly return JSON in text
            if text_value and text_value.strip().startswith("{"):
                try:
                    import json

                    parsed = json.loads(text_value)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            return {"result": text_value}

        # Multiple blocks or non-text: return full content array
        return {"content": list(content)}

    def __repr__(self) -> str:
        return (
            f"MCPProvider("
            f"provider_id={self.provider_id!r}, "
            f"endpoint={self.config.endpoint!r}, "
            f"transport={self.config.transport!r}, "
            f"capabilities={len(self._capability_names)})"
        )
