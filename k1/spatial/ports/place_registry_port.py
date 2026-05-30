"""Place registry boundary for household/domain places."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable

from k1.spatial.types import Geofence, PlaceRef


@runtime_checkable
class IPlaceRegistryPort(Protocol):
    """Read known places, aliases, geofences, and member defaults."""

    async def list_places(self, session_id: str) -> Sequence[PlaceRef]:
        """Return known place references for the session/group."""
        ...  # pragma: no cover

    async def list_geofences(self, session_id: str) -> Sequence[Geofence]:
        """Return known geofence declarations."""
        ...  # pragma: no cover

    async def member_default_places(self, session_id: str, subject_ref: str) -> Sequence[str]:
        """Return default place IDs associated with a subject."""
        ...  # pragma: no cover

    async def timezone_for_place(self, session_id: str, place_id: str) -> str | None:
        """Return a place timezone when available."""
        ...  # pragma: no cover

    async def registry_metadata(self, session_id: str) -> Mapping[str, object]:
        """Return registry availability/provenance metadata."""
        ...  # pragma: no cover


__all__ = ["IPlaceRegistryPort"]
