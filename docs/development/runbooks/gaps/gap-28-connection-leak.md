# Gap 28: UnitOfWork Connection Leak - Runbook

**Priority**: P0 - CRITICAL BLOCKER
**Component**: `k0/uow/unit_of_work.py`
**Issue**: [#002](https://github.com/Pkansagra-hub/family-os/issues/002)
**Alert**: `SQLiteConnectionPoolExhausted`

---

## Symptoms

### Alert Firing

- **Alert Name**: `SQLiteConnectionPoolExhausted`
- **Trigger**: `k0_sqlite_pool_saturation_ratio > 0.90`
- **Severity**: CRITICAL (P0)
- **Dashboard**: [P0 Blocker Dashboard - Panel 2](http://localhost:3000/d/p0-blockers)

### Observable Behavior

- Connection pool saturation > 80% sustained
- Requests timing out waiting for connections
- Metric: `k0_sqlite_pool_acquire_timeouts_total` increasing
- Metric: `k0_sqlite_pool_saturation_ratio` approaching 1.0
- Slow queries and command submission latency spikes

### User Impact

- **CRITICAL**: Request failures and timeouts
- HTTP 503 Service Unavailable errors
- Deadlocks: Requests waiting indefinitely for connections
- System may become unresponsive, requiring restart

---

## Investigation

### Step 1: Verify Alert and Pool State

```bash
# Check current pool saturation
curl -s http://localhost:9090/api/v1/query?query=k0_sqlite_pool_saturation_ratio | jq '.data.result[0].value[1]'

# Check active connections (should be <= max pool size, typically 10)
curl -s http://localhost:9090/api/v1/query?query=k0_sqlite_pool_connections_active | jq '.data.result[0].value[1]'

# Check acquire timeout rate (should be 0)
curl -s 'http://localhost:9090/api/v1/query?query=increase(k0_sqlite_pool_acquire_timeouts_total[5m])' | jq '.data.result[0].value[1]'
```

### Step 2: Identify Leaked Connections

```sql
-- Check for long-running transactions (potential leaks)
SELECT
    connection_id,
    started_ts,
    (unixepoch('now', 'subsec') * 1000 - started_ts) as duration_ms,
    state,
    operation
FROM active_connections
WHERE state = 'OPEN'
ORDER BY duration_ms DESC;
```

### Step 3: Check UnitOfWork Exception Patterns

```bash
# Check for UoW commit failures (can cause leaks)
curl -s 'http://localhost:9090/api/v1/query?query=increase(k0_uow_commit_failures_total[5m])' | jq '.data.result[0].value[1]'

# Check for exceptions during scope exit
grep "_cleanup" /var/log/k0/kernel.log | grep "Exception" | tail -20
```

### Step 4: Analyze Connection Lifecycle

```bash
# Check acquire latency (should be < 10ms)
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,%20rate(k0_sqlite_pool_acquire_latency_seconds_bucket[5m]))' | jq '.data.result[0].value[1]'

# If > 0.1 (100ms), pool is saturated
```

---

## Mitigation

### Immediate Actions (< 2 minutes)

#### Option 1: Restart Kernel (Emergency)

```bash
# Quick fix: Restart kernel to clear leaked connections
docker-compose -f k0/deploy/docker-compose.yml restart k0-kernel

# Monitor recovery
watch -n 1 'curl -s http://localhost:9090/api/v1/query?query=k0_sqlite_pool_saturation_ratio | jq .data.result[0].value[1]'
```

#### Option 2: Increase Pool Size (Temporary)

```bash
# Edit k0/config/kernel.yml
sqlite:
  connection_pool:
    max_size: 20  # Increase from 10 (TEMPORARY - does not fix leak)
    timeout: 30

# Restart kernel
docker-compose -f k0/deploy/docker-compose.yml restart k0-kernel
```

### Data Integrity Verification (< 10 minutes)

```sql
-- Verify no transactions were interrupted mid-commit
SELECT COUNT(*) as incomplete_transactions
FROM wal
WHERE metadata->>'$.commit_status' = 'IN_PROGRESS';

-- Expected: 0
-- If > 0, investigate interrupted transactions
```

### Communication

**Slack Notification** (`#k0-alerts-sre`):

```
🚨 P0 BLOCKER: Gap 28 connection leak detected
- Alert: SQLiteConnectionPoolExhausted
- Pool Saturation: [X]% (threshold: 90%)
- Active Connections: [X] / [max_size]
- Mitigation: [Restart completed / In progress]
- Downtime: [X] minutes
- Runbook: https://docs.example.com/runbooks/gaps/gap-28-connection-leak/
```

---

## Root Cause

### Technical Explanation

**Connection Cleanup Failure in Exception Paths**

```python
# VULNERABLE CODE (before Gap 28 fix):
class UnitOfWork:
    def __enter__(self):
        self._token = self._scheduler.acquire()  # Get scheduler slot
        self._scope = self._connection_pool.transaction_scope()  # Get connection
        self._scope.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._scope.__exit__(exc_type, exc_val, exc_tb)  # May raise exception!
        finally:
            self._cleanup()  # Connection may not be closed if __exit__ raises

    def _cleanup(self):
        # BUG: If _scope.__exit__() raises, connection is NOT closed
        self._token = None  # Token leak (triple assignment bug at lines 272-274)
        self._token = None  # Duplicate assignment
        self._token = None  # Duplicate assignment
        # Missing: connection.close() call
```

### Why It Happens

1. **Exception during `_scope.__exit__()`**: If transaction rollback fails, connection is not returned to pool
2. **Triple assignment bug**: Lines 272-274 have duplicate `self._token = None` assignments, causing confusion
3. **No explicit `connection.close()`**: Relies on scope manager to close, which may fail
4. **Error storm amplification**: High error rate (50% failures) exhausts pool quickly

### Gap 28 Fix

Add explicit connection cleanup:

```python
# FIXED CODE (after Gap 28 fix):
class UnitOfWork:
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._scope.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._cleanup()  # Always runs

    def _cleanup(self):
        # FIXED: Explicit connection close before scope exit
        if self._connection:
            try:
                self._connection.close()  # Force close
            except Exception as e:
                logger.error("Connection close failed", exc_info=e)

        # FIXED: Single token release
        if self._token:
            self._scheduler.release(self._token)
            self._token = None  # Single assignment
```

**Result**: Connection always returned to pool, even on exception.

---

## Long-Term Fix

### Implementation Status

- **Issue**: [#002 - Fix UnitOfWork Connection Leak](https://github.com/Pkansagra-hub/family-os/issues/002)
- **ADR**: None required (bug fix)
- **Target**: Milestone 1 - Week 1-2
- **Effort**: 6-8 hours

### Acceptance Criteria

- [ ] Explicit `connection.close()` in `_cleanup()` before scope exit
- [ ] Remove duplicate `self._token = None` assignments
- [ ] Exception during `_scope.__exit__()` doesn't prevent connection cleanup
- [ ] Stress test: 1000 commits with 50% random failures → no pool exhaustion
- [ ] Pool saturation stays below 80% during error storms

### Verification

```bash
# Run stress test
pytest tests/k0/uow/test_connection_leak_fix.py -v

# Expected output:
# test_connection_leak_with_errors ... PASSED (1000 commits, 0 leaks)
# test_pool_saturation_under_load ... PASSED (saturation < 80%)
```

---

## Monitoring and Alerting

### Key Metrics

| Metric | Threshold | Alert |
|--------|-----------|-------|
| `k0_sqlite_pool_saturation_ratio` | > 0.90 | CRITICAL |
| `k0_sqlite_pool_saturation_ratio` | > 0.80 | WARNING |
| `k0_sqlite_pool_acquire_timeouts_total` | > 0 | WARNING |
| `k0_sqlite_pool_acquire_latency_seconds` (P95) | > 0.1s | WARNING |

### Dashboard Panels

- **Panel 2**: Connection pool saturation gauge (current value)
- **Panel 2**: Connection pool saturation trend (over time)
- **Connection Pool Details**: Active connections, acquire timeouts

### Recommended Alerts

```yaml
# Already configured in slo_alerts.yaml (Issue #004)
- alert: SQLiteConnectionPoolExhausted
  expr: k0_sqlite_pool_saturation_ratio > 0.90
  for: 1m
  labels:
    severity: critical
    priority: P0
    gap: gap-28

- alert: SQLiteConnectionPoolWarning
  expr: k0_sqlite_pool_saturation_ratio > 0.80
  for: 5m
  labels:
    severity: warning
    priority: P0
    gap: gap-28
```

---

## Prevention

### Operational Best Practices

1. **Monitor pool saturation continuously**: Use P0 Blocker Dashboard
2. **Set pool size based on workload**: `max_size = max_concurrent_requests / 10`
3. **Enable connection pooling metrics**: Gap 45 (Issue #003) provides full instrumentation
4. **Regular health checks**: Verify `k0_sqlite_pool_saturation_ratio < 0.7` in staging

### Testing Requirements

```bash
# Integration test: Connection leak detection
pytest tests/k0/uow/test_connection_leak_fix.py::test_connection_leak_with_errors -v

# Load test: Pool saturation under load
pytest tests/k0/uow/test_connection_leak_fix.py::test_pool_saturation_under_load -v

# Chaos test: Random failures during commit
pytest tests/k0/uow/test_connection_leak_fix.py::test_pool_chaos_errors -v
```

---

## Related Documentation

- [K0 Implementation Roadmap - Milestone 1](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_implementation_roadmap.md#epic-11-transaction-safety--resource-management-16-20h)
- [Gap 28 Analysis](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_architecture_gaps_analysis.md#gap-28-unitofwork-connection-leak)
- [P0 Blocker Dashboard](http://localhost:3000/d/p0-blockers)
- [UnitOfWork Design](https://github.com/Pkansagra-hub/family-os/blob/main/k0/uow/README.md)

---

## Incident History

| Date | Duration | Saturation | Root Cause | Resolution |
|------|----------|-----------|------------|------------|
| 2025-11-11 | - | TBD | Gap 28 not yet fixed | Awaiting implementation |

---

**Last Updated**: 2025-11-11
**Document Owner**: SRE Team
**Review Frequency**: Weekly until Gap 28 resolved
