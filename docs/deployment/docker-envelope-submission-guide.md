# Docker Deployment & Envelope Submission Guide

**Purpose**: Step-by-step guide to boot K0 kernel in Docker and submit envelopes via HTTP API.

**Related**:
- Deployment Script: `k0/deploy/k0.ps1`
- Docker Compose: `k0/deploy/docker-compose.yml`
- Command Port: `k0/ports/command.py`
- P02 Pipeline: `k0/pipelines/p02_write/`

---

## 1. Prerequisites

- Docker Desktop installed and running
- PowerShell 5.1 or higher
- Neo4j password set in environment: `$env:NEO4J_PASSWORD`

```powershell
# Set Neo4j password (required)
$env:NEO4J_PASSWORD = "your-secure-password"
```

---

## 2. Boot Kernel in Docker

**Command**:
```powershell
cd d:\familyos\k0\deploy
.\k0.ps1 -Command up -Rebuild -Migrate -Verify
```

**What This Does**:
1. **Rebuild**: Builds `k0-kernel-local:latest` Docker image from `Dockerfile`
2. **Migrate**: Runs SQLite migrations via `apply_migrations()` (Python)
3. **Migrate**: Runs Neo4j Cypher schema migrations
4. **Start**: Launches services via `docker-compose up -d`:
   - `k0-kernel` on port **8080**
   - `neo4j` on ports **7474** (HTTP), **7687** (Bolt)
   - Prometheus, Grafana, Tempo (telemetry stack)
5. **Verify**: Health checks at `/healthz`, `/readyz`, Prometheus, Grafana

**Expected Output**:
```
✓ Building k0-kernel-local:latest...
✓ Running SQLite migrations...
✓ Running Neo4j schema migrations...
✓ Starting services...
✓ Verifying health checks...
  - Kernel /healthz: OK
  - Kernel /readyz: OK
  - Prometheus: OK
  - Grafana: OK
```

---

## 3. Verify Kernel is Running

**Health Check**:
```powershell
curl http://localhost:8080/healthz
```

**Expected Response**:
```json
{
  "status": "healthy",
  "version": "K0.1.0"
}
```

**Check Logs**:
```powershell
.\k0.ps1 -Command logs -Service k0-kernel
```

**Check Status**:
```powershell
.\k0.ps1 -Command status
```

---

## 4. Submit Envelope via HTTP

### 4.1 Envelope Structure (V1 Full Signature)

The `/k0/command.submit` endpoint expects **full envelope with signature fields** (not the flat P02 structure).

**Required Fields**:
```json
{
  "cognitive_trace_id": "uuid-v4",
  "tenant_id": "string",
  "space_id": "string",
  "topic": "string",
  "schema_uri": "string",
  "schema_version": "string",
  "actor": "string",
  "device_id": "string",
  "band": "GREEN" | "AMBER" | "RED",
  "policy_version": "string",
  "ts": "unix-timestamp",
  "sig": "signature-hex",
  "sig_alg": "ECDSA_P256_SHA256",
  "sig_kid": "did:device:device-name#timestamp",
  "envelope_sha256": "sha256-hex",
  "body": { ... }
}
```

**Optional Fields**:
- `idem_key`: Custom idempotency key (auto-generated if omitted)
- `payload_sha256`: SHA-256 hash of body
- `payload_bytes`: Body size in bytes
- `policy`, `policy_ctx`, `pep`: Policy metadata
- `location_geohash`, `location_precision_m`: Location privacy

---

### 4.2 Example Envelope (Minimal)

**File**: `example_envelope.json`

```json
{
  "cognitive_trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "tenant_id": "tenant_001",
  "space_id": "space_001",
  "topic": "memory.episodic.formation",
  "schema_uri": "https://familyos.ai/schemas/memory/episodic/v1",
  "schema_version": "1.0.0",
  "actor": "user_alice",
  "device_id": "device_phone_001",
  "band": "GREEN",
  "policy_version": "2025-11-01",
  "ts": "1732800000",
  "sig": "304502210098a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef123456022018fedcba9876543210fedcba9876543210fedcba9876543210fedcba987654",
  "sig_alg": "ECDSA_P256_SHA256",
  "sig_kid": "did:device:device_phone_001#1732800000",
  "envelope_sha256": "d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
  "idem_key": "tenant_001:device_phone_001:1732800000:12345",
  "payload_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
  "payload_bytes": 145,
  "body": {
    "text": "Had a great family dinner at home tonight with the kids",
    "activity_type": "routine",
    "content_type": "episodic",
    "participants": ["user_alice", "child_bob", "child_charlie"],
    "location": {
      "type": "home",
      "name": "Home"
    },
    "duration_minutes": 45
  }
}
```

