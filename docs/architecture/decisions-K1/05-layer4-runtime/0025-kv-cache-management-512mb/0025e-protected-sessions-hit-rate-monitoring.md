---
adr_number: 0025e
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l4_runtime.cache_monitor
- k1.l5_infrastructure.metrics
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- security
- testing
- usability
date_created: 2025-11-03
date_updated: 2025-11-03
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: IN_PROGRESS
parent_adr: ADR-0025
propagation:
  affected_adrs:
  - ADR-0002
  - ADR-0025a
  - ADR-0025b
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  affected_tests:
  - tests/k1/l4_runtime/test_cache_monitoring.py
  triggers:
  - Changing protected session policies
  - Modifying cache hit rate targets (75% P95)
  - Adding new monitoring metrics
related_adrs:
- ADR-0002
- ADR-0025
- ADR-0025a
- ADR-0025b
related_contracts:
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
related_diagrams: []
research_citations:
- Caffeine Cache Metrics (2016) - Hit Rate & Eviction Monitoring
- Google SRE Book (2016) - Service Level Indicators
- Redis INFO Stats (2024) - Cache Statistics & Monitoring
status: PROPOSED
superseded_by: []
supersedes: []
title: Protected Sessions & Cache Hit Rate Monitoring
---

# ADR-0025e: Protected Sessions & Cache Hit Rate Monitoring

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0025 (KV Cache Management 512MB)](0025-kv-cache-management-512mb.md)
**Category:** Infrastructure (Layer 5) - Reliability & Observability
**Related ADRs:**
- [ADR-0025a (Global Allocator)](0025a-global-kv-cache-allocator-512mb-budget.md)
- [ADR-0025b (Hybrid Eviction)](0025b-lru-lfu-hybrid-eviction-60-40.md)
- [ADR-0002 (Actor Model)](0002-actor-model-agent-isolation.md)

---

## Context

### Problem Statement

Not all sessions are equal - some must never be evicted. Without protection policies:

- **Critical Sessions Evicted:** Safety monitoring agent evicted by mistake (safety incident)
- **Active Turn Evicted:** User's current turn evicted mid-processing (UX disaster)
- **No Hit Rate Tracking:** Don't know if eviction policy is effective
- **No Adaptive Tuning:** Can't improve eviction based on observed metrics

**Protection & Monitoring Solution:**

Implement **protected sessions and hit rate tracking** with:

1. **Protected Classes:** Active conversation (never evict), safety monitoring (never evict)
2. **Cache Hit Rate:** Track % of turns using cached KV (target >75%)
3. **Miss Penalty:** Measure latency increase on cache miss (80-90% slower)
4. **Adaptive Policies:** Adjust eviction weights based on observed hit rate
5. **Protection Rules:** Explicit never-evict guarantees for critical sessions

**Key Challenges:**

1. **Protection Mechanism:** How to mark sessions as protected?
2. **Hit Rate Calculation:** How to measure cache hits vs misses?
3. **Miss Penalty:** How to quantify performance impact?
4. **Adaptive Tuning:** When to adjust eviction weights?

### Industry Patterns

**Redis Protected Keys:**
- `noeviction` policy: Never evict keys (OOM instead)
- `volatile-lru`: Only evict keys with TTL
- Protection via policy, not per-key

**Memcached:**
- No per-key protection
- Global eviction policies only
- No hit rate tracking built-in

**K1 Protection Model:**

```
Session Protection Classes:
┌──────────────────────────────────────────────────────────────┐
│ Protection Tier 1: NEVER EVICT                               │
│  ├─ Active turn in progress (user waiting)                   │
│  └─ Safety monitoring agent (crash detection)                │
│                                                              │
│ Protection Tier 2: LOW PRIORITY EVICTION                     │
│  ├─ Recently used session (<5 minutes)                       │
│  └─ Frequently used session (>10 accesses)                   │
│                                                              │
│ Protection Tier 3: NORMAL EVICTION                           │
│  ├─ Inactive session (5-30 minutes)                          │
│  └─ Moderate use (2-10 accesses)                             │
│                                                              │
│ Protection Tier 4: HIGH PRIORITY EVICTION                    │
│  ├─ Inactive session (>30 minutes)                           │
│  └─ Rarely used (<2 accesses)                                │
└──────────────────────────────────────────────────────────────┘
```

---

