"""
Tests for MCP Connector Lifecycle -- 5.1.3 + 5.1.4.

5.1.3 ConnectorLifecycleManager:
  TestConnectorLifecycleManagerInit      -- Constructor, initial state.
  TestDiscoverAndRegister                -- Full cycle, empty, with errors.
  TestStartLifecycleMonitoring           -- Subscribe, idempotent, stop.
  TestRefresh                            -- Unregister + re-discover + re-register.
  TestUnregisterServer                   -- Remove all capabilities for server.
  TestHealthEventHandler                 -- Provider recovery triggers refresh.
  TestServerMapping                      -- server_capabilities tracking.

5.1.4 K0ProxyClient:
  TestProxyRequest                       -- Dataclass validation.
  TestProxyResponse                      -- Dataclass defaults.
  TestK0ProxyClientDisabled              -- No endpoint = unavailable.
  TestK0ProxyClientInvoke                -- Success, 401, 429, errors.
  TestK0ProxyClientHealth                -- Health check scenarios.
  TestProxyErrors                        -- Error types.

  TestConnectorAllReExports              -- __init__ re-exports all 5.1.x.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.connectors.connector_lifecycle import ConnectorLifecycleManager
from k1.orchestrator.connectors.k0_proxy_client import (
    K0ProxyClient,
    ProxyRateLimitedError,
    ProxyRequest,
    ProxyResponse,
    ProxyUnavailableError,
)
from k1.orchestrator.connectors.mcp_discovery import (
    DiscoveredTool,
    MCPServerConfig,
    MCPToolDiscovery,
)
from k1.orchestrator.connectors.mcp_registrar import MCPRegistrationBridge, build_capability_id
from k1.orchestrator.types import RegistryEntry

# ===========================================================================
# Fakes -- shared across 5.1.3 / 5.1.4 tests
# ===========================================================================


class FakeTransport:
    """Fake IMCPTransportDiscovery."""

    def __init__(
        self,
        tools_by_server: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        error_servers: Optional[set] = None,
    ) -> None:
        self.tools_by_server = tools_by_server or {}
        self.error_servers = error_servers or set()
        self.calls: List[MCPServerConfig] = []

    async def list_tools(
        self,
        server: MCPServerConfig,
    ) -> List[Dict[str, Any]]:
        self.calls.append(server)
        if server.id in self.error_servers:
            raise ConnectionError(f"Cannot reach server '{server.id}'")
        return self.tools_by_server.get(server.id, [])


class FakeFabricPort:
    """Fake IFabricGatewayPort -- query_registry only."""

    def __init__(
        self,
        registry: Optional[Dict[str, RegistryEntry]] = None,
    ) -> None:
        self._registry: Dict[str, RegistryEntry] = registry or {}

    async def execute(self, request: object) -> object:
        raise NotImplementedError

    async def execute_batch(self, requests: list) -> list:
        raise NotImplementedError

    async def query_registry(self, capability_name: str) -> Optional[RegistryEntry]:
        return self._registry.get(capability_name)

    async def query_registry_by_category(self, prefix: str) -> list:
        return []


class FakeDeltaPort:
    """Fake IDeltaEmitPort -- records emitted events."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any], str]] = []

    async def emit(
        self,
        event_topic: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        self.events.append((event_topic, payload, trace_id))

    async def emit_progress(
        self,
        step_id: str,
        summary: str,
        trace_id: str,
    ) -> None:
        pass

    async def emit_hil_request(self, hil_request: object, trace_id: str) -> None:
        pass


class FakeSubscriptionHandle:
    """Minimal subscription handle."""

    def __init__(self, topic: str) -> None:
        self.topic = topic


class FakeEventPort:
    """Fake IEventSubscriptionPort -- records subscriptions and fires events."""

    def __init__(self) -> None:
        self.subscriptions: List[Tuple[str, Any]] = []
        self.handles: List[FakeSubscriptionHandle] = []
        self.unsubscribed: List[FakeSubscriptionHandle] = []

    def subscribe(
        self,
        topic: str,
        handler: Any,
    ) -> FakeSubscriptionHandle:
        handle = FakeSubscriptionHandle(topic)
        self.subscriptions.append((topic, handler))
        self.handles.append(handle)
        return handle

    def unsubscribe(self, handle: object) -> bool:
        self.unsubscribed.append(handle)
        return True

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        for sub_topic, handler in self.subscriptions:
            if sub_topic == topic:
                handler(topic, payload)

    def get_handler(self, topic: str) -> Optional[Any]:
        """Return the latest handler registered for a topic."""
        for sub_topic, handler in reversed(self.subscriptions):
            if sub_topic == topic:
                return handler
        return None


class FakeBridgePort:
    """Fake IBridgeWritePort -- records audit submissions."""

    def __init__(self) -> None:
        self.audits: List[Tuple[Dict[str, Any], str]] = []

    async def submit_audit(
        self,
        run_manifest: Dict[str, Any],
        trace_id: str,
    ) -> None:
        self.audits.append((run_manifest, trace_id))

    async def write_wal(
        self,
        dag_id: str,
        entry_type: str,
        payload: Dict[str, Any],
        trace_id: str,
    ) -> None:
        pass

    async def read_wal(self, dag_id: str) -> Optional[List[Dict[str, Any]]]:
        return None

    async def list_wal_ids(self) -> List[str]:
        return []

    async def submit_deferred_result(
        self,
        result: Any,
        workflow_id: str,
        trace_id: str,
    ) -> None:
        pass


class FakeProxyTransport:
    """Fake IProxyTransport -- returns canned HTTP responses."""

    def __init__(
        self,
        post_response: Optional[Dict[str, Any]] = None,
        get_response: Optional[Dict[str, Any]] = None,
        post_error: Optional[Exception] = None,
        get_error: Optional[Exception] = None,
    ) -> None:
        self.post_response = post_response or {"status": 200, "body": {}, "headers": {}}
        self.get_response = get_response or {"status": 200, "body": {}}
        self.post_error = post_error
        self.get_error = get_error
        self.post_calls: List[Tuple[str, Dict[str, Any]]] = []
        self.get_calls: List[str] = []

    async def post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self.post_calls.append((url, body))
        if self.post_error:
            raise self.post_error
        return self.post_response

    async def get(self, url: str) -> Dict[str, Any]:
        self.get_calls.append(url)
        if self.get_error:
            raise self.get_error
        return self.get_response


# ===========================================================================
# Helpers
# ===========================================================================


def _write_yaml(content: str) -> str:
    """Write YAML content to a temp file, return path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


def _tool(
    name: str = "get_weather",
    server_id: str = "weather_api",
    description: str = "Get weather info",
) -> DiscoveredTool:
    return DiscoveredTool(
        server_id=server_id,
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
    )


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="MCP",
        safety_band_min="GREEN",
        availability="HEALTHY",
    )


def _make_lifecycle(
    yaml_content: str,
    tools_by_server: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    registry: Optional[Dict[str, RegistryEntry]] = None,
) -> Tuple[
    ConnectorLifecycleManager, FakeTransport, FakeFabricPort, FakeDeltaPort, FakeEventPort, str
]:
    """Build a ConnectorLifecycleManager with fakes. Returns (mgr, transport, fabric, delta, events, yaml_path)."""
    path = _write_yaml(yaml_content)
    transport = FakeTransport(tools_by_server=tools_by_server or {})
    fabric = FakeFabricPort(registry=registry or {})
    delta = FakeDeltaPort()
    events = FakeEventPort()

    discovery = MCPToolDiscovery(config_path=path, transport=transport)
    registrar = MCPRegistrationBridge(fabric=fabric, delta=delta)
    mgr = ConnectorLifecycleManager(
        discovery=discovery,
        registrar=registrar,
        events=events,
        delta=delta,
    )
    return mgr, transport, fabric, delta, events, path


# ===========================================================================
# 5.1.3 -- ConnectorLifecycleManager
# ===========================================================================


class TestConnectorLifecycleManagerInit:
    """Constructor and initial state."""

    def test_initial_state_empty(self) -> None:
        yaml_path = _write_yaml("servers: []")
        try:
            discovery = MCPToolDiscovery(config_path=yaml_path)
            registrar = MCPRegistrationBridge(fabric=FakeFabricPort(), delta=FakeDeltaPort())
            mgr = ConnectorLifecycleManager(
                discovery=discovery,
                registrar=registrar,
                events=FakeEventPort(),
                delta=FakeDeltaPort(),
            )
            assert mgr.server_capabilities == {}
            assert mgr.get_server_ids() == []
            assert mgr.get_capabilities("nonexistent") == []
        finally:
            os.unlink(yaml_path)

    def test_pending_refreshes_empty_initially(self) -> None:
        yaml_path = _write_yaml("servers: []")
        try:
            discovery = MCPToolDiscovery(config_path=yaml_path)
            registrar = MCPRegistrationBridge(fabric=FakeFabricPort(), delta=FakeDeltaPort())
            mgr = ConnectorLifecycleManager(
                discovery=discovery,
                registrar=registrar,
                events=FakeEventPort(),
                delta=FakeDeltaPort(),
            )
            assert mgr.get_pending_refreshes() == []
        finally:
            os.unlink(yaml_path)


class TestDiscoverAndRegister:
    """discover_and_register() -- full discovery + registration cycle."""

    @pytest.mark.asyncio
    async def test_discover_and_register_success(self) -> None:
        yaml = """servers:
  - id: calendar
    type: remote
    endpoint: https://mcp.google.com/cal
"""
        tools = {
            "calendar": [
                {"name": "create_event", "description": "Create cal event"},
                {"name": "list_events", "description": "List cal events"},
            ]
        }
        mgr, transport, fabric, delta, events, path = _make_lifecycle(yaml, tools)
        try:
            result = await mgr.discover_and_register()
            assert result.registered == 2
            assert result.skipped == 0
            assert result.errors == []
            assert len(delta.events) == 2
            assert "calendar" in mgr.server_capabilities
            assert len(mgr.server_capabilities["calendar"]) == 2
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_discover_and_register_empty(self) -> None:
        yaml = "servers: []"
        mgr, _, _, delta, _, path = _make_lifecycle(yaml)
        try:
            result = await mgr.discover_and_register()
            assert result.registered == 0
            assert result.skipped == 0
            assert len(delta.events) == 0
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_discover_and_register_with_existing(self) -> None:
        """Tools already in registry are skipped."""
        yaml = """servers:
  - id: weather
    type: remote
    endpoint: http://weather.local
"""
        tools = {
            "weather": [
                {"name": "get_forecast", "description": "Forecast"},
                {"name": "get_current", "description": "Current"},
            ]
        }
        existing_cap = build_capability_id(_tool(name="get_forecast", server_id="weather"))
        registry = {existing_cap: _entry(existing_cap)}
        mgr, _, _, delta, _, path = _make_lifecycle(yaml, tools, registry)
        try:
            result = await mgr.discover_and_register()
            assert result.registered == 1
            assert result.skipped == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_discover_and_register_config_error(self) -> None:
        """Missing config file returns errors."""
        transport = FakeTransport()
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        events = FakeEventPort()
        discovery = MCPToolDiscovery(
            config_path="/nonexistent/path/mcp_servers.yaml",
            transport=transport,
        )
        registrar = MCPRegistrationBridge(fabric=fabric, delta=delta)
        mgr = ConnectorLifecycleManager(
            discovery=discovery,
            registrar=registrar,
            events=events,
            delta=delta,
        )
        result = await mgr.discover_and_register()
        assert result.registered == 0
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_updates_server_capabilities_mapping(self) -> None:
        """server_capabilities is populated after discover_and_register."""
        yaml = """servers:
  - id: srv_a
    type: local
    endpoint: /usr/bin/mcp-a
  - id: srv_b
    type: remote
    endpoint: http://b.local
"""
        tools = {
            "srv_a": [{"name": "tool_1", "description": "T1"}],
            "srv_b": [
                {"name": "tool_2", "description": "T2"},
                {"name": "tool_3", "description": "T3"},
            ],
        }
        mgr, _, _, _, _, path = _make_lifecycle(yaml, tools)
        try:
            await mgr.discover_and_register()
            assert "srv_a" in mgr.server_capabilities
            assert "srv_b" in mgr.server_capabilities
            assert len(mgr.server_capabilities["srv_a"]) == 1
            assert len(mgr.server_capabilities["srv_b"]) == 2
            assert mgr.get_server_ids() == ["srv_a", "srv_b"]
        finally:
            os.unlink(path)


class TestStartLifecycleMonitoring:
    """start_lifecycle_monitoring() / stop_lifecycle_monitoring()."""

    def test_subscribes_to_health_topic(self) -> None:
        yaml_path = _write_yaml("servers: []")
        try:
            mgr, _, _, _, events, _ = _make_lifecycle("servers: []")
            os.unlink(yaml_path)
            mgr.start_lifecycle_monitoring()
            assert len(events.subscriptions) == 1
            assert events.subscriptions[0][0] == "k1.fabric.provider.health.changed.v1"
        finally:
            pass

    def test_idempotent_resubscribe(self) -> None:
        """Calling twice unsubscribes the first handle."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.start_lifecycle_monitoring()
            mgr.start_lifecycle_monitoring()
            assert len(events.subscriptions) == 2
            assert len(events.unsubscribed) == 1
        finally:
            os.unlink(path)

    def test_stop_monitoring(self) -> None:
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.start_lifecycle_monitoring()
            mgr.stop_lifecycle_monitoring()
            assert len(events.unsubscribed) == 1
        finally:
            os.unlink(path)

    def test_stop_when_not_started(self) -> None:
        """stop_lifecycle_monitoring() is safe when not started."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.stop_lifecycle_monitoring()
            assert len(events.unsubscribed) == 0
        finally:
            os.unlink(path)


class TestRefresh:
    """refresh(server_id) -- unregister + re-discover + re-register."""

    @pytest.mark.asyncio
    async def test_refresh_known_server(self) -> None:
        yaml = """servers:
  - id: calendar
    type: remote
    endpoint: https://mcp.google.com/cal
"""
        tools = {
            "calendar": [
                {"name": "create_event", "description": "Create"},
                {"name": "list_events", "description": "List"},
            ]
        }
        mgr, _, _, delta, _, path = _make_lifecycle(yaml, tools)
        try:
            # Initial registration
            await mgr.discover_and_register()
            initial_events = len(delta.events)
            assert len(mgr.server_capabilities.get("calendar", [])) == 2

            # Refresh
            result = await mgr.refresh("calendar")
            assert result.registered == 2
            # Should have emitted unregister + re-register events
            assert len(delta.events) > initial_events
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_refresh_unknown_server(self) -> None:
        """Refresh for a server not in config returns error."""
        yaml = "servers: []"
        mgr, _, _, _, _, path = _make_lifecycle(yaml)
        try:
            result = await mgr.refresh("nonexistent")
            assert result.registered == 0
            assert len(result.errors) == 1
            assert "not found in config" in result.errors[0]
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_refresh_no_old_capabilities(self) -> None:
        """Refresh for a server with no existing capabilities."""
        yaml = """servers:
  - id: fresh_srv
    type: local
    endpoint: /usr/bin/fresh
"""
        tools = {"fresh_srv": [{"name": "new_tool", "description": "New"}]}
        mgr, _, _, _, _, path = _make_lifecycle(yaml, tools)
        try:
            result = await mgr.refresh("fresh_srv")
            assert result.registered == 1
            assert "fresh_srv" in mgr.server_capabilities
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_refresh_clears_old_mapping(self) -> None:
        """After refresh, mapping reflects new tools, not old."""
        yaml = """servers:
  - id: srv
    type: remote
    endpoint: http://srv.local
"""
        # First discovery: 2 tools
        tools = {
            "srv": [
                {"name": "old_tool_1", "description": "Old1"},
                {"name": "old_tool_2", "description": "Old2"},
            ]
        }
        mgr, transport, _, _, _, path = _make_lifecycle(yaml, tools)
        try:
            await mgr.discover_and_register()
            assert len(mgr.server_capabilities["srv"]) == 2

            # Change available tools for refresh
            transport.tools_by_server["srv"] = [
                {"name": "new_tool", "description": "New"},
            ]
            result = await mgr.refresh("srv")
            assert result.registered == 1
            assert len(mgr.server_capabilities["srv"]) == 1
        finally:
            os.unlink(path)


class TestUnregisterServer:
    """unregister_server(server_id) -- remove all capabilities for server."""

    @pytest.mark.asyncio
    async def test_unregister_known_server(self) -> None:
        yaml = """servers:
  - id: weather
    type: remote
    endpoint: http://weather.local
"""
        tools = {
            "weather": [
                {"name": "get_forecast", "description": "Forecast"},
            ]
        }
        mgr, _, _, delta, _, path = _make_lifecycle(yaml, tools)
        try:
            await mgr.discover_and_register()
            assert "weather" in mgr.server_capabilities

            count = await mgr.unregister_server("weather")
            assert count == 1
            assert "weather" not in mgr.server_capabilities
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_unregister_unknown_server(self) -> None:
        yaml = "servers: []"
        mgr, _, _, _, _, path = _make_lifecycle(yaml)
        try:
            count = await mgr.unregister_server("nonexistent")
            assert count == 0
        finally:
            os.unlink(path)


class TestHealthEventHandler:
    """_on_provider_health_changed -- triggers refresh on recovery."""

    def test_recovery_event_schedules_refresh(self) -> None:
        """UNHEALTHY -> HEALTHY for known server triggers pending refresh."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            # Manually set a known server
            mgr.server_capabilities["calendar"] = ["tool.execute.calendar.create"]

            mgr.start_lifecycle_monitoring()
            handler = events.get_handler("k1.fabric.provider.health.changed.v1")
            assert handler is not None

            # Simulate recovery event
            handler(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "calendar",
                    "old_state": "UNHEALTHY",
                    "new_state": "HEALTHY",
                    "reason": "health check passed",
                },
            )

            pending = mgr.get_pending_refreshes()
            assert pending == ["calendar"]
        finally:
            os.unlink(path)

    def test_degraded_to_healthy_also_triggers(self) -> None:
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.server_capabilities["srv_a"] = ["tool.read.srv_a.query"]
            mgr.start_lifecycle_monitoring()
            handler = events.get_handler("k1.fabric.provider.health.changed.v1")

            handler(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "srv_a",
                    "old_state": "DEGRADED",
                    "new_state": "HEALTHY",
                    "reason": "recovered",
                },
            )
            assert mgr.get_pending_refreshes() == ["srv_a"]
        finally:
            os.unlink(path)

    def test_healthy_to_degraded_ignored(self) -> None:
        """Non-recovery transitions don't trigger refresh."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.server_capabilities["srv"] = ["tool.execute.srv.action"]
            mgr.start_lifecycle_monitoring()
            handler = events.get_handler("k1.fabric.provider.health.changed.v1")

            handler(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "srv",
                    "old_state": "HEALTHY",
                    "new_state": "DEGRADED",
                    "reason": "latency spikes",
                },
            )
            assert mgr.get_pending_refreshes() == []
        finally:
            os.unlink(path)

    def test_unknown_provider_ignored(self) -> None:
        """Recovery for a provider not in server_capabilities is ignored."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.start_lifecycle_monitoring()
            handler = events.get_handler("k1.fabric.provider.health.changed.v1")

            handler(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "unknown_provider",
                    "old_state": "UNHEALTHY",
                    "new_state": "HEALTHY",
                    "reason": "recovered",
                },
            )
            assert mgr.get_pending_refreshes() == []
        finally:
            os.unlink(path)

    def test_suffix_match_provider_id(self) -> None:
        """Provider ID with prefix still matches known server_id."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.server_capabilities["calendar"] = ["tool.execute.calendar.create"]
            mgr.start_lifecycle_monitoring()
            handler = events.get_handler("k1.fabric.provider.health.changed.v1")

            handler(
                "k1.fabric.provider.health.changed.v1",
                {
                    "provider_id": "mcp.calendar",
                    "old_state": "UNHEALTHY",
                    "new_state": "HEALTHY",
                    "reason": "recovered",
                },
            )
            assert mgr.get_pending_refreshes() == ["calendar"]
        finally:
            os.unlink(path)

    def test_get_pending_refreshes_clears(self) -> None:
        """Calling get_pending_refreshes() clears the list."""
        yaml = "servers: []"
        mgr, _, _, _, events, path = _make_lifecycle(yaml)
        try:
            mgr.server_capabilities["srv"] = ["cap1"]
            mgr.start_lifecycle_monitoring()
            handler = events.get_handler("k1.fabric.provider.health.changed.v1")

            handler(
                "k1.fabric.provider.health.changed.v1",
                {"provider_id": "srv", "old_state": "UNHEALTHY", "new_state": "HEALTHY"},
            )
            assert mgr.get_pending_refreshes() == ["srv"]
            # Second call returns empty -- cleared
            assert mgr.get_pending_refreshes() == []
        finally:
            os.unlink(path)


class TestServerMapping:
    """server_capabilities tracking via get_server_ids() / get_capabilities()."""

    @pytest.mark.asyncio
    async def test_get_server_ids(self) -> None:
        yaml = """servers:
  - id: a
    type: local
    endpoint: /a
  - id: b
    type: remote
    endpoint: http://b
