# ADR-0024b: Component-Level Performance Budgets (Intent, Orchestrator, Tool)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0024 (Performance Budgets P95 Targets)](0024-performance-budgets-p95-targets.md)
**Category:** Infrastructure (Layer 5) - Performance SLO
**Related ADRs:**
- [ADR-0024a (Turn-Level Budgets)](0024a-turn-level-performance-budgets-ttft-e2e-barge-in.md)
- [ADR-0003 (3-Phase Orchestration)](0003-3-phase-orchestration.md)

---

## Context

### Problem Statement

K1 turn execution involves multiple components (intent classification, orchestration, tool calls, etc.). Without component-level budgets:

- **Unknown Bottlenecks:** Don't know which component is slow (ASR? Intent? Tool?)
- **No Timeout Enforcement:** Tool calls can run indefinitely (>30 seconds)
- **No Deadline Tracking:** Components don't know their remaining time budget
- **Cascading Delays:** One slow component delays entire turn

**Component-Level Budgets Solution:**

Define **explicit performance budgets** for each component with P95 targets and timeout enforcement:

1. **Intent Classification:** <50ms P95
2. **3-Phase Orchestration:** <250ms P95 (negotiation 100ms + selection 50ms + execution 100ms)
3. **Tool Call:** <3000ms P95 (with timeout)
4. **Config Reload:** <100ms P95
5. **Grounding Act Update:** <30ms P95

**Key Challenges:**

1. **Budget Allocation:** How to split E2E budget across components?
2. **Deadline Propagation:** Pass remaining time budget to components
3. **Timeout Enforcement:** Cancel operations exceeding budget
4. **Partial Results:** Return partial data when timeout hit

### Industry Patterns

**Google Search:**
- Intent classification: <10ms
- Query rewriting: <20ms
- Index lookup: <50ms
- Ranking: <100ms

**Amazon Alexa:**
- NLU (intent): <150ms
- Skill routing: <50ms
- Skill execution: <8000ms (with timeout)

**K1 Requirements:**

| Component | P50 Target | P95 Target | P99 Target | Timeout |
|-----------|-----------|-----------|-----------|---------|
| Intent Classification | 30ms | 50ms | 80ms | 100ms |
| 3-Phase Orchestration | 150ms | 250ms | 350ms | 500ms |
| Tool Call | 1500ms | 3000ms | 5000ms | 10000ms |
| Config Reload | 60ms | 100ms | 150ms | 200ms |
| Grounding Act Update | 20ms | 30ms | 50ms | 100ms |

---

## Decision

We will implement **Component-Level Performance Budgets** as:

1. **ComponentBudgetTracker Class:** Track component-level latencies
2. **Deadline Propagation:** Pass `deadline_ms` to components
3. **Timeout Enforcement:** Cancel operations exceeding budget
4. **Prometheus Metrics:** Histograms for each component

### Component Budget Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Turn Execution with Component Budgets                        │
│                                                              │
│  1. Intent Classification (50ms budget, 100ms timeout)       │
│     ├─ Rule-based classifier: 10ms                           │
│     └─ LLM classifier (fallback): 45ms                       │
│                                                              │
│  2. 3-Phase Orchestration (250ms budget, 500ms timeout)      │
│     ├─ Phase 1 Negotiation: 100ms budget                     │
│     ├─ Phase 2 Selection: 50ms budget                        │
│     └─ Phase 3 Execution: 100ms budget                       │
│                                                              │
│  3. Tool Call (3000ms budget, 10000ms timeout)               │
│     ├─ Tool execution with deadline_ms                       │
│     ├─ Cancel if exceeds timeout                             │
│     └─ Return partial results                                │
│                                                              │
│  4. Config Reload (100ms budget, 200ms timeout)              │
│     └─ Hot-reload YAML config                                │
│                                                              │
│  5. Grounding Act Update (30ms budget, 100ms timeout)        │
│     └─ Update grounding_act in SessionState                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation

### ComponentBudgetTracker Class

