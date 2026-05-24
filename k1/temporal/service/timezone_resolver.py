"""Timezone resolution with deterministic fallback order."""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from k1.temporal.config import TemporalConfig
from k1.temporal.ports import ITimezonePort


@dataclass(frozen=True)
class TimezoneResolution:
    """Resolved timezone plus provenance."""

    timezone: str
    source: str
    tried_sources: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...] = ()


def is_valid_timezone(candidate: str | None) -> bool:
    if not candidate:
        return False
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def resolve_timezone(
    *,
    device_timezone: str | None = None,
    spatial_timezone: str | None = None,
    persona_timezone: str | None = None,
    config: TemporalConfig | None = None,
) -> TimezoneResolution:
    """Resolve timezone in the canonical device -> spatial -> persona -> UTC order."""

    cfg = config or TemporalConfig()
    values = {
        "device": device_timezone,
        "spatial": spatial_timezone,
        "persona": persona_timezone,
        "utc": cfg.default_timezone,
    }
    rejected: list[tuple[str, str]] = []
    tried: list[str] = []
    for source in cfg.fallback_timezone_sources:
        tried.append(source)
        candidate = values.get(source)
        if is_valid_timezone(candidate):
            return TimezoneResolution(str(candidate), source, tuple(tried), tuple(rejected))
        if candidate:
            rejected.append((source, str(candidate)))
    default_timezone = cfg.default_timezone if is_valid_timezone(cfg.default_timezone) else "UTC"
    return TimezoneResolution(default_timezone, "utc", tuple(tried), tuple(rejected))


async def resolve_timezone_from_ports(
    *,
    principal_id: str,
    device_timezone: str | None,
    spatial_port: ITimezonePort | None,
    persona_port: ITimezonePort | None,
    config: TemporalConfig | None = None,
) -> TimezoneResolution:
    """Resolve timezone using optional candidate ports."""

    spatial = await spatial_port.candidate_for_principal(principal_id) if spatial_port else None
    persona = await persona_port.candidate_for_principal(principal_id) if persona_port else None
    return resolve_timezone(
        device_timezone=device_timezone,
        spatial_timezone=spatial,
        persona_timezone=persona,
        config=config,
    )


__all__ = [
    "TimezoneResolution",
    "is_valid_timezone",
    "resolve_timezone",
    "resolve_timezone_from_ports",
]
