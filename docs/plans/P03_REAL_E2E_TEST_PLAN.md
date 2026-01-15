# P03 Real End-to-End Test Execution Plan

> **Milestone**: M7 — P03 Real E2E Testing (NO MOCKS)
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M0-M6 COMPLETED
> **Branch**: `postgre-sql-migration`

---

## Executive Summary

**NO MOCKS. REAL DATABASE. REAL BUS. REAL EVERYTHING.**

This milestone implements comprehensive end-to-end testing for the P03 consolidation pipeline against:

- Real PostgreSQL 16 (via Docker)
- Real pgbouncer connection pooling
- Real Alembic migrations (0027-0045)
- Real UnitOfWork transactions
- Real outbox event emission
- Real DLQ + retry + circuit breaker behavior
- Real cross-pipeline integration (P02→P03→P06→P21)
- Real chaos/failure injection

**Total Test Categories**: 4 Epics, 31 Issues, ~87 real E2E tests

---

## Part A: Context Foundation

### A.1 Prerequisites Completed (M0-M6)

| Milestone | Status | Deliverables |
|-----------|--------|--------------|
| M0 | COMPLETE | 4 ADRs, pipeline contract, 17 module contracts, 8 event schemas |
| M1 | COMPLETE | 19 P03 modules (envelope, context, runner, checkpoint, offset_manager) |
| M2 | COMPLETE | 18 migrations (0027-0045), all truth tables, audit tables, learning tables |
| M3 | COMPLETE | R7 TruthWriter, R8 EventEmitter, OutboxPublisher, GapEmitter, FeedbackConsumer |
| M4 | COMPLETE | R1-R4 core cognition algorithms (ImportanceScorer, HebbianLearner, DBSCAN, SimHasher, EntityMerger) |
| M5 | COMPLETE | R6-R8 finalize: staging, commit, emit |
| M6 | COMPLETE | DLQ + Retries + Circuit Breakers (P08, Bus, FAISS), ErrorClassifier, PartialFailureHandler |

**Current Mock Test Count**: 2,766+ (all passing, but use mocks)

### A.2 Existing Docker Infrastructure

| Component | Location | Status |
|-----------|----------|--------|
| docker-compose.yml | `k0/deploy/docker-compose.yml` | EXISTS |
| PostgreSQL 16 | Container `k0-postgres` port 5432 | EXISTS |
| pgbouncer | Container `k0-pgbouncer` port 6432 | EXISTS |
| Neo4j 5.20 | Container `familyos-neo4j` ports 7474/7687 | EXISTS |
| k0.ps1 | `k0/deploy/k0.ps1` | EXISTS |
| Migrations | `k0/db/alembic/versions/0027-0045` | EXISTS |

### A.3 Tables Under Test

| Table | Purpose | Test Coverage |
|-------|---------|---------------|
| st_hipp_events | Source events (18+ cols, consolidation_status) | R0, R3, R7 |
| st_epi | Episodic memory (33 cols) | R7 |
| st_sem | Semantic patterns (26 cols) | R7 |
| st_procedural | Habits/routines (27 cols) | R7 |
| st_social | Relationships (27 cols) | R7 |
| st_prospective | Intentions/goals (23 cols) | R7 |
| st_kg_dom | KG entities (23 cols) | R4, R7 |
| st_kg_edges | KG relationships (22 cols) | R4, R7 |
| st_vec | pgvector embeddings | R7 |
| st_outbox | Event staging | R8 |
| st_offsets | Exactly-once offsets | R0, R8 |
| st_dlq | Dead letter queue | Error handling |
| st_consolidation_audit | Decision trail | R6, R7 |
| st_learned_weights | Thompson sampling params | R1 |
| st_learning_queue | P06 gap detection | R8 |
| st_feedback_quarantine | Quarantine system | R0 |

---

## Part B: Epic Structure

