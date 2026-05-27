"""Tests for web-to-kernel installed-device context propagation."""

from __future__ import annotations

import json
from typing import Any

from ui.web.coordinator import UiCoordinator


class _Port:
    def __init__(self) -> None:
        self.snapshots: list[Any] = []

    async def update_snapshot(self, request: Any) -> Any:
        self.snapshots.append(request)
        return request


class _Meta:
    def __init__(self) -> None:
        self.active_devices: list[str] = []

    def set_active_device(self, device_id: str) -> None:
        self.active_devices.append(device_id)


class _SessionState:
    def __init__(self, meta: _Meta) -> None:
        self._meta = meta

    def get_section(self, name: str) -> Any:
        if name != "meta":
            raise KeyError(name)
        return self._meta


async def test_record_device_context_writes_kernel_snapshot() -> None:
    port = _Port()
    meta = _Meta()
    coord = UiCoordinator(test_mode=True)
    coord._runtime = type(
        "Runtime",
        (),
        {"_session_id": "web-s1", "_service": type("Service", (), {"device_context_port": port})()},
    )()
    coord.session_state = _SessionState(meta)

    await coord._record_device_context(
        device="alex_phone",
        device_context={
            "timezone": "America/Chicago",
            "locale": "en-US",
            "observed_at_utc": "2026-05-19T04:00:00.000Z",
            "timezone_offset_minutes": 300,
            "surface": "web",
        },
    )

    assert len(port.snapshots) == 1
    snapshot = port.snapshots[0]
    assert snapshot.session_id == "web-s1"
    assert snapshot.device_id == "alex_phone"
    assert snapshot.installation_id == "alex_phone"
    assert snapshot.timezone == "America/Chicago"
    assert snapshot.locale == "en-US"
    assert snapshot.metadata["timezone_offset_minutes"] == 300
    assert meta.active_devices == ["alex_phone"]


async def test_record_device_context_falls_back_to_family_timezone() -> None:
    port = _Port()
    coord = UiCoordinator(test_mode=True)
    coord.family_profile = {"timezone": "America/Chicago"}
    coord._runtime = type(
        "Runtime",
        (),
        {"_session_id": "web-s1", "_service": type("Service", (), {"device_context_port": port})()},
    )()

    await coord._record_device_context(device="alex_phone", device_context={})

    assert len(port.snapshots) == 1
    snapshot = port.snapshots[0]
    assert snapshot.session_id == "web-s1"
    assert snapshot.device_id == "alex_phone"
    assert snapshot.timezone == "America/Chicago"
    assert snapshot.surface == "web"
    assert snapshot.metadata["profile_timezone"] == "America/Chicago"


async def test_record_device_context_falls_back_to_family_location_hint() -> None:
    port = _Port()
    coord = UiCoordinator(test_mode=True)
    coord.family_profile = {"location": "Denton, Texas"}
    coord._runtime = type(
        "Runtime",
        (),
        {"_session_id": "web-s1", "_service": type("Service", (), {"device_context_port": port})()},
    )()

    await coord._record_device_context(device="alex_phone", device_context={})

    assert len(port.snapshots) == 1
    snapshot = port.snapshots[0]
    assert snapshot.semantic_place_hint == "Denton, Texas"


async def test_record_device_context_promotes_profile_location_to_semantic_hint() -> None:
    port = _Port()
    coord = UiCoordinator(test_mode=True)
    coord._runtime = type(
        "Runtime",
        (),
        {"_session_id": "web-s1", "_service": type("Service", (), {"device_context_port": port})()},
    )()

    await coord._record_device_context(
        device="alex_phone",
        device_context={"profile_location": "Denton, Texas"},
    )

    assert len(port.snapshots) == 1
    snapshot = port.snapshots[0]
    assert snapshot.semantic_place_hint == "Denton, Texas"
    assert snapshot.metadata["profile_location"] == "Denton, Texas"


async def test_record_device_context_preserves_browser_location_fix() -> None:
    port = _Port()
    coord = UiCoordinator(test_mode=True)
    coord._runtime = type(
        "Runtime",
        (),
        {"_session_id": "web-s1", "_service": type("Service", (), {"device_context_port": port})()},
    )()

    await coord._record_device_context(
        device="alex_laptop",
        device_context={
            "timezone": "America/Chicago",
            "locale": "en-US",
            "observed_at_utc": "2026-05-23T21:00:00.000Z",
            "surface": "web",
            "location_permission": "granted",
            "location_fix": {
                "latitude": 33.2148,
                "longitude": -97.1331,
                "accuracy_m": 42,
                "captured_at_utc": "2026-05-23T21:00:00.000Z",
                "source": "browser_geolocation",
                "permission_state": "granted",
            },
            "browser_geolocation_status": "available",
        },
    )

    assert len(port.snapshots) == 1
    snapshot = port.snapshots[0]
    assert snapshot.device_id == "alex_laptop"
    assert snapshot.location_permission == "granted"
    assert snapshot.location_fix["latitude"] == 33.2148
    assert snapshot.location_fix["longitude"] == -97.1331
    assert snapshot.location_fix["source"] == "browser_geolocation"
    assert snapshot.metadata["browser_geolocation_status"] == "available"


class _Output:
    def __init__(self) -> None:
        self.member = ""
        self.turn = 0

    def set_member(self, member: str) -> None:
        self.member = member

    def start_turn(self, turn: int) -> None:
        self.turn = turn

    async def wait_for_response(self, timeout: float) -> None:
        self.timeout = timeout


class _Bus:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def publish(self, envelope: Any) -> None:
        self.payload = json.loads(envelope.payload.decode("utf-8"))


async def test_send_message_publishes_canonical_device_id() -> None:
    coord = UiCoordinator(test_mode=True)
    bus = _Bus()
    output = _Output()
    coord.bus = bus
    coord.output_channel = output

    await coord.send_message(
        text="what time is it",
        member="Alex",
        device="alex_phone",
        turn=7,
    )

    assert bus.payload is not None
    assert bus.payload["device"] == "alex_phone"
    assert bus.payload["device_id"] == "alex_phone"
