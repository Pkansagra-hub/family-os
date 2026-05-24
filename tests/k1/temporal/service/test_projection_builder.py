"""Tests for projection builder and renderer."""

from __future__ import annotations

from k1.temporal.serialization import anchor_to_dict, window_to_dict
from k1.temporal.service.projection_builder import build_projection
from k1.temporal.service.projection_renderer import render_projection
from tests.k1.temporal.helpers import sample_anchor, sample_window


def test_projection_builder_and_renderer_keep_structured_summary() -> None:
    anchor = sample_anchor()
    projection = build_projection(
        {"anchor": anchor_to_dict(anchor), "windows": {"today": window_to_dict(sample_window())}},
        consumer="front",
        now_utc=anchor.now_utc,
    )
    rendered = render_projection(projection)
    assert projection.freshness == "live"
    assert rendered["summary"]["timezone"] == "America/Los_Angeles"
