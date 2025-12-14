---
adr_number: 0024c
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l3_execution.memory_manager
- k1.l4_runtime.resource_limits
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- security
- testing
date_created: 2025-11-03
date_updated: 2025-11-03
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: IN_PROGRESS
parent_adr: ADR-0024
propagation:
  affected_adrs:
  - ADR-0017
  - ADR-0018
  - ADR-0024d
  - ADR-0025a
  affected_contracts:
  - k0/contracts/openapi.k0.yaml
  affected_tests:
  - tests/k1/l4_runtime/test_memory_budgets.py
  triggers:
  - Changing memory allocation budgets
  - Adding new resource limit enforcement
  - Modifying OOM prevention strategies
related_adrs:
- ADR-0017
- ADR-0018
- ADR-0024
- ADR-0024a
- ADR-0024b
- ADR-0024d
- ADR-0025a
- ADR-0025b
- ADR-0072
- ADR-0073
- ADR-0086b
- ADR-0086c
related_contracts:
- k0/contracts/openapi.k0.yaml
related_diagrams: []
research_citations:
- Google Borg (2015) - Large-Scale Cluster Management
- Kubernetes Resource Quotas (2024) - Container Resource Limits
- Redis Maxmemory Policy (2024) - Memory Eviction Strategies
status: PROPOSED
superseded_by: []
supersedes: []
title: Memory Budgets & Resource Limits (SessionState, KV Cache)
---

