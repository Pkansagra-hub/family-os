# Milestone 1: Foundation -- Work Tickets

> **Module**: Orchestrator (Layer 2 in K1 Cognitive Architecture)
> **Milestone**: M1 -- Foundation
> **Goal**: Establish architectural decisions, define core types, and create message envelopes before any implementation code.
> **Prerequisite**: None (first milestone)
> **Estimated Epics**: 5 (1.1 ADRs, 1.2 Types, 1.3 Contracts, 1.4 Ports, 1.5 Event Schemas)
> **Estimated Issues**: 53+

---

## How to Use These Tickets

Each ticket is self-contained. Before starting:

1. Read **Context Files** listed in the ticket
2. Check **Blocked By** -- all listed tickets must be complete
3. Follow **Anti-Hallucination Rules** strictly
4. Verify all items in **Done When** checklist upon completion

---

## Epic 1.1: ADR Review & Creation

> ADRs are governance artifacts (Markdown), not code. No Python files for this epic.
> File location: `docs/architecture/decisions-K0/ORCH-001-*.md` through `ORCH-012-*.md`

---

### WT-1.1.1: Review ADR-0006 (Contract-Net -- Superseded)

**Deliverable**: `docs/architecture/decisions-K0/ORCH-001-blind-dag-supersedes-contract-net.md`

**Blocked By**: None

**Context Files**:

- `docs/architecture/decisions-K0/ADR-0006-*.md` (existing Contract-Net ADR)
- `k1/orchestrator/orchestrator.mmd` (Executive Summary -- "blind DAG executor")
- `docs/whiteboard/schema_whiteboard.md` (overview of Orchestrator identity)

**Specification**:
ADR-0006 defined Contract-Net Protocol. Now superseded by Blind DAG Executor. Create superseding ADR: ORCH-001-blind-dag-supersedes-contract-net.md. Document why Contract-Net was replaced, what Blind DAG means, and reference orchestrator.mmd.

**Anti-Hallucination Rules**:

- Do NOT create Python files for this ticket
- Do NOT implement any runtime behavior
- ADRs are Markdown documents that record decisions

**Done When**:

- [ ] File exists at `docs/architecture/decisions-K0/ORCH-001-blind-dag-supersedes-contract-net.md`
- [ ] ADR references ADR-0006 as superseded
- [ ] ADR explains Blind DAG Executor model
- [ ] ADR follows project ADR template format

---

### WT-1.1.2: Review ADR-0007 (4-Stage Planning) for Orchestrator Impact

**Deliverable**: ADR reviewed, notes documented

**Blocked By**: None

**Context Files**:

- `docs/architecture/decisions-K0/ADR-0007-*.md` (4-Stage Planning ADR)
- `k1/orchestrator/orchestrator.mmd` (S "CommittedPlan" sections)
- `docs/whiteboard/schema_whiteboard.md` (S10 -- Planner-Orchestrator protocol)

**Specification**:
Orchestrator receives CommittedPlan from Planner Stage 4. Confirm envelope schema, plan structure, dependency graph format align with ADR-0007.

**Anti-Hallucination Rules**:

- Do NOT create Python files
- Document findings as notes in ADR or separate review doc

**Done When**:

- [ ] ADR-0007 reviewed for Orchestrator impact
- [ ] CommittedPlan envelope schema confirmed compatible
- [ ] Dependency graph format confirmed (step_id -> [dep_ids])

---

### WT-1.1.3: Review ADR-0017 (Single Writer) for Orchestrator Compliance

**Deliverable**: ADR reviewed

**Blocked By**: None

**Context Files**:

- `docs/architecture/decisions-K0/ADR-0017-*.md` (Single Writer ADR)
- `k1/orchestrator/orchestrator.mmd` (ORCH-01 invariant)

**Specification**:
Confirm ORCH-01: Orchestrator has NO IStateWritePort. All state changes via IDeltaEmitPort -> DeltaBus -> Concierge.

**Done When**:

- [ ] ADR-0017 reviewed and compliance confirmed
- [ ] ORCH-01 (no writes) validated against Single Writer principle

---

### WT-1.1.4: Review ADR-0028 (Performance Scheduling) for Orchestrator

**Deliverable**: ADR reviewed

**Blocked By**: None

**Context Files**:

- `docs/architecture/decisions-K0/ADR-0028-*.md` (Performance Scheduling ADR)

**Specification**:
Map Orchestrator operations to WFQ priority classes. Mailbox: REALTIME. DAG waves: INTERACTIVE. Progress deltas: BACKGROUND.

**Done When**:

- [ ] ADR-0028 reviewed
- [ ] Priority mapping documented for Orchestrator operations

---

### WT-1.1.5: Create ADR -- Orchestrator Concurrency Model

**Deliverable**: `docs/architecture/decisions-K0/ORCH-005-concurrency-model.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "Concurrency" sections)
- `docs/whiteboard/schema_whiteboard.md` (S9 -- mailbox durability)

**Specification**:
Single-threaded mailbox processing loop. Parallelism only within DAG waves via execute_batch(). No concurrent DAG executions (V1). This ADR gates the `_mailbox_loop()` implementation (Epic 6.2) and `ConcurrencyGuard` (3.2.9).

**Done When**:

- [ ] ADR file exists with concurrency model decision
- [ ] Single-threaded loop pattern documented
- [ ] Wave-level parallelism via asyncio documented
- [ ] No concurrent DAG execution (V1) stated

---

### WT-1.1.6: Create ADR -- Tier Degradation Cascade

**Deliverable**: `docs/architecture/decisions-K0/ORCH-006-tier-degradation.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "Tier Degradation")
- `docs/whiteboard/schema_whiteboard.md` (S7 -- circuit breakers)

**Specification**:
HIGH -> CB_PLANNER OPEN -> degrade to MEDIUM. MEDIUM -> CB_ORCHESTRATOR OPEN -> degrade to LOW. Owned by Concierge FabricOrchestratorAdapter but affects Orchestrator design. Gates ErrorRouter FALLBACK action (2.1.7) and PlannerAdapter CB_PLANNER (6.1.3).

**Done When**:

- [ ] ADR file exists with tier degradation cascade
- [ ] HIGH -> MEDIUM -> LOW path documented
- [ ] CB ownership (Concierge-side) clarified
- [ ] Impact on ErrorRouter documented

---

### WT-1.1.7: Create ADR -- Adaptive Blind DAG Extensions

