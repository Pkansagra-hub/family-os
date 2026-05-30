"""Optional installed-device location source for spatial normalization."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from k1.spatial.types import LocationFix


@runtime_checkable
class IDeviceLocationPort(Protocol):
    """Read an optional raw or approximate location fix."""

    async def get_location_fix(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> LocationFix | Mapping[str, Any] | None:
        """Return a location fix, a raw mapping, or None when unavailable."""
        ...  # pragma: no cover


__all__ = ["IDeviceLocationPort"]