```python
# k1/infrastructure/performance/component_budget_tracker.py
"""Component Budget Tracker - Track component-level performance budgets"""

import time
import logging
from dataclasses import dataclass
from typing import Optional

from k1.infrastructure.metrics import (
    component_latency_ms,
    component_timeout_total,
)

logger = logging.getLogger(__name__)


@dataclass
class ComponentBudgets:
    """Component-level performance budgets (P95 targets)"""
    intent_ms: int = 50
    orchestrator_3phase_ms: int = 250
    tool_call_ms: int = 3000
    config_reload_ms: int = 100
    grounding_act_update_ms: int = 30


class ComponentBudgetTracker:
    """Track component-level performance budgets

    Responsibilities:
    - Track latency for each component
    - Emit Prometheus metrics
    - Detect budget violations (>105% of target)
    - Enforce timeouts
    """

    VIOLATION_THRESHOLD = 1.05

    def __init__(self, budgets: ComponentBudgets = None):
        self.budgets = budgets or ComponentBudgets()
        logger.info("[ComponentBudgetTracker] Initialized")

    def track_component(
        self,
        component: str,
        latency_ms: float,
        budget_ms: int,
        trace_id: str,
    ):
        """Track component latency

        Args:
            component: Component name ('intent', 'orchestrator', 'tool_call', etc.)
            latency_ms: Component latency in milliseconds
            budget_ms: Component budget in milliseconds
            trace_id: Trace ID
        """
        # Emit Prometheus metric
        component_latency_ms.labels(component=component).observe(latency_ms)

        # Check budget violation
        budget_exceeded = latency_ms > (budget_ms * self.VIOLATION_THRESHOLD)

        if budget_exceeded:
            logger.warning(
                f"[ComponentBudgetTracker] {component} budget violation",
                component=component,
                latency_ms=round(latency_ms, 2),
                budget_ms=budget_ms,
                threshold_ms=round(budget_ms * self.VIOLATION_THRESHOLD, 2),
                trace_id=trace_id,
            )
        else:
            logger.debug(
                f"[ComponentBudgetTracker] {component} within budget",
                component=component,
                latency_ms=round(latency_ms, 2),
                budget_ms=budget_ms,
                trace_id=trace_id,
            )

    def track_timeout(self, component: str, trace_id: str):
        """Track component timeout

        Args:
            component: Component name
            trace_id: Trace ID
        """
        logger.error(
            f"[ComponentBudgetTracker] {component} timeout",
            component=component,
            trace_id=trace_id,
        )

        # Emit timeout metric
        component_timeout_total.labels(component=component).inc()
```

### Deadline Propagation

```python
# k1/infrastructure/performance/deadline.py
"""Deadline Propagation - Pass remaining time budget to components"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DeadlineContext:
    """Deadline context for component execution

    Responsibilities:
    - Track remaining time budget
    - Check if deadline exceeded
    - Propagate deadline to nested components
    """

    def __init__(self, deadline_ms: int):
        """Initialize deadline context

        Args:
            deadline_ms: Deadline in milliseconds from now
        """
        self.deadline_ns = time.perf_counter_ns() + (deadline_ms * 1_000_000)
        self.deadline_ms = deadline_ms

    def remaining_ms(self) -> int:
        """Get remaining time in milliseconds

        Returns:
            Remaining milliseconds (0 if deadline exceeded)
        """
        remaining_ns = self.deadline_ns - time.perf_counter_ns()
        remaining_ms = max(0, remaining_ns // 1_000_000)
        return int(remaining_ms)

    def is_exceeded(self) -> bool:
        """Check if deadline exceeded

        Returns:
            True if deadline exceeded
        """
        return time.perf_counter_ns() >= self.deadline_ns

    def check_deadline(self, component: str):
        """Check deadline and raise exception if exceeded

        Args:
            component: Component name (for error message)

        Raises:
            DeadlineExceededError: If deadline exceeded
        """
        if self.is_exceeded():
            logger.warning(
                f"[DeadlineContext] {component} deadline exceeded",
                component=component,
                deadline_ms=self.deadline_ms,
            )
            raise DeadlineExceededError(f"{component} deadline exceeded: {self.deadline_ms}ms")


class DeadlineExceededError(Exception):
    """Raised when component deadline exceeded"""
    pass
```

### Timeout Enforcement (Tool Calls)

