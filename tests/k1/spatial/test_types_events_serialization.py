"""M3-E1 spatial type, event, and serialization coverage."""

from __future__ import annotations

import dataclasses

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.events import (
    SPATIAL_CONTEXT_CREATED,
    SPATIAL_CONTEXT_REDACTED,
    SPATIAL_CONTEXT_REFRESHED,
    SPATIAL_LOCATION_UNAVAILABLE,
    SPATIAL_PLACE_RESOLVED,
    SpatialContextCreatedPayload,
)
from k1.spatial.serialization import (
    dict_to_spatial_context,
    dict_to_spatial_projection,
    spatial_context_to_dict,
    spatial_projection_to_dict,
)
from k1.spatial.types import (
    DeviceSurface,
    LocationFix,
    PlaceRef,
    SpatialContext,
    SpatialProjection,
    SpatialRedaction,
)


def test_spatial_types_are_frozen_and_reuse_device_context_snapshot() -> None:
    for cls in (
        DeviceSurface,
        LocationFix,
        PlaceRef,
        SpatialContext,
        SpatialProjection,
        SpatialRedaction,
    ):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True

    snapshot = DeviceContextSnapshot(
        session_id="s1",
        device_id="phone",
        installation_id="install",
        observed_at_utc="2026-05-23T01:00:00+00:00",
        surface="mobile",
    )
    context = _context(snapshot)
    assert context.device_context is snapshot


def test_spatial_events_match_whiteboard_topics() -> None:
    assert SPATIAL_CONTEXT_CREATED == "k1.spatial.context.created.v1"
    assert SPATIAL_CONTEXT_REFRESHED == "k1.spatial.context.refreshed.v1"
    assert SPATIAL_PLACE_RESOLVED == "k1.spatial.place.resolved.v1"
    assert SPATIAL_CONTEXT_REDACTED == "k1.spatial.context.redacted.v1"
    assert SPATIAL_LOCATION_UNAVAILABLE == "k1.spatial.location.unavailable.v1"

    payload = SpatialContextCreatedPayload(
        context_id="ctx1",
        session_id="s1",
        captured_at_utc="2026-05-23T01:00:00+00:00",
        semantic_place="home",
        precision="semantic",
        source="device",
    )
    assert dataclasses.asdict(payload)["semantic_place"] == "home"


def test_context_and_projection_roundtrip_preserve_nested_types() -> None:
    snapshot = DeviceContextSnapshot(
        session_id="s1",
        device_id="phone",
        installation_id="install",
        observed_at_utc="2026-05-23T01:00:00+00:00",
        surface="mobile",
        location_permission="granted",
    )
    context = _context(snapshot)
    assert dict_to_spatial_context(spatial_context_to_dict(context)) == context

    projection = SpatialProjection(
        projection_id="proj1",
        context_id=context.context_id,
        session_id="s1",
        consumer="front",
        semantic_place="home",
        precision="semantic",
        place_refs=(),
        active_device_surface="mobile",
        co_presence=(),
        freshness="live",
        redactions=("raw_location_denied",),
        relevant_place_refs=(context.active_place,),
    )
    assert dict_to_spatial_projection(spatial_projection_to_dict(projection)) == projection


def _context(snapshot: DeviceContextSnapshot) -> SpatialContext:
    place = PlaceRef(
        place_id="place_home",
        label="home",
        place_kind="home",
        confidence=0.9,
        source="registry",
        aliases=("house",),
    )
    return SpatialContext(
        context_id="ctx1",
        session_id="s1",
        captured_at_utc="2026-05-23T01:00:00+00:00",
        active_place=place,
        active_device_surface=DeviceSurface(
            surface_id="install",
            surface_kind="mobile",
            device_id="phone",
            installation_id="install",
        ),
        location_fix=LocationFix(
            latitude=33.2,
            longitude=-97.1,
            accuracy_m=30.0,
            captured_at_utc="2026-05-23T01:00:00+00:00",
            permission_state="granted",
            source="device",
            confidence=0.9,
        ),
        co_presence=(),
        freshness="live",
        redactions=(),
        location_permission="granted",
        precision="semantic",
        place_refs=(place,),
        device_context=snapshot,
    )
