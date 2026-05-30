"""Configuration for the k1.spatial kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from k1.spatial.constants import DEFAULT_CONSUMER_PRECISION


@dataclass(frozen=True)
class SpatialConfig:
    """Static policy for spatial freshness, precision, and privacy."""

    context_ttl_ms: int = 60_000
    stale_after_ms: int = 120_000
    default_precision: str = "semantic"
    raw_location_allowed_by_default: bool = False
    unknown_place_label: str = "unknown"
    max_location_age_ms: int = 120_000
    max_acceptable_accuracy_m: float = 1_000.0
    geofence_match_radius_m: float = 75.0
    approximate_decimal_places: int = 2
    consumer_precision: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_CONSUMER_PRECISION)
    )
