---
adr_id: ORCH-001
title: "Blind DAG Executor Supersedes Contract-Net Protocol"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "FAB-005"
  - "ORCH-002"
  - "ORCH-003"
  - "ORCH-004"
related_events:
  - "k1.orchestration.task.accepted.v1"
  - "k1.orchestration.dag.started.v1"
  - "k1.orchestration.step.started.v1"
  - "k1.orchestration.step.completed.v1"
  - "k1.orchestration.dag.completed.v1"
  - "k1.orchestration.delta.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
related_ports:
  - "IMailboxPort"
  - "IFabricGatewayPort"
  - "IPlannerPort"
  - "IStateReadPort"
  - "IDeltaEmitPort"
  - "IBridgeWritePort"
  - "IEventSubscriptionPort"
  - "IWorkflowStoragePort"
implements_issue: "1.1.1"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - dag
  - contract-net
  - supersession
  - foundation
---

# ORCH-001: Blind DAG Executor Supersedes Contract-Net Protocol

## Context

### Problem Statement

ADR-0006 established a 3-Phase Orchestration model using the Contract-Net Protocol (Smith, 1980) for agent selection: Task Announcement, Agent Bidding, Winner Selection. This protocol assumed a static pool of 58 agents that self-evaluate and submit competitive bids, with the Orchestrator scoring bids via a weighted function to select winners.

The Capability Fabric (FAB-005) has fundamentally replaced the capability resolution and execution model. Fabric centralizes all resolution (registry lookup + semantic retrieval + deterministic ranking) and all execution (6 provider types via `Fabric.execute(CapabilityRequest)`). The Contract-Net's negotiation and bidding phases are now redundant -- Fabric handles capability discovery and provider selection without broadcast, without bidding, and without agent self-evaluation.

The Orchestrator must evolve from a negotiation coordinator into a **Blind DAG Executor** -- a pure deterministic actor that mechanically walks dependency graphs by calling Fabric per step.

### Current Situation (ADR-0006)

| Phase | ADR-0006 Behavior | Latency |
|-------|-------------------|---------|
| Phase 1: Negotiation | Broadcast TaskAnnouncement to all ACTIVE agents, collect Proposals within 50ms deadline | ~20-50ms |
| Phase 2: Selection | Evaluate proposals with weighted scoring (confidence, latency, cost, parallelism, track record) | <5ms |
| Phase 3: Execution | Award task to winner(s), execute DAG with parallel waves, MapReduce barriers | ~150-200ms |

**What ADR-0006 got right (preserved):**
- DAG-based parallel execution with dependency waves (Phase 3)
- Topological sort for execution ordering
- Saga pattern for compensation (via ADR-0008)
- Orchestrator as pure deterministic actor (no LLM)

**What ADR-0006 assumed incorrectly (superseded):**
- Agents bid competitively for tasks (replaced by Fabric deterministic resolution)
- Orchestrator broadcasts to all agents (replaced by Fabric registry direct lookup)
- Selection requires scoring proposals (replaced by Fabric soft ranking in retrieval)
- Agents are the only execution targets (Fabric supports 6 provider types: MCP, WASM, Bridge, Agent, Workflow, Concierge)

### Constraints

- Orchestrator remains a pure deterministic actor (ORCH-02: No LLM, ORCH-03: Zero tools)
- All capability operations route through Fabric (ORCH-04)
- Hexagonal architecture with 8 ports must be preserved
- DAG execution pattern from Phase 3 of ADR-0006 is retained and extended
- Must support both MEDIUM tier (1-2 direct Fabric calls) and HIGH tier (full DAG from Planner)

### Requirements

- Mechanically execute DAG plans received from Planner (HIGH) or built inline (MEDIUM)
- Topological wave execution with parallel steps per wave
- Parameter reference resolution between steps (`$step_id.result.path`)
- Retry policy (2 retries per step, ORCH-06)
- Dependent cancellation on parent failure, independent continuation (ORCH-07)
- Saga compensation for side-effect rollback (strict reverse order, per ORCH-008)
- 6 adaptive extensions (Output Schema Guard, Conditional Edges, Micro-Replan, Token Budget Tracker, Quality Gate, Execution Monitor) -- all deterministic, no LLM

