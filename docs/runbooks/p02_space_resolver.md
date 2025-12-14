# P02 Space Resolver Runbook

**Version:** 1.0.0
**Date:** 2025-11-13
**Owner:** K0 Memory Kernel Team
**Status:** Production

---

## 1. Overview

This runbook covers operational procedures for the **SpaceResolver** integration within the **P02 Episodic Write Pipeline**. The SpaceResolver determines memory ownership, visibility, and access control based on space policies, family relationships, and guardian rules.

**Architecture References:**
- ADR-K004a: Space Resolution Core Architecture
- ADR-K004b: Cache Authority + Invalidation
- ADR-K004c: Guardian Ownership Rules
- ADR-K004d: Visibility Matrix
- ADR-K004e: Degraded State Transitions
- Implementation Plan: `k0/modules/space/IMPLEMENTATION_PLAN.md`
- P02 Integration Guide: `k0/pipelines/P02_IMPLEMENTATION_GUIDE.md`

**Key Components:**
- **SpaceResolver** (`k0/modules/space/resolver.py`): Main orchestrator
- **SpaceAuthorityCache** (`k0/modules/space/cache/space_authority.py`): In-memory cache with TTL
- **CacheInvalidationSubscriber** (`k0/modules/space/cache/invalidation.py`): Bus event handler
- **P02 Pipeline** (`k0/pipelines/p02_episodic_write.py`): Integration point

---

## 2. Architecture Overview

```
K1 Envelope → K0 Kernel (Gate) → WAL → Outbox → P02 Pipeline
                                                      ↓
                                              SpaceResolver
                                                      ↓
                        ┌─────────────────────────────┴─────────────────────────────┐
                        ↓                             ↓                             ↓
            SpaceAuthorityCache         OwnershipResolver              VisibilityEngine
                        ↓                             ↓                             ↓
                   st_spaces                   Guardian Rules                Visibility Matrix
                st_space_members            Relationship Graph            Policy Overrides
               st_relationships                                        Visibility Adjustments
                        ↓
                st_hipp_store (11 resolver columns)
```

**Data Flow:**
1. P02 receives `cognitive.memory.write.committed.v1` event
2. SpaceResolver.resolve() called with `SpaceResolutionRequest`
3. Cache lookup for space metadata, members, relationships
4. Ownership determination based on actor + guardian rules
5. Visibility projection using policy matrix
6. Resolution written to `st_hipp_store` (11 new columns)

---

## 3. New Columns in st_hipp_store

### 3.1 Column Reference

| Column | Type | Purpose | Example | Nullability |
|--------|------|---------|---------|-------------|
| `owner_id` | TEXT | Primary memory owner (data sovereignty) | `"person_prince_001"` | NOT NULL |
| `co_owners` | TEXT (JSON array) | Shared ownership (multi-person experiences) | `["person_jeel_001"]` | NULL |
| `author_role` | TEXT | Relationship role of author | `"guardian"`, `"child"`, `"spouse"` | NULL |
| `participant_roles` | TEXT (JSON object) | Roles of all participants | `{"person_sharvi_001": "child"}` | NULL |
| `visible_to` | TEXT (JSON array) | Person IDs who can read this memory | `["person_prince_001", "person_jeel_001", "person_sharvi_001"]` | NOT NULL |
| `visibility_policy_version` | TEXT | Policy lineage hash for auditing | `"space:shared:household\|matrix-k004d-v1"` | NULL |
| `policy_overrides` | TEXT (JSON array) | Override tags applied | `["cache_warn"]` | NULL |
| `visibility_adjustments` | TEXT (JSON array) | Audit trail of visibility modifications | `[{"reason": "guardian_only", "subject_id": "person_sharvi_001"}]` | NULL |
| `resolver_state` | TEXT | Resolver operational state | `"NORMAL"`, `"CACHE_WARN"`, `"SAFE_MODE"` | NULL |
| `cache_snapshot_version` | TEXT | Cache lineage digest | `"spaces:v5\|space_members:v8\|relationships:v3"` | NULL |
| `resolution_latency_ms` | REAL | Resolver performance metric | `12.4` | NULL |

### 3.2 Column Details

#### `owner_id` (PRIMARY OWNER)