| Epic | Scope | Issues | Tests |
|------|-------|--------|-------|
| 7.1 | Real Database Infrastructure & Fixtures | 7 | 15 |
| 7.2 | Phase-by-Phase Real DB Tests (R0-R8) | 8 | 32 |
| 7.3 | Full Pipeline E2E Tests (All Paths) | 10 | 24 |
| 7.4 | Chaos Engineering & Failure Injection | 6 | 16 |
| **Total** | | **31** | **87** |

---

# Epic 7.1 — Real Database Infrastructure & Fixtures

> **Scope**: Create pytest fixtures that connect to real PostgreSQL, run real migrations, provide real connections to tests.
> **Output**: `tests/e2e/p03/conftest.py`, `tests/e2e/p03/fixtures/`
> **Test Count**: 15 tests

---

## Issue 7.1.1: Docker Compose E2E Configuration

**Create**: `k0/deploy/docker-compose.e2e.yml`

**Deliverables**:

- PostgreSQL 16 container on port 5433 (separate from dev on 5432)
- pgbouncer on port 6433
- Health checks configured
- Volumes for persistence

**Acceptance Criteria**:

- [ ] `docker-compose -f docker-compose.e2e.yml up -d` starts stack
- [ ] Health checks pass within 30s
- [ ] Port 5433 accessible from host
- [ ] Port 6433 accessible from host

---

## Issue 7.1.2: Real PostgreSQL Connection Fixture

**Create**: `tests/e2e/p03/conftest.py`

**Deliverables**:

- `real_pg_pool` fixture - asyncpg pool to real DB
- `real_pg_connection` fixture - single connection with transaction isolation
- Connection configuration (host, port, db, user, password)
- Proper cleanup on session end

**Acceptance Criteria**:

- [ ] Fixture connects to real PostgreSQL (port 5433)
- [ ] Connection pool properly initialized (min=2, max=20)
- [ ] Cleanup on test session end
- [ ] Skip if Docker not running

---

## Issue 7.1.3: Alembic Migration Runner Fixture

**Create**: `tests/e2e/p03/fixtures/migration_runner.py`

**Deliverables**:

- `run_migrations_to_head()` - applies all migrations
- `run_migrations_downgrade()` - downgrades for clean slate
- Environment variable configuration for E2E database
- Error handling for migration failures

**Acceptance Criteria**:

- [ ] Migrations 0027-0045 apply successfully
- [ ] All 16 P03 tables created
- [ ] Downgrade works for test isolation
- [ ] Idempotent (can run multiple times)

---

## Issue 7.1.4: Table Existence Verification Tests

**Create**: `tests/e2e/p03/test_database_foundation.py`

**Deliverables**:

- Test truth tables exist (st_epi, st_sem, st_procedural, st_social, st_prospective)
- Test KG tables exist (st_kg_dom, st_kg_edges)
- Test operational tables exist (st_hipp_events, st_vec, st_outbox, st_offsets, st_dlq)
- Test learning tables exist (st_learned_weights, st_learning_queue, st_consolidation_audit)
- Test RLS policies enabled on critical tables
- Test pgvector extension installed
- Test critical indexes exist

**Test Count**: 7 tests

**Acceptance Criteria**:

- [ ] 16 tables verified
- [ ] RLS policies checked on 5 tables
- [ ] pgvector extension confirmed
- [ ] HNSW index verified on st_vec

---

## Issue 7.1.5: Test Data Factory

**Create**: `tests/e2e/p03/fixtures/data_factory.py`

**Deliverables**:

- `create_test_hipp_event()` - creates valid st_hipp_events row
- `create_test_batch(count)` - creates batch of events
- `insert_test_batch(conn, events)` - inserts into real table
- `create_test_offset()` - creates offset record
- `create_test_learned_weights()` - creates weights record

**Acceptance Criteria**:

- [ ] Factory creates valid events with all 18+ columns
- [ ] Batch insertion works with asyncpg
- [ ] Embeddings are valid 768-dim vectors
- [ ] All FK constraints satisfied

---

## Issue 7.1.6: Test Cleanup Utilities

