"""
Tests for AutoDiscoveryMCPTransport and AutoDiscoveryWASMRuntime.

Validates:
  - Auto-discovery of MCP servers from k1/tools/mcp_servers/
  - Auto-discovery of WASM executors from k1/tools/wasm_modules/
  - JSON-RPC dispatch (Calendar, Weather)
  - FastMCP dispatch (Notes, Recipes)
  - WASM executor dispatch (date_calc, unit_convert)
  - Handler registration for internal tools
  - Unknown tool error handling
  - Factory integration with wasm_runtime parameter
"""

from __future__ import annotations

import pytest

from k1.fabric.adapters.auto_mcp_transport import AutoDiscoveryMCPTransport
from k1.fabric.adapters.auto_wasm_runtime import AutoDiscoveryWASMRuntime
from k1.fabric.providers.mcp_provider import MCPRequest, MCPResponse
from k1.fabric.providers.wasm_provider import WASMModuleHandle, WASMSandboxConfig

# =========================================================================
# AutoDiscoveryMCPTransport
# =========================================================================


class TestAutoDiscoveryMCPTransportInit:
    """Test server discovery at construction time."""

    def test_discovers_servers(self) -> None:
        """Transport finds all servers in k1/tools/mcp_servers/."""
        transport = AutoDiscoveryMCPTransport()
        # Should have discovered Calendar and Weather (JSON-RPC)
        # and Notes and Recipes (FastMCP)
        total = len(transport._jsonrpc_routes) + len(transport._fastmcp_routes)
        assert total >= 8, (
            f"Expected at least 8 discovered tools, got {total}. "
            f"JSON-RPC: {list(transport._jsonrpc_routes.keys())}, "
            f"FastMCP: {list(transport._fastmcp_routes.keys())}"
        )

    def test_jsonrpc_routes_populated(self) -> None:
        """Calendar and Weather tools appear in JSON-RPC routes."""
        transport = AutoDiscoveryMCPTransport()
        # Calendar tools use full names in TOOLS list
        assert "tool.read.calendar_list_events" in transport._jsonrpc_routes
        assert "tool.write.calendar_create_event" in transport._jsonrpc_routes
        assert "tool.write.calendar_delete_event" in transport._jsonrpc_routes
        # Weather tools
        assert "tool.read.weather_current" in transport._jsonrpc_routes
        assert "tool.read.weather_forecast" in transport._jsonrpc_routes

    def test_fastmcp_routes_populated(self) -> None:
        """Notes and Recipes tools appear in FastMCP routes."""
        transport = AutoDiscoveryMCPTransport()
        # FastMCP tools indexed by function name
        assert "notes_list" in transport._fastmcp_routes
        assert "notes_create" in transport._fastmcp_routes
        assert "notes_search" in transport._fastmcp_routes
        assert "recipe_search" in transport._fastmcp_routes
        assert "recipe_meal_plan" in transport._fastmcp_routes

    def test_is_connected(self) -> None:
        """Transport starts connected."""
        transport = AutoDiscoveryMCPTransport(auto_discover=False)
        assert transport.is_connected()

    def test_nonexistent_dir_doesnt_crash(self) -> None:
        """Non-existent servers dir logs warning but no crash."""
        transport = AutoDiscoveryMCPTransport(
            servers_dir="k1/tools/nonexistent_dir",
        )
        assert len(transport._jsonrpc_routes) == 0
        assert len(transport._fastmcp_routes) == 0


# =========================================================================
# AutoDiscoveryMCPTransport -- Dispatch
# =========================================================================