**Determination Rules:**
- **Default:** `actor_id` (person who created memory)
- **Exception (Guardian Rule):** If actor is a minor AND participants include guardians → owner flips to guardian
- **Example:** Sharvi (minor) creates memory with Prince (guardian) → `owner_id = "person_prince_001"`

**Query Example:**
```sql
SELECT event_id, text, owner_id, author_id
FROM st_hipp_store
WHERE owner_id = 'person_prince_001'
  AND author_id = 'person_sharvi_001';  -- Memories owned by Prince, authored by Sharvi
```

#### `co_owners` (SHARED OWNERSHIP)

**Determination Rules:**
- **Shared Spaces:** If `space_id` starts with `"shared:"` AND multiple participants → all participants become co-owners
- **Personal Spaces:** Empty `[]`
- **Example:** Alice + Bob + Emma in `shared:household` → `co_owners = ["person_bob_001", "person_emma_001"]`

**Query Example:**
```sql
SELECT event_id, text, owner_id, co_owners
FROM st_hipp_store
WHERE json_array_length(co_owners) > 0;  -- Find shared memories
```

#### `author_role` (RELATIONSHIP CONTEXT)

**Possible Values:**
- `"guardian"` - Parent or caretaker of minor
- `"child"` - Minor under guardianship
- `"spouse"` - Partner in household
- `"sibling"` - Brother/sister relationship
- `"parent"` - Adult child of elderly parent
- `"grandparent"` - Grandparent relationship
- `"automation_delegate"` - Agent acting on behalf of user
- `"unknown"` - Relationship not determined

**Query Example:**
```sql
SELECT event_id, text, author_id, author_role
FROM st_hipp_store
WHERE author_role = 'child'
  AND owner_id != author_id;  -- Minor's memories owned by guardian
```

#### `participant_roles` (MULTI-PERSON CONTEXT)

**Format:** JSON object mapping person_id → role

**Example:**
```json
{
  "person_prince_001": "guardian",
  "person_jeel_001": "guardian",
  "person_sharvi_001": "child"
}
```

**Query Example:**
```sql
SELECT event_id, text, participant_roles
FROM st_hipp_store
WHERE json_extract(participant_roles, '$.person_sharvi_001') = 'child';
```

#### `visible_to` (ACCESS CONTROL)

**Determination Rules:**
- **Personal Space:** `[owner_id]` only
- **Shared Space (NORMAL mode):** All active household members
- **SAFE_MODE:** Guardians only (when cache expired)
- **Automation:** Delegates inherit visibility from delegator

**Query Example:**
```sql
-- Find memories visible to Prince
SELECT event_id, text, visible_to
FROM st_hipp_store
WHERE json_array_contains(visible_to, 'person_prince_001');

-- Count visibility scope
SELECT
  CASE
    WHEN json_array_length(visible_to) = 1 THEN 'Private'
    WHEN json_array_length(visible_to) <= 3 THEN 'Family'
    ELSE 'Extended'
  END as scope,
  COUNT(*) as memory_count
FROM st_hipp_store
GROUP BY scope;
```

#### `visibility_policy_version` (AUDIT TRAIL)

**Format:** `"space:{space_id}|matrix-{version}"`

**Example:** `"space:shared:household|matrix-k004d-v1"`

**Purpose:** Track which policy version was used for visibility determination. Critical for:
- Debugging visibility issues
- Policy rollback scenarios
- Compliance audits

**Query Example:**
```sql
SELECT visibility_policy_version, COUNT(*) as memory_count
FROM st_hipp_store
GROUP BY visibility_policy_version
ORDER BY memory_count DESC;
```

#### `policy_overrides` (OVERRIDE TAGS)

**Possible Values:**
- `"cache_warn"` - Cache TTL > 70%
- `"safe_mode"` - Cache TTL > 100%
- `"manual_override"` - Admin intervention
- `"emergency_access"` - Break-glass scenario

**Example:** `["cache_warn"]`

**Query Example:**
```sql
-- Find memories with overrides
SELECT event_id, text, policy_overrides, resolver_state
FROM st_hipp_store
WHERE json_array_length(policy_overrides) > 0;
```

#### `visibility_adjustments` (MODIFICATION AUDIT)

**Format:** Array of `{"reason": string, "subject_id": string}` objects

**Example:**
```json
[
  {"reason": "guardian_only", "subject_id": "person_sharvi_001"},
  {"reason": "minor_protection", "subject_id": "person_sharvi_001"}
]
```

