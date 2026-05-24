"""Clock port for deterministic temporal computations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IClockPort(Protocol):
    """Wall-clock and monotonic time boundary."""

    def now_utc(self) -> str:
        """Return the current UTC instant as an ISO-8601 string."""
        ...  # pragma: no cover

    def monotonic_ms(self) -> int:
        """Return a monotonic clock reading in milliseconds."""
        ...  # pragma: no cover


__all__ = ["IClockPort"]
