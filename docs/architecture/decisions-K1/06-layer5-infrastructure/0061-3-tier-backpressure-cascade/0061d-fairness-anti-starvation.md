---
adr_number: 0061d
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l5_infrastructure.priority_scheduler
- k1.l4_runtime.fairness_controller
- k1.l5_infrastructure.aging_manager
authors:
- K1 Architecture Team
concerns:
- architecture
- observability
- performance
- privacy
- reliability
- scalability
- security
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 4 (Performance Optimization)
implementation_status: COMPLETED
related_adrs:
- ADR-0061
related_contracts:
- k0/contracts/api/rest/idempotency/24h_retention.yml
- k0/contracts/asyncapi.events.yaml
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
research_citations:
- Fair Queuing (Demers et al., 1989)
- Starvation-Free Scheduling (Coffman et al., 1971)
- Weighted Fair Queuing (Bennett & Zhang, 1996)
status: PROPOSED
title: Fairness & Anti-Starvation for Priority Scheduling
---

# ADR-0061d: Fairness & Anti-Starvation for Priority Scheduling

**Status:** Proposed
**Date:** 2025-10-15
**Parent:** [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md)
**Tier:** 1

## Context

Priority-based backpressure systems face a fundamental challenge: **high-priority traffic can starve low-priority traffic indefinitely**. The challenge: **how do we ensure CRITICAL and REALTIME operations get preferential treatment while preventing BACKGROUND work from never executing?**

**Problem Statement:**

Traditional priority scheduling suffers from starvation:
- ❌ **Strict priority**: High-priority work always preempts low-priority (BACKGROUND never runs)
- ❌ **No aging**: Waiting time doesn't increase priority (old BACKGROUND requests stay low forever)
- ❌ **Priority inversion**: Low-priority work holds resources needed by high-priority (deadlock risk)
- ❌ **No fairness**: High-priority senders monopolize queues (other senders starved)

**K1 Requirement:**

