# Runbook: SessionState - K1 Memory Management

**Module**: `k1/sessionstate`
**Owner**: K1 Kernel Team
**Priority**: P0 (CRITICAL) - Core memory management component
**Alert Configuration**: `k1/sessionstate/alerts.yaml`
**Policy Contract**: `k1/contracts/schemas/runtime/sessionstate.policies.yaml`

---

## Overview

SessionState is the 96KB edge-first memory system that manages conversational context for the K1 kernel. It uses a tiered architecture (HOT → WARM → LOCAL COLD) with pressure-based eviction to maintain strict memory bounds.

### Architecture Summary

| Tier | Size | Sections | Evictable | Purpose |
|------|------|----------|-----------|---------|
| HOT | 48KB | 8 | Partial | Active turn data, control, scoreboard |
| WARM | 48KB | 4 | Yes | Recent history, archived beliefs |
| LOCAL COLD | Disk | - | N/A | SQLite checkpoint storage |

### Pressure Levels

| Level | Utilization | Action | Description |
|-------|-------------|--------|-------------|
| NORMAL | <80% | None | Healthy operation |
| ELEVATED | 80-90% | Soft eviction | Proactive cleanup |
| CRITICAL | 90-95% | Hard eviction | Aggressive cleanup |
| EMERGENCY | >95% | Reject mutations | Data loss prevention |

---

## Quick Reference

### Key Metrics

```promql
# Memory utilization
sessionstate_total_size_bytes / 98304

# Pressure level (0=NORMAL, 1=ELEVATED, 2=CRITICAL, 3=EMERGENCY)
sessionstate_pressure_level{tier="total"}

# Eviction success rate
sum(rate(sessionstate_evictions_total{result="success"}[5m])) / sum(rate(sessionstate_evictions_total[5m]))

# Read latency P95
histogram_quantile(0.95, rate(sessionstate_read_latency_seconds_bucket{tier="hot"}[5m]))
```

### Common Investigation Commands

```bash
# Check current memory utilization
curl http://localhost:9090/metrics | grep sessionstate_total_size_bytes

# Check pressure level
curl http://localhost:9090/metrics | grep sessionstate_pressure_level

# View recent SessionState logs
kubectl logs -l app=k1-kernel --since=10m | grep -E "sessionstate\."

# Check eviction activity
curl http://localhost:9090/metrics | grep sessionstate_evictions_total
```

---

## 2. Alert Response Procedures

### 2.1 SessionStateMemoryWarning

**Alert**: `SessionStateMemoryWarning`
**Severity**: Warning
**Threshold**: Memory utilization >90%
**Pressure Level**: CRITICAL

#### Symptoms

- Alert: `sessionstate_total_size_bytes / 98304 > 0.90`
- Metrics showing utilization between 90-95%
- Soft eviction may be active
- Logs showing `sessionstate.pressure.critical` events

#### Root Cause

Common causes of elevated memory:

1. **Large conversation turns** - User or assistant messages with long content
2. **High belief accumulation** - Many facts added without demotion
3. **Telemetry backlog** - Telemetry section filling faster than eviction
4. **Missing eviction** - Eviction engine not running or failing

#### Investigation Steps

```bash
# 1. Check current utilization breakdown
curl http://localhost:9090/metrics | grep -E "sessionstate_(total|tier|section)_size_bytes"

# 2. Identify largest sections
curl http://localhost:9090/metrics | grep sessionstate_section_size_bytes | sort -t= -k2 -rn

# 3. Check eviction activity
curl http://localhost:9090/metrics | grep -E "sessionstate_evictions_total"

# 4. Review recent mutations
kubectl logs -l app=k1-kernel --since=5m | grep "sessionstate.mutation.approved" | tail -20
```

#### Mitigation Steps

**Immediate (< 5 minutes):**

1. Check if eviction is active:
   ```bash
   curl http://localhost:9090/metrics | grep sessionstate_evictions_total
   ```

2. If no recent evictions, verify eviction engine is running:
   ```bash
   kubectl logs -l app=k1-kernel --since=5m | grep "eviction"
   ```

3. If eviction is blocked, check for pinned sections or failures:
   ```bash
   kubectl logs -l app=k1-kernel --since=5m | grep -E "(eviction.failed|eviction.blocked)"
   ```

**Short-term (< 1 hour):**

