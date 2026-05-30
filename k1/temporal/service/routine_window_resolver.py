"""Routine-backed expression resolution."""

from __future__ import annotations

from k1.temporal.ports import IRoutinePort
from k1.temporal.service.temporal_tokens import RoutineToken
from k1.temporal.types import ResolvedTemporalExpression, TemporalAnchor


async def resolve_routine_window(
    raw_text: str,
    token: RoutineToken,
    anchor: TemporalAnchor,
    routine_port: IRoutinePort | None,
) -> ResolvedTemporalExpression:
    if routine_port is None:
        return ResolvedTemporalExpression(
            raw_text, token.label, "ambiguous", None, None, None, 0.0, True, "routine_unavailable"
        )
    window = await routine_port.get_window(token.routine_id, anchor)
    if window is None:
        return ResolvedTemporalExpression(
            raw_text, token.label, "ambiguous", None, None, None, 0.0, True, "routine_not_found"
        )
    return ResolvedTemporalExpression(
        raw_text, token.label, "window", window, None, None, 0.82, False, None
    )


__all__ = ["resolve_routine_window"]
