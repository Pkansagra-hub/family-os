"""M3-E3 geofence matcher tests."""

from __future__ import annotations

from k1.spatial.service import match_geofences
from k1.spatial.types import Geofence, LocationFix


def test_geofence_matcher_matches_circle_with_accuracy_radius() -> None:
    geofence = Geofence(
        geofence_id="geo_home",
        place_id="home",
        shape="circle",
        parameters={"latitude": 33.2, "longitude": -97.1, "radius_m": 100},
        source="registry",
    )
    fix = _fix(33.2002, -97.1002)

    assert match_geofences(fix, (geofence,)) == (geofence,)


def test_geofence_matcher_returns_empty_when_coordinates_unavailable() -> None:
    geofence = Geofence(
        geofence_id="geo_home",
        place_id="home",
        shape="circle",
        parameters={"latitude": 33.2, "longitude": -97.1, "radius_m": 100},
        source="registry",
    )

    assert match_geofences(None, (geofence,)) == ()


def _fix(latitude: float, longitude: float) -> LocationFix:
    return LocationFix(
        latitude=latitude,
        longitude=longitude,
        accuracy_m=20,
        captured_at_utc="2026-05-23T01:00:00+00:00",
        permission_state="granted",
        source="device",
        confidence=0.9,
    )
