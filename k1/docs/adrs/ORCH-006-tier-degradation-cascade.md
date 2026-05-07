---
adr_id: ORCH-006
title: "Tier Degradation Cascade -- Error Classification and Handoff Protocol"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-004"
# Originally referenced ADR-0028 (legacy K0 ADR, not migrated to K1).
related_events:
  - "k1.orchestration.dag.completed.v1"
  - "k1.orchestration.task.degraded.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IFabricGatewayPort"
  - "IPlannerPort"
  - "IMailboxPort"
implements_issue: "1.1.6"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - tier-degradation
  - error-classification
  - circuit-breaker
---

# ORCH-006: Tier Degradation Cascade -- Error Classification and Handoff Protocol

## Context

### Problem Statement

When Orchestrator encounters adapter failures (Fabric timeout, Planner circuit-breaker open, StateRead unavailable), the system must degrade gracefully rather than fail entirely. A clear protocol is needed to define:

1. Who CLASSIFIES errors (Orchestrator ErrorRouter)
2. Who DECIDES degradation (Concierge FabricOrchestratorAdapter)
3. What information flows between them

### Current Situation

The Concierge MMD defines TIER_DEGRADATION spec where Concierge's FabricOrchestratorAdapter owns degradation decisions. Circuit breakers (CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP) live on the Concierge side. Orchestrator must report error severity accurately so Concierge can act.

### Constraints

- Orchestrator is a blind executor -- it does NOT make tier decisions (ORCH-02, no LLM)
- Circuit breakers are owned by Concierge's FabricOrchestratorAdapter, not by Orchestrator
- Orchestrator must report severity via AggregatedResult, not take degradation action
- ErrorRouter must classify ALL adapter errors into the 3-level severity taxonomy (RECOVERABLE, DEGRADED, TERMINAL)

### Requirements

- ErrorRouter classifies every adapter error before surfacing it
- AggregatedResult carries error severity for Concierge consumption
- Orchestrator handles RECOVERABLE errors internally (retry/fallback)
- Orchestrator reports DEGRADED/TERMINAL errors to Concierge via result
- No error from any adapter bypasses ErrorRouter classification

---

## Decision

### Chosen Approach

**Split-responsibility model: Orchestrator CLASSIFIES, Concierge DECIDES.**

### Key Design

**Error Classification Matrix:**

| Adapter | Error Type | Severity | Orchestrator Action | Concierge Action |
|---------|-----------|----------|-------------------|------------------|
| IMailboxPort | Dequeue failure | RECOVERABLE | Re-enqueue once | None (transparent) |
| IFabricGatewayPort | Step execution failure | DEGRADED | Step fails, independent steps continue | Record step failure in turn |
| IFabricGatewayPort | CB_FABRIC OPEN | DEGRADED | Capability unavailable, skip step | Degrade HIGH to MEDIUM |
| IPlannerPort | Planning failure | DEGRADED | Return partial result (no plan) | Degrade HIGH to MEDIUM |
| IPlannerPort | CB_PLANNER OPEN | DEGRADED | Skip planning, return immediately | Degrade HIGH to MEDIUM |
| IStateReadPort | Snapshot failure | DEGRADED | Use stale/empty context | Log degraded context |
| IDeltaEmitPort | Delta emit failure | RECOVERABLE | Retry once, then silent drop | None (best-effort) |
| IBridgeWritePort | Audit write failure | RECOVERABLE | Retry once, then silent drop | None (fire-and-forget) |
| IEventSubscriptionPort | Subscribe failure | RECOVERABLE | Resubscribe | None (transparent) |

**Degradation Cascade:**

```text
HIGH Tier Path:
  TaskEnvelope(HIGH) -> Orchestrator -> PlanRequest -> Planner
    If CB_PLANNER OPEN:
      ErrorRouter classifies as DEGRADED
      AggregatedResult.success = false
      AggregatedResult includes AdapterError{severity=DEGRADED, adapter="planner", fallback_action="SKIP_PLANNING"}
      -> Concierge receives AggregatedResult
      -> Concierge FabricOrchestratorAdapter sees DEGRADED + SKIP_PLANNING
      -> Concierge DECIDES: re-dispatch as MEDIUM tier (1-2 direct Fabric calls)

MEDIUM Tier Path:
  TaskEnvelope(MEDIUM) -> Orchestrator -> Fabric.execute()
    If CB_FABRIC OPEN or CB_ORCHESTRATOR OPEN:
      ErrorRouter classifies as DEGRADED
      AggregatedResult.success = false
      -> Concierge receives AggregatedResult
      -> Concierge DECIDES: degrade to LOW (Concierge calls Fabric directly, bypassing Orchestrator)
```

