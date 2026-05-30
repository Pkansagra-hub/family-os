"""Grounding boundary to the temporal kernel module."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from k1.temporal.types import CandidateSpan, TemporalProjection, TemporalTurnSnapshot


@runtime_checkable
class IGroundingTemporalPort(Protocol):
    """Provide temporal projections for grounding envelopes."""

    async def build_projection(self, session_id: str, consumer: str) -> TemporalProjection:
        """Return a consumer-safe temporal projection for the session."""
        ...  # pragma: no cover

    async def refresh_turn(
        self,
        session_id: str,
        *,
        turn_id: str | None = None,
        trace_id: str | None = None,
        candidates: Iterable[str | CandidateSpan] = (),
        device_id: str | None = None,
        installation_id: str | None = None,
    ) -> TemporalTurnSnapshot:
        """Refresh temporal state for a turn before projection."""
        ...  # pragma: no cover


__all__ = ["IGroundingTemporalPort"]
