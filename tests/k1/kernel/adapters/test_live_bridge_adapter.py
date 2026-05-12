"""Tests for k1.kernel.adapters.live_bridge_adapter.LiveBridgeAdapter.

Smoke-tests the adapter against the pseudo-K0 server in-process.
Run: python -m pytest tests/k1/kernel/adapters/test_live_bridge_adapter.py -q --no-cov
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from k1.kernel.adapters.live_bridge_adapter import LiveBridgeAdapter
from scripts.pseudo_k0.connector_host import ConnectorHost
from scripts.pseudo_k0.server import create_app
from scripts.pseudo_k0.store import SQLiteK0Store


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _UvicornThread(threading.Thread):
    def __init__(self, app, host: str, port: int) -> None:
        super().__init__(daemon=True)
        cfg = uvicorn.Config(app=app, host=host, port=port, log_level="warning", lifespan="off")
        self.server = uvicorn.Server(cfg)

    def run(self) -> None:
        self.server.run()


@pytest.fixture
def pseudo_k0_server():
    port = _find_free_port()
    store = SQLiteK0Store(":memory:")
    app = create_app(store=store, connector_host=ConnectorHost())
    t = _UvicornThread(app, "127.0.0.1", port)
    t.start()
    # Wait for server to come up.
    deadline = time.time() + 5.0
    while time.time() < deadline and not getattr(t.server, "started", False):
        time.sleep(0.05)
    if not getattr(t.server, "started", False):
        t.server.should_exit = True
        pytest.fail("pseudo-K0 server failed to start")
    yield f"http://127.0.0.1:{port}", store
    t.server.should_exit = True
    t.join(timeout=5.0)


class TestLiveBridgeAdapter:
    @pytest.mark.asyncio
    async def test_connect_disconnect_idempotent(self, pseudo_k0_server) -> None:
        endpoint, _ = pseudo_k0_server
        adapter = LiveBridgeAdapter(endpoint=endpoint)
        assert adapter.is_connected() is False
        assert adapter.get_client() is None

        await adapter.connect()
        assert adapter.is_connected() is True
        assert adapter.get_client() is not None

        # Idempotent.
        await adapter.connect()
        assert adapter.is_connected() is True

        await adapter.disconnect()
        assert adapter.is_connected() is False
        assert adapter.get_client() is None

    @pytest.mark.asyncio
    async def test_disconnect_without_connect_is_safe(self) -> None:
        adapter = LiveBridgeAdapter(endpoint="http://127.0.0.1:1")
        await adapter.disconnect()
        assert adapter.is_connected() is False

    @pytest.mark.asyncio
    async def test_submit_command_writes_to_pseudo_k0(self, pseudo_k0_server) -> None:
        """End-to-end: submit_command → POST /k0/command.submit → WAL row."""
        endpoint, store = pseudo_k0_server
        adapter = LiveBridgeAdapter(
            endpoint=endpoint,
            default_space_id="family:test",
            default_actor="alice",
        )
        await adapter.connect()
        try:
            client = adapter.get_client()
            assert client is not None
            assert client.is_connected() is True

            await client.submit_command(
                "memory.delta",
                {"content": "hello-from-mw", "summary": "s"},
                schema_uri="schema://memory.delta",
                trace_id="trace-abc",
            )
        finally:
            await adapter.disconnect()

        wal_rows, _ = store.counts()
        assert wal_rows == 1

    @pytest.mark.asyncio
    async def test_submit_command_batch_writes_mw_envelopes(self, pseudo_k0_server) -> None:
        """End-to-end: MW envelope shape (with ``headers``) lands in WAL.

        Mirrors what ``BridgeCommandAdapter.submit_batch`` will push when the
        DeltaAggregator flushes a real batch.
        """
        endpoint, store = pseudo_k0_server
        adapter = LiveBridgeAdapter(
            endpoint=endpoint,
            default_space_id="family:default",
            default_actor="bob",
        )
        await adapter.connect()
        try:
            client = adapter.get_client()
            mw_envelopes = [
                {
                    "topic": "memory.delta",
                    "schema_uri": "schema://memory.delta",
                    "body": {
                        "content": "atom-one",
                        "memory_type": "episodic",
                    },
                    "trace_id": "trace-1",
                    "headers": {
                        "cognitive_trace_id": "trace-1",
                        "tenant_id": "t1",
                        "space_id": "family:alpha",
                        "actor": "alice",
                        "device_id": "dev-1",
                        "band": "GREEN",
                        "schema_uri": "schema://memory.delta",
                        "schema_version": "1.0",
                    },
                },
                {
                    "topic": "memory.delta",
                    "schema_uri": "schema://memory.delta",
                    "body": {"content": "atom-two", "memory_type": "episodic"},
                    "trace_id": "trace-2",
                    "headers": {
                        "tenant_id": "t1",
                        "space_id": "family:alpha",
                        "actor": "alice",
                        "device_id": "dev-1",
                        "band": "GREEN",
                    },
                },
            ]
            await client.submit_command_batch(mw_envelopes)
        finally:
            await adapter.disconnect()

        wal_rows, _ = store.counts()
        assert wal_rows == 2

        # Verify space_id / actor were flattened from headers correctly.
        with store._lock:  # noqa: SLF001 — test introspection
            rows = store._conn.execute(  # noqa: SLF001
                "SELECT space_id, actor_id, content, trace_id " "FROM wal ORDER BY id ASC"
            ).fetchall()
        assert [r["space_id"] for r in rows] == ["family:alpha", "family:alpha"]
        assert [r["actor_id"] for r in rows] == ["alice", "alice"]
        assert [r["content"] for r in rows] == ["atom-one", "atom-two"]
        assert [r["trace_id"] for r in rows] == ["trace-1", "trace-2"]

    @pytest.mark.asyncio
    async def test_recall_request_returns_seeded_hits(self, pseudo_k0_server) -> None:
        """End-to-end: seed → recall_memory closure → pseudo-K0 WAL → hits.

        Mirrors the concierge ``recall_memory`` tool path:
        :func:`k1.concierge.adapters.recall_memory.build_recall_fn` resolves
        the ``recall_request_v1`` slot off the live client (our
        :class:`_LiveRecallSlot` shim) and POSTs to
        ``/k0/command.submit``. Pseudo-K0 routes ``recall.request.v1`` to
        :meth:`SQLiteK0Store.recall` and returns matching WAL rows.
        """
        from k1.concierge.adapters.recall_memory import build_recall_fn

        endpoint, _ = pseudo_k0_server
        adapter = LiveBridgeAdapter(
            endpoint=endpoint,
            default_space_id="family:smith",
            default_actor="alice",
        )
        await adapter.connect()
        try:
            client = adapter.get_client()
            # Seed 3 memories under family:smith.
            await client.submit_command_batch(
                [
                    {
                        "topic": "memory.write.v1",
                        "schema_uri": "schema://memory.write.v1",
                        "body": {
                            "memory_type": "episodic",
                            "content": "Dad took Alex to the dentist last Tuesday",
                        },
                        "headers": {"space_id": "family:smith", "actor": "dad"},
                    },
                    {
                        "topic": "memory.write.v1",
                        "schema_uri": "schema://memory.write.v1",
                        "body": {
                            "memory_type": "semantic",
                            "content": "Alex is allergic to peanuts",
                        },
                        "headers": {"space_id": "family:smith", "actor": "mom"},
                    },
                    {
                        "topic": "memory.write.v1",
                        "schema_uri": "schema://memory.write.v1",
                        "body": {
                            "memory_type": "episodic",
                            "content": "Family vacation to Yellowstone in July",
                        },
                        "headers": {"space_id": "family:smith", "actor": "dad"},
                    },
                ]
            )

            # Call recall the same way ``execute_recall_memory`` would
            # — but pass the family space explicitly so the typed
            # ``RecallRequestV1.space_id`` matches the seeded WAL rows.
            recall_fn = build_recall_fn(client, space_id="family:smith")
            hits = await recall_fn("peanut", ["semantic"], 5)
        finally:
            await adapter.disconnect()

        assert isinstance(hits, list)
        assert len(hits) >= 1
        # Hit shape: {selector_type, content, score, source}
        contents = " ".join(str(h.get("content", "")) for h in hits)
        assert "peanut" in contents.lower()
        assert hits[0].get("source", "").startswith("pseudo_k0")
