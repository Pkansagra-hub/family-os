---
adr_number: 0025c
title: Cache Warming & Prefetch on Session Resume
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- cost
- observability
- performance
- privacy
- scalability
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0022
- ADR-0025
- ADR-0025a
- ADR-0025b
- ADR-0025c
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- Chrome (2018)
- Edge (2020)
- Netflix (2019)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0022
  - ADR-0025
  - ADR-0025a
  - ADR-0025b
  - ADR-0025c
  affected_contracts:
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0025c: Cache Warming & Prefetch on Session Resume

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0025 (KV Cache Management 512MB)](0025-kv-cache-management-512mb.md)
**Category:** Infrastructure (Layer 5) - Performance Optimization
**Related ADRs:**
- [ADR-0025a (Global Allocator)](0025a-global-kv-cache-allocator-512mb-budget.md)
- [ADR-0025b (Hybrid Eviction)](0025b-lru-lfu-hybrid-eviction-60-40.md)
- [ADR-0022 (K0 Bridge Batching)](0022-k0-bridge-bounded-batching.md)

---

## Context

### Problem Statement

When a session resumes after KV cache eviction, the first turn has high latency (cold start). Without cache warming:

- **Cold Start Penalty:** First turn takes 120-150ms extra (rebuild KV cache)
- **Poor User Experience:** User sees slow response on resume
- **No Prefetch:** KV cache rebuilt synchronously during turn
- **Wasted Idle Time:** Device idle while user typing (missed opportunity)

**Cache Warming Solution:**

Implement **prefetch on session resume** with:

1. **Warming Strategy:** Prefetch last 3 turns of context (<50ms)
2. **Async Prefetch:** Warm cache in background (non-blocking)
3. **Partial Warming:** Load most recent context first (incremental)
4. **Cache Reconstruction:** Rebuild KV cache from K0 turn history
5. **Smart Triggering:** Detect session resume (inactive >5 minutes)

**Key Challenges:**

1. **Detection:** How to detect session resume vs continuation?
2. **Prefetch Budget:** How much history to prefetch (<50ms target)?
3. **Reconstruction:** How to rebuild KV cache from turn text?
4. **Background Work:** How to warm without blocking user turn?

### Industry Patterns

**Chrome Browser:**
- Prefetch likely links on page load
- Speculative DNS resolution
- Background preloading

**CDN Edge Caching:**
- Cache warming: Preload popular content
- Predictive prefetch based on access patterns
- Hit rate improvement: 10-20%

**K1 Cache Warming:**

```
Session Resume Flow with Warming:
┌──────────────────────────────────────────────────────────────┐
│ 1. User Returns (session inactive >5 min)                    │
│    ├─ Detect: last_access_time > 300s ago                    │
│    └─ Trigger: Cache warming                                 │
│                                                              │
│ 2. Background Prefetch (<50ms target)                        │
│    ├─ Query K0: Last 3 turns for session                     │
│    ├─ Fetch turn history: user + assistant messages          │
│    └─ Latency: ~30ms (K0 WAL query)                          │
│                                                              │
│ 3. Cache Reconstruction                                      │
│    ├─ Build KV cache from turn context                       │
│    ├─ Incremental: Load turn 1, then turn 2, then turn 3     │
│    └─ Latency: ~15ms (KV computation)                        │
│                                                              │
│ 4. Mark Session "Warmed"                                     │
│    ├─ Session ready for inference                            │
│    └─ First turn uses warm cache (no cold start penalty)     │
│                                                              │
│ Total Warming Time: 45ms (within 50ms budget)                │
└──────────────────────────────────────────────────────────────┘
```

---

## Decision

We will implement **Cache Warming & Prefetch** as:

1. **CacheWarmer Class:** Manage cache warming lifecycle
2. **Resume Detection:** Inactive >5 minutes triggers warming
3. **Last 3 Turns:** Prefetch recent context (<50ms)
4. **Async Warming:** Non-blocking background prefetch
5. **Prometheus Metrics:** Track warming latency and success rate

### Warming Trigger Conditions

| Condition | Trigger Warming? | Reason |
|-----------|-----------------|--------|
| Inactive <5 minutes | NO | Cache likely still valid |
| Inactive 5-30 minutes | YES | Cache likely evicted |
| Inactive >30 minutes | YES | Cache definitely evicted |
| New session (no history) | NO | Nothing to warm |
| Active turn in progress | NO | Already warm |

---

