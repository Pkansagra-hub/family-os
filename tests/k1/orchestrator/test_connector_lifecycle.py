"""ConnectorLifecycleManager tests (Epic 7.1.6) with factory-backed adapters.

All integration tests obtain ConnectorLifecycleManager from
OrchestratorFactory.create_standalone() and script behavior via
real test adapters:
  - MockFabricAdapter
  - TestDeltaAdapter
  - TestEventAdapter
  - MockBridgeAdapter (K0 proxy edge path)

No fake adapter classes are used.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional

import pytest

from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.connectors.connector_lifecycle import ConnectorLifecycleManager
from k1.orchestrator.connectors.k0_proxy_client import (
    K0ProxyClient,
    ProxyRequest,
    ProxyUnavailableError,
)
from k1.orchestrator.connectors.mcp_discovery import MCPServerConfig
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import RegistryEntry


class _Transport:
    """Tiny test transport for MCPToolDiscovery.list_tools()."""

    def __init__(
        self,
        tools_by_server: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        error_servers: Optional[set[str]] = None,
    ) -> None:
        self.tools_by_server = tools_by_server or {}
        self.error_servers = error_servers or set()
        self.calls: List[str] = []

    async def list_tools(self, server: MCPServerConfig) -> List[Dict[str, Any]]:
        self.calls.append(server.id)
        if server.id in self.error_servers:
            raise ConnectionError(f"cannot reach {server.id}")
        return self.tools_by_server.get(server.id, [])


class _ProxyTransport:
    def __init__(self, *, post_response: Optional[Dict[str, Any]] = None) -> None:
        self.post_response = post_response or {"status": 200, "body": {"data": {}}, "headers": {}}
        self.post_calls: List[Dict[str, Any]] = []

    async def post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self.post_calls.append({"url": url, "body": body})
        return self.post_response

    async def get(self, url: str) -> Dict[str, Any]:
        return {"status": 200, "body": {"healthy": True}}


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    lifecycle: ConnectorLifecycleManager = service._connector_lifecycle  # type: ignore[assignment]
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    delta: TestDeltaAdapter = service._delta_port  # type: ignore[assignment]
    event: TestEventAdapter = service._event_port  # type: ignore[assignment]
    bridge: MockBridgeAdapter = service._bridge_port  # type: ignore[assignment]
    return service, lifecycle, fabric, delta, event, bridge


def _yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="MCP",
        safety_band_min="GREEN",
        availability="AVAILABLE",
    )


def _bind_discovery(
    lifecycle: ConnectorLifecycleManager, config_path: str, transport: _Transport
) -> None:
    lifecycle._discovery._config_path = config_path  # type: ignore[attr-defined]
    lifecycle._discovery._transport = transport  # type: ignore[attr-defined]


class TestDiscoveryAndRegistration:
    @pytest.mark.asyncio
    async def test_discover_register_counts_and_mapping(self) -> None:
        _, lifecycle, _, delta, _, _ = await _svc()
        path = _yaml(
            """servers:
  - id: cal
    type: remote
    endpoint: http://cal
  - id: mail
    type: remote
    endpoint: http://mail
"""
        )
        try:
            _bind_discovery(
                lifecycle,
                path,
                _Transport(
                    {
                        "cal": [{"name": "create_event", "description": "Create"}],
                        "mail": [{"name": "search_mail", "description": "Search"}],
                    }
                ),
            )

            result = await lifecycle.discover_and_register()

            assert result.registered == 2
            assert result.skipped == 0
            assert result.errors == []
            delta.assert_emitted("k1.mcp.tool.discovered.v1", 2)
            assert set(lifecycle.get_server_ids()) == {"cal", "mail"}
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_empty_config_discovers_zero(self) -> None:
        _, lifecycle, _, delta, _, _ = await _svc()
        path = _yaml("servers: []")
        try:
            _bind_discovery(lifecycle, path, _Transport())
            result = await lifecycle.discover_and_register()
            assert result.registered == 0
            assert result.skipped == 0
            assert result.errors == []
            assert len(delta.emitted) == 0
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_malformed_config_returns_error(self) -> None:
        _, lifecycle, _, _, _, _ = await _svc()
        path = _yaml("servers: {}")
        try:
            _bind_discovery(lifecycle, path, _Transport())
            result = await lifecycle.discover_and_register()
            assert result.registered == 0
            assert len(result.errors) >= 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_duplicate_capability_is_skipped(self) -> None:
        _, lifecycle, fabric, _, _, _ = await _svc()
        path = _yaml(
            """servers:
  - id: weather
    type: remote
    endpoint: http://weather
"""
        )
        try:
            transport = _Transport(
                {"weather": [{"name": "get_forecast", "description": "Forecast"}]}
            )
            _bind_discovery(lifecycle, path, transport)
            cap_id = "tool.read.weather.get_forecast"
            fabric.register_capability(cap_id, _entry(cap_id))

            result = await lifecycle.discover_and_register()

            assert result.registered == 0
            assert result.skipped == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_event_payload_contract_shape(self) -> None:
        _, lifecycle, _, delta, _, _ = await _svc()
        path = _yaml(
            """servers:
  - id: cal
    type: remote
    endpoint: http://cal