---

### 4.3 Submit via curl

**PowerShell**:
```powershell
curl.exe -X POST http://localhost:8080/k0/command.submit `
  -H "Content-Type: application/json" `
  -d '@example_envelope.json'
```

**Expected Response (202 Accepted)**:
```json
{
  "receipt_id": "f9e8d7c6-b5a4-3210-9876-543210fedcba",
  "commit_ts": "2024-11-28T12:00:00Z",
  "offsets": {
    "st_wal": 12345,
    "st_outbox": 67890
  },
  "idem_key": "tenant_001:device_phone_001:1732800000:12345",
  "obligations": [],
  "policy_manifest_fingerprint": "abc123def456",
  "obligation_details": []
}
```

---

### 4.4 Submit via Invoke-RestMethod (PowerShell native)

```powershell
$envelope = Get-Content example_envelope.json | ConvertFrom-Json
$response = Invoke-RestMethod -Uri "http://localhost:8080/k0/command.submit" `
  -Method POST `
  -ContentType "application/json" `
  -Body (ConvertTo-Json $envelope -Depth 10)

# Display response
$response | ConvertTo-Json -Depth 10
```

---

## 5. Verify P02 Pipeline Execution

### 5.1 Check Kernel Logs

**Watch for P02 processing**:
```powershell
.\k0.ps1 -Command logs -Service k0-kernel -Follow
```

**Look for**:
- `[P02] Processing envelope cognitive_trace_id=a1b2c3d4-...`
- `[P02] M01 pattern_separate: SimHash/MinHash computed`
- `[P02] M02 semantic_project: embedding_id generated`
- `[P02] M13 hipp_events_row: 86-field row created`
- `[P02] M14 embedding_queue_write: Job queued for P08`

---

### 5.2 Query Database

**Connect to SQLite**:
```powershell
cd d:\familyos\k0\deploy
sqlite3 ./data/kernel.sqlite3
```

**Check WAL Entry**:
```sql
SELECT cognitive_trace_id, topic, band, wal_pos, committed_at
FROM st_wal
WHERE cognitive_trace_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
```

**Check Outbox**:
```sql
SELECT outbox_id, cognitive_trace_id, driver, operation, dispatched_at
FROM st_outbox
WHERE cognitive_trace_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
```

**Check Hippocampus Events (P02 Output)**:
```sql
SELECT
  event_id, cognitive_trace_id, tenant_id, space_id,
  embedding_id, salience_score, affect_valence, affect_arousal,
  social_group_id, device_group_id, retention_band
