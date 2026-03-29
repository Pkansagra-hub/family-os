"""
k1.bus.ports.bus -- IBus protocol and SubscriptionHandle.

IBus is the SINGLE canonical pub/sub interface for the K1 bus layer.
It replaces the separate IEventBus / IDeltaBus split -- the bus is
BLIND to payload content (opaque bytes inside Envelope).

Design:
    - Topic-based pub/sub with trie-matching (exact + prefix wildcard)
    - Fire-and-forget, at-most-once semantics
    - Handlers receive full Envelope (header + payload)
    - Bus stamps envelope_id, sequence, created_ns on publish
    - Bus NEVER reads payload bytes

Structural subtyping:
    IBus is @runtime_checkable so implementations can be checked with
    isinstance(obj, IBus) without inheritance.  This is Python's
    Protocol pattern -- any class with matching methods satisfies IBus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from k1.bus.envelope import Envelope

# ---------------------------------------------------------------------------
# Subscription handle (returned by subscribe, passed to unsubscribe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubscriptionHandle:
    """
    Opaque handle for an active subscription.

    Returned by IBus.subscribe(), passed to IBus.unsubscribe().
    The bus implementation fills these fields; callers should not
    construct handles directly.

    Attributes:
        subscription_id: Unique identifier for this subscription.
        pattern:         The topic or pattern that was subscribed to.
    """

    subscription_id: str
    pattern: str


# ---------------------------------------------------------------------------
# Handler type alias
# ---------------------------------------------------------------------------

#: Signature for bus subscription handlers.
#: Called by the bus when a matching envelope arrives.
#: Handler exceptions are caught by the bus (fail-safe) and logged.
BusHandler = Callable[[Envelope], None]


# ---------------------------------------------------------------------------
# IBus protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IBus(Protocol):
    """
    Canonical pub/sub bus protocol for K1.

    All events (capability, lifecycle, delta, feedback, etc.) flow
    through IBus as Envelope instances with opaque bytes payloads.

    Implementations:
        - LocalBus  (M2, in-process, for single-node and testing)
        - Future: DistributedBus backed by external broker

    Concurrency:
        Implementations MUST be thread-safe.  subscribe/unsubscribe
        may be called from any thread.  Handlers MAY be invoked on
        a dispatch thread or the caller's thread depending on impl.

    Topic matching:
        - Exact: "k1.capability.completed.v1"
        - Prefix wildcard: "k1.capability.*" matches all under k1.capability

    Error handling:
        - Handler exceptions MUST be caught by the bus, logged,
          and MUST NOT propagate to the publisher.
        - publish() itself MUST NOT raise for normal payloads.
    """

    def publish(self, envelope: Envelope) -> None:
        """
        Publish an envelope to the bus.

        The bus will:
            1. Stamp envelope_id (global monotonic)
            2. Stamp sequence (per-topic monotonic)
            3. Stamp created_ns (monotonic clock)
            4. Match topic against subscriber patterns
            5. Dispatch to matching handlers

        The original envelope is NOT mutated (frozen dataclass).
        Handlers receive a NEW envelope with bus-stamped fields.

        Args:
            envelope: Envelope with at minimum topic and payload set.
                      Bus-assigned fields (envelope_id, sequence,
                      created_ns) will be overwritten.
        """
        ...

    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
        """
        Subscribe a handler to a topic pattern.

        Args:
            pattern: Topic string or prefix wildcard (e.g. "k1.delta.*").
            handler: Callable[[Envelope], None] invoked on match.

        Returns:
            SubscriptionHandle that can be passed to unsubscribe().
        """
        ...

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """
        Remove a subscription.

        Args:
            handle: The handle returned by subscribe().

        Returns:
            True if the subscription was found and removed,
            False if it was already removed or unknown.
        """
        ...
