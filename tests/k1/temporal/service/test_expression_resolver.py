"""Tests for deterministic temporal expression resolver."""

from __future__ import annotations

from k1.temporal.service.expression_resolver import resolve_expression_candidate
from tests.k1.temporal.helpers import sample_anchor


async def test_expression_resolver_resolves_catalog_phrase() -> None:
    resolution = await resolve_expression_candidate("tomorrow", sample_anchor())
    assert resolution.needs_clarification is False
    assert resolution.normalized_label == "tomorrow"
    assert resolution.window is not None


async def test_expression_resolver_accepts_iso_date_as_day_window() -> None:
    resolution = await resolve_expression_candidate("2026-05-25", sample_anchor())

    assert resolution.needs_clarification is False
    assert resolution.resolution_kind == "window"
    assert resolution.normalized_label == "2026-05-25"
    assert resolution.window is not None
    assert resolution.window.start_local == "2026-05-25T00:00:00-07:00"
    assert resolution.window.end_local == "2026-05-26T00:00:00-07:00"


async def test_expression_resolver_marks_unknown_ambiguous() -> None:
    resolution = await resolve_expression_candidate("sometime around then", sample_anchor())
    assert resolution.needs_clarification is True
    assert resolution.resolution_kind == "ambiguous"
