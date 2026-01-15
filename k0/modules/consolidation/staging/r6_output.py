"""
R6Output - Core dataclass for R6 staged writes assembly.

This module provides the R6Output dataclass that encapsulates all staged
writes accumulated from R1-R5 phases, ready for atomic commit in R7.

Issue: 5.1.1
Spec Reference:
    - Dossier §4.7 (R6 — Staging Table Updates)
    - Dossier Appendix G (R6Output specification)
    - M5_EXECUTION.md Issue 5.1.1

DESIGN DECISIONS:
    - R6Output is frozen (immutable after creation) for safety
    - StagedEventUpdate captures per-event status/metadata updates
    - StagedWritesContainer is mutable builder for R6Output
    - Reuses StagedWrite and StagedOutboxEvent from staged_writes.py
    - Dependency order defined for foreign key constraints

TIMESTAMP CONVENTION (LOCKED):
    All `*_ts` and `*_ms` fields use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Import existing staged writes infrastructure from M1
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_HIPP_EVENTS,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_LEARNING_QUEUE,
    LAYER_ST_PROCEDURAL,
    LAYER_ST_PROSPECTIVE,
    LAYER_ST_SEM,
    LAYER_ST_SOCIAL,
    LAYER_ST_VEC,
    StagedOutboxEvent,
    StagedWrite,
    WriteOperation,
)

# =============================================================================
# CONSOLIDATION STATUS ENUM VALUES (from Dossier §4.7.1)
# =============================================================================

# Consolidation status values (stored in st_hipp_events.consolidation_status)
STATUS_CONSOLIDATED = "CONSOLIDATED"  # Event successfully reconciled
STATUS_DUPLICATE = "DUPLICATE"  # Event is exact/near duplicate
STATUS_PRUNED = "PRUNED"  # Event decayed below threshold
STATUS_PENDING_REVIEW = "PENDING_REVIEW"  # Event flagged for P06

# Valid status values set for validation
VALID_CONSOLIDATION_STATUSES = frozenset(
    {
        STATUS_CONSOLIDATED,
        STATUS_DUPLICATE,
        STATUS_PRUNED,
        STATUS_PENDING_REVIEW,
    }
)


# =============================================================================
# STAGED EVENT UPDATE DATACLASS
# =============================================================================


@dataclass
class StagedEventUpdate:
    """
    Per-event status update for st_hipp_events in R6.

    This captures all the metadata that R6 writes back to the source
    event table after R1-R5 cognition completes.

    Attributes:
        event_id: st_hipp_events.event_id (ULID)
        consolidation_status: CONSOLIDATED/DUPLICATE/PRUNED/PENDING_REVIEW
        near_duplicates_json: JSON array of near-duplicate event_ids with scores
        novelty_score: Computed novelty score [0, 1]
        episode_cluster_id: Cluster assignment from R2 (None for noise/singleton)
        reconciliation_action: Decision type (REINFORCE, EXTEND, CREATE, etc.)
        best_match_id: Matched truth record ID (None if CREATE/PRUNE/SKIP)
        best_match_layer: Truth layer of match (st_epi, st_sem, etc.)
        similarity_score: Cosine similarity to best match [0, 1]
        confidence: Decision confidence [0, 1]
        reconciliation_reason: Human-readable explanation
        idempotency_key: Deterministic key for retry safety
        version_conflict: Whether optimistic lock conflict detected in R6
        created_at_ms: Timestamp when update was staged (MILLISECONDS)
    """

    event_id: str
    consolidation_status: str
    near_duplicates_json: str = "[]"
    novelty_score: float = 1.0
    episode_cluster_id: Optional[str] = None
    reconciliation_action: str = "PENDING"
    best_match_id: Optional[str] = None
    best_match_layer: Optional[str] = None
    similarity_score: float = 0.0
    confidence: float = 0.0
    reconciliation_reason: str = ""
    idempotency_key: str = ""
    version_conflict: bool = False
    created_at_ms: int = field(default_factory=lambda: _now_ms())

    def __post_init__(self) -> None:
        """Validate status on creation."""
        if self.consolidation_status not in VALID_CONSOLIDATION_STATUSES:
            raise ValueError(
                f"Invalid consolidation_status: {self.consolidation_status}. "
                f"Must be one of: {VALID_CONSOLIDATION_STATUSES}"
            )

    def __hash__(self) -> int:
        """Enable use in sets (for deduplication)."""
        return hash((self.event_id, self.idempotency_key))

    def __eq__(self, other: object) -> bool:
        """Equality based on event_id and idempotency_key."""
        if not isinstance(other, StagedEventUpdate):
            return NotImplemented
        return self.event_id == other.event_id and self.idempotency_key == other.idempotency_key

    def to_record_data(self) -> Dict[str, Any]:
        """
        Convert to record data dict for StagedWrite.

        Returns:
            Dict of columns to update in st_hipp_events
        """
        return {
            "consolidation_status": self.consolidation_status,
            "near_duplicates_json": self.near_duplicates_json,
            "novelty_score": self.novelty_score,
            "episode_cluster_id": self.episode_cluster_id,
            "reconciliation_action": self.reconciliation_action,
            "best_match_id": self.best_match_id,
            "best_match_layer": self.best_match_layer,
            "similarity_score": self.similarity_score,
            "confidence": self.confidence,
            "reconciliation_reason": self.reconciliation_reason,
            "consolidated_at_ms": self.created_at_ms,
        }

    def to_staged_write(self, phase: str = "R6") -> StagedWrite:
        """
        Convert to StagedWrite for R7 commit.

        Args:
            phase: Source phase identifier (default R6)

        Returns:
            StagedWrite configured for UPDATE on st_hipp_events
        """
        from k0.pipelines.p03.context import generate_ulid

        return StagedWrite(
            write_id=generate_ulid(),
            layer=LAYER_ST_HIPP_EVENTS,
            operation=WriteOperation.UPDATE,
            record_id=self.event_id,
            record_data=self.to_record_data(),
            idempotency_key=self.idempotency_key,
            source_phase=phase,
            source_event_ids=[self.event_id],
        )

    def to_json(self) -> str:
        """Serialize to JSON for checkpoint/logging."""
        return json.dumps(
            {
                "event_id": self.event_id,
                "consolidation_status": self.consolidation_status,
                "near_duplicates_json": self.near_duplicates_json,
                "novelty_score": self.novelty_score,
                "episode_cluster_id": self.episode_cluster_id,
                "reconciliation_action": self.reconciliation_action,
                "best_match_id": self.best_match_id,
                "best_match_layer": self.best_match_layer,
                "similarity_score": self.similarity_score,
                "confidence": self.confidence,
                "reconciliation_reason": self.reconciliation_reason,
                "idempotency_key": self.idempotency_key,
                "created_at_ms": self.created_at_ms,
            }
        )

    @classmethod
    def from_json(cls, json_str: str) -> StagedEventUpdate:
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(**data)


# =============================================================================
# RECONCILIATION SUMMARY DATACLASS
# =============================================================================


@dataclass(frozen=True)
class ReconciliationSummary:
    """
    Aggregate statistics for a consolidation cycle.

    Captures counts and breakdowns of how events were processed,
    used for metrics emission in R8 and audit logging.

    Issue 8.1.12: Added insight_count for R5 outputs tracking.
    Issue 8.1.17: Added counterfactual_count, routine_optimization_count.

    Attributes:
        total_events: Total events in batch
        consolidated_count: Events with status CONSOLIDATED
        duplicate_count: Events with status DUPLICATE
        pruned_count: Events with status PRUNED
        pending_review_count: Events with status PENDING_REVIEW
        action_breakdown: Count per ReconciliationAction value
        layer_write_counts: Count of writes per truth layer
        kg_entity_count: New/updated KG entities
        kg_edge_count: New/updated KG edges
        gap_count: Gaps emitted for P06
        insight_count: Insights generated by R5 (Issue 8.1.12)
        counterfactual_count: Counterfactual scenarios from CPN (Issue 8.1.17)
        routine_optimization_count: Routine optimizations from TDL-HCO (Issue 8.1.17)
        total_writes: Total database writes staged
        cycle_duration_ms: R0-R6 processing time in MILLISECONDS
    """

    total_events: int = 0
    consolidated_count: int = 0
    duplicate_count: int = 0
    pruned_count: int = 0
    pending_review_count: int = 0
    action_breakdown: Tuple[Tuple[str, int], ...] = ()
    layer_write_counts: Tuple[Tuple[str, int], ...] = ()
    kg_entity_count: int = 0
    kg_edge_count: int = 0
    gap_count: int = 0
    insight_count: int = 0  # Issue 8.1.12
    counterfactual_count: int = 0  # Issue 8.1.17
    routine_optimization_count: int = 0  # Issue 8.1.17
    total_writes: int = 0
    cycle_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "total_events": self.total_events,
            "consolidated_count": self.consolidated_count,
            "duplicate_count": self.duplicate_count,
            "pruned_count": self.pruned_count,
            "pending_review_count": self.pending_review_count,
            "action_breakdown": dict(self.action_breakdown),
            "layer_write_counts": dict(self.layer_write_counts),
            "kg_entity_count": self.kg_entity_count,
            "kg_edge_count": self.kg_edge_count,
            "gap_count": self.gap_count,
            "insight_count": self.insight_count,
            "counterfactual_count": self.counterfactual_count,
            "routine_optimization_count": self.routine_optimization_count,
            "total_writes": self.total_writes,
            "cycle_duration_ms": self.cycle_duration_ms,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


# =============================================================================
# R6 OUTPUT DATACLASS (FROZEN)
# =============================================================================


@dataclass(frozen=True)
class R6Output:
    """
    Immutable output from R6 phase containing all staged writes.

    This is the contract between R6 and R7: R6 produces an R6Output,
    and R7 commits it atomically via UnitOfWork.

    The R6Output is frozen (immutable) to ensure no modifications
    after R6 completes. Use StagedWritesContainer to build it.

    DEPENDENCY ORDER (for R7 commit):
        vec → kg_dom → kg_edges → epi → sem →
        procedural → social → prospective →
        learning_queue → hipp_events

    Attributes:
        cycle_ulid: Cycle identifier for idempotency and tracing
        batch_id: Deterministic batch hash from R0
        staged_event_updates: Per-event status updates (tuple for immutability)
        staged_truth_writes: Truth layer writes (epi, sem, procedural, etc.)
        staged_kg_writes: KG entity and edge writes
        staged_outbox_events: Outbox events for R8 emission
        reconciliation_summary: Aggregate cycle statistics
        created_at_ms: Timestamp when R6Output was finalized (MILLISECONDS)
        r6_idempotency_key: Idempotency key for the R6 phase itself
    """

    cycle_ulid: str
    batch_id: str
    staged_event_updates: Tuple[StagedEventUpdate, ...]
    staged_truth_writes: Tuple[StagedWrite, ...]
    staged_kg_writes: Tuple[StagedWrite, ...]
    staged_outbox_events: Tuple[StagedOutboxEvent, ...]
    reconciliation_summary: ReconciliationSummary
    created_at_ms: int
    r6_idempotency_key: str

    def __post_init__(self) -> None:
        """Validate R6Output on creation."""
        if not self.cycle_ulid:
            raise ValueError("cycle_ulid is required")
        if not self.batch_id:
            raise ValueError("batch_id is required")
        if not self.r6_idempotency_key:
            raise ValueError("r6_idempotency_key is required")

    @property
    def event_count(self) -> int:
        """Number of events processed in this cycle."""
        return len(self.staged_event_updates)

    @property
    def total_truth_writes(self) -> int:
        """Total truth layer writes (excluding KG)."""
        return len(self.staged_truth_writes)

    @property
    def total_kg_writes(self) -> int:
        """Total KG entity + edge writes."""
        return len(self.staged_kg_writes)

    @property
    def total_outbox_events(self) -> int:
        """Total outbox events for R8."""
        return len(self.staged_outbox_events)

    @property
    def total_writes(self) -> int:
        """Total database writes to commit."""
        return (
            self.event_count  # st_hipp_events updates
            + self.total_truth_writes
            + self.total_kg_writes
        )

    def get_all_writes_ordered(self) -> List[StagedWrite]:
        """
        Get all writes in dependency order for R7 commit.

        Order: vec → kg_dom → kg_edges → epi → sem →
               procedural → social → prospective →
               learning_queue → hipp_events

        Returns:
            List of StagedWrite in commit order
        """
        # Build layer buckets
        writes_by_layer: Dict[str, List[StagedWrite]] = {
            LAYER_ST_VEC: [],
            LAYER_ST_KG_DOM: [],
            LAYER_ST_KG_EDGES: [],
            LAYER_ST_EPI: [],
            LAYER_ST_SEM: [],
            LAYER_ST_PROCEDURAL: [],
            LAYER_ST_SOCIAL: [],
            LAYER_ST_PROSPECTIVE: [],
            LAYER_ST_LEARNING_QUEUE: [],
            LAYER_ST_HIPP_EVENTS: [],
        }

        # Route truth writes
        for write in self.staged_truth_writes:
            if write.layer in writes_by_layer:
                writes_by_layer[write.layer].append(write)

        # Route KG writes
        for write in self.staged_kg_writes:
            if write.layer in writes_by_layer:
                writes_by_layer[write.layer].append(write)

        # Add event updates as staged writes
        for update in self.staged_event_updates:
            writes_by_layer[LAYER_ST_HIPP_EVENTS].append(update.to_staged_write("R6"))

        # Return in dependency order
        return [
            *writes_by_layer[LAYER_ST_VEC],
            *writes_by_layer[LAYER_ST_KG_DOM],
            *writes_by_layer[LAYER_ST_KG_EDGES],
            *writes_by_layer[LAYER_ST_EPI],
            *writes_by_layer[LAYER_ST_SEM],
            *writes_by_layer[LAYER_ST_PROCEDURAL],
            *writes_by_layer[LAYER_ST_SOCIAL],
            *writes_by_layer[LAYER_ST_PROSPECTIVE],
            *writes_by_layer[LAYER_ST_LEARNING_QUEUE],
            *writes_by_layer[LAYER_ST_HIPP_EVENTS],
        ]

    def to_json(self) -> str:
        """
        Serialize to JSON for checkpoint/recovery.

        Returns:
            JSON string representation
        """
        return json.dumps(
            {
                "cycle_ulid": self.cycle_ulid,
                "batch_id": self.batch_id,
                "staged_event_updates": [u.to_json() for u in self.staged_event_updates],
                "staged_truth_writes_count": len(self.staged_truth_writes),
                "staged_kg_writes_count": len(self.staged_kg_writes),
                "staged_outbox_events_count": len(self.staged_outbox_events),
                "reconciliation_summary": self.reconciliation_summary.to_dict(),
                "created_at_ms": self.created_at_ms,
                "r6_idempotency_key": self.r6_idempotency_key,
            }
        )

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Generate compact summary for logging/metrics.

        Returns:
            Dict with key counts and statistics
        """
        return {
            "cycle_ulid": self.cycle_ulid,
            "batch_id": self.batch_id,
            "event_count": self.event_count,
            "total_truth_writes": self.total_truth_writes,
            "total_kg_writes": self.total_kg_writes,
            "total_outbox_events": self.total_outbox_events,
            "total_writes": self.total_writes,
            "summary": self.reconciliation_summary.to_dict(),
            "created_at_ms": self.created_at_ms,
        }


