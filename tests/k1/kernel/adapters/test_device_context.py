"""Tests for kernel installed-device context storage."""

from __future__ import annotations

from k1.grounding.types import DeviceContextSnapshot
from k1.kernel.adapters.device_context import InMemoryDeviceContextPort
from k1.kernel.ports import IDeviceContextPort
from k1.temporal.adapters.device_context_adapter import DeviceContextAdapter


async def test_in_memory_device_context_port_stores_latest_snapshot() -> None:
    port = InMemoryDeviceContextPort()
    assert isinstance(port, IDeviceContextPort)

    stored = await port.update_snapshot(
        DeviceContextSnapshot(
            session_id="s1",
            device_id="alex_phone",
            installation_id="alex_phone",
            observed_at_utc="2026-05-19T04:00:00+00:00",
            surface="web",
            timezone="America/Chicago",
            locale="en-US",
            metadata={"timezone_offset_minutes": 300},
        )
    )
    snapshot = await port.get_snapshot("s1", "alex_phone", "alex_phone")

    assert snapshot is stored
    assert snapshot.timezone == "America/Chicago"
    assert snapshot.locale == "en-US"
    assert snapshot.metadata["timezone_offset_minutes"] == 300


async def test_in_memory_device_context_port_returns_empty_snapshot_when_missing() -> None:
    port = InMemoryDeviceContextPort()

    snapshot = await port.get_snapshot("s1", "unknown", "unknown")

    assert snapshot.session_id == "s1"
    assert snapshot.device_id == "unknown"
    assert snapshot.timezone is None


async def test_in_memory_device_context_feeds_temporal_adapter() -> None:
    port = InMemoryDeviceContextPort()
    await port.update_snapshot(
        DeviceContextSnapshot(
            session_id="s1",
            device_id="alex_phone",
            installation_id="alex_phone",
            observed_at_utc="2026-05-19T04:00:00+00:00",
            surface="web",
            timezone="America/Chicago",
            locale="en-US",
        )
    )

    adapter = DeviceContextAdapter(port)
    snapshot = await adapter.get_device_snapshot("s1", "alex_phone", "alex_phone")

    assert snapshot["timezone"] == "America/Chicago"
    assert snapshot["locale"] == "en-US"
    assert snapshot["source"] == "device_context"
