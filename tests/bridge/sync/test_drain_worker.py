"""MS-3b Epic 3b.3 \u2014 enriched outbox + DrainWorker tests.

Real SQLite, real ``HttpTransport`` backed by ``httpx.MockTransport``,
real asyncio events. No mocks of bridge components themselves.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from bridge.core.events import EventBus, HealthTransition, utc_now
from bridge.core.transport import HttpTransport, TransportConfig
from bridge.sync.drain_worker import DrainWorker
from bridge.sync.local_outbox import LocalOutbox

pytestmark = pytest.mark.asyncio


def _envelope(topic: str = "memory.write.v1", body: dict | None = None) -> str:
    return json.dumps({"topic": topic, "body": body or {"text": "x"}})


def _make_transport(handler) -> HttpTransport:
    transport = HttpTransport(TransportConfig(base_url="http://test-k0:8000"))
    transport._client = httpx.AsyncClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler),
        base_url="http://test-k0:8000",
    )
    return transport


# ---------------------------------------------------------------------------
# Enriched LocalOutbox
# ---------------------------------------------------------------------------


def test_enqueue_with_max_queue_age_persists_ttl(tmp_path: Path):
    ob = LocalOutbox(db_path=tmp_path / "ob.db")
    try:
        ob.enqueue(_envelope(), "memory.write.v1", max_queue_age_s=60)
        rows = ob._conn.execute(  # noqa: SLF001
            "SELECT max_queue_age_s FROM outbox_queue"
        ).fetchall()
        assert rows == [(60,)]
    finally:
        ob.close()


def test_prune_expired_removes_only_aged_rows(tmp_path: Path):
    ob = LocalOutbox(db_path=tmp_path / "ob.db")
    try:
        # Row with very short TTL, backdated.
        ob.enqueue(_envelope(), "fast", max_queue_age_s=1)
        # Row with long TTL.
        ob.enqueue(_envelope(), "slow", max_queue_age_s=3600)
        # Row with no TTL (immortal).
        ob.enqueue(_envelope(), "immortal")
        # Backdate the first row by hand so it ages past the TTL.
        old_iso = (
            (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
        )
        ob._conn.execute(  # noqa: SLF001
            "UPDATE outbox_queue SET created_at = ? WHERE topic = 'fast'",
            (old_iso,),
        )
        ob._conn.commit()  # noqa: SLF001

        pruned = ob.prune_expired()
        assert pruned == 1
        remaining = {e.topic for e in ob.list_pending()}
        assert remaining == {"slow", "immortal"}
    finally:
        ob.close()


def test_move_to_dead_letter_atomic(tmp_path: Path):
    ob = LocalOutbox(db_path=tmp_path / "ob.db")
    try:
        row_id = ob.enqueue(_envelope(), "bad.contract")
        ob.move_to_dead_letter(
            row_id, reason="schema_violation", response_code=422, response_body="oops"
        )
        assert ob.pending_count() == 0
        assert ob.dead_letter_count() == 1
        rows = ob.list_dead_letter()
        assert rows[0]["topic"] == "bad.contract"
        assert rows[0]["response_code"] == 422
        assert rows[0]["reason"] == "schema_violation"
    finally:
        ob.close()


# ---------------------------------------------------------------------------
# DrainWorker
# ---------------------------------------------------------------------------


@pytest.fixture
def outbox(tmp_path: Path):
    ob = LocalOutbox(db_path=tmp_path / "drain.db")
    yield ob
    ob.close()


async def test_drain_worker_drains_2xx_responses(outbox: LocalOutbox):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = _make_transport(handler)
    try:
        for _ in range(5):
            outbox.enqueue(_envelope(), "memory.write.v1")
        worker = DrainWorker(outbox=outbox, transport=transport)
        drained = await worker.drain_now()
        assert drained == 5
        assert outbox.pending_count() == 0
    finally:
        await transport.close()


async def test_drain_worker_routes_4xx_to_dead_letter(outbox: LocalOutbox):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "schema"})

    transport = _make_transport(handler)
    try:
        outbox.enqueue(_envelope(), "memory.write.v1")
        worker = DrainWorker(outbox=outbox, transport=transport)
        await worker.drain_now()
        assert outbox.pending_count() == 0
        assert outbox.dead_letter_count() == 1
        row = outbox.list_dead_letter()[0]
        assert row["response_code"] == 422
        assert row["reason"] == "http_422"
    finally:
        await transport.close()


async def test_drain_worker_keeps_5xx_for_retry(outbox: LocalOutbox):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    transport = _make_transport(handler)
    try:
        outbox.enqueue(_envelope(), "memory.write.v1")
        worker = DrainWorker(outbox=outbox, transport=transport)
        await worker.drain_now()
        assert outbox.pending_count() == 1
        assert outbox.dead_letter_count() == 0
        # Second pass also fails; row still there for retry.
        await worker.drain_now()
        assert outbox.pending_count() == 1
        assert calls["n"] == 2
    finally:
        await transport.close()


async def test_drain_worker_event_driven_on_health_transition(outbox: LocalOutbox):
    """OFFLINE\u2192ONLINE event triggers a drain pass within the safety budget."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = _make_transport(handler)
    bus = EventBus()
    try:
        for _ in range(3):
            outbox.enqueue(_envelope(), "memory.write.v1")
        worker = DrainWorker(
            outbox=outbox,
            transport=transport,
            event_bus=bus,
            safety_net_interval_s=10.0,  # so safety-net does not fire first
        )
        await worker.start()
        # Startup pass kicks first; wait for it to drain.
        for _ in range(40):
            if outbox.pending_count() == 0:
                break
            await asyncio.sleep(0.02)
        assert outbox.pending_count() == 0

        # Queue more, simulate offline\u2192online; the event should wake the
        # worker.
        for _ in range(2):
            outbox.enqueue(_envelope(), "memory.write.v1")
        bus.publish(
            HealthTransition(
                from_state="OFFLINE",
                to_state="ONLINE",
                at_utc=utc_now(),
            )
        )
        for _ in range(50):
            if outbox.pending_count() == 0:
                break
            await asyncio.sleep(0.02)
        assert outbox.pending_count() == 0
        assert worker.first_batch_after_transition_ms is not None
        # Generous bound for CI noise; the design target is <50ms p99.
        assert worker.first_batch_after_transition_ms < 1000.0
    finally:
        await worker.stop()
        await transport.close()


