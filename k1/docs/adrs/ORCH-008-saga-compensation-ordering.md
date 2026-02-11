---
adr_id: ORCH-008
title: "Saga Compensation Ordering -- Strict Reverse Sequential"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-005"
  - "ORCH-007"
related_events:
  - "k1.orchestration.dag.compensation.started.v1"
  - "k1.orchestration.dag.compensation.completed.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IFabricGatewayPort"
  - "IBridgeWritePort"
implements_issue: "1.1.8"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - saga
  - compensation
  - rollback
---

# ORCH-008: Saga Compensation Ordering -- Strict Reverse Sequential

## Context

### Problem Statement

When a DAG step fails and dependent steps are cancelled (ORCH-07), completed steps with side effects may need rollback. The compensation (saga recovery) pattern must define:

1. In what ORDER compensations execute
2. Whether compensations run concurrently or sequentially
3. What happens when a compensation itself fails

This resolves Open Question Q1 from orchestrator.md Section 26.

### Current Situation

PlanStep can declare a `compensation_capability` -- a capability to invoke if the step's side effects need to be undone (e.g., undo a calendar event creation, revert a file write). DAGExecutor must execute these compensations when a DAG fails mid-execution.

### Constraints

- Compensations may have ordering dependencies (step B's compensation might fail if step A's compensation hasn't run yet -- e.g., deleting a child resource before parent)
- Orchestrator has no knowledge of step semantics (blind executor) -- it cannot infer compensation dependencies
- Compensation execution adds latency to failure recovery
- CompensationRecord must be audited via IBridgeWritePort for K0 traceability

### Requirements

- Deterministic compensation order (reproducible in tests and production)
- Side-effect correctness: compensations must not create inconsistent states
- Failed compensations must not block remaining compensations
- Complete audit trail of all compensation attempts

---

## Decision

### Chosen Approach

**Strict reverse execution order. Sequential (not concurrent). Failed compensations are dead-lettered and logged.**

### Key Design

**Compensation Execution Protocol:**

```text
Given completed steps in execution order: [S1, S2, S3, S4]
Step S4 fails.
Compensate: S3 -> S2 -> S1 (reverse order, sequential)

Per compensation:
  1. Build CapabilityRequest from step.compensation_capability + step.compensation_params
  2. Execute via Fabric.execute() (single call, no retry)
  3. Record CompensationRecord{status: EXECUTED | FAILED}
  4. If FAILED: log error, mark DEAD_LETTERED, continue to next
  5. Audit all records via IBridgeWritePort
```

**Which Steps Get Compensated:**

Only steps that satisfy ALL of:
- status == COMPLETED (actually ran and succeeded)
- compensation_capability is not None (step declares a rollback action)
- Not already compensated (idempotency check)

Steps with status PENDING, RUNNING, CANCELLED, SKIPPED, or FAILED are never compensated.

**CompensationRecord Lifecycle:**

```text
PENDING -> EXECUTED  (compensation succeeded)
PENDING -> FAILED -> DEAD_LETTERED  (compensation failed, abandoned)
```

DEAD_LETTERED records generate a telemetry alert (structured log at ERROR level) and are included in AggregatedResult.compensations for Concierge visibility.

**No Retry on Compensation Failure:**

Compensations execute exactly once. Rationale:
- If a compensation fails, retrying with the same params is unlikely to succeed (transient failures are rare for rollback operations)
- Compensation retry chains risk infinite loops or cascading failures
- Dead-lettering with audit trail allows manual intervention
- V2 may add a one-retry policy if operational data shows transient compensation failures

**Sequential Execution (No Concurrent Compensation):**

V1 enforces sequential compensation even for steps from the same wave (which originally ran in parallel). Rationale:
- Cannot infer which compensations are independent without semantic knowledge
- Reverse-sequential is the safest default
- Concurrent compensation adds test complexity disproportionate to the latency savings
- V2: add `compensation_group` to PlanStep allowing parallel compensation within groups

### Rationale

- Strict reverse order is the safest strategy for side-effect rollback (same as database transaction rollback semantics)
- Sequential execution prevents race conditions between compensations
- Dead-lettering with audit trail provides manual recovery capability without automated retry risk
- Deterministic order makes compensation behavior fully reproducible in tests

---

## Alternatives Considered

### Alternative 1: Concurrent Compensation (Parallel All)

**Rejected because:** Without compensation dependency knowledge, parallel execution risks inconsistent states. Example: step S2 created a sub-resource of S1. If S1's compensation (delete parent) runs concurrently with S2's (delete child), the child deletion may fail if parent is deleted first. Reverse-sequential naturally handles parent-child by deleting child first.

### Alternative 2: Forward Order Compensation

**Rejected because:** Forward order is counter-intuitive and dangerous for hierarchical side effects. Created-first should be undone-last, matching stack-based rollback semantics universally used in databases, file systems, and transaction managers.

### Alternative 3: Compensation with Retry (Max 2)

**Rejected because:** Adds complexity without clear benefit in V1. Operational data does not yet exist to justify retry. Dead-letter + alert + manual intervention is sufficient for V1 scale. Re-evaluate in V2 with production telemetry.

---

## Consequences

### Positive

- Deterministic, reproducible compensation order
- Zero race conditions (sequential execution)
- Complete audit trail for every compensation attempt
- Dead-letter pattern prevents compensation cascades

### Negative

- Sequential compensation adds latency (linear in number of compensated steps)
- No automatic retry on compensation failure (manual intervention required)
- Cannot optimize independent compensations for parallel execution (V1 limitation)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Compensation itself causes additional side effects | Low | High | Compensation capabilities SHOULD be idempotent by design |
| Dead-lettered compensation leaves orphaned resources | Medium | Medium | Telemetry alert + K0 audit trail for manual cleanup |
| Sequential compensation too slow for large DAGs | Low | Low | Typical DAG: 3-8 steps, max ~8 compensations. <1s total. |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| DAGExecutor._compensate() | `k1/orchestrator/orchestration/dag_executor.py` | New |
| CompensationRecord | `k1/orchestrator/types.py` | New |
| AggregatedResult.compensations | `k1/orchestrator/types.py` | New |
| IBridgeWritePort (audit) | `k1/orchestrator/ports/bridge_write_port.py` | New |

### Success Metrics

- Compensations always execute in strict reverse order (verified by test assertions on order)
- Dead-lettered compensations generate telemetry alerts
- Zero race conditions in compensation (sequential, never concurrent)

### Testing Strategy

- [ ] Unit tests: 3-step DAG, step 3 fails, compensate S2 then S1
- [ ] Unit tests: compensation failure -> DEAD_LETTERED, execution continues
- [ ] Unit tests: step without compensation_capability is skipped
- [ ] Integration tests: compensation audit records written to IBridgeWritePort

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- strict reverse sequential compensation |
