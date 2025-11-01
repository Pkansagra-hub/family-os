# K0 Kernel Local Deployment Guide# How to deploy k0 kernel



## OverviewRun from d:/familyos/k0/deploy:



This directory contains the **complete local development and testing infrastructure** for K0 Kernel with the **bridge policy enforcement** workflow. The deployment orchestrates:```powershell

powershell -ExecutionPolicy Bypass -File .\k0.ps1 up -Verify -WaitSeconds 10

- **K0 Kernel** (core enforcement engine with PEM)```

- **Policy Enforcement Module (PEM)** (manifest fingerprinting, obligation evaluation, redaction)

- **Observability Stack** (Prometheus, Grafana, Tempo, AlertManager)Notes:

- **SQLite Backend** (WAL-mode for concurrency)

- -Verify waits for services to become healthy

**Architecture Diagram:** See `../../architecture_diagrams/k1/k1_complete_with_flows.mmd` for K1-orchestrated K0 kernel interaction pattern.- -WaitSeconds sets readiness timeout (e.g., 10)

- If scripts are blocked, run: `Set-ExecutionPolicy -Scope Process Bypass -Force`

**Policy Contract:** See `../../k0/contracts/policy/bridge_policy.yml` for P00-P03 port definitions and manifest fingerprint validation.

---

## Quick Start

### Prerequisites

1. **Windows PowerShell 5.1+** (or PowerShell Core 7+)
2. **Docker Desktop** (with Compose v2.20+)
3. **Python 3.13+** (for migration scripts)
4. **SQLite 3.44+** (optional, for manual queries)

### Deploy & Verify

```powershell
# From d:\familyos\k0\deploy directory
cd .\deploy
powershell -ExecutionPolicy Bypass -File .\k0.ps1 up -Verify -WaitSeconds 15
```

**Expected Output:**
```
[k0] Starting services (kernel + telemetry)
...
[k0] Waiting 15 seconds before verification
[k0] Verifying service health
[k0] kernel /healthz: 200
[k0] kernel /readyz: 200
[k0] prometheus: 200
[k0] grafana: 200
[k0] alertmanager: 200
[k0] tempo: 200
```

### Hot Reload Development Workflow

For iterative development, enable file watching and automatic container restarts:

```powershell
# Start services with hot reload watcher
.\k0.ps1 up -HotReload -Verify -WaitSeconds 15

# Or start watcher on already-running services
.\k0.ps1 watch
```

**What hot reload does:**
- 📁 **Watches** `k0/` directory for file changes
- ⚡ **Config Reloads** (SIGHUP): `*.yml`, `*.yaml`, `*.json` changes trigger graceful reload (no restart)
- 🔄 **Code Restarts** (Orchestrated): Python code changes trigger:
  1. Send SIGTERM to container (graceful drain)
  2. Wait for inflight requests to complete
  3. Restart container
  4. Poll health checks until ready
  5. Resume watching

**Terminal UI** shows real-time status:
```
[14:32:05] 🟢 WATCHING  - k0/ directory monitored
[14:32:15] 📝 CONFIG RELOAD - k0/config/kernel.yml changed (SIGHUP)
[14:32:16] ⏳ Container healthy - ready for requests
[14:32:45] 🔄 CODE RESTART - k0/kernel/core.py changed
[14:32:46] ⏳ Draining... waiting for requests
[14:32:48] 🔄 Restarting container k0-kernel
[14:33:02] ✅ Container healthy - resuming watch
```

**Full hot reload documentation:** See `k0/automation/README.md` - Milestone F.1.1 section

### Validation Test

Once healthy, test the policy enforcement flow:

```powershell
# Test command submission with policy enforcement
$envelope = @{
    tenant = "tenant-001"
    space = "space-home"
    device = "device-local-001"
    command = @{
        id = "cmd-001"
        action = "read_profile"
        resource = "/profiles/family"
    }
} | ConvertTo-Json

curl -X POST http://localhost:8080/k0/command.submit `
  -H "Content-Type: application/json" `
  -d $envelope
```

