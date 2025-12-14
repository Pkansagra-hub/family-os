# K0 Telemetry Module

> **Status:** ✅ Complete (Issue 8.1.1)
> **Owner:** Observability Team
> **Version:** 0.1.0

---

## Overview

The K0 telemetry module provides production-ready SLO dashboards, Prometheus alert rules, and a local preview stack for the K0 kernel. Dashboards are designed to match the visual polish and functional depth of macOS Activity Monitor and Windows Reliability Monitor.

**Key Features:**
- 5 Grafana dashboards covering kernel overview, command/query latency, SSE health, and replay throughput
- 18 Prometheus alert rules (9 SLO families × warning/critical pairs) including topology failover coverage
- Deterministic rendering with checksum verification
- Docker Compose preview stack for local development
- Comprehensive Ward test suite

---

## Quick Start

### Render Dashboards and Alerts
```powershell
# Windows
python -m k0.telemetry.render --verbose

# Verify checksums
python -m k0.telemetry.render --verify
```

```bash
# Linux/macOS
python -m k0.telemetry.render --verbose

# Verify checksums
python -m k0.telemetry.render --verify
```

### Start Preview Stack
```powershell
# Windows
cd k0\telemetry\preview
.\start-preview.ps1
```

```bash
# Linux/macOS
cd k0/telemetry/preview
./start-preview.sh
```

**Access:**
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

**Prerequisites:**
- Docker Desktop running
- K0 kernel exposing `/metrics` on port `8080`
  - When you run the kernel locally on your host, the preview stack reaches it via `http://host.docker.internal:8080/metrics` (the compose file pins this alias to the host gateway).
  - When you run the container bundle, the in-cluster address `http://k0-kernel:8080/metrics` remains available.

### Stop Preview Stack
```bash
cd k0/telemetry/preview
docker-compose down
```

---

## Module Structure

```
k0/telemetry/
  __init__.py                  # Package entry point
  render.py                    # CLI for rendering dashboards and rules
  design_brief.md              # Design decisions and architecture alignment
  metrics_inventory.md         # Canonical metrics catalog
  mixins/                      # Dashboard and alert builders
    __init__.py
    _config.py                 # Shared config (SLO targets, thresholds, colors)
    slo_dashboards.py          # Dashboard builders (Python)
    alert_rules.py             # Alert rule builder (Python)
  slo_definitions.yaml         # SLO definitions (source of truth)
  generated/                   # Rendered artifacts (SINGLE SOURCE OF TRUTH)
    dashboards/
      kernel_overview.json
      command_latency.json
      query_latency.json
      sse_health.json
      replay_throughput.json
    rules/
      slo_alerts.yaml
  preview/                     # Local dev stack
    docker-compose.yaml
    prometheus.yml
    start-preview.ps1          # Windows helper script
    start-preview.sh           # Linux/macOS helper script
    grafana/
      provisioning/
        datasources/
          prometheus.yaml
        dashboards/
          dashboards.yaml
```

### Artifact Lifecycle

**Single Source of Truth Pattern:**

1. **Source**: `k0/telemetry/slo_definitions.yaml` (SLO definitions)
2. **Rendering**: `k0/telemetry/render.py --verbose` generates artifacts to `k0/telemetry/generated/`
3. **Deployment**: `k0/deploy/k0.ps1 up` automatically syncs `k0/telemetry/generated/* → k0/deploy/generated/`
4. **Docker Compose**: Mounts `k0/deploy/generated/` for prometheus, grafana, etc.

**Key Point**: Never edit `k0/deploy/generated/` directly. All changes flow through:
```
SLO definitions → render.py → k0/telemetry/generated/ → deploy sync → k0/deploy/generated/
```

---

## Dashboards

### 1. Kernel Overview (`k0-kernel-overview`)
High-level health snapshot with 6 SLO stat panels (API availability, command/query latency, replay throughput, WAL lag, outbox backlog) plus time series for HTTP traffic, errors, UoW commits, and connections.

### 2. Command Latency (`k0-command-latency`)
Deep dive into command path performance: submit latency percentiles, UoW commit latency distribution, WAL fsync latency, commit/rollback rates.

### 3. Query Latency (`k0-query-latency`)
Query path performance: execute latency percentiles, query rate by status.

### 4. SSE Health (`k0-sse-health`)
SSE subscription health: active subscriptions, subscribe/disconnect rate, bus dispatch latency.

### 5. Replay & Snapshots (`k0-replay-throughput`)
WAL replay and snapshot freshness: replay throughput, snapshot age, outbox state breakdown, apply rate by outcome.

---

## Alert Rules

