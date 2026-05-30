"""Nominatim-backed geocoder adapter for spatial place names."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

from k1.spatial.ports import IGeocoderPort
from k1.spatial.types import LocationFix, PlaceCandidate, PlaceRef


class NominatimGeocoderAdapter(IGeocoderPort):
    """Resolve location fixes into address-level places when the provider can."""

    def __init__(
        self,
        *,
        endpoint: str = "https://nominatim.openstreetmap.org",
        user_agent: str = "familyos-k1-spatial/1.0",
        timeout_s: float = 2.0,
        coordinate_decimals: int = 6,
        reverse_zoom: int = 18,
        language: str = "en",
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._user_agent = user_agent
        self._timeout_s = float(timeout_s)
        self._coordinate_decimals = int(coordinate_decimals)
        self._reverse_zoom = int(reverse_zoom)
        self._language = language
        self._reverse_cache: dict[tuple[float, float, int], tuple[PlaceRef, ...]] = {}

    async def geocode(self, session_id: str, candidate: PlaceCandidate) -> Sequence[PlaceRef]:
        if not candidate.raw_text.strip():
            return ()
        params = urllib.parse.urlencode(
            {
                "format": "jsonv2",
                "addressdetails": "1",
                "limit": "3",
                "q": candidate.raw_text,
            }
        )
        payload = await self._fetch_json(f"{self._endpoint}/search?{params}")
        if not isinstance(payload, list):
            return ()
        places = []
        for item in payload:
            if isinstance(item, Mapping):
                place = _place_from_payload(item, candidate_source=candidate.source)
                if place is not None:
                    places.append(place)
        return tuple(places)

    async def reverse_geocode(self, session_id: str, fix: LocationFix) -> Sequence[PlaceRef]:
        if fix.latitude is None or fix.longitude is None:
            return ()
        latitude = round(float(fix.latitude), self._coordinate_decimals)
        longitude = round(float(fix.longitude), self._coordinate_decimals)
        key = (latitude, longitude, self._reverse_zoom)
        cached = self._reverse_cache.get(key)
        if cached is not None:
            return cached

        params = urllib.parse.urlencode(
            {
                "format": "jsonv2",
                "addressdetails": "1",
                "lat": latitude,
                "lon": longitude,
                "zoom": self._reverse_zoom,
            }
        )
        payload = await self._fetch_json(f"{self._endpoint}/reverse?{params}")
        if not isinstance(payload, Mapping):
            self._reverse_cache[key] = ()
            return ()
        place = _place_from_payload(payload, candidate_source="geocoder")
        resolved = (place,) if place is not None else ()
        self._reverse_cache[key] = resolved
        return resolved

    async def _fetch_json(self, url: str) -> Any:
        return await asyncio.to_thread(self._fetch_json_sync, url)

    def _fetch_json_sync(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
                "Accept-Language": self._language,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None


def _place_from_payload(payload: Mapping[str, Any], *, candidate_source: str) -> PlaceRef | None:
    address = payload.get("address")
    if not isinstance(address, Mapping):
        return None
    locality_key, locality = _locality_from_address(address)
    state = _string(address.get("state") or address.get("region"))
    country = _string(address.get("country_code") or address.get("country"))
    locality_label = _compose_locality_label(locality, state)
    house_number = _string(address.get("house_number"))
    road = _string(
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("residential")
    )
    street_label = _compose_street_label(house_number, road, locality_label)
    if street_label:
        place_kind = "address" if house_number else "street"
        return PlaceRef(
            place_id=_safe_place_id("geocoder", place_kind, street_label),
            label=street_label,
            place_kind=place_kind,
            confidence=_confidence(payload, place_kind),
            source="geocoder",
            aliases=tuple(_alias_values(street_label, locality_label, road, state)),
            timezone=None,
            metadata={
                "provider": "nominatim",
                "matched_candidate_source": candidate_source,
                "country": country,
                "address_level": True,
                "locality_label": locality_label,
                "locality_kind": locality_key or "locality",
                "locality_place_id": _safe_place_id(
                    "geocoder",
                    locality_key or "locality",
                    locality_label or street_label,
                ),
                "road": road,
                "house_number_available": bool(house_number),
            },
        )
    if not locality_label:
        return None
    place_kind = locality_key or _string(payload.get("type")) or "locality"
    return PlaceRef(
        place_id=_safe_place_id("geocoder", place_kind, locality_label),
        label=locality_label,
        place_kind=place_kind,
        confidence=_confidence(payload, place_kind),
        source="geocoder",
        aliases=tuple(_alias_values(locality_label, locality, state)),
        timezone=None,
        metadata={
            "provider": "nominatim",
            "matched_candidate_source": candidate_source,
            "country": country,
            "city_level": True,
            "locality_label": locality_label,
            "locality_kind": place_kind,
        },
    )


def _locality_from_address(address: Mapping[str, Any]) -> tuple[str | None, str | None]:
    locality_key, locality = _first_address_value(
        address,
        (
            "city",
            "town",
            "village",
            "municipality",
            "suburb",
            "neighbourhood",
            "county",
        ),
    )
    return locality_key, locality


def _compose_locality_label(locality: str | None, state: str | None) -> str | None:
    if not locality:
        return None
    return f"{locality}, {state}" if state else locality


def _compose_street_label(
    house_number: str | None,
    road: str | None,
    locality_label: str | None,
) -> str | None:
    if not road:
        return None
    street = f"{house_number} {road}" if house_number else road
    return f"{street}, {locality_label}" if locality_label else street


def _first_address_value(
    address: Mapping[str, Any], keys: tuple[str, ...]
) -> tuple[str | None, str | None]:
    for key in keys:
        value = _string(address.get(key))
        if value:
            return key, value
    return None, None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_place_id(*parts: str) -> str:
    raw = ":".join(parts).lower()
    slug = re.sub(r"[^a-z0-9:]+", "-", raw).strip("-:")
    return slug or "geocoder:unknown"


def _alias_values(*values: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in values if item))


def _confidence(payload: Mapping[str, Any], place_kind: str) -> float:
    try:
        importance = float(payload.get("importance", 0.0))
    except (TypeError, ValueError):
        importance = 0.0
    if place_kind == "address":
        base = 0.82
    elif place_kind == "street":
        base = 0.72
    elif place_kind in {"city", "town", "village", "municipality"}:
        base = 0.7
    else:
        base = 0.55
    return max(base, min(0.9, 0.55 + importance))


__all__ = ["NominatimGeocoderAdapter"]
