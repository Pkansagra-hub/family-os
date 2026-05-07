"""Tests for bridge/client.py — StubBridgeClient + SinkBridgeClient.

Verifies:
  1. IBridgeClient is runtime-checkable and both impls satisfy it.
  2. StubBridgeClient records all calls and returns empty defaults.
  3. SinkBridgeClient queues commands, returns empty recall, drops obs.
  4. SinkBridgeClient raises NotImplementedError for IFL.

Milestone: MS-2 Epic 2.9
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge.client import IBridgeClient, SinkBridgeClient
from bridge.core.health import K0AvailabilityStatus
from bridge.ports.obs_port_protocol import FeedbackEnvelope
from bridge.sync.local_outbox import LocalOutbox
from bridge.testing import StubBridgeClient

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestIBridgeClientProtocol:
    def test_stub_satisfies_protocol(self):
        assert isinstance(StubBridgeClient(), IBridgeClient)

    def test_sink_satisfies_protocol(self, tmp_path: Path):
        outbox = LocalOutbox(db_path=tmp_path / "proto.db")
        assert isinstance(SinkBridgeClient(outbox), IBridgeClient)


# ---------------------------------------------------------------------------
# StubBridgeClient
# ---------------------------------------------------------------------------


class TestStubBridgeClient:
    @pytest.fixture
    def stub(self):
        return StubBridgeClient()

    @pytest.mark.asyncio
    async def test_submit_command_records_call(self, stub: StubBridgeClient):
        await stub.submit_command("memory.write", {"key": "val"}, band="B1")
        assert len(stub.calls) == 1
        method, args, kwargs = stub.calls[0]
        assert method == "submit_command"
        assert args[0] == "memory.write"
        assert kwargs["band"] == "B1"

    @pytest.mark.asyncio
    async def test_submit_batch_records_call(self, stub: StubBridgeClient):
        await stub.submit_command_batch([{"topic": "t1", "body": {}}])
        assert stub.calls[0][0] == "submit_command_batch"

    # MS-3c: ``query`` / ``query_single`` removed; recall is reachable only
    # via the typed paired-contract surface (``runtime.query.recall_request_v1``).
    # MS-3d: ``subscribe`` / ``ack`` / ``close_sse`` removed; SSE is reachable
    # only via the typed per-contract surface (``runtime.sse.<topic>.subscribe``).

    @pytest.mark.asyncio
    async def test_emit_obs_records_call(self, stub: StubBridgeClient):
        await stub.emit_obs("METRICS", {"cpu": 42}, priority="HIGH")
        assert stub.calls[0][0] == "emit_obs"

    @pytest.mark.asyncio
    async def test_emit_feedback_records_call(self, stub: StubBridgeClient):
        fb = FeedbackEnvelope(
            feedback_id="f1",
            pipeline_id="p1",
            signal_class="correction",
            payload={"delta": 0.1},
        )
        await stub.emit_feedback(fb)
        assert stub.calls[0][0] == "emit_feedback"

    @pytest.mark.asyncio
    async def test_execute_connector_returns_stub(self, stub: StubBridgeClient):
        result = await stub.execute_connector("hue-001", "set_brightness", {"level": 80})
        assert result == {"stub": True}

    def test_health_returns_online(self, stub: StubBridgeClient):
        snap = stub.health()
        assert snap.status == K0AvailabilityStatus.ONLINE


# ---------------------------------------------------------------------------
# SinkBridgeClient
# ---------------------------------------------------------------------------


class TestSinkBridgeClient:
    @pytest.fixture
    def outbox(self, tmp_path: Path):
        return LocalOutbox(db_path=tmp_path / "sink_outbox.db")

    @pytest.fixture
    def sink(self, outbox: LocalOutbox):
        return SinkBridgeClient(outbox)

    @pytest.mark.asyncio
    async def test_submit_command_enqueues_to_outbox(
        self, sink: SinkBridgeClient, outbox: LocalOutbox
    ):
        await sink.submit_command("memory.write", {"key": "val"})
        pending = outbox.list_pending(limit=10)
        assert len(pending) == 1
        assert pending[0].topic == "memory.write"

    @pytest.mark.asyncio
    async def test_submit_batch_enqueues_all(self, sink: SinkBridgeClient, outbox: LocalOutbox):
        batch = [
            {"topic": "t1", "body": {"a": 1}},
            {"topic": "t2", "body": {"b": 2}},
        ]
        await sink.submit_command_batch(batch)
        pending = outbox.list_pending(limit=10)
        assert len(pending) == 2
        topics = {e.topic for e in pending}
        assert topics == {"t1", "t2"}

    # MS-3c: ``query`` / ``query_single`` removed; recall is reachable only
    # via the typed paired-contract surface (``runtime.query.recall_request_v1``).
    # MS-3d: ``subscribe`` / ``ack`` / ``close_sse`` removed; SSE is reachable
    # only via the typed per-contract surface (``runtime.sse.<topic>.subscribe``).

    @pytest.mark.asyncio
    async def test_emit_obs_drops_low_priority(self, sink: SinkBridgeClient):
        # LOW priority is dropped when OFFLINE — no side effects to check,
        # just verify it doesn't raise
        await sink.emit_obs("METRICS", {"cpu": 42}, priority="LOW")

    @pytest.mark.asyncio
    async def test_emit_obs_logs_normal_priority(self, sink: SinkBridgeClient):
        await sink.emit_obs("METRICS", {"cpu": 42}, priority="NORMAL")

    @pytest.mark.asyncio
    async def test_emit_feedback_drops(self, sink: SinkBridgeClient):
        fb = FeedbackEnvelope(
            feedback_id="f1",
            pipeline_id="p1",
            signal_class="correction",
            payload={},
        )
        await sink.emit_feedback(fb)  # should not raise

    @pytest.mark.asyncio
    async def test_execute_connector_raises_not_implemented(self, sink: SinkBridgeClient):
        with pytest.raises(NotImplementedError, match="MS-3"):
            await sink.execute_connector("hue-001", "set_brightness", {"level": 80})

    def test_health_returns_offline(self, sink: SinkBridgeClient):
        snap = sink.health()
        assert snap.status == K0AvailabilityStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_submit_command_generates_trace_id(
        self, sink: SinkBridgeClient, outbox: LocalOutbox
    ):
        """Envelope gets a trace_id even if caller doesn't provide one."""
        await sink.submit_command("memory.write", {"key": "val"})
        pending = outbox.list_pending(limit=1)
        import json

        envelope = json.loads(pending[0].envelope_json)
        assert envelope["trace_id"] is not None
        assert len(envelope["trace_id"]) == 32  # uuid4.hex
