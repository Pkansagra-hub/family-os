---
adr_id: ORCH-004
title: "Performance Scheduling -- WFQ Priority Mapping for Orchestrator"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-002"
  - "ORCH-003"
  - "FAB-009"
related_events:
  - "k1.orchestration.task.accepted.v1"
  - "k1.orchestration.dag.started.v1"
  - "k1.orchestration.step.completed.v1"
  - "k1.orchestration.delta.v1"
  - "k1.hil.progress.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IMailboxPort"
  - "IFabricGatewayPort"
  - "IDeltaEmitPort"
implements_issue: "1.1.4"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - performance
  - wfq
  - scheduling
  - priority
---

# ORCH-004: Performance Scheduling -- WFQ Priority Mapping for Orchestrator

## Context

### Problem Statement

ADR-0028 establishes the Weighted Fair Queuing (WFQ) Scheduler with 4 priority classes: URGENT (<=50ms), REALTIME (<=150ms), INTERACTIVE (<=300ms), BACKGROUND (<=5s). Every K1 component must map its operations to these priority classes so the scheduler can enforce latency budgets, prevent starvation, and ensure fair CPU allocation.

The Orchestrator generates several types of work items with different latency requirements. Without explicit priority mapping, all Orchestrator operations compete equally with unrelated system tasks, causing:
1. Mailbox message processing delayed behind background learning ticks
2. Progress deltas stalled behind DAG wave execution
3. User interrupts (barge-in during execution) waiting behind step completion
4. Workflow scheduler triggers missing their fire windows

### Current Situation

ADR-0028 defines the 4 priority classes with proportional CPU allocation:

| Priority | Latency Budget | CPU Weight | Use Case |
|----------|---------------|------------|----------|
| URGENT | <=50ms | 10x | Barge-in, cancel, emergency stop |
| REALTIME | <=150ms | 5x | Voice turns, model inference |
| INTERACTIVE | <=300ms | 3x | UI clicks, text input, task dispatch |
| BACKGROUND | <=5s | 1x | Learning, sync, cache cleanup |

FAB-009 (Performance Scheduling in Fabric) already mapped Fabric operations:
- Capability execution: INTERACTIVE (step-level)
- Semantic retrieval: INTERACTIVE
- Registry lookup: REALTIME (<1ms, effectively instant)
- Context building: INTERACTIVE

The Orchestrator must define its own mapping that aligns with Fabric's and integrates with the WFQ scheduler.

### Constraints

- Orchestrator operates on a single-threaded mailbox loop (no parallelism except within DAG waves)
- Mailbox has WFQ priority class REALTIME (ADR-0028 assignment for kernel message processing)
- DAG execution can span 10-45s for HIGH tier (many waves, each with multiple steps)
- Orchestrator overhead budget: <18ms P99 (excluding Fabric + Planner time)
- Progress deltas must reach user within reasonable latency (perceived responsiveness)

### Requirements

- Every Orchestrator operation classified into exactly one WFQ priority class
- Mailbox processing at REALTIME priority (per ADR-0028 kernel-level assignment)
- DAG waves at INTERACTIVE priority (primary user-facing work)
- Progress deltas at BACKGROUND priority (best-effort, non-blocking)
- User interrupts processed at URGENT priority (barge-in during execution)
- Workflow scheduler triggers at INTERACTIVE priority (time-sensitive but not urgent)
- Total Orchestrator system-owned overhead <18ms P99
- No starvation: BACKGROUND progress deltas always emitted within 5s

---

## Decision

### Chosen Approach

**Map all Orchestrator operations to WFQ priority classes, with the Orchestrator Mailbox at REALTIME and internal operations distributed across INTERACTIVE and BACKGROUND.**

### Key Design

**Complete Priority Mapping:**

