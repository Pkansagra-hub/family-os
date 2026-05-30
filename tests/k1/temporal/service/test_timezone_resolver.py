"""Tests for timezone resolver."""

from __future__ import annotations

from k1.temporal.service.timezone_resolver import resolve_timezone


def test_timezone_resolution_prefers_device_then_spatial_then_persona_then_utc() -> None:
    assert resolve_timezone(device_timezone="America/Los_Angeles").source == "device"
    assert (
        resolve_timezone(device_timezone="Nope/Zone", spatial_timezone="Europe/London").source
        == "spatial"
    )
    assert (
        resolve_timezone(spatial_timezone="Nope/Zone", persona_timezone="Asia/Tokyo").source
        == "persona"
    )
    assert resolve_timezone(persona_timezone="Nope/Zone").timezone == "UTC"
