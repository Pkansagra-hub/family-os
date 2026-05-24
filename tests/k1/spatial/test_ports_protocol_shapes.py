"""M3-E2 Protocol shape tests for spatial ports."""

from __future__ import annotations

import inspect

from k1.spatial.ports import (
    IDeviceLocationPort,
    IGeocoderPort,
    IPlaceRegistryPort,
    IPresencePort,
    ISpatialDeviceContextPort,
    ISpatialEventPort,
    ISpatialIdPort,
    ISpatialMetricsPort,
    ISpatialPolicyPort,
    ISpatialStatePort,
)


def test_spatial_protocol_methods_are_present() -> None:
    assert (
        "session_id" in inspect.signature(ISpatialDeviceContextPort.get_device_snapshot).parameters
    )
    assert "device_id" in inspect.signature(IDeviceLocationPort.get_location_fix).parameters
    assert "session_id" in inspect.signature(IPlaceRegistryPort.list_places).parameters
    assert "candidate" in inspect.signature(IGeocoderPort.geocode).parameters
    assert "fix" in inspect.signature(IGeocoderPort.reverse_geocode).parameters
    assert "subject_ref" in inspect.signature(IPresencePort.list_presence).parameters
    assert "consumer" in inspect.signature(ISpatialPolicyPort.allowed_precision).parameters
    assert "payload" in inspect.signature(ISpatialStatePort.write_spatial_section).parameters
    assert "topic" in inspect.signature(ISpatialEventPort.publish).parameters
    assert hasattr(ISpatialIdPort, "new_context_id")
    assert "name" in inspect.signature(ISpatialMetricsPort.incr).parameters


def test_spatial_protocols_are_runtime_checkable() -> None:
    class IdPort:
        def new_context_id(self):  # type: ignore[no-untyped-def]
            return "ctx1"

        def new_place_id(self):  # type: ignore[no-untyped-def]
            return "place1"

        def new_geofence_id(self):  # type: ignore[no-untyped-def]
            return "geo1"

        def new_fix_id(self):  # type: ignore[no-untyped-def]
            return "fix1"

        def new_projection_id(self):  # type: ignore[no-untyped-def]
            return "proj1"

    assert isinstance(IdPort(), ISpatialIdPort)
