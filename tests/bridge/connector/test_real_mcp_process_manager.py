"""Integration tests for :class:`RealMCPProcessManager`.

These exercise the full path through the manager → transport → echo
MCP fixture subprocess. Each test starts and stops its own children so
they can run in parallel.
"""

from __future__ import annotations

import sys

import pytest

from bridge.connector import RealMCPProcessManager
from bridge.connector.contracts import (
    AdapterQuarantinedError,
    OfflineAdapterError,
    UnknownAdapterError,
)

pytestmark = pytest.mark.asyncio


def _echo_manifest(adapter_id: str = "echo_test") -> dict:
    return {
        "adapter_id": adapter_id,
        "mcp": {
            "server_command": [
                sys.executable,
                "-m",
                "tests.fixtures.mcp_servers.echo.server",
            ],
        },
    }


class TestRealMCPProcessManagerStart:
    async def test_start_then_invoke_round_trip(self) -> None:
        mgr = RealMCPProcessManager()
        try:
            await mgr.start(adapter_id="echo", manifest=_echo_manifest())
            result = await mgr.invoke(
                adapter_id="echo",
                tool="echo",
                args={"message": "hi"},
            )
            assert result == {"message": "hi"}
        finally:
            await mgr.stop(adapter_id="echo")

    async def test_start_is_idempotent(self) -> None:
        mgr = RealMCPProcessManager()
        try:
            await mgr.start(adapter_id="echo", manifest=_echo_manifest())
            await mgr.start(adapter_id="echo", manifest=_echo_manifest())
            health = await mgr.health(adapter_id="echo")
            assert health.state == "ready"
        finally:
            await mgr.stop(adapter_id="echo")

    async def test_health_unknown_for_never_started(self) -> None:
        mgr = RealMCPProcessManager()
        health = await mgr.health(adapter_id="never_started")
        assert health.state == "unknown"

    async def test_invoke_before_start_raises_unknown(self) -> None:
        mgr = RealMCPProcessManager()
        with pytest.raises(UnknownAdapterError):
            await mgr.invoke(
                adapter_id="never",
                tool="echo",
                args={"message": "x"},
            )

    async def test_list_tools_returns_descriptors(self) -> None:
        mgr = RealMCPProcessManager()
        try:
            await mgr.start(adapter_id="echo", manifest=_echo_manifest())
            tools = await mgr.list_tools(adapter_id="echo")
            names = {t.name for t in tools}
            assert "echo" in names
            assert "add" in names
        finally:
            await mgr.stop(adapter_id="echo")


class TestRealMCPProcessManagerHealth:
    async def test_ping_succeeds_and_updates_health(self) -> None:
        mgr = RealMCPProcessManager()
        try:
            await mgr.start(adapter_id="echo", manifest=_echo_manifest())
            latency_ms = await mgr.ping(adapter_id="echo")
            assert latency_ms >= 0.0
            health = await mgr.health(adapter_id="echo")
            assert health.state == "ready"
            assert health.last_ping_ms > 0
        finally:
            await mgr.stop(adapter_id="echo")


class TestRealMCPProcessManagerStop:
    async def test_stop_clears_state(self) -> None:
        mgr = RealMCPProcessManager()
        await mgr.start(adapter_id="echo", manifest=_echo_manifest())
        await mgr.stop(adapter_id="echo")
        health = await mgr.health(adapter_id="echo")
        assert health.state == "stopped"
        with pytest.raises(OfflineAdapterError):
            await mgr.invoke(
                adapter_id="echo",
                tool="echo",
                args={"message": "x"},
            )

    async def test_stop_unknown_adapter_is_noop(self) -> None:
        mgr = RealMCPProcessManager()
        # Idempotent: stop on a never-started adapter must not raise.
        await mgr.stop(adapter_id="never_started")


class TestRealMCPProcessManagerErrors:
    async def test_missing_server_command_raises(self) -> None:
        mgr = RealMCPProcessManager()
        bad = {"adapter_id": "broken", "mcp": {}}
        with pytest.raises(ValueError):
            await mgr.start(adapter_id="broken", manifest=bad)

    async def test_init_failure_quarantines_after_budget(self) -> None:
        # Use a command that will exit immediately so init can never
        # complete. Three crashes should quarantine the adapter.
        mgr = RealMCPProcessManager(
            init_timeout_s=1.0,
            crash_budget_count=2,
            crash_budget_window_s=300.0,
        )
        bad = {
            "adapter_id": "crasher",
            "mcp": {
                "server_command": [sys.executable, "-c", "import sys; sys.exit(1)"],
            },
        }
        # First failure: marks unhealthy.
        with pytest.raises(OfflineAdapterError):
            await mgr.start(adapter_id="crasher", manifest=bad)
        h1 = await mgr.health(adapter_id="crasher")
        assert h1.state in ("unhealthy", "quarantined")
        # Second failure: budget at threshold (count=2) → quarantined.
        with pytest.raises((OfflineAdapterError, AdapterQuarantinedError)):
            await mgr.start(adapter_id="crasher", manifest=bad)
        h2 = await mgr.health(adapter_id="crasher")
        assert h2.state == "quarantined"
        # Subsequent start attempts must be rejected.
        with pytest.raises(AdapterQuarantinedError):
            await mgr.start(adapter_id="crasher", manifest=bad)
