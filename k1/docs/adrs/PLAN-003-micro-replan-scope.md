---
adr_id: PLAN-003
title: "Micro-Replan Scope and Limits"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "PLAN-001"
  - "PLAN-002"
  - "PLAN-006"
  - "ORCH-002"
related_events:
  - "k1.planner.plan.ready.v1"
  - "k1.planner.plan.failed.v1"
  - "k1.planner.delta.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "IMailboxPort"
  - "ILLMPort"
  - "IFabricRetrievalPort"
  - "IStateReadPort"
  - "IBridgePort"
implements_issue: "1.1.5"
superseded_by: ""
tags:
  - planner
  - micro-replan
  - pipeline
  - orchestrator
  - abbreviated
---

# PLAN-003: Micro-Replan Scope and Limits

## Context

### Problem Statement

During DAG execution, the Orchestrator may discover that remaining plan steps are no longer valid due to capability failures, new discoveries, or changed conditions. A full re-plan (~12s P50) is too slow for mid-execution adjustments. The Planner needs an abbreviated pipeline that adjusts remaining steps within a tight time budget while preserving already-completed work.

### Current Situation

planner.md SS10 defines a micro-replan mechanism: an abbreviated 3-stage pipeline (MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE, then COMMIT) with a 10s total budget. The Orchestrator triggers micro-replan via the `MicroReplanCheckpoint` guard after wave completion (ORCH-13). Only remaining (not-yet-executed) steps are eligible for modification.

### Constraints

- PLAN-12: Micro-replan adjusts remaining steps only; completed steps are frozen (SS10.1)
- Max 1 micro-replan per DAG execution (SS10.3)
- No HIL interaction during micro-replan (time budget too tight)
- Must acquire `_plan_lock` (PLAN-001) -- blocks if full plan in flight
- 10s caller-side timeout -- if a full plan is in flight (~12s P50), micro-replan almost always times out
- ToolCallRouter counter resets to 0 for micro-replan (SS10.3)

### Requirements

- Abbreviated pipeline completes within 10s total
- Remaining steps receive new capability mappings based on discoveries/failures
- Original plan structure preserved for completed steps
- CommittedPlan output replaces original plan for remaining steps only
- Overlap heuristic determines which remaining steps are affected

---

## Decision

### Chosen Approach

Micro-replan runs an abbreviated 3-stage pipeline with 10s total budget, bypassing the mailbox queue (planner.md SS10, SS4.2).

### Key Design

**Protocol (SS4.2):**

Micro-replan uses a direct method call, not event-driven:

```python
class IMailboxPort(Protocol):
    async def micro_replan(self, request: MicroReplanRequest) -> Optional[CommittedPlan]:
        """Abbreviated replan. Returns None on timeout or failure."""
```

This bypasses the mailbox queue entirely but still acquires `_plan_lock` for mutual exclusion with full plans.

**Abbreviated Pipeline Stages:**

| Stage | Budget ms | LLM Call | Description |
| ----- | --------- | -------- | ----------- |
| MICRO_SKETCH | 5000 | LLM-M1 | Generate partial replan from remaining steps + context |
| MICRO_EXPAND | 3000 | LLM-M2 | Remap affected steps to capabilities |
| MICRO_VALIDATE | 2000 | LLM-M3 | Validate replan against original plan constraints |
| COMMIT | <100 | None | Deterministic assembly (same as full plan COMMIT) |

Total: ~10s budget.

**MicroReplanRequest Content:**

```python
@dataclass(frozen=True)
class MicroReplanRequest:
    original_plan: CommittedPlan
    completed_step_ids: FrozenSet[str]
    discoveries: Tuple[Discovery, ...]
    failures: Tuple[FailureContext, ...]
    request_id: str
```

**Overlap Heuristic (SS10.2.2):**

Determines which remaining steps are affected by discoveries/failures:

- 3-way field match: exact match, substring forward, substring reverse
- Complexity: O(D * S * P) where D=discoveries, S=remaining steps, P=parameters per step
- Expected latency: <1ms for typical plan sizes
- Steps with overlap score above threshold are marked for re-expansion

**Scope Restrictions (SS10.3):**

- No HIL interaction (no clarification, no approval)
- Max 1 per DAG (second request returns None)
- ToolCallRouter counter resets to 0 (independent budget from full plan)
- Token budgets are separate from full plan (MICRO_SKETCH=1024, MICRO_EXPAND=512, MICRO_VALIDATE=256)

**Concurrency Model (SS24.3):**