**Deliverable**: `docs/architecture/decisions-K0/ORCH-007-adaptive-dag-extensions.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "Adaptive DAG Extensions")
- `docs/whiteboard/schema_whiteboard.md` (S8 -- guard pipeline G0-G10)

**Specification**:
6 deterministic extensions: Output Schema Guard (ORCH-15), Conditional Edges (ORCH-16), Micro-Replan (ORCH-13), Token Budget (ORCH-14), Quality Gate, Execution Monitor. All NO LLM. Gates all 8 guards in Epic 3.2.

**Done When**:

- [ ] ADR documents all 6 extensions
- [ ] Each extension confirmed deterministic (no LLM)
- [ ] ORCH invariant references included per extension

---

### WT-1.1.8: Create ADR -- Saga Compensation Ordering

**Deliverable**: `docs/architecture/decisions-K0/ORCH-008-saga-compensation.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.md` (S26 -- Open Q1)
- `k1/orchestrator/orchestrator.mmd` (S "Saga")

**Specification**:
Resolves Open Q1. Decision: strict reverse order (safest, deterministic). Compensations run sequentially in reverse execution order. Concurrent compensation rejected (V1). Affects Epic 2.2.5 Saga Recovery.

**Done When**:

- [ ] ADR documents LIFO compensation ordering
- [ ] Sequential (not concurrent) execution stated
- [ ] Open Q1 marked resolved

---

### WT-1.1.9: Create ADR -- Workflow Persistence Strategy

**Deliverable**: `docs/architecture/decisions-K0/ORCH-009-workflow-persistence.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.md` (S26 -- Open Q2)

**Specification**:
Resolves Open Q2. Decision: K1 SQLite LOCAL COLD for WorkflowRegistry + WorkflowScheduler trigger state. Edge-First: always available without K0. Schema: workflows, triggers, runs, gaps tables. Affects Epic 4.1 + 4.2.

**Done When**:

- [ ] ADR documents SQLite persistence decision
- [ ] Edge-First availability rationale included
- [ ] Table schema outlined (workflows, triggers, runs, gaps)
- [ ] Open Q2 marked resolved

---

### WT-1.1.10: Create ADR -- MCP Connector Security Model

**Deliverable**: `docs/architecture/decisions-K0/ORCH-010-mcp-security.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "MCP Connectors")

**Specification**:
Per-connector process isolation (V1). Resource limits: CPU/memory caps via OS process controls. Network: allowlist per connector config. No container/namespace isolation in V1. Audit: all MCP calls logged with trace_id. Affects Epic 5.1.4.

**Done When**:

- [ ] ADR documents process isolation model
- [ ] Resource limits strategy documented
- [ ] V1 scope limitations acknowledged
- [ ] Audit requirements stated

---

### WT-1.1.11: Create ADR -- Open Questions Resolution Batch

**Deliverable**: `docs/architecture/decisions-K0/ORCH-011-open-questions.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.md` (S26 -- all open questions Q3-Q11)
- `docs/whiteboard/schema_whiteboard.md` (all sections for cross-ref)

**Specification**:
Resolves remaining Open Questions from orchestrator.md S26:

- Q3: MCP health = passive (CB_MCP tracks failures), active for critical tools
- Q4: Re-read safety_band at wave boundary, trust rest
- Q5: Single active run per workflow (V1), abort previous
- Q6: Parent overrides take precedence for sub-workflow params
- Q7: Per-step cost metering via CapabilityResult.cost_usd accumulation
- Q8: Conservative discovery heuristic (exact field match V1)
- Q9: Quality thresholds 0.3/0.7 hardcoded V1, configurable V1.5
- Q10: Simple comparisons only V1 (no function calls in conditions)
- Q11: Sub-step event rate limit max 1 per step per 500ms

**Done When**:

- [ ] ADR documents all 9 resolved questions (Q3-Q11)
- [ ] Each question has decision + rationale
- [ ] Cross-references to affected epics included

---

### WT-1.1.12: Create ADR -- Event-Driven Concurrency for HIGH Tier

**Deliverable**: `docs/architecture/decisions-K0/ORCH-012-event-driven-high-tier.md`

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "dispatch_high" and "Event-Driven" sections)
- `docs/whiteboard/schema_whiteboard.md` (S10 -- Planner-Orchestrator protocol)

**Specification**:
Resolves ARCH-1 (await_plan blocking). Decision: Event-driven model. dispatch_high() sends PlanRequest to Planner, parks TaskEnvelope context in PendingPlanContext store (keyed by request_id), returns to mailbox loop immediately. CommittedPlan arrives as mailbox message via k1.planner.plan.ready.v1. Timeouts: PlanRequest 45s, HIL Constraint 60s, HIL Override 30s. Timeout reaper runs every 5s. Gates dispatch_high (2.1.4), HIL fallback (3.1.5), mailbox loop (6.2.5).

**Done When**:

- [ ] ADR documents event-driven async pattern
- [ ] PendingPlanContext store mechanism described
- [ ] Timeout values and reaper interval stated
- [ ] Two-phase flow (dispatch_high -> receive_plan) documented
- [ ] Impact on mailbox loop non-blocking property explained

---

## Epic 1.2: Core Types & Message Envelopes

> **ALL types go in `k1/orchestrator/types.py`** (single file). Exception: events in `k1/orchestrator/events.py`, config in `k1/orchestrator/config.py`.
> **Anti-Hallucination**: All types are pure dataclasses with NO I/O, NO port references, NO service logic. Do NOT add async methods. Do NOT import from `k1.orchestrator.orchestration/*`.
> **Import graph**: `k1.orchestrator.types` imports from `k1.fabric.types` (Tier, CapabilityRequest, CapabilityResult) but NEVER from any service or port module.

---

### WT-1.2.1: TaskEnvelope Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add TaskEnvelope class)

**Blocked By**: None

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "TaskEnvelope")
- `docs/whiteboard/schema_whiteboard.md` (S1 -- ProcessingContext, for trace_id pattern)
- `k1/fabric/types.py` (Tier enum for validation reference)

