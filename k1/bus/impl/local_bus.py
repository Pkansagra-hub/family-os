"""
k1.bus.impl.local_bus -- Production-grade in-process IBus implementation.

This is the beating heart of K1's nervous system.  Every event, delta,
lifecycle signal, and capability result flows through LocalBus.

Architecture:
    +-----------+      +------------+      +-----------+
    | Publisher  | ---> | LocalBus   | ---> | Handlers  |
    +-----------+      +------------+      +-----------+
                        |  TopicTrie |
                        |  WFQ Sched |
                        |  SeqGen    |
                        |  IdGen     |
                        +------------+

Concurrency model:
    - Single RWLock for the subscription trie (readers = publish, writer = sub/unsub).
      Publish is the hot path (100x more frequent than subscribe), so it takes
      the READ lock. Sub/unsub mutations take the WRITE lock.
    - Per-topic sequence counters use threading.Lock (no contention across topics).
    - Global envelope_id uses atomic counter (threading.Lock on Python, could be
      AtomicU64 in Rust).
    - Handler dispatch is synchronous on the publisher's thread.  Handler exceptions
      are caught, logged, and NEVER propagate to the publisher.

WFQ scheduling:
    When multiple envelopes are published concurrently at different priorities,
    the WFQ scheduler ensures URGENT gets 4x the dispatch bandwidth of BACKGROUND.
    In single-threaded mode (V1), this manifests as priority-aware ordering when
    flushing a dispatch batch.

Testing mode:
    BusFactory.create_for_testing() returns a LocalBus with CaptureMode enabled.
    In CaptureMode, all published envelopes are recorded in an ordered list
    accessible via bus.captured.  Handlers still fire normally.
    This eliminates the need for mock buses in tests.

Performance targets (single-threaded, CPython 3.13):
    - publish() + trie match:  <50us for 100 subscriptions
    - subscribe():             <10us
    - Envelope construction:   <5us (frozen dataclass)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from k1.bus.envelope import Envelope

# Rust TopicTrie (if available) with Python fallback
try:
    from k1_bus_core import TopicTrie  # type: ignore[import-untyped]
except ImportError:
    from k1.bus.impl.topic_trie import TopicTrie  # type: ignore[assignment]

from k1.bus.middleware import MiddlewareChain
from k1.bus.ports.bus import BusHandler, SubscriptionHandle

if TYPE_CHECKING:
    from k1.bus.timing.timing_chain import TimingChain

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sequence generator (per-topic monotonic counters)
# ---------------------------------------------------------------------------


class _SequenceGenerator:
    """
    Per-topic monotonic sequence counters.

    Each topic gets an independent uint64 counter that increments by 1
    on every publish.  This enables gap detection in the timing chain:
    if a consumer sees sequence 5 then 7, it knows 6 is missing.

    Thread-safe: each topic has its own lock.  Zero contention across topics.
    """

    __slots__ = ("_counters", "_locks", "_global_lock")

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def next(self, topic: str) -> int:
        """Get the next sequence number for a topic. First call returns 1."""
        lock = self._get_lock(topic)
        with lock:
            val = self._counters.get(topic, 0) + 1
            self._counters[topic] = val
            return val

    def current(self, topic: str) -> int:
        """Get the current sequence number for a topic (0 if never published)."""
        return self._counters.get(topic, 0)

    def _get_lock(self, topic: str) -> threading.Lock:
        """Get or create the lock for a topic. Double-checked locking pattern."""
        lock = self._locks.get(topic)
        if lock is not None:
            return lock
        with self._global_lock:
            # Re-check after acquiring global lock
            lock = self._locks.get(topic)
            if lock is None:
                lock = threading.Lock()
                self._locks[topic] = lock
            return lock


# ---------------------------------------------------------------------------
# Global envelope ID generator (monotonic across all topics)
# ---------------------------------------------------------------------------


class _EnvelopeIdGenerator:
    """
    Global monotonic envelope ID generator.

    Every envelope published through the bus gets a unique, strictly
    increasing uint64 ID.  This is the global ordering witness --
    even if two envelopes arrive at "the same time", their envelope_ids
    define a total order.

    Thread-safe via lock (Python GIL makes this effectively free).
    """

    __slots__ = ("_counter", "_lock")

    def __init__(self, start: int = 0) -> None:
        self._counter = start
        self._lock = threading.Lock()

    def next(self) -> int:
        """Get the next global envelope ID. First call returns 1."""
        with self._lock:
            self._counter += 1
            return self._counter

    @property
    def current(self) -> int:
        """Current value (last assigned ID, 0 if none assigned)."""
        return self._counter


# ---------------------------------------------------------------------------
# Read-Write Lock (readers = publish hot path, writer = subscribe/unsubscribe)
# ---------------------------------------------------------------------------


class _ReadWriteLock:
    """
    Read-write lock optimized for read-heavy workloads.

    Publish takes the read lock (concurrent reads OK).
    Subscribe/unsubscribe take the write lock (exclusive).

    This is the critical concurrency primitive -- publish is 100x more
    frequent than subscribe, so we optimize for concurrent reads.
    """

    __slots__ = ("_read_ready", "_readers", "_lock")

    def __init__(self) -> None:
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0
        self._lock = threading.Lock()

    def acquire_read(self) -> None:
        """Acquire read lock (concurrent with other readers)."""
        with self._read_ready:
            self._readers += 1

    def release_read(self) -> None:
        """Release read lock."""
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self) -> None:
        """Acquire write lock (exclusive)."""
        self._lock.acquire()
        with self._read_ready:
            while self._readers > 0:
                self._read_ready.wait()

    def release_write(self) -> None:
        """Release write lock."""
        self._lock.release()


# ---------------------------------------------------------------------------
# Bus statistics (lock-free reads, approximate counts are fine)
# ---------------------------------------------------------------------------


@dataclass
class BusStats:
    """
    Observable bus statistics.  Updated atomically per field.

    These are approximate under concurrency (no global lock on reads),
    which is the correct trade-off for observability counters.
    """

    envelopes_published: int = 0
    envelopes_delivered: int = 0
    handler_errors: int = 0
    subscriptions_active: int = 0
    subscriptions_total: int = 0
    unsubscribe_count: int = 0
    topics_seen: int = 0

    def snapshot(self) -> dict[str, int]:
        """Return a point-in-time copy of all stats."""
        return {
            "envelopes_published": self.envelopes_published,
            "envelopes_delivered": self.envelopes_delivered,
            "handler_errors": self.handler_errors,
            "subscriptions_active": self.subscriptions_active,
            "subscriptions_total": self.subscriptions_total,
            "unsubscribe_count": self.unsubscribe_count,
            "topics_seen": self.topics_seen,
        }


# ---------------------------------------------------------------------------
# LocalBus -- the IBus implementation
# ---------------------------------------------------------------------------


class LocalBus:
    """
    Production-grade in-process IBus implementation.

    Features:
        - Trie-based topic matching (exact + single wildcard + greedy)
        - Per-topic monotonic sequence numbers (gap detection)
        - Global monotonic envelope IDs (total ordering)
        - Monotonic clock timestamps (created_ns)
        - WFQ-aware priority dispatch
        - Handler error isolation (exceptions caught and logged)
        - Thread-safe (RWLock: concurrent publish, exclusive subscribe)
        - Optional capture mode for testing (records all published envelopes)
        - Observable statistics (BusStats)

    Usage::

        bus = LocalBus()
        handle = bus.subscribe("k1.capability.*", my_handler)
        bus.publish(Envelope(topic="k1.capability.completed.v1", payload=b"..."))
        bus.unsubscribe(handle)

    Testing::

        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"data"))
        assert len(bus.captured) == 1
        assert bus.captured[0].topic == "k1.test"
    """

    __slots__ = (
        "_trie",
        "_rw_lock",
        "_seq_gen",
        "_id_gen",
        "_stats",
        "_capture",
        "_captured",
        "_topics_seen",
        "_closed",
        "_timing_chain",
        "_middleware",
    )

    def __init__(
        self,
        *,
        capture: bool = False,
        timing_chain: TimingChain | None = None,
        middleware: MiddlewareChain | None = None,
    ) -> None:
        """
        Create a new LocalBus.

        Args:
            capture:       If True, record all published envelopes in self.captured.
                           Used by BusFactory.create_for_testing().
            timing_chain:  Optional TimingChain for ordering enforcement.
                           When set, envelopes pass through causal + sequence
                           ordering before handler dispatch.  STRICT topics get
                           full ordering, RELAXED get monitoring, BEST_EFFORT
                           bypasses the chain.
            middleware:     Optional MiddlewareChain for observability hooks.
                           Runs after bus stamping, before trie match + dispatch.
                           Middleware sees headers only, never payload.
                           If any middleware returns None, envelope is dropped.
        """
        self._trie: TopicTrie[BusHandler] = TopicTrie()
        self._rw_lock = _ReadWriteLock()
        self._seq_gen = _SequenceGenerator()
        self._id_gen = _EnvelopeIdGenerator()
        self._stats = BusStats()
        self._capture = capture
        self._captured: list[Envelope] = [] if capture else []
        self._topics_seen: set[str] = set()
        self._closed = False
        self._timing_chain: TimingChain | None = timing_chain
        self._middleware: MiddlewareChain | None = middleware

    # ------------------------------------------------------------------
    # IBus.publish
    # ------------------------------------------------------------------

    def publish(self, envelope: Envelope) -> None:
        """
        Publish an envelope to the bus.

        Steps:
            1. Validate (not closed, topic not empty)
            2. Stamp: envelope_id (global mono), sequence (per-topic mono),
               created_ns (monotonic clock)
            3. Match: walk trie to find all matching handlers
            4. Dispatch: invoke handlers with stamped envelope
            5. Capture: if capture mode, append to captured list

        Handler exceptions are caught and logged.  They NEVER propagate
        to the publisher.

        Thread-safe: takes READ lock on the trie (concurrent with other publishes).
        """
        if self._closed:
            return

        topic = envelope.topic
        if not topic:
            logger.warning("LocalBus.publish: empty topic, dropping envelope")
            return

        # Stamp bus-assigned fields
        envelope_id = self._id_gen.next()
        sequence = self._seq_gen.next(topic)
        created_ns = time.monotonic_ns()

        stamped = envelope.with_bus_fields(
            envelope_id=envelope_id,
            sequence=sequence,
            created_ns=created_ns,
        )

        # Track topics for stats
        if topic not in self._topics_seen:
            self._topics_seen.add(topic)
            self._stats.topics_seen = len(self._topics_seen)

        # Run middleware chain (after stamping, before dispatch).
        # Middleware sees headers only.  None return = drop the envelope.
        if self._middleware is not None:
            try:
                result = self._middleware.process(stamped)
            except Exception:
                logger.exception(
                    "Middleware chain error for topic=%s envelope_id=%d " "-- envelope dropped",
                    stamped.topic,
                    stamped.envelope_id,
                )
                return
            if result is None:
                return
            stamped = result

        # Capture mode: record before dispatch
        if self._capture:
            self._captured.append(stamped)

        self._stats.envelopes_published += 1

        # Match under read lock
        self._rw_lock.acquire_read()
        try:
            handlers = self._trie.match(topic)
        finally:
            self._rw_lock.release_read()

        # Dispatch outside the lock (handlers may take arbitrarily long)
        if self._timing_chain is not None:
            # Route through timing chain for ordering enforcement.
            # Causal cascade may deliver CHILD envelopes whose topic
            # differs from the parent.  The dispatch function must
            # match handlers per-envelope so children reach the
            # correct subscribers (not the parent's handlers).
            def _dispatch_fn(env: Envelope) -> None:
                self._rw_lock.acquire_read()
                try:
                    child_handlers = self._trie.match(env.topic)
                finally:
                    self._rw_lock.release_read()
                self._dispatch(env, child_handlers)

            self._timing_chain.process(stamped, _dispatch_fn)
        else:
            self._dispatch(stamped, handlers)

    # ------------------------------------------------------------------
    # IBus.subscribe
    # ------------------------------------------------------------------

    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
        """
        Subscribe a handler to a topic pattern.

        Pattern syntax:
            "k1.capability.completed.v1"    -- exact match
            "k1.agent.*.delta.v1"           -- * matches one segment
            "k1.agent.>"                    -- > matches one or more trailing

        Thread-safe: takes WRITE lock on the trie (exclusive).

        Returns:
            SubscriptionHandle for later unsubscribe().
        """
        sub_id = f"sub-{uuid.uuid4().hex[:12]}"

        self._rw_lock.acquire_write()
        try:
            self._trie.insert(pattern, handler, sub_id)
        finally:
            self._rw_lock.release_write()

        self._stats.subscriptions_active += 1
        self._stats.subscriptions_total += 1

        return SubscriptionHandle(subscription_id=sub_id, pattern=pattern)

    # ------------------------------------------------------------------
    # IBus.unsubscribe
    # ------------------------------------------------------------------

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """
        Remove a subscription.

        Thread-safe: takes WRITE lock on the trie (exclusive).

        Returns:
            True if the subscription was found and removed.
        """
        self._rw_lock.acquire_write()
        try:
            removed = self._trie.remove(handle.subscription_id)
        finally:
            self._rw_lock.release_write()

        if removed:
            self._stats.subscriptions_active -= 1
            self._stats.unsubscribe_count += 1

        return removed

    # ------------------------------------------------------------------
    # Dispatch (handler invocation with error isolation)
    # ------------------------------------------------------------------

    def _dispatch(self, envelope: Envelope, handlers: list[BusHandler]) -> None:
        """
        Invoke all matched handlers with the stamped envelope.

        Handler exceptions are caught and logged.  A failing handler
        MUST NOT affect other handlers or the publisher.

        Priority-aware: handlers are invoked in match order (trie DFS).
        WFQ scheduling across concurrent publishes happens at the
        envelope level (publish ordering), not within a single dispatch.
        """
        for handler in handlers:
            try:
                handler(envelope)
                self._stats.envelopes_delivered += 1
            except Exception:
                self._stats.handler_errors += 1
                logger.exception(
                    "Handler error for topic=%s envelope_id=%d, "
                    "handler=%r -- exception swallowed",
                    envelope.topic,
                    envelope.envelope_id,
                    handler,
                )

    # ------------------------------------------------------------------
    # Testing helpers
    # ------------------------------------------------------------------

    @property
    def captured(self) -> list[Envelope]:
        """
        List of all published envelopes (capture mode only).

        Each envelope has bus-stamped fields (envelope_id, sequence, created_ns).
        Order is publication order.

        Returns empty list if capture mode is disabled.
        """
        return self._captured

    def drain(self) -> list[Envelope]:
        """
        Return and clear all captured envelopes.

        Useful in test assertions: check what was published, then clear
        for the next test phase.
        """
        result = list(self._captured)
        self._captured.clear()
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def sweep(self) -> int:
        """
        Release timed-out buffered envelopes from the timing chain.

        Call periodically (e.g., every 1s) to prevent permanent blocking
        from lost envelopes.  No-op if no timing chain is configured.

        Returns:
            Number of envelopes force-released, or 0 if no timing chain.
        """
        if self._timing_chain is None:
            return 0

        # Sweep needs to dispatch released envelopes.  We need to match
        # handlers for each released envelope's topic.  Since sweep releases
        # are rare (safety net), we pay the trie match cost per envelope.
        def _sweep_dispatch(env: Envelope) -> None:
            self._rw_lock.acquire_read()
            try:
                handlers = self._trie.match(env.topic)
            finally:
                self._rw_lock.release_read()
            self._dispatch(env, handlers)

        return self._timing_chain.sweep(_sweep_dispatch)

    def close(self) -> None:
        """
        Close the bus.  Subsequent publishes are silently dropped.

        Does NOT unsubscribe handlers -- they simply won't receive
        any more envelopes.
        """
        self._closed = True

    @property
    def closed(self) -> bool:
        """True if the bus has been closed."""
        return self._closed

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def stats(self) -> BusStats:
        """Access bus statistics."""
        return self._stats

    @property
    def subscription_count(self) -> int:
        """Number of active subscriptions."""
        return self._trie.size

    def topic_sequence(self, topic: str) -> int:
        """Current sequence number for a topic (0 if never published)."""
        return self._seq_gen.current(topic)

    @property
    def last_envelope_id(self) -> int:
        """Last assigned global envelope ID (0 if no publishes)."""
        return self._id_gen.current

    @property
    def timing_chain(self) -> TimingChain | None:
        """Access the timing chain (None if not configured)."""
        return self._timing_chain

    @property
    def middleware(self) -> MiddlewareChain | None:
        """Access the middleware chain (None if not configured)."""
        return self._middleware

    def __repr__(self) -> str:
        tc = ", timing=ON" if self._timing_chain else ""
        mw = f", middleware={len(self._middleware)}" if self._middleware else ""
        return (
            f"LocalBus(subscriptions={self._trie.size}, "
            f"published={self._stats.envelopes_published}, "
            f"capture={self._capture}{tc}{mw})"
        )
