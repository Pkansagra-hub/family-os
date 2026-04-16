"""Tests for PrivacyEnforcer (E-MW-3.2).

22 tests in 5 classes covering:
  - GREEN band: full passthrough
  - AMBER band: location_name generalized to location_type label
  - RED band: location stripped, participants masked
  - Unknown/empty band: fail-secure → RED
  - Edge cases: empty participants, all location types, in-place mutation
"""

from __future__ import annotations

import pytest

from k1.memory_writer.envelope.privacy_enforcer import PrivacyEnforcer

# ===========================================================================
# Helpers
# ===========================================================================


def _base_body(**overrides: object) -> dict:
    """Minimal body dict with location and participant fields."""
    defaults: dict = {
        "text": "Had dinner with Mom at Olive Garden",
        "topics": ["dinner", "family"],
        "participants": ["person_mom"],
        "num_participants": 1,
        "sentiment_label": "positive",
        "location_name": "Olive Garden",
        "location_type": "restaurant",
        "place_id": "place_olive_garden",
        "geohash_6": "9q8yyk",
    }
    defaults.update(overrides)
    return defaults


# ===========================================================================
# Tests
# ===========================================================================


class TestGreenBand:
    """GREEN: no modifications to any field."""

    def test_green_no_modifications(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        original = body.copy()
        result = enforcer.enforce(body, "GREEN")
        assert result == original

    def test_green_location_preserved(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(location_name="Olive Garden")
        result = enforcer.enforce(body, "GREEN")
        assert result["location_name"] == "Olive Garden"

    def test_green_participants_preserved(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(participants=["person_mom"])
        result = enforcer.enforce(body, "GREEN")
        assert result["participants"] == ["person_mom"]


class TestAmberBand:
    """AMBER: location_name generalized to location_type label."""

    def test_amber_location_generalized_restaurant(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(location_name="Olive Garden", location_type="restaurant")
        enforcer.enforce(body, "AMBER")
        assert body["location_name"] == "Restaurant"

    def test_amber_location_generalized_hospital(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(location_name="Stanford Hospital", location_type="hospital")
        enforcer.enforce(body, "AMBER")
        assert body["location_name"] == "Hospital"

    def test_amber_location_no_type_fallback(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(location_name="Custom Place", location_type=None)
        enforcer.enforce(body, "AMBER")
        assert body["location_name"] == "Location"

    def test_amber_no_location_noop(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(location_name=None, location_type="restaurant")
        enforcer.enforce(body, "AMBER")
        assert body["location_name"] is None

    def test_amber_participants_preserved(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(participants=["person_mom", "person_dad"])
        enforcer.enforce(body, "AMBER")
        assert body["participants"] == ["person_mom", "person_dad"]

    def test_amber_other_fields_preserved(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "AMBER")
        assert body["text"] == "Had dinner with Mom at Olive Garden"
        assert body["topics"] == ["dinner", "family"]
        assert body["sentiment_label"] == "positive"


class TestRedBand:
    """RED: location stripped entirely, participants masked."""

    def test_red_location_name_stripped(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "RED")
        assert body["location_name"] is None

    def test_red_location_type_stripped(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "RED")
        assert body["location_type"] is None

    def test_red_place_id_stripped(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "RED")
        assert body["place_id"] is None

    def test_red_geohash_stripped(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "RED")
        assert body["geohash_6"] is None

    def test_red_participants_masked(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(participants=["person_mom", "person_dad"])
        enforcer.enforce(body, "RED")
        assert body["participants"] == ["person_redacted_0", "person_redacted_1"]

    def test_red_num_participants_preserved(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(
            participants=["person_mom", "person_dad"],
            num_participants=2,
        )
        enforcer.enforce(body, "RED")
        assert body["num_participants"] == 2

    def test_red_text_preserved(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "RED")
        assert body["text"] == "Had dinner with Mom at Olive Garden"


class TestUnknownBand:
    """Unknown/empty band → fail-secure (RED)."""

    def test_unknown_band_treated_as_red(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "INVALID")
        assert body["location_name"] is None
        assert body["participants"] == ["person_redacted_0"]

    def test_empty_band_treated_as_red(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        enforcer.enforce(body, "")
        assert body["location_name"] is None
        assert body["participants"] == ["person_redacted_0"]


class TestPrivacyEdgeCases:
    """Edge cases for privacy enforcement."""

    def test_empty_participants_red(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body(participants=[])
        enforcer.enforce(body, "RED")
        assert body["participants"] == []

    def test_all_location_types_generalize(self) -> None:
        """Each of 19 LocationType values → correct label."""
        enforcer = PrivacyEnforcer()
        expected = {
            "home": "Home",
            "restaurant": "Restaurant",
            "hospital": "Hospital",
            "school": "School",
            "office": "Office",
            "gym": "Gym",
            "store": "Store",
            "park": "Park",
            "church": "Church",
            "airport": "Airport",
            "hotel": "Hotel",
            "other": "Location",
            "city": "City",
            "university": "University",
            "medical_facility": "Medical Facility",
            "recreational": "Recreation",
            "residence": "Residence",
            "religious_place": "Place of Worship",
            "social_venue": "Social Venue",
        }
        for loc_type, label in expected.items():
            body = _base_body(location_name="SomePlace", location_type=loc_type)
            enforcer.enforce(body, "AMBER")
            assert body["location_name"] == label, f"Failed for {loc_type}"

    def test_body_modified_in_place(self) -> None:
        enforcer = PrivacyEnforcer()
        body = _base_body()
        result = enforcer.enforce(body, "RED")
        assert result is body

    def test_no_location_fields_green_noop(self) -> None:
        enforcer = PrivacyEnforcer()
        body = {"text": "hello", "topics": ["chat"]}
        result = enforcer.enforce(body, "GREEN")
        assert "location_name" not in result