"""
        tools = {
            "a": [{"name": "t1", "description": "T1"}],
            "b": [{"name": "t2", "description": "T2"}],
        }
        mgr, _, _, _, _, path = _make_lifecycle(yaml, tools)
        try:
            await mgr.discover_and_register()
            ids = mgr.get_server_ids()
            assert sorted(ids) == ["a", "b"]
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_get_capabilities_for_server(self) -> None:
        yaml = """servers:
  - id: cal
    type: remote
    endpoint: http://cal
"""
        tools = {
            "cal": [
                {"name": "create_event", "description": "Create"},
                {"name": "list_events", "description": "List"},
            ]
        }
        mgr, _, _, _, _, path = _make_lifecycle(yaml, tools)
        try:
            await mgr.discover_and_register()
            caps = mgr.get_capabilities("cal")
            assert len(caps) == 2
            assert all(c.startswith("tool.") for c in caps)
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_no_duplicate_cap_ids_on_repeat(self) -> None:
        """Calling discover_and_register twice doesn't duplicate mapping entries."""
        yaml = """servers:
  - id: srv
    type: local
    endpoint: /srv
"""
        tools = {"srv": [{"name": "tool_a", "description": "A"}]}
        mgr, _, _, _, _, path = _make_lifecycle(yaml, tools)
        try:
            await mgr.discover_and_register()
            await mgr.discover_and_register()
            assert len(mgr.server_capabilities["srv"]) == 1
        finally:
            os.unlink(path)