**Common Reasons:**
- `"guardian_only"` - Minor's content restricted to guardians
- `"minor_protection"` - Age-gated content filtering
- `"delegation_scope"` - Automation delegate visibility limits
- `"safe_mode_fallback"` - Cache expired, conservative visibility

**Query Example:**
```sql
-- Find memories with guardian-only adjustments
SELECT event_id, text, visibility_adjustments, visible_to
FROM st_hipp_store
WHERE json_extract(visibility_adjustments, '$[0].reason') = 'guardian_only';
```

#### `resolver_state` (OPERATIONAL STATE)

**Possible Values:**
- `"NORMAL"` - Cache fresh, normal operation
- `"CACHE_WARN"` - Cache TTL > 70% (7 min / 10 min)
- `"SAFE_MODE"` - Cache TTL > 100% (expired), guardian-only fallback
- `"STRICT_GUARDIAN"` - Policy override for sensitive content
- `"BYPASS_LEGACY"` - Feature flag OFF, using legacy logic

**State Transitions:**
```
NORMAL → CACHE_WARN (TTL > 70%)
CACHE_WARN → SAFE_MODE (TTL > 100%)
SAFE_MODE → NORMAL (cache refresh)
```

**Query Example:**
```sql
-- Monitor resolver state distribution
SELECT resolver_state, COUNT(*) as count
FROM st_hipp_store
WHERE created_at > datetime('now', '-1 hour')
GROUP BY resolver_state;
```

#### `cache_snapshot_version` (LINEAGE TRACKING)

**Format:** `"spaces:v{N}|space_members:v{M}|relationships:v{K}"`

**Example:** `"spaces:v5|space_members:v8|relationships:v3"`

**Purpose:** Track which cache snapshot version was used. Critical for:
- Debugging stale cache issues
- Correlating resolver decisions with cache state
- Rollback scenarios

**Query Example:**
```sql
SELECT cache_snapshot_version, COUNT(*) as memory_count
FROM st_hipp_store
WHERE created_at > datetime('now', '-1 day')
GROUP BY cache_snapshot_version;
```

#### `resolution_latency_ms` (PERFORMANCE METRIC)

**Typical Values:**
- < 5ms: Normal operation (cache hit)
- 5-20ms: Cache miss, database query
- > 20ms: Degraded performance, investigate

**Query Example:**
```sql
-- P95 latency over last hour
SELECT
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY resolution_latency_ms) as p95_latency
FROM st_hipp_store
WHERE created_at > datetime('now', '-1 hour');
```

---

## 4. Interpreting Resolver States

### 4.1 NORMAL State

**Characteristics:**
- Cache TTL < 70%
- All lookups successful
- No policy overrides

**Example Query:**
```sql
SELECT event_id, text, owner_id, visible_to
FROM st_hipp_store
WHERE resolver_state = 'NORMAL'
  AND created_at > datetime('now', '-1 hour');
```

**Expected Behavior:**
- Ownership determined by actor + guardian rules
- Visibility includes all active household members
- No adjustments or overrides

**Action Required:** None (normal operation)

---

### 4.2 CACHE_WARN State

**Trigger:** Cache TTL > 70% (7 min / 10 min default)

**Characteristics:**
- Cache is stale but still usable
- Warning logged
- `policy_overrides = ["cache_warn"]`
- Resolution proceeds with current cache

**Example Query:**
```sql
SELECT event_id, text, resolver_state, policy_overrides, cache_snapshot_version
FROM st_hipp_store
WHERE resolver_state = 'CACHE_WARN'
  AND created_at > datetime('now', '-15 minutes');
```

**Expected Behavior:**
- Ownership + visibility determined using stale cache
- Warning emitted to logs
- Policy receipt generated

**Action Required:**
1. Check cache refresh job status
2. Verify Neo4j → SQLite sync pipeline
3. If persistent > 10 min → manually refresh cache

**Manual Cache Refresh:**
```bash
# Trigger immediate cache reload
python k0/scripts/refresh_space_cache.py --force

# Verify cache age
sqlite3 /data/k0/cache/st_spaces.db "SELECT hydrated_at FROM st_spaces LIMIT 1;"
```

---

### 4.3 SAFE_MODE State

