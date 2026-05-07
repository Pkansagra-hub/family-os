"""
poc.k1_poc.demo.web.app -- FastAPI + WebSocket server for the K1 demo UI.

Bridges the K1 coordinator/kernel with a browser-based chat UI.
WebSocket handles bidirectional real-time communication:
  - Client sends user messages, member switches, commands
  - Server streams responses, timeline events, FSM state, affect updates

Usage::

    python -m poc.k1_poc.demo.web.app [--port 8765] [--test-mode]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from poc.k1_poc.demo.web.renderer import WebSocketRenderer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="FamilyOS K1 Concierge Demo")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared state -- initialized on first WebSocket connection
_coordinator: Any = None
_renderer: WebSocketRenderer = WebSocketRenderer()
_initialized: bool = False
_init_lock = asyncio.Lock()
_test_mode: bool = False

# Per-connection turn tracking
_turn_counter: int = 0
_current_member: str = "Alex"
_current_device: str = "alex_phone"


# ---------------------------------------------------------------------------
# Coordinator lifecycle
# ---------------------------------------------------------------------------


async def _ensure_coordinator() -> Any:
    """Lazily initialize the K1 coordinator on first connection."""
    global _coordinator, _initialized

    async with _init_lock:
        if _initialized and _coordinator is not None:
            return _coordinator

        from poc.k1_poc.demo.coordinator import (
            get_k1_demo_coordinator,
            reset_coordinator,
        )

        reset_coordinator()
        coord = get_k1_demo_coordinator(test_mode=_test_mode)

        # Initialize the kernel
        success = await coord.initialize_system()
        if not success:
            raise RuntimeError("K1 coordinator initialization failed")

        # Replace the output channel renderer with our WebSocket renderer
        if coord.output_channel:
            coord.output_channel._renderer = _renderer
            # Disable the console spinner -- no terminal in web mode
            coord.output_channel._enable_spinner = False

        # Wire additional bus subscriptions for real-time web events
        # (FSM state changes, affect updates, tool events)
        _wire_web_timeline_hooks(coord)

        _coordinator = coord
        _initialized = True

        logger.info("WEB: K1 coordinator initialized (test_mode=%s)", _test_mode)
        return _coordinator


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        str(STATIC_DIR / "index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/family")
async def get_family() -> dict:
    """Return the Smith family profile for the member switcher."""
    from poc.k1_poc.demo.smith_family import SMITH_FAMILY_PROFILE

    return SMITH_FAMILY_PROFILE


@app.get("/api/status")
async def get_status() -> dict:
    """Return system status."""
    if _coordinator is None:
        return {"system_ready": False}
    return _coordinator.get_status_report()


# M2 E2.5.5: Dead-letter observability endpoint
@app.get("/api/dead-letters")
async def get_dead_letters() -> dict:
    """Return dead-letter consumer summary and recent events."""
    if _coordinator is None or _coordinator.dead_letter_consumer is None:
        return {"enabled": False}
    consumer = _coordinator.dead_letter_consumer
    snapshot = consumer.snapshot()
    recent = [e.to_dict() for e in consumer.events[-10:]]
    return {
        "enabled": True,
        "total": snapshot.get("total_dead_letters", 0),
        "by_reason": snapshot.get("counts_by_reason", {}),
        "by_state": snapshot.get("counts_by_state", {}),
        "by_topic": snapshot.get("counts_by_topic", {}),
        "recent": recent,
    }


# M2 E2.5.5: Ledger stats endpoint
@app.get("/api/ledger/stats")
async def get_ledger_stats() -> dict:
    """Return ledger operational statistics."""
    if _coordinator is None or _coordinator.ledger_store is None:
        return {"enabled": False}
    store = _coordinator.ledger_store
    total = store.count()
    dead_letter_count = (
        len(store.read_by_type(_coordinator.ledger.session_id, "conversation.dead_lettered"))
        if _coordinator.ledger
        else 0
    )
    return {
        "enabled": True,
        "total_events": total,
        "dead_letter_events": dead_letter_count,
        "store_type": type(store).__name__,
    }


# Session state snapshot -- all tiers
@app.get("/api/session/state")
async def get_session_state() -> dict:
    """Return full session state snapshot with all tiers and section data."""
    if _coordinator is None or _coordinator.session_state is None:
        logger.warning(
            "API /api/session/state: coordinator=%s session_state=%s",
            _coordinator is not None,
            getattr(_coordinator, "session_state", "N/A") is not None if _coordinator else False,
        )
        return {"available": False, "reason": "coordinator not ready"}
    try:
        ss = _coordinator.session_state

        # Sync size tracker from actual section sizes (sections are often
        # mutated directly, bypassing manager.mutate() which would update the
        # tracker).  This ensures the snapshot reflects real sizes.
        if hasattr(ss, "_sync_size_tracker"):
            ss._sync_size_tracker()

        snapshot = ss.get_snapshot()
        result: dict = snapshot.to_dict()
        result["available"] = True

        # Enrich with per-section metadata (includes section-specific fields)
        section_details: dict = {}
        for section_name in list(result.get("sections", {})):
            try:
                section = ss.get_section(section_name)
                if hasattr(section, "get_metadata"):
                    meta = section.get_metadata()
                    # Sanitize enum values
                    section_details[section_name] = {
                        k: (v.value if hasattr(v, "value") else v) for k, v in meta.items()
                    }
            except Exception as e:
                section_details[section_name] = {"error": str(e)}
        result["section_details"] = section_details

        # Local cold stats
        try:
            cold = ss.get_local_cold()
            if hasattr(cold, "count"):
                result["local_cold_count"] = cold.count()
            elif hasattr(cold, "_archive") and hasattr(cold._archive, "count"):
                result["local_cold_count"] = cold._archive.count()
            else:
                result["local_cold_count"] = 0
        except Exception:
            result["local_cold_count"] = 0

        # Validate JSON-serializable before returning
        json.dumps(result)
        logger.info("API /api/session/state: OK sections=%d", len(result.get("sections", {})))
        return result
    except Exception as exc:
        logger.error("API /api/session/state error: %s", exc, exc_info=True)
        return {"available": False, "error": str(exc)}


# M4 E4.5.2: Control section diagnostics endpoint
@app.get("/api/session/control")
async def get_session_control() -> dict:
    """Return control section snapshot with FSM overlay."""
    if _coordinator is None or _coordinator.session_state is None:
        return {"available": False}
    try:
        from poc.k1_poc.actors.shared import safe_get_section

        control = safe_get_section(_coordinator.session_state, "control")
        if control is None:
            return {"available": False, "reason": "control section not found"}
        result: dict = {"available": True}
        if hasattr(control, "to_dict"):
            result["data"] = control.to_dict()
        if hasattr(control, "fsm_overlay"):
            overlay = control.fsm_overlay
            result["fsm_overlay"] = overlay if overlay is not None else None
            result["overlay_bound"] = overlay is not None
        if hasattr(control, "get_metadata"):
            result["metadata"] = control.get_metadata()
        return result
    except Exception as exc:
        return {"available": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    global _turn_counter, _current_member, _current_device

    await ws.accept()
    await _renderer.add_connection(ws)

    try:
        # Initialize coordinator (lazy)
        coord = await _ensure_coordinator()

        # Send initial state to client
        from poc.k1_poc.demo.smith_family import SMITH_FAMILY_PROFILE

        await ws.send_text(
            json.dumps(
                {
                    "type": "init",
                    "family": SMITH_FAMILY_PROFILE,
                    "member": _current_member,
                    "device": _current_device,
                    "turn": _turn_counter,
                    "system_ready": coord.system_ready,
                    "fsm_state": coord.fsm.state.name if coord.fsm else "UNKNOWN",
                }
            )
        )

        # Message loop
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "message":
                await _handle_user_message(coord, ws, msg)
            elif msg_type == "switch_member":
                _handle_switch_member(msg)
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "member_switched",
                            "member": _current_member,
                            "device": _current_device,
                        }
                    )
                )
            elif msg_type == "command":
                await _handle_command(coord, ws, msg)
            elif msg_type == "get_timeline":
                await _send_timeline(coord, ws, msg)

    except WebSocketDisconnect:
        logger.info("WEB: Client disconnected")
    except Exception as exc:
        logger.error("WEB: WebSocket error: %s", exc, exc_info=True)
    finally:
        await _renderer.remove_connection(ws)


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------


async def _handle_user_message(coord: Any, ws: WebSocket, msg: dict) -> None:
    """Process a user message: publish to bus and wait for response."""
    global _turn_counter

    text = msg.get("text", "").strip()
    if not text:
        return

    member = msg.get("member", _current_member)
    device = msg.get("device", _current_device)

    _turn_counter += 1
    turn = _turn_counter

    # Inform client of turn start
    _renderer.send_turn_info(turn, member)

    # Reset dispatchers
    try:
        coord.front_dispatcher.reset()
        coord.back_dispatcher.reset()
    except Exception:
        pass

    # IoT proactive stubs disabled -- scripted events removed
    # iot = coord.get_iot_stubs()
    # if iot.has_event(turn):
    #     _renderer.render_system(f"IoT event at turn {turn}")
    #     iot.check(turn)
    #     await asyncio.sleep(0.3)

    # Update output channel
    output = coord.get_output_channel()
    output.set_member(member)
    output.start_turn(turn)

    # Build and publish user input envelope
    from poc.k1_poc.bus.builders import build_user_input

    payload = {
        "text": text,
        "member": member,
        "device": device,
        "turn": turn,
    }
    envelope = build_user_input(payload=payload)
    bus = coord.get_bus()
    bus.publish(envelope)

    # Wait for response
    try:
        await output.wait_for_response(timeout=180.0)
    except Exception as exc:
        logger.error("WEB: Response wait failed: %s", exc)
        _renderer.render_system(f"Response error: {exc}")
        return

    # Send system activity data
    _renderer.send_activity(
        {
            "turn": turn,
            "session_ops": list(output._turn_session_ops),
            "tool_calls": list(output._turn_tool_calls),
            "state_changes": dict(output._turn_state_changes),
            "fsm_states": list(output._turn_fsm_states),
            "bytes_in": output._turn_bytes_in,
            "bytes_out": output._turn_bytes_out,
            "latency_ms": (
                int((time.monotonic_ns() - output._turn_start_ns) / 1_000_000)
                if output._turn_start_ns
                else 0
            ),
        }
    )

    # Send current FSM state
    if coord.fsm:
        await ws.send_text(
            json.dumps(
                {
                    "type": "fsm_current",
                    "state": coord.fsm.state.name,
                }
            )
        )


def _handle_switch_member(msg: dict) -> None:
    """Switch the active family member."""
    global _current_member, _current_device

    from poc.k1_poc.demo.smith_family import (
        DEVICE_REGISTRY,
        MEMBER_TO_DEFAULT_DEVICE,
        resolve_member,
    )

    name = msg.get("member", "").lower()
    device_id = MEMBER_TO_DEFAULT_DEVICE.get(name)
    if device_id and device_id in DEVICE_REGISTRY:
        _current_device = device_id
        _current_member = resolve_member(device_id)


async def _handle_command(coord: Any, ws: WebSocket, msg: dict) -> None:
    """Handle slash commands from the UI."""
    cmd = msg.get("cmd", "").strip().lower()

    if cmd == "/status":
        report = coord.get_status_report()
        await ws.send_text(
            json.dumps(
                {
                    "type": "status_report",
                    "data": report,
                }
            )
        )
    elif cmd == "/timeline":
        await _send_timeline(coord, ws, msg)


async def _send_timeline(coord: Any, ws: WebSocket, msg: dict) -> None:
    """Send timeline entries to the client."""
    count = msg.get("count", 50)
    entries = coord.timeline[-count:]
    await ws.send_text(
        json.dumps(
            {
                "type": "timeline_batch",
                "entries": [e.to_dict() for e in entries],
            }
        )
    )


# ---------------------------------------------------------------------------
# Enhanced output channel wiring for web
# ---------------------------------------------------------------------------


def _wire_web_timeline_hooks(coord: Any) -> None:
    """Wire additional bus subscriptions for web-specific events.

    The base output_channel already handles rendering via IRenderer.
    This adds hooks to forward timeline, FSM, and affect events in
    real-time to the WebSocket renderer.
    """
    from k1.bus.envelope import Envelope

    bus = coord.get_bus()
    from poc.k1_poc.bus.topics import (
        TOPIC_AFFECT_UPDATE,
        TOPIC_STATE_UPDATED,
        TOPIC_TOOL_COMPLETED,
        TOPIC_TOOL_STARTED,
    )

    def _on_fsm_for_web(envelope: Envelope) -> None:
        try:
            p = json.loads(envelope.payload) if envelope.payload else {}
            _renderer.send_fsm_state(
                p.get("from_state", "?"),
                p.get("to_state", "?"),
                p.get("trigger", "?"),
            )
        except Exception:
            pass

    def _on_affect_for_web(envelope: Envelope) -> None:
        try:
            p = json.loads(envelope.payload) if envelope.payload else {}
            _renderer.send_affect_update(
                p.get("emotion", "neutral"),
                p.get("valence", 0.0),
            )
        except Exception:
            pass

    def _on_tool_for_web(envelope: Envelope) -> None:
        try:
            p = json.loads(envelope.payload) if envelope.payload else {}
            _renderer.send_tool_event(
                tool_name=p.get("tool_name", "?"),
                actor=p.get("actor", "?"),
                phase="started" if "started" in envelope.topic else "completed",
                duration_ms=p.get("duration_ms", 0),
                success=p.get("success", True),
                args_summary=p.get("args_summary", ""),
                result_summary=p.get("result_summary", ""),
            )
        except Exception:
            pass

    bus.subscribe(TOPIC_STATE_UPDATED, _on_fsm_for_web)
    bus.subscribe(TOPIC_AFFECT_UPDATE, _on_affect_for_web)
    bus.subscribe(TOPIC_TOOL_STARTED, _on_tool_for_web)
    bus.subscribe(TOPIC_TOOL_COMPLETED, _on_tool_for_web)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="K1 Concierge Web UI")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--test-mode", action="store_true", help="Use test adapter")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    global _test_mode
    _test_mode = args.test_mode

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    import uvicorn

    print("\n  FamilyOS K1 Concierge -- Web UI")
    print(f"  Open http://{args.host}:{args.port} in your browser\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
