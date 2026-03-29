"""
Parametrized parity tests: LocalBus vs RustBus behavioral equivalence.

V2-M5-015: Run the core LocalBus behavioral tests against RustBus to
            verify identical semantics for publish, subscribe, dispatch,
            stamping, error isolation, capture, close, stats, and more.

V2-M5-016: Cross-module integration tests against RustBus backend.

The RustBusAdapter wraps k1_bus_core.RustBus to present the same API as
LocalBus (Envelope in/out, SubscriptionHandle, BusStats dataclass).

Tests that are LocalBus-specific (IBus protocol isinstance, BusFactory,
timing_chain, middleware, drain) are NOT parametrized -- they remain in
test_local_bus.py.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from typing import Any

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.impl.local_bus import BusStats, LocalBus
from k1.bus.ports.bus import SubscriptionHandle

# --- Conditional import: skip RustBus tests if crate not installed ---

try:
    import k1_bus_core

    HAS_RUST = True
except ImportError:
    HAS_RUST = False
    k1_bus_core = None  # type: ignore[assignment]


# ===================================================================
# RustBusAdapter -- wraps RustBus to match LocalBus API surface
# ===================================================================


class RustBusAdapter:
    """
    Adapter wrapping k1_bus_core.RustBus to present the same API as LocalBus.

    Conversions:
        - Envelope <-> RustEnvelope (on publish, on handler receive)
        - SubscriptionHandle <-> str subscription_id
        - BusStats dataclass <-> dict stats
        - captured list[Envelope] <-> list[RustEnvelope]
        - closed property <-> is_closed property
    """

    def __init__(self, *, capture: bool = False) -> None:
        self._bus = k1_bus_core.RustBus(capture=capture)
        self._capture = capture
        # Track sub_id -> pattern for SubscriptionHandle reconstruction
        self._sub_patterns: dict[str, str] = {}

    @staticmethod
    def _envelope_to_rust(env: Envelope) -> Any:
        """Convert Python Envelope to RustEnvelope."""
        return k1_bus_core.RustEnvelope(
            topic=env.topic,
            priority=env.priority.value if isinstance(env.priority, Priority) else env.priority,
            envelope_id=env.envelope_id,
            sequence=env.sequence,
            cognitive_trace_id=env.cognitive_trace_id,
            session_id=env.session_id,
            request_id=env.request_id,
            parent_id=env.parent_id,
            created_ns=env.created_ns,
            payload=env.payload,
            ttl_ms=env.ttl_ms,
            payload_format=(
                env.payload_format.value
                if hasattr(env.payload_format, "value")
                else env.payload_format
            ),
        )

    @staticmethod
    def _rust_to_envelope(renv: Any) -> Envelope:
        """Convert RustEnvelope to Python Envelope."""
        return Envelope(
            topic=renv.topic,
            priority=Priority(renv.priority),
            envelope_id=renv.envelope_id,
            sequence=renv.sequence,
            cognitive_trace_id=renv.cognitive_trace_id,
            session_id=renv.session_id,
            request_id=renv.request_id,
            parent_id=renv.parent_id,
            created_ns=renv.created_ns,
            payload=bytes(renv.payload),
            ttl_ms=renv.ttl_ms,
            payload_format=renv.payload_format,
        )

    def publish(self, envelope: Envelope) -> None:
        """Publish, converting Envelope -> RustEnvelope."""
        renv = self._envelope_to_rust(envelope)
        # RustBus.publish raises on closed bus; LocalBus silently drops
        try:
            self._bus.publish(renv)
        except RuntimeError:
            # Closed bus -- LocalBus silently drops
            return
        except ValueError:
            # Invalid topic -- LocalBus silently drops empty topics
            return

    def subscribe(self, pattern: str, handler: Any) -> SubscriptionHandle:
        """Subscribe, wrapping handler to convert RustEnvelope -> Envelope."""

        def adapted_handler(renv: Any) -> None:
            env = self._rust_to_envelope(renv)
            handler(env)

        sub_id = self._bus.subscribe(pattern, adapted_handler)
        self._sub_patterns[sub_id] = pattern
        return SubscriptionHandle(subscription_id=sub_id, pattern=pattern)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Unsubscribe by subscription_id."""
        self._sub_patterns.pop(handle.subscription_id, None)
        return self._bus.unsubscribe(handle.subscription_id)

    def close(self) -> None:
        self._bus.close()

    @property
    def closed(self) -> bool:
        return self._bus.is_closed

    @property
    def stats(self) -> BusStats:
        """Convert RustBus stats dict to BusStats dataclass."""
        s = self._bus.stats
        bs = BusStats()
        bs.envelopes_published = s["envelopes_published"]
        bs.envelopes_delivered = s["envelopes_delivered"]
        bs.handler_errors = s["handler_errors"]
        bs.subscriptions_active = s["subscriptions_active"]
        bs.subscriptions_total = s["subscriptions_total"]
        bs.unsubscribe_count = s["unsubscribe_count"]
        bs.topics_seen = s["topics_seen"]
        return bs

    @property
    def captured(self) -> list[Envelope]:
        """Convert captured RustEnvelopes to Envelopes."""
        return [self._rust_to_envelope(r) for r in self._bus.captured]

    @property
    def subscription_count(self) -> int:
        return self._bus.subscription_count

    def topic_sequence(self, topic: str) -> int:
        return self._bus.topic_sequence(topic)

    @property
    def last_envelope_id(self) -> int:
        return self._bus.last_envelope_id


