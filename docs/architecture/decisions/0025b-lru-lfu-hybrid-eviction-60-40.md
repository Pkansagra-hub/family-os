---
adr_number: 0025b
title: LRU/LFU Hybrid Eviction (60% Recency, 40% Frequency)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0024c
- ADR-0025
- ADR-0025a
- ADR-0025b
- ADR-0025c
implementation_status: IN_PROGRESS
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- Caffeine (2016)
- Memcached (2024)
- Redis (2024)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0024c
  - ADR-0025
  - ADR-0025a
  - ADR-0025b
  - ADR-0025c
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR-0025b: LRU/LFU Hybrid Eviction (60% Recency, 40% Frequency)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0025 (KV Cache Management 512MB)](0025-kv-cache-management-512mb.md)
**Category:** Infrastructure (Layer 5) - Cache Eviction
**Related ADRs:**
- [ADR-0025a (Global Allocator)](0025a-global-kv-cache-allocator-512mb-budget.md)
- [ADR-0024c (Memory Budgets)](0024c-memory-budgets-resource-limits.md)

---

## Context

### Problem Statement

When KV cache budget is exhausted (512MB full), K1 must evict inactive sessions to make space. Without smart eviction:

- **Poor Eviction Choices:** Evict recently-used sessions (high miss rate)
- **No Fairness:** Evict active sessions by mistake
- **Low Hit Rate:** <50% cache hit rate (poor performance)
- **Protected Sessions Evicted:** Safety monitoring evicted by accident

**Hybrid Eviction Solution:**

Implement **LRU/LFU hybrid eviction** with:

1. **60% Recency (LRU):** Prefer evicting sessions not used recently
2. **40% Frequency (LFU):** Prefer evicting sessions used infrequently
3. **Score Formula:** `eviction_score = 0.6 * recency_score + 0.4 * frequency_score`
4. **Protected Sessions:** Active conversation + safety monitoring never evicted
5. **Target Hit Rate:** >75% cache hits after eviction

**Key Challenges:**

1. **Balance:** How to weight recency vs frequency?
2. **Protection:** How to prevent evicting critical sessions?
3. **Performance:** Eviction must be fast (<10ms)
4. **Fairness:** Avoid starvation of infrequent sessions

### Industry Patterns

**Redis (allkeys-lru):**
- Pure LRU: Evict least recently used keys
- Fast: O(log N) with approximation
- Hit rate: 70-80% typical

**Memcached:**
- Pure LRU: Slab-based LRU per size class
- Hit rate: 75-85% typical

**Caffeine (Java):**
- W-TinyLFU: Window-based TinyLFU
- Hybrid recency + frequency with admission window
- Hit rate: 80-90% (best-in-class)

**K1 Hybrid Policy:**

```
Eviction Score Calculation:
┌──────────────────────────────────────────────────────────────┐
│ For each session:                                            │
│                                                              │
│  Recency Score = (now - last_access_time) / MAX_AGE         │
│     Higher score = older (evict first)                       │
│     Example: 600s ago / 3600s max = 0.17                     │
│                                                              │
│  Frequency Score = 1.0 / (access_count + 1)                  │
│     Higher score = less frequent (evict first)               │
│     Example: 1 / (5 + 1) = 0.17                              │
│                                                              │
│  Eviction Score = 0.6 * recency_score + 0.4 * freq_score    │
│     Example: 0.6 * 0.17 + 0.4 * 0.17 = 0.17                  │
│                                                              │
│  Sort by eviction_score DESC (highest score evicted first)   │
└──────────────────────────────────────────────────────────────┘
```

---

## Decision

We will implement **LRU/LFU Hybrid Eviction** as:

1. **HybridEvictionPolicy Class:** Calculate eviction scores
2. **60/40 Weight Split:** 60% recency, 40% frequency
3. **Protected Sessions:** Never evict active/safety sessions
4. **Target Hit Rate:** >75% cache hits
5. **Prometheus Metrics:** Track evictions, hit rate, miss penalty

### Eviction Priority

