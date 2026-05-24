"""Resolve installed-device surface metadata into a spatial surface."""

from __future__ import annotations

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.constants import DEVICE_SURFACES
from k1.spatial.types import DeviceSurface

_SURFACE_ALIASES = {
    "browser": "browser",
    "car": "car",
    "desktop": "desktop",
    "hub": "shared_hub",
    "mobile": "mobile",
    "phone": "mobile",
    "shared_home_hub": "shared_hub",
    "shared hub": "shared_hub",
    "tablet": "mobile",
    "voice": "voice",
    "watch": "watch",
    "web": "web",
}


def normalize_surface_kind(raw: object) -> str:
    """Normalize an installed-device surface label to the canonical vocabulary."""
    text = str(raw or "").strip().lower().replace("-", "_")
    if not text:
        return "unknown"
    normalized = _SURFACE_ALIASES.get(text, text)
    return normalized if normalized in DEVICE_SURFACES else "unknown"


def resolve_device_surface(snapshot: DeviceContextSnapshot) -> DeviceSurface:
    """Build a deterministic device surface from a shared device snapshot."""
    surface_kind = normalize_surface_kind(snapshot.surface)
    capabilities = snapshot.metadata.get("capabilities", ()) if snapshot.metadata else ()
    if isinstance(capabilities, str):
        capabilities = (capabilities,)
    surface_id = str(
        snapshot.metadata.get("surface_id")
        if snapshot.metadata and snapshot.metadata.get("surface_id")
        else snapshot.installation_id or snapshot.device_id or "unknown"
    )
    return DeviceSurface(
        surface_id=surface_id,
        surface_kind=surface_kind,
        device_id=snapshot.device_id,
        installation_id=snapshot.installation_id,
        capabilities=tuple(str(item) for item in capabilities),
        metadata={"locale": snapshot.locale, "timezone": snapshot.timezone},
    )


class DeviceSurfaceResolver:
    """Class wrapper used by factory/service wiring."""

    def resolve(self, snapshot: DeviceContextSnapshot) -> DeviceSurface:
        return resolve_device_surface(snapshot)


__all__ = ["DeviceSurfaceResolver", "normalize_surface_kind", "resolve_device_surface"]
