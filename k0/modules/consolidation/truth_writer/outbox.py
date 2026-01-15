"""
OutboxWriter — Issue 5.2.2

Transactional outbox pattern implementation for durable memory layer writes.
Ensures exactly-once semantics through idempotency keys (fingerprints).

Spec Reference:
    - M5_EXECUTION.md (Issue 5.2.2 — Outbox pattern implementation)
    - Dossier §4.8.1 (Outbox Pattern Implementation)
    - Dossier §6.15 (st_outbox Schema)

DESIGN DECISIONS:
    - All writes go through st_outbox for durability
    - Idempotency keys (fingerprint) prevent duplicate writes on retry
    - Batch staging for efficiency (configurable max batch size)
    - Status lifecycle: PENDING → PROCESSING → DONE/FAILED

Fingerprint (idempotency key) format:
    p03:write:{cycle_ulid}:{layer}:{record_id}

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from k0.pipelines.p03.staged_writes import StagedOutboxEvent, StagedWrite
from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork


@dataclass
class OutboxWriteConfig:
    """
    Configuration for OutboxWriter.

    Attributes:
        driver_prefix: Target table prefix (default 'p03')
        max_batch_size: Maximum writes per batch (default 100)
        retry_backoff_base_ms: Base backoff for retries in milliseconds (default 1000)
        enable_fingerprint: Whether to generate fingerprints (default True)
    """

    driver_prefix: str = "p03"
    max_batch_size: int = 100
    retry_backoff_base_ms: int = 1000
    enable_fingerprint: bool = True


@dataclass
class OutboxStagingResult:
    """
    Result of outbox staging operation.

    Attributes:
        writes_staged: Number of writes successfully staged
        events_staged: Number of events successfully staged
        total_staged: Total items staged
        fingerprints: List of generated fingerprints
    """

    writes_staged: int = 0
    events_staged: int = 0
    fingerprints: List[str] = field(default_factory=list)

    @property
    def total_staged(self) -> int:
        """Total items staged (writes + events)."""
        return self.writes_staged + self.events_staged


class OutboxWriter:
    """
    Wrapper for durable writes via st_outbox transactional pattern.

    Ensures all memory layer writes are persisted durably through the
    outbox table before being processed. Provides exactly-once semantics
    through fingerprint-based idempotency.

    Outbox Entry Lifecycle:
        1. PENDING: Entry created within UoW transaction
        2. PROCESSING: Background worker picks up entry
        3. DONE: Write successfully applied
        4. FAILED: Write failed after max retries (moves to DLQ)

    Usage:
        writer = OutboxWriter()
        async with uow:
            writer.stage_write(uow, write, tenant_id, space_id)
            # Entry committed with transaction

    The outbox worker processes entries asynchronously, ensuring
    writes survive process crashes and network failures.
    """

    def __init__(self, config: OutboxWriteConfig | None = None):
        """
        Initialize OutboxWriter.

        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self._config = config or OutboxWriteConfig()

    @property
    def config(self) -> OutboxWriteConfig:
        """Current configuration."""
        return self._config

    @property
    def max_batch_size(self) -> int:
        """Maximum batch size for staging."""
        return self._config.max_batch_size

    def stage_write(
        self,
        uow: UnitOfWork,
        write: StagedWrite,
        tenant_id: str,
        space_id: str,
        cycle_ulid: Optional[str] = None,
    ) -> str:
        """
        Stage a StagedWrite as an outbox entry for durability.

        Creates an OutboxEntry with the write's data and stages it
        within the current UnitOfWork transaction.

        Fingerprint format:
            p03:write:{cycle_ulid}:{layer}:{record_id}

        If write already has an idempotency_key, it's used as fingerprint.
        Otherwise, a fingerprint is generated from the parameters.

        Args:
            uow: Active UnitOfWork
            write: StagedWrite to stage
            tenant_id: Tenant identifier
            space_id: Space identifier
            cycle_ulid: Optional cycle ULID for fingerprint

        Returns:
            Generated fingerprint (idempotency key)
        """
        fingerprint = self._generate_fingerprint(write, cycle_ulid)

        entry = OutboxEntry(
            id=None,  # Auto-assigned by database
            wal_pos=0,  # Set by outbox store
            tenant_id=tenant_id,
            space_id=space_id,
            driver=write.layer,  # Target table (st_epi, st_sem, etc.)
            op_kind=write.operation.value,  # INSERT/UPDATE/ARCHIVE
            payload=json.dumps(write.record_data).encode("utf-8"),
            fingerprint=fingerprint,  # Prevents duplicates
            requeue_seq=0,
            retries=0,
        )

        uow.stage_outbox(entry)
        return fingerprint

    def stage_batch(
        self,
        uow: UnitOfWork,
        writes: List[StagedWrite],
        tenant_id: str,
        space_id: str,
        cycle_ulid: Optional[str] = None,
    ) -> OutboxStagingResult:
        """
        Stage multiple writes as outbox entries.

        Stages writes up to max_batch_size. For larger batches,
        call multiple times or increase max_batch_size.

        Args:
            uow: Active UnitOfWork
            writes: List of StagedWrite objects
            tenant_id: Tenant identifier
            space_id: Space identifier
            cycle_ulid: Optional cycle ULID for fingerprints

        Returns:
            OutboxStagingResult with staging statistics
        """
        fingerprints: List[str] = []
        batch_writes = writes[: self._config.max_batch_size]

        for write in batch_writes:
            fingerprint = self.stage_write(
                uow=uow,
                write=write,
                tenant_id=tenant_id,
                space_id=space_id,
                cycle_ulid=cycle_ulid,
            )
            fingerprints.append(fingerprint)

        return OutboxStagingResult(
            writes_staged=len(batch_writes),
            fingerprints=fingerprints,
        )

    def stage_event(
        self,
        uow: UnitOfWork,
        event: StagedOutboxEvent,
        tenant_id: str,
        space_id: str,
    ) -> str:
        """
        Stage an outbox event for R8 emission.

        Outbox events are different from writes - they're messages
        to be published after successful commit.

        Args:
            uow: Active UnitOfWork
            event: StagedOutboxEvent to stage
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            Event fingerprint
        """
        fingerprint = f"p03:event:{event.event_id}"

        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=tenant_id,
            space_id=space_id,
            driver="bus",  # Internal bus driver
            op_kind="EMIT",  # Event emission
            payload=json.dumps(
                {
                    "topic": event.topic,
                    "payload": event.payload,
                    "priority": event.priority,
                    "source_phase": event.source_phase,
                }
            ).encode("utf-8"),
            fingerprint=fingerprint,
            requeue_seq=0,
            retries=0,
        )

        uow.stage_outbox(entry)
        return fingerprint

    def stage_events_batch(
        self,
        uow: UnitOfWork,
        events: List[StagedOutboxEvent],
        tenant_id: str,
        space_id: str,
    ) -> OutboxStagingResult:
        """
        Stage multiple outbox events.

        Args:
            uow: Active UnitOfWork
            events: List of StagedOutboxEvent objects
            tenant_id: Tenant identifier
            space_id: Space identifier

        Returns:
            OutboxStagingResult with staging statistics
        """
        fingerprints: List[str] = []
        batch_events = events[: self._config.max_batch_size]

        for event in batch_events:
            fingerprint = self.stage_event(
                uow=uow,
                event=event,
                tenant_id=tenant_id,
                space_id=space_id,
            )
            fingerprints.append(fingerprint)

        return OutboxStagingResult(
            events_staged=len(batch_events),
            fingerprints=fingerprints,
        )

    def _generate_fingerprint(
        self,
        write: StagedWrite,
        cycle_ulid: Optional[str] = None,
    ) -> str:
        """
        Generate fingerprint (idempotency key) for a write.

        If the write already has an idempotency_key, use it.
        Otherwise, generate from cycle_ulid, layer, and record_id.

        Format: p03:write:{cycle_ulid}:{layer}:{record_id}

        Args:
            write: StagedWrite to generate fingerprint for
            cycle_ulid: Optional cycle ULID

        Returns:
            Fingerprint string
        """
        if not self._config.enable_fingerprint:
            return ""

        # Use existing idempotency key if present
        if write.idempotency_key:
            return write.idempotency_key

        # Generate from components
        cycle_part = cycle_ulid or "unknown"
        return f"p03:write:{cycle_part}:{write.layer}:{write.record_id}"


def create_outbox_writer(
    config: OutboxWriteConfig | None = None,
) -> OutboxWriter:
    """
    Factory function to create an OutboxWriter.

    Args:
        config: Optional configuration

    Returns:
        Configured OutboxWriter
    """
    return OutboxWriter(config=config)
