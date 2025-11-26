"""Unit tests for k0.policy.spatial_enrich module.

Tests:
1. Copy location_name and location_type from K1 envelope
2. Compute geohash-12 for clustering
3. Extract city/region from location_name
4. Strip internal fields before persistence
5. AMBER/RED band behavior
6. Missing/invalid lat/lon handling
7. Metrics tracking
"""

import pytest

from k0.policy.spatial_enrich import (
    apply_spatial_enrichment,
    enrich_spatial_metadata,
    extract_city_region,
    get_metrics,
    reset_metrics,
    strip_internal_fields,
)


@pytest.fixture(autouse=True)
def reset_spatial_metrics():
    """Reset metrics before each test."""
    reset_metrics()
    yield
    reset_metrics()


class TestExtractCityRegion:
    """Test city/region extraction from location_name."""

    def test_full_address_format(self):
        """Test: Place, City, Region format."""
        location_name = "Olive Garden, San Francisco, CA"
        city, region = extract_city_region(location_name)
        assert city == "San Francisco"
        assert region == "CA"

    def test_place_city_format(self):
        """Test: Place, City format (no region)."""
        location_name = "Home, Palo Alto"
        city, region = extract_city_region(location_name)
        assert city == "Palo Alto"
        assert region is None

    def test_place_only_format(self):
        """Test: Place only (no city or region)."""
        location_name = "Golden Gate Park"
        city, region = extract_city_region(location_name)
        assert city is None
        assert region is None

    def test_none_input(self):
        """Test: None input returns None, None."""
        city, region = extract_city_region(None)
        assert city is None
        assert region is None

    def test_empty_string(self):
        """Test: Empty string returns None, None."""
        city, region = extract_city_region("")
        assert city is None
        assert region is None

    def test_whitespace_handling(self):
        """Test: Whitespace is stripped correctly."""
        location_name = "  Starbucks  ,  San Jose  ,  CA  "
        city, region = extract_city_region(location_name)
        assert city == "San Jose"
        assert region == "CA"


class TestEnrichSpatialMetadata:
    """Test spatial enrichment from K1 envelope."""

    def test_copy_location_from_k1(self):
        """Test: Copy location_name and location_type from K1 envelope."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            }
        }

        result = enrich_spatial_metadata(envelope, "GREEN")

        # Location fields should remain unchanged (already in body from K1)
        assert result["body"]["location_name"] == "Olive Garden, San Francisco, CA"
        assert result["body"]["location_type"] == "restaurant"

        # Internal geohash-12 computed
        assert "_internal_geohash_12" in result
        assert len(result["_internal_geohash_12"]) == 12

        # City and region extracted
        assert result["_internal_city"] == "San Francisco"
        assert result["_internal_region"] == "CA"

        # Metrics updated
        metrics = get_metrics()
        assert metrics["location_name_copied"] == 1
        assert metrics["location_type_copied"] == 1
        assert metrics["geohash_12_computed"] == 1
        assert metrics["city_region_extracted"] == 1

    def test_missing_location_name_from_k1(self):
        """Test: K1 did not provide location_name (geocoding unavailable)."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                # No location_name or location_type from K1
            }
        }

        result = enrich_spatial_metadata(envelope, "GREEN")

        # Internal geohash-12 still computed
        assert "_internal_geohash_12" in result
        assert len(result["_internal_geohash_12"]) == 12

        # No city/region (no location_name to parse)
        assert "_internal_city" not in result
        assert "_internal_region" not in result

        # Metrics updated
        metrics = get_metrics()
        assert metrics["location_name_missing"] == 1
        assert metrics["location_type_missing"] == 1
        assert metrics["geohash_12_computed"] == 1

    def test_missing_lat_lon(self):
        """Test: No lat/lon in envelope."""
        envelope = {
            "body": {
                "location_name": "Olive Garden, San Francisco, CA",
                # No location_lat or location_lon
            }
        }

        result = enrich_spatial_metadata(envelope, "GREEN")

        # No enrichment possible without lat/lon
        assert "_internal_geohash_12" not in result
        assert "_internal_city" not in result
        assert "_internal_region" not in result

        # Metrics updated
        metrics = get_metrics()
        assert metrics["lat_lon_missing"] == 1

    def test_invalid_lat_lon(self):
        """Test: Invalid lat/lon values."""
        envelope = {
            "body": {
                "location_lat": 999.0,  # Invalid (>90)
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
            }
        }

        result = enrich_spatial_metadata(envelope, "GREEN")

        # No enrichment with invalid coordinates
        assert "_internal_geohash_12" not in result

        # Metrics updated
        metrics = get_metrics()
        assert metrics["lat_lon_invalid"] == 1

    def test_geohash_computation(self):
        """Test: Geohash-12 computed correctly."""
        envelope = {
            "body": {
                "location_lat": 37.7749,  # San Francisco
                "location_lon": -122.4194,
            }
        }

        result = enrich_spatial_metadata(envelope, "GREEN")

        # Geohash-12 computed
        geohash = result["_internal_geohash_12"]
        assert len(geohash) == 12
        assert geohash.startswith("9q8yy")  # San Francisco geohash prefix

    def test_amber_band_behavior(self):
        """Test: AMBER band enrichment (same as GREEN for enrichment stage)."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            }
        }

        result = enrich_spatial_metadata(envelope, "AMBER")

        # Enrichment same as GREEN (redaction happens in location_privacy stage)
        assert result["body"]["location_name"] == "Olive Garden, San Francisco, CA"
        assert "_internal_geohash_12" in result
        assert result["_internal_city"] == "San Francisco"

    def test_red_band_behavior(self):
        """Test: RED band enrichment (same as GREEN for enrichment stage)."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            }
        }

        result = enrich_spatial_metadata(envelope, "RED")

        # Enrichment happens regardless of band (redaction is separate)
        assert result["body"]["location_name"] == "Olive Garden, San Francisco, CA"
        assert "_internal_geohash_12" in result
        assert result["_internal_city"] == "San Francisco"


