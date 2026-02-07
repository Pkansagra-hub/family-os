---
adr_id: FAB-009
title: "Performance Scheduling in Fabric (Applies ADR-0028)"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-003"
  - "FAB-005"
  - "FAB-006"
related_events:
  - "k1.fabric.task.scheduled.v1"
  - "k1.fabric.task.priority_assigned.v1"
related_contracts: []
related_ports:
  - "ISchedulerPort"
implements_issue: "1.1.6"
superseded_by: ""
tags:
  - wfq
  - scheduling
  - priority
  - performance
  - latency
---

# FAB-009: Performance Scheduling in Fabric (Applies ADR-0028)

## Context

### Problem Statement

ADR-0028 defines a Weighted Fair Queuing (WFQ) scheduler with 4 priority classes. Fabric's 7 subsystems have different latency requirements. This ADR maps Fabric operations to WFQ priority classes and defines performance budgets for each subsystem.

### Legacy ADR-0028 Review Summary

ADR-0028 (1595 lines, APPROVED, COMPLETED) establishes:

- **4 priority classes** with proportional CPU weights:
  - URGENT (<=50ms, 10x weight) — barge-in, safety interventions
  - REALTIME (<=150ms, 5x weight) — voice, streaming, user-facing
  - INTERACTIVE (<=300ms, 3x weight) — standard user requests
  - BACKGROUND (<=5s, 1x weight) — learning, maintenance
- **Heap-based O(log n)**: <2ms enqueue/dequeue
- **Preemption**: URGENT preempts all lower priorities
- **Anti-starvation**: Force-schedule BACKGROUND if starved >500ms
- **Yield mechanism**: CPU-bound tasks yield every 10ms

### Fabric's Latency Requirements

Fabric sits between Orchestrator and Execution. Its latency contributes directly to the E2E turn latency budget (P95 <2000ms).

```
Orchestrator -> [Fabric: Retrieve + Resolve + Execute] -> Result
                 |_________|__________|_________|
                   ~20ms      ~5ms      varies (agent-dependent)
```

---

## Decision

### Chosen Approach: Map Fabric Operations to WFQ Priority Classes

Each Fabric operation is assigned a WFQ priority class based on the caller's context and the operation type.

### Priority Assignment Matrix

| Fabric Operation | WFQ Priority | Budget | Rationale |
|---|---|---|---|
| **Retrieval** (SemanticIndex.search) | Same as caller | <=20ms | Fast CPU-bound FAISS lookup; inherits caller priority |
| **Resolution** (ProviderSelector.resolve) | Same as caller | <=5ms | In-memory scoring; inherits caller priority |
| **PolicyGuard** (policy check) | Same as caller | <=2ms | Synchronous rule evaluation; inherits caller priority |
| **Agent Spawn** (AgentFactory.spawn) | INTERACTIVE | <=250ms cold / <=50ms warm | Always INTERACTIVE: spawning is a standard-priority allocation |
| **Agent Execution** (spawned agent runs) | Same as original caller | Varies (<=300ms INTERACTIVE, <=150ms REALTIME) | Agent inherits the priority of the original CapabilityRequest |
| **Index Rebuild** (SemanticIndex.rebuild) | BACKGROUND | <=5s | Maintenance operation; never block user requests |
| **Contract Registration** (Registry.register) | BACKGROUND | <=100ms | Admin operation; background priority |

### Priority Propagation Rule

```python
@dataclass
class CapabilityRequest:
    """Every request carries the caller's WFQ priority."""
    intent: str
    parameters: dict
    wfq_priority: WFQPriority  # Propagated from caller context
    deadline_ms: int            # Computed from priority class budget
    trace_id: str
```

**Rule**: Fabric DOES NOT upgrade or downgrade priority. It propagates the caller's `wfq_priority` through the pipeline: Retrieval -> Resolution -> Execution. The only exception is Agent Spawn, which is always INTERACTIVE (resource allocation is never URGENT or BACKGROUND).

### Performance Budget Breakdown

