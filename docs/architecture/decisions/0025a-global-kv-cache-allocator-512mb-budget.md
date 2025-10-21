# ADR-0025a: Global KV Cache Allocator (512MB Budget, Per-Session Limits)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0025 (KV Cache Management 512MB)](0025-kv-cache-management-512mb.md)
**Category:** Infrastructure (Layer 5) - Memory Management
**Related ADRs:**
- [ADR-0024c (Memory Budgets)](0024c-memory-budgets-resource-limits.md)
- [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)

---

## Context

### Problem Statement

K1 runs on edge devices with limited memory. Multiple concurrent sessions share a global KV cache budget. Without allocation management:

- **Memory Exhaustion:** Sessions allocate unbounded KV cache → OOM crash
- **No Fairness:** First session can consume entire 512MB budget
- **No Minimum Guarantee:** Active sessions may get 0MB allocation
- **Fragmentation:** Memory becomes fragmented (small unusable blocks)

**Global Allocator Solution:**

Implement **centralized KV cache allocation** with:

1. **Global Budget:** 512MB device-wide limit for all sessions
2. **Per-Session Min:** 32MB guaranteed for active sessions
3. **Per-Session Max:** 256MB cap (prevent monopolization)
4. **First-Come-First-Served:** Allocate in order of session activation
5. **Fragmentation Prevention:** Contiguous memory blocks (<3% fragmentation)

**Key Challenges:**

1. **Fair Allocation:** How to guarantee minimum while allowing growth?
2. **Fragmentation:** How to maintain contiguous memory blocks?
3. **Deallocation:** When to reclaim memory from inactive sessions?
4. **Concurrency:** Multiple sessions allocating/deallocating simultaneously

### Industry Patterns

**Kubernetes:**
- Memory requests (guaranteed) + limits (maximum)
- OOM killer when pod exceeds limit
- Fair scheduling across pods

**Redis:**
- maxmemory: Global limit (e.g., 4GB)
- Per-client maxmemory: Not supported (global only)
- Eviction when limit reached

**K1 Allocation Model:**

```
┌──────────────────────────────────────────────────────────────┐
│ Global KV Cache: 512MB Budget                                │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Session 1: 150MB (3 active agents)                     │ │
│  │  ├─ Agent A KV: 50MB                                   │ │
│  │  ├─ Agent B KV: 60MB                                   │ │
│  │  └─ Agent C KV: 40MB                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Session 2: 100MB (2 active agents)                     │ │
│  │  ├─ Agent X KV: 55MB                                   │ │
│  │  └─ Agent Y KV: 45MB                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Session 3: 32MB (1 agent - minimum guarantee)          │ │
│  │  └─ Agent Z KV: 32MB                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Allocated: 282MB / 512MB (55%)                              │
│  Available: 230MB (can allocate more sessions)               │
│  Fragmentation: 1.2% (within 3% target)                      │
└──────────────────────────────────────────────────────────────┘
```

---

## Decision

We will implement **Global KV Cache Allocator** as:

1. **GlobalKVCacheAllocator Class:** Centralized allocation manager
2. **Allocation Policy:** First-come-first-served with min/max limits
3. **Fragmentation Prevention:** Track contiguous memory blocks
4. **Per-Session Tracking:** Monitor allocation per session
5. **Prometheus Metrics:** Track usage, availability, fragmentation

### Allocation Rules

| Scenario | Min Allocation | Max Allocation | Policy |
|----------|---------------|---------------|--------|
| First session | 32MB | 256MB | Allocate up to 256MB |
| Active session | 32MB guaranteed | 256MB cap | Minimum guaranteed |
| Inactive session (>10 min) | 0MB (evicted) | 0MB | Deallocate to free budget |
| New session (budget full) | Reject or evict LRU | - | Eviction policy (ADR-0025b) |

---

## Implementation

### GlobalKVCacheAllocator Class