class TestAutoDiscoveryMCPTransportDispatch:
    """Test actual tool execution through auto-discovered routes."""

    @pytest.fixture
    def transport(self) -> AutoDiscoveryMCPTransport:
        return AutoDiscoveryMCPTransport()

    async def test_calendar_list_events(self, transport: AutoDiscoveryMCPTransport) -> None:
        """Execute calendar_list_events through JSON-RPC route."""
        request = MCPRequest(
            tool_name="tool.read.calendar_list_events",
            arguments={
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
            },
        )
        response = await transport.send(request)
        assert response.success, f"Calendar list failed: {response.error_message}"
        assert len(response.content) > 0

    async def test_weather_current(self, transport: AutoDiscoveryMCPTransport) -> None:
        """Execute weather_current through JSON-RPC route."""
        request = MCPRequest(
            tool_name="tool.read.weather_current",
            arguments={"location": "London"},
        )
        response = await transport.send(request)
        assert response.success, f"Weather current failed: {response.error_message}"
        assert len(response.content) > 0

    async def test_notes_list(self, transport: AutoDiscoveryMCPTransport) -> None:
        """Execute notes_list through FastMCP route."""
        request = MCPRequest(
            tool_name="tool.read.notes_list",
            arguments={},
        )
        response = await transport.send(request)
        assert response.success, f"Notes list failed: {response.error_message}"

    async def test_notes_create(self, transport: AutoDiscoveryMCPTransport) -> None:
        """Execute notes_create through FastMCP route."""
        request = MCPRequest(
            tool_name="tool.write.notes_create",
            arguments={
                "title": "Test Note",
                "content": "Auto-discovery test",
            },
        )
        response = await transport.send(request)
        assert response.success, f"Notes create failed: {response.error_message}"

    async def test_recipe_search(self, transport: AutoDiscoveryMCPTransport) -> None:
        """Execute recipe_search through FastMCP route."""
        request = MCPRequest(
            tool_name="tool.read.recipe_search",
            arguments={"query": "pasta", "max_results": 5},
        )
        response = await transport.send(request)
        assert response.success, f"Recipe search failed: {response.error_message}"

    async def test_unknown_tool_returns_error(self, transport: AutoDiscoveryMCPTransport) -> None:
        """Unknown tool name returns MCPResponse with success=False."""
        request = MCPRequest(
            tool_name="tool.read.nonexistent_tool",
            arguments={},
        )
        response = await transport.send(request)
        assert not response.success
        assert "Unknown tool" in response.error_message

    async def test_metadata_stripped_from_arguments(
        self, transport: AutoDiscoveryMCPTransport
    ) -> None:
        """Fabric metadata keys (_depends_on etc.) are stripped."""
        request = MCPRequest(
            tool_name="tool.read.calendar_list_events",
            arguments={
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
                "_depends_on": ["some_other_tool"],
            },
        )
        response = await transport.send(request)
        assert response.success


# =========================================================================
# AutoDiscoveryMCPTransport -- Handler Registration
# =========================================================================


class TestAutoDiscoveryMCPTransportHandlers:
    """Test explicit handler registration for internal tools."""

    async def test_register_handler(self) -> None:
        """Registered handler is called for matching tool name."""
        transport = AutoDiscoveryMCPTransport(auto_discover=False)

        async def my_handler(request: MCPRequest) -> MCPResponse:
            return MCPResponse(
                success=True,
                content=[{"type": "text", "text": "handled"}],
            )

        transport.register_handler("tool.write.build_agent", my_handler)

        request = MCPRequest(
            tool_name="tool.write.build_agent",
            arguments={"agent_name": "test"},
        )
        response = await transport.send(request)
        assert response.success
        assert response.content[0]["text"] == "handled"

    async def test_handler_priority_over_server(self) -> None:
        """Explicit handlers take priority over auto-discovered servers."""
        transport = AutoDiscoveryMCPTransport()

        # Register handler for a tool that also exists on a server
        async def override_handler(request: MCPRequest) -> MCPResponse:
            return MCPResponse(
                success=True,
                content=[{"type": "text", "text": "overridden"}],
            )

        transport.register_handler("tool.read.calendar_list_events", override_handler)

        request = MCPRequest(
            tool_name="tool.read.calendar_list_events",
            arguments={
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
            },
        )
        response = await transport.send(request)
        assert response.success
        assert response.content[0]["text"] == "overridden"


# =========================================================================
# AutoDiscoveryMCPTransport -- Lifecycle
# =========================================================================