**Expected Response (200 OK with policy decision):**
```json
{
  "command_id": "cmd-001",
  "status": "ALLOWED",
  "obligations": ["kernel.audit.log"],
  "decision_id": "pem-xyz-123"
}
```

---

## Directory Structure

```
k0/deploy/
├── readme.md                              # This file
├── k0.ps1                                 # Main deployment orchestration script
├── docker-compose.yml                     # Docker Compose config (kernel + telemetry)
├── local-single-node-telemetry.yml        # Observability services stack
│
├── env/
│   └── k0.env                            # Environment variables
│       ├── K0_POLICY_MANIFEST_PATH       # (NEW) Path to policy manifest JSON
│       ├── K0_BRIDGE_POLICY_CONTRACT_PATH # (NEW) Path to bridge_policy.yml
│       ├── K0_PEM_REDACTION_ENABLED      # (NEW) Redaction directive processing
│       ├── K0_PEM_AUDIT_ENABLED          # (NEW) Policy decision audit logging
│       └── K0_QOS_*                      # QoS timeouts
│
├── config/
│   ├── grafana/                          # Grafana dashboard provisioning
│   ├── prometheus/                       # Prometheus scrape configs
│   └── alertmanager/                     # Alert routing rules
│
├── data/                                 # (Auto-created) SQLite database
│   └── k0_kernel.db
│
├── secrets/                              # (Auto-created) Signing keys, certificates
│   ├── signing_key.pem
│   └── public_key.pem
│
├── telemetry/                            # Static observability configs (NOT generated)
│   ├── prometheus.yml
│   ├── tempo.yaml
│   ├── alertmanager.yml
│   └── grafana/
│       └── provisioning/
│
├── generated/                            # AUTO-SYNCED from k0/telemetry/generated/
│   ├── manifests/                        # (NEW) Policy manifest JSON files
│   │   └── allow_all.json               # Default development manifest
│   ├── rules/                           # Prometheus recording rules (synced from k0/telemetry/generated/rules/)
│   │   └── slo_alerts.yaml
│   └── dashboards/                      # Grafana dashboards (synced from k0/telemetry/generated/dashboards/)
│       ├── kernel_overview.json
│       ├── command_latency.json
│       ├── query_latency.json
│       ├── sse_health.json
│       └── replay_throughput.json
│
└── logs/                                # (Auto-created) Service logs
```

### Telemetry Artifact Sync Strategy

**Single Source of Truth**: All telemetry rendering happens in `k0/telemetry/`:
1. `k0/telemetry/slo_definitions.yaml` — SLO definitions (source of truth)
2. `k0/telemetry/render.py` — Generates dashboards + rules to `k0/telemetry/generated/`
3. `k0/deploy/k0.ps1` **→ `Sync-Telemetry-Artifacts` function** — Auto-syncs artifacts on `up`: `k0/telemetry/generated/* → k0/deploy/generated/`

**Workflow**:
```
┌─────────────────────────────────────────────────────┐
│ Edit SLO definitions                                │
│ k0/telemetry/slo_definitions.yaml                   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│ Render dashboards & alert rules                     │
│ python -m k0.telemetry.render --verbose            │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼ (outputs to)
┌─────────────────────────────────────────────────────┐
│ k0/telemetry/generated/                            │
│ ├── dashboards/*.json                              │
│ └── rules/slo_alerts.yaml                          │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼ (auto-sync on deploy start)
┌─────────────────────────────────────────────────────┐
│ k0/deploy/k0.ps1 up                                │
│ → Sync-Telemetry-Artifacts                         │
│ → k0/deploy/generated/                             │
│ ├── dashboards/*.json (for Grafana)               │
│ ├── rules/*.yaml (for Prometheus)                 │
│ └── checksums_*.json (for validation)             │
└─────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│ Docker Compose mounts                              │
│ - ./generated/dashboards → /mnt/grafana/dashboards │
│ - ./generated/rules → /etc/prometheus/rules        │
└─────────────────────────────────────────────────────┘
```