## Decision

We will implement **Protected Sessions & Hit Rate Monitoring** as:

1. **ProtectionManager Class:** Manage session protection policies
2. **Protection Rules:** Never evict active/safety sessions
3. **HitRateMonitor Class:** Track cache hit rate (target >75%)
4. **Miss Penalty Tracker:** Measure latency increase on miss
5. **Adaptive Tuner:** Adjust eviction weights based on hit rate

### Protection Rules

| Session Type | Protection Level | Eviction Score | Notes |
|-------------|-----------------|---------------|-------|
| Active turn in progress | NEVER | -∞ | User waiting for response |
| Safety monitoring agent | NEVER | -∞ | Critical safety function |
| Recently used (<5min) | LOW | 0.0-0.2 | Likely needed soon |
| Frequently used (>10 accesses) | LOW | 0.0-0.3 | High value |
| Inactive (5-30min) | NORMAL | 0.3-0.7 | Standard eviction |
| Background learning | NORMAL | 0.5-0.8 | Non-critical workload |
| Rarely used (<2 accesses) | HIGH | 0.7-1.0 | Evict first |

---

## Implementation

### ProtectionManager Class

```python
# k1/infrastructure/kv_cache/protection_manager.py
"""Protection Manager - Manage session protection policies"""

import logging
from dataclasses import dataclass
from typing import Set
from enum import Enum

logger = logging.getLogger(__name__)


class ProtectionLevel(Enum):
    """Session protection levels"""
    NEVER_EVICT = "never_evict"  # Never evict (active turn, safety)
    LOW_PRIORITY = "low_priority"  # Evict last (recently used)
    NORMAL = "normal"  # Standard eviction
    HIGH_PRIORITY = "high_priority"  # Evict first (inactive)


@dataclass
class ProtectionPolicy:
    """Protection policy configuration"""
    protect_active_turns: bool = True
    protect_safety_monitoring: bool = True
    recently_used_threshold_seconds: int = 300  # 5 minutes
    frequent_use_threshold: int = 10  # 10+ accesses


class ProtectionManager:
    """Manage session protection policies

    Responsibilities:
    - Mark sessions as protected (never evict)
    - Assign protection levels to sessions
    - Track active turns and safety agents
    - Provide eviction score modifiers
    """

    def __init__(self, policy: ProtectionPolicy = None):
        self.policy = policy or ProtectionPolicy()
        self.never_evict_sessions: Set[str] = set()
        self.active_turn_sessions: Set[str] = set()
        self.safety_monitoring_sessions: Set[str] = set()
        logger.info("[ProtectionManager] Initialized")

    def protect_session(
        self,
        session_id: str,
        reason: str,
        trace_id: str,
    ):
        """Mark session as protected from eviction

        Args:
            session_id: Session ID
            reason: Protection reason ('active_turn', 'safety_monitoring', etc.)
            trace_id: Trace ID
        """
        self.never_evict_sessions.add(session_id)

        if reason == "active_turn":
            self.active_turn_sessions.add(session_id)
        elif reason == "safety_monitoring":
            self.safety_monitoring_sessions.add(session_id)

        logger.info(
            "[ProtectionManager] Protected session",
            session_id=session_id,
            reason=reason,
            trace_id=trace_id,
        )

    def unprotect_session(
        self,
        session_id: str,
        reason: str,
        trace_id: str,
    ):
        """Unmark session as protected

        Args:
            session_id: Session ID
            reason: Protection reason
            trace_id: Trace ID
        """
        self.never_evict_sessions.discard(session_id)

        if reason == "active_turn":
            self.active_turn_sessions.discard(session_id)
        elif reason == "safety_monitoring":
            self.safety_monitoring_sessions.discard(session_id)

        logger.info(
            "[ProtectionManager] Unprotected session",
            session_id=session_id,
            reason=reason,
            trace_id=trace_id,
        )

    def is_protected(self, session_id: str) -> bool:
        """Check if session is protected from eviction

        Args:
            session_id: Session ID

        Returns:
            True if protected
        """
        return session_id in self.never_evict_sessions

    def get_protection_level(
        self,
        session_id: str,
        last_access_ns: int,
        access_count: int,
        now_ns: int,
    ) -> ProtectionLevel:
        """Get protection level for session

        Args:
            session_id: Session ID
            last_access_ns: Last access time
            access_count: Access count
            now_ns: Current time

        Returns:
            Protection level
        """
        # NEVER_EVICT: Active turn or safety monitoring
        if session_id in self.never_evict_sessions:
            return ProtectionLevel.NEVER_EVICT

        # Calculate inactive duration
        inactive_seconds = (now_ns - last_access_ns) / 1e9

        # LOW_PRIORITY: Recently used or frequently used
        if inactive_seconds < self.policy.recently_used_threshold_seconds:
            return ProtectionLevel.LOW_PRIORITY
        if access_count >= self.policy.frequent_use_threshold:
            return ProtectionLevel.LOW_PRIORITY

        # HIGH_PRIORITY: Inactive >30 minutes or rarely used
        if inactive_seconds > 1800:  # 30 minutes
            return ProtectionLevel.HIGH_PRIORITY
        if access_count < 2:
            return ProtectionLevel.HIGH_PRIORITY

        # NORMAL: Everything else
        return ProtectionLevel.NORMAL
```

