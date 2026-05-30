"""Spatial adapter used by grounding before the M3 spatial runtime lands."""

from __future__ import annotations

from typing import Any

from k1.grounding.ports import IGroundingSpatialPort
from k1.spatial.types import SpatialProjection


class SpatialHandleAdapter(IGroundingSpatialPort):
    """Return a spatial projection from a handle or an unknown hidden fallback."""

    def __init__(self, spatial_handle: Any | None = None) -> None:
        self._handle = spatial_handle

    async def refresh_turn(
        self,
        session_id: str,
        consumer: str,
        *,
        device_id: str | None = None,
        installation_id: str | None = None,
        requested_precision: str | None = None,
    ) -> SpatialProjection:
        """Refresh the underlying spatial handle before projection use."""
        method = getattr(self._handle, "refresh_turn", None) if self._handle is not None else None
        if callable(method):
            snapshot = await method(
                session_id,
                consumer=consumer,
                device_id=device_id,
                installation_id=installation_id,
            )
            if requested_precision is None:
                projection = getattr(snapshot, "projection", None)
                if isinstance(projection, SpatialProjection):
                    return projection
            return await self.build_projection(
                session_id,
                consumer,
                device_id=device_id,
                installation_id=installation_id,
                requested_precision=requested_precision,
            )
        return await self.build_projection(
            session_id,
            consumer,
            device_id=device_id,
            installation_id=installation_id,
            requested_precision=requested_precision,
        )

    async def build_projection(
        self,
        session_id: str,
        consumer: str,
        *,
        device_id: str | None = None,
        installation_id: str | None = None,
        requested_precision: str | None = None,
    ) -> SpatialProjection:
        method = (
            getattr(self._handle, "build_projection", None) if self._handle is not None else None
        )
        if callable(method):
            return await method(
                session_id,
                consumer=consumer,
                device_id=device_id,
                installation_id=installation_id,
                requested_precision=requested_precision,
            )
        method = getattr(self._handle, "get_projection", None) if self._handle is not None else None
        if callable(method):
            return await method(consumer=consumer)
        return build_unknown_spatial_projection(
            session_id=session_id,
            consumer=consumer,
            requested_precision=requested_precision,
        )


def build_unknown_spatial_projection(
    *,
    session_id: str,
    consumer: str,
    requested_precision: str | None = None,
) -> SpatialProjection:
    """Build the M1.5 unknown/hidden spatial projection placeholder."""
    return SpatialProjection(
        projection_id=f"spatial-unknown-{session_id}",
        context_id="unknown",
        session_id=session_id,
        consumer=consumer,
        semantic_place="unknown",
        precision=requested_precision or "hidden",
        place_refs=(),
        active_device_surface="unknown",
        co_presence=(),
        freshness="unavailable",
        redactions=("source_unavailable",),
    )


UnknownSpatialAdapter = SpatialHandleAdapter

__all__ = ["SpatialHandleAdapter", "UnknownSpatialAdapter", "build_unknown_spatial_projection"]
