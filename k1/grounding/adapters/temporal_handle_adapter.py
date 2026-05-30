"""Adapter from TemporalHandle to the grounding temporal port."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from k1.grounding.ports import IGroundingTemporalPort
from k1.temporal.types import CandidateSpan, TemporalProjection, TemporalTurnSnapshot


class TemporalHandleAdapter(IGroundingTemporalPort):
    """Expose a TemporalHandle through the grounding temporal boundary."""

    def __init__(self, temporal_handle: Any) -> None:
        self._handle = temporal_handle

    async def build_projection(self, session_id: str, consumer: str) -> TemporalProjection:
        method = getattr(self._handle, "build_projection", None)
        if callable(method):
            return await method(session_id, consumer=consumer)
        method = getattr(self._handle, "get_projection", None)
        if callable(method):
            return await method(consumer=consumer)
        raise RuntimeError("Temporal handle does not expose a projection method")

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
        method = getattr(self._handle, "refresh_turn", None)
        if not callable(method):
            raise RuntimeError("Temporal handle does not expose refresh_turn")
        return await method(
            session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            candidates=candidates,
            device_id=device_id,
            installation_id=installation_id,
        )


__all__ = ["TemporalHandleAdapter"]
