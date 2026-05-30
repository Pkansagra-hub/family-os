"""Explicit serialization helpers for spatial payload dataclasses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from k1.grounding.serialization import device_context_to_dict, dict_to_device_context
from k1.spatial.types import (
    DeviceSurface,
    Geofence,
    LocationFix,
    PlaceCandidate,
    PlaceRef,
    PresenceRef,
    SpatialContext,
    SpatialProjection,
    SpatialRedaction,
    SpatialTurnSnapshot,
)


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload)


def device_surface_to_dict(surface: DeviceSurface) -> dict[str, Any]:
    return _plain(surface)


def dict_to_device_surface(payload: Mapping[str, Any]) -> DeviceSurface:
    data = _dict(payload)
    data["capabilities"] = tuple(data.get("capabilities", ()))
    return DeviceSurface(**data)


def location_fix_to_dict(fix: LocationFix) -> dict[str, Any]:
    return _plain(fix)


def dict_to_location_fix(payload: Mapping[str, Any]) -> LocationFix:
    data = _dict(payload)
    data["redactions"] = tuple(data.get("redactions", ()))
    return LocationFix(**data)


def place_ref_to_dict(place: PlaceRef) -> dict[str, Any]:
    return _plain(place)


def dict_to_place_ref(payload: Mapping[str, Any]) -> PlaceRef:
    data = _dict(payload)
    data["aliases"] = tuple(data.get("aliases", ()))
    data["geofence_ids"] = tuple(data.get("geofence_ids", ()))
    return PlaceRef(**data)


def geofence_to_dict(geofence: Geofence) -> dict[str, Any]:
    return _plain(geofence)


def dict_to_geofence(payload: Mapping[str, Any]) -> Geofence:
    return Geofence(**_dict(payload))


def place_candidate_to_dict(candidate: PlaceCandidate) -> dict[str, Any]:
    return _plain(candidate)


def dict_to_place_candidate(payload: Mapping[str, Any]) -> PlaceCandidate:
    return PlaceCandidate(**_dict(payload))


def presence_ref_to_dict(presence: PresenceRef) -> dict[str, Any]:
    return _plain(presence)


def dict_to_presence_ref(payload: Mapping[str, Any]) -> PresenceRef:
    data = _dict(payload)
    if data.get("place_ref") is not None:
        data["place_ref"] = dict_to_place_ref(data["place_ref"])
    return PresenceRef(**data)


def redaction_to_dict(redaction: SpatialRedaction) -> dict[str, Any]:
    return _plain(redaction)


def dict_to_redaction(payload: Mapping[str, Any]) -> SpatialRedaction:
    return SpatialRedaction(**_dict(payload))


def spatial_context_to_dict(context: SpatialContext) -> dict[str, Any]:
    data = _plain(context)
    if context.device_context is not None:
        data["device_context"] = device_context_to_dict(context.device_context)
    return data


def dict_to_spatial_context(payload: Mapping[str, Any]) -> SpatialContext:
    data = _dict(payload)
    if data.get("active_place") is not None:
        data["active_place"] = dict_to_place_ref(data["active_place"])
    if data.get("active_device_surface") is not None:
        data["active_device_surface"] = dict_to_device_surface(data["active_device_surface"])
    if data.get("location_fix") is not None:
        data["location_fix"] = dict_to_location_fix(data["location_fix"])
    if data.get("device_context") is not None:
        data["device_context"] = dict_to_device_context(data["device_context"])
    data["co_presence"] = tuple(dict_to_presence_ref(item) for item in data.get("co_presence", ()))
    data["redactions"] = tuple(data.get("redactions", ()))
    data["place_refs"] = tuple(dict_to_place_ref(item) for item in data.get("place_refs", ()))
    data["mentioned_places"] = tuple(
        dict_to_place_ref(item) for item in data.get("mentioned_places", ())
    )
    data["provenance"] = tuple(data.get("provenance", ()))
    return SpatialContext(**data)


def spatial_projection_to_dict(projection: SpatialProjection) -> dict[str, Any]:
    return _plain(projection)


def dict_to_spatial_projection(payload: Mapping[str, Any]) -> SpatialProjection:
    data = _dict(payload)
    data["place_refs"] = tuple(dict_to_place_ref(item) for item in data.get("place_refs", ()))
    data["co_presence"] = tuple(dict_to_presence_ref(item) for item in data.get("co_presence", ()))
    data["redactions"] = tuple(data.get("redactions", ()))
    data["relevant_place_refs"] = tuple(
        dict_to_place_ref(item) for item in data.get("relevant_place_refs", ())
    )
    data["provenance"] = tuple(data.get("provenance", ()))
    if data.get("raw_location") is not None:
        data["raw_location"] = dict_to_location_fix(data["raw_location"])
    return SpatialProjection(**data)


def turn_snapshot_to_dict(snapshot: SpatialTurnSnapshot) -> dict[str, Any]:
    return _plain(snapshot)


def dict_to_turn_snapshot(payload: Mapping[str, Any]) -> SpatialTurnSnapshot:
    data = _dict(payload)
    data["context"] = dict_to_spatial_context(data["context"])
    data["projection"] = dict_to_spatial_projection(data["projection"])
    return SpatialTurnSnapshot(**data)


__all__ = [
    "device_surface_to_dict",
    "dict_to_device_surface",
    "dict_to_geofence",
    "dict_to_location_fix",
    "dict_to_place_candidate",
    "dict_to_place_ref",
    "dict_to_presence_ref",
    "dict_to_redaction",
    "dict_to_spatial_context",
    "dict_to_spatial_projection",
    "dict_to_turn_snapshot",
    "geofence_to_dict",
    "location_fix_to_dict",
    "place_candidate_to_dict",
    "place_ref_to_dict",
    "presence_ref_to_dict",
    "redaction_to_dict",
    "spatial_context_to_dict",
    "spatial_projection_to_dict",
    "turn_snapshot_to_dict",
]
