"""
Tests for MCP Connector Lifecycle -- 5.1.1 + 5.1.2.

5.1.1 MCPToolDiscovery:
  TestMCPServerConfig            -- Dataclass validation.
  TestDiscoveredTool             -- Dataclass identity.
  TestMCPToolDiscoveryConfig     -- YAML loading, validation, edge cases.
  TestMCPToolDiscoveryDiscover   -- discover_server, discover_all, errors.

5.1.2 MCPRegistrationBridge:
  TestInferType                  -- Tool type heuristic.
  TestBuildCapabilityId          -- Naming convention.
  TestMCPRegistrationBridge      -- register_tools, collision, errors, unregister.

  TestConnectorReExports         -- __init__ re-exports.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import pytest

from k1.orchestrator.connectors.mcp_discovery import (
    DiscoveredTool,
    DiscoveryResult,
    MCPServerConfig,
    MCPToolDiscovery,
)
from k1.orchestrator.connectors.mcp_registrar import (
    MCPRegistrationBridge,
    RegistrationResult,
    build_capability_id,
    infer_type,
)
from k1.orchestrator.types import RegistryEntry

# ===========================================================================
# Fakes
# ===========================================================================


class FakeTransport:
    """Fake IMCPTransportDiscovery that returns canned tool lists."""

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

# ===========================================================================
# Helpers
# ===========================================================================


def _write_yaml(content: str) -> str:
    """Write YAML content to a temp file. Returns path."""
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
        availability="ONLINE",
    )


# ===========================================================================
# 5.1.1 Tests -- MCPServerConfig
# ===========================================================================


class TestMCPServerConfig:
    """Server config validation."""

    def test_valid_local(self) -> None:
        cfg = MCPServerConfig(id="fs", type="local", endpoint="/usr/bin/mcp-fs")
        assert cfg.validate() == []

    def test_valid_remote(self) -> None:
        cfg = MCPServerConfig(id="cal", type="remote", endpoint="https://mcp.example.com")
        assert cfg.validate() == []

    def test_missing_id(self) -> None:
        cfg = MCPServerConfig(id="", type="local", endpoint="/bin/x")
        errors = cfg.validate()
        assert len(errors) == 1
        assert "id" in errors[0]

    def test_invalid_type(self) -> None:
        cfg = MCPServerConfig(id="x", type="grpc", endpoint="localhost")
        errors = cfg.validate()
        assert len(errors) == 1
        assert "type" in errors[0]

    def test_missing_endpoint(self) -> None:
        cfg = MCPServerConfig(id="x", type="local", endpoint="")
        errors = cfg.validate()
        assert len(errors) == 1
        assert "endpoint" in errors[0]

    def test_critical_default_false(self) -> None:
        cfg = MCPServerConfig(id="x", type="local", endpoint="y")
        assert cfg.critical is False


# ===========================================================================
# 5.1.1 Tests -- DiscoveredTool
# ===========================================================================


class TestDiscoveredTool:
    """DiscoveredTool identity."""

    def test_basic(self) -> None:
        tool = _tool()
        assert tool.server_id == "weather_api"
        assert tool.name == "get_weather"
        assert tool.description == "Get weather info"

    def test_output_schema_default_none(self) -> None:
        tool = DiscoveredTool(server_id="x", name="y", description="z")
        assert tool.output_schema is None

    def test_frozen(self) -> None:
        tool = _tool()
        with pytest.raises(AttributeError):
            tool.name = "other"  # type: ignore[misc]


# ===========================================================================
# 5.1.1 Tests -- MCPToolDiscovery config loading
# ===========================================================================


class TestMCPToolDiscoveryConfig:
    """YAML loading, validation, edge cases."""

    def test_load_valid_config(self) -> None:
        yaml_content = """\
servers:
  - id: weather
    type: remote
    endpoint: https://weather.mcp.io
  - id: local_fs
    type: local
    endpoint: /usr/bin/mcp-fs
    critical: true
