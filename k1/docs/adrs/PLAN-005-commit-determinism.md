---
adr_id: PLAN-005
title: "CommitService Determinism Guarantee (PLAN-03)"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "PLAN-001"
  - "PLAN-002"
  - "ORCH-002"
related_events:
  - "k1.planner.plan.ready.v1"
  - "k1.planner.delta.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "IBridgePort"
  - "IDeltaEmitPort"
  - "IEventPort"
implements_issue: "1.1.7"
superseded_by: ""
tags:
  - planner
  - commit
  - determinism
  - plan-03
  - zero-llm
  - wal
---

# PLAN-005: CommitService Determinism Guarantee (PLAN-03)

## Context

### Problem Statement

Stage 4 COMMIT assembles the final `CommittedPlan` from the validated `ExpandedPlan` and `ValidationVerdict`. This stage must be fully deterministic: given the same inputs, it must produce the same output every time. Any non-determinism (LLM calls, random generation, external queries) in COMMIT would make plan output unreproducible, complicate crash recovery, and undermine test reliability.

### Current Situation

planner.md SS9 defines COMMIT as a zero-LLM stage. PLAN-03 is a system invariant that forbids LLM calls in COMMIT. This ADR formalizes the enforcement mechanism and documents the deterministic assembly steps.

### Constraints

- PLAN-03: COMMIT stage makes zero LLM calls (SS9, invariant table SS2)
- CommitService constructor must NOT accept ILLMPort (enforcement at interface level)
- CommittedPlan is a frozen dataclass (immutable after construction)
- WAL persistence is fire-and-forget (plan validity does not depend on WAL success)
- Plan output must be reproducible for testing and debugging

### Requirements

- Zero LLM calls in COMMIT stage
- Structural enforcement via constructor signature (not just convention)
- Deterministic UUID generation from request context (reproducible plan_id)
- WAL persistence via IBridgePort (idempotent upsert)
- Event emission of plan.ready.v1 and delta.v1

---

## Decision

### Chosen Approach

COMMIT is fully deterministic with zero LLM calls. Enforcement is structural: `CommitService` constructor signature excludes `ILLMPort` (planner.md SS9, SS30.5.3 F23).

### Key Design

**Constructor Enforcement (SS30.5.3 F23):**

```python
class CommitService:
    def __init__(
        self,
        bridge_port: IBridgePort,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
    ) -> None:
        # NO ILLMPort parameter -- PLAN-03 enforced at interface level
        self._bridge = bridge_port
        self._delta = delta_port
        self._event = event_port
```

This is enforced at the interface level, not just by convention. Any attempt to inject ILLMPort into CommitService requires changing the constructor signature, which is a contract violation detectable by static analysis and code review.

**Deterministic Assembly Steps (SS9.2):**

1. Generate `plan_id` as UUID5 from `(request_id, namespace=PLANNER_NS)` -- deterministic given same request
2. Collect `PlanStep` list from `ExpandedPlan.steps` (order preserved from EXPAND stage)
3. Build dependency dict from `PlanStep.depends_on` fields
4. Assign `created_at` timestamp from `StageContext.plan_start_time` (not `datetime.now()`)
5. Construct `CommittedPlan` as frozen dataclass

```python
async def commit(
    self,
    expanded: ExpandedPlan,
    verdict: ValidationVerdict,
    ctx: StageContext,
) -> CommittedPlan:
    plan_id = uuid5(PLANNER_NS, ctx.request_id)
    plan = CommittedPlan(
        plan_id=str(plan_id),
        request_id=ctx.request_id,
        steps=tuple(expanded.steps),
        dependencies=self._build_deps(expanded.steps),
        created_at=ctx.plan_start_time,
        metadata=PlanMetadata(
            sketch_token_usage=ctx.stage_token_usage[PlanStage.SKETCH],
            expand_token_usage=ctx.stage_token_usage[PlanStage.EXPAND],
            validate_token_usage=ctx.stage_token_usage[PlanStage.VALIDATE],
            total_duration_ms=ctx.elapsed_ms(),
        ),
    )
    return plan
```

**WAL Persistence (SS9.3):**

```python
# Fire-and-forget -- plan validity does NOT depend on WAL success
try:
    await self._bridge.persist_plan(plan)
except Exception:
    # Log warning but do not fail the plan
    pass
```

Idempotent upsert via `plan_id` dedup key. If WAL write fails, plan is still emitted on the event bus. WAL serves as crash-recovery backup, not as a correctness requirement.

**Event Emission:**

After assembly and WAL persist:

- `k1.planner.plan.ready.v1` with full `CommittedPlan` payload
- `k1.planner.delta.v1` with `{type: "plan_committed", plan_id, step_count, total_tokens}`

**Token Usage:**

