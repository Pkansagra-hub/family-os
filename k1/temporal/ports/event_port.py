"""Temporal event publication boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class ITemporalEventPort(Protocol):
    """Publish temporal events to the kernel/session bus."""

    async def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        """Publish a JSON-safe event payload."""
        ...  # pragma: no cover


__all__ = ["ITemporalEventPort"]