"""
        path = _write_yaml(yaml_content)
        try:
            discovery = MCPToolDiscovery(config_path=path)
            configs = discovery.load_config()
            assert len(configs) == 2
            assert configs[0].id == "weather"
            assert configs[0].type == "remote"
            assert configs[0].critical is False
            assert configs[1].id == "local_fs"
            assert configs[1].type == "local"
            assert configs[1].critical is True
        finally:
            os.unlink(path)

    def test_load_file_not_found(self) -> None:
        discovery = MCPToolDiscovery(config_path="/nonexistent/path.yaml")
        with pytest.raises(FileNotFoundError):
            discovery.load_config()

    def test_load_invalid_yaml_structure(self) -> None:
        path = _write_yaml("just a string")
        try:
            discovery = MCPToolDiscovery(config_path=path)
            with pytest.raises(ValueError, match="YAML mapping"):
                discovery.load_config()
        finally:
            os.unlink(path)

    def test_load_invalid_servers_not_list(self) -> None:
        path = _write_yaml("servers: not_a_list")
        try:
            discovery = MCPToolDiscovery(config_path=path)
            with pytest.raises(ValueError, match="list"):
                discovery.load_config()
        finally:
            os.unlink(path)

    def test_load_skips_invalid_entries(self) -> None:
        yaml_content = """\
servers:
  - id: valid
    type: local
    endpoint: /bin/x
  - id: ""
    type: local
    endpoint: /bin/y
  - id: bad_type
    type: grpc
    endpoint: /bin/z
"""
        path = _write_yaml(yaml_content)
        try:
            discovery = MCPToolDiscovery(config_path=path)
            configs = discovery.load_config()
            assert len(configs) == 1
            assert configs[0].id == "valid"
        finally:
            os.unlink(path)

    def test_load_empty_servers(self) -> None:
        path = _write_yaml("servers: []")
        try:
            discovery = MCPToolDiscovery(config_path=path)
            configs = discovery.load_config()
            assert configs == []
        finally:
            os.unlink(path)

    def test_load_missing_servers_key(self) -> None:
        path = _write_yaml("other_key: value")
        try:
            discovery = MCPToolDiscovery(config_path=path)
            configs = discovery.load_config()
            assert configs == []
        finally:
            os.unlink(path)


# ===========================================================================
# 5.1.1 Tests -- MCPToolDiscovery discover
# ===========================================================================


class TestMCPToolDiscoveryDiscover:
    """discover_server, discover_all, errors."""

    @pytest.mark.asyncio
    async def test_discover_server_returns_tools(self) -> None:
        transport = FakeTransport(
            tools_by_server={
                "cal": [
                    {"name": "create_event", "description": "Create calendar event"},
                    {"name": "list_events", "description": "List events"},
                ]
            }
        )
        discovery = MCPToolDiscovery(config_path="unused", transport=transport)
        server = MCPServerConfig(id="cal", type="remote", endpoint="https://mcp.cal.io")

        tools = await discovery.discover_server(server)
        assert len(tools) == 2
        assert tools[0].name == "create_event"
        assert tools[0].server_id == "cal"
        assert tools[1].name == "list_events"

    @pytest.mark.asyncio
    async def test_discover_server_skips_empty_name(self) -> None:
        transport = FakeTransport(tools_by_server={"x": [{"name": "", "description": "No name"}]})
        discovery = MCPToolDiscovery(config_path="unused", transport=transport)
        server = MCPServerConfig(id="x", type="local", endpoint="/bin/x")

        tools = await discovery.discover_server(server)
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_discover_server_no_transport(self) -> None:
        discovery = MCPToolDiscovery(config_path="unused", transport=None)
        server = MCPServerConfig(id="x", type="local", endpoint="/bin/x")

        tools = await discovery.discover_server(server)
        assert tools == []

    @pytest.mark.asyncio
    async def test_discover_server_parses_input_schema(self) -> None:
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}
        transport = FakeTransport(
            tools_by_server={
                "search": [
                    {
                        "name": "search",
                        "description": "Search",
                        "inputSchema": schema,
                    }
                ]
            }
        )
        discovery = MCPToolDiscovery(config_path="unused", transport=transport)
        server = MCPServerConfig(id="search", type="remote", endpoint="https://search.io")

        tools = await discovery.discover_server(server)
        assert tools[0].input_schema == schema

    @pytest.mark.asyncio
    async def test_discover_all_aggregates(self) -> None:
        yaml_content = """\
servers:
  - id: a
    type: local
    endpoint: /bin/a
  - id: b
    type: remote
    endpoint: https://b.io