**Create**: `tests/e2e/p03/fixtures/cleanup.py`

**Deliverables**:

- `truncate_all_p03_tables(conn)` - truncates all tables in FK order
- `reset_offsets(conn, subscriber_id)` - resets offsets
- `cleanup_test_tenant(conn, tenant_id)` - removes tenant data
- Fixture that runs cleanup before/after each test class

**Acceptance Criteria**:

- [ ] All tables truncated in correct FK order (no constraint violations)
- [ ] Offsets reset properly
- [ ] No orphaned data after tests
- [ ] Idempotent cleanup

---

## Issue 7.1.7: pytest Markers and Configuration

**Update**: `pyproject.toml`, create `tests/e2e/pytest.ini`

**Deliverables**:

- `@pytest.mark.e2e` - end-to-end tests requiring real database
- `@pytest.mark.real_db` - tests that use real PostgreSQL
- `@pytest.mark.chaos` - chaos engineering tests
- `@pytest.mark.slow` - tests > 30 seconds
- pytest configuration for asyncio mode
- Test discovery configuration

**Acceptance Criteria**:

- [ ] `pytest -m e2e` runs only E2E tests
- [ ] `pytest -m "not e2e"` skips E2E tests
- [ ] `pytest -m chaos` runs only chaos tests
- [ ] Markers documented in pyproject.toml

---

# Epic 7.2 — Phase-by-Phase Real DB Tests (R0-R8)

> **Scope**: Test each P03 phase individually against real PostgreSQL
> **Output**: `tests/e2e/p03/phases/`
> **Test Count**: 32 tests

---

## Issue 7.2.1: R0 Batch Selection - Real DB

**Create**: `tests/e2e/p03/phases/test_r0_real.py`

**Tests** (5):

1. `test_r0_selects_pending_events` - R0 fetches only PENDING events
2. `test_r0_respects_offset` - R0 only selects events newer than last committed offset
3. `test_r0_empty_batch_skips` - R0 returns skip when no eligible events
4. `test_r0_batch_size_limit` - R0 respects max_batch_size configuration
5. `test_r0_space_isolation` - R0 only selects events from configured space_id

**Acceptance Criteria**:

- [ ] All 5 tests pass against real st_hipp_events
- [ ] Offset handling verified with real st_offsets
- [ ] Space isolation verified with real RLS

---

## Issue 7.2.2: R1 Importance Scoring - Real DB

**Create**: `tests/e2e/p03/phases/test_r1_real.py`

**Tests** (4):

1. `test_r1_uses_default_weights_when_empty` - Falls back to static weights when st_learned_weights empty
2. `test_r1_uses_learned_weights` - Reads weights from st_learned_weights
3. `test_r1_hebbian_updates_written` - Hebbian edge updates created in staging
4. `test_r1_audit_logged` - Importance decisions logged to st_consolidation_audit

**Acceptance Criteria**:

- [ ] Weight fallback verified with real empty table
- [ ] Learned weight read verified with real populated table
- [ ] Audit logging verified in real st_consolidation_audit

---

## Issue 7.2.3: R2 Episodic Clustering - Real DB

**Create**: `tests/e2e/p03/phases/test_r2_real.py`

**Tests** (4):

1. `test_r2_clusters_similar_events` - Clusters events with similar embeddings
2. `test_r2_episode_splitting` - Splits on time gap > 60 minutes
3. `test_r2_adaptive_params` - Adjusts eps/min_samples based on quality history
4. `test_r2_centroid_calculation` - Calculates cluster centroids correctly

**Acceptance Criteria**:

- [ ] Clustering verified with real 768-dim embeddings
- [ ] Episode splitting logic verified with real timestamps
- [ ] Adaptive parameters verified

---

## Issue 7.2.4: R3 Dedup & Decay - Real DB

**Create**: `tests/e2e/p03/phases/test_r3_real.py`

**Tests** (4):