# =============================================================================
# STAGED WRITES CONTAINER (MUTABLE BUILDER)
# =============================================================================


class StagedWritesContainer:
    """
    Mutable container that accumulates staged writes during R6.

    Use this class to build an R6Output incrementally:
    1. Create container with cycle context
    2. Add event updates, truth writes, KG writes, outbox events
    3. Call to_r6_output() to finalize and freeze

    The container validates writes as they're added and tracks
    statistics for the ReconciliationSummary.

    Example:
        container = StagedWritesContainer(cycle_ulid, batch_id)
        container.add_event_update(update1)
        container.add_truth_write(write1)
        container.add_kg_write(kg_write1)
        container.add_outbox_event(event1)
        r6_output = container.to_r6_output()
    """

    def __init__(
        self,
        cycle_ulid: str,
        batch_id: str,
        start_time_ms: Optional[int] = None,
    ) -> None:
        """
        Initialize container for a consolidation cycle.

        Args:
            cycle_ulid: Cycle identifier (from P03CycleContext)
            batch_id: Batch hash (from P03CycleContext)
            start_time_ms: Cycle start timestamp for duration calculation
        """
        self.cycle_ulid = cycle_ulid
        self.batch_id = batch_id
        self.start_time_ms = start_time_ms or _now_ms()

        # Staged items (mutable during R6)
        self._event_updates: List[StagedEventUpdate] = []
        self._truth_writes: List[StagedWrite] = []
        self._kg_writes: List[StagedWrite] = []
        self._outbox_events: List[StagedOutboxEvent] = []

        # Deduplication sets (prevent duplicate adds)
        self._seen_event_ids: set[str] = set()
        self._seen_write_keys: set[str] = set()
        self._seen_outbox_ids: set[str] = set()

        # Finalization flag
        self._finalized = False

    def _check_not_finalized(self) -> None:
        """Raise if container has been finalized."""
        if self._finalized:
            raise RuntimeError(
                "StagedWritesContainer has been finalized. " "Cannot add more writes."
            )

    # =========================================================================
    # Add Methods
    # =========================================================================

    def add_event_update(self, update: StagedEventUpdate) -> bool:
        """
        Add a per-event status update.

        Args:
            update: StagedEventUpdate to add

        Returns:
            True if added, False if duplicate event_id
        """
        self._check_not_finalized()

        if update.event_id in self._seen_event_ids:
            return False

        self._event_updates.append(update)
        self._seen_event_ids.add(update.event_id)
        return True

    def add_truth_write(self, write: StagedWrite) -> bool:
        """
        Add a truth layer write (st_epi, st_sem, etc.).

        Args:
            write: StagedWrite for truth layer

        Returns:
            True if added, False if duplicate idempotency key
        """
        self._check_not_finalized()

        if write.idempotency_key in self._seen_write_keys:
            return False

        # Validate layer is a truth layer (not KG)
        if write.layer in (LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES):
            raise ValueError(
                f"Use add_kg_write() for KG layers, not add_truth_write(). "
                f"Got layer: {write.layer}"
            )

        self._truth_writes.append(write)
        self._seen_write_keys.add(write.idempotency_key)
        return True

    def add_kg_write(self, write: StagedWrite) -> bool:
        """
        Add a KG entity or edge write.

        Args:
            write: StagedWrite for st_kg_dom or st_kg_edges

        Returns:
            True if added, False if duplicate idempotency key
        """
        self._check_not_finalized()

        if write.idempotency_key in self._seen_write_keys:
            return False

        # Validate layer is a KG layer
        if write.layer not in (LAYER_ST_KG_DOM, LAYER_ST_KG_EDGES):
            raise ValueError(
                f"Use add_truth_write() for non-KG layers. " f"Got layer: {write.layer}"
            )

        self._kg_writes.append(write)
        self._seen_write_keys.add(write.idempotency_key)
        return True

    def add_outbox_event(self, event: StagedOutboxEvent) -> bool:
        """
        Add an outbox event for R8 emission.

        Args:
            event: StagedOutboxEvent to stage

        Returns:
            True if added, False if duplicate event_id
        """
        self._check_not_finalized()

        if event.event_id in self._seen_outbox_ids:
            return False

        self._outbox_events.append(event)
        self._seen_outbox_ids.add(event.event_id)
        return True

    # =========================================================================
    # Query Methods
    # =========================================================================

    @property
    def event_update_count(self) -> int:
        """Number of event updates staged."""
        return len(self._event_updates)

    @property
    def truth_write_count(self) -> int:
        """Number of truth layer writes staged."""
        return len(self._truth_writes)

    @property
    def kg_write_count(self) -> int:
        """Number of KG writes staged."""
        return len(self._kg_writes)

    @property
    def outbox_event_count(self) -> int:
        """Number of outbox events staged."""
        return len(self._outbox_events)

    @property
    def total_writes(self) -> int:
        """Total database writes (excluding outbox)."""
        return self.event_update_count + self.truth_write_count + self.kg_write_count

    def get_status_counts(self) -> Dict[str, int]:
        """
        Count events by consolidation status.

        Returns:
            Dict mapping status to count
        """
        counts: Dict[str, int] = {
            STATUS_CONSOLIDATED: 0,
            STATUS_DUPLICATE: 0,
            STATUS_PRUNED: 0,
            STATUS_PENDING_REVIEW: 0,
        }
        for update in self._event_updates:
            if update.consolidation_status in counts:
                counts[update.consolidation_status] += 1
        return counts

    def get_action_breakdown(self) -> Dict[str, int]:
        """
        Count events by reconciliation action.

        Returns:
            Dict mapping action to count
        """
        counts: Dict[str, int] = {}
        for update in self._event_updates:
            action = update.reconciliation_action
            counts[action] = counts.get(action, 0) + 1
        return counts

    def get_layer_write_counts(self) -> Dict[str, int]:
        """
        Count writes by target layer.

        Returns:
            Dict mapping layer name to write count
        """
        counts: Dict[str, int] = {}

        for write in self._truth_writes:
            counts[write.layer] = counts.get(write.layer, 0) + 1

        for write in self._kg_writes:
            counts[write.layer] = counts.get(write.layer, 0) + 1

        counts[LAYER_ST_HIPP_EVENTS] = self.event_update_count

        return counts

    # =========================================================================
    # Finalization Methods
    # =========================================================================

    def _build_reconciliation_summary(self) -> ReconciliationSummary:
        """Build the reconciliation summary from accumulated data."""
        status_counts = self.get_status_counts()
        action_breakdown = self.get_action_breakdown()
        layer_write_counts = self.get_layer_write_counts()

        # Count KG entities and edges separately
        kg_entity_count = sum(1 for w in self._kg_writes if w.layer == LAYER_ST_KG_DOM)
        kg_edge_count = sum(1 for w in self._kg_writes if w.layer == LAYER_ST_KG_EDGES)

        # Count gaps (learning queue writes)
        gap_count = sum(1 for w in self._truth_writes if w.layer == LAYER_ST_LEARNING_QUEUE)

        # Calculate cycle duration
        cycle_duration_ms = _now_ms() - self.start_time_ms

        return ReconciliationSummary(
            total_events=self.event_update_count,
            consolidated_count=status_counts.get(STATUS_CONSOLIDATED, 0),
            duplicate_count=status_counts.get(STATUS_DUPLICATE, 0),
            pruned_count=status_counts.get(STATUS_PRUNED, 0),
            pending_review_count=status_counts.get(STATUS_PENDING_REVIEW, 0),
            action_breakdown=tuple(sorted(action_breakdown.items())),
            layer_write_counts=tuple(sorted(layer_write_counts.items())),
            kg_entity_count=kg_entity_count,
            kg_edge_count=kg_edge_count,
            gap_count=gap_count,
            total_writes=self.total_writes,
            cycle_duration_ms=cycle_duration_ms,
        )

    def _generate_r6_idempotency_key(self) -> str:
        """
        Generate idempotency key for R6 phase.

        Format: p03:r6:{cycle_ulid}:{batch_hash}

        Returns:
            Deterministic idempotency key
        """
        # Hash the sorted event IDs for deterministic batch identification
        event_ids = sorted(self._seen_event_ids)
        batch_hash = hashlib.sha256("|".join(event_ids).encode("utf-8")).hexdigest()[:12]

        return f"p03:r6:{self.cycle_ulid}:{batch_hash}"

    def to_r6_output(self) -> R6Output:
        """
        Finalize container and return frozen R6Output.

        This method can only be called once. After calling,
        the container cannot accept more writes.

        Returns:
            Frozen R6Output ready for R7 commit

        Raises:
            RuntimeError: If already finalized
        """
        self._check_not_finalized()
        self._finalized = True

        return R6Output(
            cycle_ulid=self.cycle_ulid,
            batch_id=self.batch_id,
            staged_event_updates=tuple(self._event_updates),
            staged_truth_writes=tuple(self._truth_writes),
            staged_kg_writes=tuple(self._kg_writes),
            staged_outbox_events=tuple(self._outbox_events),
            reconciliation_summary=self._build_reconciliation_summary(),
            created_at_ms=_now_ms(),
            r6_idempotency_key=self._generate_r6_idempotency_key(),
        )

    def to_json(self) -> str:
        """
        Serialize current state to JSON for checkpoint.

        Can be called before finalization for progress checkpoints.

        Returns:
            JSON string of current container state
        """
        return json.dumps(
            {
                "cycle_ulid": self.cycle_ulid,
                "batch_id": self.batch_id,
                "start_time_ms": self.start_time_ms,
                "finalized": self._finalized,
                "event_update_count": self.event_update_count,
                "truth_write_count": self.truth_write_count,
                "kg_write_count": self.kg_write_count,
                "outbox_event_count": self.outbox_event_count,
                "status_counts": self.get_status_counts(),
            }
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _now_ms() -> int:
    """Get current time in milliseconds since Unix epoch."""
    return int(time.time() * 1000)