class TestStripInternalFields:
    """Test stripping internal fields before persistence."""

    def test_strip_all_internal_fields(self):
        """Test: All _internal_* fields removed."""
        envelope = {
            "body": {"text": "test"},
            "_internal_geohash_12": "9q8yy9mf2vjd",
            "_internal_city": "San Francisco",
            "_internal_region": "CA",
            "other_field": "keep_this",
        }

        result = strip_internal_fields(envelope)

        # Internal fields removed
        assert "_internal_geohash_12" not in result
        assert "_internal_city" not in result
        assert "_internal_region" not in result

        # Other fields preserved
        assert result["body"] == {"text": "test"}
        assert result["other_field"] == "keep_this"

    def test_strip_partial_internal_fields(self):
        """Test: Only present internal fields removed."""
        envelope = {
            "_internal_geohash_12": "9q8yy9mf2vjd",
            # No _internal_city or _internal_region
        }

        result = strip_internal_fields(envelope)

        # Only geohash removed (others not present)
        assert "_internal_geohash_12" not in result

    def test_strip_no_internal_fields(self):
        """Test: No internal fields to remove."""
        envelope = {
            "body": {"text": "test"},
            "other_field": "keep_this",
        }

        result = strip_internal_fields(envelope)

        # Envelope unchanged
        assert result == {"body": {"text": "test"}, "other_field": "keep_this"}


class TestApplySpatialEnrichment:
    """Test public API wrapper."""

    def test_success_path(self):
        """Test: Successful enrichment via public API."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            }
        }

        result = apply_spatial_enrichment(envelope, "GREEN")

        # Enrichment successful
        assert "_internal_geohash_12" in result
        assert result["_internal_city"] == "San Francisco"

    def test_error_handling(self):
        """Test: Graceful error handling in public API."""
        # Invalid envelope (body is not dict)
        envelope = {"body": "invalid"}

        result = apply_spatial_enrichment(envelope, "GREEN")

        # Envelope returned unchanged (fail gracefully)
        assert result == {"body": "invalid"}


class TestMetrics:
    """Test metrics tracking."""

    def test_metrics_tracking(self):
        """Test: All metrics tracked correctly."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            }
        }

        enrich_spatial_metadata(envelope, "GREEN")

        metrics = get_metrics()
        assert metrics["total_enrichments"] == 1
        assert metrics["location_name_copied"] == 1
        assert metrics["location_type_copied"] == 1
        assert metrics["geohash_12_computed"] == 1
        assert metrics["city_region_extracted"] == 1
        assert metrics["lat_lon_missing"] == 0
        assert metrics["lat_lon_invalid"] == 0

    def test_metrics_reset(self):
        """Test: Metrics reset correctly."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
            }
        }

        enrich_spatial_metadata(envelope, "GREEN")
        assert get_metrics()["total_enrichments"] == 1

        reset_metrics()
        assert get_metrics()["total_enrichments"] == 0
