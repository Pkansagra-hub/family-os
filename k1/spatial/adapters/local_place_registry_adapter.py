"""In-memory place registry adapter for standalone and test deployments."""

from __future__ import annotations

from typing import Mapping, Sequence

from k1.spatial.ports import IPlaceRegistryPort
from k1.spatial.types import Geofence, PlaceRef


class LocalPlaceRegistryAdapter(IPlaceRegistryPort):
    """Read configured places from local memory."""

    def __init__(
        self,
        *,
        places: Sequence[PlaceRef] = (),
        geofences: Sequence[Geofence] = (),
        member_defaults: Mapping[str, Sequence[str]] | None = None,
        place_timezones: Mapping[str, str] | None = None,
        available: bool = True,
    ) -> None:
        self._places = tuple(places)
        self._geofences = tuple(geofences)
        self._member_defaults = {
            str(key): tuple(value) for key, value in dict(member_defaults or {}).items()
        }
        self._place_timezones = dict(place_timezones or {})
        self._available = available

    async def list_places(self, session_id: str) -> Sequence[PlaceRef]:
        return self._places

    async def list_geofences(self, session_id: str) -> Sequence[Geofence]:
        return self._geofences

    async def member_default_places(self, session_id: str, subject_ref: str) -> Sequence[str]:
        return self._member_defaults.get(subject_ref, ())

    async def timezone_for_place(self, session_id: str, place_id: str) -> str | None:
        place = next((item for item in self._places if item.place_id == place_id), None)
        return self._place_timezones.get(place_id) or (
            place.timezone if place is not None else None
        )

    async def registry_metadata(self, session_id: str) -> Mapping[str, object]:
        return {"available": self._available, "mode": "local", "place_count": len(self._places)}


__all__ = ["LocalPlaceRegistryAdapter"]
