"""tests.ui.web.test_app — FastAPI surface tests for the web layer.

Uses `fastapi.testclient.TestClient` (which spins up uvicorn-like internals
in-process). Covers:
    * `GET /` returns the static index.html
    * `GET /api/family` returns family profile shape (works pre-init via fallback)
    * `GET /api/status` returns system_ready=False pre-init
    * `GET /api/dead-letters` and `GET /api/ledger/stats` return {enabled: False} pre-init
    * `GET /api/session/state` returns {available: False} pre-init
    * `GET /api/session/control` returns {available: False} pre-init
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ui.web import app as app_module
from ui.web.coordinator import reset_coordinator


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Ensure pristine module state between tests."""
    app_module._coordinator = None
    app_module._initialized = False
    app_module._turn_counter = 0
    app_module._current_member = "Alex"
    app_module._current_device = "alex_phone"
    reset_coordinator()
    yield
    app_module._coordinator = None
    app_module._initialized = False
    reset_coordinator()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_module.app)


def test_index_serves_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<title>" in r.text


def test_family_endpoint_has_fallback(client: TestClient) -> None:
    """When coordinator is not initialized, /api/family falls back to fixture."""
    r = client.get("/api/family")
    assert r.status_code == 200
    body = r.json()
    assert "family_name" in body
    assert isinstance(body.get("members"), list)


def test_status_endpoint_pre_init(client: TestClient) -> None:
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json() == {"system_ready": False}


def test_dead_letters_pre_init(client: TestClient) -> None:
    r = client.get("/api/dead-letters")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_ledger_stats_pre_init(client: TestClient) -> None:
    r = client.get("/api/ledger/stats")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_session_state_pre_init(client: TestClient) -> None:
    r = client.get("/api/session/state")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False


def test_session_control_pre_init(client: TestClient) -> None:
    r = client.get("/api/session/control")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False


def test_static_assets_served(client: TestClient) -> None:
    """Static mount serves CSS + JS."""
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    r = client.get("/static/app.js")
    assert r.status_code == 200


def test_configure_sets_test_mode() -> None:
    app_module.configure(test_mode=True)
    assert app_module._test_mode is True
    app_module.configure(test_mode=False)
    assert app_module._test_mode is False
