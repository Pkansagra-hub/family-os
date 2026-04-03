"""EventBusAdapter -- K1 Event Bus pub/sub binding [F31].

Publishes all model_hub events with trace_id.
Subscribes to config_update events for hot-reload.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.event_bus_adapter
  -> k1.model_hub.ports      (Layer 1)
  -> stdlib only
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, List

from k1.model_hub.ports.event_port import Subscription

logger = logging.getLogger(__name__)


class EventBusAdapter:
    """IEventPort adapter binding to K1 Event Bus.

    Production: delegates to K1 bus transport.
    Current: in-memory pub/sub for single-process operation.

    Error handling: publish failures logged, never crash hub.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, List[Callable[[str, Any], Awaitable[None]]]] = {}
        self._subscriptions: List[Subscription] = []

    async def publish(self, topic: str, payload: Any) -> None:
        """Publish event to K1 Event Bus."""
        try:
            for handler in self._handlers.get(topic, []):
                await handler(topic, payload)
        except Exception:
            logger.exception("EventBusAdapter.publish failed topic=%s", topic)

    async def subscribe(
        self,
        topics: List[str],
        handler: Callable[[str, Any], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to event topics."""
        sub_id = str(uuid.uuid4())
        sub = Subscription(subscription_id=sub_id, topics=topics)
        self._subscriptions.append(sub)
        for topic in topics:
            self._handlers.setdefault(topic, []).append(handler)
        return sub


__all__ = ["EventBusAdapter"]
