"""
k1.tools.mcp_servers.weather.server -- Weather MCP Server (SSE transport).

MCP server entry point for weather data retrieval.
Unlike the calendar server (stdio), this server is designed for SSE
(Server-Sent Events) transport -- each request/response uses JSON-RPC
routed through handle_message, but the transport layer is SSE-compatible.

Implements the MCP protocol subset needed for tool execution:
  - initialize: Server capabilities and info
  - tools/list: Advertise available tools
  - tools/call: Execute a tool by name
  - ping: Health check

MCP Protocol Reference:
  - JSON-RPC 2.0 over SSE
  - tools/call params: {"name": str, "arguments": dict}
  - tools/call result: {"content": [{"type": "text", "text": str}]}

References:
  - fabric_tool_implementation_plan.md Phase 2, Section 4.1
  - fabric_developer_guide.md Section 4
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from k1.tools.mcp_servers.weather.api_client import WeatherAPIClient
from k1.tools.mcp_servers.weather.cache import WeatherCache
from k1.tools.mcp_servers.weather.handlers import WeatherHandlers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (advertised via tools/list)
# ---------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "tool.read.weather_current",
        "description": "Get current weather conditions for a location",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, zip code, or lat,lon coordinates",
                },
                "units": {
                    "type": "string",
                    "description": "Unit system: metric, imperial, or kelvin (default: metric)",
                    "enum": ["metric", "imperial", "kelvin"],
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "tool.read.weather_forecast",
        "description": "Get multi-day weather forecast for a location",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, zip code, or lat,lon coordinates",
                },
                "days": {
                    "type": "number",
                    "description": "Number of forecast days, 1-7 (default: 3)",
                },
                "units": {
                    "type": "string",
                    "description": "Unit system: metric, imperial, or kelvin (default: metric)",
                    "enum": ["metric", "imperial", "kelvin"],
                },
            },
            "required": ["location"],
        },
    },
]


# ---------------------------------------------------------------------------
# WeatherMCPServer
# ---------------------------------------------------------------------------


class WeatherMCPServer:
    """
    MCP server for weather data (SSE transport).

    Routes JSON-RPC messages to the appropriate handler.
    Stateless per-request; all state lives in the cache.

    Args:
        api_client: Optional WeatherAPIClient. Defaults to built-in.
        cache_ttl: Cache TTL in seconds. Default 300 (5 min).
    """

    __slots__ = ("_api_client", "_cache", "_handlers", "_tool_map")

    def __init__(
        self,
        api_client: Optional[WeatherAPIClient] = None,
        cache_ttl: float = 300.0,
    ) -> None:
        self._api_client = api_client or WeatherAPIClient()
        self._cache = WeatherCache(ttl_seconds=cache_ttl)
        self._handlers = WeatherHandlers(
            api_client=self._api_client,
            cache=self._cache,
        )
        self._tool_map: Dict[
            str, Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]
        ] = {
            "tool.read.weather_current": self._handlers.weather_current,
            "tool.read.weather_forecast": self._handlers.weather_forecast,
        }

    @property
    def api_client(self) -> WeatherAPIClient:
        """Expose api_client for testing."""
        return self._api_client

    @property
    def cache(self) -> WeatherCache:
        """Expose cache for testing."""
        return self._cache

    @property
    def handlers(self) -> WeatherHandlers:
        """Expose handlers for direct testing."""
        return self._handlers

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route a JSON-RPC message to the correct handler.

        Supports:
          - initialize: Return server capabilities
          - tools/list: Return tool definitions
          - tools/call: Execute a tool
          - ping: Health check

        Args:
            message: Parsed JSON-RPC message.

        Returns:
            JSON-RPC response dict.
        """
        method = message.get("method", "")
        msg_id = message.get("id")

        if method == "initialize":
            return _response(
                msg_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "weather-mcp-sse", "version": "1.0.0"},
                },
            )

        if method == "tools/list":
            return _response(msg_id, {"tools": TOOLS})

        if method == "tools/call":
            return await self._handle_tool_call(message, msg_id)

        if method == "ping":
            return _response(msg_id, {})

        return _error(msg_id, -32601, f"Method not found: {method}")

    async def _handle_tool_call(
        self,
        message: Dict[str, Any],
        msg_id: Any,
    ) -> Dict[str, Any]:
        """Handle a tools/call message."""
        params = message.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = self._tool_map.get(tool_name)
        if handler is None:
            return _error(msg_id, -32601, f"Unknown tool: {tool_name}")

        try:
            result = await handler(arguments)
            return _response(
                msg_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                },
            )
        except ValueError as exc:
            return _error(msg_id, -32602, f"Invalid params: {exc}")
        except Exception as exc:
            logger.exception("Tool execution error: %s", exc)
            return _error(msg_id, -32000, f"Internal error: {exc}")

    def close(self) -> None:
        """Clean up resources."""
        self._cache.clear()


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _response(msg_id: Any, result: Any) -> Dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> Dict[str, Any]:
    """Build a JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }
