"""
Tests for k1.bus.impl.local_bus -- LocalBus, the IBus implementation.

Coverage targets:
    - Protocol compliance (isinstance IBus)
    - Publish/subscribe round-trip (exact and wildcard)
    - Bus-stamped fields (envelope_id, sequence, created_ns)
    - Global envelope_id monotonicity
    - Per-topic sequence monotonicity
    - Handler error isolation (exception swallowed, others still called)
    - Unsubscribe stops delivery
    - Capture mode (recording + drain)
    - Close prevents new publishes
    - Stats tracking
    - Empty topic dropped
    - BusFactory.create_local / create_for_testing
    - Thread safety under concurrent publish + subscribe
    - WFQ priority ordering under contention
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from k1.bus import BusFactory, Envelope, IBus, LocalBus, Priority, SubscriptionHandle

# ===================================================================
# Helpers
# ===================================================================


class _Collector:
    """Handler that records received envelopes."""

    def __init__(self) -> None:
        self.received: list[Envelope] = []
        self._lock = threading.Lock()

    def __call__(self, envelope: Envelope) -> None:
        with self._lock:
            self.received.append(envelope)

    def count(self) -> int:
        with self._lock:
            return len(self.received)


class _ErrorHandler:
    """Handler that raises on every call."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or RuntimeError("boom")
        self.call_count = 0

    def __call__(self, envelope: Envelope) -> None:
        self.call_count += 1
        raise self._error


# ===================================================================
# Protocol compliance
# ===================================================================


class TestProtocolCompliance:
    """LocalBus satisfies IBus protocol."""

    def test_isinstance_ibus(self) -> None:
        bus = LocalBus()
        assert isinstance(bus, IBus)

    def test_factory_produces_ibus(self) -> None:
        bus = BusFactory.create_local()
        assert isinstance(bus, IBus)

    def test_factory_testing_produces_ibus(self) -> None:
        bus = BusFactory.create_for_testing()
        assert isinstance(bus, IBus)


# ===================================================================
# Basic publish/subscribe
# ===================================================================


class TestPublishSubscribe:
    """Core publish/subscribe functionality."""

    def test_exact_match_delivery(self) -> None:
        bus = LocalBus()
        collector = _Collector()
        bus.subscribe("k1.test.event.v1", collector)
        bus.publish(Envelope(topic="k1.test.event.v1", payload=b"hello"))
        assert collector.count() == 1
        assert collector.received[0].payload == b"hello"
        assert collector.received[0].topic == "k1.test.event.v1"

    def test_wildcard_delivery(self) -> None:
        bus = LocalBus()
        collector = _Collector()
        bus.subscribe("k1.capability.*", collector)
        bus.publish(Envelope(topic="k1.capability.completed", payload=b"a"))
        bus.publish(Envelope(topic="k1.capability.failed", payload=b"b"))
        bus.publish(Envelope(topic="k1.other.event", payload=b"c"))
        assert collector.count() == 2

    def test_greedy_wildcard_delivery(self) -> None:
        bus = LocalBus()
        collector = _Collector()
        bus.subscribe("k1.agent.>", collector)
        bus.publish(Envelope(topic="k1.agent.abc.delta.v1", payload=b"d"))
        bus.publish(Envelope(topic="k1.agent.xyz", payload=b"e"))
        bus.publish(Envelope(topic="k1.session.update", payload=b"f"))
        assert collector.count() == 2

    def test_no_match_no_delivery(self) -> None:
        bus = LocalBus()
        collector = _Collector()
        bus.subscribe("k1.session.*", collector)
        bus.publish(Envelope(topic="k1.capability.completed", payload=b"x"))
        assert collector.count() == 0

    def test_multiple_subscribers_same_pattern(self) -> None:
        bus = LocalBus()
        c1, c2 = _Collector(), _Collector()
        bus.subscribe("k1.test", c1)
        bus.subscribe("k1.test", c2)
        bus.publish(Envelope(topic="k1.test", payload=b"both"))
        assert c1.count() == 1
        assert c2.count() == 1

    def test_fan_out_across_patterns(self) -> None:
        bus = LocalBus()
        c_exact = _Collector()
        c_wild = _Collector()
        c_greedy = _Collector()
        bus.subscribe("k1.a.b.c", c_exact)
        bus.subscribe("k1.a.*.c", c_wild)
        bus.subscribe("k1.a.>", c_greedy)
        bus.publish(Envelope(topic="k1.a.b.c", payload=b"fan"))
        assert c_exact.count() == 1
        assert c_wild.count() == 1
        assert c_greedy.count() == 1


# ===================================================================
# Bus-stamped fields
# ===================================================================


class TestBusStampedFields:
    """Bus assigns envelope_id, sequence, created_ns."""

    def test_envelope_id_assigned(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"a"))
        assert bus.captured[0].envelope_id > 0

    def test_envelope_id_monotonic(self) -> None:
        bus = LocalBus(capture=True)
        for _ in range(100):
            bus.publish(Envelope(topic="k1.test", payload=b"x"))
        ids = [e.envelope_id for e in bus.captured]
        assert ids == sorted(ids)
        assert len(set(ids)) == 100  # all unique

    def test_sequence_per_topic(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="k1.a", payload=b"1"))
        bus.publish(Envelope(topic="k1.b", payload=b"2"))
        bus.publish(Envelope(topic="k1.a", payload=b"3"))
        bus.publish(Envelope(topic="k1.b", payload=b"4"))

        a_seqs = [e.sequence for e in bus.captured if e.topic == "k1.a"]
        b_seqs = [e.sequence for e in bus.captured if e.topic == "k1.b"]

        assert a_seqs == [1, 2]
        assert b_seqs == [1, 2]

    def test_sequence_independent_per_topic(self) -> None:
        bus = LocalBus(capture=True)
        for i in range(50):
            bus.publish(Envelope(topic="k1.topic.a", payload=b""))
        for i in range(30):
            bus.publish(Envelope(topic="k1.topic.b", payload=b""))

        a_seqs = [e.sequence for e in bus.captured if e.topic == "k1.topic.a"]
        b_seqs = [e.sequence for e in bus.captured if e.topic == "k1.topic.b"]
        assert a_seqs == list(range(1, 51))
        assert b_seqs == list(range(1, 31))

    def test_created_ns_monotonic(self) -> None:
        bus = LocalBus(capture=True)
        for _ in range(10):
            bus.publish(Envelope(topic="k1.test", payload=b""))
        timestamps = [e.created_ns for e in bus.captured]
        assert timestamps == sorted(timestamps)
        assert all(t > 0 for t in timestamps)

    def test_publisher_fields_preserved(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(
            Envelope(
                topic="k1.test",
                priority=Priority.URGENT,
                cognitive_trace_id="trace-42",
                session_id="sess-1",
                request_id="req-1",
                parent_id=99,
                payload=b"keep-me",
            )
        )
        env = bus.captured[0]
        assert env.topic == "k1.test"
        assert env.priority == Priority.URGENT
        assert env.cognitive_trace_id == "trace-42"
        assert env.session_id == "sess-1"
        assert env.request_id == "req-1"
        assert env.parent_id == 99
        assert env.payload == b"keep-me"

    def test_original_envelope_not_mutated(self) -> None:
        original = Envelope(topic="k1.test", payload=b"data")
        bus = LocalBus()
        bus.publish(original)
        assert original.envelope_id == 0  # frozen, never mutated
        assert original.sequence == 0
        assert original.created_ns == 0


# ===================================================================
# Handler error isolation
# ===================================================================


class TestHandlerErrorIsolation:
    """Handler exceptions MUST NOT propagate to publisher or other handlers."""

    def test_exception_swallowed(self) -> None:
        bus = LocalBus()
        err_handler = _ErrorHandler()
        bus.subscribe("k1.test", err_handler)
        # Should not raise
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))
        assert err_handler.call_count == 1

    def test_other_handlers_still_called(self) -> None:
        bus = LocalBus()
        c_before = _Collector()
        err_handler = _ErrorHandler()
        c_after = _Collector()
        bus.subscribe("k1.test", c_before)
        bus.subscribe("k1.test", err_handler)
        bus.subscribe("k1.test", c_after)
        bus.publish(Envelope(topic="k1.test", payload=b"survive"))
        assert c_before.count() == 1
        assert c_after.count() == 1
        assert err_handler.call_count == 1

    def test_handler_error_counted_in_stats(self) -> None:
        bus = LocalBus()
        bus.subscribe("k1.test", _ErrorHandler())
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.stats.handler_errors == 1


