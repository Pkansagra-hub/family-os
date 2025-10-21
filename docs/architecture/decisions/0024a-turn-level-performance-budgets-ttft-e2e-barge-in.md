# ADR-0024a: Turn-Level Performance Budgets (TTFT, E2E, Barge-In)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Last Updated:** 2025-01-15 (M4 Context: See ADR-0078 for tool call batching latency targets)
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0024 (Performance Budgets P95 Targets)](0024-performance-budgets-p95-targets.md)
**Category:** Infrastructure (Layer 5) - Performance SLO
**Related ADRs:**
- [ADR-0028 (Weighted Fair Queuing Scheduler)](0028-weighted-fair-queuing-scheduler.md)
- [ADR-0078 (Tool Call Batching Pipeline - **NEW M4**)](0078-tool-call-batching-pipeline.md)

---

## Context

### Problem Statement

K1 must deliver conversational experiences that feel **instant and responsive**. Without performance budgets, latency degrades unpredictably:

- **Slow First Response:** TTFT >500ms feels laggy (users perceive delay)
- **Long Turn Duration:** E2E >5s users lose patience
- **Unresponsive Barge-In:** Cancel latency >300ms feels broken
- **No Accountability:** No measurable targets, no alerts when degraded

**Performance is a Feature - Requires Explicit Budgets:**

Define **turn-level performance budgets** with P95 targets:

1. **TTFT (Time to First Token):** <150ms P95 (user perceives instant response)
2. **E2E Turn Latency:** <2000ms P95 (complete turn from user message to AI response)
3. **Barge-In Cancel:** <120ms P95 (instant cancellation when user interrupts)

**Key Challenges:**

1. **Budget Decomposition:** TTFT = ASR + Intent + Orchestrator (how to allocate?)
2. **Measurement:** Instrument all components with trace_id for end-to-end tracking
3. **Enforcement:** Alert when P95 exceeds 105% of target (early warning)
4. **Observability:** Dashboards showing P50/P95/P99 trends

### Current Landscape

**Industry Performance Budget Patterns:**

1. **Google Search (SERP)**:
   - **Target:** <200ms TTFT, <1000ms full page load
   - **Enforcement:** Automated performance regression tests
   - **Monitoring:** Real User Monitoring (RUM) + synthetic checks

2. **Amazon Alexa**:
   - **Target:** <1500ms E2E (wake word → response)
   - **Enforcement:** P95 alerts, automatic rollback on regression
   - **Monitoring:** CloudWatch + custom metrics

3. **Microsoft Teams (VoIP)**:
   - **Target:** <150ms E2E latency (audio roundtrip)
   - **Enforcement:** Network jitter buffer, adaptive bitrate
   - **Monitoring:** Telemetry on all calls

4. **OpenAI ChatGPT**:
   - **Target:** ~500ms TTFT (streaming response)
   - **Enforcement:** Model optimization, inference caching
   - **Monitoring:** Prometheus + Grafana dashboards

### K1 Requirements

**Turn-Level Budget Definitions:**

| Metric | P50 Target | P95 Target | P99 Target | Rationale |
|--------|-----------|-----------|-----------|-----------|
| TTFT | 100ms | 150ms | 200ms | User perceives <200ms as instant |
| E2E Turn | 1200ms | 2000ms | 2500ms | Conversational responsiveness |
| Barge-In Cancel | 80ms | 120ms | 180ms | Instant cancellation feel |

**Budget Decomposition (TTFT = 150ms):**

- ASR (Speech-to-Text): 80ms (53%)
- Intent Classification: 50ms (33%)
- Orchestrator (3-phase): 20ms (13%)
- **Total:** 150ms P95

**Performance Targets (P95):**

| Metric | Target | Alert Threshold | Rationale |
|--------|--------|----------------|-----------|
| TTFT | 150ms | 157ms (105%) | Early warning before user-visible impact |
| E2E Turn | 2000ms | 2100ms (105%) | Prevent conversational lag |
| Barge-In | 120ms | 126ms (105%) | Maintain instant cancellation feel |

---

## Decision

We will implement **Turn-Level Performance Budgets** as:

1. **BudgetTracker Class:** Python class tracking turn-level latencies
2. **Prometheus Metrics:** Histograms for TTFT, E2E, Barge-In with P50/P95/P99
3. **Alert Rules:** Prometheus alerts when P95 exceeds 105% of budget
4. **Grafana Dashboard:** Visualization of all turn-level budgets
5. **Trace Integration:** Use `cognitive_trace_id` for end-to-end tracking