1. Review conversation patterns causing large turns
2. Check if specific session IDs are consuming disproportionate memory
3. Consider adjusting section budgets in `sessionstate.policies.yaml`

#### Verification

```bash
# Confirm utilization dropped below 90%
curl http://localhost:9090/metrics | grep sessionstate_total_size_bytes
# Should be < 88474 bytes (90% of 98304)

# Confirm pressure level returned to NORMAL or ELEVATED
curl http://localhost:9090/metrics | grep sessionstate_pressure_level
```

---

### 2.2 SessionStateMemoryCritical

**Alert**: `SessionStateMemoryCritical`
**Severity**: Critical
**Threshold**: Memory utilization >95%
**Pressure Level**: Near EMERGENCY

#### Symptoms

- Alert: `sessionstate_total_size_bytes / 98304 > 0.95`
- Metrics showing utilization between 95-100%
- Hard eviction should be active
- Logs showing `sessionstate.pressure.emergency` imminent
- Possible mutation rejections starting

#### Root Cause

Memory approaching emergency threshold. If not resolved quickly:

1. Emergency mode will activate
2. New mutations will be rejected
3. User experience will degrade

#### Investigation Steps

```bash
# 1. IMMEDIATE: Check if emergency mode is already active
curl http://localhost:9090/metrics | grep "sessionstate_pressure_level{tier=\"total\"}"
# Value 3 = EMERGENCY

# 2. Check HOT vs WARM breakdown
curl http://localhost:9090/metrics | grep sessionstate_tier_size_bytes

# 3. Identify sections over budget
curl http://localhost:9090/metrics | grep sessionstate_section_size_bytes | \
  awk -F'[{=}]' '{print $2, $NF}' | sort -k2 -rn

# 4. Check eviction queue
kubectl logs -l app=k1-kernel --since=2m | grep -E "eviction\.(triggered|completed)"

# 5. Check for eviction failures
kubectl logs -l app=k1-kernel --since=5m | grep "eviction.failed"
```

#### Mitigation Steps

**Immediate (< 2 minutes):**

1. **Force eviction of telemetry** (lowest priority, safest to drop):
   ```bash
   # This is a manual intervention - verify telemetry can be evicted
   kubectl exec -it k1-kernel-0 -- python -c "
   from k1.sessionstate import SessionStateFactory
   manager = SessionStateFactory.create_standalone()
   manager.start()
   # Force telemetry eviction
   manager._eviction_engine.evict_section('telemetry')
   manager.stop()
   "
   ```

2. **Check if LOCAL COLD archival is working**:
   ```bash
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "SELECT COUNT(*) FROM archives;"
   ```

3. **If archival is blocked**, check disk space:
   ```bash
   kubectl exec -it k1-kernel-0 -- df -h /data
   ```

**Short-term (< 30 minutes):**

1. Investigate why eviction isn't keeping up with inflow
2. Review mutation patterns for anomalies
3. Consider temporary reduction in section budgets

#### Verification

```bash
# Confirm utilization dropped below 95%
curl http://localhost:9090/metrics | grep sessionstate_total_size_bytes
# Should be < 93389 bytes (95% of 98304)

# Confirm pressure level is not EMERGENCY (3)
curl http://localhost:9090/metrics | grep sessionstate_pressure_level
# Should be < 3
```

---

### 2.3 SessionStateEmergencyActivated

**Alert**: `SessionStateEmergencyActivated`
**Severity**: Critical
**Threshold**: Pressure level = EMERGENCY (3)
**Impact**: NEW MUTATIONS ARE BEING REJECTED

#### Symptoms

- Alert: `sessionstate_pressure_level{tier="total"} == 3`
- User-facing impact: Writes failing, conversation may stall
- Logs showing `sessionstate.emergency.activated` events
- Logs showing `sessionstate.mutation.rejected` events
- Error messages returned to Concierge/user

#### Root Cause

SessionState has exceeded 95% utilization and activated emergency mode as a data-loss-prevention measure. All new mutations are rejected until memory is freed.

**This is a critical user-impacting event.**

#### Investigation Steps

