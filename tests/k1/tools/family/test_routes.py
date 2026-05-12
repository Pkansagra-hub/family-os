"""Tests for the per-adapter REST router factory (§E15.0.9)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from k1.tools.family.events import EventEmitter
from k1.tools.family.idem import IdempotencyStore
from k1.tools.family.policy import default_policy
from k1.tools.family.routes import build_router
from k1.tools.family.storage import K1FamilyStore
from tests.k1.tools.family._stubs import DemoToolService, RecordingSsePublisher


@pytest.fixture()
def client(tmp_path: Path):
    store = K1FamilyStore(str(tmp_path / "k.db"))
    emitter = EventEmitter(RecordingSsePublisher())
    idem = IdempotencyStore(store.conn)
    svc = DemoToolService(store.conn, emitter, default_policy(), idem)
    app = FastAPI()
    app.include_router(build_router(svc))
    try:
        yield TestClient(app)
    finally:
        store.close()


def test_manifest_endpoint(client: TestClient) -> None:
    resp = client.get("/k1/tools/demo/manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["adapter_id"] == "demo"


def test_llm_specs_endpoint(client: TestClient) -> None:
    resp = client.get("/k1/tools/demo/llm_specs")
    assert resp.status_code == 200
    body = resp.json()
    assert any(s["name"] == "demo.echo" for s in body)


def test_post_write_action(client: TestClient) -> None:
    resp = client.post(
        "/k1/tools/demo/record_write",
        json={"payload": "alpha"},
        headers={
            "X-Actor-Member-Id": "u1",
            "X-Actor-Role": "parent",
            "X-Space-Id": "h1",
            "X-Trace-Id": "tr-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["id"] == "row-alpha"


def test_role_denied_returns_403(client: TestClient) -> None:
    resp = client.post(
        "/k1/tools/demo/record_write",
        json={"payload": "alpha"},
        headers={"X-Actor-Member-Id": "u1", "X-Actor-Role": "guest"},
    )
    assert resp.status_code == 403


def test_read_action_via_get(client: TestClient) -> None:
    resp = client.get(
        "/k1/tools/demo/adults_only",
        headers={"X-Actor-Member-Id": "u1", "X-Actor-Role": "parent"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
