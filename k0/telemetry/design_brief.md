# Issue 8.1.1 Design Brief: SLO Dashboards & Preview Stack

> **Issue:** Milestone 8 Epic 8.1 Issue 8.1.1
> **Date:** 2025-10-01
> **Status:** In Progress
> **Owner:** Observability Team

---

## Context

Rebuild telemetry infrastructure after Milestone 8 reset, delivering OS-grade Grafana dashboards and Prometheus alerts that match the visual polish and functional depth of macOS Activity Monitor and Windows Reliability Monitor.

### Architecture Alignment
- **Diagrams ingested:**
  - `project_architecture_part2.mmd` (alias: `d2_inputs_perception`) - ID: 9a83e24c-7141-4fa3-bf21-98fa13f50009
  - `project_architecture_part4.mmd` (alias: `d4_ops_observability`) - ID: 59af66b9-7c82-4780-8e34-eeadc3a903f0
- **KG relationships:** Metrics exporter → receipts store, bus workers → outbox, ports → UoW
- **Key nodes:** `k0/obs/metrics.py`, `k0/storage/*`, `k0/bus/core.py`, `k0/ports/*`

### Guardrails (from instructions)
1. **Architecture Governance:** Memory-first, contract-led, event discipline, observability mandatory
2. **Service Design:** Reuse existing event bus, policy hooks, cognitive_trace_id propagation
3. **Production Policy:** Zero simulation code, real components only, deterministic builds
4. **Documentation:** README updates, runbook authoring, MCP memory traceability

---

## Design Decisions

### 1. Telemetry Module Structure
```
k0/telemetry/
  __init__.py              # Package entry, version
  render.py                # CLI entrypoint (python -m k0.telemetry.render)
  metrics_inventory.md     # Canonical metrics catalog
  design_brief.md          # This file
  mixins/                  # Jsonnet source
    _config.libsonnet      # Shared config/variables
    slo_dashboards.libsonnet  # Dashboard definitions
    alert_rules.libsonnet  # Prometheus rules
  generated/               # Rendered artifacts (gitignored deterministic outputs)
    dashboards/
      kernel_overview.json
      command_latency.json
      query_latency.json
      sse_health.json
      replay_throughput.json
    rules/
      slo_alerts.yaml
  preview/                 # Local dev stack
    docker-compose.yaml    # Grafana + Prometheus
    prometheus.yml         # Scrape config
    grafana/
      provisioning/
        datasources/
          prometheus.yaml
        dashboards/
          dashboards.yaml
```

### 2. Jsonnet Tooling Choice
- **Decision:** Use `_gojsonnet` Python binding for cross-platform compatibility
- **Rationale:**
  - Pure-Python alternatives (e.g., `pyjsonnet`) lack active maintenance
  - `_gojsonnet` provides Windows/Linux/macOS compatibility via go-jsonnet bindings
  - Fallback: Bundle `jsonnet` CLI binary for systems without CGo support
- **Dependency:** Add `gojsonnet>=0.20.0` to `requirements.txt`

### 3. Visual Design Standards
- **Color Palette:** Inspired by macOS Big Sur system monitors
  - Success/Healthy: `#34C759` (green)
  - Warning: `#FF9F0A` (orange)
  - Critical: `#FF3B30` (red)
  - Info/Background: `#1C1C1E` (dark) / `#F2F2F7` (light)
- **Typography:** Grafana default (Inter font), 12pt base, 16pt headers
- **Panel Layout:**
  - Top row: High-level SLOs (availability, p95 latencies)
  - Middle rows: Subsystem drill-downs (UoW, Outbox, SSE)
  - Bottom row: Resource saturation (connections, backlog, WAL lag)
- **Accessibility:** WCAG AA contrast ratios (4.5:1 text, 3:1 UI components)

### 4. SLO Definitions
| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Command latency (p95) | < 100ms | > 150ms (warning), > 250ms (critical) |
| Query latency (p95) | < 50ms | > 75ms (warning), > 150ms (critical) |
| API availability | > 99.9% | < 99.5% (warning), < 99.0% (critical) |
| Replay throughput | > 1000 evt/s | < 500 evt/s (warning), < 100 evt/s (critical) |
| WAL lag | < 60s | > 120s (warning), > 300s (critical) |
| Outbox backlog | < 10k | > 50k (warning), > 100k (critical) |

### 5. Integration Points
- **Metrics Source:** Existing `/metrics` endpoint (k0/obs/metrics.py)
- **Scrape Config:** Prometheus scrapes the kernel every 15s via `http://host.docker.internal:8080/metrics` (preview stack injects the host-gateway alias) and retains `http://k0-kernel:8080/metrics` for the container bundle path; keep `K0_SERVER_PORT=8080` when running locally.
- **Dashboard Variables:**
  - `$tenant` - Filter by tenant_id
  - `$device` - Filter by device_id
  - `$interval` - Aggregation window (default: 5m)
  - `$percentile` - Latency percentile (default: 95)
- **Recording Rules:** Pre-aggregate high-cardinality metrics (per-tenant SLOs)

---

## Implementation Plan

### Phase 1: Jsonnet Mixins (Current)
1. Create `_config.libsonnet` with variable definitions
2. Implement `slo_dashboards.libsonnet` with 5 core dashboards
3. Implement `alert_rules.libsonnet` with SLO alerts
4. Add rendering logic in `render.py`

### Phase 2: Preview Stack
1. Docker Compose with Grafana 10.x + Prometheus 2.x
2. Provisioning configs for datasource + dashboards
3. Windows PowerShell and Linux shell scripts
4. Health check and teardown automation

### Phase 3: Validation
1. Ward suites for render CLI (smoke test, schema validation)
2. Manual QA with synthetic metrics
3. Screenshot capture for documentation
4. Linting (`jsonnet fmt`, `promtool check rules`)

### Phase 4: Documentation
1. Runbook: `docs/development/runbooks/slo-dashboard.md`
2. Update: `docs/development/runbooks/README.md`
3. Update: `k0/README.md` observability section
4. MCP memory entry with traceability links

---

## Open Questions
1. **Jsonnet library dependencies:** Should we vendor Grafonnet (grafana-jsonnet-lib)?
   - **Decision pending:** Evaluate bundle size vs maintenance overhead
2. **Multi-tenant filtering:** Do we need tenant-specific dashboard instances?
   - **Decision pending:** Start with single dashboard + tenant variable, revisit if needed
3. **Windows path handling:** Does docker-compose volume mount work with backslashes?
   - **Mitigation:** Use forward slashes in compose file, test on Windows

---

## Success Criteria
- [ ] Dashboards render deterministically from CLI
- [ ] Preview stack launches on Windows PowerShell and Linux
- [ ] Ward tests pass in CI
- [ ] Visual polish approved by Ops/Product stakeholders
- [ ] Documentation complete with runbooks + memory entry

---

## References
- Metrics inventory: `k0/telemetry/metrics_inventory.md`
- Architecture diagrams: Ingested via MCP (IDs above)
- Instructions: `.github/instructions/architecture-governance.instructions.md`, `service-design.instructions.md`
- Plan: `k0/plan.md` Milestone 8 Epic 8.1 Issue 8.1.1
