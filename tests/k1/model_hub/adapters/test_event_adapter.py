"""TestEventAdapter -- test adapter for IEventPort [6.1.2].

Captures all published events and allows scripted subscriptions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List

from k1.model_hub.ports.event_port import Subscription


@dataclass(frozen=True)
class CapturedEvent:
    """A captured publish() call."""

    topic: str
    payload: Any


class TestEventAdapter:
    """Deterministic IEventPort for testing.

    Capture:
      - published: All (topic, payload) pairs from publish().
      - subscriptions: All active subscriptions.

    isinstance(adapter, IEventPort) == True.
    """

    def __init__(self) -> None:
        self._published: List[CapturedEvent] = []
        self._handlers: Dict[str, List[Callable[[str, Any], Awaitable[None]]]] = {}
        self._subscriptions: List[Subscription] = []

    async def publish(self, topic: str, payload: Any) -> None:
        """Capture event and dispatch to any registered handlers."""
        self._published.append(CapturedEvent(topic=topic, payload=payload))
        for handler in self._handlers.get(topic, []):
            await handler(topic, payload)

    async def subscribe(
        self,
        topics: List[str],
        handler: Callable[[str, Any], Awaitable[None]],
    ) -> Subscription:
        """Register handler for topics."""
        sub_id = str(uuid.uuid4())
        sub = Subscription(subscription_id=sub_id, topics=topics)
        self._subscriptions.append(sub)
        for topic in topics:
            self._handlers.setdefault(topic, []).append(handler)
        return sub

    # -- Test inspection -------------------------------------------------------

    @property
    def published(self) -> List[CapturedEvent]:
        return list(self._published)

    def published_for(self, topic: str) -> List[CapturedEvent]:
        """Get events published to a specific topic."""
        return [e for e in self._published if e.topic == topic]

    @property
    def subscriptions(self) -> List[Subscription]:
        return list(self._subscriptions)

    def reset(self) -> None:
        self._published.clear()
        self._handlers.clear()
        self._subscriptions.clear()


__all__ = ["CapturedEvent", "TestEventAdapter"]