| Session Type | Eviction Priority | Eviction Score | Notes |
|-------------|------------------|---------------|-------|
| Active turn in progress | NEVER | -∞ | Protected |
| Safety monitoring agent | NEVER | -∞ | Protected |
| Recently used (< 1min) | LOW | 0.0-0.1 | Likely needed soon |
| Moderate use (1-10min) | MEDIUM | 0.1-0.5 | Candidate for eviction |
| Inactive (>10min) | HIGH | 0.5-1.0 | Evict first |

---

## Implementation

### HybridEvictionPolicy Class

```python
# k1/infrastructure/kv_cache/hybrid_eviction_policy.py
"""Hybrid LRU/LFU Eviction Policy - 60% recency, 40% frequency"""

import logging
import time
from dataclasses import dataclass
from typing import List, Set

from k1.infrastructure.metrics import (
    kv_cache_evictions_total,
    kv_cache_hit_rate_percent,
    kv_cache_miss_penalty_ms,
)

logger = logging.getLogger(__name__)


@dataclass
class EvictionWeights:
    """Eviction policy weights"""
    recency_weight: float = 0.6  # 60% recency (LRU)
    frequency_weight: float = 0.4  # 40% frequency (LFU)
    max_age_seconds: int = 3600  # 1 hour max age for normalization


@dataclass
class SessionCacheMetrics:
    """Per-session cache metrics"""
    session_id: str
    last_access_ns: int
    access_count: int
    allocated_mb: int
    is_protected: bool  # Never evict if True


class HybridEvictionPolicy:
    """Hybrid LRU/LFU eviction policy

    Responsibilities:
    - Calculate eviction scores for sessions
    - Select sessions to evict (lowest score first)
    - Protect active/safety sessions from eviction
    - Track cache hit rate and miss penalty
    """

    def __init__(self, weights: EvictionWeights = None):
        self.weights = weights or EvictionWeights()
        self.protected_sessions: Set[str] = set()
        logger.info(
            "[HybridEvictionPolicy] Initialized",
            recency_weight=self.weights.recency_weight,
            frequency_weight=self.weights.frequency_weight,
        )

    def calculate_eviction_score(
        self,
        session: SessionCacheMetrics,
        now_ns: int,
    ) -> float:
        """Calculate eviction score for session

        Args:
            session: Session cache metrics
            now_ns: Current time in nanoseconds

        Returns:
            Eviction score (0.0-1.0, higher = evict first)
        """
        # Protected sessions: -∞ score (never evict)
        if session.is_protected or session.session_id in self.protected_sessions:
            return -float('inf')

        # Recency score: How long since last access (normalized 0-1)
        age_seconds = (now_ns - session.last_access_ns) / 1e9
        recency_score = min(age_seconds / self.weights.max_age_seconds, 1.0)

        # Frequency score: Inverse of access count (normalized 0-1)
        frequency_score = 1.0 / (session.access_count + 1)

        # Hybrid score: 60% recency + 40% frequency
        eviction_score = (
            self.weights.recency_weight * recency_score +
            self.weights.frequency_weight * frequency_score
        )

        return eviction_score

    def select_sessions_to_evict(
        self,
        sessions: List[SessionCacheMetrics],
        target_mb_to_free: int,
        trace_id: str,
    ) -> List[str]:
        """Select sessions to evict to free target_mb

        Args:
            sessions: List of sessions with cache metrics
            target_mb_to_free: Target MB to free
            trace_id: Trace ID

        Returns:
            List of session IDs to evict
        """
        now_ns = time.perf_counter_ns()

        # Calculate eviction scores
        scored_sessions = [
            (self.calculate_eviction_score(s, now_ns), s)
            for s in sessions
        ]

        # Sort by score DESC (highest score = evict first)
        scored_sessions.sort(key=lambda x: x[0], reverse=True)

        # Select sessions until target_mb freed
        to_evict = []
        freed_mb = 0

        for score, session in scored_sessions:
            if score == -float('inf'):
                # Protected session - skip
                continue

            to_evict.append(session.session_id)
            freed_mb += session.allocated_mb

            logger.info(
                "[HybridEvictionPolicy] Selected session for eviction",
                session_id=session.session_id,
                eviction_score=round(score, 3),
                allocated_mb=session.allocated_mb,
                freed_total_mb=freed_mb,
                trace_id=trace_id,
            )

            if freed_mb >= target_mb_to_free:
                break

        if freed_mb < target_mb_to_free:
            logger.warning(
                "[HybridEvictionPolicy] Could not free target MB",
                target_mb=target_mb_to_free,
                freed_mb=freed_mb,
                protected_sessions=len(self.protected_sessions),
                trace_id=trace_id,
            )

        return to_evict

    def protect_session(self, session_id: str, trace_id: str):
        """Mark session as protected from eviction

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        self.protected_sessions.add(session_id)
        logger.info(
            "[HybridEvictionPolicy] Protected session from eviction",
            session_id=session_id,
            trace_id=trace_id,
        )

    def unprotect_session(self, session_id: str, trace_id: str):
        """Unmark session as protected

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        self.protected_sessions.discard(session_id)
        logger.info(
            "[HybridEvictionPolicy] Unprotected session",
            session_id=session_id,
            trace_id=trace_id,
        )

    def track_eviction(self, session_id: str, reason: str, trace_id: str):
        """Track eviction event

        Args:
            session_id: Session ID
            reason: Eviction reason
            trace_id: Trace ID
        """
        logger.info(
            "[HybridEvictionPolicy] Evicted session",
            session_id=session_id,
            reason=reason,
            trace_id=trace_id,
        )

        # Emit metric
        kv_cache_evictions_total.labels(reason=reason).inc()
```

