"""
k1.memory_writer.pipeline.session_batch_dispatcher -- Buffered turn batching (Option B).

Replaces the per-turn ``TurnDispatcher`` for production use. Buffers
``turn.completed.v1`` events and flushes the buffer to
``MemoryWriterPipeline.process_session()`` (one LLM call) when ANY of:

  (a) ``MemoryWriterService.stop()`` is called (session end),
  (b) buffer reaches ``config.flush_turn_threshold`` turns, or
  (c) no new turn has arrived for ``config.flush_idle_seconds`` seconds.

Trade-offs vs per-turn extraction:
  + ~30x fewer LLM calls per typical session.
  + Better atom quality: LLM sees the whole transcript, dedups naturally.
  + Lower context shipping cost.
  - Bounded data loss if process crashes mid-session before flush
    (worst case: last ``flush_turn_threshold`` turns since last flush).

Subscribes to the canonical FSM-side topic ``k1.session.turn.completed.v1``
(NOTE: legacy ``TurnDispatcher`` subscribed to ``k1.session.turn.complete.v1``
without the ``d`` and was a dead pipeline as a result).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Optional

from k1.memory_writer.events import TOPIC_TURN_COMPLETE as _CANONICAL_TOPIC
from k1.memory_writer.events import TurnCompletePayload
from k1.memory_writer.pipeline.pipeline import MemoryWriterPipeline
from k1.memory_writer.pipeline.turn_dispatcher import TurnDispatcher
from k1.memory_writer.ports.event_subscription_port import IEventSubscriptionPort
from k1.memory_writer.types import Subscription

log = logging.getLogger(__name__)


class SessionBatchDispatcher:
    """Buffered + threshold + idle flush dispatcher (Option B).

    Drop-in replacement for ``TurnDispatcher`` exposing the same
    ``start()`` / ``stop()`` lifecycle expected by ``MemoryWriterService``.
    """

    TOPIC = "k1.session.turn.completed.v1"

    def __init__(
        self,
        pipeline: MemoryWriterPipeline,
        event_port: IEventSubscriptionPort,
        flush_turn_threshold: int = 20,
        flush_idle_seconds: int = 300,
    ) -> None:
        if flush_turn_threshold < 1:
            raise ValueError("flush_turn_threshold must be >= 1")
        if flush_idle_seconds < 1:
            raise ValueError("flush_idle_seconds must be >= 1")

        self._pipeline = pipeline
        self._event_port = event_port
        self._flush_turn_threshold = flush_turn_threshold
        self._flush_idle_seconds = flush_idle_seconds

        self._subscription: Optional[Subscription] = None
        self._buffer: list[TurnCompletePayload] = []
        self._processed_ids: deque[str] = deque(maxlen=200)  # bounded: MW-02-A
        self._lock = asyncio.Lock()
        self._idle_task: Optional[asyncio.Task[None]] = None
        self._last_arrival_ts: float = 0.0
        self._stopping: bool = False
        self._flush_in_progress: bool = False  # MW-03: concurrent flush guard

    async def start(self) -> None:
        """Subscribe to ``turn.completed.v1`` and start the idle-flush task."""
        # Drift guard: ensure our TOPIC matches the canonical events.py constant (MW-01-D)
        assert (
            self.TOPIC == _CANONICAL_TOPIC
        ), f"SessionBatchDispatcher.TOPIC drift: {self.TOPIC!r} != {_CANONICAL_TOPIC!r}"
        self._stopping = False
        self._subscription = await self._event_port.subscribe(self.TOPIC, self._on_turn_completed)
        self._idle_task = asyncio.create_task(self._idle_loop(), name="mw-session-idle-flush")
        log.info(
            "MW: SessionBatchDispatcher started, topic=%s, threshold=%d, idle=%ds",
            self.TOPIC,
            self._flush_turn_threshold,
            self._flush_idle_seconds,
        )

    async def stop(self) -> None:
        """Unsubscribe, cancel idle task, flush remaining buffer (session end)."""
        self._stopping = True

        # Cancel idle task first so it cannot interleave with the final flush
        if self._idle_task is not None:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._idle_task = None

        if self._subscription is not None:
            try:
                await self._event_port.unsubscribe(self._subscription.subscription_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("MW: unsubscribe failed, error=%s", str(exc))
            self._subscription = None

        # Final flush (session end) — drain any buffered turns
        await self._flush_buffer(reason="session_end")

        # Drain any leftover envelopes in the aggregator
        try:
            await self._pipeline.flush_pending()
        except Exception as exc:  # noqa: BLE001
            log.warning("MW: flush_pending error on stop, error=%s", str(exc))

        self._processed_ids.clear()
        log.info("MW: SessionBatchDispatcher stopped")

    async def _on_turn_completed(self, raw_payload: dict) -> None:
        """Bus handler: deserialize, dedup, append to buffer, maybe flush."""
        try:
            payload = TurnDispatcher._deserialize(raw_payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("MW: failed to deserialize turn event, error=%s", str(exc))
            return

        if not payload.turn_id:
            log.warning("MW: turn event missing turn_id, skipping")
            return

        if payload.turn_id in self._processed_ids:
            log.info("MW: duplicate turn_id, skipping, turn_id=%s", payload.turn_id)
            return

        async with self._lock:
            if payload.turn_id in self._processed_ids:
                return  # double-check under lock
            self._processed_ids.append(payload.turn_id)  # bounded deque: MW-02-A
            self._buffer.append(payload)
            self._last_arrival_ts = time.monotonic()
            should_flush = len(self._buffer) >= self._flush_turn_threshold

        if should_flush:
            await self._flush_buffer(reason="threshold")

    async def _idle_loop(self) -> None:
        """Periodically check whether the buffer has been idle long enough to flush."""
        check_interval = max(1.0, self._flush_idle_seconds / 4)
        while not self._stopping:
            try:
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                return

            async with self._lock:
                buffer_has = bool(self._buffer)
                idle_for = time.monotonic() - self._last_arrival_ts

            if buffer_has and idle_for >= self._flush_idle_seconds:
                await self._flush_buffer(reason="idle")

    async def _flush_buffer(self, reason: str) -> None:
        """Flush the buffer through the pipeline (one LLM call). Never raises."""
        async with self._lock:
            if not self._buffer or self._flush_in_progress:
                return
            turns = self._buffer
            self._buffer = []
            self._flush_in_progress = True  # MW-03: block concurrent flushes

        try:
            result = await self._pipeline.process_session(turns)
            log.info(
                "MW: session batch processed, reason=%s, turns=%d, "
                "atoms=%d, submitted=%d, trace=%s, error=%s",
                reason,
                len(turns),
                result.atoms_extracted,
                result.envelopes_submitted,
                result.trace_id,
                result.error or "",
            )
        except Exception as exc:  # noqa: BLE001
            log.error(
                "MW: session batch error, reason=%s, turns=%d, error=%s",
                reason,
                len(turns),
                str(exc),
            )
        finally:
            async with self._lock:
                self._flush_in_progress = False

    # ----- Test introspection helpers -----

    @property
    def buffered_count(self) -> int:
        """Number of turns currently buffered (for tests)."""
        return len(self._buffer)