**Specification**:
`@dataclass(frozen=True)`. Fields: `envelope_id: str, intent: str, context: Dict[str, Any], tier: str, capabilities: List[str], params: Dict[str, Dict[str, Any]], constraints: Dict[str, Any], trace_id: str, caller_id: str, timeout_ms: int`. Defaults: envelope_id=uuid4(), tier="MEDIUM", capabilities=[], params={}, constraints={}, timeout_ms=30000. Validation (`__post_init__`): tier in {"MEDIUM", "HIGH"} (LOW/CRISIS never reach Orchestrator); intent non-empty; trace_id non-empty; if tier=MEDIUM then capabilities non-empty and len<=2 (ORCH-10); if tier=HIGH then capabilities may be empty. Params keyed by capability_name.

**Example**:

```json
{
  "envelope_id": "550e8400-e29b-41d4-a716-446655440000",
  "intent": "Find meetings for next week",
  "context": {"session_id": "abc123"},
  "tier": "MEDIUM",
  "capabilities": ["tool.calendar.search"],
  "params": {"tool.calendar.search": {"query": "next week meetings"}},
  "constraints": {},
  "trace_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "caller_id": "concierge",
  "timeout_ms": 30000
}
```

**Done When**:

- [ ] TaskEnvelope dataclass in `k1/orchestrator/types.py`
- [ ] `@dataclass(frozen=True)` decorator applied
- [ ] All 10 fields with correct types and defaults
- [ ] `__post_init__` validation: tier in {"MEDIUM","HIGH"}, intent non-empty, trace_id non-empty, MEDIUM capabilities non-empty + len<=2
- [ ] No I/O, no imports from services/ports

---

### WT-1.2.2: PlanRequest Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add PlanRequest class)

**Blocked By**: WT-1.2.1 (shares file)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10.1-10.2 -- Planner-Orchestrator request protocol)
- `k1/orchestrator/orchestrator.mmd` (S "PlanRequest")

**Specification**:
`@dataclass(frozen=True)`. Fields: `request_id: str, intent: str, constraints: Dict[str, Any], context: ContextSnapshot, trace_id: str, timeout_ms: int`. Defaults: request_id=uuid4(), constraints={}, timeout_ms=45000. Validation: intent non-empty; trace_id non-empty. Key contract: request_id is NEW (not envelope_id) -- echoed back by Planner in CommittedPlan.request_id for PendingPlanContext correlation.

**Done When**:

- [ ] PlanRequest dataclass in types.py
- [ ] request_id defaults to uuid4()
- [ ] timeout_ms defaults to 45000 (CB_PLANNER)
- [ ] Validation: intent non-empty, trace_id non-empty

---

### WT-1.2.3: CommittedPlan Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add CommittedPlan class)

**Blocked By**: WT-1.2.18 (PlanStep must be defined)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10.3 -- CommittedPlan reconciliation table)
- `k1/orchestrator/orchestrator.mmd` (S "CommittedPlan")

**Specification**:
`@dataclass(frozen=True)`. Fields: `plan_id: str, request_id: str, intent: str, steps: List[PlanStep], dependencies: Dict[str, List[str]], token_budget_max: int, cost_budget_max_usd: Optional[float], created_at: float, trace_id: str`. Dependencies format: {"s2": ["s1"], "s3": ["s1", "s2"]}. Validation: plan_id non-empty; request_id non-empty (required for PendingPlanContext correlation per WB S10.3); steps non-empty; dependency keys must be subset of step IDs; no cycles in dependency graph. Provide from_dict()/to_dict() class methods for JSON serialization.

**Done When**:

- [ ] CommittedPlan dataclass in types.py
- [ ] request_id field present and validated non-empty
- [ ] Dependencies dict with cycle detection in validation
- [ ] from_dict()/to_dict() class methods

---

### WT-1.2.4: AggregatedResult Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add AggregatedResult class)

**Blocked By**: WT-1.2.5 (StepResult), WT-1.2.13 (CompensationRecord)

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "AggregatedResult")

**Specification**:
`@dataclass(frozen=True)`. Fields: result_id, plan_id (Optional), total_steps, completed, failed, cancelled, skipped, step_results (List[StepResult]), compensations (List[CompensationRecord]), total_tokens_consumed, total_cost_usd, budget_utilization, success, duration_ms, trace_id. Computed: success = (failed == 0 and cancelled == 0); budget_utilization = total_tokens_consumed / token_budget_max (0.0 if no budget). Factory methods: `from_medium(step_results, trace_id)` for MEDIUM tier, `from_dag(plan_id, step_results, compensations, token_budget_max, trace_id)` for HIGH tier. to_dict() for event payload.

**Done When**:

- [ ] AggregatedResult dataclass in types.py
- [ ] Both factory methods (from_medium, from_dag) implemented
- [ ] success computed property correct
- [ ] to_dict() serialization method

---

### WT-1.2.5: StepResult Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add StepResult class)

**Blocked By**: WT-1.2.9 (StepStatus enum)

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "StepResult")
- `k1/fabric/types.py` (CapabilityResult import)

**Specification**:
`@dataclass(frozen=True)`. Fields: step_id, capability_name, status (StepStatus), result (Optional[CapabilityResult]), duration_ms, retry_attempts, schema_retry (bool), quality_retry (bool), cost_usd, tokens_consumed, error_detail (Optional[str]). Invariant: COMPLETED -> result not None; FAILED -> error_detail not None; CANCELLED/SKIPPED -> result is None.

**Done When**:

- [ ] StepResult dataclass in types.py
- [ ] Status invariants documented in docstring
- [ ] Correct defaults (retry_attempts=0, cost_usd=0.0, etc.)

---

### WT-1.2.6: WorkflowRunRequest Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add WorkflowRunRequest class)

**Blocked By**: WT-1.2.9 (TriggerType enum)

**Context Files**:

- `k1/orchestrator/orchestrator.mmd` (S "Workflows")

**Specification**:
`@dataclass(frozen=True)`. Fields: request_id, workflow_id, version, trigger_type (TriggerType), trigger_context, param_overrides, trace_id, priority. Defaults: request_id=uuid4(), trigger_context={}, param_overrides={}, priority="INTERACTIVE" (per SEM-3). Validation: workflow_id non-empty; version follows semver.

**Done When**:

- [ ] WorkflowRunRequest dataclass in types.py
- [ ] priority defaults to "INTERACTIVE" (not REALTIME)
- [ ] Validation for workflow_id and version format

---

### WT-1.2.7: Wave Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add Wave class)

**Blocked By**: WT-1.2.18 (PlanStep)

**Specification**:
`@dataclass` (mutable -- not frozen). Fields: wave_index (int), steps (List[PlanStep]), resolved_params (Dict[str, Dict[str, Any]]). Defaults: resolved_params={}. Internal only -- never serialized. wave_index is 0-based.

