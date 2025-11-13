# Dashboard Empty Graphs - Root Cause Analysis

**Date**: 2025-11-11
**Status**: 🔴 CRITICAL - Most dashboard panels showing "No data"
**Impact**: Zero observability for production operations

---

## Executive Summary

**Root Cause**: Dashboards query metrics that are **never emitted** by the application code.

**Key Finding**: Only HTTP request metrics are currently instrumented. All operational metrics (replay, WAL, outbox, connections, SSE) are missing.

**Impact Severity**: **CRITICAL**

- ❌ Cannot monitor replay throughput
- ❌ Cannot monitor WAL lag
- ❌ Cannot monitor outbox backlog
- ❌ Cannot monitor active connections
- ❌ Cannot monitor SSE subscriptions
- ✅ Can monitor HTTP requests (latency, errors, throughput)

---

## 1. Metrics Inventory Audit

### ✅ Metrics That ARE Emitted

**Source**: `k0/kernel/app.py` lines 596-609

| Metric Name (Raw) | Full Name (with namespace) | Location | Works? |
|-------------------|----------------------------|----------|--------|
| `http_requests_total` | `k0_kernel_http_requests_total` | kernel/app.py:602 | ✅ YES |
| `http_request_latency_seconds` | `k0_kernel_http_request_latency_seconds` | kernel/app.py:597 | ✅ YES |
| `policy_stamp_attached_total` | `k0_kernel_policy_stamp_attached_total` | ports/command.py:403 | ✅ YES |
| `wal_policy_stamp_present_total` | `k0_kernel_wal_policy_stamp_present_total` | ports/command.py:601 | ✅ YES |
| `receipts_policy_stamp_present_total` | `k0_kernel_receipts_policy_stamp_present_total` | ports/command.py:768 | ✅ YES |
| `idem_toctou_race_detected_total` | `k0_kernel_idem_toctou_race_detected_total` | ports/command.py:667 | ✅ YES |
| `gate_rejections_total` | `k0_kernel_gate_rejections_total` | gate/minimal_gate.py:multiple | ✅ YES |
| `gate_accepted_total` | `k0_kernel_gate_accepted_total` | gate/minimal_gate.py:427 | ✅ YES |
| `schema_cache_hits_total` | `k0_kernel_schema_cache_hits_total` | gate/schema_registry.py:124 | ✅ YES |
| `schema_cache_misses_total` | `k0_kernel_schema_cache_misses_total` | gate/schema_registry.py:129 | ✅ YES |
| `sqlite_pool_connections_active` | `k0_kernel_sqlite_pool_connections_active` | uow/connection_pool.py:186 | ✅ YES |
| `sqlite_pool_saturation_ratio` | `k0_kernel_sqlite_pool_saturation_ratio` | uow/connection_pool.py:191 | ✅ YES |
| `k0_dlq_entries_by_state` | `k0_kernel_k0_dlq_entries_by_state` | storage/dlq.py:96 | ⚠️ DOUBLE PREFIX |
| `k0_dlq_retry_attempts_total` | `k0_kernel_k0_dlq_retry_attempts_total` | storage/dlq.py:103 | ⚠️ DOUBLE PREFIX |
| `k0_dlq_requeue_latency_seconds` | `k0_kernel_k0_dlq_requeue_latency_seconds` | storage/dlq.py:110 | ⚠️ DOUBLE PREFIX |
| `k0_dlq_entries_abandoned_total` | `k0_kernel_k0_dlq_entries_abandoned_total` | outbox/worker.py | ⚠️ DOUBLE PREFIX |
| `k0_outbox_retry_backoff_exponent` | `k0_kernel_k0_outbox_retry_backoff_exponent` | outbox/worker.py | ⚠️ DOUBLE PREFIX |
| `k0_outbox_backoff_sleep_seconds` | `k0_kernel_k0_outbox_backoff_sleep_seconds` | outbox/worker.py | ⚠️ DOUBLE PREFIX |
| `k0_sse_invalid_cursor_total` | `k0_kernel_k0_sse_invalid_cursor_total` | sse/server.py | ⚠️ DOUBLE PREFIX |
| `k0_sse_cursor_validation_seconds` | `k0_kernel_k0_sse_cursor_validation_seconds` | sse/server.py | ⚠️ DOUBLE PREFIX |

**Note**: Epic 3.5 metrics have DOUBLE PREFIX bug (`k0_kernel_k0_*`) - they're emitted with `k0_` prefix manually, then namespace adds another `k0_kernel_` prefix!

---

### ❌ Metrics That Are NEVER Emitted

