"""Freshness evaluation for temporal anchors."""

from __future__ import annotations

from k1.temporal.config import TemporalConfig
from k1.temporal.service.daylight_boundary import parse_utc
from k1.temporal.types import FreshnessState, TemporalAnchor


def evaluate_freshness(
    anchor: TemporalAnchor | None, now_utc: str, *, config: TemporalConfig | None = None
) -> FreshnessState:
    """Return live/stale/degraded/unavailable for an anchor."""

    if anchor is None:
        return "unavailable"
    cfg = config or TemporalConfig()
    captured = parse_utc(anchor.captured_at_utc)
    now = parse_utc(now_utc)
    age_ms = int((now - captured).total_seconds() * 1000)
    if age_ms <= cfg.stale_after_ms:
        return "live"
    if age_ms <= cfg.degraded_after_ms:
        return "stale"
    return "degraded"


__all__ = ["evaluate_freshness"]
