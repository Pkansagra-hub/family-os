"""Freshness checks for grounding envelopes."""

from __future__ import annotations

from datetime import UTC, datetime

from k1.grounding.config import GroundingConfig
from k1.grounding.types import GroundingEnvelope


def envelope_age_ms(envelope: GroundingEnvelope, *, now_utc: str | None = None) -> int:
    """Return envelope age in milliseconds, clamped at zero."""
    created = _parse_utc(envelope.created_at_utc)
    now = _parse_utc(now_utc) if now_utc else datetime.now(UTC)
    return max(0, int((now - created).total_seconds() * 1000))


def is_stale(
    envelope: GroundingEnvelope, *, config: GroundingConfig, now_utc: str | None = None
) -> bool:
    """Return True when the envelope is older than configured TTL."""
    return envelope_age_ms(envelope, now_utc=now_utc) > int(config.envelope_ttl_ms)


def _parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


__all__ = ["envelope_age_ms", "is_stale"]
