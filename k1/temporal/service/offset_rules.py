"""Rules for offset expressions such as in two weeks."""

from __future__ import annotations

from datetime import date, timedelta

from k1.temporal.service.temporal_tokens import (
    MonthWindowToken,
    OffsetToken,
    WeekWindowToken,
)
from k1.temporal.service.window_builder import day_window, month_window, week_window
from k1.temporal.types import ResolvedTemporalExpression, TemporalAnchor


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def resolve_week_window(
    raw_text: str, token: WeekWindowToken, anchor: TemporalAnchor
) -> ResolvedTemporalExpression:
    base = date.fromisoformat(anchor.local_date) + timedelta(days=token.offset_weeks * 7)
    window = week_window(token.label, base, anchor.timezone, anchor.week_start_day)
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.94, False, None
    )


def resolve_month_window(
    raw_text: str, token: MonthWindowToken, anchor: TemporalAnchor
) -> ResolvedTemporalExpression:
    base = _add_months(date.fromisoformat(anchor.local_date), token.offset_months)
    window = month_window(token.label, base, anchor.timezone)
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.94, False, None
    )


def resolve_offset(
    raw_text: str, token: OffsetToken, anchor: TemporalAnchor
) -> ResolvedTemporalExpression:
    sign = 1 if token.direction == "future" else -1
    base = date.fromisoformat(anchor.local_date)
    if token.unit == "day":
        target = base + timedelta(days=sign * token.amount)
        window = day_window(token.label, target, anchor.timezone)
    elif token.unit == "week":
        target = base + timedelta(days=sign * token.amount * 7)
        window = week_window(token.label, target, anchor.timezone, anchor.week_start_day)
    else:
        target = _add_months(base, sign * token.amount)
        window = month_window(token.label, target, anchor.timezone)
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.88, False, None
    )


__all__ = ["resolve_month_window", "resolve_offset", "resolve_week_window"]