**Trigger:** Cache TTL > 100% (cache expired)

**Characteristics:**
- Cache is expired, conservative fallback
- `policy_overrides = ["safe_mode"]`
- Visibility restricted to **guardians only**
- `visibility_adjustments` includes `"safe_mode_fallback"`

**Example Query:**
```sql
SELECT event_id, text, author_id, owner_id, visible_to, visibility_adjustments
FROM st_hipp_store
WHERE resolver_state = 'SAFE_MODE';
```

**Expected Behavior:**
- Minors' content: `visible_to = [guardians only]`
- Adults' content: `visible_to = [owner only]`
- No cross-household visibility

**Visibility Logic:**
```python
if resolver_state == "SAFE_MODE":
    if actor_is_minor:
        visible_to = [guardian_ids]
    else:
        visible_to = [actor_id]
```

**Action Required (URGENT):**
1. **Immediate:** Check cache refresh pipeline failure
2. **Verify:** Neo4j connectivity
3. **Manual:** Force cache refresh
4. **Alert:** Notify on-call if SAFE_MODE persists > 15 min

**Troubleshooting Steps:**
```bash
# 1. Check cache age
sqlite3 /data/k0/cache/st_spaces.db \
  "SELECT datetime(hydrated_at), (strftime('%s','now') - strftime('%s',hydrated_at)) as age_seconds FROM st_spaces LIMIT 1;"

# 2. Check sync job status
kubectl logs -l app=k0-sync-job --tail=100

# 3. Manually trigger refresh
kubectl exec -it k0-sync-job -- python /app/scripts/refresh_space_cache.py --force

# 4. Verify cache loaded
sqlite3 /data/k0/cache/st_spaces.db "SELECT COUNT(*) FROM st_spaces WHERE state='ACTIVE';"
```

---

### 4.4 STRICT_GUARDIAN State

**Trigger:** Policy override for sensitive content

**Characteristics:**
- Manual or policy-driven restriction
- Visibility limited to guardians only (regardless of cache state)
- Used for medical, legal, or sensitive family content

**Example Query:**
```sql
SELECT event_id, text, privacy_band, resolver_state, visible_to
FROM st_hipp_store
WHERE resolver_state = 'STRICT_GUARDIAN';
```

**Expected Behavior:**
- `visible_to = [guardian_ids]` (even if cache is fresh)
- `visibility_adjustments` includes explicit reason

**Action Required:** None (policy-driven behavior)

---

### 4.5 BYPASS_LEGACY State

**Trigger:** Feature flag `SPACE_RESOLUTION_V1 = OFF`

**Characteristics:**
- SpaceResolver disabled
- Using legacy ownership logic
- `owner_id = actor_id` (simple rule)
- `visible_to = [actor_id]` (private by default)

**Example Query:**
```sql
SELECT event_id, text, resolver_state, owner_id, author_id
FROM st_hipp_store
WHERE resolver_state = 'BYPASS_LEGACY';
```

**Expected Behavior:**
- No guardian rules applied
- No relationship-based visibility
- Minimal overhead

**Action Required:** None (intended for gradual rollout)

**Rollout Status Check:**
```yaml
# Check feature flag
kubectl get configmap k0-feature-flags -o yaml | grep SPACE_RESOLUTION_V1
```

---

## 5. Common Troubleshooting Scenarios

### 5.1 Problem: Memories Not Visible to Expected Users

**Symptoms:**
- User reports "can't see shared memory"
- `visible_to` array doesn't include expected person_id

**Diagnosis Steps:**
1. Check resolver state:
   ```sql
   SELECT event_id, resolver_state, policy_overrides, visible_to
   FROM st_hipp_store
   WHERE event_id = ?;
   ```

2. Check cache snapshot version:
   ```sql
   SELECT cache_snapshot_version FROM st_hipp_store WHERE event_id = ?;
   ```

3. Compare with current cache:
   ```bash
   sqlite3 /data/k0/cache/st_spaces.db \
     "SELECT * FROM st_space_members WHERE space_id='shared:household';"
   ```

**Common Causes:**
- **SAFE_MODE:** Cache expired → guardian-only visibility
- **Stale Cache:** Membership changes not reflected in cache
- **Wrong Space ID:** Memory created in `personal:*` instead of `shared:household`

