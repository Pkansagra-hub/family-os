"""Typed tokens used by deterministic temporal expression rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RelativeDayToken:
    offset_days: int
    label: str


@dataclass(frozen=True)
class DayPartToken:
    offset_days: int
    part: str
    label: str


@dataclass(frozen=True)
class WeekWindowToken:
    offset_weeks: int
    label: str


@dataclass(frozen=True)
class MonthWindowToken:
    offset_months: int
    label: str


@dataclass(frozen=True)
class WeekdayToken:
    weekday: int
    direction: Literal["this", "next", "previous", "deadline"]
    label: str


@dataclass(frozen=True)
class OffsetToken:
    amount: int
    unit: Literal["day", "week", "month"]
    direction: Literal["future", "past"]
    label: str


@dataclass(frozen=True)
class RoutineToken:
    routine_id: str
    label: str


TemporalToken = (
    RelativeDayToken
    | DayPartToken
    | WeekWindowToken
    | MonthWindowToken
    | WeekdayToken
    | OffsetToken
    | RoutineToken
)

__all__ = [
    "DayPartToken",
    "MonthWindowToken",
    "OffsetToken",
    "RelativeDayToken",
    "RoutineToken",
    "TemporalToken",
    "WeekWindowToken",
    "WeekdayToken",
]
