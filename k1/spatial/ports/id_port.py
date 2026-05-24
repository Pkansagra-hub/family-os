"""Spatial ID generation boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ISpatialIdPort(Protocol):
    """Generate stable IDs for spatial runtime objects."""

    def new_context_id(self) -> str:
        """Return a new spatial context ID."""
        ...  # pragma: no cover

    def new_place_id(self) -> str:
        """Return a new place ID."""
        ...  # pragma: no cover

    def new_geofence_id(self) -> str:
        """Return a new geofence ID."""
        ...  # pragma: no cover

    def new_fix_id(self) -> str:
        """Return a new location-fix ID."""
        ...  # pragma: no cover

    def new_projection_id(self) -> str:
        """Return a new spatial projection ID."""
        ...  # pragma: no cover


__all__ = ["ISpatialIdPort"]
