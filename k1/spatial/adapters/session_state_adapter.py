"""SessionState adapter for spatial and place-registry projections."""

from __future__ import annotations

from typing import Any, Mapping, cast

from k1.spatial.ports import ISpatialStatePort


class SpatialStateAdapter(ISpatialStatePort):
    """Write spatial payloads through a narrow SessionState boundary."""

    def __init__(self, manager: Any | None = None) -> None:
        self._manager = manager
        self._memory: dict[tuple[str, str], dict[str, Any]] = {}

    async def write_spatial_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        await self._write(session_id, "spatial", payload)

    async def read_spatial_section(self, session_id: str) -> Mapping[str, Any] | None:
        return await self._read(session_id, "spatial")

    async def write_place_registry_section(
        self,
        session_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        await self._write(session_id, "place_registry", payload)

    async def read_place_registry_section(self, session_id: str) -> Mapping[str, Any] | None:
        return await self._read(session_id, "place_registry")

    async def _write(self, session_id: str, section_name: str, payload: Mapping[str, Any]) -> None:
        section = self._section(session_id, section_name)
        if section is not None:
            method = getattr(section, "replace", None) or getattr(section, "set_payload", None)
            if callable(method):
                method(dict(payload))
                return
            method = getattr(section, "update", None)
            if callable(method):
                method(dict(payload))
                return
        self._memory[(session_id, section_name)] = dict(payload)

    async def _read(self, session_id: str, section_name: str) -> Mapping[str, Any] | None:
        section = self._section(session_id, section_name)
        if section is not None:
            for name in ("to_dict", "get_payload", "get_metadata"):
                method = getattr(section, name, None)
                if callable(method):
                    value = method()
                    if isinstance(value, Mapping):
                        return dict(cast(Mapping[str, Any], value))
        payload = self._memory.get((session_id, section_name))
        return dict(payload) if payload is not None else None

    def _section(self, session_id: str, section_name: str) -> Any | None:
        if self._manager is None:
            return None
        for method_name in ("get_section", "section"):
            method = getattr(self._manager, method_name, None)
            if callable(method):
                try:
                    return method(section_name)
                except TypeError:
                    return method(session_id, section_name)
        sections = getattr(self._manager, "sections", None)
        if isinstance(sections, Mapping):
            return sections.get(section_name)
        return None


__all__ = ["SpatialStateAdapter"]