```python
async def micro_replan(self, request: MicroReplanRequest) -> Optional[CommittedPlan]:
    try:
        async with asyncio.timeout(10.0):
            async with self._plan_lock:
                return await self._pipeline.execute_micro(request)
    except TimeoutError:
        return None
```

### Rationale

The abbreviated pipeline preserves the same 4-stage architecture while tightening budgets. Bypassing the mailbox queue avoids queuing delay but the lock ensures mutual exclusion. The 10s timeout is a pragmatic tradeoff: long enough to produce a useful replan, short enough that the Orchestrator can fall back to the original plan without significant delay.

---

## Alternatives Considered

### Alternative 1: Full Pipeline with Reduced Budgets

**Description:** Run the standard 4-stage pipeline but with halved token budgets and tighter timeouts.

**Pros:**

- Code reuse -- no separate MICRO_* states in FSM

**Cons:**

- Full pipeline includes HIL coordination points that are inappropriate for micro-replan
- FSM state diagram becomes confusing when same states have different behaviors

**Rejected because:** Dedicated MICRO_* FSM states make the abbreviated nature explicit and avoid conditional HIL logic inside stages.

### Alternative 2: Orchestrator-Side Plan Patching

**Description:** Orchestrator modifies the CommittedPlan directly by swapping failed steps with alternative capabilities.

**Pros:**

- No round-trip to Planner
- Instant (no LLM calls)

**Cons:**

- Violates separation of concerns (Orchestrator has no planning logic, ORCH-02)
- Cannot evaluate step dependencies or validate plan coherence
- Limited to 1:1 step replacement (cannot restructure)

**Rejected because:** Plan modification requires planning intelligence. The Planner owns plan structure; the Orchestrator owns plan execution.

---

## Consequences

### Positive

- Mid-execution plan adaptation within 10s budget
- Completed steps preserved (no re-execution)
- Same 4-stage architecture applied consistently
- Clear separation: Planner patches the plan, Orchestrator re-executes

### Negative

- Only 1 micro-replan per DAG (subsequent failures revert to original plan or fail)
- Lock contention with full plans means micro-replan often times out during active planning
- Abbreviated budgets may produce lower-quality replans than full pipeline

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| 10s timeout too tight for complex replans | Med | Med | Monitor timeout rate; V2 may increase budget |
| Overlap heuristic misses affected steps | Low | Med | Conservative matching (substring in both directions) |
| Micro-replan called during full plan (times out) | Med | Low | Orchestrator falls back to original plan |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
| --------- | ---- | ----------- |
| PipelineController | `k1/planner/pipeline_controller.py` [F03] | New -- execute_micro() method |
| PlanFSM | `k1/planner/plan_fsm.py` [F04] | New -- MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE states |
| OverlapHeuristic | `k1/planner/services/overlap.py` | New -- 3-way field match algorithm |
| MailboxAdapter | `k1/planner/adapters/mailbox_adapter.py` [F28] | New -- micro_replan() bypass method |
| PlannerConfig | `k1/planner/config.py` [F07] | New -- micro_replan_budgets, micro_replan_timeout_ms |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
| ----------- | --------- | ----------- |
| `k1.planner.plan.ready.v1` | Emitted | CommittedPlan from micro-replan (same event as full plan) |
| `k1.planner.delta.v1` | Emitted | Delta with type "micro_replan_committed" |

### Contracts Affected

| Contract | Type | Change |
| -------- | ---- | ------ |
| `module.contract.yaml` | Module | Declares micro-replan as capability with PLAN-12 invariant |
| `wiring.contract.yaml` | Module Wiring | IMailboxPort.micro_replan method signature |

### Port/Adapter Impact

| Port | Adapter | Change |
| ---- | ------- | ------ |
| `IMailboxPort` | `MailboxAdapter` | New method -- micro_replan(MicroReplanRequest) -> Optional[CommittedPlan] |

### Success Metrics

- Micro-replan P50 latency < 8s (within 10s budget)
- Micro-replan success rate > 70% when lock is free
- Overlap heuristic latency < 1ms for typical plan sizes (10-20 steps)

### Testing Strategy

- [ ] Unit test: overlap heuristic with known-affected and unaffected steps
- [ ] Unit test: MICRO_* FSM state transitions
- [ ] Unit test: micro_replan() returns None on timeout
- [ ] Integration test: full plan followed by micro-replan on same PlannerAgent
- [ ] Contract test: IMailboxPort.micro_replan Protocol compliance

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial decision -- abbreviated 3-stage micro-replan pipeline |
