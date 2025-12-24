# PostgreSQL Migration Test Fix Plan

**Status:** 1941 passed, 224 failed (as of 2024-12-23)
**Goal:** Get all tests passing with new PostgreSQL backend

---

## Milestone 1: Core Infrastructure Tests (Est: 2 hours)

### Epic 1.1: Gate & Schema Registry Tests (62 tests)
Database async/await pattern changes for PostgreSQL.

**Issue 1.1.1: Gate Validation Tests** (35 tests)
- File: `tests/k0/gate/test_minimal_gate_validation.py`
- Root Cause: Tests not awaiting async functions, mock setup incorrect for asyncpg
- Tests:
  - `test_validate_success_complete_flow`
  - `test_validate_canonicalization_error`
  - `test_validate_envelope_too_large`
  - `test_validate_body_required`
  - `test_validate_body_too_large`
  - `test_validate_body_type_error`
  - `test_validate_missing_bindings`
  - `test_validate_clock_skew_excessive`
  - `test_validate_device_not_provisioned`
  - `test_validate_space_mismatch`
  - `test_validate_schema_not_active`
  - `test_validate_schema_deprecated`
  - `test_validate_schema_blocked`
  - `test_validate_payload_hash_missing`
  - `test_validate_payload_hash_mismatch`
  - `test_validate_payload_hash_invalid_format`
  - `test_validate_signature_missing`
  - `test_validate_no_valid_keys`
  - `test_validate_revoked_key`
  - `test_validate_signature_invalid`
  - `test_validate_envelope_sha256_mismatch`
  - `test_validate_envelope_replay_detected`
  - `test_validate_idempotency_key_mismatch`
  - `test_validate_location_missing_for_amber`
  - `test_validate_policy_stamp_invalid`
  - `test_check_envelope_replay_no_connection`
  - `test_check_envelope_replay_not_found`
  - `test_check_envelope_replay_found`
  - `test_get_device_secret_success`
  - `test_get_device_secret_not_found`
  - `test_cached_provisioning_lookup_hit`
  - `test_cached_provisioning_lookup_miss`
  - `test_cached_schema_get_hit`
  - `test_cached_schema_get_miss`

**Issue 1.1.2: Schema Registry Tests** (26 tests)
- File: `tests/k0/gate/test_schema_registry.py`
- Root Cause: Async functions not awaited, connection pool mock issues
- Tests:
  - `test_clear_cache`
  - `test_load_empty_registry`
  - `test_load_with_schemas`
  - `test_load_with_metrics`
  - `test_get_cache_hit`
  - `test_get_cache_miss_found_in_db`
  - `test_get_not_found`
  - `test_register_success`
  - `test_register_duplicate`
  - `test_register_invalid_record`
  - `test_upsert_insert`
  - `test_upsert_update`
  - `test_promote_to_active`
  - `test_promote_with_demotion`
  - `test_promote_blocked_schema`
  - `test_promote_not_found`
  - `test_block_success`
  - `test_block_empty_operator_id`
  - `test_block_empty_reason`
  - `test_block_not_found`
  - `test_get_audit_trail_all`
  - `test_get_audit_trail_filtered_by_uri`
  - `test_get_audit_trail_filtered_by_status`
  - `test_get_audit_trail_version_requires_uri`
  - `test_store_record`
  - `test_refresh_uri_cache`

### Epic 1.2: Idempotency Ledger Tests (9 tests)
**Issue 1.2.1: Ledger Operations**
- File: `tests/k0/idem/test_ledger_operations.py`
- Root Cause: Async functions not awaited
- Tests:
  - `test_lookup_missing_key`
  - `test_lookup_existing_key`
  - `test_lookup_with_expiry`
  - `test_upsert_new_entry`
  - `test_upsert_updates_existing`
  - `test_upsert_with_expiry`
  - `test_pending_state`
  - `test_committed_state`
  - `test_state_transition`

### Epic 1.3: Kernel & Pipeline Tests (10 tests)
**Issue 1.3.1: Kernel Pipeline Integration**
- File: `tests/k0/kernel/test_app_pipeline_integration.py`
- Root Cause: Async startup/shutdown patterns changed
- Tests:
  - `test_kernel_boots_with_empty_pipelines_directory`
  - `test_kernel_boots_with_valid_pipeline`
  - `test_kernel_graceful_shutdown_calls_pipeline_shutdown`
  - `test_kernel_records_clean_shutdown_timestamp`
  - `test_kernel_handles_pipeline_on_shutdown_errors`
  - `test_kernel_handles_pipeline_discovery_errors`

**Issue 1.3.2: FAISS Syscall Tests**
- File: `tests/k0/kernel/test_syscalls_faiss.py`
- Root Cause: NotImplementedError expectations changed
- Tests:
  - `test_faiss_add_raises_not_implemented`
  - `test_faiss_add_batch_raises_not_implemented`
  - `test_faiss_search_raises_not_implemented`
  - `test_faiss_remove_batch_raises_not_implemented`