| Orchestrator Operation | WFQ Priority | Latency Budget | Rationale |
|------------------------|-------------|----------------|-----------|
| Mailbox dequeue + routing | REALTIME | <=1ms | Kernel message processing must be responsive |
| TaskEnvelope acceptance | REALTIME | <=1ms | Part of mailbox dequeue (same priority) |
| dispatch_medium (build CapReq) | INTERACTIVE | <=5ms | Direct user-facing: build 1-2 requests |
| dispatch_high (build PlanReq) | INTERACTIVE | <=5ms | User-facing: build and park plan request |
| DAG wave construction | INTERACTIVE | <=5ms | Topological sort for next parallel batch |
| CapabilityRequest construction | INTERACTIVE | <=1ms/step | Per-step request building |
| Parameter reference resolution | INTERACTIVE | <=1ms/step | Substitute $ref placeholders |
| Output Schema Guard (ORCH-15) | INTERACTIVE | <=1ms/step | JSON schema validation per step result |
| Conditional Edge evaluation (ORCH-16) | INTERACTIVE | <=1ms/wave | Boolean expression evaluation |
| Token Budget check (ORCH-14) | INTERACTIVE | <=0.1ms/wave | Counter + threshold comparison |
| Discovery heuristic (ORCH-13) | INTERACTIVE | <=1ms/wave | Check discoveries against remaining params |
| Constraint validation | INTERACTIVE | <=5ms | Pre-execution capability existence check |
| Result aggregation | INTERACTIVE | <=2ms | Collect step results into AggregatedResult |
| User interrupt check | URGENT | <=1ms | Barge-in / cancel at wave boundary |
| Progress delta emission | BACKGROUND | <=5s | Step narration to user (best-effort) |
| Audit write (Bridge) | BACKGROUND | <=5s | Fire-and-forget to K0 |
| Constraint progress reporting | BACKGROUND | <=5s | Observability event |
| Workflow trigger check | INTERACTIVE | <=5ms | Scheduler due-time evaluation |
| Workflow compilation | INTERACTIVE | <=10ms | Rehydrate frozen DAG |
| Gap detection scan | BACKGROUND | <=5s | Proactive workflow gap analysis |

**Mailbox WFQ Configuration:**

```
IMailboxPort:
  priority_class: REALTIME
  max_depth: 100
  backpressure: reject at depth 100 (RECOVERABLE error)
  dequeue_order: WFQ priority within REALTIME class
    Sub-ordering within mailbox:
      1. InterruptRequest (USER_CANCEL, MODIFY_PARAMS)
      2. CommittedPlan (plan.ready event re-enqueued)
      3. TaskEnvelope (MEDIUM before HIGH by default)
      4. WorkflowRunRequest
```

The Orchestrator's own mailbox provides internal prioritization within the REALTIME WFQ class. This means the system scheduler gives Orchestrator mailbox processing 5x CPU weight relative to INTERACTIVE work, ensuring kernel message handling is never starved.

**DAG Wave Execution Budget Breakdown:**

```
Per DAG execution (HIGH tier typical: 5 steps, 2 waves):

  Wave construction (topological sort):      5ms   INTERACTIVE
  Wave 1 (3 parallel steps):
    - 3x CapReq construction:               3ms   INTERACTIVE
    - 3x param resolution:                  3ms   INTERACTIVE
    - 3x Fabric.execute() [EXTERNAL]:      varies  (Fabric's budget)
    - 3x output schema validation:          3ms   INTERACTIVE
    - Conditional edge evaluation:          1ms   INTERACTIVE
    - Token budget check:                   0.1ms INTERACTIVE
    - Discovery heuristic:                  1ms   INTERACTIVE
    - Progress delta emission:              1ms   BACKGROUND
  Wave 2 (2 sequential steps):
    - Similar per-step overhead:            ~6ms  INTERACTIVE
    - Progress delta:                       1ms   BACKGROUND
  Result aggregation:                       2ms   INTERACTIVE
  Audit write:                              1ms   BACKGROUND

  Total Orchestrator overhead:              ~17ms (within 18ms budget)
  Total Fabric time:                        variable (Fabric's SLI)
  Total Planner time:                       10-30s (Planner's SLI)
```