### Performance Budget Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Turn Execution - Performance Budget Tracking                 │
│                                                              │
│  TTFT Budget (150ms P95):                                    │
│    User Speech → ASR (80ms)                                  │
│                → Intent Classification (50ms)                │
│                → Orchestrator 3-Phase (20ms)                 │
│                → First Token Generated                       │
│    Total: 150ms P95                                          │
│                                                              │
│  E2E Turn Budget (2000ms P95):                               │
│    User Speech → TTFT (150ms)                                │
│                → Model Inference (1500ms)                    │
│                → TTS Synthesis (300ms)                       │
│                → Audio Playback (50ms)                       │
│    Total: 2000ms P95                                         │
│                                                              │
│  Barge-In Budget (120ms P95):                                │
│    User Interruption → Cancel Signal (20ms)                  │
│                      → Stop Inference (50ms)                 │
│                      → Stop TTS (30ms)                       │
│                      → Stop Audio (20ms)                     │
│    Total: 120ms P95                                          │
└──────────────────────────────────────────────────────────────┘
           ↓ Emit Prometheus metrics
┌──────────────────────────────────────────────────────────────┐
│ Prometheus + Grafana                                          │
│  • Histogram metrics (P50/P95/P99 quantiles)                 │
│  • Alert rules (>105% of budget)                             │
│  • Dashboards (trend visualization)                          │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation

### BudgetTracker Class

