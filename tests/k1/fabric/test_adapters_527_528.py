"""
Tests for Fabric adapter issues 5.2.7 and 5.2.8.

5.2.7 -- TestDeltaBusAdapter (in-memory delta capture)
5.2.8 -- BridgeConnectionAdapter (production Bridge connection)

Coverage:
  - Protocol satisfaction (structural subtyping)
  - Core operations (emit, drain, reconnect, offline fallback)
  - Setup helpers (filters, assertions, config)
  - Edge cases (no client, disconnection, error handling)
  - Thread safety (concurrent operations)
  - Package exports via adapters __init__
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from k1.fabric.adapters.bridge_connection import BridgeConnectionAdapter as BridgeConnPkg
from k1.fabric.adapters.bridge_connection import BridgeConnectionConfig

# -- Adapters under test ---------------------------------------------------
from k1.fabric.adapters.test_delta_bus import CapturedDelta
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter as DeltaBusPkg

# -- Port protocols --------------------------------------------------------
from k1.fabric.ports.bridge_port import IFabricK0Port, IFLRoute
from k1.fabric.ports.delta_bus import IDeltaBusPort

# ===========================================================================
# 5.2.7 -- TestDeltaBusAdapter
# ===========================================================================


class TestDeltaBusProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self) -> None:
        adapter = DeltaBusPkg()
        assert isinstance(adapter, IDeltaBusPort)

    def test_has_emit_delta(self) -> None:
        assert hasattr(DeltaBusPkg, "emit_delta")

    def test_runtime_checkable(self) -> None:
        assert isinstance(DeltaBusPkg(), IDeltaBusPort)


class TestDeltaBusEmit:
    """emit_delta tests."""

    def test_emit_stores_delta(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("agent-1", "plan_update", "plan", {"step": 1})
        assert adapter.delta_count == 1

    def test_emit_multiple(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "plan_update", "plan", {"s": 1})
        adapter.emit_delta("a2", "context_change", "context", {"k": "v"})
        adapter.emit_delta("a1", "tool_result", "tools", {"r": True})
        assert adapter.delta_count == 3

    def test_emit_captures_all_fields(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("agent-x", "status_change", "status", {"state": "ACTIVE"})
        deltas = adapter.get_deltas()
        assert len(deltas) == 1
        d = deltas[0]
        assert d.agent_id == "agent-x"
        assert d.delta_type == "status_change"
        assert d.section == "status"
        assert d.data == {"state": "ACTIVE"}
        assert d.timestamp_ms > 0

    def test_emit_copies_data(self) -> None:
        adapter = DeltaBusPkg()
        data = {"key": "val"}
        adapter.emit_delta("a", "t", "s", data)
        data["key"] = "modified"
        assert adapter.get_deltas()[0].data == {"key": "val"}

    def test_captured_delta_to_dict(self) -> None:
        d = CapturedDelta(
            agent_id="a1",
            delta_type="plan_update",
            section="plan",
            data={"s": 1},
            timestamp_ms=1000,
        )
        result = d.to_dict()
        assert result["agent_id"] == "a1"
        assert result["section"] == "plan"
        assert result["timestamp_ms"] == 1000


class TestDeltaBusQuery:
    """get_deltas filter tests."""

    def _load_adapter(self) -> DeltaBusPkg:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "plan_update", "plan", {"s": 1})
        adapter.emit_delta("a2", "context_change", "context", {"k": "v"})
        adapter.emit_delta("a1", "tool_result", "tools", {"r": True})
        adapter.emit_delta("a2", "plan_update", "plan", {"s": 2})
        return adapter

    def test_get_all(self) -> None:
        adapter = self._load_adapter()
        assert len(adapter.get_deltas()) == 4

    def test_filter_by_agent_id(self) -> None:
        adapter = self._load_adapter()
        result = adapter.get_deltas(agent_id="a1")
        assert len(result) == 2
        assert all(d.agent_id == "a1" for d in result)

    def test_filter_by_delta_type(self) -> None:
        adapter = self._load_adapter()
        result = adapter.get_deltas(delta_type="plan_update")
        assert len(result) == 2
        assert all(d.delta_type == "plan_update" for d in result)

    def test_filter_by_section(self) -> None:
        adapter = self._load_adapter()
        result = adapter.get_deltas(section="context")
        assert len(result) == 1

    def test_filter_combined(self) -> None:
        adapter = self._load_adapter()
        result = adapter.get_deltas(agent_id="a1", delta_type="plan_update")
        assert len(result) == 1

    def test_filter_no_match(self) -> None:
        adapter = self._load_adapter()
        result = adapter.get_deltas(agent_id="nonexistent")
        assert len(result) == 0

    def test_agent_ids(self) -> None:
        adapter = self._load_adapter()
        assert adapter.agent_ids == {"a1", "a2"}


class TestDeltaBusDrain:
    """drain and clear tests."""

    def test_drain_returns_all(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "s", {})
        adapter.emit_delta("a2", "t", "s", {})
        drained = adapter.drain()
        assert len(drained) == 2
        assert adapter.delta_count == 0

    def test_drain_empty(self) -> None:
        adapter = DeltaBusPkg()
        assert adapter.drain() == []

    def test_clear(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "s", {})
        adapter.clear()
        assert adapter.delta_count == 0


class TestDeltaBusAssertions:
    """assert_emitted tests."""

    def test_assert_emitted_pass(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "plan_update", "plan", {})
        adapter.assert_emitted(agent_id="a1")  # no error

    def test_assert_emitted_fail(self) -> None:
        adapter = DeltaBusPkg()
        with pytest.raises(AssertionError, match="at least 1"):
            adapter.assert_emitted(agent_id="no-agent")

    def test_assert_emitted_count_pass(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "s", {})
        adapter.emit_delta("a1", "t", "s", {})
        adapter.assert_emitted(agent_id="a1", count=2)

    def test_assert_emitted_count_fail(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "s", {})
        with pytest.raises(AssertionError, match="Expected 3"):
            adapter.assert_emitted(agent_id="a1", count=3)

    def test_assert_emitted_zero_count(self) -> None:
        adapter = DeltaBusPkg()
        adapter.assert_emitted(agent_id="a1", count=0)

    def test_assert_emitted_by_delta_type(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "plan_update", "plan", {})
        adapter.assert_emitted(delta_type="plan_update")

    def test_assert_emitted_by_section(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "tools", {})
        adapter.assert_emitted(section="tools")

    def test_assert_emitted_combined(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "plan_update", "plan", {})
        adapter.emit_delta("a2", "plan_update", "plan", {})
        adapter.assert_emitted(agent_id="a1", delta_type="plan_update", count=1)

    def test_assert_emitted_all_no_filter(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "s", {})
        adapter.assert_emitted()  # any delta emitted


class TestDeltaBusRepr:
    """repr and misc."""

    def test_repr(self) -> None:
        adapter = DeltaBusPkg()
        r = repr(adapter)
        assert "TestDeltaBusAdapter" in r
        assert "deltas=0" in r

    def test_repr_with_data(self) -> None:
        adapter = DeltaBusPkg()
        adapter.emit_delta("a1", "t", "s", {})
        r = repr(adapter)
        assert "deltas=1" in r
        assert "agents=1" in r


class TestDeltaBusConcurrency:
    """Thread safety."""

    def test_concurrent_emit(self) -> None:
        adapter = DeltaBusPkg()
        errors: List[Exception] = []

        def worker(i: int) -> None:
            try:
                adapter.emit_delta(f"agent-{i}", "t", "s", {"i": i})
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(50)))

        assert not errors
        assert adapter.delta_count == 50

    def test_concurrent_emit_and_drain(self) -> None:
        adapter = DeltaBusPkg()
        total_emitted = 0
        total_drained = 0
        lock = threading.Lock()

        def emitter() -> None:
            nonlocal total_emitted
            for _ in range(20):
                adapter.emit_delta("a", "t", "s", {})
                with lock:
                    total_emitted += 1

        def drainer() -> None:
            nonlocal total_drained
            for _ in range(10):
                batch = adapter.drain()
                with lock:
                    total_drained += len(batch)

        threads = [threading.Thread(target=emitter) for _ in range(3)]
        threads += [threading.Thread(target=drainer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Remaining + drained should equal total emitted
        remaining = adapter.delta_count
        assert total_drained + remaining == total_emitted


# ===========================================================================
# 5.2.8 -- BridgeConnectionAdapter
# ===========================================================================


class FakeBridgeClient:
    """Fake bridge client for testing the production adapter."""

    def __init__(
        self,
        *,
        connected: bool = True,
        health: Optional[Dict[str, Any]] = None,
        fail_on: Optional[str] = None,
    ) -> None:
        self._connected = connected
        self._health = health or {"mode": "K0_FULL", "latency_ms": 5}
        self._fail_on = fail_on
        self.send_calls: List[tuple] = []
        self.query_calls: List[tuple] = []
        self.ifl_calls: List[tuple] = []

    def is_connected(self) -> bool:
        return self._connected

    def get_health(self) -> Dict[str, Any]:
        return self._health

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def send(
        self,
        operation: str,
        payload: Dict[str, Any],
        trace_id: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        if self._fail_on == "send":
            raise ConnectionError("send failed")
        self.send_calls.append((operation, payload, trace_id))
        return {"ok": True, "operation": operation}

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        trace_id: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        if self._fail_on == "query":
            raise ConnectionError("query failed")
        self.query_calls.append((operation, selectors, trace_id))
        return {"results": [], "operation": operation}

    async def route_ifl(
        self,
        address: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        if self._fail_on == "route_ifl":
            raise ConnectionError("route_ifl failed")
        self.ifl_calls.append((address, payload, trace_id))
        return {"executed": True, "address": address}


class TestBridgeConnProtocol:
    """Protocol satisfaction."""

    def test_satisfies_protocol(self) -> None:
        adapter = BridgeConnPkg()
        assert isinstance(adapter, IFabricK0Port)

    def test_has_send_command(self) -> None:
        assert hasattr(BridgeConnPkg, "send_command")

    def test_has_query(self) -> None:
        assert hasattr(BridgeConnPkg, "query")

    def test_has_route_ifl(self) -> None:
        assert hasattr(BridgeConnPkg, "route_ifl")

    def test_has_is_available(self) -> None:
        assert hasattr(BridgeConnPkg, "is_available")

    def test_has_get_health(self) -> None:
        assert hasattr(BridgeConnPkg, "get_health")

    def test_runtime_checkable(self) -> None:
        assert isinstance(BridgeConnPkg(), IFabricK0Port)


class TestBridgeConnNoClient:
    """Behavior when no client is provided (LOCAL COLD mode)."""

    def test_not_available_by_default(self) -> None:
        adapter = BridgeConnPkg()
        assert adapter.is_available() is False

    def test_health_offline_by_default(self) -> None:
        adapter = BridgeConnPkg()
        h = adapter.get_health()
        assert h.available is False
        assert h.mode == "K0_OFFLINE"

    @pytest.mark.asyncio
    async def test_send_command_returns_offline(self) -> None:
        adapter = BridgeConnPkg()
        result = await adapter.send_command("memory.store", {"k": "v"})
        assert result.success is False
        assert result.error_code == "k0_offline"

    @pytest.mark.asyncio
    async def test_query_returns_offline(self) -> None:
        adapter = BridgeConnPkg()
        result = await adapter.query("memory.recall", {})
        assert result.success is False
        assert result.error_code == "k0_offline"

    @pytest.mark.asyncio
    async def test_route_ifl_returns_offline(self) -> None:
        adapter = BridgeConnPkg()
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await adapter.route_ifl(route, {})
        assert result.success is False
        assert result.error_code == "k0_offline"

    @pytest.mark.asyncio
    async def test_reconnect_without_client_returns_false(self) -> None:
        adapter = BridgeConnPkg()
        assert await adapter.reconnect() is False

    def test_config_defaults(self) -> None:
        adapter = BridgeConnPkg()
        assert adapter.config.endpoint == "http://localhost:8090"
        assert adapter.config.default_timeout_ms == 5000

    def test_custom_config(self) -> None:
        cfg = BridgeConnectionConfig(
            endpoint="http://bridge:9090",
            default_timeout_ms=10000,
        )
        adapter = BridgeConnPkg(config=cfg)
        assert adapter.config.endpoint == "http://bridge:9090"


class TestBridgeConnWithClient:
    """Behavior with a connected client."""

    def test_available_when_client_connected(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        assert adapter.is_available() is True

    def test_not_available_when_client_disconnected(self) -> None:
        client = FakeBridgeClient(connected=False)
        adapter = BridgeConnPkg(client=client)
        assert adapter.is_available() is False

    def test_health_full_when_connected(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        h = adapter.get_health()
        assert h.available is True
        assert h.mode == "K0_FULL"

    @pytest.mark.asyncio
    async def test_send_command_routes_through_client(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        result = await adapter.send_command("memory.store", {"key": "val"}, trace_id="t-1")
        assert result.success is True
        assert result.data["operation"] == "memory.store"
        assert len(client.send_calls) == 1

    @pytest.mark.asyncio
    async def test_query_routes_through_client(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        result = await adapter.query("memory.recall", {"filter": "recent"})
        assert result.success is True
        assert result.data["operation"] == "memory.recall"
        assert len(client.query_calls) == 1

    @pytest.mark.asyncio
    async def test_route_ifl_routes_through_client(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await adapter.route_ifl(route, {"action": "on"}, trace_id="t-2")
        assert result.success is True
        assert result.data["address"] == "tool.execute.home.lights"
        assert len(client.ifl_calls) == 1

    @pytest.mark.asyncio
    async def test_trace_id_passed_to_send(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        result = await adapter.send_command("op", {}, trace_id="trace-123")
        assert result.trace_id == "trace-123"
        assert client.send_calls[0][2] == "trace-123"


class TestBridgeConnErrorHandling:
    """Error handling and disconnection."""

    @pytest.mark.asyncio
    async def test_send_error_marks_disconnected(self) -> None:
        client = FakeBridgeClient(connected=True, fail_on="send")
        adapter = BridgeConnPkg(client=client)
        assert adapter.is_available() is True
        result = await adapter.send_command("op", {})
        assert result.success is False
        assert result.error_code == "bridge_error"
        assert adapter.is_available() is False

    @pytest.mark.asyncio
    async def test_query_error_marks_disconnected(self) -> None:
        client = FakeBridgeClient(connected=True, fail_on="query")
        adapter = BridgeConnPkg(client=client)
        result = await adapter.query("op", {})
        assert result.success is False
        assert adapter.is_available() is False

    @pytest.mark.asyncio
    async def test_route_ifl_error_marks_disconnected(self) -> None:
        client = FakeBridgeClient(connected=True, fail_on="route_ifl")
        adapter = BridgeConnPkg(client=client)
        route = IFLRoute.parse("tool.execute.home.x")
        result = await adapter.route_ifl(route, {})
        assert result.success is False
        assert adapter.is_available() is False

    @pytest.mark.asyncio
    async def test_operations_after_disconnect_return_offline(self) -> None:
        client = FakeBridgeClient(connected=True, fail_on="send")
        adapter = BridgeConnPkg(client=client)
        # First call fails and disconnects
        await adapter.send_command("op", {})
        # Subsequent calls are offline
        result = await adapter.send_command("op2", {})
        assert result.error_code == "k0_offline"


class TestBridgeConnReconnect:
    """Reconnect behavior."""

    @pytest.mark.asyncio
    async def test_reconnect_succeeds(self) -> None:
        client = FakeBridgeClient(connected=False)
        adapter = BridgeConnPkg(client=client)
        assert adapter.is_available() is False
        result = await adapter.reconnect()
        assert result is True
        assert adapter.is_available() is True

    @pytest.mark.asyncio
    async def test_reconnect_throttled(self) -> None:
        cfg = BridgeConnectionConfig(reconnect_interval_ms=60000)
        client = FakeBridgeClient(connected=False)
        adapter = BridgeConnPkg(config=cfg, client=client)
        # First reconnect: succeeds
        await adapter.reconnect()
        assert adapter.is_available() is True
        # Simulate disconnect
        adapter._mark_disconnected("test")
        # Second reconnect is throttled (within interval)
        result = await adapter.reconnect()
        assert result is False  # Still disconnected, throttled

    @pytest.mark.asyncio
    async def test_reconnect_max_attempts(self) -> None:
        cfg = BridgeConnectionConfig(
            max_reconnect_attempts=1,
            reconnect_interval_ms=0,
        )
        client = MagicMock()
        client.is_connected = MagicMock(return_value=False)
        client.connect = AsyncMock(return_value=False)
        adapter = BridgeConnPkg(config=cfg, client=client)
        # First attempt (attempt #1)
        await adapter.reconnect()
        # Second attempt exceeds max
        result = await adapter.reconnect()
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        assert adapter.is_available() is True
        await adapter.disconnect()
        assert adapter.is_available() is False
        assert adapter.get_health().mode == "K0_OFFLINE"


class TestBridgeConnHealthProbe:
    """Health probing from client."""

    def test_health_from_client(self) -> None:
        client = FakeBridgeClient(
            connected=True,
            health={"mode": "K0_DEGRADED", "latency_ms": 42},
        )
        adapter = BridgeConnPkg(client=client)
        h = adapter.get_health()
        assert h.mode == "K0_DEGRADED"
        assert h.latency_ms == 42

    def test_health_default_when_no_health_method(self) -> None:
        # Minimal client without get_health
        class MinimalClient:
            def is_connected(self) -> bool:
                return True

        adapter = BridgeConnPkg(client=MinimalClient())
        h = adapter.get_health()
        assert h.available is True
        assert h.mode == "K0_FULL"  # default when no health info


class TestBridgeConnRepr:
    """repr and misc."""

    def test_repr_no_client(self) -> None:
        adapter = BridgeConnPkg()
        r = repr(adapter)
        assert "BridgeConnectionAdapter" in r
        assert "connected=False" in r

    def test_repr_with_client(self) -> None:
        client = FakeBridgeClient(connected=True)
        adapter = BridgeConnPkg(client=client)
        r = repr(adapter)
        assert "connected=True" in r
        assert "K0_FULL" in r

    def test_config_frozen(self) -> None:
        cfg = BridgeConnectionConfig()
        with pytest.raises(Exception):
            cfg.endpoint = "http://new"  # type: ignore[misc]


# ===========================================================================
# Package exports
# ===========================================================================


class TestAdaptersExports527_528:
    """Verify adapters package exports include 5.2.7-5.2.8."""

    def test_all_count(self) -> None:
        import k1.fabric.adapters as pkg

        assert len(pkg.__all__) >= 12

    def test_delta_bus_in_all(self) -> None:
        import k1.fabric.adapters as pkg

        assert "TestDeltaBusAdapter" in pkg.__all__
        assert "CapturedDelta" in pkg.__all__

    def test_bridge_conn_in_all(self) -> None:
        import k1.fabric.adapters as pkg

        assert "BridgeConnectionAdapter" in pkg.__all__
        assert "BridgeConnectionConfig" in pkg.__all__

    def test_all_importable(self) -> None:
        import k1.fabric.adapters as pkg

        for name in pkg.__all__:
            obj = getattr(pkg, name)
            assert obj is not None, f"{name} resolved to None"

    def test_direct_import_delta_bus(self) -> None:
        from k1.fabric.adapters import TestDeltaBusAdapter

        assert TestDeltaBusAdapter is DeltaBusPkg

    def test_direct_import_bridge_conn(self) -> None:
        from k1.fabric.adapters import BridgeConnectionAdapter

        assert BridgeConnectionAdapter is BridgeConnPkg

    def test_direct_import_config(self) -> None:
        from k1.fabric.adapters import BridgeConnectionConfig as Cfg

        assert Cfg is BridgeConnectionConfig

    def test_prior_exports_still_present(self) -> None:
        """Ensure 5.2.1-5.2.6 exports not broken."""
        import k1.fabric.adapters as pkg

        for name in [
            "SessionStateReaderAdapter",
            "TestSessionStateReaderAdapter",
            "LocalEventAdapter",
            "TestBridgeAdapter",
            "CapturedBridgeCall",
            "TestModelGatewayAdapter",
            "TestLLMHandle",
            "TestPromptSystemAdapter",
        ]:
            assert name in pkg.__all__, f"{name} missing from __all__"