**Source**: Dashboard queries with no corresponding code

| Dashboard Metric | Dashboard File | Line | Status |
|-----------------|----------------|------|--------|
| `k0_kernel_replay_processed_total` | kernel_overview.json | 327 | ❌ NEVER EMITTED |
| `k0_kernel_snapshot_watermark` | kernel_overview.json | 397 | ❌ NEVER EMITTED |
| `k0_kernel_outbox_pending_total` | kernel_overview.json | 467 | ❌ NEVER EMITTED |
| `k0_kernel_active_connections` | kernel_overview.json | 932 | ❌ NEVER EMITTED |
| `k0_kernel_sse_pending_events` | kernel_overview.json | 1025 | ❌ NEVER EMITTED |
| `k0_kernel_uow_commit_seconds` | kernel_overview.json | 746 | ❌ NEVER EMITTED |
| `k0_kernel_outbox_apply_total` | kernel_overview.json | 839 | ❌ NEVER EMITTED |

**Impact**: 7 out of 11 panels in `kernel_overview.json` show **NO DATA** (64% failure rate)

---

## 2. Recording Rules Analysis

### ✅ Recording Rules That Work

**Source**: `k0/deploy/generated/rules/recording_rules.yaml`

These recording rules depend on `k0_kernel_http_requests_total` and `k0_kernel_http_request_latency_seconds`, which ARE emitted:

| Recording Rule | Base Metric | Status |
|---------------|-------------|--------|
| `job:k0_api_availability:ratio5m` | `k0_kernel_http_requests_total` | ✅ WORKS |
| `job:k0_command_latency_seconds:p95:5m` | `k0_kernel_http_request_latency_seconds_bucket` | ✅ WORKS |
| `job:k0_query_latency_seconds:p95:5m` | `k0_kernel_http_request_latency_seconds_bucket` | ✅ WORKS |
| `job:k0_http_requests:rate5m` | `k0_kernel_http_requests_total` | ✅ WORKS |

### ❌ Recording Rules That Are Broken

| Recording Rule | Base Metric | Status | Line |
|---------------|-------------|--------|------|
| `job:k0_replay_throughput:rate5m` | `k0_kernel_replay_processed_total` | ❌ BROKEN | Line 52 |
| `job:k0_outbox_pending:ratio` | `k0_kernel_outbox_pending_total` | ❌ BROKEN | Line 73 |
| `job:k0_wal_commits:rate5m` | `k0_kernel_k0_uow_commit_total` | ❌ WRONG NAME | Line 63 |
| `job:k0_wal_fsync_duration_seconds:p95:5m` | `k0_kernel_k0_uow_wal_fsync_seconds_total` | ❌ WRONG NAME | Line 65 |

---

## 3. Epic 3.5 Metrics - Double Prefix Bug

### Problem

Epic 3.5 metrics were emitted with **manual `k0_` prefix**:

```python
# storage/dlq.py line 96
self._metrics.emit("k0_dlq_entries_by_state", ...)
```

But `MetricsExporter` **automatically adds namespace** `k0_kernel_`:

```python
# obs/metrics.py line 35
def __init__(self, *, namespace: str = "k0_kernel", ...):
```

**Result**: Double prefix → `k0_kernel_k0_dlq_entries_by_state` ❌

### Affected Metrics

All Epic 3.5 metrics have this bug:

- `k0_kernel_k0_dlq_entries_by_state` (should be `k0_kernel_dlq_entries_by_state`)
- `k0_kernel_k0_dlq_retry_attempts_total`
- `k0_kernel_k0_dlq_requeue_latency_seconds`
- `k0_kernel_k0_dlq_entries_abandoned_total`
- `k0_kernel_k0_outbox_retry_backoff_exponent`
- `k0_kernel_k0_outbox_backoff_sleep_seconds`
- `k0_kernel_k0_sse_invalid_cursor_total`
- `k0_kernel_k0_sse_cursor_validation_seconds`

### Fix

Remove `k0_` prefix from emit calls:

```python
# BEFORE (wrong)
self._metrics.emit("k0_dlq_entries_by_state", ...)

# AFTER (correct)
self._metrics.emit("dlq_entries_by_state", ...)
```

---

## 4. Missing Instrumentation Audit

### Critical Missing Metrics

These metrics are queried by dashboards but **never instrumented**:

#### 4.1 Replay Metrics

**Dashboard Query**: `k0_kernel_replay_processed_total`
**Status**: ❌ Not instrumented
**Required Location**: `k0/storage/replayer.py` in `process()` method
**Implementation**:

