"""Context precision declarations for Fabric contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

TemporalPrecision = Literal["anchor", "windows", "execution"]
SpatialPrecision = Literal["hidden", "semantic", "approximate", "place_id", "raw"]

TEMPORAL_PRECISION_VALUES = ("anchor", "windows", "execution")
SPATIAL_PRECISION_VALUES = ("hidden", "semantic", "approximate", "place_id", "raw")


@dataclass(frozen=True)
class ContextPrecision:
    temporal: TemporalPrecision
    spatial: SpatialPrecision

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextPrecision":
        temporal = data.get("temporal")
        spatial = data.get("spatial")
        if temporal not in TEMPORAL_PRECISION_VALUES:
            raise ValueError(f"invalid temporal context precision: {temporal!r}")
        if spatial not in SPATIAL_PRECISION_VALUES:
            raise ValueError(f"invalid spatial context precision: {spatial!r}")
        return cls(temporal=temporal, spatial=spatial)

    def to_dict(self) -> dict[str, str]:
        return {"temporal": self.temporal, "spatial": self.spatial}


def parse_context_precision(value: Any) -> ContextPrecision | None:
    if value is None:
        return None
    if isinstance(value, ContextPrecision):
        return value
    if isinstance(value, Mapping):
        return ContextPrecision.from_dict(value)
    raise TypeError(f"context_precision must be a mapping, got {type(value).__name__}")


__all__ = [
    "ContextPrecision",
    "SPATIAL_PRECISION_VALUES",
    "SpatialPrecision",
    "TEMPORAL_PRECISION_VALUES",
    "TemporalPrecision",
    "parse_context_precision",
]
