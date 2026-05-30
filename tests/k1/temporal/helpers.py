"""Test helpers for k1.temporal focused tests."""

from __future__ import annotations

from k1.temporal.types import TemporalAnchor, TemporalWindow


def sample_anchor() -> TemporalAnchor:
    return TemporalAnchor(
        anchor_id="anchor-1",
        captured_at_utc="2025-03-09T09:30:00+00:00",
        now_utc="2025-03-09T09:30:00+00:00",
        now_local="2025-03-09T01:30:00-08:00",
        timezone="America/Los_Angeles",
        timezone_source="device",
        local_date="2025-03-09",
        local_time="01:30:00",
        day_of_week="Sunday",
        hour_24=1,
        time_of_day="late_night",
        is_weekend=True,
        locale="en-US",
        week_start_day="monday",
        freshness_ms=0,
        source="test",
        confidence=1.0,
    )


def sample_window(label: str = "today") -> TemporalWindow:
    return TemporalWindow(
        label=label,
        start_local="2025-03-09T00:00:00-08:00",
        end_local="2025-03-10T00:00:00-07:00",
        start_utc="2025-03-09T08:00:00+00:00",
        end_utc="2025-03-10T07:00:00+00:00",
        timezone="America/Los_Angeles",
        granularity="day",
    )
