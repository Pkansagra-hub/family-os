"""Nominatim geocoder adapter tests without live network calls."""

from __future__ import annotations

from typing import Any

from k1.spatial.adapters import NominatimGeocoderAdapter
from k1.spatial.types import LocationFix


class _FakeNominatim(NominatimGeocoderAdapter):
    def __init__(self, payload: Any) -> None:
        super().__init__(endpoint="https://example.invalid", coordinate_decimals=2)
        self.payload = payload
        self.urls: list[str] = []

    async def _fetch_json(self, url: str) -> Any:
        self.urls.append(url)
        return self.payload


async def test_reverse_geocode_returns_address_level_place() -> None:
    adapter = _FakeNominatim(
        {
            "address": {
                "house_number": "123",
                "road": "Example Ln",
                "city": "Sampleton",
                "state": "Testland",
                "country_code": "us",
            },
            "importance": 0.72,
        }
    )

    places = await adapter.reverse_geocode(
        "s1",
        LocationFix(
            latitude=33.0148,
            longitude=-96.8291,
            accuracy_m=77,
            captured_at_utc="2026-05-23T01:00:00+00:00",
            permission_state="granted",
            source="device",
            confidence=0.75,
        ),
    )

    assert len(places) == 1
    assert places[0].label == "123 Example Ln, Sampleton, Testland"
    assert places[0].place_kind == "address"
    assert places[0].source == "geocoder"
    assert places[0].metadata["address_level"] is True
    assert places[0].metadata["locality_label"] == "Sampleton, Testland"
    assert "lat=33.01" in adapter.urls[0]
    assert "lon=-96.83" in adapter.urls[0]


async def test_reverse_geocode_falls_back_to_city_level_place() -> None:
    adapter = _FakeNominatim(
        {
            "address": {
                "city": "Plano",
                "state": "Texas",
                "country_code": "us",
            },
            "importance": 0.72,
        }
    )

    places = await adapter.reverse_geocode(
        "s1",
        LocationFix(
            latitude=33.0148,
            longitude=-96.8291,
            accuracy_m=77,
            captured_at_utc="2026-05-23T01:00:00+00:00",
            permission_state="granted",
            source="device",
            confidence=0.75,
        ),
    )

    assert len(places) == 1
    assert places[0].label == "Plano, Texas"
    assert places[0].place_kind == "city"
    assert places[0].metadata["city_level"] is True
