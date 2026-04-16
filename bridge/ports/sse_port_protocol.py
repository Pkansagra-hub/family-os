"""IKernelSSEPort — K0→K1 server-sent event streaming.

Real-time events pushed from K0 to K1:
  memory.formed.v1, k0.learning.advisory.v1, k0.proactive.signal.v1,
  curiosity.intent.v1, k0.sync.complete.v1, cognitive.vector.stored.v1

Includes backpressure signalling (ok / throttle / shed).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class BackpressureLevel(enum.Enum):
    """K0 backpressure signal levels."""

    OK = "ok"
    THROTTLE = "throttle"
    SHED = "shed"


@dataclass(frozen=True, slots=True)
class SSEBackpressure:
    """Backpressure metadata from K0 SSE stream.

    Attributes:
        level: Current pressure level.
        lag_ms: How far behind K1 is from K0 WAL head.
        pending_events: Number of events waiting to be sent.
    """

    level: BackpressureLevel = BackpressureLevel.OK
    lag_ms: int = 0
    pending_events: int = 0


@dataclass(frozen=True, slots=True)
class SSETraceEvent:
    """A single event from the K0 SSE stream.

    Attributes:
        topic: Event topic (e.g. ``memory.formed.v1``).
        cursor: Opaque cursor for resumption after disconnect.
        wal_pos: K0 WAL position for this event.
        commit_ts: K0 commit timestamp (ISO-8601).
        policy_stamp: Policy version that produced this event.
        data: Event payload (structure depends on topic).
        backpressure: Optional backpressure metadata from K0.
    """

    topic: str
    cursor: str = ""
    wal_pos: int = 0
    commit_ts: str = ""
    policy_stamp: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    backpressure: SSEBackpressure | None = None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IKernelSSEPort(Protocol):
    """K0→K1 server-sent event streaming.

    Provides a persistent connection to K0 that yields real-time events
    for memory formation, learning advisories, proactive signals, etc.

    The subscriber MUST acknowledge processed events via ``ack()`` to
    advance the K0-side cursor.  On reconnect, the cursor is used to
    resume from the last acknowledged position.

    Offline behaviour:
        ``subscribe()`` returns an empty async iterator that never yields.
        When K0 becomes available again, the implementation reconnects
        with exponential backoff and resumes from the last cursor.
    """

    async def subscribe(
        self,
        topics: list[str] | None = None,
        *,
        cursor: str = "",
    ) -> AsyncIterator[SSETraceEvent]:
        """Open a streaming connection to K0 SSE endpoint.

        Args:
            topics: Topic filter list.  ``None`` = all topics.
            cursor: Resume cursor from previous session.

        Returns:
            Async iterator of SSETraceEvent.  Empty when offline.
        """
        ...  # pragma: no cover

    async def ack(self, topic: str, cursor: str) -> None:
        """Acknowledge processing of events up to the given cursor.

        Advances the K0-side cursor so that on reconnect, events
        before this cursor are not re-delivered.

        Args:
            topic: The topic to acknowledge.
            cursor: The cursor position to advance to.
        """
        ...  # pragma: no cover

    async def close(self) -> None:
        """Close the SSE connection gracefully."""
        ...  # pragma: no cover
