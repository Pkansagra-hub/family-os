"""MS-3b Epic 3b.3 \u2014 ``DrainWorker``: event-driven outbox replay with
safety-net periodic sweep, bounded batches, per-contract pacing, and
dead-letter routing on 4xx responses.

Three triggers (per D-resolved item 2):

* **Event-driven**: subscribes to
  :class:`bridge.core.events.HealthTransition` and drains immediately
  when ``OFFLINE \u2192 ONLINE`` flips. Target latency: \u226450ms p99 from
  transition to first batch attempt.
* **Safety-net**: periodic sweep every ``safety_net_interval_s`` (60s
  default) so a missed/dropped event still drains the queue.
* **Startup**: one immediate pass when :meth:`start` is called so
  envelopes queued during a previous offline window go out as soon as
  the new process boots.

The worker never blocks the event loop: each drain pass yields to other
tasks between batches.

Failure routing:
- ``2xx``                \u2192 ``LocalOutbox.delete``
- ``409`` (idempotency)  \u2192 ``LocalOutbox.delete``
- ``4xx`` other          \u2192 ``LocalOutbox.move_to_dead_letter`` (no retry)
- ``5xx`` / transport    \u2192 leave in outbox; retry on next pass

Per-contract pacing is honoured via a ``rate_for`` callback that returns
``drain_rate_per_sec`` for a topic. ``None`` disables pacing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.events import EventBus
    from ..core.transport import HttpTransport
    from .local_outbox import LocalOutbox

logger = logging.getLogger(__name__)

DEFAULT_SAFETY_NET_INTERVAL_S = 60.0
DEFAULT_BATCH_SIZE = 100
DEFAULT_BATCH_WALL_BUDGET_S = 5.0


class DrainWorker:
    """Background drain orchestrator owned by :class:`bridge.runtime.BridgeRuntime`.

    Parameters
    ----------
    outbox:
        :class:`bridge.sync.local_outbox.LocalOutbox` instance.
    transport:
        Open :class:`bridge.core.transport.HttpTransport` used for
        ``post_command``.
    event_bus:
        Bus to subscribe to ``HealthTransition`` events. Optional \u2014
        when omitted only the safety-net + startup paths run.
    rate_for:
        Optional callable ``topic -> Optional[float]`` returning the
        per-contract ``drain_rate_per_sec`` cap. ``None`` disables
        pacing.
    safety_net_interval_s:
        Period for the periodic sweep.
    batch_size:
        Maximum envelopes per drain pass.
    batch_wall_budget_s:
        Wall-clock cap per batch; the worker yields control once
        exceeded so the event loop can service other tasks.
    """

    def __init__(
        self,
        *,
        outbox: "LocalOutbox",
        transport: "HttpTransport",
        event_bus: "EventBus | None" = None,
        rate_for: Callable[[str], float | None] | None = None,
        safety_net_interval_s: float = DEFAULT_SAFETY_NET_INTERVAL_S,
        batch_size: int = DEFAULT_BATCH_SIZE,
        batch_wall_budget_s: float = DEFAULT_BATCH_WALL_BUDGET_S,
    ) -> None:
        self._outbox = outbox
        self._transport = transport
        self._rate_for = rate_for or (lambda _topic: None)
        self._safety_net_interval_s = safety_net_interval_s
        self._batch_size = batch_size
        self._batch_wall_budget_s = batch_wall_budget_s
        self._stop_event: asyncio.Event | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._sub_task: asyncio.Task[None] | None = None
        self._wakeup_event = asyncio.Event()
        self._first_batch_after_transition_ms: float | None = None

        self._event_bus = event_bus
        self._sub_queue = None
        if event_bus is not None:
            from ..core.events import HealthTransition

            self._sub_queue = event_bus.subscribe(HealthTransition)

    @property
    def first_batch_after_transition_ms(self) -> float | None:
        """Latency from ``OFFLINE \u2192 ONLINE`` event to first batch attempt.

        Used by the MS-3b exit test (epic 3b.6) to assert p99 \u2264 50ms.
        ``None`` until a transition has been processed.
        """
        return self._first_batch_after_transition_ms

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        self._loop_task = loop.create_task(self._main_loop())
        if self._sub_queue is not None:
            self._sub_task = loop.create_task(self._event_loop())
        # Startup pass: drain whatever was queued during a previous
        # offline window.
        self._wakeup_event.set()

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        self._wakeup_event.set()
        for task in (self._loop_task, self._sub_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._loop_task = None
        self._sub_task = None
        self._stop_event = None

    # -- triggers ----------------------------------------------------------

    async def _event_loop(self) -> None:
        """Subscribe to health transitions; trigger drain on OFFLINE \u2192 ONLINE."""
        assert self._sub_queue is not None
        while True:
            evt = await self._sub_queue.get()
            if (  # noqa: degraded-mode — structural recovery-edge detector, not a policy branch
                evt.from_state == "OFFLINE" and evt.to_state == "ONLINE"
            ):
                self._transition_at = time.monotonic()
                self._wakeup_event.set()

    async def _main_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._wakeup_event.wait(),
                    timeout=self._safety_net_interval_s,
                )
            except asyncio.TimeoutError:
                pass
            self._wakeup_event.clear()
            if self._stop_event.is_set():
                break
            await self._drain_pass()

    # -- drain --------------------------------------------------------------

    async def drain_now(self) -> int:
        """Synchronous-ish manual drain (used by tests). Returns count drained."""
        return await self._drain_pass()

    async def _drain_pass(self) -> int:
        """One full pass: prune TTL, then drain up to ``batch_size`` rows."""
        # Capture transition latency on first batch attempt after recovery.
        if (
            self._first_batch_after_transition_ms is None
            and getattr(self, "_transition_at", None) is not None
        ):
            self._first_batch_after_transition_ms = (
                time.monotonic() - self._transition_at
            ) * 1000.0

        self._outbox.prune_expired()
        entries = self._outbox.list_pending(limit=self._batch_size)
        if not entries:
            return 0

        started = time.monotonic()
        succeeded = 0
        for entry in entries:
            if (time.monotonic() - started) > self._batch_wall_budget_s:
                break
            outcome = await self._drain_one(entry)
            if outcome is True:
                succeeded += 1
            # Per-contract pacing.
            rate = self._rate_for(entry.topic)
            if rate is not None and rate > 0:
                await asyncio.sleep(1.0 / rate)
            else:
                # Yield to other tasks each iteration.
                await asyncio.sleep(0)
        return succeeded

    async def _drain_one(self, entry) -> bool:
        try:
            result = await self._transport.post_command(entry.envelope_json.encode("utf-8"))
        except Exception as exc:  # transport-level failure
            logger.warning(
                "DrainWorker: transport error id=%d topic=%s: %s",
                entry.id,
                entry.topic,
                exc,
            )
            return False

        code = result.status_code
        if code == 200 or code == 409:
            self._outbox.delete(entry.id)
            return True
        if 400 <= code < 500:
            body = getattr(result, "body", None)
            body_text: str | None
            if body is None:
                body_text = None
            elif isinstance(body, str):
                body_text = body
            else:
                import json

                try:
                    body_text = json.dumps(body)
                except (TypeError, ValueError):
                    body_text = repr(body)
            self._outbox.move_to_dead_letter(
                entry.id,
                reason=f"http_{code}",
                response_code=code,
                response_body=body_text,
            )
            return False
        # 5xx / unknown \u2014 leave in outbox; LocalOutbox.drain has its own
        # attempts counter for the legacy path, but the worker simply
        # retries on the next pass.
        logger.warning(
            "DrainWorker: id=%d topic=%s 5xx (%d) \u2014 will retry",
            entry.id,
            entry.topic,
            code,
        )
        return False
