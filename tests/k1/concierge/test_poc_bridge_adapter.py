"""
E6.7.2 — Unit tests for poc_bridge_adapter.py.

Validates POCMockBridgeAdapter implements IBridgePort and dispatches
to POC handler functions correctly.
"""

from __future__ import annotations

import pytest

from k1.concierge.fabric.capability_registry import CapabilityRegistry
from k1.concierge.fabric.poc_bridge_adapter import POCMockBridgeAdapter
from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IBridgePort, IFLRoute

# =====================================================================
# Fixtures
# =====================================================================


def _make_registry() -> CapabilityRegistry:
    """Create a registry with a few test handlers."""
    registry = CapabilityRegistry()

    async def _hotel_search(params: dict) -> dict:
        return {
            "success": True,
            "data": {"hotels": [{"name": "Test Hotel", "location": params.get("location", "")}]},
        }

    async def _weather(params: dict) -> dict:
        return {"success": True, "data": {"temp": 72, "city": params.get("location", "")}}

    async def _failing_handler(params: dict) -> dict:
        raise RuntimeError("Handler crashed")

    registry.register(
        {
            "name": "tool.execute.hotel_search",
            "description": "Search hotels",
            "domain": "travel",
            "required_inputs": ["location"],
            "optional_inputs": [],
            "has_side_effects": False,
            "estimated_cost": "free",
        },
        _hotel_search,
    )
    registry.register(
        {
            "name": "tool.execute.weather_forecast",
            "description": "Get weather",
            "domain": "travel",
            "required_inputs": ["location"],
            "optional_inputs": [],
            "has_side_effects": False,
            "estimated_cost": "free",
        },
        _weather,
    )
    registry.register(
        {
            "name": "tool.execute.failing_cap",
            "description": "Always fails",
            "domain": "test",
            "required_inputs": [],
            "optional_inputs": [],
            "has_side_effects": False,
            "estimated_cost": "free",
        },
        _failing_handler,
    )
    return registry


# =====================================================================
# Structural — satisfies IBridgePort
# =====================================================================


class TestStructural:
    """POCMockBridgeAdapter satisfies IBridgePort protocol."""

    def test_isinstance_check(self) -> None:
        adapter = POCMockBridgeAdapter(CapabilityRegistry())
        assert isinstance(adapter, IBridgePort)

    def test_has_send_command(self) -> None:
        assert hasattr(POCMockBridgeAdapter, "send_command")

    def test_has_query(self) -> None:
        assert hasattr(POCMockBridgeAdapter, "query")

    def test_has_route_ifl(self) -> None:
        assert hasattr(POCMockBridgeAdapter, "route_ifl")

    def test_has_is_available(self) -> None:
        assert hasattr(POCMockBridgeAdapter, "is_available")

    def test_has_get_health(self) -> None:
        assert hasattr(POCMockBridgeAdapter, "get_health")


# =====================================================================
# Availability
# =====================================================================


class TestAvailability:
    """Always available / full health."""

    def test_is_available_true(self) -> None:
        adapter = POCMockBridgeAdapter(CapabilityRegistry())
        assert adapter.is_available() is True

    def test_get_health_available(self) -> None:
        adapter = POCMockBridgeAdapter(CapabilityRegistry())
        health = adapter.get_health()
        assert isinstance(health, BridgeHealth)
        assert health.available is True

    def test_get_health_mode_full(self) -> None:
        adapter = POCMockBridgeAdapter(CapabilityRegistry())
        health = adapter.get_health()
        assert health.mode == "K0_FULL"


# =====================================================================
# send_command — happy path
# =====================================================================


class TestSendCommand:
    """Dispatch via send_command."""

    @pytest.mark.asyncio
    async def test_known_operation_returns_success(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.send_command("tool.execute.hotel_search", {"location": "Paris"})
        assert isinstance(result, BridgeCommandResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_result_data_from_handler(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.send_command("tool.execute.hotel_search", {"location": "Paris"})
        assert "hotels" in result.data.get("data", {}) or "hotels" in result.data

    @pytest.mark.asyncio
    async def test_trace_id_echoed(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.send_command(
            "tool.execute.hotel_search", {"location": "Paris"}, trace_id="t-123"
        )
        assert result.trace_id == "t-123"

    @pytest.mark.asyncio
    async def test_unknown_operation_returns_failure(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.send_command("tool.execute.nonexistent", {})
        assert result.success is False
        assert result.error_code == "not_found"

    @pytest.mark.asyncio
    async def test_handler_exception_returns_failure(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.send_command("tool.execute.failing_cap", {})
        assert result.success is False
        assert result.error_code == "handler_error"
        assert "crashed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_latency_ms_positive(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.send_command("tool.execute.hotel_search", {"location": "Paris"})
        assert result.latency_ms >= 0


# =====================================================================
# query — delegates to send_command
# =====================================================================


class TestQuery:
    """query() delegates to the same handler dispatch."""

    @pytest.mark.asyncio
    async def test_query_dispatches_like_send_command(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.query("tool.execute.weather_forecast", {"location": "NYC"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_query_unknown_fails(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        result = await adapter.query("tool.execute.nonexistent", {})
        assert result.success is False


# =====================================================================
# route_ifl
# =====================================================================


class TestRouteIFL:
    """IFL routing dispatches via address as operation."""

    @pytest.mark.asyncio
    async def test_route_ifl_dispatches(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        route = IFLRoute(
            address="tool.execute.hotel_search",
            namespace="hotel",
            function_name="search",
        )
        result = await adapter.route_ifl(route, {"location": "London"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_route_ifl_unknown_fails(self) -> None:
        adapter = POCMockBridgeAdapter(_make_registry())
        route = IFLRoute(address="tool.execute.unknown", namespace="x", function_name="y")
        result = await adapter.route_ifl(route, {})
        assert result.success is False
        route = IFLRoute(address="tool.execute.unknown", namespace="x", function_name="y")
        result = await adapter.route_ifl(route, {})
        assert result.success is False
