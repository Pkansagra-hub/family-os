---
adr_id: PLAN-002
title: "LLM Budget Enforcement Strategy"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "PLAN-001"
  - "PLAN-005"
  - "ORCH-002"
related_events:
  - "k1.planner.delta.v1"
  - "k1.planner.plan.ready.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "ILLMPort"
implements_issue: "1.1.4"
superseded_by: ""
tags:
  - planner
  - llm
  - token-budget
  - enforcement
  - model-hub
---

# PLAN-002: LLM Budget Enforcement Strategy

## Context

### Problem Statement

The Planner makes multiple LLM calls across the 4-stage pipeline. Without explicit per-stage budgets, a verbose SKETCH response could exhaust the token allocation before EXPAND or VALIDATE stages execute. Budget enforcement must be declarative (stamped on each request), tracked per-stage, and reported in the plan completion delta.

### Current Situation

planner.md SS13 defines a per-stage token budget table and an injection protocol. The Model Hub already enforces `max_tokens` and `timeout_ms` on its side -- the Planner's responsibility is to declare correct budgets in every `HubRequest.constraints` object and track actual usage for observability.

### Constraints

- PLAN-11: Every `HubRequest.constraints` must carry explicit `max_tokens` and `timeout_ms` (SS13.3)
- PLAN-03: COMMIT stage makes zero LLM calls (enforced by PLAN-005)
- Model Hub is the enforcement boundary -- Planner declares, Model Hub truncates/rejects
- V1 defers PLAN-07 (per-step `token_budget` on PlanStep) to reduce type complexity

### Requirements

- Each LLM call must carry per-stage budget in `HubRequest.constraints`
- Token usage must be tracked per stage and reported in PLAN_END delta
- Budget injection must be centralized in PipelineController (single source of truth)
- 5 main LLM call types + 3 micro-replan variants must all carry budgets

---

## Decision

### Chosen Approach

Every LLM call carries explicit budget in `HubRequest.constraints`, injected by PipelineController at stage transition (planner.md SS13.3).

### Key Design

**Budget Table (SS13.3):**

| Stage | max_tokens | timeout_ms | temperature | LLM Call IDs |
| ----- | ---------- | ---------- | ----------- | ------------ |
| SKETCH | 2048 | 8000 | 0.7 | LLM-1 |
| EXPAND | 1024 | 5000 | 0.3 | LLM-2 |
| VALIDATE | 512 | 3000 | 0.2 | LLM-3 |
| COMMIT | 0 | 0 | N/A | None |

Total budget: ~3,584 tokens per full plan.

**Injection Point:**

PipelineController stamps the next stage's `HubRequest.constraints` at STAGE_TRANSITION (SS23.3 step 6):

```python
class PipelineController:
    def _build_hub_request(self, stage: PlanStage, prompt: str) -> HubRequest:
        budget = self._config.stage_budgets[stage]
        return HubRequest(
            prompt=prompt,
            constraints=HubConstraints(
                max_tokens=budget.max_tokens,
                timeout_ms=budget.timeout_ms,
                temperature=budget.temperature,
            ),
        )
```

**5 Main LLM Call Types (SS13.1):**

- LLM-1 (SKETCH main): Generates rough plan structure from intent + discovery results
- LLM-2 (EXPAND main): Maps rough steps to concrete capabilities with parameters
- LLM-3 (VALIDATE arbiter): Evaluates validation issues when deterministic checks are ambiguous
- LLM-4a (HIL clarification): Generates clarification question for user
- LLM-4b (HIL approval draft): Generates approval summary for user review

**3 Micro-Replan Variants (SS13.1):**

- LLM-M1 (MICRO_SKETCH): Generates partial replan from remaining steps
- LLM-M2 (MICRO_EXPAND): Remaps affected steps to capabilities
- LLM-M3 (MICRO_VALIDATE): Validates replan against original plan constraints

**Token Tracking (SS13.3.3):**

After each LLM call, actual usage is accumulated:

```python
self._stage_token_usage[stage] += hub_response.metadata.usage.total_tokens
```

Reported in PLAN_END delta as `stage_token_usage: Dict[PlanStage, int]`.

**Enforcement Boundary:**

