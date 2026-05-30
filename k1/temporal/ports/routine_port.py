"""Routine window port."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from k1.temporal.types import RoutineRef, TemporalAnchor, TemporalWindow


@runtime_checkable
class IRoutinePort(Protocol):
    """Routine lookup boundary for expressions such as after routine_id."""

    async def get_window(self, routine_id: str, anchor: TemporalAnchor) -> TemporalWindow | None:
        """Return a routine-backed window, if known and allowed."""
        ...  # pragma: no cover

    async def list_routines(self, principal_id: str | None = None) -> Sequence[RoutineRef]:
        """Return routine references available to the principal."""
        ...  # pragma: no cover


__all__ = ["IRoutinePort"]
