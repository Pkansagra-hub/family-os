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

    def publish_batch(self, envelopes: list[Envelope]) -> None:
        """
        Publish a batch of envelopes (M7.2 / B06).

        Equivalent to calling ``publish`` for each envelope, but
        implementations MAY amortise per-envelope overhead (e.g.,
        sharing a single subscriber-trie read-lock acquisition across
        the batch).  Per-envelope semantics (stamping, middleware,
        sequence allocation, dispatch) are otherwise identical to
        ``publish``.

        An empty list is a no-op.  The batch is best-effort: a
        middleware drop, outbox failure, or other per-envelope error
        for one envelope does NOT abort the batch.

        Args:
            envelopes: Envelopes to publish, in order.
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

    def flush(self, timeout_ms: int = 5000) -> bool:
        """
        Block until all in-flight envelopes have been delivered to handlers.

        For implementations with synchronous dispatch (publish blocks the
        publisher's thread until handlers complete), this is a no-op and
        always returns True.

        For implementations with asynchronous dispatch (per-subscription
        mailboxes drained by worker threads), this waits until every
        subscription mailbox is empty AND no worker is mid-handler.

        Tests that publish then immediately assert handler side-effects
        should call ``bus.flush()`` first when running against an async-
        dispatch bus.

        Args:
            timeout_ms: Maximum time to wait. 0 = non-blocking check.

        Returns:
            True if drained within timeout; False on timeout.

        Note:
            ``flush()`` is additive (Phase 6 / P6.5).  Implementations
            that pre-date this method satisfy the Protocol via duck
            typing -- the default expectation is that synchronous
            implementations may omit this method, but new implementations
            should define it explicitly.
        """
        ...

    def close(self) -> None:
        """Shut the bus down. Subsequent ``publish`` calls MUST be rejected.

        Idempotent: a second call MUST be a no-op.
        """
        ...

    @property
    def is_closed(self) -> bool:
        """Public closed-state accessor.

        Replaces external reads of the impl-private ``_closed`` slot so
        callers (kernel health-check, tests) do not have to reach into
        adapter internals.
        """
        ...
