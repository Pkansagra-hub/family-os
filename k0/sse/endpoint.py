"""K0 SSE endpoint \u2014 chunked stream + Last-Event-ID resume (MS-3d Epic 3d.3).

This is the **new** MS-3d SSE wire surface, distinct from the legacy
:mod:`k0.ports.sse` route (``/k0/sse.subscribe?topics=...``) which
routes WAL traffic. The new route is **per-topic** at
``GET /k0/sse/{topic}`` and is the canonical home for the five
MS-3d.1 push manifests (``curiosity.intent.v1``, ``k0.proactive.signal.v1``,
``k0.learning.advisory.v1``, ``p03.gap.detected.v1``, ``p03.complete.v1``).

Wire grammar produced (per the W3C SSE spec):

    id: <envelope_id>
    event: <topic>
    data: <json-body>
    \\n

On stale cursor (a ``Last-Event-ID`` value not present in the buffer),
a single synthetic frame is emitted and the connection is closed:

    id: <stale-cursor>
    event: replay-gap-detected
    data: {"reason": "...", "topic": "..."}
    \\n
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, Path, Request
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from k0.sse.fanout import FanoutEvent, SSEFanout
from k0.sse.replay_buffer import ReplayGapError, SSEReplayBuffer

logger = logging.getLogger(__name__)


KEEPALIVE_INTERVAL_S: float = 15.0
"""Server-side keepalive heartbeat. ``EventSourceResponse(ping=...)``
emits a ``: ping`` comment frame at this cadence so intermediaries don't
close idle connections; the K1 client's parser silently drops comments."""


def build_router(
    *,
    replay_buffer: SSEReplayBuffer,
    fanout: SSEFanout,
    allowed_topics: frozenset[str] | None = None,
) -> APIRouter:
    """Build the SSE router bound to ``replay_buffer`` and ``fanout``.

    ``allowed_topics`` (when provided) gates the route to a known set of
    contract topics; an unknown topic returns 404 instead of opening a
    stream against an empty buffer. In production this is the union of
    every active SSE manifest topic.
    """
    router = APIRouter()

    @router.get("/k0/sse/{topic:path}")
    async def stream(  # noqa: D401 \u2014 framework callable, not a public API doc
        request: Request,
        topic: str = Path(..., min_length=1),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> EventSourceResponse:
        """Open a chunked SSE stream for ``topic``.

        Reads ``Last-Event-ID`` (case-insensitive) and replays every
        event with ``seq > cursor_seq`` first, then live-fanout events
        until the client disconnects.
        """
        if allowed_topics is not None and topic not in allowed_topics:
            # 404 is more honest than an empty stream for unknown topics.
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"unknown SSE topic: {topic!r}")

        async def event_generator() -> AsyncIterator[ServerSentEvent]:
            # ----- Replay phase -----------------------------------------
            try:
                replay_iter = replay_buffer.replay_after(topic=topic, cursor=last_event_id)
            except ReplayGapError as gap:
                logger.info(
                    "sse_endpoint: replay gap topic=%s cursor=%s",
                    gap.topic,
                    gap.cursor,
                )
                yield ServerSentEvent(
                    id=last_event_id or "",
                    event="replay-gap-detected",
                    data=json.dumps(
                        {"topic": topic, "reason": "cursor older than retention"},
                        separators=(",", ":"),
                    ),
                )
                return

            for event in replay_iter:
                if await request.is_disconnected():
                    return
                yield ServerSentEvent(
                    id=event.envelope_id,
                    event=event.topic,
                    data=json.dumps(event.payload, separators=(",", ":")),
                )

            # ----- Live phase -------------------------------------------
            async with fanout.subscribe(topic) as sub:
                while not sub.closed.is_set():
                    if await request.is_disconnected():
                        return
                    try:
                        live = await asyncio.wait_for(sub.queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue  # let keepalive fire / re-check disconnect
                    yield ServerSentEvent(
                        id=live.envelope_id,
                        event=live.topic,
                        data=json.dumps(live.payload, separators=(",", ":")),
                    )

        return EventSourceResponse(
            event_generator(),
            ping=int(KEEPALIVE_INTERVAL_S),
            headers={"Cache-Control": "no-cache"},
        )

    return router


__all__ = ("KEEPALIVE_INTERVAL_S", "build_router")
