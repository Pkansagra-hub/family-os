"""Null routine adapter for deployments without routine data."""

from __future__ import annotations

from collections.abc import Sequence

from k1.temporal.ports import IRoutinePort
from k1.temporal.types import RoutineRef, TemporalAnchor, TemporalWindow


class NullRoutineAdapter(IRoutinePort):
    """Return explicit routine-unavailable results."""

    async def get_window(self, routine_id: str, anchor: TemporalAnchor) -> TemporalWindow | None:
        return None

    async def list_routines(self, principal_id: str | None = None) -> Sequence[RoutineRef]:
        return ()


__all__ = ["NullRoutineAdapter"]