```python
# k1/infrastructure/performance/budget_tracker.py
"""Budget Tracker - Turn-level performance budget enforcement

Research:
- Performance Budgets: "Setting a Performance Budget" (Web Performance Working Group, 2019)
- SLO Enforcement: "Site Reliability Engineering" (Google, 2016) - Chapter 4: Service Level Objectives
- Percentile Metrics: "HdrHistogram: A High Dynamic Range Histogram" (Gil Tene, 2013)
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional

from k1.infrastructure.metrics import (
    turn_ttft_ms,
    turn_e2e_latency_ms,
    barge_in_cancel_latency_ms,
    budget_violation_total,
)

logger = logging.getLogger(__name__)


@dataclass
class TurnBudgets:
    """Turn-level performance budgets (P95 targets)"""
    ttft_ms: int = 150  # Time to First Token
    e2e_turn_ms: int = 2000  # End-to-end turn latency
    barge_in_ms: int = 120  # Barge-in cancel latency


@dataclass
class BudgetSnapshot:
    """Snapshot of budget performance"""
    ttft_ms: float
    e2e_turn_ms: float
    barge_in_ms: Optional[float]
    trace_id: str
    ttft_budget_exceeded: bool
    e2e_budget_exceeded: bool
    barge_in_budget_exceeded: bool


class BudgetTracker:
    """Track and enforce turn-level performance budgets

    Responsibilities:
    - Track TTFT, E2E turn latency, barge-in latency
    - Emit Prometheus metrics (histograms)
    - Detect budget violations (>105% of target)
    - Log violations with trace_id for debugging

    Performance:
    - Tracking overhead: <1ms per turn
    - No blocking operations (async metrics emission)
    """

    VIOLATION_THRESHOLD = 1.05  # Alert when >105% of budget

    def __init__(self, budgets: TurnBudgets = None):
        """Initialize budget tracker

        Args:
            budgets: Turn-level budgets (default: P95 targets)
        """
        self.budgets = budgets or TurnBudgets()

        logger.info(
            "[BudgetTracker] Initialized",
            ttft_budget_ms=self.budgets.ttft_ms,
            e2e_budget_ms=self.budgets.e2e_turn_ms,
            barge_in_budget_ms=self.budgets.barge_in_ms,
        )

    def track_ttft(self, ttft_ms: float, trace_id: str):
        """Track Time to First Token

        Args:
            ttft_ms: TTFT latency in milliseconds
            trace_id: Cognitive trace ID for debugging
        """
        # Emit Prometheus metric
        turn_ttft_ms.observe(ttft_ms)

        # Check budget violation
        budget_exceeded = ttft_ms > (self.budgets.ttft_ms * self.VIOLATION_THRESHOLD)

        if budget_exceeded:
            logger.warning(
                "[BudgetTracker] TTFT budget violation",
                ttft_ms=round(ttft_ms, 2),
                budget_ms=self.budgets.ttft_ms,
                threshold_ms=round(self.budgets.ttft_ms * self.VIOLATION_THRESHOLD, 2),
                trace_id=trace_id,
            )

            # Emit violation metric
            budget_violation_total.labels(metric="ttft").inc()

        else:
            logger.debug(
                "[BudgetTracker] TTFT within budget",
                ttft_ms=round(ttft_ms, 2),
                budget_ms=self.budgets.ttft_ms,
                trace_id=trace_id,
            )

    def track_e2e_turn(self, e2e_ms: float, trace_id: str):
        """Track End-to-End turn latency

        Args:
            e2e_ms: E2E latency in milliseconds
            trace_id: Cognitive trace ID for debugging
        """
        # Emit Prometheus metric
        turn_e2e_latency_ms.observe(e2e_ms)

        # Check budget violation
        budget_exceeded = e2e_ms > (self.budgets.e2e_turn_ms * self.VIOLATION_THRESHOLD)

        if budget_exceeded:
            logger.warning(
                "[BudgetTracker] E2E turn budget violation",
                e2e_ms=round(e2e_ms, 2),
                budget_ms=self.budgets.e2e_turn_ms,
                threshold_ms=round(self.budgets.e2e_turn_ms * self.VIOLATION_THRESHOLD, 2),
                trace_id=trace_id,
            )

            # Emit violation metric
            budget_violation_total.labels(metric="e2e_turn").inc()

        else:
            logger.debug(
                "[BudgetTracker] E2E turn within budget",
                e2e_ms=round(e2e_ms, 2),
                budget_ms=self.budgets.e2e_turn_ms,
                trace_id=trace_id,
            )

    def track_barge_in(self, cancel_ms: float, trace_id: str):
        """Track Barge-In cancel latency

        Args:
            cancel_ms: Barge-in cancel latency in milliseconds
            trace_id: Cognitive trace ID for debugging
        """
        # Emit Prometheus metric
        barge_in_cancel_latency_ms.observe(cancel_ms)

        # Check budget violation
        budget_exceeded = cancel_ms > (self.budgets.barge_in_ms * self.VIOLATION_THRESHOLD)

        if budget_exceeded:
            logger.warning(
                "[BudgetTracker] Barge-in budget violation",
                cancel_ms=round(cancel_ms, 2),
                budget_ms=self.budgets.barge_in_ms,
                threshold_ms=round(self.budgets.barge_in_ms * self.VIOLATION_THRESHOLD, 2),
                trace_id=trace_id,
            )

            # Emit violation metric
            budget_violation_total.labels(metric="barge_in").inc()

        else:
            logger.debug(
                "[BudgetTracker] Barge-in within budget",
                cancel_ms=round(cancel_ms, 2),
                budget_ms=self.budgets.barge_in_ms,
                trace_id=trace_id,
            )

    def get_snapshot(
        self,
        ttft_ms: float,
        e2e_ms: float,
        barge_in_ms: Optional[float],
        trace_id: str,
    ) -> BudgetSnapshot:
        """Get budget performance snapshot

        Args:
            ttft_ms: TTFT latency
            e2e_ms: E2E turn latency
            barge_in_ms: Barge-in latency (optional)
            trace_id: Trace ID

        Returns:
            BudgetSnapshot with violation flags
        """
        return BudgetSnapshot(
            ttft_ms=ttft_ms,
            e2e_turn_ms=e2e_ms,
            barge_in_ms=barge_in_ms,
            trace_id=trace_id,
            ttft_budget_exceeded=ttft_ms > (self.budgets.ttft_ms * self.VIOLATION_THRESHOLD),
            e2e_budget_exceeded=e2e_ms > (self.budgets.e2e_turn_ms * self.VIOLATION_THRESHOLD),
            barge_in_budget_exceeded=(
                barge_in_ms > (self.budgets.barge_in_ms * self.VIOLATION_THRESHOLD)
                if barge_in_ms is not None else False
            ),
        )
```

### Budget Decomposition Tracker

