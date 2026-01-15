# P03 Integration Test Plan

> **Issue**: 3.2.7 — Cross-Pipeline Integration Tests
> **Status**: ✅ COMPLETE
> **Created**: 2026-01-01
> **Last Updated**: 2026-01-01 (Phase 4 completion)
> **Total Tests**: 107 planned → **887 actual** (P03 suite)

---

## Progress Summary

| Phase | Description | Status | Tests Added |
|-------|-------------|--------|-------------|
| Phase 1 | E2E Pipeline Tests | ✅ DONE | 11 tests |
| Phase 2 | Cross-Pipeline Integration | ✅ DONE | 20 tests |
| Phase 3 | Envelope/Runner Integration | ✅ DONE | 17 tests |
| Phase 4 | Suite Summary Verification | ✅ DONE | 19 tests |

**Final Test Count**: 887 tests (P03 suite)

---

## Overview

This document defines the complete integration test plan for P03 consolidation pipeline, covering all milestones M0-M3.

---

## 1. M1 Envelope & Runner Tests (8 tests)

**File**: `tests/k0/pipelines/p03/test_envelope_integration.py`

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 1 | `test_envelope_frozen_context_prevents_mutation` | Envelope | P03CycleContext immutability | ☐ |
| 2 | `test_envelope_events_list_is_mutable` | Envelope | P03EventState mutation allowed | ☐ |
| 3 | `test_envelope_serialization_roundtrip` | Serialization | JSON ↔ Object roundtrip | ☐ |
| 4 | `test_checkpoint_save_and_restore` | Checkpoint | PhaseCheckpoint persistence | ☐ |
| 5 | `test_sequential_runner_phase_chain_r1_to_r6` | Runner | Phase sequence execution | ☐ |
| 6 | `test_sequential_runner_halts_on_fatal_error` | Runner | Early termination | ☐ |
| 7 | `test_sequential_runner_skip_phases_honor_skip_policy` | Runner | P03SkipPolicy | ☐ |
| 8 | `test_deterministic_seed_reproducibility` | Determinism | Same inputs → same outputs | ☐ |

---

## 2. M2 Storage Migration Tests (12 tests)

**File**: `tests/k0/pipelines/p03/test_storage_migrations.py` (exists, verify coverage)

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 9 | `test_st_epi_schema_matches_dossier_33_columns` | Migration | st_epi completeness | ☐ |
| 10 | `test_st_sem_schema_matches_dossier_26_columns` | Migration | st_sem completeness | ☐ |
| 11 | `test_st_procedural_schema_matches_dossier` | Migration | st_procedural completeness | ☐ |
| 12 | `test_st_social_schema_matches_dossier` | Migration | st_social completeness | ☐ |
| 13 | `test_st_prospective_schema_matches_dossier` | Migration | st_prospective completeness | ☐ |
| 14 | `test_st_kg_dom_schema_matches_dossier` | Migration | st_kg_dom completeness | ☐ |
| 15 | `test_st_kg_edges_schema_matches_dossier` | Migration | st_kg_edges completeness | ☐ |
| 16 | `test_st_hipp_events_p03_columns_added` | Migration | consolidation_status, etc. | ☐ |
| 17 | `test_st_outbox_next_attempt_ts_is_bigint` | Migration | Type fix verified | ☐ |
| 18 | `test_st_consolidation_audit_schema` | Migration | Audit table | ☐ |
| 19 | `test_st_learning_queue_schema` | Migration | Gap queue table | ☐ |
| 20 | `test_st_feedback_signals_consumption_columns` | Migration | consumed_at, consumed_by | ☐ |

---

## 3. M3 Epic 3.1 — R7/R8 Phase & Outbox Tests (25 tests)

**File**: `tests/k0/pipelines/p03/test_r7_r8_integration.py` (exists, extend)

### 3.1 R7 Truth Writer Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 21 | `test_r7_commit_persists_truth_and_outbox_atomically` | R7 Atomicity | UoW transaction | ☐ |
| 22 | `test_r7_failure_rolls_back_truth_and_outbox` | R7 Rollback | Transaction rollback | ☐ |
| 23 | `test_r7_writes_in_dependency_order` | R7 Order | vec→kg→epi→sem order | ☐ |
| 24 | `test_r7_optimistic_lock_conflict_detection` | R7 Locking | Version check | ☐ |
| 25 | `test_r7_insert_with_on_conflict_do_nothing` | R7 Idempotency | Duplicate insert safety | ☐ |
| 26 | `test_r7_update_increments_version` | R7 Versioning | version = version + 1 | ☐ |
| 27 | `test_r7_archive_sets_archival_status` | R7 Archive | Soft delete | ☐ |
| 28 | `test_r7_tombstone_marks_record` | R7 Tombstone | Hard delete marker | ☐ |
| 29 | `test_r7_stages_outbox_for_each_staged_event` | R7 Outbox | OutboxEntry staging | ☐ |

