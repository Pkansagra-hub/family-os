"""Emit spatial service events through the event port."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any, Mapping, cast

from k1.spatial.events import (
    SPATIAL_CONTEXT_CREATED,
    SPATIAL_CONTEXT_REDACTED,
    SPATIAL_CONTEXT_REFRESHED,
    SPATIAL_LOCATION_UNAVAILABLE,
    SPATIAL_PLACE_RESOLVED,
    SpatialContextCreatedPayload,
    SpatialContextRedactedPayload,
    SpatialContextRefreshedPayload,
    SpatialLocationUnavailablePayload,
    SpatialPlaceResolvedPayload,
)
from k1.spatial.ports import ISpatialEventPort


class SpatialEventEmitter:
    """Convert spatial outcomes to bus events."""

    def __init__(self, event_port: ISpatialEventPort | None = None) -> None:
        self._event_port = event_port

    async def context_created(self, payload: SpatialContextCreatedPayload) -> None:
        await self._publish(SPATIAL_CONTEXT_CREATED, payload)

    async def context_refreshed(self, payload: SpatialContextRefreshedPayload) -> None:
        await self._publish(SPATIAL_CONTEXT_REFRESHED, payload)

    async def place_resolved(self, payload: SpatialPlaceResolvedPayload) -> None:
        await self._publish(SPATIAL_PLACE_RESOLVED, payload)

    async def context_redacted(self, payload: SpatialContextRedactedPayload) -> None:
        await self._publish(SPATIAL_CONTEXT_REDACTED, payload)

    async def location_unavailable(self, payload: SpatialLocationUnavailablePayload) -> None:
        await self._publish(SPATIAL_LOCATION_UNAVAILABLE, payload)

    async def _publish(self, topic: str, payload: object) -> None:
        if self._event_port is not None:
            if is_dataclass(payload):
                event_payload = {
                    field.name: getattr(payload, field.name) for field in fields(payload)
                }
            else:
                event_payload = cast(Mapping[str, Any], payload)
            await self._event_port.publish(topic, event_payload)


__all__ = ["SpatialEventEmitter"]