```python
# k1/infrastructure/performance/ttft_decomposition.py
"""TTFT Budget Decomposition - Track component contributions"""

import time
import logging
from dataclasses import dataclass

from k1.infrastructure.metrics import (
    ttft_component_latency_ms,
)

logger = logging.getLogger(__name__)


@dataclass
class TTFTDecomposition:
    """TTFT budget decomposition (150ms total)"""
    asr_ms: float  # Speech-to-Text: 80ms budget
    intent_ms: float  # Intent classification: 50ms budget
    orchestrator_ms: float  # 3-phase orchestration: 20ms budget
    total_ms: float  # Total TTFT

    def to_dict(self) -> dict:
        return {
            "asr_ms": round(self.asr_ms, 2),
            "intent_ms": round(self.intent_ms, 2),
            "orchestrator_ms": round(self.orchestrator_ms, 2),
            "total_ms": round(self.total_ms, 2),
        }


class TTFTDecompositionTracker:
    """Track TTFT component contributions

    Responsibilities:
    - Track ASR, intent, orchestrator latencies
    - Emit per-component Prometheus metrics
    - Identify bottlenecks (which component exceeding budget?)

    Performance: <500µs tracking overhead
    """

    # Component budgets (P95)
    ASR_BUDGET_MS = 80
    INTENT_BUDGET_MS = 50
    ORCHESTRATOR_BUDGET_MS = 20

    def track_decomposition(
        self,
        asr_ms: float,
        intent_ms: float,
        orchestrator_ms: float,
        trace_id: str,
    ) -> TTFTDecomposition:
        """Track TTFT decomposition

        Args:
            asr_ms: ASR latency
            intent_ms: Intent classification latency
            orchestrator_ms: Orchestrator latency
            trace_id: Trace ID

        Returns:
            TTFTDecomposition
        """
        total_ms = asr_ms + intent_ms + orchestrator_ms

        # Emit per-component metrics
        ttft_component_latency_ms.labels(component="asr").observe(asr_ms)
        ttft_component_latency_ms.labels(component="intent").observe(intent_ms)
        ttft_component_latency_ms.labels(component="orchestrator").observe(orchestrator_ms)

        # Check component budget violations
        if asr_ms > self.ASR_BUDGET_MS * 1.05:
            logger.warning(
                "[TTFTDecomposition] ASR budget violation",
                asr_ms=round(asr_ms, 2),
                budget_ms=self.ASR_BUDGET_MS,
                trace_id=trace_id,
            )

        if intent_ms > self.INTENT_BUDGET_MS * 1.05:
            logger.warning(
                "[TTFTDecomposition] Intent budget violation",
                intent_ms=round(intent_ms, 2),
                budget_ms=self.INTENT_BUDGET_MS,
                trace_id=trace_id,
            )

        if orchestrator_ms > self.ORCHESTRATOR_BUDGET_MS * 1.05:
            logger.warning(
                "[TTFTDecomposition] Orchestrator budget violation",
                orchestrator_ms=round(orchestrator_ms, 2),
                budget_ms=self.ORCHESTRATOR_BUDGET_MS,
                trace_id=trace_id,
            )

        decomposition = TTFTDecomposition(
            asr_ms=asr_ms,
            intent_ms=intent_ms,
            orchestrator_ms=orchestrator_ms,
            total_ms=total_ms,
        )

        logger.debug(
            "[TTFTDecomposition] TTFT tracked",
            **decomposition.to_dict(),
            trace_id=trace_id,
        )

        return decomposition
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/performance/test_budget_tracker.py
from ward import test, fixture

from k1.infrastructure.performance.budget_tracker import (
    BudgetTracker,
    TurnBudgets,
)

@fixture
def budget_tracker():
    """Fixture for BudgetTracker"""
    return BudgetTracker(budgets=TurnBudgets(
        ttft_ms=150,
        e2e_turn_ms=2000,
        barge_in_ms=120,
    ))

@test("BudgetTracker tracks TTFT within budget")
def _(tracker=budget_tracker):
    # Track TTFT below budget
    tracker.track_ttft(ttft_ms=140, trace_id="trace-123")

    # Should not log warning (within budget)
    # Verify via log capture or mock

@test("BudgetTracker detects TTFT violation")
def _(tracker=budget_tracker):
    # Track TTFT above 105% threshold (150ms * 1.05 = 157.5ms)
    tracker.track_ttft(ttft_ms=160, trace_id="trace-456")

    # Should log warning (budget violation)
    # Verify violation metric incremented

@test("BudgetTracker tracks E2E turn within budget")
def _(tracker=budget_tracker):
    # Track E2E below budget
    tracker.track_e2e_turn(e2e_ms=1800, trace_id="trace-789")

    # Should not log warning

@test("BudgetTracker detects E2E violation")
def _(tracker=budget_tracker):
    # Track E2E above 105% threshold (2000ms * 1.05 = 2100ms)
    tracker.track_e2e_turn(e2e_ms=2200, trace_id="trace-abc")

    # Should log warning

@test("BudgetTracker snapshot captures violations")
def _(tracker=budget_tracker):
    # Get snapshot with violations
    snapshot = tracker.get_snapshot(
        ttft_ms=160,  # Exceeds 157.5ms threshold
        e2e_ms=1800,  # Within budget
        barge_in_ms=None,
        trace_id="trace-def",
    )

    # Verify violation flags
    assert snapshot.ttft_budget_exceeded is True
    assert snapshot.e2e_budget_exceeded is False
```

