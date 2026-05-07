"""EventSubscriptionAdapter -- bridges MW's IEventSubscriptionPort to FabricBusAdapter.

Translates:
  MW  subscribe(topic, async_handler) -> Subscription
  ->  bus.subscribe(topic, sync_wrapper) -> FabricSubscriptionHandle -> Subscription

  MW  unsubscribe(subscription_id)
  ->  bus.unsubscribe(handle)

  MW  publish(topic, payload)
  ->  bus.emit(topic, payload)

Key differences from FabricBusAdapter directly:
  - MW handlers are async (bus handlers are sync) -> wrapper creates asyncio task
  - MW subscribe returns Subscription (not FabricSubscriptionHandle)
  - MW unsubscribe takes subscription_id string (not handle object)

References:
  - E-MW-5.1: Production Adapters
  - k1/memory_writer/ports/event_subscription_port.py (IEventSubscriptionPort)
  - k1/bus/adapters/fabric_adapter.py (FabricBusAdapter)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Protocol, runtime_checkable

from k1.memory_writer.types import Subscription

logger = logging.getLogger(__name__)


@runtime_checkable
class _IFabricBus(Protocol):
    """Minimal local Protocol for FabricBusAdapter dependency."""

    def subscribe(self, topic: str, handler: Callable[..., Any]) -> Any: ...

    def unsubscribe(self, handle: Any) -> None: ...

    def emit(self, topic: str, payload: dict) -> None: ...


class EventSubscriptionAdapter:
    """Implements IEventSubscriptionPort by wrapping FabricBusAdapter.

    Constructor Args:
        bus_adapter: FabricBusAdapter instance (typed as Any to avoid
            import coupling).
    """

    __slots__ = ("_bus", "_subscriptions")

    def __init__(self, bus_adapter: _IFabricBus) -> None:
        self._bus = bus_adapter
        self._subscriptions: dict[str, Any] = {}  # sub_id -> (handle, topic)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> Subscription:
        """Subscribe to a K1 Bus topic with an async handler.

        FabricBusAdapter.subscribe() expects sync handlers.
        This adapter wraps the async handler in asyncio.create_task().
        """

        def _sync_wrapper(event_topic: str, payload: dict) -> None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(handler(payload))
            except RuntimeError:
                # No running loop (unlikely in production)
                logger.warning("MW: no event loop for handler, topic=%s", topic)

        handle = self._bus.subscribe(topic, _sync_wrapper)
        sub_id = handle.subscription_id
        self._subscriptions[sub_id] = (handle, topic)

        return Subscription(subscription_id=sub_id, topic=topic)

    async def unsubscribe(
        self,
        subscription_id: str,
    ) -> None:
        """Remove a subscription by ID."""
        entry = self._subscriptions.pop(subscription_id, None)
        if entry:
            handle, _topic = entry
            self._bus.unsubscribe(handle)

    async def publish(
        self,
        topic: str,
        payload: dict,
    ) -> None:
        """Publish an observability event to the K1 Bus.

        Delegates to FabricBusAdapter.emit() (fire-and-forget).
        """
        self._bus.emit(topic, payload)
