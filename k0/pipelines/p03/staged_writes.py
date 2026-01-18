"""
P03StagedWrites - Deferred write accumulator for atomic commit.

This module implements the staged writes container that accumulates
database operations during R1-R6, to be committed atomically by R7.

Spec Reference: docs/pipelines/P03_envelope_fields_discovery.md section 18.1

DESIGN DECISIONS:
    - Writes grouped by layer for batch execution efficiency
    - Idempotency keys computed deterministically for retry safety
    - Dependency order defined for foreign key constraints
    - Not frozen: phases append writes throughout execution

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .context import generate_ulid

if TYPE_CHECKING:
    from k0.modules.consolidation.algorithms.observation_context import (
        ObservationContext,
    )

# =============================================================================
# WRITE OPERATION ENUM
# =============================================================================


class WriteOperation(Enum):
    """
    Types of write operations for staged writes.

    Each operation maps to specific SQL semantics:
    - INSERT: Create new record (fails if exists)
    - UPDATE: Modify existing record (uses optimistic locking)
    - ARCHIVE: Soft-delete with timestamp (sets archived_at)
    - TOMBSTONE: Hard-delete marker for sync propagation
    """

    INSERT = "INSERT"
    UPDATE = "UPDATE"
    ARCHIVE = "ARCHIVE"
    TOMBSTONE = "TOMBSTONE"


# =============================================================================
# STAGED WRITE DATACLASS
# =============================================================================


@dataclass
class StagedWrite:
    """
    A single deferred write operation.

    Writes are accumulated during R1-R6 but not executed.
    R7 commits all staged writes atomically via UnitOfWork.

    Attributes:
        write_id: ULID for tracking and debugging
        layer: Target table (st_epi, st_sem, st_kg_dom, etc.)
        operation: Type of write (INSERT/UPDATE/ARCHIVE/TOMBSTONE)
        record_id: Primary key of the target record
        record_data: Full record data for INSERT/UPDATE operations
        idempotency_key: Deterministic key for retry safety
        source_phase: Phase that created this write (R1-R6)
        source_event_ids: Contributing event IDs for provenance
        expected_version: For optimistic locking on UPDATE
        created_at_ms: Timestamp when write was staged (MILLISECONDS)
        observation_context: Holistic context for observation recording (Issue 7.5)
    """

    write_id: str
    layer: str
    operation: WriteOperation
    record_id: str
    record_data: Dict[str, Any]
    idempotency_key: str
    source_phase: str
    source_event_ids: List[str] = field(default_factory=list)
    expected_version: Optional[int] = None
    created_at_ms: int = field(default_factory=lambda: _now_ms())
    observation_context: Optional["ObservationContext"] = None

    @classmethod
    def insert(
        cls,
        layer: str,
        record_id: str,
        data: Dict[str, Any],
        phase: str,
        event_ids: Optional[List[str]] = None,
    ) -> StagedWrite:
        """
        Factory for INSERT write.

        Args:
            layer: Target table (st_epi, st_sem, etc.)
            record_id: Primary key for new record
            data: Full record data
            phase: Source phase (R1-R6)
            event_ids: Contributing events for provenance

        Returns:
            StagedWrite configured for INSERT
        """
        return cls(
            write_id=generate_ulid(),
            layer=layer,
            operation=WriteOperation.INSERT,
            record_id=record_id,
            record_data=data,
            idempotency_key=f"{phase}:{layer}:{record_id}",
            source_phase=phase,
            source_event_ids=event_ids or [],
        )

    @classmethod
    def update(
        cls,
        layer: str,
        record_id: str,
        data: Dict[str, Any],
        phase: str,
        expected_version: int,
        event_ids: Optional[List[str]] = None,
    ) -> StagedWrite:
        """
        Factory for UPDATE write with optimistic locking.

        Args:
            layer: Target table
            record_id: Primary key of existing record
            data: Fields to update (may be partial)
            phase: Source phase (R1-R6)
            expected_version: Current version for optimistic lock
            event_ids: Contributing events for provenance

        Returns:
            StagedWrite configured for UPDATE with version check
        """
        return cls(
            write_id=generate_ulid(),
            layer=layer,
            operation=WriteOperation.UPDATE,
            record_id=record_id,
            record_data=data,
            idempotency_key=f"{phase}:{layer}:{record_id}:v{expected_version}",
            source_phase=phase,
            expected_version=expected_version,
            source_event_ids=event_ids or [],
        )

    @classmethod
    def archive(
        cls,
        layer: str,
        record_id: str,
        phase: str,
        reason: str = "",
        event_ids: Optional[List[str]] = None,
    ) -> StagedWrite:
        """
        Factory for ARCHIVE (soft-delete) write.

        Args:
            layer: Target table
            record_id: Primary key of record to archive
            phase: Source phase (R3 typically)
            reason: Reason for archival (decay, duplicate, etc.)
            event_ids: Contributing events

        Returns:
            StagedWrite configured for ARCHIVE
        """
        return cls(
            write_id=generate_ulid(),
            layer=layer,
            operation=WriteOperation.ARCHIVE,
            record_id=record_id,
            record_data={"archived_reason": reason},
            idempotency_key=f"{phase}:{layer}:{record_id}:archive",
            source_phase=phase,
            source_event_ids=event_ids or [],
        )

    @classmethod
    def tombstone(
        cls,
        layer: str,
        record_id: str,
        phase: str,
        event_ids: Optional[List[str]] = None,
    ) -> StagedWrite:
        """
        Factory for TOMBSTONE (hard-delete marker) write.

        Args:
            layer: Target table
            record_id: Primary key of record to tombstone
            phase: Source phase
            event_ids: Contributing events

        Returns:
            StagedWrite configured for TOMBSTONE
        """
        return cls(
            write_id=generate_ulid(),
            layer=layer,
            operation=WriteOperation.TOMBSTONE,
            record_id=record_id,
            record_data={},
            idempotency_key=f"{phase}:{layer}:{record_id}:tombstone",
            source_phase=phase,
            source_event_ids=event_ids or [],
        )


# =============================================================================
# STAGED OUTBOX EVENT
# =============================================================================


@dataclass
class StagedOutboxEvent:
    """
    Outbox event to be published after R7 commit.

    Events are staged during phases but only emitted by R8 after
    successful database commit to ensure consistency.

    Issue 8.1.13: Added idempotency_key for deterministic deduplication.

    Attributes:
        event_id: ULID for the outbox event
        topic: Event topic for publication (e.g., "p03.cycle.completed")
        payload: Event payload data
        source_phase: Phase that created this event
        idempotency_key: Deterministic key for deduplication (Issue 8.1.13)
        priority: Event priority (lower = higher priority, default 50)
        created_at_ms: Timestamp when event was staged (MILLISECONDS)
    """

    event_id: str
    topic: str
    payload: Dict[str, Any]
    source_phase: str
    idempotency_key: str  # Issue 8.1.13: Required for A.0.5 invariant
    priority: int = 50
    created_at_ms: int = field(default_factory=lambda: _now_ms())

    @classmethod
    def create(
        cls,
        topic: str,
        payload: Dict[str, Any],
        phase: str,
        priority: int = 50,
        idempotency_key: Optional[str] = None,
    ) -> StagedOutboxEvent:
        """
        Factory for outbox events.

        Issue 8.1.13: Added idempotency_key parameter.

        Args:
            topic: Event topic
            payload: Event payload
            phase: Source phase (R4, R5, R8 typically)
            priority: Event priority (default 50)
            idempotency_key: Deterministic key for deduplication.
                             If not provided, generates from event_id (non-deterministic).

        Returns:
            StagedOutboxEvent ready for staging
        """
        event_id = generate_ulid()
        # Issue 8.1.13: Use provided key or fallback to event_id-based key
        # Prefer explicit deterministic keys for retry safety
        idem_key = idempotency_key if idempotency_key else f"{phase}:event:{event_id}"
        return cls(
            event_id=event_id,
            topic=topic,
            payload=payload,
            source_phase=phase,
            idempotency_key=idem_key,
            priority=priority,
        )


# =============================================================================
# STAGED WRITES CONTAINER
# =============================================================================


# Layer names as constants for type safety
LAYER_ST_EPI = "st_epi"
LAYER_ST_SEM = "st_sem"
LAYER_ST_PROCEDURAL = "st_procedural"
LAYER_ST_SOCIAL = "st_social"
LAYER_ST_PROSPECTIVE = "st_prospective"
LAYER_ST_KG_DOM = "st_kg_dom"
LAYER_ST_KG_EDGES = "st_kg_edges"
LAYER_ST_VEC = "st_vec"
LAYER_ST_HIPP_EVENTS = "st_hipp_events"
LAYER_ST_LEARNING_QUEUE = "st_learning_queue"

# All valid layer names
VALID_LAYERS = frozenset(
    {
        LAYER_ST_EPI,
        LAYER_ST_SEM,
        LAYER_ST_PROCEDURAL,
        LAYER_ST_SOCIAL,
        LAYER_ST_PROSPECTIVE,
        LAYER_ST_KG_DOM,
        LAYER_ST_KG_EDGES,
        LAYER_ST_VEC,
        LAYER_ST_HIPP_EVENTS,
        LAYER_ST_LEARNING_QUEUE,
    }
)


@dataclass
class P03StagedWrites:
    """
    Container for all deferred writes accumulated during R1-R6.

    Writes are grouped by layer for efficient batch execution.
    R7 processes these in dependency order with atomic commit.

    DEPENDENCY ORDER (for get_all_writes_ordered):
        vec → kg_dom → kg_edges → epi → sem →
        procedural → social → prospective →
        learning_queue → hipp_events

    This order ensures:
        1. Embeddings exist before entities reference them
        2. Entities exist before edges reference them
        3. Truth layers written before source events updated
        4. Source events updated last (marks processing complete)

    Attributes:
        st_epi_writes: Episodic memory inserts/updates
        st_sem_writes: Semantic memory (pattern) writes
        st_procedural_writes: Procedural memory (routine) writes
        st_social_writes: Social memory (relationship) writes
        st_prospective_writes: Prospective memory (intention) writes
        st_kg_dom_writes: Knowledge graph entity writes
        st_kg_edges_writes: Knowledge graph edge writes
        st_vec_writes: Vector store (embedding) writes
        st_hipp_events_updates: Source event status updates
        st_learning_queue_writes: P06 learning queue entries
        outbox_events: Events for R8 emission
    """

    # === TRUTH LAYER WRITES ===
    st_epi_writes: List[StagedWrite] = field(default_factory=list)
    st_sem_writes: List[StagedWrite] = field(default_factory=list)
    st_procedural_writes: List[StagedWrite] = field(default_factory=list)
    st_social_writes: List[StagedWrite] = field(default_factory=list)
    st_prospective_writes: List[StagedWrite] = field(default_factory=list)
    st_kg_dom_writes: List[StagedWrite] = field(default_factory=list)
    st_kg_edges_writes: List[StagedWrite] = field(default_factory=list)
    st_vec_writes: List[StagedWrite] = field(default_factory=list)

    # === SOURCE EVENT UPDATES ===
    st_hipp_events_updates: List[StagedWrite] = field(default_factory=list)

    # === LEARNING QUEUE (P06) ===
    st_learning_queue_writes: List[StagedWrite] = field(default_factory=list)

    # === OUTBOX EVENTS ===
    outbox_events: List[StagedOutboxEvent] = field(default_factory=list)

    def add_write(self, write: StagedWrite) -> bool:
        """
        Route write to appropriate layer bucket.

        Args:
            write: StagedWrite to add

        Returns:
            True if write was added, False if layer is unknown
        """
        layer_map = {
            LAYER_ST_EPI: self.st_epi_writes,
            LAYER_ST_SEM: self.st_sem_writes,
            LAYER_ST_PROCEDURAL: self.st_procedural_writes,
            LAYER_ST_SOCIAL: self.st_social_writes,
            LAYER_ST_PROSPECTIVE: self.st_prospective_writes,
            LAYER_ST_KG_DOM: self.st_kg_dom_writes,
            LAYER_ST_KG_EDGES: self.st_kg_edges_writes,
            LAYER_ST_VEC: self.st_vec_writes,
            LAYER_ST_HIPP_EVENTS: self.st_hipp_events_updates,
            LAYER_ST_LEARNING_QUEUE: self.st_learning_queue_writes,
        }
        target = layer_map.get(write.layer)
        if target is not None:
            target.append(write)
            return True
        return False

    def add_outbox_event(
        self,
        topic: str,
        payload: Dict[str, Any],
        phase: str,
        priority: int = 50,
    ) -> StagedOutboxEvent:
        """
        Stage an outbox event for R8 emission.

        Args:
            topic: Event topic
            payload: Event payload
            phase: Source phase
            priority: Event priority (default 50)

        Returns:
            The created StagedOutboxEvent
        """
        event = StagedOutboxEvent.create(
            topic=topic,
            payload=payload,
            phase=phase,
            priority=priority,
        )
        self.outbox_events.append(event)
        return event

    def total_writes(self) -> int:
        """
        Count total staged writes (excluding outbox events).

        Returns:
            Total number of staged database writes
        """
        return sum(
            [
                len(self.st_epi_writes),
                len(self.st_sem_writes),
                len(self.st_procedural_writes),
                len(self.st_social_writes),
                len(self.st_prospective_writes),
                len(self.st_kg_dom_writes),
                len(self.st_kg_edges_writes),
                len(self.st_vec_writes),
                len(self.st_hipp_events_updates),
                len(self.st_learning_queue_writes),
            ]
        )

    def total_outbox_events(self) -> int:
        """
        Count total outbox events.

        Returns:
            Number of staged outbox events
        """
        return len(self.outbox_events)

    def get_all_writes_ordered(self) -> List[StagedWrite]:
        """
        Return writes in dependency order for atomic commit.

        Order: vec → kg_dom → kg_edges → epi → sem →
               procedural → social → prospective →
               learning_queue → hipp_events

        This ensures foreign key constraints are satisfied:
        - Embeddings before entities (entities reference embeddings)
        - Entities before edges (edges reference entities)
        - All truth layers before hipp_events (provenance tracking)

        Returns:
            List of all StagedWrite objects in commit order
        """
        return [
            *self.st_vec_writes,  # Embeddings first (referenced by others)
            *self.st_kg_dom_writes,  # Entities before edges
            *self.st_kg_edges_writes,  # Edges reference entities
            *self.st_epi_writes,  # Episodes
            *self.st_sem_writes,  # Patterns
            *self.st_procedural_writes,  # Routines
            *self.st_social_writes,  # Relationships
            *self.st_prospective_writes,  # Intentions
            *self.st_learning_queue_writes,  # P06 gaps
            *self.st_hipp_events_updates,  # Source status last
        ]

    def get_writes_by_layer(self, layer: str) -> List[StagedWrite]:
        """
        Get writes for a specific layer.

        Args:
            layer: Layer name (use LAYER_* constants)

        Returns:
            List of writes for that layer, empty if unknown layer
        """
        layer_map = {
            LAYER_ST_EPI: self.st_epi_writes,
            LAYER_ST_SEM: self.st_sem_writes,
            LAYER_ST_PROCEDURAL: self.st_procedural_writes,
            LAYER_ST_SOCIAL: self.st_social_writes,
            LAYER_ST_PROSPECTIVE: self.st_prospective_writes,
            LAYER_ST_KG_DOM: self.st_kg_dom_writes,
            LAYER_ST_KG_EDGES: self.st_kg_edges_writes,
            LAYER_ST_VEC: self.st_vec_writes,
            LAYER_ST_HIPP_EVENTS: self.st_hipp_events_updates,
            LAYER_ST_LEARNING_QUEUE: self.st_learning_queue_writes,
        }
        return layer_map.get(layer, [])

    def get_writes_by_phase(self, phase: str) -> List[StagedWrite]:
        """
        Get all writes created by a specific phase.

        Args:
            phase: Phase name (e.g., "R3", "R4")

        Returns:
            List of writes from that phase across all layers
        """
        return [w for w in self.get_all_writes_ordered() if w.source_phase == phase]

    def get_outbox_events_by_priority(self) -> List[StagedOutboxEvent]:
        """
        Get outbox events sorted by priority (ascending = higher priority first).

        Returns:
            List of outbox events sorted by priority
        """
        return sorted(self.outbox_events, key=lambda e: e.priority)

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Generate compact summary for logging/metrics.

        Returns:
            Dict with write counts per layer and outbox count
        """
        return {
            "total_writes": self.total_writes(),
            "total_outbox_events": self.total_outbox_events(),
            "by_layer": {
                "st_vec": len(self.st_vec_writes),
                "st_kg_dom": len(self.st_kg_dom_writes),
                "st_kg_edges": len(self.st_kg_edges_writes),
                "st_epi": len(self.st_epi_writes),
                "st_sem": len(self.st_sem_writes),
                "st_procedural": len(self.st_procedural_writes),
                "st_social": len(self.st_social_writes),
                "st_prospective": len(self.st_prospective_writes),
                "st_learning_queue": len(self.st_learning_queue_writes),
                "st_hipp_events": len(self.st_hipp_events_updates),
            },
            "by_operation": self._count_by_operation(),
        }

    def _count_by_operation(self) -> Dict[str, int]:
        """Count writes grouped by operation type."""
        counts: Dict[str, int] = {}
        for write in self.get_all_writes_ordered():
            op = write.operation.value
            counts[op] = counts.get(op, 0) + 1
        return counts

    def clear(self) -> None:
        """
        Clear all staged writes and outbox events.

        Use after successful commit to reset for next cycle.
        """
        self.st_epi_writes.clear()
        self.st_sem_writes.clear()
        self.st_procedural_writes.clear()
        self.st_social_writes.clear()
        self.st_prospective_writes.clear()
        self.st_kg_dom_writes.clear()
        self.st_kg_edges_writes.clear()
        self.st_vec_writes.clear()
        self.st_hipp_events_updates.clear()
        self.st_learning_queue_writes.clear()
        self.outbox_events.clear()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _now_ms() -> int:
    """Get current time in milliseconds since Unix epoch."""
    import time

    return int(time.time() * 1000)
