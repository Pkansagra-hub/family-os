# Runbook: Gap 27 - Idempotency TOCTOU Race Condition

**Priority**: P0 (CRITICAL)
**Component**: `k0/ports/command.py`, `k0/idem/`
**Alert**: `K0IdempotencyTOCTOURaceDetected`
**Related ADRs**: ADR-K002 (Idempotency Key Design)

---

## Symptoms

- Alert: `k0_idem_toctou_race_detected_total` metric increasing
- Duplicate WAL entries with same `idem_key` but different `position`
- Data corruption: Same command persisted multiple times
- Inconsistent receipt generation for duplicate requests

## Root Cause

Race condition in idempotency check:
1. Thread A checks idempotency table OUTSIDE transaction → Key not found
2. Thread B checks idempotency table OUTSIDE transaction → Key not found
3. Thread A enters UoW transaction, inserts entry
4. Thread B enters UoW transaction, inserts entry (DUPLICATE)

**Time-of-Check to Time-of-Use (TOCTOU) gap**: Check outside transaction, insert inside transaction.

---

## Investigation Steps

### 1. Verify Race Detection
```bash
# Check current race rate
curl http://localhost:9090/metrics | grep idem_toctou_race_detected_total

# Check concurrent check gauge (should be low, < 5)
curl http://localhost:9090/metrics | grep idem_concurrent_checks_gauge
```

**Expected**: `k0_idem_concurrent_checks_gauge` < 5
**Alert Threshold**: Race rate > 0 for 1m

### 2. Identify Racing Requests
```bash
# Query logs for racing idem_keys
kubectl logs -l app=k0-kernel --since=10m | grep "TOCTOU race detected"

# Example log output:
# {"level":"warning","idem_key":"idem:abc123","age_ms":450,"msg":"TOCTOU race detected"}
```

**Key Fields**:
- `idem_key`: Duplicate key that raced
- `age_ms`: Time since idempotency entry created (< 1000ms indicates race)
- `cognitive_trace_id`: Trace ID for racing request

### 3. Check Clock Skew
```bash
# Verify NTP sync on all nodes
for node in $(kubectl get nodes -o name); do
  kubectl debug $node -it --image=nicolaka/netshoot -- chronyc tracking
done

# Look for:
# - System time offset > 500ms (indicates skew)
# - Leap status not "Normal" (indicates NTP issues)
```

### 4. Analyze WAL Duplicates
```sql
-- Connect to SQLite database
sqlite3 /data/k0.db

-- Find duplicate idem_keys in WAL
SELECT idem_key, COUNT(*) as duplicate_count, GROUP_CONCAT(position) as positions
FROM wal
WHERE idem_key IS NOT NULL
GROUP BY idem_key
HAVING duplicate_count > 1
ORDER BY duplicate_count DESC
LIMIT 20;

-- Check timing of duplicates
SELECT position, idem_key, commit_ts,
       (julianday(commit_ts) - LAG(julianday(commit_ts)) OVER (PARTITION BY idem_key ORDER BY position)) * 86400000 as gap_ms
FROM wal
WHERE idem_key IN (SELECT idem_key FROM wal GROUP BY idem_key HAVING COUNT(*) > 1)
ORDER BY idem_key, position;
```

**Expected**: `gap_ms` < 1000 indicates concurrent race

---

## Mitigation Steps

### Immediate Actions (< 5 minutes)

#### 1. Enable HMAC Idempotency (Gap 2 Fix)
```bash
# Verify HMAC idempotency is enabled
kubectl exec -it k0-kernel-0 -- sqlite3 /data/k0.db \
  "SELECT COUNT(*) FROM pragma_table_info('provisioning_ledger') WHERE name='hmac_secret';"

# If 0, HMAC not enabled → Deploy Gap 2 fix immediately
kubectl apply -f k0/deploy/migrations/0002_add_hmac_secret.sql
```

**Why**: HMAC-based keys use 60-second time buckets, reducing collision window vs. BLAKE3 content-based keys.

#### 2. Check Transaction Isolation
```python
# Verify idempotency check is INSIDE transaction (line 643+ in command.py)
grep -A 10 "Check idempotency INSIDE transaction" k0/ports/command.py

# Expected output:
# # ADR-K002: Check idempotency INSIDE transaction to prevent TOCTOU race
# existing_entry = check_idempotency_in_transaction(...)
```

#### 3. Restart High-Concurrency Pods
```bash
# If concurrent checks gauge > 10, restart pods to clear backlog
kubectl rollout restart deployment k0-kernel
```

### Short-Term Fixes (< 1 hour)

#### 4. Increase Time Bucket Granularity (if clock skew detected)
```yaml
# k0/config/idempotency.yml
idem:
  time_bucket_seconds: 120  # Increase from 60 to 120 seconds
  max_clock_skew_ms: 5000   # Increase tolerance
```

**Why**: Wider time buckets reduce false negatives from clock skew.

#### 5. Enable Circuit Breaker
```yaml
# k0/config/qos.yml
qos:
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    timeout_seconds: 30
```

**Why**: Prevent retry storms that amplify TOCTOU races.

---

## Verification

### 1. Confirm Race Rate Drops
```bash
# Monitor metric for 10 minutes
watch -n 10 'curl -s http://localhost:9090/metrics | grep idem_toctou_race_detected_total'

# Expected: No new increments
```

### 2. Verify Idempotency Works
```bash
# Send duplicate request with same idem_key
curl -X POST http://k0-kernel:8080/k0/command.submit \
  -H "Content-Type: application/json" \
  -d '{"idem_key":"test-idem-123","topic":"test.command","payload":{}}'

# Check WAL for duplicates
sqlite3 /data/k0.db "SELECT COUNT(*) FROM wal WHERE idem_key='test-idem-123';"

# Expected: COUNT = 1 (no duplicates)
```

### 3. Check Concurrent Check Gauge
```bash
curl http://localhost:9090/metrics | grep idem_concurrent_checks_gauge

# Expected: Value < 5 (low concurrency)
```

---

## Prevention

### Code-Level Guards
- ✅ **IMPLEMENTED**: Idempotency check INSIDE transaction (line 643+ in `command.py`)
- ✅ **IMPLEMENTED**: TOCTOU race detection metric with < 1.0s age check
- ⏳ **RECOMMENDED**: HMAC-based idempotency (Gap 2) - cryptographically secure keys

### Operational Guards
- **NTP Sync**: Monitor clock skew < 500ms across all nodes
- **Circuit Breaker**: Prevent retry storms
- **Alert Threshold**: Fire alert on ANY race detection (> 0 for 1m)

### Architecture Improvements
- **V2 Enhancement**: Distributed locking via Redis/etcd for idempotency checks
- **V2 Enhancement**: WAL unique constraint on `idem_key` (SQLite UPSERT)

---

## Related Documentation

- **ADR-K002**: Idempotency Key Design (BLAKE3 vs. HMAC)
- **Gap 2 Runbook**: [gap-02-hmac-idempotency.md](gap-02-hmac-idempotency.md)
- **Gap 41 Runbook**: [gap-41-toctou-metrics.md](gap-41-toctou-metrics.md)
- **Prometheus Alert**: `K0IdempotencyTOCTOURaceDetected`

---

## Contact

**On-Call Team**: kernel-oncall@familyos.dev
**Slack Channel**: #k0-incidents
**Issue Tracker**: https://github.com/Pkansagra-hub/family-os/issues (Gap 27)
