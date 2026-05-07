"""In-process pub/sub fanout broker for K0 SSE topics (MS-3d Epic 3d.3).

Producer side (P06 / P03 / P05 emitters) calls :meth:`SSEFanout.publish`
synchronously after the event is durably appended to the
:class:`k0.sse.replay_buffer.SSEReplayBuffer`. The fanout broker
forwards the event to every currently-subscribed consumer (one
``asyncio.Queue`` per HTTP-level subscriber). Slow consumers don't
back-pressure the producer: each per-subscriber queue is bounded and on
overflow the **subscriber's stream is closed** (drop the connection,
not the event \u2014 the event is already in the replay buffer; the
consumer reconnects with its cursor and replays).

This is the in-memory hot path. It complements the durable replay
buffer; the buffer is the source of truth for "did the event ship?"
and the fanout is the optimisation for "tell live consumers in
microseconds, not seconds".
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


SSE_FANOUT_QUEUE_MAXSIZE_DEFAULT = 1024
"""Per-subscriber queue cap. A subscriber that falls behind by more
than this many events is closed by the broker (consumer must reconnect
with its cursor)."""


@dataclass(frozen=True)
class FanoutEvent:
    """One event passed through the fanout broker. Mirrors :class:`ReplayEvent`."""

    topic: str
    envelope_id: str
    payload: dict[str, Any]


@dataclass
class _Subscription:
    topic: str
    queue: asyncio.Queue[FanoutEvent]
    closed: asyncio.Event = field(default_factory=asyncio.Event)


class SSEFanout:
    """Topic-keyed fan-out broker.

    Constructed once per K0 process. Thread-safe under the asyncio event
    loop's invariant: every public method either runs on the event loop
    or grabs ``asyncio.run_coroutine_threadsafe``-friendly primitives.
    """

    def __init__(
        self,
        *,
        queue_maxsize: int = SSE_FANOUT_QUEUE_MAXSIZE_DEFAULT,
    ) -> None:
        self._queue_maxsize = queue_maxsize
        self._subs: dict[str, list[_Subscription]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Producer side.
    # ------------------------------------------------------------------

    def publish(self, event: FanoutEvent) -> int:
        """Deliver ``event`` to every live subscriber on its topic.

        Synchronous (non-blocking): each subscriber's bounded queue is
        ``put_nowait``-d. Returns the number of subscribers reached.
        Slow / full subscribers are **closed**; the buffer is the
        source of truth and they will resume on reconnect.
        """
        subs = list(self._subs.get(event.topic, ()))  # snapshot
        delivered = 0
        for sub in subs:
            if sub.closed.is_set():
                continue
            try:
                sub.queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                # Slow consumer \u2014 close the subscription. The K1 client
                # reconnects with cursor; events are not lost (replay
                # buffer holds them).
                logger.warning(
                    "sse_fanout: slow consumer on topic=%s, closing subscription",
                    event.topic,
                )
                sub.closed.set()
        return delivered

    # ------------------------------------------------------------------
    # Consumer side.
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def subscribe(self, topic: str) -> AsyncIterator[_Subscription]:
        """Open a subscription on ``topic``.

        Returns the underlying :class:`_Subscription` whose ``queue``
        is fed by the broker and whose ``closed`` event signals the
        endpoint to terminate the response stream cleanly.
        """
        sub = _Subscription(
            topic=topic,
            queue=asyncio.Queue(maxsize=self._queue_maxsize),
        )
        async with self._lock:
            self._subs.setdefault(topic, []).append(sub)
        try:
            yield sub
        finally:
            sub.closed.set()
            async with self._lock:
                lst = self._subs.get(topic)
                if lst is not None:
                    try:
                        lst.remove(sub)
                    except ValueError:
                        pass
                    if not lst:
                        self._subs.pop(topic, None)

    # ------------------------------------------------------------------
    # Introspection (tests + /k0/sse/health metrics).
    # ------------------------------------------------------------------

    def subscriber_count(self, topic: str | None = None) -> int:
        if topic is None:
            return sum(len(v) for v in self._subs.values())
        return len(self._subs.get(topic, ()))


__all__ = (
    "FanoutEvent",
    "SSE_FANOUT_QUEUE_MAXSIZE_DEFAULT",
    "SSEFanout",
)
