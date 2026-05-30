"""Prompt block rendering for grounding projections."""

from __future__ import annotations

import json

from k1.grounding.types import AgentGroundingLease, GroundingProjection

# ---------------------------------------------------------------------------
# Front Iteration 2 typed blocks
# ---------------------------------------------------------------------------
#
# Iteration 2 of the Front prompt seats the typed ``GroundingProjection``
# directly into three structured blocks: ``[grounding]`` (envelope metadata
# and freshness), ``[time]`` (temporal anchor + windows + resolved
# expressions), and ``[place_and_device]`` (spatial projection + active
# device surface). These are the canonical successors to the v1
# ``== NOW ==`` and ``== PLACE ==`` headers when
# ``prompt.front_prompt_iteration == "v2"``.


def render_grounding_meta_block_v2(projection: GroundingProjection) -> str:
    """Render the Front Iteration 2 ``== GROUNDING ==`` envelope block."""
    freshness = projection.freshness
    lines = [
        "== GROUNDING ==",
        f"projection_id: {projection.projection_id}",
        f"envelope_id: {projection.envelope_id}",
        f"consumer: {projection.consumer}",
        f"freshness.status: {freshness.status}",
        f"freshness.generated_at_utc: {freshness.generated_at_utc}",
        f"freshness.age_ms: {freshness.age_ms}",
    ]
    if freshness.source_status:
        compact = ", ".join(f"{k}={v}" for k, v in sorted(freshness.source_status.items()))
        lines.append(f"freshness.source_status: {compact}")
    if projection.redactions:
        lines.append(f"redactions: {', '.join(projection.redactions)}")
    lines.append(
        "Rule: these grounding values are authoritative for this turn. "
        "Do not override them with chat-history guesses or native model priors."
    )
    return "\n".join(lines)


def render_time_block_v2(projection: GroundingProjection) -> str:
    """Render the Front Iteration 2 ``== TIME ==`` typed block."""
    temporal = projection.temporal
    anchor = temporal.anchor
    kind = "weekend" if anchor.is_weekend else "weekday"
    lines = [
        "== TIME ==",
        f"now_local: {anchor.now_local}",
        f"local_date: {anchor.local_date}",
        f"local_time: {anchor.local_time}",
        f"day_of_week: {anchor.day_of_week} ({kind})",
        f"time_of_day: {anchor.time_of_day}",
        f"timezone: {anchor.timezone} (source={anchor.timezone_source})",
    ]
    if anchor.locale:
        lines.append(f"locale: {anchor.locale}")
    lines.append(f"precision: {temporal.precision}")
    lines.append(f"freshness: {temporal.freshness}")
    if temporal.windows:
        window_labels = ", ".join(sorted(temporal.windows.keys()))
        lines.append(f"windows: {window_labels}")
    if temporal.resolved_expressions:
        lines.append("resolved_expressions:")
        for resolution in temporal.resolved_expressions:
            detail = (
                resolution.instant_local
                or resolution.clarification_reason
                or resolution.resolution_kind
            )
            lines.append(
                f"- {resolution.raw_text} -> {resolution.normalized_label} "
                f"({resolution.resolution_kind}: {detail})"
            )
    return "\n".join(lines)


def render_place_and_device_block_v2(projection: GroundingProjection) -> str:
    """Render the Front Iteration 2 ``== PLACE AND DEVICE ==`` typed block."""
    spatial = projection.spatial
    place = spatial.semantic_place or "unknown"
    lines = [
        "== PLACE AND DEVICE ==",
        f"semantic_place: {place}",
        f"precision: {spatial.precision}",
        f"freshness: {spatial.freshness}",
        f"location_permission: {spatial.location_permission}",
    ]
    if spatial.active_device_surface:
        lines.append(f"active_device_surface: {spatial.active_device_surface}")
    accuracy_m = _spatial_accuracy_m(spatial)
    if accuracy_m is not None:
        lines.append(f"accuracy_m: {_format_accuracy_m(accuracy_m)}")
    if spatial.place_refs:
        refs = ", ".join(
            f"{ref.place_id}({ref.place_kind})" for ref in spatial.place_refs[:3] if ref.place_id
        )
        if refs:
            lines.append(f"place_refs: {refs}")
    if spatial.co_presence:
        names = ", ".join(ref.subject_ref for ref in spatial.co_presence[:5] if ref.subject_ref)
        if names:
            lines.append(f"co_presence: {names}")
    if spatial.redactions:
        lines.append(f"redactions: {', '.join(spatial.redactions)}")
    return "\n".join(lines)


