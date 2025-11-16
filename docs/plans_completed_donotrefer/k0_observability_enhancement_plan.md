# K0 Observability Enhancement Plan

**Date**: 2025-11-11
**Status**: 🟡 PLANNING
**Owner**: Engineering Team
**Timeline**: 2-3 weeks (15-20 hours total effort)

---

## Executive Summary

**Current State**: 64% of dashboard panels show "No data" due to missing metrics instrumentation. Only 30% of planned metrics are implemented (HTTP path only).

**Target State**: 100% dashboard coverage with all operational metrics instrumented, Epic 3.5 metrics fixed, and complete observability for production operations.

**Business Impact**:

- ✅ Enable production monitoring and SLO tracking
- ✅ Detect incidents before customer impact
- ✅ Support capacity planning and performance optimization
- ✅ Provide debugging context for incidents

---

## Milestone 1: K0 Observability Complete Coverage

**Goal**: Achieve 100% functional observability with all metrics instrumented, dashboards working, and alerts firing correctly.

**Success Criteria**:

- [ ] All 15+ metrics instrumented and emitting data
- [ ] 100% dashboard panel success rate (0 "No data" errors)
- [ ] All 10+ P0/P2 alerts functional
- [ ] Recording rules producing aggregated metrics
- [ ] Production observability validated

**Timeline**: 2-3 weeks
**Total Effort**: 15-20 hours
**Dependencies**: None (foundational work)

---

## Epic 1: Metrics Instrumentation & Fixes (Foundational)

**Epic ID**: EPIC-OBS-001
**Priority**: 🔴 CRITICAL
**Goal**: Fix broken metrics and add missing instrumentation to enable dashboard functionality
**Timeline**: Week 1 (8-10 hours)
**Depends On**: None
**Blocks**: Epic 2 (Dashboard Coverage)

### Success Criteria

- [ ] All 8 Epic 3.5 metrics fixed (double prefix removed)
- [ ] All 7 core metrics instrumented (replay, WAL, outbox, etc.)
- [ ] All 4 recording rules fixed
- [ ] Metrics validated in Prometheus
- [ ] Unit tests for metric emission added

---

### Issue #042: Fix Epic 3.5 Double Prefix Bug

**Priority**: 🔴 CRITICAL
**Effort**: 1 hour
**Assignee**: TBD
**Labels**: `bug`, `observability`, `metrics`, `epic-3.5`

#### Problem

Epic 3.5 metrics have double prefix (`k0_kernel_k0_*` instead of `k0_kernel_*`) because:

- Metrics emitted with manual `k0_` prefix: `self._metrics.emit("k0_dlq_entries_by_state", ...)`
- MetricsExporter automatically adds namespace: `k0_kernel_`
- Result: `k0_kernel_k0_dlq_entries_by_state` ❌

#### Affected Metrics (8 total)

- `k0_kernel_k0_dlq_entries_by_state` → should be `k0_kernel_dlq_entries_by_state`
- `k0_kernel_k0_dlq_retry_attempts_total`
- `k0_kernel_k0_dlq_requeue_latency_seconds`
- `k0_kernel_k0_dlq_entries_abandoned_total`
- `k0_kernel_k0_outbox_retry_backoff_exponent`
- `k0_kernel_k0_outbox_backoff_sleep_seconds`
- `k0_kernel_k0_sse_invalid_cursor_total`
- `k0_kernel_k0_sse_cursor_validation_seconds`

#### Files to Fix

1. `k0/storage/dlq.py` (lines 96, 103, 110)
2. `k0/outbox/worker.py` (backoff metrics)
3. `k0/sse/server.py` (cursor validation metrics)

#### Implementation Tasks

- [ ] Remove `k0_` prefix from emit calls in `storage/dlq.py`
- [ ] Remove `k0_` prefix from emit calls in `outbox/worker.py`
- [ ] Remove `k0_` prefix from emit calls in `sse/server.py`
- [ ] Validate correct metric names in Prometheus
- [ ] Update dashboard queries to use correct names (if needed)
- [ ] Test metric emission with unit tests

#### Example Fix

