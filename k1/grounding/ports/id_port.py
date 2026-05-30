"""Grounding ID generation boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IGroundingIdPort(Protocol):
    """Generate stable IDs for grounding runtime payloads."""

    def new_envelope_id(self) -> str:
        """Return a new envelope ID."""
        ...  # pragma: no cover

    def new_projection_id(self) -> str:
        """Return a new projection ID."""
        ...  # pragma: no cover

    def new_lease_id(self) -> str:
        """Return a new lease ID."""
        ...  # pragma: no cover


__all__ = ["IGroundingIdPort"]
