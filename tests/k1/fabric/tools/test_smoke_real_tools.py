"""
Smoke test -- Call REAL tools through the full Fabric pipeline and get output.

This is NOT canned/mocked. It wires AutoDiscoveryMCPTransport and
AutoDiscoveryWASMRuntime into the Fabric, calls real MCP servers and
WASM executors, and asserts on the actual returned data.

Tools exercised:
  MCP (JSON-RPC): calendar_list_events, calendar_create_event, calendar_delete_event
  MCP (JSON-RPC): weather_current, weather_forecast
  MCP (FastMCP):  notes_create, notes_list, notes_search
  MCP (FastMCP):  recipe_search, recipe_meal_plan
  WASM:           date_calc (days_between, add_days, weekday, is_weekend)
  WASM:           unit_convert (temperature, length, weight, volume)

Run:
  python -m pytest tests/k1/fabric/tools/test_smoke_real_tools.py -v -s
"""

from __future__ import annotations

import pytest

from k1.fabric.adapters.auto_mcp_transport import AutoDiscoveryMCPTransport
from k1.fabric.adapters.auto_wasm_runtime import AutoDiscoveryWASMRuntime
from k1.fabric.factory import FabricFactory
from k1.fabric.types import CapabilityRequest

# ---------------------------------------------------------------------------
# Fixtures -- real adapters, real fabric
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_transport():
    """Auto-discovery MCP transport wired to k1/tools/mcp_servers/."""
    return AutoDiscoveryMCPTransport()


@pytest.fixture(scope="module")
def wasm_runtime():
    """Auto-discovery WASM runtime wired to k1/tools/wasm_modules/."""
    return AutoDiscoveryWASMRuntime()


@pytest.fixture(scope="module")
def fabric(mcp_transport, wasm_runtime):
    """Fully wired Fabric with real tool backends."""
    return FabricFactory.create_for_testing(
        mcp_transport=mcp_transport,
        wasm_runtime=wasm_runtime,
    )


# =========================================================================
# MCP -- Calendar (JSON-RPC)
# =========================================================================


