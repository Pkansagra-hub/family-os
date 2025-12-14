---
adr_number: 'K002'
affected_layers:
- layer5_infrastructure
- layer4_runtime
affected_modules:
- k0.ports.command
- k0.idem.ledger
- k0.uow.unit_of_work
authors:
- K0 Architecture Team
concerns:
- data-integrity
- concurrency
- security
date_created: '2025-11-11'
date_updated: '2025-11-11'
implementation_date: null
implementation_phase: 'V1 Launch'
implementation_status: IN_PROGRESS
propagation:
  affected_adrs:
  - K001
  affected_contracts:
  - k0/contracts/sql/storage.sql
  affected_tests:
  - tests/k0/integration/test_command_idempotency.py
  - tests/k0/integration/test_concurrent_idempotency.py
  triggers:
  - Gap 27 discovered in Pass 2 race condition analysis
  - CRITICAL data corruption bug under concurrent load
  - Production blocker for V1 launch
related_adrs:
- K001
related_contracts:
- k0/contracts/sql/storage.sql
related_diagrams:
- docs/envelope_movement/envelope_write_path.md
research_citations:
- 'TOCTOU vulnerabilities (Bishop & Dilger, 1996)'
- 'SQLite transaction isolation levels'
- 'Idempotent REST API design (Stripe API)'
status: ACCEPTED
superseded_by: []
supersedes: []
title: Fix Idempotency Check-Then-Act TOCTOU Race Condition
---

# ADR-K002: Fix Idempotency Check-Then-Act TOCTOU Race Condition

**Status**: Accepted

**Date**: 2025-11-11

**Authors**: @K0-Architecture-Team

## Context

### Problem Statement

**CRITICAL BUG DISCOVERED**: Pass 2 race condition analysis identified a classic Time-of-Check-Time-of-Use (TOCTOU) race in the idempotency system that allows duplicate commits under concurrent load.

**Current Implementation** (`k0/ports/command.py` lines 293-332):

```python
# CHECK: Idempotency lookup OUTSIDE transaction
with connection_scope() as gate_connection:  # ❌ READ-ONLY CONNECTION!
    outcome = minimal_gate.validate(...)
    idem_key = outcome.idem_key

    # CHECK: Read idempotency ledger
    duplicate = idem_ledger.lookup(idem_key, connection=gate_connection)
    if duplicate is not None:
        return 409_CONFLICT  # Early exit
    # ... exits connection scope ...

# ❌ GAP: No transaction held between CHECK and USE!

# Later in code (line 620+):
with unit_of_work_factory() as uow:  # ✅ NEW TRANSACTION!
    # USE: Insert into idempotency ledger
    ledger_entry = LedgerEntry(idem_key=idem_key, ...)
    idem_ledger.upsert(ledger_entry, connection=uow.connection)
    uow.commit()
```

### Race Condition Scenario

**Timeline with 2 concurrent requests for same idem_key**:

```
T0: Request A: CHECK idempotency ledger → NOT FOUND ✅
T1: Request B: CHECK idempotency ledger → NOT FOUND ✅ (A hasn't committed yet)
T2: Request A: USE - Insert into ledger + WAL commit ✅
T3: Request B: USE - Insert into ledger + WAL commit ✅ ❌ DUPLICATE!
```

**Result**: Both requests commit! WAL contains duplicate entries!

### Impact Analysis

| Impact Area | Severity | Description |
|-------------|----------|-------------|
| **Data Corruption** | CRITICAL | Duplicate WAL entries violate exactly-once semantics |
| **Receipt Duplication** | CRITICAL | Two receipts issued for same idem_key |
| **Financial Loss** | CRITICAL | Duplicate payments, duplicate resource allocation |
| **Audit Trail Broken** | CRITICAL | Cannot prove exactly-once guarantee to regulators |
| **Customer Trust** | CRITICAL | Duplicate operations (e.g., 2x money transfers) |

**Likelihood**: HIGH under load (100+ concurrent requests with same idem_key)

### Business Drivers

- **V1 Production Launch**: P0 blocker - cannot ship with data corruption bug
- **Financial Safety**: Money transfer APIs must guarantee exactly-once
- **Regulatory Compliance**: ACID guarantees required for audit trail
- **Performance**: Fix must not degrade latency (target <100ms P95)

### Constraints

- **Single-Writer SQLite**: Must use transaction isolation correctly
- **Latency Budget**: 100ms P95 for command.submit
- **Backward Compatibility**: Existing idempotency behavior must be preserved
- **Testing**: Must verify fix with concurrent stress test

## Decision

**Move idempotency CHECK inside UnitOfWork transaction to eliminate TOCTOU race.**

### Implementation Strategy

**Option 1: Check-Then-Insert within Single Transaction (CHOSEN)**

