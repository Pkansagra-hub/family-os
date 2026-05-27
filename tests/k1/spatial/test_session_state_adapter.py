"""M3-E2/E3 spatial state adapter and service integration tests."""

from __future__ import annotations

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.adapters import (
    LocalPlaceRegistryAdapter,
    SpatialDeviceContextAdapter,
    SpatialEventBusAdapter,
    SpatialStateAdapter,
)
from k1.spatial.service import SpatialService
from k1.spatial.types import Geofence, PlaceRef


class _DeviceContextPort:
    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        return DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id,
            installation_id=installation_id,
            observed_at_utc="2026-05-23T01:00:00+00:00",
            surface="phone",
            location_permission="granted",
            location_fix={"latitude": 33.2, "longitude": -97.1, "accuracy_m": 20},
            semantic_place_hint="home",
        )


class _CoordinateOnlyDeviceContextPort:
    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        return DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id,
            installation_id=installation_id,
            observed_at_utc="2026-05-23T01:00:00+00:00",
            surface="web",
            location_permission="granted",
            location_fix={"latitude": 33.2148, "longitude": -97.1331, "accuracy_m": 42},
        )


class _SemanticOnlyDeviceContextPort:
    async def get_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        return DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id,
            installation_id=installation_id,
            observed_at_utc="2026-05-23T01:00:00+00:00",
            surface="web",
            timezone="America/Chicago",
            location_permission="hidden",
            semantic_place_hint="Denton, Texas",
        )


class _ReverseGeocoderPort:
    async def geocode(self, session_id: str, candidate):  # type: ignore[no-untyped-def]
        return ()

    async def reverse_geocode(self, session_id: str, fix):  # type: ignore[no-untyped-def]
        return (
            PlaceRef(
                place_id="geocoder:city:plano-texas",
                label="Plano, Texas",
                place_kind="city",
                confidence=0.82,
                source="geocoder",
                aliases=("Plano",),
                metadata={"provider": "test"},
            ),
        )


class _ReverseAddressGeocoderPort:
    async def geocode(self, session_id: str, candidate):  # type: ignore[no-untyped-def]
        return ()

    async def reverse_geocode(self, session_id: str, fix):  # type: ignore[no-untyped-def]
        return (
            PlaceRef(
                place_id="geocoder:address:123-example-ln-sampleton-testland",
                label="123 Example Ln, Sampleton, Testland",
                place_kind="address",
                confidence=0.88,
                source="geocoder",
                aliases=("123 Example Ln", "Sampleton, Testland"),
                metadata={"address_level": True, "locality_label": "Sampleton, Testland"},
            ),
        )


async def test_state_adapter_roundtrips_spatial_and_place_registry_payloads() -> None:
    adapter = SpatialStateAdapter()

    await adapter.write_spatial_section("s1", {"current": {"context_id": "ctx1"}})
    await adapter.write_place_registry_section("s1", {"places": [{"place_id": "home"}]})

    assert (await adapter.read_spatial_section("s1"))["current"]["context_id"] == "ctx1"
    assert (await adapter.read_place_registry_section("s1"))["places"][0]["place_id"] == "home"


async def test_spatial_service_refresh_writes_projection_without_prompt_raw_coordinates() -> None:
    state = SpatialStateAdapter()
    events = SpatialEventBusAdapter()
    registry = LocalPlaceRegistryAdapter(
        places=(
            PlaceRef(
                place_id="home",
                label="home",
                place_kind="home",
                confidence=0.95,
                source="registry",
                aliases=("house",),
            ),
        ),
        geofences=(
            Geofence(
                geofence_id="geo_home",
                place_id="home",
                shape="circle",
                parameters={"latitude": 33.2, "longitude": -97.1, "radius_m": 100},
                source="registry",
            ),
        ),
    )
    service = SpatialService(
        device_context_port=SpatialDeviceContextAdapter(_DeviceContextPort()),
        device_location_port=None,
        place_registry_port=registry,
        state_port=state,
        event_port=events,
    )

    snapshot = await service.refresh_turn(
        "s1",
        device_id="phone",
        installation_id="install",
        turn_id="t1",
    )

    assert snapshot.context.active_place is not None
    assert snapshot.context.active_place.place_id == "home"
    assert snapshot.projection.semantic_place == "home"
    assert snapshot.projection.raw_location is None
    assert (await state.read_spatial_section("s1"))["projection"]["semantic_place"] == "home"
    assert any(topic == "k1.spatial.context.created.v1" for topic, _payload in events.published)


