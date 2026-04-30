"""HIL-local IEventPort (E1.M1.7).

Minimal surface the HIL service needs: publish a topic + payload, and
subscribe a handler with `(topic, payload)` signature.

Production adapters (e.g. `k1.fabric.adapters.event_port_prod`) satisfy
this Protocol structurally without importing it.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

# Subscription handles are returned by `subscribe()` so the caller can
# unsubscribe on shutdown. We treat them as opaque -- any object that
# the underlying bus understands.
SubscriptionHandle = Any

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


@runtime_checkable
class IEventPort(Protocol):
    """Bus port from the HIL service's perspective."""

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish a payload dict to a topic. Must be awaitable."""
        ...

    def subscribe(self, topic: str, handler: EventHandler) -> SubscriptionHandle:
        """Register a handler for a topic. Returns a handle for later
        unsubscription. Handler signature MUST be `async (topic, payload)`.
        """
        ...

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """Remove a previously registered subscription. Idempotent."""
        ...