# ===================================================================
# Unsubscribe
# ===================================================================


class TestUnsubscribe:
    """Unsubscribe stops delivery."""

    def test_unsubscribe_stops_delivery(self) -> None:
        bus = LocalBus()
        collector = _Collector()
        handle = bus.subscribe("k1.test", collector)
        bus.publish(Envelope(topic="k1.test", payload=b"before"))
        assert collector.count() == 1

        assert bus.unsubscribe(handle) is True
        bus.publish(Envelope(topic="k1.test", payload=b"after"))
        assert collector.count() == 1  # no new delivery

    def test_double_unsubscribe(self) -> None:
        bus = LocalBus()
        handle = bus.subscribe("k1.test", _Collector())
        assert bus.unsubscribe(handle) is True
        assert bus.unsubscribe(handle) is False

    def test_unsubscribe_returns_false_for_unknown(self) -> None:
        bus = LocalBus()
        fake = SubscriptionHandle(subscription_id="nonexistent", pattern="x")
        assert bus.unsubscribe(fake) is False


# ===================================================================
# Capture mode
# ===================================================================


class TestCaptureMode:
    """Capture mode for testing."""

    def test_capture_records_envelopes(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="k1.a", payload=b"1"))
        bus.publish(Envelope(topic="k1.b", payload=b"2"))
        assert len(bus.captured) == 2
        assert bus.captured[0].topic == "k1.a"
        assert bus.captured[1].topic == "k1.b"

    def test_capture_records_stamped_envelopes(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert bus.captured[0].envelope_id > 0
        assert bus.captured[0].sequence > 0
        assert bus.captured[0].created_ns > 0

    def test_drain_returns_and_clears(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b"a"))
        bus.publish(Envelope(topic="k1.test", payload=b"b"))
        drained = bus.drain()
        assert len(drained) == 2
        assert len(bus.captured) == 0

    def test_no_capture_mode(self) -> None:
        bus = LocalBus(capture=False)
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(bus.captured) == 0

    def test_capture_plus_handler(self) -> None:
        """Capture AND handler both work simultaneously."""
        bus = LocalBus(capture=True)
        collector = _Collector()
        bus.subscribe("k1.test", collector)
        bus.publish(Envelope(topic="k1.test", payload=b"both"))
        assert len(bus.captured) == 1
        assert collector.count() == 1


# ===================================================================
# Close
# ===================================================================


class TestClose:
    """Bus close lifecycle."""

    def test_close_drops_publishes(self) -> None:
        bus = LocalBus(capture=True)
        collector = _Collector()
        bus.subscribe("k1.test", collector)
        bus.close()
        bus.publish(Envelope(topic="k1.test", payload=b"dropped"))
        assert collector.count() == 0
        assert len(bus.captured) == 0

    def test_closed_property(self) -> None:
        bus = LocalBus()
        assert bus.closed is False
        bus.close()
        assert bus.closed is True


# ===================================================================
# Empty topic
# ===================================================================


class TestEmptyTopic:
    """Empty topic envelopes are dropped."""

    def test_empty_topic_dropped(self) -> None:
        bus = LocalBus(capture=True)
        bus.publish(Envelope(topic="", payload=b"nowhere"))
        assert len(bus.captured) == 0
        assert bus.stats.envelopes_published == 0


# ===================================================================
# Stats
# ===================================================================


