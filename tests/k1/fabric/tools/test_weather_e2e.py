"""
Integration tests for Phase 2 -- Weather MCP Server (SSE).

Tests the full weather tool stack:
  - WeatherData / ForecastDay / ForecastData models (frozen, to_dict, from_dict)
  - WeatherCache (TTL-based, get/put/purge)
  - WeatherAPIClient (deterministic data, temperature conversion)
  - WeatherHandlers (argument validation, caching, delegation)
  - WeatherMCPServer (JSON-RPC routing, MCP protocol)
  - Contract YAML parsing and validation

NO MOCKS -- all tests use real components.

References:
  - fabric_tool_implementation_plan.md Phase 2, Section 4.1
  - tests/k1/fabric/tools/test_calendar_e2e.py (pattern)
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from k1.fabric.contracts import parse_contract
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.types import CapabilityContract
from k1.tools.mcp_servers.weather.api_client import WeatherAPIClient
from k1.tools.mcp_servers.weather.cache import WeatherCache
from k1.tools.mcp_servers.weather.handlers import WeatherHandlers
from k1.tools.mcp_servers.weather.models import ForecastData, ForecastDay, WeatherData
from k1.tools.mcp_servers.weather.server import TOOLS, WeatherMCPServer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "k1" / "contracts" / "tools"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rpc(
    method: str,
    *,
    id: int = 1,
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 request dict."""
    msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


# =========================================================================
# Section 1: WeatherData model
# =========================================================================


class TestWeatherDataModel:
    """WeatherData frozen dataclass behavior."""

    def test_default_construction(self) -> None:
        data = WeatherData()
        assert data.location == ""
        assert data.temperature == 0.0
        assert data.humidity == 0.0
        assert data.wind_speed == 0.0
        assert data.description == ""
        assert data.units == "metric"

    def test_full_construction(self) -> None:
        data = WeatherData(
            location="London",
            temperature=15.0,
            humidity=72.0,
            wind_speed=8.5,
            description="Partly cloudy",
            units="metric",
        )
        assert data.location == "London"
        assert data.temperature == 15.0
        assert data.humidity == 72.0
        assert data.wind_speed == 8.5

    def test_frozen_immutability(self) -> None:
        data = WeatherData(location="Berlin")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            data.location = "Paris"  # type: ignore[misc]

    def test_to_dict_all_fields(self) -> None:
        data = WeatherData(
            location="Tokyo",
            temperature=22.0,
            humidity=65.0,
            wind_speed=12.0,
            description="Clear sky",
            units="metric",
        )
        d = data.to_dict()
        assert d["location"] == "Tokyo"
        assert d["temperature"] == 22.0
        assert d["humidity"] == 65.0
        assert d["wind_speed"] == 12.0
        assert d["description"] == "Clear sky"
        assert d["units"] == "metric"

    def test_from_dict_roundtrip(self) -> None:
        original = {
            "location": "Paris",
            "temperature": 18.5,
            "humidity": 55.0,
            "wind_speed": 6.0,
            "description": "Overcast",
            "units": "imperial",
        }
        data = WeatherData.from_dict(original)
        assert data.location == "Paris"
        assert data.temperature == 18.5
        assert data.units == "imperial"
        # roundtrip
        assert data.to_dict() == original

    def test_from_dict_missing_fields(self) -> None:
        data = WeatherData.from_dict({})
        assert data.location == ""
        assert data.temperature == 0.0
        assert data.units == "metric"


# =========================================================================
# Section 2: ForecastDay / ForecastData models
# =========================================================================