```bash
# 1. IMMEDIATE: Confirm emergency mode
curl http://localhost:9090/metrics | grep "sessionstate_pressure_level"

# 2. Check current utilization
curl http://localhost:9090/metrics | grep sessionstate_total_size_bytes
# Divide by 98304 to get percentage

# 3. Check rejection rate
curl http://localhost:9090/metrics | grep "sessionstate_mutations_total{result=\"rejected\"}"

# 4. View emergency activation logs
kubectl logs -l app=k1-kernel --since=5m | grep "emergency.activated"

# 5. Check what sections are consuming memory
curl http://localhost:9090/metrics | grep sessionstate_section_size_bytes | sort -t= -k2 -rn
```

#### Mitigation Steps

**Immediate (< 1 minute):**

1. **Page on-call if not already alerted** - This is user-impacting

2. **Attempt forced eviction**:
   ```bash
   # Force eviction of all evictable WARM sections in priority order
   kubectl exec -it k1-kernel-0 -- python -c "
   from k1.sessionstate import SessionStateFactory
   manager = SessionStateFactory.create_standalone()
   manager.start()

   # Evict in priority order: telemetry, beliefs_history, history_recent
   for section in ['telemetry', 'beliefs_history', 'history_recent']:
       try:
           result = manager._eviction_engine.evict_section(section)
           print(f'{section}: evicted {result.bytes_freed} bytes')
       except Exception as e:
           print(f'{section}: failed - {e}')

   print(f'New utilization: {manager.get_snapshot().utilization_pct:.1f}%')
   manager.stop()
   "
   ```

3. **If eviction fails, check disk space**:
   ```bash
   kubectl exec -it k1-kernel-0 -- df -h /data
   ```

4. **If disk full, emergency cleanup**:
   ```bash
   # Remove old checkpoint archives (keep last 3)
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "
   DELETE FROM archives
   WHERE session_id NOT IN (
     SELECT session_id FROM archives
     ORDER BY created_at_ms DESC LIMIT 3
   );"
   ```

**Short-term (< 15 minutes):**

1. Monitor that emergency resolves:
   ```bash
   watch -n 5 'curl -s http://localhost:9090/metrics | grep sessionstate_pressure_level'
   ```

2. Review logs for resolution:
   ```bash
   kubectl logs -l app=k1-kernel -f | grep "emergency.resolved"
   ```

3. Document incident for post-mortem

#### Verification

```bash
# Confirm pressure level is not EMERGENCY
curl http://localhost:9090/metrics | grep "sessionstate_pressure_level{tier=\"total\"}"
# Should be < 3 (EMERGENCY)

# Confirm mutations are being approved again
curl http://localhost:9090/metrics | grep "sessionstate_mutations_total{result=\"approved\"}"

# Check no new rejections
kubectl logs -l app=k1-kernel --since=1m | grep "mutation.rejected" | wc -l
# Should be 0
```

---

### 2.4 SessionStateReconstructionSLABreach

**Alert**: `SessionStateReconstructionSLABreach`
**Severity**: Warning
**Threshold**: LOCAL COLD P95 >50ms OR K0 P95 >100ms
**Impact**: Slow session restoration, user-perceived latency

#### Symptoms

- Alert: Reconstruction latency exceeds SLA
- Slow session startup after resume
- Users waiting longer for conversation context to load
- Logs showing slow `sessionstate.reconstruction.completed` events

#### Root Cause

Common causes:

1. **Large checkpoint size** - Too much data to deserialize
2. **Disk I/O contention** - SQLite competing with other processes
3. **Fragmented SQLite database** - Needs VACUUM
4. **K0 network latency** - If using K0 fallback path

#### Investigation Steps

```bash
# 1. Check current reconstruction latency
curl http://localhost:9090/metrics | grep sessionstate_reconstruction_latency_seconds

# 2. Calculate P95 from histogram
curl http://localhost:9090/metrics | grep sessionstate_reconstruction_latency_seconds_bucket

# 3. Check checkpoint sizes
kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "
SELECT
  session_id,
  length(checkpoint_data) as size_bytes,
  created_at_ms
FROM checkpoints
ORDER BY created_at_ms DESC
LIMIT 10;"

# 4. Check disk I/O
kubectl exec -it k1-kernel-0 -- iostat -x 1 5

# 5. Check SQLite fragmentation
kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "
SELECT page_count, freelist_count FROM pragma_page_count(), pragma_freelist_count();"
```

#### Mitigation Steps

**Immediate (< 5 minutes):**

