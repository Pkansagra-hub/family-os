"""k1.kernel.ports.device_context_port -- IDeviceContextPort.

Kernel-visible Protocol for installed-device observations. The pure
DeviceContextSnapshot payload is owned by k1.grounding.types so temporal
and spatial services consume one shared shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.grounding.types import DeviceContextSnapshot


@runtime_checkable
class IDeviceContextPort(Protocol):
    """Producer/reader boundary for installed-device snapshots."""

    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        """Return the latest installed-device observation for a session."""
        ...  # pragma: no cover

    async def update_snapshot(self, request: DeviceContextSnapshot) -> DeviceContextSnapshot:
        """Persist and return a normalized installed-device observation."""
        ...  # pragma: no cover


__all__ = ["DeviceContextSnapshot", "IDeviceContextPort"]
