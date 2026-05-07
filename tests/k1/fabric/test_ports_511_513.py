"""
Tests for Epic 5.1 -- Port Interfaces (5.1.1, 5.1.2, 5.1.3).

Covers:
  5.1.1 ISessionStateReader + SessionSnapshot
  5.1.2 IEventPort + SubscriptionHandle
  5.1.3 IBridgePort + BridgeHealth + BridgeCommandResult + IFLRoute

Test structure:
  TestSessionSnapshot -- Frozen dataclass, section helpers, auto-names
  TestISessionStateReaderProtocol -- Protocol shape, runtime_checkable
  TestISessionStateReaderStructural -- Structural subtyping with fakes
  TestSubscriptionHandle -- Frozen dataclass construction
  TestIEventPortProtocol -- Protocol shape, runtime_checkable
  TestIEventPortStructural -- Structural subtyping with fakes
  TestBridgeHealth -- Frozen dataclass, mode helpers, to_dict
  TestBridgeCommandResult -- ok/fail factories, frozen
  TestIFLRoute -- Parse addresses, validation, frozen
  TestIBridgePortProtocol -- Protocol shape, runtime_checkable
  TestIBridgePortStructural -- Structural subtyping with fakes
  TestPortsExports -- __all__ count and presence
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pytest

from k1.fabric.ports import (
    BridgeCommandResult,
    BridgeHealth,
    IEventPort,
    IFabricK0Port,
    IFLRoute,
    ISessionStateReader,
    SessionSnapshot,
    SubscriptionHandle,
)
from k1.fabric.ports.bridge_port import BridgeCommandResult as BridgeCommandResultDirect
from k1.fabric.ports.bridge_port import BridgeHealth as BridgeHealthDirect
from k1.fabric.ports.bridge_port import IFLRoute as IFLRouteDirect
from k1.fabric.ports.event_port import SubscriptionHandle as SubscriptionHandleDirect
from k1.fabric.ports.state_reader import SessionSnapshot as SessionSnapshotDirect

# ---------------------------------------------------------------------------
# Fakes for structural subtyping verification
# ---------------------------------------------------------------------------


class FakeSessionStateReader:
    """Satisfies ISessionStateReader protocol structurally."""

    def __init__(self) -> None:
        self._sections: Dict[str, Dict[str, Any]] = {}

    def load(self, session_id: str, section: str, data: Dict[str, Any]) -> None:
        """Pre-load a section for testing."""
        key = f"{session_id}:{section}"
        self._sections[key] = data

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        return self._sections.get(f"{session_id}:{section}")

    def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for name in names:
            data = self.read_section(session_id, name)
            if data is not None:
                result[name] = data
        return result

    def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        prefix = f"{session_id}:"
        sections = {k[len(prefix) :]: v for k, v in self._sections.items() if k.startswith(prefix)}
        return SessionSnapshot(
            session_id=session_id,
            sections=sections,
            timestamp_ms=1000,
        )


class FakeEventPort:
    """Satisfies IEventPort protocol structurally."""

    def __init__(self) -> None:
        self._events: List[tuple[str, Dict[str, Any]]] = []
        self._subscriptions: Dict[str, Callable[[str, Dict[str, Any]], None]] = {}
        self._counter: int = 0

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        self._events.append((topic, payload))
        for handler in self._subscriptions.values():
            try:
                handler(topic, payload)
            except Exception:
                pass

    def subscribe(
        self,
        topic: str,
        handler: Callable[[str, Dict[str, Any]], None],
    ) -> SubscriptionHandle:
        self._counter += 1
        sub_id = f"sub-{self._counter}"
        self._subscriptions[sub_id] = handler
        return SubscriptionHandle(subscription_id=sub_id, topic=topic)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        if handle.subscription_id in self._subscriptions:
            del self._subscriptions[handle.subscription_id]
            return True
        return False


class FakeBridgePort:
    """Satisfies IBridgePort protocol structurally."""

    def __init__(
        self,
        available: bool = True,
        mode: str = "K0_FULL",
    ) -> None:
        self._available = available
        self._mode = mode
        self._commands: List[tuple[str, Dict[str, Any]]] = []

    async def send_command(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        self._commands.append((operation, payload))
        if not self._available:
            return BridgeCommandResult.fail("k0_offline", "K0 is offline")
        return BridgeCommandResult.ok({"stored": True}, trace_id=trace_id)

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        if not self._available:
            return BridgeCommandResult.fail("k0_offline", "K0 is offline")
        return BridgeCommandResult.ok({"results": []}, trace_id=trace_id)

    async def route_ifl(
        self,
        route: IFLRoute,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
    ) -> BridgeCommandResult:
        if not self._available:
            return BridgeCommandResult.fail("k0_offline", "K0 is offline")
        return BridgeCommandResult.ok(
            {"route": route.address, "result": "ok"},
            trace_id=trace_id,
        )

    def is_available(self) -> bool:
        return self._available

    def get_health(self) -> BridgeHealth:
        return BridgeHealth(
            available=self._available,
            mode=self._mode,
            last_heartbeat_ms=1000 if self._available else 0,
        )


# =========================================================================
# 5.1.1 -- SessionSnapshot
# =========================================================================


class TestSessionSnapshot:
    """Tests for SessionSnapshot frozen dataclass."""

    def test_default_construction(self) -> None:
        snap = SessionSnapshot()
        assert snap.session_id == ""
        assert snap.sections == {}
        assert snap.timestamp_ms == 0
        assert snap.section_names == []

    def test_construction_with_data(self) -> None:
        snap = SessionSnapshot(
            session_id="s1",
            sections={"affective_now": {"emotion": "happy", "intensity": 0.8}},
            timestamp_ms=1234567890,
        )
        assert snap.session_id == "s1"
        assert snap.sections["affective_now"]["emotion"] == "happy"
        assert snap.timestamp_ms == 1234567890

    def test_auto_section_names(self) -> None:
        snap = SessionSnapshot(
            session_id="s1",
            sections={"cognitive": {}, "affective_now": {}},
        )
        assert snap.section_names == ["affective_now", "cognitive"]

    def test_explicit_section_names_preserved(self) -> None:
        snap = SessionSnapshot(
            session_id="s1",
            sections={"a": {}, "b": {}},
            section_names=["b", "a"],
        )
        assert snap.section_names == ["b", "a"]

    def test_has_section_true(self) -> None:
        snap = SessionSnapshot(sections={"cognitive": {"load": 0.5}})
        assert snap.has_section("cognitive") is True

    def test_has_section_false(self) -> None:
        snap = SessionSnapshot(sections={"cognitive": {"load": 0.5}})
        assert snap.has_section("missing") is False

    def test_get_section_present(self) -> None:
        data = {"emotion": "happy"}
        snap = SessionSnapshot(sections={"affective_now": data})
        assert snap.get_section("affective_now") == data

    def test_get_section_missing(self) -> None:
        snap = SessionSnapshot(sections={})
        assert snap.get_section("missing") is None

    def test_frozen(self) -> None:
        snap = SessionSnapshot(session_id="s1")
        with pytest.raises(AttributeError):
            snap.session_id = "s2"  # type: ignore[misc]

    def test_direct_import_same_class(self) -> None:
        assert SessionSnapshot is SessionSnapshotDirect


# =========================================================================
# 5.1.1 -- ISessionStateReader protocol
# =========================================================================


class TestISessionStateReaderProtocol:
    """Tests for ISessionStateReader protocol shape."""

    def test_is_protocol(self) -> None:
        assert hasattr(ISessionStateReader, "__protocol_attrs__") or hasattr(
            ISessionStateReader, "_is_protocol"
        )

    def test_runtime_checkable(self) -> None:
        """ISessionStateReader is decorated with @runtime_checkable."""
        reader = FakeSessionStateReader()
        assert isinstance(reader, ISessionStateReader)

    def test_has_read_section_method(self) -> None:
        assert callable(getattr(ISessionStateReader, "read_section", None))

    def test_has_read_sections_method(self) -> None:
        assert callable(getattr(ISessionStateReader, "read_sections", None))

    def test_has_get_snapshot_method(self) -> None:
        assert callable(getattr(ISessionStateReader, "get_snapshot", None))

    def test_non_conforming_rejected(self) -> None:
        """An object without the right methods does NOT satisfy the protocol."""

        class NotAReader:
            pass

        assert not isinstance(NotAReader(), ISessionStateReader)


class TestISessionStateReaderStructural:
    """Tests for structural subtyping -- fake reader works end-to-end."""

    def test_read_section_returns_data(self) -> None:
        reader = FakeSessionStateReader()
        reader.load("s1", "cognitive", {"load": 0.7})
        result = reader.read_section("s1", "cognitive")
        assert result == {"load": 0.7}

    def test_read_section_returns_none_for_missing(self) -> None:
        reader = FakeSessionStateReader()
        assert reader.read_section("s1", "missing") is None

    def test_read_sections_batch(self) -> None:
        reader = FakeSessionStateReader()
        reader.load("s1", "a", {"x": 1})
        reader.load("s1", "b", {"y": 2})
        result = reader.read_sections("s1", ["a", "b", "c"])
        assert "a" in result
        assert "b" in result
        assert "c" not in result

    def test_get_snapshot(self) -> None:
        reader = FakeSessionStateReader()
        reader.load("s1", "cognitive", {"load": 0.5})
        reader.load("s1", "affective_now", {"emotion": "calm"})
        snap = reader.get_snapshot("s1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "s1"
        assert snap.has_section("cognitive")
        assert snap.has_section("affective_now")

    def test_get_snapshot_empty_session(self) -> None:
        reader = FakeSessionStateReader()
        snap = reader.get_snapshot("s1")
        assert snap.sections == {}

    def test_session_isolation(self) -> None:
        reader = FakeSessionStateReader()
        reader.load("s1", "a", {"x": 1})
        reader.load("s2", "a", {"x": 2})
        assert reader.read_section("s1", "a") == {"x": 1}
        assert reader.read_section("s2", "a") == {"x": 2}


# =========================================================================
# 5.1.2 -- SubscriptionHandle
# =========================================================================


class TestSubscriptionHandle:
    """Tests for SubscriptionHandle frozen dataclass."""

    def test_default_construction(self) -> None:
        h = SubscriptionHandle()
        assert h.subscription_id == ""
        assert h.topic == ""

    def test_construction_with_values(self) -> None:
        h = SubscriptionHandle(subscription_id="sub-1", topic="test.topic")
        assert h.subscription_id == "sub-1"
        assert h.topic == "test.topic"

    def test_frozen(self) -> None:
        h = SubscriptionHandle(subscription_id="sub-1")
        with pytest.raises(AttributeError):
            h.subscription_id = "sub-2"  # type: ignore[misc]

    def test_direct_import_same_class(self) -> None:
        assert SubscriptionHandle is SubscriptionHandleDirect


# =========================================================================
# 5.1.2 -- IEventPort protocol
# =========================================================================


class TestIEventPortProtocol:
    """Tests for IEventPort protocol shape."""

    def test_runtime_checkable(self) -> None:
        port = FakeEventPort()
        assert isinstance(port, IEventPort)

    def test_has_emit_method(self) -> None:
        assert callable(getattr(IEventPort, "emit", None))

    def test_has_subscribe_method(self) -> None:
        assert callable(getattr(IEventPort, "subscribe", None))

    def test_has_unsubscribe_method(self) -> None:
        assert callable(getattr(IEventPort, "unsubscribe", None))

    def test_non_conforming_rejected(self) -> None:
        class NotAnEventPort:
            def emit(self) -> None:
                pass

        assert not isinstance(NotAnEventPort(), IEventPort)


class TestIEventPortStructural:
    """Tests for structural subtyping -- fake event port works end-to-end."""

    def test_emit_stores_event(self) -> None:
        port = FakeEventPort()
        port.emit("test.topic", {"key": "value"})
        assert len(port._events) == 1
        assert port._events[0] == ("test.topic", {"key": "value"})

    def test_subscribe_returns_handle(self) -> None:
        port = FakeEventPort()
        handle = port.subscribe("test.topic", lambda t, p: None)
        assert isinstance(handle, SubscriptionHandle)
        assert handle.topic == "test.topic"
        assert handle.subscription_id != ""

    def test_subscribe_handler_called_on_emit(self) -> None:
        port = FakeEventPort()
        received: list[tuple[str, dict]] = []
        port.subscribe("test.topic", lambda t, p: received.append((t, p)))
        port.emit("test.topic", {"x": 1})
        assert len(received) == 1
        assert received[0] == ("test.topic", {"x": 1})

    def test_unsubscribe_removes_handler(self) -> None:
        port = FakeEventPort()
        received: list[tuple[str, dict]] = []
        handle = port.subscribe("t", lambda t, p: received.append((t, p)))
        port.emit("t", {"a": 1})
        assert len(received) == 1
        result = port.unsubscribe(handle)
        assert result is True
        port.emit("t", {"b": 2})
        assert len(received) == 1  # Handler no longer called

    def test_unsubscribe_nonexistent_returns_false(self) -> None:
        port = FakeEventPort()
        handle = SubscriptionHandle(subscription_id="nonexistent", topic="t")
        assert port.unsubscribe(handle) is False

    def test_emit_with_trace_id(self) -> None:
        """FAB-09: events should carry cognitive_trace_id."""
        port = FakeEventPort()
        port.emit("test.topic", {"cognitive_trace_id": "trace-001", "data": "x"})
        assert port._events[0][1]["cognitive_trace_id"] == "trace-001"

    def test_multiple_subscribers(self) -> None:
        port = FakeEventPort()
        counts = [0, 0]

        def handler_a(t: str, p: dict) -> None:
            counts[0] += 1

        def handler_b(t: str, p: dict) -> None:
            counts[1] += 1

        port.subscribe("t", handler_a)
        port.subscribe("t", handler_b)
        port.emit("t", {})
        assert counts == [1, 1]

    def test_handler_exception_does_not_break_emit(self) -> None:
        port = FakeEventPort()
        good_called = [False]

        def bad_handler(t: str, p: dict) -> None:
            raise RuntimeError("boom")

        def good_handler(t: str, p: dict) -> None:
            good_called[0] = True

        port.subscribe("t", bad_handler)
        port.subscribe("t", good_handler)
        port.emit("t", {})
        assert good_called[0] is True


# =========================================================================
# 5.1.3 -- BridgeHealth
# =========================================================================


class TestBridgeHealth:
    """Tests for BridgeHealth frozen dataclass."""

    def test_default_offline(self) -> None:
        h = BridgeHealth()
        assert h.available is False
        assert h.mode == "K0_OFFLINE"
        assert h.is_offline() is True
        assert h.is_full() is False
        assert h.is_degraded() is False

    def test_full_mode(self) -> None:
        h = BridgeHealth(available=True, mode="K0_FULL")
        assert h.is_full() is True
        assert h.is_degraded() is False
        assert h.is_offline() is False

    def test_degraded_mode(self) -> None:
        h = BridgeHealth(available=True, mode="K0_DEGRADED")
        assert h.is_degraded() is True
        assert h.is_full() is False
        assert h.is_offline() is False

    def test_offline_when_not_available(self) -> None:
        h = BridgeHealth(available=False, mode="K0_FULL")
        assert h.is_offline() is True
        assert h.is_full() is False

    def test_to_dict(self) -> None:
        h = BridgeHealth(
            available=True,
            mode="K0_FULL",
            last_heartbeat_ms=1000,
            latency_ms=5,
            error_message="",
        )
        d = h.to_dict()
        assert d["available"] is True
        assert d["mode"] == "K0_FULL"
        assert d["last_heartbeat_ms"] == 1000
        assert d["latency_ms"] == 5
        assert d["error_message"] == ""

    def test_frozen(self) -> None:
        h = BridgeHealth()
        with pytest.raises(AttributeError):
            h.available = True  # type: ignore[misc]

    def test_direct_import_same_class(self) -> None:
        assert BridgeHealth is BridgeHealthDirect


# =========================================================================
# 5.1.3 -- BridgeCommandResult
# =========================================================================


class TestBridgeCommandResult:
    """Tests for BridgeCommandResult factories and structure."""

    def test_default_success(self) -> None:
        r = BridgeCommandResult()
        assert r.success is True
        assert r.data == {}
        assert r.error_code == ""
        assert r.error_message == ""

    def test_ok_factory(self) -> None:
        r = BridgeCommandResult.ok({"key": "value"}, latency_ms=10, trace_id="t-1")
        assert r.success is True
        assert r.data == {"key": "value"}
        assert r.latency_ms == 10
        assert r.trace_id == "t-1"

    def test_ok_factory_default_data(self) -> None:
        r = BridgeCommandResult.ok()
        assert r.success is True
        assert r.data == {}

    def test_fail_factory(self) -> None:
        r = BridgeCommandResult.fail(
            "k0_offline",
            "K0 is unreachable",
            k0_mode="K0_OFFLINE",
            trace_id="t-2",
        )
        assert r.success is False
        assert r.error_code == "k0_offline"
        assert r.error_message == "K0 is unreachable"
        assert r.k0_mode == "K0_OFFLINE"
        assert r.trace_id == "t-2"

    def test_fail_factory_defaults(self) -> None:
        r = BridgeCommandResult.fail("err", "msg")
        assert r.success is False
        assert r.k0_mode == "K0_OFFLINE"

    def test_frozen(self) -> None:
        r = BridgeCommandResult.ok({"x": 1})
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]

    def test_direct_import_same_class(self) -> None:
        assert BridgeCommandResult is BridgeCommandResultDirect


# =========================================================================
# 5.1.3 -- IFLRoute
# =========================================================================


class TestIFLRoute:
    """Tests for IFLRoute parsing and structure."""

    def test_default_construction(self) -> None:
        r = IFLRoute()
        assert r.address == ""
        assert r.namespace == ""
        assert r.function_name == ""
        assert r.timeout_ms == 0

    def test_parse_home_tool(self) -> None:
        r = IFLRoute.parse("tool.execute.home.lights")
        assert r.address == "tool.execute.home.lights"
        assert r.namespace == "home"
        assert r.function_name == "lights"

    def test_parse_device_tool(self) -> None:
        r = IFLRoute.parse("tool.execute.device.thermostat")
        assert r.namespace == "device"
        assert r.function_name == "thermostat"

    def test_parse_nested_function(self) -> None:
        r = IFLRoute.parse("tool.execute.home.lights.bedroom.dimmer")
        assert r.namespace == "home"
        assert r.function_name == "lights.bedroom.dimmer"

    def test_parse_with_timeout(self) -> None:
        r = IFLRoute.parse("tool.execute.home.lights", timeout_ms=5000)
        assert r.timeout_ms == 5000

    def test_parse_invalid_too_short(self) -> None:
        with pytest.raises(ValueError, match="Invalid IFL address"):
            IFLRoute.parse("tool.execute")

    def test_parse_invalid_wrong_prefix(self) -> None:
        with pytest.raises(ValueError, match="Invalid IFL address"):
            IFLRoute.parse("command.run.home.lights")

    def test_parse_invalid_missing_execute(self) -> None:
        with pytest.raises(ValueError, match="Invalid IFL address"):
            IFLRoute.parse("tool.invoke.home.lights")

    def test_frozen(self) -> None:
        r = IFLRoute.parse("tool.execute.home.lights")
        with pytest.raises(AttributeError):
            r.address = "other"  # type: ignore[misc]

    def test_direct_import_same_class(self) -> None:
        assert IFLRoute is IFLRouteDirect


# =========================================================================
# 5.1.3 -- IBridgePort protocol
# =========================================================================


class TestIBridgePortProtocol:
    """Tests for IBridgePort protocol shape."""

    def test_runtime_checkable(self) -> None:
        port = FakeBridgePort()
        assert isinstance(port, IFabricK0Port)

    def test_has_send_command_method(self) -> None:
        assert callable(getattr(IFabricK0Port, "send_command", None))

    def test_has_query_method(self) -> None:
        assert callable(getattr(IFabricK0Port, "query", None))

    def test_has_route_ifl_method(self) -> None:
        assert callable(getattr(IFabricK0Port, "route_ifl", None))

    def test_has_is_available_method(self) -> None:
        assert callable(getattr(IFabricK0Port, "is_available", None))

    def test_has_get_health_method(self) -> None:
        assert callable(getattr(IFabricK0Port, "get_health", None))

    def test_non_conforming_rejected(self) -> None:
        class NotABridge:
            pass

        assert not isinstance(NotABridge(), IFabricK0Port)


class TestIBridgePortStructural:
    """Tests for structural subtyping -- fake bridge port works end-to-end."""

    async def test_send_command_success(self) -> None:
        port = FakeBridgePort(available=True)
        result = await port.send_command(
            "memory.store",
            {"key": "val"},
            trace_id="t-1",
        )
        assert result.success is True
        assert result.data == {"stored": True}
        assert result.trace_id == "t-1"

    async def test_send_command_offline(self) -> None:
        port = FakeBridgePort(available=False)
        result = await port.send_command("memory.store", {"key": "val"})
        assert result.success is False
        assert result.error_code == "k0_offline"

    async def test_query_success(self) -> None:
        port = FakeBridgePort(available=True)
        result = await port.query(
            "memory.recall",
            {"filter": "recent"},
            trace_id="t-2",
        )
        assert result.success is True
        assert "results" in result.data

    async def test_query_offline(self) -> None:
        port = FakeBridgePort(available=False)
        result = await port.query("memory.recall", {})
        assert result.success is False

    async def test_route_ifl_success(self) -> None:
        port = FakeBridgePort(available=True)
        route = IFLRoute.parse("tool.execute.home.lights")
        result = await port.route_ifl(route, {"brightness": 80}, trace_id="t-3")
        assert result.success is True
        assert result.data["route"] == "tool.execute.home.lights"

    async def test_route_ifl_offline(self) -> None:
        port = FakeBridgePort(available=False)
        route = IFLRoute.parse("tool.execute.device.thermostat")
        result = await port.route_ifl(route, {"temp": 22})
        assert result.success is False

    def test_is_available_true(self) -> None:
        port = FakeBridgePort(available=True)
        assert port.is_available() is True

    def test_is_available_false(self) -> None:
        port = FakeBridgePort(available=False)
        assert port.is_available() is False

    def test_get_health_full(self) -> None:
        port = FakeBridgePort(available=True, mode="K0_FULL")
        h = port.get_health()
        assert isinstance(h, BridgeHealth)
        assert h.is_full() is True

    def test_get_health_offline(self) -> None:
        port = FakeBridgePort(available=False, mode="K0_OFFLINE")
        h = port.get_health()
        assert h.is_offline() is True

    async def test_commands_recorded(self) -> None:
        port = FakeBridgePort(available=True)
        await port.send_command("checkpoint", {"seq": 1})
        await port.send_command("feedback.signal", {"type": "positive"})
        assert len(port._commands) == 2
        assert port._commands[0][0] == "checkpoint"
        assert port._commands[1][0] == "feedback.signal"


# =========================================================================
# Cross-port: structural compatibility with inline declarations
# =========================================================================


class TestInlineProtocolCompatibility:
    """Verify the canonical ports are structurally compatible with inline ones."""

    def test_policy_ports_isessionstatereader_compatible(self) -> None:
        """FakeSessionStateReader satisfies both canonical and inline protocol."""

        reader = FakeSessionStateReader()
        # Both should accept via isinstance (if both are runtime_checkable)
        assert isinstance(reader, ISessionStateReader)
        # Structural: has read_section(session_id, section)
        assert hasattr(reader, "read_section")

    def test_bridge_provider_ibridgeport_methods_subset(self) -> None:
        """Canonical IBridgePort has the same core methods as inline."""
        from k1.fabric.providers.bridge_provider import IBridgePort as InlineBridgePort

        # Both should have send_command, query, is_available
        for method_name in ("send_command", "query", "is_available"):
            assert callable(getattr(IFabricK0Port, method_name, None))
            assert callable(getattr(InlineBridgePort, method_name, None))

    def test_agent_provider_isessionstatereader_compatible(self) -> None:
        """FakeSessionStateReader satisfies agent_provider's inline protocol."""

        reader = FakeSessionStateReader()
        # Structural: has read_section method
        assert hasattr(reader, "read_section")


