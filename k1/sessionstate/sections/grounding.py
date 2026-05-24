"""GroundingSection -- HOT grounding envelope/projection metadata."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any


class GroundingSection:
    """Lightweight HOT section for grounding metadata.

    This section stores only stable identifiers and redaction summaries. It
    intentionally does not persist raw spatial payloads or full grounding
    projections.
    """

    BUDGET_BYTES: int = 2 * 1024
    TIER: str = "hot"
    CAN_EVICT: bool = False
    SECTION_NAME: str = "grounding"

    __slots__ = (
        "_session_id",
        "_latest_envelope_id",
        "_latest_projection_ids",
        "_source_temporal_section_version",
        "_source_spatial_section_version",
        "_redaction_summary",
        "_last_updated_ms",
        "_extra",
    )

    def __init__(self, session_id: str = "") -> None:
        self._session_id = session_id
        self._latest_envelope_id: str | None = None
        self._latest_projection_ids: dict[str, str] = {}
        self._source_temporal_section_version: str | None = None
        self._source_spatial_section_version: str | None = None
        self._redaction_summary: list[str] = []
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

    def set_envelope_metadata(
        self,
        *,
        latest_envelope_id: str | None = None,
        latest_projection_ids: dict[str, str] | None = None,
        source_temporal_section_version: str | None = None,
        source_spatial_section_version: str | None = None,
        redaction_summary: list[str] | tuple[str, ...] | None = None,
        session_id: str | None = None,
    ) -> None:
        if session_id is not None:
            self._session_id = str(session_id)
        self._latest_envelope_id = latest_envelope_id
        self._latest_projection_ids = {
            str(key): str(value)
            for key, value in (latest_projection_ids or {}).items()
            if key and value
        }
        self._source_temporal_section_version = source_temporal_section_version
        self._source_spatial_section_version = source_spatial_section_version
        self._redaction_summary = [str(item) for item in (redaction_summary or []) if item]
        self._touch()

    def get_envelope_metadata(self) -> dict[str, Any]:
        return {
            "session_id": self._session_id,
            "latest_envelope_id": self._latest_envelope_id,
            "latest_projection_ids": deepcopy(self._latest_projection_ids),
            "source_temporal_section_version": self._source_temporal_section_version,
            "source_spatial_section_version": self._source_spatial_section_version,
            "redaction_summary": list(self._redaction_summary),
        }

    def clear_for_new_turn(self) -> None:
        self._latest_envelope_id = None
        self._latest_projection_ids = {}
        self._redaction_summary = []
        self._touch()

    def clear(self) -> None:
        self._latest_envelope_id = None
        self._latest_projection_ids = {}
        self._source_temporal_section_version = None
        self._source_spatial_section_version = None
        self._redaction_summary = []
        self._extra = {}
        self._touch()

    def set_data(self, data: dict[str, Any]) -> None:
        payload = dict(data or {})
        self._session_id = str(payload.get("session_id") or self._session_id or "")

        latest_envelope_id = payload.get("latest_envelope_id")
        latest_projection_ids = payload.get("latest_projection_ids")
        source_temporal = payload.get("source_temporal_section_version")
        source_spatial = payload.get("source_spatial_section_version")
        redactions = payload.get("redaction_summary")

        envelope = payload.get("last_envelope")
        if isinstance(envelope, dict):
            latest_envelope_id = latest_envelope_id or envelope.get("envelope_id")
            temporal = (
                envelope.get("temporal") if isinstance(envelope.get("temporal"), dict) else {}
            )
            spatial = envelope.get("spatial") if isinstance(envelope.get("spatial"), dict) else {}
            anchor = temporal.get("anchor") if isinstance(temporal.get("anchor"), dict) else {}
            source_temporal = source_temporal or anchor.get("anchor_id")
            source_spatial = source_spatial or spatial.get("context_id")
            redactions = _merge_redactions(redactions, envelope.get("redactions"))

        projection = payload.get("last_projection")
        if isinstance(projection, dict):
            consumer = str(projection.get("consumer") or "")
            projection_id = str(projection.get("projection_id") or "")
            if latest_projection_ids is None:
                latest_projection_ids = {}
            if consumer and projection_id and isinstance(latest_projection_ids, dict):
                latest_projection_ids = dict(latest_projection_ids)
                latest_projection_ids[consumer] = projection_id
            latest_envelope_id = latest_envelope_id or projection.get("envelope_id")
            redactions = _merge_redactions(redactions, projection.get("redactions"))

        self.set_envelope_metadata(
            latest_envelope_id=str(latest_envelope_id) if latest_envelope_id else None,
            latest_projection_ids=(
                {str(key): str(value) for key, value in latest_projection_ids.items()}
                if isinstance(latest_projection_ids, dict)
                else None
            ),
            source_temporal_section_version=(str(source_temporal) if source_temporal else None),
            source_spatial_section_version=(str(source_spatial) if source_spatial else None),
            redaction_summary=[str(item) for item in (redactions or []) if item],
            session_id=self._session_id,
        )
        known = {
            "session_id",
            "latest_envelope_id",
            "latest_projection_ids",
            "source_temporal_section_version",
            "source_spatial_section_version",
            "redaction_summary",
            "last_envelope",
            "last_projection",
            "last_lease",
        }
        self._extra = deepcopy({key: value for key, value in payload.items() if key not in known})

    def to_dict(self) -> dict[str, Any]:
        data = self.get_envelope_metadata()
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
            "has_envelope": self._latest_envelope_id is not None,
            "projection_count": len(self._latest_projection_ids),
            "redaction_count": len(self._redaction_summary),
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


def _merge_redactions(*values: Any) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        if value is None:
            continue
        items = [value] if isinstance(value, str) else value
        try:
            iterator = iter(items)
        except TypeError:
            continue
        for item in iterator:
            text = str(item)
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


__all__ = ["GroundingSection"]
