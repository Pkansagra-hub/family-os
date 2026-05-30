"""Grounding event publication helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from k1.grounding.events import (
    GROUNDING_ENVELOPE_CREATED,
    GROUNDING_ENVELOPE_STALE,
    GROUNDING_LEASE_CREATED,
    GROUNDING_PROJECTION_CREATED,
    GROUNDING_PROJECTION_DENIED,
)
from k1.grounding.ports import IGroundingEventPort


class GroundingEventEmitter:
    """Publish typed grounding events through an optional event port."""

    def __init__(self, event_port: IGroundingEventPort | None) -> None:
        self._event_port = event_port

    async def publish_envelope_created(self, payload: Any) -> None:
        await self._publish(GROUNDING_ENVELOPE_CREATED, payload)

    async def publish_projection_created(self, payload: Any) -> None:
        await self._publish(GROUNDING_PROJECTION_CREATED, payload)

    async def publish_lease_created(self, payload: Any) -> None:
        await self._publish(GROUNDING_LEASE_CREATED, payload)

    async def publish_envelope_stale(self, payload: Any) -> None:
        await self._publish(GROUNDING_ENVELOPE_STALE, payload)

    async def publish_projection_denied(self, payload: Any) -> None:
        await self._publish(GROUNDING_PROJECTION_DENIED, payload)

    async def _publish(self, topic: str, payload: Any) -> None:
        if self._event_port is None:
            return
        await self._event_port.publish(topic, _payload_to_dict(payload))


def _payload_to_dict(payload: Any) -> Mapping[str, Any]:
    if is_dataclass(payload):
        return asdict(payload)
    if isinstance(payload, Mapping):
        return dict(payload)
    return dict(getattr(payload, "__dict__", {}))


__all__ = ["GroundingEventEmitter"]
