---
adr_id: ORCH-007
title: "Adaptive Blind DAG Extensions -- V1 Guard Pipeline"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-005"
# Originally referenced ADR-0007 (legacy K0 ADR, not migrated to K1).
related_events:
  - "k1.orchestration.dag.step.completed.v1"
  - "k1.orchestration.dag.micro_replan.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IFabricGatewayPort"
  - "IPlannerPort"
  - "IDeltaEmitPort"
implements_issue: "1.1.7"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - adaptive-dag
  - guards
  - v1-scope
---

# ORCH-007: Adaptive Blind DAG Extensions -- V1 Guard Pipeline

## Context

### Problem Statement

The Blind DAG Executor (ORCH-001) needs agent-aware extensions that enhance basic topological execution with runtime intelligence. These extensions must remain deterministic (no LLM calls) while providing schema validation, conditional branching, mid-flight replanning, execution monitoring, and concurrency control.

The original design specified 8 guards. Three of these consume fields that no upstream provider populates in V1.

### Current Situation

Orchestrator.mmd defines 8 adaptive extensions:
1. OutputSchemaGuard (ORCH-15)
2. ConditionalEdgeEvaluator (ORCH-16)
3. TokenBudgetTracker (ORCH-14)
4. QualityGate
5. MicroReplanCheckpoint (ORCH-13)
6. ExecutionMonitor
7. Sub-Step Observability (pass-through)
8. ConcurrencyGuard

Fabric's CapabilityResult does NOT include `cost_usd`, `tokens_consumed`, or `quality_score` fields. No provider in the current Fabric implementation populates these values.

### Constraints

- All guards must be deterministic (no LLM, ORCH-02)
- Guards execute within DAG wave boundaries
- Guards must not add significant latency (per ORCH-004 WFQ budget: 17ms total DAG overhead)
- Cannot consume data that does not exist in upstream types

### Requirements

- Define which guards ship in V1 and which are deferred to V2
- Provide clear reintroduction criteria for deferred guards
- Ensure V1 guards cover the critical execution safety needs

---

## Decision

### Chosen Approach

**5 guards in V1. 3 guards deferred to V2 (phantom field consumers).**

### V1 Guard Pipeline (Active)

| Guard | Invariant | Trigger Point | Purpose |
|-------|-----------|---------------|---------|
| OutputSchemaGuard | ORCH-15 | After each step completes | Validates step output against declared JSON Schema. On fail: schema-retry with hint (1 retry). |
| ConditionalEdgeEvaluator | ORCH-16 | Before dispatching each step in wave | Evaluates boolean conditions on edges. FALSE -> step SKIPPED. V1: simple comparisons only (no function calls). |
| MicroReplanCheckpoint | ORCH-13 | After each wave completes | Checks for discoveries (new facts) or failures. If triggered: sends MicroReplanRequest to Planner. Max 1 per DAG. |
| ExecutionMonitor | -- | After each wave completes | Emits progress summaries via IDeltaEmitPort. Listens for user override (CANCEL_DAG) via IEventSubscriptionPort. Sets interrupt flag on cancel. |
| ConcurrencyGuard | -- | Before DAG execution starts | Ensures at most one DAG active (V1). Defers new DAG-requiring messages. |

### V2 Deferred Guards (Removed from V1)

| Guard | Reason for Deferral | Reintroduction Criteria |
|-------|---------------------|------------------------|
| TokenBudgetTracker (ORCH-14) | Fabric CapabilityResult has no `tokens_consumed` field. No LLM provider reports token usage metadata. | V2: When LLM providers report usage metadata in CapabilityResult.data or a dedicated field. |
| QualityGate | Fabric CapabilityResult has no `quality_score` field. No provider populates quality metrics. | V2: When a quality scoring pipeline exists (inference-time or post-hoc evaluation). |
| CostBudgetGuard | Fabric CapabilityResult has no `cost_usd` field. No provider reports cost per invocation. | V2: When LLM providers report cost metadata. Depends on TokenBudgetTracker. |

### Guard Execution Order

```text
Per wave:
  1. ConcurrencyGuard.check()         -- reject if another DAG active
  2. ConditionalEdgeEvaluator.evaluate(step)  -- per step, before dispatch
  3. [step executes via Fabric]
  4. OutputSchemaGuard.validate(step_result)   -- per step, after result
  5. MicroReplanCheckpoint.check(wave_results) -- after all steps in wave
  6. ExecutionMonitor.report(wave_results)     -- after all steps in wave
```

**Guard Interface:**