Model Hub enforces `max_tokens` and `timeout_ms` -- if the LLM generates beyond `max_tokens`, Model Hub truncates. If the call exceeds `timeout_ms`, Model Hub raises timeout. Planner trusts Model Hub for enforcement; Planner is responsible only for declaration (SS13.3.2).

### Rationale

Declarative budgets with centralized injection provide:

- Single source of truth for budget configuration (PlannerConfig)
- Consistent enforcement via Model Hub (no Planner-side token counting required)
- Per-stage visibility for cost analysis and optimization
- Clear separation: Planner declares intent, Model Hub enforces limits

---

## Alternatives Considered

### Alternative 1: Global Token Pool

**Description:** Single shared budget of ~3,584 tokens across all stages. Each call deducts from the pool.

**Pros:**

- Flexible allocation -- SKETCH can use more if EXPAND uses less

**Cons:**

- Greedy SKETCH can starve EXPAND/VALIDATE
- No per-stage observability
- Recovery logic complex when pool exhausted mid-pipeline

**Rejected because:** Per-stage budgets provide predictable resource allocation and simpler reasoning about failure modes.

### Alternative 2: Planner-Side Token Counting

**Description:** Planner counts tokens in prompts and responses, enforcing budget before sending to Model Hub.

**Pros:**

- Budget enforcement happens closer to the source

**Cons:**

- Requires tokenizer in Planner (dependency on model-specific tokenization)
- Duplicates Model Hub enforcement
- Token counting is approximate (prompt tokens vs completion tokens)

**Rejected because:** Model Hub already has the tokenizer and enforcement logic. Duplicating it in Planner adds complexity without benefit.

---

## Consequences

### Positive

- Every LLM call has explicit, auditable budget constraints
- Per-stage tracking enables cost optimization and anomaly detection
- Centralized injection in PipelineController prevents budget omission
- PLAN-11 invariant (SS13.3) is structurally enforced

### Negative

- Fixed per-stage budgets may be suboptimal for some request types (long intents may need more SKETCH tokens)
- V1 does not support adaptive budget reallocation between stages

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| SKETCH truncation on complex intents | Med | Med | Monitor truncation rate; V2 may add adaptive SKETCH budget |
| Model Hub timeout misalignment | Low | Med | PipelineController reads timeout from PlannerConfig, not hardcoded |
| Missing constraints on new LLM call type | Low | High | Contract test verifies all HubRequest objects carry non-null constraints |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
| --------- | ---- | ----------- |
| PipelineController | `k1/planner/pipeline_controller.py` [F03] | New -- _build_hub_request(), stage_budgets lookup |
| PlannerConfig | `k1/planner/config.py` [F07] | New -- stage_budgets dict, StageBudget dataclass |
| StageContext | `k1/planner/types.py` [F05] | New -- stage_token_usage accumulator |
| DeltaPayload | `k1/planner/types.py` [F05] | New -- stage_token_usage field in delta |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
| ----------- | --------- | ----------- |
| `k1.planner.delta.v1` | Emitted | Contains stage_token_usage in PLAN_END delta |

### Contracts Affected

| Contract | Type | Change |
| -------- | ---- | ------ |
| `module.contract.yaml` | Module | Declares LLM budget table and PLAN-11 invariant |
| `wiring.contract.yaml` | Module Wiring | ILLMPort required for SKETCH, EXPAND, VALIDATE stages |

### Port/Adapter Impact

| Port | Adapter | Change |
| ---- | ------- | ------ |
| `ILLMPort` | `LLMAdapter` | Existing -- receives HubRequest with constraints stamped by PipelineController |

### Success Metrics

- 100% of HubRequest objects carry non-null `constraints` (contract test)
- Per-stage token usage reported in every PLAN_END delta
- Token truncation rate < 5% of SKETCH calls under normal workload

### Testing Strategy

- [ ] Contract test: all HubRequest.constraints fields non-null (PLAN-11 enforcement)
- [ ] Unit test: PipelineController._build_hub_request() stamps correct budget per stage
- [ ] Unit test: stage_token_usage accumulation across multiple LLM calls
- [ ] Integration test: end-to-end plan with token tracking in delta payload

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial decision -- per-stage LLM budget enforcement |