```python
# BEFORE (wrong)
self._metrics.emit("k0_dlq_entries_by_state", value, state="PENDING")

# AFTER (correct)
self._metrics.emit("dlq_entries_by_state", value, state="PENDING")
```

#### Acceptance Criteria

- [ ] All 8 metrics emit with single prefix `k0_kernel_*`
- [ ] Prometheus query `{__name__=~"k0_kernel_k0_.*"}` returns zero results
- [ ] Prometheus query `k0_kernel_dlq_entries_by_state` returns data
- [ ] Unit tests verify correct metric names

#### Testing Strategy

```bash
# Start kernel
python -m k0.kernel.app

# Generate DLQ/outbox/SSE activity
curl -X POST http://localhost:8000/command -d '...'

# Query Prometheus
curl http://localhost:9090/api/v1/query?query=k0_kernel_dlq_entries_by_state

# Verify no double prefix
curl http://localhost:9090/api/v1/query?query={__name__=~"k0_kernel_k0_.*"}
```

#### Dependencies

- Blocks: Issue #040, #041 (dashboards need correct metric names)

---

### Issue #043: Add Core Replay Metrics

**Priority**: 🔴 CRITICAL
**Effort**: 30 minutes
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `metrics`, `replay`

#### Problem

Dashboard queries `k0_kernel_replay_processed_total` but metric is never emitted. Results in "No data" for Replay Throughput panel in kernel_overview.json.

#### Metrics to Add

- `replay_processed_total` (counter) - Total replay events processed
- Labels: `driver`, `outcome` (success/error)

#### Files to Modify

1. `k0/storage/replayer.py` - Add instrumentation in `process()` method

#### Implementation

```python
# k0/storage/replayer.py
async def process(self, entry: ReplayEntry) -> None:
    start = time.perf_counter()
    try:
        # ... existing replay logic ...

        if self._metrics:
            self._metrics.emit(
                "replay_processed_total",
                1.0,
                driver=entry.driver,
                outcome="success"
            )
    except Exception as e:
        if self._metrics:
            self._metrics.emit(
                "replay_processed_total",
                1.0,
                driver=entry.driver,
                outcome="error"
            )
        raise
```

#### Acceptance Criteria

- [ ] `k0_kernel_replay_processed_total` metric exists in Prometheus
- [ ] Metric increments on each replay event
- [ ] Labels include driver and outcome
- [ ] Dashboard "Replay Throughput" panel shows data
- [ ] Unit test verifies metric emission

#### Testing Strategy

```bash
# Trigger replay
python -m k0.scripts.trigger_replay

# Query Prometheus
curl http://localhost:9090/api/v1/query?query=k0_kernel_replay_processed_total

# Verify rate calculation
curl http://localhost:9090/api/v1/query?query=rate(k0_kernel_replay_processed_total[5m])
```

---

### Issue #044: Add WAL Watermark Metrics

**Priority**: 🟡 HIGH
**Effort**: 45 minutes
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `metrics`, `wal`

#### Problem

Dashboard calculates WAL lag as `time() - k0_kernel_snapshot_watermark` but metric never emitted. Results in "No data" for WAL Lag panel.

#### Metrics to Add

- `snapshot_watermark` (gauge) - Latest snapshot WAL position
- `wal_current_position` (gauge) - Current WAL write position

#### Files to Modify

1. `k0/storage/snapshots.py` - Add instrumentation in `save_snapshot()`
2. `k0/storage/wal.py` - Add instrumentation in `append()`

#### Implementation

```python
# k0/storage/snapshots.py
async def save_snapshot(self, snapshot: Snapshot) -> None:
    # ... existing code ...

    if self._metrics:
        self._metrics.set_gauge(
            "snapshot_watermark",
            float(snapshot.wal_position)
        )

# k0/storage/wal.py
async def append(self, entry: WALEntry) -> int:
    # ... existing code ...
    position = await self._write(entry)

    if self._metrics:
        self._metrics.set_gauge(
            "wal_current_position",
            float(position)
        )

    return position
```

#### Acceptance Criteria

