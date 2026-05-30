"""Optional geocoder boundary for address/place lookup."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from k1.spatial.types import LocationFix, PlaceCandidate, PlaceRef


@runtime_checkable
class IGeocoderPort(Protocol):
    """Resolve address-like candidates when a geocoder is available."""

    async def geocode(self, session_id: str, candidate: PlaceCandidate) -> Sequence[PlaceRef]:
        """Return geocoder candidates, or an empty sequence when unavailable."""
        ...  # pragma: no cover

    async def reverse_geocode(self, session_id: str, fix: LocationFix) -> Sequence[PlaceRef]:
        """Return place candidates for a coordinate fix, or empty when unavailable."""
        ...  # pragma: no cover


__all__ = ["IGeocoderPort"]
