"""M3-E4 PlaceRegistrySection tests."""

from __future__ import annotations

from k1.sessionstate.sections.place_registry import PlaceRegistrySection


def test_place_registry_section_indexes_places_and_geofences() -> None:
    section = PlaceRegistrySection(session_id="s1")

    section.set_registry(
        places=[{"place_id": "home", "label": "Home"}],
        geofences=[{"geofence_id": "geo_home", "place_id": "home"}],
        member_default_places={"actor:parent": ["home"]},
        metadata={"source": "test"},
    )

    assert section.get_places()["home"]["label"] == "Home"
    assert section.get_geofences()["geo_home"]["place_id"] == "home"
    assert section.get_member_default_places()["actor:parent"] == ["home"]
    assert section.get_metadata()["place_count"] == 1


def test_place_registry_section_flatbuffer_roundtrip() -> None:
    section = PlaceRegistrySection(session_id="s1")
    section.replace({"places": {"school": {"place_id": "school", "label": "School"}}})

    restored = PlaceRegistrySection()
    restored.from_flatbuffer(section.to_flatbuffer())

    assert restored.get_places()["school"]["label"] == "School"