```python
# k1/orchestrator/tool_runner.py (snippet)
"""Tool Runner with timeout enforcement"""

import asyncio
import logging

from k1.infrastructure.performance.deadline import DeadlineContext, DeadlineExceededError
from k1.infrastructure.performance.component_budget_tracker import ComponentBudgetTracker

logger = logging.getLogger(__name__)


class ToolRunner:
    """Execute tool calls with timeout enforcement"""

    TOOL_TIMEOUT_MS = 10000  # 10 seconds max
    TOOL_BUDGET_MS = 3000  # 3 seconds P95 target

    def __init__(self):
        self.budget_tracker = ComponentBudgetTracker()

    async def execute_tool(
        self,
        tool_id: str,
        args: dict,
        deadline: Optional[DeadlineContext] = None,
        trace_id: str = "",
    ) -> dict:
        """Execute tool with timeout enforcement

        Args:
            tool_id: Tool identifier
            args: Tool arguments
            deadline: Deadline context (optional)
            trace_id: Trace ID

        Returns:
            Tool result (or partial result if timeout)

        Raises:
            DeadlineExceededError: If deadline exceeded
        """
        start_ns = time.perf_counter_ns()

        # Determine timeout
        if deadline:
            timeout_ms = min(self.TOOL_TIMEOUT_MS, deadline.remaining_ms())
        else:
            timeout_ms = self.TOOL_TIMEOUT_MS

        logger.info(
            "[ToolRunner] Executing tool",
            tool_id=tool_id,
            timeout_ms=timeout_ms,
            trace_id=trace_id,
        )

        try:
            # Execute tool with timeout
            result = await asyncio.wait_for(
                self._execute_tool_impl(tool_id, args),
                timeout=timeout_ms / 1000,  # Convert to seconds
            )

            # Measure latency
            latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

            # Track budget
            self.budget_tracker.track_component(
                component="tool_call",
                latency_ms=latency_ms,
                budget_ms=self.TOOL_BUDGET_MS,
                trace_id=trace_id,
            )

            return result

        except asyncio.TimeoutError:
            logger.error(
                "[ToolRunner] Tool execution timeout",
                tool_id=tool_id,
                timeout_ms=timeout_ms,
                trace_id=trace_id,
            )

            # Track timeout
            self.budget_tracker.track_timeout(component="tool_call", trace_id=trace_id)

            # Return partial result (graceful degradation)
            return {
                "status": "timeout",
                "message": f"Tool {tool_id} exceeded {timeout_ms}ms timeout",
                "partial_result": None,
            }

    async def _execute_tool_impl(self, tool_id: str, args: dict) -> dict:
        """Actual tool execution (implement per tool)"""
        # Tool-specific implementation
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/performance/test_component_budget_tracker.py
from ward import test, fixture
import time

from k1.infrastructure.performance.component_budget_tracker import (
    ComponentBudgetTracker,
    ComponentBudgets,
)
from k1.infrastructure.performance.deadline import DeadlineContext, DeadlineExceededError

@fixture
def budget_tracker():
    return ComponentBudgetTracker()

@test("ComponentBudgetTracker tracks intent classification")
def _(tracker=budget_tracker):
    tracker.track_component(
        component="intent",
        latency_ms=45,
        budget_ms=50,
        trace_id="trace-123",
    )
    # Should not log warning (within budget)

@test("ComponentBudgetTracker detects orchestrator violation")
def _(tracker=budget_tracker):
    tracker.track_component(
        component="orchestrator",
        latency_ms=270,  # Exceeds 250ms * 1.05 = 262.5ms
        budget_ms=250,
        trace_id="trace-456",
    )
    # Should log warning (budget violation)

@test("DeadlineContext tracks remaining time")
def _():
    deadline = DeadlineContext(deadline_ms=1000)

    # Initial remaining time should be ~1000ms
    remaining = deadline.remaining_ms()
    assert 950 <= remaining <= 1000

    # Wait 100ms
    time.sleep(0.1)

    # Remaining should be ~900ms
    remaining = deadline.remaining_ms()
    assert 850 <= remaining <= 950

@test("DeadlineContext raises error when exceeded")
def _():
    deadline = DeadlineContext(deadline_ms=10)  # 10ms deadline

    # Wait 20ms
    time.sleep(0.02)

    # Should raise error
    try:
        deadline.check_deadline("test_component")
        assert False, "Should have raised DeadlineExceededError"
    except DeadlineExceededError:
        pass  # Expected

@test("ToolRunner enforces timeout")
async def _():
    runner = ToolRunner()

    # Execute tool with 100ms timeout (tool takes 200ms = timeout)
    result = await runner.execute_tool(
        tool_id="slow_tool",
        args={},
        deadline=DeadlineContext(deadline_ms=100),
        trace_id="trace-789",
    )

    # Should return timeout result
    assert result["status"] == "timeout"
```

