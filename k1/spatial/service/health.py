"""Spatial service health snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SpatialHealth:
    """Health shape for the spatial module."""

    status: str
    module: str = "spatial"
    place_registry: Mapping[str, Any] = field(default_factory=dict)
    device_location: Mapping[str, Any] = field(default_factory=dict)
    last_context_id: str | None = None
    safe_mode: bool = False

    @property
    def ready(self) -> bool:
        return self.status in {"ok", "degraded"}


__all__ = ["SpatialHealth"]
