"""Integration tests for Gate spatial enrichment + redaction pipeline.

Tests full pipeline:
1. Gate Stage 2.5: Spatial enrichment (spatial_enrich.py)
2. Gate Stage 3: Location privacy redaction (location_privacy.py)
3. Verify internal fields stripped before WAL write
"""

from k0.policy.location_privacy import apply_location_privacy
from k0.policy.spatial_enrich import apply_spatial_enrichment, strip_internal_fields


class TestSpatialEnrichmentRedactionPipeline:
    """Test full Gate spatial pipeline."""

    def test_green_band_full_pipeline(self):
        """Test: GREEN band - full precision maintained."""
        # K1 envelope with full location data
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            },
            "policy_stamp": {"band": "GREEN"},
        }

        # Stage 2.5: Spatial enrichment
        envelope = apply_spatial_enrichment(envelope, "GREEN")

        # Verify enrichment
        assert "_internal_geohash_12" in envelope
        assert envelope["_internal_city"] == "San Francisco"
        assert envelope["_internal_region"] == "CA"
        assert envelope["body"]["location_name"] == "Olive Garden, San Francisco, CA"

        # Stage 3: Location privacy redaction
        envelope = apply_location_privacy(envelope, "GREEN")

        # Verify GREEN band: full precision geohash (12 chars)
        assert "location_geohash" in envelope
        assert len(envelope["location_geohash"]) == 12
        assert envelope["location_precision_m"] == 1

        # Verify lat/lon NOT stripped for GREEN band
        assert "location_lat" in envelope["body"]
        assert "location_lon" in envelope["body"]

        # Strip internal fields before WAL write
        envelope = strip_internal_fields(envelope)

        # Verify internal fields removed
        assert "_internal_geohash_12" not in envelope
        assert "_internal_city" not in envelope
        assert "_internal_region" not in envelope

        # Verify public fields preserved
        assert envelope["body"]["location_name"] == "Olive Garden, San Francisco, CA"
        assert envelope["location_geohash"]  # Public geohash preserved

    def test_amber_band_full_pipeline(self):
        """Test: AMBER band - 5km precision geohash."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            },
            "policy_stamp": {"band": "AMBER"},
        }

        # Stage 2.5: Spatial enrichment
        envelope = apply_spatial_enrichment(envelope, "AMBER")

        # Verify enrichment (same as GREEN)
        assert "_internal_geohash_12" in envelope
        assert envelope["_internal_city"] == "San Francisco"

        # Stage 3: Location privacy redaction
        envelope = apply_location_privacy(envelope, "AMBER")

        # Verify AMBER band: 6-char geohash (~5km precision)
        assert "location_geohash" in envelope
        assert len(envelope["location_geohash"]) == 6
        assert envelope["location_precision_m"] == 5000

        # Verify lat/lon STRIPPED for AMBER band
        assert "location_lat" not in envelope["body"]
        assert "location_lon" not in envelope["body"]

        # Strip internal fields before WAL write
        envelope = strip_internal_fields(envelope)

        # Verify internal fields removed
        assert "_internal_geohash_12" not in envelope
        assert "_internal_city" not in envelope

        # Verify public fields preserved
        assert envelope["body"]["location_name"] == "Olive Garden, San Francisco, CA"
        assert envelope["location_geohash"]  # 6-char geohash preserved

    def test_red_band_full_pipeline(self):
        """Test: RED band - 25km precision geohash."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            },
            "policy_stamp": {"band": "RED"},
        }

        # Stage 2.5: Spatial enrichment
        envelope = apply_spatial_enrichment(envelope, "RED")

        # Verify enrichment (same as GREEN)
        assert "_internal_geohash_12" in envelope

        # Stage 3: Location privacy redaction
        envelope = apply_location_privacy(envelope, "RED")

        # Verify RED band: 4-char geohash (~25km precision)
        assert "location_geohash" in envelope
        assert len(envelope["location_geohash"]) == 4
        assert envelope["location_precision_m"] == 25000

        # Verify lat/lon STRIPPED for RED band
        assert "location_lat" not in envelope["body"]
        assert "location_lon" not in envelope["body"]

        # Strip internal fields before WAL write
        envelope = strip_internal_fields(envelope)

        # Verify internal fields removed
        assert "_internal_geohash_12" not in envelope

        # Verify public fields preserved (location_name preserved for RED)
        assert envelope["location_geohash"]  # 4-char geohash preserved

    def test_missing_location_graceful_degradation(self):
        """Test: Pipeline handles missing location data gracefully."""
        envelope = {
            "body": {
                # No location data from K1
            },
            "policy_stamp": {"band": "GREEN"},
        }

        # Stage 2.5: Spatial enrichment
        envelope = apply_spatial_enrichment(envelope, "GREEN")

        # No enrichment (no lat/lon)
        assert "_internal_geohash_12" not in envelope

        # Stage 3: Location privacy redaction
        envelope = apply_location_privacy(envelope, "GREEN")

        # No redaction (no location data)
        assert "location_geohash" not in envelope

        # Strip internal fields (no-op)
        envelope = strip_internal_fields(envelope)

        # Envelope unchanged
        assert envelope == {"body": {}, "policy_stamp": {"band": "GREEN"}}

    def test_internal_fields_never_persisted(self):
        """Test: Verify internal fields NEVER make it to persistence."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Home, Palo Alto, CA",
                "location_type": "home",
            },
            "policy_stamp": {"band": "GREEN"},
        }

        # Full pipeline
        envelope = apply_spatial_enrichment(envelope, "GREEN")
        envelope = apply_location_privacy(envelope, "GREEN")
        envelope = strip_internal_fields(envelope)

        # Verify NO internal fields in final envelope
        assert "_internal_geohash_12" not in envelope
        assert "_internal_city" not in envelope
        assert "_internal_region" not in envelope

        # Verify only public fields remain
        assert "location_geohash" in envelope
        assert envelope["body"]["location_name"] == "Home, Palo Alto, CA"


class TestP03ConsolidationDataAvailability:
    """Test that P03 consolidation has access to ephemeral internal fields."""

    def test_internal_fields_available_before_strip(self):
        """Test: P03 can access internal fields BEFORE strip_internal_fields()."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
                "location_type": "restaurant",
            },
            "policy_stamp": {"band": "GREEN"},
        }

        # Enrichment + redaction (WITHOUT strip)
        envelope = apply_spatial_enrichment(envelope, "GREEN")
        envelope = apply_location_privacy(envelope, "GREEN")

        # P03 can access internal fields for clustering
        assert envelope["_internal_geohash_12"]  # High-precision for clustering
        assert envelope["_internal_city"] == "San Francisco"
        assert envelope["_internal_region"] == "CA"

        # These internal fields enable:
        # - Spatial clustering (geohash-12 similarity)
        # - City-level consolidation queries ("all SF memories")
        # - Region-level analytics ("all CA memories")

    def test_internal_fields_stripped_before_wal(self):
        """Test: Internal fields stripped BEFORE WAL write (never persisted)."""
        envelope = {
            "body": {
                "location_lat": 37.7749,
                "location_lon": -122.4194,
                "location_name": "Olive Garden, San Francisco, CA",
            },
        }

        envelope = apply_spatial_enrichment(envelope, "GREEN")
        envelope = apply_location_privacy(envelope, "GREEN")

        # Before strip: internal fields present
        assert "_internal_geohash_12" in envelope

        # After strip: internal fields removed
        envelope = strip_internal_fields(envelope)
        assert "_internal_geohash_12" not in envelope
        assert "_internal_city" not in envelope
        assert "_internal_region" not in envelope
