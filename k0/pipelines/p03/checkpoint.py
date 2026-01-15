"""
P03 Checkpoint Contract - Envelope snapshot and persistence hooks.

This module defines the checkpoint contract for P03 runner-level checkpointing,
enabling recovery from failures and offset management.

Issue Reference: M1_EXECUTION.md Issue 1.2.5
Spec Reference: docs/pipelines/P03_consolidation_dossier_v2.md section 4.9.2, 6.14

Key Concepts:
- P03Checkpoint: Full checkpoint state at phase boundary
- CheckpointStore: Protocol for persisting/loading checkpoints
- Compatible with K0's OffsetStore patterns (subscriber_id, topic, offset)

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k0.pipelines.p03.context import generate_ulid
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

# =============================================================================
# CONSTANTS
# =============================================================================

# Pipeline identifier for offset storage
P03_SUBSCRIBER_ID = "P03_CONSOLIDATE"

# Default topic for P03 checkpoints
P03_CHECKPOINT_TOPIC = "p03_checkpoints"

# Source topic for P03 ingestion
P03_SOURCE_TOPIC = "st_hipp_events"


# =============================================================================
# P03 CHECKPOINT DATACLASS
# =============================================================================


@dataclass
class P03Checkpoint:
    """
    Checkpoint state at a phase boundary.

    Captures all information needed to:
    - Resume execution from a specific phase
    - Track offset/watermark for exactly-once processing
    - Audit and debug pipeline execution

    Attributes:
        checkpoint_id: ULID for this checkpoint (unique identifier)
        cycle_id: ULID of the cycle being checkpointed
        batch_id: Batch identifier (deterministic hash of event_ids)
        space_id: Space identifier
        tenant_id: Tenant identifier
        phase_id: Phase at checkpoint (R0-R8)
        phase_status: Status at checkpoint (DONE, SKIP, FAIL)
        created_at_ms: Checkpoint creation timestamp (unix ms)
        envelope_summary: Compact envelope summary for logging/metrics
        envelope_full: Full envelope snapshot (optional, for recovery)
        last_wal_pos: Last processed WAL position (for offset tracking)
        last_event_id: Last processed event ID in batch
        event_ids: All event IDs in batch (for idempotency)
        errors: List of error summaries if any
        metadata: Additional metadata (flexible)
    """

    checkpoint_id: str
    cycle_id: str
    batch_id: str
    space_id: str
    tenant_id: str
    phase_id: P03PhaseId
    phase_status: P03PhaseStatus
    created_at_ms: int
    envelope_summary: Dict[str, Any] = field(default_factory=dict)
    envelope_full: Optional[Dict[str, Any]] = None
    last_wal_pos: Optional[int] = None
    last_event_id: Optional[str] = None
    event_ids: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # FACTORY METHODS
    # =========================================================================

    @classmethod
    def create(
        cls,
        cycle_id: str,
        batch_id: str,
        space_id: str,
        tenant_id: str,
        phase_id: P03PhaseId,
        phase_status: P03PhaseStatus,
        *,
        envelope_summary: Optional[Dict[str, Any]] = None,
        envelope_full: Optional[Dict[str, Any]] = None,
        last_wal_pos: Optional[int] = None,
        last_event_id: Optional[str] = None,
        event_ids: Optional[List[str]] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> P03Checkpoint:
        """
        Factory for creating checkpoints.

        Args:
            cycle_id: ULID of the cycle
            batch_id: Batch identifier
            space_id: Space identifier
            tenant_id: Tenant identifier
            phase_id: Current phase
            phase_status: Current phase status
            envelope_summary: Compact envelope summary
            envelope_full: Full envelope snapshot (optional)
            last_wal_pos: Last WAL position processed
            last_event_id: Last event ID processed
            event_ids: All event IDs in batch
            errors: List of errors
            metadata: Additional metadata

        Returns:
            New P03Checkpoint instance
        """
        return cls(
            checkpoint_id=generate_ulid(),
            cycle_id=cycle_id,
            batch_id=batch_id,
            space_id=space_id,
            tenant_id=tenant_id,
            phase_id=phase_id,
            phase_status=phase_status,
            created_at_ms=_now_ms(),
            envelope_summary=envelope_summary or {},
            envelope_full=envelope_full,
            last_wal_pos=last_wal_pos,
            last_event_id=last_event_id,
            event_ids=list(event_ids) if event_ids else [],
            errors=list(errors) if errors else [],
            metadata=metadata or {},
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> P03Checkpoint:
        """
        Reconstruct checkpoint from dictionary.

        Args:
            data: Dictionary from to_dict()

        Returns:
            P03Checkpoint instance
        """
        return cls(
            checkpoint_id=data["checkpoint_id"],
            cycle_id=data["cycle_id"],
            batch_id=data["batch_id"],
            space_id=data["space_id"],
            tenant_id=data["tenant_id"],
            phase_id=P03PhaseId(data["phase_id"]),
            phase_status=P03PhaseStatus(data["phase_status"]),
            created_at_ms=data["created_at_ms"],
            envelope_summary=data.get("envelope_summary", {}),
            envelope_full=data.get("envelope_full"),
            last_wal_pos=data.get("last_wal_pos"),
            last_event_id=data.get("last_event_id"),
            event_ids=data.get("event_ids", []),
            errors=data.get("errors", []),
            metadata=data.get("metadata", {}),
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to JSON-serializable dictionary.

        Returns:
            Dictionary suitable for JSON serialization
        """
        result: Dict[str, Any] = {
            "checkpoint_id": self.checkpoint_id,
            "cycle_id": self.cycle_id,
            "batch_id": self.batch_id,
            "space_id": self.space_id,
            "tenant_id": self.tenant_id,
            "phase_id": self.phase_id.value,
            "phase_status": self.phase_status.value,
            "created_at_ms": self.created_at_ms,
            "envelope_summary": self.envelope_summary,
        }

        # Include optional fields only if set
        if self.envelope_full is not None:
            result["envelope_full"] = self.envelope_full
        if self.last_wal_pos is not None:
            result["last_wal_pos"] = self.last_wal_pos
        if self.last_event_id is not None:
            result["last_event_id"] = self.last_event_id
        if self.event_ids:
            result["event_ids"] = self.event_ids
        if self.errors:
            result["errors"] = self.errors
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Convert to compact summary for logging.

        Returns:
            Minimal dictionary for logging/metrics
        """
        return {
            "checkpoint_id": self.checkpoint_id,
            "cycle_id": self.cycle_id,
            "batch_id": self.batch_id,
            "phase_id": self.phase_id.value,
            "phase_status": self.phase_status.value,
            "created_at_ms": self.created_at_ms,
            "event_count": len(self.event_ids),
            "error_count": len(self.errors),
        }

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def is_terminal(self) -> bool:
        """Check if this checkpoint is at a terminal state."""
        return self.phase_id == P03PhaseId.R8_EMIT and self.phase_status == P03PhaseStatus.DONE

    @property
    def is_failed(self) -> bool:
        """Check if this checkpoint represents a failed state."""
        return self.phase_status == P03PhaseStatus.FAIL

    @property
    def is_resumable(self) -> bool:
        """Check if execution can be resumed from this checkpoint."""
        # Cannot resume from terminal or failed states
        if self.is_terminal or self.is_failed:
            return False
        # Can resume from completed phases (except R8)
        return self.phase_status == P03PhaseStatus.DONE

    @property
    def resume_phase(self) -> Optional[P03PhaseId]:
        """
        Get the phase to resume from.

        For most phases, resume from the next phase.
        For R7 failures, resume from R6 (re-stage).

        Returns:
            Phase to resume from, or None if not resumable
        """
        if not self.is_resumable:
            return None

        # Resume from next phase after completed phase
        return self.phase_id.next_phase()


# =============================================================================
# CHECKPOINT STORE PROTOCOL
# =============================================================================


@runtime_checkable
class CheckpointStoreProtocol(Protocol):
    """
    Protocol for checkpoint persistence.

    Implementations can store checkpoints in:
    - PostgreSQL (recommended for production)
    - SQLite (for testing)
    - In-memory (for unit tests)
    """

    async def save(self, checkpoint: P03Checkpoint) -> None:
        """
        Persist a checkpoint.

        Args:
            checkpoint: Checkpoint to save

        Raises:
            CheckpointSaveError: If save fails
        """
        ...

    async def load_latest(
        self,
        space_id: str,
        tenant_id: str,
        *,
        batch_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> Optional[P03Checkpoint]:
        """
        Load the most recent checkpoint.

        Args:
            space_id: Space identifier
            tenant_id: Tenant identifier
            batch_id: Optional batch ID filter
            cycle_id: Optional cycle ID filter

        Returns:
            Most recent checkpoint, or None if not found
        """
        ...

    async def load_by_cycle(
        self,
        cycle_id: str,
    ) -> Optional[P03Checkpoint]:
        """
        Load checkpoint by cycle ID.

        Args:
            cycle_id: Cycle identifier

        Returns:
            Checkpoint for cycle, or None if not found
        """
        ...

    async def delete(
        self,
        checkpoint_id: str,
    ) -> bool:
        """
        Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint to delete

        Returns:
            True if deleted, False if not found
        """
        ...


class CheckpointStoreBase(ABC):
    """
    Abstract base class for checkpoint stores.

    Provides default implementations where possible.
    """

    @abstractmethod
    async def save(self, checkpoint: P03Checkpoint) -> None:
        """Persist a checkpoint."""
        pass

    @abstractmethod
    async def load_latest(
        self,
        space_id: str,
        tenant_id: str,
        *,
        batch_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> Optional[P03Checkpoint]:
        """Load the most recent checkpoint."""
        pass

    @abstractmethod
    async def load_by_cycle(
        self,
        cycle_id: str,
    ) -> Optional[P03Checkpoint]:
        """Load checkpoint by cycle ID."""
        pass

    @abstractmethod
    async def delete(
        self,
        checkpoint_id: str,
    ) -> bool:
        """Delete a checkpoint."""
        pass


# =============================================================================
# IN-MEMORY CHECKPOINT STORE (FOR TESTING)
# =============================================================================


class InMemoryCheckpointStore(CheckpointStoreBase):
    """
    In-memory checkpoint store for testing.

    Thread-safe for single-threaded async usage.
    """

    def __init__(self) -> None:
        """Initialize empty store."""
        self._checkpoints: Dict[str, P03Checkpoint] = {}
        self._by_cycle: Dict[str, str] = {}  # cycle_id -> checkpoint_id

    async def save(self, checkpoint: P03Checkpoint) -> None:
        """Save checkpoint to memory."""
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        self._by_cycle[checkpoint.cycle_id] = checkpoint.checkpoint_id

    async def load_latest(
        self,
        space_id: str,
        tenant_id: str,
        *,
        batch_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> Optional[P03Checkpoint]:
        """Load most recent matching checkpoint."""
        matching = [
            cp
            for cp in self._checkpoints.values()
            if cp.space_id == space_id and cp.tenant_id == tenant_id
        ]

        if batch_id:
            matching = [cp for cp in matching if cp.batch_id == batch_id]
        if cycle_id:
            matching = [cp for cp in matching if cp.cycle_id == cycle_id]

        if not matching:
            return None

        # Return most recent by created_at_ms
        return max(matching, key=lambda cp: cp.created_at_ms)

    async def load_by_cycle(
        self,
        cycle_id: str,
    ) -> Optional[P03Checkpoint]:
        """Load checkpoint by cycle ID."""
        checkpoint_id = self._by_cycle.get(cycle_id)
        if checkpoint_id:
            return self._checkpoints.get(checkpoint_id)
        return None

    async def delete(
        self,
        checkpoint_id: str,
    ) -> bool:
        """Delete checkpoint from memory."""
        if checkpoint_id in self._checkpoints:
            checkpoint = self._checkpoints.pop(checkpoint_id)
            if checkpoint.cycle_id in self._by_cycle:
                if self._by_cycle[checkpoint.cycle_id] == checkpoint_id:
                    del self._by_cycle[checkpoint.cycle_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all checkpoints (for test cleanup)."""
        self._checkpoints.clear()
        self._by_cycle.clear()

    @property
    def count(self) -> int:
        """Return number of stored checkpoints."""
        return len(self._checkpoints)


