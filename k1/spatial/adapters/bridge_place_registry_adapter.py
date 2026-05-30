"""Bridge-backed place registry adapter placeholder for M5 durable storage."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from k1.spatial.ports import IPlaceRegistryPort
from k1.spatial.types import Geofence, PlaceRef


class BridgePlaceRegistryAdapter(IPlaceRegistryPort):
    """Delegate to a bridge client when it exposes place-registry methods."""

    def __init__(self, bridge_client: Any | None = None) -> None:
        self._bridge = bridge_client

    async def list_places(self, session_id: str) -> Sequence[PlaceRef]:
        method = getattr(self._bridge, "list_places", None) if self._bridge is not None else None
        if callable(method):
            return tuple(await method(session_id=session_id))
        return ()

    async def list_geofences(self, session_id: str) -> Sequence[Geofence]:
        method = getattr(self._bridge, "list_geofences", None) if self._bridge is not None else None
        if callable(method):
            return tuple(await method(session_id=session_id))
        return ()

    async def member_default_places(self, session_id: str, subject_ref: str) -> Sequence[str]:
        method = (
            getattr(self._bridge, "member_default_places", None)
            if self._bridge is not None
            else None
        )
        if callable(method):
            return tuple(await method(session_id=session_id, subject_ref=subject_ref))
        return ()

    async def timezone_for_place(self, session_id: str, place_id: str) -> str | None:
        method = (
            getattr(self._bridge, "timezone_for_place", None) if self._bridge is not None else None
        )
        if callable(method):
            return await method(session_id=session_id, place_id=place_id)
        return None

    async def registry_metadata(self, session_id: str) -> Mapping[str, object]:
        return {"available": self._bridge is not None, "mode": "bridge"}


__all__ = ["BridgePlaceRegistryAdapter"]