---

## Performance Benchmarks

### Budget Tracking Overhead

| Operation | Latency | Overhead |
|-----------|---------|----------|
| track_ttft() | <500µs | Negligible |
| track_e2e_turn() | <500µs | Negligible |
| track_barge_in() | <500µs | Negligible |
| get_snapshot() | <100µs | Negligible |

**Total overhead: <2ms per turn (acceptable for budget tracking)**

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Turn-Level Budgets)
from prometheus_client import Histogram, Counter

# TTFT histogram
turn_ttft_ms = Histogram(
    'turn_ttft_ms',
    'Time to First Token latency in milliseconds',
    buckets=[50, 100, 150, 200, 300, 500]
)

# E2E turn histogram
turn_e2e_latency_ms = Histogram(
    'turn_e2e_latency_ms',
    'End-to-end turn latency in milliseconds',
    buckets=[500, 1000, 1500, 2000, 2500, 3000, 5000]
)

# Barge-in histogram
barge_in_cancel_latency_ms = Histogram(
    'barge_in_cancel_latency_ms',
    'Barge-in cancel latency in milliseconds',
    buckets=[50, 100, 120, 150, 200, 300]
)

# Budget violations
budget_violation_total = Counter(
    'budget_violation_total',
    'Total budget violations',
    labelnames=['metric']  # 'ttft', 'e2e_turn', 'barge_in'
)