async def test_drain_worker_safety_net_sweep_when_no_event(outbox: LocalOutbox):
    """Without any health-transition event, the periodic sweep still drains."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = _make_transport(handler)
    try:
        worker = DrainWorker(
            outbox=outbox,
            transport=transport,
            event_bus=None,  # no event path
            safety_net_interval_s=0.1,
        )
        await worker.start()
        outbox.enqueue(_envelope(), "memory.write.v1")
        for _ in range(40):
            if outbox.pending_count() == 0:
                break
            await asyncio.sleep(0.05)
        assert outbox.pending_count() == 0
    finally:
        await worker.stop()
        await transport.close()


async def test_drain_worker_stop_is_safe_when_never_started(outbox: LocalOutbox):
    transport = _make_transport(lambda r: httpx.Response(200))
    worker = DrainWorker(outbox=outbox, transport=transport)
    await worker.stop()  # should not raise
    await transport.close()


async def test_drain_worker_per_contract_pacing(outbox: LocalOutbox):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = _make_transport(handler)
    try:
        for _ in range(4):
            outbox.enqueue(_envelope(), "memory.write.v1")
        # 20 ops/sec \u2192 4 ops should take \u2248 0.15s minimum.
        worker = DrainWorker(outbox=outbox, transport=transport, rate_for=lambda _t: 20.0)
        started = time.monotonic()
        await worker.drain_now()
        elapsed = time.monotonic() - started
        assert outbox.pending_count() == 0
        assert elapsed >= 0.15, f"pacing not honoured: elapsed={elapsed:.3f}s"
    finally:
        await transport.close()