async def test_spatial_service_projects_coordinate_only_browser_fix_without_raw_coordinates() -> (
    None
):
    service = SpatialService(
        device_context_port=SpatialDeviceContextAdapter(_CoordinateOnlyDeviceContextPort()),
        device_location_port=None,
        place_registry_port=LocalPlaceRegistryAdapter(),
        state_port=SpatialStateAdapter(),
    )

    snapshot = await service.refresh_turn(
        "s1",
        device_id="alex_laptop",
        installation_id="alex_laptop",
        turn_id="t1",
    )

    assert snapshot.context.location_permission == "granted"
    assert snapshot.context.freshness == "live"
    assert snapshot.projection.precision == "address"
    assert snapshot.projection.approximate_location is None
    assert snapshot.projection.metadata["location_accuracy_m"] == 42.0
    assert snapshot.projection.raw_location is None


async def test_spatial_service_uses_profile_semantic_hint_when_no_fix_or_registry_match() -> None:
    service = SpatialService(
        device_context_port=SpatialDeviceContextAdapter(_SemanticOnlyDeviceContextPort()),
        device_location_port=None,
        place_registry_port=LocalPlaceRegistryAdapter(),
        state_port=SpatialStateAdapter(),
    )

    snapshot = await service.refresh_turn(
        "s1",
        device_id="alex_laptop",
        installation_id="alex_laptop",
        turn_id="t1",
    )

    assert snapshot.context.active_place is not None
    assert snapshot.context.active_place.label == "Denton, Texas"
    assert snapshot.context.active_place.source == "device_hint"
    assert snapshot.context.active_place.metadata["semantic_fallback"] is True
    assert snapshot.projection.semantic_place == "Denton, Texas"


async def test_spatial_service_reverse_geocodes_coordinate_only_browser_fix() -> None:
    service = SpatialService(
        device_context_port=SpatialDeviceContextAdapter(_CoordinateOnlyDeviceContextPort()),
        device_location_port=None,
        place_registry_port=LocalPlaceRegistryAdapter(),
        geocoder_port=_ReverseGeocoderPort(),
        state_port=SpatialStateAdapter(),
    )

    snapshot = await service.refresh_turn(
        "s1",
        device_id="alex_laptop",
        installation_id="alex_laptop",
        turn_id="t1",
    )

    assert snapshot.context.active_place is not None
    assert snapshot.context.active_place.label == "Plano, Texas"
    assert snapshot.projection.semantic_place == "Plano, Texas"
    assert snapshot.projection.freshness == "live"
    assert snapshot.projection.raw_location is None


async def test_spatial_service_projects_address_reverse_geocode_without_raw_coordinates() -> None:
    service = SpatialService(
        device_context_port=SpatialDeviceContextAdapter(_CoordinateOnlyDeviceContextPort()),
        device_location_port=None,
        place_registry_port=LocalPlaceRegistryAdapter(),
        geocoder_port=_ReverseAddressGeocoderPort(),
        state_port=SpatialStateAdapter(),
    )

    snapshot = await service.refresh_turn(
        "s1",
        device_id="alex_laptop",
        installation_id="alex_laptop",
        turn_id="t1",
    )

    assert snapshot.context.active_place is not None
    assert snapshot.projection.semantic_place == "123 Example Ln, Sampleton, Testland"
    assert snapshot.projection.precision == "address"
    assert snapshot.projection.raw_location is None
    assert snapshot.projection.metadata["location_accuracy_m"] == 42.0
