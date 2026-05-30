"""Event topics and payloads emitted by the grounding kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

GROUNDING_ENVELOPE_CREATED = "k1.grounding.envelope.created.v1"
GROUNDING_PROJECTION_CREATED = "k1.grounding.projection.created.v1"
GROUNDING_LEASE_CREATED = "k1.grounding.lease.created.v1"
GROUNDING_ENVELOPE_STALE = "k1.grounding.envelope.stale.v1"
GROUNDING_PROJECTION_DENIED = "k1.grounding.projection.denied.v1"


@dataclass(frozen=True)
class GroundingEnvelopeCreatedPayload:
    """Payload emitted when a new grounding envelope is built."""

    envelope_id: str
    session_id: str
    created_at_utc: str
    temporal_anchor_id: str | None
    spatial_context_id: str | None
    trace_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundingProjectionCreatedPayload:
    """Payload emitted when a consumer projection is built."""

    projection_id: str
    envelope_id: str
    session_id: str
    consumer: str
    created_at_utc: str
    redactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroundingLeaseCreatedPayload:
    """Payload emitted when an agent grounding lease is issued."""

    lease_id: str
    envelope_id: str
    issued_at_utc: str
    expires_at_utc: str
    task_scope: str
    subject_ref: str | None = None


@dataclass(frozen=True)
class GroundingEnvelopeStalePayload:
    """Payload emitted when a grounding envelope exceeds freshness policy."""

    envelope_id: str
    session_id: str
    stale_since_utc: str
    age_ms: int
    freshness_state: str


@dataclass(frozen=True)
class GroundingProjectionDeniedPayload:
    """Payload emitted when projection policy denies a consumer request."""

    envelope_id: str
    session_id: str
    consumer: str
    reason: str
    denied_at_utc: str


__all__ = [
    "GROUNDING_ENVELOPE_CREATED",
    "GROUNDING_ENVELOPE_STALE",
    "GROUNDING_LEASE_CREATED",
    "GROUNDING_PROJECTION_CREATED",
    "GROUNDING_PROJECTION_DENIED",
    "GroundingEnvelopeCreatedPayload",
    "GroundingEnvelopeStalePayload",
    "GroundingLeaseCreatedPayload",
    "GroundingProjectionCreatedPayload",
    "GroundingProjectionDeniedPayload",
]