# TTFT component breakdown
ttft_component_latency_ms = Histogram(
    'ttft_component_latency_ms',
    'TTFT component latency in milliseconds',
    labelnames=['component'],  # 'asr', 'intent', 'orchestrator'
    buckets=[10, 30, 50, 80, 100, 150]
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/performance_budgets.yml
groups:
  - name: k1_performance_budgets
    interval: 30s
    rules:
      - alert: TTFTBudgetViolation
        expr: histogram_quantile(0.95, rate(turn_ttft_ms_bucket[5m])) > 157.5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "TTFT P95 exceeds budget (>105% of 150ms)"
          description: "TTFT P95: {{ $value }}ms (budget: 150ms)"

      - alert: E2ETurnBudgetViolation
        expr: histogram_quantile(0.95, rate(turn_e2e_latency_ms_bucket[5m])) > 2100
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "E2E turn P95 exceeds budget (>105% of 2000ms)"
          description: "E2E P95: {{ $value }}ms (budget: 2000ms)"

      - alert: BargeInBudgetViolation
        expr: histogram_quantile(0.95, rate(barge_in_cancel_latency_ms_bucket[5m])) > 126
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Barge-in P95 exceeds budget (>105% of 120ms)"
          description: "Barge-in P95: {{ $value }}ms (budget: 120ms)"

      - alert: TTFTComponentBottleneck
        expr: histogram_quantile(0.95, rate(ttft_component_latency_ms_bucket{component="asr"}[5m])) > 84
        for: 2m
        labels:
          severity: info
        annotations:
          summary: "ASR component exceeds budget (>105% of 80ms)"
          description: "ASR P95: {{ $value }}ms (budget: 80ms)"
```

### Grafana Dashboard

```yaml
# Grafana dashboard: Turn-Level Performance Budgets
dashboard:
  title: "K1 Performance Budgets"
  panels:
    - title: "TTFT Latency (P50/P95/P99)"
      type: graph
      targets:
        - expr: histogram_quantile(0.50, rate(turn_ttft_ms_bucket[5m]))
          legend: "P50"
        - expr: histogram_quantile(0.95, rate(turn_ttft_ms_bucket[5m]))
          legend: "P95 (Budget: 150ms)"
        - expr: histogram_quantile(0.99, rate(turn_ttft_ms_bucket[5m]))
          legend: "P99"
      yaxis:
        label: "Latency (ms)"
      threshold:
        - value: 150
          color: "green"
          label: "P95 Budget"
        - value: 157.5
          color: "red"
          label: "Alert Threshold (105%)"

    - title: "E2E Turn Latency (P50/P95/P99)"
      type: graph
      targets:
        - expr: histogram_quantile(0.50, rate(turn_e2e_latency_ms_bucket[5m]))
          legend: "P50"
        - expr: histogram_quantile(0.95, rate(turn_e2e_latency_ms_bucket[5m]))
          legend: "P95 (Budget: 2000ms)"
        - expr: histogram_quantile(0.99, rate(turn_e2e_latency_ms_bucket[5m]))
          legend: "P99"
      threshold:
        - value: 2000
          color: "green"
        - value: 2100
          color: "red"

    - title: "TTFT Component Breakdown (P95)"
      type: graph
      targets:
        - expr: histogram_quantile(0.95, rate(ttft_component_latency_ms_bucket{component="asr"}[5m]))
          legend: "ASR (Budget: 80ms)"
        - expr: histogram_quantile(0.95, rate(ttft_component_latency_ms_bucket{component="intent"}[5m]))
          legend: "Intent (Budget: 50ms)"
        - expr: histogram_quantile(0.95, rate(ttft_component_latency_ms_bucket{component="orchestrator"}[5m]))
          legend: "Orchestrator (Budget: 20ms)"
      yaxis:
        label: "Latency (ms)"

    - title: "Budget Violations (Rate)"
      type: graph
      targets:
        - expr: rate(budget_violation_total{metric="ttft"}[5m])
          legend: "TTFT Violations/sec"
        - expr: rate(budget_violation_total{metric="e2e_turn"}[5m])
          legend: "E2E Violations/sec"
        - expr: rate(budget_violation_total{metric="barge_in"}[5m])
          legend: "Barge-in Violations/sec"
```

---

## Research Citations

1. **Web Performance Working Group (2019).** *"Setting a Performance Budget."* W3C. — Performance budget methodology.

2. **Google (2016).** *"Site Reliability Engineering - Chapter 4: Service Level Objectives."* O'Reilly. — SLO enforcement patterns.

3. **Gil Tene (2013).** *"HdrHistogram: A High Dynamic Range Histogram."* Azul Systems. — Percentile metrics implementation.

---

## Consequences

### Positive

1. **Clear Targets:** Explicit P95 budgets (TTFT 150ms, E2E 2000ms, Barge-In 120ms)
2. **Early Warning:** Alert at 105% of budget (before user-visible impact)
3. **Decomposable:** TTFT broken down into ASR/Intent/Orchestrator components
4. **Observability:** Prometheus metrics + Grafana dashboards for tracking

### Negative

1. **Overhead:** ~2ms tracking overhead per turn (negligible)
2. **Alert Fatigue:** Too many alerts if thresholds too aggressive
3. **Budget Evolution:** Budgets may need adjustment as features added

### Mitigations

1. **Acceptable Overhead:** 2ms tracking overhead negligible vs 2000ms E2E budget
2. **Alert Tuning:** Use 105% threshold (not 100%) to reduce false positives
3. **Quarterly Review:** Re-evaluate budgets every quarter based on metrics

---

## Roadmap

### Week 1: Budget Definitions & Tracker

- [ ] Define TurnBudgets data class (TTFT, E2E, Barge-In)
- [ ] Implement BudgetTracker class
- [ ] Add track_ttft(), track_e2e_turn(), track_barge_in() methods
- [ ] Add budget violation detection (>105% threshold)

### Week 2: TTFT Decomposition

- [ ] Implement TTFTDecompositionTracker
- [ ] Track ASR, Intent, Orchestrator latencies separately
- [ ] Emit per-component Prometheus metrics
- [ ] Add component budget violation warnings

### Week 3: Prometheus Integration

- [ ] Add histogram metrics (turn_ttft_ms, turn_e2e_latency_ms, barge_in_cancel_latency_ms)
- [ ] Add budget_violation_total counter
- [ ] Add ttft_component_latency_ms histogram
- [ ] Write Prometheus alert rules

### Week 4: Testing & Dashboards

- [ ] Write WARD unit tests (budget tracking, violations, snapshots)
- [ ] Create Grafana dashboard (TTFT, E2E, component breakdown, violations)
- [ ] Integration testing with real turn execution
- [ ] Production rollout (monitor budget metrics, validate alerts)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** None (foundational)
**Blocks:** 0024b (Component-Level Budgets), 0024d (Graceful Degradation)

---

**END OF ADR-0024a**
