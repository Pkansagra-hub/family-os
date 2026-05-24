"""Temporal metrics boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ITemporalMetricsPort(Protocol):
    """No-op-safe metrics sink for temporal service operations."""

    def incr(self, name: str, value: int = 1) -> None:
        """Increment a counter."""
        ...  # pragma: no cover

    def gauge(self, name: str, value: float) -> None:
        """Record a gauge value."""
        ...  # pragma: no cover

    def timer(self, name: str, ms: int) -> None:
        """Record elapsed milliseconds."""
        ...  # pragma: no cover


__all__ = ["ITemporalMetricsPort"]
