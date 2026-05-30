"""Spatial metrics boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ISpatialMetricsPort(Protocol):
    """No-op-safe spatial counters and timings."""

    def incr(
        self,
        name: str,
        value: int = 1,
        tags: Mapping[str, Any] | None = None,
    ) -> None:
        """Increment a spatial metric."""
        ...  # pragma: no cover

    def timing(
        self,
        name: str,
        value_ms: float,
        tags: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a spatial timing metric."""
        ...  # pragma: no cover


__all__ = ["ISpatialMetricsPort"]
