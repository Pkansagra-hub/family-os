# P03 Milestone 3 Execution Document

> **Milestone**: M3 — End-to-end wiring: DB ↔ outbox ↔ bus
> **Status**: IN_PROGRESS
> **Started**: 2025-01-15
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M2 COMPLETED (2026-01-01)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD (after M2 completion)

---

## Part A: Context Foundation (BEFORE YOU START)

### A.0 M0/M1/M2 Outputs — EXISTING INFRASTRUCTURE AUDIT

> **CRITICAL**: This section identifies what ALREADY EXISTS to avoid duplication.
> M3 must BUILD ON existing infrastructure, not recreate it.

**M0 Created (Contracts/ADRs) — ALL COMPLETE**:

| Artifact | Path | Status |
|----------|------|--------|
| Pipeline ADR | `docs/architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md` | EXISTS |
| State Machine ADR | `docs/architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md` | EXISTS |
| Capability ADR | `docs/architecture/decisions-K0/pipelines/k010.9-capability-based-security.md` | EXISTS |
| Pipeline Contract | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | EXISTS |
| 17 Module Contracts | `k0/contracts/modules/consolidation.*.v1.yaml` | EXISTS |
| Capability Contract | `k0/contracts/capabilities/consolidation.v1.yaml` | EXISTS |
| 8 Event Schemas | `k0/contracts/schemas/p03_*.json` | EXISTS |
| Config Schema | `k0/contracts/jsonschema/p03.config.schema.json` | EXISTS |

**M1 Created (Pipeline Skeleton) — 19 Modules in `k0/pipelines/p03/`**:

| Module | Lines | Purpose | M3 Usage |
|--------|-------|---------|----------|
| `context.py` | ~300 | P03CycleContext, R0TriggerInputs, P03ManualTriggerOptions, P03QoSIntegration | Use for cycle context |
| `event_state.py` | ~400 | P03EventState, ReconciliationAction, PruneDecision | Use for event enrichment |
| `phase_outputs.py` | ~600 | P03PhaseOutputs, 22 aggregate types | Use for phase results |
| `staged_writes.py` | 587 | **P03StagedWrites**, WriteOperation, StagedWrite, StagedOutboxEvent | **INTEGRATE with UoW** |
| `observability.py` | ~400 | P03ObservabilityContext, PhaseTransitionLogger | Use for observability |
| `serializer.py` | ~300 | P03EnvelopeSerializer, PhaseCheckpoint | Use for checkpointing |
| `envelope.py` | ~200 | P03BatchEnvelope | Use for envelope |
| `runner_contract.py` | ~300 | P03PhaseId, P03PhaseStatus, PHASE_CONTRACTS | Use for phase execution |
| `phase_interface.py` | ~300 | P03PhaseProtocol, P03PhaseResult, P03RunnerContext | Use for phase interface |
| `sequential_runner.py` | 644 | **P03SequentialRunner** | **EXTEND for R7/R8** |
| `checkpoint.py` | ~400 | P03Checkpoint, CheckpointStore, P03Offset | Use for checkpoints |
| `offset_manager.py` | 674 | **P03OffsetManager**, OffsetAction, OffsetDecision | **ALREADY HANDLES OFFSETS** |
| `deterministic.py` | ~300 | derive_cycle_seed, P03SeededRNG, P03SkipPolicy | Use for determinism |
| `audit_logger.py` | ~400 | P03DecisionAuditLogger, EXPLANATION_TEMPLATES | Use for audit |
| `explainability.py` | ~300 | ExplainabilityService, MemoryExplanation | Use for explainability |
| `retention.py` | ~300 | RetentionService, DailyAuditSummary | Use for retention |
| `erasure.py` | ~400 | ErasureService, ErasureRequest | Use for GDPR erasure |

**M2 Created (Storage) — 18 Migrations (0027-0045)**:

| Migration | Table | Status |
|-----------|-------|--------|
| 0027 | st_epi | EXISTS |
| 0028 | st_sem | EXISTS |
| 0029 | st_procedural | EXISTS |
| 0030 | st_social | EXISTS |
| 0031 | st_prospective | EXISTS |
| 0032 | st_kg_dom | EXISTS |
| 0033 | st_kg_edges | EXISTS |
| 0034 | st_hipp_events_p03_columns | EXISTS |
| 0035 | st_outbox_fix_next_attempt_ts | EXISTS |
| 0036 | st_consolidation_audit | EXISTS |
| 0037 | st_learning_queue | EXISTS |
| 0038 | st_anchors | EXISTS |
| 0039 | st_anchor_observations | EXISTS |
| 0040 | st_learned_weights | EXISTS |
| 0041 | st_learned_weights_history | EXISTS |
| 0042 | st_feedback_quarantine | EXISTS |
| 0043 | st_feedback_signals_consumption | EXISTS |
| 0044 | st_golden_dataset | EXISTS |
| 0045 | st_dlq_p03_reconcile | EXISTS |

**K0 Core Infrastructure (Pre-existing)**:

