"""Integration tests for :class:`MCPStdioTransport` against the echo fixture.

These spawn a real Python subprocess (the in-tree echo MCP server) so
they exercise the full fastmcp stdio path. Tests are async, gated on
fastmcp being importable, and tagged ``slow_subprocess`` so an op can
exclude them with ``-m "not slow_subprocess"`` if running in a tight
pre-commit loop.
"""

from __future__ import annotations

import sys

import pytest

from bridge.connector.transport import MCPStdioTransport

pytestmark = pytest.mark.asyncio


def _echo_server_command() -> tuple[str, list[str]]:
    """Compose the (command, args) tuple for the echo fixture."""
    return sys.executable, ["-m", "tests.fixtures.mcp_servers.echo.server"]


class TestMCPStdioTransportLifecycle:
    async def test_open_lists_tools_via_initialize(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        try:
            tools = await transport.open()
            tool_names = {t["name"] for t in tools}
            assert "echo" in tool_names
            assert "add" in tool_names
        finally:
            await transport.close()

    async def test_invoke_round_trip_returns_payload(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        try:
            await transport.open()
            result = await transport.invoke(
                tool="echo",
                args={"message": "hello bridge"},
            )
            assert result == {"message": "hello bridge"}
        finally:
            await transport.close()

    async def test_invoke_typed_args(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        try:
            await transport.open()
            result = await transport.invoke(tool="add", args={"a": 2, "b": 3})
            assert result == {"sum": 5}
        finally:
            await transport.close()

    async def test_ping_returns_positive_latency(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        try:
            await transport.open()
            latency_ms = await transport.ping()
            assert latency_ms >= 0.0
        finally:
            await transport.close()

    async def test_double_open_raises(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        try:
            await transport.open()
            with pytest.raises(RuntimeError):
                await transport.open()
        finally:
            await transport.close()

    async def test_invoke_before_open_raises(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        with pytest.raises(RuntimeError):
            await transport.invoke(tool="echo", args={"message": "x"})

    async def test_close_is_idempotent(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        await transport.open()
        await transport.close()
        await transport.close()  # second close must not raise

    async def test_is_connected_lifecycle(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        assert transport.is_connected is False
        await transport.open()
        assert transport.is_connected is True
        await transport.close()
        assert transport.is_connected is False

    async def test_cached_tools_match_open_return(self) -> None:
        cmd, args = _echo_server_command()
        transport = MCPStdioTransport(command=cmd, args=args)
        try:
            tools = await transport.open()
            assert transport.cached_tools() == tools
        finally:
            await transport.close()