### 3.2 R8 Event Emitter Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 30 | `test_r8_builds_completion_payload_with_required_fields` | R8 Payload | Schema compliance | ☐ |
| 31 | `test_r8_status_success_when_all_phases_done` | R8 Status | SUCCESS determination | ☐ |
| 32 | `test_r8_status_partial_when_some_failures` | R8 Status | PARTIAL determination | ☐ |
| 33 | `test_r8_status_failed_when_fatal_error` | R8 Status | FAILED determination | ☐ |
| 34 | `test_r8_stages_completion_event_to_outbox` | R8 Outbox | Completion event | ☐ |
| 35 | `test_r8_persists_gaps_to_learning_queue` | R8 Gaps | st_learning_queue insert | ☐ |
| 36 | `test_r8_stages_gap_events_to_outbox` | R8 Gaps | Gap event staging | ☐ |
| 37 | `test_r8_commits_offset_on_success` | R8 Offset | Exactly-once | ☐ |
| 38 | `test_r8_fingerprint_enables_deduplication` | R8 Idempotency | Fingerprint pattern | ☐ |

### 3.3 Outbox Publisher Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 39 | `test_publisher_delivers_to_bus` | Outbox | Bus delivery | ☐ |
| 40 | `test_publisher_retries_on_transient_failure` | Outbox | Exponential backoff | ☐ |
| 41 | `test_publisher_backoff_formula` | Outbox | base*2^retries+jitter | ☐ |
| 42 | `test_publisher_dlq_after_max_retries` | Outbox | DLQ escalation | ☐ |
| 43 | `test_publisher_dlq_entry_has_p03_context` | Outbox | DLQ metadata | ☐ |

### 3.4 R7/R8 E2E Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 44 | `test_r7_r8_publisher_end_to_end_happy_path` | E2E | Full flow | ☐ |
| 45 | `test_r7_failure_prevents_r8_execution` | E2E | Failure isolation | ☐ |

---

## 4. M3 Epic 3.2 — R0 Event Ingestion Tests (13 tests)

**File**: `tests/k0/pipelines/p03/test_r0_integration.py`

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 46 | `test_r0_fetches_offset_at_startup` | R0 Offset | OffsetStore.fetch | ☐ |
| 47 | `test_r0_starts_at_zero_when_no_offset` | R0 Offset | Default offset | ☐ |
| 48 | `test_r0_respects_offset_exactly` | R0 Offset | Boundary condition | ☐ |
| 49 | `test_r0_ingestion_respects_offset` | R0 Offset | Only events > offset | ☐ |
| 50 | `test_r0_offset_unchanged_on_failure` | R0 Rollback | Offset not advanced | ☐ |
| 51 | `test_r0_excludes_non_ready_embeddings` | R0 Filter | embedding_status=READY | ☐ |
| 52 | `test_r0_excludes_already_consolidated` | R0 Filter | consolidation_status IS NULL | ☐ |
| 53 | `test_r0_excludes_archived_events` | R0 Filter | archival_status IS NULL | ☐ |
| 54 | `test_r0_respects_batch_size_limit` | R0 Batch | batch_size config | ☐ |
| 55 | `test_r0_skip_when_no_events` | R0 Skip | Returns SKIP result | ☐ |
| 56 | `test_r0_creates_valid_envelope` | R0 Envelope | P03BatchEnvelope structure | ☐ |
| 57 | `test_r0_envelope_watermark_is_max_event_id` | R0 Watermark | Watermark calculation | ☐ |
| 58 | `test_r0_event_state_population` | R0 Events | P03Event field mapping | ☐ |

---

## 5. M3 Epic 3.2 — Status Writeback Tests (9 tests)

