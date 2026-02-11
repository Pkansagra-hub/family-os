---
adr_id: ORCH-005
title: "Orchestrator Concurrency Model -- Single-Threaded Mailbox Loop"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-002"
  - "ORCH-004"
  - "ORCH-012"
related_events:
  - "k1.orchestration.task.accepted.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IMailboxPort"
  - "IFabricGatewayPort"
implements_issue: "1.1.5"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - concurrency
  - mailbox
  - single-threaded
---

# ORCH-005: Orchestrator Concurrency Model -- Single-Threaded Mailbox Loop

## Context

### Problem Statement

The Orchestrator processes multiple message types (TaskEnvelope, CommittedPlan, WorkflowRunRequest, InterruptRequest) from its mailbox. A concurrency model must define how messages are dequeued, processed, and how parallelism is scoped to prevent race conditions, state corruption, and non-deterministic behavior.

K1 runs on edge devices with limited CPU cores. The Orchestrator must be efficient without introducing complexity from multi-threaded state management.

### Constraints

- Single async event loop (Python asyncio) shared with other K1 components
- Orchestrator internal state (PendingPlanContext, active DAG context) is mutable and not thread-safe
- Fabric.execute_batch() provides intra-wave parallelism (concurrent await, not threads)
- No concurrent DAG executions in V1 (one DAG at a time)
- Mailbox must remain responsive during long DAG executions (V1: deferred via ORCH-012 event-driven model)

### Requirements

- One message dequeued and processed at a time from mailbox
- Parallelism ONLY within DAG waves via `Fabric.execute_batch()` (concurrent async tasks)
- No shared mutable state between concurrent operations
- Interrupt handling at wave boundaries (check mailbox for InterruptRequest)
- ConcurrencyGuard rejects new DAG-requiring messages while a DAG is active (V1)

---

## Decision

### Chosen Approach

**Single-threaded async mailbox processing loop with intra-wave parallelism via execute_batch().**

### Key Design

```
Mailbox Processing Loop:
  while running:
    msg = await mailbox.dequeue()    # async wait, yields to event loop
    result = await process(msg)       # may fan out DAG waves internally
    deliver(result)                   # send AggregatedResult to Concierge

Within process(msg):
  if msg is TaskEnvelope(MEDIUM):
    # 1-2 sequential Fabric calls, fast path
    result = await dispatch_medium(msg)

  if msg is TaskEnvelope(HIGH):
    # Non-blocking: park context, send PlanRequest, return immediately
    dispatch_high(msg)  # parks PendingPlanContext, returns to loop

  if msg is CommittedPlan:
    # DAG execution: multiple waves, parallel steps per wave
    result = await DAGExecutor.execute(msg)
    # Inside execute(): waves run sequentially, steps within wave run in parallel

  if msg is WorkflowRunRequest:
    result = await dispatch_workflow(msg)

Within DAGExecutor.execute():
  for wave in waves:
    check_interrupt()  # peek mailbox for InterruptRequest
    step_results = await Fabric.execute_batch(wave.steps)  # PARALLEL within wave
    # All steps in wave run concurrently via asyncio.gather()
    # Wave completes when ALL steps complete or timeout
```

**ConcurrencyGuard (V1):**

Only one DAG execution active at a time. When a DAG is running:
- New TaskEnvelope(HIGH) messages receive DEFERRED ProcessResult and are re-enqueued
- New TaskEnvelope(MEDIUM) messages are processed normally (no DAG required, fast path)
- CommittedPlan messages for the active DAG are processed normally
- WorkflowRunRequests that require DAG are deferred

**No Threads, No Locks:**

| Concern | Approach |
|---------|----------|
| State mutation | Single writer (mailbox loop), no concurrent access |
| Step parallelism | asyncio.gather() within execute_batch(), no shared mutable state between steps |
| Interrupt checking | Mailbox peek (non-blocking), checked at wave boundaries |
| PendingPlanContext store | Dict accessed only from mailbox loop -- no concurrent mutation |

### Rationale

- Single-threaded eliminates all lock contention, race conditions, and deadlocks
- asyncio.gather() provides effective parallelism for I/O-bound Fabric calls without threads
- ConcurrencyGuard prevents resource contention between concurrent DAGs
- Same pattern used successfully by Concierge (proven in production)

---

## Alternatives Considered

### Alternative 1: Thread Pool for DAG Waves

**Rejected because:** Introduces shared mutable state between threads. StepResult aggregation, PendingPlanContext access, and interrupt flag checking all become concurrent data structure problems. The Orchestrator's overhead is I/O bound (waiting for Fabric), not CPU bound -- threads add complexity without improving throughput.

### Alternative 2: Actor Per DAG (Multi-DAG Concurrent)

**Rejected because:** V1 scope. Concurrent DAGs require isolation of DAG state, shared resource management (Fabric connection limits), and inter-DAG priority resolution. Deferred to V2 when observability data reveals whether single-DAG is a bottleneck.

---

## Consequences

### Positive

- Zero lock contention, zero race conditions, zero deadlocks
- Deterministic message processing order (debuggable, reproducible)
- asyncio.gather() maximizes I/O parallelism within waves without threads

### Negative

- Only one DAG active at a time (V1 limitation)
- Mailbox processing blocked during long synchronous operations (mitigated by ORCH-012 event-driven pattern)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Single-DAG bottleneck under load | Medium | Medium | ConcurrencyGuard defers, V2 multi-DAG upgrade path |
| Long wave blocks mailbox | Low | High | ORCH-012 non-blocking pattern, wave-boundary interrupt checks |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| Mailbox loop | `k1/orchestrator/orchestration/orchestrator_service.py` | New |
| ConcurrencyGuard | `k1/orchestrator/orchestration/guards/concurrency_guard.py` | New |
| DAGExecutor (asyncio.gather) | `k1/orchestrator/orchestration/dag_executor.py` | New |

### Success Metrics

- Zero race conditions in integration tests
- Single-DAG throughput: 3-8 steps/plan, <18ms overhead
- ConcurrencyGuard correctly defers concurrent DAG requests

### Testing Strategy

- [ ] Unit tests: ConcurrencyGuard defer/allow decisions
- [ ] Integration tests: concurrent MEDIUM during active DAG
- [ ] Stress tests: rapid message arrival during DAG execution

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- single-threaded mailbox concurrency model |