---

## Decision

### Chosen Approach

The Orchestrator is a **Blind DAG Executor** -- a pure deterministic actor (Layer 2) that:

1. **Receives instructions** via mailbox (TaskEnvelope from Concierge, CommittedPlan from Planner, WorkflowRunRequest from Scheduler)
2. **Walks the DAG** step by step in topological wave order
3. **Calls Fabric** per step via `IFabricGatewayPort.execute(CapabilityRequest)` -- never calls providers directly
4. **Aggregates results** into `AggregatedResult` and returns to Concierge
5. **Manages workflows** (saved plans as cron/event-driven tasks)
6. **Hosts connectors** (MCP server tool discovery and Fabric registration)

Phases 1 and 2 of ADR-0006 (Negotiation and Selection) are **fully eliminated**. Fabric handles all capability discovery, resolution, and provider selection. Phase 3 (Execution) is **retained and extended** with 6 agent-aware adaptive extensions.

### Key Design

**Six Internal Services:**

| # | Service | Responsibility |
|---|---------|---------------|
| 1 | OrchestratorService | Central dispatch, message routing, result aggregation |
| 2 | DAGExecutor | Topological wave walk, parallel execution, adaptive extensions |
| 3 | StepRunner | Single-step Fabric call with retry policy |
| 4 | ConstraintResolver | Pre-execution validation, capability checks, HIL fallback |
| 5 | WorkflowEngine | Registry, compiler, scheduler, gap detection |
| 6 | ConnectorLifecycleManager | MCP discovery, registration bridge to Fabric |
| 7 | ErrorRouter | Error classification and routing across all adapters |

**Eight Hexagonal Ports:**

| Port | Direction | Purpose |
|------|-----------|---------|
| IMailboxPort | Inbound | MPSC queue with WFQ priority REALTIME |
| IFabricGatewayPort | Both | execute(), execute_batch(), spawn(), query_registry() |
| IPlannerPort | Outbound | request_plan(), await_plan(), micro_replan() |
| IStateReadPort | Inbound | Read-only SessionState snapshots (ORCH-01) |
| IDeltaEmitPort | Outbound | Fire-and-forget deltas + progress |
| IBridgeWritePort | Outbound | Fire-and-forget audit writes to K0 |
| IEventSubscriptionPort | Inbound | Subscribe to plan.ready, capability.*, workflow.trigger |
| IWorkflowStoragePort | Both | Workflow persistence (SQLite) |

**DAG Execution Flow (replaces Contract-Net):**

```
TaskEnvelope arrives at Orchestrator Mailbox
  |
  +-- MEDIUM tier: Build 1-2 CapabilityRequests directly, execute via Fabric
  |
  +-- HIGH tier:
        1. Build PlanRequest from envelope
        2. Send to Planner via IPlannerPort (event-driven, non-blocking)
        3. Planner returns CommittedPlan via k1.planner.plan.ready.v1
        4. DAGExecutor.execute(CommittedPlan):
             a. build_waves(steps, dependencies) -- topological sort into parallel batches
             b. For each wave:
                  - resolve_params() -- substitute $step_id.result.path references
                  - evaluate_conditions() -- ORCH-16 conditional edges
                  - check_token_budget() -- ORCH-14 cumulative token tracking
                  - execute_batch(wave_steps) via IFabricGatewayPort
                  - validate_output() -- ORCH-15 schema guard
                  - check_quality() -- quality gate
                  - check_discoveries() -- ORCH-13 micro-replan trigger
             c. On step failure: retry (2x), then cancel dependents (ORCH-07)
             d. On side-effect failure: Saga compensation in reverse order
        5. aggregate(step_results) -> AggregatedResult
        6. Return to Concierge
```

**Tier Involvement:**

| Tier | Orchestrator? | Path |
|------|---------------|------|
| LOW | No | Concierge calls Fabric directly |
| MEDIUM | Yes | TaskEnvelope -> 1-2 Fabric calls, no planning |
| HIGH | Yes | TaskEnvelope -> PlanRequest -> Planner -> CommittedPlan -> DAG execution |
| CRISIS | No | Safety Agent handles immediately |

### Rationale

