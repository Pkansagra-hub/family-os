"""
k1.bus.impl.local_mailbox -- Production-grade in-process IMailbox + IMailboxRouter.

Point-to-point actor messaging with bounded queues, WFQ priority within
each mailbox, and backpressure to sender.

Architecture:
    +-------------------+      +------------------+      +-----------+
    | Sender            | ---> | MailboxRouter    | ---> | Mailbox   |
    | (deliver(id,env)) |      | (actor registry) |      | (bounded) |
    +-------------------+      +------------------+      +-----------+
                                                          | WFQ Queue|
                                                          | URGENT   |
                                                          | REALTIME |
                                                          | INTERACT |
                                                          | BACKGRND |
                                                          +----------+

WFQ Priority:
    When priority_wfq=True, the mailbox maintains 4 sub-queues (one per
    Priority level).  On receive(), it picks from the highest-priority
    non-empty queue (strict priority -- simpler than weighted round-robin
    for V1, and correct for our latency targets).

    V1 is STRICT priority (not weighted round-robin):
        URGENT always drained before REALTIME, REALTIME before INTERACTIVE, etc.
    This matches the latency targets: URGENT <5ms, BACKGROUND <500ms.

    V2 (future): true weighted fair queueing with configurable weights
    to prevent BACKGROUND starvation under sustained URGENT load.

    When priority_wfq=False, a single FIFO queue is used regardless of
    envelope priority level.

Backpressure:
    Each mailbox has a bounded capacity.  When full, deliver() raises
    BackpressureError.  The sender must decide: retry, drop, or escalate.

Thread safety:
    - LocalMailboxRouter: RLock on the actor registry (register/unregister
      vs deliver happen from different threads).
    - LocalMailbox: Condition variable for blocking receive() + mutex
      protecting the internal queues.

Lifecycle:
    - close() on a mailbox prevents new deliveries but allows draining.
    - unregister() on the router closes the mailbox and removes it.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Optional

from k1.bus.envelope import Envelope, Priority
from k1.bus.ports.mailbox import BackpressureError, MailboxConfig, UnknownActorError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LocalMailbox -- single actor inbox with optional WFQ priority
# ---------------------------------------------------------------------------


class LocalMailbox:
    """
    Bounded, optionally priority-sorted mailbox for a single actor.

    When priority_wfq=True, maintains 4 sub-queues (URGENT, REALTIME,
    INTERACTIVE, BACKGROUND).  receive() returns from highest-priority
    non-empty queue first (strict priority scheduling V1).

    When priority_wfq=False, uses a single FIFO queue.

    Thread-safe: Condition variable for blocking receive, mutex for
    queue operations.  Supports concurrent deliver + receive.
    """

    __slots__ = (
        "_actor_id",
        "_capacity",
        "_priority_wfq",
        "_queues",
        "_single_queue",
        "_size",
        "_lock",
        "_not_empty",
        "_closed",
        "_delivered_count",
        "_received_count",
    )

    # Priority levels in dequeue order (highest first)
    _PRIORITY_ORDER = (
        Priority.URGENT,
        Priority.REALTIME,
        Priority.INTERACTIVE,
        Priority.BACKGROUND,
    )

    def __init__(self, actor_id: str, config: MailboxConfig) -> None:
        self._actor_id = actor_id
        self._capacity = config.capacity
        self._priority_wfq = config.priority_wfq
        self._size = 0
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._closed = False
        self._delivered_count = 0
        self._received_count = 0

        if self._priority_wfq:
            # 4 sub-queues indexed by Priority value (0-3)
            self._queues: list[deque[Envelope]] = [deque() for _ in range(4)]
            self._single_queue: Optional[deque[Envelope]] = None
        else:
            self._queues = []
            self._single_queue = deque()

    # ------------------------------------------------------------------
    # IMailbox interface
    # ------------------------------------------------------------------

    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]:
        """
        Receive the next envelope from this mailbox.

        Priority order (when WFQ enabled):
            URGENT > REALTIME > INTERACTIVE > BACKGROUND

        Args:
            timeout_ms: 0 = non-blocking.  >0 = block up to timeout_ms ms.

        Returns:
            Next Envelope, or None if empty/timeout.
        """
        with self._not_empty:
            envelope = self._try_dequeue()
            if envelope is not None:
                return envelope

            if timeout_ms <= 0:
                return None

            # Block until data arrives or timeout
            timeout_sec = timeout_ms / 1000.0
            self._not_empty.wait(timeout=timeout_sec)
            return self._try_dequeue()

    def pending(self) -> int:
        """Number of envelopes waiting in this mailbox."""
        with self._lock:
            return self._size

    # ------------------------------------------------------------------
    # Internal: delivery (called by router)
    # ------------------------------------------------------------------

    def _deliver(self, envelope: Envelope) -> None:
        """
        Enqueue an envelope into the mailbox.

        Raises:
            BackpressureError: Mailbox is at capacity.
            ValueError:        Mailbox is closed.
        """
        with self._not_empty:
            if self._closed:
                raise ValueError(f"Mailbox for actor '{self._actor_id}' is closed")

            if self._size >= self._capacity:
                raise BackpressureError(self._actor_id, self._capacity)

            if self._priority_wfq:
                # Route to appropriate priority sub-queue
                priority_val = envelope.priority
                if priority_val < 0 or priority_val > 3:
                    priority_val = Priority.INTERACTIVE
                self._queues[priority_val].append(envelope)
            else:
                assert self._single_queue is not None
                self._single_queue.append(envelope)

            self._size += 1
            self._delivered_count += 1
            self._not_empty.notify()

    def _try_dequeue(self) -> Optional[Envelope]:
        """
        Try to dequeue one envelope.  Must be called under self._lock.

        When WFQ: strict priority -- pick from highest-priority non-empty queue.
        When FIFO: pick from the single queue.
        """
        if self._size == 0:
            return None

        if self._priority_wfq:
            for priority in self._PRIORITY_ORDER:
                q = self._queues[priority.value]
                if q:
                    envelope = q.popleft()
                    self._size -= 1
                    self._received_count += 1
                    return envelope
            return None  # Should not happen if _size > 0
        else:
            assert self._single_queue is not None
            if self._single_queue:
                envelope = self._single_queue.popleft()
                self._size -= 1
                self._received_count += 1
                return envelope
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        Close the mailbox.  Prevents new deliveries.

        Existing envelopes can still be drained via receive().
        """
        with self._lock:
            self._closed = True

    @property
    def closed(self) -> bool:
        """True if the mailbox has been closed."""
        return self._closed

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def actor_id(self) -> str:
        """The actor this mailbox belongs to."""
        return self._actor_id

    @property
    def capacity(self) -> int:
        """Maximum queue capacity."""
        return self._capacity

    @property
    def delivered_count(self) -> int:
        """Total envelopes delivered to this mailbox (lifetime)."""
        return self._delivered_count

    @property
    def received_count(self) -> int:
        """Total envelopes received (dequeued) from this mailbox (lifetime)."""
        return self._received_count

    def depth_by_priority(self) -> dict[str, int]:
        """
        Current queue depth per priority level.

        Returns empty dict {} if WFQ is disabled (single FIFO mode).
        """
        if not self._priority_wfq:
            return {}
        with self._lock:
            return {p.name: len(self._queues[p.value]) for p in self._PRIORITY_ORDER}

    def __repr__(self) -> str:
        mode = "WFQ" if self._priority_wfq else "FIFO"
        return (
            f"LocalMailbox(actor={self._actor_id!r}, "
            f"pending={self._size}/{self._capacity}, "
            f"mode={mode})"
        )