**Done When**:

- [ ] Wave dataclass in types.py
- [ ] Mutable (no frozen=True)
- [ ] resolved_params defaults to empty dict

---

### WT-1.2.8: MicroReplanRequest Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add MicroReplanRequest class)

**Blocked By**: WT-1.2.5, WT-1.2.18, WT-1.2.20 (StepResult, PlanStep, Discovery/FailureContext)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10.6 -- MicroReplanRequest sync round-trip)

**Specification**:
`@dataclass(frozen=True)`. Fields: request_id, original_plan_id, completed_results (Dict[str, StepResult]), discoveries (List[Discovery]), remaining_steps (List[PlanStep]), failure_context (Optional[FailureContext]), trace_id. Defaults: request_id=uuid4(), discoveries=[], failure_context=None. Validation: original_plan_id non-empty; remaining_steps non-empty. Max 1 micro-replan per DAG (ORCH-13).

**Done When**:

- [ ] MicroReplanRequest dataclass in types.py
- [ ] Validation: remaining_steps non-empty
- [ ] All field types match specification

---

### WT-1.2.9: Enums (StepStatus, TriggerType, ProcessResult)

**Deliverable**: `k1/orchestrator/types.py` (add 3 enums)

**Blocked By**: None

**Specification**:
Three `str, Enum` classes (same pattern as k1.fabric.types.Tier):

- **StepStatus**: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, SKIPPED
- **TriggerType**: CRON, EVENT, MANUAL
- **ProcessResult**: COMPLETED, FAILED, DEGRADED, CANCELLED, DEFERRED

DEFERRED = re-enqueued because DAG active (ConcurrencyGuard). SKIPPED covers conditional-edge-false, token-budget-95%-skip, and dependent-of-failed-optional.

**Done When**:

- [ ] All 3 enums in types.py
- [ ] Each is `str, Enum` pattern
- [ ] All values match specification exactly

---

### WT-1.2.10: ErrorSeverity Enum + AdapterError Dataclass

**Deliverable**: `k1/orchestrator/types.py` (add ErrorSeverity + AdapterError)

**Blocked By**: None

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S7 -- circuit breakers, error classification)

**Specification**:
**ErrorSeverity**: `str, Enum` with RECOVERABLE, DEGRADED, TERMINAL. **AdapterError**: `@dataclass(frozen=True)`. Fields: severity (ErrorSeverity), adapter_name, operation, error_code, error_message, original_exception (Optional), fallback_action, trace_id. Classification matrix: Mailbox->RECOVERABLE, Fabric->DEGRADED, Planner->DEGRADED, StateRead->DEGRADED, DeltaEmit->RECOVERABLE, BridgeWrite->RECOVERABLE, EventSub->RECOVERABLE.

**Done When**:

- [ ] ErrorSeverity enum with 3 values
- [ ] AdapterError frozen dataclass with all 8 fields
- [ ] Classification matrix documented in docstring

---

### WT-1.2.11: WorkflowSaveRequest + TriggerSpec Dataclasses

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: WT-1.2.9 (TriggerType)

**Specification**:
**WorkflowSaveRequest**: `@dataclass(frozen=True)`. Fields: request_id, committed_plan_id, workflow_name, trigger_spec (TriggerSpec), trace_id. **TriggerSpec**: `@dataclass(frozen=True)`. Fields: type (TriggerType), schedule (Optional[str]), timezone (Optional[str]), event_topic (Optional[str]). Validation: CRON requires schedule; EVENT requires event_topic; MANUAL requires neither.

**Done When**:

- [ ] Both dataclasses in types.py
- [ ] TriggerSpec validation per trigger type
- [ ] Cron schedule field accepts cron expressions

---

### WT-1.2.12: ProactiveGap + ProactiveGapStatus Types

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Specification**:
**ProactiveGapStatus**: `str, Enum` (PENDING, ASKED, RESOLVED, AUTO_RESOLVED). **ProactiveGap**: `@dataclass` (mutable -- status transitions). Fields: gap_id, workflow_id, detected_at, gap_type, affected_step_id, capability_name, old_contract_version, new_contract_version, description, question (Optional), justification, status, resolved_value (Optional). gap_type values: "SCHEMA_DRIFT", "CAPABILITY_REMOVED", "PERMISSION_CHANGE".

**Done When**:

- [ ] Both types in types.py
- [ ] ProactiveGap is mutable (not frozen)
- [ ] gap_type values documented

---

### WT-1.2.13: CompensationRecord Dataclass

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Specification**:
`@dataclass` (mutable). Fields: record_id, dag_id, step_id, compensation_capability, compensation_params, status, initiated_at, completed_at (Optional), error_detail (Optional). Status transitions: PENDING -> EXECUTED or PENDING -> FAILED -> DEAD_LETTERED.

**Done When**:

- [ ] CompensationRecord in types.py
- [ ] Mutable (not frozen)
- [ ] Status transition documented in docstring

---

### WT-1.2.14: ConnectorHealthStatus Dataclass

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Specification**:
`@dataclass(frozen=True)`. Fields: connector_id, server_uri, server_type, status, last_check_at, consecutive_failures, capabilities_count, error_detail (Optional). server_type: "LOCAL", "REMOTE", "K0_PROXY". status: "ONLINE", "OFFLINE", "DEGRADED".

**Done When**:

- [ ] ConnectorHealthStatus in types.py
- [ ] Frozen dataclass
- [ ] server_type and status value sets documented

---

### WT-1.2.15: InterruptRequest Dataclass

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Specification**:
`@dataclass(frozen=True)`. Fields: request_id, target_dag_id (Optional -- None targets current), interrupt_type, reason, trace_id. interrupt_type values: "CANCEL_DAG" only in V1 ("PAUSE" and "MODIFY_PARAMS" removed). Validation: interrupt_type in allowed set; trace_id non-empty.

**Done When**:

- [ ] InterruptRequest in types.py
- [ ] Only "CANCEL_DAG" allowed in V1
- [ ] Validation in **post_init**

---

### WT-1.2.16: CostAccumulator Dataclass

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Specification**:
`@dataclass` (mutable). Fields: budget_max_usd (Optional), total_cost_usd (float=0.0), per_step_costs (Dict). Methods: `add(step_id, cost_usd)`, `utilization() -> float` (0.0 if no budget), `is_exceeded() -> bool`, `is_warning() -> bool` (>=0.80). Treat None cost_usd from CapabilityResult as 0.0.

