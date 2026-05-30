"""Explicit serialization helpers for grounding payload dataclasses."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from k1.grounding.types import (
    AgentGroundingLease,
    ConsumerScope,
    DeviceContextSnapshot,
    GroundingEnvelope,
    GroundingFreshness,
    GroundingProjection,
    GroundingSource,
)
from k1.spatial.types import (
    DeviceSurface,
    LocationFix,
    PlaceRef,
    PresenceRef,
    SpatialContext,
    SpatialProjection,
    SpatialTurnSnapshot,
)
from k1.temporal.serialization import dict_to_projection as dict_to_temporal_projection
from k1.temporal.serialization import projection_to_dict as temporal_projection_to_dict


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


def device_context_to_dict(snapshot: DeviceContextSnapshot) -> dict[str, Any]:
    return _plain(snapshot)


def dict_to_device_context(payload: Mapping[str, Any]) -> DeviceContextSnapshot:
    return DeviceContextSnapshot(**_dict(payload))


def freshness_to_dict(freshness: GroundingFreshness) -> dict[str, Any]:
    return _plain(freshness)


def dict_to_freshness(payload: Mapping[str, Any]) -> GroundingFreshness:
    return GroundingFreshness(**_dict(payload))


def source_to_dict(source: GroundingSource) -> dict[str, Any]:
    return _plain(source)


def dict_to_source(payload: Mapping[str, Any]) -> GroundingSource:
    return GroundingSource(**_dict(payload))


def scope_to_dict(scope: ConsumerScope) -> dict[str, Any]:
    return _plain(scope)


def dict_to_scope(payload: Mapping[str, Any]) -> ConsumerScope:
    data = _dict(payload)
    for key in ("allowed_context_sections", "denied_context_sections"):
        data[key] = tuple(data.get(key, ()))
    return ConsumerScope(**data)


def place_ref_to_dict(place: PlaceRef) -> dict[str, Any]:
    return _plain(place)


def dict_to_place_ref(payload: Mapping[str, Any]) -> PlaceRef:
    data = _dict(payload)
    data["aliases"] = tuple(data.get("aliases", ()))
    data["geofence_ids"] = tuple(data.get("geofence_ids", ()))
    return PlaceRef(**data)


def device_surface_to_dict(surface: DeviceSurface) -> dict[str, Any]:
    return _plain(surface)


def dict_to_device_surface(payload: Mapping[str, Any]) -> DeviceSurface:
    data = _dict(payload)
    data["capabilities"] = tuple(data.get("capabilities", ()))
    return DeviceSurface(**data)


def dict_to_location_fix(payload: Mapping[str, Any]) -> LocationFix:
    data = _dict(payload)
    data["redactions"] = tuple(data.get("redactions", ()))
    return LocationFix(**data)


def presence_ref_to_dict(presence: PresenceRef) -> dict[str, Any]:
    return _plain(presence)


def dict_to_presence_ref(payload: Mapping[str, Any]) -> PresenceRef:
    data = _dict(payload)
    if data.get("place_ref") is not None:
        data["place_ref"] = dict_to_place_ref(data["place_ref"])
    return PresenceRef(**data)


def spatial_context_to_dict(context: SpatialContext) -> dict[str, Any]:
    return _plain(context)


def dict_to_spatial_context(payload: Mapping[str, Any]) -> SpatialContext:
    data = _dict(payload)
    if data.get("active_place") is not None:
        data["active_place"] = dict_to_place_ref(data["active_place"])
    if data.get("active_device_surface") is not None:
        data["active_device_surface"] = dict_to_device_surface(data["active_device_surface"])
    if data.get("location_fix") is not None:
        data["location_fix"] = dict_to_location_fix(data["location_fix"])
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


def spatial_turn_snapshot_to_dict(snapshot: SpatialTurnSnapshot) -> dict[str, Any]:
    return _plain(snapshot)


def envelope_to_dict(envelope: GroundingEnvelope) -> dict[str, Any]:
    return {
        "envelope_id": envelope.envelope_id,
        "session_id": envelope.session_id,
        "turn_id": envelope.turn_id,
        "trace_id": envelope.trace_id,
        "created_at_utc": envelope.created_at_utc,
        "consumer": envelope.consumer,
        "identity_ref": envelope.identity_ref,
        "temporal": temporal_projection_to_dict(envelope.temporal),
        "spatial": spatial_projection_to_dict(envelope.spatial),
        "group_refs": list(envelope.group_refs),
        "device_surface": envelope.device_surface,
        "policy_scope": envelope.policy_scope,
        "freshness": freshness_to_dict(envelope.freshness),
        "provenance": [source_to_dict(item) for item in envelope.provenance],
        "redactions": list(envelope.redactions),
        "metadata": dict(envelope.metadata),
    }


def dict_to_envelope(payload: Mapping[str, Any]) -> GroundingEnvelope:
    data = _dict(payload)
    data["temporal"] = dict_to_temporal_projection(data["temporal"])
    data["spatial"] = dict_to_spatial_projection(data["spatial"])
    data["freshness"] = dict_to_freshness(data["freshness"])
    data["provenance"] = tuple(dict_to_source(item) for item in data.get("provenance", ()))
    data["group_refs"] = tuple(data.get("group_refs", ()))
    data["redactions"] = tuple(data.get("redactions", ()))
    return GroundingEnvelope(**data)


def projection_to_dict(projection: GroundingProjection) -> dict[str, Any]:
    return {
        "projection_id": projection.projection_id,
        "envelope_id": projection.envelope_id,
        "consumer": projection.consumer,
        "temporal": temporal_projection_to_dict(projection.temporal),
        "spatial": spatial_projection_to_dict(projection.spatial),
        "freshness": freshness_to_dict(projection.freshness),
        "redactions": list(projection.redactions),
        "metadata": dict(projection.metadata),
    }


def dict_to_projection(payload: Mapping[str, Any]) -> GroundingProjection:
    data = _dict(payload)
    data["temporal"] = dict_to_temporal_projection(data["temporal"])
    data["spatial"] = dict_to_spatial_projection(data["spatial"])
    data["freshness"] = dict_to_freshness(data["freshness"])
    data["redactions"] = tuple(data.get("redactions", ()))
    return GroundingProjection(**data)


def lease_to_dict(lease: AgentGroundingLease) -> dict[str, Any]:
    return {
        "lease_id": lease.lease_id,
        "envelope_id": lease.envelope_id,
        "issued_at_utc": lease.issued_at_utc,
        "expires_at_utc": lease.expires_at_utc,
        "temporal": temporal_projection_to_dict(lease.temporal),
        "spatial": spatial_projection_to_dict(lease.spatial),
        "subject_ref": lease.subject_ref,
        "group_refs": list(lease.group_refs),
        "role_refs": list(lease.role_refs),
        "task_scope": lease.task_scope,
        "privacy_scope": lease.privacy_scope,
        "allowed_context_sections": list(lease.allowed_context_sections),
        "denied_context_sections": list(lease.denied_context_sections),
        "redactions": list(lease.redactions),
        "refresh_allowed": lease.refresh_allowed,
        "status": lease.status,
        "metadata": dict(lease.metadata),
    }


def dict_to_lease(payload: Mapping[str, Any]) -> AgentGroundingLease:
    data = _dict(payload)
    data["temporal"] = dict_to_temporal_projection(data["temporal"])
    data["spatial"] = dict_to_spatial_projection(data["spatial"])
    for key in (
        "group_refs",
        "role_refs",
        "allowed_context_sections",
        "denied_context_sections",
        "redactions",
    ):
        data[key] = tuple(data.get(key, ()))
    return AgentGroundingLease(**data)


__all__ = [
    "device_context_to_dict",
    "dict_to_device_context",
    "dict_to_envelope",
    "dict_to_freshness",
    "dict_to_lease",
    "dict_to_projection",
    "dict_to_scope",
    "dict_to_source",
    "dict_to_spatial_projection",
    "envelope_to_dict",
    "freshness_to_dict",
    "lease_to_dict",
    "projection_to_dict",
    "scope_to_dict",
    "source_to_dict",
    "spatial_projection_to_dict",
]
