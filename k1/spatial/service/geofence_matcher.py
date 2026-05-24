"""Geofence matching with explicit coordinate availability checks."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, Mapping

from k1.spatial.types import Geofence, LocationFix


def match_geofences(fix: LocationFix | None, geofences: Iterable[Geofence]) -> tuple[Geofence, ...]:
    """Return geofences containing the fix, or empty when coordinates are unavailable."""
    if fix is None or fix.latitude is None or fix.longitude is None:
        return ()
    return tuple(item for item in geofences if geofence_contains_fix(item, fix))


def geofence_contains_fix(geofence: Geofence, fix: LocationFix) -> bool:
    """Evaluate circle or polygon geofence membership."""
    if fix.latitude is None or fix.longitude is None:
        return False
    shape = geofence.shape.strip().lower()
    if shape == "circle":
        return _contains_circle(geofence.parameters, fix)
    if shape == "polygon":
        return _contains_polygon(geofence.parameters, fix)
    return False


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _contains_circle(parameters: Mapping[str, Any], fix: LocationFix) -> bool:
    center_lat = float(parameters.get("center_latitude", parameters.get("latitude")))
    center_lon = float(parameters.get("center_longitude", parameters.get("longitude")))
    radius_m = float(parameters.get("radius_m", 0.0))
    accuracy = fix.accuracy_m or 0.0
    return distance_m(center_lat, center_lon, fix.latitude or 0.0, fix.longitude or 0.0) <= (
        radius_m + accuracy
    )


def _contains_polygon(parameters: Mapping[str, Any], fix: LocationFix) -> bool:
    points = parameters.get("points", ())
    vertices = [(float(item[0]), float(item[1])) for item in points]
    if len(vertices) < 3:
        return False
    inside = False
    lat = fix.latitude or 0.0
    lon = fix.longitude or 0.0
    j = len(vertices) - 1
    for i, (lat_i, lon_i) in enumerate(vertices):
        lat_j, lon_j = vertices[j]
        intersects = (lon_i > lon) != (lon_j > lon) and lat < (lat_j - lat_i) * (lon - lon_i) / (
            (lon_j - lon_i) or 1e-12
        ) + lat_i
        if intersects:
            inside = not inside
        j = i
    return inside


__all__ = ["distance_m", "geofence_contains_fix", "match_geofences"]