1. **Fabric eliminated the need for negotiation.** Fabric's CapabilityRegistry provides O(1) name lookup and semantic retrieval -- no need for agents to self-evaluate and bid. Resolution is centralized, deterministic, and sub-millisecond.

2. **6 provider types exceed agent-only model.** ADR-0006 assumed only actor-based agents. Fabric handles MCP tools, WASM sandboxes, Bridge services, Agents, Workflows, and Concierge providers. Broadcasting to "all agents" is meaningless when half the execution targets are not agents.

3. **Orchestrator complexity reduced.** Removing negotiation and selection eliminates ~40% of ADR-0006's logic. The Orchestrator becomes simpler, faster, and more testable.

4. **DAG execution pattern proven.** Phase 3 of ADR-0006 (parallel DAG with barriers) is well-established in Apache Airflow, Temporal.io, and LangGraph. Extending it with 6 adaptive guards for LLM agent non-determinism is the right evolution.

5. **Latency budget recovered.** ADR-0006 allocated 50-80ms for negotiation + selection. Eliminating these phases gives that budget back to actual execution.

---

## Alternatives Considered

### Alternative 1: Keep Contract-Net with Fabric Backend

**Description:** Preserve negotiation and bidding phases but route winning bids through Fabric instead of direct agent calls.

**Pros:**
- Preserves familiar negotiation pattern
- Agents can still self-evaluate capability match

**Cons:**
- Redundant: Fabric already resolves capabilities deterministically
- Added latency (50-80ms) for zero benefit
- Agents bidding implies agents are the only execution target (false with 6 provider types)

**Rejected because:** Fabric's registry + soft ranking is strictly superior to agent self-evaluation for capability matching. Bidding adds latency without improving selection quality.

### Alternative 2: Hybrid Model (Negotiate for Complex, Direct for Simple)

**Description:** Use Contract-Net for HIGH-tier multi-step plans but skip negotiation for MEDIUM-tier single-capability calls.

**Pros:**
- Gradual migration path
- Complex plans benefit from agent self-evaluation

**Cons:**
- Two execution paths to maintain
- Complex plans are exactly where Fabric's registry shines (multi-capability resolution)
- Agents don't have better information than Fabric's registry about available capabilities

**Rejected because:** Fabric's resolution quality does not degrade with plan complexity. Having two execution paths doubles testing surface for no quality improvement.

### Alternative 3: Orchestrator as Smart Router (Add LLM Reasoning)

**Description:** Give Orchestrator LLM capability to reason about execution strategy, retry logic, and step ordering.

**Pros:**
- More adaptive to unexpected situations
- Can reason about step quality and alternatives

**Cons:**
- Violates ORCH-02 (No LLM) -- fundamental identity invariant
- Adds latency (LLM inference 150-500ms per reasoning step)
- Non-deterministic behavior makes testing unreliable
- Increased cost per DAG execution

**Rejected because:** The Orchestrator's value is in being deterministic, fast, and testable. LLM reasoning belongs in the Planner (Stage 1 Sketch) and in agents (via Fabric). Adding LLM to the execution layer creates unpredictable behavior exactly where predictability matters most.

---

## Consequences

### Positive

- Orchestrator overhead drops from ~80ms (negotiate + select + execute overhead) to <18ms (pure DAG walk)
- Single execution path for all tiers (Fabric.execute per step)
- 6 adaptive extensions handle LLM agent non-determinism without compromising determinism
- Simpler codebase: 7 services instead of negotiator + scorer + executor + 7 services
- Hexagonal architecture enables independent testing via 8 port interfaces
- Workflow engine (saved plans) and connector ecosystem (MCP) are clean additions on top of DAG executor

### Negative