# =========================================================================
# Exports
# =========================================================================


class TestPortsExports:
    """Tests for ports package __all__ validation."""

    def test_export_count(self) -> None:
        from k1.fabric.ports import __all__

        # 8 (5.1.1-5.1.3) + 4 (5.1.4) + 2 (5.1.5) + 2 (5.1.6) = 16
        assert len(__all__) >= 8

    def test_all_exports_present(self) -> None:
        from k1.fabric.ports import __all__

        expected = [
            "ISessionStateReader",
            "SessionSnapshot",
            "IEventPort",
            "SubscriptionHandle",
            "IFabricK0Port",
            "BridgeHealth",
            "BridgeCommandResult",
            "IFLRoute",
        ]
        for name in expected:
            assert name in __all__, f"{name} missing from __all__"

    def test_all_importable(self) -> None:
        import k1.fabric.ports as ports_mod
        from k1.fabric.ports import __all__

        for name in __all__:
            assert hasattr(ports_mod, name), f"{name} not importable from k1.fabric.ports"

    def test_state_reader_exports(self) -> None:
        from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot

        assert ISessionStateReader is not None
        assert SessionSnapshot is not None

    def test_event_port_exports(self) -> None:
        from k1.fabric.ports.event_port import IEventPort, SubscriptionHandle

        assert IEventPort is not None
        assert SubscriptionHandle is not None

    def test_bridge_port_exports(self) -> None:
        from k1.fabric.ports.bridge_port import (
            BridgeCommandResult,
            BridgeHealth,
            IFabricK0Port,
            IFLRoute,
        )

        assert IFabricK0Port is not None
        assert BridgeHealth is not None
        assert BridgeCommandResult is not None
        assert IFLRoute is not None
        assert BridgeCommandResult is not None
        assert IFLRoute is not None