```python
class IGuard(Protocol):
    """All guards implement this protocol."""

    async def check(self, context: GuardContext) -> GuardResult:
        """Returns PASS, FAIL, SKIP, or REPLAN."""
        ...

@dataclass(frozen=True)
class GuardResult:
    action: str          # "PASS", "FAIL", "SKIP", "RETRY", "REPLAN"
    reason: str          # Human-readable explanation
    modified_steps: Optional[List[PlanStep]]  # For REPLAN only
```

### OutputSchemaGuard Detail (ORCH-15)

- PlanStep declares `output_schema: Optional[Dict]` (JSON Schema)
- After Fabric returns CapabilityResult, guard validates `result.data` against schema
- On validation failure: re-execute step with schema hint appended to params (`_schema_hint: str`)
- Max 1 schema retry per step (then FAIL with schema_retry=True in StepResult)
- Schema retry does NOT count against ORCH-06 (2 execution retries) -- separate budget

### ConditionalEdgeEvaluator Detail (ORCH-16)

- PlanStep declares `condition: Optional[str]` (expression string)
- V1 language: simple comparisons only
  - `$step_1.result.field == "value"`
  - `$step_1.result.count > 5`
  - `$step_1.status == "COMPLETED"`
  - Boolean operators: `and`, `or`, `not`
- No function calls, no nested expressions, no regex (V1)
- FALSE -> step status = SKIPPED, skip reason logged in StepResult.error_detail

### MicroReplanCheckpoint Detail (ORCH-13)

- After wave N completes, checkpoint evaluates:
  1. Any step discovered new information (result.data contains discovery markers)
  2. Any step failed and dependent steps exist
- If triggered: build MicroReplanRequest with completed results + remaining steps
- Send to Planner via IPlannerPort.micro_replan()
- Planner returns adjusted CommittedPlan (replacement steps only)
- Max 1 micro-replan per DAG execution (counter tracked per DAG)
- If already replanned: skip checkpoint, continue with original remaining plan

### Rationale

- V1 ships only guards with real upstream data, avoiding phantom-field consumption
- 5 guards cover all critical safety needs (schema validation, conditional execution, mid-flight adjustment, progress/cancel, concurrency)
- Deferred guards have explicit reintroduction criteria tied to upstream capability changes
- Guard pipeline is extensible -- V2 guards slot into the same IGuard interface

---

## Alternatives Considered

### Alternative 1: Ship All 8 Guards with Stub Implementations

**Rejected because:** Stub guards that always return PASS provide no value. They add code surface (import, registration, testing) without functionality. Worse, they create an illusion of protection that does not exist. Clean removal with documented V2 re-add criteria is more honest.

### Alternative 2: Remove Deferred Guards from Architecture Entirely

**Rejected because:** TokenBudgetTracker, QualityGate, and CostBudgetGuard are architecturally sound concepts. Their MMD definitions and invariant assignments (ORCH-14) should remain in the architecture diagram as "V2 planned" markers. Only the implementation and type definitions are removed from V1.

---

## Consequences

### Positive

- Zero phantom-field consumption -- every guard operates on real data
- Reduced V1 test surface (~45 tests removed from estimated total)
- Clear V2 upgrade path with explicit reintroduction criteria

### Negative

- No token budget protection in V1 (unbounded LLM usage per DAG)
- No cost tracking in V1 (no per-request cost visibility)
- No quality gating in V1 (no automatic quality-based retry)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Unbounded token usage in V1 | Medium | Medium | Fabric-level provider timeouts limit individual step duration |
| Missing quality signals | Low | Low | Manual inspection of results; Learning Loop captures patterns |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| OutputSchemaGuard | `k1/orchestrator/orchestration/guards/output_schema_guard.py` | New |
| ConditionalEdgeEvaluator | `k1/orchestrator/orchestration/guards/conditional_edge_evaluator.py` | New |
| MicroReplanCheckpoint | `k1/orchestrator/orchestration/guards/micro_replan_checkpoint.py` | New |
| ExecutionMonitor | `k1/orchestrator/orchestration/guards/execution_monitor.py` | New |
| ConcurrencyGuard | `k1/orchestrator/orchestration/guards/concurrency_guard.py` | New |
| IGuard Protocol | `k1/orchestrator/orchestration/guards/__init__.py` | New |

### Success Metrics

- OutputSchemaGuard catches 100% of schema violations in test suite
- ConditionalEdgeEvaluator correctly skips FALSE-condition steps
- MicroReplanCheckpoint triggers exactly once per DAG max
- ConcurrencyGuard defers 100% of concurrent DAG requests

### Testing Strategy

- [ ] Unit tests per guard: PASS/FAIL/SKIP/REPLAN results
- [ ] Integration tests: guard pipeline within DAGExecutor wave loop
- [ ] Regression tests: V2 guard stubs do not interfere with V1 pipeline

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- 5 guards V1, 3 deferred to V2 |
