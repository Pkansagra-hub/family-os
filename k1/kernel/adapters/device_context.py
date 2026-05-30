"""Installed-device context adapter for kernel-owned grounding inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from k1.grounding.types import DeviceContextSnapshot
from k1.kernel.ports import IDeviceContextPort


class InMemoryDeviceContextPort(IDeviceContextPort):
    """Process-local store for latest installed-device observations."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[tuple[str, str, str], DeviceContextSnapshot] = {}

    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        session = str(session_id or "")
        device = str(device_id or "")
        installation = str(installation_id or device or "")
        with self._lock:
            snapshot = self._snapshots.get((session, device, installation))
            if snapshot is not None:
                return snapshot
            candidates = [
                item
                for key, item in self._snapshots.items()
                if key[0] == session and key[1] == device
            ]
            if candidates:
                return max(candidates, key=lambda item: item.observed_at_utc)
        return DeviceContextSnapshot(
            session_id=session,
            device_id=device,
            installation_id=installation,
            observed_at_utc=datetime.now(timezone.utc).isoformat(),
            surface="unknown",
        )

    async def update_snapshot(self, request: DeviceContextSnapshot) -> DeviceContextSnapshot:
        snapshot = self._normalize(request)
        key = (snapshot.session_id, snapshot.device_id, snapshot.installation_id)
        with self._lock:
            self._snapshots[key] = snapshot
        return snapshot

    @staticmethod
    def _normalize(request: DeviceContextSnapshot) -> DeviceContextSnapshot:
        session_id = str(request.session_id or "")
        device_id = str(request.device_id or "")
        installation_id = str(request.installation_id or device_id or "")
        observed_at = str(request.observed_at_utc or datetime.now(timezone.utc).isoformat())
        timezone_name = str(request.timezone).strip() if request.timezone else None
        locale = str(request.locale).strip() if request.locale else None
        surface = str(request.surface or "unknown")
        return DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id,
            installation_id=installation_id,
            observed_at_utc=observed_at,
            surface=surface,
            timezone=timezone_name or None,
            locale=locale or None,
            clock_skew_ms=request.clock_skew_ms,
            location_permission=request.location_permission or "unknown",
            location_fix=request.location_fix,
            semantic_place_hint=request.semantic_place_hint,
            metadata=dict(request.metadata or {}),
        )


__all__ = ["InMemoryDeviceContextPort"]
