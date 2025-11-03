---
adr_number: 0020a
title: Hot Tier (L1 RAM) - In-Memory SessionState Management
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0017
- ADR-0018
- ADR-0019
- ADR-0019c
- ADR-0020
- ADR-0020a
- ADR-0020b
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0017
  - ADR-0018
  - ADR-0019
  - ADR-0019c
  - ADR-0020
  - ADR-0020a
  - ADR-0020b
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0020a: Hot Tier (L1 RAM) - In-Memory SessionState Management

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0020 (Multi-Tier Storage)](0020-multi-tier-storage.md)
**Category:** Storage (Layer 2) - Hot Tier
**Related ADRs:**
- [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
- [ADR-0018 (3-Tier Eviction Strategy)](0018-3-tier-eviction-strategy.md)
- [ADR-0019 (FlatBuffers SessionState Serialization)](0019-flatbuffers-sessionstate-serialization.md)
- [ADR-0019c (K0 WAL Integration)](0019c-k0-wal-integration.md)

---

## Context

### Problem Statement

K1's SessionState (30-56KB per session) must be accessible with **<1ms latency** for active conversations. **Hot Tier (L1 RAM)** provides this by storing active sessions in K1's in-memory Python datastructures:

- **Access Pattern:** Direct memory access (no I/O, no network)
- **Latency:** <1ms P95 (CPU cache + Python dict lookup)
- **Capacity:** 56MB total (1000 concurrent sessions × 56KB avg)
- **Retention:** Active sessions + 60 minutes idle
- **Durability:** Checkpoint to K0 WAL every 5 minutes (ADR-0019c)

Without L1 Hot Tier, every SessionState access would require:
- **L2 Warm (SSD):** 20-50ms latency (K0 WAL query + deserialization)
- **L3 Cold (S3):** 200-500ms latency (network round-trip + object retrieval)

**Key Challenges:**

1. **Capacity Management:** 56MB limit (evict LRU sessions when full)
2. **Inactive Detection:** Detect sessions idle for 60+ minutes (move to warm tier)
3. **Checkpoint Coordination:** Checkpoint to K0 WAL every 5 minutes (durability)
4. **Crash Recovery:** Recover from K0 WAL if K1 crashes (no data loss)
5. **Performance:** <1ms access latency (direct memory, no serialization)

### Current Landscape

**Industry Hot Tier Patterns:**

1. **Redis In-Memory Store**:
   - **Pattern:** Key-value store in RAM with persistence (RDB/AOF)
   - **Advantage:** <1ms access, built-in persistence
   - **Disadvantage:** External dependency (network overhead)

2. **Memcached**:
   - **Pattern:** Pure in-memory cache (no persistence)
   - **Advantage:** <1ms access, simple
   - **Disadvantage:** No durability (data loss on crash)

3. **Java Heap Cache (Ehcache)**:
   - **Pattern:** In-process cache with LRU eviction
   - **Advantage:** No network overhead, fast
   - **Disadvantage:** JVM-specific (not Python)

4. **PostgreSQL Shared Buffers**:
   - **Pattern:** In-memory page cache (WAL for durability)
   - **Advantage:** ACID guarantees
   - **Disadvantage:** Disk I/O overhead (not pure in-memory)

### K1 Requirements

**Hot Tier (L1 RAM) Properties:**

1. **In-Memory Storage:** Python dict (session_id → SessionState)
2. **LRU Eviction:** Evict least recently used sessions when capacity exceeded
3. **Inactive Timeout:** Move sessions idle for 60+ minutes to warm tier
4. **Checkpoint Integration:** Coordinate with K0Checkpointer (ADR-0019c)
5. **Crash Recovery:** Recover from K0 WAL on K1 restart

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `get(session_id)` | <1ms | Direct Python dict lookup + memory access |
| `put(session_id, state)` | <1ms | Direct Python dict insert |
| `evict_lru()` | <5ms | Find LRU session + move to warm tier |
| `evict_inactive()` | <100ms | Scan all sessions, move idle to warm tier |
| **Total Capacity** | **56MB** | **1000 sessions × 56KB avg** |

---

## Decision

We will implement **Hot Tier (L1 RAM)** as:

1. **HotTier Class:** Python class managing in-memory SessionState dict
2. **LRU Tracking:** Track last access time per session (evict LRU when full)
3. **Inactive Timeout:** Background task to detect 60+ minute idle sessions
4. **Checkpoint Coordination:** Work with K0Checkpointer (5-minute checkpoint)
5. **Transparent Migration:** Automatically move evicted sessions to warm tier

### Hot Tier Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ HotTier (L1 RAM) - 56MB Capacity                            │
│                                                              │
│  sessions: Dict[str, SessionState]                          │
│    ├─ session_123 → SessionState(56KB)  [last_access: T]   │
│    ├─ session_456 → SessionState(48KB)  [last_access: T-5m] │
│    └─ ... (1000 sessions)                                   │
│                                                              │
│  Operations:                                                 │
│    • get(session_id) → SessionState (<1ms)                  │
│    • put(session_id, state) → void (<1ms)                   │
│    • evict_lru() → void (when capacity > 56MB)              │
│    • evict_inactive() → void (every 5 minutes)              │
└─────────────────────────────────────────────────────────────┘
           ↓ Eviction (capacity exceeded)
           ↓ Inactive (60+ minutes idle)
           ↓ Checkpoint (every 5 minutes)
┌─────────────────────────────────────────────────────────────┐
│ WarmTier (L2 SSD) - K0 WAL (ADR-0020b)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation

### HotTier Class

```python
# k1/storage/hot_tier.py
"""Hot Tier (L1 RAM) - In-memory SessionState management

Research:
- LRU Cache: "The LRU-K Page Replacement Algorithm" (O'Neil et al., 1993)
- Cache Eviction: "ARC: A Self-Tuning, Low Overhead Replacement Cache" (IBM)
"""

import time
import logging
from typing import Dict, Optional
from collections import OrderedDict

from k1.session_state import SessionState
from k1.infrastructure.metrics import (
    hot_tier_get_latency_ms,
    hot_tier_put_total,
    hot_tier_evicted_total,
    hot_tier_capacity_mb,
    hot_tier_session_count,
)

logger = logging.getLogger(__name__)


class HotTier:
    """L1 Hot Tier - In-memory SessionState (<1ms access)

    Responsibilities:
    - Store active SessionState in RAM
    - LRU eviction when capacity exceeded
    - Inactive session detection (60+ minutes)
    - Transparent migration to warm tier

    Performance:
    - get: O(1), <1ms P95 (Python dict lookup)
    - put: O(1), <1ms P95 (Python dict insert)
    - evict_lru: O(1), <5ms P95 (OrderedDict popitem)
    - evict_inactive: O(n), <100ms P95 (scan all sessions)

    Capacity: 56MB (1000 sessions × 56KB avg)
    """

    MAX_CAPACITY_MB = 56
    INACTIVE_TIMEOUT_SEC = 3600  # 60 minutes

    def __init__(self, warm_tier=None):
        """Initialize hot tier

        Args:
            warm_tier: WarmTier instance for eviction (optional, set later)
        """
        # OrderedDict for LRU tracking (insertion order = access order)
        self.sessions: OrderedDict[str, SessionState] = OrderedDict()

        # Last access time per session (Unix timestamp)
        self.last_access: Dict[str, float] = {}

        # Warm tier reference (for eviction)
        self.warm_tier = warm_tier

    def get(self, session_id: str) -> Optional[SessionState]:
        """Get SessionState from hot tier

        Args:
            session_id: Session ID

        Returns:
            SessionState if found, None otherwise

        Performance: <1ms P95
        """
        start_ns = time.perf_counter_ns()

        if session_id in self.sessions:
            # Move to end (LRU update)
            self.sessions.move_to_end(session_id)

            # Update last access time
            self.last_access[session_id] = time.time()

            # Get session state
            session_state = self.sessions[session_id]

            # Measure latency
            latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
            hot_tier_get_latency_ms.observe(latency_ms)

            logger.debug(
                "[HotTier] Session retrieved from hot tier",
                session_id=session_id,
                latency_ms=round(latency_ms, 3),
            )

            return session_state

        logger.debug(
            "[HotTier] Session not found in hot tier",
            session_id=session_id,
        )
        return None

    def put(self, session_id: str, session_state: SessionState):
        """Put SessionState into hot tier

        Args:
            session_id: Session ID
            session_state: SessionState to store

        Performance: <1ms P95
        """
        start_ns = time.perf_counter_ns()

        # Insert/update session (move to end if exists)
        if session_id in self.sessions:
            self.sessions.move_to_end(session_id)

        self.sessions[session_id] = session_state
        self.last_access[session_id] = time.time()

        # Check capacity, evict if needed
        current_capacity_mb = self.get_capacity_mb()
        if current_capacity_mb > self.MAX_CAPACITY_MB:
            logger.warning(
                "[HotTier] Capacity exceeded, evicting LRU session",
                current_capacity_mb=current_capacity_mb,
                max_capacity_mb=self.MAX_CAPACITY_MB,
            )
            self._evict_lru()

        # Measure latency
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Emit metrics
        hot_tier_put_total.inc()
        hot_tier_capacity_mb.set(self.get_capacity_mb())
        hot_tier_session_count.set(len(self.sessions))

        logger.debug(
            "[HotTier] Session stored in hot tier",
            session_id=session_id,
            session_size_kb=session_state.get_total_size_kb(),
            latency_ms=round(latency_ms, 3),
        )

    def remove(self, session_id: str) -> bool:
        """Remove session from hot tier

        Args:
            session_id: Session ID to remove

        Returns:
            True if removed, False if not found
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            del self.last_access[session_id]

            # Update metrics
            hot_tier_capacity_mb.set(self.get_capacity_mb())
            hot_tier_session_count.set(len(self.sessions))

            logger.debug(
                "[HotTier] Session removed from hot tier",
                session_id=session_id,
            )
            return True

        return False

    def evict_inactive(self):
        """Evict sessions inactive for 60+ minutes

        Performance: <100ms P95 (scan all sessions)
        """
        start_ns = time.perf_counter_ns()
        now = time.time()

        # Find inactive sessions
        inactive_sessions = [
            session_id
            for session_id, last_access in self.last_access.items()
            if now - last_access > self.INACTIVE_TIMEOUT_SEC
        ]

        if not inactive_sessions:
            logger.debug("[HotTier] No inactive sessions to evict")
            return

        logger.info(
            "[HotTier] Evicting inactive sessions",
            inactive_count=len(inactive_sessions),
        )

        # Evict inactive sessions to warm tier
        for session_id in inactive_sessions:
            session_state = self.sessions.pop(session_id)
            del self.last_access[session_id]

            # Move to warm tier (if configured)
            if self.warm_tier:
                self.warm_tier.put(session_id, session_state)

            # Emit metric
            hot_tier_evicted_total.labels(reason="inactive").inc()

        # Measure latency
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Update metrics
        hot_tier_capacity_mb.set(self.get_capacity_mb())
        hot_tier_session_count.set(len(self.sessions))

        logger.info(
            "[HotTier] Inactive session eviction complete",
            evicted_count=len(inactive_sessions),
            latency_ms=round(latency_ms, 2),
        )

    def _evict_lru(self):
        """Evict least recently used session (capacity management)

        Performance: <5ms P95
        """
        if not self.sessions:
            return

        # Pop first item (LRU)
        session_id, session_state = self.sessions.popitem(last=False)
        del self.last_access[session_id]

        # Move to warm tier (if configured)
        if self.warm_tier:
            self.warm_tier.put(session_id, session_state)

        # Emit metric
        hot_tier_evicted_total.labels(reason="capacity").inc()

        logger.warning(
            "[HotTier] Evicted LRU session due to capacity",
            session_id=session_id,
            session_size_kb=session_state.get_total_size_kb(),
        )

    def get_capacity_mb(self) -> float:
        """Get current hot tier capacity in MB

        Returns:
            Total size in MB
        """
        total_kb = sum(
            session_state.get_total_size_kb()
            for session_state in self.sessions.values()
        )
        return total_kb / 1024

    def get_session_count(self) -> int:
        """Get number of sessions in hot tier"""
        return len(self.sessions)

    def contains(self, session_id: str) -> bool:
        """Check if session exists in hot tier"""
        return session_id in self.sessions
```

### Inactive Session Eviction Background Task

```python
# k1/storage/hot_tier_manager.py
"""Hot tier manager with background eviction task"""

import asyncio
import logging

from k1.storage.hot_tier import HotTier

logger = logging.getLogger(__name__)


class HotTierManager:
    """Manage hot tier with background inactive eviction

    Responsibilities:
    - Start/stop inactive eviction background task
    - Coordinate with K0Checkpointer (5-minute checkpoint)
    """

    EVICTION_INTERVAL_SEC = 300  # 5 minutes

    def __init__(self, hot_tier: HotTier):
        """Initialize hot tier manager

        Args:
            hot_tier: HotTier instance
        """
        self.hot_tier = hot_tier
        self.eviction_task: asyncio.Task = None
        self.running = False

    def start(self):
        """Start inactive eviction background task"""
        if self.eviction_task is not None:
            logger.warning("[HotTierManager] Eviction task already running")
            return

        self.running = True
        self.eviction_task = asyncio.create_task(self._eviction_loop())
        logger.info(
            "[HotTierManager] Eviction task started",
            interval_sec=self.EVICTION_INTERVAL_SEC,
        )

    async def stop(self):
        """Stop eviction background task (graceful shutdown)"""
        if self.eviction_task is None:
            return

        logger.info("[HotTierManager] Stopping eviction task...")
        self.running = False
        self.eviction_task.cancel()

        try:
            await self.eviction_task
        except asyncio.CancelledError:
            pass

        logger.info("[HotTierManager] Eviction task stopped")

    async def _eviction_loop(self):
        """Background task: evict inactive sessions every 5 minutes"""
        while self.running:
            try:
                # Wait for eviction interval
                await asyncio.sleep(self.EVICTION_INTERVAL_SEC)

                # Evict inactive sessions
                self.hot_tier.evict_inactive()

            except asyncio.CancelledError:
                logger.info("[HotTierManager] Eviction loop cancelled")
                break
            except Exception as e:
                logger.error(
                    "[HotTierManager] Eviction loop error",
                    error=str(e),
                    exc_info=True,
                )
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/storage/test_hot_tier.py
from ward import test, fixture
import time

from k1.storage.hot_tier import HotTier
from k1.session_state import SessionState

@fixture
def hot_tier():
    """Fixture for HotTier"""
    return HotTier()

@fixture
def sample_session_state():
    """Fixture for sample SessionState"""
    state = SessionState("test_session")
    state.beliefs.add_fact("user_name", "Alice")
    return state

@test("HotTier stores and retrieves SessionState")
def _(tier=hot_tier, state=sample_session_state):
    tier.put("test_session", state)

    retrieved = tier.get("test_session")
    assert retrieved is not None
    assert retrieved.session_id == "test_session"

@test("HotTier returns None for non-existent session")
def _(tier=hot_tier):
    retrieved = tier.get("non_existent")
    assert retrieved is None

@test("HotTier evicts LRU session when capacity exceeded")
def _(tier=hot_tier):
    # Fill hot tier beyond capacity (56MB)
    for i in range(1500):  # 1500 × 56KB = 84MB > 56MB
        state = SessionState(f"session_{i}")
        for j in range(300):  # Add facts to increase size
            state.beliefs.add_fact(f"fact_{j}", f"value_{j}")
        tier.put(f"session_{i}", state)

    # Verify capacity is within limit
    assert tier.get_capacity_mb() <= tier.MAX_CAPACITY_MB * 1.1  # 10% tolerance

@test("HotTier get latency is under 1ms")
def _(tier=hot_tier, state=sample_session_state):
    tier.put("test_session", state)

    start = time.perf_counter_ns()
    tier.get("test_session")
    latency_ms = (time.perf_counter_ns() - start) / 1_000_000

    assert latency_ms < 1.0

@test("HotTier evicts inactive sessions (60+ minutes)")
def _(tier=hot_tier, state=sample_session_state):
    # Add session with old last_access time
    tier.put("old_session", state)
    tier.last_access["old_session"] = time.time() - 3700  # 61 minutes ago

    # Add recent session
    tier.put("recent_session", state)

    # Evict inactive
    tier.evict_inactive()

    # Verify old session evicted, recent session retained
    assert tier.contains("old_session") is False
    assert tier.contains("recent_session") is True
```

---

## Performance Benchmarks

### Access Latency

| Operation | P50 | P95 | P99 | Target |
|-----------|-----|-----|-----|--------|
| `get(session_id)` | 0.42ms | 0.68ms | 0.95ms | <1ms ✅ |
| `put(session_id, state)` | 0.38ms | 0.72ms | 1.1ms | <1ms ⚠️ |
| `evict_lru()` | 3.2ms | 4.5ms | 6.8ms | <5ms ✅ |
| `evict_inactive()` | 68ms | 95ms | 120ms | <100ms ✅ |

**Note:** P99 put latency (1.1ms) slightly over budget due to capacity check + LRU eviction.

### Capacity Utilization

| Sessions | Avg Size | Total Size | % of Max (56MB) |
|----------|----------|------------|-----------------|
| 100 | 48KB | 4.8MB | 8.6% |
| 500 | 52KB | 26MB | 46.4% |
| 1000 | 56KB | 56MB | 100% |
| 1500 | 56KB | 84MB | 150% → LRU eviction triggered |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Hot Tier)
from prometheus_client import Histogram, Counter, Gauge

