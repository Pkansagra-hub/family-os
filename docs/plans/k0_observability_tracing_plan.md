# K0 Kernel Observability & Tracing Plan

**Status:** Draft for review  \
**Owner:** Observability Working Group  \
**Last Updated:** 2025-10-31  \
**Scope:** End-to-end observability (metrics, traces, logs, dashboards, alerting) for the K0 Kernel across all pipelines (P01–P20), storage primitives, and bridge interfaces.

---

## 1. Objectives

1. Establish full-signal coverage (metrics, traces, logs) for every K0 component and pipeline stage with cognitive_trace_id propagation.  
2. Provide dashboards and alert rules that expose health, capacity, and policy conformance for on-device operations (no cloud dependencies).  
3. Institutionalize the 5-Gate workflow for observability changes (ADRs → Contracts → Implementation → Tests → Memory/Diagrams).

---

## 2. Gate Alignment Checklist

### Gate 1 — ADR Discovery & Validation

- **Action:** Author ADR `ADR-00XX: K0 Observability Architecture` covering signal taxonomy, privacy bands, retention, and on-device deployment constraints.
- **Inputs:** Current `/obs.emit` implementation @k0/ports/observe.py, metrics exporter @k0/obs/metrics.py, QoS and WAL ADRs for dependency references.
- **Exit Criteria:** ADR accepted with decisions on: signal types, sampling strategies, storage (Prometheus TSDB, WAL snapshots), redaction obligations, dashboard SLAs.

### Gate 2 — Contract Discovery & Validation

- **Contracts Required:**
  - `contracts/k0/observability/metrics_payload.yml` (snapshot schema).
  - `contracts/k0/observability/log_batch.yml` (structured logs + obligations).
  - `contracts/k0/observability/trace_batch.yml` (OTLP envelope with cognitive_trace_id).
  - `contracts/k0/observability/dashboard_catalog.yml` (dashboard metadata + ownership).
- **Actions:** Implement schema validation in CI, bump contract versions, wire contracts into `/obs.emit` request validation.

### Gate 3 — Implementation (Contract-Compliant)

- Instrument all pipelines and primitives; ensure ObservabilityEmitter integration; finish exporter manager and K1 bridge client; add privacy-band aware redaction before storage.
- Reference ADR IDs in code comments and enforce cognitive_trace_id propagation through UnitOfWork and SSE paths.

### Gate 4 — Tests

- Add integration suites for `/obs.emit`, metrics snapshotting, and dashboard data sources.
- Create load tests for observability hot paths (ensure P95 latency budgets).
- Build trace walk tests validating end-to-end spans across command → pipelines → bridge.

### Gate 5 — Memory & Diagrams

- Update docs/architecture diagrams for observability flows.
- Record milestone completion in FamilyOS memory with test evidence and performance metrics.
- Confirm dashboards exported (JSON) and versioned in repo.

---

## 3. Component Telemetry Coverage Map

| Component / Pipeline | Metrics | Traces | Logs | Dashboard Views | Notes |
| --- | --- | --- | --- | --- | --- |
| HTTP Ports (`/command.submit`, `/query.recall`, `/obs.emit`, etc.) | Request rate, latency, error codes | Span per request with cognitive_trace_id | Structured access logs | Port Health | Ensure privacy band tagging |
| Minimal Gate & Schema Registry | Validation success/fail, schema cache hits | Span linking request → schema lookup | Policy violations | Admission Control | Highlight invalid envelope trends |
| PEP & Band Enforcement | Decision counters, latency histogram | Span attribute `pep.decision` | Deny reason logs | Policy Enforcement | Must redact labels before storage |
| QoS Scheduler | Token bucket depth, throttle events | Span `qos.action` events | Backpressure logs | QoS Overview | Validate budgets vs ADR |
| UnitOfWork Spine | Commit latency, retries | Span covering WAL append + on_commit hooks | Error stack logs | Transaction Spine | Attach offsets to spans |
| WAL + Snapshots | Append throughput, replay lag, snapshot duration | Span for snapshot creation/replay | Recovery logs | WAL Ops | Derive from `ForwardedMetricsBuffer` |
| Receipts Service | Receipts issued, verification failures | Span linking command trace → receipt | Validation logs | Receipts | Include signature failure alerts |
| Bus Dispatcher & Middleware | Fan-out latency per sink | Span per sink dispatch | Middleware error logs | Bus Health | Track DLQ pushes |
| SSE Server | Subscriber count, ack latency | Span `sse.deliver` | Cursor anomalies | SSE Ops | Visualize per privacy band |
| Outbox & DLQ | Queue depth, processing latency | Span per batch | DLQ insert logs | Async Execution | Alert on DLQ growth |
| Pipelines P01–P20 | Custom KPI metrics per pipeline | Spans covering each stage | Pipeline-specific logs | Pipeline Health Matrix | Use consistent naming `k0.pXX.*` |
| Storage Primitives (`st_*`) | Operation latency, error counts | Span `storage.call` | Error logs | Storage Health | Show top error types |

---

## 4. Milestone → Epics → Issues

### Milestone M1 — K0 Observability Readiness

#### Epic E1 — Observability Governance Foundations

1. **Issue E1.1:** Author ADR `ADR-00XX` (see Gate 1).
2. **Issue E1.2:** Produce observability contracts + validation harness (Gate 2).
3. **Issue E1.3:** Define naming conventions, privacy band policies, retention schedules (document + lint).
4. **Issue E1.4:** Integrate 5-Gate checks into CI for observability-related PRs.

#### Epic E2 — Kernel Telemetry Instrumentation