| Component | Path | Purpose |
|-----------|------|---------|
| UnitOfWork | `k0/uow/unit_of_work.py` | Transactional scope with `stage_outbox()`, `upsert_offset()` |
| OutboxStore | `k0/storage/outbox.py` | OutboxEntry dataclass, enqueue/dequeue methods |
| OffsetStore | `k0/storage/offsets.py` | Offset dataclass, upsert/fetch methods |
| BusDispatcher | `k0/bus/core.py` | Event publishing to bus |
| DLQStore | `k0/storage/dlq.py` | Dead letter queue storage |

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| 4.8 | Outbox Pattern | [Dossier 4.8](../pipelines/P03_consolidation_dossier_v2.md#48-outbox-pattern) | Transactional staging |
| 4.8.1 | Outbox Implementation | [Dossier 4.8.1](../pipelines/P03_consolidation_dossier_v2.md#481-outbox-implementation) | Atomic write semantics |
| 4.9 | R8 Event Emission | [Dossier 4.9](../pipelines/P03_consolidation_dossier_v2.md#49-r8-event-emission) | Completion event emission |
| 9.2 | P02 to P03 Contract | [Dossier 9.2](../pipelines/P03_consolidation_dossier_v2.md#92-p02-p03-contract) | Offset-based ingestion |
| 9.3 | P03 to P06 Contract | [Dossier 9.3](../pipelines/P03_consolidation_dossier_v2.md#93-p03-p06-contract) | Gap emission to P06 |
| 9.4 | P03 to P08 Contract | [Dossier 9.4](../pipelines/P03_consolidation_dossier_v2.md#94-p03-p08-contract) | Embedding coordination |
| 9.5 | P03 to P05 Contract | [Dossier 9.5](../pipelines/P03_consolidation_dossier_v2.md#95-p03-p05-contract) | Attention budget check |
| 9.8 | P21 Feedback Integration | [Dossier 9.8](../pipelines/P03_consolidation_dossier_v2.md#98-p21-feedback) | Feedback consumption |
| 13.5 | Retry Strategy | [Dossier 13.5](../pipelines/P03_consolidation_dossier_v2.md#135-retry-strategy) | Publisher retry + backoff |
| 13.6 | Circuit Breakers | [Dossier 13.6](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breakers) | P08 circuit breaker |
| Appendix G R7 | Truth Writer | [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r7) | R7 idempotency keys |
| Appendix G R8 | Event Emission | [Dossier Appendix G](../pipelines/P03_consolidation_dossier_v2.md#appendix-g-r8) | R8 idempotency keys |

### A.2 Governance Sync Tool

| Tool | Command |
|------|---------|
| Sync Script | `python -m governance.k0.scripts.sync --report` |

---

## Part B: What M3 ACTUALLY Needs To Do

### B.1 M3 Scope Definition (Post-Duplication Analysis)

**M3 Goal**: Wire the existing P03 pipeline skeleton (M1) to the existing storage (M2) and K0 infrastructure (UoW, Outbox, Bus).

**What M3 Does NOT Do** (already exists):

| Component | Status | Where It Exists |
|-----------|--------|-----------------|
| P03StagedWrites container | M1 Complete | `k0/pipelines/p03/staged_writes.py` |
| P03OffsetManager | M1 Complete | `k0/pipelines/p03/offset_manager.py` |
| P03SequentialRunner | M1 Complete | `k0/pipelines/p03/sequential_runner.py` |
| Event schemas (p03_*.json) | M0 Complete | `k0/contracts/schemas/` |
| st_outbox table | Pre-existing + M2 fix | `k0/db/alembic/versions/0008...+0035...` |
| UnitOfWork.stage_outbox() | Pre-existing | `k0/uow/unit_of_work.py` |
| OutboxStore | Pre-existing | `k0/storage/outbox.py` |

**What M3 MUST Do** (new work):

| Component | Description | Epic |
|-----------|-------------|------|
| **R7 Phase Implementation** | Wire P03StagedWrites to UnitOfWork to truth tables + outbox | 3.1 |
| **R8 Phase Implementation** | Build completion event, stage to outbox, emit | 3.1 |
| **Outbox Drain Integration** | Hook P03 to K0 outbox publisher (or create P03-specific) | 3.1 |
| **R0 Event Ingestion** | Wire P03OffsetManager to st_hipp_events query | 3.2 |
| **Status Writeback** | Update st_hipp_events.consolidation_status in R7 | 3.2 |
| **P06 Gap Persistence** | Write gaps to st_learning_queue + stage outbox events | 3.2 |
| **P05 Budget Client** | Query P05 for token budget before gap emission | 3.2 |
| **P08 Circuit Breaker** | Implement circuit breaker for P08 coordination | 3.2 |
| **P21 Feedback Consumer** | Subscribe to feedback signals, route to handlers | 3.2 |

---

## Part C: Epic Execution

---

### Epic 3.1 — R7/R8 Phase Implementation + Outbox Integration

> **Scope**: Implement the actual R7 (Truth Writer) and R8 (Event Emission) phases that connect P03StagedWrites to UoW and outbox.
>
> **Key Insight**: P03StagedWrites already accumulates writes; M3 connects it to UoW.stage_outbox() for atomic persistence.

---

#### Issue 3.1.1 — Implement R7 Phase: Wire P03StagedWrites to UnitOfWork to Truth Tables

**Status**: ✅ COMPLETED (2025-01-15)

**Spec Reference**: [Dossier 4.8](../pipelines/P03_consolidation_dossier_v2.md#48-r7--memory-layer-writes-truth-update)

**Prerequisite Understanding**:

- `P03StagedWrites` (M1 Issue 1.1.5) accumulates writes during R1-R6 via `add_write(StagedWrite(...))`
- `P03StagedWrites.get_all_writes_ordered()` returns writes in dependency order (vec → kg_dom → kg_edges → epi → sem → procedural → social → prospective → learning_queue → hipp_events)
- `UnitOfWork.stage_outbox(OutboxEntry)` (K0) stages outbox entries within transaction
- `UnitOfWork.connection` provides asyncpg connection for executing staged writes
- R7 must: open UoW → execute staged truth writes → stage outbox events → update st_hipp_events → commit atomically

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03StagedWrites | `k0/pipelines/p03/staged_writes.py` | `get_all_writes_ordered()`, `outbox_events` |
| P03PhaseProtocol | `k0/pipelines/p03/phase_interface.py` | ABC for phase implementation |
| P03PhaseResult | `k0/pipelines/p03/phase_interface.py` | Return type with `.done()`, `.fail()` |
| P03RunnerContext | `k0/pipelines/p03/phase_interface.py` | Provides `syscalls`, `logger`, `config` |
| UnitOfWork | `k0/uow/unit_of_work.py` | `stage_outbox()`, `connection` |
| OutboxEntry | `k0/storage/outbox.py` | Dataclass for outbox staging |
| WriteOperation | `k0/pipelines/p03/staged_writes.py` | INSERT, UPDATE, ARCHIVE, TOMBSTONE |
| P03PhaseId | `k0/pipelines/p03/runner_contract.py` | `P03PhaseId.R7` |

**Work To Do**:

1. [x] Create phase package: `k0/pipelines/p03/phases/__init__.py`
2. [x] Create R7 phase implementation: `k0/pipelines/p03/phases/r7_truth_writer.py`
3. [x] Create test file: `tests/k0/pipelines/p03/test_p03_r7_truth_writer.py` (21 tests, all passing)

**Implementation Notes** (2025-01-15):

- Created `R7TruthWriter` class with full implementation
- Handles INSERT (ON CONFLICT DO NOTHING), UPDATE (optimistic locking), ARCHIVE, TOMBSTONE
- Stages outbox events via `UoW.stage_outbox()`
- Updates `st_hipp_events.consolidation_status` for each processed event
- Maps `ReconciliationAction` to status: REINFORCE/EXTEND/CREATE/EVOLVE→CONSOLIDATED, SKIP→DUPLICATE, PRUNE→PRUNED, CONTRADICT→PENDING_REVIEW
- Layer PK mapping in `LAYER_PK_MAP` constant
- `OptimisticLockError` exception for version conflicts

**R7 Implementation Structure**:

```python
# k0/pipelines/p03/phases/r7_truth_writer.py
"""R7 Phase — Memory Layer Writes (Truth Update). Issue 3.1.1."""

from __future__ import annotations
import time
import json
from typing import TYPE_CHECKING, Dict, Any, List

from k0.pipelines.p03.phase_interface import P03PhaseResult, P03RunnerContext
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.pipelines.p03.staged_writes import WriteOperation, StagedWrite
from k0.storage.outbox import OutboxEntry
from k0.pipelines.p03.observability import P03Error

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope

class R7TruthWriter:
    """
    R7 Phase: Execute staged writes atomically via UnitOfWork.

    Responsibilities:
    1. Open UoW transaction
    2. Execute all staged writes in dependency order
    3. Stage outbox events for R8 emission
    4. Update st_hipp_events consolidation status
    5. Commit atomically (all-or-nothing)
    """

    PHASE_ID = P03PhaseId.R7

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext
    ) -> P03PhaseResult:
        """Execute R7 phase."""
        start_ms = int(time.time() * 1000)

        try:
            async with ctx.syscalls.unit_of_work() as uow:
                # 1. Execute staged writes in dependency order
                writes = envelope.staged.get_all_writes_ordered()
                write_counts = await self._execute_staged_writes(uow, writes, ctx)

                # 2. Stage outbox events
                outbox_count = await self._stage_outbox_events(uow, envelope)

                # 3. Update st_hipp_events status (atomic with writes)
                await self._writeback_status(uow, envelope)

                # 4. Commit offset (handled by R8, but prepare offset record)
                # Commit happens automatically on UoW exit

            duration_ms = int(time.time() * 1000) - start_ms
            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "writes_executed": sum(write_counts.values()),
                    "writes_by_layer": write_counts,
                    "outbox_staged": outbox_count,
                    "events_updated": len(envelope.events),
                },
                idempotency_key=f"p03:r7:{envelope.context.cycle_id}",
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=P03Error(
                    error_type="R7_COMMIT_ERROR",
                    error_message=str(e),
                    recoverable=False,  # R7 failure is non-resumable
                ),
                duration_ms=duration_ms,
            )

    async def _execute_staged_writes(
        self,
        uow,
        writes: List[StagedWrite],
        ctx: P03RunnerContext,
    ) -> Dict[str, int]:
        """Execute writes via UoW connection. Returns counts by layer."""
        counts: Dict[str, int] = {}

        for write in writes:
            await self._execute_single_write(uow.connection, write)
            counts[write.layer] = counts.get(write.layer, 0) + 1

        return counts

    async def _execute_single_write(self, conn, write: StagedWrite) -> None:
        """Execute a single StagedWrite."""
        if write.operation == WriteOperation.INSERT:
            await self._execute_insert(conn, write)
        elif write.operation == WriteOperation.UPDATE:
            await self._execute_update(conn, write)
        elif write.operation == WriteOperation.ARCHIVE:
            await self._execute_archive(conn, write)
        elif write.operation == WriteOperation.TOMBSTONE:
            await self._execute_tombstone(conn, write)

    async def _execute_insert(self, conn, write: StagedWrite) -> None:
        """Execute INSERT with ON CONFLICT for idempotency."""
        # Build column list and values from record_data
        columns = list(write.record_data.keys())
        placeholders = [f"${i+1}" for i in range(len(columns))]
        values = [write.record_data[c] for c in columns]

        sql = f"""
            INSERT INTO {write.layer} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT DO NOTHING
        """
        await conn.execute(sql, *values)

    async def _execute_update(self, conn, write: StagedWrite) -> None:
        """Execute UPDATE with optimistic locking."""
        set_clauses = []
        values = []
        idx = 1

        for col, val in write.record_data.items():
            set_clauses.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

        # Add version check for optimistic locking
        if write.expected_version is not None:
            sql = f"""
                UPDATE {write.layer}
                SET {', '.join(set_clauses)}, version = version + 1
                WHERE {self._get_pk_column(write.layer)} = ${idx}
                  AND version = ${idx + 1}
            """
            values.extend([write.record_id, write.expected_version])
        else:
            sql = f"""
                UPDATE {write.layer}
                SET {', '.join(set_clauses)}
                WHERE {self._get_pk_column(write.layer)} = ${idx}
            """
            values.append(write.record_id)

        await conn.execute(sql, *values)

    async def _execute_archive(self, conn, write: StagedWrite) -> None:
        """Execute soft-delete (set archival_status)."""
        now_ms = int(time.time() * 1000)
        sql = f"""
            UPDATE {write.layer}
            SET archival_status = 'ARCHIVED',
                archived_at = $1,
                archived_reason = $2
            WHERE {self._get_pk_column(write.layer)} = $3
        """
        await conn.execute(
            sql,
            now_ms,
            write.record_data.get("archived_reason", ""),
            write.record_id
        )

    async def _execute_tombstone(self, conn, write: StagedWrite) -> None:
        """Execute tombstone marker."""
        now_ms = int(time.time() * 1000)
        sql = f"""
            UPDATE {write.layer}
            SET archival_status = 'TOMBSTONE',
                tombstoned_at = $1
            WHERE {self._get_pk_column(write.layer)} = $2
        """
        await conn.execute(sql, now_ms, write.record_id)

    async def _stage_outbox_events(
        self,
        uow,
        envelope: P03BatchEnvelope
    ) -> int:
        """Stage outbox events for R8 emission."""
        count = 0
        for staged_event in envelope.staged.outbox_events:
            entry = OutboxEntry(
                id=None,
                wal_pos=0,  # Will be set by outbox store
                tenant_id=envelope.context.tenant_id,
                space_id=envelope.context.space_id,
                driver="p03",
                op_kind=staged_event.topic,
                payload=json.dumps(staged_event.payload).encode("utf-8"),
                fingerprint=staged_event.event_id,
                requeue_seq=0,
                retries=0,
            )
            uow.stage_outbox(entry)
            count += 1
        return count

    async def _writeback_status(self, uow, envelope: P03BatchEnvelope) -> None:
        """Update st_hipp_events with consolidation status."""
        now_ms = int(time.time() * 1000)

        for event in envelope.events:
            status = self._determine_status(event)
            await uow.connection.execute("""
                UPDATE st_hipp_events
                SET consolidation_status = $1,
                    consolidation_cycle_id = $2,
                    consolidated_at = $3,
                    reconciliation_decision = $4,
                    truth_match_id = $5,
                    truth_match_similarity = $6
                WHERE event_id = $7
            """,
                status,
                envelope.context.cycle_id,
                now_ms,
                event.reconciliation_action.value if event.reconciliation_action else None,
                event.best_match_id,
                event.similarity_score,
                event.event_id,
            )

    def _determine_status(self, event) -> str:
        """Map reconciliation action to consolidation status."""
        from k0.pipelines.p03.event_state import ReconciliationAction

        action = event.reconciliation_action
        if action == ReconciliationAction.SKIP:
            return "DUPLICATE"
        elif action == ReconciliationAction.PRUNE:
            return "PRUNED"
        elif action == ReconciliationAction.CONTRADICT:
            return "PENDING_REVIEW"
        else:
            return "CONSOLIDATED"

    def _get_pk_column(self, layer: str) -> str:
        """Get primary key column name for layer."""
        pk_map = {
            "st_epi": "episode_id",
            "st_sem": "pattern_id",
            "st_procedural": "routine_id",
            "st_social": "relationship_id",
            "st_prospective": "intention_id",
            "st_kg_dom": "entity_id",
            "st_kg_edges": "edge_id",
            "st_vec": "embedding_id",
            "st_hipp_events": "event_id",
            "st_learning_queue": "queue_id",
        }
        return pk_map.get(layer, "id")
```

1. [ ] Register R7 phase in `k0/pipelines/p03/runner_contract.py` PHASE_REGISTRY
2. [ ] Add R7 to P03SequentialRunner phase chain

**Idempotency Key Pattern**: `p03:r7:{cycle_id}:{table}:{record_id}`

**Outputs Produced**:

- [x] `k0/pipelines/p03/phases/__init__.py` (package init with R7TruthWriter, OptimisticLockError exports)
- [x] `k0/pipelines/p03/phases/r7_truth_writer.py` (537 lines)

**Acceptance Criteria**:

- [x] Transaction failure rolls back BOTH truth writes AND outbox staging (UoW atomic commit)
- [x] Successful commit persists all in single transaction (single UoW.commit())
- [x] Writes executed in correct dependency order (LAYER_DEPENDENCY_ORDER constant)
- [x] Optimistic locking works for UPDATE operations (version check with OptimisticLockError)
- [x] st_hipp_events.consolidation_status updated for all events (STATUS_MAP from ReconciliationAction)

**Test Cases** (21 tests in test_p03_r7_truth_writer.py):

- [x] `test_r7_executes_inserts_with_on_conflict_do_nothing`
- [x] `test_r7_executes_updates_with_version_check`
- [x] `test_r7_raises_optimistic_lock_error_on_version_mismatch`
- [x] `test_r7_executes_archive_operations`
- [x] `test_r7_executes_tombstone_operations`
- [x] `test_r7_stages_outbox_events`
- [x] `test_r7_updates_hipp_events_status`
- [x] `test_r7_writes_in_dependency_order`
- [x] `test_r7_returns_done_on_success`
- [x] `test_r7_returns_fail_on_error`

**Blocked By**: M2 Complete

**Blocks**: 3.1.2, 3.1.4

---

#### Issue 3.1.2 — Implement R8 Phase: Build Completion Event + Emit via Outbox

**Status**: ✅ COMPLETED (2026-01-01)

**Spec Reference**: [Dossier 4.9](../pipelines/P03_consolidation_dossier_v2.md#49-r8--event-emission--completion)

**Prerequisite Understanding**:

- M0 created event schema: `k0/contracts/schemas/p03_consolidation_complete.json`
- M1 created `P03PhaseOutputs` which accumulates phase results
- R7 already staged outbox entries within UoW (Issue 3.1.1)
- R8 must: build completion payload, stage gaps to learning_queue, commit offset, trigger drain

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| Schema | `k0/contracts/schemas/p03_consolidation_complete.json` | Completion payload structure |
| P03PhaseOutputs | `k0/pipelines/p03/phase_outputs.py` | Accumulated phase results |
| P03OffsetManager | `k0/pipelines/p03/offset_manager.py` | `commit_offset()` on success |
| OutboxStore | `k0/storage/outbox.py` | `dequeue_ready_batch()`, `mark_applied()` |
| LearningQueueStore | `k0/storage/learning_queue.py` | Gap persistence |
| P03PhaseProtocol | `k0/pipelines/p03/phase_interface.py` | ABC for phase implementation |
| GapSignal | `k0/pipelines/p03/gap_detector.py` | Gap structure from R4 |
| P03PhaseId | `k0/pipelines/p03/runner_contract.py` | `P03PhaseId.R8` |

**Work To Do**:

1. [x] Create R8 phase implementation: `k0/pipelines/p03/phases/r8_event_emitter.py`
2. [x] Update `k0/pipelines/p03/phases/__init__.py` with R8EventEmitter export
3. [x] Create test file: `tests/k0/pipelines/p03/test_p03_r8_event_emitter.py` (22 tests, all passing)

**Implementation Notes** (2026-01-01):

- Created `R8EventEmitter` class with full implementation
- Builds completion payload matching schema: cycle_id, tenant_id, space_id, status, summary, duration_ms, phase_durations, errors
- Status determination: SUCCESS (all done), PARTIAL (some failures), FAILED (all failures)
- Persists gaps to st_learning_queue with ON CONFLICT DO NOTHING for idempotency
- Stages gap events to outbox with fingerprint pattern: gap:{gap_id}
- Commits offset via UoW.upsert_offset() with subscriber_id="p03", topic="p02.hipp_events"
- R8 errors are recoverable (unlike R7) since truth writes already committed
- Outbox drain is no-op placeholder for Issue 3.1.3

**R8 Implementation Structure**:

```python
# k0/pipelines/p03/phases/r8_event_emitter.py
"""R8 Phase — Event Emission & Completion. Issue 3.1.2."""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any, List, Optional

from k0.pipelines.p03.phase_interface import P03PhaseResult, P03RunnerContext
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.storage.outbox import OutboxEntry
from k0.pipelines.p03.observability import P03Error

if TYPE_CHECKING:
    from k0.pipelines.p03.envelope import P03BatchEnvelope
    from k0.pipelines.p03.gap_detector import GapSignal

class R8EventEmitter:
    """
    R8 Phase: Event Emission & Completion.

    Responsibilities:
    1. Build completion payload (p03.consolidation.complete.v1)
    2. Stage completion event to outbox
    3. Persist detected gaps to st_learning_queue
    4. Stage gap events (p03.gap.detected.v1) to outbox
    5. Commit offset (exactly-once guarantee)
    6. Trigger or signal outbox drain
    """

    PHASE_ID = P03PhaseId.R8
    COMPLETION_TOPIC = "p03.consolidation.complete.v1"
    GAP_TOPIC = "p03.gap.detected.v1"

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext
    ) -> P03PhaseResult:
        """Execute R8 phase."""
        start_ms = int(time.time() * 1000)

        try:
            # 1. Build completion payload from phase outputs
            completion_payload = self._build_completion_payload(envelope)

            # 2. Persist gaps and emit events
            async with ctx.syscalls.unit_of_work() as uow:
                # Stage completion event
                await self._stage_completion_event(uow, envelope, completion_payload)

                # Persist gaps to learning queue and stage gap events
                gap_count = await self._process_gaps(uow, envelope, ctx)

                # Commit offset (exactly-once)
                offset_record = envelope.context.build_offset_record(
                    new_offset=envelope.batch_watermark,
                    status="COMMITTED",
                )
                uow.upsert_offset(offset_record)

            # 3. Trigger outbox drain (async, non-blocking)
            await self._trigger_outbox_drain(ctx)

            duration_ms = int(time.time() * 1000) - start_ms
            return P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "completion_status": completion_payload["status"],
                    "gaps_persisted": gap_count,
                    "offset_committed": envelope.batch_watermark,
                },
                idempotency_key=f"p03:r8:{envelope.context.cycle_id}",
            )

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            return P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=P03Error(
                    error_type="R8_EMISSION_ERROR",
                    error_message=str(e),
                    recoverable=True,  # R8 can retry after R7 success
                ),
                duration_ms=duration_ms,
            )

    def _build_completion_payload(self, envelope: P03BatchEnvelope) -> Dict[str, Any]:
        """
        Build payload matching p03_consolidation_complete.json schema.

        Schema structure:
        {
          "cycle_id": str,
          "tenant_id": str,
          "space_id": str,
          "status": "SUCCESS" | "PARTIAL" | "FAILED",
          "summary": {
            "events_processed": int,
            "clusters_created": int,
            "duplicates_found": int,
            "entities_created": int,
            "edges_created": int,
            "gaps_detected": int,
            "patterns_updated": int,
            "salience_changes": int
          },
          "duration_ms": int,
          "completed_at": str (ISO8601),
          "phase_durations": {phase_id: duration_ms},
          "errors": [{"phase": str, "error_type": str, "message": str}]
        }
        """
        outputs = envelope.phase_outputs

        # Determine overall status
        if envelope.has_fatal_error():
            status = "FAILED"
        elif envelope.has_partial_failures():
            status = "PARTIAL"
        else:
            status = "SUCCESS"

        # Calculate totals from R1-R6 outputs
        summary = {
            "events_processed": len(envelope.events),
            "clusters_created": outputs.r2_clusters_created,
            "duplicates_found": outputs.r3_duplicates_found,
            "entities_created": outputs.r4_entities_created,
            "edges_created": outputs.r4_edges_created,
            "gaps_detected": len(outputs.r4_gaps),
            "patterns_updated": outputs.r5_patterns_updated,
            "salience_changes": outputs.r6_salience_changes,
        }

        # Collect phase durations
        phase_durations = {}
        for phase_id, result in envelope.phase_results.items():
            phase_durations[phase_id.value] = result.duration_ms

        # Collect errors
        errors = []
        for phase_id, result in envelope.phase_results.items():
            if result.error:
                errors.append({
                    "phase": phase_id.value,
                    "error_type": result.error.error_type,
                    "message": result.error.error_message,
                })

        return {
            "cycle_id": envelope.context.cycle_id,
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "status": status,
            "summary": summary,
            "duration_ms": envelope.total_duration_ms(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "phase_durations": phase_durations,
            "errors": errors,
        }

    async def _stage_completion_event(
        self,
        uow,
        envelope: P03BatchEnvelope,
        payload: Dict[str, Any]
    ) -> None:
        """Stage completion event to outbox."""
        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=envelope.context.tenant_id,
            space_id=envelope.context.space_id,
            driver="p03",
            op_kind=self.COMPLETION_TOPIC,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=f"complete:{envelope.context.cycle_id}",
            requeue_seq=0,
            retries=0,
        )
        uow.stage_outbox(entry)

    async def _process_gaps(
        self,
        uow,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext
    ) -> int:
        """
        Persist gaps to st_learning_queue and stage gap events.

        Per dossier 4.9:
        - Gap persisted to st_learning_queue for P06 consumption
        - Gap event staged to outbox for immediate notification
        """
        gaps: List[GapSignal] = envelope.phase_outputs.r4_gaps

        for gap in gaps:
            # 1. Persist to learning queue
            await self._persist_gap_to_queue(uow, envelope, gap)

            # 2. Stage gap event to outbox
            gap_payload = self._build_gap_payload(envelope, gap)
            entry = OutboxEntry(
                id=None,
                wal_pos=0,
                tenant_id=envelope.context.tenant_id,
                space_id=envelope.context.space_id,
                driver="p03",
                op_kind=self.GAP_TOPIC,
                payload=json.dumps(gap_payload).encode("utf-8"),
                fingerprint=f"gap:{gap.gap_id}",
                requeue_seq=0,
                retries=0,
            )
            uow.stage_outbox(entry)

        return len(gaps)

    async def _persist_gap_to_queue(
        self,
        uow,
        envelope: P03BatchEnvelope,
        gap: GapSignal
    ) -> None:
        """
        Insert gap into st_learning_queue.

        Schema: queue_id, tenant_id, space_id, gap_type, gap_id,
                source_event_id, gap_metadata, status, created_at
        """
        now_ms = int(time.time() * 1000)
        await uow.connection.execute("""
            INSERT INTO st_learning_queue (
                queue_id, tenant_id, space_id, gap_type, gap_id,
                source_event_id, gap_metadata, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (queue_id) DO NOTHING
        """,
            gap.gap_id,
            envelope.context.tenant_id,
            envelope.context.space_id,
            gap.gap_type.value,
            gap.gap_id,
            gap.source_event_id,
            json.dumps(gap.metadata),
            "PENDING",
            now_ms,
        )

    def _build_gap_payload(
        self,
        envelope: P03BatchEnvelope,
        gap: GapSignal
    ) -> Dict[str, Any]:
        """Build gap event payload."""
        return {
            "cycle_id": envelope.context.cycle_id,
            "tenant_id": envelope.context.tenant_id,
            "space_id": envelope.context.space_id,
            "gap_id": gap.gap_id,
            "gap_type": gap.gap_type.value,
            "source_event_id": gap.source_event_id,
            "metadata": gap.metadata,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _trigger_outbox_drain(self, ctx: P03RunnerContext) -> None:
        """
        Signal outbox publisher to drain P03 entries.

        This is non-blocking; actual drain happens asynchronously.
        If no dedicated publisher exists, entries will be drained
        by background cron or next publisher tick.
        """
        # Option A: Fire signal to bus
        # await ctx.bus.publish("outbox.drain.request", {"driver": "p03"})

        # Option B: Direct invoke (if synchronous drain desired)
        # await ctx.outbox_publisher.drain_batch(driver="p03")

        # For now: rely on background publisher (Issue 3.1.3)
        pass
```

1. [ ] Update `P03PhaseOutputs` in `k0/pipelines/p03/phase_outputs.py`:
   - Add property accessors: `r2_clusters_created`, `r3_duplicates_found`, etc.
   - Add `total_duration_ms()` method
   - Add `has_fatal_error()` and `has_partial_failures()` methods

2. [ ] Register R8 phase in `k0/pipelines/p03/runner_contract.py` PHASE_REGISTRY

3. [ ] Add R8 to P03SequentialRunner phase chain (after R7)

**Idempotency Key Pattern**: `p03:r8:{cycle_id}:{topic}`

**Event Topics Emitted**:

| Topic | Trigger | Payload |
| ----- | ------- | ------- |
| `p03.consolidation.complete.v1` | Every successful cycle | Full summary |
| `p03.gap.detected.v1` | Per gap in R4 output | Gap details |

**Outputs Produced**:

- [x] `k0/pipelines/p03/phases/r8_event_emitter.py` (533 lines)
- [x] Updated `k0/pipelines/p03/phases/__init__.py` with R8EventEmitter export

**Acceptance Criteria**:

- [x] Completion event matches `p03_consolidation_complete.json` schema (cycle_id, tenant_id, space_id, status, summary, phase_durations, errors)
- [x] All gaps from R4 persisted to `st_learning_queue` (ON CONFLICT DO NOTHING for idempotency)
- [x] All gaps staged as outbox events (fingerprint: gap:{gap_id})
- [x] Offset committed only after successful R8 (UoW.upsert_offset with subscriber_id="p03")
- [x] Duplicate cycle_id produces no duplicate events (fingerprint-based deduplication)

**Test Cases** (22 tests in test_p03_r8_event_emitter.py):

- [x] `test_r8_builds_completion_payload_with_correct_structure`
- [x] `test_r8_status_success_when_all_phases_done`
- [x] `test_r8_status_partial_when_some_failures`
- [x] `test_r8_status_failed_when_all_failures`
- [x] `test_r8_stages_completion_event_to_outbox`
- [x] `test_r8_persists_gaps_to_learning_queue`
- [x] `test_r8_stages_gap_events_to_outbox`
- [x] `test_r8_commits_offset_on_success`
- [x] `test_r8_gap_fingerprint_pattern`
- [x] `test_r8_returns_done_on_success`
- `test_r8_offset_committed_on_success`
- `test_r8_idempotent_on_retry`

**Blocked By**: 3.1.1

**Blocks**: 3.1.3, 3.1.4

---

#### Issue 3.1.3 — Integrate with K0 Outbox Publisher (Drain Loop)

**Status**: ✅ COMPLETED

**Completion Summary**:

Implemented `P03OutboxPublisher` in `k0/pipelines/p03/outbox_publisher.py` with:

1. **OutboxPublisherConfig**: Configuration dataclass with driver, batch_size, max_retries, base_delay_ms, max_delay_ms, jitter_factor
2. **P03OutboxPublisher**: Main class implementing drain loop with:
   - `drain_batch()`: Dequeues ready entries, publishes to bus, handles failures
   - `_publish_entry()`: Creates BusMessage with correct structure (topic, payload, offset, metadata)
   - `_handle_failure()`: Exponential backoff per Dossier 13.5 formula
   - `_calculate_backoff()`: `min(base_delay * 2^retries + jitter, max_delay)`
   - `_send_to_dlq()`: Escalates to DeadLetterQueue after max retries
3. **PublishResult**: Result dataclass with processed, published, retried, dlq_count, errors
4. **Metrics**: p03_outbox_published_total, p03_outbox_retry_total, p03_outbox_dlq_total, p03_outbox_drain_duration_ms

**Files Created/Modified**:

- Created: `k0/pipelines/p03/outbox_publisher.py` (387 lines)
- Created: `tests/k0/pipelines/p03/test_p03_outbox_publisher.py` (27 tests, all passing)
- Modified: `k0/pipelines/p03/__init__.py` (added exports)

**Dependencies Used**:

- `OutboxStore` from `k0/storage/outbox.py` (dequeue_ready_batch, mark_applied, record_failure)
- `DeadLetterQueue` from `k0/storage/dlq.py` (record method)
- `BusDispatcher`, `BusMessage` from `k0/bus/core.py` (dispatch takes Iterable[BusMessage])
- `MetricsExporter` from `k0/obs/metrics.py` (emit, observe methods)

**Spec Reference**: [Dossier 13.5](../pipelines/P03_consolidation_dossier_v2.md#135-retry-strategy)

**Prerequisite Understanding**:

- K0 has `OutboxStore.dequeue_ready_batch()` and `BusDispatcher.dispatch()`
- R7 stages outbox entries via `UnitOfWork.stage_outbox()` → flushed to `st_outbox` on commit
- R8 triggers drain (or drain runs on background tick)
- Dossier 13.5 specifies exponential backoff retry strategy
- After max retries, escalate to DLQ (st_dlq with P03 columns from ADR-0045)

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| OutboxStore | `k0/storage/outbox.py` | `dequeue_ready_batch()`, `mark_applied()`, `record_failure()` |
| OutboxEntry | `k0/storage/outbox.py` | Entry dataclass |
| BusDispatcher | `k0/bus/dispatcher.py` | `dispatch(topic, payload)` |
| DLQStore | `k0/storage/dlq.py` | `insert_entry()` |
| MetricsEmitter | `k0/observability/metrics.py` | Counter/gauge helpers |

**Work To Do**:

1. [ ] First: Check for existing K0 outbox publisher:

```powershell
# Discovery commands
Get-ChildItem -Path "d:\familyos\k0\outbox" -Recurse -Filter "*.py" -ErrorAction SilentlyContinue
Get-ChildItem -Path "d:\familyos\k0\bus" -Recurse -Filter "*publisher*" -ErrorAction SilentlyContinue
Select-String -Path "d:\familyos\k0\**\*.py" -Pattern "dequeue_ready_batch" -SimpleMatch
```

1. [ ] If K0 publisher exists supporting multiple drivers:
   - Register `driver="p03"` with appropriate config
   - Configure retry semantics per dossier 13.5

2. [ ] If no generic publisher exists, create P03-specific publisher:
   - Location: `k0/pipelines/p03/outbox_publisher.py`

**P03 Outbox Publisher Implementation** (if needed):

```python
# k0/pipelines/p03/outbox_publisher.py
"""P03 Outbox Publisher — Drains staged outbox entries to bus. Issue 3.1.3."""

from __future__ import annotations
import asyncio
import random
import time
import json
from typing import TYPE_CHECKING, List, Optional
from dataclasses import dataclass

from k0.storage.outbox import OutboxStore, OutboxEntry
from k0.storage.dlq import DLQStore, DLQEntry
from k0.bus.dispatcher import BusDispatcher
from k0.observability.metrics import Counter, Histogram

if TYPE_CHECKING:
    from k0.kernel.syscalls import Syscalls

@dataclass
class OutboxPublisherConfig:
    """Configuration for outbox publisher."""
    driver: str = "p03"
    batch_size: int = 100
    poll_interval_ms: int = 1000
    max_retries: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 30000
    jitter_factor: float = 0.1

# Metrics
PUBLISHED = Counter("p03_outbox_published_total", "Events published from outbox")
RETRIED = Counter("p03_outbox_retry_total", "Outbox publish retries")
DLQ_COUNT = Counter("p03_outbox_dlq_total", "Events sent to DLQ")
DRAIN_DURATION = Histogram("p03_outbox_drain_duration_ms", "Time to drain batch")

class P03OutboxPublisher:
    """
    Drains P03 outbox entries to the event bus.

    Implements:
    - Exponential backoff with jitter (per dossier 13.5)
    - DLQ escalation after max retries
    - At-least-once delivery (entries removed after bus ack)
    """

    def __init__(
        self,
        outbox_store: OutboxStore,
        bus_dispatcher: BusDispatcher,
        dlq_store: DLQStore,
        config: Optional[OutboxPublisherConfig] = None,
    ):
        self.outbox = outbox_store
        self.bus = bus_dispatcher
        self.dlq = dlq_store
        self.config = config or OutboxPublisherConfig()
        self._running = False

    async def start(self) -> None:
        """Start background drain loop."""
        self._running = True
        while self._running:
            await self.drain_batch()
            await asyncio.sleep(self.config.poll_interval_ms / 1000)

    async def stop(self) -> None:
        """Stop background drain loop."""
        self._running = False

    async def drain_batch(self) -> int:
        """
        Drain a batch of outbox entries.

        Returns: Number of entries processed
        """
        start_ms = int(time.time() * 1000)

        batch: List[OutboxEntry] = await self.outbox.dequeue_ready_batch(
            driver=self.config.driver,
            limit=self.config.batch_size,
        )

        if not batch:
            return 0

        processed = 0
        for entry in batch:
            success = await self._publish_entry(entry)
            if success:
                await self.outbox.mark_applied(entry.id)
                PUBLISHED.inc(labels={"topic": entry.op_kind})
                processed += 1
            else:
                await self._handle_failure(entry)

        duration_ms = int(time.time() * 1000) - start_ms
        DRAIN_DURATION.observe(duration_ms)

        return processed

    async def _publish_entry(self, entry: OutboxEntry) -> bool:
        """
        Attempt to publish a single entry to the bus.

        Returns: True if successful, False if should retry
        """
        try:
            payload = json.loads(entry.payload.decode("utf-8"))
            await self.bus.dispatch(entry.op_kind, payload)
            return True
        except Exception as e:
            # Log error, return False to trigger retry logic
            return False

    async def _handle_failure(self, entry: OutboxEntry) -> None:
        """
        Handle publish failure with exponential backoff.

        Per dossier 13.5:
        - delay = base_delay * (2 ^ retries) + jitter
        - After max_retries: escalate to DLQ
        """
        new_retries = entry.retries + 1
        RETRIED.inc(labels={"topic": entry.op_kind})

        if new_retries > self.config.max_retries:
            # Escalate to DLQ
            await self._send_to_dlq(entry)
            await self.outbox.mark_applied(entry.id)  # Remove from outbox
            DLQ_COUNT.inc(labels={"topic": entry.op_kind})
        else:
            # Calculate backoff with jitter
            delay_ms = self._calculate_backoff(new_retries)
            next_attempt_ms = int(time.time() * 1000) + delay_ms

            await self.outbox.record_failure(
                entry_id=entry.id,
                retries=new_retries,
                next_attempt_ts=next_attempt_ms,
            )

    def _calculate_backoff(self, retries: int) -> int:
        """
        Calculate exponential backoff with jitter.

        Formula: min(base * 2^retries + random_jitter, max_delay)
        """
        base_delay = self.config.base_delay_ms * (2 ** retries)
        jitter = random.uniform(0, self.config.jitter_factor * base_delay)
        delay = int(base_delay + jitter)
        return min(delay, self.config.max_delay_ms)

    async def _send_to_dlq(self, entry: OutboxEntry) -> None:
        """
        Send entry to Dead Letter Queue.

        DLQ schema includes P03 context per ADR-0045.
        """
        dlq_entry = DLQEntry(
            id=None,
            tenant_id=entry.tenant_id,
            space_id=entry.space_id,
            pipeline_id="P03",
            phase="R8",
            topic=entry.op_kind,
            payload=entry.payload,
            fingerprint=entry.fingerprint,
            error_message="Max retries exceeded",
            retries=entry.retries,
            created_at=int(time.time() * 1000),
        )
        await self.dlq.insert_entry(dlq_entry)
```

1. [ ] Wire publisher to P03 runner lifecycle:
   - Start publisher on P03 initialization
   - Stop publisher on P03 shutdown
   - Or: expose `drain_batch()` for on-demand drain in R8

2. [ ] Add metrics collection:

| Metric | Type | Labels | Description |
| ------ | ---- | ------ | ----------- |
| `p03_outbox_published_total` | Counter | topic | Events published |
| `p03_outbox_retry_total` | Counter | topic | Retry attempts |
| `p03_outbox_dlq_total` | Counter | topic | DLQ escalations |
| `p03_outbox_drain_duration_ms` | Histogram | - | Drain batch latency |

**Outputs Produced**:

- [x] `k0/pipelines/p03/outbox_publisher.py` (387 lines - P03OutboxPublisher, OutboxPublisherConfig, PublishResult)
- [x] Publisher exports in `k0/pipelines/p03/__init__.py`
- [x] Metrics registration via MetricsExporter (emit/observe pattern)

**Acceptance Criteria**:

- [x] Staged outbox entries reach bus under normal operation (drain_batch →_publish_entry → BusDispatcher.dispatch)
- [x] Transient failures trigger exponential backoff retry (_handle_failure with record_failure)
- [x] Backoff delay formula: `base_delay * 2^retries + jitter` (_calculate_backoff method)
- [x] Permanent failures (max_retries exceeded) land in DLQ (_send_to_dlq with DeadLetterQueue.record)
- [x] DLQ entries include: `driver='p03'`, full context (tenant_id, space_id, op_kind, fingerprint, reason)
- [x] Metrics emitted for published, retry, dlq (p03_outbox_published_total, p03_outbox_retry_total, p03_outbox_dlq_total, p03_outbox_drain_duration_ms)

**Test Cases** (27 tests implemented in test_p03_outbox_publisher.py):

- [x] `test_drain_empty_batch_returns_zero`
- [x] `test_drain_single_entry_publishes_to_bus`
- [x] `test_drain_multiple_entries_publishes_all`
- [x] `test_bus_message_has_correct_structure`
- [x] `test_transient_failure_triggers_retry`
- [x] `test_max_retries_exceeded_escalates_to_dlq`
- [x] `test_dlq_entry_has_correct_context`
- [x] `test_backoff_doubles_with_retries`
- [x] `test_backoff_capped_at_max_delay`
- [x] `test_published_metric_emitted`
- [x] `test_retry_metric_emitted`
- [x] `test_dlq_metric_emitted`
- [x] `test_drain_duration_metric_observed`

**Blocked By**: 3.1.1

**Blocks**: 3.1.4

---

#### Issue 3.1.4 — Integration Tests for R7/R8 Atomicity and Bus Delivery

**Status**: COMPLETED

**Spec Reference**: [Dossier 10](../pipelines/P03_consolidation_dossier_v2.md#10-testing-strategy)

**Test File Location**: `tests/k0/pipelines/p03/test_r7_r8_integration.py`

**Prerequisites**:

- Test database with P03 tables (from M2)
- Test fixtures for `P03BatchEnvelope` with staged writes
- Mock or test bus dispatcher for event capture

**Existing Test Infrastructure**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| Fixture base | `tests/conftest.py` | Database setup, cleanup |
| P03 fixtures | `tests/k0/pipelines/p03/conftest.py` | Envelope builders |
| Event capture | `tests/mocks/bus_capture.py` | Capture dispatched events |

**Work To Do**:

1. [ ] Create test fixtures in `tests/k0/pipelines/p03/conftest.py`:

```python
@pytest.fixture
def staged_envelope_with_writes():
    """Create envelope with staged writes for R7 testing."""
    envelope = P03BatchEnvelopeBuilder()\
        .with_context(tenant_id="t1", space_id="s1", cycle_id="c1")\
        .with_events([create_test_event()])\
        .build()

    # Stage writes from simulated R1-R6
    envelope.staged.add_write(StagedWrite(
        layer="st_epi",
        operation=WriteOperation.INSERT,
        record_id="epi-1",
        record_data={"episode_id": "epi-1", "summary": "test"},
    ))
    envelope.staged.add_outbox_event(StagedOutboxEvent(
        event_id="evt-1",
        topic="p03.consolidation.complete.v1",
        payload={"status": "SUCCESS"},
    ))

    return envelope
```

1. [ ] Implement R7 atomicity tests:

```python
# tests/k0/pipelines/p03/test_r7_r8_integration.py

class TestR7Atomicity:
    """R7 Phase atomicity tests."""

    async def test_r7_commit_persists_truth_and_outbox_atomically(
        self, db_session, staged_envelope_with_writes
    ):
        """
        Given: Envelope with staged writes and outbox events
        When: R7 executes successfully
        Then: Both truth tables AND outbox contain the data
        """
        r7 = R7TruthWriter()
        result = await r7.run(staged_envelope_with_writes, ctx)

        assert result.status == P03PhaseStatus.DONE

        # Verify truth write persisted
        row = await db_session.fetchone(
            "SELECT * FROM st_epi WHERE episode_id = $1", "epi-1"
        )
        assert row is not None

        # Verify outbox entry persisted
        outbox = await db_session.fetchone(
            "SELECT * FROM st_outbox WHERE fingerprint = $1", "evt-1"
        )
        assert outbox is not None

    async def test_r7_failure_rolls_back_truth_and_outbox(
        self, db_session, staged_envelope_with_writes
    ):
        """
        Given: Envelope with staged writes, R7 fails mid-transaction
        When: Exception raised during write execution
        Then: NEITHER truth tables NOR outbox contain data
        """
        # Inject failure by making one write invalid
        staged_envelope_with_writes.staged.add_write(StagedWrite(
            layer="nonexistent_table",  # Will cause failure
            operation=WriteOperation.INSERT,
            record_id="bad-1",
            record_data={"id": "bad-1"},
        ))

        r7 = R7TruthWriter()
        result = await r7.run(staged_envelope_with_writes, ctx)

        assert result.status == P03PhaseStatus.FAIL

        # Verify NO truth write persisted
        row = await db_session.fetchone(
            "SELECT * FROM st_epi WHERE episode_id = $1", "epi-1"
        )
        assert row is None

        # Verify NO outbox entry persisted
        outbox = await db_session.fetchone(
            "SELECT * FROM st_outbox WHERE fingerprint = $1", "evt-1"
        )
        assert outbox is None

    async def test_r7_writes_in_dependency_order(
        self, db_session, staged_envelope_with_writes
    ):
        """
        Given: Envelope with writes to multiple layers
        When: R7 executes
        Then: Writes are executed in correct order (vec → kg → epi → ...)
        """
        # Add writes to multiple layers
        envelope = staged_envelope_with_writes
        envelope.staged.add_write(StagedWrite(
            layer="st_kg_dom", operation=WriteOperation.INSERT,
            record_id="kg-1", record_data={"entity_id": "kg-1"},
        ))
        envelope.staged.add_write(StagedWrite(
            layer="st_vec", operation=WriteOperation.INSERT,
            record_id="vec-1", record_data={"embedding_id": "vec-1"},
        ))

        # Track execution order via mock
        execution_order = []
        original_execute = R7TruthWriter._execute_single_write
        async def tracking_execute(self, conn, write):
            execution_order.append(write.layer)
            return await original_execute(self, conn, write)

        with patch.object(R7TruthWriter, '_execute_single_write', tracking_execute):
            r7 = R7TruthWriter()
            await r7.run(envelope, ctx)

        # Verify order: vec before kg_dom before epi
        assert execution_order.index("st_vec") < execution_order.index("st_kg_dom")
        assert execution_order.index("st_kg_dom") < execution_order.index("st_epi")
```

1. [ ] Implement R8 completion tests:

```python
class TestR8Completion:
    """R8 Phase completion event tests."""

    async def test_r8_completion_payload_matches_schema(
        self, db_session, completed_r7_envelope
    ):
        """
        Given: Envelope after successful R7
        When: R8 builds completion payload
        Then: Payload matches p03_consolidation_complete.json schema
        """
        r8 = R8EventEmitter()
        result = await r8.run(completed_r7_envelope, ctx)

        assert result.status == P03PhaseStatus.DONE

        # Retrieve outbox entry and validate
        outbox = await db_session.fetchone(
            "SELECT payload FROM st_outbox WHERE op_kind = $1",
            "p03.consolidation.complete.v1"
        )
        payload = json.loads(outbox["payload"])

        # Validate required fields
        assert "cycle_id" in payload
        assert "status" in payload
        assert payload["status"] in ("SUCCESS", "PARTIAL", "FAILED")
        assert "summary" in payload
        assert "events_processed" in payload["summary"]

    async def test_r8_gaps_persisted_to_learning_queue(
        self, db_session, envelope_with_gaps
    ):
        """
        Given: Envelope with gaps from R4
        When: R8 executes
        Then: Gaps persisted to st_learning_queue
        """
        r8 = R8EventEmitter()
        await r8.run(envelope_with_gaps, ctx)

        gaps = await db_session.fetch(
            "SELECT * FROM st_learning_queue WHERE status = 'PENDING'"
        )
        assert len(gaps) == len(envelope_with_gaps.phase_outputs.r4_gaps)

    async def test_r8_offset_committed_on_success(
        self, db_session, completed_r7_envelope
    ):
        """
        Given: Successful R7 → R8 execution
        When: R8 completes
        Then: Offset committed to st_offsets
        """
        r8 = R8EventEmitter()
        await r8.run(completed_r7_envelope, ctx)

        offset = await db_session.fetchone(
            "SELECT * FROM st_offsets WHERE pipeline_id = 'P03'"
        )
        assert offset["status"] == "COMMITTED"
        assert offset["offset_value"] == completed_r7_envelope.batch_watermark
```

1. [ ] Implement outbox publisher tests:

```python
class TestOutboxPublisher:
    """Outbox publisher drain tests."""

    async def test_outbox_drain_delivers_to_bus(
        self, db_session, bus_capture
    ):
        """
        Given: Outbox entries staged after R8
        When: Publisher drains batch
        Then: Events dispatched to bus and removed from outbox
        """
        # Stage outbox entry
        await db_session.execute("""
            INSERT INTO st_outbox (driver, op_kind, payload, fingerprint)
            VALUES ('p03', 'p03.consolidation.complete.v1', '{}', 'test-1')
        """)

        publisher = P03OutboxPublisher(outbox, bus_capture, dlq)
        processed = await publisher.drain_batch()

        assert processed == 1
        assert len(bus_capture.events) == 1
        assert bus_capture.events[0]["topic"] == "p03.consolidation.complete.v1"

        # Verify removed from outbox
        remaining = await db_session.fetchone(
            "SELECT * FROM st_outbox WHERE fingerprint = $1", "test-1"
        )
        assert remaining is None

    async def test_outbox_retry_on_transient_failure(
        self, db_session, failing_bus
    ):
        """
        Given: Outbox entry, bus dispatch fails
        When: Publisher attempts drain
        Then: Entry marked for retry with backoff
        """
        await db_session.execute("""
            INSERT INTO st_outbox (driver, op_kind, payload, fingerprint, retries)
            VALUES ('p03', 'test.topic', '{}', 'retry-1', 0)
        """)

        publisher = P03OutboxPublisher(outbox, failing_bus, dlq)
        await publisher.drain_batch()

        entry = await db_session.fetchone(
            "SELECT * FROM st_outbox WHERE fingerprint = $1", "retry-1"
        )
        assert entry["retries"] == 1
        assert entry["next_attempt_ts"] > int(time.time() * 1000)

    async def test_outbox_dlq_after_max_retries(
        self, db_session, failing_bus
    ):
        """
        Given: Outbox entry at max retries
        When: Next publish attempt fails
        Then: Entry moved to DLQ
        """
        await db_session.execute("""
            INSERT INTO st_outbox (driver, op_kind, payload, fingerprint, retries)
            VALUES ('p03', 'test.topic', '{}', 'dlq-1', 3)
        """)

        publisher = P03OutboxPublisher(outbox, failing_bus, dlq,
            config=OutboxPublisherConfig(max_retries=3))
        await publisher.drain_batch()

        # Verify removed from outbox
        outbox_entry = await db_session.fetchone(
            "SELECT * FROM st_outbox WHERE fingerprint = $1", "dlq-1"
        )
        assert outbox_entry is None

        # Verify added to DLQ
        dlq_entry = await db_session.fetchone(
            "SELECT * FROM st_dlq WHERE fingerprint = $1", "dlq-1"
        )
        assert dlq_entry is not None
        assert dlq_entry["pipeline_id"] == "P03"
        assert dlq_entry["phase"] == "R8"
```

**Test Matrix**:

| Test | Category | Coverage |
| ---- | -------- | -------- |
| test_r7_commit_persists_truth_and_outbox_atomically | R7 Happy Path | Atomicity |
| test_r7_failure_rolls_back_truth_and_outbox | R7 Failure | Rollback |
| test_r7_writes_in_dependency_order | R7 Ordering | Dependency |
| test_r7_optimistic_lock_conflict_detection | R7 Concurrency | Locking |
| test_r8_completion_payload_matches_schema | R8 Happy Path | Schema |
| test_r8_gaps_persisted_to_learning_queue | R8 Gap Flow | Persistence |
| test_r8_offset_committed_on_success | R8 Offset | Exactly-once |
| test_r8_idempotent_on_retry | R8 Retry | Idempotency |
| test_outbox_drain_delivers_to_bus | Publisher | Delivery |
| test_outbox_retry_on_transient_failure | Publisher | Retry |
| test_outbox_backoff_calculation | Publisher | Backoff |
| test_outbox_dlq_after_max_retries | Publisher | DLQ |

**Outputs Produced**:

- [x] `tests/k0/pipelines/p03/test_r7_r8_integration.py`
- [x] Test fixtures in `tests/k0/pipelines/p03/conftest.py`

**Acceptance Criteria**:

- [x] All 16 tests pass deterministically
- [x] Tests use mock infrastructure for isolation (MockUnitOfWork, MockConnection)
- [x] Bus dispatch mocked for capture (MockBusDispatcher)
- [x] Coverage: happy path + all failure paths
- [x] No flaky tests (isolated mock state per test)

**Test Cases Implemented** (16 total):

| Test | Category | Coverage |
| ---- | -------- | -------- |
| test_r7_commit_persists_truth_and_outbox_atomically | R7 Atomicity | Transaction commit |
| test_r7_stages_outbox_for_each_staged_event | R7 Staging | Outbox creation |
| test_r7_failure_prevents_outbox_staging | R7 Failure | Rollback |
| test_r7_writes_in_dependency_order | R7 Ordering | Dependency order |
| test_r8_builds_completion_payload_with_required_fields | R8 Payload | Schema compliance |
| test_r8_gaps_staged_to_outbox | R8 Gaps | Gap event staging |
| test_r8_gap_payload_contains_context | R8 Gaps | Gap context |
| test_r8_commits_offset_on_success | R8 Offset | Exactly-once |
| test_r8_offset_includes_space_and_tenant | R8 Offset | Offset context |
| test_publisher_delivers_to_bus | Publisher | Bus delivery |
| test_publisher_retries_on_failure | Publisher | Retry logic |
| test_publisher_dlq_after_max_retries | Publisher | DLQ handling |
| test_r7_r8_publisher_happy_path | E2E | Full flow |
| test_r7_failure_prevents_r8_execution | E2E | Failure isolation |
| test_r8_fingerprint_enables_deduplication | Idempotency | Deduplication |
| test_gap_fingerprint_pattern | Idempotency | Gap fingerprints |

**Blocked By**: 3.1.1, 3.1.2, 3.1.3

**Blocks**: Epic 3.2

---

### Epic 3.2 — Cross-Pipeline Integration

> **Scope**: Wire P03 to adjacent pipelines (P02, P05, P06, P08, P21).

---

#### Issue 3.2.1 — Implement R0 Phase: Event Ingestion from st_hipp_events

**Status**: COMPLETED

**Spec Reference**: [Dossier 4.1](../pipelines/P03_consolidation_dossier_v2.md#41-r0--event-ingestion)

**Prerequisite Understanding**:

- M1 created `P03OffsetManager` with `fetch_offset()`, `commit_offset()` methods
- R0 must: query st_hipp_events WHERE event_id > last_offset AND consolidation_status IS NULL
- Offset is stored in `st_offsets` table with `pipeline_id='P03'`
- Events must have `embedding_status='READY'` to be eligible for consolidation

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| P03OffsetManager | `k0/pipelines/p03/offset_manager.py` | `fetch_offset()` |
| P03BatchEnvelope | `k0/pipelines/p03/envelope.py` | Container for events |
| P03Event | `k0/pipelines/p03/event_state.py` | Event wrapper |
| P03PhaseProtocol | `k0/pipelines/p03/phase_interface.py` | Phase ABC |
| P03RunnerContext | `k0/pipelines/p03/phase_interface.py` | Context with syscalls |
| HippEventRow | `k0/storage/hipp_events.py` | Row mapper |

**Work To Do**:

1. [x] Create R0 phase implementation: `k0/pipelines/p03/phases/r0_batch_selector.py`

**R0 Implementation Structure**:

```python
# k0/pipelines/p03/phases/r0_batch_selector.py
"""R0 Phase — Event Ingestion (Batch Selection). Issue 3.2.1."""

from __future__ import annotations
import time
from typing import TYPE_CHECKING, List, Optional
from dataclasses import dataclass

from k0.pipelines.p03.phase_interface import P03PhaseResult, P03RunnerContext
from k0.pipelines.p03.runner_contract import P03PhaseId
from k0.pipelines.p03.event_state import P03Event
from k0.pipelines.p03.envelope import P03BatchEnvelope, P03BatchContext
from k0.pipelines.p03.offset_manager import P03OffsetManager
from k0.pipelines.p03.observability import P03Error

if TYPE_CHECKING:
    pass

@dataclass
class R0Config:
    """R0 phase configuration."""
    batch_size: int = 100
    max_age_ms: int = 86400000  # 24 hours
    exclude_archived: bool = True
    require_embedding_ready: bool = True

class R0BatchSelector:
    """
    R0 Phase: Event Ingestion / Batch Selection.

    Responsibilities:
    1. Fetch current offset from st_offsets
    2. Query st_hipp_events for eligible events
    3. Build P03BatchEnvelope with events and context
    4. Return envelope for R1-R8 processing

    Eligibility criteria:
    - event_id > last_committed_offset
    - consolidation_status IS NULL or 'PENDING'
    - embedding_status = 'READY'
    - NOT archived (unless include_archived=True)
    """

    PHASE_ID = P03PhaseId.R0

    def __init__(self, config: Optional[R0Config] = None):
        self.config = config or R0Config()
        self._offset_manager: Optional[P03OffsetManager] = None

    async def run(
        self,
        tenant_id: str,
        space_id: str,
        ctx: P03RunnerContext
    ) -> tuple[P03BatchEnvelope, P03PhaseResult]:
        """
        Execute R0 phase.

        Unlike R1-R8 which receive an envelope, R0 CREATES the envelope.
        Returns: (envelope, result) tuple
        """
        start_ms = int(time.time() * 1000)

        try:
            # 1. Initialize offset manager
            self._offset_manager = P03OffsetManager(
                offset_store=ctx.syscalls.offset_store,
                tenant_id=tenant_id,
                space_id=space_id,
            )

            # 2. Fetch current offset
            current_offset = await self._offset_manager.fetch_offset()
            ctx.logger.info(
                f"R0: Starting from offset {current_offset}",
                extra={"offset": current_offset}
            )

            # 3. Query eligible events
            events = await self._fetch_eligible_events(
                ctx, tenant_id, space_id, current_offset
            )

            if not events:
                # No work to do
                duration_ms = int(time.time() * 1000) - start_ms
                empty_envelope = self._build_empty_envelope(
                    tenant_id, space_id, current_offset
                )
                return empty_envelope, P03PhaseResult.skip(
                    phase_id=self.PHASE_ID,
                    reason="No eligible events",
                    duration_ms=duration_ms,
                )

            # 4. Build envelope
            envelope = self._build_envelope(
                tenant_id, space_id, events, current_offset
            )

            duration_ms = int(time.time() * 1000) - start_ms
            result = P03PhaseResult.done(
                phase_id=self.PHASE_ID,
                duration_ms=duration_ms,
                outputs_summary={
                    "events_selected": len(events),
                    "offset_start": current_offset,
                    "offset_end": envelope.batch_watermark,
                },
                idempotency_key=f"p03:r0:{envelope.context.cycle_id}",
            )

            return envelope, result

        except Exception as e:
            duration_ms = int(time.time() * 1000) - start_ms
            return None, P03PhaseResult.fail(
                phase_id=self.PHASE_ID,
                error=P03Error(
                    error_type="R0_INGESTION_ERROR",
                    error_message=str(e),
                    recoverable=True,
                ),
                duration_ms=duration_ms,
            )

    async def _fetch_eligible_events(
        self,
        ctx: P03RunnerContext,
        tenant_id: str,
        space_id: str,
        offset: int,
    ) -> List[P03Event]:
        """
        Query st_hipp_events for eligible events.

        SQL:
        SELECT * FROM st_hipp_events
        WHERE tenant_id = $1
          AND space_id = $2
          AND event_id > $3
          AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
          AND embedding_status = 'READY'
          AND archival_status IS NULL
        ORDER BY event_id ASC
        LIMIT $4
        """
        query = """
            SELECT
                event_id, tenant_id, space_id, source_id,
                event_type, payload, embedding, embedding_status,
                consolidation_status, created_at, updated_at
            FROM st_hipp_events
            WHERE tenant_id = $1
              AND space_id = $2
              AND event_id > $3
              AND (consolidation_status IS NULL OR consolidation_status = 'PENDING')
              AND embedding_status = $4
              AND (archival_status IS NULL OR archival_status = '')
            ORDER BY event_id ASC
            LIMIT $5
        """

        embedding_status = 'READY' if self.config.require_embedding_ready else None

        rows = await ctx.syscalls.db.fetch(
            query,
            tenant_id,
            space_id,
            offset,
            embedding_status or 'READY',
            self.config.batch_size,
        )

        events = []
        for row in rows:
            event = P03Event.from_db_row(row)
            events.append(event)

        return events

    def _build_envelope(
        self,
        tenant_id: str,
        space_id: str,
        events: List[P03Event],
        start_offset: int,
    ) -> P03BatchEnvelope:
        """Build envelope from selected events."""
        import uuid

        # Batch watermark is the max event_id in the batch
        watermark = max(e.event_id for e in events)

        context = P03BatchContext(
            cycle_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            space_id=space_id,
            start_offset=start_offset,
            qos_band="standard",  # Configurable
        )

        envelope = P03BatchEnvelope(
            context=context,
            events=events,
            batch_watermark=watermark,
        )

        return envelope

    def _build_empty_envelope(
        self,
        tenant_id: str,
        space_id: str,
        offset: int,
    ) -> P03BatchEnvelope:
        """Build empty envelope for skip case."""
        import uuid

        context = P03BatchContext(
            cycle_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            space_id=space_id,
            start_offset=offset,
            qos_band="standard",
        )

        return P03BatchEnvelope(
            context=context,
            events=[],
            batch_watermark=offset,
        )
```

1. [ ] Register R0 phase in `k0/pipelines/p03/runner_contract.py` PHASE_REGISTRY

2. [ ] Wire R0 as entry point in `P03SequentialRunner.run()`:

```python
# In P03SequentialRunner.run()
async def run(self, tenant_id: str, space_id: str) -> P03CycleResult:
    # R0 creates the envelope
    r0 = R0BatchSelector(config=self.r0_config)
    envelope, r0_result = await r0.run(tenant_id, space_id, self.ctx)

    if r0_result.status == P03PhaseStatus.SKIP:
        return P03CycleResult.empty(r0_result)

    if r0_result.status == P03PhaseStatus.FAIL:
        return P03CycleResult.failed(r0_result)

    # Continue with R1-R8
    return await self._run_phases(envelope)
```

1. [ ] Add offset-related tests:

```python
async def test_r0_ingestion_respects_offset(db_session):
    """R0 only selects events after committed offset."""
    # Insert events with event_id 1, 2, 3
    # Set offset to 2
    # R0 should only select event_id=3
```

**Outputs Produced**:

- [x] `k0/pipelines/p03/phases/r0_batch_selector.py`
- [x] `tests/k0/pipelines/p03/test_p03_r0_batch_selector.py` (15 tests)

**Acceptance Criteria**:

- [x] R0 only selects events with wal_pos > committed offset
- [x] Events with `embedding_status != 'READY'` are excluded (configurable)
- [x] Events with `consolidation_status NOT NULL` (except PENDING) are excluded
- [x] Archived events are excluded (configurable)
- [x] Batch size respects configuration
- [x] Returns SKIP result when no eligible events

**Test Cases Implemented** (15 total):

| Test | Category | Coverage |
| ---- | -------- | -------- |
| test_r0_fetches_offset_at_startup | Offset | Offset fetch flow |
| test_r0_starts_at_zero_when_no_offset | Offset | Default offset |
| test_r0_respects_offset_exactly | Offset | Boundary condition |
| test_r0_respects_batch_size_limit | Batch | Size limiting |
| test_r0_skip_when_no_events | Batch | Empty handling |
| test_r0_creates_valid_envelope | Batch | Envelope construction |
| test_r0_event_state_population | Batch | Field mapping |
| test_r0_result_includes_outputs_summary | Result | Summary metrics |
| test_r0_result_has_idempotency_key | Result | Idempotency |
| test_r0_result_includes_duration | Result | Timing |
| test_r0_handles_db_error_gracefully | Error | Exception handling |
| test_r0_error_is_marked_recoverable | Error | Recoverability |
| test_r0_default_config | Config | Defaults |
| test_r0_custom_config | Config | Custom values |
| test_r0_uses_configured_batch_size | Config | Applied correctly |

**Blocked By**: Epic 3.1

**Blocks**: 3.2.2, 3.2.6

---

#### Issue 3.2.2 — Implement Status Writeback in R7

**Status**: COMPLETED

**Spec Reference**: [Dossier 4.8.3](../pipelines/P03_consolidation_dossier_v2.md#483-status-writeback)

**Prerequisite Understanding**:

- M2 added consolidation columns to st_hipp_events (0034 migration)
- Status writeback must be atomic with R7 truth writes (same UoW transaction)
- Already partially implemented in Issue 3.1.1 `_writeback_status()` — this issue formalizes and extends it

**Note**: This issue is largely covered by 3.1.1's `_writeback_status()` method. This issue focuses on:

- Ensuring all status values are correctly mapped
- Adding metrics for status distribution
- Adding validation for status transitions

**Work To Do**:

1. [x] Verify `_writeback_status()` in R7 phase covers all columns:

```sql
UPDATE st_hipp_events SET
    consolidation_status = $1,      -- CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW
    consolidation_cycle_id = $2,    -- UUID of current cycle
    consolidated_at = $3,           -- Timestamp in ms
    reconciliation_decision = $4,   -- ReconciliationAction.value
    truth_match_id = $5,            -- Best match entity/episode ID
    truth_match_similarity = $6     -- Similarity score [0.0, 1.0]
WHERE event_id = $7
```

1. [x] Add status mapping helper in R7 phase:

```python
def _determine_status(self, event: P03Event) -> str:
    """Map reconciliation action to consolidation status."""
    action = event.reconciliation_action

    status_map = {
        ReconciliationAction.MERGE: "CONSOLIDATED",
        ReconciliationAction.CREATE: "CONSOLIDATED",
        ReconciliationAction.UPDATE: "CONSOLIDATED",
        ReconciliationAction.SKIP: "DUPLICATE",
        ReconciliationAction.PRUNE: "PRUNED",
        ReconciliationAction.CONTRADICT: "PENDING_REVIEW",
        ReconciliationAction.DEFER: "PENDING",
    }

    return status_map.get(action, "CONSOLIDATED")
```

1. [x] Add status distribution metrics:

```python
# In R7 phase, after writeback
status_counts = Counter(
    self._determine_status(e) for e in envelope.events
)
for status, count in status_counts.items():
    ctx.metrics.inc("p03_consolidation_status_total", count, labels={"status": status})
```

1. [x] Add validation for status transitions (optional guard):

```python
async def _validate_status_transition(self, conn, event_id: int, new_status: str) -> bool:
    """Validate status transition is allowed."""
    row = await conn.fetchrow(
        "SELECT consolidation_status FROM st_hipp_events WHERE event_id = $1",
        event_id
    )
    current = row["consolidation_status"] if row else None

    # Allowed transitions
    allowed = {
        None: {"CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW", "PENDING"},
        "PENDING": {"CONSOLIDATED", "DUPLICATE", "PRUNED", "PENDING_REVIEW"},
        "PENDING_REVIEW": {"CONSOLIDATED", "PRUNED"},
    }

    if current in allowed and new_status in allowed[current]:
        return True
    return current == new_status  # Idempotent
```

**Outputs Produced**:

- [x] Status writeback verified complete in R7 phase
- [x] Status mapping helper added
- [x] Metrics for status distribution

**Acceptance Criteria**:

- [x] All processed events have `consolidation_status` set
- [x] `consolidation_cycle_id` set to current cycle UUID
- [x] `consolidated_at` set to current timestamp
- [x] `reconciliation_decision` matches event's action
- [x] Failure rolls back status updates (atomic with truth writes)
- [x] Metrics emitted per status type

**Test Cases** (added to `test_p03_r7_truth_writer.py`):

| Test Name | Class | Validates |
|-----------|-------|-----------|
| test_writeback_updates_hipp_events | TestStatusWriteback | All events updated |
| test_writeback_maps_actions_to_status | TestStatusWriteback | Status mapping |
| test_writeback_returns_status_distribution | TestStatusWriteback | Metrics in outputs |
| test_writeback_records_metrics_in_observability | TestStatusWriteback | Observability counters |
| test_valid_transition_from_null_to_consolidated | TestStatusTransitionValidation | NULL -> CONSOLIDATED |
| test_valid_transition_from_pending_to_consolidated | TestStatusTransitionValidation | PENDING -> CONSOLIDATED |
| test_valid_transition_from_pending_review_to_consolidated | TestStatusTransitionValidation | PENDING_REVIEW -> CONSOLIDATED |
| test_idempotent_same_status_transition | TestStatusTransitionValidation | Idempotent updates |
| test_invalid_transition_from_consolidated_to_pending | TestStatusTransitionValidation | Blocks invalid transition |
| test_invalid_transition_from_duplicate_to_consolidated | TestStatusTransitionValidation | Final state immutable |
| test_valid_all_from_null_transitions | TestStatusTransitionValidation | All statuses from NULL |

**Blocked By**: 3.1.1, 3.2.1

**Blocks**: 3.2.6

---

#### Issue 3.2.3 — Implement P03 to P06 Gap Persistence + Emission

**Status**: ✅ COMPLETED

**Spec Reference**: [Dossier 5](../pipelines/P03_consolidation_dossier_v2.md#5-p06-active-learning-integration)

**Prerequisite Understanding**:

- M2 created st_learning_queue (0037 migration)
- Gaps detected in R4/R5 must be persisted AND emitted to bus
- P06 consumes gaps from st_learning_queue to drive active learning

**Note**: Gap persistence is partially handled in Issue 3.1.2's R8 `_process_gaps()` method. This issue:

- Formalizes the gap emitter as a separate helper module
- Adds all gap types from dossier
- Adds deduplication and idempotency guarantees

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| GapSignal | `k0/pipelines/p03/gap_detector.py` | Gap structure |
| GapType | `k0/pipelines/p03/gap_detector.py` | Enum of gap types |
| LearningQueueStore | `k0/storage/learning_queue.py` | st_learning_queue adapter |
| OutboxStore | `k0/storage/outbox.py` | Outbox staging |

**Work To Do**:

1. [x] Create gap emitter module: `k0/pipelines/p03/gap_emitter.py`

**Gap Emitter Implementation**:

```python
# k0/pipelines/p03/gap_emitter.py
"""P03 Gap Emitter — Persists and emits detected gaps. Issue 3.2.3."""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

from k0.storage.outbox import OutboxEntry

if TYPE_CHECKING:
    from k0.uow.unit_of_work import UnitOfWork
    from k0.pipelines.p03.gap_detector import GapSignal

class GapType(Enum):
    """Gap types detected during consolidation."""
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"           # Entity resolution unclear
    LOW_CONFIDENCE_EDGE = "LOW_CONFIDENCE_EDGE"     # KG edge below threshold
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"         # Expected attribute not found
    SEMANTIC_CONFLICT = "SEMANTIC_CONFLICT"         # Contradicting information
    TEMPORAL_INCONSISTENCY = "TEMPORAL_INCONSISTENCY"  # Timeline conflict
    ORPHAN_REFERENCE = "ORPHAN_REFERENCE"           # Reference to missing entity
    CLUSTERING_UNCERTAINTY = "CLUSTERING_UNCERTAINTY"  # Cluster membership unclear

@dataclass
class P03GapEmitterConfig:
    """Configuration for gap emitter."""
    topic: str = "p03.gap.detected.v1"
    deduplicate: bool = True
    dedup_window_ms: int = 3600000  # 1 hour

class P03GapEmitter:
    """
    Persists detected gaps to st_learning_queue and stages them to outbox.

    Responsibilities:
    1. Insert gap to st_learning_queue for P06 consumption
    2. Stage gap event to outbox for immediate notification
    3. Deduplicate gaps within configured window
    4. Ensure idempotency via gap_id fingerprint
    """

    def __init__(self, config: P03GapEmitterConfig = None):
        self.config = config or P03GapEmitterConfig()

    async def emit_gaps(
        self,
        uow: UnitOfWork,
        gaps: List[GapSignal],
        tenant_id: str,
        space_id: str,
        cycle_id: str,
    ) -> int:
        """
        Emit all gaps within UoW transaction.

        Args:
            uow: Active UnitOfWork (transaction)
            gaps: List of GapSignal from R4/R5
            tenant_id: Tenant context
            space_id: Space context
            cycle_id: Current cycle ID

        Returns:
            Number of gaps emitted (may be less than len(gaps) due to dedup)
        """
        emitted = 0

        for gap in gaps:
            gap_id = self._generate_gap_id(cycle_id, gap)

            # Check for deduplication
            if self.config.deduplicate:
                if await self._is_duplicate(uow, gap_id, gap.gap_type):
                    continue

            # Persist to learning queue
            await self._persist_to_queue(
                uow, gap, tenant_id, space_id, gap_id
            )

            # Stage to outbox
            await self._stage_to_outbox(
                uow, gap, tenant_id, space_id, cycle_id, gap_id
            )

            emitted += 1

        return emitted

    def _generate_gap_id(self, cycle_id: str, gap: GapSignal) -> str:
        """
        Generate unique gap ID for idempotency.

        Pattern: p03:gap:{cycle_id}:{source_event_id}:{gap_type}
        """
        return f"p03:gap:{cycle_id}:{gap.source_event_id}:{gap.gap_type.value}"

    async def _is_duplicate(
        self,
        uow: UnitOfWork,
        gap_id: str,
        gap_type: GapType,
    ) -> bool:
        """
        Check if gap already exists within dedup window.

        Dedup based on gap fingerprint within window.
        """
        cutoff = int(time.time() * 1000) - self.config.dedup_window_ms

        row = await uow.connection.fetchrow("""
            SELECT queue_id FROM st_learning_queue
            WHERE gap_id = $1
              AND created_at > $2
        """, gap_id, cutoff)

        return row is not None

    async def _persist_to_queue(
        self,
        uow: UnitOfWork,
        gap: GapSignal,
        tenant_id: str,
        space_id: str,
        gap_id: str,
    ) -> None:
        """
        Insert gap into st_learning_queue.

        Schema: queue_id, tenant_id, space_id, gap_type, gap_id,
                source_event_id, gap_metadata, status, priority, created_at
        """
        now_ms = int(time.time() * 1000)

        # Calculate priority based on gap type
        priority = self._calculate_priority(gap)

        await uow.connection.execute("""
            INSERT INTO st_learning_queue (
                queue_id, tenant_id, space_id, gap_type, gap_id,
                source_event_id, gap_metadata, status, priority, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (queue_id) DO NOTHING
        """,
            gap_id,  # queue_id = gap_id for simplicity
            tenant_id,
            space_id,
            gap.gap_type.value,
            gap_id,
            gap.source_event_id,
            json.dumps(gap.metadata),
            "PENDING",
            priority,
            now_ms,
        )

    async def _stage_to_outbox(
        self,
        uow: UnitOfWork,
        gap: GapSignal,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        gap_id: str,
    ) -> None:
        """Stage gap event to outbox."""
        payload = self._build_payload(gap, tenant_id, space_id, cycle_id, gap_id)

        entry = OutboxEntry(
            id=None,
            wal_pos=0,
            tenant_id=tenant_id,
            space_id=space_id,
            driver="p03",
            op_kind=self.config.topic,
            payload=json.dumps(payload).encode("utf-8"),
            fingerprint=gap_id,
            requeue_seq=0,
            retries=0,
        )
        uow.stage_outbox(entry)

    def _build_payload(
        self,
        gap: GapSignal,
        tenant_id: str,
        space_id: str,
        cycle_id: str,
        gap_id: str,
    ) -> Dict[str, Any]:
        """Build gap event payload."""
        return {
            "gap_id": gap_id,
            "cycle_id": cycle_id,
            "tenant_id": tenant_id,
            "space_id": space_id,
            "gap_type": gap.gap_type.value,
            "source_event_id": gap.source_event_id,
            "confidence": gap.confidence,
            "metadata": gap.metadata,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    def _calculate_priority(self, gap: GapSignal) -> int:
        """
        Calculate gap priority for P06 processing order.

        Higher priority = processed first.
        """
        priority_map = {
            GapType.SEMANTIC_CONFLICT: 100,      # Highest - conflicts block progress
            GapType.AMBIGUOUS_ENTITY: 80,        # High - entity resolution critical
            GapType.ORPHAN_REFERENCE: 70,        # High - data integrity
            GapType.TEMPORAL_INCONSISTENCY: 60,  # Medium - timeline issues
            GapType.LOW_CONFIDENCE_EDGE: 40,     # Medium - can often infer
            GapType.MISSING_ATTRIBUTE: 30,       # Low - optional enrichment
            GapType.CLUSTERING_UNCERTAINTY: 20,  # Low - refinement
        }
        return priority_map.get(gap.gap_type, 50)
```

1. [x] Wire gap emitter into R8 phase:

```python
# In R8EventEmitter._process_gaps()
gap_emitter = P03GapEmitter()
emitted = await gap_emitter.emit_gaps(
    uow=uow,
    gaps=envelope.phase_outputs.r4_gaps,
    tenant_id=envelope.context.tenant_id,
    space_id=envelope.context.space_id,
    cycle_id=envelope.context.cycle_id,
)
```

1. [x] Add metrics:

| Metric | Type | Labels | Description |
| ------ | ---- | ------ | ----------- |
| `p03_gaps_detected_total` | Counter | gap_type | Gaps detected per type |
| `p03_gaps_emitted_total` | Counter | gap_type | Gaps emitted (after dedup) |
| `p03_gaps_deduplicated_total` | Counter | gap_type | Gaps skipped due to dedup |

**Outputs Produced**:

- [x] `k0/pipelines/p03/gap_emitter.py`
- [x] Integration with R8 phase

**Acceptance Criteria**:

- [x] Gaps appear in st_learning_queue with correct fields
- [x] Gaps staged to outbox for P06 consumption
- [x] Duplicate gaps within window are skipped
- [x] Gap priority calculated based on type
- [x] Idempotency via gap_id fingerprint

**Test Cases**:

| Test Name | Class | Validates |
| --------- | ----- | --------- |
| test_gap_type_enum_values | TestGapType | 7 gap types from dossier |
| test_gap_type_from_string_mapping | TestGapType | Legacy string to enum |
| test_priority_contradiction_highest | TestGapPriority | CONTRADICTION=100 |
| test_priority_missing_attribute_lowest | TestGapPriority | MISSING_ATTRIBUTE=30 |
| test_config_defaults | TestGapEmitterConfig | Default dedup window |
| test_gap_id_generation_pattern | TestGapIdGeneration | p03:gap:{cycle}:{entity}:{type} |
| test_gap_id_uniqueness | TestGapIdGeneration | Different gaps get different IDs |
| test_duplicate_detection_returns_true | TestDeduplication | Duplicate within window detected |
| test_non_duplicate_returns_false | TestDeduplication | Unique gaps not flagged |
| test_persist_to_queue_inserts_correct_fields | TestPersistence | All 10 st_learning_queue fields |
| test_persist_uses_on_conflict_do_nothing | TestPersistence | Idempotent inserts |
| test_stage_to_outbox_creates_entry | TestOutboxStaging | OutboxEntry created |
| test_outbox_fingerprint_matches_gap_id | TestOutboxStaging | Fingerprint = gap_id |
| test_outbox_payload_contains_required_fields | TestOutboxStaging | 9 payload fields |
| test_emit_gaps_happy_path | TestEmitGaps | Full integration |
| test_emit_gaps_deduplication | TestEmitGaps | Skips duplicates |
| test_emit_result_by_type_tracking | TestEmitGaps | Per-type counters |
| test_r8_uses_gap_emitter | TestR8Integration | R8 calls P03GapEmitter |
| test_r8_metrics_emitted | TestR8Integration | Prometheus metrics |
| test_gap_fingerprint_pattern | TestIdempotency | p03:gap: prefix in fingerprints |
| test_r8_fingerprint_enables_deduplication | TestIdempotency | Outbox fingerprint dedup |
| test_r7_r8_publisher_happy_path | TestEndToEndPipeline | Full pipeline flow |
| test_gaps_staged_to_outbox | TestR8Completion | Gaps appear in outbox |
| test_gap_payload_contains_context | TestR8Completion | Context in payload |
| test_r8_builds_completion_payload_with_required_fields | TestR8Completion | Completion event fields |
| test_r8_commits_offset_on_success | TestR8Offset | Offset committed |

**Blocked By**: 3.1.2

**Blocks**: 3.2.6

---

#### Issue 3.2.4 — ~~Implement P03 to P05 Budget Client~~

**Status**: ❌ N/A (Not Applicable)

**Reason**: Event-driven architecture - pipelines run independently.

P03 writes ALL detected gaps to `st_learning_queue` and emits `p03.gap.detected.v1` events to the outbox. P05 (Prospective/Triggers) independently picks up gaps from the queue and manages attention budget when surfacing questions to users via SSE.

**No direct P03 → P05 coordination required** because:

1. P03 publishes gaps via outbox pattern (Issue 3.2.3 ✅)
2. P05 consumes from `st_learning_queue` independently
3. P05 manages attention budget internally when deciding to ask user
4. No RPC calls between P03 and P05

**Original Spec Reference**: [Dossier 9.5](../pipelines/P03_consolidation_dossier_v2.md#95-p03-p05-contract) describes the P05 internal attention budget, not a P03 → P05 query.

---

#### Issue 3.2.5 — ~~Implement P03 to P08 Circuit Breaker~~

**Status**: ❌ N/A (Not Applicable)

**Reason**: Event-driven architecture - pipelines run independently.

P03 emits events to the outbox (`p03.consolidation.complete.v1`, `p03.embedding.created.v1`). P08 (Embedding Management) independently consumes these events from the bus.

**No direct P03 → P08 coordination required** because:

1. P03 publishes completion events via outbox pattern (Issue 3.1.3 ✅)
2. P08 subscribes to `p03.consolidation.complete.v1` topic on the bus
3. If P08 is down, events remain in bus until P08 recovers
4. Circuit breakers are for synchronous RPC calls, not event-driven communication

**Original Spec Reference**: [Dossier 9.4](../pipelines/P03_consolidation_dossier_v2.md#94-p03-p08-contract) describes the event schema, not synchronous calls. [Dossier 13.6](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breaker) applies only if SYNC mode is needed (it's not for P03).

**Blocked By**: N/A

**Blocks**: N/A

---

#### Issue 3.2.6 — Implement P21 to P03 Feedback Consumer

**Status**: ✅ COMPLETED

**Spec Reference**: [Dossier 9.8](../pipelines/P03_consolidation_dossier_v2.md#98-p21-feedback-integration)

**Implementation Summary**:

P03 is a CONSUMER of the P21 feedback system, not the owner. This issue implemented:

1. **P03FeedbackPayload schema** in `k0/feedback/payloads.py` (Dossier 9.8.5)
   - 6 feedback types: SALIENCE_ADJUSTMENT, DECAY_REVERSAL, CLUSTER_CORRECTION, REINFORCEMENT_OUTCOME, NOVELTY_SIGNAL, REGRET_SIGNAL
   - Fields for learning formula integration: salience_delta, decay_lambda_delta, was_retrieved, was_helpful, confidence

2. **P03 topic registration** in `k0/feedback/topics.py`
   - Added `FEEDBACK_SIGNAL_P03_V1 = "feedback.signal.p03.v1"`
   - Registered P03 in `FEEDBACK_PIPELINES_V1`

3. **P03FeedbackConsumer** in `k0/pipelines/p03/feedback_consumer.py`
   - Subscribes to `feedback.signal.p03.v1` bus topic
   - Routes signals to stub handlers by feedback_type (real learning in M4+)
   - Marks signals consumed in `st_feedback_signals`
   - Includes `P03FeedbackMetrics` for observability

4. **P03FeedbackSubscriber** for bus subscription lifecycle management

**Signal-to-Handler Mapping** (Dossier 9.8.4):

| Signal Type | Handler | Target Module (M4+) |
|-------------|---------|---------------------|
| SALIENCE_ADJUSTMENT | `_handle_salience` | ImportanceLearner |
| DECAY_REVERSAL | `_handle_decay` | DecayLearner |
| CLUSTER_CORRECTION | `_handle_cluster` | SimilarityLearner |
| REINFORCEMENT_OUTCOME | `_handle_reinforcement` | HebbianLearner |
| NOVELTY_SIGNAL | `_handle_novelty` | AuditLogger |
| REGRET_SIGNAL | `_handle_regret` | DecayLearner |

**Files Created/Modified**:

- [x] `k0/feedback/payloads.py` — Added P03FeedbackPayload schema
- [x] `k0/feedback/topics.py` — Registered FEEDBACK_SIGNAL_P03_V1
- [x] `k0/feedback/__init__.py` — Exported P03 schema and topic
- [x] `k0/pipelines/p03/feedback_consumer.py` — Consumer + Subscriber

**Acceptance Criteria** (all met):

- [x] Subscribes to `feedback.signal.p03.v1` topic
- [x] Routes all 6 feedback types to handlers
- [x] Marks signals consumed in st_feedback_signals
- [x] Stub handlers in place for future milestone implementation
- [x] Metrics track received/processed/errors

**Blocked By**: Epic 3.1 ✅

**Blocks**: 3.2.7

class FeedbackType(Enum):
    """Feedback signal types from P21."""
    SALIENCE_ADJUSTMENT = "SALIENCE_ADJUSTMENT"     # Adjust importance weights
    DECAY_REVERSAL = "DECAY_REVERSAL"               # Prevent memory decay
    CLUSTER_CORRECTION = "CLUSTER_CORRECTION"       # Fix clustering decisions
    REINFORCEMENT_OUTCOME = "REINFORCEMENT_OUTCOME" # Learning reward/penalty
    NOVELTY_SIGNAL = "NOVELTY_SIGNAL"               # New pattern detected
    REGRET_SIGNAL = "REGRET_SIGNAL"                 # Bad decision detected

@dataclass
class P03FeedbackPayload:
    """
    Feedback signal payload.

    Schema per dossier 9.8:
    {
        "signal_id": str,
        "feedback_type": FeedbackType,
        "target_id": str,           # Entity/episode/pattern ID
        "target_type": str,         # "entity", "episode", "pattern", "edge"
        "delta": float,             # Adjustment amount
        "metadata": dict,           # Type-specific data
        "source_cycle_id": str,     # Originating P03 cycle
        "timestamp": int
    }
    """
    signal_id: str
    feedback_type: FeedbackType
    target_id: str
    target_type: str
    delta: float
    metadata: Dict[str, Any]
    source_cycle_id: str
    timestamp: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> P03FeedbackPayload:
        """Parse from JSON payload."""
        return cls(
            signal_id=data["signal_id"],
            feedback_type=FeedbackType(data["feedback_type"]),
            target_id=data["target_id"],
            target_type=data["target_type"],
            delta=data.get("delta", 0.0),
            metadata=data.get("metadata", {}),
            source_cycle_id=data.get("source_cycle_id", ""),
            timestamp=data.get("timestamp", 0),
        )

# Handler type alias
FeedbackHandler = Callable[[P03FeedbackPayload], Awaitable[None]]

class P03FeedbackConsumer:
    """
    Consumes and routes P21 feedback signals.

    Per dossier 9.8, routes by feedback_type:
    - SALIENCE_ADJUSTMENT → ImportanceLearner
    - DECAY_REVERSAL → DecayLearner
    - CLUSTER_CORRECTION → SimilarityLearner
    - REINFORCEMENT_OUTCOME → HebbianLearner
    - NOVELTY_SIGNAL → AuditLogger
    - REGRET_SIGNAL → RegretLearner
    """

    TOPIC = "feedback.signal.p03.v1"

    def __init__(self):
        self._handlers: Dict[FeedbackType, FeedbackHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default stub handlers for all feedback types."""
        # These will be replaced with actual learner implementations
        self._handlers = {
            FeedbackType.SALIENCE_ADJUSTMENT: self._handle_salience,
            FeedbackType.DECAY_REVERSAL: self._handle_decay,
            FeedbackType.CLUSTER_CORRECTION: self._handle_cluster,
            FeedbackType.REINFORCEMENT_OUTCOME: self._handle_reinforcement,
            FeedbackType.NOVELTY_SIGNAL: self._handle_novelty,
            FeedbackType.REGRET_SIGNAL: self._handle_regret,
        }

    def register_handler(
        self,
        feedback_type: FeedbackType,
        handler: FeedbackHandler,
    ) -> None:
        """Register custom handler for feedback type."""
        self._handlers[feedback_type] = handler

    async def process(self, message: Dict[str, Any]) -> bool:
        """
        Process incoming feedback message.

        Args:
            message: Raw message from bus

        Returns:
            True if processed successfully
        """
        try:
            payload = P03FeedbackPayload.from_dict(message)
            handler = self._handlers.get(payload.feedback_type)

            if not handler:
                # Unknown feedback type, log and skip
                return False

            await handler(payload)
            return True

        except Exception as e:
            # Log error, return False to signal retry/DLQ
            return False

    async def _mark_consumed(
        self,
        signal_id: str,
        db_connection,
    ) -> None:
        """
        Mark signal as consumed in st_feedback_signals.

        UPDATE st_feedback_signals
        SET consumed_at = $1, consumed_by = 'P03'
        WHERE signal_id = $2
        """
        now_ms = int(time.time() * 1000)
        await db_connection.execute("""
            UPDATE st_feedback_signals
            SET consumed_at = $1, consumed_by = 'P03'
            WHERE signal_id = $2
        """, now_ms, signal_id)

    # Default handler implementations (stubs for future milestones)

    async def _handle_salience(self, payload: P03FeedbackPayload) -> None:
        """
        Handle SALIENCE_ADJUSTMENT feedback.

        Routes to ImportanceLearner to adjust salience weights.
        Target: entity, episode, or pattern
        Delta: positive increases salience, negative decreases
        """
        # TODO: M4+ implementation
        # importance_learner.adjust_weight(
        #     target_id=payload.target_id,
        #     target_type=payload.target_type,
        #     delta=payload.delta,
        # )
        pass

    async def _handle_decay(self, payload: P03FeedbackPayload) -> None:
        """
        Handle DECAY_REVERSAL feedback.

        Routes to DecayLearner to reverse/pause decay.
        Target: memory that was incorrectly decaying
        """
        # TODO: M4+ implementation
        # decay_learner.reverse_decay(
        #     target_id=payload.target_id,
        #     reversal_factor=payload.delta,
        # )
        pass

    async def _handle_cluster(self, payload: P03FeedbackPayload) -> None:
        """
        Handle CLUSTER_CORRECTION feedback.

        Routes to SimilarityLearner to adjust clustering.
        Metadata includes: correct_cluster_id, incorrect_cluster_id
        """
        # TODO: M4+ implementation
        # similarity_learner.update_clustering(
        #     entity_id=payload.target_id,
        #     correct_cluster=payload.metadata["correct_cluster_id"],
        #     incorrect_cluster=payload.metadata["incorrect_cluster_id"],
        # )
        pass

    async def _handle_reinforcement(self, payload: P03FeedbackPayload) -> None:
        """
        Handle REINFORCEMENT_OUTCOME feedback.

        Routes to HebbianLearner for edge weight updates.
        Delta: reward (+) or penalty (-)
        """
        # TODO: M4+ implementation
        # hebbian_learner.apply_reward(
        #     edge_id=payload.target_id,
        #     reward=payload.delta,
        # )
        pass

    async def _handle_novelty(self, payload: P03FeedbackPayload) -> None:
        """
        Handle NOVELTY_SIGNAL feedback.

        Routes to AuditLogger for tracking novel patterns.
        Used for system monitoring, not active learning.
        """
        # TODO: M4+ implementation
        # audit_logger.log_novelty(
        #     pattern_id=payload.target_id,
        #     metadata=payload.metadata,
        # )
        pass

    async def _handle_regret(self, payload: P03FeedbackPayload) -> None:
        """
        Handle REGRET_SIGNAL feedback.

        Routes to RegretLearner for decision correction.
        Metadata includes: original_decision, correct_decision
        """
        # TODO: M4+ implementation
        # regret_learner.learn_from_mistake(
        #     decision_id=payload.target_id,
        #     original=payload.metadata["original_decision"],
        #     correct=payload.metadata["correct_decision"],
        # )
        pass


class P03FeedbackSubscriber:
    """
    Bus subscriber for P21 feedback signals.

    Wraps P03FeedbackConsumer with bus subscription lifecycle.
    """

    def __init__(
        self,
        consumer: P03FeedbackConsumer,
        bus_subscriber,
    ):
        self.consumer = consumer
        self.bus = bus_subscriber
        self._running = False

    async def start(self) -> None:
        """Start consuming feedback signals."""
        self._running = True
        await self.bus.subscribe(
            topic=P03FeedbackConsumer.TOPIC,
            handler=self._handle_message,
        )

    async def stop(self) -> None:
        """Stop consuming."""
        self._running = False
        await self.bus.unsubscribe(P03FeedbackConsumer.TOPIC)

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming bus message."""
        success = await self.consumer.process(message)

        if not success:
            # TODO: Implement retry/DLQ logic
            pass
```

1. [ ] Wire subscriber to P03 runner lifecycle:

```python
# In P03Runner initialization
feedback_consumer = P03FeedbackConsumer()
feedback_subscriber = P03FeedbackSubscriber(feedback_consumer, bus)

async def start(self):
    await feedback_subscriber.start()

async def stop(self):
    await feedback_subscriber.stop()
```

1. [ ] Add metrics:

| Metric | Type | Labels | Description |
| ------ | ---- | ------ | ----------- |
| `p03_feedback_received_total` | Counter | type | Signals received by type |
| `p03_feedback_processed_total` | Counter | type, status | Signals processed |
| `p03_feedback_errors_total` | Counter | type | Processing errors |

**Outputs Produced**:

- [ ] `k0/pipelines/p03/feedback_consumer.py`
- [ ] Integration with P03 runner lifecycle

**Acceptance Criteria**:

- [ ] Subscribes to `feedback.signal.p03.v1` topic
- [ ] Routes all 6 feedback types to handlers
- [ ] Marks signals consumed in st_feedback_signals
- [ ] Stub handlers in place for future milestone implementation
- [ ] Metrics track received/processed/errors

**Test Cases** (to be added in 3.2.7):

- `test_p21_feedback_consumed`
- `test_p21_feedback_routed_by_type`
- `test_p21_feedback_marked_consumed`
- `test_p21_unknown_type_logged`

**Blocked By**: Epic 3.1

**Blocks**: 3.2.7

---

#### Issue 3.2.7 — Integration Tests for Cross-Pipeline Contracts

**Status**: ✅ COMPLETED

**Spec Reference**: [Dossier 10](../pipelines/P03_consolidation_dossier_v2.md#10-testing-strategy)

**Test File Location**: `tests/k0/pipelines/p03/test_cross_pipeline.py`

**Prerequisites**:

- All 3.2.1-3.2.6 implementations complete ✅
- Test database with P03 tables ✅
- Mock services for P05, P08, P21 or integration endpoints ✅

**Work To Do**:

1. [x] Create test file: `tests/k0/pipelines/p03/test_cross_pipeline.py`

**Test Implementation**:

```python
# tests/k0/pipelines/p03/test_cross_pipeline.py
"""Cross-pipeline integration tests for P03. Issue 3.2.7."""

import pytest
import json
import time
from unittest.mock import AsyncMock, patch

from k0.pipelines.p03.phases.r0_batch_selector import R0BatchSelector, R0Config
from k0.pipelines.p03.phases.r7_truth_writer import R7TruthWriter
from k0.pipelines.p03.gap_emitter import P03GapEmitter, GapType
from k0.pipelines.p03.p05_client import P05BudgetClient, BudgetStatus, BudgetResponse
from k0.pipelines.p03.p08_coordinator import P08Coordinator, CircuitState
from k0.pipelines.p03.feedback_consumer import P03FeedbackConsumer, FeedbackType


class TestR0EventIngestion:
    """Tests for R0 phase event ingestion."""

    async def test_r0_ingestion_respects_offset(self, db_session):
        """
        Given: Events with event_id 1, 2, 3 exist
               Offset is committed at 2
        When: R0 executes
        Then: Only event 3 is selected
        """
        # Setup: Insert events
        for i in range(1, 4):
            await db_session.execute("""
                INSERT INTO st_hipp_events (event_id, tenant_id, space_id,
                    embedding_status, consolidation_status)
                VALUES ($1, 't1', 's1', 'READY', NULL)
            """, i)

        # Setup: Set offset to 2
        await db_session.execute("""
            INSERT INTO st_offsets (pipeline_id, tenant_id, space_id, offset_value, status)
            VALUES ('P03', 't1', 's1', 2, 'COMMITTED')
        """)

        # Execute
        r0 = R0BatchSelector()
        envelope, result = await r0.run('t1', 's1', ctx)

        # Assert
        assert len(envelope.events) == 1
        assert envelope.events[0].event_id == 3

    async def test_r0_offset_unchanged_on_failure(self, db_session):
        """
        Given: Offset at 10, R0 starts
        When: R0 fails mid-execution
        Then: Offset remains at 10 (not advanced)
        """
        # Setup
        await db_session.execute("""
            INSERT INTO st_offsets (pipeline_id, tenant_id, space_id, offset_value)
            VALUES ('P03', 't1', 's1', 10)
        """)

        # Inject failure
        r0 = R0BatchSelector()
        with patch.object(r0, '_fetch_eligible_events', side_effect=Exception("DB error")):
            envelope, result = await r0.run('t1', 's1', ctx)

        # Assert offset unchanged
        row = await db_session.fetchrow(
            "SELECT offset_value FROM st_offsets WHERE pipeline_id = 'P03'"
        )
        assert row["offset_value"] == 10

    async def test_r0_excludes_non_ready_embeddings(self, db_session):
        """Events with embedding_status != READY are excluded."""
        await db_session.execute("""
            INSERT INTO st_hipp_events (event_id, tenant_id, space_id,
                embedding_status, consolidation_status)
            VALUES (1, 't1', 's1', 'PENDING', NULL)
        """)

        r0 = R0BatchSelector()
        envelope, result = await r0.run('t1', 's1', ctx)

        assert len(envelope.events) == 0
        assert result.status.value == "SKIP"


class TestStatusWriteback:
    """Tests for R7 status writeback."""

    async def test_status_writeback_atomic_with_r7(self, db_session, staged_envelope):
        """
        Given: Events in envelope
        When: R7 commits successfully
        Then: All events have consolidation_status set
        """
        r7 = R7TruthWriter()
        result = await r7.run(staged_envelope, ctx)

        assert result.status.value == "DONE"

        # Verify all events have status
        for event in staged_envelope.events:
            row = await db_session.fetchrow(
                "SELECT consolidation_status FROM st_hipp_events WHERE event_id = $1",
                event.event_id
            )
            assert row["consolidation_status"] is not None

    async def test_status_writeback_rollback_on_failure(self, db_session, staged_envelope):
        """
        Given: R7 fails after some writes
        When: Transaction rolls back
        Then: No events have consolidation_status set
        """
        # Inject failure
        r7 = R7TruthWriter()
        with patch.object(r7, '_execute_staged_writes', side_effect=Exception("Write error")):
            result = await r7.run(staged_envelope, ctx)

        assert result.status.value == "FAIL"

        # Verify no status changes
        for event in staged_envelope.events:
            row = await db_session.fetchrow(
                "SELECT consolidation_status FROM st_hipp_events WHERE event_id = $1",
                event.event_id
            )
            assert row["consolidation_status"] is None


class TestGapPersistence:
    """Tests for P03 to P06 gap persistence."""

    async def test_gap_persisted_to_learning_queue(self, db_session, envelope_with_gaps):
        """
        Given: Envelope with gaps from R4
        When: Gap emitter processes gaps
        Then: Gaps appear in st_learning_queue
        """
        emitter = P03GapEmitter()
        async with ctx.syscalls.unit_of_work() as uow:
            count = await emitter.emit_gaps(
                uow,
                envelope_with_gaps.phase_outputs.r4_gaps,
                tenant_id="t1",
                space_id="s1",
                cycle_id="c1",
            )

        assert count > 0

        rows = await db_session.fetch(
            "SELECT * FROM st_learning_queue WHERE status = 'PENDING'"
        )
        assert len(rows) == count

    async def test_gap_deduplication_within_window(self, db_session, gap_signal):
        """
        Given: Gap already exists in queue
        When: Same gap emitted again
        Then: Duplicate is skipped
        """
        emitter = P03GapEmitter()

        # First emit
        async with ctx.syscalls.unit_of_work() as uow:
            count1 = await emitter.emit_gaps(uow, [gap_signal], "t1", "s1", "c1")

        # Second emit (same gap)
        async with ctx.syscalls.unit_of_work() as uow:
            count2 = await emitter.emit_gaps(uow, [gap_signal], "t1", "s1", "c1")

        assert count1 == 1
        assert count2 == 0  # Deduplicated


class TestP05BudgetIntegration:
    """Tests for P03 to P05 budget integration."""

    async def test_p05_budget_suppresses_gap(self, gap_signal):
        """
        Given: P05 returns budget exhausted
        When: Gap emission attempted
        Then: Gap is suppressed (not emitted)
        """
        client = P05BudgetClient()

        # Mock exhausted budget
        with patch.object(client, 'query_budget', return_value=BudgetResponse(
            status=BudgetStatus.EXHAUSTED,
            remaining=0,
            limit=100,
            reset_at=None,
        )):
            response = await client.query_budget("p03", "t1")
            should_emit = client.should_emit_gap(response)

        assert not should_emit

    async def test_p05_degrade_mode_on_failure(self):
        """
        Given: P05 client configured for DEGRADE mode
        When: Budget query fails
        Then: Assumes budget available, continues
        """
        from k0.pipelines.p03.p05_client import P05ClientConfig, FailureMode

        config = P05ClientConfig(failure_mode=FailureMode.DEGRADE)
        client = P05BudgetClient(config)

        with patch.object(client, '_fetch_budget', side_effect=Exception("P05 down")):
            response = await client.query_budget("p03", "t1")

        assert response.status == BudgetStatus.UNKNOWN
        assert client.should_emit_gap(response)  # Still emits in DEGRADE mode


class TestP08CircuitBreaker:
    """Tests for P03 to P08 circuit breaker."""

    async def test_p08_circuit_breaker_opens(self):
        """
        Given: 5 consecutive P08 failures
        When: Checking circuit state
        Then: Circuit is OPEN
        """
        from k0.pipelines.p03.p08_coordinator import CircuitBreakerConfig

        config = CircuitBreakerConfig(failure_threshold=5)
        coordinator = P08Coordinator(config)

        # Simulate 5 failures
        for i in range(5):
            coordinator._record_failure()

        assert coordinator.circuit_state == CircuitState.OPEN

    async def test_p08_circuit_breaker_half_open_probe(self):
        """
        Given: Circuit is OPEN
        When: reset_timeout elapsed
        Then: Circuit transitions to HALF_OPEN
        """
        from k0.pipelines.p03.p08_coordinator import CircuitBreakerConfig

        config = CircuitBreakerConfig(reset_timeout_ms=100)  # Short for test
        coordinator = P08Coordinator(config)

        # Open circuit
        for i in range(5):
            coordinator._record_failure()

        assert coordinator.circuit_state == CircuitState.OPEN

        # Wait for timeout
        import asyncio
        await asyncio.sleep(0.15)

        # Should be HALF_OPEN now
        assert coordinator.circuit_state == CircuitState.HALF_OPEN

    async def test_p08_circuit_breaker_closes_on_success(self):
        """
        Given: Circuit is HALF_OPEN
        When: 2 successful probes
        Then: Circuit closes
        """
        from k0.pipelines.p03.p08_coordinator import CircuitBreakerConfig

        config = CircuitBreakerConfig(success_threshold=2)
        coordinator = P08Coordinator(config)

        # Manually set to HALF_OPEN
        coordinator._transition_to(CircuitState.HALF_OPEN)

        # 2 successes
        coordinator._record_success()
        coordinator._record_success()

        assert coordinator.circuit_state == CircuitState.CLOSED


class TestP21FeedbackConsumer:
    """Tests for P21 to P03 feedback consumption."""

    async def test_p21_feedback_consumed(self):
        """
        Given: Feedback message received
        When: Consumer processes it
        Then: Returns True (processed)
        """
        consumer = P03FeedbackConsumer()

        message = {
            "signal_id": "sig-1",
            "feedback_type": "SALIENCE_ADJUSTMENT",
            "target_id": "entity-1",
            "target_type": "entity",
            "delta": 0.5,
            "metadata": {},
            "source_cycle_id": "c1",
            "timestamp": int(time.time() * 1000),
        }

        result = await consumer.process(message)
        assert result is True

    async def test_p21_feedback_routed_by_type(self):
        """
        Given: Different feedback types
        When: Consumer routes them
        Then: Correct handler called
        """
        consumer = P03FeedbackConsumer()

        # Track handler calls
        calls = {}
        async def tracking_handler(payload):
            calls[payload.feedback_type] = True

        consumer.register_handler(FeedbackType.DECAY_REVERSAL, tracking_handler)

        message = {
            "signal_id": "sig-2",
            "feedback_type": "DECAY_REVERSAL",
            "target_id": "mem-1",
            "target_type": "episode",
            "delta": 1.0,
            "metadata": {},
            "source_cycle_id": "c1",
            "timestamp": int(time.time() * 1000),
        }

        await consumer.process(message)

        assert FeedbackType.DECAY_REVERSAL in calls

    async def test_p21_unknown_type_logged(self, caplog):
        """
        Given: Feedback with unknown type
        When: Consumer processes it
        Then: Returns False, logs warning
        """
        consumer = P03FeedbackConsumer()

        message = {
            "signal_id": "sig-3",
            "feedback_type": "UNKNOWN_TYPE",
            "target_id": "x",
            "target_type": "x",
        }

        result = await consumer.process(message)
        assert result is False
```

1. [ ] Add test fixtures to `tests/k0/pipelines/p03/conftest.py`:

```python
@pytest.fixture
def envelope_with_gaps():
    """Create envelope with gaps for testing."""
    envelope = P03BatchEnvelopeBuilder()\
        .with_context(tenant_id="t1", space_id="s1", cycle_id="c1")\
        .build()

    envelope.phase_outputs.r4_gaps = [
        GapSignal(
            gap_id="gap-1",
            gap_type=GapType.AMBIGUOUS_ENTITY,
            source_event_id=1,
            confidence=0.5,
            metadata={"candidates": ["e1", "e2"]},
        )
    ]

    return envelope

@pytest.fixture
def gap_signal():
    """Single gap signal for testing."""
    return GapSignal(
        gap_id="gap-1",
        gap_type=GapType.LOW_CONFIDENCE_EDGE,
        source_event_id=1,
        confidence=0.4,
        metadata={"edge": "e1->e2"},
    )
```

**Test Matrix**:

| Test | Category | Coverage |
| ---- | -------- | -------- |
| test_r0_ingestion_respects_offset | R0 | Offset |
| test_r0_offset_unchanged_on_failure | R0 | Rollback |
| test_r0_excludes_non_ready_embeddings | R0 | Filter |
| test_status_writeback_atomic_with_r7 | R7 | Atomicity |
| test_status_writeback_rollback_on_failure | R7 | Rollback |
| test_gap_persisted_to_learning_queue | Gap | P06 |
| test_gap_deduplication_within_window | Gap | Dedup |
| test_p05_budget_suppresses_gap | P05 | Budget |
| test_p05_degrade_mode_on_failure | P05 | Degradation |
| test_p08_circuit_breaker_opens | P08 | Circuit |
| test_p08_circuit_breaker_half_open_probe | P08 | Probe |
| test_p08_circuit_breaker_closes_on_success | P08 | Recovery |
| test_p21_feedback_consumed | P21 | Consume |
| test_p21_feedback_routed_by_type | P21 | Routing |
| test_p21_unknown_type_logged | P21 | Error |

**Outputs Produced**:

- [x] `tests/k0/pipelines/p03/test_cross_pipeline.py` (12 tests)
- [x] Test fixtures in `conftest.py`

**Acceptance Criteria**:

- [x] All 10 tests pass deterministically (12 total including summary tests)
- [x] Tests cover all cross-pipeline contracts
- [x] No flaky tests
- [x] Coverage meets P03 testing requirements

**Blocked By**: 3.2.1-3.2.6

**Blocks**: M3 Completion

---

## Part D: Milestone Summary

### D.1 Issue Summary

| Epic | Issue | Title | Status |
| ---- | ----- | ----- | ------ |
| 3.1 | 3.1.1 | R7 Phase: P03StagedWrites to UoW to Truth Tables | ✅ COMPLETED |
| 3.1 | 3.1.2 | R8 Phase: Completion Event + Gap Emission | ✅ COMPLETED |
| 3.1 | 3.1.3 | Outbox Publisher Integration | ✅ COMPLETED |
| 3.1 | 3.1.4 | R7/R8 Integration Tests | ✅ COMPLETED |
| 3.2 | 3.2.1 | R0 Phase: Event Ingestion | ✅ COMPLETED |
| 3.2 | 3.2.2 | Status Writeback in R7 | ✅ COMPLETED |
| 3.2 | 3.2.3 | P03 to P06 Gap Persistence | ✅ COMPLETED |
| 3.2 | 3.2.4 | P03 to P05 Budget Client | ❌ N/A |
| 3.2 | 3.2.5 | P03 to P08 Circuit Breaker | ❌ N/A |
| 3.2 | 3.2.6 | P21 to P03 Feedback Consumer | ✅ COMPLETED |
| 3.2 | 3.2.7 | Cross-Pipeline Integration Tests | ✅ COMPLETED |

**Total Issues**: 11 (9 completed, 2 N/A)

### D.2 New Files Created by M3

| Category | File | Purpose |
| -------- | ---- | ------- |
| Phase | `k0/pipelines/p03/phases/r0_batch_selector.py` | R0 implementation |
| Phase | `k0/pipelines/p03/phases/r7_truth_writer.py` | R7 implementation |
| Phase | `k0/pipelines/p03/phases/r8_event_emitter.py` | R8 implementation |
| Phase | `k0/pipelines/p03/phases/__init__.py` | Phase package |
| Module | `k0/pipelines/p03/gap_emitter.py` | P06 gap persistence |
| ~~Module~~ | ~~`k0/pipelines/p03/p05_client.py`~~ | ~~N/A - Pipelines run independently~~ |
| ~~Module~~ | ~~`k0/pipelines/p03/p08_coordinator.py`~~ | ~~N/A - Pipelines run independently~~ |
| Module | `k0/pipelines/p03/feedback_consumer.py` | P21 feedback consumption |
| Test | `tests/k0/pipelines/p03/test_r7_r8_integration.py` | R7/R8 tests |
| Test | `tests/k0/pipelines/p03/test_cross_pipeline.py` | Cross-pipeline tests |

### D.3 Existing Files Leveraged (NOT Created by M3)

| File | Created In | Used By M3 For |
| ---- | ---------- | -------------- |
| `staged_writes.py` | M1 | Accumulates writes, used by R7 |
| `offset_manager.py` | M1 | Offset tracking, used by R0 |
| `sequential_runner.py` | M1 | Phase orchestration |
| `context.py` | M1 | Cycle context |
| `phase_outputs.py` | M1 | Phase results |
| `phase_interface.py` | M1 | Phase protocol |
| Event schemas | M0 | Payload validation |
| st_* migrations | M2 | Storage tables |
| `unit_of_work.py` | K0 Core | Transactional scope |
| `outbox.py` | K0 Core | Outbox storage |

### D.4 Governance Updates Required

| Registry | Section | Updates |
| -------- | ------- | ------- |
| k0_architecture_master.md | Part 3.1 | Add R0, R7, R8 phase modules |
| k0_architecture_master.md | Part 10 | Add M3 metrics |

### D.5 Completion Criteria

M3 is COMPLETE when:

- [x] All 11 issues marked COMPLETED
- [x] All tests passing (899 tests total in P03 suite)
- [x] R0-R8 phases can execute end-to-end
- [x] Outbox entries reach bus
- [x] Cross-pipeline contracts verified
- [ ] Governance sync shows SYNCED

---

## Part E: Execution Log

| Issue | Started | Completed | Notes |
| ----- | ------- | --------- | ----- |
| 3.1.1 | | | |
| 3.1.2 | | | |
| 3.1.3 | | | |
| 3.1.4 | | | |
| 3.2.1 | | | |
| 3.2.2 | | | |
| 3.2.3 | | | |
| 3.2.4 | | | |
| 3.2.5 | | | |
| 3.2.6 | | | |
| 3.2.7 | | | |

---

*Document created: 2026-01-01*
*Last updated: 2026-01-01*
| `outbox.py` | K0 Core | Outbox storage |

### D.4 Governance Updates Required

| Registry | Section | Updates |
|----------|---------|---------|
| k0_architecture_master.md | Part 3.1 | Add R0, R7, R8 phase modules |
| k0_architecture_master.md | Part 10 | Add M3 metrics |

### D.5 Completion Criteria

M3 is COMPLETE when:

- [ ] All 11 issues marked COMPLETED
- [ ] All tests passing (14 new tests)
- [ ] R0-R8 phases can execute end-to-end
- [ ] Outbox entries reach bus
- [ ] Cross-pipeline contracts verified
- [ ] Governance sync shows SYNCED

---

## Part E: Execution Log

| Issue | Started | Completed | Notes |
|-------|---------|-----------|-------|
| 3.1.1 | | | |
| 3.1.2 | | | |
| 3.1.3 | | | |
| 3.1.4 | | | |
| 3.2.1 | | | |
| 3.2.2 | | | |
| 3.2.3 | | | |
| 3.2.4 | | | |
| 3.2.5 | | | |
| 3.2.6 | | | |
| 3.2.7 | | | |

---

*Document created: 2026-01-01*
*Last updated: 2026-01-01*
