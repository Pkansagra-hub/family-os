"""MCPStdioTransport — fastmcp Client + StdioTransport adapter (MS-5 PR#2).

This module isolates fastmcp's API surface so the rest of the connector
tier sees a stable, narrowly-scoped Protocol-style class. If we ever
need to drop fastmcp (or pin a different version) only this file
changes.

Shape we expose to the rest of the connector:

* ``async open(env)`` — connect, run mcp/initialize, return cached
  ``tools/list``.
* ``async invoke(tool, args, *, timeout_s)`` — single
  ``tools/call`` round trip.
* ``async ping(*, timeout_s)`` — health probe; returns latency_ms.
* ``async close()`` — graceful shutdown (SIGTERM-equivalent).
* ``is_connected`` — boolean snapshot.

The fastmcp ``Client`` uses ``async with`` for its lifecycle; we wrap
that by managing the context via ``__aenter__`` / ``__aexit__``
explicitly so callers can keep the connection open across multiple
``invoke`` calls without nesting ``async with`` blocks.
"""

from __future__ import annotations

import time
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from .._tool_descriptor_helpers import tool_descriptors_from_fastmcp


class MCPStdioTransport:
    """Owns one fastmcp ``Client`` + child stdio process pair.

    Parameters:
        command: Executable to spawn (e.g. ``python``).
        args: CLI args (e.g. ``["-m", "bridge.ifl.adapters.google_calendar.server"]``).
        cwd: Optional working directory for the child.
        init_timeout_s: How long to wait for ``mcp/initialize`` to
            complete before giving up.
    """

    def __init__(
        self,
        *,
        command: str,
        args: list[str],
        cwd: str | None = None,
        init_timeout_s: float = 10.0,
    ) -> None:
        self._command = command
        self._args = list(args)
        self._cwd = cwd
        self._init_timeout_s = init_timeout_s
        self._client: Client | None = None
        self._tools_cache: list[dict[str, Any]] | None = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    async def open(self, *, env: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """Spawn the child, run mcp/initialize, return cached tools/list.

        Returns:
            Plain-dict tool descriptors (``name``, ``description``,
            ``input_schema``). Stable shape regardless of fastmcp
            internal types.
        """
        if self._client is not None:
            raise RuntimeError("MCPStdioTransport.open() called twice")
        transport = StdioTransport(
            command=self._command,
            args=self._args,
            env=env,
            cwd=self._cwd,
            keep_alive=True,
        )
        client = Client(
            transport=transport,
            init_timeout=self._init_timeout_s,
            timeout=self._init_timeout_s,
        )
        # Enter context so the underlying subprocess and JSON-RPC
        # session are both live for the duration of this transport.
        await client.__aenter__()
        self._client = client
        # Cache tools/list so subsequent invoke calls don't re-roundtrip.
        tools = await client.list_tools()
        self._tools_cache = tool_descriptors_from_fastmcp(tools)
        return list(self._tools_cache)

    async def invoke(
        self,
        *,
        tool: str,
        args: dict[str, Any],
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        """Call a tool and return its structured content.

        The fastmcp ``call_tool`` returns a typed result with a
        ``data`` / ``content`` payload; we normalise to a plain dict
        so the rest of the connector tier doesn't depend on fastmcp
        types.
        """
        if self._client is None:
            raise RuntimeError("MCPStdioTransport.invoke() before open()")
        result = await self._client.call_tool(
            tool,
            args,
            timeout=timeout_s,
        )
        # fastmcp returns CallToolResult; .data is the structured
        # JSON dict if the server set output_schema, else .content
        # holds a list of content blocks. Prefer .data; fall back to
        # serialising .content blocks to a {"content": [...]} envelope.
        data = getattr(result, "data", None)
        if data is not None:
            return _ensure_dict(data)
        content = getattr(result, "content", None)
        if content is not None:
            return {"content": _serialise_content(content)}
        return {}

    async def ping(self, *, timeout_s: float = 2.0) -> float:
        """Health probe; returns measured round-trip in milliseconds.

        Raises:
            RuntimeError: transport not open.
            Exception: any error from the child JSON-RPC ping.
        """
        if self._client is None:
            raise RuntimeError("MCPStdioTransport.ping() before open()")
        t0 = time.monotonic()
        await self._client.ping()
        return (time.monotonic() - t0) * 1000.0

    def cached_tools(self) -> list[dict[str, Any]]:
        """Return the tool descriptor list captured at :meth:`open` time."""
        return list(self._tools_cache or ())

    async def close(self) -> None:
        """Gracefully terminate the underlying client + child process."""
        if self._client is None:
            return
        try:
            await self._client.__aexit__(None, None, None)
        finally:
            self._client = None


def _ensure_dict(obj: Any) -> dict[str, Any]:
    """Coerce a fastmcp data payload into a plain dict.

    fastmcp returns either a dict (when the tool declared an
    output_schema) or a Pydantic model. We accept both and fall
    through to ``model_dump`` for the latter.
    """
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump()
    # Last resort: stringify under a stable key so callers don't crash.
    return {"value": obj}


def _serialise_content(content: Any) -> list[dict[str, Any]]:
    """Convert a list of fastmcp content blocks to plain dicts."""
    out: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict):
            out.append(block)
            continue
        dump = getattr(block, "model_dump", None)
        if callable(dump):
            out.append(dump())
            continue
        out.append({"raw": str(block)})
    return out


__all__ = ["MCPStdioTransport"]
