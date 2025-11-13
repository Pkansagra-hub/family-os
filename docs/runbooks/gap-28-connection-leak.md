# Runbook: Gap 28 - UnitOfWork Connection Leak

**Priority**: P0 (CRITICAL)
**Component**: `k0/uow/unit_of_work.py`
**Symptoms**: Connection pool exhaustion, timeouts, deadlocks
**Related**: Gap 45 (Pool Saturation Metrics)

---

## Symptoms

- Metric: `sqlite_pool_saturation_ratio` approaching 1.0 (100%)
- Metric: `sqlite_pool_acquire_timeouts_total` increasing
- HTTP 500 errors: "Timed out waiting for SQLite connection"
- Application hangs waiting for connections
- Database locked errors in logs

## Root Cause

Connection leak in `UnitOfWork._cleanup()`:
1. Exception raised during `__exit__`
2. Connection not explicitly closed
3. `connection_scope.__exit__()` fails before releasing to pool
4. Connection remains in "in_use" state forever

**Leak Scenario**:
```python
try:
    with connection_scope() as conn:
        # Exception here
        raise RuntimeError("Oops")
finally:
    # connection_scope.__exit__() runs but conn not explicitly closed
    # Pool thinks connection still in use → LEAK
```

---

## Investigation Steps

### 1. Check Pool Saturation
```bash
# Current pool state
curl http://localhost:9090/metrics | grep sqlite_pool

# Expected metrics:
# sqlite_pool_connections_active{} 8.0      # All connections used
# sqlite_pool_saturation_ratio{} 1.0        # 100% saturated
# sqlite_pool_acquire_timeouts_total{} 45   # Increasing
```

**Alert Threshold**: `saturation_ratio > 0.9` for 5m

### 2. Identify Leaked Connections
```python
# Attach to running K0 process
import sys
sys.path.insert(0, "/app")
from k0.uow.connection_pool import get_pool

pool = get_pool()
stats = pool.stats()

print(f"Created: {stats.created}")
print(f"Available: {stats.available}")
print(f"In Use: {stats.in_use}")

# If in_use == max_size and available == 0 → FULL LEAK
# If in_use > 0 but no active requests → PARTIAL LEAK
```

### 3. Find Stuck Transactions
```bash
# Check SQLite WAL journal
ls -lh /data/k0.db-wal

# Large WAL file (> 10MB) indicates uncommitted transactions
# Check for long-running connections
```

### 4. Review Error Logs
```bash
kubectl logs -l app=k0-kernel --since=1h | grep -E "(TimeoutError|Connection|Pool exhausted)"

# Look for:
# - "Timed out waiting for SQLite connection" (pool exhausted)
# - "database is locked" (connection not released)
# - Tracebacks in UnitOfWork.__exit__
```

---

## Mitigation Steps

### Immediate Actions (< 5 minutes)

#### 1. Restart K0 Kernel
```bash
# Nuclear option: Restart all pods to close leaked connections
kubectl rollout restart deployment k0-kernel

# Monitor recovery
watch -n 5 'curl -s http://localhost:9090/metrics | grep sqlite_pool_saturation_ratio'
```

**Expected**: Saturation drops to 0.2-0.4 after restart

#### 2. Verify Fix Applied
```bash
# Check for Gap 28 fix in production code
kubectl exec -it k0-kernel-0 -- grep -A 20 "Gap 28 fix" /app/k0/uow/unit_of_work.py

# Expected output (line 296+):
# # CRITICAL: Explicitly close connection first (Gap 28 fix)
# if self._connection is not None:
#     try:
#         self._connection.close()
#     except Exception:
#         pass
#     finally:
#         self._connection = None
```

**If missing**: Deploy hotfix immediately from `k0-Strengthning` branch

### Short-Term Fixes (< 1 hour)

#### 3. Increase Pool Size (Temporary Workaround)
```yaml
# k0/config/database.yml
database:
  pool:
    max_size: 16  # Increase from 8 to 16
    busy_timeout_ms: 10000  # Increase timeout
```

**Why**: Buys time while fixing root cause
**Warning**: Does not fix leak, only delays saturation