# ---------------------------------------------------------------------------
# LocalMailboxRouter -- actor registry + delivery dispatch
# ---------------------------------------------------------------------------


class LocalMailboxRouter:
    """
    In-process IMailboxRouter implementation.

    Maintains a thread-safe registry of actor_id -> LocalMailbox mappings.
    Provides point-to-point delivery with backpressure.

    Usage::

        router = LocalMailboxRouter()
        mailbox = router.register("orchestrator", MailboxConfig(capacity=50))
        router.deliver("orchestrator", envelope)
        env = mailbox.receive(timeout_ms=100)

    Thread-safe: RLock on the actor registry.  Delivery to a specific
    mailbox releases the registry lock before calling mailbox._deliver(),
    so concurrent delivers to different actors don't block each other.
    """

    __slots__ = ("_mailboxes", "_lock", "_closed")

    def __init__(self) -> None:
        self._mailboxes: dict[str, LocalMailbox] = {}
        self._lock = threading.RLock()
        self._closed = False

    # ------------------------------------------------------------------
    # IMailboxRouter interface
    # ------------------------------------------------------------------

    def deliver(self, actor_id: str, envelope: Envelope) -> None:
        """
        Deliver an envelope to a specific actor's mailbox.

        Thread-safe: acquires registry lock to look up the mailbox,
        then releases it before the actual enqueue (minimizing lock
        hold time).

        Raises:
            UnknownActorError:  actor_id not registered.
            BackpressureError:  actor's mailbox is full.
            ValueError:         Router or mailbox is closed.
        """
        if self._closed:
            raise ValueError("MailboxRouter is closed")

        with self._lock:
            mailbox = self._mailboxes.get(actor_id)
            if mailbox is None:
                raise UnknownActorError(actor_id)

        # Deliver outside the registry lock (mailbox has its own lock)
        mailbox._deliver(envelope)

    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> LocalMailbox:
        """
        Register an actor and create its mailbox.

        Args:
            actor_id: Unique actor identifier.  Must not be empty.
            config:   Mailbox configuration.  None = defaults.

        Returns:
            The LocalMailbox the actor will receive from.

        Raises:
            ValueError: actor_id empty or already registered, or router closed.
        """
        if not actor_id:
            raise ValueError("actor_id must not be empty")

        if self._closed:
            raise ValueError("MailboxRouter is closed")

        effective_config = config or MailboxConfig()

        with self._lock:
            if actor_id in self._mailboxes:
                raise ValueError(f"Actor '{actor_id}' is already registered")

            mailbox = LocalMailbox(actor_id, effective_config)
            self._mailboxes[actor_id] = mailbox

            logger.debug(
                "Registered mailbox: actor=%s capacity=%d wfq=%s",
                actor_id,
                effective_config.capacity,
                effective_config.priority_wfq,
            )

            return mailbox

    def unregister(self, actor_id: str) -> bool:
        """
        Remove an actor and close its mailbox.

        Pending envelopes in the mailbox are available for draining
        after close, but no new deliveries will be accepted.

        Returns:
            True if the actor was found and removed, False otherwise.
        """
        with self._lock:
            mailbox = self._mailboxes.pop(actor_id, None)

        if mailbox is None:
            return False

        mailbox.close()
        logger.debug("Unregistered mailbox: actor=%s", actor_id)
        return True

    def registered_actors(self) -> list[str]:
        """Return the list of currently registered actor IDs."""
        with self._lock:
            return list(self._mailboxes.keys())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        Close the router and all mailboxes.

        Prevents new registrations and deliveries.  Existing mailboxes
        are closed (drainable but no new deliveries).
        """
        with self._lock:
            self._closed = True
            for mailbox in self._mailboxes.values():
                mailbox.close()

    @property
    def closed(self) -> bool:
        """True if the router has been closed."""
        return self._closed

    @property
    def is_closed(self) -> bool:
        """Public alias of ``closed`` to satisfy ``IMailboxRouter.is_closed``."""
        return self._closed

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def actor_count(self) -> int:
        """Number of registered actors."""
        with self._lock:
            return len(self._mailboxes)

    def mailbox_for(self, actor_id: str) -> Optional[LocalMailbox]:
        """
        Get the mailbox for an actor (for observability/testing).

        Returns None if actor is not registered.
        """
        with self._lock:
            return self._mailboxes.get(actor_id)

    def stats_snapshot(self) -> dict[str, dict[str, int]]:
        """
        Return per-actor stats snapshot.

        Returns:
            {actor_id: {"pending": N, "delivered": N, "received": N, "capacity": N}}
        """
        with self._lock:
            mailboxes = list(self._mailboxes.items())

        return {
            actor_id: {
                "pending": mb.pending(),
                "delivered": mb.delivered_count,
                "received": mb.received_count,
                "capacity": mb.capacity,
            }
            for actor_id, mb in mailboxes
        }

    def __repr__(self) -> str:
        return f"LocalMailboxRouter(actors={self.actor_count}, " f"closed={self._closed})"
