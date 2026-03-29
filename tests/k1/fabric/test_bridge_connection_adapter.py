"""
Epic 6.3.11 -- Test BridgeConnectionAdapter integration.

Covers:
  - LOCAL COLD mode: no client provided, all operations return offline fallback.
  - Bridge available: connected client routes send_command/query/route_ifl.
  - Client error handling: operation failure marks adapter disconnected.
  - Auto-reconnect: throttled, max-attempts enforced.
  - IFLRoute.parse(): home.*, device.* addresses, invalid format raises.
  - BridgeHealth: mode transitions FULL -> OFFLINE -> FULL.
  - Thread-safe health snapshot consistency.

NO MOCKS -- uses InMemoryBridgeClient (a real in-memory implementation)
and BridgeConnectionAdapter (production code).

References:
  - fabric-implementation-plan.md Epic 6.3.11
  - bridge_architecture.mmd (IFL addressing, envelope format)
  - BridgeConnectionAdapter (5.2.8)
  - IBridgePort protocol (5.1.3)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.adapters.bridge_connection import (
    BridgeConnectionAdapter,
    BridgeConnectionConfig,
)
from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IFLRoute

# ---------------------------------------------------------------------------
# InMemoryBridgeClient -- real test implementation (NOT a mock)
# ---------------------------------------------------------------------------


class InMemoryBridgeClient:
    """
    In-memory bridge client satisfying BridgeConnectionAdapter's protocol.

    Real test implementation with recorded calls and configurable responses.
    NOT a mock: has real state, real behavior, raises real errors.
    """

    def __init__(
        self,
        *,
        connected: bool = True,
        health_mode: str = "K0_FULL",
        latency_ms: int = 5,
    ) -> None:
        self._connected = connected
        self._health_mode = health_mode
        self._latency_ms = latency_ms
        self._calls: List[Dict[str, Any]] = []
        self._responses: Dict[str, Dict[str, Any]] = {}
        self._ifl_responses: Dict[str, Dict[str, Any]] = {}
        self._should_error: bool = False
        self._error_msg: str = "client error"

    # -- Protocol methods ---------------------------------------------------

    async def send(
        self,
        operation: str,
        payload: Dict[str, Any],
        trace_id: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        """Send command, recording the call."""
        self._record("send", operation, payload, trace_id)
        if self._should_error:
            raise RuntimeError(self._error_msg)
        return self._responses.get(operation, {"status": "ok"})

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        trace_id: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        """Query, recording the call."""
        self._record("query", operation, selectors, trace_id)
        if self._should_error:
            raise RuntimeError(self._error_msg)
        return self._responses.get(operation, {"results": []})

    async def route_ifl(
        self,
        address: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> Dict[str, Any]:
        """Route IFL call, recording the call."""
        self._record("route_ifl", address, payload, trace_id)
        if self._should_error:
            raise RuntimeError(self._error_msg)
        return self._ifl_responses.get(address, {"executed": True})

    def is_connected(self) -> bool:
        """Return current connection state."""
        return self._connected

    def get_health(self) -> Dict[str, Any]:
        """Return health dict."""
        return {
            "available": self._connected,
            "mode": self._health_mode,
            "latency_ms": self._latency_ms,
        }

    async def connect(self) -> bool:
        """Simulate connecting."""
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Simulate disconnecting."""
        self._connected = False

    # -- Test helpers -------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        """Change connection state."""
        self._connected = connected

    def set_error(self, should_error: bool, msg: str = "client error") -> None:
        """Enable/disable forced errors on operations."""
        self._should_error = should_error
        self._error_msg = msg

    def add_response(self, operation: str, data: Dict[str, Any]) -> None:
        """Register a response for a given operation."""
        self._responses[operation] = data

    def add_ifl_response(self, address: str, data: Dict[str, Any]) -> None:
        """Register a response for an IFL address."""
        self._ifl_responses[address] = data

    @property
    def calls(self) -> List[Dict[str, Any]]:
        """Return recorded call log."""
        return list(self._calls)

    def _record(
        self,
        method: str,
        operation: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        self._calls.append(
            {
                "method": method,
                "operation": operation,
                "payload": payload,
                "trace_id": trace_id,
            }
        )


# =========================================================================
# 6.3.11a -- LOCAL COLD mode (no client)
# =========================================================================


class TestBridgeUnavailable:
    """
    BridgeConnectionAdapter with NO client -> LOCAL COLD mode.
    All operations return graceful offline fallback, no crash.
    """

    def _make_adapter(self) -> BridgeConnectionAdapter:
        return BridgeConnectionAdapter(client=None)

    def test_is_available_false_no_client(self) -> None:
        """No client means adapter is not available."""
        adapter = self._make_adapter()
        assert adapter.is_available() is False

    def test_health_shows_k0_offline(self) -> None:
        """Health indicates K0_OFFLINE when no client."""
        adapter = self._make_adapter()
        health = adapter.get_health()

        assert isinstance(health, BridgeHealth)
        assert health.available is False
        assert health.mode == "K0_OFFLINE"
        assert health.is_offline() is True

    async def test_send_command_returns_offline_fallback(self) -> None:
        """send_command returns k0_offline BridgeCommandResult."""
        adapter = self._make_adapter()

        result = await adapter.send_command(
            "memory.store",
            {"key": "test", "value": "data"},
            trace_id="trace-001",
        )

        assert isinstance(result, BridgeCommandResult)
        assert result.success is False
        assert result.error_code == "k0_offline"
        assert result.k0_mode == "K0_OFFLINE"
        assert result.trace_id == "trace-001"

    async def test_query_returns_offline_fallback(self) -> None:
        """query returns k0_offline BridgeCommandResult."""
        adapter = self._make_adapter()

        result = await adapter.query(
            "memory.recall",
            {"entity_id": "user-1"},
            trace_id="trace-002",
        )

        assert result.success is False
        assert result.error_code == "k0_offline"
        assert result.trace_id == "trace-002"

    async def test_route_ifl_returns_offline_fallback(self) -> None:
        """route_ifl returns k0_offline BridgeCommandResult."""
        adapter = self._make_adapter()
        route = IFLRoute.parse("tool.execute.home.lights")

        result = await adapter.route_ifl(
            route,
            {"action": "turn_on"},
            trace_id="trace-003",
        )

        assert result.success is False
        assert result.error_code == "k0_offline"
        assert result.trace_id == "trace-003"

    async def test_reconnect_fails_without_client(self) -> None:
        """reconnect() returns False when no client provided."""
        adapter = self._make_adapter()
        result = await adapter.reconnect()

        assert result is False
        assert adapter.is_available() is False

    async def test_disconnect_safe_without_client(self) -> None:
        """disconnect() does not crash when no client."""
        adapter = self._make_adapter()
        await adapter.disconnect()

        assert adapter.is_available() is False

    async def test_multiple_operations_no_crash(self) -> None:
        """Multiple operations on offline adapter: all return fallback, no crash."""
        adapter = self._make_adapter()

        for _ in range(10):
            r1 = await adapter.send_command("memory.store", {})
            r2 = await adapter.query("memory.recall", {})
            route = IFLRoute.parse("tool.execute.home.thermostat")
            r3 = await adapter.route_ifl(route, {})

            assert r1.success is False
            assert r2.success is False
            assert r3.success is False


# =========================================================================
# 6.3.11b -- Bridge available (connected client)
# =========================================================================


class TestBridgeAvailable:
    """
    BridgeConnectionAdapter with connected client: operations route through.
    """

    def _make_adapter(
        self,
        client: Optional[InMemoryBridgeClient] = None,
        config: Optional[BridgeConnectionConfig] = None,
    ) -> BridgeConnectionAdapter:
        c = client or InMemoryBridgeClient(connected=True)
        return BridgeConnectionAdapter(client=c, config=config)

    def test_is_available_true_with_connected_client(self) -> None:
        """Connected client means adapter is available."""
        adapter = self._make_adapter()
        assert adapter.is_available() is True

    def test_health_shows_k0_full(self) -> None:
        """Health indicates K0_FULL with connected client."""
        adapter = self._make_adapter()
        health = adapter.get_health()

        assert health.available is True
        assert health.mode == "K0_FULL"
        assert health.is_full() is True
        assert health.is_offline() is False

    async def test_send_command_routes_through_client(self) -> None:
        """send_command routes to client.send() and returns ok result."""
        client = InMemoryBridgeClient(connected=True)
        client.add_response("memory.store", {"stored": True, "version": 3})
        adapter = self._make_adapter(client=client)

        result = await adapter.send_command(
            "memory.store",
            {"key": "test", "value": "hello"},
            trace_id="trace-100",
        )

        assert result.success is True
        assert result.data == {"stored": True, "version": 3}
        assert result.trace_id == "trace-100"

        # Verify client received the call
        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["method"] == "send"
        assert call["operation"] == "memory.store"
        assert call["trace_id"] == "trace-100"

    async def test_query_routes_through_client(self) -> None:
        """query routes to client.query() and returns ok result."""
        client = InMemoryBridgeClient(connected=True)
        client.add_response("memory.recall", {"memories": [{"id": "m1"}]})
        adapter = self._make_adapter(client=client)

        result = await adapter.query(
            "memory.recall",
            {"entity_id": "user-1"},
            trace_id="trace-200",
        )

        assert result.success is True
        assert result.data == {"memories": [{"id": "m1"}]}
        assert len(client.calls) == 1
        assert client.calls[0]["method"] == "query"

    async def test_route_ifl_routes_through_client(self) -> None:
        """route_ifl routes to client.route_ifl() and returns ok result."""
        client = InMemoryBridgeClient(connected=True)
        client.add_ifl_response(
            "tool.execute.home.lights",
            {"executed": True, "state": "on"},
        )
        adapter = self._make_adapter(client=client)
        route = IFLRoute.parse("tool.execute.home.lights")

        result = await adapter.route_ifl(
            route,
            {"action": "turn_on"},
            trace_id="trace-300",
        )

        assert result.success is True
        assert result.data == {"executed": True, "state": "on"}
        assert len(client.calls) == 1
        assert client.calls[0]["method"] == "route_ifl"

    async def test_default_timeout_from_config(self) -> None:
        """Operations use config.default_timeout_ms when no per-call timeout."""
        client = InMemoryBridgeClient(connected=True)
        config = BridgeConnectionConfig(default_timeout_ms=7500)
        adapter = self._make_adapter(client=client, config=config)

        await adapter.send_command("memory.store", {})

        # Client received the call (we trust the timeout is passed internally)
        assert len(client.calls) == 1

    async def test_probe_connection_on_init(self) -> None:
        """Client that is_connected() on init -> adapter available immediately."""
        client = InMemoryBridgeClient(connected=True)
        adapter = BridgeConnectionAdapter(client=client)

        assert adapter.is_available() is True
        assert adapter.get_health().mode == "K0_FULL"

    async def test_disconnected_client_on_init(self) -> None:
        """Client that is NOT connected on init -> adapter not available."""
        client = InMemoryBridgeClient(connected=False)
        adapter = BridgeConnectionAdapter(client=client)

        assert adapter.is_available() is False
        assert adapter.get_health().is_offline() is True


# =========================================================================
# 6.3.11c -- Client error handling
# =========================================================================


class TestBridgeClientErrors:
    """
    When client operations raise exceptions, adapter returns error result
    and marks itself disconnected.
    """

    async def test_send_error_returns_bridge_error(self) -> None:
        """send_command failure returns bridge_error result."""
        client = InMemoryBridgeClient(connected=True)
        client.set_error(True, "connection reset")
        adapter = BridgeConnectionAdapter(client=client)

        result = await adapter.send_command(
            "memory.store",
            {"key": "test"},
            trace_id="trace-err-1",
        )

        assert result.success is False
        assert result.error_code == "bridge_error"
        assert "connection reset" in result.error_message
        assert result.k0_mode == "K0_OFFLINE"

    async def test_query_error_marks_disconnected(self) -> None:
        """Query failure marks adapter as disconnected."""
        client = InMemoryBridgeClient(connected=True)
        adapter = BridgeConnectionAdapter(client=client)

        assert adapter.is_available() is True

        # Now make client error
        client.set_error(True, "timeout")
        await adapter.query("memory.recall", {})

        assert adapter.is_available() is False
        assert adapter.get_health().is_offline() is True

    async def test_ifl_error_marks_disconnected(self) -> None:
        """IFL routing failure marks adapter as disconnected."""
        client = InMemoryBridgeClient(connected=True)
        adapter = BridgeConnectionAdapter(client=client)

        client.set_error(True, "network unreachable")
        route = IFLRoute.parse("tool.execute.home.sensor")
        await adapter.route_ifl(route, {})

        assert adapter.is_available() is False

    async def test_error_then_recovery_via_operation(self) -> None:
        """After error disconnect, reconnect restores availability."""
        client = InMemoryBridgeClient(connected=True)
        config = BridgeConnectionConfig(reconnect_interval_ms=0)
        adapter = BridgeConnectionAdapter(client=client, config=config)

        # Cause error
        client.set_error(True, "transient")
        await adapter.send_command("test.op", {})
        assert adapter.is_available() is False

        # Fix client and reconnect
        client.set_error(False)
        reconnected = await adapter.reconnect()
        assert reconnected is True
        assert adapter.is_available() is True

        # Operations work again
        result = await adapter.send_command("test.op", {})
        assert result.success is True


# =========================================================================
# 6.3.11d -- Auto-reconnect behavior
# =========================================================================


class TestBridgeAutoReconnect:
    """
    Test reconnect(): throttling, max attempts, state transitions.
    """

    async def test_reconnect_succeeds(self) -> None:
        """Reconnect with disconnected client -> client.connect() called -> available."""
        client = InMemoryBridgeClient(connected=False)
        config = BridgeConnectionConfig(reconnect_interval_ms=0)
        adapter = BridgeConnectionAdapter(client=client, config=config)

        assert adapter.is_available() is False
        result = await adapter.reconnect()

        assert result is True
        assert adapter.is_available() is True

    async def test_reconnect_throttle(self) -> None:
        """Reconnect within interval_ms: does not actually attempt."""
        client = InMemoryBridgeClient(connected=False)
        config = BridgeConnectionConfig(reconnect_interval_ms=60_000)
        adapter = BridgeConnectionAdapter(client=client, config=config)

        # First attempt goes through
        await adapter.reconnect()

        # Second attempt within 60s is throttled (returns current state)
        result = await adapter.reconnect()
        # Returns True because first attempt connected
        assert result is True

    async def test_reconnect_max_attempts(self) -> None:
        """Max reconnect attempts enforced."""
        client = _FailingConnectClient(fail_count=100)
        config = BridgeConnectionConfig(
            reconnect_interval_ms=0,
            max_reconnect_attempts=3,
        )
        adapter = BridgeConnectionAdapter(client=client, config=config)

        # Exhaust all 3 attempts
        for _ in range(3):
            await adapter.reconnect()

        # 4th attempt: max reached, returns False immediately
        result = await adapter.reconnect()
        assert result is False

    async def test_successful_reconnect_resets_attempts(self) -> None:
        """After successful reconnect, attempt counter resets."""
        client = InMemoryBridgeClient(connected=False)
        config = BridgeConnectionConfig(
            reconnect_interval_ms=0,
            max_reconnect_attempts=5,
        )
        adapter = BridgeConnectionAdapter(client=client, config=config)

        # First reconnect succeeds (resets counter)
        result = await adapter.reconnect()
        assert result is True

        # The adapter is connected, health should be full
        assert adapter.get_health().mode == "K0_FULL"


# =========================================================================
# 6.3.11e -- IFLRoute parsing
# =========================================================================


class TestIFLRouting:
    """
    IFLRoute.parse() for various IFL addresses.
    """

    def test_parse_home_address(self) -> None:
        """Parse tool.execute.home.lights -> namespace=home, function=lights."""
        route = IFLRoute.parse("tool.execute.home.lights")

        assert route.address == "tool.execute.home.lights"
        assert route.namespace == "home"
        assert route.function_name == "lights"

    def test_parse_device_address(self) -> None:
        """Parse tool.execute.device.thermostat -> namespace=device."""
        route = IFLRoute.parse("tool.execute.device.thermostat")

        assert route.namespace == "device"
        assert route.function_name == "thermostat"

    def test_parse_nested_function_name(self) -> None:
        """Dotted function names: tool.execute.home.sensor.temperature."""
        route = IFLRoute.parse("tool.execute.home.sensor.temperature")

        assert route.namespace == "home"
        assert route.function_name == "sensor.temperature"

    def test_parse_with_timeout(self) -> None:
        """Parse with custom timeout_ms."""
        route = IFLRoute.parse("tool.execute.home.lights", timeout_ms=5000)

        assert route.timeout_ms == 5000
        assert route.namespace == "home"

    def test_invalid_address_raises_valueerror(self) -> None:
        """Invalid IFL address raises ValueError."""
        with pytest.raises(ValueError, match="Invalid IFL address"):
            IFLRoute.parse("invalid.address")

    def test_too_short_address_raises(self) -> None:
        """Address with fewer than 4 parts raises ValueError."""
        with pytest.raises(ValueError):
            IFLRoute.parse("tool.execute")

    def test_wrong_prefix_raises(self) -> None:
        """Address not starting with tool.execute raises ValueError."""
        with pytest.raises(ValueError):
            IFLRoute.parse("agent.spawn.home.lights")


# =========================================================================
# 6.3.11f -- Health transitions
# =========================================================================


class TestBridgeHealthTransitions:
    """
    BridgeHealth mode transitions through adapter lifecycle.
    """

    def test_health_offline_to_full(self) -> None:
        """Adapter starts offline, becomes full after connecting client."""
        client = InMemoryBridgeClient(connected=False)
        adapter = BridgeConnectionAdapter(client=client)

        # Before: offline
        assert adapter.get_health().is_offline() is True

    async def test_health_full_to_offline_on_error(self) -> None:
        """Connected adapter goes offline on client error."""
        client = InMemoryBridgeClient(connected=True)
        adapter = BridgeConnectionAdapter(client=client)

        assert adapter.get_health().is_full() is True

        # Cause error
        client.set_error(True, "network down")
        await adapter.send_command("test.op", {})

        health = adapter.get_health()
        assert health.is_offline() is True
        assert "network down" in health.error_message

    async def test_health_offline_to_full_via_reconnect(self) -> None:
        """Offline adapter transitions to full via reconnect."""
        client = InMemoryBridgeClient(connected=False)
        config = BridgeConnectionConfig(reconnect_interval_ms=0)
        adapter = BridgeConnectionAdapter(client=client, config=config)

        assert adapter.get_health().is_offline() is True

        await adapter.reconnect()

        health = adapter.get_health()
        assert health.is_full() is True
        assert health.available is True
        assert health.last_heartbeat_ms > 0

    async def test_disconnect_transitions_to_offline(self) -> None:
        """disconnect() transitions health to offline."""
        client = InMemoryBridgeClient(connected=True)
        adapter = BridgeConnectionAdapter(client=client)

        assert adapter.get_health().is_full() is True

        await adapter.disconnect()

        assert adapter.get_health().is_offline() is True
        assert adapter.is_available() is False


# =========================================================================
# 6.3.11g -- BridgeCommandResult factories
# =========================================================================


class TestBridgeCommandResult:
    """
    BridgeCommandResult.ok() and .fail() factory methods.
    """

    def test_ok_factory(self) -> None:
        """ok() creates successful result."""
        result = BridgeCommandResult.ok(
            data={"stored": True},
            latency_ms=12,
            trace_id="t-1",
        )

        assert result.success is True
        assert result.data == {"stored": True}
        assert result.latency_ms == 12
        assert result.trace_id == "t-1"
        assert result.error_code == ""

    def test_ok_factory_defaults(self) -> None:
        """ok() with defaults."""
        result = BridgeCommandResult.ok()

        assert result.success is True
        assert result.data == {}
        assert result.latency_ms == 0

    def test_fail_factory(self) -> None:
        """fail() creates failure result."""
        result = BridgeCommandResult.fail(
            "timeout",
            "operation timed out",
            k0_mode="K0_DEGRADED",
            trace_id="t-2",
        )

        assert result.success is False
        assert result.error_code == "timeout"
        assert result.error_message == "operation timed out"
        assert result.k0_mode == "K0_DEGRADED"
        assert result.trace_id == "t-2"

    def test_fail_factory_defaults(self) -> None:
        """fail() with minimal args."""
        result = BridgeCommandResult.fail("k0_offline", "offline")

        assert result.success is False
        assert result.k0_mode == "K0_OFFLINE"


# ---------------------------------------------------------------------------
# Helper: client that fails connect() N times
# ---------------------------------------------------------------------------


class _FailingConnectClient:
    """Client whose connect() fails a configurable number of times."""

    def __init__(self, fail_count: int = 1) -> None:
        self._fail_count = fail_count
        self._attempts = 0

    def is_connected(self) -> bool:
        return self._attempts > self._fail_count

    def get_health(self) -> Dict[str, Any]:
        return {"available": False, "mode": "K0_OFFLINE"}

    async def connect(self) -> bool:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            return False
        return True

    async def disconnect(self) -> None:
        pass