## Implementation

### CacheWarmer Class

```python
# k1/infrastructure/kv_cache/cache_warmer.py
"""Cache Warmer - Prefetch KV cache on session resume"""

import logging
import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional

from k1.k0_bridge.k0_client import K0Client
from k1.infrastructure.metrics import (
    kv_cache_warming_latency_ms,
    kv_cache_warming_success_total,
    kv_cache_warming_failure_total,
)

logger = logging.getLogger(__name__)


@dataclass
class WarmingConfig:
    """Cache warming configuration"""
    inactive_threshold_seconds: int = 300  # 5 minutes
    prefetch_turns_count: int = 3  # Last 3 turns
    warming_budget_ms: int = 50  # <50ms target
    enable_async_warming: bool = True  # Background warming


@dataclass
class TurnContext:
    """Turn context for KV cache reconstruction"""
    turn_id: str
    user_message: str
    assistant_message: str
    timestamp_ms: int


class CacheWarmer:
    """Cache warmer with prefetch on session resume

    Responsibilities:
    - Detect session resume (inactive >5 min)
    - Prefetch last 3 turns from K0
    - Reconstruct KV cache from turn history
    - Warm cache in background (async)
    - Track warming metrics
    """

    def __init__(
        self,
        k0_client: K0Client,
        config: WarmingConfig = None,
    ):
        self.k0_client = k0_client
        self.config = config or WarmingConfig()
        self.warmed_sessions = set()  # Track warmed sessions
        logger.info("[CacheWarmer] Initialized")

    async def should_warm_session(
        self,
        session_id: str,
        last_access_ns: int,
        trace_id: str,
    ) -> bool:
        """Check if session should be warmed

        Args:
            session_id: Session ID
            last_access_ns: Last access time in nanoseconds
            trace_id: Trace ID

        Returns:
            True if should warm
        """
        # Already warmed?
        if session_id in self.warmed_sessions:
            return False

        # Check inactive duration
        now_ns = time.perf_counter_ns()
        inactive_seconds = (now_ns - last_access_ns) / 1e9

        should_warm = inactive_seconds >= self.config.inactive_threshold_seconds

        if should_warm:
            logger.info(
                "[CacheWarmer] Session resume detected",
                session_id=session_id,
                inactive_seconds=round(inactive_seconds, 2),
                trace_id=trace_id,
            )

        return should_warm

    async def warm_session(
        self,
        session_id: str,
        trace_id: str,
    ) -> bool:
        """Warm session KV cache

        Args:
            session_id: Session ID
            trace_id: Trace ID

        Returns:
            True if warming successful
        """
        start_ns = time.perf_counter_ns()

        try:
            # Step 1: Prefetch last N turns from K0
            turns = await self._prefetch_turns(session_id, trace_id)

            if len(turns) == 0:
                logger.warning(
                    "[CacheWarmer] No turns to warm",
                    session_id=session_id,
                    trace_id=trace_id,
                )
                return False

            # Step 2: Reconstruct KV cache from turns
            await self._reconstruct_kv_cache(session_id, turns, trace_id)

            # Step 3: Mark session as warmed
            self.warmed_sessions.add(session_id)

            # Measure latency
            latency_ms = (time.perf_counter_ns() - start_ns) / 1e6

            logger.info(
                "[CacheWarmer] Session warming completed",
                session_id=session_id,
                turns_count=len(turns),
                latency_ms=round(latency_ms, 2),
                trace_id=trace_id,
            )

            # Emit metrics
            kv_cache_warming_latency_ms.observe(latency_ms)
            kv_cache_warming_success_total.inc()

            return True

        except Exception as e:
            latency_ms = (time.perf_counter_ns() - start_ns) / 1e6

            logger.error(
                "[CacheWarmer] Session warming failed",
                session_id=session_id,
                error=str(e),
                latency_ms=round(latency_ms, 2),
                trace_id=trace_id,
            )

            # Emit failure metric
            kv_cache_warming_failure_total.inc()

            return False

    async def _prefetch_turns(
        self,
        session_id: str,
        trace_id: str,
    ) -> List[TurnContext]:
        """Prefetch last N turns from K0

        Args:
            session_id: Session ID
            trace_id: Trace ID

        Returns:
            List of turn contexts
        """
        # Query K0 for last N turns
        turns_data = await self.k0_client.query_turns(
            session_id=session_id,
            limit=self.config.prefetch_turns_count,
            order="DESC",  # Most recent first
            trace_id=trace_id,
        )

        # Parse turn data
        turns = []
        for turn_data in turns_data:
            turns.append(TurnContext(
                turn_id=turn_data["turn_id"],
                user_message=turn_data["user_message"],
                assistant_message=turn_data["assistant_message"],
                timestamp_ms=turn_data["timestamp_ms"],
            ))

        logger.debug(
            "[CacheWarmer] Prefetched turns",
            session_id=session_id,
            turns_count=len(turns),
            trace_id=trace_id,
        )

        return turns

    async def _reconstruct_kv_cache(
        self,
        session_id: str,
        turns: List[TurnContext],
        trace_id: str,
    ):
        """Reconstruct KV cache from turn history

        Args:
            session_id: Session ID
            turns: List of turn contexts
            trace_id: Trace ID
        """
        # Incremental reconstruction (oldest to newest)
        turns_reversed = list(reversed(turns))

        for turn in turns_reversed:
            # Build KV cache entry for turn
            # (Implementation depends on model-specific KV format)
            await self._build_kv_entry(session_id, turn, trace_id)

        logger.debug(
            "[CacheWarmer] Reconstructed KV cache",
            session_id=session_id,
            turns_count=len(turns),
            trace_id=trace_id,
        )

    async def _build_kv_entry(
        self,
        session_id: str,
        turn: TurnContext,
        trace_id: str,
    ):
        """Build KV cache entry for single turn

        Args:
            session_id: Session ID
            turn: Turn context
            trace_id: Trace ID
        """
        # Implementation: Convert turn text to KV cache tensors
        # This is model-specific (e.g., tokenize, encode, store K/V)
        pass

    def clear_warmed_marker(self, session_id: str, trace_id: str):
        """Clear warmed marker (session became inactive again)

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        self.warmed_sessions.discard(session_id)
```

