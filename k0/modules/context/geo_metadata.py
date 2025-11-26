"""
M12: Geo Metadata Extraction Module

Extracts privacy-preserving spatial metadata from WAL envelope:
- Reads pre-masked location_geohash (Gate Stage 3 already applied band masking)
- Copies location_name and location_type
- Tracks geo_precision_external and geo_masking_reason

NO re-masking, NO enrichment (no reverse geocoding, no place lookup).
Performance: <2ms P95 (pure field copy/parse, no external APIs).

Contract: k0/contracts/modules/context.geo_metadata.v1.yaml
ADR: k007.5 (Geo Metadata Lookup - Privacy-Preserving Location)
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ===========================
# Data Structures
# ===========================


@dataclass(frozen=True)
class GeoMetadata:
    """
    Geo metadata extracted from envelope.

    Fields:
    - geohash_6: 6-character geohash (truncated from envelope location_geohash)
    - location_name: Human-readable place name (e.g., "Olive Garden, Market St")
    - location_type: Place category (e.g., "restaurant", "home", "park")
    - geo_precision_external: Precision level (GREEN=full, AMBER=geohash-6, RED=geohash-4)
    - geo_masking_reason: Why masking was applied (band_policy/user_preference/none)
    - geo_metadata_extracted_at_utc: ISO 8601 timestamp
    """

    geohash_6: Optional[str]
    location_name: Optional[str]
    location_type: Optional[str]
    geo_precision_external: str
    geo_masking_reason: str
    geo_metadata_extracted_at_utc: str


# ===========================
# Band → Geo Precision Mapping
# ===========================

BAND_PRECISION_MAP = {
    "GREEN": "full",  # Full precision (geohash-9, ~5m radius)
    "AMBER": "geohash-6",  # Neighborhood level (~1.2km radius)
    "RED": "geohash-4",  # City level (~39km radius)
}

# ===========================
# Metrics
# ===========================

_metrics = {
    "total_extractions": 0,
    "geohash_present": 0,
    "geohash_missing": 0,
    "location_name_present": 0,
    "location_name_missing": 0,
    "location_type_present": 0,
    "location_type_missing": 0,
    "precision_green": 0,
    "precision_amber": 0,
    "precision_red": 0,
    "precision_unknown": 0,
    "masking_band_policy": 0,
    "masking_user_preference": 0,
    "masking_none": 0,
    "invalid_geohash_format": 0,
}

# ===========================
# Geohash Validation
# ===========================


def is_valid_geohash(geohash: Optional[str]) -> bool:
    """
    Validate geohash format (base32 characters: 0-9, b-z excluding a,i,l,o).

    Args:
        geohash: Geohash string to validate

    Returns:
        True if valid geohash format, False otherwise
    """
    if not geohash:
        return False

    # Geohash uses base32: 0-9, b-h, j-k, m-n, p-z (32 chars, excluding a,i,l,o)
    geohash_pattern = re.compile(r"^[0-9b-hj-km-np-z]+$", re.IGNORECASE)
    return bool(geohash_pattern.match(geohash))


# ===========================
# Geo Precision Extraction
# ===========================


def get_geo_precision_from_band(band: Optional[str]) -> str:
    """
    Map privacy band to geo precision level.

    Args:
        band: Privacy band (GREEN/AMBER/RED)

    Returns:
        Geo precision string (full/geohash-6/geohash-4/unknown)
    """
    if not band:
        _metrics["precision_unknown"] += 1
        return "unknown"

    precision = BAND_PRECISION_MAP.get(band.upper(), "unknown")

    if band.upper() == "GREEN":
        _metrics["precision_green"] += 1
    elif band.upper() == "AMBER":
        _metrics["precision_amber"] += 1
    elif band.upper() == "RED":
        _metrics["precision_red"] += 1
    else:
        _metrics["precision_unknown"] += 1

    return precision


# ===========================
# Geo Masking Reason Extraction
# ===========================


def get_geo_masking_reason(obligations: Optional[list]) -> str:
    """
    Extract geo masking reason from policy obligations.

    Args:
        obligations: List of policy obligations (e.g., ["mask.location.precision"])

    Returns:
        Masking reason (band_policy/user_preference/none)
    """
    if not obligations:
        _metrics["masking_none"] += 1
        return "none"

    # Check for location masking obligations
    for obligation in obligations:
        if "mask.location" in obligation:
            _metrics["masking_band_policy"] += 1
            return "band_policy"
        if "user.privacy.location" in obligation:
            _metrics["masking_user_preference"] += 1
            return "user_preference"

    _metrics["masking_none"] += 1
    return "none"


# ===========================
# Core Extraction Logic
# ===========================


def extract_geo_metadata(envelope: Dict[str, Any]) -> GeoMetadata:
    """
    Extract geo metadata from envelope (pre-masked).

    NO re-masking, NO enrichment.
    Performance: <2ms P95 (pure field copy/parse).

    Args:
        envelope: WAL envelope with location data

    Returns:
        GeoMetadata with extracted fields
    """
    _metrics["total_extractions"] += 1

    body = envelope.get("body", {})
    policy_stamp = envelope.get("policy_stamp", {})

    # Extract pre-masked geohash (truncate to 6 chars for storage)
    location_geohash = body.get("location_geohash")

    if location_geohash:
        if is_valid_geohash(location_geohash):
            geohash_6 = location_geohash[:6] if len(location_geohash) >= 6 else location_geohash
            _metrics["geohash_present"] += 1
        else:
            geohash_6 = None
            _metrics["invalid_geohash_format"] += 1
    else:
        geohash_6 = None
        _metrics["geohash_missing"] += 1

    # Extract location name (user-provided or None)
    location_name = body.get("location_name")
    if location_name:
        _metrics["location_name_present"] += 1
    else:
        _metrics["location_name_missing"] += 1

    # Extract location type (default to "unknown" if missing)
    location_type = body.get("location_type")
    if location_type:
        _metrics["location_type_present"] += 1
    else:
        _metrics["location_type_missing"] += 1

    # Extract geo precision from band
    band = policy_stamp.get("band")
    geo_precision_external = get_geo_precision_from_band(band)

    # Extract geo masking reason from obligations
    obligations = policy_stamp.get("obligations")
    geo_masking_reason = get_geo_masking_reason(obligations)

    # Generate timestamp
    geo_metadata_extracted_at_utc = datetime.now(timezone.utc).isoformat()

    return GeoMetadata(
        geohash_6=geohash_6,
        location_name=location_name,
        location_type=location_type,
        geo_precision_external=geo_precision_external,
        geo_masking_reason=geo_masking_reason,
        geo_metadata_extracted_at_utc=geo_metadata_extracted_at_utc,
    )


# ===========================
# Module Entry Point
# ===========================


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    M12 entry point (Phase 2 signature): Extract geo metadata from envelope.

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Stage-specific configuration
            - default_location_type (str): Fallback location type (default: "unknown")
            - default_geo_precision (str): Fallback precision (default: "full")
            - validate_geohash_format (bool): Enable validation (default: True)

    Returns:
        Enriched envelope with geo metadata fields

    Performance: <2ms P95
    Contract: k0/contracts/modules/context.geo_metadata.v1.yaml
    """
    # Parse envelope from message
    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )

    # Extract config parameters (with defaults)
    default_location_type = config.get("default_location_type", "unknown")
    default_geo_precision = config.get("default_geo_precision", "full")
    validate_geohash_format = config.get("validate_geohash_format", True)

    # Log module start
    context.logger.debug(
        "M12 geo_metadata starting",
        extra={
            "module_id": "context.geo_metadata",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
        },
    )

    # Extract geo metadata
    geo_metadata = extract_geo_metadata(envelope)

    # Convert to dict for enriched envelope
    geo_fields = {
        "geohash_6": geo_metadata.geohash_6,
        "location_name": geo_metadata.location_name,
        "location_type": geo_metadata.location_type,
        "geo_precision_external": geo_metadata.geo_precision_external,
        "geo_masking_reason": geo_metadata.geo_masking_reason,
        "geo_metadata_extracted_at_utc": geo_metadata.geo_metadata_extracted_at_utc,
    }

    # Log module completion
    context.logger.debug(
        "M12 geo_metadata completed",
        extra={
            "module_id": "context.geo_metadata",
            "trace_id": message.trace_id,
            "geohash_present": geo_metadata.geohash_6 is not None,
            "geo_precision": geo_metadata.geo_precision_external,
        },
    )

    # Return enriched envelope
    return {**envelope, **geo_fields}


# ===========================
# Observability
# ===========================


def get_metrics() -> Dict[str, int]:
    """
    Get current metrics for observability.

    Returns:
        Dict with 14 metrics:
        - total_extractions
        - geohash_present/missing
        - location_name_present/missing
        - location_type_present/missing
        - precision_green/amber/red/unknown
        - masking_band_policy/user_preference/none
        - invalid_geohash_format
    """
    return _metrics.copy()


def reset_metrics() -> None:
    """Reset all metrics to zero (for testing)."""
    for key in _metrics:
        _metrics[key] = 0
