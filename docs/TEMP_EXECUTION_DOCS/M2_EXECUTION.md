# P03 Milestone 2 Execution Document

> **Milestone**: M2 — Storage + migrations + transactional backbone
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M1 COMPLETED (2025-01-01)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD (after M1 completion)

---

## Part A: Context Foundation (BEFORE YOU START)

### A.0 M0/M1 Outputs (PREREQUISITES FROM PREVIOUS MILESTONES)

> **References**: [M0_EXECUTION.md](./M0_EXECUTION.md), [M1_EXECUTION.md](./M1_EXECUTION.md)

**M0 Created These Artifacts That M2 Depends On**:

| Artifact | Path | M2 Issues Using It |
|----------|------|-------------------|
| Pipeline ADR | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | 2.1.1, 2.2.1 |
| Pipeline Contract | [k0/contracts/pipelines/p03_consolidation.v1.yaml](../../k0/contracts/pipelines/p03_consolidation.v1.yaml) | 2.1.1 (storage dependencies) |
| Capability Contract | [k0/contracts/capabilities/consolidation.v1.yaml](../../k0/contracts/capabilities/consolidation.v1.yaml) | 2.2.2, 2.2.3 |
| Master Registry Update | [k0_architecture_master.md](../../governance/k0/k0_architecture_master.md) | All issues (Part 6 Storage) |

**M1 Created These Artifacts That M2 Depends On**:

| Artifact | Path | M2 Issues Using It |
|----------|------|-------------------|
| P03BatchEnvelope | [k0/pipelines/p03/envelope.py](../../k0/pipelines/p03/envelope.py) | 2.2.2 (audit context) |
| P03CycleContext | [k0/pipelines/p03/context.py](../../k0/pipelines/p03/context.py) | 2.2.2, 2.3.x (cycle_id, space_id) |
| P03StagedWrites | [k0/pipelines/p03/staged_writes.py](../../k0/pipelines/p03/staged_writes.py) | 2.1.x (layer table names) |
| P03ObservabilityContext | [k0/pipelines/p03/observability.py](../../k0/pipelines/p03/observability.py) | 2.2.2 (audit logging) |
| P03EnvelopeSerializer | [k0/pipelines/p03/serializer.py](../../k0/pipelines/p03/serializer.py) | 2.2.2 (JSON serialization) |
| P03SequentialRunner | [k0/pipelines/p03/sequential_runner.py](../../k0/pipelines/p03/sequential_runner.py) | 2.2.2, 2.3.x (phase context) |
| P03 Checkpoint Contract | [k0/pipelines/p03/checkpoint.py](../../k0/pipelines/p03/checkpoint.py) | 2.1.12 (offsets/status) |
| P03 Offset Manager | [k0/pipelines/p03/offset_manager.py](../../k0/pipelines/p03/offset_manager.py) | 2.1.12 (st_offsets usage) |

