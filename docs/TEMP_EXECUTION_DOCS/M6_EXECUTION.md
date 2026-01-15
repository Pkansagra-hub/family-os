# P03 Milestone 6 Execution Document

> **Milestone**: M6 — Ops readiness: observability, DLQ, security/privacy, performance
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M5 COMPLETED (R6-R8 finalize: stage → commit → emit)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD (after M5 completion)

---

## Document Overview

This document provides the execution plan for Milestone 6 (M6), which implements operational readiness for P03: observability (metrics/tracing/logging), DLQ/retries/circuit breakers, security/privacy enforcement, and performance/QoS integration.

**M6 Focus**: Production-grade operational infrastructure for P03 consolidation pipeline.

---

## Part A: Context Foundation (BEFORE YOU START)

### A.0 M0–M5 Outputs — EXISTING INFRASTRUCTURE AUDIT

> **CRITICAL**: M6 builds on completed infrastructure from M0-M5.
> This section documents what ALREADY EXISTS to avoid duplication.

#### M0 Deliverables (Contracts & ADRs) — ALL COMPLETE

| Artifact | Path | Status |
|----------|------|--------|
| Pipeline ADR | `docs/architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md` | EXISTS |
| State Machine ADR | `docs/architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md` | EXISTS |
| Capability ADR | `docs/architecture/decisions-K0/pipelines/k010.9-capability-based-security.md` | EXISTS |
| Pipeline Contract | `k0/contracts/pipelines/p03_consolidation.v1.yaml` | EXISTS |
| 17 Module Contracts | `k0/contracts/modules/consolidation.*.v1.yaml` | EXISTS |
| Capability Contract | `k0/contracts/capabilities/consolidation.v1.yaml` | EXISTS |
| 8 Event Schemas | `k0/contracts/schemas/p03_*.json` | EXISTS |
| Config Schema | `k0/contracts/jsonschema/p03.config.schema.json` | EXISTS |

#### M1 Deliverables (Pipeline Skeleton) — Core Files

| File | Purpose | M6 Usage |
|------|---------|----------|
| `context.py` | P03CycleContext | Cycle context for observability |
| `event_state.py` | P03EventState + enums | Decision tracking for metrics |
| `phase_outputs.py` | P03PhaseOutputs | Phase results for metrics |
| `staged_writes.py` | P03StagedWrites | Write tracking for DLQ |
| `observability.py` | P03ObservabilityContext | **EXTEND** with M6 observability |
| `serializer.py` | P03EnvelopeSerializer | DLQ serialization |
| `envelope.py` | P03BatchEnvelope | Root container |
| `sequential_runner.py` | P03SequentialRunner | **EXTEND** with retry/circuit breaker |

#### M2 Deliverables (Storage + Audit + Learning) — 18 Migrations

| Migration | Table | M6 Usage |
|-----------|-------|----------|
| 0036 | st_consolidation_audit | Audit logging, RLS policies |
| 0037 | st_learning_queue | Gap metrics |
| 0040 | st_learned_weights | RLS policies |
| 0042 | st_feedback_quarantine | Quarantine detection |
| 0045 | st_dlq_p03_reconcile | DLQ error handling |

#### M3 Deliverables (DB ↔ Outbox ↔ Bus Wiring) — 9 Issues

| Component | M6 Usage |
|-----------|----------|
| R7TruthWriter | Circuit breaker integration |
| R8EventEmitter | Bus circuit breaker |
| OutboxPublisher | Retry/DLQ integration |
| GapEmitter | Gap metrics |

#### M4 Deliverables (R1-R4 Core Cognition) — 40 Issues

| Component | M6 Usage |
|-----------|----------|
| ImportanceScorer | R1 metrics |
| HebbianLearner | Hebbian metrics |
| EpisodicDBSCAN | R2 clustering metrics |
| DuplicateDetector | R3 dedup metrics |
| EntityDisambiguator | R4 entity metrics |

#### M5 Deliverables (R6-R8 Finalize) — Issues

| Component | M6 Usage |
|-----------|----------|
| R6Coordinator | R6 staging metrics |
| StagedWritesContainer | Write metrics |
| R7R8Coordinator | R7/R8 phase metrics |
| EventEmitter | Emission metrics |
| GapEmitter | Gap detection metrics |

#### K0 Core Infrastructure (Pre-existing)

| Component | Path | Purpose |
|-----------|------|---------|
| MetricsExporter | `k0/obs/metrics.py` | Prometheus metrics emission |
| TracerFactory | `k0/obs/tracing.py` | OpenTelemetry tracing |
| Structlog | `k0/obs/log.py` | Structured JSON logging |
| DLQStore | `k0/storage/dlq.py` | Dead letter queue storage |
| RetryScheduler | `k0/outbox/scheduler.py` | Retry scheduling |
| CircuitBreaker | `k0/resilience/circuit_breaker.py` | Circuit breaker base |
| QoSScheduler | `k0/qos/scheduler.py` | QoS token management |
| RLSEnforcer | `k0/policy/rls.py` | Row-level security |
| RetentionEnforcer | `k0/policy/retention_enforcer.py` | Retention policies |
| CryptoLayer | `k0/security/crypto.py` | Content fingerprinting |

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| §8 | Observability | [Dossier §8](../pipelines/P03_consolidation_dossier_v2.md#8-observability) | Metrics, tracing, logging |
| §8.1 | Cross-Space Leakage Detection | [Dossier §8.1](../pipelines/P03_consolidation_dossier_v2.md#81-cross-space-leakage-detection) | Security metrics |
| §8.2 | Metric Definitions | [Dossier §8.2](../pipelines/P03_consolidation_dossier_v2.md#82-metric-definitions) | All P03 metrics |
| §8.3 | Distributed Tracing | [Dossier §8.3](../pipelines/P03_consolidation_dossier_v2.md#83-distributed-tracing) | Span hierarchy |
| §8.4 | Structured Logging | [Dossier §8.4](../pipelines/P03_consolidation_dossier_v2.md#84-structured-logging) | Log schema |
| §8.5 | Dashboards | [Dossier §8.5](../pipelines/P03_consolidation_dossier_v2.md#85-dashboards) | Grafana dashboards |
| §8.6 | Alerting Rules | [Dossier §8.6](../pipelines/P03_consolidation_dossier_v2.md#86-alerting-rules) | Prometheus alerts |
| §13 | Error Handling & DLQ | [Dossier §13](../pipelines/P03_consolidation_dossier_v2.md#13-error-handling--dead-letter-queue) | DLQ, retries |
| §13.2 | Error Classification | [Dossier §13.2](../pipelines/P03_consolidation_dossier_v2.md#132-error-classification) | TRANSIENT/VALIDATION/LOGIC/FATAL |
| §13.5 | Retry Strategy | [Dossier §13.5](../pipelines/P03_consolidation_dossier_v2.md#135-retry-strategy) | Exponential backoff |
| §13.6 | Circuit Breaker | [Dossier §13.6](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breaker) | P08/Bus/FAISS breakers |
| §13.7 | Partial Failure Handling | [Dossier §13.7](../pipelines/P03_consolidation_dossier_v2.md#137-partial-failure-handling) | COMMIT_PARTIAL/ROLLBACK_ALL |
| §13.9 | Edge Case Handling | [Dossier §13.9](../pipelines/P03_consolidation_dossier_v2.md#139-edge-case-handling-matrix) | Edge case matrix |
| §14 | Security & Privacy | [Dossier §14](../pipelines/P03_consolidation_dossier_v2.md#14-security--privacy) | RLS, privacy bands |
| §14.2 | Privacy Band Enforcement | [Dossier §14.2](../pipelines/P03_consolidation_dossier_v2.md#142-privacy-band-enforcement) | GREEN/AMBER/RED |
| §14.7 | GDPR | [Dossier §14.7](../pipelines/P03_consolidation_dossier_v2.md#147-gdpr) | Erasure handling |
| §14.11 | Learning Data Isolation | [Dossier §14.11](../pipelines/P03_consolidation_dossier_v2.md#1411-learning-data-isolation) | RLS for learning tables |
| §15 | Performance Tuning | [Dossier §15](../pipelines/P03_consolidation_dossier_v2.md#15-performance-tuning) | QoS, batch sizing |
| §15.2 | K0 Scheduler Integration | [Dossier §15.2](../pipelines/P03_consolidation_dossier_v2.md#152-k0-scheduler-integration) | Token management |
| §15.3 | Performance Baselines | [Dossier §15.3](../pipelines/P03_consolidation_dossier_v2.md#153-performance-baselines) | Latency targets |
| Appendix G.5 | Metrics Per Phase | [Dossier Appendix G.5](../pipelines/P03_consolidation_dossier_v2.md#g5-phase-metrics) | Per-phase metrics |

### A.2 ADRs to Reference

| ADR | Path | Governs |
|-----|------|---------|
| K010 | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | P03 pipeline architecture |
| K010.1 | [k010.1-sleep-cycle-state-machine.md](../architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md) | R0-R8 state machine |
| K010.9 | [k010.9-capability-based-security.md](../architecture/decisions-K0/pipelines/k010.9-capability-based-security.md) | Capability model |
| K002 | [k002-idempotency-toctou-race-fix.md](../architecture/decisions-K0/k002-idempotency-toctou-race-fix.md) | Idempotency patterns |
| K004 | [k004-capability-mesh-architecture.md](../architecture/decisions-K0/k004-capability-mesh-architecture.md) | Capability model |

### A.3 Governance Sync Tool

| Tool | Command |
|------|---------|
| Sync Script | `python -m governance.k0.scripts.sync --report` |

**When To Run Governance Sync**:

- Before starting any Epic (capture baseline)
- After completing any Epic (verify no drift)
- Before marking M6 complete (final verification)

---

## Part B: What M6 ACTUALLY Needs To Do

### B.1 M6 Scope Definition

**M6 Goal**: Implement production-grade operational infrastructure for P03 consolidation pipeline.

**Epic 6.1 — Metrics/Tracing/Logging Implementation**:

- P03 metrics registry and exporter integration
- Cycle metrics, phase timing histograms
- Decision metrics, gap metrics, layer metrics
- Module performance metrics, shadow mode metrics
- Distributed tracing span hierarchy
- Structured logging schema
- Grafana dashboards and alerting rules

**Epic 6.2 — DLQ + Retries + Circuit Breakers**:

- Error classification and P03ErrorHandler
- DLQRecord and DLQStore integration
- Retry configuration with phase overrides
- Circuit breakers (P08, Bus, FAISS)
- Partial failure handling strategies
- Quarantine detection and management
- CLI commands for DLQ management

**Epic 6.3 — Security & Privacy Enforcement**:

- RLS policies for learning tables
- Cross-space isolation verification
- Privacy band enforcement
- Location privacy masking
- GDPR erasure handling
- Tombstone lifecycle management
- Security alerting rules

**Epic 6.4 — Performance + QoS**:

- K0 QoS scheduler integration
- Adaptive batch sizing
- Phase latency targets
- Throughput tracking
- Resource utilization metrics
- Performance baseline validation

### B.2 K0 Kernel Services — P03 INTEGRATES, NOT DUPLICATES

> **CRITICAL ARCHITECTURE PRINCIPLE**: K0 is the kernel. P03 is a pipeline.
> P03 integrates with K0 services — it does NOT recreate them.

#### K0 Kernel Services Used by P03 (Already Exist)

| K0 Service | Path | P03 Usage |
|------------|------|-----------|
| **Observability** | `k0/obs/` | |
| MetricsExporter | `k0/obs/metrics.py` | Register P03 metrics with K0 exporter |
| TracerFactory | `k0/obs/tracing.py` | Create spans using K0 tracer |
| Structlog | `k0/obs/log.py` | Log using K0 structured logging |
| **QoS & Scheduling** | `k0/qos/` | |
| Scheduler | `k0/qos/scheduler.py` | Acquire tokens before batch processing |
| QoSContext | `k0/qos/context.py` | Use fanout/top_k budgets |
| QoSMetrics | `k0/qos/metrics.py` | Record acquisition metrics |
| **Storage & DLQ** | `k0/storage/` | |
| DLQStore | `k0/storage/dlq.py` | Record failed envelopes |
| RetryScheduler | `k0/outbox/scheduler.py` | Phase-aware retry configuration |
| OutboxStore | `k0/storage/outbox.py` | Event staging |
| **Policy & Security** | `k0/policy/` | |
| PEP | `k0/policy/pep_syscall.py` | Policy evaluation |
| RLSEnforcer | `k0/policy/rls.py` | Row-level security |
| RetentionEnforcer | `k0/policy/retention_enforcer.py` | Retention policies |
| LocationPrivacy | `k0/policy/location_privacy.py` | Location masking |
| ACLEnforcer | `k0/policy/acl_enforcer.py` | Permission checks |
| **Security/Crypto** | `k0/security/` | |
| Crypto | `k0/security/crypto.py` | Content fingerprinting |

#### B.2.1 What M6 ACTUALLY Creates (Integration Code Only)

```text
k0/pipelines/p03/
├── ops/                            # P03 operational integration (thin wrappers)
│   ├── __init__.py
│   ├── metrics.py                  # P03 metric DEFINITIONS (registered with k0/obs/)
│   ├── spans.py                    # P03 span NAMES/hierarchy (uses k0/obs/tracing)
│   └── dashboards/                 # Grafana dashboard JSON (config, not code)
│       ├── p03_health.json
│       └── p03_gaps.json
├── resilience.py                   # P03ErrorHandler → uses k0/storage/dlq.py
└── config/
    └── alerts/                     # Prometheus alert rules (config, not code)
        └── p03_alerts.yaml

k0/migrations/versions/             # RLS policies via Alembic (SQL, not Python duplication)
├── 0046_rls_st_learned_weights.py
├── 0047_rls_st_consolidation_audit.py
├── 0048_rls_st_pruned_entities.py
└── 0049_rls_st_decay_feedback.py

tests/k0/pipelines/p03/
├── test_metrics_integration.py     # Verify P03 metrics appear in /metrics endpoint
├── test_dlq_integration.py         # Verify DLQStore integration
├── test_rls_isolation.py           # Verify RLS policies work
└── test_qos_integration.py         # Verify scheduler token acquisition
```

#### B.2.2 P03 Integration Pattern (NOT Duplication)

```python
# ❌ WRONG - Creating kernel inside kernel
from k0.modules.consolidation.observability.metrics_registry import P03MetricsRegistry

# ✅ CORRECT - Integrating with K0 kernel
from k0.obs.metrics import MetricsExporter

# P03 defines metrics, K0 exports them
P03_METRICS = {
    "p03_cycle_duration_seconds": Histogram(...),
    "p03_phase_duration_seconds": Histogram(...),
    "p03_decisions_total": Counter(...),
}

# Register with K0's exporter (not a new exporter)
for name, metric in P03_METRICS.items():
    MetricsExporter.register(name, metric)
```

```python
# ❌ WRONG - Creating P03-specific DLQ
from k0.modules.consolidation.resilience.dlq_record import DLQRecord

# ✅ CORRECT - Using K0's DLQ
from k0.storage.dlq import DLQStore

async def handle_p03_failure(envelope, error):
    await DLQStore.record(
        envelope=envelope,
        error=error,
        source="p03_consolidation",
        phase=current_phase,
    )
```

```python
# ❌ WRONG - Creating P03-specific RLS enforcer
from k0.modules.consolidation.security.rls_policies import P03RLSPolicy

# ✅ CORRECT - Using K0's RLS with P03 context
from k0.policy.rls import RLSEnforcer

# RLS policies defined in migrations (SQL), enforced by PostgreSQL
# P03 just sets the context before queries
async with RLSEnforcer.context(tenant_id=tenant, space_id=space):
    results = await conn.fetch("SELECT * FROM st_learned_weights")
```

---

## Part C: Epic Execution

### Epic 6.1 — Metrics/Tracing/Logging Implementation

> **Scope**: Implement comprehensive observability for P03 consolidation pipeline.
>
> **Dossier Reference**: Section 8 "Observability"

#### Epic 6.1 Issues Summary

| Issue | Title | Goal |
|-------|-------|------|
| 6.1.1 | P03 metrics registry and exporter integration | Centralized metrics registry |
| 6.1.2 | Consolidation cycle metrics implementation | Cycle-level metrics |
| 6.1.3 | Phase timing histograms per R0-R8 | Per-phase duration histograms |
| 6.1.4 | Decision metrics implementation (by type/layer) | Reconciliation decision metrics |
| 6.1.5 | Gap detection metrics for P06 integration | Knowledge gap metrics |
| 6.1.6 | Memory layer metrics implementation | Layer health metrics |
| 6.1.7 | Module performance metrics (M18-M25) | Per-module performance |
| 6.1.8 | Shadow mode and learning metrics | Shadow mode comparison |
| 6.1.9 | Decay engine metrics (resurrections, immunity) | Decay lifecycle metrics |
| 6.1.10 | Distributed tracing span hierarchy implementation | OpenTelemetry tracing |
| 6.1.11 | Trace context propagation (cycle_id, tenant_id, space_id baggage) | Trace context |
| 6.1.12 | Structured logging schema and context fields | JSON logging |
| 6.1.13 | Log levels by phase matrix implementation | Phase-appropriate logging |
| 6.1.14 | Cross-space leakage detection metrics | Security metrics |
| 6.1.15 | Formula debug tracing (3-level: User/Ops/Debug) | Debug tracing |
| 6.1.16 | Formula comparison metrics (new vs old version) | Version comparison |
| 6.1.17 | Grafana dashboard definitions | Dashboards |
| 6.1.18 | Alerting rules configuration | Prometheus alerts |
| 6.1.19 | Observability unit and integration tests | Test coverage |

---

#### Issue 6.1.1 — P03 Metrics Registry and Exporter Integration

**Status**: 🔲 NOT STARTED

**Goal**: Create centralized P03 metrics registry that integrates with K0's `MetricsExporter` to register all P03-specific metrics.

**Dossier Reference**: [Section 8.2 Metric Definitions](../pipelines/P03_consolidation_dossier_v2.md#82-metric-definitions)

**K0 Integration Pattern** (CRITICAL — do not duplicate kernel):

```python
# ✅ CORRECT — P03 USES K0's MetricsExporter, does not create its own
from k0.obs.metrics import MetricsExporter

class P03MetricsRegistry:
    """Registry of all P03 metrics. Delegates to K0 MetricsExporter."""

    def __init__(self, exporter: MetricsExporter):
        self._exporter = exporter
        self._registered = False

    def register_all(self) -> None:
        """Register all P03 metrics with K0's exporter (idempotent)."""
        if self._registered:
            return

        # Cycle metrics
        self._exporter.counter("p03_cycle_total", "Total consolidation cycles",
                               ["tenant_id", "status"])
        self._exporter.histogram("p03_cycle_duration_seconds",
                                 "Cycle duration", ["tenant_id", "phase"],
                                 buckets=[1, 5, 10, 30, 60, 120, 300, 600])

        # Phase metrics
        self._exporter.histogram("p03_phase_duration_seconds",
                                 "Phase duration", ["tenant_id", "phase"],
                                 buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120])

        # ... additional metrics from dossier 8.2
        self._registered = True
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| MetricsExporter | `k0/obs/metrics.py` | `counter()`, `histogram()`, `gauge()` methods |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | Existing counters/histograms dicts |
| R1PhaseMetrics | `k0/pipelines/p03/observability.py` | Pattern for `to_prometheus_metrics()` |
| P03OutboxPublisher | `k0/pipelines/p03/outbox_publisher.py` | Shows correct MetricsExporter usage |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/ops/__init__.py` (ops subpackage for observability)
2. [ ] Create `k0/pipelines/p03/ops/metrics.py` with `P03MetricsRegistry` class
3. [ ] Define all P03 metrics from dossier Section 8.2.1 (cycle metrics)
4. [ ] Define all P03 metrics from dossier Section 8.2.2 (decision metrics)
5. [ ] Define all P03 metrics from dossier Section 8.2.3 (gap metrics)
6. [ ] Define all P03 metrics from dossier Section 8.2.4 (learning metrics)
7. [ ] Add `P03MetricsRegistry.emit_cycle_complete()` convenience method
8. [ ] Add `P03MetricsRegistry.emit_phase_timing()` convenience method
9. [ ] Create tests: `tests/k0/pipelines/p03/test_p03_metrics_registry.py`

**Implementation Notes**:

- K0's `MetricsExporter` (line 50-240 of `k0/obs/metrics.py`) uses lazy metric creation
- Metrics are created on first use via `_counters`, `_gauges`, `_histograms` dicts
- `default_histogram_buckets`: (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
- P03 metrics MUST use `p03_` prefix for namespace consistency
- Labels from dossier: `tenant_id`, `space_id`, `phase`, `status`, `decision_type`, `target_layer`

**Acceptance Criteria**:

- [ ] `P03MetricsRegistry` created with all dossier-specified metrics
- [ ] Integrates with K0 `MetricsExporter` (no standalone Prometheus Registry)
- [ ] `register_all()` is idempotent (safe to call multiple times)
- [ ] Convenience methods for common emission patterns
- [ ] ≥95% test coverage for registry module

---

#### Issue 6.1.2 — Consolidation Cycle Metrics Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement cycle-level metrics that track overall P03 consolidation execution.

**Dossier Reference**: [Section 8.2.1 Consolidation Cycle Metrics](../pipelines/P03_consolidation_dossier_v2.md#821-consolidation-cycle-metrics)

**Metrics to Implement**:

```python
# From dossier 8.2.1
p03_cycle_total = Counter(
    'p03_cycle_total',
    'Total consolidation cycles executed',
    ['tenant_id', 'status']  # status: success, failure, partial, aborted
)

p03_cycle_duration_seconds = Histogram(
    'p03_cycle_duration_seconds',
    'Consolidation cycle duration',
    ['tenant_id', 'phase'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

p03_events_processed_total = Counter(
    'p03_events_processed_total',
    'Total events processed during consolidation',
    ['tenant_id', 'space_id', 'outcome']  # outcome: consolidated, duplicate, pruned
)

p03_pending_events = Gauge(
    'p03_pending_events',
    'Number of events pending consolidation',
    ['tenant_id', 'space_id']
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03SequentialRunner | `k0/pipelines/p03/runner.py` | Hook start/end of cycle |
| P03BatchEnvelope | `k0/pipelines/p03/envelope.py` | `events`, `context.cycle_id` |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | `counters`, `phase_start_ts`, `phase_end_ts` |
| P03PhaseResult | `k0/pipelines/p03/phase_interface.py` | `status`, `duration_ms` |

**Work To Do**:

1. [ ] Add `p03_cycle_total`, `p03_cycle_duration_seconds`, `p03_events_processed_total`, `p03_pending_events` to `P03MetricsRegistry`
2. [ ] Hook `P03SequentialRunner._run_cycle()` to emit `p03_cycle_total` on completion
3. [ ] Hook `P03SequentialRunner._run_cycle()` to emit `p03_cycle_duration_seconds` with total time
4. [ ] Hook phase completion to emit `p03_events_processed_total` with outcome labels
5. [ ] Implement `p03_pending_events` gauge update at cycle start (query `st_hipp_events` pending count)
6. [ ] Add status mapping: `P03PhaseResult.is_success() → success`, `.is_partial() → partial`, `.is_failure() → failure`
7. [ ] Create tests validating metric emission for each cycle outcome

**Integration Point**:

```python
# k0/pipelines/p03/runner.py - P03SequentialRunner
async def _run_cycle(self, envelope: P03BatchEnvelope) -> P03CycleResult:
    start_time = time.monotonic()
    try:
        # ... run phases ...
        result = P03CycleResult(...)

        # Emit cycle metrics via K0 exporter
        self._metrics.emit("p03_cycle_total", 1,
                           tenant_id=envelope.context.tenant_id,
                           status=result.status.value)
        self._metrics.observe("p03_cycle_duration_seconds",
                              time.monotonic() - start_time,
                              tenant_id=envelope.context.tenant_id,
                              phase="complete")
        return result
    except Exception as e:
        self._metrics.emit("p03_cycle_total", 1,
                           tenant_id=envelope.context.tenant_id,
                           status="failure")
        raise
```

**Acceptance Criteria**:

- [ ] All four cycle metrics emit correctly on cycle completion
- [ ] Status labels correctly reflect cycle outcome
- [ ] `p03_pending_events` updates at cycle start
- [ ] Metrics visible via Prometheus scrape endpoint
- [ ] Integration test validates metric values

---

#### Issue 6.1.3 — Phase Timing Histograms per R0-R8

**Status**: 🔲 NOT STARTED

**Goal**: Implement per-phase duration histograms for all 9 P03 phases (R0-R8).

**Dossier Reference**: [Section 8.2.1 Phase Timing](../pipelines/P03_consolidation_dossier_v2.md#821-consolidation-cycle-metrics)

**Metric to Implement**:

```python
p03_phase_duration_seconds = Histogram(
    'p03_phase_duration_seconds',
    'Duration of each consolidation phase',
    ['tenant_id', 'phase'],  # phase: R0, R1, R2, R3, R4, R5, R6, R7, R8
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120]
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | `start_phase()`, `end_phase()`, `get_phase_duration_ms()` |
| P03PhaseId | `k0/pipelines/p03/runner_contract.py` | Enum: R0, R1, R2, R3, R4, R5, R6, R7, R8 |
| VALID_PHASES | `k0/pipelines/p03/observability.py` | Tuple of valid phase IDs |
| PhaseTransitionLogger | `k0/pipelines/p03/observability.py` | Logs phase transitions |

**Work To Do**:

1. [ ] Add `p03_phase_duration_seconds` histogram to `P03MetricsRegistry`
2. [ ] Extend `P03ObservabilityContext.end_phase()` to emit histogram observation
3. [ ] Ensure bucket alignment: `[0.1, 0.5, 1, 5, 10, 30, 60, 120]` seconds
4. [ ] Add phase-specific latency targets from dossier:
   - R0 (Fetch): < 100ms
   - R1 (Hippocampal Replay): < 500ms
   - R2 (Similarity): < 1s
   - R3 (Reconciliation): < 2s
   - R4 (Staged Writes): < 500ms
   - R5 (Decay Signals): < 200ms
   - R6 (Gap Detection): < 300ms
   - R7 (Truth Writer): < 1s
   - R8 (Event Emission): < 200ms
5. [ ] Create tests validating histogram observations for each phase

**Implementation Pattern**:

```python
# k0/pipelines/p03/observability.py - P03ObservabilityContext
def end_phase(self, phase_id: str) -> float:
    """End phase timing and emit histogram."""
    duration_ms = self._phase_end_ts[phase_id] - self._phase_start_ts[phase_id]
    duration_seconds = duration_ms / 1000.0

    # Emit to K0 MetricsExporter
    self._metrics.observe(
        "p03_phase_duration_seconds",
        duration_seconds,
        tenant_id=self._tenant_id,
        phase=phase_id,
    )
    return duration_ms
```

**Acceptance Criteria**:

- [ ] All 9 phases (R0-R8) emit duration histograms
- [ ] Bucket boundaries match dossier specification
- [ ] Phase labels are consistent with `P03PhaseId` enum
- [ ] Latency targets documented for alerting rules (Issue 6.1.18)
- [ ] Tests validate histogram emission for each phase

---

#### Issue 6.1.4 — Decision Metrics Implementation (by type/layer)

**Status**: 🔲 NOT STARTED

**Goal**: Implement reconciliation decision metrics with labels for decision type and target layer.

**Dossier Reference**: [Section 8.2.2 Decision Metrics](../pipelines/P03_consolidation_dossier_v2.md#822-decision-metrics)

**Metrics to Implement**:

```python
# From dossier 8.2.2
p03_decisions_total = Counter(
    'p03_decisions_total',
    'Reconciliation decisions by type',
    ['tenant_id', 'decision_type', 'target_layer']
    # decision_type: REINFORCE, EXTEND, CREATE, EVOLVE, PRUNE, CONTRADICT
    # target_layer: st_epi, st_sem, st_procedural, st_social, st_prospective
)

p03_decision_confidence = Histogram(
    'p03_decision_confidence',
    'Confidence scores of reconciliation decisions',
    ['tenant_id', 'decision_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
)

p03_similarity_scores = Histogram(
    'p03_similarity_scores',
    'Similarity scores during truth matching',
    ['tenant_id', 'match_result'],  # match, partial, no_match
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| ReconciliationAction | `k0/pipelines/p03/reconciliation/action.py` | Enum: REINFORCE, EXTEND, CREATE, EVOLVE, PRUNE, CONTRADICT |
| ReconciliationDecision | `k0/pipelines/p03/reconciliation/decision.py` | Contains `action`, `confidence`, `target_layer` |
| R3Reconciler | `k0/pipelines/p03/phases/r3_reconciliation.py` | Produces decisions |
| P03StagedWrites | `k0/pipelines/p03/staged_writes.py` | `layer` field in StagedWrite |

**Work To Do**:

1. [ ] Add `p03_decisions_total`, `p03_decision_confidence`, `p03_similarity_scores` to `P03MetricsRegistry`
2. [ ] Hook `R3Reconciler` decision output to emit `p03_decisions_total` counter
3. [ ] Extract confidence from `ReconciliationDecision` to emit `p03_decision_confidence` histogram
4. [ ] Hook R2 similarity phase to emit `p03_similarity_scores` histogram
5. [ ] Map target layers: `st_epi`, `st_sem`, `st_procedural`, `st_social`, `st_prospective`
6. [ ] Map match results: `match` (similarity > 0.9), `partial` (0.7-0.9), `no_match` (< 0.7)
7. [ ] Create tests validating metric emission for each decision type

**Decision Type Mapping**:

| ReconciliationAction | Metric Label |
|---------------------|--------------|
| `REINFORCE` | `reinforce` |
| `EXTEND` | `extend` |
| `CREATE` | `create` |
| `EVOLVE` | `evolve` |
| `PRUNE` | `prune` |
| `CONTRADICT` | `contradict` |
| `SKIP` | `skip` |

**Acceptance Criteria**:

- [ ] All three decision metrics emit correctly
- [ ] Decision type labels match `ReconciliationAction` enum
- [ ] Target layer labels match truth table names
- [ ] Confidence buckets enable p99/p95 percentile queries
- [ ] Integration test validates decision metric values

---

#### Issue 6.1.5 — Gap Detection Metrics for P06 Integration

**Status**: 🔲 NOT STARTED

**Goal**: Implement knowledge gap metrics that integrate with P06 (Active Learning) pipeline.

**Dossier Reference**: [Section 8.2.3 Gap Detection Metrics](../pipelines/P03_consolidation_dossier_v2.md#823-gap-detection-metrics)

**Metrics to Implement**:

```python
# From dossier 8.2.3
p03_gaps_detected_total = Counter(
    'p03_gaps_detected_total',
    'Knowledge gaps detected during consolidation',
    ['tenant_id', 'gap_type']
    # gap_type: AMBIGUOUS_ENTITY, LOW_CONFIDENCE_EDGE, MISSING_ATTRIBUTE,
    #           CONTRADICTION, CONCEPT_DRIFT, STRUCTURAL_HOLE, STALE_ANCHOR
)

p03_gap_importance_score = Histogram(
    'p03_gap_importance_score',
    'Importance scores of detected gaps',
    ['tenant_id', 'gap_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

p03_gaps_pending = Gauge(
    'p03_gaps_pending',
    'Number of gaps pending resolution in st_learning_queue',
    ['tenant_id', 'space_id']
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| R6GapDetector | `k0/pipelines/p03/phases/r6_gap_detection.py` | Gap detection logic |
| GapRecord | `k0/pipelines/p03/gaps/gap_record.py` | `gap_type`, `importance`, `space_id` |
| GapEmitter | `k0/pipelines/p03/gaps/gap_emitter.py` | Emits gaps to P06 |
| st_learning_queue | SQL schema | Pending gaps storage |

**Gap Type Enum**:

```python
class GapType(str, Enum):
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"      # Multiple matches for same entity
    LOW_CONFIDENCE_EDGE = "LOW_CONFIDENCE_EDGE"  # Edge below confidence threshold
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"     # Expected attribute not present
    CONTRADICTION = "CONTRADICTION"             # Conflicting information
    CONCEPT_DRIFT = "CONCEPT_DRIFT"             # Meaning shift detected
    STRUCTURAL_HOLE = "STRUCTURAL_HOLE"         # Missing link in graph
    STALE_ANCHOR = "STALE_ANCHOR"               # Anchor needs refresh
```

**Work To Do**:

1. [ ] Add `p03_gaps_detected_total`, `p03_gap_importance_score`, `p03_gaps_pending` to `P03MetricsRegistry`
2. [ ] Hook `R6GapDetector` or `GapEmitter` to emit `p03_gaps_detected_total` on gap detection
3. [ ] Extract importance from `GapRecord` to emit `p03_gap_importance_score` histogram
4. [ ] Implement `p03_gaps_pending` gauge update by querying `st_learning_queue WHERE status = 'pending'`
5. [ ] Map gap types to label values (lowercase with underscores)
6. [ ] Create tests validating metric emission for each gap type

**P06 Integration Point**:

```python
# k0/pipelines/p03/gaps/gap_emitter.py
class GapEmitter:
    async def emit(self, gap: GapRecord) -> None:
        # Persist to st_learning_queue for P06
        await self._store.insert(gap)

        # Emit metrics to K0
        self._metrics.emit("p03_gaps_detected_total", 1,
                          tenant_id=gap.tenant_id,
                          gap_type=gap.gap_type.value.lower())
        self._metrics.observe("p03_gap_importance_score",
                             gap.importance,
                             tenant_id=gap.tenant_id,
                             gap_type=gap.gap_type.value.lower())
```

**Acceptance Criteria**:

- [ ] All three gap metrics emit correctly
- [ ] Gap type labels match `GapType` enum (lowercased)
- [ ] Importance score buckets span 0.0-1.0
- [ ] `p03_gaps_pending` accurately reflects queue depth
- [ ] P06 can query gap metrics for prioritization
- [ ] Integration test validates gap metric values

---

#### Issue 6.1.6 — Memory Layer Metrics Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement health metrics for all 8 memory layers (truth tables).

**Dossier Reference**: [Section 8.2.4 Memory Layer Metrics](../pipelines/P03_consolidation_dossier_v2.md#824-memory-layer-metrics)

**Metrics to Implement**:

```python
# From dossier 8.2.4
p03_layer_records_total = Counter(
    'p03_layer_records_total',
    'Records created/updated in memory layers',
    ['tenant_id', 'layer', 'operation']  # operation: create, update, archive, tombstone
)

p03_layer_size = Gauge(
    'p03_layer_size',
    'Current size of memory layer (canonical records only)',
    ['tenant_id', 'layer', 'archival_status']  # archival_status: active, archived, tombstoned
)

p03_layer_avg_confidence = Gauge(
    'p03_layer_avg_confidence',
    'Average confidence score in memory layer',
    ['tenant_id', 'layer']
)

p03_layer_avg_decay = Gauge(
    'p03_layer_avg_decay',
    'Average decay factor in memory layer',
    ['tenant_id', 'layer']
)
```

**Memory Layer Enum**:

```python
MEMORY_LAYERS = [
    "st_epi",           # Episodic Memory
    "st_sem",           # Semantic Memory
    "st_procedural",    # Procedural Memory (habits)
    "st_social",        # Social Memory (relationships)
    "st_prospective",   # Prospective Memory (intentions)
    "st_kg_dom",        # Knowledge Graph: entities/concepts
    "st_kg_edges",      # Knowledge Graph: relationships
    "st_hipp_events",   # Hippocampal buffer (staging)
]
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| R7TruthWriter | `k0/pipelines/p03/phases/r7_truth_writer.py` | `_execute_staged_writes()` |
| P03StagedWrites | `k0/pipelines/p03/staged_writes.py` | `layer` field, WriteOperation enum |
| WriteOperation | `k0/pipelines/p03/staged_writes.py` | INSERT, UPDATE, ARCHIVE, TOMBSTONE |
| UnifiedDecayEngine | `k0/modules/consolidation/algorithms/decay_engine.py` | `LAYER_LAMBDAS` constant |

**Work To Do**:

1. [ ] Add `p03_layer_records_total`, `p03_layer_size`, `p03_layer_avg_confidence`, `p03_layer_avg_decay` to `P03MetricsRegistry`
2. [ ] Hook `R7TruthWriter._execute_single_write()` to emit `p03_layer_records_total`
3. [ ] Map WriteOperation to operation labels: INSERT→`create`, UPDATE→`update`, ARCHIVE→`archive`, TOMBSTONE→`tombstone`
4. [ ] Create periodic task (or cycle-end hook) to update `p03_layer_size` gauges
5. [ ] Query each layer's record count grouped by archival_status
6. [ ] Compute `p03_layer_avg_confidence` via `SELECT AVG(confidence_score) FROM {layer}`
7. [ ] Compute `p03_layer_avg_decay` via `SELECT AVG(decay_factor) FROM {layer}`
8. [ ] Create tests validating layer metrics for each operation type

**Layer Size Query Pattern**:

```sql
-- For each layer, get counts by archival status
SELECT
    'st_epi' as layer,
    archival_status,
    COUNT(*) as record_count
FROM st_epi
WHERE space_id = $1
GROUP BY archival_status;
```

**Acceptance Criteria**:

- [ ] All four layer metrics emit correctly for all 8 layers
- [ ] Operation labels correctly mapped from WriteOperation enum
- [ ] Layer size gauges reflect current database state
- [ ] Average confidence/decay computed correctly
- [ ] Integration test validates per-layer metric values

---

#### Issue 6.1.7 — Module Performance Metrics (M18-M25)

**Status**: 🔲 NOT STARTED

**Goal**: Implement per-module performance metrics for all P03-specific modules.

**Dossier Reference**: [Section 8.2.5 Module Performance Metrics](../pipelines/P03_consolidation_dossier_v2.md#825-module-performance-metrics)

**Module Registry** (from dossier Section 7.2):

| Module | Name | Phase | Responsibility |
| ------ | ---- | ----- | -------------- |
| M18 | EpisodicClusterer | R2 | DBSCAN clustering of episodes |
| M19 | DuplicateDetector | R3 | SimHash deduplication |
| M20 | RetentionEnforcer | R3 | Decay calculation, archival decisions |
| M21 | KGConsolidator | R4 | Entity/relationship extraction |
| M22 | DreamExplorer | R5 | Counterfactual simulation (optional) |
| M23 | ReplayCoordinator | R1 | Importance scoring, batch selection |
| M24 | TruthWriter | R7 | Memory layer write orchestration |
| M25 | GapDetector | R8 | Active Learning gap detection |

**Metrics to Implement**:

```python
# From dossier 8.2.5
p03_module_duration_seconds = Histogram(
    'p03_module_duration_seconds',
    'Execution time per module',
    ['tenant_id', 'module'],  # module: M18, M19, M20, M21, M22, M23, M24, M25
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30]
)

p03_module_items_processed = Counter(
    'p03_module_items_processed',
    'Items processed by each module',
    ['tenant_id', 'module', 'outcome']  # outcome: success, skip, error
)

# M18-specific: Clustering metrics
p03_clustering_clusters_created = Counter(
    'p03_clustering_clusters_created',
    'Episode clusters created by M18',
    ['tenant_id']
)

p03_clustering_cluster_size = Histogram(
    'p03_clustering_cluster_size',
    'Size of episode clusters',
    ['tenant_id'],
    buckets=[1, 2, 5, 10, 20, 50, 100]
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | Phase timing methods |
| EpisodicClusterer | `k0/pipelines/p03/clustering/episodic_clusterer.py` | `cluster()` method |
| DuplicateDetector | `k0/pipelines/p03/dedup/duplicate_detector.py` | `detect()` method |
| RetentionEnforcer | `k0/pipelines/p03/retention/retention_enforcer.py` | `evaluate()` method |

**Work To Do**:

1. [ ] Add `p03_module_duration_seconds`, `p03_module_items_processed` to `P03MetricsRegistry`
2. [ ] Add M18-specific `p03_clustering_clusters_created`, `p03_clustering_cluster_size`
3. [ ] Create `@module_metric` decorator for timing module execution
4. [ ] Wrap each module's entry point with timing instrumentation
5. [ ] Emit `p03_module_items_processed` with outcome labels on module completion
6. [ ] Hook M18 cluster output to emit clustering-specific metrics
7. [ ] Create tests validating module metrics for each M18-M25 module

**Instrumentation Pattern**:

```python
# k0/pipelines/p03/ops/module_metrics.py
def module_metric(module_id: str):
    """Decorator for module performance instrumentation."""
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            start = time.monotonic()
            try:
                result = await func(self, *args, **kwargs)
                self._metrics.emit("p03_module_items_processed", 1,
                                  tenant_id=self._tenant_id,
                                  module=module_id,
                                  outcome="success")
                return result
            except Exception as e:
                self._metrics.emit("p03_module_items_processed", 1,
                                  tenant_id=self._tenant_id,
                                  module=module_id,
                                  outcome="error")
                raise
            finally:
                duration = time.monotonic() - start
                self._metrics.observe("p03_module_duration_seconds",
                                     duration,
                                     tenant_id=self._tenant_id,
                                     module=module_id)
        return wrapper
    return decorator
```

**Acceptance Criteria**:

- [ ] All 8 modules (M18-M25) emit duration histograms
- [ ] Items processed counters track success/skip/error outcomes
- [ ] M18 clustering metrics capture cluster creation patterns
- [ ] Module latency percentiles queryable via PromQL
- [ ] Integration test validates each module's metrics

---

#### Issue 6.1.8 — Shadow Mode and Learning Metrics

**Status**: 🔲 NOT STARTED

**Goal**: Implement shadow mode metrics for comparing baseline vs learned formula outcomes.

**Dossier Reference**: [Section 8.2.6 Shadow Mode Learning Metrics](../pipelines/P03_consolidation_dossier_v2.md#826-shadow-mode-learning-metrics)

**Shadow Mode Concept** (from dossier Section 6.5):

- Feature flag controls: `off` → `shadow` → `partial` → `full`
- Shadow mode runs BOTH baseline and learned formulas, applies only baseline
- Comparison logged for analysis before promotion

**Learning Types**:

| Learning Type | Description | Affects |
| ------------- | ----------- | ------- |
| `importance` | Importance scoring weights | R1 hippocampal replay |
| `hebbian` | Edge weight adjustments | R4 KG consolidation |
| `decay` | Lambda parameter tuning | R3/R5 retention |
| `similarity` | Matching thresholds | R2 clustering |
| `threshold` | Decision thresholds | R3 reconciliation |

**Metrics to Implement**:

```python
# From dossier 8.2.6
p03_shadow_executions_total = Counter(
    'p03_shadow_executions_total',
    'Total shadow mode dual executions',
    ['tenant_id', 'learning_type', 'outcome']
    # outcome: agreement, improvement, regression, divergence
)

p03_shadow_agreement_rate = Gauge(
    'p03_shadow_agreement_rate',
    'Percentage where old and new formulas agree',
    ['tenant_id', 'learning_type']
)

p03_shadow_improvement_rate = Gauge(
    'p03_shadow_improvement_rate',
    'Percentage where new formula is objectively better',
    ['tenant_id', 'learning_type']
)

p03_shadow_regression_rate = Gauge(
    'p03_shadow_regression_rate',
    'Percentage where new formula is worse than baseline',
    ['tenant_id', 'learning_type']
)

p03_shadow_divergence_magnitude = Histogram(
    'p03_shadow_divergence_magnitude',
    'Magnitude of difference when decisions diverge',
    ['tenant_id', 'learning_type'],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
)

p03_shadow_promotion_eligibility = Gauge(
    'p03_shadow_promotion_eligibility',
    'Whether shadow mode meets promotion criteria (0=no, 1=yes)',
    ['tenant_id', 'learning_type']
)

p03_shadow_sample_size = Gauge(
    'p03_shadow_sample_size',
    'Number of shadow mode samples collected (last 7 days)',
    ['tenant_id', 'learning_type']
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| FeatureFlags | `k0/config/feature_flags.py` | `P03_FF_IMPORTANCE_LEARNING` etc. |
| st_consolidation_audit | SQL schema | Shadow comparison records |
| LearningMode | `k0/pipelines/p03/learning/mode.py` | Enum: OFF, SHADOW, PARTIAL, FULL |

**Work To Do**:

1. [ ] Add all 7 shadow metrics to `P03MetricsRegistry`
2. [ ] Create `ShadowModeComparator` class for outcome classification
3. [ ] Implement `compare_importance_scores()`, `compare_hebbian_weights()`, etc.
4. [ ] Hook shadow comparisons to emit `p03_shadow_executions_total`
5. [ ] Implement rolling rate calculations (7-day window) for agreement/improvement/regression gauges
6. [ ] Define promotion criteria: `improvement_rate > 0.05 AND regression_rate < 0.02 AND sample_size > 1000`
7. [ ] Update `p03_shadow_promotion_eligibility` based on criteria evaluation
8. [ ] Create tests validating shadow metrics for each learning type

**Shadow Comparison Logic**:

```python
# k0/pipelines/p03/ops/shadow_comparator.py
class ShadowModeComparator:
    AGREEMENT_TOLERANCE = 0.05  # Within 5% = agreement
    IMPROVEMENT_THRESHOLD = 0.10  # 10% better = improvement

    def compare(self, baseline: float, learned: float, ground_truth: float | None) -> str:
        """Classify comparison outcome."""
        if abs(baseline - learned) / max(baseline, 0.001) < self.AGREEMENT_TOLERANCE:
            return "agreement"

        if ground_truth is not None:
            baseline_error = abs(baseline - ground_truth)
            learned_error = abs(learned - ground_truth)

            if learned_error < baseline_error * (1 - self.IMPROVEMENT_THRESHOLD):
                return "improvement"
            elif learned_error > baseline_error * (1 + self.IMPROVEMENT_THRESHOLD):
                return "regression"

        return "divergence"
```

**Acceptance Criteria**:

- [ ] All 7 shadow metrics emit correctly per learning type
- [ ] Outcome classification (agreement/improvement/regression/divergence) is accurate
- [ ] Rolling rate gauges update based on 7-day sliding window
- [ ] Promotion eligibility reflects actual criteria evaluation
- [ ] Integration test validates shadow mode metric values

---

#### Issue 6.1.9 — Decay Engine Metrics (Resurrections, Immunity)

**Status**: 🔲 NOT STARTED

**Goal**: Implement decay lifecycle metrics including resurrection tracking and immunity handling.

**Dossier Reference**: [Section 8.2.7 Decay Engine Metrics](../pipelines/P03_consolidation_dossier_v2.md#827-decay-engine-metrics)

**Decay Engine** (from `k0/modules/consolidation/algorithms/decay_engine.py`):

- `UnifiedDecayEngine` with per-layer λ values (LAYER_LAMBDAS)
- `DecayClassification`: ACTIVE (≥0.10), ARCHIVE_CANDIDATE (0.01-0.10), PRUNE_CANDIDATE (<0.01)
- Resurrection formula: `max(0.70, 0.50 + old_decay × 0.50)`

**Resurrection Triggers**:

| Trigger | Description |
| ------- | ----------- |
| `QUERY` | Entity retrieved via direct query |
| `CO_OCCURRENCE` | Entity appears with active entity |
| `USER_MENTION` | User explicitly references entity |

**Metrics to Implement**:

```python
# From dossier 8.2.7
# Aggregate decay metrics
p03_decay_total_active = Gauge(
    'p03_decay_total_active',
    'Total ACTIVE records across all memory layers',
    ['tenant_id', 'space_id']
)

p03_decay_total_archived = Gauge(
    'p03_decay_total_archived',
    'Total ARCHIVED records across all memory layers',
    ['tenant_id', 'space_id']
)

p03_decay_total_tombstoned = Gauge(
    'p03_decay_total_tombstoned',
    'Total TOMBSTONE records across all memory layers',
    ['tenant_id', 'space_id']
)

# Resurrection metrics
p03_decay_resurrections_total = Counter(
    'p03_decay_resurrections_total',
    'Total resurrection events',
    ['tenant_id', 'space_id', 'layer', 'trigger']
)

p03_resurrection_rate = Gauge(
    'p03_resurrection_rate',
    'Resurrections per 1000 accesses (rolling 7d)',
    ['tenant_id', 'space_id', 'layer']
)

p03_resurrection_loops = Counter(
    'p03_resurrection_loops',
    'Entities with resurrection_count >= 3 (instability)',
    ['tenant_id', 'space_id', 'layer']
)

# Immunity metrics
p03_decay_immune_entities = Gauge(
    'p03_decay_immune_entities',
    'Count of immune entities per layer',
    ['tenant_id', 'space_id', 'layer', 'reason']
)

p03_decay_immune_skipped = Counter(
    'p03_decay_immune_skipped',
    'Decay updates skipped due to immunity',
    ['tenant_id', 'space_id', 'layer']
)

# Lambda learning metrics
p03_lambda_learned_spaces = Gauge(
    'p03_lambda_learned_spaces',
    'Number of spaces with learned λ modifiers',
    ['layer']
)

p03_lambda_drift_30d = Gauge(
    'p03_lambda_drift_30d',
    'Maximum λ change over 30 days per space',
    ['tenant_id', 'space_id', 'layer']
)

# Decay feedback metrics
p03_decay_feedback_events = Counter(
    'p03_decay_feedback_events',
    'Decay feedback events recorded',
    ['layer', 'event_type']  # event_type: ACCESS, RESURRECTION, ARCHIVE, TOMBSTONE
)

p03_premature_archival_rate = Gauge(
    'p03_premature_archival_rate',
    'Rate of entities accessed within 7 days of archival',
    ['layer', 'space_id']
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| UnifiedDecayEngine | `k0/modules/consolidation/algorithms/decay_engine.py` | `classify_record()`, `LAYER_LAMBDAS` |
| DecayClassification | `k0/modules/consolidation/algorithms/decay_engine.py` | ACTIVE, ARCHIVE_CANDIDATE, PRUNE_CANDIDATE |
| RetentionEnforcer | `k0/pipelines/p03/retention/retention_enforcer.py` | `compute_resurrection_decay()` |
| st_decay_feedback | SQL schema | Decay feedback events |

**Work To Do**:

1. [ ] Add all 14 decay metrics to `P03MetricsRegistry`
2. [ ] Hook `RetentionEnforcer.evaluate()` to emit classification counts
3. [ ] Track resurrection events with trigger type labels
4. [ ] Implement resurrection loop detection (`resurrection_count >= 3`)
5. [ ] Track immunity reasons: `FAMILY_MEMBER`, `MANUAL_PIN`, `HIGH_ACCESS_FREQUENCY`
6. [ ] Query `st_learned_weights` for lambda drift calculation
7. [ ] Compute premature archival rate from `st_decay_feedback`
8. [ ] Create tests validating decay metrics across lifecycle states

**Resurrection Constants** (from test file):

```python
RESURRECTION_FLOOR = 0.70   # Minimum post-resurrection decay
RESURRECTION_BASE = 0.50    # Base value
RESURRECTION_CARRY = 0.50   # Carry-over factor from old decay
RESURRECTION_ALERT_THRESHOLD = 3  # Loop detection threshold
```

**Alert Conditions**:

| Metric | Warning | Critical | Action |
| ------ | ------- | -------- | ------ |
| `resurrection_rate` | > 5% | > 10% | Lambda too aggressive |
| `immune_skipped` | > 30% | > 50% | Too many immunities |
| `lambda_drift_30d` | > 30% | > 50% | Unstable learning |
| `premature_archival_rate` | > 3% | > 5% | Archive threshold too low |

**Acceptance Criteria**:

- [ ] All 14 decay metrics emit correctly
- [ ] Resurrection tracking includes trigger type labels
- [ ] Loop detection identifies unstable entities
- [ ] Immunity tracking differentiates reasons
- [ ] Lambda drift calculations are accurate over 30-day window
- [ ] Integration test validates decay lifecycle metrics

---

#### Issue 6.1.10 — Distributed Tracing Span Hierarchy Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement OpenTelemetry distributed tracing with proper span hierarchy for P03 phases.

**Dossier Reference**: [Section 8.3 Distributed Tracing](../pipelines/P03_consolidation_dossier_v2.md#83-distributed-tracing)

**K0 Tracing Infrastructure** (from `k0/obs/tracing.py`):

```python
# K0 TracerFactory provides:
- TracerFactory(service_name, service_version, environment, otlp_endpoint, sample_ratio)
- span(name, kind, attributes, context_override)  # Context manager
- new_trace_id()                                   # Generate cognitive trace ID
- attach_cognitive_trace(trace_id)                 # Attach to context
- current_cognitive_trace_id()                     # Get from context
- COGNITIVE_TRACE_BAGGAGE_KEY = "cognitive_trace_id"
```

**P03 Span Hierarchy** (from dossier 8.3.1):

```
p03.consolidation_cycle (root)
├── p03.r0.trigger_detection
├── p03.r1.replay
│   ├── p03.r1.batch_selection
│   └── p03.r1.importance_scoring
├── p03.r2.clustering
│   ├── p03.r2.embedding_fetch
│   ├── p03.r2.dbscan
│   └── p03.r2.pattern_extraction
├── p03.r3.forgetting
│   ├── p03.r3.deduplication
│   └── p03.r3.retention_enforcement
├── p03.r4.kg_consolidation
│   ├── p03.r4.entity_extraction
│   ├── p03.r4.entity_resolution
│   └── p03.r4.edge_discovery
├── p03.r5.dream_exploration (optional)
├── p03.r6.staging_update
├── p03.r7.truth_write
│   ├── p03.r7.outbox_insert
│   └── p03.r7.layer_write (per layer)
└── p03.r8.event_emission
    ├── p03.r8.bus_publish
    └── p03.r8.gap_emission
```

**Required Span Attributes**:

| Attribute | Type | Description |
| --------- | ---- | ----------- |
| `cycle_id` | string | P03 cycle identifier |
| `tenant_id` | string | Tenant isolation |
| `space_id` | string | Space isolation |
| `phase` | string | R0-R8 phase identifier |
| `batch_size` | int | Number of events in batch |
| `duration_ms` | int | Phase duration |

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| TracerFactory | `k0/obs/tracing.py` | `span()`, `attach_cognitive_trace()` |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | `push_span()`, `pop_span()`, span_stack |
| P03SequentialRunner | `k0/pipelines/p03/runner.py` | Phase orchestration loop |
| COGNITIVE_TRACE_BAGGAGE_KEY | `k0/obs/tracing.py` | Baggage propagation key |

**Work To Do**:

1. [ ] Create `P03ConsolidationTracer` class wrapping K0's `TracerFactory`
2. [ ] Implement `trace_cycle(cycle_id, tenant_id, space_id)` context manager for root span
3. [ ] Implement `start_phase_span(phase_id, **attributes)` for phase spans
4. [ ] Implement sub-span creation for phase sub-operations (e.g., `r1.batch_selection`)
5. [ ] Hook `P03SequentialRunner` to create root span on cycle start
6. [ ] Hook each phase to create phase span with proper parent
7. [ ] Attach cognitive trace ID via `attach_cognitive_trace()`
8. [ ] Ensure span propagation across async boundaries
9. [ ] Create tests validating span hierarchy correctness

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/tracing.py
from k0.obs.tracing import TracerFactory, COGNITIVE_TRACE_BAGGAGE_KEY

class P03ConsolidationTracer:
    """Distributed tracing for P03 consolidation cycles."""

    def __init__(self, tracer_factory: TracerFactory):
        self._tracer = tracer_factory.get_tracer()
        self._factory = tracer_factory

    @contextmanager
    def trace_cycle(self, cycle_id: str, tenant_id: str, space_id: str):
        """Create root span for consolidation cycle."""
        # Attach cognitive trace ID for cross-service correlation
        trace_token = self._factory.attach_cognitive_trace(cycle_id)
        try:
            with self._factory.span(
                "p03.consolidation_cycle",
                attributes={
                    "cycle_id": cycle_id,
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                }
            ) as root_span:
                yield root_span
        finally:
            TracerFactory.detach(trace_token)

    @contextmanager
    def phase_span(self, phase_id: str, **attributes):
        """Create span for a consolidation phase."""
        with self._factory.span(
            f"p03.{phase_id.lower()}",
            attributes={"phase": phase_id, **attributes}
        ) as span:
            yield span

    @contextmanager
    def sub_span(self, operation: str, **attributes):
        """Create span for sub-operation within a phase."""
        with self._factory.span(
            f"p03.{operation}",
            attributes=attributes
        ) as span:
            yield span
```

**Trace Context Propagation**:

```python
# Required baggage items for cross-service propagation
REQUIRED_BAGGAGE = [
    'cycle_id',        # P03 cycle identifier
    'tenant_id',       # Tenant isolation
    'space_id',        # Space isolation
    'correlation_id',  # Cross-service correlation
]

# Optional baggage items
OPTIONAL_BAGGAGE = [
    'source_event_ids',  # Comma-separated source events
    'triggered_by',      # What triggered this cycle
    'parent_cycle_id',   # If retry/continuation
]
```

**Acceptance Criteria**:

- [ ] Root span `p03.consolidation_cycle` created for each cycle
- [ ] Phase spans correctly nested under root span
- [ ] Sub-spans created for phase sub-operations
- [ ] Cognitive trace ID attached and propagated
- [ ] Required attributes present on all spans
- [ ] Traces visible in Jaeger/Zipkin
- [ ] Span hierarchy matches dossier specification (8.3.1)
- [ ] Integration test validates span tree structure

---

#### Issue 6.1.11 — Trace Context Propagation (cycle_id, tenant_id, space_id Baggage)

**Status**: 🔲 NOT STARTED

**Goal**: Implement trace context propagation using OpenTelemetry baggage for cross-service correlation.

**Dossier Reference**: [Section 8.3.2 Trace Context Propagation](../pipelines/P03_consolidation_dossier_v2.md#832-trace-context-propagation)

**K0 Tracing Infrastructure** (from `k0/obs/tracing.py`):

```python
# K0 provides baggage propagation via OpenTelemetry:
COGNITIVE_TRACE_BAGGAGE_KEY = "cognitive_trace_id"

class TracerFactory:
    def attach_cognitive_trace(self, trace_id: str) -> object:
        """Attach the cognitive trace identifier to the current context."""
        baggage_ctx = baggage.set_baggage(COGNITIVE_TRACE_BAGGAGE_KEY, trace_id)
        return context.attach(baggage_ctx)

    @staticmethod
    def current_cognitive_trace_id() -> str | None:
        """Fetch the cognitive trace identifier from the current context."""
        return str(baggage.get_baggage(COGNITIVE_TRACE_BAGGAGE_KEY))

    @staticmethod
    def inject(headers: MutableMapping[str, str]) -> None:
        """Inject the current context into HTTP headers."""
        propagate.inject(headers)

    @staticmethod
    def extract(headers: Mapping[str, str]):
        """Extract a context from HTTP headers."""
        return propagate.extract(headers)
```

**Required Baggage Items** (from dossier 8.3.2):

| Baggage Key | Description | Required |
| ----------- | ----------- | -------- |
| `cycle_id` | P03 cycle identifier (ULID) | ✅ Yes |
| `tenant_id` | Tenant isolation key | ✅ Yes |
| `space_id` | Space isolation key | ✅ Yes |
| `correlation_id` | Cross-service correlation | ✅ Yes |
| `source_event_ids` | Comma-separated source events | Optional |
| `triggered_by` | What triggered this cycle | Optional |
| `parent_cycle_id` | If retry/continuation | Optional |

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| TracerFactory | `k0/obs/tracing.py` | `attach_cognitive_trace()`, `inject()`, `extract()` |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | `trace_id`, `log_context` |
| P03CycleContext | `k0/pipelines/p03/runner_contract.py` | `cycle_id`, `tenant_id`, `space_id` |
| P03OutboxPublisher | `k0/pipelines/p03/outbox_publisher.py` | Event emission with trace context |

**Work To Do**:

1. [ ] Create `P03TraceContextPropagator` class in `k0/pipelines/p03/ops/context_propagation.py`
2. [ ] Implement `attach_p03_baggage(cycle_id, tenant_id, space_id, correlation_id)` method
3. [ ] Extend K0's baggage to include all required P03 fields (not just cognitive_trace_id)
4. [ ] Implement `inject_into_event(event_payload, span)` for bus event propagation
5. [ ] Implement `extract_from_event(event_payload)` for downstream context restoration
6. [ ] Hook `P03SequentialRunner` to attach baggage at cycle start
7. [ ] Hook `P03OutboxPublisher` to inject context into outbound events
8. [ ] Create tests validating baggage propagation across service boundaries

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/context_propagation.py
from opentelemetry import baggage, context, propagate, trace
from typing import MutableMapping

class P03TraceContextPropagator:
    """Propagate P03 trace context across service boundaries."""

    # Baggage keys
    CYCLE_ID_KEY = "p03_cycle_id"
    TENANT_ID_KEY = "p03_tenant_id"
    SPACE_ID_KEY = "p03_space_id"
    CORRELATION_ID_KEY = "correlation_id"

    def attach_p03_baggage(
        self,
        cycle_id: str,
        tenant_id: str,
        space_id: str,
        correlation_id: str | None = None,
    ) -> object:
        """Attach all P03 baggage items to current context."""
        ctx = context.get_current()
        ctx = baggage.set_baggage(self.CYCLE_ID_KEY, cycle_id, ctx)
        ctx = baggage.set_baggage(self.TENANT_ID_KEY, tenant_id, ctx)
        ctx = baggage.set_baggage(self.SPACE_ID_KEY, space_id, ctx)
        if correlation_id:
            ctx = baggage.set_baggage(self.CORRELATION_ID_KEY, correlation_id, ctx)
        return context.attach(ctx)

    def inject_into_event(self, event_payload: dict, span: trace.Span) -> dict:
        """Inject trace context into bus event payload."""
        span_ctx = span.get_span_context()
        event_payload["trace_id"] = format(span_ctx.trace_id, "032x")
        event_payload["span_id"] = format(span_ctx.span_id, "016x")

        # Include baggage in event payload
        event_payload["cycle_id"] = baggage.get_baggage(self.CYCLE_ID_KEY)
        event_payload["tenant_id"] = baggage.get_baggage(self.TENANT_ID_KEY)
        event_payload["space_id"] = baggage.get_baggage(self.SPACE_ID_KEY)

        return event_payload

    def extract_from_headers(self, headers: dict) -> object:
        """Extract context from incoming HTTP headers."""
        return propagate.extract(headers)
```

**Acceptance Criteria**:

- [ ] All required baggage items attached at cycle start
- [ ] Baggage propagated to child spans automatically
- [ ] Event payloads contain trace context fields
- [ ] Downstream services can extract and continue trace
- [ ] Cross-service correlation visible in trace backends
- [ ] Integration test validates end-to-end propagation

---

#### Issue 6.1.12 — Structured Logging Schema and Context Fields

**Status**: 🔲 NOT STARTED

**Goal**: Define and implement P03-specific structured logging schema with required context fields.

**Dossier Reference**: [Section 8.4.1 Log Schema](../pipelines/P03_consolidation_dossier_v2.md#841-log-schema)

**K0 Logging Infrastructure** (from `k0/obs/logging.py`):

```python
# K0 provides:
StructuredLogFormatter  # JSON formatter with PII redaction
bind_log_context()      # Bind context values for subsequent log records
update_log_context()    # Merge additional values into active log context
current_log_context()   # Return the active structured logging context
reset_log_context()     # Reset context to previous state

# _StructuredContextFilter attaches:
- cognitive_trace_id from TracerFactory.current_cognitive_trace_id()
- All keys from current_log_context()

# _DEFAULT_SENSITIVE_KEYS for PII redaction:
email, phone, ssn, password, api_key, tenant_id, space_id, user_id, etc.
```

**P03 Log Schema** (from dossier 8.4.1):

```python
P03_LOG_SCHEMA = {
    # Required fields (all logs)
    "timestamp": "ISO 8601 timestamp",
    "level": "DEBUG | INFO | WARN | ERROR",
    "message": "Human-readable message",
    "correlation_id": "Trace correlation ID",

    # P03-specific fields (always present in P03 logs)
    "cycle_id": "P03 cycle identifier",
    "phase": "R0 | R1 | R2 | ... | R8",
    "tenant_id": "Tenant ID",
    "space_id": "Space ID",

    # Contextual fields (phase-dependent)
    "event_id": "Source event ID if applicable",
    "decision_type": "REINFORCE | EXTEND | CREATE | EVOLVE | PRUNE | CONTRADICT",
    "target_layer": "st_epi | st_sem | st_procedural | ...",
    "duration_ms": "Operation duration",
    "error_code": "Error code if error",
    "error_message": "Error message if error",
}
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| StructuredLogFormatter | `k0/obs/logging.py` | JSON formatting, PII redaction |
| bind_log_context | `k0/obs/logging.py` | Context binding |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | `get_log_context()`, `set_log_context()` |
| _StructuredContextFilter | `k0/obs/logging.py` | Auto-attach cognitive_trace_id |

**Work To Do**:

1. [ ] Create `P03LogSchema` dataclass in `k0/pipelines/p03/ops/logging.py`
2. [ ] Define `P03_REQUIRED_FIELDS` and `P03_OPTIONAL_FIELDS` constants
3. [ ] Implement `P03LogContextManager` class for phase-aware context management
4. [ ] Implement `bind_p03_context(cycle_id, tenant_id, space_id, phase)` helper
5. [ ] Extend `P03ObservabilityContext.get_log_context()` to return full schema
6. [ ] Add phase-specific field validators
7. [ ] Hook runner to bind P03 context at phase start/end
8. [ ] Create tests validating log output against schema

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/logging.py
from k0.obs.logging import bind_log_context, reset_log_context
from contextlib import contextmanager

P03_REQUIRED_FIELDS = frozenset({
    "cycle_id", "phase", "tenant_id", "space_id"
})

P03_OPTIONAL_FIELDS = frozenset({
    "event_id", "decision_type", "target_layer", "duration_ms",
    "error_code", "error_message", "batch_size", "similarity_score",
    "confidence_before", "confidence_after"
})

class P03LogContextManager:
    """Manage P03 structured logging context."""

    @contextmanager
    def cycle_context(self, cycle_id: str, tenant_id: str, space_id: str):
        """Bind P03 cycle context for all logs within scope."""
        token = bind_log_context(
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            space_id=space_id,
            pipeline="P03"
        )
        try:
            yield
        finally:
            reset_log_context(token)

    @contextmanager
    def phase_context(self, phase: str, **extra):
        """Bind phase-specific context."""
        token = bind_log_context(phase=phase, **extra)
        try:
            yield
        finally:
            reset_log_context(token)
```

**Log Examples** (from dossier):

```python
# INFO: Cycle start
logger.info(
    "consolidation_cycle_started",
    cycle_id="01HXYZ...",
    tenant_id="tenant_123",
    space_id="space_456",
    phase="R0",
    pending_events=1500
)

# DEBUG: Reconciliation decision
logger.debug(
    "reconciliation_decision",
    cycle_id="01HXYZ...",
    phase="R3",
    event_id="evt_789",
    decision_type="REINFORCE",
    target_layer="st_sem",
    similarity_score=0.92,
    confidence_before=0.75,
    confidence_after=0.80
)

# ERROR: Write failure
logger.error(
    "truth_write_failed",
    cycle_id="01HXYZ...",
    phase="R7",
    target_layer="st_epi",
    error_code="CONSTRAINT_VIOLATION",
    error_message="Unique constraint violated on episode_id",
    affected_events=["evt_001", "evt_002"]
)
```

**Acceptance Criteria**:

- [ ] All P03 logs include required fields (cycle_id, phase, tenant_id, space_id)
- [ ] Logs emit as valid JSON via StructuredLogFormatter
- [ ] PII redaction applied to sensitive fields
- [ ] cognitive_trace_id automatically attached via filter
- [ ] Phase context bound/released correctly
- [ ] Log schema validator passes for all P03 log events

---

#### Issue 6.1.13 — Log Levels by Phase Matrix Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement phase-appropriate logging levels based on dossier specification.

**Dossier Reference**: [Section 8.4.2 Log Levels by Phase](../pipelines/P03_consolidation_dossier_v2.md#842-log-levels-by-phase)

**Phase-Level Matrix** (from dossier 8.4.2):

| Phase | INFO | DEBUG | WARN | ERROR |
| ----- | ---- | ----- | ---- | ----- |
| R0 | Cycle start, trigger type | Lock acquisition | Lock contention | Lock timeout |
| R1 | Batch size, importance range | Per-event scoring | Low-importance batch | Batch selection failed |
| R2 | Cluster count, avg size | Per-cluster details | Oversized clusters | Clustering failed |
| R3 | Duplicates found, pruned | Per-event decisions | High novelty conflicts | Dedup index error |
| R4 | Entities/edges created | Resolution details | Ambiguous entities | KG update failed |
| R5 | Insights generated | Counterfactual details | No insights found | Exploration error |
| R6 | Events updated | Per-event status | Update conflicts | Staging update failed |
| R7 | Records written | Per-layer counts | Retry scenarios | Write transaction failed |
| R8 | Events emitted, gaps detected | Per-event emission | Bus unavailable | Emission failed |

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| P03PhaseId | `k0/pipelines/p03/runner_contract.py` | Phase enum (R0-R8) |
| logger.info/debug/warning/error | Python logging | Standard log calls |
| Phase implementations | `k0/pipelines/p03/phases/*.py` | Existing logger.info calls |

**Work To Do**:

1. [ ] Create `P03LogLevelMatrix` constant mapping phase → event → level
2. [ ] Create `PhaseLogger` wrapper class that enforces level matrix
3. [ ] Implement `phase_info()`, `phase_debug()`, `phase_warn()`, `phase_error()` methods
4. [ ] Add `validate_log_level(phase, event_type, level)` method
5. [ ] Audit existing phase code for log level correctness
6. [ ] Update phase implementations to use PhaseLogger
7. [ ] Create tests validating log level enforcement

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/phase_logger.py
import logging
from enum import Enum
from typing import Dict, Set

class LogEventCategory(Enum):
    LIFECYCLE = "lifecycle"       # Start/end events
    METRICS = "metrics"           # Counts, sizes, durations
    DECISIONS = "decisions"       # Per-item decisions
    CONTENTION = "contention"     # Resource conflicts
    FAILURE = "failure"           # Errors and failures

# Define what should be INFO vs DEBUG per phase
PHASE_INFO_EVENTS: Dict[str, Set[str]] = {
    "R0": {"cycle_start", "trigger_type", "lock_acquired"},
    "R1": {"batch_size", "importance_range", "batch_selected"},
    "R2": {"cluster_count", "avg_cluster_size", "clustering_complete"},
    "R3": {"duplicates_found", "records_pruned", "dedup_complete"},
    "R4": {"entities_created", "edges_created", "kg_update_complete"},
    "R5": {"insights_generated", "exploration_complete"},
    "R6": {"events_updated", "staging_complete"},
    "R7": {"records_written", "layer_counts", "truth_write_complete"},
    "R8": {"events_emitted", "gaps_detected", "emission_complete"},
}

PHASE_DEBUG_EVENTS: Dict[str, Set[str]] = {
    "R0": {"lock_acquisition_attempt", "lock_wait_ms"},
    "R1": {"event_importance_score", "scoring_formula_used"},
    "R2": {"cluster_membership", "dbscan_params", "embedding_fetch"},
    "R3": {"dedup_decision", "novelty_score", "hamming_distance"},
    "R4": {"entity_resolution", "edge_discovery", "confidence_update"},
    "R5": {"counterfactual_detail", "simulation_step"},
    "R6": {"event_status_update", "staging_row"},
    "R7": {"layer_write_detail", "uow_transaction"},
    "R8": {"event_emission_detail", "gap_emission"},
}

class PhaseLogger:
    """Phase-aware logger that enforces log level matrix."""

    def __init__(self, phase: str, logger: logging.Logger):
        self._phase = phase
        self._logger = logger
        self._info_events = PHASE_INFO_EVENTS.get(phase, set())
        self._debug_events = PHASE_DEBUG_EVENTS.get(phase, set())

    def log_event(self, event_type: str, message: str, **kwargs):
        """Log event at appropriate level based on matrix."""
        if event_type in self._info_events:
            self._logger.info(message, extra={"event_type": event_type, **kwargs})
        elif event_type in self._debug_events:
            self._logger.debug(message, extra={"event_type": event_type, **kwargs})
        else:
            # Default to DEBUG for unlisted events
            self._logger.debug(message, extra={"event_type": event_type, **kwargs})
```

**Acceptance Criteria**:

- [ ] Log level matrix defined for all 9 phases
- [ ] PhaseLogger enforces correct levels
- [ ] INFO logs contain summary-level information
- [ ] DEBUG logs contain per-item details
- [ ] WARN logs for contention/conflict scenarios
- [ ] ERROR logs for failures with error context
- [ ] Integration test validates log levels per phase

---

#### Issue 6.1.14 — Cross-Space Leakage Detection Metrics

**Status**: 🔲 NOT STARTED

**Goal**: Implement metrics and monitoring for cross-space data leakage prevention.

**Dossier Reference**: [Section 8.1 Cross-Space Leakage Detection](../pipelines/P03_consolidation_dossier_v2.md#81-cross-space-leakage-detection)

**Security Context**:

- P03 operates on learning tables (st_learned_weights, st_consolidation_audit, st_pruned_entities)
- All learning data is space-scoped: `WHERE space_id = $current_space`
- PostgreSQL RLS (Row Level Security) enforces isolation at database level
- Application-level monitoring detects any bypass attempts

**Metrics to Implement**:

```python
# From dossier 8.1
# Should always be 0 - any value > 0 is critical alert
p03_cross_space_query_attempts = Counter(
    "p03_cross_space_query_attempts",
    "Attempted queries without space_id filter",
    ["table", "query_type"]  # table: st_learned_weights, etc.
)

# Track RLS enforcement activity
p03_rls_policy_blocks = Counter(
    "p03_rls_policy_blocks",
    "Queries blocked by RLS policy",
    ["table", "policy_name"]
)

# Isolation health indicator (1 = healthy, 0 = violation detected)
p03_isolation_health = Gauge(
    "p03_isolation_health",
    "1 if no violations detected, 0 otherwise"
)
```

**Learning Tables Requiring Protection**:

| Table | Purpose | RLS Policy |
| ----- | ------- | ---------- |
| `st_learned_weights` | Learned parameters per space | `space_id = current_setting('app.space_id')` |
| `st_consolidation_audit` | Audit trail per space | `space_id = current_setting('app.space_id')` |
| `st_pruned_entities` | Pruned entity records | `space_id = current_setting('app.space_id')` |
| `st_decay_feedback` | Decay feedback events | `space_id = current_setting('app.space_id')` |

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| ACLEnforcer | `k0/policy/acl_enforcer.py` | Permission check pattern |
| RLS migrations | `k0/storage/migrations/*.py` | `ENABLE ROW LEVEL SECURITY` |
| MetricsExporter | `k0/obs/metrics.py` | Counter, Gauge registration |

**Work To Do**:

1. [ ] Add `p03_cross_space_query_attempts`, `p03_rls_policy_blocks`, `p03_isolation_health` to P03MetricsRegistry
2. [ ] Create `CrossSpaceAuditor` class in `k0/pipelines/p03/ops/security.py`
3. [ ] Implement `audit_queries(time_window_hours)` to scan query logs
4. [ ] Implement `check_rls_policies()` to verify RLS is enabled
5. [ ] Implement `weekly_scan()` job for automated monitoring
6. [ ] Add query interception hook to detect missing space_id clauses
7. [ ] Create alert rules for p03_cross_space_query_attempts > 0
8. [ ] Create integration tests for isolation verification

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/security.py
class CrossSpaceAuditor:
    """Monitor and audit cross-space access attempts."""

    PROTECTED_TABLES = [
        "st_learned_weights",
        "st_consolidation_audit",
        "st_pruned_entities",
        "st_decay_feedback"
    ]

    async def audit_queries(self, db, time_window_hours: int = 168) -> list:
        """Scan pg_stat_statements for queries missing space_id filter."""
        violations = []
        for table in self.PROTECTED_TABLES:
            result = await db.fetch(f"""
                SELECT query, calls, userid
                FROM pg_stat_statements
                WHERE query ILIKE '%{table}%'
                  AND query NOT ILIKE '%space_id%'
                  AND query NOT ILIKE '%CREATE%'
                  AND query NOT ILIKE '%ALTER%'
            """)
            violations.extend(result)

        if violations:
            self._metrics.set_gauge("p03_isolation_health", 0)
            for v in violations:
                self._metrics.emit("p03_cross_space_query_attempts", 1,
                                   table=self._extract_table(v["query"]),
                                   query_type=self._classify_query(v["query"]))
        else:
            self._metrics.set_gauge("p03_isolation_health", 1)

        return violations

    async def check_rls_policies(self, db) -> dict:
        """Verify RLS is enabled on all protected tables."""
        results = {}
        for table in self.PROTECTED_TABLES:
            rls_enabled = await db.fetchval("""
                SELECT relrowsecurity FROM pg_class WHERE relname = $1
            """, table)
            results[table] = bool(rls_enabled)
            if not rls_enabled:
                # Critical: RLS not enabled
                self._metrics.set_gauge("p03_isolation_health", 0)
        return results
```

**Alert Configuration** (from dossier):

```yaml
# Alert if any cross-space attempt detected - CRITICAL
- alert: P03CrossSpaceLeakageDetected
  expr: p03_cross_space_query_attempts > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Cross-space data access attempt detected"
    description: "{{ $value }} attempts to access data across spaces"

# Alert if RLS blocks spike (may indicate application bug)
- alert: P03RLSBlockSpike
  expr: rate(p03_rls_policy_blocks[5m]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "RLS policy blocking spike detected"
```

**Acceptance Criteria**:

- [ ] All three cross-space metrics registered and functional
- [ ] CrossSpaceAuditor scans query logs correctly
- [ ] RLS policy verification runs on all protected tables
- [ ] `p03_isolation_health` gauge reflects actual state
- [ ] Critical alert triggers on any violation (count > 0)
- [ ] Integration test validates cross-space isolation

---

#### Issue 6.1.15 — Formula Debug Tracing (3-Level: User/Ops/Debug)

**Status**: 🔲 NOT STARTED

**Goal**: Implement three-level formula debug tracing for different audiences.

**Dossier Reference**: [Section 8.5.1 Formula Debug Tracing](../pipelines/P03_consolidation_dossier_v2.md#851-formula-debug-tracing)

**Trace Levels** (from dossier):

| Level | Audience | Content | Retention |
| ----- | -------- | ------- | --------- |
| User | End users | Natural language explanation | 90 days |
| Ops | Support team | Structured audit + decision path | 90 days |
| Debug | Developers | Full computation trace + intermediates | 7 days |

**Debug Trace Content**:

1. **Input Capture**: All input values, feature flags, space context, entity metadata
2. **Step-by-Step Computation**: Each formula step with intermediate results, threshold comparisons
3. **Performance Timing**: Time per step, database query time, total execution time
4. **Output Details**: Final decision, confidence, modified parameters, side effects

**Metrics to Implement**:

```python
p03_debug_traces_captured = Counter(
    "p03_debug_traces_captured",
    "Total debug traces captured",
    ["level", "formula"]  # level: user, ops, debug
)

p03_debug_trace_storage_bytes = Gauge(
    "p03_debug_trace_storage_bytes",
    "Storage used by debug traces",
    ["level"]
)

p03_debug_trace_sampling_rate = Gauge(
    "p03_debug_trace_sampling_rate",
    "Current sampling rate for debug traces"
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| P03ObservabilityContext | `k0/pipelines/p03/observability.py` | Trace context, timing |
| ObservabilityEmitter | `k0/obs/events.py` | Event buffering pattern |
| TracerFactory | `k0/obs/tracing.py` | Span attributes, trace IDs |
| FeatureFlags | `k0/config/feature_flags.py` | `P03_FF_DEBUG_TRACE_RATE` |

**Work To Do**:

1. [ ] Create `TraceLevel` enum: USER, OPS, DEBUG
2. [ ] Create `FormulaTracer` class in `k0/pipelines/p03/ops/formula_tracing.py`
3. [ ] Implement `trace_formula_execution(formula_name, level, context)` method
4. [ ] Implement `TraceContext` class for step-by-step capture
5. [ ] Implement `NoOpTraceContext` for when tracing is disabled
6. [ ] Add sampling logic: default 1%, configurable via `P03_FF_DEBUG_TRACE_RATE`
7. [ ] Always trace: errors, rollbacks, anomalies (bypass sampling)
8. [ ] Implement per-space override for 100% tracing
9. [ ] Add storage backend (st_formula_traces table or file-based)
10. [ ] Create tests validating trace capture and storage

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/formula_tracing.py
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List
import time
import random

class TraceLevel(Enum):
    USER = "user"      # Natural language, 90 days
    OPS = "ops"        # Structured audit, 90 days
    DEBUG = "debug"    # Full computation, 7 days

@dataclass
class TraceStep:
    step: int
    operation: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    duration_ms: float

@dataclass
class TraceContext:
    trace_id: str
    level: TraceLevel
    formula: str
    timestamp: int
    inputs: Dict[str, Any]
    steps: List[TraceStep] = field(default_factory=list)
    feature_flags: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    total_duration_ms: float = 0.0

    def add_step(self, operation: str, input_data: dict, output_data: dict, duration_ms: float):
        """Record a computation step."""
        self.steps.append(TraceStep(
            step=len(self.steps) + 1,
            operation=operation,
            input=input_data,
            output=output_data,
            duration_ms=duration_ms
        ))

    def finalize(self, output: dict, total_ms: float):
        """Finalize trace with output."""
        self.output = output
        self.total_duration_ms = total_ms

class FormulaTracer:
    """Capture formula execution traces at multiple levels."""

    DEFAULT_SAMPLE_RATE = 0.01  # 1%

    def __init__(self, metrics, storage, feature_flags):
        self._metrics = metrics
        self._storage = storage
        self._flags = feature_flags

    def should_trace(self, level: TraceLevel, is_error: bool = False) -> bool:
        """Determine if tracing should occur."""
        # Always trace errors
        if is_error:
            return True

        # Check space-specific override
        if self._flags.get("P03_FF_DEBUG_TRACE_ALL_SPACES"):
            return True

        # Apply sampling
        rate = self._flags.get("P03_FF_DEBUG_TRACE_RATE", self.DEFAULT_SAMPLE_RATE)
        return random.random() < rate

    async def trace_formula_execution(
        self,
        formula_name: str,
        level: TraceLevel,
        context: dict,
        is_error: bool = False,
    ) -> "TraceContext | NoOpTraceContext":
        """Create trace context for formula execution."""
        if not self.should_trace(level, is_error):
            return NoOpTraceContext()

        trace_id = f"trace_{uuid4().hex[:12]}"
        trace = TraceContext(
            trace_id=trace_id,
            level=level,
            formula=formula_name,
            timestamp=int(time.time() * 1000),
            inputs=context.get("inputs", {}),
            feature_flags=await self._get_active_flags(),
        )

        self._metrics.emit("p03_debug_traces_captured", 1,
                          level=level.value, formula=formula_name)

        return trace

    async def store_trace(self, trace: TraceContext):
        """Persist trace to storage backend."""
        await self._storage.insert_trace(trace)
```

**Debug Trace Example** (from dossier):

```json
{
  "trace_id": "trace_abc123",
  "level": "DEBUG",
  "formula": "hebbian_v2",
  "timestamp": 1734567890000,
  "inputs": {
    "entity_id": "ent_sarah_001",
    "entity_type": "PERSON",
    "access_count": 15
  },
  "steps": [
    {"step": 1, "operation": "calculate_cooccurrence", "output": {"cooccurrence_score": 0.75}, "duration_ms": 12},
    {"step": 2, "operation": "compare_threshold", "output": {"decision": "REINFORCE"}, "duration_ms": 1}
  ],
  "feature_flags": {"P03_FF_HEBBIAN_LEARNING": true},
  "output": {"action": "REINFORCE", "confidence": 0.85},
  "total_duration_ms": 45
}
```

**Acceptance Criteria**:

- [ ] Three trace levels implemented (User, Ops, Debug)
- [ ] FormulaTracer with configurable sampling rate
- [ ] Always-trace for errors/rollbacks/anomalies
- [ ] Per-space override capability
- [ ] Step-by-step computation capture
- [ ] Timing information at step and total level
- [ ] Storage with level-appropriate retention
- [ ] Metrics for trace capture and storage usage
- [ ] Integration test validates trace capture

---

#### Issue 6.1.16 — Formula Comparison Metrics (New vs Old Version)

**Status**: 🔲 NOT STARTED

**Goal**: Implement metrics for comparing formula performance between versions during shadow mode and canary rollout.

**Dossier Reference**: [Section 8.7 Formula Comparison Metrics](../pipelines/P03_consolidation_dossier_v2.md#87-formula-comparison-metrics)

**Purpose**: Data-driven rollout decisions based on measured outcomes prevent regressions from reaching production.

**Comparison Metrics to Implement** (from dossier 8.7):

| Metric | Success Criteria | Measurement | Data Source |
| ------ | ---------------- | ----------- | ----------- |
| Memory retrieval accuracy | New ≥ Old | P04 grounding rate | P04 query events |
| Decay calibration error | New < Old by > 5% | Regret signal rate | st_feedback_signals |
| Processing time | New ≤ Old × 1.1 | p99 latency | p03_formula_duration_ms |
| Edge case handling | No regressions | Error rate delta | p03_formula_errors |

**Metrics to Implement**:

```python
# Formula version comparison metrics
p03_formula_duration_ms = Histogram(
    "p03_formula_duration_ms",
    "Formula execution duration in milliseconds",
    ["formula", "version"],  # version: v1, v2, etc.
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000]
)

p03_formula_errors_total = Counter(
    "p03_formula_errors_total",
    "Total formula execution errors",
    ["formula", "version", "error_type"]
)

p03_formula_decisions_total = Counter(
    "p03_formula_decisions_total",
    "Total decisions made by formula version",
    ["formula", "version", "decision_type"]
)

p03_formula_comparison_divergence = Counter(
    "p03_formula_comparison_divergence",
    "Times old and new formula disagreed",
    ["formula", "old_decision", "new_decision"]
)

p03_prune_regrets_total = Counter(
    "p03_prune_regrets_total",
    "Pruned entities that were later accessed (regret events)",
    ["formula_version", "space_id"]
)

p03_entities_pruned_total = Counter(
    "p03_entities_pruned_total",
    "Total entities pruned",
    ["formula_version", "space_id"]
)
```

**PromQL Queries for Comparison** (from dossier):

```promql
# Memory retrieval accuracy comparison (P04 integration)
rate(p04_grounding_success_total{formula_version="v2"}[1h]) /
rate(p04_grounding_attempts_total{formula_version="v2"}[1h])
vs
rate(p04_grounding_success_total{formula_version="v1"}[1h]) /
rate(p04_grounding_attempts_total{formula_version="v1"}[1h])

# Decay calibration error (regret rate)
rate(p03_prune_regrets_total{formula_version="v2"}[24h]) /
rate(p03_entities_pruned_total{formula_version="v2"}[24h])

# Processing time comparison (p99 latency)
histogram_quantile(0.99,
  rate(p03_formula_duration_ms_bucket{formula_version="v2"}[15m])
)
vs
histogram_quantile(0.99,
  rate(p03_formula_duration_ms_bucket{formula_version="v1"}[15m])
)

# Error rate delta
rate(p03_formula_errors_total{formula_version="v2"}[1h]) -
rate(p03_formula_errors_total{formula_version="v1"}[1h])
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| ShadowModeComparator | `k0/pipelines/p03/phases/r5_exploration.py` | Shadow mode execution pattern |
| FeatureFlags | `k0/config/feature_flags.py` | `P03_FF_FORMULA_VERSION_*` flags |
| P03MetricsRegistry | `k0/pipelines/p03/ops/metrics.py` | Metric registration |
| FormulaTracer | `k0/pipelines/p03/ops/formula_tracing.py` | Step-by-step timing |

**Work To Do**:

1. [ ] Add `formula_version` label to all formula-related metrics
2. [ ] Create `FormulaComparator` class in `k0/pipelines/p03/ops/formula_comparison.py`
3. [ ] Implement `compare_versions(old_result, new_result)` method
4. [ ] Emit `p03_formula_comparison_divergence` when versions disagree
5. [ ] Implement statistical significance testing (Welch's t-test, p < 0.05)
6. [ ] Add minimum sample size check (1000 events per version)
7. [ ] Create comparison dashboard queries (see above PromQL)
8. [ ] Integrate with shadow mode feature flag: `P03_FF_FORMULA_VERSION_*`
9. [ ] Create tests for version comparison metrics

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/formula_comparison.py
from dataclasses import dataclass
from scipy import stats
from typing import Literal

@dataclass
class FormulaComparisonResult:
    formula: str
    old_version: str
    new_version: str
    metric_name: str
    old_value: float
    new_value: float
    p_value: float
    significant: bool
    winner: Literal["old", "new", "tie"]
    sample_size_old: int
    sample_size_new: int

class FormulaComparator:
    """Compare formula performance across versions."""

    MIN_SAMPLE_SIZE = 1000
    SIGNIFICANCE_THRESHOLD = 0.05

    def __init__(self, metrics_registry):
        self._metrics = metrics_registry

    def compare_latency(
        self,
        formula: str,
        old_version: str,
        new_version: str,
        old_samples: list[float],
        new_samples: list[float],
    ) -> FormulaComparisonResult:
        """Compare latency between versions using Welch's t-test."""
        if len(old_samples) < self.MIN_SAMPLE_SIZE or len(new_samples) < self.MIN_SAMPLE_SIZE:
            return FormulaComparisonResult(
                formula=formula,
                old_version=old_version,
                new_version=new_version,
                metric_name="latency_p99",
                old_value=0,
                new_value=0,
                p_value=1.0,
                significant=False,
                winner="tie",
                sample_size_old=len(old_samples),
                sample_size_new=len(new_samples),
            )

        # Welch's t-test for unequal variances
        t_stat, p_value = stats.ttest_ind(old_samples, new_samples, equal_var=False)

        old_p99 = np.percentile(old_samples, 99)
        new_p99 = np.percentile(new_samples, 99)

        # New wins if faster and significant (lower is better)
        significant = p_value < self.SIGNIFICANCE_THRESHOLD
        if not significant:
            winner = "tie"
        elif new_p99 < old_p99:
            winner = "new"
        else:
            winner = "old"

        return FormulaComparisonResult(
            formula=formula,
            old_version=old_version,
            new_version=new_version,
            metric_name="latency_p99",
            old_value=old_p99,
            new_value=new_p99,
            p_value=p_value,
            significant=significant,
            winner=winner,
            sample_size_old=len(old_samples),
            sample_size_new=len(new_samples),
        )

    def emit_divergence(
        self,
        formula: str,
        old_decision: str,
        new_decision: str,
    ) -> None:
        """Record when versions produce different decisions."""
        self._metrics.emit(
            "p03_formula_comparison_divergence", 1,
            formula=formula,
            old_decision=old_decision,
            new_decision=new_decision,
        )
```

**Statistical Significance Requirements** (from dossier):

- Require p < 0.05 (95% confidence) before declaring winner
- Use Welch's t-test for unequal variances
- Minimum sample size: 1000 events per version
- Anomaly highlighting: automatic detection of regressions > 5%

**Acceptance Criteria**:

- [ ] All formula metrics include `formula_version` label
- [ ] FormulaComparator implements statistical comparison
- [ ] Welch's t-test with p < 0.05 threshold
- [ ] Minimum sample size enforcement (1000 events)
- [ ] Divergence counter tracks disagreements
- [ ] Regret rate calculable from prune/regret metrics
- [ ] Integration test validates comparison logic

---

#### Issue 6.1.17 — Grafana Dashboard Definitions

**Status**: 🔲 NOT STARTED

**Goal**: Create Grafana dashboard JSON definitions for P03 observability.

**Dossier Reference**: [Section 8.5 Dashboards](../pipelines/P03_consolidation_dossier_v2.md#85-dashboards)

**Dashboards to Implement**:

| Dashboard | Purpose | Key Panels |
| --------- | ------- | ---------- |
| P03 Health | Cycle health overview | Success rate, duration, pending queue |
| Memory Growth | Layer size tracking | Records by layer, creation vs archival |
| Active Learning | Gap detection/resolution | Gaps detected, gap types, resolution rate |
| Learning Performance | Learning budget tracking | Budget %, queue depth, latency |
| Formula Comparison | Version comparison | Side-by-side metrics, divergence |

**Dashboard Locations**:

```text
k0/pipelines/p03/ops/dashboards/
├── p03_health.json
├── p03_memory_growth.json
├── p03_active_learning.json
├── p03_learning_performance.json
└── p03_formula_comparison.json
```

**Dashboard 1: P03 Health** (from dossier 8.5.1):

```yaml
dashboard:
  title: "P03 Consolidation Health"
  uid: "p03-health"
  tags: ["p03", "consolidation", "health"]

  templating:
    - name: tenant_id
      type: query
      query: "label_values(p03_cycle_total, tenant_id)"

  rows:
    - title: "Cycle Overview"
      panels:
        - type: stat
          title: "Cycles (24h)"
          query: 'sum(increase(p03_cycle_total{tenant_id="$tenant_id"}[24h]))'

        - type: gauge
          title: "Success Rate"
          query: |
            sum(rate(p03_cycle_total{status="success",tenant_id="$tenant_id"}[1h])) /
            sum(rate(p03_cycle_total{tenant_id="$tenant_id"}[1h]))
          thresholds:
            - value: 0.9
              color: red
            - value: 0.95
              color: yellow
            - value: 0.99
              color: green

        - type: timeseries
          title: "Cycle Duration (p95)"
          query: 'histogram_quantile(0.95, rate(p03_cycle_duration_seconds_bucket{tenant_id="$tenant_id"}[5m]))'

    - title: "Event Processing"
      panels:
        - type: timeseries
          title: "Events Processed/Hour"
          query: 'sum(rate(p03_events_processed_total{tenant_id="$tenant_id"}[1h])) * 3600'

        - type: gauge
          title: "Pending Queue"
          query: 'sum(p03_pending_events{tenant_id="$tenant_id"})'
          thresholds:
            - value: 1000
              color: green
            - value: 5000
              color: yellow
            - value: 10000
              color: red

    - title: "Decisions"
      panels:
        - type: piechart
          title: "Decision Distribution"
          query: 'sum by (decision_type) (increase(p03_decisions_total{tenant_id="$tenant_id"}[24h]))'
```

**Dashboard 2: Memory Growth** (from dossier 8.5.2):

```yaml
dashboard:
  title: "Memory Layer Growth"
  uid: "p03-memory-growth"

  rows:
    - title: "Layer Sizes"
      panels:
        - type: timeseries
          title: "Records by Layer"
          query: 'sum by (layer) (p03_layer_size{archival_status="ACTIVE"})'

        - type: timeseries
          title: "Creation vs Archival Rate"
          queries:
            - 'sum(rate(p03_layer_records_total{operation="create"}[1h])) as "Creation"'
            - 'sum(rate(p03_layer_records_total{operation="archive"}[1h])) as "Archival"'

    - title: "Quality Metrics"
      panels:
        - type: gauge
          title: "Avg Confidence (st_sem)"
          query: 'avg(p03_layer_avg_confidence{layer="st_sem"})'

        - type: heatmap
          title: "Decay Factor Distribution"
          query: 'p03_layer_avg_decay'
```

**Dashboard 3: Active Learning** (from dossier 8.5.3):

```yaml
dashboard:
  title: "Active Learning Integration"
  uid: "p03-active-learning"

  rows:
    - title: "Gap Detection"
      panels:
        - type: timeseries
          title: "Gaps Detected/Day"
          query: 'sum(increase(p03_gaps_detected_total[24h]))'

        - type: piechart
          title: "Gap Types"
          query: 'sum by (gap_type) (p03_gaps_pending)'

    - title: "Resolution"
      panels:
        - type: stat
          title: "Resolution Rate"
          query: |
            sum(rate(p06_gaps_resolved_total[24h])) /
            sum(rate(p03_gaps_detected_total[24h]))

        - type: timeseries
          title: "Pending Gap Queue"
          query: 'sum(p03_gaps_pending{status="PENDING"})'
```

**Dashboard 4: Learning Performance** (from dossier 8.2.5):

```yaml
dashboard:
  title: "P03 Learning Performance"
  uid: "p03-learning-performance"

  rows:
    - title: "Budget Overview"
      panels:
        - type: gauge
          title: "Learning Time %"
          query: 'sum(p03_learning_time_pct)'
          thresholds:
            - value: 4
              color: green
            - value: 5
              color: red

        - type: barchart
          title: "Budget by Component"
          query: 'sum by (component) (p03_learning_time_pct)'

        - type: timeseries
          title: "Skip Rate"
          query: 'rate(p03_learning_skip_count[1h])'

    - title: "Queue Health"
      panels:
        - type: gauge
          title: "Queue Depth"
          query: 'p03_learning_queue_depth'
          thresholds:
            - value: 500
              color: green
            - value: 1000
              color: red

        - type: timeseries
          title: "Overflow Rate"
          query: 'rate(p03_learning_queue_overflow[5m])'

    - title: "Operation Performance"
      panels:
        - type: timeseries
          title: "Latency p99 by Operation"
          query: 'histogram_quantile(0.99, rate(p03_learning_latency_ms_bucket[5m]))'
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| K0 dashboard templates | `k0/ops/dashboards/` | JSON structure pattern |
| Grafana provisioning | `docker/grafana/provisioning/` | Dashboard provisioning |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/ops/dashboards/` directory
2. [ ] Implement `p03_health.json` with cycle overview, events, decisions
3. [ ] Implement `p03_memory_growth.json` with layer sizes, quality metrics
4. [ ] Implement `p03_active_learning.json` with gap detection, resolution
5. [ ] Implement `p03_learning_performance.json` with budget, queue, latency
6. [ ] Implement `p03_formula_comparison.json` with side-by-side version metrics
7. [ ] Add tenant_id and space_id template variables to all dashboards
8. [ ] Create alerting panel annotations linked to Issue 6.1.18 rules
9. [ ] Add dashboard provisioning to Docker Compose configuration
10. [ ] Create validation script to verify dashboard JSON syntax

**Acceptance Criteria**:

- [ ] All 5 dashboards created as valid Grafana JSON
- [ ] Dashboards use consistent styling and layout
- [ ] Template variables for tenant_id and space_id filtering
- [ ] All metrics from dossier 8.2 represented in appropriate dashboard
- [ ] Threshold colors match dossier specifications
- [ ] Dashboards import successfully into Grafana

---

#### Issue 6.1.18 — Alerting Rules Configuration

**Status**: 🔲 NOT STARTED

**Goal**: Define Prometheus alerting rules for P03 operational monitoring.

**Dossier Reference**: [Section 8.6 Alerting Rules](../pipelines/P03_consolidation_dossier_v2.md#86-alerting-rules)

**Alert Categories**:

| Category | Severity | Focus |
| -------- | -------- | ----- |
| Cycle Health | warning/critical | Failure rate, duration |
| Queue Health | warning/info | Pending events, gap queue |
| Learning Budget | warning/critical | Budget exceeded, queue overflow |
| Security | critical | Cross-space leakage |
| Performance | warning | Latency thresholds |

**Alert Rules File Location**:

```text
k0/pipelines/p03/config/alerts/
└── p03_alerts.yaml
```

**Alert Rules to Implement** (from dossier 8.6):

```yaml
# k0/pipelines/p03/config/alerts/p03_alerts.yaml
groups:
  - name: p03_cycle_alerts
    rules:
      # Cycle failure rate above 10%
      - alert: P03CycleFailureRate
        expr: |
          sum(rate(p03_cycle_total{status="failure"}[1h])) /
          sum(rate(p03_cycle_total[1h])) > 0.1
        for: 15m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 cycle failure rate above 10%"
          description: "Cycle failure rate is {{ $value | humanizePercentage }} over the last hour"
          runbook_url: "https://docs.familyos/runbooks/p03-cycle-failures"

      # Cycle failure rate above 25% - critical
      - alert: P03CycleFailureRateCritical
        expr: |
          sum(rate(p03_cycle_total{status="failure"}[1h])) /
          sum(rate(p03_cycle_total[1h])) > 0.25
        for: 10m
        labels:
          severity: critical
          pipeline: p03
        annotations:
          summary: "P03 cycle failure rate critically high"
          description: "Cycle failure rate is {{ $value | humanizePercentage }}"

      # Cycle duration p95 above 5 minutes
      - alert: P03CycleDurationHigh
        expr: |
          histogram_quantile(0.95, rate(p03_cycle_duration_seconds_bucket[15m])) > 300
        for: 30m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 cycle p95 duration above 5 minutes"
          description: "p95 cycle duration is {{ $value | humanizeDuration }}"

  - name: p03_queue_alerts
    rules:
      # Pending event queue above 10K
      - alert: P03PendingQueueHigh
        expr: sum(p03_pending_events) > 10000
        for: 30m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "P03 pending event queue above 10K"
          description: "{{ $value }} events pending consolidation"

      # Gap queue above 500
      - alert: P03GapQueueOverflow
        expr: sum(p03_gaps_pending{status="PENDING"}) > 500
        for: 1h
        labels:
          severity: info
          pipeline: p03
        annotations:
          summary: "P03 gap queue above 500 pending items"
          description: "{{ $value }} gaps waiting for P06 resolution"

  - name: p03_learning_alerts
    rules:
      # Learning budget exceeded
      - alert: P03LearningBudgetExceeded
        expr: p03_learning_time_pct > 5
        for: 5m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "Learning operations exceed 5% budget"
          description: "Space {{ $labels.space_id }} learning at {{ $value }}%"

      # Learning skip rate high
      - alert: P03LearningSkipRateHigh
        expr: rate(p03_learning_skip_count[1h]) > 10
        for: 15m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "High learning operation skip rate"
          description: "{{ $value }} operations/hour skipped due to budget"

      # Learning queue overflowing
      - alert: P03LearningQueueOverflow
        expr: rate(p03_learning_queue_overflow[5m]) > 50
        for: 5m
        labels:
          severity: critical
          pipeline: p03
        annotations:
          summary: "Learning queue overflowing"
          description: "{{ $value }} signals/min discarded"

  - name: p03_security_alerts
    rules:
      # Cross-space leakage detected - CRITICAL
      - alert: P03CrossSpaceLeakageDetected
        expr: p03_cross_space_query_attempts > 0
        for: 1m
        labels:
          severity: critical
          pipeline: p03
          security: true
        annotations:
          summary: "Cross-space data access attempt detected"
          description: "{{ $value }} attempts to access data across spaces"
          runbook_url: "https://docs.familyos/runbooks/p03-security-incident"

      # RLS policy blocks spike
      - alert: P03RLSBlockSpike
        expr: rate(p03_rls_policy_blocks[5m]) > 10
        for: 5m
        labels:
          severity: warning
          pipeline: p03
        annotations:
          summary: "RLS policy blocking spike detected"
          description: "{{ $value }} blocks/second - may indicate application bug"

  - name: p03_performance_alerts
    rules:
      # Phase latency exceeded (per phase targets from dossier)
      - alert: P03R0LatencyHigh
        expr: |
          histogram_quantile(0.95, rate(p03_phase_duration_seconds_bucket{phase="R0"}[5m])) > 0.1
        for: 15m
        labels:
          severity: warning
          pipeline: p03
          phase: R0
        annotations:
          summary: "R0 (Fetch) p95 latency above 100ms target"

      - alert: P03R3LatencyHigh
        expr: |
          histogram_quantile(0.95, rate(p03_phase_duration_seconds_bucket{phase="R3"}[5m])) > 2
        for: 15m
        labels:
          severity: warning
          pipeline: p03
          phase: R3
        annotations:
          summary: "R3 (Reconciliation) p95 latency above 2s target"

      - alert: P03R7LatencyHigh
        expr: |
          histogram_quantile(0.95, rate(p03_phase_duration_seconds_bucket{phase="R7"}[5m])) > 1
        for: 15m
        labels:
          severity: warning
          pipeline: p03
          phase: R7
        annotations:
          summary: "R7 (Truth Write) p95 latency above 1s target"
```

**Alert Thresholds Summary** (from dossier):

| Metric | Warning | Critical | Action |
| ------ | ------- | -------- | ------ |
| Cycle failure rate | > 10% | > 25% | Investigate errors |
| Cycle duration p95 | > 300s | > 600s | Check phase bottlenecks |
| Pending queue | > 10K | > 50K | Scale up or throttle intake |
| Learning time % | > 4% | > 5% | Investigate slow operations |
| Learning queue overflow | > 10/min | > 50/min | Increase queue size |
| Cross-space attempts | > 0 | - | Security incident |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/config/alerts/` directory
2. [ ] Implement `p03_alerts.yaml` with all alert groups
3. [ ] Define cycle health alerts (failure rate, duration)
4. [ ] Define queue health alerts (pending, gaps)
5. [ ] Define learning budget alerts (exceeded, skip rate, overflow)
6. [ ] Define security alerts (cross-space leakage, RLS blocks)
7. [ ] Define per-phase latency alerts (R0-R8 targets from dossier)
8. [ ] Add runbook URLs for critical alerts
9. [ ] Add alert provisioning to Prometheus configuration
10. [ ] Create validation script for alert YAML syntax

**Existing Code to Leverage**:

| Component | Path | What to Use |
| --------- | ---- | ----------- |
| K0 alert templates | `k0/ops/alerts/` | YAML structure pattern |
| Prometheus config | `docker/prometheus/` | Alert rule provisioning |

**Acceptance Criteria**:

- [ ] All alert categories from dossier 8.6 implemented
- [ ] Alert severity labels consistent (info, warning, critical)
- [ ] `for` duration appropriate for each alert (avoid flapping)
- [ ] Annotations include summary, description, runbook_url
- [ ] Alert YAML passes promtool check rules validation
- [ ] Alerts integrate with Alertmanager routing

---

#### Issue 6.1.19 — Observability Unit and Integration Tests

**Status**: 🔲 NOT STARTED

**Goal**: Implement comprehensive test coverage for all P03 observability components.

**Dossier Reference**: Validation of sections 8.1-8.7

**Test Files to Create**:

```text
tests/k0/pipelines/p03/
├── test_p03_metrics_registry.py        # 6.1.1 - Metrics registry
├── test_p03_cycle_metrics.py           # 6.1.2 - Cycle metrics
├── test_p03_phase_histograms.py        # 6.1.3 - Phase timing
├── test_p03_decision_metrics.py        # 6.1.4 - Decision metrics
├── test_p03_gap_metrics.py             # 6.1.5 - Gap metrics
├── test_p03_layer_metrics.py           # 6.1.6 - Layer metrics
├── test_p03_module_metrics.py          # 6.1.7 - Module metrics
├── test_p03_shadow_mode_metrics.py     # 6.1.8 - Shadow mode metrics
├── test_p03_decay_metrics.py           # 6.1.9 - Decay metrics
├── test_p03_tracing.py                 # 6.1.10-6.1.11 - Tracing + propagation
├── test_p03_structured_logging.py      # 6.1.12-6.1.13 - Logging + levels
├── test_p03_cross_space_metrics.py     # 6.1.14 - Cross-space detection
├── test_p03_formula_tracing.py         # 6.1.15 - Formula debug tracing
├── test_p03_formula_comparison.py      # 6.1.16 - Version comparison
├── test_p03_dashboards.py              # 6.1.17 - Dashboard JSON validation
├── test_p03_alerts.py                  # 6.1.18 - Alert YAML validation
└── integration/
    └── test_p03_observability_integration.py  # End-to-end observability
```

**Existing Test Patterns to Follow**:

| Test File | Path | Pattern to Reuse |
| --------- | ---- | ---------------- |
| test_r1_metrics.py | `tests/k0/pipelines/p03/test_r1_metrics.py` | Metric assertion patterns |
| test_p03_envelope.py | `tests/k0/pipelines/p03/test_p03_envelope.py` | Observability context testing |
| test_p03_qos_integration.py | `tests/k0/pipelines/p03/test_p03_qos_integration.py` | K0 integration patterns |

**Test Categories**:

**1. Metrics Registry Tests** (`test_p03_metrics_registry.py`):

```python
class TestP03MetricsRegistry:
    def test_register_all_idempotent(self):
        """Calling register_all() multiple times is safe."""
        ...

    def test_all_metrics_registered(self):
        """All dossier 8.2 metrics are registered."""
        ...

    def test_metrics_emit_correctly(self):
        """Metrics emit with correct labels."""
        ...

    def test_k0_exporter_integration(self):
        """P03 metrics appear in K0 MetricsExporter."""
        ...
```

**2. Phase Histogram Tests** (`test_p03_phase_histograms.py`):

```python
class TestPhaseHistograms:
    @pytest.mark.parametrize("phase", ["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"])
    def test_phase_duration_histogram(self, phase):
        """Each phase emits duration histogram."""
        ...

    def test_bucket_boundaries(self):
        """Histogram buckets match dossier specification."""
        ...

    def test_latency_targets(self):
        """Phase latencies within targets (for baseline)."""
        ...
```

**3. Tracing Tests** (`test_p03_tracing.py`):

```python
class TestP03Tracing:
    def test_span_hierarchy(self):
        """Spans follow dossier 8.3.1 hierarchy."""
        ...

    def test_baggage_propagation(self):
        """cycle_id, tenant_id, space_id baggage propagates."""
        ...

    def test_trace_context_injection(self):
        """Trace context injected into bus events."""
        ...

    def test_trace_context_extraction(self):
        """Trace context extracted from incoming events."""
        ...
```

**4. Logging Tests** (`test_p03_structured_logging.py`):

```python
class TestStructuredLogging:
    def test_log_schema_compliance(self):
        """Logs match P03_LOG_SCHEMA from dossier 8.4.1."""
        ...

    def test_pii_redaction(self):
        """Sensitive fields redacted by K0 formatter."""
        ...

    def test_log_levels_by_phase(self):
        """Log levels match dossier 8.4.2 matrix."""
        ...

    def test_log_context_binding(self):
        """P03 context bound to all logs in cycle."""
        ...
```

**5. Dashboard/Alert Validation Tests**:

```python
# test_p03_dashboards.py
class TestDashboardValidation:
    @pytest.mark.parametrize("dashboard", [
        "p03_health.json",
        "p03_memory_growth.json",
        "p03_active_learning.json",
        "p03_learning_performance.json",
        "p03_formula_comparison.json",
    ])
    def test_dashboard_valid_json(self, dashboard):
        """Dashboard JSON is syntactically valid."""
        ...

    def test_dashboard_has_required_panels(self):
        """Dashboard contains expected panels from dossier."""
        ...

    def test_dashboard_queries_reference_existing_metrics(self):
        """All PromQL queries reference registered metrics."""
        ...

# test_p03_alerts.py
class TestAlertValidation:
    def test_alerts_valid_yaml(self):
        """Alert YAML is syntactically valid."""
        ...

    def test_promtool_check_rules(self):
        """Alerts pass promtool check rules."""
        ...

    def test_all_dossier_alerts_present(self):
        """All alerts from dossier 8.6 are defined."""
        ...
```

**6. Integration Tests** (`test_p03_observability_integration.py`):

```python
class TestObservabilityIntegration:
    @pytest.mark.integration
    async def test_full_cycle_emits_metrics(self):
        """Complete cycle run emits all expected metrics."""
        ...

    @pytest.mark.integration
    async def test_trace_spans_created(self):
        """Complete cycle creates expected span tree."""
        ...

    @pytest.mark.integration
    async def test_logs_contain_context(self):
        """All logs during cycle contain P03 context."""
        ...

    @pytest.mark.integration
    async def test_metrics_visible_prometheus_endpoint(self):
        """P03 metrics appear on /metrics scrape endpoint."""
        ...
```

**Work To Do**:

1. [ ] Create test file structure as defined above
2. [ ] Implement `test_p03_metrics_registry.py` (Issue 6.1.1 validation)
3. [ ] Implement `test_p03_cycle_metrics.py` (Issue 6.1.2 validation)
4. [ ] Implement `test_p03_phase_histograms.py` (Issue 6.1.3 validation)
5. [ ] Implement `test_p03_decision_metrics.py` (Issue 6.1.4 validation)
6. [ ] Implement `test_p03_gap_metrics.py` (Issue 6.1.5 validation)
7. [ ] Implement `test_p03_layer_metrics.py` (Issue 6.1.6 validation)
8. [ ] Implement `test_p03_module_metrics.py` (Issue 6.1.7 validation)
9. [ ] Implement `test_p03_shadow_mode_metrics.py` (Issue 6.1.8 validation)
10. [ ] Implement `test_p03_decay_metrics.py` (Issue 6.1.9 validation)
11. [ ] Implement `test_p03_tracing.py` (Issues 6.1.10-6.1.11 validation)
12. [ ] Implement `test_p03_structured_logging.py` (Issues 6.1.12-6.1.13 validation)
13. [ ] Implement `test_p03_cross_space_metrics.py` (Issue 6.1.14 validation)
14. [ ] Implement `test_p03_formula_tracing.py` (Issue 6.1.15 validation)
15. [ ] Implement `test_p03_formula_comparison.py` (Issue 6.1.16 validation)
16. [ ] Implement `test_p03_dashboards.py` (Issue 6.1.17 validation)
17. [ ] Implement `test_p03_alerts.py` (Issue 6.1.18 validation)
18. [ ] Implement `test_p03_observability_integration.py` (end-to-end)
19. [ ] Ensure ≥90% coverage for observability modules
20. [ ] Run all tests in CI pipeline

**Acceptance Criteria**:

- [ ] All 18 test files created and passing
- [ ] ≥90% code coverage for `k0/pipelines/p03/ops/` module
- [ ] Integration tests validate end-to-end metric emission
- [ ] Dashboard JSON validation passes
- [ ] Alert YAML validation passes
- [ ] Tests run in CI with < 5 minute runtime
- [ ] No flaky tests (all deterministic)

---

### Epic 6.2 — DLQ + Retries + Circuit Breakers

> **Scope**: Implement error handling, retry logic, and circuit breakers for resilience.
>
> **Dossier Reference**: Section 13 "Error Handling & Dead Letter Queue"

#### Epic 6.2 Issues Summary

| Issue | Title | Goal |
|-------|-------|------|
| 6.2.1 | ErrorClassifier implementation | Error classification logic |
| 6.2.2 | P03ErrorHandler core implementation | Central error handler |
| 6.2.3 | DLQRecord and DLQStore P03 integration | DLQ persistence |
| 6.2.4 | P03RetryConfig and RetryScheduler integration | Phase-aware retry |
| 6.2.5 | P03CircuitBreaker base implementation | Circuit breaker state machine |
| 6.2.6 | P08 embedding circuit breaker | P08 coordination protection |
| 6.2.7 | Bus dispatcher circuit breaker | Event bus protection |
| 6.2.8 | FAISS index circuit breaker | FAISS fallback |
| 6.2.9 | Partial failure handling strategies | COMMIT_PARTIAL/ROLLBACK_ALL |
| 6.2.10 | st_feedback_quarantine schema | Quarantine table |
| 6.2.11 | QuarantineDetector implementation | Suspicious signal detection |
| 6.2.12 | FeedbackRateLimiter implementation | Rate limiting |
| 6.2.13 | VelocityAnomalyDetector implementation | Spike detection |
| 6.2.14 | Quarantine auto-release job | 48h auto-release |
| 6.2.15 | Manual quarantine review API | Review capability |
| 6.2.16 | k0ctl dlq commands for P03 | CLI commands |
| 6.2.17 | P03LearningAnomalyDetector | Learning anomaly detection |
| 6.2.18 | Edge case handling implementation | Edge case handlers |
| 6.2.19 | Quarantine metrics implementation | Quarantine metrics |
| 6.2.20 | DLQ + retry integration tests | Test coverage |

---

#### Issue 6.2.1 — ErrorClassifier Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement error classification logic to categorize exceptions into TRANSIENT, VALIDATION, LOGIC, or FATAL for routing decisions.

**Dossier Reference**: [Section 13.2 Error Classification](../pipelines/P03_consolidation_dossier_v2.md#132-error-classification)

**Error Classification Matrix** (from dossier 13.2):

| Error Type | Severity | K0 Component | Retry Strategy | Example |
|------------|----------|--------------|----------------|---------|
| **TRANSIENT** | Low | RetryScheduler | Yes (exponential backoff) | DB connection timeout, lock contention |
| **VALIDATION** | Medium | DLQ → st_dlq | No (DLQ) | Schema mismatch, constraint violation |
| **LOGIC** | High | DLQ + ObsEmitter | No (DLQ + alert) | Reconciliation logic failure |
| **FATAL** | Critical | Circuit Breaker | No (abort cycle) | Out of memory, disk full |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03ErrorType enum | `k0/pipelines/p03/runner_contract.py` | DB_TIMEOUT, LOCK_TIMEOUT, VERSION_CONFLICT types |
| P03Error dataclass | `k0/pipelines/p03/observability.py` | error_type, recoverable fields |
| RetryDecision | `k0/outbox/scheduler.py` | action (retry/quarantine) field |
| DeadLetter.state | `k0/storage/dlq.py` | PENDING, REQUEUED, QUARANTINED states |

**Work To Do**:

1. [ ] Create `P03ErrorCategory` enum in `k0/pipelines/p03/ops/error_classifier.py`
2. [ ] Define `TRANSIENT_EXCEPTIONS` frozenset (ConnectionError, TimeoutError, asyncpg.PostgresConnectionError, etc.)
3. [ ] Define `VALIDATION_EXCEPTIONS` frozenset (ValidationError, SchemaError, pydantic.ValidationError, etc.)
4. [ ] Define `FATAL_EXCEPTIONS` frozenset (MemoryError, OSError with disk full, SystemExit, etc.)
5. [ ] Implement `ErrorClassifier.classify(error: Exception) -> P03ErrorCategory` method
6. [ ] Implement `ErrorClassifier.is_retriable(error: Exception) -> bool` method
7. [ ] Map `P03ErrorType` enum values to `P03ErrorCategory` for typed errors
8. [ ] Add phase-specific classification overrides (R7 version conflicts → TRANSIENT)
9. [ ] Create unit tests for all error type mappings

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/error_classifier.py
from enum import Enum
from typing import FrozenSet, Type
import asyncpg

class P03ErrorCategory(Enum):
    """Error categories for routing decisions."""
    TRANSIENT = "TRANSIENT"    # Retry via RetryScheduler
    VALIDATION = "VALIDATION"  # DLQ, no retry
    LOGIC = "LOGIC"            # DLQ + alert
    FATAL = "FATAL"            # Circuit breaker, abort cycle

# Exception types that are transient (retriable)
TRANSIENT_EXCEPTIONS: FrozenSet[Type[Exception]] = frozenset({
    ConnectionError,
    TimeoutError,
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    asyncpg.TooManyConnectionsError,
})

# Exception types that are validation errors (DLQ, no retry)
VALIDATION_EXCEPTIONS: FrozenSet[Type[Exception]] = frozenset({
    ValueError,
    TypeError,
    asyncpg.DataError,
    asyncpg.IntegrityConstraintViolationError,
    asyncpg.CheckViolationError,
})

# Exception types that are fatal (abort cycle)
FATAL_EXCEPTIONS: FrozenSet[Type[Exception]] = frozenset({
    MemoryError,
    SystemExit,
    KeyboardInterrupt,
    asyncpg.InternalServerError,
})

class ErrorClassifier:
    """Classify exceptions for routing to retry, DLQ, or abort."""

    # P03ErrorType → P03ErrorCategory mapping
    ERROR_TYPE_MAPPING = {
        P03ErrorType.DB_TIMEOUT: P03ErrorCategory.TRANSIENT,
        P03ErrorType.LOCK_TIMEOUT: P03ErrorCategory.TRANSIENT,
        P03ErrorType.POOL_EXHAUSTED: P03ErrorCategory.TRANSIENT,
        P03ErrorType.R6_VERSION_CONFLICT: P03ErrorCategory.TRANSIENT,
        P03ErrorType.R7_VERSION_CONFLICT: P03ErrorCategory.TRANSIENT,
        P03ErrorType.R6_UNIQUE_VIOLATION: P03ErrorCategory.VALIDATION,
        P03ErrorType.R6_MANIFEST_INVALID: P03ErrorCategory.VALIDATION,
        P03ErrorType.R7_TRANSACTION_FAILED: P03ErrorCategory.LOGIC,
        P03ErrorType.GENERIC: P03ErrorCategory.LOGIC,
    }

    def classify(self, error: Exception) -> P03ErrorCategory:
        """Classify exception into routing category."""
        # Check typed P03 errors first
        if hasattr(error, 'error_type') and isinstance(error.error_type, P03ErrorType):
            return self.ERROR_TYPE_MAPPING.get(
                error.error_type, P03ErrorCategory.LOGIC
            )

        # Check exception type hierarchy
        for exc_type in FATAL_EXCEPTIONS:
            if isinstance(error, exc_type):
                return P03ErrorCategory.FATAL

        for exc_type in TRANSIENT_EXCEPTIONS:
            if isinstance(error, exc_type):
                return P03ErrorCategory.TRANSIENT

        for exc_type in VALIDATION_EXCEPTIONS:
            if isinstance(error, exc_type):
                return P03ErrorCategory.VALIDATION

        # Default to LOGIC (DLQ + alert)
        return P03ErrorCategory.LOGIC

    def is_retriable(self, error: Exception) -> bool:
        """Check if error should be retried."""
        return self.classify(error) == P03ErrorCategory.TRANSIENT
```

**Phase-Specific Overrides**:

| Phase | Error | Default Category | Override Category | Reason |
|-------|-------|------------------|-------------------|--------|
| R6 | UniqueViolationError | VALIDATION | TRANSIENT (1 retry) | Concurrent staging race |
| R7 | VersionConflictError | VALIDATION | TRANSIENT (3 retries) | Optimistic locking race |
| R7 | TransactionFailedError | LOGIC | TRANSIENT (1 retry) | Deadlock recovery |

**Acceptance Criteria**:

- [ ] All 4 error categories (TRANSIENT, VALIDATION, LOGIC, FATAL) implemented
- [ ] TRANSIENT exceptions correctly identified for retry
- [ ] VALIDATION exceptions routed to DLQ without retry
- [ ] FATAL exceptions trigger circuit breaker / abort
- [ ] P03ErrorType enum values correctly mapped to categories
- [ ] Phase-specific overrides implemented for R6/R7
- [ ] Unit tests cover all exception type mappings
- [ ] classify() returns LOGIC for unknown exceptions (safe default)

---

#### Issue 6.2.2 — P03ErrorHandler Core Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement central error handler that routes errors to retry scheduler, DLQ, or circuit breaker based on classification.

**Dossier Reference**: [Section 13.3 K0 DLQ Integration](../pipelines/P03_consolidation_dossier_v2.md#133-k0-dlq-integration)

**Error Handler Flow** (from dossier 13.1):

```
Phase Error → P03ErrorHandler.handle_error()
                    │
                    ▼
           ErrorClassifier.classify(error)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   TRANSIENT    VALIDATION   LOGIC/FATAL
        │           │           │
        ▼           ▼           ▼
 RetryScheduler  DLQ.record  DLQ.record +
   .decide()       ()        ObsEmitter.emit
        │                       │
        ▼                       ▼
   retry/DLQ             alert triggered
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| DeadLetterQueue | `k0/storage/dlq.py` | record(), list_pending(), mark_requeued() |
| DeadLetter dataclass | `k0/storage/dlq.py` | DLQ entry structure |
| RetryScheduler | `k0/outbox/scheduler.py` | decide() returns RetryDecision |
| RetryDecision | `k0/outbox/scheduler.py` | action, retries, next_attempt_ts |
| MetricsExporter | `k0/obs/metrics.py` | counter(), gauge(), histogram() |
| P03Error | `k0/pipelines/p03/observability.py` | Error record dataclass |
| ErrorClassifier | Issue 6.2.1 | classify(), is_retriable() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/ops/error_handler.py` module
2. [ ] Define `P03ErrorContext` dataclass for error metadata
3. [ ] Implement `P03ErrorHandler.__init__()` with dependency injection
4. [ ] Implement `handle_error()` main routing method
5. [ ] Implement `_handle_transient()` for retry scheduling
6. [ ] Implement `_handle_validation()` for immediate DLQ
7. [ ] Implement `_handle_logic()` for DLQ + alerting
8. [ ] Implement `_handle_fatal()` for circuit breaker trigger
9. [ ] Implement `_send_to_dlq()` helper using K0 DeadLetterQueue
10. [ ] Implement `_schedule_retry()` helper using K0 RetryScheduler
11. [ ] Add metrics emission for all error paths
12. [ ] Create integration tests with mock DLQ/RetryScheduler

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/error_handler.py
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from k0.storage.dlq import DeadLetter, DeadLetterQueue
from k0.outbox.scheduler import RetryScheduler, RetryDecision
from k0.obs.metrics import MetricsExporter
from k0.pipelines.p03.ops.error_classifier import ErrorClassifier, P03ErrorCategory
from k0.ulid import generate_ulid

if TYPE_CHECKING:
    import asyncpg


@dataclass
class P03ErrorContext:
    """Context for error handling decisions."""
    cycle_id: str
    phase: str
    event_id: Optional[str] = None
    entity_id: Optional[str] = None
    tenant_id: str = ""
    space_id: str = ""
    attempt_count: int = 1
    payload: dict = field(default_factory=dict)


class P03ErrorHandler:
    """
    Central error handler integrated with K0 DLQ and retry subsystems.

    References:
    - k0/storage/dlq.py: DeadLetterQueue.record()
    - k0/outbox/scheduler.py: RetryScheduler.decide()
    - Dossier Section 13.3
    """

    def __init__(
        self,
        dlq: DeadLetterQueue,
        retry_scheduler: RetryScheduler,
        metrics: MetricsExporter,
        *,
        max_attempts: int = 3,
    ):
        self._dlq = dlq
        self._retry = retry_scheduler
        self._metrics = metrics
        self._classifier = ErrorClassifier()
        self._max_attempts = max_attempts

    async def handle_error(
        self,
        error: Exception,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> RetryDecision | None:
        """
        Route error to appropriate handler based on classification.

        Returns:
            RetryDecision if error should be retried, None if sent to DLQ.
        """
        category = self._classifier.classify(error)

        # Emit error metric
        self._metrics.emit(
            "p03_errors_total",
            1.0,
            phase=context.phase,
            error_type=category.value,
            error_class=type(error).__name__,
        )

        if category == P03ErrorCategory.TRANSIENT:
            return await self._handle_transient(error, context, connection=connection)
        elif category == P03ErrorCategory.VALIDATION:
            await self._handle_validation(error, context, connection=connection)
            return None
        elif category == P03ErrorCategory.LOGIC:
            await self._handle_logic(error, context, connection=connection)
            return None
        else:  # FATAL
            await self._handle_fatal(error, context, connection=connection)
            return None

    async def _handle_transient(
        self,
        error: Exception,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> RetryDecision | None:
        """Handle transient error with retry logic."""
        if context.attempt_count >= self._max_attempts:
            # Max retries exceeded, send to DLQ
            await self._send_to_dlq(
                error, context, status="ABANDONED", connection=connection
            )
            self._metrics.emit(
                "p03_retry_exhausted_total",
                1.0,
                phase=context.phase,
            )
            return None

        # Schedule retry with exponential backoff
        decision = RetryDecision(
            action="retry",
            retries=context.attempt_count,
            requeue_seq=0,
            next_attempt_ts=None,  # Calculated by scheduler
            backoff_exp=min(context.attempt_count, 6),
            status="PENDING",
        )

        self._metrics.emit(
            "p03_retry_scheduled_total",
            1.0,
            phase=context.phase,
            attempt=str(context.attempt_count),
        )

        return decision

    async def _handle_validation(
        self,
        error: Exception,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Handle validation error - immediate DLQ, no retry."""
        await self._send_to_dlq(
            error, context, status="PENDING", connection=connection
        )

    async def _handle_logic(
        self,
        error: Exception,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Handle logic error - DLQ + alert."""
        await self._send_to_dlq(
            error, context, status="MANUAL_REVIEW", connection=connection
        )

        # Emit alert event
        self._metrics.emit(
            "p03_error_alert_total",
            1.0,
            phase=context.phase,
            severity="high",
        )

    async def _handle_fatal(
        self,
        error: Exception,
        context: P03ErrorContext,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Handle fatal error - DLQ + circuit breaker trigger."""
        await self._send_to_dlq(
            error, context, status="ABANDONED", connection=connection
        )

        # Emit critical alert
        self._metrics.emit(
            "p03_error_fatal_total",
            1.0,
            phase=context.phase,
        )

    async def _send_to_dlq(
        self,
        error: Exception,
        context: P03ErrorContext,
        *,
        status: str = "PENDING",
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record error in K0 DLQ (st_dlq table)."""
        from k0.ulid import now_ms

        now = now_ms()
        letter = DeadLetter(
            id=None,
            wal_pos=None,
            tenant_id=context.tenant_id,
            space_id=context.space_id,
            driver="p03_consolidation",
            op_kind=context.phase,
            fingerprint=f"{context.cycle_id}:{context.event_id or 'batch'}",
            payload=json.dumps(context.payload).encode("utf-8"),
            reason=str(error),
            retries=context.attempt_count,
            requeue_seq=0,
            first_failure_ts=str(now),
            last_failure_ts=str(now),
            state=status,
        )

        return await self._dlq.record(letter, connection=connection)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_errors_total | counter | phase, error_type, error_class | All errors by category |
| p03_retry_scheduled_total | counter | phase, attempt | Retry attempts scheduled |
| p03_retry_exhausted_total | counter | phase | Retries exceeded max attempts |
| p03_error_alert_total | counter | phase, severity | Alerts triggered |
| p03_error_fatal_total | counter | phase | Fatal errors (circuit breaker) |

**Acceptance Criteria**:

- [ ] P03ErrorHandler created with DLQ, RetryScheduler, MetricsExporter injection
- [ ] handle_error() routes to correct handler by category
- [ ] TRANSIENT errors schedule retry up to max_attempts
- [ ] TRANSIENT errors go to DLQ after max_attempts exceeded
- [ ] VALIDATION errors go directly to DLQ (no retry)
- [ ] LOGIC errors go to DLQ with MANUAL_REVIEW status + alert
- [ ] FATAL errors trigger circuit breaker + alert
- [ ] All error paths emit appropriate metrics
- [ ] DLQ entries include full context (cycle_id, phase, event_id, payload)
- [ ] Integration tests validate all routing paths

---

#### Issue 6.2.3 — DLQRecord and DLQStore P03 Integration

**Status**: 🔲 NOT STARTED

**Goal**: Create P03-specific DLQ record format and integration with K0's DeadLetterQueue.

**Dossier Reference**: [Section 13.4 Dead Letter Queue Schema](../pipelines/P03_consolidation_dossier_v2.md#134-dead-letter-queue-schema-st_dlq)

**DLQ Schema** (from dossier 13.4):

The K0 `st_dlq` table stores all dead-lettered items. P03 uses the standard K0 DeadLetter format with P03-specific conventions:

| Field | K0 DeadLetter Field | P03 Usage |
|-------|---------------------|-----------|
| driver | driver | "p03_consolidation" |
| op_kind | op_kind | Phase (R0, R1, ..., R8) |
| fingerprint | fingerprint | "{cycle_id}:{event_id}" |
| payload | payload | JSON-encoded batch/event data |
| reason | reason | Error message |
| state | state | PENDING, REQUEUED, QUARANTINED |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| DeadLetterQueue | `k0/storage/dlq.py` | record(), list_pending(), get(), mark_requeued(), purge() |
| DeadLetter | `k0/storage/dlq.py` | Standard DLQ entry dataclass |
| P03Error | `k0/pipelines/p03/observability.py` | Error record with stack trace |
| P03Envelope | `k0/pipelines/p03/envelope.py` | Cycle envelope for context |

**Work To Do**:

1. [ ] Create `P03DLQRecord` dataclass extending P03-specific fields
2. [ ] Implement `P03DLQStore` wrapper around K0 DeadLetterQueue
3. [ ] Implement `record_phase_error()` for phase-level errors
4. [ ] Implement `record_event_error()` for event-level errors
5. [ ] Implement `record_batch_error()` for batch-level errors
6. [ ] Implement `list_pending_by_phase()` filtered query
7. [ ] Implement `list_pending_by_cycle()` filtered query
8. [ ] Implement `mark_resolved()` with resolution metadata
9. [ ] Implement `to_dead_letter()` conversion method
10. [ ] Implement `from_dead_letter()` factory method
11. [ ] Add P03-specific metrics for DLQ operations
12. [ ] Create unit tests for all conversion methods

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/dlq_store.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, List

from k0.storage.dlq import DeadLetter, DeadLetterQueue
from k0.obs.metrics import MetricsExporter
from k0.ulid import generate_ulid, now_ms

if TYPE_CHECKING:
    import asyncpg


@dataclass
class P03DLQRecord:
    """
    P03-specific DLQ record with enriched context.

    Maps to/from K0 DeadLetter for persistence.
    """
    # Identity
    id: Optional[int] = None
    dlq_id: str = field(default_factory=generate_ulid)

    # P03 Context
    cycle_id: str = ""
    phase: str = ""
    event_id: Optional[str] = None
    entity_id: Optional[str] = None

    # Tenant Context
    tenant_id: str = ""
    space_id: str = ""

    # Error Details
    error_type: str = ""          # TRANSIENT, VALIDATION, LOGIC, FATAL
    error_code: str = ""          # Exception class name
    error_message: str = ""
    stack_trace: Optional[str] = None

    # Payload
    payload: dict = field(default_factory=dict)

    # Retry State
    attempt_count: int = 1
    max_attempts: int = 3

    # Timestamps (milliseconds)
    first_failure_ts: int = 0
    last_failure_ts: int = 0
    resolved_at: Optional[int] = None

    # Status
    status: str = "PENDING"  # PENDING, RETRYING, RESOLVED, ABANDONED, MANUAL_REVIEW
    resolution_notes: Optional[str] = None

    def to_dead_letter(self) -> DeadLetter:
        """Convert to K0 DeadLetter for persistence."""
        return DeadLetter(
            id=self.id,
            wal_pos=None,
            tenant_id=self.tenant_id,
            space_id=self.space_id,
            driver="p03_consolidation",
            op_kind=self.phase,
            fingerprint=f"{self.cycle_id}:{self.event_id or 'batch'}",
            payload=json.dumps({
                "dlq_id": self.dlq_id,
                "cycle_id": self.cycle_id,
                "event_id": self.event_id,
                "entity_id": self.entity_id,
                "error_type": self.error_type,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "stack_trace": self.stack_trace,
                "payload": self.payload,
                "attempt_count": self.attempt_count,
                "max_attempts": self.max_attempts,
            }).encode("utf-8"),
            reason=self.error_message,
            retries=self.attempt_count,
            requeue_seq=0,
            first_failure_ts=str(self.first_failure_ts),
            last_failure_ts=str(self.last_failure_ts),
            state=self.status,
        )

    @classmethod
    def from_dead_letter(cls, letter: DeadLetter) -> P03DLQRecord:
        """Create from K0 DeadLetter."""
        payload_data = json.loads(letter.payload.decode("utf-8"))
        return cls(
            id=letter.id,
            dlq_id=payload_data.get("dlq_id", generate_ulid()),
            cycle_id=payload_data.get("cycle_id", ""),
            phase=letter.op_kind,
            event_id=payload_data.get("event_id"),
            entity_id=payload_data.get("entity_id"),
            tenant_id=letter.tenant_id,
            space_id=letter.space_id,
            error_type=payload_data.get("error_type", ""),
            error_code=payload_data.get("error_code", ""),
            error_message=letter.reason,
            stack_trace=payload_data.get("stack_trace"),
            payload=payload_data.get("payload", {}),
            attempt_count=letter.retries,
            max_attempts=payload_data.get("max_attempts", 3),
            first_failure_ts=int(letter.first_failure_ts) if letter.first_failure_ts else 0,
            last_failure_ts=int(letter.last_failure_ts) if letter.last_failure_ts else 0,
            status=letter.state,
        )


class P03DLQStore:
    """
    P03-specific DLQ store wrapping K0 DeadLetterQueue.

    Provides P03 context-aware queries and metrics.
    """

    DRIVER = "p03_consolidation"

    def __init__(
        self,
        dlq: DeadLetterQueue,
        metrics: MetricsExporter,
    ):
        self._dlq = dlq
        self._metrics = metrics

    async def record_phase_error(
        self,
        record: P03DLQRecord,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> int:
        """Record a phase-level error in DLQ."""
        now = now_ms()
        if not record.first_failure_ts:
            record.first_failure_ts = now
        record.last_failure_ts = now

        letter = record.to_dead_letter()
        dlq_id = await self._dlq.record(letter, connection=connection)

        self._metrics.emit(
            "p03_dlq_records_total",
            1.0,
            phase=record.phase,
            error_type=record.error_type,
            status=record.status,
        )

        return dlq_id

    async def list_pending_by_phase(
        self,
        phase: str,
        *,
        tenant_id: Optional[str] = None,
        space_id: Optional[str] = None,
        limit: int = 100,
        connection: asyncpg.Connection | None = None,
    ) -> List[P03DLQRecord]:
        """List pending DLQ records for a specific phase."""
        letters = await self._dlq.list_pending(
            limit=limit,
            state="PENDING",
            tenant_id=tenant_id,
            space_id=space_id,
            driver=self.DRIVER,
            connection=connection,
        )
        # Filter by phase (op_kind)
        return [
            P03DLQRecord.from_dead_letter(letter)
            for letter in letters
            if letter.op_kind == phase
        ]

    async def list_pending_by_cycle(
        self,
        cycle_id: str,
        *,
        limit: int = 100,
        connection: asyncpg.Connection | None = None,
    ) -> List[P03DLQRecord]:
        """List pending DLQ records for a specific cycle."""
        letters = await self._dlq.list_pending(
            limit=limit,
            state="PENDING",
            driver=self.DRIVER,
            connection=connection,
        )
        # Filter by cycle_id in fingerprint
        return [
            P03DLQRecord.from_dead_letter(letter)
            for letter in letters
            if letter.fingerprint.startswith(f"{cycle_id}:")
        ]

    async def mark_resolved(
        self,
        dlq_id: int,
        *,
        resolution_notes: Optional[str] = None,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Mark DLQ entry as resolved."""
        await self._dlq.mark_requeued(dlq_id, connection=connection)

        self._metrics.emit(
            "p03_dlq_resolved_total",
            1.0,
        )
```

**P03 DLQ Queries**:

| Query | Method | Filter |
|-------|--------|--------|
| Pending by phase | list_pending_by_phase(phase) | driver=p03_consolidation, op_kind=phase |
| Pending by cycle | list_pending_by_cycle(cycle_id) | fingerprint LIKE '{cycle_id}:%' |
| Pending by tenant | list_pending(tenant_id=...) | tenant_id filter |
| All for space | list_pending(space_id=...) | space_id filter |

**Acceptance Criteria**:

- [ ] P03DLQRecord dataclass captures all P03-specific context
- [ ] to_dead_letter() correctly maps to K0 DeadLetter
- [ ] from_dead_letter() correctly reconstructs P03DLQRecord
- [ ] P03DLQStore wraps K0 DeadLetterQueue with P03 conventions
- [ ] record_phase_error() records with correct driver/op_kind
- [ ] list_pending_by_phase() filters by phase correctly
- [ ] list_pending_by_cycle() filters by cycle_id fingerprint
- [ ] mark_resolved() updates state and emits metrics
- [ ] All DLQ operations emit appropriate metrics
- [ ] Unit tests validate all conversion round-trips

---

#### Issue 6.2.4 — P03RetryConfig and RetryScheduler Integration

**Status**: 🔲 NOT STARTED

**Goal**: Implement P03-specific retry configuration with phase overrides and K0 RetryScheduler integration.

**Dossier Reference**: [Section 13.5 Retry Strategy (K0 RetryScheduler)](../pipelines/P03_consolidation_dossier_v2.md#135-retry-strategy-k0-retryscheduler)

**Retry Configuration** (from dossier 13.5):

| Parameter | Default | Description |
|-----------|---------|-------------|
| base_delay_ms | 1000 | Initial retry delay |
| max_delay_ms | 60000 | Maximum backoff cap |
| exponential_base | 2.0 | Backoff multiplier |
| jitter_factor | 0.1 | Random jitter (±10%) |

**Phase Overrides** (from dossier 13.5):

| Phase | max_attempts | Reason |
|-------|--------------|--------|
| R0 | 5 | Trigger detection can retry more (lock contention) |
| R7 | 10 | Truth writes are critical (version conflicts) |
| R8 | 3 | Bus emission standard (default) |
| Default | 3 | Standard retry count |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| RetryScheduler | `k0/outbox/scheduler.py` | decide() method |
| RetryDecision | `k0/outbox/scheduler.py` | action, retries, next_attempt_ts |
| OutboxEntry | `k0/storage/outbox.py` | Entry structure for decide() |
| P03PhaseId | `k0/pipelines/p03/runner_contract.py` | Phase enum |

**Work To Do**:

1. [ ] Create `P03RetryConfig` dataclass in `k0/pipelines/p03/ops/retry_config.py`
2. [ ] Define `PHASE_RETRY_OVERRIDES` constant dict
3. [ ] Implement `get_max_attempts(phase: str) -> int` method
4. [ ] Implement `get_backoff_delay_ms(attempt: int) -> int` method
5. [ ] Implement `add_jitter(delay_ms: int) -> int` method
6. [ ] Create `P03RetryScheduler` wrapper with phase awareness
7. [ ] Implement `decide(phase: str, attempt_count: int, error: Exception) -> RetryDecision`
8. [ ] Implement `create_p03_retry_scheduler()` factory function
9. [ ] Add retry metrics (attempt counts, delays, exhaustions)
10. [ ] Create unit tests for all retry scenarios

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/retry_config.py
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from k0.outbox.scheduler import RetryDecision


@dataclass
class P03RetryConfig:
    """
    P03-specific retry configuration with phase overrides.

    K0 Reference: k0/outbox/scheduler.py
    Dossier Reference: Section 13.5
    """

    # Base configuration
    base_delay_ms: int = 1000
    max_delay_ms: int = 60000
    exponential_base: float = 2.0
    jitter_factor: float = 0.1

    # Default max attempts (overridden per phase)
    default_max_attempts: int = 3

    # Phase-specific overrides
    phase_overrides: Dict[str, Dict[str, int]] = field(default_factory=lambda: {
        "R0": {"max_attempts": 5},   # Trigger detection can retry more
        "R7": {"max_attempts": 10},  # Truth writes are critical
        "R8": {"max_attempts": 3},   # Bus emission standard
    })

    def get_max_attempts(self, phase: str) -> int:
        """Get max retry attempts for a phase."""
        override = self.phase_overrides.get(phase, {})
        return override.get("max_attempts", self.default_max_attempts)

    def get_backoff_delay_ms(self, attempt: int) -> int:
        """Calculate exponential backoff delay for attempt number."""
        delay = self.base_delay_ms * (self.exponential_base ** (attempt - 1))
        return min(int(delay), self.max_delay_ms)

    def add_jitter(self, delay_ms: int) -> int:
        """Add random jitter to delay (±jitter_factor)."""
        jitter_range = int(delay_ms * self.jitter_factor)
        jitter = random.randint(-jitter_range, jitter_range)
        return max(0, delay_ms + jitter)


class P03RetryScheduler:
    """
    Phase-aware retry scheduler for P03 using K0 patterns.

    Integrates with k0/outbox/scheduler.py: RetryDecision
    """

    def __init__(self, config: Optional[P03RetryConfig] = None):
        self._config = config or P03RetryConfig()

    @property
    def config(self) -> P03RetryConfig:
        return self._config

    def decide(
        self,
        phase: str,
        attempt_count: int,
        error: Optional[Exception] = None,
    ) -> RetryDecision:
        """
        Decide whether to retry based on phase and attempt count.

        Returns:
            RetryDecision with action="retry" or action="quarantine"
        """
        max_attempts = self._config.get_max_attempts(phase)

        if attempt_count >= max_attempts:
            # Max retries exceeded → quarantine
            return RetryDecision(
                action="quarantine",
                retries=attempt_count,
                requeue_seq=0,
                next_attempt_ts=None,
                backoff_exp=0,
                status="DEAD",
            )

        # Calculate backoff with jitter
        delay_ms = self._config.get_backoff_delay_ms(attempt_count)
        delay_ms = self._config.add_jitter(delay_ms)

        next_attempt = datetime.now(timezone.utc) + timedelta(milliseconds=delay_ms)
        backoff_exp = min(attempt_count, 6)

        return RetryDecision(
            action="retry",
            retries=attempt_count,
            requeue_seq=0,
            next_attempt_ts=next_attempt,
            backoff_exp=backoff_exp,
            status="PENDING",
        )

    def should_retry(self, phase: str, attempt_count: int) -> bool:
        """Check if retry should be attempted."""
        return attempt_count < self._config.get_max_attempts(phase)

    def get_delay_ms(self, attempt_count: int) -> int:
        """Get delay for next retry attempt (with jitter)."""
        delay = self._config.get_backoff_delay_ms(attempt_count)
        return self._config.add_jitter(delay)


def create_p03_retry_scheduler(
    config: Optional[P03RetryConfig] = None,
) -> P03RetryScheduler:
    """Factory for P03's retry scheduler instance."""
    return P03RetryScheduler(config=config)
```

**Retry Delay Calculations**:

| Attempt | Base Delay | With Jitter (±10%) | Max Cap |
|---------|------------|-------------------|---------|
| 1 | 1000ms | 900-1100ms | — |
| 2 | 2000ms | 1800-2200ms | — |
| 3 | 4000ms | 3600-4400ms | — |
| 4 | 8000ms | 7200-8800ms | — |
| 5 | 16000ms | 14400-17600ms | — |
| 6 | 32000ms | 28800-35200ms | — |
| 7+ | 60000ms | 54000-60000ms | capped |

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_retry_attempt_total | counter | phase, attempt | Retry attempts by phase |
| p03_retry_delay_ms | histogram | phase | Retry delay distribution |
| p03_retry_exhausted_total | counter | phase | Retries exceeded max |

**Acceptance Criteria**:

- [ ] P03RetryConfig captures all retry parameters
- [ ] Phase overrides correctly applied (R0:5, R7:10, R8:3)
- [ ] get_backoff_delay_ms() implements exponential backoff
- [ ] add_jitter() adds ±jitter_factor randomness
- [ ] Delay capped at max_delay_ms
- [ ] P03RetryScheduler.decide() returns correct RetryDecision
- [ ] "quarantine" returned when attempt_count >= max_attempts
- [ ] "retry" returned with calculated delay when under max
- [ ] create_p03_retry_scheduler() factory works with default/custom config
- [ ] Unit tests validate all backoff calculations

---

#### Issue 6.2.5 — P03CircuitBreaker Base Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement circuit breaker state machine for P03 external dependencies (P08, Bus, FAISS).

**Dossier Reference**: [Section 13.6 Circuit Breaker (External Dependencies)](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breaker-external-dependencies)

**Circuit Breaker States** (from dossier 13.6):

```
CLOSED ──(failures >= threshold)──▶ OPEN ──(timeout elapsed)──▶ HALF_OPEN
   ▲                                                                 │
   └────────────(successes >= threshold)─────────────────────────────┘
   ▲                                                                 │
   └────────────────────(failure in HALF_OPEN)───────────────────────┘
                              (back to OPEN)
```

**Circuit Breaker Configuration** (from dossier 13.6):

| Parameter | Default | Description |
|-----------|---------|-------------|
| failure_threshold | 5 | Failures before opening circuit |
| reset_timeout_seconds | 60 | Time before half-open transition |
| success_threshold | 3 | Successes in half-open before closing |

**P03 Circuit Breaker Instances** (from dossier 13.6):

| Instance | Dependency | Use Case |
|----------|------------|----------|
| p08_embedding | P08 embedding pipeline | R4 KG entity embedding |
| bus_dispatcher | Internal event bus | R8 event emission |
| faiss_index | FAISS vector index | R2 similarity search |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| get_network_delay_ms | `k0/chaos/toggles.py` | Chaos injection for testing |
| MetricsExporter | `k0/obs/metrics.py` | Circuit breaker metrics |
| P03PhaseId | `k0/pipelines/p03/runner_contract.py` | Phase enum |

**Work To Do**:

1. [ ] Create `P03CircuitBreakerState` enum in `k0/pipelines/p03/ops/circuit_breaker.py`
2. [ ] Create `P03CircuitBreakerConfig` dataclass
3. [ ] Implement `P03CircuitBreaker` class with state machine
4. [ ] Implement `should_allow_request() -> bool` method
5. [ ] Implement `record_success()` method
6. [ ] Implement `record_failure()` method
7. [ ] Implement `_transition_to(state)` with metrics
8. [ ] Implement `get_state_duration_seconds() -> float` method
9. [ ] Create `P03CircuitBreakerRegistry` for managing instances
10. [ ] Create pre-configured instances (p08_embedding, bus_dispatcher, faiss_index)
11. [ ] Add chaos toggle integration for testing
12. [ ] Create unit tests for all state transitions

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/circuit_breaker.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from k0.obs.metrics import MetricsExporter


class P03CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"       # Normal operation, requests allowed
    OPEN = "OPEN"           # Circuit tripped, requests blocked
    HALF_OPEN = "HALF_OPEN" # Testing recovery, limited requests


@dataclass
class P03CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5       # Failures before opening
    reset_timeout_seconds: float = 60.0  # Time before half-open
    success_threshold: int = 3       # Successes before closing
    half_open_max_requests: int = 1  # Concurrent requests in half-open


class P03CircuitBreaker:
    """
    Circuit breaker for P03's external dependencies.

    Implements CLOSED → OPEN → HALF_OPEN → CLOSED state machine.
    Integrates with K0 chaos toggles for testing resilience.

    Dossier Reference: Section 13.6
    """

    def __init__(
        self,
        name: str,
        config: Optional[P03CircuitBreakerConfig] = None,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._name = name
        self._config = config or P03CircuitBreakerConfig()
        self._metrics = metrics

        # State tracking
        self._state = P03CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._state_changed_at: float = time.monotonic()
        self._half_open_requests = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> P03CircuitBreakerState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def should_allow_request(self) -> bool:
        """
        Check if request should be allowed through circuit.

        Returns:
            True if request should proceed, False if blocked.
        """
        # Check for chaos injection (testing)
        if self._is_chaos_injected():
            self._transition_to(P03CircuitBreakerState.OPEN)
            return False

        if self._state == P03CircuitBreakerState.CLOSED:
            return True

        if self._state == P03CircuitBreakerState.OPEN:
            # Check if reset timeout elapsed
            if self._time_since_state_change() >= self._config.reset_timeout_seconds:
                self._transition_to(P03CircuitBreakerState.HALF_OPEN)
                self._half_open_requests = 1
                return True
            return False

        if self._state == P03CircuitBreakerState.HALF_OPEN:
            # Allow limited requests in half-open
            if self._half_open_requests < self._config.half_open_max_requests:
                self._half_open_requests += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record successful call."""
        if self._state == P03CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._config.success_threshold:
                self._transition_to(P03CircuitBreakerState.CLOSED)
        elif self._state == P03CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

        self._emit_metric("p03_circuit_breaker_success_total", 1.0)

    def record_failure(self) -> None:
        """Record failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == P03CircuitBreakerState.HALF_OPEN:
            # Failure in half-open → back to open
            self._transition_to(P03CircuitBreakerState.OPEN)
        elif self._state == P03CircuitBreakerState.CLOSED:
            if self._failure_count >= self._config.failure_threshold:
                self._transition_to(P03CircuitBreakerState.OPEN)

        self._emit_metric("p03_circuit_breaker_failure_total", 1.0)

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self._transition_to(P03CircuitBreakerState.CLOSED)
        self._failure_count = 0
        self._success_count = 0

    def _transition_to(self, new_state: P03CircuitBreakerState) -> None:
        """Transition to new state with metrics."""
        old_state = self._state
        self._state = new_state
        self._state_changed_at = time.monotonic()

        if new_state == P03CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == P03CircuitBreakerState.HALF_OPEN:
            self._success_count = 0
            self._half_open_requests = 0

        self._emit_metric(
            "p03_circuit_breaker_state_transitions_total",
            1.0,
            from_state=old_state.value,
            to_state=new_state.value,
        )

    def _time_since_state_change(self) -> float:
        """Get seconds since last state change."""
        return time.monotonic() - self._state_changed_at

    def _is_chaos_injected(self) -> bool:
        """Check for K0 chaos injection (testing)."""
        try:
            from k0.chaos.toggles import get_network_delay_ms
            return get_network_delay_ms() > 30000  # 30s simulated partition
        except ImportError:
            return False

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        """Emit metric if exporter available."""
        if self._metrics:
            self._metrics.emit(name, value, circuit=self._name, **labels)


class P03CircuitBreakerRegistry:
    """Registry for P03 circuit breaker instances."""

    def __init__(self, metrics: Optional[MetricsExporter] = None):
        self._metrics = metrics
        self._circuits: Dict[str, P03CircuitBreaker] = {}

    def get(self, name: str) -> P03CircuitBreaker:
        """Get or create circuit breaker by name."""
        if name not in self._circuits:
            self._circuits[name] = P03CircuitBreaker(
                name=name,
                metrics=self._metrics,
            )
        return self._circuits[name]

    def get_all(self) -> Dict[str, P03CircuitBreaker]:
        """Get all registered circuit breakers."""
        return dict(self._circuits)

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for circuit in self._circuits.values():
            circuit.reset()


# Pre-configured P03 circuit breakers (from dossier 13.6)
def create_p03_circuit_breakers(
    metrics: Optional[MetricsExporter] = None,
) -> P03CircuitBreakerRegistry:
    """Create pre-configured P03 circuit breakers."""
    registry = P03CircuitBreakerRegistry(metrics=metrics)

    # P08 embedding pipeline
    registry._circuits["p08_embedding"] = P03CircuitBreaker(
        name="p08_embedding",
        config=P03CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout_seconds=60.0,
            success_threshold=3,
        ),
        metrics=metrics,
    )

    # Internal event bus
    registry._circuits["bus_dispatcher"] = P03CircuitBreaker(
        name="bus_dispatcher",
        config=P03CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout_seconds=60.0,
            success_threshold=3,
        ),
        metrics=metrics,
    )

    # FAISS vector index
    registry._circuits["faiss_index"] = P03CircuitBreaker(
        name="faiss_index",
        config=P03CircuitBreakerConfig(
            failure_threshold=3,  # FAISS is more sensitive
            reset_timeout_seconds=30.0,  # Faster recovery
            success_threshold=2,
        ),
        metrics=metrics,
    )

    return registry
```

**State Transition Table**:

| Current State | Event | Next State | Action |
|---------------|-------|------------|--------|
| CLOSED | failure_count >= threshold | OPEN | Block requests |
| CLOSED | success | CLOSED | Reset failure count |
| OPEN | timeout elapsed | HALF_OPEN | Allow test request |
| OPEN | request | OPEN | Reject immediately |
| HALF_OPEN | success_count >= threshold | CLOSED | Resume normal |
| HALF_OPEN | failure | OPEN | Block again |

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_circuit_breaker_state | gauge | circuit | Current state (0=CLOSED, 1=OPEN, 2=HALF_OPEN) |
| p03_circuit_breaker_failure_total | counter | circuit | Failures recorded |
| p03_circuit_breaker_success_total | counter | circuit | Successes recorded |
| p03_circuit_breaker_state_transitions_total | counter | circuit, from_state, to_state | State changes |
| p03_circuit_breaker_open_duration_seconds | histogram | circuit | Time spent in OPEN state |

**Acceptance Criteria**:

- [ ] P03CircuitBreakerState enum with CLOSED, OPEN, HALF_OPEN
- [ ] P03CircuitBreakerConfig with configurable thresholds
- [ ] should_allow_request() returns False when OPEN
- [ ] should_allow_request() allows test request in HALF_OPEN
- [ ] record_success() transitions HALF_OPEN → CLOSED after threshold
- [ ] record_failure() transitions CLOSED → OPEN after threshold
- [ ] record_failure() transitions HALF_OPEN → OPEN immediately
- [ ] Timeout elapsed in OPEN → HALF_OPEN automatic transition
- [ ] P03CircuitBreakerRegistry manages named instances
- [ ] Pre-configured circuits: p08_embedding, bus_dispatcher, faiss_index
- [ ] Chaos toggle integration for testing
- [ ] All state transitions emit metrics
- [ ] Unit tests validate complete state machine

---

#### Issue 6.2.6 — P08 Embedding Circuit Breaker

**Status**: 🔲 NOT STARTED

**Goal**: Implement specialized circuit breaker for P08 embedding pipeline coordination used in R4 KG entity embedding.

**Dossier Reference**: [Section 13.6 Circuit Breaker (External Dependencies)](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breaker-external-dependencies)

**P08 Dependency Context**:

P03's R4 phase (KG construction) relies on P08 for entity embeddings. When P08 is unavailable or slow, R4 must gracefully degrade.

| Scenario | P08 Available | P08 Unavailable |
|----------|---------------|-----------------|
| Entity embedding | Real-time embedding via P08 | Use cached embedding from st_vec |
| New entity | Fresh embedding | Queue for later embedding |
| Embedding refresh | Request new embedding | Skip refresh, use existing |

**Circuit Breaker Configuration** (P08-specific):

| Parameter | Value | Reason |
|-----------|-------|--------|
| failure_threshold | 5 | Standard threshold |
| reset_timeout_seconds | 60 | 1 minute recovery window |
| success_threshold | 3 | 3 successful calls to close |
| half_open_max_requests | 1 | Single test request |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03CircuitBreaker | Issue 6.2.5 | Base circuit breaker class |
| P03CircuitBreakerRegistry | Issue 6.2.5 | Registry for named instances |
| P08Coordinator | `k0/pipelines/p08/` | P08 embedding pipeline interface |
| R4KGBuilder | `k0/pipelines/p03/phases/r4_kg.py` | KG construction phase |
| MetricsExporter | `k0/obs/metrics.py` | Circuit breaker metrics |

**Work To Do**:

1. [ ] Create `P08EmbeddingCircuitBreaker` wrapper in `k0/pipelines/p03/ops/p08_circuit.py`
2. [ ] Implement `get_embedding_with_fallback(entity_id)` method
3. [ ] Implement `_fallback_to_cached(entity_id)` method
4. [ ] Implement `_queue_for_later(entity_id)` for deferred embedding
5. [ ] Hook R4 phase to use circuit breaker for all P08 calls
6. [ ] Add P08-specific metrics (open duration, fallback usage)
7. [ ] Implement automatic recovery when circuit closes
8. [ ] Create integration tests with P08 mock

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/p08_circuit.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from k0.pipelines.p03.ops.circuit_breaker import (
    P03CircuitBreaker,
    P03CircuitBreakerConfig,
    P03CircuitBreakerState,
)
from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class P08EmbeddingCircuitBreaker:
    """
    Circuit breaker for P08 embedding pipeline coordination.

    Used by R4 phase for entity embedding requests.
    Provides fallback to cached embeddings when P08 unavailable.

    Dossier Reference: Section 13.6
    """

    def __init__(
        self,
        p08_client,  # P08 pipeline client
        circuit: P03CircuitBreaker,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._p08 = p08_client
        self._circuit = circuit
        self._metrics = metrics
        self._pending_queue: list[str] = []  # Entities queued for later

    @property
    def is_open(self) -> bool:
        return self._circuit.state == P03CircuitBreakerState.OPEN

    async def get_embedding(
        self,
        entity_id: str,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Optional[list[float]]:
        """
        Get entity embedding with circuit breaker protection.

        Returns:
            Embedding vector if available, None if circuit open and no cache.
        """
        if not self._circuit.should_allow_request():
            # Circuit open - fallback to cache
            self._emit_metric("p03_p08_circuit_fallback_total", 1.0)
            return await self._fallback_to_cached(entity_id, connection=connection)

        try:
            embedding = await self._p08.get_embedding(entity_id)
            self._circuit.record_success()
            return embedding

        except Exception as e:
            self._circuit.record_failure()
            self._emit_metric(
                "p03_p08_embedding_failure_total",
                1.0,
                error_type=type(e).__name__,
            )

            # Try fallback
            cached = await self._fallback_to_cached(entity_id, connection=connection)
            if cached is None:
                # Queue for later embedding
                await self._queue_for_later(entity_id)
            return cached

    async def _fallback_to_cached(
        self,
        entity_id: str,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Optional[list[float]]:
        """Retrieve cached embedding from st_vec."""
        from k0.db.connection import connection_scope

        async with connection_scope(connection) as conn:
            row = await conn.fetchrow(
                """
                SELECT embedding
                FROM st_vec
                WHERE entity_id = $1 AND status = 'ACTIVE'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                entity_id,
            )

        if row and row["embedding"]:
            self._emit_metric("p03_p08_cache_hit_total", 1.0)
            return list(row["embedding"])

        self._emit_metric("p03_p08_cache_miss_total", 1.0)
        return None

    async def _queue_for_later(self, entity_id: str) -> None:
        """Queue entity for embedding when circuit recovers."""
        if entity_id not in self._pending_queue:
            self._pending_queue.append(entity_id)
            self._emit_metric("p03_p08_queued_total", 1.0)

    async def process_pending_queue(self) -> int:
        """Process pending embeddings when circuit closes. Returns count processed."""
        if self._circuit.state != P03CircuitBreakerState.CLOSED:
            return 0

        processed = 0
        while self._pending_queue and self._circuit.should_allow_request():
            entity_id = self._pending_queue.pop(0)
            try:
                await self._p08.get_embedding(entity_id)
                self._circuit.record_success()
                processed += 1
            except Exception:
                self._circuit.record_failure()
                self._pending_queue.insert(0, entity_id)  # Put back
                break

        return processed

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)


def create_p08_circuit_breaker(
    p08_client,
    metrics: Optional[MetricsExporter] = None,
) -> P08EmbeddingCircuitBreaker:
    """Factory for P08 embedding circuit breaker."""
    circuit = P03CircuitBreaker(
        name="p08_embedding",
        config=P03CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout_seconds=60.0,
            success_threshold=3,
        ),
        metrics=metrics,
    )
    return P08EmbeddingCircuitBreaker(p08_client, circuit, metrics)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_p08_circuit_fallback_total | counter | — | Fallback to cache due to open circuit |
| p03_p08_embedding_failure_total | counter | error_type | P08 embedding failures |
| p03_p08_cache_hit_total | counter | — | Successful cache fallbacks |
| p03_p08_cache_miss_total | counter | — | Cache miss (no fallback available) |
| p03_p08_queued_total | counter | — | Entities queued for later |
| p03_p08_circuit_open_seconds | histogram | — | Duration of OPEN state |

**Acceptance Criteria**:

- [ ] P08EmbeddingCircuitBreaker wraps P03CircuitBreaker
- [ ] get_embedding() checks circuit before calling P08
- [ ] Fallback to cached embedding when circuit open
- [ ] Queue entities for later when no cache available
- [ ] process_pending_queue() drains queue when circuit closes
- [ ] All operations emit appropriate metrics
- [ ] R4 phase uses P08 circuit breaker for entity embeddings
- [ ] Integration tests validate fallback behavior

---

#### Issue 6.2.7 — Bus Dispatcher Circuit Breaker

**Status**: 🔲 NOT STARTED

**Goal**: Implement specialized circuit breaker for internal event bus used in R8 event emission.

**Dossier Reference**: [Section 13.6 Circuit Breaker (External Dependencies)](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breaker-external-dependencies)

**Bus Dependency Context**:

P03's R8 phase emits events to the internal bus for downstream consumers (P04, P06, etc.). When the bus is unavailable, events must be queued for later emission.

| Scenario | Bus Available | Bus Unavailable |
|----------|---------------|-----------------|
| Event emission | Immediate publish | Queue to outbox |
| Gap emission | Immediate publish | Queue to outbox |
| Health events | Immediate publish | Drop (non-critical) |

**Circuit Breaker Configuration** (Bus-specific):

| Parameter | Value | Reason |
|-----------|-------|--------|
| failure_threshold | 5 | Standard threshold |
| reset_timeout_seconds | 60 | 1 minute recovery window |
| success_threshold | 3 | 3 successful emissions to close |
| half_open_max_requests | 1 | Single test emission |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03CircuitBreaker | Issue 6.2.5 | Base circuit breaker class |
| InternalBus | `k0/bus/internal_bus.py` | Bus interface |
| R8EventEmitter | `k0/pipelines/p03/phases/r8_emit.py` | Event emission phase |
| OutboxPublisher | `k0/pipelines/p03/outbox_publisher.py` | Outbox fallback |
| MetricsExporter | `k0/obs/metrics.py` | Circuit breaker metrics |

**Work To Do**:

1. [ ] Create `BusDispatcherCircuitBreaker` wrapper in `k0/pipelines/p03/ops/bus_circuit.py`
2. [ ] Implement `emit_with_fallback(event)` method
3. [ ] Implement `_fallback_to_outbox(event)` for deferred emission
4. [ ] Implement `_classify_event_priority(event)` for drop decisions
5. [ ] Hook R8 phase to use circuit breaker for all bus emissions
6. [ ] Add bus-specific metrics (queue depth, fallback rate)
7. [ ] Implement outbox drain when circuit closes
8. [ ] Create integration tests with bus mock

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/bus_circuit.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.pipelines.p03.ops.circuit_breaker import (
    P03CircuitBreaker,
    P03CircuitBreakerConfig,
    P03CircuitBreakerState,
)
from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class EventPriority(Enum):
    """Event priority for emission decisions."""
    CRITICAL = "CRITICAL"    # Must emit (consolidation complete, errors)
    NORMAL = "NORMAL"        # Should emit (standard events)
    LOW = "LOW"              # Can drop (health checks, diagnostics)


@dataclass
class EmissionResult:
    """Result of event emission attempt."""
    success: bool
    method: str  # "direct", "outbox", "dropped"
    event_id: str


class BusDispatcherCircuitBreaker:
    """
    Circuit breaker for internal event bus.

    Used by R8 phase for event emission.
    Provides fallback to outbox when bus unavailable.

    Dossier Reference: Section 13.6
    """

    # Event types that can be dropped when bus unavailable
    DROPPABLE_EVENTS = frozenset({
        "p03.health.idle.v1",
        "p03.health.heartbeat.v1",
        "p03.debug.trace.v1",
    })

    def __init__(
        self,
        bus_client,  # Internal bus client
        outbox_publisher,  # Outbox fallback
        circuit: P03CircuitBreaker,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._bus = bus_client
        self._outbox = outbox_publisher
        self._circuit = circuit
        self._metrics = metrics

    @property
    def is_open(self) -> bool:
        return self._circuit.state == P03CircuitBreakerState.OPEN

    async def emit(
        self,
        event: dict,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> EmissionResult:
        """
        Emit event with circuit breaker protection.

        Returns:
            EmissionResult with success status and method used.
        """
        event_id = event.get("event_id", "unknown")
        event_type = event.get("event_type", "")
        priority = self._classify_event_priority(event_type)

        if not self._circuit.should_allow_request():
            # Circuit open - use fallback strategy
            return await self._handle_circuit_open(
                event, event_id, priority, connection=connection
            )

        try:
            await self._bus.publish(event)
            self._circuit.record_success()
            self._emit_metric("p03_bus_emit_success_total", 1.0)
            return EmissionResult(success=True, method="direct", event_id=event_id)

        except Exception as e:
            self._circuit.record_failure()
            self._emit_metric(
                "p03_bus_emit_failure_total",
                1.0,
                error_type=type(e).__name__,
            )
            return await self._handle_circuit_open(
                event, event_id, priority, connection=connection
            )

    async def _handle_circuit_open(
        self,
        event: dict,
        event_id: str,
        priority: EventPriority,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> EmissionResult:
        """Handle emission when circuit is open."""
        if priority == EventPriority.LOW:
            # Drop low-priority events
            self._emit_metric("p03_bus_dropped_total", 1.0)
            return EmissionResult(success=False, method="dropped", event_id=event_id)

        # Queue to outbox for later
        await self._fallback_to_outbox(event, connection=connection)
        self._emit_metric("p03_bus_outbox_fallback_total", 1.0)
        return EmissionResult(success=True, method="outbox", event_id=event_id)

    async def _fallback_to_outbox(
        self,
        event: dict,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Queue event to outbox for later emission."""
        await self._outbox.enqueue(
            event_type=event.get("event_type", "unknown"),
            payload=event,
            connection=connection,
        )

    def _classify_event_priority(self, event_type: str) -> EventPriority:
        """Classify event priority for drop decisions."""
        if event_type in self.DROPPABLE_EVENTS:
            return EventPriority.LOW
        if event_type.startswith("p03.error.") or event_type.endswith(".complete.v1"):
            return EventPriority.CRITICAL
        return EventPriority.NORMAL

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)


def create_bus_circuit_breaker(
    bus_client,
    outbox_publisher,
    metrics: Optional[MetricsExporter] = None,
) -> BusDispatcherCircuitBreaker:
    """Factory for bus dispatcher circuit breaker."""
    circuit = P03CircuitBreaker(
        name="bus_dispatcher",
        config=P03CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout_seconds=60.0,
            success_threshold=3,
        ),
        metrics=metrics,
    )
    return BusDispatcherCircuitBreaker(bus_client, outbox_publisher, circuit, metrics)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_bus_emit_success_total | counter | — | Successful direct emissions |
| p03_bus_emit_failure_total | counter | error_type | Failed emission attempts |
| p03_bus_outbox_fallback_total | counter | — | Events queued to outbox |
| p03_bus_dropped_total | counter | — | Low-priority events dropped |
| p03_bus_circuit_open_seconds | histogram | — | Duration of OPEN state |

**Acceptance Criteria**:

- [ ] BusDispatcherCircuitBreaker wraps P03CircuitBreaker
- [ ] emit() checks circuit before calling bus
- [ ] Fallback to outbox for CRITICAL/NORMAL events
- [ ] Drop LOW priority events when circuit open
- [ ] Event priority classification works correctly
- [ ] All operations emit appropriate metrics
- [ ] R8 phase uses bus circuit breaker for all emissions
- [ ] Integration tests validate fallback behavior

---

#### Issue 6.2.8 — FAISS Index Circuit Breaker

**Status**: 🔲 NOT STARTED

**Goal**: Implement specialized circuit breaker for FAISS vector index used in R2 similarity search.

**Dossier Reference**: [Section 13.6 Circuit Breaker (External Dependencies)](../pipelines/P03_consolidation_dossier_v2.md#136-circuit-breaker-external-dependencies)

**FAISS Dependency Context**:

P03's R2 phase uses FAISS for fast approximate nearest neighbor search during clustering. When FAISS is unavailable, fallback to brute-force similarity is slower but functional.

| Scenario | FAISS Available | FAISS Unavailable |
|----------|-----------------|-------------------|
| Similarity search | Fast ANN via FAISS | Brute-force PostgreSQL |
| Cluster embeddings | FAISS index | Direct embedding comparison |
| Batch search | Vectorized FAISS | Sequential brute-force |

**Circuit Breaker Configuration** (FAISS-specific):

| Parameter | Value | Reason |
|-----------|-------|--------|
| failure_threshold | 3 | FAISS is more sensitive (lower threshold) |
| reset_timeout_seconds | 30 | Faster recovery attempt |
| success_threshold | 2 | 2 successful calls to close |
| half_open_max_requests | 1 | Single test query |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03CircuitBreaker | Issue 6.2.5 | Base circuit breaker class |
| FAISSIndex | `k0/storage/faiss.py` | FAISS index interface |
| R2Cluster | `k0/pipelines/p03/phases/r2_cluster.py` | Clustering phase |
| st_vec | DB table | Brute-force fallback source |
| MetricsExporter | `k0/obs/metrics.py` | Circuit breaker metrics |

**Work To Do**:

1. [ ] Create `FAISSCircuitBreaker` wrapper in `k0/pipelines/p03/ops/faiss_circuit.py`
2. [ ] Implement `search_with_fallback(query_vec, top_k)` method
3. [ ] Implement `_brute_force_search(query_vec, top_k)` fallback
4. [ ] Implement `_trigger_index_rebuild()` for recovery
5. [ ] Hook R2 phase to use circuit breaker for similarity search
6. [ ] Add FAISS-specific metrics (fallback latency, rebuild triggers)
7. [ ] Implement index health check
8. [ ] Create integration tests with FAISS mock

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/faiss_circuit.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, List, Tuple

from k0.pipelines.p03.ops.circuit_breaker import (
    P03CircuitBreaker,
    P03CircuitBreakerConfig,
    P03CircuitBreakerState,
)
from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg
    import numpy as np


@dataclass
class SimilarityResult:
    """Result of similarity search."""
    entity_id: str
    similarity: float
    method: str  # "faiss" or "brute_force"


class FAISSCircuitBreaker:
    """
    Circuit breaker for FAISS vector index.

    Used by R2 phase for similarity search during clustering.
    Provides fallback to brute-force search when FAISS unavailable.

    Dossier Reference: Section 13.6, Edge Case 13.9
    """

    def __init__(
        self,
        faiss_index,  # FAISS index client
        circuit: P03CircuitBreaker,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._faiss = faiss_index
        self._circuit = circuit
        self._metrics = metrics
        self._rebuild_requested = False

    @property
    def is_open(self) -> bool:
        return self._circuit.state == P03CircuitBreakerState.OPEN

    async def search(
        self,
        query_vec: "np.ndarray",
        top_k: int = 10,
        *,
        space_id: str,
        connection: asyncpg.Connection | None = None,
    ) -> List[SimilarityResult]:
        """
        Search for similar entities with circuit breaker protection.

        Returns:
            List of SimilarityResult, empty if both methods fail.
        """
        start_time = time.monotonic()

        if not self._circuit.should_allow_request():
            # Circuit open - use brute force
            self._emit_metric("p03_faiss_fallback_total", 1.0)
            results = await self._brute_force_search(
                query_vec, top_k, space_id=space_id, connection=connection
            )
            self._observe_latency("brute_force", start_time)
            return results

        try:
            # Try FAISS first
            raw_results = await self._faiss.search(query_vec, top_k, space_id=space_id)
            self._circuit.record_success()

            results = [
                SimilarityResult(
                    entity_id=r["entity_id"],
                    similarity=r["similarity"],
                    method="faiss",
                )
                for r in raw_results
            ]
            self._observe_latency("faiss", start_time)
            return results

        except Exception as e:
            self._circuit.record_failure()
            self._emit_metric(
                "p03_faiss_error_total",
                1.0,
                error_type=type(e).__name__,
            )

            # Fallback to brute force
            self._emit_metric("p03_faiss_fallback_total", 1.0)
            results = await self._brute_force_search(
                query_vec, top_k, space_id=space_id, connection=connection
            )
            self._observe_latency("brute_force", start_time)

            # Request rebuild if not already pending
            if not self._rebuild_requested:
                await self._trigger_index_rebuild()

            return results

    async def _brute_force_search(
        self,
        query_vec: "np.ndarray",
        top_k: int,
        *,
        space_id: str,
        connection: asyncpg.Connection | None = None,
    ) -> List[SimilarityResult]:
        """
        Brute-force similarity search via PostgreSQL.

        Slower but always available as fallback.
        """
        from k0.db.connection import connection_scope
        import numpy as np

        async with connection_scope(connection) as conn:
            # Fetch all embeddings for space (limited for performance)
            rows = await conn.fetch(
                """
                SELECT entity_id, embedding
                FROM st_vec
                WHERE space_id = $1 AND status = 'ACTIVE'
                LIMIT 10000
                """,
                space_id,
            )

        if not rows:
            return []

        # Calculate cosine similarities
        results = []
        query_norm = np.linalg.norm(query_vec)

        for row in rows:
            if row["embedding"] is None:
                continue
            emb = np.array(row["embedding"])
            emb_norm = np.linalg.norm(emb)
            if emb_norm == 0 or query_norm == 0:
                continue

            similarity = float(np.dot(query_vec, emb) / (query_norm * emb_norm))
            results.append(
                SimilarityResult(
                    entity_id=row["entity_id"],
                    similarity=similarity,
                    method="brute_force",
                )
            )

        # Sort by similarity descending, return top_k
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    async def _trigger_index_rebuild(self) -> None:
        """Request FAISS index rebuild job."""
        self._rebuild_requested = True
        self._emit_metric("p03_faiss_rebuild_requested_total", 1.0)
        # In production, this would enqueue a job via k0ctl or job scheduler

    def _observe_latency(self, method: str, start_time: float) -> None:
        """Record search latency."""
        latency = time.monotonic() - start_time
        if self._metrics:
            self._metrics.observe(
                "p03_similarity_search_seconds",
                latency,
                labels={"method": method},
            )

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)


def create_faiss_circuit_breaker(
    faiss_index,
    metrics: Optional[MetricsExporter] = None,
) -> FAISSCircuitBreaker:
    """Factory for FAISS circuit breaker."""
    circuit = P03CircuitBreaker(
        name="faiss_index",
        config=P03CircuitBreakerConfig(
            failure_threshold=3,  # More sensitive
            reset_timeout_seconds=30.0,  # Faster recovery
            success_threshold=2,
        ),
        metrics=metrics,
    )
    return FAISSCircuitBreaker(faiss_index, circuit, metrics)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_faiss_fallback_total | counter | — | Fallbacks to brute-force |
| p03_faiss_error_total | counter | error_type | FAISS errors |
| p03_faiss_rebuild_requested_total | counter | — | Index rebuild requests |
| p03_similarity_search_seconds | histogram | method | Search latency by method |
| p03_faiss_circuit_open_seconds | histogram | — | Duration of OPEN state |

**Acceptance Criteria**:

- [ ] FAISSCircuitBreaker wraps P03CircuitBreaker
- [ ] search() checks circuit before calling FAISS
- [ ] Fallback to brute-force PostgreSQL search
- [ ] Brute-force calculates cosine similarity correctly
- [ ] Index rebuild triggered on persistent failures
- [ ] Latency tracked for both methods
- [ ] All operations emit appropriate metrics
- [ ] R2 phase uses FAISS circuit breaker for similarity search
- [ ] Integration tests validate fallback behavior

---

#### Issue 6.2.9 — Partial Failure Handling Strategies

**Status**: 🔲 NOT STARTED

**Goal**: Implement partial failure handling strategies (COMMIT_PARTIAL, ROLLBACK_ALL, QUARANTINE_BATCH) for batch processing.

**Dossier Reference**: [Section 13.7 Partial Failure Handling](../pipelines/P03_consolidation_dossier_v2.md#137-partial-failure-handling)

**Partial Failure Strategies** (from dossier 13.7):

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **COMMIT_PARTIAL** | Commit successful events, DLQ failed, advance offset | Default for most phases |
| **ROLLBACK_ALL** | Rollback entire batch, no offset advance | When ordering is critical |
| **QUARANTINE_BATCH** | DLQ entire batch, advance offset | When failure rate > 20% |

**Strategy Selection Logic**:

```
if failure_rate > 20%:
    strategy = QUARANTINE_BATCH
elif phase in (R7, R8) and ordering_critical:
    strategy = ROLLBACK_ALL
else:
    strategy = COMMIT_PARTIAL
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| UnitOfWork | `k0/uow/unit_of_work.py` | _commit(),_rollback() |
| OffsetStore | `k0/storage/offsets.py` | upsert() for offset tracking |
| DeadLetterQueue | `k0/storage/dlq.py` | record() for failed events |
| P03DLQStore | Issue 6.2.3 | P03-specific DLQ integration |
| P03Envelope | `k0/pipelines/p03/envelope.py` | Batch container |
| MetricsExporter | `k0/obs/metrics.py` | Strategy metrics |

**Work To Do**:

1. [ ] Create `P03PartialFailureStrategy` enum in `k0/pipelines/p03/ops/partial_failure.py`
2. [ ] Create `P03BatchResult` dataclass for batch processing results
3. [ ] Implement `PartialFailureHandler` class
4. [ ] Implement `select_strategy(failed_count, total_count, phase)` method
5. [ ] Implement `handle_partial(batch_result, strategy)` method
6. [ ] Implement `_commit_partial(batch_result)` helper
7. [ ] Implement `_rollback_all(batch_result)` helper
8. [ ] Implement `_quarantine_batch(batch_result)` helper
9. [ ] Hook phase runners to use partial failure handler
10. [ ] Add strategy metrics (selection counts, outcome)
11. [ ] Create tests for all three strategies

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/partial_failure.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, List

from k0.storage.dlq import DeadLetterQueue
from k0.storage.offsets import OffsetStore
from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class P03PartialFailureStrategy(Enum):
    """Strategies for handling partial batch failures."""
    COMMIT_PARTIAL = "COMMIT_PARTIAL"      # Commit successful, DLQ failed
    ROLLBACK_ALL = "ROLLBACK_ALL"          # Rollback entire batch
    QUARANTINE_BATCH = "QUARANTINE_BATCH"  # DLQ entire batch


@dataclass
class P03EventResult:
    """Result of processing a single event."""
    event_id: str
    success: bool
    error: Optional[Exception] = None
    phase: str = ""


@dataclass
class P03BatchResult:
    """Result of processing a batch of events."""
    cycle_id: str
    phase: str
    tenant_id: str
    space_id: str
    total_count: int
    results: List[P03EventResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def failure_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.failure_count / self.total_count

    @property
    def successful_events(self) -> List[P03EventResult]:
        return [r for r in self.results if r.success]

    @property
    def failed_events(self) -> List[P03EventResult]:
        return [r for r in self.results if not r.success]


# Phases where ordering is critical (use ROLLBACK_ALL on failure)
ORDERING_CRITICAL_PHASES = frozenset({"R7", "R8"})

# Failure rate threshold for QUARANTINE_BATCH
QUARANTINE_THRESHOLD = 0.20  # 20%


class PartialFailureHandler:
    """
    Handle partial batch failures with configurable strategies.

    Dossier Reference: Section 13.7
    """

    def __init__(
        self,
        dlq: DeadLetterQueue,
        offset_store: OffsetStore,
        metrics: Optional[MetricsExporter] = None,
        *,
        quarantine_threshold: float = QUARANTINE_THRESHOLD,
    ):
        self._dlq = dlq
        self._offsets = offset_store
        self._metrics = metrics
        self._quarantine_threshold = quarantine_threshold

    def select_strategy(
        self,
        batch_result: P03BatchResult,
        *,
        force_strategy: Optional[P03PartialFailureStrategy] = None,
    ) -> P03PartialFailureStrategy:
        """
        Select appropriate failure handling strategy.

        Args:
            batch_result: Results from batch processing
            force_strategy: Override automatic selection

        Returns:
            Selected strategy
        """
        if force_strategy:
            return force_strategy

        # Check for high failure rate → quarantine
        if batch_result.failure_rate > self._quarantine_threshold:
            return P03PartialFailureStrategy.QUARANTINE_BATCH

        # Check for ordering-critical phases
        if batch_result.phase in ORDERING_CRITICAL_PHASES:
            if batch_result.failure_count > 0:
                return P03PartialFailureStrategy.ROLLBACK_ALL

        # Default: commit partial
        return P03PartialFailureStrategy.COMMIT_PARTIAL

    async def handle_partial(
        self,
        batch_result: P03BatchResult,
        *,
        strategy: Optional[P03PartialFailureStrategy] = None,
        connection: asyncpg.Connection | None = None,
    ) -> P03PartialFailureStrategy:
        """
        Handle partial failure using selected strategy.

        Args:
            batch_result: Results from batch processing
            strategy: Override strategy (or auto-select)
            connection: Database connection

        Returns:
            Strategy that was applied
        """
        selected = strategy or self.select_strategy(batch_result)

        self._emit_metric(
            "p03_partial_failure_strategy_total",
            1.0,
            strategy=selected.value,
            phase=batch_result.phase,
        )

        if selected == P03PartialFailureStrategy.COMMIT_PARTIAL:
            await self._commit_partial(batch_result, connection=connection)
        elif selected == P03PartialFailureStrategy.ROLLBACK_ALL:
            await self._rollback_all(batch_result, connection=connection)
        else:  # QUARANTINE_BATCH
            await self._quarantine_batch(batch_result, connection=connection)

        return selected

    async def _commit_partial(
        self,
        batch_result: P03BatchResult,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """
        Commit successful events, send failed to DLQ, advance offset.

        K0 Integration:
        - UnitOfWork._commit() for successful events
        - DLQStore.record() for failed events
        - OffsetStore.upsert() to advance offset
        """
        # Record failed events to DLQ
        for event_result in batch_result.failed_events:
            await self._record_to_dlq(
                batch_result, event_result, connection=connection
            )

        # Advance offset to last successful event
        if batch_result.successful_events:
            last_success = batch_result.successful_events[-1]
            await self._offsets.upsert(
                consumer_id=f"p03_{batch_result.phase}",
                topic="st_hipp_events",
                offset=last_success.event_id,
                connection=connection,
            )

        self._emit_metric(
            "p03_partial_commit_total",
            1.0,
            success_count=str(batch_result.success_count),
            failure_count=str(batch_result.failure_count),
        )

    async def _rollback_all(
        self,
        batch_result: P03BatchResult,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """
        Rollback entire batch, do not advance offset.

        K0 Integration:
        - UnitOfWork._rollback() for transaction rollback
        - Offset NOT advanced (retry entire batch next cycle)
        """
        # Note: Actual rollback happens at transaction level
        # This method records the decision and emits metrics

        self._emit_metric(
            "p03_rollback_all_total",
            1.0,
            phase=batch_result.phase,
            total_count=str(batch_result.total_count),
        )

    async def _quarantine_batch(
        self,
        batch_result: P03BatchResult,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """
        Send entire batch to DLQ with quarantine status, advance offset.

        K0 Integration:
        - DLQStore.record() for all events with QUARANTINE status
        - OffsetStore.upsert() to advance offset
        """
        # Record all events to DLQ
        for event_result in batch_result.results:
            await self._record_to_dlq(
                batch_result,
                event_result,
                status="MANUAL_REVIEW",
                connection=connection,
            )

        # Advance offset past entire batch
        if batch_result.results:
            last_event = batch_result.results[-1]
            await self._offsets.upsert(
                consumer_id=f"p03_{batch_result.phase}",
                topic="st_hipp_events",
                offset=last_event.event_id,
                connection=connection,
            )

        self._emit_metric(
            "p03_quarantine_batch_total",
            1.0,
            phase=batch_result.phase,
            failure_rate=f"{batch_result.failure_rate:.2f}",
        )

    async def _record_to_dlq(
        self,
        batch_result: P03BatchResult,
        event_result: P03EventResult,
        *,
        status: str = "PENDING",
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Record single event to DLQ."""
        from k0.storage.dlq import DeadLetter
        from k0.ulid import now_ms

        now = now_ms()
        letter = DeadLetter(
            id=None,
            wal_pos=None,
            tenant_id=batch_result.tenant_id,
            space_id=batch_result.space_id,
            driver="p03_consolidation",
            op_kind=batch_result.phase,
            fingerprint=f"{batch_result.cycle_id}:{event_result.event_id}",
            payload=b"{}",  # Minimal payload for now
            reason=str(event_result.error) if event_result.error else "batch_quarantine",
            retries=0,
            requeue_seq=0,
            first_failure_ts=str(now),
            last_failure_ts=str(now),
            state=status,
        )
        await self._dlq.record(letter, connection=connection)

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_partial_failure_strategy_total | counter | strategy, phase | Strategy selection counts |
| p03_partial_commit_total | counter | success_count, failure_count | COMMIT_PARTIAL operations |
| p03_rollback_all_total | counter | phase, total_count | ROLLBACK_ALL operations |
| p03_quarantine_batch_total | counter | phase, failure_rate | QUARANTINE_BATCH operations |

**Acceptance Criteria**:

- [ ] P03PartialFailureStrategy enum with all three strategies
- [ ] P03BatchResult captures success/failure counts per event
- [ ] select_strategy() correctly applies threshold logic
- [ ] COMMIT_PARTIAL: successful committed, failed to DLQ, offset advanced
- [ ] ROLLBACK_ALL: no commit, no offset advance (retry next cycle)
- [ ] QUARANTINE_BATCH: all events to DLQ, offset advanced
- [ ] Ordering-critical phases (R7, R8) use ROLLBACK_ALL on failure
- [ ] Quarantine triggered when failure rate > 20%
- [ ] All strategies emit appropriate metrics
- [ ] Integration tests validate all three strategies

---

#### Issue 6.2.10 — st_feedback_quarantine Schema

**Status**: 🔲 NOT STARTED

**Goal**: Create Alembic migration for st_feedback_quarantine table and implement quarantine detector.

**Dossier Reference**: [Section 6.21 st_feedback_quarantine (Suspicious Signals)](../pipelines/P03_consolidation_dossier_v2.md#621-st_feedback_quarantine-suspicious-signals)

**Schema Definition** (from dossier 6.21.1):

```sql
CREATE TABLE st_feedback_quarantine (
  -- Identity
  quarantine_id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL,              -- Reference to st_feedback_signals

  -- Context
  space_id TEXT NOT NULL,

  -- Detection details
  reason TEXT NOT NULL,                 -- 'RATE_LIMIT', 'VELOCITY_SPIKE', 'ANOMALY', 'ENTROPY'
  severity TEXT NOT NULL,               -- 'LOW', 'MEDIUM', 'HIGH'
  detected_at BIGINT NOT NULL,

  -- Review process
  reviewed_at BIGINT,                   -- When reviewed (nullable)
  reviewed_by TEXT,                     -- Reviewer ID (nullable)
  decision TEXT,                        -- 'RELEASE', 'DISCARD', NULL

  -- Auto-release
  auto_release_at BIGINT NOT NULL       -- 48h after detected_at
);
```

**Quarantine Reasons**:

| Reason | Severity | Description | Auto-Release |
|--------|----------|-------------|--------------|
| RATE_LIMIT | LOW | User exceeded feedback rate limit | Yes (48h) |
| VELOCITY_SPIKE | MEDIUM | Sudden volume spike detected | Yes (48h) |
| ANOMALY | HIGH | Anomalous pattern detected | No (manual) |
| ENTROPY | HIGH | Unusually high entropy in signals | No (manual) |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Alembic migrations | `k0/migrations/versions/` | Migration pattern |
| st_feedback_signals | M2 migration | Foreign key reference |
| RLS policies | Existing patterns | Policy template |
| MetricsExporter | `k0/obs/metrics.py` | Quarantine metrics |

**Work To Do**:

1. [ ] Create migration `0050_st_feedback_quarantine.py`
2. [ ] Define table with all columns from dossier
3. [ ] Create indexes for efficient queries
4. [ ] Create RLS policy for space isolation
5. [ ] Grant permissions to p03_role and security_role
6. [ ] Create `QuarantineDetector` class in `k0/pipelines/p03/feedback/quarantine_detector.py`
7. [ ] Implement `quarantine_signal(signal_id, reason, severity)` method
8. [ ] Implement `check_rate_limit(space_id, user_id)` method
9. [ ] Implement `check_velocity_spike(space_id)` method
10. [ ] Add quarantine metrics (total quarantined, pending reviews)
11. [ ] Create tests for migration and detector

**Implementation Pattern**:

```python
# k0/migrations/versions/0050_st_feedback_quarantine.py
"""Create st_feedback_quarantine table.

Revision ID: 0050
Revises: 0049
Create Date: 2026-01-04

Dossier Reference: Section 6.21 st_feedback_quarantine
"""

from alembic import op
import sqlalchemy as sa

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create table
    op.execute("""
        CREATE TABLE st_feedback_quarantine (
            -- Identity
            quarantine_id TEXT PRIMARY KEY,
            signal_id TEXT NOT NULL,

            -- Context
            space_id TEXT NOT NULL,

            -- Detection details
            reason TEXT NOT NULL CHECK (reason IN (
                'RATE_LIMIT', 'VELOCITY_SPIKE', 'ANOMALY', 'ENTROPY'
            )),
            severity TEXT NOT NULL CHECK (severity IN (
                'LOW', 'MEDIUM', 'HIGH'
            )),
            detected_at BIGINT NOT NULL,

            -- Review process
            reviewed_at BIGINT,
            reviewed_by TEXT,
            decision TEXT CHECK (decision IN (
                'RELEASE', 'DISCARD'
            ) OR decision IS NULL),

            -- Auto-release
            auto_release_at BIGINT NOT NULL
        )
    """)

    # Indexes for efficient quarantine management
    op.execute("""
        CREATE INDEX idx_quarantine_space_status
        ON st_feedback_quarantine(space_id, decision)
        WHERE decision IS NULL
    """)

    op.execute("""
        CREATE INDEX idx_quarantine_auto_release
        ON st_feedback_quarantine(auto_release_at)
        WHERE decision IS NULL
    """)

    op.execute("""
        CREATE INDEX idx_quarantine_signal
        ON st_feedback_quarantine(signal_id)
    """)

    op.execute("""
        CREATE INDEX idx_quarantine_severity
        ON st_feedback_quarantine(severity, detected_at DESC)
        WHERE decision IS NULL
    """)

    # RLS policy for multi-tenant isolation
    op.execute("""
        ALTER TABLE st_feedback_quarantine ENABLE ROW LEVEL SECURITY
    """)

    op.execute("""
        CREATE POLICY quarantine_isolation
        ON st_feedback_quarantine
        FOR ALL
        USING (space_id = current_setting('app.current_space_id', true)::TEXT)
    """)

    # Grant permissions
    op.execute("""
        GRANT SELECT, INSERT, UPDATE ON st_feedback_quarantine TO p03_role
    """)

    op.execute("""
        GRANT SELECT ON st_feedback_quarantine TO security_role
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS st_feedback_quarantine CASCADE")
```

```python
# k0/pipelines/p03/feedback/quarantine_detector.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter
from k0.ulid import generate_ulid

if TYPE_CHECKING:
    import asyncpg


class QuarantineReason(Enum):
    """Reasons for quarantining a feedback signal."""
    RATE_LIMIT = "RATE_LIMIT"
    VELOCITY_SPIKE = "VELOCITY_SPIKE"
    ANOMALY = "ANOMALY"
    ENTROPY = "ENTROPY"


class QuarantineSeverity(Enum):
    """Severity levels for quarantined signals."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class QuarantineResult:
    """Result of quarantine operation."""
    quarantined: bool
    quarantine_id: Optional[str] = None
    reason: Optional[QuarantineReason] = None
    severity: Optional[QuarantineSeverity] = None


# Reason → default severity mapping
REASON_SEVERITY_MAP = {
    QuarantineReason.RATE_LIMIT: QuarantineSeverity.LOW,
    QuarantineReason.VELOCITY_SPIKE: QuarantineSeverity.MEDIUM,
    QuarantineReason.ANOMALY: QuarantineSeverity.HIGH,
    QuarantineReason.ENTROPY: QuarantineSeverity.HIGH,
}

# Auto-release period in seconds (48 hours)
AUTO_RELEASE_SECONDS = 48 * 60 * 60


class QuarantineDetector:
    """
    Detect and quarantine suspicious feedback signals.

    Dossier Reference: Section 6.21
    """

    def __init__(
        self,
        metrics: Optional[MetricsExporter] = None,
        *,
        rate_limit_per_minute: int = 100,
        velocity_spike_multiplier: float = 10.0,
    ):
        self._metrics = metrics
        self._rate_limit = rate_limit_per_minute
        self._velocity_multiplier = velocity_spike_multiplier

    async def check_and_quarantine(
        self,
        signal_id: str,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> QuarantineResult:
        """
        Check signal for quarantine conditions and quarantine if needed.

        Returns:
            QuarantineResult with quarantine status and details.
        """
        # Check rate limit
        if await self._check_rate_limit(space_id, user_id, connection=connection):
            return await self._quarantine_signal(
                signal_id,
                space_id,
                QuarantineReason.RATE_LIMIT,
                connection=connection,
            )

        # Check velocity spike
        if await self._check_velocity_spike(space_id, connection=connection):
            return await self._quarantine_signal(
                signal_id,
                space_id,
                QuarantineReason.VELOCITY_SPIKE,
                connection=connection,
            )

        return QuarantineResult(quarantined=False)

    async def _check_rate_limit(
        self,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Check if user has exceeded rate limit."""
        import time

        now = int(time.time())
        window_start = now - 60  # 1 minute window

        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as signal_count
            FROM st_feedback_signals
            WHERE space_id = $1
              AND user_id = $2
              AND created_at > $3
            """,
            space_id,
            user_id,
            window_start,
        )

        return row["signal_count"] >= self._rate_limit

    async def _check_velocity_spike(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Check for sudden volume spike in feedback signals."""
        import time

        now = int(time.time())
        recent_window = now - (5 * 60)  # Last 5 minutes
        baseline_window = now - (60 * 60)  # Last hour

        recent = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_signals
            WHERE space_id = $1 AND created_at > $2
            """,
            space_id,
            recent_window,
        )

        baseline = await connection.fetchrow(
            """
            SELECT COUNT(*) as count
            FROM st_feedback_signals
            WHERE space_id = $1 AND created_at > $2
            """,
            space_id,
            baseline_window,
        )

        recent_rate = recent["count"] / 5.0  # per minute
        baseline_rate = baseline["count"] / 60.0  # per minute

        # Spike if 10x baseline (and baseline > 0)
        if baseline_rate > 0:
            return recent_rate > (baseline_rate * self._velocity_multiplier)
        return False

    async def _quarantine_signal(
        self,
        signal_id: str,
        space_id: str,
        reason: QuarantineReason,
        *,
        severity: Optional[QuarantineSeverity] = None,
        connection: asyncpg.Connection,
    ) -> QuarantineResult:
        """Record quarantine entry for signal."""
        import time

        severity = severity or REASON_SEVERITY_MAP[reason]
        quarantine_id = f"quarantine_{generate_ulid()}"
        detected_at = int(time.time())
        auto_release_at = detected_at + AUTO_RELEASE_SECONDS

        await connection.execute(
            """
            INSERT INTO st_feedback_quarantine (
                quarantine_id, signal_id, space_id, reason, severity,
                detected_at, auto_release_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            quarantine_id,
            signal_id,
            space_id,
            reason.value,
            severity.value,
            detected_at,
            auto_release_at,
        )

        self._emit_metric(
            "p03_quarantine_signals_total",
            1.0,
            reason=reason.value,
            severity=severity.value,
        )

        # Alert on high severity
        if severity == QuarantineSeverity.HIGH:
            self._emit_metric(
                "p03_quarantine_high_severity_total",
                1.0,
                reason=reason.value,
            )

        return QuarantineResult(
            quarantined=True,
            quarantine_id=quarantine_id,
            reason=reason,
            severity=severity,
        )

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_quarantine_signals_total | counter | reason, severity | Signals quarantined |
| p03_quarantine_high_severity_total | counter | reason | High severity quarantines |
| p03_quarantine_pending_reviews | gauge | severity | Pending reviews count |

**Acceptance Criteria**:

- [ ] Migration creates st_feedback_quarantine with correct schema
- [ ] All columns from dossier 6.21.1 included
- [ ] Indexes created for efficient queries
- [ ] RLS policy enforces space isolation
- [ ] Permissions granted to p03_role and security_role
- [ ] QuarantineDetector implements rate limit check
- [ ] QuarantineDetector implements velocity spike detection
- [ ] Signals quarantined with correct reason and severity
- [ ] Auto-release timestamp set to 48h from detection
- [ ] HIGH severity quarantines trigger alerts
- [ ] All quarantine operations emit metrics
- [ ] Migration can be rolled back cleanly

---

#### Issue 6.2.11 — FeedbackRateLimiter Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement dedicated rate limiter class for feedback signals with configurable per-user/device limits and sliding window enforcement.

**Dossier Reference**: [Section 6.21.4 Detection Algorithms - Rate Limiting](../pipelines/P03_consolidation_dossier_v2.md#6214-detection-algorithms)

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| QuarantineDetector | `k0/pipelines/p03/feedback/quarantine_detector.py` | Uses rate limit check inline |
| st_feedback_signals | Migration 0042 | Source table for counting signals |
| MetricsExporter | `k0/obs/metrics.py` | Rate limit metrics emission |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/feedback/rate_limiter.py` with `FeedbackRateLimiter` class
2. [ ] Implement sliding window algorithm with configurable window size (default: 60 seconds)
3. [ ] Implement per-user limit (default: 100 signals per minute)
4. [ ] Implement per-device limit (optional, separate from user)
5. [ ] Add `check_rate_limit()` async method returning `RateLimitResult`
6. [ ] Add `get_remaining_quota()` method for API rate limit headers
7. [ ] Implement `RateLimitResult` dataclass with `exceeded`, `remaining`, `reset_at` fields
8. [ ] Refactor `QuarantineDetector._check_rate_limit()` to use `FeedbackRateLimiter`
9. [ ] Add metrics for rate limit checks and violations
10. [ ] Create tests: `tests/k0/pipelines/p03/feedback/test_rate_limiter.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/feedback/rate_limiter.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    exceeded: bool
    current_count: int
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp when window resets
    window_size: int  # Window size in seconds


class FeedbackRateLimiter:
    """
    Rate limit feedback signals per user/device.

    Uses sliding window algorithm with configurable limits.
    Dossier Reference: Section 6.21.4
    """

    def __init__(
        self,
        *,
        max_signals_per_minute: int = 100,
        window_size_seconds: int = 60,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._max_per_minute = max_signals_per_minute
        self._window_size = window_size_seconds
        self._metrics = metrics

    async def check_rate_limit(
        self,
        space_id: str,
        user_id: str,
        *,
        device_id: Optional[str] = None,
        connection: asyncpg.Connection,
    ) -> RateLimitResult:
        """
        Check if user/device has exceeded rate limit.

        Args:
            space_id: Space context
            user_id: User to check
            device_id: Optional device for device-specific limits
            connection: Database connection

        Returns:
            RateLimitResult with exceeded status and remaining quota.
        """
        now = int(time.time())
        window_start = now - self._window_size

        # Count signals in current window
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as signal_count
            FROM st_feedback_signals
            WHERE space_id = $1
              AND user_id = $2
              AND created_at > $3
            """,
            space_id,
            user_id,
            window_start,
        )

        current_count = row["signal_count"]
        exceeded = current_count >= self._max_per_minute
        remaining = max(0, self._max_per_minute - current_count)
        reset_at = now + self._window_size

        # Emit metrics
        self._emit_metric(
            "p03_rate_limit_checks_total",
            1.0,
            exceeded=str(exceeded).lower(),
        )

        if exceeded:
            self._emit_metric(
                "p03_rate_limit_exceeded_total",
                1.0,
                user_id=user_id[:8],  # Truncate for cardinality
            )

        return RateLimitResult(
            exceeded=exceeded,
            current_count=current_count,
            limit=self._max_per_minute,
            remaining=remaining,
            reset_at=reset_at,
            window_size=self._window_size,
        )

    async def get_remaining_quota(
        self,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> tuple[int, int]:
        """
        Get remaining quota for rate limit headers.

        Returns:
            Tuple of (remaining, reset_at) for X-RateLimit headers.
        """
        result = await self.check_rate_limit(
            space_id,
            user_id,
            connection=connection,
        )
        return result.remaining, result.reset_at

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_rate_limit_checks_total | counter | exceeded | Rate limit checks performed |
| p03_rate_limit_exceeded_total | counter | user_id | Rate limit violations |

**Acceptance Criteria**:

- [ ] `FeedbackRateLimiter` class created with configurable limits
- [ ] Sliding window algorithm correctly implemented
- [ ] `check_rate_limit()` returns accurate remaining quota
- [ ] `get_remaining_quota()` provides API rate limit header values
- [ ] `QuarantineDetector` refactored to use `FeedbackRateLimiter`
- [ ] Rate limit metrics emitted on every check
- [ ] ≥95% test coverage for rate limiter module

---

#### Issue 6.2.12 — VelocityAnomalyDetector Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement velocity spike detection to identify sudden surges in feedback signal volume that may indicate manipulation or bot activity.

**Dossier Reference**: [Section 6.21.4 Detection Algorithms - Velocity Anomaly Detection](../pipelines/P03_consolidation_dossier_v2.md#6214-detection-algorithms)

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| QuarantineDetector | `k0/pipelines/p03/feedback/quarantine_detector.py` | Uses velocity check inline |
| st_feedback_signals | Migration 0042 | Source table for counting signals |
| MetricsExporter | `k0/obs/metrics.py` | Velocity metrics emission |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/feedback/velocity_detector.py` with `VelocityAnomalyDetector` class
2. [ ] Implement baseline calculation (last hour average rate)
3. [ ] Implement recent rate calculation (last 5 minutes)
4. [ ] Implement spike detection with configurable multiplier (default: 10x baseline)
5. [ ] Add `detect_velocity_spike()` async method returning `VelocityResult`
6. [ ] Add per-space and per-user velocity tracking
7. [ ] Implement `VelocityResult` dataclass with `is_spike`, `recent_rate`, `baseline_rate`, `multiplier` fields
8. [ ] Refactor `QuarantineDetector._check_velocity_spike()` to use `VelocityAnomalyDetector`
9. [ ] Add metrics for velocity checks and detected spikes
10. [ ] Create tests: `tests/k0/pipelines/p03/feedback/test_velocity_detector.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/feedback/velocity_detector.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


@dataclass
class VelocityResult:
    """Result of velocity spike detection."""
    is_spike: bool
    recent_rate: float  # Signals per minute (last 5 min)
    baseline_rate: float  # Signals per minute (last hour average)
    spike_multiplier: float  # How many times over baseline
    threshold_multiplier: float  # Configured threshold


class VelocityAnomalyDetector:
    """
    Detect sudden spikes in feedback signal volume.

    Compares recent rate (last 5 minutes) to baseline rate (last hour).
    Spike detected if recent > baseline * multiplier.

    Dossier Reference: Section 6.21.4
    """

    def __init__(
        self,
        *,
        spike_multiplier: float = 10.0,
        recent_window_minutes: int = 5,
        baseline_window_minutes: int = 60,
        min_baseline_count: int = 10,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._spike_multiplier = spike_multiplier
        self._recent_window = recent_window_minutes * 60  # Convert to seconds
        self._baseline_window = baseline_window_minutes * 60
        self._min_baseline_count = min_baseline_count
        self._metrics = metrics

    async def detect_velocity_spike(
        self,
        space_id: str,
        *,
        user_id: Optional[str] = None,
        connection: asyncpg.Connection,
    ) -> VelocityResult:
        """
        Detect if current velocity exceeds baseline.

        Args:
            space_id: Space to check
            user_id: Optional user for user-specific detection
            connection: Database connection

        Returns:
            VelocityResult with spike status and rate details.
        """
        now = int(time.time())
        recent_start = now - self._recent_window
        baseline_start = now - self._baseline_window

        # Build query based on whether user_id is provided
        if user_id:
            recent_row = await connection.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM st_feedback_signals
                WHERE space_id = $1 AND user_id = $2 AND created_at > $3
                """,
                space_id,
                user_id,
                recent_start,
            )
            baseline_row = await connection.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM st_feedback_signals
                WHERE space_id = $1 AND user_id = $2 AND created_at > $3
                """,
                space_id,
                user_id,
                baseline_start,
            )
        else:
            recent_row = await connection.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM st_feedback_signals
                WHERE space_id = $1 AND created_at > $2
                """,
                space_id,
                recent_start,
            )
            baseline_row = await connection.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM st_feedback_signals
                WHERE space_id = $1 AND created_at > $2
                """,
                space_id,
                baseline_start,
            )

        recent_count = recent_row["count"]
        baseline_count = baseline_row["count"]

        # Calculate rates (per minute)
        recent_rate = recent_count / (self._recent_window / 60.0)
        baseline_rate = baseline_count / (self._baseline_window / 60.0)

        # Determine if spike
        is_spike = False
        spike_multiplier = 0.0

        if baseline_rate > 0 and baseline_count >= self._min_baseline_count:
            spike_multiplier = recent_rate / baseline_rate
            is_spike = spike_multiplier >= self._spike_multiplier

        # Emit metrics
        self._emit_metric(
            "p03_velocity_checks_total",
            1.0,
            is_spike=str(is_spike).lower(),
        )

        if is_spike:
            self._emit_metric(
                "p03_velocity_spikes_total",
                1.0,
                space_id=space_id[:8],
            )
            self._emit_metric(
                "p03_velocity_spike_multiplier",
                spike_multiplier,
            )

        return VelocityResult(
            is_spike=is_spike,
            recent_rate=recent_rate,
            baseline_rate=baseline_rate,
            spike_multiplier=spike_multiplier,
            threshold_multiplier=self._spike_multiplier,
        )

    async def get_current_velocity(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> float:
        """Get current velocity (signals per minute) for monitoring."""
        result = await self.detect_velocity_spike(
            space_id,
            connection=connection,
        )
        return result.recent_rate

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_velocity_checks_total | counter | is_spike | Velocity checks performed |
| p03_velocity_spikes_total | counter | space_id | Velocity spikes detected |
| p03_velocity_spike_multiplier | gauge | - | Current spike multiplier |

**Acceptance Criteria**:

- [ ] `VelocityAnomalyDetector` class created with configurable thresholds
- [ ] Baseline rate correctly calculated from last hour
- [ ] Recent rate correctly calculated from last 5 minutes
- [ ] Spike detection uses configurable multiplier (default: 10x)
- [ ] Minimum baseline count prevents false positives on low volume
- [ ] `QuarantineDetector` refactored to use `VelocityAnomalyDetector`
- [ ] Velocity metrics emitted on every check
- [ ] ≥95% test coverage for velocity detector module

---

#### Issue 6.2.13 — P03LearningAnomalyDetector Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement anomaly detection for feedback signal content that identifies suspicious patterns like low entropy, repetitive content, or statistical outliers.

**Dossier Reference**: [Section 6.21 st_feedback_quarantine](../pipelines/P03_consolidation_dossier_v2.md#621-st_feedback_quarantine)

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| QuarantineDetector | `k0/pipelines/p03/feedback/quarantine_detector.py` | ANOMALY and ENTROPY reasons |
| QuarantineReason | Same file | Enum values for anomaly types |
| MetricsExporter | `k0/obs/metrics.py` | Anomaly metrics emission |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/feedback/anomaly_detector.py` with `P03LearningAnomalyDetector` class
2. [ ] Implement entropy check for signal content (Shannon entropy)
3. [ ] Implement repetition detector for duplicate content patterns
4. [ ] Implement statistical outlier detection using Z-score
5. [ ] Add `detect_anomalies()` async method returning `AnomalyResult`
6. [ ] Define configurable thresholds for each anomaly type
7. [ ] Implement `AnomalyResult` dataclass with anomaly types and scores
8. [ ] Integrate with `QuarantineDetector` for ANOMALY and ENTROPY reasons
9. [ ] Add metrics for anomaly detection
10. [ ] Create tests: `tests/k0/pipelines/p03/feedback/test_anomaly_detector.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/feedback/anomaly_detector.py
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class AnomalyType(Enum):
    """Types of detected anomalies."""
    LOW_ENTROPY = "LOW_ENTROPY"
    REPETITIVE_CONTENT = "REPETITIVE_CONTENT"
    STATISTICAL_OUTLIER = "STATISTICAL_OUTLIER"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    is_anomalous: bool
    anomaly_types: list[AnomalyType] = field(default_factory=list)
    entropy_score: Optional[float] = None
    repetition_score: Optional[float] = None
    z_score: Optional[float] = None
    details: dict = field(default_factory=dict)


class P03LearningAnomalyDetector:
    """
    Detect anomalies in feedback signal content.

    Checks for:
    - Low entropy content (bot-like repetitive text)
    - Duplicate/repetitive feedback patterns
    - Statistical outliers in signal characteristics

    Dossier Reference: Section 6.21
    """

    def __init__(
        self,
        *,
        min_entropy_threshold: float = 2.0,
        repetition_threshold: float = 0.8,
        z_score_threshold: float = 3.0,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._min_entropy = min_entropy_threshold
        self._repetition_threshold = repetition_threshold
        self._z_score_threshold = z_score_threshold
        self._metrics = metrics

    async def detect_anomalies(
        self,
        signal_id: str,
        content: str,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> AnomalyResult:
        """
        Detect anomalies in feedback signal.

        Args:
            signal_id: Signal ID for context
            content: Signal content to analyze
            space_id: Space context
            user_id: User who submitted signal
            connection: Database connection

        Returns:
            AnomalyResult with detected anomalies and scores.
        """
        anomaly_types: list[AnomalyType] = []
        details: dict = {}

        # Check entropy
        entropy = self._calculate_entropy(content)
        if entropy < self._min_entropy and len(content) > 10:
            anomaly_types.append(AnomalyType.LOW_ENTROPY)
            details["entropy_reason"] = f"Entropy {entropy:.2f} below threshold {self._min_entropy}"

        # Check for repetitive content from same user
        repetition_score = await self._check_repetition(
            content, space_id, user_id, connection=connection
        )
        if repetition_score >= self._repetition_threshold:
            anomaly_types.append(AnomalyType.REPETITIVE_CONTENT)
            details["repetition_reason"] = f"Similarity {repetition_score:.2f} exceeds threshold"

        # Check for statistical outliers
        z_score = await self._calculate_z_score(
            content, space_id, connection=connection
        )
        if z_score and abs(z_score) > self._z_score_threshold:
            anomaly_types.append(AnomalyType.STATISTICAL_OUTLIER)
            details["z_score_reason"] = f"Z-score {z_score:.2f} exceeds threshold"

        is_anomalous = len(anomaly_types) > 0

        # Emit metrics
        self._emit_metric(
            "p03_anomaly_checks_total",
            1.0,
            is_anomalous=str(is_anomalous).lower(),
        )

        for anomaly_type in anomaly_types:
            self._emit_metric(
                "p03_anomalies_detected_total",
                1.0,
                type=anomaly_type.value,
            )

        return AnomalyResult(
            is_anomalous=is_anomalous,
            anomaly_types=anomaly_types,
            entropy_score=entropy,
            repetition_score=repetition_score,
            z_score=z_score,
            details=details,
        )

    def _calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of text."""
        if not text:
            return 0.0

        # Count character frequencies
        counter = Counter(text.lower())
        length = len(text)

        # Calculate entropy
        entropy = 0.0
        for count in counter.values():
            probability = count / length
            if probability > 0:
                entropy -= probability * math.log2(probability)

        return entropy

    async def _check_repetition(
        self,
        content: str,
        space_id: str,
        user_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> float:
        """Check for repetitive content from same user (last hour)."""
        import time

        now = int(time.time())
        window_start = now - 3600  # 1 hour

        # Get recent signals from same user
        rows = await connection.fetch(
            """
            SELECT content
            FROM st_feedback_signals
            WHERE space_id = $1
              AND user_id = $2
              AND created_at > $3
            ORDER BY created_at DESC
            LIMIT 20
            """,
            space_id,
            user_id,
            window_start,
        )

        if not rows:
            return 0.0

        # Calculate max similarity to any recent signal
        max_similarity = 0.0
        content_lower = content.lower()

        for row in rows:
            if row["content"]:
                other_lower = row["content"].lower()
                similarity = self._jaccard_similarity(content_lower, other_lower)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    async def _calculate_z_score(
        self,
        content: str,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> Optional[float]:
        """Calculate Z-score of content length vs space average."""
        import time

        now = int(time.time())
        window_start = now - 86400  # 24 hours

        # Get length statistics for space
        row = await connection.fetchrow(
            """
            SELECT
                AVG(LENGTH(content)) as avg_length,
                STDDEV(LENGTH(content)) as stddev_length,
                COUNT(*) as sample_count
            FROM st_feedback_signals
            WHERE space_id = $1
              AND created_at > $2
              AND content IS NOT NULL
            """,
            space_id,
            window_start,
        )

        if not row or row["sample_count"] < 10:
            return None

        avg_length = row["avg_length"] or 0
        stddev_length = row["stddev_length"] or 1

        if stddev_length == 0:
            return None

        # Calculate Z-score
        content_length = len(content)
        z_score = (content_length - avg_length) / stddev_length

        return z_score

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_anomaly_checks_total | counter | is_anomalous | Anomaly checks performed |
| p03_anomalies_detected_total | counter | type | Anomalies by type |

**Acceptance Criteria**:

- [ ] `P03LearningAnomalyDetector` class created with configurable thresholds
- [ ] Shannon entropy calculation correctly identifies low-entropy content
- [ ] Jaccard similarity detects repetitive content from same user
- [ ] Z-score calculation identifies statistical outliers
- [ ] All anomaly types emit appropriate metrics
- [ ] Configurable thresholds for each detection method
- [ ] ≥95% test coverage for anomaly detector module

---

#### Issue 6.2.14 — Quarantine Auto-Release Job Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement scheduled job that automatically releases quarantined signals after 48h retention period expires, allowing them to be processed normally.

**Dossier Reference**: [Section 6.21.3 Auto-Release](../pipelines/P03_consolidation_dossier_v2.md#6213-quarantine-process)

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| st_feedback_quarantine | Migration 0050 | `auto_release_at` column |
| QuarantineDetector | `k0/pipelines/p03/feedback/quarantine_detector.py` | AUTO_RELEASE_SECONDS constant |
| K0 Scheduler | `k0/scheduler/scheduler.py` | Job scheduling infrastructure |
| MetricsExporter | `k0/obs/metrics.py` | Auto-release metrics |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/maintenance/quarantine_cleanup.py` with `QuarantineAutoReleaseJob` class
2. [ ] Implement `auto_release_quarantined_signals()` async function per dossier
3. [ ] Update `st_feedback_quarantine` with decision='RELEASE', reviewed_by='AUTO'
4. [ ] Update corresponding `st_feedback_signals.quarantine_status` to 'RELEASED'
5. [ ] Implement batch processing with configurable batch size (default: 100)
6. [ ] Add job registration with K0 scheduler (run every 15 minutes)
7. [ ] Add metrics for auto-release counts and processing time
8. [ ] Handle edge cases: already reviewed signals, missing source signals
9. [ ] Create tests: `tests/k0/pipelines/p03/maintenance/test_quarantine_cleanup.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/maintenance/quarantine_cleanup.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import TracerFactory

if TYPE_CHECKING:
    import asyncpg


@dataclass
class AutoReleaseResult:
    """Result of auto-release job execution."""
    signals_released: int
    signals_failed: int
    duration_ms: float
    errors: list[str]


class QuarantineAutoReleaseJob:
    """
    Automatically release quarantined signals after retention period.

    Runs periodically to release signals where:
    - auto_release_at <= current_time
    - decision IS NULL (not manually reviewed)

    Dossier Reference: Section 6.21.3
    """

    JOB_NAME = "p03_quarantine_auto_release"
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_INTERVAL_SECONDS = 900  # 15 minutes

    def __init__(
        self,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        metrics: Optional[MetricsExporter] = None,
        tracer: Optional[TracerFactory] = None,
    ):
        self._batch_size = batch_size
        self._metrics = metrics
        self._tracer = tracer

    async def run(
        self,
        *,
        connection: asyncpg.Connection,
    ) -> AutoReleaseResult:
        """
        Execute auto-release job.

        Returns:
            AutoReleaseResult with release counts and timing.
        """
        start_time = time.monotonic()
        released_count = 0
        failed_count = 0
        errors: list[str] = []

        now = int(time.time())

        # Get signals ready for auto-release (batch processing)
        while True:
            ready_signals = await connection.fetch(
                """
                SELECT quarantine_id, signal_id, space_id
                FROM st_feedback_quarantine
                WHERE decision IS NULL
                  AND auto_release_at <= $1
                ORDER BY auto_release_at ASC
                LIMIT $2
                """,
                now,
                self._batch_size,
            )

            if not ready_signals:
                break

            for signal in ready_signals:
                try:
                    await self._release_signal(
                        signal["quarantine_id"],
                        signal["signal_id"],
                        now,
                        connection=connection,
                    )
                    released_count += 1
                except Exception as e:
                    failed_count += 1
                    errors.append(
                        f"Failed to release {signal['quarantine_id']}: {e}"
                    )

        duration_ms = (time.monotonic() - start_time) * 1000

        # Emit metrics
        self._emit_metrics(released_count, failed_count, duration_ms)

        return AutoReleaseResult(
            signals_released=released_count,
            signals_failed=failed_count,
            duration_ms=duration_ms,
            errors=errors,
        )

    async def _release_signal(
        self,
        quarantine_id: str,
        signal_id: str,
        reviewed_at: int,
        *,
        connection: asyncpg.Connection,
    ) -> None:
        """Release a single quarantined signal."""
        # Update quarantine record
        await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = 'AUTO',
                decision = 'RELEASE'
            WHERE quarantine_id = $2
              AND decision IS NULL
            """,
            reviewed_at,
            quarantine_id,
        )

        # Update source signal status
        await connection.execute(
            """
            UPDATE st_feedback_signals
            SET quarantine_status = 'RELEASED'
            WHERE signal_id = $1
            """,
            signal_id,
        )

    def _emit_metrics(
        self,
        released: int,
        failed: int,
        duration_ms: float,
    ) -> None:
        if not self._metrics:
            return

        self._metrics.counter(
            "p03_quarantine_auto_released_total",
            released,
        )

        if failed > 0:
            self._metrics.counter(
                "p03_quarantine_auto_release_failures_total",
                failed,
            )

        self._metrics.histogram(
            "p03_quarantine_auto_release_duration_seconds",
            duration_ms / 1000,
        )

    @classmethod
    def register_with_scheduler(cls, scheduler) -> None:
        """Register job with K0 scheduler."""
        job = cls()
        scheduler.register_periodic_job(
            name=cls.JOB_NAME,
            interval_seconds=cls.DEFAULT_INTERVAL_SECONDS,
            handler=job.run,
        )
```

```python
# k0/pipelines/p03/maintenance/__init__.py
from k0.pipelines.p03.maintenance.quarantine_cleanup import (
    AutoReleaseResult,
    QuarantineAutoReleaseJob,
)

__all__ = [
    "AutoReleaseResult",
    "QuarantineAutoReleaseJob",
]
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_quarantine_auto_released_total | counter | - | Signals auto-released |
| p03_quarantine_auto_release_failures_total | counter | - | Auto-release failures |
| p03_quarantine_auto_release_duration_seconds | histogram | - | Job execution time |

**Acceptance Criteria**:

- [ ] `QuarantineAutoReleaseJob` class created with batch processing
- [ ] Correctly identifies signals past `auto_release_at`
- [ ] Updates `st_feedback_quarantine.decision` to 'RELEASE'
- [ ] Updates `st_feedback_quarantine.reviewed_by` to 'AUTO'
- [ ] Updates `st_feedback_signals.quarantine_status` to 'RELEASED'
- [ ] Handles missing source signals gracefully
- [ ] Batch processing prevents long-running transactions
- [ ] Job can be registered with K0 scheduler
- [ ] All operations emit appropriate metrics
- [ ] ≥95% test coverage for auto-release job

---

#### Issue 6.2.15 — Quarantine Manual Review API Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement API for security operators to manually review quarantined signals, making RELEASE or DISCARD decisions.

**Dossier Reference**: [Section 6.21.3 Manual Review](../pipelines/P03_consolidation_dossier_v2.md#6213-quarantine-process)

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| st_feedback_quarantine | Migration 0050 | reviewed_at, reviewed_by, decision columns |
| QuarantineDetector | `k0/pipelines/p03/feedback/quarantine_detector.py` | Quarantine data structures |
| MetricsExporter | `k0/obs/metrics.py` | Review metrics |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/api/quarantine_review.py` with review functions
2. [ ] Implement `review_quarantined_signal()` per dossier pattern
3. [ ] Implement `list_pending_reviews()` for review queue
4. [ ] Implement `get_quarantine_details()` for single signal inspection
5. [ ] Add decision validation (only 'RELEASE' or 'DISCARD' allowed)
6. [ ] Update `st_feedback_signals.quarantine_status` based on decision
7. [ ] Add audit logging for review decisions
8. [ ] Add metrics for review decisions by type
9. [ ] Create tests: `tests/k0/pipelines/p03/api/test_quarantine_review.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/api/quarantine_review.py
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class ReviewDecision(Enum):
    """Valid review decisions."""
    RELEASE = "RELEASE"
    DISCARD = "DISCARD"


@dataclass
class QuarantineRecord:
    """Quarantine record for review."""
    quarantine_id: str
    signal_id: str
    space_id: str
    reason: str
    severity: str
    detected_at: int
    auto_release_at: int
    reviewed_at: Optional[int] = None
    reviewed_by: Optional[str] = None
    decision: Optional[str] = None


@dataclass
class PendingReviewsResult:
    """Result of pending reviews query."""
    records: list[QuarantineRecord]
    total_count: int
    page: int
    page_size: int


class QuarantineReviewAPI:
    """
    API for manual review of quarantined signals.

    Allows security operators to:
    - List pending reviews (with pagination)
    - Get details of specific quarantined signal
    - Make RELEASE or DISCARD decisions

    Dossier Reference: Section 6.21.3
    """

    def __init__(
        self,
        *,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._metrics = metrics

    async def list_pending_reviews(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        severity_filter: Optional[str] = None,
        reason_filter: Optional[str] = None,
        connection: asyncpg.Connection,
    ) -> PendingReviewsResult:
        """
        List quarantined signals pending review.

        Args:
            page: Page number (1-indexed)
            page_size: Number of records per page
            severity_filter: Filter by severity (LOW, MEDIUM, HIGH)
            reason_filter: Filter by reason (RATE_LIMIT, VELOCITY_SPIKE, ANOMALY, ENTROPY)
            connection: Database connection

        Returns:
            PendingReviewsResult with records and pagination info.
        """
        offset = (page - 1) * page_size

        # Build WHERE clause
        where_conditions = ["decision IS NULL"]
        params: list = []
        param_idx = 1

        if severity_filter:
            where_conditions.append(f"severity = ${param_idx}")
            params.append(severity_filter)
            param_idx += 1

        if reason_filter:
            where_conditions.append(f"reason = ${param_idx}")
            params.append(reason_filter)
            param_idx += 1

        where_clause = " AND ".join(where_conditions)

        # Get total count
        count_row = await connection.fetchrow(
            f"""
            SELECT COUNT(*) as total
            FROM st_feedback_quarantine
            WHERE {where_clause}
            """,
            *params,
        )
        total_count = count_row["total"]

        # Get records
        rows = await connection.fetch(
            f"""
            SELECT
                quarantine_id, signal_id, space_id,
                reason, severity, detected_at, auto_release_at
            FROM st_feedback_quarantine
            WHERE {where_clause}
            ORDER BY
                CASE severity
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                END,
                detected_at ASC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """,
            *params,
            page_size,
            offset,
        )

        records = [
            QuarantineRecord(
                quarantine_id=row["quarantine_id"],
                signal_id=row["signal_id"],
                space_id=row["space_id"],
                reason=row["reason"],
                severity=row["severity"],
                detected_at=row["detected_at"],
                auto_release_at=row["auto_release_at"],
            )
            for row in rows
        ]

        # Emit gauge for pending reviews
        self._emit_pending_gauge(total_count)

        return PendingReviewsResult(
            records=records,
            total_count=total_count,
            page=page,
            page_size=page_size,
        )

    async def get_quarantine_details(
        self,
        quarantine_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> Optional[QuarantineRecord]:
        """Get details of a specific quarantined signal."""
        row = await connection.fetchrow(
            """
            SELECT
                quarantine_id, signal_id, space_id,
                reason, severity, detected_at, auto_release_at,
                reviewed_at, reviewed_by, decision
            FROM st_feedback_quarantine
            WHERE quarantine_id = $1
            """,
            quarantine_id,
        )

        if not row:
            return None

        return QuarantineRecord(
            quarantine_id=row["quarantine_id"],
            signal_id=row["signal_id"],
            space_id=row["space_id"],
            reason=row["reason"],
            severity=row["severity"],
            detected_at=row["detected_at"],
            auto_release_at=row["auto_release_at"],
            reviewed_at=row["reviewed_at"],
            reviewed_by=row["reviewed_by"],
            decision=row["decision"],
        )

    async def review_quarantined_signal(
        self,
        quarantine_id: str,
        reviewer_id: str,
        decision: ReviewDecision,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """
        Make review decision on quarantined signal.

        Args:
            quarantine_id: ID of quarantine record
            reviewer_id: ID of reviewer making decision
            decision: RELEASE or DISCARD

        Returns:
            True if review was applied, False if already reviewed.
        """
        reviewed_at = int(time.time())

        # Update quarantine record (only if not already reviewed)
        result = await connection.execute(
            """
            UPDATE st_feedback_quarantine
            SET reviewed_at = $1,
                reviewed_by = $2,
                decision = $3
            WHERE quarantine_id = $4
              AND decision IS NULL
            """,
            reviewed_at,
            reviewer_id,
            decision.value,
            quarantine_id,
        )

        if result == "UPDATE 0":
            return False  # Already reviewed

        # Get signal_id for updating source
        row = await connection.fetchrow(
            """
            SELECT signal_id
            FROM st_feedback_quarantine
            WHERE quarantine_id = $1
            """,
            quarantine_id,
        )

        if row:
            # Update source signal status
            new_status = "RELEASED" if decision == ReviewDecision.RELEASE else "DISCARDED"
            await connection.execute(
                """
                UPDATE st_feedback_signals
                SET quarantine_status = $1
                WHERE signal_id = $2
                """,
                new_status,
                row["signal_id"],
            )

        # Emit metrics
        self._emit_review_metric(decision)

        return True

    def _emit_pending_gauge(self, count: int) -> None:
        if self._metrics:
            self._metrics.gauge(
                "p03_quarantine_pending_reviews",
                count,
            )

    def _emit_review_metric(self, decision: ReviewDecision) -> None:
        if self._metrics:
            self._metrics.counter(
                "p03_quarantine_review_decisions_total",
                1,
                decision=decision.value,
            )
```

```python
# k0/pipelines/p03/api/__init__.py
from k0.pipelines.p03.api.quarantine_review import (
    PendingReviewsResult,
    QuarantineRecord,
    QuarantineReviewAPI,
    ReviewDecision,
)

__all__ = [
    "PendingReviewsResult",
    "QuarantineRecord",
    "QuarantineReviewAPI",
    "ReviewDecision",
]
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_quarantine_pending_reviews | gauge | - | Pending review count |
| p03_quarantine_review_decisions_total | counter | decision | Review decisions by type |

**Acceptance Criteria**:

- [ ] `QuarantineReviewAPI` class created with all review methods
- [ ] `list_pending_reviews()` returns paginated results sorted by severity
- [ ] `get_quarantine_details()` returns full record with review status
- [ ] `review_quarantined_signal()` only allows RELEASE or DISCARD decisions
- [ ] Review updates `st_feedback_quarantine.reviewed_by` with reviewer ID
- [ ] Review updates `st_feedback_signals.quarantine_status` appropriately
- [ ] Already-reviewed signals return False (not re-reviewed)
- [ ] Filtering by severity and reason works correctly
- [ ] All review operations emit appropriate metrics
- [ ] ≥95% test coverage for review API

---

#### Issue 6.2.16 — k0ctl DLQ Commands for P03

**Status**: 🔲 NOT STARTED

**Goal**: Implement CLI commands for managing P03 DLQ entries via k0ctl, enabling operators to list, inspect, requeue, and purge failed events.

**Dossier Reference**: [Section 13.8 K0 CLI Integration (k0ctl dlq)](../pipelines/P03_consolidation_dossier_v2.md#138-k0-cli-integration-k0ctl-dlq)

**Commands to Implement** (from dossier 13.8):

```bash
# List pending DLQ items for P03
k0ctl dlq list --pipeline p03_consolidation --status PENDING

# Inspect specific failed event
k0ctl dlq get <dlq_id> --verbose

# Requeue after fix (retries with exponential backoff)
k0ctl dlq requeue <dlq_id>

# Bulk requeue all pending items
k0ctl dlq requeue-all --pipeline p03_consolidation --max-items 100

# Purge old items
k0ctl dlq purge --pipeline p03_consolidation --older-than 7d

# Show DLQ statistics
k0ctl dlq stats --pipeline p03_consolidation
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 CLI base | `k0/cli/k0ctl.py` | CLI framework, command registration |
| DLQStore | `k0/storage/dlq.py` | `list_pending()`, `get()`, `mark_requeued()`, `purge()` |
| DeadLetter | `k0/storage/dlq.py` | DLQ record dataclass |
| Click | External dependency | CLI argument parsing |

**Work To Do**:

1. [ ] Create `k0/cli/commands/dlq.py` with DLQ command group
2. [ ] Implement `dlq list` command with filters (--pipeline, --status, --phase, --error-code)
3. [ ] Implement `dlq get <dlq_id>` command with --verbose flag for full payload
4. [ ] Implement `dlq requeue <dlq_id>` command for single item requeue
5. [ ] Implement `dlq requeue-all` command with --max-items and --filter options
6. [ ] Implement `dlq purge` command with --older-than and --status filters
7. [ ] Implement `dlq stats` command showing counts by status, phase, error type
8. [ ] Add JSON output format option (--format json) for scripting
9. [ ] Add confirmation prompts for destructive operations (purge, requeue-all)
10. [ ] Create tests: `tests/k0/cli/commands/test_dlq_commands.py`

**Implementation Pattern**:

```python
# k0/cli/commands/dlq.py
from __future__ import annotations

import click
import json
from datetime import datetime, timedelta
from typing import Optional

from k0.storage.dlq import DLQStore, DeadLetter


@click.group(name="dlq")
def dlq_group():
    """Dead Letter Queue management commands."""
    pass


@dlq_group.command(name="list")
@click.option("--pipeline", "-p", help="Filter by pipeline name")
@click.option("--status", "-s", type=click.Choice(["PENDING", "REQUEUED", "QUARANTINED", "DISCARDED"]))
@click.option("--phase", help="Filter by failed phase (e.g., R3, R7)")
@click.option("--error-code", help="Filter by error code")
@click.option("--limit", "-l", default=50, help="Maximum items to return")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def list_dlq(
    pipeline: Optional[str],
    status: Optional[str],
    phase: Optional[str],
    error_code: Optional[str],
    limit: int,
    output_format: str,
):
    """List DLQ entries with optional filters."""
    import asyncio

    async def _list():
        store = DLQStore()
        entries = await store.list_pending(
            pipeline=pipeline,
            status=status,
            phase=phase,
            error_code=error_code,
            limit=limit,
        )

        if output_format == "json":
            click.echo(json.dumps([e.to_dict() for e in entries], indent=2))
        else:
            _print_table(entries)

    asyncio.run(_list())


def _print_table(entries: list[DeadLetter]):
    """Print DLQ entries as table."""
    if not entries:
        click.echo("No DLQ entries found.")
        return

    click.echo(f"{'DLQ ID':<28} {'Pipeline':<20} {'Phase':<6} {'Status':<12} {'Error':<30}")
    click.echo("-" * 100)
    for e in entries:
        click.echo(
            f"{e.dlq_id:<28} {e.pipeline:<20} {e.phase or '-':<6} "
            f"{e.status:<12} {e.error_type[:30]:<30}"
        )
    click.echo(f"\nTotal: {len(entries)} entries")


@dlq_group.command(name="get")
@click.argument("dlq_id")
@click.option("--verbose", "-v", is_flag=True, help="Include full payload")
def get_dlq(dlq_id: str, verbose: bool):
    """Get details of a specific DLQ entry."""
    import asyncio

    async def _get():
        store = DLQStore()
        entry = await store.get(dlq_id)

        if not entry:
            click.echo(f"DLQ entry not found: {dlq_id}", err=True)
            raise SystemExit(1)

        click.echo(f"DLQ ID:      {entry.dlq_id}")
        click.echo(f"Pipeline:    {entry.pipeline}")
        click.echo(f"Phase:       {entry.phase or 'N/A'}")
        click.echo(f"Status:      {entry.status}")
        click.echo(f"Error Type:  {entry.error_type}")
        click.echo(f"Error Msg:   {entry.error_message}")
        click.echo(f"Created:     {datetime.fromtimestamp(entry.created_at / 1000)}")
        click.echo(f"Retries:     {entry.retry_count}")

        if verbose:
            click.echo("\nPayload:")
            click.echo(json.dumps(entry.payload, indent=2))

    asyncio.run(_get())


@dlq_group.command(name="requeue")
@click.argument("dlq_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def requeue_dlq(dlq_id: str, force: bool):
    """Requeue a DLQ entry for retry processing."""
    import asyncio

    if not force:
        click.confirm(f"Requeue DLQ entry {dlq_id}?", abort=True)

    async def _requeue():
        store = DLQStore()
        success = await store.mark_requeued(dlq_id)

        if success:
            click.echo(f"Successfully requeued: {dlq_id}")
        else:
            click.echo(f"Failed to requeue: {dlq_id}", err=True)
            raise SystemExit(1)

    asyncio.run(_requeue())


@dlq_group.command(name="requeue-all")
@click.option("--pipeline", "-p", required=True, help="Pipeline name")
@click.option("--max-items", default=100, help="Maximum items to requeue")
@click.option("--phase", help="Filter by phase")
@click.option("--error-type", help="Filter by error type (TRANSIENT only recommended)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def requeue_all(
    pipeline: str,
    max_items: int,
    phase: Optional[str],
    error_type: Optional[str],
    force: bool,
):
    """Bulk requeue pending DLQ entries."""
    import asyncio

    async def _requeue_all():
        store = DLQStore()
        entries = await store.list_pending(
            pipeline=pipeline,
            status="PENDING",
            phase=phase,
            error_type=error_type,
            limit=max_items,
        )

        if not entries:
            click.echo("No matching DLQ entries found.")
            return

        if not force:
            click.confirm(f"Requeue {len(entries)} entries?", abort=True)

        requeued = 0
        for entry in entries:
            if await store.mark_requeued(entry.dlq_id):
                requeued += 1

        click.echo(f"Requeued {requeued}/{len(entries)} entries")

    asyncio.run(_requeue_all())


@dlq_group.command(name="purge")
@click.option("--pipeline", "-p", required=True, help="Pipeline name")
@click.option("--older-than", required=True, help="Age threshold (e.g., 7d, 24h)")
@click.option("--status", default="DISCARDED", help="Status to purge")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def purge_dlq(pipeline: str, older_than: str, status: str, force: bool):
    """Purge old DLQ entries."""
    import asyncio

    # Parse duration
    threshold = _parse_duration(older_than)
    cutoff = datetime.now() - threshold

    if not force:
        click.confirm(
            f"Purge {status} entries older than {cutoff.isoformat()} for {pipeline}?",
            abort=True,
        )

    async def _purge():
        store = DLQStore()
        count = await store.purge(
            pipeline=pipeline,
            status=status,
            older_than_ms=int(cutoff.timestamp() * 1000),
        )
        click.echo(f"Purged {count} entries")

    asyncio.run(_purge())


@dlq_group.command(name="stats")
@click.option("--pipeline", "-p", help="Filter by pipeline")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def stats_dlq(pipeline: Optional[str], output_format: str):
    """Show DLQ statistics."""
    import asyncio

    async def _stats():
        store = DLQStore()
        stats = await store.get_stats(pipeline=pipeline)

        if output_format == "json":
            click.echo(json.dumps(stats, indent=2))
        else:
            click.echo(f"\nDLQ Statistics{' for ' + pipeline if pipeline else ''}")
            click.echo("-" * 40)
            click.echo(f"Total entries:   {stats.get('total', 0)}")
            click.echo(f"Pending:         {stats.get('pending', 0)}")
            click.echo(f"Requeued:        {stats.get('requeued', 0)}")
            click.echo(f"Quarantined:     {stats.get('quarantined', 0)}")
            click.echo(f"Discarded:       {stats.get('discarded', 0)}")
            click.echo("\nBy Phase:")
            for phase, count in stats.get("by_phase", {}).items():
                click.echo(f"  {phase}: {count}")
            click.echo("\nBy Error Type:")
            for err_type, count in stats.get("by_error_type", {}).items():
                click.echo(f"  {err_type}: {count}")

    asyncio.run(_stats())


def _parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like '7d', '24h', '30m'."""
    import re

    match = re.match(r"^(\d+)([dhm])$", duration_str.lower())
    if not match:
        raise click.BadParameter(f"Invalid duration format: {duration_str}")

    value, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return timedelta(days=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "m":
        return timedelta(minutes=value)
    else:
        raise click.BadParameter(f"Unknown unit: {unit}")
```

```python
# k0/cli/k0ctl.py - Add registration
from k0.cli.commands.dlq import dlq_group

@click.group()
def k0ctl():
    """K0 Kernel Control CLI."""
    pass

# Register command groups
k0ctl.add_command(dlq_group)
```

**Acceptance Criteria**:

- [ ] `k0ctl dlq list` shows pending entries with filters
- [ ] `k0ctl dlq get` displays full entry details
- [ ] `k0ctl dlq requeue` successfully requeues single entry
- [ ] `k0ctl dlq requeue-all` bulk requeues with safety limits
- [ ] `k0ctl dlq purge` removes old entries with confirmation
- [ ] `k0ctl dlq stats` shows comprehensive statistics
- [ ] JSON output format available for scripting
- [ ] Destructive operations require confirmation (or --force)
- [ ] Duration parsing handles days, hours, minutes
- [ ] ≥95% test coverage for CLI commands

---

#### Issue 6.2.17 — P03LearningAnomalyDetector Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement learning-specific anomaly detection to identify parameter drift, contradictory signals, and formula regression that could degrade P03 quality.

**Dossier Reference**: [Section 14.9 P03 Learning Anomaly Detection](../pipelines/P03_consolidation_dossier_v2.md#149-p03-learning-anomaly-detection)

**P03-Specific Checks** (from dossier 14.9):

| Check | Threshold | Action |
|-------|-----------|--------|
| Parameter drift | > 20% change in 24h | Pause learning, alert |
| Contradictory signals | Same entity, opposite signals | Flag for review |
| Formula regression | Quality metric drops > 10% | Auto-rollback |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03LearningAnomalyDetector (feedback) | `k0/pipelines/p03/feedback/anomaly_detector.py` | Content-level anomaly detection (Issue 6.2.13) |
| st_learned_weights | Migration 0040 | Parameter storage with version history |
| FeedbackSignal | `k0/pipelines/p03/learning/signals.py` | Signal structure |
| MetricsExporter | `k0/obs/metrics.py` | Anomaly metrics emission |
| ParameterRollback | Dossier 13.11 | Rollback mechanism |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/learning/anomaly_detector.py` with `P03LearningAnomalyDetector` class
2. [ ] Implement `check_parameter_drift()` for 20% change detection
3. [ ] Implement `check_contradictory_signals()` for opposing signal detection
4. [ ] Implement `check_formula_regression()` for quality drop detection
5. [ ] Implement `pause_learning()` to halt learning for specific parameters
6. [ ] Implement `resume_learning()` with review confirmation
7. [ ] Add integration with `ParameterRollback` for auto-rollback on regression
8. [ ] Add metrics for all anomaly types detected
9. [ ] Add alerts for HIGH severity anomalies
10. [ ] Create tests: `tests/k0/pipelines/p03/learning/test_learning_anomaly_detector.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/learning/anomaly_detector.py
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class LearningAnomalyType(Enum):
    """Types of learning anomalies."""
    PARAMETER_DRIFT = "PARAMETER_DRIFT"
    CONTRADICTORY_SIGNALS = "CONTRADICTORY_SIGNALS"
    FORMULA_REGRESSION = "FORMULA_REGRESSION"
    QUALITY_DEGRADATION = "QUALITY_DEGRADATION"


@dataclass
class LearningAnomalyResult:
    """Result of learning anomaly detection."""
    is_anomalous: bool
    anomaly_type: Optional[LearningAnomalyType] = None
    param_key: Optional[str] = None
    entity_id: Optional[str] = None
    details: dict = field(default_factory=dict)
    action_taken: Optional[str] = None


@dataclass
class FeedbackSignal:
    """Feedback signal for anomaly analysis."""
    signal_id: str
    entity_id: str
    feedback_type: str
    salience_delta: Optional[float] = None
    created_at: int = 0


class P03LearningAnomalyDetector:
    """
    Detect anomalies in P03 learning parameters.

    Checks for:
    - Parameter drift (> 20% change in 24h)
    - Contradictory signals (opposing signals for same entity)
    - Formula regression (quality drop > 10%)

    Dossier Reference: Section 14.9
    """

    def __init__(
        self,
        *,
        drift_threshold: float = 0.20,  # 20% change
        quality_drop_threshold: float = 0.10,  # 10% quality drop
        min_signals_for_contradiction: int = 2,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._drift_threshold = drift_threshold
        self._quality_drop_threshold = quality_drop_threshold
        self._min_signals = min_signals_for_contradiction
        self._metrics = metrics
        self._paused_params: set[str] = set()

    async def check_parameter_drift(
        self,
        param_key: str,
        space_id: str,
        current_value: float,
        *,
        connection: asyncpg.Connection,
    ) -> LearningAnomalyResult:
        """
        Check if parameter changed too quickly (> 20% in 24h).

        Args:
            param_key: Parameter identifier
            space_id: Space context
            current_value: New proposed value
            connection: Database connection

        Returns:
            LearningAnomalyResult with drift detection status.
        """
        now = int(time.time())
        yesterday = now - 86400  # 24 hours ago

        # Get value from 24h ago
        row = await connection.fetchrow(
            """
            SELECT current_value
            FROM st_learned_weights
            WHERE param_key = $1
              AND space_id = $2
              AND updated_at <= $3
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            param_key,
            space_id,
            yesterday * 1000,  # ms
        )

        if not row or row["current_value"] == 0:
            return LearningAnomalyResult(is_anomalous=False)

        previous_value = row["current_value"]
        drift_pct = abs(current_value - previous_value) / abs(previous_value)

        if drift_pct > self._drift_threshold:
            # Pause learning for this parameter
            await self._pause_learning(param_key, space_id, connection=connection)

            # Emit alert
            await self._emit_alert(
                LearningAnomalyType.PARAMETER_DRIFT,
                param_key=param_key,
                drift_pct=drift_pct,
            )

            self._emit_metric(
                "p03_learning_anomaly_detected_total",
                1.0,
                type=LearningAnomalyType.PARAMETER_DRIFT.value,
            )

            return LearningAnomalyResult(
                is_anomalous=True,
                anomaly_type=LearningAnomalyType.PARAMETER_DRIFT,
                param_key=param_key,
                details={
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "drift_pct": drift_pct,
                    "threshold": self._drift_threshold,
                },
                action_taken="LEARNING_PAUSED",
            )

        return LearningAnomalyResult(is_anomalous=False)

    async def check_contradictory_signals(
        self,
        entity_id: str,
        signals: list[FeedbackSignal],
    ) -> LearningAnomalyResult:
        """
        Detect opposing signals for same entity.

        Args:
            entity_id: Entity being updated
            signals: Recent signals for this entity

        Returns:
            LearningAnomalyResult with contradiction status.
        """
        if len(signals) < self._min_signals:
            return LearningAnomalyResult(is_anomalous=False)

        # Group by feedback type
        by_type: dict[str, list[FeedbackSignal]] = defaultdict(list)
        for sig in signals:
            by_type[sig.feedback_type].append(sig)

        # Check for contradictions within each type
        for sig_type, type_signals in by_type.items():
            deltas = [
                s.salience_delta
                for s in type_signals
                if s.salience_delta is not None
            ]

            if len(deltas) >= 2:
                # Check if signals have opposite signs
                has_positive = any(d > 0 for d in deltas)
                has_negative = any(d < 0 for d in deltas)

                if has_positive and has_negative:
                    self._emit_metric(
                        "p03_learning_anomaly_detected_total",
                        1.0,
                        type=LearningAnomalyType.CONTRADICTORY_SIGNALS.value,
                    )

                    return LearningAnomalyResult(
                        is_anomalous=True,
                        anomaly_type=LearningAnomalyType.CONTRADICTORY_SIGNALS,
                        entity_id=entity_id,
                        details={
                            "feedback_type": sig_type,
                            "signal_count": len(type_signals),
                            "positive_deltas": [d for d in deltas if d > 0],
                            "negative_deltas": [d for d in deltas if d < 0],
                        },
                        action_taken="FLAGGED_FOR_REVIEW",
                    )

        return LearningAnomalyResult(is_anomalous=False)

    async def check_formula_regression(
        self,
        formula_name: str,
        space_id: str,
        current_quality: float,
        *,
        connection: asyncpg.Connection,
    ) -> LearningAnomalyResult:
        """
        Check if formula quality has regressed significantly.

        Args:
            formula_name: Formula being monitored
            space_id: Space context
            current_quality: Current quality metric (0-1)
            connection: Database connection

        Returns:
            LearningAnomalyResult with regression status.
        """
        # Get previous quality (7-day rolling average)
        row = await connection.fetchrow(
            """
            SELECT AVG(quality_metric) as avg_quality
            FROM st_formula_quality_history
            WHERE formula_name = $1
              AND space_id = $2
              AND recorded_at > $3
            """,
            formula_name,
            space_id,
            (int(time.time()) - 7 * 86400) * 1000,
        )

        if not row or row["avg_quality"] is None:
            return LearningAnomalyResult(is_anomalous=False)

        previous_quality = row["avg_quality"]
        quality_drop = (previous_quality - current_quality) / previous_quality

        if quality_drop > self._quality_drop_threshold:
            # Trigger auto-rollback
            from k0.pipelines.p03.learning.parameter_rollback import ParameterRollback

            rollback = ParameterRollback()
            await rollback.rollback_formula_parameters(
                formula_name,
                space_id,
                reason=f"Quality regression: {quality_drop:.1%}",
                connection=connection,
            )

            self._emit_metric(
                "p03_learning_anomaly_detected_total",
                1.0,
                type=LearningAnomalyType.FORMULA_REGRESSION.value,
            )

            self._emit_metric(
                "p03_formula_auto_rollbacks_total",
                1.0,
                formula=formula_name,
            )

            return LearningAnomalyResult(
                is_anomalous=True,
                anomaly_type=LearningAnomalyType.FORMULA_REGRESSION,
                details={
                    "formula_name": formula_name,
                    "previous_quality": previous_quality,
                    "current_quality": current_quality,
                    "quality_drop": quality_drop,
                },
                action_taken="AUTO_ROLLBACK",
            )

        return LearningAnomalyResult(is_anomalous=False)

    async def _pause_learning(
        self,
        param_key: str,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> None:
        """Pause learning for a parameter."""
        self._paused_params.add(f"{space_id}:{param_key}")

        await connection.execute(
            """
            UPDATE st_learned_weights
            SET learning_paused = TRUE,
                paused_at = $1,
                paused_reason = 'ANOMALY_DETECTED'
            WHERE param_key = $2 AND space_id = $3
            """,
            int(time.time() * 1000),
            param_key,
            space_id,
        )

        self._emit_metric(
            "p03_learning_paused_total",
            1.0,
            param_key=param_key[:20],
        )

    async def resume_learning(
        self,
        param_key: str,
        space_id: str,
        reviewer_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> bool:
        """Resume learning after review."""
        key = f"{space_id}:{param_key}"
        if key in self._paused_params:
            self._paused_params.remove(key)

        result = await connection.execute(
            """
            UPDATE st_learned_weights
            SET learning_paused = FALSE,
                paused_at = NULL,
                paused_reason = NULL,
                resumed_by = $1,
                resumed_at = $2
            WHERE param_key = $3 AND space_id = $4
            """,
            reviewer_id,
            int(time.time() * 1000),
            param_key,
            space_id,
        )

        if result != "UPDATE 0":
            self._emit_metric(
                "p03_learning_resumed_total",
                1.0,
                param_key=param_key[:20],
            )
            return True
        return False

    def is_learning_paused(self, param_key: str, space_id: str) -> bool:
        """Check if learning is paused for a parameter."""
        return f"{space_id}:{param_key}" in self._paused_params

    async def _emit_alert(
        self,
        anomaly_type: LearningAnomalyType,
        **context,
    ) -> None:
        """Emit security alert for anomaly."""
        # Integration with alerting system
        pass

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_learning_anomaly_detected_total | counter | type | Anomalies by type |
| p03_learning_paused_total | counter | param_key | Learning pause events |
| p03_learning_resumed_total | counter | param_key | Learning resume events |
| p03_formula_auto_rollbacks_total | counter | formula | Auto-rollback events |

**Acceptance Criteria**:

- [ ] `P03LearningAnomalyDetector` class created with all detection methods
- [ ] Parameter drift detection triggers at > 20% change in 24h
- [ ] Contradictory signal detection identifies opposing deltas
- [ ] Formula regression triggers auto-rollback at > 10% quality drop
- [ ] Learning pause/resume mechanism functional
- [ ] All anomaly types emit metrics
- [ ] Integration with `ParameterRollback` for auto-rollback
- [ ] ≥95% test coverage for learning anomaly detector

---

#### Issue 6.2.18 — Edge Case Handling Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement handlers for P03-specific edge cases as defined in the dossier edge case matrix, ensuring graceful degradation and appropriate metrics.

**Dossier Reference**: [Section 13.9 Edge Case Handling Matrix](../pipelines/P03_consolidation_dossier_v2.md#139-edge-case-handling-matrix)

**Edge Case Matrix** (from dossier 13.9):

| Edge Case | Detection | Handling Strategy | Recovery Action | Metric |
|-----------|-----------|-------------------|-----------------|--------|
| Empty st_hipp_events (>24h) | Scheduled health check | Emit `p03.health.idle.v1` event | No action (normal during low activity) | `p03_idle_cycles_total` |
| Corrupted embeddings in st_vec | Dimension mismatch or NaN detection | Skip event, flag for P08 re-embedding | `UPDATE st_vec SET status='RECOMPUTE_REQUIRED'` | `p03_corrupted_embeddings_total` |
| Partial R7 write failure | Transaction rollback exception | Use COMMIT_PARTIAL strategy | Manual DLQ requeue after fix | `p03_partial_write_failures_total` |
| st_hipp_events backlog > 10K | Batch selector overflow | Trigger adaptive batching | Page via k0ctl ops alert | `p03_backlog_overflow_total` |
| P08 circuit open > 5min | Circuit breaker OPEN state duration | Queue embedding requests locally | Automatic on circuit HALF_OPEN | `p03_p08_circuit_open_seconds` |
| FAISS index unavailable | Index load failure or timeout | Fall back to brute-force similarity | Trigger FAISS index rebuild job | `p03_faiss_fallback_total` |
| Duplicate cycle trigger | Same batch_hash detected | Idempotent skip; log and continue | None (by design) | `p03_duplicate_triggers_total` |
| Memory pressure during R5 | Heap > 80% threshold | Skip R5 creative algorithms | Automatic via `can_skip_dream_phase()` | `p03_r5_memory_skipped_total` |
| KG entity explosion (>1M nodes) | Node count threshold exceeded | Partition KG by space_id | Enable KG sharding feature flag | `p03_kg_partition_events_total` |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03CircuitBreaker | `k0/pipelines/p03/ops/circuit_breaker.py` | Circuit state monitoring |
| FAISSCircuitBreaker | `k0/pipelines/p03/ops/faiss_circuit.py` | FAISS fallback |
| P08EmbeddingCircuitBreaker | `k0/pipelines/p03/ops/p08_circuit.py` | P08 coordination |
| PartialFailureHandler | `k0/pipelines/p03/ops/partial_failure.py` | COMMIT_PARTIAL strategy |
| P03AdaptiveBatchSizer | `k0/pipelines/p03/qos/batch_sizer.py` | Adaptive batch sizing |
| MetricsExporter | `k0/obs/metrics.py` | Edge case metrics |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/ops/edge_case_handler.py` with `P03EdgeCaseHandler` class
2. [ ] Implement `check_idle_cycle()` for empty st_hipp_events detection
3. [ ] Implement `check_corrupted_embedding()` for NaN/dimension mismatch detection
4. [ ] Implement `check_backlog_overflow()` for > 10K pending events
5. [ ] Implement `check_p08_circuit_duration()` for circuit open > 5min
6. [ ] Implement `check_duplicate_trigger()` for batch_hash idempotency
7. [ ] Implement `check_memory_pressure()` for heap > 80% threshold
8. [ ] Implement `check_kg_explosion()` for > 1M node detection
9. [ ] Implement scheduled health check job for proactive detection
10. [ ] Add all edge case metrics from matrix
11. [ ] Create tests: `tests/k0/pipelines/p03/ops/test_edge_case_handler.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/edge_case_handler.py
from __future__ import annotations

import gc
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class EdgeCaseType(Enum):
    """Types of edge cases detected."""
    IDLE_CYCLE = "IDLE_CYCLE"
    CORRUPTED_EMBEDDING = "CORRUPTED_EMBEDDING"
    PARTIAL_WRITE_FAILURE = "PARTIAL_WRITE_FAILURE"
    BACKLOG_OVERFLOW = "BACKLOG_OVERFLOW"
    P08_CIRCUIT_OPEN = "P08_CIRCUIT_OPEN"
    FAISS_UNAVAILABLE = "FAISS_UNAVAILABLE"
    DUPLICATE_TRIGGER = "DUPLICATE_TRIGGER"
    MEMORY_PRESSURE = "MEMORY_PRESSURE"
    KG_EXPLOSION = "KG_EXPLOSION"


@dataclass
class EdgeCaseResult:
    """Result of edge case detection."""
    detected: bool
    edge_case_type: Optional[EdgeCaseType] = None
    action_taken: Optional[str] = None
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class P03EdgeCaseHandler:
    """
    Handle P03-specific edge cases with graceful degradation.

    Provides detection, handling, and recovery for edge cases
    defined in dossier Section 13.9.
    """

    # Thresholds from dossier
    IDLE_THRESHOLD_HOURS = 24
    BACKLOG_WARNING_THRESHOLD = 10_000
    BACKLOG_CRITICAL_THRESHOLD = 50_000
    MEMORY_PRESSURE_THRESHOLD = 0.80  # 80%
    KG_NODE_THRESHOLD = 1_000_000  # 1M nodes
    P08_CIRCUIT_OPEN_THRESHOLD_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        *,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._metrics = metrics
        self._seen_batch_hashes: set[str] = set()
        self._batch_hash_window: list[tuple[float, str]] = []

    async def check_idle_cycle(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> EdgeCaseResult:
        """
        Check if st_hipp_events has been empty for > 24h.

        Returns idle status but takes no action (normal behavior).
        """
        now = int(time.time())
        threshold = now - (self.IDLE_THRESHOLD_HOURS * 3600)

        row = await connection.fetchrow(
            """
            SELECT MAX(created_at) as last_event
            FROM st_hipp_events
            WHERE space_id = $1
            """,
            space_id,
        )

        if row["last_event"] is None or row["last_event"] / 1000 < threshold:
            self._emit_metric("p03_idle_cycles_total", 1.0, space_id=space_id[:8])

            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.IDLE_CYCLE,
                action_taken="EMIT_IDLE_EVENT",
                details={
                    "last_event_at": row["last_event"],
                    "threshold_hours": self.IDLE_THRESHOLD_HOURS,
                },
            )

        return EdgeCaseResult(detected=False)

    async def check_corrupted_embedding(
        self,
        entity_id: str,
        embedding: list[float],
        expected_dimension: int = 1536,
    ) -> EdgeCaseResult:
        """
        Check for corrupted embeddings (NaN or dimension mismatch).
        """
        import math

        # Check dimension
        if len(embedding) != expected_dimension:
            self._emit_metric(
                "p03_corrupted_embeddings_total",
                1.0,
                reason="dimension_mismatch",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.CORRUPTED_EMBEDDING,
                action_taken="FLAG_FOR_RECOMPUTE",
                details={
                    "entity_id": entity_id,
                    "actual_dimension": len(embedding),
                    "expected_dimension": expected_dimension,
                },
            )

        # Check for NaN values
        has_nan = any(math.isnan(v) for v in embedding)
        if has_nan:
            self._emit_metric(
                "p03_corrupted_embeddings_total",
                1.0,
                reason="nan_detected",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.CORRUPTED_EMBEDDING,
                action_taken="FLAG_FOR_RECOMPUTE",
                details={
                    "entity_id": entity_id,
                    "reason": "NaN values in embedding",
                },
            )

        return EdgeCaseResult(detected=False)

    async def check_backlog_overflow(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> EdgeCaseResult:
        """
        Check if st_hipp_events backlog exceeds threshold.
        """
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as pending_count
            FROM st_hipp_events
            WHERE space_id = $1
              AND processed_at IS NULL
            """,
            space_id,
        )

        pending = row["pending_count"]

        if pending >= self.BACKLOG_CRITICAL_THRESHOLD:
            self._emit_metric(
                "p03_backlog_overflow_total",
                1.0,
                severity="critical",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.BACKLOG_OVERFLOW,
                action_taken="ADAPTIVE_BATCHING_CRITICAL",
                details={
                    "pending_count": pending,
                    "threshold": self.BACKLOG_CRITICAL_THRESHOLD,
                    "severity": "critical",
                },
            )
        elif pending >= self.BACKLOG_WARNING_THRESHOLD:
            self._emit_metric(
                "p03_backlog_overflow_total",
                1.0,
                severity="warning",
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.BACKLOG_OVERFLOW,
                action_taken="ADAPTIVE_BATCHING_WARNING",
                details={
                    "pending_count": pending,
                    "threshold": self.BACKLOG_WARNING_THRESHOLD,
                    "severity": "warning",
                },
            )

        return EdgeCaseResult(detected=False)

    def check_duplicate_trigger(
        self,
        batch_hash: str,
        cycle_id: str,
    ) -> EdgeCaseResult:
        """
        Check for duplicate cycle trigger using batch_hash.

        Uses sliding window to prevent memory growth.
        """
        now = time.time()

        # Clean old hashes (older than 1 hour)
        self._batch_hash_window = [
            (ts, h) for ts, h in self._batch_hash_window
            if now - ts < 3600
        ]
        self._seen_batch_hashes = {h for _, h in self._batch_hash_window}

        if batch_hash in self._seen_batch_hashes:
            self._emit_metric("p03_duplicate_triggers_total", 1.0)
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.DUPLICATE_TRIGGER,
                action_taken="IDEMPOTENT_SKIP",
                details={
                    "batch_hash": batch_hash,
                    "cycle_id": cycle_id,
                },
            )

        # Add to window
        self._batch_hash_window.append((now, batch_hash))
        self._seen_batch_hashes.add(batch_hash)

        return EdgeCaseResult(detected=False)

    def check_memory_pressure(
        self,
        threshold: Optional[float] = None,
    ) -> EdgeCaseResult:
        """
        Check if memory usage exceeds threshold for R5 skip.
        """
        threshold = threshold or self.MEMORY_PRESSURE_THRESHOLD

        # Get current memory usage
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            total_memory = psutil.virtual_memory().total
            usage_pct = memory_info.rss / total_memory
        except ImportError:
            # Fallback to gc-based estimation
            gc.collect()
            # Rough estimation - not accurate without psutil
            usage_pct = 0.0

        if usage_pct >= threshold:
            self._emit_metric("p03_r5_memory_skipped_total", 1.0)
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.MEMORY_PRESSURE,
                action_taken="SKIP_R5_PHASE",
                details={
                    "memory_usage_pct": usage_pct,
                    "threshold": threshold,
                },
            )

        return EdgeCaseResult(detected=False)

    async def check_kg_explosion(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> EdgeCaseResult:
        """
        Check if KG node count exceeds threshold for partitioning.
        """
        row = await connection.fetchrow(
            """
            SELECT COUNT(*) as node_count
            FROM st_kg_dom
            WHERE space_id = $1
            """,
            space_id,
        )

        node_count = row["node_count"]

        if node_count >= self.KG_NODE_THRESHOLD:
            self._emit_metric(
                "p03_kg_partition_events_total",
                1.0,
                space_id=space_id[:8],
            )
            return EdgeCaseResult(
                detected=True,
                edge_case_type=EdgeCaseType.KG_EXPLOSION,
                action_taken="ENABLE_KG_SHARDING",
                details={
                    "node_count": node_count,
                    "threshold": self.KG_NODE_THRESHOLD,
                },
            )

        return EdgeCaseResult(detected=False)

    async def flag_embedding_for_recompute(
        self,
        entity_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> None:
        """Flag corrupted embedding for P08 re-embedding."""
        await connection.execute(
            """
            UPDATE st_vec
            SET status = 'RECOMPUTE_REQUIRED',
                updated_at = $1
            WHERE entity_id = $2
            """,
            int(time.time() * 1000),
            entity_id,
        )

    def can_skip_dream_phase(self) -> bool:
        """Check if R5 dream phase should be skipped due to memory."""
        result = self.check_memory_pressure()
        return result.detected

    def _emit_metric(self, name: str, value: float, **labels) -> None:
        if self._metrics:
            self._metrics.emit(name, value, **labels)
```

```python
# k0/pipelines/p03/ops/health_check.py
from __future__ import annotations

from typing import TYPE_CHECKING

from k0.pipelines.p03.ops.edge_case_handler import P03EdgeCaseHandler

if TYPE_CHECKING:
    import asyncpg


class P03HealthCheck:
    """Scheduled health check for P03 edge cases."""

    def __init__(self, handler: P03EdgeCaseHandler):
        self._handler = handler

    async def run_all_checks(
        self,
        space_id: str,
        *,
        connection: asyncpg.Connection,
    ) -> list[dict]:
        """Run all health checks and return results."""
        results = []

        # Check idle cycle
        idle_result = await self._handler.check_idle_cycle(
            space_id, connection=connection
        )
        if idle_result.detected:
            results.append({
                "check": "idle_cycle",
                "status": "warning",
                "details": idle_result.details,
            })

        # Check backlog
        backlog_result = await self._handler.check_backlog_overflow(
            space_id, connection=connection
        )
        if backlog_result.detected:
            results.append({
                "check": "backlog_overflow",
                "status": backlog_result.details.get("severity", "warning"),
                "details": backlog_result.details,
            })

        # Check memory pressure
        memory_result = self._handler.check_memory_pressure()
        if memory_result.detected:
            results.append({
                "check": "memory_pressure",
                "status": "warning",
                "details": memory_result.details,
            })

        # Check KG explosion
        kg_result = await self._handler.check_kg_explosion(
            space_id, connection=connection
        )
        if kg_result.detected:
            results.append({
                "check": "kg_explosion",
                "status": "critical",
                "details": kg_result.details,
            })

        return results
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_idle_cycles_total | counter | space_id | Idle cycle detections |
| p03_corrupted_embeddings_total | counter | reason | Corrupted embedding detections |
| p03_backlog_overflow_total | counter | severity | Backlog overflow events |
| p03_duplicate_triggers_total | counter | - | Duplicate trigger skips |
| p03_r5_memory_skipped_total | counter | - | R5 skips due to memory |
| p03_kg_partition_events_total | counter | space_id | KG partition triggers |

**Acceptance Criteria**:

- [ ] `P03EdgeCaseHandler` class created with all detection methods
- [ ] Idle cycle detection for > 24h empty events
- [ ] Corrupted embedding detection (NaN, dimension mismatch)
- [ ] Backlog overflow detection with warning/critical thresholds
- [ ] Duplicate trigger detection with idempotent skip
- [ ] Memory pressure detection for R5 skip
- [ ] KG explosion detection for partitioning trigger
- [ ] `P03HealthCheck` runs all checks in scheduled job
- [ ] All edge case metrics emitted correctly
- [ ] `flag_embedding_for_recompute()` updates st_vec status
- [ ] ≥95% test coverage for edge case handler

---

#### Issue 6.2.19 — Quarantine Metrics Implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement comprehensive metrics for the feedback quarantine system to enable monitoring, alerting, and operational visibility.

**Dossier Reference**: [Section 6.21.5 Metrics & Monitoring](../pipelines/P03_consolidation_dossier_v2.md#6215-metrics--monitoring)

**Metrics to Implement** (from dossier 6.21.5):

```python
# k0/pipelines/p03/ops/quarantine_metrics.py

# Quarantine signals metrics
p03_quarantine_signals_total = Counter(
    'p03_quarantine_signals_total',
    'Total signals quarantined',
    ['reason', 'severity']
)

p03_quarantine_decisions = Counter(
    'p03_quarantine_decisions',
    'Quarantine review decisions',
    ['decision']  # RELEASE, DISCARD, AUTO_RELEASE
)

p03_quarantine_auto_released = Counter(
    'p03_quarantine_auto_released',
    'Signals auto-released after quarantine period'
)

p03_quarantine_pending_reviews = Gauge(
    'p03_quarantine_pending_reviews',
    'Number of quarantined signals awaiting review',
    ['severity']
)

# Rate limiting metrics
p03_rate_limit_checks_total = Counter(
    'p03_rate_limit_checks_total',
    'Rate limit checks performed',
    ['exceeded']
)

p03_rate_limit_exceeded_total = Counter(
    'p03_rate_limit_exceeded_total',
    'Rate limit violations',
    ['user_id']
)

# Velocity metrics
p03_velocity_checks_total = Counter(
    'p03_velocity_checks_total',
    'Velocity checks performed',
    ['is_spike']
)

p03_velocity_spikes_total = Counter(
    'p03_velocity_spikes_total',
    'Velocity spikes detected',
    ['space_id']
)

p03_velocity_spike_multiplier = Gauge(
    'p03_velocity_spike_multiplier',
    'Current spike multiplier'
)

# Learning anomaly metrics
p03_learning_anomaly_detected_total = Counter(
    'p03_learning_anomaly_detected_total',
    'Learning anomalies detected',
    ['type']
)

p03_learning_paused_total = Counter(
    'p03_learning_paused_total',
    'Learning pause events',
    ['param_key']
)

p03_learning_resumed_total = Counter(
    'p03_learning_resumed_total',
    'Learning resume events',
    ['param_key']
)

p03_formula_auto_rollbacks_total = Counter(
    'p03_formula_auto_rollbacks_total',
    'Auto-rollback events',
    ['formula']
)
```

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03MetricsRegistry | `k0/pipelines/p03/ops/metrics.py` | Metric registration pattern |
| QuarantineDetector | `k0/pipelines/p03/feedback/quarantine_detector.py` | Existing metric emission |
| FeedbackRateLimiter | `k0/pipelines/p03/feedback/rate_limiter.py` | Rate limit metrics |
| VelocityAnomalyDetector | `k0/pipelines/p03/feedback/velocity_detector.py` | Velocity metrics |
| P03LearningAnomalyDetector | `k0/pipelines/p03/learning/anomaly_detector.py` | Learning metrics |
| MetricsExporter | `k0/obs/metrics.py` | Counter, gauge, histogram methods |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/ops/quarantine_metrics.py` with all quarantine-related metrics
2. [ ] Register all metrics with `P03MetricsRegistry`
3. [ ] Add `p03_quarantine_signals_total` with reason/severity labels
4. [ ] Add `p03_quarantine_decisions` with decision label (RELEASE, DISCARD, AUTO_RELEASE)
5. [ ] Add `p03_quarantine_auto_released` counter
6. [ ] Add `p03_quarantine_pending_reviews` gauge with severity breakdown
7. [ ] Implement `QuarantineMetricsCollector` class for scheduled gauge updates
8. [ ] Add dashboard queries for quarantine monitoring
9. [ ] Add alerting rules for high quarantine rates
10. [ ] Create tests: `tests/k0/pipelines/p03/ops/test_quarantine_metrics.py`

**Implementation Pattern**:

```python
# k0/pipelines/p03/ops/quarantine_metrics.py
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    import asyncpg


class QuarantineMetricsCollector:
    """
    Collect and emit quarantine-related metrics.

    Provides both event-driven metrics (counters) and
    scheduled gauge updates for pending reviews.

    Dossier Reference: Section 6.21.5
    """

    # Metric names
    SIGNALS_TOTAL = "p03_quarantine_signals_total"
    DECISIONS_TOTAL = "p03_quarantine_decisions_total"
    AUTO_RELEASED_TOTAL = "p03_quarantine_auto_released_total"
    PENDING_REVIEWS = "p03_quarantine_pending_reviews"
    HIGH_SEVERITY_TOTAL = "p03_quarantine_high_severity_total"
    REVIEW_LATENCY = "p03_quarantine_review_latency_seconds"

    def __init__(
        self,
        metrics: Optional[MetricsExporter] = None,
    ):
        self._metrics = metrics

    def record_quarantine(
        self,
        reason: str,
        severity: str,
    ) -> None:
        """Record a quarantine event."""
        if self._metrics:
            self._metrics.counter(
                self.SIGNALS_TOTAL,
                1,
                reason=reason,
                severity=severity,
            )

            if severity == "HIGH":
                self._metrics.counter(
                    self.HIGH_SEVERITY_TOTAL,
                    1,
                    reason=reason,
                )

    def record_decision(
        self,
        decision: str,
        *,
        review_latency_seconds: Optional[float] = None,
    ) -> None:
        """Record a review decision."""
        if self._metrics:
            self._metrics.counter(
                self.DECISIONS_TOTAL,
                1,
                decision=decision,
            )

            if decision == "AUTO_RELEASE":
                self._metrics.counter(
                    self.AUTO_RELEASED_TOTAL,
                    1,
                )

            if review_latency_seconds is not None:
                self._metrics.histogram(
                    self.REVIEW_LATENCY,
                    review_latency_seconds,
                    decision=decision,
                )

    async def update_pending_gauge(
        self,
        *,
        connection: asyncpg.Connection,
    ) -> dict[str, int]:
        """
        Update pending reviews gauge (called periodically).

        Returns counts by severity for monitoring.
        """
        rows = await connection.fetch(
            """
            SELECT severity, COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE decision IS NULL
            GROUP BY severity
            """
        )

        counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
        for row in rows:
            severity = row["severity"]
            count = row["count"]
            counts[severity] = count

            if self._metrics:
                self._metrics.gauge(
                    self.PENDING_REVIEWS,
                    count,
                    severity=severity,
                )

        return counts

    async def get_quarantine_stats(
        self,
        *,
        connection: asyncpg.Connection,
    ) -> dict:
        """Get comprehensive quarantine statistics."""
        # Total by reason
        reason_rows = await connection.fetch(
            """
            SELECT reason, COUNT(*) as count
            FROM st_feedback_quarantine
            GROUP BY reason
            """
        )

        # Total by decision
        decision_rows = await connection.fetch(
            """
            SELECT decision, COUNT(*) as count
            FROM st_feedback_quarantine
            WHERE decision IS NOT NULL
            GROUP BY decision
            """
        )

        # Average review latency
        latency_row = await connection.fetchrow(
            """
            SELECT AVG(reviewed_at - detected_at) as avg_latency_ms
            FROM st_feedback_quarantine
            WHERE reviewed_at IS NOT NULL
            """
        )

        return {
            "by_reason": {r["reason"]: r["count"] for r in reason_rows},
            "by_decision": {d["decision"]: d["count"] for d in decision_rows},
            "avg_review_latency_ms": latency_row["avg_latency_ms"] or 0,
            "pending": sum(
                (await self.update_pending_gauge(connection=connection)).values()
            ),
        }


# Convenience functions for direct emission
def emit_quarantine_metric(
    metrics: MetricsExporter,
    reason: str,
    severity: str,
) -> None:
    """Emit quarantine metric (convenience function)."""
    collector = QuarantineMetricsCollector(metrics)
    collector.record_quarantine(reason, severity)


def emit_decision_metric(
    metrics: MetricsExporter,
    decision: str,
    review_latency_seconds: Optional[float] = None,
) -> None:
    """Emit decision metric (convenience function)."""
    collector = QuarantineMetricsCollector(metrics)
    collector.record_decision(decision, review_latency_seconds=review_latency_seconds)
```

**Alerting Rules** (add to `p03_alerts.yaml`):

```yaml
# Quarantine alerting rules
- alert: P03QuarantineRateHigh
  expr: rate(p03_quarantine_signals_total[5m]) > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High quarantine rate detected"
    description: "P03 is quarantining > 10 signals/minute"

- alert: P03QuarantineHighSeveritySpike
  expr: rate(p03_quarantine_high_severity_total[5m]) > 1
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High-severity quarantine spike"
    description: "Multiple HIGH severity quarantines detected"

- alert: P03QuarantinePendingReviewsHigh
  expr: p03_quarantine_pending_reviews{severity="HIGH"} > 10
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "High-severity reviews pending"
    description: "{{ $value }} HIGH severity signals awaiting review"
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_quarantine_signals_total | counter | reason, severity | Signals quarantined |
| p03_quarantine_decisions_total | counter | decision | Review decisions |
| p03_quarantine_auto_released_total | counter | - | Auto-released signals |
| p03_quarantine_pending_reviews | gauge | severity | Pending review count |
| p03_quarantine_high_severity_total | counter | reason | High severity quarantines |
| p03_quarantine_review_latency_seconds | histogram | decision | Review latency |

**Acceptance Criteria**:

- [ ] `QuarantineMetricsCollector` class created with all methods
- [ ] All quarantine counters emit correctly on events
- [ ] Pending reviews gauge updates on scheduled interval
- [ ] Review latency histogram tracks time from detection to decision
- [ ] Statistics endpoint returns comprehensive quarantine stats
- [ ] Alerting rules added for high quarantine rates
- [ ] Alerting rules added for pending high-severity reviews
- [ ] Integration with Grafana dashboard (Issue 6.1.17)
- [ ] ≥95% test coverage for quarantine metrics

---

#### Issue 6.2.20 — DLQ + Retry Integration Tests

**Status**: 🔲 NOT STARTED

**Goal**: Implement comprehensive integration tests for the entire DLQ, retry, circuit breaker, and quarantine system to validate end-to-end error handling flows.

**Dossier Reference**: Validation of Section 13 "Error Handling & Dead Letter Queue"

**Test Files to Create**:

```text
tests/k0/pipelines/p03/ops/
├── test_error_classifier.py          # 6.2.1 validation
├── test_error_handler.py             # 6.2.2 validation
├── test_dlq_integration.py           # 6.2.3 validation
├── test_retry_config.py              # 6.2.4 validation
├── test_circuit_breaker.py           # 6.2.5-6.2.8 validation
├── test_partial_failure.py           # 6.2.9 validation
├── test_quarantine_detector.py       # 6.2.10-6.2.11 validation
├── test_rate_limiter.py              # 6.2.12 validation (already specified)
├── test_velocity_detector.py         # 6.2.13 validation (already specified)
├── test_auto_release_job.py          # 6.2.14 validation
├── test_quarantine_review_api.py     # 6.2.15 validation
├── test_dlq_cli_commands.py          # 6.2.16 validation
├── test_learning_anomaly_detector.py # 6.2.17 validation
├── test_edge_case_handler.py         # 6.2.18 validation
├── test_quarantine_metrics.py        # 6.2.19 validation
└── integration/
    ├── test_dlq_retry_e2e.py         # End-to-end DLQ flow
    ├── test_circuit_breaker_e2e.py   # End-to-end circuit breaker
    ├── test_quarantine_e2e.py        # End-to-end quarantine flow
    └── test_error_recovery_e2e.py    # Complete error recovery scenarios
```

**Existing Test Patterns to Follow**:

| Test File | Path | Pattern to Reuse |
|-----------|------|------------------|
| test_p03_envelope.py | `tests/k0/pipelines/p03/test_p03_envelope.py` | P03 context testing |
| test_p03_qos_integration.py | `tests/k0/pipelines/p03/test_p03_qos_integration.py` | K0 integration patterns |
| test_dlq.py | `tests/k0/storage/test_dlq.py` | DLQ storage testing |

**Work To Do**:

1. [ ] Create test directory structure as defined above
2. [ ] Implement `test_error_classifier.py` (all 4 error categories)
3. [ ] Implement `test_error_handler.py` (routing to retry/DLQ/circuit breaker)
4. [ ] Implement `test_dlq_integration.py` (DLQStore P03 integration)
5. [ ] Implement `test_retry_config.py` (phase-specific configs)
6. [ ] Implement `test_circuit_breaker.py` (state transitions, fallbacks)
7. [ ] Implement `test_partial_failure.py` (all 3 strategies)
8. [ ] Implement `test_quarantine_detector.py` (detection and quarantine)
9. [ ] Implement `test_auto_release_job.py` (48h release, batch processing)
10. [ ] Implement `test_quarantine_review_api.py` (review decisions)
11. [ ] Implement `test_dlq_cli_commands.py` (all CLI commands)
12. [ ] Implement `test_learning_anomaly_detector.py` (drift, contradictions, regression)
13. [ ] Implement `test_edge_case_handler.py` (all 9 edge cases)
14. [ ] Implement `test_quarantine_metrics.py` (metric emission)
15. [ ] Implement `test_dlq_retry_e2e.py` (end-to-end DLQ flow)
16. [ ] Implement `test_circuit_breaker_e2e.py` (end-to-end circuit breaker)
17. [ ] Implement `test_quarantine_e2e.py` (end-to-end quarantine)
18. [ ] Implement `test_error_recovery_e2e.py` (complete recovery scenarios)
19. [ ] Ensure ≥90% coverage for resilience module
20. [ ] All tests run in CI with < 10 minute runtime

**Implementation Pattern**:

```python
# tests/k0/pipelines/p03/ops/integration/test_dlq_retry_e2e.py
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from k0.pipelines.p03.ops.error_classifier import ErrorClassifier, P03ErrorCategory
from k0.pipelines.p03.ops.error_handler import P03ErrorHandler, P03ErrorContext
from k0.storage.dlq import DLQStore, DeadLetter
from k0.outbox.scheduler import RetryScheduler


class TestDLQRetryEndToEnd:
    """End-to-end tests for DLQ and retry flow."""

    @pytest.fixture
    def mock_dlq_store(self):
        store = AsyncMock(spec=DLQStore)
        store.record.return_value = "dlq_123"
        store.list_pending.return_value = []
        return store

    @pytest.fixture
    def mock_retry_scheduler(self):
        scheduler = AsyncMock(spec=RetryScheduler)
        return scheduler

    @pytest.fixture
    def error_handler(self, mock_dlq_store, mock_retry_scheduler):
        return P03ErrorHandler(
            dlq_store=mock_dlq_store,
            retry_scheduler=mock_retry_scheduler,
        )

    @pytest.mark.asyncio
    async def test_transient_error_retries_then_dlq(
        self,
        error_handler,
        mock_retry_scheduler,
        mock_dlq_store,
    ):
        """
        Given: A transient error that exceeds max retries
        When: Error handler processes the error
        Then: Error is retried up to max_attempts, then sent to DLQ
        """
        # Arrange
        context = P03ErrorContext(
            cycle_id="cycle_123",
            phase="R2",
            tenant_id="tenant_1",
            space_id="space_1",
            retry_count=3,  # Already at max
            max_retries=3,
        )
        error = ConnectionError("Database connection timeout")

        # Act
        result = await error_handler.handle_error(error, context)

        # Assert
        assert result.action == "DLQ"
        mock_dlq_store.record.assert_called_once()
        call_args = mock_dlq_store.record.call_args
        assert call_args.kwargs["error_type"] == "TRANSIENT"
        assert call_args.kwargs["phase"] == "R2"

    @pytest.mark.asyncio
    async def test_validation_error_immediate_dlq(
        self,
        error_handler,
        mock_dlq_store,
    ):
        """
        Given: A validation error
        When: Error handler processes the error
        Then: Error is sent directly to DLQ without retry
        """
        # Arrange
        context = P03ErrorContext(
            cycle_id="cycle_456",
            phase="R3",
            tenant_id="tenant_1",
            space_id="space_1",
        )
        error = ValueError("Invalid schema")

        # Act
        result = await error_handler.handle_error(error, context)

        # Assert
        assert result.action == "DLQ"
        assert result.retry_scheduled is False

    @pytest.mark.asyncio
    async def test_fatal_error_triggers_circuit_breaker(
        self,
        error_handler,
    ):
        """
        Given: A fatal error (MemoryError)
        When: Error handler processes the error
        Then: Circuit breaker is triggered and cycle aborts
        """
        # Arrange
        context = P03ErrorContext(
            cycle_id="cycle_789",
            phase="R5",
            tenant_id="tenant_1",
            space_id="space_1",
        )
        error = MemoryError("Out of memory")

        # Act
        result = await error_handler.handle_error(error, context)

        # Assert
        assert result.action == "ABORT"
        assert result.circuit_breaker_triggered is True

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(
        self,
        error_handler,
        mock_retry_scheduler,
    ):
        """
        Given: A transient error with retries remaining
        When: Error handler schedules retry
        Then: Retry uses exponential backoff
        """
        # Arrange
        context = P03ErrorContext(
            cycle_id="cycle_abc",
            phase="R7",
            tenant_id="tenant_1",
            space_id="space_1",
            retry_count=1,
            max_retries=3,
        )
        error = TimeoutError("Lock acquisition timeout")

        # Act
        result = await error_handler.handle_error(error, context)

        # Assert
        assert result.action == "RETRY"
        mock_retry_scheduler.schedule.assert_called_once()
        # Verify backoff: 2^1 * base_delay
        call_args = mock_retry_scheduler.schedule.call_args
        assert call_args.kwargs["delay_seconds"] > 0


class TestCircuitBreakerEndToEnd:
    """End-to-end tests for circuit breaker flow."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """
        Given: Multiple consecutive failures
        When: Failure count exceeds threshold
        Then: Circuit opens and requests are rejected
        """
        from k0.pipelines.p03.ops.circuit_breaker import P03CircuitBreaker

        breaker = P03CircuitBreaker(
            name="test_breaker",
            failure_threshold=3,
            reset_timeout_seconds=30,
        )

        # Record failures
        for _ in range(3):
            breaker.record_failure()

        # Assert circuit is open
        assert breaker.is_open() is True
        assert breaker.state.value == "OPEN"

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self):
        """
        Given: An open circuit
        When: Reset timeout elapses
        Then: Circuit transitions to half-open
        """
        from k0.pipelines.p03.ops.circuit_breaker import P03CircuitBreaker
        import time

        breaker = P03CircuitBreaker(
            name="test_breaker",
            failure_threshold=3,
            reset_timeout_seconds=0.1,  # 100ms for testing
        )

        # Open circuit
        for _ in range(3):
            breaker.record_failure()

        assert breaker.is_open() is True

        # Wait for reset timeout
        await asyncio.sleep(0.15)

        # Circuit should be half-open
        assert breaker.is_half_open() is True

    @pytest.mark.asyncio
    async def test_circuit_closes_on_success(self):
        """
        Given: A half-open circuit
        When: A request succeeds
        Then: Circuit closes
        """
        from k0.pipelines.p03.ops.circuit_breaker import P03CircuitBreaker

        breaker = P03CircuitBreaker(
            name="test_breaker",
            failure_threshold=3,
            reset_timeout_seconds=0.1,
        )

        # Open and wait for half-open
        for _ in range(3):
            breaker.record_failure()
        await asyncio.sleep(0.15)

        # Record success
        breaker.record_success()

        # Assert circuit is closed
        assert breaker.is_closed() is True


class TestQuarantineEndToEnd:
    """End-to-end tests for quarantine flow."""

    @pytest.fixture
    def mock_connection(self):
        conn = AsyncMock()
        return conn

    @pytest.mark.asyncio
    async def test_rate_limited_signal_quarantined(self, mock_connection):
        """
        Given: A user exceeding rate limit
        When: Signal is processed
        Then: Signal is quarantined with RATE_LIMIT reason
        """
        from k0.pipelines.p03.feedback.quarantine_detector import (
            QuarantineDetector,
            QuarantineReason,
        )

        # Mock rate limit exceeded
        mock_connection.fetchrow.return_value = {"signal_count": 150}
        mock_connection.execute.return_value = None

        detector = QuarantineDetector(rate_limit_per_minute=100)

        result = await detector.check_and_quarantine(
            signal_id="sig_123",
            space_id="space_1",
            user_id="user_1",
            connection=mock_connection,
        )

        assert result.quarantined is True
        assert result.reason == QuarantineReason.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_velocity_spike_quarantined(self, mock_connection):
        """
        Given: A sudden volume spike (10x baseline)
        When: Signal is processed
        Then: Signal is quarantined with VELOCITY_SPIKE reason
        """
        from k0.pipelines.p03.feedback.quarantine_detector import (
            QuarantineDetector,
            QuarantineReason,
        )

        # Mock: rate limit not exceeded
        mock_connection.fetchrow.side_effect = [
            {"signal_count": 50},  # Rate limit check
            {"count": 100},  # Recent window (5 min)
            {"count": 60},  # Baseline window (1 hour)
        ]
        mock_connection.execute.return_value = None

        detector = QuarantineDetector(
            rate_limit_per_minute=100,
            velocity_spike_multiplier=10.0,
        )

        result = await detector.check_and_quarantine(
            signal_id="sig_456",
            space_id="space_1",
            user_id="user_1",
            connection=mock_connection,
        )

        # 100 in 5 min = 20/min, 60 in 1 hour = 1/min, ratio = 20x
        assert result.quarantined is True
        assert result.reason == QuarantineReason.VELOCITY_SPIKE

    @pytest.mark.asyncio
    async def test_auto_release_after_48h(self, mock_connection):
        """
        Given: A quarantined signal past auto_release_at
        When: Auto-release job runs
        Then: Signal is released with decision='RELEASE', reviewed_by='AUTO'
        """
        from k0.pipelines.p03.maintenance.quarantine_cleanup import (
            QuarantineAutoReleaseJob,
        )
        import time

        # Mock signals ready for release
        mock_connection.fetch.return_value = [
            {"quarantine_id": "q_123", "signal_id": "sig_123", "space_id": "space_1"},
        ]
        mock_connection.execute.return_value = "UPDATE 1"

        job = QuarantineAutoReleaseJob()
        result = await job.run(connection=mock_connection)

        assert result.signals_released == 1
        assert result.signals_failed == 0

        # Verify updates
        calls = mock_connection.execute.call_args_list
        assert len(calls) >= 2  # quarantine update + signal update


class TestErrorRecoveryScenarios:
    """Complete error recovery scenario tests."""

    @pytest.mark.asyncio
    async def test_partial_write_recovery_commit_partial(self):
        """
        Given: A partial R7 write failure
        When: COMMIT_PARTIAL strategy is applied
        Then: Successful writes persist, failed items go to DLQ
        """
        from k0.pipelines.p03.ops.partial_failure import (
            PartialFailureHandler,
            P03PartialFailureStrategy,
            P03BatchResult,
        )

        handler = PartialFailureHandler(
            strategy=P03PartialFailureStrategy.COMMIT_PARTIAL,
        )

        # Simulate batch with partial failure
        batch_result = P03BatchResult(
            total_items=10,
            successful_items=7,
            failed_items=3,
            failed_item_ids=["item_8", "item_9", "item_10"],
        )

        result = await handler.handle_partial_failure(batch_result)

        assert result.committed_count == 7
        assert result.dlq_count == 3
        assert result.strategy_applied == P03PartialFailureStrategy.COMMIT_PARTIAL

    @pytest.mark.asyncio
    async def test_dlq_requeue_success(self):
        """
        Given: A DLQ entry from transient failure
        When: Entry is requeued after fix
        Then: Entry is processed successfully
        """
        # This would be a more complex integration test
        # requiring actual database setup
        pass
```

```python
# tests/k0/pipelines/p03/ops/test_error_classifier.py
import pytest
import asyncpg

from k0.pipelines.p03.ops.error_classifier import (
    ErrorClassifier,
    P03ErrorCategory,
    TRANSIENT_EXCEPTIONS,
    VALIDATION_EXCEPTIONS,
    FATAL_EXCEPTIONS,
)


class TestErrorClassifier:
    """Unit tests for ErrorClassifier."""

    @pytest.fixture
    def classifier(self):
        return ErrorClassifier()

    @pytest.mark.parametrize("error_class", [
        ConnectionError,
        TimeoutError,
        asyncpg.TooManyConnectionsError,
    ])
    def test_transient_errors_classified_correctly(self, classifier, error_class):
        """Transient errors should be classified as TRANSIENT."""
        error = error_class("test error")
        result = classifier.classify(error)
        assert result == P03ErrorCategory.TRANSIENT

    @pytest.mark.parametrize("error_class", [
        ValueError,
        KeyError,
    ])
    def test_validation_errors_classified_correctly(self, classifier, error_class):
        """Validation errors should be classified as VALIDATION."""
        error = error_class("test error")
        result = classifier.classify(error)
        assert result == P03ErrorCategory.VALIDATION

    @pytest.mark.parametrize("error_class", [
        MemoryError,
        SystemExit,
    ])
    def test_fatal_errors_classified_correctly(self, classifier, error_class):
        """Fatal errors should be classified as FATAL."""
        error = error_class("test error")
        result = classifier.classify(error)
        assert result == P03ErrorCategory.FATAL

    def test_unknown_error_defaults_to_logic(self, classifier):
        """Unknown errors should default to LOGIC category."""

        class CustomError(Exception):
            pass

        error = CustomError("unknown error")
        result = classifier.classify(error)
        assert result == P03ErrorCategory.LOGIC

    def test_is_retriable_true_for_transient(self, classifier):
        """Transient errors should be retriable."""
        error = ConnectionError("timeout")
        assert classifier.is_retriable(error) is True

    def test_is_retriable_false_for_validation(self, classifier):
        """Validation errors should not be retriable."""
        error = ValueError("invalid schema")
        assert classifier.is_retriable(error) is False

    def test_is_retriable_false_for_fatal(self, classifier):
        """Fatal errors should not be retriable."""
        error = MemoryError("out of memory")
        assert classifier.is_retriable(error) is False
```

**Coverage Requirements**:

| Module | Required Coverage | Test Location |
|--------|-------------------|---------------|
| error_classifier.py | ≥95% | `test_error_classifier.py` |
| error_handler.py | ≥90% | `test_error_handler.py` |
| circuit_breaker.py | ≥90% | `test_circuit_breaker.py` |
| partial_failure.py | ≥90% | `test_partial_failure.py` |
| quarantine_detector.py | ≥95% | `test_quarantine_detector.py` |
| rate_limiter.py | ≥95% | `test_rate_limiter.py` |
| velocity_detector.py | ≥95% | `test_velocity_detector.py` |
| anomaly_detector.py | ≥95% | `test_learning_anomaly_detector.py` |
| edge_case_handler.py | ≥90% | `test_edge_case_handler.py` |
| quarantine_metrics.py | ≥90% | `test_quarantine_metrics.py` |
| Integration tests | N/A | `integration/*.py` |

**Acceptance Criteria**:

- [ ] All 18 test files created and passing
- [ ] ≥90% code coverage for `k0/pipelines/p03/ops/` module
- [ ] Integration tests validate end-to-end DLQ flow
- [ ] Integration tests validate circuit breaker state transitions
- [ ] Integration tests validate quarantine detection and release
- [ ] Integration tests validate error recovery scenarios
- [ ] All error categories tested (TRANSIENT, VALIDATION, LOGIC, FATAL)
- [ ] All circuit breaker states tested (CLOSED, OPEN, HALF_OPEN)
- [ ] All partial failure strategies tested (COMMIT_PARTIAL, ROLLBACK_ALL, QUARANTINE_BATCH)
- [ ] CLI commands tested with mock DLQ store
- [ ] Tests run in CI with < 10 minute runtime
- [ ] No flaky tests (all deterministic)

---

### Epic 6.3 — Security & Privacy Enforcement

> **Scope**: Implement RLS, privacy bands, GDPR compliance, and security monitoring.
>
> **Dossier Reference**: Section 14 "Security & Privacy"

#### Epic 6.3 Issues Summary

| Issue | Title | Goal |
|-------|-------|------|
| 6.3.1 | RLS policy for st_learned_weights | Space isolation |
| 6.3.2 | RLS policy for st_consolidation_audit | Audit isolation |
| 6.3.3 | RLS policy for st_pruned_entities | Pruned entity isolation |
| 6.3.4 | RLS policy for st_decay_feedback | Decay feedback isolation |
| 6.3.5 | Application context setup helper | Context management |
| 6.3.6 | Cross-space isolation integration tests | Isolation verification |
| 6.3.7 | RLS enforcement verification job | RLS health check |
| 6.3.8 | Query audit scanner for missing space_id | Query scanning |
| 6.3.9 | Weekly automated security scan job | Security automation |
| 6.3.10 | PrivacyBandEnforcer implementation | GREEN/AMBER/RED enforcement |
| 6.3.11 | Location privacy masking | Location precision |
| 6.3.12 | Tenant isolation query builder | Query isolation |
| 6.3.13 | P03AuditTrail implementation | Audit logging |
| 6.3.14 | GDPR erasure handler | Right to erasure |
| 6.3.15 | Tombstone lifecycle management | Soft delete lifecycle |
| 6.3.16 | Retention policy enforcement | Band-based retention |
| 6.3.17 | Content fingerprinting for dedup | Secure hashing |
| 6.3.18 | Cross-space leakage metrics | Security metrics |
| 6.3.19 | Security alerting rules | Security alerts |
| 6.3.20 | Security integration tests | Test coverage |

---

#### Issue 6.3.1 — RLS policy for st_learned_weights

**Status**: 🔲 NOT STARTED

**Goal**: Verify and enhance the Row-Level Security policy for st_learned_weights table, implement runtime context helper, and add comprehensive isolation tests.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 6.17

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| st_learned_weights migration | `k0/db/alembic/versions/0040_st_learned_weights.py` | RLS policy already created |
| Migration tests | `tests/k0/pipelines/p03/test_p03_storage_migrations.py` | RLS test pattern (lines 1548-1553) |
| Connection scope | `k0/db/connection.py` | Context manager pattern |
| Dossier isolation spec | `P03_consolidation_dossier_v2.md` Section 14.11 | Isolation boundaries |

**RLS Policy Already Implemented** (in migration 0040):

```sql
-- Already exists in 0040_st_learned_weights.py
ALTER TABLE st_learned_weights ENABLE ROW LEVEL SECURITY;

CREATE POLICY learned_weights_isolation ON st_learned_weights
    FOR ALL USING (space_id = current_setting('app.current_space_id', true)::text)
```

**Work To Do**:

1. [ ] Verify migration 0040 RLS policy is correctly applied
2. [ ] Create `k0/db/context_helper.py` with `set_space_context()` helper
3. [ ] Add `set_tenant_context()` for tenant-level isolation
4. [ ] Add `clear_context()` to reset application settings
5. [ ] Create context manager `isolation_scope()` for RLS-enabled queries
6. [ ] Add tests for cross-space access prevention
7. [ ] Add tests for context helper functions
8. [ ] Verify RLS policy blocks access when context not set
9. [ ] Document RLS usage pattern for P03 developers
10. [ ] Add metrics for RLS policy blocks

**Implementation Pattern**:

```python
# k0/db/context_helper.py
"""Database context helpers for Row-Level Security enforcement.

Provides functions to set application-level context variables that
RLS policies use for tenant/space isolation.

Dossier Reference: Section 14.11 Learning Data Isolation
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, Optional

if TYPE_CHECKING:
    from asyncpg import Connection


async def set_space_context(
    conn: "Connection",
    space_id: str,
) -> None:
    """
    Set the current space context for RLS enforcement.

    This MUST be called before any query against RLS-protected tables.
    The context is transaction-scoped (SET LOCAL).

    Args:
        conn: Active database connection
        space_id: Space ID for isolation

    Example:
        async with connection_scope() as conn:
            await set_space_context(conn, "space_123")
            # Now queries to st_learned_weights are filtered by space_id
            rows = await conn.fetch("SELECT * FROM st_learned_weights")
    """
    await conn.execute(
        "SET LOCAL app.current_space_id = $1",
        space_id,
    )


async def set_tenant_context(
    conn: "Connection",
    tenant_id: str,
) -> None:
    """
    Set the current tenant context for RLS enforcement.

    Args:
        conn: Active database connection
        tenant_id: Tenant ID for isolation
    """
    await conn.execute(
        "SET LOCAL app.current_tenant_id = $1",
        tenant_id,
    )


async def set_full_context(
    conn: "Connection",
    *,
    tenant_id: str,
    space_id: str,
    user_id: Optional[str] = None,
) -> None:
    """
    Set complete isolation context for P03 operations.

    Args:
        conn: Active database connection
        tenant_id: Tenant ID
        space_id: Space ID
        user_id: Optional user ID for audit
    """
    await conn.execute(
        "SET LOCAL app.current_tenant_id = $1",
        tenant_id,
    )
    await conn.execute(
        "SET LOCAL app.current_space_id = $1",
        space_id,
    )
    if user_id:
        await conn.execute(
            "SET LOCAL app.current_user_id = $1",
            user_id,
        )


async def clear_context(conn: "Connection") -> None:
    """
    Clear all application context settings.

    Primarily for testing; normally context is cleared when
    transaction ends.
    """
    await conn.execute("RESET app.current_space_id")
    await conn.execute("RESET app.current_tenant_id")
    await conn.execute("RESET app.current_user_id")


@asynccontextmanager
async def isolation_scope(
    conn: "Connection",
    *,
    tenant_id: str,
    space_id: str,
    user_id: Optional[str] = None,
) -> AsyncIterator["Connection"]:
    """
    Context manager that sets isolation context and clears on exit.

    Usage:
        async with connection_scope() as conn:
            async with isolation_scope(conn, tenant_id="t1", space_id="s1"):
                # All queries here are isolated
                rows = await conn.fetch("SELECT * FROM st_learned_weights")
    """
    await set_full_context(
        conn,
        tenant_id=tenant_id,
        space_id=space_id,
        user_id=user_id,
    )
    try:
        yield conn
    finally:
        await clear_context(conn)
```

**Test Pattern**:

```python
# tests/k0/db/test_context_helper.py
import pytest
from k0.db.connection import connection_scope
from k0.db.context_helper import (
    set_space_context,
    set_full_context,
    clear_context,
    isolation_scope,
)


class TestSetSpaceContext:
    """Tests for set_space_context()."""

    @pytest.mark.asyncio
    async def test_set_space_context_sets_variable(self):
        """Verify SET LOCAL sets the application variable."""
        async with connection_scope() as conn:
            await set_space_context(conn, "space_123")

            result = await conn.fetchval(
                "SELECT current_setting('app.current_space_id', true)"
            )
            assert result == "space_123"

    @pytest.mark.asyncio
    async def test_context_is_transaction_scoped(self):
        """Verify context is cleared after transaction."""
        async with connection_scope() as conn:
            async with conn.transaction():
                await set_space_context(conn, "space_abc")
                result = await conn.fetchval(
                    "SELECT current_setting('app.current_space_id', true)"
                )
                assert result == "space_abc"

            # After transaction, context should be reset
            result = await conn.fetchval(
                "SELECT current_setting('app.current_space_id', true)"
            )
            assert result in (None, "")


class TestRLSEnforcement:
    """Integration tests for RLS on st_learned_weights."""

    @pytest.mark.asyncio
    async def test_rls_blocks_cross_space_access(self):
        """Verify RLS blocks access to other space's data."""
        async with connection_scope() as conn:
            # Insert test data for space_a
            await set_space_context(conn, "space_a")
            await conn.execute("""
                INSERT INTO st_learned_weights
                (param_id, param_key, param_scope, space_id, current_value,
                 prior_value, last_updated_at, created_at, updated_at)
                VALUES ('p1', 'test_key', 'space', 'space_a', 1.0,
                        1.0, 0, 0, 0)
                ON CONFLICT DO NOTHING
            """)

            # Switch to space_b context
            await set_space_context(conn, "space_b")

            # Query should return empty (RLS blocks space_a data)
            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE param_key = 'test_key'"
            )
            assert len(rows) == 0  # Cannot see space_a data

    @pytest.mark.asyncio
    async def test_rls_allows_same_space_access(self):
        """Verify RLS allows access to own space's data."""
        async with connection_scope() as conn:
            await set_space_context(conn, "space_test")

            # Insert and read in same context
            await conn.execute("""
                INSERT INTO st_learned_weights
                (param_id, param_key, param_scope, space_id, current_value,
                 prior_value, last_updated_at, created_at, updated_at)
                VALUES ('p2', 'own_key', 'space', 'space_test', 2.0,
                        1.0, 0, 0, 0)
                ON CONFLICT DO NOTHING
            """)

            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE param_key = 'own_key'"
            )
            assert len(rows) == 1  # Can see own data

    @pytest.mark.asyncio
    async def test_rls_blocks_when_no_context(self):
        """Verify RLS returns empty when no context set."""
        async with connection_scope() as conn:
            # No context set - should see nothing
            rows = await conn.fetch("SELECT * FROM st_learned_weights")
            # RLS with current_setting(..., true) returns NULL, which
            # won't match any space_id, so result is empty
            assert len(rows) == 0
```

**Metrics Emitted**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_rls_context_set_total | counter | table | Context set operations |
| p03_rls_policy_blocks_total | counter | table, policy | RLS policy block events |

**Acceptance Criteria**:

- [ ] `set_space_context()` correctly sets `app.current_space_id`
- [ ] `set_tenant_context()` correctly sets `app.current_tenant_id`
- [ ] `set_full_context()` sets all three context variables
- [ ] `clear_context()` resets all context variables
- [ ] `isolation_scope()` context manager works correctly
- [ ] RLS blocks cross-space access to st_learned_weights
- [ ] RLS allows same-space access to st_learned_weights
- [ ] RLS returns empty (not error) when no context set
- [ ] Context is transaction-scoped (cleared on transaction end)
- [ ] ≥95% test coverage for context_helper.py
- [ ] Integration tests pass with real PostgreSQL

---

#### Issue 6.3.2 — RLS policy for st_consolidation_audit

**Status**: 🔲 NOT STARTED

**Goal**: Verify and enhance the Row-Level Security policy for st_consolidation_audit table, add audit-specific isolation tests.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 6.20

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| st_consolidation_audit migration | `k0/db/alembic/versions/0036_st_consolidation_audit.py` | RLS policy already created |
| Migration tests | `tests/k0/pipelines/p03/test_p03_storage_migrations.py` | RLS test (lines 995-1001) |
| Context helper | `k0/db/context_helper.py` | set_space_context() from Issue 6.3.1 |
| Audit logger | `k0/pipelines/p03/audit_logger.py` | P03DecisionAuditLogger |

**RLS Policy Already Implemented** (in migration 0036):

```sql
-- Already exists in 0036_st_consolidation_audit.py
ALTER TABLE st_consolidation_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_isolation ON st_consolidation_audit
    FOR ALL USING (space_id = current_setting('app.current_space_id', true))
```

**Work To Do**:

1. [ ] Verify migration 0036 RLS policy is correctly applied
2. [ ] Add integration test: cross-space audit access blocked
3. [ ] Add integration test: same-space audit access allowed
4. [ ] Add integration test: tenant isolation for audit records
5. [ ] Verify P03DecisionAuditLogger sets context before writes
6. [ ] Add test: audit records cannot be read across spaces
7. [ ] Add test: audit history query respects isolation
8. [ ] Document audit RLS usage for explainability queries

**Implementation Pattern**:

```python
# Integration with audit_logger.py
# k0/pipelines/p03/audit_logger.py already uses space_id

class P03DecisionAuditLogger:
    """
    Audit logger with RLS-aware writes.

    All writes MUST have space_id set in context or in the record.
    The RLS policy will filter reads automatically.
    """

    async def log_decision(
        self,
        *,
        memory_id: str,
        action: AuditAction,
        space_id: str,
        tenant_id: str,
        # ... other params
        connection: "asyncpg.Connection",
    ) -> str:
        """
        Log a consolidation decision.

        Note: RLS enforces isolation on reads. For writes, we
        explicitly include space_id in the record.
        """
        # Ensure context is set for any subsequent reads
        await set_space_context(connection, space_id)

        audit_id = generate_ulid()
        await connection.execute(
            """
            INSERT INTO st_consolidation_audit (
                audit_id, memory_id, action, space_id, tenant_id,
                created_at, ...
            ) VALUES ($1, $2, $3, $4, $5, $6, ...)
            """,
            audit_id, memory_id, action.value, space_id, tenant_id,
            now_ms(), # ...
        )
        return audit_id
```

**Test Pattern**:

```python
# tests/k0/pipelines/p03/security/test_audit_rls.py
import pytest
from k0.db.connection import connection_scope
from k0.db.context_helper import set_space_context


class TestAuditRLSIsolation:
    """Integration tests for RLS on st_consolidation_audit."""

    @pytest.mark.asyncio
    async def test_audit_cross_space_blocked(self):
        """Verify RLS blocks access to other space's audit records."""
        async with connection_scope() as conn:
            # Insert audit record for space_a
            await set_space_context(conn, "space_a")
            await conn.execute("""
                INSERT INTO st_consolidation_audit
                (audit_id, memory_id, source_table, action, space_id,
                 tenant_id, created_at)
                VALUES ('a1', 'mem1', 'st_epi', 'REINFORCE', 'space_a',
                        'tenant1', 0)
                ON CONFLICT DO NOTHING
            """)

            # Switch to space_b - should not see space_a's audit
            await set_space_context(conn, "space_b")
            rows = await conn.fetch(
                "SELECT * FROM st_consolidation_audit WHERE audit_id = 'a1'"
            )
            assert len(rows) == 0  # Blocked by RLS

    @pytest.mark.asyncio
    async def test_audit_same_space_allowed(self):
        """Verify RLS allows access to own space's audit records."""
        async with connection_scope() as conn:
            await set_space_context(conn, "space_x")
            await conn.execute("""
                INSERT INTO st_consolidation_audit
                (audit_id, memory_id, source_table, action, space_id,
                 tenant_id, created_at)
                VALUES ('a2', 'mem2', 'st_sem', 'DECAY', 'space_x',
                        'tenant1', 0)
                ON CONFLICT DO NOTHING
            """)

            # Same context - should see record
            rows = await conn.fetch(
                "SELECT * FROM st_consolidation_audit WHERE audit_id = 'a2'"
            )
            assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_explainability_query_isolated(self):
        """Verify explainability queries respect RLS."""
        async with connection_scope() as conn:
            # Create audit records in different spaces
            for space in ["space_1", "space_2"]:
                await set_space_context(conn, space)
                await conn.execute("""
                    INSERT INTO st_consolidation_audit
                    (audit_id, memory_id, source_table, action, space_id,
                     tenant_id, created_at, explanation)
                    VALUES ($1, 'mem_shared', 'st_epi', 'CREATE', $2,
                            'tenant1', 0, 'Test explanation')
                    ON CONFLICT DO NOTHING
                """, f"audit_{space}", space)

            # Query in space_1 context
            await set_space_context(conn, "space_1")
            rows = await conn.fetch("""
                SELECT explanation FROM st_consolidation_audit
                WHERE memory_id = 'mem_shared'
            """)
            assert len(rows) == 1
            assert rows[0]["explanation"] == "Test explanation"
```

**Acceptance Criteria**:

- [ ] Migration 0036 RLS policy verified as correct
- [ ] Cross-space audit read access blocked by RLS
- [ ] Same-space audit read access allowed
- [ ] Audit records include space_id on all writes
- [ ] P03DecisionAuditLogger sets context before operations
- [ ] Explainability queries respect RLS isolation
- [ ] Audit history queries filtered by space
- [ ] ≥95% test coverage for audit RLS scenarios

---

#### Issue 6.3.3 — RLS policy for st_pruned_entities

**Status**: 🔲 NOT STARTED

**Goal**: Create st_pruned_entities table migration with Row-Level Security for regret tracking with space isolation.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 6.19

**Note**: st_pruned_entities migration does NOT exist yet. This issue creates both the table and RLS policy.

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Dossier schema | `P03_consolidation_dossier_v2.md` Section 6.19.1 | Full table schema |
| Dossier RLS | `P03_consolidation_dossier_v2.md` Section 6.19.2 | RLS policy definition |
| Prune regret detector | `k0/modules/consolidation/algorithms/prune_regret_detector.py` | Uses st_pruned_entities |
| Context helper | `k0/db/context_helper.py` | set_space_context() from Issue 6.3.1 |
| Migration pattern | `k0/db/alembic/versions/0040_st_learned_weights.py` | RLS migration pattern |

**Schema from Dossier §6.19.1**:

```sql
CREATE TABLE st_pruned_entities (
  -- Identity
  prune_id TEXT PRIMARY KEY,              -- Unique prune event ID
  entity_id TEXT NOT NULL,                -- Original entity ID
  entity_type TEXT NOT NULL,              -- PERSON, PLACE, THING, etc.

  -- Matching data (for regret detection)
  canonical_name TEXT NOT NULL,           -- Normalized name for fuzzy matching
  embedding VECTOR(1024) NOT NULL,        -- Embedding for semantic matching

  -- Context
  space_id TEXT NOT NULL,                 -- Isolation by space
  layer_table TEXT NOT NULL,              -- Source table
  decay_factor_at_prune REAL NOT NULL,    -- What decay_factor was when pruned
  lambda_at_prune REAL NOT NULL,          -- What λ was used

  -- Timestamps
  pruned_at BIGINT NOT NULL,              -- When pruned (epoch ms)
  matched_query_id TEXT,                  -- If regret detected, which query matched
  matched_at BIGINT,                      -- When regret detected
  match_type TEXT,                        -- STRONG_MATCH, LIKELY_MATCH, SEMANTIC_MATCH
  match_confidence REAL                   -- Match confidence [0, 1]
);
```

**Work To Do**:

1. [ ] Create migration `0049_st_pruned_entities.py`
2. [ ] Define all columns per dossier §6.19.1
3. [ ] Create index `idx_pruned_entity_type` (entity_type, space_id)
4. [ ] Create index `idx_pruned_space_time` (space_id, pruned_at DESC)
5. [ ] Create partial vector index `idx_pruned_embedding` (WHERE matched_at IS NULL)
6. [ ] Create partial index `idx_pruned_cleanup` (WHERE matched_at IS NULL)
7. [ ] Enable RLS: `ALTER TABLE st_pruned_entities ENABLE ROW LEVEL SECURITY`
8. [ ] Create RLS policy `pruned_entities_isolation` per §6.19.2
9. [ ] Add downgrade to drop policy, indexes, and table
10. [ ] Create tests: `tests/k0/pipelines/p03/test_p03_storage_migrations.py` for 0049
11. [ ] Add integration tests for RLS isolation

**Implementation Pattern**:

```python
# k0/db/alembic/versions/0049_st_pruned_entities.py
"""Create st_pruned_entities table for regret tracking.

Revision ID: 0049
Revises: 0048
Create Date: 2026-01-04

Track pruned entities for 14 days to detect regret (user queries
a pruned entity). Enables learning to adjust decay rates.

Dossier Reference: Section 6.19 st_pruned_entities
Retention: 14 days
Isolation: RLS enforced for space-level security
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0049"
down_revision: str = "0048"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create st_pruned_entities table with RLS."""
    op.create_table(
        "st_pruned_entities",
        # Identity
        sa.Column("prune_id", sa.Text, primary_key=True),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        # Matching data
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        # Context
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("layer_table", sa.Text, nullable=False),
        sa.Column("decay_factor_at_prune", sa.Float, nullable=False),
        sa.Column("lambda_at_prune", sa.Float, nullable=False),
        # Timestamps
        sa.Column("pruned_at", sa.BigInteger, nullable=False),
        sa.Column("matched_query_id", sa.Text, nullable=True),
        sa.Column("matched_at", sa.BigInteger, nullable=True),
        sa.Column("match_type", sa.Text, nullable=True),
        sa.Column("match_confidence", sa.Float, nullable=True),
    )

    # Core indexes
    op.create_index(
        "idx_pruned_entity_type",
        "st_pruned_entities",
        ["entity_type", "space_id"],
    )
    op.create_index(
        "idx_pruned_space_time",
        "st_pruned_entities",
        ["space_id", sa.text("pruned_at DESC")],
    )

    # Partial vector index for semantic matching (unmatched only)
    op.execute("""
        CREATE INDEX idx_pruned_embedding ON st_pruned_entities
        USING ivfflat (embedding vector_cosine_ops)
        WHERE matched_at IS NULL
    """)

    # Cleanup index (for nightly 14-day deletion)
    op.execute("""
        CREATE INDEX idx_pruned_cleanup ON st_pruned_entities(pruned_at)
        WHERE matched_at IS NULL
    """)

    # Enable RLS
    op.execute("ALTER TABLE st_pruned_entities ENABLE ROW LEVEL SECURITY")

    # Create isolation policy
    op.execute("""
        CREATE POLICY pruned_entities_isolation ON st_pruned_entities
            FOR ALL USING (space_id = current_setting('app.current_space_id', true))
    """)


def downgrade() -> None:
    """Drop st_pruned_entities table."""
    op.execute("DROP POLICY IF EXISTS pruned_entities_isolation ON st_pruned_entities")
    op.execute("DROP INDEX IF EXISTS idx_pruned_cleanup")
    op.execute("DROP INDEX IF EXISTS idx_pruned_embedding")
    op.drop_index("idx_pruned_space_time", table_name="st_pruned_entities")
    op.drop_index("idx_pruned_entity_type", table_name="st_pruned_entities")
    op.drop_table("st_pruned_entities")
```

**Test Pattern**:

```python
# tests/k0/pipelines/p03/security/test_pruned_entities_rls.py
import pytest
from k0.db.connection import connection_scope
from k0.db.context_helper import set_space_context


class TestPrunedEntitiesRLSIsolation:
    """Integration tests for RLS on st_pruned_entities."""

    @pytest.mark.asyncio
    async def test_cross_space_pruned_access_blocked(self):
        """Verify RLS blocks access to other space's pruned entities."""
        async with connection_scope() as conn:
            # Insert pruned entity for space_a
            await set_space_context(conn, "space_a")
            await conn.execute("""
                INSERT INTO st_pruned_entities
                (prune_id, entity_id, entity_type, canonical_name, embedding,
                 space_id, layer_table, decay_factor_at_prune, lambda_at_prune,
                 pruned_at)
                VALUES ('p1', 'ent1', 'PERSON', 'John Doe',
                        $1::vector(1024), 'space_a', 'st_epi', 0.01, 0.1, 0)
                ON CONFLICT DO NOTHING
            """, [0.0] * 1024)

            # Switch to space_b - should not see space_a's pruned entities
            await set_space_context(conn, "space_b")
            rows = await conn.fetch(
                "SELECT * FROM st_pruned_entities WHERE prune_id = 'p1'"
            )
            assert len(rows) == 0  # Blocked by RLS

    @pytest.mark.asyncio
    async def test_regret_detection_respects_isolation(self):
        """Verify regret matching only finds same-space pruned entities."""
        # Regret detector should only match entities in same space
        pass  # Detailed test implementation
```

**Acceptance Criteria**:

- [ ] Migration 0049 creates st_pruned_entities with all columns
- [ ] All 4 indexes created (2 standard, 2 partial)
- [ ] Vector index uses ivfflat for pgvector
- [ ] RLS enabled with `pruned_entities_isolation` policy
- [ ] Cross-space access blocked by RLS
- [ ] Same-space access allowed
- [ ] Regret detection only matches same-space entities
- [ ] Migration tests pass
- [ ] Integration tests with real PostgreSQL pass
- [ ] ≥95% test coverage for migration

---

#### Issue 6.3.4 — RLS policy for st_decay_feedback

**Status**: 🔲 NOT STARTED

**Goal**: Create st_decay_feedback table migration with Row-Level Security for decay rate learning.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 6.22

**Note**: st_decay_feedback migration does NOT exist yet. This issue creates both the table and RLS policy.

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Dossier schema | `P03_consolidation_dossier_v2.md` Section 6.22.1 | Full table schema |
| Dossier RLS | `P03_consolidation_dossier_v2.md` Section 6.22.1 | RLS policy definition |
| Context helper | `k0/db/context_helper.py` | set_space_context() from Issue 6.3.1 |
| Migration pattern | `k0/db/alembic/versions/0040_st_learned_weights.py` | RLS migration pattern |

**Schema from Dossier §6.22.1**:

```sql
CREATE TABLE st_decay_feedback (
  -- Identity
  feedback_id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,              -- Entity this feedback is about
  layer TEXT NOT NULL,                  -- 'st_epi', 'st_sem', 'st_kg_dom', etc.

  -- Context
  space_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,

  -- Observed behavior
  event_type TEXT NOT NULL,             -- 'ACCESS', 'RESURRECTION', 'ARCHIVE', 'TOMBSTONE'
  inter_access_interval REAL,           -- Days since last access
  decay_factor_at_event REAL,           -- Decay factor when event occurred
  expected_decay REAL,                  -- What decay would have been with current λ

  -- Learning signals
  resurrection_needed BOOLEAN,          -- TRUE if resurrected from ARCHIVED/TOMBSTONE
  archival_premature BOOLEAN,           -- TRUE if accessed shortly after archival

  -- Timestamps
  created_at INTEGER NOT NULL,
  observed_at INTEGER NOT NULL          -- When the access/resurrection occurred
);
```

**Work To Do**:

1. [ ] Create migration `0050_st_decay_feedback.py`
2. [ ] Define all columns per dossier §6.22.1
3. [ ] Create index `idx_decay_fb_space_layer` (space_id, layer, observed_at)
4. [ ] Create index `idx_decay_fb_memory` (memory_id, observed_at)
5. [ ] Create index `idx_decay_fb_event_type` (event_type, observed_at)
6. [ ] Add CHECK constraint for event_type values
7. [ ] Enable RLS: `ALTER TABLE st_decay_feedback ENABLE ROW LEVEL SECURITY`
8. [ ] Create RLS policy `decay_feedback_isolation`
9. [ ] Add downgrade to drop policy, indexes, and table
10. [ ] Create migration tests
11. [ ] Add integration tests for RLS isolation

**Implementation Pattern**:

```python
# k0/db/alembic/versions/0050_st_decay_feedback.py
"""Create st_decay_feedback table for decay rate learning.

Revision ID: 0050
Revises: 0049
Create Date: 2026-01-04

Track access patterns and decay outcomes for Bayesian lambda estimation.
365-day rolling window for seasonal pattern detection.

Dossier Reference: Section 6.22 st_decay_feedback
Retention: 365 days
Isolation: RLS enforced for space-level security
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0050"
down_revision: str = "0049"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Valid event types from dossier §6.22.2
EVENT_TYPES = ("ACCESS", "RESURRECTION", "ARCHIVE", "TOMBSTONE")


def upgrade() -> None:
    """Create st_decay_feedback table with RLS."""
    op.create_table(
        "st_decay_feedback",
        # Identity
        sa.Column("feedback_id", sa.Text, primary_key=True),
        sa.Column("memory_id", sa.Text, nullable=False),
        sa.Column("layer", sa.Text, nullable=False),
        # Context
        sa.Column("space_id", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.Text, nullable=False),
        # Observed behavior
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("inter_access_interval", sa.Float, nullable=True),
        sa.Column("decay_factor_at_event", sa.Float, nullable=True),
        sa.Column("expected_decay", sa.Float, nullable=True),
        # Learning signals
        sa.Column("resurrection_needed", sa.Boolean, nullable=True),
        sa.Column("archival_premature", sa.Boolean, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.BigInteger, nullable=False),
        sa.Column("observed_at", sa.BigInteger, nullable=False),
        # CHECK constraints
        sa.CheckConstraint(
            f"event_type IN ({', '.join(repr(t) for t in EVENT_TYPES)})",
            name="ck_decay_fb_event_type",
        ),
    )

    # Indexes
    op.create_index(
        "idx_decay_fb_space_layer",
        "st_decay_feedback",
        ["space_id", "layer", "observed_at"],
    )
    op.create_index(
        "idx_decay_fb_memory",
        "st_decay_feedback",
        ["memory_id", "observed_at"],
    )
    op.create_index(
        "idx_decay_fb_event_type",
        "st_decay_feedback",
        ["event_type", "observed_at"],
    )

    # Enable RLS
    op.execute("ALTER TABLE st_decay_feedback ENABLE ROW LEVEL SECURITY")

    # Create isolation policy
    op.execute("""
        CREATE POLICY decay_feedback_isolation ON st_decay_feedback
            FOR ALL USING (space_id = current_setting('app.current_space_id', true))
    """)


def downgrade() -> None:
    """Drop st_decay_feedback table."""
    op.execute("DROP POLICY IF EXISTS decay_feedback_isolation ON st_decay_feedback")
    op.drop_index("idx_decay_fb_event_type", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_memory", table_name="st_decay_feedback")
    op.drop_index("idx_decay_fb_space_layer", table_name="st_decay_feedback")
    op.drop_table("st_decay_feedback")
```

**Acceptance Criteria**:

- [ ] Migration 0050 creates st_decay_feedback with all columns
- [ ] All 3 indexes created
- [ ] CHECK constraint enforces valid event_type values
- [ ] RLS enabled with `decay_feedback_isolation` policy
- [ ] Cross-space access blocked by RLS
- [ ] Same-space access allowed
- [ ] Migration tests pass
- [ ] Integration tests with real PostgreSQL pass
- [ ] ≥95% test coverage for migration

---

#### Issue 6.3.5 — Application context setup helper

**Status**: 🔲 NOT STARTED

**Goal**: Already implemented in Issue 6.3.1. This issue consolidates and extends the context helper.

**Note**: Context helper `k0/db/context_helper.py` created in Issue 6.3.1. This issue adds P03-specific integration.

**Dossier Reference**: Section 14.11 Learning Data Isolation

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Context helper | `k0/db/context_helper.py` | set_space_context(), set_full_context() |
| P03 context | `k0/pipelines/p03/context.py` | P03CycleContext |
| Connection scope | `k0/db/connection.py` | connection_scope(), transaction_scope() |

**Work To Do**:

1. [ ] Add P03-aware context helper function: `p03_isolation_scope(ctx: P03CycleContext)`
2. [ ] Create convenience wrapper: `isolated_transaction_scope(ctx)` combining transaction + RLS
3. [ ] Add to `k0/db/__init__.py` exports
4. [ ] Integrate with P03 stages that access RLS-protected tables
5. [ ] Add logging for context setup/teardown in structured log format
6. [ ] Create unit tests for P03 context helper integration
7. [ ] Create integration tests with real PostgreSQL

**Implementation Pattern**:

```python
# k0/db/context_helper.py — extend with P03 integration

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from k0.db.pool import get_pool

if TYPE_CHECKING:
    from asyncpg import Connection
    from asyncpg.transaction import Transaction
    from k0.pipelines.p03.context import P03CycleContext


@asynccontextmanager
async def p03_isolation_scope(
    ctx: P03CycleContext,
) -> AsyncIterator[tuple[Connection, Transaction]]:
    """
    P03-aware transaction scope with RLS context.

    Automatically sets space_id and tenant_id from P03CycleContext
    for Row-Level Security enforcement.

    Usage:
        async with p03_isolation_scope(envelope.context) as (conn, tx):
            # All queries filtered by space_id automatically
            rows = await conn.fetch("SELECT * FROM st_learned_weights")

    Args:
        ctx: P03CycleContext with space_id and tenant_id

    Yields:
        Tuple of (asyncpg.Connection, asyncpg.Transaction) with RLS context set
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction() as tx:
            # Set RLS context from P03CycleContext
            await conn.execute(
                "SET LOCAL app.current_space_id = $1",
                ctx.space_id,
            )
            await conn.execute(
                "SET LOCAL app.current_tenant_id = $1",
                ctx.tenant_id,
            )
            yield conn, tx


@asynccontextmanager
async def isolated_read_scope(
    ctx: P03CycleContext,
) -> AsyncIterator[Connection]:
    """
    P03-aware read-only scope with RLS context.

    Sets RLS context and read-only mode for safe queries.

    Args:
        ctx: P03CycleContext with space_id and tenant_id

    Yields:
        asyncpg.Connection with RLS context set in read-only mode
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute(
                "SET LOCAL app.current_space_id = $1",
                ctx.space_id,
            )
            await conn.execute(
                "SET LOCAL app.current_tenant_id = $1",
                ctx.tenant_id,
            )
            yield conn
```

**Test Pattern**:

```python
# tests/k0/db/test_context_helper_p03.py
"""P03 context helper integration tests."""

import pytest
from k0.db.context_helper import p03_isolation_scope, isolated_read_scope
from k0.pipelines.p03 import P03CycleContext


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create sample P03 context."""
    return P03CycleContext.create(
        tenant_id="tenant-001",
        space_id="family-abc",
        event_ids=["evt-001"],
    )


@pytest.fixture
def other_context() -> P03CycleContext:
    """Create different space context."""
    return P03CycleContext.create(
        tenant_id="tenant-001",
        space_id="family-xyz",
        event_ids=["evt-002"],
    )


class TestP03IsolationScope:
    """Tests for p03_isolation_scope."""

    @pytest.mark.integration
    async def test_sets_space_context(
        self,
        sample_context: P03CycleContext,
        pg_pool,  # Real PostgreSQL fixture
    ) -> None:
        """Verify space_id is set in connection."""
        async with p03_isolation_scope(sample_context) as (conn, tx):
            result = await conn.fetchval(
                "SELECT current_setting('app.current_space_id', true)"
            )
            assert result == sample_context.space_id

    @pytest.mark.integration
    async def test_rls_blocks_cross_space(
        self,
        sample_context: P03CycleContext,
        other_context: P03CycleContext,
        pg_pool,
    ) -> None:
        """Verify RLS prevents cross-space access."""
        # Insert with family-abc context
        async with p03_isolation_scope(sample_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_learned_weights
                (weight_id, layer, space_id, tenant_id, lambda_decay, updated_at)
                VALUES ('w1', 'st_epi', 'family-abc', 'tenant-001', 0.05, 1000)
            """)

        # Query with family-xyz context - should not see the row
        async with p03_isolation_scope(other_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE weight_id = 'w1'"
            )
            assert len(rows) == 0  # RLS blocks cross-space

    @pytest.mark.integration
    async def test_rls_allows_same_space(
        self,
        sample_context: P03CycleContext,
        pg_pool,
    ) -> None:
        """Verify same-space access allowed."""
        async with p03_isolation_scope(sample_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_learned_weights
                (weight_id, layer, space_id, tenant_id, lambda_decay, updated_at)
                VALUES ('w2', 'st_sem', 'family-abc', 'tenant-001', 0.04, 1000)
            """)

        # Same context can see the row
        async with p03_isolation_scope(sample_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE weight_id = 'w2'"
            )
            assert len(rows) == 1


class TestIsolatedReadScope:
    """Tests for isolated_read_scope."""

    @pytest.mark.integration
    async def test_read_only_rejects_writes(
        self,
        sample_context: P03CycleContext,
        pg_pool,
    ) -> None:
        """Verify read-only mode prevents mutations."""
        with pytest.raises(Exception):  # ReadOnlySqlTransactionError
            async with isolated_read_scope(sample_context) as conn:
                await conn.execute("INSERT INTO st_learned_weights ...")
```

**Acceptance Criteria**:

- [ ] `p03_isolation_scope(ctx)` sets space_id and tenant_id from P03CycleContext
- [ ] `isolated_read_scope(ctx)` provides read-only connection with RLS
- [ ] Both functions exported from `k0/db/__init__.py`
- [ ] RLS correctly blocks cross-space queries
- [ ] RLS correctly allows same-space queries
- [ ] Context cleared on scope exit (SET LOCAL is transaction-scoped)
- [ ] Integration tests pass with real PostgreSQL
- [ ] ≥95% test coverage

---

#### Issue 6.3.6 — Cross-space isolation integration tests

**Status**: 🔲 NOT STARTED

**Goal**: Comprehensive integration tests to verify RLS policies prevent cross-space data access across all 6 learning tables.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 8.1 Cross-Space Leakage Detection

**Tables to Test**:

- st_learned_weights
- st_consolidation_audit
- st_pruned_entities
- st_decay_feedback
- st_feedback_signals
- st_feedback_quarantine

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Context helper | `k0/db/context_helper.py` | p03_isolation_scope() from Issue 6.3.5 |
| P03 context | `k0/pipelines/p03/context.py` | P03CycleContext |
| Migration patterns | `k0/db/alembic/versions/0040_*.py` | RLS policy patterns |
| Test fixtures | `tests/conftest.py` | pg_pool fixture |

**Work To Do**:

1. [ ] Create test file `tests/k0/modules/consolidation/security/test_cross_space_isolation.py`
2. [ ] Implement `test_cross_space_isolation()` - Insert in space_a, query from space_b → empty
3. [ ] Implement `test_rls_enforcement()` - Verify RLS enabled on all 6 tables
4. [ ] Implement `test_same_space_access()` - Verify own-space data accessible
5. [ ] Implement `test_no_privilege_escalation()` - Verify superuser bypass is disabled
6. [ ] Implement `test_cross_tenant_isolation()` - Verify tenant-level isolation
7. [ ] Add pytest markers for integration tests
8. [ ] Configure CI to run with real PostgreSQL

**Implementation Pattern**:

```python
# tests/k0/modules/consolidation/security/test_cross_space_isolation.py
"""
Cross-space isolation integration tests for P03 learning tables.

These tests verify RLS policies correctly isolate data between spaces.
Requires real PostgreSQL with RLS enabled.

Dossier Reference: Section 8.1 Cross-Space Leakage Detection
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from k0.db.context_helper import p03_isolation_scope
from k0.pipelines.p03 import P03CycleContext

if TYPE_CHECKING:
    from asyncpg import Pool

# All learning tables that must have RLS
RLS_PROTECTED_TABLES = [
    "st_learned_weights",
    "st_consolidation_audit",
    "st_pruned_entities",
    "st_decay_feedback",
    "st_feedback_signals",
    "st_feedback_quarantine",
]


@pytest.fixture
def space_a_context() -> P03CycleContext:
    """Context for space A."""
    return P03CycleContext.create(
        tenant_id="tenant-001",
        space_id="family-alpha",
        event_ids=["evt-001"],
    )


@pytest.fixture
def space_b_context() -> P03CycleContext:
    """Context for space B (different space, same tenant)."""
    return P03CycleContext.create(
        tenant_id="tenant-001",
        space_id="family-beta",
        event_ids=["evt-002"],
    )


@pytest.fixture
def other_tenant_context() -> P03CycleContext:
    """Context for different tenant."""
    return P03CycleContext.create(
        tenant_id="tenant-002",
        space_id="family-gamma",
        event_ids=["evt-003"],
    )


class TestRLSEnforcement:
    """Verify RLS is enabled on all learning tables."""

    @pytest.mark.integration
    async def test_rls_enabled_on_all_tables(
        self,
        pg_pool: Pool,
    ) -> None:
        """All learning tables must have RLS enabled."""
        async with pg_pool.acquire() as conn:
            for table in RLS_PROTECTED_TABLES:
                result = await conn.fetchval(
                    """
                    SELECT relrowsecurity
                    FROM pg_class
                    WHERE relname = $1
                    """,
                    table,
                )
                assert result is True, f"RLS not enabled on {table}"

    @pytest.mark.integration
    async def test_rls_policy_exists_on_all_tables(
        self,
        pg_pool: Pool,
    ) -> None:
        """All learning tables must have isolation policy."""
        async with pg_pool.acquire() as conn:
            for table in RLS_PROTECTED_TABLES:
                policies = await conn.fetch(
                    """
                    SELECT polname, polcmd
                    FROM pg_policies
                    WHERE tablename = $1
                    """,
                    table,
                )
                assert len(policies) > 0, f"No RLS policy on {table}"
                policy_names = [p["polname"] for p in policies]
                # Verify isolation policy exists
                has_isolation = any("isolation" in name for name in policy_names)
                assert has_isolation, f"No isolation policy on {table}"


class TestCrossSpaceIsolation:
    """Verify cross-space data access is blocked."""

    @pytest.mark.integration
    async def test_cross_space_isolation_learned_weights(
        self,
        space_a_context: P03CycleContext,
        space_b_context: P03CycleContext,
        pg_pool: Pool,
    ) -> None:
        """Data from space_a invisible to space_b."""
        # Insert data in space_a
        async with p03_isolation_scope(space_a_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_learned_weights
                (weight_id, layer, space_id, tenant_id, lambda_decay, updated_at)
                VALUES ('cross-test-1', 'st_epi', 'family-alpha', 'tenant-001', 0.05, 1000)
            """)

        # Query from space_b - should see nothing
        async with p03_isolation_scope(space_b_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE weight_id = 'cross-test-1'"
            )
            assert len(rows) == 0, "Cross-space data leaked!"

    @pytest.mark.integration
    async def test_cross_space_isolation_audit(
        self,
        space_a_context: P03CycleContext,
        space_b_context: P03CycleContext,
        pg_pool: Pool,
    ) -> None:
        """Audit records from space_a invisible to space_b."""
        async with p03_isolation_scope(space_a_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_consolidation_audit
                (audit_id, cycle_id, space_id, tenant_id, action, entity_id, created_at)
                VALUES ('audit-x1', 'cycle-1', 'family-alpha', 'tenant-001', 'PRUNE', 'ent-1', 1000)
            """)

        async with p03_isolation_scope(space_b_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_consolidation_audit WHERE audit_id = 'audit-x1'"
            )
            assert len(rows) == 0, "Cross-space audit leaked!"

    @pytest.mark.integration
    async def test_cross_space_isolation_pruned_entities(
        self,
        space_a_context: P03CycleContext,
        space_b_context: P03CycleContext,
        pg_pool: Pool,
    ) -> None:
        """Pruned entities from space_a invisible to space_b."""
        async with p03_isolation_scope(space_a_context) as (conn, tx):
            # Simplified insert for test
            await conn.execute("""
                INSERT INTO st_pruned_entities
                (entity_id, layer, space_id, tenant_id, prune_reason, pruned_at, created_at)
                VALUES ('prune-x1', 'st_epi', 'family-alpha', 'tenant-001', 'DECAY', 1000, 1000)
            """)

        async with p03_isolation_scope(space_b_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_pruned_entities WHERE entity_id = 'prune-x1'"
            )
            assert len(rows) == 0, "Cross-space pruned entity leaked!"

    @pytest.mark.integration
    async def test_cross_space_isolation_decay_feedback(
        self,
        space_a_context: P03CycleContext,
        space_b_context: P03CycleContext,
        pg_pool: Pool,
    ) -> None:
        """Decay feedback from space_a invisible to space_b."""
        async with p03_isolation_scope(space_a_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_decay_feedback
                (feedback_id, memory_id, layer, space_id, tenant_id, event_type, created_at, observed_at)
                VALUES ('fb-x1', 'mem-1', 'st_epi', 'family-alpha', 'tenant-001', 'ACCESS', 1000, 1000)
            """)

        async with p03_isolation_scope(space_b_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_decay_feedback WHERE feedback_id = 'fb-x1'"
            )
            assert len(rows) == 0, "Cross-space decay feedback leaked!"


class TestSameSpaceAccess:
    """Verify same-space data is accessible."""

    @pytest.mark.integration
    async def test_same_space_can_read_own_data(
        self,
        space_a_context: P03CycleContext,
        pg_pool: Pool,
    ) -> None:
        """Data inserted in space_a visible to same space."""
        async with p03_isolation_scope(space_a_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_learned_weights
                (weight_id, layer, space_id, tenant_id, lambda_decay, updated_at)
                VALUES ('own-data-1', 'st_sem', 'family-alpha', 'tenant-001', 0.04, 1000)
            """)

        async with p03_isolation_scope(space_a_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE weight_id = 'own-data-1'"
            )
            assert len(rows) == 1
            assert rows[0]["space_id"] == "family-alpha"


class TestCrossTenantIsolation:
    """Verify cross-tenant isolation."""

    @pytest.mark.integration
    async def test_cross_tenant_blocked(
        self,
        space_a_context: P03CycleContext,
        other_tenant_context: P03CycleContext,
        pg_pool: Pool,
    ) -> None:
        """Data from tenant-001 invisible to tenant-002."""
        async with p03_isolation_scope(space_a_context) as (conn, tx):
            await conn.execute("""
                INSERT INTO st_learned_weights
                (weight_id, layer, space_id, tenant_id, lambda_decay, updated_at)
                VALUES ('tenant-test-1', 'st_kg', 'family-alpha', 'tenant-001', 0.03, 1000)
            """)

        # Different tenant should not see the data
        async with p03_isolation_scope(other_tenant_context) as (conn, tx):
            rows = await conn.fetch(
                "SELECT * FROM st_learned_weights WHERE weight_id = 'tenant-test-1'"
            )
            assert len(rows) == 0, "Cross-tenant data leaked!"
```

**Acceptance Criteria**:

- [ ] All 6 learning tables have RLS enabled (verified by test)
- [ ] All 6 learning tables have isolation policy (verified by test)
- [ ] Cross-space access returns empty result, not error
- [ ] Same-space access returns correct data
- [ ] Cross-tenant access returns empty result
- [ ] No exceptions or privilege escalation paths
- [ ] Tests run in CI with real PostgreSQL
- [ ] ≥95% test coverage for isolation scenarios

---

#### Issue 6.3.7 — RLS enforcement verification job

**Status**: 🔲 NOT STARTED

**Goal**: Implement automated verification that RLS is enabled and functioning on all P03 learning tables.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 8.1 `check_rls_policies()`

**Tables to Verify**:

- st_learned_weights
- st_consolidation_audit
- st_pruned_entities
- st_decay_feedback
- st_feedback_signals
- st_feedback_quarantine

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03 metrics | `k0/pipelines/p03/observability/metrics.py` | P03MetricsEmitter |
| Connection scope | `k0/db/connection.py` | connection_scope() |
| Policy layer | `k0/policy/acl_enforcer.py` | ACL patterns |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/rls_verifier.py`
2. [ ] Implement `verify_rls_enabled(conn) -> List[str]` — return tables missing RLS
3. [ ] Implement `verify_rls_policies(conn, table) -> List[PolicyInfo]` — return policy details
4. [ ] Implement `emit_rls_health_metric()` — set gauge 1 if healthy, 0 if violations
5. [ ] Add startup verification hook to P03 initialization
6. [ ] Create unit tests for verifier functions
7. [ ] Create integration tests with real PostgreSQL
8. [ ] Add alert emission on RLS policy gaps

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/rls_verifier.py
"""
RLS enforcement verification for P03 learning tables.

Runs on startup and periodically to verify all learning tables
have proper Row-Level Security policies enabled.

Dossier Reference: Section 8.1 `check_rls_policies()`
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from k0.observability.metrics import gauge

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)

# All tables that MUST have RLS enabled
RLS_REQUIRED_TABLES = [
    "st_learned_weights",
    "st_consolidation_audit",
    "st_pruned_entities",
    "st_decay_feedback",
    "st_feedback_signals",
    "st_feedback_quarantine",
]


@dataclass
class PolicyInfo:
    """RLS policy metadata."""
    name: str
    command: str  # SELECT, INSERT, UPDATE, DELETE, ALL
    using_expr: str | None
    with_check: str | None


@dataclass
class RLSHealthReport:
    """Result of RLS verification."""
    healthy: bool
    tables_missing_rls: List[str]
    tables_missing_policy: List[str]
    policy_details: dict[str, List[PolicyInfo]]

    def summary(self) -> str:
        """Human-readable summary."""
        if self.healthy:
            return f"RLS healthy: {len(RLS_REQUIRED_TABLES)} tables protected"
        issues = []
        if self.tables_missing_rls:
            issues.append(f"Missing RLS: {self.tables_missing_rls}")
        if self.tables_missing_policy:
            issues.append(f"Missing policy: {self.tables_missing_policy}")
        return f"RLS UNHEALTHY: {', '.join(issues)}"


async def verify_rls_enabled(conn: Connection) -> List[str]:
    """
    Check which tables have RLS enabled.

    Args:
        conn: Database connection

    Returns:
        List of table names that are MISSING RLS
    """
    missing = []
    for table in RLS_REQUIRED_TABLES:
        result = await conn.fetchval(
            """
            SELECT relrowsecurity
            FROM pg_class
            WHERE relname = $1
            """,
            table,
        )
        if result is not True:
            missing.append(table)
    return missing


async def verify_rls_policies(
    conn: Connection,
    table: str,
) -> List[PolicyInfo]:
    """
    Get RLS policy details for a table.

    Args:
        conn: Database connection
        table: Table name

    Returns:
        List of PolicyInfo with policy details
    """
    rows = await conn.fetch(
        """
        SELECT polname, polcmd, pg_get_expr(polqual, polrelid) AS qual,
               pg_get_expr(polwithcheck, polrelid) AS withcheck
        FROM pg_policy
        JOIN pg_class ON pg_policy.polrelid = pg_class.oid
        WHERE pg_class.relname = $1
        """,
        table,
    )
    return [
        PolicyInfo(
            name=r["polname"],
            command=r["polcmd"],
            using_expr=r["qual"],
            with_check=r["withcheck"],
        )
        for r in rows
    ]


async def check_rls_health(conn: Connection) -> RLSHealthReport:
    """
    Full RLS health check.

    Args:
        conn: Database connection

    Returns:
        RLSHealthReport with full status
    """
    missing_rls = await verify_rls_enabled(conn)
    missing_policy = []
    policy_details: dict[str, List[PolicyInfo]] = {}

    for table in RLS_REQUIRED_TABLES:
        policies = await verify_rls_policies(conn, table)
        policy_details[table] = policies
        if not policies:
            missing_policy.append(table)

    healthy = not missing_rls and not missing_policy

    return RLSHealthReport(
        healthy=healthy,
        tables_missing_rls=missing_rls,
        tables_missing_policy=missing_policy,
        policy_details=policy_details,
    )


async def emit_rls_health_metric(conn: Connection) -> None:
    """
    Emit RLS health gauge metric.

    Metric: p03_isolation_health (1 = healthy, 0 = violations)
    """
    report = await check_rls_health(conn)
    health_value = 1.0 if report.healthy else 0.0

    gauge(
        "p03_isolation_health",
        health_value,
        labels={"pipeline": "p03_consolidation"},
    )

    if not report.healthy:
        logger.critical(
            "RLS health check FAILED",
            extra={
                "missing_rls": report.tables_missing_rls,
                "missing_policy": report.tables_missing_policy,
            },
        )
    else:
        logger.info(
            "RLS health check passed",
            extra={"tables_protected": len(RLS_REQUIRED_TABLES)},
        )


async def verify_on_startup(conn: Connection) -> None:
    """
    Run RLS verification on P03 startup.

    Raises:
        RuntimeError: If RLS is not properly configured
    """
    report = await check_rls_health(conn)
    if not report.healthy:
        raise RuntimeError(
            f"P03 startup blocked: RLS not properly configured. "
            f"Missing RLS: {report.tables_missing_rls}, "
            f"Missing policy: {report.tables_missing_policy}"
        )
    logger.info("P03 RLS verification passed on startup")
```

**Acceptance Criteria**:

- [ ] `verify_rls_enabled()` returns list of tables missing RLS
- [ ] `verify_rls_policies()` returns policy details for a table
- [ ] `check_rls_health()` returns full health report
- [ ] `emit_rls_health_metric()` sets gauge to 1 (healthy) or 0 (violations)
- [ ] `verify_on_startup()` blocks P03 start if RLS misconfigured
- [ ] Critical log emitted on RLS violation detection
- [ ] Health metric reflects current state accurately
- [ ] Integration tests pass with real PostgreSQL
- [ ] ≥95% test coverage

---

#### Issue 6.3.8 — Query audit scanner for missing space_id

**Status**: 🔲 NOT STARTED

**Goal**: Implement scanner to detect P03 queries missing space_id filter (violation detection).

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 8.1 `CrossSpaceAuditor`

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| RLS verifier | `k0/pipelines/p03/security/rls_verifier.py` | RLS_REQUIRED_TABLES |
| P03 metrics | `k0/pipelines/p03/observability/metrics.py` | P03MetricsEmitter |
| Connection scope | `k0/db/connection.py` | connection_scope() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/query_auditor.py`
2. [ ] Implement `CrossSpaceAuditor` class
3. [ ] Implement `audit_queries(time_window_hours)` — scan pg_stat_statements
4. [ ] Implement `weekly_scan()` — combined audit + RLS check
5. [ ] Implement `emit_alert(alert_type, details)` — alert on violations
6. [ ] Add `p03_cross_space_query_attempts` Counter metric
7. [ ] Add `p03_rls_policy_blocks` Counter metric
8. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/query_auditor.py
"""
Query auditor for detecting cross-space violations.

Scans pg_stat_statements for queries to learning tables
that are missing space_id filters.

Dossier Reference: Section 8.1 `CrossSpaceAuditor` class
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List

from k0.observability.metrics import counter, gauge

from .rls_verifier import RLS_REQUIRED_TABLES, check_rls_health

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


@dataclass
class QueryViolation:
    """A query that may be violating space isolation."""
    query: str
    table: str
    calls: int
    detected_at: datetime
    reason: str  # 'missing_space_id' | 'suspicious_join'


@dataclass
class SecurityReport:
    """Result of security scan."""
    scan_time: datetime
    violations: List[QueryViolation]
    rls_healthy: bool
    tables_without_rls: List[str]

    @property
    def is_clean(self) -> bool:
        return len(self.violations) == 0 and self.rls_healthy


class CrossSpaceAuditor:
    """
    Audits queries for cross-space isolation violations.

    Uses pg_stat_statements to detect queries that access
    learning tables without proper space_id filtering.
    """

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    async def audit_queries(
        self,
        time_window_hours: int = 168,  # 1 week
    ) -> List[QueryViolation]:
        """
        Scan pg_stat_statements for potential violations.

        Args:
            time_window_hours: How far back to scan (default 7 days)

        Returns:
            List of QueryViolation for suspicious queries
        """
        violations = []

        # Query pg_stat_statements for queries touching our tables
        rows = await self.conn.fetch(
            """
            SELECT query, calls
            FROM pg_stat_statements
            WHERE query ~* $1
            ORDER BY calls DESC
            LIMIT 1000
            """,
            "|".join(RLS_REQUIRED_TABLES),
        )

        for row in rows:
            query = row["query"]
            # Check if query mentions a protected table without space_id
            for table in RLS_REQUIRED_TABLES:
                if table in query.lower():
                    if not self._has_space_filter(query):
                        violations.append(
                            QueryViolation(
                                query=query[:500],  # Truncate
                                table=table,
                                calls=row["calls"],
                                detected_at=datetime.utcnow(),
                                reason="missing_space_id",
                            )
                        )

        return violations

    def _has_space_filter(self, query: str) -> bool:
        """Check if query has space_id in WHERE clause."""
        query_lower = query.lower()
        # Look for space_id in WHERE clause
        patterns = [
            r"where.*space_id",
            r"and\s+space_id",
            r"space_id\s*=",
            r"current_setting\s*\(\s*'app\.current_space_id",
        ]
        return any(re.search(p, query_lower) for p in patterns)

    async def weekly_scan(self) -> SecurityReport:
        """
        Run full weekly security scan.

        Combines query audit with RLS health check.

        Returns:
            SecurityReport with all findings
        """
        # Audit queries
        violations = await self.audit_queries(time_window_hours=168)

        # Check RLS health
        rls_report = await check_rls_health(self.conn)

        # Emit metrics
        if violations:
            counter(
                "p03_cross_space_query_attempts",
                len(violations),
                labels={"pipeline": "p03_consolidation"},
            )

        gauge(
            "p03_isolation_health",
            1.0 if rls_report.healthy and not violations else 0.0,
            labels={"pipeline": "p03_consolidation"},
        )

        report = SecurityReport(
            scan_time=datetime.utcnow(),
            violations=violations,
            rls_healthy=rls_report.healthy,
            tables_without_rls=rls_report.tables_missing_rls,
        )

        if not report.is_clean:
            await self.emit_alert("security_violation", report)

        return report

    async def emit_alert(
        self,
        alert_type: str,
        report: SecurityReport,
    ) -> None:
        """
        Emit security alert for violations.

        Args:
            alert_type: Type of alert
            report: Security report with details
        """
        logger.critical(
            "P03 security scan found violations",
            extra={
                "alert_type": alert_type,
                "violation_count": len(report.violations),
                "tables_without_rls": report.tables_without_rls,
                "scan_time": report.scan_time.isoformat(),
            },
        )
        # In production, integrate with alerting system (PagerDuty, etc.)
```

**Acceptance Criteria**:

- [ ] `CrossSpaceAuditor` scans pg_stat_statements for violations
- [ ] Queries without space_id filter flagged as violations
- [ ] `weekly_scan()` combines query audit + RLS check
- [ ] `p03_cross_space_query_attempts` Counter emitted
- [ ] Critical log on violations
- [ ] SecurityReport captures all findings
- [ ] Integration tests with real PostgreSQL pass
- [ ] ≥95% test coverage

---

#### Issue 6.3.9 — Weekly automated security scan job

**Status**: 🔲 NOT STARTED

**Goal**: Schedule weekly security scan for cross-space violations using K0 scheduler.

**Dossier Reference**: Section 14 Security & Privacy, Section 8.1 Quarterly Manual Review Checklist

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Query auditor | `k0/pipelines/p03/security/query_auditor.py` | CrossSpaceAuditor |
| RLS verifier | `k0/pipelines/p03/security/rls_verifier.py` | check_rls_health() |
| Pipeline contracts | `k0/contracts/pipelines/*.yaml` | Contract pattern |
| Capability fabric | `k0/kernel/capability_fabric.py` | Capability registration |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/weekly_scan.py` — scan job implementation
2. [ ] Create `k0/contracts/pipelines/p03_security_scan.yaml` — pipeline contract
3. [ ] Register capability `consolidation.security.scan` in capability fabric
4. [ ] Add CLI commands `k0ctl security scan` and `k0ctl security status`
5. [ ] Add scheduler registration for weekly trigger
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/weekly_scan.py
"""
Weekly security scan job for P03.

Runs CrossSpaceAuditor.weekly_scan() on schedule.
Registered with K0 scheduler for automatic weekly execution.

Dossier Reference: Section 8.1 "Quarterly Manual Review Checklist"
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from k0.db.connection import connection_scope
from k0.kernel.capability_fabric import register_capability

from .query_auditor import CrossSpaceAuditor, SecurityReport

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def run_weekly_security_scan() -> SecurityReport:
    """
    Execute weekly security scan.

    Performs:
    - Query audit for missing space_id filters
    - RLS policy verification
    - Alert emission if violations found

    Returns:
        SecurityReport with scan results
    """
    logger.info("Starting weekly P03 security scan")

    async with connection_scope() as conn:
        auditor = CrossSpaceAuditor(conn)
        report = await auditor.weekly_scan()

    if report.is_clean:
        logger.info(
            "Weekly security scan completed: CLEAN",
            extra={"scan_time": report.scan_time.isoformat()},
        )
    else:
        logger.warning(
            "Weekly security scan completed: VIOLATIONS FOUND",
            extra={
                "scan_time": report.scan_time.isoformat(),
                "violation_count": len(report.violations),
            },
        )

    return report


@register_capability("consolidation.security.scan")
async def handle_security_scan_request(request: dict) -> dict:
    """
    Capability handler for security scan requests.

    Called by K0 CapabilityFabric when scan is requested.
    """
    report = await run_weekly_security_scan()
    return {
        "scan_time": report.scan_time.isoformat(),
        "is_clean": report.is_clean,
        "violation_count": len(report.violations),
        "tables_without_rls": report.tables_without_rls,
    }
```

```yaml
# k0/contracts/pipelines/p03_security_scan.yaml
---
pipeline_id: p03_security_scan
version: "1.0.0"
description: Weekly security scan for P03 consolidation
trigger:
  type: INTERVAL
  interval_seconds: 604800  # 7 days
  enabled: true
capability: consolidation.security.scan
owner: security
alert_on_failure: true
alert_channels:
  - security-oncall
  - p03-owners
```

**CLI Commands**:

```python
# k0/cli/commands/security.py
"""Security CLI commands."""

import asyncio
import click

from k0.pipelines.p03.security.weekly_scan import run_weekly_security_scan
from k0.pipelines.p03.security.rls_verifier import check_rls_health
from k0.db.connection import connection_scope


@click.group()
def security() -> None:
    """Security management commands."""
    pass


@security.command()
@click.option("--pipeline", default="p03_consolidation")
def scan(pipeline: str) -> None:
    """Run security scan manually."""
    async def _scan() -> None:
        report = await run_weekly_security_scan()
        click.echo(f"Scan completed: {'CLEAN' if report.is_clean else 'VIOLATIONS'}")
        if not report.is_clean:
            click.echo(f"  Violations: {len(report.violations)}")
            click.echo(f"  Tables without RLS: {report.tables_without_rls}")

    asyncio.run(_scan())


@security.command()
@click.option("--pipeline", default="p03_consolidation")
def status(pipeline: str) -> None:
    """Show isolation health status."""
    async def _status() -> None:
        async with connection_scope() as conn:
            report = await check_rls_health(conn)
            click.echo(f"Isolation health: {'HEALTHY' if report.healthy else 'UNHEALTHY'}")
            click.echo(report.summary())

    asyncio.run(_status())
```

**Acceptance Criteria**:

- [ ] Weekly scan runs automatically via K0 scheduler
- [ ] Scan performs query audit + RLS verification
- [ ] Report generated with all checklist items
- [ ] Violations trigger critical alerts
- [ ] `k0ctl security scan` works for manual trigger
- [ ] `k0ctl security status` shows isolation health
- [ ] Integration tests pass
- [ ] ≥95% test coverage

---

#### Issue 6.3.10 — PrivacyBandEnforcer implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement P03 privacy band enforcer for GREEN/AMBER/RED band constraints on cross-event linking.

**Dossier Reference**: Section 14.2 Privacy Band Enforcement, Section 14.2.1 K0 Privacy Bands in Consolidation

**Privacy Band Constraints (from Dossier)**:

| Band | Cross-Event | Cross-Actor | KG Entities | Location |
|------|-------------|-------------|-------------|----------|
| GREEN | Yes | Yes | Full | Full |
| AMBER | Yes | Same actor | Anonymized | City (~10km) |
| RED | Self only | No | No | Country |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Location privacy | `k0/policy/location_privacy.py` | get_geohash_precision_for_band(), mask_location_for_band() |
| Policy stamp | `k0/policy/policy_stamp.py` | PolicyStamp.band |
| PEP syscall | `k0/policy/pep_syscall.py` | _lookup_band_policy() |
| Redaction | `k0/policy/redaction.py` | apply_redactions() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/privacy_band.py`
2. [ ] Define `BAND_CONSTRAINTS` dict matching dossier specification
3. [ ] Implement `PrivacyBandEnforcer.can_link_events(event_a, event_b, stamp_a, stamp_b)`
4. [ ] Implement `PrivacyBandEnforcer.get_band_constraints(band)`
5. [ ] Implement `PrivacyBandEnforcer.filter_kg_entities(entities, band)`
6. [ ] Create unit tests for all band scenarios
7. [ ] Integration tests with P03 stages (R5 linking)

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/privacy_band.py
"""
Privacy band enforcement for P03 consolidation.

Enforces K0 privacy bands (GREEN/AMBER/RED) during consolidation
to restrict cross-event linking, actor linking, and KG ingestion.

Dossier Reference: Section 14.2 Privacy Band Enforcement
K0 References:
- k0/policy/pep_syscall.py: _lookup_band_policy()
- k0/policy/policy_stamp.py: PolicyStamp.band
- k0/policy/location_privacy.py: mask_location_for_band()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Literal

from k0.policy.location_privacy import get_geohash_precision_for_band

if TYPE_CHECKING:
    from k0.policy.policy_stamp import PolicyStamp


@dataclass
class BandConstraints:
    """Constraints for a privacy band."""
    cross_event_linking: bool
    cross_actor_linking: bool
    kg_ingestion: bool
    location_precision: Literal["full", "city", "country"]

    @property
    def geohash_precision(self) -> int:
        """Convert location_precision to geohash precision."""
        mapping = {
            "full": 12,    # ~0.6m
            "city": 6,     # ~5km
            "country": 4,  # ~39km
        }
        return mapping[self.location_precision]


class PrivacyBandEnforcer:
    """
    Enforce K0 privacy bands during P03 consolidation.

    Restricts operations based on event privacy bands:
    - GREEN: Full access, all linking allowed
    - AMBER: Same-actor linking only, location masked to city
    - RED: Self-reference only, no KG, country-level location
    """

    BAND_CONSTRAINTS = {
        "GREEN": BandConstraints(
            cross_event_linking=True,
            cross_actor_linking=True,
            kg_ingestion=True,
            location_precision="full",
        ),
        "AMBER": BandConstraints(
            cross_event_linking=True,
            cross_actor_linking=False,  # Same actor only
            kg_ingestion=True,  # Anonymized
            location_precision="city",
        ),
        "RED": BandConstraints(
            cross_event_linking=False,  # Self only
            cross_actor_linking=False,
            kg_ingestion=False,  # No KG entities
            location_precision="country",
        ),
    }

    @classmethod
    def get_band_constraints(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> BandConstraints:
        """
        Get constraints for a privacy band.

        Args:
            band: Privacy band

        Returns:
            BandConstraints for the band
        """
        if band not in cls.BAND_CONSTRAINTS:
            raise ValueError(f"Invalid privacy band: {band}")
        return cls.BAND_CONSTRAINTS[band]

    @classmethod
    def can_link_events(
        cls,
        event_a_id: str,
        event_b_id: str,
        event_a_actor: str,
        event_b_actor: str,
        event_a_space: str,
        event_b_space: str,
        stamp_a_band: Literal["GREEN", "AMBER", "RED"],
        stamp_b_band: Literal["GREEN", "AMBER", "RED"],
    ) -> bool:
        """
        Check if two events can be linked based on privacy bands.

        K0-integrated cross-event linking check per dossier §14.2.1.

        Args:
            event_a_id: First event ID
            event_b_id: Second event ID
            event_a_actor: First event actor ID
            event_b_actor: Second event actor ID
            event_a_space: First event space ID
            event_b_space: Second event space ID
            stamp_a_band: Privacy band of first event
            stamp_b_band: Privacy band of second event

        Returns:
            True if linking is allowed, False otherwise
        """
        # RED events cannot link to anything else
        if stamp_a_band == "RED" or stamp_b_band == "RED":
            return event_a_id == event_b_id  # Only self-reference

        # AMBER events link only within same actor
        if stamp_a_band == "AMBER" or stamp_b_band == "AMBER":
            return event_a_actor == event_b_actor

        # GREEN events can link freely within space
        return event_a_space == event_b_space

    @classmethod
    def filter_kg_entities(
        cls,
        entities: List[dict],
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> List[dict]:
        """
        Filter KG entities based on privacy band.

        Args:
            entities: List of KG entities to filter
            band: Privacy band

        Returns:
            Filtered entities (empty for RED band)
        """
        constraints = cls.get_band_constraints(band)

        if not constraints.kg_ingestion:
            return []  # RED band: no KG entities

        if band == "AMBER":
            # Anonymize entities (remove PII)
            return [
                cls._anonymize_entity(e) for e in entities
            ]

        return entities  # GREEN: full entities

    @classmethod
    def _anonymize_entity(cls, entity: dict) -> dict:
        """Anonymize entity for AMBER band."""
        # Remove PII fields
        pii_fields = ["email", "phone", "address", "full_name", "ssn"]
        return {
            k: v for k, v in entity.items()
            if k not in pii_fields
        }

    @classmethod
    def get_location_precision(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> int:
        """
        Get geohash precision for location masking.

        Args:
            band: Privacy band

        Returns:
            Geohash precision (4=country, 6=city, 12=full)
        """
        return get_geohash_precision_for_band(band)
```

**Test Pattern**:

```python
# tests/k0/pipelines/p03/security/test_privacy_band.py
"""Tests for PrivacyBandEnforcer."""

import pytest

from k0.pipelines.p03.security.privacy_band import (
    PrivacyBandEnforcer,
    BandConstraints,
)


class TestBandConstraints:
    """Tests for BAND_CONSTRAINTS."""

    def test_green_allows_all(self) -> None:
        """GREEN band allows all operations."""
        constraints = PrivacyBandEnforcer.get_band_constraints("GREEN")
        assert constraints.cross_event_linking is True
        assert constraints.cross_actor_linking is True
        assert constraints.kg_ingestion is True
        assert constraints.location_precision == "full"

    def test_amber_restricts_actor(self) -> None:
        """AMBER band restricts cross-actor linking."""
        constraints = PrivacyBandEnforcer.get_band_constraints("AMBER")
        assert constraints.cross_event_linking is True
        assert constraints.cross_actor_linking is False
        assert constraints.kg_ingestion is True
        assert constraints.location_precision == "city"

    def test_red_restricts_all(self) -> None:
        """RED band restricts all operations."""
        constraints = PrivacyBandEnforcer.get_band_constraints("RED")
        assert constraints.cross_event_linking is False
        assert constraints.cross_actor_linking is False
        assert constraints.kg_ingestion is False
        assert constraints.location_precision == "country"


class TestCanLinkEvents:
    """Tests for can_link_events()."""

    def test_red_self_only(self) -> None:
        """RED events can only self-reference."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="evt-1",
            event_b_id="evt-2",
            event_a_actor="actor-1",
            event_b_actor="actor-1",
            event_a_space="space-1",
            event_b_space="space-1",
            stamp_a_band="RED",
            stamp_b_band="GREEN",
        )
        assert result is False

    def test_red_allows_self(self) -> None:
        """RED events can self-reference."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="evt-1",
            event_b_id="evt-1",  # Same event
            event_a_actor="actor-1",
            event_b_actor="actor-1",
            event_a_space="space-1",
            event_b_space="space-1",
            stamp_a_band="RED",
            stamp_b_band="RED",
        )
        assert result is True

    def test_amber_same_actor(self) -> None:
        """AMBER events can link within same actor."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="evt-1",
            event_b_id="evt-2",
            event_a_actor="actor-1",
            event_b_actor="actor-1",  # Same actor
            event_a_space="space-1",
            event_b_space="space-1",
            stamp_a_band="AMBER",
            stamp_b_band="GREEN",
        )
        assert result is True

    def test_amber_blocks_cross_actor(self) -> None:
        """AMBER events cannot link across actors."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="evt-1",
            event_b_id="evt-2",
            event_a_actor="actor-1",
            event_b_actor="actor-2",  # Different actor
            event_a_space="space-1",
            event_b_space="space-1",
            stamp_a_band="AMBER",
            stamp_b_band="GREEN",
        )
        assert result is False

    def test_green_same_space(self) -> None:
        """GREEN events can link within same space."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="evt-1",
            event_b_id="evt-2",
            event_a_actor="actor-1",
            event_b_actor="actor-2",
            event_a_space="space-1",
            event_b_space="space-1",  # Same space
            stamp_a_band="GREEN",
            stamp_b_band="GREEN",
        )
        assert result is True


class TestFilterKgEntities:
    """Tests for filter_kg_entities()."""

    def test_red_returns_empty(self) -> None:
        """RED band returns no entities."""
        entities = [{"name": "Entity1"}, {"name": "Entity2"}]
        result = PrivacyBandEnforcer.filter_kg_entities(entities, "RED")
        assert result == []

    def test_green_returns_all(self) -> None:
        """GREEN band returns all entities."""
        entities = [{"name": "Entity1", "email": "test@example.com"}]
        result = PrivacyBandEnforcer.filter_kg_entities(entities, "GREEN")
        assert result == entities

    def test_amber_anonymizes(self) -> None:
        """AMBER band anonymizes entities."""
        entities = [{"name": "Entity1", "email": "test@example.com"}]
        result = PrivacyBandEnforcer.filter_kg_entities(entities, "AMBER")
        assert len(result) == 1
        assert "email" not in result[0]
        assert result[0]["name"] == "Entity1"
```

**Acceptance Criteria**:

- [ ] `BAND_CONSTRAINTS` defines GREEN/AMBER/RED per dossier
- [ ] `get_band_constraints()` returns correct constraints
- [ ] `can_link_events()` enforces band restrictions:
  - RED: self-reference only
  - AMBER: same-actor only
  - GREEN: same-space allowed
- [ ] `filter_kg_entities()` blocks RED, anonymizes AMBER
- [ ] `get_location_precision()` returns correct geohash precision
- [ ] All unit tests pass
- [ ] ≥95% test coverage

---

#### Issue 6.3.11 — Location privacy masking

**Status**: 🔲 NOT STARTED

**Goal**: Implement P03 location privacy masking wrapper using K0 `location_privacy.py` module.

**Dossier Reference**: Section 14.4 K0 Location Privacy Integration

**Location Precision by Band**:

| Band | Geohash Precision | Approx. Distance |
|------|-------------------|------------------|
| GREEN | 12 | ~0.6m (full) |
| AMBER | 6 | ~5km (city) |
| RED | 4 | ~39km (country) |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 location privacy | `k0/policy/location_privacy.py` | mask_location_for_band(), get_geohash_precision_for_band() |
| Privacy band enforcer | `k0/pipelines/p03/security/privacy_band.py` | PrivacyBandEnforcer |
| Geohash conversion | `k0/policy/location_privacy.py` | lat_lon_to_geohash() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/location_privacy.py` — P03-specific wrapper
2. [ ] Implement `P03LocationPrivacy.process_location_for_kg(event, policy_stamp)`
3. [ ] Implement `P03LocationPrivacy._precision_to_meters(precision)` mapping
4. [ ] Integrate with R5 linking stage for location masking
5. [ ] Create unit tests for all band scenarios
6. [ ] Integration tests with KG ingestion

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/location_privacy.py
"""
P03 location privacy wrapper.

Integrates with K0 location_privacy.py for band-based location masking
during consolidation.

Dossier Reference: Section 14.4 K0 Location Privacy Integration
K0 Reference: k0/policy/location_privacy.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional

from k0.policy.location_privacy import (
    get_geohash_precision_for_band,
    lat_lon_to_geohash,
    mask_location_for_band,
)

if TYPE_CHECKING:
    from k0.policy.policy_stamp import PolicyStamp


@dataclass
class MaskedLocation:
    """Result of location masking."""
    geohash: str
    precision_meters: int
    band: str


class P03LocationPrivacy:
    """
    P03-specific location privacy handler.

    Wraps K0 location_privacy.py for consolidation use cases.
    """

    # Geohash precision to meters mapping
    PRECISION_TO_METERS = {
        12: 1,        # Full precision (~0.6m)
        11: 2,        # ~2.4m
        10: 10,       # ~9.3m
        9: 40,        # ~37m
        8: 150,       # ~150m
        7: 610,       # ~610m
        6: 2400,      # ~2.4km (AMBER)
        5: 10000,     # ~10km
        4: 39000,     # ~39km (RED)
        3: 150000,    # ~150km
        2: 600000,    # ~600km
        1: 2500000,   # ~2500km
    }

    @classmethod
    def process_location_for_kg(
        cls,
        lat: float | None,
        lon: float | None,
        stamp_band: Literal["GREEN", "AMBER", "RED"],
    ) -> Optional[MaskedLocation]:
        """
        Process location for KG ingestion based on privacy band.

        Args:
            lat: Latitude (may be None)
            lon: Longitude (may be None)
            stamp_band: Privacy band from PolicyStamp

        Returns:
            MaskedLocation with geohash and precision, or None if no location
        """
        if lat is None or lon is None:
            return None

        # Use K0 masking function
        geohash, precision_meters = mask_location_for_band(lat, lon, stamp_band)

        if geohash is None:
            return None

        return MaskedLocation(
            geohash=geohash,
            precision_meters=precision_meters or 0,
            band=stamp_band,
        )

    @classmethod
    def _precision_to_meters(cls, precision: int) -> int:
        """
        Convert geohash precision to meters.

        Args:
            precision: Geohash precision (1-12)

        Returns:
            Approximate precision in meters
        """
        return cls.PRECISION_TO_METERS.get(precision, 39000)

    @classmethod
    def should_include_location_in_kg(
        cls,
        stamp_band: Literal["GREEN", "AMBER", "RED"],
    ) -> bool:
        """
        Check if location should be included in KG for this band.

        All bands include location, but at different precisions.
        RED band uses country-level precision (~39km).

        Args:
            stamp_band: Privacy band

        Returns:
            True (always include, just at different precision)
        """
        return True  # All bands include masked location
```

**Acceptance Criteria**:

- [ ] `process_location_for_kg()` returns geohash at correct precision
- [ ] GREEN band: full precision (~0.6m)
- [ ] AMBER band: city precision (~5km)
- [ ] RED band: country precision (~39km)
- [ ] None input returns None output
- [ ] Integration with K0 location_privacy.py verified
- [ ] ≥95% test coverage

---

#### Issue 6.3.12 — Tenant isolation query builder

**Status**: 🔲 NOT STARTED

**Goal**: Implement query builder that enforces tenant_id and space_id in all P03 queries.

**Dossier Reference**: Section 14.3 K0 ACL Enforcer Integration

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 ACL enforcer | `k0/policy/acl_enforcer.py` | verify_access(), check_permission() |
| Context helper | `k0/db/context_helper.py` | p03_isolation_scope() |
| P03 context | `k0/pipelines/p03/context.py` | P03CycleContext |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/query_builder.py`
2. [ ] Implement `P03TenantIsolation.verify_consolidation_access(tenant_id, space_id, actor_id)`
3. [ ] Implement `P03TenantIsolation.build_isolated_query(base_query, ctx)`
4. [ ] Implement `ConsolidationQueryBuilder` with mandatory isolation
5. [ ] Add static analysis hook for isolation verification
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/query_builder.py
"""
Tenant isolation query builder for P03.

Ensures all P03 queries include mandatory tenant_id and space_id filters.
Raises exception if isolation is not properly applied.

Dossier Reference: Section 14.3 K0 ACL Enforcer Integration
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.pipelines.p03.context import P03CycleContext

logger = logging.getLogger(__name__)


class IsolationViolationError(Exception):
    """Raised when query isolation is not properly applied."""
    pass


class P03TenantIsolation:
    """
    Enforces tenant isolation on all P03 queries.

    All queries MUST include tenant_id and space_id filters.
    """

    @classmethod
    def verify_consolidation_access(
        cls,
        tenant_id: str,
        space_id: str,
        actor_id: str | None = None,
    ) -> bool:
        """
        Verify access permission using K0 ACL Enforcer.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            actor_id: Optional actor for actor-specific checks

        Returns:
            True if access allowed

        Raises:
            IsolationViolationError: If access denied
        """
        # In production, delegate to K0 ACL Enforcer
        # from k0.policy.acl_enforcer import check_permission
        # return check_permission(tenant_id, space_id, "consolidation.read")

        # For now, verify IDs are not empty
        if not tenant_id or not space_id:
            raise IsolationViolationError(
                "tenant_id and space_id are required"
            )
        return True

    @classmethod
    def build_isolated_query(
        cls,
        base_query: str,
        ctx: P03CycleContext,
    ) -> tuple[str, dict[str, Any]]:
        """
        Add isolation filters to a query.

        Args:
            base_query: SQL query (must not have WHERE clause)
            ctx: P03 cycle context with tenant_id and space_id

        Returns:
            Tuple of (modified_query, parameters)

        Raises:
            IsolationViolationError: If query already has WHERE clause
        """
        if "where" in base_query.lower():
            raise IsolationViolationError(
                "Base query should not contain WHERE clause. "
                "Use build_isolated_query_with_conditions instead."
            )

        isolated_query = f"{base_query} WHERE tenant_id = $1 AND space_id = $2"
        params = {"$1": ctx.tenant_id, "$2": ctx.space_id}

        return isolated_query, params


class ConsolidationQueryBuilder:
    """
    Build isolated queries for P03 consolidation.

    All methods enforce tenant_id and space_id isolation.
    """

    def __init__(self, ctx: P03CycleContext) -> None:
        self.ctx = ctx
        self._verify_context()

    def _verify_context(self) -> None:
        """Verify context has required fields."""
        if not self.ctx.tenant_id or not self.ctx.space_id:
            raise IsolationViolationError(
                "P03CycleContext missing tenant_id or space_id"
            )

    def build_event_query(
        self,
        event_ids: list[str],
    ) -> tuple[str, list[Any]]:
        """
        Build isolated event query.

        Args:
            event_ids: Event IDs to query

        Returns:
            Tuple of (query, parameters)
        """
        query = """
            SELECT * FROM st_hipp_events
            WHERE tenant_id = $1 AND space_id = $2
            AND event_id = ANY($3)
        """
        return query, [self.ctx.tenant_id, self.ctx.space_id, event_ids]

    def build_truth_query(
        self,
        pattern_type: str,
    ) -> tuple[str, list[Any]]:
        """
        Build isolated truth table query.

        Args:
            pattern_type: Type of pattern to query

        Returns:
            Tuple of (query, parameters)
        """
        query = """
            SELECT * FROM st_truth
            WHERE tenant_id = $1 AND space_id = $2
            AND pattern_type = $3
        """
        return query, [self.ctx.tenant_id, self.ctx.space_id, pattern_type]
```

**Acceptance Criteria**:

- [ ] All queries include tenant_id and space_id filters
- [ ] `build_isolated_query()` appends WHERE clause
- [ ] `ConsolidationQueryBuilder` enforces isolation at construction
- [ ] Missing isolation raises `IsolationViolationError`
- [ ] Integration with P03CycleContext verified
- [ ] ≥95% test coverage

---

#### Issue 6.3.13 — P03AuditTrail implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement full audit trail for P03 reconciliation decisions using K0 ObservabilityEmitter.

**Dossier Reference**: Section 14.5 Audit Trail (K0 Observability)

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 ObservabilityEmitter | `k0/observability/emitter.py` | ObservabilityEmitter |
| Existing audit logger | `k0/pipelines/p03/audit_logger.py` | P03DecisionAuditLogger |
| Obligation store | `k0/observability/obligations.py` | ObligationStore |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/audit_trail.py`
2. [ ] Implement `P03AuditTrail.log_reconciliation_decision()`
3. [ ] Implement `P03AuditTrail.log_erasure_completed()`
4. [ ] Implement `P03AuditTrail.log_security_event()`
5. [ ] Integrate with K0 ObservabilityEmitter
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/audit_trail.py
"""
Audit trail for P03 consolidation via K0 Observability.

Logs all reconciliation decisions, erasure events, and security events
through K0 ObservabilityEmitter for compliance and debugging.

Dossier Reference: Section 14.5 Audit Trail (K0 Observability)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.observability.emitter import ObservabilityEmitter


logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """Audit event structure."""
    event_type: str
    timestamp_ms: int
    cycle_id: str | None
    tenant_id: str
    space_id: str
    details: dict[str, Any] = field(default_factory=dict)


class P03AuditTrail:
    """
    Audit trail for P03 consolidation.

    Emits audit events through K0 ObservabilityEmitter.
    """

    def __init__(
        self,
        emitter: ObservabilityEmitter | None = None,
    ) -> None:
        self.emitter = emitter

    def log_reconciliation_decision(
        self,
        *,
        cycle_id: str,
        phase: str,
        tenant_id: str,
        space_id: str,
        decision_type: str,
        source_event_id: str,
        target_truth_id: str | None,
        similarity_score: float,
        confidence_before: float,
        confidence_after: float,
    ) -> None:
        """
        Log a reconciliation decision.

        Emits `p03.reconciliation.decision` event.
        """
        event = AuditEvent(
            event_type="p03.reconciliation.decision",
            timestamp_ms=int(time.time() * 1000),
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            space_id=space_id,
            details={
                "phase": phase,
                "decision_type": decision_type,
                "source_event_id": source_event_id,
                "target_truth_id": target_truth_id,
                "similarity_score": similarity_score,
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
            },
        )
        self._emit(event)

    def log_erasure_completed(
        self,
        *,
        erasure_id: str,
        tenant_id: str,
        actor_id: str,
        scope: str,
        affected_counts: dict[str, int],
    ) -> None:
        """
        Log GDPR erasure completion.

        Emits `p03.erasure.completed` event.
        """
        event = AuditEvent(
            event_type="p03.erasure.completed",
            timestamp_ms=int(time.time() * 1000),
            cycle_id=None,
            tenant_id=tenant_id,
            space_id="",  # Erasure affects all spaces for actor
            details={
                "erasure_id": erasure_id,
                "actor_id": actor_id,
                "scope": scope,
                "affected_counts": affected_counts,
            },
        )
        self._emit(event)

    def log_security_event(
        self,
        *,
        event_type: str,
        tenant_id: str,
        space_id: str,
        details: dict[str, Any],
    ) -> None:
        """
        Log generic security event.

        Args:
            event_type: Security event type
            tenant_id: Tenant identifier
            space_id: Space identifier
            details: Event details
        """
        event = AuditEvent(
            event_type=f"p03.security.{event_type}",
            timestamp_ms=int(time.time() * 1000),
            cycle_id=None,
            tenant_id=tenant_id,
            space_id=space_id,
            details=details,
        )
        self._emit(event)

    def _emit(self, event: AuditEvent) -> None:
        """Emit event through K0 ObservabilityEmitter."""
        logger.info(
            "Audit event",
            extra={
                "event_type": event.event_type,
                "cycle_id": event.cycle_id,
                "tenant_id": event.tenant_id,
                "details": event.details,
            },
        )
        if self.emitter:
            self.emitter.emit(
                event_type=event.event_type,
                payload=event.details,
                tenant_id=event.tenant_id,
                space_id=event.space_id,
            )
```

**Acceptance Criteria**:

- [ ] `log_reconciliation_decision()` emits `p03.reconciliation.decision`
- [ ] `log_erasure_completed()` emits `p03.erasure.completed`
- [ ] `log_security_event()` emits generic security events
- [ ] All events include timestamp, tenant_id, space_id
- [ ] Integration with K0 ObservabilityEmitter verified
- [ ] Events queryable by trace_id and cycle_id
- [ ] ≥95% test coverage

---

#### Issue 6.3.14 — GDPR erasure handler

**Status**: 🔲 NOT STARTED

**Goal**: Implement GDPR Article 17 erasure request handling with cascade deletion.

**Dossier Reference**: Section 14.7 Data Minimization & GDPR

**Erasure Scope Options**:

- `ACTOR_DATA`: Erase all data for an actor
- `ALL_MENTIONS`: Erase all mentions of an actor
- `FULL_PURGE`: Complete data removal including backups

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03 audit trail | `k0/pipelines/p03/security/audit_trail.py` | P03AuditTrail |
| Connection scope | `k0/db/connection.py` | transaction_scope() |
| K0 WAL | `k0/db/wal.py` | WriteAheadLog.append() |
| K0 BusDispatcher | `k0/kernel/bus_dispatcher.py` | emit_event() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/erasure_handler.py`
2. [ ] Implement `P03ErasureHandler.handle_erasure_request()`
3. [ ] Implement cascade deletion for all memory layers
4. [ ] Implement FAISS index rebuild request via BusDispatcher
5. [ ] Integrate with K0 WAL for compliance logging
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/erasure_handler.py
"""
GDPR erasure handler for P03.

Implements GDPR Article 17 "Right to Erasure" with cascade deletion
across all P03 memory layers.

Dossier Reference: Section 14.7 Data Minimization & GDPR
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)

ErasureScope = Literal["ACTOR_DATA", "ALL_MENTIONS", "FULL_PURGE"]


@dataclass
class ErasureResult:
    """Result of erasure operation."""
    erasure_id: str
    status: Literal["COMPLETED", "PARTIAL", "FAILED"]
    affected_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    completed_at: datetime | None = None


class P03ErasureHandler:
    """
    Handle GDPR erasure requests for P03.

    Cascade deletion order:
    1. Mark st_hipp_events as TOMBSTONE
    2. Cascade to truth tables (st_epi, st_sem, st_kg_dom)
    3. Remove from st_vec (embeddings)
    4. Request FAISS index rebuild from P08
    5. Update st_kg_dom and st_kg_edges
    6. Log in audit trail
    7. Record in WAL for compliance
    """

    # Tables to erase in order
    ERASURE_ORDER = [
        "st_hipp_events",
        "st_epi",
        "st_sem",
        "st_kg_dom",
        "st_kg_edges",
        "st_vec",
        "st_learned_weights",
        "st_consolidation_audit",
    ]

    async def handle_erasure_request(
        self,
        conn: Connection,
        tenant_id: str,
        actor_id: str,
        scope: ErasureScope,
    ) -> ErasureResult:
        """
        Handle GDPR erasure request.

        Args:
            conn: Database connection
            tenant_id: Tenant identifier
            actor_id: Actor to erase
            scope: Erasure scope

        Returns:
            ErasureResult with affected counts
        """
        erasure_id = f"erasure-{uuid4().hex[:12]}"
        affected_counts: dict[str, int] = {}
        errors: list[str] = []

        logger.info(
            "Starting GDPR erasure",
            extra={
                "erasure_id": erasure_id,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "scope": scope,
            },
        )

        try:
            # Step 1: Mark events as TOMBSTONE
            count = await self._tombstone_events(conn, tenant_id, actor_id)
            affected_counts["st_hipp_events"] = count

            # Step 2: Cascade to truth tables
            for table in ["st_epi", "st_sem", "st_kg_dom"]:
                count = await self._cascade_erasure(
                    conn, table, tenant_id, actor_id, scope
                )
                affected_counts[table] = count

            # Step 3: Remove embeddings
            count = await self._erase_embeddings(conn, tenant_id, actor_id)
            affected_counts["st_vec"] = count

            # Step 4: Request FAISS rebuild (async)
            await self._request_faiss_rebuild(tenant_id)

            # Step 5: Update KG edges
            count = await self._erase_kg_edges(conn, tenant_id, actor_id)
            affected_counts["st_kg_edges"] = count

            return ErasureResult(
                erasure_id=erasure_id,
                status="COMPLETED",
                affected_counts=affected_counts,
                completed_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.exception("Erasure failed", extra={"erasure_id": erasure_id})
            errors.append(str(e))
            return ErasureResult(
                erasure_id=erasure_id,
                status="FAILED",
                affected_counts=affected_counts,
                errors=errors,
            )

    async def _tombstone_events(
        self,
        conn: Connection,
        tenant_id: str,
        actor_id: str,
    ) -> int:
        """Mark events as TOMBSTONE."""
        result = await conn.execute("""
            UPDATE st_hipp_events
            SET archival_status = 'TOMBSTONE',
                tombstone_at = $3
            WHERE tenant_id = $1 AND actor_id = $2
        """, tenant_id, actor_id, int(datetime.utcnow().timestamp() * 1000))
        return int(result.split()[-1])

    async def _cascade_erasure(
        self,
        conn: Connection,
        table: str,
        tenant_id: str,
        actor_id: str,
        scope: ErasureScope,
    ) -> int:
        """Cascade erasure to a table."""
        if scope == "FULL_PURGE":
            result = await conn.execute(f"""
                DELETE FROM {table}
                WHERE tenant_id = $1 AND actor_id = $2
            """, tenant_id, actor_id)
        else:
            result = await conn.execute(f"""
                UPDATE {table}
                SET archival_status = 'TOMBSTONE'
                WHERE tenant_id = $1 AND actor_id = $2
            """, tenant_id, actor_id)
        return int(result.split()[-1])

    async def _erase_embeddings(
        self,
        conn: Connection,
        tenant_id: str,
        actor_id: str,
    ) -> int:
        """Remove embeddings from st_vec."""
        result = await conn.execute("""
            DELETE FROM st_vec
            WHERE tenant_id = $1 AND source_actor_id = $2
        """, tenant_id, actor_id)
        return int(result.split()[-1])

    async def _request_faiss_rebuild(self, tenant_id: str) -> None:
        """Request FAISS index rebuild from P08."""
        # In production: emit via K0 BusDispatcher
        logger.info("Requesting FAISS rebuild", extra={"tenant_id": tenant_id})

    async def _erase_kg_edges(
        self,
        conn: Connection,
        tenant_id: str,
        actor_id: str,
    ) -> int:
        """Erase KG edges involving actor."""
        result = await conn.execute("""
            DELETE FROM st_kg_edges
            WHERE tenant_id = $1
            AND (source_actor = $2 OR target_actor = $2)
        """, tenant_id, actor_id)
        return int(result.split()[-1])
```

**Acceptance Criteria**:

- [ ] Erasure cascades through all memory layers
- [ ] TOMBSTONE status applied for soft deletes
- [ ] FULL_PURGE performs hard delete
- [ ] FAISS index rebuild requested via BusDispatcher
- [ ] Full audit trail in WAL
- [ ] ErasureResult includes affected counts
- [ ] Erasure completes within SLA
- [ ] ≥95% test coverage

---

#### Issue 6.3.15 — Tombstone lifecycle management

**Status**: 🔲 NOT STARTED

**Goal**: Implement soft delete with tombstone markers and lifecycle management.

**Dossier Reference**: Section 14.7 Data Minimization & GDPR

**Tombstone Lifecycle**:

1. Entity marked TOMBSTONE with timestamp
2. Tombstoned entities excluded from queries
3. After retention period (90 days), hard delete eligible
4. Hard delete job runs weekly

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Erasure handler | `k0/pipelines/p03/security/erasure_handler.py` | _tombstone_events() |
| K0 retention enforcer | `k0/policy/retention_enforcer.py` | RetentionEnforcer |
| Connection scope | `k0/db/connection.py` | transaction_scope() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/tombstone.py`
2. [ ] Implement `TombstoneManager.mark_tombstone()`
3. [ ] Implement `TombstoneManager.get_tombstoned_entities()`
4. [ ] Implement `TombstoneManager.hard_delete_tombstones()`
5. [ ] Add scheduled job for weekly hard delete
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/tombstone.py
"""
Tombstone lifecycle management for P03.

Implements soft delete with tombstone markers and scheduled hard deletion.

Dossier Reference: Section 14.7 Data Minimization & GDPR
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


@dataclass
class TombstonedEntity:
    """A tombstoned entity."""
    entity_id: str
    table: str
    tenant_id: str
    space_id: str
    tombstoned_at: datetime
    reason: str


class TombstoneManager:
    """
    Manage tombstone lifecycle for P03 entities.

    Lifecycle:
    1. mark_tombstone() - Mark entity as TOMBSTONE
    2. get_tombstoned_entities() - Query tombstoned entities
    3. hard_delete_tombstones() - Hard delete after retention period
    """

    DEFAULT_RETENTION_DAYS = 90

    async def mark_tombstone(
        self,
        conn: Connection,
        entity_id: str,
        table: str,
        reason: str,
    ) -> None:
        """
        Mark an entity as TOMBSTONE.

        Args:
            conn: Database connection
            entity_id: Entity to tombstone
            table: Table name
            reason: Reason for tombstoning
        """
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        await conn.execute(f"""
            UPDATE {table}
            SET archival_status = 'TOMBSTONE',
                tombstone_at = $1,
                tombstone_reason = $2
            WHERE entity_id = $3
        """, now_ms, reason, entity_id)

        logger.info(
            "Entity tombstoned",
            extra={
                "entity_id": entity_id,
                "table": table,
                "reason": reason,
            },
        )

    async def get_tombstoned_entities(
        self,
        conn: Connection,
        table: str,
        older_than_days: int = DEFAULT_RETENTION_DAYS,
    ) -> List[TombstonedEntity]:
        """
        Get tombstoned entities older than threshold.

        Args:
            conn: Database connection
            table: Table name
            older_than_days: Age threshold

        Returns:
            List of TombstonedEntity
        """
        threshold = datetime.utcnow() - timedelta(days=older_than_days)
        threshold_ms = int(threshold.timestamp() * 1000)

        rows = await conn.fetch(f"""
            SELECT entity_id, tenant_id, space_id, tombstone_at, tombstone_reason
            FROM {table}
            WHERE archival_status = 'TOMBSTONE'
            AND tombstone_at < $1
        """, threshold_ms)

        return [
            TombstonedEntity(
                entity_id=r["entity_id"],
                table=table,
                tenant_id=r["tenant_id"],
                space_id=r["space_id"],
                tombstoned_at=datetime.fromtimestamp(r["tombstone_at"] / 1000),
                reason=r["tombstone_reason"] or "",
            )
            for r in rows
        ]

    async def hard_delete_tombstones(
        self,
        conn: Connection,
        table: str,
        older_than_days: int = DEFAULT_RETENTION_DAYS,
    ) -> int:
        """
        Hard delete tombstoned entities past retention.

        Args:
            conn: Database connection
            table: Table name
            older_than_days: Age threshold

        Returns:
            Number of deleted entities
        """
        threshold = datetime.utcnow() - timedelta(days=older_than_days)
        threshold_ms = int(threshold.timestamp() * 1000)

        result = await conn.execute(f"""
            DELETE FROM {table}
            WHERE archival_status = 'TOMBSTONE'
            AND tombstone_at < $1
        """, threshold_ms)

        count = int(result.split()[-1])
        logger.info(
            "Hard deleted tombstones",
            extra={"table": table, "count": count},
        )
        return count
```

**Acceptance Criteria**:

- [ ] `mark_tombstone()` sets status and timestamp
- [ ] `get_tombstoned_entities()` queries by age threshold
- [ ] `hard_delete_tombstones()` removes old tombstones
- [ ] Default retention is 90 days
- [ ] `p03.entity.tombstoned.v1` event emitted
- [ ] Weekly hard delete job runs automatically
- [ ] ≥95% test coverage

---

#### Issue 6.3.16 — Retention policy enforcement

**Status**: 🔲 NOT STARTED

**Goal**: Implement band-based retention policy enforcement using K0 RetentionEnforcer.

**Dossier Reference**: Section 14.6 K0 Retention Enforcer Integration

**Retention by Band**:

| Band | Default Retention | Override Allowed |
|------|-------------------|------------------|
| GREEN | 365 days | Yes |
| AMBER | 90 days | Yes (shorter only) |
| RED | 30 days | No |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 retention enforcer | `k0/policy/retention_enforcer.py` | RetentionEnforcer |
| Tombstone manager | `k0/pipelines/p03/security/tombstone.py` | TombstoneManager |
| Privacy band enforcer | `k0/pipelines/p03/security/privacy_band.py` | BAND_CONSTRAINTS |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/retention.py`
2. [ ] Implement `P03RetentionEnforcer.get_retention_for_band()`
3. [ ] Implement `P03RetentionEnforcer.apply_retention_policy()`
4. [ ] Implement `P03RetentionEnforcer.run_retention_cleanup()`
5. [ ] Add scheduled job for daily retention enforcement
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/retention.py
"""
Retention policy enforcement for P03.

Enforces band-based retention policies via K0 RetentionEnforcer.

Dossier Reference: Section 14.6 K0 Retention Enforcer Integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from .tombstone import TombstoneManager

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


@dataclass
class RetentionPolicy:
    """Retention policy for a band."""
    band: str
    retention_days: int
    override_allowed: bool
    min_retention_days: int | None = None


class P03RetentionEnforcer:
    """
    Enforce band-based retention policies.

    Integrates with K0 RetentionEnforcer for policy lookup.
    """

    BAND_RETENTION = {
        "GREEN": RetentionPolicy(
            band="GREEN",
            retention_days=365,
            override_allowed=True,
            min_retention_days=30,
        ),
        "AMBER": RetentionPolicy(
            band="AMBER",
            retention_days=90,
            override_allowed=True,
            min_retention_days=30,  # Can only shorten
        ),
        "RED": RetentionPolicy(
            band="RED",
            retention_days=30,
            override_allowed=False,  # Fixed, no override
        ),
    }

    # Tables to enforce retention on
    RETENTION_TABLES = [
        "st_hipp_events",
        "st_epi",
        "st_sem",
        "st_kg_dom",
        "st_decay_feedback",
        "st_consolidation_audit",
    ]

    @classmethod
    def get_retention_for_band(
        cls,
        band: Literal["GREEN", "AMBER", "RED"],
    ) -> RetentionPolicy:
        """
        Get retention policy for a band.

        Args:
            band: Privacy band

        Returns:
            RetentionPolicy for the band
        """
        if band not in cls.BAND_RETENTION:
            raise ValueError(f"Invalid band: {band}")
        return cls.BAND_RETENTION[band]

    async def apply_retention_policy(
        self,
        conn: Connection,
        table: str,
    ) -> int:
        """
        Apply retention policy to a table.

        Marks entities past retention as TOMBSTONE.

        Args:
            conn: Database connection
            table: Table name

        Returns:
            Number of entities marked for retention
        """
        total_marked = 0
        tombstone_mgr = TombstoneManager()

        for band, policy in self.BAND_RETENTION.items():
            threshold = datetime.utcnow() - timedelta(days=policy.retention_days)
            threshold_ms = int(threshold.timestamp() * 1000)

            result = await conn.execute(f"""
                UPDATE {table}
                SET archival_status = 'TOMBSTONE',
                    tombstone_at = $1,
                    tombstone_reason = 'RETENTION_EXPIRED'
                WHERE privacy_band = $2
                AND archival_status = 'ACTIVE'
                AND created_at < $3
            """, int(datetime.utcnow().timestamp() * 1000), band, threshold_ms)

            count = int(result.split()[-1])
            total_marked += count

            if count > 0:
                logger.info(
                    "Retention policy applied",
                    extra={
                        "table": table,
                        "band": band,
                        "count": count,
                    },
                )

        return total_marked

    async def run_retention_cleanup(
        self,
        conn: Connection,
    ) -> dict[str, int]:
        """
        Run retention cleanup across all tables.

        Returns:
            Dict of table -> count marked for retention
        """
        results: dict[str, int] = {}
        for table in self.RETENTION_TABLES:
            count = await self.apply_retention_policy(conn, table)
            results[table] = count
        return results
```

**Acceptance Criteria**:

- [ ] GREEN: 365 days retention (override allowed)
- [ ] AMBER: 90 days retention (shorter override only)
- [ ] RED: 30 days retention (no override)
- [ ] `apply_retention_policy()` marks expired entities as TOMBSTONE
- [ ] `run_retention_cleanup()` processes all tables
- [ ] Daily retention job runs automatically
- [ ] Integration with K0 RetentionEnforcer verified
- [ ] ≥95% test coverage

---

#### Issue 6.3.17 — Content fingerprinting for dedup

**Status**: 🔲 NOT STARTED

**Goal**: Implement secure content fingerprinting using K0 crypto for deduplication and integrity checking.

**Dossier Reference**: Section 14.8 Encryption (K0 Crypto Layer)

**Sensitive Columns by Table**:

| Table | Sensitive Columns |
|-------|-------------------|
| st_hipp_events | body_text, attachments_json, location_name |
| st_epi | episode_summary |
| st_sem | pattern_description, pattern_attributes_json |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 crypto | `k0/security/crypto.py` | hash_payload(), compute_envelope_sha256() |
| K0 canonical JSON | `k0/security/crypto.py` | canonical_json() |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/security/fingerprint.py`
2. [ ] Define `SENSITIVE_COLUMNS` mapping per dossier
3. [ ] Implement `hash_sensitive_content(content)` using K0 crypto
4. [ ] Implement `compute_content_fingerprint(event)` for dedup
5. [ ] Implement `is_sensitive_column(table, column)` check
6. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/security/fingerprint.py
"""
Content fingerprinting for P03 deduplication.

Uses K0 crypto layer for deterministic, secure hashing
of content for deduplication and integrity checking.

Dossier Reference: Section 14.8 Encryption (K0 Crypto Layer)
K0 Reference: k0/security/crypto.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from k0.security.crypto import (
    canonical_json,
    compute_envelope_sha256,
    hash_payload,
)

if TYPE_CHECKING:
    pass


# Sensitive columns per table (from dossier §14.8)
SENSITIVE_COLUMNS: dict[str, set[str]] = {
    "st_hipp_events": {"body_text", "attachments_json", "location_name"},
    "st_epi": {"episode_summary"},
    "st_sem": {"pattern_description", "pattern_attributes_json"},
    "st_kg_dom": {"entity_attributes_json"},
    "st_kg_edges": {"edge_attributes_json"},
}


def is_sensitive_column(table: str, column: str) -> bool:
    """
    Check if a column contains sensitive data.

    Args:
        table: Table name
        column: Column name

    Returns:
        True if column is marked sensitive
    """
    return column in SENSITIVE_COLUMNS.get(table, set())


def hash_sensitive_content(content: str | bytes) -> str:
    """
    Hash sensitive content using K0 crypto.

    Uses SHA-256 via K0 hash_payload() for consistent hashing.

    Args:
        content: Content to hash (string or bytes)

    Returns:
        Hexadecimal SHA-256 hash (64 characters)
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hash_payload(content) or ""


def compute_content_fingerprint(event: dict[str, Any]) -> str:
    """
    Compute content fingerprint for event deduplication.

    Uses K0 compute_envelope_sha256() for full envelope hashing.

    Args:
        event: Event dict to fingerprint

    Returns:
        Hexadecimal SHA-256 fingerprint (64 characters)
    """
    return compute_envelope_sha256(event)


def compute_semantic_fingerprint(
    text: str,
    normalize: bool = True,
) -> str:
    """
    Compute semantic fingerprint for text deduplication.

    Normalizes text before hashing for fuzzy matching.

    Args:
        text: Text to fingerprint
        normalize: Whether to normalize (lowercase, strip)

    Returns:
        Hexadecimal SHA-256 fingerprint
    """
    if normalize:
        text = text.lower().strip()
    return hash_sensitive_content(text)


def redact_sensitive_fields(
    record: dict[str, Any],
    table: str,
) -> dict[str, Any]:
    """
    Redact sensitive fields in a record for logging.

    Args:
        record: Database record
        table: Table name

    Returns:
        Copy with sensitive fields replaced by [REDACTED]
    """
    sensitive = SENSITIVE_COLUMNS.get(table, set())
    result = dict(record)
    for col in sensitive:
        if col in result:
            result[col] = "[REDACTED]"
    return result
```

**Acceptance Criteria**:

- [ ] `SENSITIVE_COLUMNS` defines all sensitive columns per dossier
- [ ] `hash_sensitive_content()` uses K0 hash_payload()
- [ ] `compute_content_fingerprint()` uses K0 compute_envelope_sha256()
- [ ] Fingerprints are deterministic (same input → same hash)
- [ ] `is_sensitive_column()` correctly identifies sensitive columns
- [ ] `redact_sensitive_fields()` masks sensitive data for logs
- [ ] ≥95% test coverage

---

#### Issue 6.3.18 — Cross-space leakage metrics

**Status**: 🔲 NOT STARTED

**Goal**: Implement metrics for cross-space leakage detection and security monitoring.

**Dossier Reference**: Section 14.11 Learning Data Isolation, Section 8.1 Metrics

**Security Metrics to Implement**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| p03_cross_space_query_attempts | Counter | table, query_type | Should always be 0 |
| p03_rls_policy_blocks | Counter | table, policy_name | RLS enforcement count |
| p03_isolation_health | Gauge | pipeline | 1=healthy, 0=violations |
| p03_erasure_requests_total | Counter | scope, status | Erasure request count |
| p03_tombstone_count | Gauge | table, space_id | Tombstoned entities |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03 metrics | `k0/pipelines/p03/observability/metrics.py` | P03MetricsEmitter |
| RLS verifier | `k0/pipelines/p03/security/rls_verifier.py` | check_rls_health() |
| Query auditor | `k0/pipelines/p03/security/query_auditor.py` | CrossSpaceAuditor |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/observability/security_metrics.py`
2. [ ] Implement all 5 security metrics
3. [ ] Integrate with RLS verifier for health gauge
4. [ ] Integrate with query auditor for attempt counter
5. [ ] Add metric emission to erasure handler
6. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/observability/security_metrics.py
"""
Security metrics for P03 consolidation.

Tracks cross-space leakage detection, RLS enforcement,
and GDPR compliance metrics.

Dossier Reference: Section 8.1 Metrics, Section 14.11 Learning Data Isolation
"""

from __future__ import annotations

from typing import Literal

from k0.observability.metrics import counter, gauge


def record_cross_space_attempt(
    table: str,
    query_type: str,
) -> None:
    """
    Record a cross-space query attempt.

    This metric should always be 0 in a healthy system.

    Args:
        table: Table name
        query_type: Type of query (SELECT, UPDATE, etc.)
    """
    counter(
        "p03_cross_space_query_attempts",
        1,
        labels={
            "table": table,
            "query_type": query_type,
        },
    )


def record_rls_block(
    table: str,
    policy_name: str,
) -> None:
    """
    Record an RLS policy block.

    Args:
        table: Table name
        policy_name: RLS policy that blocked access
    """
    counter(
        "p03_rls_policy_blocks",
        1,
        labels={
            "table": table,
            "policy_name": policy_name,
        },
    )


def set_isolation_health(
    healthy: bool,
) -> None:
    """
    Set isolation health gauge.

    Args:
        healthy: True if no violations detected
    """
    gauge(
        "p03_isolation_health",
        1.0 if healthy else 0.0,
        labels={"pipeline": "p03_consolidation"},
    )


def record_erasure_request(
    scope: Literal["ACTOR_DATA", "ALL_MENTIONS", "FULL_PURGE"],
    status: Literal["COMPLETED", "PARTIAL", "FAILED"],
) -> None:
    """
    Record a GDPR erasure request.

    Args:
        scope: Erasure scope
        status: Request status
    """
    counter(
        "p03_erasure_requests_total",
        1,
        labels={
            "scope": scope,
            "status": status,
        },
    )


def set_tombstone_count(
    table: str,
    space_id: str,
    count: int,
) -> None:
    """
    Set tombstone count gauge.

    Args:
        table: Table name
        space_id: Space identifier
        count: Number of tombstoned entities
    """
    gauge(
        "p03_tombstone_count",
        float(count),
        labels={
            "table": table,
            "space_id": space_id,
        },
    )
```

**Acceptance Criteria**:

- [ ] `p03_cross_space_query_attempts` Counter always 0 in healthy system
- [ ] `p03_rls_policy_blocks` Counter tracks RLS enforcement
- [ ] `p03_isolation_health` Gauge reflects current health
- [ ] `p03_erasure_requests_total` Counter tracks erasure requests
- [ ] `p03_tombstone_count` Gauge tracks tombstoned entities
- [ ] All metrics scrapable via Prometheus endpoint
- [ ] ≥95% test coverage

---

#### Issue 6.3.19 — Security alerting rules

**Status**: 🔲 NOT STARTED

**Goal**: Implement alerting rules for security violations with immediate escalation.

**Dossier Reference**: Section 14 Security & Privacy, Section 8.1 Alert Configuration

**Alert Rules to Implement**:

| Alert | Expression | Duration | Severity |
|-------|------------|----------|----------|
| P03CrossSpaceLeakageDetected | p03_cross_space_query_attempts > 0 | 1m | critical |
| P03RLSBlockSpike | rate(p03_rls_policy_blocks[5m]) > 10 | 5m | warning |
| P03IsolationHealthDegraded | p03_isolation_health == 0 | 1m | critical |
| P03MissingRLSPolicy | p03_tables_without_rls > 0 | 1m | critical |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 telemetry | `k0/telemetry/mixins/*.py` | Alert rule builder pattern |
| Security metrics | `k0/pipelines/p03/observability/security_metrics.py` | Metric names |

**Work To Do**:

1. [ ] Create `k0/telemetry/mixins/p03_security_alerts.py` — rule builder
2. [ ] Generate `k0/telemetry/generated/rules/p03_security_alerts.yaml`
3. [ ] Implement all 4 alert rules
4. [ ] Add remediation steps to alert descriptions
5. [ ] Configure critical alerts to page on-call
6. [ ] Create validation tests

**Implementation Pattern**:

```python
# k0/telemetry/mixins/p03_security_alerts.py
"""
P03 security alerting rules.

Generates Prometheus/Grafana alerting rules for security violations.

Dossier Reference: Section 8.1 Alert Configuration
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class AlertRule:
    """Prometheus alerting rule definition."""
    name: str
    expression: str
    duration: str
    severity: str
    summary: str
    description: str
    runbook_url: str | None = None


class P03SecurityAlertBuilder:
    """Build security alerting rules for P03."""

    @classmethod
    def build_rules(cls) -> List[AlertRule]:
        """Build all P03 security alerting rules."""
        return [
            AlertRule(
                name="P03CrossSpaceLeakageDetected",
                expression="p03_cross_space_query_attempts > 0",
                duration="1m",
                severity="critical",
                summary="Cross-space data leakage detected in P03",
                description=(
                    "A query was detected accessing data across space boundaries. "
                    "This is a critical security violation. "
                    "Check pg_stat_statements for the offending query."
                ),
                runbook_url="https://docs/runbooks/p03-cross-space-leakage",
            ),
            AlertRule(
                name="P03RLSBlockSpike",
                expression="rate(p03_rls_policy_blocks[5m]) > 10",
                duration="5m",
                severity="warning",
                summary="High rate of RLS blocks in P03",
                description=(
                    "RLS policies are blocking an unusual number of queries. "
                    "This may indicate misconfigured queries or an attack attempt. "
                    "Review recent queries and application logs."
                ),
            ),
            AlertRule(
                name="P03IsolationHealthDegraded",
                expression="p03_isolation_health == 0",
                duration="1m",
                severity="critical",
                summary="P03 isolation health check failed",
                description=(
                    "RLS verification failed on one or more tables. "
                    "Run `k0ctl security status --pipeline p03_consolidation` "
                    "to identify missing RLS policies."
                ),
                runbook_url="https://docs/runbooks/p03-isolation-health",
            ),
            AlertRule(
                name="P03MissingRLSPolicy",
                expression="p03_tables_without_rls > 0",
                duration="1m",
                severity="critical",
                summary="Tables without RLS detected in P03",
                description=(
                    "One or more P03 learning tables do not have RLS enabled. "
                    "This is a critical security gap. "
                    "Run database migration to add missing policies."
                ),
            ),
        ]

    @classmethod
    def to_yaml(cls) -> str:
        """Generate YAML alerting rules."""
        rules = cls.build_rules()
        yaml_rules = []
        for rule in rules:
            yaml_rules.append(f"""
  - alert: {rule.name}
    expr: {rule.expression}
    for: {rule.duration}
    labels:
      severity: {rule.severity}
      pipeline: p03_consolidation
    annotations:
      summary: "{rule.summary}"
      description: "{rule.description}"
""")
        return f"""groups:
- name: p03_security_alerts
  rules:{''.join(yaml_rules)}"""
```

**Generated YAML** (`k0/telemetry/generated/rules/p03_security_alerts.yaml`):

```yaml
groups:
  - name: p03_security_alerts
    rules:
      - alert: P03CrossSpaceLeakageDetected
        expr: p03_cross_space_query_attempts > 0
        for: 1m
        labels:
          severity: critical
          pipeline: p03_consolidation
        annotations:
          summary: "Cross-space data leakage detected in P03"
          description: "A query was detected accessing data across space boundaries."

      - alert: P03RLSBlockSpike
        expr: rate(p03_rls_policy_blocks[5m]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High rate of RLS blocks in P03"

      - alert: P03IsolationHealthDegraded
        expr: p03_isolation_health == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "P03 isolation health check failed"
```

**Acceptance Criteria**:

- [ ] All 4 alert rules implemented
- [ ] Critical alerts configured to page on-call
- [ ] Alert descriptions include remediation steps
- [ ] Runbook URLs provided for critical alerts
- [ ] YAML rules importable into Prometheus/Grafana
- [ ] Alert tests validate rule expressions
- [ ] ≥95% test coverage

---

#### Issue 6.3.20 — Security integration tests

**Status**: 🔲 NOT STARTED

**Goal**: Comprehensive integration tests for all P03 security and privacy features.

**Dossier Reference**: Section 14 Security & Privacy

**Test Categories**:

| Category | Test File | Coverage Target |
|----------|-----------|-----------------|
| RLS | test_rls.py | All 6 learning tables |
| Privacy Bands | test_privacy_bands.py | GREEN/AMBER/RED |
| Erasure | test_erasure.py | Cascade + audit |
| Tombstone | test_tombstone.py | Lifecycle |
| Location | test_location_masking.py | Precision per band |

**Existing Code to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| Cross-space tests | Issue 6.3.6 | TestCrossSpaceIsolation pattern |
| Privacy band enforcer | Issue 6.3.10 | PrivacyBandEnforcer |
| Erasure handler | Issue 6.3.14 | P03ErasureHandler |
| Tombstone manager | Issue 6.3.15 | TombstoneManager |
| Location privacy | Issue 6.3.11 | P03LocationPrivacy |

**Work To Do**:

1. [ ] Create `tests/k0/modules/consolidation/security/test_rls.py`
2. [ ] Create `tests/k0/modules/consolidation/security/test_privacy_bands.py`
3. [ ] Create `tests/k0/modules/consolidation/security/test_erasure.py`
4. [ ] Create `tests/k0/modules/consolidation/security/test_tombstone.py`
5. [ ] Create `tests/k0/modules/consolidation/security/test_location_masking.py`
6. [ ] Ensure ≥90% line coverage for security module

**Implementation Pattern**:

```python
# tests/k0/modules/consolidation/security/test_rls.py
"""RLS integration tests for P03."""

import pytest
from k0.db.context_helper import p03_isolation_scope
from k0.pipelines.p03 import P03CycleContext
from k0.pipelines.p03.security.rls_verifier import (
    RLS_REQUIRED_TABLES,
    check_rls_health,
    verify_rls_enabled,
)


class TestRLSEnabled:
    """Verify RLS is enabled on all tables."""

    @pytest.mark.integration
    async def test_all_tables_have_rls(self, pg_pool) -> None:
        """All learning tables must have RLS."""
        async with pg_pool.acquire() as conn:
            missing = await verify_rls_enabled(conn)
            assert len(missing) == 0, f"Tables missing RLS: {missing}"

    @pytest.mark.integration
    async def test_rls_health_passes(self, pg_pool) -> None:
        """RLS health check should pass."""
        async with pg_pool.acquire() as conn:
            report = await check_rls_health(conn)
            assert report.healthy, report.summary()


class TestCrossSpaceBlocked:
    """Verify cross-space access is blocked."""

    @pytest.fixture
    def ctx_a(self) -> P03CycleContext:
        return P03CycleContext.create(
            tenant_id="t1", space_id="space-a", event_ids=["e1"]
        )

    @pytest.fixture
    def ctx_b(self) -> P03CycleContext:
        return P03CycleContext.create(
            tenant_id="t1", space_id="space-b", event_ids=["e2"]
        )

    @pytest.mark.integration
    @pytest.mark.parametrize("table", RLS_REQUIRED_TABLES)
    async def test_cross_space_returns_empty(
        self, pg_pool, ctx_a, ctx_b, table
    ) -> None:
        """Cross-space queries return empty, not error."""
        # Insert data with ctx_a
        async with p03_isolation_scope(ctx_a) as (conn, tx):
            # Insert test row (table-specific)
            pass

        # Query with ctx_b - should see nothing
        async with p03_isolation_scope(ctx_b) as (conn, tx):
            rows = await conn.fetch(f"SELECT * FROM {table} LIMIT 1")
            # Should be empty due to RLS


# tests/k0/modules/consolidation/security/test_privacy_bands.py
"""Privacy band integration tests for P03."""

import pytest
from k0.pipelines.p03.security.privacy_band import PrivacyBandEnforcer


class TestGreenBand:
    """GREEN band allows all operations."""

    def test_green_allows_cross_actor(self) -> None:
        """GREEN allows cross-actor linking."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="e1", event_b_id="e2",
            event_a_actor="a1", event_b_actor="a2",
            event_a_space="s1", event_b_space="s1",
            stamp_a_band="GREEN", stamp_b_band="GREEN",
        )
        assert result is True


class TestAmberBand:
    """AMBER band restricts cross-actor."""

    def test_amber_blocks_cross_actor(self) -> None:
        """AMBER blocks cross-actor linking."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="e1", event_b_id="e2",
            event_a_actor="a1", event_b_actor="a2",
            event_a_space="s1", event_b_space="s1",
            stamp_a_band="AMBER", stamp_b_band="GREEN",
        )
        assert result is False

    def test_amber_allows_same_actor(self) -> None:
        """AMBER allows same-actor linking."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="e1", event_b_id="e2",
            event_a_actor="a1", event_b_actor="a1",
            event_a_space="s1", event_b_space="s1",
            stamp_a_band="AMBER", stamp_b_band="GREEN",
        )
        assert result is True


class TestRedBand:
    """RED band restricts all linking."""

    def test_red_blocks_all_except_self(self) -> None:
        """RED only allows self-reference."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="e1", event_b_id="e2",
            event_a_actor="a1", event_b_actor="a1",
            event_a_space="s1", event_b_space="s1",
            stamp_a_band="RED", stamp_b_band="GREEN",
        )
        assert result is False

    def test_red_allows_self(self) -> None:
        """RED allows self-reference."""
        result = PrivacyBandEnforcer.can_link_events(
            event_a_id="e1", event_b_id="e1",  # Same event
            event_a_actor="a1", event_b_actor="a1",
            event_a_space="s1", event_b_space="s1",
            stamp_a_band="RED", stamp_b_band="RED",
        )
        assert result is True


# tests/k0/modules/consolidation/security/test_erasure.py
"""GDPR erasure integration tests for P03."""

import pytest
from k0.pipelines.p03.security.erasure_handler import P03ErasureHandler


class TestErasureCascade:
    """Erasure cascades to all tables."""

    @pytest.mark.integration
    async def test_erasure_marks_tombstone(self, pg_pool) -> None:
        """Erasure marks events as TOMBSTONE."""
        handler = P03ErasureHandler()
        async with pg_pool.acquire() as conn:
            result = await handler.handle_erasure_request(
                conn,
                tenant_id="t1",
                actor_id="actor-to-erase",
                scope="ACTOR_DATA",
            )
            assert result.status == "COMPLETED"


# tests/k0/modules/consolidation/security/test_location_masking.py
"""Location masking integration tests for P03."""

import pytest
from k0.pipelines.p03.security.location_privacy import P03LocationPrivacy


class TestLocationPrecision:
    """Location precision per band."""

    def test_green_full_precision(self) -> None:
        """GREEN returns full precision."""
        result = P03LocationPrivacy.process_location_for_kg(
            lat=37.7749, lon=-122.4194, stamp_band="GREEN"
        )
        assert result is not None
        assert len(result.geohash) == 12

    def test_amber_city_precision(self) -> None:
        """AMBER returns city precision."""
        result = P03LocationPrivacy.process_location_for_kg(
            lat=37.7749, lon=-122.4194, stamp_band="AMBER"
        )
        assert result is not None
        assert len(result.geohash) == 6

    def test_red_country_precision(self) -> None:
        """RED returns country precision."""
        result = P03LocationPrivacy.process_location_for_kg(
            lat=37.7749, lon=-122.4194, stamp_band="RED"
        )
        assert result is not None
        assert len(result.geohash) == 4
```

**Acceptance Criteria**:

- [ ] ≥90% line coverage for `k0/pipelines/p03/security/` module
- [ ] All 6 RLS tables tested for cross-space isolation
- [ ] All 3 privacy bands tested (GREEN/AMBER/RED)
- [ ] GDPR erasure cascade tested
- [ ] Tombstone lifecycle tested
- [ ] Location masking precision tested per band
- [ ] All tests pass with real PostgreSQL
- [ ] Tests integrated into CI pipeline

---

### Epic 6.4 — Performance + QoS

> **Scope**: Implement K0 QoS integration, adaptive batching, and performance tracking.
>
> **Dossier Reference**: Section 15 "Performance Tuning"

#### Epic 6.4 Issues Summary

| Issue | Title | Goal |
|-------|-------|------|
| 6.4.1 | P03SchedulerIntegration implementation | Token-based resource management |
| 6.4.2 | P03QoSContext budget management | Fanout/top_k budgets |
| 6.4.3 | P03AdaptiveBatchSizer implementation | K0-aware batch sizing |
| 6.4.4 | Phase latency targets implementation | Latency tracking |
| 6.4.5 | Throughput targets implementation | Throughput SLOs |
| 6.4.6 | Resource utilization metrics | CPU/memory/network |
| 6.4.7 | Database query optimization metrics | PostgreSQL optimization |
| 6.4.8 | Learning compute budget tracking | <5% cycle time |
| 6.4.9 | Learning batch processing optimization | Batch learning |
| 6.4.10 | Performance baseline validation tests | Performance tests |
| 6.4.11 | Load testing framework integration | Load testing |
| 6.4.12 | Performance regression detection | Regression alerts |

---

#### Issue 6.4.1 — P03SchedulerIntegration implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement integration with K0 QoS Scheduler for token-based resource management before batch processing.

**Dossier Reference**: Section 15.2 "K0 Scheduler Integration"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Scheduler | `k0/qos/scheduler.py` | `Scheduler.acquire()`, `SchedulerToken`, `SchedulerProfile` |
| K0 QoS Metrics | `k0/qos/metrics.py` | `QoSMetrics.record_acquisition()`, `update_port_metrics()` |
| K0 QoS Context | `k0/qos/context.py` | `QoSContext.acquire()` for delegation |

**K0 Scheduler Algorithm**:

- Uses Weighted Deficit Round Robin (WDRR) with priority bands: GREEN > AMBER > RED
- Token acquisition via `Scheduler.acquire(band=, port=, cost=)`
- Returns `SchedulerToken` as context manager for auto-release

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/qos/scheduler_integration.py`
2. [ ] Implement `P03SchedulerIntegration` class with K0 Scheduler
3. [ ] Define `P03_SCHEDULER_PROFILES` dict per dossier
4. [ ] Implement `acquire_batch_token()` using K0 `Scheduler.acquire()`
5. [ ] Implement `release_token()` using K0 `SchedulerToken.release()`
6. [ ] Integrate with K0 QoSMetrics for acquisition recording
7. [ ] Create unit tests and integration tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/qos/scheduler_integration.py
"""
P03 integration with K0 QoS Scheduler.

Uses K0 Scheduler for token-based resource management
with WDRR algorithm and priority bands.

Dossier Reference: Section 15.2 K0 Scheduler Integration
K0 Reference: k0/qos/scheduler.py, k0/qos/metrics.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional

from k0.qos.metrics import QoSMetrics
from k0.qos.scheduler import Scheduler, SchedulerToken

if TYPE_CHECKING:
    pass


# Scheduler profiles for P03 operations (from dossier Section 15.4)
@dataclass(frozen=True, slots=True)
class P03SchedulerProfile:
    """Scheduler profile for P03 operations."""

    name: str
    port: Literal["command", "query"]
    estimated_cost: float
    description: str


# P03-specific scheduler profiles from dossier
P03_SCHEDULER_PROFILES: dict[str, P03SchedulerProfile] = {
    "BATCH_CONSOLIDATION": P03SchedulerProfile(
        name="BATCH_CONSOLIDATION",
        port="command",
        estimated_cost=100.0,
        description="Standard batch consolidation processing",
    ),
    "SIMILARITY_SEARCH": P03SchedulerProfile(
        name="SIMILARITY_SEARCH",
        port="query",
        estimated_cost=50.0,
        description="FAISS/embedding similarity search",
    ),
    "DREAM_EXPLORATION": P03SchedulerProfile(
        name="DREAM_EXPLORATION",
        port="command",
        estimated_cost=200.0,
        description="Creative dream-phase exploration",
    ),
}


class P03SchedulerIntegration:
    """
    P03 integration with K0 QoS Scheduler.

    Manages token acquisition for batch processing using
    K0 WDRR scheduler with priority bands.

    K0 References:
    - k0/qos/scheduler.py: Scheduler.acquire(), Scheduler.tighten()
    - k0/qos/metrics.py: QoSMetrics.record_acquisition()
    """

    def __init__(
        self,
        scheduler: Scheduler,
        qos_metrics: QoSMetrics,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize P03 scheduler integration.

        Args:
            scheduler: K0 Scheduler instance
            qos_metrics: K0 QoSMetrics for telemetry
            pipeline_id: Pipeline identifier for metrics
        """
        self.scheduler = scheduler
        self.qos_metrics = qos_metrics
        self.pipeline_id = pipeline_id

    def acquire_batch_token(
        self,
        batch_size: int,
        band: Literal["GREEN", "AMBER", "RED"] = "GREEN",
        profile_name: str = "BATCH_CONSOLIDATION",
    ) -> Optional[SchedulerToken]:
        """
        Acquire scheduler token for batch processing.

        Uses K0 Scheduler.acquire() with WDRR algorithm.
        Priority: GREEN > AMBER > RED

        Args:
            batch_size: Number of events in batch
            band: Privacy band (affects priority)
            profile_name: Name of profile from P03_SCHEDULER_PROFILES

        Returns:
            SchedulerToken if acquired, None if capacity exceeded

        Raises:
            ValueError: If profile_name not found
        """
        profile = P03_SCHEDULER_PROFILES.get(profile_name)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_name}")

        # Calculate cost based on batch size and profile
        # Cost scales with batch size (dossier: cost = batch_size * 0.1)
        cost = max(1, int(batch_size * 0.1))

        try:
            # Acquire token from K0 Scheduler
            token = self.scheduler.acquire(
                band=band,
                port=profile.port,
                cost=cost,
            )

            # Record acquisition in K0 QoSMetrics
            self.qos_metrics.record_acquisition(
                band=band,
                port=profile.port,
            )

            return token

        except Exception:
            # Capacity exceeded - return None instead of raising
            # Caller should reduce batch size or wait
            return None

    def acquire_similarity_token(
        self,
        query_count: int,
        band: Literal["GREEN", "AMBER", "RED"] = "AMBER",
    ) -> Optional[SchedulerToken]:
        """
        Acquire token for similarity search operations.

        Uses query port with lower priority than command.

        Args:
            query_count: Number of queries to execute
            band: Privacy band (AMBER default for queries)

        Returns:
            SchedulerToken if acquired, None otherwise
        """
        return self.acquire_batch_token(
            batch_size=query_count,
            band=band,
            profile_name="SIMILARITY_SEARCH",
        )

    def acquire_dream_token(
        self,
        exploration_depth: int,
    ) -> Optional[SchedulerToken]:
        """
        Acquire token for dream phase exploration.

        Dream operations are high-cost creative exploration.

        Args:
            exploration_depth: Depth of exploration (affects cost)

        Returns:
            SchedulerToken if acquired, None otherwise
        """
        return self.acquire_batch_token(
            batch_size=exploration_depth * 2,  # Higher cost
            band="GREEN",
            profile_name="DREAM_EXPLORATION",
        )

    @staticmethod
    def release_token(token: SchedulerToken) -> None:
        """
        Release scheduler token after batch completion.

        Should be called in finally block or use token as context manager.

        Args:
            token: Token to release
        """
        token.release()
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/qos/test_scheduler_integration.py
"""Tests for P03SchedulerIntegration."""

import pytest
from unittest.mock import MagicMock

from k0.qos.scheduler import Scheduler, SchedulerProfile, SchedulerToken
from k0.qos.metrics import QoSMetrics


class TestP03SchedulerIntegration:
    """Test P03 scheduler integration."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create test scheduler."""
        profile = SchedulerProfile(
            name="test",
            description="Test profile",
            port_limits={"command": 100, "query": 50},
        )
        return Scheduler(profile=profile)

    @pytest.fixture
    def qos_metrics(self) -> MagicMock:
        """Mock QoS metrics."""
        return MagicMock(spec=QoSMetrics)

    def test_acquire_batch_token_success(
        self, scheduler, qos_metrics
    ) -> None:
        """Token acquired for valid batch."""
        from k0.pipelines.p03.qos.scheduler_integration import (
            P03SchedulerIntegration,
        )

        integration = P03SchedulerIntegration(scheduler, qos_metrics)
        token = integration.acquire_batch_token(batch_size=100)

        assert token is not None
        qos_metrics.record_acquisition.assert_called_once()

    def test_token_context_manager(
        self, scheduler, qos_metrics
    ) -> None:
        """Token works as context manager."""
        from k0.pipelines.p03.qos.scheduler_integration import (
            P03SchedulerIntegration,
        )

        integration = P03SchedulerIntegration(scheduler, qos_metrics)

        with integration.acquire_batch_token(batch_size=50) as token:
            assert token is not None
            # Token held during processing

        # Token auto-released after block

    def test_unknown_profile_raises(
        self, scheduler, qos_metrics
    ) -> None:
        """Unknown profile raises ValueError."""
        from k0.pipelines.p03.qos.scheduler_integration import (
            P03SchedulerIntegration,
        )

        integration = P03SchedulerIntegration(scheduler, qos_metrics)

        with pytest.raises(ValueError, match="Unknown profile"):
            integration.acquire_batch_token(
                batch_size=100, profile_name="INVALID"
            )
```

**Acceptance Criteria**:

- [ ] `P03SchedulerIntegration` class uses K0 `Scheduler.acquire()`
- [ ] `P03_SCHEDULER_PROFILES` defines 3 profiles per dossier
- [ ] Token acquired before batch processing starts
- [ ] Token released on batch completion (via context manager or explicit release)
- [ ] Metrics recorded via K0 `QoSMetrics.record_acquisition()`
- [ ] WDRR algorithm respects priority bands (GREEN > AMBER > RED)
- [ ] ≥95% test coverage

---

#### Issue 6.4.2 — P03QoSContext budget management

**Status**: 🔲 NOT STARTED

**Goal**: Implement K0 QoSContext integration for fanout and top_k budget management during cross-event queries.

**Dossier Reference**: Section 15.3 "K0 QoSContext Integration"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 QoS Context | `k0/qos/context.py` | `QoSContext.consume_fanout()`, `consume_top_k()`, `tighten()` |
| K0 QoS Policy | `k0/qos/policy.py` | `apply_qos_obligations()`, `QoSTightening` |
| K0 Scheduler | `k0/qos/scheduler.py` | `QoSContext.acquire()` for token delegation |

**Budget Types (from dossier)**:

- `fanout_budget`: Limits cross-event/cross-table queries (default: 1000)
- `top_k_budget`: Limits similarity search result size (default: 500)

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/qos/context_integration.py`
2. [ ] Implement `P03QoSContext` wrapper class
3. [ ] Implement `check_fanout_budget()` and `consume_fanout()`
4. [ ] Implement `check_top_k_budget()` and `consume_top_k()`
5. [ ] Implement `apply_tightening()` using K0 `apply_qos_obligations()`
6. [ ] Define `P03_QOS_DEFAULTS` dict per dossier
7. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/qos/context_integration.py
"""
P03 integration with K0 QoSContext.

Wraps K0 QoSContext for budget management during
cross-event queries and similarity search.

Dossier Reference: Section 15.3 K0 QoSContext Integration
K0 Reference: k0/qos/context.py, k0/qos/policy.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from k0.qos.context import QoSBudgetError, QoSContext
from k0.qos.policy import QoSTightening, apply_qos_obligations

if TYPE_CHECKING:
    pass


# Default QoS budgets for P03 operations (from dossier Section 15.3)
P03_QOS_DEFAULTS: dict[str, int] = {
    "fanout_budget": 1000,   # Max cross-event queries per batch
    "top_k_budget": 500,     # Max similarity results per batch
}


class P03QoSContext:
    """
    P03 integration with K0 QoSContext for budget management.

    Wraps QoSContext to provide P03-specific budget checking
    and consumption for cross-event queries and similarity search.

    K0 References:
    - k0/qos/context.py: QoSContext.consume_fanout(), consume_top_k()
    - k0/qos/policy.py: apply_qos_obligations()

    QoS Budgets:
    - fanout_budget: Limits cross-event/cross-table queries
    - top_k_budget: Limits similarity search result size
    """

    def __init__(self, qos_ctx: QoSContext) -> None:
        """
        Initialize P03 QoS context wrapper.

        Args:
            qos_ctx: K0 QoSContext instance
        """
        self.qos_ctx = qos_ctx

    @property
    def fanout_budget(self) -> int:
        """Current fanout budget remaining."""
        return self.qos_ctx.fanout_budget

    @property
    def top_k_budget(self) -> int:
        """Current top_k budget remaining."""
        return self.qos_ctx.top_k_budget

    def check_fanout_budget(self, required: int) -> bool:
        """
        Check if fanout budget allows cross-event queries.

        Used during R1-R4 when linking events across truth layers.

        Args:
            required: Number of fanout operations needed

        Returns:
            True if budget sufficient, False otherwise
        """
        return self.qos_ctx.fanout_budget >= required

    def consume_fanout(self, amount: int) -> bool:
        """
        Consume fanout budget for cross-event queries.

        Args:
            amount: Number of fanout operations to consume

        Returns:
            True if consumed successfully, False if insufficient budget

        Note:
            Returns False rather than raising to allow graceful degradation.
        """
        if not self.check_fanout_budget(amount):
            return False

        try:
            self.qos_ctx.consume_fanout(amount)
            return True
        except QoSBudgetError:
            return False

    def check_top_k_budget(self, required: int) -> bool:
        """
        Check if top_k budget allows similarity search.

        Used during FAISS queries for pattern matching.

        Args:
            required: Number of results requested

        Returns:
            True if budget sufficient, False otherwise
        """
        return self.qos_ctx.top_k_budget >= required

    def consume_top_k(self, amount: int) -> bool:
        """
        Consume top_k budget for similarity search.

        Args:
            amount: Number of results consumed

        Returns:
            True if consumed successfully, False if insufficient budget
        """
        if not self.check_top_k_budget(amount):
            return False

        try:
            self.qos_ctx.consume_top_k(amount)
            return True
        except QoSBudgetError:
            return False

    def apply_tightening(
        self,
        obligations: Sequence[Any],
    ) -> QoSTightening:
        """
        Apply QoS tightening from policy obligations.

        Uses K0 apply_qos_obligations() to process policy
        obligations and tighten budgets accordingly.

        Args:
            obligations: List of policy obligations

        Returns:
            QoSTightening schedule applied
        """
        return apply_qos_obligations(self.qos_ctx, obligations)

    def tighten(
        self,
        *,
        fanout: int | None = None,
        top_k: int | None = None,
    ) -> None:
        """
        Manually tighten budgets to lower values.

        Budgets can only be tightened (reduced), never increased.

        Args:
            fanout: New fanout limit (must be <= current)
            top_k: New top_k limit (must be <= current)
        """
        self.qos_ctx.tighten(fanout=fanout, top_k=top_k)


def create_p03_qos_context(
    scheduler,
    fanout_budget: int | None = None,
    top_k_budget: int | None = None,
) -> P03QoSContext:
    """
    Factory to create P03 QoSContext with defaults.

    Args:
        scheduler: K0 Scheduler instance
        fanout_budget: Override default fanout budget
        top_k_budget: Override default top_k budget

    Returns:
        Configured P03QoSContext
    """
    qos_ctx = QoSContext(
        scheduler=scheduler,
        fanout_budget=fanout_budget or P03_QOS_DEFAULTS["fanout_budget"],
        top_k_budget=top_k_budget or P03_QOS_DEFAULTS["top_k_budget"],
    )
    return P03QoSContext(qos_ctx)
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/qos/test_context_integration.py
"""Tests for P03QoSContext budget management."""

import pytest
from unittest.mock import MagicMock

from k0.qos.context import QoSContext
from k0.qos.scheduler import Scheduler, SchedulerProfile


class TestP03QoSContext:
    """Test P03 QoS context wrapper."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create test scheduler."""
        return Scheduler(profile=SchedulerProfile(
            name="test", description="Test"
        ))

    @pytest.fixture
    def qos_ctx(self, scheduler) -> QoSContext:
        """Create K0 QoSContext."""
        return QoSContext(
            scheduler=scheduler,
            fanout_budget=100,
            top_k_budget=50,
        )

    def test_check_fanout_sufficient(self, qos_ctx) -> None:
        """Check returns True when budget sufficient."""
        from k0.pipelines.p03.qos.context_integration import (
            P03QoSContext,
        )

        p03_ctx = P03QoSContext(qos_ctx)
        assert p03_ctx.check_fanout_budget(50) is True
        assert p03_ctx.check_fanout_budget(100) is True
        assert p03_ctx.check_fanout_budget(101) is False

    def test_consume_fanout_success(self, qos_ctx) -> None:
        """Consume reduces budget."""
        from k0.pipelines.p03.qos.context_integration import (
            P03QoSContext,
        )

        p03_ctx = P03QoSContext(qos_ctx)
        assert p03_ctx.consume_fanout(30) is True
        assert p03_ctx.fanout_budget == 70

    def test_consume_fanout_insufficient(self, qos_ctx) -> None:
        """Consume returns False when insufficient."""
        from k0.pipelines.p03.qos.context_integration import (
            P03QoSContext,
        )

        p03_ctx = P03QoSContext(qos_ctx)
        assert p03_ctx.consume_fanout(150) is False
        assert p03_ctx.fanout_budget == 100  # Unchanged

    def test_consume_top_k(self, qos_ctx) -> None:
        """Top-k consumption works."""
        from k0.pipelines.p03.qos.context_integration import (
            P03QoSContext,
        )

        p03_ctx = P03QoSContext(qos_ctx)
        assert p03_ctx.consume_top_k(25) is True
        assert p03_ctx.top_k_budget == 25

    def test_tighten_reduces_budget(self, qos_ctx) -> None:
        """Tighten can only reduce budgets."""
        from k0.pipelines.p03.qos.context_integration import (
            P03QoSContext,
        )

        p03_ctx = P03QoSContext(qos_ctx)
        p03_ctx.tighten(fanout=50)
        assert p03_ctx.fanout_budget == 50

        # Cannot increase
        p03_ctx.tighten(fanout=75)
        assert p03_ctx.fanout_budget == 50  # Still 50
```

**Acceptance Criteria**:

- [ ] `P03QoSContext` wraps K0 `QoSContext`
- [ ] `check_fanout_budget()` validates before consumption
- [ ] `consume_fanout()` returns False (not exception) when insufficient
- [ ] `check_top_k_budget()` validates similarity search budget
- [ ] `consume_top_k()` returns False when insufficient
- [ ] `apply_tightening()` uses K0 `apply_qos_obligations()`
- [ ] `P03_QOS_DEFAULTS` matches dossier (1000/500)
- [ ] ≥95% test coverage

---

#### Issue 6.4.3 — P03AdaptiveBatchSizer implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement K0-aware adaptive batch sizing based on scheduler state and resource constraints.

**Dossier Reference**: Section 15.4 "Batch Size Optimization (K0-Aware)"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Scheduler | `k0/qos/scheduler.py` | `Scheduler.active_tokens()` for contention |
| K0 QoS Metrics | `k0/qos/metrics.py` | `QoSMetrics.set_port_utilization()` |

**Batch Size Table (from dossier)**:

| Size | Events | Latency | Memory | Token Cost | fanout | top_k |
|------|--------|---------|--------|------------|--------|-------|
| Small | 100 | ~5s | 50MB | 10 | 100 | 50 |
| Medium | 1000 | ~30s | 200MB | 100 | 500 | 250 |
| Large | 10000 | ~5min | 1GB | 1000 | 2000 | 1000 |

**Contention Factors**:
>
- >10 active tokens → 0.5x (high contention)
- >5 active tokens → 0.75x (moderate contention)
- ≤5 active tokens → 1.0x (low contention)

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/qos/batch_sizer.py`
2. [ ] Implement `P03AdaptiveBatchSizer` class
3. [ ] Implement `compute_optimal_batch_size()` with contention/memory/time factors
4. [ ] Define batch size constants per dossier table
5. [ ] Report utilization to K0 QoSMetrics
6. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/qos/batch_sizer.py
"""
K0-aware adaptive batch sizing for P03.

Computes optimal batch size based on K0 scheduler state,
memory constraints, and time budget.

Dossier Reference: Section 15.4 Batch Size Optimization (K0-Aware)
K0 Reference: k0/qos/scheduler.py, k0/qos/metrics.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from k0.qos.metrics import QoSMetrics
from k0.qos.scheduler import Scheduler

if TYPE_CHECKING:
    pass


# Batch size presets from dossier Section 15.4
@dataclass(frozen=True, slots=True)
class BatchSizePreset:
    """Batch size preset with resource requirements."""

    name: str
    events: int
    latency_seconds: int
    memory_mb: int
    token_cost: int
    fanout_budget: int
    top_k_budget: int


BATCH_PRESETS: dict[str, BatchSizePreset] = {
    "SMALL": BatchSizePreset(
        name="SMALL",
        events=100,
        latency_seconds=5,
        memory_mb=50,
        token_cost=10,
        fanout_budget=100,
        top_k_budget=50,
    ),
    "MEDIUM": BatchSizePreset(
        name="MEDIUM",
        events=1000,
        latency_seconds=30,
        memory_mb=200,
        token_cost=100,
        fanout_budget=500,
        top_k_budget=250,
    ),
    "LARGE": BatchSizePreset(
        name="LARGE",
        events=10000,
        latency_seconds=300,
        memory_mb=1024,
        token_cost=1000,
        fanout_budget=2000,
        top_k_budget=1000,
    ),
}

# Batch size limits
MIN_BATCH_SIZE = 100
MAX_BATCH_SIZE = 10000
DEFAULT_BASE_BATCH_SIZE = 1000

# Contention thresholds
HIGH_CONTENTION_THRESHOLD = 10
MODERATE_CONTENTION_THRESHOLD = 5
MAX_TOKENS_ASSUMED = 20


class P03AdaptiveBatchSizer:
    """
    Adaptive batch sizing integrated with K0 QoS.

    Computes optimal batch size based on:
    - K0 scheduler contention (active tokens)
    - Available memory
    - Time budget

    K0 References:
    - k0/qos/scheduler.py: Scheduler.active_tokens()
    - k0/qos/metrics.py: QoSMetrics.set_port_utilization()
    """

    def __init__(
        self,
        scheduler: Scheduler,
        qos_metrics: QoSMetrics | None = None,
        base_batch_size: int = DEFAULT_BASE_BATCH_SIZE,
    ) -> None:
        """
        Initialize adaptive batch sizer.

        Args:
            scheduler: K0 Scheduler instance
            qos_metrics: K0 QoSMetrics for telemetry (optional)
            base_batch_size: Base batch size before adjustments
        """
        self.scheduler = scheduler
        self.qos_metrics = qos_metrics
        self.base_batch_size = base_batch_size

    def compute_optimal_batch_size(
        self,
        available_memory_mb: int,
        time_budget_seconds: int,
        port: str = "command",
    ) -> int:
        """
        Compute optimal batch size based on K0 scheduler state.

        Args:
            available_memory_mb: Available memory in MB
            time_budget_seconds: Time budget in seconds
            port: Scheduler port to check

        Returns:
            Optimal batch size clamped to [100, 10000]
        """
        # Get K0 scheduler contention
        active_tokens = self.scheduler.active_tokens(port)
        contention_factor = self._compute_contention_factor(active_tokens)

        # Memory constraint
        memory_factor = self._compute_memory_factor(available_memory_mb)

        # Time constraint
        time_factor = self._compute_time_factor(time_budget_seconds)

        # Compute optimal size
        optimal = int(
            self.base_batch_size
            * contention_factor
            * memory_factor
            * time_factor
        )

        # Report to K0 QoSMetrics
        if self.qos_metrics is not None:
            utilization = active_tokens / MAX_TOKENS_ASSUMED
            self.qos_metrics._port_utilization.labels(
                port=port
            ).set(min(1.0, utilization) * 100)

        # Clamp to valid range
        return max(MIN_BATCH_SIZE, min(MAX_BATCH_SIZE, optimal))

    def _compute_contention_factor(self, active_tokens: int) -> float:
        """
        Compute contention factor from active tokens.

        High contention = smaller batches to share resources.

        Args:
            active_tokens: Number of active scheduler tokens

        Returns:
            Factor between 0.5 and 1.0
        """
        if active_tokens > HIGH_CONTENTION_THRESHOLD:
            return 0.5  # High contention
        elif active_tokens > MODERATE_CONTENTION_THRESHOLD:
            return 0.75  # Moderate contention
        else:
            return 1.0  # Low contention

    def _compute_memory_factor(self, available_memory_mb: int) -> float:
        """
        Compute memory factor.

        Assumes 512MB is optimal baseline.

        Args:
            available_memory_mb: Available memory in MB

        Returns:
            Factor clamped to [0.1, 1.0]
        """
        return min(1.0, max(0.1, available_memory_mb / 512))

    def _compute_time_factor(self, time_budget_seconds: int) -> float:
        """
        Compute time factor.

        Assumes 300 seconds (5 min) is optimal baseline.

        Args:
            time_budget_seconds: Time budget in seconds

        Returns:
            Factor clamped to [0.1, 1.0]
        """
        return min(1.0, max(0.1, time_budget_seconds / 300))

    def get_preset_for_size(self, batch_size: int) -> BatchSizePreset:
        """
        Get the matching preset for a batch size.

        Args:
            batch_size: Computed batch size

        Returns:
            Matching preset (SMALL, MEDIUM, or LARGE)
        """
        if batch_size <= 100:
            return BATCH_PRESETS["SMALL"]
        elif batch_size <= 1000:
            return BATCH_PRESETS["MEDIUM"]
        else:
            return BATCH_PRESETS["LARGE"]
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/qos/test_batch_sizer.py
"""Tests for P03AdaptiveBatchSizer."""

import pytest
from unittest.mock import MagicMock

from k0.qos.scheduler import Scheduler, SchedulerProfile


class TestP03AdaptiveBatchSizer:
    """Test adaptive batch sizing."""

    @pytest.fixture
    def scheduler(self) -> MagicMock:
        """Mock scheduler with active_tokens."""
        mock = MagicMock(spec=Scheduler)
        mock.active_tokens.return_value = 0
        return mock

    def test_low_contention_full_batch(self, scheduler) -> None:
        """Low contention uses full batch size."""
        from k0.pipelines.p03.qos.batch_sizer import (
            P03AdaptiveBatchSizer,
        )

        scheduler.active_tokens.return_value = 2
        sizer = P03AdaptiveBatchSizer(scheduler, base_batch_size=1000)

        size = sizer.compute_optimal_batch_size(
            available_memory_mb=512,
            time_budget_seconds=300,
        )
        assert size == 1000

    def test_high_contention_half_batch(self, scheduler) -> None:
        """High contention halves batch size."""
        from k0.pipelines.p03.qos.batch_sizer import (
            P03AdaptiveBatchSizer,
        )

        scheduler.active_tokens.return_value = 15
        sizer = P03AdaptiveBatchSizer(scheduler, base_batch_size=1000)

        size = sizer.compute_optimal_batch_size(
            available_memory_mb=512,
            time_budget_seconds=300,
        )
        assert size == 500

    def test_low_memory_reduces_batch(self, scheduler) -> None:
        """Low memory reduces batch size."""
        from k0.pipelines.p03.qos.batch_sizer import (
            P03AdaptiveBatchSizer,
        )

        scheduler.active_tokens.return_value = 0
        sizer = P03AdaptiveBatchSizer(scheduler, base_batch_size=1000)

        size = sizer.compute_optimal_batch_size(
            available_memory_mb=256,  # Half optimal
            time_budget_seconds=300,
        )
        assert size == 500

    def test_minimum_batch_enforced(self, scheduler) -> None:
        """Batch never goes below minimum."""
        from k0.pipelines.p03.qos.batch_sizer import (
            P03AdaptiveBatchSizer,
            MIN_BATCH_SIZE,
        )

        scheduler.active_tokens.return_value = 20
        sizer = P03AdaptiveBatchSizer(scheduler, base_batch_size=100)

        size = sizer.compute_optimal_batch_size(
            available_memory_mb=50,
            time_budget_seconds=30,
        )
        assert size >= MIN_BATCH_SIZE

    def test_get_preset_for_size(self, scheduler) -> None:
        """Correct preset selected for size."""
        from k0.pipelines.p03.qos.batch_sizer import (
            P03AdaptiveBatchSizer,
        )

        sizer = P03AdaptiveBatchSizer(scheduler)

        small = sizer.get_preset_for_size(50)
        assert small.name == "SMALL"

        medium = sizer.get_preset_for_size(500)
        assert medium.name == "MEDIUM"

        large = sizer.get_preset_for_size(5000)
        assert large.name == "LARGE"
```

**Acceptance Criteria**:

- [ ] `P03AdaptiveBatchSizer` uses K0 `Scheduler.active_tokens()`
- [ ] Contention factor: >10 → 0.5x, >5 → 0.75x, else 1.0x
- [ ] Memory and time factors computed per dossier
- [ ] Batch size clamped to [100, 10000]
- [ ] Port utilization reported to K0 QoSMetrics
- [ ] `BATCH_PRESETS` matches dossier table
- [ ] ≥95% test coverage

---

#### Issue 6.4.4 — Phase latency targets implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement and track phase latency targets per dossier baselines using K0 MetricsExporter histograms.

**Dossier Reference**: Section 15.3.1 "Phase Latency Targets"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.histogram()` |
| K0 Observability | `k0/obs/__init__.py` | `ObservabilityEmitter` |

**Phase Latency Targets (from dossier)**:

| Phase | Target P50 | Target P95 | Target P99 |
|-------|------------|------------|------------|
| R0 (Batch Select) | 10ms | 50ms | 100ms |
| R1 (Importance/Hebbian) | 20ms | 100ms | 200ms |
| R2 (Episode Clustering) | 50ms | 200ms | 500ms |
| R3 (Dedup/Decay/Prune) | 30ms | 150ms | 300ms |
| R4 (KG/Entity/Causal) | 100ms | 300ms | 600ms |
| R5 (Dream - if enabled) | 200ms | 500ms | 1000ms |
| R6 (Status Update) | 10ms | 30ms | 50ms |
| R7 (Truth Write) | 50ms | 150ms | 300ms |
| R8 (Event Emit) | 5ms | 20ms | 50ms |
| **Full Cycle** | 500ms | 1500ms | 3000ms |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/obs/phase_metrics.py`
2. [ ] Define `PHASE_LATENCY_TARGETS` dict per dossier
3. [ ] Implement `P03PhaseMetrics` class using K0 MetricsExporter
4. [ ] Create histogram with appropriate buckets
5. [ ] Implement `record_phase_duration()` method
6. [ ] Implement `check_slo_compliance()` method
7. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/obs/phase_metrics.py
"""
P03 phase latency metrics.

Tracks phase-level latency using K0 MetricsExporter histograms
with SLO targets from dossier.

Dossier Reference: Section 15.3.1 Phase Latency Targets
K0 Reference: k0/obs/metrics.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Histogram


# Phase types
PhaseType = Literal[
    "R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "FULL_CYCLE"
]


@dataclass(frozen=True, slots=True)
class LatencyTarget:
    """Latency SLO targets for a phase."""

    phase: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    description: str


# Phase latency targets from dossier Section 15.3.1
PHASE_LATENCY_TARGETS: dict[str, LatencyTarget] = {
    "R0": LatencyTarget("R0", 10, 50, 100, "Batch Select"),
    "R1": LatencyTarget("R1", 20, 100, 200, "Importance/Hebbian"),
    "R2": LatencyTarget("R2", 50, 200, 500, "Episode Clustering"),
    "R3": LatencyTarget("R3", 30, 150, 300, "Dedup/Decay/Prune"),
    "R4": LatencyTarget("R4", 100, 300, 600, "KG/Entity/Causal"),
    "R5": LatencyTarget("R5", 200, 500, 1000, "Dream Exploration"),
    "R6": LatencyTarget("R6", 10, 30, 50, "Status Update"),
    "R7": LatencyTarget("R7", 50, 150, 300, "Truth Write"),
    "R8": LatencyTarget("R8", 5, 20, 50, "Event Emit"),
    "FULL_CYCLE": LatencyTarget("FULL_CYCLE", 500, 1500, 3000, "Full Cycle"),
}

# Histogram buckets in seconds (covering 1ms to 5s)
# Aligned with dossier targets
LATENCY_BUCKETS_SECONDS = (
    0.001,   # 1ms
    0.005,   # 5ms
    0.01,    # 10ms
    0.02,    # 20ms
    0.03,    # 30ms
    0.05,    # 50ms
    0.1,     # 100ms
    0.15,    # 150ms
    0.2,     # 200ms
    0.3,     # 300ms
    0.5,     # 500ms
    1.0,     # 1s
    1.5,     # 1.5s
    2.0,     # 2s
    3.0,     # 3s
    5.0,     # 5s
)


class P03PhaseMetrics:
    """
    P03 phase latency metrics using K0 MetricsExporter.

    Tracks phase-level duration histograms and provides
    SLO compliance checking.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram()
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize phase metrics.

        Args:
            metrics_exporter: K0 MetricsExporter instance
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics_exporter
        self.pipeline_id = pipeline_id

        # Create phase duration histogram
        self._phase_duration: Histogram = metrics_exporter.histogram(
            name="p03_phase_duration_seconds",
            description="P03 phase execution duration in seconds",
            labelnames=["phase", "pipeline_id"],
            buckets=LATENCY_BUCKETS_SECONDS,
        )

        # Create full cycle histogram
        self._cycle_duration: Histogram = metrics_exporter.histogram(
            name="p03_cycle_duration_seconds",
            description="P03 full cycle duration in seconds",
            labelnames=["pipeline_id"],
            buckets=LATENCY_BUCKETS_SECONDS,
        )

    def record_phase_duration(
        self,
        phase: PhaseType,
        duration_ms: float,
    ) -> None:
        """
        Record phase execution duration.

        Args:
            phase: Phase identifier (R0-R8 or FULL_CYCLE)
            duration_ms: Duration in milliseconds
        """
        duration_seconds = duration_ms / 1000.0

        if phase == "FULL_CYCLE":
            self._cycle_duration.labels(
                pipeline_id=self.pipeline_id,
            ).observe(duration_seconds)
        else:
            self._phase_duration.labels(
                phase=phase,
                pipeline_id=self.pipeline_id,
            ).observe(duration_seconds)

    def check_slo_compliance(
        self,
        phase: PhaseType,
        duration_ms: float,
    ) -> tuple[bool, str]:
        """
        Check if duration meets SLO targets.

        Args:
            phase: Phase identifier
            duration_ms: Observed duration in milliseconds

        Returns:
            Tuple of (is_compliant, reason)
        """
        target = PHASE_LATENCY_TARGETS.get(phase)
        if target is None:
            return True, f"No target defined for {phase}"

        if duration_ms <= target.p50_ms:
            return True, f"Excellent: {duration_ms:.1f}ms <= P50 ({target.p50_ms}ms)"
        elif duration_ms <= target.p95_ms:
            return True, f"Good: {duration_ms:.1f}ms <= P95 ({target.p95_ms}ms)"
        elif duration_ms <= target.p99_ms:
            return True, f"Warning: {duration_ms:.1f}ms <= P99 ({target.p99_ms}ms)"
        else:
            return False, f"SLO breach: {duration_ms:.1f}ms > P99 ({target.p99_ms}ms)"

    def get_target(self, phase: PhaseType) -> LatencyTarget | None:
        """Get latency target for a phase."""
        return PHASE_LATENCY_TARGETS.get(phase)
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/obs/test_phase_metrics.py
"""Tests for P03 phase latency metrics."""

import pytest
from unittest.mock import MagicMock

from k0.obs.metrics import MetricsExporter


class TestP03PhaseMetrics:
    """Test phase latency tracking."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MetricsExporter(namespace="test")

    def test_record_phase_duration(self, metrics_exporter) -> None:
        """Duration recorded to histogram."""
        from k0.pipelines.p03.obs.phase_metrics import (
            P03PhaseMetrics,
        )

        phase_metrics = P03PhaseMetrics(metrics_exporter)
        phase_metrics.record_phase_duration("R0", 25.0)
        # Histogram observation recorded (verify via registry)

    def test_check_slo_excellent(self, metrics_exporter) -> None:
        """Duration under P50 is excellent."""
        from k0.pipelines.p03.obs.phase_metrics import (
            P03PhaseMetrics,
        )

        phase_metrics = P03PhaseMetrics(metrics_exporter)
        compliant, reason = phase_metrics.check_slo_compliance("R0", 5.0)

        assert compliant is True
        assert "Excellent" in reason

    def test_check_slo_breach(self, metrics_exporter) -> None:
        """Duration over P99 is breach."""
        from k0.pipelines.p03.obs.phase_metrics import (
            P03PhaseMetrics,
        )

        phase_metrics = P03PhaseMetrics(metrics_exporter)
        compliant, reason = phase_metrics.check_slo_compliance("R0", 150.0)

        assert compliant is False
        assert "breach" in reason

    def test_full_cycle_uses_separate_histogram(
        self, metrics_exporter
    ) -> None:
        """Full cycle recorded to dedicated histogram."""
        from k0.pipelines.p03.obs.phase_metrics import (
            P03PhaseMetrics,
        )

        phase_metrics = P03PhaseMetrics(metrics_exporter)
        phase_metrics.record_phase_duration("FULL_CYCLE", 1200.0)
        # Uses _cycle_duration histogram

    def test_get_target_returns_correct_values(
        self, metrics_exporter
    ) -> None:
        """Target lookup returns dossier values."""
        from k0.pipelines.p03.obs.phase_metrics import (
            P03PhaseMetrics,
        )

        phase_metrics = P03PhaseMetrics(metrics_exporter)
        target = phase_metrics.get_target("R4")

        assert target is not None
        assert target.p50_ms == 100
        assert target.p95_ms == 300
        assert target.p99_ms == 600
```

**Acceptance Criteria**:

- [ ] `P03PhaseMetrics` uses K0 `MetricsExporter.histogram()`
- [ ] All 9 phases (R0-R8) tracked with histograms
- [ ] Full cycle duration tracked separately
- [ ] `PHASE_LATENCY_TARGETS` matches dossier table
- [ ] Histogram buckets cover 1ms to 5s range
- [ ] `check_slo_compliance()` returns compliance status
- [ ] Metrics exposed via K0 registry
- [ ] ≥95% test coverage

---

#### Issue 6.4.5 — Throughput targets implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement throughput tracking and SLO validation for events per cycle and processing rates.

**Dossier Reference**: Section 15.3.2 "Throughput Targets"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.counter()`, `gauge()` |
| K0 Observability | `k0/obs/__init__.py` | `ObservabilityEmitter` |

**Throughput Targets (from dossier)**:

| Metric | Target | Description |
|--------|--------|-------------|
| Events per cycle | 1000 | Standard batch size |
| Cycles per hour | 40 | 90-second interval |
| Events per hour | 40,000 | Sustained throughput |
| Peak events per hour | 100,000 | With adaptive batching |

**SLO Targets (from dossier)**:

| SLO | Value | Description |
|-----|-------|-------------|
| cycle_duration_p99_ms | 300,000 | 5 minute max cycle |
| batch_throughput_min | 100 | Events per second minimum |
| memory_max_mb | 512 | Memory ceiling |
| error_rate_max | 0.01 | 1% maximum error rate |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/obs/throughput_metrics.py`
2. [ ] Define `P03_THROUGHPUT_TARGETS` dict per dossier
3. [ ] Define `P03_SLO_TARGETS` dict per dossier
4. [ ] Implement `P03ThroughputMetrics` class using K0 MetricsExporter
5. [ ] Implement `record_batch_size()` method
6. [ ] Implement `set_backlog_size()` method
7. [ ] Implement `check_throughput_slo()` method
8. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/obs/throughput_metrics.py
"""
P03 throughput metrics and SLO tracking.

Tracks events per cycle, cycles per hour, and throughput
SLOs using K0 MetricsExporter.

Dossier Reference: Section 15.3.2 Throughput Targets
K0 Reference: k0/obs/metrics.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram


@dataclass(frozen=True, slots=True)
class ThroughputTarget:
    """Throughput SLO target."""

    name: str
    value: float
    unit: str
    description: str


# Throughput targets from dossier Section 15.3.2
P03_THROUGHPUT_TARGETS: dict[str, ThroughputTarget] = {
    "events_per_cycle": ThroughputTarget(
        "events_per_cycle", 1000, "events", "Standard batch size"
    ),
    "cycles_per_hour": ThroughputTarget(
        "cycles_per_hour", 40, "cycles", "90-second interval"
    ),
    "events_per_hour": ThroughputTarget(
        "events_per_hour", 40000, "events", "Sustained throughput"
    ),
    "peak_events_per_hour": ThroughputTarget(
        "peak_events_per_hour", 100000, "events", "With adaptive batching"
    ),
}


@dataclass(frozen=True, slots=True)
class SLOTarget:
    """Service Level Objective target."""

    name: str
    value: float
    unit: str
    alert_threshold: float
    description: str


# SLO targets from dossier Section 15.3.2
P03_SLO_TARGETS: dict[str, SLOTarget] = {
    "cycle_duration_p99_ms": SLOTarget(
        "cycle_duration_p99_ms",
        300000,  # 5 minutes
        "ms",
        240000,  # Alert at 4 minutes (80%)
        "Maximum cycle duration",
    ),
    "batch_throughput_min": SLOTarget(
        "batch_throughput_min",
        100,
        "events/sec",
        50,  # Alert if below 50 events/sec
        "Minimum batch throughput",
    ),
    "memory_max_mb": SLOTarget(
        "memory_max_mb",
        512,
        "MB",
        410,  # Alert at 80%
        "Memory ceiling per cycle",
    ),
    "error_rate_max": SLOTarget(
        "error_rate_max",
        0.01,  # 1%
        "ratio",
        0.005,  # Alert at 0.5%
        "Maximum error rate",
    ),
}


class P03ThroughputMetrics:
    """
    P03 throughput metrics using K0 MetricsExporter.

    Tracks events processed, cycles completed, and
    throughput SLO compliance.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter(), gauge()
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize throughput metrics.

        Args:
            metrics_exporter: K0 MetricsExporter instance
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics_exporter
        self.pipeline_id = pipeline_id

        # Counters
        self._events_processed: Counter = metrics_exporter.counter(
            name="p03_events_processed_total",
            description="Total events processed by P03",
            labelnames=["phase", "pipeline_id", "status"],
        )

        self._cycles_completed: Counter = metrics_exporter.counter(
            name="p03_cycles_completed_total",
            description="Total consolidation cycles completed",
            labelnames=["pipeline_id", "status"],
        )

        # Gauges
        self._backlog_size: Gauge = metrics_exporter.gauge(
            name="p03_backlog_events",
            description="Number of events pending consolidation",
            labelnames=["tenant_id", "pipeline_id"],
        )

        self._current_batch_size: Gauge = metrics_exporter.gauge(
            name="p03_current_batch_size",
            description="Size of current batch being processed",
            labelnames=["pipeline_id"],
        )

        self._throughput_events_per_second: Gauge = metrics_exporter.gauge(
            name="p03_throughput_events_per_second",
            description="Current throughput in events per second",
            labelnames=["pipeline_id"],
        )

        # Histograms
        self._batch_size_histogram: Histogram = metrics_exporter.histogram(
            name="p03_batch_size",
            description="Batch size distribution",
            labelnames=["phase", "pipeline_id"],
            buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
        )

    def record_batch_size(
        self,
        phase: str,
        size: int,
    ) -> None:
        """
        Record batch size processed.

        Args:
            phase: Processing phase (e.g., "R0", "R3")
            size: Number of events in batch
        """
        self._batch_size_histogram.labels(
            phase=phase,
            pipeline_id=self.pipeline_id,
        ).observe(size)

        self._current_batch_size.labels(
            pipeline_id=self.pipeline_id,
        ).set(size)

    def record_events_processed(
        self,
        phase: str,
        count: int,
        status: str = "success",
    ) -> None:
        """
        Record events processed.

        Args:
            phase: Processing phase
            count: Number of events processed
            status: Processing status (success/error)
        """
        self._events_processed.labels(
            phase=phase,
            pipeline_id=self.pipeline_id,
            status=status,
        ).inc(count)

    def record_cycle_completed(
        self,
        status: str = "success",
    ) -> None:
        """
        Record cycle completion.

        Args:
            status: Cycle status (success/error/partial)
        """
        self._cycles_completed.labels(
            pipeline_id=self.pipeline_id,
            status=status,
        ).inc()

    def set_backlog_size(
        self,
        tenant_id: str,
        size: int,
    ) -> None:
        """
        Set current backlog size.

        Args:
            tenant_id: Tenant identifier
            size: Number of pending events
        """
        self._backlog_size.labels(
            tenant_id=tenant_id,
            pipeline_id=self.pipeline_id,
        ).set(size)

    def set_throughput(
        self,
        events_per_second: float,
    ) -> None:
        """
        Set current throughput.

        Args:
            events_per_second: Current processing rate
        """
        self._throughput_events_per_second.labels(
            pipeline_id=self.pipeline_id,
        ).set(events_per_second)

    def check_throughput_slo(
        self,
        events_per_second: float,
    ) -> tuple[bool, str]:
        """
        Check if throughput meets SLO.

        Args:
            events_per_second: Current throughput

        Returns:
            Tuple of (is_compliant, reason)
        """
        slo = P03_SLO_TARGETS["batch_throughput_min"]

        if events_per_second >= slo.value:
            return True, f"Throughput OK: {events_per_second:.1f} >= {slo.value}"
        elif events_per_second >= slo.alert_threshold:
            return True, f"Throughput warning: {events_per_second:.1f} < {slo.value}"
        else:
            return False, f"SLO breach: {events_per_second:.1f} < {slo.alert_threshold}"
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/obs/test_throughput_metrics.py
"""Tests for P03 throughput metrics."""

import pytest

from k0.obs.metrics import MetricsExporter


class TestP03ThroughputMetrics:
    """Test throughput tracking."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MetricsExporter(namespace="test")

    def test_record_batch_size(self, metrics_exporter) -> None:
        """Batch size recorded to histogram."""
        from k0.pipelines.p03.obs.throughput_metrics import (
            P03ThroughputMetrics,
        )

        throughput = P03ThroughputMetrics(metrics_exporter)
        throughput.record_batch_size("R0", 500)
        # Histogram observation recorded

    def test_record_events_processed(self, metrics_exporter) -> None:
        """Events counter incremented."""
        from k0.pipelines.p03.obs.throughput_metrics import (
            P03ThroughputMetrics,
        )

        throughput = P03ThroughputMetrics(metrics_exporter)
        throughput.record_events_processed("R3", 1000)
        # Counter incremented by 1000

    def test_set_backlog_size(self, metrics_exporter) -> None:
        """Backlog gauge set correctly."""
        from k0.pipelines.p03.obs.throughput_metrics import (
            P03ThroughputMetrics,
        )

        throughput = P03ThroughputMetrics(metrics_exporter)
        throughput.set_backlog_size("tenant-1", 5000)
        # Gauge set to 5000

    def test_check_throughput_slo_pass(self, metrics_exporter) -> None:
        """Throughput above target passes."""
        from k0.pipelines.p03.obs.throughput_metrics import (
            P03ThroughputMetrics,
        )

        throughput = P03ThroughputMetrics(metrics_exporter)
        compliant, reason = throughput.check_throughput_slo(150.0)

        assert compliant is True
        assert "OK" in reason

    def test_check_throughput_slo_breach(self, metrics_exporter) -> None:
        """Throughput below threshold breaches."""
        from k0.pipelines.p03.obs.throughput_metrics import (
            P03ThroughputMetrics,
        )

        throughput = P03ThroughputMetrics(metrics_exporter)
        compliant, reason = throughput.check_throughput_slo(25.0)

        assert compliant is False
        assert "breach" in reason
```

**Acceptance Criteria**:

- [ ] `P03ThroughputMetrics` uses K0 `MetricsExporter`
- [ ] `p03_events_processed_total` Counter tracks events by phase
- [ ] `p03_cycles_completed_total` Counter tracks cycle completions
- [ ] `p03_backlog_events` Gauge tracks pending events per tenant
- [ ] `p03_batch_size` Histogram tracks batch size distribution
- [ ] `P03_THROUGHPUT_TARGETS` matches dossier values
- [ ] `P03_SLO_TARGETS` defines alert thresholds
- [ ] `check_throughput_slo()` validates against targets
- [ ] ≥95% test coverage

---

#### Issue 6.4.6 — Resource utilization metrics

**Status**: 🔲 NOT STARTED

**Goal**: Implement resource utilization tracking (memory, CPU, DB connections, FAISS queries) per dossier baselines.

**Dossier Reference**: Section 15.3.3 "Resource Utilization Targets"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.gauge()`, `counter()` |
| K0 DB Pool | `k0/db/pool.py` | Pool stats for connection tracking |

**Resource Utilization Targets (from dossier)**:

| Resource | Target | Alert Threshold | Description |
|----------|--------|-----------------|-------------|
| Memory (per cycle) | < 512MB | 80% (410MB) | Memory ceiling |
| CPU (per cycle) | < 2 cores | 90% for >30s | CPU limit |
| DB connections | < 10 pooled | 80% exhaustion | Pool limit |
| FAISS queries/cycle | < 100 | N/A | Query budget |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/obs/resource_metrics.py`
2. [ ] Define `P03_RESOURCE_TARGETS` dict per dossier
3. [ ] Implement `P03ResourceMetrics` class
4. [ ] Implement memory tracking with `p03_memory_mb` Gauge
5. [ ] Implement CPU tracking with `p03_cpu_utilization` Gauge
6. [ ] Implement DB pool tracking with `p03_db_pool_active` Gauge
7. [ ] Implement FAISS query tracking with `p03_faiss_queries_total` Counter
8. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/obs/resource_metrics.py
"""
P03 resource utilization metrics.

Tracks memory, CPU, DB connections, and FAISS queries
per dossier resource utilization targets.

Dossier Reference: Section 15.3.3 Resource Utilization Targets
K0 Reference: k0/obs/metrics.py
"""

from __future__ import annotations

import os
import resource
from dataclasses import dataclass
from typing import TYPE_CHECKING

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge


@dataclass(frozen=True, slots=True)
class ResourceTarget:
    """Resource utilization target."""

    name: str
    target_value: float
    alert_threshold: float
    unit: str
    description: str


# Resource targets from dossier Section 15.3.3
P03_RESOURCE_TARGETS: dict[str, ResourceTarget] = {
    "memory_mb": ResourceTarget(
        "memory_mb",
        512.0,
        410.0,  # 80% alert threshold
        "MB",
        "Memory per cycle",
    ),
    "cpu_cores": ResourceTarget(
        "cpu_cores",
        2.0,
        1.8,  # 90% alert threshold
        "cores",
        "CPU per cycle",
    ),
    "db_connections": ResourceTarget(
        "db_connections",
        10,
        8,  # 80% alert threshold
        "connections",
        "DB connection pool",
    ),
    "faiss_queries": ResourceTarget(
        "faiss_queries",
        100,
        100,  # No alert threshold
        "queries",
        "FAISS queries per cycle",
    ),
}

# Memory thresholds for pressure levels
MEMORY_THRESHOLDS = {
    "warning_mb": 256,
    "throttle_mb": 384,
    "critical_mb": 480,
}


class P03ResourceMetrics:
    """
    P03 resource utilization metrics using K0 MetricsExporter.

    Tracks memory, CPU, DB connections, and FAISS queries.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.gauge(), counter()
    """

    def __init__(
        self,
        metrics_exporter: MetricsExporter,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize resource metrics.

        Args:
            metrics_exporter: K0 MetricsExporter instance
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics_exporter
        self.pipeline_id = pipeline_id

        # Memory gauge
        self._memory_mb: Gauge = metrics_exporter.gauge(
            name="p03_memory_mb",
            description="P03 memory usage in MB",
            labelnames=["stage", "pipeline_id"],
        )

        # CPU gauge
        self._cpu_utilization: Gauge = metrics_exporter.gauge(
            name="p03_cpu_utilization",
            description="P03 CPU utilization (0.0-1.0)",
            labelnames=["pipeline_id"],
        )

        # DB pool gauge
        self._db_pool_active: Gauge = metrics_exporter.gauge(
            name="p03_db_pool_active",
            description="Active DB connections in pool",
            labelnames=["pipeline_id"],
        )

        self._db_pool_size: Gauge = metrics_exporter.gauge(
            name="p03_db_pool_size",
            description="Total DB pool size",
            labelnames=["pipeline_id"],
        )

        # FAISS query counter
        self._faiss_queries: Counter = metrics_exporter.counter(
            name="p03_faiss_queries_total",
            description="Total FAISS queries executed",
            labelnames=["operation", "pipeline_id"],
        )

        # Memory pressure gauge
        self._memory_pressure: Gauge = metrics_exporter.gauge(
            name="p03_memory_pressure",
            description="Memory pressure level (0=ok, 1=warning, 2=throttle, 3=critical)",
            labelnames=["pipeline_id"],
        )

    def record_memory_usage(
        self,
        stage: str,
        memory_mb: float | None = None,
    ) -> None:
        """
        Record memory usage for a stage.

        Args:
            stage: Processing stage (R0-R8)
            memory_mb: Memory in MB (auto-detect if None)
        """
        if memory_mb is None:
            # Auto-detect from process
            memory_mb = self._get_process_memory_mb()

        self._memory_mb.labels(
            stage=stage,
            pipeline_id=self.pipeline_id,
        ).set(memory_mb)

        # Update pressure level
        pressure = self._compute_memory_pressure(memory_mb)
        self._memory_pressure.labels(
            pipeline_id=self.pipeline_id,
        ).set(pressure)

    def record_cpu_utilization(
        self,
        utilization: float,
    ) -> None:
        """
        Record CPU utilization.

        Args:
            utilization: CPU usage (0.0-1.0)
        """
        self._cpu_utilization.labels(
            pipeline_id=self.pipeline_id,
        ).set(utilization)

    def record_db_pool_stats(
        self,
        active: int,
        pool_size: int,
    ) -> None:
        """
        Record DB connection pool stats.

        Args:
            active: Active connections
            pool_size: Total pool size
        """
        self._db_pool_active.labels(
            pipeline_id=self.pipeline_id,
        ).set(active)

        self._db_pool_size.labels(
            pipeline_id=self.pipeline_id,
        ).set(pool_size)

    def record_faiss_query(
        self,
        operation: str = "search",
        count: int = 1,
    ) -> None:
        """
        Record FAISS query execution.

        Args:
            operation: Query type (search, add, etc.)
            count: Number of queries
        """
        self._faiss_queries.labels(
            operation=operation,
            pipeline_id=self.pipeline_id,
        ).inc(count)

    def check_memory_threshold(
        self,
        memory_mb: float,
    ) -> tuple[str, bool]:
        """
        Check if memory exceeds thresholds.

        Args:
            memory_mb: Current memory usage

        Returns:
            Tuple of (level, should_throttle)
        """
        target = P03_RESOURCE_TARGETS["memory_mb"]

        if memory_mb >= MEMORY_THRESHOLDS["critical_mb"]:
            return "critical", True
        elif memory_mb >= MEMORY_THRESHOLDS["throttle_mb"]:
            return "throttle", True
        elif memory_mb >= MEMORY_THRESHOLDS["warning_mb"]:
            return "warning", False
        else:
            return "ok", False

    def _get_process_memory_mb(self) -> float:
        """Get current process memory in MB."""
        try:
            # Unix: use resource module
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return usage.ru_maxrss / 1024  # Convert KB to MB
        except Exception:
            return 0.0

    def _compute_memory_pressure(self, memory_mb: float) -> int:
        """Compute memory pressure level."""
        if memory_mb >= MEMORY_THRESHOLDS["critical_mb"]:
            return 3
        elif memory_mb >= MEMORY_THRESHOLDS["throttle_mb"]:
            return 2
        elif memory_mb >= MEMORY_THRESHOLDS["warning_mb"]:
            return 1
        else:
            return 0
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/obs/test_resource_metrics.py
"""Tests for P03 resource utilization metrics."""

import pytest

from k0.obs.metrics import MetricsExporter


class TestP03ResourceMetrics:
    """Test resource utilization tracking."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MetricsExporter(namespace="test")

    def test_record_memory_usage(self, metrics_exporter) -> None:
        """Memory gauge set correctly."""
        from k0.pipelines.p03.obs.resource_metrics import (
            P03ResourceMetrics,
        )

        resource_metrics = P03ResourceMetrics(metrics_exporter)
        resource_metrics.record_memory_usage("R3", 256.0)
        # Gauge set to 256

    def test_record_db_pool_stats(self, metrics_exporter) -> None:
        """DB pool stats tracked."""
        from k0.pipelines.p03.obs.resource_metrics import (
            P03ResourceMetrics,
        )

        resource_metrics = P03ResourceMetrics(metrics_exporter)
        resource_metrics.record_db_pool_stats(active=5, pool_size=10)
        # Both gauges updated

    def test_record_faiss_query(self, metrics_exporter) -> None:
        """FAISS queries counted."""
        from k0.pipelines.p03.obs.resource_metrics import (
            P03ResourceMetrics,
        )

        resource_metrics = P03ResourceMetrics(metrics_exporter)
        resource_metrics.record_faiss_query("search", 5)
        # Counter incremented by 5

    def test_memory_threshold_ok(self, metrics_exporter) -> None:
        """Low memory is OK."""
        from k0.pipelines.p03.obs.resource_metrics import (
            P03ResourceMetrics,
        )

        resource_metrics = P03ResourceMetrics(metrics_exporter)
        level, throttle = resource_metrics.check_memory_threshold(200.0)

        assert level == "ok"
        assert throttle is False

    def test_memory_threshold_critical(self, metrics_exporter) -> None:
        """High memory triggers critical."""
        from k0.pipelines.p03.obs.resource_metrics import (
            P03ResourceMetrics,
        )

        resource_metrics = P03ResourceMetrics(metrics_exporter)
        level, throttle = resource_metrics.check_memory_threshold(490.0)

        assert level == "critical"
        assert throttle is True
```

**Acceptance Criteria**:

- [ ] `P03ResourceMetrics` uses K0 `MetricsExporter`
- [ ] `p03_memory_mb` Gauge tracks memory per stage
- [ ] `p03_cpu_utilization` Gauge tracks CPU usage
- [ ] `p03_db_pool_active` Gauge tracks active DB connections
- [ ] `p03_faiss_queries_total` Counter tracks FAISS queries
- [ ] `P03_RESOURCE_TARGETS` matches dossier values
- [ ] Memory pressure levels (ok/warning/throttle/critical) computed
- [ ] `check_memory_threshold()` returns throttle decision
- [ ] ≥95% test coverage

---

#### Issue 6.4.7 — P03StreamingProcessor implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement streaming event processor to prevent OOM on large datasets (100K+ events).

**Dossier Reference**: Section 15.6.1 "Streaming with K0 Observability"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.histogram()`, `gauge()` |
| K0 Tracing | `k0/obs/tracing.py` | `TracerFactory.span()` for batch spans |

**Memory Thresholds (from dossier)**:

| Level | Threshold | Action |
|-------|-----------|--------|
| warning | 256 MB | Log warning via K0 Logging |
| throttle | 384 MB | Reduce batch size |
| critical | 480 MB | Pause and GC |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/streaming/processor.py`
2. [ ] Define `P03_MEMORY_THRESHOLDS` dict per dossier
3. [ ] Implement `P03StreamingProcessor` class
4. [ ] Implement `process_events_streaming(events, batch_size=100)`
5. [ ] Add K0 trace spans for each batch
6. [ ] Add `p03_batch_size` histogram metric
7. [ ] Add memory pressure reporting to K0 gauge
8. [ ] Implement memory release after each batch
9. [ ] Implement throttle/pause logic on threshold breach
10. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/streaming/processor.py
"""
P03 streaming event processor with K0 observability.

Processes events in batches to prevent OOM on large datasets.
Implements memory thresholds with K0 metrics reporting.

Dossier Reference: Section 15.6.1 Streaming with K0 Observability
K0 References:
- k0/obs/metrics.py: MetricsExporter.histogram(), gauge()
- k0/obs/tracing.py: TracerFactory.span()
"""

from __future__ import annotations

import gc
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import TracerFactory

if TYPE_CHECKING:
    from k0.pipelines.p03.models import HippEvent


# Memory thresholds from dossier Section 15.6.1
P03_MEMORY_THRESHOLDS = {
    "warning_mb": 256,      # Log warning via K0 Logging
    "throttle_mb": 384,     # Reduce batch size
    "critical_mb": 480,     # Pause and GC
}

# Throttle factors for memory pressure
THROTTLE_FACTORS = {
    "warning": 0.75,   # Reduce batch by 25%
    "throttle": 0.5,   # Reduce batch by 50%
    "critical": 0.25,  # Reduce batch by 75%
}


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Result from processing a single batch."""

    batch_num: int
    events_processed: int
    memory_mb: float
    throttled: bool


class P03StreamingProcessor:
    """
    Streaming event processor with K0 observability.

    Processes events in batches to prevent OOM on large datasets.
    Reports memory pressure and batch metrics to K0.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.histogram(), gauge()
    - k0/obs/tracing.py: TracerFactory.span()
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        tracer: TracerFactory,
        base_batch_size: int = 100,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize streaming processor.

        Args:
            metrics: K0 MetricsExporter instance
            tracer: K0 TracerFactory instance
            base_batch_size: Default batch size
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics
        self.tracer = tracer
        self.base_batch_size = base_batch_size
        self.pipeline_id = pipeline_id

        self._current_batch_size = base_batch_size
        self._batch_count = 0
        self._total_processed = 0

    async def process_events_streaming(
        self,
        events: AsyncIterator[HippEvent],
        batch_size: int | None = None,
    ) -> int:
        """
        Process events in streaming fashion with K0 metrics.

        Processes events in batches, releasing memory after each.
        Automatically throttles batch size on memory pressure.

        Args:
            events: Async iterator of events to process
            batch_size: Override batch size (uses base if None)

        Returns:
            Total events processed
        """
        if batch_size is not None:
            self._current_batch_size = batch_size
        else:
            self._current_batch_size = self.base_batch_size

        self._batch_count = 0
        self._total_processed = 0

        batch: list[HippEvent] = []

        async for event in events:
            batch.append(event)

            if len(batch) >= self._current_batch_size:
                result = await self._process_batch(batch)
                self._adjust_batch_size(result)
                batch = []  # Release memory

        # Process remaining events
        if batch:
            await self._process_batch(batch)

        return self._total_processed

    async def _process_batch(
        self,
        batch: list[HippEvent],
    ) -> BatchResult:
        """
        Process a single batch with K0 tracing.

        Args:
            batch: Events to process

        Returns:
            BatchResult with metrics
        """
        with self.tracer.span(
            name="p03.process_batch",
            attributes={
                "batch_size": len(batch),
                "batch_num": self._batch_count,
                "pipeline_id": self.pipeline_id,
            },
        ):
            # Process batch (implementation in subclass)
            await self._do_process(batch)

            # K0 metrics: batch size histogram
            self.metrics.histogram(
                name="p03_batch_size",
                value=len(batch),
                labels={"phase": "streaming", "pipeline_id": self.pipeline_id},
            )

            # Get memory usage
            memory_mb = self._get_process_memory_mb()

            # K0 metrics: memory gauge
            self.metrics.gauge(
                name="p03_memory_mb",
                value=memory_mb,
                labels={"stage": "streaming"},
            )

            # Check memory pressure
            throttled = await self._handle_memory_pressure(memory_mb)

            self._batch_count += 1
            self._total_processed += len(batch)

            return BatchResult(
                batch_num=self._batch_count,
                events_processed=len(batch),
                memory_mb=memory_mb,
                throttled=throttled,
            )

    async def _do_process(self, batch: list[HippEvent]) -> None:
        """Process batch. Override in subclass."""
        pass

    async def _handle_memory_pressure(
        self,
        memory_mb: float,
    ) -> bool:
        """
        Handle memory pressure based on thresholds.

        Args:
            memory_mb: Current memory usage

        Returns:
            True if throttled
        """
        if memory_mb >= P03_MEMORY_THRESHOLDS["critical_mb"]:
            # Critical: pause and GC
            gc.collect()
            return True
        elif memory_mb >= P03_MEMORY_THRESHOLDS["throttle_mb"]:
            return True
        elif memory_mb >= P03_MEMORY_THRESHOLDS["warning_mb"]:
            # Just warning, no throttle
            return False
        return False

    def _adjust_batch_size(self, result: BatchResult) -> None:
        """Adjust batch size based on memory pressure."""
        if result.memory_mb >= P03_MEMORY_THRESHOLDS["critical_mb"]:
            factor = THROTTLE_FACTORS["critical"]
        elif result.memory_mb >= P03_MEMORY_THRESHOLDS["throttle_mb"]:
            factor = THROTTLE_FACTORS["throttle"]
        elif result.memory_mb >= P03_MEMORY_THRESHOLDS["warning_mb"]:
            factor = THROTTLE_FACTORS["warning"]
        else:
            # No pressure, restore base
            self._current_batch_size = self.base_batch_size
            return

        self._current_batch_size = max(
            10,  # Minimum batch size
            int(self.base_batch_size * factor),
        )

    def _get_process_memory_mb(self) -> float:
        """Get current process memory in MB."""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return usage.ru_maxrss / 1024
        except Exception:
            return 0.0
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/streaming/test_processor.py
"""Tests for P03 streaming processor."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from k0.obs.metrics import MetricsExporter
from k0.obs.tracing import TracerFactory


class TestP03StreamingProcessor:
    """Test streaming event processor."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MagicMock(spec=MetricsExporter)

    @pytest.fixture
    def tracer_factory(self) -> TracerFactory:
        """Create tracer factory."""
        tracer = MagicMock(spec=TracerFactory)
        tracer.span.return_value.__enter__ = MagicMock()
        tracer.span.return_value.__exit__ = MagicMock()
        return tracer

    @pytest.mark.asyncio
    async def test_process_events_streaming(
        self, metrics_exporter, tracer_factory
    ) -> None:
        """Events processed in batches."""
        from k0.pipelines.p03.streaming.processor import (
            P03StreamingProcessor,
        )

        processor = P03StreamingProcessor(
            metrics_exporter,
            tracer_factory,
            base_batch_size=10,
        )

        async def event_generator():
            for i in range(25):
                yield MagicMock(event_id=f"evt_{i}")

        total = await processor.process_events_streaming(event_generator())

        assert total == 25
        assert processor._batch_count == 3  # 10 + 10 + 5

    @pytest.mark.asyncio
    async def test_memory_threshold_throttle(
        self, metrics_exporter, tracer_factory
    ) -> None:
        """High memory triggers throttle."""
        from k0.pipelines.p03.streaming.processor import (
            P03StreamingProcessor,
            P03_MEMORY_THRESHOLDS,
        )

        processor = P03StreamingProcessor(
            metrics_exporter,
            tracer_factory,
            base_batch_size=100,
        )

        # Simulate high memory
        processor._get_process_memory_mb = MagicMock(return_value=400.0)

        throttled = await processor._handle_memory_pressure(400.0)

        assert throttled is True

    @pytest.mark.asyncio
    async def test_memory_threshold_critical_gc(
        self, metrics_exporter, tracer_factory
    ) -> None:
        """Critical memory triggers GC."""
        from k0.pipelines.p03.streaming.processor import (
            P03StreamingProcessor,
        )

        processor = P03StreamingProcessor(
            metrics_exporter,
            tracer_factory,
        )

        # Mock GC
        import gc
        gc.collect = MagicMock()

        throttled = await processor._handle_memory_pressure(490.0)

        assert throttled is True
        gc.collect.assert_called_once()

    def test_adjust_batch_size_on_pressure(
        self, metrics_exporter, tracer_factory
    ) -> None:
        """Batch size reduced on memory pressure."""
        from k0.pipelines.p03.streaming.processor import (
            P03StreamingProcessor,
            BatchResult,
        )

        processor = P03StreamingProcessor(
            metrics_exporter,
            tracer_factory,
            base_batch_size=100,
        )

        result = BatchResult(
            batch_num=0,
            events_processed=100,
            memory_mb=400.0,  # Throttle level
            throttled=True,
        )

        processor._adjust_batch_size(result)

        assert processor._current_batch_size == 50  # 100 * 0.5
```

**Acceptance Criteria**:

- [ ] `P03StreamingProcessor` uses K0 `MetricsExporter` and `TracerFactory`
- [ ] `process_events_streaming()` processes events in batches
- [ ] Memory released after each batch (batch = [])
- [ ] K0 trace span per batch with `p03.process_batch` name
- [ ] `p03_batch_size` histogram records batch sizes
- [ ] `p03_memory_mb` gauge updated after each batch
- [ ] Memory thresholds: warning=256MB, throttle=384MB, critical=480MB
- [ ] Critical threshold triggers GC
- [ ] Batch size auto-throttled on pressure
- [ ] Streaming processes 100K+ events without OOM
- [ ] ≥95% test coverage

---

#### Issue 6.4.8 — P03EmbeddingCache implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement LRU cache for embeddings to reduce FAISS query load with K0 metrics reporting.

**Dossier Reference**: Section 15.6.2 "Embedding Caching with K0 Metrics"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.counter()` for hit/miss |

**Cache Configuration (from dossier)**:

| Setting | Value | Description |
|---------|-------|-------------|
| max_size | 10000 | Maximum entries |
| ttl_seconds | 3600 | 1 hour TTL |

**Cache Priority Levels**:

| Priority | Type | Behavior |
|----------|------|----------|
| HIGH | cluster_centroids | Always cache |
| MEDIUM | recent_patterns | Cache for 1 hour |
| LOW | archived_patterns | Don't cache |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/cache/embedding_cache.py`
2. [ ] Define `P03_CACHE_PRIORITIES` dict per dossier
3. [ ] Implement `P03EmbeddingCache` class with LRU eviction
4. [ ] Implement `get(key)` with TTL check and K0 metrics
5. [ ] Implement `set(key, value)` with LRU eviction
6. [ ] Add `p03_embedding_cache_hit` Counter
7. [ ] Add `p03_embedding_cache_miss` Counter
8. [ ] Add `p03_embedding_cache_eviction` Counter
9. [ ] Add `p03_embedding_cache_expired` Counter
10. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/cache/embedding_cache.py
"""
P03 LRU embedding cache with K0 metrics.

Caches embeddings to reduce FAISS query load.
Reports hit/miss/eviction metrics to K0.

Dossier Reference: Section 15.6.2 Embedding Caching with K0 Metrics
K0 Reference: k0/obs/metrics.py: MetricsExporter.counter()
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Counter


# Cache priority levels from dossier Section 15.6.2
P03_CACHE_PRIORITIES = {
    "cluster_centroids": "HIGH",      # Always cache
    "recent_patterns": "MEDIUM",      # Cache for 1 hour
    "archived_patterns": "LOW",       # Don't cache
}


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cache entry with timestamp."""

    value: np.ndarray
    timestamp: float
    priority: str


class P03EmbeddingCache:
    """
    LRU cache for embeddings with K0 metrics.

    Implements LRU eviction with TTL expiration.
    Reports cache metrics to K0 MetricsExporter.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for hit/miss
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        max_size: int = 10000,
        ttl_seconds: int = 3600,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize embedding cache.

        Args:
            metrics: K0 MetricsExporter instance
            max_size: Maximum cache entries
            ttl_seconds: TTL in seconds (default 1 hour)
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.pipeline_id = pipeline_id

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # K0 metrics
        self._hit_counter: Counter = metrics.counter(
            name="p03_embedding_cache_hit",
            description="Cache hits",
            labelnames=["cache", "pipeline_id"],
        )
        self._miss_counter: Counter = metrics.counter(
            name="p03_embedding_cache_miss",
            description="Cache misses",
            labelnames=["cache", "pipeline_id"],
        )
        self._eviction_counter: Counter = metrics.counter(
            name="p03_embedding_cache_eviction",
            description="LRU evictions",
            labelnames=["cache", "pipeline_id"],
        )
        self._expired_counter: Counter = metrics.counter(
            name="p03_embedding_cache_expired",
            description="TTL expirations",
            labelnames=["cache", "pipeline_id"],
        )

    async def get(self, key: str) -> np.ndarray | None:
        """
        Get embedding from cache with K0 metrics.

        Args:
            key: Cache key

        Returns:
            Embedding array or None if miss/expired
        """
        if key not in self._cache:
            self._miss_counter.labels(
                cache="embedding",
                pipeline_id=self.pipeline_id,
            ).inc()
            return None

        entry = self._cache[key]

        # Check TTL (except HIGH priority)
        if entry.priority != "HIGH" and self._is_expired(entry):
            del self._cache[key]
            self._expired_counter.labels(
                cache="embedding",
                pipeline_id=self.pipeline_id,
            ).inc()
            return None

        # Hit - move to end for LRU
        self._cache.move_to_end(key)
        self._hit_counter.labels(
            cache="embedding",
            pipeline_id=self.pipeline_id,
        ).inc()

        return entry.value

    async def set(
        self,
        key: str,
        value: np.ndarray,
        priority: str = "MEDIUM",
    ) -> None:
        """
        Set embedding in cache.

        Args:
            key: Cache key
            value: Embedding array
            priority: Cache priority (HIGH/MEDIUM/LOW)
        """
        # Skip LOW priority
        if priority == "LOW":
            return

        # Evict if full
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._eviction_counter.labels(
                cache="embedding",
                pipeline_id=self.pipeline_id,
            ).inc()

        self._cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            priority=priority,
        )

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if entry is expired."""
        age = time.time() - entry.timestamp
        return age > self.ttl_seconds

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Current cache size."""
        return len(self._cache)

    def get_priority(self, pattern_type: str) -> str:
        """
        Get cache priority for pattern type.

        Args:
            pattern_type: Type of pattern

        Returns:
            Priority level
        """
        return P03_CACHE_PRIORITIES.get(pattern_type, "MEDIUM")
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/cache/test_embedding_cache.py
"""Tests for P03 embedding cache."""

import pytest
import numpy as np
from unittest.mock import MagicMock

from k0.obs.metrics import MetricsExporter


class TestP03EmbeddingCache:
    """Test LRU embedding cache."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MagicMock(spec=MetricsExporter)

    @pytest.mark.asyncio
    async def test_cache_hit(self, metrics_exporter) -> None:
        """Cache hit returns value and records metric."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )

        cache = P03EmbeddingCache(metrics_exporter, max_size=100)

        embedding = np.array([1.0, 2.0, 3.0])
        await cache.set("key1", embedding)

        result = await cache.get("key1")

        assert result is not None
        np.testing.assert_array_equal(result, embedding)

    @pytest.mark.asyncio
    async def test_cache_miss(self, metrics_exporter) -> None:
        """Cache miss returns None and records metric."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )

        cache = P03EmbeddingCache(metrics_exporter)

        result = await cache.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self, metrics_exporter) -> None:
        """LRU eviction when cache full."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )

        cache = P03EmbeddingCache(metrics_exporter, max_size=2)

        await cache.set("key1", np.array([1.0]))
        await cache.set("key2", np.array([2.0]))
        await cache.set("key3", np.array([3.0]))  # Evicts key1

        assert await cache.get("key1") is None
        assert await cache.get("key2") is not None
        assert await cache.get("key3") is not None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, metrics_exporter) -> None:
        """TTL expiration removes stale entries."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )
        import time

        cache = P03EmbeddingCache(metrics_exporter, ttl_seconds=1)

        await cache.set("key1", np.array([1.0]))

        # Simulate time passing
        cache._cache["key1"] = cache._cache["key1"].__class__(
            value=cache._cache["key1"].value,
            timestamp=time.time() - 2,  # 2 seconds ago
            priority=cache._cache["key1"].priority,
        )

        result = await cache.get("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_high_priority_no_ttl(self, metrics_exporter) -> None:
        """HIGH priority entries don't expire."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )
        import time

        cache = P03EmbeddingCache(metrics_exporter, ttl_seconds=1)

        await cache.set("key1", np.array([1.0]), priority="HIGH")

        # Simulate time passing
        cache._cache["key1"] = cache._cache["key1"].__class__(
            value=cache._cache["key1"].value,
            timestamp=time.time() - 2,  # 2 seconds ago
            priority="HIGH",
        )

        result = await cache.get("key1")

        assert result is not None  # HIGH priority doesn't expire

    @pytest.mark.asyncio
    async def test_low_priority_skipped(self, metrics_exporter) -> None:
        """LOW priority entries not cached."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )

        cache = P03EmbeddingCache(metrics_exporter)

        await cache.set("key1", np.array([1.0]), priority="LOW")

        assert cache.size == 0

    def test_get_priority(self, metrics_exporter) -> None:
        """Priority levels map correctly."""
        from k0.pipelines.p03.cache.embedding_cache import (
            P03EmbeddingCache,
        )

        cache = P03EmbeddingCache(metrics_exporter)

        assert cache.get_priority("cluster_centroids") == "HIGH"
        assert cache.get_priority("recent_patterns") == "MEDIUM"
        assert cache.get_priority("archived_patterns") == "LOW"
        assert cache.get_priority("unknown") == "MEDIUM"
```

**Acceptance Criteria**:

- [ ] `P03EmbeddingCache` uses K0 `MetricsExporter`
- [ ] LRU eviction when `max_size` exceeded
- [ ] TTL expiration enforced (except HIGH priority)
- [ ] `p03_embedding_cache_hit` Counter recorded on hit
- [ ] `p03_embedding_cache_miss` Counter recorded on miss
- [ ] `p03_embedding_cache_eviction` Counter recorded on eviction
- [ ] `p03_embedding_cache_expired` Counter recorded on expiration
- [ ] HIGH priority entries never expire
- [ ] LOW priority entries never cached
- [ ] `P03_CACHE_PRIORITIES` matches dossier values
- [ ] ≥95% test coverage

---

#### Issue 6.4.9 — P03EmbeddingQueryOptimizer implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement two-stage retrieval (FAISS ANN + cosine re-ranking) with K0 QoS budget tracking.

**Dossier Reference**: Section 15.5 "Embedding Query Optimization (K0-Aware)"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 QoSContext | `k0/qos/context.py` | `consume_top_k()` budget tracking |
| K0 CapabilityFabric | `k0/fabric/fabric.py` | `invoke()` for P08 embedding search |
| K0 FAISS Driver | `k0/drivers/faiss_driver.py` | FAISS ANN search |

**Two-Stage Retrieval Strategy (from dossier)**:

| Stage | Method | Purpose |
|-------|--------|---------|
| Stage 1 | FAISS ANN | Fast, approximate (3x over-retrieve) |
| Stage 2 | Cosine re-rank | Accurate, exact scoring |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/qos/query_optimizer.py`
2. [ ] Define `QoSBudgetExceededError` exception
3. [ ] Implement `P03EmbeddingQueryOptimizer` class
4. [ ] Implement `query_similar_patterns(embedding, top_k=10)`
5. [ ] Check K0 `QoSContext.top_k_budget` before query
6. [ ] Call K0 `CapabilityFabric.invoke()` for Stage 1 search
7. [ ] Consume budget via `QoSContext.consume_top_k()`
8. [ ] Implement `_rerank_by_exact_cosine()` for Stage 2
9. [ ] Raise `QoSBudgetExceededError` if insufficient budget
10. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/qos/query_optimizer.py
"""
P03 embedding query optimizer with K0 QoS integration.

Two-stage retrieval: FAISS ANN + cosine re-ranking.
Tracks budget via K0 QoSContext.

Dossier Reference: Section 15.5 Embedding Query Optimization (K0-Aware)
K0 References:
- k0/qos/context.py: QoSContext.consume_top_k()
- k0/fabric/fabric.py: CapabilityFabric.invoke()
- k0/drivers/faiss_driver.py: FAISS search
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from k0.fabric.fabric import CapabilityFabric
from k0.qos.context import QoSContext

if TYPE_CHECKING:
    from collections.abc import Sequence


class QoSBudgetExceededError(Exception):
    """Raised when QoS budget insufficient for operation."""

    pass


@dataclass(frozen=True, slots=True)
class PatternMatch:
    """Pattern match result."""

    pattern_id: str
    score: float
    embedding: np.ndarray | None = None
    metadata: dict | None = None


# Over-retrieve factor for re-ranking quality
OVER_RETRIEVE_FACTOR = 3


class P03EmbeddingQueryOptimizer:
    """
    Optimize similarity queries with K0 QoS awareness.

    Two-stage retrieval:
    - Stage 1: FAISS ANN via K0 CapabilityFabric (fast, 3x over-retrieve)
    - Stage 2: Exact cosine similarity for re-ranking (accurate)

    K0 References:
    - k0/qos/context.py: QoSContext.consume_top_k()
    - k0/fabric/fabric.py: CapabilityFabric.invoke() for P08 embedding
    - k0/drivers/faiss_driver.py: FAISS search operations
    """

    def __init__(
        self,
        qos_ctx: QoSContext,
        fabric: CapabilityFabric,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize query optimizer.

        Args:
            qos_ctx: K0 QoSContext for budget tracking
            fabric: K0 CapabilityFabric for embedding search
            pipeline_id: Pipeline identifier for context
        """
        self.qos_ctx = qos_ctx
        self.fabric = fabric
        self.pipeline_id = pipeline_id

    async def query_similar_patterns(
        self,
        query_embedding: np.ndarray,
        top_k: int = 10,
    ) -> list[PatternMatch]:
        """
        Two-stage retrieval with K0 QoS budget tracking.

        Stage 1: FAISS ANN via K0 CapabilityFabric (fast, approximate)
        Stage 2: Exact cosine similarity for re-ranking (accurate)

        Args:
            query_embedding: Query vector
            top_k: Number of results to return

        Returns:
            Top-k pattern matches

        Raises:
            QoSBudgetExceededError: If insufficient top_k budget
        """
        # Calculate over-retrieve amount
        over_retrieve_k = top_k * OVER_RETRIEVE_FACTOR

        # Check K0 top_k budget before query
        if self.qos_ctx.top_k_budget < over_retrieve_k:
            # Reduce to available budget
            over_retrieve_k = self.qos_ctx.top_k_budget

        if over_retrieve_k < top_k:
            raise QoSBudgetExceededError(
                f"Insufficient top_k budget: need {top_k}, have {over_retrieve_k}"
            )

        # Stage 1: ANN search via K0 CapabilityFabric
        # This invokes P08 embedding management pipeline
        candidates = await self.fabric.invoke(
            capability="embedding.search",
            context={"pipeline_id": self.pipeline_id},
            query_vector=query_embedding.tolist(),
            top_k=over_retrieve_k,
        )

        # Consume K0 QoS budget
        self.qos_ctx.consume_top_k(len(candidates))

        # Stage 2: Exact re-ranking
        ranked = self._rerank_by_exact_cosine(query_embedding, candidates)

        return ranked[:top_k]

    def _rerank_by_exact_cosine(
        self,
        query: np.ndarray,
        candidates: Sequence[dict],
    ) -> list[PatternMatch]:
        """
        Re-rank candidates using exact cosine similarity.

        Args:
            query: Query embedding
            candidates: Candidate results from Stage 1

        Returns:
            Sorted PatternMatch list
        """
        scored: list[tuple[float, dict]] = []

        for c in candidates:
            vec = np.array(c.get("embedding", []))
            if vec.size == 0:
                continue

            # Cosine similarity
            query_norm = np.linalg.norm(query)
            vec_norm = np.linalg.norm(vec)

            if query_norm == 0 or vec_norm == 0:
                score = 0.0
            else:
                score = float(np.dot(query, vec) / (query_norm * vec_norm))

            scored.append((score, c))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            PatternMatch(
                pattern_id=c.get("pattern_id", ""),
                score=s,
                embedding=np.array(c.get("embedding", [])),
                metadata=c.get("metadata"),
            )
            for s, c in scored
        ]
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/qos/test_query_optimizer.py
"""Tests for P03 embedding query optimizer."""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock

from k0.qos.context import QoSContext
from k0.fabric.fabric import CapabilityFabric


class TestP03EmbeddingQueryOptimizer:
    """Test two-stage retrieval optimizer."""

    @pytest.fixture
    def qos_context(self) -> QoSContext:
        """Create QoS context with budget."""
        ctx = MagicMock(spec=QoSContext)
        ctx.top_k_budget = 100
        return ctx

    @pytest.fixture
    def capability_fabric(self) -> CapabilityFabric:
        """Create capability fabric."""
        fabric = MagicMock(spec=CapabilityFabric)
        fabric.invoke = AsyncMock(return_value=[
            {"pattern_id": "p1", "embedding": [1.0, 0.0, 0.0]},
            {"pattern_id": "p2", "embedding": [0.9, 0.1, 0.0]},
            {"pattern_id": "p3", "embedding": [0.0, 1.0, 0.0]},
        ])
        return fabric

    @pytest.mark.asyncio
    async def test_query_similar_patterns(
        self, qos_context, capability_fabric
    ) -> None:
        """Two-stage retrieval returns ranked matches."""
        from k0.pipelines.p03.qos.query_optimizer import (
            P03EmbeddingQueryOptimizer,
        )

        optimizer = P03EmbeddingQueryOptimizer(qos_context, capability_fabric)

        query = np.array([1.0, 0.0, 0.0])
        results = await optimizer.query_similar_patterns(query, top_k=2)

        assert len(results) == 2
        assert results[0].pattern_id == "p1"  # Exact match
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_over_retrieve_factor(
        self, qos_context, capability_fabric
    ) -> None:
        """Over-retrieve 3x for re-ranking."""
        from k0.pipelines.p03.qos.query_optimizer import (
            P03EmbeddingQueryOptimizer,
            OVER_RETRIEVE_FACTOR,
        )

        optimizer = P03EmbeddingQueryOptimizer(qos_context, capability_fabric)

        query = np.array([1.0, 0.0, 0.0])
        await optimizer.query_similar_patterns(query, top_k=10)

        # Should request 30 (10 * 3)
        capability_fabric.invoke.assert_called_once()
        call_kwargs = capability_fabric.invoke.call_args.kwargs
        assert call_kwargs["top_k"] == 30

    @pytest.mark.asyncio
    async def test_budget_consumed(
        self, qos_context, capability_fabric
    ) -> None:
        """Budget consumed via QoSContext."""
        from k0.pipelines.p03.qos.query_optimizer import (
            P03EmbeddingQueryOptimizer,
        )

        optimizer = P03EmbeddingQueryOptimizer(qos_context, capability_fabric)

        query = np.array([1.0, 0.0, 0.0])
        await optimizer.query_similar_patterns(query, top_k=10)

        qos_context.consume_top_k.assert_called_once_with(3)  # 3 candidates

    @pytest.mark.asyncio
    async def test_insufficient_budget_error(
        self, capability_fabric
    ) -> None:
        """Raises QoSBudgetExceededError if budget insufficient."""
        from k0.pipelines.p03.qos.query_optimizer import (
            P03EmbeddingQueryOptimizer,
            QoSBudgetExceededError,
        )

        qos_ctx = MagicMock(spec=QoSContext)
        qos_ctx.top_k_budget = 5  # Less than top_k=10

        optimizer = P03EmbeddingQueryOptimizer(qos_ctx, capability_fabric)

        query = np.array([1.0, 0.0, 0.0])

        with pytest.raises(QoSBudgetExceededError):
            await optimizer.query_similar_patterns(query, top_k=10)

    def test_rerank_by_exact_cosine(self, qos_context, capability_fabric) -> None:
        """Cosine re-ranking sorts correctly."""
        from k0.pipelines.p03.qos.query_optimizer import (
            P03EmbeddingQueryOptimizer,
        )

        optimizer = P03EmbeddingQueryOptimizer(qos_context, capability_fabric)

        query = np.array([1.0, 0.0, 0.0])
        candidates = [
            {"pattern_id": "p1", "embedding": [0.5, 0.5, 0.0]},
            {"pattern_id": "p2", "embedding": [1.0, 0.0, 0.0]},  # Best
            {"pattern_id": "p3", "embedding": [0.0, 1.0, 0.0]},
        ]

        ranked = optimizer._rerank_by_exact_cosine(query, candidates)

        assert ranked[0].pattern_id == "p2"  # Best match
        assert ranked[0].score == pytest.approx(1.0, rel=1e-6)
```

**Acceptance Criteria**:

- [ ] `P03EmbeddingQueryOptimizer` uses K0 `QoSContext` and `CapabilityFabric`
- [ ] Stage 1: FAISS ANN via `CapabilityFabric.invoke()`
- [ ] Over-retrieve 3x (`top_k * 3`) for quality
- [ ] Budget checked before query
- [ ] Budget consumed via `QoSContext.consume_top_k()`
- [ ] Stage 2: Exact cosine re-ranking
- [ ] `QoSBudgetExceededError` raised if budget < top_k
- [ ] Re-ranking improves precision
- [ ] ≥95% test coverage

---

#### Issue 6.4.10 — PostgreSQL session optimization

**Status**: 🔲 NOT STARTED

**Goal**: Implement PostgreSQL session settings for P03 performance optimization.

**Dossier Reference**: Section 15.7.2 "PostgreSQL Configuration (K0 Kernel Config)"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 PostgresSettings | `k0/config/postgres.py` | Pool sizes, SSL, statement cache |
| K0 AsyncPgPool | `k0/db/pool.py` | Connection pool with pgbouncer |
| K0 PostgresDriver | `k0/drivers/postgres.py` | ACID transactions |

**Session Settings (from dossier)**:

| Setting | Value | Description |
|---------|-------|-------------|
| statement_timeout | 300s | 5 min max for consolidation |
| lock_timeout | 30s | Max wait for row locks |
| idle_in_transaction_session_timeout | 60s | Prevent stuck transactions |
| work_mem | 256MB | Per-operation memory |
| maintenance_work_mem | 512MB | For ANALYZE operations |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/db/session_config.py`
2. [ ] Define `P03_POSTGRES_SESSION_SETTINGS` dict per dossier
3. [ ] Implement `P03DatabaseConfig` class
4. [ ] Implement `from_k0_settings(pg_settings)` factory
5. [ ] Implement `get_session_settings()` returning SET commands
6. [ ] Implement `apply_session_settings(conn)` for connection setup
7. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/db/session_config.py
"""
P03 PostgreSQL session configuration.

Optimizes PostgreSQL sessions for P03 consolidation workload.
Integrates with K0 PostgresSettings.

Dossier Reference: Section 15.7.2 PostgreSQL Configuration (K0 Kernel Config)
K0 References:
- k0/config/postgres.py: PostgresSettings
- k0/db/pool.py: AsyncPgPool
- k0/drivers/postgres.py: PostgresDriver
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

    from k0.config.postgres import PostgresSettings


# P03-optimized PostgreSQL session settings from dossier Section 15.7.2
P03_POSTGRES_SESSION_SETTINGS = {
    "statement_timeout": "300s",  # 5 min max for consolidation queries
    "lock_timeout": "30s",  # 30s max wait for row locks
    "idle_in_transaction_session_timeout": "60s",  # Prevent stuck transactions
    "work_mem": "256MB",  # Per-operation memory for sorts/hashes
    "maintenance_work_mem": "512MB",  # For ANALYZE operations
}


@dataclass(frozen=True, slots=True)
class PoolConfig:
    """Pool configuration derived from K0 settings."""

    min_pool_size: int
    max_pool_size: int
    command_timeout: float
    statement_cache_size: int
    vector_dimensions: int


class P03DatabaseConfig:
    """
    Database configuration aligned with K0 PostgreSQL Settings.

    K0 References:
    - k0/config/postgres.py: PostgresSettings (host, port, pool sizes, SSL)
    - k0/db/pool.py: AsyncPgPool (asyncpg connection pool with pgbouncer)
    - k0/drivers/postgres.py: PostgresDriver (ACID transactions)
    """

    def __init__(
        self,
        session_settings: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize database config.

        Args:
            session_settings: Override session settings (defaults to dossier)
        """
        self.session_settings = session_settings or P03_POSTGRES_SESSION_SETTINGS

    @classmethod
    def from_k0_settings(
        cls,
        pg_settings: PostgresSettings,
    ) -> PoolConfig:
        """
        Build P03 PostgreSQL config from K0 PostgresSettings.

        Args:
            pg_settings: K0 PostgresSettings instance

        Returns:
            PoolConfig with K0-derived settings
        """
        return PoolConfig(
            min_pool_size=pg_settings.min_pool_size,  # Default: 5
            max_pool_size=pg_settings.max_pool_size,  # Default: 25
            command_timeout=pg_settings.command_timeout,  # Default: 60.0s
            statement_cache_size=pg_settings.statement_cache_size,  # 0 for pgbouncer
            vector_dimensions=pg_settings.vector_dimensions,  # 768 for UltraBERT
        )

    def get_session_settings(self) -> dict[str, str]:
        """
        Get session settings for P03 optimization.

        Returns:
            Dict of PostgreSQL SET parameter -> value
        """
        return dict(self.session_settings)

    def get_set_commands(self) -> list[str]:
        """
        Get SET commands for session initialization.

        Returns:
            List of SET commands to execute
        """
        return [
            f"SET {key} = '{value}'"
            for key, value in self.session_settings.items()
        ]

    async def apply_session_settings(
        self,
        conn: asyncpg.Connection,
    ) -> None:
        """
        Apply session settings to connection.

        Args:
            conn: asyncpg connection
        """
        for key, value in self.session_settings.items():
            await conn.execute(f"SET {key} = '{value}'")

    @staticmethod
    def get_connection_init_callback() -> callable:
        """
        Get callback for connection pool initialization.

        Returns:
            Async callback for asyncpg pool init
        """

        async def init_connection(conn: asyncpg.Connection) -> None:
            """Initialize connection with P03 settings."""
            config = P03DatabaseConfig()
            await config.apply_session_settings(conn)

        return init_connection
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/db/test_session_config.py
"""Tests for P03 PostgreSQL session configuration."""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestP03DatabaseConfig:
    """Test PostgreSQL session configuration."""

    def test_default_session_settings(self) -> None:
        """Default settings from dossier."""
        from k0.pipelines.p03.db.session_config import (
            P03DatabaseConfig,
            P03_POSTGRES_SESSION_SETTINGS,
        )

        config = P03DatabaseConfig()

        assert config.get_session_settings() == P03_POSTGRES_SESSION_SETTINGS

    def test_statement_timeout(self) -> None:
        """Statement timeout is 5 minutes."""
        from k0.pipelines.p03.db.session_config import (
            P03_POSTGRES_SESSION_SETTINGS,
        )

        assert P03_POSTGRES_SESSION_SETTINGS["statement_timeout"] == "300s"

    def test_lock_timeout(self) -> None:
        """Lock timeout is 30 seconds."""
        from k0.pipelines.p03.db.session_config import (
            P03_POSTGRES_SESSION_SETTINGS,
        )

        assert P03_POSTGRES_SESSION_SETTINGS["lock_timeout"] == "30s"

    def test_work_mem(self) -> None:
        """Work mem is 256MB."""
        from k0.pipelines.p03.db.session_config import (
            P03_POSTGRES_SESSION_SETTINGS,
        )

        assert P03_POSTGRES_SESSION_SETTINGS["work_mem"] == "256MB"

    def test_from_k0_settings(self) -> None:
        """PoolConfig from K0 PostgresSettings."""
        from k0.pipelines.p03.db.session_config import (
            P03DatabaseConfig,
        )

        pg_settings = MagicMock()
        pg_settings.min_pool_size = 5
        pg_settings.max_pool_size = 25
        pg_settings.command_timeout = 60.0
        pg_settings.statement_cache_size = 0
        pg_settings.vector_dimensions = 768

        pool_config = P03DatabaseConfig.from_k0_settings(pg_settings)

        assert pool_config.min_pool_size == 5
        assert pool_config.max_pool_size == 25
        assert pool_config.vector_dimensions == 768

    def test_get_set_commands(self) -> None:
        """SET commands generated correctly."""
        from k0.pipelines.p03.db.session_config import (
            P03DatabaseConfig,
        )

        config = P03DatabaseConfig()
        commands = config.get_set_commands()

        assert any("statement_timeout" in cmd for cmd in commands)
        assert any("300s" in cmd for cmd in commands)

    @pytest.mark.asyncio
    async def test_apply_session_settings(self) -> None:
        """Settings applied to connection."""
        from k0.pipelines.p03.db.session_config import (
            P03DatabaseConfig,
        )

        config = P03DatabaseConfig()
        conn = AsyncMock()

        await config.apply_session_settings(conn)

        assert conn.execute.call_count == 5  # 5 settings

    def test_get_connection_init_callback(self) -> None:
        """Returns valid callback."""
        from k0.pipelines.p03.db.session_config import (
            P03DatabaseConfig,
        )

        callback = P03DatabaseConfig.get_connection_init_callback()

        assert callable(callback)
```

**Acceptance Criteria**:

- [ ] `P03DatabaseConfig` integrates with K0 `PostgresSettings`
- [ ] `P03_POSTGRES_SESSION_SETTINGS` matches dossier values
- [ ] `statement_timeout` = 300s (5 min)
- [ ] `lock_timeout` = 30s
- [ ] `idle_in_transaction_session_timeout` = 60s
- [ ] `work_mem` = 256MB
- [ ] `maintenance_work_mem` = 512MB
- [ ] `from_k0_settings()` extracts pool config from K0
- [ ] `apply_session_settings()` executes SET commands
- [ ] Connection init callback available for pool
- [ ] ≥95% test coverage

---

#### Issue 6.4.11 — LearningBudgetManager implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement learning budget enforcement (<5% of cycle time) with component breakdown.

**Dossier Reference**: Section 15.9 "Learning Compute Budget"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.counter()`, `histogram()` |
| K0 Logging | `k0/obs/logging.py` | Structured logging for budget warnings |

**Component Budget Breakdown (from dossier)**:

| Component | % of 5% Budget | Absolute Target |
|-----------|----------------|-----------------|
| feedback_ingestion | 20% (1% cycle) | < 10ms per signal |
| parameter_update | 30% (1.5% cycle) | < 50ms per update |
| quality_monitoring | 30% (1.5% cycle) | < 100ms per cycle |
| audit_logging | 20% (1% cycle) | < 20ms per record |

**Priority Levels**:

| Priority | Level | Skip Behavior |
|----------|-------|---------------|
| 1 | Critical | Execute anyway, log warning |
| 2 | High | Execute anyway, log warning |
| 3 | Medium | Skip if over budget |
| 4 | Low | Skip if over budget |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/qos/learning_budget.py`
2. [ ] Define `COMPONENT_BUDGET_FRACTIONS` per dossier
3. [ ] Implement `LearningBudgetManager` class
4. [ ] Implement `execute_with_budget(component, operation, priority)`
5. [ ] Implement `_timed_execute()` with latency tracking
6. [ ] Implement `get_budget_usage()` returning percentages
7. [ ] Implement `reset()` for new cycle
8. [ ] Add `p03_learning_skip_count` Counter integration
9. [ ] Add `p03_learning_latency_ms` Histogram integration
10. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/qos/learning_budget.py
"""
P03 learning budget manager.

Enforces <5% compute budget for learning operations.
Tracks time per component and skips low priority when exhausted.

Dossier Reference: Section 15.9 Learning Compute Budget
K0 References:
- k0/obs/metrics.py: MetricsExporter.counter(), histogram()
- k0/obs/logging.py: Structured logging
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from k0.obs.logging import get_logger
from k0.obs.metrics import MetricsExporter

T = TypeVar("T")

logger = get_logger(__name__)


# Component budget fractions from dossier Section 15.9
COMPONENT_BUDGET_FRACTIONS = {
    "feedback_ingestion": 0.20,  # 20% of 5% = 1% cycle
    "parameter_update": 0.30,   # 30% of 5% = 1.5% cycle
    "quality_monitoring": 0.30,  # 30% of 5% = 1.5% cycle
    "audit_logging": 0.20,       # 20% of 5% = 1% cycle
}

# Priority levels
PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 2
PRIORITY_MEDIUM = 3
PRIORITY_LOW = 4


@dataclass
class BudgetUsage:
    """Budget usage tracking."""

    component: str
    budget_ms: float
    spent_ms: float
    usage_pct: float


class LearningBudgetManager:
    """
    Enforce 5% compute budget for learning operations.

    Tracks time per component and skips low priority operations
    when budget exhausted.

    Dossier Reference: Section 15.9 Learning Compute Budget
    K0 References:
    - k0/obs/metrics.py: MetricsExporter for latency/skip metrics
    """

    def __init__(
        self,
        cycle_budget_ms: float,
        metrics: MetricsExporter,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize budget manager.

        Args:
            cycle_budget_ms: Total cycle time in ms
            metrics: K0 MetricsExporter instance
            pipeline_id: Pipeline identifier for labels
        """
        self.total_budget_ms = cycle_budget_ms * 0.05  # 5% of cycle
        self.pipeline_id = pipeline_id
        self.metrics = metrics

        # Component budgets
        self.component_budgets = {
            k: self.total_budget_ms * v
            for k, v in COMPONENT_BUDGET_FRACTIONS.items()
        }

        # Time spent tracking
        self.time_spent: dict[str, float] = {
            k: 0.0 for k in self.component_budgets
        }

        # K0 metrics
        self._skip_counter = metrics.counter(
            name="p03_learning_skip_count",
            description="Operations skipped due to budget constraints",
            labelnames=["component", "reason", "pipeline_id"],
        )

        self._latency_histogram = metrics.histogram(
            name="p03_learning_latency_ms",
            description="Latency of learning operations in milliseconds",
            labelnames=["component", "operation", "pipeline_id"],
            buckets=[1, 5, 10, 20, 50, 100, 200, 500, 1000],
        )

    async def execute_with_budget(
        self,
        component: str,
        operation: Callable[[], Awaitable[T]],
        priority: int,
        operation_name: str = "default",
    ) -> T | None:
        """
        Execute operation if budget allows.

        Priority:
        1 = Critical (quality monitoring)
        2 = High (parameter update)
        3 = Medium (audit logging)
        4 = Low (feedback ingestion)

        Args:
            component: Component name
            operation: Async operation to execute
            priority: Priority level (1-4)
            operation_name: Name for metrics

        Returns:
            Operation result or None if skipped
        """
        budget = self.component_budgets.get(component, 0.0)
        spent = self.time_spent.get(component, 0.0)

        if spent >= budget:
            # Budget exhausted
            if priority <= PRIORITY_HIGH:
                # Critical/High: Execute anyway, log warning
                logger.warning(
                    "learning_budget_exceeded",
                    component=component,
                    spent_ms=spent,
                    budget_ms=budget,
                    priority=priority,
                )
                return await self._timed_execute(
                    component, operation, operation_name
                )
            else:
                # Medium/Low: Skip operation
                self._skip_counter.labels(
                    component=component,
                    reason="budget_exhausted",
                    pipeline_id=self.pipeline_id,
                ).inc()
                return None

        # Within budget: Execute
        return await self._timed_execute(
            component, operation, operation_name
        )

    async def _timed_execute(
        self,
        component: str,
        operation: Callable[[], Awaitable[T]],
        operation_name: str,
    ) -> T:
        """Execute operation and track time."""
        start = time.perf_counter()
        try:
            result = await operation()
            return result
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.time_spent[component] = (
                self.time_spent.get(component, 0.0) + duration_ms
            )
            self._latency_histogram.labels(
                component=component,
                operation=operation_name,
                pipeline_id=self.pipeline_id,
            ).observe(duration_ms)

    def get_budget_usage(self) -> dict[str, BudgetUsage]:
        """
        Return budget usage per component.

        Returns:
            Dict of component -> BudgetUsage
        """
        return {
            component: BudgetUsage(
                component=component,
                budget_ms=budget,
                spent_ms=self.time_spent.get(component, 0.0),
                usage_pct=(
                    self.time_spent.get(component, 0.0) / budget * 100
                    if budget > 0
                    else 0.0
                ),
            )
            for component, budget in self.component_budgets.items()
        }

    def get_total_usage_pct(self) -> float:
        """Return total learning time as percentage of cycle."""
        total_spent = sum(self.time_spent.values())
        return (total_spent / self.total_budget_ms * 5.0) if self.total_budget_ms > 0 else 0.0

    def reset(self) -> None:
        """Reset budget tracking for new cycle."""
        self.time_spent = {k: 0.0 for k in self.component_budgets}
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/qos/test_learning_budget.py
"""Tests for P03 learning budget manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from k0.obs.metrics import MetricsExporter


class TestLearningBudgetManager:
    """Test learning budget enforcement."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MagicMock(spec=MetricsExporter)

    @pytest.mark.asyncio
    async def test_execute_within_budget(self, metrics_exporter) -> None:
        """Operations within budget execute."""
        from k0.pipelines.p03.qos.learning_budget import (
            LearningBudgetManager,
        )

        mgr = LearningBudgetManager(
            cycle_budget_ms=10000,  # 10s cycle
            metrics=metrics_exporter,
        )

        result = await mgr.execute_with_budget(
            "feedback_ingestion",
            AsyncMock(return_value="done"),
            priority=4,
        )

        assert result == "done"

    @pytest.mark.asyncio
    async def test_skip_low_priority_over_budget(
        self, metrics_exporter
    ) -> None:
        """Low priority skipped when over budget."""
        from k0.pipelines.p03.qos.learning_budget import (
            LearningBudgetManager,
        )

        mgr = LearningBudgetManager(
            cycle_budget_ms=10000,
            metrics=metrics_exporter,
        )

        # Exhaust budget
        mgr.time_spent["feedback_ingestion"] = 200.0  # Over 100ms budget

        result = await mgr.execute_with_budget(
            "feedback_ingestion",
            AsyncMock(return_value="done"),
            priority=4,  # Low priority
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_critical_executes_over_budget(
        self, metrics_exporter
    ) -> None:
        """Critical priority executes even over budget."""
        from k0.pipelines.p03.qos.learning_budget import (
            LearningBudgetManager,
        )

        mgr = LearningBudgetManager(
            cycle_budget_ms=10000,
            metrics=metrics_exporter,
        )

        # Exhaust budget
        mgr.time_spent["quality_monitoring"] = 200.0

        result = await mgr.execute_with_budget(
            "quality_monitoring",
            AsyncMock(return_value="critical_done"),
            priority=1,  # Critical
        )

        assert result == "critical_done"

    def test_get_budget_usage(self, metrics_exporter) -> None:
        """Budget usage calculated correctly."""
        from k0.pipelines.p03.qos.learning_budget import (
            LearningBudgetManager,
        )

        mgr = LearningBudgetManager(
            cycle_budget_ms=10000,
            metrics=metrics_exporter,
        )

        mgr.time_spent["feedback_ingestion"] = 50.0

        usage = mgr.get_budget_usage()

        assert "feedback_ingestion" in usage
        assert usage["feedback_ingestion"].spent_ms == 50.0

    def test_reset(self, metrics_exporter) -> None:
        """Reset clears time spent."""
        from k0.pipelines.p03.qos.learning_budget import (
            LearningBudgetManager,
        )

        mgr = LearningBudgetManager(
            cycle_budget_ms=10000,
            metrics=metrics_exporter,
        )

        mgr.time_spent["feedback_ingestion"] = 50.0
        mgr.reset()

        assert mgr.time_spent["feedback_ingestion"] == 0.0
```

**Acceptance Criteria**:

- [ ] `LearningBudgetManager` enforces 5% total budget
- [ ] Component budgets match dossier breakdown
- [ ] Critical/High priority executes over budget with warning
- [ ] Medium/Low priority skipped when over budget
- [ ] `p03_learning_skip_count` incremented on skip
- [ ] `p03_learning_latency_ms` records operation duration
- [ ] `get_budget_usage()` returns per-component stats
- [ ] `reset()` clears for new cycle
- [ ] ≥95% test coverage

---

#### Issue 6.4.12 — Learning budget metrics

**Status**: 🔲 NOT STARTED

**Goal**: Implement comprehensive metrics for learning budget tracking per dossier specification.

**Dossier Reference**: Section 8.2.2 "Learning Performance Metrics"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.gauge()`, `counter()`, `histogram()` |

**Metrics to Implement (from dossier)**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `p03_learning_time_pct` | Gauge | space_id, component | % of cycle time |
| `p03_learning_latency_ms` | Histogram | component, operation | Operation latency |
| `p03_learning_queue_depth` | Gauge | space_id | Pending signals |
| `p03_learning_queue_overflow` | Counter | space_id | Discarded signals |
| `p03_learning_batch_size` | Histogram | operation | Signals per batch |
| `p03_learning_batch_duration_ms` | Histogram | operation | Batch duration |
| `p03_learning_skip_count` | Counter | component, reason | Skipped ops |
| `p03_learning_budget_exceeded` | Counter | space_id | Budget violations |
| `p03_learning_parameter_updates` | Counter | param_key, space_id | Param updates |
| `p03_audit_writes` | Counter | batch_size | Audit writes |
| `p03_audit_drops` | Counter | - | Dropped audits |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/obs/learning_metrics.py`
2. [ ] Implement `P03LearningMetrics` class
3. [ ] Create all gauge metrics per dossier
4. [ ] Create all counter metrics per dossier
5. [ ] Create all histogram metrics with correct buckets
6. [ ] Add helper methods for recording operations
7. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/obs/learning_metrics.py
"""
P03 learning performance metrics.

Comprehensive metrics for learning budget tracking.

Dossier Reference: Section 8.2.2 Learning Performance Metrics
K0 Reference: k0/obs/metrics.py: MetricsExporter
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram


class P03LearningMetrics:
    """
    Learning performance metrics using K0 MetricsExporter.

    Tracks budget usage, queue health, and operation performance.

    K0 References:
    - k0/obs/metrics.py: MetricsExporter.gauge(), counter(), histogram()
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize learning metrics.

        Args:
            metrics: K0 MetricsExporter instance
            pipeline_id: Pipeline identifier for labels
        """
        self.metrics = metrics
        self.pipeline_id = pipeline_id

        # Budget gauges
        self._learning_time_pct: Gauge = metrics.gauge(
            name="p03_learning_time_pct",
            description="Percentage of cycle time spent on learning",
            labelnames=["space_id", "component"],
        )

        self._queue_depth: Gauge = metrics.gauge(
            name="p03_learning_queue_depth",
            description="Number of feedback signals pending",
            labelnames=["space_id"],
        )

        # Budget counters
        self._queue_overflow: Counter = metrics.counter(
            name="p03_learning_queue_overflow",
            description="Signals discarded due to queue overflow",
            labelnames=["space_id"],
        )

        self._skip_count: Counter = metrics.counter(
            name="p03_learning_skip_count",
            description="Operations skipped due to budget",
            labelnames=["component", "reason"],
        )

        self._budget_exceeded: Counter = metrics.counter(
            name="p03_learning_budget_exceeded",
            description="Times learning exceeded 5% budget",
            labelnames=["space_id"],
        )

        self._parameter_updates: Counter = metrics.counter(
            name="p03_learning_parameter_updates",
            description="Total parameter updates from learning",
            labelnames=["param_key", "space_id"],
        )

        self._audit_writes: Counter = metrics.counter(
            name="p03_audit_writes",
            description="Audit records written",
            labelnames=["batch_size"],
        )

        self._audit_drops: Counter = metrics.counter(
            name="p03_audit_drops",
            description="Audit records dropped",
            labelnames=[],
        )

        # Latency histograms
        self._latency_ms: Histogram = metrics.histogram(
            name="p03_learning_latency_ms",
            description="Latency of learning operations",
            labelnames=["component", "operation"],
            buckets=[1, 5, 10, 20, 50, 100, 200, 500, 1000],
        )

        self._batch_size: Histogram = metrics.histogram(
            name="p03_learning_batch_size",
            description="Number of signals processed per batch",
            labelnames=["operation"],
            buckets=[1, 10, 25, 50, 100, 200, 500],
        )

        self._batch_duration_ms: Histogram = metrics.histogram(
            name="p03_learning_batch_duration_ms",
            description="Duration of batch processing",
            labelnames=["operation"],
            buckets=[10, 50, 100, 500, 1000, 5000],
        )

    def record_learning_time_pct(
        self,
        space_id: str,
        component: str,
        pct: float,
    ) -> None:
        """Record learning time percentage."""
        self._learning_time_pct.labels(
            space_id=space_id,
            component=component,
        ).set(pct)

    def record_queue_depth(self, space_id: str, depth: int) -> None:
        """Record queue depth."""
        self._queue_depth.labels(space_id=space_id).set(depth)

    def record_queue_overflow(self, space_id: str) -> None:
        """Record queue overflow."""
        self._queue_overflow.labels(space_id=space_id).inc()

    def record_skip(self, component: str, reason: str) -> None:
        """Record skipped operation."""
        self._skip_count.labels(
            component=component,
            reason=reason,
        ).inc()

    def record_budget_exceeded(self, space_id: str) -> None:
        """Record budget exceeded."""
        self._budget_exceeded.labels(space_id=space_id).inc()

    def record_latency(
        self,
        component: str,
        operation: str,
        latency_ms: float,
    ) -> None:
        """Record operation latency."""
        self._latency_ms.labels(
            component=component,
            operation=operation,
        ).observe(latency_ms)

    def record_batch(
        self,
        operation: str,
        size: int,
        duration_ms: float,
    ) -> None:
        """Record batch processing."""
        self._batch_size.labels(operation=operation).observe(size)
        self._batch_duration_ms.labels(operation=operation).observe(duration_ms)

    def record_parameter_update(
        self,
        param_key: str,
        space_id: str,
    ) -> None:
        """Record parameter update."""
        self._parameter_updates.labels(
            param_key=param_key,
            space_id=space_id,
        ).inc()

    def record_audit_write(self, batch_size: int) -> None:
        """Record audit write."""
        self._audit_writes.labels(batch_size=str(batch_size)).inc()

    def record_audit_drop(self) -> None:
        """Record audit drop."""
        self._audit_drops.inc()
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/obs/test_learning_metrics.py
"""Tests for P03 learning metrics."""

import pytest
from unittest.mock import MagicMock

from k0.obs.metrics import MetricsExporter


class TestP03LearningMetrics:
    """Test learning performance metrics."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MagicMock(spec=MetricsExporter)

    def test_record_learning_time_pct(self, metrics_exporter) -> None:
        """Learning time gauge set."""
        from k0.pipelines.p03.obs.learning_metrics import (
            P03LearningMetrics,
        )

        learning_metrics = P03LearningMetrics(metrics_exporter)
        learning_metrics.record_learning_time_pct("space1", "feedback", 3.5)

    def test_record_queue_overflow(self, metrics_exporter) -> None:
        """Queue overflow counter incremented."""
        from k0.pipelines.p03.obs.learning_metrics import (
            P03LearningMetrics,
        )

        learning_metrics = P03LearningMetrics(metrics_exporter)
        learning_metrics.record_queue_overflow("space1")

    def test_record_batch(self, metrics_exporter) -> None:
        """Batch size and duration recorded."""
        from k0.pipelines.p03.obs.learning_metrics import (
            P03LearningMetrics,
        )

        learning_metrics = P03LearningMetrics(metrics_exporter)
        learning_metrics.record_batch("feedback", size=50, duration_ms=100.0)
```

**Acceptance Criteria**:

- [ ] `P03LearningMetrics` uses K0 `MetricsExporter`
- [ ] `p03_learning_time_pct` Gauge tracks budget usage
- [ ] `p03_learning_queue_depth` Gauge tracks queue size
- [ ] `p03_learning_queue_overflow` Counter tracks discards
- [ ] `p03_learning_skip_count` Counter tracks skipped ops
- [ ] `p03_learning_budget_exceeded` Counter tracks violations
- [ ] `p03_learning_latency_ms` Histogram with correct buckets
- [ ] `p03_learning_batch_size` Histogram with correct buckets
- [ ] `p03_audit_writes` and `p03_audit_drops` Counters
- [ ] All metrics match dossier specification
- [ ] ≥95% test coverage

---

#### Issue 6.4.13 — Learning budget alerting

**Status**: 🔲 NOT STARTED

**Goal**: Implement Prometheus alerting rules for learning budget violations.

**Dossier Reference**: Section 8.2.2 "Alert Configuration"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Telemetry | `k0/telemetry/mixins/` | Alert rule builder pattern |

**Alerting Thresholds (from dossier)**:

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| learning_time_pct | > 4% | > 5% | Investigate slow ops |
| learning_queue_depth | > 500 | > 1000 | Scale up processing |
| learning_skip_count | > 1/hour | > 10/hour | Budget too tight |
| learning_queue_overflow | > 10/min | > 50/min | Increase queue size |
| audit_drops | > 1/min | > 10/min | Async writer overloaded |

**Work To Do**:

1. [ ] Create `k0/telemetry/mixins/p03_learning_alerts.py`
2. [ ] Implement alert rule builder following K0 patterns
3. [ ] Create `P03LearningBudgetExceeded` alert (warning)
4. [ ] Create `P03LearningSkipRateHigh` alert (warning)
5. [ ] Create `P03LearningQueueOverflow` alert (critical)
6. [ ] Create `P03LearningQueueHigh` alert (warning)
7. [ ] Create `P03LearningQueueCritical` alert (critical)
8. [ ] Generate YAML output to `k0/telemetry/generated/rules/`
9. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/telemetry/mixins/p03_learning_alerts.py
"""
P03 learning budget alert rules.

Generates Prometheus alerting rules for learning budget violations.

Dossier Reference: Section 8.2.2 Alert Configuration
K0 Reference: k0/telemetry/mixins/ pattern
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import yaml


@dataclass(frozen=True, slots=True)
class AlertRule:
    """Prometheus alert rule definition."""

    name: str
    expr: str
    for_duration: str
    severity: str
    summary: str
    description: str


# Alert rules from dossier Section 8.2.2
P03_LEARNING_ALERTS: list[AlertRule] = [
    AlertRule(
        name="P03LearningBudgetExceeded",
        expr="p03_learning_time_pct > 5",
        for_duration="5m",
        severity="warning",
        summary="Learning operations exceed 5% budget",
        description="Space {{ $labels.space_id }} learning at {{ $value }}%",
    ),
    AlertRule(
        name="P03LearningSkipRateHigh",
        expr="rate(p03_learning_skip_count[1h]) > 10",
        for_duration="15m",
        severity="warning",
        summary="High learning operation skip rate",
        description="{{ $value }} operations/hour skipped due to budget",
    ),
    AlertRule(
        name="P03LearningQueueOverflow",
        expr="rate(p03_learning_queue_overflow[5m]) > 50",
        for_duration="5m",
        severity="critical",
        summary="Learning queue overflowing",
        description="{{ $value }} signals/min discarded",
    ),
    AlertRule(
        name="P03LearningQueueHigh",
        expr="p03_learning_queue_depth > 500",
        for_duration="5m",
        severity="warning",
        summary="Learning feedback queue above 500 signals",
        description="Queue depth at {{ $value }} signals",
    ),
    AlertRule(
        name="P03LearningQueueCritical",
        expr="p03_learning_queue_depth > 1000",
        for_duration="1m",
        severity="critical",
        summary="Learning feedback queue at capacity (1000 signals)",
        description="Queue depth at {{ $value }} signals - at risk of overflow",
    ),
]


class P03LearningAlertBuilder:
    """
    Build Prometheus alert rules for P03 learning.

    Follows K0 telemetry mixin pattern.
    """

    OUTPUT_PATH: ClassVar[str] = (
        "k0/telemetry/generated/rules/p03_learning_alerts.yaml"
    )

    def __init__(self, alerts: list[AlertRule] | None = None) -> None:
        """
        Initialize alert builder.

        Args:
            alerts: Custom alerts (defaults to dossier alerts)
        """
        self.alerts = alerts or P03_LEARNING_ALERTS

    def build(self) -> dict:
        """
        Build Prometheus alerting rules structure.

        Returns:
            Dict suitable for YAML serialization
        """
        rules = []
        for alert in self.alerts:
            rules.append({
                "alert": alert.name,
                "expr": alert.expr,
                "for": alert.for_duration,
                "labels": {
                    "severity": alert.severity,
                },
                "annotations": {
                    "summary": alert.summary,
                    "description": alert.description,
                },
            })

        return {
            "groups": [
                {
                    "name": "p03_learning",
                    "rules": rules,
                }
            ]
        }

    def to_yaml(self) -> str:
        """Generate YAML string."""
        return yaml.dump(self.build(), default_flow_style=False)

    def write(self, path: str | None = None) -> None:
        """
        Write alerts to YAML file.

        Args:
            path: Output path (defaults to OUTPUT_PATH)
        """
        output_path = path or self.OUTPUT_PATH
        with open(output_path, "w") as f:
            f.write(self.to_yaml())
```

**Test Pattern**:

```python
# tests/k0/telemetry/test_p03_learning_alerts.py
"""Tests for P03 learning alert rules."""

import pytest
import yaml


class TestP03LearningAlertBuilder:
    """Test alert rule generation."""

    def test_build_all_alerts(self) -> None:
        """All dossier alerts generated."""
        from k0.telemetry.mixins.p03_learning_alerts import (
            P03LearningAlertBuilder,
            P03_LEARNING_ALERTS,
        )

        builder = P03LearningAlertBuilder()
        result = builder.build()

        assert "groups" in result
        rules = result["groups"][0]["rules"]
        assert len(rules) == len(P03_LEARNING_ALERTS)

    def test_budget_exceeded_alert(self) -> None:
        """Budget exceeded alert configured correctly."""
        from k0.telemetry.mixins.p03_learning_alerts import (
            P03LearningAlertBuilder,
        )

        builder = P03LearningAlertBuilder()
        result = builder.build()
        rules = result["groups"][0]["rules"]

        budget_alert = next(
            r for r in rules if r["alert"] == "P03LearningBudgetExceeded"
        )

        assert budget_alert["expr"] == "p03_learning_time_pct > 5"
        assert budget_alert["for"] == "5m"
        assert budget_alert["labels"]["severity"] == "warning"

    def test_queue_critical_alert(self) -> None:
        """Queue critical alert is critical severity."""
        from k0.telemetry.mixins.p03_learning_alerts import (
            P03LearningAlertBuilder,
        )

        builder = P03LearningAlertBuilder()
        result = builder.build()
        rules = result["groups"][0]["rules"]

        queue_alert = next(
            r for r in rules if r["alert"] == "P03LearningQueueCritical"
        )

        assert queue_alert["labels"]["severity"] == "critical"
        assert queue_alert["for"] == "1m"

    def test_to_yaml(self) -> None:
        """YAML output is valid."""
        from k0.telemetry.mixins.p03_learning_alerts import (
            P03LearningAlertBuilder,
        )

        builder = P03LearningAlertBuilder()
        yaml_str = builder.to_yaml()

        # Should parse without error
        parsed = yaml.safe_load(yaml_str)
        assert "groups" in parsed
```

**Acceptance Criteria**:

- [ ] Alert rules follow K0 telemetry mixin pattern
- [ ] `P03LearningBudgetExceeded` alert: expr=`> 5`, for=5m, warning
- [ ] `P03LearningSkipRateHigh` alert: expr=`rate > 10/h`, for=15m, warning
- [ ] `P03LearningQueueOverflow` alert: expr=`rate > 50/5m`, for=5m, critical
- [ ] `P03LearningQueueHigh` alert: expr=`> 500`, for=5m, warning
- [ ] `P03LearningQueueCritical` alert: expr=`> 1000`, for=1m, critical
- [ ] YAML output valid and importable
- [ ] Alert descriptions include context
- [ ] ≥95% test coverage

---

#### Issue 6.4.14 — FeedbackQueue with overflow handling

**Status**: 🔲 NOT STARTED

**Goal**: Implement feedback signal queue with sampling overflow protection.

**Dossier Reference**: Section 15.10 "Queue Management"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.counter()` for overflow |

**Queue Configuration (from dossier)**:

| Setting | Value | Description |
|---------|-------|-------------|
| max_depth | 1000 | Maximum signals in queue |
| sample_rate | 0.10 | Keep 10% on overflow |
| discard_rate | 0.90 | Discard 90% on overflow |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/learning/feedback_queue.py`
2. [ ] Implement `FeedbackQueue` class with asyncio.Queue
3. [ ] Implement `enqueue(signal)` with overflow sampling
4. [ ] Implement `dequeue_batch(batch_size)` for batch processing
5. [ ] Implement `depth()` for queue monitoring
6. [ ] Add `p03_learning_queue_overflow` Counter integration
7. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/learning/feedback_queue.py
"""
P03 feedback signal queue with overflow handling.

Manages learning feedback signals with sampling overflow protection.

Dossier Reference: Section 15.10 Queue Management
K0 Reference: k0/obs/metrics.py: MetricsExporter.counter()
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Counter


@dataclass
class FeedbackSignal:
    """Feedback signal for learning."""

    signal_id: str
    signal_type: str
    memory_id: str
    confidence: float
    timestamp: float


# Queue configuration from dossier Section 15.10
QUEUE_MAX_DEPTH = 1000
OVERFLOW_SAMPLE_RATE = 0.10  # Keep 10% on overflow


class FeedbackQueue:
    """
    Manage feedback signal queue with overflow handling.

    Uses sampling on overflow to preserve signal diversity.

    Dossier Reference: Section 15.10 Queue Management
    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for overflow tracking
    """

    def __init__(
        self,
        metrics: MetricsExporter,
        max_depth: int = QUEUE_MAX_DEPTH,
        sample_rate: float = OVERFLOW_SAMPLE_RATE,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize feedback queue.

        Args:
            metrics: K0 MetricsExporter instance
            max_depth: Maximum queue size
            sample_rate: Sampling rate on overflow (0.0-1.0)
            pipeline_id: Pipeline identifier for labels
        """
        self.queue: asyncio.Queue[FeedbackSignal] = asyncio.Queue(
            maxsize=max_depth
        )
        self.max_depth = max_depth
        self.sample_rate = sample_rate
        self.pipeline_id = pipeline_id
        self.overflow_count = 0

        # K0 metrics
        self._overflow_counter: Counter = metrics.counter(
            name="p03_learning_queue_overflow",
            description="Signals discarded due to queue overflow",
            labelnames=["space_id", "pipeline_id"],
        )

    async def enqueue(
        self,
        signal: FeedbackSignal,
        space_id: str = "default",
    ) -> bool:
        """
        Add signal to queue, sample if full.

        Args:
            signal: Feedback signal to enqueue
            space_id: Space identifier for metrics

        Returns:
            True if enqueued, False if discarded
        """
        try:
            self.queue.put_nowait(signal)
            return True
        except asyncio.QueueFull:
            # Queue full: Sample (keep 10%, discard 90%)
            if random.random() < self.sample_rate:
                # Discard oldest, add new
                try:
                    self.queue.get_nowait()
                    self.queue.put_nowait(signal)
                    self.overflow_count += 1
                    return True
                except Exception:
                    pass

            # Discarded
            self._overflow_counter.labels(
                space_id=space_id,
                pipeline_id=self.pipeline_id,
            ).inc()
            return False

    async def dequeue_batch(
        self,
        batch_size: int,
    ) -> list[FeedbackSignal]:
        """
        Dequeue up to batch_size signals.

        Args:
            batch_size: Maximum signals to dequeue

        Returns:
            List of dequeued signals
        """
        batch: list[FeedbackSignal] = []
        for _ in range(batch_size):
            try:
                signal = self.queue.get_nowait()
                batch.append(signal)
            except asyncio.QueueEmpty:
                break
        return batch

    def depth(self) -> int:
        """Current queue depth."""
        return self.queue.qsize()

    def is_full(self) -> bool:
        """Check if queue is full."""
        return self.queue.full()

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/learning/test_feedback_queue.py
"""Tests for P03 feedback queue."""

import pytest
from unittest.mock import MagicMock

from k0.obs.metrics import MetricsExporter


class TestFeedbackQueue:
    """Test feedback queue with overflow handling."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MagicMock(spec=MetricsExporter)

    @pytest.mark.asyncio
    async def test_enqueue_within_capacity(self, metrics_exporter) -> None:
        """Signals enqueued when capacity available."""
        from k0.pipelines.p03.learning.feedback_queue import (
            FeedbackQueue,
            FeedbackSignal,
        )

        queue = FeedbackQueue(metrics_exporter, max_depth=10)

        signal = FeedbackSignal(
            signal_id="sig1",
            signal_type="positive",
            memory_id="mem1",
            confidence=0.9,
            timestamp=0.0,
        )

        result = await queue.enqueue(signal)

        assert result is True
        assert queue.depth() == 1

    @pytest.mark.asyncio
    async def test_dequeue_batch(self, metrics_exporter) -> None:
        """Batch dequeue returns correct signals."""
        from k0.pipelines.p03.learning.feedback_queue import (
            FeedbackQueue,
            FeedbackSignal,
        )

        queue = FeedbackQueue(metrics_exporter, max_depth=10)

        for i in range(5):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        batch = await queue.dequeue_batch(3)

        assert len(batch) == 3
        assert queue.depth() == 2

    @pytest.mark.asyncio
    async def test_overflow_sampling(self, metrics_exporter) -> None:
        """Overflow triggers sampling."""
        from k0.pipelines.p03.learning.feedback_queue import (
            FeedbackQueue,
            FeedbackSignal,
        )

        queue = FeedbackQueue(
            metrics_exporter,
            max_depth=5,
            sample_rate=0.0,  # Always discard on overflow
        )

        # Fill queue
        for i in range(5):
            signal = FeedbackSignal(
                signal_id=f"sig{i}",
                signal_type="positive",
                memory_id=f"mem{i}",
                confidence=0.9,
                timestamp=0.0,
            )
            await queue.enqueue(signal)

        # Overflow
        overflow_signal = FeedbackSignal(
            signal_id="overflow",
            signal_type="positive",
            memory_id="memX",
            confidence=0.9,
            timestamp=0.0,
        )
        result = await queue.enqueue(overflow_signal)

        assert result is False  # Discarded
        assert queue.depth() == 5  # Still at capacity
```

**Acceptance Criteria**:

- [ ] `FeedbackQueue` uses asyncio.Queue with max_depth=1000
- [ ] `enqueue()` returns True on success, False on discard
- [ ] Overflow samples 10%, discards 90%
- [ ] `p03_learning_queue_overflow` incremented on discard
- [ ] `dequeue_batch()` returns up to batch_size signals
- [ ] Queue never blocks on full
- [ ] ≥95% test coverage

---

#### Issue 6.4.15 — AsyncAuditLogger implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement non-blocking audit logging with batched writes.

**Dossier Reference**: Section 15.10 "Async Writes"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| K0 Metrics | `k0/obs/metrics.py` | `MetricsExporter.counter()` for writes/drops |
| K0 Logging | `k0/obs/logging.py` | Structured error logging |

**Batch Configuration (from dossier)**:

| Setting | Value | Description |
|---------|-------|-------------|
| write_interval | 30s | Batch write interval |
| max_batch_size | 50 | Max records per batch |

**Work To Do**:

1. [ ] Create `k0/pipelines/p03/learning/async_audit.py`
2. [ ] Define `AuditRecord` dataclass
3. [ ] Implement `AsyncAuditLogger` class
4. [ ] Implement `start()` to spawn background writer task
5. [ ] Implement `log_audit(record)` for non-blocking enqueue
6. [ ] Implement `_writer_loop()` for batched writes every 30s
7. [ ] Implement `_write_batch()` with `executemany()`
8. [ ] Add `p03_audit_writes` and `p03_audit_drops` Counters
9. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/pipelines/p03/learning/async_audit.py
"""
P03 async audit logger with batched writes.

Non-blocking audit logging to avoid impacting consolidation cycle.

Dossier Reference: Section 15.10 Async Writes
K0 References:
- k0/obs/metrics.py: MetricsExporter.counter()
- k0/obs/logging.py: Structured logging
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from k0.obs.logging import get_logger
from k0.obs.metrics import MetricsExporter

if TYPE_CHECKING:
    from prometheus_client import Counter

    from k0.drivers.postgres import PostgresDriver

logger = get_logger(__name__)


# Batch configuration from dossier Section 15.10
WRITE_INTERVAL_SECONDS = 30
MAX_BATCH_SIZE = 50
QUEUE_MAX_SIZE = 500


@dataclass
class AuditRecord:
    """Audit record for consolidation changes."""

    audit_id: str
    memory_id: str
    cycle_id: str
    operation: str
    before_state: dict | None = None
    after_state: dict | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class AsyncAuditLogger:
    """
    Non-blocking audit logging with batched writes.

    Queues audit records and writes in batches every 30s.

    Dossier Reference: Section 15.10 Async Writes
    K0 References:
    - k0/obs/metrics.py: MetricsExporter.counter() for tracking
    """

    def __init__(
        self,
        db: PostgresDriver,
        metrics: MetricsExporter,
        write_interval: int = WRITE_INTERVAL_SECONDS,
        max_batch_size: int = MAX_BATCH_SIZE,
        pipeline_id: str = "p03_consolidation",
    ) -> None:
        """
        Initialize async audit logger.

        Args:
            db: K0 PostgresDriver instance
            metrics: K0 MetricsExporter instance
            write_interval: Seconds between batch writes
            max_batch_size: Max records per batch
            pipeline_id: Pipeline identifier for labels
        """
        self.db = db
        self.write_interval = write_interval
        self.max_batch_size = max_batch_size
        self.pipeline_id = pipeline_id

        self.write_queue: asyncio.Queue[AuditRecord] = asyncio.Queue(
            maxsize=QUEUE_MAX_SIZE
        )
        self.writer_task: asyncio.Task | None = None
        self._running = False

        # K0 metrics
        self._write_counter: Counter = metrics.counter(
            name="p03_audit_writes",
            description="Audit records written",
            labelnames=["batch_size"],
        )

        self._drop_counter: Counter = metrics.counter(
            name="p03_audit_drops",
            description="Audit records dropped",
            labelnames=[],
        )

    async def start(self) -> None:
        """Start background writer task."""
        if self._running:
            return
        self._running = True
        self.writer_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> None:
        """Stop background writer and flush remaining."""
        self._running = False
        if self.writer_task:
            self.writer_task.cancel()
            try:
                await self.writer_task
            except asyncio.CancelledError:
                pass

        # Flush remaining
        await self._flush()

    def log_audit(self, record: AuditRecord) -> bool:
        """
        Queue audit record (non-blocking).

        Args:
            record: Audit record to log

        Returns:
            True if queued, False if dropped
        """
        try:
            self.write_queue.put_nowait(record)
            return True
        except asyncio.QueueFull:
            # Drop audit if queue full (fire-and-forget)
            self._drop_counter.inc()
            return False

    async def _writer_loop(self) -> None:
        """Background writer: batch writes every 30s."""
        while self._running:
            await asyncio.sleep(self.write_interval)
            await self._flush()

    async def _flush(self) -> None:
        """Flush pending records."""
        batch: list[AuditRecord] = []

        # Drain queue up to max batch size
        while not self.write_queue.empty() and len(batch) < self.max_batch_size:
            try:
                record = self.write_queue.get_nowait()
                batch.append(record)
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._write_batch(batch)

    async def _write_batch(self, batch: list[AuditRecord]) -> None:
        """
        Write batch to database.

        Args:
            batch: Records to write
        """
        try:
            # Use executemany for batched inserts
            await self.db.executemany(
                """
                INSERT INTO st_consolidation_audit
                (audit_id, memory_id, cycle_id, operation, before_state, after_state, timestamp)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        r.audit_id,
                        r.memory_id,
                        r.cycle_id,
                        r.operation,
                        r.before_state,
                        r.after_state,
                        r.timestamp,
                    )
                    for r in batch
                ],
            )
            self._write_counter.labels(batch_size=str(len(batch))).inc()
        except Exception as e:
            logger.error(
                "audit_batch_write_failed",
                batch_size=len(batch),
                error=str(e),
            )
```

**Test Pattern**:

```python
# tests/k0/modules/consolidation/learning/test_async_audit.py
"""Tests for P03 async audit logger."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from k0.obs.metrics import MetricsExporter


class TestAsyncAuditLogger:
    """Test non-blocking audit logging."""

    @pytest.fixture
    def metrics_exporter(self) -> MetricsExporter:
        """Create metrics exporter."""
        return MagicMock(spec=MetricsExporter)

    @pytest.fixture
    def db_driver(self):
        """Create mock DB driver."""
        driver = MagicMock()
        driver.executemany = AsyncMock()
        return driver

    def test_log_audit_enqueues(
        self, db_driver, metrics_exporter
    ) -> None:
        """Audit records enqueued."""
        from k0.pipelines.p03.learning.async_audit import (
            AsyncAuditLogger,
            AuditRecord,
        )

        logger = AsyncAuditLogger(db_driver, metrics_exporter)

        record = AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
        )

        result = logger.log_audit(record)

        assert result is True
        assert logger.write_queue.qsize() == 1

    def test_log_audit_drops_when_full(
        self, db_driver, metrics_exporter
    ) -> None:
        """Audit records dropped when queue full."""
        from k0.pipelines.p03.learning.async_audit import (
            AsyncAuditLogger,
            AuditRecord,
            QUEUE_MAX_SIZE,
        )

        # Create logger with tiny queue
        logger = AsyncAuditLogger(db_driver, metrics_exporter)
        logger.write_queue = MagicMock()
        logger.write_queue.put_nowait.side_effect = asyncio.QueueFull()

        record = AuditRecord(
            audit_id="audit1",
            memory_id="mem1",
            cycle_id="cycle1",
            operation="merge",
        )

        result = logger.log_audit(record)

        assert result is False

    @pytest.mark.asyncio
    async def test_write_batch(
        self, db_driver, metrics_exporter
    ) -> None:
        """Batch written to database."""
        from k0.pipelines.p03.learning.async_audit import (
            AsyncAuditLogger,
            AuditRecord,
        )

        logger = AsyncAuditLogger(db_driver, metrics_exporter)

        batch = [
            AuditRecord(
                audit_id=f"audit{i}",
                memory_id=f"mem{i}",
                cycle_id="cycle1",
                operation="merge",
            )
            for i in range(5)
        ]

        await logger._write_batch(batch)

        db_driver.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_drains_queue(
        self, db_driver, metrics_exporter
    ) -> None:
        """Flush drains queue and writes batch."""
        from k0.pipelines.p03.learning.async_audit import (
            AsyncAuditLogger,
            AuditRecord,
        )

        logger = AsyncAuditLogger(db_driver, metrics_exporter)

        for i in range(5):
            record = AuditRecord(
                audit_id=f"audit{i}",
                memory_id=f"mem{i}",
                cycle_id="cycle1",
                operation="merge",
            )
            logger.log_audit(record)

        await logger._flush()

        assert logger.write_queue.qsize() == 0
        db_driver.executemany.assert_called_once()
```

**Acceptance Criteria**:

- [ ] `AsyncAuditLogger` uses asyncio for non-blocking operation
- [ ] `log_audit()` returns immediately (non-blocking)
- [ ] `_writer_loop()` writes batches every 30 seconds
- [ ] `_write_batch()` uses `executemany()` for efficiency
- [ ] `max_batch_size` = 50 records
- [ ] `p03_audit_writes` Counter incremented on batch write
- [ ] `p03_audit_drops` Counter incremented on queue full
- [ ] Drops tracked when queue full
- [ ] ≥95% test coverage

---

#### Issue 6.4.16 — P03TestFixtures implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement test fixtures for P03 performance and integration testing.

**Dossier Reference**: Section 10.7 "Test Fixtures"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| ULID | `ulid` package | Generate event IDs |

**st_hipp_events Schema Fields (from dossier)**:

| Field | Type | Generation |
|-------|------|------------|
| event_id | TEXT | ULID |
| tenant_id | TEXT | Parameter |
| space_id | TEXT | Parameter |
| content | TEXT | Random or pattern-based |
| content_hash | TEXT | MD5 of content |
| embedding_vector | FLOAT[768] | Random 768-dim |
| salience_score | FLOAT | Random [0.1, 1.0] |
| policy_band | TEXT | "GREEN" |

**Work To Do**:

1. [ ] Create `tests/fixtures/p03.py`
2. [ ] Implement `P03TestFixtures` dataclass
3. [ ] Implement `create_random_events(n, tenant_id, space_id)`
4. [ ] Implement `create_events_with_patterns(n_events, n_patterns, events_per_pattern)`
5. [ ] Implement `create_semantic_truth(content, confidence, observation_count)`
6. [ ] Implement `create_events_matching_truth(truth, n_events, similarity)`
7. [ ] Ensure 768-dim embedding vectors
8. [ ] Ensure ULID event IDs
9. [ ] Ensure MD5 content hashes
10. [ ] Create unit tests

**Implementation Pattern**:

```python
# tests/fixtures/p03.py
"""
P03 test fixtures for performance and integration testing.

Provides factory methods for generating valid st_hipp_events
and semantic truth records.

Dossier Reference: Section 10.7 Test Fixtures
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ulid import ULID

if TYPE_CHECKING:
    pass


@dataclass
class P03TestFixtures:
    """
    Factory for P03 test data.

    Generates valid st_hipp_events and semantic records
    for performance and integration testing.
    """

    default_tenant_id: str = "test_tenant"
    default_space_id: str = "test_space"
    embedding_dim: int = 768

    def create_random_events(
        self,
        n: int,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> list[dict]:
        """
        Create n random st_hipp_events.

        Args:
            n: Number of events to create
            tenant_id: Tenant ID (defaults to test_tenant)
            space_id: Space ID (defaults to test_space)

        Returns:
            List of event dicts matching st_hipp_events schema
        """
        tenant = tenant_id or self.default_tenant_id
        space = space_id or self.default_space_id

        return [
            {
                "event_id": str(ULID()),
                "tenant_id": tenant,
                "space_id": space,
                "actor_id": f"actor_{random.randint(1, 10)}",
                "content": f"Random content {i}: {random.random()}",
                "content_hash": hashlib.md5(
                    f"content_{i}_{random.random()}".encode()
                ).hexdigest(),
                "embedding_id": str(ULID()),
                "embedding_vector": [
                    random.random() for _ in range(self.embedding_dim)
                ],
                "salience_score": random.uniform(0.1, 1.0),
                "importance_score": random.uniform(0.0, 1.0),
                "policy_band": "GREEN",
                "entities_json": "[]",
                "triplets_json": "[]",
                "consolidation_status": None,
                "created_at": 1699999999000 + i,
            }
            for i in range(n)
        ]

    def create_events_with_patterns(
        self,
        n_events: int,
        n_patterns: int,
        events_per_pattern: int,
    ) -> list[dict]:
        """
        Create events following distinct patterns.

        Useful for testing clustering and pattern recognition.

        Args:
            n_events: Total events to create
            n_patterns: Number of distinct patterns
            events_per_pattern: Events per pattern

        Returns:
            List of event dicts with pattern_id for verification
        """
        events: list[dict] = []
        patterns = [
            f"Pattern topic {i}: content about subject {i}"
            for i in range(n_patterns)
        ]

        # Base embedding per pattern
        pattern_embeddings = [
            [random.random() for _ in range(self.embedding_dim)]
            for _ in range(n_patterns)
        ]

        for pattern_idx, pattern in enumerate(patterns):
            base_embedding = pattern_embeddings[pattern_idx]

            for j in range(events_per_pattern):
                variation = f"{pattern} (variation {j})"

                # Add small noise to embedding
                noisy_embedding = [
                    v + random.uniform(-0.05, 0.05) for v in base_embedding
                ]

                events.append(
                    {
                        "event_id": str(ULID()),
                        "tenant_id": self.default_tenant_id,
                        "space_id": self.default_space_id,
                        "actor_id": f"actor_{pattern_idx}",
                        "content": variation,
                        "content_hash": hashlib.md5(
                            variation.encode()
                        ).hexdigest(),
                        "embedding_id": str(ULID()),
                        "embedding_vector": noisy_embedding,
                        "salience_score": 0.8,
                        "importance_score": 0.7,
                        "policy_band": "GREEN",
                        "pattern_id": pattern_idx,  # For verification
                        "consolidation_status": None,
                        "created_at": 1699999999000 + (pattern_idx * 1000) + j,
                    }
                )

                if len(events) >= n_events:
                    return events

        return events

    def create_semantic_truth(
        self,
        content: str,
        confidence: float = 0.7,
        observation_count: int = 5,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> dict:
        """
        Create a semantic truth record (st_sem).

        Args:
            content: Truth content
            confidence: Confidence score (0.0-1.0)
            observation_count: Number of supporting observations
            tenant_id: Tenant ID
            space_id: Space ID

        Returns:
            Dict matching st_sem schema
        """
        return {
            "id": str(ULID()),
            "tenant_id": tenant_id or self.default_tenant_id,
            "space_id": space_id or self.default_space_id,
            "version": 1,
            "content": content,
            "confidence": confidence,
            "observation_count": observation_count,
            "decay_factor": 1.0,
            "archival_status": "ACTIVE",
            "created_at": 1699999999000,
        }

    def create_events_matching_truth(
        self,
        truth: dict,
        n_events: int,
        similarity: float,
    ) -> list[dict]:
        """
        Create events that match/reinforce existing truth.

        Args:
            truth: Semantic truth record
            n_events: Number of events to create
            similarity: Target similarity (0.0-1.0)

        Returns:
            List of events with controlled similarity
        """
        base_content = truth["content"]
        events: list[dict] = []

        for i in range(n_events):
            if similarity > 0.9:
                content = base_content  # Near-identical
            elif similarity > 0.7:
                content = f"{base_content} (additional detail {i})"
            else:
                content = f"Related: {base_content[:20]}... (different context {i})"

            events.append(
                {
                    "event_id": str(ULID()),
                    "tenant_id": truth["tenant_id"],
                    "space_id": truth["space_id"],
                    "actor_id": "actor_reinforcement",
                    "content": content,
                    "content_hash": hashlib.md5(content.encode()).hexdigest(),
                    "embedding_id": str(ULID()),
                    "embedding_vector": [
                        random.random() for _ in range(self.embedding_dim)
                    ],
                    "salience_score": 0.8,
                    "importance_score": 0.75,
                    "policy_band": "GREEN",
                    "target_similarity": similarity,  # For verification
                    "consolidation_status": None,
                    "created_at": 1699999999000 + i,
                }
            )

        return events
```

**Test Pattern**:

```python
# tests/fixtures/test_p03_fixtures.py
"""Tests for P03 test fixtures."""

import pytest


class TestP03TestFixtures:
    """Test fixture generation."""

    def test_create_random_events(self) -> None:
        """Random events have correct structure."""
        from tests.fixtures.p03 import P03TestFixtures

        fixtures = P03TestFixtures()
        events = fixtures.create_random_events(10)

        assert len(events) == 10

        for event in events:
            assert "event_id" in event
            assert "embedding_vector" in event
            assert len(event["embedding_vector"]) == 768
            assert 0.1 <= event["salience_score"] <= 1.0

    def test_create_events_with_patterns(self) -> None:
        """Pattern events cluster correctly."""
        from tests.fixtures.p03 import P03TestFixtures

        fixtures = P03TestFixtures()
        events = fixtures.create_events_with_patterns(
            n_events=30,
            n_patterns=3,
            events_per_pattern=10,
        )

        assert len(events) == 30

        # Check pattern distribution
        pattern_ids = [e["pattern_id"] for e in events]
        assert set(pattern_ids) == {0, 1, 2}

    def test_create_semantic_truth(self) -> None:
        """Semantic truth has correct fields."""
        from tests.fixtures.p03 import P03TestFixtures

        fixtures = P03TestFixtures()
        truth = fixtures.create_semantic_truth(
            content="The sky is blue",
            confidence=0.9,
            observation_count=10,
        )

        assert truth["content"] == "The sky is blue"
        assert truth["confidence"] == 0.9
        assert truth["observation_count"] == 10

    def test_create_events_matching_truth(self) -> None:
        """Matching events reference truth."""
        from tests.fixtures.p03 import P03TestFixtures

        fixtures = P03TestFixtures()
        truth = fixtures.create_semantic_truth("Test content")
        events = fixtures.create_events_matching_truth(
            truth=truth,
            n_events=5,
            similarity=0.95,
        )

        assert len(events) == 5
        for event in events:
            assert event["tenant_id"] == truth["tenant_id"]
            assert event["space_id"] == truth["space_id"]

    def test_embedding_dimension(self) -> None:
        """All embeddings are 768-dim."""
        from tests.fixtures.p03 import P03TestFixtures

        fixtures = P03TestFixtures()
        events = fixtures.create_random_events(5)

        for event in events:
            assert len(event["embedding_vector"]) == 768

    def test_ulid_event_ids(self) -> None:
        """Event IDs are valid ULIDs."""
        from tests.fixtures.p03 import P03TestFixtures
        from ulid import ULID

        fixtures = P03TestFixtures()
        events = fixtures.create_random_events(5)

        for event in events:
            # Should not raise
            ULID.from_str(event["event_id"])
```

**Acceptance Criteria**:

- [ ] `P03TestFixtures` dataclass implemented
- [ ] `create_random_events()` generates valid st_hipp_events
- [ ] Embedding vectors are 768-dimensional
- [ ] Event IDs are valid ULIDs
- [ ] Content hashes are MD5
- [ ] `create_events_with_patterns()` enables clustering tests
- [ ] `create_semantic_truth()` generates valid st_sem records
- [ ] `create_events_matching_truth()` controls similarity
- [ ] Salience scores in [0.1, 1.0] range
- [ ] ≥95% test coverage

---

#### Issue 6.4.17 — Throughput benchmark tests

**Status**: 🔲 NOT STARTED

**Goal**: Implement throughput benchmark tests per dossier targets.

**Dossier Reference**: Section 10.5 "Performance Tests" - TestThroughputBenchmarks

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03TestFixtures | `tests/fixtures/p03.py` | `create_random_events()` |

**Performance Targets**:

| Test | Target | Dataset |
|------|--------|---------|
| `test_consolidation_throughput` | ≥1000 events/minute | 1000 events |
| `test_large_batch_cycle_time` | <5 minutes (300s) | 10000 events |

**Work To Do**:

1. [ ] Create `tests/k0/pipelines/p03/performance/test_throughput.py`
2. [ ] Implement `TestThroughputBenchmarks` class
3. [ ] Implement `test_consolidation_throughput()` — target ≥1000 events/min
4. [ ] Implement `test_large_batch_cycle_time()` — target <300s for 10K events
5. [ ] Add `@pytest.mark.performance` decorator
6. [ ] Calculate events_per_minute correctly
7. [ ] Provide clear failure messages with actual vs target
8. [ ] Create `conftest.py` with `p03_fixtures` fixture
9. [ ] Create unit tests

**Implementation Pattern**:

```python
# tests/k0/pipelines/p03/performance/test_throughput.py
"""
Throughput benchmark tests for P03 consolidation.

Validates that the pipeline meets performance targets:
- ≥1000 events/minute for standard batches
- <5 minutes for 10K event batches

Dossier Reference: Section 10.5 Performance Tests
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.fixtures.p03 import P03TestFixtures


@pytest.mark.performance
class TestThroughputBenchmarks:
    """Performance benchmarks for P03 consolidation throughput."""

    @pytest.mark.asyncio
    async def test_consolidation_throughput(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures,
    ) -> None:
        """
        Target: ≥1000 events/minute.

        Setup 1000 events, run consolidation cycle,
        measure throughput.
        """
        # Setup: 1000 events
        events = p03_fixtures.create_random_events(n=1000)
        await pipeline.storage.insert_hipp_events(events)

        # Execute with timing
        start = time.perf_counter()

        await pipeline.run_cycle(
            tenant_id="perf_tenant",
            space_id="perf_space",
        )

        elapsed = time.perf_counter() - start

        # Calculate throughput
        events_per_second = 1000 / elapsed if elapsed > 0 else 0
        events_per_minute = events_per_second * 60

        # Assert throughput meets target
        assert events_per_minute >= 1000, (
            f"Throughput {events_per_minute:.0f} events/min "
            f"below target 1000 events/min "
            f"(elapsed: {elapsed:.2f}s)"
        )

    @pytest.mark.asyncio
    async def test_large_batch_cycle_time(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures,
    ) -> None:
        """
        Target: <5 minutes for 10K events.

        Setup 10000 events, run consolidation cycle,
        verify completes within time limit.
        """
        # Setup: 10000 events
        events = p03_fixtures.create_random_events(n=10000)
        await pipeline.storage.insert_hipp_events(events)

        # Execute with timing
        start = time.perf_counter()

        await pipeline.run_cycle(
            tenant_id="perf_tenant",
            space_id="perf_space",
        )

        elapsed = time.perf_counter() - start

        # Assert cycle time meets target
        target_seconds = 300  # 5 minutes
        assert elapsed < target_seconds, (
            f"Cycle time {elapsed:.1f}s exceeds target {target_seconds}s (5 min) "
            f"for 10K events"
        )


# Conftest fixture for performance tests
# tests/k0/pipelines/p03/performance/conftest.py
"""
Fixtures for P03 performance tests.
"""

import pytest

from tests.fixtures.p03 import P03TestFixtures


@pytest.fixture
def p03_fixtures() -> P03TestFixtures:
    """Provide P03 test fixtures."""
    return P03TestFixtures()
```

**Test Pattern**:

```python
# tests/k0/pipelines/p03/performance/test_throughput_unit.py
"""Unit tests for throughput benchmark calculations."""

import pytest


class TestThroughputCalculation:
    """Test throughput calculation logic."""

    def test_events_per_minute_calculation(self) -> None:
        """Events per minute calculated correctly."""
        events_count = 1000
        elapsed_seconds = 30  # 30 seconds

        events_per_second = events_count / elapsed_seconds
        events_per_minute = events_per_second * 60

        assert events_per_minute == 2000  # 1000 events in 30s = 2000/min

    def test_throughput_failure_message(self) -> None:
        """Failure message includes actual vs target."""
        events_per_minute = 800
        target = 1000

        message = (
            f"Throughput {events_per_minute:.0f} events/min "
            f"below target {target} events/min"
        )

        assert "800" in message
        assert "1000" in message

    def test_cycle_time_failure_message(self) -> None:
        """Cycle time failure includes elapsed vs target."""
        elapsed = 350.5
        target = 300

        message = (
            f"Cycle time {elapsed:.1f}s exceeds target {target}s"
        )

        assert "350.5" in message
        assert "300" in message


class TestPerformanceMarkers:
    """Test that performance markers are applied."""

    def test_performance_marker_exists(self) -> None:
        """Performance tests have marker."""
        import tests.k0.pipelines.p03.performance.test_throughput as mod

        cls = mod.TestThroughputBenchmarks
        markers = getattr(cls, "pytestmark", [])

        marker_names = [m.name for m in markers]
        assert "performance" in marker_names
```

**Acceptance Criteria**:

- [ ] `TestThroughputBenchmarks` class implemented
- [ ] `test_consolidation_throughput()` targets ≥1000 events/min
- [ ] `test_large_batch_cycle_time()` targets <300s for 10K events
- [ ] `@pytest.mark.performance` decorator applied
- [ ] Throughput calculated as events_per_second * 60
- [ ] Failure messages include actual vs target values
- [ ] `p03_fixtures` fixture provided in conftest.py
- [ ] Uses `time.perf_counter()` for accurate timing
- [ ] ≥95% test coverage

---

#### Issue 6.4.18 — Memory footprint benchmark tests

**Status**: 🔲 NOT STARTED

**Goal**: Implement memory usage benchmark tests per dossier targets.

**Dossier Reference**: Section 10.5 "Performance Tests" - TestMemoryFootprint

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| P03TestFixtures | `tests/fixtures/p03.py` | `create_random_events()` |
| tracemalloc | stdlib | Memory tracking |

**Memory Targets**:

| Test | Target | Dataset |
|------|--------|---------|
| `test_peak_memory_under_limit` | <500MB peak | 10000 events |
| `test_streaming_prevents_oom` | No MemoryError | 100000 events |

**Work To Do**:

1. [ ] Create `tests/k0/pipelines/p03/performance/test_memory.py`
2. [ ] Implement `TestMemoryFootprint` class
3. [ ] Implement `test_peak_memory_under_limit()` — target <500MB peak
4. [ ] Implement `test_streaming_prevents_oom()` — 100K events, batch_size=1000
5. [ ] Add `@pytest.mark.performance` decorator
6. [ ] Use `tracemalloc` for memory measurement
7. [ ] Provide clear failure messages with actual vs target
8. [ ] Create unit tests

**Implementation Pattern**:

```python
# tests/k0/pipelines/p03/performance/test_memory.py
"""
Memory footprint benchmark tests for P03 consolidation.

Validates that the pipeline meets memory targets:
- <500MB peak memory for 10K events
- No OOM on 100K events with streaming

Dossier Reference: Section 10.5 Performance Tests
"""

from __future__ import annotations

import tracemalloc
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.fixtures.p03 import P03TestFixtures


@pytest.mark.performance
class TestMemoryFootprint:
    """Memory usage benchmarks for P03 consolidation."""

    @pytest.mark.asyncio
    async def test_peak_memory_under_limit(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures,
    ) -> None:
        """
        Target: <500MB peak memory.

        Setup 10000 events, run consolidation cycle,
        verify peak memory stays under limit.
        """
        # Setup: 10000 events
        events = p03_fixtures.create_random_events(n=10000)
        await pipeline.storage.insert_hipp_events(events)

        # Track memory
        tracemalloc.start()

        try:
            await pipeline.run_cycle(
                tenant_id="perf_tenant",
                space_id="perf_space",
            )

            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        target_mb = 500

        # Assert memory limit
        assert peak_mb < target_mb, (
            f"Peak memory {peak_mb:.1f}MB exceeds target {target_mb}MB "
            f"for 10K events"
        )

    @pytest.mark.asyncio
    async def test_streaming_prevents_oom(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures,
    ) -> None:
        """
        Streaming batches prevent OOM on large datasets.

        Setup 100000 events, run with batch_size=1000,
        verify no MemoryError raised.
        """
        # Setup: Very large batch (100K events)
        events = p03_fixtures.create_random_events(n=100000)
        await pipeline.storage.insert_hipp_events(events)

        # Should not raise MemoryError
        try:
            await pipeline.run_cycle(
                tenant_id="perf_tenant",
                space_id="perf_space",
                batch_size=1000,  # Stream in batches
            )
        except MemoryError:
            pytest.fail(
                "MemoryError raised - streaming not working. "
                "Expected batch_size=1000 to prevent OOM on 100K events."
            )

    @pytest.mark.asyncio
    async def test_memory_stable_across_batches(
        self,
        pipeline,
        p03_fixtures: P03TestFixtures,
    ) -> None:
        """
        Memory usage stays stable across multiple batches.

        Run multiple cycles and verify memory doesn't grow unbounded.
        """
        events = p03_fixtures.create_random_events(n=1000)
        await pipeline.storage.insert_hipp_events(events)

        memory_samples: list[float] = []

        for _ in range(5):
            tracemalloc.start()

            await pipeline.run_cycle(
                tenant_id="perf_tenant",
                space_id="perf_space",
            )

            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            memory_samples.append(peak / (1024 * 1024))

        # Memory should not grow more than 20% across iterations
        first_peak = memory_samples[0]
        last_peak = memory_samples[-1]
        growth_pct = ((last_peak - first_peak) / first_peak) * 100 if first_peak > 0 else 0

        assert growth_pct < 20, (
            f"Memory grew {growth_pct:.1f}% across iterations. "
            f"First: {first_peak:.1f}MB, Last: {last_peak:.1f}MB"
        )
```

**Test Pattern**:

```python
# tests/k0/pipelines/p03/performance/test_memory_unit.py
"""Unit tests for memory benchmark calculations."""

import pytest


class TestMemoryCalculation:
    """Test memory calculation logic."""

    def test_bytes_to_mb_conversion(self) -> None:
        """Bytes to MB conversion is correct."""
        peak_bytes = 500 * 1024 * 1024  # 500MB

        peak_mb = peak_bytes / (1024 * 1024)

        assert peak_mb == 500

    def test_memory_failure_message(self) -> None:
        """Failure message includes actual vs target."""
        peak_mb = 550.5
        target_mb = 500

        message = (
            f"Peak memory {peak_mb:.1f}MB exceeds target {target_mb}MB"
        )

        assert "550.5" in message
        assert "500" in message

    def test_growth_percentage_calculation(self) -> None:
        """Growth percentage calculated correctly."""
        first_peak = 100.0
        last_peak = 115.0

        growth_pct = ((last_peak - first_peak) / first_peak) * 100

        assert growth_pct == 15.0


class TestTracemalloc:
    """Test tracemalloc usage."""

    def test_tracemalloc_start_stop(self) -> None:
        """tracemalloc can be started and stopped."""
        import tracemalloc

        tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert isinstance(current, int)
        assert isinstance(peak, int)

    def test_tracemalloc_cleanup(self) -> None:
        """tracemalloc stopped even on error."""
        import tracemalloc

        tracemalloc.start()

        try:
            # Simulate work that may fail
            pass
        finally:
            tracemalloc.stop()

        # Should not raise - already stopped
        assert not tracemalloc.is_tracing()
```

**Acceptance Criteria**:

- [ ] `TestMemoryFootprint` class implemented
- [ ] `test_peak_memory_under_limit()` targets <500MB for 10K events
- [ ] `test_streaming_prevents_oom()` handles 100K events
- [ ] `@pytest.mark.performance` decorator applied
- [ ] Memory measured via `tracemalloc`
- [ ] `tracemalloc.stop()` called in finally block
- [ ] Failure messages include actual vs target values
- [ ] Streaming uses `batch_size=1000`
- [ ] Memory stability test validates no unbounded growth
- [ ] ≥95% test coverage

---

#### Issue 6.4.19 — Performance dashboard implementation

**Status**: 🔲 NOT STARTED

**Goal**: Implement Grafana dashboard for learning performance monitoring.

**Dossier Reference**: Section 8.2.2 "Dashboard Layout"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| slo_dashboards | `k0/telemetry/mixins/slo_dashboards.py` | Dashboard builder pattern |
| _config | `k0/telemetry/mixins/_config.py` | Dashboard template, panel defaults |

**Dashboard Layout (from dossier)**:

```
+------------------------------------------------------------------+
|                  P03 Learning Performance Dashboard               |
+------------------------------------------------------------------+
| Row 1: Budget Overview                                            |
|  - Learning Time % (gauge, target <5%)                            |
|  - Budget by Component (bar chart)                                |
|  - Skip Rate (time series)                                        |
+------------------------------------------------------------------+
| Row 2: Queue Health                                               |
|  - Queue Depth (gauge, warning >500)                              |
|  - Overflow Rate (time series)                                    |
|  - Batch Size Distribution (histogram)                            |
+------------------------------------------------------------------+
| Row 3: Operation Performance                                      |
|  - Latency p99 by Operation (time series)                         |
|  - Batch Duration (histogram)                                     |
|  - Parameter Update Rate (time series)                            |
+------------------------------------------------------------------+
| Row 4: Quality Indicators                                         |
|  - Signal Confidence Distribution (histogram)                     |
|  - Audit Write Success Rate (time series)                         |
|  - Learning vs Consolidation Time (stacked area)                  |
+------------------------------------------------------------------+
```

**PromQL Queries (from dossier Section 8.2.2)**:

| Panel | PromQL |
|-------|--------|
| Learning Time % | `p03_learning_time_ratio * 100` |
| Budget by Component | `p03_learning_budget_used_seconds{component=~"$component"}` |
| Skip Rate | `rate(p03_learning_skip_count[1h])` |
| Queue Depth | `p03_learning_queue_depth` |
| Overflow Rate | `rate(p03_queue_overflow_total[5m])` |
| Batch Size | `p03_learning_batch_size` |
| Latency p99 | `histogram_quantile(0.99, rate(p03_learning_operation_seconds_bucket[5m]))` |
| Parameter Updates | `rate(p03_learning_parameter_updates[5m])` |
| Signal Confidence | `p03_signal_confidence_bucket` |
| Audit Success Rate | `rate(p03_audit_writes_total{result="success"}[5m])` |

**Work To Do**:

1. [ ] Create `k0/telemetry/mixins/p03_dashboards.py`
2. [ ] Implement `build_p03_learning_performance_dashboard()` function
3. [ ] Implement Row 1: Budget Overview (3 panels)
4. [ ] Implement Row 2: Queue Health (3 panels)
5. [ ] Implement Row 3: Operation Performance (3 panels)
6. [ ] Implement Row 4: Quality Indicators (3 panels)
7. [ ] Use PromQL queries from dossier
8. [ ] Generate `k0/telemetry/generated/dashboards/p03_learning_performance.json`
9. [ ] Register in `__init__.py`
10. [ ] Create unit tests

**Implementation Pattern**:

```python
# k0/telemetry/mixins/p03_dashboards.py
"""P03 Learning Performance dashboard builder."""

from __future__ import annotations

from typing import Any

from ._config import (
    COLORS,
    DASHBOARD_VARIABLES,
    get_dashboard_template,
    get_panel_defaults,
    get_stat_panel_defaults,
)

__all__ = [
    "build_p03_learning_performance_dashboard",
]


def _add_grid_pos(panel: dict[str, Any], x: int, y: int, w: int, h: int) -> None:
    """Add grid position to panel."""
    panel["gridPos"] = {"x": x, "y": y, "w": w, "h": h}


def _add_target(
    panel: dict[str, Any],
    expr: str,
    legend: str = "",
    ref_id: str = "A",
) -> None:
    """Add Prometheus query target to panel."""
    panel["targets"].append(
        {
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "expr": expr,
            "legendFormat": legend,
            "refId": ref_id,
        }
    )


def _create_row(title: str, y_pos: int) -> dict[str, Any]:
    """Create a row panel."""
    return {
        "type": "row",
        "title": title,
        "collapsed": False,
        "gridPos": {"x": 0, "y": y_pos, "w": 24, "h": 1},
    }


def _create_gauge_panel(
    panel_id: int,
    title: str,
    expr: str,
    x: int,
    y: int,
    thresholds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a gauge panel."""
    panel = get_stat_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = title
    panel["type"] = "gauge"
    _add_grid_pos(panel, x, y, 8, 6)
    _add_target(panel, expr)

    if thresholds:
        panel["fieldConfig"]["defaults"]["thresholds"] = {
            "mode": "absolute",
            "steps": thresholds,
        }

    return panel


def _create_timeseries_panel(
    panel_id: int,
    title: str,
    expr: str,
    legend: str,
    x: int,
    y: int,
    w: int = 8,
) -> dict[str, Any]:
    """Create a time series panel."""
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = title
    panel["type"] = "timeseries"
    _add_grid_pos(panel, x, y, w, 6)
    _add_target(panel, expr, legend)

    return panel


def _create_histogram_panel(
    panel_id: int,
    title: str,
    expr: str,
    x: int,
    y: int,
) -> dict[str, Any]:
    """Create a histogram panel."""
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = title
    panel["type"] = "histogram"
    _add_grid_pos(panel, x, y, 8, 6)
    _add_target(panel, expr)

    return panel


def build_p03_learning_performance_dashboard() -> dict[str, Any]:
    """
    Build P03 Learning Performance dashboard.

    Layout per dossier Section 8.2.2:
    - Row 1: Budget Overview
    - Row 2: Queue Health
    - Row 3: Operation Performance
    - Row 4: Quality Indicators
    """
    dashboard = get_dashboard_template()
    dashboard["title"] = "P03 Learning Performance"
    dashboard["uid"] = "p03-learning-performance"
    dashboard["templating"]["list"] = DASHBOARD_VARIABLES

    panel_id = 1
    y_pos = 0

    # Row 1: Budget Overview
    dashboard["panels"].append(_create_row("Budget Overview", y_pos))
    y_pos += 1

    # Learning Time % (gauge, target <5%)
    dashboard["panels"].append(
        _create_gauge_panel(
            panel_id=panel_id,
            title="Learning Time %",
            expr="p03_learning_time_ratio * 100",
            x=0,
            y=y_pos,
            thresholds=[
                {"color": COLORS["green"], "value": None},
                {"color": COLORS["yellow"], "value": 3},
                {"color": COLORS["red"], "value": 5},
            ],
        )
    )
    panel_id += 1

    # Budget by Component (bar chart)
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Budget by Component"
    panel["type"] = "barchart"
    _add_grid_pos(panel, 8, y_pos, 8, 6)
    _add_target(
        panel,
        'p03_learning_budget_used_seconds{component=~"$component"}',
        "{{component}}",
    )
    dashboard["panels"].append(panel)
    panel_id += 1

    # Skip Rate (time series)
    dashboard["panels"].append(
        _create_timeseries_panel(
            panel_id=panel_id,
            title="Skip Rate",
            expr="rate(p03_learning_skip_count[1h])",
            legend="Skip Rate",
            x=16,
            y=y_pos,
        )
    )
    panel_id += 1
    y_pos += 7

    # Row 2: Queue Health
    dashboard["panels"].append(_create_row("Queue Health", y_pos))
    y_pos += 1

    # Queue Depth (gauge, warning >500)
    dashboard["panels"].append(
        _create_gauge_panel(
            panel_id=panel_id,
            title="Queue Depth",
            expr="p03_learning_queue_depth",
            x=0,
            y=y_pos,
            thresholds=[
                {"color": COLORS["green"], "value": None},
                {"color": COLORS["yellow"], "value": 500},
                {"color": COLORS["red"], "value": 1000},
            ],
        )
    )
    panel_id += 1

    # Overflow Rate (time series)
    dashboard["panels"].append(
        _create_timeseries_panel(
            panel_id=panel_id,
            title="Overflow Rate",
            expr="rate(p03_queue_overflow_total[5m])",
            legend="Overflow/s",
            x=8,
            y=y_pos,
        )
    )
    panel_id += 1

    # Batch Size Distribution (histogram)
    dashboard["panels"].append(
        _create_histogram_panel(
            panel_id=panel_id,
            title="Batch Size Distribution",
            expr="p03_learning_batch_size",
            x=16,
            y=y_pos,
        )
    )
    panel_id += 1
    y_pos += 7

    # Row 3: Operation Performance
    dashboard["panels"].append(_create_row("Operation Performance", y_pos))
    y_pos += 1

    # Latency p99 by Operation (time series)
    dashboard["panels"].append(
        _create_timeseries_panel(
            panel_id=panel_id,
            title="Latency p99 by Operation",
            expr="histogram_quantile(0.99, rate(p03_learning_operation_seconds_bucket[5m]))",
            legend="{{operation}}",
            x=0,
            y=y_pos,
        )
    )
    panel_id += 1

    # Batch Duration (histogram)
    dashboard["panels"].append(
        _create_histogram_panel(
            panel_id=panel_id,
            title="Batch Duration",
            expr="p03_learning_batch_duration_seconds_bucket",
            x=8,
            y=y_pos,
        )
    )
    panel_id += 1

    # Parameter Update Rate (time series)
    dashboard["panels"].append(
        _create_timeseries_panel(
            panel_id=panel_id,
            title="Parameter Update Rate",
            expr="rate(p03_learning_parameter_updates[5m])",
            legend="Updates/s",
            x=16,
            y=y_pos,
        )
    )
    panel_id += 1
    y_pos += 7

    # Row 4: Quality Indicators
    dashboard["panels"].append(_create_row("Quality Indicators", y_pos))
    y_pos += 1

    # Signal Confidence Distribution (histogram)
    dashboard["panels"].append(
        _create_histogram_panel(
            panel_id=panel_id,
            title="Signal Confidence Distribution",
            expr="p03_signal_confidence_bucket",
            x=0,
            y=y_pos,
        )
    )
    panel_id += 1

    # Audit Write Success Rate (time series)
    dashboard["panels"].append(
        _create_timeseries_panel(
            panel_id=panel_id,
            title="Audit Write Success Rate",
            expr='rate(p03_audit_writes_total{result="success"}[5m])',
            legend="Success/s",
            x=8,
            y=y_pos,
        )
    )
    panel_id += 1

    # Learning vs Consolidation Time (stacked area)
    panel = get_panel_defaults()
    panel["id"] = panel_id
    panel["title"] = "Learning vs Consolidation Time"
    panel["type"] = "timeseries"
    _add_grid_pos(panel, 16, y_pos, 8, 6)
    _add_target(
        panel,
        "p03_learning_time_seconds",
        "Learning",
        "A",
    )
    _add_target(
        panel,
        "p03_consolidation_time_seconds",
        "Consolidation",
        "B",
    )
    panel["fieldConfig"]["defaults"]["custom"] = {
        "stacking": {"mode": "normal"},
        "fillOpacity": 50,
    }
    dashboard["panels"].append(panel)

    return dashboard
```

**Test Pattern**:

```python
# tests/k0/telemetry/mixins/test_p03_dashboards.py
"""Tests for P03 dashboard builder."""

import json

import pytest


class TestP03LearningPerformanceDashboard:
    """Test P03 Learning Performance dashboard."""

    def test_dashboard_structure(self) -> None:
        """Dashboard has required structure."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        assert dashboard["title"] == "P03 Learning Performance"
        assert dashboard["uid"] == "p03-learning-performance"
        assert "panels" in dashboard

    def test_has_four_rows(self) -> None:
        """Dashboard has 4 row panels."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        rows = [p for p in dashboard["panels"] if p.get("type") == "row"]
        assert len(rows) == 4

        row_titles = [r["title"] for r in rows]
        assert "Budget Overview" in row_titles
        assert "Queue Health" in row_titles
        assert "Operation Performance" in row_titles
        assert "Quality Indicators" in row_titles

    def test_budget_overview_panels(self) -> None:
        """Row 1 has correct panels."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        panel_titles = [p["title"] for p in dashboard["panels"]]

        assert "Learning Time %" in panel_titles
        assert "Budget by Component" in panel_titles
        assert "Skip Rate" in panel_titles

    def test_queue_health_panels(self) -> None:
        """Row 2 has correct panels."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        panel_titles = [p["title"] for p in dashboard["panels"]]

        assert "Queue Depth" in panel_titles
        assert "Overflow Rate" in panel_titles
        assert "Batch Size Distribution" in panel_titles

    def test_dashboard_imports_as_valid_json(self) -> None:
        """Dashboard serializes to valid JSON."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        # Should not raise
        json_str = json.dumps(dashboard, indent=2)
        parsed = json.loads(json_str)

        assert parsed["uid"] == "p03-learning-performance"

    def test_learning_time_gauge_thresholds(self) -> None:
        """Learning Time gauge has <5% threshold."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        gauge = next(
            p for p in dashboard["panels"]
            if p.get("title") == "Learning Time %"
        )

        thresholds = gauge["fieldConfig"]["defaults"]["thresholds"]["steps"]
        threshold_values = [t["value"] for t in thresholds if t["value"]]

        assert 5 in threshold_values  # Red threshold at 5%

    def test_queue_depth_gauge_threshold(self) -> None:
        """Queue Depth gauge has >500 warning threshold."""
        from k0.telemetry.mixins.p03_dashboards import (
            build_p03_learning_performance_dashboard,
        )

        dashboard = build_p03_learning_performance_dashboard()

        gauge = next(
            p for p in dashboard["panels"]
            if p.get("title") == "Queue Depth"
        )

        thresholds = gauge["fieldConfig"]["defaults"]["thresholds"]["steps"]
        threshold_values = [t["value"] for t in thresholds if t["value"]]

        assert 500 in threshold_values  # Warning at 500
```

**Acceptance Criteria**:

- [ ] `build_p03_learning_performance_dashboard()` function implemented
- [ ] Dashboard has 4 rows per dossier layout
- [ ] Row 1: Budget Overview (Learning Time %, Budget by Component, Skip Rate)
- [ ] Row 2: Queue Health (Queue Depth, Overflow Rate, Batch Size Distribution)
- [ ] Row 3: Operation Performance (Latency p99, Batch Duration, Parameter Updates)
- [ ] Row 4: Quality Indicators (Signal Confidence, Audit Success, Learning vs Consolidation)
- [ ] All panels use PromQL queries from dossier Section 8.2.2
- [ ] Dashboard serializes to valid JSON
- [ ] Dashboard imports cleanly into Grafana
- [ ] Learning Time gauge threshold at 5%
- [ ] Queue Depth gauge warning at 500
- [ ] ≥95% test coverage

---

#### Issue 6.4.20 — Performance integration tests

**Status**: 🔲 NOT STARTED

**Goal**: Comprehensive integration testing of all performance components.

**Dossier Reference**: Section 10.4 "Test Categories", Section 15 "K0 QoS Integration"

**K0 Components to Leverage**:

| Component | Path | What to Use |
|-----------|------|-------------|
| TokenBucketScheduler | `k0/modules/p03/qos/scheduler.py` | Token acquisition/release |
| QoSContext | `k0/modules/p03/qos/context.py` | Budget enforcement |
| BatchSizer | `k0/modules/p03/qos/batch_sizer.py` | Adaptive sizing |
| LearningBudgetTracker | `k0/modules/p03/qos/learning_budget.py` | 5% budget |
| StreamingBatchProcessor | `k0/modules/p03/performance/streaming.py` | Memory management |
| EmbeddingCache | `k0/modules/p03/performance/cache.py` | LRU/TTL |

**Work To Do**:

1. [ ] Create `tests/k0/pipelines/p03/performance/test_qos_integration.py`
2. [ ] Create `tests/k0/pipelines/p03/performance/test_learning_budget.py`
3. [ ] Create `tests/k0/pipelines/p03/performance/test_streaming.py`
4. [ ] Create `tests/k0/pipelines/p03/performance/test_caching.py`
5. [ ] Test scheduler token acquisition/release
6. [ ] Test QoS budget enforcement (fanout, top_k)
7. [ ] Test adaptive batch sizing under contention
8. [ ] Test 5% budget enforcement
9. [ ] Test skip behavior when over budget
10. [ ] Test streaming memory release
11. [ ] Test embedding cache LRU eviction
12. [ ] Test cache hit/miss metrics

**Implementation Pattern**:

```python
# tests/k0/pipelines/p03/performance/test_qos_integration.py
"""
QoS integration tests for P03.

Tests scheduler token acquisition, budget enforcement,
and adaptive batch sizing.

Dossier Reference: Section 15 K0 QoS Integration
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestSchedulerIntegration:
    """Test TokenBucketScheduler K0 integration."""

    @pytest.mark.asyncio
    async def test_token_acquisition_release_cycle(self) -> None:
        """Scheduler acquires and releases tokens correctly."""
        from k0.modules.p03.qos.scheduler import TokenBucketScheduler

        scheduler = TokenBucketScheduler(
            max_tokens=10,
            refill_rate=1.0,
        )

        # Acquire tokens
        acquired = await scheduler.acquire(5)
        assert acquired is True
        assert scheduler.available_tokens == 5

        # Release tokens
        await scheduler.release(3)
        assert scheduler.available_tokens == 8

    @pytest.mark.asyncio
    async def test_token_exhaustion_blocks(self) -> None:
        """Scheduler blocks when tokens exhausted."""
        from k0.modules.p03.qos.scheduler import TokenBucketScheduler

        scheduler = TokenBucketScheduler(
            max_tokens=5,
            refill_rate=0.1,  # Slow refill
        )

        # Exhaust tokens
        await scheduler.acquire(5)

        # Next acquire should wait or fail
        acquired = await scheduler.try_acquire(3, timeout=0.1)
        assert acquired is False


@pytest.mark.integration
class TestQoSBudgetEnforcement:
    """Test QoS budget enforcement."""

    @pytest.mark.asyncio
    async def test_fanout_limited_by_qos(self, qos_context) -> None:
        """Fanout respects QoS limits."""
        qos_context.max_fanout = 5

        # Should limit fanout
        fanout = qos_context.get_effective_fanout(requested=10)

        assert fanout <= 5

    @pytest.mark.asyncio
    async def test_top_k_limited_by_qos(self, qos_context) -> None:
        """Top-K respects QoS limits."""
        qos_context.max_top_k = 100

        # Should limit top_k
        top_k = qos_context.get_effective_top_k(requested=500)

        assert top_k <= 100


@pytest.mark.integration
class TestAdaptiveBatchSizing:
    """Test adaptive batch sizing under contention."""

    @pytest.mark.asyncio
    async def test_batch_size_reduces_under_contention(
        self,
        batch_sizer,
    ) -> None:
        """Batch size reduces when contention detected."""
        from k0.modules.p03.qos.batch_sizer import BatchSizer

        sizer = BatchSizer(
            min_size=10,
            max_size=1000,
            initial_size=500,
        )

        # Simulate contention
        for _ in range(5):
            sizer.record_contention()

        new_size = sizer.get_current_size()
        assert new_size < 500

    @pytest.mark.asyncio
    async def test_batch_size_increases_without_contention(
        self,
        batch_sizer,
    ) -> None:
        """Batch size increases when no contention."""
        from k0.modules.p03.qos.batch_sizer import BatchSizer

        sizer = BatchSizer(
            min_size=10,
            max_size=1000,
            initial_size=100,
        )

        # Simulate success
        for _ in range(10):
            sizer.record_success()

        new_size = sizer.get_current_size()
        assert new_size > 100
```

```python
# tests/k0/pipelines/p03/performance/test_learning_budget.py
"""
Learning budget tests for P03.

Tests 5% budget enforcement and skip behavior.

Dossier Reference: Section 8.2 Learning Metrics
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestLearningBudgetEnforcement:
    """Test 5% learning budget enforcement."""

    @pytest.mark.asyncio
    async def test_budget_enforced_at_5_percent(self) -> None:
        """Learning stays within 5% budget."""
        from k0.modules.p03.qos.learning_budget import LearningBudgetTracker

        tracker = LearningBudgetTracker(budget_percent=5.0)

        # Simulate cycle with learning
        tracker.record_consolidation_time(100.0)  # 100s consolidation
        tracker.record_learning_time(4.0)  # 4s learning

        # Within budget
        assert tracker.is_within_budget() is True
        assert tracker.get_usage_percent() < 5.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_triggers_skip(self) -> None:
        """Exceeding budget triggers skip."""
        from k0.modules.p03.qos.learning_budget import LearningBudgetTracker

        tracker = LearningBudgetTracker(budget_percent=5.0)

        # Exceed budget
        tracker.record_consolidation_time(100.0)
        tracker.record_learning_time(10.0)  # 10% - exceeds 5%

        assert tracker.is_within_budget() is False
        assert tracker.should_skip_learning() is True

    @pytest.mark.asyncio
    async def test_component_budget_allocation(self) -> None:
        """Component budgets allocated correctly."""
        from k0.modules.p03.qos.learning_budget import LearningBudgetTracker

        tracker = LearningBudgetTracker(budget_percent=5.0)

        # Record by component
        tracker.record_component_time("feedback_queue", 1.0)
        tracker.record_component_time("embedding_update", 2.0)
        tracker.record_component_time("audit_write", 0.5)

        breakdown = tracker.get_component_breakdown()

        assert "feedback_queue" in breakdown
        assert breakdown["feedback_queue"] == 1.0
```

```python
# tests/k0/pipelines/p03/performance/test_streaming.py
"""
Streaming processor tests for P03.

Tests memory release and threshold triggers.

Dossier Reference: Section 10.5 Performance Tests
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestStreamingMemoryManagement:
    """Test streaming processor memory management."""

    @pytest.mark.asyncio
    async def test_memory_released_after_batch(
        self,
        streaming_processor,
        p03_fixtures,
    ) -> None:
        """Memory released after processing batch."""
        import tracemalloc

        events = p03_fixtures.create_random_events(n=1000)

        tracemalloc.start()
        initial = tracemalloc.get_traced_memory()[0]

        async for batch in streaming_processor.process_batches(events):
            pass  # Process each batch

        final = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        # Memory should not grow significantly
        growth_mb = (final - initial) / (1024 * 1024)
        assert growth_mb < 50  # Less than 50MB growth

    @pytest.mark.asyncio
    async def test_memory_threshold_triggers_flush(
        self,
        streaming_processor,
    ) -> None:
        """High memory triggers batch flush."""
        from k0.modules.p03.performance.streaming import StreamingBatchProcessor

        processor = StreamingBatchProcessor(
            memory_threshold_mb=100,
        )

        # Force high memory condition
        processor._force_memory_pressure = True

        should_flush = processor.should_flush_batch()
        assert should_flush is True

    @pytest.mark.asyncio
    async def test_batch_metrics_emitted(
        self,
        streaming_processor,
        metrics_collector,
    ) -> None:
        """Batch processing emits metrics."""
        async for batch in streaming_processor.process_batches(
            [{"id": i} for i in range(100)]
        ):
            pass

        # Verify metrics emitted
        assert metrics_collector.get("p03_streaming_batches_total") > 0
```

```python
# tests/k0/pipelines/p03/performance/test_caching.py
"""
Embedding cache tests for P03.

Tests LRU eviction and TTL expiration.

Dossier Reference: Section 6.3 Caching
"""

from __future__ import annotations

import time

import pytest


@pytest.mark.integration
class TestEmbeddingCacheLRU:
    """Test LRU eviction behavior."""

    @pytest.mark.asyncio
    async def test_lru_eviction_on_capacity(self) -> None:
        """LRU eviction when capacity exceeded."""
        from k0.modules.p03.performance.cache import EmbeddingCache

        cache = EmbeddingCache(max_size=3)

        # Fill cache
        cache.put("key1", [0.1] * 768)
        cache.put("key2", [0.2] * 768)
        cache.put("key3", [0.3] * 768)

        # Access key1 to make it recent
        _ = cache.get("key1")

        # Add new item - should evict key2 (least recently used)
        cache.put("key4", [0.4] * 768)

        assert cache.get("key1") is not None
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None


@pytest.mark.integration
class TestEmbeddingCacheTTL:
    """Test TTL expiration behavior."""

    @pytest.mark.asyncio
    async def test_ttl_expiration(self) -> None:
        """Items expire after TTL."""
        from k0.modules.p03.performance.cache import EmbeddingCache

        cache = EmbeddingCache(
            max_size=100,
            ttl_seconds=0.1,  # 100ms TTL
        )

        cache.put("key1", [0.1] * 768)

        # Immediately available
        assert cache.get("key1") is not None

        # Wait for TTL
        time.sleep(0.15)

        # Should be expired
        assert cache.get("key1") is None


@pytest.mark.integration
class TestCacheMetrics:
    """Test cache hit/miss metrics."""

    @pytest.mark.asyncio
    async def test_cache_hit_metric(
        self,
        embedding_cache,
        metrics_collector,
    ) -> None:
        """Cache hit increments metric."""
        embedding_cache.put("key1", [0.1] * 768)
        _ = embedding_cache.get("key1")

        assert metrics_collector.get("p03_cache_hits_total") == 1

    @pytest.mark.asyncio
    async def test_cache_miss_metric(
        self,
        embedding_cache,
        metrics_collector,
    ) -> None:
        """Cache miss increments metric."""
        _ = embedding_cache.get("nonexistent")

        assert metrics_collector.get("p03_cache_misses_total") == 1

    @pytest.mark.asyncio
    async def test_cache_hit_rate(
        self,
        embedding_cache,
    ) -> None:
        """Cache hit rate calculated correctly."""
        embedding_cache.put("key1", [0.1] * 768)

        # 2 hits
        _ = embedding_cache.get("key1")
        _ = embedding_cache.get("key1")

        # 1 miss
        _ = embedding_cache.get("key2")

        hit_rate = embedding_cache.get_hit_rate()
        assert abs(hit_rate - 0.666) < 0.01  # ~66.7%
```

**Test Pattern**:

```python
# tests/k0/pipelines/p03/performance/conftest.py
"""Fixtures for performance integration tests."""

import pytest

from tests.fixtures.p03 import P03TestFixtures


@pytest.fixture
def p03_fixtures() -> P03TestFixtures:
    """Provide P03 test fixtures."""
    return P03TestFixtures()


@pytest.fixture
def qos_context():
    """Provide mock QoS context."""
    from k0.modules.p03.qos.context import QoSContext

    return QoSContext(
        tenant_id="test_tenant",
        max_fanout=10,
        max_top_k=200,
    )


@pytest.fixture
def batch_sizer():
    """Provide batch sizer instance."""
    from k0.modules.p03.qos.batch_sizer import BatchSizer

    return BatchSizer(
        min_size=10,
        max_size=1000,
        initial_size=100,
    )


@pytest.fixture
def streaming_processor():
    """Provide streaming processor instance."""
    from k0.modules.p03.performance.streaming import StreamingBatchProcessor

    return StreamingBatchProcessor(batch_size=100)


@pytest.fixture
def embedding_cache():
    """Provide embedding cache instance."""
    from k0.modules.p03.performance.cache import EmbeddingCache

    return EmbeddingCache(max_size=1000)


@pytest.fixture
def metrics_collector():
    """Provide mock metrics collector."""
    class MockMetrics:
        def __init__(self):
            self._counters = {}

        def get(self, name: str) -> int:
            return self._counters.get(name, 0)

        def inc(self, name: str, value: int = 1) -> None:
            self._counters[name] = self._counters.get(name, 0) + value

    return MockMetrics()
```

**Acceptance Criteria**:

- [ ] `test_qos_integration.py` — Scheduler token tests implemented
- [ ] `test_qos_integration.py` — QoS budget enforcement tests (fanout, top_k)
- [ ] `test_qos_integration.py` — Adaptive batch sizing tests
- [ ] `test_learning_budget.py` — 5% budget enforcement validated
- [ ] `test_learning_budget.py` — Component budget allocation tested
- [ ] `test_learning_budget.py` — Skip behavior when over budget tested
- [ ] `test_streaming.py` — Memory release after batch validated
- [ ] `test_streaming.py` — Memory threshold triggers tested
- [ ] `test_streaming.py` — Batch metrics emission tested
- [ ] `test_caching.py` — LRU eviction tested
- [ ] `test_caching.py` — TTL expiration tested
- [ ] `test_caching.py` — Cache hit/miss metrics tested
- [ ] All tests marked with `@pytest.mark.integration`
- [ ] ≥90% line coverage for qos module
- [ ] All K0 integrations tested

---

## Part D: Acceptance Criteria Summary

### Epic 6.1 Acceptance

- [ ] All P03 metrics registered with K0 MetricsExporter
- [ ] Metrics scrapable via Prometheus endpoint
- [ ] Full trace visible in Jaeger/Zipkin
- [ ] Span hierarchy matches dossier specification
- [ ] All logs emit as valid JSON
- [ ] Dashboards importable into Grafana
- [ ] ≥90% line coverage for observability module

### Epic 6.2 Acceptance

- [ ] All 4 error types correctly routed
- [ ] TRANSIENT errors retry up to max_attempts before DLQ
- [ ] Circuit breakers implement CLOSED→OPEN→HALF_OPEN→CLOSED transitions
- [ ] All 3 partial failure strategies implemented
- [ ] All k0ctl dlq commands functional
- [ ] ≥90% line coverage for resilience module

### Epic 6.3 Acceptance

- [ ] RLS enabled on all 6 learning tables
- [ ] Cross-space access returns empty (not other space's data)
- [ ] All 3 privacy bands enforced correctly
- [ ] GDPR erasure cascades to all tables
- [ ] ≥90% line coverage for security module

### Epic 6.4 Acceptance

- [ ] Token acquired before batch processing
- [ ] Batch size adapts to K0 scheduler contention
- [ ] Phase latency tracked with histograms
- [ ] SLO targets configurable
- [ ] Performance tests validate baselines

---

## Part E: Test Coverage Requirements

| Module | Required Coverage | Test Location |
|--------|-------------------|---------------|
| observability/ | ≥90% | `tests/k0/modules/consolidation/observability/` |
| resilience/ | ≥90% | `tests/k0/modules/consolidation/resilience/` |
| security/ | ≥90% | `tests/k0/modules/consolidation/security/` |
| qos/ | ≥90% | `tests/k0/modules/consolidation/qos/` |

---

## Part F: Governance Checklist

### Before Starting M6

- [ ] Run `python -m governance.k0.scripts.sync --report` — must show SYNCED
- [ ] Verify M5 completion status
- [ ] Confirm M5 test suite passing (all R6-R8 tests)

### After Each Epic

- [ ] Run governance sync to verify no drift
- [ ] Update `k0_architecture_master.md` if new components added
- [ ] Verify test coverage meets 90% threshold

### Before Marking M6 Complete

- [ ] All 4 epics completed
- [ ] All tests passing
- [ ] Governance sync shows SYNCED
- [ ] Documentation updated

---

## Appendix: Dossier Cross-Reference

| Dossier Section | Epic | Primary Issues |
|-----------------|------|----------------|
| §8.2 Metric Definitions | 6.1 | 6.1.1-6.1.9 |
| §8.3 Distributed Tracing | 6.1 | 6.1.10-6.1.11 |
| §8.4 Structured Logging | 6.1 | 6.1.12-6.1.13 |
| §8.5 Dashboards | 6.1 | 6.1.17 |
| §8.6 Alerting Rules | 6.1 | 6.1.18 |
| §13.2 Error Classification | 6.2 | 6.2.1-6.2.2 |
| §13.5 Retry Strategy | 6.2 | 6.2.4 |
| §13.6 Circuit Breaker | 6.2 | 6.2.5-6.2.8 |
| §13.7 Partial Failure | 6.2 | 6.2.9 |
| §6.21 st_feedback_quarantine | 6.2 | 6.2.10-6.2.15 |
| §14.2 Privacy Bands | 6.3 | 6.3.10-6.3.11 |
| §14.7 GDPR | 6.3 | 6.3.14-6.3.16 |
| §14.11 Learning Isolation | 6.3 | 6.3.1-6.3.5 |
| §15.2 K0 Scheduler | 6.4 | 6.4.1-6.4.2 |
| §15.3 Performance Baselines | 6.4 | 6.4.4-6.4.5 |
| §15.4 Batch Optimization | 6.4 | 6.4.3 |



Let me investigate whether these subdirectories are actually wired into the P03 execution flow:

Searched for regex `from.*\.ops|from.*\.security|from.*\.feedback|from.*\.learning|from.*\.maintenance|from.*\.cache|from.*\.qos|from.*\.api` (`**/k0/pipelines/p03/phases/*.py`), no results

Searched for regex `from k0\.pipelines\.p03\.(ops|security|feedback|learning|maintenance|cache|qos|api)` (`**/k0/pipelines/p03/phases/**`), no results

Searched for regex `from \.\.ops|from \.ops|from k0\.pipelines\.p03\.ops`, 20 results

These are only tests! Let me check if the actual phases import and use these modules:

Searched for regex `from k0\.pipelines\.p03\.ops`, 20 results

All results are from tests. Let me search specifically in the production code:

Searched for regex `from.*ops|import.*ops` (`**/k0/pipelines/p03/**`), 20 results

Let me search directly in the phases source code, sequential_runner, and root files:

Ran terminal command: Get-ChildItem D:\familyos\k0\pipelines\p03\phases\*.py | ForEach-Object { $file = $_.Name; Select-String -Path $_.FullName -Pattern "from.*ops|from.*security|from.*feedback|from.*learning|from.*maintenance|from.*cache|from.*qos" | ForEach-Object { "$file`: $_" } }

Ran terminal command: Get-ChildItem D:\familyos\k0\pipelines\p03\*.py | ForEach-Object { $file = $_.Name; Select-String -Path $_.FullName -Pattern "from k0\.pipelines\.p03\.(ops|security|feedback|learning|maintenance|cache|qos|api)" | ForEach-Object { "$file`: $_" } }

Only 2 imports! Let me see what's actually exported/used:

Read [](file:///d%3A/familyos/k0/pipelines/p03/__init__.py#130-130), lines 130 to 200

Now let me see what's in the __init__.py and check if metrics is connected:

Read [](file:///d%3A/familyos/k0/pipelines/p03/ops/__init__.py#1-1), lines 1 to 100

Now let me check which of these are actually USED in the execution:

Searched for regex `P03MetricsRegistry|P03ErrorHandler|P03CircuitBreaker|FormulaTracer` (`**/k0/pipelines/p03/*.py`), 20 results

All matches are in tests! Let me check what the sequential_runner actually does with P03MetricsRegistry:

Read [](file:///d%3A/familyos/k0/pipelines/p03/sequential_runner.py#20-20), lines 20 to 50

Searched for text `P03MetricsRegistry` (`**/k0/pipelines/p03/sequential_runner.py`), 3 results

Let me check where the metrics_registry is created in the phase_interface:

Searched for text `metrics_registry` (`**/k0/pipelines/p03/phase_interface.py`), 2 results

Read [](file:///d%3A/familyos/k0/pipelines/p03/phase_interface.py#180-180), lines 180 to 230

Now I understand. The metrics_registry is optional and defaults to None. Let me check if it's wired up anywhere in the adapter or kernel:

Searched for regex `P03MetricsRegistry\(|metrics_registry.*=.*P03` (`**/k0/**/*.py`), 9 results

Searched for regex `metrics_registry|P03MetricsRegistry` (`**/k0/runtime/*.py`), no results

Let me now check all the subdirectories to see what's ACTUALLY connected:

Read [](file:///d%3A/familyos/k0/pipelines/p03/api)

Read [](file:///d%3A/familyos/k0/pipelines/p03/ops)

Read [](file:///d%3A/familyos/k0/pipelines/p03/security)

Read [](file:///d%3A/familyos/k0/pipelines/p03/learning)

Read [](file:///d%3A/familyos/k0/pipelines/p03/feedback)

Read [](file:///d%3A/familyos/k0/pipelines/p03/maintenance)

Read [](file:///d%3A/familyos/k0/pipelines/p03/cache)

Read [](file:///d%3A/familyos/k0/pipelines/p03/qos)

Now let me comprehensively check which of these are ACTUALLY imported/used in the main execution flow:

Ran terminal command: cd D:\familyos; Get-ChildItem k0/pipelines/p03/*.py -Recurse | Where-Object { $_.FullName -notmatch "tests|__pycache__" -and $_.DirectoryName -notmatch "\\(api|ops|security|learning|feedback|maintenance|cache|qos)\\" } | ForEach-Object { Select-String -Path $_.FullName -Pattern "from k0\.pipelines\.p03\.(api|ops|security|learning|feedback|maintenance|cache|qos)" } | Select-Object -First 30

Now let me focus on the actual MAIN execution flow - the phases and runner:

Ran terminal command: @("k0\pipelines\p03\sequential_runner.py", "k0\pipelines\p03\__init__.py", "k0\pipelines\p03\observability.py", "k0\pipelines\p03\phases\r0_batch_selector.py", "k0\pipelines\p03\phases\r1_importance_scorer.py", "k0\pipelines\p03\phases\r4_kg_consolidator.py", "k0\pipelines\p03\phases\r6_staging.py", "k0\pipelines\p03\phases\r7_truth_writer.py", "k0\pipelines\p03\phases\r8_event_emitter.py") | ForEach-Object { if (Test-Path $_) { Select-String -Path $_ -Pattern "from k0\.pipelines\.p03\.(api|ops|security|learning|feedback|maintenance|cache|qos)" } }

Now I have the full picture. Let me summarize what's connected vs what's NOT:

---

## 🔌 P03 Subdirectory Wiring Status

### ❌ **NOT CONNECTED TO EXECUTION FLOW**

| Subdirectory | Files | Status | Why Not Connected |
|--------------|-------|--------|-------------------|
| **api/** | `quarantine_review.py` | ❌ ORPHAN | Not imported by any phase or runner |
| **security/** | 8 files (rls_verifier, tombstone, privacy_band, etc.) | ❌ ORPHAN | Not imported by any phase or runner |
| **learning/** | 3 files (async_audit, feedback_queue, learning_anomaly_detector) | ❌ ORPHAN | Not imported by any phase or runner |
| **feedback/** | 4 files (anomaly_detector, quarantine_detector, rate_limiter, velocity_detector) | ❌ ORPHAN | Not imported by any phase or runner |
| **maintenance/** | `quarantine_cleanup.py` | ❌ ORPHAN | Not imported by any phase or runner |
| **cache/** | `embedding_cache.py` | ❌ ORPHAN | Not imported by any phase or runner |

### ⚠️ **PARTIALLY CONNECTED**

| Subdirectory | What's Connected | What's NOT |
|--------------|------------------|-----------|
| **ops/** | `P03MetricsRegistry` imported by sequential_runner.py | BUT `metrics_registry` is never instantiated in production! It stays `None` |
| **qos/** | `P03QoSContext`, `P03SchedulerIntegration` exported in __init__.py | But phases don't actually use them |

### ✅ **WHAT'S ACTUALLY CONNECTED**

Only the **root-level files** are wired into execution:
- sequential_runner.py → orchestrates phases
- `envelope.py`, `context.py` → data containers
- phase_interface.py → phase protocol
- observability.py → phase transition logging
- `runner_contract.py` → phase IDs and transitions
- `phases/*.py` → R0-R8 implementations

---

## 🚨 **THE REAL PROBLEM**

The subdirectories in the mermaid diagram (`api/`, `ops/`, `security/`, `learning/`, `feedback/`, `maintenance/`, `cache/`, `qos/`) are **designed but NOT wired**:

1. **Tests exist** for all these modules ✅
2. **Code is complete** ✅
3. **Imports are NOT in phases** ❌
4. **No integration in `sequential_runner`** ❌
5. **No initialization in app.py** ❌

### Example: What SHOULD Happen but DOESN'T

Per the diagram, R0 should:
- Use `cache/embedding_cache.py` for LRU caching
- Use `qos/adaptive_batch_sizer.py` for batch sizing
- Use `security/input_sanitizer.py` for input sanitization

Per the diagram, SequentialRunner should:
- Use `ops/circuit_breaker.py` to wrap phase calls
- Use `ops/error_handler.py` for DLQ routing
- Use `ops/tracing.py` for OpenTelemetry spans

**None of this is actually called.**

---

## 📋 **What Needs Wiring**

To connect these modules, you'd need to:

1. **Instantiate P03MetricsRegistry** in app.py or sequential_adapter.py and pass to context
2. **Import and call circuit breakers** in each phase
3. **Import and use error handlers** in sequential_runner.py
4. **Wire feedback detectors** to a bus consumer
5. **Wire maintenance jobs** to the scheduler
6. **Wire security modules** to pre/post hooks

Want me to create the wiring for any specific subdirectory?
