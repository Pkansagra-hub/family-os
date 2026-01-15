"""
P03 Sequential Runner Contract — Issue 1.2.1 Decision Note

This module documents the contract for P03's sequential phase execution engine.
It captures design decisions that inform the implementation in subsequent issues.

References:
- Spec: docs/pipelines/P03_consolidation_dossier_v2.md Appendix G
- Issue: docs/TEMP_EXECUTION_DOCS/M1_EXECUTION.md Issue 1.2.1
- Contrast: k0/runtime/pipeline_runner.py (generic DAG runner)

Decision: (A) Dedicated P03Pipeline with internal sequential runner
Rationale: P03 requires strict R0→R8 sequential execution with specific skip
transitions that don't fit the generic DAG runner's parallel-by-level model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple

# =============================================================================
# ERROR TYPE CLASSIFICATIONS (Issue 5.2.W6)
# =============================================================================


class P03ErrorType(Enum):
    """
    Typed error categories for retry logic.

    M5 Issue 5.2.W6: R6-specific error types for targeted recovery.
    """

    GENERIC = "GENERIC"
    DB_TIMEOUT = "DB_TIMEOUT"
    LOCK_TIMEOUT = "LOCK_TIMEOUT"
    POOL_EXHAUSTED = "POOL_EXHAUSTED"
    # R6-specific errors
    R6_VERSION_CONFLICT = "R6_VERSION_CONFLICT"
    R6_UNIQUE_VIOLATION = "R6_UNIQUE_VIOLATION"
    R6_MANIFEST_INVALID = "R6_MANIFEST_INVALID"
    # R7-specific errors
    R7_VERSION_CONFLICT = "R7_VERSION_CONFLICT"
    R7_TRANSACTION_FAILED = "R7_TRANSACTION_FAILED"


# =============================================================================
# PHASE DEFINITIONS (from Appendix G.2)
# =============================================================================


class P03PhaseId(Enum):
    """
    Phase identifiers for R0-R8 consolidation pipeline.

    Order is significant: R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8
    Terminal states are COMPLETE and FAILED.

    Phases:
        R0_INIT: Batch Selection - Select pending events from st_hipp_events
        R1_SCORE: Importance Scoring - Compute importance, hebbian updates
        R2_CLUSTER: Episodic Clustering - DBSCAN clustering of events
        R3_PRUNE: Forgetting/Pruning - Dedup, decay, archive candidates
        R4_KG: Knowledge Graph - Entity extraction, edge building
        R5_DREAM: Dream Exploration - Counterfactuals, insights (optional)
        R6_STAGE: Status Staging - Prepare writes, version checks
        R7_WRITE: Memory Writing - Atomic UoW commit to truth layers
        R8_EMIT: Event Emission - Publish completion, gap detection
        COMPLETE: Successful cycle completion (terminal)
        FAILED: Cycle failure (terminal)
    """

    R0_INIT = "R0"
    R1_SCORE = "R1"
    R2_CLUSTER = "R2"
    R3_PRUNE = "R3"
    R4_KG = "R4"
    R5_DREAM = "R5"
    R6_STAGE = "R6"
    R7_WRITE = "R7"
    R8_EMIT = "R8"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

    @classmethod
    def execution_order(cls) -> Tuple["P03PhaseId", ...]:
        """Return phases in execution order (excludes terminal states)."""
        return (
            cls.R0_INIT,
            cls.R1_SCORE,
            cls.R2_CLUSTER,
            cls.R3_PRUNE,
            cls.R4_KG,
            cls.R5_DREAM,
            cls.R6_STAGE,
            cls.R7_WRITE,
            cls.R8_EMIT,
        )

    @staticmethod
    def valid_transitions() -> Dict[str, List[str]]:
        """Define valid phase transitions."""
        return {
            "R0": ["R1", "FAILED"],
            "R1": ["R2", "FAILED"],
            "R2": ["R3", "FAILED"],
            "R3": ["R4", "FAILED"],
            "R4": ["R5", "R6", "FAILED"],  # R5 is optional
            "R5": ["R6", "FAILED"],
            "R6": ["R7", "FAILED"],
            "R7": ["R8", "FAILED"],
            "R8": ["COMPLETE", "FAILED"],
            "COMPLETE": [],  # Terminal
            "FAILED": [],  # Terminal
        }

    def can_transition_to(self, target: "P03PhaseId") -> bool:
        """Check if transition to target phase is valid."""
        return target.value in self.valid_transitions().get(self.value, [])

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (P03PhaseId.COMPLETE, P03PhaseId.FAILED)

    def next_phase(self) -> Optional["P03PhaseId"]:
        """Return next phase in normal execution order, or None if terminal."""
        if self.is_terminal():
            return None
        order = self.execution_order()
        try:
            idx = order.index(self)
            if idx < len(order) - 1:
                return order[idx + 1]
        except ValueError:
            pass
        return None

    def index(self) -> int:
        """Return 0-based index in execution order, or -1 for terminal states."""
        if self.is_terminal():
            return -1
        return self.execution_order().index(self)


class P03PhaseStatus(Enum):
    """
    Phase execution status (from Appendix G.1).

    States:
        INIT: Phase not yet started
        PROC: Phase in progress (processing)
        SKIP: Phase skipped (with reason)
        FAIL: Phase failed (may be retriable, eventually DLQ)
        DONE: Phase completed successfully
    """

    INIT = "INIT"
    PROC = "PROC"
    SKIP = "SKIP"
    FAIL = "FAIL"
    DONE = "DONE"


# =============================================================================
# PHASE TRANSITION RULES (from Appendix G.3)
# =============================================================================

# Normal transitions: phase → next phase
# All phases transition to next in order when successful
NORMAL_TRANSITIONS: Dict[P03PhaseId, P03PhaseId] = {
    P03PhaseId.R0_INIT: P03PhaseId.R1_SCORE,
    P03PhaseId.R1_SCORE: P03PhaseId.R2_CLUSTER,
    P03PhaseId.R2_CLUSTER: P03PhaseId.R3_PRUNE,
    P03PhaseId.R3_PRUNE: P03PhaseId.R4_KG,
    P03PhaseId.R4_KG: P03PhaseId.R5_DREAM,
    P03PhaseId.R5_DREAM: P03PhaseId.R6_STAGE,
    P03PhaseId.R6_STAGE: P03PhaseId.R7_WRITE,
    P03PhaseId.R7_WRITE: P03PhaseId.R8_EMIT,
    # R8 is terminal - no next phase
}

# Skip transitions: phase → skip-to phase (with condition)
SKIP_TRANSITIONS: Dict[P03PhaseId, Tuple[P03PhaseId, str]] = {
    # R2 can skip to R6 for minimal-work fast-path (batch_size < 2)
    P03PhaseId.R2_CLUSTER: (P03PhaseId.R6_STAGE, "batch_size < 2"),
    # R5 can be skipped when backlogged (R4 → R6)
    P03PhaseId.R4_KG: (P03PhaseId.R6_STAGE, "r5_skip_on_backlog AND pending > threshold"),
    # R5 itself can skip (already at R5, just mark skipped and proceed)
    P03PhaseId.R5_DREAM: (P03PhaseId.R6_STAGE, "backlog_threshold exceeded"),
}

# Phases that can never be skipped
REQUIRED_PHASES: FrozenSet[P03PhaseId] = frozenset(
    {
        P03PhaseId.R0_INIT,
        P03PhaseId.R1_SCORE,
        P03PhaseId.R3_PRUNE,
        P03PhaseId.R4_KG,
        P03PhaseId.R6_STAGE,
        P03PhaseId.R7_WRITE,
        P03PhaseId.R8_EMIT,
    }
)

# Phases that MAY be skipped under conditions
SKIPPABLE_PHASES: FrozenSet[P03PhaseId] = frozenset(
    {
        P03PhaseId.R2_CLUSTER,  # When batch_size < 2
        P03PhaseId.R5_DREAM,  # When backlogged
    }
)


def is_valid_transition(from_phase: P03PhaseId, to_phase: P03PhaseId) -> bool:
    """
    Check if a phase transition is valid.

    Valid transitions:
    1. Normal: R0→R1→R2→R3→R4→R5→R6→R7→R8
    2. Skip: R2→R6 (minimal work), R4→R6 (skip R5), R5→R6 (R5 skipped)
    3. Fail: Any phase → FAIL status (handled separately)

    Args:
        from_phase: Current phase
        to_phase: Proposed next phase

    Returns:
        True if transition is allowed
    """
    # Normal transition?
    if NORMAL_TRANSITIONS.get(from_phase) == to_phase:
        return True

    # Skip transition?
    skip_info = SKIP_TRANSITIONS.get(from_phase)
    if skip_info and skip_info[0] == to_phase:
        return True

    return False


# =============================================================================
# PHASE CONTRACT SPECIFICATIONS (from Appendix G.2)
# =============================================================================


@dataclass(frozen=True)
class PhaseContract:
    """
    Contract specification for a single phase.

    Captures inputs, outputs, idempotency, retry policy, and timeouts
    as specified in Appendix G.2.
    """

    phase_id: P03PhaseId
    purpose: str

    # Data flow
    db_reads: Tuple[str, ...]  # Tables read
    db_writes: Tuple[str, ...]  # Tables written (empty for deferred phases)

    # Idempotency
    idempotency_key_template: str  # e.g., "p03:r1:{cycle_id}:{batch_hash}"

    # Retry policy
    retryable: bool
    max_retries: int
    dlq_condition: str

    # Timing
    timeout_seconds: int

    # Skip policy
    skip_condition: Optional[str]  # None = never skip


# Phase contracts from Appendix G.2
PHASE_CONTRACTS: Dict[P03PhaseId, PhaseContract] = {
    P03PhaseId.R0_INIT: PhaseContract(
        phase_id=P03PhaseId.R0_INIT,
        purpose="Select pending events from st_hipp_events for this cycle",
        db_reads=("st_hipp_events", "st_pipeline_status"),
        db_writes=("st_pipeline_status",),
        idempotency_key_template="p03:cycle:{cycle_id}",
        retryable=True,
        max_retries=3,
        dlq_condition="DB connection failure after 3 retries",
        timeout_seconds=30,
        skip_condition=None,
    ),
    P03PhaseId.R1_SCORE: PhaseContract(
        phase_id=P03PhaseId.R1_SCORE,
        purpose="Compute importance score for each event; update co-occurrence edges",
        db_reads=("st_hipp_events", "st_kg_edges", "st_vec"),
        db_writes=(),  # In-memory enrichment, deferred to R7
        idempotency_key_template="p03:r1:{cycle_id}:{batch_hash}",
        retryable=True,
        max_retries=3,
        dlq_condition="P08 embedding service unavailable",
        timeout_seconds=60,
        skip_condition=None,
    ),
    P03PhaseId.R2_CLUSTER: PhaseContract(
        phase_id=P03PhaseId.R2_CLUSTER,
        purpose="Cluster events into episodes using DBSCAN",
        db_reads=("st_vec", "st_epi"),
        db_writes=(),  # In-memory
        idempotency_key_template="p03:r2:{cycle_id}:{batch_hash}",
        retryable=True,
        max_retries=2,
        dlq_condition="Clustering algorithm timeout",
        timeout_seconds=120,
        skip_condition="batch_size < 2",
    ),
    P03PhaseId.R3_PRUNE: PhaseContract(
        phase_id=P03PhaseId.R3_PRUNE,
        purpose="Deduplicate via SimHash; apply decay; mark prune/archive candidates",
        db_reads=("st_hipp_events", "st_epi", "st_sem", "st_kg_edges"),
        db_writes=(),  # Deferred to R7
        idempotency_key_template="p03:r3:{cycle_id}:{batch_hash}",
        retryable=True,
        max_retries=3,
        dlq_condition="None (always succeeds)",
        timeout_seconds=60,
        skip_condition=None,
    ),
    P03PhaseId.R4_KG: PhaseContract(
        phase_id=P03PhaseId.R4_KG,
        purpose="Extract entities; build relationships; infer causality",
        db_reads=("st_kg_dom", "st_kg_edges"),
        db_writes=(),  # Deferred to R7
        idempotency_key_template="p03:r4:{cycle_id}:{batch_hash}",
        retryable=True,
        max_retries=3,
        dlq_condition="Entity resolution service failure",
        timeout_seconds=90,
        skip_condition=None,
    ),
    P03PhaseId.R5_DREAM: PhaseContract(
        phase_id=P03PhaseId.R5_DREAM,
        purpose="Counterfactual simulation; insight generation; motor rehearsal",
        db_reads=("st_epi", "st_sem", "st_procedural", "st_prospective"),
        db_writes=(),  # Deferred to R7
        idempotency_key_template="p03:r5:{cycle_id}:{batch_hash}",
        retryable=True,
        max_retries=3,
        dlq_condition="MCTS timeout",
        timeout_seconds=120,
        skip_condition="skip_on_backlog=true AND pending > backlog_threshold",
    ),
    P03PhaseId.R6_STAGE: PhaseContract(
        phase_id=P03PhaseId.R6_STAGE,
        purpose="Stage all R1-R5 outputs as writes; validate manifest; prepare for R7 commit",
        db_reads=("st_hipp_events",),  # For version check
        db_writes=(),  # Preparation only - R7 does actual writes
        idempotency_key_template="p03:staging:{cycle_ulid}:{event_id}",
        retryable=True,
        max_retries=3,
        dlq_condition="Validation failure OR version conflict on >10% of events",
        timeout_seconds=45,
        skip_condition=None,  # R6 is REQUIRED_PHASE
    ),
    P03PhaseId.R7_WRITE: PhaseContract(
        phase_id=P03PhaseId.R7_WRITE,
        purpose="Atomic write to all truth layers via UnitOfWork",
        db_reads=(),
        db_writes=(
            "st_epi",
            "st_sem",
            "st_procedural",
            "st_social",
            "st_prospective",
            "st_kg_dom",
            "st_kg_edges",
            "st_vec",
            "st_hipp_events",
            "st_outbox",
        ),
        idempotency_key_template="p03:r7:{cycle_id}:{table}:{record_id}",
        retryable=True,
        max_retries=3,
        dlq_condition="Transaction failure after 3 retries",
        timeout_seconds=60,
        skip_condition=None,
    ),
    P03PhaseId.R8_EMIT: PhaseContract(
        phase_id=P03PhaseId.R8_EMIT,
        purpose="Emit completion events; detect and emit P06 gaps",
        db_reads=("st_outbox",),
        db_writes=("st_outbox", "st_learning_queue"),
        idempotency_key_template="p03:r8:{cycle_id}:{topic}:{offset}",
        retryable=True,
        max_retries=10,
        dlq_condition="Event bus unavailable",
        timeout_seconds=30,
        skip_condition=None,
    ),
}


# =============================================================================
# RESUME MATRIX (from Appendix G.4)
# =============================================================================


@dataclass(frozen=True)
class ResumePolicy:
    """
    Resume policy for a phase.

    Specifies what happens when resuming a cycle that failed/interrupted
    at this phase.
    """

    phase_id: P03PhaseId
    can_resume: bool
    resume_from: P03PhaseId  # Which phase to actually start from
    requires_state: Tuple[str, ...]  # What checkpoint state is needed
    notes: str


RESUME_MATRIX: Dict[P03PhaseId, ResumePolicy] = {
    P03PhaseId.R0_INIT: ResumePolicy(
        phase_id=P03PhaseId.R0_INIT,
        can_resume=True,
        resume_from=P03PhaseId.R0_INIT,
        requires_state=(),
        notes="Re-select batch; may get different events if new arrived",
    ),
    P03PhaseId.R1_SCORE: ResumePolicy(
        phase_id=P03PhaseId.R1_SCORE,
        can_resume=True,
        resume_from=P03PhaseId.R1_SCORE,
        requires_state=("event_ids", "batch_id"),
        notes="Idempotent; re-score same events",
    ),
    P03PhaseId.R2_CLUSTER: ResumePolicy(
        phase_id=P03PhaseId.R2_CLUSTER,
        can_resume=True,
        resume_from=P03PhaseId.R2_CLUSTER,
        requires_state=("event_ids", "importance_scores"),
        notes="Idempotent; re-cluster with same embeddings",
    ),
    P03PhaseId.R3_PRUNE: ResumePolicy(
        phase_id=P03PhaseId.R3_PRUNE,
        can_resume=True,
        resume_from=P03PhaseId.R3_PRUNE,
        requires_state=("event_ids", "clusters"),
        notes="Idempotent; re-compute dedup/decay",
    ),
    P03PhaseId.R4_KG: ResumePolicy(
        phase_id=P03PhaseId.R4_KG,
        can_resume=True,
        resume_from=P03PhaseId.R4_KG,
        requires_state=("event_ids", "clusters", "novelty_scores"),
        notes="Idempotent; re-extract entities/edges",
    ),
    P03PhaseId.R5_DREAM: ResumePolicy(
        phase_id=P03PhaseId.R5_DREAM,
        can_resume=True,
        resume_from=P03PhaseId.R5_DREAM,
        requires_state=("kg_outputs", "clusters"),
        notes="Idempotent; re-run MCTS exploration",
    ),
    P03PhaseId.R6_STAGE: ResumePolicy(
        phase_id=P03PhaseId.R6_STAGE,
        can_resume=True,
        resume_from=P03PhaseId.R6_STAGE,
        requires_state=("all_phase_outputs",),
        notes="Re-stage with version re-check",
    ),
    P03PhaseId.R7_WRITE: ResumePolicy(
        phase_id=P03PhaseId.R7_WRITE,
        can_resume=True,
        resume_from=P03PhaseId.R6_STAGE,  # Must re-stage to get fresh versions
        requires_state=("all_phase_outputs",),
        notes="Must re-stage (R6) to handle version conflicts",
    ),
    P03PhaseId.R8_EMIT: ResumePolicy(
        phase_id=P03PhaseId.R8_EMIT,
        can_resume=True,
        resume_from=P03PhaseId.R8_EMIT,
        requires_state=("write_results",),
        notes="Idempotent via st_outbox dedup",
    ),
}


# =============================================================================
# ERROR RECOVERY (from Appendix G.4)
# =============================================================================


@dataclass(frozen=True)
class ErrorRecovery:
    """Error recovery specification for a phase/error type combination."""

    phase_id: P03PhaseId
    error_type: str
    strategy: str
    max_retries: int
    backoff: str  # "exponential", "linear", "immediate", "none"


ERROR_RECOVERY_MATRIX: List[ErrorRecovery] = [
    # R0 errors
    ErrorRecovery(P03PhaseId.R0_INIT, "DB_TIMEOUT", "Retry with backoff", 3, "exponential"),
    ErrorRecovery(P03PhaseId.R0_INIT, "LOCK_TIMEOUT", "Wait and retry", 5, "linear"),
    ErrorRecovery(
        P03PhaseId.R0_INIT, "POOL_EXHAUSTED", "Queue, wait for connection", 3, "exponential"
    ),
    # R1 errors
    ErrorRecovery(P03PhaseId.R1_SCORE, "P08_UNAVAILABLE", "Use cached embeddings", 1, "none"),
    ErrorRecovery(P03PhaseId.R1_SCORE, "EMBEDDING_TIMEOUT", "Skip event, log", 0, "none"),
    # R2 errors
    ErrorRecovery(P03PhaseId.R2_CLUSTER, "CLUSTER_TIMEOUT", "Reduce batch, retry", 2, "none"),
    # R3 errors
    ErrorRecovery(P03PhaseId.R3_PRUNE, "SIMHASH_ERROR", "Skip dedup, continue", 0, "none"),
    # R4 errors
    ErrorRecovery(P03PhaseId.R4_KG, "NER_TIMEOUT", "Skip entities, continue", 0, "none"),
    # R5 errors
    ErrorRecovery(P03PhaseId.R5_DREAM, "MCTS_TIMEOUT", "Skip R5, continue", 0, "none"),
    # R6 errors
    ErrorRecovery(P03PhaseId.R6_STAGE, "VERSION_CONFLICT", "Re-read, re-stage", 3, "immediate"),
    ErrorRecovery(
        P03PhaseId.R6_STAGE, "UNIQUE_VIOLATION", "Check existing, skip/merge", 1, "immediate"
    ),
    # R7 errors
    ErrorRecovery(P03PhaseId.R7_WRITE, "TRANSACTION_FAIL", "Full cycle retry", 3, "exponential"),
    ErrorRecovery(
        P03PhaseId.R7_WRITE, "SERIALIZATION_FAIL", "Retry with fresh read", 3, "immediate"
    ),
    # R8 errors
    ErrorRecovery(P03PhaseId.R8_EMIT, "BUS_UNAVAILABLE", "Queue locally, retry", 10, "exponential"),
]


# =============================================================================
# R6-SPECIFIC RETRY CONFIGURATION (Issue 5.2.W6)
# =============================================================================


@dataclass(frozen=True)
class R6RetryConfig:
    """
    R6-specific retry configuration per error type.

    M5 Issue 5.2.W6: Targeted recovery for R6 staging errors.
    """

    max_retries: int
    backoff: str  # "immediate" or "exponential"
    strategy: str  # Recovery strategy description


# R6 retry configuration per error type
R6_RETRY_CONFIGS: Dict[P03ErrorType, R6RetryConfig] = {
    P03ErrorType.R6_VERSION_CONFLICT: R6RetryConfig(
        max_retries=3,
        backoff="immediate",
        strategy="re_read_re_stage",
    ),
    P03ErrorType.R6_UNIQUE_VIOLATION: R6RetryConfig(
        max_retries=1,
        backoff="immediate",
        strategy="check_existing_skip_merge",
    ),
    P03ErrorType.R6_MANIFEST_INVALID: R6RetryConfig(
        max_retries=0,
        backoff="immediate",
        strategy="dlq_immediately",
    ),
}

# DLQ threshold: >10% version conflicts triggers DLQ (per Appendix G.4)
R6_DLQ_CONFLICT_THRESHOLD: float = 0.10


def classify_r6_error(error_message: str) -> P03ErrorType:
    """
    Classify R6 error from error message for retry logic.

    Args:
        error_message: Error message string

    Returns:
        P03ErrorType classification
    """
    msg_lower = error_message.lower()
    if "version" in msg_lower or "optimistic" in msg_lower or "stale" in msg_lower:
        return P03ErrorType.R6_VERSION_CONFLICT
    if "unique" in msg_lower or "duplicate" in msg_lower or "already exists" in msg_lower:
        return P03ErrorType.R6_UNIQUE_VIOLATION
    if "manifest" in msg_lower or "validation" in msg_lower or "invalid" in msg_lower:
        return P03ErrorType.R6_MANIFEST_INVALID
    return P03ErrorType.GENERIC


# =============================================================================
# DECISION SUMMARY
# =============================================================================

"""
## Issue 1.2.1 Decision Summary