**Interrupt Handling at URGENT Priority:**

```
At each wave boundary, the mailbox loop checks for interrupts:

  check_interrupt():
    1. Peek mailbox for InterruptRequest messages
    2. If found: process at URGENT priority (<1ms)
    3. Actions:
       - CANCEL_DAG: set cancel flag, stop dispatching waves
       - MODIFY_PARAMS: update remaining step params in-place
       - CONTINUE: no-op, resume DAG
    4. If not found: continue to next wave
```

Interrupts are checked at wave boundaries (not per-step) to avoid overhead. The WFQ scheduler guarantees URGENT tasks preempt INTERACTIVE DAG work, so a barge-in during wave execution triggers at the next yield point. The yield point is the `await` in `execute_batch()`.

**Tier-Specific Budget Envelopes:**

| Tier | Total Budget | Orch Overhead | Planner | Fabric | Headroom |
|------|-------------|---------------|---------|--------|----------|
| MEDIUM | 10s | <15ms | 0 | 1-9.985s | ~15ms |
| HIGH | 45s | <15ms | 10-30s | varies | 15s buffer before CB_ORCHESTRATOR 60s |

### Rationale

1. **REALTIME for mailbox aligns with ADR-0028 kernel assignment.** The Orchestrator is a kernel component alongside Concierge and Event Bus. Kernel message processing must not be starved by application-level work.

2. **INTERACTIVE for DAG operations matches user-facing latency expectations.** Users initiated the request and expect visible progress. INTERACTIVE's 300ms budget per operation is well within the 18ms total Orchestrator overhead.

3. **BACKGROUND for progress deltas preserves responsiveness.** Progress narration is nice-to-have but should never block DAG execution. BACKGROUND's 5s budget and 1x CPU weight is sufficient for fire-and-forget deltas.

4. **URGENT for interrupts ensures barge-in responsiveness.** ADR-0028 allocates URGENT for cancel/interrupt operations. The Orchestrator's interrupt check at wave boundaries guarantees <50ms response to user cancellation (wave duration is typically 10-200ms).

5. **Budget arithmetic confirms feasibility.** The detailed per-operation breakdown shows 17ms total overhead for a typical 5-step DAG, well within the 18ms P99 budget.

---

## Alternatives Considered

### Alternative 1: All Orchestrator Operations at REALTIME

**Description:** Map everything (DAG waves, deltas, audits) to REALTIME priority.

**Pros:**
- Simple mapping (one priority class)
- Guarantees fast processing

**Cons:**
- REALTIME is for sub-150ms kernel operations; DAG waves can take seconds (Fabric time)
- Monopolizes REALTIME CPU allocation for non-kernel work
- Starves other REALTIME consumers (Concierge, Event Bus)

**Rejected because:** REALTIME is for the Orchestrator's kernel-level mailbox processing, not for application-level DAG execution. Over-prioritizing DAG work steals CPU from other kernel components.

### Alternative 2: All Internal Operations at INTERACTIVE

**Description:** Drop BACKGROUND for progress deltas, use INTERACTIVE for everything inside the Orchestrator.

**Pros:**
- Simpler (only two priority classes used: REALTIME for mailbox, INTERACTIVE for everything else)
- Progress deltas delivered faster

**Cons:**
- Progress deltas compete with DAG step execution for CPU
- Audit writes compete with parameter resolution
- No distinction between essential work and nice-to-have work

**Rejected because:** Progress deltas and audit writes are fire-and-forget; they should explicitly yield CPU to step execution. BACKGROUND classification makes this explicit and allows the WFQ scheduler to defer them under load.

---

## Consequences

### Positive

