"""Pure payload types for the k1.grounding kernel module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from k1.spatial.types import SpatialProjection
from k1.temporal.types import TemporalProjection

Consumer = Literal["front", "back", "planner", "fabric", "agent", "tool", "memory"]
GroundingFreshnessState = Literal["live", "stale", "degraded", "unavailable"]
GroundingSourceKind = Literal["temporal", "spatial", "identity", "device", "policy", "selfmodel"]
LeaseStatus = Literal["active", "expired", "revoked", "refresh_required"]


@dataclass(frozen=True)
class DeviceContextSnapshot:
    """Shared installed-device observation consumed by temporal and spatial."""

    session_id: str
    device_id: str
    installation_id: str
    observed_at_utc: str
    surface: str
    timezone: str | None = None
    locale: str | None = None
    clock_skew_ms: int | None = None
    location_permission: str = "unknown"
    location_fix: Mapping[str, Any] | None = None
    semantic_place_hint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundingFreshness:
    """Aggregated freshness for an envelope or projection."""

    status: GroundingFreshnessState | str
    generated_at_utc: str
    age_ms: int
    source_status: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundingSource:
    """Provenance record for one grounding input."""

    source: GroundingSourceKind | str
    source_id: str | None
    captured_at_utc: str
    confidence: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsumerScope:
    """Policy scope applied while building a consumer projection."""

    consumer: Consumer
    allowed_context_sections: tuple[str, ...]
    denied_context_sections: tuple[str, ...]
    temporal_precision: str
    spatial_precision: str
    privacy_scope: str


@dataclass(frozen=True)
class GroundingEnvelope:
    """Canonical per-turn binding of identity, time, place, and policy."""

    envelope_id: str
    session_id: str
    turn_id: str | None
    trace_id: str | None
    created_at_utc: str
    consumer: Consumer
    identity_ref: str | None
    temporal: TemporalProjection
    spatial: SpatialProjection
    group_refs: tuple[str, ...]
    device_surface: str | None
    policy_scope: str
    freshness: GroundingFreshness
    provenance: tuple[GroundingSource, ...]
    redactions: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundingProjection:
    """Policy-filtered projection derived from a grounding envelope."""

    projection_id: str
    envelope_id: str
    consumer: Consumer
    temporal: TemporalProjection
    spatial: SpatialProjection
    freshness: GroundingFreshness
    redactions: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentGroundingLease:
    """TTL-bound grounding projection granted to a spawned agent."""

    lease_id: str
    envelope_id: str
    issued_at_utc: str
    expires_at_utc: str
    temporal: TemporalProjection
    spatial: SpatialProjection
    subject_ref: str | None
    group_refs: tuple[str, ...]
    role_refs: tuple[str, ...]
    task_scope: str
    privacy_scope: str
    allowed_context_sections: tuple[str, ...]
    denied_context_sections: tuple[str, ...]
    redactions: tuple[str, ...]
    refresh_allowed: bool
    status: LeaseStatus | str = "active"
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "AgentGroundingLease",
    "Consumer",
    "ConsumerScope",
    "DeviceContextSnapshot",
    "GroundingFreshnessState",
    "GroundingEnvelope",
    "GroundingFreshness",
    "GroundingProjection",
    "GroundingSource",
    "GroundingSourceKind",
    "LeaseStatus",
]