1. `test_r3_simhash_dedup` - Detects near-duplicates via SimHash
2. `test_r3_decay_classification` - Classifies events as ACTIVE/ARCHIVE/PRUNE
3. `test_r3_immunity_protection` - Does not decay immune entities
4. `test_r3_near_duplicates_json_update` - Updates st_hipp_events.near_duplicates_json JSONB

**Acceptance Criteria**:

- [ ] SimHash deduplication verified with real embeddings
- [ ] Decay engine verified with real access patterns
- [ ] JSONB column updates verified

---

## Issue 7.2.5: R4 KG Consolidation - Real DB

**Create**: `tests/e2e/p03/phases/test_r4_real.py`

**Tests** (4):

1. `test_r4_entity_extraction` - Extracts entities and writes to staging
2. `test_r4_entity_disambiguation` - Merges similar entities based on threshold
3. `test_r4_causal_edge_creation` - Creates causal edges with sufficient observations
4. `test_r4_kg_dom_writes` - Staged writes target st_kg_dom correctly

**Acceptance Criteria**:

- [ ] Entity extraction verified
- [ ] Disambiguation verified with real embeddings
- [ ] Causal inference verified

---

## Issue 7.2.6: R6 Staging - Real DB

**Create**: `tests/e2e/p03/phases/test_r6_real.py`

**Tests** (4):

1. `test_r6_assembles_all_staged_writes` - Collects writes from all prior phases
2. `test_r6_idempotency_key_generation` - Generates deterministic idempotency keys
3. `test_r6_version_conflict_detection` - Detects VERSION_CONFLICT on stale event versions
4. `test_r6_audit_manifest_creation` - Creates write manifest for audit

**Acceptance Criteria**:

- [ ] Staged write assembly verified
- [ ] Idempotency keys verified as deterministic
- [ ] Version conflict handling verified

---

## Issue 7.2.7: R7 Truth Writer - Real DB

**Create**: `tests/e2e/p03/phases/test_r7_real.py`

**Tests** (8):

1. `test_r7_writes_to_st_epi` - Writes episodic memories to st_epi
2. `test_r7_writes_to_st_sem` - Writes semantic patterns to st_sem
3. `test_r7_writes_to_st_kg_dom` - Writes KG entities to st_kg_dom
4. `test_r7_writes_to_st_kg_edges` - Writes KG edges to st_kg_edges
5. `test_r7_atomic_commit` - Commits all writes atomically
6. `test_r7_rollback_on_failure` - Rolls back on any write failure
7. `test_r7_status_writeback` - Updates st_hipp_events.consolidation_status
8. `test_r7_audit_log_writes` - Writes decisions to st_consolidation_audit

**Acceptance Criteria**:

- [ ] All 5 truth layers verified (epi, sem, procedural, social, prospective)
- [ ] Both KG tables verified (kg_dom, kg_edges)
- [ ] UoW commit/rollback verified with real transactions
- [ ] Status writeback verified

---

## Issue 7.2.8: R8 Event Emission - Real DB

**Create**: `tests/e2e/p03/phases/test_r8_real.py`

**Tests** (4):

1. `test_r8_emits_completion_event` - Writes completion event to st_outbox
2. `test_r8_emits_gap_events` - Writes gap events to st_learning_queue
3. `test_r8_commits_offset` - Commits offset only on success
4. `test_r8_no_offset_on_failure` - Does NOT commit offset on failure

**Acceptance Criteria**:

- [ ] Outbox emission verified with real st_outbox
- [ ] Gap emission verified with real st_learning_queue
- [ ] Offset commit semantics verified with real st_offsets

---

# Epic 7.3 — Full Pipeline E2E Tests (All Paths)

> **Scope**: End-to-end R0→R8 tests covering ALL paths, not just happy path
> **Output**: `tests/e2e/p03/pipeline/`
> **Test Count**: 24 tests

---

## Issue 7.3.1: Happy Path - Full Consolidation Cycle

**Create**: `tests/e2e/p03/pipeline/test_full_cycle.py`

