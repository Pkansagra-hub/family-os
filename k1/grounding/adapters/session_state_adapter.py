"""Grounding SessionState adapter."""

from __future__ import annotations

from typing import Any, Mapping

from k1.grounding.ports import IGroundingStatePort


class GroundingStateAdapter(IGroundingStatePort):
    """Read/write the grounding section through a SessionState-like manager."""

    def __init__(self, manager: Any | None = None, *, allow_memory_fallback: bool = False) -> None:
        self._manager = manager
        self._allow_memory_fallback = allow_memory_fallback
        self._memory: dict[str, dict[str, Any]] = {}

    async def write_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        data = dict(payload)
        if self._manager is None:
            if not self._allow_memory_fallback:
                raise RuntimeError("GroundingStateAdapter requires a SessionState manager")
            self._memory[session_id] = data
            return

        section = self._get_grounding_section()
        if section is None:
            if self._allow_memory_fallback:
                self._memory[session_id] = data
                return
            raise RuntimeError("SessionState grounding section is not available")

        if hasattr(section, "set_data"):
            section.set_data(data)
            return
        if hasattr(section, "set"):
            section.set(data)
            return
        setattr(section, "_data", data)

    async def read_section(self, session_id: str) -> Mapping[str, Any] | None:
        if self._manager is None:
            return self._memory.get(session_id)
        section = self._get_grounding_section()
        if section is None:
            return self._memory.get(session_id)
        if hasattr(section, "to_dict"):
            value = section.to_dict()
            return value if isinstance(value, Mapping) else None
        if hasattr(section, "get_data"):
            value = section.get_data()
            return value if isinstance(value, Mapping) else None
        value = getattr(section, "_data", None)
        return value if isinstance(value, Mapping) else None

    def _get_grounding_section(self) -> Any | None:
        try:
            return self._manager.get_section("grounding")
        except Exception:
            return None


__all__ = ["GroundingStateAdapter"]
