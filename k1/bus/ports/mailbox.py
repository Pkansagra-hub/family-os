"""
k1.bus.ports.mailbox -- IMailbox, IMailboxRouter protocols and support types.

IMailbox is the single-actor inbox.  IMailboxRouter dispatches envelopes
to actor mailboxes by actor_id.

Design differences from IBus:
    - At-least-once delivery (vs at-most-once for IBus)
    - Per-actor bounded queue with backpressure
    - Weighted Fair Queue (WFQ) priority across actors
    - Point-to-point (unicast) instead of pub/sub (multicast)

Usage:
    The Orchestrator and Planner use IMailboxRouter to send envelopes
    to specific sub-agents.  Sub-agents receive from their IMailbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from k1.bus.envelope import Envelope

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BackpressureError(Exception):
    """Raised when an actor's mailbox is full and cannot accept envelopes."""

    def __init__(self, actor_id: str, capacity: int) -> None:
        self.actor_id = actor_id
        self.capacity = capacity
        super().__init__(f"Mailbox for actor '{actor_id}' is full (capacity={capacity})")


class TtlExpiredError(Exception):
    """Raised/recorded when an envelope's TTL has expired before delivery.

    Used as the error passed to the DLQ callback when the bus drops an
    envelope whose ``ttl_ms`` window has elapsed (M7.1 / B01).
    """

    def __init__(self, envelope_id: int, topic: str, age_ms: int, ttl_ms: int) -> None:
        self.envelope_id = envelope_id
        self.topic = topic
        self.age_ms = age_ms
        self.ttl_ms = ttl_ms
        super().__init__(
            f"Envelope {envelope_id} on topic '{topic}' expired "
            f"(age_ms={age_ms} ttl_ms={ttl_ms})"
        )


class UnknownActorError(Exception):
    """Raised when delivery is attempted to an unregistered actor."""

    def __init__(self, actor_id: str) -> None:
        self.actor_id = actor_id
        super().__init__(f"Unknown actor: '{actor_id}'")


# ---------------------------------------------------------------------------
# MailboxConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MailboxConfig:
    """
    Configuration for a single actor's mailbox.

    Attributes:
        capacity:     Maximum number of envelopes in the mailbox queue.
                      Must be > 0.  Default 256.
        priority_wfq: Whether to use WFQ scheduling across priority
                      levels within this mailbox.  Default True.
        wfq_quantum:  M7.3 / B08.  When set, switches the WFQ scheduler
                      from strict priority to deficit round-robin (DRR)
                      with the given per-priority quantum tuple in
                      ``(URGENT, REALTIME, INTERACTIVE, BACKGROUND)``
                      order (e.g. ``(4, 3, 2, 1)``).  Strict-priority
                      semantics are preserved when ``None`` (default).
                      Only honoured when ``priority_wfq=True``.
    """

    capacity: int = 256
    priority_wfq: bool = True
    wfq_quantum: Optional[tuple[int, int, int, int]] = None

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {self.capacity}")
        if self.wfq_quantum is not None:
            if len(self.wfq_quantum) != 4:
                raise ValueError(
                    f"wfq_quantum must be a 4-tuple, got length {len(self.wfq_quantum)}"
                )
            if any(q <= 0 for q in self.wfq_quantum):
                raise ValueError(f"wfq_quantum values must all be > 0, got {self.wfq_quantum}")


# ---------------------------------------------------------------------------
# IMailbox protocol (single actor inbox)
# ---------------------------------------------------------------------------


@runtime_checkable
class IMailbox(Protocol):
    """
    Single-actor mailbox -- the receive side.

    Actors call receive() to get the next envelope from their inbox.
    The mailbox may internally order by WFQ priority.

    Implementations:
        - LocalMailbox (M3, in-process bounded queue)
    """

    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        """
        Receive the next envelope from this mailbox.

        Args:
            timeout_ms: How long to wait for an envelope.
                        0 = non-blocking (return None immediately if empty).
                        >0 = block up to timeout_ms milliseconds.

        Returns:
            The next Envelope, or None if the mailbox is empty and
            timeout expired.
        """
        ...

    def pending(self) -> int:
        """Return the number of envelopes waiting in this mailbox."""
        ...


# ---------------------------------------------------------------------------
# IMailboxRouter protocol (dispatcher across actor mailboxes)
# ---------------------------------------------------------------------------


@runtime_checkable
class IMailboxRouter(Protocol):
    """
    Mailbox router -- dispatches envelopes to actor mailboxes.

    The router maintains a registry of actor_id -> IMailbox mappings
    and provides point-to-point delivery with backpressure.

    Implementations:
        - LocalMailboxRouter (M3, in-process)

    Error handling:
        - BackpressureError raised when target mailbox is full.
        - UnknownActorError raised when actor_id is not registered.
    """

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        """
        Deliver an envelope to a specific actor's mailbox.

        Args:
            actor_id: Target actor identifier.
            envelope: The envelope to deliver.

        Raises:
            UnknownActorError:  actor_id not registered.
            BackpressureError:  actor's mailbox is full.
        """
        ...

    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox:
        """
        Register an actor and create its mailbox.

        Args:
            actor_id: Unique actor identifier.
            config:   Mailbox configuration.  None = use defaults.

        Returns:
            The IMailbox that the actor will receive from.

        Raises:
            ValueError: actor_id already registered.
        """
        ...

    def unregister(self, actor_id: str) -> bool:
        """
        Remove an actor and its mailbox.

        Pending envelopes in the mailbox are discarded.

        Args:
            actor_id: The actor to remove.

        Returns:
            True if the actor was found and removed, False otherwise.
        """
        ...

    def registered_actors(self) -> list[str]:
        """Return the list of currently registered actor IDs."""
        ...

    def close(self) -> None:
        """Close the router and all mailboxes. Idempotent."""
        ...

    @property
    def is_closed(self) -> bool:
        """Public closed-state accessor.

        Replaces external reads of the impl-private ``_closed`` slot.
        """
        ...
