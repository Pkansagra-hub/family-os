"""Constants for the k1.temporal kernel module."""

from __future__ import annotations

STANDARD_WINDOW_LABELS: tuple[str, ...] = (
    "yesterday",
    "today",
    "tomorrow",
    "this_week",
    "next_week",
    "this_weekend",
    "next_weekend",
    "this_month",
    "next_month",
)

TIME_OF_DAY_BUCKETS: tuple[str, ...] = (
    "early_morning",
    "morning",
    "midday",
    "afternoon",
    "evening",
    "night",
    "late_night",
)

FRESHNESS_STATES: tuple[str, ...] = ("live", "stale", "degraded", "unavailable")
TIMEZONE_SOURCES: tuple[str, ...] = ("device", "spatial", "persona", "utc")
WEEKDAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
