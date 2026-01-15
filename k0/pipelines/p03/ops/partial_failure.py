"""Partial failure handling strategies (Issue 6.2.9).

Implements COMMIT_PARTIAL, ROLLBACK_ALL, and QUARANTINE_BATCH strategies
for handling partial batch failures during P03 consolidation.

Dossier Reference: Section 13.7 Partial Failure Handling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class P03PartialFailureStrategy(Enum):
    """Strategies for handling partial batch failures.

    COMMIT_PARTIAL: Commit successful events, DLQ failed, advance offset.
    ROLLBACK_ALL: Rollback entire batch, no offset advance.
    QUARANTINE_BATCH: DLQ entire batch, advance offset.
    """

    COMMIT_PARTIAL = "COMMIT_PARTIAL"
    ROLLBACK_ALL = "ROLLBACK_ALL"
    QUARANTINE_BATCH = "QUARANTINE_BATCH"


@dataclass
class P03EventResult:
    """Result of processing a single event."""

    event_id: str
    success: bool
    error: Optional[Exception] = None
    phase: str = ""
    payload: Optional[bytes] = None


@dataclass
class P03BatchResult:
    """Result of processing a batch of events."""

    cycle_id: str
    phase: str
    tenant_id: str
    space_id: str
    total_count: int
    results: list[P03EventResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        """Count of successful event results."""
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        """Count of failed event results."""
        return sum(1 for r in self.results if not r.success)

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as fraction of total."""
        if self.total_count == 0:
            return 0.0
        return self.failure_count / self.total_count

    @property
    def successful_events(self) -> list[P03EventResult]:
        """Return list of successful event results."""
        return [r for r in self.results if r.success]

    @property
    def failed_events(self) -> list[P03EventResult]:
        """Return list of failed event results."""
        return [r for r in self.results if not r.success]


@dataclass
class PartialFailureOutcome:
    """Outcome of partial failure handling."""

    strategy: P03PartialFailureStrategy
    committed_count: int
    dlq_count: int
    offset_advanced: bool


# Phases where ordering is critical (use ROLLBACK_ALL on failure)
ORDERING_CRITICAL_PHASES: frozenset[str] = frozenset({"R7", "R8"})

# Failure rate threshold for QUARANTINE_BATCH (20%)
QUARANTINE_THRESHOLD: float = 0.20

# P03 driver constant for DLQ records
P03_DLQ_DRIVER: str = "p03_consolidation"