```python
def process(self, ...):
    # ... existing code ...
    if self._metrics:
        self._metrics.emit("replay_processed_total", 1.0, driver=entry.driver)
```

#### 4.2 WAL Watermark Metrics

**Dashboard Query**: `k0_kernel_snapshot_watermark`
**Status**: ❌ Not instrumented
**Required Location**: `k0/storage/wal.py` or `k0/storage/snapshots.py`
**Implementation**:

```python
def save_snapshot(self, ...):
    # ... existing code ...
    if self._metrics:
        self._metrics.set_gauge("snapshot_watermark", float(snapshot.wal_position))
```

#### 4.3 Outbox Backlog Metrics

**Dashboard Query**: `k0_kernel_outbox_pending_total`
**Status**: ❌ Not instrumented
**Required Location**: `k0/storage/outbox.py` in `save()` and `mark_applied()` methods
**Implementation**:

```python
def save(self, ...):
    # ... existing code ...
    pending_count = self._count_pending()
    if self._metrics:
        self._metrics.set_gauge("outbox_pending_total", float(pending_count))
```

#### 4.4 Active HTTP Connections

**Dashboard Query**: `k0_kernel_active_connections`
**Status**: ❌ Not instrumented
**Required Location**: `k0/kernel/app.py` in request middleware
**Implementation**:

```python
async def telemetry_chain(request: Request, call_next):
    active_connections.inc()
    try:
        response = await call_next(request)
        return response
    finally:
        active_connections.dec()
```

#### 4.5 SSE Active Subscriptions

**Dashboard Query**: `k0_kernel_sse_pending_events`
**Status**: ❌ Not instrumented (should be `sse_active_subscriptions`)
**Required Location**: `k0/sse/server.py` in `subscribe()` and connection handlers
**Implementation**:

```python
async def subscribe(self, ...):
    if self._metrics:
        self._metrics.set_gauge("sse_active_subscriptions", len(active_subs))
```

#### 4.6 UoW Commit Metrics

**Dashboard Query**: `k0_kernel_uow_commit_seconds`
**Status**: ❌ Not instrumented
**Required Location**: `k0/uow/unit_of_work.py` in `commit()` method
**Implementation**:

```python
async def commit(self):
    start = time.perf_counter()
    # ... existing code ...
    duration = time.perf_counter() - start
    if self._metrics:
        self._metrics.observe("uow_commit_seconds", duration, labels={"outcome": "success"})
```

#### 4.7 Outbox Apply Metrics

**Dashboard Query**: `k0_kernel_outbox_apply_total`
**Status**: ❌ Not instrumented
**Required Location**: `k0/outbox/worker.py` in `_handle_success()` and `_handle_failure()`
**Implementation**:

```python
def _handle_success(self, ...):
    # ... existing code ...
    self._emit_metric("outbox_apply_total", 1.0, outcome="success", driver=alias)

def _handle_failure(self, ...):
    # ... existing code ...
    self._emit_metric("outbox_apply_total", 1.0, outcome="retry", driver=alias)
```

---

## 5. Fix Implementation Plan

### Phase 1: Fix Epic 3.5 Double Prefix Bug (1 hour) - URGENT

**Files to Fix**:

1. `k0/storage/dlq.py` - Remove `k0_` prefix from 4 metrics
2. `k0/outbox/worker.py` - Remove `k0_` prefix from 2 metrics
3. `k0/sse/server.py` - Remove `k0_` prefix from 2 metrics

**Impact**: Fixes 8 Epic 3.5 metrics immediately

### Phase 2: Add Missing Core Instrumentation (4-6 hours) - HIGH PRIORITY

**7 Metrics to Add**:

1. `replay_processed_total` in `storage/replayer.py`
2. `snapshot_watermark` in `storage/snapshots.py`
3. `outbox_pending_total` in `storage/outbox.py`
4. `active_connections` in `kernel/app.py` middleware
5. `sse_active_subscriptions` in `sse/server.py`
6. `uow_commit_seconds` in `uow/unit_of_work.py`
7. `outbox_apply_total` in `outbox/worker.py`

**Impact**: Fixes 7 broken dashboard panels in kernel_overview.json

### Phase 3: Fix Recording Rules (1 hour) - MEDIUM PRIORITY

**Files to Fix**:

1. `k0/deploy/generated/rules/recording_rules.yaml` - Fix lines 63, 65, 73
2. Update metric names to match actual emissions

### Phase 4: Create Epic 3.5 Dashboards (4 hours) - MEDIUM PRIORITY

**New Dashboards**:

1. `dlq_outbox_operations.json` - 10 panels
2. `sse_cursor_validation.json` - 8 panels

