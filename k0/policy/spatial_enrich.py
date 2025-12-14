"""Gate Stage 2.5: Spatial Enrichment (PRE-REDACTION)

Enriches location data BEFORE privacy redaction is applied.
This is the ONLY place where raw lat/lon coordinates are accessible.

**Purpose**:
- Copy location_name, location_type from K1 envelope (K1 does geocoding)
- Compute full geohash-12 for clustering (internal use only, never persisted)
- Attach city/region metadata for consolidation queries
- Enable rich spatial queries while maintaining privacy

**NO EXTERNAL DEPENDENCIES**:
- K0 is persistent storage ONLY - no cloud API calls
- K1 provides pre-geocoded location_name and location_type
- K0 just validates and copies enrichments from K1 envelope
- Local SQLite lookup for favorite/saved places (optional)

**Privacy Guarantee**:
- Enrichments are computed but NOT stored in st_hipp_events for AMBER/RED
- Only geohash (truncated) and location_name (if safe) are persisted
- Raw lat/lon is stripped AFTER enrichment by location_privacy stage

**Performance**: <3ms P95 (copy + geohash computation only, no I/O)

**Pipeline Order**:
1. Gate Stage 1: Schema validation
2. Gate Stage 2: Policy evaluation
3. Gate Stage 2.5: Spatial enrichment (THIS MODULE) ← NEW
4. Gate Stage 3: Location privacy redaction (location_privacy.py)
5. Gate Stage 4: WAL write

Contract: k0/contracts/modules/context.geo_metadata.v1.yaml (M12 equivalent)
ADR: k007.5 (Geo Metadata Lookup - Privacy-Preserving Location)
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from .location_privacy import lat_lon_to_geohash

logger = logging.getLogger(__name__)

# ===========================
# Metrics for observability
# ===========================

_metrics = {
    "total_enrichments": 0,
    "lat_lon_missing": 0,
    "lat_lon_invalid": 0,
    "location_name_copied": 0,
    "location_type_copied": 0,
    "location_name_missing": 0,
    "location_type_missing": 0,
    "geohash_12_computed": 0,
    "geohash_12_failed": 0,
    "city_region_extracted": 0,
}


def extract_city_region(location_name: str | None) -> tuple[str | None, str | None]:
    """Extract city and region from location name (basic parsing).

    K1 should provide structured address in location_name format:
    - Format: "Place Name, City, Region" (e.g., "Olive Garden, San Francisco, CA")
    - Format: "Place Name, City" (e.g., "Home, Palo Alto")
    - Format: "Place Name" (e.g., "Golden Gate Park")

    Simple heuristic parsing:
    - Split by commas
    - Last token = region (if present)
    - Second-to-last token = city (if present)

    Args:
        location_name: Human-readable location name from K1 envelope

    Returns:
        Tuple of (city, region)
        - city: "San Francisco" or None
        - region: "CA" or None

    Performance: <1ms (string parsing)
    """
    if not location_name:
        return None, None

    # Split by commas and strip whitespace
    parts = [part.strip() for part in location_name.split(",")]

    if len(parts) >= 3:
        # Format: "Place, City, Region"
        city = parts[-2]
        region = parts[-1]
        return city, region
    elif len(parts) == 2:
        # Format: "Place, City" (no region)
        city = parts[-1]
        return city, None
    else:
        # Format: "Place" (no city or region)
        return None, None


def enrich_spatial_metadata(
    envelope: dict[str, Any],
    band: Literal["GREEN", "AMBER", "RED"],
) -> dict[str, Any]:
    """Enrich spatial metadata from K1 envelope (BEFORE redaction).

    This runs BEFORE location_privacy.apply_location_privacy() strips lat/lon.

    **NO EXTERNAL DEPENDENCIES**:
    - K1 provides pre-geocoded location_name and location_type in body
    - K0 just copies these fields (no API calls, no cloud dependencies)
    - Compute geohash-12 from lat/lon for internal clustering
    - Parse city/region from location_name string (basic heuristics)

    **Enrichments Added**:
    1. _internal_geohash_12: Full-precision geohash for clustering (never persisted to st_hipp_events)
    2. body.location_name: Copied from K1 envelope (K1 does geocoding)
    3. body.location_type: Copied from K1 envelope (K1 does classification)
    4. _internal_city: City name parsed from location_name (never persisted)
    5. _internal_region: Region/state parsed from location_name (never persisted)

    **Privacy Notes**:
    - _internal_* fields are NEVER written to st_hipp_events
    - Used only for P03 consolidation clustering (ephemeral)
    - Stripped before WAL write (removed in command port)
    - location_name/location_type are safe for AMBER/GREEN (no exact coordinates)
    - RED band: location_name is also stripped by location_privacy stage

    Args:
        envelope: Envelope to enrich (mutated in-place)
        band: Privacy band (GREEN/AMBER/RED) - used for logging only

    Returns:
        Modified envelope with spatial enrichments

    Performance: <3ms P95 (copy + geohash computation only, no I/O)
    """
    _metrics["total_enrichments"] += 1

    # Extract location from body
    body = envelope.get("body")
    if not isinstance(body, dict):
        _metrics["lat_lon_missing"] += 1
        return envelope

    lat = body.get("location_lat")
    lon = body.get("location_lon")

    if lat is None or lon is None:
        _metrics["lat_lon_missing"] += 1
        return envelope

    # Validate coordinates
    try:
        lat_float = float(lat)
        lon_float = float(lon)

        if not (-90 <= lat_float <= 90):
            logger.warning(f"Invalid latitude: {lat_float}")
            _metrics["lat_lon_invalid"] += 1
            return envelope

        if not (-180 <= lon_float <= 180):
            logger.warning(f"Invalid longitude: {lon_float}")
            _metrics["lat_lon_invalid"] += 1
            return envelope

    except (ValueError, TypeError) as exc:
        logger.warning(f"Invalid lat/lon types: {type(lat)}, {type(lon)}: {exc}")
        _metrics["lat_lon_invalid"] += 1
        return envelope

    # Compute full-precision geohash-12 for clustering (internal use only)
    try:
        geohash_12 = lat_lon_to_geohash(lat_float, lon_float, precision=12)
        envelope["_internal_geohash_12"] = geohash_12
        _metrics["geohash_12_computed"] += 1
        logger.debug(
            f"Computed geohash-12: {geohash_12}",
            extra={"band": band, "geohash_12": geohash_12},
        )
    except Exception as exc:
        logger.warning(f"Failed to compute geohash-12: {exc}")
        _metrics["geohash_12_failed"] += 1
        # Continue without internal geohash (not critical)

    # Copy location_name and location_type from K1 envelope (K1 does geocoding)
    # K0 is persistent storage only - no external API calls
    location_name = body.get("location_name")
    location_type = body.get("location_type")

    if location_name is not None:
        # Already present in body from K1 - just track metric
        _metrics["location_name_copied"] += 1
        logger.debug(
            f"Location name from K1: {location_name}",
            extra={"band": band, "location_name": location_name},
        )
    else:
        _metrics["location_name_missing"] += 1
        logger.debug(
            "No location_name from K1 (geocoding may not be available)",
            extra={"band": band},
        )

    if location_type is not None:
        # Already present in body from K1 - just track metric
        _metrics["location_type_copied"] += 1
        logger.debug(
            f"Location type from K1: {location_type}",
            extra={"band": band, "location_type": location_type},
        )
    else:
        _metrics["location_type_missing"] += 1

    # Extract city and region for consolidation queries (internal use only)
    if location_name is not None:
        city, region = extract_city_region(location_name)
        if city is not None or region is not None:
            _metrics["city_region_extracted"] += 1
        if city is not None:
            envelope["_internal_city"] = city
            logger.debug(f"Extracted city: {city}", extra={"band": band, "city": city})
        if region is not None:
            envelope["_internal_region"] = region
            logger.debug(f"Extracted region: {region}", extra={"band": band, "region": region})

    return envelope


def apply_spatial_enrichment(
    envelope: dict[str, Any],
    band: Literal["GREEN", "AMBER", "RED"],
) -> dict[str, Any]:
    """Public API for spatial enrichment (called from gate pipeline).

    Wrapper around enrich_spatial_metadata with error handling and logging.

    Args:
        envelope: Envelope to enrich (mutated in-place)
        band: Privacy band (GREEN/AMBER/RED)

    Returns:
        Modified envelope with spatial enrichments

    Raises:
        No exceptions raised - all errors are logged and gracefully handled
    """
    try:
        return enrich_spatial_metadata(envelope, band)
    except Exception as exc:
        logger.exception(
            "Spatial enrichment failed, continuing without enrichment",
            extra={"band": band, "error": str(exc)},
            exc_info=exc,
        )
        # Return unmodified envelope (fail gracefully)
        return envelope


def strip_internal_fields(envelope: dict[str, Any]) -> dict[str, Any]:
    """Strip internal spatial fields before WAL write.

    Internal fields are for P03 consolidation only (ephemeral):
    - _internal_geohash_12: High-precision geohash for clustering
    - _internal_city: City name for consolidation queries
    - _internal_region: Region/state for consolidation queries

    These fields are NEVER persisted to st_hipp_events or WAL.

    Args:
        envelope: Envelope to clean (mutated in-place)

    Returns:
        Modified envelope without internal fields

    Performance: <1ms (dict key deletion)
    """
    envelope.pop("_internal_geohash_12", None)
    envelope.pop("_internal_city", None)
    envelope.pop("_internal_region", None)
    return envelope


def get_metrics() -> dict[str, int]:
    """Get spatial enrichment metrics for observability.

    Returns:
        Dict with 10 metrics:
        - total_enrichments: Total enrichment attempts
        - lat_lon_missing/invalid: Input validation failures
        - location_name/type_copied: K1 data copied successfully
        - location_name/type_missing: K1 data not provided
        - geohash_12_computed/failed: Geohash computation results
        - city_region_extracted: City/region parsing successes
    """
    return _metrics.copy()


def reset_metrics() -> None:
    """Reset all metrics to zero (for testing)."""
    for key in _metrics:
        _metrics[key] = 0


__all__ = [
    "apply_spatial_enrichment",
    "enrich_spatial_metadata",
    "extract_city_region",
    "get_metrics",
    "reset_metrics",
    "strip_internal_fields",
]
