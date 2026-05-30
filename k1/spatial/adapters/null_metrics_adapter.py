"""No-op metrics adapter for spatial services."""

from __future__ import annotations

from typing import Any, Mapping

from k1.spatial.ports import ISpatialMetricsPort


class NullSpatialMetricsAdapter(ISpatialMetricsPort):
    """No-op spatial metrics sink."""

    def incr(
        self,
        name: str,
        value: int = 1,
        tags: Mapping[str, Any] | None = None,
    ) -> None:
        return None

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, Any] | None = None,
    ) -> None:
        return None


__all__ = ["NullSpatialMetricsAdapter"]
