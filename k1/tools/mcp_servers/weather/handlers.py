"""
k1.tools.mcp_servers.weather.handlers -- Weather tool handler functions.

Each handler maps to one MCP tool. Receives raw arguments dict from the
MCP server router, delegates to WeatherAPIClient (with caching), and
returns a dict matching the contract output schema.

Handler naming: matches the tool name suffix (weather_current, weather_forecast).

References:
  - weather_current.yaml, weather_forecast.yaml
  - fabric_developer_guide.md Section 4 step 3
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from k1.tools.mcp_servers.weather.api_client import WeatherAPIClient
from k1.tools.mcp_servers.weather.cache import WeatherCache
from k1.tools.mcp_servers.weather.models import ForecastData, WeatherData

logger = logging.getLogger(__name__)


class WeatherHandlers:
    """
    Handler implementations for weather MCP tools.

    Each method corresponds to one tool contract. Methods receive
    a raw arguments dict (from MCP tools/call params.arguments)
    and return a dict matching the contract output schema.

    Args:
        api_client: WeatherAPIClient instance for data retrieval.
        cache: WeatherCache instance for response caching.
    """

    __slots__ = ("_api_client", "_cache")

    def __init__(
        self,
        api_client: WeatherAPIClient,
        cache: WeatherCache,
    ) -> None:
        self._api_client = api_client
        self._cache = cache

    async def weather_current(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool.read.weather_current.

        Required arguments:
            location (str): City name, zip code, or coordinates

        Optional arguments:
            units (str): metric | imperial | kelvin (default: metric)

        Returns:
            {location, temperature, humidity, wind_speed, description, units}
        """
        location = arguments.get("location")
        if not location:
            raise ValueError("location is required")

        units = arguments.get("units", "metric")
        if units not in ("metric", "imperial", "kelvin"):
            raise ValueError(f"Invalid units: {units}. Must be metric, imperial, or kelvin")

        cache_key = ("current", location.lower(), units)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for current weather: %s/%s", location, units)
            return cached

        data: WeatherData = await self._api_client.fetch_current(location, units)
        result = data.to_dict()
        self._cache.put(cache_key, result)
        return result

    async def weather_forecast(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool.read.weather_forecast.

        Required arguments:
            location (str): City name, zip code, or coordinates

        Optional arguments:
            days (int): 1-7 forecast days (default: 3)
            units (str): metric | imperial | kelvin (default: metric)

        Returns:
            {location, forecast: [{date, high, low, description}], units}
        """
        location = arguments.get("location")
        if not location:
            raise ValueError("location is required")

        days = int(arguments.get("days", 3))
        days = max(1, min(days, 7))

        units = arguments.get("units", "metric")
        if units not in ("metric", "imperial", "kelvin"):
            raise ValueError(f"Invalid units: {units}. Must be metric, imperial, or kelvin")

        cache_key = ("forecast", location.lower(), str(days), units)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for forecast: %s/%d/%s", location, days, units)
            return cached

        data: ForecastData = await self._api_client.fetch_forecast(location, days, units)
        result = data.to_dict()
        self._cache.put(cache_key, result)
        return result