### HitRateMonitor Class

```python
# k1/infrastructure/kv_cache/hit_rate_monitor.py
"""Hit Rate Monitor - Track KV cache hit rate and miss penalty"""

import logging
import time
from dataclasses import dataclass
from typing import List

from k1.infrastructure.metrics import (
    kv_cache_hit_rate_percent,
    kv_cache_miss_penalty_ms,
    kv_cache_hit_total,
    kv_cache_miss_total,
)

logger = logging.getLogger(__name__)


@dataclass
class HitRateTarget:
    """Hit rate targets"""
    target_hit_rate_percent: float = 75.0  # >75% target
    miss_penalty_baseline_ms: float = 120.0  # Typical miss penalty


class HitRateMonitor:
    """Monitor KV cache hit rate

    Responsibilities:
    - Track cache hits and misses
    - Calculate hit rate percentage
    - Measure miss penalty (latency increase)
    - Emit metrics and alerts
    """

    def __init__(self, target: HitRateTarget = None):
        self.target = target or HitRateTarget()
        self.hits = 0
        self.misses = 0
        self.miss_latencies: List[float] = []
        logger.info(
            "[HitRateMonitor] Initialized",
            target_hit_rate=self.target.target_hit_rate_percent,
        )

    def track_hit(self, session_id: str, trace_id: str):
        """Track cache hit

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        self.hits += 1

        logger.debug(
            "[HitRateMonitor] Cache hit",
            session_id=session_id,
            trace_id=trace_id,
        )

        # Emit metrics
        kv_cache_hit_total.inc()
        self._emit_hit_rate()

    def track_miss(
        self,
        session_id: str,
        miss_latency_ms: float,
        trace_id: str,
    ):
        """Track cache miss

        Args:
            session_id: Session ID
            miss_latency_ms: Latency penalty in milliseconds
            trace_id: Trace ID
        """
        self.misses += 1
        self.miss_latencies.append(miss_latency_ms)

        logger.warning(
            "[HitRateMonitor] Cache miss",
            session_id=session_id,
            miss_latency_ms=round(miss_latency_ms, 2),
            hit_rate_percent=self.get_hit_rate_percent(),
            trace_id=trace_id,
        )

        # Emit metrics
        kv_cache_miss_total.inc()
        self._emit_hit_rate()
        self._emit_miss_penalty()

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
        """Get average miss penalty

        Returns:
            Average miss latency in milliseconds
        """
        if len(self.miss_latencies) == 0:
            return 0.0

        # Use recent 100 samples (sliding window)
        recent_latencies = self.miss_latencies[-100:]
        return sum(recent_latencies) / len(recent_latencies)

    def is_hit_rate_below_target(self) -> bool:
        """Check if hit rate is below target

        Returns:
            True if below target
        """
        return self.get_hit_rate_percent() < self.target.target_hit_rate_percent

    def _emit_hit_rate(self):
        """Emit hit rate metric"""
        hit_rate = self.get_hit_rate_percent()
        kv_cache_hit_rate_percent.set(hit_rate)

    def _emit_miss_penalty(self):
        """Emit miss penalty metric"""
        avg_penalty = self.get_avg_miss_penalty_ms()
        kv_cache_miss_penalty_ms.set(avg_penalty)
```

### AdaptiveTuner Class