"""
        path = _write_yaml(yaml_content)
        try:
            transport = FakeTransport(
                tools_by_server={
                    "a": [{"name": "tool_a", "description": "A"}],
                    "b": [{"name": "tool_b", "description": "B"}],
                }
            )
            discovery = MCPToolDiscovery(config_path=path, transport=transport)
            result = await discovery.discover_all()
            assert result.servers_ok == 2
            assert result.servers_failed == 0
            assert len(result.tools) == 2
            assert result.errors == []
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_discover_all_partial_failure(self) -> None:
        yaml_content = """\
servers:
  - id: ok
    type: local
    endpoint: /bin/ok
  - id: broken
    type: remote
    endpoint: https://broken.io
"""
        path = _write_yaml(yaml_content)
        try:
            transport = FakeTransport(
                tools_by_server={"ok": [{"name": "t1", "description": "T1"}]},
                error_servers={"broken"},
            )
            discovery = MCPToolDiscovery(config_path=path, transport=transport)
            result = await discovery.discover_all()
            assert result.servers_ok == 1
            assert result.servers_failed == 1
            assert len(result.tools) == 1
            assert len(result.errors) == 1
            assert "broken" in result.errors[0]
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_discover_all_config_error(self) -> None:
        discovery = MCPToolDiscovery(config_path="/no/such/file.yaml")
        result = await discovery.discover_all()
        assert result.servers_ok == 0
        assert result.servers_failed == 0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_discover_all_idempotent(self) -> None:
        yaml_content = """\
servers:
  - id: s
    type: local
    endpoint: /bin/s
