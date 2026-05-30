"""Tests for SystemClockAdapter."""

from __future__ import annotations

from datetime import datetime

from k1.temporal.adapters import SystemClockAdapter


def test_system_clock_returns_utc_iso_and_monotonic_ms() -> None:
    adapter = SystemClockAdapter()
    first = adapter.monotonic_ms()
    now = datetime.fromisoformat(adapter.now_utc())
    second = adapter.monotonic_ms()
    assert now.tzinfo is not None
    assert second >= first
