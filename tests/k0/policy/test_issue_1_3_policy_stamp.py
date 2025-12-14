"""Test Issue 1.3: Policy Stamp Propagation & Location Privacy (V1.3).

Tests for:
1. Policy stamp creation and attachment to envelope
2. Policy stamp serialization/deserialization
3. Location masking (geohash) for GREEN/AMBER/RED bands
4. Exact coordinate clearing for AMBER/RED
"""

from __future__ import annotations

import pytest

from k0.policy import (
    PolicyStamp,
    apply_location_privacy,
    attach_policy_stamp_to_envelope,
    create_policy_stamp,
    extract_policy_stamp,
    get_geohash_precision_for_band,
    get_precision_meters_for_band,
    lat_lon_to_geohash,
    mask_location_for_band,
)


class TestPolicyStampCreation:
    """Test policy stamp creation and properties."""

    def test_create_policy_stamp(self) -> None:
        """✅ Create policy stamp with all required fields."""
        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="AMBER",
            obligations=["mask.location.precision", "redact.pii"],
            visible_to=["dad", "mom"],
            decision="ALLOW",
        )

        assert stamp.policy_version == "2025-11-01"
        assert stamp.band == "AMBER"
        assert stamp.obligations == ["mask.location.precision", "redact.pii"]
        assert stamp.visible_to == ["dad", "mom"]
        assert stamp.decision == "ALLOW"
        assert stamp.applied_at is not None

    def test_policy_stamp_applied_at_auto_set(self) -> None:
        """✅ applied_at timestamp auto-set if not provided."""
        stamp = PolicyStamp(
            policy_version="2025-11-01",
            band="GREEN",
            obligations=[],
            visible_to=[],
            decision="ALLOW",
        )
        assert stamp.applied_at is not None

    def test_policy_stamp_serialize_to_dict(self) -> None:
        """✅ Convert policy stamp to dictionary."""
        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="RED",
            obligations=["mask.location.precision"],
            visible_to=["dad"],
            decision="CONDITIONAL",
        )

        stamp_dict = stamp.to_dict()
        assert stamp_dict["policy_version"] == "2025-11-01"
        assert stamp_dict["band"] == "RED"
        assert stamp_dict["decision"] == "CONDITIONAL"
        assert "applied_at" in stamp_dict

    def test_policy_stamp_serialize_to_json(self) -> None:
        """✅ Convert policy stamp to JSON string."""
        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="AMBER",
            obligations=["test"],
            visible_to=["user"],
            decision="ALLOW",
        )

        json_str = stamp.to_json()
        assert isinstance(json_str, str)
        assert "2025-11-01" in json_str
        assert "AMBER" in json_str

    def test_policy_stamp_deserialize_from_dict(self) -> None:
        """✅ Reconstruct policy stamp from dictionary."""
        original = create_policy_stamp(
            policy_version="2025-11-01",
            band="GREEN",
            obligations=["no-redaction"],
            visible_to=["user"],
            decision="ALLOW",
        )

        restored = PolicyStamp.from_dict(original.to_dict())
        assert restored.policy_version == original.policy_version
        assert restored.band == original.band
        assert restored.obligations == original.obligations

    def test_policy_stamp_deserialize_from_json(self) -> None:
        """✅ Reconstruct policy stamp from JSON string."""
        original = create_policy_stamp(
            policy_version="2025-11-01",
            band="RED",
            obligations=["mask.location"],
            visible_to=["admin"],
            decision="ALLOW",
        )

        json_str = original.to_json()
        restored = PolicyStamp.from_json(json_str)
        assert restored.band == original.band
        assert restored.decision == original.decision


class TestPolicyStampAttachment:
    """Test attaching policy stamps to envelopes."""

    def test_attach_policy_stamp_to_envelope(self) -> None:
        """✅ Attach policy stamp to envelope."""
        envelope = {
            "actor": "alice",
            "space_id": "personal:alice",
            "topic": "memory.create",
        }

        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="AMBER",
            obligations=["mask.location.precision"],
            visible_to=["alice"],
            decision="ALLOW",
        )

        result = attach_policy_stamp_to_envelope(envelope, stamp)

        assert "policy_stamp" in result
        assert result["policy_stamp"]["band"] == "AMBER"
        assert result["policy_stamp"]["decision"] == "ALLOW"

    def test_extract_policy_stamp_from_envelope(self) -> None:
        """✅ Extract policy stamp from envelope."""
        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="RED",
            obligations=["mask.location.precision"],
            visible_to=["admin"],
            decision="CONDITIONAL",
        )

        envelope = {"actor": "bob", "policy_stamp": stamp.to_dict()}

        extracted = extract_policy_stamp(envelope)
        assert extracted is not None
        assert extracted.band == "RED"
        assert extracted.decision == "CONDITIONAL"

    def test_extract_policy_stamp_returns_none_if_missing(self) -> None:
        """✅ Return None if policy stamp not in envelope."""
        envelope = {"actor": "charlie", "topic": "events.update"}
        extracted = extract_policy_stamp(envelope)
        assert extracted is None


