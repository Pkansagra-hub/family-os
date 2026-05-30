"""Persona preference timezone adapter."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

from k1.temporal.ports import ITimezonePort


class PersonaTimezoneAdapter(ITimezonePort):
    """Read an IANA timezone from an injected persona/preference reader."""

    def __init__(self, persona_reader: Any) -> None:
        self._persona_reader = persona_reader

    async def candidate_for_principal(self, principal_id: str) -> str | None:
        prefs = await self._read_preferences(principal_id)
        if not isinstance(prefs, Mapping):
            return None
        value = prefs.get("timezone")
        return str(value) if value else None

    async def _read_preferences(self, principal_id: str) -> Mapping[str, Any] | None:
        reader = self._persona_reader
        for name in ("get_preferences", "preferences_for_principal", "get_all_preferences"):
            method = getattr(reader, name, None)
            if not callable(method):
                continue
            try:
                if name == "get_all_preferences":
                    result = method()
                else:
                    result = method(principal_id)
                if inspect.isawaitable(result):
                    result = await result
                return result if isinstance(result, Mapping) else None
            except TypeError:
                continue
        if isinstance(reader, Mapping):
            value = reader.get(principal_id, reader)
            return value if isinstance(value, Mapping) else None
        return None


__all__ = ["PersonaTimezoneAdapter"]
