"""
k1.tools.mcp_servers.weather.models -- Weather data models.

Frozen dataclasses for weather responses. Immutable after construction.
All temperatures are numeric, units tracked explicitly.

References:
  - weather_current.yaml (output schema)
  - weather_forecast.yaml (output schema)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class WeatherData:
    """
    Current weather conditions for a location.

    Matches the output schema of tool.read.weather_current.
    """

    location: str = ""
    temperature: float = 0.0
    humidity: float = 0.0
    wind_speed: float = 0.0
    description: str = ""
    units: str = "metric"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict matching contract output schema."""
        return {
            "location": self.location,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "description": self.description,
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeatherData":
        """Construct from dict."""
        return cls(
            location=data.get("location", ""),
            temperature=float(data.get("temperature", 0.0)),
            humidity=float(data.get("humidity", 0.0)),
            wind_speed=float(data.get("wind_speed", 0.0)),
            description=data.get("description", ""),
            units=data.get("units", "metric"),
        )


@dataclass(frozen=True)
class ForecastDay:
    """Single day within a multi-day forecast."""

    date: str = ""
    high: float = 0.0
    low: float = 0.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "high": self.high,
            "low": self.low,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ForecastDay":
        return cls(
            date=data.get("date", ""),
            high=float(data.get("high", 0.0)),
            low=float(data.get("low", 0.0)),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class ForecastData:
    """
    Multi-day weather forecast for a location.

    Matches the output schema of tool.read.weather_forecast.
    """

    location: str = ""
    forecast: Tuple[ForecastDay, ...] = ()
    units: str = "metric"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict matching contract output schema."""
        return {
            "location": self.location,
            "forecast": [day.to_dict() for day in self.forecast],
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ForecastData":
        days = tuple(ForecastDay.from_dict(d) for d in data.get("forecast", []))
        return cls(
            location=data.get("location", ""),
            forecast=days,
            units=data.get("units", "metric"),
        )
