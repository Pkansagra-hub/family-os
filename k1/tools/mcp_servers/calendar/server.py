"""
k1.tools.mcp_servers.calendar.server -- Calendar MCP Server (stdio).

MCP server entry point for family calendar management.
Communicates via stdio JSON-RPC (line-delimited JSON on stdin/stdout).

Implements the MCP protocol subset needed for tool execution:
  - initialize: Server capabilities and info
  - tools/list: Advertise available tools
  - tools/call: Execute a tool by name
  - ping: Health check

MCP Protocol Reference:
  - JSON-RPC 2.0 over stdio
  - tools/call params: {"name": str, "arguments": dict}
  - tools/call result: {"content": [{"type": "text", "text": str}]}

Usage:
  python -m k1.tools.mcp_servers.calendar.server

References:
  - fabric_tool_implementation_plan.md Phase 1, Section 3.1.2
  - fabric_developer_guide.md Section 4
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Coroutine, Dict, List, Optional

from k1.tools.mcp_servers.calendar.handlers import CalendarHandlers
from k1.tools.mcp_servers.calendar.storage import CalendarStorage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (advertised via tools/list)
# ---------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "tool.read.calendar_list_events",
        "description": "List family calendar events within a date range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Range start date (ISO 8601)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Range end date (ISO 8601)",
                },
                "max_results": {
                    "type": "number",
                    "description": "Max events to return (default 50)",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "tool.write.calendar_create_event",
        "description": "Create a new family calendar event",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "start_time": {
                    "type": "string",
                    "description": "Start datetime (ISO 8601)",
                },
                "end_time": {
                    "type": "string",
                    "description": "End datetime (ISO 8601)",
                },
                "location": {"type": "string", "description": "Event location"},
                "description": {"type": "string", "description": "Event notes"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Attendee names",
                },
            },
            "required": ["title", "start_time", "end_time"],
        },
    },
    {
        "name": "tool.write.calendar_delete_event",
        "description": "Delete a calendar event by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Event identifier to delete",
                },
            },
            "required": ["event_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# CalendarMCPServer
# ---------------------------------------------------------------------------


class CalendarMCPServer:
    """
    MCP server for family calendar (stdio transport).

    Routes JSON-RPC messages to the appropriate handler.
    Stateless per-request; all state lives in CalendarStorage.

    Args:
        db_path: SQLite database path. Use ":memory:" for testing.
    """

    __slots__ = ("_storage", "_handlers", "_tool_map")

    def __init__(self, db_path: str = ":memory:") -> None:
        self._storage = CalendarStorage(db_path=db_path)
        self._handlers = CalendarHandlers(self._storage)
        self._tool_map: Dict[
            str, Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]
        ] = {
            "tool.read.calendar_list_events": self._handlers.list_events,
            "tool.write.calendar_create_event": self._handlers.create_event,
            "tool.write.calendar_delete_event": self._handlers.delete_event,
        }

    @property
    def storage(self) -> CalendarStorage:
        """Expose storage for testing access."""
        return self._storage

    @property
    def handlers(self) -> CalendarHandlers:
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
                    "serverInfo": {"name": "calendar-mcp", "version": "1.0.0"},
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
        self._storage.close()


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


# ---------------------------------------------------------------------------
# stdio main loop
# ---------------------------------------------------------------------------


async def _stdio_loop(server: CalendarMCPServer) -> None:
    """
    Read JSON-RPC messages from stdin, dispatch, write responses to stdout.

    Line-delimited JSON protocol: one JSON object per line.
    """
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            message = json.loads(line.decode("utf-8"))
            response = await server.handle_message(message)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received: %s", line)
            err = _error(None, -32700, "Parse error: invalid JSON")
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


def main(db_path: Optional[str] = None) -> None:
    """Entry point for the calendar MCP server."""
    effective_path = db_path or ":memory:"
    server = CalendarMCPServer(db_path=effective_path)
    try:
        asyncio.run(_stdio_loop(server))
    finally:
        server.close()


if __name__ == "__main__":
    main()
