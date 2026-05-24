"""Consumer-specific rendering of TemporalProjection values."""

from __future__ import annotations

from typing import Any

from k1.temporal.serialization import projection_to_dict
from k1.temporal.types import TemporalProjection


def render_projection(projection: TemporalProjection) -> dict[str, Any]:
    """Render a projection as structured data, preserving canonical fields."""

    data = projection_to_dict(projection)
    if projection.consumer == "front":
        anchor = projection.anchor
        data["summary"] = {
            "local_date": anchor.local_date,
            "local_time": anchor.local_time,
            "day_of_week": anchor.day_of_week,
            "time_of_day": anchor.time_of_day,
            "timezone": anchor.timezone,
        }
    return data


def render_now_block(projection: TemporalProjection) -> str:
    """Render a compact NOW block from a typed projection."""
    anchor = projection.anchor
    kind = "weekend" if anchor.is_weekend else "weekday"
    parts = [
        anchor.now_local,
        anchor.day_of_week,
        anchor.time_of_day,
        anchor.timezone,
    ]
    joined = " | ".join(part for part in parts if part)
    return f"== NOW ==\n{joined} ({kind}, {projection.freshness})"


def render_execution_block(projection: TemporalProjection) -> str:
    """Render a task-facing temporal execution block."""
    anchor = projection.anchor
    lines = [
        "== TEMPORAL CONTEXT ==",
        f"anchor_id: {anchor.anchor_id}",
        f"now_utc: {anchor.now_utc}",
        f"now_local: {anchor.now_local}",
        f"timezone: {anchor.timezone} ({anchor.timezone_source})",
        f"local_date: {anchor.local_date}",
        f"day: {anchor.day_of_week} {anchor.time_of_day}",
        f"freshness: {projection.freshness}",
    ]
    for key in ("today", "tomorrow", "this_week", "next_week", "this_weekend", "next_weekend"):
        window = projection.windows.get(key)
        if window is not None:
            lines.append(
                f"{key}: {window.start_local} -> {window.end_local} "
                f"({window.start_utc} -> {window.end_utc})"
            )
    if projection.resolved_expressions:
        lines.append("resolved_expressions:")
        for resolution in projection.resolved_expressions:
            lines.append(
                f"- {resolution.raw_text}: {resolution.normalized_label} "
                f"[{resolution.resolution_kind}, confidence={resolution.confidence:.2f}]"
            )
    return "\n".join(lines)


__all__ = ["render_execution_block", "render_now_block", "render_projection"]