**Tests** (4):

1. `test_100_events_full_cycle` - 100 events flow through R0→R8 successfully
2. `test_1000_events_batch_cycle` - Large batch (1000 events) processes correctly
3. `test_multi_space_isolation` - Events from different spaces processed in isolation
4. `test_multi_tenant_isolation` - Events from different tenants processed in isolation

**Acceptance Criteria**:

- [ ] 100 events: all marked CONSOLIDATED, clusters in st_epi, entities in st_kg_dom
- [ ] 1000 events: completes within timeout, no memory issues
- [ ] Space isolation: RLS verified
- [ ] Tenant isolation: RLS verified

---

## Issue 7.3.2: Empty Batch Path

**Create**: `tests/e2e/p03/pipeline/test_empty_batch.py`

**Tests** (2):

1. `test_empty_batch_skips_all_phases` - No PENDING events → R0 skip → no writes
2. `test_all_events_already_consolidated` - All events CONSOLIDATED → empty batch

**Acceptance Criteria**:

- [ ] Skip semantics verified (no phase execution after R0)
- [ ] No writes to any table
- [ ] Offset unchanged

---

## Issue 7.3.3: Partial Success Path

**Create**: `tests/e2e/p03/pipeline/test_partial_success.py`

**Tests** (2):

1. `test_some_events_fail_validation` - Events failing validation are DLQ'd, rest succeed
2. `test_partial_cluster_failure` - Some clusters fail to write, others succeed (strategy-dependent)

**Acceptance Criteria**:

- [ ] Valid events CONSOLIDATED
- [ ] Invalid events in st_dlq with error context
- [ ] Partial failure strategy verified

---

## Issue 7.3.4: DLQ Escalation Path

**Create**: `tests/e2e/p03/pipeline/test_dlq_escalation.py`

**Tests** (4):

1. `test_transient_error_retried` - TRANSIENT error retried up to max_retries
2. `test_max_retries_to_dlq` - After max_retries, event goes to DLQ
3. `test_fatal_error_immediate_dlq` - FATAL error goes to DLQ immediately
4. `test_dlq_record_contains_full_context` - DLQ record includes error, phase, envelope, trace_id

**Acceptance Criteria**:

- [ ] Retry logic verified with real ErrorClassifier
- [ ] DLQ record completeness verified
- [ ] Error types (TRANSIENT, VALIDATION, LOGIC, FATAL) handled correctly

---

## Issue 7.3.5: Circuit Breaker Paths

**Create**: `tests/e2e/p03/pipeline/test_circuit_breakers.py`

**Tests** (4):

1. `test_p08_circuit_open_blocks_pipeline` - P08 circuit OPEN → pipeline waits or fails fast
2. `test_bus_circuit_open_queues_events` - Bus circuit OPEN → events queue in outbox
3. `test_faiss_circuit_open_skips_embedding` - FAISS circuit OPEN → embedding operations skipped
4. `test_circuit_half_open_probe` - HALF_OPEN circuit allows probe request

**Acceptance Criteria**:

- [ ] All 3 circuits (P08, Bus, FAISS) verified
- [ ] State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED) verified
- [ ] Metrics emitted

---

## Issue 7.3.6: Checkpoint Resume Path

**Create**: `tests/e2e/p03/pipeline/test_checkpoint_resume.py`

**Tests** (3):

1. `test_resume_from_r4_checkpoint` - Pipeline resumes from R4 checkpoint after crash
2. `test_checkpoint_idempotency` - Resuming from checkpoint produces same result
3. `test_stale_checkpoint_rejected` - Checkpoint older than retention window rejected

**Acceptance Criteria**:

- [ ] Resume semantics verified (R5-R8 complete, no duplicate R0-R4 work)
- [ ] Idempotency verified (same final state)
- [ ] Stale checkpoint handling verified

---

## Issue 7.3.7: Version Conflict Path

**Create**: `tests/e2e/p03/pipeline/test_version_conflict.py`

