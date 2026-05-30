"""Build consumer grounding projections from canonical envelopes."""

from __future__ import annotations

from typing import Any, Mapping

from k1.grounding.types import ConsumerScope, GroundingEnvelope, GroundingProjection


def build_projection(
    *,
    projection_id: str,
    envelope: GroundingEnvelope,
    scope: ConsumerScope,
    metadata: Mapping[str, Any] | None = None,
) -> GroundingProjection:
    """Build a consumer projection while preserving temporal and spatial slots."""
    redactions = tuple(dict.fromkeys((*envelope.redactions, *scope.denied_context_sections)))
    projection_metadata = {
        "session_id": envelope.session_id,
        "turn_id": envelope.turn_id,
        "trace_id": envelope.trace_id,
        "identity_ref": envelope.identity_ref,
        "group_refs": list(envelope.group_refs),
        "device_surface": envelope.device_surface,
        "policy_scope": envelope.policy_scope,
    }
    projection_metadata.update(dict(metadata or {}))
    return GroundingProjection(
        projection_id=projection_id,
        envelope_id=envelope.envelope_id,
        consumer=scope.consumer,
        temporal=envelope.temporal,
        spatial=envelope.spatial,
        freshness=envelope.freshness,
        redactions=redactions,
        metadata=projection_metadata,
    )


__all__ = ["build_projection"]
