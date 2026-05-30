"""UUID-backed spatial ID adapter."""

from __future__ import annotations

import uuid

from k1.spatial.ports import ISpatialIdPort


class UUIDSpatialIdAdapter(ISpatialIdPort):
    """Generate stable prefixed spatial IDs."""

    def new_context_id(self) -> str:
        return f"spatial_{uuid.uuid4().hex}"

    def new_place_id(self) -> str:
        return f"place_{uuid.uuid4().hex}"

    def new_geofence_id(self) -> str:
        return f"geofence_{uuid.uuid4().hex}"

    def new_fix_id(self) -> str:
        return f"fix_{uuid.uuid4().hex}"

    def new_projection_id(self) -> str:
        return f"spatial_projection_{uuid.uuid4().hex}"


__all__ = ["UUIDSpatialIdAdapter"]
