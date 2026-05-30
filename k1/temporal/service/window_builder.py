"""Build canonical temporal windows from an anchor."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from k1.temporal.service.daylight_boundary import (
    iso,
    local_midnight,
    local_window_to_utc,
)
from k1.temporal.types import TemporalAnchor, TemporalWindow

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def day_window(label: str, day: date, timezone_name: str) -> TemporalWindow:
    start_local = local_midnight(day, timezone_name)
    end_local = local_midnight(day + timedelta(days=1), timezone_name)
    start_utc, end_utc = local_window_to_utc(start_local, end_local)
    return TemporalWindow(
        label, iso(start_local), iso(end_local), start_utc, end_utc, timezone_name, "day"
    )


def custom_window(label: str, start_local: datetime, end_local: datetime) -> TemporalWindow:
    start_utc, end_utc = local_window_to_utc(start_local, end_local)
    timezone_name = (
        start_local.tzinfo.key if hasattr(start_local.tzinfo, "key") else str(start_local.tzinfo)
    )
    return TemporalWindow(
        label, iso(start_local), iso(end_local), start_utc, end_utc, timezone_name, "custom"
    )


def week_window(label: str, day: date, timezone_name: str, week_start_day: str) -> TemporalWindow:
    start_index = _WEEKDAY_INDEX.get(week_start_day.lower(), 0)
    delta_days = (day.weekday() - start_index) % 7
    start_day = day - timedelta(days=delta_days)
    start_local = local_midnight(start_day, timezone_name)
    end_local = local_midnight(start_day + timedelta(days=7), timezone_name)
    start_utc, end_utc = local_window_to_utc(start_local, end_local)
    return TemporalWindow(
        label, iso(start_local), iso(end_local), start_utc, end_utc, timezone_name, "week"
    )


def month_window(label: str, day: date, timezone_name: str) -> TemporalWindow:
    first = day.replace(day=1)
    _, last_day = calendar.monthrange(day.year, day.month)
    next_month = first.replace(day=last_day) + timedelta(days=1)
    start_local = local_midnight(first, timezone_name)
    end_local = local_midnight(next_month, timezone_name)
    start_utc, end_utc = local_window_to_utc(start_local, end_local)
    return TemporalWindow(
        label, iso(start_local), iso(end_local), start_utc, end_utc, timezone_name, "month"
    )


def daypart_window(label: str, day: date, timezone_name: str, part: str) -> TemporalWindow:
    hours = {
        "morning": (6, 12),
        "midday": (11, 14),
        "afternoon": (12, 17),
        "evening": (17, 21),
        "night": (21, 24),
        "late_night": (0, 5),
    }
    start_hour, end_hour = hours.get(part, (0, 24))
    zone = ZoneInfo(timezone_name)
    start_local = datetime.combine(day, time(start_hour), tzinfo=zone)
    end_day = day + timedelta(days=1) if end_hour == 24 else day
    end_time = time.min if end_hour == 24 else time(end_hour)
    end_local = datetime.combine(end_day, end_time, tzinfo=zone)
    return custom_window(label, start_local, end_local)


def build_standard_windows(anchor: TemporalAnchor) -> dict[str, TemporalWindow]:
    """Build canonical day/week/month windows around the anchor."""

    today = date.fromisoformat(anchor.local_date)
    timezone_name = anchor.timezone
    this_week = week_window("this_week", today, timezone_name, anchor.week_start_day)
    this_week_start = datetime.fromisoformat(this_week.start_local).date()
    saturday = this_week_start + timedelta(days=(5 - this_week_start.weekday()) % 7)
    next_saturday = saturday + timedelta(days=7)
    return {
        "yesterday": day_window("yesterday", today - timedelta(days=1), timezone_name),
        "today": day_window("today", today, timezone_name),
        "tomorrow": day_window("tomorrow", today + timedelta(days=1), timezone_name),
        "this_week": this_week,
        "next_week": week_window(
            "next_week", today + timedelta(days=7), timezone_name, anchor.week_start_day
        ),
        "this_month": month_window("this_month", today, timezone_name),
        "next_month": month_window(
            "next_month", today.replace(day=28) + timedelta(days=4), timezone_name
        ),
        "this_weekend": custom_window(
            "this_weekend",
            local_midnight(saturday, timezone_name),
            local_midnight(saturday + timedelta(days=2), timezone_name),
        ),
        "next_weekend": custom_window(
            "next_weekend",
            local_midnight(next_saturday, timezone_name),
            local_midnight(next_saturday + timedelta(days=2), timezone_name),
        ),
    }


__all__ = [
    "build_standard_windows",
    "custom_window",
    "day_window",
    "daypart_window",
    "month_window",
    "week_window",
]
