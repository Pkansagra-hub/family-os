"""M3-E2/E3 device context and surface behavior."""

from __future__ import annotations

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.adapters import (
    BrowserDeviceLocationAdapter,
    SpatialDeviceContextAdapter,
)
from k1.spatial.service import candidates_from_device_context, resolve_device_surface


class _KernelDeviceContextPort:
    def __init__(self, snapshot: DeviceContextSnapshot) -> None:
        self.snapshot = snapshot

    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        return self.snapshot


async def test_device_context_adapter_and_surface_resolution() -> None:
    snapshot = _snapshot(surface="phone", semantic_place_hint="Home")
    adapter = SpatialDeviceContextAdapter(_KernelDeviceContextPort(snapshot))

    restored = await adapter.get_device_snapshot("s1", "phone", "install")
    surface = resolve_device_surface(restored)

    assert restored is snapshot
    assert surface.surface_kind == "mobile"
    assert surface.installation_id == "install"


async def test_browser_location_adapter_reads_shared_device_context() -> None:
    snapshot = _snapshot(location_fix={"latitude": 33.2, "longitude": -97.1, "accuracy_m": 25})
    device_adapter = SpatialDeviceContextAdapter(_KernelDeviceContextPort(snapshot))
    location_adapter = BrowserDeviceLocationAdapter(device_adapter)

    assert (
        await location_adapter.get_location_fix("s1", "phone", "install") == snapshot.location_fix
    )


def test_device_context_candidates_use_semantic_hint() -> None:
    candidate = candidates_from_device_context(_snapshot(semantic_place_hint="Jordan School"))[0]

    assert candidate.normalized_text == "jordan school"
    assert candidate.source == "device_hint"


def _snapshot(**overrides: object) -> DeviceContextSnapshot:
    data = {
        "session_id": "s1",
        "device_id": "phone",
        "installation_id": "install",
        "observed_at_utc": "2026-05-23T01:00:00+00:00",
        "surface": "mobile",
        "location_permission": "granted",
    }
    data.update(overrides)
    return DeviceContextSnapshot(**data)