- [ ] `k0_kernel_snapshot_watermark` metric exists
- [ ] `k0_kernel_wal_current_position` metric exists
- [ ] Dashboard "WAL Lag" panel shows data
- [ ] WAL lag calculated as `wal_current_position - snapshot_watermark`
- [ ] Unit tests verify metric emission

---

### Issue #045: Add Outbox Metrics

**Priority**: 🟡 HIGH
**Effort**: 1 hour
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `metrics`, `outbox`

#### Problem

Two critical outbox metrics missing:

1. `k0_kernel_outbox_pending_total` - Dashboard shows "No data"
2. `k0_kernel_outbox_apply_total` - Cannot track delivery outcomes

#### Metrics to Add

- `outbox_pending_total` (gauge) - Count of pending outbox entries
- `outbox_apply_total` (counter) - Total apply attempts by outcome
- Labels: `driver`, `outcome` (success/retry/abandoned)

#### Files to Modify

1. `k0/storage/outbox.py` - Add pending count instrumentation
2. `k0/outbox/worker.py` - Add apply outcome instrumentation

#### Implementation

```python
# k0/storage/outbox.py
async def save(self, entries: List[OutboxEntry]) -> None:
    # ... existing code ...

    if self._metrics:
        pending_count = await self._count_pending()
        self._metrics.set_gauge("outbox_pending_total", float(pending_count))

# k0/outbox/worker.py
def _handle_success(self, entry: OutboxEntry, alias: str) -> None:
    # ... existing code ...
    self._emit_metric("outbox_apply_total", 1.0, outcome="success", driver=alias)

def _handle_failure(self, entry: OutboxEntry, alias: str, retry: bool) -> None:
    # ... existing code ...
    outcome = "retry" if retry else "abandoned"
    self._emit_metric("outbox_apply_total", 1.0, outcome=outcome, driver=alias)
```

#### Acceptance Criteria

- [ ] `k0_kernel_outbox_pending_total` shows current backlog
- [ ] `k0_kernel_outbox_apply_total` tracks all outcomes
- [ ] Dashboard "Outbox Backlog" panel shows data
- [ ] Alert `OutboxBacklogGrowing` can fire
- [ ] Unit tests verify metric emission

---

### Issue #046: Add Connection & SSE Metrics

**Priority**: 🟢 MEDIUM
**Effort**: 1.5 hours
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `metrics`, `sse`, `http`

#### Problem

Two capacity planning metrics missing:

1. `k0_kernel_active_connections` - HTTP connection count
2. `k0_kernel_sse_active_subscriptions` - SSE subscriber count (wrong name: `sse_pending_events`)

#### Metrics to Add

- `active_connections` (gauge) - Active HTTP connections
- `sse_active_subscriptions` (gauge) - Active SSE subscriptions

#### Files to Modify

1. `k0/kernel/app.py` - Add connection tracking middleware
2. `k0/sse/server.py` - Add subscription count tracking

#### Implementation

```python
# k0/kernel/app.py
active_connections = 0

async def telemetry_chain(request: Request, call_next):
    global active_connections
    active_connections += 1
    metrics.set_gauge("active_connections", float(active_connections))

    try:
        response = await call_next(request)
        return response
    finally:
        active_connections -= 1
        metrics.set_gauge("active_connections", float(active_connections))

# k0/sse/server.py
async def subscribe(self, cursor: int, filters: dict) -> None:
    # ... existing code ...

    if self._metrics:
        self._metrics.set_gauge(
            "sse_active_subscriptions",
            float(len(self._active_subscriptions))
        )
```

#### Acceptance Criteria

- [ ] `k0_kernel_active_connections` tracks HTTP connections
- [ ] `k0_kernel_sse_active_subscriptions` tracks SSE subscribers
- [ ] Dashboard panels show data
- [ ] Metrics update on connect/disconnect
- [ ] Unit tests verify metric emission

---

### Issue #047: Add UoW Commit Metrics

**Priority**: 🟡 HIGH
**Effort**: 45 minutes
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `metrics`, `uow`

#### Problem

Dashboard queries `k0_kernel_uow_commit_seconds` but metric never emitted. Cannot monitor transaction commit latency.

#### Metrics to Add