class TestSmokeCalendar:
    """Real calls to the calendar MCP server via Fabric."""

    @pytest.mark.asyncio
    async def test_list_events_returns_data(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.calendar_list_events",
                params={"start_date": "2025-06-01", "end_date": "2025-06-30"},
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert "events" in result.data, f"Missing 'events' key. Got: {result.data}"
        assert isinstance(result.data["events"], list)
        print(f"\n  >> calendar_list_events => {result.data}")

    @pytest.mark.asyncio
    async def test_create_event_returns_id(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.write.calendar_create_event",
                params={
                    "title": "Smoke Test Event",
                    "start_time": "2025-06-15T10:00:00",
                    "end_time": "2025-06-15T11:00:00",
                    "location": "Test Room",
                },
                caller="smoke_test",
                safety_band="AMBER",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert (
            "event_id" in result.data or "status" in result.data
        ), f"Unexpected data shape: {result.data}"
        print(f"\n  >> calendar_create_event => {result.data}")

    @pytest.mark.asyncio
    async def test_delete_event(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.write.calendar_delete_event",
                params={"event_id": "nonexistent-id"},
                caller="smoke_test",
                safety_band="AMBER",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert "status" in result.data, f"Unexpected data shape: {result.data}"
        print(f"\n  >> calendar_delete_event => {result.data}")


# =========================================================================
# MCP -- Weather (JSON-RPC)
# =========================================================================


class TestSmokeWeather:
    """Real calls to the weather MCP server via Fabric."""

    @pytest.mark.asyncio
    async def test_current_weather(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.weather_current",
                params={"location": "San Francisco"},
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert (
            "temperature" in result.data or "conditions" in result.data
        ), f"Unexpected data: {result.data}"
        print(f"\n  >> weather_current => {result.data}")

    @pytest.mark.asyncio
    async def test_weather_forecast(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.weather_forecast",
                params={"location": "New York", "days": 3},
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert "forecast" in result.data or "days" in result.data, f"Unexpected data: {result.data}"
        print(f"\n  >> weather_forecast => {result.data}")


# =========================================================================
# MCP -- Notes (FastMCP)
# =========================================================================


class TestSmokeNotes:
    """Real calls to the notes FastMCP server via Fabric."""

    @pytest.mark.asyncio
    async def test_create_note(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.write.notes_create",
                params={
                    "title": "Smoke Test Note",
                    "content": "This is a smoke test note.",
                    "tags": "test,smoke",
                },
                caller="smoke_test",
                safety_band="AMBER",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert (
            "note_id" in result.data or "status" in result.data
        ), f"Unexpected data: {result.data}"
        print(f"\n  >> notes_create => {result.data}")

    @pytest.mark.asyncio
    async def test_list_notes(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.notes_list",
                params={},
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert "notes" in result.data, f"Missing 'notes' key. Got: {result.data}"
        print(f"\n  >> notes_list => {result.data}")

    @pytest.mark.asyncio
    async def test_search_notes(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.notes_search",
                params={"query": "smoke"},
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert "notes" in result.data or "results" in result.data, f"Unexpected data: {result.data}"
        print(f"\n  >> notes_search => {result.data}")


# =========================================================================
# MCP -- Recipes (FastMCP)
# =========================================================================


class TestSmokeRecipes:
    """Real calls to the recipes FastMCP server via Fabric."""

    @pytest.mark.asyncio
    async def test_search_recipes(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.read.recipe_search",
                params={"query": "pasta", "max_results": 3},
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert (
            "recipes" in result.data or "results" in result.data
        ), f"Unexpected data: {result.data}"
        print(f"\n  >> recipe_search => {result.data}")

    @pytest.mark.asyncio
    async def test_meal_plan(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.write.recipe_meal_plan",
                params={"days": 3, "servings": 2, "dietary": "vegetarian"},
                caller="smoke_test",
                safety_band="AMBER",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        print(f"\n  >> recipe_meal_plan => {result.data}")


# =========================================================================
# WASM -- date_calc
# =========================================================================


class TestSmokeDateCalc:
    """Real calls to the date_calc WASM executor via Fabric."""

    @pytest.mark.asyncio
    async def test_days_between(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.date_calc",
                params={
                    "operation": "days_between",
                    "date": "2025-01-01",
                    "date2": "2025-12-31",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert result.data.get("result") == 364, f"Expected 364, got: {result.data}"
        print(f"\n  >> date_calc.days_between => {result.data}")

    @pytest.mark.asyncio
    async def test_add_days(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.date_calc",
                params={
                    "operation": "add_days",
                    "date": "2025-06-01",
                    "days": 30,
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert result.data.get("result") == "2025-07-01", f"Got: {result.data}"
        print(f"\n  >> date_calc.add_days => {result.data}")

    @pytest.mark.asyncio
    async def test_weekday(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.date_calc",
                params={
                    "operation": "weekday",
                    "date": "2025-02-08",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert result.data.get("result") == "Saturday", f"Got: {result.data}"
        print(f"\n  >> date_calc.weekday => {result.data}")

    @pytest.mark.asyncio
    async def test_is_weekend(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.date_calc",
                params={
                    "operation": "is_weekend",
                    "date": "2025-02-08",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert result.data.get("result") is True, f"Got: {result.data}"
        print(f"\n  >> date_calc.is_weekend => {result.data}")


# =========================================================================
# WASM -- unit_convert
# =========================================================================


class TestSmokeUnitConvert:
    """Real calls to the unit_convert WASM executor via Fabric."""

    @pytest.mark.asyncio
    async def test_celsius_to_fahrenheit(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.unit_convert",
                params={
                    "category": "temperature",
                    "value": 100,
                    "from_unit": "celsius",
                    "to_unit": "fahrenheit",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        assert result.data.get("result") == 212.0, f"Got: {result.data}"
        print(f"\n  >> unit_convert.temperature C->F => {result.data}")

    @pytest.mark.asyncio
    async def test_meters_to_feet(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.unit_convert",
                params={
                    "category": "distance",
                    "value": 1,
                    "from_unit": "meter",
                    "to_unit": "foot",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        val = result.data.get("result")
        assert abs(val - 3.28084) < 0.001, f"Got: {result.data}"
        print(f"\n  >> unit_convert.distance m->ft => {result.data}")

    @pytest.mark.asyncio
    async def test_kg_to_pounds(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.unit_convert",
                params={
                    "category": "weight",
                    "value": 1,
                    "from_unit": "kilogram",
                    "to_unit": "pound",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        val = result.data.get("result")
        assert abs(val - 2.20462) < 0.001, f"Got: {result.data}"
        print(f"\n  >> unit_convert.weight kg->lb => {result.data}")

    @pytest.mark.asyncio
    async def test_liters_to_gallons(self, fabric) -> None:
        result = await fabric.execute(
            CapabilityRequest(
                capability_name="tool.execute.unit_convert",
                params={
                    "category": "volume",
                    "value": 1,
                    "from_unit": "liter",
                    "to_unit": "gallon",
                },
                caller="smoke_test",
            )
        )
        assert result.success, f"FAILED: {result.error}"
        val = result.data.get("result")
        assert abs(val - 0.264172) < 0.001, f"Got: {result.data}"
        print(f"\n  >> unit_convert.volume L->gal => {result.data}")
