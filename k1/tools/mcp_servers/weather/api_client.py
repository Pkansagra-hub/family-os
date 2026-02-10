"""
k1.tools.mcp_servers.weather.api_client -- External weather API client.

Abstracts the external weather data source behind a clean async interface.
The default implementation returns realistic simulated data (no HTTP
dependency) so the server is fully testable and runnable without API keys.

To integrate a real API (OpenWeatherMap, weatherapi.com, etc.), subclass
WeatherAPIClient and override fetch_current / fetch_forecast.

References:
  - fabric_tool_implementation_plan.md Phase 2, Section 4.1
"""

from __future__ import annotations

import hashlib
import logging
from typing import List

from k1.tools.mcp_servers.weather.models import ForecastData, ForecastDay, WeatherData

logger = logging.getLogger(__name__)


class WeatherAPIClient:
    """
    Weather data provider.

    Default implementation returns deterministic data derived from the
    location string (hash-based) so tests are stable without network.
    Subclass and override for real HTTP integration.
    """

    async def fetch_current(self, location: str, units: str = "metric") -> WeatherData:
        """
        Fetch current weather for *location*.

        Parameters
        ----------
        location : str
            City name, zip code, or "lat,lon".
        units : str
            One of ``metric``, ``imperial``, ``kelvin``.

        Returns
        -------
        WeatherData
        """
        seed = self._seed(location)
        temp_base = (seed % 40) - 5  # -5 to 34 range

        temp = self._convert_temp(float(temp_base), units)
        humidity = float(30 + (seed % 60))  # 30-89
        wind = round(2.0 + (seed % 25), 1)

        conditions = [
            "Clear sky",
            "Partly cloudy",
            "Overcast",
            "Light rain",
            "Heavy rain",
            "Thunderstorm",
            "Snow",
            "Fog",
        ]
        desc = conditions[seed % len(conditions)]

        return WeatherData(
            location=location,
            temperature=temp,
            humidity=humidity,
            wind_speed=wind,
            description=desc,
            units=units,
        )

    async def fetch_forecast(
        self, location: str, days: int = 3, units: str = "metric"
    ) -> ForecastData:
        """
        Fetch multi-day forecast for *location*.

        Parameters
        ----------
        location : str
            City name, zip code, or "lat,lon".
        days : int
            Number of forecast days (1-7).
        units : str
            One of ``metric``, ``imperial``, ``kelvin``.

        Returns
        -------
        ForecastData
        """
        days = max(1, min(days, 7))
        seed = self._seed(location)

        forecast_days: List[ForecastDay] = []
        for i in range(days):
            day_seed = seed + i * 7
            high_base = float(15 + (day_seed % 25))
            low_base = high_base - float(5 + (day_seed % 10))

            high = self._convert_temp(high_base, units)
            low = self._convert_temp(low_base, units)

            conditions = [
                "Sunny",
                "Partly cloudy",
                "Cloudy",
                "Rain",
                "Thunderstorm",
                "Snow",
            ]
            desc = conditions[day_seed % len(conditions)]

            forecast_days.append(
                ForecastDay(
                    date=f"2025-01-{10 + i:02d}",
                    high=high,
                    low=low,
                    description=desc,
                )
            )

        return ForecastData(
            location=location,
            forecast=tuple(forecast_days),
            units=units,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _seed(location: str) -> int:
        """Deterministic seed from location string."""
        h = hashlib.md5(location.lower().encode("utf-8")).hexdigest()
        return int(h[:8], 16)

    @staticmethod
    def _convert_temp(celsius: float, units: str) -> float:
        """Convert Celsius to the requested unit system."""
        if units == "imperial":
            return round(celsius * 9.0 / 5.0 + 32.0, 1)
        if units == "kelvin":
            return round(celsius + 273.15, 1)
        return round(celsius, 1)