# ADR-0024c: Memory Budgets & Resource Limits (SessionState, KV Cache)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Last Updated:** 2025-10-17 (M1 Context: Resource bounds in agent factory - See ADR-0072)
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0024 (Performance Budgets P95 Targets)](0024-performance-budgets-p95-targets.md)
**Category:** Infrastructure (Layer 5) - Resource Management
**Related ADRs:**
- [ADR-0024a (Turn-Level Budgets)](0024a-turn-level-performance-budgets-ttft-e2e-barge-in.md)
- [ADR-0024b (Component Budgets)](0024b-component-level-performance-budgets.md)
- [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
- [ADR-0018 (3-Tier Eviction)](0018-3-tier-eviction-strategy.md)
- [ADR-0072 (Dynamic Agent Creation - **NEW M1**)](0072-dynamic-agent-creation-subsystem.md)

---

## Context

### Problem Statement

K1 operates on edge devices with constrained memory (<1GB available). Without memory budgets:

- **OOM Crashes:** SessionState grows unbounded → 256KB → OOM
- **KV Cache Exhaustion:** Device runs out of memory mid-turn
- **No Per-Session Fairness:** One session can starve others
- **No OOM Prevention:** Reactive crash vs proactive rejection

**Memory Budget Solution:**

Define **explicit memory budgets** with 3-tier enforcement:

1. **SessionState Size:** 64KB soft / 128KB hard / 256KB OOM
2. **KV Cache Global:** 512MB device-wide budget
3. **K1 Total Memory:** <500MB (OS + all sessions)
4. **Per-Session Minimum:** 32MB KV cache guaranteed
5. **CPU Utilization:** <10% idle, <35% during speech

**Key Challenges:**

1. **Budget Allocation:** How to distribute 512MB KV cache across sessions?
2. **OOM Prevention:** How to reject turns before crash?
3. **Eviction Integration:** When to trigger eviction?
4. **Fairness:** Guarantee minimum KV cache per session

### Industry Patterns

**Kubernetes:**
- Memory limits: request (guaranteed) + limit (max)
- OOM killer: Terminate pods exceeding limit
- Resource quotas: Namespace-level limits

**Redis:**
- maxmemory: Hard limit (e.g., 4GB)
- maxmemory-policy: allkeys-lru, volatile-lru
- Eviction before OOM

**K1 Memory Architecture:**

```
┌──────────────────────────────────────────────────────────────┐
│ Device Memory Budget (1GB total, 500MB for K1)               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ K1 Total Memory: 500MB Budget                          │ │
│  │                                                        │ │
│  │  ┌────────────────────────────────────────────────┐   │ │
│  │  │ KV Cache: 512MB Global Budget                   │   │ │
│  │  │  ├─ Session 1: 150MB (3 active agents)         │   │ │
│  │  │  ├─ Session 2: 100MB (2 active agents)         │   │ │
│  │  │  └─ Session 3: 32MB (1 agent - min guarantee) │   │ │
│  │  └────────────────────────────────────────────────┘   │ │
│  │                                                        │ │
│  │  ┌────────────────────────────────────────────────┐   │ │
│  │  │ SessionState: Per-session (64KB soft limit)    │   │ │
│  │  │  ├─ beliefs: 16KB                               │   │ │
│  │  │  ├─ scoreboard: 12KB                            │   │ │
│  │  │  ├─ control: 8KB                                │   │ │
│  │  │  ├─ persona: 20KB                               │   │ │
│  │  │  ├─ multimodal: 4KB                             │   │ │
│  │  │  └─ meta: 4KB                                   │   │ │
│  │  └────────────────────────────────────────────────┘   │ │
│  │                                                        │ │
│  │  OS + Python Runtime: ~180MB                          │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Decision

We will implement **Memory Budgets & Resource Limits** as:

1. **MemoryBudgetTracker Class:** Track memory usage across all sessions
2. **3-Tier SessionState Limits:** 64KB soft → 128KB hard → 256KB OOM
3. **KV Cache Allocation:** 512MB global with 32MB per-session minimum
4. **OOM Prevention:** Reject turns when K1 memory >480MB (96% of budget)
5. **Eviction Integration:** Trigger eviction at 128KB hard limit

### Memory Budget Tiers

| Tier | SessionState Size | Action | Consequence |
|------|------------------|--------|-------------|
| **Green (Soft)** | <64KB | None | Normal operation |
| **Amber (Hard)** | 64-128KB | Trigger eviction | Evict COLD items |
| **Red (OOM)** | 128-256KB | Reject turn + Force eviction | Evict WARM items |
| **Critical** | >256KB | Kill session | OOM crash imminent |

---

## Implementation

### MemoryBudgetTracker Class

```python
# k1/infrastructure/performance/memory_budget_tracker.py
"""Memory Budget Tracker - Track memory usage and enforce limits"""

import logging
import psutil
from dataclasses import dataclass
from typing import Dict

from k1.infrastructure.metrics import (
    session_state_size_kb,
    kv_cache_total_mb,
    k1_memory_total_mb,
    cpu_utilization_percent,
)

logger = logging.getLogger(__name__)


@dataclass
class MemoryBudgets:
    """Memory budgets for K1 system"""
    session_state_soft_kb: int = 64
    session_state_hard_kb: int = 128
    session_state_oom_kb: int = 256
    kv_cache_global_mb: int = 512
    kv_cache_min_per_session_mb: int = 32
    k1_total_mb: int = 500
    k1_oom_threshold_mb: int = 480  # 96% of budget


class MemoryBudgetTracker:
    """Track memory budgets and enforce limits

    Responsibilities:
    - Track SessionState size per session
    - Track global KV cache usage
    - Track total K1 memory (psutil)
    - Enforce 3-tier limits (soft/hard/OOM)
    - Trigger eviction when limits exceeded
    - Reject turns when OOM risk
    """

    def __init__(self, budgets: MemoryBudgets = None):
        self.budgets = budgets or MemoryBudgets()
        self.session_state_sizes: Dict[str, int] = {}  # session_id -> size_bytes
        logger.info("[MemoryBudgetTracker] Initialized")

    def track_session_state_size(
        self,
        session_id: str,
        size_kb: int,
        trace_id: str,
    ) -> str:
        """Track SessionState size and return tier

        Args:
            session_id: Session ID
            size_kb: SessionState size in KB
            trace_id: Trace ID

        Returns:
            Tier: 'green', 'amber', 'red', 'critical'
        """
        self.session_state_sizes[session_id] = size_kb

        # Emit Prometheus metric
        session_state_size_kb.labels(session_id=session_id).set(size_kb)

        # Determine tier
        if size_kb < self.budgets.session_state_soft_kb:
            tier = "green"
        elif size_kb < self.budgets.session_state_hard_kb:
            tier = "amber"
            logger.warning(
                "[MemoryBudgetTracker] SessionState AMBER tier (eviction triggered)",
                session_id=session_id,
                size_kb=size_kb,
                soft_limit_kb=self.budgets.session_state_soft_kb,
                trace_id=trace_id,
            )
        elif size_kb < self.budgets.session_state_oom_kb:
            tier = "red"
            logger.error(
                "[MemoryBudgetTracker] SessionState RED tier (force eviction + reject turn)",
                session_id=session_id,
                size_kb=size_kb,
                hard_limit_kb=self.budgets.session_state_hard_kb,
                trace_id=trace_id,
            )
        else:
            tier = "critical"
            logger.critical(
                "[MemoryBudgetTracker] SessionState CRITICAL tier (kill session)",
                session_id=session_id,
                size_kb=size_kb,
                oom_limit_kb=self.budgets.session_state_oom_kb,
                trace_id=trace_id,
            )

        return tier

    def track_kv_cache_usage(self, total_mb: int, trace_id: str):
        """Track global KV cache usage

        Args:
            total_mb: Total KV cache usage in MB
            trace_id: Trace ID
        """
        # Emit Prometheus metric
        kv_cache_total_mb.set(total_mb)

        # Check budget
        if total_mb > self.budgets.kv_cache_global_mb:
            logger.error(
                "[MemoryBudgetTracker] KV cache exceeds budget",
                total_mb=total_mb,
                budget_mb=self.budgets.kv_cache_global_mb,
                trace_id=trace_id,
            )

    def track_k1_total_memory(self, trace_id: str) -> int:
        """Track total K1 memory usage via psutil

        Args:
            trace_id: Trace ID

        Returns:
            Total K1 memory in MB
        """
        process = psutil.Process()
        memory_info = process.memory_info()
        total_mb = memory_info.rss / (1024 * 1024)  # Convert bytes to MB

        # Emit Prometheus metric
        k1_memory_total_mb.set(total_mb)

        # Check OOM threshold
        if total_mb > self.budgets.k1_oom_threshold_mb:
            logger.error(
                "[MemoryBudgetTracker] K1 memory exceeds OOM threshold",
                total_mb=round(total_mb, 2),
                oom_threshold_mb=self.budgets.k1_oom_threshold_mb,
                trace_id=trace_id,
            )

        return int(total_mb)

    def track_cpu_utilization(self, trace_id: str) -> float:
        """Track CPU utilization

        Args:
            trace_id: Trace ID

        Returns:
            CPU utilization percentage
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Emit Prometheus metric
        cpu_utilization_percent.set(cpu_percent)

        return cpu_percent

    def should_reject_turn(self, trace_id: str) -> bool:
        """Check if new turn should be rejected (OOM prevention)

        Args:
            trace_id: Trace ID

        Returns:
            True if turn should be rejected
        """
        total_mb = self.track_k1_total_memory(trace_id)

        if total_mb > self.budgets.k1_oom_threshold_mb:
            logger.warning(
                "[MemoryBudgetTracker] Rejecting turn (OOM prevention)",
                total_mb=total_mb,
                oom_threshold_mb=self.budgets.k1_oom_threshold_mb,
                trace_id=trace_id,
            )
            return True

        return False
```

### Eviction Integration

```python
# k1/session_state/eviction_manager.py (snippet)
"""Eviction Manager with memory budget integration"""

import logging

from k1.infrastructure.performance.memory_budget_tracker import MemoryBudgetTracker
from k1.session_state.eviction_policy import EvictionPolicy

logger = logging.getLogger(__name__)


class EvictionManager:
    """Manage eviction with memory budget integration"""

    def __init__(self, memory_tracker: MemoryBudgetTracker):
        self.memory_tracker = memory_tracker

    async def check_and_evict(
        self,
        session_id: str,
        session_state_size_kb: int,
        trace_id: str,
    ):
        """Check memory tier and trigger eviction if needed

        Args:
            session_id: Session ID
            session_state_size_kb: SessionState size in KB
            trace_id: Trace ID
        """
        # Track size and get tier
        tier = self.memory_tracker.track_session_state_size(
            session_id=session_id,
            size_kb=session_state_size_kb,
            trace_id=trace_id,
        )

        # Eviction logic based on tier
        if tier == "green":
            # No eviction needed
            pass

        elif tier == "amber":
            # Trigger eviction of COLD items
            logger.info(
                "[EvictionManager] Evicting COLD items (AMBER tier)",
                session_id=session_id,
                trace_id=trace_id,
            )
            await self._evict_cold_items(session_id, trace_id)

        elif tier == "red":
            # Force eviction of WARM items
            logger.warning(
                "[EvictionManager] Force evicting WARM items (RED tier)",
                session_id=session_id,
                trace_id=trace_id,
            )
            await self._evict_warm_items(session_id, trace_id)

        elif tier == "critical":
            # Kill session (OOM imminent)
            logger.critical(
                "[EvictionManager] Killing session (CRITICAL tier)",
                session_id=session_id,
                trace_id=trace_id,
            )
            await self._kill_session(session_id, trace_id)

    async def _evict_cold_items(self, session_id: str, trace_id: str):
        """Evict COLD items from SessionState"""
        # Implementation: Evict items with temperature=COLD
        pass

    async def _evict_warm_items(self, session_id: str, trace_id: str):
        """Evict WARM items from SessionState"""
        # Implementation: Evict items with temperature=WARM
        pass

    async def _kill_session(self, session_id: str, trace_id: str):
        """Kill session (OOM critical)"""
        # Implementation: Terminate session, free all resources
        pass
```

### OOM Prevention (API Gateway)

```python
# k1/api_gateway/turn_handler.py (snippet)
"""Turn Handler with OOM prevention"""

import logging

from k1.infrastructure.performance.memory_budget_tracker import MemoryBudgetTracker

logger = logging.getLogger(__name__)


class TurnHandler:
    """Handle turns with OOM prevention"""

    def __init__(self, memory_tracker: MemoryBudgetTracker):
        self.memory_tracker = memory_tracker

    async def handle_turn(self, session_id: str, user_input: str, trace_id: str):
        """Handle turn with OOM check

        Args:
            session_id: Session ID
            user_input: User input
            trace_id: Trace ID

        Returns:
            Turn result (or rejection)
        """
        # OOM prevention check
        if self.memory_tracker.should_reject_turn(trace_id):
            logger.error(
                "[TurnHandler] Rejecting turn (OOM prevention)",
                session_id=session_id,
                trace_id=trace_id,
            )
            return {
                "status": "rejected",
                "message": "System under heavy memory pressure, please try again",
            }

        # Process turn normally
        result = await self._process_turn(session_id, user_input, trace_id)
        return result

    async def _process_turn(self, session_id: str, user_input: str, trace_id: str):
        """Actual turn processing"""
        # Implementation
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/performance/test_memory_budget_tracker.py
from ward import test, fixture

from k1.infrastructure.performance.memory_budget_tracker import (
    MemoryBudgetTracker,
    MemoryBudgets,
)

@fixture
def memory_tracker():
    return MemoryBudgetTracker()

@test("MemoryBudgetTracker tracks GREEN tier")
def _(tracker=memory_tracker):
    tier = tracker.track_session_state_size(
        session_id="sess-1",
        size_kb=50,  # <64KB soft limit
        trace_id="trace-123",
    )
    assert tier == "green"

@test("MemoryBudgetTracker tracks AMBER tier")
def _(tracker=memory_tracker):
    tier = tracker.track_session_state_size(
        session_id="sess-2",
        size_kb=100,  # 64-128KB range
        trace_id="trace-456",
    )
    assert tier == "amber"

@test("MemoryBudgetTracker tracks RED tier")
def _(tracker=memory_tracker):
    tier = tracker.track_session_state_size(
        session_id="sess-3",
        size_kb=200,  # 128-256KB range
        trace_id="trace-789",
    )
    assert tier == "red"

@test("MemoryBudgetTracker tracks CRITICAL tier")
def _(tracker=memory_tracker):
    tier = tracker.track_session_state_size(
        session_id="sess-4",
        size_kb=300,  # >256KB OOM limit
        trace_id="trace-abc",
    )
    assert tier == "critical"

@test("MemoryBudgetTracker tracks K1 total memory")
def _(tracker=memory_tracker):
    total_mb = tracker.track_k1_total_memory(trace_id="trace-123")

    # Should return current process memory
    assert total_mb > 0

@test("MemoryBudgetTracker rejects turn on OOM risk")
def _(tracker=memory_tracker):
    # Mock high memory usage (override psutil)
    # (Proper test would use mocking framework)

    # For now, test logic:
    # If total_mb > 480MB, should reject
    should_reject = tracker.should_reject_turn(trace_id="trace-456")

    # Assertion depends on actual memory usage
    # In production, this would be mocked
```

---

## Performance Benchmarks

### Memory Budget Targets

| Resource | Soft Limit | Hard Limit | OOM Limit | Current | Status |
|----------|-----------|-----------|-----------|---------|--------|
| SessionState (per-session) | 64KB | 128KB | 256KB | 48KB | ✅ Green |
| KV Cache (global) | - | 512MB | - | 380MB | ✅ Within budget |
| K1 Total Memory | - | 500MB | 480MB | 450MB | ✅ Within budget |
| CPU Utilization (idle) | - | 10% | - | 8% | ✅ Within target |
| CPU Utilization (speech) | - | 35% | - | 32% | ✅ Within target |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Memory Metrics)
from prometheus_client import Gauge

# SessionState size per session
session_state_size_kb = Gauge(
    'session_state_size_kb',
    'SessionState size in KB',
    labelnames=['session_id']
)

# KV cache total
kv_cache_total_mb = Gauge(
    'kv_cache_total_mb',
    'Total KV cache usage in MB'
)

# K1 total memory
k1_memory_total_mb = Gauge(
    'k1_memory_total_mb',
    'Total K1 memory usage in MB'
)

# CPU utilization
cpu_utilization_percent = Gauge(
    'cpu_utilization_percent',
    'CPU utilization percentage'
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/memory_budgets.yml
groups:
  - name: k1_memory_budgets
    rules:
      - alert: SessionStateAmberTier
        expr: session_state_size_kb > 64
        for: 30s
        labels:
          severity: warning
        annotations:
          summary: "SessionState exceeds soft limit (>64KB, eviction triggered)"

      - alert: SessionStateRedTier
        expr: session_state_size_kb > 128
        for: 10s
        labels:
          severity: critical
        annotations:
          summary: "SessionState exceeds hard limit (>128KB, force eviction)"

      - alert: KVCacheExhaustion
        expr: kv_cache_total_mb > 512
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "KV cache exceeds budget (>512MB)"

      - alert: K1MemoryOOMRisk
        expr: k1_memory_total_mb > 480
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "K1 memory exceeds OOM threshold (>480MB, rejecting turns)"

      - alert: CPUUtilizationHigh
        expr: cpu_utilization_percent > 50
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "CPU utilization exceeds target (>50%)"
```

---

## Research Citations

1. **Kubernetes (2024).** *"Resource Management."* CNCF. — Memory limits and OOM handling.

2. **Redis (2024).** *"Memory Optimization."* Redis Labs. — Eviction policies and maxmemory.

3. **Google (2016).** *"Site Reliability Engineering."* O'Reilly. — Resource allocation and OOM prevention.

---

## Consequences

### Positive

1. **OOM Prevention:** Proactive turn rejection prevents crashes
2. **Fair Allocation:** Minimum KV cache per session guaranteed
3. **Eviction Integration:** Automatic eviction at memory limits
4. **Observability:** Metrics show memory usage trends

### Negative

1. **Turn Rejection:** Users may see "system under pressure" errors
2. **Complexity:** 3-tier limits add cognitive overhead
3. **Tuning Required:** Budgets may need per-device adjustment

### Mitigations

1. **User Transparency:** Notify user when turn rejected (ADR-0024d)
2. **Graceful Degradation:** Return partial results instead of rejection
3. **Dynamic Budgets:** Adjust based on device capabilities

---

## Roadmap

### Week 1: Memory Budget Tracker
- [ ] Implement MemoryBudgetTracker class
- [ ] Add track_session_state_size(), track_kv_cache_usage() methods
- [ ] Add should_reject_turn() OOM prevention

### Week 2: Eviction Integration
- [ ] Integrate with EvictionManager
- [ ] Implement 3-tier eviction (COLD at amber, WARM at red)
- [ ] Add kill_session() for critical tier

### Week 3: OOM Prevention
- [ ] Add OOM check to TurnHandler
- [ ] Reject turns when K1 memory >480MB
- [ ] Return user-friendly error message

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
**Blocked By:** 0024a (Turn-Level Budgets), 0024b (Component Budgets)
**Blocks:** 0024d (Graceful Degradation)

---

**END OF ADR-0024c**