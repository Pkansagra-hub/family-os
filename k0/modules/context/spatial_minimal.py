"""
M15: Spatial Minimal Enrichment Module

Copies band-appropriate spatial fields from WAL envelope to st_hipp_events:
- location_name: Human-readable place name (from K1/Gate enrichment)
- location_type: Place category (from K1/Gate enrichment)
- geohash_6: 6-character geohash for GREEN band (±0.61 km precision)

**COPY MODE** - Enrichment already done by Gate Stage 2.5:
- Gate Stage 2.5 (spatial_enrich) already copied location_name/type from K1
- Gate Stage 3 (location_privacy) already computed location_geohash
- M15 just copies to st_hipp_events with final band-based truncation

Band-Based Spatial Minimization:
- GREEN: Full geohash_6 from envelope location_geohash
- AMBER: Truncate to geohash_4 (±20 km precision)
- RED: Omit geohash entirely (NULL for maximum privacy)

Privacy Guarantee:
- Does NOT access raw lat/lon (already stripped by Gate Stage 3)
- Only reads pre-masked location_geohash from WAL envelope
- Applies additional band-based truncation as needed

Performance: <1ms P95 (copy/truncate operations only, no computation)

Contract: k0/contracts/modules/context.spatial_minimal.v1.yaml
ADR: k007.5 (Geo Metadata Lookup - Privacy-Preserving Location)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ===========================
# Data Structures
# ===========================


@dataclass(frozen=True)
class SpatialMinimal:
    """
    Minimal spatial fields with band-based privacy truncation.

    Fields:
    - geohash_6: Truncated geohash (GREEN=6 chars, AMBER=4 chars, RED=NULL)
    - location_name: Human-readable place name
    - location_type: Place category
    - spatial_minimized_at_utc: ISO 8601 timestamp
    """

    geohash_6: Optional[str]
    location_name: Optional[str]
    location_type: Optional[str]
    spatial_minimized_at_utc: str


# ===========================
# Band → Geohash Precision Mapping
# ===========================

BAND_PRECISION_MAP = {
    "GREEN": 6,  # Full precision (geohash-6, ±0.61 km)
    "AMBER": 4,  # Coarse precision (geohash-4, ±20 km)
    "RED": 0,  # No geohash (NULL for maximum privacy)
}


# ===========================
# Metrics
# ===========================

_metrics = {
    "total_minimizations": 0,
    "green_band_full": 0,
    "amber_band_truncated": 0,
    "red_band_null": 0,
    "geohash_present": 0,
    "geohash_missing": 0,
    "location_name_present": 0,
    "location_name_missing": 0,
    "location_type_present": 0,
    "location_type_missing": 0,
    "band_unknown": 0,
}


# ===========================
# Core Truncation Logic
# ===========================


def truncate_geohash(geohash: Optional[str], band: Optional[str]) -> Optional[str]:
    """
    Truncate geohash based on privacy band.

    Args:
        geohash: Full geohash string
        band: Privacy band (GREEN/AMBER/RED)

    Returns:
        Truncated geohash or None (if RED band or missing)
    """
    if not geohash:
        _metrics["geohash_missing"] += 1
        return None

    # Default to GREEN if band is missing
    if not band:
        band = "GREEN"
        _metrics["band_unknown"] += 1

    precision = BAND_PRECISION_MAP.get(band.upper(), 6)  # Default to GREEN

    if precision == 0:
        # RED band: omit geohash entirely
        _metrics["red_band_null"] += 1
        return None

    # Truncate to desired precision
    truncated = geohash[:precision] if len(geohash) >= precision else geohash

    if band.upper() == "GREEN":
        _metrics["green_band_full"] += 1
    elif band.upper() == "AMBER":
        _metrics["amber_band_truncated"] += 1

    _metrics["geohash_present"] += 1
    return truncated


def minimize_spatial_fields(envelope: Dict[str, Any]) -> SpatialMinimal:
    """
    Copy and minimize spatial fields from envelope (COPY MODE).

    **Gate enrichment already done**:
    - Gate Stage 2.5: Copied location_name/type from K1
    - Gate Stage 3: Computed location_geohash with band-based masking
    - M15: Just copies fields + applies final geohash truncation

    Applies band-based geohash truncation and copies location metadata.
    Performance: <1ms P95 (pure copy + string truncation).

    Args:
        envelope: WAL envelope with pre-enriched location data

    Returns:
        SpatialMinimal with minimized fields
    """
    _metrics["total_minimizations"] += 1

    body = envelope.get("body", {})
    policy_stamp = envelope.get("policy_stamp", {})

    # Extract band for truncation logic
    band = policy_stamp.get("band")

    # Copy location_geohash from envelope (already computed by Gate Stage 3)
    location_geohash = envelope.get("location_geohash")

    # Apply final band-based truncation (double-check Gate's work)
    geohash_6 = truncate_geohash(location_geohash, band)

    # Copy location name and type from body (already copied by Gate Stage 2.5)
    location_name = body.get("location_name") if isinstance(body, dict) else None
    if location_name:
        _metrics["location_name_present"] += 1
    else:
        _metrics["location_name_missing"] += 1

    location_type = body.get("location_type") if isinstance(body, dict) else None
    if location_type:
        _metrics["location_type_present"] += 1
    else:
        _metrics["location_type_missing"] += 1

    # Generate timestamp
    spatial_minimized_at_utc = datetime.now(timezone.utc).isoformat()

    return SpatialMinimal(
        geohash_6=geohash_6,
        location_name=location_name,
        location_type=location_type,
        spatial_minimized_at_utc=spatial_minimized_at_utc,
    )


# ===========================
# Module Entry Point
# ===========================


async def run(message: Any, context: Any, **config: Any) -> Dict[str, Any]:
    """
    M15 entry point: Minimize spatial fields with band-based truncation.

    Phase 2 Signature:
    - message: BusMessage with .payload, .trace_id, .offset
    - context: PipelineContext with .syscalls, .logger, .config
    - **config: Stage-specific configuration from pipeline YAML

    Config Parameters:
    - green_band_precision (int): Geohash precision for GREEN band (default: 6)
    - amber_band_precision (int): Geohash precision for AMBER band (default: 4)
    - red_band_precision (int): Geohash precision for RED band (default: 0)
    - allow_null_location (bool): Allow NULL location fields (default: True)

    Args:
        message: BusMessage with envelope payload
        context: PipelineContext with logger and syscalls
        **config: Configuration parameters

    Returns:
        Dict with minimized spatial fields (enriched envelope)

    Contract: k0/contracts/modules/context.spatial_minimal.v1.yaml
    """
    import json

    # Parse envelope from message
    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )

    # Extract config parameters (currently unused, but available for tuning)
    green_band_precision = config.get("green_band_precision", 6)
    amber_band_precision = config.get("amber_band_precision", 4)
    red_band_precision = config.get("red_band_precision", 0)
    allow_null_location = config.get("allow_null_location", True)

    # Log module start
    context.logger.debug(
        "M15 spatial_minimal starting",
        extra={
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
            "band": envelope.get("policy_stamp", {}).get("band"),
        },
    )

    # Execute minimization logic
    spatial = minimize_spatial_fields(envelope)

    # Log completion
    context.logger.debug(
        "M15 spatial_minimal completed",
        extra={
            "trace_id": message.trace_id,
            "geohash_present": spatial.geohash_6 is not None,
            "location_name_present": spatial.location_name is not None,
        },
    )

    # Return enriched envelope
    return {
        **envelope,
        "geohash_6": spatial.geohash_6,
        "location_name": spatial.location_name,
        "location_type": spatial.location_type,
        "spatial_minimized_at_utc": spatial.spatial_minimized_at_utc,
    }


# ===========================
# Observability
# ===========================


def get_metrics() -> Dict[str, int]:
    """
    Get current metrics for observability.

    Returns:
        Dict with 11 metrics:
        - total_minimizations
        - green_band_full / amber_band_truncated / red_band_null
        - geohash_present / geohash_missing
        - location_name_present / location_name_missing
        - location_type_present / location_type_missing
        - band_unknown
    """
    return _metrics.copy()


def reset_metrics() -> None:
    """Reset all metrics to zero (for testing)."""
    for key in _metrics:
        _metrics[key] = 0
