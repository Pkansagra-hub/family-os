# Grafana Dashboards

**Purpose:** Grafana dashboard definitions for K1 observability
**Location:** `k1/l5_infrastructure/observability/dashboards/`
**Performance:** N/A (static definitions)

## Primary ADRs

- **ADR-0029** — Prometheus Metrics (dashboard integration)
- **ADR-0002d** — Actor Fabric Observability (mailbox, router, supervisor dashboards)
- **ADR-0029e** — Alerting (Turn Overview, Component Health, Infrastructure, Incident Response)

## Dashboard Catalog (7 dashboards)

### 1. K1 Overview Dashboard
**File:** `k1_overview.json`
**Purpose:** High-level K1 metrics across all layers

**Panels:**
- Turn metrics: TTFT (P50/P95/P99), E2E latency, error rate
- Layer latencies: Layer 1-5 latency breakdown
- Agent lifecycle: Hire count, active agents, crash count
- Tool execution: Tool call count, success rate, latency
- Resource usage: CPU, memory, KV cache hit rate

**Alerts:**
- TTFT >157ms (5% SLO buffer)
- E2E latency >2100ms
- Error rate >1%

---

### 2. Layer 1 Dashboard
**File:** `layer1_input.json`
**Purpose:** Layer 1 input processing metrics

**Panels:**
- TTFT: P50/P95/P99 latency
- VAD latency: Voice activity detection
- Intent classification: T1/T2/T3 routing latency
- ASR metrics: Transcription accuracy, latency
- Input rate: Requests per second

---

### 3. Layer 2 Dashboard
**File:** `layer2_orchestration.json`
**Purpose:** Layer 2 orchestration metrics

**Panels:**
- Planning latency: 4-stage pipeline (Sketch/Expand/Validate/Commit)
- Orchestration latency: 3-phase coordination (Negotiation/Selection/Execution)
- Protocol validation: MPST validation latency
- Agent selection: Hiring score, selection time

---

### 4. Layer 3 Dashboard
**File:** `layer3_execution.json`
**Purpose:** Layer 3 execution metrics

**Panels:**
- Agent lifecycle: FSM transitions, state durations
- Model Hub inference: Inference latency, model selection
- Tool execution: Tool call count, success rate, latency
- Capability checks: Capability validation latency

---

### 5. Layer 4 Dashboard
**File:** `layer4_runtime.json`
**Purpose:** Layer 4 runtime metrics

**Panels:**
- SessionState size: Bytes, growth rate
- Mailbox depth: Queue depth, admission control
- Learning cycle: Feedback signals, drift detection
- KV cache: Hit rate, eviction rate, compression ratio

---

### 6. Layer 5 Dashboard
**File:** `layer5_infrastructure.json`
**Purpose:** Layer 5 infrastructure metrics

**Panels:**
- Event bus: Event rate, delivery latency, backpressure
- Thermal: Device temperature, placement decisions, emergency jumps
- Circuit breaker: State (CLOSED/OPEN/HALF_OPEN), failure rate
- K0 Bridge: Command latency, query latency, batch efficiency

---

### 7. Actor Fabric Dashboard
**File:** `actor_fabric.json`
**Purpose:** Actor model observability (ADR-0002d)

**Panels:**
- Mailbox health: Queue depth, admission rejections, overflow events
- Router: Routing latency, admission control, backpressure
- Supervisor: Restart count, crash rate, recovery time
- Message flow: Message rate, processing latency, delivery failures

---

## Alert Routing (ADR-0029e)

### Critical Alerts (PagerDuty, 24/7 on-call)
- TTFT >157ms sustained >5min
- E2E latency >2100ms sustained >5min
- Error rate >1% sustained >5min
- Circuit breaker stuck OPEN >5min
- Thermal EMERGENCY state

### Warning Alerts (Slack #k1-alerts)
- TTFT >150ms (within SLO but approaching limit)
- E2E latency >2000ms
- Error rate >0.5%
- Backpressure events >10/min
- Thermal CRITICAL state

### Info Alerts (Grafana dashboard annotations)
- Thermal HOT state
- Circuit breaker transitions (CLOSED→OPEN, OPEN→HALF_OPEN)
- Config hot-reload events

---

## Dashboard Deployment

### Prerequisites
- Prometheus server running (localhost:9090)
- Grafana server running (localhost:3000)
- K1 metrics exporter pushing to Prometheus

### Installation
1. Import dashboard JSON files into Grafana
2. Configure Prometheus data source in Grafana
3. Set up alert channels (PagerDuty, Slack)
4. Configure alert routing rules

### Maintenance
- Dashboard definitions stored in Git (version control)
- Auto-sync dashboards from Git to Grafana (Grafana provisioning)
- Review dashboards quarterly (add/remove panels as needed)

---

## Dashboard Files

```
dashboards/
├── README.md (this file)
├── k1_overview.json (K1 high-level metrics)
├── layer1_input.json (Layer 1 metrics)
├── layer2_orchestration.json (Layer 2 metrics)
├── layer3_execution.json (Layer 3 metrics)
├── layer4_runtime.json (Layer 4 metrics)
├── layer5_infrastructure.json (Layer 5 metrics)
└── actor_fabric.json (Actor model metrics)
```

---

**Total Dashboards:** 7 dashboards
**Total Panels:** ~50 panels (7-10 panels per dashboard)
**Refresh Rate:** 10s (matches Prometheus scrape interval)