1. Check if this is a transient spike:
   ```bash
   # Compare last 5m to last 1h
   curl http://localhost:9090/metrics | grep sessionstate_reconstruction_latency_seconds_sum
   ```

2. If persistent, check for large checkpoints:
   ```bash
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "
   SELECT session_id, length(checkpoint_data) as size
   FROM checkpoints WHERE length(checkpoint_data) > 50000
   ORDER BY size DESC LIMIT 5;"
   ```

**Short-term (< 1 hour):**

1. **VACUUM SQLite database** (during low traffic):
   ```bash
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "VACUUM;"
   ```

2. **Review disk I/O patterns**:
   ```bash
   kubectl exec -it k1-kernel-0 -- iotop -b -n 5
   ```

3. **If K0 path is slow**, check network:
   ```bash
   kubectl exec -it k1-kernel-0 -- ping -c 5 k0-kernel
   ```

#### Verification

```bash
# Confirm P95 is back within SLA
# LOCAL COLD: < 50ms (0.050s)
# K0: < 100ms (0.100s)
curl http://localhost:9090/metrics | grep sessionstate_reconstruction_latency_seconds_bucket

# Calculate P95:
# histogram_quantile(0.95, rate(sessionstate_reconstruction_latency_seconds_bucket[5m]))
```

---

### 2.5 SessionStateEvictionFailure

**Alert**: `SessionStateEvictionFailure`
**Severity**: Critical
**Threshold**: Eviction success rate <99.9%
**Impact**: Memory pressure buildup, potential emergency mode

#### Symptoms

- Alert: Eviction success rate below threshold
- Metrics showing failed evictions
- Memory utilization not decreasing despite eviction attempts
- Logs showing `sessionstate.eviction.failed` events

#### Root Cause

Common causes:

1. **Archive failure** - LOCAL COLD SQLite write failed
2. **Disk full** - No space to archive evicted data
3. **Lock contention** - Section locked during eviction
4. **Corruption** - Section data serialization failed

#### Investigation Steps

```bash
# 1. Check eviction success/failure counts
curl http://localhost:9090/metrics | grep sessionstate_evictions_total

# 2. View eviction failure logs
kubectl logs -l app=k1-kernel --since=10m | grep "eviction.failed"

# 3. Check disk space
kubectl exec -it k1-kernel-0 -- df -h /data

# 4. Check SQLite integrity
kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "PRAGMA integrity_check;"

# 5. Check for lock contention
kubectl logs -l app=k1-kernel --since=5m | grep -E "(lock.timeout|deadlock)"
```

#### Mitigation Steps

**Immediate (< 5 minutes):**

1. **If disk full**, emergency cleanup:
   ```bash
   # Remove old archives
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "
   DELETE FROM archives WHERE created_at_ms < strftime('%s','now','-7 days') * 1000;"

   # VACUUM to reclaim space
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "VACUUM;"
   ```

2. **If SQLite corrupted**, restore from backup:
   ```bash
   # Check corruption
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db "PRAGMA integrity_check;"

   # If corrupted, export what we can and recreate
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db ".dump" > /tmp/backup.sql
   kubectl exec -it k1-kernel-0 -- rm /data/sessionstate.db
   kubectl exec -it k1-kernel-0 -- sqlite3 /data/sessionstate.db < /tmp/backup.sql
   ```

3. **If lock contention**, restart manager:
   ```bash
   kubectl delete pod k1-kernel-0
   # Wait for restart
   kubectl wait --for=condition=ready pod/k1-kernel-0 --timeout=60s
   ```

**Short-term (< 1 hour):**

1. Review eviction patterns for systematic issues
2. Check if specific sections consistently fail
3. Review disk capacity and plan expansion

#### Verification

```bash
# Confirm eviction success rate recovered
# Calculate: success / total > 0.999
curl http://localhost:9090/metrics | grep sessionstate_evictions_total

# Confirm new evictions are succeeding
kubectl logs -l app=k1-kernel --since=2m | grep "eviction.completed"
```

---

### 2.6 SessionStateLatencySLOBreach

**Alert**: `SessionStateLatencySLOBreach`
**Severity**: Warning
**Threshold**: Latency compliance <99.5%
**Impact**: Slower reads/writes, user-perceived latency

#### Symptoms

- Alert: Latency SLO compliance below target
- Slow read operations (HOT >100us, WARM >200us)
- Slow preflight checks (>50us)
- Users experiencing slower conversation responses

