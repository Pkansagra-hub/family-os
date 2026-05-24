"""Tests for prompt builder temporal projection bridge."""

from __future__ import annotations

from k1.concierge.prompt.affect import AffectBand
from k1.concierge.prompt.builder import (
    DynamicPromptBuilder,
    SSReadConfig,
    _render_temporal_full,
)
from k1.concierge.prompt.mode import PromptMode
from k1.sessionstate.sections.temporal import TemporalSection
from k1.temporal.serialization import anchor_to_dict, window_to_dict
from tests.k1.temporal.helpers import sample_anchor, sample_window


def _temporal_section() -> TemporalSection:
    section = TemporalSection(session_id="s1")
    section.set_data(
        {
            "session_id": "s1",
            "turn_id": "t1",
            "anchor": anchor_to_dict(sample_anchor()),
            "windows": {
                "today": window_to_dict(sample_window("today")),
                "tomorrow": window_to_dict(sample_window("tomorrow")),
            },
            "resolved_expressions": [],
        }
    )
    return section


class _SS:
    def __init__(self, temporal: TemporalSection) -> None:
        self._temporal = temporal

    def get_section(self, name: str):  # type: ignore[no-untyped-def]
        return self._temporal if name == "temporal" else None


def test_temporal_renderer_uses_projection_blocks() -> None:
    text = _render_temporal_full(_temporal_section(), SSReadConfig("temporal", "full"))
    assert "anchor_id: anchor-1" in text
    assert "Denton" not in text


def test_now_block_uses_temporal_section() -> None:
    context = DynamicPromptBuilder().build(
        mode=PromptMode.STANDARD,
        affect_band=AffectBand(band="neutral"),
        ss=_SS(_temporal_section()),
    )
    assert "== NOW ==" in context.system_prompt
    assert "America/Los_Angeles" in context.system_prompt
    assert "Denton" not in context.system_prompt
