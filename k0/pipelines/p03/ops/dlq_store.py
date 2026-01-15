"""P03 DLQ Store — Issue 6.2.3.

P03-specific DLQ record format and integration with K0's DeadLetterQueue.
Provides enriched context and P03-aware queries.

References:
- Dossier Section 13.4: Dead Letter Queue Schema (st_dlq)
- M6_EXECUTION.md Issue 6.2.3
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from k0.storage.dlq import DeadLetter, DeadLetterQueue


def _generate_ulid() -> str:
    """Generate a ULID-like identifier using UUID4."""
    return str(uuid.uuid4())


def _now_ms() -> int:
    """Get current time in milliseconds."""
    return int(time.time() * 1000)


if TYPE_CHECKING:
    import asyncpg

    from k0.obs.metrics import MetricsExporter


@dataclass
class P03DLQRecord:
    """P03-specific DLQ record with enriched context.

    Maps to/from K0 DeadLetter for persistence in st_dlq table.

    Attributes:
        id: Database ID (from st_dlq.id).
        dlq_id: ULID for this DLQ record.
        cycle_id: P03 consolidation cycle ID.
        phase: Phase where error occurred (R0-R8).
        event_id: Optional event ID if error was event-specific.
        entity_id: Optional entity ID if error was entity-specific.
        tenant_id: Tenant identifier.
        space_id: Space identifier.
        error_type: Classification (TRANSIENT, VALIDATION, LOGIC, FATAL).
        error_code: Exception class name.
        error_message: Error message string.
        stack_trace: Full stack trace if available.
        payload: Original payload that failed.
        attempt_count: Current retry attempt number.
        max_attempts: Maximum allowed retry attempts.
        first_failure_ts: First failure timestamp (ms).
        last_failure_ts: Most recent failure timestamp (ms).
        resolved_at: Resolution timestamp (ms) if resolved.
        status: Current status (PENDING, RETRYING, RESOLVED, ABANDONED, MANUAL_REVIEW).
        resolution_notes: Notes on how the issue was resolved.
    """

    # Identity
    id: Optional[int] = None
    dlq_id: str = field(default_factory=_generate_ulid)

    # P03 Context
    cycle_id: str = ""
    phase: str = ""
    event_id: Optional[str] = None
    entity_id: Optional[str] = None

    # Tenant Context
    tenant_id: str = ""
    space_id: str = ""

    # Error Details
    error_type: str = ""
    error_code: str = ""
    error_message: str = ""
    stack_trace: Optional[str] = None

    # Payload
    payload: dict = field(default_factory=dict)

    # Retry State
    attempt_count: int = 1
    max_attempts: int = 3

    # Timestamps (milliseconds)
    first_failure_ts: int = 0
    last_failure_ts: int = 0
    resolved_at: Optional[int] = None

    # Status
    status: str = "PENDING"
    resolution_notes: Optional[str] = None

    def to_dead_letter(self) -> DeadLetter:
        """Convert to K0 DeadLetter for persistence.

        Returns:
            DeadLetter instance for st_dlq table.
        """
        payload_dict = {
            "dlq_id": self.dlq_id,
            "cycle_id": self.cycle_id,
            "event_id": self.event_id,
            "entity_id": self.entity_id,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "payload": self.payload,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "resolution_notes": self.resolution_notes,
        }

        return DeadLetter(
            id=self.id,
            wal_pos=None,
            tenant_id=self.tenant_id,
            space_id=self.space_id,
            driver=P03DLQStore.DRIVER,
            op_kind=self.phase,
            fingerprint=f"{self.cycle_id}:{self.event_id or 'batch'}",
            payload=json.dumps(payload_dict).encode("utf-8"),
            reason=self.error_message,
            retries=self.attempt_count,
            requeue_seq=0,
            first_failure_ts=str(self.first_failure_ts),
            last_failure_ts=str(self.last_failure_ts),
            state=self.status,
        )

    @classmethod
    def from_dead_letter(cls, letter: DeadLetter) -> P03DLQRecord:
        """Create from K0 DeadLetter.

        Args:
            letter: DeadLetter from st_dlq table.

        Returns:
            P03DLQRecord with enriched context.
        """
        try:
            payload_data = json.loads(letter.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload_data = {}

        return cls(
            id=letter.id,
            dlq_id=payload_data.get("dlq_id", _generate_ulid()),
            cycle_id=payload_data.get("cycle_id", ""),
            phase=letter.op_kind,
            event_id=payload_data.get("event_id"),
            entity_id=payload_data.get("entity_id"),
            tenant_id=letter.tenant_id,
            space_id=letter.space_id,
            error_type=payload_data.get("error_type", ""),
            error_code=payload_data.get("error_code", ""),
            error_message=letter.reason,
            stack_trace=payload_data.get("stack_trace"),
            payload=payload_data.get("payload", {}),
            attempt_count=letter.retries,
            max_attempts=payload_data.get("max_attempts", 3),
            first_failure_ts=int(letter.first_failure_ts) if letter.first_failure_ts else 0,
            last_failure_ts=int(letter.last_failure_ts) if letter.last_failure_ts else 0,
            status=letter.state,
            resolution_notes=payload_data.get("resolution_notes"),
        )


class P03DLQStore:
    """P03-specific DLQ store wrapping K0 DeadLetterQueue.

    Provides P03 context-aware queries and metrics.
    Uses driver="p03_consolidation" and op_kind=phase for filtering.

    References:
    - k0/storage/dlq.py: DeadLetterQueue
    - Dossier Section 13.4
    """

    DRIVER = "p03_consolidation"

    def __init__(
        self,
        dlq: DeadLetterQueue,
        metrics: Optional[MetricsExporter] = None,
    ) -> None:
        """Initialize P03 DLQ store.

        Args:
            dlq: K0 DeadLetterQueue instance.
            metrics: Optional metrics exporter.
        """
        self._dlq = dlq
        self._metrics = metrics

    async def record_phase_error(
        self,
        record: P03DLQRecord,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record a phase-level error in DLQ.

        Args:
            record: P03DLQRecord with error details.
            connection: Optional database connection.

        Returns:
            The assigned dead letter ID.
        """
        now = _now_ms()
        if not record.first_failure_ts:
            record.first_failure_ts = now
        record.last_failure_ts = now

        letter = record.to_dead_letter()
        dlq_id = await self._dlq.record(letter, connection=connection)

        self._emit_metric(
            "p03_dlq_records_total",
            1.0,
            phase=record.phase,
            error_type=record.error_type,
            status=record.status,
        )

        return dlq_id

    async def record_event_error(
        self,
        record: P03DLQRecord,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record an event-level error in DLQ.

        Convenience wrapper for record_phase_error.

        Args:
            record: P03DLQRecord with event_id set.
            connection: Optional database connection.

        Returns:
            The assigned dead letter ID.
        """
        return await self.record_phase_error(record, connection=connection)

    async def record_batch_error(
        self,
        record: P03DLQRecord,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record a batch-level error in DLQ.

        Sets event_id to None for batch-level errors.

        Args:
            record: P03DLQRecord (event_id will be cleared).
            connection: Optional database connection.

        Returns:
            The assigned dead letter ID.
        """
        record.event_id = None
        return await self.record_phase_error(record, connection=connection)

    async def list_pending(
        self,
        *,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
        limit: int = 100,
        connection: asyncpg.Connection | None = None,
    ) -> List[P03DLQRecord]:
        """List all pending P03 DLQ records.

        Args:
            tenant_id: Optional tenant filter.
            space_id: Optional space filter.
            limit: Maximum records to return.
            connection: Optional database connection.

        Returns:
            List of P03DLQRecord objects.
        """
        letters = await self._dlq.list_pending(
            limit=limit,
            state="PENDING",
            tenant_id=tenant_id,
            space_id=space_id,
            driver=self.DRIVER,
            connection=connection,
        )
        return [P03DLQRecord.from_dead_letter(letter) for letter in letters]

    async def list_pending_by_phase(
        self,
        phase: str,
        *,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
        limit: int = 100,
        connection: asyncpg.Connection | None = None,
    ) -> List[P03DLQRecord]:
        """List pending DLQ records for a specific phase.

        Args:
            phase: Phase identifier (R0-R8).
            tenant_id: Optional tenant filter.
            space_id: Optional space filter.
            limit: Maximum records to return.
            connection: Optional database connection.

        Returns:
            List of P03DLQRecord objects for the phase.
        """
        letters = await self._dlq.list_pending(
            limit=limit,
            state="PENDING",
            tenant_id=tenant_id,
            space_id=space_id,
            driver=self.DRIVER,
            connection=connection,
        )
        # Filter by phase (op_kind)
        return [
            P03DLQRecord.from_dead_letter(letter) for letter in letters if letter.op_kind == phase
        ]

    async def list_pending_by_cycle(
        self,
        cycle_id: str,
        *,
        limit: int = 100,
        connection: asyncpg.Connection | None = None,
    ) -> List[P03DLQRecord]:
        """List pending DLQ records for a specific cycle.

        Args:
            cycle_id: P03 cycle ID.
            limit: Maximum records to return.
            connection: Optional database connection.

        Returns:
            List of P03DLQRecord objects for the cycle.
        """
        letters = await self._dlq.list_pending(
            limit=limit,
            state="PENDING",
            driver=self.DRIVER,
            connection=connection,
        )
        # Filter by cycle_id in fingerprint
        return [
            P03DLQRecord.from_dead_letter(letter)
            for letter in letters
            if letter.fingerprint.startswith(f"{cycle_id}:")
        ]

    async def list_by_status(
        self,
        status: str,
        *,
        limit: int = 100,
        connection: asyncpg.Connection | None = None,
    ) -> List[P03DLQRecord]:
        """List DLQ records by status.

        Args:
            status: Status to filter by (PENDING, REQUEUED, QUARANTINED).
            limit: Maximum records to return.
            connection: Optional database connection.

        Returns:
            List of P03DLQRecord objects with the status.
        """
        letters = await self._dlq.list_pending(
            limit=limit,
            state=status,
            driver=self.DRIVER,
            connection=connection,
        )
        return [P03DLQRecord.from_dead_letter(letter) for letter in letters]

    async def get(
        self,
        dlq_id: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Optional[P03DLQRecord]:
        """Get a specific DLQ record by ID.

        Args:
            dlq_id: Database ID of the DLQ record.
            connection: Optional database connection.

        Returns:
            P03DLQRecord if found, None otherwise.
        """
        letter = await self._dlq.get(dlq_id, connection=connection)
        if letter is None:
            return None
        return P03DLQRecord.from_dead_letter(letter)

    async def mark_resolved(
        self,
        dlq_id: int,
        *,
        resolution_notes: Optional[str] = None,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Mark DLQ entry as resolved (requeued).

        Args:
            dlq_id: Database ID of the DLQ record.
            resolution_notes: Optional notes on resolution.
            connection: Optional database connection.
        """
        await self._dlq.mark_requeued(dlq_id, connection=connection)

        self._emit_metric(
            "p03_dlq_resolved_total",
            1.0,
        )

    async def mark_quarantined(
        self,
        dlq_id: int,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> bool:
        """Mark DLQ entry as quarantined (purged).

        Args:
            dlq_id: Database ID of the DLQ record.
            connection: Optional database connection.

        Returns:
            True if entry was found and updated.
        """
        result = await self._dlq.purge(dlq_id, connection=connection)

        if result:
            self._emit_metric(
                "p03_dlq_quarantined_total",
                1.0,
            )

        return result

    def _emit_metric(self, name: str, value: float, **labels: str) -> None:
        """Emit metric if exporter available."""
        if self._metrics is not None:
            self._metrics.emit(name, value, **labels)
