"""Pure payload types for the k1.temporal kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

FreshnessState = Literal["live", "stale", "degraded", "unavailable"]
TimezoneSource = Literal["device", "spatial", "persona", "utc"]
TimeOfDay = Literal[
    "early_morning",
    "morning",
    "midday",
    "afternoon",
    "evening",
    "night",
    "late_night",
]


@dataclass(frozen=True)
class TemporalAnchor:
    """Authoritative local-time anchor for a session turn."""

    anchor_id: str
    captured_at_utc: str
    now_utc: str
    now_local: str
    timezone: str
    timezone_source: str
    local_date: str
    local_time: str
    day_of_week: str
    hour_24: int
    time_of_day: str
    is_weekend: bool
    locale: str | None
    week_start_day: str
    freshness_ms: int
    source: str
    confidence: float


@dataclass(frozen=True)
class TemporalWindow:
    """A safe, timezone-aware temporal range for tools and planners."""

    label: str
    start_local: str
    end_local: str
    start_utc: str
    end_utc: str
    timezone: str
    granularity: Literal["instant", "day", "week", "month", "custom"]
    inclusive_start: bool = True
    exclusive_end: bool = True


@dataclass(frozen=True)
class ResolvedTemporalExpression:
    """Structured resolution for a user-facing temporal phrase."""

    raw_text: str
    normalized_label: str
    resolution_kind: Literal["instant", "window", "recurrence", "ambiguous"]
    window: TemporalWindow | None
    instant_local: str | None
    recurrence_rule: str | None
    confidence: float
    needs_clarification: bool
    clarification_reason: str | None


@dataclass(frozen=True)
class CandidateSpan:
    """Structured temporal candidate supplied by Front or task params."""

    text: str
    locale: str = "en-US"
    span_start: int | None = None
    span_end: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutineRef:
    """Opaque routine reference supplied by a routine provider."""

    routine_id: str
    label: str
    routine_kind: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TemporalProjection:
    """Policy-shaped temporal payload for one downstream consumer."""

    anchor: TemporalAnchor
    windows: Mapping[str, TemporalWindow]
    resolved_expressions: tuple[ResolvedTemporalExpression, ...]
    consumer: str
    freshness: FreshnessState
    precision: str


@dataclass(frozen=True)
class TemporalTurnSnapshot:
    """Temporal state written after a turn refresh."""

    session_id: str
    turn_id: str | None
    anchor: TemporalAnchor
    windows: Mapping[str, TemporalWindow]
    resolved_expressions: tuple[ResolvedTemporalExpression, ...]
    refreshed_at_utc: str
    source: str


__all__ = [
    "CandidateSpan",
    "FreshnessState",
    "ResolvedTemporalExpression",
    "RoutineRef",
    "TemporalAnchor",
    "TemporalProjection",
    "TemporalTurnSnapshot",
    "TemporalWindow",
    "TimeOfDay",
    "TimezoneSource",
]