**Key Points**:
- ✅ `k0/telemetry/generated/` is the single source of truth
- ✅ `k0/deploy/generated/` is auto-synced on **every** `k0.ps1 up` command (via `Sync-Telemetry-Artifacts`)
- ✅ Changes only flow through: SLO definitions → render → sync → deploy
- ✅ `k0/deploy/telemetry/` contains static configs (prometheus.yml, alertmanager.yml, grafana provisioning)
- ✅ Checksums automatically copied for drift detection in CI

### Implementation Details: Sync Function

The `Sync-Telemetry-Artifacts` function in `k0.ps1` handles:
1. **Source validation**: Checks `k0/telemetry/generated/` exists
2. **Directory creation**: Creates `k0/deploy/generated/dashboards` and `rules` if needed
3. **Dashboard sync**: Copies all `*.json` files from source to deploy (preserves modification times)
4. **Rule sync**: Copies all `*.yaml` files from source to deploy (Prometheus reads these)
5. **Checksum sync**: Copies validation checksums for CI drift detection
6. **Logging**: Reports what was synced with green success messages

**Example output** (when running `k0.ps1 up`):
```
[k0] Syncing telemetry artifacts from source to deployment
[k0] Syncing dashboards: D:\familyos\k0\telemetry\generated/dashboards -> D:\familyos\k0\deploy\generated\dashboards
[k0] Dashboards synced
[k0] Syncing alert rules: D:\familyos\k0\telemetry\generated/rules -> D:\familyos\k0\deploy\generated\rules
[k0] Alert rules synced
```

---

### Key Mount Points in Docker Compose

- `/data` ← SQLite database directory
- `/secrets` ← Signing keys for envelope verification (read-only)
- `/app/k0/contracts/policy/pep.schema.json` ← Policy schema
- `/app/k0/contracts/policy/bridge_policy.yml` ← (NEW) Bridge contract
- `/mnt/policy` ← (NEW) Policy manifests from generated/manifests

---

## Configuration

### Policy Manifest (`env/k0.env`)

**New PEM variables (Phase 1 bridge integration):**

```bash
# Policy manifest path (JSON file with policy rules)
# LOCAL DEV: /app/k0/contracts/policy/pep.schema.json (built-in default)
# CUSTOM: /mnt/policy/allow_all.json (from volume mount)
# PRODUCTION: provisioned by bridge via secure channel
K0_POLICY_MANIFEST_PATH=/app/k0/contracts/policy/pep.schema.json

# Bridge policy contract (defines P00-P03 endpoints)
K0_BRIDGE_POLICY_CONTRACT_PATH=/app/k0/contracts/policy/bridge_policy.yml

# Feature Flags
K0_PEM_REDACTION_ENABLED=true            # Process kernel.redact.* obligations
K0_PEM_METRICS_ENABLED=true              # Export k0_pem_* metrics
K0_PEM_AUDIT_ENABLED=true                # Log policy decisions with trace_id

# Decision caching (for high-throughput scenarios)
K0_PEM_DECISION_CACHE_TTL_MS=5000        # Cache policy decisions for 5s
```

### Policy Manifest Format (`generated/manifests/allow_all.json`)

Example allow_all development manifest:

```json
{
  "version": "1.0",
  "tenant": "tenant-001",
  "space": "space-home",
  "fingerprint": "sha256:...",
  "policies": [
    {
      "name": "allow_all",
      "band": "GREEN",
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

**Manifest Validation (automatic):**
- ✓ Valid JSON structure
- ✓ SHA-256 fingerprint computation
- ✓ Version compatibility with bridge contract
- ✓ Required fields: version, tenant, policies

---

## Deployment Commands

### Start Services

```powershell
# Basic up
.\k0.ps1 up

# Up with verification (waits for health checks)
.\k0.ps1 up -Verify -WaitSeconds 15