**Done When**:

- [ ] CostAccumulator in types.py
- [ ] All 4 methods implemented
- [ ] Division-by-zero protection (no budget = 0.0 utilization)

---

### WT-1.2.17: Complete Event Catalog Constants

**Deliverable**: `k1/orchestrator/events.py` (separate file from types.py)

**Blocked By**: None

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S3 -- 32 event payload schemas)
- `k1/orchestrator/orchestrator.mmd` (S "Event Catalog")

**Specification**:
Module-level string constants (NOT an enum). Pattern: `ORCH_<category>_<action> = "k1.orchestration.<category>.<action>.v1"`. **20 Emitted**: TASK_ACCEPTED, PLAN_REQUESTED, DAG_STARTED, STEP_STARTED, STEP_COMPLETED, STEP_FAILED, STEP_CANCELLED, STEP_SKIPPED, STEP_RETRYING, STEP_SCHEMA_RETRY, STEP_QUALITY_RETRY, SAGA_COMPENSATING, DAG_MICRO_REPLAN, DAG_BUDGET_WARNING, DAG_BUDGET_EXHAUSTED, DAG_COMPLETED, DELTA_V1, WORKFLOW_TRIGGERED, WORKFLOW_COMPLETED, MCP_TOOL_REGISTERED. **12 Consumed**: PLAN_READY, PLAN_FAILED, PLAN_CANCELLED, MICRO_REPLAN_READY, CAPABILITY_COMPLETED, CAPABILITY_FAILED, CONTRACT_UPDATED, AGENT_TOOL_CALL, AGENT_LLM_CALL, WORKFLOW_TRIGGER_DUE, HIL_OVERRIDE_RESPONSE, HIL_FALLBACK_RESPONSE. Add `ALL_EMITTED` and `ALL_CONSUMED` frozensets.

**Done When**:

- [ ] `k1/orchestrator/events.py` file exists
- [ ] All 20 emitted event constants defined
- [ ] All 12 consumed event constants defined
- [ ] ALL_EMITTED and ALL_CONSUMED frozensets
- [ ] Each constant matches exact topic string (no typos)

---

### WT-1.2.18: PlanStep Dataclass (Full 14-Field Definition)

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: WT-1.2.9 (StepStatus for validation reference), WT-1.2.20 (ConditionExpr)

**Context Files**:

- `k1/fabric/types.py` (Fabric PlanStep -- 6 fields to extend from)
- `k1/orchestrator/orchestrator.mmd` (S "PlanStep")

**Specification**:
`@dataclass(frozen=True)`. All 14 fields: (1) id: str, (2) capability: str, (3) params: Dict, (4) deps: List[str], (5) prompt_template: Optional[str], (6) tools_granted: Optional[List[str]], (7) token_budget: int (default 0=unlimited), (8) output_schema: Optional[Dict] (JSON Schema), (9) condition: Optional[ConditionExpr], (10) is_optional: bool=False, (11) has_side_effects: bool=False, (12) compensation: Optional[str], (13) timeout_ms: Optional[int], (14) required_context: Optional[List[str]]. Prefer re-define over subclassing Fabric PlanStep (avoid tight coupling). Provide `from_fabric(fabric_step, planner_extensions)` factory. to_dict()/from_dict() for serialization.

**Done When**:

- [ ] PlanStep with 14 fields in types.py
- [ ] `@dataclass(frozen=True)`
- [ ] from_fabric() factory method
- [ ] to_dict()/from_dict() methods
- [ ] Validation: id non-empty, capability non-empty, token_budget >= 0

---

### WT-1.2.19: PendingPlanContext + PendingHILContext Types

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: WT-1.2.1 (TaskEnvelope), WT-1.2.7 (Wave)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10 -- Planner-Orchestrator protocol)
- WT-1.1.12 (Event-driven ADR -- defines the async pattern)

**Specification**:
**PendingPlanContext**: `@dataclass`. Fields: request_id, task_envelope (TaskEnvelope), state_snapshot (ContextSnapshot), created_at, timeout_ms (45000). Keyed by request_id in OrchestratorService.pending_plans dict. **PendingHILContext**: `@dataclass`. Fields: request_id, dag_execution_id, current_wave_index, completed_waves (List[WaveResult]), remaining_waves (List[Wave]), question, options (List[str]), created_at, timeout_ms, timeout_fallback ("CONTINUE" or "GRACEFUL_FAIL"). Add max_pending_plans=50 and max_pending_hil=20 hard caps.

**Done When**:

- [ ] Both context types in types.py
- [ ] Both mutable (not frozen)
- [ ] Hard cap constants defined (50, 20)
- [ ] timeout_fallback field on PendingHILContext

---

### WT-1.2.20: Supporting Types Batch (15 Types)

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: WT-1.2.9

**Specification**:
All `@dataclass(frozen=True)` unless noted. 15 types: (1) ContextSnapshot, (2) SectionData, (3) ValidationResult, (4) CapabilityCheck, (5) ResolutionResult, (6) WaveResult, (7) RegistryEntry, (8) Discovery, (9) ConditionExpr (type in AND/OR/NOT/EQ/NEQ/GT/LT), (10) QualityDecision (action in PASS/RETRY/SOFT_FAIL), (11) SchemaResult, (12) HILRequest, (13) PlanAck, (14) TaskAck, (15) FailureContext. See plan Epic 1.2 issue 1.2.20 for full field signatures per type.

**Done When**:

- [ ] All 15 types in types.py
- [ ] Each has correct frozen/mutable annotation
- [ ] ConditionExpr valid type values documented
- [ ] QualityDecision thresholds documented

---

### WT-1.2.21: ProcessingContext Standalone Type

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S1 -- ProcessingContext definition)

**Specification**:
`@dataclass`. Full field set per WB S1: trace_id, request_id, tier, created_at, dag_id (Optional), workflow_id (Optional), parent_trace_id (Optional), session_id (Optional), user_id (Optional). Defaults: created_at=time.time(), optionals=None. Validation: trace_id non-empty, request_id non-empty, tier in valid set. Carried through every service call for trace correlation.

**Done When**:

- [ ] ProcessingContext in types.py
- [ ] All 9 fields per WB S1
- [ ] Validation in **post_init**
- [ ] Mutable (not frozen -- dag_id set after creation)

---

### WT-1.2.22: OrchestratorConfig Dataclass (~40 Fields)

