"""Tests for KernelQueryPort, KernelSSEPort, KernelObsPort.

Issue 3.9.3 / 3.9.4 / 3.9.5 (MS-3): Scaffold adapter tests.
Uses httpx.MockTransport — no real K0 needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from bridge.core.transport import HttpTransport, TransportConfig
from bridge.kernel.obs_port import KernelObsPort
from bridge.kernel.query_port import KernelQueryPort
from bridge.kernel.sse_port import KernelSSEPort
from bridge.ports.obs_port_protocol import FeedbackEnvelope
from bridge.ports.query_port_protocol import QueryEnvelope, RecallSelector
from bridge.ports.sse_port_protocol import SSETraceEvent
from bridge.sync.local_outbox import LocalOutbox

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(handler) -> HttpTransport:
    transport = HttpTransport(TransportConfig(base_url="http://test-k0:8000"))
    transport._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://test-k0:8000",
    )
    return transport


def _ok_json(body: dict) -> httpx.Response:
    return httpx.Response(200, json=body)


def _error_response(status: int = 500) -> httpx.Response:
    return httpx.Response(status, json={"error": "test"})


# ===========================================================================
# KernelQueryPort (Issue 3.9.3)
# ===========================================================================


class TestKernelQueryPortOnline:
    """Query port returns parsed RecallBundle when K0 responds 200."""

    @pytest.mark.asyncio
    async def test_query_returns_parsed_bundle(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _ok_json(
                {
                    "items": [
                        {
                            "selector_type": "episodic",
                            "content": {"text": "memory_1"},
                            "score": 0.95,
                            "source": "wal",
                            "cursor": "c1",
                        },
                        {
                            "selector_type": "semantic",
                            "content": {"text": "memory_2"},
                            "score": 0.8,
                            "source": "pgvector",
                            "cursor": "c2",
                        },
                    ],
                    "total_count": 2,
                    "latency_ms": 42,
                    "partial": False,
                }
            )

        port = KernelQueryPort(transport=_make_transport(handler))
        envelope = QueryEnvelope(
            selectors=[
                RecallSelector(type="episodic", limit=5),
                RecallSelector(type="semantic", query="test"),
            ],
            trace_id="tr-1",
        )
        bundle = await port.query(envelope)

        assert len(bundle.items) == 2
        assert bundle.items[0].selector_type == "episodic"
        assert bundle.items[0].score == 0.95
        assert bundle.items[1].content == {"text": "memory_2"}
        assert bundle.total_count == 2
        assert bundle.latency_ms == 42
        assert bundle.partial is False
        assert bundle.trace_id == "tr-1"

    @pytest.mark.asyncio
    async def test_query_single_wraps_selector(self) -> None:
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return _ok_json({"items": [], "total_count": 0})

        port = KernelQueryPort(transport=_make_transport(handler))
        sel = RecallSelector(type="belief", topic="family", limit=3)
        await port.query_single(sel, trace_id="tr-2")

        assert len(captured) == 1
        assert len(captured[0]["selectors"]) == 1
        assert captured[0]["selectors"][0]["type"] == "belief"
        assert captured[0]["trace_id"] == "tr-2"

    @pytest.mark.asyncio
    async def test_query_sends_correct_request_body(self) -> None:
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return _ok_json({"items": []})

        port = KernelQueryPort(transport=_make_transport(handler))
        envelope = QueryEnvelope(
            selectors=[RecallSelector(type="session", limit=10, after="2026-01-01")],
            space_id="sp-1",
            tenant_id="tn-1",
            max_latency_ms=500,
            fail_fast=True,
            trace_id="tr-3",
        )
        await port.query(envelope)

        body = captured[0]
        assert body["space_id"] == "sp-1"
        assert body["tenant_id"] == "tn-1"
        assert body["max_latency_ms"] == 500
        assert body["fail_fast"] is True
        assert body["selectors"][0]["after"] == "2026-01-01"


class TestKernelQueryPortOffline:
    """Query port returns empty bundle on failure."""

    @pytest.mark.asyncio
    async def test_query_returns_empty_on_500(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _error_response(500)

        port = KernelQueryPort(transport=_make_transport(handler))
        bundle = await port.query(QueryEnvelope(selectors=[], trace_id="tr-err"))

        assert len(bundle.items) == 0
        assert bundle.trace_id == "tr-err"

    @pytest.mark.asyncio
    async def test_query_returns_empty_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        port = KernelQueryPort(transport=_make_transport(handler))
        bundle = await port.query(
            QueryEnvelope(selectors=[RecallSelector(type="episodic")], trace_id="tr-down")
        )

        assert len(bundle.items) == 0
        assert bundle.trace_id == "tr-down"

    @pytest.mark.asyncio
    async def test_query_returns_empty_on_malformed_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        port = KernelQueryPort(transport=_make_transport(handler))
        bundle = await port.query(QueryEnvelope(selectors=[], trace_id="tr-bad"))

        assert len(bundle.items) == 0


# ===========================================================================
# KernelSSEPort (Issue 3.9.4)
# ===========================================================================


class TestKernelSSEPortOffline:
    """SSE port returns empty iterator on failure."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_empty_on_transport_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        port = KernelSSEPort(transport=_make_transport(handler))
        stream = await port.subscribe(topics=["memory.formed.v1"])

        events = [e async for e in stream]
        assert events == []

    @pytest.mark.asyncio
    async def test_subscribe_returns_empty_on_500(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _error_response(500)

        port = KernelSSEPort(transport=_make_transport(handler))
        stream = await port.subscribe()

        events = [e async for e in stream]
        assert events == []

    @pytest.mark.asyncio
    async def test_ack_no_error_on_transport_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        port = KernelSSEPort(transport=_make_transport(handler))
        # Should not raise
        await port.ack("memory.formed.v1", "cursor-42")

    @pytest.mark.asyncio
    async def test_close_sets_inactive(self) -> None:
        port = KernelSSEPort(transport=_make_transport(lambda r: _error_response()))
        port._active = True
        await port.close()
        assert port._active is False


class TestKernelSSEPortOnline:
    """SSE port parses events when K0 responds 200."""

    @pytest.mark.asyncio
    async def test_subscribe_parses_events(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _ok_json(
                {
                    "events": [
                        {
                            "topic": "memory.formed.v1",
                            "cursor": "c-1",
                            "wal_pos": 100,
                            "commit_ts": "2026-04-12T00:00:00Z",
                            "data": {"atom_id": "a1"},
                        },
                        {
                            "topic": "k0.learning.advisory.v1",
                            "cursor": "c-2",
                            "wal_pos": 101,
                            "data": {"advisory": "retrain"},
                            "backpressure": {
                                "level": "throttle",
                                "lag_ms": 500,
                                "pending_events": 20,
                            },
                        },
                    ],
                }
            )

        port = KernelSSEPort(transport=_make_transport(handler))
        stream = await port.subscribe(topics=["memory.formed.v1"])
        events = [e async for e in stream]

        assert len(events) == 2
        assert isinstance(events[0], SSETraceEvent)
        assert events[0].topic == "memory.formed.v1"
        assert events[0].cursor == "c-1"
        assert events[0].wal_pos == 100
        assert events[0].data == {"atom_id": "a1"}
        assert events[0].backpressure is None

        assert events[1].topic == "k0.learning.advisory.v1"
        assert events[1].backpressure is not None
        assert events[1].backpressure.lag_ms == 500
        assert events[1].backpressure.pending_events == 20

    @pytest.mark.asyncio
    async def test_ack_sends_correct_body(self) -> None:
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return _ok_json({})

        port = KernelSSEPort(transport=_make_transport(handler))
        await port.ack("memory.formed.v1", "cursor-99")

        assert len(captured) == 1
        assert captured[0] == {"topic": "memory.formed.v1", "cursor": "cursor-99"}


# ===========================================================================
# KernelObsPort (Issue 3.9.5)
# ===========================================================================


class TestKernelObsPortOnline:
    """Obs port emits successfully when K0 responds 200."""

    @pytest.mark.asyncio
    async def test_emit_sends_payload(self) -> None:
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return _ok_json({})

        port = KernelObsPort(transport=_make_transport(handler))
        await port.emit("metrics", {"cpu": 0.5}, priority="NORMAL", trace_id="tr-obs")

        assert len(captured) == 1
        assert captured[0]["kind"] == "metrics"
        assert captured[0]["body"] == {"cpu": 0.5}
        assert captured[0]["priority"] == "NORMAL"
        assert captured[0]["trace_id"] == "tr-obs"

    @pytest.mark.asyncio
    async def test_emit_feedback_sends_envelope(self) -> None:
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return _ok_json({})

        port = KernelObsPort(transport=_make_transport(handler))
        fb = FeedbackEnvelope(
            feedback_id="fb-1",
            pipeline_id="P02",
            signal_class="CORRECTION",
            correlation={"session_id": "s1"},
            provenance={"hash": "abc"},
            payload={"correction": "spelling"},
            trace_id="tr-fb",
        )
        await port.emit_feedback(fb)

        assert len(captured) == 1
        assert captured[0]["kind"] == "feedback"
        assert captured[0]["priority"] == "HIGH"
        assert captured[0]["body"]["feedback_id"] == "fb-1"
        assert captured[0]["body"]["pipeline_id"] == "P02"


class TestKernelObsPortOffline:
    """Obs port handles offline: drop LOW, queue NORMAL/HIGH."""

    @pytest.mark.asyncio
    async def test_emit_low_dropped_on_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        port = KernelObsPort(transport=_make_transport(handler), outbox=None)
        # Should not raise — LOW is silently dropped
        await port.emit("metrics", {"cpu": 0.5}, priority="LOW")

    @pytest.mark.asyncio
    async def test_emit_normal_queued_to_outbox(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        outbox = LocalOutbox(db_path=tmp_path / "obs_test.db")
        try:
            port = KernelObsPort(transport=_make_transport(handler), outbox=outbox)
            await port.emit("logs", {"msg": "test"}, priority="NORMAL", trace_id="tr-q")

            pending = outbox.pending_count()
            assert pending >= 1
        finally:
            outbox.close()

    @pytest.mark.asyncio
    async def test_emit_high_queued_to_outbox(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        outbox = LocalOutbox(db_path=tmp_path / "obs_high_test.db")
        try:
            port = KernelObsPort(transport=_make_transport(handler), outbox=outbox)
            await port.emit("feedback", {"signal": "x"}, priority="HIGH")

            pending = outbox.pending_count()
            assert pending >= 1
        finally:
            outbox.close()

    @pytest.mark.asyncio
    async def test_emit_normal_no_outbox_no_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        port = KernelObsPort(transport=_make_transport(handler), outbox=None)
        # NORMAL without outbox: logged warning, no raise
        await port.emit("logs", {"msg": "test"}, priority="NORMAL")

    @pytest.mark.asyncio
    async def test_emit_feedback_queued_on_failure(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("K0 unreachable")

        outbox = LocalOutbox(db_path=tmp_path / "fb_test.db")
        try:
            port = KernelObsPort(transport=_make_transport(handler), outbox=outbox)
            fb = FeedbackEnvelope(feedback_id="fb-2", trace_id="tr-fb2")
            await port.emit_feedback(fb)

            pending = outbox.pending_count()
            assert pending >= 1
        finally:
            outbox.close()

    @pytest.mark.asyncio
    async def test_emit_on_non_200_queues_normal(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _error_response(503)

        outbox = LocalOutbox(db_path=tmp_path / "obs_503.db")
        try:
            port = KernelObsPort(transport=_make_transport(handler), outbox=outbox)
            await port.emit("logs", {"msg": "x"}, priority="NORMAL")

            pending = outbox.pending_count()
            assert pending >= 1
        finally:
            outbox.close()


# ===========================================================================
# Protocol conformance
# ===========================================================================


class TestProtocolConformance:
    """Verify adapters satisfy their port protocols."""

    def test_query_port_satisfies_protocol(self) -> None:
        from bridge.ports.query_port_protocol import IKernelQueryPort

        transport = HttpTransport(TransportConfig())
        port = KernelQueryPort(transport=transport)
        assert isinstance(port, IKernelQueryPort)

    def test_sse_port_satisfies_protocol(self) -> None:
        from bridge.ports.sse_port_protocol import IKernelSSEPort

        transport = HttpTransport(TransportConfig())
        port = KernelSSEPort(transport=transport)
        assert isinstance(port, IKernelSSEPort)

    def test_obs_port_satisfies_protocol(self) -> None:
        from bridge.ports.obs_port_protocol import IKernelObsPort

        transport = HttpTransport(TransportConfig())
        port = KernelObsPort(transport=transport)
        assert isinstance(port, IKernelObsPort)
