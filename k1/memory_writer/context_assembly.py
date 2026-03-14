"""
Context Assembly -- Temporal/Spatial Resolution (GAP-002 Epic 1.3)

Payload-first, SessionState-fallback pattern for temporal and spatial context.

Race condition T7: Concierge calls beliefs_active.start_new_turn() which clears
_mentioned_time and _mentioned_location BEFORE MW Stage 2 may have read them.
By snapshotting these into TurnCompletePayload (Epic 1.1) and reading from payload
first (this module), the race is eliminated.

Priority order:
  1. TurnCompletePayload fields (race-free -- snapshotted before start_new_turn)
  2. SessionState beliefs_active snapshot (fallback for pre-Epic-1.1 payloads)

Import graph:
  - k1.memory_writer.context_assembly -> k1.memory_writer.events (TurnCompletePayload)
  - k1.memory_writer.context_assembly -> typing (stdlib)
  - NEVER imports from k1.sessionstate (loose coupling via dict snapshot)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from k1.memory_writer.events import TurnCompletePayload


@dataclass
class _EntityProxy:
    """Lightweight proxy so PlaceResolver can use getattr() on dict entities."""

    type: str
    display_name: str
    confidence: float


def resolve_place_id(
    location_raw: str,
    beliefs_snapshot: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve a raw location string to a stable place_id.

    Uses PlaceResolver with LOCATION entities from beliefs_active snapshot.
    Returns None if no matching entity found or location_raw is empty.

    Args:
        location_raw: Raw location text (e.g. "Olive Garden").
        beliefs_snapshot: beliefs_active section as dict with 'mentioned_entities' list.

    Returns:
        place_id string (e.g. "place_olive_garden") or None.
    """
    if not location_raw or not location_raw.strip():
        return None

    from k1.memory_writer.place_resolver import PlaceResolver

    entities: list = []
    if beliefs_snapshot:
        raw_entities = beliefs_snapshot.get("mentioned_entities", [])
        for e in raw_entities:
            if isinstance(e, dict):
                entities.append(
                    _EntityProxy(
                        type=e.get("type", ""),
                        display_name=e.get("display_name", ""),
                        confidence=float(e.get("confidence", 1.0)),
                    )
                )
            else:
                entities.append(e)

    resolver = PlaceResolver(entities)
    return resolver.resolve(location_raw)


def resolve_mentioned_time(
    payload: TurnCompletePayload,
    beliefs_snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int, float, bool]:
    """
    Resolve temporal context: payload first, SessionState fallback.

    Args:
        payload: TurnCompletePayload with snapshotted temporal fields.
        beliefs_snapshot: Optional beliefs_active section as dict (from ISessionReadPort).
            Expected keys: mentioned_time.raw_text, mentioned_time.resolved_ms,
            mentioned_time.confidence, mentioned_time.is_relative.

    Returns:
        (raw_text, resolved_ms, confidence, is_relative)
        All empty/zero if no temporal context available.
    """
    # Priority 1: Payload (race-free)
    if payload.mentioned_time_raw:
        return (
            payload.mentioned_time_raw,
            payload.mentioned_time_resolved_ms,
            payload.mentioned_time_confidence,
            payload.mentioned_time_is_relative,
        )

    # Priority 2: SessionState beliefs_active snapshot (fallback)
    if beliefs_snapshot:
        mt = beliefs_snapshot.get("mentioned_time")
        if mt and isinstance(mt, dict) and mt.get("raw_text"):
            return (
                mt["raw_text"],
                int(mt.get("resolved_ms", 0)),
                float(mt.get("confidence", 0.0)),
                bool(mt.get("is_relative", True)),
            )

    # No temporal context
    return ("", 0, 0.0, True)


def resolve_mentioned_location(
    payload: TurnCompletePayload,
    beliefs_snapshot: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str, float]:
    """
    Resolve spatial context: payload first, SessionState fallback.

    Args:
        payload: TurnCompletePayload with snapshotted spatial fields.
        beliefs_snapshot: Optional beliefs_active section as dict (from ISessionReadPort).
            Expected keys: mentioned_location.raw_text, mentioned_location.location_type,
            mentioned_location.entity_id, mentioned_location.confidence.

    Returns:
        (raw_text, location_type, entity_id, confidence)
        All empty/zero if no spatial context available.
    """
    # Priority 1: Payload (race-free)
    if payload.mentioned_location_raw:
        return (
            payload.mentioned_location_raw,
            payload.mentioned_location_type,
            payload.mentioned_location_entity_id,
            payload.mentioned_location_confidence,
        )

    # Priority 2: SessionState beliefs_active snapshot (fallback)
    if beliefs_snapshot:
        ml = beliefs_snapshot.get("mentioned_location")
        if ml and isinstance(ml, dict) and ml.get("raw_text"):
            return (
                ml["raw_text"],
                ml.get("location_type", ""),
                ml.get("entity_id", ""),
                float(ml.get("confidence", 0.0)),
            )

    # No spatial context
    return ("", "", "", 0.0)


def assemble_temporal_spatial(
    payload: TurnCompletePayload,
    beliefs_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assemble all temporal/spatial fields for ExtractionContext construction.

    Returns a dict matching ExtractionContext field names (Epic 1.3 + 3.1),
    ready to be unpacked into ExtractionContext(**temporal_spatial_fields).

    Args:
        payload: TurnCompletePayload with snapshotted temporal/spatial fields.
        beliefs_snapshot: Optional beliefs_active section as dict.

    Returns:
        Dict with 10 keys matching ExtractionContext temporal/spatial fields.
    """
    raw, resolved_ms, confidence, is_relative = resolve_mentioned_time(payload, beliefs_snapshot)
    loc_raw, loc_type, loc_entity_id, loc_confidence = resolve_mentioned_location(
        payload, beliefs_snapshot
    )

    # Epic 3.1: Resolve stable place_id from location name + entities
    place_id = resolve_place_id(loc_raw, beliefs_snapshot)

    return {
        # Epic 1.1 (M1-TIME-01): Gold-standard conversation timestamp propagation
        "turn_timestamp_ms": payload.timestamp_ms,
        "mentioned_time_raw": raw,
        "mentioned_time_resolved_ms": resolved_ms,
        "mentioned_time_confidence": confidence,
        "mentioned_time_is_relative": is_relative,
        "mentioned_location_raw": loc_raw,
        "mentioned_location_type": loc_type,
        "mentioned_location_entity_id": loc_entity_id,
        "mentioned_location_confidence": loc_confidence,
        "place_id": place_id,
    }
