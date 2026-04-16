"""
k1.bus -- K1 Cognitive Architecture Bus Layer.

The bus layer provides two complementary messaging primitives:

    IBus             Pub/sub with trie topic matching (events + deltas)
    IMailboxRouter   Point-to-point actor mailboxes with WFQ priority

Both primitives carry Envelope -- a frozen dataclass with opaque bytes
payload.  The bus NEVER reads payload content.

Ordering enforcement is provided by TimingChain, which sits between
publish and dispatch.  STRICT topics get causal + sequence ordering,
RELAXED get monitoring, BEST_EFFORT bypasses everything.

Public API
----------
Envelope types:
    Envelope, Priority, DeliveryMode

Bus port:
    IBus, SubscriptionHandle, BusHandler

Mailbox ports:
    IMailbox, IMailboxRouter, MailboxConfig,
    BackpressureError, UnknownActorError

Implementations:
    LocalBus, BusFactory, BusStats, TopicTrie
    LocalMailbox, LocalMailboxRouter

Middleware:
    Middleware, MiddlewareChain,
    TracingMiddleware, MetricsMiddleware,
    TopicRegistry, TopicValidationMiddleware

Adapters:
    FabricBusAdapter, SessionBusAdapter

Timing:
    TimingChain, TimingConfig, TimingStats,
    default_timing_config, DEFAULT_RULES, DEFAULT_MODE
"""

from k1.bus.adapters import FabricBusAdapter, SessionBusAdapter
from k1.bus.async_bridge import AsyncBusBridge, AsyncMailboxBridge, AsyncMailboxRouterBridge
from k1.bus.config import BusConfig, load_bus_config
from k1.bus.envelope import DeliveryMode, Envelope, PayloadFormat, Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import BusStats, LocalBus
from k1.bus.impl.local_mailbox import LocalMailbox, LocalMailboxRouter
from k1.bus.impl.topic_trie import TopicTrie
from k1.bus.middleware import Middleware, MiddlewareChain
from k1.bus.middleware.metrics import MetricsMiddleware
from k1.bus.middleware.topic_validation import TopicRegistry, TopicValidationMiddleware
from k1.bus.middleware.tracing import TracingMiddleware
from k1.bus.ports.async_bus import AsyncBusHandler, IAsyncBus, IAsyncMailbox, IAsyncMailboxRouter
from k1.bus.ports.bus import BusHandler, IBus, SubscriptionHandle
from k1.bus.ports.mailbox import (
    BackpressureError,
    IMailbox,
    IMailboxRouter,
    MailboxConfig,
    UnknownActorError,
)
from k1.bus.timing import (
    DEFAULT_MODE,
    DEFAULT_RULES,
    TimingChain,
    TimingConfig,
    TimingStats,
    default_timing_config,
)

__all__ = [
    # Envelope
    "Envelope",
    "Priority",
    "DeliveryMode",
    "PayloadFormat",
    # Sync bus port
    "IBus",
    "SubscriptionHandle",
    "BusHandler",
    # Async bus ports
    "IAsyncBus",
    "IAsyncMailbox",
    "IAsyncMailboxRouter",
    "AsyncBusHandler",
    # Async bridge implementations
    "AsyncBusBridge",
    "AsyncMailboxBridge",
    "AsyncMailboxRouterBridge",
    # Bus implementation
    "LocalBus",
    "BusFactory",
    "BusStats",
    "TopicTrie",
    # Mailbox port
    "IMailbox",
    "IMailboxRouter",
    "MailboxConfig",
    "BackpressureError",
    "UnknownActorError",
    # Mailbox implementation
    "LocalMailbox",
    "LocalMailboxRouter",
    # Middleware
    "Middleware",
    "MiddlewareChain",
    "TracingMiddleware",
    "MetricsMiddleware",
    "TopicRegistry",
    "TopicValidationMiddleware",
    # Adapters
    "FabricBusAdapter",
    "SessionBusAdapter",
    # Config
    "BusConfig",
    "load_bus_config",
    # Timing
    "TimingChain",
    "TimingConfig",
    "TimingStats",
    "default_timing_config",
    "DEFAULT_RULES",
    "DEFAULT_MODE",
]
