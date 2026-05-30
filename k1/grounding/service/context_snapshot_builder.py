"""Device-context snapshot helpers for grounding."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from k1.grounding.types import DeviceContextSnapshot


def build_device_context_snapshot(
    *,
    session_id: str = "",
    device_id: str | None = None,
    installation_id: str | None = None,
    surface: str = "unknown",
    locale: str | None = None,
    timezone: str | None = None,
    clock_skew_ms: int | None = None,
    location_permission: str = "unknown",
    location_fix: Mapping[str, Any] | None = None,
    semantic_place_hint: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DeviceContextSnapshot:
    """Build a prompt-safe installed-device context snapshot."""
    return DeviceContextSnapshot(
        session_id=session_id,
        device_id=device_id or "",
        installation_id=installation_id or "",
        observed_at_utc=datetime.now(UTC).isoformat(),
        surface=surface,
        timezone=timezone,
        locale=locale,
        clock_skew_ms=clock_skew_ms,
        location_permission=location_permission,
        location_fix=location_fix,
        semantic_place_hint=semantic_place_hint,
        metadata=dict(metadata or {}),
    )


__all__ = ["build_device_context_snapshot"]
