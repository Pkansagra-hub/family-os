"""Build structured place candidates from typed runtime evidence."""

from __future__ import annotations

from typing import Any, Mapping

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.service.place_alias_catalog import normalize_place_label
from k1.spatial.types import PlaceCandidate


def candidates_from_device_context(snapshot: DeviceContextSnapshot) -> tuple[PlaceCandidate, ...]:
    """Extract semantic place hints from a device context snapshot."""
    hint = normalize_place_label(snapshot.semantic_place_hint)
    if not hint:
        return ()
    return (
        PlaceCandidate(
            raw_text=str(snapshot.semantic_place_hint),
            normalized_text=hint,
            source="device_hint",
            confidence=0.72,
            metadata={"device_id": snapshot.device_id, "installation_id": snapshot.installation_id},
        ),
    )


def candidates_from_mapping(payload: Mapping[str, Any]) -> tuple[PlaceCandidate, ...]:
    """Extract structured place candidates from task params/reference context."""
    candidates: list[PlaceCandidate] = []
    for key in ("place", "place_hint", "semantic_place", "location", "destination"):
        value = payload.get(key)
        normalized = normalize_place_label(value)
        if normalized:
            candidates.append(
                PlaceCandidate(
                    raw_text=str(value),
                    normalized_text=normalized,
                    source="task_param",
                    confidence=0.65,
                    metadata={"field": key},
                )
            )
    return tuple(candidates)


def candidates_from_beliefs_active(section: Any) -> tuple[PlaceCandidate, ...]:
    """Extract low-confidence place evidence from beliefs_active.mentioned_location."""
    mentioned = None
    getter = getattr(section, "get_mentioned_location", None)
    if callable(getter):
        mentioned = getter()
    if mentioned is None:
        mentioned = getattr(section, "_mentioned_location", None)
    if mentioned is None:
        return ()

    raw_text = _get_mentioned_value(mentioned, "raw_text")
    normalized = normalize_place_label(raw_text)
    if not normalized:
        return ()
    confidence = _bounded_confidence(_get_mentioned_value(mentioned, "confidence"), cap=0.45)
    location_type = _get_mentioned_value(mentioned, "location_type")
    entity_id = _get_mentioned_value(mentioned, "entity_id")
    return (
        PlaceCandidate(
            raw_text=str(raw_text),
            normalized_text=normalized,
            source="conversation_mention",
            confidence=confidence,
            metadata={
                "section": "beliefs_active",
                "location_type": str(location_type or ""),
                "entity_id": str(entity_id or ""),
                "authoritative_current_place": False,
            },
        ),
    )


def candidates_from_session_state(ss: Any) -> tuple[PlaceCandidate, ...]:
    """Read beliefs_active and return conversation-mentioned place candidates."""
    getter = getattr(ss, "get_section", None)
    if not callable(getter):
        return ()
    try:
        section = getter("beliefs_active")
    except Exception:
        return ()
    if section is None:
        return ()
    return candidates_from_beliefs_active(section)


def _get_mentioned_value(mentioned: Any, name: str) -> Any:
    if isinstance(mentioned, Mapping):
        return mentioned.get(name)
    return getattr(mentioned, name, None)


def _bounded_confidence(value: Any, *, cap: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = cap
    confidence = max(0.0, min(confidence, 1.0))
    return min(confidence, cap)


__all__ = [
    "candidates_from_beliefs_active",
    "candidates_from_device_context",
    "candidates_from_mapping",
    "candidates_from_session_state",
]
