# Gap 27: Idempotency TOCTOU Race - Runbook

**Priority**: P0 - CRITICAL BLOCKER
**Component**: `k0/ports/command.py`, `k0/idem/derive.py`
**Issue**: [#001](https://github.com/Pkansagra-hub/family-os/issues/001)
**Alert**: `IdempotencyDuplicateCommitCritical`

---

## Symptoms

### Alert Firing
- **Alert Name**: `IdempotencyDuplicateCommitCritical`
- **Trigger**: `increase(k0_idem_toctou_race_detected_total[5m]) >= 5`
- **Severity**: CRITICAL (P0)
- **Dashboard**: [P0 Blocker Dashboard - Panel 1](http://localhost:3000/d/p0-blockers)

### Observable Behavior
- Multiple WAL commits with same `idem_key` (duplicate events)
- Data corruption: Same command executed twice
- Metric: `k0_idem_toctou_race_detected_total` increasing
- Receipts table shows duplicate sequence numbers for same operation

### User Impact
- **CRITICAL**: Data corruption possible
- Commands may be executed multiple times (e.g., double charges, duplicate records)
- Loss of exactly-once semantics guarantee
- Potential financial impact if commands involve transactions

---

## Investigation

### Step 1: Verify Alert and Scope
```bash
# Check current TOCTOU race count
curl -s http://localhost:9090/api/v1/query?query=k0_idem_toctou_race_detected_total | jq '.data.result[0].value[1]'

# Check rate of races (last 5 minutes)
curl -s http://localhost:9090/api/v1/query?query=increase(k0_idem_toctou_race_detected_total[5m]) | jq '.data.result[0].value[1]'

# Check concurrent idempotency checks
curl -s http://localhost:9090/api/v1/query?query=k0_idem_concurrent_checks_active | jq '.data.result[0].value[1]'
```

### Step 2: Identify Affected Tenants
```sql
-- Query idem_ledger for duplicate keys (created within same second)
SELECT
    idem_key,
    COUNT(*) as duplicate_count,
    MIN(created_ts) as first_commit,
    MAX(created_ts) as last_commit,
    MAX(created_ts) - MIN(created_ts) as race_window_ms
FROM idem_ledger
GROUP BY idem_key
HAVING COUNT(*) > 1
ORDER BY race_window_ms ASC
LIMIT 10;
```

### Step 3: Check WAL for Duplicates
```sql
-- Find duplicate WAL entries
SELECT
    w1.seq,
    w2.seq,
    w1.aggregate_id,
    w1.event_type,
    w1.ts,
    (w2.ts - w1.ts) as duplicate_delay_ms
FROM wal w1
JOIN wal w2 ON w1.aggregate_id = w2.aggregate_id
    AND w1.event_type = w2.event_type
    AND w1.seq < w2.seq
WHERE (w2.ts - w1.ts) < 1000  -- Duplicates within 1 second
ORDER BY duplicate_delay_ms ASC;
```

### Step 4: Analyze Transaction Timing
```bash
# Check idempotency check-commit window (should be < 100ms)
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,%20rate(k0_idem_check_commit_window_seconds_bucket[5m]))' | jq '.data.result[0].value[1]'

# If > 0.1 (100ms), TOCTOU race window is too large
```

---

## Mitigation

### Immediate Actions (< 5 minutes)

#### Option 1: Enable Gap 27 Fix (if available)
```bash
# Enable TOCTOU fix via feature flag
export K0_TOCTOU_FIX_ENABLED=true

# Restart kernel
docker-compose -f k0/deploy/docker-compose.yml restart k0-kernel
```

#### Option 2: Reduce Concurrency (if fix not deployed)
```bash
# Reduce max concurrent requests to minimize race window
# Edit k0/config/kernel.yml
max_concurrent_requests: 10  # Down from 100

# Restart kernel
docker-compose -f k0/deploy/docker-compose.yml restart k0-kernel
```

#### Option 3: Enable Request Serialization (emergency)
```bash
# Force single-threaded command processing (SEVERE PERFORMANCE IMPACT)
export K0_COMMAND_SERIALIZE=true
docker-compose -f k0/deploy/docker-compose.yml restart k0-kernel
```

### Data Cleanup (< 15 minutes)

```sql
-- CRITICAL: Identify and quarantine duplicate events
-- DO NOT DELETE - preserve for forensics

-- 1. Mark duplicate WAL entries
UPDATE wal
SET metadata = json_set(metadata, '$.duplicate', 'true')
WHERE seq IN (
    SELECT w2.seq
    FROM wal w1
    JOIN wal w2 ON w1.aggregate_id = w2.aggregate_id
        AND w1.event_type = w2.event_type
        AND w1.seq < w2.seq
    WHERE (w2.ts - w1.ts) < 1000
);

-- 2. Create incident report
INSERT INTO incidents (
    incident_id,
    type,
    severity,
    gap_number,
    detected_ts,
    affected_count,
    metadata
) VALUES (
    'INC-' || strftime('%Y%m%d%H%M%S', 'now'),
    'TOCTOU_RACE',
    'P0_CRITICAL',
    27,
    unixepoch('now', 'subsec') * 1000,
    (SELECT COUNT(*) FROM wal WHERE json_extract(metadata, '$.duplicate') = 'true'),
    json_object(
        'duplicate_wals', (SELECT GROUP_CONCAT(seq) FROM wal WHERE json_extract(metadata, '$.duplicate') = 'true'),
        'investigation_status', 'IN_PROGRESS'
    )
);
```

### Communication

**Slack Notification** (`#k0-alerts-sre`):
```
🚨 P0 BLOCKER: Gap 27 TOCTOU race detected
- Alert: IdempotencyDuplicateCommitCritical
- Duplicates: [X] events in last 5 minutes
- Mitigation: [In Progress / Completed]
- Estimated Impact: [X] tenants affected
- Incident ID: INC-YYYYMMDDHHMMSS
- Runbook: https://docs.example.com/runbooks/gaps/gap-27-toctou-race/
```

---

## Root Cause

### Technical Explanation
**Time-of-Check to Time-of-Use (TOCTOU) Race Condition**

```python
# VULNERABLE CODE (before Gap 27 fix):
# Step 1: Check idempotency (OUTSIDE transaction)
existing = idem_store.get(idem_key)  # Thread 1: None, Thread 2: None (race!)

if existing:
    return 409  # Duplicate

# Step 2: Begin transaction
with unit_of_work_factory() as uow:
    # Step 3: Append to WAL
    uow.wal.append(event)

    # Step 4: Record idempotency (INSIDE transaction, but TOO LATE)
    uow.idem_ledger.insert(idem_key)

    uow.commit()  # Thread 1 commits, Thread 2 also commits (DUPLICATE!)
```

**Race Window**:
- **Thread 1**: Check idem_key at T=0ms (not found) → Commit at T=50ms
- **Thread 2**: Check idem_key at T=5ms (not found, race!) → Commit at T=55ms
- **Result**: Both threads see "not found" and both commit

### Why It Happens
1. Idempotency check happens **outside** UnitOfWork transaction
2. Race window between check (T1) and commit (T2) = 50-100ms typically
3. High concurrency (100+ req/s) increases probability
4. SQLite WAL mode allows concurrent reads, enabling race

### Gap 27 Fix
Move idempotency check **inside** transaction:
```python
# FIXED CODE (after Gap 27 fix):
with unit_of_work_factory() as uow:
    # Step 1: Check idempotency INSIDE transaction (atomic)
    existing = uow.idem_ledger.get(idem_key)

    if existing:
        return 409  # Duplicate

    # Step 2: Append to WAL + record idempotency (single transaction)
    uow.wal.append(event)
    uow.idem_ledger.insert(idem_key)  # UNIQUE constraint prevents duplicates

    uow.commit()  # Atomic: both WAL and idem_ledger updated together
```

**Result**: UNIQUE constraint on `idem_ledger.idem_key` prevents duplicates at database level.

---

## Long-Term Fix

### Implementation Status
- **Issue**: [#001 - Fix Idempotency TOCTOU Race](https://github.com/Pkansagra-hub/family-os/issues/001)
- **ADR**: ADR-XXXX (Transaction Boundary Change)
- **Target**: Milestone 1 - Week 1-2
- **Effort**: 6-8 hours

### Acceptance Criteria
- [ ] Idempotency lookup inside UnitOfWork transaction
- [ ] UNIQUE constraint on `idem_ledger.idem_key`
- [ ] Integration test: 100 concurrent requests with same idem_key → exactly 1 commit
- [ ] Metric `k0_idem_toctou_race_detected_total` stops increasing
- [ ] Alert `IdempotencyDuplicateCommitCritical` resolves

### Verification
```bash
# Run integration test
pytest tests/k0/idem/test_toctou_fix.py -v

# Expected output:
# test_concurrent_duplicate_idem_key ... PASSED (100 requests, 1 commit, 99 conflicts)
```

---

## Related Documentation

- [K0 Implementation Roadmap - Milestone 1](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_implementation_roadmap.md#epic-11-transaction-safety--resource-management-16-20h)
- [Gap 27 Analysis](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_architecture_gaps_analysis.md#gap-27-idempotency-toctou-race)
- [P0 Blocker Dashboard](http://localhost:3000/d/p0-blockers)
- [Idempotency Design](https://github.com/Pkansagra-hub/family-os/blob/main/k0/idem/README.md)

---

## Incident History

| Date | Duration | Affected | Root Cause | Resolution |
|------|----------|----------|------------|------------|
| 2025-11-11 | - | TBD | Gap 27 not yet fixed | Awaiting implementation |

---

**Last Updated**: 2025-11-11
**Document Owner**: SRE Team
**Review Frequency**: Weekly until Gap 27 resolved