#### Root Cause

Common causes:

1. **Memory pressure** - High utilization slowing operations
2. **Lock contention** - Concurrent access patterns
3. **Large section sizes** - Serialization overhead
4. **CPU throttling** - Container resource limits

#### Investigation Steps

```bash
# 1. Check current latency percentiles
curl http://localhost:9090/metrics | grep sessionstate_read_latency_seconds

# 2. Check CPU throttling
kubectl top pod k1-kernel-0

# 3. Check memory pressure correlation
curl http://localhost:9090/metrics | grep -E "(sessionstate_pressure_level|sessionstate_read_latency)"

# 4. Check concurrent access patterns
kubectl logs -l app=k1-kernel --since=5m | grep "lock.acquired" | wc -l

# 5. Check section sizes (larger = slower)
curl http://localhost:9090/metrics | grep sessionstate_section_size_bytes
```

#### Mitigation Steps

**Immediate (< 5 minutes):**

1. Check if correlated with memory pressure:
   ```bash
   curl http://localhost:9090/metrics | grep sessionstate_pressure_level
   # If ELEVATED/CRITICAL, focus on reducing memory first
   ```

2. Check CPU usage:
   ```bash
   kubectl top pod k1-kernel-0
   # If >80% CPU, may need scaling
   ```

**Short-term (< 1 hour):**

1. **If CPU-bound**, increase resources:
   ```yaml
   # Update deployment
   resources:
     limits:
       cpu: "2000m"  # Increase from 1000m
       memory: "512Mi"
   ```

2. **If memory-pressure correlated**, trigger eviction:
   ```bash
   # Reduce memory to improve latency
   kubectl exec -it k1-kernel-0 -- python -c "
   from k1.sessionstate import SessionStateFactory
   manager = SessionStateFactory.create_standalone()
   manager.start()
   manager._eviction_engine.evict_section('telemetry')
   manager.stop()
   "
   ```

3. **If large sections**, review section budgets:
   ```bash
   # Check which sections are largest
   curl http://localhost:9090/metrics | grep sessionstate_section_size_bytes | sort -t= -k2 -rn
   ```

#### Verification

```bash
# Confirm latency P95 back within SLA
# HOT: < 100us (0.0001s)
# WARM: < 200us (0.0002s)
# Preflight: < 50us (0.00005s)

# Check compliance is >99.5%
# (requests meeting SLA / total requests) * 100
```

---

## 3. Preventive Measures

### 3.1 Capacity Planning

- Monitor 7-day utilization trends
- Alert at 80% average utilization (pre-warning)
- Plan section budget adjustments quarterly
- Review turn size distributions monthly

### 3.2 Performance Optimization

- Keep SQLite VACUUM schedule (weekly)
- Monitor disk I/O patterns
- Review lock contention metrics
- Profile serialization overhead

### 3.3 Disaster Recovery

- Checkpoint retention: 7 days minimum
- Backup SQLite database daily
- Test reconstruction from backup monthly
- Document recovery procedures

---

## 4. Related Documentation

### ADRs

- [ADR-K089: SessionState Memory Budget](../architecture/decisions-K1/0089-sessionstate-memory-budget.md)
- [ADR-K090: SessionState FlatBuffer Serialization](../architecture/decisions-K1/0090-sessionstate-flatbuffer.md)
- [ADR-K091: SessionState Eviction Policy](../architecture/decisions-K1/0091-sessionstate-eviction.md)

### Contracts

- [SessionState Policies Contract](../../k1/contracts/schemas/runtime/sessionstate.policies.yaml)
- [SessionState Module Contract](../../k1/contracts/schemas/module.contract.yaml)

### Implementation

- [SessionState Implementation Plan](../plans/k1/sessionstate-implementation-plan.md)
- [SessionState Module](../../k1/sessionstate/)
- [Alert Rules](../../k1/sessionstate/alerts.yaml)

### Dashboards

- `sessionstate-overview` - Main metrics dashboard
- `sessionstate-latency` - Latency breakdown
- `sessionstate-eviction` - Eviction activity
- `sessionstate-emergency` - Emergency mode tracker

---

## 5. Contact

- **On-Call Team**: k1-kernel-oncall@familyos.dev
- **Slack Channel**: #k1-sessionstate-alerts
- **Escalation**: See K1 Kernel escalation policy
