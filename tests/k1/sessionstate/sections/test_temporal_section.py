"""Tests for TemporalSection."""

from __future__ import annotations

from k1.sessionstate.sections.temporal import TemporalSection


def test_temporal_section_round_trips_json_payload() -> None:
    section = TemporalSection(session_id="s1")
    payload = {
        "session_id": "s1",
        "turn_id": "t1",
        "anchor": {"anchor_id": "a1", "timezone": "UTC"},
        "windows": {"today": {"label": "today"}},
        "resolved_expressions": [{"raw_text": "tomorrow"}],
        "provenance": [{"source": "test"}],
    }

    section.set_data(payload)
    restored = TemporalSection(session_id="s1")
    restored.from_flatbuffer(section.to_flatbuffer())

    assert restored.get_anchor() == payload["anchor"]
    assert restored.get_windows() == payload["windows"]
    assert restored.get_resolutions() == payload["resolved_expressions"]
    assert restored.to_dict()["last_turn_id"] == "t1"


def test_temporal_section_clear_for_new_turn_keeps_anchor() -> None:
    section = TemporalSection(session_id="s1")
    section.set_anchor({"anchor_id": "a1"})
    section.set_resolutions([{"raw_text": "today"}])
    section.clear_for_new_turn()
    assert section.get_anchor() == {"anchor_id": "a1"}
    assert section.get_resolutions() == []
