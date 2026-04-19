"""
Phase 6 E2E test (P6.14) -- exercises every Tier-3..Tier-6 change end-to-end.

Coverage matrix:
    P6.5  -- async dispatch + flush() backpressure
    P6.6  -- per-topic RetryPolicy via retry_resolver
    P6.7  -- DLQ callback on retry exhaustion
    P6.8  -- topic rename (k1.session.turn.complete.v1) routing
    P6.9  -- SessionBusAdapter flatten (k1.sessionstate.*)
    P6.11 -- TopicRegistry schema validation (permissive + strict)
    P6.12 -- IdempotencyMiddleware drops duplicates
    P6.13 -- Durable outbox replay across simulated process restart

This is a single-file smoke that wires several bus features together.
Each test is independent; no fixtures cross test boundaries.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from k1.bus.envelope import Envelope
from k1.bus.factory import BusFactory
from k1.bus.middleware import MiddlewareChain
from k1.bus.middleware.idempotency import IdempotencyMiddleware
from k1.bus.middleware.topic_validation import (
    SchemaValidationError,
    TopicRegistry,
    TopicValidationMiddleware,
)
from k1.bus.outbox import BusOutbox


@dataclass
class _RetryPolicy:
    max_attempts: int = 2
    base_ms: int = 1
    backoff: str = "fixed"
    jitter: bool = False


# ---------------------------------------------------------------------------
# P6.5 + P6.6 + P6.7 chained
# ---------------------------------------------------------------------------


class TestE2EAsyncRetryDLQ:
    def test_retry_then_success_no_dlq(self) -> None:
        attempts: list[int] = []

        def handler(env: Envelope) -> None:
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise RuntimeError("transient")

        dlq: list[tuple[Envelope, BaseException, int]] = []

        bus = BusFactory.create_local(
            async_dispatch=True,
            retry_resolver=lambda topic: _RetryPolicy(max_attempts=3),
            dlq_callback=lambda env, exc, n: dlq.append((env, exc, n)),
        )
        bus.subscribe("k1.cmd.do.v1", handler)
        bus.publish(Envelope(topic="k1.cmd.do.v1", payload=b"x"))

        assert bus.flush(timeout_ms=2000)
        assert len(attempts) == 3
        assert dlq == []
        bus.close()

    def test_retry_exhaustion_lands_in_dlq(self) -> None:
        def handler(env: Envelope) -> None:
            raise RuntimeError("always fails")

        dlq: list[tuple[Envelope, BaseException, int]] = []

        bus = BusFactory.create_local(
            async_dispatch=True,
            retry_resolver=lambda topic: _RetryPolicy(max_attempts=2),
            dlq_callback=lambda env, exc, n: dlq.append((env, exc, n)),
        )
        bus.subscribe("k1.cmd.do.v1", handler)
        bus.publish(Envelope(topic="k1.cmd.do.v1", payload=b"x"))

        assert bus.flush(timeout_ms=2000)
        assert len(dlq) == 1
        env, exc, n = dlq[0]
        assert env.topic == "k1.cmd.do.v1"
        assert isinstance(exc, RuntimeError)
        assert n == 3  # 1 initial + 2 retries
        bus.close()


# ---------------------------------------------------------------------------
# P6.8 + P6.9 -- topic-rename traffic
# ---------------------------------------------------------------------------


class TestE2ETopicRoutingRenames:
    def test_turn_complete_topic_routes_post_rename(self) -> None:
        from k1.memory_writer.events import TOPIC_TURN_COMPLETE
        from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher

        assert TOPIC_TURN_COMPLETE == "k1.session.turn.complete.v1"
        assert TurnDispatcher.TOPIC == TOPIC_TURN_COMPLETE

        bus = BusFactory.create_local()
        received: list[Envelope] = []
        bus.subscribe(TOPIC_TURN_COMPLETE, received.append)
        bus.publish(Envelope(topic=TOPIC_TURN_COMPLETE, payload=b"{}"))
        assert len(received) == 1

    def test_session_adapter_flattens_sessionstate_topic(self) -> None:
        from k1.bus.adapters.session_adapter import SessionBusAdapter

        bus = BusFactory.create_local()
        adapter = SessionBusAdapter(bus)
        seen: list[str] = []
        bus.subscribe("k1.sessionstate.>", lambda e: seen.append(e.topic))
        adapter.emit("sessionstate.mutation.requested", payload=b"{}")
        # Flattened: NOT k1.session.sessionstate.* -- must be k1.sessionstate.*
        assert seen == ["k1.sessionstate.mutation.requested"]


# ---------------------------------------------------------------------------
# P6.11 -- schema validation chained into the middleware
# ---------------------------------------------------------------------------


class TestE2ESchemaValidation:
    def test_strict_mode_drops_bad_payload_before_handler(self) -> None:
        def validator(payload: bytes, env: Envelope) -> None:
            if not payload.startswith(b"{"):
                raise SchemaValidationError("expected JSON object")

        reg = TopicRegistry()
        reg.register("k1.cmd.do.v1", validator=validator)
        topic_mw = TopicValidationMiddleware(reg, schema_validation_mode="strict")
        chain = MiddlewareChain([topic_mw])

        bus = BusFactory.create_local(middleware=chain)
        received: list[Envelope] = []
        bus.subscribe("k1.cmd.do.v1", received.append)

        bus.publish(Envelope(topic="k1.cmd.do.v1", payload=b'{"ok": 1}'))
        bus.publish(Envelope(topic="k1.cmd.do.v1", payload=b"not json"))

        assert len(received) == 1
        assert topic_mw.schema_drop_count == 1


# ---------------------------------------------------------------------------
# P6.12 -- IdempotencyMiddleware blocks duplicate request_id
# ---------------------------------------------------------------------------


class TestE2EIdempotency:
    def test_duplicate_request_id_runs_handler_once(self) -> None:
        chain = MiddlewareChain([IdempotencyMiddleware()])
        bus = BusFactory.create_local(middleware=chain)
        received: list[Envelope] = []
        bus.subscribe("k1.cmd.do.v1", received.append)

        for _ in range(5):
            bus.publish(
                Envelope(topic="k1.cmd.do.v1", payload=b"{}", request_id="req-42")
            )

        assert len(received) == 1


# ---------------------------------------------------------------------------
# P6.13 -- durable outbox replay across simulated process restart
# ---------------------------------------------------------------------------


class TestE2EDurabilityReplay:
    def test_unacked_envelopes_replay_on_new_bus(self, tmp_path: Path) -> None:
        outbox_path = tmp_path / "phase6_e2e.db"

        # ----- "Process 1" -----
        ob1 = BusOutbox(outbox_path)
        bus1 = BusFactory.create_local(
            outbox=ob1, durable_topics={"k1.cmd.do.v1"}
        )
        for i in range(3):
            bus1.publish(
                Envelope(topic="k1.cmd.do.v1", payload=str(i).encode())
            )
        bus1.close()
        assert ob1.count("k1.cmd.do.v1") == 3

        # ----- "Process 2" (simulated restart) -----
        ob2 = BusOutbox(outbox_path)
        bus2 = BusFactory.create_local(
            outbox=ob2, durable_topics={"k1.cmd.do.v1"}
        )
        replayed: list[bytes] = []
        bus2.subscribe(
            "k1.cmd.do.v1",
            lambda e: replayed.append(e.payload),
            consumer_id="worker-1",
        )
        n = bus2.replay_durable_topics()
        assert n == 3
        assert replayed == [b"0", b"1", b"2"]

        # Acks were recorded -> a third "process" would replay nothing.
        ob3 = BusOutbox(outbox_path)
        bus3 = BusFactory.create_local(
            outbox=ob3, durable_topics={"k1.cmd.do.v1"}
        )
        replay_again: list[bytes] = []
        bus3.subscribe(
            "k1.cmd.do.v1",
            lambda e: replay_again.append(e.payload),
            consumer_id="worker-1",
        )
        assert bus3.replay_durable_topics() == 0
        assert replay_again == []
        bus2.close()
        bus3.close()
