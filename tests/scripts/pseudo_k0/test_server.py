"""Tests for scripts.pseudo_k0.server (FastAPI handlers)."""

from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from scripts.pseudo_k0.connector_host import ConnectorHost
from scripts.pseudo_k0.server import create_app
from scripts.pseudo_k0.store import SQLiteK0Store


@pytest.fixture
def client() -> TestClient:
    store = SQLiteK0Store(":memory:")
    host = ConnectorHost()

    async def echo(params: Dict[str, Any]) -> Dict[str, Any]:
        return {"echoed": params}

    host.register_fn("echo", "ping", echo)
    app = create_app(store, connector_host=host)
    return TestClient(app)


def _envelope(topic: str, body: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    env = {
        "topic": topic,
        "body": body,
        "tenant_id": "t1",
        "space_id": "default",
        "actor": "test",
        "device_id": "dev1",
        "ts": "2026-05-11T10:00:00.000000Z",
        "band": "GREEN",
        "schema_uri": f"bridge://contracts/schemas/{topic}.json",
        "schema_version": "2.2",
        "sig_alg": "hmac-sha256",
        "sig_kid": "test-001",
        "sig": "AAAA",
        "cognitive_trace_id": "trace-xyz",
    }
    env.update(extra)
    return env


class TestHealthz:
    def test_healthz_ok(self, client: TestClient) -> None:
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["wal_rows"] == 0
        assert body["obs_rows"] == 0


class TestCommandSubmitRecall:
    def test_recall_empty_store_returns_response_v1_shape(self, client: TestClient) -> None:
        env = _envelope(
            "recall.request.v1",
            {
                "selectors": [{"type": "semantic", "limit": 5, "query": "hello"}],
                "space_id": "default",
                "max_results": 5,
                "vector_query": "hello",
            },
        )
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 200, r.text
        body = r.json()
        # RecallResponseV1 contract shape
        assert "hits" in body
        assert body["hits"] == []
        assert body["total"] == 0
        assert "latency_ms" in body
        assert isinstance(body["latency_ms"], int)
        assert body["truncated"] is False
        assert body["trace_id"] == "trace-xyz"

    def test_recall_after_write_returns_hit(self, client: TestClient) -> None:
        write_env = _envelope(
            "memory.write.v1",
            {
                "memory_type": "episodic",
                "content": "Alice loves cookies",
                "tenant_id": "t1",
                "space_id": "default",
            },
        )
        wr = client.post("/k0/command.submit", json=write_env)
        assert wr.status_code == 200, wr.text
        ack = wr.json()
        assert ack["ok"] is True
        assert ack["topic"] == "memory.write.v1"
        assert isinstance(ack["wal_row_id"], int)

        recall_env = _envelope(
            "recall.request.v1",
            {
                "selectors": [{"type": "episodic", "limit": 5, "query": "cookies"}],
                "space_id": "default",
                "max_results": 5,
            },
        )
        rr = client.post("/k0/command.submit", json=recall_env)
        assert rr.status_code == 200, rr.text
        body = rr.json()
        assert body["total"] >= 1
        assert len(body["hits"]) >= 1
        hit = body["hits"][0]
        assert hit["atom_id"].startswith("wal:")
        assert hit["source"].startswith("pseudo_k0")
        # RecallHit.content must be a dict per contract
        assert isinstance(hit["content"], dict)

    def test_recall_invalid_body_returns_400(self, client: TestClient) -> None:
        env = _envelope("recall.request.v1", {"selectors": [], "space_id": "default"})
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_recall_body"


class TestCommandSubmitWrites:
    def test_memory_write_persists_and_acks(self, client: TestClient) -> None:
        env = _envelope(
            "memory.write.v1",
            {"memory_type": "belief", "content": "sky is blue"},
        )
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 200
        ack = r.json()
        assert ack["ok"] is True
        assert ack["trace_id"] == "trace-xyz"

    def test_unknown_topic_still_persists(self, client: TestClient) -> None:
        env = _envelope("custom.topic.v1", {"foo": "bar"})
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestCommandSubmitConnector:
    def test_connector_dispatch_ok(self, client: TestClient) -> None:
        env = _envelope(
            "connector.execute.v1",
            {"adapter_id": "echo", "action": "ping", "params": {"x": 1}},
        )
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["result"] == {"echoed": {"x": 1}}

    def test_connector_unknown_returns_404(self, client: TestClient) -> None:
        env = _envelope(
            "connector.execute.v1",
            {"adapter_id": "nope", "action": "noop", "params": {}},
        )
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 404
        assert r.json()["error"] == "connector_not_found"

    def test_connector_missing_fields_returns_400(self, client: TestClient) -> None:
        env = _envelope("connector.execute.v1", {"params": {}})
        r = client.post("/k0/command.submit", json=env)
        assert r.status_code == 400


class TestCommandSubmitMalformed:
    def test_missing_topic_returns_400(self, client: TestClient) -> None:
        r = client.post("/k0/command.submit", json={"body": {}})
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_envelope"

    def test_not_json_returns_400(self, client: TestClient) -> None:
        r = client.post(
            "/k0/command.submit",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400


class TestObsEmit:
    def test_obs_emit_persists(self, client: TestClient) -> None:
        r = client.post(
            "/k0/obs.emit",
            json={"kind": "log", "body": {"msg": "hello"}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert isinstance(body["obs_row_id"], int)
        h = client.get("/healthz").json()
        assert h["obs_rows"] == 1

    def test_obs_missing_kind_returns_400(self, client: TestClient) -> None:
        r = client.post("/k0/obs.emit", json={"body": {}})
        assert r.status_code == 400


class TestSSE:
    def test_sse_opens_with_comment_frame(self) -> None:
        # Infinite SSE streams hang any ASGI-buffering test transport (Starlette
        # TestClient, httpx ASGITransport). Test the streaming response generator
        # directly by invoking the route's StreamingResponse body iterator.
        import asyncio

        from scripts.pseudo_k0.connector_host import ConnectorHost
        from scripts.pseudo_k0.server import _build_sse_response, create_app
        from scripts.pseudo_k0.store import SQLiteK0Store

        store = SQLiteK0Store(":memory:")
        app = create_app(store, connector_host=ConnectorHost())
        response = _build_sse_response(app, "recall.events")

        assert response.media_type == "text/event-stream"

        async def first_chunk() -> bytes:
            agen = response.body_iterator
            chunk = await asyncio.wait_for(agen.__anext__(), timeout=5.0)
            await agen.aclose()
            return chunk if isinstance(chunk, (bytes, bytearray)) else chunk.encode()

        chunk = asyncio.run(first_chunk())
        assert b"pseudo-k0 sse open" in chunk
        assert b"recall.events" in chunk
