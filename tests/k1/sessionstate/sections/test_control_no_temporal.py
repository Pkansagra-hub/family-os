"""M1-E11 ControlSection hard removal checks for temporal mirror state."""

from __future__ import annotations

from k1.sessionstate.sections.control import ControlSection


def test_control_section_has_no_temporal_anchor_api() -> None:
    section = ControlSection(session_id="s-control-no-temporal")

    assert not hasattr(section, "set_temporal_anchor")
    assert not hasattr(section, "get_temporal_anchor")


def test_control_metadata_does_not_expose_temporal_anchor() -> None:
    section = ControlSection(session_id="s-control-no-temporal")

    metadata = section.get_metadata()

    assert "temporal_anchor" not in metadata
    assert "_temporal_anchor" not in section.__dict__