def render_now_block(projection: GroundingProjection) -> str:
    """Render the user-facing NOW block from a grounding projection."""
    anchor = projection.temporal.anchor
    kind = "weekend" if anchor.is_weekend else "weekday"
    parts = [anchor.now_local, anchor.day_of_week, anchor.time_of_day, anchor.timezone]
    joined = " | ".join(part for part in parts if part)
    return f"== NOW ==\n{joined} ({kind}, {projection.temporal.freshness})"


def render_place_block(projection: GroundingProjection) -> str:
    """Render the user-facing PLACE block from a grounding projection."""
    spatial = projection.spatial
    if spatial.semantic_place:
        place = spatial.semantic_place
    else:
        place = "unknown"
    lines = ["== PLACE ==", f"{place} ({spatial.precision}, {spatial.freshness})"]
    if spatial.active_device_surface and spatial.active_device_surface != "unknown":
        lines.append(f"surface: {spatial.active_device_surface}")
    accuracy_m = _spatial_accuracy_m(spatial)
    if accuracy_m is not None:
        lines.append(f"accuracy_m: {_format_accuracy_m(accuracy_m)}")
    if getattr(spatial, "approximate_location", None) and place == "unknown":
        lines.append("approx_location: available")
    if spatial.place_refs:
        refs = ", ".join(ref.place_id for ref in spatial.place_refs[:3] if ref.place_id)
        if refs:
            lines.append(f"place_refs: {refs}")
    if spatial.redactions:
        lines.append(f"redactions: {', '.join(spatial.redactions)}")
    return "\n".join(lines)


def _spatial_accuracy_m(spatial: object) -> float | None:
    approximate = getattr(spatial, "approximate_location", None)
    if isinstance(approximate, dict):
        value = approximate.get("accuracy_m")
        if value is not None:
            return _to_float(value)
    raw = getattr(spatial, "raw_location", None)
    if raw is not None:
        return _to_float(getattr(raw, "accuracy_m", None))
    metadata = getattr(spatial, "metadata", None)
    if isinstance(metadata, dict):
        return _to_float(metadata.get("location_accuracy_m"))
    return None


def _to_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _format_accuracy_m(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def render_execution_grounding_block(
    projection: GroundingProjection,
    *,
    lease: AgentGroundingLease | None = None,
) -> str:
    """Render task-facing execution grounding."""
    anchor = projection.temporal.anchor
    lines = [
        "== EXECUTION GROUNDING ==",
        f"grounding_envelope_id: {projection.envelope_id}",
        f"temporal_anchor_id: {anchor.anchor_id}",
        f"spatial_context_id: {projection.spatial.context_id}",
        f"now_utc: {anchor.now_utc}",
        f"now_local: {anchor.now_local}",
        f"timezone: {anchor.timezone} ({anchor.timezone_source})",
        f"place: {projection.spatial.semantic_place or 'unknown'} ({projection.spatial.precision})",
        f"freshness: {projection.freshness.status}",
    ]
    if lease is not None:
        lines.append(f"grounding_lease_id: {lease.lease_id}")
        lines.append(f"lease_expires_at_utc: {lease.expires_at_utc}")
    if projection.temporal.resolved_expressions:
        lines.append("resolved_temporal_refs:")
        for resolution in projection.temporal.resolved_expressions:
            if resolution.window is not None:
                window = {
                    "start_local": resolution.window.start_local,
                    "end_local": resolution.window.end_local,
                    "start_utc": resolution.window.start_utc,
                    "end_utc": resolution.window.end_utc,
                    "timezone": resolution.window.timezone,
                    "granularity": resolution.window.granularity,
                }
                detail = json.dumps(window, sort_keys=True)
            elif resolution.instant_local is not None:
                detail = resolution.instant_local
            else:
                detail = resolution.clarification_reason or resolution.resolution_kind
            lines.append(
                f"- {resolution.raw_text}: {resolution.normalized_label} "
                f"({resolution.resolution_kind}) {detail}"
            )
    return "\n".join(lines)


def render_planning_grounding_block(projection: GroundingProjection) -> str:
    """Render planner-facing grounding."""
    anchor = projection.temporal.anchor
    lines = [
        "== PLANNING GROUNDING ==",
        f"grounding_envelope_id: {projection.envelope_id}",
        f"temporal_anchor_id: {anchor.anchor_id}",
        f"spatial_context_id: {projection.spatial.context_id}",
        f"local_date: {anchor.local_date}",
        f"day: {anchor.day_of_week} {anchor.time_of_day}",
        f"timezone: {anchor.timezone}",
        f"place_precision: {projection.spatial.precision}",
    ]
    return "\n".join(lines)


__all__ = [
    "render_execution_grounding_block",
    "render_now_block",
    "render_place_block",
    "render_planning_grounding_block",
]
