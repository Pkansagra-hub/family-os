"""Tests for timezone candidate adapters."""

from __future__ import annotations

from k1.temporal.adapters import PersonaTimezoneAdapter, SpatialTimezoneAdapter


async def test_persona_timezone_adapter_reads_mapping() -> None:
    adapter = PersonaTimezoneAdapter({"principal-1": {"timezone": "America/New_York"}})
    assert await adapter.candidate_for_principal("principal-1") == "America/New_York"


async def test_spatial_timezone_adapter_is_disabled_by_default() -> None:
    adapter = SpatialTimezoneAdapter({"timezone": "America/Chicago"})
    assert await adapter.candidate_for_principal("principal-1") is None


async def test_spatial_timezone_adapter_reads_when_enabled() -> None:
    adapter = SpatialTimezoneAdapter({"timezone": "America/Chicago"}, enabled=True)
    assert await adapter.candidate_for_principal("principal-1") == "America/Chicago"
