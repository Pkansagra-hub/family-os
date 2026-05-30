"""Tests for the HOT grounding metadata section."""

from __future__ import annotations

from k1.sessionstate.sections.grounding import GroundingSection
from k1.sessionstate.tiers.hot import HotTier


def test_grounding_section_stores_metadata_only_from_service_payload() -> None:
    section = GroundingSection(session_id="s1")
    section.set_data(
        {
            "last_envelope": {
                "envelope_id": "env-1",
                "temporal": {"anchor": {"anchor_id": "ta-1"}},
                "spatial": {"context_id": "unknown"},
                "redactions": ["precise_location"],
            },
            "last_projection": {
                "projection_id": "proj-1",
                "envelope_id": "env-1",
                "consumer": "front",
                "redactions": ["contacts"],
            },
        }
    )

    data = section.to_dict()

    assert data["latest_envelope_id"] == "env-1"
    assert data["latest_projection_ids"] == {"front": "proj-1"}
    assert data["source_temporal_section_version"] == "ta-1"
    assert data["source_spatial_section_version"] == "unknown"
    assert data["redaction_summary"] == ["precise_location", "contacts"]
    assert "last_envelope" not in data
    assert "last_projection" not in data


def test_grounding_section_round_trips_metadata() -> None:
    section = GroundingSection(session_id="s1")
    section.set_envelope_metadata(
        latest_envelope_id="env-1",
        latest_projection_ids={"front": "proj-a", "back": "proj-b"},
        source_temporal_section_version="ta-1",
        source_spatial_section_version="unknown",
        redaction_summary=["location"],
    )

    restored = GroundingSection(session_id="s1")
    restored.from_flatbuffer(section.to_flatbuffer())

    assert restored.get_envelope_metadata() == section.get_envelope_metadata()


def test_grounding_section_clear_for_new_turn_keeps_no_stale_metadata() -> None:
    section = GroundingSection(session_id="s1")
    section.set_envelope_metadata(
        latest_envelope_id="env-1", latest_projection_ids={"front": "proj-1"}
    )

    section.clear_for_new_turn()

    assert section.to_dict()["latest_envelope_id"] is None
    assert section.to_dict()["latest_projection_ids"] == {}


def test_hot_tier_registers_grounding_section() -> None:
    hot = HotTier(session_id="s1")

    section = hot.get_section("grounding")

    assert isinstance(section, GroundingSection)