**Resolution:**
- If SAFE_MODE → refresh cache immediately
- If stale cache → wait for next sync cycle (2 AM daily) or force refresh
- If wrong space → re-submit memory with correct space_id

---

### 5.2 Problem: Ownership Flipped to Guardian Unexpectedly

**Symptoms:**
- Minor creates memory, but `owner_id = guardian_id`
- `author_id != owner_id`

**Diagnosis Steps:**
```sql
SELECT event_id, author_id, author_role, owner_id, participants, participant_roles
FROM st_hipp_store
WHERE author_id = 'person_sharvi_001'
  AND owner_id != author_id;
```

**Expected Behavior:**
- **Guardian Rule (ADR-K004c):** If author is minor AND participants include guardian → ownership flips
- This is **intentional** for data sovereignty (guardian owns minor's data)

**Validation:**
1. Check author's age:
   ```bash
   sqlite3 /data/k0/cache/st_relationships.db \
     "SELECT * FROM st_relationships WHERE person_id='person_sharvi_001' AND relationship_type='PARENT_OF';"
   ```

2. Verify guardian is in participants:
   ```sql
   SELECT json_extract(participant_roles, '$.person_prince_001') as prince_role
   FROM st_hipp_store
   WHERE event_id = ?;
   ```

**Resolution:** None needed (correct behavior per ADR-K004c)

---

### 5.3 Problem: High Resolution Latency (> 20ms)

**Symptoms:**
- `resolution_latency_ms > 20` consistently
- Slow P02 pipeline processing

**Diagnosis Steps:**
1. Check P95 latency:
   ```sql
   SELECT
     PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY resolution_latency_ms) as p95_latency,
     AVG(resolution_latency_ms) as avg_latency,
     MAX(resolution_latency_ms) as max_latency
   FROM st_hipp_store
   WHERE created_at > datetime('now', '-1 hour');
   ```

2. Check cache hit rate:
   ```bash
   # Prometheus query
   rate(space_resolver_cache_hits_total[5m]) / rate(space_resolver_cache_lookups_total[5m])
   ```

**Common Causes:**
- Cache misses → SQLite queries slow
- Large relationship graph (> 100 persons)
- Disk I/O bottleneck

**Resolution:**
- **Optimize Cache:** Increase cache size, reduce TTL churn
- **Index Tuning:** Verify SQLite indexes on `household_id`, `person_id`
- **Disk:** Move cache to SSD if on HDD

---

### 5.4 Problem: Policy Receipts Not Generated

**Symptoms:**
- CACHE_WARN or SAFE_MODE state, but no policy receipts in logs

**Diagnosis Steps:**
```bash
# Check logs for policy receipts
kubectl logs -l app=k0-pipeline-p02 | grep "resolver_state_degraded"
```

**Expected Log Entry:**
```json
{
  "level": "warning",
  "msg": "Resolver state degraded: CACHE_WARN - Cache TTL threshold exceeded",
  "event_type": "resolver_state_degraded",
  "resolver_state": "CACHE_WARN",
  "trace_id": "trace-abc123",
  "cache_age_seconds": 450,
  "ttl_seconds": 600
}
```

**Common Causes:**
- Log level too high (set to ERROR instead of WARNING)
- Policy receipts module not imported

**Resolution:**
```bash
# Set log level to WARNING
kubectl set env deployment/k0-pipeline-p02 LOG_LEVEL=WARNING
```

---

## 6. Monitoring & Alerts

### 6.1 Key Metrics

**Prometheus Metrics:**
```promql
# Resolver latency P95
histogram_quantile(0.95, rate(space_resolver_latency_ms_bucket[5m]))

# Resolver state distribution
sum by (state) (rate(space_resolver_resolutions_total[5m]))

# Cache hit rate
rate(space_resolver_cache_hits_total[5m]) / rate(space_resolver_cache_lookups_total[5m])

# SAFE_MODE entries
increase(space_resolver_safe_mode_entries_total[1h])
```

**Grafana Dashboard Panels:**
1. **Resolver Latency (P50, P95, P99)** - Line chart
2. **Resolver State Distribution** - Stacked area chart
3. **Cache Hit Rate** - Gauge (target > 95%)
4. **SAFE_MODE Frequency** - Counter (alert if > 10/hour)

### 6.2 Alerting Rules

**Alert: Cache Staleness**
```yaml
alert: SpaceResolverCacheStale
expr: (time() - space_resolver_cache_age_seconds) > 600
for: 5m
severity: warning
annotations:
  summary: "Space resolver cache is stale (> 10 min)"
  description: "Cache age: {{ $value }}s. Expected refresh every 10 min."
```

**Alert: High SAFE_MODE Rate**
```yaml
alert: SpaceResolverSafeModeHigh
expr: increase(space_resolver_safe_mode_entries_total[1h]) > 10
for: 5m
severity: critical
annotations:
  summary: "Excessive SAFE_MODE entries (> 10/hour)"
  description: "Cache refresh failing. Check Neo4j sync pipeline."
```

**Alert: High Latency**
```yaml
alert: SpaceResolverHighLatency
expr: histogram_quantile(0.95, rate(space_resolver_latency_ms_bucket[5m])) > 20
for: 10m
severity: warning
annotations:
  summary: "Space resolver P95 latency > 20ms"
  description: "Current P95: {{ $value }}ms. Investigate cache performance."
```

---

## 7. Operational Procedures

### 7.1 Cache Refresh (Manual)

**When:** SAFE_MODE persists > 15 min OR cache age > 12 hours

**Steps:**
```bash
# 1. Check current cache age
kubectl exec -it k0-sync-job -- sqlite3 /data/k0/cache/st_spaces.db \
  "SELECT datetime(hydrated_at), (strftime('%s','now') - strftime('%s',hydrated_at))/60 as age_minutes FROM st_spaces LIMIT 1;"

# 2. Trigger refresh
kubectl exec -it k0-sync-job -- python /app/scripts/refresh_space_cache.py --force

# 3. Verify new cache age
kubectl exec -it k0-sync-job -- sqlite3 /data/k0/cache/st_spaces.db \
  "SELECT datetime(hydrated_at) FROM st_spaces LIMIT 1;"

# 4. Check resolver state transitions
sqlite3 /data/k0/storage/k0.db \
  "SELECT resolver_state, COUNT(*) FROM st_hipp_store WHERE created_at > datetime('now', '-5 minutes') GROUP BY resolver_state;"
```

**Expected Result:**
- Cache age resets to 0 minutes
- Resolver state transitions from SAFE_MODE → NORMAL
- No new CACHE_WARN entries for next 7 minutes

---

### 7.2 Feature Flag Rollout (SPACE_RESOLUTION_V1)

**Current Status Check:**
```bash
kubectl get configmap k0-feature-flags -o jsonpath='{.data.SPACE_RESOLUTION_V1}'
```

**Gradual Rollout Steps:**

**Phase 1: Canary (1%)**
```bash
kubectl patch configmap k0-feature-flags --type merge -p '{"data":{"SPACE_RESOLUTION_V1":"true","SPACE_RESOLUTION_V1_PERCENTAGE":"1"}}'
kubectl rollout restart deployment/k0-pipeline-p02
```

**Validation:**
```sql
-- Check BYPASS_LEGACY vs NORMAL ratio
SELECT
  resolver_state,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
FROM st_hipp_store
WHERE created_at > datetime('now', '-1 hour')
GROUP BY resolver_state;
```

**Phase 2: Ramp to 10%**
```bash
kubectl patch configmap k0-feature-flags --type merge -p '{"data":{"SPACE_RESOLUTION_V1_PERCENTAGE":"10"}}'
```

**Phase 3: Full Rollout (100%)**
```bash
kubectl patch configmap k0-feature-flags --type merge -p '{"data":{"SPACE_RESOLUTION_V1_PERCENTAGE":"100"}}'
```

**Rollback (if errors):**
```bash
kubectl patch configmap k0-feature-flags --type merge -p '{"data":{"SPACE_RESOLUTION_V1":"false"}}'
kubectl rollout restart deployment/k0-pipeline-p02
```

---

### 7.3 Investigating Ownership Disputes

**Scenario:** User reports "wrong owner" for memory

**Investigation Query:**
```sql
SELECT
  event_id,
  cognitive_trace_id,
  author_id,
  author_role,
  owner_id,
  json_extract(participant_roles, '$') as participant_roles,
  visible_to,
  visibility_adjustments,
  resolver_state,
  cache_snapshot_version
FROM st_hipp_store
WHERE event_id = ?;
```

**Check Relationship Graph:**
```bash
sqlite3 /data/k0/cache/st_relationships.db \
  "SELECT * FROM st_relationships WHERE person_id=? OR related_person_id=?;"
```

**Common Patterns:**
- **Guardian flip:** Minor author → guardian owner (expected per ADR-K004c)
- **Co-ownership:** Shared space → multiple co-owners (expected)
- **Delegation:** Automation agent → delegated_from becomes owner (expected)

**Resolution:**
- If behavior matches ADR rules → explain to user
- If unexpected → check cache snapshot version, verify relationship data

---

## 8. Schema Migration Notes

### 8.1 Adding Resolver Columns

**Migration:** `k0/contracts/sql/migrations/0013_p02_write_pipeline_enhancements.sql`

**Columns Added:**
- `owner_id TEXT NOT NULL`
- `co_owners TEXT`
- `author_role TEXT`
- `participant_roles TEXT`
- `visible_to TEXT NOT NULL`
- `visibility_policy_version TEXT`
- `policy_overrides TEXT`
- `visibility_adjustments TEXT`
- `resolver_state TEXT`
- `cache_snapshot_version TEXT`
- `resolution_latency_ms REAL`

**Backward Compatibility:**
- Default values: `owner_id = author_id`, `visible_to = [author_id]`
- Legacy memories readable with NULL resolver fields

**Query for Pre-Resolver Memories:**
```sql
SELECT COUNT(*) FROM st_hipp_store WHERE owner_id IS NULL;
```

---

## 9. Quick Reference

### 9.1 Query Templates

**Find all guardian-owned memories:**
```sql
SELECT event_id, text, author_id, owner_id, author_role
FROM st_hipp_store
WHERE owner_id != author_id
  AND author_role = 'child';
```

**Find shared memories (co-owned):**
```sql
SELECT event_id, text, owner_id, co_owners
FROM st_hipp_store
WHERE json_array_length(co_owners) > 0;
```

**Find memories with visibility adjustments:**
```sql
SELECT event_id, text, visibility_adjustments, visible_to
FROM st_hipp_store
WHERE json_array_length(visibility_adjustments) > 0;
```

**Monitor resolver health:**
```sql
SELECT
  resolver_state,
  COUNT(*) as count,
  AVG(resolution_latency_ms) as avg_latency
FROM st_hipp_store
WHERE created_at > datetime('now', '-1 hour')
GROUP BY resolver_state;
```

### 9.2 Log Patterns

**Normal Resolution:**
```
INFO Space resolution complete trace_id=trace-abc owner_id=person_prince_001 resolver_state=NORMAL latency_ms=2.3
```

**Cache Warning:**
```
WARNING Resolver state degraded: CACHE_WARN - Cache TTL threshold exceeded trace_id=trace-def cache_age_seconds=450 ttl_seconds=600
```

**Safe Mode Entry:**
```
WARNING Resolver state degraded: SAFE_MODE - Cache TTL threshold exceeded trace_id=trace-ghi cache_age_seconds=720 ttl_seconds=600
```

---

## 10. Escalation Path

### L1 Support
- Check resolver state in logs
- Verify cache age
- Consult this runbook

### L2 Support (DevOps)
- Manual cache refresh
- Feature flag rollout/rollback
- Grafana dashboard analysis

### L3 Support (Engineering)
- Cache performance tuning
- Resolver algorithm debugging
- Schema migration issues

**On-Call Contact:**
- PagerDuty: `k0-memory-kernel-oncall`
- Slack: `#k0-alerts`

---

## 11. References

- **ADR-K004a:** Space Resolution Core Architecture
- **ADR-K004b:** Cache Authority + Invalidation
- **ADR-K004c:** Guardian Ownership Rules
- **ADR-K004d:** Visibility Matrix
- **ADR-K004e:** Degraded State Transitions
- **Implementation Plan:** `k0/modules/space/IMPLEMENTATION_PLAN.md`
- **P02 Integration Guide:** `k0/pipelines/P02_IMPLEMENTATION_GUIDE.md`
- **Schema Migration:** `k0/contracts/sql/migrations/0013_p02_write_pipeline_enhancements.sql`

---

**Version:** 1.0.0
**Last Updated:** 2025-11-13
**Next Review:** 2025-12-13
