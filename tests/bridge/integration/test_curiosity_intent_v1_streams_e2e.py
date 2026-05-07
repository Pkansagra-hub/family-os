"""End-to-end SSE flow test (MS-3d Epic 3d.4 EXIT criterion).

Wires K0 emitter \u2192 real chunked SSE over a live ``uvicorn`` server \u2192
K1 ``SSEClient`` \u2192 generated ``CuriosityIntentV1Subscriber`` \u2192 user
handler. Asserts:

* Live emit traverses the full real-transport path (real TCP + real
  chunked HTTP). ``httpx.ASGITransport`` cannot be used here because
  ``sse-starlette.EventSourceResponse`` holds its ASGI ``__call__`` open
  inside an ``anyio.create_task_group`` until the response generator
  exits, so an ASGI-only transport deadlocks before the client ever
  sees the response headers. The test therefore boots a real uvicorn
  server on a free localhost port.
* p99 of round-trip latency over 100 emits stays < 200ms.
* Cellular-handoff / disconnect resume: after a forced reconnect the
  consumer picks up from its last cursor and observes events emitted
  during the disconnect window once the stream comes back.
"""

from __future__ import annotations

import asyncio
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from bridge._generated.k1.handlers.curiosity_intent_v1 import (
    register_subscriber as register_curiosity_subscriber,
)
from bridge._generated.k1.models.curiosity_intent_v1 import CuriosityIntentV1
from bridge.core.transport.sse_client import (
    CursorStore,
    SSEClient,
    SSEClientConfig,
)
from bridge.runtime import BridgeRuntime, Role
from k0.sse.emitter import K0SSEEmitter
from k0.sse.endpoint import build_router as build_sse_router
from k0.sse.fanout import SSEFanout
from k0.sse.replay_buffer import SSEReplayBuffer

CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "bridge" / "contracts"


def _build_k0_app() -> tuple[FastAPI, K0SSEEmitter, SSEReplayBuffer, SSEFanout]:
    buf = SSEReplayBuffer.from_path(":memory:", retention_s=3600)
    fan = SSEFanout()
    emitter = K0SSEEmitter(replay_buffer=buf, fanout=fan)
    app = FastAPI()
    app.include_router(build_sse_router(replay_buffer=buf, fanout=fan))
    return app, emitter, buf, fan


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@asynccontextmanager
async def _serve(app: FastAPI):
    """Boot a uvicorn server on a free port for the lifetime of the ctx."""
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    deadline = time.monotonic() + 5.0
    while not server.started and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
    if not server.started:  # pragma: no cover - boot failure
        raise RuntimeError("uvicorn did not start in time")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await server_task


def _build_k1_runtime(
    *,
    base_url: str,
    cursor_path: Path,
) -> tuple[BridgeRuntime, SSEClient]:
    sse_client = SSEClient(
        SSEClientConfig(base_url=base_url),
        cursor_store=CursorStore(path=cursor_path),
    )
    runtime = BridgeRuntime(role=Role.K1, contracts_path=CONTRACTS_PATH)
    object.__setattr__(runtime, "_sse_client", sse_client)
    register_curiosity_subscriber(runtime)
    return runtime, sse_client


def _make_payload(idx: int) -> dict[str, object]:
    return {
        "envelope_id": f"01HZ-CUR-{idx:06d}",
        "gap_id": f"gap-{idx:06d}",
        "question_text": f"q{idx}",
        "budget_remaining": 10,
    }


@pytest.mark.asyncio
async def test_curiosity_intent_v1_streams_e2e_under_200ms_p99(tmp_path: Path) -> None:
    """100 emits, p99 round-trip < 200ms over real chunked SSE."""
    app, emitter, _buf, _fan = _build_k0_app()
    received: asyncio.Queue[CuriosityIntentV1] = asyncio.Queue()

    async def handler(event: CuriosityIntentV1) -> None:
        await received.put(event)

    n = 100
    latencies_ms: list[float] = []
    async with _serve(app) as base_url:
        runtime, sse_client = _build_k1_runtime(
            base_url=base_url, cursor_path=tmp_path / "cursors.sqlite"
        )
        try:
            async with runtime.sse.curiosity_intent_v1.subscribe(handler):
                await asyncio.sleep(0.2)
                for i in range(n):
                    t0 = time.monotonic()
                    await emitter.emit(
                        topic="curiosity.intent.v1",
                        schema_uri="bridge://contracts/schemas/curiosity.intent.v1.json",
                        payload=_make_payload(i),
                    )
                    event = await asyncio.wait_for(received.get(), timeout=5.0)
                    latencies_ms.append((time.monotonic() - t0) * 1000.0)
                    assert event.envelope_id == f"01HZ-CUR-{i:06d}"
        finally:
            await sse_client.aclose()

    latencies_ms.sort()
    p99 = latencies_ms[int(0.99 * (n - 1))]
    p50 = latencies_ms[n // 2]
    assert p99 < 200.0, (
        f"p99 latency {p99:.2f}ms exceeds 200ms budget "
        f"(p50={p50:.2f}ms, max={latencies_ms[-1]:.2f}ms)"
    )


@pytest.mark.asyncio
async def test_curiosity_intent_v1_cellular_handoff_resumes_via_cursor(
    tmp_path: Path,
) -> None:
    """Drop the active SSE TCP, emit during the gap, reconnect, verify resume."""
    app, emitter, _buf, _fan = _build_k0_app()
    cursor_path = tmp_path / "cursors.sqlite"

    async with _serve(app) as base_url:
        runtime1, sse1 = _build_k1_runtime(base_url=base_url, cursor_path=cursor_path)
        received_pre: asyncio.Queue[CuriosityIntentV1] = asyncio.Queue()

        async def handler_pre(event: CuriosityIntentV1) -> None:
            await received_pre.put(event)

        try:
            async with runtime1.sse.curiosity_intent_v1.subscribe(handler_pre):
                await asyncio.sleep(0.2)
                await emitter.emit(
                    topic="curiosity.intent.v1",
                    schema_uri="bridge://contracts/schemas/curiosity.intent.v1.json",
                    payload=_make_payload(1),
                )
                event = await asyncio.wait_for(received_pre.get(), timeout=5.0)
                assert event.envelope_id == "01HZ-CUR-000001"
        finally:
            await sse1.aclose()

        # Emit while disconnected \u2014 events persist in the replay buffer.
        await emitter.emit(
            topic="curiosity.intent.v1",
            schema_uri="bridge://contracts/schemas/curiosity.intent.v1.json",
            payload=_make_payload(2),
        )
        await emitter.emit(
            topic="curiosity.intent.v1",
            schema_uri="bridge://contracts/schemas/curiosity.intent.v1.json",
            payload=_make_payload(3),
        )

        runtime2, sse2 = _build_k1_runtime(base_url=base_url, cursor_path=cursor_path)
        received_post: asyncio.Queue[CuriosityIntentV1] = asyncio.Queue()

        async def handler_post(event: CuriosityIntentV1) -> None:
            await received_post.put(event)

        try:
            async with runtime2.sse.curiosity_intent_v1.subscribe(handler_post):
                ev2 = await asyncio.wait_for(received_post.get(), timeout=5.0)
                ev3 = await asyncio.wait_for(received_post.get(), timeout=5.0)
                assert {ev2.envelope_id, ev3.envelope_id} == {
                    "01HZ-CUR-000002",
                    "01HZ-CUR-000003",
                }
        finally:
            await sse2.aclose()