### Decision: (A) Dedicated P03Pipeline with internal sequential runner

### Rationale:

1. **Sequential vs Parallel**: The generic DAG runner (`k0/runtime/pipeline_runner.py`)
   uses parallel-by-level execution. P03 requires STRICT sequential R0→R8 execution.

2. **Skip Transitions**: P03 has specific conditional skip paths:
   - R2 → R6 (batch_size < 2)
   - R4 → R6 (backlogged, skip R5)
   These are not expressible in the generic DAG model.

3. **Phase State Machine**: Each phase has INIT/PROC/SKIP/FAIL/DONE states
   with specific recovery semantics that need custom handling.

4. **Resume Semantics**: Resume from a failed phase requires understanding
   which earlier phases' outputs are still valid (checkpoint dependencies).

5. **Idempotency Keys**: Each phase has a specific idempotency key format
   that must be tracked for exactly-once semantics.

### Implementation Plan (Issues 1.2.2-1.2.8):

1. **1.2.2**: Define P03Phase interface (run, should_skip, idempotency_key)
2. **1.2.3**: Implement P03SequentialRunner core orchestration
3. **1.2.4**: Implement checkpoint persistence (SQLite or st_pipeline_status)
4. **1.2.5**: Implement phase timeline recording for metrics
5. **1.2.6**: Implement P03 stub phases (R0-R8 with no-op implementations)
6. **1.2.7**: Integration test: full cycle runs R0→R8
7. **1.2.8**: Integration test: resume from checkpoint