**M0/M1 Governance Status**: ✅ SYNCED (verified 2025-01-01)
**M1 Test Count**: 399 tests passing

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| §6.2 | st_hipp_events (P03 columns) | [Dossier §6.2](../pipelines/P03_consolidation_dossier_v2.md#62-st_hipp_events) | Consolidation status columns |
| §6.3 | st_epi (episodic) | [Dossier §6.3](../pipelines/P03_consolidation_dossier_v2.md#63-st_epi) | Episodic memory table |
| §6.4 | st_sem (semantic) | [Dossier §6.4](../pipelines/P03_consolidation_dossier_v2.md#64-st_sem) | Semantic patterns table |
| §6.5 | st_procedural (habits) | [Dossier §6.5](../pipelines/P03_consolidation_dossier_v2.md#65-st_procedural) | Procedural memory table |
| §6.6 | st_social (relationships) | [Dossier §6.6](../pipelines/P03_consolidation_dossier_v2.md#66-st_social) | Social graph table |
| §6.7 | st_prospective (intentions) | [Dossier §6.7](../pipelines/P03_consolidation_dossier_v2.md#67-st_prospective) | Goals and intentions table |
| §6.8 | st_kg_dom (KG entities) | [Dossier §6.8](../pipelines/P03_consolidation_dossier_v2.md#68-st_kg_dom) | Knowledge graph entities |
| §6.9 | st_kg_edges (KG relations) | [Dossier §6.9](../pipelines/P03_consolidation_dossier_v2.md#69-st_kg_edges) | Knowledge graph edges |
| §6.10 | st_vec (embeddings) | [Dossier §6.10](../pipelines/P03_consolidation_dossier_v2.md#610-st_vec) | Vector embeddings |
| §6.11 | st_learning_queue (gaps) | [Dossier §6.11](../pipelines/P03_consolidation_dossier_v2.md#611-st_learning_queue) | Gap detection queue |
| §6.12 | st_anchors (Bayesian) | [Dossier §6.12](../pipelines/P03_consolidation_dossier_v2.md#612-st_anchors) | Thompson sampling anchors |
| §6.13 | st_anchor_observations | [Dossier §6.13](../pipelines/P03_consolidation_dossier_v2.md#613-st_anchor_observations) | Anchor outcome tracking |
| §6.14 | st_offsets/status/watermarks | [Dossier §6.14](../pipelines/P03_consolidation_dossier_v2.md#614-operational-tables) | Resume infrastructure |
| §6.15 | st_outbox | [Dossier §6.15](../pipelines/P03_consolidation_dossier_v2.md#615-st_outbox) | Transactional outbox |
| §6.16 | st_retention_policy | [Dossier §6.16](../pipelines/P03_consolidation_dossier_v2.md#616-st_retention_policy) | Retention rules |
| §6.17 | st_learned_weights | [Dossier §6.17](../pipelines/P03_consolidation_dossier_v2.md#617-st_learned_weights) | Thompson sampling params |
| §6.20 | st_consolidation_audit | [Dossier §6.20](../pipelines/P03_consolidation_dossier_v2.md#620-st_consolidation_audit) | Decision audit trail |
| §6.21 | st_feedback_quarantine | [Dossier §6.21](../pipelines/P03_consolidation_dossier_v2.md#621-st_feedback_quarantine) | Suspicious feedback |
| §6.23 | st_learned_weights_history | [Dossier §6.23](../pipelines/P03_consolidation_dossier_v2.md#623-st_learned_weights_history) | Parameter history |
| §13.4 | st_dlq (dead letter queue) | [Dossier §13.4](../pipelines/P03_consolidation_dossier_v2.md#134-st_dlq) | Failed message storage |
| §14.7 | GDPR erasure | [Dossier §14.7](../pipelines/P03_consolidation_dossier_v2.md#147-gdpr) | Data minimization |
| §14.10 | Explanation templates | [Dossier §14.10](../pipelines/P03_consolidation_dossier_v2.md#1410-explanation-templates) | Audit explanations |
| Appendix I | RLS Posture | [Dossier Appendix I](../pipelines/P03_consolidation_dossier_v2.md#appendix-i-rls-posture) | Row-level security |

### A.2 Existing Alembic Migrations (MUST AUDIT)

| Migration | Table(s) | Path | Status |
|-----------|----------|------|--------|
| 0005 | st_offsets | [k0/db/alembic/versions/0005_st_offsets.py](../../k0/db/alembic/versions/0005_st_offsets.py) | TBD |
| 0008 | st_outbox | [k0/db/alembic/versions/0008_st_outbox.py](../../k0/db/alembic/versions/0008_st_outbox.py) | TBD |
| 0009 | st_dlq | [k0/db/alembic/versions/0009_st_dlq.py](../../k0/db/alembic/versions/0009_st_dlq.py) | TBD |
| 0014 | st_retention_policy | [k0/db/alembic/versions/0014_st_retention_policy.py](../../k0/db/alembic/versions/0014_st_retention_policy.py) | TBD |
| 0020 | st_pipeline_status | [k0/db/alembic/versions/0020_st_pipeline_status.py](../../k0/db/alembic/versions/0020_st_pipeline_status.py) | TBD |
| 0021 | st_pipeline_watermarks | [k0/db/alembic/versions/0021_st_pipeline_watermarks.py](../../k0/db/alembic/versions/0021_st_pipeline_watermarks.py) | TBD |
| 0022 | st_hipp_events | [k0/db/alembic/versions/0022_st_hipp_events.py](../../k0/db/alembic/versions/0022_st_hipp_events.py) | TBD |
| 0025 | st_vec | [k0/db/alembic/versions/0025_st_vec.py](../../k0/db/alembic/versions/0025_st_vec.py) | TBD |

### A.3 ADRs to Reference

| ADR | Path | Governs |
|-----|------|---------|
| K010 | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | P03 pipeline architecture |
| K010.1 | [k010.1-sleep-cycle-state-machine.md](../architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md) | R0-R8 state machine |
| K002 | [k002-idempotency-toctou-race-fix.md](../architecture/decisions-K0/k002-idempotency-toctou-race-fix.md) | Idempotency patterns |
| K004 | [k004-capability-mesh-architecture.md](../architecture/decisions-K0/k004-capability-mesh-architecture.md) | Capability model |

### A.4 Governance Sync Tool (RUN BEFORE AND AFTER EACH EPIC)

| Tool | Path | Command |
|------|------|---------|
| Sync Script | [governance/k0/scripts/sync.py](../../governance/k0/scripts/sync.py) | `python -m governance.k0.scripts.sync --report` |
| Event Scanner | [governance/k0/scripts/event_scanner.py](../../governance/k0/scripts/event_scanner.py) | Validates event topics |
| Contract Scanner | [governance/k0/scripts/contract_scanner.py](../../governance/k0/scripts/contract_scanner.py) | Validates contract files |

**When To Run Governance Sync**:

- ✅ Before starting any Epic (capture baseline)
- ✅ After completing any Epic (verify no drift)
- ✅ Before marking M2 complete (final verification)

### A.5 K0 Storage Patterns to Follow

| Pattern | Path | What to Learn |
|---------|------|---------------|
| Alembic Migration | [k0/db/alembic/versions/](../../k0/db/alembic/versions/) | Migration file naming, upgrade/downgrade |
| Storage Driver | [k0/storage/postgres.py](../../k0/storage/postgres.py) | PostgreSQL connection patterns |
| WAL Append | [k0/storage/wal.py](../../k0/storage/wal.py) | Write-ahead log usage |
| Retention Enforcer | [k0/policy/retention_enforcer.py](../../k0/policy/retention_enforcer.py) | Retention job patterns |
| Policy Redaction | [k0/policy/redaction.py](../../k0/policy/redaction.py) | PII redaction for audit |

---

## Part B: Code Discovery Results

> **Code discovery completed 2026-01-01 — Actual findings from codebase analysis**

### B.1 Existing Alembic Migration Patterns Found

| File | Pattern | Relevant For |
|------|---------|--------------|
| `0022_st_hipp_events.py` | ~80 columns, grouped by category (Identity, Integrity, Policy, Actor, Temporal), BigInteger timestamps, Text IDs, CheckConstraints | 2.1.10 (adding P03 columns) |
| `0008_st_outbox.py` | `next_attempt_ts` is **TEXT not BIGINT**, status CHECK constraint, partial indexes | 2.1.11 (type reconciliation) |
| `0005_st_offsets.py` | Composite PK (subscriber_id, topic, space_id, tenant_id), `updated_ts` as TEXT | 2.1.12 (verify alignment) |
| `0025_st_vec.py` | FK to `st_hipp_events`, LargeBinary for vectors, status CHECK, multiple indexes | 2.1.9 (verify alignment) |
| `0009_st_dlq.py` | BigInteger auto-increment id, TEXT timestamps, state CHECK constraint | 2.3.10 (reconcile with dossier) |
| `0020_st_pipeline_status.py` | Composite PK (pipeline_id, wal_pos), status CHECK (OK/ERROR/DEFERRED), BigInteger timestamps | 2.1.12 |
| `0021_st_pipeline_watermarks.py` | Composite PK (pipeline_id, space_id), BigInteger watermark | 2.1.12 |
| `0014_st_retention_policy.py` | Text policy_id PK, privacy_band CHECK (GREEN/AMBER/RED), archive settings | 2.1.12, 2.2.4 |
| `0026_st_feedback_signals.py` | Uses **JSONB** for payload/correlation/provenance, validation_status column | 2.3.8 (consumption semantics) |

### B.2 Existing Storage Drivers Found

| File | Class/Function | Pattern | Relevant For |
|------|----------------|---------|--------------|
| `k0/storage/outbox.py` | `OutboxStore` | Async PostgreSQL, `enqueue()` method, dataclass `OutboxEntry` | 2.1.11 (outbox alignment) |
| `k0/storage/offsets.py` | `OffsetStore` | Async PostgreSQL, `upsert()`/`fetch()`, composite key lookups | 2.1.12 (offsets alignment) |
| `k0/storage/dlq.py` | `DeadLetterQueue` | Async PostgreSQL, `record()` method, dataclass `DeadLetter` | 2.3.10 (DLQ reconciliation) |
| `k0/storage/wal.py` | WAL primitives | Append-only log patterns | 2.2.5 (erasure compliance) |
| `k0/policy/retention_enforcer.py` | Retention job | Policy-driven deletion patterns | 2.2.4 (audit retention) |

### B.3 Truth Layer Tables Gap Analysis

| Table | Dossier Section | Existing Migration | Status | Delta Required |
|-------|-----------------|-------------------|--------|----------------|
| `st_epi` | §6.3 | **NONE** | **MISSING** | Create new migration |
| `st_sem` | §6.4 | **NONE** | **MISSING** | Create new migration |
| `st_procedural` | §6.5 | **NONE** | **MISSING** | Create new migration |
| `st_social` | §6.6 | **NONE** | **MISSING** | Create new migration |
| `st_prospective` | §6.7 | **NONE** | **MISSING** | Create new migration |
| `st_kg_dom` | §6.8 | **NONE** | **MISSING** | Create new migration |
| `st_kg_edges` | §6.9 | **NONE** | **MISSING** | Create new migration |
| `st_vec` | §6.10 | `0025_st_vec.py` | **EXISTS** | Verify alignment |
| `st_hipp_events` | §6.2 | `0022_st_hipp_events.py` | **PARTIAL** | Add P03 consolidation columns |

### B.4 Operational Tables Gap Analysis

| Table | Dossier Section | Existing Migration | Status | Delta Required |
|-------|-----------------|-------------------|--------|----------------|
| `st_offsets` | §6.14 | `0005_st_offsets.py` | **EXISTS** | Verify alignment |
| `st_pipeline_status` | §6.14 | `0020_st_pipeline_status.py` | **EXISTS** | Verify alignment |
| `st_pipeline_watermarks` | §6.14 | `0021_st_pipeline_watermarks.py` | **EXISTS** | Verify alignment |
| `st_outbox` | §6.15 | `0008_st_outbox.py` | **MISMATCH** | `next_attempt_ts` TEXT→BIGINT |
| `st_retention_policy` | §6.16 | `0014_st_retention_policy.py` | **EXISTS** | Verify alignment |

### B.5 Learning + Audit Tables Gap Analysis

| Table | Dossier Section | Existing Migration | Status | Delta Required |
|-------|-----------------|-------------------|--------|----------------|
| `st_consolidation_audit` | §6.20 | **NONE** | **MISSING** | Create new migration |
| `st_learning_queue` | §6.11 | **NONE** | **MISSING** | Create new migration |
| `st_anchors` | §6.12 | **NONE** | **MISSING** | Create new migration |
| `st_anchor_observations` | §6.13 | **NONE** | **MISSING** | Create new migration |
| `st_learned_weights` | §6.17 | **NONE** | **MISSING** | Create new migration |
| `st_learned_weights_history` | §6.23 | **NONE** | **MISSING** | Create new migration |
| `st_feedback_quarantine` | §6.21 | **NONE** | **MISSING** | Create new migration |
| `st_golden_dataset_pairs` | Golden dataset | **NONE** | **MISSING** | Create new migration |
| `st_validation_results` | Golden dataset | **NONE** | **MISSING** | Create new migration |
| `st_dlq` | §13.4 | `0009_st_dlq.py` | **MISMATCH** | Schema differs from dossier |
| `st_feedback_signals` | Consumption | `0026_st_feedback_signals.py` | **PARTIAL** | Add consumed_at/consumed_by |

### B.6 Key Findings Summary

**Critical Mismatches Requiring Decisions**:

1. **`st_outbox.next_attempt_ts`**: Current migration uses TEXT, dossier uses BIGINT
   - **Impact**: Timestamp sorting/comparison bugs in retry scheduling
   - **Action**: Issue 2.1.11 must add corrective migration

2. **`st_dlq` schema**: Current migration (BigInteger id, TEXT timestamps) differs from dossier (pipeline_id, phase, error tracking columns)
   - **Impact**: P03 error handling may not have required fields
   - **Action**: Issue 2.3.10 requires decision + corrective migration

3. **`st_feedback_signals` consumption**: Missing `consumed_at`/`consumed_by` columns for P03 consumption semantics
   - **Impact**: P03 cannot mark signals as consumed
   - **Action**: Issue 2.3.8 requires decision + corrective migration

**New Migrations Required (15 total)**:

| Priority | Table | Issue |
|----------|-------|-------|
| HIGH | `st_epi` | 2.1.2 |
| HIGH | `st_sem` | 2.1.3 |
| HIGH | `st_procedural` | 2.1.4 |
| HIGH | `st_social` | 2.1.5 |
| HIGH | `st_prospective` | 2.1.6 |
| HIGH | `st_kg_dom` | 2.1.7 |
| HIGH | `st_kg_edges` | 2.1.8 |
| HIGH | `st_hipp_events` (P03 columns) | 2.1.10 |
| MEDIUM | `st_consolidation_audit` | 2.2.1 |
| MEDIUM | `st_learning_queue` | 2.3.2 |
| MEDIUM | `st_anchors` | 2.3.3 |
| MEDIUM | `st_anchor_observations` | 2.3.4 |
| MEDIUM | `st_learned_weights` | 2.3.5 |
| MEDIUM | `st_learned_weights_history` | 2.3.6 |
| MEDIUM | `st_feedback_quarantine` | 2.3.7 |
| LOW | `st_golden_dataset_pairs` + `st_validation_results` | 2.3.9 |

**Corrective Migrations Required (3 total)**:

| Table | Issue | Delta |
|-------|-------|-------|
| `st_outbox` | 2.1.11 | `next_attempt_ts` TEXT→BIGINT |
| `st_dlq` | 2.3.10 | Add pipeline_id, phase, error columns |
| `st_feedback_signals` | 2.3.8 | Add consumed_at, consumed_by columns |

### B.7 Migration Naming Convention (from existing patterns)

```
Format: XXXX_st_<table_name>.py
Examples:
  0027_st_epi.py
  0028_st_sem.py
  0029_st_procedural.py
  0030_st_social.py
  0031_st_prospective.py
  0032_st_kg_dom.py
  0033_st_kg_edges.py
  0034_st_hipp_events_p03_columns.py
  0035_st_consolidation_audit.py
  0036_st_outbox_next_attempt_ts.py
  ...
```

---

## Part C: Scope Boundaries (WHAT TO DO / NOT DO)

### C.1 Migrations To CREATE (Epic 2.1)

| File Path | Purpose | Created By Issue |
|-----------|---------|------------------|
| `k0/db/alembic/versions/00XX_st_epi.py` | Episodic memory table | 2.1.2 |
| `k0/db/alembic/versions/00XX_st_sem.py` | Semantic patterns table | 2.1.3 |
| `k0/db/alembic/versions/00XX_st_procedural.py` | Procedural memory table | 2.1.4 |
| `k0/db/alembic/versions/00XX_st_social.py` | Social relationships table | 2.1.5 |
| `k0/db/alembic/versions/00XX_st_prospective.py` | Intentions/goals table | 2.1.6 |
| `k0/db/alembic/versions/00XX_st_kg_dom.py` | KG entities table | 2.1.7 |
| `k0/db/alembic/versions/00XX_st_kg_edges.py` | KG edges table | 2.1.8 |
| `k0/db/alembic/versions/00XX_st_hipp_events_p03.py` | P03 consolidation columns | 2.1.10 |
| `k0/db/alembic/versions/00XX_st_consolidation_audit.py` | Audit table | 2.2.1 |

### C.2 Files To CREATE (Epic 2.2/2.3)

| File Path | Purpose | Created By Issue |
|-----------|---------|------------------|
| `k0/pipelines/p03/audit_logger.py` | Decision audit write path | 2.2.2 |
| `k0/pipelines/p03/explainability.py` | Audit query API | 2.2.3 |
| `k0/pipelines/p03/retention.py` | Audit retention job | 2.2.4 |
| `k0/pipelines/p03/erasure.py` | GDPR erasure handler | 2.2.5 |
| `tests/k0/pipelines/p03/test_storage.py` | Storage integration tests | 2.1.x, 2.2.x |

### C.3 Files To NEVER EDIT (Append-Only Migrations)

| File Path | Reason |
|-----------|--------|
| `k0/db/alembic/versions/0005_st_offsets.py` | Past migration - add corrective only |
| `k0/db/alembic/versions/0008_st_outbox.py` | Past migration - add corrective only |
| `k0/db/alembic/versions/0009_st_dlq.py` | Past migration - add corrective only |
| `k0/db/alembic/versions/0022_st_hipp_events.py` | Past migration - add corrective only |
| `k0/db/alembic/versions/0025_st_vec.py` | Past migration - add corrective only |

### C.4 Out of Scope (Deferred)

| Item | Deferred To | Reason |
|------|-------------|--------|
| Actual phase implementations (R0-R8) | M3-M6 | Phase code is later milestones |
| P08 embedding integration | M4 | Embedding pipeline integration |
| Thompson sampling algorithm | M5 | Learning algorithm implementation |
| Production RLS policies | M7 | Hardening milestone |

---

## Part D: Execution Checklist (THE WORK)

### Epic 2.1 — Core truth + operational tables

> **Status**: ✅ COMPLETED
> **Source**: [P03_implementation_plan_skeleton.md](../pipelines/P03_implementation_plan_skeleton.md) (Lines 738-936)
> **Governance Baseline**: Pre-Epic sync verified
> **Issues**: 2.1.1–2.1.12 (12 issues) — ALL COMPLETE
> **Tests**: 42 tests in `tests/k0/pipelines/p03/test_p03_storage_migrations.py`

**Summary**:

- Epic 2.1 covers **truth-layer tables** (st_epi, st_sem, st_procedural, st_social, st_prospective, st_kg_dom, st_kg_edges)
- Epic 2.1 covers **operational backbone tables** (st_offsets, st_pipeline_status, st_pipeline_watermarks, st_outbox, st_retention_policy)
- Epic 2.1 covers **P03 consolidation columns** on st_hipp_events
- Epic 2.1 does **NOT** cover learning/audit tables (those are Epic 2.2/2.3)

**Migrations Created**:

- `0027_st_epi.py` — Episodic memory (33 columns, 4 indexes)
- `0028_st_sem.py` — Semantic patterns (26 columns, 4 indexes)
- `0029_st_procedural.py` — Procedural habits (27 columns, 3 indexes)
- `0030_st_social.py` — Social relationships (27 columns, 2 indexes)
- `0031_st_prospective.py` — Prospective intentions (23 columns, 2 indexes)
- `0032_st_kg_dom.py` — KG entities (23 columns, 3 indexes)
- `0033_st_kg_edges.py` — KG relationships (22 columns, 3 indexes)
- `0034_st_hipp_events_p03_columns.py` — P03 consolidation columns (6 columns, 1 partial index)
- `0035_st_outbox_fix_next_attempt_ts.py` — Type fix TEXT→BIGINT

---

#### Issue 2.1.1 — Storage gap analysis: dossier schema vs existing Alembic migrations (truth + ops tables)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Produce a precise "already exists vs missing vs mismatched" map for P03's required tables, before writing new migrations.

**Spec Reference**: [Dossier §6 Storage Schema Design](../pipelines/P03_consolidation_dossier_v2.md#6-storage-schema-design)

---

### 🎯 DECISION NOTE — Issue 2.1.1

#### Decision 1: Gap Analysis Output Format

**CHOSEN**: Produce a markdown table with columns: Table | Dossier Section | Migration File | Status | Delta Required

| Format Option | Pros | Cons | Winner |
|---------------|------|------|--------|
| Markdown table | Easy to read, version-controllable | Manual updates | ✅ |
| JSON inventory | Machine-readable, scriptable | Less human-friendly | ❌ |
| Spreadsheet | Filterable, sortable | Not in repo | ❌ |

**Rationale**: Markdown table integrates into this document and is immediately actionable for subsequent issues.

#### Decision 2: Migration Strategy for Mismatches

**CHOSEN**: Create **new corrective migrations** (ALTER TABLE) rather than editing past migrations

| Strategy | Pros | Cons | Winner |
|----------|------|------|--------|
| Edit past migrations | Clean history | Breaks deployed DBs, violates Alembic best practice | ❌ |
| New ALTER migrations | Safe for deployed DBs, audit trail | More migration files | ✅ |
| Drop + recreate | Clean schema | Data loss risk | ❌ |

**Rationale**: Production databases may already have data. New migrations add columns/indexes without data loss.

---

**Inputs Required**:

- [x] Dossier Sections 6.2-6.17: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md#6-storage-schema-design)
- [x] Existing migrations: [k0/db/alembic/versions/](../../k0/db/alembic/versions/)
- [x] Code Discovery from Part B of this document

**Deliverables**:

- [ ] Complete gap analysis table (see template below)
- [ ] Migration action plan (NEW vs ALTER vs VERIFY)
- [ ] Dependency ordering for FK relationships

**Gap Analysis Table Template**:

| Table | Dossier § | Migration File | Status | Delta Required |
|-------|-----------|----------------|--------|----------------|
| st_epi | 6.3 | — | 🔴 MISSING | NEW MIGRATION |
| st_sem | 6.4 | — | 🔴 MISSING | NEW MIGRATION |
| st_procedural | 6.5 | — | 🔴 MISSING | NEW MIGRATION |
| st_social | 6.6 | — | 🔴 MISSING | NEW MIGRATION |
| st_prospective | 6.7 | — | 🔴 MISSING | NEW MIGRATION |
| st_kg_dom | 6.8 | — | 🔴 MISSING | NEW MIGRATION |
| st_kg_edges | 6.9 | — | 🔴 MISSING | NEW MIGRATION (after st_kg_dom) |
| st_vec | 6.10 | 0025_st_vec.py | 🟢 EXISTS | VERIFY schema |
| st_hipp_events | 6.2 | 0022_st_hipp_events.py | 🟡 PARTIAL | ADD P03 columns |
| st_offsets | 6.14 | 0005_st_offsets.py | 🟢 EXISTS | VERIFY schema |
| st_pipeline_status | 6.14 | 0020_st_pipeline_status.py | 🟢 EXISTS | VERIFY schema |
| st_pipeline_watermarks | 6.14 | 0021_st_pipeline_watermarks.py | 🟢 EXISTS | VERIFY schema |
| st_outbox | 6.15 | 0008_st_outbox.py | 🟡 MISMATCH | ALTER next_attempt_ts → BIGINT |
| st_retention_policy | 6.16 | 0014_st_retention_policy.py | 🟢 EXISTS | VERIFY schema |
| st_learning_queue | 6.11 | — | 🔴 MISSING | NEW MIGRATION |
| st_anchors | 6.12 | — | 🔴 MISSING | NEW MIGRATION |
| st_anchor_observations | 6.13 | — | 🔴 MISSING | NEW MIGRATION |
| st_learned_weights | 6.17 | — | 🔴 MISSING | NEW MIGRATION |

**Migration Dependency Order** (based on FK relationships):

```
1. st_epi, st_sem, st_procedural, st_social, st_prospective (no FKs)
2. st_kg_dom (no FKs)
3. st_kg_edges (FKs to st_kg_dom)
4. st_learning_queue (FK to st_hipp_events - already exists)
5. st_anchors, st_anchor_observations
6. st_learned_weights
7. Corrective: st_outbox.next_attempt_ts ALTER
8. Corrective: st_hipp_events ADD P03 columns
```

**Acceptance**:

- [x] All 17+ tables from dossier §6 are mapped with status (see Part B.3, B.4, B.5)
- [x] Each MISMATCH has specific ALTER statement identified (see Part B.6)
- [x] FK dependency order documented (see Migration Dependency Order above)

**Blocked By**: M1 ✅

**Blocks**: 2.1.2, 2.1.3, 2.1.4, 2.1.5, 2.1.6, 2.1.7, 2.1.8, 2.1.9, 2.1.10, 2.1.11, 2.1.12

---

#### Issue 2.1.2 — Create `st_epi` (episodic memory) table + indexes (Section 6.3)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_epi` schema and indexes for episodic memory storage.

**Spec Reference**: [Dossier §6.3 st_epi](../pipelines/P03_consolidation_dossier_v2.md#63-st_epi-episodic-memory)

---

### Schema from Dossier §6.3

> **Brain Analog**: Episodic Memory (Tulving)
> **Role**: Consolidated episode clusters with temporal anchoring
> **Written by**: P03 R7 (after R2 clustering)

**Column Definitions** (33 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `episode_id` | TEXT | PRIMARY KEY | ULID for episode |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Immutability versioning |
| `supersedes_id` | TEXT | — | Previous version ID (for EVOLVE) |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version is canonical |
| `episode_summary` | TEXT | — | AI-generated summary |
| `episode_type` | TEXT | — | ROUTINE, MILESTONE, NOVEL, etc. |
| `start_time_utc` | INTEGER | NOT NULL | Earliest event in episode (Unix ms) |
| `end_time_utc` | INTEGER | NOT NULL | Latest event in episode (Unix ms) |
| `duration_minutes` | INTEGER | — | Computed duration |
| `temporal_bucket` | TEXT | — | MORNING, AFTERNOON, EVENING, NIGHT |
| `day_of_week` | TEXT | — | MONDAY, TUESDAY, etc. |
| `is_recurring` | BOOLEAN | — | Part of recurring pattern |
| `recurrence_pattern` | TEXT | — | e.g., "WEEKLY:TUESDAY" |
| `source_events_json` | TEXT | NOT NULL | JSON array of source event_ids |
| `source_event_count` | INTEGER | NOT NULL | Count of source events |
| `primary_location` | TEXT | — | Primary location string |
| `location_type` | TEXT | — | HOME, WORK, PUBLIC, etc. |
| `participants_json` | TEXT | — | JSON array of participant IDs |
| `participant_count` | INTEGER | — | Count of participants |
| `embedding_id` | TEXT | — | Reference to st_vec (aggregated) |
| `cluster_id` | TEXT | — | From P03 R2 clustering |
| `cluster_confidence` | REAL | — | Cluster assignment confidence |
| `consolidation_cycle_id` | TEXT | — | P03 cycle that created this |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence in episode |
| `last_observed_at` | INTEGER | — | Last time this pattern was seen |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' CHECK(...) | ACTIVE, ARCHIVED, TOMBSTONE |
| `created_at` | INTEGER | NOT NULL | Creation timestamp (Unix ms) |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp (Unix ms) |
| `valid_from` | INTEGER | NOT NULL | Bitemporal: when became true |
| `valid_to` | INTEGER | — | Bitemporal: when stopped being true |

**Indexes** (4 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_epi_tenant_time` | `(tenant_id, start_time_utc DESC)` | — | Tenant timeline queries |
| `idx_epi_space_time` | `(space_id, start_time_utc DESC)` | — | Space timeline queries |
| `idx_epi_cluster` | `(cluster_id)` | `WHERE cluster_id IS NOT NULL` | Cluster lookups |
| `idx_epi_canonical` | `(is_canonical, archival_status)` | — | Active canonical filter |

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_epi is MISSING
- [x] Dossier §6.3 schema (above)
- [x] Migration naming convention: `NNNN_st_epi.py`

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0027_st_epi.py`
- [x] Table creation with all 33 columns
- [x] CHECK constraint on `archival_status`
- [x] All 4 indexes with exact names from dossier
- [x] Tests → `tests/k0/pipelines/p03/test_p03_storage_migrations.py::TestMigration0027StEpi` (6 tests passing)

**Implementation Notes**:

```python
# k0/db/alembic/versions/0027_st_epi.py
"""Create st_epi episodic memory table."""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"  # After st_feedback_signals
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "st_epi",
        # Identity
        sa.Column("episode_id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("space_id", sa.Text(), nullable=False),
        # Versioning
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", sa.Text()),
        sa.Column("is_canonical", sa.Boolean(), server_default="TRUE"),
        # Content
        sa.Column("episode_summary", sa.Text()),
        sa.Column("episode_type", sa.Text()),
        # Temporal
        sa.Column("start_time_utc", sa.BigInteger(), nullable=False),
        sa.Column("end_time_utc", sa.BigInteger(), nullable=False),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("temporal_bucket", sa.Text()),
        sa.Column("day_of_week", sa.Text()),
        sa.Column("is_recurring", sa.Boolean()),
        sa.Column("recurrence_pattern", sa.Text()),
        # Source events
        sa.Column("source_events_json", sa.Text(), nullable=False),
        sa.Column("source_event_count", sa.Integer(), nullable=False),
        # Location
        sa.Column("primary_location", sa.Text()),
        sa.Column("location_type", sa.Text()),
        # Participants
        sa.Column("participants_json", sa.Text()),
        sa.Column("participant_count", sa.Integer()),
        # Embeddings
        sa.Column("embedding_id", sa.Text()),
        # Clustering
        sa.Column("cluster_id", sa.Text()),
        sa.Column("cluster_confidence", sa.Float()),
        sa.Column("consolidation_cycle_id", sa.Text()),
        # Truth tracking
        sa.Column("observation_count", sa.Integer(), server_default="1"),
        sa.Column("confidence_score", sa.Float(), server_default="0.5"),
        sa.Column("last_observed_at", sa.BigInteger()),
        sa.Column("decay_factor", sa.Float(), server_default="1.0"),
        # Lifecycle
        sa.Column("archival_status", sa.Text(), server_default="'ACTIVE'"),
        # Timestamps
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.BigInteger(), nullable=False),
        sa.Column("valid_to", sa.BigInteger()),
        # CHECK constraint
        sa.CheckConstraint(
            "archival_status IN ('ACTIVE', 'ARCHIVED', 'TOMBSTONE')",
            name="ck_epi_archival_status"
        ),
    )

    # Indexes
    op.create_index("idx_epi_tenant_time", "st_epi", ["tenant_id", sa.text("start_time_utc DESC")])
    op.create_index("idx_epi_space_time", "st_epi", ["space_id", sa.text("start_time_utc DESC")])
    op.create_index("idx_epi_cluster", "st_epi", ["cluster_id"], postgresql_where=sa.text("cluster_id IS NOT NULL"))
    op.create_index("idx_epi_canonical", "st_epi", ["is_canonical", "archival_status"])

def downgrade():
    op.drop_table("st_epi")
```

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] `st_epi` columns match Section 6.3 exactly (33 columns)
- [ ] All 4 index names match dossier
- [ ] CHECK constraint rejects invalid `archival_status` values
- [ ] Tests verify table creation and constraint enforcement

**Blocked By**: 2.1.1

---

#### Issue 2.1.3 — Create `st_sem` (semantic patterns) table + indexes (Section 6.4)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_sem` schema for semantic pattern storage.

**Spec Reference**: [Dossier §6.4 st_sem](../pipelines/P03_consolidation_dossier_v2.md#64-st_sem-semantic-patterns)

---

### Schema from Dossier §6.4

> **Brain Analog**: Semantic Memory (Neocortex)
> **Role**: Extracted patterns, preferences, themes from episodes
> **Written by**: P03 R7 (after R2 pattern extraction)

**Column Definitions** (26 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `pattern_id` | TEXT | PRIMARY KEY | ULID for pattern |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `actor_id` | TEXT | — | Whose pattern (NULL = shared family) |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Versioning |
| `supersedes_id` | TEXT | — | Previous version ID |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version canonical |
| `pattern_type` | TEXT | NOT NULL CHECK(...) | ROUTINE, PREFERENCE, THEME, RELATIONSHIP, GOAL, VALUE |
| `pattern_subtype` | TEXT | — | More specific classification |
| `pattern_name` | TEXT | NOT NULL | Human-readable name |
| `pattern_description` | TEXT | — | Detailed description |
| `pattern_attributes_json` | TEXT | — | Structured attributes (JSON) |
| `temporal_regularity` | REAL | — | [0-1] How regular is timing |
| `temporal_pattern_json` | TEXT | — | Cron-like pattern |
| `source_episodes_json` | TEXT | NOT NULL | JSON array of episode_ids |
| `source_episode_count` | INTEGER | NOT NULL | Count of source episodes |
| `embedding_id` | TEXT | — | Pattern embedding (aggregated) |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence in pattern |
| `last_observed_at` | INTEGER | — | Last observation timestamp |
| `first_observed_at` | INTEGER | — | First observation timestamp |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' CHECK(...) | ACTIVE, ARCHIVED, TOMBSTONE |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |
| `valid_from` | INTEGER | NOT NULL | Bitemporal start |
| `valid_to` | INTEGER | — | Bitemporal end |

**Indexes** (4 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_sem_tenant_type` | `(tenant_id, pattern_type)` | — | Tenant + type queries |
| `idx_sem_actor_type` | `(actor_id, pattern_type)` | `WHERE actor_id IS NOT NULL` | Actor patterns |
| `idx_sem_canonical` | `(is_canonical, archival_status)` | — | Active canonical filter |
| `idx_sem_confidence` | `(confidence_score DESC)` | `WHERE is_canonical = TRUE` | High-confidence lookup |

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_sem is MISSING
- [x] Dossier §6.4 schema (above)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0028_st_sem.py`
- [x] Table creation with all 26 columns
- [x] CHECK constraint on `pattern_type`: `IN ('ROUTINE','PREFERENCE','THEME','RELATIONSHIP','GOAL','VALUE')`
- [x] CHECK constraint on `archival_status`: `IN ('ACTIVE','ARCHIVED','TOMBSTONE')`
- [x] All 4 indexes with partial WHERE clauses
- [x] Tests → `TestMigration0028StSem` (5 tests passing)

**Implementation Notes**:

```python
# Key constraint
sa.CheckConstraint(
    "pattern_type IN ('ROUTINE', 'PREFERENCE', 'THEME', 'RELATIONSHIP', 'GOAL', 'VALUE')",
    name="ck_sem_pattern_type"
)

# Partial index example
op.create_index(
    "idx_sem_actor_type", "st_sem",
    ["actor_id", "pattern_type"],
    postgresql_where=sa.text("actor_id IS NOT NULL")
)
```

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] CHECK constraint rejects invalid `pattern_type` values
- [ ] All 4 indexes created with correct partial WHERE predicates
- [ ] Column names match dossier §6.4 exactly

**Blocked By**: 2.1.1

---

#### Issue 2.1.4 — Create `st_procedural` (habits & routines) table (Section 6.5)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_procedural` schema for habit/routine storage.

**Spec Reference**: [Dossier §6.5 st_procedural](../pipelines/P03_consolidation_dossier_v2.md#65-st_procedural-habits--routines)

---

### Schema from Dossier §6.5

> **Brain Analog**: Basal Ganglia (Procedural Memory)
> **Role**: Recurring behavioral patterns, habits, skills
> **Written by**: P03 R7

**Column Definitions** (27 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `routine_id` | TEXT | PRIMARY KEY | ULID for routine |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `actor_id` | TEXT | NOT NULL | Who performs this routine |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Versioning |
| `supersedes_id` | TEXT | — | Previous version ID |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version canonical |
| `routine_name` | TEXT | NOT NULL | Routine name |
| `routine_category` | TEXT | — | MORNING, EXERCISE, MEAL, WORK, etc. |
| `temporal_anchor` | TEXT | — | Time of day: "07:30" |
| `day_pattern` | TEXT | — | "WEEKDAYS", "WEEKENDS", "DAILY", etc. |
| `frequency` | TEXT | — | "DAILY", "WEEKLY", "MONTHLY" |
| `regularity_score` | REAL | — | [0-1] How consistent |
| `action_sequence_json` | TEXT | — | Ordered list of actions |
| `typical_duration_minutes` | INTEGER | — | Typical duration |
| `source_episodes_json` | TEXT | NOT NULL | JSON array of episode_ids |
| `source_episode_count` | INTEGER | NOT NULL | Count of source episodes |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence |
| `last_observed_at` | INTEGER | — | Last observation timestamp |
| `streak_count` | INTEGER | DEFAULT 0 | Consecutive occurrences |
| `streak_broken_at` | INTEGER | — | When streak was broken |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' | Lifecycle status |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |
| `valid_from` | INTEGER | NOT NULL | Bitemporal start |
| `valid_to` | INTEGER | — | Bitemporal end |

**Indexes**: None specified in dossier (do NOT invent indexes)

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_procedural is MISSING
- [x] Dossier §6.5 schema (above)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0029_st_procedural.py`
- [x] Table creation with all 27 columns
- [x] 3 indexes (idx_procedural_actor, idx_procedural_category, idx_procedural_regularity)
- [x] Tests → `TestMigration0029StProcedural` (4 tests passing)

**Implementation Notes**:

```python
# Note: actor_id is NOT NULL for procedural (unlike st_sem)
sa.Column("actor_id", sa.Text(), nullable=False),  # Who performs this routine
```

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] `st_procedural` columns match Section 6.5 exactly (27 columns)
- [ ] `actor_id` is NOT NULL (unlike st_sem where it's nullable)
- [ ] No extraneous indexes created

**Blocked By**: 2.1.1

---

#### Issue 2.1.5 — Create `st_social` (relationships) table + uniqueness constraint (Section 6.6)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_social` schema for relationship tracking.

**Spec Reference**: [Dossier §6.6 st_social](../pipelines/P03_consolidation_dossier_v2.md#66-st_social-relationships)

---

### Schema from Dossier §6.6

> **Brain Analog**: Social Brain Network
> **Role**: Relationship tracking, interaction history, social graph
> **Written by**: P03 R7

**Column Definitions** (27 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `relationship_id` | TEXT | PRIMARY KEY | ULID for relationship |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `actor_a_id` | TEXT | NOT NULL | First person in relationship |
| `actor_b_id` | TEXT | NOT NULL | Second person |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Versioning |
| `supersedes_id` | TEXT | — | Previous version ID |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version canonical |
| `relationship_type` | TEXT | NOT NULL | FAMILY, FRIEND, COLLEAGUE, etc. |
| `relationship_subtype` | TEXT | — | SPOUSE, SIBLING, PARENT, etc. |
| `relationship_label` | TEXT | — | Custom label |
| `interaction_count` | INTEGER | DEFAULT 0 | Number of interactions |
| `avg_sentiment` | REAL | — | Average sentiment |
| `relationship_strength` | REAL | DEFAULT 0.5 | [0-1] Overall strength |
| `intimacy_level` | TEXT | — | ACQUAINTANCE, CASUAL, CLOSE, INTIMATE |
| `first_interaction_at` | INTEGER | — | First interaction timestamp |
| `last_interaction_at` | INTEGER | — | Last interaction timestamp |
| `interaction_frequency` | TEXT | — | DAILY, WEEKLY, MONTHLY, RARE |
| `source_episodes_json` | TEXT | — | JSON array of episode_ids |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' | Lifecycle status |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |
| `valid_from` | INTEGER | NOT NULL | Bitemporal start |
| `valid_to` | INTEGER | — | Bitemporal end |

**Constraints**:

| Constraint | Type | Definition |
|------------|------|------------|
| `uq_social_canonical` | UNIQUE | `(tenant_id, actor_a_id, actor_b_id, is_canonical)` |

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_social is MISSING
- [x] Dossier §6.6 schema (above)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0030_st_social.py`
- [x] Table creation with all 27 columns
- [x] UNIQUE constraint: `(tenant_id, actor_a_id, actor_b_id, is_canonical)`
- [x] Tests → `TestMigration0030StSocial` (4 tests passing)

**Implementation Notes**:

```python
# Key unique constraint prevents duplicate canonical relationships
sa.UniqueConstraint(
    "tenant_id", "actor_a_id", "actor_b_id", "is_canonical",
    name="uq_social_canonical"
)
```

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] UNIQUE constraint prevents duplicate canonical relationship rows for a tenant
- [ ] Columns match dossier §6.6 exactly (27 columns)

**Blocked By**: 2.1.1

---

#### Issue 2.1.6 — Create `st_prospective` (intentions & goals) table + CHECK constraints (Section 6.7)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_prospective` schema for future-oriented patterns.

**Spec Reference**: [Dossier §6.7 st_prospective](../pipelines/P03_consolidation_dossier_v2.md#67-st_prospective-intentions--goals)

---

### Schema from Dossier §6.7

> **Brain Analog**: Prefrontal Cortex (Future Thinking)
> **Role**: Future-oriented patterns, goals, intentions, reminders
> **Written by**: P03 R7 (from R5 forward simulation)

**Column Definitions** (23 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `intention_id` | TEXT | PRIMARY KEY | ULID for intention |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `actor_id` | TEXT | NOT NULL | Who has this intention |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Versioning |
| `supersedes_id` | TEXT | — | Previous version ID |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version canonical |
| `intention_type` | TEXT | NOT NULL CHECK(...) | GOAL, PLAN, REMINDER, COMMITMENT, WISH |
| `intention_description` | TEXT | NOT NULL | Description of intention |
| `target_date` | INTEGER | — | When to complete (Unix ms) |
| `target_context` | TEXT | — | Triggering context |
| `status` | TEXT | DEFAULT 'ACTIVE' CHECK(...) | ACTIVE, COMPLETED, ABANDONED, DEFERRED |
| `inferred_from_json` | TEXT | — | Source patterns/episodes |
| `inference_confidence` | REAL | — | Confidence of inference |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' | Lifecycle status |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |
| `valid_from` | INTEGER | NOT NULL | Bitemporal start |
| `valid_to` | INTEGER | — | Bitemporal end |

**CHECK Constraints**:

| Constraint | Column | Valid Values |
|------------|--------|--------------|
| `ck_prosp_intention_type` | `intention_type` | `'GOAL', 'PLAN', 'REMINDER', 'COMMITMENT', 'WISH'` |
| `ck_prosp_status` | `status` | `'ACTIVE', 'COMPLETED', 'ABANDONED', 'DEFERRED'` |

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_prospective is MISSING
- [x] Dossier §6.7 schema (above)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0031_st_prospective.py`
- [x] Table creation with all 23 columns
- [x] CHECK constraint on `intention_type`
- [x] CHECK constraint on `status`
- [x] Tests → `TestMigration0031StProspective` (4 tests passing)

**Implementation Notes**:

```python
sa.CheckConstraint(
    "intention_type IN ('GOAL', 'PLAN', 'REMINDER', 'COMMITMENT', 'WISH')",
    name="ck_prosp_intention_type"
),
sa.CheckConstraint(
    "status IN ('ACTIVE', 'COMPLETED', 'ABANDONED', 'DEFERRED')",
    name="ck_prosp_status"
)
```

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] CHECK constraints reject invalid `intention_type` and `status` values
- [ ] Columns match dossier §6.7 exactly (23 columns)

**Blocked By**: 2.1.1

---

#### Issue 2.1.7 — Create `st_kg_dom` (KG entities) table + indexes (Section 6.8)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_kg_dom` schema for knowledge graph entities.

**Spec Reference**: [Dossier §6.8 st_kg_dom](../pipelines/P03_consolidation_dossier_v2.md#68-st_kg_dom-kg-entities)

---

### Schema from Dossier §6.8

> **Brain Analog**: Semantic Memory (Concept Nodes)
> **Role**: Canonical entities with attributes (people, places, things)
> **Written by**: P03 R7 (from R4 entity extraction)

**Column Definitions** (23 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `entity_id` | TEXT | PRIMARY KEY | Canonical entity ID |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Versioning |
| `supersedes_id` | TEXT | — | Previous version ID |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version canonical |
| `entity_type` | TEXT | NOT NULL | PERSON, PLACE, ORGANIZATION, THING, EVENT |
| `entity_subtype` | TEXT | — | More specific type |
| `canonical_name` | TEXT | NOT NULL | Primary display name |
| `aliases_json` | TEXT | — | Alternative names/spellings |
| `attributes_json` | TEXT | — | Structured attributes |
| `embedding_id` | TEXT | — | Entity embedding |
| `source_episodes_json` | TEXT | — | Source episodes |
| `first_mentioned_event_id` | TEXT | — | First mention event |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence |
| `last_observed_at` | INTEGER | — | Last observation timestamp |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' | Lifecycle status |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |
| `valid_from` | INTEGER | NOT NULL | Bitemporal start |
| `valid_to` | INTEGER | — | Bitemporal end |

**Indexes** (3 indexes):

| Index Name | Columns | Purpose |
|------------|---------|---------|
| `idx_kg_dom_tenant_type` | `(tenant_id, entity_type)` | Tenant + type queries |
| `idx_kg_dom_name` | `(canonical_name)` | Name lookups |
| `idx_kg_dom_canonical` | `(is_canonical, archival_status)` | Active canonical filter |

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_kg_dom is MISSING
- [x] Dossier §6.8 schema (above)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0032_st_kg_dom.py`
- [x] Table creation with all 23 columns
- [x] All 3 indexes with exact names from dossier
- [x] Tests → `TestMigration0032StKgDom` (4 tests passing)

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] Index names match dossier §6.8 exactly
- [ ] Columns match dossier §6.8 exactly (23 columns)

**Blocked By**: 2.1.1

---

#### Issue 2.1.8 — Create `st_kg_edges` (KG relationships) table + FKs + indexes (Section 6.9)

**Status**: ✅ COMPLETED (2026-01-01)

**Goal**: Implement the dossier's canonical `st_kg_edges` schema with FKs to `st_kg_dom`.

**Spec Reference**: [Dossier §6.9 st_kg_edges](../pipelines/P03_consolidation_dossier_v2.md#69-st_kg_edges-kg-relationships)

---

### Schema from Dossier §6.9

> **Brain Analog**: Associative Connections
> **Role**: Typed relationships between entities with temporal validity
> **Written by**: P03 R7 (from R4 relationship discovery)

**Column Definitions** (22 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `edge_id` | TEXT | PRIMARY KEY | ULID for edge |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `source_entity_id` | TEXT | NOT NULL FK | From entity (→ st_kg_dom) |
| `target_entity_id` | TEXT | NOT NULL FK | To entity (→ st_kg_dom) |
| `version` | INTEGER | NOT NULL DEFAULT 1 | Versioning |
| `supersedes_id` | TEXT | — | Previous version ID |
| `is_canonical` | BOOLEAN | DEFAULT TRUE | Only one version canonical |
| `relation_type` | TEXT | NOT NULL | WORKS_AT, LIVES_IN, KNOWS, LIKES, etc. |
| `relation_subtype` | TEXT | — | More specific relation |
| `properties_json` | TEXT | — | Edge attributes |
| `edge_weight` | REAL | DEFAULT 1.0 | Relationship strength |
| `confidence_score` | REAL | DEFAULT 0.5 | [0-1] Confidence |
| `source_episodes_json` | TEXT | — | Source episodes |
| `co_occurrence_count` | INTEGER | DEFAULT 1 | Hebbian: how often seen together |
| `observation_count` | INTEGER | DEFAULT 1 | How many times observed |
| `last_observed_at` | INTEGER | — | Last observation timestamp |
| `decay_factor` | REAL | DEFAULT 1.0 | [0-1] Temporal decay |
| `archival_status` | TEXT | DEFAULT 'ACTIVE' | Lifecycle status |
| `valid_from` | INTEGER | NOT NULL | Bitemporal start |
| `valid_to` | INTEGER | — | Bitemporal end |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |

**Foreign Keys**:

| FK Name | Column | References |
|---------|--------|------------|
| `fk_edges_source` | `source_entity_id` | `st_kg_dom(entity_id)` |
| `fk_edges_target` | `target_entity_id` | `st_kg_dom(entity_id)` |

**Indexes** (3 indexes):

| Index Name | Columns | Purpose |
|------------|---------|---------|
| `idx_kg_edges_source` | `(source_entity_id, relation_type)` | Source + type queries |
| `idx_kg_edges_target` | `(target_entity_id, relation_type)` | Target + type queries |
| `idx_kg_edges_canonical` | `(is_canonical, archival_status)` | Active canonical filter |

---

**Inputs Required**:

- [x] Gap analysis from 2.1.1 confirms st_kg_edges is MISSING
- [x] Dossier §6.9 schema (above)
- [x] **st_kg_dom must exist first** (Issue 2.1.7)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0033_st_kg_edges.py`
- [x] Table creation with all 22 columns
- [x] Foreign keys to `st_kg_dom(entity_id)`
- [x] All 3 indexes
- [x] Tests → `TestMigration0033StKgEdges` (4 tests passing)

**Implementation Notes**:

```python
# Foreign keys
sa.Column("source_entity_id", sa.Text(), sa.ForeignKey("st_kg_dom.entity_id"), nullable=False),
sa.Column("target_entity_id", sa.Text(), sa.ForeignKey("st_kg_dom.entity_id"), nullable=False),
```

**Acceptance**:

- [ ] Migration applies cleanly on PostgreSQL
- [ ] FK constraints prevent edges referencing non-existent entities
- [ ] Index names match dossier §6.9 exactly
- [ ] Columns match dossier §6.9 exactly (22 columns)

**Blocked By**: 2.1.7 (st_kg_dom must exist first)

---

#### Issue 2.1.9 — Verify `st_vec` (embeddings) matches dossier + migrate deltas if needed (Section 6.10)

**Status**: ✅ VERIFIED (2026-01-01) — No migration needed

**Goal**: Ensure existing `st_vec` table aligns with dossier Section 6.10 schema.

**Spec Reference**: [Dossier §6.10 st_vec](../pipelines/P03_consolidation_dossier_v2.md#610-st_vec-embeddings)

---

### Schema from Dossier §6.10

> **Source**: P02 inline embedding (M23), indexed by P08
> **Role**: UltraBERT 768-dim embeddings for semantic similarity

**Column Definitions** (13 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `embedding_id` | TEXT | PRIMARY KEY | ULID for embedding |
| `event_id` | TEXT | NOT NULL FK | Source event (st_hipp_events) |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `vector` | BYTEA | NOT NULL | 768 floats x 4 bytes = 3072 bytes |
| `vector_dim` | INTEGER | NOT NULL DEFAULT 768 | Dimension |
| `model_id` | TEXT | NOT NULL DEFAULT 'ultrabert_v2.1.0' | Embedding model |
| `status` | TEXT | NOT NULL DEFAULT 'READY' CHECK(...) | READY, INDEXED, FAILED |
| `faiss_id` | INTEGER | — | FAISS index ID (set by P08) |
| `indexed_at` | INTEGER | — | When indexed by P08 |
| `cognitive_trace_id` | TEXT | — | Tracing |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `updated_at` | INTEGER | NOT NULL | Last update timestamp |

**Foreign Key**:

| FK | Column | References |
|----|--------|------------|
| — | `event_id` | `st_hipp_events(event_id) ON DELETE CASCADE` |

**Indexes** (4 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_vec_event_id` | `(event_id)` | — | Event lookup |
| `idx_vec_tenant_space` | `(tenant_id, space_id)` | — | Tenant/space filter |
| `idx_vec_status_created` | `(status, created_at)` | `WHERE status = 'READY'` | P08 indexing queue |
| `idx_vec_faiss_id` | `(faiss_id)` | — | FAISS reverse lookup |

---

### Existing Migration Analysis (from Part B)

**File**: `k0/db/alembic/versions/0025_st_vec.py`

| Aspect | Dossier | Migration | Match? |
|--------|---------|-----------|--------|
| `embedding_id` PK | TEXT | TEXT | ✅ |
| `event_id` FK | TEXT NOT NULL | TEXT NOT NULL | ✅ |
| `vector` type | BYTEA | LargeBinary | ✅ |
| `status` CHECK | READY/INDEXED/FAILED | TBD | VERIFY |
| `idx_vec_status_created` partial | WHERE status='READY' | TBD | VERIFY |

---

**Inputs Required**:

- [x] Dossier §6.10 schema (above)
- [x] Existing migration: `k0/db/alembic/versions/0025_st_vec.py`

**Deliverables**:

- [x] Comparison checklist: dossier columns vs migration columns — ALL MATCH
- [x] If mismatch: new corrective migration (do NOT edit 0025) — NOT NEEDED
- [x] If match: mark as VERIFIED — ✅ VERIFIED

**Verification Notes**:

Existing migration `0025_st_vec.py` is fully compliant with dossier §6.10:

- ✅ All 13 columns present
- ✅ CHECK constraint on `status` (READY, INDEXED, FAILED)
- ✅ FK to `st_hipp_events` with `ON DELETE CASCADE`
- ✅ All 4 required indexes plus 1 extra (`idx_vec_model_id`)
- ✅ Partial WHERE on `idx_vec_status_created`

**Acceptance**:

- [x] `st_vec` contains all 13 columns from dossier §6.10
- [x] CHECK constraint on `status` enforced
- [x] FK to `st_hipp_events` with CASCADE delete
- [x] All 4 indexes present with correct partial WHERE

**Blocked By**: 2.1.1

---

#### Issue 2.1.10 — Add P03 consolidation columns + pending index to `st_hipp_events` (Section 6.2 + 6.2.2)

**Status**: ✅ COMPLETED

**Goal**: Make staging table support P03 consolidation lifecycle with pending-scan index.

**Spec Reference**: [Dossier §6.2, §6.2.2](../pipelines/P03_consolidation_dossier_v2.md#62-st_hipp_events-staging--hippocampus)

---

### P03 Consolidation Columns from Dossier §6.2.2

> These columns enable P03 to track which events have been processed

**New Columns to Add** (6 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `consolidation_status` | TEXT | CHECK(...) NULL allowed | PENDING, IN_PROGRESS, CONSOLIDATED, DUPLICATE, PRUNED, PENDING_REVIEW |
| `consolidation_cycle_id` | TEXT | — | Which P03 cycle processed this |
| `consolidated_at` | INTEGER | — | When consolidated (Unix ms) |
| `reconciliation_decision` | TEXT | — | CREATE, REINFORCE, CONTRADICT, SKIP, DECAY |
| `truth_match_id` | TEXT | — | Matched truth record ID |
| `truth_match_similarity` | REAL | — | Similarity score [0-1] |

**New Index**:

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_hipp_events_consolidation` | `(consolidation_status, event_time_utc)` | `WHERE consolidation_status IS NULL OR consolidation_status = 'PENDING'` | R0 pending scan |

---

### Existing Migration Analysis (from Part B)

**File**: `k0/db/alembic/versions/0022_st_hipp_events.py`

The migration has ~80 columns but P03 consolidation columns are **NOT present**.

---

**Inputs Required**:

- [x] Dossier §6.2.2 schema (above)
- [x] Existing migration: `k0/db/alembic/versions/0022_st_hipp_events.py`

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0034_st_hipp_events_p03_columns.py`
- [x] ALTER TABLE to add 6 columns
- [x] Add CHECK constraint on `consolidation_status`
- [x] Add partial index for pending scan

**Tests**: `tests/k0/pipelines/p03/test_p03_storage_migrations.py::TestMigration0034StHippEventsP03Columns` (5 tests)

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] New events with `consolidation_status = NULL` are selectable efficiently via index
- [x] Invalid consolidation statuses rejected by CHECK constraint
- [x] R0 pending scan query uses the partial index

**Blocked By**: 2.1.1 ✅

---

#### Issue 2.1.11 — Reconcile `st_outbox.next_attempt_ts` type with dossier (Section 6.15)

**Status**: ✅ COMPLETED

**Goal**: Align outbox schema with dossier's canonical types for timestamp sorting.

**Spec Reference**: [Dossier §6.15 st_outbox](../pipelines/P03_consolidation_dossier_v2.md#615-st_outbox-durable-writes)

---

### Schema from Dossier §6.15

> **Role**: Transactional outbox pattern for reliable writes

**Expected Columns**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-increment ID |
| `wal_pos` | INTEGER | NOT NULL | WAL position |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `driver` | TEXT | NOT NULL | Target driver (e.g., 'p08_embedding') |
| `op_kind` | TEXT | NOT NULL | Operation type |
| `payload` | BYTEA | NOT NULL | Serialized operation |
| `fingerprint` | TEXT | NOT NULL | Idempotency key |
| `requeue_seq` | INTEGER | NOT NULL DEFAULT 0 | Requeue sequence |
| `retries` | INTEGER | NOT NULL DEFAULT 0 | Retry count |
| `last_error` | TEXT | — | Last error message |
| `next_attempt_ts` | BIGINT | — | **Unix timestamp (ms)** |
| `backoff_exp` | INTEGER | DEFAULT 1 | Backoff exponent |
| `status` | TEXT | DEFAULT 'PENDING' CHECK(...) | PENDING, PROCESSING, FAILED, DEAD |

**Expected Index**:

| Index Name | Columns | Purpose |
|------------|---------|---------|
| `uq_outbox_idem` | `(tenant_id, space_id, driver, fingerprint, requeue_seq)` | Idempotency |

---

### Existing Migration Analysis (from Part B)

**File**: `k0/db/alembic/versions/0008_st_outbox.py`

| Aspect | Dossier | Migration | Match? |
|--------|---------|-----------|--------|
| `next_attempt_ts` | BIGINT | TEXT | 🔴 MISMATCH → FIXED |

**Critical Issue**: `next_attempt_ts` was TEXT in migration but BIGINT in dossier. **Corrected by 0035 migration.**

---

**Inputs Required**:

- [x] Dossier §6.15 schema (above)
- [x] Existing migration: `k0/db/alembic/versions/0008_st_outbox.py`

**Deliverables**:

- [x] New corrective migration → `k0/db/alembic/versions/0035_st_outbox_fix_next_attempt_ts.py`
- [x] ALTER COLUMN `next_attempt_ts` from TEXT to BIGINT
- [x] Data migration: convert existing TEXT values to BIGINT (Unix ms)

**Tests**: `tests/k0/pipelines/p03/test_p03_storage_migrations.py::TestMigration0035StOutboxFixNextAttemptTs` (6 tests)

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] `next_attempt_ts` supports numeric range comparisons without casts
- [x] Existing data preserved (converted)
- [x] Idempotency uniqueness enforced exactly as dossier specifies

**Blocked By**: 2.1.1 ✅

---

#### Issue 2.1.12 — Verify offsets/status/watermarks + retention policy tables match dossier (Sections 6.14-6.16)

**Status**: ✅ VERIFIED

**Goal**: Confirm resume-capability tables match dossier DDL for P03 runner/checkpointing.

**Spec Reference**: [Dossier §6.14-6.16](../pipelines/P03_consolidation_dossier_v2.md#614-st_pipeline_offsets--st_pipeline_status)

---

### Tables to Verify

**1. st_offsets (Dossier §6.14)**

| Column | Type | Constraints |
|--------|------|-------------|
| `subscriber_id` | TEXT | NOT NULL, PK part |
| `topic` | TEXT | NOT NULL, PK part |
| `space_id` | TEXT | NOT NULL, PK part |
| `tenant_id` | TEXT | NOT NULL, PK part |
| `offset` | INTEGER | NOT NULL |
| `updated_ts` | TEXT | NOT NULL |

**Existing Migration**: `k0/db/alembic/versions/0005_st_offsets.py`

**2. st_pipeline_status (Dossier §6.14)**

| Column | Type | Constraints |
|--------|------|-------------|
| `pipeline_id` | TEXT | NOT NULL, PK part |
| `wal_pos` | INTEGER | NOT NULL, PK part |
| `status` | TEXT | NOT NULL CHECK(IN 'OK','ERROR','DEFERRED') |
| `duration_ms` | INTEGER | — |
| `error_kind` | TEXT | — |
| `error_msg` | TEXT | — |
| `updated_at` | INTEGER | NOT NULL |

**Existing Migration**: `k0/db/alembic/versions/0020_st_pipeline_status.py`

**3. st_pipeline_watermarks (Dossier §6.14)**

| Column | Type | Constraints |
|--------|------|-------------|
| `pipeline_id` | TEXT | NOT NULL, PK part |
| `space_id` | TEXT | NOT NULL, PK part |
| `watermark` | INTEGER | NOT NULL |
| `updated_at` | INTEGER | NOT NULL |

**Existing Migration**: `k0/db/alembic/versions/0021_st_pipeline_watermarks.py`

**4. st_retention_policy (Dossier §6.16)**

| Column | Type | Constraints |
|--------|------|-------------|
| `policy_id` | TEXT | PRIMARY KEY |
| `policy_name` | TEXT | NOT NULL UNIQUE |
| `resource_type` | TEXT | NOT NULL |
| `privacy_band` | TEXT | CHECK(IN 'GREEN','AMBER','RED') or NULL |
| `retention_days` | INTEGER | NOT NULL |
| `archive_enabled` | BOOLEAN | DEFAULT 1 |
| `archive_after_days` | INTEGER | — |
| `created_at` | TEXT | NOT NULL |
| `created_by` | TEXT | NOT NULL |
| `updated_at` | TEXT | — |
| `enabled` | BOOLEAN | DEFAULT 1 |

**Existing Migration**: `k0/db/alembic/versions/0014_st_retention_policy.py`

---

**Inputs Required**:

- [x] Dossier §6.14-6.16 schemas (above)
- [x] Existing migrations

**Deliverables**:

- [x] Verification checklist for each table
- [x] Document any deltas found: **NONE** - All 4 tables match dossier
- [x] If mismatch: new corrective migration(s): **N/A** - All compliant
- [x] If match: mark each as VERIFIED

**Verification Results**:

| Table | Migration | Status |
|-------|-----------|--------|
| st_offsets | 0005_st_offsets.py | ✅ VERIFIED (6 columns, composite PK) |
| st_pipeline_status | 0020_st_pipeline_status.py | ✅ VERIFIED (7 columns, CHECK constraint) |
| st_pipeline_watermarks | 0021_st_pipeline_watermarks.py | ✅ VERIFIED (4 columns, composite PK) |
| st_retention_policy | 0014_st_retention_policy.py | ✅ VERIFIED (11 columns, CHECK constraint) |

**Acceptance**:

- [x] P03 can read/write subscriber offsets
- [x] P03 can record per-wal outcomes
- [x] P03 can track per-space watermarks
- [x] Retention policies can be queried by resource type and privacy band

**Blocked By**: 2.1.1 ✅

---

### Epic 2.2 — Audit + explainability + compliance

> **Status**: ✅ COMPLETED
> **Source**: [P03_implementation_plan_skeleton.md](../pipelines/P03_implementation_plan_skeleton.md) (Lines 944-1075)
> **Governance Baseline**: TBD
> **Issues**: 2.2.1–2.2.5 (5 issues)

**Summary**:

- Epic 2.2 covers **audit/explainability/compliance storage surfaces and hooks**
- Creates `st_consolidation_audit` table for decision tracking
- Implements audit write path and explainability query API
- Implements retention wiring and GDPR erasure hooks
- Epic 2.2 does **NOT** cover parameter-learning tables (those are Epic 2.3)

---

#### Issue 2.2.1 — Create `st_consolidation_audit` table + indexes (+ outcome-tracking columns) (Section 6.20)

**Status**: ✅ COMPLETED

**Goal**: Add dossier's canonical audit table for explainability, debugging, and learning analysis.

**Spec Reference**: [Dossier §6.20 st_consolidation_audit](../pipelines/P03_consolidation_dossier_v2.md#620-st_consolidation_audit-decision-audit)

---

### Schema from Dossier §6.20

> **Purpose**: Complete audit trail for consolidation decisions
> **Retention**: 90 days detailed records, then aggregate to daily summaries
> **Isolation**: RLS enforced for multi-tenant security

**Column Definitions** (15 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `audit_id` | TEXT | PRIMARY KEY | ULID for audit record |
| `memory_id` | TEXT | NOT NULL | Affected memory ID |
| `source_table` | TEXT | NOT NULL | st_epi, st_kg_dom, etc. |
| `action` | TEXT | NOT NULL | REINFORCE, DECAY, ARCHIVE, MERGE, CREATE |
| `formula_used` | TEXT | — | e.g., "hebbian_v2", "decay_unified" |
| `formula_version` | TEXT | — | Version identifier for rollback |
| `inputs_json` | JSONB | — | Input parameters to formula |
| `outputs_json` | JSONB | — | Output values from formula |
| `explanation` | TEXT | — | User-friendly explanation template |
| `decision_id` | TEXT | — | Links to decision outcome tracking |
| `space_id` | TEXT | NOT NULL | User/family space |
| `cycle_id` | TEXT | — | Consolidation cycle ID |
| `confidence` | REAL | — | Decision confidence [0-1] |
| `created_at` | BIGINT | NOT NULL | Creation timestamp (Unix ms) |

**Outcome Tracking Columns** (from §1.4.7):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `threshold_used` | REAL | — | Threshold value that triggered decision |
| `threshold_name` | TEXT | — | Name of threshold parameter |
| `outcome_evaluated` | BOOLEAN | DEFAULT FALSE | Whether outcome has been evaluated |
| `outcome_success` | BOOLEAN | — | Whether decision was successful |
| `evaluated_at` | BIGINT | — | When outcome was evaluated |

**Indexes** (5 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_audit_memory_time` | `(memory_id, created_at)` | — | Memory history |
| `idx_audit_action` | `(action, created_at)` | — | Action analysis |
| `idx_audit_formula` | `(formula_used, created_at)` | — | Formula analysis |
| `idx_audit_decision` | `(decision_id)` | — | Outcome linkage |
| `idx_consolidation_audit_outcome_eval` | `(outcome_evaluated, created_at)` | `WHERE outcome_evaluated = FALSE` | Pending evaluations |

---

**Inputs Required**:

- [x] Dossier §6.20 schema (above)
- [x] Gap analysis confirms table is MISSING

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0036_st_consolidation_audit.py`
- [x] Table creation with all columns (15 base + 5 outcome tracking = 20 total)
- [x] All 6 indexes (5 dossier + 1 canonical lookup)
- [x] RLS policy for multi-tenant isolation

**Tests**: `tests/k0/pipelines/p03/test_p03_storage_migrations.py::TestMigration0036StConsolidationAudit` (7 tests)

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] RLS prevents cross-space reads
- [x] Partial index on `outcome_evaluated = FALSE` works correctly
- [x] All 20 columns match dossier §6.20

**Blocked By**: 2.1.1 ✅

---

#### Issue 2.2.2 — Implement the P03 decision audit logger (write path) (Sections 6.20 + 14.10)

**Status**: ✅ COMPLETED

**Goal**: Record every consolidation decision to `st_consolidation_audit` in deterministic, queryable format.

**Spec Reference**: [Dossier §6.20.3](../pipelines/P03_consolidation_dossier_v2.md#6203-record-decision), [Dossier §14.10](../pipelines/P03_consolidation_dossier_v2.md#1410-explanation-templates)

**Deliverables**:

- [x] Create `k0/pipelines/p03/audit_logger.py` with:
  - Writes all audit fields from 2.2.1 schema
  - Accepts structured inputs/outputs and serializes to JSON text
  - Never logs raw PII (IDs only); applies K0 redaction via RED_BAND_FIELDS
- [x] Define stable "explanation template" convention per Section 14.10 (EXPLANATION_TEMPLATES dict)
- [x] Add trace context linkage (`cycle_id`, `space_id`, `tenant_id`)

**Tests**: `tests/k0/pipelines/p03/test_p03_audit_logger.py` (32 tests)

**Acceptance**:

- [x] At least one audit record per decision type (REINFORCE/EXTEND/CREATE/PRUNE/etc.) — parametrized test covers all 9 action types
- [x] Logger rejects/strips RED-band forbidden fields — redact_pii_fields() tested
- [x] Writes idempotent per `audit_id` (no duplicate PK violations) — test_log_decision_idempotent passes

**Blocked By**: 2.2.1

---

#### Issue 2.2.3 — Implement explainability query API for a memory decision (read path) (Sections 6.20.3 + 14.10)

**Status**: ✅ COMPLETED

**Goal**: Provide stable query surface: "why was this memory handled this way?"

**Spec Reference**: [Dossier §6.20.3](../pipelines/P03_consolidation_dossier_v2.md#6203-generate-explanations), [Dossier §14.10](../pipelines/P03_consolidation_dossier_v2.md#1410-memory-decision-explanations)

**Implementation Summary**:

- Created `k0/pipelines/p03/explainability.py` with:
  - `MemoryExplanation` frozen dataclass (user-safe fields only)
  - `AuditRepository` Protocol for database abstraction
  - `InMemoryAuditRepository` for testing
  - `ExplainabilityService` with `explain_memory()` and `get_memory_history()`
  - `get_default_explanation()` for missing records
- Created `tests/k0/pipelines/p03/test_p03_explainability.py` (32 tests)

**Deliverables**:

- [x] Create `k0/pipelines/p03/explainability.py` with:
  - Function to lookup latest audit record for `(memory_id, space_id)` ordered by `created_at DESC`
  - Returns: `memory_id`, `action`, `explanation`, `confidence`, `created_at`
  - Does NOT leak `inputs_json`/`outputs_json` to end users (ops/debug only)
- [x] Unit/integration tests for:
  - No record → default explanation
  - Record exists → template renders correctly
  - Cross-space lookup returns no data

**Acceptance**:

- [x] Explainability returns deterministic output matching stored action/confidence
- [x] Cross-space lookups cannot retrieve other space's audit records

**Blocked By**: 2.2.1, 2.2.2

---

#### Issue 2.2.4 — Retention wiring for audit records (90-day raw + aggregation plan) (Section 6.20)

**Status**: ✅ COMPLETED

**Goal**: Make audit retention explicit and enforceable (90 days raw, then aggregate).

**Spec Reference**: [Dossier §6.20 Retention Policy](../pipelines/P03_consolidation_dossier_v2.md#620-st_consolidation_audit)

**Implementation Summary**:

- Created `k0/pipelines/p03/retention.py` with:
  - `DailyAuditSummary` dataclass for aggregated records
  - `RetentionJobResult` dataclass for maintenance job results
  - `RetentionRepository` Protocol for database abstraction
  - `InMemoryRetentionRepository` for testing
  - `aggregate_records_to_daily_summaries()` function
  - `RetentionService` class with `run_maintenance()` method
  - `get_retention_policy_config()` for st_retention_policy registration
- Created `tests/k0/pipelines/p03/test_p03_retention.py` (32 tests)

**Deliverables**:

- [x] Create `k0/pipelines/p03/retention.py` with:
  - Configure `st_consolidation_audit` in `st_retention_policy`
  - Maintenance job that:
    - Deletes raw audit rows older than 90 days
    - Writes daily aggregated summaries per space before deletion (minimal: day, space_id, action counts, avg confidence)
  - Logs counts and time range without sensitive payloads

**Acceptance**:

- [x] Running job twice is safe (idempotent aggregation/deletion)
- [x] Raw audit data does not grow unbounded past retention windows

**Blocked By**: 2.1.12 (st_retention_policy alignment), 2.2.1

---

#### Issue 2.2.5 — GDPR erasure hooks: tombstone + GC semantics across P03 memory layers (Section 14.7)

**Status**: ✅ COMPLETED

**Goal**: Implement explicit, testable GDPR Article 17 erasure path through P03-owned data.

**Spec Reference**: [Dossier §14.7](../pipelines/P03_consolidation_dossier_v2.md#147-gdpr)

**Implementation Summary**:

- Created `k0/pipelines/p03/erasure.py` with:
  - `ErasureScope` enum: ACTOR_DATA, ALL_MENTIONS, FULL_PURGE
  - `ErasureRequest` dataclass for erasure operations
  - `ErasureResult` dataclass for operation results
  - `TombstoneMarker` dataclass for event tombstones
  - `ErasureRepository` Protocol for database abstraction
  - `InMemoryErasureRepository` for testing
  - `ErasureService` class with `execute_erasure()` and `validate_request()`
  - Cascading deletes across: st_kg_edges, st_kg_dom, st_epi, st_sem, st_consolidation_audit
  - Tombstone creation for st_hipp_events
  - Compliance WAL entry writing
- Created `tests/k0/pipelines/p03/test_p03_erasure.py` (32 tests)

**Deliverables**:

- [x] Create `k0/pipelines/p03/erasure.py` with:
  - Erasure handler supporting scopes: `ACTOR_DATA`, `ALL_MENTIONS`, `FULL_PURGE`
  - Cascade per dossier:
    - Mark `st_hipp_events` rows as TOMBSTONE
    - Cascade to truth tables (`st_epi`, `st_sem`, `st_kg_dom`, `st_kg_edges`, etc.)
    - Delete associated embeddings from `st_vec`, coordinate P08 index rebuild
    - Write auditable compliance entry to WAL (append-only)
  - Decision for `st_consolidation_audit`: delete for `FULL_PURGE` or retain non-identifying aggregates

**Acceptance**:

- [x] Erasure request produces deterministic counts per table
- [x] Subsequent reads cannot retrieve erased records
- [x] Compliance actions recorded in WAL/audit without sensitive payloads

**Blocked By**: 2.1.2-2.1.10 (truth tables must exist), 2.2.1

---

### Epic 2.3 — Learning + feedback persistence

> **Status**: NOT_STARTED
> **Source**: [P03_implementation_plan_skeleton.md](../pipelines/P03_implementation_plan_skeleton.md) (Lines 1078-1314)
> **Governance Baseline**: TBD
> **Issues**: 2.3.1–2.3.10 (10 issues)

**Summary**:

- Epic 2.3 covers **learning + feedback persistence storage surfaces**:
  - Gap queue (`st_learning_queue`)
  - Bayesian anchors (`st_anchors`, `st_anchor_observations`)
  - Learned parameters (`st_learned_weights`, `st_learned_weights_history`)
  - Feedback quarantine (`st_feedback_quarantine`)
  - Golden dataset validation (`st_golden_dataset_pairs`, `st_validation_results`)
- Epic 2.3 includes **schema reconciliation work** for dossier↔repo conflicts (`st_feedback_signals`, `st_dlq`)
- Do **NOT** edit past Alembic migrations — add new migrations to reconcile deltas

---

#### Issue 2.3.1 — Storage gap analysis: learning + feedback tables vs existing Alembic migrations

**Status**: NOT_STARTED

**Goal**: Produce "already exists vs missing vs mismatched" map for Epic 2.3 storage surfaces.

**Spec Reference**: [Dossier §6.11-6.13, 6.17, 6.21-6.23](../pipelines/P03_consolidation_dossier_v2.md)

---

### Gap Analysis Table (Epic 2.3 Scope)

| Table | Dossier § | Migration File | Status | Action Required |
|-------|-----------|----------------|--------|-----------------|
| st_learning_queue | 6.11 | — | 🔴 MISSING | NEW MIGRATION |
| st_anchors | 6.12 | — | 🔴 MISSING | NEW MIGRATION |
| st_anchor_observations | 6.13 | — | 🔴 MISSING | NEW MIGRATION (after st_anchors) |
| st_learned_weights | 6.17 | — | 🔴 MISSING | NEW MIGRATION |
| st_learned_weights_history | 6.23 | — | 🔴 MISSING | NEW MIGRATION (after st_learned_weights) |
| st_feedback_quarantine | 6.21 | — | 🔴 MISSING | NEW MIGRATION |
| st_golden_dataset_pairs | 6.24 | — | 🔴 MISSING | NEW MIGRATION |
| st_validation_results | 6.25 | — | 🔴 MISSING | NEW MIGRATION |
| st_feedback_signals | 6.22 | 0026_st_feedback_signals.py | 🟡 MISMATCH | ALTER (add consumed_at, consumed_by) |
| st_dlq | 13.4 | 0009_st_dlq.py | 🟡 MISMATCH | VERIFY/ALTER |

---

**Inputs Required**:

- [x] Dossier §6.11-6.13, 6.17, 6.21-6.25 schemas
- [x] Existing migrations for st_feedback_signals and st_dlq

**Deliverables**:

- [x] Complete gap analysis table (above pre-filled from Part B)
- [x] Confirm each MISSING table needs NEW migration
- [x] Document exact deltas for MISMATCH tables

**Acceptance**:

- [x] Every table/index/policy accounted for with explicit next action
- [x] Any dossier↔repo mismatch captured with specific ALTER requirements

**Blocked By**: M1 ✅

**Blocks**: 2.3.2–2.3.10

---

#### Issue 2.3.2 — Create `st_learning_queue` (gap queue) table + indexes (Section 6.11)

**Status**: ✅ COMPLETED

**Goal**: Implement dossier's canonical gap queue schema for P03→P06 learning gaps.

**Spec Reference**: [Dossier §6.11 st_learning_queue](../pipelines/P03_consolidation_dossier_v2.md#611-st_learning_queue-gap-queue)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0037_st_learning_queue.py`
- 23 columns matching dossier specification (importance_score is GENERATED STORED)
- GENERATED STORED column for `importance_score`: `entropy_score * (1.0 / (COALESCE(confidence_score, 0.0) + 0.1))`
- FK to `st_hipp_events(event_id)` for `related_event_id`
- CHECK constraints: `ck_learning_queue_gap_type` (7 values), `ck_learning_queue_status` (8 values)
- 4 indexes including partial index `idx_learning_queue_importance` with `WHERE status = 'PENDING'`
- Added 9 tests in `TestMigration0037StLearningQueue`

---

### Schema from Dossier §6.11

> **Role**: Gap records for P06 Active Learning
> **Written by**: P03 R8 (gap detection) or P06 (entropy scanner)

**Column Definitions** (24 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | ULID for gap record |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `gap_type` | TEXT | NOT NULL CHECK(...) | AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, etc. |
| `entity_id` | TEXT | — | Related entity (if applicable) |
| `related_event_id` | TEXT | FK | Source event that triggered gap |
| `related_truth_id` | TEXT | — | Affected truth record |
| `confidence_score` | REAL | — | [0-1] Current confidence |
| `entropy_score` | REAL | — | [0-1] Uncertainty level |
| `importance_score` | REAL | GENERATED STORED | entropy * (1/(confidence+0.1)) |
| `context_json` | TEXT | — | Rich context for question generation |
| `status` | TEXT | DEFAULT 'PENDING' CHECK(...) | PENDING, READY, ASKED, ANSWERED, etc. |
| `created_at` | INTEGER | NOT NULL | Creation timestamp |
| `expires_at` | INTEGER | — | Auto-expire after this time |
| `ready_at` | INTEGER | — | When context became appropriate |
| `asked_at` | INTEGER | — | When question was delivered |
| `answered_at` | INTEGER | — | When user responded |
| `attempts` | INTEGER | DEFAULT 0 | How many times asked |
| `max_attempts` | INTEGER | DEFAULT 3 | Max retry attempts |
| `last_attempt_at` | INTEGER | — | Last attempt timestamp |
| `resolution_type` | TEXT | — | USER_ANSWER, INFERRED, EXPIRED |
| `resolution_data_json` | TEXT | — | Answer or inference result |
| `consolidation_cycle_id` | TEXT | — | Which P03 cycle detected this |

**CHECK Constraints**:

| Constraint | Column | Valid Values |
|------------|--------|--------------|
| `ck_gap_type` | `gap_type` | AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE, CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR |
| `ck_gap_status` | `status` | PENDING, READY, ASKED, ANSWERED, RESOLVED, EXPIRED, REJECTED, SUPPRESSED |

**Indexes** (3 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_learning_queue_importance` | `(importance_score DESC, created_at)` | `WHERE status = 'PENDING'` | Priority queue |
| `idx_learning_queue_status` | `(status, expires_at)` | — | Status queries |
| `idx_learning_queue_tenant` | `(tenant_id, gap_type, status)` | — | Tenant filtering |

---

**Inputs Required**:

- [x] Dossier §6.11 schema (above)
- [x] Gap analysis confirms table is MISSING

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0037_st_learning_queue.py`
- [x] Table creation with all 23 columns (importance_score is GENERATED STORED)
- [x] GENERATED STORED column for `importance_score`
- [x] FK to `st_hipp_events(event_id)` for `related_event_id`
- [x] All 4 indexes (3 dossier + 1 space index) with partial WHERE predicates

**Implementation Notes**:

```python
# Generated column for importance
sa.Column(
    "importance_score", sa.Float(),
    sa.Computed("entropy_score * (1.0 / (COALESCE(confidence_score, 0.0) + 0.1))", persisted=True)
)
```

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] Generated column computes correctly
- [x] Partial indexes use correct predicates
- [x] All 23 columns match dossier §6.11

**Blocked By**: 2.3.1

---

#### Issue 2.3.3 — Create `st_anchors` (Bayesian beliefs) table + indexes (Section 6.12)

**Status**: ✅ COMPLETED

**Goal**: Implement dossier's canonical Bayesian anchor storage (Beta distributions).

**Spec Reference**: [Dossier §6.12 st_anchors](../pipelines/P03_consolidation_dossier_v2.md#612-st_anchors-bayesian-beliefs)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0038_st_anchors.py`
- 17 columns matching dossier specification
- Composite PK (entity_id, attribute, tenant_id)
- GENERATED STORED columns: `confidence = alpha / (alpha + beta)`, `uncertainty = 1.0 / (1.0 + alpha + beta)`
- CHECK constraint `ck_anchors_status` (4 values: ACTIVE, DRIFTING, STALE, ARCHIVED)
- 4 indexes including partial indexes for ACTIVE and drift detection
- Added 10 tests in `TestMigration0038StAnchors`

---

### Schema from Dossier §6.12

> **Role**: User preference modeling with Beta distributions
> **Updated by**: P03 during consolidation, P06 entropy scanner

**Column Definitions** (17 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `entity_id` | TEXT | NOT NULL, PK part | Person ID this anchor belongs to |
| `attribute` | TEXT | NOT NULL, PK part | Attribute name (e.g., 'loves_spicy_food') |
| `tenant_id` | TEXT | NOT NULL, PK part | Multi-tenant isolation |
| `space_id` | TEXT | NOT NULL | User/family space |
| `alpha` | REAL | DEFAULT 1.0 | Beta distribution: evidence FOR |
| `beta` | REAL | DEFAULT 1.0 | Beta distribution: evidence AGAINST |
| `confidence` | REAL | GENERATED STORED | alpha / (alpha + beta) |
| `uncertainty` | REAL | GENERATED STORED | 1.0 / (1.0 + alpha + beta) |
| `observation_count` | INTEGER | DEFAULT 0 | Total observations |
| `first_observed_at` | INTEGER | — | First observation timestamp |
| `last_updated_at` | INTEGER | NOT NULL | Last update timestamp |
| `decay_rate` | REAL | DEFAULT 0.05 | Forgetting factor (5% per month) |
| `half_life_days` | INTEGER | DEFAULT 180 | Days until confidence halves |
| `last_drift_check_at` | INTEGER | — | Last drift check timestamp |
| `drift_detected` | BOOLEAN | DEFAULT FALSE | Concept drift detected? |
| `drift_magnitude` | REAL | — | Magnitude of drift |
| `status` | TEXT | DEFAULT 'ACTIVE' CHECK(...) | ACTIVE, DRIFTING, STALE, ARCHIVED |

**Primary Key**: `(entity_id, attribute, tenant_id)`

**Indexes** (3 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_anchors_entity` | `(entity_id, last_updated_at DESC)` | — | Entity history |
| `idx_anchors_confidence` | `(confidence DESC)` | `WHERE status = 'ACTIVE'` | High-confidence lookup |
| `idx_anchors_drift` | `(drift_detected, status)` | `WHERE drift_detected = TRUE` | Drift detection |

---

**Inputs Required**:

- [x] Dossier §6.12 schema (above)
- [x] Gap analysis confirms table is MISSING

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0038_st_anchors.py`
- [x] Table creation with composite PK
- [x] GENERATED STORED columns for `confidence` and `uncertainty`
- [x] CHECK constraint on `status`
- [x] All 4 indexes (3 dossier + 1 space index) with partial WHERE predicates

**Implementation Notes**:

```python
# Generated columns for Beta distribution metrics
sa.Column(
    "confidence", sa.Float(),
    sa.Computed("alpha / (alpha + beta)", persisted=True)
),
sa.Column(
    "uncertainty", sa.Float(),
    sa.Computed("1.0 / (1.0 + alpha + beta)", persisted=True)
)
```

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] Generated columns compute correctly
- [x] Composite PK enforces uniqueness
- [x] All 17 columns match dossier §6.12

**Blocked By**: 2.3.1

---

#### Issue 2.3.4 — Create `st_anchor_observations` (evidence log) table + indexes (Section 6.13)

**Status**: ✅ COMPLETED

**Goal**: Persist append-only evidence log explaining how anchors were updated.

**Spec Reference**: [Dossier §6.13 st_anchor_observations](../pipelines/P03_consolidation_dossier_v2.md#613-st_anchor_observations-evidence-log)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0039_st_anchor_observations.py`
- 9 columns matching dossier specification
- FK to st_anchors composite key (entity_id, attribute, tenant_id) with ON DELETE CASCADE
- FK to st_hipp_events(event_id) with ON DELETE SET NULL
- 3 indexes including partial index for event_id IS NOT NULL
- Added 8 tests in `TestMigration0039StAnchorObservations`

---

### Schema from Dossier §6.13

> **Role**: Audit trail for anchor updates (Bayesian evidence)

**Column Definitions** (9 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | ULID for observation |
| `entity_id` | TEXT | NOT NULL, FK part | Anchor entity |
| `attribute` | TEXT | NOT NULL, FK part | Anchor attribute |
| `tenant_id` | TEXT | NOT NULL, FK part | Anchor tenant |
| `observed_at` | INTEGER | NOT NULL | Observation timestamp |
| `event_id` | TEXT | FK | Source event |
| `supports_anchor` | BOOLEAN | NOT NULL | TRUE=evidence FOR, FALSE=AGAINST |
| `observation_weight` | REAL | DEFAULT 1.0 | Weight of observation [0-1] |
| `observation_context` | TEXT | — | Why interpreted as support/oppose |

**Foreign Keys**:

| FK | Columns | References |
|----|---------|------------|
| — | `(entity_id, attribute, tenant_id)` | `st_anchors(entity_id, attribute, tenant_id)` |
| — | `event_id` | `st_hipp_events(event_id)` |

**Indexes**:

| Index Name | Columns | Purpose |
|------------|---------|---------|
| `idx_anchor_obs_anchor` | `(entity_id, attribute, observed_at DESC)` | Latest observations per anchor |

---

**Inputs Required**:

- [x] Dossier §6.13 schema (above)
- [x] Gap analysis confirms table is MISSING
- [x] **st_anchors must exist first** (Issue 2.3.3)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0039_st_anchor_observations.py`
- [x] Table creation with all 9 columns
- [x] FK to st_anchors composite key
- [x] FK to st_hipp_events
- [x] Index for latest observations (+ 2 additional indexes)

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] Referential integrity holds (cannot insert for missing anchor)
- [x] Latest-observation queries efficient

**Blocked By**: 2.3.3

---

#### Issue 2.3.5 — Create `st_learned_weights` (adaptive parameters) table + RLS (Section 6.17)

**Status**: ✅ COMPLETED

**Goal**: Implement canonical learned-parameter store with isolation model.

**Spec Reference**: [Dossier §6.17 st_learned_weights](../pipelines/P03_consolidation_dossier_v2.md#617-st_learned_weights-adaptive-parameters)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0040_st_learned_weights.py`
- 16 columns matching dossier specification
- CHECK constraints: `ck_param_scope`, `ck_confidence_range`, `ck_sample_count_nonneg`
- UNIQUE constraint `uq_learned_weights` on (space_id, param_key, param_scope, scope_id)
- 3 indexes for fast lookups
- RLS policy `learned_weights_isolation` for multi-tenant isolation
- Added 10 tests in `TestMigration0040StLearnedWeights`

---

### Schema from Dossier §6.17

> **Role**: Central storage for all learned hyperparameters across P03 formulas
> **Purpose**: Single source of truth for adaptive parameters that learn from feedback
> **Scope**: Per-space isolation with hierarchical fallbacks

**Column Definitions** (17 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `param_id` | TEXT | PRIMARY KEY | UUID primary key |
| `param_key` | TEXT | NOT NULL | e.g., "importance_emotional", "decay_lambda_PERSON" |
| `param_scope` | TEXT | NOT NULL CHECK(...) | 'global', 'space', 'entity_type', 'entity' |
| `scope_id` | TEXT | — | space_id, entity_type, or entity_id (NULL for global) |
| `space_id` | TEXT | NOT NULL | Isolation (always set) |
| `current_value` | REAL | NOT NULL | Current learned value |
| `prior_value` | REAL | NOT NULL | Initial/default value |
| `confidence` | REAL | NOT NULL DEFAULT 0.0 CHECK(...) | Learning confidence [0-1] |
| `sample_count` | INTEGER | NOT NULL DEFAULT 0 CHECK(...) | Number of feedback samples |
| `last_updated_at` | BIGINT | NOT NULL | Timestamp (ms since epoch) |
| `version` | INTEGER | NOT NULL DEFAULT 1 | For parameter history/rollback |
| `previous_value` | REAL | — | Value before last update |
| `quality_at_update` | REAL | — | Quality metric when last updated |
| `rollback_eligible` | BOOLEAN | NOT NULL DEFAULT TRUE | Can be rolled back? |
| `created_at` | BIGINT | NOT NULL | Creation timestamp |
| `updated_at` | BIGINT | NOT NULL | Last update timestamp |

**Constraints**:

| Constraint | Type | Definition |
|------------|------|------------|
| `ck_param_scope` | CHECK | `param_scope IN ('global', 'space', 'entity_type', 'entity')` |
| `ck_confidence_range` | CHECK | `confidence >= 0.0 AND confidence <= 1.0` |
| `ck_sample_count_nonneg` | CHECK | `sample_count >= 0` |
| `uq_learned_weights` | UNIQUE | `(space_id, param_key, param_scope, scope_id)` |

**Indexes** (3 indexes):

| Index Name | Columns | Purpose |
|------------|---------|---------|
| `idx_learned_weights_space_key` | `(space_id, param_key)` | Fast lookup by space and key |
| `idx_learned_weights_scope` | `(space_id, param_scope, scope_id)` | Scope-based queries |
| `idx_learned_weights_confidence` | `(confidence DESC)` | Confidence-based filtering |

---

**Inputs Required**:

- [x] Dossier §6.17 schema (above)
- [x] Gap analysis confirms table is MISSING

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0040_st_learned_weights.py`
- [x] Table creation with all 16 columns
- [x] All CHECK constraints
- [x] UNIQUE constraint
- [x] All 3 indexes
- [x] RLS policy for multi-tenant isolation

**Implementation Notes**:

```python
# RLS for isolation
op.execute("""
    ALTER TABLE st_learned_weights ENABLE ROW LEVEL SECURITY;

    CREATE POLICY learned_weights_isolation ON st_learned_weights
        FOR ALL USING (space_id = current_setting('app.current_space_id', true));
""")
```

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] All CHECK constraints enforced
- [x] UNIQUE constraint prevents duplicate parameters
- [x] RLS prevents cross-space access
- [x] All 16 columns match dossier §6.17

**Blocked By**: 2.3.1

---

#### Issue 2.3.6 — Create `st_learned_weights_history` (parameter versioning) + retention (Section 6.23)

**Status**: ✅ COMPLETED

**Goal**: Add durable parameter history for rollback and longitudinal analysis.

**Spec Reference**: [Dossier §6.23 st_learned_weights_history](../pipelines/P03_consolidation_dossier_v2.md#623-st_learned_weights_history)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0041_st_learned_weights_history.py`
- 10 columns matching dossier specification
- FK to st_learned_weights(param_id) with ON DELETE CASCADE
- UNIQUE constraint `uq_weights_history_version` on (param_id, version)
- 3 indexes for version and time-based queries
- RLS policy `weights_history_isolation` for multi-tenant isolation
- Pruning trigger `trg_prune_weights_history` keeps only last 10 versions per param_id
- Added 8 tests in `TestMigration0041StLearnedWeightsHistory`

---

### Schema from Dossier §6.23

> **Role**: Version history for learned parameters
> **Purpose**: Enable rollback and track parameter evolution over time
> **Retention**: Keep last 10 versions per parameter

**Column Definitions** (10 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `history_id` | TEXT | PRIMARY KEY | ULID for history entry |
| `param_id` | TEXT | NOT NULL FK | Reference to st_learned_weights |
| `space_id` | TEXT | NOT NULL | Isolation (denormalized for RLS) |
| `version` | INTEGER | NOT NULL | Version number at time of snapshot |
| `value` | REAL | NOT NULL | Parameter value at this version |
| `confidence` | REAL | NOT NULL | Confidence at this version |
| `sample_count` | INTEGER | NOT NULL | Sample count at this version |
| `quality_metric` | REAL | — | Quality metric when updated |
| `created_at` | BIGINT | NOT NULL | When this version was created |
| `reason` | TEXT | — | Why parameter was updated |

**Constraints**:

| Constraint | Type | Definition |
|------------|------|------------|
| — | FK | `param_id REFERENCES st_learned_weights(param_id)` |
| `uq_weights_history_version` | UNIQUE | `(param_id, version)` |

**Indexes** (3 indexes):

| Index Name | Columns | Purpose |
|------------|---------|---------|
| `idx_weights_history_param_version` | `(param_id, version DESC)` | Latest version lookup |
| `idx_weights_history_param_time` | `(param_id, created_at DESC)` | Time-based rollback |
| `idx_weights_history_space` | `(space_id, created_at DESC)` | Space-level analysis |

---

**Inputs Required**:

- [x] Dossier §6.23 schema (above)
- [x] Gap analysis confirms table is MISSING
- [x] **st_learned_weights must exist first** (Issue 2.3.5)

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0041_st_learned_weights_history.py`
- [x] Table creation with all 10 columns
- [x] FK to st_learned_weights
- [x] UNIQUE constraint on (param_id, version)
- [x] All 3 indexes
- [x] RLS policy
- [x] Version pruning: keep only last 10 versions per param_id (trigger)

**Implementation Notes**:

```python
# Version pruning trigger (PostgreSQL)
op.execute("""
    CREATE OR REPLACE FUNCTION prune_weights_history()
    RETURNS TRIGGER AS $$
    BEGIN
        DELETE FROM st_learned_weights_history
        WHERE history_id IN (
            SELECT history_id FROM st_learned_weights_history
            WHERE param_id = NEW.param_id
            ORDER BY version DESC
            OFFSET 10
        );
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_prune_weights_history
    AFTER INSERT ON st_learned_weights_history
    FOR EACH ROW EXECUTE FUNCTION prune_weights_history();
""")
```

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] After >10 versions, oldest are automatically pruned
- [x] Rollback queries efficient via indexes
- [x] RLS prevents cross-space access

**Blocked By**: 2.3.5

---

#### Issue 2.3.7 — Create `st_feedback_quarantine` (suspicious signal quarantine) + indexes (Section 6.21)

**Status**: ✅ COMPLETED

**Goal**: Provide persistence for quarantining anomalous/adversarial feedback signals.

**Spec Reference**: [Dossier §6.21 st_feedback_quarantine](../pipelines/P03_consolidation_dossier_v2.md#621-st_feedback_quarantine)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0042_st_feedback_quarantine.py`
- 15 columns matching dossier specification
- 3 indexes with partial WHERE predicates for pending signals
- RLS policy `quarantine_isolation` for multi-tenant isolation
- Added 8 tests in `TestMigration0042StFeedbackQuarantine`

---

### Schema from Dossier §6.21

> **Role**: Hold suspicious feedback signals for human review or auto-release
> **Purpose**: Protect learning system from adversarial or anomalous signals

**Column Definitions** (15 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `quarantine_id` | TEXT | PRIMARY KEY | ULID for quarantine entry |
| `space_id` | TEXT | NOT NULL | User/family space |
| `tenant_id` | TEXT | NOT NULL | Multi-tenant isolation |
| `signal_id` | TEXT | NOT NULL | Reference to st_feedback_signals |
| `signal_type` | TEXT | NOT NULL | Type of feedback signal |
| `signal_payload_json` | JSONB | NOT NULL | Original signal payload |
| `quarantine_reason` | TEXT | NOT NULL | Why quarantined |
| `anomaly_score` | REAL | — | Anomaly detection score |
| `created_at` | BIGINT | NOT NULL | When quarantined |
| `auto_release_at` | BIGINT | — | When to auto-release (NULL = manual only) |
| `decision` | TEXT | — | RELEASE, REJECT, PENDING (NULL = pending) |
| `decided_by` | TEXT | — | Who made decision (system or user) |
| `decided_at` | BIGINT | — | When decision was made |
| `decision_reason` | TEXT | — | Why decision was made |
| `updated_at` | BIGINT | NOT NULL | Last update timestamp |

**Indexes** (3 indexes):

| Index Name | Columns | Condition | Purpose |
|------------|---------|-----------|---------|
| `idx_quarantine_space_status` | `(space_id, decision)` | `WHERE decision IS NULL` | Pending by space |
| `idx_quarantine_auto_release` | `(auto_release_at)` | `WHERE decision IS NULL` | Auto-release scan |
| `idx_quarantine_signal` | `(signal_id)` | — | Signal lookup |

---

**Inputs Required**:

- [x] Dossier §6.21 schema (above)
- [x] Gap analysis confirms table is MISSING

**Deliverables**:

- [x] New Alembic migration → `k0/db/alembic/versions/0042_st_feedback_quarantine.py`
- [x] Table creation with all 15 columns
- [x] All 3 indexes with partial WHERE predicates
- [x] RLS policy for isolation

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] Pending signals queryable efficiently by space
- [x] Auto-release scan efficient via partial index
- [x] Cross-space access blocked

**Blocked By**: 2.3.1

---

#### Issue 2.3.8 — Reconcile `st_feedback_signals` for P03 consumption semantics (consumed_at/consumed_by)

**Status**: ✅ COMPLETED

**Goal**: Make P03 feedback consumption durable and deterministic; resolve schema↔code mismatch.

**Spec Reference**: [Dossier §6.22 st_feedback_signals](../pipelines/P03_consolidation_dossier_v2.md#622-st_feedback_signals)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0043_st_feedback_signals_consumption.py`
- ALTER TABLE to add `consumed_at` (BIGINT) and `consumed_by` (TEXT)
- 2 partial indexes for unconsumed signals lookup
- Added 5 tests in `TestMigration0043StFeedbackSignalsConsumption`

---

### Existing Migration Analysis (from Part B)

**File**: `k0/db/alembic/versions/0026_st_feedback_signals.py`

| Aspect | Dossier | Migration | Match? |
|--------|---------|-----------|--------|
| `signal_payload` | JSONB | JSONB (presumed) | VERIFY |
| `consumed_at` | BIGINT | **MISSING** → FIXED | ✅ |
| `consumed_by` | TEXT | **MISSING** → FIXED | ✅ |

**Resolution**: Option A implemented - add consumed columns via ALTER.

---

**Inputs Required**:

- [x] Existing migration: `k0/db/alembic/versions/0026_st_feedback_signals.py`
- [x] Dossier consumption fields

**Deliverables**:

- [x] New corrective migration → `k0/db/alembic/versions/0043_st_feedback_signals_consumption.py`
- [x] ALTER TABLE to add `consumed_at` (BIGINT) and `consumed_by` (TEXT)
- [x] Add partial index for unconsumed signals: `WHERE consumed_at IS NULL`

**Acceptance**:

- [x] Migration applies cleanly on PostgreSQL
- [x] P03 can query unconsumed signals efficiently
- [x] P03 marks signals consumed exactly once (idempotent)
- [x] No reprocessing of already-consumed signals

**Blocked By**: 2.3.1

---

#### Issue 2.3.9 — Create `st_golden_dataset_pairs` + `st_validation_results` tables (Golden dataset)

**Status**: ✅ COMPLETED

**Goal**: Add durable golden dataset and validation result storage for drift detection.

**Spec Reference**: [Dossier §6.24-6.25](../pipelines/P03_consolidation_dossier_v2.md#624-st_golden_dataset_pairs)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0044_st_golden_dataset.py`
- Creates TWO tables: st_golden_dataset_pairs (12 cols) and st_validation_results (12 cols)
- FK from st_validation_results to st_golden_dataset_pairs
- Multiple indexes and RLS policies for both tables
- Added 10 tests in `TestMigration0044StGoldenDataset`

---

### Schema from Dossier §6.24-6.25

**st_golden_dataset_pairs** (12 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `pair_id` | TEXT | PRIMARY KEY | ULID for pair |
| `space_id` | TEXT | NOT NULL | User/family space |
| `entity_type` | TEXT | NOT NULL | Type of entity being tested |
| `input_json` | JSONB | NOT NULL | Input data for validation |
| `expected_output_json` | JSONB | NOT NULL | Expected ground truth |
| `ground_truth_source` | TEXT | NOT NULL | Where ground truth came from |
| `is_active` | BOOLEAN | DEFAULT TRUE | Is this pair active? |
| `difficulty` | TEXT | — | EASY, MEDIUM, HARD |
| `tags_json` | JSONB | — | Tags for filtering |
| `created_at` | BIGINT | NOT NULL | Creation timestamp |
| `updated_at` | BIGINT | NOT NULL | Last update timestamp |
| `created_by` | TEXT | NOT NULL | Who created this pair |

**st_validation_results** (12 columns):

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `result_id` | TEXT | PRIMARY KEY | ULID for result |
| `space_id` | TEXT | NOT NULL | User/family space |
| `pair_id` | TEXT | NOT NULL FK | Reference to golden pair |
| `actual_output_json` | JSONB | NOT NULL | Actual output from system |
| `is_correct` | BOOLEAN | NOT NULL | Did output match expected? |
| `similarity_score` | REAL | — | Similarity to expected |
| `error_type` | TEXT | — | Type of error if incorrect |
| `error_details_json` | JSONB | — | Error details |
| `model_version` | TEXT | NOT NULL | Model/algorithm version used |
| `param_snapshot_json` | JSONB | — | Parameters at time of test |
| `created_at` | BIGINT | NOT NULL | When validation ran |
| `duration_ms` | INTEGER | — | How long validation took |

---

**Inputs Required**:

- [x] Dossier §6.24-6.25 schemas (above)
- [x] Gap analysis confirms tables are MISSING

**Deliverables**:

- [ ] New Alembic migration → `k0/db/alembic/versions/0044_st_golden_dataset.py`
- [ ] Create `st_golden_dataset_pairs` with indexes
- [ ] Create `st_validation_results` with FK and indexes
- [ ] RLS for both tables

**Acceptance**:

- [ ] Migrations apply cleanly on PostgreSQL
- [ ] Basic read/write queries work
- [ ] FK from validation_results to golden_dataset_pairs enforced

**Blocked By**: 2.3.1

---

#### Issue 2.3.10 — Reconcile `st_dlq` schema and DLQ driver against dossier (Section 13.4)

**Status**: ✅ COMPLETED

**Goal**: Ensure P03 can reliably record failures to DLQ with dossier schema and retry semantics.

**Spec Reference**: [Dossier §13.4 st_dlq](../pipelines/P03_consolidation_dossier_v2.md#134-st_dlq)

**Implementation Summary**:

- Created `k0/db/alembic/versions/0045_st_dlq_p03_reconcile.py`
- Decision: **Option C** (Additive Approach) — add missing P03-specific columns without breaking existing functionality
- Added 12 new columns for P03-specific error tracking and resolution
- Updated state CHECK constraint to include new states (RESOLVED, ABANDONED, MANUAL_REVIEW, RETRYING)
- Added 3 partial indexes for P03-specific queries
- Added 11 tests in `TestMigration0045StDlqP03Reconcile`

---

### Existing Migration Analysis (from Part B)

**File**: `k0/db/alembic/versions/0009_st_dlq.py`

| Aspect | Dossier | Migration | Resolution |
|--------|---------|-----------|------------|
| `id` | TEXT (ULID) | BigInteger (auto-increment) | KEPT (backward compat) |
| `pipeline_id` | TEXT NOT NULL | **MISSING** | ✅ ADDED |
| `phase` | TEXT | **MISSING** | ✅ ADDED |
| `event_id` | TEXT | **MISSING** | ✅ ADDED |
| `entity_id` | TEXT | **MISSING** | ✅ ADDED |
| `error_type` | TEXT CHECK | **MISSING** | ✅ ADDED |
| `error_code` | TEXT | **MISSING** | ✅ ADDED |
| `stack_trace` | TEXT | **MISSING** | ✅ ADDED |
| `max_attempts` | INTEGER | **MISSING** | ✅ ADDED |
| `resolved_at` | BIGINT | **MISSING** | ✅ ADDED |
| `resolved_by` | TEXT | **MISSING** | ✅ ADDED |
| `resolution_notes` | TEXT | **MISSING** | ✅ ADDED |
| `updated_at` | BIGINT | **MISSING** | ✅ ADDED |
| `state` CHECK | 3 values | 7 values | ✅ EXPANDED |

**Existing Driver**: `k0/storage/dlq.py` - `DeadLetterQueue` class with `record()` method (unchanged - new columns are NULLABLE)

---

### Decision Made: Option C (Additive Approach)

| Option | Description | Chosen |
|--------|-------------|--------|
| A | Bring schema into full dossier compliance | ❌ |
| B | Declare dossier outdated, keep current | ❌ |
| **C** | Add missing columns only, keep id type | ✅ |

**Rationale**: The existing st_dlq (0009) serves as a generic K0 DLQ used by multiple pipelines. The dossier describes P03-specific DLQ requirements. Option C adds P03-specific columns as NULLABLE, enabling P03 to use enhanced tracking without breaking existing entries or other pipelines.

---

**Inputs Required**:

- [x] Existing migration: `k0/db/alembic/versions/0009_st_dlq.py`
- [x] Existing driver: `k0/storage/dlq.py`
- [x] Dossier §13.4 schema

**Deliverables**:

- [x] Governance decision: Option C (additive approach)
- [x] New corrective migration → `k0/db/alembic/versions/0045_st_dlq_p03_reconcile.py`
- [x] Decision documented in migration docstring
- [x] Added 11 tests in `TestMigration0045StDlqP03Reconcile`

**Columns Added** (12 total):

1. `pipeline_id` - TEXT (identifies source pipeline, e.g., 'p03_consolidation')
2. `phase` - TEXT (P03 phase: R0-R8)
3. `event_id` - TEXT (source event reference)
4. `entity_id` - TEXT (related entity reference)
5. `error_type` - TEXT with CHECK constraint (TRANSIENT, VALIDATION, LOGIC, FATAL)
6. `error_code` - TEXT (structured error code)
7. `stack_trace` - TEXT (optional stack trace)
8. `max_attempts` - INTEGER (retry limit, default 3)
9. `resolved_at` - BIGINT (resolution timestamp)
10. `resolved_by` - TEXT (who resolved)
11. `resolution_notes` - TEXT (resolution details)
12. `updated_at` - BIGINT (last update timestamp)

**Indexes Added** (3 partial):

1. `idx_dlq_p03_pipeline_phase` - (pipeline_id, phase) WHERE pipeline_id IS NOT NULL
2. `idx_dlq_pending_error_type` - (state, error_type) WHERE state = 'PENDING' AND error_type IS NOT NULL
3. `idx_dlq_event_id` - (event_id) WHERE event_id IS NOT NULL

**Acceptance**:

- [x] P03 error handling can record DLQ entry with required fields
- [x] Retry scans efficient via partial indexes
- [x] Decision documented in migration docstring
- [x] 11 tests passing

**Blocked By**: 2.3.1

---

## Part E: Milestone Summary

### E.1 Issue Count Summary

| Epic | Issue Count | Status |
|------|-------------|--------|
| Epic 2.1 — Core truth + operational tables | 12 issues | ✅ COMPLETED |
| Epic 2.2 — Audit + explainability + compliance | 5 issues | ✅ COMPLETED |
| Epic 2.3 — Learning + feedback persistence | 10 issues | ✅ COMPLETED |
| **Total M2** | **27 issues** | ✅ COMPLETED |

### E.2 Key Dependencies

```
M1 COMPLETE
    ↓
2.1.1 (Gap Analysis - truth/ops)
    ↓
2.1.2-2.1.12 (Create/verify tables) ─┬─→ 2.2.1 (Audit table)
                                      │        ↓
2.3.1 (Gap Analysis - learning)       │   2.2.2-2.2.5 (Audit features)
    ↓                                 │
2.3.2-2.3.10 (Learning tables) ───────┘
```

### E.3 Files Created (Expected)

| Category | Count | Location |
|----------|-------|----------|
| Alembic Migrations | ~15-20 | `k0/db/alembic/versions/00XX_*.py` |
| P03 Modules | 4 | `k0/pipelines/p03/audit_logger.py`, `explainability.py`, `retention.py`, `erasure.py` |
| Tests | 1+ | `tests/k0/pipelines/p03/test_storage.py` |

### E.4 Governance Checkpoints

| Checkpoint | When | What |
|------------|------|------|
| Pre-Epic 2.1 | Before starting | Run sync, capture baseline |
| Post-Epic 2.1 | After all 2.1.x complete | Verify no drift |
| Post-Epic 2.2 | After all 2.2.x complete | Verify no drift |
| Post-Epic 2.3 | After all 2.3.x complete | Verify no drift |
| M2 Complete | Before marking done | Final sync verification |
