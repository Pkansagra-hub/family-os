"""TemporalSection -- HOT temporal anchor and window state."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any


class TemporalSection:
    """Canonical HOT SessionState section for k1.temporal."""

    BUDGET_BYTES: int = 4 * 1024
    TIER: str = "hot"
    CAN_EVICT: bool = False
    SECTION_NAME: str = "temporal"

    __slots__ = (
        "_anchor",
        "_windows",
        "_resolved_expressions",
        "_last_turn_id",
        "_stale_after_ms",
        "_provenance",
        "_session_id",
        "_last_updated_ms",
        "_extra",
    )

    def __init__(self, session_id: str = "", stale_after_ms: int = 120_000) -> None:
        self._session_id = session_id
        self._anchor: dict[str, Any] | None = None
        self._windows: dict[str, dict[str, Any]] = {}
        self._resolved_expressions: list[dict[str, Any]] = []
        self._last_turn_id: str | None = None
        self._stale_after_ms = stale_after_ms
        self._provenance: list[dict[str, Any]] = []
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

    def set_anchor(self, anchor_dict: dict[str, Any] | None) -> None:
        self._anchor = deepcopy(anchor_dict) if anchor_dict is not None else None
        self._touch()

    def get_anchor(self) -> dict[str, Any] | None:
        return deepcopy(self._anchor)

    def set_windows(self, windows_dict: dict[str, dict[str, Any]] | None) -> None:
        self._windows = deepcopy(windows_dict) if windows_dict else {}
        self._touch()

    def get_windows(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._windows)

    def set_resolutions(self, resolutions: list[dict[str, Any]] | None) -> None:
        self._resolved_expressions = deepcopy(resolutions) if resolutions else []
        self._touch()

    def get_resolutions(self) -> list[dict[str, Any]]:
        return deepcopy(self._resolved_expressions)

    def clear_for_new_turn(self) -> None:
        self._resolved_expressions = []
        self._provenance = []
        self._last_turn_id = None
        self._touch()

    def clear(self) -> None:
        self._anchor = None
        self._windows = {}
        self._resolved_expressions = []
        self._provenance = []
        self._last_turn_id = None
        self._extra = {}
        self._touch()

    def set_data(self, data: dict[str, Any]) -> None:
        payload = dict(data or {})
        self._session_id = str(payload.get("session_id") or self._session_id or "")
        self._anchor = deepcopy(payload.get("anchor")) if payload.get("anchor") else None
        self._windows = deepcopy(payload.get("windows")) if payload.get("windows") else {}
        self._resolved_expressions = (
            deepcopy(payload.get("resolved_expressions"))
            if payload.get("resolved_expressions")
            else []
        )
        turn_id = payload.get("last_turn_id", payload.get("turn_id"))
        self._last_turn_id = str(turn_id) if turn_id else None
        stale = payload.get("stale_after_ms", self._stale_after_ms)
        try:
            self._stale_after_ms = int(stale)
        except (TypeError, ValueError):
            pass
        self._provenance = deepcopy(payload.get("provenance")) if payload.get("provenance") else []
        known = {
            "session_id",
            "anchor",
            "windows",
            "resolved_expressions",
            "turn_id",
            "last_turn_id",
            "stale_after_ms",
            "provenance",
        }
        self._extra = deepcopy({key: value for key, value in payload.items() if key not in known})
        self._touch()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "session_id": self._session_id,
            "turn_id": self._last_turn_id,
            "last_turn_id": self._last_turn_id,
            "anchor": deepcopy(self._anchor),
            "windows": deepcopy(self._windows),
            "resolved_expressions": deepcopy(self._resolved_expressions),
            "stale_after_ms": self._stale_after_ms,
            "provenance": deepcopy(self._provenance),
        }
        data.update(deepcopy(self._extra))
        return data

    def get_data(self) -> dict[str, Any]:
        return self.to_dict()

    def get_metadata(self) -> dict[str, Any]:
        return {
            "name": self.SECTION_NAME,
            "tier": self.TIER,
            "size_bytes": self.get_size_bytes(),
            "budget_bytes": self.BUDGET_BYTES,
            "last_updated_ms": self._last_updated_ms,
            "has_anchor": self._anchor is not None,
            "window_count": len(self._windows),
            "resolution_count": len(self._resolved_expressions),
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

    def _touch(self) -> None:
        self._last_updated_ms = int(time.time() * 1000)


__all__ = ["TemporalSection"]