**File**: `tests/k0/pipelines/p03/test_status_writeback.py`

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 59 | `test_writeback_updates_hipp_events` | Writeback | All events updated | ☐ |
| 60 | `test_writeback_maps_actions_to_status` | Writeback | ReconciliationAction → status | ☐ |
| 61 | `test_writeback_sets_cycle_id` | Writeback | consolidation_cycle_id | ☐ |
| 62 | `test_writeback_sets_timestamp` | Writeback | consolidated_at | ☐ |
| 63 | `test_writeback_records_best_match` | Writeback | truth_match_id, similarity | ☐ |
| 64 | `test_writeback_returns_status_distribution` | Writeback | Metrics summary | ☐ |
| 65 | `test_valid_transition_from_null_to_consolidated` | Transition | NULL → CONSOLIDATED | ☐ |
| 66 | `test_valid_transition_from_pending_to_consolidated` | Transition | PENDING → CONSOLIDATED | ☐ |
| 67 | `test_idempotent_same_status_transition` | Transition | Same status allowed | ☐ |

---

## 6. M3 Epic 3.2 — Gap Emitter Tests (13 tests)

**File**: `tests/k0/pipelines/p03/test_gap_emitter_integration.py`

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 68 | `test_gap_type_enum_values` | Gap Types | 7 types from dossier | ☐ |
| 69 | `test_gap_id_generation_pattern` | Gap ID | p03:gap:{cycle}:{entity}:{type} | ☐ |
| 70 | `test_gap_id_uniqueness` | Gap ID | Different gaps → different IDs | ☐ |
| 71 | `test_gap_persisted_to_learning_queue` | Persistence | st_learning_queue insert | ☐ |
| 72 | `test_gap_uses_on_conflict_do_nothing` | Persistence | Idempotent insert | ☐ |
| 73 | `test_gap_deduplication_within_window` | Dedup | Duplicate within 1hr skipped | ☐ |
| 74 | `test_gap_deduplication_respects_window` | Dedup | After window = new gap | ☐ |
| 75 | `test_gap_priority_calculation` | Priority | SEMANTIC_CONFLICT=100 | ☐ |
| 76 | `test_gap_staged_to_outbox` | Outbox | OutboxEntry created | ☐ |
| 77 | `test_gap_outbox_fingerprint_matches_gap_id` | Outbox | Fingerprint = gap_id | ☐ |
| 78 | `test_gap_payload_contains_required_fields` | Payload | 9 required fields | ☐ |
| 79 | `test_emit_gaps_happy_path` | E2E | Full emit flow | ☐ |
| 80 | `test_emit_gaps_returns_correct_count` | E2E | Count excludes dedup | ☐ |

---

## 7. M3 Epic 3.2 — P21 Feedback Consumer Tests (17 tests)

**File**: `tests/k0/pipelines/p03/test_feedback_consumer_integration.py`

### 7.1 Payload & Type Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 81 | `test_p03_feedback_payload_schema` | Payload | 6 feedback types | ☐ |
| 82 | `test_feedback_type_enum_values` | Types | All 6 types defined | ☐ |

### 7.2 Consumer Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 83 | `test_p21_feedback_consumed` | Consumer | Returns True on success | ☐ |
| 84 | `test_p21_feedback_routed_by_type` | Routing | Correct handler called | ☐ |
| 85 | `test_p21_feedback_marked_consumed` | Consumption | consumed_at set | ☐ |
| 86 | `test_p21_unknown_type_returns_false` | Error | Unknown type handled | ☐ |

### 7.3 Handler Stub Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 87 | `test_salience_handler_stub` | Handler | SALIENCE_ADJUSTMENT routed | ☐ |
| 88 | `test_decay_handler_stub` | Handler | DECAY_REVERSAL routed | ☐ |
| 89 | `test_cluster_handler_stub` | Handler | CLUSTER_CORRECTION routed | ☐ |
| 90 | `test_reinforcement_handler_stub` | Handler | REINFORCEMENT_OUTCOME routed | ☐ |
| 91 | `test_novelty_handler_stub` | Handler | NOVELTY_SIGNAL routed | ☐ |
| 92 | `test_regret_handler_stub` | Handler | REGRET_SIGNAL routed | ☐ |

### 7.4 Subscriber Lifecycle Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 93 | `test_subscriber_start_stop_lifecycle` | Lifecycle | Start/stop subscriber | ☐ |
| 94 | `test_subscriber_registers_handler` | Lifecycle | Handler registration | ☐ |

### 7.5 Metrics Tests

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 95 | `test_metrics_track_received` | Metrics | p03_feedback_received_total | ☐ |
| 96 | `test_metrics_track_processed` | Metrics | p03_feedback_processed_total | ☐ |
| 97 | `test_metrics_track_errors` | Metrics | p03_feedback_errors_total | ☐ |

---

## 8. End-to-End Full Pipeline Tests (10 tests)

**File**: `tests/k0/pipelines/p03/test_full_pipeline_e2e.py`