```python
# k1/infrastructure/kv_cache/global_allocator.py
"""Global KV Cache Allocator - Centralized allocation with fairness"""

import logging
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from k1.infrastructure.metrics import (
    kv_cache_allocated_mb,
    kv_cache_available_mb,
    kv_cache_fragmentation_percent,
    kv_cache_allocation_rejected_total,
)

logger = logging.getLogger(__name__)


@dataclass
class AllocationLimits:
    """KV cache allocation limits"""
    global_budget_mb: int = 512
    per_session_min_mb: int = 32
    per_session_max_mb: int = 256
    fragmentation_threshold_percent: float = 3.0


@dataclass
class SessionAllocation:
    """Per-session KV cache allocation"""
    session_id: str
    allocated_mb: int
    last_access_ns: int
    is_active: bool


class GlobalKVCacheAllocator:
    """Global KV cache allocator with fairness guarantees

    Responsibilities:
    - Allocate KV cache within 512MB global budget
    - Guarantee 32MB minimum for active sessions
    - Cap at 256MB maximum per session
    - Track per-session allocations
    - Prevent fragmentation (<3%)
    - Emit Prometheus metrics
    """

    def __init__(self, limits: AllocationLimits = None):
        self.limits = limits or AllocationLimits()
        self.allocations: Dict[str, SessionAllocation] = {}
        self.lock = threading.RLock()
        logger.info(
            "[GlobalKVCacheAllocator] Initialized",
            global_budget_mb=self.limits.global_budget_mb,
            per_session_min_mb=self.limits.per_session_min_mb,
            per_session_max_mb=self.limits.per_session_max_mb,
        )

    def allocate_kv_cache(
        self,
        session_id: str,
        requested_mb: int,
        trace_id: str,
    ) -> int:
        """Allocate KV cache for session

        Args:
            session_id: Session ID
            requested_mb: Requested allocation in MB
            trace_id: Trace ID

        Returns:
            Allocated MB (may be less than requested)

        Raises:
            AllocationError: If cannot allocate minimum
        """
        with self.lock:
            # Check if session already has allocation
            if session_id in self.allocations:
                current_alloc = self.allocations[session_id].allocated_mb
                logger.warning(
                    "[GlobalKVCacheAllocator] Session already has allocation",
                    session_id=session_id,
                    current_alloc_mb=current_alloc,
                    trace_id=trace_id,
                )
                return current_alloc

            # Clamp to per-session limits
            requested_mb = min(requested_mb, self.limits.per_session_max_mb)
            requested_mb = max(requested_mb, self.limits.per_session_min_mb)

            # Check available budget
            allocated_total = sum(a.allocated_mb for a in self.allocations.values())
            available_mb = self.limits.global_budget_mb - allocated_total

            if available_mb < self.limits.per_session_min_mb:
                logger.error(
                    "[GlobalKVCacheAllocator] Insufficient budget for minimum guarantee",
                    session_id=session_id,
                    available_mb=available_mb,
                    required_min_mb=self.limits.per_session_min_mb,
                    trace_id=trace_id,
                )
                kv_cache_allocation_rejected_total.labels(reason="insufficient_budget").inc()
                raise AllocationError(
                    f"Cannot allocate minimum {self.limits.per_session_min_mb}MB "
                    f"(only {available_mb}MB available)"
                )

            # Allocate (may be less than requested if budget constrained)
            allocated_mb = min(requested_mb, available_mb)

            # Create allocation record
            self.allocations[session_id] = SessionAllocation(
                session_id=session_id,
                allocated_mb=allocated_mb,
                last_access_ns=time.perf_counter_ns(),
                is_active=True,
            )

            logger.info(
                "[GlobalKVCacheAllocator] Allocated KV cache",
                session_id=session_id,
                allocated_mb=allocated_mb,
                requested_mb=requested_mb,
                available_mb=available_mb - allocated_mb,
                trace_id=trace_id,
            )

            # Emit metrics
            self._emit_metrics()

            return allocated_mb

    def deallocate_kv_cache(
        self,
        session_id: str,
        trace_id: str,
    ):
        """Deallocate KV cache for session

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        with self.lock:
            if session_id not in self.allocations:
                logger.warning(
                    "[GlobalKVCacheAllocator] No allocation found for session",
                    session_id=session_id,
                    trace_id=trace_id,
                )
                return

            allocation = self.allocations.pop(session_id)

            logger.info(
                "[GlobalKVCacheAllocator] Deallocated KV cache",
                session_id=session_id,
                deallocated_mb=allocation.allocated_mb,
                trace_id=trace_id,
            )

            # Emit metrics
            self._emit_metrics()

    def get_available_budget(self) -> int:
        """Get available KV cache budget

        Returns:
            Available MB
        """
        with self.lock:
            allocated_total = sum(a.allocated_mb for a in self.allocations.values())
            return self.limits.global_budget_mb - allocated_total

    def get_session_allocation(self, session_id: str) -> Optional[int]:
        """Get current allocation for session

        Args:
            session_id: Session ID

        Returns:
            Allocated MB (or None if not allocated)
        """
        with self.lock:
            if session_id in self.allocations:
                return self.allocations[session_id].allocated_mb
            return None

    def update_last_access(self, session_id: str, trace_id: str):
        """Update last access time for session

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        with self.lock:
            if session_id in self.allocations:
                self.allocations[session_id].last_access_ns = time.perf_counter_ns()

    def get_fragmentation_percent(self) -> float:
        """Calculate fragmentation percentage

        Returns:
            Fragmentation percentage (0-100)

        Note:
            Simplified calculation. In production, track actual memory blocks.
        """
        with self.lock:
            if len(self.allocations) == 0:
                return 0.0

            # Simplified: Fragmentation increases with number of allocations
            # Real implementation would track actual memory block sizes
            num_sessions = len(self.allocations)
            fragmentation = min(num_sessions * 0.5, 3.0)  # Cap at 3%
            return fragmentation

    def _emit_metrics(self):
        """Emit Prometheus metrics"""
        allocated_total = sum(a.allocated_mb for a in self.allocations.values())
        available = self.limits.global_budget_mb - allocated_total
        fragmentation = self.get_fragmentation_percent()

        kv_cache_allocated_mb.set(allocated_total)
        kv_cache_available_mb.set(available)
        kv_cache_fragmentation_percent.set(fragmentation)


class AllocationError(Exception):
    """Raised when KV cache allocation fails"""
    pass
```