---

## 6. Testing Strategy

### Validation Steps

1. **Start kernel** with instrumentation changes
2. **Generate load** (HTTP requests, replays, outbox entries)
3. **Query Prometheus** `/api/v1/query?query=k0_kernel_*`
4. **Verify metrics exist** in Prometheus output
5. **Open Grafana dashboards** and verify panels populate
6. **Trigger alerts** to verify alert rules work

### Expected Outcomes

**Before Fix**:

- ❌ 7/11 panels in kernel_overview.json show "No data" (64% broken)
- ❌ 8 Epic 3.5 metrics have double prefix
- ❌ 4 recording rules broken

**After Fix**:

- ✅ 11/11 panels in kernel_overview.json show data (100% working)
- ✅ 8 Epic 3.5 metrics correctly named
- ✅ 4 recording rules working
- ✅ 2 new dashboards with 18 panels showing Epic 3.5 data

---

## 7. Prometheus Query Examples

### Check Which Metrics Actually Exist

```promql
# List all k0_kernel metrics
{__name__=~"k0_kernel_.*"}

# Check for double prefix bug
{__name__=~"k0_kernel_k0_.*"}

# Check HTTP metrics (should work)
k0_kernel_http_requests_total

# Check Epic 3.5 metrics (double prefix bug)
k0_kernel_k0_dlq_entries_by_state

# Check broken metrics (won't exist)
k0_kernel_replay_processed_total
```

### Debug Recording Rules

```promql
# Check if recording rule output exists
job:k0_api_availability:ratio5m  # Should work
job:k0_replay_throughput:rate5m  # Won't work (base metric missing)
job:k0_outbox_pending:ratio       # Won't work (base metric missing)
```

---

## 8. Priority Recommendations

### 🔴 CRITICAL (Do Immediately)

1. **Fix Epic 3.5 Double Prefix** (1 hour)
   - Fixes 8 metrics that users just added
   - Simple find/replace in 3 files
   - No functional changes, just naming

2. **Add Replay Metrics** (30 min)
   - Most commonly monitored operation
   - Single file change
   - High visibility improvement

### 🟡 HIGH (Do This Week)

3. **Add Outbox Metrics** (1 hour)
   - Critical for delivery monitoring
   - 2 metrics: pending count, apply outcomes

4. **Add UoW Commit Metrics** (45 min)
   - Core transaction monitoring
   - Single file change

### 🟢 MEDIUM (Do Next Week)

5. **Add SSE/Connection Metrics** (2 hours)
   - Nice to have for capacity planning
   - Lower priority than data path

6. **Create New Dashboards** (4 hours)
   - Only after metrics are working
   - Can be done incrementally

---

## 9. Root Cause Summary

**Why Dashboards Are Empty**:

1. **Instrumentation Gap**: Only HTTP middleware emits metrics automatically. All operational metrics (replay, WAL, outbox, connections) were never added to the code.

2. **Double Prefix Bug**: Epic 3.5 metrics were emitted with manual `k0_` prefix, but MetricsExporter adds `k0_kernel_` namespace, resulting in `k0_kernel_k0_*` (wrong).

3. **Dashboard Assumptions**: Dashboards were created assuming metrics would be instrumented, but implementation was incomplete.

4. **Recording Rule Dependencies**: Some recording rules aggregate non-existent base metrics, so they also fail.

**Bottom Line**: **Metrics implementation is ~30% complete**. HTTP path works, everything else is missing or broken.

---

## 10. Success Criteria

### Phase 1 Complete (Double Prefix Fix)

- [ ] All 8 Epic 3.5 metrics have single prefix `k0_kernel_*`
- [ ] Prometheus query returns correct metric names
- [ ] New dashboards (Issues #040, #041) can query metrics successfully

### Phase 2 Complete (Core Instrumentation)

- [ ] All 7 missing metrics instrumented
- [ ] kernel_overview.json shows data in all 11 panels
- [ ] Recording rules output exists in Prometheus

### Phase 3 Complete (Recording Rules)

- [ ] All 4 broken recording rules fixed
- [ ] Queries return non-zero values under load

### Full Fix Complete

- [ ] 100% dashboard panel success rate (0 "No data" errors)
- [ ] All alerts can fire (metrics exist for alert queries)
- [ ] Production observability functional

---

## Next Steps

1. **Update Issue #039** with double prefix fix as first task
2. **Create Issue #042** for missing core instrumentation (7 metrics)
3. **Create Issue #043** for recording rule fixes
4. **Block Issues #040, #041** until metrics are working
5. **Test in staging** before production deployment
