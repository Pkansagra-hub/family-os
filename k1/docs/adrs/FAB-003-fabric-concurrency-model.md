---
adr_id: FAB-003
title: "Fabric Concurrency Model"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-001"
  - "FAB-009"
  - "FAB-006"
related_events:
  - "k1.fabric.request.queued.v1"
  - "k1.fabric.request.dispatched.v1"
related_contracts: []
related_ports:
  - "IFabricDispatcher"
implements_issue: "1.1.9"
superseded_by: ""
tags:
  - concurrency
  - async
  - scheduling
  - actor-model
---

# FAB-003: Fabric Concurrency Model

## Context

### Problem Statement

The architecture skeleton defines FABRIC_MAILBOX with WFQ REALTIME priority, suggesting a mailbox-based actor model for the Fabric. However, Fabric could also operate as a purely synchronous per-request pipeline. This decision determines whether Epic 4.4 (FabricMailbox) is needed or bypassed.

### Current Situation

- k1_cognitive_architecture_skeleton.mmd shows FABRIC_MAILBOX
- ADR-0028 establishes WFQ scheduling with 4 priority classes (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
- MPSC Mailbox priority assignment exists (WFQ_PRIORITY.INTERACTIVE default)
- No implementation exists for Fabric concurrency
- FAB-009 decided: Retrieval + Resolution are synchronous; only Agent Execution goes through WFQ scheduler

### Constraints

- Must support concurrent capability requests from multiple callers
- Must integrate with WFQ scheduling for Agent Execution (FAB-009)
- Must not block on single slow provider
- Resource isolation required between capability requests
- Fabric is stateless per-request (FAB-005 Invariant FAB-00)

### Requirements

- Handle multiple simultaneous capability requests
- Priority-based dispatching for agent execution (per FAB-009)
- Timeout and cancellation support
- Backpressure when providers are saturated

---

## Decision

### Chosen Approach: Hybrid — Async Facade + WFQ-Scheduled Agent Execution

Fabric uses **standard asyncio** for the fast path (Retrieval + Resolution) and the **existing WFQ scheduler** for the slow path (Agent Execution). **No FABRIC_MAILBOX is needed.** Epic 4.4 is bypassed.

### Architecture

```
Caller A ──┐
Caller B ──┤  async def execute(request)
Caller C ──┘         │
                     │ (concurrent via asyncio)
                     v
            ┌─────────────────┐
            │  FabricFacade   │  <- asyncio-based
            │                 │
            │  1. Retrieval   │  <= 20ms (FAISS, synchronous CPU-bound)
            │  2. Resolution  │  <= 5ms  (scoring, synchronous)
            │  3. Policy      │  <= 2ms  (rule check, synchronous)
            └────────┬────────┘
                     │
                     │ submit to WFQ scheduler
                     v
            ┌─────────────────┐
            │  WFQ Scheduler  │  <- ADR-0028, already exists
            │  (ISchedulerPort)│
            │                 │
            │  Agent Execution│  <= varies (50ms warm, 250ms cold)
            └─────────────────┘
```

### Why No Mailbox

| Factor | Mailbox Model | Async Model (Chosen) |
|---|---|---|
| Retrieval (FAISS) | Enqueue + dequeue overhead (~2ms) | Direct call (~0ms overhead) |
| Resolution (scoring) | Enqueue + dequeue overhead (~2ms) | Direct call (~0ms overhead) |
| Agent Execution | Mailbox WFQ scheduling | WFQ scheduler (already exists) |
| Backpressure | Mailbox depth limit | asyncio.Semaphore |
| Concurrency | MPSC mailbox + single consumer | asyncio tasks (cooperative) |
| Total overhead | ~4ms per request (enqueue/dequeue) | ~0ms for fast path |

**The mailbox adds ~4ms overhead to every request for Retrieval + Resolution (~25ms total), which is 16% overhead for zero benefit.** Retrieval and Resolution are CPU-bound, complete in <25ms, and don't need scheduling. Only Agent Execution benefits from WFQ scheduling, and that already exists via `ISchedulerPort`.

### Concurrency Control

```python
class FabricFacade:
    """
    Entry point for all Fabric operations.

    Concurrency: asyncio with bounded parallelism.
    """

    MAX_CONCURRENT_REQUESTS = 10  # Backpressure limit

    def __init__(
        self,
        retrieval: SemanticIndex,
        resolution: ProviderSelector,
        policy: PolicyGuard,
        scheduler: ISchedulerPort,
    ):
        self._retrieval = retrieval
        self._resolution = resolution
        self._policy = policy
        self._scheduler = scheduler
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a capability request through the full pipeline."""
        async with self._semaphore:
            # Fast path: synchronous, no scheduling needed
            candidates = await self._retrieval.search(request)
            provider = await self._resolution.resolve(candidates, request)
            self._policy.check(provider, request)

            # Slow path: agent execution via WFQ scheduler
            task = AgentExecutionTask(
                provider=provider,
                request=request,
                priority=request.wfq_priority,
                deadline_ms=request.deadline_ms,
            )
            return await self._scheduler.submit(task)
```

### Backpressure Strategy

| Mechanism | Trigger | Behavior |
|---|---|---|
| `asyncio.Semaphore(10)` | >10 concurrent requests | Callers await (back-pressure to Orchestrator) |
| `request.deadline_ms` | Request exceeds deadline | CapabilityResult.failure(error="deadline_exceeded") |
| Agent pool exhaustion | Max 3 agents active (ADR-0005) | Queue in WFQ scheduler, FIFO within priority class |

### Rationale

1. **KISS**: asyncio is Python's native concurrency model. Adding a mailbox layer adds complexity with no measurable benefit for the fast path.
2. **No new scheduling**: WFQ scheduler (ADR-0028) handles the only operation that needs priority scheduling (Agent Execution).
3. **Epic 4.4 bypassed**: FABRIC_MAILBOX from the architecture skeleton is NOT implemented. The skeleton predated the Fabric redesign; the actual need is asyncio + WFQ, not a full mailbox.
4. **Semaphore backpressure**: Simple, debuggable, and configurable. No custom queue depth management needed.

---

## Alternatives Considered

### Alternative 1: Mailbox-Based Actor Model (FABRIC_MAILBOX)

**Description:** Fabric operates as an actor with MPSC mailbox, WFQ scheduling for ALL operations (Retrieval, Resolution, Execution), and REALTIME priority band.

**Pros:**

- Consistent with K0 actor model conventions
- Built-in backpressure via mailbox depth
- Priority scheduling for all operations

**Cons:**

- ~4ms overhead per request for enqueue/dequeue (16% of fast path budget)
- MPSC mailbox means single consumer — serializes Retrieval calls that could run concurrently
- Requires Epic 4.4 implementation effort
- Over-engineering for operations that complete in <25ms

**Rejected because:** The overhead is measurable and the benefit is zero for the fast path. WFQ scheduling is only valuable for Agent Execution, which already has `ISchedulerPort`.

### Alternative 2: Simple Async/Await (No Backpressure)

**Description:** Pure asyncio with no concurrency limits or scheduling.

**Pros:**

- Simplest possible implementation
- Zero overhead

**Cons:**

- No backpressure (unbounded concurrency can exhaust resources)
- No priority scheduling for agent execution
- No timeout enforcement

**Rejected because:** Unbounded concurrency is dangerous. Without backpressure, a burst of 100 requests would spawn 100 FAISS searches + 100 agent executions simultaneously.

---

## Consequences

### Positive

- Zero overhead for fast path (Retrieval + Resolution)
- WFQ scheduling reused for slow path (no new scheduler code)
- Epic 4.4 (FabricMailbox) eliminated from implementation plan
- Simple debugging: asyncio task tree visible in standard Python tools

### Negative

- Architecture skeleton shows FABRIC_MAILBOX that won't be implemented (document deviation)
- No WFQ fairness metrics for Retrieval + Resolution (they're fast enough not to need them)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Semaphore limit too low/high | Medium | Low | Configurable; tune based on load testing |
| CPU-bound FAISS blocks event loop | Medium | High | Run FAISS in thread pool executor |
| Architect questions mailbox omission | Low | Low | This ADR documents the rationale |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| FabricFacade | `k1/fabric/facade.py` | New: asyncio + semaphore + scheduler |
| FabricDispatcher | `k1/fabric/concurrency/dispatcher.py` | New: request dispatching |
| TimeoutGuard | `k1/fabric/concurrency/timeout.py` | New: deadline enforcement |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.fabric.request.queued.v1` | Emitted | Request accepted by facade (semaphore acquired) |
| `k1.fabric.request.dispatched.v1` | Emitted | Request dispatched to WFQ scheduler for execution |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IFabricDispatcher` | `AsyncDispatcher` | New: replaces IFabricMailbox |
| `ISchedulerPort` | Existing WFQ adapter | Reused from ADR-0028 |

### Testing Strategy

- [ ] Concurrent request handling tests (10 simultaneous requests)
- [ ] Backpressure test (11th request waits for semaphore)
- [ ] Deadline enforcement test (expired request returns failure)
- [ ] WFQ scheduling integration test (URGENT preempts INTERACTIVE agent execution)
- [ ] FAISS thread pool test (CPU-bound search doesn't block event loop)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2025-01-01 | - | Initial proposal (seeded from implementation plan 1.1.9) |
| 2026-02-06 | - | Accepted: Async facade + WFQ for agent execution. FABRIC_MAILBOX eliminated. |
