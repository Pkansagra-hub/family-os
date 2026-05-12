"""tests.ui.web.test_websocket — End-to-end WebSocket smoke test.

Boots the FastAPI app with `test_mode=True`, opens a WebSocket connection,
and validates that:
    1. Server sends the `init` payload on connect (family, member, fsm_state).
    2. Client can send a "switch_member" message and receive ack.
    3. Client can send a "command" /status and receive a status_report.
    4. The renderer is wired so `send_fsm_state` reaches the client.

This is a smoke test only — it does NOT exercise the LLM round-trip
(test adapter is used; full conversational flows are covered by chat_repl
integration tests elsewhere).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ui.web import app as app_module
from ui.web.coordinator import reset_coordinator


@pytest.fixture(autouse=True)
def _reset_state():
    app_module._coordinator = None
    app_module._initialized = False
    app_module._turn_counter = 0
    app_module._current_member = "Alex"
    app_module._current_device = "alex_phone"
    app_module.configure(test_mode=True)
    reset_coordinator()
    yield
    coord = app_module._coordinator
    if coord is not None:
        try:
            import asyncio

            asyncio.get_event_loop().run_until_complete(coord.shutdown_system())
        except Exception:
            pass
    app_module._coordinator = None
    app_module._initialized = False
    reset_coordinator()


def test_websocket_sends_init_payload() -> None:
    """First message after connect is `init` with family + fsm_state."""
    with TestClient(app_module.app) as client:
        with client.websocket_connect("/ws") as ws:
            raw = ws.receive_text()
            msg = json.loads(raw)
            assert msg["type"] == "init"
            assert "family" in msg
            assert msg["family"].get("family_name")
            assert msg["member"] == "Alex"
            assert msg["device"] == "alex_phone"
            assert msg["turn"] == 0
            assert msg["system_ready"] is True
            assert msg["fsm_state"]  # any non-empty string


def test_websocket_switch_member_ack() -> None:
    with TestClient(app_module.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # discard init
            ws.send_text(json.dumps({"type": "switch_member", "member": "sarah"}))
            ack = json.loads(ws.receive_text())
            assert ack["type"] == "member_switched"
            assert ack["member"]  # any member name resolved


def test_websocket_status_command_returns_report() -> None:
    with TestClient(app_module.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # discard init
            ws.send_text(json.dumps({"type": "command", "cmd": "/status"}))
            report = json.loads(ws.receive_text())
            assert report["type"] == "status_report"
            assert report["data"]["system_ready"] is True
            assert "components" in report["data"]


def test_websocket_get_timeline_returns_batch() -> None:
    with TestClient(app_module.app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()  # discard init
            ws.send_text(json.dumps({"type": "get_timeline", "count": 10}))
            batch = json.loads(ws.receive_text())
            assert batch["type"] == "timeline_batch"
            assert isinstance(batch["entries"], list)
            # Should have at least the boot phase records
            assert len(batch["entries"]) > 0
