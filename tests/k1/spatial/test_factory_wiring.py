"""M3-E4 SpatialFactory wiring tests."""

from __future__ import annotations

import pytest

from k1.spatial.adapters import NominatimGeocoderAdapter, NullGeocoderAdapter
from k1.spatial.factory import DuplicateSpatialPortError, SpatialFactory
from k1.spatial.kernel import SpatialServiceBundle, build_spatial_bundle
from k1.spatial.ports import ISpatialDeviceContextPort, ISpatialIdPort


def test_spatial_factory_create_for_testing_returns_bundle_and_adapters() -> None:
    bundle, adapters = SpatialFactory.create_for_testing()

    assert isinstance(bundle, SpatialServiceBundle)
    assert isinstance(adapters["device_context_port"], ISpatialDeviceContextPort)
    assert isinstance(adapters["id_port"], ISpatialIdPort)
    assert bundle.health().module == "spatial"


def test_spatial_factory_rejects_duplicate_port_identity() -> None:
    bundle, adapters = SpatialFactory.create_for_testing()
    multi_role = _IdAndMetricsPort()

    with pytest.raises(DuplicateSpatialPortError):
        SpatialFactory.create_with_ports(
            device_context_port=adapters["device_context_port"],
            device_location_port=adapters["device_location_port"],
            place_registry_port=adapters["place_registry_port"],
            geocoder_port=adapters["geocoder_port"],
            presence_port=adapters["presence_port"],
            policy_port=adapters["policy_port"],
            state_port=adapters["state_port"],
            event_port=None,
            id_port=multi_role,
            metrics_port=multi_role,
            config=bundle.config,
        )


def test_spatial_bootstrap_selects_env_reverse_geocoder(monkeypatch: pytest.MonkeyPatch) -> None:
    _bundle, adapters = SpatialFactory.create_for_testing()

    monkeypatch.setenv("K1_SPATIAL_GEOCODER", "nominatim")
    nominatim_bundle = build_spatial_bundle(
        device_context_port=adapters["device_context_port"],
        state_port=adapters["state_port"],
        id_port=adapters["id_port"],
    )

    assert isinstance(nominatim_bundle.geocoder_port, NominatimGeocoderAdapter)

    monkeypatch.setenv("K1_SPATIAL_GEOCODER", "none")
    null_bundle = build_spatial_bundle(
        device_context_port=adapters["device_context_port"],
        state_port=adapters["state_port"],
        id_port=adapters["id_port"],
    )

    assert isinstance(null_bundle.geocoder_port, NullGeocoderAdapter)


class _IdAndMetricsPort:
    def new_context_id(self) -> str:
        return "ctx"

    def new_place_id(self) -> str:
        return "place"

    def new_geofence_id(self) -> str:
        return "geo"

    def new_fix_id(self) -> str:
        return "fix"

    def new_projection_id(self) -> str:
        return "projection"

    def incr(self, name: str, value: int = 1, tags=None) -> None:  # type: ignore[no-untyped-def]
        return None

    def timing(self, name: str, value_ms: float, tags=None) -> None:  # type: ignore[no-untyped-def]
        return None
