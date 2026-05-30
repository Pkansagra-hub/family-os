"""Temporal subset of installed-device context."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ITemporalDeviceContextPort(Protocol):
    """Read device time/locale observations without importing spatial."""

    async def get_device_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> Mapping[str, Any]:
        """Return timezone, locale, observed timestamp, and clock-skew metadata."""
        ...  # pragma: no cover


__all__ = ["ITemporalDeviceContextPort"]