class TestAutoDiscoveryMCPTransportLifecycle:
    """Test connection lifecycle."""

    async def test_ping_returns_true(self) -> None:
        transport = AutoDiscoveryMCPTransport(auto_discover=False)
        assert await transport.ping() is True

    async def test_close_disconnects(self) -> None:
        transport = AutoDiscoveryMCPTransport(auto_discover=False)
        await transport.close()
        assert not transport.is_connected()
        assert await transport.ping() is False


# =========================================================================
# AutoDiscoveryWASMRuntime
# =========================================================================


class TestAutoDiscoveryWASMRuntimeInit:
    """Test WASM module discovery at construction time."""

    def test_discovers_modules(self) -> None:
        """Runtime finds all executors in k1/tools/wasm_modules/."""
        runtime = AutoDiscoveryWASMRuntime()
        assert "date_calc" in runtime._executors
        assert "unit_convert" in runtime._executors

    def test_is_available(self) -> None:
        """Runtime is available when executors are discovered."""
        runtime = AutoDiscoveryWASMRuntime()
        assert runtime.is_available()

    def test_empty_dir_not_available(self) -> None:
        """Runtime is not available when no executors found."""
        runtime = AutoDiscoveryWASMRuntime(
            modules_dir="k1/tools/nonexistent_dir",
        )
        assert not runtime.is_available()

    def test_set_available_toggle(self) -> None:
        """set_available controls availability."""
        runtime = AutoDiscoveryWASMRuntime()
        runtime.set_available(False)
        assert not runtime.is_available()
        runtime.set_available(True)
        assert runtime.is_available()


# =========================================================================
# AutoDiscoveryWASMRuntime -- Module Loading
# =========================================================================


class TestAutoDiscoveryWASMRuntimeLoading:
    """Test module loading and handle caching."""

    async def test_load_known_module(self) -> None:
        """Loading a known module returns a loaded handle."""
        runtime = AutoDiscoveryWASMRuntime()
        handle = await runtime.load_module("modules/date_calc_wasm.wasm")
        assert handle.loaded
        assert "date_calc" in handle.module_id

    async def test_load_unknown_module_raises(self) -> None:
        """Loading an unknown module raises RuntimeError."""
        runtime = AutoDiscoveryWASMRuntime()
        with pytest.raises(RuntimeError, match="Unknown WASM module"):
            await runtime.load_module("modules/nonexistent.wasm")

    async def test_handle_caching(self) -> None:
        """Loading the same module twice returns cached handle."""
        runtime = AutoDiscoveryWASMRuntime()
        h1 = await runtime.load_module("modules/date_calc_wasm.wasm")
        h2 = await runtime.load_module("modules/date_calc_wasm.wasm")
        assert h1 is h2


# =========================================================================
# AutoDiscoveryWASMRuntime -- Execution
# =========================================================================


