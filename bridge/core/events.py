"""In-process pub/sub event bus for the bridge runtime.

E-3b.1: a tiny, dependency-free event hub so the K0 health checker can
broadcast transition events to the drain worker (Epic 3b.3) and the
DEGRADED matrix (Epic 3b.2) without any of those modules importing
each other directly.

Design intent:

* Single producer (``K0HealthChecker``) per runtime; many subscribers.
* Subscribers each own an :class:`asyncio.Queue` so a slow consumer
  cannot stall fast consumers.
* No threading; the bus assumes a running asyncio loop.
* Topic-typed: events are dataclasses; the bus keys subscriptions by
  the dataclass type. Type-narrow subscribers receive exactly one
  event class.

Anyone needing cross-module signalling inside ``bridge/`` SHOULD route
through this module rather than reaching into private state. Tests
construct their own :class:`EventBus` for isolation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthTransition:
    """Emitted by :class:`bridge.core.health.K0HealthChecker` on every
    state change. Drain worker subscribes to drain on
    ``OFFLINE → ONLINE``; DEGRADED matrix subscribes to refresh its
    "currently active behaviors" view.

    Attributes:
        from_state: Previous health state value (lowercase string).
        to_state: New health state value.
        at_utc: UTC timestamp of the transition.
        consecutive_failures: Failure counter at the moment of transition.
        latency_ms: Latency observed on the probe that caused the flip
            (``0`` for failures).
        reason: Optional human-readable reason (e.g. ``"probe_timeout"``).
    """

    from_state: str
    to_state: str
    at_utc: datetime
    consecutive_failures: int = 0
    latency_ms: int = 0
    reason: str = ""


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBus:
    """Tiny topic-typed asyncio pub/sub.

    One bus per :class:`bridge.runtime.BridgeRuntime`. Subscribers call
    :meth:`subscribe` to obtain an ``asyncio.Queue`` keyed by event
    dataclass type. Producers call :meth:`publish`.

    Thread-safety: callers MUST be on the same event loop. The bus does
    not cross loops.
    """

    def __init__(self) -> None:
        self._subscribers: dict[type, list[asyncio.Queue[Any]]] = {}

    def subscribe(self, event_type: type, *, maxsize: int = 256) -> asyncio.Queue[Any]:
        """Register a new subscriber queue for ``event_type``.

        Returns an :class:`asyncio.Queue` the caller awaits on. Bounded
        by ``maxsize`` so a wedged consumer cannot exhaust memory; if
        full, ``publish`` logs and drops (the runtime's safety-net
        sweep covers any missed event).
        """
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.setdefault(event_type, []).append(queue)
        return queue

    def unsubscribe(self, event_type: type, queue: asyncio.Queue[Any]) -> None:
        """Remove a previously-registered queue (best-effort)."""
        try:
            self._subscribers.get(event_type, []).remove(queue)
        except ValueError:
            pass

    def publish(self, event: Any) -> int:
        """Fan-out ``event`` to every subscriber of its concrete type.

        Returns the number of queues delivered to. Drops (with a log
        line) any queue that is full — bridge events are advisory; the
        outbox / health-state-machine remains the source of truth.
        """
        event_type = type(event)
        delivered = 0
        for queue in self._subscribers.get(event_type, []):
            try:
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                logger.warning(
                    "EventBus: dropping %s for full subscriber queue (size=%d)",
                    event_type.__name__,
                    queue.qsize(),
                )
        return delivered

    def subscriber_count(self, event_type: type) -> int:
        """Diagnostic: how many subscribers are listening for ``event_type``."""
        return len(self._subscribers.get(event_type, []))


def utc_now() -> datetime:
    """UTC ``datetime`` helper used by event constructors."""
    return datetime.now(timezone.utc)
