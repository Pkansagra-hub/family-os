"""
poc.k1_poc.delta -- Delta aggregation for SessionState coherence.

V2 Design Ref: Section 5 (Single Writer Invariant, DeltaAggregator)

This package provides the delta pipeline that enforces the Single
Writer Invariant for Back-originated state changes:

    Back emits deltas -> bus -> DeltaAggregator (500ms batch)
    -> dedup + causal order -> DeltaApplicator.apply(batch)
    -> MutationGuard preflight -> write to SS -> notify

Back NEVER writes SS directly.  The FSM is the single writer for
all Back-originated state (task_state, task_artifacts).

Public API:
    SessionDelta            -- single mutation dataclass
    VALID_DELTA_SECTIONS    -- allowed target sections
    VALID_DELTA_OPERATIONS  -- allowed mutation types

    ARTIFACT_CREATED        -- bus topic: artifact delta
    TASK_STATE_CHANGED      -- bus topic: task state delta
    STATE_UPDATED           -- bus topic: SS update notification
    ALL_DELTA_TOPICS        -- all delta topics

    emit_artifact           -- Back emitter: artifact created
    emit_task_state_change  -- Back emitter: task state transition
    VALID_TASK_STATUSES     -- allowed task status values

    DeltaAggregator         -- 500ms batch window aggregator
    DeltaBatch              -- collected batch of deltas
    DEFAULT_BATCH_WINDOW_MS -- default window (500ms)

    DeltaApplicator         -- FSM delta applicator (preflight + write)
    ApplyResult             -- result of applying a delta batch

    WriterRole              -- authorized SS writer roles
    SingleWriterViolation   -- unauthorized write exception
    SECTION_WRITERS         -- section -> authorized writers map
    ALL_WRITER_SECTIONS     -- all section names with writer rules
    validate_writer         -- check if role is authorized
    enforce_writer          -- raise if role is not authorized

    SectionSnapshot         -- immutable point-in-time section read
    SnapshotReader          -- lock-free SS section reader

    SectionOverflowHandler  -- section overflow eviction handler
"""

from poc.k1_poc.delta.aggregator import DEFAULT_BATCH_WINDOW_MS, DeltaAggregator, DeltaBatch
from poc.k1_poc.delta.applicator import ApplyResult, DeltaApplicator
from poc.k1_poc.delta.emitters import VALID_TASK_STATUSES, emit_artifact, emit_task_state_change
from poc.k1_poc.delta.overflow import SectionOverflowHandler
from poc.k1_poc.delta.session_delta import (
    VALID_DELTA_OPERATIONS,
    VALID_DELTA_SECTIONS,
    SessionDelta,
)
from poc.k1_poc.delta.snapshot_reader import SectionSnapshot, SnapshotReader
from poc.k1_poc.delta.topics import (
    ALL_DELTA_TOPICS,
    ARTIFACT_CREATED,
    STATE_UPDATED,
    TASK_STATE_CHANGED,
)
from poc.k1_poc.delta.writer_registry import (
    ALL_WRITER_SECTIONS,
    SECTION_WRITERS,
    SingleWriterViolation,
    WriterRole,
    enforce_writer,
    validate_writer,
)

__all__ = [
    # Session delta (Epic 11.1)
    "SessionDelta",
    "VALID_DELTA_SECTIONS",
    "VALID_DELTA_OPERATIONS",
    # Delta topics (Epic 11.2)
    "ARTIFACT_CREATED",
    "TASK_STATE_CHANGED",
    "STATE_UPDATED",
    "ALL_DELTA_TOPICS",
    # Emitters (Epic 11.2)
    "emit_artifact",
    "emit_task_state_change",
    "VALID_TASK_STATUSES",
    # Aggregator (Epic 11.3)
    "DeltaAggregator",
    "DeltaBatch",
    "DEFAULT_BATCH_WINDOW_MS",
    # Applicator (Epic 11.4)
    "DeltaApplicator",
    "ApplyResult",
    # Writer registry (Epic 11.5)
    "WriterRole",
    "SingleWriterViolation",
    "SECTION_WRITERS",
    "ALL_WRITER_SECTIONS",
    "validate_writer",
    "enforce_writer",
    # Snapshot reader (Epic 11.6)
    "SectionSnapshot",
    "SnapshotReader",
    # Overflow handler (Epic 11.7)
    "SectionOverflowHandler",
]
