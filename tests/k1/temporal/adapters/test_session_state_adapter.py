"""Tests for TemporalStateAdapter."""

from __future__ import annotations

import pytest

from k1.sessionstate.manager import SectionNotFoundError
from k1.temporal.adapters import TemporalStateAdapter


class _TemporalSection:
    def __init__(self) -> None:
        self.data = {}

    def set_data(self, data):  # type: ignore[no-untyped-def]
        self.data = data

    def to_dict(self):  # type: ignore[no-untyped-def]
        return self.data


class _Manager:
    def __init__(self, section=None):  # type: ignore[no-untyped-def]
        self.section = section

    def get_section(self, name):  # type: ignore[no-untyped-def]
        if name != "temporal" or self.section is None:
            raise SectionNotFoundError(name)
        return self.section


async def test_temporal_state_adapter_reads_and_writes_section() -> None:
    section = _TemporalSection()
    adapter = TemporalStateAdapter(_Manager(section))
    await adapter.write_section("s1", {"anchor": {"anchor_id": "a1"}})
    assert await adapter.read_section("s1") == {"anchor": {"anchor_id": "a1"}}


async def test_temporal_state_adapter_requires_section_without_fallback() -> None:
    adapter = TemporalStateAdapter(_Manager())
    with pytest.raises(SectionNotFoundError):
        await adapter.write_section("s1", {})


async def test_temporal_state_adapter_memory_fallback_is_explicit() -> None:
    adapter = TemporalStateAdapter(allow_memory_fallback=True)
    await adapter.write_section("s1", {"anchor": {"anchor_id": "a1"}})
    assert await adapter.read_section("s1") == {"anchor": {"anchor_id": "a1"}}