class TestStats:
    """BusStats tracking."""

    def test_stats_published(self) -> None:
        bus = LocalBus()
        bus.subscribe("k1.test", _Collector())
        bus.publish(Envelope(topic="k1.test", payload=b""))
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.stats.envelopes_published == 2

    def test_stats_delivered(self) -> None:
        bus = LocalBus()
        c1, c2 = _Collector(), _Collector()
        bus.subscribe("k1.test", c1)
        bus.subscribe("k1.test", c2)
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.stats.envelopes_delivered == 2  # 1 publish -> 2 handlers

    def test_stats_subscriptions(self) -> None:
        bus = LocalBus()
        h1 = bus.subscribe("k1.a", _Collector())
        bus.subscribe("k1.b", _Collector())
        assert bus.stats.subscriptions_active == 2
        assert bus.stats.subscriptions_total == 2
        bus.unsubscribe(h1)
        assert bus.stats.subscriptions_active == 1
        assert bus.stats.unsubscribe_count == 1

    def test_stats_topics_seen(self) -> None:
        bus = LocalBus()
        bus.publish(Envelope(topic="k1.a", payload=b""))
        bus.publish(Envelope(topic="k1.b", payload=b""))
        bus.publish(Envelope(topic="k1.a", payload=b""))  # duplicate
        assert bus.stats.topics_seen == 2

    def test_stats_snapshot(self) -> None:
        bus = LocalBus()
        bus.publish(Envelope(topic="k1.test", payload=b""))
        snap = bus.stats.snapshot()
        assert isinstance(snap, dict)
        assert snap["envelopes_published"] == 1

    def test_subscription_count(self) -> None:
        bus = LocalBus()
        bus.subscribe("k1.a", _Collector())
        bus.subscribe("k1.b", _Collector())
        assert bus.subscription_count == 2

    def test_topic_sequence(self) -> None:
        bus = LocalBus()
        bus.publish(Envelope(topic="k1.test", payload=b""))
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.topic_sequence("k1.test") == 2
        assert bus.topic_sequence("k1.unknown") == 0

    def test_last_envelope_id(self) -> None:
        bus = LocalBus()
        assert bus.last_envelope_id == 0
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.last_envelope_id == 1

    def test_repr(self) -> None:
        bus = LocalBus(capture=True)
        assert "LocalBus" in repr(bus)
        assert "capture=True" in repr(bus)


# ===================================================================
# BusFactory
# ===================================================================


class TestBusFactory:
    """BusFactory construction."""

    def test_create_local(self) -> None:
        bus = BusFactory.create_local()
        assert isinstance(bus, LocalBus)
        assert len(bus.captured) == 0

    def test_create_local_with_capture(self) -> None:
        bus = BusFactory.create_local(capture=True)
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert len(bus.captured) == 1

    def test_create_for_testing(self) -> None:
        bus = BusFactory.create_for_testing()
        assert isinstance(bus, LocalBus)
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert len(bus.captured) == 1


# ===================================================================
# Thread safety
# ===================================================================


