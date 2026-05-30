"""k1.kernel.ports.temporal_port -- ITemporalPort.

Kernel-visible Protocol for temporal service; see k1.temporal package.
Only pure payload types are imported here so boundary imports stay light.
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from k1.temporal.types import (
    ResolvedTemporalExpression,
    TemporalAnchor,
    TemporalProjection,
    TemporalTurnSnapshot,
    TemporalWindow,
)


@runtime_checkable
class ITemporalPort(Protocol):
    """Kernel boundary for authoritative temporal grounding."""

    async def get_anchor(self, session_id: str) -> TemporalAnchor:
        """Return the current authoritative temporal anchor for a session."""
        ...  # pragma: no cover

    async def get_windows(self, session_id: str) -> Mapping[str, TemporalWindow]:
        """Return standard local-date windows for the current anchor."""
        ...  # pragma: no cover

    async def resolve_expression(
        self,
        session_id: str,
        text: str,
        *,
        intent: str | None = None,
        subject_ref: str | None = None,
    ) -> ResolvedTemporalExpression:
        """Resolve a typed temporal phrase against the session anchor."""
        ...  # pragma: no cover

    async def build_projection(self, session_id: str, consumer: str) -> TemporalProjection:
        """Build a policy-shaped temporal projection for a consumer."""
        ...  # pragma: no cover

    async def refresh_turn(
        self,
        session_id: str,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
        candidates: tuple[str, ...] = (),
    ) -> TemporalTurnSnapshot:
        """Refresh temporal state for a new turn and write SessionState."""
        ...  # pragma: no cover

    async def shutdown(self) -> None:
        """Release temporal resources owned by this handle or bundle."""
        ...  # pragma: no cover


__all__ = [
    "ITemporalPort",
    "ResolvedTemporalExpression",
    "TemporalAnchor",
    "TemporalProjection",
    "TemporalTurnSnapshot",
    "TemporalWindow",
]
