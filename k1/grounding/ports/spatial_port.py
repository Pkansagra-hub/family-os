"""Grounding boundary to the spatial kernel module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.spatial.types import SpatialProjection


@runtime_checkable
class IGroundingSpatialPort(Protocol):
    """Provide spatial projections for grounding envelopes."""

    async def refresh_turn(
        self,
        session_id: str,
        consumer: str,
        *,
        device_id: str | None = None,
        installation_id: str | None = None,
        requested_precision: str | None = None,
    ) -> SpatialProjection:
        """Refresh spatial state and return a consumer-safe projection."""
        ...  # pragma: no cover

    async def build_projection(
        self,
        session_id: str,
        consumer: str,
        *,
        device_id: str | None = None,
        installation_id: str | None = None,
        requested_precision: str | None = None,
    ) -> SpatialProjection:
        """Return a consumer-safe spatial projection for the session."""
        ...  # pragma: no cover


__all__ = ["IGroundingSpatialPort"]
