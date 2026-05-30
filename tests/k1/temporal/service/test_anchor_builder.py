"""Tests for temporal anchor builder."""

from __future__ import annotations

from k1.temporal.service.anchor_builder import build_anchor


class _Clock:
    def now_utc(self) -> str:
        return "2025-03-09T09:30:00+00:00"

    def monotonic_ms(self) -> int:
        return 1


class _Ids:
    def new_anchor_id(self) -> str:
        return "a1"

    def new_window_id(self) -> str:
        return "w1"

    def new_resolution_id(self) -> str:
        return "r1"


async def test_anchor_builder_uses_device_timezone_and_locale() -> None:
    anchor = await build_anchor(
        session_id="s1",
        clock=_Clock(),
        id_port=_Ids(),
        device_context={"timezone": "America/Los_Angeles", "locale": "en-US"},
    )
    assert anchor.anchor_id == "a1"
    assert anchor.timezone == "America/Los_Angeles"
    assert anchor.timezone_source == "device"
    assert anchor.local_date == "2025-03-09"
