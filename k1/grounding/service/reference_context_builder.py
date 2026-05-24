"""Reference-context helpers for propagating grounding IDs."""

from __future__ import annotations

from typing import Any

from k1.grounding.types import GroundingProjection


def build_reference_context(projection: GroundingProjection) -> dict[str, Any]:
    """Return a compact reference context for downstream calls."""
    return {
        "grounding_envelope_id": projection.envelope_id,
        "temporal_anchor_id": projection.temporal.anchor.anchor_id,
        "spatial_context_id": projection.spatial.context_id,
        "projection_id": projection.projection_id,
        "consumer": projection.consumer,
    }


__all__ = ["build_reference_context"]