All alerts defined in `generated/rules/slo_alerts.yaml`:

| Alert | SLO | Warning | Critical |
|-------|-----|---------|----------|
| K0ApiAvailability | > 99.9% | < 99.5% | < 99.0% |
| K0CommandLatency | < 100ms (p95) | > 150ms | > 250ms |
| K0QueryLatency | < 50ms (p95) | > 75ms | > 150ms |
| K0WalLag | < 60s | > 120s | > 300s |
| K0WalReplicaLag | < 10s standby lag | > 20s | > 30s |
| K0OutboxBacklog | < 10k | > 50k | > 100k |
| K0ReplayThroughput | > 1000 evt/s | < 500 evt/s | < 100 evt/s |
| K0SchedulerQuorum | ≥ 3 members | < 3 | < 2 |
| K0ZoneHealth | All zones healthy (ratio = 1) | < 1.0 | ≤ 0 |

Each alert includes a runbook URL pointing to `docs/development/runbooks/alerts/*.md` or, for cluster topology incidents, the `control-plane-failover.md` and `data-plane-promotion.md` Day-2 runbooks in the same directory.

---

## Dashboard Variables

All dashboards support filtering:
- **`$tenant`** — Multi-select tenant filter
- **`$device`** — Multi-select device filter
- **`$interval`** — Aggregation window (1m, 5m, 15m, 30m, 1h, 6h, 12h, 1d)
- **`$percentile`** — Latency percentile (p50, p95, p99)

---

## Metrics Inventory

See `metrics_inventory.md` for complete list. Key metrics:
- **Latency:** `k0_kernel_http_request_duration_seconds`, `k0_uow_commit_seconds`, `k0_bus_dispatch_latency`
- **Availability:** `k0_kernel_http_requests_total`, `k0_uow_commit_total`, `k0_outbox_apply_total`
- **Saturation:** `k0_kernel_active_connections`, `k0_outbox_pending_total`, `k0_sse_active_subscriptions`
- **Errors:** Derived from counters with `status=~"5.."` or `outcome="failure"` filters

---

## Testing

### Run Ward Tests
```bash
python -m ward test --path tests/telemetry
```

**Coverage:**
- Dashboard structure validation
- Alert rule YAML validation
- Checksum verification
- Deterministic rendering
- PromQL syntax validation
- Runbook link integrity (dashboards + Alertmanager metadata)

**Current Status:** ✅ 14/14 tests passing (100%)

---

## Maintenance

### Updating SLO Targets
1. Edit `k0/telemetry/mixins/_config.py`:
   - Update `SLO_TARGETS` dict
   - Update `ALERT_THRESHOLDS` dict
2. Re-render: `python -m k0.telemetry.render --verbose`
3. Verify checksums: `python -m k0.telemetry.render --verify`
4. Commit changes
5. Update runbooks in `docs/development/runbooks/`

### Adding New Dashboards
1. Add builder function in `mixins/slo_dashboards.py`
2. Update `render.py` to include new dashboard
3. Add Ward test in `tests/telemetry/test_telemetry_render.py`
4. Update this README with dashboard description

### Adding New Alerts
1. Add rule in `mixins/alert_rules.py`
2. Create runbook in `docs/development/runbooks/alerts/`
3. Update `docs/development/runbooks/README.md`
4. Add Ward test validating alert structure

---

## Documentation

- **Design Brief:** `k0/telemetry/design_brief.md`
- **Metrics Inventory:** `k0/telemetry/metrics_inventory.md`
- **SLO Dashboard Runbook:** `docs/development/runbooks/slo-dashboard.md`
- **Alert Runbooks:** `docs/development/runbooks/alerts/*.md`
- **Architecture Diagrams:** `docs/development/mmd-diagram-usage.md`
- **Plan:** `k0/plan.md` Milestone 8 Epic 8.1 Issue 8.1.1

---

## Color Palette (macOS Inspired)

- **Success:** `#34C759` (green)
- **Warning:** `#FF9F0A` (orange)
- **Critical:** `#FF3B30` (red)
- **Info:** `#007AFF` (blue)
- **Background Dark:** `#1C1C1E`
- **Background Light:** `#F2F2F7`

Accessibility: WCAG AA contrast ratios maintained (4.5:1 text, 3:1 UI components).

---

## Version History

- **0.1.0** (2025-10-01): Initial release
  - 5 dashboards
  - 12 alert rules (6 SLOs × 2 severities)
  - Ward test suite (14 tests, 100% passing)
  - Docker Compose preview stack
  - Comprehensive documentation

---

## License

Part of the MemoryOS K0 kernel project. See root LICENSE file for terms.
