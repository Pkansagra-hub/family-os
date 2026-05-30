"""Normalize spatial permission states."""

from __future__ import annotations

from k1.spatial.constants import LOCATION_PERMISSION_STATES

_ALIASES = {
    "allow": "granted",
    "allowed": "granted",
    "authorized": "granted",
    "blocked": "denied",
    "disabled": "unavailable",
    "forbidden": "denied",
    "missing": "unavailable",
    "not_available": "unavailable",
    "not-available": "unavailable",
    "private": "hidden",
    "redacted": "hidden",
}


def normalize_permission_state(raw: object) -> str:
    """Normalize a device/app permission state without inventing access."""
    text = str(raw or "").strip().lower().replace(" ", "_")
    if not text:
        return "unknown"
    normalized = _ALIASES.get(text, text)
    return normalized if normalized in LOCATION_PERMISSION_STATES else "unknown"


def is_location_usable(permission_state: object) -> bool:
    """Return True only for states that can expose a fix to deterministic services."""
    return normalize_permission_state(permission_state) == "granted"


__all__ = ["is_location_usable", "normalize_permission_state"]
