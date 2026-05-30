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


class _MessageOutput:
    _turn_session_ops: list[str] = []
    _turn_tool_calls: list[str] = []
    _turn_state_changes: dict[str, str] = {}
    _turn_fsm_states: list[str] = []
    _turn_bytes_in: int = 0
    _turn_bytes_out: int = 0
    _turn_start_ns: int = 0


class _MessageRenderer:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def send_turn_info(self, turn: int, member: str) -> None:
        self._calls.append("turn_info")

    def send_activity(self, data: dict[str, object]) -> None:
        self._calls.append("activity")

    def render_system(self, text: str) -> None:
        self._calls.append("system")


class _MessageCoord:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.renderer = _MessageRenderer(self.calls)
        self.fsm = None
        self.recorded: dict[str, object] | None = None
        self.sent: dict[str, object] | None = None
        self._output = _MessageOutput()

    async def _record_device_context(
        self, *, device: str, device_context: dict[str, object]
    ) -> None:
        self.calls.append("record")
        self.recorded = {"device": device, "device_context": device_context}

    async def send_message(self, **kwargs: object) -> None:
        self.calls.append("send")
        self.sent = dict(kwargs)

    def get_output_channel(self) -> _MessageOutput:
        return self._output


@pytest.mark.asyncio
async def test_handle_user_message_records_device_context_before_send() -> None:
    coord = _MessageCoord()
    msg = {
        "type": "message",
        "text": "what time is it",
        "member": "Alex",
        "device": "alex_phone",
        "device_context": {
            "timezone": "America/Chicago",
            "locale": "en-US",
            "observed_at_utc": "2026-05-22T02:19:00.000Z",
            "timezone_offset_minutes": 300,
            "surface": "web",
        },
    }

    await app_module._handle_user_message(coord, object(), msg)  # type: ignore[arg-type]

    assert coord.calls[:3] == ["record", "turn_info", "send"]
    assert coord.recorded == {
        "device": "alex_phone",
        "device_context": msg["device_context"],
    }
    assert coord.sent is not None
    assert coord.sent["device"] == "alex_phone"


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
    assert "navigator.geolocation.getCurrentPosition" in js
    assert "navigator.geolocation.watchPosition" in js
    assert "BROWSER_LOCATION_TARGET_ACCURACY_M = 1" in js
    assert "maximumAge: 0" in js
    assert "location_fix" in js
    assert "browser_geolocation" in js
    assert "Privacy, kid permissions, and family feature controls" in html
    assert "_buildHomeActivityFeed" in js
    assert "_renderHomeActivity" in js
    assert "Family activity will appear as people update the apps." in js
    assert "state.timelineEntries.slice(-6)" not in js
    assert "section_payloads" in js
    assert "data-ss-section" in js
    assert "renderSessionInspector" in js
    assert 'id="ss-inspector"' in html
    assert "Inspect HOT / WARM / COLD memory sections and stored data" in html


def test_chat_static_assets_support_mermaid_blocks(client: TestClient) -> None:
    """Chat markdown can upgrade Mermaid fences to rendered diagrams."""
    html = client.get("/").text
    js = client.get("/static/app.js").text
    css = client.get("/static/styles.css").text

    assert "/static/app.js?v=136" in html
    assert "/static/styles.css?v=136" in html
    assert "MERMAID_MODULE_URL" in js
    assert "mermaid@10.9.3" in js
    assert "shouldRenderMermaidBlock" in js
    assert "isLikelyMermaidSource" in js
    assert "normalizeMermaidSourceForRender" in js
    assert "normalizeMermaidFlowchartSyntax" in js
    assert "normalizeMermaidFlowchartLabels" in js
    assert "normalizeMermaidFlowchartLinkStyles" in js
    assert "mermaidRenderSourceCandidates" in js
    assert "isLikelyMermaidGraphFragment" in js
    assert "sequenceDiagram" in js
    assert "isMermaidFenceLanguage" in js
    assert "data-mermaid-status" in js
    assert "setupMermaidViewer" in js
    assert "openMermaidViewer" in js
    assert "setMermaidViewerScale" in js
    assert "mermaid-viewer__stage" in js
    assert "hydrateMessageContent(bubble)" in js
    assert ".message-mermaid" in css
    assert ".message-mermaid__canvas" in css
    assert ".mermaid-viewer" in css
    assert ".mermaid-viewer__button" in css


def test_chat_runtime_panel_has_subtle_transparency_signals(client: TestClient) -> None:
    """Runtime panel exposes active copy, tool cues, and quiet confidence."""
    js = client.get("/static/app.js").text
    css = client.get("/static/styles.css").text

    assert "_runtimeMemoryFocus" in js
    assert "Recalling ${member}'s preferences" in js
    assert "Searching for relevant routines" in js
    assert "_runtimeToolHint" in js
    assert "runtime-phase-cue" in js
    assert "Tool cue:" in js
    assert "_runtimeConfidence" in js
    assert "Path confidence" in js
    assert "runtime-confidence" in css
    assert "runtime-phase-cue" in css


def test_configure_sets_test_mode() -> None:
    app_module.configure(test_mode=True)
    assert app_module._test_mode is True
    app_module.configure(test_mode=False)
    assert app_module._test_mode is False
