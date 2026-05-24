"""Invocation metadata helpers for tool, task, and agent calls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from k1.grounding.types import AgentGroundingLease, GroundingProjection


def build_invocation_metadata(
    projection: GroundingProjection,
    *,
    lease: AgentGroundingLease | None = None,
    invoked_at_utc: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metadata that binds an invocation to grounding references."""
    metadata = {
        "invoked_at_utc": invoked_at_utc or datetime.now(timezone.utc).isoformat(),
        "grounding_envelope_id": projection.envelope_id,
        "grounding_projection_id": projection.projection_id,
        "temporal_anchor_id": projection.temporal.anchor.anchor_id,
        "spatial_context_id": projection.spatial.context_id,
        "resolved_temporal_refs": [
            item.normalized_label for item in projection.temporal.resolved_expressions
        ],
        "resolved_spatial_refs": [item.place_id for item in projection.spatial.place_refs],
    }
    if lease is not None:
        metadata["grounding_lease_id"] = lease.lease_id
        metadata["grounding_lease_expires_at_utc"] = lease.expires_at_utc
    metadata.update(dict(extra or {}))
    return metadata


__all__ = ["build_invocation_metadata"]
