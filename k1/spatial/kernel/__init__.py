"""Kernel integration helpers for k1.spatial."""

from __future__ import annotations

from k1.spatial.kernel.bootstrap import SpatialServiceBundle, build_spatial_bundle
from k1.spatial.kernel.handle import SpatialHandle, build_spatial_handle
from k1.spatial.kernel.session_binding import SpatialSessionBinding

__all__ = [
    "SpatialHandle",
    "SpatialServiceBundle",
    "SpatialSessionBinding",
    "build_spatial_bundle",
    "build_spatial_handle",
]