**ErrorRouter Protocol:**

```python
class ErrorRouter:
    def route_error(self, error: AdapterError) -> ErrorAction:
        """Classify and determine orchestrator-local action."""
        match error.severity:
            case ErrorSeverity.RECOVERABLE:
                return ErrorAction(retry=True, max_retries=1, propagate=False)
            case ErrorSeverity.DEGRADED:
                return ErrorAction(retry=False, propagate=True,
                                   include_in_result=True)
            case ErrorSeverity.TERMINAL:
                return ErrorAction(retry=False, propagate=True,
                                   abort_dag=True, compensate=True)
```

**AggregatedResult Error Reporting:**

AggregatedResult carries a list of AdapterError objects. Concierge inspects:
- `success == false` + any AdapterError with `fallback_action == "SKIP_PLANNING"` -> degrade HIGH to MEDIUM
- `success == false` + any AdapterError with `severity == TERMINAL` -> degrade MEDIUM to LOW
- `success == false` + all errors RECOVERABLE -> retry (Concierge decision)

### Rationale

- Orchestrator stays deterministic -- it classifies but never makes tier decisions
- Concierge retains full authority over user-facing behavior changes
- ErrorRouter provides a single classification point, preventing scattered error handling
- AdapterError severity taxonomy is simple (3 levels) and extensible

---

## Alternatives Considered

### Alternative 1: Orchestrator Decides Degradation Internally

**Rejected because:** Violates separation of concerns. Orchestrator would need user context, conversation history, and policy knowledge to decide tier changes. This is Concierge's domain (L1 cognitive orchestration). Orchestrator is L2 mechanical execution.

### Alternative 2: Circuit Breakers Inside Orchestrator

**Rejected because:** Duplicates Concierge's CB infrastructure. Circuit breaker state (open/half-open/closed) needs to be shared across retries and affects routing decisions. Concierge's FabricOrchestratorAdapter already owns these CBs. Orchestrator sees CB_OPEN as an adapter error to classify, not a state to manage.

### Alternative 3: Event-Based Degradation Notification

**Rejected because:** Adds latency and complexity. Direct AggregatedResult reporting is synchronous (Concierge gets result immediately) and sufficient. An event-based notification would require Concierge to correlate events with pending tasks, adding unnecessary indirection.

---

## Consequences

### Positive

- Clean separation: classify (Orchestrator) vs. decide (Concierge)
- Single classification point (ErrorRouter) prevents inconsistent error handling
- AggregatedResult is self-contained -- Concierge needs no additional queries

### Negative

- Concierge must inspect AdapterError list in AggregatedResult (minor parsing overhead)
- Degradation latency includes full Orchestrator round-trip (error -> classify -> result -> Concierge)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ErrorRouter misclassifies severity | Low | High | Exhaustive classification matrix, integration tests per adapter |
| Concierge ignores degradation signals | Low | Medium | Contract test: AggregatedResult with DEGRADED triggers tier change |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| ErrorRouter | `k1/orchestrator/orchestration/error_router.py` | New |
| AdapterError + ErrorSeverity | `k1/orchestrator/types.py` | New |
| AggregatedResult (error list) | `k1/orchestrator/types.py` | New |
| PlannerAdapter (CB_PLANNER handling) | `k1/orchestrator/adapters/planner_adapter.py` | New |
| FabricGatewayAdapter (CB_FABRIC handling) | `k1/orchestrator/adapters/fabric_gateway_adapter.py` | New |

### Success Metrics

- All adapter errors routed through ErrorRouter (zero unclassified exceptions)
- Concierge correctly degrades HIGH to MEDIUM when CB_PLANNER is OPEN
- Concierge correctly degrades MEDIUM to LOW when CB_ORCHESTRATOR is OPEN

### Testing Strategy

- [ ] Unit tests: ErrorRouter classification for all 9 adapter error types
- [ ] Integration tests: AggregatedResult carries correct severity per failure scenario
- [ ] Contract tests: Concierge acts on DEGRADED AggregatedResult correctly

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- split-responsibility degradation model |
