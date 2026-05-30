"""Load and normalize the place registry through a narrow port."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from k1.spatial.ports import IPlaceRegistryPort
from k1.spatial.types import Geofence, PlaceRef


@dataclass(frozen=True)
class PlaceRegistrySnapshot:
    """Current registry projection used by spatial resolvers."""

    places: tuple[PlaceRef, ...]
    geofences: tuple[Geofence, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


async def load_place_registry(
    port: IPlaceRegistryPort,
    session_id: str,
) -> PlaceRegistrySnapshot:
    """Load places and geofences without exposing registry internals."""
    return PlaceRegistrySnapshot(
        places=tuple(await port.list_places(session_id)),
        geofences=tuple(await port.list_geofences(session_id)),
        metadata=dict(await port.registry_metadata(session_id)),
    )


__all__ = ["PlaceRegistrySnapshot", "load_place_registry"]
