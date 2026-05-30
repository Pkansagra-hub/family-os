"""Null geocoder adapter for explicit unavailable geocoding."""

from __future__ import annotations

from typing import Sequence

from k1.spatial.ports import IGeocoderPort
from k1.spatial.types import LocationFix, PlaceCandidate, PlaceRef


class NullGeocoderAdapter(IGeocoderPort):
    """Return no geocoder candidates without blocking context refresh."""

    async def geocode(self, session_id: str, candidate: PlaceCandidate) -> Sequence[PlaceRef]:
        return ()

    async def reverse_geocode(self, session_id: str, fix: LocationFix) -> Sequence[PlaceRef]:
        return ()


__all__ = ["NullGeocoderAdapter"]
