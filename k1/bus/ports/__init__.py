"""
k1.bus.ports -- Port interfaces (Protocols) for the K1 bus layer.

Exports:
    IBus              -- Pub/sub bus protocol (events AND deltas, unified)
    SubscriptionHandle -- Opaque handle returned by IBus.subscribe()
    IMailbox          -- Single-actor mailbox protocol
    IMailboxRouter    -- Actor mailbox router protocol
    MailboxConfig     -- Actor mailbox configuration
    BackpressureError -- Raised when actor mailbox is full
    UnknownActorError -- Raised when actor is not registered
"""

from .async_bus import AsyncBusHandler, IAsyncBus, IAsyncMailbox, IAsyncMailboxRouter
from .bus import IBus, SubscriptionHandle
from .mailbox import BackpressureError, IMailbox, IMailboxRouter, MailboxConfig, UnknownActorError

__all__ = [
    # Sync ports
    "IBus",
    "SubscriptionHandle",
    "IMailbox",
    "IMailboxRouter",
    "MailboxConfig",
    "BackpressureError",
    "UnknownActorError",
    # Async ports
    "AsyncBusHandler",
    "IAsyncBus",
    "IAsyncMailbox",
    "IAsyncMailboxRouter",
]
