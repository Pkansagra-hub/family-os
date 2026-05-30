"""Temporal event bus adapter."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from k1.temporal.ports import ITemporalEventPort

logger = logging.getLogger(__name__)


class EventBusAdapter(ITemporalEventPort):
    """Publish temporal events onto the K1 bus as JSON envelopes."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus

    async def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        try:
            from k1.bus.envelope.envelope import Envelope, Priority
        except Exception:  # pragma: no cover
            logger.warning("EventBusAdapter: bus envelope import failed", exc_info=True)
            return
        try:
            raw = json.dumps(dict(payload), separators=(",", ":"), default=str).encode("utf-8")
            session_id = str(payload.get("session_id") or "")
            self._bus.publish(
                Envelope(
                    topic=topic,
                    payload=raw,
                    session_id=session_id,
                    cognitive_trace_id=str(payload.get("trace_id", "")),
                    priority=Priority.INTERACTIVE,
                )
            )
        except Exception:
            logger.warning("EventBusAdapter: publish failed topic=%s", topic, exc_info=True)


__all__ = ["EventBusAdapter"]