FROM st_hipp_events
WHERE cognitive_trace_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
```

**Check Embedding Queue (P08 Input)**:
```sql
SELECT embedding_id, status, cognitive_trace_id, enqueued_at
FROM embedding_queue
WHERE cognitive_trace_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
```

---

### 5.3 Verify Field Counts

**Expected Enrichment**:
- **Input**: 18 fields from Command Port (cognitive_trace_id, tenant_id, space_id, etc.)
- **After M01**: +3 fields (SimHash, MinHash digests)
- **After M02**: +4 fields (embedding_id, entity counts)
- **After M04**: +11 fields (affect valence/arousal, emotions)
- **After M05**: +1 field (visible_to ACLs)
- **After M07**: +10 fields (social context, family graph)
- **After M08**: +9 fields (temporal profile)
- **After M09**: +4 fields (device profile)
- **After M10**: +6 fields (content classification)
- **After M11**: +5 fields (geo metadata)
- **After M12**: +2 fields (spatial privacy geohash)
- **After M15**: +3 fields (retention policy)
- **After M06**: +1 field (salience score)
- **Final**: 86 fields in `st_hipp_events`

**Verify**:
```sql
SELECT COUNT(*) as field_count
FROM pragma_table_info('st_hipp_events');
```

---

## 6. Error Handling

### 6.1 Gate Rejection (400 Bad Request)

**Example Response**:
```json
{
  "error": {
    "code": "REJECTED_KERNEL_GATE",
    "component": "kernel.gate",
    "reason": "PAYLOAD_HASH_MISMATCH",
    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "hint": "payload_sha256 does not match computed hash"
  }
}
```

**Fix**: Ensure `payload_sha256` matches SHA-256 of canonical JSON body.

---

### 6.2 Policy Denial (403 Forbidden)

**Example Response**:
```json
{
  "error": {
    "code": "PEP_DENY",
    "component": "kernel.policy",
    "reason": "ROLE_FORBIDDEN",
    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**Fix**: Check policy manifest at `k0/deploy/generated/manifests/`.

---

### 6.3 Idempotency Conflict (409 Conflict)

**Example Response**:
```json
{
  "receipt_id": "11111111-2222-3333-4444-555555555555",
  "commit_ts": "2024-11-28T12:00:00Z",
  "idem_key": "tenant_001:device_phone_001:1732800000:12345",
  "offsets": {
    "st_wal": 12345,
    "st_outbox": 67890
  }
}
```

**Meaning**: Envelope already processed (within 60s idempotency window).

---

### 6.4 QoS Budget Exhausted (429 Too Many Requests)

**Example Response**:
```json
{
  "error": {
    "code": "QOS_BUDGET_EXHAUSTED",
    "component": "kernel.qos",
    "reason": "FANOUT_BUDGET_EXHAUSTED",
    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "budgets": {"fanout": 0, "top_k": 8},
    "hint": "Reduce fanout request"
  }
}
```

**Fix**: Reduce fanout obligations or wait for budget refresh.

---

## 7. Shutdown

**Stop Services**:
```powershell
.\k0.ps1 -Command down
```

**Clean Volumes** (optional, deletes database):
```powershell
docker-compose down -v
```

---

## 8. Troubleshooting

### Database Not Found

**Problem**: `sqlite3: ./data/kernel.sqlite3 not found`

**Fix**: Ensure migrations ran during startup:
```powershell
.\k0.ps1 -Command up -Migrate
```

---

### Policy Manifest Missing

**Problem**: `PEP_CONFIGURATION_ERROR`

**Fix**: Create default allow_all.json:
```powershell
# Script auto-creates ./generated/manifests/allow_all.json
.\k0.ps1 -Command up -Rebuild
```

---

### Neo4j Connection Failed

**Problem**: `Neo4jConnectionError`

**Fix**: Check Neo4j container:
```powershell
docker logs k0-neo4j-1
```

---

### P02 Not Processing

**Problem**: Envelope accepted but no st_hipp_events row

**Checklist**:
1. Check outbox: `SELECT * FROM st_outbox WHERE dispatched_at IS NULL;`
2. Check logs: `.\k0.ps1 -Command logs -Service k0-kernel`
3. Verify P02 worker running: Look for `[P02] Starting outbox worker`
4. Check module errors: Look for `[P02] M## failed` in logs

---

## 9. Next Steps

**End-to-End Test Script**:
Create automated test that:
1. Boots kernel in Docker
2. Submits envelope
3. Verifies st_hipp_events row
4. Shuts down

**Example**:
```powershell
# test-docker-e2e.ps1
.\k0.ps1 -Command up -Rebuild -Migrate -Verify

$envelope = @{
  cognitive_trace_id = [guid]::NewGuid().ToString()
  tenant_id = "test_tenant"
  space_id = "test_space"
  # ... full envelope ...
}

$response = Invoke-RestMethod -Uri "http://localhost:8080/k0/command.submit" `
  -Method POST -ContentType "application/json" `
  -Body (ConvertTo-Json $envelope -Depth 10)

Start-Sleep -Seconds 5

$result = sqlite3 ./data/kernel.sqlite3 `
  "SELECT COUNT(*) FROM st_hipp_events WHERE cognitive_trace_id = '$($envelope.cognitive_trace_id)';"

if ($result -eq 1) {
  Write-Host "✓ E2E Test PASSED"
} else {
  Write-Host "✗ E2E Test FAILED"
}

.\k0.ps1 -Command down
```

---

## 10. References

- **Whiteboard**: `k0/pipelines/whiteboard.md` (Section 1: K0 Kernel Hot Path Design)
- **P02 Dossier**: `docs/pipelines/P02_write_dossier.md`
- **Command Port**: `k0/ports/command.py`
- **Integration Tests**: `tests/integration/test_p02_simple.py`
- **Module README**: `k0/modules/*/README.md`

---