"""
        path = _write_yaml(yaml_content)
        try:
            transport = FakeTransport(tools_by_server={"s": [{"name": "t", "description": "T"}]})
            discovery = MCPToolDiscovery(config_path=path, transport=transport)
            r1 = await discovery.discover_all()
            r2 = await discovery.discover_all()
            assert len(r1.tools) == len(r2.tools)
            assert r1.tools[0].name == r2.tools[0].name
        finally:
            os.unlink(path)


# ===========================================================================
# 5.1.2 Tests -- infer_type
# ===========================================================================


class TestInferType:
    """Tool type heuristic."""

    def test_read_prefixes(self) -> None:
        for prefix in ("get", "query", "search", "list", "find", "fetch", "read", "lookup"):
            tool = _tool(name=f"{prefix}_something")
            assert infer_type(tool) == "read", f"Expected 'read' for prefix '{prefix}'"

    def test_write_prefixes(self) -> None:
        for prefix in ("create", "update", "delete", "remove", "set", "put", "post", "patch"):
            tool = _tool(name=f"{prefix}_something")
            assert infer_type(tool) == "execute", f"Expected 'execute' for prefix '{prefix}'"

    def test_default_execute(self) -> None:
        tool = _tool(name="run_analysis")
        assert infer_type(tool) == "execute"

    def test_case_insensitive(self) -> None:
        tool = _tool(name="GET_Weather")
        assert infer_type(tool) == "read"


# ===========================================================================
# 5.1.2 Tests -- build_capability_id
# ===========================================================================


class TestBuildCapabilityId:
    """Naming convention."""

    def test_read_tool(self) -> None:
        tool = _tool(name="get_forecast", server_id="weather_api")
        assert build_capability_id(tool) == "tool.read.weather_api.get_forecast"

    def test_execute_tool(self) -> None:
        tool = _tool(name="create_event", server_id="google_cal")
        assert build_capability_id(tool) == "tool.execute.google_cal.create_event"

    def test_default_execute(self) -> None:
        tool = _tool(name="run_job", server_id="batch")
        assert build_capability_id(tool) == "tool.execute.batch.run_job"


# ===========================================================================
# 5.1.2 Tests -- MCPRegistrationBridge
# ===========================================================================


class TestMCPRegistrationBridge:
    """register_tools, collision, errors, unregister."""

    @pytest.mark.asyncio
    async def test_register_new_tools(self) -> None:
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        tools = [
            _tool(name="get_weather", server_id="weather"),
            _tool(name="create_event", server_id="calendar"),
        ]
        result = await bridge.register_tools(tools)

        assert result.registered == 2
        assert result.skipped == 0
        assert result.errors == []
        assert len(delta.events) == 2

    @pytest.mark.asyncio
    async def test_register_skips_existing(self) -> None:
        # Pre-populate Fabric registry with existing capability
        cap_id = "tool.read.weather.get_weather"
        fabric = FakeFabricPort(registry={cap_id: _entry(cap_id)})
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        tools = [_tool(name="get_weather", server_id="weather")]
        result = await bridge.register_tools(tools)

        assert result.registered == 0
        assert result.skipped == 1
        assert len(delta.events) == 0

    @pytest.mark.asyncio
    async def test_register_mixed_new_and_existing(self) -> None:
        cap_id = "tool.read.weather.get_forecast"
        fabric = FakeFabricPort(registry={cap_id: _entry(cap_id)})
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        tools = [
            _tool(name="get_forecast", server_id="weather"),  # exists
            _tool(name="create_event", server_id="calendar"),  # new
        ]
        result = await bridge.register_tools(tools)

        assert result.registered == 1
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_register_empty_list(self) -> None:
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        result = await bridge.register_tools([])
        assert result.registered == 0
        assert result.skipped == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_event_payload_structure(self) -> None:
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        tool = _tool(name="search_docs", server_id="docs_api")
        await bridge.register_tools([tool])

        assert len(delta.events) == 1
        topic, payload, trace_id = delta.events[0]
        assert topic == "k1.mcp.tool.discovered.v1"
        assert payload["tool_name"] == "search_docs"
        assert payload["server_id"] == "docs_api"
        assert payload["tool_description"] == "Get weather info"
        assert "input_schema" in payload
        assert "capability_id" in payload
        assert trace_id  # non-empty

    @pytest.mark.asyncio
    async def test_register_handles_error(self) -> None:
        """Query_registry raises -> treated as error, not crash."""

        class BrokenFabric:
            async def query_registry(self, name: str) -> None:
                raise RuntimeError("Fabric down")

        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=BrokenFabric(), delta=delta)

        tools = [_tool(name="t1", server_id="s1")]
        result = await bridge.register_tools(tools)

        assert result.registered == 0
        assert result.errors
        assert "Fabric down" in result.errors[0]

    @pytest.mark.asyncio
    async def test_unregister_tools(self) -> None:
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        count = await bridge.unregister_tools(
            ["tool.read.weather.get_weather", "tool.execute.cal.create"]
        )
        assert count == 2
        assert len(delta.events) == 2
        assert delta.events[0][0] == "k1.orchestration.mcp.tool_unregistered.v1"

    @pytest.mark.asyncio
    async def test_unregister_empty(self) -> None:
        fabric = FakeFabricPort()
        delta = FakeDeltaPort()
        bridge = MCPRegistrationBridge(fabric=fabric, delta=delta)

        count = await bridge.unregister_tools([])
        assert count == 0


# ===========================================================================
# Re-exports
# ===========================================================================


class TestConnectorReExports:
    """__init__ re-exports."""

    def test_discovery_exports(self) -> None:
        from k1.orchestrator.connectors import DiscoveredTool as DT
        from k1.orchestrator.connectors import DiscoveryResult as DR
        from k1.orchestrator.connectors import MCPServerConfig as MSC
        from k1.orchestrator.connectors import MCPToolDiscovery as MTD

        assert DT is DiscoveredTool
        assert DR is DiscoveryResult
        assert MSC is MCPServerConfig
        assert MTD is MCPToolDiscovery

    def test_registrar_exports(self) -> None:
        from k1.orchestrator.connectors import MCPRegistrationBridge as MRB
        from k1.orchestrator.connectors import RegistrationResult as RR
        from k1.orchestrator.connectors import build_capability_id as bci
        from k1.orchestrator.connectors import infer_type as it

        assert MRB is MCPRegistrationBridge
        assert RR is RegistrationResult
        assert bci is build_capability_id
        assert it is infer_type
        from k1.orchestrator.connectors import (
            build_capability_id as bci,
        )
        from k1.orchestrator.connectors import (
            infer_type as it,
        )

        assert MRB is MCPRegistrationBridge
        assert RR is RegistrationResult
        assert bci is build_capability_id
        assert it is infer_type
