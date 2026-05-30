"""Error hierarchy for the k1.spatial kernel module."""

from __future__ import annotations


class SpatialError(Exception):
    """Base error for spatial grounding failures."""


class MissingPlaceRegistryError(SpatialError):
    """Raised when the place registry is required but unavailable."""


class UnknownPlaceError(SpatialError):
    """Raised when a place reference cannot be resolved."""


class InvalidLocationFixError(SpatialError):
    """Raised when a raw location fix is malformed or impossible."""


class StaleLocationError(SpatialError):
    """Raised when a location observation is too old for the requested use."""


class PermissionDeniedSpatialError(SpatialError):
    """Raised when a consumer requests disallowed spatial precision."""


class SpatialPolicyDeniedError(SpatialError):
    """Raised when spatial policy denies a projection or precision request."""


class SpatialUnavailableError(SpatialError):
    """Raised when no trusted spatial source is available."""


__all__ = [
    "InvalidLocationFixError",
    "MissingPlaceRegistryError",
    "PermissionDeniedSpatialError",
    "SpatialError",
    "SpatialPolicyDeniedError",
    "SpatialUnavailableError",
    "StaleLocationError",
    "UnknownPlaceError",
]