class TestAutoDiscoveryWASMRuntimeExecution:
    """Test WASM execution through auto-discovered executors."""

    @pytest.fixture
    async def runtime(self) -> AutoDiscoveryWASMRuntime:
        return AutoDiscoveryWASMRuntime()

    async def test_date_calc_days_between(self, runtime: AutoDiscoveryWASMRuntime) -> None:
        """Execute days_between through date_calc executor."""
        handle = await runtime.load_module("modules/date_calc_wasm.wasm")
        result = await runtime.execute(
            handle,
            "execute",
            {"operation": "days_between", "date": "2025-01-01", "date2": "2025-01-31"},
            WASMSandboxConfig(),
        )
        assert result.success, f"date_calc failed: {result.error_message}"
        assert result.output["result"] == 30

    async def test_date_calc_weekday(self, runtime: AutoDiscoveryWASMRuntime) -> None:
        """Execute weekday through date_calc executor."""
        handle = await runtime.load_module("modules/date_calc_wasm.wasm")
        result = await runtime.execute(
            handle,
            "execute",
            {"operation": "weekday", "date": "2025-01-06"},
            WASMSandboxConfig(),
        )
        assert result.success
        assert result.output["result"] == "Monday"

    async def test_unit_convert(self, runtime: AutoDiscoveryWASMRuntime) -> None:
        """Execute unit conversion through unit_convert executor."""
        handle = await runtime.load_module("modules/unit_convert_wasm.wasm")
        result = await runtime.execute(
            handle,
            "execute",
            {
                "category": "temperature",
                "from_unit": "celsius",
                "to_unit": "fahrenheit",
                "value": 100,
            },
            WASMSandboxConfig(),
        )
        assert result.success, f"unit_convert failed: {result.error_message}"
        assert result.output["result"] == pytest.approx(212.0)

    async def test_execution_error_returns_failure(self, runtime: AutoDiscoveryWASMRuntime) -> None:
        """Invalid params produce WASMExecutionResult with success=False."""
        handle = await runtime.load_module("modules/date_calc_wasm.wasm")
        result = await runtime.execute(
            handle,
            "execute",
            {"operation": "days_between", "date": "not-a-date"},
            WASMSandboxConfig(),
        )
        assert not result.success
        assert result.error_message

    async def test_unloaded_handle_returns_failure(self, runtime: AutoDiscoveryWASMRuntime) -> None:
        """Executing with an unloaded handle returns failure."""
        handle = WASMModuleHandle(module_path="test", module_id="test", loaded=False)
        result = await runtime.execute(
            handle,
            "execute",
            {},
            WASMSandboxConfig(),
        )
        assert not result.success
        assert "not loaded" in result.error_message


# =========================================================================
# AutoDiscoveryWASMRuntime -- Manual Registration
# =========================================================================


class TestAutoDiscoveryWASMRuntimeRegistration:
    """Test manual executor registration."""

    async def test_register_custom_executor(self) -> None:
        """Manually registered executor is callable."""
        runtime = AutoDiscoveryWASMRuntime(auto_discover=False)

        def my_executor(params: dict) -> dict:
            return {"result": params.get("x", 0) * 2}

        runtime.register_executor("my_module", my_executor)

        handle = await runtime.load_module("modules/my_module.wasm")
        result = await runtime.execute(
            handle,
            "execute",
            {"x": 21},
            WASMSandboxConfig(),
        )
        assert result.success
        assert result.output["result"] == 42


# =========================================================================
# Factory Integration
# =========================================================================


class TestFactoryAutoDiscoveryIntegration:
    """Test that factory accepts auto-discovery adapters."""

    def test_factory_accepts_wasm_runtime(self) -> None:
        """create_for_testing accepts wasm_runtime parameter."""
        from k1.fabric.factory import FabricFactory

        runtime = AutoDiscoveryWASMRuntime()
        transport = AutoDiscoveryMCPTransport()

        fabric = FabricFactory.create_for_testing(
            mcp_transport=transport,
            wasm_runtime=runtime,
        )
        assert fabric is not None

    async def test_end_to_end_mcp_through_fabric(self) -> None:
        """Full Fabric execute with auto-discovery transport."""
        from k1.fabric.factory import FabricFactory
        from k1.fabric.types import CapabilityRequest

        transport = AutoDiscoveryMCPTransport()
        fabric = FabricFactory.create_for_testing(
            mcp_transport=transport,
        )

        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.calendar_list_events",
                params={
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-31",
                },
            ),
        )
        assert result.success, f"E2E MCP failed: {result.error}"

    async def test_end_to_end_wasm_through_fabric(self) -> None:
        """Full Fabric execute with auto-discovery WASM runtime."""
        from k1.fabric.factory import FabricFactory
        from k1.fabric.types import CapabilityRequest

        runtime = AutoDiscoveryWASMRuntime()
        fabric = FabricFactory.create_for_testing(
            wasm_runtime=runtime,
        )

        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.date_calc",
                params={
                    "operation": "weekday",
                    "date": "2025-01-06",
                },
            ),
        )
        assert result.success, f"E2E WASM failed: {result.error}"
