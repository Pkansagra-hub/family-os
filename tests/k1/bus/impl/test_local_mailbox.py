"""
Tests for k1.bus.impl.local_mailbox -- LocalMailbox + LocalMailboxRouter.

Coverage targets:
    LocalMailbox:
        - FIFO delivery (single queue, no WFQ)
        - WFQ priority: URGENT dequeued before BACKGROUND
        - WFQ priority: all 4 levels strict ordering
        - Capacity enforcement (BackpressureError at limit)
        - Blocking receive with timeout
        - Non-blocking receive returns None when empty
        - Close prevents new deliveries but allows drain
        - Pending count accurate
        - Depth-by-priority observability
        - delivered_count / received_count lifetime counters
        - repr

    LocalMailboxRouter:
        - Register creates mailbox, returns IMailbox
        - Deliver to registered actor succeeds
        - Deliver to unknown actor raises UnknownActorError
        - Deliver to full mailbox raises BackpressureError
        - Double register same actor_id raises ValueError
        - Empty actor_id rejected
        - Unregister returns True and closes mailbox
        - Unregister unknown returns False
        - registered_actors() list
        - Close router prevents new deliveries and registrations
        - stats_snapshot observability
        - mailbox_for observability
        - Thread safety: concurrent deliver + receive
        - Thread safety: concurrent register + deliver

    Protocol compliance:
        - LocalMailbox satisfies IMailbox Protocol
        - LocalMailboxRouter satisfies IMailboxRouter Protocol

    BusFactory:
        - create_mailbox_router returns LocalMailboxRouter

    Integration:
        - Full flow: register -> deliver -> receive round-trip
        - Multiple actors receiving independently
        - Unregister stops delivery, subsequent deliver raises
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from k1.bus import (
    BackpressureError,
    BusFactory,
    Envelope,
    IMailbox,
    IMailboxRouter,
    LocalMailbox,
    LocalMailboxRouter,
    MailboxConfig,
    Priority,
    UnknownActorError,
)

# ===================================================================
# Helpers
# ===================================================================


def _env(
    topic: str = "k1.test",
    payload: bytes = b"data",
    priority: int = Priority.INTERACTIVE,
) -> Envelope:
    return Envelope(topic=topic, payload=payload, priority=priority)


# ===================================================================
# Protocol compliance
# ===================================================================


class TestProtocolCompliance:
    def test_local_mailbox_is_imailbox(self) -> None:
        mb = LocalMailbox("test", MailboxConfig())
        assert isinstance(mb, IMailbox)

    def test_local_mailbox_router_is_imailbox_router(self) -> None:
        router = LocalMailboxRouter()
        assert isinstance(router, IMailboxRouter)


# ===================================================================
# LocalMailbox -- FIFO mode
# ===================================================================


class TestLocalMailboxFIFO:
    def test_receive_from_empty_returns_none(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(priority_wfq=False))
        assert mb.receive() is None
        assert mb.pending() == 0

    def test_fifo_delivery_order(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10, priority_wfq=False))
        for i in range(5):
            mb._deliver(_env(payload=f"msg{i}".encode()))

        assert mb.pending() == 5
        for i in range(5):
            env = mb.receive()
            assert env is not None
            assert env.payload == f"msg{i}".encode()

        assert mb.pending() == 0
        assert mb.receive() is None

    def test_fifo_ignores_priority(self) -> None:
        """In FIFO mode, BACKGROUND arrives before URGENT if sent first."""
        mb = LocalMailbox("a", MailboxConfig(capacity=10, priority_wfq=False))
        mb._deliver(_env(priority=Priority.BACKGROUND))
        mb._deliver(_env(priority=Priority.URGENT))

        first = mb.receive()
        assert first is not None
        assert first.priority == Priority.BACKGROUND

    def test_depth_by_priority_empty_in_fifo(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(priority_wfq=False))
        assert mb.depth_by_priority() == {}


# ===================================================================
# LocalMailbox -- WFQ priority mode
# ===================================================================


class TestLocalMailboxWFQ:
    def test_urgent_dequeued_before_background(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        # Deliver BACKGROUND first, then URGENT
        mb._deliver(_env(priority=Priority.BACKGROUND, payload=b"bg"))
        mb._deliver(_env(priority=Priority.URGENT, payload=b"urg"))

        first = mb.receive()
        assert first is not None
        assert first.payload == b"urg"

        second = mb.receive()
        assert second is not None
        assert second.payload == b"bg"

    def test_strict_priority_ordering_all_levels(self) -> None:
        """All 4 levels: URGENT > REALTIME > INTERACTIVE > BACKGROUND."""
        mb = LocalMailbox("a", MailboxConfig(capacity=20))

        # Deliver in reverse priority order
        mb._deliver(_env(priority=Priority.BACKGROUND, payload=b"bg"))
        mb._deliver(_env(priority=Priority.INTERACTIVE, payload=b"int"))
        mb._deliver(_env(priority=Priority.REALTIME, payload=b"rt"))
        mb._deliver(_env(priority=Priority.URGENT, payload=b"urg"))

        results = []
        for _ in range(4):
            env = mb.receive()
            assert env is not None
            results.append(env.payload)

        assert results == [b"urg", b"rt", b"int", b"bg"]

    def test_same_priority_fifo_within_level(self) -> None:
        """Within the same priority level, FIFO order is preserved."""
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        mb._deliver(_env(priority=Priority.INTERACTIVE, payload=b"first"))
        mb._deliver(_env(priority=Priority.INTERACTIVE, payload=b"second"))
        mb._deliver(_env(priority=Priority.INTERACTIVE, payload=b"third"))

        r = [mb.receive().payload for _ in range(3)]  # type: ignore[union-attr]
        assert r == [b"first", b"second", b"third"]

    def test_high_priority_interleaving(self) -> None:
        """URGENT injected after INTERACTIVE -- still dequeued first."""
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        mb._deliver(_env(priority=Priority.INTERACTIVE, payload=b"int1"))
        mb._deliver(_env(priority=Priority.INTERACTIVE, payload=b"int2"))
        mb._deliver(_env(priority=Priority.URGENT, payload=b"urg1"))

        first = mb.receive()
        assert first is not None
        assert first.payload == b"urg1"

    def test_depth_by_priority(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=20))
        mb._deliver(_env(priority=Priority.URGENT))
        mb._deliver(_env(priority=Priority.URGENT))
        mb._deliver(_env(priority=Priority.BACKGROUND))

        depths = mb.depth_by_priority()
        assert depths["URGENT"] == 2
        assert depths["REALTIME"] == 0
        assert depths["INTERACTIVE"] == 0
        assert depths["BACKGROUND"] == 1

    def test_depth_updates_after_receive(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        mb._deliver(_env(priority=Priority.URGENT))
        mb._deliver(_env(priority=Priority.BACKGROUND))

        mb.receive()  # Should dequeue URGENT
        depths = mb.depth_by_priority()
        assert depths["URGENT"] == 0
        assert depths["BACKGROUND"] == 1


# ===================================================================
# LocalMailbox -- capacity and backpressure
# ===================================================================


class TestLocalMailboxCapacity:
    def test_at_capacity_raises_backpressure(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=3))
        for _ in range(3):
            mb._deliver(_env())

        try:
            mb._deliver(_env())
            assert False, "Expected BackpressureError"
        except BackpressureError as e:
            assert e.actor_id == "a"
            assert e.capacity == 3

    def test_drain_frees_capacity(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=2))
        mb._deliver(_env(payload=b"1"))
        mb._deliver(_env(payload=b"2"))

        # Full
        try:
            mb._deliver(_env(payload=b"3"))
            assert False, "Expected BackpressureError"
        except BackpressureError:
            pass

        # Drain one
        mb.receive()
        # Now space for one more
        mb._deliver(_env(payload=b"3"))
        assert mb.pending() == 2

    def test_capacity_one(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=1))
        mb._deliver(_env())
        assert mb.pending() == 1

        try:
            mb._deliver(_env())
            assert False, "Expected BackpressureError"
        except BackpressureError:
            pass


# ===================================================================
# LocalMailbox -- blocking receive
# ===================================================================


class TestLocalMailboxBlocking:
    def test_blocking_receive_returns_when_data_arrives(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        result: list[Envelope] = []

        def receiver() -> None:
            env = mb.receive(timeout_ms=2000)
            if env is not None:
                result.append(env)

        t = threading.Thread(target=receiver)
        t.start()
        time.sleep(0.02)  # Let receiver block
        mb._deliver(_env(payload=b"wakeup"))
        t.join(timeout=2)
        assert not t.is_alive()
        assert len(result) == 1
        assert result[0].payload == b"wakeup"

    def test_blocking_receive_timeout_returns_none(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        start = time.monotonic()
        result = mb.receive(timeout_ms=50)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed >= 0.04  # At least ~40ms (allowing some slack)

    def test_nonblocking_receive_immediate(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        start = time.monotonic()
        result = mb.receive(timeout_ms=0)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 0.01


# ===================================================================
# LocalMailbox -- close / lifecycle
# ===================================================================


class TestLocalMailboxClose:
    def test_close_prevents_delivery(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        mb._deliver(_env(payload=b"before"))
        mb.close()

        try:
            mb._deliver(_env(payload=b"after"))
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "closed" in str(e).lower()

    def test_close_allows_drain(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        mb._deliver(_env(payload=b"drain-me"))
        mb.close()

        env = mb.receive()
        assert env is not None
        assert env.payload == b"drain-me"

    def test_closed_property(self) -> None:
        mb = LocalMailbox("a", MailboxConfig())
        assert mb.closed is False
        mb.close()
        assert mb.closed is True


# ===================================================================
# LocalMailbox -- observability
# ===================================================================


class TestLocalMailboxObservability:
    def test_delivered_and_received_counts(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=10))
        assert mb.delivered_count == 0
        assert mb.received_count == 0

        mb._deliver(_env())
        mb._deliver(_env())
        assert mb.delivered_count == 2
        assert mb.received_count == 0

        mb.receive()
        assert mb.received_count == 1

    def test_actor_id_property(self) -> None:
        mb = LocalMailbox("orchestrator", MailboxConfig())
        assert mb.actor_id == "orchestrator"

    def test_capacity_property(self) -> None:
        mb = LocalMailbox("a", MailboxConfig(capacity=42))
        assert mb.capacity == 42

    def test_repr(self) -> None:
        mb = LocalMailbox("test", MailboxConfig(capacity=100))
        r = repr(mb)
        assert "test" in r
        assert "100" in r
        assert "WFQ" in r

    def test_repr_fifo(self) -> None:
        mb = LocalMailbox("test", MailboxConfig(capacity=5, priority_wfq=False))
        assert "FIFO" in repr(mb)


# ===================================================================
# LocalMailboxRouter -- register / unregister
# ===================================================================


class TestLocalMailboxRouterRegistration:
    def test_register_returns_mailbox(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("concierge", MailboxConfig(capacity=100))
        assert isinstance(mb, LocalMailbox)
        assert mb.actor_id == "concierge"

    def test_register_default_config(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("agent1")
        assert mb.capacity == 256  # Default

    def test_double_register_raises(self) -> None:
        router = LocalMailboxRouter()
        router.register("agent1")
        try:
            router.register("agent1")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "already registered" in str(e).lower()

    def test_empty_actor_id_rejected(self) -> None:
        router = LocalMailboxRouter()
        try:
            router.register("")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "empty" in str(e).lower()

    def test_unregister_existing(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("agent1")
        result = router.unregister("agent1")
        assert result is True
        assert mb.closed is True
        assert "agent1" not in router.registered_actors()

    def test_unregister_unknown_returns_false(self) -> None:
        router = LocalMailboxRouter()
        assert router.unregister("ghost") is False

    def test_registered_actors(self) -> None:
        router = LocalMailboxRouter()
        router.register("a")
        router.register("b")
        router.register("c")
        actors = router.registered_actors()
        assert sorted(actors) == ["a", "b", "c"]

    def test_register_after_unregister_ok(self) -> None:
        router = LocalMailboxRouter()
        router.register("agent1")
        router.unregister("agent1")
        mb = router.register("agent1")
        assert mb.actor_id == "agent1"


# ===================================================================
# LocalMailboxRouter -- deliver
# ===================================================================


class TestLocalMailboxRouterDeliver:
    def test_deliver_and_receive(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("orch", MailboxConfig(capacity=10))

        router.deliver("orch", _env(payload=b"hello"))
        env = mb.receive()
        assert env is not None
        assert env.payload == b"hello"

    def test_deliver_to_unknown_raises(self) -> None:
        router = LocalMailboxRouter()
        try:
            router.deliver("nobody", _env())
            assert False, "Expected UnknownActorError"
        except UnknownActorError as e:
            assert e.actor_id == "nobody"

    def test_deliver_to_full_mailbox_raises(self) -> None:
        router = LocalMailboxRouter()
        router.register("small", MailboxConfig(capacity=2))
        router.deliver("small", _env())
        router.deliver("small", _env())

        try:
            router.deliver("small", _env())
            assert False, "Expected BackpressureError"
        except BackpressureError as e:
            assert e.actor_id == "small"
            assert e.capacity == 2

    def test_deliver_after_unregister_raises(self) -> None:
        router = LocalMailboxRouter()
        router.register("victim")
        router.unregister("victim")

        try:
            router.deliver("victim", _env())
            assert False, "Expected UnknownActorError"
        except UnknownActorError:
            pass

    def test_deliver_multiple_actors_independently(self) -> None:
        router = LocalMailboxRouter()
        mb_a = router.register("a", MailboxConfig(capacity=10))
        mb_b = router.register("b", MailboxConfig(capacity=10))

        router.deliver("a", _env(payload=b"for-a"))
        router.deliver("b", _env(payload=b"for-b"))

        assert mb_a.receive().payload == b"for-a"  # type: ignore[union-attr]
        assert mb_b.receive().payload == b"for-b"  # type: ignore[union-attr]
        assert mb_a.pending() == 0
        assert mb_b.pending() == 0

    def test_deliver_preserves_priority_in_wfq_mailbox(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("orch", MailboxConfig(capacity=10))

        router.deliver("orch", _env(priority=Priority.BACKGROUND, payload=b"bg"))
        router.deliver("orch", _env(priority=Priority.URGENT, payload=b"urg"))

        first = mb.receive()
        assert first is not None
        assert first.payload == b"urg"


# ===================================================================
# LocalMailboxRouter -- close / lifecycle
# ===================================================================


class TestLocalMailboxRouterClose:
    def test_close_prevents_delivery(self) -> None:
        router = LocalMailboxRouter()
        router.register("a")
        router.close()

        try:
            router.deliver("a", _env())
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "closed" in str(e).lower()

    def test_close_prevents_registration(self) -> None:
        router = LocalMailboxRouter()
        router.close()

        try:
            router.register("new")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "closed" in str(e).lower()

    def test_close_closes_all_mailboxes(self) -> None:
        router = LocalMailboxRouter()
        mb_a = router.register("a")
        mb_b = router.register("b")
        router.close()

        assert mb_a.closed is True
        assert mb_b.closed is True

    def test_closed_property(self) -> None:
        router = LocalMailboxRouter()
        assert router.closed is False
        router.close()
        assert router.closed is True

    def test_drain_after_close(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("a", MailboxConfig(capacity=10))
        router.deliver("a", _env(payload=b"pending"))
        router.close()

        # Mailbox is closed but drainable
        env = mb.receive()
        assert env is not None
        assert env.payload == b"pending"


# ===================================================================
# LocalMailboxRouter -- observability
# ===================================================================


class TestLocalMailboxRouterObservability:
    def test_actor_count(self) -> None:
        router = LocalMailboxRouter()
        assert router.actor_count == 0
        router.register("a")
        router.register("b")
        assert router.actor_count == 2
        router.unregister("a")
        assert router.actor_count == 1

    def test_mailbox_for(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("target")
        found = router.mailbox_for("target")
        assert found is mb

    def test_mailbox_for_unknown_returns_none(self) -> None:
        router = LocalMailboxRouter()
        assert router.mailbox_for("ghost") is None

    def test_stats_snapshot(self) -> None:
        router = LocalMailboxRouter()
        mb = router.register("a", MailboxConfig(capacity=10))
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
        router = LocalMailboxRouter()
        router.register("x")
        r = repr(router)
        assert "LocalMailboxRouter" in r
        assert "1" in r


# ===================================================================
# BusFactory
# ===================================================================


class TestBusFactoryMailbox:
    def test_create_mailbox_router(self) -> None:
        router = BusFactory.create_mailbox_router()
        assert isinstance(router, LocalMailboxRouter)
        assert isinstance(router, IMailboxRouter)
        assert router.actor_count == 0


# ===================================================================
# Thread safety
# ===================================================================


class TestMailboxThreadSafety:
    def test_concurrent_deliver_and_receive(self) -> None:
        """Multiple threads delivering while one thread receives."""
        router = LocalMailboxRouter()
        mb = router.register("target", MailboxConfig(capacity=5000))
        errors: list[str] = []
        received: list[Envelope] = []
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
        router = LocalMailboxRouter()
        errors: list[str] = []

        def registerer() -> None:
            for i in range(20):
                try:
                    router.register(f"actor-{i}", MailboxConfig(capacity=100))
                except Exception as e:
                    errors.append(f"Register: {e}")

        def deliverer() -> None:
            time.sleep(0.01)  # Let some registrations happen first
            for i in range(20):
                actor_id = f"actor-{i}"
                try:
                    if actor_id in router.registered_actors():
                        router.deliver(actor_id, _env())
                except (UnknownActorError, ValueError):
                    pass  # Race with registration -- expected
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
        router = LocalMailboxRouter()
        mb = router.register("shared", MailboxConfig(capacity=100))
        results: list[Envelope] = []
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
            # Wait a bit for receivers to drain, then they'll timeout
            for f in recv_futures:
                f.result(timeout=5)

        assert len(results) == n_messages


# ===================================================================
# Integration -- full round-trip
# ===================================================================


class TestMailboxIntegration:
    def test_full_round_trip(self) -> None:
        """Register -> deliver -> receive pipeline."""
        router = BusFactory.create_mailbox_router()
        mb = router.register("orchestrator", MailboxConfig(capacity=50, priority_wfq=True))

        # Send various priority messages
        router.deliver("orchestrator", _env(priority=Priority.BACKGROUND, payload=b"bg"))
        router.deliver("orchestrator", _env(priority=Priority.URGENT, payload=b"urg"))
        router.deliver("orchestrator", _env(priority=Priority.INTERACTIVE, payload=b"int"))

        # Receive in priority order
        assert mb.receive().payload == b"urg"  # type: ignore[union-attr]
        assert mb.receive().payload == b"int"  # type: ignore[union-attr]
        assert mb.receive().payload == b"bg"  # type: ignore[union-attr]
        assert mb.receive() is None

    def test_multiple_actors_independent_queues(self) -> None:
        router = BusFactory.create_mailbox_router()
        orch = router.register("orch", MailboxConfig(capacity=10))
        plan = router.register("plan", MailboxConfig(capacity=10))

        for i in range(5):
            router.deliver("orch", _env(payload=f"orch-{i}".encode()))
        for i in range(3):
            router.deliver("plan", _env(payload=f"plan-{i}".encode()))

        assert orch.pending() == 5
        assert plan.pending() == 3

        # Drain orch, plan unaffected
        while orch.receive() is not None:
            pass
        assert orch.pending() == 0
        assert plan.pending() == 3

    def test_unregister_lifecycle(self) -> None:
        router = BusFactory.create_mailbox_router()
        mb = router.register("temp", MailboxConfig(capacity=5))
        router.deliver("temp", _env(payload=b"pending"))

        # Unregister closes mailbox
        router.unregister("temp")
        assert mb.closed is True

        # Drain still works
        env = mb.receive()
        assert env is not None
        assert env.payload == b"pending"

        # Deliver to unregistered raises
        try:
            router.deliver("temp", _env())
            assert False, "Expected UnknownActorError"
        except UnknownActorError:
            pass

    def test_backpressure_flow(self) -> None:
        """Simulates producer backing off on backpressure."""
        router = BusFactory.create_mailbox_router()
        mb = router.register("constrained", MailboxConfig(capacity=3))

        delivered = 0
        backed_off = 0

        for i in range(10):
            try:
                router.deliver("constrained", _env(payload=f"msg{i}".encode()))
                delivered += 1
            except BackpressureError:
                backed_off += 1
                # Consumer drains one
                mb.receive()
                # Retry
                router.deliver("constrained", _env(payload=f"msg{i}".encode()))
                delivered += 1

        assert delivered == 10
        assert backed_off > 0  # Should have hit backpressure at least once