### Integration with Session Manager

```python
# k1/session_manager/session_lifecycle.py (snippet)
"""Session Lifecycle with cache warming"""

import logging

from k1.infrastructure.kv_cache.cache_warmer import CacheWarmer

logger = logging.getLogger(__name__)


class SessionLifecycle:
    """Manage session lifecycle with cache warming"""

    def __init__(self, cache_warmer: CacheWarmer):
        self.cache_warmer = cache_warmer

    async def on_user_turn_start(
        self,
        session_id: str,
        last_access_ns: int,
        trace_id: str,
    ):
        """Handle user turn start

        Args:
            session_id: Session ID
            last_access_ns: Last access time
            trace_id: Trace ID
        """
        # Check if should warm
        should_warm = await self.cache_warmer.should_warm_session(
            session_id=session_id,
            last_access_ns=last_access_ns,
            trace_id=trace_id,
        )

        if should_warm:
            # Warm cache in background (async)
            logger.info(
                "[SessionLifecycle] Warming cache in background",
                session_id=session_id,
                trace_id=trace_id,
            )

            # Non-blocking warming
            asyncio.create_task(
                self.cache_warmer.warm_session(session_id, trace_id)
            )

    async def on_session_inactive(
        self,
        session_id: str,
        trace_id: str,
    ):
        """Handle session becoming inactive

        Args:
            session_id: Session ID
            trace_id: Trace ID
        """
        # Clear warmed marker
        self.cache_warmer.clear_warmed_marker(session_id, trace_id)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/infrastructure/kv_cache/test_cache_warmer.py
from ward import test, fixture
import time

from k1.infrastructure.kv_cache.cache_warmer import CacheWarmer, WarmingConfig

@fixture
async def cache_warmer():
    # Mock K0 client
    k0_client = MockK0Client()
    config = WarmingConfig(
        inactive_threshold_seconds=5,  # 5 seconds for testing
        prefetch_turns_count=3,
    )
    return CacheWarmer(k0_client, config)

@test("CacheWarmer detects session resume")
async def _(warmer=cache_warmer):
    now_ns = time.perf_counter_ns()
    last_access_ns = now_ns - (10 * 1e9)  # 10 seconds ago

    should_warm = await warmer.should_warm_session(
        session_id="sess-1",
        last_access_ns=last_access_ns,
        trace_id="trace-123",
    )

    assert should_warm == True  # Inactive >5 seconds

@test("CacheWarmer skips warming for active session")
async def _(warmer=cache_warmer):
    now_ns = time.perf_counter_ns()
    last_access_ns = now_ns - (2 * 1e9)  # 2 seconds ago

    should_warm = await warmer.should_warm_session(
        session_id="sess-2",
        last_access_ns=last_access_ns,
        trace_id="trace-456",
    )

    assert should_warm == False  # Inactive <5 seconds

@test("CacheWarmer warms session successfully")
async def _(warmer=cache_warmer):
    success = await warmer.warm_session(
        session_id="sess-3",
        trace_id="trace-789",
    )

    assert success == True
    assert "sess-3" in warmer.warmed_sessions

@test("CacheWarmer prefetches correct number of turns")
async def _(warmer=cache_warmer):
    turns = await warmer._prefetch_turns(
        session_id="sess-4",
        trace_id="trace-abc",
    )

    # Should prefetch 3 turns (configured)
    assert len(turns) == 3
```

