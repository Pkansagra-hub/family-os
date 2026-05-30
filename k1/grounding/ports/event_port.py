"""Grounding event publication boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class IGroundingEventPort(Protocol):
    """Publish grounding events to the kernel/session bus."""

    async def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        """Publish a JSON-safe event payload."""
        ...  # pragma: no cover


__all__ = ["IGroundingEventPort"]