- **Fairness**: All priority levels eventually execute (no indefinite starvation)
- **Responsiveness**: High-priority work still gets <150ms TTFT (aging doesn't slow CRITICAL)
- **Predictability**: BACKGROUND work completes within bounded time (not "eventually, maybe")
- **Priority preservation**: CRITICAL always preempts BACKGROUND (safety over fairness)

**Industry Precedent:**

- **Linux CFS (Completely Fair Scheduler)**: Virtual runtime tracks fairness, low-priority catches up
- **WFQ (Weighted Fair Queueing)**: Each flow gets bandwidth proportional to weight
- **BPF (Berkeley Packet Filter)**: Aging increases priority of waiting packets
- **RT-Linux**: Priority inheritance prevents priority inversion

---

## Decision

We adopt **Weighted Fair Queueing (WFQ)** with aging policies and priority inheritance to balance fairness with responsiveness.

### **Core Principles**

**1. WFQ for Fairness (Weighted by Priority)**
- Each priority level gets "virtual time" proportional to weight
- CRITICAL: 50% bandwidth, REALTIME: 30%, INTERACTIVE: 15%, BACKGROUND: 5%
- Ensures BACKGROUND gets ≥5% CPU even under CRITICAL load

**2. Aging for Anti-Starvation**
- Waiting time increases effective priority (1 level per 10s)
- BACKGROUND waiting 10s → INTERACTIVE priority
- BACKGROUND waiting 20s → REALTIME priority
- **Never ages to CRITICAL** (safety preserved)

**3. Priority Inheritance for Deadlock Prevention**
- If CRITICAL waits on resource held by BACKGROUND, BACKGROUND inherits CRITICAL priority temporarily
- Prevents priority inversion deadlock
- Applies to: locks, semaphores, agent mailbox replies

**4. Per-Sender Fairness (Round-Robin within Priority)**
- Within same priority, senders alternate (round-robin)
- Prevents single sender monopolizing queue
- Example: 3 senders at INTERACTIVE priority each get 33% bandwidth

**5. Starvation Detection & Alerts**
- Monitor waiting time per priority level
- Alert if BACKGROUND waits >60s (starvation threshold)
- Emit metrics for SLO tracking

**6. Graceful Degradation under Overload**
- Under sustained overload (>10s), shed BACKGROUND first
- If overload continues, shed INTERACTIVE
- CRITICAL and REALTIME never shed (safety preserved)

---

## Weighted Fair Queueing (WFQ)

### **Algorithm Overview**

WFQ assigns each priority level a **weight** and schedules operations to maintain proportional virtual time.

**Weights (Bandwidth Allocation):**

| Priority | Weight | Bandwidth % | Rationale |
|----------|--------|-------------|-----------|
| **CRITICAL** | 50 | 50% | Safety and compliance operations |
| **REALTIME** | 30 | 30% | User-facing voice, streaming |
| **INTERACTIVE** | 15 | 15% | Tool calls, model inference |
| **BACKGROUND** | 5 | 5% | Analytics, metrics, logs |

**Virtual Time Calculation:**

Each operation has a **virtual finish time** `F_i`:

```
F_i = max(F_prev, V_now) + (size_i / weight_i)
```

Where:
- `F_prev` = Virtual finish time of previous operation from same sender
- `V_now` = Current virtual time (global clock)
- `size_i` = Work size (e.g., 1 for single operation)
- `weight_i` = Priority weight (50, 30, 15, 5)

**Scheduling Rule:** Select operation with smallest `F_i` (earliest virtual finish time).

**Example:**

```
Time 0:
- Op A (CRITICAL, weight=50): F_A = 0 + (1/50) = 0.02
- Op B (REALTIME, weight=30): F_B = 0 + (1/30) = 0.033
- Op C (BACKGROUND, weight=5): F_C = 0 + (1/5) = 0.20

Schedule: A (F_A = 0.02 < F_B < F_C)

Time 1 (after A completes):
V_now = 0.02 (updated to F_A)
- Op B (REALTIME): F_B = 0.033 (unchanged)
- Op C (BACKGROUND): F_C = 0.20 (unchanged)
- Op D (CRITICAL): F_D = 0.02 + (1/50) = 0.04

Schedule: B (F_B = 0.033 < F_D < F_C)

Time 2 (after B completes):
V_now = 0.033
- Op C (BACKGROUND): F_C = 0.20
- Op D (CRITICAL): F_D = 0.04

Schedule: D (F_D = 0.04 < F_C)

Time 3 (after D completes):
V_now = 0.04
- Op C (BACKGROUND): F_C = 0.20

Schedule: C (only remaining)
```

**Result:** BACKGROUND eventually executes (no starvation) despite CRITICAL/REALTIME traffic.

---

### **WFQ Implementation**

```python
# k1/infrastructure/scheduling/wfq_scheduler.py
from dataclasses import dataclass
from heapq import heappush, heappop
from collections import defaultdict

@dataclass
class ScheduledOperation:
    """Operation with virtual finish time"""
    operation: Operation
    virtual_finish_time: float
    sender_id: str

    def __lt__(self, other):
        """Comparison for heap (min-heap by virtual finish time)"""
        return self.virtual_finish_time < other.virtual_finish_time

class WFQScheduler:
    """Weighted Fair Queueing scheduler"""

    # Priority weights (bandwidth allocation)
    WEIGHTS = {
        Priority.CRITICAL: 50,
        Priority.REALTIME: 30,
        Priority.INTERACTIVE: 15,
        Priority.BACKGROUND: 5
    }

    def __init__(self):
        self.ready_queue = []  # Min-heap of ScheduledOperation
        self.virtual_time = 0.0  # Global virtual clock
        self.sender_last_finish = defaultdict(float)  # Per-sender virtual finish time
        self.metrics = PrometheusMetrics()

    async def enqueue(self, operation: Operation):
        """Add operation to ready queue with virtual finish time"""

        # 1. Get weight for priority
        weight = self.WEIGHTS[operation.priority]

        # 2. Calculate virtual finish time
        sender_id = operation.sender_id
        prev_finish = self.sender_last_finish[sender_id]

        virtual_finish_time = max(prev_finish, self.virtual_time) + (1.0 / weight)

        # 3. Update sender's last finish time
        self.sender_last_finish[sender_id] = virtual_finish_time

        # 4. Add to ready queue (min-heap)
        scheduled_op = ScheduledOperation(
            operation=operation,
            virtual_finish_time=virtual_finish_time,
            sender_id=sender_id
        )
        heappush(self.ready_queue, scheduled_op)

        # 5. Emit metrics
        self.metrics.scheduler_queue_depth.labels(
            priority=operation.priority.name
        ).inc()

        logger.debug(
            "operation_enqueued",
            operation_id=operation.id,
            priority=operation.priority.name,
            virtual_finish_time=virtual_finish_time
        )

    async def dequeue(self) -> Operation | None:
        """Remove and return next operation (earliest virtual finish time)"""

        if not self.ready_queue:
            return None

        # 1. Pop operation with smallest virtual finish time
        scheduled_op = heappop(self.ready_queue)

        # 2. Update virtual time (advance global clock)
        self.virtual_time = scheduled_op.virtual_finish_time

        # 3. Emit metrics
        self.metrics.scheduler_queue_depth.labels(
            priority=scheduled_op.operation.priority.name
        ).dec()

        logger.debug(
            "operation_dequeued",
            operation_id=scheduled_op.operation.id,
            priority=scheduled_op.operation.priority.name,
            virtual_time=self.virtual_time
        )

        return scheduled_op.operation

    def get_queue_depth_by_priority(self, priority: Priority) -> int:
        """Get current queue depth for specific priority"""
        return sum(1 for sop in self.ready_queue if sop.operation.priority == priority)
```

---

## Aging Policy (Anti-Starvation)

### **Aging Rules**

**Purpose:** Increase priority of waiting operations to prevent indefinite starvation.

**Aging Thresholds:**

| Current Priority | Wait Time Threshold | New Priority | Notes |
|------------------|---------------------|--------------|-------|
| BACKGROUND | 10s | INTERACTIVE | First aging step |
| BACKGROUND | 20s | REALTIME | Second aging step |
| INTERACTIVE | 15s | REALTIME | Single aging step |
| REALTIME | N/A | REALTIME | No aging (already high) |
| CRITICAL | N/A | CRITICAL | No aging (highest priority) |

**Never Age to CRITICAL:** Safety-critical operations must be explicitly marked CRITICAL (cannot age into critical path).

---

### **Aging Implementation**

```python
# k1/infrastructure/scheduling/aging_policy.py
class AgingPolicy:
    """Apply aging to prevent starvation"""

    # Aging thresholds (seconds)
    AGING_THRESHOLDS = {
        Priority.BACKGROUND: [(10, Priority.INTERACTIVE), (20, Priority.REALTIME)],
        Priority.INTERACTIVE: [(15, Priority.REALTIME)]
    }

    def __init__(self, scheduler: WFQScheduler):
        self.scheduler = scheduler
        self.enqueue_times = {}  # operation_id → enqueue timestamp
        self.metrics = PrometheusMetrics()

    async def check_aging(self):
        """Periodically check for operations needing aging (every 1s)"""

        while True:
            await asyncio.sleep(1.0)  # 1s poll

            now_ms = time.time_ns() // 1_000_000

            # Check all operations in ready queue
            for scheduled_op in self.scheduler.ready_queue:
                operation = scheduled_op.operation
                enqueue_time_ms = self.enqueue_times.get(operation.id)

                if enqueue_time_ms is None:
                    continue

                wait_time_s = (now_ms - enqueue_time_ms) / 1000.0

                # Check if operation needs aging
                new_priority = self._check_aging_threshold(operation.priority, wait_time_s)

                if new_priority != operation.priority:
                    # Age operation (increase priority)
                    await self._age_operation(operation, new_priority, wait_time_s)

    def _check_aging_threshold(self, current_priority: Priority, wait_time_s: float) -> Priority:
        """Check if operation crossed aging threshold"""

        thresholds = self.AGING_THRESHOLDS.get(current_priority, [])

        for threshold_s, new_priority in reversed(thresholds):  # Check highest threshold first
            if wait_time_s >= threshold_s:
                return new_priority

        return current_priority  # No aging

    async def _age_operation(self, operation: Operation, new_priority: Priority, wait_time_s: float):
        """Age operation to new priority"""

        old_priority = operation.priority

        # 1. Update operation priority
        operation.priority = new_priority

        # 2. Re-enqueue with new priority (WFQ recalculates virtual finish time)
        self.scheduler.ready_queue.remove(operation)  # Remove old entry
        await self.scheduler.enqueue(operation)       # Re-add with new priority

        # 3. Log aging event
        logger.info(
            "operation_aged",
            operation_id=operation.id,
            old_priority=old_priority.name,
            new_priority=new_priority.name,
            wait_time_s=wait_time_s
        )

        # 4. Emit metrics
        self.metrics.scheduler_aging_total.labels(
            from_priority=old_priority.name,
            to_priority=new_priority.name
        ).inc()

        self.metrics.scheduler_wait_time_seconds.labels(
            priority=old_priority.name
        ).observe(wait_time_s)
```

---

## Priority Inheritance (Deadlock Prevention)

### **Priority Inversion Problem**

**Scenario:**
1. Agent A (BACKGROUND) acquires lock on resource R
2. Agent B (CRITICAL) waits for lock on resource R
3. Agent C (INTERACTIVE) preempts Agent A
4. **Result:** CRITICAL blocked by INTERACTIVE (priority inversion)

**Solution: Priority Inheritance**
- When CRITICAL waits on BACKGROUND's lock, BACKGROUND inherits CRITICAL priority temporarily
- BACKGROUND executes with CRITICAL priority until lock released
- Prevents INTERACTIVE from preempting BACKGROUND

---

### **Priority Inheritance Implementation**

```python
# k1/infrastructure/scheduling/priority_inheritance.py
class PriorityInheritanceLock:
    """Lock with priority inheritance"""

    def __init__(self, lock_id: str):
        self.lock_id = lock_id
        self.holder = None  # Current lock holder (Operation)
        self.waiters = []   # List of waiting operations (FIFO)
        self.original_priority = None  # Holder's original priority
        self._lock = asyncio.Lock()

    async def acquire(self, operation: Operation):
        """Acquire lock with priority inheritance"""

        async with self._lock:
            # 1. Check if lock available
            if self.holder is None:
                # Lock available, grant immediately
                self.holder = operation
                self.original_priority = operation.priority
                logger.debug("lock_acquired", lock_id=self.lock_id, holder=operation.id)
                return

            # 2. Lock held, add to waiters
            self.waiters.append(operation)

            # 3. Check for priority inheritance
            if operation.priority.value < self.holder.priority.value:
                # Waiter has higher priority (lower value) than holder
                # Apply priority inheritance
                old_holder_priority = self.holder.priority
                self.holder.priority = operation.priority

                logger.info(
                    "priority_inherited",
                    lock_id=self.lock_id,
                    holder=self.holder.id,
                    old_priority=old_holder_priority.name,
                    new_priority=operation.priority.name,
                    waiter=operation.id
                )

                # Emit metrics
                self.metrics.priority_inheritance_total.labels(
                    from_priority=old_holder_priority.name,
                    to_priority=operation.priority.name
                ).inc()

        # 4. Wait for lock (blocking)
        await self._wait_for_lock(operation)

    async def release(self, operation: Operation):
        """Release lock and restore original priority"""

        async with self._lock:
            # 1. Verify caller holds lock
            if self.holder != operation:
                raise ValueError(f"Operation {operation.id} does not hold lock {self.lock_id}")

            # 2. Restore original priority (undo inheritance)
            if self.original_priority != operation.priority:
                logger.info(
                    "priority_restored",
                    lock_id=self.lock_id,
                    holder=operation.id,
                    inherited_priority=operation.priority.name,
                    original_priority=self.original_priority.name
                )
                operation.priority = self.original_priority

            # 3. Grant lock to highest-priority waiter
            if self.waiters:
                next_holder = min(self.waiters, key=lambda op: op.priority.value)
                self.waiters.remove(next_holder)
                self.holder = next_holder
                self.original_priority = next_holder.priority
                logger.debug("lock_granted", lock_id=self.lock_id, new_holder=next_holder.id)
            else:
                self.holder = None
                self.original_priority = None
                logger.debug("lock_released", lock_id=self.lock_id)
```

---

## Starvation Detection & Alerts

### **Starvation Threshold**

**Definition:** Operation starves if wait time exceeds threshold for its priority:

| Priority | Starvation Threshold | Action |
|----------|---------------------|--------|
| **CRITICAL** | 500ms | Page immediately (safety at risk) |
| **REALTIME** | 5s | Alert (UX degradation) |
| **INTERACTIVE** | 30s | Warning (poor UX) |
| **BACKGROUND** | 60s | Info (monitor, expected under load) |

---

### **Starvation Detection Implementation**

```python
# k1/infrastructure/scheduling/starvation_detector.py
class StarvationDetector:
    """Detect and alert on operation starvation"""

    STARVATION_THRESHOLDS = {
        Priority.CRITICAL: 0.5,      # 500ms
        Priority.REALTIME: 5.0,      # 5s
        Priority.INTERACTIVE: 30.0,  # 30s
        Priority.BACKGROUND: 60.0    # 60s
    }

    def __init__(self, scheduler: WFQScheduler):
        self.scheduler = scheduler
        self.enqueue_times = {}  # operation_id → enqueue timestamp
        self.metrics = PrometheusMetrics()

    async def check_starvation(self):
        """Periodically check for starved operations (every 1s)"""

        while True:
            await asyncio.sleep(1.0)  # 1s poll

            now_ms = time.time_ns() // 1_000_000

            for scheduled_op in self.scheduler.ready_queue:
                operation = scheduled_op.operation
                enqueue_time_ms = self.enqueue_times.get(operation.id)

                if enqueue_time_ms is None:
                    continue

                wait_time_s = (now_ms - enqueue_time_ms) / 1000.0
                threshold_s = self.STARVATION_THRESHOLDS[operation.priority]

                if wait_time_s >= threshold_s:
                    # Starvation detected
                    await self._handle_starvation(operation, wait_time_s)

    async def _handle_starvation(self, operation: Operation, wait_time_s: float):
        """Handle starved operation"""

        # 1. Determine severity
        if operation.priority == Priority.CRITICAL:
            severity = "critical"
            logger.critical("starvation_critical", operation_id=operation.id, wait_time_s=wait_time_s)
        elif operation.priority == Priority.REALTIME:
            severity = "warning"
            logger.warning("starvation_realtime", operation_id=operation.id, wait_time_s=wait_time_s)
        else:
            severity = "info"
            logger.info("starvation_detected", operation_id=operation.id, priority=operation.priority.name, wait_time_s=wait_time_s)

        # 2. Emit metrics
        self.metrics.scheduler_starvation_total.labels(
            priority=operation.priority.name,
            severity=severity
        ).inc()

        self.metrics.scheduler_starvation_duration_seconds.labels(
            priority=operation.priority.name
        ).observe(wait_time_s)

        # 3. Trigger alert (if critical/warning)
        if severity in ["critical", "warning"]:
            await self.alertmanager.send_alert(
                alert_name=f"OperationStarvation_{operation.priority.name}",
                severity=severity,
                description=f"Operation {operation.id} starved for {wait_time_s:.1f}s",
                runbook="https://runbooks.k1.dev/STARVATION-001"
            )
```

---

## Per-Sender Fairness (Round-Robin within Priority)

### **Problem**

Without per-sender fairness, single sender can monopolize queue:

**Example:**
- Sender A: 100 INTERACTIVE operations enqueued
- Sender B: 1 INTERACTIVE operation enqueued
- **Result (without fairness):** A's 100 ops execute before B's 1 op (monopolization)

### **Solution: Round-Robin within Priority**

**Rule:** Within same priority, alternate between senders (round-robin).

**Example (with fairness):**
- Sender A: 100 INTERACTIVE ops
- Sender B: 1 INTERACTIVE op
- **Schedule:** A, B, A, A, A, ... (B gets turn after 1st A operation)

---

### **Per-Sender Fairness Implementation**

```python
# k1/infrastructure/scheduling/fair_queue.py
class FairQueue:
    """Per-sender fairness within priority level"""

    def __init__(self, priority: Priority):
        self.priority = priority
        self.sender_queues = defaultdict(deque)  # sender_id → deque of operations
        self.sender_order = []  # Round-robin order of senders
        self.current_sender_idx = 0

    def enqueue(self, operation: Operation):
        """Add operation to sender's queue"""
        sender_id = operation.sender_id

        # Add to sender's queue
        self.sender_queues[sender_id].append(operation)

        # Add sender to round-robin order (if new)
        if sender_id not in self.sender_order:
            self.sender_order.append(sender_id)

    def dequeue(self) -> Operation | None:
        """Remove next operation (round-robin across senders)"""

        if not self.sender_order:
            return None

        # Try up to N senders (full round-robin cycle)
        for _ in range(len(self.sender_order)):
            sender_id = self.sender_order[self.current_sender_idx]
            sender_queue = self.sender_queues[sender_id]

            if sender_queue:
                # Sender has operations, dequeue
                operation = sender_queue.popleft()

                # Advance to next sender (round-robin)
                self.current_sender_idx = (self.current_sender_idx + 1) % len(self.sender_order)

                return operation
            else:
                # Sender queue empty, remove from round-robin
                self.sender_order.remove(sender_id)
                del self.sender_queues[sender_id]

                # Adjust index (account for removed sender)
                if self.current_sender_idx >= len(self.sender_order) and self.sender_order:
                    self.current_sender_idx = 0

        return None  # No operations available
```

---

## Consequences

### **Positive**

✅ **Fairness**: WFQ ensures all priority levels get bandwidth (BACKGROUND ≥5%)
✅ **Anti-starvation**: Aging prevents indefinite waiting (max 60s for BACKGROUND)
✅ **Deadlock prevention**: Priority inheritance prevents priority inversion
✅ **Per-sender fairness**: Round-robin prevents single sender monopolization

### **Negative**

⚠️ **Complexity**: WFQ + aging + priority inheritance requires careful implementation
⚠️ **Overhead**: Virtual time calculations add <1ms per enqueue/dequeue
⚠️ **Tuning**: Weights (50/30/15/5) and aging thresholds (10s/20s) may need adjustment

---

## References

- [ADR-0061: 3-Tier Backpressure Cascade](0061-3-tier-backpressure-cascade.md) — Parent ADR
- Demers, A. et al. (1989): "Analysis and Simulation of a Fair Queueing Algorithm" (WFQ)
- Linux CFS: https://www.kernel.org/doc/Documentation/scheduler/sched-design-CFS.txt
- Sha, L. et al. (1990): "Priority Inheritance Protocols: An Approach to Real-Time Synchronization"
- RFC 2474: Definition of the Differentiated Services Field (DiffServ)

---

**Status:** Proposed
**Implementation:** Phase 1 (Week 1) - WFQ scheduler core + aging policy