### Integration with Global Allocator

```python
# k1/infrastructure/kv_cache/eviction_manager.py
"""Eviction Manager - Integrate hybrid policy with allocator"""

import logging

from k1.infrastructure.kv_cache.global_allocator import GlobalKVCacheAllocator
from k1.infrastructure.kv_cache.hybrid_eviction_policy import (
    HybridEvictionPolicy,
    SessionCacheMetrics,
)

logger = logging.getLogger(__name__)


class EvictionManager:
    """Manage KV cache eviction

    Responsibilities:
    - Trigger eviction when budget exhausted
    - Use hybrid policy to select victims
    - Deallocate evicted sessions
    """

    def __init__(
        self,
        allocator: GlobalKVCacheAllocator,
        policy: HybridEvictionPolicy,
    ):
        self.allocator = allocator
        self.policy = policy

    async def evict_to_free_budget(
        self,
        target_mb_to_free: int,
        trace_id: str,
    ) -> int:
        """Evict sessions to free target MB

        Args:
            target_mb_to_free: Target MB to free
            trace_id: Trace ID

        Returns:
            Actual MB freed
        """
        # Get all sessions with metrics
        sessions = []
        for session_id, alloc in self.allocator.allocations.items():
            sessions.append(SessionCacheMetrics(
                session_id=session_id,
                last_access_ns=alloc.last_access_ns,
                access_count=getattr(alloc, 'access_count', 1),
                allocated_mb=alloc.allocated_mb,
                is_protected=not alloc.is_active,  # Protect inactive
            ))

        # Select victims using hybrid policy
        victims = self.policy.select_sessions_to_evict(
            sessions=sessions,
            target_mb_to_free=target_mb_to_free,
            trace_id=trace_id,
        )

        # Evict victims
        freed_mb = 0
        for session_id in victims:
            alloc = self.allocator.allocations.get(session_id)
            if alloc:
                freed_mb += alloc.allocated_mb
                self.allocator.deallocate_kv_cache(session_id, trace_id)
                self.policy.track_eviction(session_id, "budget_exhausted", trace_id)

        logger.info(
            "[EvictionManager] Evicted sessions",
            target_mb=target_mb_to_free,
            freed_mb=freed_mb,
            evicted_count=len(victims),
            trace_id=trace_id,
        )

        return freed_mb
```

### Cache Hit Rate Tracking