# ===========================================================================
# 5.1.4 -- K0ProxyClient
# ===========================================================================


class TestProxyRequest:
    """ProxyRequest dataclass."""

    def test_defaults(self) -> None:
        req = ProxyRequest(server_id="srv", tool_name="get_data")
        assert req.params == {}
        assert req.auth_context is None

    def test_with_auth_context(self) -> None:
        req = ProxyRequest(
            server_id="srv",
            tool_name="get_data",
            params={"key": "value"},
            auth_context={"token": "abc"},
        )
        assert req.auth_context == {"token": "abc"}
        assert req.params == {"key": "value"}

    def test_frozen(self) -> None:
        req = ProxyRequest(server_id="s", tool_name="t")
        with pytest.raises(AttributeError):
            req.server_id = "other"  # type: ignore[misc]


class TestProxyResponse:
    """ProxyResponse dataclass."""

    def test_defaults(self) -> None:
        resp = ProxyResponse()
        assert resp.data == {}
        assert resp.cached is False
        assert resp.cache_ttl_s == 0

    def test_with_data(self) -> None:
        resp = ProxyResponse(data={"result": 42}, cached=True, cache_ttl_s=300)
        assert resp.data == {"result": 42}
        assert resp.cached is True
        assert resp.cache_ttl_s == 300