**Tests** (3):

1. `test_version_conflict_triggers_retry` - VERSION_CONFLICT in R6 → retry with fresh versions
2. `test_persistent_conflict_to_dlq` - Persistent VERSION_CONFLICT → DLQ after max retries
3. `test_conflict_metrics_emitted` - VERSION_CONFLICT increments conflict counter

**Acceptance Criteria**:

- [ ] Retry behavior verified with real version mismatch
- [ ] Metrics verified
- [ ] DLQ escalation verified

---

## Issue 7.3.8: Feedback Integration Path

**Create**: `tests/e2e/p03/pipeline/test_feedback_integration.py`

**Tests** (3):

1. `test_p21_feedback_updates_weights` - P21 feedback signal updates st_learned_weights
2. `test_quarantine_feedback_ignored` - Quarantined feedback not applied
3. `test_feedback_loop_convergence` - Multiple feedback cycles converge weights

**Acceptance Criteria**:

- [ ] P21 integration verified with real st_feedback_signals
- [ ] Quarantine handling verified with real st_feedback_quarantine
- [ ] Weight convergence verified

---

## Issue 7.3.9: Gap Detection Path

**Create**: `tests/e2e/p03/pipeline/test_gap_detection.py`

**Tests** (4):

1. `test_ambiguous_entity_creates_gap` - Ambiguous entity → gap in st_learning_queue
2. `test_gap_resolution_updates_entity` - P06 answer resolves gap → entity updated in next cycle
3. `test_gap_priority_ordering` - Gaps processed in priority order
4. `test_gap_deduplication` - Duplicate gaps not created

**Acceptance Criteria**:

- [ ] P06 integration verified with real st_learning_queue
- [ ] Priority ordering verified
- [ ] Deduplication verified

---

## Issue 7.3.10: Cross-Pipeline Integration Path

**Create**: `tests/e2e/p03/pipeline/test_cross_pipeline.py`

**Tests** (4):

1. `test_p02_event_triggers_p03` - P02 completion event triggers P03 batch selection
2. `test_p03_gap_triggers_p06` - P03 gap emission triggers P06 active learning
3. `test_p21_feedback_triggers_p03_update` - P21 feedback triggers P03 weight update
4. `test_full_feedback_loop_p03_p21_p03` - Complete cycle: P03 → user action → P21 → P03 update

**Acceptance Criteria**:

- [ ] P02→P03 handoff verified
- [ ] P03→P06 gap emission verified
- [ ] P21→P03 feedback loop verified

---

# Epic 7.4 — Chaos Engineering & Failure Injection

> **Scope**: Test P03 resilience under failure conditions
> **Output**: `tests/e2e/p03/chaos/`
> **Test Count**: 16 tests

---

## Issue 7.4.1: PostgreSQL Primary Failure

**Create**: `tests/e2e/p03/chaos/test_postgres_failure.py`

**Tests** (3):

1. `test_primary_kill_during_r7` - Kill PostgreSQL during R7 write phase
2. `test_connection_drop_mid_transaction` - Connection dropped mid-transaction
3. `test_pgbouncer_restart` - pgbouncer restart during pipeline

**Acceptance Criteria**:

- [ ] UoW rollback verified (no partial writes)
- [ ] Recovery verified after postgres restart
- [ ] Reconnection verified after pgbouncer restart

---

## Issue 7.4.2: Connection Pool Exhaustion

**Create**: `tests/e2e/p03/chaos/test_pool_exhaustion.py`

**Tests** (3):

1. `test_pool_exhaustion_queues_requests` - Pool exhaustion queues requests, no failures
2. `test_pool_timeout_triggers_retry` - Pool timeout triggers retry with backoff
3. `test_pool_recovery_resumes_processing` - Pool recovery resumes queued requests

**Acceptance Criteria**:

- [ ] Queue behavior verified (no immediate failure)
- [ ] Recovery verified
- [ ] No lost requests

---

## Issue 7.4.3: Network Partition Simulation

