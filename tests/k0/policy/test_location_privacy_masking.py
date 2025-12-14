"""Test V1 location geohash masking for GDPR compliance.

Tests for Issue 2.2: Location Geohash Masking
- Verifies GREEN preserves exact coordinates
- Verifies AMBER applies geohash-6 (5km precision)
- Verifies RED applies geohash-4 (25km precision)
- Verifies missing/invalid location handling
"""

import pytest

from k0.policy.redaction import RedactionError, mask_location_for_band


class TestGreenBandNoMasking:
    """Test GREEN band preserves exact coordinates."""

    def test_green_preserves_exact_coordinates(self) -> None:
        """Verify GREEN preserves exact lat/lon coordinates."""
        body = {
            "location_lat": 37.7749,
            "location_lon": -122.4194,
            "text": "Some event",
        }

        masked = mask_location_for_band(body, "GREEN")

        # GREEN: Exact coordinates preserved
        assert masked["location_lat"] == 37.7749
        assert masked["location_lon"] == -122.4194

        # Geohash added with high precision (geohash-12)
        assert "location_geohash" in masked
        assert len(masked["location_geohash"]) == 12  # High precision

        # Precision marker shows exact
        assert masked["location_precision_m"] == 1

        # Other fields unchanged
        assert masked["text"] == "Some event"

    def test_green_high_precision_geohash(self) -> None:
        """Verify GREEN uses geohash-12 (highest precision)."""
        body = {"location_lat": 51.5074, "location_lon": -0.1278}

        masked = mask_location_for_band(body, "GREEN")

        # London coordinates should produce geohash starting with "gcpv"
        assert masked["location_geohash"].startswith("gcpv")
        assert len(masked["location_geohash"]) == 12


class TestAmberBand5kmMasking:
    """Test AMBER band applies geohash-6 (5km precision)."""

    def test_amber_masks_to_5km_precision(self) -> None:
        """Verify AMBER applies geohash-6 (5km precision) and clears exact coords."""
        body = {
            "location_lat": 37.7749,
            "location_lon": -122.4194,
            "text": "Private event",
        }

        masked = mask_location_for_band(body, "AMBER")

        # AMBER: Exact coordinates CLEARED (GDPR compliance)
        assert masked["location_lat"] is None
        assert masked["location_lon"] is None

        # Geohash with 5km precision (geohash-6)
        assert "location_geohash" in masked
        assert len(masked["location_geohash"]) == 6

        # Precision marker shows 5km
        assert masked["location_precision_m"] == 5000

        # Other fields unchanged
        assert masked["text"] == "Private event"

    def test_amber_geohash_coarse_enough(self) -> None:
        """Verify AMBER geohash-6 is coarse enough for privacy."""
        # Two nearby locations should get same geohash-6
        loc1 = {"location_lat": 37.7749, "location_lon": -122.4194}
        loc2 = {"location_lat": 37.7750, "location_lon": -122.4195}

        masked1 = mask_location_for_band(loc1, "AMBER")
        masked2 = mask_location_for_band(loc2, "AMBER")

        # Same geohash-6 (within 5km box)
        assert masked1["location_geohash"] == masked2["location_geohash"]


class TestRedBand25kmMasking:
    """Test RED band applies geohash-4 (25km precision)."""

    def test_red_masks_to_25km_precision(self) -> None:
        """Verify RED applies geohash-4 (25km precision) and clears exact coords."""
        body = {
            "location_lat": 37.7749,
            "location_lon": -122.4194,
            "text": "Sensitive event",
        }

        masked = mask_location_for_band(body, "RED")

        # RED: Exact coordinates CLEARED (GDPR compliance)
        assert masked["location_lat"] is None
        assert masked["location_lon"] is None

        # Geohash with 25km precision (geohash-4)
        assert "location_geohash" in masked
        assert len(masked["location_geohash"]) == 4

        # Precision marker shows 25km
        assert masked["location_precision_m"] == 25000

        # Other fields unchanged
        assert masked["text"] == "Sensitive event"

    def test_red_geohash_very_coarse(self) -> None:
        """Verify RED geohash-4 is very coarse for high sensitivity."""
        # San Francisco should get geohash "9q8y"
        body = {"location_lat": 37.7749, "location_lon": -122.4194}

        masked = mask_location_for_band(body, "RED")

        # Verify very coarse geohash
        assert masked["location_geohash"] == "9q8y"
        assert len(masked["location_geohash"]) == 4


