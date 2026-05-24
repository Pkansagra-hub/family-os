"""Deterministic temporal expression resolver."""

from __future__ import annotations

from k1.temporal.ports import IRoutinePort
from k1.temporal.service.ambiguity_resolver import ambiguous_resolution
from k1.temporal.service.expression_candidates import (
    ensure_candidate,
    normalize_candidate_text,
)
from k1.temporal.service.offset_rules import (
    resolve_month_window,
    resolve_offset,
    resolve_week_window,
)
from k1.temporal.service.phrase_catalog import lookup_phrase
from k1.temporal.service.relative_day_rules import resolve_daypart, resolve_relative_day
from k1.temporal.service.routine_window_resolver import resolve_routine_window
from k1.temporal.service.temporal_tokens import (
    DayPartToken,
    MonthWindowToken,
    OffsetToken,
    RelativeDayToken,
    RoutineToken,
    WeekdayToken,
    WeekWindowToken,
)
from k1.temporal.service.weekday_rules import resolve_weekday
from k1.temporal.types import CandidateSpan, ResolvedTemporalExpression, TemporalAnchor


async def resolve_expression_candidate(
    candidate: str | CandidateSpan,
    anchor: TemporalAnchor,
    *,
    routine_port: IRoutinePort | None = None,
) -> ResolvedTemporalExpression:
    """Resolve one typed candidate using catalog and deterministic rules."""

    value = ensure_candidate(candidate, locale=anchor.locale or "en-US")
    normalized = normalize_candidate_text(value.text)
    token = lookup_phrase(normalized)
    if token is None and routine_port is not None:
        token = await _routine_token_from_phrase(normalized, routine_port)
    if isinstance(token, RelativeDayToken):
        return resolve_relative_day(value.text, token, anchor)
    if isinstance(token, DayPartToken):
        return resolve_daypart(value.text, token, anchor)
    if isinstance(token, WeekdayToken):
        return resolve_weekday(value.text, token, anchor)
    if isinstance(token, WeekWindowToken):
        return resolve_week_window(value.text, token, anchor)
    if isinstance(token, MonthWindowToken):
        return resolve_month_window(value.text, token, anchor)
    if isinstance(token, OffsetToken):
        return resolve_offset(value.text, token, anchor)
    if isinstance(token, RoutineToken):
        return await resolve_routine_window(value.text, token, anchor, routine_port)
    return ambiguous_resolution(value.text)


async def _routine_token_from_phrase(
    normalized: str, routine_port: IRoutinePort
) -> RoutineToken | None:
    if not normalized.startswith("after ") and not normalized.startswith("before "):
        return None
    target = normalized.split(" ", 1)[1]
    routines = await routine_port.list_routines()
    for routine in routines:
        if normalize_candidate_text(routine.label) == target or routine.routine_id == target:
            return RoutineToken(routine.routine_id, normalized.replace(" ", "_"))
    return None


__all__ = ["resolve_expression_candidate"]