**Create**: `tests/e2e/p03/chaos/test_network_partition.py`

**Tests** (3):

1. `test_app_db_partition` - Network partition between app and database
2. `test_latency_injection` - High latency injection (500ms)
3. `test_packet_loss_injection` - 10% packet loss injection

**Acceptance Criteria**:

- [ ] Partition handling verified (timeout, retry)
- [ ] Latency tolerance verified
- [ ] Packet loss tolerance verified

---

## Issue 7.4.4: Outbox Drain Failure

**Create**: `tests/e2e/p03/chaos/test_outbox_drain.py`

**Tests** (3):

1. `test_bus_unavailable_queues_in_outbox` - Bus unavailable → events queue in st_outbox
2. `test_outbox_retry_on_bus_recovery` - Outbox retries when bus recovers
3. `test_outbox_dlq_after_max_retries` - Outbox events DLQ'd after max retries

**Acceptance Criteria**:

- [ ] Event durability verified (no lost events)
- [ ] Retry logic verified
- [ ] DLQ escalation verified

---

## Issue 7.4.5: Concurrent Pipeline Execution

**Create**: `tests/e2e/p03/chaos/test_concurrent_execution.py`

**Tests** (3):

1. `test_two_cycles_concurrent` - Two P03 cycles running concurrently don't conflict
2. `test_lock_contention_handling` - Lock contention handled gracefully
3. `test_offset_race_condition` - Offset updates don't race

**Acceptance Criteria**:

- [ ] No duplicate processing
- [ ] Lock handling verified
- [ ] Offset atomicity verified

---

## Issue 7.4.6: Chaos Test Runner Script

**Create**: `k0/deploy/run_e2e_tests.ps1`

**Deliverables**:

- PowerShell script to run E2E tests
- Docker stack management (start/stop)
- Migration execution
- Scope selection (phases, pipeline, chaos, all)
- Results reporting

**Acceptance Criteria**:

- [ ] Script starts Docker stack
- [ ] Script runs migrations
- [ ] Script runs appropriate test scope
- [ ] Exit code reflects test results

---

# Part C: Summary & Execution Plan

## Issue Summary

| Epic | Issues | Tests | Status |
|------|--------|-------|--------|
| 7.1 Infrastructure & Fixtures | 7 | 15 | NOT_STARTED |
| 7.2 Phase-by-Phase Real DB | 8 | 32 | NOT_STARTED |
| 7.3 Full Pipeline E2E (All Paths) | 10 | 24 | NOT_STARTED |
| 7.4 Chaos Engineering | 6 | 16 | NOT_STARTED |
| **Total** | **31** | **87** | - |

---

## Execution Order

### Week 1: Epic 7.1 (Infrastructure)

| Day | Issue | Deliverable |
|-----|-------|-------------|
| 1 | 7.1.1 | Docker Compose E2E |
| 1 | 7.1.2 | Real PostgreSQL Fixture |
| 2 | 7.1.3 | Migration Runner |
| 2 | 7.1.4 | Table Verification Tests |
| 3 | 7.1.5 | Data Factory |
| 3 | 7.1.6 | Cleanup Utilities |
| 4 | 7.1.7 | pytest Markers |

### Week 2: Epic 7.2 (Phase Tests)

| Day | Issue | Deliverable |
|-----|-------|-------------|
| 1 | 7.2.1 | R0 Real DB (5 tests) |
| 1 | 7.2.2 | R1 Real DB (4 tests) |
| 2 | 7.2.3 | R2 Real DB (4 tests) |
| 2 | 7.2.4 | R3 Real DB (4 tests) |
| 3 | 7.2.5 | R4 Real DB (4 tests) |
| 3 | 7.2.6 | R6 Real DB (4 tests) |
| 4 | 7.2.7 | R7 Real DB (8 tests) |
| 4 | 7.2.8 | R8 Real DB (4 tests) |

### Week 3: Epic 7.3 (Pipeline E2E)

