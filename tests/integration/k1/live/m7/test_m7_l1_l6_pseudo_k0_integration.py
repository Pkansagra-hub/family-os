"""M7-L1..M7-L6 pseudo-K0 / Recipe-C live integration probes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bridge.client import HttpBridgeClient, SinkBridgeClient
from k1.concierge.adapters.recall_memory import build_recall_fn
from k1.concierge.bus.topics import TOPIC_TOOL_STATE_CHANGED
from k1.kernel.adapters.bridge_adapter import OfflineBridgeAdapter
from k1.kernel.adapters.bridge_adapter import SinkBridgeAdapter as KernelSinkBridgeAdapter
from k1.kernel.adapters.live_bridge_adapter import LiveBridgeAdapter, LiveBridgeClient
from k1.kernel.service import KernelService
from tests.integration.k1.live.m6.helpers import active_task_snapshot as _active_task_snapshot
from tests.integration.k1.live.m6.helpers import assert_no_task_leaks as _assert_no_task_leaks
from tests.integration.k1.live.m6.helpers import cleanup_service as _cleanup_service
from tests.integration.k1.live.m6.helpers import recipe_a as _recipe_a
from tests.integration.k1.live.m7.helpers import PseudoK0Handle
from tests.integration.k1.live.m7.helpers import memory_write_payload as _memory_write_payload
from tests.integration.k1.live.m7.helpers import pseudo_k0_server
from tests.integration.k1.live.m7.helpers import recipe_c_pseudo_k0 as _recipe_c_pseudo_k0
from tests.integration.k1.live.m7.helpers import wait_for_sse_subscriber as _wait_for_sse_subscriber
from tests.integration.k1.live.m7.helpers import wait_until as _wait_until
from tests.integration.k1.live.m7.helpers import wal_rows as _wal_rows

pytestmark = pytest.mark.integration


def _live_client(svc: KernelService) -> LiveBridgeClient:
    assert isinstance(svc._bridge, LiveBridgeAdapter)
    client = svc._bridge.get_client()
    assert isinstance(client, LiveBridgeClient)
    return client


@pytest.mark.asyncio
@pytest.mark.xfail_on_real_k0
async def test_m7_l1_memory_write_round_trip_to_pseudo_k0_wal(
    tmp_path: Path,
    pseudo_k0_server: PseudoK0Handle,
) -> None:
    """Typed memory.write.v1 reaches pseudo-K0 WAL with provenance and signature fields."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_pseudo_k0(tmp_path, pseudo_k0_server.endpoint))

    try:
        await svc.startup()
        client = _live_client(svc)
        assert isinstance(svc._bridge._http_bridge_client, HttpBridgeClient)
        assert client.memory_write_v1 is not None

        await client.memory_write_v1.publish(
            _memory_write_payload(
                "Alex remembered the purple lunchbox before school.",
                session_id="m7l1",
            )
        )

        rows = _wal_rows(pseudo_k0_server.store)
        assert len(rows) == 1
        row = rows[0]
        assert row["topic"] == "memory.write.v1"
        assert row["space_id"] == "family:m7"
        assert row["actor_id"] == "actor:m7"
        assert row["band"] == "GREEN"
        assert row["trace_id"]
        assert "purple lunchbox" in row["content"]

        body = json.loads(row["body"])
        envelope = json.loads(row["envelope"])
        assert body["text"] == "Alex remembered the purple lunchbox before school."
        assert envelope["payload_sha256"]
        assert envelope["envelope_sha256"]
        assert envelope["sig_alg"] == "hmac-sha256"
        assert envelope["sig"]
        assert "idem_key" not in envelope
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail_on_real_k0
async def test_m7_l2_recall_request_like_search_returns_pseudo_k0_hits(
    tmp_path: Path,
    pseudo_k0_server: PseudoK0Handle,
) -> None:
    """recall.request.v1 uses pseudo-K0 LIKE search and preserves hit source tags."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_pseudo_k0(tmp_path, pseudo_k0_server.endpoint))

    try:
        await svc.startup()
        client = _live_client(svc)
        await client.submit_command(
            "memory.write.v1",
            {
                "memory_type": "semantic",
                "content": "Alex is allergic to peanuts and carries an epipen.",
            },
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            trace_id="trace-m7-l2-seed",
        )

        recall_fn = build_recall_fn(client, space_id="family:m7")
        hits = await recall_fn("peanut", ["semantic"], 5)
        assert len(hits) == 1
        assert hits[0]["selector_type"] == "semantic"
        assert hits[0]["source"].startswith("pseudo_k0")
        assert "peanut" in hits[0]["content"]["content"].lower()

        assert await recall_fn("peanut", ["belief"], 5) == []
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail_on_real_k0
async def test_m7_l3_tool_state_sse_republishes_to_k1_bus(
    tmp_path: Path,
    pseudo_k0_server: PseudoK0Handle,
) -> None:
    """pseudo-K0 tool_state.changed.v1 SSE is forwarded onto the K1 bus."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_pseudo_k0(tmp_path, pseudo_k0_server.endpoint))
    received: list[dict[str, Any]] = []
    handle: Any = None

    try:
        await svc.startup()
        client = _live_client(svc)

        def capture(envelope: Any) -> None:
            received.append(json.loads(envelope.payload))

        handle = svc._bus.subscribe(TOPIC_TOOL_STATE_CHANGED, capture)
        await _wait_for_sse_subscriber(pseudo_k0_server, "tool_state.changed.v1")

        await client.submit_command(
            "k1.tool_state.calendar.changed.v1",
            {"adapter_id": "calendar", "action": "refresh", "space_id": "family:m7"},
            schema_uri="bridge://contracts/schemas/tool_state.changed.v1.json",
            trace_id="trace-m7-l3",
        )
        await _wait_until(lambda: bool(received), timeout_s=5.0)

        assert received[0]["adapter_id"] == "calendar"
        assert received[0]["action"] == "refresh"
        assert received[0]["topic"] == "k1.tool_state.calendar.changed.v1"
        assert received[0]["trace_id"] == "trace-m7-l3"
    finally:
        if handle is not None and svc._bus is not None:
            svc._bus.unsubscribe(handle)
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail_on_real_k0
async def test_m7_l4_connector_execute_routes_to_pseudo_k0_connector_host(
    tmp_path: Path,
    pseudo_k0_server: PseudoK0Handle,
) -> None:
    """connector.execute.* reaches pseudo-K0 ConnectorHost through the live bridge."""
    calls: list[dict[str, Any]] = []

    async def create_event(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params)
        return {"event_id": "evt-m7-l4", "title": params["title"]}

    pseudo_k0_server.connector_host.register_fn("calendar", "create_event", create_event)

    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_pseudo_k0(tmp_path, pseudo_k0_server.endpoint))

    try:
        await svc.startup()
        client = _live_client(svc)
        result = await client.execute_connector(
            "calendar",
            "create_event",
            {"title": "Dentist", "starts_at": "2026-05-16T09:00:00Z"},
            trace_id="trace-m7-l4",
        )

        assert result["ok"] is True
        assert result["trace_id"] == "trace-m7-l4"
        assert result["result"] == {"event_id": "evt-m7-l4", "title": "Dentist"}
        assert calls == [{"title": "Dentist", "starts_at": "2026-05-16T09:00:00Z"}]
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason="I7.2.4 gap: LiveBridgeAdapter does not yet own LocalOutbox/DrainWorker recovery.",
)
async def test_m7_l5_live_bridge_queues_and_drains_after_pseudo_k0_restart(
    tmp_path: Path,
    pseudo_k0_server: PseudoK0Handle,
) -> None:
    """Desired negative: K0 outage queues locally, restart drains, metrics increment."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_pseudo_k0(tmp_path, pseudo_k0_server.endpoint))

    try:
        await svc.startup()
        client = _live_client(svc)
        pseudo_k0_server.stop()

        await client.submit_command(
            "memory.write.v1",
            {"memory_type": "episodic", "content": "queued while K0 is down"},
            schema_uri="bridge://contracts/schemas/memory.write.v1.json",
            trace_id="trace-m7-l5",
        )

        outbox = getattr(client, "_outbox", None)
        assert outbox is not None
        assert outbox.pending_count() == 1

        pseudo_k0_server.restart()
        drain_worker = getattr(client, "_drain_worker", None)
        assert drain_worker is not None
        await drain_worker.drain_now()

        assert outbox.pending_count() == 0
        rows = _wal_rows(pseudo_k0_server.store)
        assert any(row["trace_id"] == "trace-m7-l5" for row in rows)
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m7_l6_s4_bridge_mode_selects_expected_client_classes(
    tmp_path: Path,
    pseudo_k0_server: PseudoK0Handle,
) -> None:
    """S4 selects live HTTP, sink outbox, or null bridge by KernelConfig."""
    baseline_tasks = _active_task_snapshot()
    live_dir = tmp_path / "live"
    sink_dir = tmp_path / "sink"
    offline_dir = tmp_path / "offline"
    live_dir.mkdir()
    sink_dir.mkdir()
    offline_dir.mkdir()

    live = KernelService(config=_recipe_c_pseudo_k0(live_dir, pseudo_k0_server.endpoint))
    try:
        await live.startup()
        live_client = _live_client(live)
        assert live._bridge.is_connected() is True
        assert isinstance(live._bridge._http_bridge_client, HttpBridgeClient)
        assert live_client.memory_write_v1 is live._bridge._http_bridge_client.memory_write_v1
    finally:
        await _cleanup_service(live, baseline_tasks)

    sink = KernelService(
        config=_recipe_a(
            sink_dir,
            bridge_enabled=True,
            k0_endpoint="",
            bridge_outbox_path=str(sink_dir / "bridge.db"),
        )
    )
    try:
        await sink.startup()
        assert isinstance(sink._bridge, KernelSinkBridgeAdapter)
        assert isinstance(sink._bridge.get_client(), SinkBridgeClient)
        assert sink._bridge.is_connected() is False
    finally:
        await _cleanup_service(sink, baseline_tasks)

    offline = KernelService(
        config=_recipe_a(
            offline_dir,
            bridge_enabled=False,
            k0_endpoint="",
        )
    )
    try:
        await offline.startup()
        assert isinstance(offline._bridge, OfflineBridgeAdapter)
        assert offline._bridge.get_client() is None
        assert offline._bridge.is_connected() is False
    finally:
        await _cleanup_service(offline, baseline_tasks)

    await _assert_no_task_leaks(baseline_tasks)