"""Location privacy handling for V1.3 (Geohash masking for AMBER/RED bands).

Implements geohash-based location masking:
  - GREEN band: No masking, full precision (exact lat/lon)
  - AMBER band: 5km precision (geohash-6, ~1250 km²)
  - RED band: 25km precision (geohash-4, ~39,000 km²)

Geohashing reduces location precision while maintaining spatial queries.
"""

from __future__ import annotations

from typing import Any, Literal


def lat_lon_to_geohash(
    lat: float,
    lon: float,
    precision: int = 12,
) -> str:
    """Convert latitude/longitude to geohash.

    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)
        precision: Geohash precision (1-12 characters)

    Returns:
        Geohash string

    Precision levels:
        1: ~2,500 km
        2: ~600 km
        3: ~150 km
        4: ~39 km (RED band precision)
        5: ~10 km
        6: ~2.4 km (AMBER band precision)
        7: ~0.61 km
        8: ~0.15 km
        9: ~0.037 km
        10: ~0.0093 km
        11: ~0.0023 km
        12: ~0.00058 km (full precision)
    """
    if not (-90 <= lat <= 90):
        raise ValueError(f"Invalid latitude: {lat}")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Invalid longitude: {lon}")
    if not (1 <= precision <= 12):
        raise ValueError(f"Precision must be 1-12, got {precision}")

    lat_min, lat_max = -90.0, 90.0
    lon_min, lon_max = -180.0, 180.0
    geohash = ""
    is_even = True

    ch = 0
    bit = 0

    while len(geohash) < precision:
        if is_even:
            mid = (lon_min + lon_max) / 2
            if lon >= mid:
                ch |= 1 << (4 - bit)
                lon_min = mid
            else:
                lon_max = mid
        else:
            mid = (lat_min + lat_max) / 2
            if lat >= mid:
                ch |= 1 << (4 - bit)
                lat_min = mid
            else:
                lat_max = mid

        is_even = not is_even

        if bit < 4:
            bit += 1
        else:
            geohash += __BASE32[ch]
            bit = 0
            ch = 0

    return geohash


def get_geohash_precision_for_band(
    band: Literal["GREEN", "AMBER", "RED"],
) -> int:
    """Get geohash precision for privacy band.

    Args:
        band: Privacy band (GREEN/AMBER/RED)

    Returns:
        Geohash precision (1-12)
        - GREEN: 12 (full precision, ~0.6m)
        - AMBER: 6 (5km precision)
        - RED: 4 (39km precision)
    """
    if band == "GREEN":
        return 12  # Full precision
    elif band == "AMBER":
        return 6  # ~2.4km (conservative: 5km precision)
    elif band == "RED":
        return 4  # ~39km precision
    else:
        raise ValueError(f"Unknown band: {band}")


def get_precision_meters_for_band(
    band: Literal["GREEN", "AMBER", "RED"],
) -> int:
    """Get precision in meters for privacy band.

    Args:
        band: Privacy band (GREEN/AMBER/RED)

    Returns:
        Precision in meters
        - GREEN: 1 (exact)
        - AMBER: 5000 (5km)
        - RED: 25000 (25km)
    """
    if band == "GREEN":
        return 1
    elif band == "AMBER":
        return 5000
    elif band == "RED":
        return 25000
    else:
        raise ValueError(f"Unknown band: {band}")


def mask_location_for_band(
    lat: float | None,
    lon: float | None,
    band: Literal["GREEN", "AMBER", "RED"],
) -> tuple[str | None, int | None]:
    """Mask location coordinates to appropriate precision for band.

    Args:
        lat: Latitude (or None if already masked)
        lon: Longitude (or None if already masked)
        band: Privacy band

    Returns:
        Tuple of (geohash, precision_meters)
        - GREEN: (12-char geohash, 1m) - full precision
        - AMBER: (6-char geohash, 5000m) - ~5km precision
        - RED: (4-char geohash, 25000m) - ~25km precision
        - If lat/lon are None: (None, None)
    """
    if lat is None or lon is None:
        return None, None

    precision = get_geohash_precision_for_band(band)
    geohash = lat_lon_to_geohash(lat, lon, precision)
    precision_m = get_precision_meters_for_band(band)

    return geohash, precision_m


def apply_location_privacy(
    envelope: dict[str, Any],
    band: Literal["GREEN", "AMBER", "RED"],
) -> dict[str, Any]:
    """Apply location privacy masking to envelope.

    Updates envelope with:
    - location_geohash: Geohash for the band
    - location_precision_m: Precision in meters
    - Clears exact coordinates for AMBER/RED (if present in body)

    Args:
        envelope: Envelope to modify (mutated)
        band: Privacy band

    Returns:
        Modified envelope
    """
    # Extract location from body if present
    body = envelope.get("body")
    lat = None
    lon = None

    if isinstance(body, dict):
        lat = body.get("location_lat")
        lon = body.get("location_lon")

    # Apply masking
    geohash, precision_m = mask_location_for_band(lat, lon, band)

    if geohash is not None:
        envelope["location_geohash"] = geohash
        envelope["location_precision_m"] = precision_m

    # Clear exact coordinates for AMBER/RED (privacy protection)
    if band in ("AMBER", "RED"):
        if isinstance(body, dict):
            body.pop("location_lat", None)
            body.pop("location_lon", None)

    return envelope


# Base32 alphabet for geohashing (exclude A, I, L, O for clarity)
__BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


__all__ = [
    "apply_location_privacy",
    "get_geohash_precision_for_band",
    "get_precision_meters_for_band",
    "lat_lon_to_geohash",
    "mask_location_for_band",
]
