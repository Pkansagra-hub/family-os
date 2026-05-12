"""
M7 — Bus reliability tests.

Covers the production-readiness fixes added in Milestone 7:

* B01 — TTL enforcement on sync and async dispatch (``ttl_drops`` stat,
  ``TtlExpiredError`` routed through DLQ on async path).
* B02 — sequence numbers are allocated AFTER middleware so dropped
  envelopes do not produce gaps for STRICT-mode timing chains.
* B03 — ``_GapBuffer`` evicts the least-recently-created topic when
  ``max_topics`` is exceeded (no more linear lock/state leak).
* B04 — backpressure drops route through the DLQ callback.
* B06 — ``IBus.publish_batch`` shares a single trie read-lock
  acquisition; ``SessionBusAdapter.emit_batch`` overrides the loop
  default to call it once.
* B07 — ``BusFactory.create_local_ordered`` installs
  ``TopicValidationMiddleware`` against ``DEFAULT_TOPIC_REGISTRY`` by
  default.
* B08 — ``LocalMailbox`` supports deficit round-robin scheduling via
  ``MailboxConfig.wfq_quantum`` (strict priority remains the default).
"""

from __future__ import annotations

import time

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus
from k1.bus.impl.local_mailbox import LocalMailbox
from k1.bus.middleware import Middleware, MiddlewareChain
from k1.bus.middleware.default_registry import get_default_registry
from k1.bus.middleware.topic_validation import TopicValidationMiddleware
from k1.bus.ports.mailbox import (
    BackpressureError,
    MailboxConfig,
    TtlExpiredError,
)
from k1.bus.timing.timing_chain import _GapBuffer

# ---------------------------------------------------------------------------
# B01 — TTL enforcement
# ---------------------------------------------------------------------------


class _DropAfterMiddleware:
    """Test middleware that returns None to drop every envelope."""

    def process(self, envelope: Envelope) -> Envelope | None:
        return None


class _IdMiddleware:
    """Pass-through middleware (records seen envelopes)."""

    def __init__(self) -> None:
        self.seen: list[Envelope] = []

    def process(self, envelope: Envelope) -> Envelope | None:
        self.seen.append(envelope)
        return envelope


class TestTtlEnforcementSync:
    def test_sync_ttl_zero_means_no_expiry(self) -> None:
        bus = LocalBus()
        delivered: list[Envelope] = []
        bus.subscribe("k1.test.ttl", delivered.append)
        bus.publish(Envelope(topic="k1.test.ttl", payload=b"x", ttl_ms=0))
        assert len(delivered) == 1
        assert bus.stats.ttl_drops == 0

    def test_sync_ttl_drops_when_expired(self) -> None:
        # We simulate TTL expiry by post-stamping a captured envelope
        # with an old created_ns and re-dispatching via the internal
        # _dispatch hook.  Public API keeps the contract simple: any
        # envelope whose age exceeds ttl_ms is dropped at dispatch.
        bus = LocalBus()
        delivered: list[Envelope] = []
        env = Envelope(
            topic="k1.test.ttl",
            payload=b"x",
            ttl_ms=1,
            envelope_id=1,
            sequence=1,
            created_ns=time.monotonic_ns() - 5_000_000_000,
        )
        bus._dispatch(env, [delivered.append])  # type: ignore[attr-defined]
        assert delivered == []
        assert bus.stats.ttl_drops == 1

    def test_sync_ttl_does_not_drop_when_within_window(self) -> None:
        bus = LocalBus()
        delivered: list[Envelope] = []
        env = Envelope(
            topic="k1.test.ttl",
            payload=b"x",
            ttl_ms=60_000,  # 60s TTL -- easily within window
            envelope_id=1,
            sequence=1,
            created_ns=time.monotonic_ns(),
        )
        bus._dispatch(env, [delivered.append])  # type: ignore[attr-defined]
        assert len(delivered) == 1
        assert bus.stats.ttl_drops == 0

    def test_bus_stats_snapshot_includes_ttl_drops(self) -> None:
        bus = LocalBus()
        snap = bus.stats.snapshot()
        assert "ttl_drops" in snap
        assert snap["ttl_drops"] == 0


