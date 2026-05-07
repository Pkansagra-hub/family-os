"""MS-3b Epic 3b.4 \u2014 ``OnlineFirstClient`` decorator tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel

from bridge.core.degraded import DegradedBehavior, DegradedMatrix
from bridge.core.envelope_builder import BridgeConfig, EnvelopeBuilder
from bridge.core.events import EventBus, HealthTransition, utc_now
from bridge.core.health import K0HealthChecker, K0HealthState
from bridge.core.online_first import (
    OfflineError,
    OnlineFirstClient,
    _parse_iso8601_duration_to_s,
)
from bridge.core.signing import HmacSigning
from bridge.core.transport import HttpTransport, TransportConfig
from bridge.sync.local_outbox import LocalOutbox

pytestmark = pytest.mark.asyncio


class _Payload(BaseModel):
    schema_version: str = "1.0"
    text: str


def _make_transport(handler) -> HttpTransport:
    cfg = TransportConfig(base_url="http://k0.test")
    builder = EnvelopeBuilder(
        config=BridgeConfig(tenant_id="t1", space_id="s1", device_id="d1"),
        signer=HmacSigning(secret=b"\x00" * 32, key_id="dev:test"),
    )
    transport = HttpTransport(config=cfg, envelope_builder=builder)
    transport._client = httpx.AsyncClient(  # noqa: SLF001
        transport=httpx.MockTransport(handler), base_url=cfg.base_url
    )
    return transport


class _RealishInner:
    """Stand-in for a generated client \u2014 forwards to transport.publish."""

    __topic__ = "memory.write.v1"
    __schema_uri__ = "bridge://contracts/schemas/memory.write.v1.json"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def publish(self, payload):
        return await self._transport.publish(
            topic=self.__topic__,
            schema_uri=self.__schema_uri__,
            payload=payload,
        )


def _matrix(online_required: bool = False, max_queue_age: str = "PT24H") -> DegradedMatrix:
    return DegradedMatrix(
        [
            {
                "topic": "memory.write.v1",
                "direction": "k1_to_k0",
                "delivery": {
                    "online_required": online_required,
                    "max_queue_age": max_queue_age,
                    "transport": "http",
                },
            }
        ]
    )


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------


def test_parse_iso8601_duration_to_s_handles_common_shapes():
    assert _parse_iso8601_duration_to_s("PT24H") == 24 * 3600
    assert _parse_iso8601_duration_to_s("PT5M") == 300
    assert _parse_iso8601_duration_to_s("PT1H30M15S") == 3600 + 30 * 60 + 15
    assert _parse_iso8601_duration_to_s("invalid") is None
    assert _parse_iso8601_duration_to_s(None) is None


# ---------------------------------------------------------------------------
# Behaviour matrix
# ---------------------------------------------------------------------------


async def test_online_first_dispatches_inline_when_online(tmp_path: Path):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["called"] = True
        return httpx.Response(
            200,
            json={
                "receipt_id": "r1",
                "commit_ts": "2026-05-08T00:00:00Z",
                "offsets": {"memory.write.v1": 1},
                "idem_key": "x",
                "obligations": [],
            },
        )

    transport = _make_transport(handler)
    outbox = LocalOutbox(db_path=tmp_path / "ob.db")
    health = K0HealthChecker()
    health.record_success(latency_ms=5)
    matrix = _matrix()
    client = OnlineFirstClient(
        inner=_RealishInner(transport),
        topic="memory.write.v1",
        schema_uri="bridge://contracts/schemas/memory.write.v1.json",
        port_kind="command",
        transport=transport,
        outbox=outbox,
        health=health,
        matrix=matrix,
    )
    try:
        result = await client.publish(_Payload(text="hi"))
        assert captured.get("called") is True
        assert result["receipt_id"] == "r1"
        assert outbox.pending_count() == 0
    finally:
        await transport.close()
        outbox.close()


async def test_online_first_queues_when_offline_and_queueable(tmp_path: Path):
    transport = _make_transport(lambda r: httpx.Response(200))
    outbox = LocalOutbox(db_path=tmp_path / "ob.db")
    health = K0HealthChecker()
    health.force_offline("test")
    matrix = _matrix(online_required=False)
    client = OnlineFirstClient(
        inner=_RealishInner(transport),
        topic="memory.write.v1",
        schema_uri="bridge://contracts/schemas/memory.write.v1.json",
        port_kind="command",
        transport=transport,
        outbox=outbox,
        health=health,
        matrix=matrix,
        max_queue_age_s=60,
    )
    try:
        result = await client.publish(_Payload(text="hi"))
        assert result is None
        assert outbox.pending_count() == 1
        # Stored row carries the per-row TTL forwarded by the wrapper.
        ttl = outbox._conn.execute(  # noqa: SLF001
            "SELECT max_queue_age_s FROM outbox_queue"
        ).fetchone()
        assert ttl == (60,)
    finally:
        await transport.close()
        outbox.close()


async def test_online_first_raises_when_offline_and_required(tmp_path: Path):
    transport = _make_transport(lambda r: httpx.Response(200))
    outbox = LocalOutbox(db_path=tmp_path / "ob.db")
    health = K0HealthChecker()
    health.force_offline("test")
    matrix = _matrix(online_required=True)
    client = OnlineFirstClient(
        inner=_RealishInner(transport),
        topic="memory.write.v1",
        schema_uri="bridge://contracts/schemas/memory.write.v1.json",
        port_kind="command",
        transport=transport,
        outbox=outbox,
        health=health,
        matrix=matrix,
    )
    try:
        with pytest.raises(OfflineError) as ei:
            await client.publish(_Payload(text="hi"))
        assert ei.value.topic == "memory.write.v1"
        assert ei.value.current_state is K0HealthState.OFFLINE
        assert ei.value.behavior is DegradedBehavior.RAISE_OFFLINE_ERROR
        assert outbox.pending_count() == 0
    finally:
        await transport.close()
        outbox.close()


async def test_online_first_queues_on_5xx_during_online_when_queueable(tmp_path: Path):
    transport = _make_transport(lambda r: httpx.Response(503))
    outbox = LocalOutbox(db_path=tmp_path / "ob.db")
    health = K0HealthChecker()
    health.record_success(latency_ms=5)  # ONLINE
    matrix = _matrix(online_required=False)
    client = OnlineFirstClient(
        inner=_RealishInner(transport),
        topic="memory.write.v1",
        schema_uri="bridge://contracts/schemas/memory.write.v1.json",
        port_kind="command",
        transport=transport,
        outbox=outbox,
        health=health,
        matrix=matrix,
    )
    try:
        result = await client.publish(_Payload(text="hi"))
        assert result is None
        assert outbox.pending_count() == 1
    finally:
        await transport.close()
        outbox.close()


async def test_online_first_propagates_4xx_does_not_queue(tmp_path: Path):
    transport = _make_transport(lambda r: httpx.Response(422, json={"err": "schema"}))
    outbox = LocalOutbox(db_path=tmp_path / "ob.db")
    health = K0HealthChecker()
    health.record_success(latency_ms=5)
    matrix = _matrix(online_required=False)
    client = OnlineFirstClient(
        inner=_RealishInner(transport),
        topic="memory.write.v1",
        schema_uri="bridge://contracts/schemas/memory.write.v1.json",
        port_kind="command",
        transport=transport,
        outbox=outbox,
        health=health,
        matrix=matrix,
    )
    try:
        from bridge.core.transport import BridgeTransportError

        with pytest.raises(BridgeTransportError) as ei:
            await client.publish(_Payload(text="hi"))
        assert ei.value.status_code == 422
        assert outbox.pending_count() == 0
    finally:
        await transport.close()
        outbox.close()


async def test_online_first_e2e_queue_then_drain_on_recovery(tmp_path: Path):
    """End-to-end: queue 5 envelopes during outage; flip ONLINE; drain via worker."""
    from bridge.sync.drain_worker import DrainWorker

    posts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "receipt_id": "r",
                "commit_ts": "2026-05-08T00:00:00Z",
                "offsets": {"memory.write.v1": 1},
                "idem_key": "x",
                "obligations": [],
            },
        )

    transport = _make_transport(handler)
    outbox = LocalOutbox(db_path=tmp_path / "ob.db")
    bus = EventBus()
    health = K0HealthChecker(event_bus=bus, failure_threshold=1)
    health.record_success(latency_ms=5)
    health.record_failure("k0_down")  # \u2192 OFFLINE
    assert health.status is K0HealthState.OFFLINE
    matrix = _matrix(online_required=False)

    client = OnlineFirstClient(
        inner=_RealishInner(transport),
        topic="memory.write.v1",
        schema_uri="bridge://contracts/schemas/memory.write.v1.json",
        port_kind="command",
        transport=transport,
        outbox=outbox,
        health=health,
        matrix=matrix,
    )
    worker = DrainWorker(
        outbox=outbox, transport=transport, event_bus=bus, safety_net_interval_s=10.0
    )
    try:
        for i in range(5):
            await client.publish(_Payload(text=f"m{i}"))
        assert outbox.pending_count() == 5

        await worker.start()
        # Trigger recovery via the bus.
        health.record_success(latency_ms=5)
        bus.publish(HealthTransition(from_state="OFFLINE", to_state="ONLINE", at_utc=utc_now()))
        import asyncio

        for _ in range(80):
            if outbox.pending_count() == 0:
                break
            await asyncio.sleep(0.02)
        assert outbox.pending_count() == 0
        assert len(posts) == 5
    finally:
        await worker.stop()
        await transport.close()
        outbox.close()
