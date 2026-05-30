"""Adapter from the kernel device-context port to the spatial port shape."""

from __future__ import annotations

from typing import Any

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.ports import ISpatialDeviceContextPort


class SpatialDeviceContextAdapter(ISpatialDeviceContextPort):
    """Expose installed-device snapshots to the spatial service."""

    def __init__(self, device_context_port: Any) -> None:
        self._port = device_context_port

    async def get_device_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        snapshot = await self._port.get_snapshot(session_id, device_id, installation_id)
        if not isinstance(snapshot, DeviceContextSnapshot):
            raise TypeError("device_context_port.get_snapshot() must return DeviceContextSnapshot")
        return snapshot


__all__ = ["SpatialDeviceContextAdapter"]
