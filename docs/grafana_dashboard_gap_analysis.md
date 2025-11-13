# Grafana Dashboard Gap Analysis - K0 Kernel

**Date**: 2025-11-11
**Scope**: All Grafana dashboards in `k0/deploy/generated/dashboards/`
**Context**: Epic 3.5 completed, need dashboard coverage for new metrics

---

## Executive Summary

**Critical Issues Found**: 8 broken graph queries, 0 dashboards for Epic 3.5 metrics
**Missing Coverage**: DLQ operations, outbox backoff, SSE cursor validation, replayer parity
**Recommendation**: Create 2 new dashboards, fix 8 broken queries, add 15+ new panels

---

## 1. Broken Metric Queries (CRITICAL)

### Dashboard: `kernel_overview.json`

These queries reference **non-existent metrics** and will show "No data":

| Panel Title | Broken Metric | Line | Issue |
|------------|---------------|------|-------|
| **Replay Throughput** | `k0_kernel_replay_processed_total` | 327 | Metric never emitted in code |
| **WAL Lag** | `k0_kernel_snapshot_watermark` | 397 | Metric doesn't exist |
| **Outbox Backlog** | `k0_kernel_outbox_pending_total` | 467 | Wrong metric name |
| **Active HTTP Connections** | `k0_kernel_active_connections` | 932 | Metric not instrumented |
| **Active SSE Subscriptions** | `k0_kernel_sse_pending_events` | 1025 | Wrong metric name |

### Dashboard: `p0_blockers.json`