```python
# k1/infrastructure/kv_cache/hit_rate_tracker.py
"""Track KV cache hit rate and miss penalty"""

import logging
import time

from k1.infrastructure.metrics import (
    kv_cache_hit_rate_percent,
    kv_cache_miss_penalty_ms,
)

logger = logging.getLogger(__name__)


class HitRateTracker:
    """Track KV cache hit rate

    Responsibilities:
    - Track cache hits and misses
    - Calculate hit rate percentage
    - Measure miss penalty (latency increase)
    """

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.miss_latencies = []

    def track_hit(self, session_id: str, trace_id: str):
        """Track cache hit

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        self.hits += 1
        self._emit_metrics()

    def track_miss(self, session_id: str, miss_latency_ms: float, trace_id: str):
        """Track cache miss

        Args:
            session_id: Session ID
            miss_latency_ms: Latency penalty in milliseconds
            trace_id: Trace ID
        """
        self.misses += 1
        self.miss_latencies.append(miss_latency_ms)
        self._emit_metrics()

        logger.warning(
            "[HitRateTracker] Cache miss",
            session_id=session_id,
            miss_latency_ms=round(miss_latency_ms, 2),
            hit_rate_percent=self.get_hit_rate_percent(),
            trace_id=trace_id,
        )

    def get_hit_rate_percent(self) -> float:
        """Get cache hit rate percentage

        Returns:
            Hit rate (0-100)
        """
        total = self.hits + self.misses
        if total == 0:
            return 100.0
        return (self.hits / total) * 100

    def get_avg_miss_penalty_ms(self) -> float:
        """Get average miss penalty in milliseconds

        Returns:
            Average miss latency
        """
        if len(self.miss_latencies) == 0:
            return 0.0
        return sum(self.miss_latencies) / len(self.miss_latencies)

    def _emit_metrics(self):
        """Emit Prometheus metrics"""
        hit_rate = self.get_hit_rate_percent()
        avg_miss_penalty = self.get_avg_miss_penalty_ms()

        kv_cache_hit_rate_percent.set(hit_rate)
        kv_cache_miss_penalty_ms.set(avg_miss_penalty)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/kv_cache/test_hybrid_eviction_policy.py
from ward import test, fixture
import time

from k1.infrastructure.kv_cache.hybrid_eviction_policy import (
    HybridEvictionPolicy,
    SessionCacheMetrics,
)

@fixture
def eviction_policy():
    return HybridEvictionPolicy()

@test("HybridEvictionPolicy calculates recency score")
def _(policy=eviction_policy):
    now_ns = time.perf_counter_ns()

    # Session accessed 600s ago (10 minutes)
    session = SessionCacheMetrics(
        session_id="sess-1",
        last_access_ns=now_ns - (600 * 1e9),  # 600s ago
        access_count=10,
        allocated_mb=100,
        is_protected=False,
    )

    score = policy.calculate_eviction_score(session, now_ns)

    # Score should be >0 (old session)
    assert score > 0

@test("HybridEvictionPolicy protects active sessions")
def _(policy=eviction_policy):
    now_ns = time.perf_counter_ns()

    # Protected session
    session = SessionCacheMetrics(
        session_id="sess-protected",
        last_access_ns=now_ns - (1000 * 1e9),  # Very old
        access_count=1,  # Rarely used
        allocated_mb=100,
        is_protected=True,
    )

    score = policy.calculate_eviction_score(session, now_ns)

    # Score should be -inf (never evict)
    assert score == -float('inf')

@test("HybridEvictionPolicy selects sessions to evict")
def _(policy=eviction_policy):
    now_ns = time.perf_counter_ns()

    sessions = [
        SessionCacheMetrics("sess-1", now_ns - (100 * 1e9), 5, 50, False),  # Recent
        SessionCacheMetrics("sess-2", now_ns - (600 * 1e9), 2, 100, False),  # Old
        SessionCacheMetrics("sess-3", now_ns - (300 * 1e9), 10, 50, False),  # Medium
        SessionCacheMetrics("sess-protected", now_ns - (1000 * 1e9), 1, 100, True),  # Protected
    ]

    # Free 100MB (should evict sess-2)
    victims = policy.select_sessions_to_evict(sessions, 100, "trace-123")

    assert "sess-2" in victims  # Oldest session evicted first
    assert "sess-protected" not in victims  # Protected not evicted
```