class TestForecastModels:
    """ForecastDay and ForecastData frozen dataclass behavior."""

    def test_forecast_day_default(self) -> None:
        day = ForecastDay()
        assert day.date == ""
        assert day.high == 0.0
        assert day.low == 0.0
        assert day.description == ""

    def test_forecast_day_to_dict(self) -> None:
        day = ForecastDay(date="2025-01-10", high=25.0, low=15.0, description="Sunny")
        d = day.to_dict()
        assert d["date"] == "2025-01-10"
        assert d["high"] == 25.0
        assert d["low"] == 15.0

    def test_forecast_day_from_dict(self) -> None:
        day = ForecastDay.from_dict({"date": "2025-01-11", "high": 20.0, "low": 10.0})
        assert day.date == "2025-01-11"
        assert day.high == 20.0

    def test_forecast_day_frozen(self) -> None:
        day = ForecastDay(date="2025-01-10")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            day.date = "2025-01-11"  # type: ignore[misc]

    def test_forecast_data_default(self) -> None:
        data = ForecastData()
        assert data.location == ""
        assert data.forecast == ()
        assert data.units == "metric"

    def test_forecast_data_to_dict(self) -> None:
        data = ForecastData(
            location="NYC",
            forecast=(
                ForecastDay(date="2025-01-10", high=5.0, low=-2.0, description="Snow"),
                ForecastDay(date="2025-01-11", high=3.0, low=-5.0, description="Cloudy"),
            ),
            units="metric",
        )
        d = data.to_dict()
        assert d["location"] == "NYC"
        assert len(d["forecast"]) == 2
        assert d["forecast"][0]["description"] == "Snow"

    def test_forecast_data_from_dict(self) -> None:
        raw = {
            "location": "LA",
            "forecast": [
                {"date": "2025-01-10", "high": 25.0, "low": 15.0, "description": "Sunny"},
            ],
            "units": "imperial",
        }
        data = ForecastData.from_dict(raw)
        assert data.location == "LA"
        assert len(data.forecast) == 1
        assert data.forecast[0].high == 25.0
        assert data.units == "imperial"

    def test_forecast_data_frozen(self) -> None:
        data = ForecastData(location="Berlin")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            data.location = "Munich"  # type: ignore[misc]


# =========================================================================
# Section 3: WeatherCache
# =========================================================================


class TestWeatherCache:
    """WeatherCache TTL-based caching."""

    def test_put_and_get(self) -> None:
        cache = WeatherCache(ttl_seconds=60.0)
        cache.put(("current", "london", "metric"), {"temp": 15.0})
        assert cache.get(("current", "london", "metric")) == {"temp": 15.0}

    def test_miss_returns_none(self) -> None:
        cache = WeatherCache(ttl_seconds=60.0)
        assert cache.get(("current", "unknown", "metric")) is None

    def test_expired_returns_none(self) -> None:
        cache = WeatherCache(ttl_seconds=0.01)  # 10ms TTL
        cache.put(("current", "london", "metric"), {"temp": 15.0})
        time.sleep(0.02)  # wait past TTL
        assert cache.get(("current", "london", "metric")) is None

    def test_size(self) -> None:
        cache = WeatherCache(ttl_seconds=60.0)
        assert cache.size == 0
        cache.put(("a",), 1)
        cache.put(("b",), 2)
        assert cache.size == 2

    def test_invalidate(self) -> None:
        cache = WeatherCache(ttl_seconds=60.0)
        cache.put(("a",), 1)
        cache.invalidate(("a",))
        assert cache.get(("a",)) is None
        assert cache.size == 0

    def test_invalidate_nonexistent(self) -> None:
        cache = WeatherCache(ttl_seconds=60.0)
        cache.invalidate(("nope",))  # should not raise

    def test_clear(self) -> None:
        cache = WeatherCache(ttl_seconds=60.0)
        cache.put(("a",), 1)
        cache.put(("b",), 2)
        cache.clear()
        assert cache.size == 0

    def test_purge_expired(self) -> None:
        cache = WeatherCache(ttl_seconds=0.01)
        cache.put(("a",), 1)
        cache.put(("b",), 2)
        time.sleep(0.02)
        purged = cache.purge_expired()
        assert purged == 2
        assert cache.size == 0

    def test_purge_mixed_fresh_and_stale(self) -> None:
        cache = WeatherCache(ttl_seconds=0.01)
        cache.put(("old",), 1)
        time.sleep(0.02)
        cache.put(("new",), 2)
        purged = cache.purge_expired()
        assert purged == 1
        assert cache.get(("new",)) == 2

    def test_overwrite_resets_ttl(self) -> None:
        cache = WeatherCache(ttl_seconds=0.05)
        cache.put(("a",), "v1")
        time.sleep(0.03)
        cache.put(("a",), "v2")  # reset TTL
        time.sleep(0.03)
        # total elapsed since first put > TTL, but second put resets
        assert cache.get(("a",)) == "v2"


# =========================================================================
# Section 4: WeatherAPIClient
# =========================================================================


