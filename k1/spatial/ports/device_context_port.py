"""Installed-device context boundary for spatial normalization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.grounding.types import DeviceContextSnapshot


@runtime_checkable
class ISpatialDeviceContextPort(Protocol):
    """Read latest installed-device observation for spatial service use."""

    async def get_device_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        """Return the latest device context snapshot for this installation."""
        ...  # pragma: no cover


__all__ = ["ISpatialDeviceContextPort"]
