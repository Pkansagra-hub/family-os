# K0/K1 Runbooks - Incident Response Procedures

This directory contains operational runbooks for investigating and mitigating production issues in the K0 microkernel and K1 orchestration layer.

## Priority Levels

- **P0 (CRITICAL)**: Data corruption, resource leaks, production blockers
- **P1 (HIGH)**: Security vulnerabilities, race conditions, monitoring gaps
- **P2 (MEDIUM)**: Edge cases, operational stability issues
- **P3 (LOW)**: Future enhancements, nice-to-have features

---

## P0 - CRITICAL BLOCKERS

| Runbook | Gap/Module | Component | Symptoms |
|---------|------------|-----------|----------|
| [Gap 27: Idempotency TOCTOU Race](gap-27-toctou-race.md) | 27 | `k0/ports/command.py`, `k0/idem/` | Duplicate WAL entries, `k0_idem_toctou_race_detected_total` metric increasing |
| [Gap 28: UnitOfWork Connection Leak](gap-28-connection-leak.md) | 28 | `k0/uow/unit_of_work.py` | Pool exhaustion, `sqlite_pool_saturation_ratio` → 1.0, timeouts |
| [SessionState Memory Management](sessionstate.md) | SessionState | `k1/sessionstate/` | Memory pressure, emergency mode, eviction failures, SLO breaches |

---

## P1 - HIGH PRIORITY

| Runbook | Gap | Component | Symptoms |
|---------|-----|-----------|----------|
| Gap 30: Schema Cache Race | 30 | `k0/gate/schema_registry.py` | Thread safety violations, schema fetch failures |
| Gap 33: Replayer Receipt Parity | 33 | `k0/storage/replayer.py` | Missing receipts after replay |
| Gap 35: Revoked Key Enforcement | 35 | `k0/security/key_management.py` | Revoked keys still accepted |
| Gap 38: DLQ Infinite Retry | 38 | `k0/outbox/` | Outbox entries retried infinitely |
| Gap 39: SSE Negative Cursor | 39 | `k0/sse/server.py` | SSE cursor validation errors |

---

## Quick Reference

### Common Investigation Commands

```bash
# Check system health
curl http://localhost:9090/metrics | grep -E "(k0_|sqlite_pool_)"

# View recent errors
kubectl logs -l app=k0-kernel --since=10m | grep -E "(ERROR|CRITICAL)"

# Database inspection
kubectl exec -it k0-kernel-0 -- sqlite3 /data/k0.db

# Pool saturation
curl http://localhost:9090/metrics | grep sqlite_pool_saturation_ratio
```

### Alert Routing

| Alert Pattern | Severity | Runbook |
|---------------|----------|---------|
| `K0IdempotencyTOCTOURaceDetected` | critical | [gap-27-toctou-race.md](gap-27-toctou-race.md) |
| `K0PoolSaturationHigh` | critical | [gap-28-connection-leak.md](gap-28-connection-leak.md) |
| `K0CommandLatencyTrendIncreasing` | warning | Anomaly detection response |
| `K0TrafficSpikeAnomaly` | warning | Anomaly detection response |
| `SessionStateMemoryWarning` | warning | [sessionstate.md](sessionstate.md#21-sessionstatememorywarning) |
| `SessionStateMemoryCritical` | critical | [sessionstate.md](sessionstate.md#22-sessionstatememorcritical) |
| `SessionStateEmergencyActivated` | critical | [sessionstate.md](sessionstate.md#23-sessionstateemergencyactivated) |
| `SessionStateReconstructionSLABreach` | warning | [sessionstate.md](sessionstate.md#24-sessionstatereconstructionslabreach) |
| `SessionStateEvictionFailure` | critical | [sessionstate.md](sessionstate.md#25-sessionstateevictionfailure) |
| `SessionStateLatencySLOBreach` | warning | [sessionstate.md](sessionstate.md#26-sessionstatelatencyslobreach) |

---

## Runbook Template

Each runbook follows this structure:

1. **Symptoms**: Observable behavior (metrics, logs, errors)
2. **Root Cause**: Technical explanation of the issue
3. **Investigation Steps**: Commands to diagnose the problem
4. **Mitigation Steps**: Immediate actions (< 5 min), short-term fixes (< 1 hour)
5. **Verification**: How to confirm the fix works
6. **Prevention**: Long-term guards and improvements
7. **Related Documentation**: Links to ADRs, code, issues

---

## Contact

- **On-Call Team**: kernel-oncall@familyos.dev
- **Slack Channel**: #k0-incidents
- **Issue Tracker**: https://github.com/Pkansagra-hub/family-os/issues
- **Documentation**: `docs/architecture/decisions/` (ADRs)

---

## Contributing

When adding new runbooks:

1. Follow the template structure above
2. Include concrete commands (not pseudocode)
3. Add verification steps with expected output
4. Link to related ADRs and code locations
5. Update this README index

### File Naming Convention

`gap-{NUMBER}-{short-description}.md`

Example: `gap-27-toctou-race.md`
