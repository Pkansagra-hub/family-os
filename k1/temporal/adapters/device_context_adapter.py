"""Adapter from kernel device context into temporal context subset."""

from __future__ import annotations

from typing import Any, Mapping

from k1.kernel.ports import IDeviceContextPort
from k1.temporal.ports import ITemporalDeviceContextPort


class DeviceContextAdapter(ITemporalDeviceContextPort):
    """Extract timezone, locale, observed timestamp, and clock skew."""

    def __init__(self, kernel_device_port: IDeviceContextPort) -> None:
        self._kernel_device_port = kernel_device_port

    async def get_device_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> Mapping[str, Any]:
        snapshot = await self._kernel_device_port.get_snapshot(
            session_id,
            device_id,
            installation_id,
        )
        return {
            "timezone": snapshot.timezone,
            "locale": snapshot.locale,
            "observed_at_utc": snapshot.observed_at_utc,
            "clock_skew_ms": snapshot.clock_skew_ms,
            "source": "device_context",
        }


__all__ = ["DeviceContextAdapter"]
