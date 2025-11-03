---
adr_number: 0022c
title: Backpressure Cascade (K0 Queue >80%)
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
- observability
- performance
- privacy
- reliability
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0006
- ADR-0022
- ADR-0022a
- ADR-0022b
- ADR-0022c
implementation_status: IN_PROGRESS
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- IETF (2015)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0006
  - ADR-0022
  - ADR-0022a
  - ADR-0022b
  - ADR-0022c
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


# ADR-0022c: Backpressure Cascade (K0 Queue >80%)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0022 (K0 Bridge Bounded Batching)](0022-k0-bridge-bounded-batching.md)
**Category:** Infrastructure (Layer 5) - K0 Bridge
**Related ADRs:**
- [ADR-0022a (Batching Algorithm)](0022a-batching-algorithm-10-50-messages-100ms.md)
- [ADR-0022b (HTTP/2 Multiplexing)](0022b-http2-multiplexing-connection-management.md)
- [ADR-0006 (Backpressure Cascade)](0006-backpressure-cascade.md)

---

## Context

### Problem Statement

K1 batches messages and sends them to K0 via HTTP/2. If K0 cannot keep up, the **K0 Write-Ahead Log (WAL)** queue depth grows. Without backpressure, K1 continues sending messages, leading to:

- **Queue Overflow:** K0 WAL queue exceeds capacity (e.g., 10,000 messages)
- **Out-of-Memory (OOM):** K0 memory exhausted (>2GB)
- **Message Loss:** K0 drops messages (data loss)
- **Cascading Failure:** K0 crashes, K1 blocked

**Backpressure Solution:**

Monitor K0 queue depth and trigger **backpressure cascade** when queue depth exceeds **80%**:

1. **NORMAL (<60%):** K1 batching enabled, normal operation
2. **WARNING (60-80%):** K1 continues batching, emit warning
3. **CRITICAL (>80%):** K1 stops batching, orchestrator rejects new turns, emit alert

**Key Challenges:**

1. **Queue Depth Monitoring:** Query K0 queue depth every 1s (observability)
2. **State Machine:** Deterministic transitions (NORMAL → WARNING → CRITICAL → NORMAL)
3. **Cascade Actions:** Stop batching, reject turns, notify orchestrator
4. **Recovery:** Resume batching when queue depth <60%
5. **Observability:** Emit metrics (queue depth, backpressure state, rejections)

### Current Landscape

**Industry Backpressure Patterns:**

1. **Go Channels (Buffered)**:
   - **Pattern:** Block sender when channel full
   - **Advantage:** Built-in backpressure, simple
   - **Disadvantage:** Go-specific, no HTTP-level backpressure

2. **Kafka Producer (linger.ms + batch.size)**:
   - **Pattern:** Buffer messages, emit backpressure when buffer full
   - **Advantage:** High throughput, configurable buffering
   - **Disadvantage:** Kafka-specific, complex config

3. **gRPC Flow Control (HTTP/2 WINDOW_UPDATE)**:
   - **Pattern:** HTTP/2 flow control frames
   - **Advantage:** Protocol-level backpressure
   - **Disadvantage:** HTTP/2-specific, not application-level

4. **AWS SQS (ReceiveMessageWaitTimeSeconds)**:
   - **Pattern:** Long polling, backpressure via message visibility timeout
   - **Advantage:** Cloud-native, scalable
   - **Disadvantage:** AWS-specific, eventual consistency

### K1 Requirements

**Backpressure Monitor Properties:**

1. **Queue Depth Monitoring:** Query K0 `/metrics` endpoint every 1s
2. **State Machine:** BackpressureState enum (NORMAL/WARNING/CRITICAL)
3. **Thresholds:**
   - WARNING: 60% queue depth (6000/10000 messages)
   - CRITICAL: 80% queue depth (8000/10000 messages)
   - RECOVERY: <60% queue depth (back to NORMAL)
4. **Cascade Actions:**
   - CRITICAL: Stop batching, reject turns, emit Prometheus alert
   - NORMAL: Resume batching, accept turns

**Performance Targets (P95):**

| Metric | Target | Rationale |
|--------|--------|-----------|
| Monitoring interval | 1s | Balance responsiveness vs overhead |
| State transition latency | <10ms | Fast reaction to queue depth changes |
| Rejection latency | <5ms | Immediate turn rejection when CRITICAL |
| Recovery latency | <100ms | Resume batching after queue depth drops |

