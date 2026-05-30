"""Temporal SessionState boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ITemporalStatePort(Protocol):
    """Read/write the canonical temporal SessionState section."""

    async def write_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        """Write the serialized temporal section payload."""
        ...  # pragma: no cover

    async def read_section(self, session_id: str) -> Mapping[str, Any] | None:
        """Read the serialized temporal section payload, if available."""
        ...  # pragma: no cover


__all__ = ["ITemporalStatePort"]