**Deliverable**: `k1/orchestrator/config.py` (separate file -- avoids circular imports with factory)

**Blocked By**: None

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S2 -- full field catalog)
- `k1/orchestrator/orchestrator.mmd` (S "Configuration")

**Specification**:
`@dataclass(frozen=True)`. ~40 fields organized by group: Concurrency (max_concurrent_dags=3, max_wave_parallelism=5, mailbox_capacity=100), Timeouts (default_step=30000, plan_request=45000, hil=120000, drain=30000), Circuit Breakers (4 CBs with threshold + reset per WB S7), Token Budgets (multiplier=1.0, warn=0.80, skip=0.95), Guard Pipeline (guard_order list per WB S8), MCP (discovery_interval=300000, max_servers=10), Telemetry (metrics_interval=10000, trace_sample_rate=1.0), Admin (port=8081, enabled=True). Factory methods: from_dict() and default(). Validation: all timeouts > 0, multiplier > 0, trace_sample_rate [0.0, 1.0].

**Done When**:

- [ ] `k1/orchestrator/config.py` file exists
- [ ] OrchestratorConfig frozen dataclass with ~40 fields
- [ ] All field groups present with correct defaults
- [ ] from_dict() and default() factory methods
- [ ] Validation in **post_init**

---

### WT-1.2.23: CircuitBreakerConfig + CircuitBreakerState Types

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S7 -- 4 circuit breakers)

**Specification**:
**CircuitBreakerConfig**: `@dataclass(frozen=True)`. Fields: name, failure_threshold, reset_timeout_ms, half_open_max_probes (default 1). **CircuitBreakerState**: `@dataclass` (mutable). Fields: name, state ("CLOSED"/"OPEN"/"HALF_OPEN"), failure_count, last_failure_at, last_success_at, opened_at. Methods: record_failure(), record_success(), should_allow() -> bool, check_reset_timeout() -> bool. Config defaults per WB S7: CB_PLANNER(3, 60000, 1), CB_FABRIC(5, 30000, 2), CB_MCP(3, 45000, 1), CB_BRIDGE(5, 30000, 2).

**Done When**:

- [ ] CircuitBreakerConfig frozen dataclass
- [ ] CircuitBreakerState mutable dataclass with 4 methods
- [ ] State transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
- [ ] 4 CB defaults documented

---

### WT-1.2.24: Guard Pipeline Types (GuardAction, GuardDecision, 3 Protocols)

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: WT-1.2.21 (ProcessingContext), WT-1.2.16 (CostAccumulator)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S8 -- guard pipeline G0-G10)

**Specification**:
**GuardAction**: `str, Enum` (ALLOW, REJECT, DEGRADE, DEFER). **GuardDecision**: `@dataclass(frozen=True)`. Fields: guard_name, action (GuardAction), reason, degraded_to (Optional). Pipeline short-circuits on first REJECT. **3 Protocol classes**: (1) PreDispatchGuard: `check(envelope, ctx) -> GuardDecision`, (2) PreWaveGuard: `check(wave, accum, ctx) -> GuardDecision`, (3) PostStepGuard: `check(result, ctx) -> GuardDecision`. Guard ordering per WB S8: G0-G4 pre-dispatch, G5-G8 pre-wave, G9-G10 post-step.

**Done When**:

- [ ] GuardAction enum with 4 values
- [ ] GuardDecision frozen dataclass
- [ ] 3 Protocol classes with correct method signatures
- [ ] Guard ordering documented in docstring

---

### WT-1.2.25: Admin API Types

**Deliverable**: `k1/orchestrator/types.py`

**Blocked By**: None

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S5 -- 18 admin endpoints, S6 -- health probes)

**Specification**:
**HealthStatus**: `@dataclass(frozen=True)`. Fields: status ("HEALTHY"/"DEGRADED"/"UNHEALTHY"), uptime_ms, active_dags, mailbox_depth, circuit_breakers (Dict[str, str]), last_error (Optional). **ActiveDAGInfo**: `@dataclass(frozen=True)`. Fields: dag_id, plan_id, current_wave, total_waves, steps_completed, steps_failed, started_at, trace_id. **DrainResult**: `@dataclass(frozen=True)`. Fields: drained (bool), active_dags_remaining, timeout_reached, duration_ms.

**Done When**:

- [ ] All 3 admin types in types.py
- [ ] HealthStatus status values documented
- [ ] All fields match WB S5/S6

---

### WT-1.2.26: PlanRequest + CapabilityDescriptor JSON Schemas

**Deliverable**: `k1/contracts/schemas/orchestrator/plan_request.v1.json`, `k1/contracts/schemas/orchestrator/capability_descriptor.v1.json`

**Blocked By**: WT-1.2.2 (PlanRequest type)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10.2, S10.5)

**Specification**:
JSON Schema Draft 2020-12. (1) plan_request.v1.json: required (request_id: uuid, intent: string, trace_id: string, timeout_ms: integer min 1000), optional (constraints: object, context: object). (2) capability_descriptor.v1.json: required (name: string, provider_type: enum["tool","agent","meta_agent"], safety_band_min: enum["OPEN","STANDARD","RESTRICTED"]), optional (estimated_duration_ms: integer, compensation_capability: string).

**Done When**:

- [ ] Both JSON Schema files exist in `k1/contracts/schemas/orchestrator/`
- [ ] Schemas pass JSON Schema Draft 2020-12 metaschema validation
- [ ] Field constraints match dataclass signatures

---

### WT-1.2.27: MicroReplanRequest JSON Schema

**Deliverable**: `k1/contracts/schemas/orchestrator/micro_replan_request.v1.json`

**Blocked By**: WT-1.2.8 (MicroReplanRequest type)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10.6)

**Specification**:
JSON Schema. Required: request_id (uuid), original_plan_id, completed_results (object), remaining_steps (array, minItems: 1), trace_id. Optional: discoveries (array, default []), failure_context (object). Validation: remaining_steps must be non-empty; completed_results keys must not overlap with remaining_steps ids.

**Done When**:

- [ ] JSON Schema file exists
- [ ] minItems: 1 on remaining_steps
- [ ] All required/optional fields match spec

---

## Epic 1.3: Contract Schema Registration

> All files in `k1/contracts/modules/orchestrator/`. YAML/Markdown declarations only -- no Python code.

---

### WT-1.3.1: Create module.contract.yaml

