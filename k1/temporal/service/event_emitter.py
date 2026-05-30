"""Temporal event emission helpers."""

from __future__ import annotations

from dataclasses import asdict

from k1.temporal.events import (
    TEMPORAL_ANCHOR_CREATED,
    TEMPORAL_ANCHOR_REFRESHED,
    TEMPORAL_ANCHOR_STALE,
    TEMPORAL_EXPRESSION_AMBIGUOUS,
    TEMPORAL_EXPRESSION_RESOLVED,
    AnchorCreatedPayload,
    AnchorRefreshedPayload,
    AnchorStalePayload,
    ExpressionAmbiguousPayload,
    ExpressionResolvedPayload,
)
from k1.temporal.ports import ITemporalEventPort


class TemporalEventEmitter:
    """Best-effort typed event publisher."""

    def __init__(self, event_port: ITemporalEventPort | None) -> None:
        self._event_port = event_port

    async def publish_anchor_created(self, payload: AnchorCreatedPayload) -> None:
        await self._publish(TEMPORAL_ANCHOR_CREATED, asdict(payload))

    async def publish_anchor_refreshed(self, payload: AnchorRefreshedPayload) -> None:
        await self._publish(TEMPORAL_ANCHOR_REFRESHED, asdict(payload))

    async def publish_anchor_stale(self, payload: AnchorStalePayload) -> None:
        await self._publish(TEMPORAL_ANCHOR_STALE, asdict(payload))

    async def publish_expression_resolved(self, payload: ExpressionResolvedPayload) -> None:
        await self._publish(TEMPORAL_EXPRESSION_RESOLVED, asdict(payload))

    async def publish_expression_ambiguous(self, payload: ExpressionAmbiguousPayload) -> None:
        await self._publish(TEMPORAL_EXPRESSION_AMBIGUOUS, asdict(payload))

    async def _publish(self, topic: str, payload: dict[str, object]) -> None:
        if self._event_port is not None:
            await self._event_port.publish(topic, payload)


__all__ = ["TemporalEventEmitter"]