# Up with hot reload watcher (for development iteration)
.\k0.ps1 up -HotReload -Verify -WaitSeconds 15

# Up with Docker image rebuild
.\k0.ps1 up -Rebuild -Verify

# Up with database migration
.\k0.ps1 up -Migrate -Verify

# Up with all validations
.\k0.ps1 up -Rebuild -Migrate -Verify -WaitSeconds 20
```

### Hot Reload Development (Watcher Process)

Start the hot reload watcher separately (useful if services already running):

```powershell
# Start watcher on already-running services
.\k0.ps1 watch

# Watcher will:
# - Monitor k0/ directory for changes
# - Send SIGHUP on config file changes (graceful reload)
# - Orchestrate container restart on code changes
# - Display real-time status in terminal
```

### Stop Services

```powershell
.\k0.ps1 down
```

### Restart Services

```powershell
.\k0.ps1 restart -Verify
```

### Check Status

```powershell
.\k0.ps1 status
```

### View Logs

```powershell
# All services
.\k0.ps1 logs

# Specific service
.\k0.ps1 logs -Service k0-kernel

# Follow real-time
.\k0.ps1 logs -Service k0-kernel   # (Press Ctrl+C to exit)
```

---

## Validation & Testing

### Health Checks (automatic with `-Verify`)

```
✓ K0 Kernel /healthz (dependency ready)
✓ K0 Kernel /readyz (accepting requests)
✓ Prometheus (metrics collection)
✓ Grafana (dashboards)
✓ AlertManager (alert routing)
✓ Tempo (trace collection)
```

### Manual Command Submission

```powershell
# Example: Test ALLOW policy
$envelope = @{
    tenant = "tenant-001"
    space = "space-home"
    device = "device-local-001"
    command = @{
        id = "cmd-001"
        action = "read_profile"
        resource = "/profiles/family"
    }
} | ConvertTo-Json

curl -X POST http://localhost:8080/k0/command.submit `
  -H "Content-Type: application/json" `
  -d $envelope

# Expected: 200 OK with ["kernel.audit.log"] obligations
```

### Redaction Flow Test

```powershell
# Example: Test REDACT policy
$envelope = @{
    tenant = "tenant-001"
    space = "space-home"
    device = "device-local-001"
    command = @{
        id = "cmd-002"
        action = "read_records"
        resource = "/records/shared"
    }
} | ConvertTo-Json

curl -X POST http://localhost:8080/k0/command.submit `
  -H "Content-Type: application/json" `
  -d $envelope

# Expected: 200 OK with ["kernel.redact.field:/records/shared/wal_body"] obligations
# WAL body field will be masked in response envelope
```

### Manifest Fingerprint Mismatch (HTTP 412)

```powershell
# Simulate stale manifest fingerprint
# 1. Change policy manifest file
# 2. Resubmit command with old fingerprint in bridge context
# 3. Expect: HTTP 412 POLICY_VERSION_MISMATCH

curl -X POST http://localhost:8080/k0/command.submit `
  -H "X-Policy-Fingerprint: sha256:old-fingerprint" `
  -H "Content-Type: application/json" `
  -d $envelope

# Expected: 412 with error: "POLICY_VERSION_MISMATCH"
```

---

## Troubleshooting

### Issue: Services fail to start

**Symptoms:** `docker compose up` exits with error

**Solution:**
```powershell
# Check for port conflicts
netstat -ano | Select-String 8080,9090,3000,9093,4317

# Clear Docker state
docker compose down -v
docker system prune -f

# Retry with rebuild
.\k0.ps1 up -Rebuild -Verify
```

### Issue: HTTP 412 on policy-enforce commands

**Symptoms:** `/k0/command.submit` returns 412 POLICY_VERSION_MISMATCH

**Root Cause:** Manifest fingerprint validation failed

**Solution:**
```powershell
# 1. Verify manifest exists
Test-Path ".\generated\manifests\allow_all.json"