---

## Milestone 2: Module Signature Updates (Est: 3 hours)

### Epic 2.1: Embedding Module Tests (~50 tests)
Module `run()` signature changed from `run(envelope, enriched, context)` to `run(message, context, **config)`

**Issue 2.1.1: extract_from_cache Tests** (23 tests)
- File: `tests/k0/modules/embedding/test_extract_from_cache.py`
- Fix: Update all test calls to new signature

**Issue 2.1.2: embedding_write Tests** (16 tests)
- File: `tests/k0/modules/builders/test_embedding_write.py`
- Fix: Update all test calls to new signature

**Issue 2.1.3: faiss_indexer Tests** (20 tests)
- File: `tests/k0/modules/embedding/test_faiss_indexer.py`
- Fix: Update all test calls to new signature

### Epic 2.2: Context Module Tests (~15 tests)
**Issue 2.2.1: ingress_classify Tests**
- File: `tests/k0/modules/context/test_ingress_classify.py`
- Fix: Update test assertions for classification results

**Issue 2.2.2: spatial_minimal Tests**
- File: `tests/k0/modules/context/test_spatial_minimal.py`
- Fix: Geohash computation returning None - check policy stamp handling

### Epic 2.3: Core Module Tests (~20 tests)
**Issue 2.3.1: event_emitter Tests**
- File: `tests/k0/modules/core/test_event_emitter.py`
- Root Cause: RuntimeError: coroutine raised StopIteration
- Fix: Update async iterator handling

**Issue 2.3.2: hipp_events_row Tests**
- File: `tests/k0/modules/builders/test_hipp_events_row.py`
- Root Cause: KeyError: 'embedding_model_id'
- Fix: Add missing enrichment field

---

## Milestone 3: Policy & ACL Tests (Est: 2 hours)

### Epic 3.1: ACL Enforcer Tests (~18 tests)
**Issue 3.1.1: Missing await on coroutines**
- File: `tests/k0/policy/test_acl_enforcer_edge_cases.py`
- Root Cause: Tests comparing coroutine objects instead of awaited results
- Fix: Add `await` to all async function calls

### Epic 3.2: Retention Enforcer Tests (~8 tests)
**Issue 3.2.1: Coroutine handling**
- File: `tests/k0/policy/test_retention_enforcer.py`
- Fix: Add `await` to async function calls

---

## Milestone 4: Receipt & Runtime Tests (Est: 1 hour)

### Epic 4.1: Receipt Audit Tests (~12 tests)
**Issue 4.1.1: Coroutine attribute access**
- File: `tests/k0/receipts/test_receipt_audit_fields.py`
- Root Cause: AttributeError on coroutine objects
- Fix: Await ReceiptIssuer.issue() calls

### Epic 4.2: Runtime Schema Tests (~5 tests)
**Issue 4.2.1: P02 Parallel Execution**
- File: `tests/k0/runtime/test_p02_parallel_execution.py`
- Root Cause: KeyError: 'embedding.extract_from_cache:v1'
- Fix: Register module in test fixtures

**Issue 4.2.2: Trigger Schema Tests**
- File: `tests/k0/runtime/test_schemas_trigger.py`
- Root Cause: Idle trigger field None vs expected 1
- Fix: Update test expectations

---

## Milestone 5: Contract Value Updates (Est: 30 min)

### Epic 5.1: P08 Trigger Contract Tests (2 tests)
**Issue 5.1.1: Config value mismatches**
- File: `tests/contracts/test_p08_triggers.py`
- Root Cause: interval_seconds 30 != 300, threshold_count 5 != 50
- Fix: Update test assertions or contract values

---

## Execution Order

1. **Epic 1.1** - Gate tests (critical path for security)
2. **Epic 1.2** - Ledger tests (critical for idempotency)
3. **Epic 3.1** - ACL tests (simple await fixes)
4. **Epic 4.1** - Receipt tests (simple await fixes)
5. **Epic 2.1** - Embedding module tests (signature changes)
6. **Epic 5.1** - Contract value tests (quick fix)
7. Remaining epics

---

## Quick Fix Categories

### Category A: Missing `await` (~50 tests)
Pattern: `assert result.field` should be `result = await func(); assert result.field`
Files:
- test_acl_enforcer_edge_cases.py
- test_retention_enforcer.py
- test_receipt_audit_fields.py
- test_ledger_operations.py

### Category B: Module Signature Change (~50 tests)
Pattern: `run(envelope, enriched, context)` → `run(envelope, context)`
Files:
- test_extract_from_cache.py
- test_embedding_write.py
- test_faiss_indexer.py

### Category C: Mock Setup for asyncpg (~35 tests)
Pattern: Update connection mock from sqlite to asyncpg patterns
Files:
- test_minimal_gate_validation.py
- test_schema_registry.py

### Category D: Assertion Value Updates (~10 tests)
Pattern: Update expected values to match new config
Files:
- test_p08_triggers.py
- test_schemas_trigger.py
