"""Feedback worker for dispatching feedback signals to bus (ADR-055)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

    from k0.bus import BusDispatcher
    from k0.obs import MetricsExporter

logger = logging.getLogger(__name__)


class FeedbackWorker:
    """Background worker that publishes feedback signals from st_feedback_signals to bus.

    Uses stream="feedback" to avoid WAL pollution and semantic collision with WAL-backed events.
    Implements correct idempotency via feedback_id (not offset-based).

    Architecture (ADR-055):
    - Reads pending feedback from st_feedback_signals (status='pending')
    - Publishes to bus using stream="feedback" with message_id in metadata
    - Marks as processed (status='published') on success
    - Marks as failed (status='error') on dispatch errors
    - No WAL involvement: feedback signals don't need durability guarantees

    Backpressure:
    - Emits feedback_queue_depth metric (count of pending feedback)
    - Optional: Can implement 429 throttling at /k0/obs.emit if depth exceeds threshold
    """

    def __init__(
        self,
        *,
        pool: Pool,
        bus_dispatcher: BusDispatcher,
        metrics_exporter: MetricsExporter | None = None,
        batch_size: int = 100,
        poll_interval: float = 0.5,
    ) -> None:
        """Initialize feedback worker.

        Args:
            pool: Async database pool for claiming feedback signals
            bus_dispatcher: BusDispatcher configured with stream="feedback"
            metrics_exporter: Optional metrics exporter for feedback_queue_depth
            batch_size: Max feedback signals to process per batch
            poll_interval: Seconds to wait between polling iterations
        """
        self._pool = pool
        self._bus = bus_dispatcher
        self._metrics = metrics_exporter
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None

        # Register metrics
        if self._metrics:
            self._queue_depth_gauge = self._metrics.gauge(
                "feedback_queue_depth",
                "Count of pending feedback signals awaiting dispatch",
            )
            self._published_counter = self._metrics.counter(
                "feedback_signals_published",
                "Total feedback signals successfully published to bus",
            )
            self._failed_counter = self._metrics.counter(
                "feedback_signals_failed",
                "Total feedback signal dispatch failures",
            )
        else:
            self._queue_depth_gauge = None
            self._published_counter = None
            self._failed_counter = None

    async def start(self) -> None:
        """Start feedback worker background task."""
        if self._running:
            logger.warning("FeedbackWorker already running, ignoring start()")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("FeedbackWorker started")

    async def stop(self) -> None:
        """Stop feedback worker and wait for graceful shutdown."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("FeedbackWorker stopped")

    async def _run_loop(self) -> None:
        """Main worker loop: claim → dispatch → mark processed."""
        while self._running:
            try:
                # Emit queue depth metric
                await self._emit_queue_depth()

                # Claim batch of pending feedback
                batch = await self._claim_batch()
                if not batch:
                    await asyncio.sleep(self._poll_interval)
                    continue

                # Dispatch to bus (stream="feedback")
                await self._dispatch_batch(batch)

            except asyncio.CancelledError:
                logger.info("FeedbackWorker loop cancelled")
                raise
            except Exception:
                logger.exception("FeedbackWorker loop error (continuing)")
                await asyncio.sleep(self._poll_interval)

    async def _emit_queue_depth(self) -> None:
        """Emit feedback_queue_depth metric for backpressure monitoring."""
        if not self._queue_depth_gauge:
            return

        async with self._pool.acquire() as conn:
            depth = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM st_feedback_signals
                WHERE status = 'pending'
                """
            )
            self._queue_depth_gauge.set(depth or 0)

    async def _claim_batch(self) -> list[dict]:
        """Claim batch of pending feedback using FOR UPDATE SKIP LOCKED.

        Returns:
            List of claimed feedback rows with fields:
            - feedback_id, signal_type, source_pipeline, payload,
              provenance_data, trace_id, space_id, topic
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    feedback_id,
                    signal_type,
                    source_pipeline,
                    payload,
                    provenance_data,
                    trace_id,
                    space_id,
                    topic
                FROM st_feedback_signals
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                self._batch_size,
            )
            return [dict(row) for row in rows]

    async def _dispatch_batch(self, batch: list[dict]) -> None:
        """Dispatch feedback batch to bus and mark processed/failed."""
        from k0.bus import BUS_MESSAGE_ID_KEY, BusMessage

        messages = []
        for row in batch:
            # Construct BusMessage for stream="feedback"
            # CRITICAL: offset=None, message_id in metadata (ADR-055 enforcement)
            messages.append(
                BusMessage(
                    topic=row["topic"],
                    payload=row["payload"],
                    offset=None,  # stream="feedback" ignores offset
                    trace_id=row["trace_id"],
                    space_id=row["space_id"],
                    metadata={
                        BUS_MESSAGE_ID_KEY: row["feedback_id"],  # Required for stream="feedback"
                        "signal_type": row["signal_type"],
                        "source_pipeline": row["source_pipeline"],
                        "provenance": row["provenance_data"],
                    },
                )
            )

        # Dispatch to bus (will validate stream="feedback" requirements)
        try:
            await self._bus.dispatch(messages)

            # Mark all as published
            feedback_ids = [row["feedback_id"] for row in batch]
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE st_feedback_signals
                    SET status = 'published', published_at = NOW()
                    WHERE feedback_id = ANY($1::uuid[])
                    """,
                    feedback_ids,
                )

            if self._published_counter:
                self._published_counter.inc(len(batch))

            logger.debug(f"Published {len(batch)} feedback signals to bus")

        except Exception as e:
            logger.exception(f"Failed to dispatch feedback batch: {e}")

            # Mark all as failed
            feedback_ids = [row["feedback_id"] for row in batch]
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE st_feedback_signals
                    SET status = 'error', error_message = $1
                    WHERE feedback_id = ANY($2::uuid[])
                    """,
                    str(e),
                    feedback_ids,
                )

            if self._failed_counter:
                self._failed_counter.inc(len(batch))


@asynccontextmanager
async def feedback_worker_lifespan(
    pool: Pool,
    bus_dispatcher: BusDispatcher,
    metrics_exporter: MetricsExporter | None = None,
):
    """Context manager for feedback worker lifecycle management.

    Example:
        async with feedback_worker_lifespan(pool, feedback_bus, metrics) as worker:
            # Worker runs in background
            await asyncio.sleep(10)
        # Worker stops automatically on exit
    """
    worker = FeedbackWorker(
        pool=pool,
        bus_dispatcher=bus_dispatcher,
        metrics_exporter=metrics_exporter,
    )
    await worker.start()
    try:
        yield worker
    finally:
        await worker.stop()