### Contract Table (Appendix G.2 Summary):

| Phase | Inputs | Outputs | Idempotency Key | Retry | Timeout | Skip |
|-------|--------|---------|-----------------|-------|---------|------|
| R0 | st_hipp_events | BatchContext | p03:cycle:{cycle_id} | 3x | 30s | Never |
| R1 | R0 event_ids | ScoredEvents | p03:r1:{cycle_id}:{batch_hash} | 3x | 60s | Never |
| R2 | R1 scored | Clusters | p03:r2:{cycle_id}:{batch_hash} | 2x | 120s | batch<2 |
| R3 | R2 clusters | PruneDecisions | p03:r3:{cycle_id}:{batch_hash} | 3x | 60s | Never |
| R4 | R2,R3 | KGUpdates | p03:r4:{cycle_id}:{batch_hash} | 3x | 90s | Never |
| R5 | R2-R4 | DreamResults | p03:r5:{cycle_id}:{batch_hash} | 3x | 120s | Backlog |
| R6 | R1-R5 | StagedWrites | p03:r6:{cycle_id}:{event_id} | 3x | 30s | Never |
| R7 | R6 staged | WriteResult | p03:r7:{cycle_id}:{table}:{id} | 3x | 60s | Never |
| R8 | R7 result | EmitResult | p03:r8:{cycle_id}:{topic}:{offset} | 10x | 30s | Never |

### Persistence Surfaces:

- **st_pipeline_status**: Cycle status, current phase, started_at, updated_at
- **st_p03_checkpoints**: Phase snapshots for resume (new table)
- **st_dlq**: Failed cycles after max retries (existing)

"""
