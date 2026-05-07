"""Endpoint tests for :mod:`k0.sse.endpoint` (MS-3d Epic 3d.3).

Uses ``httpx.AsyncClient`` over an ASGI ``FastAPI`` app to exercise the
real ``EventSourceResponse`` chunked stream, including the
``Last-Event-ID`` resume path and the ``replay-gap-detected`` synthetic
frame.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI

from k0.sse.emitter import K0SSEEmitter
from k0.sse.endpoint import build_router
from k0.sse.fanout import SSEFanout
from k0.sse.replay_buffer import SSEReplayBuffer


def _build_app() -> tuple[FastAPI, K0SSEEmitter, SSEReplayBuffer, SSEFanout]:
    buf = SSEReplayBuffer.from_path(":memory:", retention_s=3600)
    fan = SSEFanout()
    emitter = K0SSEEmitter(replay_buffer=buf, fanout=fan)
    app = FastAPI()
    app.include_router(build_router(replay_buffer=buf, fanout=fan))
    return app, emitter, buf, fan


async def _read_n_frames(
    resp: httpx.Response, n: int, timeout: float = 5.0
) -> list[dict[str, str]]:
    """Pull ``n`` SSE frames out of a chunked response and parse them."""
    frames: list[dict[str, str]] = []
    current: dict[str, str] = {}

    async def reader() -> None:
        nonlocal current
        async for line in resp.aiter_lines():
            if line == "":
                if current:
                    frames.append(current)
                    current = {}
                    if len(frames) >= n:
                        return
                continue
            if line.startswith(":"):
                continue  # comment / keepalive
            if ":" in line:
                k, _, v = line.partition(":")
                current[k.strip()] = v.lstrip()

    await asyncio.wait_for(reader(), timeout=timeout)
    return frames


@pytest.mark.asyncio
async def test_chunked_transfer_encoding_header() -> None:
    app, emitter, _buf, _fan = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/k0/sse/curiosity.intent.v1") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            # sse-starlette sets either "transfer-encoding: chunked" or
            # an unset content-length to enable streaming.
            assert "content-length" not in resp.headers


@pytest.mark.asyncio
async def test_live_publish_reaches_subscriber() -> None:
    app, emitter, _buf, _fan = _build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/k0/sse/curiosity.intent.v1") as resp:
            # Wait briefly so the subscriber registers before publish.
            await asyncio.sleep(0.05)
            await emitter.emit(
                topic="curiosity.intent.v1",
                schema_uri="schema://x",
                payload={"envelope_id": "01HZ-A", "msg": "hi"},
            )
            frames = await _read_n_frames(resp, 1)
    assert frames[0]["id"] == "01HZ-A"
    assert frames[0]["event"] == "curiosity.intent.v1"
    assert json.loads(frames[0]["data"]) == {"envelope_id": "01HZ-A", "msg": "hi"}


@pytest.mark.asyncio
async def test_last_event_id_replays_then_streams_live() -> None:
    app, emitter, _buf, _fan = _build_app()
    # Pre-populate buffer with two events.
    await emitter.emit(
        topic="curiosity.intent.v1",
        schema_uri="schema://x",
        payload={"envelope_id": "01HZ-A", "i": 1},
    )
    await emitter.emit(
        topic="curiosity.intent.v1",
        schema_uri="schema://x",
        payload={"envelope_id": "01HZ-B", "i": 2},
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Resume from cursor = "01HZ-A" \u21d2 should receive only "01HZ-B"
        # from replay, then the live "01HZ-C".
        async with client.stream(
            "GET",
            "/k0/sse/curiosity.intent.v1",
            headers={"Last-Event-ID": "01HZ-A"},
        ) as resp:
            await asyncio.sleep(0.05)
            await emitter.emit(
                topic="curiosity.intent.v1",
                schema_uri="schema://x",
                payload={"envelope_id": "01HZ-C", "i": 3},
            )
            frames = await _read_n_frames(resp, 2)
    assert [f["id"] for f in frames] == ["01HZ-B", "01HZ-C"]


@pytest.mark.asyncio
async def test_unknown_last_event_id_emits_replay_gap_and_closes() -> None:
    app, emitter, _buf, _fan = _build_app()
    await emitter.emit(
        topic="curiosity.intent.v1",
        schema_uri="schema://x",
        payload={"envelope_id": "REAL", "i": 1},
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "GET",
            "/k0/sse/curiosity.intent.v1",
            headers={"Last-Event-ID": "GHOST"},
        ) as resp:
            frames = await _read_n_frames(resp, 1)
    assert frames[0]["event"] == "replay-gap-detected"
    body = json.loads(frames[0]["data"])
    assert body == {"topic": "curiosity.intent.v1", "reason": "cursor older than retention"}


@pytest.mark.asyncio
async def test_unknown_topic_returns_404() -> None:
    buf = SSEReplayBuffer.from_path(":memory:")
    fan = SSEFanout()
    app = FastAPI()
    app.include_router(
        build_router(
            replay_buffer=buf,
            fanout=fan,
            allowed_topics=frozenset({"curiosity.intent.v1"}),
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/k0/sse/nope.v1")
    assert resp.status_code == 404
    buf.close()
