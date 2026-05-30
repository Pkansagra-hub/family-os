"""Render prompt-safe spatial blocks from SpatialProjection only."""

from __future__ import annotations

from k1.spatial.types import SpatialProjection


def render_place_block(projection: SpatialProjection) -> str:
    """Render compact Front PLACE block."""
    return "\n".join(
        [
            "== PLACE ==",
            f"Surface: {projection.active_device_surface or 'unknown'}",
            f"Active place: {projection.semantic_place or 'unknown'}",
            f"Location precision: {projection.precision}",
            f"Freshness: {projection.freshness}",
        ]
    )


def render_execution_place_block(projection: SpatialProjection) -> str:
    """Render Back execution place context."""
    lines = [
        "== EXECUTION PLACE CONTEXT ==",
        f"spatial_context_id: {projection.context_id}",
        f"surface: {projection.active_device_surface or 'unknown'}",
        f"semantic_place: {projection.semantic_place or 'unknown'}",
        f"location_precision: {projection.precision}",
        f"location_permission: {projection.location_permission}",
    ]
    if projection.place_refs:
        lines.append("relevant_places:")
        for place in projection.place_refs:
            lines.append(f"- {place.place_id}: {place.label} ({place.place_kind})")
    if projection.raw_location is not None:
        lines.append(
            "raw_coordinates: "
            f"{projection.raw_location.latitude},{projection.raw_location.longitude} "
            f"accuracy_m={projection.raw_location.accuracy_m}"
        )
    else:
        lines.append("raw_coordinates: not available to this actor")
    if projection.redactions:
        lines.append("redactions: " + ", ".join(projection.redactions))
    return "\n".join(lines)


def render_planning_spatial_block(projection: SpatialProjection) -> str:
    """Render planner-facing spatial constraints."""
    lines = [
        "== PLANNING SPATIAL ==",
        f"spatial_context_id: {projection.context_id}",
        f"semantic_place: {projection.semantic_place or 'unknown'}",
        f"precision: {projection.precision}",
        f"freshness: {projection.freshness}",
    ]
    if projection.place_refs or projection.relevant_place_refs:
        place_ids = [
            place.place_id for place in (*projection.place_refs, *projection.relevant_place_refs)
        ]
        lines.append("place_ids: " + ", ".join(dict.fromkeys(place_ids)))
    return "\n".join(lines)


__all__ = ["render_execution_place_block", "render_place_block", "render_planning_spatial_block"]
