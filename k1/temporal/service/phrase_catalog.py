"""Deterministic temporal phrase catalog."""

from __future__ import annotations

from k1.temporal.service.expression_candidates import normalize_candidate_text
from k1.temporal.service.temporal_tokens import (
    DayPartToken,
    MonthWindowToken,
    OffsetToken,
    RelativeDayToken,
    TemporalToken,
    WeekdayToken,
    WeekWindowToken,
)

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
}

_STATIC: dict[str, TemporalToken] = {
    "today": RelativeDayToken(0, "today"),
    "yesterday": RelativeDayToken(-1, "yesterday"),
    "tomorrow": RelativeDayToken(1, "tomorrow"),
    "tonight": DayPartToken(0, "night", "tonight"),
    "this morning": DayPartToken(0, "morning", "this_morning"),
    "this afternoon": DayPartToken(0, "afternoon", "this_afternoon"),
    "this evening": DayPartToken(0, "evening", "this_evening"),
    "this week": WeekWindowToken(0, "this_week"),
    "next week": WeekWindowToken(1, "next_week"),
    "last week": WeekWindowToken(-1, "last_week"),
    "this weekend": DayPartToken(0, "weekend", "this_weekend"),
    "next month": MonthWindowToken(1, "next_month"),
    "this month": MonthWindowToken(0, "this_month"),
    "last month": MonthWindowToken(-1, "last_month"),
}


def lookup_phrase(text: str) -> TemporalToken | None:
    """Return a typed token for known deterministic phrases."""

    normalized = normalize_candidate_text(text)
    token = _STATIC.get(normalized)
    if token is not None:
        return token
    pieces = normalized.split()
    if len(pieces) == 2 and pieces[0] in {"next", "last", "this", "by"} and pieces[1] in _WEEKDAYS:
        direction = {"next": "next", "last": "previous", "this": "this", "by": "deadline"}[
            pieces[0]
        ]
        return WeekdayToken(_WEEKDAYS[pieces[1]], direction, normalized.replace(" ", "_"))
    if len(pieces) == 3 and pieces[0] == "in":
        amount = _NUMBERS.get(pieces[1])
        if amount is None and pieces[1].isdigit():
            amount = int(pieces[1])
        unit = pieces[2].rstrip("s")
        if amount is not None and unit in {"day", "week", "month"}:
            return OffsetToken(amount, unit, "future", normalized.replace(" ", "_"))
    if len(pieces) == 3 and pieces[2] == "ago":
        amount = _NUMBERS.get(pieces[0])
        if amount is None and pieces[0].isdigit():
            amount = int(pieces[0])
        unit = pieces[1].rstrip("s")
        if amount is not None and unit in {"day", "week", "month"}:
            return OffsetToken(amount, unit, "past", normalized.replace(" ", "_"))
    return None


__all__ = ["lookup_phrase"]