| Panel Title | Issue | Recommendation |
|------------|-------|----------------|
| Gap 27 TOCTOU Panel | Uses `k0_idem_toctou_race_detected_total` | ✅ CORRECT (Issue #013) |
| Gap 28 Pool Saturation | Uses `k0_sqlite_pool_saturation_ratio` | ✅ CORRECT (Issue #003) |

---

## 2. Missing Epic 3.5 Metric Coverage (NEW GAPS)

### Gap: No DLQ Operations Dashboard

**Missing Metrics** (Issue #032 - Gap 44):
- ❌ `k0_dlq_entries_by_state{state="PENDING|REQUEUED|ABANDONED"}`
- ❌ `k0_dlq_retry_attempts_total`
- ❌ `k0_dlq_requeue_latency_seconds`
- ❌ `k0_dlq_entries_abandoned_total`

**Business Impact**: Cannot monitor dead letter queue health, retry exhaustion, or abandoned entries.

**Required Panels**:
1. DLQ Entries by State (time series, stacked)
2. DLQ Abandoned Entries Rate (stat + alert indicator)
3. DLQ Retry Rate by Driver (time series)
4. DLQ Requeue Latency P95 (gauge)
5. DLQ Pending Queue Growth (delta graph)

---

### Gap: No Outbox Backoff Monitoring

**Missing Metrics** (Issue #033 - Gap 46):
- ❌ `k0_outbox_retry_backoff_exponent{driver}`
- ❌ `k0_outbox_backoff_sleep_seconds{driver}`

**Business Impact**: Cannot detect exponential backoff explosion (2^N growth) indicating persistent delivery failures.

**Required Panels**:
1. Backoff Exponent by Driver (time series, log scale)
2. Max Backoff Exponent (stat with critical threshold at 10)
3. Backoff Sleep Duration (heatmap showing distribution)
4. Exponential Growth Alert Status (stat, red if >10, yellow if >6)

---

### Gap: No SSE Cursor Validation Dashboard

**Missing Metrics** (Issue #034 - Gap 48):
- ❌ `k0_sse_invalid_cursor_total{reason="MALFORMED|NEGATIVE"}`
- ❌ `k0_sse_cursor_validation_seconds`

**Business Impact**: Cannot detect cursor validation failures, negative cursor attacks, or validation latency issues.

**Required Panels**:
1. Invalid Cursor Rate by Reason (time series, stacked)
2. Negative Cursor Attack Detection (stat, red if >0)
3. Cursor Validation Latency P95 (gauge)
4. Invalid Cursor Spike Alert Status (stat)

---

### Gap: No Replayer Parity Monitoring

**Existing Metrics** (Issue #027 - Gap 33, already implemented):
- ✅ `replay_parity_failures_total{failure_type="schema_missing|schema_blocked|receipt_missing|outbox_parity_mismatch"}`

**Business Impact**: Replayer parity metrics exist but NO dashboard visualizes them.

**Required Panels**:
1. Parity Failures by Type (time series, stacked)
2. Parity Failure Rate (stat)
3. Last Parity Failure (time since last failure)

---

## 3. Existing Dashboard Audit

### ✅ Working Dashboards

| Dashboard | Status | Coverage |
|-----------|--------|----------|
| `p0_blockers.json` | ✅ WORKING | Gap 27 (TOCTOU), Gap 28 (Pool Saturation) |
| `slo_burn_rate.json` | ✅ WORKING | SLO burn rate calculations |
| `anomaly_detection.json` | ✅ WORKING | Anomaly detection panels |

### ⚠️ Partially Broken Dashboards

| Dashboard | Working Panels | Broken Panels | Fix Priority |
|-----------|----------------|---------------|--------------|
| `kernel_overview.json` | 6/11 | 5/11 (45% broken) | **CRITICAL** |
| `sse_health.json` | Unknown | Needs audit | **HIGH** |
| `replay_throughput.json` | Unknown | Needs audit | **MEDIUM** |

---

## 4. Correct Metric Names (Reference)

### Actually Instrumented Metrics

From code analysis (`k0/ports/command.py`, `k0/storage/dlq.py`, etc.):

**Idempotency (Issue #013)**:
- ✅ `k0_idem_toctou_race_detected_total`
- ✅ `k0_idem_check_commit_window_seconds`
- ✅ `k0_idem_concurrent_checks_active`

**Policy Stamps (Issue #014)**:
- ✅ `k0_policy_stamp_attached_total`
- ✅ `k0_wal_policy_stamp_present_total`
- ✅ `k0_receipts_policy_stamp_present_total`

**Schema Cache (Issue #015)**:
- ✅ `k0_schema_cache_hits_total`
- ✅ `k0_schema_cache_misses_total`
- ✅ `k0_schema_cache_entries_active`

**Gate Metrics (Issue #016)**:
- ✅ `k0_gate_rejections_total{reason, tenant}`
- ✅ `k0_gate_accepted_total{tenant}`

**Connection Pool (Issue #003)**:
- ✅ `sqlite_pool_connections_active`
- ✅ `sqlite_pool_saturation_ratio`
- ✅ `sqlite_pool_acquire_latency_seconds`
- ✅ `sqlite_pool_acquire_timeouts_total`

**DLQ Metrics (Issue #032)**:
- ✅ `k0_dlq_entries_by_state`
- ✅ `k0_dlq_retry_attempts_total`
- ✅ `k0_dlq_requeue_latency_seconds`
- ✅ `k0_dlq_entries_abandoned_total`

**Outbox Backoff (Issue #033)**:
- ✅ `k0_outbox_retry_backoff_exponent`
- ✅ `k0_outbox_backoff_sleep_seconds`

**SSE Cursor (Issue #034)**:
- ✅ `k0_sse_invalid_cursor_total`
- ✅ `k0_sse_cursor_validation_seconds`

**Replayer Parity (Issue #027)**:
- ✅ `replay_parity_failures_total`

---

## 5. Recommended Dashboard Structure

### New Dashboard 1: **DLQ & Outbox Operations** (`dlq_outbox_operations.json`)

**Purpose**: Monitor dead letter queue health, retry exhaustion, and outbox backoff behavior

**Rows**:
1. **DLQ Health Overview**
   - DLQ Entries by State (time series, 3 series: PENDING/REQUEUED/ABANDONED)
   - Abandoned Entries Alert Status (stat, red if firing)
   - Total Retry Attempts (counter)

2. **DLQ Performance**
   - Requeue Latency P95 (gauge, threshold: 500ms)
   - Requeue Latency Heatmap (heatmap by driver)
   - Retry Rate by Driver (time series)

3. **Outbox Backoff Monitoring**
   - Backoff Exponent by Driver (time series, log scale)
   - Max Backoff Exponent (stat, red if >10)
   - Backoff Sleep Duration Distribution (heatmap)
   - Exponential Growth Alert Status (stat)

**Alert Indicators**: 4 alerts (DLQAbandonedEntriesDetected, DLQPendingQueueGrowing, OutboxBackoffExponentialGrowthCritical, OutboxBackoffSleepDurationHigh)

---

### New Dashboard 2: **SSE & Cursor Validation** (`sse_cursor_validation.json`)

**Purpose**: Monitor SSE health, cursor validation failures, and security events

**Rows**:
1. **SSE Overview**
   - Active SSE Subscriptions (stat) - **FIX METRIC NAME**
   - SSE Connection Rate (time series)
   - SSE Disconnection Rate (time series)

2. **Cursor Validation**
   - Invalid Cursor Rate by Reason (time series, stacked: MALFORMED/NEGATIVE)
   - Cursor Validation Latency P95 (gauge)
   - Validation Latency Histogram (heatmap)

3. **Security Events**
   - Negative Cursor Attack Detection (stat, red if >0, SECURITY ALERT)
   - Invalid Cursor Spike Alert Status (stat)
   - Top Offending Clients (table, if client_id tracked)

**Alert Indicators**: 3 alerts (SSEInvalidCursorSpike, SSENegativeCursorAttack, SSECursorValidationLatencyHigh)

---

### Updated Dashboard: **kernel_overview.json** (FIXES)

**Fix Broken Panels**:

1. **Replay Throughput** (line 327)
   - ❌ Old: `sum(rate(k0_kernel_replay_processed_total[$__interval]))`
   - ✅ New: `sum(rate(replay_processed_total[$__interval]))` (if metric exists)
   - **Alternative**: Remove panel if metric not instrumented

2. **WAL Lag** (line 397)
   - ❌ Old: `time() - k0_kernel_snapshot_watermark`
   - ✅ New: `time() - max(wal_position)` (if WAL position tracked)
   - **Alternative**: Use `increase(wal_entries_total[5m])` as proxy

3. **Outbox Backlog** (line 467)
   - ❌ Old: `sum(k0_kernel_outbox_pending_total)`
   - ✅ New: `sum(outbox_pending_entries)` (need to instrument)

4. **Active HTTP Connections** (line 932)
   - ❌ Old: `k0_kernel_active_connections`
   - ✅ New: Remove panel (not instrumented) OR add instrumentation

5. **Active SSE Subscriptions** (line 1025)
   - ❌ Old: `k0_kernel_sse_pending_events`
   - ✅ New: `sum(sse_active_subscriptions)` (need to instrument)

**Add New Panels**:
1. Replayer Parity Failures (time series, stacked by failure_type)
2. Gate Rejection Rate by Reason (time series)
3. Schema Cache Hit Rate (gauge, alert if <80%)

---

## 6. Implementation Roadmap

### Phase 1: Critical Fixes (2-3 hours)

**Priority**: Fix broken queries in `kernel_overview.json`

1. **Issue #039: Fix Broken Metrics in kernel_overview.json**
   - Audit all 11 panels
   - Fix 5 broken metric queries
   - Remove panels for non-existent metrics OR instrument missing metrics
   - Validate queries against Prometheus

### Phase 2: Epic 3.5 Dashboard (3-4 hours)

**Priority**: Add visibility for Epic 3.5 metrics

2. **Issue #040: Create DLQ & Outbox Operations Dashboard**
   - Create `dlq_outbox_operations.json`
   - 3 rows, 10 panels
   - 4 alert indicator panels
   - Link to runbooks (Gap 44, Gap 46)

3. **Issue #041: Create SSE & Cursor Validation Dashboard**
   - Create `sse_cursor_validation.json`
   - 3 rows, 8 panels
   - 3 alert indicator panels (including SECURITY alert)
   - Link to runbooks (Gap 48, Gap 39)

### Phase 3: Enhancements (2-3 hours, optional)

4. Add Replayer Parity panel to `kernel_overview.json`
5. Add Gate Rejection panel to `kernel_overview.json`
6. Audit `sse_health.json` and `replay_throughput.json` for broken queries
7. Create dashboard provisioning tests

---

## 7. Acceptance Criteria

### Issue #039: Fix Broken Metrics
- [ ] All 5 broken queries replaced with correct metrics or removed
- [ ] All panels show data in Grafana (no "No data" errors)
- [ ] Dashboard loads without errors
- [ ] Queries validated against Prometheus `/api/v1/query` endpoint

### Issue #040: DLQ & Outbox Dashboard
- [ ] Dashboard created with 10 panels across 3 rows
- [ ] All 4 alert indicators functional (DLQ + backoff alerts)
- [ ] Runbook links added for Gap 44, Gap 46
- [ ] Dashboard auto-refreshes every 30s
- [ ] Queries return data when DLQ/outbox activity present

### Issue #041: SSE & Cursor Validation Dashboard
- [ ] Dashboard created with 8 panels across 3 rows
- [ ] Security alert panel (negative cursor attack) highlighted in red
- [ ] All 3 alert indicators functional
- [ ] Runbook links added for Gap 48, Gap 39
- [ ] Dashboard auto-refreshes every 30s

---

## 8. Testing Strategy

### Unit Tests
- Validate JSON syntax for all dashboards
- Check all metric names exist in codebase
- Verify PromQL query syntax

### Integration Tests
1. Deploy dashboards to test Grafana instance
2. Generate test load (DLQ entries, invalid cursors, backoff events)
3. Verify all panels populate with data
4. Trigger alerts, verify alert indicators turn red
5. Validate dashboard links work

### Manual Tests
- Click through all runbook links
- Verify time series show correct data
- Check heatmaps render properly
- Validate stat panels have correct thresholds

---

## 9. Summary Statistics

**Current State**:
- 11 dashboards exist
- 5 broken queries in `kernel_overview.json` (45% panel failure rate)
- 0 dashboards for Epic 3.5 metrics (0% coverage for Gaps 38, 44, 46, 48)
- 2 P0 alerts visualized correctly (TOCTOU, pool saturation)
- 0 P2 alerts visualized (Epic 3.5 alerts)

**After Implementation**:
- 13 dashboards (2 new)
- 0 broken queries (100% working)
- 100% coverage for Epic 3.5 metrics (18 new panels)
- 10 P2 alerts visualized (Epic 3.5 alerts)
- Complete operational visibility for DLQ, outbox, SSE cursor validation

**Effort Estimate**: 7-10 hours total (Phase 1: 3h, Phase 2: 4h, Phase 3: 3h)

---

## 10. Related Documentation

- Implementation Roadmap: `docs/k0_implementation_roadmap.md`
- Alert Rules: `k0/deploy/generated/rules/slo_alerts.yaml` (Epic 3.5 alerts added)
- Gap Analysis: `docs/k0_architecture_gaps_analysis.md` (Gaps 38, 44, 46, 48)
- Runbooks: `docs/development/runbooks/` (need to create Epic 3.5 runbooks)

---

## Next Steps

1. **Create todo list** for Issues #039, #040, #041
2. **Fix broken queries** in kernel_overview.json (Issue #039)
3. **Create DLQ dashboard** (Issue #040)
4. **Create SSE dashboard** (Issue #041)
5. **Test in staging** environment
6. **Deploy to production** after validation