class PartialFailureHandler:
    """Handle partial batch failures with configurable strategies.

    Integrates with K0's DLQ and OffsetStore for recording failures
    and tracking progress.

    Dossier Reference: Section 13.7
    """

    def __init__(
        self,
        metrics: Optional[MetricsExporter] = None,
        *,
        quarantine_threshold: float = QUARANTINE_THRESHOLD,
    ) -> None:
        """Initialize partial failure handler.

        Args:
            metrics: Optional metrics exporter for observability.
            quarantine_threshold: Failure rate threshold for quarantine (default 20%).
        """
        self._metrics = metrics
        self._quarantine_threshold = quarantine_threshold

    def select_strategy(
        self,
        batch_result: P03BatchResult,
        *,
        force_strategy: Optional[P03PartialFailureStrategy] = None,
    ) -> P03PartialFailureStrategy:
        """Select appropriate failure handling strategy.

        Selection logic:
        1. If force_strategy provided, use it.
        2. If failure_rate > quarantine_threshold, use QUARANTINE_BATCH.
        3. If phase is ordering-critical (R7, R8) and has failures, use ROLLBACK_ALL.
        4. Otherwise, use COMMIT_PARTIAL.

        Args:
            batch_result: Results from batch processing.
            force_strategy: Override automatic selection.

        Returns:
            Selected strategy.
        """
        if force_strategy is not None:
            return force_strategy

        # High failure rate → quarantine entire batch
        if batch_result.failure_rate > self._quarantine_threshold:
            return P03PartialFailureStrategy.QUARANTINE_BATCH

        # Ordering-critical phases → rollback on any failure
        if batch_result.phase in ORDERING_CRITICAL_PHASES:
            if batch_result.failure_count > 0:
                return P03PartialFailureStrategy.ROLLBACK_ALL

        # Default: commit successful, DLQ failed
        return P03PartialFailureStrategy.COMMIT_PARTIAL

    async def handle_partial(
        self,
        batch_result: P03BatchResult,
        *,
        strategy: Optional[P03PartialFailureStrategy] = None,
        connection: Optional[asyncpg.Connection] = None,
    ) -> PartialFailureOutcome:
        """Handle partial failure using selected strategy.

        Args:
            batch_result: Results from batch processing.
            strategy: Override strategy (or auto-select).
            connection: Database connection for DLQ/offset operations.

        Returns:
            PartialFailureOutcome with strategy applied and counts.
        """
        selected = strategy or self.select_strategy(batch_result)

        self._emit_metric(
            "p03_partial_failure_strategy_total",
            strategy=selected.value,
            phase=batch_result.phase,
        )

        if selected == P03PartialFailureStrategy.COMMIT_PARTIAL:
            outcome = await self._commit_partial(batch_result, connection=connection)
        elif selected == P03PartialFailureStrategy.ROLLBACK_ALL:
            outcome = await self._rollback_all(batch_result, connection=connection)
        else:  # QUARANTINE_BATCH
            outcome = await self._quarantine_batch(batch_result, connection=connection)

        return outcome

    async def _commit_partial(
        self,
        batch_result: P03BatchResult,
        *,
        connection: Optional[asyncpg.Connection] = None,
    ) -> PartialFailureOutcome:
        """Commit successful events, send failed to DLQ, advance offset.

        K0 Integration:
        - UnitOfWork._commit() for successful events (handled by caller)
        - DLQStore.record() for failed events
        - OffsetStore.upsert() to advance offset
        """
        dlq_count = 0

        # Record failed events to DLQ
        for event_result in batch_result.failed_events:
            await self._record_to_dlq(batch_result, event_result, connection=connection)
            dlq_count += 1

        # Offset advancement is implicit (caller commits transaction)
        self._emit_metric(
            "p03_partial_commit_total",
            success_count=str(batch_result.success_count),
            failure_count=str(batch_result.failure_count),
        )

        return PartialFailureOutcome(
            strategy=P03PartialFailureStrategy.COMMIT_PARTIAL,
            committed_count=batch_result.success_count,
            dlq_count=dlq_count,
            offset_advanced=True,
        )

    async def _rollback_all(
        self,
        batch_result: P03BatchResult,
        *,
        connection: Optional[asyncpg.Connection] = None,
    ) -> PartialFailureOutcome:
        """Rollback entire batch, do not advance offset.

        K0 Integration:
        - UnitOfWork._rollback() for transaction rollback (handled by caller)
        - Offset NOT advanced (retry entire batch next cycle)
        """
        self._emit_metric(
            "p03_rollback_all_total",
            phase=batch_result.phase,
            total_count=str(batch_result.total_count),
        )

        return PartialFailureOutcome(
            strategy=P03PartialFailureStrategy.ROLLBACK_ALL,
            committed_count=0,
            dlq_count=0,
            offset_advanced=False,
        )

    async def _quarantine_batch(
        self,
        batch_result: P03BatchResult,
        *,
        connection: Optional[asyncpg.Connection] = None,
    ) -> PartialFailureOutcome:
        """Send entire batch to DLQ with quarantine status, advance offset.

        K0 Integration:
        - DLQStore.record() for all events with MANUAL_REVIEW status
        - OffsetStore.upsert() to advance offset past batch
        """
        dlq_count = 0

        # Record all events to DLQ (both success and failure)
        for event_result in batch_result.results:
            await self._record_to_dlq(
                batch_result,
                event_result,
                status="MANUAL_REVIEW",
                connection=connection,
            )
            dlq_count += 1

        self._emit_metric(
            "p03_quarantine_batch_total",
            phase=batch_result.phase,
            failure_rate=f"{batch_result.failure_rate:.2f}",
        )

        return PartialFailureOutcome(
            strategy=P03PartialFailureStrategy.QUARANTINE_BATCH,
            committed_count=0,
            dlq_count=dlq_count,
            offset_advanced=True,
        )

    async def _record_to_dlq(
        self,
        batch_result: P03BatchResult,
        event_result: P03EventResult,
        *,
        status: str = "PENDING",
        connection: Optional[asyncpg.Connection] = None,
    ) -> None:
        """Record single event to DLQ.

        Uses K0's DeadLetterQueue.record() for storage.
        """
        import time

        from k0.storage.dlq import DeadLetter

        now = int(time.time() * 1000)
        fingerprint = f"{batch_result.cycle_id}:{event_result.event_id}"
        reason = str(event_result.error) if event_result.error else "batch_quarantine"
        payload = event_result.payload or b"{}"

        letter = DeadLetter(
            id=None,
            wal_pos=None,
            tenant_id=batch_result.tenant_id,
            space_id=batch_result.space_id,
            driver=P03_DLQ_DRIVER,
            op_kind=batch_result.phase,
            fingerprint=fingerprint,
            payload=payload,
            reason=reason,
            retries=0,
            requeue_seq=0,
            first_failure_ts=str(now),
            last_failure_ts=str(now),
            state=status,
        )

        # Import DLQStore and record
        from k0.storage.dlq import DLQStore

        if connection is not None:
            await DLQStore.record(letter, connection=connection)
        # If no connection, caller is responsible for DLQ recording

        self._emit_metric("p03_dlq_record_total", phase=batch_result.phase)

    def _emit_metric(
        self, name: str, labels: Optional[dict[str, Any]] = None, **kwargs: str
    ) -> None:
        """Emit metric with labels."""
        if self._metrics is not None:
            all_labels = labels or {}
            all_labels.update(kwargs)
            self._metrics.emit(name, 1.0, **all_labels)


def create_partial_failure_handler(
    metrics: Optional[MetricsExporter] = None,
    *,
    quarantine_threshold: float = QUARANTINE_THRESHOLD,
) -> PartialFailureHandler:
    """Factory function to create PartialFailureHandler.

    Args:
        metrics: Optional metrics exporter.
        quarantine_threshold: Failure rate threshold for quarantine.

    Returns:
        Configured PartialFailureHandler instance.
    """
    return PartialFailureHandler(
        metrics=metrics,
        quarantine_threshold=quarantine_threshold,
    )
