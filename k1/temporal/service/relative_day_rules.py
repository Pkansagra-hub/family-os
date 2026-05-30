"""Rules for relative day and day-part expressions."""

from __future__ import annotations

from datetime import date, timedelta

from k1.temporal.service.temporal_tokens import DayPartToken, RelativeDayToken
from k1.temporal.service.window_builder import (
    build_standard_windows,
    day_window,
    daypart_window,
)
from k1.temporal.types import ResolvedTemporalExpression, TemporalAnchor


def resolve_relative_day(
    raw_text: str, token: RelativeDayToken, anchor: TemporalAnchor
) -> ResolvedTemporalExpression:
    base = date.fromisoformat(anchor.local_date)
    window = day_window(token.label, base + timedelta(days=token.offset_days), anchor.timezone)
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.97, False, None
    )


def resolve_daypart(
    raw_text: str, token: DayPartToken, anchor: TemporalAnchor
) -> ResolvedTemporalExpression:
    if token.part == "weekend":
        window = build_standard_windows(anchor)["this_weekend"]
    else:
        base = date.fromisoformat(anchor.local_date) + timedelta(days=token.offset_days)
        window = daypart_window(token.label, base, anchor.timezone, token.part)
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.94, False, None
    )


__all__ = ["resolve_daypart", "resolve_relative_day"]