class TestLocationGeohashing:
    """Test geohash computation for location masking."""

    def test_geohash_precision_green_band(self) -> None:
        """✅ GREEN band uses full precision."""
        precision = get_geohash_precision_for_band("GREEN")
        assert precision == 12  # Full precision

    def test_geohash_precision_amber_band(self) -> None:
        """✅ AMBER band uses 5km precision."""
        precision = get_geohash_precision_for_band("AMBER")
        assert precision == 6  # ~2.4km

    def test_geohash_precision_red_band(self) -> None:
        """✅ RED band uses 25km precision."""
        precision = get_geohash_precision_for_band("RED")
        assert precision == 4  # ~39km

    def test_geohash_meters_green_band(self) -> None:
        """✅ GREEN band precision: 1 meter."""
        meters = get_precision_meters_for_band("GREEN")
        assert meters == 1

    def test_geohash_meters_amber_band(self) -> None:
        """✅ AMBER band precision: 5000 meters (5km)."""
        meters = get_precision_meters_for_band("AMBER")
        assert meters == 5000

    def test_geohash_meters_red_band(self) -> None:
        """✅ RED band precision: 25000 meters (25km)."""
        meters = get_precision_meters_for_band("RED")
        assert meters == 25000

    def test_lat_lon_to_geohash_conversion(self) -> None:
        """✅ Convert valid lat/lon to geohash."""
        # San Francisco: 37.7749, -122.4194
        geohash = lat_lon_to_geohash(37.7749, -122.4194, precision=6)
        assert isinstance(geohash, str)
        assert len(geohash) == 6
        assert all(c in "0123456789bcdefghjkmnpqrstuvwxyz" for c in geohash)

    def test_lat_lon_to_geohash_invalid_latitude(self) -> None:
        """✅ Reject invalid latitude."""
        with pytest.raises(ValueError, match="Invalid latitude"):
            lat_lon_to_geohash(91.0, 0.0, precision=6)

    def test_lat_lon_to_geohash_invalid_longitude(self) -> None:
        """✅ Reject invalid longitude."""
        with pytest.raises(ValueError, match="Invalid longitude"):
            lat_lon_to_geohash(0.0, 181.0, precision=6)

    def test_lat_lon_to_geohash_invalid_precision(self) -> None:
        """✅ Reject invalid precision."""
        with pytest.raises(ValueError, match="Precision must be"):
            lat_lon_to_geohash(0.0, 0.0, precision=13)

    def test_mask_location_green_band(self) -> None:
        """✅ Mask location for GREEN band (full precision)."""
        lat, lon = 37.7749, -122.4194
        geohash, precision_m = mask_location_for_band(lat, lon, "GREEN")

        assert geohash is not None
        assert len(geohash) == 12  # Full precision
        assert precision_m == 1

    def test_mask_location_amber_band(self) -> None:
        """✅ Mask location for AMBER band (5km precision)."""
        lat, lon = 37.7749, -122.4194
        geohash, precision_m = mask_location_for_band(lat, lon, "AMBER")

        assert geohash is not None
        assert len(geohash) == 6  # 5km precision
        assert precision_m == 5000

    def test_mask_location_red_band(self) -> None:
        """✅ Mask location for RED band (25km precision)."""
        lat, lon = 37.7749, -122.4194
        geohash, precision_m = mask_location_for_band(lat, lon, "RED")

        assert geohash is not None
        assert len(geohash) == 4  # 25km precision
        assert precision_m == 25000

    def test_mask_location_none_coordinates(self) -> None:
        """✅ Handle None coordinates gracefully."""
        geohash, precision_m = mask_location_for_band(None, None, "AMBER")
        assert geohash is None
        assert precision_m is None