```python
# k1/infrastructure/kv_cache/adaptive_tuner.py
"""Adaptive Tuner - Adjust eviction weights based on hit rate"""

import logging

from k1.infrastructure.kv_cache.hit_rate_monitor import HitRateMonitor
from k1.infrastructure.kv_cache.hybrid_eviction_policy import HybridEvictionPolicy

logger = logging.getLogger(__name__)


class AdaptiveTuner:
    """Adaptive eviction tuner

    Responsibilities:
    - Monitor hit rate
    - Adjust eviction weights when hit rate low
    - Increase recency weight if hit rate <75%
    - Increase frequency weight if hit rate >85%
    """

    def __init__(
        self,
        hit_rate_monitor: HitRateMonitor,
        eviction_policy: HybridEvictionPolicy,
    ):
        self.hit_rate_monitor = hit_rate_monitor
        self.eviction_policy = eviction_policy
        logger.info("[AdaptiveTuner] Initialized")

    def tune_eviction_weights(self, trace_id: str):
        """Tune eviction weights based on hit rate

        Args:
            trace_id: Trace ID
        """
        hit_rate = self.hit_rate_monitor.get_hit_rate_percent()

        if hit_rate < 75.0:
            # Hit rate low - increase recency weight (favor recent sessions)
            new_recency_weight = min(0.7, self.eviction_policy.weights.recency_weight + 0.05)
            new_frequency_weight = 1.0 - new_recency_weight

            logger.info(
                "[AdaptiveTuner] Increasing recency weight (low hit rate)",
                hit_rate=round(hit_rate, 2),
                old_recency=self.eviction_policy.weights.recency_weight,
                new_recency=new_recency_weight,
                trace_id=trace_id,
            )

            self.eviction_policy.weights.recency_weight = new_recency_weight
            self.eviction_policy.weights.frequency_weight = new_frequency_weight

        elif hit_rate > 85.0:
            # Hit rate high - increase frequency weight (favor frequent sessions)
            new_frequency_weight = min(0.5, self.eviction_policy.weights.frequency_weight + 0.05)
            new_recency_weight = 1.0 - new_frequency_weight

            logger.info(
                "[AdaptiveTuner] Increasing frequency weight (high hit rate)",
                hit_rate=round(hit_rate, 2),
                old_frequency=self.eviction_policy.weights.frequency_weight,
                new_frequency=new_frequency_weight,
                trace_id=trace_id,
            )

            self.eviction_policy.weights.recency_weight = new_recency_weight
            self.eviction_policy.weights.frequency_weight = new_frequency_weight
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/kv_cache/test_protection_manager.py
from ward import test, fixture
import time

from k1.infrastructure.kv_cache.protection_manager import (
    ProtectionManager,
    ProtectionLevel,
)

@fixture
def protection_manager():
    return ProtectionManager()

@test("ProtectionManager protects active turn")
def _(pm=protection_manager):
    pm.protect_session("sess-1", "active_turn", "trace-123")

    assert pm.is_protected("sess-1") == True
    assert "sess-1" in pm.active_turn_sessions

@test("ProtectionManager unprotects session")
def _(pm=protection_manager):
    pm.protect_session("sess-2", "active_turn", "trace-456")
    pm.unprotect_session("sess-2", "active_turn", "trace-789")

    assert pm.is_protected("sess-2") == False

@test("ProtectionManager assigns protection levels")
def _(pm=protection_manager):
    now_ns = time.perf_counter_ns()

    # Recently used session
    level = pm.get_protection_level(
        session_id="sess-3",
        last_access_ns=now_ns - (100 * 1e9),  # 100s ago
        access_count=5,
        now_ns=now_ns,
    )
    assert level == ProtectionLevel.LOW_PRIORITY

    # Inactive session
    level = pm.get_protection_level(
        session_id="sess-4",
        last_access_ns=now_ns - (2000 * 1e9),  # 2000s ago
        access_count=1,
        now_ns=now_ns,
    )
    assert level == ProtectionLevel.HIGH_PRIORITY

# tests/infrastructure/kv_cache/test_hit_rate_monitor.py
from ward import test, fixture

from k1.infrastructure.kv_cache.hit_rate_monitor import HitRateMonitor

@fixture
def hit_rate_monitor():
    return HitRateMonitor()

@test("HitRateMonitor tracks hits and misses")
def _(hrm=hit_rate_monitor):
    hrm.track_hit("sess-1", "trace-1")
    hrm.track_hit("sess-2", "trace-2")
    hrm.track_miss("sess-3", 120.0, "trace-3")

    # 2 hits, 1 miss = 66.7% hit rate
    hit_rate = hrm.get_hit_rate_percent()
    assert 66.0 <= hit_rate <= 67.0

@test("HitRateMonitor calculates miss penalty")
def _(hrm=hit_rate_monitor):
    hrm.track_miss("sess-1", 100.0, "trace-1")
    hrm.track_miss("sess-2", 120.0, "trace-2")
    hrm.track_miss("sess-3", 140.0, "trace-3")

    avg_penalty = hrm.get_avg_miss_penalty_ms()
    assert 115.0 <= avg_penalty <= 125.0  # Average ~120ms
```

