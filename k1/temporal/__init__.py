"""k1.temporal -- kernel-owned time, windows, and expression grounding.

M0 exposes only inert payload types, configuration, constants, and errors.
Runtime services and adapters land in later milestones.
"""

from __future__ import annotations

from k1.temporal.config import TemporalConfig
from k1.temporal.errors import (
    AmbiguousExpressionError,
    InvalidTimezoneError,
    StaleAnchorError,
    TemporalError,
    UnavailableClockError,
    UnsupportedLocaleError,
)
from k1.temporal.events import (
    TEMPORAL_ANCHOR_CREATED,
    TEMPORAL_ANCHOR_REFRESHED,
    TEMPORAL_ANCHOR_STALE,
    TEMPORAL_EXPRESSION_AMBIGUOUS,
    TEMPORAL_EXPRESSION_RESOLVED,
    AnchorCreatedPayload,
    AnchorRefreshedPayload,
    AnchorStalePayload,
    ExpressionAmbiguousPayload,
    ExpressionResolvedPayload,
)
from k1.temporal.types import (
    CandidateSpan,
    FreshnessState,
    ResolvedTemporalExpression,
    RoutineRef,
    TemporalAnchor,
    TemporalProjection,
    TemporalTurnSnapshot,
    TemporalWindow,
    TimeOfDay,
    TimezoneSource,
)

__all__ = [
    "AmbiguousExpressionError",
    "AnchorCreatedPayload",
    "AnchorRefreshedPayload",
    "AnchorStalePayload",
    "CandidateSpan",
    "ExpressionAmbiguousPayload",
    "ExpressionResolvedPayload",
    "FreshnessState",
    "InvalidTimezoneError",
    "ResolvedTemporalExpression",
    "RoutineRef",
    "StaleAnchorError",
    "TEMPORAL_ANCHOR_CREATED",
    "TEMPORAL_ANCHOR_REFRESHED",
    "TEMPORAL_ANCHOR_STALE",
    "TEMPORAL_EXPRESSION_AMBIGUOUS",
    "TEMPORAL_EXPRESSION_RESOLVED",
    "TemporalAnchor",
    "TemporalConfig",
    "TemporalError",
    "TemporalProjection",
    "TemporalTurnSnapshot",
    "TemporalWindow",
    "TimeOfDay",
    "TimezoneSource",
    "UnavailableClockError",
    "UnsupportedLocaleError",
]