# 2. Check manifest validity
Get-Content ".\generated\manifests\allow_all.json" | ConvertFrom-Json

# 3. Compute current fingerprint
certutil -hashfile ".\generated\manifests\allow_all.json" SHA256

# 4. Restart kernel with manifest validation
.\k0.ps1 restart -Verify
```

### Issue: Redaction not working (WAL body not masked)

**Symptoms:** Response body contains unmasked WAL data despite `kernel.redact.field` obligations

**Root Cause:** Redaction pipeline disabled or obligation details malformed

**Solution:**
```powershell
# 1. Verify redaction enabled
grep "K0_PEM_REDACTION_ENABLED" ".\env\k0.env"   # Should be true

# 2. Check PEM logs for obligation processing
.\k0.ps1 logs -Service k0-kernel | Select-String "kernel.redact"

# 3. Inspect raw obligations in response
curl http://localhost:8080/k0/command.submit ... | ConvertFrom-Json | Select -ExpandProperty obligations

# 4. If obligation details are strings like "[...]" instead of arrays,
#    this indicates stringification bug - rebuild and restart
.\k0.ps1 up -Rebuild -Verify
```

### Issue: SQLite database locked

**Symptoms:** `database is locked` errors in logs

**Root Cause:** WAL checkpoint conflict or stale connection

**Solution:**
```powershell
# 1. Stop services and check database
.\k0.ps1 down

# 2. Remove checkpoint files
Remove-Item ".\data\k0_kernel.db-wal" -Force -ErrorAction SilentlyContinue
Remove-Item ".\data\k0_kernel.db-shm" -Force -ErrorAction SilentlyContinue

# 3. Restart
.\k0.ps1 up -Migrate -Verify
```

### Issue: Prometheus/Grafana not collecting metrics

**Symptoms:** Grafana dashboards empty, no k0_pem_* metrics in Prometheus

**Root Cause:** PEM metrics disabled or scrape config stale

**Solution:**
```powershell
# 1. Verify metrics enabled
grep "K0_PEM_METRICS_ENABLED" ".\env\k0.env"    # Should be true

# 2. Check Prometheus targets
curl http://localhost:9090/api/v1/targets | ConvertFrom-Json

# 3. Query PEM metrics
curl "http://localhost:9090/api/v1/query?query=k0_pem_decisions_total"