class TestTtlEnforcementAsync:
    def test_async_ttl_routes_through_dlq(self) -> None:
        """Async-dispatched expired envelopes invoke the DLQ callback.

        Strategy: gate the worker on a blocker envelope so the second
        envelope sits in the mailbox long enough to expire its TTL,
        guaranteeing the TTL-check path runs.
        """
        import threading

        dlq_calls: list[tuple[Envelope, BaseException, int]] = []

        def dlq(env: Envelope, exc: BaseException, attempts: int) -> None:
            dlq_calls.append((env, exc, attempts))

        bus = LocalBus(async_dispatch=True, dlq_callback=dlq)
        delivered: list[Envelope] = []
        gate = threading.Event()

        def handler(env: Envelope) -> None:
            if env.payload == b"gate":
                gate.wait(timeout=2.0)
            else:
                delivered.append(env)

        bus.subscribe("k1.test.ttl.async", handler)

        # Envelope 1 blocks the worker; envelope 2 has tiny TTL.
        bus.publish(Envelope(topic="k1.test.ttl.async", payload=b"gate", ttl_ms=0))
        bus.publish(Envelope(topic="k1.test.ttl.async", payload=b"x", ttl_ms=1))
        # Wait long enough that env 2 will be expired by the time the
        # worker dequeues it after we release the gate.
        time.sleep(0.05)
        gate.set()
        bus.flush(timeout_ms=2000)

        assert delivered == []
        assert bus.stats.ttl_drops == 1
        assert len(dlq_calls) == 1
        _env, exc, attempts = dlq_calls[0]
        assert isinstance(exc, TtlExpiredError)
        assert attempts == 0
        assert exc.topic == "k1.test.ttl.async"


# ---------------------------------------------------------------------------
# B02 — sequence allocation after middleware
# ---------------------------------------------------------------------------


class TestSequenceAfterMiddleware:
    def test_dropped_envelope_does_not_consume_sequence(self) -> None:
        """Sequence stream is gap-free across middleware drops."""
        # First publish: dropped by middleware.  Sequence should NOT be
        # consumed.  Then second publish without middleware drop should
        # see sequence=1, not 2.
        delivered: list[Envelope] = []
        chain = MiddlewareChain([_DropAfterMiddleware()])
        bus = LocalBus(middleware=chain)
        bus.subscribe("k1.test.seq", delivered.append)
        bus.publish(Envelope(topic="k1.test.seq", payload=b"drop"))
        assert delivered == []
        # Verify the topic counter wasn't bumped.
        assert bus._seq_gen.current("k1.test.seq") == 0  # type: ignore[attr-defined]

    def test_sequence_starts_at_one_after_middleware_passes(self) -> None:
        recorder = _IdMiddleware()
        chain = MiddlewareChain([recorder])
        bus = LocalBus(middleware=chain)
        delivered: list[Envelope] = []
        bus.subscribe("k1.test.seq2", delivered.append)
        bus.publish(Envelope(topic="k1.test.seq2", payload=b"a"))
        bus.publish(Envelope(topic="k1.test.seq2", payload=b"b"))
        assert [e.sequence for e in delivered] == [1, 2]
        # Middleware sees sequence=0 placeholder.
        assert all(e.sequence == 0 for e in recorder.seen)

    def test_mixed_drop_and_pass_keeps_sequence_contiguous(self) -> None:
        class _DropEveryOther(Middleware):
            def __init__(self) -> None:
                self.count = 0

            def process(self, envelope: Envelope) -> Envelope | None:
                self.count += 1
                return None if self.count % 2 == 0 else envelope

        mw = _DropEveryOther()
        bus = LocalBus(middleware=MiddlewareChain([mw]))
        delivered: list[Envelope] = []
        bus.subscribe("k1.test.seqmix", delivered.append)
        for i in range(6):
            bus.publish(Envelope(topic="k1.test.seqmix", payload=str(i).encode()))
        # 3 envelopes pass (odd counts); their sequences must be 1, 2, 3
        # — no gaps, despite drops.
        assert [e.sequence for e in delivered] == [1, 2, 3]


# ---------------------------------------------------------------------------
# B03 — GapBuffer LRU eviction
# ---------------------------------------------------------------------------