class TestMissingLocationHandling:
    """Test handling of missing or invalid location fields."""

    def test_missing_location_ignored(self) -> None:
        """Verify missing location fields pass through unchanged."""
        body = {"text": "Event without location"}

        masked = mask_location_for_band(body, "AMBER")

        # No location fields added
        assert "location_lat" not in masked
        assert "location_lon" not in masked
        assert "location_geohash" not in masked
        assert "location_precision_m" not in masked

        # Other fields unchanged
        assert masked["text"] == "Event without location"

    def test_partial_location_error(self) -> None:
        """Verify partial location (only lat or only lon) raises error."""
        # Only latitude
        body = {"location_lat": 37.7749}

        with pytest.raises(RedactionError) as exc_info:
            mask_location_for_band(body, "AMBER")

        assert "both location_lat and location_lon must be present" in str(exc_info.value)

        # Only longitude
        body = {"location_lon": -122.4194}

        with pytest.raises(RedactionError) as exc_info:
            mask_location_for_band(body, "AMBER")

        assert "both location_lat and location_lon must be present" in str(exc_info.value)

    def test_invalid_latitude_error(self) -> None:
        """Verify invalid latitude raises error."""
        body = {"location_lat": 91.0, "location_lon": -122.4194}  # Latitude > 90

        with pytest.raises(RedactionError) as exc_info:
            mask_location_for_band(body, "AMBER")

        assert "Invalid latitude" in str(exc_info.value)

    def test_invalid_longitude_error(self) -> None:
        """Verify invalid longitude raises error."""
        body = {"location_lat": 37.7749, "location_lon": 181.0}  # Longitude > 180

        with pytest.raises(RedactionError) as exc_info:
            mask_location_for_band(body, "AMBER")

        assert "Invalid longitude" in str(exc_info.value)

    def test_non_numeric_coordinates_error(self) -> None:
        """Verify non-numeric coordinates raise error."""
        body = {"location_lat": "invalid", "location_lon": -122.4194}

        with pytest.raises(RedactionError) as exc_info:
            mask_location_for_band(body, "AMBER")

        assert "Invalid location coordinates" in str(exc_info.value)


class TestUnknownBandTreatedAsRed:
    """Test unknown bands treated as RED (most conservative)."""

    def test_unknown_band_uses_red_masking(self) -> None:
        """Verify unknown band applies RED-level masking."""
        body = {"location_lat": 37.7749, "location_lon": -122.4194}

        masked = mask_location_for_band(body, "UNKNOWN")

        # Should apply RED-level masking (25km)
        assert masked["location_lat"] is None
        assert masked["location_lon"] is None
        assert len(masked["location_geohash"]) == 4
        assert masked["location_precision_m"] == 25000


class TestCustomFieldNames:
    """Test custom latitude/longitude field names."""

    def test_custom_field_names(self) -> None:
        """Verify custom lat/lon field names work."""
        body = {"lat": 37.7749, "lon": -122.4194}

        masked = mask_location_for_band(body, "AMBER", lat_field="lat", lon_field="lon")

        # Custom fields masked
        assert masked["lat"] is None
        assert masked["lon"] is None

        # Geohash added
        assert "location_geohash" in masked
        assert masked["location_precision_m"] == 5000


class TestOriginalBodyUnchanged:
    """Test original body dict is not mutated."""

    def test_original_body_not_mutated(self) -> None:
        """Verify mask_location_for_band() does not mutate original body."""
        original = {"location_lat": 37.7749, "location_lon": -122.4194, "text": "Event"}

        masked = mask_location_for_band(original, "AMBER")

        # Original unchanged
        assert original["location_lat"] == 37.7749
        assert original["location_lon"] == -122.4194
        assert "location_geohash" not in original

        # Masked has changes
        assert masked["location_lat"] is None
        assert masked["location_lon"] is None
        assert "location_geohash" in masked


# Run with: pytest tests/k0/policy/test_location_privacy_masking.py -v
