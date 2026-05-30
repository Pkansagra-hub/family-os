"""PlaceRegistrySection: WARM spatial registry projection."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any


class PlaceRegistrySection:
    """WARM SessionState section for known places, aliases, and geofences."""

    BUDGET_BYTES: int = 8 * 1024
    TIER: str = "warm"
    CAN_EVICT: bool = True
    SECTION_NAME: str = "place_registry"

    __slots__ = (
        "_session_id",
        "_places",
        "_geofences",
        "_member_default_places",
        "_metadata",
        "_last_updated_ms",
        "_extra",
    )

    def __init__(self, session_id: str = "") -> None:
        self._session_id = session_id
        self._places: dict[str, dict[str, Any]] = {}
        self._geofences: dict[str, dict[str, Any]] = {}
        self._member_default_places: dict[str, list[str]] = {}
        self._metadata: dict[str, Any] = {}
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

    def set_registry(
        self,
        *,
        places: list[dict[str, Any]] | dict[str, dict[str, Any]] | None = None,
        geofences: list[dict[str, Any]] | dict[str, dict[str, Any]] | None = None,
        member_default_places: dict[str, list[str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._places = _index_by_id(places, "place_id")
        self._geofences = _index_by_id(geofences, "geofence_id")
        self._member_default_places = {
            str(key): [str(item) for item in value]
            for key, value in dict(member_default_places or {}).items()
        }
        self._metadata = deepcopy(metadata or {})
        self._touch()

    def get_places(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._places)

    def get_geofences(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._geofences)

    def get_member_default_places(self) -> dict[str, list[str]]:
        return deepcopy(self._member_default_places)

    def clear(self) -> None:
        self._places = {}
        self._geofences = {}
        self._member_default_places = {}
        self._metadata = {}
        self._extra = {}
        self._touch()

    def set_data(self, data: dict[str, Any]) -> None:
        payload = dict(data or {})
        self._session_id = str(payload.get("session_id") or self._session_id or "")
        self.set_registry(
            places=payload.get("places") or payload.get("household_places") or {},
            geofences=payload.get("geofences") or {},
            member_default_places=payload.get("member_default_places") or {},
            metadata=payload.get("metadata") or {},
        )
        known = {
            "session_id",
            "places",
            "household_places",
            "geofences",
            "member_default_places",
            "metadata",
        }
        self._extra = deepcopy({key: value for key, value in payload.items() if key not in known})

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "session_id": self._session_id,
            "places": deepcopy(self._places),
            "geofences": deepcopy(self._geofences),
            "member_default_places": deepcopy(self._member_default_places),
            "metadata": deepcopy(self._metadata),
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
            "place_count": len(self._places),
            "geofence_count": len(self._geofences),
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


def _index_by_id(
    value: list[dict[str, Any]] | dict[str, dict[str, Any]] | None,
    id_field: str,
) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        return {str(key): deepcopy(dict(item)) for key, item in value.items()}
    indexed: dict[str, dict[str, Any]] = {}
    for item in value or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get(id_field) or "")
        if key:
            indexed[key] = deepcopy(item)
    return indexed


__all__ = ["PlaceRegistrySection"]
