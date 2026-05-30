"""Adapter for browser/app supplied location payloads in DeviceContextSnapshot."""

from __future__ import annotations

from typing import Any, Mapping

from k1.spatial.ports import IDeviceLocationPort, ISpatialDeviceContextPort
from k1.spatial.types import LocationFix


class BrowserDeviceLocationAdapter(IDeviceLocationPort):
    """Read optional browser location payloads from the shared device snapshot."""

    def __init__(self, device_context_port: ISpatialDeviceContextPort) -> None:
        self._device_context = device_context_port

    async def get_location_fix(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> LocationFix | Mapping[str, Any] | None:
        snapshot = await self._device_context.get_device_snapshot(
            session_id,
            device_id,
            installation_id,
        )
        return snapshot.location_fix


__all__ = ["BrowserDeviceLocationAdapter"]
