"""Clock skew evaluation for device observations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClockSkewStatus:
    """Clock skew status for anchor provenance."""

    skew_ms: int | None
    is_suspicious: bool
    confidence_penalty: float


def check_clock_skew(
    clock_skew_ms: int | None, *, suspicious_after_ms: int = 300_000
) -> ClockSkewStatus:
    """Return whether device clock skew should reduce confidence."""

    if clock_skew_ms is None:
        return ClockSkewStatus(None, False, 0.0)
    suspicious = abs(clock_skew_ms) >= suspicious_after_ms
    return ClockSkewStatus(clock_skew_ms, suspicious, 0.15 if suspicious else 0.0)


__all__ = ["ClockSkewStatus", "check_clock_skew"]