# 4. If no metrics, restart with telemetry rebuild
.\k0.ps1 down
docker compose -f docker-compose.yml -f local-single-node-telemetry.yml up -d
```

---

## Bridge Handoff Instructions

### Phase 1: Development (Current - Local Kernel)

**Workflow:**
1. Deploy K0 kernel locally with default allow_all manifest
2. Test policy enforcement pipeline (PEM)
3. Verify manifest fingerprinting works
4. Validate obligation evaluation (ALLOW, DENY, REDACT)
5. Confirm redaction directives mask fields correctly
6. **Output:** Working kernel ready for bridge integration

**Checklist:**
- [ ] `.\k0.ps1 up -Rebuild -Migrate -Verify` succeeds
- [ ] All 16 bootstrap tests pass: `pytest tests/scripts/test_k0_bootstrap_harness.py`
- [ ] Manual command submission returns 200 OK with policy decisions
- [ ] Fingerprint mismatch correctly returns 412
- [ ] Redaction test masks WAL body field
- [ ] Observability stack metrics/traces flowing

### Phase 2: Bridge Integration (Upcoming - K1 Orchestrator)

**What changes:**
- K1 orchestrator becomes manifest provisioning authority
- Bridge P00-P03 ports implement manifest delivery
- K0 calls P01 `.policy.manifest.describe` to fetch fingerprint
- K0 validates manifest signature + fingerprint before policy decision
- K1 handles rolling manifest upgrades without K0 downtime

**Handoff Artifacts (Phase 1 → Phase 2):**
1. **Bridge Contract:** `k0/contracts/policy/bridge_policy.yml` (defines P00-P03)
2. **PEM Implementation:** `k0/policy/pep_syscall.py` with fingerprinting working
3. **Docker Config:** `docker-compose.yml` with manifest volume mounts
4. **Deployment Script:** `k0.ps1` with manifest validation
5. **Test Suite:** 16 passing bootstrap tests
6. **Documentation:** This README + inline code comments

**Phase 2 Integration Points:**
- K1 orchestrator implements P00 (policy.manifest.push) to provision manifests
- K0 calls P01 (policy.manifest.describe) on command receive
- Automatic rollback on fingerprint mismatch (HTTP 412)
- Metrics: k0_pem_manifest_mismatches_total, k0_pem_policy_decisions_total

### Phase 3: Multi-Agent Sync (Future - P07)

**Future Enhancement:**
- Multi-agent policy synchronization via P07 event bus
- Distributed manifest caching
- Policy audit federation across agents
- See ADR-0089 Phase 3 for full specification

---

## Observability & Monitoring

### Key Metrics

**PEM Decision Metrics:**
```
k0_pem_decisions_total{action="ALLOW"}
k0_pem_decisions_total{action="DENY"}
k0_pem_decisions_total{action="REDACT"}
k0_pem_decision_latency_ms (histogram)
k0_pem_manifest_mismatches_total
```

**Command Execution Metrics:**
```
k0_commands_submitted_total
k0_commands_successful_total
k0_commands_failed_total
k0_command_latency_ms (histogram)
```

**Policy Audit Events:**
```json
{
  "timestamp": "2025-01-20T10:30:45Z",
  "event": "POLICY_DECISION",
  "command_id": "cmd-001",
  "decision_id": "pem-xyz-123",
  "action": "ALLOW",
  "obligations": ["kernel.audit.log"],
  "latency_ms": 15,
  "trace_id": "xyz-123-abc"
}
```

### Grafana Dashboards

- **K0 Kernel Overview:** PEM decisions, command latency, manifest validation status
- **Policy Audit:** Decision distribution (ALLOW/DENY/REDACT), obligation types
- **Infrastructure:** SQLite WAL size, Docker memory/CPU, network I/O

Access: `http://localhost:3000` (admin / admin by default)

### Alerts (via AlertManager)

- **Manifest Fingerprint Mismatch Rate** > 5/min (severity: warning)
- **Policy Decision Latency** p99 > 100ms (severity: warning)
- **K0 Kernel Down** (severity: critical)

---

## Performance Budgets

| Metric | Budget | Notes |
|--------|--------|-------|
| Policy Decision Latency (P95) | 50ms | Manifest cached, single manifest lookup |
| Command Submit E2E | 100ms | Including gate + PEM + redaction + WAL |
| Manifest Validation (on start) | <1s | SHA-256 fingerprint + JSON parsing |
| Database Query (WAL audit insert) | 10ms | Single row insert, WAL mode |

**Performance Tuning Tips:**
1. Enable `K0_PEM_DECISION_CACHE_TTL_MS=5000` for repeated decisions
2. Increase Docker memory to 2GB for SQLite WAL optimization
3. Monitor `k0_pem_decision_latency_ms` in Grafana to detect regression

---

## Additional Resources

- **Policy Contract:** `../../k0/contracts/policy/bridge_policy.yml`
- **Architecture:** `../../docs/whiteboard.md` (K0 kernel architecture, sections 3-4)
- **ADR-0089:** `../../docs/architecture/decisions/0089-k0-bridge-policy-enforcement.md`
- **Test Reference:** `../../tests/scripts/test_k0_bootstrap_harness.py`
- **PEM Implementation:** `../../k0/policy/pep_syscall.py`

---

## Support

For deployment issues:
1. Check **Troubleshooting** section above
2. Review logs: `.\k0.ps1 logs -Service k0-kernel`
3. Verify prerequisites met (Docker, Python, PowerShell)
4. Check GitHub issues: https://github.com/familyos/familyos/issues