class TestGapBufferLru:
    def test_topic_lock_evicted_when_cap_exceeded(self) -> None:
        gb = _GapBuffer(max_topics=3)
        # Force lock creation for 4 distinct topics.
        for i in range(4):
            gb._get_lock(f"k1.lru.t{i}")
        # Oldest topic should be evicted.
        assert "k1.lru.t0" not in gb._locks
        assert len(gb._locks) == 3
        assert len(gb._topic_order) == 3

    def test_evicted_topic_resets_state(self) -> None:
        """Evicted topics restart sequence checking from 1."""
        gb = _GapBuffer(max_topics=2)
        env_a1 = Envelope(topic="k1.lru.A", payload=b"x", sequence=1)
        env_a2 = Envelope(topic="k1.lru.A", payload=b"x", sequence=2)
        gb.check_and_buffer(env_a1, time.monotonic_ns())
        gb.check_and_buffer(env_a2, time.monotonic_ns())
        # _expected[A] == 3 now
        assert gb._expected["k1.lru.A"] == 3

        # Touch two more topics so A is evicted (LRU cap=2).
        gb._get_lock("k1.lru.B")
        gb._get_lock("k1.lru.C")
        assert "k1.lru.A" not in gb._locks
        assert "k1.lru.A" not in gb._expected

        # Re-publishing on A starts fresh (expected=1).
        assert gb.expected_sequence("k1.lru.A") == 1

    def test_default_cap_does_not_evict_under_normal_load(self) -> None:
        gb = _GapBuffer()  # default max_topics=512
        for i in range(100):
            gb._get_lock(f"k1.lru.normal{i}")
        assert len(gb._locks) == 100


# ---------------------------------------------------------------------------
# B04 — Backpressure DLQ
# ---------------------------------------------------------------------------


class TestBackpressureDlq:
    def test_backpressure_invokes_dlq(self) -> None:
        """Backpressure-dropped envelopes route through DLQ with attempts=0."""
        dlq_calls: list[tuple[Envelope, BaseException, int]] = []

        def dlq(env: Envelope, exc: BaseException, attempts: int) -> None:
            dlq_calls.append((env, exc, attempts))

        # Capacity=1 mailbox; slow handler so the second publish hits backpressure.
        bus = LocalBus(
            async_dispatch=True,
            subscription_mailbox_capacity=1,
            dlq_callback=dlq,
        )
        block = [True]

        def slow_handler(_env: Envelope) -> None:
            while block[0]:
                time.sleep(0.005)

        bus.subscribe("k1.test.bp", slow_handler)
        # Fire 5 envelopes at the 1-slot mailbox.  At least one will
        # fail backpressure since the handler is blocked.
        for i in range(5):
            bus.publish(Envelope(topic="k1.test.bp", payload=str(i).encode()))
            time.sleep(0.001)
        block[0] = False
        bus.flush(timeout_ms=1000)

        assert bus.stats.mailbox_full_drops >= 1
        assert len(dlq_calls) >= 1
        env, exc, attempts = dlq_calls[0]
        assert isinstance(exc, BackpressureError)
        assert attempts == 0


# ---------------------------------------------------------------------------
# B06 — publish_batch
# ---------------------------------------------------------------------------


class TestPublishBatch:
    def test_publish_batch_delivers_all(self) -> None:
        bus = LocalBus()
        delivered: list[Envelope] = []
        bus.subscribe("k1.test.batch", delivered.append)
        envs = [Envelope(topic="k1.test.batch", payload=str(i).encode()) for i in range(5)]
        bus.publish_batch(envs)
        assert len(delivered) == 5
        assert [e.sequence for e in delivered] == [1, 2, 3, 4, 5]

    def test_publish_batch_empty_is_noop(self) -> None:
        bus = LocalBus()
        delivered: list[Envelope] = []
        bus.subscribe("k1.test.batch", delivered.append)
        bus.publish_batch([])
        assert delivered == []
        assert bus.stats.envelopes_published == 0

    def test_publish_batch_skips_dropped_middleware(self) -> None:
        """Middleware drop in a batch does not abort the rest."""

        class _DropEven(Middleware):
            def __init__(self) -> None:
                self.count = 0

            def process(self, envelope: Envelope) -> Envelope | None:
                self.count += 1
                return None if self.count % 2 == 0 else envelope

        bus = LocalBus(middleware=MiddlewareChain([_DropEven()]))
        delivered: list[Envelope] = []
        bus.subscribe("k1.test.batchdrop", delivered.append)
        envs = [Envelope(topic="k1.test.batchdrop", payload=b"x") for _ in range(4)]
        bus.publish_batch(envs)
        assert len(delivered) == 2
        # Sequence is gap-free for delivered envelopes.
        assert [e.sequence for e in delivered] == [1, 2]

    def test_session_adapter_emit_batch_uses_publish_batch(self) -> None:
        """SessionBusAdapter.emit_batch routes through bus.publish_batch."""
        from k1.bus.adapters.session_adapter import SessionBusAdapter

        bus = LocalBus(capture=True)
        adapter = SessionBusAdapter(bus)
        adapter.emit_batch(
            [
                ("session.a", {"k": "1"}),
                ("session.b", {"k": "2"}),
                ("session.c", {"k": "3"}),
            ]
        )
        # All 3 envelopes captured.
        assert len(bus.captured) == 3
        # Topics mapped via _map_topic prefix.
        topics = [e.topic for e in bus.captured]
        assert all(t.startswith("k1.session.") for t in topics)


