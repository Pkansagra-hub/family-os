"""Spatial timezone candidate adapter."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from k1.temporal.ports import ITimezonePort


class SpatialTimezoneAdapter(ITimezonePort):
    """Read timezone hints from spatial context when spatial is available."""

    def __init__(self, spatial_source: Any | None, *, enabled: bool = False) -> None:
        self._spatial_source = spatial_source
        self._enabled = enabled

    async def candidate_for_principal(self, principal_id: str) -> str | None:
        if not self._enabled or self._spatial_source is None:
            return None
        source = self._spatial_source
        for name in ("candidate_timezone_for_principal", "candidate_for_principal"):
            method = getattr(source, name, None)
            if callable(method):
                result = method(principal_id)
                if inspect.isawaitable(result):
                    result = await result
                return str(result) if result else None
        if isinstance(source, Mapping):
            value = source.get("timezone") or source.get("local_timezone")
            return str(value) if value else None
        return None


__all__ = ["SpatialTimezoneAdapter"]