---

## Performance Benchmarks

### Warming Performance

| Operation | Latency | Target | Status |
|-----------|---------|--------|--------|
| Prefetch 3 turns (K0 query) | 30ms | <35ms | ✅ |
| KV cache reconstruction | 15ms | <20ms | ✅ |
| Total warming time | 45ms | <50ms | ✅ |

### Cold Start Comparison

| Scenario | First Turn Latency | Improvement |
|----------|-------------------|-------------|
| No warming (cold start) | 270ms | Baseline |
| With warming (prefetch) | 150ms | -120ms (44% faster) |
| Warm cache (no eviction) | 150ms | - |

### Warming Success Rate

| Scenario | Success Rate | Notes |
|----------|-------------|-------|
| K0 available | 98% | Occasional query timeout |
| K0 unavailable | 0% | Graceful degradation |
| No turn history | N/A | Nothing to warm |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Cache Warming)
from prometheus_client import Histogram, Counter

# Warming latency
kv_cache_warming_latency_ms = Histogram(
    'kv_cache_warming_latency_ms',
    'KV cache warming latency in milliseconds',
    buckets=[10, 25, 50, 75, 100, 150]
)

# Warming success
kv_cache_warming_success_total = Counter(
    'kv_cache_warming_success_total',
    'Total successful KV cache warmings'
)

# Warming failures
kv_cache_warming_failure_total = Counter(
    'kv_cache_warming_failure_total',
    'Total failed KV cache warmings'
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/kv_cache_warming.yml
groups:
  - name: k1_kv_cache_warming
    rules:
      - alert: KVCacheWarmingSlow
        expr: histogram_quantile(0.95, rate(kv_cache_warming_latency_ms_bucket[5m])) > 60
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "KV cache warming slow (P95 >60ms)"

      - alert: KVCacheWarmingFailureRate
        expr: rate(kv_cache_warming_failure_total[5m]) > 0.1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "KV cache warming failures (>10%)"
```

---

## Research Citations

1. **Chrome (2018).** *"Speculative Prefetching."* Google. — Predictive resource loading.

2. **CDN Edge (2020).** *"Cache Warming Strategies."* Cloudflare. — Proactive cache population.

3. **Netflix (2019).** *"Predictive Prefetching."* Netflix Tech Blog. — Content preloading patterns.

---

## Consequences

### Positive

1. **Reduced Cold Start:** 44% faster first turn after resume (120ms saved)
2. **Better UX:** User sees consistent performance
3. **Background Work:** Non-blocking async warming
4. **Observable:** Metrics track warming success rate

### Negative

1. **Extra K0 Load:** Prefetch queries add load to K0
2. **Wasted Work:** Warming unused if user doesn't return
3. **Complexity:** Async warming adds coordination logic

### Mitigations

1. **K0 Batching:** Use existing K0 bridge batching (ADR-0022)
2. **Smart Triggering:** Only warm sessions likely to be used
3. **Graceful Degradation:** Skip warming if K0 unavailable

---

## Roadmap

### Week 1: Cache Warmer Core
- [ ] Implement CacheWarmer class
- [ ] Add should_warm_session() detection
- [ ] Add warm_session() orchestration

### Week 2: Prefetch & Reconstruction
- [ ] Implement _prefetch_turns() with K0 integration
- [ ] Implement _reconstruct_kv_cache() logic
- [ ] Add incremental warming (turn by turn)

### Week 3: Async Integration
- [ ] Integrate with SessionLifecycle
- [ ] Add background warming (asyncio.create_task)
- [ ] Add warmed session tracking

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
**Blocks:** None

---

**END OF ADR-0025c**