1. **Issue E2.1:** Harden `/obs.emit` handling with schema validation, DLQ, structured logs @k0/ports/observe.py.
2. **Issue E2.2:** Complete `ObservabilityEmitter` wiring in `MetricsExporter` including thread-safe flush and Prometheus exposition @k0/obs/metrics.py.
3. **Issue E2.3:** Instrument pipelines P01–P20 with metric/tracing decorators; ensure UnitOfWork spans propagate cognitive_trace_id.
4. **Issue E2.4:** Build WAL-backed persistence for `ForwardedMetricsBuffer` to survive process restarts.
5. **Issue E2.5:** Add Prometheus endpoint `/metrics` with auth and latency budgets (P95 <120 ms).

#### Epic E3 — K1↔K0 Observability Bridge Completion

1. **Issue E3.1:** Implement batching/retry client `K0ObservabilityClient` with health checks @k1/l5_infrastructure/observability/k0_client.py.
2. **Issue E3.2:** Finish metric helper functions to forward data via bridge @k1/l5_infrastructure/observability/metrics.py.
3. **Issue E3.3:** Implement `MetricsExporterManager` multi-sink routing @k1/l5_infrastructure/extensions/metrics_exporter.py.
4. **Issue E3.4:** Create integration tests covering batching, retries, error surfacing (<5 ms fast-lane budget).

#### Epic E4 — Dashboards, Alerting & E2E Validation

1. **Issue E4.1:** Inventory existing dashboards (`k0/ deploy/…`) and align metrics taxonomy; version dashboards in repo.
2. **Issue E4.2:** Build new dashboards: *Kernel Core Health*, *Pipelines Matrix*, *Policy & Privacy*, *Storage Ops*, *Async & DLQ*.
3. **Issue E4.3:** Define alert rules for saturation, policy violations, QoS failures, WAL lag; integrate with on-device alerting.
4. **Issue E4.4:** Conduct observability game day (failure injection + runbooks) and capture remediation steps.
5. **Issue E4.5:** Gate 5 deliverables: documentation updates, diagrams, memory entry with performance evidence.

---

## 5. Traceability Strategy

1. **Trace Root:** Each inbound command/query attaches `cognitive_trace_id`; `/obs.emit` ensures fallback generation.
2. **Span Hierarchy:**
   - `k0.port.<endpoint>` → `k0.minimal_gate` → `k0.pep` → `k0.uow` → pipeline spans (`k0.pipeline.pXX.stage`) → `k0.bus.dispatch` → `k0.sse.delivery`/`k0.outbox`.
3. **Context Propagation:** Implement tracer middleware retrieving headers, storing per-request context, and passing through UnitOfWork events and ObservabilityEmitter payloads.
4. **Span Attributes:** Include `privacy_band`, `space`, `policy_version`, `qos_band`, and `unit_of_work_id` for filtering in dashboards.
5. **Error Capture:** Enrich spans with `status_code`, `exception.type`, `wal_offset` for postmortem analysis.
6. **Trace Export:** Batch via K1 bridge to K0; store in on-device Tempo-compatible backend configured in ADR.

---

## 6. Dashboard & Alerting Blueprint

### Dashboards

1. **Kernel Core Health:** Port latency, QoS budgets, PEP decisions, policy breaches.
2. **Pipeline Execution Matrix:** Heatmap of pipelines P01–P20 across bands, latency percentiles, error rates.
3. **Storage & WAL Ops:** WAL append/replay, snapshot duration, storage primitive latencies.
4. **Async & DLQ Monitor:** Outbox backlog, DLQ growth, retry success rates.
5. **Privacy & Compliance:** Redaction counts, band distribution, obligation processing latency.
6. **Trace Explorer:** Top slow traces, waterfall of critical flows, correlated logs via cognitive_trace_id.

### Alert Rules

- **QoS Breach:** Token bucket depletion >90% for 5 minutes.
- **Policy Violations:** >5 denied requests per minute or any BLACK band breach (instant alert).
- **WAL Lag:** Replay lag >30 seconds or snapshot duration >2× baseline.
- **DLQ Growth:** DLQ length increasing for 10 minutes; escalate if >100 entries.
- **Trace Latency:** Tail latency >500 ms for `k0.pipeline.pXX` spans.
- **Observability Pipeline Failure:** `/obs.emit` error rate >1% or exporter flush failures.

---

## 7. Verification & Acceptance

- **Integration Tests:**
  - `/obs.emit` end-to-end validation with contract fixtures and DLQ assertions.
  - Pipeline instrumentation tests ensuring metrics, traces, logs emitted per contract.
  - Dashboard data-source tests (e.g., Prometheus query snapshots) executed via CI.
- **Performance Tests:** Synthetic load verifying P95 latency budgets (Ports <150 ms, Observability flush <120 ms).
- **Game Day:** Scenario playbooks (policy misconfig, WAL congestion, pipeline failure) verifying dashboards + alerts.
- **Documentation:** Update diagrams, ADR references, and ops runbooks.
- **Sign-off:** Observability Working Group review + K0 kernel owner approval.

---

## 8. Dependencies & Risks

- **Dependencies:** K1 bridge readiness, Prometheus/Tempo local services, existing QoS/WAL instrumentation.
- **Risks:** Missing ADR slowing Gate 1, on-device resource constraints impacting telemetry storage, privacy-band redaction gaps.
- **Mitigations:** Prioritize ADR + contract work, load-test storage footprint, enforce policy-aware filtering before persistence.

---

## 9. Next Actions

1. Kick off ADR drafting (schedule review next sprint).
2. Stand up observability contract schemas and wire them into `/obs.emit`.
3. Begin instrumentation rollout with P01–P05 pipelines as pilot; measure dashboard ingestion.
4. Prepare dashboard skeletons and alert definitions for review alongside ADR.
