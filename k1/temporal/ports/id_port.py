"""Temporal ID generation boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ITemporalIdPort(Protocol):
    """Generate stable IDs for temporal payloads."""

    def new_anchor_id(self) -> str:
        """Return a new anchor ID."""
        ...  # pragma: no cover

    def new_window_id(self) -> str:
        """Return a new window ID."""
        ...  # pragma: no cover

    def new_resolution_id(self) -> str:
        """Return a new resolution ID."""
        ...  # pragma: no cover


__all__ = ["ITemporalIdPort"]