"""
        )
        try:
            _bind_discovery(
                lifecycle,
                path,
                _Transport(
                    {
                        "cal": [
                            {
                                "name": "create_event",
                                "description": "Create",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    }
                ),
            )
            await lifecycle.discover_and_register()

            payload = delta.get_emitted("k1.mcp.tool.discovered.v1")[0]
            assert payload["tool_name"] == "create_event"
            assert payload["tool_description"] == "Create"
            assert payload["server_id"] == "cal"
            assert payload["server_name"] == "cal"
            assert payload["capability_id"].startswith("tool.")
            assert isinstance(payload["input_schema"], dict)
            assert isinstance(payload["output_schema"], dict)
        finally:
            os.unlink(path)


class TestLifecycleMonitoringAndRefresh:
    @pytest.mark.asyncio
    async def test_subscribes_to_provider_health_topic(self) -> None:
        _, lifecycle, _, _, event, _ = await _svc()
        lifecycle.start_lifecycle_monitoring()
        event.assert_subscribed("k1.fabric.provider.health.changed.v1")

    @pytest.mark.asyncio
    async def test_recovery_event_queues_refresh(self) -> None:
        _, lifecycle, _, _, event, _ = await _svc()
        lifecycle.server_capabilities["calendar"] = ["tool.execute.calendar.create_event"]
        lifecycle.start_lifecycle_monitoring()

        event.fire(
            "k1.fabric.provider.health.changed.v1",
            {
                "provider_id": "mcp.calendar",
                "old_state": "DEGRADED",
                "new_state": "HEALTHY",
            },
        )

        assert lifecycle.get_pending_refreshes() == ["calendar"]
        assert lifecycle.get_pending_refreshes() == []

    @pytest.mark.asyncio
    async def test_non_recovery_event_does_not_queue_refresh(self) -> None:
        _, lifecycle, _, _, event, _ = await _svc()
        lifecycle.server_capabilities["calendar"] = ["tool.execute.calendar.create_event"]
        lifecycle.start_lifecycle_monitoring()

        event.fire(
            "k1.fabric.provider.health.changed.v1",
            {
                "provider_id": "calendar",
                "old_state": "HEALTHY",
                "new_state": "DEGRADED",
            },
        )

        assert lifecycle.get_pending_refreshes() == []

    @pytest.mark.asyncio
    async def test_refresh_unregisters_and_reregisters(self) -> None:
        _, lifecycle, _, delta, _, _ = await _svc()
        path = _yaml(
            """servers:
  - id: cal
    type: remote
    endpoint: http://cal
"""
        )
        try:
            transport = _Transport({"cal": [{"name": "create_event", "description": "Create"}]})
            _bind_discovery(lifecycle, path, transport)

            await lifecycle.discover_and_register()
            before = len(delta.emitted)
            result = await lifecycle.refresh("cal")

            assert result.registered == 1
            assert len(delta.emitted) > before
            assert len(lifecycle.get_capabilities("cal")) == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_unregister_server_removes_capabilities(self) -> None:
        _, lifecycle, _, _, _, _ = await _svc()
        path = _yaml(
            """servers:
  - id: mail
    type: remote
    endpoint: http://mail
"""
        )
        try:
            _bind_discovery(lifecycle, path, _Transport({"mail": [{"name": "search_mail"}]}))
            await lifecycle.discover_and_register()

            assert len(lifecycle.get_capabilities("mail")) == 1
            count = await lifecycle.unregister_server("mail")
            assert count == 1
            assert lifecycle.get_capabilities("mail") == []
        finally:
            os.unlink(path)


class TestK0ProxyBridgePath:
    @pytest.mark.asyncio
    async def test_k0_offline_raises_unavailable(self) -> None:
        _, _, _, _, _, bridge = await _svc()
        client = K0ProxyClient(bridge=bridge, proxy_endpoint=None)
        assert client.is_available() is False
        with pytest.raises(ProxyUnavailableError):
            await client.invoke_via_proxy(ProxyRequest(server_id="srv", tool_name="tool"))

    @pytest.mark.asyncio
    async def test_k0_proxy_401_routes_token_refresh_via_bridge(self) -> None:
        _, _, _, _, _, bridge = await _svc()
        client = K0ProxyClient(
            bridge=bridge,
            proxy_endpoint="http://proxy.local",
            transport=_ProxyTransport(post_response={"status": 401, "body": {}, "headers": {}}),
        )

        with pytest.raises(RuntimeError, match="401"):
            await client.invoke_via_proxy(ProxyRequest(server_id="secure_srv", tool_name="do_it"))

        bridge.assert_audit_written(1)
        manifest, trace_id = bridge.audit_log[0]
        assert manifest["type"] == "token_refresh_request"
        assert manifest["server_id"] == "secure_srv"
        assert trace_id == "token-refresh-secure_srv"
