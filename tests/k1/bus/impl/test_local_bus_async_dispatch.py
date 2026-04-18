"""
Phase 6 / P6.5-P6.7: tests for opt-in async dispatch on LocalBus.

Covers:
    P6.5 -- per-subscription bounded mailbox + worker drain + IBus.flush()
    P6.6 -- per-topic RetryPolicy via retry_resolver
    P6.7 -- DLQ callback on retry exhaustion

These tests exercise the new ``LocalBus(async_dispatch=True)`` path.
The legacy synchronous-dispatch path remains the default and is covered
by the pre-existing test suite.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from k1.bus.envelope import Envelope, Priority
from k1.bus.factory import BusFactory
from k1.bus.impl.local_bus import LocalBus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _RetryPolicy:
    """Minimal duck-typed RetryPolicy (P6.6)."""

    max_attempts: int = 0
    base_ms: int = 10
    jitter: bool = False
    backoff: str = "fixed"


# ---------------------------------------------------------------------------
# P6.5 -- async dispatch + flush()
# ---------------------------------------------------------------------------


class TestAsyncDispatch:
    def test_publish_returns_before_handler_runs(self) -> None:
        """Publisher thread must not be blocked by slow handlers."""
        bus = BusFactory.create_local(async_dispatch=True)
        try:
            block = threading.Event()
            release = threading.Event()
            saw: list[Envelope] = []

            def slow_handler(env: Envelope) -> None:
                block.set()
                release.wait(timeout=2.0)
                saw.append(env)

            bus.subscribe("k1.async.*", slow_handler)
            t0 = time.monotonic()
            bus.publish(Envelope(topic="k1.async.test", payload=b"x"))
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            # publish() returned without waiting for the handler
            assert block.wait(timeout=2.0)
            assert elapsed_ms < 200, f"publish blocked for {elapsed_ms:.1f}ms"
            release.set()
            assert bus.flush(timeout_ms=2000)
            assert len(saw) == 1
        finally:
            bus.close()

    def test_flush_waits_for_drain(self) -> None:
        bus = BusFactory.create_local(async_dispatch=True)
        try:
            received: list[int] = []

            def handler(env: Envelope) -> None:
                time.sleep(0.01)
                received.append(env.envelope_id)

            bus.subscribe("k1.flush.*", handler)
            for _ in range(20):
                bus.publish(Envelope(topic="k1.flush.t", payload=b"x"))

            assert bus.flush(timeout_ms=5000) is True
            assert len(received) == 20
        finally:
            bus.close()

    def test_flush_default_sync_is_noop(self) -> None:
        """Sync-dispatch bus.flush() returns True instantly with no work."""
        bus = BusFactory.create_local()
        assert bus.flush() is True
        assert bus.flush(timeout_ms=0) is True
        bus.close()

    def test_backpressure_increments_drop_counter(self) -> None:
        bus = BusFactory.create_local(
            async_dispatch=True,
            subscription_mailbox_capacity=4,
        )
        try:
            allow = threading.Event()

            def blocking(env: Envelope) -> None:
                allow.wait(timeout=2.0)

            bus.subscribe("k1.bp.*", blocking)
            # First publish goes into the worker thread (active);
            # next 4 fill the mailbox; subsequent publishes drop.
            for _ in range(20):
                bus.publish(Envelope(topic="k1.bp.t", payload=b"x"))

            stats = bus.stats.snapshot()
            assert stats["mailbox_full_drops"] > 0
            assert stats["mailbox_high_water_mark"] >= 1

            allow.set()
            bus.flush(timeout_ms=2000)
        finally:
            bus.close()

    def test_unsubscribe_joins_worker(self) -> None:
        bus = BusFactory.create_local(async_dispatch=True)
        try:
            seen: list[Envelope] = []
            handle = bus.subscribe("k1.un.*", seen.append)
            bus.publish(Envelope(topic="k1.un.t", payload=b"a"))
            assert bus.flush(timeout_ms=2000)
            assert bus.unsubscribe(handle) is True
            # After unsubscribe, no further deliveries
            bus.publish(Envelope(topic="k1.un.t", payload=b"b"))
            assert bus.flush(timeout_ms=200)
            assert len(seen) == 1
        finally:
            bus.close()

    def test_close_drains_workers(self) -> None:
        bus = BusFactory.create_local(async_dispatch=True)
        seen: list[Envelope] = []
        bus.subscribe("k1.cl.*", seen.append)
        for _ in range(5):
            bus.publish(Envelope(topic="k1.cl.t", payload=b"x"))
        bus.flush(timeout_ms=2000)
        bus.close()
        assert bus.closed
        assert len(seen) == 5
        # Subsequent publish on closed bus is a no-op
        bus.publish(Envelope(topic="k1.cl.t", payload=b"y"))
        assert len(seen) == 5

    def test_priority_preserved_within_subscription(self) -> None:
        """Mailbox uses WFQ priority (URGENT before BACKGROUND)."""
        bus = BusFactory.create_local(async_dispatch=True)
        try:
            seen: list[int] = []
            block = threading.Event()
            saw_first = threading.Event()

            def handler(env: Envelope) -> None:
                # Block on first call so subsequent envelopes pile up
                # in the mailbox to exercise WFQ ordering.
                if not saw_first.is_set():
                    saw_first.set()
                    block.wait(timeout=2.0)
                seen.append(env.priority)

            bus.subscribe("k1.pri.*", handler)
            # Prime the worker
            bus.publish(
                Envelope(topic="k1.pri.t", payload=b"prime", priority=Priority.INTERACTIVE)
            )
            assert saw_first.wait(timeout=2.0)
            # Now load the mailbox in mixed priority order
            bus.publish(
                Envelope(topic="k1.pri.t", payload=b"bg", priority=Priority.BACKGROUND)
            )
            bus.publish(
                Envelope(topic="k1.pri.t", payload=b"urg", priority=Priority.URGENT)
            )
            bus.publish(
                Envelope(topic="k1.pri.t", payload=b"rt", priority=Priority.REALTIME)
            )
            block.set()
            assert bus.flush(timeout_ms=2000)
            # First entry is the prime envelope; the rest should be in
            # priority order: URGENT < REALTIME (numeric values 0,1,2,3).
            assert seen[0] == Priority.INTERACTIVE
            assert seen[1] == Priority.URGENT
            assert seen[2] == Priority.REALTIME
            assert seen[3] == Priority.BACKGROUND
        finally:
            bus.close()


# ---------------------------------------------------------------------------
# P6.6 -- RetryPolicy via retry_resolver
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_no_resolver_means_no_retry(self) -> None:
        bus = BusFactory.create_local(async_dispatch=True)
        try:
            attempts: list[int] = []

            def flaky(env: Envelope) -> None:
                attempts.append(1)
                raise RuntimeError("boom")

            bus.subscribe("k1.no_retry.*", flaky)
            bus.publish(Envelope(topic="k1.no_retry.t", payload=b"x"))
            bus.flush(timeout_ms=2000)
            assert sum(attempts) == 1
            assert bus.stats.async_handler_retries == 0
        finally:
            bus.close()

    def test_retry_then_success(self) -> None:
        policy = _RetryPolicy(max_attempts=3, base_ms=1)

        def resolver(topic: str) -> _RetryPolicy:
            return policy

        bus = BusFactory.create_local(
            async_dispatch=True, retry_resolver=resolver
        )
        try:
            calls = {"n": 0}

            def flaky(env: Envelope) -> None:
                calls["n"] += 1
                if calls["n"] < 3:
                    raise RuntimeError("transient")

            bus.subscribe("k1.retry.*", flaky)
            bus.publish(Envelope(topic="k1.retry.t", payload=b"x"))
            assert bus.flush(timeout_ms=5000)
            assert calls["n"] == 3
            assert bus.stats.async_handler_retries == 2
        finally:
            bus.close()

    def test_retry_exhaustion_reaches_dlq(self) -> None:
        policy = _RetryPolicy(max_attempts=2, base_ms=1)
        dlq_records: list[tuple[Envelope, BaseException, int]] = []

        def resolver(topic: str) -> _RetryPolicy:
            return policy

        def dlq(env: Envelope, exc: BaseException, attempts: int) -> None:
            dlq_records.append((env, exc, attempts))

        bus = BusFactory.create_local(
            async_dispatch=True, retry_resolver=resolver, dlq_callback=dlq
        )
        try:
            def always_fail(env: Envelope) -> None:
                raise ValueError("nope")

            bus.subscribe("k1.dlq.*", always_fail)
            bus.publish(Envelope(topic="k1.dlq.t", payload=b"x"))
            assert bus.flush(timeout_ms=5000)
            assert len(dlq_records) == 1
            env, exc, attempts = dlq_records[0]
            assert env.topic == "k1.dlq.t"
            assert isinstance(exc, ValueError)
            assert attempts == 3  # 1 initial + 2 retries
            assert bus.stats.async_handler_dlq == 1
        finally:
            bus.close()


# ---------------------------------------------------------------------------
# Direct LocalBus construction (no factory)
# ---------------------------------------------------------------------------


class TestDirectConstruction:
    def test_localbus_async_dispatch_constructor(self) -> None:
        bus = LocalBus(async_dispatch=True, subscription_mailbox_capacity=8)
        try:
            seen: list[Envelope] = []
            bus.subscribe("k1.direct.*", seen.append)
            bus.publish(Envelope(topic="k1.direct.t", payload=b"x"))
            assert bus.flush(timeout_ms=2000)
            assert len(seen) == 1
        finally:
            bus.close()