Exactly 0 tokens consumed in COMMIT stage. `stage_token_usage[COMMIT] = 0` is verified by assertion.

### Rationale

Structural enforcement (constructor signature) is stronger than convention-based enforcement:

- Static analysis tools can verify ILLMPort is not injected
- Code review catches constructor changes
- No runtime check needed -- the dependency simply does not exist
- Deterministic plan_id via UUID5 ensures reproducibility
- Fire-and-forget WAL avoids making WAL availability a correctness dependency

---

## Alternatives Considered

### Alternative 1: Runtime Check (Assert No LLM Calls)

**Description:** CommitService accepts ILLMPort but has a runtime assertion that `_llm_call_count == 0` at end of commit.

**Pros:**

- Allows LLM injection for future use (e.g., commit-time summarization)

**Cons:**

- Runtime-only enforcement (fails in production, not at compile/review time)
- Presence of ILLMPort in constructor signals that LLM calls are expected
- Test must exercise the assertion path to verify

**Rejected because:** Structural enforcement is strictly stronger. If V2 needs LLM in COMMIT, a new ADR explicitly overrides PLAN-03 and the constructor changes.

### Alternative 2: CommitService as Pure Function

**Description:** `commit()` as a standalone function (not a class) with no injected dependencies. WAL and events handled by caller.

**Pros:**

- Pure function is trivially deterministic
- No dependency injection at all

**Cons:**

- Caller (PipelineController) must handle WAL persistence and event emission
- Breaks the consistent service-per-stage pattern
- Mixed responsibilities in PipelineController

**Rejected because:** Consistent service-per-stage pattern (SketchService, ExpandService, ValidateService, CommitService) keeps the architecture uniform. CommitService encapsulates all COMMIT concerns including WAL and event emission.

---

## Consequences

### Positive

- PLAN-03 invariant enforced at structural level (no ILLMPort in constructor)
- Reproducible plan output aids testing and debugging
- Fire-and-forget WAL avoids availability dependency
- Zero tokens in COMMIT -- cost-free final stage

### Negative

- Rigid constructor prevents future LLM use in COMMIT without ADR amendment
- UUID5 determinism requires consistent namespace UUID across deployments

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| WAL persistence failure | Low | Low | Fire-and-forget; plan emitted on event bus regardless |
| UUID5 namespace collision | Very Low | Low | PLANNER_NS is a fixed constant; collision probability negligible |
| Future need for LLM in COMMIT | Low | Med | New ADR explicitly overrides PLAN-03 with justification |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
| --------- | ---- | ----------- |
| CommitService | `k1/planner/services/commit_service.py` [F23] | New -- deterministic assembly, WAL persist, event emit |
| PipelineController | `k1/planner/pipeline_controller.py` [F03] | Modified -- calls commit_service.commit() in COMMIT stage |
| PlannerConfig | `k1/planner/config.py` [F07] | New -- PLANNER_NS UUID constant |
| CommittedPlan | `k1/orchestrator/types.py` | Existing -- frozen dataclass consumed by CommitService |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
| ----------- | --------- | ----------- |
| `k1.planner.plan.ready.v1` | Emitted | CommittedPlan ready for Orchestrator consumption |
| `k1.planner.delta.v1` | Emitted | Delta with type "plan_committed" |

### Contracts Affected

| Contract | Type | Change |
| -------- | ---- | ------ |
| `module.contract.yaml` | Module | Declares PLAN-03 invariant and COMMIT stage spec |
| `wiring.contract.yaml` | Module Wiring | CommitService ports: IBridgePort, IDeltaEmitPort, IEventPort (NO ILLMPort) |

### Port/Adapter Impact

| Port | Adapter | Change |
| ---- | ------- | ------ |
| `IBridgePort` | `BridgeAdapter` | Used for WAL persist_plan() |
| `IDeltaEmitPort` | `DeltaAdapter` | Used for delta emission |
| `IEventPort` | `EventAdapter` | Used for plan.ready.v1 emission |

### Success Metrics

- COMMIT token usage == 0 for every plan (assertion + metric)
- CommitService constructor has no ILLMPort parameter (static analysis check)
- WAL persist success rate > 99% (monitoring; failure is non-fatal)
- COMMIT stage latency < 100ms P99

### Testing Strategy

- [ ] Unit test: CommitService produces identical CommittedPlan for identical inputs
- [ ] Unit test: CommitService constructor rejects ILLMPort (static analysis or test)
- [ ] Unit test: WAL persist failure does not prevent plan.ready.v1 emission
- [ ] Unit test: plan_id is deterministic UUID5 from request_id
- [ ] Integration test: full pipeline ending in deterministic COMMIT
- [ ] Contract test: CommittedPlan schema validation against plan_ready.v1.json

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial decision -- zero-LLM deterministic COMMIT |