- Every Orchestrator operation has an explicit latency budget enforced by the WFQ scheduler
- Mailbox processing at REALTIME prevents kernel-level starvation
- DAG execution at INTERACTIVE ensures user-facing work gets proportional CPU
- Progress deltas at BACKGROUND prevent non-essential work from blocking execution
- Interrupt handling at URGENT guarantees barge-in responsiveness
- Budget arithmetic verified: 17ms total overhead within 18ms P99 target

### Negative

- Progress deltas may be delayed up to 5s under extreme CPU pressure (acceptable for best-effort narration)
- Audit writes may be delayed under load (acceptable for fire-and-forget Edge-First pattern)
- Priority mapping adds cognitive overhead for developers (documented in this ADR)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Orchestrator overhead exceeds 18ms budget | Low | High | Per-operation microbenchmarks in CI, alert on regression |
| Progress deltas starved (user sees no progress) | Low | Medium | Anti-starvation guarantee from ADR-0028: BACKGROUND runs every 500ms minimum |
| Interrupt latency exceeds 50ms | Low | High | Wave boundary checks guarantee interrupt processing within 1 wave duration |
| WFQ scheduler itself adds overhead | Low | Low | ADR-0028 measured <2ms enqueue/dequeue |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| IMailboxPort (REALTIME config) | `k1/orchestrator/ports/mailbox_port.py` | New |
| MailboxAdapter (WFQ integration) | `k1/orchestrator/adapters/mailbox_adapter.py` | New |
| DAGExecutor (INTERACTIVE scheduling) | `k1/orchestrator/orchestration/dag_executor.py` | New |
| DeltaEmitAdapter (BACKGROUND priority) | `k1/orchestrator/adapters/delta_emit_adapter.py` | New |
| Interrupt handler | `k1/orchestrator/orchestration/orchestrator_service.py` | New |

### Events Emitted/Consumed

| Event Topic | Direction | Priority | Description |
|-------------|-----------|----------|-------------|
| `k1.orchestration.task.accepted.v1` | Emitted | REALTIME | Inline with mailbox dequeue |
| `k1.orchestration.dag.started.v1` | Emitted | INTERACTIVE | DAG execution initiated |
| `k1.orchestration.step.completed.v1` | Emitted | INTERACTIVE | Step finished |
| `k1.orchestration.dag.completed.v1` | Emitted | INTERACTIVE | DAG finished |
| `k1.hil.progress.v1` | Emitted | BACKGROUND | Step narration |
| `k1.orchestration.delta.v1` | Emitted | BACKGROUND | Progress deltas |

### Contracts Affected

| Contract | Type | Change |
|----------|------|--------|
| Orchestrator module contract | Module | Add priority_mapping section |
| ADR-0028 alignment | Cross-cutting | Orchestrator operations mapped to 4 WFQ classes |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IMailboxPort` | `MailboxAdapter` | Configure REALTIME priority class |
| `IDeltaEmitPort` | `DeltaEmitAdapter` | Tag emissions with BACKGROUND priority |

### Success Metrics

- Orchestrator overhead <18ms P99 (measured by span tracing)
- Mailbox dequeue latency <1ms P99
- Interrupt-to-acknowledgment <50ms
- Zero starvation events for progress deltas (anti-starvation guarantee from ADR-0028)
- Budget envelope compliance: MEDIUM <10s, HIGH <45s

### Testing Strategy

- [ ] Microbenchmarks: per-operation latency in `tests/k1/orchestrator/perf/`
- [ ] Integration tests: WFQ priority inheritance through mailbox -> DAG -> delta
- [ ] Interrupt tests: barge-in during DAG execution, measure latency
- [ ] Load tests: concurrent MEDIUM + HIGH + workflow, verify no starvation
- [ ] Anti-starvation tests: verify BACKGROUND deltas emitted under sustained INTERACTIVE load

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- WFQ priority mapping for ADR-0028 compliance |
