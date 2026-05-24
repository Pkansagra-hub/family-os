"""ui.web.app — FastAPI + WebSocket server for the K1 web UI.

Bridges the production K1 kernel (via `UiCoordinator`) to a browser-based
chat UI. WebSocket carries bidirectional traffic:

  Client → Server: user messages, member switches, slash commands
  Server → Client: streamed responses, FSM badges, affect, timeline, tools

Run with::

    python -m ui.web [--port 8765] [--host 127.0.0.1] [--test-mode]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ui.web.coordinator import UiCoordinator, get_web_coordinator, reset_coordinator
from ui.web.routes.family_tools import build_family_tools_api

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="FamilyOS K1 Concierge")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Family-tool adapter discovery API (lazy: coordinator resolved per-request).
app.include_router(build_family_tools_api(lambda: _coordinator))

# Process-wide shared state (lazy-init on first WebSocket connection)
_coordinator: UiCoordinator | None = None
_initialized: bool = False
_init_lock = asyncio.Lock()
_test_mode: bool = False
_model_mode: str | None = None

# Per-process turn / active member tracking (single-tenant demo)
_turn_counter: int = 0
_current_member: str = "Alex"
_current_device: str = "alex_phone"


def configure(*, test_mode: bool, model_mode: str | None = None) -> None:
    """Configure module globals before the first WebSocket connection.

    Called by `ui.web.__main__` and by tests.
    """
    global _test_mode, _model_mode
    _test_mode = test_mode
    _model_mode = model_mode


# ---------------------------------------------------------------------------
# Coordinator lifecycle
# ---------------------------------------------------------------------------


async def _ensure_coordinator() -> UiCoordinator:
    """Lazily initialize the UiCoordinator on first connection."""
    global _coordinator, _initialized

    async with _init_lock:
        if _initialized and _coordinator is not None:
            return _coordinator

        reset_coordinator()  # Drop any stale singleton from a prior worker
        coord = get_web_coordinator(test_mode=_test_mode, model_mode=_model_mode)

        ok = await coord.initialize_system()
        if not ok:
            raise RuntimeError("UiCoordinator initialization failed")

        _coordinator = coord
        _initialized = True
        logger.info("WEB: UiCoordinator initialized (test_mode=%s)", _test_mode)
        _mount_family_tool_routers(coord)
        return _coordinator


def _mount_family_tool_routers(coord: UiCoordinator) -> None:
    """Attach per-adapter REST routers from the kernel's FamilyToolsBundle.

    The kernel publishes a ``FamilyToolsBundle`` at S8 of ``_startup_tier1``
    when ``KernelConfig.enable_family_tools`` is True. Each registered
    ``BaseToolService`` is exposed as ``/k1/tools/<adapter>/...`` via
    :func:`k1.tools.family.build_router`. The mount is idempotent within a
    process — duplicate FastAPI prefixes are silently skipped.
    """
    runtime = getattr(coord, "_runtime", None)
    service = getattr(runtime, "_service", None) if runtime is not None else None
    bundle = getattr(service, "family_tools", None) if service is not None else None
    if bundle is None:
        return

    from k1.tools.family import build_router

    existing = {getattr(r, "path", None) for r in app.routes}
    mounted: list[str] = []
    for svc in bundle.tool_registry.services.values():
        prefix = f"/k1/tools/{svc.DEFINITION.adapter_id}"
        if any(p and p.startswith(prefix) for p in existing):
            continue
        app.include_router(build_router(svc))
        mounted.append(prefix)
    if mounted:
        logger.info("WEB: mounted family-tool routers: %s", mounted)


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Gracefully tear the coordinator down with uvicorn."""
    global _coordinator, _initialized
    if _coordinator is not None:
        try:
            await _coordinator.shutdown_system()
        except Exception:
            logger.error("WEB: coordinator shutdown failed", exc_info=True)
        finally:
            _coordinator = None
            _initialized = False
            reset_coordinator()


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
    """Family profile (for the member switcher)."""
    if _coordinator is None:
        # Fall back to raw fixture so the page can render before the kernel
        # is initialized (avoids a chicken-and-egg with WebSocket lazy init).
        from poc.k1_poc.demo.smith_family import SMITH_FAMILY_PROFILE

        return dict(SMITH_FAMILY_PROFILE)
    return _coordinator.family_profile