class TestWeatherAPIClient:
    """WeatherAPIClient deterministic data generation."""

    @pytest.fixture()
    def client(self) -> WeatherAPIClient:
        return WeatherAPIClient()

    @pytest.mark.asyncio
    async def test_fetch_current_returns_weather(self, client: WeatherAPIClient) -> None:
        data = await client.fetch_current("London", "metric")
        assert isinstance(data, WeatherData)
        assert data.location == "London"
        assert data.units == "metric"
        assert isinstance(data.temperature, float)
        assert isinstance(data.humidity, float)
        assert isinstance(data.wind_speed, float)
        assert data.description != ""

    @pytest.mark.asyncio
    async def test_fetch_current_deterministic(self, client: WeatherAPIClient) -> None:
        d1 = await client.fetch_current("London", "metric")
        d2 = await client.fetch_current("London", "metric")
        assert d1.temperature == d2.temperature
        assert d1.description == d2.description

    @pytest.mark.asyncio
    async def test_fetch_current_different_locations(self, client: WeatherAPIClient) -> None:
        london = await client.fetch_current("London", "metric")
        tokyo = await client.fetch_current("Tokyo", "metric")
        # different locations should produce different data (with very high probability)
        assert london.location != tokyo.location

    @pytest.mark.asyncio
    async def test_fetch_current_imperial(self, client: WeatherAPIClient) -> None:
        metric = await client.fetch_current("London", "metric")
        imperial = await client.fetch_current("London", "imperial")
        assert imperial.units == "imperial"
        # F = C * 9/5 + 32
        expected = round(metric.temperature * 9.0 / 5.0 + 32.0, 1)
        assert imperial.temperature == expected

    @pytest.mark.asyncio
    async def test_fetch_current_kelvin(self, client: WeatherAPIClient) -> None:
        metric = await client.fetch_current("London", "metric")
        kelvin = await client.fetch_current("London", "kelvin")
        assert kelvin.units == "kelvin"
        expected = round(metric.temperature + 273.15, 1)
        assert kelvin.temperature == expected

    @pytest.mark.asyncio
    async def test_fetch_forecast_returns_data(self, client: WeatherAPIClient) -> None:
        data = await client.fetch_forecast("London", days=3, units="metric")
        assert isinstance(data, ForecastData)
        assert data.location == "London"
        assert len(data.forecast) == 3
        for day in data.forecast:
            assert isinstance(day, ForecastDay)
            assert day.date != ""
            assert day.high >= day.low

    @pytest.mark.asyncio
    async def test_fetch_forecast_clamps_days(self, client: WeatherAPIClient) -> None:
        data = await client.fetch_forecast("London", days=20, units="metric")
        assert len(data.forecast) == 7  # max 7

    @pytest.mark.asyncio
    async def test_fetch_forecast_min_1_day(self, client: WeatherAPIClient) -> None:
        data = await client.fetch_forecast("London", days=0, units="metric")
        assert len(data.forecast) == 1

    @pytest.mark.asyncio
    async def test_fetch_forecast_deterministic(self, client: WeatherAPIClient) -> None:
        d1 = await client.fetch_forecast("Tokyo", days=3)
        d2 = await client.fetch_forecast("Tokyo", days=3)
        assert d1.to_dict() == d2.to_dict()


# =========================================================================
# Section 5: WeatherHandlers
# =========================================================================


class TestWeatherHandlers:
    """WeatherHandlers argument validation, caching, and delegation."""

    @pytest.fixture()
    def cache(self) -> WeatherCache:
        return WeatherCache(ttl_seconds=300.0)

    @pytest.fixture()
    def handlers(self, cache: WeatherCache) -> WeatherHandlers:
        return WeatherHandlers(api_client=WeatherAPIClient(), cache=cache)

    @pytest.mark.asyncio
    async def test_current_basic(self, handlers: WeatherHandlers) -> None:
        result = await handlers.weather_current({"location": "Berlin"})
        assert result["location"] == "Berlin"
        assert "temperature" in result
        assert "humidity" in result
        assert result["units"] == "metric"

    @pytest.mark.asyncio
    async def test_current_with_units(self, handlers: WeatherHandlers) -> None:
        result = await handlers.weather_current({"location": "Berlin", "units": "imperial"})
        assert result["units"] == "imperial"

    @pytest.mark.asyncio
    async def test_current_missing_location(self, handlers: WeatherHandlers) -> None:
        with pytest.raises(ValueError, match="location is required"):
            await handlers.weather_current({})

    @pytest.mark.asyncio
    async def test_current_invalid_units(self, handlers: WeatherHandlers) -> None:
        with pytest.raises(ValueError, match="Invalid units"):
            await handlers.weather_current({"location": "Berlin", "units": "rankine"})

    @pytest.mark.asyncio
    async def test_current_uses_cache(self, handlers: WeatherHandlers, cache: WeatherCache) -> None:
        # first call populates cache
        r1 = await handlers.weather_current({"location": "London"})
        assert cache.size == 1
        # second call should return cached result
        r2 = await handlers.weather_current({"location": "London"})
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_forecast_basic(self, handlers: WeatherHandlers) -> None:
        result = await handlers.weather_forecast({"location": "Tokyo"})
        assert result["location"] == "Tokyo"
        assert len(result["forecast"]) == 3  # default days
        assert result["units"] == "metric"

    @pytest.mark.asyncio
    async def test_forecast_custom_days(self, handlers: WeatherHandlers) -> None:
        result = await handlers.weather_forecast({"location": "Tokyo", "days": 5})
        assert len(result["forecast"]) == 5

    @pytest.mark.asyncio
    async def test_forecast_missing_location(self, handlers: WeatherHandlers) -> None:
        with pytest.raises(ValueError, match="location is required"):
            await handlers.weather_forecast({})

    @pytest.mark.asyncio
    async def test_forecast_uses_cache(
        self, handlers: WeatherHandlers, cache: WeatherCache
    ) -> None:
        r1 = await handlers.weather_forecast({"location": "Paris", "days": 3})
        assert cache.size == 1
        r2 = await handlers.weather_forecast({"location": "Paris", "days": 3})
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_different_days_different_cache_keys(
        self, handlers: WeatherHandlers, cache: WeatherCache
    ) -> None:
        await handlers.weather_forecast({"location": "Paris", "days": 3})
        await handlers.weather_forecast({"location": "Paris", "days": 5})
        assert cache.size == 2