class TestThreadSafety:
    """Concurrent publish + subscribe from multiple threads."""

    def test_concurrent_publish(self) -> None:
        """Multiple threads publishing simultaneously."""
        bus = LocalBus(capture=True)
        collector = _Collector()
        bus.subscribe("k1.stress.>", collector)

        n_threads = 8
        n_per_thread = 500
        barrier = threading.Barrier(n_threads)

        def publisher(thread_id: int) -> None:
            barrier.wait()
            for i in range(n_per_thread):
                bus.publish(
                    Envelope(
                        topic=f"k1.stress.t{thread_id}.msg",
                        payload=f"{thread_id}-{i}".encode(),
                    )
                )

        threads = [threading.Thread(target=publisher, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = n_threads * n_per_thread
        assert collector.count() == total
        assert len(bus.captured) == total
        assert bus.stats.envelopes_published == total

        # Envelope IDs must all be unique
        ids = {e.envelope_id for e in bus.captured}
        assert len(ids) == total

    def test_concurrent_subscribe_unsubscribe(self) -> None:
        """Subscribe and unsubscribe while publishing."""
        bus = LocalBus()
        errors: list[Exception] = []
        stop = threading.Event()

        def publisher() -> None:
            while not stop.is_set():
                try:
                    bus.publish(Envelope(topic="k1.churn.test", payload=b"x"))
                except Exception as e:
                    errors.append(e)

        def subscriber() -> None:
            for _ in range(200):
                try:
                    h = bus.subscribe("k1.churn.*", lambda env: None)
                    bus.unsubscribe(h)
                except Exception as e:
                    errors.append(e)

        pub_thread = threading.Thread(target=publisher)
        sub_threads = [threading.Thread(target=subscriber) for _ in range(4)]

        pub_thread.start()
        for t in sub_threads:
            t.start()
        for t in sub_threads:
            t.join()
        stop.set()
        pub_thread.join()

        # No errors from concurrent operations
        assert errors == [], f"Concurrency errors: {errors}"

    def test_concurrent_sequence_monotonicity(self) -> None:
        """Per-topic sequences must be strictly monotonic even under contention."""
        bus = LocalBus(capture=True)
        n_threads = 4
        n_per_thread = 250
        barrier = threading.Barrier(n_threads)

        def publisher() -> None:
            barrier.wait()
            for _ in range(n_per_thread):
                bus.publish(Envelope(topic="k1.contested.topic", payload=b""))

        threads = [threading.Thread(target=publisher) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        seqs = [e.sequence for e in bus.captured]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == n_threads * n_per_thread  # all unique
        assert seqs == list(range(1, n_threads * n_per_thread + 1))


# ===================================================================
# Priority-aware dispatch verification
# ===================================================================


class TestPriorityDispatch:
    """Verify priority metadata is preserved through the bus."""

    def test_priority_preserved_in_envelope(self) -> None:
        bus = LocalBus(capture=True)
        for p in Priority:
            bus.publish(Envelope(topic="k1.test", priority=p, payload=b""))

        priorities = [e.priority for e in bus.captured]
        assert priorities == [
            Priority.URGENT,
            Priority.REALTIME,
            Priority.INTERACTIVE,
            Priority.BACKGROUND,
        ]

    def test_priority_available_to_handler(self) -> None:
        bus = LocalBus()
        received_priorities: list[int] = []

        def handler(env: Envelope) -> None:
            received_priorities.append(env.priority)

        bus.subscribe("k1.test", handler)
        bus.publish(Envelope(topic="k1.test", priority=Priority.URGENT, payload=b""))
        bus.publish(Envelope(topic="k1.test", priority=Priority.BACKGROUND, payload=b""))
        assert received_priorities == [Priority.URGENT, Priority.BACKGROUND]


# ===================================================================
# High-volume stress test
# ===================================================================


class TestHighVolume:
    """Stress tests for correctness under high throughput."""

    def test_100k_publishes(self) -> None:
        """100K publishes with multiple subscribers -- correctness check."""
        bus = LocalBus()
        counts = defaultdict(int)
        lock = threading.Lock()

        def counter_handler(env: Envelope) -> None:
            with lock:
                counts[env.topic] += 1

        bus.subscribe("k1.bulk.>", counter_handler)
        bus.subscribe("k1.bulk.a", counter_handler)  # double subscription for topic a

        n = 100_000
        start = time.monotonic()
        for i in range(n):
            topic = "k1.bulk.a" if i % 2 == 0 else "k1.bulk.b"
            bus.publish(Envelope(topic=topic, payload=b""))
        elapsed = time.monotonic() - start

        # greedy subscriber gets all 100K
        # "k1.bulk.a" also matches exact subscriber -> 50K extra
        assert counts["k1.bulk.a"] == 100_000  # 50K * 2 handlers
        assert counts["k1.bulk.b"] == 50_000  # 50K * 1 handler
        assert bus.stats.envelopes_published == n

        # Performance guard: should complete in <5s even on slow CI
        assert elapsed < 5.0, f"100K publishes took {elapsed:.2f}s"

    def test_sequence_integrity_under_volume(self) -> None:
        """Sequence numbers must be contiguous under high volume."""
        bus = LocalBus(capture=True)
        n = 10_000
        for _ in range(n):
            bus.publish(Envelope(topic="k1.seq.test", payload=b""))

        seqs = [e.sequence for e in bus.captured]
        assert seqs == list(range(1, n + 1))
