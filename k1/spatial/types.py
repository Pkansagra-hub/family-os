"""Pure payload types for the k1.spatial kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Mapping

if TYPE_CHECKING:  # pragma: no cover - avoids runtime cycle with k1.grounding.types
    from k1.grounding.types import DeviceContextSnapshot

SpatialFreshnessState = Literal["live", "stale", "degraded", "unavailable"]
LocationPermissionState = Literal[
    "granted",
    "denied",
    "hidden",
    "stale",
    "degraded",
    "unavailable",
    "unknown",
]
SpatialPrecision = Literal["hidden", "semantic", "approximate", "place_id", "address", "raw"]
SpatialSource = Literal[
    "device",
    "device_hint",
    "registry",
    "geofence",
    "conversation_mention",
    "calendar_location",
    "policy",
    "fallback",
]
DeviceSurfaceKind = Literal[
    "browser",
    "car",
    "desktop",
    "mobile",
    "shared_hub",
    "voice",
    "watch",
    "web",
    "unknown",
]


@dataclass(frozen=True)
class DeviceSurface:
    """Observed client surface for the active installation."""

    surface_id: str
    surface_kind: DeviceSurfaceKind | str
    device_id: str | None
    installation_id: str | None
    capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocationFix:
    """Raw or approximate location observation before projection policy."""

    latitude: float | None
    longitude: float | None
    accuracy_m: float | None
    captured_at_utc: str
    permission_state: LocationPermissionState | str
    source: SpatialSource | str
    confidence: float
    altitude_m: float | None = None
    heading_deg: float | None = None
    speed_mps: float | None = None
    precision: SpatialPrecision | str = "raw"
    privacy_class: str = "sensitive"
    redactions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlaceRef:
    """Semantic place reference with an open place-kind vocabulary."""

    place_id: str
    label: str
    place_kind: str
    confidence: float
    source: SpatialSource | str
    aliases: tuple[str, ...] = ()
    timezone: str | None = None
    parent_place_id: str | None = None
    geofence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Geofence:
    """Policy-safe geofence declaration associated with a place."""

    geofence_id: str
    place_id: str
    shape: str
    parameters: Mapping[str, Any]
    source: SpatialSource | str
    confidence: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlaceCandidate:
    """Structured place evidence from a device, task, calendar, or conversation."""

    raw_text: str
    normalized_text: str
    source: SpatialSource | str
    confidence: float
    subject_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PresenceRef:
    """Co-presence signal for a subject, redacted by projection policy."""

    subject_ref: str
    place_ref: PlaceRef | None
    confidence: float
    source: SpatialSource | str
    captured_at_utc: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialRedaction:
    """Audit record for a spatial field hidden or downgraded by policy."""

    reason: str
    field: str
    consumer: str
    policy: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialContext:
    """Authoritative current spatial context for a session."""

    context_id: str
    session_id: str
    captured_at_utc: str
    active_place: PlaceRef | None
    active_device_surface: DeviceSurface | None
    location_fix: LocationFix | None
    co_presence: tuple[PresenceRef, ...]
    freshness: SpatialFreshnessState | str
    redactions: tuple[str, ...]
    location_permission: LocationPermissionState | str = "unknown"
    precision: SpatialPrecision | str = "hidden"
    place_refs: tuple[PlaceRef, ...] = ()
    mentioned_places: tuple[PlaceRef, ...] = ()
    device_context: "DeviceContextSnapshot | None" = None
    provenance: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialProjection:
    """Policy-shaped spatial payload for one downstream consumer."""

    projection_id: str
    context_id: str
    session_id: str
    consumer: str
    semantic_place: str
    precision: SpatialPrecision | str
    place_refs: tuple[PlaceRef, ...]
    active_device_surface: str | None
    co_presence: tuple[PresenceRef, ...]
    freshness: SpatialFreshnessState | str
    redactions: tuple[str, ...]
    location_permission: LocationPermissionState | str = "unknown"
    approximate_location: Mapping[str, Any] | None = None
    raw_location: LocationFix | None = None
    relevant_place_refs: tuple[PlaceRef, ...] = ()
    provenance: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialTurnSnapshot:
    """Spatial state written after a turn refresh."""

    session_id: str
    turn_id: str | None
    context: SpatialContext
    projection: SpatialProjection
    refreshed_at_utc: str
    source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "DeviceSurface",
    "DeviceSurfaceKind",
    "Geofence",
    "LocationFix",
    "LocationPermissionState",
    "PlaceCandidate",
    "PlaceRef",
    "PresenceRef",
    "SpatialFreshnessState",
    "SpatialContext",
    "SpatialPrecision",
    "SpatialProjection",
    "SpatialRedaction",
    "SpatialSource",
    "SpatialTurnSnapshot",
]