---

## Decision

We will implement **Backpressure Cascade** as:

1. **BackpressureMonitor Class:** Python class monitoring K0 queue depth
2. **State Machine:** 3 states (NORMAL/WARNING/CRITICAL) with deterministic transitions
3. **Queue Depth Polling:** Query K0 `/metrics` endpoint every 1s
4. **Cascade Actions:** Stop batching (CRITICAL), resume batching (NORMAL)
5. **Orchestrator Integration:** Notify orchestrator to reject turns (CRITICAL)

### Backpressure State Machine

```
┌──────────────────────────────────────────────────────────────┐
│ BackpressureMonitor - Queue Depth Monitoring                 │
│                                                               │
│  State Machine:                                               │
│                                                               │
│    NORMAL (<60%)                                             │
│      ├─> queue_depth > 60% ──> WARNING (60-80%)             │
│      └─> Actions: None (batching enabled)                    │
│                                                               │
│    WARNING (60-80%)                                          │
│      ├─> queue_depth > 80% ──> CRITICAL (>80%)              │
│      ├─> queue_depth < 60% ──> NORMAL (<60%)                │
│      └─> Actions: Emit warning metric                        │
│                                                               │
│    CRITICAL (>80%)                                           │
│      ├─> queue_depth < 60% ──> NORMAL (<60%)                │
│      └─> Actions:                                            │
│          • Stop batching (BatchingEngine.stop())             │
│          • Notify orchestrator (reject new turns)            │
│          • Emit Prometheus alert                             │
│                                                               │
│  Monitoring:                                                  │
│    • Query K0 /metrics every 1s                              │
│    • Parse k0_wal_queue_depth_messages gauge                 │
│    • Emit k1_backpressure_state gauge                        │
└──────────────────────────────────────────────────────────────┘
           ↓ HTTP GET /metrics (every 1s)
┌──────────────────────────────────────────────────────────────┐
│ K0 Service (Prometheus /metrics endpoint)                    │
│  • k0_wal_queue_depth_messages: Current queue depth          │
│  • k0_wal_queue_capacity_messages: Max capacity (10,000)     │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation

### BackpressureMonitor Class

```python
# k1/k0_bridge/backpressure_monitor.py
"""Backpressure Monitor - K0 queue depth monitoring & cascade

Research:
- Backpressure: "Flow Control in Computer Networks" (Ramakrishnan & Jain, 1990)
- Queueing Theory: "Introduction to Queueing Systems" (Sidi, 2018)
- HTTP/2 Flow Control: "RFC 7540 Section 5.2 - Flow Control" (IETF, 2015)
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Optional

import httpx

from k1.infrastructure.metrics import (
    k1_backpressure_state,
    k1_backpressure_transitions_total,
    k1_turns_rejected_backpressure_total,
    k0_queue_depth_messages,
)

logger = logging.getLogger(__name__)


class BackpressureState(Enum):
    """Backpressure states"""
    NORMAL = "NORMAL"      # <60% queue depth
    WARNING = "WARNING"    # 60-80% queue depth
    CRITICAL = "CRITICAL"  # >80% queue depth


class BackpressureMonitor:
    """Monitor K0 queue depth and trigger backpressure cascade

    Responsibilities:
    - Query K0 /metrics every 1s
    - Track queue depth (current vs capacity)
    - Trigger backpressure cascade at 80%
    - Notify BatchingEngine and orchestrator

    State Transitions:
    - NORMAL (<60%) → WARNING (60-80%) → CRITICAL (>80%)
    - CRITICAL (>80%) → NORMAL (<60%) when queue drains

    Performance:
    - Monitoring interval: 1s
    - State transition latency: <10ms
    - Rejection latency: <5ms
    """

    K0_METRICS_URL = "https://k0-service:8443/metrics"
    POLL_INTERVAL_SEC = 1.0  # Query K0 every 1 second
    WARNING_THRESHOLD = 0.60  # 60% queue depth
    CRITICAL_THRESHOLD = 0.80  # 80% queue depth
    RECOVERY_THRESHOLD = 0.60  # Resume at <60%

    def __init__(
        self,
        k0_metrics_url: str = None,
        batching_engine=None,
        orchestrator=None,
    ):
        """Initialize backpressure monitor

        Args:
            k0_metrics_url: K0 Prometheus metrics URL
            batching_engine: BatchingEngine instance (for stop/resume)
            orchestrator: Orchestrator instance (for turn rejection)
        """
        self.k0_metrics_url = k0_metrics_url or self.K0_METRICS_URL
        self.batching_engine = batching_engine
        self.orchestrator = orchestrator

        # State machine
        self.state = BackpressureState.NORMAL
        self.queue_depth = 0
        self.queue_capacity = 10000  # Default capacity (overridden by K0)

        # HTTP client for metrics
        self.http_client = httpx.AsyncClient(timeout=5.0)

        # Background task
        self.monitor_task: asyncio.Task = None
        self.running = False

        logger.info(
            "[BackpressureMonitor] Initialized",
            k0_metrics_url=self.k0_metrics_url,
            warning_threshold=self.WARNING_THRESHOLD,
            critical_threshold=self.CRITICAL_THRESHOLD,
        )

    def start(self):
        """Start backpressure monitoring"""
        if self.monitor_task is not None:
            logger.warning("[BackpressureMonitor] Already running")
            return

        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info(
            "[BackpressureMonitor] Backpressure monitor started",
            interval_sec=self.POLL_INTERVAL_SEC,
        )

    async def stop(self):
        """Stop backpressure monitoring"""
        if self.monitor_task is None:
            return

        logger.info("[BackpressureMonitor] Stopping...")
        self.running = False
        self.monitor_task.cancel()

        try:
            await self.monitor_task
        except asyncio.CancelledError:
            pass

        await self.http_client.aclose()
        logger.info("[BackpressureMonitor] Stopped")

    async def _monitor_loop(self):
        """Background task: query K0 queue depth every 1s"""
        while self.running:
            try:
                # Wait for polling interval
                await asyncio.sleep(self.POLL_INTERVAL_SEC)

                # Query K0 metrics
                await self._query_k0_metrics()

                # Check thresholds and transition state
                await self._check_thresholds()

            except asyncio.CancelledError:
                logger.info("[BackpressureMonitor] Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(
                    "[BackpressureMonitor] Monitor loop error",
                    error=str(e),
                    exc_info=True,
                )

    async def _query_k0_metrics(self):
        """Query K0 /metrics endpoint for queue depth

        Parses Prometheus metrics:
        - k0_wal_queue_depth_messages: Current queue depth
        - k0_wal_queue_capacity_messages: Max capacity
        """
        try:
            response = await self.http_client.get(self.k0_metrics_url)
            if response.status_code != 200:
                logger.error(
                    "[BackpressureMonitor] K0 metrics query failed",
                    status_code=response.status_code,
                )
                return

            # Parse Prometheus metrics
            metrics_text = response.text
            self.queue_depth = self._parse_metric(
                metrics_text, "k0_wal_queue_depth_messages"
            )
            self.queue_capacity = self._parse_metric(
                metrics_text, "k0_wal_queue_capacity_messages"
            )

            # Emit metric
            k0_queue_depth_messages.set(self.queue_depth)

            logger.debug(
                "[BackpressureMonitor] K0 queue depth",
                queue_depth=self.queue_depth,
                queue_capacity=self.queue_capacity,
                utilization=round(self.queue_depth / self.queue_capacity, 2),
            )

        except Exception as e:
            logger.error(
                "[BackpressureMonitor] K0 metrics query error",
                error=str(e),
                exc_info=True,
            )

    def _parse_metric(self, metrics_text: str, metric_name: str) -> int:
        """Parse Prometheus metric from /metrics response

        Args:
            metrics_text: Prometheus metrics text
            metric_name: Metric name (e.g., "k0_wal_queue_depth_messages")

        Returns:
            Metric value (int)
        """
        for line in metrics_text.split("\n"):
            if line.startswith(metric_name):
                # Parse: k0_wal_queue_depth_messages 7500
                parts = line.split()
                if len(parts) >= 2:
                    return int(float(parts[1]))
        return 0

    async def _check_thresholds(self):
        """Check queue depth thresholds and transition state"""
        if self.queue_capacity == 0:
            # Avoid division by zero
            return

        utilization = self.queue_depth / self.queue_capacity
        old_state = self.state

        # State transitions
        if self.state == BackpressureState.NORMAL:
            if utilization > self.WARNING_THRESHOLD:
                # NORMAL → WARNING
                await self._transition_to(BackpressureState.WARNING)
        elif self.state == BackpressureState.WARNING:
            if utilization > self.CRITICAL_THRESHOLD:
                # WARNING → CRITICAL
                await self._transition_to(BackpressureState.CRITICAL)
            elif utilization < self.RECOVERY_THRESHOLD:
                # WARNING → NORMAL
                await self._transition_to(BackpressureState.NORMAL)
        elif self.state == BackpressureState.CRITICAL:
            if utilization < self.RECOVERY_THRESHOLD:
                # CRITICAL → NORMAL (direct recovery)
                await self._transition_to(BackpressureState.NORMAL)

        # Emit state metric
        k1_backpressure_state.set(self._state_to_value(self.state))

        # Log state change
        if old_state != self.state:
            logger.info(
                "[BackpressureMonitor] State transition",
                old_state=old_state.value,
                new_state=self.state.value,
                queue_depth=self.queue_depth,
                utilization=round(utilization, 2),
            )

    async def _transition_to(self, new_state: BackpressureState):
        """Transition to new backpressure state

        Args:
            new_state: Target state
        """
        old_state = self.state
        self.state = new_state

        # Emit metric
        k1_backpressure_transitions_total.labels(
            from_state=old_state.value,
            to_state=new_state.value,
        ).inc()

        # Execute cascade actions
        if new_state == BackpressureState.CRITICAL:
            await self._enter_critical()
        elif new_state == BackpressureState.NORMAL and old_state == BackpressureState.CRITICAL:
            await self._exit_critical()

    async def _enter_critical(self):
        """Enter CRITICAL state - trigger backpressure cascade"""
        logger.warning(
            "[BackpressureMonitor] ENTERING CRITICAL STATE",
            queue_depth=self.queue_depth,
            queue_capacity=self.queue_capacity,
            utilization=round(self.queue_depth / self.queue_capacity, 2),
        )

        # Action 1: Stop batching
        if self.batching_engine is not None:
            logger.warning("[BackpressureMonitor] Stopping batching engine")
            self.batching_engine.stop_batching()

        # Action 2: Notify orchestrator (reject new turns)
        if self.orchestrator is not None:
            logger.warning("[BackpressureMonitor] Notifying orchestrator to reject turns")
            self.orchestrator.set_backpressure(True)

        # Emit alert metric (Prometheus alert rule will trigger)
        logger.critical(
            "[BackpressureMonitor] BACKPRESSURE ALERT - K0 queue >80%",
            queue_depth=self.queue_depth,
            queue_capacity=self.queue_capacity,
        )

    async def _exit_critical(self):
        """Exit CRITICAL state - recover from backpressure"""
        logger.info(
            "[BackpressureMonitor] EXITING CRITICAL STATE",
            queue_depth=self.queue_depth,
            queue_capacity=self.queue_capacity,
            utilization=round(self.queue_depth / self.queue_capacity, 2),
        )

        # Action 1: Resume batching
        if self.batching_engine is not None:
            logger.info("[BackpressureMonitor] Resuming batching engine")
            self.batching_engine.resume_batching()

        # Action 2: Notify orchestrator (accept turns)
        if self.orchestrator is not None:
            logger.info("[BackpressureMonitor] Notifying orchestrator to accept turns")
            self.orchestrator.set_backpressure(False)

    def get_state(self) -> BackpressureState:
        """Get current backpressure state

        Returns:
            Current BackpressureState
        """
        return self.state

    def get_queue_depth(self) -> int:
        """Get current K0 queue depth

        Returns:
            Queue depth (messages)
        """
        return self.queue_depth

    def _state_to_value(self, state: BackpressureState) -> int:
        """Convert BackpressureState to numeric value for metrics

        Args:
            state: BackpressureState

        Returns:
            Numeric value (0=NORMAL, 1=WARNING, 2=CRITICAL)
        """
        return {
            BackpressureState.NORMAL: 0,
            BackpressureState.WARNING: 1,
            BackpressureState.CRITICAL: 2,
        }[state]
```

### Orchestrator Integration

```python
# k1/orchestrator/orchestrator.py (snippet)
class Orchestrator:
    """Orchestrator - 3-phase coordination"""

    def __init__(self):
        self.backpressure_enabled = False

    def set_backpressure(self, enabled: bool):
        """Enable/disable backpressure (reject turns)

        Args:
            enabled: True to reject turns, False to accept
        """
        self.backpressure_enabled = enabled
        logger.info(
            "[Orchestrator] Backpressure",
            enabled=enabled,
        )

    async def handle_turn(self, turn: Turn):
        """Handle incoming turn (reject if backpressure)

        Args:
            turn: User turn

        Returns:
            Turn result or rejection
        """
        if self.backpressure_enabled:
            logger.warning(
                "[Orchestrator] Turn rejected due to backpressure",
                turn_id=turn.turn_id,
            )

            # Emit metric
            from k1.infrastructure.metrics import k1_turns_rejected_backpressure_total
            k1_turns_rejected_backpressure_total.inc()

            # Return error response
            return TurnRejection(
                turn_id=turn.turn_id,
                reason="BACKPRESSURE",
                message="K0 queue overloaded, try again later",
            )

        # Normal turn processing
        return await self._process_turn(turn)
```

### BatchingEngine Integration

```python
# k1/k0_bridge/batching_engine.py (snippet)
class BatchingEngine:
    """Batching Engine - Bounded batching"""

    def __init__(self):
        self.batching_enabled = True

    def stop_batching(self):
        """Stop batching (drain existing batches)"""
        logger.warning("[BatchingEngine] Batching stopped (backpressure)")
        self.batching_enabled = False

    def resume_batching(self):
        """Resume batching (accept new messages)"""
        logger.info("[BatchingEngine] Batching resumed (backpressure cleared)")
        self.batching_enabled = True

    async def enqueue(self, session_id: str, message: K0Message):
        """Enqueue message for batching

        Args:
            session_id: Session ID
            message: K0Message

        Raises:
            BackpressureError: If batching disabled
        """
        if not self.batching_enabled:
            raise BackpressureError("Batching disabled due to backpressure")

        # Normal enqueue logic
        self.session_queues[session_id].append(message)
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/k0_bridge/test_backpressure_monitor.py
from ward import test, fixture
import asyncio

from k1.k0_bridge.backpressure_monitor import BackpressureMonitor, BackpressureState
from k1.k0_bridge.batching_engine import BatchingEngine
from k1.orchestrator.orchestrator import Orchestrator

@fixture
async def backpressure_monitor():
    """Fixture for BackpressureMonitor"""
    batching_engine = BatchingEngine()
    orchestrator = Orchestrator()
    monitor = BackpressureMonitor(
        k0_metrics_url="http://localhost:9090/metrics",
        batching_engine=batching_engine,
        orchestrator=orchestrator,
    )
    yield monitor
    await monitor.stop()

@test("BackpressureMonitor transitions NORMAL → WARNING")
async def _(monitor=backpressure_monitor):
    # Mock K0 queue depth at 65%
    monitor.queue_depth = 6500
    monitor.queue_capacity = 10000

    await monitor._check_thresholds()

    assert monitor.get_state() == BackpressureState.WARNING

@test("BackpressureMonitor transitions WARNING → CRITICAL")
async def _(monitor=backpressure_monitor):
    # Mock K0 queue depth at 85%
    monitor.state = BackpressureState.WARNING
    monitor.queue_depth = 8500
    monitor.queue_capacity = 10000

    await monitor._check_thresholds()

    assert monitor.get_state() == BackpressureState.CRITICAL

@test("BackpressureMonitor stops batching in CRITICAL")
async def _(monitor=backpressure_monitor):
    # Mock K0 queue depth at 85%
    monitor.queue_depth = 8500
    monitor.queue_capacity = 10000

    await monitor._transition_to(BackpressureState.CRITICAL)

    # Verify batching stopped
    assert monitor.batching_engine.batching_enabled is False

@test("BackpressureMonitor recovers from CRITICAL to NORMAL")
async def _(monitor=backpressure_monitor):
    # Start in CRITICAL
    monitor.state = BackpressureState.CRITICAL
    monitor.batching_engine.batching_enabled = False

    # Queue drains to 50%
    monitor.queue_depth = 5000
    monitor.queue_capacity = 10000

    await monitor._check_thresholds()

    # Verify recovery
    assert monitor.get_state() == BackpressureState.NORMAL
    assert monitor.batching_engine.batching_enabled is True
```

---

## Performance Benchmarks

### State Transition Latency

| Transition | Latency P95 | Action |
|------------|-------------|--------|
| NORMAL → WARNING | <5ms | Emit metric |
| WARNING → CRITICAL | <10ms | Stop batching, notify orchestrator |
| CRITICAL → NORMAL | <100ms | Resume batching, accept turns |

### Monitoring Overhead

| Metric | Value | Rationale |
|--------|-------|-----------|
| Polling interval | 1s | Balance responsiveness vs overhead |
| HTTP GET latency | <5ms | K0 on same network |
| Metric parsing | <1ms | Simple regex parsing |
| CPU overhead | <0.1% | Minimal impact |

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Backpressure)
from prometheus_client import Counter, Gauge

# Backpressure state
k1_backpressure_state = Gauge(
    'k1_backpressure_state',
    'Current backpressure state (0=NORMAL, 1=WARNING, 2=CRITICAL)'
)

# State transitions
k1_backpressure_transitions_total = Counter(
    'k1_backpressure_transitions_total',
    'Total backpressure state transitions',
    labelnames=['from_state', 'to_state']
)

# Turn rejections
k1_turns_rejected_backpressure_total = Counter(
    'k1_turns_rejected_backpressure_total',
    'Total turns rejected due to backpressure'
)

# K0 queue depth
k0_queue_depth_messages = Gauge(
    'k0_queue_depth_messages',
    'K0 WAL queue depth in messages'
)
```

### Prometheus Alert Rules

```yaml
# prometheus/alerts/backpressure.yml
groups:
  - name: k1_backpressure
    interval: 10s
    rules:
      - alert: K1BackpressureCritical
        expr: k1_backpressure_state == 2
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "K1 in CRITICAL backpressure state"
          description: "K0 queue depth >80%, batching stopped, turns rejected"

      - alert: K1BackpressureWarning
        expr: k1_backpressure_state == 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "K1 in WARNING backpressure state"
          description: "K0 queue depth 60-80%, monitor closely"

      - alert: K1TurnsRejected
        expr: rate(k1_turns_rejected_backpressure_total[5m]) > 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "K1 rejecting turns due to backpressure"
          description: "{{ $value }} turns/sec rejected"
```

---

## Research Citations

1. **Ramakrishnan, K. K., & Jain, R. (1990).** *"A Binary Feedback Scheme for Congestion Avoidance in Computer Networks."* ACM SIGCOMM. — Backpressure theory.

2. **Sidi, M. (2018).** *"Introduction to Queueing Systems."* Cambridge University Press. — Queueing theory foundations.

3. **IETF (2015).** *"RFC 7540 Section 5.2 - Flow Control."* IETF. — HTTP/2 flow control.

---

## Consequences

### Positive

1. **Prevents Overload:** K0 queue cannot exceed 80% (prevents OOM)
2. **Fast Reaction:** <10ms state transition latency
3. **Automatic Recovery:** Resume at <60% (no manual intervention)
4. **Observability:** Prometheus metrics + alerts for visibility

### Negative

1. **Turn Rejection:** Users experience "try again later" errors
2. **Complexity:** State machine adds orchestrator integration overhead
3. **False Positives:** Temporary spikes may trigger backpressure

### Mitigations

1. **User Feedback:** Return 503 Service Unavailable with retry-after header
2. **Monitoring:** Track rejection rate (alert if >1% of turns)
3. **Tuning:** Adjust thresholds based on K0 capacity and load patterns

---

## Roadmap

### Week 1: BackpressureMonitor Setup

- [ ] Implement BackpressureMonitor class
- [ ] Add K0 /metrics polling (every 1s)
- [ ] Implement state machine (NORMAL/WARNING/CRITICAL)
- [ ] Add threshold checking logic (60%/80%)

### Week 2: Cascade Actions

- [ ] Implement _enter_critical() (stop batching, notify orchestrator)
- [ ] Implement _exit_critical() (resume batching, accept turns)
- [ ] Integrate with BatchingEngine (stop/resume methods)
- [ ] Integrate with Orchestrator (set_backpressure method)

### Week 3: Observability & Alerts

- [ ] Add Prometheus metrics (state, transitions, rejections, queue depth)
- [ ] Write Prometheus alert rules (CRITICAL, WARNING, turns rejected)
- [ ] Add structured logging (state transitions, actions)
- [ ] Create Grafana dashboard (backpressure state, queue depth, rejections)

### Week 4: Testing & Validation

- [ ] Write WARD unit tests (state transitions, cascade actions)
- [ ] Write WARD integration tests (end-to-end backpressure flow)
- [ ] Simulate K0 overload (inject high queue depth)
- [ ] Production rollout (monitor backpressure metrics, validate recovery)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** 0022a (Batching Algorithm), 0022b (HTTP/2 Multiplexing)
**Blocks:** None (final sub-ADR for ADR-0022)

---

**END OF ADR-0022c**