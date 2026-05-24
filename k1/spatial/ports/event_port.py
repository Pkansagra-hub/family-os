"""Spatial event boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ISpatialEventPort(Protocol):
    """Publish spatial lifecycle and redaction events."""

    async def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        """Publish a spatial event."""
        ...  # pragma: no cover


__all__ = ["ISpatialEventPort"]
