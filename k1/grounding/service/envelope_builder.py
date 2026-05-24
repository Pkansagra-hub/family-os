"""Build canonical grounding envelopes from temporal/spatial projections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from k1.grounding.types import GroundingEnvelope, GroundingFreshness, GroundingSource
from k1.spatial.types import SpatialProjection
from k1.temporal.types import TemporalProjection


def build_envelope(
    *,
    envelope_id: str,
    session_id: str,
    consumer: str,
    temporal: TemporalProjection,
    spatial: SpatialProjection,
    identity_ref: str | None = None,
    group_refs: tuple[str, ...] = (),
    device_surface: str | None = None,
    policy_scope: str = "default",
    turn_id: str | None = None,
    trace_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> GroundingEnvelope:
    """Build a canonical envelope that always carries temporal and spatial slots."""
    created_at_utc = datetime.now(UTC).isoformat()
    freshness = _build_freshness(temporal=temporal, spatial=spatial, created_at_utc=created_at_utc)
    provenance = (
        GroundingSource(
            source="temporal",
            source_id=getattr(temporal.anchor, "anchor_id", None),
            captured_at_utc=getattr(temporal.anchor, "captured_at_utc", created_at_utc),
            confidence=float(getattr(temporal.anchor, "confidence", 1.0)),
            metadata={"freshness": temporal.freshness, "precision": temporal.precision},
        ),
        GroundingSource(
            source="spatial",
            source_id=spatial.context_id,
            captured_at_utc=created_at_utc,
            confidence=0.0 if spatial.freshness == "unavailable" else 1.0,
            metadata={"freshness": spatial.freshness, "precision": spatial.precision},
        ),
    )
    redactions = tuple(dict.fromkeys(tuple(spatial.redactions)))
    return GroundingEnvelope(
        envelope_id=envelope_id,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        created_at_utc=created_at_utc,
        consumer=consumer,
        identity_ref=identity_ref,
        temporal=temporal,
        spatial=spatial,
        group_refs=tuple(group_refs),
        device_surface=device_surface or spatial.active_device_surface,
        policy_scope=policy_scope,
        freshness=freshness,
        provenance=provenance,
        redactions=redactions,
        metadata=dict(metadata or {}),
    )


def _build_freshness(
    *, temporal: TemporalProjection, spatial: SpatialProjection, created_at_utc: str
) -> GroundingFreshness:
    source_status = {"temporal": temporal.freshness, "spatial": spatial.freshness}
    if "stale" in source_status.values():
        status = "stale"
    elif "degraded" in source_status.values() or "unavailable" in source_status.values():
        status = "degraded"
    else:
        status = "live"
    return GroundingFreshness(
        status=status,
        generated_at_utc=created_at_utc,
        age_ms=0,
        source_status=source_status,
    )


__all__ = ["build_envelope"]