- `uow_commit_seconds` (histogram) - Commit latency distribution
- Labels: `outcome` (success/rollback)

#### Files to Modify

1. `k0/uow/unit_of_work.py` - Add instrumentation in `commit()` and `rollback()`

#### Implementation

```python
# k0/uow/unit_of_work.py
async def commit(self) -> None:
    start = time.perf_counter()
    try:
        # ... existing commit logic ...

        duration = time.perf_counter() - start
        if self._metrics:
            self._metrics.observe(
                "uow_commit_seconds",
                duration,
                outcome="success"
            )
    except Exception as e:
        if self._metrics:
            duration = time.perf_counter() - start
            self._metrics.observe(
                "uow_commit_seconds",
                duration,
                outcome="rollback"
            )
        raise
```

#### Acceptance Criteria

- [ ] `k0_kernel_uow_commit_seconds` metric exists
- [ ] Histogram buckets configured: [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
- [ ] P95/P99 latency calculable
- [ ] Dashboard shows commit latency distribution
- [ ] Unit tests verify metric emission

---

### Issue #048: Fix Recording Rules

**Priority**: 🟢 MEDIUM
**Effort**: 1 hour
**Assignee**: TBD
**Labels**: `bug`, `observability`, `prometheus`, `recording-rules`

#### Problem

4 recording rules broken due to wrong metric names or non-existent base metrics:

1. `job:k0_replay_throughput:rate5m` - Base metric missing
2. `job:k0_outbox_pending:ratio` - Base metric missing
3. `job:k0_wal_commits:rate5m` - Wrong metric name
4. `job:k0_wal_fsync_duration_seconds:p95:5m` - Wrong metric name

#### Files to Modify

1. `k0/deploy/generated/rules/recording_rules.yaml`

#### Implementation

```yaml
# Fix recording rules with correct metric names

# Rule 1: Replay throughput (depends on Issue #043)
- record: job:k0_replay_throughput:rate5m
  expr: sum(rate(k0_kernel_replay_processed_total[5m])) by (job)

# Rule 2: Outbox pending ratio (depends on Issue #045)
- record: job:k0_outbox_pending:ratio
  expr: sum(k0_kernel_outbox_pending_total) / 1000

# Rule 3: WAL commit rate (fix metric name)
- record: job:k0_wal_commits:rate5m
  expr: sum(rate(k0_kernel_uow_commit_total[5m])) by (job)

# Rule 4: WAL fsync P95 (fix metric name)
- record: job:k0_wal_fsync_duration_seconds:p95:5m
  expr: histogram_quantile(0.95, rate(k0_kernel_uow_fsync_seconds_bucket[5m]))
```

#### Acceptance Criteria

- [ ] All 4 recording rules produce output
- [ ] Recording rule queries work in Prometheus
- [ ] Dashboards using recording rules show data
- [ ] Recording rules tested with `promtool check rules`
- [ ] Documentation updated with rule descriptions

#### Dependencies

- Depends On: Issue #043 (replay metrics), Issue #045 (outbox metrics), Issue #047 (UoW metrics)

---

## Epic 2: Dashboard & Visualization Coverage

**Epic ID**: EPIC-OBS-002
**Priority**: 🟡 HIGH
**Goal**: Fix broken dashboards and create new dashboards for Epic 3.5 metrics
**Timeline**: Week 2 (7-10 hours)
**Depends On**: Epic 1 (metrics must work first)

### Success Criteria

- [ ] All broken dashboard panels fixed
- [ ] 2 new dashboards created for Epic 3.5 metrics
- [ ] 100% panel success rate (0 "No data" errors)
- [ ] All alert indicators functional
- [ ] Runbook links added

---

### Issue #039: Fix Broken Metrics in kernel_overview.json

**Priority**: 🔴 CRITICAL
**Effort**: 2-3 hours
**Assignee**: TBD
**Labels**: `bug`, `observability`, `dashboard`, `grafana`

#### Problem

5 out of 11 panels in kernel_overview.json show "No data" (45% failure rate) due to wrong metric names or missing metrics.

#### Broken Panels (5 total)

| Panel Title | Line | Broken Metric | Fix Required |
|------------|------|---------------|--------------|
| Replay Throughput | 327 | `k0_kernel_replay_processed_total` | Update after Issue #043 |
| WAL Lag | 397 | `k0_kernel_snapshot_watermark` | Update after Issue #044 |
| Outbox Backlog | 467 | `k0_kernel_outbox_pending_total` | Update after Issue #045 |
| Active HTTP Connections | 932 | `k0_kernel_active_connections` | Update after Issue #046 |
| Active SSE Subscriptions | 1025 | `k0_kernel_sse_pending_events` | Fix name: `sse_active_subscriptions` |

#### Files to Modify

1. `k0/deploy/generated/dashboards/kernel_overview.json`

#### Implementation Tasks

- [ ] Audit all 11 panels in kernel_overview.json
- [ ] Update 5 broken metric queries with correct names
- [ ] Add new panels: Replayer Parity Failures, Gate Rejections, Schema Cache Hit Rate
- [ ] Validate queries against Prometheus
- [ ] Test dashboard loads without errors
- [ ] Add panel descriptions and runbook links

#### Acceptance Criteria

- [ ] All 11 existing panels show data (100% success)
- [ ] 3 new panels added (14 total panels)
- [ ] Dashboard loads in <2 seconds
- [ ] All queries validated with `promtool query`
- [ ] Runbook links functional

#### Testing Strategy

```bash
# Validate dashboard JSON
jq . k0/deploy/generated/dashboards/kernel_overview.json

# Test queries in Prometheus
for query in $(jq -r '.panels[].targets[].expr' kernel_overview.json); do
  curl "http://localhost:9090/api/v1/query?query=$query"
done

# Load dashboard in Grafana
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @kernel_overview.json
```

#### Dependencies

- Depends On: Issue #042, #043, #044, #045, #046 (metrics must exist)

---

### Issue #040: Create DLQ & Outbox Operations Dashboard

**Priority**: 🟡 HIGH
**Effort**: 3-4 hours
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `dashboard`, `grafana`, `epic-3.5`

#### Problem

No dashboard for Epic 3.5 DLQ and outbox backoff metrics. Cannot monitor dead letter queue health, retry exhaustion, or exponential backoff behavior.

#### Dashboard Structure

**File**: `k0/deploy/generated/dashboards/dlq_outbox_operations.json`

**3 Rows, 10 Panels**:

**Row 1: DLQ Health Overview**

1. DLQ Entries by State (time series, stacked: PENDING/REQUEUED/ABANDONED)
2. Abandoned Entries Alert Status (stat, red if firing)
3. Total Retry Attempts (counter)

**Row 2: DLQ Performance**
4. Requeue Latency P95 (gauge, threshold: 500ms)
5. Requeue Latency Heatmap (heatmap by driver)
6. Retry Rate by Driver (time series)

**Row 3: Outbox Backoff Monitoring**
7. Backoff Exponent by Driver (time series, log scale)
8. Max Backoff Exponent (stat, red if >10)
9. Backoff Sleep Duration Distribution (heatmap)
10. Exponential Growth Alert Status (stat)

#### Alert Indicators (4)

- DLQAbandonedEntriesDetected (P2)
- DLQPendingQueueGrowing (P2)
- OutboxBackoffExponentialGrowthCritical (P2)
- OutboxBackoffSleepDurationHigh (P2)

#### Acceptance Criteria

- [ ] Dashboard created with 10 panels across 3 rows
- [ ] All panels show data when DLQ/outbox activity present
- [ ] 4 alert indicators functional
- [ ] Runbook links added for Gap 44, Gap 46
- [ ] Dashboard auto-refreshes every 30s
- [ ] Time range selector working

#### Testing Strategy

```bash
# Generate DLQ entries
python -m k0.scripts.generate_dlq_entries

# Trigger outbox backoff
python -m k0.scripts.trigger_outbox_backoff

# Verify dashboard
curl http://localhost:3000/api/dashboards/uid/dlq-outbox-ops
```

#### Dependencies

- Depends On: Issue #042 (double prefix fix for Epic 3.5 metrics)

---

### Issue #041: Create SSE & Cursor Validation Dashboard

**Priority**: 🟡 HIGH
**Effort**: 3-4 hours
**Assignee**: TBD
**Labels**: `enhancement`, `observability`, `dashboard`, `grafana`, `epic-3.5`, `security`

#### Problem

No dashboard for Epic 3.5 SSE cursor validation metrics. Cannot monitor cursor validation failures, negative cursor attacks, or security events.

#### Dashboard Structure

**File**: `k0/deploy/generated/dashboards/sse_cursor_validation.json`

**3 Rows, 8 Panels**:

**Row 1: SSE Overview**

1. Active SSE Subscriptions (stat)
2. SSE Connection Rate (time series)
3. SSE Disconnection Rate (time series)

**Row 2: Cursor Validation**
4. Invalid Cursor Rate by Reason (time series, stacked: MALFORMED/NEGATIVE)
5. Cursor Validation Latency P95 (gauge)
6. Validation Latency Histogram (heatmap)

**Row 3: Security Events**
7. Negative Cursor Attack Detection (stat, red if >0, **SECURITY ALERT**)
8. Invalid Cursor Spike Alert Status (stat)

#### Alert Indicators (3)

- SSEInvalidCursorSpike (P2)
- SSENegativeCursorAttack (P1 - **SECURITY**)
- SSECursorValidationLatencyHigh (P2)

#### Acceptance Criteria

- [ ] Dashboard created with 8 panels across 3 rows
- [ ] Security alert panel highlighted in red
- [ ] All 3 alert indicators functional
- [ ] Runbook links added for Gap 48, Gap 39
- [ ] Dashboard auto-refreshes every 30s
- [ ] Security event panel triggers incident workflow

#### Testing Strategy

```bash
# Generate invalid cursors
python -m k0.scripts.generate_invalid_cursors

# Trigger negative cursor attack
curl -X GET http://localhost:8000/sse/subscribe?cursor=-1

# Verify dashboard
curl http://localhost:3000/api/dashboards/uid/sse-cursor-validation
```

#### Dependencies

- Depends On: Issue #042 (double prefix fix for Epic 3.5 metrics)

---

## Implementation Roadmap

### Week 1: Metrics Instrumentation (Epic 1)

**Day 1-2**: Critical Fixes

- [ ] Issue #042: Fix double prefix bug (1h)
- [ ] Issue #043: Add replay metrics (30m)
- [ ] Issue #044: Add WAL metrics (45m)
- [ ] Issue #045: Add outbox metrics (1h)

**Day 3-4**: Remaining Instrumentation

- [ ] Issue #047: Add UoW metrics (45m)
- [ ] Issue #046: Add connection/SSE metrics (1.5h)
- [ ] Issue #048: Fix recording rules (1h)

**Day 5**: Testing & Validation

- [ ] Run full test suite
- [ ] Validate metrics in Prometheus
- [ ] Performance testing
- [ ] Documentation updates

### Week 2: Dashboard Coverage (Epic 2)

**Day 1-2**: Fix Existing Dashboards

- [ ] Issue #039: Fix kernel_overview.json (2-3h)

**Day 3-4**: New Dashboards

- [ ] Issue #040: Create DLQ dashboard (3-4h)
- [ ] Issue #041: Create SSE dashboard (3-4h)

**Day 5**: Testing & Deployment

- [ ] Integration testing
- [ ] Load testing with dashboards
- [ ] Staging deployment
- [ ] Production deployment

---

## Risk Management

### High Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Metrics cause performance regression | HIGH | Add performance tests, limit cardinality |
| Double prefix fix breaks existing queries | MEDIUM | Audit all dashboard/alert queries first |
| Dashboard load time too high | MEDIUM | Use recording rules for expensive queries |
| Cardinality explosion | HIGH | Limit label values, add cardinality tests |

### Rollback Plan

**If metrics cause issues**:

1. Feature flag to disable metric emission
2. Revert instrumentation changes
3. Monitor for performance impact
4. Gradual rollout by component

---

## Testing Strategy

### Unit Tests

- [ ] Test metric emission for all new metrics
- [ ] Verify correct metric names (no double prefix)
- [ ] Test label values within expected ranges
- [ ] Validate histogram bucket configurations

### Integration Tests

- [ ] Deploy to staging environment
- [ ] Generate load across all components
- [ ] Verify all metrics appear in Prometheus
- [ ] Trigger alerts and verify alert manager receives them
- [ ] Load dashboards and verify all panels populate

### Performance Tests

- [ ] Measure overhead of metric emission (<1ms P95)
- [ ] Verify cardinality within limits (<10K unique series)
- [ ] Test dashboard query performance (<2s load time)
- [ ] Load test with metrics enabled vs disabled

### Manual Tests

- [ ] Click through all dashboards
- [ ] Verify all runbook links work
- [ ] Test alert indicator behavior
- [ ] Validate time range selectors
- [ ] Check dashboard auto-refresh

---

## Success Metrics

### Quantitative

- **Dashboard Coverage**: 0% → 100% (0 "No data" panels)
- **Metric Instrumentation**: 30% → 100% (15+ metrics)
- **Alert Functionality**: 2/10 → 10/10 alerts working
- **Panel Success Rate**: 36% → 100% (kernel_overview.json)

### Qualitative

- ✅ Engineers can debug incidents with metrics
- ✅ SLO tracking fully operational
- ✅ Capacity planning enabled
- ✅ Security events visible in real-time

---

## Documentation Requirements

### ADRs (GATE 1)

- [ ] Search for existing observability ADRs
- [ ] Create ADR if metrics schema changed significantly

### Contracts (GATE 2)

- [ ] Validate Prometheus metric naming conventions
- [ ] Document histogram bucket configurations
- [ ] Update metrics catalog

### Implementation (GATE 3)

- [ ] Code comments reference metrics purpose
- [ ] Performance budget documented
- [ ] Cardinality limits documented

### Tests (GATE 4)

- [ ] Test coverage >80% for metric emission
- [ ] Integration tests for all dashboards

### Memory (GATE 5)

- [ ] Create memory entry with decisions and file references
- [ ] Link to related ADRs
- [ ] Update architecture diagrams if needed

---

## Dependencies & Blockers

### External Dependencies

- Prometheus running and accessible
- Grafana running and configured
- Alert manager configured

### Internal Dependencies

```
Epic 1 (Instrumentation)
  ├─ Issue #042 (Double Prefix) [CRITICAL, NO DEPS]
  ├─ Issue #043 (Replay Metrics) [CRITICAL, NO DEPS]
  ├─ Issue #044 (WAL Metrics) [HIGH, NO DEPS]
  ├─ Issue #045 (Outbox Metrics) [HIGH, NO DEPS]
  ├─ Issue #046 (Connection/SSE) [MEDIUM, NO DEPS]
  ├─ Issue #047 (UoW Metrics) [HIGH, NO DEPS]
  └─ Issue #048 (Recording Rules) [MEDIUM, depends on #043, #045, #047]

Epic 2 (Dashboards) [depends on Epic 1]
  ├─ Issue #039 (Fix kernel_overview) [CRITICAL, depends on #042-#047]
  ├─ Issue #040 (DLQ Dashboard) [HIGH, depends on #042]
  └─ Issue #041 (SSE Dashboard) [HIGH, depends on #042]
```

---

## Related Documentation

- **Gap Analysis**: `docs/grafana_dashboard_gap_analysis.md`
- **Root Cause**: `docs/dashboard_empty_graphs_root_cause.md`
- **Implementation Roadmap**: `docs/k0_implementation_roadmap.md` (if exists)
- **Alert Rules**: `k0/deploy/generated/rules/slo_alerts.yaml`
- **Recording Rules**: `k0/deploy/generated/rules/recording_rules.yaml`
- **Runbooks**: `docs/development/runbooks/` (to be created)

---

## Next Steps

1. **Review Plan**: Team review and approval
2. **Create Issues**: Create GitHub issues for all 8 tasks
3. **Assign Work**: Assign issues to engineers
4. **Start Week 1**: Begin with Issue #042 (double prefix fix)
5. **Daily Standups**: Track progress, blockers, dependencies
6. **Weekly Demo**: Show working dashboards at end of each week