@app.get("/api/status")
async def get_status() -> dict:
    if _coordinator is None:
        return {"system_ready": False}
    return _coordinator.get_status_report()


@app.get("/api/dead-letters")
async def get_dead_letters() -> dict:
    """Dead-letter consumer summary and recent events."""
    if _coordinator is None or _coordinator.dead_letter_consumer is None:
        return {"enabled": False}
    consumer = _coordinator.dead_letter_consumer
    try:
        snapshot = consumer.snapshot()
    except Exception:
        snapshot = {}
    recent_events = getattr(consumer, "events", []) or []
    recent = [e.to_dict() for e in recent_events[-10:] if hasattr(e, "to_dict")]
    return {
        "enabled": True,
        "total": snapshot.get("total_dead_letters", 0),
        "by_reason": snapshot.get("counts_by_reason", {}),
        "by_state": snapshot.get("counts_by_state", {}),
        "by_topic": snapshot.get("counts_by_topic", {}),
        "recent": recent,
    }


@app.get("/api/ledger/stats")
async def get_ledger_stats() -> dict:
    if _coordinator is None or _coordinator.ledger_store is None:
        return {"enabled": False}
    store = _coordinator.ledger_store
    try:
        total = store.count()
    except Exception:
        total = -1
    dead_letter_count = 0
    if _coordinator.ledger is not None:
        try:
            session_id = getattr(_coordinator.ledger, "session_id", None)
            if session_id is not None:
                dead_letter_count = len(
                    store.read_by_type(session_id, "conversation.dead_lettered")
                )
        except Exception:
            dead_letter_count = -1
    return {
        "enabled": True,
        "total_events": total,
        "dead_letter_events": dead_letter_count,
        "store_type": type(store).__name__,
    }


@app.get("/api/session/state")
async def get_session_state() -> dict:
    """Full session state snapshot (all tiers + section metadata)."""
    if _coordinator is None or _coordinator.session_state is None:
        return {"available": False, "reason": "coordinator not ready"}
    try:
        ss = _coordinator.session_state
        if hasattr(ss, "_sync_size_tracker"):
            ss._sync_size_tracker()
        snapshot = ss.get_snapshot()
        result: dict = snapshot.to_dict()
        result["available"] = True

        section_details: dict = {}
        section_payloads: dict = {}
        for section_name in list(result.get("sections", {})):
            try:
                section = ss.get_section(section_name)
                if hasattr(section, "get_metadata"):
                    meta = section.get_metadata()
                    section_details[section_name] = {
                        k: (v.value if hasattr(v, "value") else v) for k, v in meta.items()
                    }
                section_payloads[section_name] = _serialize_session_section(section)
            except Exception as e:
                section_details[section_name] = {"error": str(e)}
                section_payloads[section_name] = {"error": str(e), "data": None}
        result["section_details"] = section_details
        result["section_payloads"] = section_payloads

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

        json.dumps(result)  # validate JSON-serializable
        return result
    except Exception as exc:
        logger.error("API /api/session/state failed: %s", exc, exc_info=True)
        return {"available": False, "error": str(exc)}


_SECTION_ATTR_SKIP = {
    "_cached_bytes",
    "_cache_valid",
    "_cache",
    "_lock",
    "_mutex",
    "_logger",
}


def _serialize_session_section(section: Any) -> dict[str, Any]:
    """Return safe, JSON-ready section content for the web inspector."""
    serializer = "attributes"
    try:
        if hasattr(section, "to_dict") and callable(section.to_dict):
            serializer = "to_dict"
            data = section.to_dict()
        else:
            data = _section_object_attrs(section)
        return {
            "serializer": serializer,
            "data": _safe_json_value(data),
        }
    except Exception as exc:
        return {
            "serializer": serializer,
            "error": str(exc),
            "data": None,
        }


