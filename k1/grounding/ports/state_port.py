"""Grounding SessionState boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class IGroundingStatePort(Protocol):
    """Read/write serialized grounding runtime metadata."""

    async def write_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        """Write the serialized grounding section payload."""
        ...  # pragma: no cover

    async def read_section(self, session_id: str) -> Mapping[str, Any] | None:
        """Read the serialized grounding section payload, if available."""
        ...  # pragma: no cover


__all__ = ["IGroundingStatePort"]
