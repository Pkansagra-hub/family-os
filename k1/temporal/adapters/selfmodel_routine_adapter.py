"""SelfModel-backed routine adapter."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any, Mapping

from k1.temporal.ports import IRoutinePort
from k1.temporal.types import RoutineRef, TemporalAnchor, TemporalWindow


class SelfModelRoutineAdapter(IRoutinePort):
    """Read routine references through an injected SelfModel-compatible source."""

    def __init__(self, source: Any) -> None:
        self._source = source

    async def get_window(self, routine_id: str, anchor: TemporalAnchor) -> TemporalWindow | None:
        method = getattr(self._source, "get_routine_window", None)
        if not callable(method):
            return None
        result = method(routine_id, anchor)
        if inspect.isawaitable(result):
            result = await result
        return result if isinstance(result, TemporalWindow) else None

    async def list_routines(self, principal_id: str | None = None) -> Sequence[RoutineRef]:
        method = getattr(self._source, "list_routines", None)
        if not callable(method):
            return ()
        result = method(principal_id)
        if inspect.isawaitable(result):
            result = await result
        refs: list[RoutineRef] = []
        for item in result or ():
            if isinstance(item, RoutineRef):
                refs.append(item)
            elif isinstance(item, Mapping):
                refs.append(
                    RoutineRef(
                        routine_id=str(item.get("routine_id") or item.get("id") or ""),
                        label=str(item.get("label") or item.get("name") or ""),
                        routine_kind=str(item.get("routine_kind") or item.get("kind") or "routine"),
                        metadata=dict(item.get("metadata") or {}),
                    )
                )
        return tuple(ref for ref in refs if ref.routine_id)


__all__ = ["SelfModelRoutineAdapter"]