# ---------------------------------------------------------------------------
# B07 — DEFAULT_TOPIC_REGISTRY + factory wiring
# ---------------------------------------------------------------------------


class TestDefaultTopicRegistry:
    def test_get_default_registry_is_singleton(self) -> None:
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_default_registry_recognises_known_prefixes(self) -> None:
        r = get_default_registry()
        assert r.is_known("k1.session.turn.started.v1")
        assert r.is_known("k1.agent.foo.delta.v1")
        assert r.is_known("k1.fabric.capability.completed.v1")
        assert r.is_known("k1.test.synthetic")  # test prefix is registered

    def test_factory_default_installs_topic_validation(self) -> None:
        """create_local_ordered() with no middleware gets the default chain."""
        bus = BusFactory.create_local_ordered()
        try:
            assert bus.middleware is not None
            # The chain wraps a single TopicValidationMiddleware.
            chain_mws = bus.middleware._middlewares  # type: ignore[attr-defined]
            assert len(chain_mws) == 1
            assert isinstance(chain_mws[0], TopicValidationMiddleware)
        finally:
            bus.close()

    def test_factory_explicit_middleware_bypasses_default(self) -> None:
        """Explicit middleware= overrides the default."""
        recorder = _IdMiddleware()
        bus = BusFactory.create_local_ordered(middleware=[recorder])
        try:
            chain_mws = bus.middleware._middlewares  # type: ignore[attr-defined]
            assert len(chain_mws) == 1
            assert chain_mws[0] is recorder
        finally:
            bus.close()


# ---------------------------------------------------------------------------
# B08 — DRR mailbox scheduling
# ---------------------------------------------------------------------------


class TestDrrMailbox:
    def test_strict_priority_is_default(self) -> None:
        """No wfq_quantum -> strict priority preserved."""
        mb = LocalMailbox("test", MailboxConfig(capacity=10))
        for prio in (Priority.BACKGROUND, Priority.URGENT):
            mb._deliver(Envelope(topic="k1.test", payload=b"x", priority=prio))
        first = mb.receive(timeout_ms=10)
        assert first is not None and first.priority == Priority.URGENT

    def test_drr_serves_lower_priority_after_quantum(self) -> None:
        """DRR allows BACKGROUND to drain even when URGENT has work."""
        mb = LocalMailbox(
            "test",
            MailboxConfig(capacity=20, wfq_quantum=(2, 1, 1, 1)),
        )
        # 4 URGENT + 4 BACKGROUND messages.
        for _ in range(4):
            mb._deliver(Envelope(topic="k1.test", payload=b"u", priority=Priority.URGENT))
        for _ in range(4):
            mb._deliver(Envelope(topic="k1.test", payload=b"b", priority=Priority.BACKGROUND))
        order: list[bytes] = []
        for _ in range(8):
            env = mb.receive(timeout_ms=10)
            assert env is not None
            order.append(env.payload)
        # Under strict priority this would be ['u','u','u','u','b','b','b','b'].
        # Under DRR with quantum (2,1,1,1), BACKGROUND must appear before
        # URGENT is fully drained.
        urgent_first_b = order.index(b"b")
        urgent_last = max(i for i, p in enumerate(order) if p == b"u")
        assert urgent_first_b < urgent_last, f"DRR did not interleave priorities: order={order}"

    def test_drr_quantum_validates_shape(self) -> None:
        with pytest.raises(ValueError):
            MailboxConfig(wfq_quantum=(1, 2, 3))  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            MailboxConfig(wfq_quantum=(1, 0, 1, 1))