#### 4. Add Pool Saturation Alert
```yaml
# k0/deploy/generated/rules/slo_alerts.yaml
- alert: K0PoolSaturationHigh
  expr: sqlite_pool_saturation_ratio > 0.9
  for: 5m
  labels:
    severity: critical
    component: database
    gap: "28"
  annotations:
    summary: "SQLite connection pool 90% saturated"
    runbook_url: "https://github.com/Pkansagra-hub/family-os/tree/k0-Strengthning/docs/runbooks/gap-28-connection-leak.md"
```

---

## Root Cause Fix (ALREADY IMPLEMENTED in Gap 28)

### Code Changes in `k0/uow/unit_of_work.py` (lines 296-320)

```python
def _cleanup(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: TracebackType | None,
) -> None:
    # CRITICAL: Explicitly close connection first (Gap 28 fix)
    # Ensures connection returned to pool even if scope.__exit__() fails
    if self._connection is not None:
        try:
            self._connection.close()
        except Exception:  # pragma: no cover - defensive guard
            pass  # Best effort cleanup, don't raise
        finally:
            self._connection = None

    # Exit scope (handles pool release)
    if self._scope is not None:
        try:
            self._scope.__exit__(exc_type, exc, tb)
        except Exception:  # pragma: no cover - prevent double-exception
            pass  # Scope exit already attempted connection cleanup
        finally:
            self._scope = None

    # Reset state flags
    self._entered = False

    # Reset context var (Gap 28 fix: single assignment, not triple)
    if self._token is not None:
        try:
            _ACTIVE_UOW.reset(self._token)
        except Exception:  # pragma: no cover - defensive guard
            pass  # Context cleanup is best-effort
        finally:
            self._token = None  # ✅ Single assignment (was 3x before)
```

**Key Changes**:
1. **Explicit `connection.close()`** before scope exit
2. **Best-effort exception handling** (don't raise in cleanup)
3. **Single assignment** to `_token = None` (was 3x duplicate before)

---

## Verification

### 1. Confirm Pool Metrics Stabilize
```bash
# Monitor for 30 minutes
watch -n 30 'curl -s http://localhost:9090/metrics | grep -E "(sqlite_pool_saturation_ratio|sqlite_pool_acquire_timeouts_total)"'

# Expected:
# sqlite_pool_saturation_ratio < 0.6 (healthy)
# sqlite_pool_acquire_timeouts_total = 0 (no new timeouts)
```

### 2. Load Test
```bash
# Generate high load
ab -n 10000 -c 50 http://k0-kernel:8080/k0/command.submit

# Check pool doesn't saturate
curl http://localhost:9090/metrics | grep sqlite_pool_saturation_ratio

# Expected: < 0.8 even under load
```

### 3. Verify Cleanup Logic
```bash
# Check connection is closed in all code paths
grep -n "self._connection.close()" k0/uow/unit_of_work.py

# Expected: Line 299 (in _cleanup method)
```

---

## Prevention

### Code-Level Guards
- ✅ **IMPLEMENTED**: Explicit connection close in `_cleanup()` (line 296)
- ✅ **IMPLEMENTED**: Best-effort exception handling (no raise in cleanup)
- ✅ **IMPLEMENTED**: Single assignment to `_token` (was 3x before)

### Operational Guards
- **Pool Metrics**: Monitor `sqlite_pool_saturation_ratio` < 0.9
- **Timeout Alert**: Fire on `sqlite_pool_acquire_timeouts_total` increase
- **Load Testing**: Verify no leaks under sustained 50 req/sec load

### Architecture Improvements
- **V2 Enhancement**: Connection lifetime tracking with TTL
- **V2 Enhancement**: Automatic pool drain-and-refill on saturation

---

## Related Documentation

- **Gap 45**: [gap-45-pool-metrics.md](gap-45-pool-metrics.md) - Pool saturation metrics
- **Gap 21**: Pool shutdown in `finally` block
- **ADR-K001**: UnitOfWork transaction model

---

## Contact

**On-Call Team**: kernel-oncall@familyos.dev
**Slack Channel**: #k0-incidents
**Issue Tracker**: https://github.com/Pkansagra-hub/family-os/issues (Gap 28)
