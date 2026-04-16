"""
k1.memory_writer.envelope.privacy_enforcer -- Band-based field stripping.

Runs AFTER FieldMapper, BEFORE DeltaAggregator.
Defense-in-depth: K0 Gate also enforces band policies.

Bands:
  GREEN: No modifications
  AMBER: location_name generalized to location_type category
  RED:   location stripped entirely, participants masked
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class PrivacyEnforcer:
    """Band-based field stripping on envelope body dicts.

    Runs AFTER FieldMapper, BEFORE DeltaAggregator.
    Defense-in-depth: K0 Gate also enforces band policies.

    Bands:
      GREEN: No modifications
      AMBER: location_name generalized to location_type category
      RED:   location stripped entirely, participants masked
    """

    # AMBER generalization: location_type → user-friendly label
    _LOCATION_TYPE_LABELS: dict[str, str] = {
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
        # v2.3 expansion -- from POC Gemini outputs
        "city": "City",
        "university": "University",
        "medical_facility": "Medical Facility",
        "recreational": "Recreation",
        "residence": "Residence",
        "religious_place": "Place of Worship",
        "social_venue": "Social Venue",
    }

    def enforce(self, body: dict, band: str) -> dict:
        """Apply band-based field stripping to an envelope body dict.

        Args:
            body: Mutable body dict from FieldMapper.
            band: Privacy band (GREEN/AMBER/RED).

        Returns:
            The same body dict (modified in place for AMBER/RED).
        """
        if band == "GREEN":
            return body

        if band == "AMBER":
            return self._enforce_amber(body)

        if band == "RED":
            return self._enforce_red(body)

        # Unknown band → treat as RED (fail-secure)
        log.warning("MW: unknown privacy band, treating as RED", extra={"band": band})
        return self._enforce_red(body)

    def _enforce_amber(self, body: dict) -> dict:
        """AMBER: generalize location_name to category label."""
        loc_type = body.get("location_type")
        if body.get("location_name"):
            if loc_type:
                body["location_name"] = self._LOCATION_TYPE_LABELS.get(loc_type, "Location")
            else:
                body["location_name"] = "Location"
        return body

    def _enforce_red(self, body: dict) -> dict:
        """RED: strip all location, mask participants."""
        # Strip location entirely
        body["location_name"] = None
        body["location_type"] = None
        body["place_id"] = None
        body["geohash_6"] = None

        # Mask participants (preserve count for analytics)
        participants = body.get("participants", [])
        body["participants"] = [f"person_redacted_{i}" for i in range(len(participants))]
        # num_participants preserved — count is non-identifying

        return body
