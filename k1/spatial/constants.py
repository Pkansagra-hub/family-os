"""Constants for the k1.spatial kernel module."""

from __future__ import annotations

SPATIAL_FRESHNESS_STATES: tuple[str, ...] = ("live", "stale", "degraded", "unavailable")
LOCATION_PERMISSION_STATES: tuple[str, ...] = (
    "granted",
    "denied",
    "hidden",
    "stale",
    "degraded",
    "unavailable",
    "unknown",
)
SPATIAL_PRECISIONS: tuple[str, ...] = (
    "hidden",
    "semantic",
    "approximate",
    "place_id",
    "address",
    "raw",
)
DEVICE_SURFACES: tuple[str, ...] = (
    "browser",
    "car",
    "desktop",
    "mobile",
    "shared_hub",
    "voice",
    "watch",
    "web",
    "unknown",
)
PLACE_KINDS: tuple[str, ...] = (
    "home",
    "school",
    "work",
    "store",
    "vehicle",
    "room",
    "address",
    "street",
    "outdoor",
    "unknown",
)
PLACE_CANDIDATE_SOURCES: tuple[str, ...] = (
    "device_hint",
    "registry",
    "task_param",
    "calendar_location",
    "conversation_mention",
    "geofence",
    "fallback",
)
SPATIAL_REDACTION_REASONS: tuple[str, ...] = (
    "policy_hidden",
    "raw_location_denied",
    "permission_denied",
    "permission_unavailable",
    "source_unavailable",
    "stale_location",
    "precision_downgraded",
)

DEFAULT_CONSUMER_PRECISION: dict[str, str] = {
    "front": "address",
    "back": "semantic",
    "planner": "place_id",
    "fabric": "place_id",
    "agent": "semantic",
    "tool": "place_id",
    "memory": "place_id",
}


__all__ = [
    "DEFAULT_CONSUMER_PRECISION",
    "DEVICE_SURFACES",
    "LOCATION_PERMISSION_STATES",
    "PLACE_CANDIDATE_SOURCES",
    "PLACE_KINDS",
    "SPATIAL_FRESHNESS_STATES",
    "SPATIAL_PRECISIONS",
    "SPATIAL_REDACTION_REASONS",
]
