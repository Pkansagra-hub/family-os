"""Event topics and payloads emitted by the temporal kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

TEMPORAL_ANCHOR_CREATED = "k1.temporal.anchor.created.v1"
TEMPORAL_ANCHOR_REFRESHED = "k1.temporal.anchor.refreshed.v1"
TEMPORAL_EXPRESSION_RESOLVED = "k1.temporal.expression.resolved.v1"
TEMPORAL_EXPRESSION_AMBIGUOUS = "k1.temporal.expression.ambiguous.v1"
TEMPORAL_ANCHOR_STALE = "k1.temporal.anchor.stale.v1"


@dataclass(frozen=True)
class AnchorCreatedPayload:
    """Payload for a newly created temporal anchor."""

    anchor_id: str
    session_id: str
    anchor: Mapping[str, Any]
    created_at_utc: str
    provenance: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class AnchorRefreshedPayload:
    """Payload for a refreshed temporal anchor."""

    anchor_id: str
    previous_anchor_id: str | None
    session_id: str
    anchor: Mapping[str, Any]
    refreshed_at_utc: str
    delta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnchorStalePayload:
    """Payload emitted when an anchor is no longer fresh."""

    anchor_id: str
    session_id: str
    stale_since_utc: str
    freshness_state: str


@dataclass(frozen=True)
class ExpressionResolvedPayload:
    """Payload for a resolved temporal expression."""

    session_id: str
    raw_text: str
    normalized_label: str
    resolution_kind: str
    confidence: float
    resolved_at_utc: str
    window: Mapping[str, Any] | None = None
    instant_local: str | None = None


@dataclass(frozen=True)
class ExpressionAmbiguousPayload:
    """Payload for an ambiguous temporal expression."""

    session_id: str
    raw_text: str
    reason: str
    resolved_at_utc: str


__all__ = [
    "AnchorCreatedPayload",
    "AnchorRefreshedPayload",
    "AnchorStalePayload",
    "ExpressionAmbiguousPayload",
    "ExpressionResolvedPayload",
    "TEMPORAL_ANCHOR_CREATED",
    "TEMPORAL_ANCHOR_REFRESHED",
    "TEMPORAL_ANCHOR_STALE",
    "TEMPORAL_EXPRESSION_AMBIGUOUS",
    "TEMPORAL_EXPRESSION_RESOLVED",
]