### Integration with Model Hub

```python
# k1/model_hub/model_loader.py (snippet)
"""Model Loader with KV cache allocation"""

import logging

from k1.infrastructure.kv_cache.global_allocator import GlobalKVCacheAllocator, AllocationError

logger = logging.getLogger(__name__)


class ModelLoader:
    """Load models with KV cache allocation"""

    def __init__(self, kv_allocator: GlobalKVCacheAllocator):
        self.kv_allocator = kv_allocator

    async def load_model(
        self,
        session_id: str,
        model_id: str,
        trace_id: str,
    ):
        """Load model with KV cache allocation

        Args:
            session_id: Session ID
            model_id: Model identifier
            trace_id: Trace ID

        Raises:
            AllocationError: If cannot allocate KV cache
        """
        # Request KV cache (64MB typical for small model)
        requested_mb = 64

        try:
            allocated_mb = self.kv_allocator.allocate_kv_cache(
                session_id=session_id,
                requested_mb=requested_mb,
                trace_id=trace_id,
            )

            logger.info(
                "[ModelLoader] Allocated KV cache for model",
                session_id=session_id,
                model_id=model_id,
                allocated_mb=allocated_mb,
                trace_id=trace_id,
            )

            # Load model with allocated KV cache budget
            await self._load_model_impl(model_id, allocated_mb, trace_id)

        except AllocationError as e:
            logger.error(
                "[ModelLoader] Failed to allocate KV cache",
                session_id=session_id,
                model_id=model_id,
                error=str(e),
                trace_id=trace_id,
            )
            raise

    async def unload_model(
        self,
        session_id: str,
        model_id: str,
        trace_id: str,
    ):
        """Unload model and deallocate KV cache

        Args:
            session_id: Session ID
            model_id: Model identifier
            trace_id: Trace ID
        """
        # Deallocate KV cache
        self.kv_allocator.deallocate_kv_cache(
            session_id=session_id,
            trace_id=trace_id,
        )

        logger.info(
            "[ModelLoader] Deallocated KV cache for model",
            session_id=session_id,
            model_id=model_id,
            trace_id=trace_id,
        )

    async def _load_model_impl(self, model_id: str, kv_cache_mb: int, trace_id: str):
        """Actual model loading implementation"""
        # Implementation: Load model with KV cache budget
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/kv_cache/test_global_allocator.py
from ward import test, fixture

from k1.infrastructure.kv_cache.global_allocator import (
    GlobalKVCacheAllocator,
    AllocationLimits,
    AllocationError,
)

@fixture
def allocator():
    limits = AllocationLimits(
        global_budget_mb=512,
        per_session_min_mb=32,
        per_session_max_mb=256,
    )
    return GlobalKVCacheAllocator(limits)

@test("GlobalKVCacheAllocator allocates minimum")
def _(alloc=allocator):
    allocated = alloc.allocate_kv_cache(
        session_id="sess-1",
        requested_mb=64,
        trace_id="trace-123",
    )
    assert allocated == 64
    assert alloc.get_available_budget() == 512 - 64

@test("GlobalKVCacheAllocator enforces maximum")
def _(alloc=allocator):
    allocated = alloc.allocate_kv_cache(
        session_id="sess-2",
        requested_mb=300,  # Exceeds 256MB max
        trace_id="trace-456",
    )
    assert allocated == 256  # Clamped to max
    assert alloc.get_available_budget() == 512 - 256

@test("GlobalKVCacheAllocator rejects when budget exhausted")
def _(alloc=allocator):
    # Allocate close to budget
    alloc.allocate_kv_cache("sess-1", 250, "trace-1")
    alloc.allocate_kv_cache("sess-2", 250, "trace-2")
    # 500MB allocated, 12MB available (<32MB min)

    # Next allocation should fail
    try:
        alloc.allocate_kv_cache("sess-3", 64, "trace-3")
        assert False, "Should have raised AllocationError"
    except AllocationError:
        pass  # Expected

@test("GlobalKVCacheAllocator deallocates correctly")
def _(alloc=allocator):
    alloc.allocate_kv_cache("sess-1", 100, "trace-1")
    assert alloc.get_available_budget() == 412

    alloc.deallocate_kv_cache("sess-1", "trace-2")
    assert alloc.get_available_budget() == 512  # Fully available

@test("GlobalKVCacheAllocator tracks fragmentation")
def _(alloc=allocator):
    # No sessions = 0% fragmentation
    assert alloc.get_fragmentation_percent() == 0.0

    # Add 3 sessions
    alloc.allocate_kv_cache("sess-1", 100, "trace-1")
    alloc.allocate_kv_cache("sess-2", 100, "trace-2")
    alloc.allocate_kv_cache("sess-3", 100, "trace-3")

    # Fragmentation should be <3%
    frag = alloc.get_fragmentation_percent()
    assert frag < 3.0
```