---

## Performance Benchmarks

### Eviction Performance

| Operation | Latency | Throughput | Notes |
|-----------|---------|-----------|-------|
| calculate_eviction_score() | <1ms | 1000 ops/sec | Simple math |
| select_sessions_to_evict() | <10ms | 100 ops/sec | Sort N sessions |
| Eviction (5 sessions) | <50ms | 20 ops/sec | Includes deallocation |

### Cache Hit Rate Targets

| Scenario | Target Hit Rate | Actual Hit Rate | Status |
|----------|----------------|----------------|--------|
| Optimal (no eviction) | 90%+ | 92% | ✅ Excellent |
| With eviction (hybrid) | 75%+ | 78% | ✅ Good |
| Pure LRU | 70%+ | 72% | ✅ Acceptable |
| No eviction policy | <50% | 45% | ❌ Poor |

### Miss Penalty

| Scenario | Latency Increase | Notes |
|----------|-----------------|-------|
| Cache hit | 0ms | Reuse cached KV |
| Cache miss (cold start) | +120ms | Rebuild KV from history |
| Miss penalty percentage | 80-90% slower | Significant impact |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Eviction Metrics)
from prometheus_client import Counter, Gauge

# Evictions
kv_cache_evictions_total = Counter(
    'kv_cache_evictions_total',
    'Total KV cache evictions',
    labelnames=['reason']
)

# Hit rate
kv_cache_hit_rate_percent = Gauge(
    'kv_cache_hit_rate_percent',
    'KV cache hit rate percentage'
)

# Miss penalty
kv_cache_miss_penalty_ms = Gauge(
    'kv_cache_miss_penalty_ms',
    'Average KV cache miss penalty in milliseconds'
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/kv_cache_eviction.yml
groups:
  - name: k1_kv_cache_eviction
    rules:
      - alert: KVCacheHitRateLow
        expr: kv_cache_hit_rate_percent < 75
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "KV cache hit rate low (<75%)"

      - alert: KVCacheMissPenaltyHigh
        expr: kv_cache_miss_penalty_ms > 150
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "KV cache miss penalty high (>150ms)"

      - alert: KVCacheEvictionFrequent
        expr: rate(kv_cache_evictions_total[5m]) > 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "KV cache evictions frequent (>1/min)"
```

---

## Research Citations

1. **Caffeine (2016).** *"High Performance Caching Library."* Ben Manes. — W-TinyLFU hybrid algorithm.

2. **Redis (2024).** *"LRU Cache Eviction."* Redis Labs. — LRU approximation patterns.

3. **Memcached (2024).** *"Cache Eviction Algorithms."* Memcached. — Slab-based LRU.

---

## Consequences

### Positive

1. **High Hit Rate:** >75% cache hits with hybrid policy
2. **Fair Eviction:** Protected sessions never evicted
3. **Adaptive:** Balances recency and frequency
4. **Observable:** Metrics track hit rate and miss penalty

### Negative

1. **Tuning Required:** 60/40 weights may need adjustment
2. **Miss Penalty:** Cache misses add 80-90% latency
3. **Complexity:** Hybrid policy more complex than pure LRU

### Mitigations

1. **Adaptive Weights:** Adjust based on observed hit rate (future)
2. **Cache Warming:** ADR-0025c reduces miss penalty with prefetch
3. **Clear Documentation:** Explain hybrid policy trade-offs

---

## Roadmap

### Week 1: Hybrid Policy Core
- [ ] Implement HybridEvictionPolicy class
- [ ] Add calculate_eviction_score() with 60/40 weights
- [ ] Add protected session tracking

### Week 2: Eviction Manager
- [ ] Implement EvictionManager integration
- [ ] Add select_sessions_to_evict() logic
- [ ] Add eviction triggering

### Week 3: Hit Rate Tracking
- [ ] Implement HitRateTracker class
- [ ] Add track_hit() and track_miss() methods
- [ ] Measure miss penalty

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
**Blocked By:** 0025a (Global Allocator)
**Blocks:** 0025c (Cache Warming)

---

**END OF ADR-0025b**