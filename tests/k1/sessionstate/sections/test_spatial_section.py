"""M3-E4 SpatialSection tests."""

from __future__ import annotations

from k1.sessionstate.sections.spatial import SpatialSection


def test_spatial_section_replace_derives_hot_fields() -> None:
    section = SpatialSection(session_id="s1")

    section.replace(
        {
            "session_id": "s1",
            "turn_id": "t1",
            "current": {
                "context_id": "ctx1",
                "active_place": {"place_id": "home", "label": "Home"},
                "active_device_surface": {"surface_kind": "mobile"},
                "freshness": "live",
            },
            "projection": {
                "semantic_place": "home",
                "precision": "semantic",
                "freshness": "live",
            },
        }
    )

    payload = section.to_dict()
    assert payload["active_place"]["place_id"] == "home"
    assert payload["active_device_surface"] == "mobile"
    assert payload["freshness"] == "live"
    assert section.get_metadata()["has_projection"] is True


def test_spatial_section_flatbuffer_roundtrip() -> None:
    section = SpatialSection(session_id="s1")
    section.set_projection({"semantic_place": "school", "freshness": "degraded"})

    restored = SpatialSection()
    restored.from_flatbuffer(section.to_flatbuffer())

    assert restored.to_dict()["projection"]["semantic_place"] == "school"
    assert restored.to_dict()["freshness"] == "degraded"