class TestLocationPrivacyApplication:
    """Test applying location privacy to envelopes."""

    def test_apply_location_privacy_green_band(self) -> None:
        """✅ Apply privacy masking for GREEN band (no masking)."""
        envelope = {
            "actor": "alice",
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
            },
        }

        result = apply_location_privacy(envelope, "GREEN")

        assert "location_geohash" in result
        assert result["location_precision_m"] == 1
        # GREEN keeps exact coordinates
        assert "location_lat" in result["body"]
        assert "location_lon" in result["body"]

    def test_apply_location_privacy_amber_band(self) -> None:
        """✅ Apply privacy masking for AMBER band (5km, clear coords)."""
        envelope = {
            "actor": "alice",
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
            },
        }

        result = apply_location_privacy(envelope, "AMBER")

        assert "location_geohash" in result
        assert result["location_precision_m"] == 5000
        # AMBER clears exact coordinates
        assert "location_lat" not in result["body"]
        assert "location_lon" not in result["body"]

    def test_apply_location_privacy_red_band(self) -> None:
        """✅ Apply privacy masking for RED band (25km, clear coords)."""
        envelope = {
            "actor": "alice",
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
            },
        }

        result = apply_location_privacy(envelope, "RED")

        assert "location_geohash" in result
        assert result["location_precision_m"] == 25000
        # RED clears exact coordinates
        assert "location_lat" not in result["body"]
        assert "location_lon" not in result["body"]

    def test_apply_location_privacy_no_body(self) -> None:
        """✅ Handle envelope without body gracefully."""
        envelope = {"actor": "alice"}
        result = apply_location_privacy(envelope, "AMBER")
        # Should not crash
        assert result == envelope or "location_geohash" not in result

    def test_apply_location_privacy_no_location(self) -> None:
        """✅ Handle body without location coordinates gracefully."""
        envelope = {
            "actor": "alice",
            "body": {"text": "Hello world"},
        }
        result = apply_location_privacy(envelope, "AMBER")
        # Should not crash
        assert result == envelope or "location_geohash" not in result


class TestLocationPrivacyIntegration:
    """Integration tests combining policy stamp + location privacy."""

    def test_envelope_with_policy_stamp_and_location_privacy(self) -> None:
        """✅ Combine policy stamp + location masking in full flow."""
        # Start envelope
        envelope = {
            "actor": "alice",
            "space_id": "personal:alice",
            "band": "AMBER",
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "text": "Visited San Francisco today",
            },
        }

        # 1. Attach policy stamp (PEP decision)
        stamp = create_policy_stamp(
            policy_version="2025-11-01",
            band="AMBER",
            obligations=["mask.location.precision", "redact.pii"],
            visible_to=["alice"],
            decision="ALLOW",
        )
        envelope = attach_policy_stamp_to_envelope(envelope, stamp)

        # 2. Apply location privacy (RedactionCoordinator)
        envelope = apply_location_privacy(envelope, "AMBER")

        # Verify results
        assert "policy_stamp" in envelope
        assert envelope["policy_stamp"]["band"] == "AMBER"
        assert "location_geohash" in envelope
        assert envelope["location_precision_m"] == 5000
        # Exact coordinates cleared
        assert "location_lat" not in envelope["body"]
        assert "location_lon" not in envelope["body"]

    def test_multiple_privacy_bands_in_sequence(self) -> None:
        """✅ Verify different bands produce different geohashes."""
        lat, lon = 37.7749, -122.4194

        envelope_green = {
            "actor": "alice",
            "body": {"location_lat": lat, "location_lon": lon},
        }
        envelope_green = apply_location_privacy(envelope_green, "GREEN")

        envelope_amber = {
            "actor": "alice",
            "body": {"location_lat": lat, "location_lon": lon},
        }
        envelope_amber = apply_location_privacy(envelope_amber, "AMBER")

        envelope_red = {
            "actor": "alice",
            "body": {"location_lat": lat, "location_lon": lon},
        }
        envelope_red = apply_location_privacy(envelope_red, "RED")

        # Different precisions produce different geohashes
        assert envelope_green.get("location_geohash") is not None
        assert envelope_amber.get("location_geohash") is not None
        assert envelope_red.get("location_geohash") is not None

        # AMBER is substring of GREEN (AMBER is 6-char, GREEN is 12-char)
        green_hash = envelope_green["location_geohash"]
        amber_hash = envelope_amber["location_geohash"]
        assert green_hash.startswith(amber_hash)  # Same area, different precision


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
