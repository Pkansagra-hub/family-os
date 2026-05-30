"""Event topics and payloads emitted by the spatial kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

SPATIAL_CONTEXT_CREATED = "k1.spatial.context.created.v1"
SPATIAL_CONTEXT_REFRESHED = "k1.spatial.context.refreshed.v1"
SPATIAL_PLACE_RESOLVED = "k1.spatial.place.resolved.v1"
SPATIAL_CONTEXT_REDACTED = "k1.spatial.context.redacted.v1"
SPATIAL_LOCATION_UNAVAILABLE = "k1.spatial.location.unavailable.v1"


@dataclass(frozen=True)
class SpatialContextCreatedPayload:
    """Payload emitted when a spatial context is first created."""

    context_id: str
    session_id: str
    captured_at_utc: str
    semantic_place: str
    precision: str
    source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialContextRefreshedPayload:
    """Payload emitted when an existing spatial context is refreshed."""

    context_id: str
    previous_context_id: str | None
    session_id: str
    refreshed_at_utc: str
    freshness: str
    delta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialPlaceResolvedPayload:
    """Payload emitted when place evidence resolves to a place reference."""

    context_id: str
    session_id: str
    place_id: str
    raw_text: str
    source: str
    confidence: float
    resolved_at_utc: str


@dataclass(frozen=True)
class SpatialContextRedactedPayload:
    """Payload emitted when policy redacts spatial fields."""

    context_id: str
    session_id: str
    consumer: str
    redactions: tuple[str, ...]
    redacted_at_utc: str


@dataclass(frozen=True)
class SpatialLocationUnavailablePayload:
    """Payload emitted when installed-device location is unavailable."""

    session_id: str
    device_id: str | None
    installation_id: str | None
    permission_state: str
    observed_at_utc: str
    reason: str


__all__ = [
    "SPATIAL_CONTEXT_CREATED",
    "SPATIAL_CONTEXT_REDACTED",
    "SPATIAL_CONTEXT_REFRESHED",
    "SPATIAL_LOCATION_UNAVAILABLE",
    "SPATIAL_PLACE_RESOLVED",
    "SpatialContextCreatedPayload",
    "SpatialContextRedactedPayload",
    "SpatialContextRefreshedPayload",
    "SpatialLocationUnavailablePayload",
    "SpatialPlaceResolvedPayload",
]
