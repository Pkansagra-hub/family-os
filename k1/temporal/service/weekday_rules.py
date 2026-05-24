"""Rules for weekday expressions."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from k1.temporal.service.temporal_tokens import WeekdayToken
from k1.temporal.service.window_builder import custom_window, day_window
from k1.temporal.types import ResolvedTemporalExpression, TemporalAnchor


def resolve_weekday(
    raw_text: str, token: WeekdayToken, anchor: TemporalAnchor
) -> ResolvedTemporalExpression:
    base = date.fromisoformat(anchor.local_date)
    if token.direction == "next":
        days = (token.weekday - base.weekday()) % 7 or 7
        target = base + timedelta(days=days)
        window = day_window(token.label, target, anchor.timezone)
        return ResolvedTemporalExpression(
            raw_text, token.label, "window", window, None, None, 0.9, False, None
        )
    if token.direction == "previous":
        days = (base.weekday() - token.weekday) % 7 or 7
        target = base - timedelta(days=days)
        window = day_window(token.label, target, anchor.timezone)
        return ResolvedTemporalExpression(
            raw_text, token.label, "window", window, None, None, 0.9, False, None
        )
    if token.direction == "deadline":
        days = (token.weekday - base.weekday()) % 7
        target = base + timedelta(days=days)
        zone = ZoneInfo(anchor.timezone)
        start_local = datetime.fromisoformat(anchor.now_local)
        if start_local.tzinfo is None:
            start_local = start_local.replace(tzinfo=zone)
        end_local = datetime.combine(target + timedelta(days=1), time.min, tzinfo=zone)
        window = custom_window(token.label, start_local, end_local)
        return ResolvedTemporalExpression(
            raw_text, token.label, "window", window, None, None, 0.86, False, None
        )
    days = (token.weekday - base.weekday()) % 7
    target = base + timedelta(days=days)
    window = day_window(token.label, target, anchor.timezone)
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.86, False, None
    )


__all__ = ["resolve_weekday"]
