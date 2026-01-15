"""
P03 Offset Manager — Issue 1.2.6

Implements offset/watermark integration for P03 pipeline, enabling
exactly-once processing semantics by managing WAL position tracking.

References:
- Spec: docs/pipelines/P03_consolidation_dossier_v2.md §4.9.2
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.6
- Checkpoint: k0/pipelines/p03/checkpoint.py (Issue 1.2.5)
- K0 OffsetStore: k0/storage/offsets.py

Key Behaviors:
- Offset writes ONLY on successful cycle completion (R8 DONE)
- Aborted cycles with resumable phases persist checkpoint, NOT offset
- Aborted cycles with non-resumable phases go to DLQ, no offset advance
- Idempotent offset updates for retry safety

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, runtime_checkable

from k0.pipelines.p03.checkpoint import (
    P03_SOURCE_TOPIC,
    P03_SUBSCRIBER_ID,
    P03Checkpoint,
    P03Offset,
)
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.phase_interface import P03CycleResult
    from k0.uow.unit_of_work import UnitOfWork


# =============================================================================
# OFFSET MANAGER ERRORS
# =============================================================================


class OffsetManagerError(Exception):
    """Base error for offset manager operations."""

    pass


class OffsetWriteError(OffsetManagerError):
    """Failed to write offset."""

    def __init__(self, reason: str, cycle_id: Optional[str] = None):
        self.reason = reason
        self.cycle_id = cycle_id
        msg = f"Offset write failed: {reason}"
        if cycle_id:
            msg = f"Offset write failed for cycle {cycle_id}: {reason}"
        super().__init__(msg)


class OffsetIdempotencyError(OffsetManagerError):
    """Offset already written for this cycle (idempotency check)."""

    def __init__(self, cycle_id: str, existing_offset: int):
        self.cycle_id = cycle_id
        self.existing_offset = existing_offset
        super().__init__(
            f"Offset already committed for cycle {cycle_id} at position {existing_offset}"
        )


# =============================================================================
# OFFSET ACTION ENUM
# =============================================================================


class OffsetAction(str, Enum):
    """Actions to take based on cycle result."""

    COMMIT = "COMMIT"  # Cycle complete (R8 DONE) - advance offset
    CHECKPOINT_ONLY = "CHECKPOINT_ONLY"  # Resumable failure - persist checkpoint, no offset
    DLQ = "DLQ"  # Non-resumable failure - mark DLQ, no offset advance
    SKIP = "SKIP"  # No action needed (e.g., already committed)


# =============================================================================
# OFFSET DECISION RESULT
# =============================================================================


@dataclass
class OffsetDecision:
    """
    Decision about what offset action to take.

    Encapsulates the logic from Issue 1.2.6 spec:
    - COMMIT: Cycle completed successfully (R8 DONE)
    - CHECKPOINT_ONLY: Cycle aborted at resumable phase
    - DLQ: Cycle aborted at non-resumable phase
    - SKIP: Already processed (idempotent retry)

    Attributes:
        action: The offset action to take
        reason: Human-readable reason for the decision
        phase_id: Phase where decision was made
        phase_status: Status at decision point
        offset_value: WAL position to commit (if action=COMMIT)
        checkpoint: Checkpoint to persist (if action=CHECKPOINT_ONLY)
        idempotent: True if this is a detected retry of same cycle
    """

    action: OffsetAction
    reason: str
    phase_id: Optional[P03PhaseId] = None
    phase_status: Optional[P03PhaseStatus] = None
    offset_value: Optional[int] = None
    checkpoint: Optional[P03Checkpoint] = None
    idempotent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        result: Dict[str, Any] = {
            "action": self.action.value,
            "reason": self.reason,
            "idempotent": self.idempotent,
        }
        if self.phase_id:
            result["phase_id"] = self.phase_id.value
        if self.phase_status:
            result["phase_status"] = self.phase_status.value
        if self.offset_value is not None:
            result["offset_value"] = self.offset_value
        return result


# =============================================================================
# OFFSET STORE PROTOCOL (FOR TESTING)
# =============================================================================


@runtime_checkable
class OffsetStoreProtocol(Protocol):
    """
    Protocol for offset storage.

    Matches K0's OffsetStore interface for compatibility.
    """

    async def upsert(
        self,
        record: Any,  # Offset
        *,
        connection: Any = None,
    ) -> None:
        """Upsert an offset record."""
        ...

    async def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: Any = None,
    ) -> Any:  # Optional[Offset]
        """Fetch an offset record."""
        ...


# =============================================================================
# IN-MEMORY OFFSET STORE (FOR TESTING)
# =============================================================================


@dataclass
class InMemoryOffset:
    """In-memory offset record for testing."""

    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int
    updated_ts: str


class InMemoryOffsetStore:
    """
    In-memory offset store for testing.

    Compatible with K0's OffsetStore interface.
    """

    def __init__(self) -> None:
        """Initialize empty store."""
        self._offsets: Dict[str, InMemoryOffset] = {}

    def _make_key(self, subscriber_id: str, topic: str, space_id: str, tenant_id: str) -> str:
        """Create composite key."""
        return f"{subscriber_id}:{topic}:{space_id}:{tenant_id}"

    async def upsert(
        self,
        record: InMemoryOffset,
        *,
        connection: Any = None,
    ) -> None:
        """Upsert an offset record."""
        key = self._make_key(
            record.subscriber_id,
            record.topic,
            record.space_id,
            record.tenant_id,
        )
        self._offsets[key] = record

    async def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: Any = None,
    ) -> Optional[InMemoryOffset]:
        """Fetch an offset record."""
        key = self._make_key(subscriber_id, topic, space_id, tenant_id)
        return self._offsets.get(key)

    def clear(self) -> None:
        """Clear all offsets (for test cleanup)."""
        self._offsets.clear()

    @property
    def count(self) -> int:
        """Return number of stored offsets."""
        return len(self._offsets)

    def get_all(self) -> Dict[str, InMemoryOffset]:
        """Return all offsets (for testing)."""
        return dict(self._offsets)


# =============================================================================
# P03 OFFSET MANAGER
# =============================================================================


class P03OffsetManager:
    """
    Manages offset/watermark persistence for P03 pipeline.

    Responsibilities:
    - Determine offset action based on cycle result
    - Write offsets only on successful cycle completion
    - Ensure idempotency for retry safety
    - Support both UoW (atomic) and standalone modes

    Usage (Standalone):
        manager = P03OffsetManager(offset_store=my_store)
        decision = manager.decide_action(cycle_result, envelope)
        if decision.action == OffsetAction.COMMIT:
            await manager.commit_offset(decision, envelope)

    Usage (With UoW):
        async with uow:
            decision = manager.decide_action(cycle_result, envelope)
            if decision.action == OffsetAction.COMMIT:
                await manager.commit_offset_in_uow(decision, envelope, uow)
    """

    def __init__(
        self,
        offset_store: Optional[OffsetStoreProtocol] = None,
        *,
        subscriber_id: str = P03_SUBSCRIBER_ID,
        topic: str = P03_SOURCE_TOPIC,
        check_idempotency: bool = True,
    ):
        """
        Initialize the offset manager.

        Args:
            offset_store: Optional offset store for standalone mode
            subscriber_id: Pipeline identifier (default: P03_CONSOLIDATE)
            topic: Source topic (default: st_hipp_events)
            check_idempotency: Whether to check for duplicate offset writes
        """
        self._offset_store = offset_store
        self._subscriber_id = subscriber_id
        self._topic = topic
        self._check_idempotency = check_idempotency
        self._committed_cycles: Dict[str, int] = {}  # cycle_id -> offset (for idempotency)

    @property
    def subscriber_id(self) -> str:
        """Return subscriber ID."""
        return self._subscriber_id

    @property
    def topic(self) -> str:
        """Return topic."""
        return self._topic

    # =========================================================================
    # DECISION LOGIC
    # =========================================================================

    def decide_action(
        self,
        cycle_result: "P03CycleResult",
        envelope: "P03BatchEnvelope",
        *,
        last_wal_pos: Optional[int] = None,
    ) -> OffsetDecision:
        """
        Decide what offset action to take based on cycle result.

        Logic from Issue 1.2.6 spec:
        - Cycle completes (R8 DONE): COMMIT offset
        - Cycle aborts, resumable phase: CHECKPOINT_ONLY
        - Cycle aborts, non-resumable: DLQ

        Args:
            cycle_result: Result from P03SequentialRunner.run()
            envelope: The batch envelope
            last_wal_pos: WAL position for offset tracking (required for COMMIT)

        Returns:
            OffsetDecision with action and metadata
        """
        cycle_id = cycle_result.cycle_id

        # Check idempotency first
        if self._check_idempotency and cycle_id in self._committed_cycles:
            return OffsetDecision(
                action=OffsetAction.SKIP,
                reason=f"Cycle {cycle_id} already committed",
                idempotent=True,
                offset_value=self._committed_cycles[cycle_id],
            )

        # Use provided WAL position
        wal_pos = last_wal_pos

        # Check for successful completion (R8 DONE)
        if cycle_result.is_success:
            if wal_pos is None:
                return OffsetDecision(
                    action=OffsetAction.SKIP,
                    reason="No WAL position available for commit",
                    phase_id=P03PhaseId.R8_EMIT,
                    phase_status=P03PhaseStatus.DONE,
                )

            return OffsetDecision(
                action=OffsetAction.COMMIT,
                reason="Cycle completed successfully (R8 DONE)",
                phase_id=P03PhaseId.R8_EMIT,
                phase_status=P03PhaseStatus.DONE,
                offset_value=wal_pos,
            )

        # Cycle failed - check if resumable
        failed_phase = cycle_result.final_phase

        if failed_phase is None:
            # Should not happen, but handle gracefully
            return OffsetDecision(
                action=OffsetAction.DLQ,
                reason="Cycle failed with no identified phase",
            )

        # Check if failed phase is resumable
        from k0.pipelines.p03.runner_contract import RESUME_MATRIX

        resume_point = RESUME_MATRIX.get(failed_phase)

        if resume_point is not None and resume_point.can_resume:
            # Resumable - checkpoint only, do NOT advance offset
            checkpoint = P03Checkpoint.create(
                cycle_id=cycle_id,
                batch_id=cycle_result.batch_id,
                space_id=envelope.context.space_id,
                tenant_id=envelope.context.tenant_id,
                phase_id=failed_phase,
                phase_status=P03PhaseStatus.FAIL,
                last_wal_pos=wal_pos,
                last_event_id=(
                    envelope.context.event_ids[-1] if envelope.context.event_ids else None
                ),
                event_ids=list(envelope.context.event_ids),
                errors=[{"dlq_reason": cycle_result.dlq_reason}] if cycle_result.dlq_reason else [],
            )

            return OffsetDecision(
                action=OffsetAction.CHECKPOINT_ONLY,
                reason=f"Cycle aborted at resumable phase {failed_phase.value}, resume from {resume_point.resume_from.value}",
                phase_id=failed_phase,
                phase_status=P03PhaseStatus.FAIL,
                checkpoint=checkpoint,
            )

        # Non-resumable - DLQ
        return OffsetDecision(
            action=OffsetAction.DLQ,
            reason=f"Cycle aborted at non-resumable phase {failed_phase.value}",
            phase_id=failed_phase,
            phase_status=P03PhaseStatus.FAIL,
        )

    # =========================================================================
    # OFFSET COMMIT (STANDALONE MODE)
    # =========================================================================

    async def commit_offset(
        self,
        decision: OffsetDecision,
        envelope: "P03BatchEnvelope",
        *,
        check_existing: bool = True,
    ) -> bool:
        """
        Commit offset using standalone offset store.

        This is the simple mode without UnitOfWork atomicity.
        For atomic writes with R7 persistence, use commit_offset_in_uow().

        Args:
            decision: OffsetDecision from decide_action()
            envelope: The batch envelope
            check_existing: Whether to check if offset already exists

        Returns:
            True if offset was written, False if skipped

        Raises:
            OffsetWriteError: If offset store is not configured
            OffsetIdempotencyError: If offset already written (and check_existing=True)
        """
        if decision.action != OffsetAction.COMMIT:
            return False

        if self._offset_store is None:
            raise OffsetWriteError(
                "No offset store configured for standalone mode",
                cycle_id=envelope.context.cycle_id,
            )

        if decision.offset_value is None:
            raise OffsetWriteError(
                "No offset value in decision",
                cycle_id=envelope.context.cycle_id,
            )

        # Check for existing offset (idempotency)
        if check_existing:
            existing = await self._offset_store.fetch(
                subscriber_id=self._subscriber_id,
                topic=self._topic,
                space_id=envelope.context.space_id,
                tenant_id=envelope.context.tenant_id,
            )

            if existing and existing.offset >= decision.offset_value:
                # Already committed at same or higher offset
                self._committed_cycles[envelope.context.cycle_id] = existing.offset
                return False

        # Create offset record
        offset_record = InMemoryOffset(
            subscriber_id=self._subscriber_id,
            topic=self._topic,
            space_id=envelope.context.space_id,
            tenant_id=envelope.context.tenant_id,
            offset=decision.offset_value,
            updated_ts=_format_timestamp_ms(int(time.time() * 1000)),
        )

        await self._offset_store.upsert(offset_record)

        # Track for idempotency
        self._committed_cycles[envelope.context.cycle_id] = decision.offset_value

        return True

    # =========================================================================
    # OFFSET COMMIT (UoW MODE)
    # =========================================================================

    async def commit_offset_in_uow(
        self,
        decision: OffsetDecision,
        envelope: "P03BatchEnvelope",
        uow: "UnitOfWork",
    ) -> bool:
        """
        Commit offset within a UnitOfWork transaction.

        This provides atomic commit with R7 writes for exactly-once semantics.
        The offset is written as part of the UoW transaction.

        Args:
            decision: OffsetDecision from decide_action()
            envelope: The batch envelope
            uow: Active UnitOfWork context

        Returns:
            True if offset was staged for commit, False if skipped

        Raises:
            OffsetWriteError: If decision has no offset value
        """
        if decision.action != OffsetAction.COMMIT:
            return False

        if decision.offset_value is None:
            raise OffsetWriteError(
                "No offset value in decision",
                cycle_id=envelope.context.cycle_id,
            )

        # Import K0 Offset type
        from k0.storage.offsets import Offset

        # Create K0 Offset record
        offset_record = Offset(
            subscriber_id=self._subscriber_id,
            topic=self._topic,
            space_id=envelope.context.space_id,
            tenant_id=envelope.context.tenant_id,
            offset=decision.offset_value,
            updated_ts=_format_timestamp_ms(int(time.time() * 1000)),
        )

        # Use UoW's upsert_offset method
        await uow.upsert_offset(offset_record)

        # Track for idempotency
        self._committed_cycles[envelope.context.cycle_id] = decision.offset_value

        return True

    # =========================================================================
    # OFFSET QUERY
    # =========================================================================

    async def get_current_offset(
        self,
        space_id: str,
        tenant_id: str,
    ) -> Optional[int]:
        """
        Get current offset for a space/tenant.

        Args:
            space_id: Space identifier
            tenant_id: Tenant identifier

        Returns:
            Current offset value or None if not found
        """
        if self._offset_store is None:
            return None

        existing = await self._offset_store.fetch(
            subscriber_id=self._subscriber_id,
            topic=self._topic,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        return existing.offset if existing else None

    # =========================================================================
    # IDEMPOTENCY
    # =========================================================================

    def is_cycle_committed(self, cycle_id: str) -> bool:
        """Check if a cycle has already been committed."""
        return cycle_id in self._committed_cycles

    def get_committed_offset(self, cycle_id: str) -> Optional[int]:
        """Get the committed offset for a cycle (if any)."""
        return self._committed_cycles.get(cycle_id)

    def clear_idempotency_cache(self) -> None:
        """Clear the in-memory idempotency cache."""
        self._committed_cycles.clear()

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            "subscriber_id": self._subscriber_id,
            "topic": self._topic,
            "check_idempotency": self._check_idempotency,
            "committed_cycles_count": len(self._committed_cycles),
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_timestamp_ms(ms: int) -> str:
    """Format milliseconds timestamp as ISO string."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat()