- Agents lose the ability to self-evaluate and decline tasks (Fabric decides provider suitability)
- No competitive bidding means no dynamic load-based selection (Fabric uses static health + success rate)
- Tighter coupling to Fabric API (all steps route through single gateway)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Fabric becomes bottleneck | Low | High | Thread-safe registry, circuit breakers, per-step timeout |
| DAG execution too rigid | Medium | Medium | 6 adaptive extensions + micro-replan (ORCH-13) |
| Loss of agent self-knowledge | Low | Low | Fabric registry populated from agent contracts (YAML declarations) |
| MCP connector isolation gaps | Medium | Medium | Fabric owns execution isolation (CircuitBreaker + OutputValidation) |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| OrchestratorService | `k1/orchestrator/orchestration/orchestrator_service.py` | New |
| DAGExecutor | `k1/orchestrator/orchestration/dag_executor.py` | New |
| StepRunner | `k1/orchestrator/orchestration/step_runner.py` | New |
| ConstraintResolver | `k1/orchestrator/orchestration/constraint_resolver.py` | New |
| WorkflowEngine | `k1/orchestrator/workflows/workflow_engine.py` | New |
| ConnectorLifecycleManager | `k1/orchestrator/connectors/connector_manager.py` | New |
| ErrorRouter | `k1/orchestrator/orchestration/error_router.py` | New |
| 8 Port Interfaces | `k1/orchestrator/ports/*.py` | New |
| 16 Adapters (8 prod + 8 test) | `k1/orchestrator/adapters/*.py` | New |
| Core Types | `k1/orchestrator/types.py` | New |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.orchestration.task.accepted.v1` | Emitted | TaskEnvelope accepted for processing |
| `k1.orchestration.dag.started.v1` | Emitted | DAG execution initiated |
| `k1.orchestration.step.started.v1` | Emitted | Individual step dispatched to Fabric |
| `k1.orchestration.step.completed.v1` | Emitted | Step completed (success or failure) |
| `k1.orchestration.dag.completed.v1` | Emitted | DAG execution finished with AggregatedResult |
| `k1.orchestration.delta.v1` | Emitted | Progress deltas to Concierge |
| `k1.planner.plan.ready.v1` | Consumed | CommittedPlan ready from Planner |
| `k1.planner.plan.failed.v1` | Consumed | Planning failed (degrade HIGH -> MEDIUM) |
| `k1.hil.override_response.v1` | Consumed | User override during execution |
| `k1.hil.fallback_response.v1` | Consumed | User response to HIL constraint question |
| `k1.workflow.trigger.due` | Consumed | Scheduled workflow trigger |
| `k1.fabric.capability.registered.v1` | Consumed | New capability available (gap detection) |
| `k1.fabric.capability.unregistered.v1` | Consumed | Capability removed (gap detection) |

### Contracts Affected

| Contract | Type | Change |
|----------|------|--------|
| `k1/contracts/schemas/modules/orchestrator/module.contract.yaml` | Module | New -- defines Orchestrator module boundary |
| ADR-0006 | Legacy ADR | Superseded by this decision |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IMailboxPort` | `MailboxAdapter` / `TestMailboxAdapter` | New (replaces Contract-Net broadcast) |
| `IFabricGatewayPort` | `FabricGatewayAdapter` / `MockFabricAdapter` | New (replaces direct agent calls) |
| `IPlannerPort` | `PlannerAdapter` / `MockPlannerAdapter` | New |
| `IStateReadPort` | `StateReadAdapter` / `MockStateReadAdapter` | New (read-only, ORCH-01) |
| `IDeltaEmitPort` | `DeltaEmitAdapter` / `TestDeltaAdapter` | New |
| `IBridgeWritePort` | `BridgeWriteAdapter` / `MockBridgeAdapter` | New |
| `IEventSubscriptionPort` | `EventSubscriptionAdapter` / `TestEventAdapter` | New |
| `IWorkflowStoragePort` | `SQLiteWorkflowAdapter` / `TestWorkflowAdapter` | New |

### Success Metrics

- Orchestrator overhead <18ms P99 (excl. Fabric + Planner)
- Zero LLM calls from Orchestrator (ORCH-02 compliance)
- Zero SessionState writes from Orchestrator (ORCH-01 compliance)
- All step executions routed through Fabric (ORCH-04 compliance)
- DAG execution correctness validated by ~470 tests

### Testing Strategy

- [ ] Unit tests in `tests/k1/orchestrator/` (~380 tests across 7 services)
- [ ] Integration tests (5 core + 7 advanced scenarios)
- [ ] Contract tests (4 port interface validations)
- [ ] Cross-subsystem tests (3 multi-component flows)
- [ ] Performance benchmarks (2 load scenarios)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- Blind DAG Executor supersedes ADR-0006 Contract-Net |
