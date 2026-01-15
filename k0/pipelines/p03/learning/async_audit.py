"""
P03 async audit logger with batched writes.

Non-blocking audit logging to avoid impacting consolidation cycle.

Dossier Reference: Section 15.10 Async Writes
K0 References:
- k0/obs/metrics.py: MetricsExporter.counter()
- k0/obs/logging.py: Structured logging

Issue 6.4.15 - AsyncAuditLogger implementation
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prometheus_client import Counter

    from k0.drivers.postgres import PostgresDriver
    from k0.obs.metrics import MetricsExporter

logger = logging.getLogger(__name__)


# Batch configuration from dossier Section 15.10
WRITE_INTERVAL_SECONDS: int = 30
MAX_BATCH_SIZE: int = 50
QUEUE_MAX_SIZE: int = 500


@dataclass
class AuditRecord:
    """Audit record for consolidation changes.

    Attributes:
        audit_id: Unique audit identifier (ULID)
        memory_id: Associated memory identifier
        cycle_id: Consolidation cycle identifier
        operation: Operation type (merge, prune, decay, etc.)
        before_state: State before operation (optional)
        after_state: State after operation (optional)
        timestamp: When the operation occurred
        space_id: Space identifier for isolation
        metadata: Additional metadata
    """

    audit_id: str
    memory_id: str
    cycle_id: str
    operation: str
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    space_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


class AsyncAuditLogger:
    """
    Non-blocking audit logging with batched writes.

    Queues audit records and writes in batches every 30s.
    Uses fire-and-forget semantics to avoid impacting
    consolidation cycle latency.

    Dossier Reference: Section 15.10 Async Writes
    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for tracking

    Attributes:
        db: K0 PostgresDriver instance
        write_interval: Seconds between batch writes
        max_batch_size: Max records per batch
        pipeline_id: Pipeline identifier for labels
    """

    def __init__(
        self,
        db: PostgresDriver,
        metrics: MetricsExporter,
        write_interval: int = WRITE_INTERVAL_SECONDS,
        max_batch_size: int = MAX_BATCH_SIZE,
        queue_max_size: int = QUEUE_MAX_SIZE,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize async audit logger.

        Args:
            db: K0 PostgresDriver instance
            metrics: K0 MetricsExporter instance
            write_interval: Seconds between batch writes (default 30)
            max_batch_size: Max records per batch (default 50)
            queue_max_size: Max queue size before drops (default 500)
            pipeline_id: Pipeline identifier for labels
        """
        self.db = db
        self.write_interval = write_interval
        self.max_batch_size = max_batch_size
        self.pipeline_id = pipeline_id

        self.write_queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=queue_max_size)
        self.writer_task: asyncio.Task[None] | None = None
        self._running: bool = False

        # K0 metrics
        self._write_counter: Counter = metrics.counter(
            name="p03_audit_writes",
            description="Audit records written",
            labelnames=["batch_size", "pipeline_id"],
        )

        self._drop_counter: Counter = metrics.counter(
            name="p03_audit_drops",
            description="Audit records dropped",
            labelnames=["pipeline_id"],
        )

        self._batch_counter: Counter = metrics.counter(
            name="p03_audit_batches",
            description="Audit batches written",
            labelnames=["pipeline_id"],
        )

    async def start(self) -> None:
        """Start background writer task."""
        if self._running:
            return
        self._running = True
        self.writer_task = asyncio.create_task(self._writer_loop())
        logger.info("async_audit_logger_started pipeline_id=%s", self.pipeline_id)

    async def stop(self) -> None:
        """Stop background writer and flush remaining."""
        self._running = False
        if self.writer_task:
            self.writer_task.cancel()
            try:
                await self.writer_task
            except asyncio.CancelledError:
                pass

        # Flush remaining
        await self._flush()
        logger.info("async_audit_logger_stopped pipeline_id=%s", self.pipeline_id)

    def log_audit(self, record: AuditRecord) -> bool:
        """
        Queue audit record (non-blocking).

        Fire-and-forget semantics: returns immediately.
        If queue is full, record is dropped and metric incremented.

        Args:
            record: Audit record to log

        Returns:
            True if queued, False if dropped
        """
        try:
            self.write_queue.put_nowait(record)
            return True
        except asyncio.QueueFull:
            # Drop audit if queue full (fire-and-forget)
            self._drop_counter.labels(pipeline_id=self.pipeline_id).inc()
            logger.warning(
                "audit_record_dropped audit_id=%s reason=queue_full",
                record.audit_id,
            )
            return False

    async def _writer_loop(self) -> None:
        """Background writer: batch writes every 30s."""
        while self._running:
            try:
                await asyncio.sleep(self.write_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("audit_writer_loop_error error=%s", str(e))

    async def _flush(self) -> None:
        """Flush pending records."""
        batch: list[AuditRecord] = []

        # Drain queue up to max batch size
        while not self.write_queue.empty() and len(batch) < self.max_batch_size:
            try:
                record = self.write_queue.get_nowait()
                batch.append(record)
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._write_batch(batch)

    async def _write_batch(self, batch: list[AuditRecord]) -> None:
        """
        Write batch to database.

        Uses executemany for efficient batched inserts.

        Args:
            batch: Records to write
        """
        try:
            # Prepare records for insertion
            records = [
                (
                    r.audit_id,
                    r.memory_id,
                    r.cycle_id,
                    r.operation,
                    json.dumps(r.before_state) if r.before_state else None,
                    json.dumps(r.after_state) if r.after_state else None,
                    r.timestamp,
                    r.space_id,
                    json.dumps(r.metadata) if r.metadata else None,
                )
                for r in batch
            ]

            # Use executemany for batched inserts
            await self.db.executemany(
                """
                INSERT INTO st_consolidation_audit
                (audit_id, memory_id, cycle_id, operation, before_state,
                 after_state, timestamp, space_id, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (audit_id) DO NOTHING
                """,
                records,
            )

            # Record metrics
            self._write_counter.labels(
                batch_size=str(len(batch)),
                pipeline_id=self.pipeline_id,
            ).inc(len(batch))
            self._batch_counter.labels(pipeline_id=self.pipeline_id).inc()

            logger.debug(
                "audit_batch_written batch_size=%d pipeline_id=%s",
                len(batch),
                self.pipeline_id,
            )
        except Exception as e:
            logger.error(
                "audit_batch_write_failed batch_size=%d error=%s",
                len(batch),
                str(e),
            )
            # Re-queue failed records (up to a point)
            for record in batch:
                try:
                    self.write_queue.put_nowait(record)
                except asyncio.QueueFull:
                    self._drop_counter.labels(pipeline_id=self.pipeline_id).inc()
                    break

    @property
    def pending_count(self) -> int:
        """Number of pending audit records."""
        return self.write_queue.qsize()

    @property
    def is_running(self) -> bool:
        """Whether the writer task is running."""
        return self._running

    def get_stats(self) -> dict[str, Any]:
        """
        Get logger statistics.

        Returns:
            Dictionary with pending_count, is_running, etc.
        """
        return {
            "pending_count": self.pending_count,
            "is_running": self.is_running,
            "write_interval": self.write_interval,
            "max_batch_size": self.max_batch_size,
            "pipeline_id": self.pipeline_id,
        }
