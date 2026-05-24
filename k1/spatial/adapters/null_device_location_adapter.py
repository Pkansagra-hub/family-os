"""Null location adapter for deployments without a raw location sensor."""

from __future__ import annotations

from k1.spatial.ports import IDeviceLocationPort


class NullDeviceLocationAdapter(IDeviceLocationPort):
    """Return explicit location-unavailable state by returning no fix."""

    async def get_location_fix(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> None:
        return None


__all__ = ["NullDeviceLocationAdapter"]