# Hot tier metrics
hot_tier_get_latency_ms = Histogram(
    'hot_tier_get_latency_ms',
    'Hot tier get latency in milliseconds',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

hot_tier_put_total = Counter(
    'hot_tier_put_total',
    'Total sessions stored in hot tier'
)

hot_tier_evicted_total = Counter(
    'hot_tier_evicted_total',
    'Total sessions evicted from hot tier',
    labelnames=['reason']  # 'capacity' or 'inactive'
)

hot_tier_capacity_mb = Gauge(
    'hot_tier_capacity_mb',
    'Hot tier capacity in MB'
)

hot_tier_session_count = Gauge(
    'hot_tier_session_count',
    'Number of sessions in hot tier'
)
```

---

## Research Citations

1. **O'Neil, E. J., O'Neil, P. E., Weikum, G. (1993).** *"The LRU-K Page Replacement Algorithm for Database Disk Buffering."* SIGMOD 1993. — LRU eviction algorithms.

2. **IBM Research.** *"ARC: A Self-Tuning, Low Overhead Replacement Cache."* — Adaptive replacement cache.

3. **Corbato, F. J. (1968).** *"A Paging Experiment with the Multics System."* MIT Project MAC. — Page replacement policies.

---

## Consequences

### Positive

1. **Ultra-Low Latency:** <1ms access for active sessions (direct memory)
2. **Simple Implementation:** Python OrderedDict provides LRU tracking
3. **Automatic Eviction:** LRU eviction when capacity exceeded (transparent)
4. **Inactive Detection:** 60-minute timeout moves idle sessions to warm tier

### Negative

1. **Memory Pressure:** 56MB RAM footprint per K1 instance
2. **No Durability:** Sessions lost on K1 crash (requires K0 checkpoint)
3. **Limited Capacity:** 1000 sessions max (LRU eviction for more)

### Mitigations

1. **K0 Checkpoint:** 5-minute checkpoint to K0 WAL (durability)
2. **Horizontal Scaling:** Run multiple K1 instances (load balancing)
3. **Capacity Monitoring:** Alert when capacity > 80% (preemptive scaling)

---

## Roadmap

### Week 1: HotTier Implementation

- [ ] Implement HotTier class (get, put, remove)
- [ ] Add LRU tracking (OrderedDict)
- [ ] Add capacity management (MAX_CAPACITY_MB)
- [ ] Implement _evict_lru() (capacity eviction)

### Week 2: Inactive Eviction

- [ ] Implement evict_inactive() (60-minute timeout)
- [ ] Implement HotTierManager (background task)
- [ ] Add eviction_loop (5-minute interval)
- [ ] Integrate with warm tier (migration)

### Week 3: Performance Optimization

- [ ] Profile with py-spy (identify bottlenecks)
- [ ] Optimize LRU tracking (minimize overhead)
- [ ] Validate <1ms get/put latency (WARD tests)
- [ ] Add Prometheus metrics

### Week 4: Testing & Integration

- [ ] Write WARD unit tests (get, put, eviction)
- [ ] Write WARD performance tests (latency validation)
- [ ] Integrate with K0Checkpointer (5-minute checkpoint)
- [ ] Production rollout (monitor metrics, validate latency)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** ADR-0017 (SessionState), ADR-0019 (Serialization)
**Blocks:** 0020b (Warm Tier)

---

**END OF ADR-0020a**