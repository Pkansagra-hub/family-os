"""SpatialSection: HOT spatial context and projection state."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any


class SpatialSection:
    """Canonical HOT SessionState section for k1.spatial."""

    BUDGET_BYTES: int = 4 * 1024
    TIER: str = "hot"
    CAN_EVICT: bool = False
    SECTION_NAME: str = "spatial"

    __slots__ = (
        "_session_id",
        "_current",
        "_projection",
        "_active_place",
        "_active_device_surface",
        "_co_presence_summary",
        "_mentioned_places_this_turn",
        "_freshness",
        "_redactions",
        "_last_turn_id",
        "_last_updated_ms",
        "_extra",
    )

    def __init__(self, session_id: str = "") -> None:
        self._session_id = session_id
        self._current: dict[str, Any] | None = None
        self._projection: dict[str, Any] | None = None
        self._active_place: dict[str, Any] | None = None
        self._active_device_surface: str = "unknown"
        self._co_presence_summary: list[dict[str, Any]] = []
        self._mentioned_places_this_turn: list[dict[str, Any]] = []
        self._freshness: str = "unavailable"
        self._redactions: list[str] = []
        self._last_turn_id: str | None = None
        self._last_updated_ms = int(time.time() * 1000)
        self._extra: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self.SECTION_NAME

    @property
    def tier(self) -> str:
        return self.TIER

    @property
    def budget_bytes(self) -> int:
        return self.BUDGET_BYTES

    @property
    def can_evict(self) -> bool:
        return self.CAN_EVICT

    def replace(self, payload: dict[str, Any]) -> None:
        self.set_data(payload)

    def set_payload(self, payload: dict[str, Any]) -> None:
        self.set_data(payload)

    def update(self, payload: dict[str, Any]) -> None:
        merged = self.to_dict()
        merged.update(dict(payload or {}))
        self.set_data(merged)

    def set_current(self, current: dict[str, Any] | None) -> None:
        self._current = deepcopy(current) if current is not None else None
        self._derive_from_current()
        self._touch()

    def get_current(self) -> dict[str, Any] | None:
        return deepcopy(self._current)

    def set_projection(self, projection: dict[str, Any] | None) -> None:
        self._projection = deepcopy(projection) if projection is not None else None
        if self._projection is not None:
            self._freshness = str(self._projection.get("freshness") or self._freshness)
            self._redactions = [str(item) for item in self._projection.get("redactions", [])]
        self._touch()

    def get_projection(self) -> dict[str, Any] | None:
        return deepcopy(self._projection)

    def clear_for_new_turn(self) -> None:
        self._mentioned_places_this_turn = []
        self._last_turn_id = None
        self._touch()

    def clear(self) -> None:
        self._current = None
        self._projection = None
        self._active_place = None
        self._active_device_surface = "unknown"
        self._co_presence_summary = []
        self._mentioned_places_this_turn = []
        self._freshness = "unavailable"
        self._redactions = []
        self._last_turn_id = None
        self._extra = {}
        self._touch()

    def set_data(self, data: dict[str, Any]) -> None:
        payload = dict(data or {})
        self._session_id = str(payload.get("session_id") or self._session_id or "")
        self._current = deepcopy(payload.get("current")) if payload.get("current") else None
        self._projection = (
            deepcopy(payload.get("projection")) if payload.get("projection") else None
        )
        self._active_place = (
            deepcopy(payload.get("active_place")) if payload.get("active_place") else None
        )
        self._active_device_surface = str(payload.get("active_device_surface") or "unknown")
        self._co_presence_summary = deepcopy(payload.get("co_presence_summary") or [])
        self._mentioned_places_this_turn = deepcopy(payload.get("mentioned_places_this_turn") or [])
        self._freshness = str(payload.get("freshness") or "unavailable")
        self._redactions = [str(item) for item in payload.get("redactions", [])]
        turn_id = payload.get("last_turn_id", payload.get("turn_id"))
        self._last_turn_id = str(turn_id) if turn_id else None
        self._derive_from_current()
        self._derive_from_projection()
        known = {
            "session_id",
            "current",
            "projection",
            "active_place",
            "active_device_surface",
            "co_presence_summary",
            "mentioned_places_this_turn",
            "freshness",
            "redactions",
            "turn_id",
            "last_turn_id",
        }
        self._extra = deepcopy({key: value for key, value in payload.items() if key not in known})
        self._touch()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "session_id": self._session_id,
            "turn_id": self._last_turn_id,
            "last_turn_id": self._last_turn_id,
            "current": deepcopy(self._current),
            "projection": deepcopy(self._projection),
            "active_place": deepcopy(self._active_place),
            "active_device_surface": self._active_device_surface,
            "co_presence_summary": deepcopy(self._co_presence_summary),
            "mentioned_places_this_turn": deepcopy(self._mentioned_places_this_turn),
            "freshness": self._freshness,
            "redactions": list(self._redactions),
        }
        data.update(deepcopy(self._extra))
        return data

    def get_data(self) -> dict[str, Any]:
        return self.to_dict()

    def get_payload(self) -> dict[str, Any]:
        return self.to_dict()

    def get_metadata(self) -> dict[str, Any]:
        return {
            "name": self.SECTION_NAME,
            "tier": self.TIER,
            "size_bytes": self.get_size_bytes(),
            "budget_bytes": self.BUDGET_BYTES,
            "last_updated_ms": self._last_updated_ms,
            "has_context": self._current is not None,
            "has_projection": self._projection is not None,
            "freshness": self._freshness,
            "redaction_count": len(self._redactions),
        }

    def get_size_bytes(self) -> int:
        return len(json.dumps(self.to_dict(), separators=(",", ":"), default=str).encode("utf-8"))

    def to_flatbuffer(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":"), default=str).encode("utf-8")

    def from_flatbuffer(self, data: bytes) -> None:
        if not data:
            self.set_data({})
            return
        payload = json.loads(data.decode("utf-8"))
        self.set_data(payload if isinstance(payload, dict) else {})

    def _derive_from_current(self) -> None:
        current = self._current or {}
        active_place = current.get("active_place")
        if isinstance(active_place, dict):
            self._active_place = deepcopy(active_place)
        surface = current.get("active_device_surface")
        if isinstance(surface, dict):
            self._active_device_surface = str(surface.get("surface_kind") or "unknown")
        elif surface:
            self._active_device_surface = str(surface)
        co_presence = current.get("co_presence")
        if isinstance(co_presence, list):
            self._co_presence_summary = deepcopy(co_presence)
        mentioned = current.get("mentioned_places")
        if isinstance(mentioned, list):
            self._mentioned_places_this_turn = deepcopy(mentioned)
        if current.get("freshness"):
            self._freshness = str(current.get("freshness"))
        redactions = current.get("redactions")
        if isinstance(redactions, list):
            self._redactions = [str(item) for item in redactions]

    def _derive_from_projection(self) -> None:
        projection = self._projection or {}
        if projection.get("active_device_surface"):
            self._active_device_surface = str(projection.get("active_device_surface"))
        if projection.get("freshness"):
            self._freshness = str(projection.get("freshness"))
        redactions = projection.get("redactions")
        if isinstance(redactions, list):
            self._redactions = [str(item) for item in redactions]

    def _touch(self) -> None:
        self._last_updated_ms = int(time.time() * 1000)


__all__ = ["SpatialSection"]
