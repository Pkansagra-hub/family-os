"""Ambiguity helpers for temporal expression resolution."""

from __future__ import annotations

from k1.temporal.types import ResolvedTemporalExpression


def ambiguous_resolution(
    raw_text: str, *, reason: str = "unknown_expression"
) -> ResolvedTemporalExpression:
    """Return a canonical ambiguous resolution."""

    return ResolvedTemporalExpression(
        raw_text, "ambiguous", "ambiguous", None, None, None, 0.0, True, reason
    )


def choose_resolution(
    raw_text: str, candidates: tuple[ResolvedTemporalExpression, ...]
) -> ResolvedTemporalExpression:
    """Choose a unique highest-confidence result or mark ambiguous."""

    if not candidates:
        return ambiguous_resolution(raw_text)
    ordered = sorted(candidates, key=lambda item: item.confidence, reverse=True)
    if len(ordered) > 1 and ordered[0].confidence == ordered[1].confidence:
        return ambiguous_resolution(raw_text, reason="multiple_equal_candidates")
    return ordered[0]


__all__ = ["ambiguous_resolution", "choose_resolution"]
