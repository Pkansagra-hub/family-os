"""Configuration for the k1.temporal kernel module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalConfig:
    """Static policy for temporal anchor construction and freshness."""

    anchor_ttl_ms: int = 60_000
    stale_after_ms: int = 120_000
    degraded_after_ms: int = 180_000
    fallback_timezone_sources: tuple[str, ...] = ("device", "spatial", "persona", "utc")
    default_timezone: str = "UTC"
    default_locale: str = "en-US"
    week_start_day: str = "monday"
    default_consumer: str = "front"