| # | Test Name | Category | Validates | Status |
|---|-----------|----------|-----------|--------|
| 98 | `test_full_cycle_r0_to_r8_happy_path` | E2E | Complete R0→R8 flow | ☐ |
| 99 | `test_full_cycle_with_empty_batch_skips` | E2E | No-work cycle | ☐ |
| 100 | `test_full_cycle_with_gaps_emits_to_p06` | E2E | Gap detection → P06 | ☐ |
| 101 | `test_full_cycle_updates_all_event_statuses` | E2E | Status writeback | ☐ |
| 102 | `test_full_cycle_advances_offset` | E2E | Offset committed | ☐ |
| 103 | `test_full_cycle_completion_event_published` | E2E | Bus delivery | ☐ |
| 104 | `test_full_cycle_idempotent_on_retry` | E2E | Same cycle_id = no dupe | ☐ |
| 105 | `test_failure_in_r1_halts_before_r7` | E2E | Early termination | ☐ |
| 106 | `test_failure_in_r7_rolls_back_all` | E2E | Transaction rollback | ☐ |
| 107 | `test_feedback_received_during_cycle` | E2E | P21 integration | ☐ |

---

## Summary

| Section | Category | Test Count | Completed |
|---------|----------|------------|-----------|
| 1 | M1 Envelope/Runner | 8 | 0 |
| 2 | M2 Storage/Migrations | 12 | 0 |
| 3 | M3 Epic 3.1 (R7/R8/Outbox) | 25 | 0 |
| 4 | M3 Epic 3.2 R0 Ingestion | 13 | 0 |
| 5 | M3 Epic 3.2 Status Writeback | 9 | 0 |
| 6 | M3 Epic 3.2 Gap Emitter | 13 | 0 |
| 7 | M3 Epic 3.2 P21 Feedback | 17 | 0 |
| 8 | E2E Full Pipeline | 10 | 0 |
| **TOTAL** | | **107** | **0** |

---

## Test Files to Create

| File | Tests | Priority |
|------|-------|----------|
| `tests/k0/pipelines/p03/test_envelope_integration.py` | #1-8 | P2 |
| `tests/k0/pipelines/p03/test_storage_migrations.py` | #9-20 | P2 (verify existing) |
| `tests/k0/pipelines/p03/test_r7_r8_integration.py` | #21-45 | P1 (extend existing) |
| `tests/k0/pipelines/p03/test_r0_integration.py` | #46-58 | P1 |
| `tests/k0/pipelines/p03/test_status_writeback.py` | #59-67 | P1 |
| `tests/k0/pipelines/p03/test_gap_emitter_integration.py` | #68-80 | P1 |
| `tests/k0/pipelines/p03/test_feedback_consumer_integration.py` | #81-97 | P1 |
| `tests/k0/pipelines/p03/test_full_pipeline_e2e.py` | #98-107 | P0 (most critical) |

---

## Implementation Order

1. **Phase 1 — Core Integration** (P1)
   - `test_r0_integration.py` (#46-58)
   - `test_status_writeback.py` (#59-67)
   - `test_gap_emitter_integration.py` (#68-80)
   - `test_feedback_consumer_integration.py` (#81-97)

2. **Phase 2 — R7/R8 Extension** (P1)
   - Extend `test_r7_r8_integration.py` (#21-45)

3. **Phase 3 — E2E Tests** (P0)
   - `test_full_pipeline_e2e.py` (#98-107)

4. **Phase 4 — Foundation Tests** (P2)
   - `test_envelope_integration.py` (#1-8)
   - Verify `test_storage_migrations.py` (#9-20)

---

## Dependencies

```
test_full_pipeline_e2e.py
    ├── test_r0_integration.py
    ├── test_r7_r8_integration.py
    │   ├── test_status_writeback.py
    │   └── test_gap_emitter_integration.py
    └── test_feedback_consumer_integration.py
```

---

## Fixtures Required

| Fixture | Location | Used By |
|---------|----------|---------|
| `db_session` | `conftest.py` | All DB tests |
| `mock_uow` | `conftest.py` | R7/R8 tests |
| `mock_bus` | `conftest.py` | Outbox/feedback tests |
| `staged_envelope` | `conftest.py` | R7 tests |
| `envelope_with_gaps` | `conftest.py` | Gap emitter tests |
| `gap_signal` | `conftest.py` | Gap tests |
| `feedback_message` | `conftest.py` | Feedback tests |
| `mock_runner_context` | `conftest.py` | All phase tests |

---

*Document created: 2026-01-01*
*Last updated: 2026-01-01*
