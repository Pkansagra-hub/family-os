---
adr_id: PLAN-004
title: "HIL Coordination Protocol"
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
  - "ORCH-005"
related_events:
  - "k1.hil.clarification.v1"
  - "k1.hil.clarification_response.v1"
  - "k1.hil.approval_request.v1"
  - "k1.hil.approval_response.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/schemas/events/planner/hil_clarification.v1.json"
  - "k1/contracts/schemas/events/planner/hil_approval.v1.json"
related_ports:
  - "ILLMPort"
  - "IEventPort"
implements_issue: "1.1.6"
superseded_by: ""
tags:
  - planner
  - hil
  - human-in-the-loop
  - clarification
  - approval
  - coordination
---

# PLAN-004: HIL Coordination Protocol

## Context

### Problem Statement

The Planner must interact with users during planning when intent is ambiguous or when a plan carries high-risk side effects. These human-in-the-loop (HIL) interactions must be bounded to prevent planning from stalling indefinitely, and must be clearly separated from execution-time HIL interactions owned by the Orchestrator.

### Current Situation

planner.md SS12 defines two HIL interaction points: clarification during SKETCH (SS12.2) and approval during VALIDATE (SS12.3). The Concierge module mediates the user-facing interaction. HIL events flow over the event bus; the Planner emits requests and subscribes to responses.

### Constraints

- PLAN-10: Max 2 HIL rounds total per plan (SS12.1) -- prevents infinite clarification loops
- HIL events are distinct from execution-time HIL events (SS12.1 namespace split)
- Planning-time: `k1.hil.clarification.*` and `k1.hil.approval_*.*`
- Execution-time: `k1.hil.override.*` and `k1.hil.fallback.*` (Orchestrator-owned)
- Micro-replan has no HIL interaction (PLAN-003)
- HIL uses LLM calls (LLM-4a, LLM-4b) which count against token tracking but have their own budget

### Requirements

- Clarification flow: emit question, await response, timeout after 60s
- Approval flow: emit summary with side effects, await approve/reject/modify, timeout after 120s
- Max 2 rounds total per plan (mix of clarification and approval)
- Clean timeout handling (best-effort on clarification timeout, PLAN_FAILED on approval timeout)
- Correlation via request_id across all HIL events

---

## Decision

### Chosen Approach

Two HIL interaction points managed by HILCoordinator with PLAN-10 round budget (planner.md SS12).

### Key Design

**HILCoordinator Component:**

```
HILCoordinator
  deps: ILLMPort (generate HIL messages), IEventPort (publish/subscribe HIL events)
  state: _round_counter: int (max 2), _pending: Dict[str, asyncio.Future]
```

**Clarification Flow (Stage 1 SKETCH, SS12.2):**

Triggered when SketchService detects:

- Ambiguity in user intent (multiple valid interpretations)
- Multi-interpretation capability matches (>3 relevant capabilities with low confidence)
- Missing required context (key planning context fields are empty)

Protocol:

1. SketchService calls `hil_coordinator.request_clarification(question, context)`
2. HILCoordinator checks `_round_counter < 2`, increments counter
3. Generates clarification message via LLM-4a (ILLMPort)
4. Emits `k1.hil.clarification.v1{request_id, question, context, options}`
5. Creates `asyncio.Future` keyed by `request_id`
6. Awaits future with 60s timeout
7. On response (`k1.hil.clarification_response.v1`): resolve future, return user answer
8. On timeout: return `None` (SketchService proceeds with best-effort interpretation)

**Approval Flow (Stage 3 VALIDATE, SS12.3):**

Triggered when ValidateService determines:

- Plan has high-risk side effects (destructive operations, external API calls)
- Elevated safety band operations detected
- Estimated cost above configurable threshold

Protocol:

1. ValidateService calls `hil_coordinator.request_approval(summary, plan, side_effects)`
2. HILCoordinator checks `_round_counter < 2`, increments counter
3. Generates approval summary via LLM-4b (ILLMPort)
4. Emits `k1.hil.approval_request.v1{request_id, summary, options, side_effects, safety_assessment}`
5. Creates `asyncio.Future` keyed by `request_id`
6. Awaits future with 120s timeout
7. On `APPROVED`: return approved, continue to COMMIT
8. On `REJECTED`: return rejected, emit plan.failed.v1 with reason "user_rejected"
9. On `MODIFIED`: return modifications, re-run VALIDATE with user-modified plan
10. On timeout: return timeout, emit plan.failed.v1 with reason "approval_timeout"

**PLAN-10 Round Budget:**

```python
class HILCoordinator:
    MAX_ROUNDS = 2

    async def _check_budget(self) -> bool:
        if self._round_counter >= self.MAX_ROUNDS:
            return False  # budget exhausted, proceed without HIL
        self._round_counter += 1
        return True
```

If both rounds are consumed by clarification, no approval is possible. This is by design -- if intent requires 2 clarification rounds, the plan is unlikely to also need approval (user has already been engaged).

