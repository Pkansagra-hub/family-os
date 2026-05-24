"""Deterministic spatial services."""

from __future__ import annotations

from k1.spatial.service.device_surface_resolver import (
    DeviceSurfaceResolver,
    normalize_surface_kind,
    resolve_device_surface,
)
from k1.spatial.service.geofence_matcher import geofence_contains_fix, match_geofences
from k1.spatial.service.location_normalizer import normalize_location_fix
from k1.spatial.service.permission_normalizer import (
    is_location_usable,
    normalize_permission_state,
)
from k1.spatial.service.place_candidate_source import (
    candidates_from_beliefs_active,
    candidates_from_device_context,
    candidates_from_mapping,
    candidates_from_session_state,
)
from k1.spatial.service.place_resolver import resolve_place_candidate
from k1.spatial.service.precision_selector import (
    clamp_precision,
    select_consumer_precision,
)
from k1.spatial.service.privacy_projector import project_context
from k1.spatial.service.projection_builder import (
    SpatialProjectionBuilder,
    build_spatial_projection,
)
from k1.spatial.service.projection_renderer import (
    render_execution_place_block,
    render_place_block,
    render_planning_spatial_block,
)
from k1.spatial.service.spatial_service import SpatialService

__all__ = [
    "DeviceSurfaceResolver",
    "SpatialProjectionBuilder",
    "SpatialService",
    "build_spatial_projection",
    "candidates_from_beliefs_active",
    "candidates_from_device_context",
    "candidates_from_mapping",
    "candidates_from_session_state",
    "clamp_precision",
    "geofence_contains_fix",
    "is_location_usable",
    "match_geofences",
    "normalize_location_fix",
    "normalize_permission_state",
    "normalize_surface_kind",
    "project_context",
    "render_execution_place_block",
    "render_place_block",
    "render_planning_spatial_block",
    "resolve_device_surface",
    "resolve_place_candidate",
    "select_consumer_precision",
]