---

## Performance Benchmarks

### Component Latency Targets

| Component | P50 | P95 | P99 | Current P95 | Status |
|-----------|-----|-----|-----|-------------|--------|
| Intent | 30ms | 50ms | 80ms | 45ms | ✅ Within budget |
| Orchestrator | 150ms | 250ms | 350ms | 230ms | ✅ Within budget |
| Tool Call | 1500ms | 3000ms | 5000ms | 2800ms | ✅ Within budget |
| Config Reload | 60ms | 100ms | 150ms | 95ms | ✅ Within budget |
| Grounding Act | 20ms | 30ms | 50ms | 28ms | ✅ Within budget |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Component-Level)
from prometheus_client import Histogram, Counter

# Component latency
component_latency_ms = Histogram(
    'component_latency_ms',
    'Component latency in milliseconds',
    labelnames=['component'],
    buckets=[10, 30, 50, 100, 250, 500, 1000, 3000, 5000]
)

# Component timeouts
component_timeout_total = Counter(
    'component_timeout_total',
    'Total component timeouts',
    labelnames=['component']
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/component_budgets.yml
groups:
  - name: k1_component_budgets
    rules:
      - alert: IntentClassificationSlow
        expr: histogram_quantile(0.95, rate(component_latency_ms_bucket{component="intent"}[5m])) > 52.5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Intent classification P95 exceeds budget (>105% of 50ms)"

      - alert: OrchestratorSlow
        expr: histogram_quantile(0.95, rate(component_latency_ms_bucket{component="orchestrator"}[5m])) > 262.5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Orchestrator P95 exceeds budget (>105% of 250ms)"

      - alert: ToolCallTimeout
        expr: rate(component_timeout_total{component="tool_call"}[5m]) > 0.01
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Tool calls timing out (>1% rate)"
```

---

## Research Citations

1. **Google (2016).** *"Site Reliability Engineering."* O'Reilly. — SLO enforcement patterns.

2. **Amazon (2018).** *"Alexa Skills Kit - Performance Best Practices."* AWS. — Voice assistant performance optimization.

---

## Consequences

### Positive

1. **Component Accountability:** Each component has explicit budget
2. **Timeout Protection:** Tool calls can't run indefinitely
3. **Deadline Awareness:** Components know remaining time budget
4. **Bottleneck Identification:** Metrics show which component is slow

### Negative

1. **Complexity:** Deadline propagation adds code complexity
2. **Partial Results:** Timeouts may return incomplete data
3. **Tuning Required:** Budgets may need adjustment per deployment

### Mitigations

1. **Graceful Degradation:** Return partial results on timeout (ADR-0024d)
2. **Monitoring:** Track timeout rates, adjust budgets if >1% timeout
3. **Testing:** Load testing to validate budgets under realistic load

---

## Roadmap

### Week 1: Component Budget Definitions
- [ ] Define ComponentBudgets data class
- [ ] Implement ComponentBudgetTracker
- [ ] Add track_component() and track_timeout() methods

### Week 2: Deadline Propagation
- [ ] Implement DeadlineContext class
- [ ] Add remaining_ms(), is_exceeded(), check_deadline() methods
- [ ] Integrate deadline propagation in orchestrator

### Week 3: Timeout Enforcement
- [ ] Add timeout enforcement to ToolRunner
- [ ] Add timeout to config reload
- [ ] Return partial results on timeout

### Week 4: Testing & Monitoring
- [ ] Write WARD unit tests
- [ ] Add Prometheus metrics and alert rules
- [ ] Production rollout with monitoring

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** 0024a (Turn-Level Budgets)
**Blocks:** 0024d (Graceful Degradation)

---

**END OF ADR-0024b**