```python
# k0/ports/command.py - FIX:
with unit_of_work_factory() as uow:  # ✅ Single transaction!
    # CHECK: Lookup idempotency ledger within transaction
    duplicate = idem_ledger.lookup(idem_key, connection=uow.connection)
    if duplicate is not None:
        # Duplicate detected - rollback and return 409
        uow.rollback()
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "receipt_id": duplicate.receipt_id,
                "commit_ts": duplicate.first_seen_ts,
                "idem_key": duplicate.idem_key,
            },
        )

    # No duplicate - proceed with WAL commit
    wal_pos = uow.append_wal(wal_entry)

    # ... other work ...

    # USE: Insert into idempotency ledger (protected by transaction)
    ledger_entry = LedgerEntry(idem_key=idem_key, ...)
    idem_ledger.upsert(ledger_entry, connection=uow.connection)

    # Atomic commit of WAL + receipts + idempotency ledger
    uow.commit()  # If duplicate inserted concurrently, UNIQUE constraint fails
```

**Why This Works:**

1. **Single Transaction Scope**: Both CHECK and USE happen within `BEGIN IMMEDIATE...COMMIT`
2. **SQLite Locking**: `BEGIN IMMEDIATE` acquires write lock, preventing concurrent writes
3. **UNIQUE Constraint Defense**: `idem_ledger.idem_key PRIMARY KEY` provides DB-level enforcement
4. **Atomic Rollback**: If duplicate detected after lock acquired, clean rollback

**Database Schema Guarantee** (`k0/contracts/sql/storage.sql`):

```sql
CREATE TABLE IF NOT EXISTS idem_ledger (
  idem_key TEXT PRIMARY KEY,  -- ✅ UNIQUE constraint enforced
  receipt_id TEXT NOT NULL,
  first_seen_ts TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('COMMITTED','REJECTED')),
  expiry_ts TEXT
);
```

### Migration Strategy

**Phase 1: Refactor `k0/ports/command.py`**

1. Remove idempotency lookup from `connection_scope()` block (lines 293-332)
2. Move lookup inside `unit_of_work_factory()` transaction (after line 620)
3. Add early return on duplicate detection within transaction
4. Preserve telemetry emission for duplicate detection

**Phase 2: Update Tests**

1. Create new integration test: `test_concurrent_idempotency_race_condition`
2. Test: 100 concurrent requests with same idem_key → exactly 1 commit
3. Verify: Second request receives 409 CONFLICT with original receipt
4. Measure: Latency impact (target <5ms increase)

**Phase 3: Validation**

1. Run existing idempotency tests to verify no regressions
2. Run concurrency stress test with 1000 concurrent requests
3. Verify metrics: `k0_idem_duplicate_detected` correctly emitted
4. Check observability events for duplicate detection

## Consequences

### Positive

- ✅ **TOCTOU Race Eliminated**: Atomic CHECK+USE within single transaction
- ✅ **Data Integrity Restored**: Exactly-once semantics guaranteed by SQLite isolation
- ✅ **UNIQUE Constraint Defense**: Database-level enforcement as last line of defense
- ✅ **Audit Trail Intact**: No duplicate receipts, proper 409 responses
- ✅ **Concurrency Safe**: SQLite `BEGIN IMMEDIATE` prevents concurrent writes
- ✅ **Minimal Code Change**: ~30 lines moved, no new dependencies

### Negative

- ⚠️ **Longer Transaction Hold Time**: Idempotency check now holds write lock
- ⚠️ **Slight Latency Increase**: +2-5ms for idempotency lookup within transaction
- ⚠️ **Contention Risk**: Multiple concurrent requests will serialize at transaction start

### Risks & Mitigation

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| **Transaction timeout under high load** | LOW | SQLite `PRAGMA busy_timeout=5000` allows 5s retry |
| **Performance regression** | LOW | Idempotency lookup is single-row SELECT (< 1ms) |
| **Deadlock with other transactions** | VERY LOW | K0 is single-writer; no distributed transactions |
| **Backward compatibility break** | NONE | Behavior unchanged for clients |

### Performance Impact Analysis

**Expected Latency Changes**:

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Idempotency lookup | 1ms (outside txn) | 1ms (inside txn) | 0ms |
| Transaction acquire | 0ms | +2-3ms (IMMEDIATE lock) | +2-3ms |
| **Total P95 Latency** | ~85ms | ~88ms | +3ms |

**Verdict**: Well within 100ms P95 budget (12ms headroom)

## Alternatives Considered

### Alternative 1: UNIQUE Constraint Only (No Pre-Check)

**Approach**: Remove idempotency lookup entirely, rely on SQLite UNIQUE constraint

