"""
Temporal Resolution Engine - Temporal Anchor Computation
=========================================================

Architecture Reference:
  k1_cognitive_architecture_skeleton.mmd -> ACKING_CORE -> TIME_RESOLUTION subgraph
    - TIMEZONE_CONTEXT: User TZ from device/profile
    - TEMPORAL_ANCHOR:  now, today, this_week
    - TIME_PARSER:      NER TIME/DATE/DURATION -> parsed  (handled by UltraBERT NER head)
    - TIME_RESOLVER:    Relative -> Absolute              (future: '9' -> '09:00' or '21:00')

Production Port Path:
  - Temporal anchor fields become sub-fields of Multimodal section (Section 5 of
    canonical 8 HOT sections) per skeleton.mmd line 834 NOTE.
  - This engine moves to k1/concierge/engines/temporal_resolution.py
  - Computation is called from Phase 1 pipeline (alongside UltraBERT).

POC Wiring:
  - compute_temporal_anchor(tz_name) -> TemporalAnchor dataclass
  - Called from _write_phase1_to_ss() to write anchor into Control section
  - Persona section holds family timezone ("America/Los_Angeles" etc.)
  - Prompt builder renders anchor from Control.get_metadata()
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

if sys.version_info >= (3, 9):
    from zoneinfo import ZoneInfo
else:
    from backports.zoneinfo import ZoneInfo


# Time-of-day buckets (hour boundaries, local time)
_TOD_BUCKETS = [
    (5, "early_morning"),
    (9, "morning"),
    (12, "afternoon"),
    (17, "evening"),
    (21, "night"),
    (24, "late_night"),
]

_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _bucket_for_hour(hour: int) -> str:
    for upper, label in _TOD_BUCKETS:
        if hour < upper:
            return label
    return "late_night"


@dataclass(frozen=True)
class TemporalAnchor:
    """Immutable snapshot of current temporal context.

    Mirrors the TEMPORAL_ANCHOR node in the architecture skeleton.
    Produced by compute_temporal_anchor(), consumed by Control section
    and rendered by prompt builder.

    Port path: becomes Multimodal.temporal_anchor sub-field.
    """

    local_time_iso: str
    day_of_week: str
    time_of_day: str
    is_weekend: bool
    timezone: str
    hour_24: int

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_full(self) -> str:
        """Multi-line rendering for full prompt mode."""
        return (
            f"Local time: {self.local_time_iso}\n"
            f"Day: {self.day_of_week}\n"
            f"Time of day: {self.time_of_day}\n"
            f"Weekend: {self.is_weekend}\n"
            f"Timezone: {self.timezone}"
        )

    def to_prompt_slim(self) -> str:
        """One-liner for slim prompt mode."""
        return f"{self.day_of_week} {self.time_of_day} ({self.timezone})"


def compute_temporal_anchor(tz_name: str = "UTC") -> TemporalAnchor:
    """Compute temporal anchor from wall clock + family timezone.

    Called during Phase 1 (or lazily before prompt build).
    Mirrors the Temporal Resolution Engine in the architecture.

    Args:
        tz_name: IANA timezone string from Persona preferences
                 (e.g. "America/Los_Angeles"). Falls back to UTC.

    Returns:
        Frozen TemporalAnchor dataclass.
    """
    utc_now = datetime.now(timezone.utc)
    try:
        local_now = utc_now.astimezone(ZoneInfo(tz_name))
    except (KeyError, Exception):
        local_now = utc_now
        tz_name = "UTC"

    return TemporalAnchor(
        local_time_iso=local_now.strftime("%Y-%m-%dT%H:%M:%S%z"),
        day_of_week=_DAY_NAMES[local_now.weekday()],
        time_of_day=_bucket_for_hour(local_now.hour),
        is_weekend=local_now.weekday() >= 5,
        timezone=tz_name,
        hour_24=local_now.hour,
    )