# =============================================================================
# CHECKPOINT ERRORS
# =============================================================================


class CheckpointError(Exception):
    """Base error for checkpoint operations."""

    pass


class CheckpointSaveError(CheckpointError):
    """Failed to save checkpoint."""

    def __init__(self, checkpoint_id: str, reason: str):
        self.checkpoint_id = checkpoint_id
        self.reason = reason
        super().__init__(f"Failed to save checkpoint {checkpoint_id}: {reason}")


class CheckpointLoadError(CheckpointError):
    """Failed to load checkpoint."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Failed to load checkpoint: {reason}")


class CheckpointNotFoundError(CheckpointError):
    """Checkpoint not found."""

    def __init__(self, identifier: str):
        self.identifier = identifier
        super().__init__(f"Checkpoint not found: {identifier}")


# =============================================================================
# OFFSET INTEGRATION HELPERS
# =============================================================================


@dataclass
class P03Offset:
    """
    Offset representation for P03 pipeline.

    Compatible with K0's OffsetStore patterns.

    Attributes:
        subscriber_id: Pipeline identifier (P03_CONSOLIDATE)
        topic: Source topic (st_hipp_events)
        space_id: Space identifier
        tenant_id: Tenant identifier
        offset: Last processed WAL position
        updated_ts: Last update timestamp (ISO format)
    """

    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int
    updated_ts: str

    @classmethod
    def from_checkpoint(cls, checkpoint: P03Checkpoint) -> Optional["P03Offset"]:
        """
        Create offset from checkpoint.

        Args:
            checkpoint: Source checkpoint

        Returns:
            P03Offset if checkpoint has WAL position, None otherwise
        """
        if checkpoint.last_wal_pos is None:
            return None

        return cls(
            subscriber_id=P03_SUBSCRIBER_ID,
            topic=P03_SOURCE_TOPIC,
            space_id=checkpoint.space_id,
            tenant_id=checkpoint.tenant_id,
            offset=checkpoint.last_wal_pos,
            updated_ts=_format_timestamp(checkpoint.created_at_ms),
        )

    def to_k0_offset(self) -> Dict[str, Any]:
        """
        Convert to K0 OffsetStore compatible format.

        Returns:
            Dictionary compatible with k0.storage.offsets.Offset
        """
        return {
            "subscriber_id": self.subscriber_id,
            "topic": self.topic,
            "space_id": self.space_id,
            "tenant_id": self.tenant_id,
            "offset": self.offset,
            "updated_ts": self.updated_ts,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _now_ms() -> int:
    """Return current time in milliseconds since epoch."""
    return int(time.time() * 1000)


def _format_timestamp(ms: int) -> str:
    """Format milliseconds timestamp as ISO string."""
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat()


def create_checkpoint_from_envelope(
    envelope: Any,  # P03BatchEnvelope (avoid circular import)
    phase_id: P03PhaseId,
    phase_status: P03PhaseStatus,
    *,
    include_full_envelope: bool = False,
    last_wal_pos: Optional[int] = None,
    last_event_id: Optional[str] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> P03Checkpoint:
    """
    Create checkpoint from envelope state.

    Args:
        envelope: P03BatchEnvelope instance
        phase_id: Current phase
        phase_status: Current phase status
        include_full_envelope: Whether to include full envelope snapshot
        last_wal_pos: Last WAL position (for offset tracking)
        last_event_id: Last event ID processed
        errors: List of errors to include

    Returns:
        P03Checkpoint instance
    """
    # Build envelope summary
    envelope_summary = {
        "cycle_id": envelope.context.cycle_id,
        "batch_id": envelope.context.batch_id,
        "batch_size": envelope.context.batch_size,
        "current_phase": phase_id.value,
        "events_processed": len(envelope.events),
        "staged_writes_count": envelope.staged.total_writes(),
        "error_count": len(envelope.observability.errors) if envelope.observability else 0,
    }

    # Build full envelope if requested
    envelope_full = None
    if include_full_envelope:
        # Import here to avoid circular dependency
        from k0.pipelines.p03.serializer import P03EnvelopeSerializer

        envelope_full = P03EnvelopeSerializer.to_full_dict(envelope)

    return P03Checkpoint.create(
        cycle_id=envelope.context.cycle_id,
        batch_id=envelope.context.batch_id,
        space_id=envelope.context.space_id,
        tenant_id=envelope.context.tenant_id,
        phase_id=phase_id,
        phase_status=phase_status,
        envelope_summary=envelope_summary,
        envelope_full=envelope_full,
        last_wal_pos=last_wal_pos,
        last_event_id=last_event_id
        or (envelope.context.event_ids[-1] if envelope.context.event_ids else None),
        event_ids=list(envelope.context.event_ids),
        errors=errors,
    )
