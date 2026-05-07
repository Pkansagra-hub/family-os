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

import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, List

from k1.model_hub.ports.event_port import Subscription

logger = logging.getLogger(__name__)


class EventBusAdapter:
    """IEventPort adapter binding to K1 Event Bus.

    Two modes:

    * **Standalone (default, ``bus=None``)** — in-memory pub/sub for tests
      and single-process runs. Handlers are invoked inline.
    * **Production (``bus=<IBus>``)** — P5.4: forwards to the K1 ``IBus``.
      Payloads are JSON-encoded into ``Envelope.payload``; handlers are
      wrapped to decode the payload and dispatch on the running event loop.

    Error handling: publish failures logged, never crash hub.
    """

    def __init__(self, bus: Any | None = None) -> None:
        self._bus = bus
        self._handlers: dict[str, List[Callable[[str, Any], Awaitable[None]]]] = {}
        self._subscriptions: List[Subscription] = []
        # Track K1-bus subscription handles for cleanup (production mode).
        self._bus_handles: list[Any] = []

    async def publish(self, topic: str, payload: Any) -> None:
        """Publish event to the K1 Event Bus (or in-memory fan-out)."""
        if self._bus is not None:
            try:
                from k1.bus.envelope.envelope import Envelope

                body = json.dumps(payload, default=str).encode("utf-8")
                self._bus.publish(Envelope(topic=topic, payload=body))
                return
            except Exception:
                logger.exception("EventBusAdapter.publish (k1 bus) failed topic=%s", topic)
                return
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
        if self._bus is not None:
            loop = asyncio.get_running_loop()

            def _bus_handler(envelope: Any) -> None:
                try:
                    payload = json.loads(envelope.payload.decode("utf-8"))
                except Exception:
                    payload = envelope.payload
                # Bridge sync bus → async handler.
                asyncio.run_coroutine_threadsafe(handler(envelope.topic, payload), loop)

            for topic in topics:
                self._bus_handles.append(self._bus.subscribe(topic, _bus_handler))
            return sub

        for topic in topics:
            self._handlers.setdefault(topic, []).append(handler)
        return sub


__all__ = ["EventBusAdapter"]
