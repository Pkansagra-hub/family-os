"""k1.kernel.ports.spatial_port -- ISpatialPort.

Kernel-visible Protocol for spatial service; see k1.spatial package.
Only pure payload types are imported here so boundary imports stay light.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k1.spatial.types import (
    LocationFix,
    PlaceRef,
    SpatialContext,
    SpatialProjection,
    SpatialTurnSnapshot,
)


@runtime_checkable
class ISpatialPort(Protocol):
    """Kernel boundary for authoritative spatial grounding."""

    async def get_context(self, session_id: str) -> SpatialContext:
        """Return current policy-normalized spatial context for a session."""
        ...  # pragma: no cover

    async def resolve_place(
        self,
        session_id: str,
        text: str,
        *,
        subject_ref: str | None = None,
    ) -> PlaceRef | None:
        """Resolve a place mention as candidate evidence, if possible."""
        ...  # pragma: no cover

    async def build_projection(self, session_id: str, consumer: str) -> SpatialProjection:
        """Build a policy-shaped spatial projection for a consumer."""
        ...  # pragma: no cover

    async def refresh_turn(
        self,
        session_id: str,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
    ) -> SpatialTurnSnapshot:
        """Refresh spatial state for a new turn and write SessionState."""
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Release spatial resources owned by this handle or bundle."""
        ...  # pragma: no cover


__all__ = [
    "ISpatialPort",
    "LocationFix",
    "PlaceRef",
    "SpatialContext",
    "SpatialProjection",
    "SpatialTurnSnapshot",
]