| Day | Issue | Deliverable |
|-----|-------|-------------|
| 1 | 7.3.1 | Happy Path (4 tests) |
| 1 | 7.3.2 | Empty Batch (2 tests) |
| 2 | 7.3.3 | Partial Success (2 tests) |
| 2 | 7.3.4 | DLQ Escalation (4 tests) |
| 3 | 7.3.5 | Circuit Breakers (4 tests) |
| 3 | 7.3.6 | Checkpoint Resume (3 tests) |
| 4 | 7.3.7 | Version Conflict (3 tests) |
| 4 | 7.3.8 | Feedback Integration (3 tests) |
| 5 | 7.3.9 | Gap Detection (4 tests) |
| 5 | 7.3.10 | Cross-Pipeline (4 tests) |

### Week 4: Epic 7.4 (Chaos)

| Day | Issue | Deliverable |
|-----|-------|-------------|
| 1 | 7.4.1 | PostgreSQL Failure (3 tests) |
| 2 | 7.4.2 | Pool Exhaustion (3 tests) |
| 3 | 7.4.3 | Network Partition (3 tests) |
| 4 | 7.4.4 | Outbox Drain Failure (3 tests) |
| 4 | 7.4.5 | Concurrent Execution (3 tests) |
| 5 | 7.4.6 | Test Runner Script |

---

## Files Created

```
tests/e2e/p03/
├── conftest.py                          # Issue 7.1.2
├── pytest.ini                           # Issue 7.1.7
├── test_database_foundation.py          # Issue 7.1.4
├── fixtures/
│   ├── __init__.py
│   ├── migration_runner.py              # Issue 7.1.3
│   ├── data_factory.py                  # Issue 7.1.5
│   └── cleanup.py                       # Issue 7.1.6
├── phases/
│   ├── __init__.py
│   ├── test_r0_real.py                  # Issue 7.2.1
│   ├── test_r1_real.py                  # Issue 7.2.2
│   ├── test_r2_real.py                  # Issue 7.2.3
│   ├── test_r3_real.py                  # Issue 7.2.4
│   ├── test_r4_real.py                  # Issue 7.2.5
│   ├── test_r6_real.py                  # Issue 7.2.6
│   ├── test_r7_real.py                  # Issue 7.2.7
│   └── test_r8_real.py                  # Issue 7.2.8
├── pipeline/
│   ├── __init__.py
│   ├── test_full_cycle.py               # Issue 7.3.1
│   ├── test_empty_batch.py              # Issue 7.3.2
│   ├── test_partial_success.py          # Issue 7.3.3
│   ├── test_dlq_escalation.py           # Issue 7.3.4
│   ├── test_circuit_breakers.py         # Issue 7.3.5
│   ├── test_checkpoint_resume.py        # Issue 7.3.6
│   ├── test_version_conflict.py         # Issue 7.3.7
│   ├── test_feedback_integration.py     # Issue 7.3.8
│   ├── test_gap_detection.py            # Issue 7.3.9
│   └── test_cross_pipeline.py           # Issue 7.3.10
└── chaos/
    ├── __init__.py
    ├── test_postgres_failure.py         # Issue 7.4.1
    ├── test_pool_exhaustion.py          # Issue 7.4.2
    ├── test_network_partition.py        # Issue 7.4.3
    ├── test_outbox_drain.py             # Issue 7.4.4
    └── test_concurrent_execution.py     # Issue 7.4.5

k0/deploy/
├── docker-compose.e2e.yml               # Issue 7.1.1
└── run_e2e_tests.ps1                    # Issue 7.4.6
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Total E2E Tests | 87 |
| Test Coverage (real DB paths) | 100% of P03 code paths |
| Test Execution Time | < 30 min (full suite) |
| Chaos Test Pass Rate | 100% (resilience verified) |
| Zero Mock Tests | 0 mocks in E2E suite |

---

**Ready to proceed with Epic 7.1, Issue 7.1.1: Docker Compose E2E Configuration.**
