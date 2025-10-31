# K0 Policy Enforcement Module (PEM) — Operations Runbook

**Document Version**: 1.0
**Last Updated**: 2025-10-31
**Related ADRs**: ADR-0089 (K0 Bridge Policy Enforcement), ADR-0001 (K0–K1 Split)
**Related Contracts**: `k0/contracts/policy/bridge_policy.yml`, `k0/contracts/policy/pep.schema.json`

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Components](#architecture--components)
3. [Policy Manifest Configuration](#policy-manifest-configuration)
4. [PEM Decision Outcomes](#pem-decision-outcomes)
5. [Obligation Execution](#obligation-execution)
6. [Metrics & Observability](#metrics--observability)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)
9. [Emergency Operations](#emergency-operations)

---

## Overview

The **Policy Enforcement Module (PEM)** is K0's syscall-level policy evaluation engine. PEM intercepts every command submission, evaluates policy decisions (ALLOW/DENY/REDACT) based on tenant/space/device/band context, and applies obligations (redaction, audit, QoS tightening) before the command is written to the WAL.

### Key Design Principles

- **Syscall-level evaluation**: Policy decisions happen **before** Minimal Gate; redaction applies **before** UoW commit.
- **Deterministic decisions**: All policy logic is side-effect free and replayable.
- **Observable outcomes**: Every decision is recorded with metrics, traces, and audit logs.
- **Fail-safe defaults**: Missing policy manifests or schema errors result in automatic denials (RED band).
- **Per-space isolation**: Policies are enforced independently per `{tenant_id, space_id}`.

---

## Architecture & Components

### Component Breakdown

```
K0 Command Pipeline
│
├─ Envelope Deserialization
│  └─ Extract: {tenant_id, space_id, device_id, band, policy_version, ...}
│
├─ PEP@Syscall (THIS MODULE)
│  ├─ Load policy manifest for {tenant_id, space_id}
│  ├─ Evaluate ABAC rules (band, roles, caps)
│  ├─ Generate decision: ALLOW | DENY | REDACT with obligations
│  └─ Emit: decision outcome + obligations to trace
│
├─ Minimal Gate
│  ├─ Validate envelope presence/hash/sig/size
│  └─ Reject before WAL if policy decision is DENY
│
├─ Idempotency Ledger & UoW
│  └─ If allowed: commit to WAL + Outbox
│
├─ Obligation Execution (async)
│  ├─ Redaction: apply field masking to WAL body
│  ├─ Audit logging: emit policy_decision events
│  └─ QoS updates: adjust scheduler budgets if tightening obligations present
│
└─ Receipt & SSE Emission
   └─ Annotate receipt with obligations + manifest version
```

### PEM Public API

```python
class PEPDecision:
    decision: str  # "ALLOW" | "DENY" | "REDACT"
    band: str      # "GREEN" | "AMBER" | "RED"
    obligations: List[Obligation]
    manifest_version: str
    manifest_hash: str
    reason: str  # human-readable reason for DENY

class Obligation:
    name: str  # "redact", "audit", "qos.tighten", "device.reauth"
    details: Dict[str, Any]

async def evaluate_policy(
    envelope: Envelope,
    manifest: PolicyManifest,
    schema: PolicySchema
) -> PEPDecision:
    """
    Evaluate policy decision based on envelope and current manifest.

    Returns:
        PEPDecision with decision, obligations, and reason.

    Raises:
        PolicyUnavailable if manifest/schema not available.
        PolicyVersionMismatch if envelope policy_version != current version.
    """
```

---

## Policy Manifest Configuration

### Manifest Location & Loading

Manifests are stored in `/k0/deploy/generated/manifests/` and referenced by name:

```bash
# Default manifest (auto-loaded)
/k0/deploy/generated/manifests/allow_all.json

# Custom manifests (via environment override)
K0_PEM_MANIFEST_PATH=/path/to/custom_manifest.json
```

### Manifest Structure

```json
{
  "version": "1.0",
  "tenant": "tenant-001",
  "space": "space-home",
  "description": "Default development policy",
  "bands": {
    "GREEN": {
      "description": "Development - all access allowed",
      "deny": false,
      "obligations": []
    },
    "AMBER": {
      "description": "Audit-logged access",
      "deny": false,
      "obligations": [
        {
          "name": "kernel.audit.log",
          "details": { "level": "amber" }
        }
      ]
    },
    "RED": {
      "description": "Restricted access - requires approval",
      "deny": true,
      "obligations": [
        {
          "name": "kernel.security.notify",
          "details": { "severity": "critical" }
        }
      ]
    }
  },
  "roles": [
    {
      "name": "admin",
      "description": "Administrator role - full access",
      "max_band": "RED",
      "allow_topics": ["*"],
      "obligations": []
    },
    {
      "name": "device",
      "description": "Device role - command writes only",
      "max_band": "GREEN",
      "allow_topics": ["commands.*"],
      "obligations": []
    },
    {
      "name": "guest",
      "description": "Guest role - read-only access",
      "max_band": "GREEN",
      "allow_topics": ["ui.*"],
      "obligations": [
        {
          "name": "kernel.redact.enforce",
          "details": { "scope": "PII" }
        }
      ]
    }
  ],
  "policies": [
    {
      "name": "allow_all",
      "band": "GREEN",
      "description": "Development policy - allows all actions",
      "rules": [
        {
          "action": "ALLOW",
          "target": "*",
          "obligations": ["kernel.audit.log"]
        }
      ]
    }
  ]
}
```

### Configuration Options

Override PEM settings via environment variables:

```bash
# Policy manifest path
K0_PEM_MANIFEST_PATH=/path/to/manifest.json

# Policy schema path
K0_PEM_SCHEMA_PATH=/path/to/pep.schema.json

# Redaction directives (comma-separated field paths to redact)
K0_PEM_REDACTION_FIELDS=device_id,tenant_id,user_email

# Redaction mask token
K0_PEM_REDACTION_MASK=***REDACTED***

# Enable/disable redaction
K0_PEM_REDACTION_ENABLED=true

# Policy decision caching (TTL seconds)
K0_PEM_CACHE_TTL_SECONDS=300

# Obligation timeout (how long to wait for obligation execution)
K0_PEM_OBLIGATION_TIMEOUT_MS=1000

# Fail-safe band (default band when policy unavailable)
K0_PEM_FAILSAFE_BAND=RED
```

---

## PEM Decision Outcomes

### Decision Matrix

| Scenario | Decision | HTTP Status | WAL Written | Obligations |
|----------|----------|-------------|-------------|-------------|
| Green band, matching topic, no caps exceeded | ALLOW | 200 OK | ✅ Yes | As configured |
| Amber band, audit policy | ALLOW | 200 OK | ✅ Yes + audit log | `kernel.audit.log` |
| Red band, no override | DENY | 403 Forbidden | ❌ No | `kernel.security.notify` |
| Band mismatch (e.g., RED device sending RED band) | ALLOW | 200 OK | ✅ Yes | As configured |
| Topic denied for role | DENY | 403 Forbidden | ❌ No | `kernel.policy.review` |
| Device revoked | DENY | 403 Forbidden | ❌ No | `kernel.device.reauth` |
| Manifest version mismatch | 412 Conflict | 412 Precondition Failed | ❌ No | N/A |
| Policy unavailable/schema error | 503 Error | 503 Service Unavailable | ❌ No | N/A |

### Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| **200 OK** | Command allowed | Proceed to WAL |
| **403 Forbidden** | PEP deny | Return error envelope; no WAL |
| **412 Precondition Failed** | Manifest/schema version mismatch | Client retries with updated manifest |
| **503 Service Unavailable** | PEP error (manifest/schema unavailable) | Retry after brief delay |

---

## Obligation Execution

### Supported Obligations

#### 1. Redaction

```json
{
  "name": "kernel.redact.enforce",
  "details": {
    "scope": "PII",
    "fields": ["device_id", "tenant_id"],
    "mask": "***REDACTED***"
  }
}
```

**Effect**: Before WAL commit, redact specified fields from command envelope. Original hash is preserved for idempotency.

```python
# Example: Original envelope
{
  "device_id": "pixel8:XYZ",
  "tenant_id": "household:abc123",
  "payload": {"user_email": "user@example.com"}
}

# After redaction obligation
{
  "device_id": "***REDACTED***",
  "tenant_id": "***REDACTED***",
  "payload": {"user_email": "***REDACTED***"}
}
```

#### 2. Audit Logging

```json
{
  "name": "kernel.audit.log",
  "details": {
    "level": "amber",
    "include_payload": false
  }
}
```

**Effect**: Emit audit event to `policy.*` topic with policy decision metadata.

```json
{
  "event_type": "command_policy_decision",
  "decision": "ALLOW",
  "band": "AMBER",
  "device_id": "pixel8:XYZ",
  "manifest_hash": "sha256:...",
  "obligations": ["kernel.audit.log"],
  "timestamp": "2025-10-31T14:00:00Z"
}
```

#### 3. QoS Tightening

```json
{
  "name": "kernel.qos.tighten",
  "details": {
    "band": "AMBER",
    "fanout_reduction": 0.5,
    "duration_seconds": 300
  }
}
```

**Effect**: Temporarily reduce query fanout/bandwidth for the device/tenant until duration expires.

#### 4. Device Re-authentication

```json
{
  "name": "kernel.device.reauth",
  "details": {
    "reason": "revoked_key",
    "reauth_required": true,
    "grace_period_seconds": 300
  }
}
```

**Effect**: Flag device for re-authentication; subsequent commands rejected until credential refresh.

### Obligation Execution Flow

```
1. PEP evaluates policy → generates decision + obligations
2. MinimalGate validates envelope (before obligation application)
3. UoW.begin() transaction
4. Apply obligations (redaction, audit log entries, QoS updates)
5. Write to WAL with redacted payload (if applicable)
6. Emit audit/advisory events to bus
7. UoW.commit() → atomically persist WAL + obligation log
8. Emit receipt with obligation metadata
9. (Async) Indexers process Outbox entries + redaction directives
```

### Obligation Log Schema

Obligations are persisted in `st_obligation_log` table (created by migration `0002_pem_obligations.sql`):

```sql
CREATE TABLE st_obligation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wal_pos INTEGER NOT NULL,
  obligation TEXT NOT NULL,
  details_json TEXT,
  commit_ts TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  FOREIGN KEY(wal_pos) REFERENCES st_wal(pos)
);
```

Query obligation history:

```bash
# List recent redaction obligations
sqlite3 data/kernel.sqlite3 \
  "SELECT wal_pos, obligation, details_json FROM st_obligation_log \
   WHERE obligation='kernel.redact.enforce' \
   ORDER BY commit_ts DESC LIMIT 10;"

# Audit trail for device
sqlite3 data/kernel.sqlite3 \
  "SELECT commit_ts, obligation, details_json FROM st_obligation_log \
   WHERE device_id='pixel8:XYZ' \
   ORDER BY commit_ts DESC LIMIT 50;"
```

---

## Metrics & Observability

### Prometheus Metrics

PEM exports the following metrics:

```
# Decisions by outcome
k0_pep_decisions_total{decision,band,schema_uri,lane}
  # Labels: decision=ALLOW|DENY|REDACT
  #         band=GREEN|AMBER|RED
  #         schema_uri=memory.delta|events.action|etc.
  #         lane=default|fast|batch

# Obligations applied
k0_pep_obligations_total{obligation,decision,band}
  # Labels: obligation=redact|audit|qos.tighten|device.reauth
  #         decision=ALLOW|DENY|REDACT
  #         band=GREEN|AMBER|RED

# Policy evaluation latency (milliseconds)
k0_pep_evaluation_latency_ms (histogram)
  # P50, P95, P99 tracked separately
```

### Observability Events

Policy decisions are emitted to the `policy.*` SSE topic:

```json
{
  "event_type": "command_policy_decision",
  "decision": "ALLOW",
  "band": "GREEN",
  "device_id": "pixel8:XYZ",
  "tenant_id": "household:abc123",
  "space_id": "space-home",
  "topic": "memory.formation",
  "schema_uri": "mem://m1",
  "manifest_version": "1.0",
  "manifest_hash": "sha256:OsIL+WVh...",
  "obligations": [
    {
      "name": "kernel.audit.log",
      "details": {"level": "amber"}
    }
  ],
  "evaluation_latency_ms": 1.2,
  "cognitive_trace_id": "trace-uuid-123",
  "timestamp": "2025-10-31T14:00:00.123Z"
}
```

### Dashboard & Alerting

View PEM metrics in Grafana:

1. Navigate to `http://localhost:3000`
2. Open Dashboard: **"K0 Policy Enforcement"**
3. Key panels:
   - **Decision Rate**: `k0_pep_decisions_total` by decision type
   - **Obligation Distribution**: Top obligations applied per band
   - **Latency Trends**: P50/P95/P99 evaluation time
   - **Deny Reasons**: Top denial reasons by device/tenant

**Alert Rules** (in `k0/deploy/telemetry/prometheus.yml`):

```yaml
groups:
  - name: pem_alerts
    rules:
      - alert: PEMDenyRateHigh
        expr: rate(k0_pep_decisions_total{decision="DENY"}[5m]) > 0.1
        for: 2m
        annotations:
          summary: "PEP deny rate elevated ({{ $value }}/sec)"

      - alert: PEMEvaluationLatencyHigh
        expr: k0_pep_evaluation_latency_ms{quantile="0.95"} > 10
        for: 1m
        annotations:
          summary: "PEP evaluation P95 latency high ({{ $value }}ms)"
```

---

## Troubleshooting

### Issue 1: Policy Decisions Not Applied

**Symptom**: Commands always returning 200 OK; no redaction happening.

**Diagnosis**:

```bash
# 1. Check if PEM is enabled
curl http://localhost:8080/config | jq '.pem.enabled'

# 2. Check manifest file exists
ls -la /k0/deploy/generated/manifests/allow_all.json

# 3. Verify manifest is valid JSON
python -m json.tool /k0/deploy/generated/manifests/allow_all.json

# 4. Check logs for PEM errors
docker logs k0-kernel --tail=100 | grep -i "pem\|policy"
```

**Resolution**:

```bash
# Reload manifest
curl -X POST http://localhost:8080/admin/pem/reload-manifest

# Verify reload succeeded
curl http://localhost:8080/config | jq '.pem.manifest_hash'
```

### Issue 2: Policy Schema Version Mismatch

**Symptom**: Devices returning **HTTP 412 Precondition Failed** with error:

```json
{
  "error": {
    "code": "POLICY_VERSION_MISMATCH",
    "reason": "Manifest version '1.0' not active; expected '1.1'",
    "component": "kernel.pep"
  }
}
```

**Diagnosis**:

```bash
# Check current manifest version
sqlite3 /k0/deploy/data/kernel.sqlite3 \
  "SELECT manifest_version FROM schema_registry WHERE schema_uri='policy' LIMIT 1;"

# Check what version device is using
curl -X GET "http://localhost:8080/metrics" | grep "pem_policy_version"
```

**Resolution**:

```bash
# Option 1: Device updates to new manifest version
# (Device should fetch manifest from /k0/policy/manifest endpoint and retry)

# Option 2: Rollback kernel policy version (emergency only)
curl -X POST http://localhost:8080/admin/pem/rollback-manifest \
  -H "Content-Type: application/json" \
  -d '{"rollback_to": "1.0"}'
```

### Issue 3: Redaction Not Working

**Symptom**: Sensitive fields visible in WAL after redaction obligation applied.

**Diagnosis**:

```bash
# 1. Check if redaction obligation was emitted
sqlite3 /k0/deploy/data/kernel.sqlite3 \
  "SELECT * FROM st_obligation_log WHERE obligation='kernel.redact.enforce' LIMIT 1;"

# 2. Check redaction configuration
curl http://localhost:8080/config | jq '.pem.redaction'

# 3. Verify redaction directives in obligation details
sqlite3 /k0/deploy/data/kernel.sqlite3 \
  "SELECT details_json FROM st_obligation_log WHERE obligation='kernel.redact.enforce' LIMIT 1;"
```

**Resolution**:

```bash
# Update redaction configuration in k0.ps1 and redeploy
# Or use environment variable:
export K0_PEM_REDACTION_FIELDS=device_id,tenant_id,user_email
export K0_PEM_REDACTION_MASK="***REDACTED***"

# Restart kernel
./k0.ps1 restart
```

### Issue 4: High PEP Evaluation Latency

**Symptom**: `k0_pep_evaluation_latency_ms{quantile="0.95"} > 10ms`.

**Diagnosis**:

```bash
# Check manifest size (larger manifests = slower evaluation)
ls -lah /k0/deploy/generated/manifests/*.json

# Check if manifest is cached (should be <2ms if cached)
curl http://localhost:8080/metrics | grep "pem_manifest_cache"

# Profile PEP module
docker exec k0-kernel python -m cProfile -s cumulative -m k0.policy.pep_syscall
```

**Resolution**:

```bash
# 1. Optimize manifest (split into smaller tenant-specific manifests)
# 2. Enable PEP evaluation caching (already default, 5 min TTL)
# 3. Use fast-path decision (no ABAC rules for hot tenants)

# Check cache hit rate
curl http://localhost:8080/metrics | grep "pem_manifest_cache_hits"
```

### Issue 5: Device Revoked but Still Able to Submit Commands

**Symptom**: Revoked device key still accepted; commands not rejected.

**Diagnosis**:

```bash
# Check device key status
sqlite3 /k0/deploy/data/kernel.sqlite3 \
  "SELECT device_id, key_state, revoked_ts FROM st_device_keys WHERE device_id='pixel8:XYZ';"

# Check if revocation obligation was applied
sqlite3 /k0/deploy/data/kernel.sqlite3 \
  "SELECT * FROM st_obligation_log WHERE obligation='kernel.device.reauth' \
   AND device_id='pixel8:XYZ' ORDER BY commit_ts DESC LIMIT 1;"

# Check key cache TTL
curl http://localhost:8080/config | jq '.pem.key_cache_ttl_seconds'
```

**Resolution**:

```bash
# 1. Refresh key cache immediately
curl -X POST http://localhost:8080/admin/pem/refresh-key-cache

# 2. Force revocation (should be immediate)
curl -X POST http://localhost:8080/admin/pem/revoke-device \
  -H "Content-Type: application/json" \
  -d '{"device_id": "pixel8:XYZ", "reason": "security_incident"}'

# 3. Verify device is now rejected
curl -X POST http://localhost:8080/k0/command.submit \
  -H "Content-Type: application/json" \
  -d '{...device payload...}' \
  # Should return 403 with "kernel.device.reauth" obligation
```

---

## Best Practices

### 1. Manifest Versioning

Always version your manifests semantically:

```json
{
  "version": "1.0.0",  // SemVer format
  "tenant": "tenant-001",
  "space": "space-home"
}
```

**Deployment workflow**:

```bash
# 1. Create new manifest version
cp /k0/deploy/generated/manifests/allow_all.json \
   /k0/deploy/generated/manifests/allow_all_v1.1.0.json

# 2. Update manifest with new rules
vi /k0/deploy/generated/manifests/allow_all_v1.1.0.json

# 3. Register new version (no reload yet)
curl -X POST http://localhost:8080/admin/pem/register-manifest \
  -H "Content-Type: application/json" \
  -d @/k0/deploy/generated/manifests/allow_all_v1.1.0.json

# 4. Validate in staging (run tests)
pytest tests/k0/pem/

# 5. Activate new manifest (immediate effect)
curl -X POST http://localhost:8080/admin/pem/activate-manifest \
  -H "Content-Type: application/json" \
  -d '{"version": "1.1.0"}'

# 6. Monitor metrics
watch 'curl http://localhost:9090/api/v1/query?query=rate(k0_pem_decisions_total%5B1m%5D) | jq'

# 7. If rollback needed
curl -X POST http://localhost:8080/admin/pem/rollback-manifest \
  -d '{"rollback_to": "1.0.0"}'
```

### 2. Obligation Auditing

Always audit obligation decisions for compliance:

```sql
-- Daily obligation report
SELECT
  DATE(commit_ts) as day,
  obligation,
  COUNT(*) as count,
  COUNT(DISTINCT device_id) as unique_devices,
  COUNT(DISTINCT space_id) as unique_spaces
FROM st_obligation_log
WHERE commit_ts > datetime('now', '-1 day')
GROUP BY DATE(commit_ts), obligation
ORDER BY day DESC, count DESC;

-- Per-device redaction history (last 30 days)
SELECT
  device_id,
  COUNT(*) as redaction_count,
  MAX(commit_ts) as last_redacted
FROM st_obligation_log
WHERE obligation='kernel.redact.enforce'
  AND commit_ts > datetime('now', '-30 days')
GROUP BY device_id
ORDER BY redaction_count DESC;
```

### 3. Gradual Rollout

Deploy PEM changes gradually using feature flags:

```yaml
# k0/deploy/env/k0.env
K0_PEM_ENABLED=true
K0_PEM_ENFORCEMENT_MODE=shadow  # shadow | enforce | disabled
K0_PEM_SHADOW_RATIO=0.1         # Evaluate for 10% of traffic
```

Monitoring during rollout:

```bash
# 1. Shadow mode (0% enforcement, 100% metrics)
K0_PEM_ENFORCEMENT_MODE=shadow ./k0.ps1 restart

# 2. Monitor metrics for 1 hour
watch 'curl http://localhost:9090/api/v1/query?query=rate(k0_pem_decisions_total%5B5m%5D)'

# 3. Gradually increase enforcement ratio
for ratio in 0.1 0.25 0.5 0.75 1.0; do
  echo "Testing with ratio=$ratio"
  K0_PEM_SHADOW_RATIO=$ratio ./k0.ps1 restart
  sleep 300  # 5 minutes between steps
  # Check error rates...
done

# 4. Full enforcement
K0_PEM_ENFORCEMENT_MODE=enforce ./k0.ps1 restart
```

### 4. Security Best Practices

- **Sensitive fields**: Always include in redaction directives:

  ```bash
  K0_PEM_REDACTION_FIELDS=device_id,tenant_id,user_email,ssn,credit_card
  ```

- **Audit all denials**: Set up alerts for high deny rates:

  ```yaml
  - alert: PEMDenyRateSpike
    expr: rate(k0_pep_decisions_total{decision="DENY"}[5m]) > 0.5
    for: 1m
  ```

- **Key rotation**: Rotate device keys at least quarterly:

  ```bash
  # Rotate all GREEN band devices
  curl -X POST http://localhost:8080/admin/pem/rotate-keys \
    -d '{"band": "GREEN", "grace_period_seconds": 1800}'
  ```

---

## Emergency Operations

### Scenario 1: Disable PEM Temporarily

If PEM is causing production issues, disable it immediately:

```bash
# Set enforcement mode to disabled (still evaluate, but don't apply obligations)
export K0_PEM_ENFORCEMENT_MODE=disabled
./k0.ps1 restart

# Verify PEM is disabled
curl http://localhost:8080/config | jq '.pem.enforcement_mode'

# Investigate root cause (check logs)
docker logs k0-kernel --tail=200 | grep -i "pem\|policy"

# Re-enable once issue is resolved
export K0_PEM_ENFORCEMENT_MODE=enforce
./k0.ps1 restart
```

### Scenario 2: Mass Redaction Needed (GDPR/Privacy Incident)

If there's a privacy incident and you need to redact entire datasets:

```bash
# 1. Create emergency redaction manifest
cat > /tmp/emergency_redact.json << 'EOF'
{
  "version": "emergency.1.0",
  "tenant": "*",
  "space": "*",
  "bands": {
    "GREEN": { "deny": false, "obligations": [{"name": "kernel.redact.enforce", "details": {"scope": "ALL"}}] },
    "AMBER": { "deny": false, "obligations": [{"name": "kernel.redact.enforce", "details": {"scope": "ALL"}}] },
    "RED": { "deny": true }
  }
}
EOF

# 2. Activate emergency manifest
curl -X POST http://localhost:8080/admin/pem/activate-manifest \
  -H "Content-Type: application/json" \
  -d @/tmp/emergency_redact.json

# 3. Run redaction batch job (replays WAL with new redaction directives)
k0ctl replay --from 0 --apply-redaction-obligations

# 4. Verify redaction completed
sqlite3 /k0/deploy/data/kernel.sqlite3 \
  "SELECT COUNT(*) FROM st_obligation_log WHERE obligation='kernel.redact.enforce';"

# 5. Revert to normal manifest once redaction complete
curl -X POST http://localhost:8080/admin/pem/activate-manifest \
  -d '{"version": "1.0.0"}'
```

### Scenario 3: Policy Schema Corruption

If policy schema file becomes corrupted:

```bash
# 1. Check schema file
cat /k0/deploy/generated/manifests/allow_all.json | python -m json.tool

# 2. If corrupted, restore from backup
cp /k0/deploy/generated/manifests/.backup/allow_all.json.bak \
   /k0/deploy/generated/manifests/allow_all.json

# 3. Reload manifest
curl -X POST http://localhost:8080/admin/pem/reload-manifest

# 4. Verify schema loaded correctly
curl http://localhost:8080/admin/pem/status | jq '.manifest'

# 5. Permanently fix root cause (prevent future corruption)
chmod 444 /k0/deploy/generated/manifests/allow_all.json
```

---

## Related Documentation

- **K0 README**: [`k0/README.md`](../../../k0/README.md) — Overall K0 architecture and operation
- **ADR-0089**: [`docs/architecture/decisions/0089-k0-bridge-policy-enforcement.md`](../decisions/0089-k0-bridge-policy-enforcement.md) — Policy enforcement design decisions
- **Bridge Policy Contract**: [`k0/contracts/policy/bridge_policy.yml`](../../../k0/contracts/policy/bridge_policy.yml) — Formal policy constraints
- **Migration Guide**: [`docs/development/runbooks/k0-migration-guide.md`](./k0-migration-guide.md) — Database schema migration steps

---

## Support & Escalation

- **Operational Issue**: Check [Troubleshooting](#troubleshooting) section
- **Design Question**: Review ADR-0089 and bridge_policy.yml contract
- **Security Incident**: Contact <security-incident@familyos.dev> immediately
- **Performance Issue**: File ticket with `k0_pem_evaluation_latency_ms` metrics attached
