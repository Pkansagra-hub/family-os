"""
Async port protocols for K1 Bus layer.

These protocols mirror the sync IBus / IMailbox / IMailboxRouter ports
but expose ``async def`` methods so that async callers (Fabric, Orchestrator,
Planner, ModelHub) can talk to the bus without blocking the event-loop.

The *only* concrete implementation shipped today is :class:`AsyncBusBridge`
(see ``k1.bus.async_bridge``), which wraps the sync ``LocalBus`` via
``asyncio.to_thread``.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Optional, Protocol, runtime_checkable

from k1.bus.envelope import Envelope
from k1.bus.ports.bus import SubscriptionHandle

# ---------------------------------------------------------------------------
# Type alias – async handler receives an Envelope, returns nothing.
# ---------------------------------------------------------------------------
AsyncBusHandler = Callable[[Envelope], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# IAsyncBus
# ---------------------------------------------------------------------------
@runtime_checkable
class IAsyncBus(Protocol):
    """
    Async pub/sub bus port.

    Mirrors :class:`k1.bus.ports.bus.IBus` with ``async def`` methods.
    """

    async def publish(self, envelope: Envelope) -> None:
        """Publish an envelope onto the bus (async)."""
        ...

    async def subscribe(self, pattern: str, handler: AsyncBusHandler) -> SubscriptionHandle:
        """Subscribe to a topic pattern with an async handler."""
        ...

    async def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Remove a subscription by handle."""
        ...


# ---------------------------------------------------------------------------
# IAsyncMailbox
# ---------------------------------------------------------------------------
@runtime_checkable
class IAsyncMailbox(Protocol):
    """
    Async mailbox port – the consumer side of a point-to-point channel.

    Mirrors :class:`k1.bus.ports.mailbox.IMailbox`.
    """

    async def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        """Receive the next envelope (async, non-blocking to the event-loop)."""
        ...

    def pending(self) -> int:
        """Number of enqueued envelopes (lock-free, always sync)."""
        ...


# ---------------------------------------------------------------------------
# IAsyncMailboxRouter
# ---------------------------------------------------------------------------
@runtime_checkable
class IAsyncMailboxRouter(Protocol):
    """
    Async mailbox router port – delivers envelopes to actor mailboxes.

    Mirrors :class:`k1.bus.ports.mailbox.IMailboxRouter`.
    """

    async def deliver(self, actor_id: str, envelope: Envelope) -> None:
        """Deliver an envelope to an actor's mailbox (async)."""
        ...

    async def register(
        self,
        actor_id: str,
        config: Optional["MailboxConfig"] = None,
    ) -> IAsyncMailbox:
        """Register an actor mailbox and return an async view of it."""
        ...

    async def unregister(self, actor_id: str) -> bool:
        """Unregister an actor mailbox."""
        ...

    def registered_actors(self) -> list[str]:
        """List registered actor IDs (lock-free, always sync)."""
        ...


# Re-import for the Optional["MailboxConfig"] forward ref above
from k1.bus.ports.mailbox import MailboxConfig  # noqa: E402, F811

__all__ = [
    "AsyncBusHandler",
    "IAsyncBus",
    "IAsyncMailbox",
    "IAsyncMailboxRouter",
]
