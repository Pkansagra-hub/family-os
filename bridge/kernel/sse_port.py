"""Concrete IKernelSSEPort — K0→K1 server-sent event streaming.

Implements persistent SSE connection to K0 with cursor-based resumption,
backpressure awareness, and offline fallback (empty async iterator).

Issue 3.9.4 (MS-3): Scaffold adapter — transport calls are wired but
K0 SSE endpoint does not exist yet.  Offline path fully functional.

References:
  - bridge/ports/sse_port_protocol.py (IKernelSSEPort)
  - bridge/client.py (IBridgeClient.subscribe / ack / close_sse)
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from ..core.transport import HttpTransport
from ..ports.sse_port_protocol import SSEBackpressure, SSETraceEvent

logger = logging.getLogger(__name__)

# K0 SSE endpoints (MS-3+: not yet deployed on K0 side)
_SSE_SUBSCRIBE_PATH = "/k0/sse.subscribe"
_SSE_ACK_PATH = "/k0/sse.ack"


class KernelSSEPort:
    """Bridge-side SSE port for receiving K0→K1 real-time events.

    Offline behaviour:
        ``subscribe()`` returns an empty async iterator that yields
        nothing.  ``ack()`` and ``close()`` are no-ops.

    Parameters
    ----------
    transport : HttpTransport
        HTTP client for K0 communication.  Must be opened before use.
    """

    __slots__ = ("_transport", "_active")

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport
        self._active: bool = False

    async def subscribe(
        self,
        topics: list[str] | None = None,
        *,
        cursor: str = "",
    ) -> AsyncIterator[SSETraceEvent]:
        """Open a streaming connection to K0 SSE endpoint.

        Returns an empty async iterator when K0 is unreachable.
        """
        try:
            client = self._transport._ensure_client()
            response = await client.post(
                _SSE_SUBSCRIBE_PATH,
                content=json.dumps(
                    {"topics": topics, "cursor": cursor},
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            )
            if response.status_code != 200:
                logger.warning(
                    "KernelSSEPort.subscribe: K0 returned status=%d, returning empty stream",
                    response.status_code,
                )
                return _empty_async_iter()
        except Exception:
            logger.warning(
                "KernelSSEPort.subscribe: transport error, returning empty stream",
                exc_info=True,
            )
            return _empty_async_iter()

        self._active = True
        return self._consume_stream(response)

    async def ack(self, topic: str, cursor: str) -> None:
        """Acknowledge processing of events up to the given cursor."""
        try:
            client = self._transport._ensure_client()
            await client.post(
                _SSE_ACK_PATH,
                content=json.dumps(
                    {"topic": topic, "cursor": cursor},
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            logger.warning(
                "KernelSSEPort.ack: failed topic=%s cursor=%s",
                topic,
                cursor,
                exc_info=True,
            )

    async def close(self) -> None:
        """Close the SSE connection gracefully."""
        self._active = False
        logger.debug("KernelSSEPort: SSE connection closed")

    async def _consume_stream(
        self,
        response: Any,
    ) -> AsyncIterator[SSETraceEvent]:
        """Parse response stream into SSETraceEvent objects.

        NOTE: Real SSE streaming requires httpx-sse or similar.
        This scaffold parses a JSON array response as a fallback.
        """
        try:
            body = response.json()
            events = body.get("events", []) if isinstance(body, dict) else []
            for raw_event in events:
                if not self._active:
                    break
                yield self._parse_event(raw_event)
        except Exception:
            logger.warning(
                "KernelSSEPort: stream parse error",
                exc_info=True,
            )
        finally:
            self._active = False

    @staticmethod
    def _parse_event(raw: dict[str, Any]) -> SSETraceEvent:
        """Parse a raw event dict into SSETraceEvent."""
        bp_raw = raw.get("backpressure")
        backpressure = None
        if bp_raw:
            from ..ports.sse_port_protocol import BackpressureLevel

            backpressure = SSEBackpressure(
                level=BackpressureLevel(bp_raw.get("level", "ok")),
                lag_ms=int(bp_raw.get("lag_ms", 0)),
                pending_events=int(bp_raw.get("pending_events", 0)),
            )

        return SSETraceEvent(
            topic=raw.get("topic", ""),
            cursor=raw.get("cursor", ""),
            wal_pos=int(raw.get("wal_pos", 0)),
            commit_ts=raw.get("commit_ts", ""),
            policy_stamp=raw.get("policy_stamp", ""),
            data=raw.get("data", {}),
            backpressure=backpressure,
        )


async def _empty_async_iter() -> AsyncIterator[SSETraceEvent]:
    """Yield nothing — empty async iterator for offline fallback."""
    return
    yield  # noqa: RET504 — makes this an async generator
