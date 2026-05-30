"""Temporal SessionState adapter."""

from __future__ import annotations

from typing import Any, Mapping

from k1.sessionstate.manager import SectionNotFoundError
from k1.temporal.ports import ITemporalStatePort


class TemporalStateAdapter(ITemporalStatePort):
    """Read/write the temporal section through a SessionState-like manager."""

    def __init__(self, manager: Any | None = None, *, allow_memory_fallback: bool = False) -> None:
        self._manager = manager
        self._allow_memory_fallback = allow_memory_fallback
        self._memory: dict[str, dict[str, Any]] = {}

    async def write_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        data = dict(payload)
        if self._manager is None:
            if not self._allow_memory_fallback:
                raise RuntimeError("TemporalStateAdapter requires a SessionState manager")
            self._memory[session_id] = data
            return

        section = self._get_temporal_section()
        if section is None:
            if self._allow_memory_fallback:
                self._memory[session_id] = data
                return
            raise SectionNotFoundError("temporal")

        if hasattr(section, "set_data"):
            section.set_data(data)
            return
        if hasattr(section, "set"):
            section.set(data)
            return
        if hasattr(section, "set_anchor"):
            if "anchor" in data:
                section.set_anchor(data.get("anchor"))
            if "windows" in data and hasattr(section, "set_windows"):
                section.set_windows(data.get("windows") or {})
            if "resolved_expressions" in data and hasattr(section, "set_resolutions"):
                section.set_resolutions(data.get("resolved_expressions") or [])
            if "last_turn_id" in data and hasattr(section, "set_last_turn_id"):
                section.set_last_turn_id(data.get("last_turn_id"))
            return
        setattr(section, "_data", data)

    async def read_section(self, session_id: str) -> Mapping[str, Any] | None:
        if self._manager is None:
            return self._memory.get(session_id)
        section = self._get_temporal_section()
        if section is None:
            return self._memory.get(session_id)
        if hasattr(section, "to_dict"):
            value = section.to_dict()
            return value if isinstance(value, Mapping) else None
        if hasattr(section, "get_data"):
            value = section.get_data()
            return value if isinstance(value, Mapping) else None
        if hasattr(section, "get_anchor"):
            return {
                "anchor": section.get_anchor(),
                "windows": section.get_windows() if hasattr(section, "get_windows") else {},
                "resolved_expressions": (
                    section.get_resolutions() if hasattr(section, "get_resolutions") else []
                ),
            }
        value = getattr(section, "_data", None)
        return value if isinstance(value, Mapping) else None

    def _get_temporal_section(self) -> Any | None:
        try:
            return self._manager.get_section("temporal")
        except Exception:
            return None


__all__ = ["TemporalStateAdapter"]