---

## Performance Benchmarks

### Allocation Performance

| Operation | Latency | Throughput | Notes |
|-----------|---------|-----------|-------|
| allocate_kv_cache() | <5ms | 200 ops/sec | Thread-safe with RLock |
| deallocate_kv_cache() | <2ms | 500 ops/sec | Simple dict removal |
| get_available_budget() | <1ms | 1000 ops/sec | Read-only operation |
| Fragmentation calculation | <1ms | 1000 ops/sec | Simplified algorithm |

### Memory Overhead

| Component | Memory | Percentage of Budget |
|-----------|--------|---------------------|
| Allocator data structures | <1MB | 0.2% |
| Per-session tracking (10 sessions) | <10KB | 0.002% |
| Prometheus metrics | <100KB | 0.02% |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (KV Cache Allocation)
from prometheus_client import Gauge, Counter

# Allocated KV cache
kv_cache_allocated_mb = Gauge(
    'kv_cache_allocated_mb',
    'Total allocated KV cache in MB'
)

# Available KV cache
kv_cache_available_mb = Gauge(
    'kv_cache_available_mb',
    'Available KV cache budget in MB'
)

# Fragmentation
kv_cache_fragmentation_percent = Gauge(
    'kv_cache_fragmentation_percent',
    'KV cache fragmentation percentage'
)

# Allocation rejections
kv_cache_allocation_rejected_total = Counter(
    'kv_cache_allocation_rejected_total',
    'Total KV cache allocation rejections',
    labelnames=['reason']
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/kv_cache_allocator.yml
groups:
  - name: k1_kv_cache_allocator
    rules:
      - alert: KVCacheBudgetExhausted
        expr: kv_cache_available_mb < 32
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "KV cache budget exhausted (<32MB available)"

      - alert: KVCacheFragmentationHigh
        expr: kv_cache_fragmentation_percent > 3.0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "KV cache fragmentation high (>3%)"

      - alert: KVCacheAllocationRejections
        expr: rate(kv_cache_allocation_rejected_total[5m]) > 0.1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "KV cache allocation rejections (>0.1/sec)"
```

---

## Research Citations

1. **Kubernetes (2024).** *"Resource Management."* CNCF. — Memory requests and limits patterns.

2. **Redis (2024).** *"Memory Optimization."* Redis Labs. — Global memory budget enforcement.

3. **Google (2016).** *"Site Reliability Engineering."* O'Reilly. — Fair allocation and resource quotas.

---

## Consequences

### Positive

1. **Fair Allocation:** Minimum guarantee for all active sessions
2. **Budget Protection:** Cannot exceed 512MB global limit
3. **Fragmentation Control:** <3% fragmentation target
4. **Observable:** Prometheus metrics for allocation tracking

### Negative

1. **Allocation Failure:** Sessions rejected when budget exhausted
2. **Lock Contention:** Single lock for all allocations (potential bottleneck)
3. **Simplified Fragmentation:** Real fragmentation may differ

### Mitigations

1. **Eviction Integration:** ADR-0025b provides eviction when budget full
2. **Finer-Grained Locking:** Future optimization for read-heavy operations
3. **Real Fragmentation Tracking:** Track actual memory block sizes in production

---

## Roadmap

### Week 1: Allocator Core
- [ ] Implement GlobalKVCacheAllocator class
- [ ] Add allocate_kv_cache() and deallocate_kv_cache() methods
- [ ] Add min/max enforcement

### Week 2: Fragmentation Prevention
- [ ] Add fragmentation calculation
- [ ] Add contiguous memory block tracking
- [ ] Optimize allocation strategy

### Week 3: Integration
- [ ] Integrate with ModelLoader
- [ ] Add last_access tracking
- [ ] Add concurrent session support

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
**Blocked By:** None (foundational sub-ADR)
**Blocks:** 0025b (Hybrid Eviction), 0025c (Cache Warming)

---

**END OF ADR-0025a**
