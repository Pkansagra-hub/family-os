"""FastAPI server for pseudo-K0.

Exposes the **real** K0 wire surface used by the K1 bridge client:

* ``POST /k0/command.submit`` — every bridge contract call lands here.
  The K1 ``HttpTransport.publish(topic, ...)`` wraps the payload in a
  signed K0 envelope and POSTs the envelope JSON. We deserialize the
  envelope, dispatch by ``envelope["topic"]``:

    - ``recall.request.v1`` → :meth:`SQLiteK0Store.recall` →
      ``RecallResponseV1``-shaped JSON body.
    - ``memory.write.*``, ``belief.*``, etc. → stored verbatim into the
      WAL via :meth:`SQLiteK0Store.write_envelope`; reply is an ack dict.
    - ``connector.execute.*`` → routed through :class:`ConnectorHost`
      with ``adapter_id`` + ``action`` taken from the envelope body.
    - Anything else → still persisted to the WAL; reply is ack-only.

* ``POST /k0/obs.emit`` — unsigned ``{"kind", "body"}`` observations.
* ``GET  /k0/sse/{topic}`` — server-sent-events keep-alive stream;
  emits heartbeat comments so K1's SSE client stays connected.
* ``GET  /healthz`` — 200 OK liveness probe.

Signatures on incoming envelopes are **not verified** in dev mode —
the pseudo-K0 server is intended for local development of K1 features
that depend on a live recall path. Production K0 verifies signatures
through ``bridge.core.signing``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from scripts.pseudo_k0.connector_host import ConnectorHost, ConnectorNotFound
from scripts.pseudo_k0.models import (
    K0Envelope,
    ObsPayload,
    RecallRequestBody,
)
from scripts.pseudo_k0.store import SQLiteK0Store

logger = logging.getLogger("pseudo_k0.server")


def create_app(
    store: SQLiteK0Store,
    *,
    connector_host: ConnectorHost | None = None,
    sse_heartbeat_s: float = 15.0,
) -> FastAPI:
    """Build a FastAPI app bound to ``store`` and ``connector_host``.

    The app holds no module-level state; ``store`` and ``connector_host``
    are closed over via ``app.state`` so tests can spin multiple
    independent instances against in-memory databases.
    """
    app = FastAPI(title="pseudo-K0", version="0.1.0")
    app.state.store = store
    app.state.connector_host = connector_host or ConnectorHost()
    app.state.sse_heartbeat_s = sse_heartbeat_s

    @app.get("/healthz")
    async def healthz() -> Dict[str, Any]:
        wal_n, obs_n = app.state.store.counts()
        return {"ok": True, "wal_rows": wal_n, "obs_rows": obs_n}

    @app.post("/k0/command.submit")
    async def command_submit(request: Request) -> JSONResponse:
        return await _handle_command_submit(app, request)

    @app.post("/k0/obs.emit")
    async def obs_emit(request: Request) -> JSONResponse:
        return await _handle_obs_emit(app, request)

    @app.get("/k0/sse/{topic}")
    async def sse(topic: str) -> StreamingResponse:
        return _build_sse_response(app, topic)

    return app


# ---------------------------------------------------------------------------
# /k0/command.submit
# ---------------------------------------------------------------------------


async def _handle_command_submit(app: FastAPI, request: Request) -> JSONResponse:
    try:
        raw = await request.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("command.submit: malformed JSON: %s", exc)
        return JSONResponse({"error": "malformed_json"}, status_code=400)

    try:
        envelope = K0Envelope.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("command.submit: envelope validation failed: %s", exc)
        return JSONResponse({"error": "invalid_envelope", "detail": str(exc)}, status_code=400)

    topic = envelope.topic
    body = _extract_body(raw)
    trace_id = raw.get("cognitive_trace_id") if isinstance(raw, dict) else None

    store: SQLiteK0Store = app.state.store
    host: ConnectorHost = app.state.connector_host

    if topic == "recall.request.v1":
        return await _dispatch_recall(store, body, trace_id)

    if topic.startswith("connector.execute"):
        return await _dispatch_connector(host, body, trace_id)

    # All other topics: persist the envelope verbatim and ack.
    row_id = store.write_envelope(envelope)
    return JSONResponse(
        {"ok": True, "topic": topic, "wal_row_id": row_id, "trace_id": trace_id},
        status_code=200,
    )


def _extract_body(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    body = raw.get("body")
    return body if isinstance(body, dict) else {}


async def _dispatch_recall(
    store: SQLiteK0Store,
    body: Dict[str, Any],
    trace_id: str | None,
) -> JSONResponse:
    try:
        req = RecallRequestBody.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("recall.request.v1: body validation failed: %s", exc)
        return JSONResponse({"error": "invalid_recall_body", "detail": str(exc)}, status_code=400)
    # Carry the envelope-level trace_id through if the body did not set one.
    if not req.trace_id and trace_id:
        req = req.model_copy(update={"trace_id": trace_id})
    response = store.recall(req)
    # Emit as a dict matching the RecallResponseV1 contract shape exactly.
    return JSONResponse(response.model_dump(mode="json", exclude_none=True))


async def _dispatch_connector(
    host: ConnectorHost,
    body: Dict[str, Any],
    trace_id: str | None,
) -> JSONResponse:
    adapter_id = body.get("adapter_id")
    action = body.get("action")
    params = body.get("params") or {}
    if not isinstance(adapter_id, str) or not isinstance(action, str):
        return JSONResponse(
            {"error": "invalid_connector_call", "detail": "adapter_id/action required"},
            status_code=400,
        )
    try:
        result = await host.dispatch(adapter_id, action, params if isinstance(params, dict) else {})
    except ConnectorNotFound as exc:
        return JSONResponse(
            {"error": "connector_not_found", "detail": str(exc), "trace_id": trace_id},
            status_code=404,
        )
    return JSONResponse({"ok": True, "result": result, "trace_id": trace_id})


# ---------------------------------------------------------------------------
# /k0/obs.emit
# ---------------------------------------------------------------------------


async def _handle_obs_emit(app: FastAPI, request: Request) -> JSONResponse:
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "malformed_json"}, status_code=400)
    try:
        payload = ObsPayload.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": "invalid_obs", "detail": str(exc)}, status_code=400)
    row_id = app.state.store.write_obs(payload.kind, payload.body)
    return JSONResponse({"ok": True, "obs_row_id": row_id})


# ---------------------------------------------------------------------------
# /k0/sse/{topic}
# ---------------------------------------------------------------------------


def _build_sse_response(app: FastAPI, topic: str) -> StreamingResponse:
    heartbeat_s: float = app.state.sse_heartbeat_s

    async def _stream() -> Any:
        # Initial comment frame so the client knows the stream is open.
        yield f": pseudo-k0 sse open topic={topic}\n\n".encode()
        try:
            while True:
                await asyncio.sleep(heartbeat_s)
                yield b": heartbeat\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