**Deliverable**: `k1/contracts/modules/orchestrator/module.contract.yaml`

**Blocked By**: WT-1.2.17 (event catalog for reference), WT-1.2.9 (type names)

**Context Files**:

- `k1/contracts/modules/fabric/module.contract.yaml` (reference pattern)
- `docs/whiteboard/schema_whiteboard.md` (S4.1 -- module contract template)

**Specification**:
Follow Fabric pattern. Metadata: module_id="orchestrator", owner="platform-team", band="GREEN". Exports: 7 services (OrchestratorService, DAGExecutor, StepRunner, ConstraintResolver, WorkflowEngine, ConnectorManager, ErrorRouter). Ports: 8. Dependencies: fabric, sessionstate, bus, bridge. Invariants section: ORCH-01 to ORCH-16.

**Done When**:

- [ ] YAML file exists following Fabric pattern
- [ ] 7 exports listed
- [ ] 8 ports listed
- [ ] 16 invariants listed
- [ ] Format matches WB S4.1 template

---

### WT-1.3.2: Create wiring.contract.yaml

**Deliverable**: `k1/contracts/modules/orchestrator/wiring.contract.yaml`

**Blocked By**: WT-1.2.17 (event catalog), WT-1.4.1-WT-1.4.7 (ports)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S4.2 -- wiring contract template)

**Specification**:
Required files list. Provided capabilities: none. Consumed: "*". Emitted events (20) with payload refs. Subscribed events (12). Validation rules: all 8 ports required, IStateReadPort read-only, event topics must match exactly.

**Done When**:

- [ ] YAML file exists
- [ ] 20 emitted events listed
- [ ] 12 subscribed events listed
- [ ] Validation rules documented

---

### WT-1.3.3: Create policies.contract.yaml

**Deliverable**: `k1/contracts/modules/orchestrator/policies.contract.yaml`

**Blocked By**: None

**Specification**:
Performance budgets (overhead_p99=18ms, medium=10s, high=45s, step=30s). Step limits (max_steps=50, max_waves=20, max_concurrent=10, max_replans=1). Retry limits (normal=2, schema=1, quality=1). Budget thresholds (warn=80%, skip=95%, stop=100%). Quality thresholds (soft_fail=0.3, retry=0.7). Mailbox (max_depth=100, 3 priority classes). Workflow limits (depth=3, active=100, tick=1s). Pending context limits (plans=50, hil=20, reaper=5s).

**Done When**:

- [ ] YAML file with all policy sections
- [ ] All numeric values match specification
- [ ] No hardcoded magic numbers in source code will reference values not in this file

---

### WT-1.3.4: Create cross-component-contracts.md

**Deliverable**: `k1/contracts/modules/orchestrator/cross-component-contracts.md`

**Blocked By**: WT-1.2.1 (TaskEnvelope), WT-1.2.4 (AggregatedResult)

**Specification**:
Documents the Concierge-side interface: (1) submit_task(TaskEnvelope) -> TaskAck with CB_ORCHESTRATOR, (2) event subscription for dag.completed (AggregatedResult), (3) progress subscription, (4) tier degradation callbacks, (5) TaskEnvelope construction spec per tier.

**Done When**:

- [ ] Markdown file documents full Concierge contract
- [ ] All 5 sections present
- [ ] TaskEnvelope construction rules per tier documented

---

## Epic 1.4: Port Interface Definitions (Protocol Stubs)

> Each port in its own file under `k1/orchestrator/ports/`. Package `__init__.py` re-exports all 8 Protocols.
> **Anti-Hallucination**: Port files contain ZERO implementation logic. Every method body is `...` (Protocol). No default implementations. No helper methods. No state.

---

### WT-1.4.1: IMailboxPort

**Deliverable**: `k1/orchestrator/ports/mailbox_port.py`

**Blocked By**: WT-1.2.1 (TaskEnvelope), WT-1.2.15 (InterruptRequest)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S9 -- mailbox durability)

**Specification**:
`class IMailboxPort(Protocol)`. All methods sync. Methods: `enqueue(message, priority="INTERACTIVE") -> int`, `dequeue() -> Optional[Any]`, `depth() -> int`, `peek_priority() -> Optional[str]`. WFQ: REALTIME(60%) > INTERACTIVE(30%) > BACKGROUND(10%).

**Done When**:

- [ ] File exists at `k1/orchestrator/ports/mailbox_port.py`
- [ ] Protocol class with 4 method stubs
- [ ] MailboxMessage type union defined or documented
- [ ] No implementation -- all methods `...`

---

### WT-1.4.2: IFabricGatewayPort

**Deliverable**: `k1/orchestrator/ports/fabric_gateway_port.py`

**Blocked By**: None (imports from k1.fabric.types)

**Specification**:
`class IFabricGatewayPort(Protocol)`. All async. Methods: `execute(request) -> CapabilityResult`, `execute_batch(requests) -> List[CapabilityResult]`, `query_registry(capability_name) -> Optional[RegistryEntry]`. No spawn() in V1.

**Done When**:

- [ ] File exists with Protocol class
- [ ] 3 async method stubs
- [ ] Imports CapabilityRequest, CapabilityResult from k1.fabric.types

---

### WT-1.4.3: IPlannerPort

**Deliverable**: `k1/orchestrator/ports/planner_port.py`

**Blocked By**: WT-1.2.2 (PlanRequest), WT-1.2.8 (MicroReplanRequest)

**Specification**:
`class IPlannerPort(Protocol)`. All async. Methods: `request_plan(request) -> PlanAck` (fire-and-forget, CommittedPlan arrives via event bus), `cancel_plan(request_id) -> None`, `micro_replan(request) -> Optional[CommittedPlan]` (synchronous with 10s timeout). No await_plan().

**Done When**:

- [ ] File exists with Protocol class
- [ ] 3 async method stubs
- [ ] No await_plan() method (event-driven model)

---

### WT-1.4.4: IStateReadPort

**Deliverable**: `k1/orchestrator/ports/state_read_port.py`

**Blocked By**: WT-1.2.20 (ContextSnapshot, SectionData)

**Specification**:
`class IStateReadPort(Protocol)`. All async. Methods: `read(section) -> Optional[SectionData]`, `snapshot(sections) -> ContextSnapshot`. **CRITICAL**: NO write methods (ORCH-01).

**Done When**:

