# K0 Gap Runbooks

**Purpose**: Incident response runbooks for P0/P1/P2 gaps discovered in K0 V1 production readiness analysis.

**Source**: [K0 Architecture Gaps Analysis](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_architecture_gaps_analysis.md)

**Implementation Plan**: [K0 Implementation Roadmap](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_implementation_roadmap.md)

---

## Quick Reference

| Gap | Priority | Alert | Runbook | Status |
|-----|----------|-------|---------|--------|
| **27** | P0 - CRITICAL | `IdempotencyDuplicateCommitCritical` | [gap-27-toctou-race.md](gap-27-toctou-race.md) | 🔴 Not Fixed |
| **28** | P0 - CRITICAL | `SQLiteConnectionPoolExhausted` | [gap-28-connection-leak.md](gap-28-connection-leak.md) | 🔴 Not Fixed |

---

## P0 BLOCKER Alerts

### Gap 27: Idempotency TOCTOU Race

- **Symptom**: `k0_idem_toctou_race_detected_total` increasing
- **Impact**: Data corruption, duplicate commits
- **Alert**: Fires when `>= 5` races in 5 minutes
- **Mitigation**: Enable `K0_TOCTOU_FIX_ENABLED=true` or reduce concurrency
- **Runbook**: [gap-27-toctou-race.md](gap-27-toctou-race.md)

### Gap 28: UnitOfWork Connection Leak

- **Symptom**: `k0_sqlite_pool_saturation_ratio > 0.90`
- **Impact**: Request failures, deadlocks, system unresponsive
- **Alert**: Fires when saturation > 90% for 1 minute
- **Mitigation**: Restart kernel or increase pool size (temporary)
- **Runbook**: [gap-28-connection-leak.md](gap-28-connection-leak.md)

---

## Dashboards

- **P0 Blocker Dashboard**: [http://localhost:3000/d/p0-blockers](http://localhost:3000/d/p0-blockers)
  - Panel 1: Gap 27 TOCTOU race rate (5min window)
  - Panel 2: Gap 28 connection pool saturation (current + trend)
  - Panel 3: Signature verification failures (Gap 19 related)
  - Auto-refresh: 10 seconds

---

## Alert Routing

All P0 alerts are configured in `k0/deploy/generated/rules/slo_alerts.yaml`:

```yaml
# Gap 27: TOCTOU Race
- alert: IdempotencyDuplicateCommitCritical
  expr: increase(k0_idem_toctou_race_detected_total[5m]) >= 5
  labels:
    severity: critical
    priority: P0
    gap: gap-27

# Gap 28: Connection Leak
- alert: SQLiteConnectionPoolExhausted
  expr: k0_sqlite_pool_saturation_ratio > 0.90
  labels:
    severity: critical
    priority: P0
    gap: gap-28
```

---

## Incident Response Workflow

### 1. Alert Fires

- Check Slack: `#k0-alerts-sre`
- Open P0 Blocker Dashboard: [http://localhost:3000/d/p0-blockers](http://localhost:3000/d/p0-blockers)

### 2. Identify Gap

- Check alert labels: `gap=gap-27` or `gap=gap-28`
- Open corresponding runbook

### 3. Follow Runbook

- **Investigation**: Verify alert, identify scope, analyze root cause
- **Mitigation**: Immediate actions (< 5 minutes)
- **Communication**: Notify stakeholders in `#k0-alerts-sre`

### 4. Post-Incident

- Update incident history in runbook
- Create GitHub issue if new pattern discovered
- Update metrics/alerts if needed

---

## Future Runbooks (Milestone 2-3)

### P1 Gaps (Planned - Issue #017)

- Gap 30: Schema cache thread safety
- Gap 33: Replayer parity verification
- Gap 35: REVOKED key rejection

### P2 Gaps (Planned - Issue #017)

- Gap 38: DLQ max retry logic
- Gap 39: SSE negative cursor validation
- Gap 40: Pool timeout interrupt cleanup

---

## Related Documentation

- [K0 Implementation Roadmap - Epic 1.2](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_implementation_roadmap.md#epic-12-critical-alerting--monitoring-4h)
- [K0 Architecture Gaps Analysis](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_architecture_gaps_analysis.md)
- [P0 Alert Configuration (slo_alerts.yaml)](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/k0/deploy/generated/rules/slo_alerts.yaml)
- [P0 Blocker Dashboard (p0_blockers.json)](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/k0/deploy/generated/dashboards/p0_blockers.json)

---

**Last Updated**: 2025-11-11
**Document Owner**: SRE Team
**Epic**: [Epic 1.2 - Critical Alerting & Monitoring](https://github.com/Pkansagra-hub/family-os/blob/k0-Strengthning/docs/k0_implementation_roadmap.md#epic-12-critical-alerting--monitoring-4h)