class TestK0ProxyClientDisabled:
    """K0ProxyClient with no endpoint -- entirely disabled."""

    def test_is_available_false(self) -> None:
        client = K0ProxyClient(bridge=FakeBridgePort(), proxy_endpoint=None)
        assert client.is_available() is False

    @pytest.mark.asyncio
    async def test_invoke_raises_unavailable(self) -> None:
        client = K0ProxyClient(bridge=FakeBridgePort(), proxy_endpoint=None)
        with pytest.raises(ProxyUnavailableError, match="standalone"):
            await client.invoke_via_proxy(
                ProxyRequest(server_id="srv", tool_name="t"),
            )

    @pytest.mark.asyncio
    async def test_health_check_returns_false(self) -> None:
        client = K0ProxyClient(bridge=FakeBridgePort(), proxy_endpoint=None)
        assert await client.check_proxy_health() is False

    @pytest.mark.asyncio
    async def test_no_transport_raises_unavailable(self) -> None:
        """Endpoint set but no transport still raises unavailable."""
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=None,
        )
        with pytest.raises(ProxyUnavailableError, match="No transport"):
            await client.invoke_via_proxy(
                ProxyRequest(server_id="srv", tool_name="t"),
            )


class TestK0ProxyClientInvoke:
    """invoke_via_proxy() -- success, 401, 429, errors."""

    @pytest.mark.asyncio
    async def test_invoke_success(self) -> None:
        transport = FakeProxyTransport(
            post_response={
                "status": 200,
                "body": {"data": {"weather": "sunny"}, "cached": False, "cache_ttl_s": 0},
                "headers": {},
            },
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        resp = await client.invoke_via_proxy(
            ProxyRequest(server_id="weather", tool_name="get_forecast", params={"city": "SF"}),
        )
        assert resp.data == {"weather": "sunny"}
        assert resp.cached is False

        # Verify correct URL was called
        assert len(transport.post_calls) == 1
        url, body = transport.post_calls[0]
        assert url == "http://proxy.local/mcp/invoke"
        assert body["server_id"] == "weather"
        assert body["tool_name"] == "get_forecast"

    @pytest.mark.asyncio
    async def test_invoke_with_auth_context(self) -> None:
        transport = FakeProxyTransport(
            post_response={"status": 200, "body": {"data": {}}, "headers": {}},
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        await client.invoke_via_proxy(
            ProxyRequest(
                server_id="srv",
                tool_name="t",
                auth_context={"token": "xyz"},
            ),
        )
        _, body = transport.post_calls[0]
        assert body["auth_context"] == {"token": "xyz"}

    @pytest.mark.asyncio
    async def test_invoke_401_triggers_token_refresh(self) -> None:
        """HTTP 401 triggers token refresh via bridge and raises."""
        transport = FakeProxyTransport(
            post_response={"status": 401, "body": {}, "headers": {}},
        )
        bridge = FakeBridgePort()
        client = K0ProxyClient(
            bridge=bridge,
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        with pytest.raises(RuntimeError, match="401"):
            await client.invoke_via_proxy(
                ProxyRequest(server_id="secure_srv", tool_name="t"),
            )
        # Bridge should have received a token refresh request
        assert len(bridge.audits) == 1
        manifest, _ = bridge.audits[0]
        assert manifest["type"] == "token_refresh_request"
        assert manifest["server_id"] == "secure_srv"

    @pytest.mark.asyncio
    async def test_invoke_429_raises_rate_limited(self) -> None:
        """HTTP 429 raises ProxyRateLimitedError with retry_after."""
        transport = FakeProxyTransport(
            post_response={
                "status": 429,
                "body": {"retry_after_s": 30},
                "headers": {"Retry-After": "30"},
            },
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        with pytest.raises(ProxyRateLimitedError) as exc_info:
            await client.invoke_via_proxy(
                ProxyRequest(server_id="srv", tool_name="t"),
            )
        assert exc_info.value.retry_after_s == 30.0

    @pytest.mark.asyncio
    async def test_invoke_500_raises_runtime_error(self) -> None:
        transport = FakeProxyTransport(
            post_response={"status": 500, "body": {"error": "internal"}, "headers": {}},
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        with pytest.raises(RuntimeError, match="500"):
            await client.invoke_via_proxy(
                ProxyRequest(server_id="srv", tool_name="t"),
            )

    @pytest.mark.asyncio
    async def test_invoke_transport_error(self) -> None:
        """Transport exception wraps in RuntimeError."""
        transport = FakeProxyTransport(post_error=ConnectionError("timeout"))
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        with pytest.raises(RuntimeError, match="timeout"):
            await client.invoke_via_proxy(
                ProxyRequest(server_id="srv", tool_name="t"),
            )

    @pytest.mark.asyncio
    async def test_invoke_cached_response(self) -> None:
        transport = FakeProxyTransport(
            post_response={
                "status": 200,
                "body": {"data": {"temp": 72}, "cached": True, "cache_ttl_s": 600},
                "headers": {},
            },
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        resp = await client.invoke_via_proxy(
            ProxyRequest(server_id="weather", tool_name="get"),
        )
        assert resp.cached is True
        assert resp.cache_ttl_s == 600


class TestK0ProxyClientHealth:
    """check_proxy_health() -- lightweight health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        transport = FakeProxyTransport(
            get_response={"status": 200, "body": {"healthy": True}},
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        assert await client.check_proxy_health() is True
        assert transport.get_calls == ["http://proxy.local/health"]

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        transport = FakeProxyTransport(
            get_response={"status": 503, "body": {}},
        )
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        assert await client.check_proxy_health() is False

    @pytest.mark.asyncio
    async def test_health_check_transport_error(self) -> None:
        transport = FakeProxyTransport(get_error=ConnectionError("DNS"))
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=transport,
        )
        assert await client.check_proxy_health() is False

    @pytest.mark.asyncio
    async def test_health_check_no_transport(self) -> None:
        client = K0ProxyClient(
            bridge=FakeBridgePort(),
            proxy_endpoint="http://proxy.local",
            transport=None,
        )
        assert await client.check_proxy_health() is False


class TestProxyErrors:
    """ProxyUnavailableError, ProxyRateLimitedError."""

    def test_unavailable_error(self) -> None:
        err = ProxyUnavailableError("test message")
        assert str(err) == "test message"
        assert isinstance(err, RuntimeError)

    def test_rate_limited_error(self) -> None:
        err = ProxyRateLimitedError(retry_after_s=45.0)
        assert err.retry_after_s == 45.0
        assert "45.0s" in str(err)

    def test_rate_limited_error_custom_message(self) -> None:
        err = ProxyRateLimitedError(retry_after_s=10.0, message="custom")
        assert str(err) == "custom"
        assert err.retry_after_s == 10.0


class TestConnectorAllReExports:
    """__init__ re-exports all 5.1.x types."""

    def test_all_513_exports(self) -> None:
        from k1.orchestrator.connectors import ConnectorLifecycleManager as CLM

        assert CLM is not None

    def test_all_514_exports(self) -> None:
        from k1.orchestrator.connectors import K0ProxyClient as KPC
        from k1.orchestrator.connectors import ProxyRateLimitedError as PRLE
        from k1.orchestrator.connectors import ProxyRequest as PR
        from k1.orchestrator.connectors import ProxyResponse as PRsp
        from k1.orchestrator.connectors import ProxyUnavailableError as PUE

        assert all(x is not None for x in [KPC, PR, PRsp, PUE, PRLE])

    def test_all_exports_complete(self) -> None:
        import k1.orchestrator.connectors as mod

        expected = {
            "MCPToolDiscovery",
            "MCPServerConfig",
            "DiscoveredTool",
            "DiscoveryResult",
            "IMCPTransportDiscovery",
            "MCPRegistrationBridge",
            "RegistrationResult",
            "build_capability_id",
            "infer_type",
            "ConnectorLifecycleManager",
            "K0ProxyClient",
            "ProxyRequest",
            "ProxyResponse",
            "ProxyUnavailableError",
            "ProxyRateLimitedError",
        }
        assert expected.issubset(set(mod.__all__))
