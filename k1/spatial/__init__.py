"""k1.spatial -- kernel-owned surface, place, and presence grounding."""

from __future__ import annotations

from k1.spatial.config import SpatialConfig
from k1.spatial.errors import (
    InvalidLocationFixError,
    MissingPlaceRegistryError,
    PermissionDeniedSpatialError,
    SpatialError,
    SpatialPolicyDeniedError,
    SpatialUnavailableError,
    StaleLocationError,
    UnknownPlaceError,
)
from k1.spatial.events import (
    SPATIAL_CONTEXT_CREATED,
    SPATIAL_CONTEXT_REDACTED,
    SPATIAL_CONTEXT_REFRESHED,
    SPATIAL_LOCATION_UNAVAILABLE,
    SPATIAL_PLACE_RESOLVED,
)
from k1.spatial.types import (
    DeviceSurface,
    DeviceSurfaceKind,
    Geofence,
    LocationFix,
    LocationPermissionState,
    PlaceCandidate,
    PlaceRef,
    PresenceRef,
    SpatialContext,
    SpatialFreshnessState,
    SpatialPrecision,
    SpatialProjection,
    SpatialRedaction,
    SpatialSource,
    SpatialTurnSnapshot,
)

__all__ = [
    "DeviceSurface",
    "DeviceSurfaceKind",
    "DuplicateSpatialPortError",
    "Geofence",
    "InvalidLocationFixError",
    "InvalidSpatialPortError",
    "LocationFix",
    "LocationPermissionState",
    "MissingPlaceRegistryError",
    "MissingSpatialPortError",
    "PermissionDeniedSpatialError",
    "PlaceCandidate",
    "PlaceRef",
    "PresenceRef",
    "SPATIAL_CONTEXT_CREATED",
    "SPATIAL_CONTEXT_REDACTED",
    "SPATIAL_CONTEXT_REFRESHED",
    "SPATIAL_LOCATION_UNAVAILABLE",
    "SPATIAL_PLACE_RESOLVED",
    "SpatialConfig",
    "SpatialContext",
    "SpatialError",
    "SpatialFactory",
    "SpatialFreshnessState",
    "SpatialHandle",
    "SpatialPolicyDeniedError",
    "SpatialPrecision",
    "SpatialProjection",
    "SpatialRedaction",
    "SpatialServiceBundle",
    "SpatialSessionBinding",
    "SpatialSource",
    "SpatialTurnSnapshot",
    "SpatialUnavailableError",
    "StaleLocationError",
    "UnknownPlaceError",
    "build_spatial_bundle",
    "build_spatial_handle",
]


def __getattr__(name: str):
    if name in {
        "DuplicateSpatialPortError",
        "InvalidSpatialPortError",
        "MissingSpatialPortError",
        "SpatialFactory",
    }:
        from k1.spatial import factory as _factory

        return getattr(_factory, name)
    if name in {
        "SpatialHandle",
        "SpatialServiceBundle",
        "SpatialSessionBinding",
        "build_spatial_bundle",
        "build_spatial_handle",
    }:
        from k1.spatial import kernel as _kernel

        return getattr(_kernel, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