def create_offset_from_checkpoint(
    checkpoint: P03Checkpoint,
    *,
    subscriber_id: str = P03_SUBSCRIBER_ID,
    topic: str = P03_SOURCE_TOPIC,
) -> Optional[P03Offset]:
    """
    Create P03Offset from a checkpoint.

    Convenience wrapper around P03Offset.from_checkpoint().

    Args:
        checkpoint: Source checkpoint
        subscriber_id: Override subscriber ID
        topic: Override topic

    Returns:
        P03Offset if checkpoint has WAL position, None otherwise
    """
    offset = P03Offset.from_checkpoint(checkpoint)
    if offset is None:
        return None

    # Apply overrides if different
    if subscriber_id != P03_SUBSCRIBER_ID or topic != P03_SOURCE_TOPIC:
        return P03Offset(
            subscriber_id=subscriber_id,
            topic=topic,
            space_id=offset.space_id,
            tenant_id=offset.tenant_id,
            offset=offset.offset,
            updated_ts=offset.updated_ts,
        )

    return offset


def should_advance_offset(
    cycle_result: "P03CycleResult",
) -> bool:
    """
    Quick check if offset should be advanced based on cycle result.

    Args:
        cycle_result: Result from runner

    Returns:
        True only if cycle completed successfully (R8 DONE)
    """
    return cycle_result.is_success
