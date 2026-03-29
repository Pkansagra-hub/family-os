"""
k1.fabric.adapters.test_mcp_transport -- TestMCPTransport (5.2.x).

In-memory MCP transport stub for testing. Returns canned responses
for MCP tools/call requests keyed by tool_name.

Design:
  - ``is_connected()`` configurable via constructor (default True).
  - Canned responses keyed by ``tool_name`` string.
  - Dynamic handlers for custom per-test behavior.
  - Thread-safe via RLock for concurrent test scenarios.
  - Capture mode: records all sent requests for assertions.
  - No real MCP server dependency.

Structural subtyping:
  Satisfies IMCPTransport protocol without inheriting from it.

References:
  - mcp_provider.py (3.3.2) -- IMCPTransport protocol
  - TestBridgeAdapter (5.2.4) -- same pattern
  - Epic 5.2 in fabric-implementation-plan.md

Exports:
  TestMCPTransport
  CapturedMCPCall
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from k1.fabric.providers.mcp_provider import MCPRequest, MCPResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Captured call record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedMCPCall:
    """Record of an MCP transport call for test assertions."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    timestamp_ms: int = 0


# ---------------------------------------------------------------------------
# TestMCPTransport
# ---------------------------------------------------------------------------


class TestMCPTransport:
    """
    In-memory MCP transport stub for testing.

    Implements IMCPTransport structurally:
      - async send(request: MCPRequest) -> MCPResponse
      - async ping() -> bool
      - is_connected() -> bool
      - async close() -> None

    Setup helpers for tests:
      - set_connected(flag) -- toggle connectivity
      - add_response(tool_name, response) -- canned MCPResponse for tool
      - add_handler(tool_name, handler) -- dynamic handler (takes MCPRequest, returns MCPResponse)
      - clear_responses() -- reset all canned data
      - get_captured() -- list of all captured calls
      - drain() -- return + clear captured calls
      - call_count -- total calls made
    """

    def __init__(
        self,
        *,
        connected: bool = True,
        default_response: Optional[MCPResponse] = None,
    ) -> None:
        self._connected = connected
        self._default_response = default_response or MCPResponse(
            success=True,
            content=[{"type": "text", "text": "test response"}],
            latency_ms=1,
        )
        self._responses: Dict[str, MCPResponse] = {}
        self._handlers: Dict[str, Callable[[MCPRequest], MCPResponse]] = {}
        self._captured: List[CapturedMCPCall] = []
        self._lock = threading.RLock()

    # ======================================================================
    # IMCPTransport protocol
    # ======================================================================

    async def send(self, request: MCPRequest) -> MCPResponse:
        """
        Send an MCP request and return canned response.

        Priority:
          1. Dynamic handler (if registered for tool_name)
          2. Canned response (if registered for tool_name)
          3. Default response
        """
        with self._lock:
            self._captured.append(
                CapturedMCPCall(
                    tool_name=request.tool_name,
                    arguments=dict(request.arguments),
                    trace_id=request.trace_id,
                    timestamp_ms=int(time.monotonic() * 1000),
                )
            )

            # Dynamic handler first
            handler = self._handlers.get(request.tool_name)
            if handler is not None:
                return handler(request)

            # Canned response
            canned = self._responses.get(request.tool_name)
            if canned is not None:
                return canned

            return self._default_response

    async def ping(self) -> bool:
        """Return connected state."""
        return self._connected

    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected

    async def close(self) -> None:
        """Close transport (no-op for test)."""
        self._connected = False

    # ======================================================================
    # Test setup helpers
    # ======================================================================

    def set_connected(self, flag: bool) -> None:
        """Toggle connectivity state."""
        self._connected = flag

    def add_response(self, tool_name: str, response: MCPResponse) -> None:
        """Register a canned MCPResponse for a tool_name."""
        with self._lock:
            self._responses[tool_name] = response

    def add_handler(
        self,
        tool_name: str,
        handler: Callable[[MCPRequest], MCPResponse],
    ) -> None:
        """Register a dynamic handler for a tool_name."""
        with self._lock:
            self._handlers[tool_name] = handler

    def clear_responses(self) -> None:
        """Remove all canned responses and handlers."""
        with self._lock:
            self._responses.clear()
            self._handlers.clear()

    def get_captured(self) -> List[CapturedMCPCall]:
        """Return defensive copy of captured calls."""
        with self._lock:
            return list(self._captured)

    def drain(self) -> List[CapturedMCPCall]:
        """Return and clear captured calls."""
        with self._lock:
            captured = list(self._captured)
            self._captured.clear()
            return captured

    @property
    def call_count(self) -> int:
        """Total number of send() calls."""
        with self._lock:
            return len(self._captured)