# ===================================================================
# Fixtures
# ===================================================================


def _make_bus(backend: str, capture: bool = False) -> LocalBus | RustBusAdapter:
    if backend == "python":
        return LocalBus(capture=capture)
    else:
        return RustBusAdapter(capture=capture)


@pytest.fixture(
    params=["python", "rust"] if HAS_RUST else ["python"],
    ids=lambda p: f"bus={p}",
)
def bus_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def bus(bus_backend: str) -> LocalBus | RustBusAdapter:
    return _make_bus(bus_backend)


@pytest.fixture
def capture_bus(bus_backend: str) -> LocalBus | RustBusAdapter:
    return _make_bus(bus_backend, capture=True)


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
# Publish/Subscribe
# ===================================================================


class TestPublishSubscribe:
    """Core publish/subscribe parity."""

    def test_exact_match_delivery(self, bus: Any) -> None:
        collector = _Collector()
        bus.subscribe("k1.test.event.v1", collector)
        bus.publish(Envelope(topic="k1.test.event.v1", payload=b"hello"))
        assert collector.count() == 1
        assert collector.received[0].payload == b"hello"
        assert collector.received[0].topic == "k1.test.event.v1"

    def test_wildcard_delivery(self, bus: Any) -> None:
        collector = _Collector()
        bus.subscribe("k1.capability.*", collector)
        bus.publish(Envelope(topic="k1.capability.completed", payload=b"a"))
        bus.publish(Envelope(topic="k1.capability.failed", payload=b"b"))
        bus.publish(Envelope(topic="k1.other.event", payload=b"c"))
        assert collector.count() == 2

    def test_greedy_wildcard_delivery(self, bus: Any) -> None:
        collector = _Collector()
        bus.subscribe("k1.agent.>", collector)
        bus.publish(Envelope(topic="k1.agent.abc.delta.v1", payload=b"d"))
        bus.publish(Envelope(topic="k1.agent.xyz", payload=b"e"))
        bus.publish(Envelope(topic="k1.session.update", payload=b"f"))
        assert collector.count() == 2

    def test_no_match_no_delivery(self, bus: Any) -> None:
        collector = _Collector()
        bus.subscribe("k1.session.*", collector)
        bus.publish(Envelope(topic="k1.capability.completed", payload=b"x"))
        assert collector.count() == 0

    def test_multiple_subscribers_same_pattern(self, bus: Any) -> None:
        c1, c2 = _Collector(), _Collector()
        bus.subscribe("k1.test", c1)
        bus.subscribe("k1.test", c2)
        bus.publish(Envelope(topic="k1.test", payload=b"both"))
        assert c1.count() == 1
        assert c2.count() == 1

    def test_fan_out_across_patterns(self, bus: Any) -> None:
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

    def test_envelope_id_assigned(self, capture_bus: Any) -> None:
        capture_bus.publish(Envelope(topic="k1.test", payload=b"a"))
        assert capture_bus.captured[0].envelope_id > 0

    def test_envelope_id_monotonic(self, capture_bus: Any) -> None:
        for _ in range(100):
            capture_bus.publish(Envelope(topic="k1.test", payload=b"x"))
        ids = [e.envelope_id for e in capture_bus.captured]
        assert ids == sorted(ids)
        assert len(set(ids)) == 100

    def test_sequence_per_topic(self, capture_bus: Any) -> None:
        capture_bus.publish(Envelope(topic="k1.a", payload=b"1"))
        capture_bus.publish(Envelope(topic="k1.b", payload=b"2"))
        capture_bus.publish(Envelope(topic="k1.a", payload=b"3"))
        capture_bus.publish(Envelope(topic="k1.b", payload=b"4"))
        a_seqs = [e.sequence for e in capture_bus.captured if e.topic == "k1.a"]
        b_seqs = [e.sequence for e in capture_bus.captured if e.topic == "k1.b"]
        assert a_seqs == [1, 2]
        assert b_seqs == [1, 2]

    def test_sequence_independent_per_topic(self, capture_bus: Any) -> None:
        for _ in range(50):
            capture_bus.publish(Envelope(topic="k1.topic.a", payload=b""))
        for _ in range(30):
            capture_bus.publish(Envelope(topic="k1.topic.b", payload=b""))
        a_seqs = [e.sequence for e in capture_bus.captured if e.topic == "k1.topic.a"]
        b_seqs = [e.sequence for e in capture_bus.captured if e.topic == "k1.topic.b"]
        assert a_seqs == list(range(1, 51))
        assert b_seqs == list(range(1, 31))

    def test_created_ns_monotonic(self, capture_bus: Any) -> None:
        for _ in range(10):
            capture_bus.publish(Envelope(topic="k1.test", payload=b""))
        timestamps = [e.created_ns for e in capture_bus.captured]
        assert timestamps == sorted(timestamps)
        assert all(t > 0 for t in timestamps)

    def test_publisher_fields_preserved(self, capture_bus: Any) -> None:
        capture_bus.publish(
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
        env = capture_bus.captured[0]
        assert env.topic == "k1.test"
        assert env.priority == Priority.URGENT
        assert env.cognitive_trace_id == "trace-42"
        assert env.session_id == "sess-1"
        assert env.request_id == "req-1"
        assert env.parent_id == 99
        assert env.payload == b"keep-me"


# ===================================================================
# Handler error isolation
# ===================================================================


class TestHandlerErrorIsolation:
    """Handler exceptions MUST NOT propagate to publisher or other handlers."""

    def test_exception_swallowed(self, bus: Any) -> None:
        err_handler = _ErrorHandler()
        bus.subscribe("k1.test", err_handler)
        bus.publish(Envelope(topic="k1.test", payload=b"ok"))
        assert err_handler.call_count == 1

    def test_other_handlers_still_called(self, bus: Any) -> None:
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

    def test_handler_error_counted_in_stats(self, bus: Any) -> None:
        bus.subscribe("k1.test", _ErrorHandler())
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.stats.handler_errors == 1


# ===================================================================
# Unsubscribe
# ===================================================================


class TestUnsubscribe:
    """Unsubscribe stops delivery."""

    def test_unsubscribe_stops_delivery(self, bus: Any) -> None:
        collector = _Collector()
        handle = bus.subscribe("k1.test", collector)
        bus.publish(Envelope(topic="k1.test", payload=b"before"))
        assert collector.count() == 1
        assert bus.unsubscribe(handle) is True
        bus.publish(Envelope(topic="k1.test", payload=b"after"))
        assert collector.count() == 1

    def test_double_unsubscribe(self, bus: Any) -> None:
        handle = bus.subscribe("k1.test", _Collector())
        assert bus.unsubscribe(handle) is True
        assert bus.unsubscribe(handle) is False

    def test_unsubscribe_returns_false_for_unknown(self, bus: Any) -> None:
        fake = SubscriptionHandle(subscription_id="nonexistent", pattern="x")
        assert bus.unsubscribe(fake) is False


# ===================================================================
# Capture mode
# ===================================================================


class TestCaptureMode:
    """Capture mode for testing."""

    def test_capture_records_envelopes(self, capture_bus: Any) -> None:
        capture_bus.publish(Envelope(topic="k1.a", payload=b"1"))
        capture_bus.publish(Envelope(topic="k1.b", payload=b"2"))
        assert len(capture_bus.captured) == 2
        assert capture_bus.captured[0].topic == "k1.a"
        assert capture_bus.captured[1].topic == "k1.b"

    def test_capture_records_stamped_envelopes(self, capture_bus: Any) -> None:
        capture_bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert capture_bus.captured[0].envelope_id > 0
        assert capture_bus.captured[0].sequence > 0
        assert capture_bus.captured[0].created_ns > 0

    def test_no_capture_mode(self, bus: Any) -> None:
        bus.publish(Envelope(topic="k1.test", payload=b"x"))
        assert len(bus.captured) == 0

    def test_capture_plus_handler(self, capture_bus: Any) -> None:
        collector = _Collector()
        capture_bus.subscribe("k1.test", collector)
        capture_bus.publish(Envelope(topic="k1.test", payload=b"both"))
        assert len(capture_bus.captured) == 1
        assert collector.count() == 1


# ===================================================================
# Close
# ===================================================================


class TestClose:
    """Bus close lifecycle."""

    def test_close_drops_publishes(self, capture_bus: Any) -> None:
        collector = _Collector()
        capture_bus.subscribe("k1.test", collector)
        capture_bus.close()
        capture_bus.publish(Envelope(topic="k1.test", payload=b"dropped"))
        assert collector.count() == 0
        assert len(capture_bus.captured) == 0

    def test_closed_property(self, bus: Any) -> None:
        assert bus.closed is False
        bus.close()
        assert bus.closed is True


# ===================================================================
# Empty topic
# ===================================================================


class TestEmptyTopic:
    """Empty topic envelopes are dropped."""

    def test_empty_topic_dropped(self, capture_bus: Any) -> None:
        capture_bus.publish(Envelope(topic="", payload=b"nowhere"))
        assert len(capture_bus.captured) == 0
        assert capture_bus.stats.envelopes_published == 0


# ===================================================================
# Stats
# ===================================================================


class TestStats:
    """BusStats tracking."""

    def test_stats_published(self, bus: Any) -> None:
        bus.subscribe("k1.test", _Collector())
        bus.publish(Envelope(topic="k1.test", payload=b""))
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.stats.envelopes_published == 2

    def test_stats_delivered(self, bus: Any) -> None:
        c1, c2 = _Collector(), _Collector()
        bus.subscribe("k1.test", c1)
        bus.subscribe("k1.test", c2)
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.stats.envelopes_delivered == 2

    def test_stats_subscriptions(self, bus: Any) -> None:
        h1 = bus.subscribe("k1.a", _Collector())
        bus.subscribe("k1.b", _Collector())
        assert bus.stats.subscriptions_active == 2
        assert bus.stats.subscriptions_total == 2
        bus.unsubscribe(h1)
        assert bus.stats.subscriptions_active == 1
        assert bus.stats.unsubscribe_count == 1

    def test_stats_topics_seen(self, bus: Any) -> None:
        bus.publish(Envelope(topic="k1.a", payload=b""))
        bus.publish(Envelope(topic="k1.b", payload=b""))
        bus.publish(Envelope(topic="k1.a", payload=b""))
        assert bus.stats.topics_seen == 2

    def test_subscription_count(self, bus: Any) -> None:
        bus.subscribe("k1.a", _Collector())
        bus.subscribe("k1.b", _Collector())
        assert bus.subscription_count == 2

    def test_topic_sequence(self, bus: Any) -> None:
        bus.publish(Envelope(topic="k1.test", payload=b""))
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.topic_sequence("k1.test") == 2
        assert bus.topic_sequence("k1.unknown") == 0

    def test_last_envelope_id(self, bus: Any) -> None:
        assert bus.last_envelope_id == 0
        bus.publish(Envelope(topic="k1.test", payload=b""))
        assert bus.last_envelope_id == 1


# ===================================================================
# Thread safety
# ===================================================================


class TestThreadSafety:
    """Concurrent publish + subscribe from multiple threads."""

    def test_concurrent_publish(self, bus_backend: str) -> None:
        bus = _make_bus(bus_backend, capture=True)
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

        ids = {e.envelope_id for e in bus.captured}
        assert len(ids) == total

    def test_concurrent_subscribe_unsubscribe(self, bus_backend: str) -> None:
        bus = _make_bus(bus_backend)
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

        assert errors == [], f"Concurrency errors: {errors}"

    def test_concurrent_sequence_monotonicity(self, bus_backend: str) -> None:
        bus = _make_bus(bus_backend, capture=True)
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
        assert len(set(seqs)) == n_threads * n_per_thread
        assert seqs == list(range(1, n_threads * n_per_thread + 1))


# ===================================================================
# Priority dispatch
# ===================================================================


class TestPriorityDispatch:
    """Verify priority metadata is preserved through the bus."""

    def test_priority_preserved_in_envelope(self, bus_backend: str) -> None:
        bus = _make_bus(bus_backend, capture=True)
        for p in Priority:
            bus.publish(Envelope(topic="k1.test", priority=p, payload=b""))
        priorities = [e.priority for e in bus.captured]
        assert priorities == [
            Priority.URGENT,
            Priority.REALTIME,
            Priority.INTERACTIVE,
            Priority.BACKGROUND,
        ]

    def test_priority_available_to_handler(self, bus: Any) -> None:
        received_priorities: list[int] = []

        def handler(env: Envelope) -> None:
            received_priorities.append(env.priority)

        bus.subscribe("k1.test", handler)
        bus.publish(Envelope(topic="k1.test", priority=Priority.URGENT, payload=b""))
        bus.publish(Envelope(topic="k1.test", priority=Priority.BACKGROUND, payload=b""))
        assert received_priorities == [Priority.URGENT, Priority.BACKGROUND]


# ===================================================================
# High volume
# ===================================================================


class TestHighVolume:
    """Stress tests for correctness under high throughput."""

    def test_10k_publishes(self, bus_backend: str) -> None:
        """10K publishes with multiple subscribers -- correctness check."""
        bus = _make_bus(bus_backend)
        counts: dict[str, int] = defaultdict(int)
        lock = threading.Lock()

        def counter_handler(env: Envelope) -> None:
            with lock:
                counts[env.topic] += 1

        bus.subscribe("k1.bulk.>", counter_handler)
        bus.subscribe("k1.bulk.a", counter_handler)  # double sub for topic a

        n = 10_000
        for i in range(n):
            topic = "k1.bulk.a" if i % 2 == 0 else "k1.bulk.b"
            bus.publish(Envelope(topic=topic, payload=b""))

        assert counts["k1.bulk.a"] == 10_000  # 5K * 2 handlers
        assert counts["k1.bulk.b"] == 5_000
        assert bus.stats.envelopes_published == n

    def test_sequence_integrity_under_volume(self, bus_backend: str) -> None:
        bus = _make_bus(bus_backend, capture=True)
        n = 10_000
        for _ in range(n):
            bus.publish(Envelope(topic="k1.seq.test", payload=b""))
        seqs = [e.sequence for e in bus.captured]
        assert seqs == list(range(1, n + 1))


# ===================================================================
# Subscription lifecycle events (V2-M5-012, RustBus only)
# ===================================================================


@pytest.mark.skipif(not HAS_RUST, reason="k1_bus_core not installed")
class TestSubscriptionLifecycleEvents:
    """V2-M5-012: Lifecycle events on subscribe/unsubscribe."""

    def test_subscribe_emits_created(self) -> None:
        bus = k1_bus_core.RustBus()
        events = []
        bus.subscribe("k1.bus.subscription.>", events.append)
        bus.subscribe("k1.another.topic", lambda e: None)
        created = [e for e in events if e.topic == "k1.bus.subscription.created"]
        # At least 2: one for the listener itself, one for k1.another.topic
        assert len(created) >= 2
        # The last created event is for the second subscribe call
        payload = json.loads(created[-1].payload)
        assert "subscription_id" in payload
        assert "pattern" in payload
        assert payload["pattern"] == "k1.another.topic"

    def test_unsubscribe_emits_removed(self) -> None:
        bus = k1_bus_core.RustBus()
        events = []
        bus.subscribe("k1.bus.subscription.>", events.append)
        sid = bus.subscribe("k1.test", lambda e: None)
        bus.unsubscribe(sid)
        removed = [e for e in events if e.topic == "k1.bus.subscription.removed"]
        assert len(removed) == 1
        payload = json.loads(removed[0].payload)
        assert payload["subscription_id"] == sid

    def test_lifecycle_handler_self_subscribe(self) -> None:
        """The lifecycle handler receives its own subscribe created event."""
        bus = k1_bus_core.RustBus()
        events = []
        bus.subscribe("k1.bus.subscription.created", events.append)
        # The subscribe itself triggers a created event
        assert len(events) == 1
        assert events[0].topic == "k1.bus.subscription.created"

    def test_lifecycle_events_are_background_priority(self) -> None:
        bus = k1_bus_core.RustBus()
        events = []
        bus.subscribe("k1.bus.subscription.>", events.append)
        bus.subscribe("k1.test", lambda e: None)
        for e in events:
            assert e.priority == 3  # BACKGROUND

    def test_lifecycle_events_have_json_payload(self) -> None:
        bus = k1_bus_core.RustBus()
        events = []
        bus.subscribe("k1.bus.subscription.>", events.append)
        bus.subscribe("k1.test.pattern", lambda e: None)
        for e in events:
            payload = json.loads(e.payload)
            assert isinstance(payload, dict)
            assert "subscription_id" in payload