# =========================================================================
# Section 6: WeatherMCPServer
# =========================================================================


class TestWeatherMCPServer:
    """WeatherMCPServer JSON-RPC protocol handling."""

    @pytest.fixture()
    def server(self) -> WeatherMCPServer:
        return WeatherMCPServer(cache_ttl=300.0)

    # -- protocol methods --------------------------------------------------

    @pytest.mark.asyncio
    async def test_initialize(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(_rpc("initialize"))
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["protocolVersion"] == "2024-11-05"
        assert "weather-mcp-sse" in response["result"]["serverInfo"]["name"]

    @pytest.mark.asyncio
    async def test_tools_list_returns_2_tools(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(_rpc("tools/list"))
        tools = response["result"]["tools"]
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {
            "tool.read.weather_current",
            "tool.read.weather_forecast",
        }

    @pytest.mark.asyncio
    async def test_ping(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(_rpc("ping", id=99))
        assert "result" in response
        assert response["id"] == 99

    @pytest.mark.asyncio
    async def test_unknown_method(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(_rpc("unknown/method"))
        assert "error" in response
        assert response["error"]["code"] == -32601

    # -- tools/call: current -----------------------------------------------

    @pytest.mark.asyncio
    async def test_tools_call_current(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.weather_current",
                    "arguments": {"location": "London"},
                },
            )
        )
        content = response["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        data = json.loads(content[0]["text"])
        assert data["location"] == "London"
        assert "temperature" in data
        assert "humidity" in data

    @pytest.mark.asyncio
    async def test_tools_call_current_with_units(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.weather_current",
                    "arguments": {"location": "Berlin", "units": "imperial"},
                },
            )
        )
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["units"] == "imperial"

    @pytest.mark.asyncio
    async def test_tools_call_current_missing_location(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.weather_current",
                    "arguments": {},
                },
            )
        )
        assert "error" in response
        assert response["error"]["code"] == -32602

    # -- tools/call: forecast ----------------------------------------------

    @pytest.mark.asyncio
    async def test_tools_call_forecast(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.weather_forecast",
                    "arguments": {"location": "Tokyo", "days": 5},
                },
            )
        )
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["location"] == "Tokyo"
        assert len(data["forecast"]) == 5

    @pytest.mark.asyncio
    async def test_tools_call_forecast_default_days(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.weather_forecast",
                    "arguments": {"location": "Paris"},
                },
            )
        )
        data = json.loads(response["result"]["content"][0]["text"])
        assert len(data["forecast"]) == 3  # default

    @pytest.mark.asyncio
    async def test_tools_call_unknown_tool(self, server: WeatherMCPServer) -> None:
        response = await server.handle_message(
            _rpc(
                "tools/call",
                params={
                    "name": "tool.read.nonexistent",
                    "arguments": {},
                },
            )
        )
        assert "error" in response
        assert response["error"]["code"] == -32601

    # -- server properties -------------------------------------------------

    def test_server_exposes_cache(self, server: WeatherMCPServer) -> None:
        assert isinstance(server.cache, WeatherCache)

    def test_server_exposes_handlers(self, server: WeatherMCPServer) -> None:
        assert isinstance(server.handlers, WeatherHandlers)

    def test_server_exposes_api_client(self, server: WeatherMCPServer) -> None:
        assert isinstance(server.api_client, WeatherAPIClient)

    def test_server_injectable_api_client(self) -> None:
        custom_client = WeatherAPIClient()
        server = WeatherMCPServer(api_client=custom_client)
        assert server.api_client is custom_client

    def test_server_close_clears_cache(self, server: WeatherMCPServer) -> None:
        server.cache.put(("test",), "value")
        server.close()
        assert server.cache.size == 0

    # -- TOOLS list integrity ----------------------------------------------

    def test_tools_list_has_correct_names(self) -> None:
        names = {t["name"] for t in TOOLS}
        assert names == {
            "tool.read.weather_current",
            "tool.read.weather_forecast",
        }

    def test_tools_list_has_input_schemas(self) -> None:
        for tool in TOOLS:
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "location" in tool["inputSchema"]["properties"]

    def test_current_tool_location_required(self) -> None:
        current = next(t for t in TOOLS if t["name"] == "tool.read.weather_current")
        assert "location" in current["inputSchema"]["required"]

    def test_forecast_tool_location_required(self) -> None:
        forecast = next(t for t in TOOLS if t["name"] == "tool.read.weather_forecast")
        assert "location" in forecast["inputSchema"]["required"]