def _section_object_attrs(section: Any) -> dict[str, Any]:
    raw = vars(section) if hasattr(section, "__dict__") else {}
    data: dict[str, Any] = {}
    for name, value in raw.items():
        if not _include_section_attr(name, value):
            continue
        key = name[1:] if name.startswith("_") else name
        data[key] = value
    return data


def _include_section_attr(name: str, value: Any) -> bool:
    if name in _SECTION_ATTR_SKIP or name.startswith("__"):
        return False
    lowered = name.lower()
    if "cache" in lowered or "lock" in lowered or "callback" in lowered:
        return False
    if callable(value):
        return False
    return True


def _safe_json_value(value: Any, *, depth: int = 0, seen: set[int] | None = None) -> Any:
    if seen is None:
        seen = set()
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"_type": "bytes", "size_bytes": len(value)}
    if depth >= 8:
        return repr(value)

    obj_id = id(value)
    if obj_id in seen:
        return "<cycle>"
    seen.add(obj_id)

    if isinstance(value, dict):
        return {
            str(k): _safe_json_value(v, depth=depth + 1, seen=seen)
            for k, v in list(value.items())[:200]
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        result = [_safe_json_value(v, depth=depth + 1, seen=seen) for v in items[:200]]
        if len(items) > 200:
            result.append({"_truncated": len(items) - 200})
        return result
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return _safe_json_value(value.model_dump(mode="json"), depth=depth + 1, seen=seen)
        except Exception:
            pass
    if is_dataclass(value):
        return {
            field.name: _safe_json_value(getattr(value, field.name), depth=depth + 1, seen=seen)
            for field in fields(value)
        }
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _safe_json_value(value.to_dict(), depth=depth + 1, seen=seen)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {
            key.lstrip("_"): _safe_json_value(val, depth=depth + 1, seen=seen)
            for key, val in vars(value).items()
            if _include_section_attr(key, val)
        }
    return repr(value)


@app.get("/api/session/control")
async def get_session_control() -> dict:
    """Control section snapshot with FSM overlay."""
    if _coordinator is None or _coordinator.session_state is None:
        return {"available": False}
    try:
        from k1.concierge.actors.shared import safe_get_section

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

    try:
        coord = await _ensure_coordinator()
    except Exception as exc:
        logger.error("WEB: coordinator init failed for new connection: %s", exc, exc_info=True)
        await ws.close(code=1011)
        return

    await coord.renderer.add_connection(ws)

    try:
        await ws.send_text(
            json.dumps(
                {
                    "type": "init",
                    "family": coord.family_profile,
                    "member": _current_member,
                    "device": _current_device,
                    "turn": _turn_counter,
                    "system_ready": coord.system_ready,
                    "fsm_state": coord.fsm.state.name if coord.fsm else "UNKNOWN",
                }
            )
        )

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
            elif msg_type == "hil_response":
                await _handle_hil_response(coord, ws, msg)
            else:
                logger.debug("WEB: unknown message type=%r", msg_type)

    except WebSocketDisconnect:
        logger.info("WEB: Client disconnected")
    except Exception as exc:
        logger.error("WEB: WebSocket error: %s", exc, exc_info=True)
    finally:
        await coord.renderer.remove_connection(ws)


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------


async def _handle_user_message(coord: UiCoordinator, ws: WebSocket, msg: dict) -> None:
    """Process a user message: publish to bus, await response, send activity."""
    global _turn_counter

    text = (msg.get("text") or "").strip()
    if not text:
        return

    member = msg.get("member", _current_member)
    device = msg.get("device", _current_device)
    device_context = msg.get("device_context")
    if not isinstance(device_context, dict):
        device_context = None

    _turn_counter += 1
    turn = _turn_counter

    coord.renderer.send_turn_info(turn, member)

    try:
        await coord.send_message(
            text=text,
            member=member,
            device=device,
            device_context=device_context,
            turn=turn,
            timeout_s=180.0,
        )
    except Exception as exc:
        logger.error("WEB: send_message failed: %s", exc, exc_info=True)
        coord.renderer.render_system(f"Response error: {exc}")
        return

    output = coord.get_output_channel()
    coord.renderer.send_activity(
        {
            "turn": turn,
            "session_ops": list(getattr(output, "_turn_session_ops", []) or []),
            "tool_calls": list(getattr(output, "_turn_tool_calls", []) or []),
            "state_changes": dict(getattr(output, "_turn_state_changes", {}) or {}),
            "fsm_states": list(getattr(output, "_turn_fsm_states", []) or []),
            "bytes_in": getattr(output, "_turn_bytes_in", 0),
            "bytes_out": getattr(output, "_turn_bytes_out", 0),
            "latency_ms": (
                int((time.monotonic_ns() - output._turn_start_ns) / 1_000_000)
                if getattr(output, "_turn_start_ns", 0)
                else 0
            ),
        }
    )

    if coord.fsm is not None:
        try:
            await ws.send_text(
                json.dumps(
                    {
                        "type": "fsm_current",
                        "state": coord.fsm.state.name,
                    }
                )
            )
        except RuntimeError as exc:
            # Browser disconnected before response arrived (e.g. long LLM call).
            # The response was already published to the bus; log and move on.
            logger.warning("WEB: fsm_current send skipped — WebSocket closed: %s", exc)


async def _handle_hil_response(coord: UiCoordinator, ws: WebSocket, msg: dict) -> None:
    """Publish a HIL response from the browser back onto the bus."""
    import time as _time

    from k1.hil.topics import TOPIC_HIL_RESPONSE as _TOPIC_HIL_RESPONSE

    hil_request_id = msg.get("hil_request_id", "")
    kind = msg.get("kind", "")
    payload = dict(msg.get("payload", {}))

    envelope_payload = {
        "hil_request_id": hil_request_id,
        "kind": kind,
        "responded_at_ms": int(_time.time() * 1000),
        "payload": payload,
        "timed_out": False,
    }

    try:
        from k1.bus import Envelope

        coord.get_bus().publish(
            Envelope(topic=_TOPIC_HIL_RESPONSE, payload=json.dumps(envelope_payload).encode())
        )
        logger.info("WEB: hil_response published hil_request_id=%s kind=%s", hil_request_id, kind)
    except Exception as exc:
        logger.error("WEB: hil_response publish failed: %s", exc, exc_info=True)


def _handle_switch_member(msg: dict) -> None:
    """Switch the active family member (single-tenant demo)."""
    global _current_member, _current_device

    from poc.k1_poc.demo.smith_family import (
        DEVICE_REGISTRY,
        MEMBER_TO_DEFAULT_DEVICE,
        resolve_member,
    )

    name = (msg.get("member") or "").lower()
    device_id = MEMBER_TO_DEFAULT_DEVICE.get(name)
    if device_id and device_id in DEVICE_REGISTRY:
        _current_device = device_id
        _current_member = resolve_member(device_id)


async def _handle_command(coord: UiCoordinator, ws: WebSocket, msg: dict) -> None:
    """Handle slash commands."""
    cmd = (msg.get("cmd") or "").strip().lower()

    if cmd == "/status":
        await ws.send_text(json.dumps({"type": "status_report", "data": coord.get_status_report()}))
    elif cmd == "/timeline":
        await _send_timeline(coord, ws, msg)


async def _send_timeline(coord: UiCoordinator, ws: WebSocket, msg: dict) -> None:
    """Send timeline entries (most recent N) to the client."""
    count = int(msg.get("count", 50) or 50)
    entries = coord.timeline[-count:]
    await ws.send_text(
        json.dumps(
            {
                "type": "timeline_batch",
                "entries": [e.to_dict() for e in entries],
            }
        )
    )