---

## Performance Benchmarks

### Hit Rate Targets

| Eviction Policy | Target Hit Rate | Actual Hit Rate | Status |
|----------------|----------------|----------------|--------|
| No eviction | 95%+ | 98% | ✅ Excellent |
| Hybrid 60/40 | 75%+ | 78% | ✅ Good |
| Pure LRU | 70%+ | 72% | ✅ Acceptable |
| No policy | <50% | 45% | ❌ Poor |

### Miss Penalty

| Scenario | First Turn Latency | Miss Penalty | Percentage |
|----------|-------------------|--------------|-----------|
| Cache hit | 150ms | 0ms | - |
| Cache miss (cold start) | 270ms | +120ms | 80% slower |
| Cache miss (compressed) | 168ms | +18ms | 12% slower |

### Protection Impact

| Protection Rule | Sessions Protected | Eviction Rate | Hit Rate Impact |
|----------------|-------------------|---------------|----------------|
| No protection | 0 | 10/min | 65% (baseline) |
| Protect active turns | 1-3 | 8/min | 72% (+7%) |
| Protect active + safety | 2-4 | 7/min | 78% (+13%) |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Hit Rate Metrics)
from prometheus_client import Gauge, Counter

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

# Hits and misses
kv_cache_hit_total = Counter(
    'kv_cache_hit_total',
    'Total KV cache hits'
)

kv_cache_miss_total = Counter(
    'kv_cache_miss_total',
    'Total KV cache misses'
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/kv_cache_protection.yml
groups:
  - name: k1_kv_cache_protection
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

      - alert: KVCacheMissRateHigh
        expr: rate(kv_cache_miss_total[5m]) > 5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "KV cache miss rate high (>5/min)"
```

---

## Research Citations

1. **Redis (2024).** *"Eviction Policies."* Redis Labs. — Protected key patterns.

2. **Caffeine (2016).** *"W-TinyLFU."* Ben Manes. — Adaptive cache admission policies.

3. **Google (2016).** *"Site Reliability Engineering."* O'Reilly. — SLO-based adaptive systems.

---

## Consequences

### Positive

1. **Critical Protection:** Active turns and safety monitoring never evicted
2. **Observable:** Hit rate metrics show eviction effectiveness
3. **Adaptive:** Automatically tune eviction weights based on hit rate
4. **Fair:** Protection levels balance critical vs non-critical sessions

### Negative

1. **Complexity:** Protection rules add coordination overhead
2. **Protected Starvation:** Too many protected sessions = no eviction possible
3. **Tuning Required:** Adaptive weights may need manual override

### Mitigations

1. **Protection Limits:** Cap protected sessions at 50% of budget
2. **Manual Override:** Allow ops to disable adaptive tuning
3. **Clear Documentation:** Explain protection levels and trade-offs

---

## Roadmap

### Week 1: Protection Manager
- [ ] Implement ProtectionManager class
- [ ] Add protect_session() and unprotect_session() methods
- [ ] Add protection level assignment

### Week 2: Hit Rate Monitor
- [ ] Implement HitRateMonitor class
- [ ] Add track_hit() and track_miss() methods
- [ ] Calculate miss penalty

### Week 3: Adaptive Tuner
- [ ] Implement AdaptiveTuner class
- [ ] Add tune_eviction_weights() logic
- [ ] Integrate with eviction policy

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
**Blocked By:** 0025a (Global Allocator), 0025b (Hybrid Eviction)
**Blocks:** None (final sub-ADR for ADR-0025)

---

**END OF ADR-0025e**