# =========================================================================
# Section 7: Contract YAML parsing
# =========================================================================


class TestWeatherContracts:
    """Parse and validate weather contract YAML files."""

    @pytest.fixture()
    def validator(self) -> ContractValidator:
        return ContractValidator()

    # -- weather_current ---------------------------------------------------

    def test_current_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "weather_current.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.read.weather_current"
        assert contract.version == "1.0.0"

    def test_current_contract_green_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_current.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_current_contract_provider(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_current.yaml", validator=validator)
        assert contract.provider_type == "MCP"
        assert contract.provider_id == "weather_mcp_sse"

    def test_current_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_current.yaml", validator=validator)
        required_names = [inp.name for inp in contract.required_inputs]
        assert "location" in required_names

    def test_current_contract_output(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_current.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "location" in props
        assert "temperature" in props
        assert "humidity" in props
        assert "wind_speed" in props
        assert "description" in props
        assert "units" in props

    def test_current_contract_domain(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_current.yaml", validator=validator)
        assert "WEATHER" in contract.domain

    # -- weather_forecast --------------------------------------------------

    def test_forecast_contract_parses(self, validator: ContractValidator) -> None:
        path = CONTRACTS_DIR / "weather_forecast.yaml"
        contract = parse_contract(path, validator=validator)
        assert isinstance(contract, CapabilityContract)
        assert contract.name == "tool.read.weather_forecast"
        assert contract.version == "1.0.0"

    def test_forecast_contract_green_band(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_forecast.yaml", validator=validator)
        assert contract.safety_band_min == "GREEN"

    def test_forecast_contract_provider(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_forecast.yaml", validator=validator)
        assert contract.provider_type == "MCP"
        assert contract.provider_id == "weather_mcp_sse"

    def test_forecast_contract_required_inputs(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_forecast.yaml", validator=validator)
        required_names = [inp.name for inp in contract.required_inputs]
        assert "location" in required_names

    def test_forecast_contract_output(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_forecast.yaml", validator=validator)
        props = contract.output.get("properties", {})
        assert "location" in props
        assert "forecast" in props
        assert "units" in props

    def test_forecast_contract_domain(self, validator: ContractValidator) -> None:
        contract = parse_contract(CONTRACTS_DIR / "weather_forecast.yaml", validator=validator)
        assert "WEATHER" in contract.domain

    # -- cross-contract invariants -----------------------------------------

    def test_both_contracts_share_provider_id(self, validator: ContractValidator) -> None:
        ids = set()
        for name in ["weather_current.yaml", "weather_forecast.yaml"]:
            c = parse_contract(CONTRACTS_DIR / name, validator=validator)
            ids.add(c.provider_id)
        assert ids == {"weather_mcp_sse"}

    def test_both_contracts_are_read_operations(self, validator: ContractValidator) -> None:
        for name in ["weather_current.yaml", "weather_forecast.yaml"]:
            c = parse_contract(CONTRACTS_DIR / name, validator=validator)
            assert c.name.startswith("tool.read.")
            assert c.safety_band_min == "GREEN"