**Namespace Split (SS12.1):**

| Namespace | Owner | When |
| --------- | ----- | ---- |
| `k1.hil.clarification.*` | Planner HILCoordinator | Planning-time (SKETCH stage) |
| `k1.hil.approval_*.*` | Planner HILCoordinator | Planning-time (VALIDATE stage) |
| `k1.hil.override.*` | Orchestrator | Execution-time (DAG wave) |
| `k1.hil.fallback.*` | Orchestrator | Execution-time (step failure) |

### Rationale

Bounded HIL rounds prevent indefinite planning stalls. Event-driven protocol keeps the Planner's mailbox loop unblocked (HILCoordinator awaits a Future, not the mailbox). Clean namespace separation avoids cross-concern event confusion between planning and execution HIL.

---

## Alternatives Considered

### Alternative 1: Synchronous HIL via Concierge RPC

**Description:** Planner calls Concierge directly via an RPC port instead of event-driven HIL.

**Pros:**

- Simpler code (no Future management, no event subscription)
- Direct response without correlation

**Cons:**

- Blocks Planner's processing loop during HIL wait (up to 120s)
- Tight coupling between Planner and Concierge
- Violates event-driven architecture principle

**Rejected because:** Event-driven HIL keeps the Planner reactive. A 120s synchronous block would prevent cancel handling and other event processing.

### Alternative 2: Unlimited HIL Rounds

**Description:** No budget on HIL rounds. Keep asking until user is satisfied.

**Pros:**

- Maximum user engagement and plan quality

**Cons:**

- Planning time becomes unbounded
- User fatigue from excessive interaction
- Each round consumes LLM tokens
- Orchestrator timeout (45s CB_PLANNER) would fire before 3+ rounds complete

**Rejected because:** PLAN-10's 2-round budget aligns with the 45s Orchestrator circuit breaker. 2 rounds (60s + 60s worst case) already risk timeout; more rounds guarantee it.

---

## Consequences

### Positive

- Bounded planning time with user interaction
- Clean separation of planning-time vs execution-time HIL
- Event-driven protocol maintains Planner reactivity
- 2-round budget prevents infinite loops

### Negative

- Complex Future-based coordination in HILCoordinator
- 2-round budget may be insufficient for highly ambiguous requests
- Approval timeout causes PLAN_FAILED (no graceful degradation)

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| User does not respond within timeout | Med | Med | Clarification: best-effort. Approval: PLAN_FAILED with clear reason |
| Both rounds consumed by clarification | Low | Low | By design -- highly interactive requests get 2 clarification chances |
| Concierge fails to deliver HIL event | Low | High | Circuit breaker on event delivery; Future timeout acts as backstop |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
| --------- | ---- | ----------- |
| HILCoordinator | `k1/planner/services/hil_coordinator.py` [F26] | New -- clarification/approval flows, round budget |
| SketchService | `k1/planner/services/sketch_service.py` [F20] | Modified -- calls hil_coordinator.request_clarification |
| ValidateService | `k1/planner/services/validate_service.py` [F22] | Modified -- calls hil_coordinator.request_approval |
| PlannerConfig | `k1/planner/config.py` [F07] | New -- hil_clarification_timeout_ms, hil_approval_timeout_ms |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
| ----------- | --------- | ----------- |
| `k1.hil.clarification.v1` | Emitted | Clarification question for user |
| `k1.hil.clarification_response.v1` | Consumed | User's clarification response |
| `k1.hil.approval_request.v1` | Emitted | Plan approval request with side effects |
| `k1.hil.approval_response.v1` | Consumed | User's approval/rejection/modification |

### Contracts Affected

| Contract | Type | Change |
| -------- | ---- | ------ |
| `hil_clarification.v1.json` | Event Schema | New -- clarification request/response schema |
| `hil_approval.v1.json` | Event Schema | New -- approval request/response schema |
| `module.contract.yaml` | Module | Declares PLAN-10 invariant and HIL capability |

### Port/Adapter Impact

| Port | Adapter | Change |
| ---- | ------- | ------ |
| `IEventPort` | `EventAdapter` | Used for HIL event pub/sub |
| `ILLMPort` | `LLMAdapter` | Used for HIL message generation (LLM-4a, LLM-4b) |

### Success Metrics

- HIL clarification response rate > 80% (within 60s timeout)
- HIL approval response rate > 90% (within 120s timeout)
- Round budget exhaustion rate < 10% of plans with HIL interaction

### Testing Strategy

- [ ] Unit test: HILCoordinator round budget enforcement (3rd request rejected)
- [ ] Unit test: clarification timeout returns None (best-effort)
- [ ] Unit test: approval timeout causes PLAN_FAILED
- [ ] Unit test: approval REJECTED causes PLAN_FAILED with correct reason
- [ ] Integration test: full clarification round-trip with mock Concierge
- [ ] Contract test: HIL event schema validation

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial decision -- 2-round HIL coordination protocol |