- [ ] File exists with Protocol class
- [ ] 2 async method stubs (read + snapshot only)
- [ ] ORCH-01 invariant documented in docstring
- [ ] Zero write methods

---

### WT-1.4.5: IDeltaEmitPort

**Deliverable**: `k1/orchestrator/ports/delta_emit_port.py`

**Blocked By**: WT-1.2.20 (HILRequest)

**Specification**:
`class IDeltaEmitPort(Protocol)`. All async, fire-and-forget. Methods: `emit(event_topic, payload, trace_id) -> None`, `emit_progress(step_id, summary, trace_id) -> None`, `emit_hil_request(hil_request, trace_id) -> None`. All methods catch exceptions internally -- never fails.

**Done When**:

- [ ] File exists with Protocol class
- [ ] 3 async method stubs
- [ ] Fire-and-forget semantics documented

---

### WT-1.4.6: IBridgeWritePort

**Deliverable**: `k1/orchestrator/ports/bridge_write_port.py`

**Blocked By**: None

**Specification**:
`class IBridgeWritePort(Protocol)`. All async, fire-and-forget. Methods: `submit_audit(run_manifest, trace_id) -> None`, `write_wal(dag_id, entry_type, payload, trace_id) -> None`, `read_wal(dag_id) -> Optional[List[Dict]]`, `list_wal_ids() -> List[str]`, `submit_deferred_result(result, workflow_id, trace_id) -> None`. read_wal/list_wal_ids raise AdapterError(DEGRADED) if K0 unreachable.

**Done When**:

- [ ] File exists with Protocol class
- [ ] 5 async method stubs
- [ ] WAL entry_type values documented ("PLAN_START", "WAVE_COMPLETE", "STEP_COMPLETE", "DAG_COMPLETE")

---

### WT-1.4.7: IEventSubscriptionPort

**Deliverable**: `k1/orchestrator/ports/event_subscription_port.py`

**Blocked By**: None

**Specification**:
`class IEventSubscriptionPort(Protocol)`. Methods: `subscribe(topic, handler) -> str` (returns subscription_id), `unsubscribe(subscription_id) -> None`, `publish(topic, payload) -> None`. Supports wildcards. Required subscriptions listed (12 consumed events). Reconnection: exponential backoff 1s..30s.

**Done When**:

- [ ] File exists with Protocol class
- [ ] 3 async method stubs
- [ ] Required subscriptions documented in docstring

---

### WT-1.4.8: Ports Package **init**.py

**Deliverable**: `k1/orchestrator/ports/__init__.py`

**Blocked By**: WT-1.4.1 through WT-1.4.7

**Specification**:
Re-export all 7 port Protocols (8th port IWorkflowStoragePort ships with Epic 4.1): `from k1.orchestrator.ports.mailbox_port import IMailboxPort` etc.

**Done When**:

- [ ] `__init__.py` re-exports all 7 Protocols
- [ ] `from k1.orchestrator.ports import IMailboxPort, IFabricGatewayPort, ...` works

---

## Epic 1.5: Event Payload JSON Schemas

> Files in `k1/contracts/schemas/orchestrator/events/`. Declarative JSON Schema files only -- no Python code generation.

---

### WT-1.5.1: Create 20 Emitted Event Payload JSON Schemas

**Deliverable**: `k1/contracts/schemas/orchestrator/events/emitted/` (20 files)

**Blocked By**: WT-1.2.17 (event catalog -- need exact topic names)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S3 -- emitted event schemas)

**Specification**:
One JSON Schema file per emitted event. Files: task_accepted.v1.json, plan_requested.v1.json, dag_started.v1.json, step_started.v1.json, step_completed.v1.json, step_failed.v1.json, step_cancelled.v1.json, step_skipped.v1.json, step_retrying.v1.json, step_schema_retry.v1.json, step_quality_retry.v1.json, saga_compensating.v1.json, dag_micro_replan.v1.json, dag_budget_warning.v1.json, dag_budget_exhausted.v1.json, dag_completed.v1.json, delta_v1.v1.json, workflow_triggered.v1.json, workflow_completed.v1.json, mcp_tool_registered.v1.json. Each includes: required fields (event_id, topic, timestamp, trace_id, payload). All Draft 2020-12.

**Done When**:

- [ ] 20 JSON Schema files in emitted/ directory
- [ ] Each passes Draft 2020-12 metaschema validation
- [ ] Each has required: [event_id, topic, timestamp, trace_id, payload]
- [ ] Payload objects have event-specific fields per WB S3

---

### WT-1.5.2: Create 12 Consumed Event Payload JSON Schemas

**Deliverable**: `k1/contracts/schemas/orchestrator/events/consumed/` (12 files)

**Blocked By**: WT-1.2.17 (event catalog)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S3 -- consumed event schemas)

**Specification**:
One JSON Schema file per consumed event. Files: plan_ready.v1.json (CommittedPlan payload), plan_failed.v1.json, plan_cancelled.v1.json, micro_replan_ready.v1.json, capability_completed.v1.json, capability_failed.v1.json, contract_updated.v1.json, agent_tool_call.v1.json, agent_llm_call.v1.json, workflow_trigger_due.v1.json, hil_override_response.v1.json, hil_fallback_response.v1.json.

**Done When**:

- [ ] 12 JSON Schema files in consumed/ directory
- [ ] Each passes metaschema validation
- [ ] plan_ready.v1.json mirrors CommittedPlan fields

---

### WT-1.5.3: Create Planner Contract YAML (Module + Wiring)

**Deliverable**: `k1/contracts/modules/planner/module.contract.yaml`, `k1/contracts/modules/planner/wiring.contract.yaml`

**Blocked By**: WT-1.2.26 (PlanRequest JSON Schema)

**Context Files**:

- `docs/whiteboard/schema_whiteboard.md` (S10 -- Planner-Orchestrator protocol)

**Specification**:
Defines Planner-side contract from Orchestrator's perspective. Module contract: Planner metadata, exports, ports. Wiring contract: emitted (plan_ready, plan_failed, plan_cancelled, micro_replan_ready), consumed (plan_requested), required schemas (PlanRequest per WB S10.2, CommittedPlan per WB S10.3). Key protocol: request_id echo contract, PlanAck within 500ms, CapabilityDescriptor format.

**Done When**:

- [ ] Both YAML files in `k1/contracts/modules/planner/`
- [ ] request_id echo contract documented
- [ ] PlanAck 500ms SLO stated
- [ ] Event wiring matches Orchestrator consumed events
