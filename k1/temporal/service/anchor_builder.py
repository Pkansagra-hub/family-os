"""Build authoritative temporal anchors from injected ports."""

from __future__ import annotations

from datetime import timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from k1.temporal.config import TemporalConfig
from k1.temporal.ports import IClockPort, ITemporalIdPort, ITimezonePort
from k1.temporal.service.clock_skew_checker import check_clock_skew
from k1.temporal.service.daylight_boundary import parse_utc
from k1.temporal.service.locale_resolver import resolve_locale
from k1.temporal.service.timezone_resolver import resolve_timezone_from_ports
from k1.temporal.types import TemporalAnchor

_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_TOD_BUCKETS = (
    (5, "late_night"),
    (9, "early_morning"),
    (12, "morning"),
    (14, "midday"),
    (17, "afternoon"),
    (21, "evening"),
    (24, "night"),
)


def time_of_day_for_hour(hour: int) -> str:
    for upper, label in _TOD_BUCKETS:
        if hour < upper:
            return label
    return "night"


async def build_anchor(
    *,
    session_id: str,
    clock: IClockPort,
    id_port: ITemporalIdPort,
    config: TemporalConfig | None = None,
    device_context: Mapping[str, Any] | None = None,
    spatial_timezone_port: ITimezonePort | None = None,
    persona_timezone_port: ITimezonePort | None = None,
    principal_id: str | None = None,
) -> TemporalAnchor:
    """Build a canonical temporal anchor from clock, timezone, and locale context."""

    cfg = config or TemporalConfig()
    now_utc = parse_utc(clock.now_utc())
    context = dict(device_context or {})
    resolved = await resolve_timezone_from_ports(
        principal_id=principal_id or session_id,
        device_timezone=context.get("timezone"),
        spatial_port=spatial_timezone_port,
        persona_port=persona_timezone_port,
        config=cfg,
    )
    local_now = now_utc.astimezone(ZoneInfo(resolved.timezone))
    skew = check_clock_skew(context.get("clock_skew_ms"))
    confidence = max(0.0, 1.0 - skew.confidence_penalty)
    locale = resolve_locale(context.get("locale"), config=cfg)
    return TemporalAnchor(
        anchor_id=id_port.new_anchor_id(),
        captured_at_utc=now_utc.astimezone(timezone.utc).isoformat(),
        now_utc=now_utc.astimezone(timezone.utc).isoformat(),
        now_local=local_now.isoformat(),
        timezone=resolved.timezone,
        timezone_source=resolved.source,
        local_date=local_now.date().isoformat(),
        local_time=local_now.time().replace(microsecond=0).isoformat(),
        day_of_week=_DAY_NAMES[local_now.weekday()],
        hour_24=local_now.hour,
        time_of_day=time_of_day_for_hour(local_now.hour),
        is_weekend=local_now.weekday() >= 5,
        locale=locale,
        week_start_day=cfg.week_start_day,
        freshness_ms=0,
        source="k1.temporal.anchor_builder",
        confidence=confidence,
    )


__all__ = ["build_anchor", "time_of_day_for_hour"]
