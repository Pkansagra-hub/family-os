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
    # Async-dispatch counters (Phase 6 / P6.5)
    mailbox_full_drops: int = 0
    mailbox_high_water_mark: int = 0
    async_handler_retries: int = 0
    async_handler_dlq: int = 0
    # M7.1 / B01: envelopes dropped because their TTL expired before delivery.
    ttl_drops: int = 0

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
            "mailbox_full_drops": self.mailbox_full_drops,
            "mailbox_high_water_mark": self.mailbox_high_water_mark,
            "async_handler_retries": self.async_handler_retries,
            "async_handler_dlq": self.async_handler_dlq,
            "ttl_drops": self.ttl_drops,
        }


# ---------------------------------------------------------------------------
# Async dispatch subscription wrapper (Phase 6 / P6.5)
# ---------------------------------------------------------------------------


class _AsyncSubscription:
    """
    Per-subscription bounded mailbox + worker thread for async dispatch.

    When ``LocalBus(async_dispatch=True)``, each subscription gets one
    of these.  The trie stores ``self.enqueue`` as the "handler"; the
    worker thread invokes the real user handler from a background
    drain loop.

    Slow or blocking handlers no longer stall publishers (M-1).  The
    bounded mailbox provides backpressure (M-2/M-8); when full,
    publish drops the envelope and increments ``mailbox_full_drops``.

    A future Phase 6 issue (P6.6/P6.7) extends this with retry policy
    and DLQ publishing.  For now the worker simply logs handler
    exceptions (matching the synchronous-dispatch contract).
    """

    __slots__ = (
        "subscription_id",
        "pattern",
        "handler",
        "mailbox",
        "_worker",
        "_running",
        "_inflight",
        "_inflight_lock",
        "_idle_event",
        "_bus_stats",
        "_retry_policy",
        "_dlq_callback",
    )

    def __init__(
        self,
        subscription_id: str,
        pattern: str,
        handler: BusHandler,
        capacity: int,
        bus_stats: BusStats,
        retry_policy: object | None = None,
        dlq_callback: object | None = None,
    ) -> None:
        # Late import to avoid circular dependency at module load time
        from k1.bus.impl.local_mailbox import LocalMailbox
        from k1.bus.ports.mailbox import MailboxConfig

        self.subscription_id = subscription_id
        self.pattern = pattern
        self.handler = handler
        self.mailbox = LocalMailbox(
            actor_id=f"sub:{subscription_id}",
            config=MailboxConfig(capacity=capacity, priority_wfq=True),
        )
        self._running = True
        # Single counter covers both queued and currently-running envelopes.
        # Incremented at enqueue (publisher thread), decremented after handler
        # completion (worker thread).  Eliminates the dequeue/active race that
        # could let ``is_idle()`` flap to True between mailbox.pop and the
        # handler invocation.
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._idle_event = threading.Event()
        self._idle_event.set()
        self._bus_stats = bus_stats
        self._retry_policy = retry_policy
        self._dlq_callback = dlq_callback

        self._worker = threading.Thread(
            target=self._drain_loop,
            name=f"bus-sub-{subscription_id[:12]}",
            daemon=True,
        )
        self._worker.start()

    def enqueue(self, envelope: Envelope) -> None:
        """
        Publisher-side enqueue.  Called from `LocalBus._dispatch_async`.

        On backpressure, increments the bus-level drop counter and
        logs at WARNING level.  Never raises.
        """
        from k1.bus.ports.mailbox import BackpressureError

        # Reserve a slot in the inflight counter BEFORE delivery so that
        # ``is_idle()`` cannot return True between the publisher returning
        # and the worker thread starting to process.
        with self._inflight_lock:
            self._inflight += 1
            self._idle_event.clear()
        try:
            self.mailbox._deliver(envelope)
            depth = self.mailbox.pending()
            if depth > self._bus_stats.mailbox_high_water_mark:
                self._bus_stats.mailbox_high_water_mark = depth
        except BackpressureError as bp_err:
            self._bus_stats.mailbox_full_drops += 1
            self._dec_inflight()
            logger.warning(
                "Bus mailbox full for subscription=%s pattern=%s "
                "topic=%s envelope_id=%d -- dropping envelope",
                self.subscription_id,
                self.pattern,
                envelope.topic,
                envelope.envelope_id,
            )
            # M7.2 / B04: route backpressure drops through the DLQ
            # callback when configured.  Use ``attempts=0`` to signal
            # "never attempted" (distinct from retry-exhaustion which
            # uses ``attempts >= 1``).
            if self._dlq_callback is not None:
                try:
                    self._dlq_callback(envelope, bp_err, 0)  # type: ignore[operator]
                except Exception:
                    logger.exception(
                        "DLQ callback failed for backpressure-dropped " "envelope_id=%d topic=%s",
                        envelope.envelope_id,
                        envelope.topic,
                    )
        except ValueError:
            # Mailbox closed during teardown; silently drop
            self._dec_inflight()

    def _dec_inflight(self) -> None:
        with self._inflight_lock:
            self._inflight -= 1
            if self._inflight <= 0:
                self._inflight = 0
                self._idle_event.set()

    def _drain_loop(self) -> None:
        """Worker thread loop: pull envelopes and invoke handler."""
        while self._running:
            envelope = self.mailbox.receive(timeout_ms=100)
            if envelope is None:
                continue
            try:
                self._invoke_handler(envelope)
            finally:
                self._dec_inflight()

        # Drain anything left in the mailbox after shutdown signal
        while True:
            envelope = self.mailbox.receive(timeout_ms=0)
            if envelope is None:
                break
            try:
                self._invoke_handler(envelope)
            finally:
                self._dec_inflight()

    def _invoke_handler(self, envelope: Envelope) -> None:
        """
        Invoke the user handler with retry + DLQ semantics.

        Phase 6 / P6.6: per-topic ``RetryPolicy`` is consulted via the
        injected ``_retry_policy`` resolver.  Default = no retry, matching
        the synchronous-dispatch contract.

        M7.1 / B01: TTL enforcement.  If the envelope's ``ttl_ms`` window
        has elapsed since publish (``created_ns`` stamp), drop it without
        invoking the handler.  TTL drops route to the DLQ callback (if
        configured) so consumers can observe expired traffic, and
        increment ``BusStats.ttl_drops``.
        """
        from k1.bus.ports.mailbox import TtlExpiredError

        if envelope.ttl_ms > 0:
            age_ms = (time.monotonic_ns() - envelope.created_ns) // 1_000_000
            if age_ms >= envelope.ttl_ms:
                self._bus_stats.ttl_drops += 1
                logger.debug(
                    "TTL expired (async) topic=%s envelope_id=%d sub=%s "
                    "age_ms=%d ttl_ms=%d -- dropping envelope",
                    envelope.topic,
                    envelope.envelope_id,
                    self.subscription_id,
                    age_ms,
                    envelope.ttl_ms,
                )
                if self._dlq_callback is not None:
                    try:
                        self._dlq_callback(  # type: ignore[operator]
                            envelope,
                            TtlExpiredError(
                                envelope.envelope_id,
                                envelope.topic,
                                age_ms,
                                envelope.ttl_ms,
                            ),
                            0,
                        )
                    except Exception:
                        logger.exception(
                            "DLQ callback failed for ttl-expired envelope_id=%d topic=%s",
                            envelope.envelope_id,
                            envelope.topic,
                        )
                return

        # Phase 6 / P6.7: on retry exhaustion, hand off to the DLQ
        # callback if configured, otherwise log at ERROR level.
        attempts = 1
        max_attempts = 1
        policy = None
        if self._retry_policy is not None:
            try:
                policy = self._retry_policy(envelope.topic)  # type: ignore[operator]
            except Exception:
                policy = None
        if policy is not None:
            max_attempts = max(1, int(getattr(policy, "max_attempts", 0)) + 1)

        last_exc: BaseException | None = None
        while attempts <= max_attempts:
            try:
                self.handler(envelope)
                self._bus_stats.envelopes_delivered += 1
                return
            except Exception as exc:
                last_exc = exc
                self._bus_stats.handler_errors += 1
                if attempts < max_attempts and policy is not None:
                    self._bus_stats.async_handler_retries += 1
                    delay_ms = _compute_retry_delay_ms(policy, attempts)
                    logger.warning(
                        "Bus handler error (attempt %d/%d) for topic=%s "
                        "envelope_id=%d sub=%s -- retrying in %dms",
                        attempts,
                        max_attempts,
                        envelope.topic,
                        envelope.envelope_id,
                        self.subscription_id,
                        delay_ms,
                    )
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)
                    attempts += 1
                    continue
                # Exhausted (or no retry configured)
                logger.exception(
                    "Bus handler error for topic=%s envelope_id=%d sub=%s "
                    "(attempt %d/%d) -- exception swallowed",
                    envelope.topic,
                    envelope.envelope_id,
                    self.subscription_id,
                    attempts,
                    max_attempts,
                )
                break

        # Retry exhausted: hand off to DLQ if configured
        if self._dlq_callback is not None and last_exc is not None:
            self._bus_stats.async_handler_dlq += 1
            try:
                self._dlq_callback(envelope, last_exc, attempts)  # type: ignore[operator]
            except Exception:
                logger.exception(
                    "DLQ callback failed for envelope_id=%d topic=%s",
                    envelope.envelope_id,
                    envelope.topic,
                )

    def is_idle(self) -> bool:
        """True if no envelopes are queued or in-flight."""
        with self._inflight_lock:
            return self._inflight == 0

    def wait_idle(self, timeout_s: float) -> bool:
        """Block up to ``timeout_s`` for this subscription to drain."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_idle():
                return True
            self._idle_event.wait(timeout=0.05)
        return self.is_idle()

    def shutdown(self, *, join_timeout_s: float = 1.0) -> None:
        """Stop accepting work, drain remaining envelopes, join the worker."""
        self._running = False
        self.mailbox.close()
        self._worker.join(timeout=join_timeout_s)


def _compute_retry_delay_ms(policy: object, attempt: int) -> int:
    """Compute the delay before the next retry attempt."""
    base_ms = int(getattr(policy, "base_ms", 100))
    backoff = str(getattr(policy, "backoff", "exponential"))
    jitter = bool(getattr(policy, "jitter", True))
    if backoff == "exponential":
        delay = base_ms * (2 ** (attempt - 1))
    else:  # fixed
        delay = base_ms
    if jitter:
        # Bounded uniform jitter +/- 25%
        import random

        delay = int(delay * random.uniform(0.75, 1.25))
    # Cap at 10 seconds to avoid pathological backoff
    return max(0, min(delay, 10_000))


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
        "_async_dispatch",
        "_async_capacity",
        "_async_subs",
        "_async_subs_lock",
        "_retry_resolver",
        "_dlq_callback",
        "_outbox",
        "_durable_topics",
        "_durable_consumers",
        "_durable_consumers_lock",
        # Diagnostics: sub_id -> (pattern, original_handler).
        # Written by subscribe(); read by list_subscriptions() probes only.
        "_sub_patterns",
    )

    def __init__(
        self,
        *,
        capture: bool = False,
        timing_chain: TimingChain | None = None,
        middleware: MiddlewareChain | None = None,
        async_dispatch: bool = False,
        subscription_mailbox_capacity: int = 1024,
        retry_resolver: object | None = None,
        dlq_callback: object | None = None,
        outbox: object | None = None,
        durable_topics: set[str] | None = None,
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
            async_dispatch:
                Phase 6 / P6.5.  When True, each subscription gets a bounded
                ``LocalMailbox`` and a worker thread; publish enqueues to all
                matching mailboxes and returns immediately.  Slow handlers no
                longer stall publishers.  When False (default), dispatch is
                synchronous on the publisher's thread (legacy behavior).
                Tests that publish then immediately assert handler side-effects
                must call ``bus.flush()`` first when async_dispatch is True.
            subscription_mailbox_capacity:
                Per-subscription mailbox capacity when async_dispatch=True.
                Default 1024.  Beyond this depth, publish drops envelopes and
                increments ``stats.mailbox_full_drops``.
            retry_resolver:
                Phase 6 / P6.6.  Optional callable ``(topic: str) -> RetryPolicy | None``
                consulted by the async-dispatch worker when a handler raises.
                Returning None or omitting this argument preserves the legacy
                "log + drop" behavior.  Ignored when async_dispatch=False.
            dlq_callback:
                Phase 6 / P6.7.  Optional callable
                ``(envelope, exception, attempts) -> None`` invoked by the
                async-dispatch worker after retry exhaustion.  Used by the
                DLQ publisher.  Ignored when async_dispatch=False.
            outbox:
                Phase 6 / P6.13.  Optional ``BusOutbox`` instance.  When
                provided together with ``durable_topics``, every published
                envelope on a durable topic is appended to the outbox
                BEFORE dispatch, and durable subscribers (those that pass
                ``consumer_id=`` to ``subscribe``) ack envelopes after
                their handler returns successfully.
            durable_topics:
                Phase 6 / P6.13.  Set of exact topic strings whose
                envelopes must be persisted to ``outbox`` before
                dispatch.  Topics not listed here behave as before
                (RAM-only).  Ignored when ``outbox`` is None.
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
        self._async_dispatch = async_dispatch
        self._async_capacity = subscription_mailbox_capacity
        self._async_subs: dict[str, _AsyncSubscription] = {}
        self._async_subs_lock = threading.Lock()
        self._retry_resolver = retry_resolver
        self._dlq_callback = dlq_callback
        # P6.13 durability state
        self._outbox = outbox
        self._durable_topics: set[str] = set(durable_topics) if durable_topics else set()
        # consumer_id -> list of (topic_pattern, raw_handler)
        self._durable_consumers: dict[str, list[tuple[str, BusHandler]]] = {}
        self._durable_consumers_lock = threading.Lock()
        # Diagnostics: sub_id -> (pattern, original_handler) for list_subscriptions().
        self._sub_patterns: dict[str, tuple[str, BusHandler]] = {}

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

        # Stamp bus-assigned fields (Phase 1: id + created_ns).
        # Sequence is deferred until AFTER middleware so that
        # middleware-dropped envelopes do not consume a sequence number
        # (which would create gaps for STRICT-mode timing chains).  See
        # M7.1.3 / B02.
        envelope_id = self._id_gen.next()
        created_ns = time.monotonic_ns()

        stamped = envelope.with_bus_fields(
            envelope_id=envelope_id,
            sequence=0,
            created_ns=created_ns,
        )

        # Track topics for stats
        if topic not in self._topics_seen:
            self._topics_seen.add(topic)
            self._stats.topics_seen = len(self._topics_seen)

        # Run middleware chain (after partial stamp, before sequence
        # allocation and dispatch).  Middleware sees envelope_id and
        # created_ns but sequence is a placeholder (0) until after
        # middleware confirms the envelope is not dropped.  None return
        # = drop the envelope; no sequence is consumed.
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

        # Phase 2: allocate sequence and re-stamp.  Only envelopes that
        # passed middleware consume a sequence number, ensuring a gap-free
        # monotonic per-topic sequence stream for downstream consumers.
        sequence = self._seq_gen.next(topic)
        stamped = stamped.with_bus_fields(
            envelope_id=stamped.envelope_id,
            sequence=sequence,
            created_ns=stamped.created_ns,
        )

        # P6.13: durability append BEFORE dispatch.  If a crash happens
        # between the outbox write and the handler invocation, replay
        # will redeliver on next startup (at-least-once for durable topics).
        # NOTE: append is now after middleware so that middleware-rejected
        # envelopes are not durably stored (they would otherwise be
        # replayed on restart, defeating the middleware's drop decision).
        if self._outbox is not None and topic in self._durable_topics:
            try:
                self._outbox.append(stamped)  # type: ignore[attr-defined]
            except Exception:
                logger.exception(
                    "Outbox append failed for topic=%s envelope_id=%d "
                    "-- continuing with in-memory dispatch only",
                    topic,
                    stamped.envelope_id,
                )

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
    # IBus.publish_batch
    # ------------------------------------------------------------------

    def publish_batch(self, envelopes: list[Envelope]) -> None:
        """
        Publish a batch of envelopes with shared trie-lock acquisition.

        M7.2 / B06: each envelope still goes through the full per-envelope
        pipeline (topic check, stamping, middleware, sequence allocation,
        outbox, capture, dispatch), but the subscriber-trie read lock is
        acquired ONCE for the whole batch instead of once per envelope.
        This benefits callers (e.g. ``SessionBusAdapter.emit_batch``) that
        publish many envelopes in tight succession.

        Empty batch is a no-op.  A per-envelope error (middleware drop,
        outbox failure, etc.) is contained to that envelope and does NOT
        abort the batch.

        When ``timing_chain`` is configured, envelopes are routed through
        it after the lock is released, identical to single ``publish``.
        """
        if not envelopes:
            return

        # Phase 1: stamp + middleware + sequence + outbox + capture for
        # each envelope, accumulating (stamped, dispatch_action) pairs.
        # Done OUTSIDE the trie lock since these steps don't touch
        # subscribers.
        pending: list[Envelope] = []
        for envelope in envelopes:
            topic = envelope.topic
            if not topic:
                logger.warning("LocalBus.publish_batch: empty topic, skipping envelope")
                continue

            envelope_id = self._id_gen.next()
            created_ns = time.monotonic_ns()
            stamped = envelope.with_bus_fields(
                envelope_id=envelope_id,
                sequence=0,
                created_ns=created_ns,
            )

            if topic not in self._topics_seen:
                self._topics_seen.add(topic)
                self._stats.topics_seen = len(self._topics_seen)

            # Middleware
            if self._middleware is not None:
                try:
                    result = self._middleware.process(stamped)
                except Exception:
                    logger.exception(
                        "Middleware chain error for topic=%s envelope_id=%d " "-- envelope dropped",
                        stamped.topic,
                        stamped.envelope_id,
                    )
                    continue
                if result is None:
                    continue
                stamped = result

            # Allocate sequence and re-stamp (only envelopes passing middleware)
            sequence = self._seq_gen.next(topic)
            stamped = stamped.with_bus_fields(
                envelope_id=stamped.envelope_id,
                sequence=sequence,
                created_ns=stamped.created_ns,
            )

            # Outbox (durable topics)
            if self._outbox is not None and topic in self._durable_topics:
                try:
                    self._outbox.append(stamped)  # type: ignore[attr-defined]
                except Exception:
                    logger.exception(
                        "Outbox append failed for topic=%s envelope_id=%d "
                        "-- continuing with in-memory dispatch only",
                        topic,
                        stamped.envelope_id,
                    )

            # Capture mode
            if self._capture:
                self._captured.append(stamped)

            self._stats.envelopes_published += 1
            pending.append(stamped)

        if not pending:
            return

        # Phase 2: match all topics under a SINGLE read-lock acquisition.
        matched: list[tuple[Envelope, list[BusHandler]]] = []
        self._rw_lock.acquire_read()
        try:
            for stamped in pending:
                matched.append((stamped, self._trie.match(stamped.topic)))
        finally:
            self._rw_lock.release_read()

        # Phase 3: dispatch outside the lock.
        if self._timing_chain is not None:

            def _dispatch_fn(env: Envelope) -> None:
                self._rw_lock.acquire_read()
                try:
                    child_handlers = self._trie.match(env.topic)
                finally:
                    self._rw_lock.release_read()
                self._dispatch(env, child_handlers)

            for stamped, _ in matched:
                self._timing_chain.process(stamped, _dispatch_fn)
        else:
            for stamped, handlers in matched:
                self._dispatch(stamped, handlers)

    # ------------------------------------------------------------------
    # IBus.subscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        pattern: str,
        handler: BusHandler,
        *,
        consumer_id: str | None = None,
    ) -> SubscriptionHandle:
        """
        Subscribe a handler to a topic pattern.

        Pattern syntax:
            "k1.capability.completed.v1"    -- exact match
            "k1.agent.*.delta.v1"           -- * matches one segment
            "k1.agent.>"                    -- > matches one or more trailing

        Thread-safe: takes WRITE lock on the trie (exclusive).

        Args:
            pattern:     Topic / pattern to subscribe to.
            handler:     User callback.
            consumer_id: Phase 6 / P6.13.  When the bus has an
                ``outbox`` configured and ``pattern`` matches a durable
                topic, supplying ``consumer_id`` opts in to at-least-once
                delivery: the bus auto-acks the consumer's last seen
                envelope_id on every successful handler return, and
                ``replay_durable_topics()`` re-emits any envelope whose
                id exceeds that watermark.  Without ``consumer_id``,
                durable topics behave at-most-once for this subscriber.

        Returns:
            SubscriptionHandle for later unsubscribe().
        """
        sub_id = f"sub-{uuid.uuid4().hex[:12]}"

        # Diagnostics: record original pattern + handler before any wrapping.
        self._sub_patterns[sub_id] = (pattern, handler)
        # wrap the user handler so successful invocations ack to the outbox.
        # The wrapper preserves exception propagation so retry/DLQ behavior
        # in the async path remains unchanged.
        effective_handler = handler
        if consumer_id is not None and self._outbox is not None:
            outbox = self._outbox
            cid = consumer_id

            def _acking_handler(env: Envelope, _user=handler, _cid=cid, _ob=outbox) -> None:
                _user(env)
                # Only acked on successful return -- exceptions skip ack.
                try:
                    _ob.ack(_cid, env.topic, env.envelope_id)  # type: ignore[attr-defined]
                except Exception:
                    logger.exception(
                        "Outbox ack failed for consumer=%s topic=%s envelope_id=%d",
                        _cid,
                        env.topic,
                        env.envelope_id,
                    )

            effective_handler = _acking_handler

            # Track for replay_durable_topics()
            with self._durable_consumers_lock:
                self._durable_consumers.setdefault(cid, []).append((pattern, _acking_handler))

        # Async-dispatch path: wrap handler in a per-sub mailbox + worker.
        # The trie sees the mailbox-enqueue closure as the "handler".
        if self._async_dispatch:
            async_sub = _AsyncSubscription(
                subscription_id=sub_id,
                pattern=pattern,
                handler=effective_handler,
                capacity=self._async_capacity,
                bus_stats=self._stats,
                retry_policy=self._retry_resolver,
                dlq_callback=self._dlq_callback,
            )
            with self._async_subs_lock:
                self._async_subs[sub_id] = async_sub
            trie_handler: BusHandler = async_sub.enqueue
        else:
            trie_handler = effective_handler

        self._rw_lock.acquire_write()
        try:
            self._trie.insert(pattern, trie_handler, sub_id)
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
            # Clean up diagnostics map.
            self._sub_patterns.pop(handle.subscription_id, None)
            # Shut down the async worker (if any) outside the trie lock.
            if self._async_dispatch:
                with self._async_subs_lock:
                    async_sub = self._async_subs.pop(handle.subscription_id, None)
                if async_sub is not None:
                    async_sub.shutdown()

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

        M7.1 / B01: enforce envelope TTL before invoking handlers.  Sync
        path drops silently (matching the sync error contract: log,
        increment counter, no DLQ).  Async path TTL enforcement lives
        in ``_AsyncSubscription._invoke_handler``.
        """
        if envelope.ttl_ms > 0:
            age_ms = (time.monotonic_ns() - envelope.created_ns) // 1_000_000
            if age_ms >= envelope.ttl_ms:
                self._stats.ttl_drops += 1
                logger.debug(
                    "TTL expired (sync) topic=%s envelope_id=%d age_ms=%d ttl_ms=%d",
                    envelope.topic,
                    envelope.envelope_id,
                    age_ms,
                    envelope.ttl_ms,
                )
                return
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

        When ``async_dispatch=True``, also shuts down all per-subscription
        worker threads after draining their mailboxes.
        """
        self._closed = True
        if self._async_dispatch:
            with self._async_subs_lock:
                subs = list(self._async_subs.values())
                self._async_subs.clear()
            for sub in subs:
                sub.shutdown()

    def flush(self, timeout_ms: int = 5000) -> bool:
        """
        Block until every per-subscription mailbox is drained AND no
        worker thread is mid-handler.

        For synchronous-dispatch buses (``async_dispatch=False``) this is
        a no-op and returns True immediately.

        For async-dispatch buses, walks the registered subscriptions and
        waits for each to become idle.  Returns False if the overall
        timeout is exceeded.

        Phase 6 / P6.5.
        """
        if not self._async_dispatch:
            return True

        # Snapshot subscriptions under lock; release before waiting so
        # subscribe/unsubscribe can proceed concurrently.
        with self._async_subs_lock:
            subs = list(self._async_subs.values())

        if not subs:
            return True

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        for sub in subs:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if not sub.wait_idle(remaining):
                return False
        return True

    @property
    def closed(self) -> bool:
        """True if the bus has been closed."""
        return self._closed

    @property
    def is_closed(self) -> bool:
        """Public alias of ``closed`` to satisfy ``IBus.is_closed``."""
        return self._closed

    # ------------------------------------------------------------------
    # Durability replay (P6.13)
    # ------------------------------------------------------------------

    def replay_durable_topics(self, *, consumer_id: str | None = None) -> int:
        """
        Replay un-acked envelopes from the outbox to durable subscribers.

        For each ``(consumer_id, pattern)`` registered via
        ``subscribe(..., consumer_id=...)``, this method walks the
        outbox for every durable topic that the pattern would match
        (currently exact-topic patterns only) and re-invokes the
        ack-wrapping handler with each envelope whose ``envelope_id``
        is greater than the consumer's last ack watermark.

        At-least-once semantics: handlers MUST be idempotent.  Use
        ``IdempotencyMiddleware`` (P6.12) on the publish side and
        application-level dedup on the consume side.

        Args:
            consumer_id: Optional filter -- replay only this consumer.
                If None, replay all registered durable consumers.

        Returns:
            Total number of envelopes replayed.
        """
        if self._outbox is None:
            return 0

        with self._durable_consumers_lock:
            if consumer_id is not None:
                items = [(consumer_id, list(self._durable_consumers.get(consumer_id, [])))]
            else:
                items = [(cid, list(subs)) for cid, subs in self._durable_consumers.items()]

        replayed = 0
        for cid, subs in items:
            for pattern, acking_handler in subs:
                # Only exact-topic durable replay is supported; wildcard
                # subscribers don't get replay (they'd need a topic-list
                # discovery mechanism out of scope here).
                if pattern not in self._durable_topics:
                    continue
                for record in self._outbox.unacked(cid, pattern):  # type: ignore[attr-defined]
                    envelope = record.to_envelope()
                    try:
                        acking_handler(envelope)
                        replayed += 1
                    except Exception:
                        logger.exception(
                            "Replay handler error consumer=%s topic=%s envelope_id=%d",
                            cid,
                            pattern,
                            record.envelope_id,
                        )
                        # Stop replay for this (consumer, topic) on error
                        # so we don't skip past unprocessed envelopes.
                        break
        return replayed

    @property
    def durable_topics(self) -> set[str]:
        """Read-only view of durable topic names."""
        return frozenset(self._durable_topics)  # type: ignore[return-value]

    @property
    def outbox(self) -> object | None:
        """The configured BusOutbox, if any (P6.13)."""
        return self._outbox

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

    def list_subscriptions(self) -> list[tuple[str, str]]:
        """Return a snapshot of all active subscriptions for diagnostics.

        Intended exclusively for SUBSCRIPTION-TOPOLOGY probes in
        ``tests/integration/k1/live/``.  Never call from production code.

        Returns:
            List of ``(pattern, handler_qualname)`` tuples, one per live
            subscription, in arbitrary order.
        """
        return [
            (pattern, getattr(h, "__qualname__", repr(h)))
            for pattern, h in self._sub_patterns.values()
        ]

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
