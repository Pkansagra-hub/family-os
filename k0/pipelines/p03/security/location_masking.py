"""Simplified location masking for external API calls.

Masks location precision before sending to external LLMs/APIs
based on privacy band. Uses K0 location_privacy.py.

Only needed when:
- Sending data to external API (LLM, cloud service)
- User has set privacy band to AMBER or RED

NOT needed for:
- On-device processing (full precision always available)
- Local storage (we keep full precision, mask on output)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from k0.policy.location_privacy import get_precision_meters_for_band, mask_location_for_band


@dataclass(frozen=True)
class MaskedLocation:
    """Location masked for external sharing."""

    geohash: str
    precision_meters: int
    band: str


def mask_for_external_api(
    lat: float | None,
    lon: float | None,
    band: Literal["GREEN", "AMBER", "RED"],
) -> MaskedLocation | None:
    """Mask location before sending to external API.

    Call this when preparing data for:
    - LLM API calls
    - External cloud services
    - Any network transmission

    Args:
        lat: Latitude (or None)
        lon: Longitude (or None)
        band: Privacy band of the data

    Returns:
        MaskedLocation with appropriate precision, or None if no location
    """
    if lat is None or lon is None:
        return None

    geohash, precision_meters = mask_location_for_band(lat, lon, band)

    if geohash is None:
        return None

    return MaskedLocation(
        geohash=geohash,
        precision_meters=precision_meters or 0,
        band=band,
    )


def get_safe_location_description(
    lat: float | None,
    lon: float | None,
    band: Literal["GREEN", "AMBER", "RED"],
) -> str:
    """Get human-readable location description safe for sharing.

    For including in LLM prompts without revealing exact location.

    Args:
        lat: Latitude
        lon: Longitude
        band: Privacy band

    Returns:
        Safe description like "near San Francisco" or "in California"
    """
    if lat is None or lon is None:
        return "unknown location"

    precision = get_precision_meters_for_band(band)

    if precision <= 1:
        # GREEN: can be specific
        return f"at coordinates ({lat:.4f}, {lon:.4f})"
    elif precision <= 5000:
        # AMBER: city level
        return "in the local area"
    else:
        # RED: country level
        return "in the general region"


def should_include_location(
    band: Literal["GREEN", "AMBER", "RED"],
) -> bool:
    """Check if location should be included in external API calls.

    Always returns True - we mask to appropriate precision,
    not omit entirely. Even RED band includes country-level.

    Args:
        band: Privacy band

    Returns:
        True (always include at appropriate precision)
    """
    return True
