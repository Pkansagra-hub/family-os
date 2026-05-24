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


def test_family_app_static_contracts_are_manifest_aligned(client: TestClient) -> None:
    """Regression guard for family-tool SPA wiring that is easy to break."""
    html = client.get("/").text
    js = client.get("/static/app.js").text

    assert 'data-app-action="chores:create_template"' in html
    assert 'data-app-action="chores:create_chore"' not in html
    assert 'readAction("list_tasks")' in js
    assert 'readAction("list_lists")' in js
    assert 'readAction("get_visibility_policy")' in js
    assert 'readAction("list_feature_flags")' in js
    assert "SETTINGS_SOURCE_RULES" in js
    assert "SETTINGS_KID_CAPABILITIES" in js
    assert "data-setting-rule" in js
    assert "data-kid-capability" in js
    assert "data-keyword-add" in js
    assert "Privacy, kid permissions, and family feature controls" in html
    assert "_buildHomeActivityFeed" in js
    assert "_renderHomeActivity" in js
    assert "getDeviceContext" in js
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in js
    assert "device_context: getDeviceContext()" in js
    assert "Family activity will appear as people update the apps." in js
    assert "state.timelineEntries.slice(-6)" not in js
    assert "section_payloads" in js
    assert "data-ss-section" in js
    assert "renderSessionInspector" in js
    assert 'id="ss-inspector"' in html
    assert "Inspect HOT / WARM / COLD memory sections and stored data" in html


def test_configure_sets_test_mode() -> None:
    app_module.configure(test_mode=True)
    assert app_module._test_mode is True
    app_module.configure(test_mode=False)
    assert app_module._test_mode is False
