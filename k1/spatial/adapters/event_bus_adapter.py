"""Spatial event-bus adapter."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from k1.spatial.ports import ISpatialEventPort

logger = logging.getLogger(__name__)


class SpatialEventBusAdapter(ISpatialEventPort):
    """Publish spatial events onto the K1 bus as JSON envelopes."""

    def __init__(self, bus: Any | None = None) -> None:
        self._bus = bus
        self.published: list[tuple[str, Mapping[str, Any]]] = []

    async def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        self.published.append((topic, dict(payload)))
        if self._bus is None:
            return
        try:
            from k1.bus.envelope.envelope import Envelope, Priority
        except Exception:  # pragma: no cover
            logger.warning("SpatialEventBusAdapter: bus envelope import failed", exc_info=True)
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
            logger.warning("SpatialEventBusAdapter: publish failed topic=%s", topic, exc_info=True)


__all__ = ["SpatialEventBusAdapter"]