```python
try:
    with unit_of_work_factory() as uow:
        # Skip lookup, just insert
        ledger_entry = LedgerEntry(idem_key=idem_key, ...)
        idem_ledger.upsert(ledger_entry, connection=uow.connection)
        uow.append_wal(wal_entry)
        uow.commit()
except sqlite3.IntegrityError:
    # Duplicate detected by database
    duplicate = idem_ledger.lookup(idem_key)
    return 409_CONFLICT with duplicate receipt
```

**Rejected Because**:
- ❌ **WAL Entry Wasted**: WAL append happens before integrity error detected
- ❌ **Poor UX**: Exception-driven flow is harder to debug
- ❌ **Rollback Overhead**: Must rollback entire transaction on duplicate
- ❌ **Less Observable**: Harder to emit telemetry on duplicate detection

### Alternative 2: Application-Level Lock

**Approach**: Use Python `threading.Lock` per idem_key

```python
_IDEM_LOCKS: dict[str, threading.Lock] = {}

def _acquire_idem_lock(idem_key: str) -> threading.Lock:
    if idem_key not in _IDEM_LOCKS:
        _IDEM_LOCKS[idem_key] = threading.Lock()
    return _IDEM_LOCKS[idem_key]

with _acquire_idem_lock(idem_key):
    # Check and commit atomically
    pass
```

**Rejected Because**:
- ❌ **Distributed System**: Won't work in multi-process deployment
- ❌ **Memory Leak**: Lock dictionary grows unbounded
- ❌ **Complexity**: Introduces new concurrency primitive
- ❌ **SQLite Sufficient**: Database already provides transaction isolation

### Alternative 3: Optimistic Concurrency Control

**Approach**: Add `version` field to `idem_ledger`, use CAS (Compare-And-Swap)

**Rejected Because**:
- ❌ **Overkill**: Not needed for INSERT-only workload
- ❌ **Schema Change**: Requires migration for `version` column
- ❌ **Retry Logic**: Clients must handle retry storms
- ❌ **Pessimistic Better**: `BEGIN IMMEDIATE` is simpler for single-writer

## Implementation Notes

### Phasing Strategy

**Week 1 (This Sprint)**:
1. **Day 1**: Create ADR (this document) + review with team
2. **Day 2**: Refactor `k0/ports/command.py` (move idempotency check)
3. **Day 3**: Create concurrent stress test (100 concurrent requests)
4. **Day 4**: Run full test suite + performance benchmarks
5. **Day 5**: Code review + merge to `k0-Strengthning` branch

**Week 2 (V1 Launch Prep)**:
1. Deploy to staging environment
2. Run load tests (1000 req/s for 1 hour)
3. Verify metrics/observability
4. Production rollout with monitoring

### Testing Requirements

**New Test**: `tests/k0/integration/test_concurrent_idempotency.py`

```python
@test("100 concurrent requests with same idem_key result in exactly 1 commit")
def test_concurrent_idempotency_race():
    """
    Verify TOCTOU race is fixed:
    - 100 threads submit same envelope concurrently
    - Exactly 1 commit to WAL
    - 99 requests receive 409 CONFLICT with same receipt_id
    - No duplicate receipts in st_receipts
    """
    # Implementation details in test file
```

**Performance Test**: Measure P95 latency before/after fix

**Stress Test**: 1000 concurrent requests for 60 seconds

### Rollback Plan

**If latency regression > 10ms**:
1. Revert commit to restore old behavior
2. Investigate alternative: Two-phase locking with advisory locks
3. Re-test with optimized SQLite settings (`PRAGMA journal_mode=WAL2`)

**If UNIQUE constraint fails unexpectedly**:
1. Add defensive logging around `idem_ledger.upsert()`
2. Investigate SQLite version compatibility
3. Fallback: Use `INSERT OR IGNORE` pattern

## References

- **Gap Analysis**: `docs/k0_architecture_gaps_analysis.md` (Gap 27, lines 1516-1666)
- **Related ADR**: ADR-K001 (Write Pipeline V1 Hardening)
- **Schema Contract**: `k0/contracts/sql/storage.sql` (idem_ledger table)
- **Current Implementation**: `k0/ports/command.py` (lines 293-332, 620+)
- **UnitOfWork**: `k0/uow/unit_of_work.py` (transaction management)
- **Idempotency Ledger**: `k0/idem/ledger.py` (lookup/upsert methods)
- **Research**:
  - Bishop & Dilger (1996): "Checking for Race Conditions in File Accesses"
  - SQLite Documentation: "Transaction Isolation in WAL Mode"
  - Stripe API Design: "Idempotent Requests Best Practices"

## Revision History

- 2025-11-11: Initial draft (@K0-Architecture-Team)
- 2025-11-11: Accepted (P0 CRITICAL fix for V1 launch)