```
Total Fabric Budget (INTERACTIVE caller): <=300ms
  ├── Retrieval:  <=20ms  (FAISS IndexFlatIP, 768-dim, <1K contracts)
  ├── Resolution: <=5ms   (score + rank + policy check)
  ├── Execution:  <=275ms (agent spawn + LLM call + tool execution)
  │   ├── Agent Spawn (cold): <=250ms (warm: <=50ms via FAB-006 pooling)
  │   ├── LLM Call:           within remaining budget
  │   └── Tool Execution:     within remaining budget
  └── Overhead:   <1ms    (envelope creation, logging, tracing)
```

### Integration with ADR-0028 Scheduler

Fabric does NOT implement its own scheduler. It uses the existing WFQ scheduler via `ISchedulerPort`:

```python
class FabricFacade:
    def __init__(self, scheduler: ISchedulerPort, ...):
        self._scheduler = scheduler

    async def execute(self, request: CapabilityRequest) -> CapabilityResult:
        # Fast path: Retrieval + Resolution are synchronous, no scheduling needed
        candidates = await self._retrieval.search(request)
        provider = await self._resolution.resolve(candidates, request)

        # Slow path: Agent execution goes through scheduler
        task = AgentExecutionTask(
            provider=provider,
            request=request,
            priority=request.wfq_priority,
            deadline_ms=request.deadline_ms,
        )
        return await self._scheduler.submit(task)
```

### Rationale

1. **ADR-0028 is not modified**: Fabric uses existing priority classes, no new ones needed.
2. **Priority propagation** prevents priority inversion (user request stays at caller priority).
3. **Agent Spawn is always INTERACTIVE**: Prevents URGENT tasks from starving agent pools, and prevents BACKGROUND tasks from unnecessarily waiting for spawn slots.
4. **Retrieval + Resolution are synchronous**: No scheduling overhead for sub-millisecond operations.

---

## Alternatives Considered

### Alternative 1: Fabric gets its own FABRIC_REALTIME priority band

**Rejected because:**
- ADR-0028 has exactly 4 priority classes; adding a 5th changes the weight proportions for ALL K1 tasks.
- Fabric operations don't have a single latency requirement — they vary by operation type.
- Priority propagation from caller is more flexible.

### Alternative 2: All Fabric operations at REALTIME priority

**Rejected because:**
- Background operations (index rebuild, contract registration) don't need REALTIME priority.
- Would waste REALTIME budget on maintenance tasks.
- Anti-starvation guarantee would force BACKGROUND tasks to run anyway.

### Alternative 3: Fabric manages its own internal task queue

**Rejected because:**
- Duplicates ADR-0028 scheduler logic.
- Two schedulers competing for CPU time creates unpredictable behavior.
- FAB-003 (Concurrency Model) may introduce a mailbox, but that's dispatching, not scheduling.

---

## Consequences

### Positive

- Zero WFQ scheduler modifications needed
- Fabric respects existing priority balance
- Measurable per-subsystem latency budgets
- Priority propagation prevents inversion

### Negative

- Retrieval + Resolution don't go through scheduler (no WFQ fairness metrics for those stages)
- Agent Spawn always INTERACTIVE even if caller is URGENT (adds ~50ms warm / ~250ms cold to URGENT path)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Retrieval exceeds 20ms budget at >1K contracts | Low | Medium | Switch FAISS Flat to IVF at 10K contracts (FAB-002) |
| Agent cold start exceeds 250ms budget | Medium | High | Pre-warm popular templates, pool reuse (FAB-006) |
| URGENT caller waits for INTERACTIVE agent spawn | Low | Medium | Pre-warmed pool should satisfy most URGENT paths with <50ms warm start |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| CapabilityRequest | `k1/fabric/types/envelopes.py` | Add wfq_priority field |
| FabricFacade | `k1/fabric/facade.py` | Scheduler integration |
| AgentExecutionTask | `k1/fabric/execution/task.py` | New: wraps agent execution with priority |

### Testing Strategy

- [ ] Priority propagation test: INTERACTIVE caller -> agent executes at INTERACTIVE
- [ ] Agent spawn priority test: Always INTERACTIVE regardless of caller priority
- [ ] Latency budget tests: Retrieval <20ms, Resolution <5ms
- [ ] Anti-starvation test: BACKGROUND index rebuild gets scheduled within 500ms
- [ ] End-to-end budget test: Full Fabric pipeline <300ms for INTERACTIVE caller

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | - | Accepted: WFQ priority propagation, per-operation budget mapping. |
