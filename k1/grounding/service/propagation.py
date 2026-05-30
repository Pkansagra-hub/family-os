"""Grounding propagation metadata helpers."""

from __future__ import annotations

from typing import Any, Mapping

from k1.grounding.constants import (
    PROPAGATION_FIELD_ENVELOPE_ID,
    PROPAGATION_FIELD_RESOLVED_SPATIAL_REFS,
    PROPAGATION_FIELD_RESOLVED_TEMPORAL_REFS,
    PROPAGATION_FIELD_SPATIAL_CONTEXT_ID,
    PROPAGATION_FIELD_TEMPORAL_ANCHOR_ID,
)
from k1.grounding.types import GroundingProjection


def build_propagation_metadata(
    projection: GroundingProjection,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable propagation metadata field set."""
    metadata: dict[str, Any] = {
        PROPAGATION_FIELD_ENVELOPE_ID: projection.envelope_id,
        PROPAGATION_FIELD_TEMPORAL_ANCHOR_ID: projection.temporal.anchor.anchor_id,
        PROPAGATION_FIELD_SPATIAL_CONTEXT_ID: projection.spatial.context_id,
        PROPAGATION_FIELD_RESOLVED_TEMPORAL_REFS: {
            item.raw_text: item.normalized_label
            for item in projection.temporal.resolved_expressions
            if item.raw_text
        },
        PROPAGATION_FIELD_RESOLVED_SPATIAL_REFS: {
            item.place_id: item.label for item in projection.spatial.place_refs if item.place_id
        },
    }
    metadata.update(dict(extra or {}))
    return metadata


def attach_propagation_metadata(
    payload: Mapping[str, Any], projection: GroundingProjection
) -> dict[str, Any]:
    """Return a copy of payload with grounding propagation fields attached."""
    merged = dict(payload)
    merged.update(build_propagation_metadata(projection))
    return merged


__all__ = ["attach_propagation_metadata", "build_propagation_metadata"]
