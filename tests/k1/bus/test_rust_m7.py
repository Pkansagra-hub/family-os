"""
Tests for V2-M7: Rust Mailbox + Dead-Letter Queue.

Coverage:
    RustMailbox:
        - Construction (WFQ / FIFO modes)
        - WFQ priority ordering (URGENT > REALTIME > INTERACTIVE > BACKGROUND)
        - FIFO ordering (ignores priority)
        - Same-priority FIFO within level
        - Interleaving priority injection
        - Capacity enforcement (RuntimeError on full)
        - Blocking receive with timeout (GIL released)
        - Non-blocking receive returns None
        - Close prevents delivery but allows drain
        - Pending count
        - Depth-by-priority observability
        - delivered_count / received_count counters
        - repr

    RustMailboxRouter:
        - Register creates mailbox, returns RustMailbox
        - Deliver to registered actor succeeds
        - Deliver to unknown actor raises ValueError
        - Deliver to full mailbox raises RuntimeError
        - Double register raises ValueError
        - Empty actor_id rejected
        - Unregister returns True and closes mailbox
        - Unregister unknown returns False
        - registered_actors list
        - Close router prevents new deliveries
        - stats_snapshot observability
        - mailbox_for observability

    DeadLetterQueue:
        - Construction
        - Push and drain
        - Peek without removing
        - Bounded drops oldest (ring buffer)
        - All 5 reason strings
        - DLQ integration with router (backpressure -> DLQ)
        - Capacity / depth / total_pushed / total_dropped

    Thread safety:
        - Concurrent deliver + receive
        - Concurrent register + deliver

    Parity:
        - RustMailbox WFQ vs Python LocalMailbox strict priority
          (produces same results for small batches)
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from k1_bus_core import DeadLetterQueue, RustEnvelope, RustMailbox, RustMailboxRouter

# ===================================================================
# Helpers
# ===================================================================


def _env(
    topic: str = "k1.test",
    payload: bytes = b"data",
    priority: int = 2,
) -> RustEnvelope:
    """Create a RustEnvelope for testing."""
    return RustEnvelope(topic=topic, payload=payload, priority=priority)


# ===================================================================
# RustMailbox -- Construction
# ===================================================================


class TestRustMailboxConstruction:
    def test_default_construction(self) -> None:
        mb = RustMailbox("agent1")
        assert mb.actor_id == "agent1"
        assert mb.capacity == 256
        assert mb.pending() == 0
        assert mb.closed is False

    def test_custom_capacity(self) -> None:
        mb = RustMailbox("a", capacity=42)
        assert mb.capacity == 42

    def test_fifo_mode(self) -> None:
        mb = RustMailbox("a", priority_wfq=False)
        assert "FIFO" in repr(mb)

    def test_wfq_mode(self) -> None:
        mb = RustMailbox("a", priority_wfq=True)
        assert "WFQ" in repr(mb)

    def test_empty_actor_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            RustMailbox("")

    def test_zero_capacity_rejected(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            RustMailbox("a", capacity=0)

    def test_custom_weights(self) -> None:
        mb = RustMailbox("a", weights=[8, 6, 4, 2])
        assert mb.actor_id == "a"

    def test_wrong_weights_count(self) -> None:
        with pytest.raises(ValueError, match="4 weights"):
            RustMailbox("a", weights=[1, 2, 3])


# ===================================================================
# RustMailbox -- FIFO mode
# ===================================================================


class TestRustMailboxFIFO:
    def test_receive_empty_returns_none(self) -> None:
        mb = RustMailbox("a", priority_wfq=False)
        assert mb.receive() is None
        assert mb.pending() == 0

    def test_fifo_delivery_order(self) -> None:
        mb = RustMailbox("a", capacity=10, priority_wfq=False)
        for i in range(5):
            mb.deliver(_env(payload=f"msg{i}".encode()))
        assert mb.pending() == 5
        for i in range(5):
            env = mb.receive()
            assert env is not None
            assert bytes(env.payload) == f"msg{i}".encode()
        assert mb.receive() is None

    def test_fifo_ignores_priority(self) -> None:
        mb = RustMailbox("a", capacity=10, priority_wfq=False)
        mb.deliver(_env(priority=3))  # BACKGROUND first
        mb.deliver(_env(priority=0))  # URGENT second
        first = mb.receive()
        assert first is not None
        assert first.priority == 3  # BACKGROUND came first (FIFO)

    def test_depth_by_priority_empty_in_fifo(self) -> None:
        mb = RustMailbox("a", priority_wfq=False)
        depths = mb.depth_by_priority()
        assert depths == {}


# ===================================================================
# RustMailbox -- WFQ priority mode
# ===================================================================


class TestRustMailboxWFQ:
    def test_urgent_before_background(self) -> None:
        mb = RustMailbox("a", capacity=10)
        mb.deliver(_env(priority=3, payload=b"bg"))
        mb.deliver(_env(priority=0, payload=b"urg"))

        first = mb.receive()
        assert bytes(first.payload) == b"urg"
        second = mb.receive()
        assert bytes(second.payload) == b"bg"

    def test_all_four_levels(self) -> None:
        mb = RustMailbox("a", capacity=20)
        mb.deliver(_env(priority=3, payload=b"bg"))
        mb.deliver(_env(priority=2, payload=b"int"))
        mb.deliver(_env(priority=1, payload=b"rt"))
        mb.deliver(_env(priority=0, payload=b"urg"))

        results = [bytes(mb.receive().payload) for _ in range(4)]
        assert results == [b"urg", b"rt", b"int", b"bg"]

    def test_same_priority_fifo(self) -> None:
        mb = RustMailbox("a", capacity=10)
        mb.deliver(_env(priority=2, payload=b"first"))
        mb.deliver(_env(priority=2, payload=b"second"))
        mb.deliver(_env(priority=2, payload=b"third"))

        results = [bytes(mb.receive().payload) for _ in range(3)]
        assert results == [b"first", b"second", b"third"]

    def test_interleaving(self) -> None:
        mb = RustMailbox("a", capacity=10)
        mb.deliver(_env(priority=2, payload=b"int1"))
        mb.deliver(_env(priority=2, payload=b"int2"))
        mb.deliver(_env(priority=0, payload=b"urg1"))

        first = mb.receive()
        assert bytes(first.payload) == b"urg1"

    def test_depth_by_priority(self) -> None:
        mb = RustMailbox("a", capacity=20)
        mb.deliver(_env(priority=0))
        mb.deliver(_env(priority=0))
        mb.deliver(_env(priority=3))

        depths = mb.depth_by_priority()
        assert depths["URGENT"] == 2
        assert depths["REALTIME"] == 0
        assert depths["INTERACTIVE"] == 0
        assert depths["BACKGROUND"] == 1

    def test_depth_updates_after_receive(self) -> None:
        mb = RustMailbox("a", capacity=10)
        mb.deliver(_env(priority=0))
        mb.deliver(_env(priority=3))

        mb.receive()  # Should dequeue URGENT
        depths = mb.depth_by_priority()
        assert depths["URGENT"] == 0
        assert depths["BACKGROUND"] == 1


# ===================================================================
# RustMailbox -- Capacity / backpressure
# ===================================================================


class TestRustMailboxCapacity:
    def test_at_capacity_raises(self) -> None:
        mb = RustMailbox("a", capacity=3)
        for _ in range(3):
            mb.deliver(_env())
        with pytest.raises(RuntimeError, match="full"):
            mb.deliver(_env())

    def test_drain_frees_capacity(self) -> None:
        mb = RustMailbox("a", capacity=2)
        mb.deliver(_env(payload=b"1"))
        mb.deliver(_env(payload=b"2"))
        with pytest.raises(RuntimeError):
            mb.deliver(_env(payload=b"3"))
        mb.receive()  # free one slot
        mb.deliver(_env(payload=b"3"))
        assert mb.pending() == 2

    def test_capacity_one(self) -> None:
        mb = RustMailbox("a", capacity=1)
        mb.deliver(_env())
        assert mb.pending() == 1
        with pytest.raises(RuntimeError):
            mb.deliver(_env())


# ===================================================================
# RustMailbox -- Blocking receive
# ===================================================================


class TestRustMailboxBlocking:
    def test_blocking_receive_wakeup(self) -> None:
        mb = RustMailbox("a", capacity=10)
        result: list = []

        def receiver() -> None:
            env = mb.receive(timeout_ms=2000)
            if env is not None:
                result.append(env)

        t = threading.Thread(target=receiver)
        t.start()
        time.sleep(0.02)
        mb.deliver(_env(payload=b"wakeup"))
        t.join(timeout=2)
        assert not t.is_alive()
        assert len(result) == 1
        assert bytes(result[0].payload) == b"wakeup"

    def test_blocking_receive_timeout(self) -> None:
        mb = RustMailbox("a", capacity=10)
        start = time.monotonic()
        result = mb.receive(timeout_ms=50)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed >= 0.04

    def test_nonblocking_immediate(self) -> None:
        mb = RustMailbox("a", capacity=10)
        start = time.monotonic()
        result = mb.receive(timeout_ms=0)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 0.01


# ===================================================================
# RustMailbox -- Close / lifecycle
# ===================================================================


class TestRustMailboxClose:
    def test_close_prevents_delivery(self) -> None:
        mb = RustMailbox("a", capacity=10)
        mb.deliver(_env(payload=b"before"))
        mb.close()
        with pytest.raises(ValueError, match="closed"):
            mb.deliver(_env(payload=b"after"))

    def test_close_allows_drain(self) -> None:
        mb = RustMailbox("a", capacity=10)
        mb.deliver(_env(payload=b"drain-me"))
        mb.close()
        env = mb.receive()
        assert env is not None
        assert bytes(env.payload) == b"drain-me"

    def test_closed_property(self) -> None:
        mb = RustMailbox("a")
        assert mb.closed is False
        mb.close()
        assert mb.closed is True


# ===================================================================
# RustMailbox -- Observability
# ===================================================================


class TestRustMailboxObservability:
    def test_delivered_received_counts(self) -> None:
        mb = RustMailbox("a", capacity=10)
        assert mb.delivered_count == 0
        assert mb.received_count == 0
        mb.deliver(_env())
        mb.deliver(_env())
        assert mb.delivered_count == 2
        assert mb.received_count == 0
        mb.receive()
        assert mb.received_count == 1

    def test_actor_id_property(self) -> None:
        mb = RustMailbox("orchestrator")
        assert mb.actor_id == "orchestrator"

    def test_capacity_property(self) -> None:
        mb = RustMailbox("a", capacity=42)
        assert mb.capacity == 42

    def test_repr_wfq(self) -> None:
        mb = RustMailbox("test", capacity=100)
        r = repr(mb)
        assert "test" in r
        assert "100" in r
        assert "WFQ" in r

    def test_repr_fifo(self) -> None:
        mb = RustMailbox("test", capacity=5, priority_wfq=False)
        assert "FIFO" in repr(mb)


# ===================================================================
# RustMailboxRouter -- Registration
# ===================================================================


class TestRustMailboxRouterRegistration:
    def test_register_returns_mailbox(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("concierge", capacity=100)
        assert isinstance(mb, RustMailbox)
        assert mb.actor_id == "concierge"

    def test_register_default_config(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("agent1")
        assert mb.capacity == 256

    def test_double_register_raises(self) -> None:
        router = RustMailboxRouter()
        router.register("agent1")
        with pytest.raises(ValueError, match="already registered"):
            router.register("agent1")

    def test_empty_actor_id_rejected(self) -> None:
        router = RustMailboxRouter()
        with pytest.raises(ValueError, match="empty"):
            router.register("")

    def test_unregister_existing(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("agent1")
        result = router.unregister("agent1")
        assert result is True
        assert mb.closed is True
        assert "agent1" not in router.registered_actors()

    def test_unregister_unknown_returns_false(self) -> None:
        router = RustMailboxRouter()
        assert router.unregister("ghost") is False

    def test_registered_actors(self) -> None:
        router = RustMailboxRouter()
        router.register("a")
        router.register("b")
        router.register("c")
        assert sorted(router.registered_actors()) == ["a", "b", "c"]

    def test_register_after_unregister(self) -> None:
        router = RustMailboxRouter()
        router.register("agent1")
        router.unregister("agent1")
        mb = router.register("agent1")
        assert mb.actor_id == "agent1"


# ===================================================================
# RustMailboxRouter -- Deliver
# ===================================================================


class TestRustMailboxRouterDeliver:
    def test_deliver_and_receive(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("orch", capacity=10)
        router.deliver("orch", _env(payload=b"hello"))
        env = mb.receive()
        assert env is not None
        assert bytes(env.payload) == b"hello"

    def test_deliver_to_unknown_raises(self) -> None:
        router = RustMailboxRouter()
        with pytest.raises(ValueError, match="Unknown actor"):
            router.deliver("nobody", _env())

    def test_deliver_to_full_mailbox_raises(self) -> None:
        router = RustMailboxRouter()
        router.register("small", capacity=2)
        router.deliver("small", _env())
        router.deliver("small", _env())
        with pytest.raises(RuntimeError, match="full"):
            router.deliver("small", _env())

    def test_deliver_after_unregister_raises(self) -> None:
        router = RustMailboxRouter()
        router.register("victim")
        router.unregister("victim")
        with pytest.raises(ValueError, match="Unknown actor"):
            router.deliver("victim", _env())

    def test_deliver_multiple_actors(self) -> None:
        router = RustMailboxRouter()
        mb_a = router.register("a", capacity=10)
        mb_b = router.register("b", capacity=10)
        router.deliver("a", _env(payload=b"for-a"))
        router.deliver("b", _env(payload=b"for-b"))

        assert bytes(mb_a.receive().payload) == b"for-a"
        assert bytes(mb_b.receive().payload) == b"for-b"
        assert mb_a.pending() == 0
        assert mb_b.pending() == 0

    def test_deliver_preserves_priority(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("orch", capacity=10)
        router.deliver("orch", _env(priority=3, payload=b"bg"))
        router.deliver("orch", _env(priority=0, payload=b"urg"))
        first = mb.receive()
        assert bytes(first.payload) == b"urg"


# ===================================================================
# RustMailboxRouter -- Close / lifecycle
# ===================================================================


class TestRustMailboxRouterClose:
    def test_close_prevents_delivery(self) -> None:
        router = RustMailboxRouter()
        router.register("a")
        router.close()
        with pytest.raises(ValueError, match="closed"):
            router.deliver("a", _env())

    def test_close_prevents_registration(self) -> None:
        router = RustMailboxRouter()
        router.close()
        with pytest.raises(ValueError, match="closed"):
            router.register("new")

    def test_close_closes_all_mailboxes(self) -> None:
        router = RustMailboxRouter()
        mb_a = router.register("a")
        mb_b = router.register("b")
        router.close()
        assert mb_a.closed is True
        assert mb_b.closed is True

    def test_closed_property(self) -> None:
        router = RustMailboxRouter()
        assert router.closed is False
        router.close()
        assert router.closed is True

    def test_drain_after_close(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("a", capacity=10)
        router.deliver("a", _env(payload=b"pending"))
        router.close()
        env = mb.receive()
        assert env is not None
        assert bytes(env.payload) == b"pending"


# ===================================================================
# RustMailboxRouter -- Observability
# ===================================================================


class TestRustMailboxRouterObservability:
    def test_actor_count(self) -> None:
        router = RustMailboxRouter()
        assert router.actor_count == 0
        router.register("a")
        router.register("b")
        assert router.actor_count == 2
        router.unregister("a")
        assert router.actor_count == 1

    def test_mailbox_for(self) -> None:
        router = RustMailboxRouter()
        router.register("target")
        found = router.mailbox_for("target")
        assert found is not None
        assert found.actor_id == "target"

    def test_mailbox_for_unknown_returns_none(self) -> None:
        router = RustMailboxRouter()
        assert router.mailbox_for("ghost") is None

    def test_stats_snapshot(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("a", capacity=10)
        router.deliver("a", _env())
        router.deliver("a", _env())
        mb.receive()

        snap = router.stats_snapshot()
        assert "a" in snap
        assert snap["a"]["pending"] == 1
        assert snap["a"]["delivered"] == 2
        assert snap["a"]["received"] == 1
        assert snap["a"]["capacity"] == 10

    def test_repr(self) -> None:
        router = RustMailboxRouter()
        router.register("x")
        r = repr(router)
        assert "RustMailboxRouter" in r
        assert "1" in r


# ===================================================================
# DeadLetterQueue
# ===================================================================


class TestDeadLetterQueue:
    def test_construction(self) -> None:
        dlq = DeadLetterQueue(capacity=100)
        assert dlq.depth == 0
        assert dlq.total_pushed == 0
        assert dlq.total_dropped == 0
        assert dlq.capacity == 100

    def test_zero_capacity_rejected(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            DeadLetterQueue(capacity=0)

    def test_push_and_drain(self) -> None:
        dlq = DeadLetterQueue(capacity=100)
        dlq.push(_env(payload=b"one"), "BackpressureFull")
        dlq.push(_env(payload=b"two"), "HandlerError")

        assert dlq.depth == 2
        assert dlq.total_pushed == 2

        entries = dlq.drain()
        assert len(entries) == 2
        assert bytes(entries[0][0].payload) == b"one"
        assert entries[0][1] == "BackpressureFull"
        assert bytes(entries[1][0].payload) == b"two"
        assert entries[1][1] == "HandlerError"

        assert dlq.depth == 0

    def test_peek_does_not_remove(self) -> None:
        dlq = DeadLetterQueue(capacity=100)
        dlq.push(_env(payload=b"peek-me"), "TtlExpired")

        peeked = dlq.peek(5)
        assert len(peeked) == 1
        assert bytes(peeked[0][0].payload) == b"peek-me"
        assert peeked[0][1] == "TtlExpired"
        assert dlq.depth == 1  # Still there

    def test_bounded_drops_oldest(self) -> None:
        dlq = DeadLetterQueue(capacity=3)
        dlq.push(_env(payload=b"a"), "BackpressureFull")
        dlq.push(_env(payload=b"b"), "BackpressureFull")
        dlq.push(_env(payload=b"c"), "BackpressureFull")
        assert dlq.depth == 3
        assert dlq.total_dropped == 0

        # Push 4th -- "a" should be dropped
        dlq.push(_env(payload=b"d"), "HandlerError")
        assert dlq.depth == 3
        assert dlq.total_dropped == 1

        entries = dlq.drain()
        payloads = [bytes(e[0].payload) for e in entries]
        assert payloads == [b"b", b"c", b"d"]

    def test_all_reason_strings(self) -> None:
        reasons = [
            "BackpressureFull",
            "HandlerError",
            "TtlExpired",
            "CircuitOpen",
            "MiddlewareDropped",
        ]
        dlq = DeadLetterQueue(capacity=100)
        for r in reasons:
            dlq.push(_env(), r)

        entries = dlq.drain()
        assert [e[1] for e in entries] == reasons

    def test_invalid_reason_raises(self) -> None:
        dlq = DeadLetterQueue(capacity=100)
        with pytest.raises(ValueError, match="Unknown DLQ reason"):
            dlq.push(_env(), "InvalidReason")

    def test_repr(self) -> None:
        dlq = DeadLetterQueue(capacity=50)
        dlq.push(_env(), "BackpressureFull")
        r = repr(dlq)
        assert "DeadLetterQueue" in r
        assert "1" in r
        assert "50" in r


# ===================================================================
# DLQ Integration with Router
# ===================================================================


class TestDLQRouterIntegration:
    def test_backpressure_routes_to_dlq(self) -> None:
        """When mailbox is full, rejected envelopes go to DLQ."""
        router = RustMailboxRouter()
        dlq = DeadLetterQueue(capacity=100)
        router.set_dlq(dlq)

        router.register("constrained", capacity=2)
        router.deliver("constrained", _env(payload=b"ok1"))
        router.deliver("constrained", _env(payload=b"ok2"))

        # Third delivery should fail AND route to DLQ
        with pytest.raises(RuntimeError, match="full"):
            router.deliver("constrained", _env(payload=b"rejected"))

        assert dlq.depth == 1
        entries = dlq.drain()
        assert bytes(entries[0][0].payload) == b"rejected"
        assert entries[0][1] == "BackpressureFull"

    def test_no_dlq_attached_just_raises(self) -> None:
        """Without DLQ, backpressure just raises normally."""
        router = RustMailboxRouter()
        router.register("small", capacity=1)
        router.deliver("small", _env())
        with pytest.raises(RuntimeError, match="full"):
            router.deliver("small", _env())


# ===================================================================
# Thread safety
# ===================================================================


class TestMailboxThreadSafety:
    def test_concurrent_deliver_and_receive(self) -> None:
        """Multiple threads delivering while one thread receives."""
        router = RustMailboxRouter()
        mb = router.register("target", capacity=5000)
        errors: list[str] = []
        received: list = []
        stop = threading.Event()

        n_senders = 4
        n_per_sender = 200

        def sender(thread_id: int) -> None:
            for i in range(n_per_sender):
                try:
                    router.deliver(
                        "target",
                        _env(payload=f"t{thread_id}-{i}".encode()),
                    )
                except Exception as e:
                    errors.append(f"Sender {thread_id}: {e}")

        def receiver() -> None:
            while not stop.is_set() or mb.pending() > 0:
                env = mb.receive(timeout_ms=10)
                if env is not None:
                    received.append(env)

        with ThreadPoolExecutor(max_workers=n_senders + 1) as pool:
            futures = [pool.submit(sender, i) for i in range(n_senders)]
            recv_future = pool.submit(receiver)

            for f in futures:
                f.result()
            stop.set()
            recv_future.result()

        assert errors == [], f"Thread errors: {errors}"
        assert len(received) == n_senders * n_per_sender

    def test_concurrent_register_and_deliver(self) -> None:
        """Register + deliver from different threads."""
        router = RustMailboxRouter()
        errors: list[str] = []

        def registerer() -> None:
            for i in range(20):
                try:
                    router.register(f"actor-{i}", capacity=100)
                except Exception as e:
                    errors.append(f"Register: {e}")

        def deliverer() -> None:
            time.sleep(0.01)
            for i in range(20):
                actor_id = f"actor-{i}"
                try:
                    if actor_id in router.registered_actors():
                        router.deliver(actor_id, _env())
                except (ValueError, RuntimeError):
                    pass  # Race with registration
                except Exception as e:
                    errors.append(f"Deliver: {e}")

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(registerer)
            f2 = pool.submit(deliverer)
            f1.result()
            f2.result()

        assert errors == []

    def test_blocking_receive_wakeup_concurrency(self) -> None:
        """Multiple receivers blocking, single producer wakes them."""
        router = RustMailboxRouter()
        mb = router.register("shared", capacity=100)
        results: list = []
        lock = threading.Lock()

        n_receivers = 4
        n_messages = 20

        def blocker() -> None:
            while True:
                env = mb.receive(timeout_ms=500)
                if env is None:
                    break
                with lock:
                    results.append(env)

        def producer() -> None:
            for i in range(n_messages):
                router.deliver("shared", _env(payload=f"msg{i}".encode()))
                time.sleep(0.001)

        with ThreadPoolExecutor(max_workers=n_receivers + 1) as pool:
            recv_futures = [pool.submit(blocker) for _ in range(n_receivers)]
            pool.submit(producer).result()
            for f in recv_futures:
                f.result(timeout=5)

        assert len(results) == n_messages


# ===================================================================
# Parity -- Rust WFQ vs Python strict priority
# ===================================================================


class TestMailboxParity:
    """Verify that Rust WFQ produces same results as Python strict
    priority for small batch patterns (where they are equivalent)."""

    def test_four_priorities_same_order(self) -> None:
        """Both implementations deliver URGENT > RT > INT > BG."""
        from k1.bus.envelope import Envelope, Priority
        from k1.bus.impl.local_mailbox import LocalMailbox
        from k1.bus.ports.mailbox import MailboxConfig

        # Python V1
        py_mb = LocalMailbox("test", MailboxConfig(capacity=20))
        py_mb._deliver(Envelope(topic="t", priority=Priority.BACKGROUND, payload=b"bg"))
        py_mb._deliver(Envelope(topic="t", priority=Priority.INTERACTIVE, payload=b"int"))
        py_mb._deliver(Envelope(topic="t", priority=Priority.REALTIME, payload=b"rt"))
        py_mb._deliver(Envelope(topic="t", priority=Priority.URGENT, payload=b"urg"))

        py_results = []
        for _ in range(4):
            env = py_mb.receive()
            py_results.append(env.payload)

        # Rust V2
        rs_mb = RustMailbox("test", capacity=20)
        rs_mb.deliver(_env(priority=3, payload=b"bg"))
        rs_mb.deliver(_env(priority=2, payload=b"int"))
        rs_mb.deliver(_env(priority=1, payload=b"rt"))
        rs_mb.deliver(_env(priority=0, payload=b"urg"))

        rs_results = []
        for _ in range(4):
            env = rs_mb.receive()
            rs_results.append(bytes(env.payload))

        assert py_results == rs_results

    def test_interleaving_parity(self) -> None:
        """Both: URGENT injected last still dequeued first."""
        from k1.bus.envelope import Envelope, Priority
        from k1.bus.impl.local_mailbox import LocalMailbox
        from k1.bus.ports.mailbox import MailboxConfig

        py_mb = LocalMailbox("test", MailboxConfig(capacity=20))
        py_mb._deliver(Envelope(topic="t", priority=Priority.INTERACTIVE, payload=b"int1"))
        py_mb._deliver(Envelope(topic="t", priority=Priority.INTERACTIVE, payload=b"int2"))
        py_mb._deliver(Envelope(topic="t", priority=Priority.URGENT, payload=b"urg"))

        rs_mb = RustMailbox("test", capacity=20)
        rs_mb.deliver(_env(priority=2, payload=b"int1"))
        rs_mb.deliver(_env(priority=2, payload=b"int2"))
        rs_mb.deliver(_env(priority=0, payload=b"urg"))

        py_first = py_mb.receive().payload
        rs_first = bytes(rs_mb.receive().payload)
        assert py_first == rs_first == b"urg"


# ===================================================================
# Integration -- full round-trip
# ===================================================================


class TestMailboxIntegration:
    def test_full_round_trip(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("orchestrator", capacity=50)

        router.deliver("orchestrator", _env(priority=3, payload=b"bg"))
        router.deliver("orchestrator", _env(priority=0, payload=b"urg"))
        router.deliver("orchestrator", _env(priority=2, payload=b"int"))

        assert bytes(mb.receive().payload) == b"urg"
        assert bytes(mb.receive().payload) == b"int"
        assert bytes(mb.receive().payload) == b"bg"
        assert mb.receive() is None

    def test_multiple_actors_independent(self) -> None:
        router = RustMailboxRouter()
        orch = router.register("orch", capacity=10)
        plan = router.register("plan", capacity=10)

        for i in range(5):
            router.deliver("orch", _env(payload=f"orch-{i}".encode()))
        for i in range(3):
            router.deliver("plan", _env(payload=f"plan-{i}".encode()))

        assert orch.pending() == 5
        assert plan.pending() == 3

        while orch.receive() is not None:
            pass
        assert orch.pending() == 0
        assert plan.pending() == 3

    def test_unregister_lifecycle(self) -> None:
        router = RustMailboxRouter()
        mb = router.register("temp", capacity=5)
        router.deliver("temp", _env(payload=b"pending"))

        router.unregister("temp")
        assert mb.closed is True

        # Drain still works
        env = mb.receive()
        assert env is not None
        assert bytes(env.payload) == b"pending"

        # Deliver to unregistered raises
        with pytest.raises(ValueError, match="Unknown actor"):
            router.deliver("temp", _env())

    def test_backpressure_flow(self) -> None:
        """Producer backs off on backpressure."""
        router = RustMailboxRouter()
        mb = router.register("constrained", capacity=3)

        delivered = 0
        backed_off = 0

        for i in range(10):
            try:
                router.deliver("constrained", _env(payload=f"msg{i}".encode()))
                delivered += 1
            except RuntimeError:
                backed_off += 1
                mb.receive()  # drain one
                router.deliver("constrained", _env(payload=f"msg{i}".encode()))
                delivered += 1

        assert delivered == 10
        assert backed_off > 0
