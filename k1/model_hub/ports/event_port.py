"""IEventPort -- event bus pub/sub [F11].

Publish model_hub events and subscribe to config updates.

Import graph (Layer 1)
----------------------
k1.model_hub.ports.event_port
  -> stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Protocol, runtime_checkable


@dataclass(frozen=True)
class Subscription:
    """Event subscription handle for unsubscribe."""

    subscription_id: str
    topics: List[str]


@runtime_checkable
class IEventPort(Protocol):
    """Event bus pub/sub for Model Hub events.

    Pub: all k1.model_hub.*.v1 events.
    Sub: k1.model_hub.config_update.v1.
    """

    async def publish(self, topic: str, payload: Any) -> None:
        """Publish an event to the given topic."""
        ...

    async def subscribe(
        self,
        topics: List[str],
        handler: Callable[[str, Any], Awaitable[None]],
    ) -> Subscription:
        """Subscribe to one or more topics with an async handler."""
        ...


__all__ = ["IEventPort", "Subscription"]
