"""P03 Outbox Publisher — Drains staged outbox entries to bus. Issue 3.1.3.

This module implements the outbox drain loop for P03, responsible for:
- Dequeuing ready outbox entries (staged by R7)
- Publishing to the event bus via BusDispatcher
- Handling transient failures with exponential backoff
- Escalating permanent failures to the Dead Letter Queue

Per Dossier 13.5 retry strategy:
- Exponential backoff formula: min(base_delay * 2^retries + jitter, max_delay)
- Max retries configurable (default 3)
- After max retries: escalate to DLQ with full context
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from k0.bus.core import BusDispatcher, BusMessage
from k0.storage.dlq import DeadLetter, DeadLetterQueue
from k0.storage.outbox import OutboxEntry, OutboxStore

if TYPE_CHECKING:
    from k0.obs.metrics import MetricsExporter

__all__ = [
    "OutboxPublisherConfig",
    "P03OutboxPublisher",
    "PublishResult",
]

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class OutboxPublisherConfig:
    """Configuration for P03 outbox publisher.

    Attributes:
        driver: Driver identifier for filtering outbox entries.
        batch_size: Maximum entries to process per drain cycle.
        max_retries: Maximum retry attempts before DLQ escalation.
        base_delay_ms: Base delay for exponential backoff (milliseconds).
        max_delay_ms: Maximum backoff delay cap (milliseconds).
        jitter_factor: Random jitter factor (0.0-1.0) to prevent thundering herd.
    """

    driver: str = "p03"
    batch_size: int = 100
    max_retries: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 30000
    jitter_factor: float = 0.1


@dataclass(slots=True)
class PublishResult:
    """Result of a drain batch operation.

    Attributes:
        processed: Total entries processed.
        published: Entries successfully published to bus.
        retried: Entries scheduled for retry.
        dlq_count: Entries escalated to DLQ.
        errors: List of error messages for failed entries.
    """

    processed: int = 0
    published: int = 0
    retried: int = 0
    dlq_count: int = 0
    errors: list[str] = field(default_factory=list)


class P03OutboxPublisher:
    """Drains P03 outbox entries to the event bus.

    Implements:
    - Dequeue via OutboxStore.dequeue_ready_batch()
    - Publish to BusDispatcher with BusMessage
    - Exponential backoff with jitter (per Dossier 13.5)
    - DLQ escalation after max retries
    - At-least-once delivery semantics

    Thread Safety:
        Not thread-safe. Use one instance per async context.
    """

    def __init__(
        self,
        *,
        outbox_store: OutboxStore,
        bus_dispatcher: BusDispatcher,
        dlq_store: DeadLetterQueue,
        config: OutboxPublisherConfig | None = None,
        metrics: MetricsExporter | None = None,
    ) -> None:
        """Initialize the outbox publisher.

        Args:
            outbox_store: Store for outbox entry operations.
            bus_dispatcher: Event bus dispatcher for message publishing.
            dlq_store: Dead letter queue for permanent failures.
            config: Publisher configuration (uses defaults if None).
            metrics: Optional metrics exporter for observability.
        """
        self._outbox = outbox_store
        self._bus = bus_dispatcher
        self._dlq = dlq_store
        self._config = config or OutboxPublisherConfig()
        self._metrics = metrics

    @property
    def config(self) -> OutboxPublisherConfig:
        """Return the publisher configuration."""
        return self._config

    async def drain_batch(self) -> PublishResult:
        """Drain a batch of outbox entries to the event bus.

        Dequeues entries for driver='p03' that are ready for processing
        (respecting next_attempt_ts backoff). For each entry:
        - Attempt to publish to bus
        - On success: mark_applied (removes from outbox)
        - On failure: record_failure with backoff, or escalate to DLQ

        Returns:
            PublishResult with counts of processed, published, retried, dlq.
        """
        result = PublishResult()
        start_time = time.perf_counter()

        # Dequeue ready entries
        batch: list[OutboxEntry] = await self._outbox.dequeue_ready_batch(
            driver=self._config.driver,
            limit=self._config.batch_size,
        )

        if not batch:
            return result

        for entry in batch:
            result.processed += 1

            # Entries from dequeue_ready_batch always have an id
            if entry.id is None:
                LOGGER.error("Outbox entry missing id, skipping")
                continue

            success, error = await self._publish_entry(entry)

            if success:
                await self._outbox.mark_applied(entry.id)
                result.published += 1
                self._emit_published_metric(entry)
            else:
                await self._handle_failure(entry, error or "Unknown error", result)

        # Emit drain duration metric
        duration_ms = (time.perf_counter() - start_time) * 1000
        self._emit_drain_duration_metric(duration_ms)

        LOGGER.info(
            "P03 outbox drain completed: processed=%d, published=%d, retried=%d, dlq=%d",
            result.processed,
            result.published,
            result.retried,
            result.dlq_count,
        )

        return result

    async def _publish_entry(self, entry: OutboxEntry) -> tuple[bool, str | None]:
        """Attempt to publish a single entry to the bus.

        Args:
            entry: The outbox entry to publish.

        Returns:
            Tuple of (success, error_message).
        """
        try:
            # Parse payload as JSON for metadata
            try:
                payload_dict = json.loads(entry.payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload_dict = {}

            # Extract trace_id and space_id from payload if present
            trace_id = payload_dict.get("trace_id") if isinstance(payload_dict, dict) else None
            space_id = entry.space_id

            # Create BusMessage with proper structure
            # op_kind is the topic (e.g., "p03.consolidation.complete.v1")
            message = BusMessage(
                topic=entry.op_kind,
                payload=entry.payload,
                offset=entry.wal_pos,
                trace_id=trace_id,
                space_id=space_id,
                metadata={
                    "tenant_id": entry.tenant_id,
                    "fingerprint": entry.fingerprint,
                    "driver": entry.driver,
                },
            )

            # Dispatch to bus (dispatch takes Iterable[BusMessage])
            await self._bus.dispatch([message])
            return True, None

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            LOGGER.warning(
                "Failed to publish outbox entry %s: %s",
                entry.id,
                error_msg,
            )
            return False, error_msg

    async def _handle_failure(
        self,
        entry: OutboxEntry,
        error: str,
        result: PublishResult,
    ) -> None:
        """Handle publish failure with exponential backoff or DLQ escalation.

        Per Dossier 13.5:
        - delay = min(base_delay * 2^retries + jitter, max_delay)
        - After max_retries: escalate to DLQ

        Args:
            entry: The failed outbox entry.
            error: Error message from publish attempt.
            result: PublishResult to update with retry/dlq counts.
        """
        new_retries = entry.retries + 1
        result.errors.append(f"Entry {entry.id}: {error}")

        # entry.id is guaranteed to be set for entries from dequeue_ready_batch
        entry_id = entry.id
        if entry_id is None:
            LOGGER.error("Outbox entry missing id in _handle_failure, skipping")
            return

        if new_retries > self._config.max_retries:
            # Escalate to DLQ
            await self._send_to_dlq(entry, error)
            await self._outbox.mark_applied(entry_id)  # Remove from outbox
            result.dlq_count += 1
            self._emit_dlq_metric(entry)
            LOGGER.warning(
                "Outbox entry %s exceeded max retries (%d), escalated to DLQ",
                entry_id,
                self._config.max_retries,
            )
        else:
            # Calculate backoff with jitter and schedule retry
            delay_ms = self._calculate_backoff(new_retries)
            next_attempt = datetime.now(timezone.utc).replace(
                microsecond=0,
            )
            # Add delay (convert ms to seconds for timedelta)
            next_attempt = datetime.fromtimestamp(
                next_attempt.timestamp() + (delay_ms / 1000),
                tz=timezone.utc,
            )

            await self._outbox.record_failure(
                entry,
                retries=new_retries,
                requeue_seq=entry.requeue_seq,
                last_error=error,
                next_attempt_ts=next_attempt,
                backoff_exp=new_retries,
                status="PENDING",
            )
            result.retried += 1
            self._emit_retry_metric(entry)
            LOGGER.debug(
                "Outbox entry %s retry scheduled: attempt=%d, next_attempt=%s",
                entry.id,
                new_retries,
                next_attempt.isoformat(),
            )

    def _calculate_backoff(self, retries: int) -> int:
        """Calculate exponential backoff delay with jitter.

        Formula: min(base_delay * 2^retries + random_jitter, max_delay)

        Args:
            retries: Current retry attempt number (1-based).

        Returns:
            Delay in milliseconds.
        """
        base_delay = self._config.base_delay_ms * (2**retries)
        jitter = random.uniform(0, self._config.jitter_factor * base_delay)
        delay = int(base_delay + jitter)
        return min(delay, self._config.max_delay_ms)

    async def _send_to_dlq(self, entry: OutboxEntry, error: str) -> None:
        """Send entry to Dead Letter Queue.

        DLQ entry includes P03 context for debugging:
        - driver: "p03"
        - op_kind: Original topic
        - reason: Error message with context

        Args:
            entry: The outbox entry to escalate.
            error: Error message explaining failure.
        """
        now = datetime.now(timezone.utc).isoformat()

        dead_letter = DeadLetter(
            id=None,
            wal_pos=entry.wal_pos,
            tenant_id=entry.tenant_id,
            space_id=entry.space_id,
            driver=entry.driver,
            op_kind=entry.op_kind,
            fingerprint=entry.fingerprint,
            payload=entry.payload,
            reason=f"P03 publish failed after {entry.retries + 1} attempts: {error}",
            retries=entry.retries + 1,
            requeue_seq=entry.requeue_seq,
            first_failure_ts=now,
            last_failure_ts=now,
            state="PENDING",
        )

        dlq_id = await self._dlq.record(dead_letter)
        LOGGER.info(
            "Outbox entry %s moved to DLQ as dead_letter_id=%d",
            entry.id,
            dlq_id,
        )

    def _emit_published_metric(self, entry: OutboxEntry) -> None:
        """Emit metric for successfully published entry."""
        if self._metrics is not None:
            self._metrics.emit(
                "p03_outbox_published_total",
                1.0,
                topic=entry.op_kind,
                driver=entry.driver,
            )

    def _emit_retry_metric(self, entry: OutboxEntry) -> None:
        """Emit metric for retried entry."""
        if self._metrics is not None:
            self._metrics.emit(
                "p03_outbox_retry_total",
                1.0,
                topic=entry.op_kind,
                driver=entry.driver,
            )

    def _emit_dlq_metric(self, entry: OutboxEntry) -> None:
        """Emit metric for DLQ escalation."""
        if self._metrics is not None:
            self._metrics.emit(
                "p03_outbox_dlq_total",
                1.0,
                topic=entry.op_kind,
                driver=entry.driver,
            )

    def _emit_drain_duration_metric(self, duration_ms: float) -> None:
        """Emit metric for drain batch duration."""
        if self._metrics is not None:
            self._metrics.observe(
                "p03_outbox_drain_duration_ms",
                duration_ms,
                labels={"driver": self._config.driver},
            )
