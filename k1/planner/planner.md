# Planner -- Deep Architecture Discussion

> **Status**: Design Discussion (Hyper-Detailed)
> **Date**: 2026-02-14
> **Layer**: L3 in K1 Cognitive Architecture Skeleton
> **Position**: Between Orchestrator (L2) and Capability Fabric (L2.5) / Model Hub
> **Governing Documents**:
>
> - `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` (L3_PLANNER subgraph)
> - `docs/architecture/whiteboard_k1/whiteboard_concierge_orchestrator_planner_fabric.md` (Section 5)
> - `k1/planner/planner.mmd` (913-line authoritative architecture spec)
> - `k1/contracts/modules/planner/wiring.contract.yaml` (593-line wiring contract)
> - `k1/contracts/modules/planner/module.contract.yaml` (module contract)
> - `k1/kernel/kernel.md` (Phase 5 bootstrap, Section 23 CB_PLANNER, Section 18.2 events)
> - `k1/orchestrator/orchestrator.md` (ORCH-13 micro-replan, Section 6 HIGH tier flow)
> - `k1/model_hub/model_hub.mmd` (IModelHubPort consumer)
> **ADRs**: ADR-0007 (4-Stage Planner)

---

## 1. Identity & Position in K1

The Planner is Layer 3 of the K1 Cognitive Kernel. It sits between the Orchestrator (L2 -- deterministic DAG executor) and the Capability Fabric (L2.5 -- execution engine) / Model Hub (LLM gateway). The Planner is the **only LLM-powered planning component** in the system -- it transforms a PlanRequest into a CommittedPlan via a 4-stage intelligence pipeline (SKETCH -> EXPAND -> VALIDATE -> COMMIT).

**Key analogy**: Planner = the brain that designs the recipe. Orchestrator = the cook that follows it. Fabric = the kitchen with tools. The Planner decides WHAT to cook and HOW, the Orchestrator mechanically follows the instructions.

### Position in call chain

```
User -> Concierge (L1) -> Orchestrator (L2) -> PLANNER (L3, conditional) -> Fabric Retrieval (read-only)
                                                                          -> Model Hub (LLM calls)
                                                                          -> SessionState (read-only)
                                                                          -> K0 Bridge (recall + WAL)
```

### When Planner is involved

| Tier | Planner? | What happens |
|------|----------|------|
| LOW | No | Concierge calls Fabric directly |
| MEDIUM | No | Orchestrator coordinates 1-2 Fabric calls directly |
| HIGH | **Yes** | Orchestrator sends PlanRequest, Planner produces CommittedPlan |
| CRISIS | No | Safety Agent handles immediately |

### What Planner is NOT (non-negotiable)

- NOT a state writer (NEVER writes SessionState, PLAN-01)
- NOT a capability executor (NEVER invokes capabilities, PLAN-06 -- discovery only)
- NOT an agent spawner (NEVER creates agents -- Orchestrator + Fabric do that)
- NOT an Orchestrator (walks no DAG, executes no steps)
- NOT a decision maker at execution time (produces a plan, then exits)
- NOT unlimited (45s max planning time, ~3.5K tokens total, max 6 tool calls)

---

## 2. Hard Invariants

These are non-negotiable rules. Violation means rejection.

| ID | Invariant | Enforced By |
|----|-----------|-------------|
| PLAN-01 | Planner NEVER writes SessionState (all reads are lock-free multi-reader) | IStateReadPort (no write methods) |
| PLAN-02 | ALL 4 discovery tools are read-only (zero side effects) | ToolCallRouter (no action tools) |
| PLAN-03 | Stage 4 COMMIT is deterministic (zero LLM calls) | CommitService (no ILLMPort dependency) |
| PLAN-04 | Max planning time 45s (CB_PLANNER timeout, owned by Orchestrator PlannerAdapter) | PlannerAdapter circuit breaker wrapping |
| PLAN-05 | Max 6 discovery tool calls per plan (3 in SKETCH + 3 in EXPAND) | ToolCallRouter counter |
| PLAN-06 | NEVER executes capabilities (discovery only, no invoke_capability) | IFabricRetrievalPort (retrieval-only) |
| PLAN-07 | V1 DEFERRED: token_budget_max + per-step token_budget removed from types.py | CommitService (V2) |
| PLAN-08 | Each step MUST reference valid capability from Fabric Registry | ValidateService capability check |
| PLAN-09 | Plan dependencies MUST form a DAG (no cycles) | ValidateService DAG cycle detection |
| PLAN-10 | HIL clarification max 2 rounds per plan (then best-effort) | HILCoordinator round counter |
| PLAN-11 | All LLM calls carry budget{max_tokens, timeout_ms} (no unbounded calls) | PipelineController budget injection |
| PLAN-12 | Micro-replan adjusts remaining steps only (completed steps frozen) | MicroReplanService step filter |

---

## 3. Core Architecture Components

The L3_PLANNER subgraph contains 4 major subsystems:

### 3.1 Planner Core

| Component | Purpose | Notes |
|-----------|---------|-------|
| **PlannerAgent** | Single-threaded async coordinator, one plan at a time (V1) | Dequeues PlanRequest/MicroReplanRequest from mailbox, drives pipeline |
| **Planner Mailbox** | WFQ priority queue, max depth 5 | INTERACTIVE priority, rejects beyond depth 5 |
| **PipelineController** | Orchestrates SKETCH -> EXPAND -> VALIDATE -> COMMIT | Tracks stage transitions, token usage, tool call counting, micro-replan re-entry |
| **Plan State Machine** | FSM: IDLE -> SKETCHING -> EXPANDING -> VALIDATING -> COMMITTING -> COMPLETED/FAILED/CANCELLED | Micro-replan: MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE -> COMMITTING |

### 3.2 4-Stage Pipeline Services

| Component | Purpose | Notes |
|-----------|---------|-------|
| **SketchService** | Stage 1: LLM rough plan generation (~2K tokens) | Calls discover_capabilities, query_planning_context, recall_for_planning. Triggers HIL clarification |
| **ExpandService** | Stage 2: Tool mapping + parameterization (~1K tokens) | Calls discover_capabilities (refined), find_relevant_prompts. Assigns output_schema, tools_granted per step |
| **ValidateService** | Stage 3: Deterministic checks + LLM arbiter (~500 tokens) | DAG cycle detection, capability existence check. Triggers HIL approval. Verdict: approved/revise/reject |
| **CommitService** | Stage 4: Deterministic commit (0 tokens) | Builds CommittedPlan, assigns plan_id. Persists K0 WAL, emits plan.ready. NO ILLMPort dependency |

### 3.3 Support Services

| Component | Purpose | Notes |
|-----------|---------|-------|
| **ToolCallRouter** | Routes 4 discovery tools to correct backends | Fabric Retrieval, SessionState, Bridge. Enforces PLAN-05 (max 6 calls/plan) |
| **HILCoordinator** | Manages clarification + approval flows | LLM prompt generation for HIL messages. Max 2 rounds (PLAN-10), timeout handling |

### 3.4 Discovery Tool Subsystem

| Tool | Routes To | Used In Stages | Latency |
|------|-----------|----------------|---------|
| `discover_capabilities()` | Fabric Retrieval | SKETCH, EXPAND | <50ms |
| `find_relevant_prompts()` | Fabric Retrieval | EXPAND | <50ms |
| `query_planning_context()` | SessionState (direct) | SKETCH | <10ms |
| `recall_for_planning()` | K0 Bridge | SKETCH | <100ms |

---

## 4. Mailbox & Message Protocol

### 4.1 Planner Mailbox

The Planner Mailbox is a **single-priority FIFO queue** with **max depth 5** (rejects/drops beyond). Unlike the Orchestrator mailbox (MPSC + 3-class WFQ with 100 depth), the Planner mailbox is simpler because it has only one consumer, one message type flowing in (PlanRequest), and micro-replan bypasses the queue entirely (direct method call).

| Property | Orchestrator Mailbox | Planner Mailbox |
|----------|---------------------|-----------------|
| Type | MPSC + WFQ (3 priority classes) | MPSC + FIFO (single priority) |
| Max depth | 100 | 5 |
| Priority classes | REALTIME (60%) / INTERACTIVE (30%) / BACKGROUND (10%) | INTERACTIVE only |
| Message types | TaskEnvelope, CommittedPlan, WorkflowRunRequest, WorkflowSaveRequest, InterruptRequest | PlanRequest only |
| Consumer | OrchestratorActor (routes by isinstance) | PlannerAgent (always PlanRequest) |
| Dequeue semantics | WFQ weighted selection | FIFO |
| Full behavior | Raises MailboxFullError (Concierge CB handles) | Rejects with PlanAck(REJECTED) |

**Producers** (who can enqueue):

| Producer | Message | Via | Priority | Notes |
|----------|---------|-----|----------|-------|
| Orchestrator | PlanRequest | `PlannerAdapter.request_plan()` -> `IPlannerMailbox.enqueue()` | INTERACTIVE | Fire-and-forget, CommittedPlan returns via event bus |

**Not via mailbox** (direct call):

| Caller | Message | Via | Notes |
|--------|---------|-----|-------|
| Orchestrator | MicroReplanRequest | `PlannerAdapter.micro_replan()` -> `IPlannerMailbox.micro_replan()` | Synchronous, 10s timeout, bypasses queue |
| Orchestrator | cancel_plan | `PlannerAdapter.cancel_plan()` -> `IPlannerMailbox.send_cancel()` | Best-effort, bypass queue |

**Consumer**: PlannerAgent (single, sequential -- one plan at a time in V1)

### 4.2 Planner Mailbox Protocol (IPlannerMailbox)

The Planner exposes a structural protocol consumed by the Orchestrator's `PlannerAdapter`. This protocol is defined on the Orchestrator side (consumer-driven contract) and the Planner module must provide an object satisfying it.

**Source**: `k1/orchestrator/adapters/planner_adapter.py` line 65 -- `IPlannerMailbox(Protocol)`

```python
class IPlannerMailbox(Protocol):
    """Structural protocol for the Planner's inbound mailbox."""

    async def enqueue(self, request: PlanRequest) -> None:
        """Enqueue a plan request for asynchronous processing.
        Raises on mailbox full (depth >= 5)."""

    async def send_cancel(self, request_id: str) -> None:
        """Signal cancellation for an in-flight plan request.
        Best-effort: plan may have already committed."""

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        """Synchronous micro-replan. Planner responds inline (10s budget).
        PlannerAdapter wraps this with asyncio.wait_for(timeout=10.0)."""
```

**Key design decisions**:

1. **enqueue() is async but returns None** -- PlanAck is constructed by `PlannerAdapter` on the Orchestrator side after successful enqueue, not by the Planner mailbox itself.
2. **micro_replan() returns CommittedPlan directly** -- no event bus, no mailbox queuing. The `PlannerAdapter` wraps this with `asyncio.wait_for(timeout=10.0)` and returns `None` on timeout.
3. **send_cancel() is best-effort** -- the Planner may have already committed. If the plan was delivered via event bus, cancel has no effect.

### 4.3 PlannerAdapter (Orchestrator-side wrapper)

The `PlannerAdapter` (production IPlannerPort implementation) wraps `IPlannerMailbox` with CB_PLANNER circuit breaker logic. This is the Orchestrator's view of the Planner.

**Source**: `k1/orchestrator/adapters/planner_adapter.py` line 85 -- `PlannerAdapter`

```
Constructor:  PlannerAdapter(planner_mailbox: IPlannerMailbox, cb_planner: CircuitBreaker)
```

| Method | CB Check? | On Success | On Failure | Returns |
|--------|-----------|------------|------------|---------|
| `request_plan(PlanRequest)` | Yes -- OPEN raises AdapterException(DEGRADED) | `cb.reset()`, return `PlanAck(ACCEPTED)` | `cb.trip()`, return `PlanAck(REJECTED)` | `PlanAck` |
| `cancel_plan(request_id)` | No (always attempted) | silent | log warning | `None` |
| `micro_replan(MicroReplanRequest)` | Yes -- OPEN raises | `cb.reset()`, return `CommittedPlan` | Timeout: `cb.trip()`, return `None`. Other: `cb.trip()`, raise | `Optional[CommittedPlan]` |

**CB_PLANNER configuration** (from `OrchestratorConfig`):

```
failure_threshold:  3                          (cb_planner_failure_threshold)
reset_timeout_s:    60.0                       (cb_planner_reset_timeout_ms / 1000)
half_open_probes:   1                          (cb_planner_half_open_probes)
```

**State machine**: `CLOSED --[3 failures]--> OPEN --[60s]--> HALF_OPEN --[1 probe success]--> CLOSED`

### 4.4 Two-Phase Plan Delivery Protocol

Plan delivery uses a two-phase protocol where request and response travel different channels:

```
Phase 1 (request -- synchronous):
  Orchestrator                           Planner
     |                                      |
     |-- PlannerAdapter.request_plan() ---->|
     |   (CB check, enqueue to mailbox)     |
     |<---- PlanAck{ACCEPTED} ------------- |  (immediate, constructed by PlannerAdapter)
     |                                      |
     |   OrchestratorService saves          |
     |   PendingPlanContext{request_id}     |
     |                                      |

Phase 2 (delivery -- asynchronous, via event bus):
  Orchestrator                           Planner
     |                                      |
     |   (Planner runs 4-stage pipeline)    |
     |                                      |
     |<-- k1.planner.plan.ready.v1 --------|  (CommittedPlan payload)
     |   or                                 |
     |<-- k1.planner.plan.failed.v1 -------|  ({request_id, reason, stage})
     |   or                                 |
     |<-- k1.planner.plan.cancelled.v1 ----|  ({request_id, reason})
     |                                      |
     |   OrchestratorService correlates     |
     |   via request_id -> PendingPlanContext|
```

**Correlation**: `CommittedPlan.request_id` MUST match the original `PlanRequest.request_id` so the Orchestrator can look up the `PendingPlanContext` and begin DAG execution.

**Timeout**: If no plan arrives within the configured timeout (default 45s), the Orchestrator's stale-context reaper calls `cancel_plan(request_id)` and degrades the task.

### 4.5 Message Envelopes

Every message flowing into or out of the Planner has a specific schema. All types in this section are defined in `k1/orchestrator/types.py` (source of truth) -- the Planner re-exports them but MUST NOT redefine them.

**PlanRequest** (Orchestrator -> Planner, via mailbox enqueue)

```yaml
PlanRequest:                                 # @dataclass(frozen=True)
  intent: str                                # REQUIRED, non-empty -- user intent from TaskEnvelope
  trace_id: str                              # REQUIRED, non-empty -- cognitive_trace_id for full turn tracing
  context: Optional[SessionSnapshot]         # Hot-tier SessionState snapshot (beliefs, persona, control, temporal)
                                             # V1: Fabric SessionSnapshot directly (no ContextSnapshot wrapper)
                                             # SessionSnapshot{session_id, sections: Dict[str,Dict], timestamp_ms, section_names}
  request_id: str = uuid4()                  # Auto-generated, NEW per attempt (not envelope_id)
  constraints: Dict[str, Any] = {}           # V1: opaque dict (structured constraint schema TBD V2)
                                             # Future V2 fields: token_budget_max, cost_budget_max_usd,
                                             # safety_band, max_steps, time_constraints, permissions
  timeout_ms: int = 45_000                   # Planning budget (CB_PLANNER wraps with same timeout)
```

**Validation** (`__post_init__`):

- `intent` must be non-empty (raises `ValueError`)
- `trace_id` must be non-empty (raises `ValueError`)

**Origin**: `OrchestratorService.dispatch_high()` builds PlanRequest from `TaskEnvelope.intent`, `TaskEnvelope.constraints`, and a fresh `StateReadAdapter.get_snapshot()` for context.

---

**MicroReplanRequest** (Orchestrator -> Planner, synchronous 10s, max 1 per DAG)

```yaml
MicroReplanRequest:                          # @dataclass(frozen=True)
  original_plan_id: str                      # REQUIRED, non-empty -- plan_id of the CommittedPlan being replanned
  completed_results: Dict[str, StepResult]   # Results from completed steps (step_id -> StepResult)
                                             # StepResult{step_id, capability_name, status: StepStatus,
                                             #   duration_ms, result: Optional[CapabilityResult],
                                             #   retry_attempts, schema_retry, error_detail}
  remaining_steps: List[PlanStep]            # REQUIRED, non-empty -- only uncompleted steps from original plan
  trace_id: str                              # REQUIRED -- cognitive_trace_id
  request_id: str = uuid4()                  # Auto-generated
  discoveries: List[Discovery] = []          # Runtime discoveries that triggered replan
                                             # Discovery{field: str, value: Any, source_step_id: str}
  failure_context: Optional[FailureContext]   # Present if replan triggered by step failure
    = None                                   # FailureContext{step_id, error_code, error_message, partial_result}
```

**Validation** (`__post_init__`):

- `original_plan_id` must be non-empty
- `remaining_steps` must be non-empty

**Origin**: `MicroReplanCheckpoint` (DAGExecutor guard, ORCH-13) builds this from current DAG state when a discovery or failure triggers re-evaluation.

**Serialization**: `to_dict()` method serializes `completed_results`, `remaining_steps`, `discoveries`, `failure_context` for Planner transport.

---

**PlanAck** (Planner -> Orchestrator, immediate synchronous response)

```yaml
PlanAck:                                     # @dataclass(frozen=True)
  request_id: str                            # Echoes PlanRequest.request_id
  status: str                                # "ACCEPTED" or "REJECTED"
  estimated_duration_ms: Optional[int]       # Optional Planner estimate (V1: echoes timeout_ms on ACCEPTED)
    = None
```

**Note**: V1 PlanAck has no `reason` field. Rejection reason is conveyed via the `k1.planner.plan.failed.v1` event payload instead.

**Construction**: PlanAck is built by `PlannerAdapter` on the Orchestrator side (not by the Planner mailbox):

- Successful enqueue -> `PlanAck(request_id, "ACCEPTED", estimated_duration_ms=request.timeout_ms)`
- Failed enqueue -> `PlanAck(request_id, "REJECTED")`

---

**CommittedPlan** (Planner -> Orchestrator, via `k1.planner.plan.ready.v1` event)

```yaml
CommittedPlan:                               # @dataclass(frozen=True)
  plan_id: str                               # REQUIRED -- Planner-generated uuid (NEW, not request_id)
  request_id: str                            # REQUIRED -- echoes PlanRequest.request_id for correlation
  intent: str                                # REQUIRED -- echoed from PlanRequest.intent
  steps: List[PlanStep]                      # REQUIRED, non-empty -- ordered plan steps (see PlanStep below)
  trace_id: str                              # REQUIRED -- cognitive_trace_id
  dependencies: Dict[str, List[str]] = {}    # step_id -> [predecessor_step_ids]
                                             # Explicit DAG edges. Keys must be subset of step IDs.
                                             # No cycles allowed (Kahn's algorithm validation).
  estimated_duration_ms: Optional[int]       # Optional Planner estimate for total execution time
    = None
  created_at: float = 0.0                    # Epoch seconds (NOT ISO timestamp). Set by CommitService.
```

**V1 scope reduction**: `token_budget_max` and `cost_budget_max_usd` REMOVED (PLAN-07 DEFERRED -- no upstream data source).

**Validation** (`__post_init__`):

- `plan_id`, `request_id` must be non-empty
- `steps` must be non-empty
- `dependencies` keys must be subset of step IDs
- Each dependency target must exist in step IDs
- Dependency graph must be acyclic (Kahn's algorithm in `_check_acyclic()`)

**Serialization**: `to_dict()` for event bus transport. `from_dict()` for deserialization on Orchestrator side.

---

**PlanStep** (14 fields, embedded in CommittedPlan.steps[])

```yaml
PlanStep:                                    # @dataclass(frozen=True)
  # --- Fabric-aligned fields (1-6) ---
  id: str = ""                               # REQUIRED, e.g. "s1", "s2" -- validated non-empty
  capability: str = ""                       # REQUIRED, e.g. "tool.execute.send_message" -- validated non-empty
  params: Dict[str, Any] = {}                # Forwarded as CapabilityRequest.parameters to Fabric
  deps: List[str] = []                       # Step IDs this depends on (within CommittedPlan.steps)
  prompt_template: Optional[str] = None      # Template name reference (resolved from Fabric Prompt Registry)
  tools_granted: Optional[List[str]] = None  # FAB-07: scoped tool list for agent steps (build_agent)

  # --- Orchestrator extension fields (7-14) ---
  output_schema: Optional[Dict] = None       # JSON Schema -- OutputSchemaGuard (ORCH-15) validates against this
  condition: Optional[ConditionExpr] = None  # Structured expression tree (ORCH-16), NOT raw JSONPath
                                             # ConditionExpr{type: AND|OR|NOT|EQ|NEQ|GT|LT,
                                             #   operands: List, path: Optional[str], literal: Optional[Any]}
  is_optional: bool = False                  # True = step failure does NOT fail the plan
  has_side_effects: bool = False             # From Fabric CapabilityDescriptor -- drives rollback decisions
  compensation: Optional[str] = None         # Capability to call on rollback if has_side_effects=True
  timeout_ms: Optional[int] = None           # Per-step timeout, seeded from Fabric estimated_duration_ms
                                             # Must be > 0 if set (validated in __post_init__)
  required_context: Optional[List[str]]      # SessionState sections needed before execution
    = None
  safety_band_min: Optional[str] = None      # Minimum safety band for this step (GREEN, AMBER, RED)
```

**V1 scope reduction**: `token_budget` per step REMOVED (PLAN-07 DEFERRED).

**Validation** (`__post_init__`):

- `id` must be non-empty
- `capability` must be non-empty
- `timeout_ms` must be > 0 if set

**Meta-Agent DAG pattern**: Steps MAY use `tool.meta.build_agent` capability to compose agent-based execution:

```yaml
# Step 1: build agent
- id: "s1"
  capability: "tool.meta.build_agent"
  params:
    name: "health_advisor"
    role: "Provide personalized health advice"
    tools_granted: ["tool.search.medical", "tool.knowledge.nutrition"]
    prompt_template: "health_advisor_v1"
    seed_context: { user_age: 35 }
    ttl_turns: 3
  deps: []
  output_schema: { agent_name: "string" }

# Step 2: invoke agent (dynamic capability reference)
- id: "s2"
  capability: "$s1.result.agent_name"          # resolved at runtime by ParamResolver
  params: { query: "What vitamins should I take?" }
  deps: ["s1"]
```

The Planner discovers and composes `AgentSpec` via `discover_capabilities()`. The Orchestrator's DAGExecutor and Fabric execute the agent (PLAN-06: Planner never executes capabilities).

---

**Supporting types referenced in envelopes**:

```yaml
ConditionExpr:                               # @dataclass(frozen=True)
  type: str                                  # AND | OR | NOT | EQ | NEQ | GT | LT
  operands: List[Any] = []                   # Sub-expressions for composite operators (AND, OR, NOT)
  path: Optional[str] = None                 # References prior step result: "s1.status", "s1.result.data.count"
  literal: Optional[Any] = None              # Comparison value for leaf operators (EQ, NEQ, GT, LT)
  # V1: simple comparisons only (no function calls)

Discovery:                                   # @dataclass(frozen=True)
  field: str                                 # Discovery field name
  value: Any = None                          # Discovery value
  source_step_id: str = ""                   # Which step produced this discovery

FailureContext:                              # @dataclass(frozen=True)
  step_id: str                               # Which step failed
  error_code: str                            # Error classification code
  error_message: str                         # Human-readable error message
  partial_result: Optional[Dict[str, Any]]   # Any partial output before failure
    = None

StepResult:                                  # @dataclass(frozen=True)
  step_id: str                               # Which step this result is for
  capability_name: str                       # Capability that was executed
  status: StepStatus                         # PENDING | RUNNING | COMPLETED | FAILED | CANCELLED | SKIPPED
  duration_ms: int = 0                       # Actual execution time
  result: Optional[CapabilityResult] = None  # Fabric CapabilityResult (success, data, metadata)
  retry_attempts: int = 0                    # How many retries were attempted
  schema_retry: bool = False                 # Whether schema retry was triggered (ORCH-15)
  error_detail: Optional[str] = None         # Error description if status=FAILED

SessionSnapshot:                             # @dataclass(frozen=True) - from k1.fabric.ports.state_reader
  session_id: str = ""                       # Session identifier
  sections: Dict[str, Dict[str, Any]] = {}   # Section name -> section data
  timestamp_ms: int = 0                      # Epoch ms when snapshot was captured
  section_names: List[str] = []              # Ordered list of available sections (auto-populated)
```

### 4.6 HIL Response Events (Inbound via Event Bus)

These events arrive via the Event Bus when the user responds to a Planner-initiated HIL interaction. They are NOT enqueued to the Planner mailbox -- they are handled by the `HILCoordinator` via event subscription.

**HILClarificationResponse** (Concierge -> Planner, topic: `k1.hil.clarification_response.v1`)

```yaml
HILClarificationResponse:
  request_id: uuid                           # Correlates to original HIL clarification request
  plan_id: uuid                              # Plan being clarified
  user_response: str                         # User's answer to the clarification question
  trace_id: str                              # Cognitive trace ID
```

**HILApprovalResponse** (Concierge -> Planner, topic: `k1.hil.approval_response.v1`)

```yaml
HILApprovalResponse:
  request_id: uuid                           # Correlates to original approval request
  plan_id: uuid                              # Plan being approved
  response_type: str                         # "approve" | "modify" | "reject"
  modifications: Optional[Dict]             # User modifications (if response_type=modify)
  trace_id: str                              # Cognitive trace ID
```

### 4.7 Message Flow Summary

```
                   ORCHESTRATOR SIDE                    |                    PLANNER SIDE
                                                        |
  dispatch_high()                                       |
    |                                                   |
    v                                                   |
  PlannerAdapter                                        |
    |-- _check_cb_open() -----> CB_PLANNER state?       |
    |   (if OPEN: raise AdapterException DEGRADED)      |
    |                                                   |
    |-- enqueue(PlanRequest) ----mailbox boundary------>|-- Planner Mailbox (FIFO, max 5)
    |<- (success: cb.reset, return PlanAck ACCEPTED)    |       |
    |   (failure: cb.trip, return PlanAck REJECTED)     |       v
    |                                                   |   PlannerAgent.dequeue()
    |   save PendingPlanContext{request_id}              |       |
    |                                                   |       v
    |                                                   |   PipelineController
    |                                                   |       SKETCH -> EXPAND -> VALIDATE -> COMMIT
    |                                                   |       |
    |   Event Bus <----------k1.planner.plan.ready.v1---|<------+-- CommittedPlan
    |       |                                           |
    v       v                                           |
  OrchestratorService.receive_plan()                    |
    correlate via request_id -> PendingPlanContext       |
    enqueue CommittedPlan to Orchestrator Mailbox        |
    begin DAG execution                                 |
                                                        |
  --- micro-replan (mid-DAG, synchronous) ---           |
                                                        |
  MicroReplanCheckpoint                                 |
    |                                                   |
    v                                                   |
  PlannerAdapter.micro_replan()                         |
    |-- _check_cb_open()                                |
    |-- asyncio.wait_for(10s) -direct method call------>|-- IPlannerMailbox.micro_replan()
    |                                                   |       |
    |                                                   |       v
    |                                                   |   PipelineController (abbreviated)
    |                                                   |       MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE -> COMMIT
    |<------- CommittedPlan (or timeout=None) ----------|<------+
    |                                                   |
    v                                                   |
  DAGExecutor merges replacement steps                  |
```

---

## 5. Full Planning Pipeline Flow

End-to-end sequence from PlanRequest arrival to CommittedPlan delivery, traced through every component and interaction boundary.

### 5.1 Pre-Conditions (Orchestrator Side -- Already Implemented)

Before the Planner receives anything, the Orchestrator has already executed **6 steps** in `_dispatch_high()` (source: `k1/orchestrator/orchestration/orchestrator_service.py` line 1514):

```
Orchestrator._dispatch_high(envelope: TaskEnvelope{tier=HIGH}):
  1. Capture state snapshot: state_port.get_snapshot(session_id) -> SessionSnapshot
     (proceeds with None if snapshot fails -- Planner can work without context)
  2. Generate request_id: uuid4() -- NEW per attempt (not envelope_id)
  3. Build PlanRequest{intent, trace_id, context=snapshot, request_id, constraints, timeout_ms}
  4. Send to Planner: planner_port.request_plan(plan_request)
     -> PlannerAdapter checks CB_PLANNER state (if OPEN: raise AdapterException DEGRADED)
     -> PlannerAdapter calls IPlannerMailbox.enqueue(plan_request)
     -> Returns PlanAck{ACCEPTED} or PlanAck{REJECTED}
  5. Guard: pending_plans capacity check (max_pending_plans)
  6. Park context: pending_plans[request_id] = PendingPlanContext{
       request_id, task_envelope, state_snapshot, created_at, timeout_ms=45000
     }
  7. Emit ORCH_PLAN_REQUESTED delta (fire-and-forget)
  8. Return ProcessResult.DEFERRED
```

**After step 8, the Orchestrator is done**. It resumes its mailbox loop and can process other messages. The Planner now owns the request.

### 5.2 Planner Pipeline Sequence (26 Steps)

```
 PLANNER INTERNAL FLOW
 ======================

 --- LIFECYCLE: PLAN_START ---

  1. MAILBOX DEQUEUE
     PlannerAgent dequeues PlanRequest from Planner Mailbox (FIFO).
     If mailbox is empty: PlannerAgent awaits (async sleep/event wait).
     If plan lock is held (V1 single plan): request stays queued until lock released.

  2. ACQUIRE PLAN LOCK
     V1: single-threaded. Plan lock prevents concurrent planning.
     Set occupied = True. If another request arrives, it queues in mailbox.

  3. EMIT PlanAck
     PlanAck is constructed by PlannerAdapter on Orchestrator side (not here).
     Planner's responsibility begins AFTER successful enqueue.
     NOTE: PlannerAdapter already returned PlanAck(ACCEPTED) to Orchestrator
     synchronously during enqueue (step 4 of pre-conditions).

  4. INITIALIZE PIPELINE STATE
     PipelineController resets:
       - stage_token_usage = {SKETCH: 0, EXPAND: 0, VALIDATE: 0, COMMIT: 0}
       - tool_call_count = 0
       - hil_round_count = 0
       - current_request = PlanRequest
       - plan_start_time = now()
     Plan FSM transitions: IDLE -> SKETCHING

  5. EMIT DELTA: k1.planner.delta.v1{stage: "SKETCH", status: "started"}

 --- STAGE 1: SKETCH (LLM -- ~2K tokens, 3-8s) ---

  6. DISCOVERY TOOL CALLS (concurrent, 3 calls max via ToolCallRouter)
     6a. discover_capabilities(domain=inferred, intent=PlanRequest.intent)
         Route: ToolCallRouter -> IFabricRetrievalPort -> FabricRetrievalAdapter
                -> Fabric.discover_capabilities()
         Returns: Top-K RetrievalResult[] with capability names, input/output schemas
         Latency: <50ms
         ToolCallRouter: tool_call_count += 1

     6b. query_planning_context(sections=["beliefs_active", "persona", "control", "temporal"])
         Route: ToolCallRouter -> IStateReadPort -> SessionStateReadAdapter
                -> SessionState multi-reader (lock-free, PLAN-01)
         Returns: StateSnapshot{sections: {beliefs_active: {...}, persona: {...}, ...}}
         Latency: <10ms
         ToolCallRouter: tool_call_count += 1

     6c. recall_for_planning(query=PlanRequest.intent)
         Route: ToolCallRouter -> IBridgePort -> BridgeAdapter -> K0 Bridge
         Returns: RecallResponse with historical preferences, prior outcomes
         Latency: <100ms
         ToolCallRouter: tool_call_count += 1

     After 6a-6c: tool_call_count = 3 (of max 6, PLAN-05)

  7. HIL CLARIFICATION CHECK (conditional)
     SketchService evaluates: is intent ambiguous? Missing critical constraints?
     IF ambiguous AND hil_round_count < 2 (PLAN-10):
       7a. LLM: generate clarification question (~300 tokens)
           HubRequest{capability: CHAT, constraints: {max_tokens: 300, timeout_ms: 3000},
                      payload: ChatPayload{...}, trace_id, consumer_id: "planner"}
           Route: ILLMPort -> LLMGatewayAdapter -> Model Hub
       7b. Emit k1.hil.clarification.v1{request_id, plan_id, question}
           Route: IEventPort -> EventBusAdapter -> Event Bus -> Concierge -> User
       7c. WAIT for k1.hil.clarification_response.v1 (60s timeout per round)
           HILCoordinator subscribes, correlates by request_id
           Response: HILClarificationResponse{user_response}
           hil_round_count += 1
       7d. IF timeout: proceed with best-effort interpretation (ERR_HIL_TIMEOUT)
       7e. IF second round needed AND hil_round_count < 2: repeat 7a-7d
           ELSE: proceed with what we have (PLAN-10 enforced)

  8. SKETCH LLM CALL
     SketchService assembles prompt:
       Input: PlanRequest.intent + discovered_capabilities[] + state_snapshot + recall_results
       + any HIL clarification responses
     HubRequest{
       capability: CHAT,
       payload: ChatPayload{messages: [system_prompt, user_intent, context_injection]},
       constraints: RequestConstraints{max_tokens: 2048, timeout_ms: 8000,
                                        consumer_id: "planner"},
       trace_id: PlanRequest.trace_id
     }
     Route: ILLMPort -> LLMGatewayAdapter -> LLM_REQUEST_BUS -> Model Hub

     Model Hub:
       - Routes based on capability=CHAT
       - Selects model per provider manifest (Planner does NOT choose model)
       - Enforces max_tokens and timeout_ms
       - Returns HubResponse{result, metadata{model_id, latency_ms, usage{tokens}}}

     SketchService parses HubResponse.result into SketchResult:
       SketchResult{
         rough_steps: [
           {intent: "book restaurant", capability_hint: "tool.execute.restaurant_booking"},
           {intent: "order cake", capability_hint: "tool.execute.cake_order"},
           {intent: "get contacts", capability_hint: "tool.read.k0_recall"},
           {intent: "send invitations", capability_hint: "agent.execute.invitation_sender",
            depends_on: ["book restaurant", "get contacts"]}
         ],
         capability_candidates: ["tool.execute.restaurant_booking", "tool.execute.cake_order", ...],
         rationale: "Multi-step event planning with parallel independent tasks..."
       }

     stage_token_usage[SKETCH] += HubResponse.metadata.usage.total_tokens

  9. STAGE 1 COMPLETE
     Plan FSM transitions: SKETCHING -> EXPANDING
     Emit: k1.planner.delta.v1{stage: "SKETCH", status: "completed",
                                tokens_used: stage_token_usage[SKETCH]}

 --- STAGE 2: EXPAND (LLM -- ~1K tokens, 2-5s) ---

 10. DISCOVERY TOOL CALLS (up to 3 more, from remaining budget of 3)
     10a. discover_capabilities(specific queries per rough step)
          Refines Top-K: e.g., "restaurant booking near San Jose" -> exact capabilities
          ToolCallRouter: tool_call_count += 1 (now 4)

     10b. find_relevant_prompts(intent=PlanRequest.intent, domain=inferred)
          Route: ToolCallRouter -> IFabricRetrievalPort -> FabricRetrievalAdapter
                 -> Fabric.find_relevant_prompts()
          Returns: Top-K prompt templates with variable definitions
          Latency: <50ms
          ToolCallRouter: tool_call_count += 1 (now 5)

     (Optional 10c: if 6th call needed for specific capability lookup)
          ToolCallRouter: tool_call_count += 1 (now 6, MAX reached PLAN-05)

     After Stage 2 tools: tool_call_count <= 6 (PLAN-05 enforced)

 11. EXPAND LLM CALL
     ExpandService assembles prompt:
       Input: SketchResult + refined_capabilities[] + prompt_templates[]
     HubRequest{
       capability: CHAT,
       constraints: RequestConstraints{max_tokens: 1024, timeout_ms: 5000,
                                        consumer_id: "planner"},
       trace_id: PlanRequest.trace_id
     }
     Route: ILLMPort -> Model Hub (same as step 8)

     ExpandService parses HubResponse.result into ExpandedPlan:
       ExpandedPlan{
         steps: [
           PlanStep{id: "s1", capability: "tool.execute.restaurant_booking",
                    params: {date: "2026-02-21", party_size: 8, cuisine: "Italian"},
                    deps: [], prompt_template: null, tools_granted: null,
                    output_schema: {venue: "string", confirmation_id: "string"},
                    timeout_ms: 10000, has_side_effects: true,
                    compensation: "tool.execute.restaurant_cancel"},
           PlanStep{id: "s2", capability: "tool.execute.cake_order",
                    params: {type: "birthday", flavor: "chocolate", date: "2026-02-21"},
                    deps: [], prompt_template: null, tools_granted: null,
                    output_schema: {order_id: "string", delivery_time: "string"},
                    timeout_ms: 8000, has_side_effects: true,
                    compensation: "tool.execute.cake_cancel"},
           PlanStep{id: "s3", capability: "tool.read.k0_recall",
                    params: {query: "family contact info"},
                    deps: [], prompt_template: null, tools_granted: null,
                    output_schema: {contacts: "array"},
                    timeout_ms: 5000, has_side_effects: false},
           PlanStep{id: "s4", capability: "agent.execute.invitation_sender",
                    params: {event: "birthday_party", recipients: "$s3.result.contacts",
                             venue: "$s1.result.venue"},
                    deps: ["s1", "s3"], prompt_template: "invitation_drafter_v1",
                    tools_granted: ["tool.execute.send_message", "tool.read.contact_lookup"],
                    output_schema: {sent_count: "number", failed: "array"},
                    timeout_ms: 30000, has_side_effects: true,
                    compensation: null, is_optional: false}
         ],
         dependencies: {"s4": ["s1", "s3"]}
       }

     stage_token_usage[EXPAND] += HubResponse.metadata.usage.total_tokens

 12. STAGE 2 COMPLETE
     Plan FSM transitions: EXPANDING -> VALIDATING
     Emit: k1.planner.delta.v1{stage: "EXPAND", status: "completed",
                                tokens_used: stage_token_usage[EXPAND]}

 --- STAGE 3: VALIDATE (LLM Arbiter -- ~500 tokens, 1-3s) ---

 13. DETERMINISTIC CHECKS (no LLM, ValidateService)
     13a. DAG Cycle Detection (Kahn's algorithm):
          Build adjacency from dependencies dict. Compute in-degrees.
          Walk topological order. If visited != step_count: REJECT (cycle found).
          For birthday example: s1,s2,s3 have in-degree 0; s4 depends on s1,s3.
          Topological sort succeeds (4 visited = 4 steps). DAG is acyclic.

     13b. Capability Existence Check:
          For each step.capability: query Fabric Registry to confirm it exists.
          Route: IFabricRetrievalPort (or cached from Stage 2 discovery)
          For birthday example: all 4 capabilities verified present in Fabric.

     IF either check fails: plan REJECTED (no LLM arbiter needed).

 14. LLM ARBITER CALL
     ValidateService assembles prompt:
       Input: ExpandedPlan + PlanRequest.intent + PlanRequest.constraints
       Asks: Is this plan coherent? Safe? Complete? Feasible?
     HubRequest{
       capability: STRUCTURED,
       constraints: RequestConstraints{max_tokens: 512, timeout_ms: 3000,
                                        consumer_id: "planner"},
       trace_id: PlanRequest.trace_id
     }
     Route: ILLMPort -> Model Hub

     Arbiter returns structured verdict:
       ValidationVerdict{
         status: "approved" | "revise" | "reject",
         reasons: [...],
         suggested_fixes: [...]
       }

     stage_token_usage[VALIDATE] += HubResponse.metadata.usage.total_tokens

 15. VERDICT ROUTING
     IF status == "approved": proceed to Stage 4.
     IF status == "revise":
       - Retry EXPAND once (go back to step 11 with suggested_fixes injected).
       - If second EXPAND also gets "revise": treat as "approved" (best-effort).
     IF status == "reject":
       - Retry EXPAND once (full re-expansion with rejection reasons).
       - If second verdict is still "reject": plan FAILED.
       - Emit k1.planner.plan.failed.v1{request_id, reason, stage: "VALIDATE"}.
       - Plan FSM transitions to FAILED.

 16. HIL APPROVAL CHECK (conditional)
     ValidateService evaluates: does plan contain HIGH-impact operations?
     Criteria: steps with has_side_effects=true that affect external systems.
     IF high-impact AND not auto-approvable:
       16a. LLM: format plan summary + options (~400 tokens)
            HubRequest{capability: CHAT, constraints: {max_tokens: 400, timeout_ms: 3000}}
       16b. Emit k1.hil.approval_request.v1{request_id, plan_id, summary, options}
            Route: IEventPort -> Event Bus -> Concierge -> User
       16c. WAIT for k1.hil.approval_response.v1 (120s timeout)
            HILCoordinator subscribes, correlates by request_id
            Response: HILApprovalResponse{response_type: "approve"|"modify"|"reject"}
       16d. IF response_type == "approve": proceed to Stage 4
       16e. IF response_type == "modify": apply modifications, re-validate (step 13)
       16f. IF response_type == "reject": plan FAILED
       16g. IF timeout: auto-approve if all steps are safe (no safety_band_min=RED)
            ELSE: plan FAILED

 17. STAGE 3 COMPLETE
     Plan FSM transitions: VALIDATING -> COMMITTING
     Emit: k1.planner.delta.v1{stage: "VALIDATE", status: "completed",
                                tokens_used: stage_token_usage[VALIDATE]}

 --- STAGE 4: COMMIT (Deterministic -- 0 tokens, <100ms, PLAN-03) ---

 18. ASSIGN PLAN ID
     CommitService generates plan_id = uuid4()
     CommitService sets created_at = time.time() (epoch seconds)

 19. BUILD CommittedPlan
     CommitService assembles:
       CommittedPlan{
         plan_id: "a7f3...",
         request_id: PlanRequest.request_id,        -- echoed for Orchestrator correlation
         intent: PlanRequest.intent,                 -- echoed
         steps: [PlanStep(s1), PlanStep(s2), PlanStep(s3), PlanStep(s4)],
         trace_id: PlanRequest.trace_id,             -- echoed
         dependencies: {"s4": ["s1", "s3"]},
         estimated_duration_ms: 60000,               -- Planner's estimate (optional)
         created_at: 1739523800.0                    -- epoch seconds
       }
     CommitService has NO ILLMPort dependency (PLAN-03 enforced at constructor level).
     stage_token_usage[COMMIT] = 0

 20. PERSIST TO K0 WAL
     CommitService calls IBridgePort.persist_plan(committed_plan)
     Route: BridgeAdapter -> K0 Bridge -> WAL write
     Fire-and-forget: plan is valid even if WAL fails (idempotent via plan_id dedup key).
     On failure: log warning, retry once, proceed anyway.

 21. EMIT PLAN READY EVENT
     CommitService calls IEventPort.publish(
       topic="k1.planner.plan.ready.v1",
       payload=committed_plan.to_dict()
     )
     Route: EventBusAdapter -> K1 Event Bus
     Consumers: Orchestrator (primary), Learning Loop (observability)

 22. STAGE 4 COMPLETE
     Plan FSM transitions: COMMITTING -> COMPLETED
     Emit: k1.planner.delta.v1{stage: "COMMIT", status: "completed", plan_id: "a7f3..."}

 --- LIFECYCLE: PLAN_END ---

 23. RELEASE PLAN LOCK
     Set occupied = False. PlannerAgent can now dequeue next PlanRequest.

 24. CLEAR STATE
     PipelineController clears: stage_token_usage, tool_call_count, hil_round_count,
     current_request. ToolCallRouter resets counter. HILCoordinator resets round counter.

 25. PLAN_END DELTA
     Emit: k1.planner.delta.v1{type: "plan_end", plan_id, total_tokens, total_duration_ms}

 26. RESUME IDLE
     Plan FSM transitions: COMPLETED -> IDLE (ready for next request)
     PlannerAgent returns to step 1 (mailbox dequeue await).
```

### 5.3 Post-Conditions (Orchestrator Side -- Already Implemented)

After the Planner emits `k1.planner.plan.ready.v1`, the Orchestrator picks it up:

```
Orchestrator Event Subscription (already running, source: orchestrator_service.py line 554):
  _on_plan_ready(topic, payload):
    1. Deserialize payload -> CommittedPlan{plan_id, request_id, intent, steps, ...}
    2. Enqueue CommittedPlan to Orchestrator Mailbox at INTERACTIVE priority
    3. Log: "on_plan_ready.enqueued"

Orchestrator Mailbox Loop dequeues CommittedPlan, routes to _receive_plan():
  _receive_plan(plan: CommittedPlan):
    1. RACE-3 dedup: check executed_plans LRU for plan_id. If duplicate, return COMPLETED.
    2. Correlate: pending_plans.pop(request_id) -> PendingPlanContext
       If no match (orphan, RACE-2): log warning, attempt WAL recovery, return FAILED.
    3. Record plan_id in executed_plans LRU (for dedup).
    4. RACE-1: re-read state snapshot for freshness (20-60s may have elapsed).
    5. Validate plan via ConstraintResolver.validate(plan, ctx).
    6. Acquire ConcurrencyGuard (V1: single DAG at a time).
    7. Execute DAG via DAGExecutor.execute(plan, ctx).
       -> Topological waves -> concurrent Fabric calls -> results
    8. Release ConcurrencyGuard.
    9. Emit result + audit.
```

### 5.4 End-to-End Timing Budget

```
 PHASE                          OWNER           BUDGET
 ===========================================================================
 dispatch_high() pre-setup      Orchestrator    <100ms (snapshot + enqueue)
 ------- MAILBOX BOUNDARY -------
 Mailbox wait (queue depth)     Planner         0-5s (depends on queue)
 Stage 1 SKETCH                 Planner         3-8s (LLM + 3 tools + optional HIL)
 Stage 2 EXPAND                 Planner         2-5s (LLM + 2-3 tools)
 Stage 3 VALIDATE               Planner         1-3s (deterministic + LLM arbiter + optional HIL)
 Stage 4 COMMIT                 Planner         <100ms (deterministic, no LLM)
 Event Bus delivery             Bus             <10ms
 ------- EVENT BUS BOUNDARY -------
 _on_plan_ready deserialization Orchestrator    <5ms
 _receive_plan correlation      Orchestrator    <10ms
 ConstraintResolver validation  Orchestrator    <50ms
 DAG execution (all waves)      Orchestrator    2-60s (depends on step count + Fabric)
 ===========================================================================
 TOTAL (Planner portion):       Planner         10-30s (within 45s CB timeout)
 TOTAL (end-to-end HIGH):       System          15-90s (planning + execution)
```

### 5.5 Worked Example: Birthday Party (Planner's Internal View)

```
INPUT:
  PlanRequest{
    intent: "Plan a birthday party for Mom next Saturday --
             book a restaurant, order a cake, and send invitations to family",
    trace_id: "ct-9f8a...",
    context: SessionSnapshot{
      sections: {
        beliefs_active: {family_members: ["Dad", "Sis", "Bro", ...], mom_birthday: "Feb 21"},
        persona: {tone: "warm", formality: "casual"},
        control: {safety_band: "GREEN"},
        temporal: {now: "2026-02-14T10:30:00", device_tz: "America/Los_Angeles"}
      }
    },
    request_id: "req-a1b2...",
    constraints: {safety_band: "GREEN"},
    timeout_ms: 45000
  }

STAGE 1 SKETCH (6.2s):
  Tool calls (concurrent):
    discover_capabilities("birthday party restaurant booking cake ordering invitations")
      -> [{name: "tool.execute.restaurant_booking", input: {date, party_size, cuisine}},
          {name: "tool.execute.cake_order", input: {type, flavor, date}},
          {name: "tool.read.k0_recall", input: {query}},
          {name: "agent.execute.invitation_sender", tools: [send_message, contact_lookup]}]
    query_planning_context(["beliefs_active", "persona", "temporal"])
      -> {beliefs_active: {family_members: 8, mom_birthday: "Feb 21"}, ...}
    recall_for_planning("Mom birthday party preferences")
      -> {facts: ["Mom prefers Italian food", "Last party was at Olive Garden"]}

  HIL check: intent is clear (4 explicit sub-tasks) -> no clarification needed

  LLM call (2,048 tokens budget):
    Prompt: "Given intent + 4 capabilities + context (8 family members, Mom prefers Italian,
             next Saturday = Feb 21). Create a rough plan."
    Response: SketchResult{
      rough_steps: [
        {intent: "book Italian restaurant for 8 on Feb 21"},
        {intent: "order chocolate birthday cake for Feb 21"},
        {intent: "retrieve family contact info from K0"},
        {intent: "send personalized invitations to 8 family members (needs restaurant + contacts)"}
      ],
      rationale: "Parallel independent tasks (restaurant, cake, contacts) then sequential invitations"
    }
  Tokens used: 1,847. Duration: 5.2s.

STAGE 2 EXPAND (3.1s):
  Tool calls:
    discover_capabilities("Italian restaurant booking San Jose Feb 21")
      -> refined: tool.execute.restaurant_booking with exact param schema
    find_relevant_prompts("family event invitation")
      -> [{name: "invitation_drafter_v1", variables: [event, recipients, venue, date]}]

  LLM call (1,024 tokens budget):
    Prompt: "Map rough steps to concrete PlanStep with params, deps, output_schema."
    Response: ExpandedPlan with 4 PlanSteps (as shown in step 11 above)
  Tokens used: 943. Duration: 2.4s.

STAGE 3 VALIDATE (1.8s):
  Deterministic checks:
    DAG cycle detection: s1,s2,s3 (in-degree 0), s4 depends on s1,s3.
      Topological order: [s1,s2,s3] -> [s4]. 4 visited = 4 steps. PASS.
    Capability existence: all 4 capabilities confirmed in Fabric. PASS.

  LLM arbiter (512 tokens budget):
    Prompt: "Validate plan for: birthday party. 4 steps, 3 parallel + 1 sequential.
             Safety: GREEN. Side effects: restaurant booking, cake order, message sending."
    Verdict: {status: "approved", reasons: ["coherent", "safe", "complete"]}
  Tokens used: 287. Duration: 1.1s.

  HIL approval check: 3 steps with has_side_effects=true, all GREEN safety.
    Auto-approve (all safe, no RED operations). Skip HIL.

STAGE 4 COMMIT (42ms):
  plan_id = "plan-a7f3..."
  created_at = 1739523812.0
  CommittedPlan assembled (4 steps, dependencies: {s4: [s1, s3]})
  Persist to K0 WAL: success (12ms)
  Emit k1.planner.plan.ready.v1: published (3ms)

TOTALS:
  Duration: 11.9s (well within 45s budget)
  Tokens: 3,077 (SKETCH: 1,847 + EXPAND: 943 + VALIDATE: 287 + COMMIT: 0)
  Tool calls: 5 (within max 6, PLAN-05)
  HIL rounds: 0
  Plan: 4 steps, 2 waves -- Wave 1: [s1, s2, s3], Wave 2: [s4]

OUTPUT:
  CommittedPlan -> k1.planner.plan.ready.v1 -> Orchestrator Event Bus
  Orchestrator._on_plan_ready() -> enqueue to Orchestrator Mailbox
  Orchestrator._receive_plan() -> correlate via "req-a1b2..." -> PendingPlanContext
  DAGExecutor.execute() -> Wave 1 (3 concurrent Fabric calls) -> Wave 2 (1 agent call)
```

### 5.6 Failure Scenarios

| Step | Failure | Recovery | Outcome |
|------|---------|----------|---------|
| 6a-6c | Discovery tool timeout | ToolCallRouter retries once, then proceeds without that tool's result | Degraded SKETCH quality (fewer capabilities known) |
| 7c | HIL clarification timeout (60s) | Proceed with best-effort interpretation | May produce less precise plan |
| 8 | SKETCH LLM timeout/error | Retry once with simplified prompt (remove memory context). If still fails: plan FAILED | k1.planner.plan.failed.v1 |
| 11 | EXPAND LLM timeout/error | Retry once. If still fails: fallback to SKETCH output as-is (degraded) | Less precise tool mapping, proceed to VALIDATE |
| 14 | VALIDATE LLM arbiter down | Auto-approve IF deterministic checks all passed | Reduced safety (no LLM coherence check) |
| 15 | Verdict = "reject" after retry | Plan FAILED | k1.planner.plan.failed.v1{stage: "VALIDATE"} |
| 16c | HIL approval timeout (120s) | Auto-approve if all steps are safe | Reduced oversight |
| 20 | K0 WAL persist fails | Log warning, retry once, proceed anyway | Plan still valid (WAL is durability, not correctness) |
| 21 | Event Bus publish fails | Retry once. If still fails: plan completed but undeliverable | Orchestrator timeout reaper cleans up PendingPlanContext |
| All | Total time > 45s | CB_PLANNER (Orchestrator side) trips. AdapterException(DEGRADED) on next call | Orchestrator degrades future HIGH -> MEDIUM |

---

## 6. Stage 1: SKETCH -- Deep Dive

LLM-powered rough plan generation. Performance envelope: ~2K tokens, p50 4s / p99 8s.
This is the creative core of planning -- where intent becomes structure.

Plan FSM transition on entry: `IDLE -> SKETCHING`. On exit: `SKETCHING -> EXPANDING`.

SketchService is the owning internal service (~60 tests). It coordinates 3 tool calls
via ToolCallRouter, an optional HIL clarification round via HILCoordinator, and exactly
one LLM call via ILLMPort. SketchService has dependencies on:

- `ILLMPort` (LLM call)
- `ToolCallRouter` (routes 3 discovery tools to backends)
- `HILCoordinator` (optional clarification)
- `PipelineController` (receives stage result, tracks token usage)

### 6.1 Inputs

SketchService receives the dequeued `PlanRequest` from PipelineController. The fields
consumed during SKETCH:

```
PlanRequest (from k1.orchestrator.types):
  intent: str              -- Natural-language user request (required, non-empty)
  request_id: str          -- Echoed back in PlanAck + CommittedPlan (correlation key)
  trace_id: str            -- Cognitive trace ID (passed to all port calls, FAB-09)
  context: SessionSnapshot -- Point-in-time SessionState from Orchestrator dispatch_high()
  constraints: Dict        -- {safety_band: str, ...} (optional overrides)
  timeout_ms: int          -- Caller's deadline (Orchestrator sets 45000, PLAN-04)
```

SessionSnapshot (from `k1.fabric.ports.state_reader.SessionSnapshot`) provides the
already-captured state at dispatch time:

```
SessionSnapshot (frozen dataclass):
  session_id: str                           -- Session this belongs to
  sections: Dict[str, Dict[str, Any]]       -- Section name -> section data
  timestamp_ms: int                         -- Capture epoch ms
  section_names: List[str]                  -- Sorted section names present
```

Available section names from `ISessionStateReader` that SKETCH may consume:

| Section | Contents | SKETCH Usage |
|---------|----------|-------------|
| `beliefs_active` | Active belief set (entities, relationships, facts) | Ground plan in known facts |
| `persona` | Tone, formality, user communication preferences | Shape LLM prompt style |
| `control` | Safety band, user preferences, policy overrides | Constrain capability selection |
| `temporal` | Current time, device timezone, recurring schedules | Time-aware step sequencing |
| `cognitive` | Cognitive load / complexity tier | Not used in SKETCH |
| `history_recent` | Recent conversation turns | Contextual disambiguation |
| `scoreboard` | Current QUD (question under discussion) | Clarify primary objective |

**Important**: The `context` snapshot in PlanRequest is captured by Orchestrator's
`dispatch_high()` at enqueue time. By the time SKETCH runs (after mailbox wait, 0-5s),
the snapshot may be slightly stale. This is acceptable -- Orchestrator re-reads fresh
state at execution time (_receive_plan step 4) to catch any changes during planning.

SketchService also receives the constraints dict which defaults to:

```
constraints: {
  safety_band: "GREEN"    -- from PlanRequest.constraints or SessionSnapshot.control
}
```

### 6.2 Discovery Tool Calls (3 max, concurrent)

SKETCH issues up to 3 tool calls through ToolCallRouter. These are the first 3 of the
6-call budget for the entire plan (PLAN-05: max 6 discovery tool calls per plan, 3 in
SKETCH + 3 in EXPAND). All tools are read-only (PLAN-02). The Planner NEVER executes
capabilities (PLAN-06).

ToolCallRouter dispatches each call to the correct backend port. Calls are issued
concurrently (asyncio.gather or equivalent).

#### 6.2.1 Tool 1: `discover_capabilities(domain?, intent?)`

**Route**: ToolCallRouter -> `IFabricRetrievalPort` -> `FabricRetrievalAdapter`
         -> `RetrievalEngine.discover_capabilities()` (in-process, NOT HTTP)

**Backend signature** (from `k1/fabric/retrieval/retrieval_engine.py`):

```python
def discover_capabilities(
    self,
    domain: Optional[List[str]] = None,   # Domain tag filter (e.g. ["cooking", "scheduling"])
    intent: str = "",                      # Natural-language capability description
    safety_band: str = "GREEN",            # Caller's safety band
    session_context: Optional[Dict[str, Any]] = None,  # Available session keys
    top_k: Optional[int] = None,           # Results cap (default: 10, max: 25)
) -> RetrievalResult
```

**Pipeline** (4-step semantic retrieval):

```
 1. Embed intent text -> query_vector (IEmbeddingPort, ultrabert-v4.0.0)
 2. HardFilter -> eliminate offline / unsafe / unsatisfiable capabilities
    - Safety band check: capability.safety_band_min <= caller safety_band
    - Availability check: must be ONLINE
    - Required inputs check: caller must have matching session keys / params
 3. SoftRanker -> composite scoring (cosine similarity + domain match + success rate + cost)
 4. TopKSelector -> truncate to top K results
```

**Return type** (from `k1/fabric/types.py`):

```
RetrievalResult (frozen dataclass):
  capabilities: List[ScoredCapability]   -- Top-K results, descending by score
  total_matched: int                     -- Total after hard filter (>= len(capabilities))
  query_latency_ms: int                  -- End-to-end retrieval time
  query_intent: str                      -- Echo of input intent
  index_size: int                        -- Total capabilities in index
  embedding_model: str                   -- "ultrabert-v4.0.0"

ScoredCapability (frozen dataclass):
  contract: CapabilityContract           -- Full capability snapshot
  score: float                           -- Cosine similarity [0.0, 1.0]
```

Each `CapabilityContract` carries (relevant fields for SKETCH):

```
CapabilityContract (frozen dataclass, from k1/fabric/types.py):
  name: str               -- e.g. "tool.execute.restaurant_booking"
  version: str            -- semver
  domain: List[str]       -- ["dining", "scheduling"]
  description: str        -- Human-readable purpose
  capabilities: List[str] -- What it can do
  limitations: List[str]  -- What it cannot do
  required_inputs: List[InputSpec]   -- Parameter specs
  optional_inputs: List[InputSpec]   -- Optional parameter specs
  required_context: List[str]        -- SessionState sections needed
  output: Dict[str, Any]             -- JSON Schema fragment
  provider_type: str       -- "tool", "agent", "prompt", etc.
  safety_band_min: str     -- Minimum safety band required
  cost_per_call: float     -- Cost estimate
  avg_latency_ms: int      -- Average latency estimate
  availability: str        -- ONLINE / OFFLINE / DEGRADED
```

**Latency target**: <50ms per call (`FabricRetrievalAdapter` timeout: 50ms, 1 retry).
**Performance targets**: RetrievalEngine: <20ms for 10K capabilities, <50ms for 100K.

**What SKETCH uses from the result**: The SketchService extracts capability names,
descriptions, input schemas, and domains from the top-K results. These become the
"available tools menu" in the LLM prompt, enabling the LLM to reference real capabilities.

#### 6.2.2 Tool 2: `query_planning_context(sections?)`

**Route**: ToolCallRouter -> `IStateReadPort` -> `SessionStateReadAdapter`
         -> SessionState (multi-reader, lock-free, PLAN-01)

**Backend signature** (from `k1/fabric/ports/state_reader.py`):

```python
# ISessionStateReader protocol -- two options:

def read_sections(
    self,
    session_id: str,          # From PlanRequest.context.session_id
    names: List[str],         # e.g. ["beliefs_active", "persona", "temporal"]
) -> Dict[str, Any]           # Section name -> section data (missing sections omitted)

def get_snapshot(
    self,
    session_id: str,
) -> SessionSnapshot            # All available sections at capture time
```

**SKETCH typically requests**: `["beliefs_active", "persona", "temporal", "control"]`

This supplements the `PlanRequest.context` snapshot (which was captured at dispatch time)
with a FRESH read. If the Orchestrator snapshot is recent enough (<5s), SketchService
MAY skip this call and use `PlanRequest.context` directly -- but the canonical path
always makes the call for consistency.

**Latency target**: <10ms (in-process, lock-free read).

**What SKETCH uses from the result**: Beliefs ground the plan in known entities and
relationships (e.g., "8 family members", "Mom's birthday is Feb 21"). Persona shapes
LLM prompt tone. Temporal context provides clock awareness. Control provides the
effective safety band.

#### 6.2.3 Tool 3: `recall_for_planning(query)`

**Route**: ToolCallRouter -> `IBridgePort` -> `BridgeAdapter` -> K0 Bridge -> K0 Memory

**Backend signature** (from `k1/fabric/ports/bridge_port.py`):

```python
# IBridgePort protocol -- recall uses the query method:

async def query(
    self,
    operation: str,               # "memory.recall"
    selectors: Dict[str, Any],    # {query: "...", ...} -- recall selectors
    *,
    trace_id: str = "",           # Cognitive trace ID (FAB-09)
    timeout_ms: int = 0,          # Per-query timeout (0 = adapter default)
) -> BridgeCommandResult
```

ToolCallRouter invokes:

```python
bridge_port.query(
    operation="memory.recall",
    selectors={"query": "<planning_recall_query>"},
    trace_id=plan_request.trace_id,
    timeout_ms=100,  # 100ms budget for K0 recall
)
```

**Return type**:

```
BridgeCommandResult (frozen dataclass):
  success: bool             -- True if K0 responded
  data: Dict[str, Any]      -- {facts: [...], prior_outcomes: [...], preferences: [...]}
  error_code: str           -- Machine-readable error (empty on success)
  error_message: str        -- Human-readable error (empty on success)
  k0_mode: str              -- "K0_FULL" | "K0_DEGRADED" | "K0_OFFLINE"
  latency_ms: int           -- Round-trip to K0
  trace_id: str             -- Echoed back
```

**Offline handling**: If K0 is offline (`BridgeCommandResult.success == false`,
`k0_mode == "K0_OFFLINE"`), SKETCH proceeds without long-term memory. The LLM generates
a plan based only on session context and discovered capabilities. This is a graceful
degradation -- the plan may be less personalized but remains functionally valid.

**Latency target**: <100ms.

**What SKETCH uses from the result**: Historical preferences (e.g., "Mom prefers Italian
food"), prior outcomes (e.g., "Last party was at Olive Garden -- 4 stars"), and user
preference patterns. These inform the LLM to make contextually better choices.

#### 6.2.4 Concurrency and Tool Call Accounting

```
 ToolCallRouter state before SKETCH:
   tool_call_count = 0  (reset at LC_PLAN_START)

 SKETCH issues 3 calls concurrently:
   [discover_capabilities, query_planning_context, recall_for_planning]
   -> asyncio.gather(*calls)
   -> tool_call_count += 3

 ToolCallRouter state after SKETCH:
   tool_call_count = 3  (of 6 max, PLAN-05)
   Remaining budget: 3 calls for EXPAND

 If any tool call fails:
   - ToolCallRouter retries once (within 50ms/10ms/100ms budget per tool)
   - On second failure: return empty result for that tool
   - SKETCH proceeds with whatever context succeeded
   - Degraded but functional: LLM has fewer inputs
```

### 6.3 LLM Call: Rough Plan Generation

After the 3 tool calls resolve, SketchService assembles a prompt and makes exactly
one LLM call through ILLMPort.

#### 6.3.1 Prompt Assembly Architecture

SketchService uses a **slot-based prompt composition** pattern. The prompt is NOT a
hardcoded string -- it is assembled at runtime from structured slots, each backed by
a concrete data source. The actual natural-language framing of each slot is an
implementation detail owned by SketchService and testable in isolation.

**Prompt structure** (2 segments: system + user):

```
 SYSTEM SEGMENT
   Slot: ROLE_DEFINITION      -- Declares planning task, output schema contract
   Slot: OUTPUT_SCHEMA         -- JSON Schema for expected response structure

 USER SEGMENT  (assembled from tool call results + PlanRequest)
   Slot: INTENT                -- Source: PlanRequest.intent
   Slot: CAPABILITY_CATALOG    -- Source: discover_capabilities() result
   Slot: SESSION_CONTEXT       -- Source: query_planning_context() result
   Slot: LONG_TERM_MEMORY      -- Source: recall_for_planning() result (nullable)
   Slot: CONSTRAINTS           -- Source: PlanRequest.constraints + control section
   Slot: HIL_ADDENDUM          -- Source: HILCoordinator (conditional, post-clarification)
```

**Slot input contracts** (what exact data feeds each slot):

| Slot | Source Type | Required | Content |
| ---- | ----------- | -------- | ------- |
| INTENT | `PlanRequest.intent: str` | Yes | Raw user intent string, unmodified |
| CAPABILITY_CATALOG | `RetrievalResult.capabilities: List[ScoredCapability]` | Yes (may be empty) | Per capability: `contract.name`, `contract.description`, `contract.required_inputs[].name`, `contract.required_inputs[].type`, `contract.domain[]` |
| SESSION_CONTEXT | `Dict[str, Dict[str, Any]]` from `IStateReadPort.read_sections()` | Yes (may be partial) | Per section requested: section name as key, section data dict as value. Sections: `beliefs_active`, `persona`, `temporal`, `control` |
| LONG_TERM_MEMORY | `BridgeCommandResult.data: Dict[str, Any]` | No (K0 offline = omitted) | If present: `data.facts: List[str]`, `data.preferences: List[str]`, `data.prior_outcomes: List[str]`. If absent: slot omitted entirely (not rendered as empty) |
| CONSTRAINTS | `PlanRequest.constraints: Dict` + `control` section | Yes | `safety_band: str`, `temporal.now: str` (ISO 8601), `temporal.device_tz: str` |
| HIL_ADDENDUM | `str` from HILCoordinator clarification response | No (only if clarification occurred) | Raw user clarification text appended as additional context |
| OUTPUT_SCHEMA | Static JSON Schema | Yes | Declares expected response shape (see Output Contract below) |

**Output contract** (what the LLM MUST return):

The SYSTEM segment declares a JSON Schema that constrains the LLM response. SketchService
validates the parsed response against this schema before constructing SketchResult.

```json
{
  "type": "object",
  "required": ["rough_steps", "rationale"],
  "properties": {
    "rough_steps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["intent"],
        "properties": {
          "intent": {
            "type": "string",
            "minLength": 1,
            "description": "Natural-language description of what this step achieves"
          },
          "suggested_capability": {
            "type": "string",
            "description": "Capability name from CAPABILITY_CATALOG (if matched)"
          },
          "depends_on": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Zero-indexed references to prior steps this depends on"
          }
        }
      }
    },
    "rationale": {
      "type": "string",
      "minLength": 1,
      "description": "Reasoning for plan structure, ordering, and capability choices"
    },
    "needs_clarification": {
      "type": "boolean",
      "description": "True if intent is ambiguous and HIL clarification is recommended"
    },
    "clarification_question": {
      "type": "string",
      "description": "Question to ask user if needs_clarification is true"
    }
  }
}
```

**Token budget allocation**:

| Component | Budget | Notes |
| --------- | ------ | ----- |
| System segment (ROLE + OUTPUT_SCHEMA) | ~200 tokens | Fixed overhead, independent of request |
| INTENT slot | Variable | Mirrors user input length |
| CAPABILITY_CATALOG slot | ~50 tokens per capability x top-K | Top-10 default = ~500 tokens |
| SESSION_CONTEXT slot | ~100-300 tokens | Depends on section count and density |
| LONG_TERM_MEMORY slot | ~50-150 tokens | Depends on K0 recall depth (0 if offline) |
| CONSTRAINTS + HIL_ADDENDUM | ~50-100 tokens | Small fixed + optional clarification |
| **Total input estimate** | **800-1200 tokens** | Leaves 800-1200 for LLM response |
| **LLM response budget** | **max_tokens: 2048** | PLAN-11 enforced ceiling |

SketchService MUST ensure total input does not exceed the budget. If input exceeds
~1200 tokens, SketchService applies truncation in priority order (lowest priority
truncated first):

1. LONG_TERM_MEMORY -- truncate to most recent 3 facts/preferences
2. CAPABILITY_CATALOG -- reduce top-K from 10 to 5
3. SESSION_CONTEXT -- omit `history_recent` section
4. INTENT -- never truncated (source of truth for planning)

#### 6.3.2 HubRequest Construction

The assembled prompt is wrapped in a `HubRequest` for Model Hub routing.
Schema (from `planner.mmd` ILLMPort specification):

```yaml
HubRequest:
  capability: CapabilityType.CHAT           # Single-shot generation (no tool_call, no structured)
  payload:
    type: ChatPayload
    fields:
      system_prompt: str                    # SYSTEM SEGMENT (ROLE_DEFINITION + OUTPUT_SCHEMA)
      user_prompt: str                      # USER SEGMENT (all slots rendered)
      messages: []                          # Empty -- single-shot, no conversation history
  constraints:
    type: RequestConstraints
    fields:
      max_tokens: 2048                      # PLAN-11: every LLM call carries budget
      timeout_ms: 8000                      # SKETCH LLM timeout
      priority: "INTERACTIVE"               # Matches mailbox WFQ priority
      temperature: 0.7                      # Creative stage -- moderate temperature
      consumer_id: "planner"                # Cost tracking + audit (MH-11)
  trace_id: PlanRequest.trace_id            # Cognitive trace propagation (FAB-09)
```

**Routing path**:

```
 SketchService.execute()
   |
   |-- assemble_prompt(intent, discovery, context, memory, constraints, hil)
   |     -> system_prompt: str, user_prompt: str
   |
   |-- build_hub_request(system_prompt, user_prompt, sketch_constraints)
   |     -> HubRequest
   |
   |-- ILLMPort.execute(hub_request)
   |     |
   |     |-- LLMGatewayAdapter (V2) / TestLLMAdapter (V1)
   |     |     |
   |     |     |-- LLM_REQUEST_BUS (async request-reply)
   |     |     |     |
   |     |     |     |-- Model Hub RequestRouter
   |     |     |     |     |-- Provider selection (capability type + constraints)
   |     |     |     |     |-- LLM inference
   |     |     |     |     <- CapabilityResult
   |     |     |     <- HubResponse
   |     |     <- HubResponse
   |     <- HubResponse
   |
   |-- parse_sketch_response(hub_response.result.content)
   |     -> validates against OUTPUT_SCHEMA (Section 6.3.1)
   |     -> SketchResult
   |
   |-- record_token_usage(hub_response.metadata.usage)
         -> stage_token_usage[SKETCH] += total_tokens
```

**HubResponse schema** (from `planner.mmd`):

```yaml
HubResponse:
  result:
    type: CapabilityResult
    fields:
      content: str                          # Raw LLM output (JSON string matching OUTPUT_SCHEMA)
  metadata:
    type: ResponseMetadata
    fields:
      request_id: str                       # Model Hub internal correlation ID
      model_id: str                         # Which model was used (e.g. "gpt-4o")
      provider_id: str                      # Which provider (e.g. "azure-openai-eastus")
      usage:                                # Token consumption
        prompt_tokens: int
        completion_tokens: int
        total_tokens: int
      cost_usd: float                       # Estimated cost for this call
      latency_ms: int                       # Model Hub observed latency (end-to-end)
```

SketchService extracts `result.content`, parses it as JSON, validates against the
OUTPUT_SCHEMA declared in Section 6.3.1, and constructs the `SketchResult` (Section 6.5).
Token usage from `metadata.usage` is recorded in `stage_token_usage[SKETCH]`.

#### 6.3.3 Budget Enforcement (PLAN-11)

Every LLM call carries explicit `{max_tokens, timeout_ms}` -- no unbounded calls.
PipelineController injects SKETCH budgets before the call:

| Parameter | SKETCH Value | Enforced By |
|-----------|-------------|-------------|
| `max_tokens` | 2048 | Model Hub (MH-04) truncates at limit |
| `timeout_ms` | 8000 | LLMGatewayAdapter cancels on timeout |
| `temperature` | 0.7 | Model Hub passes to provider |
| Circuit breaker | CB_LLM (inherited per provider, MH-05) | Model Hub provider manifest |

If the LLM call exceeds 8000ms, LLMGatewayAdapter raises a timeout error. SketchService
catches this and enters the ERR_SKETCH_FAIL recovery path (Section 6.6).

### 6.4 HIL Clarification (Conditional)

Between tool call resolution and the LLM call, SketchService evaluates whether HIL
(Human-in-the-Loop) clarification is needed. This is the first of two HIL interaction
points (the second is HIL Approval in Stage 3 VALIDATE).

#### 6.4.1 Trigger Conditions

SketchService triggers HIL clarification when:

1. **Ambiguous intent**: The intent string is too vague to produce a meaningful plan
   (e.g., "help me with something" vs. "book a restaurant for 8 on Saturday").
2. **Missing constraints**: Required information is absent from both session context
   and K0 memory (e.g., no date specified for a time-sensitive task).
3. **Conflicting signals**: Context and memory disagree (e.g., beliefs say mom prefers
   sushi but last party was Italian -- which takes precedence?).

The decision to trigger is made by a lightweight LLM check embedded in the main SKETCH
prompt, OR as a pre-check LLM call (~300 tokens, counted within the 2048 SKETCH budget).

#### 6.4.2 Clarification Flow

```
 SketchService -> HILCoordinator.request_clarification(
     request_id=plan_request.request_id,
     question=<LLM-generated natural language question>   (~300 tokens)
   )

 HILCoordinator:
   1. Generate question via ILLMPort:
      HubRequest{capability: CHAT, constraints: {max_tokens: 300, timeout_ms: 3000}}
      Prompt: "Given intent '<intent>' and context, what specific question
               would resolve the ambiguity? Keep it natural for a family context."
      (Note: this 300-token LLM call is WITHIN the SKETCH stage budget)

   2. Emit event via IEventPort:
      topic: "k1.hil.clarification.v1"
      payload: {
        request_id: plan_request.request_id,
        question: "<generated question text>",
        context_hint: "<what the Planner already knows>",
        round: 1,
        max_rounds: 2
      }

   3. Route: IEventPort -> Event Bus -> Concierge -> User
      Concierge stores request_id in PENDING_CLARIFICATIONS map.
      Concierge presents question to user via active channel.

   4. WAIT for response event:
      topic: "k1.hil.clarification_response.v1"
      HILCoordinator subscribes, correlates by request_id
      Timeout: 60s per round

   5. On response:
      payload: {
        request_id: plan_request.request_id,
        response: "<user's answer>",
        round: 1
      }
      HILCoordinator returns response to SketchService.
      SketchService incorporates response into LLM prompt context.

   6. IF answer still insufficient AND round < 2 (PLAN-10):
      Repeat steps 1-5 with round=2 and refined question.

   7. IF timeout OR round == 2 reached:
      Proceed with best-effort interpretation.
      SketchService LLM call includes note: "(User clarification unavailable,
      proceeding with best-effort interpretation)"
```

#### 6.4.3 Invariant: PLAN-10 (Max 2 Rounds)

HILCoordinator enforces a hard cap of 2 clarification rounds. After 2 rounds (or
60s timeout on either round), the Planner MUST proceed. This prevents indefinite
blocking on user input and keeps the total planning time within the 45s budget (PLAN-04).

The round counter is reset at `LC_PLAN_START` alongside `tool_call_count`.

#### 6.4.4 Event Namespace

The HIL clarification events belong to the PLANNING-TIME namespace:

```
 PLANNING-TIME (Planner owns):
   k1.hil.clarification.v1              -- Planner -> Concierge -> User
   k1.hil.clarification_response.v1     -- User -> Concierge -> Planner

 EXECUTION-TIME (Orchestrator owns, distinct family):
   k1.hil.override*.v1                  -- Orchestrator -> Concierge -> User
   k1.hil.fallback*.v1                  -- Orchestrator -> Concierge -> User
```

Concierge routes both families to the user but correlates them independently.

### 6.5 Output: SketchResult

The LLM response is parsed into a `SketchResult` structure:

```
SketchResult {
  rough_steps: List[RoughStep]
    Each RoughStep: {
      intent: str                        -- Natural-language step description
      suggested_capability: Optional[str] -- Capability name from discovery (if matched)
    }
  capability_candidates: List[ScoredCapability]
                                          -- Full discovery results carried forward for EXPAND
  rationale: str                         -- LLM's reasoning for the plan structure
                                          -- (e.g., "Parallel independent tasks then sequential")
}
```

SketchResult is an internal type (not in `k1.orchestrator.types` -- it does not cross
the Planner boundary). It flows from SketchService -> PipelineController -> ExpandService.

**Schema validation**: SketchService validates the parsed JSON before constructing
SketchResult:

1. `rough_steps` must be a non-empty list
2. Each step must have a non-empty `intent` string
3. `rationale` must be a non-empty string
4. If `suggested_capability` is present, it must match a name from the discovery results

If validation fails, SketchService attempts one re-parse (LLM output may have minor
JSON formatting issues). If re-parse also fails, enter ERR_SKETCH_FAIL.

**Token accounting**: After the LLM call, SketchService records:

```
stage_token_usage[SKETCH] = hub_response.metadata.usage.total_tokens
```

PipelineController accumulates this for the total plan token count reported in
the PLAN_END delta.

**Stage completion delta**: On success, PipelineController emits:

```
k1.planner.delta.v1 {
  type: "stage_complete",
  stage: "SKETCH",
  status: "completed",
  tokens_used: stage_token_usage[SKETCH],
  tool_calls_used: 3,
  hil_rounds: 0 | 1 | 2,
  duration_ms: <stage wall time>
}
```

### 6.6 Error Recovery: ERR_SKETCH_FAIL

SKETCH errors are handled by the ERR_SKETCH_FAIL recovery path defined in `planner.mmd`.
The error wiring: `SVC_SKETCH -> ERR_SKETCH_FAIL -> retry / plan.failed`.

#### 6.6.1 Failure Scenarios in SKETCH

| Failure | Cause | Detection |
|---------|-------|-----------|
| Discovery timeout | Fabric Retrieval slow or unavailable | ToolCallRouter 50ms timeout |
| Context read failure | SessionState unavailable | ToolCallRouter 10ms timeout |
| K0 recall failure | Bridge offline | BridgeCommandResult.success == false |
| LLM timeout | Model Hub / provider slow | LLMGatewayAdapter 8000ms timeout |
| LLM error | Provider error, rate limit | HubResponse error or exception |
| JSON parse failure | LLM output malformed | SketchService JSON validation |
| HIL timeout | User unresponsive | HILCoordinator 60s timeout |

#### 6.6.2 Recovery Strategy

```
 ERR_SKETCH_FAIL decision tree:

 1. Tool call failure (any of the 3):
    -> Retry once within tool's latency budget
    -> On second failure: proceed without that tool's data
    -> NOT a stage failure (degraded input, but SKETCH continues)

 2. LLM timeout or error (first attempt):
    -> RETRY ONCE with SIMPLIFIED PROMPT:
       - Remove K0 memory context (recall results)
       - Reduce capability list to top-3 only
       - Add instruction: "Generate a minimal plan with available information"
       - Keep same budget: {max_tokens: 2048, timeout_ms: 8000}
    -> If simplified attempt succeeds: continue to EXPAND (degraded quality)

 3. LLM timeout or error (second attempt):
    -> PLAN FAILED
    -> Plan FSM transitions: SKETCHING -> FAILED
    -> Emit: k1.planner.plan.failed.v1 {
         request_id: plan_request.request_id,
         stage: "SKETCH",
         error: "ERR_SKETCH_FAIL",
         message: "LLM failed after retry with simplified prompt",
         trace_id: plan_request.trace_id
       }
    -> Orchestrator receives via Event Bus subscription, cleans up PendingPlanContext

 4. JSON parse failure (LLM output malformed):
    -> Re-parse once (strip markdown fences, attempt recovery)
    -> If still malformed: treat as LLM error, follow path (2) above

 5. HIL timeout:
    -> NOT a stage failure
    -> Proceed with best-effort interpretation (Section 6.4.2 step 7)
    -> Plan quality may be reduced but pipeline continues
```

#### 6.6.3 Cascading Impact

If SKETCH fails (plan FSM -> FAILED), no downstream stages execute. The entire plan
request terminates. The Orchestrator's PendingPlanContext (stored in `pending_plans`
dict keyed by `request_id`) will be cleaned up either by:

1. The `k1.planner.plan.failed.v1` event handler in Orchestrator, OR
2. The Orchestrator timeout reaper (if the failure event itself fails to deliver)

The Orchestrator may then degrade future HIGH-tier requests to MEDIUM-tier processing
if CB_PLANNER trips (3 consecutive failures -> circuit open, 60s reset, 1 probe call).

---

## 7. Stage 2: EXPAND -- Deep Dive

LLM-powered tool mapping and parameterization. Performance envelope: ~1K tokens,
p50 3s / p99 5s. This is where rough intent becomes concrete executable structure.

Plan FSM transition on entry: `SKETCHING -> EXPANDING`. On exit: `EXPANDING -> VALIDATING`.

ExpandService is the owning internal service (~50 tests). It takes the rough plan from
SKETCH, issues refined discovery calls to map each step to a concrete capability, and
makes one LLM call to produce fully parameterized `PlanStep` objects. ExpandService has
dependencies on:

- `ILLMPort` (LLM call)
- `ToolCallRouter` (routes 2-3 remaining discovery tools to backends)
- `PipelineController` (receives stage result, tracks token usage)

ExpandService does NOT interact with HILCoordinator. EXPAND has no HIL interaction point
-- clarification happens in SKETCH, approval happens in VALIDATE.

### 7.1 Inputs

ExpandService receives the `SketchResult` from PipelineController, plus the original
`PlanRequest` carried through the pipeline context.

**From SketchResult** (internal type, Section 6.5):

```yaml
SketchResult:
  rough_steps: List[RoughStep]
    - intent: str                         # Natural-language step description
    - suggested_capability: str | null    # Capability name hint from SKETCH
    - depends_on: List[int] | null        # Zero-indexed step dependency references
  capability_candidates: List[ScoredCapability]
                                          # Full discovery results from SKETCH, carried forward
  rationale: str                          # SKETCH's structural reasoning
```

**From PlanRequest** (carried through pipeline context):

| Field | Type | EXPAND Usage |
| ----- | ---- | ------------ |
| `intent` | `str` | Injected into EXPAND prompt for alignment check |
| `trace_id` | `str` | Propagated to all port calls (FAB-09) |
| `context` | `SessionSnapshot` | Section data available for prompt parameterization |
| `constraints` | `Dict` | `safety_band` constrains capability filtering |

**Key transformation**: EXPAND's job is to convert `RoughStep.intent` (natural language)
into `PlanStep.capability` + `PlanStep.params` (structured, executable). The SKETCH
output tells the LLM WHAT to do; the EXPAND output tells the Orchestrator HOW to do it
with exact parameters.

### 7.2 Discovery Tool Calls (up to 3, from remaining budget)

EXPAND uses the remaining tool call budget from PLAN-05 (max 6 per plan, SKETCH used 3).
ExpandService issues 2-3 calls through ToolCallRouter. These calls are more targeted than
SKETCH -- they refine discovery per-step rather than doing broad intent matching.

#### 7.2.1 Tool 1: `discover_capabilities(specific_tools)` -- Refined Per-Step

**Route**: ToolCallRouter -> `IFabricRetrievalPort` -> `FabricRetrievalAdapter`
         -> `RetrievalEngine.discover_capabilities()` (in-process)

**Purpose**: For each `RoughStep` that has a `suggested_capability` hint, EXPAND
issues a refined discovery call to confirm the capability exists, retrieve its full
input/output schema, and find the best match if the hint was approximate.

**Backend signature** (same as Section 6.2.1):

```python
def discover_capabilities(
    self,
    domain: Optional[List[str]] = None,
    intent: str = "",                      # More specific than SKETCH: per-step intent
    safety_band: str = "GREEN",
    session_context: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,           # Typically 3-5 (narrower than SKETCH's 10)
) -> RetrievalResult
```

**EXPAND vs SKETCH discovery**:

| Aspect | SKETCH (Section 6.2.1) | EXPAND |
| ------ | ---------------------- | ------ |
| Query granularity | Broad intent (entire plan) | Per-step intent (one capability) |
| top_k | 10 (default, wide net) | 3-5 (narrow, targeted) |
| Purpose | Build capability menu for LLM | Confirm + schema-resolve per step |
| Call count | 1 | 1-2 (may batch multiple steps) |

**What EXPAND uses from the result**: Full `CapabilityContract` details -- specifically
`required_inputs[]` (parameter names and types for `PlanStep.params`),
`output` (JSON schema for `PlanStep.output_schema`), `required_context[]` (for
`PlanStep.required_context`), `safety_band_min`, `avg_latency_ms` (seeds
`PlanStep.timeout_ms`), and capability metadata that determines `has_side_effects`
and `compensation`.

**Latency target**: <50ms (same as SKETCH).
**ToolCallRouter accounting**: `tool_call_count += 1` (now 4 of 6).

#### 7.2.2 Tool 2: `find_relevant_prompts(intent, domain)`

**Route**: ToolCallRouter -> `IFabricRetrievalPort` -> `FabricRetrievalAdapter`
         -> `RetrievalEngine.find_relevant_prompts()` (in-process)

**Backend signature** (from `k1/fabric/retrieval/retrieval_engine.py`):

```python
def find_relevant_prompts(
    self,
    intent: str = "",                      # Plan-level or step-level intent
    domain: Optional[List[str]] = None,    # Inferred from SKETCH step domains
    safety_band: str = "GREEN",
    top_k: Optional[int] = None,
) -> RetrievalResult
```

This is the same 4-step retrieval pipeline as `discover_capabilities` but pre-filters
to prompt-type contracts only (`provider_type` starts with `"prompt"` or `name` starts
with `"prompt."`).

**Purpose**: Find prompt templates that should be attached to agent-type steps.
Agent steps (`capability: "agent.execute.*"`) often need a `prompt_template` reference
to shape the agent's behavior. EXPAND discovers available prompt templates so the LLM
can assign the best match to each agent step.

**Return type**: `RetrievalResult` (same as Section 6.2.1). Each `ScoredCapability`
wraps a `CapabilityContract` where `provider_type` is prompt-related. Relevant fields:

- `contract.name` -- Prompt template identifier (e.g., `"prompt.invitation_drafter_v1"`)
- `contract.description` -- What the prompt does
- `contract.required_inputs[]` -- Variable slots in the template
- `contract.domain[]` -- Domain tag alignment

**Latency target**: <50ms.
**ToolCallRouter accounting**: `tool_call_count += 1` (now 5 of 6).

#### 7.2.3 Optional Tool 3: Additional Capability Resolution

If a `RoughStep.suggested_capability` from SKETCH did not match any known capability
in the EXPAND refined discovery (Tool 1), ExpandService MAY issue a third discovery
call with a broader query to find alternatives.

**ToolCallRouter accounting**: `tool_call_count += 1` (now 6 of 6, MAX reached).
After this, PLAN-05 prevents any further tool calls in this plan.

#### 7.2.4 Tool Call Budget After EXPAND

```
 ToolCallRouter state entering EXPAND:
   tool_call_count = 3  (from SKETCH)

 EXPAND issues 2-3 calls:
   [discover_capabilities (refined), find_relevant_prompts, (optional) additional]
   -> tool_call_count = 5 or 6

 ToolCallRouter state after EXPAND:
   tool_call_count = 5 or 6  (of 6 max, PLAN-05)
   Remaining budget: 0-1 calls (no further stages use tools)
   VALIDATE and COMMIT stages do NOT make tool calls.

 If any tool call fails:
   - ToolCallRouter retries once (within 50ms budget)
   - On second failure: return empty result for that tool
   - EXPAND proceeds -- LLM maps steps using SKETCH capability_candidates as fallback
   - Degraded: less precise param mapping, but structurally valid
```

### 7.3 LLM Call: Tool Mapping and Parameterization

After tool calls resolve, ExpandService assembles a prompt and makes exactly one LLM
call through ILLMPort.

#### 7.3.1 Prompt Assembly Architecture

ExpandService uses the same slot-based composition pattern as SKETCH (Section 6.3.1),
with EXPAND-specific slots.

**Prompt structure** (2 segments: system + user):

```
 SYSTEM SEGMENT
   Slot: ROLE_DEFINITION      -- Declares expansion task, precision requirements
   Slot: OUTPUT_SCHEMA         -- JSON Schema for expected response structure

 USER SEGMENT (assembled from SKETCH output + EXPAND tool results)
   Slot: ORIGINAL_INTENT       -- Source: PlanRequest.intent (alignment anchor)
   Slot: SKETCH_PLAN           -- Source: SketchResult.rough_steps[] + rationale
   Slot: REFINED_CAPABILITIES  -- Source: EXPAND discover_capabilities() result
   Slot: PROMPT_TEMPLATES      -- Source: find_relevant_prompts() result
   Slot: SKETCH_CAPABILITIES   -- Source: SketchResult.capability_candidates (fallback)
   Slot: CONSTRAINTS           -- Source: PlanRequest.constraints + safety_band
```

**Slot input contracts**:

| Slot | Source Type | Required | Content |
| ---- | ----------- | -------- | ------- |
| ORIGINAL_INTENT | `PlanRequest.intent: str` | Yes | Raw user intent (ensures EXPAND stays aligned with user's actual request, not just SKETCH's interpretation) |
| SKETCH_PLAN | `SketchResult.rough_steps: List[RoughStep]` | Yes | Per step: `intent`, `suggested_capability`, `depends_on`. Plus `SketchResult.rationale` |
| REFINED_CAPABILITIES | `RetrievalResult.capabilities: List[ScoredCapability]` | Yes (may be empty) | Per capability: `contract.name`, `contract.required_inputs[]` (name, type, required), `contract.optional_inputs[]`, `contract.output` (JSON schema), `contract.required_context[]`, `contract.avg_latency_ms`, `contract.safety_band_min`, `contract.domain[]` |
| PROMPT_TEMPLATES | `RetrievalResult.capabilities: List[ScoredCapability]` | No (empty if no prompts found) | Per prompt: `contract.name`, `contract.description`, `contract.required_inputs[]` (variable slots), `contract.domain[]` |
| SKETCH_CAPABILITIES | `SketchResult.capability_candidates: List[ScoredCapability]` | Fallback | Used when EXPAND refined discovery returns empty -- LLM falls back to SKETCH's broader results |
| CONSTRAINTS | `PlanRequest.constraints: Dict` | Yes | `safety_band`, effective temporal context |

**Output contract** (what the LLM MUST return):

```json
{
  "type": "object",
  "required": ["steps", "dependencies"],
  "properties": {
    "steps": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "capability", "params"],
        "properties": {
          "id": {
            "type": "string",
            "pattern": "^s[0-9]+$",
            "description": "Step identifier (s1, s2, ...)"
          },
          "capability": {
            "type": "string",
            "minLength": 1,
            "description": "Fully qualified capability name from discovery results"
          },
          "params": {
            "type": "object",
            "description": "Key-value parameters matching capability.required_inputs schema. Values may reference prior step outputs via $<step_id>.result.<field> syntax"
          },
          "deps": {
            "type": "array",
            "items": {"type": "string", "pattern": "^s[0-9]+$"},
            "description": "Step IDs this depends on (must reference earlier steps)"
          },
          "prompt_template": {
            "type": ["string", "null"],
            "description": "Prompt template name from PROMPT_TEMPLATES slot (agent steps)"
          },
          "tools_granted": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "Scoped tool list for agent steps (FAB-07)"
          },
          "output_schema": {
            "type": ["object", "null"],
            "description": "JSON Schema fragment declaring expected output fields"
          },
          "is_optional": {
            "type": "boolean",
            "default": false,
            "description": "True = step failure does not fail the plan"
          },
          "has_side_effects": {
            "type": "boolean",
            "default": false,
            "description": "True = step modifies external state (drives rollback)"
          },
          "compensation": {
            "type": ["string", "null"],
            "description": "Capability to call for rollback if has_side_effects=true"
          },
          "timeout_ms": {
            "type": ["integer", "null"],
            "minimum": 1,
            "description": "Per-step timeout, seeded from capability.avg_latency_ms"
          },
          "required_context": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "SessionState sections needed before execution"
          },
          "safety_band_min": {
            "type": ["string", "null"],
            "enum": ["GREEN", "AMBER", "RED", null],
            "description": "Minimum safety band for this step"
          }
        }
      }
    },
    "dependencies": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": {"type": "string"}
      },
      "description": "step_id -> [predecessor_step_ids] dependency map"
    }
  }
}
```

This output schema maps directly to the `PlanStep` dataclass (14 fields) defined in
`k1/orchestrator/types.py`. Every field in the schema corresponds to a `PlanStep` field.

**Token budget allocation**:

| Component | Budget | Notes |
| --------- | ------ | ----- |
| System segment (ROLE + OUTPUT_SCHEMA) | ~250 tokens | Larger schema than SKETCH |
| ORIGINAL_INTENT | Variable | Same as SKETCH INTENT slot |
| SKETCH_PLAN | ~100-200 tokens | Proportional to rough_steps count |
| REFINED_CAPABILITIES | ~80 tokens per capability x 3-5 | ~300 tokens |
| PROMPT_TEMPLATES | ~50 tokens per template x 2-3 | ~120 tokens |
| CONSTRAINTS | ~30 tokens | Minimal |
| **Total input estimate** | **700-1000 tokens** | Leaves ~200-500 for LLM response |
| **LLM response budget** | **max_tokens: 1024** | PLAN-11 enforced ceiling |

The response is typically compact because it is structured JSON with well-defined fields.
Most token consumption is in the `params` values and `output_schema` fragments.

**Truncation priority** (if input exceeds budget):

1. SKETCH_CAPABILITIES -- omit fallback slot entirely (REFINED_CAPABILITIES suffices)
2. PROMPT_TEMPLATES -- reduce to top-2
3. REFINED_CAPABILITIES -- reduce capability detail (omit optional_inputs)
4. SKETCH_PLAN -- never truncated (structural source of truth for expansion)

#### 7.3.2 HubRequest Construction

```yaml
HubRequest:
  capability: CapabilityType.CHAT           # Single-shot generation
  payload:
    type: ChatPayload
    fields:
      system_prompt: str                    # SYSTEM SEGMENT (ROLE_DEFINITION + OUTPUT_SCHEMA)
      user_prompt: str                      # USER SEGMENT (all slots rendered)
      messages: []                          # Empty -- single-shot
  constraints:
    type: RequestConstraints
    fields:
      max_tokens: 1024                      # PLAN-11: half of SKETCH budget (less creative work)
      timeout_ms: 5000                      # EXPAND LLM timeout (tighter than SKETCH)
      priority: "INTERACTIVE"
      temperature: 0.3                      # Low temperature -- precision mapping, not creativity
      consumer_id: "planner"                # Cost tracking (MH-11)
  trace_id: PlanRequest.trace_id            # Cognitive trace propagation (FAB-09)
```

**Key difference from SKETCH**: `temperature: 0.3` (vs SKETCH's `0.7`). EXPAND is a
precision task -- mapping known capabilities to known parameters -- not a creative task.
Lower temperature produces more deterministic, schema-conformant output.

**Routing path**:

```
 ExpandService.execute()
   |
   |-- assemble_prompt(sketch_result, refined_caps, prompts, intent, constraints)
   |     -> system_prompt: str, user_prompt: str
   |
   |-- build_hub_request(system_prompt, user_prompt, expand_constraints)
   |     -> HubRequest
   |
   |-- ILLMPort.execute(hub_request)
   |     -> LLMGatewayAdapter -> LLM_REQUEST_BUS -> Model Hub -> Provider
   |     <- HubResponse
   |
   |-- parse_expand_response(hub_response.result.content)
   |     -> validates against OUTPUT_SCHEMA
   |     -> ExpandedPlan (internal) -> List[PlanStep] (typed)
   |
   |-- record_token_usage(hub_response.metadata.usage)
         -> stage_token_usage[EXPAND] += total_tokens
```

#### 7.3.3 Budget Enforcement (PLAN-11)

| Parameter | EXPAND Value | Enforced By |
| --------- | ------------ | ----------- |
| `max_tokens` | 1024 | Model Hub (MH-04) truncates at limit |
| `timeout_ms` | 5000 | LLMGatewayAdapter cancels on timeout |
| `temperature` | 0.3 | Model Hub passes to provider |
| Circuit breaker | CB_LLM (inherited per provider, MH-05) | Model Hub provider manifest |

### 7.4 Output: ExpandedPlan

The LLM response is parsed into an `ExpandedPlan` structure, which is then converted
into typed `PlanStep` objects.

#### 7.4.1 ExpandedPlan Structure

`ExpandedPlan` is an internal type (does not cross the Planner boundary). It flows
from ExpandService -> PipelineController -> ValidateService.

```yaml
ExpandedPlan:
  steps: List[PlanStep]                    # Fully parameterized steps (14 fields each)
  dependencies: Dict[str, List[str]]       # step_id -> [predecessor_step_ids]
```

Each `PlanStep` in the output carries all 14 fields from `k1/orchestrator/types.py`:

```yaml
PlanStep (frozen dataclass, 14 fields):
  # Fabric-aligned fields (1-6)
  id: str                                  # Required. "s1", "s2", etc.
  capability: str                          # Required. Fully qualified name from Fabric registry
  params: Dict[str, Any]                   # Forwarded as CapabilityRequest.parameters
  deps: List[str]                          # Step IDs this depends on
  prompt_template: str | null              # Template name reference (agent steps)
  tools_granted: List[str] | null          # Scoped tool list for agent steps (FAB-07)

  # Orchestrator extension fields (7-14)
  output_schema: Dict | null               # JSON Schema for OutputSchemaGuard validation
  condition: ConditionExpr | null           # Structured conditional (EXPAND does not set -- V2)
  is_optional: bool                        # False = failure fails the plan
  has_side_effects: bool                   # True = drives rollback/compensation
  compensation: str | null                 # Capability to call for rollback
  timeout_ms: int | null                   # Seeded from capability.avg_latency_ms
  required_context: List[str] | null       # SessionState sections needed pre-execution
  safety_band_min: str | null              # Minimum safety band for step execution
```

**PlanStep field validation** (enforced at construction, `__post_init__`):

- `id` must be non-empty
- `capability` must be non-empty
- `timeout_ms` must be > 0 if set
- `deps` validated at CommittedPlan level (DAG cycle check in VALIDATE)

#### 7.4.2 Field Population Sources

Each PlanStep field is populated from a specific source. The LLM does not invent values
for infrastructure fields -- those are enriched deterministically by ExpandService after
parsing the LLM response.

| PlanStep Field | Population Source | LLM-Generated? |
| -------------- | ----------------- | --------------- |
| `id` | LLM output (`"s1"`, `"s2"`, ...) | Yes |
| `capability` | LLM output (from REFINED_CAPABILITIES names) | Yes |
| `params` | LLM output (keys from `contract.required_inputs`, values from context) | Yes |
| `deps` | LLM output (from SKETCH `depends_on` + LLM inference) | Yes |
| `prompt_template` | LLM output (from PROMPT_TEMPLATES names) | Yes |
| `tools_granted` | LLM output (for agent steps, from discovery) | Yes |
| `output_schema` | LLM output (from `contract.output` JSON Schema) or ExpandService enrichment | Partial |
| `condition` | Not set in V1 (always `null`) | No |
| `is_optional` | LLM output (boolean) | Yes |
| `has_side_effects` | ExpandService enrichment from `CapabilityContract` metadata | No |
| `compensation` | ExpandService enrichment from `CapabilityContract` metadata | No |
| `timeout_ms` | ExpandService enrichment: `contract.avg_latency_ms * 2` (safety margin) | No |
| `required_context` | ExpandService enrichment from `contract.required_context[]` | No |
| `safety_band_min` | ExpandService enrichment from `contract.safety_band_min` | No |

**Post-LLM enrichment**: After parsing the LLM response, ExpandService performs a
deterministic enrichment pass over each step:

```
 for step in llm_parsed_steps:
   contract = lookup_contract(step.capability, refined_capabilities)
   if contract:
     step.has_side_effects = infer_side_effects(contract)
     step.compensation = infer_compensation(contract)
     step.timeout_ms = contract.avg_latency_ms * 2  (or default 10000)
     step.required_context = contract.required_context
     step.safety_band_min = contract.safety_band_min
     if not step.output_schema and contract.output:
       step.output_schema = contract.output
```

This separation ensures infrastructure fields are deterministic and sourced from the
Fabric registry, not hallucinated by the LLM.

#### 7.4.3 Step Parameter Reference Syntax

PlanStep params MAY contain **inter-step references** using `$<step_id>.result.<field>`
syntax. These are NOT resolved at plan time -- they are symbolic references that the
Orchestrator's DAG executor resolves at execution time by substituting actual step outputs.

```yaml
# Example: step s4 references outputs from steps s1 and s3
PlanStep:
  id: "s4"
  capability: "agent.execute.invitation_sender"
  params:
    event: "birthday_party"
    recipients: "$s3.result.contacts"       # Resolved at execution time
    venue: "$s1.result.venue"               # Resolved at execution time
  deps: ["s1", "s3"]                        # Must depend on referenced steps
```

**Invariant**: If a param value uses `$<step_id>.result.*` syntax, that `step_id` MUST
appear in `deps`. VALIDATE (Stage 3) checks this constraint during DAG validation.

#### 7.4.4 Token Accounting and Stage Completion

After the LLM call, ExpandService records token usage:

```
stage_token_usage[EXPAND] = hub_response.metadata.usage.total_tokens
```

PipelineController emits the stage completion delta:

```yaml
k1.planner.delta.v1:
  type: "stage_complete"
  stage: "EXPAND"
  status: "completed"
  tokens_used: stage_token_usage[EXPAND]
  tool_calls_used: 2-3                     # Tools used in EXPAND specifically
  hil_rounds: 0                            # EXPAND has no HIL interaction
  duration_ms: <stage wall time>
  step_count: <number of PlanSteps produced>
```

### 7.5 Meta-Agent DAG Pattern (4.5.1-4.5.9)

EXPAND is where meta-agent composition happens. When the plan requires a dynamically
created agent (not a pre-registered one), EXPAND produces `build_agent` DAG steps
using the meta-agent pattern defined in planner.mmd sections 4.5.1-4.5.9.

#### 7.5.1 Pattern Overview

The meta-agent pattern allows the Planner to compose an `AgentSpec` from discovered
capabilities, prompts, and tools -- and emit it as a DAG step for the Orchestrator
to execute. The Planner NEVER executes agents (PLAN-06) -- it only describes them.

```
 PLANNER (EXPAND stage):                  ORCHESTRATOR (execution time):
   1. Discover tools for agent              4. Execute build_agent step
   2. Discover prompt template              5. Fabric creates agent from AgentSpec
   3. Compose build_agent PlanStep          6. Execute subsequent step using new agent
      with AgentSpec in params
```

#### 7.5.2 build_agent PlanStep Schema

When EXPAND determines a step requires a dynamically created agent, it produces a
PlanStep with `capability: "tool.meta.build_agent"`:

```yaml
PlanStep:
  id: "s1"
  capability: "tool.meta.build_agent"      # Reserved capability for agent creation
  params:
    name: str                              # Agent name (e.g., "health_advisor")
    role: str                              # Agent role description
    tools_granted: List[str]               # Tools the agent may use (FAB-07 scoped)
    prompt_template: str                   # Prompt template from find_relevant_prompts()
    seed_context: Dict[str, Any]           # Initial context for the agent
    ttl_turns: int                         # Max conversation turns before auto-teardown
  deps: []                                 # build_agent typically has no dependencies
  output_schema:
    agent_name: "string"                   # The created agent's registered name
  tools_granted: null                      # This is not an agent step itself
  has_side_effects: true                   # Creates a resource (the agent)
  compensation: null                       # Agent teardown handled by TTL, not rollback
```

#### 7.5.3 Referencing a Created Agent

Subsequent steps reference the agent created by `build_agent` using the inter-step
reference syntax `$<build_step_id>.result.agent_name`:

```yaml
PlanStep:
  id: "s2"
  capability: "$s1.result.agent_name"      # Resolved at execution time to actual agent name
  params:
    query: "What exercises are safe for pregnancy?"
  deps: ["s1"]                             # MUST depend on the build_agent step
  prompt_template: null                    # Agent already has its prompt from build_agent
  tools_granted: null                      # Agent already has tools from build_agent
```

The Orchestrator's DAG executor resolves `$s1.result.agent_name` to the actual
registered agent name returned by the `build_agent` execution.

#### 7.5.4 EXPAND's Role in Meta-Agent Composition

ExpandService populates `build_agent` params from EXPAND discovery results:

| AgentSpec Field | Source |
| --------------- | ------ |
| `name` | LLM generates from intent context |
| `role` | LLM generates from intent + capability descriptions |
| `tools_granted` | From `discover_capabilities()` result: matching capability names |
| `prompt_template` | From `find_relevant_prompts()` result: best-matching template name |
| `seed_context` | From `PlanRequest.context` sections relevant to the agent's domain |
| `ttl_turns` | LLM estimates based on task complexity (default: 3) |

**Invariant**: PLAN-06 -- the Planner outputs `build_agent` as a DAG step. The Planner
NEVER calls `tool.meta.build_agent` itself. The Orchestrator receives the CommittedPlan
and executes the DAG, including agent creation.

### 7.6 Error Recovery: ERR_EXPAND_FAIL

EXPAND errors are handled by the ERR_EXPAND_FAIL recovery path defined in `planner.mmd`.
The error wiring: `SVC_EXPAND -> ERR_EXPAND_FAIL -> retry / fallback / plan.failed`.

#### 7.6.1 Failure Scenarios in EXPAND

| Failure | Cause | Detection |
| ------- | ----- | --------- |
| Refined discovery timeout | Fabric Retrieval slow or unavailable | ToolCallRouter 50ms timeout |
| Prompt discovery failure | No matching prompts found | Empty RetrievalResult |
| LLM timeout | Model Hub / provider slow | LLMGatewayAdapter 5000ms timeout |
| LLM error | Provider error, rate limit | HubResponse error or exception |
| JSON parse failure | LLM output malformed or non-conformant | ExpandService schema validation |
| Invalid capability reference | LLM referenced a capability not in discovery results | ExpandService post-parse check |
| Invalid dependency graph | LLM produced circular or self-referencing deps | ExpandService pre-check (full DAG validation in VALIDATE) |

#### 7.6.2 Recovery Strategy

```
 ERR_EXPAND_FAIL decision tree:

 1. Tool call failure (discovery or prompts):
    -> Retry once within 50ms budget
    -> On second failure: proceed using SketchResult.capability_candidates as fallback
    -> NOT a stage failure (degraded input, EXPAND continues with SKETCH data)

 2. LLM timeout or error (first attempt):
    -> RETRY ONCE with same prompt
    -> Same budget: {max_tokens: 1024, timeout_ms: 5000}

 3. LLM timeout or error (second attempt):
    -> FALLBACK: Use SKETCH output as-is (degraded)
    -> Convert SketchResult.rough_steps to minimal PlanSteps:
         PlanStep{
           id: "s<n>",
           capability: rough_step.suggested_capability or "UNRESOLVED",
           params: {},                     -- No params (Orchestrator will attempt best-effort)
           deps: <from rough_step.depends_on>,
           output_schema: null,
           timeout_ms: 10000               -- Default fallback timeout
         }
    -> These degraded PlanSteps proceed to VALIDATE (Stage 3)
    -> VALIDATE will likely flag missing params but MAY approve if safe

 4. JSON parse failure:
    -> Re-parse once (strip markdown fences, attempt recovery)
    -> If still malformed: follow path (2) above for retry
    -> If retry also malformed: follow path (3) above for fallback

 5. Invalid capability reference:
    -> Replace invalid references with best match from SketchResult.capability_candidates
    -> If no match: mark step as is_optional=true (Orchestrator skips on execution failure)

 6. Invalid dependency graph:
    -> Remove circular edges, flatten to sequential ordering
    -> Log warning in stage delta
```

**Key difference from SKETCH error recovery**: EXPAND has a FALLBACK path (use SKETCH
output degraded) instead of PLAN FAILED. Only SKETCH failure terminates the entire plan.
EXPAND degradation produces lower-quality plans that VALIDATE may catch and reject, but
the pipeline continues.

#### 7.6.3 Stage Delta on Failure

If EXPAND uses the fallback path, PipelineController emits:

```yaml
k1.planner.delta.v1:
  type: "stage_complete"
  stage: "EXPAND"
  status: "degraded"                       # Not "completed" -- signals quality reduction
  tokens_used: stage_token_usage[EXPAND]   # May be 0 if LLM never responded
  tool_calls_used: <count>
  hil_rounds: 0
  duration_ms: <stage wall time>
  degradation_reason: "expand_llm_fallback" | "expand_parse_fallback"
```

The `"degraded"` status is recorded by the Learning Loop for quality tracking. It does
NOT prevent the pipeline from continuing to VALIDATE.

---

## 8. Stage 3: VALIDATE -- Deep Dive

Two-phase validation: deterministic structural checks followed by an LLM arbiter for
semantic quality. Performance envelope: ~500 tokens, p50 2s / p99 3s.
This is the safety gate -- nothing reaches COMMIT without passing VALIDATE.

Plan FSM transition on entry: `EXPANDING -> VALIDATING`. On exit: `VALIDATING -> COMMITTING`
(approved), or `VALIDATING -> FAILED` (rejected after retry).

ValidateService is the owning internal service (~45 tests). It performs two deterministic
checks (no LLM), one LLM arbiter call, and optionally triggers HIL approval via
HILCoordinator. ValidateService has dependencies on:

- `ILLMPort` (LLM arbiter call)
- `IFabricRetrievalPort` (capability existence check, or cached from EXPAND)
- `HILCoordinator` (optional approval for high-impact plans)
- `PipelineController` (receives verdict, tracks token usage, routes revise loop)

ValidateService makes ZERO tool calls through ToolCallRouter. The capability existence
check uses `IFabricRetrievalPort` directly (or cached discovery results from EXPAND).

### 8.1 Inputs

ValidateService receives the `ExpandedPlan` from PipelineController, plus the original
`PlanRequest` carried through the pipeline context.

**From ExpandedPlan** (internal type, Section 7.4):

```yaml
ExpandedPlan:
  steps: List[PlanStep]                    # Fully parameterized (14 fields each)
  dependencies: Dict[str, List[str]]       # step_id -> [predecessor_step_ids]
```

**From PlanRequest** (carried through pipeline context):

| Field | Type | VALIDATE Usage |
| ----- | ---- | -------------- |
| `intent` | `str` | Injected into LLM arbiter prompt for coherence check |
| `trace_id` | `str` | Propagated to LLM call (FAB-09) |
| `constraints` | `Dict` | `safety_band` evaluated against step safety bands |

### 8.2 Deterministic Checks (No LLM)

ValidateService runs two deterministic checks BEFORE the LLM arbiter. If either fails,
the plan is immediately REJECTED without spending LLM tokens. These checks enforce
invariants PLAN-09 (DAG acyclicity) and PLAN-08 (capability validity).

#### 8.2.1 Check 1: DAG Cycle Detection (PLAN-09)

**Algorithm**: Kahn's topological sort.

**Input**: `ExpandedPlan.dependencies: Dict[str, List[str]]` + `ExpandedPlan.steps[].id`

**Procedure**:

```text
 1. Build adjacency list from dependencies dict.
    For each entry {step_id: [dep_ids]}: add edge dep_id -> step_id.

 2. Compute in-degree for each step.
    Steps with no dependencies have in-degree 0.

 3. Initialize queue with all zero-in-degree steps.

 4. While queue is non-empty:
    a. Dequeue step (add to topological order).
    b. For each successor of dequeued step:
       - Decrement successor's in-degree.
       - If in-degree reaches 0: enqueue successor.
    c. Increment visited counter.

 5. Result:
    IF visited == len(steps): DAG is acyclic. PASS.
    IF visited < len(steps): Cycle detected. FAIL.
```

**Additional structural checks** performed alongside DAG validation:

| Check | What | Failure |
| ----- | ---- | ------- |
| Self-reference | No step depends on itself | `deps` contains own `id` |
| Dangling reference | All dep IDs reference existing steps | `deps` contains unknown step ID |
| Inter-step ref consistency | `$<step_id>.result.*` params must have matching `deps` entry | Param references step not in `deps` |
| Step ID uniqueness | All `step.id` values are distinct | Duplicate IDs |

**Complexity**: O(V + E) where V = step count, E = dependency edge count. For typical
plans (4-10 steps): sub-millisecond.

**On failure**: ValidateService returns a rejection verdict immediately:

```yaml
ValidationVerdict:
  status: "reject"
  reasons: ["DAG cycle detected: s2 -> s3 -> s2"]  # or specific structural error
  suggested_fixes: []                                 # Deterministic failures have no fix suggestions
  deterministic_pass: false
```

#### 8.2.2 Check 2: Capability Existence (PLAN-08)

**Purpose**: Verify every `PlanStep.capability` references a real capability registered
in the Fabric Registry. Prevents the LLM from hallucinating capability names.

**Input**: `ExpandedPlan.steps[].capability` for each step.

**Procedure**:

```text
 For each step in ExpandedPlan.steps:
   IF step.capability starts with "$":
     SKIP -- inter-step reference (e.g., "$s1.result.agent_name")
     Resolved at execution time, not validateable at plan time.

   IF step.capability == "tool.meta.build_agent":
     SKIP -- reserved meta-capability, always valid.

   ELSE:
     Query IFabricRetrievalPort or check cached EXPAND discovery results:
       Does capability name exist in Fabric Registry?
       IF yes: PASS for this step.
       IF no: FAIL -- unknown capability.
```

**Route**: `ValidateService` -> `IFabricRetrievalPort` (for live check) or cached
`RetrievalResult` from EXPAND stage (preferred, avoids redundant I/O).

**On failure**: ValidateService returns a rejection verdict:

```yaml
ValidationVerdict:
  status: "reject"
  reasons: ["Unknown capability: tool.execute.nonexistent_tool (step s2)"]
  suggested_fixes: ["Replace with tool.execute.similar_tool from registry"]
  deterministic_pass: false
```

#### 8.2.3 Deterministic Check Summary

Both checks run sequentially (DAG first, then capability). Total latency: <5ms.

```text
 ValidateService.run_deterministic_checks(expanded_plan)
   |
   |-- check_dag_acyclicity(steps, dependencies)
   |     -> DagCheckResult{passed: bool, cycle_path: List[str] | null}
   |
   |-- check_capability_existence(steps, cached_capabilities)
   |     -> CapCheckResult{passed: bool, missing: List[str]}
   |
   |-- IF both passed:
   |     deterministic_pass = true
   |     Proceed to LLM arbiter (Section 8.3)
   |
   |-- IF either failed:
         deterministic_pass = false
         Return ValidationVerdict{status: "reject", ...}
         Do NOT call LLM arbiter (save tokens)
```

### 8.3 LLM Arbiter Call

If deterministic checks pass, ValidateService makes one LLM call to assess semantic
quality: coherence, safety, completeness, and feasibility.

#### 8.3.1 Prompt Assembly Architecture

ValidateService uses the slot-based composition pattern (same as Sections 6.3.1, 7.3.1).

**Prompt structure** (2 segments: system + user):

```text
 SYSTEM SEGMENT
   Slot: ROLE_DEFINITION      -- Declares validation arbiter task
   Slot: OUTPUT_SCHEMA         -- JSON Schema for ValidationVerdict

 USER SEGMENT (assembled from ExpandedPlan + PlanRequest)
   Slot: ORIGINAL_INTENT       -- Source: PlanRequest.intent
   Slot: PLAN_SUMMARY          -- Source: ExpandedPlan rendered as structured summary
   Slot: STEP_DETAILS          -- Source: Per-step capability, params, deps, side effects
   Slot: DETERMINISTIC_RESULTS -- Source: DAG check PASS, capability check PASS
   Slot: CONSTRAINTS           -- Source: PlanRequest.constraints (safety_band)
```

**Slot input contracts**:

| Slot | Source Type | Required | Content |
| ---- | ----------- | -------- | ------- |
| ORIGINAL_INTENT | `PlanRequest.intent: str` | Yes | User's original request (coherence anchor) |
| PLAN_SUMMARY | Derived from `ExpandedPlan` | Yes | Step count, dependency structure (waves), total estimated duration, side-effect summary |
| STEP_DETAILS | `ExpandedPlan.steps: List[PlanStep]` | Yes | Per step: `id`, `capability`, `params` (keys only, not values), `deps`, `has_side_effects`, `safety_band_min`, `is_optional` |
| DETERMINISTIC_RESULTS | `DagCheckResult` + `CapCheckResult` | Yes | "DAG: acyclic (N steps, M edges). Capabilities: all N verified in registry." |
| CONSTRAINTS | `PlanRequest.constraints: Dict` | Yes | `safety_band`, any user-specified limits |

**Output contract** (what the LLM MUST return):

```json
{
  "type": "object",
  "required": ["status", "reasons"],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["approved", "revise", "reject"],
      "description": "approved = proceed to COMMIT. revise = re-run EXPAND with fixes. reject = plan failed."
    },
    "reasons": {
      "type": "array",
      "items": {"type": "string"},
      "minItems": 1,
      "description": "Human-readable reasons for the verdict"
    },
    "suggested_fixes": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Actionable fixes for revise/reject verdicts (empty for approved)"
    },
    "coherence_score": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "How well the plan addresses the original intent [0.0-1.0]"
    },
    "safety_assessment": {
      "type": "string",
      "enum": ["safe", "caution", "unsafe"],
      "description": "Overall safety classification"
    },
    "completeness": {
      "type": "boolean",
      "description": "True if all aspects of the intent are addressed by at least one step"
    }
  }
}
```

**Arbiter evaluation dimensions** (instructed in ROLE_DEFINITION slot):

| Dimension | What the Arbiter Checks | Reject If |
| --------- | ----------------------- | --------- |
| Coherence | Do all steps logically serve the intent? | Steps unrelated to intent |
| Safety | Are side-effect steps appropriate given safety_band? | RED-band operations in GREEN-band plan |
| Completeness | Does the plan cover all aspects of the intent? | Major intent aspects missing |
| Feasibility | Are step params reasonable? Are dependencies satisfiable? | Impossible params, contradictory deps |
| Redundancy | Are there duplicate or unnecessary steps? | Significant waste (mild = revise, severe = reject) |

#### 8.3.2 HubRequest Construction

```yaml
HubRequest:
  capability: CapabilityType.STRUCTURED     # Structured output (JSON schema enforced)
  payload:
    type: StructuredOutputPayload
    fields:
      system_prompt: str                    # SYSTEM SEGMENT (ROLE + OUTPUT_SCHEMA)
      user_prompt: str                      # USER SEGMENT (all slots rendered)
      response_schema: Dict                 # JSON Schema from output contract above
  constraints:
    type: RequestConstraints
    fields:
      max_tokens: 512                       # PLAN-11: tighter than SKETCH/EXPAND
      timeout_ms: 3000                      # VALIDATE LLM timeout (tightest)
      priority: "INTERACTIVE"
      temperature: 0.1                      # Very low -- deterministic verdict preferred
      consumer_id: "planner"                # Cost tracking (MH-11)
  trace_id: PlanRequest.trace_id            # Cognitive trace propagation (FAB-09)
```

**Key design decisions**:

- `capability: STRUCTURED` (not CHAT) -- Model Hub enforces the `response_schema`,
  guaranteeing the output conforms to the ValidationVerdict JSON Schema. This eliminates
  parse failures for the arbiter (unlike SKETCH/EXPAND which use CHAT and must handle
  malformed JSON).
- `temperature: 0.1` -- Lowest of all 3 LLM stages. The arbiter should produce
  consistent, reproducible verdicts for the same plan.
- `max_tokens: 512` -- Sufficient for verdict + reasons + fixes. Verdict structure is
  compact; most tokens go to `reasons[]` strings.

**Token budget allocation**:

| Component | Budget | Notes |
| --------- | ------ | ----- |
| System segment (ROLE + OUTPUT_SCHEMA) | ~150 tokens | Compact (structured output schema included) |
| ORIGINAL_INTENT | Variable | Same as prior stages |
| PLAN_SUMMARY | ~100 tokens | Counts, structure, estimates |
| STEP_DETAILS | ~30 tokens per step x N | Param keys only, not values |
| DETERMINISTIC_RESULTS | ~30 tokens | Fixed size (2 check summaries) |
| CONSTRAINTS | ~20 tokens | Minimal |
| **Total input estimate** | **350-500 tokens** | Leaves ~200-350 for LLM response |
| **LLM response budget** | **max_tokens: 512** | PLAN-11 enforced ceiling |

**Routing path**:

```text
 ValidateService.execute()
   |
   |-- run_deterministic_checks(expanded_plan)
   |     -> deterministic_pass: true
   |
   |-- assemble_arbiter_prompt(expanded_plan, intent, constraints, det_results)
   |     -> system_prompt: str, user_prompt: str
   |
   |-- build_hub_request(system_prompt, user_prompt, validate_constraints)
   |     -> HubRequest (STRUCTURED capability)
   |
   |-- ILLMPort.execute(hub_request)
   |     -> LLMGatewayAdapter -> LLM_REQUEST_BUS -> Model Hub -> Provider
   |     <- HubResponse (structured, schema-validated by Model Hub)
   |
   |-- parse_verdict(hub_response.result.content)
   |     -> ValidationVerdict (typed)
   |
   |-- record_token_usage(hub_response.metadata.usage)
         -> stage_token_usage[VALIDATE] += total_tokens
```

#### 8.3.3 ValidationVerdict Type

The parsed LLM output is mapped to a typed `ValidationVerdict`:

```yaml
ValidationVerdict:
  status: str                              # "approved" | "revise" | "reject"
  reasons: List[str]                       # At least 1 reason (schema enforced)
  suggested_fixes: List[str]               # Empty for "approved", populated for "revise"/"reject"
  coherence_score: float                   # [0.0, 1.0] -- LLM self-assessment
  safety_assessment: str                   # "safe" | "caution" | "unsafe"
  completeness: bool                       # Does plan address full intent?
  deterministic_pass: bool                 # True (set by ValidateService, not LLM)
```

`ValidationVerdict` is an internal type (does not cross the Planner boundary). It flows
from ValidateService -> PipelineController for routing.

### 8.4 HIL Approval (Conditional)

After the LLM arbiter returns `status: "approved"`, ValidateService evaluates whether
HIL (Human-in-the-Loop) approval is needed. This is the second of two HIL interaction
points (the first is HIL Clarification in Stage 1 SKETCH).

#### 8.4.1 Trigger Conditions

ValidateService triggers HIL approval when ALL of the following are true:

1. **High-impact operations present**: At least one step has `has_side_effects: true`
   AND the side effect is external (booking, ordering, sending messages -- not internal
   reads or computations).
2. **Not auto-approvable**: The plan contains a step with `safety_band_min` higher
   than GREEN, OR the arbiter's `safety_assessment` is `"caution"`.
3. **LLM arbiter approved**: The plan must pass the LLM arbiter first. If the arbiter
   says "revise" or "reject", HIL approval is not triggered.

**Auto-approve rule**: If ALL steps with `has_side_effects: true` have
`safety_band_min: "GREEN"` AND the arbiter's `safety_assessment: "safe"`, ValidateService
auto-approves without user interaction. This covers the common case of safe plans that
don't need human oversight.

#### 8.4.2 Approval Flow

```text
 ValidateService -> HILCoordinator.request_approval(
     request_id=plan_request.request_id,
     plan_summary=<formatted plan summary>
   )

 HILCoordinator:
   1. Generate approval presentation via ILLMPort:
      HubRequest{capability: CHAT, constraints: {max_tokens: 400, timeout_ms: 3000}}
      Slot-based prompt -- renders plan summary with side-effect highlights,
      estimated costs, and affected external systems.
      (This 400-token LLM call is WITHIN the VALIDATE stage.)

   2. Emit event via IEventPort:
      topic: "k1.hil.approval_request.v1"
      payload: {
        request_id: plan_request.request_id,
        plan_id: <pending, assigned in COMMIT>,
        summary: "<LLM-formatted plan summary>",
        options: ["approve", "modify", "reject"],
        side_effects: [
          {step_id: "s1", capability: "tool.execute.restaurant_booking",
           description: "Books restaurant for 8 on Feb 21"},
          {step_id: "s2", capability: "tool.execute.cake_order",
           description: "Orders birthday cake for Feb 21"}
        ],
        safety_assessment: "<arbiter assessment>",
        estimated_duration_ms: <plan total estimate>
      }

   3. Route: IEventPort -> Event Bus -> Concierge -> User
      Concierge stores request_id in PENDING_CLARIFICATIONS map.
      Concierge presents options to user via active channel.

   4. WAIT for response event:
      topic: "k1.hil.approval_response.v1"
      HILCoordinator subscribes, correlates by request_id.
      Timeout: 120s (longer than clarification -- user needs time to review plan).

   5. On response:
      HILApprovalResponse{
        request_id: uuid,
        plan_id: uuid,
        response_type: "approve" | "modify" | "reject",
        modifications: Dict | null,
        trace_id: str
      }
```

#### 8.4.3 Response Routing

| Response Type | Action | Next Stage |
| ------------- | ------ | ---------- |
| `"approve"` | Proceed as-is | COMMIT (Stage 4) |
| `"modify"` | Apply user modifications to ExpandedPlan, re-run deterministic checks (8.2) | VALIDATE re-check, then COMMIT |
| `"reject"` | Plan FAILED | FSM -> FAILED, emit `k1.planner.plan.failed.v1` |
| Timeout (120s) | Auto-approve IF all steps safe (`safety_band_min: "GREEN"`) | COMMIT (Stage 4) |
| Timeout (120s) | Plan FAILED IF any step unsafe (`safety_band_min: "AMBER" or "RED"`) | FSM -> FAILED |

**Modification handling**: If the user responds with `"modify"`, the `modifications`
dict contains field-level overrides per step:

```yaml
modifications:
  "s1":
    params:
      party_size: 10                       # User changed from 8 to 10
  "s2":
    remove: true                           # User removed the cake step entirely
```

ValidateService applies modifications to the ExpandedPlan, removes deleted steps,
re-runs deterministic checks (DAG may have changed), and proceeds to COMMIT if valid.
No additional LLM arbiter call -- the user's explicit approval supersedes the arbiter.

#### 8.4.4 Event Namespace

The HIL approval events belong to the PLANNING-TIME namespace (same family as
clarification, distinct from execution-time HIL):

```text
 PLANNING-TIME (Planner owns):
   k1.hil.approval_request.v1             -- Planner -> Concierge -> User
   k1.hil.approval_response.v1            -- User -> Concierge -> Planner
```

### 8.5 Revise Loop

When the LLM arbiter returns `status: "revise"`, PipelineController routes back to
EXPAND for a second attempt with injected fix guidance.

#### 8.5.1 Revise Protocol

```text
 PipelineController.handle_verdict(verdict):
   |
   |-- IF verdict.status == "approved":
   |     Proceed to HIL approval check (Section 8.4)
   |     IF approved/auto-approved: proceed to COMMIT
   |
   |-- IF verdict.status == "revise" AND revise_count == 0:
   |     revise_count += 1
   |     Inject verdict.suggested_fixes into EXPAND prompt context
   |     Re-run EXPAND (Stage 2) with augmented SKETCH_PLAN slot:
   |       SKETCH_PLAN now includes:
   |         - Original SketchResult.rough_steps
   |         - ARBITER_FEEDBACK: verdict.reasons[] + suggested_fixes[]
   |     Re-run VALIDATE (Stage 3) on new ExpandedPlan
   |     IF second verdict == "approved": proceed to COMMIT
   |     IF second verdict == "revise": treat as "approved" (best-effort)
   |     IF second verdict == "reject": plan FAILED
   |
   |-- IF verdict.status == "revise" AND revise_count > 0:
   |     Treat as "approved" (best-effort, max 1 revise loop)
   |
   |-- IF verdict.status == "reject" AND reject_count == 0:
   |     reject_count += 1
   |     Re-run EXPAND with rejection reasons as hard constraints
   |     Re-run VALIDATE on new ExpandedPlan
   |     IF second verdict == "approved" or "revise": proceed
   |     IF second verdict == "reject": plan FAILED
   |
   |-- IF verdict.status == "reject" AND reject_count > 0:
         Plan FAILED
         Plan FSM -> FAILED
         Emit k1.planner.plan.failed.v1
```

#### 8.5.2 Revise Loop Bounds

| Counter | Max | Behavior at Max |
| ------- | --- | --------------- |
| `revise_count` | 1 | Second "revise" treated as "approved" (best-effort) |
| `reject_count` | 1 | Second "reject" terminates plan (FAILED) |
| Total EXPAND re-runs | 2 | 1 revise + 1 reject OR 2 rejects max |

The revise loop adds at most one additional EXPAND + VALIDATE cycle to the pipeline.
Impact on timing budget:

```text
 Normal path (no revise):
   SKETCH (4s) + EXPAND (3s) + VALIDATE (2s) + COMMIT (<0.1s) = ~9s

 Revise path (1 loop):
   SKETCH (4s) + EXPAND (3s) + VALIDATE (2s) + EXPAND (3s) + VALIDATE (2s) + COMMIT (<0.1s) = ~14s

 Max path (2 EXPAND re-runs):
   SKETCH (4s) + EXPAND x3 (9s) + VALIDATE x3 (6s) + COMMIT (<0.1s) = ~19s
```

All paths fit within the 45s CB_PLANNER timeout budget (PLAN-04) with margin.

#### 8.5.3 Token Impact of Revise

Each revise loop adds approximately:

- EXPAND re-run: ~1K tokens
- VALIDATE re-run: ~500 tokens
- Total additional: ~1.5K tokens per loop

Worst case total plan tokens: 3.5K (normal) + 3K (2 loops) = ~6.5K tokens.
PipelineController tracks cumulative `stage_token_usage` across retries.

### 8.6 Error Recovery: ERR_VALIDATE_FAIL

VALIDATE errors are handled by the ERR_VALIDATE_FAIL recovery path defined in
`planner.mmd`. The error wiring:
`SVC_VALIDATE -> ERR_VALIDATE_FAIL -> retry EXPAND / auto-approve / plan.failed`.

#### 8.6.1 Failure Scenarios in VALIDATE

| Failure | Cause | Detection |
| ------- | ----- | --------- |
| DAG cycle detected | EXPAND produced circular deps | Kahn's algorithm visited < step count |
| Unknown capability | EXPAND referenced non-existent capability | Capability not in Fabric Registry |
| LLM arbiter timeout | Model Hub / provider slow | LLMGatewayAdapter 3000ms timeout |
| LLM arbiter error | Provider error, rate limit | HubResponse error or exception |
| Verdict = "reject" (twice) | Plan fundamentally flawed | Second arbiter rejection |
| HIL approval timeout | User unresponsive | HILCoordinator 120s timeout |
| HIL approval rejected | User explicitly rejected plan | `response_type: "reject"` |

#### 8.6.2 Recovery Strategy

```text
 ERR_VALIDATE_FAIL decision tree:

 1. Deterministic check failure (DAG cycle or unknown capability):
    -> Route verdict.suggested_fixes to EXPAND for re-run (revise loop, Section 8.5)
    -> If re-run also fails deterministic checks: plan FAILED
    -> This is unusual -- indicates EXPAND LLM produced structurally invalid output

 2. LLM arbiter timeout or error (first attempt):
    -> AUTO-APPROVE IF deterministic checks BOTH PASSED
    -> Rationale: structural integrity is confirmed; LLM quality check is nice-to-have
    -> Log warning: "arbiter_unavailable, auto_approved_on_deterministic_pass"
    -> This is the key graceful degradation: plans proceed without LLM oversight
       when the arbiter is down, as long as structural checks pass.

 3. LLM arbiter timeout or error (if deterministic checks FAILED):
    -> Plan FAILED (cannot auto-approve structurally invalid plan)

 4. Verdict = "reject" after revise loop exhausted:
    -> Plan FAILED
    -> Plan FSM -> FAILED
    -> Emit: k1.planner.plan.failed.v1{
         request_id, stage: "VALIDATE",
         error: "ERR_VALIDATE_FAIL",
         message: "Plan rejected by arbiter after retry",
         reasons: verdict.reasons,
         trace_id
       }

 5. HIL approval timeout:
    -> Auto-approve IF all steps safe (all safety_band_min == "GREEN")
    -> Otherwise: plan FAILED

 6. HIL approval rejected:
    -> Plan FAILED (explicit user rejection is final)
```

#### 8.6.3 Stage Delta

On completion (success or failure), PipelineController emits:

```yaml
k1.planner.delta.v1:
  type: "stage_complete"
  stage: "VALIDATE"
  status: "completed" | "degraded" | "failed"
  tokens_used: stage_token_usage[VALIDATE]    # Cumulative across revise loops
  tool_calls_used: 0                          # VALIDATE uses no ToolCallRouter calls
  hil_rounds: 0 | 1                           # 0 = no HIL, 1 = approval requested
  duration_ms: <stage wall time>              # Includes HIL wait time if applicable
  verdict: "approved" | "revise" | "reject" | "auto_approved"
  revise_loops: 0 | 1 | 2
  deterministic_pass: true | false
```

The `"auto_approved"` verdict value signals that the arbiter was unavailable but
deterministic checks passed. The Learning Loop uses this for quality tracking.

---

## 9. Stage 4: COMMIT -- Deep Dive

Purely deterministic. Zero LLM calls (PLAN-03 enforced at constructor level -- CommitService
has NO `ILLMPort` dependency). Zero tool calls. Performance envelope: 0 tokens, p50 20ms /
p99 100ms.

Plan FSM transition on entry: `VALIDATING -> COMMITTING`. On exit: `COMMITTING -> COMPLETED`.

CommitService is the owning internal service (~30 tests). It performs three sequential
operations: (1) build the CommittedPlan, (2) persist to K0 WAL, (3) emit the plan delivery
event. CommitService has dependencies on:

- `IBridgePort` (WAL persistence via `persist_plan()`)
- `IEventPort` (plan delivery via `k1.planner.plan.ready.v1`)
- `IDeltaEmitPort` (stage delta)

CommitService explicitly does NOT depend on:

- `ILLMPort` -- PLAN-03 enforced at constructor level (no parameter accepted)
- `IFabricRetrievalPort` -- no discovery needed
- `IStateReadPort` -- no session state reads
- `ToolCallRouter` -- no tool calls

### 9.1 Inputs

CommitService receives the validated `ExpandedPlan` from PipelineController, plus the
original `PlanRequest` carried through the pipeline context, plus the `ValidationVerdict`
from VALIDATE (for audit).

| Input | Source | Usage in COMMIT |
| ----- | ------ | --------------- |
| `ExpandedPlan.steps` | VALIDATE output | Frozen into `CommittedPlan.steps` |
| `ExpandedPlan.dependencies` | VALIDATE output | Frozen into `CommittedPlan.dependencies` |
| `PlanRequest.request_id` | Pipeline context | Echoed into `CommittedPlan.request_id` for correlation |
| `PlanRequest.intent` | Pipeline context | Echoed into `CommittedPlan.intent` |
| `PlanRequest.trace_id` | Pipeline context | Echoed into `CommittedPlan.trace_id` (FAB-09) |
| `ValidationVerdict` | VALIDATE output | Recorded in stage delta (audit trail) |
| `stage_token_usage` | PipelineController | Summed for total token count in plan delta |

### 9.2 CommittedPlan Assembly

CommitService builds the `CommittedPlan` dataclass -- the Planner's sole output artifact.
This type crosses the Planner boundary and is consumed by the Orchestrator.

#### 9.2.1 Assembly Steps

```text
 CommitService.execute(expanded_plan, plan_request, verdict):
   |
   |-- 1. Generate plan_id
   |     plan_id = uuid4()     -- Globally unique, used as WAL dedup key
   |
   |-- 2. Set created_at
   |     created_at = time.time()   -- Epoch seconds (float)
   |
   |-- 3. Freeze step list
   |     steps = expanded_plan.steps   -- List[PlanStep], immutable (frozen dataclass)
   |     No modifications to steps in COMMIT -- VALIDATE approved them as-is
   |     (or with HIL modifications already applied in Section 8.4.3)
   |
   |-- 4. Freeze dependency graph
   |     dependencies = expanded_plan.dependencies   -- Dict[str, List[str]]
   |
   |-- 5. Compute estimated_duration_ms (optional)
   |     Sum of step.timeout_ms for critical path (longest dependency chain)
   |     This is a Planner estimate -- Orchestrator may override with runtime data
   |
   |-- 6. Assemble CommittedPlan
   |     CommittedPlan(
   |       plan_id=plan_id,
   |       request_id=plan_request.request_id,
   |       intent=plan_request.intent,
   |       steps=steps,
   |       trace_id=plan_request.trace_id,
   |       dependencies=dependencies,
   |       estimated_duration_ms=estimated_duration_ms,
   |       created_at=created_at
   |     )
   |
   |-- 7. Defensive validation (CommittedPlan.__post_init__)
         CommittedPlan is a frozen dataclass with __post_init__ validation:
         - plan_id non-empty
         - request_id non-empty
         - steps non-empty
         - All dependency keys are valid step IDs
         - All dependency values reference valid step IDs
         - Dependency graph is acyclic (Kahn's algorithm -- redundant with VALIDATE,
           defensive belt-and-suspenders)
         On validation failure: raise ValueError (should never happen if VALIDATE passed)
```

#### 9.2.2 CommittedPlan Type (Source of Truth: `k1/orchestrator/types.py`)

```yaml
CommittedPlan:                                   # @dataclass(frozen=True)
  plan_id: str                                   # uuid4(), assigned in COMMIT
  request_id: str                                # Echoed from PlanRequest (correlation key)
  intent: str                                    # Echoed from PlanRequest
  steps: List[PlanStep]                          # 14 fields each (Section 4.4)
  trace_id: str                                  # Cognitive trace propagation (FAB-09)
  dependencies: Dict[str, List[str]]             # step_id -> [predecessor_step_ids]
  estimated_duration_ms: Optional[int]           # Planner's estimate (optional)
  created_at: float                              # Epoch seconds, set in COMMIT
```

**Serialization methods** (for event bus transport):

- `to_dict() -> Dict[str, Any]`: Serializes all fields. Steps serialized via
  `PlanStep.to_dict()`. Dependencies preserved as `Dict[str, List[str]]`.
- `from_dict(data) -> CommittedPlan`: Deserializes. Steps via `PlanStep.from_dict()`.
  Used by Orchestrator's `_on_plan_ready()` handler.

**V1 scope reduction**: `token_budget_max` and `cost_budget_max_usd` fields are REMOVED
from CommittedPlan (PLAN-07 deferred to V2). Planner does not yet have upstream data
to populate these. V2: Planner will populate from Fabric cost estimates.

#### 9.2.3 Meta-Agent Pattern in CommittedPlan

If the plan includes meta-agent creation steps (Section 7.4.5), the CommittedPlan
contains `build_agent` steps with special structure:

```yaml
# Example PlanStep within CommittedPlan (meta-agent creation)
PlanStep:
  id: "s2"
  capability: "tool.meta.build_agent"
  description: "Create a restaurant booking specialist agent"
  params:
    name: "restaurant_booker"
    role: "Restaurant booking and reservation management"
    tools_granted: ["tool.execute.restaurant_search", "tool.execute.restaurant_booking"]
    prompt_template: "<discovered prompt template ID>"
    seed_context: {"cuisine_preference": "Italian", "location": "downtown"}
  deps: ["s1"]                                   # Depends on discovery step
  has_side_effects: false                        # Agent creation is internal
  safety_band_min: "GREEN"

# Subsequent step references the created agent
PlanStep:
  id: "s3"
  capability: "$s2.result.agent_name"            # Resolved at execution time
  description: "Book restaurant using specialist agent"
  params: {party_size: 8, date: "2026-02-21"}
  deps: ["s2"]                                   # Must wait for agent creation
  has_side_effects: true
  safety_band_min: "AMBER"
```

The Planner commits the DAG structure. The Orchestrator executes it (PLAN-06: Planner
NEVER executes capabilities). The `$s2.result.agent_name` reference is resolved by
the Orchestrator's DAGExecutor at runtime, not by the Planner.

### 9.3 K0 WAL Persistence

After assembling the CommittedPlan, CommitService persists it to the K0 Write-Ahead Log
for durability. This is the ONLY write operation the Planner performs to K0.

#### 9.3.1 Persistence Protocol

```text
 CommitService.persist(committed_plan):
   |
   |-- IBridgePort.persist_plan(committed_plan)
   |     Route: BridgeAdapter -> K0 Bridge -> IKernelCommandPort -> WAL write
   |
   |-- Properties:
   |     Fire-and-forget: CommitService does NOT await confirmation.
   |     Idempotent: plan_id is the dedup key. Re-persisting the same plan_id
   |                 is a no-op (WAL uses plan_id for upsert semantics).
   |     Best-effort: Plan validity does NOT depend on WAL persistence.
   |                  The plan is correct and deliverable even if WAL fails.
   |
   |-- On success:
   |     Log: "commit.wal_persisted" {plan_id, duration_ms}
   |
   |-- On failure:
         Log warning: "commit.wal_persist_failed" {plan_id, error}
         Retry once (same call, same plan_id -- idempotent).
         If retry also fails: log error, proceed to plan delivery anyway.
         WAL failure does NOT block plan delivery.
```

#### 9.3.2 Why Fire-and-Forget?

The K0 WAL serves **durability** (crash recovery), not **correctness**. The CommittedPlan
is a self-contained artifact that carries all information needed for execution. If the WAL
write fails:

- The plan still reaches the Orchestrator via the event bus (Section 9.4).
- On crash recovery, the plan will be re-requested by the Orchestrator if the
  PendingPlanContext times out.
- The WAL is an optimization for faster recovery, not a prerequisite for plan delivery.

The persist call uses `IBridgePort`, routed through `BridgeAdapter` to the K0 Bridge's
`IKernelCommandPort.persist_plan()` method. The K0 Bridge handles the actual WAL write
mechanics (K0 domain, opaque to the Planner).

### 9.4 Plan Delivery

The final operation: emit the CommittedPlan as an event for the Orchestrator to consume.

#### 9.4.1 Event Emission

```text
 CommitService.deliver(committed_plan):
   |
   |-- IEventPort.publish(
   |     topic="k1.planner.plan.ready.v1",
   |     payload=committed_plan.to_dict()
   |   )
   |
   |-- Route: EventBusAdapter -> K1 Event Bus -> Orchestrator subscription
   |
   |-- Consumers:
   |     Orchestrator (primary): _on_plan_ready() handler
   |       -> Deserializes CommittedPlan.from_dict(payload)
   |       -> Enqueues to Orchestrator Mailbox at INTERACTIVE priority
   |       -> Correlates via request_id -> PendingPlanContext
   |     Learning Loop (observability): records plan metadata for drift detection
```

#### 9.4.2 Event Schema

The `k1.planner.plan.ready.v1` event payload is the full CommittedPlan serialized
via `to_dict()`:

```yaml
k1.planner.plan.ready.v1:
  plan_id: str                                   # uuid4
  request_id: str                                # Echo contract (WB 10.10)
  intent: str
  steps:                                         # List of PlanStep dicts
    - id: str
      capability: str
      description: str
      params: Dict
      deps: List[str]
      has_side_effects: bool
      safety_band_min: str
      is_optional: bool
      output_schema: Dict | null
      tools_granted: List[str]
      timeout_ms: int
      retry_policy: Dict | null
      meta: Dict
      condition: Dict | null
  dependencies: Dict[str, List[str]]
  estimated_duration_ms: int | null
  created_at: float
  trace_id: str
```

#### 9.4.3 Correlation Contract

The `request_id` field in CommittedPlan MUST match the original `PlanRequest.request_id`.
This is the correlation key that allows the Orchestrator to match the delivered plan
to the correct `PendingPlanContext` (ADR-1.1.12 / SPEC-2).

If `request_id` does not match any pending context, the Orchestrator logs a warning
and drops the plan (orphaned plan -- typically caused by timeout reaper already cleaning
up the PendingPlanContext).

#### 9.4.4 Failure Events

If the plan fails at any stage, CommitService (or PipelineController) emits a failure
event instead of the plan.ready event:

```yaml
k1.planner.plan.failed.v1:
  request_id: str                                # Echo contract
  reason: str                                    # Enum: INTERNAL_ERROR | CAPABILITY_NOT_FOUND
                                                 #        | CONSTRAINT_UNSATISFIABLE | TIMEOUT
                                                 #        | HIL_REJECTED
  stage: str                                     # Which stage failed: SKETCH | EXPAND | VALIDATE
  error_details: str                             # Human-readable error message
  trace_id: str
```

Consumers: Orchestrator (cleans up PendingPlanContext), Learning Loop (drift detection).

If the plan is cancelled externally (via `cancel_plan()` or HIL rejection):

```yaml
k1.planner.plan.cancelled.v1:
  request_id: str
  reason: str
  trace_id: str
```

### 9.5 Plan FSM Transition

On successful delivery, the Plan FSM transitions `COMMITTING -> COMPLETED`:

```text
 CommitService.complete(plan_id):
   |
   |-- Plan FSM: COMMITTING -> COMPLETED
   |
   |-- Emit stage delta:
   |     k1.planner.delta.v1{
   |       type: "stage_complete",
   |       stage: "COMMIT",
   |       status: "completed",
   |       plan_id: plan_id,
   |       tokens_used: 0,                        # COMMIT uses no tokens
   |       tool_calls_used: 0,                     # COMMIT uses no tool calls
   |       duration_ms: <COMMIT stage wall time>,  # Typically 15-50ms
   |       wal_persisted: true | false             # Whether WAL write succeeded
   |     }
   |
   |-- Emit plan-end delta:
   |     k1.planner.delta.v1{
   |       type: "plan_end",
   |       plan_id: plan_id,
   |       total_tokens: sum(stage_token_usage),   # All stages combined
   |       total_duration_ms: <plan wall time>,
   |       total_tool_calls: tool_call_count,
   |       total_hil_rounds: hil_round_count,
   |       revise_loops: revise_count,
   |       stages_completed: ["SKETCH", "EXPAND", "VALIDATE", "COMMIT"]
   |     }
   |
   |-- Release plan lock: occupied = false
   |-- Clear state: PipelineController resets all counters and buffers
   |-- Plan FSM: COMPLETED -> IDLE (ready for next request)
```

### 9.6 Error Recovery: ERR_COMMIT_FAIL

COMMIT errors are the simplest to handle because the plan is already validated.
The error wiring: `SVC_COMMIT -> ERR_COMMIT_FAIL -> retry persist -> SVC_COMMIT`.

#### 9.6.1 Failure Scenarios in COMMIT

| Failure | Cause | Severity |
| ------- | ----- | -------- |
| WAL persist failure | K0 Bridge down, WAL disk full | Low (plan still valid) |
| WAL persist timeout | K0 Bridge slow | Low (fire-and-forget) |
| Event bus publish failure | K1 Event Bus down | High (plan undeliverable) |
| CommittedPlan validation error | Bug in VALIDATE (should never happen) | Critical |

#### 9.6.2 Recovery Strategy

```text
 ERR_COMMIT_FAIL decision tree:

 1. WAL persist failure (first attempt):
    -> Retry persist once (idempotent via plan_id dedup key)
    -> If retry succeeds: proceed to plan delivery
    -> If retry also fails: log error, proceed to plan delivery anyway
    -> WAL failure NEVER blocks plan delivery

 2. Event bus publish failure (first attempt):
    -> Retry publish once
    -> If retry succeeds: COMMIT complete
    -> If retry also fails:
       Plan is completed but undeliverable.
       Plan FSM -> COMPLETED (plan itself is valid).
       Log error: "commit.delivery_failed" {plan_id, request_id}
       Orchestrator side: PendingPlanContext times out after 45s (CB_PLANNER).
       Timeout reaper cleans up PendingPlanContext.
       This is the worst degradation path -- plan was computed but lost in transit.

 3. CommittedPlan validation error (__post_init__ raises ValueError):
    -> This indicates a bug in VALIDATE (approved a structurally invalid plan).
    -> Plan FSM -> FAILED
    -> Emit k1.planner.plan.failed.v1{reason: "INTERNAL_ERROR", stage: "COMMIT"}
    -> This should NEVER happen in production (belt-and-suspenders check).
```

#### 9.6.3 Invariant Enforcement Summary

| Invariant | How COMMIT Enforces It |
| --------- | ---------------------- |
| PLAN-03 | CommitService constructor accepts NO `ILLMPort` parameter. Zero LLM calls by design. |
| PLAN-07 | V1 deferred. `token_budget_max` not populated. V2: CommitService will read Fabric cost estimates. |
| PLAN-06 | CommitService has no `IFabricRetrievalPort` or `ToolCallRouter`. No capability execution. |

#### 9.6.4 Complete COMMIT Sequence (Nominal Path)

```text
 CommitService.execute(expanded_plan, plan_request, verdict):
   |
   |-- [1] plan_id = uuid4()
   |-- [2] created_at = time.time()
   |-- [3] committed_plan = CommittedPlan(plan_id, request_id, intent, steps, ...)
   |-- [4] committed_plan.__post_init__() validates (defensive)
   |-- [5] IBridgePort.persist_plan(committed_plan)         # Fire-and-forget
   |-- [6] IEventPort.publish("k1.planner.plan.ready.v1",
   |         committed_plan.to_dict())                      # Plan delivery
   |-- [7] Plan FSM: COMMITTING -> COMPLETED
   |-- [8] IDeltaEmitPort.emit(stage_delta)                 # Stage complete
   |-- [9] IDeltaEmitPort.emit(plan_end_delta)              # Plan complete
   |-- [10] Release lock, clear state
   |-- [11] Plan FSM: COMPLETED -> IDLE
   |
   Total: 11 steps, 0 LLM calls, 0 tokens, <100ms
```

---

## 10. Micro-Replan (ORCH-13 Support)

Partial pipeline re-entry for mid-DAG adaptive replanning. When the Orchestrator's
DAGExecutor discovers new information during step execution that invalidates remaining
steps, it triggers a synchronous micro-replan through the Planner.

This is fundamentally different from `request_plan()`:

| Dimension | `request_plan()` | `micro_replan()` |
| --------- | ---------------- | ---------------- |
| Delivery | Fire-and-forget (async, event-driven) | Synchronous (blocking, direct return) |
| Response | CommittedPlan via `k1.planner.plan.ready.v1` | `Optional[CommittedPlan]` returned directly |
| Correlation | PendingPlanContext via `request_id` | Direct `await` (no parking) |
| Context | Full ContextSnapshot (tier, session, state) | `completed_results` + `discoveries` + `remaining_steps` |
| Max calls | Unlimited per session | 1 per DAG execution (ORCH-13) |
| Timeout | 45s (CB_PLANNER) | 10s (hardcoded in PlannerAdapter) |
| On failure | AggregatedResult FAILED | Continue with original plan (graceful fallback) |
| HIL | Clarification + Approval possible | NO HIL (too time-sensitive) |

### 10.1 Protocol

#### 10.1.1 Invocation Path (Orchestrator Side -- Already Implemented)

The micro-replan is triggered by `MicroReplanCheckpoint`, a post-wave DAGGuard
(guard position G8) implemented at
[micro_replan.py](k1/orchestrator/orchestration/guards/micro_replan.py).

```text
 DAGExecutor.execute()
   |
   |-- Execute wave N (parallel step execution)
   |     -> WaveResult{step_results: List[StepResult]}
   |
   |-- Run post-wave guards (G8: MicroReplanCheckpoint.after_wave())
   |     |
   |     |-- [1] Extract discoveries from wave step results
   |     |       Source: CapabilityResult.data["discoveries"]
   |     |       -> List[Discovery{field, value, source_step_id}]
   |     |
   |     |-- [2] No discoveries? -> CONTINUE (no trigger)
   |     |
   |     |-- [3] Check param overlap heuristic:
   |     |       For each discovery.field, check if it overlaps any
   |     |       param name in remaining (unexecuted) steps.
   |     |       V1 heuristic: exact match OR substring match
   |     |       (case-insensitive, per ADR-1.1.11 Q8)
   |     |
   |     |-- [4] No overlap? -> CONTINUE (discovery irrelevant to remaining steps)
   |     |
   |     |-- [5] Replan budget exhausted? (replans_used >= max_replans)
   |     |       -> CONTINUE (budget is 1 per DAG in V1)
   |     |
   |     |-- [6] Build MicroReplanRequest (Section 10.2)
   |     |
   |     |-- [7] Call planner:
   |     |       await asyncio.wait_for(
   |     |         planner.micro_replan(request), timeout=10.0
   |     |       )
   |     |
   |     |-- [8] On success: CONTINUE with metadata["new_plan"] = CommittedPlan
   |     |       DAGExecutor reads metadata, replaces remaining waves
   |     |
   |     |-- [9] On timeout/error/None: CONTINUE (continue original plan)
   |
   |-- If metadata["new_plan"] exists:
   |     Merge new steps into DAG, replace remaining waves
   |-- Else:
         Continue with original remaining steps
```

#### 10.1.2 Delivery Protocol

```text
 Orchestrator (caller)                          Planner
   |                                              |
   |--- PlannerAdapter.micro_replan(request) ---->|
   |      |                                       |
   |      |-- _check_cb_open()                    |
   |      |     (CB_PLANNER: OPEN -> raise)       |
   |      |                                       |
   |      |-- asyncio.wait_for(10s) ------------>-|-- IPlannerMailbox.micro_replan(request)
   |      |                                       |     |
   |      |                                       |     v
   |      |                                       |   PipelineController (abbreviated mode)
   |      |                                       |     MICRO_SKETCH -> MICRO_EXPAND
   |      |                                       |       -> MICRO_VALIDATE -> COMMIT
   |      |                                       |     |
   |      |<-------- CommittedPlan --------------|<----+
   |      |                                       |
   |      |-- On success: cb.reset()              |
   |      |   return CommittedPlan                |
   |      |                                       |
   |      |-- On timeout: cb.trip()               |
   |      |   return None                         |--- [TELEMETRY] Emit:
   |      |                                       |    k1.planner.micro_replan.ready.v1
   |      |-- On error: cb.trip(), raise          |    (Learning Loop only, NOT delivery)
   |                                              |
   v                                              |
 DAGExecutor merges or continues                  |
```

**Critical protocol property**: `k1.planner.micro_replan.ready.v1` is TELEMETRY-ONLY.
It is emitted for Learning Loop observability (drift detection, quality tracking), NOT
for plan delivery. The Orchestrator does NOT subscribe to this event. Plan delivery is
via the synchronous return value.

#### 10.1.3 Plan FSM States for Micro-Replan

Micro-replan uses dedicated FSM states separate from the normal pipeline:

```text
 Normal plan:   IDLE -> SKETCHING -> EXPANDING -> VALIDATING -> COMMITTING -> COMPLETED
 Micro-replan:  IDLE -> MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE -> COMMITTING -> COMPLETED
```

The COMMITTING and COMPLETED states are shared -- the COMMIT stage is identical for
both normal plans and micro-replans (same CommitService, same WAL persist, same event
emission).

### 10.2 Inputs: MicroReplanRequest

MicroReplanRequest carries the current DAG execution state to the Planner, allowing
it to re-plan only the remaining portion.

**Source of truth**: `k1/orchestrator/types.py` -- `MicroReplanRequest`

```yaml
MicroReplanRequest:                              # @dataclass(frozen=True)
  original_plan_id: str                          # REQUIRED -- plan_id of CommittedPlan being replanned
  completed_results: Dict[str, StepResult]       # Results from completed steps (step_id -> StepResult)
  remaining_steps: List[PlanStep]                # REQUIRED, non-empty -- only uncompleted steps
  trace_id: str                                  # REQUIRED -- cognitive_trace_id propagation
  request_id: str = uuid4()                      # Auto-generated for this micro-replan request
  discoveries: List[Discovery] = []              # Runtime discoveries that triggered replan
  failure_context: Optional[FailureContext]       # Present if replan triggered by step failure
    = None
```

#### 10.2.1 Field Details

**completed_results: Dict[str, StepResult]**

Accumulated results from all waves completed before the trigger point. Each `StepResult`
contains:

```yaml
StepResult:                                      # @dataclass(frozen=True)
  step_id: str                                   # Matches PlanStep.id
  capability_name: str                           # Which capability was invoked
  status: StepStatus                             # COMPLETED | FAILED | CANCELLED | SKIPPED
  duration_ms: int = 0                           # Actual execution time
  result: Optional[CapabilityResult] = None      # Output data (if COMPLETED)
  retry_attempts: int = 0                        # How many retries occurred
  schema_retry: bool = False                     # Whether schema retry was used (ORCH-15)
  error_detail: Optional[str] = None             # Error message (if FAILED)
```

The Planner uses `completed_results` to understand what has already been accomplished
and what data is available for the remaining steps.

**remaining_steps: List[PlanStep]**

The uncompleted steps from the original CommittedPlan. These are the steps the Planner
may replace, modify, or reorder. PLAN-12 guarantees that completed steps are FROZEN --
the Planner cannot modify or remove them.

**discoveries: List[Discovery]**

New information found during step execution that triggered the replan evaluation:

```yaml
Discovery:                                       # @dataclass(frozen=True)
  field: str                                     # Name of the discovered field
  value: Any = None                              # Discovered value
  source_step_id: str = ""                       # Which step produced this discovery
```

Discoveries come from `CapabilityResult.data["discoveries"]` -- a convention where
capabilities can report new information found during execution (e.g., a search step
discovers that the user's preferred restaurant is closed, triggering replan of the
booking step).

**failure_context: Optional[FailureContext]**

Present when the micro-replan was triggered by a step failure (not just a discovery):

```yaml
FailureContext:                                  # @dataclass(frozen=True)
  step_id: str                                   # Which step failed
  error_code: str                                # Error classification
  error_message: str                             # Human-readable error
  partial_result: Optional[Dict[str, Any]]       # Any partial output before failure
```

#### 10.2.2 Overlap Heuristic (Trigger Condition)

MicroReplanCheckpoint uses a parameter overlap heuristic to decide whether discoveries
warrant a replan. The heuristic (V1, per ADR-1.1.11 Q8):

```text
 For each discovery in wave_result:
   For each step in remaining_steps:
     For each param_name in step.params:
       IF discovery.field == param_name (exact, case-insensitive)
       OR discovery.field IN param_name (substring)
       OR param_name IN discovery.field (substring):
         -> OVERLAP DETECTED -> trigger micro-replan
```

**Example**: Step s1 (restaurant search) discovers `{"field": "restaurant_closed",
"value": true}`. Remaining step s3 has `params: {"restaurant_name": "Luigi's"}`.
Substring match: "restaurant" appears in both "restaurant_closed" and
"restaurant_name" -> overlap -> trigger replan.

**Performance**: O(D \* S \* P) where D = discovery count, S = remaining step count,
P = avg params per step. For typical plans: <1ms (ORCH-13 target: <1ms P99).

### 10.3 Abbreviated Pipeline (3 Micro-Stages + COMMIT)

The micro-replan pipeline is an abbreviated version of the full pipeline. It runs the
same 4 stages but with reduced budgets, no HIL interactions, and scoped to replacement
steps only.

#### 10.3.1 Pipeline Comparison

| Dimension | Full Pipeline | Micro-Replan Pipeline |
| --------- | ------------- | --------------------- |
| Stages | SKETCH -> EXPAND -> VALIDATE -> COMMIT | MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE -> COMMIT |
| Total timeout | 45s | 10s (synchronous) |
| Token budget | ~3.5K | ~2K |
| Tool calls | Up to 6 (PLAN-05) | Up to 3 (reduced budget) |
| HIL interactions | Clarification + Approval | NONE (no time for user interaction) |
| Scope | Full plan from intent | Replacement steps only |
| Input | PlanRequest (intent, constraints, context) | MicroReplanRequest (completed, remaining, discoveries, failure) |
| Output | Full CommittedPlan (all steps) | Partial CommittedPlan (replacement steps only) |
| Delivery | Event bus (`k1.planner.plan.ready.v1`) | Synchronous return |

#### 10.3.2 Micro-SKETCH

**Purpose**: Re-plan the remaining steps given the current execution state.

**Budget**: `{max_tokens: 1024, timeout_ms: 5000}`

**Slot-based prompt** (same architecture as Section 6.3.1):

```text
 SYSTEM SEGMENT
   Slot: ROLE_DEFINITION       -- Micro-replan task (re-plan remaining portion)
   Slot: OUTPUT_SCHEMA          -- JSON Schema for MicroSketchResult

 USER SEGMENT
   Slot: ORIGINAL_INTENT        -- Source: PlanRequest.intent (from original plan)
   Slot: COMPLETED_SUMMARY      -- Source: MicroReplanRequest.completed_results
                                   Rendered as: step_id, capability, status, key outputs
   Slot: REMAINING_STEPS        -- Source: MicroReplanRequest.remaining_steps
                                   The steps that need replacement or modification
   Slot: DISCOVERIES            -- Source: MicroReplanRequest.discoveries
                                   New information that invalidates remaining steps
   Slot: FAILURE_CONTEXT        -- Source: MicroReplanRequest.failure_context (if present)
                                   What failed and why
```

**Key difference from full SKETCH**: No `query_planning_context()` or
`recall_for_planning()` tool calls. The completed_results provide sufficient context.
One `discover_capabilities()` call may be made if the LLM determines new capabilities
are needed for the replacement steps.

**Output contract** (JSON Schema):

```json
{
  "type": "object",
  "required": ["replacement_steps", "reasoning"],
  "properties": {
    "replacement_steps": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "description", "capability_hint"],
        "properties": {
          "id": {"type": "string"},
          "description": {"type": "string"},
          "capability_hint": {"type": "string"}
        }
      },
      "description": "Rough replacement steps (same format as SketchResult.rough_steps)"
    },
    "reasoning": {
      "type": "string",
      "description": "Why the remaining steps need replacement"
    },
    "reuse_steps": {
      "type": "array",
      "items": {"type": "string"},
      "description": "IDs of remaining_steps that can be kept as-is (no change needed)"
    }
  }
}
```

The `reuse_steps` field allows the LLM to indicate which of the remaining steps are
still valid. Only truly affected steps get replaced, minimizing plan disruption.

#### 10.3.3 Micro-EXPAND

**Purpose**: Map replacement steps to concrete capabilities with full parameterization.

**Budget**: `{max_tokens: 512, timeout_ms: 3000}`

**Slot-based prompt**: Same architecture as Section 7.3.1, but the USER SEGMENT includes:

| Slot | Source | Difference from Full EXPAND |
| ---- | ------ | --------------------------- |
| SKETCH_PLAN | MicroSketchResult.replacement_steps | Only replacement steps, not full plan |
| COMPLETED_CONTEXT | completed_results | Available outputs from completed steps for param binding |
| CAPABILITY_SET | Cached from full plan or 1 new discovery call | Reduced discovery budget |
| DEPENDENCY_RULES | Must reference completed step IDs | Deps may reference completed steps (cross-boundary) |

**Output**: Same ExpandedPlan structure as full EXPAND (List[PlanStep] with all 14 fields),
but containing only the replacement steps.

**Cross-boundary dependencies**: Replacement steps CAN depend on completed steps
(referencing their results). Example: `"deps": ["s1"]` where s1 is already completed.
The Orchestrator resolves these references from `completed_results` when merging.

#### 10.3.4 Micro-VALIDATE

**Purpose**: Validate the replacement steps structurally and semantically.

**Budget**: `{max_tokens: 256, timeout_ms: 2000}` (tightest of all stages)

**Deterministic checks**: Same as full VALIDATE (Section 8.2):

- DAG cycle detection on replacement steps + dependency references to completed steps
- Capability existence check for all replacement step capabilities

**LLM arbiter**: Same verdict structure (`approved | revise | reject`) but:

- No revise loop (time budget too tight within 10s total -- one shot)
- Verdict "revise" treated as "approved" (best-effort, micro-replan is already fallback)
- Verdict "reject" -> micro-replan fails, return None to Orchestrator

**NO HIL approval**: Micro-replan operates under time pressure. If the original plan
had HIL approval, the replacement steps inherit that approval implicitly (they serve
the same intent, already approved by the user).

#### 10.3.5 COMMIT

Same CommitService as full pipeline (Section 9). Produces a CommittedPlan with:

- New `plan_id` (fresh uuid4, distinct from `original_plan_id`)
- `request_id` matching the MicroReplanRequest's `request_id`
- Only replacement steps in `steps` field
- Dependencies may reference completed step IDs (cross-boundary)

The CommittedPlan is returned synchronously to the caller (no event bus delivery).
Additionally, `k1.planner.micro_replan.ready.v1` is emitted as TELEMETRY-ONLY for
Learning Loop observability.

#### 10.3.6 Timing Budget Breakdown

```text
 Total budget: 10s (synchronous timeout)

 Micro-SKETCH:    ~5s  (max_tokens: 1024, timeout_ms: 5000)
 Micro-EXPAND:    ~3s  (max_tokens: 512,  timeout_ms: 3000)
 Micro-VALIDATE:  ~2s  (max_tokens: 256,  timeout_ms: 2000)
 COMMIT:          <0.1s
 ─────────────────────
 Theoretical max: ~10.1s (barely fits within 10s budget)
 Practical p50:   ~8s
 Practical p99:   ~15s (may exceed budget -> timeout -> graceful fallback)
```

**Note**: The 10s budget is tight. If any stage runs slow, the entire micro-replan
times out and the Orchestrator continues with the original plan. This is by design --
micro-replan is best-effort, never blocking.

### 10.4 Output: Partial CommittedPlan

The micro-replan output is a CommittedPlan that contains ONLY the replacement steps.
The Orchestrator is responsible for merging.

#### 10.4.1 Merge Protocol (Orchestrator Side)

```text
 DAGExecutor receives GuardDecision with metadata["new_plan"]:
   |
   |-- new_plan: CommittedPlan (replacement steps only)
   |
   |-- Merge logic:
   |     1. Keep all completed_results (FROZEN, PLAN-12)
   |     2. Discard original remaining_steps
   |     3. Insert new_plan.steps as replacement
   |     4. Rebuild wave schedule from new_plan.dependencies
   |        (may reference completed step IDs for cross-boundary deps)
   |     5. Resume DAG execution from next wave
   |
   |-- Key property: Completed steps are NEVER modified or re-executed.
         The partial CommittedPlan only describes the future.
```

#### 10.4.2 CommittedPlan Structure (Micro-Replan)

```yaml
CommittedPlan:
  plan_id: "<new uuid4>"                         # Fresh ID (NOT original_plan_id)
  request_id: "<MicroReplanRequest.request_id>"  # Correlates to this micro-replan
  intent: "<original PlanRequest.intent>"        # Echoed from original plan context
  steps:                                         # ONLY replacement steps
    - id: "s3_replacement"
      capability: "tool.execute.alternative_restaurant_booking"
      params: {restaurant_name: "Marco's", party_size: 8}
      deps: ["s1"]                               # Cross-boundary: depends on completed step
      has_side_effects: true
      safety_band_min: "AMBER"
      # ... remaining 14 PlanStep fields
  dependencies:
    "s3_replacement": ["s1"]                     # s1 is completed (cross-boundary ref)
  trace_id: "<MicroReplanRequest.trace_id>"
  created_at: <epoch seconds>
```

### 10.5 Guard Rails

#### 10.5.1 Invariant: PLAN-12 (Completed Steps Frozen)

**PLAN-12**: Micro-replan adjusts remaining steps only. Completed steps are FROZEN.

Enforcement points:

| Layer | How Enforced |
| ----- | ------------ |
| MicroReplanCheckpoint | Only passes `remaining_steps` (unexecuted) to Planner |
| MicroReplanRequest | `remaining_steps` field contains only uncompleted steps |
| Planner Micro-SKETCH | Prompt instructs: "Do NOT modify or reference completed steps as replaceable" |
| DAGExecutor merge | Only replaces future waves; completed results are immutable |

#### 10.5.2 Max Replans per DAG

```text
 V1: max_replans = 1 (MicroReplanCheckpoint._max_replans default)

 MicroReplanCheckpoint tracks _replans_used (reset per DAG via reset()).
 After 1 successful micro-replan, all subsequent discoveries are logged
 but do not trigger additional replans.

 V2: Configurable max_replans (constructor parameter). Already supported
 in implementation but default is 1 for V1 safety.
```

#### 10.5.3 Timeout and Graceful Fallback

```text
 Micro-replan timeout: 10s (hardcoded in PlannerAdapter and MicroReplanCheckpoint)

 On timeout:
   MicroReplanCheckpoint returns GuardDecision(action=CONTINUE,
     reason="Planner micro_replan timed out after 10.0s")
   DAGExecutor continues with original remaining steps.
   No error propagation. No plan failure. Log warning only.

 On Planner returns None:
   Same CONTINUE behavior. Planner may return None if it determines
   remaining steps are still valid and no replacement is needed.

 On Planner error (exception):
   MicroReplanCheckpoint catches, logs warning, returns CONTINUE.
   Original plan continues. CB_PLANNER may trip on accumulated failures.
```

#### 10.5.4 No HIL in Micro-Replan

Micro-replan NEVER triggers HIL interactions (clarification or approval):

- **Time budget**: 10s total is insufficient for user round-trips (clarification: 60s,
  approval: 120s).
- **Implicit approval**: The original plan already received HIL approval (if required).
  Replacement steps serve the same intent and inherit that approval.
- **Scope limitation**: Micro-replan replaces a subset of steps, not the entire plan.
  The user already approved the overall approach.

#### 10.5.5 Token Budget

```text
 Micro-replan token budget: ~2K total

 Micro-SKETCH:   ~1024 tokens (max_tokens in HubRequest)
 Micro-EXPAND:   ~512 tokens
 Micro-VALIDATE: ~256 tokens
 COMMIT:         0 tokens
 ─────────────────────
 Total:          ~1.8K tokens (within ~2K budget)
```

Per-stage LLM calls use the same HubRequest construction pattern as the full pipeline:
`{capability: CHAT | STRUCTURED, constraints: {max_tokens, timeout_ms, consumer_id: "planner"}}`.
PLAN-11 (budget on every LLM call) is enforced.

### 10.6 Error Recovery

Micro-replan has the simplest error recovery of all pipeline modes because it is
inherently best-effort with a built-in fallback (continue original plan).

#### 10.6.1 Failure Scenarios

| Failure | Cause | Recovery |
| ------- | ----- | -------- |
| Planner timeout (10s) | Slow LLM, overloaded Planner | Continue original plan |
| Planner returns None | Planner decides replan unnecessary | Continue original plan |
| Planner exception | Internal error, port failure | Continue original plan, log warning |
| CB_PLANNER OPEN | Planner circuit breaker tripped | PlannerAdapter raises, checkpoint catches, continue |
| Micro-VALIDATE rejects | Replacement plan is invalid | Return None to Orchestrator, continue original |
| Micro-SKETCH/EXPAND LLM error | Provider down | No retry within micro-replan (time budget too tight), return None |

#### 10.6.2 No Revise Loop

Unlike the full pipeline (Section 8.5), micro-replan has NO revise loop:

- Verdict "revise" -> treated as "approved" (best-effort)
- Verdict "reject" -> return None (continue original plan)
- No retry of any micro-stage (single attempt per stage)

This is a deliberate simplification: the 10s budget leaves no room for retry cycles.

#### 10.6.3 Stage Delta

On micro-replan completion, PipelineController emits:

```yaml
k1.planner.delta.v1:
  type: "micro_replan_complete"
  original_plan_id: "<MicroReplanRequest.original_plan_id>"
  new_plan_id: "<new CommittedPlan.plan_id>"       # null if micro-replan failed
  status: "completed" | "failed" | "timeout"
  tokens_used: <total across all micro-stages>
  duration_ms: <micro-replan wall time>
  replacement_step_count: <number of new steps>
  trigger: "discovery" | "failure"                  # What triggered the micro-replan
  discoveries_count: <number of discoveries>
```

Additionally, the TELEMETRY-ONLY event:

```yaml
k1.planner.micro_replan.ready.v1:
  original_plan_id: str
  new_plan_id: str
  replacement_steps: List[PlanStep]                # Serialized via to_dict()
  trigger: str
  trace_id: str
```

This event is consumed by the Learning Loop for quality tracking and drift detection.
The Orchestrator does NOT subscribe to this event.

---

## 11. Discovery Tools -- Deep Dive

The Planner owns 4 read-only discovery tools, all routed through a single
`ToolCallRouter` service.  Three invariants govern every call:

| Invariant | Rule | Enforced By |
| --------- | ---- | ----------- |
| **PLAN-02** | ALL 4 tools are read-only -- zero side effects | ToolCallRouter (no action tools registered) |
| **PLAN-05** | Max 6 discovery tool calls per plan (3 SKETCH + 3 EXPAND) | ToolCallRouter.tool\_call\_count counter |
| **PLAN-06** | Planner never executes capabilities -- discovery only | ToolCallRouter (no execute path exists) |

The ToolCallRouter maintains a monotonic counter (`tool_call_count`) that increments
on every dispatched call and resets at `LC_PLAN_START`.  If a caller attempts a 7th
call, the router returns an immediate error without contacting any backend.

```text
 ToolCallRouter service (from planner.mmd):
   Routes to 3 hexagonal ports:
     PORT_FABRIC_RETRIEVAL  (discover_capabilities, find_relevant_prompts)
     PORT_STATE_READ        (query_planning_context)
     PORT_BRIDGE            (recall_for_planning)
   Enforces: PLAN-05 (counter), PLAN-06 (no execute route)
   Tests: ~35 planned
```

The following subsections document each tool's full contract: backend signature,
pipeline internals, return types, latency targets, and how each stage consumes the
results.

### 11.1 `discover_capabilities(domain?, intent?)`

**Route**: `ToolCallRouter` -> `IFabricRetrievalPort` -> `FabricRetrievalAdapter`
-> `RetrievalEngine.discover_capabilities()` (in-process, NOT HTTP)

**Source**: `k1/fabric/retrieval/retrieval_engine.py`

#### 11.1.1 Backend Signature

```python
def discover_capabilities(
    self,
    domain: Optional[List[str]] = None,       # Domain tag filter (e.g. ["cooking", "scheduling"])
    intent: str = "",                          # Natural-language capability description
    safety_band: str = "GREEN",                # Caller's current safety band
    session_context: Optional[Dict[str, Any]] = None,  # Available session keys for input satisfiability
    top_k: Optional[int] = None,               # Results cap (default: 10, max: 25)
) -> RetrievalResult
```

All parameters are optional.  At minimum, the Planner passes `intent` (derived from
`PlanRequest.intent` in SKETCH or from `RoughStep.suggested_capability` in EXPAND).
The `safety_band` comes from `PlanRequest.context.safety_band` (or the SessionState
`control` section).  The `session_context` dictionary carries available parameter
names so the HardFilter can evaluate input satisfiability.

#### 11.1.2 4-Step Retrieval Pipeline

The `RetrievalEngine._run_pipeline()` orchestrates 4 stateless stages.  Every stage
is a separate class with its own frozen-dataclass I/O types:

```text
 Step 0: GATHER
   Input:  domain tags (optional)
   Action: If domain provided -> IRegistryPort.list_by_domain(domain) -> O(1) indexed lookup
           If no domain      -> IRegistryPort.list_all() -> full scan
   Output: List[CapabilityContract] -- raw candidate set

 Step 1: EMBED
   Input:  intent string
   Action: IEmbeddingPort.embed(intent) -> np.ndarray (float32, dim=384)
   Model:  ultrabert-v4.0.0 (from RetrievalEngineConfig.embedding_model)
   Output: query_vector -- 1-D embedding

 Step 2: HARD FILTER  (k1/fabric/retrieval/hard_filter.py)
   Input:  List[FilterCandidate] built from contracts + query_vector + user_band
   Action: 3 elimination rules (short-circuit on first failure):
     Rule 1 -- Safety Band:   contract.safety_band_min <= user_band
               (band order: GREEN=0 < AMBER=1 < RED=2 < CRISIS=3)
     Rule 2 -- Availability:  contract.availability != OFFLINE
               (DEGRADED kept; penalized later by SoftRanker)
     Rule 3 -- Input Satisfiability:
               fraction of contract.required_inputs satisfiable from
               (available_param_names UNION session_keys) >= 0.5
               planner_can_ask=True relaxes this (Planner may request data)
   Config:  HardFilterConfig {
              satisfiability_threshold: 0.5,   # "most" = > 50%
              planner_can_ask: true,            # relaxed mode
              check_safety: true,
              check_availability: true,
              check_inputs: true
            }
   Output: List[FilterResult] -- each carries passed/rejected + rejection_reason
   Types:
     FilterCandidate { contract_name, safety_band_min, availability,
                       required_input_names: FrozenSet[str], contract }
     FilterResult    { contract_name, passed: bool, rejection_reason, contract }

 Step 3: SOFT RANKER  (k1/fabric/retrieval/soft_ranker.py)
   Input:  List[RankerCandidate] built from surviving contracts + query_vector
   Action: 4-dimension weighted composite score:
     Score = (0.40 * semantic_similarity)    -- cosine(query_vector, capability_vector)
           + (0.30 * domain_match)           -- Jaccard(query_domains, capability.domain)
           + (0.15 * success_rate)           -- contract.success_rate_30d (default 0.5)
           + (0.15 * cost_latency_score)     -- 1.0 - normalize(cost + latency/10000)
   Post-scoring penalty:  DEGRADED availability -> score *= 0.70
   Output: List[RankedResult] sorted descending by score
   Types:
     RankerCandidate { contract_name, capability_vector, domains: FrozenSet[str],
                       success_rate_30d, cost_per_call, avg_latency_ms,
                       availability, contract }
     RankedResult    { contract_name, score, semantic_similarity, domain_match,
                       success_rate, cost_latency_score,
                       degraded_penalty_applied: bool, contract }

 Step 4: TOP-K SELECTOR  (k1/fabric/retrieval/top_k_selector.py)
   Input:  List[RankedResult] (pre-sorted)
   Action: Clamp K to [1, max_k=25], then slice top K
   Config: TopKSelectorConfig { default_k: 10, max_k: 25 }
   Output: List[SelectedCapability] (length = min(K, survivors))
   Types:
     SelectedCapability { contract_name, score, provider_type, contract }
```

**Embedding Index** (`k1/fabric/retrieval/embedding_index.py`):
The FAISS-backed vector index provides the `capability_vector` used by SoftRanker.
Text indexed per contract: `f"{contract.description} | {' '.join(contract.capabilities)}"`.

- Index strategy: `IndexFlatL2` for <= 10,000 contracts (exact search),
  `IndexIVFFlat` for > 10,000 contracts (approximate, nlist=100, nprobe=10).
- Thread safety: RLock-guarded mutations; reads snapshot the index reference.
- Dimension: 384 (MiniLM-L6 / ultrabert-v4.0.0 output size).

#### 11.1.3 Return Type

```text
RetrievalResult (frozen dataclass, from k1/fabric/types.py):
  capabilities: List[ScoredCapability]   -- Top-K results, descending by score
  total_matched: int                     -- Total after hard filter (>= len(capabilities))
  query_latency_ms: int                  -- End-to-end retrieval time
  query_intent: str                      -- Echo of input intent
  index_size: int                        -- Total capabilities in index
  embedding_model: str                   -- "ultrabert-v4.0.0"

ScoredCapability (frozen dataclass):
  contract: Optional[CapabilityContract] -- Full capability snapshot
  score: float                           -- Composite score [0.0, 1.0]
```

Each `CapabilityContract` carries ~30 fields.  The subset relevant to planning:

```text
CapabilityContract (frozen dataclass, from k1/fabric/types.py):
  name: str                     -- e.g. "tool.execute.restaurant_booking"
  version: str                  -- semver (e.g. "1.2.0")
  domain: List[str]             -- ["dining", "scheduling"]
  description: str              -- Human-readable purpose
  capabilities: List[str]       -- What it can do
  limitations: List[str]        -- What it cannot do
  required_inputs: List[InputSpec]   -- Parameter specs (see below)
  optional_inputs: List[InputSpec]   -- Optional parameter specs
  required_context: List[str]        -- SessionState sections needed at execution time
  optional_context: List[str]        -- SessionState sections optionally used
  output: Dict[str, Any]             -- JSON Schema fragment for the output
  provider_type: str            -- "tool" | "agent" | "prompt" | "bridge" | ...
  provider_id: str              -- Provider registration identifier
  provider_endpoint: str        -- Execution endpoint (Planner never calls this -- PLAN-06)
  safety_band_min: str          -- Minimum safety band (GREEN / AMBER / RED / CRISIS)
  cost_per_call: float          -- Estimated dollar cost
  avg_latency_ms: int           -- Expected latency
  max_latency_ms: int           -- Worst-case latency
  availability: str             -- ONLINE / DEGRADED / OFFLINE
  success_rate_30d: float       -- Rolling 30-day success rate
  total_invocations_30d: int    -- Usage count for confidence scoring
  ephemeral: bool               -- True if capability is session-scoped
  session_scoped: bool          -- True if registered for this session only

InputSpec (frozen dataclass):
  name: str                     -- Parameter name (e.g. "restaurant_name")
  type: str                     -- JSON-compatible type (e.g. "string", "integer")
  description: str              -- Purpose description
  enum: Optional[List[str]]     -- Allowed values (if constrained)
  default: Optional[Any]        -- Default value (if any)
```

#### 11.1.4 What Each Stage Extracts

**SKETCH** (Section 6.2.1) uses `discover_capabilities` for **broad intent matching**:

- `top_k = 10` (default, wide net)
- Extracts: capability names, descriptions, input schemas, and domains
- Purpose: builds the "available tools menu" presented to the LLM in the SKETCH prompt
- The LLM references real capabilities when generating `RoughStep.suggested_capability`

**EXPAND** (Section 7.2.1) uses `discover_capabilities` for **targeted per-step resolution**:

- `top_k = 3-5` (narrow, one step at a time)
- `intent` is the specific step description rather than the plan-level intent
- Extracts: full `CapabilityContract` -- `required_inputs[]` populates `PlanStep.params`,
  `output` schema populates `PlanStep.output_schema`, `required_context[]` populates
  `PlanStep.required_context`, `avg_latency_ms` seeds `PlanStep.timeout_ms`,
  capability metadata determines `PlanStep.has_side_effects` and `PlanStep.compensation`
- Purpose: schema-resolve each step to a concrete, parameterized `PlanStep`

#### 11.1.5 Meta-Agent Discovery (4.5.1-4.5.4)

When a SKETCH `RoughStep` has `suggested_capability` matching `"agent.execute.*"`, the
EXPAND stage uses the same `discover_capabilities` call to find agent-type capabilities
but additionally uses the result to populate the `AgentSpec` embedded in `PlanStep.params`:

```text
 Discovery feeds AgentSpec construction:
   1. discover_capabilities(intent="<agent purpose>") -> agent-type contracts
   2. discover_capabilities(intent="<tools the agent needs>") -> tool contracts
      -> Populates AgentSpec.tools_granted[]
   3. find_relevant_prompts(intent="<agent behavior>") -> prompt contracts
      -> Populates AgentSpec.prompt_template
   4. query_planning_context(sections=["beliefs_active"]) -> session data
      -> Populates AgentSpec.seed_context

 The Planner outputs build_agent as a DAG step (PLAN-06: Planner NEVER
 executes -- Orchestrator runs build_agent at execution time).
```

This 3-tool sequence (discover + discover + find_prompts) is the canonical
meta-agent creation workflow.  It consumes 3 of the 6 available tool calls,
so when meta-agent discovery occurs in EXPAND, the SKETCH stage should have
conserved calls or the ToolCallRouter will reject the 7th attempt.

#### 11.1.6 Performance Targets

| Metric | Target | Source |
| ------ | ------ | ------ |
| End-to-end latency (10K caps) | <20ms | RetrievalEngine benchmark |
| End-to-end latency (100K caps) | <50ms | RetrievalEngine benchmark |
| FAISS search (flat, 10K) | <5ms | EmbeddingIndex spec |
| FAISS search (IVF, 100K) | <15ms | EmbeddingIndex spec |
| ToolCallRouter overhead | <1ms | In-process dispatch |
| FabricRetrievalAdapter timeout | 50ms | Adapter config (1 retry) |

### 11.2 `find_relevant_prompts(intent?, domain?)`

**Route**: `ToolCallRouter` -> `IFabricRetrievalPort` -> `FabricRetrievalAdapter`
-> `RetrievalEngine.find_relevant_prompts()` (in-process)

**Source**: `k1/fabric/retrieval/retrieval_engine.py`

#### 11.2.1 Backend Signature

```python
def find_relevant_prompts(
    self,
    intent: str = "",                          # Plan-level or step-level intent
    domain: Optional[List[str]] = None,        # Inferred from SKETCH step domains
    safety_band: str = "GREEN",                # Caller's safety band
    top_k: Optional[int] = None,               # Results cap (default: 10, max: 25)
) -> RetrievalResult
```

This method runs the identical 4-step pipeline as `discover_capabilities` (Section
11.1.2) with one critical difference: Step 0 (GATHER) pre-filters the candidate set
to **prompt-type contracts only**.  The filter logic is:

```text
 Pre-filter criteria (applied in _run_pipeline):
   contract.provider_type starts with "prompt"
   OR contract.name starts with "prompt."
```

After this pre-filter, Steps 1-4 (EMBED, HARD FILTER, SOFT RANK, TOP-K SELECT)
execute identically.

#### 11.2.2 Return Type

Same `RetrievalResult` as Section 11.1.3.  Each `ScoredCapability.contract`
is guaranteed to be a prompt-type `CapabilityContract`.  The fields most relevant
to the Planner:

```text
 contract.name             -- Prompt template identifier (e.g. "prompt.invitation_drafter_v1")
 contract.description      -- What the prompt does
 contract.required_inputs  -- Variable slots in the template (List[InputSpec])
 contract.optional_inputs  -- Optional variable slots
 contract.domain           -- Domain tag alignment
 contract.output           -- JSON Schema: expected output format when template is executed
```

#### 11.2.3 Caller Context

Only **EXPAND** (Section 7.2.2) calls `find_relevant_prompts`.  SKETCH does not.

| Aspect | Value |
| ------ | ----- |
| Caller stage | Stage 2 EXPAND |
| Purpose | Find prompt templates for agent-type steps |
| Query basis | Plan-level intent or per-step agent intent |
| Typical top\_k | 3-5 (narrow, targeted) |
| Budget slot | 5th of 6 calls (PLAN-05) |

**What EXPAND uses from the result**: Prompt template names and their variable slot
definitions (`required_inputs[]`).  These populate `PlanStep.params.prompt_template`
for agent steps.  The LLM in the EXPAND prompt can reference actual prompt template
names and knows their variable requirements, enabling correct parameterization.

#### 11.2.4 Relationship to Meta-Agent Discovery

When the EXPAND LLM maps a step to `capability: "agent.execute.*"`, it builds an
`AgentSpec` that includes a `prompt_template` field.  The `find_relevant_prompts`
results provide the LLM with actual template options:

```text
 EXPAND prompt receives (as a data slot):
   PROMPT_TEMPLATES: [
     { name: "prompt.invitation_drafter_v1", domain: ["events"],
       required_inputs: [{name: "guest_list", type: "array"}, ...] },
     { name: "prompt.task_coordinator_v2", domain: ["scheduling"],
       required_inputs: [{name: "task_list", type: "array"}, ...] },
   ]

 LLM selects best match and outputs in PlanStep.params:
   { "prompt_template": "prompt.invitation_drafter_v1", ... }
```

The Planner never instantiates the template -- PLAN-06 ensures the Orchestrator
does that at execution time.

### 11.3 `query_planning_context(sections?)`

**Route**: `ToolCallRouter` -> `IStateReadPort` -> `SessionStateReadAdapter`
-> SessionState (multi-reader, lock-free -- PLAN-01)

**Source**: `k1/fabric/ports/state_reader.py`

#### 11.3.1 Backend Signature

```python
# ISessionStateReader protocol (from k1/fabric/ports/state_reader.py):

async def read_sections(
    self,
    session_id: str,              # From PlanRequest.context.session_id
    names: List[str],             # e.g. ["beliefs_active", "persona", "temporal", "control"]
) -> Dict[str, Any]               # Section name -> section data (missing sections omitted)

async def get_snapshot(
    self,
    session_id: str,
) -> SessionSnapshot              # All sections at capture time
```

The ToolCallRouter translates the abstract `query_planning_context(sections?)` call
into a `read_sections()` call when specific sections are requested, or a `get_snapshot()`
call when the caller needs all available context.

#### 11.3.2 SessionSnapshot Type

```text
SessionSnapshot (frozen dataclass, from k1/fabric/ports/state_reader.py):
  session_id: str                         -- Active session identifier
  sections: Dict[str, Dict[str, Any]]     -- Section name -> section data
  timestamp_ms: int                       -- Capture timestamp (epoch ms)
  section_names: List[str]                -- Available section names at capture time
```

#### 11.3.3 Available Sections

The SessionState HOT tier exposes 6 section families.  The Planner typically reads
4 of them:

| Section | Contents | Planner Usage |
| ------- | -------- | ------------- |
| `beliefs_active` | Active beliefs: entities, relationships, facts | Ground plan in known world state (e.g., "8 family members") |
| `cognitive` | Cognitive state: attention focus, working memory | Rarely read by Planner; primarily Orchestrator context |
| `control` | Effective safety band, escalation state | Determines safety\_band for Fabric discovery calls |
| `affective_now` | Current emotional state | Rarely read by Planner; may influence prompt tone |
| `history_recent` | Recent interaction history | Cross-check with K0 recall results |
| `scoreboard` | Metrics and performance counters | Not used by Planner |

**Canonical SKETCH request**: `["beliefs_active", "control", "history_recent"]`
**Canonical EXPAND request**: typically none (uses SKETCH results passed through
`SketchResult`)

#### 11.3.4 Freshness Protocol

The `PlanRequest.context` snapshot (captured by the Orchestrator at dispatch time)
already contains a SessionState sample.  The `query_planning_context` call provides
a FRESH read that may contain updates since dispatch.  The SketchService uses a
freshness heuristic:

```text
 If PlanRequest.context.timestamp_ms is within 5000ms of now:
   MAY skip the fresh read and use PlanRequest.context directly
   (saves 1 tool call from the PLAN-05 budget)
 If PlanRequest.context.timestamp_ms is older than 5000ms:
   MUST issue fresh read via ToolCallRouter
   (context may have drifted during queue wait)

 The canonical path always issues the call for consistency.
 The skip optimization is a V2 enhancement.
```

#### 11.3.5 Thread Safety and PLAN-01

SessionState read access is multi-reader, lock-free.  The Planner NEVER writes
to SessionState (PLAN-01: no write ports to SessionState).  All planning outputs
are emitted as deltas through `IDeltaEmitPort` and published through `IEventPort`.
The Planner's read path cannot interfere with other readers (Orchestrator,
Supervision, Concierge).

#### 11.3.6 What Each Stage Extracts

**SKETCH**: Beliefs ground the plan in known entities and relationships (e.g.,
"Mom prefers Italian food", "8 family members", "nearest grocery is 2 miles away").
Control provides the effective safety band that gates all subsequent Fabric discovery
calls.  History gives recent interaction recency context.

**EXPAND**: Does not typically call `query_planning_context` -- it receives the
SKETCH context via `SketchResult`.  If it did call (from the remaining budget), it
would read the same sections for delta freshness.

**Latency target**: <10ms (in-process, lock-free read).

### 11.4 `recall_for_planning(query)`

**Route**: `ToolCallRouter` -> `IBridgePort` -> `BridgeAdapter` -> K0 Bridge -> K0 Memory

**Source**: `k1/fabric/ports/bridge_port.py`

#### 11.4.1 Backend Signature

The `IBridgePort` protocol does not expose a dedicated `recall_for_planning` method.
The ToolCallRouter translates the abstract tool call into the generic `query()` method
of `IBridgePort`:

```python
# IBridgePort protocol (from k1/fabric/ports/bridge_port.py):

async def query(
    self,
    operation: str,               # "memory.recall"
    selectors: Dict[str, Any],    # {"query": "<planning_recall_query>"}
    *,
    trace_id: str = "",           # Cognitive trace ID (FAB-09)
    timeout_ms: int = 0,          # Per-query timeout (0 = adapter default)
) -> BridgeCommandResult
```

The ToolCallRouter invokes:

```python
bridge_port.query(
    operation="memory.recall",
    selectors={"query": intent_text},
    trace_id=plan_request.trace_id,
    timeout_ms=100,               # 100ms budget for K0 recall
)
```

Where `intent_text` is derived from `PlanRequest.intent` (in SKETCH) or composed
from step-level context.

#### 11.4.2 Return Type

```text
BridgeCommandResult (frozen dataclass, from k1/fabric/ports/bridge_port.py):
  success: bool               -- True if K0 responded successfully
  data: Dict[str, Any]        -- Recall payload (see below)
  error_code: str             -- Machine-readable error (empty on success)
  error_message: str          -- Human-readable error (empty on success)
  k0_mode: str                -- "K0_FULL" | "K0_DEGRADED" | "K0_OFFLINE"
  latency_ms: int             -- Round-trip latency to K0
  trace_id: str               -- Echoed back for correlation
```

The `data` field on successful recall contains K0 memory signals:

```text
 data: {
   facts: List[Dict]           -- Known facts about entities (e.g., "Mom born 1965")
   prior_outcomes: List[Dict]  -- Historical plan execution results
   preferences: List[Dict]     -- User preference patterns (e.g., "prefers Italian food")
 }
```

Static factory methods:

- `BridgeCommandResult.ok(data, latency_ms, trace_id)` -- success path
- `BridgeCommandResult.fail(error_code, error_message, k0_mode, trace_id)` -- failure path

#### 11.4.3 K0 Health Awareness

The `IBridgePort` exposes two health methods the ToolCallRouter uses before
dispatching:

```python
def is_available(self) -> bool
    # True if K0 is reachable through the Bridge

def get_health(self) -> BridgeHealth
    # Returns BridgeHealth snapshot with mode:
    #   K0_FULL     -> normal execution
    #   K0_DEGRADED -> execute with extended timeout
    #   K0_OFFLINE  -> skip recall entirely
```

The ToolCallRouter checks `is_available()` before dispatching:

```text
 If is_available() == false:
   -> Return empty BridgeCommandResult.fail("k0_offline", ...) immediately
   -> Do NOT count against PLAN-05 budget (no actual call made)
   -> SKETCH proceeds without long-term memory (graceful degradation)

 If get_health().mode == K0_DEGRADED:
   -> Dispatch with extended timeout_ms (200ms instead of 100ms)
   -> Result may be partial (fewer facts, slower response)

 If get_health().mode == K0_FULL:
   -> Normal dispatch, timeout_ms=100
```

#### 11.4.4 Offline Graceful Degradation

When K0 is offline, the Planner produces a plan based ONLY on:

- Fabric-discovered capabilities (Section 11.1)
- SessionState context (Section 11.3)
- PlanRequest.intent and PlanRequest.context

The plan is functionally valid but potentially less personalized -- it lacks historical
preferences, prior outcomes, and long-term facts.  This is an acceptable degradation
because the Planner's primary function (capability discovery + DAG construction) does
not depend on K0 memory.  Personalization is additive, not structural.

#### 11.4.5 What SKETCH Extracts

Historical preferences inform the LLM to make contextually better choices:

```text
 From data.facts:
   "Mom born Feb 21" -> temporal grounding for birthday planning
   "8 family members" -> sizing context for party steps

 From data.prior_outcomes:
   "Last party at Olive Garden -- 4 stars" -> quality signal
   "Invitation emails failed 2/8 last time" -> reliability context

 From data.preferences:
   "Mom prefers Italian food" -> narrows restaurant discovery
   "Family prefers evening events" -> temporal constraint
```

The SketchService injects these into the LLM prompt as a `MEMORY_CONTEXT` data slot
alongside the Fabric capabilities and SessionState context.

#### 11.4.6 Caller Context

| Aspect | Value |
| ------ | ----- |
| Caller stage | Stage 1 SKETCH only |
| Purpose | Retrieve long-term memory for personalized planning |
| Query basis | PlanRequest.intent (natural language) |
| Typical timeout | 100ms (K0\_FULL), 200ms (K0\_DEGRADED) |
| Budget slot | 3rd of 6 calls (PLAN-05) |
| EXPAND usage | None -- uses SKETCH recall results passed through SketchResult |

**Latency target**: <100ms.

### 11.5 ToolCallRouter Service -- Internal Design

The `ToolCallRouter` is a thin dispatch layer with enforced invariants.  It is NOT
an LLM-mediated tool-use mechanism -- it is a deterministic, code-level router that
maps abstract tool names to port method calls.

#### 11.5.1 Routing Table

```text
 Tool Name                  | Port                   | Method Called
 -------------------------- | ---------------------- | --------------------------------
 discover_capabilities      | IFabricRetrievalPort   | discover_capabilities(query)
 find_relevant_prompts      | IFabricRetrievalPort   | find_relevant_prompts(query)
 query_planning_context     | IStateReadPort         | read_sections(session_id, names)
 recall_for_planning        | IBridgePort            | query("memory.recall", selectors)
```

All 4 routes are read-only.  No write, execute, or mutate path exists
in the routing table.

#### 11.5.2 Call Budget Enforcement (PLAN-05)

```text
 Dispatch algorithm:

   1. Caller invokes: router.call(tool_name, **params)
   2. Check: tool_call_count < 6
      - If false -> raise BudgetExhaustedError (log, trace, return error)
   3. Check: tool_name in ROUTING_TABLE
      - If false -> raise UnknownToolError
   4. Dispatch to port method (async)
   5. Increment: tool_call_count += 1
   6. Return result to caller

 Budget accounting per stage:
   SKETCH:  3 calls (discover_capabilities, query_planning_context, recall_for_planning)
   EXPAND:  2-3 calls (discover_capabilities refined, find_relevant_prompts, optional 3rd)
   VALIDATE: 0 calls (uses IFabricRetrievalPort directly for capability existence, not via router)
   COMMIT:   0 calls

 Counter lifecycle:
   Reset at LC_PLAN_START (start of new plan)
   Reset at LC_PLAN_START for micro-replan (resets to 0 for abbreviated pipeline)
   Never reset mid-pipeline
```

#### 11.5.3 Retry and Timeout Policy

```text
 Per-tool timeout and retry:

 | Tool                     | Timeout | Retries | Fallback on Failure          |
 | ------------------------ | ------- | ------- | ---------------------------- |
 | discover_capabilities    | 50ms    | 1       | Return empty RetrievalResult |
 | find_relevant_prompts    | 50ms    | 1       | Return empty RetrievalResult |
 | query_planning_context   | 10ms    | 0       | Use PlanRequest.context      |
 | recall_for_planning      | 100ms   | 0       | Return empty (degraded plan) |

 On retry:
   - ToolCallRouter does NOT double-count: retry uses the same call slot
   - Total wall time: timeout * (1 + retries)
   - If retry also fails: return empty result, log warning, SKETCH/EXPAND proceeds

 On all-tools-fail scenario:
   - SKETCH receives zero context enrichment
   - LLM generates plan from PlanRequest.intent alone
   - Plan is valid but minimal -- downstream stages may flag quality issues
```

#### 11.5.4 Concurrency Model

SKETCH issues its 3 tool calls concurrently (`asyncio.gather` or equivalent).
The ToolCallRouter is safe for concurrent dispatch -- the `tool_call_count` increment
uses an atomic counter or asyncio-safe pattern (single-threaded event loop guarantees
no interleaving within a coroutine boundary).

EXPAND issues its 2-3 calls concurrently within the same pattern.

```text
 SKETCH concurrent dispatch:
   results = await asyncio.gather(
       router.call("discover_capabilities", domain=..., intent=...),
       router.call("query_planning_context", sections=[...]),
       router.call("recall_for_planning", query=...),
   )
   # tool_call_count = 3 after gather completes

 EXPAND concurrent dispatch:
   results = await asyncio.gather(
       router.call("discover_capabilities", intent=step_intent),
       router.call("find_relevant_prompts", intent=agent_intent),
   )
   # tool_call_count = 5 after gather completes
```

### 11.6 Cross-Reference Summary

| Reference | Section | Relationship |
| --------- | ------- | ------------ |
| SKETCH tool calls | 6.2 | 3 calls: discover\_capabilities + query\_planning\_context + recall\_for\_planning |
| EXPAND tool calls | 7.2 | 2-3 calls: discover\_capabilities (refined) + find\_relevant\_prompts + (optional) |
| Meta-agent discovery | 7.5 | 3-call sequence across discover + discover + find\_prompts |
| Micro-replan tool calls | 10.3 | Abbreviated pipeline reuses ToolCallRouter with reset counter |
| PLAN-02 enforcement | 3 (invariants table) | ToolCallRouter has no action tools |
| PLAN-05 enforcement | 3 (invariants table) | ToolCallRouter counter, max 6 |
| PLAN-06 enforcement | 3 (invariants table) | No execute route in routing table |
| Fabric retrieval pipeline | -- (k1/fabric/retrieval/) | 4-step: Embed -> HardFilter -> SoftRanker -> TopKSelector |
| SessionState protocol | -- (k1/fabric/ports/state\_reader.py) | ISessionStateReader: read\_sections, get\_snapshot |
| Bridge protocol | -- (k1/fabric/ports/bridge\_port.py) | IBridgePort: query("memory.recall", selectors) |

---

## 12. HIL System (Human-in-the-Loop)

The Planner has exactly 2 HIL interaction points, each managed by the
`HILCoordinator` service (~35 planned tests).  These are **planning-time**
interactions -- the user is consulted BEFORE the plan is committed, not during
execution.  The single governing invariant:

| Invariant | Rule | Enforced By |
| --------- | ---- | ----------- |
| **PLAN-10** | HIL clarification max 2 rounds per plan, then best-effort | HILCoordinator round counter |

Both interaction points route through the same external path: Planner -> Event Bus ->
Concierge -> User -> Concierge -> Event Bus -> Planner.  The Concierge owns the
user-facing presentation; the Planner owns the decision logic.

### 12.1 HIL Namespace Split

The K1 HIL event namespace is divided into two distinct families with clear ownership.
This prevents cross-contamination between planning-time and execution-time user
interactions.

```text
 PLANNING-TIME (Planner owns -- this section):
   k1.hil.clarification.v1              -- Planner -> Concierge -> User
   k1.hil.clarification_response.v1     -- User -> Concierge -> Planner
   k1.hil.approval_request.v1           -- Planner -> Concierge -> User
   k1.hil.approval_response.v1          -- User -> Concierge -> Planner

 EXECUTION-TIME (Orchestrator owns -- distinct family, not covered here):
   k1.hil.override.v1                   -- Orchestrator -> Concierge -> User
   k1.hil.override_response.v1          -- User -> Concierge -> Orchestrator
   k1.hil.fallback.v1                   -- Orchestrator -> Concierge -> User
   k1.hil.fallback_response.v1          -- User -> Concierge -> Orchestrator
   k1.hil.progress.v1                   -- Orchestrator -> Concierge -> User (fire-and-forget)
```

**Routing independence**: Concierge routes both families to the user through the same
`IOutputPort`, but correlates them independently via the `PENDING_CLARIFICATIONS` map
(keyed by `{request_id, originator, agent_id?}`).  A planning-time clarification
and an execution-time fallback can coexist without interference.

**Port wiring** (from planner.mmd):

- `HILCoordinator` publishes outbound events via `IEventPort`
- `HILCoordinator` subscribes to inbound response events via `IEventPort`
- `HILCoordinator` generates LLM prompts for HIL messages via `ILLMPort`

```text
 SVC_HIL service (from planner.mmd):
   Manages clarification + approval flows
   LLM prompt generation for HIL messages
   Round counting (PLAN-10: max 2), timeout handling
   Subscribes to k1.hil.clarification_response.v1
   Subscribes to k1.hil.approval_response.v1
   Correlates responses via request_id
   Tests: ~35 planned
```

### 12.2 Requirement Clarification (Stage 1)

Clarification is the first HIL interaction point.  It occurs AFTER discovery tool
calls and BEFORE the main SKETCH LLM call (Section 6.3).  The purpose is to resolve
ambiguity in the user's intent before the LLM attempts plan generation.

#### 12.2.1 Trigger Conditions

SketchService triggers HIL clarification when any of the following are detected:

1. **Ambiguous intent**: The intent string is too vague to produce a meaningful plan
   (e.g., "help me with something" vs. "book a restaurant for 8 on Saturday").
2. **Missing constraints**: Required information is absent from both session context
   and K0 recall results (e.g., no date specified for a time-sensitive task, no
   budget for a cost-bearing operation).
3. **Conflicting signals**: Context and memory disagree (e.g., beliefs say mom prefers
   sushi but K0 recall says the last party was Italian -- which takes precedence?).

The ambiguity detection is performed either as a lightweight check embedded in the
main SKETCH prompt, or as a pre-check LLM call (~300 tokens, counted within the
2048-token SKETCH budget).

**Non-trigger conditions** (clarification is NOT requested):

- Intent is clear and constraints are complete
- All sessions where tool call results provide sufficient grounding
- Micro-replan requests (PLAN-12: micro-replan never triggers HIL)

#### 12.2.2 Clarification Flow

```text
 SketchService -> HILCoordinator.request_clarification(
     request_id=plan_request.request_id,
     question_context={intent, discovered_caps, session_context, recall_results}
   )

 HILCoordinator:
   1. GENERATE QUESTION via ILLMPort:
      HubRequest {
        capability: CHAT,
        constraints: {max_tokens: 300, timeout_ms: 3000, consumer_id: "planner"},
        trace_id: plan_request.trace_id
      }

      Prompt composition (slot-based -- Section 6.3 pattern):
        SYSTEM segment:
          Slot: ROLE_DEFINITION     -- "You are a family assistant asking a
                                        clarification question."
          Slot: OUTPUT_CONTRACT     -- "Respond with a single natural-language
                                        question. Keep it conversational and
                                        appropriate for a family context."
        USER segment:
          Slot: INTENT              -- PlanRequest.intent (str)
          Slot: KNOWN_CONTEXT       -- Summary of what Planner already knows
                                       (from session context + K0 recall)
          Slot: AMBIGUITY_SIGNAL    -- What specifically is unclear

      The LLM generates a natural-language question (~100-200 tokens typically).
      This 300-token budget is WITHIN the overall SKETCH stage allocation.

   2. EMIT EVENT via IEventPort:
      topic: "k1.hil.clarification.v1"
      payload: {
        request_id: plan_request.request_id,
        plan_id: null,                          # Not yet assigned (pre-COMMIT)
        question: "<LLM-generated question>",
        context_hint: "<what the Planner already knows>",
        round: 1,
        max_rounds: 2
      }

   3. CONCIERGE ROUTING:
      Event Bus -> Concierge receives k1.hil.clarification.v1
      Concierge stores entry in PENDING_CLARIFICATIONS:
        key: {request_id, originator: "planner"}
      Concierge renders question to user via IOutputPort -> active channel
      (SSE, WebSocket, or REST -- Concierge decides based on session state)

   4. WAIT for response:
      HILCoordinator subscribes to: "k1.hil.clarification_response.v1"
      Correlation: match by request_id
      Timeout: 60s per round

   5. ON RESPONSE (user replies):
      Concierge HIL Response Detector checks PENDING_CLARIFICATIONS:
        - Matches request_id -> routes as HIL response, NOT new turn
        - Clears matched entry from PENDING_CLARIFICATIONS
      Concierge emits: k1.hil.clarification_response.v1
      payload: {
        request_id: plan_request.request_id,
        plan_id: null,
        user_response: "<user's answer>",
        trace_id: plan_request.trace_id
      }
      HILCoordinator receives, returns response to SketchService.
      SketchService incorporates user answer into the main LLM prompt
      as the HIL_ADDENDUM slot (Section 6.3 prompt architecture).

   6. IF answer still insufficient AND round < 2 (PLAN-10):
      Repeat steps 1-5 with round=2 and a refined question
      incorporating the first response.

   7. IF timeout OR round == 2 reached:
      Proceed with best-effort interpretation.
      SketchService LLM call includes note in prompt:
        "(User clarification unavailable -- proceeding with
         best-effort interpretation based on available context)"
```

#### 12.2.3 Clarification Event Schema

**Outbound** (Planner -> Concierge, topic: `k1.hil.clarification.v1`):

```yaml
k1.hil.clarification.v1:
  request_id: uuid                     # Correlation key
  plan_id: null                        # Not yet assigned
  question: str                        # LLM-generated natural-language question
  context_hint: str                    # Summary of known context (for Concierge display)
  round: int                           # 1 or 2
  max_rounds: int                      # Always 2 (PLAN-10)
```

**Inbound** (Concierge -> Planner, topic: `k1.hil.clarification_response.v1`):

```yaml
k1.hil.clarification_response.v1:
  request_id: uuid                     # Correlates to original request
  plan_id: uuid | null                 # Echoed (null before COMMIT)
  user_response: str                   # User's answer text
  trace_id: str                        # Cognitive trace ID
```

#### 12.2.4 Round Budget and Timing

```text
 Round budget (PLAN-10):
   Max rounds: 2 per plan
   Timeout per round: 60s
   Maximum clarification wall time: 120s (2 rounds * 60s)
   LLM budget per question: 300 tokens, 3000ms

 Impact on PLAN-04 (45s total planning time):
   HIL wait time is EXCLUDED from the 45s planning budget.
   The 45s covers computational planning only (LLM + tool calls + assembly).
   CB_PLANNER timeout (owned by Orchestrator PlannerAdapter) accounts
   for HIL by extending the effective timeout when HIL is active.

 Counter lifecycle:
   HILCoordinator.round_count resets at LC_PLAN_START
   (same as ToolCallRouter.tool_call_count)
```

#### 12.2.5 How Clarification Feeds SKETCH

When a clarification response is received, SketchService injects the user's answer
into the main LLM prompt as the `HIL_ADDENDUM` slot (Section 6.3.1 prompt
architecture):

```text
 Prompt slot: HIL_ADDENDUM
   Source: HILCoordinator clarification response
   Required: No (only present if clarification occurred)
   Content: Raw user clarification text appended as additional context

 Example:
   [Before clarification]
   INTENT: "plan mom's birthday"
   -> Ambiguity: date unknown, budget unknown, indoor/outdoor unknown

   [After clarification, round 1]
   HIL_ADDENDUM: "Her birthday is Feb 21, budget around $500, she'd prefer
                   something at home with the family"
   -> SKETCH now has date, budget, venue, and guest constraints
```

If 2 rounds occurred, both responses are concatenated in the `HIL_ADDENDUM` slot.

### 12.3 Plan Approval (Stage 3)

Approval is the second HIL interaction point.  It occurs AFTER the LLM arbiter
returns an `approved` verdict in Stage 3 VALIDATE (Section 8.3) and BEFORE Stage 4
COMMIT.  The purpose is to get explicit user consent for high-impact plans.

#### 12.3.1 Trigger Conditions

ValidateService triggers HIL approval when ALL of the following are true:

1. **High-impact operations present**: At least one step has `has_side_effects: true`
   AND the side effect is external (booking, ordering, sending messages -- not
   internal reads or computations).
2. **Not auto-approvable**: The plan contains a step with `safety_band_min` higher
   than GREEN, OR the arbiter's `safety_assessment` is `"caution"`.
3. **LLM arbiter approved**: The plan must pass the LLM arbiter first.  If the arbiter
   returned `"revise"` or `"reject"`, HIL approval is not triggered (the plan goes
   back to EXPAND or FAILS).

**Auto-approve rule**: If ALL steps with `has_side_effects: true` have
`safety_band_min: "GREEN"` AND the arbiter's `safety_assessment: "safe"`,
ValidateService auto-approves without user interaction.  This covers the common
case of safe plans that don't need human oversight.

**Non-trigger conditions** (approval is NOT requested):

- All steps are read-only (`has_side_effects: false`)
- All side-effecting steps are GREEN and arbiter says "safe"
- Micro-replan requests (PLAN-12: micro-replan bypasses HIL entirely)

#### 12.3.2 Approval Flow

```text
 ValidateService -> HILCoordinator.request_approval(
     request_id=plan_request.request_id,
     expanded_plan=<current ExpandedPlan>,
     arbiter_verdict=<ValidationVerdict from Section 8.3>
   )

 HILCoordinator:
   1. GENERATE APPROVAL PRESENTATION via ILLMPort:
      HubRequest {
        capability: CHAT,
        constraints: {max_tokens: 400, timeout_ms: 3000, consumer_id: "planner"},
        trace_id: plan_request.trace_id
      }

      Prompt composition (slot-based):
        SYSTEM segment:
          Slot: ROLE_DEFINITION     -- "You are a family assistant presenting a
                                        plan for approval."
          Slot: OUTPUT_CONTRACT     -- "Summarize the plan in plain language.
                                        Highlight side effects, costs, and
                                        affected external systems. Present
                                        options: approve, modify, or reject."
        USER segment:
          Slot: PLAN_STEPS          -- Serialized step list with capability names,
                                       params, and dependency graph
          Slot: SIDE_EFFECTS        -- Steps with has_side_effects: true, extracted
                                       with capability description and impact
          Slot: SAFETY_ASSESSMENT   -- Arbiter safety_assessment field
          Slot: COST_ESTIMATE       -- Sum of step cost_per_call estimates

      The LLM generates a human-friendly plan summary (~200-300 tokens).
      This 400-token budget is WITHIN the overall VALIDATE stage allocation.

   2. EMIT EVENT via IEventPort:
      topic: "k1.hil.approval_request.v1"
      payload: {
        request_id: plan_request.request_id,
        plan_id: null,                          # Not yet assigned (pre-COMMIT)
        summary: "<LLM-formatted plan summary>",
        options: ["approve", "modify", "reject"],
        side_effects: [
          {step_id: "s1", capability: "tool.execute.restaurant_booking",
           description: "Books restaurant for 8 on Feb 21"},
          {step_id: "s4", capability: "tool.execute.cake_order",
           description: "Orders birthday cake -- $45 estimated"}
        ],
        safety_assessment: "<arbiter assessment>",
        estimated_duration_ms: <plan total estimate>
      }

   3. CONCIERGE ROUTING:
      Event Bus -> Concierge receives k1.hil.approval_request.v1
      Concierge stores entry in PENDING_CLARIFICATIONS:
        key: {request_id, originator: "planner"}
      Concierge renders summary + options to user via IOutputPort
      User sees: plan summary, side-effect list, approve/modify/reject buttons

   4. WAIT for response:
      HILCoordinator subscribes to: "k1.hil.approval_response.v1"
      Correlation: match by request_id
      Timeout: 120s (longer than clarification -- user needs time to review)

   5. ON RESPONSE:
      Concierge HIL Response Detector matches request_id in PENDING_CLARIFICATIONS
      Concierge emits: k1.hil.approval_response.v1
      HILCoordinator receives and returns to ValidateService
```

#### 12.3.3 Approval Event Schema

**Outbound** (Planner -> Concierge, topic: `k1.hil.approval_request.v1`):

```yaml
k1.hil.approval_request.v1:
  request_id: uuid                     # Correlation key
  plan_id: uuid | null                 # Not yet assigned
  summary: str                         # LLM-formatted plan summary
  options: List[str]                   # ["approve", "modify", "reject"]
  side_effects: List[Dict]            # Per-step side effect descriptions
  safety_assessment: str               # From arbiter verdict
  estimated_duration_ms: int           # Total plan duration estimate
```

**Inbound** (Concierge -> Planner, topic: `k1.hil.approval_response.v1`):

```yaml
k1.hil.approval_response.v1:
  request_id: uuid                     # Correlates to original request
  plan_id: uuid | null                 # Echoed (null before COMMIT)
  response_type: str                   # "approve" | "modify" | "reject"
  modifications: Dict | null          # User modifications (if response_type=modify)
  trace_id: str                        # Cognitive trace ID
```

#### 12.3.4 Response Routing

| Response Type | Action | Next Stage |
| ------------- | ------ | ---------- |
| `"approve"` | Proceed with plan as-is | COMMIT (Stage 4) |
| `"modify"` | Apply user modifications to ExpandedPlan, re-run deterministic checks (Section 8.2) | VALIDATE re-check, then COMMIT |
| `"reject"` | Emit `k1.planner.plan.failed.v1` with reason `"user_rejected"` | FSM -> FAILED |
| Timeout (120s) + all safe | Auto-approve (all steps GREEN + arbiter "safe") | COMMIT (Stage 4) |
| Timeout (120s) + any unsafe | Plan FAILED (unsafe steps without explicit approval) | FSM -> FAILED |

#### 12.3.5 Modification Handling

When the user responds with `"modify"`, the `modifications` dict contains field-level
overrides keyed by step ID:

```yaml
# Example: user changes party size and removes cake step
modifications:
  "s1":
    params:
      party_size: 10                   # User changed from 8 to 10
  "s4":
    remove: true                       # User removed the cake step entirely
```

ValidateService applies modifications to the ExpandedPlan:

```text
 Modification application protocol:
   1. For each step_id in modifications:
      a. If modifications[step_id].remove == true:
         -> Remove step from DAG
         -> Remove all dependency references to this step
         -> Descendant steps that ONLY depended on removed step get deps=[]
      b. Otherwise:
         -> Merge modifications[step_id].params into PlanStep.params
         -> Override any explicitly specified fields
   2. Re-run deterministic checks (Section 8.2):
      -> DAG cycle detection (removal may have broken the graph)
      -> Capability existence (modified params may invalidate a step)
   3. If deterministic checks pass -> COMMIT
   4. If deterministic checks fail -> Plan FAILED
      (no additional LLM arbiter call -- user's explicit approval supersedes)
```

### 12.4 Concierge Correlation: PENDING_CLARIFICATIONS

The Concierge maintains a `PENDING_CLARIFICATIONS` map that bridges the gap between
the Planner emitting an HIL event and the user responding.  This is the mechanism
that prevents user replies during active HIL from being treated as new conversation
turns.

#### 12.4.1 PENDING_CLARIFICATIONS Structure

```text
PENDING_CLARIFICATIONS (from concierge.mmd):
  Size: ~2KB in-memory map
  Keyed by: {request_id: uuid, originator: str, agent_id?: str}
  Written by: Concierge on receiving HIL events from DeltaBus or Event Bus
  Cleared on: User response matched by HIL Response Detector, or timeout
```

**Lifecycle**:

```text
 1. Planner emits k1.hil.clarification.v1 or k1.hil.approval_request.v1
 2. Event Bus delivers to Concierge
 3. Concierge writes entry to PENDING_CLARIFICATIONS:
      key: {request_id: "<uuid>", originator: "planner"}
 4. Concierge renders question/summary to user via IOutputPort
 5. User responds via IInputPort
 6. Concierge ACKING state -> HIL Response Detector intercepts:
      - Checks PENDING_CLARIFICATIONS for active HIL request
      - If match found: route as HIL response, NOT new conversation turn
      - Clear matched entry from PENDING_CLARIFICATIONS
 7. HIL Response Detector emits the appropriate response event:
      Planner clarification -> k1.hil.clarification_response.v1
      Planner approval     -> k1.hil.approval_response.v1
 8. Event Bus delivers response to Planner HILCoordinator
```

#### 12.4.2 Multi-Originator Support

The `PENDING_CLARIFICATIONS` map supports simultaneous HIL requests from multiple
originators:

| Originator | HIL Events (outbound) | Response Events (inbound) |
| ---------- | --------------------- | ------------------------- |
| Planner | `k1.hil.clarification.v1`, `k1.hil.approval_request.v1` | `k1.hil.clarification_response.v1`, `k1.hil.approval_response.v1` |
| Orchestrator | `k1.hil.fallback.v1`, `k1.hil.override.v1` | `k1.hil.fallback_response.v1`, `k1.hil.override_response.v1` |
| Sub-agents | Clarification request via DeltaBus delta | Clarification response routed back via DeltaBus with `agent_id` match |

The `originator` field ensures the response routes to the correct subscriber.
The `agent_id` field (optional) provides additional discrimination for sub-agent
HIL requests.

### 12.5 HILCoordinator Internal Design

#### 12.5.1 State Management

The HILCoordinator maintains per-plan state that is reset at `LC_PLAN_START`:

```text
 HILCoordinator state:
   round_count: int = 0            # Clarification rounds used (max 2, PLAN-10)
   pending_request_id: uuid | null # Currently active HIL request
   hil_type: str | null            # "clarification" | "approval"
   waiting: bool = false           # True while awaiting user response

 Reset at LC_PLAN_START:
   round_count = 0
   pending_request_id = null
   hil_type = null
   waiting = false
```

#### 12.5.2 Concurrency Contract

Only ONE HIL interaction can be active at a time within a single plan.  Clarification
(Stage 1) completes before SKETCH produces output.  Approval (Stage 3) completes before
COMMIT begins.  There is no overlap because the pipeline is sequential.

```text
 HIL timeline within a single plan:
   LC_PLAN_START
     |
     v
   SKETCH: [tools] -> [clarification?] -> [LLM] -> SketchResult
     |                  ^^^^^^^^^^^^^^^^^
     |                  Only HIL point in SKETCH
     v
   EXPAND:  [tools] -> [LLM] -> ExpandedPlan (no HIL)
     |
     v
   VALIDATE: [checks] -> [arbiter] -> [approval?] -> verdict
     |                                 ^^^^^^^^^^^^
     |                                 Only HIL point in VALIDATE
     v
   COMMIT: deterministic (no HIL, no LLM)
```

#### 12.5.3 Timeout Handling

```text
 Clarification timeout (60s per round):
   HILCoordinator.wait_for_response(60_000) expires
   -> Set waiting = false
   -> Return None to SketchService
   -> SketchService proceeds with best-effort interpretation

 Approval timeout (120s):
   HILCoordinator.wait_for_response(120_000) expires
   -> Set waiting = false
   -> ValidateService evaluates auto-approve safety:
      IF all side-effecting steps have safety_band_min == "GREEN"
         AND arbiter safety_assessment == "safe":
         -> Auto-approve, proceed to COMMIT
      ELSE:
         -> Plan FAILED (unsafe steps require explicit approval)

 LLM failure during question/summary generation:
   -> HILCoordinator skips the HIL interaction entirely
   -> Clarification: proceed without clarification (degraded plan quality)
   -> Approval: auto-approve if safe, otherwise FAIL
```

### 12.6 Error Recovery Summary

| Failure | Recovery | Impact |
| ------- | -------- | ------ |
| Clarification LLM timeout | Skip clarification, proceed with best-effort | Degraded: SKETCH may produce vaguer plan |
| Clarification user timeout (60s * 2 rounds) | Proceed with best-effort interpretation | Degraded: same as above |
| Approval LLM timeout | Skip presentation, auto-approve if safe | Plan may proceed without explicit user consent (safe plans only) |
| Approval user timeout (120s) + safe plan | Auto-approve | Plan proceeds; user missed review window |
| Approval user timeout (120s) + unsafe plan | Plan FAILED | Safety-critical: cannot proceed without consent |
| User rejects plan | Plan FAILED, emit `k1.planner.plan.failed.v1` | Orchestrator receives failure, may re-request with modified intent |
| Event Bus delivery failure | HILCoordinator never receives response -> timeout path | Resilient: timeout handler provides fallback |
| Concierge PENDING_CLARIFICATIONS miss | Response treated as new turn, HILCoordinator times out | Degraded: user's answer lost, timeout path triggers |

### 12.7 Cross-Reference Summary

| Reference | Section | Relationship |
| --------- | ------- | ------------ |
| SKETCH HIL clarification flow | 6.4 | Trigger conditions, full flow (6.4.1-6.4.4) |
| SKETCH prompt HIL\_ADDENDUM slot | 6.3.1 | Clarification response injected into LLM prompt |
| VALIDATE HIL approval flow | 8.4 | Trigger conditions, modification handling (8.4.1-8.4.4) |
| VALIDATE response routing table | 8.4.3 | approve / modify / reject / timeout actions |
| HIL response event schemas | 4.6 | HILClarificationResponse, HILApprovalResponse types |
| Micro-replan bypasses HIL | 10.4 | PLAN-12: micro-replan never triggers HIL |
| PLAN-10 invariant | 3 (invariants table) | Max 2 clarification rounds |
| PLAN-04 budget interaction | 3 (invariants table) | 45s covers computation, HIL wait is excluded |
| Concierge HIL routing | -- (k1/concierge/concierge.mmd) | PENDING\_CLARIFICATIONS, HIL Response Detector |
| Concierge HIL Response Detector | -- (k1/concierge/concierge.mmd) | Routes user reply as response, not new turn |

---

## 13. LLM Call Patterns & Budget Management

Every LLM call the Planner makes travels through a single exit point:

```text
 Service (Sketch|Expand|Validate|HILCoordinator)
   -> ILLMPort.execute(HubRequest)
      -> LLMGatewayAdapter
         -> LLM_REQUEST_BUS (async request-reply)
            -> Model Hub RequestRouter
               -> ProviderDispatcher -> Provider Plugin
            <- HubResponse
         <- HubResponse
      <- HubResponse
   <- HubResponse
```

No service contacts a provider directly.  No service picks a model.  The Planner
constructs a `HubRequest` with a **capability type** and **constraints**; the
Model Hub (Section 13.4) selects the provider, model, and fallback chain.

### 13.1 LLM Call Matrix

The Planner makes at most **5 LLM calls per full plan** (3 pipeline stages + up to
2 HIL prompts) and at most **3 LLM calls per micro-replan** (3 abbreviated stages,
no HIL).  COMMIT is deterministic -- zero LLM calls.

| Call ID | Stage | LLM? | Capability Type | max_tokens | timeout_ms | temperature | Purpose | Detail Section |
| ------- | ----- | ---- | --------------- | ---------- | ---------- | ----------- | ------- | -------------- |
| LLM-1 | SKETCH | YES | CHAT | 2048 | 8000 | 0.7 | Rough plan from intent + discovered caps | 6.3 |
| LLM-2 | EXPAND | YES | CHAT | 1024 | 5000 | 0.3 | Map tools, params, prompts to steps | 7.3 |
| LLM-3 | VALIDATE | YES | STRUCTURED | 512 | 3000 | 0.1 | Arbiter: coherence, safety, feasibility | 8.3 |
| LLM-4 | COMMIT | NO | -- | 0 | -- | -- | Deterministic: persist to K0 WAL | 9 |
| LLM-5a | HIL Clarification | YES | CHAT | 300 | 3000 | 0.7 | Generate natural-language question | 12.2 |
| LLM-5b | HIL Approval | YES | CHAT | 400 | 3000 | 0.7 | Format plan summary + approval options | 12.3 |
| LLM-M1 | Micro-SKETCH | YES | CHAT | 1024 | 5000 | 0.7 | Re-plan remaining steps | 10.3 |
| LLM-M2 | Micro-EXPAND | YES | CHAT | 512 | 3000 | 0.3 | Re-map tools for replacement | 10.3 |
| LLM-M3 | Micro-VALIDATE | YES | STRUCTURED | 256 | 2000 | 0.1 | Validate replacement plan | 10.3 |

**Capability type distribution**:

| Capability | Calls | Why |
| ---------- | ----- | --- |
| CHAT | LLM-1, LLM-2, LLM-5a, LLM-5b, LLM-M1, LLM-M2 | Free-form generation -- rough plan, tool mapping, question generation, plan summary |
| STRUCTURED | LLM-3, LLM-M3 | Schema-enforced JSON output -- arbiter verdict MUST conform to ValidationVerdict JSON Schema |

CHAT calls return raw text that the Planner parses against its OUTPUT_SCHEMA (Sections
6.3.1, 7.3.1).  STRUCTURED calls leverage Model Hub schema enforcement (the provider
constrains output tokens to match the declared `response_schema`), eliminating parse
failures for the arbiter verdict.

**Temperature gradient** (creative -> deterministic):

```text
 0.7  SKETCH, HIL Clarification, HIL Approval, Micro-SKETCH
      Creative tasks: plan generation, question phrasing, summary writing.

 0.3  EXPAND, Micro-EXPAND
      Precision tasks: capability mapping, parameter binding.
      Lower randomness produces more deterministic, schema-conformant output.

 0.1  VALIDATE, Micro-VALIDATE
      Judgment tasks: arbiter verdict.
      Near-deterministic -- the same plan should get the same verdict.
```

### 13.2 HubRequest / HubResponse Protocol

The Planner communicates with Model Hub through a single type pair defined by
the Model Hub module (`k1/model_hub/types.py`, source of truth).  Type definitions
are imported -- the Planner DOES NOT redefine them.

#### 13.2.1 HubRequest (Unified Envelope)

Every LLM call (LLM-1 through LLM-M3) is wrapped in a `HubRequest`.  The envelope
carries four top-level fields:

```yaml
HubRequest:
  capability: CapabilityType              # CHAT | STRUCTURED (Planner uses only these 2)
  payload: CapabilityPayload              # Polymorphic by capability type (see 13.2.2)
  constraints: RequestConstraints         # Budget, priority, temperature (see 13.2.3)
  trace_id: str                           # cognitive_trace_id from PlanRequest (FAB-09, MH-03)
```

**Field contract**:

| Field | Type | Required | Planner Usage |
| ----- | ---- | -------- | ------------- |
| `capability` | `CapabilityType` enum | Yes | CHAT for LLM-1, LLM-2, LLM-5a, LLM-5b, LLM-M1, LLM-M2.  STRUCTURED for LLM-3, LLM-M3. |
| `payload` | `CapabilityPayload` (union) | Yes | `ChatPayload` for CHAT calls, `StructuredOutputPayload` for STRUCTURED calls (Section 13.2.2) |
| `constraints` | `RequestConstraints` | Yes | Per-stage budget injected by PipelineController (Section 13.3) |
| `trace_id` | `str` | Yes | Propagated from `PlanRequest.trace_id`.  Enables end-to-end tracing from Concierge -> Planner -> Model Hub -> Provider. |

#### 13.2.2 Capability Payloads (Planner Uses 2 of 15)

The Model Hub defines 15 capability types (CHAT, TOOL_CALL, STRUCTURED, REASON,
EMBED, VISION, BATCH, MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS,
IMAGE_GEN, WEB_SEARCH, CODE_EXEC).  The Planner uses exactly 2:

**ChatPayload** (CHAT capability -- used by LLM-1, LLM-2, LLM-5a, LLM-5b, LLM-M1, LLM-M2):

```yaml
ChatPayload:
  messages: List[Message]                 # Planner always sends []  (single-shot, no history)
  system_prompt: str                      # SYSTEM SEGMENT from slot-based prompt assembly
  user_prompt: str                        # USER SEGMENT from slot-based prompt assembly
```

The Planner constructs single-shot requests: `messages` is empty, the full prompt
is carried in `system_prompt` + `user_prompt`.  There is no conversation history --
each LLM call is independent (the Planner assembles all prior context into the prompt
slots, not into a message thread).

**StructuredOutputPayload** (STRUCTURED capability -- used by LLM-3, LLM-M3):

```yaml
StructuredOutputPayload:
  messages: List[Message]                 # []  (single-shot)
  system_prompt: str                      # SYSTEM SEGMENT (ROLE + schema description)
  user_prompt: str                        # USER SEGMENT (plan details + check results)
  response_schema: Dict                   # JSON Schema for ValidationVerdict (Section 8.3.1)
  strict: bool                            # true -- Model Hub enforces schema at decode time
```

When `strict: true`, the Model Hub instructs the provider to constrain output tokens
to match `response_schema`.  This means the raw LLM output is always valid JSON
conforming to the ValidationVerdict schema -- no parse-and-retry needed for VALIDATE
stage calls.

**Why not TOOL_CALL?**  The Planner's 4 discovery tools (Section 11) are NOT invoked
via LLM function-calling.  The LLM generates a rough plan or expanded steps; the
Planner's `ToolCallRouter` service invokes discovery tools programmatically before
and during the LLM call.  The LLM never sees tool definitions in its payload.

#### 13.2.3 RequestConstraints

Every `HubRequest` carries explicit constraints.  No field is optional in practice --
PipelineController fills all values before the call.

```yaml
RequestConstraints:
  max_tokens: int                         # Hard ceiling on LLM output tokens (PLAN-11)
  timeout_ms: int                         # Deadline for the entire call (PLAN-11)
  priority: str                           # "INTERACTIVE" for all Planner calls (MH-15)
  temperature: float                      # 0.1 | 0.3 | 0.7 depending on call type
  consumer_id: str                        # Always "planner" (MH-11 cost tracking + audit)
```

**Constraint field behavior**:

| Field | Who Sets | Who Enforces | On Violation |
| ----- | -------- | ------------ | ------------ |
| `max_tokens` | PipelineController per stage | Model Hub (MH-04): truncates LLM output at limit | Response truncated, Planner receives partial output |
| `timeout_ms` | PipelineController per stage | LLMGatewayAdapter: cancels async wait | Timeout error raised, service enters error recovery |
| `priority` | Always `"INTERACTIVE"` | Model Hub timeout tier: INTERACTIVE = 30s max | MH-15 timeout cap (Planner's per-call timeout is always tighter) |
| `temperature` | PipelineController per stage | Model Hub passes to provider | Provider interprets (0.0 = deterministic, 1.0 = creative) |
| `consumer_id` | Always `"planner"` | Model Hub CostTracker (MH-11): aggregates cost per consumer | Cost attributed to "planner" in audit log |

**Optional constraint fields** (Planner does NOT set):

| Field | Default | Why Not Set |
| ----- | ------- | ----------- |
| `model_preference` | null | Planner does NOT pick models (Section 13.4) |
| `provider_preference` | null | Planner does NOT pick providers |
| `cost_limit` | null | Daily budget enforcement is Model Hub's (MH-08), not per-request |
| `idempotency_key` | null | Planner does not retry the same call with the same key (V1) |

#### 13.2.4 HubResponse (Unified Envelope)

The Model Hub returns a `HubResponse` for every call:

```yaml
HubResponse:
  result: CapabilityResult                # LLM output (capability-specific)
  metadata: ResponseMetadata              # Operational telemetry
```

**CapabilityResult** (what the Planner consumes):

```yaml
CapabilityResult:
  content: str                            # Raw LLM output text
                                          # For CHAT: free text (JSON string matching OUTPUT_SCHEMA)
                                          # For STRUCTURED: schema-valid JSON string
```

The Planner extracts `result.content` and parses it:

- **CHAT calls** (LLM-1, LLM-2, LLM-5a, LLM-5b, LLM-M1, LLM-M2): Parse as JSON
  against the stage's OUTPUT_SCHEMA.  On parse failure, enter stage error recovery.
- **STRUCTURED calls** (LLM-3, LLM-M3): Content is guaranteed schema-valid by Model Hub.
  Parse directly into `ValidationVerdict` (Section 8.3.3).

**ResponseMetadata** (what the Planner records):

```yaml
ResponseMetadata:
  request_id: str                         # Model Hub internal correlation ID
  model_id: str                           # Which model was used (e.g. "gpt-4o", "claude-4-sonnet")
  provider_id: str                        # Which provider (e.g. "openai", "anthropic", "ollama")
  usage:                                  # Token consumption
    prompt_tokens: int                    # Input tokens (prompt)
    completion_tokens: int                # Output tokens (LLM response)
    total_tokens: int                     # Sum
  cost_usd: float                         # Estimated cost for this call (from manifest cost table)
  latency_ms: int                         # Model Hub observed latency (end-to-end)
  cache_hit: bool                         # Whether ResponseCache served this (MH-09)
  capability: str                         # Echo of requested capability type
  trace_id: str                           # Echo of cognitive_trace_id
  fallback_used: bool                     # Whether fallback cascade was triggered
```

PipelineController records metadata for every call:

```text
 PipelineController._record_llm_call(stage, hub_response):
   |
   |-- stage_token_usage[stage] += hub_response.metadata.usage.total_tokens
   |-- stage_cost[stage] += hub_response.metadata.cost_usd
   |-- stage_latency[stage] = hub_response.metadata.latency_ms
   |-- total_plan_tokens += hub_response.metadata.usage.total_tokens
   |-- total_plan_cost += hub_response.metadata.cost_usd
   |
   |-- Emit delta:
       k1.planner.delta.v1:
         type: "llm_call_complete"
         stage: "<current stage>"
         model_id: hub_response.metadata.model_id
         tokens: hub_response.metadata.usage.total_tokens
         cost_usd: hub_response.metadata.cost_usd
         latency_ms: hub_response.metadata.latency_ms
         cache_hit: hub_response.metadata.cache_hit
```

This per-call telemetry flows to the Learning Loop for cost tracking and drift detection.

### 13.3 Budget Enforcement (PLAN-11)

**PLAN-11**: All LLM calls carry budget -- `{max_tokens, timeout_ms}` -- no unbounded calls.

The Planner enforces PLAN-11 at two layers: **PipelineController budget injection**
(compile-time guarantee) and **Model Hub hard enforcement** (runtime guarantee).

#### 13.3.1 PipelineController Budget Injection

PipelineController holds a per-stage budget table.  Before any service makes an LLM
call, PipelineController injects the stage budget into the `RequestConstraints` that
the service uses to construct its `HubRequest`.

```text
 PipelineController.execute(plan_request):
   |
   |-- stage_budgets = BUDGET_TABLE[plan_type]   # "full" or "micro"
   |
   |-- SKETCH:
   |     constraints = stage_budgets["SKETCH"]
   |     sketch_result = SketchService.execute(plan_request, constraints)
   |
   |-- EXPAND:
   |     constraints = stage_budgets["EXPAND"]
   |     expanded = ExpandService.execute(sketch_result, constraints)
   |
   |-- VALIDATE:
   |     constraints = stage_budgets["VALIDATE"]
   |     verdict = ValidateService.execute(expanded, constraints)
   |
   |-- COMMIT:
   |     CommitService.execute(expanded, plan_request)   # No constraints (no LLM)
```

**Full Pipeline Budget Table**:

| Stage | max_tokens | timeout_ms | temperature | Notes |
| ----- | ---------- | ---------- | ----------- | ----- |
| SKETCH | 2048 | 8000 | 0.7 | Creative generation -- highest budget |
| EXPAND | 1024 | 5000 | 0.3 | Precision mapping -- half of SKETCH |
| VALIDATE | 512 | 3000 | 0.1 | Compact verdict -- structured output |
| HIL Clarification | 300 | 3000 | 0.7 | Short question generation |
| HIL Approval | 400 | 3000 | 0.7 | Plan summary generation |

**Micro-Replan Budget Table**:

| Stage | max_tokens | timeout_ms | temperature | Notes |
| ----- | ---------- | ---------- | ----------- | ----- |
| Micro-SKETCH | 1024 | 5000 | 0.7 | Half of full SKETCH |
| Micro-EXPAND | 512 | 3000 | 0.3 | Half of full EXPAND |
| Micro-VALIDATE | 256 | 2000 | 0.1 | Tightest of all stages |

**Total token budget per plan type**:

| Plan Type | Worst-Case LLM Output Tokens | Typical Observed | Wall-Time Budget |
| --------- | ---------------------------- | ---------------- | ---------------- |
| Full plan (no HIL) | 2048 + 1024 + 512 = **3584** | ~2000 | 16s (sum of timeouts) |
| Full plan (with HIL clarification x2) | 3584 + 300 + 300 = **4184** | ~2500 | 22s |
| Full plan (with HIL clarification + approval) | 3584 + 300 + 400 = **4284** | ~2600 | 22s |
| Micro-replan | 1024 + 512 + 256 = **1792** | ~1200 | 10s (hard timeout) |

All values remain well within the 45s total planning timeout (PLAN-04) and the $5/day
Model Hub budget (MH-08).

#### 13.3.2 Model Hub Hard Enforcement

The Planner's per-stage budgets are **requests** to the Model Hub.  The Model Hub
enforces them as hard constraints:

| Constraint | Model Hub Enforcement | Invariant |
| ---------- | --------------------- | --------- |
| `max_tokens` | Provider receives `max_tokens` parameter; output truncated at limit | MH-04 |
| `timeout_ms` | LLMGatewayAdapter cancels the async call if Model Hub does not respond within the timeout | -- |
| `priority: INTERACTIVE` | Model Hub applies INTERACTIVE tier timeout cap (30s max per MH-15).  Planner's per-call timeout is always tighter. | MH-15 |
| Daily budget | BudgetEnforcer tracks cumulative cost.  If daily budget exceeded ($5 default), returns REJECT with `k1.model_hub.budget.alert.v1` event. | MH-04, MH-08 |
| Circuit breaker | Per-provider CB (config from manifest).  If provider CB is OPEN, Model Hub falls back to next in chain. | MH-05 |

**What happens on budget rejection**:

```text
 BudgetEnforcer returns REJECT
   -> Model Hub emits k1.model_hub.budget.alert.v1 {level: EXCEEDED}
   -> HubResponse NOT returned
   -> LLMGatewayAdapter raises BudgetExceededError
   -> Service catches -> enters stage error recovery
   -> PipelineController emits plan.failed.v1 with reason: "budget_exceeded"
```

In practice, the Planner's per-plan token usage (~3500 tokens at ~$0.005/plan) is
negligible relative to the $5/day budget.  Budget rejection would only occur under
extreme system-wide load from all consumers combined.

#### 13.3.3 Token Usage Tracking

PipelineController maintains running totals throughout the pipeline:

```python
# PipelineController internal state (reset per plan)
stage_token_usage: Dict[str, int] = {}      # stage -> total_tokens
stage_cost: Dict[str, float] = {}           # stage -> cost_usd
stage_latency: Dict[str, int] = {}          # stage -> latency_ms
total_plan_tokens: int = 0                  # Sum across all stages
total_plan_cost: float = 0.0                # Sum across all stages
```

These counters are:

- **Incremented** on every `_record_llm_call()` (after each HubResponse)
- **Emitted** as part of the stage delta (`k1.planner.delta.v1`)
- **Included** in `plan.ready.v1` and `plan.failed.v1` terminal events
- **Reset** at `LC_PLAN_START` (start of next plan)

For micro-replan, a separate set of counters is maintained so micro-replan cost does
not pollute the original plan's accounting.

#### 13.3.4 Input Token Estimation and Truncation

PLAN-11 governs **output** tokens (`max_tokens`).  Input tokens are managed by each
service's prompt assembly logic using truncation priority:

**SKETCH truncation priority** (lowest priority truncated first):

| Priority | Slot | Truncation Action |
| -------- | ---- | ----------------- |
| 4 (lowest) | LONG_TERM_MEMORY | Truncate to 3 most recent facts/preferences |
| 3 | CAPABILITY_CATALOG | Reduce top-K from 10 to 5 |
| 2 | SESSION_CONTEXT | Omit `history_recent` section |
| 1 (highest) | INTENT | Never truncated (source of truth) |

**EXPAND truncation priority**:

| Priority | Slot | Truncation Action |
| -------- | ---- | ----------------- |
| 4 (lowest) | PROMPT_CATALOG | Reduce to top-3 matches |
| 3 | CAPABILITY_SET | Reduce to only referenced capabilities |
| 2 | SKETCH_PLAN | Never truncated (input from prior stage) |
| 1 (highest) | INTENT | Never truncated |

**VALIDATE**: No truncation needed -- input is compact (plan summary + check results,
typically 350-500 tokens).

Each service estimates input token count using a conservative heuristic (4 characters
per token).  If estimated input exceeds `(model_context_window - max_tokens) * 0.9`,
truncation is applied in priority order until the estimate fits.

### 13.4 Model Selection (Planner Does Not Choose)

The Planner has zero control over which model or provider handles its LLM calls.
This is a deliberate architectural boundary:

```text
 Planner responsibility: WHAT to ask
   - Compose prompt (slot-based, per Section 6.3/7.3/8.3)
   - Declare capability type (CHAT or STRUCTURED)
   - Declare constraints (max_tokens, timeout_ms, temperature, priority)
   - Declare consumer_id ("planner")

 Model Hub responsibility: HOW to answer
   - Select provider (from manifest capabilities + health + CB state)
   - Select model (from scoring algorithm + constraints + persona)
   - Build fallback chain (up to 3 alternatives, capability-aware MH-06)
   - Route to provider plugin
   - Handle failures, retries, fallback cascade
```

#### 13.4.1 Model Hub Selection Algorithm

Model Hub's `ModelSelector` scores each eligible `(provider, model)` pair across
5 dimensions.  Weights vary by priority tier:

| Dimension | INTERACTIVE Weight | What It Measures |
| --------- | ------------------ | ---------------- |
| Latency | 0.30 | Model tier from manifest (FAST > STANDARD > PREMIUM) |
| Cost | 0.20 | Price from manifest cost table (cheaper = higher score) |
| Preference | 0.30 | User model preference from SessionState `persona` section |
| Health | 0.20 | Provider health status (HEALTHY > DEGRADED > UNHEALTHY) |

All Planner calls use `priority: INTERACTIVE`, so these weights apply uniformly.

The Planner does NOT set `model_preference` or `provider_preference` in its constraints.
If the user has expressed a model preference in SessionState (e.g., "prefer local
models"), the Model Hub's `SessionStateReadAdapter` reads this and factors it into the
preference score -- the Planner never mediates this.

#### 13.4.2 Placement Cascade (MH-13)

Model Hub applies a placement cascade before scoring:

```text
 1. Local providers (manifest.placement.type = local_*)
    NPU -> GPU (vLLM) -> CPU (Ollama)
    Checked: plugin health, CB state, capability support

 2. Remote providers (manifest.placement.type = remote)
    OpenAI, Anthropic, Google -- scored by ModelSelector
    Checked: CB state, rate limit headroom, capability support

 3. Cached response (MH-09)
    ResponseCache keyed by (capability, prompt_hash, model_id, temperature)
    TTL: 5 min.  Planner calls with temperature > 0.0 are rarely cached.

 4. Template response (last resort)
    Canned fallback for critical paths.  Planner has no template fallback --
    if all providers fail, the LLM call fails and stage error recovery activates.
```

For the Planner, the practical cascade is: if a local GPU model supports CHAT and is
healthy, it handles the call.  If not, the request goes to the best-scoring remote
provider.  The Planner is unaware of which path was taken -- it receives the same
`HubResponse` regardless.

#### 13.4.3 Capability-Aware Fallback (MH-06)

When a provider fails mid-call (timeout, 5xx, rate limit), Model Hub falls back to
the next provider in the fallback chain.  The chain is built per-request and only
includes providers that:

1. Support the requested capability (CHAT or STRUCTURED)
2. Have CB in CLOSED or HALF_OPEN state
3. Have rate limit headroom
4. Are HEALTHY or DEGRADED

For the Planner's STRUCTURED calls (LLM-3, LLM-M3), the fallback chain is narrower:
not all providers support schema-enforced structured output.  If no provider supports
STRUCTURED, Model Hub falls back to CHAT with the same prompt and the Planner must
parse the output manually (degraded mode).

#### 13.4.4 Cost Attribution (MH-11)

Every Planner LLM call carries `consumer_id: "planner"`.  Model Hub's AuditLogger
and CostTracker attribute cost to this consumer:

```text
 AuditLogger record (per LLM call):
   request_id:       <Model Hub internal ID>
   consumer_id:      "planner"
   capability:       "CHAT" | "STRUCTURED"
   model_id:         <selected model>
   provider_id:      <selected provider>
   prompt_tokens:    <input tokens>
   completion_tokens: <output tokens>
   cost_usd:         <tokens * manifest cost / 1M>
   latency_ms:       <end-to-end>
   cache_hit:        true | false
   fallback_chain:   [<provider1>, <provider2>]  (if fallback used)
   trace_id:         <cognitive_trace_id>
```

These audit records enable:

- **Cost dashboards**: Total Planner cost per day/week/month
- **Per-stage analysis**: SKETCH consistently costs more than VALIDATE
- **Model comparison**: Same plan quality at lower cost with smaller model?
- **Budget alerting**: "planner" consumer approaching its fair share of daily budget

### 13.5 LLM Call Lifecycle (End-to-End)

The complete lifecycle of a single Planner LLM call, combining all subsections:

```text
 1. PipelineController injects stage budget -> constraints
 2. Service assembles prompt (slot-based, per 6.3/7.3/8.3/12.2/12.3)
 3. Service constructs HubRequest(capability, payload, constraints, trace_id)
 4. Service calls ILLMPort.execute(hub_request)
 5. LLMGatewayAdapter serializes to LLM_REQUEST_BUS
 6. Model Hub RequestRouter:
      a. Validate envelope (schema, trace_id MH-03)
      b. BudgetEnforcer: check daily budget (MH-04, MH-08)
      c. CapabilityRouter: find eligible providers for capability
      d. ModelSelector: score (provider, model) pairs, build fallback chain
      e. ResponseCache: check for cache hit (skip for temperature > 0.9)
      f. NormalizationLayer: HubRequest -> NormalizedRequest
      g. ProviderDispatcher:
           - Acquire circuit breaker (MH-05)
           - Acquire rate limiter (MH-12)
           - Get credential (MH-02)
           - plugin.execute(normalized_request)
           - On failure: next in fallback chain (MH-06)
      h. NormalizationLayer: ProviderResponse -> HubResponse
      i. CostTracker: track(response, model_info)
      j. AuditLogger: log(request, response, metadata) (MH-11)
      k. ResponseCache: put(cache_key, response, ttl=300)
 7. HubResponse returned via LLM_REQUEST_BUS
 8. LLMGatewayAdapter deserializes HubResponse
 9. Service receives HubResponse:
      a. Extract result.content
      b. Parse against OUTPUT_SCHEMA (CHAT) or typed schema (STRUCTURED)
      c. Handle parse failure -> stage error recovery
10. PipelineController._record_llm_call(stage, hub_response)
      a. Update token/cost/latency counters
      b. Emit k1.planner.delta.v1 {type: "llm_call_complete"}
```

### 13.6 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| SKETCH prompt assembly + HubRequest | 6.3 | LLM-1 full detail: slots, output schema, routing path |
| EXPAND prompt assembly + HubRequest | 7.3 | LLM-2 full detail: precision mapping, temperature 0.3 |
| VALIDATE arbiter + HubRequest | 8.3 | LLM-3 full detail: STRUCTURED capability, verdict schema |
| COMMIT (no LLM) | 9 | LLM-4 = none, deterministic path |
| Micro-replan LLM stages | 10.3 | LLM-M1, LLM-M2, LLM-M3 abbreviated budgets |
| HIL Clarification LLM call | 12.2 | LLM-5a: question generation, 300 tokens |
| HIL Approval LLM call | 12.3 | LLM-5b: plan summary, 400 tokens |
| Model Hub architecture | `k1/model_hub/model_hub.mmd` | Full hub spec: 13 services, 18 invariants, 15 capabilities |
| ILLMPort definition | `planner.mmd` PORTS section | HubRequest/HubResponse types, routing description |
| PLAN-11 invariant | `planner.mmd` INVARIANTS section | "All LLM calls carry budget -- no unbounded calls" |
| PLAN-04 total timeout | `planner.mmd` INVARIANTS section | "Max planning time 45s" -- all LLM budgets must fit within |
| MH-04 hard budget enforcement | `model_hub.mmd` INVARIANTS section | "Budget enforcement HARD -- request rejected if exceeded" |
| MH-11 audit trail | `model_hub.mmd` INVARIANTS section | "All LLM calls audited: consumer_id, capability, cost, trace_id" |

---

## 14. SessionState Access Pattern

The Planner's relationship with SessionState is asymmetric by design: it reads
extensively but writes nothing.  Two invariants govern this relationship --
PLAN-01 (no writes) and FAB-01 (Fabric never writes) -- and together they ensure
that the Planner cannot corrupt shared session state, even under crash scenarios.

### 14.1 Reader, Never Writer (PLAN-01)

**PLAN-01**: The Planner NEVER writes SessionState.  All reads are lock-free
multi-reader.  Enforced by `IStateReadPort` (no write methods exist on the port
interface).

The Planner's sole write path to the outside world is:

- `IDeltaEmitPort.emit(delta)` -- fire-and-forget deltas to the Delta Bus
- `IEventPort.publish(topic, payload)` -- plan lifecycle events
- `IBridgePort.persist_plan(committed_plan)` -- WAL write to K0

None of these touch SessionState. The Orchestrator (or other downstream consumers)
may update SessionState based on plan results, but the Planner itself never does.

#### 14.1.1 Access Operations

| Operation | Allowed? | Port | Method | Thread Safety |
| --------- | -------- | ---- | ------ | ------------- |
| Read `beliefs_active` | Yes | IStateReadPort | `read_sections(session_id, ["beliefs_active"])` | Multi-reader, lock-free |
| Read `persona` | Yes | IStateReadPort | `read_sections(session_id, ["persona"])` | Multi-reader, lock-free |
| Read `control` | Yes | IStateReadPort | `read_sections(session_id, ["control"])` | Multi-reader, lock-free |
| Read `affective_now` | Yes | IStateReadPort | `read_sections(session_id, ["affective_now"])` | Multi-reader, lock-free |
| Read `history_recent` | Yes | IStateReadPort | `read_sections(session_id, ["history_recent"])` | Multi-reader, lock-free |
| Read `scoreboard` | Yes | IStateReadPort | `read_sections(session_id, ["scoreboard"])` | Multi-reader, lock-free |
| Read all (snapshot) | Yes | IStateReadPort | `get_snapshot(session_id)` | Atomic capture |
| Read temporal context | Yes | (inline) | `PlanRequest.context` snapshot | Immutable frozen dataclass |
| Write ANY section | **NO** | -- | -- | PLAN-01: no write port exists |

#### 14.1.2 Compile-Time Enforcement

PLAN-01 is enforced at the type level, not by runtime checks:

```text
 IStateReadPort (from planner.mmd PORT_STATE_READ):
   read_sections(sections[]) -> StateSnapshot
   Multi-reader, lock-free (PLAN-01)

 There is no IStateWritePort in the Planner's port set.
 The adapter (SessionStateReadAdapter) wraps ISessionStateReader
 which has only:
   read_section(session_id, section) -> Dict
   read_sections(session_id, names) -> Dict
   get_snapshot(session_id) -> SessionSnapshot

 No write method exists on the interface.  A developer cannot
 accidentally write because there is no path to call.
```

Other K1 modules that read SessionState follow the same pattern:

| Module | Port | Invariant |
| ------ | ---- | --------- |
| Planner | IStateReadPort | PLAN-01 |
| Fabric | ISessionStateReader | FAB-01 |
| Model Hub | IStateReadPort | MH-01 |
| Orchestrator | ISessionStatePort | Read + Write (sole writer for most sections) |

### 14.2 SessionState Section Catalog

SessionState exposes 12 sections organized into 3 storage tiers.  The Planner reads
from the HOT CORE and WARM tiers only.

#### 14.2.1 Section Inventory

| Section | Tier | FlatBuffer? | Eviction Priority | Planner Reads? | What Planner Extracts |
| ------- | ---- | ----------- | ----------------- | -------------- | --------------------- |
| `control` | HOT CORE | Yes | NEVER (0) | **Yes** | Effective safety band, escalation state, flow state, active domains |
| `beliefs_active` | HOT CORE | Yes | NEVER (0) | **Yes** | Active facts (SVO triples with confidence), mentioned entities, mentioned time/location, pinned facts |
| `scoreboard` | HOT CORE | Yes | NEVER (0) | Rarely | QUD (question under discussion), active questions, referents |
| `affective_now` | HOT CORE | Yes | NEVER (0) | Rarely | Current emotion, intensity, valence/arousal/dominance, trajectory, empathy flags |
| `narrative_active` | HOT CORE | Yes | NEVER (0) | No | Active conversation threads, topic tracking |
| `history_active` | HOT CORE | Yes | NEVER (0) | No | Turns 1-10 (full content) -- Orchestrator uses, Planner has via PlanRequest.context |
| `history_recent` | WARM | Yes | 3 | **Yes** | Compressed turns 11-30, summarized turns 31-40, session summary |
| `persona` | WARM | Yes | 4 (last to evict) | **Yes** | Personality profile (warmth, formality, verbosity, humor, directness), vocabulary mappings, response preferences, interaction style |
| `beliefs_history` | WARM | Yes | 2 | No | Graduated facts from previous turns |
| `clarifications` | WARM | Yes | 1 (first to evict) | No | HIL clarification history |
| `meta` | -- | Yes | NEVER (0) | No | Session metadata, timing, diagnostics |
| `telemetry` | -- | Yes | NEVER (0) | No | Performance counters, section sizes |

#### 14.2.2 Canonical Planner Read Sets

Different stages read different section sets:

**SKETCH** (primary usage -- via `query_planning_context()` tool call):

```text
 Canonical request: ["beliefs_active", "control", "history_recent"]

 beliefs_active:  Ground the plan in known world state.
                  "Mom prefers Italian food" (Fact: subject=Mom, predicate=prefers,
                  object=Italian food, confidence=0.92)
                  "8 family members" (Fact: subject=family, predicate=has_count,
                  object=8, confidence=1.0)
                  Mentioned entities become plan step participants.
                  Mentioned time becomes scheduling constraint.

 control:         Effective safety band gates all Fabric discovery calls.
                  safety.band -> passed as safety_band to discover_capabilities()
                  flow_state.current_phase -> awareness of Orchestrator state
                  domains.active_domains -> domain context for discovery

 history_recent:  Cross-check with K0 recall results.
                  Compressed turns provide recent interaction context.
                  Session summary (~200 chars) gives conversation arc.
```

**EXPAND** (typically does not read):

```text
 EXPAND receives all necessary context from SketchResult (which already
 incorporated SessionState data).  If EXPAND calls query_planning_context
 (from the remaining PLAN-05 budget), it reads the same sections for
 delta freshness -- but this is a V2 optimization, not V1 canonical path.
```

**VALIDATE** (does not read):

```text
 VALIDATE receives ExpandedPlan which carries all context transitively.
 The arbiter needs the plan + original intent + deterministic check results,
 not raw SessionState sections.
```

**HIL Clarification / Approval** (indirect):

```text
 HILCoordinator receives context from the calling service (SKETCH or VALIDATE).
 It does not make its own SessionState calls.
```

**Micro-Replan** (does not read):

```text
 Micro-replan receives context via MicroReplanRequest (which includes
 remaining_steps, completed_results, and failure_context from the Orchestrator).
 No fresh SessionState read.
```

### 14.3 Context Flow Into LLM Prompts

SessionState data reaches LLM prompts through two independent paths.  Both are
read-only.

#### 14.3.1 Path 1: PlanRequest.context (Orchestrator Snapshot)

The Orchestrator captures a `SessionSnapshot` at dispatch time and embeds it in the
`PlanRequest`:

```text
 Orchestrator.dispatch_high(task_envelope):
   |
   |-- fresh_snapshot = state_port.get_snapshot(session_id)
   |     -> SessionSnapshot (frozen, all sections at capture time)
   |
   |-- plan_request = PlanRequest(
   |       intent = task_envelope.intent,
   |       trace_id = task_envelope.trace_id,
   |       context = fresh_snapshot,                    # <-- snapshot embedded here
   |       constraints = task_envelope.constraints,
   |       timeout_ms = 45_000,
   |     )
   |
   |-- planner_port.request_plan(plan_request)
```

**PlanRequest.context type**:

```yaml
SessionSnapshot (frozen dataclass, from k1/fabric/ports/state_reader.py):
  session_id: str                         # Active session identifier
  sections: Dict[str, Dict[str, Any]]     # Section name -> section data
  timestamp_ms: int                       # Capture timestamp (epoch ms)
  section_names: List[str]                # Available section names at capture time
```

This snapshot is **immutable** (`frozen=True`).  The Planner cannot modify it.
It provides the baseline context at plan start time.

#### 14.3.2 Path 2: query_planning_context() (Fresh Read)

During SKETCH, the `ToolCallRouter` dispatches a `query_planning_context()` call to
`IStateReadPort`, which returns a fresh `SessionSnapshot`.  This is the canonical
path for SessionState access (Section 11.3).

```text
 SketchService.execute():
   |
   |-- tool_results = await ToolCallRouter.call_parallel([
   |       ("discover_capabilities", {intent: ..., domain: ...}),
   |       ("query_planning_context", {sections: ["beliefs_active", "control", "history_recent"]}),
   |       ("recall_for_planning", {query: ...}),
   |   ])
   |
   |-- session_data = tool_results["query_planning_context"]
   |     -> Dict[str, Any]  (section name -> section data)
   |
   |-- assemble_prompt(
   |       intent = plan_request.intent,
   |       discovery = tool_results["discover_capabilities"],
   |       context = session_data,                     # <-- fresh read
   |       memory = tool_results["recall_for_planning"],
   |       constraints = plan_request.constraints,
   |     )
```

#### 14.3.3 Prompt Slot Mapping

SessionState data populates specific slots in the SKETCH prompt (Section 6.3.1):

| Prompt Slot | SessionState Source | Content Rendered |
| ----------- | ------------------- | ---------------- |
| `SESSION_CONTEXT` | `beliefs_active` section | Active facts as structured text: `"Mom prefers Italian food (confidence: 0.92)"`, entity list, mentioned time/location |
| `SESSION_CONTEXT` | `control` section | `"Safety band: GREEN"`, `"Active domains: cooking, scheduling"` |
| `SESSION_CONTEXT` | `history_recent` section | Session summary (~200 chars), compressed turn list (entities + intents) |
| `CONSTRAINTS` | `control.safety.band` | Safety band constraint passed to discovery calls AND injected into prompt |

The `SESSION_CONTEXT` slot is a single rendered block.  SketchService merges all
section data into a coherent context summary.  Example rendering:

```text
 SESSION_CONTEXT:
   Known facts:
     - Mom prefers Italian food (confidence: 0.92)
     - Family has 8 members (confidence: 1.0)
     - Budget limit: $500 (confidence: 0.85)
   Current entities: Mom, Dad, Marcus, Amy, Panda
   Temporal: February 21 mentioned as target date
   Safety band: GREEN
   Active domains: cooking, scheduling, family
   Recent context: User has been planning a birthday party for the last 3 turns
```

**EXPAND** and **VALIDATE** do not re-read SessionState.  They inherit context
transitively:

```text
 SKETCH prompt -> SketchResult.rationale (carries context reasoning)
 SketchResult -> EXPAND prompt (SKETCH_PLAN slot includes rationale)
 ExpandedPlan -> VALIDATE prompt (PLAN_SUMMARY slot includes context)
```

### 14.4 Snapshot Freshness

Planning takes 10-30s (p50: 12s, p99: 30s).  The SessionState snapshot captured at
the start may drift during execution as the Concierge processes new user messages
or the Orchestrator updates state.

#### 14.4.1 Two-Snapshot Freshness Model

The Planner receives context from two sources with different ages:

```text
 T0: Orchestrator captures PlanRequest.context snapshot
 T1: Planner dequeues PlanRequest from mailbox (T1 >= T0)
 T2: SketchService calls query_planning_context() (T2 >= T1)
 T3: SKETCH LLM call starts (T3 >= T2)
 T4: COMMIT completes (T4 >= T3, T4 - T0 typically 10-30s)

 PlanRequest.context age at T2:   (T2 - T0) ms
 Fresh read age at T3:            (T3 - T2) ms  (negligible, <10ms read + <1ms queue)
```

**Freshness heuristic** (V1 canonical path):

```text
 V1: ALWAYS issue the fresh read via query_planning_context()
     Use fresh data as primary source.
     Use PlanRequest.context as fallback if fresh read fails.

 V2 optimization (not yet implemented):
     If PlanRequest.context.timestamp_ms is within 5000ms of now:
       MAY skip the fresh read (saves 1 tool call from PLAN-05 budget)
     If PlanRequest.context.timestamp_ms is older than 5000ms:
       MUST issue fresh read (context may have drifted during queue wait)
```

#### 14.4.2 Staleness Impact Analysis

| Scenario | Staleness Risk | Impact on Plan | Mitigation |
| -------- | -------------- | -------------- | ---------- |
| Fast plan (p50 = 12s) | Low: context <12s old at COMMIT | Negligible -- beliefs rarely change in 12s | None needed |
| Slow plan (p99 = 30s) | Medium: context <30s old | New beliefs may exist (new entities mentioned) | VALIDATE catches obvious mismatches |
| Queue wait + slow plan | Higher: mailbox delay + planning | User may have added context during wait | Fresh read at T2 partially mitigates |
| Safety band change | Critical: GREEN -> AMBER during plan | Plan may reference capabilities no longer available | VALIDATE capability-existence check catches |
| User correction | Medium: "actually, 6 people, not 8" | Plan built on stale fact | Next planning cycle corrects; current plan proceeds |

**Design decision**: The Planner does NOT re-read SessionState mid-pipeline (between
stages).  The performance cost (~10ms) would be acceptable, but the added complexity
of handling context changes mid-plan does not justify the benefit in V1.  If context
changes significantly, the Orchestrator will catch it during execution (guard checkpoints)
and trigger a micro-replan.

#### 14.4.3 Consistency Guarantees

SessionState's `get_snapshot()` provides an **atomic capture**: all sections are read
in a single operation, so there is no torn-read risk (e.g., beliefs from turn N +
control from turn N+1).

However, the Planner uses `read_sections()` (selective sections, not full snapshot)
as the canonical path via `query_planning_context()`.  The `read_sections()` method
reads each requested section under a shared reader lock, release between sections.
In practice, inter-section consistency is maintained because:

1. SessionState writes happen at turn boundaries (complete before Planner starts)
2. The Planner executes within a single turn's processing window
3. No section write can happen while the Planner is active for the same turn

### 14.5 Degraded Access

If the SessionState read fails (adapter error, timeout, or SessionState module
unhealthy), the Planner degrades gracefully:

```text
 query_planning_context() call fails:
   |
   |-- ToolCallRouter catches error, returns empty Dict
   |
   |-- SketchService fallback:
   |     1. Use PlanRequest.context (Orchestrator snapshot) as primary source
   |     2. If PlanRequest.context is also None (should never happen, but defensive):
   |        a. safety_band defaults to GREEN
   |        b. beliefs treated as empty (plan with no grounding)
   |        c. history treated as empty (no recent context)
   |     3. LLM prompt SESSION_CONTEXT slot receives degraded content:
   |        "(SessionState unavailable -- planning with limited context)"
   |
   |-- Plan quality degrades (no belief grounding) but the pipeline
       DOES NOT FAIL.  A plan with empty context is better than no plan.
```

The `ISessionStateReader` protocol explicitly supports this:

```text
 From k1/fabric/ports/state_reader.py docstring:
   "Optional port: when None is injected, consumers degrade gracefully
    (policy scores neutral, context sections empty, validation skipped)."
```

### 14.6 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| `query_planning_context()` tool | 11.3 | Full tool specification: signature, sections, freshness protocol |
| SKETCH prompt SESSION_CONTEXT slot | 6.3.1 | How SessionState data is rendered in prompt |
| PlanRequest type definition | `k1/orchestrator/types.py` | `context: Optional[SessionSnapshot]` field |
| SessionSnapshot type | `k1/fabric/ports/state_reader.py` | Frozen dataclass: session_id, sections, timestamp_ms, section_names |
| ISessionStateReader protocol | `k1/fabric/ports/state_reader.py` | `read_section()`, `read_sections()`, `get_snapshot()` |
| IStateReadPort in planner.mmd | `planner.mmd` PORTS section | `read_sections(sections[]) -> StateSnapshot` |
| SessionStateReadAdapter | `planner.mmd` ADAPTERS_PROD section | Multi-reader lock-free access, HOT sections only |
| PLAN-01 invariant | `planner.mmd` INVARIANTS section | "NEVER writes SessionState" |
| SessionState sections | `k1/sessionstate/sections/` | 12 section implementations (FlatBuffer-backed) |
| Truncation priority (SESSION_CONTEXT) | 13.3.4 | Priority 2 -- omit `history_recent` first, never truncate INTENT |

---

## 15. Port Architecture (7 Hexagonal Boundaries)

The Planner defines 7 ports that form its hexagonal boundary.  All external I/O
travels through these ports -- there is no backdoor access to infrastructure.  Two
system invariants apply globally across all ports:

- **PLAN-01**: No port exposes a SessionState write method.
- **PLAN-06**: No port exposes a capability execution method.

Each port is a `typing.Protocol` (structural subtyping, `@runtime_checkable`).  The
Planner never `import`s an adapter class -- it receives port-typed objects at
construction via dependency injection.  This means:

1. Production wiring: `Kernel.boot()` injects production adapters.
2. Test wiring: Test fixtures inject in-memory test adapters.
3. The Planner code is identical in both environments.

### 15.1 Port Summary

| Port | Direction | Underlying Fabric Port | Adapter (prod) | Adapter (test) |
| ---- | --------- | ---------------------- | --------------- | -------------- |
| IMailboxPort | Inbound | `IPlannerMailbox` (consumer-driven, `k1/orchestrator/adapters/planner_adapter.py`) | MailboxAdapter | TestMailboxAdapter |
| ILLMPort | Outbound | `IModelHubPort` (via LLM Request Bus, `k1/model_hub/model_hub.mmd`) | LLMGatewayAdapter | TestLLMAdapter |
| IFabricRetrievalPort | Outbound | `FabricRetrieval` API (`k1/fabric/fabric.py` line 1088) | FabricRetrievalAdapter | TestFabricRetrievalAdapter |
| IStateReadPort | Outbound | `ISessionStateReader` (5.1.1, `k1/fabric/ports/state_reader.py`) | SessionStateReadAdapter | TestStateReadAdapter |
| IBridgePort | Outbound | `IBridgePort` (5.1.3, `k1/fabric/ports/bridge_port.py`) | BridgeAdapter | TestBridgeAdapter |
| IDeltaEmitPort | Outbound | `IDeltaBusPort` (5.1.6, `k1/fabric/ports/delta_bus.py`) | DeltaBusAdapter | TestDeltaAdapter |
| IEventPort | In/Out | `IEventPort` (5.1.2, `k1/fabric/ports/event_port.py`) | EventBusAdapter | TestEventAdapter |

### 15.2 Port 1: IMailboxPort (Inbound)

The mailbox port is the Planner's sole inbound entry point.  Unlike the other
6 ports which are defined by the Planner as its own abstractions, this port's
protocol is defined on the **Orchestrator side** as a consumer-driven contract
(`IPlannerMailbox`).  The Planner module must expose an object satisfying it.

**Source**: `k1/orchestrator/adapters/planner_adapter.py` line 60

```python
class IPlannerMailbox(Protocol):
    """Structural protocol for the Planner's inbound mailbox."""

    async def enqueue(self, request: PlanRequest) -> None:
        """Enqueue a plan request for asynchronous processing.
        Raises on mailbox full (depth >= 5)."""

    async def send_cancel(self, request_id: str) -> None:
        """Signal cancellation for an in-flight plan request.
        Best-effort: plan may have already committed."""

    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan:
        """Synchronous micro-replan. Planner responds inline (10s budget).
        PlannerAdapter wraps this with asyncio.wait_for(timeout=10.0)."""
```

| Method | Direction | Return | Semantics | Notes |
| ------ | --------- | ------ | --------- | ----- |
| `enqueue(PlanRequest)` | In | `None` | Async, fire-and-forget | PlanAck constructed by PlannerAdapter (Orchestrator side), not by Planner |
| `send_cancel(request_id)` | In | `None` | Async, best-effort | Plan may have already committed; no effect post-COMMIT |
| `micro_replan(MicroReplanRequest)` | In | `CommittedPlan` | Sync (10s timeout) | Bypasses mailbox queue; PlannerAdapter wraps with `asyncio.wait_for(10.0)` |

**Key design decisions**:

- `enqueue()` returns `None`, not `PlanAck`.  The `PlannerAdapter` on the
  Orchestrator side constructs `PlanAck(ACCEPTED)` on successful enqueue and
  `PlanAck(REJECTED)` on failure/CB-open.
- `micro_replan()` returns `CommittedPlan` **directly** -- no event bus, no mailbox
  queuing.  This is the only synchronous request-response path in the Planner.
- `send_cancel()` is best-effort.  If the plan was already delivered via
  `k1.planner.plan.ready.v1`, the cancel has no effect.

**Mailbox properties** (from Section 4.1):

```text
 Type:           MPSC + FIFO (single priority class: INTERACTIVE)
 Max depth:      5 (rejects beyond -- PlanAck(REJECTED))
 Message types:  PlanRequest only (MicroReplanRequest bypasses queue)
 Consumer:       PlannerAgent (single, sequential -- V1 one plan at a time)
```

### 15.3 Port 2: ILLMPort (Outbound)

The LLM port is the Planner's sole exit point for all language model calls.
Three pipeline stages (SKETCH, EXPAND, VALIDATE) and two HIL prompt generators
route through this port.

**Source**: `planner.mmd` PORT_LLM definition

```text
 ILLMPort (Routes to Model Hub via LLM Request Bus)
   execute(HubRequest) -> HubResponse
```

| Method | Direction | Return | Semantics |
| ------ | --------- | ------ | --------- |
| `execute(HubRequest)` | Out | `HubResponse` | Async request-reply. Routes through LLM Request Bus to Model Hub. |

**HubRequest** envelope (constructed by Planner services):

```yaml
HubRequest:
  capability: CapabilityType             # CHAT or STRUCTURED (Planner uses only these 2)
  payload: CapabilityPayload             # ChatPayload or StructuredOutputPayload
    # ChatPayload:
    #   messages: List[ChatMessage]      # [{role: "system", content: ...}, {role: "user", content: ...}]
    #   temperature: float               # Stage-dependent: SKETCH 0.7, EXPAND 0.3, VALIDATE 0.2
    # StructuredOutputPayload:
    #   messages: List[ChatMessage]
    #   output_schema: Dict              # JSON Schema the response MUST conform to
    #   temperature: float
  constraints: RequestConstraints
    max_tokens: int                      # Per-stage budget (PLAN-11)
    timeout_ms: int                      # Per-stage timeout
    priority: str                        # "INTERACTIVE" for all Planner calls
    temperature: float                   # Overrides payload temperature if set
    consumer_id: str                     # "planner" -- for cost tracking (MH-11)
  trace_id: str                          # cognitive_trace_id for end-to-end tracing
```

**HubResponse** envelope (returned by Model Hub):

```yaml
HubResponse:
  result: CapabilityResult               # The LLM's response content
  metadata: ResponseMetadata
    request_id: str                      # Model Hub's internal request ID
    model_id: str                        # Which model was selected
    provider_id: str                     # Which provider served the request
    usage:                               # Token usage counters
      prompt_tokens: int
      completion_tokens: int
      total_tokens: int
    cost_usd: float                      # Actual cost for this call
    latency_ms: int                      # End-to-end latency (Hub perspective)
    cached: bool                         # Whether response was from prompt cache
    fallback_used: bool                  # Whether ModelSelector fell back (MH-06)
    fallback_reason: str | null          # Why fallback was needed
    circuit_breaker_state: str           # Provider CB state at call time
    retry_count: int                     # Number of retries within Hub
    rate_limited: bool                   # Whether rate limiting was applied
```

**Routing path** (from Section 13):

```text
 Service (Sketch|Expand|Validate|HILCoordinator)
   -> ILLMPort.execute(HubRequest)
      -> LLMGatewayAdapter
         -> LLM_REQUEST_BUS (async request-reply)
            -> Model Hub RequestRouter
               -> ModelSelector (5-dimension scoring)
               -> ProviderDispatcher -> Provider Plugin
            <- HubResponse
         <- HubResponse
      <- HubResponse
   <- HubResponse
```

**Budget enforcement** (PLAN-11):

Every `HubRequest` carries explicit `constraints.max_tokens` and
`constraints.timeout_ms`.  The Planner sets these; the Model Hub enforces them
(MH-04: no unbounded calls accepted, MH-08: per-provider timeout).  There is no
way to issue an unbounded LLM call through this port.

**Callers** (5 call sites mapped in Section 13.1 LLM Call Matrix):

| Call ID | Service | Capability | max_tokens | timeout_ms |
| ------- | ------- | ---------- | ---------- | ---------- |
| LLM-1 | SketchService | STRUCTURED | 2000 | 8000 |
| LLM-2 | ExpandService | STRUCTURED | 1000 | 5000 |
| LLM-3 | ValidateService | STRUCTURED | 500 | 3000 |
| LLM-C1 | HILCoordinator | CHAT | 300 | 3000 |
| LLM-A1 | HILCoordinator | CHAT | 400 | 3000 |

**Relationship to Fabric IModelGatewayPort (5.1.4)**:

The Planner's `ILLMPort` is NOT the same as the Fabric's `IModelGatewayPort`.
`IModelGatewayPort` provides `create_handle()` / `is_model_loaded()` /
`list_models()` / `find_model()` -- these are for the AgentFactory to grant LLM
handles to spawned agents.  The Planner does not spawn agents; it issues direct
`execute(HubRequest)` calls.  The two ports serve different consumers with
different calling patterns:

```text
 IModelGatewayPort (Fabric 5.1.4):     ILLMPort (Planner-specific):
   create_handle() -> ILLMHandle          execute(HubRequest) -> HubResponse
   is_model_loaded(model_id)              (no model selection API)
   list_models()                          (no handle concept)
   find_model(capabilities)               (no agent lifecycle)

 Consumer: AgentFactory                 Consumer: Planner pipeline services
 Pattern:  Handle-based, agent-scoped   Pattern:  One-shot request-reply
 Routing:  Direct to Model Hub          Routing:  Via LLM Request Bus
```

### 15.4 Port 3: IFabricRetrievalPort (Outbound)

The Fabric Retrieval port provides read-only access to the Capability Registry's
discovery and prompt retrieval API.  It is the Planner's window into "what can the
system do?" without being able to execute anything (PLAN-06).

**Source**: `planner.mmd` PORT_FABRIC_RETRIEVAL definition

```text
 IFabricRetrievalPort
   discover_capabilities(query) -> RetrievalResult[]
   find_relevant_prompts(query) -> RetrievalResult[]
   Read-only Fabric Retrieval API access
```

| Method | Direction | Return | Semantics |
| ------ | --------- | ------ | --------- |
| `discover_capabilities(domain, intent, safety_band, session_context, top_k)` | Out | `RetrievalResult` | Ranked capability discovery (HardFilter + SoftRank + TopK) |
| `find_relevant_prompts(intent, domain, safety_band, top_k)` | Out | `RetrievalResult` | Same pipeline filtered to prompt-type contracts |

**discover_capabilities()** full signature (from `k1/fabric/fabric.py` FabricRetrieval):

```python
async def discover_capabilities(
    self,
    domain: Optional[List[str]] = None,    # Domain tag filter(s)
    intent: str = "",                       # Natural-language description
    safety_band: str = "GREEN",             # Caller's effective safety band
    session_context: Optional[Dict[str, Any]] = None,  # Available session keys
    top_k: int = 10,                        # Number of results (max 25)
) -> RetrievalResult:
    """4-stage pipeline: Embed -> HardFilter -> SoftRank -> TopK"""
```

**find_relevant_prompts()** full signature:

```python
async def find_relevant_prompts(
    self,
    intent: str = "",
    domain: Optional[List[str]] = None,
    safety_band: str = "GREEN",
    top_k: int = 10,
) -> RetrievalResult:
    """Same pipeline, filtered to prompt-type contracts only."""
```

**Callers** (5 tool calls, budget PLAN-05: max 6 per plan):

| Tool | Stage | Arguments | Latency |
| ---- | ----- | --------- | ------- |
| `discover_capabilities()` | SKETCH | `domain` from control, `intent` from PlanRequest, `safety_band` from control | <50ms |
| `discover_capabilities()` | EXPAND (refined) | `intent` per-step refined, `safety_band` from control | <50ms |
| `find_relevant_prompts()` | EXPAND | `intent` per-step, `domain` from control | <50ms |

**PLAN-06 enforcement**:

The `FabricRetrieval` class wraps the `RetrievalEngine` and exposes only
`discover_capabilities()` and `find_relevant_prompts()`.  It has no
`invoke_capability()` or `execute()` method.  A developer cannot accidentally
execute a capability through this port because no execution path exists on the
interface.  This mirrors the PLAN-01 enforcement pattern (no write method exists
on `IStateReadPort`).

**Relationship to Fabric API surface**:

`FabricRetrieval` is one of 3 API objects exposed by the Fabric (Role 1: Discovery,
Role 2: Execution, Role 3: Registry Management).  The Planner touches Role 1 only.
The Orchestrator touches Role 1 + Role 2.  Role 3 is administrative.

### 15.5 Port 4: IStateReadPort (Outbound, Read-Only)

The SessionState read port provides multi-reader, lock-free access to SessionState
sections.  This is the Planner's primary context window during planning.

**Source**: `planner.mmd` PORT_STATE_READ definition

```text
 IStateReadPort
   read_sections(sections[]) -> StateSnapshot
   Multi-reader, lock-free (PLAN-01)
   Sections: beliefs, persona, control, temporal
```

**Underlying protocol**: `ISessionStateReader` (`k1/fabric/ports/state_reader.py`)

| Method | Direction | Return | Semantics |
| ------ | --------- | ------ | --------- |
| `read_section(session_id, section)` | Out | `Optional[Dict[str, Any]]` | Single section read; `None` if unavailable |
| `read_sections(session_id, names)` | Out | `Dict[str, Any]` | Multi-section batch read; missing sections omitted |
| `get_snapshot(session_id)` | Out | `SessionSnapshot` | Atomic capture of all available sections |

**SessionSnapshot** type (frozen dataclass):

```yaml
SessionSnapshot:
  session_id: str                         # Active session identifier
  sections: Dict[str, Dict[str, Any]]     # Section name -> section data
  timestamp_ms: int                       # Capture timestamp (epoch ms)
  section_names: List[str]                # Available section names at capture time
```

**Caller**: `query_planning_context()` via ToolCallRouter (Section 11.3)

```text
 Canonical read set (SKETCH):  ["beliefs_active", "control", "history_recent"]

 The adapter wraps ISessionStateReader.read_sections() and returns the
 sections dict.  Section 14 details the full 12-section catalog,
 per-section data contents, and freshness protocol.
```

**PLAN-01 enforcement**:

`ISessionStateReader` has no write method.  The protocol defines exactly 3 methods:
`read_section()`, `read_sections()`, `get_snapshot()`.  A developer cannot write to
SessionState through this port because no write path exists on the interface.

**Thread safety**: Multi-reader lock-free.  Concurrent calls from Planner pipeline
and other K1 modules are safe without external synchronization.

### 15.6 Port 5: IBridgePort (Outbound)

The Bridge port provides bidirectional access to K0 via the Cross-Kernel Bridge.
The Planner uses it for two operations: reading long-term memory (recall) and
persisting committed plans (WAL write).

**Source**: `planner.mmd` PORT_BRIDGE definition

```text
 IBridgePort
   recall(query, selectors[]) -> RecallResponse
   persist_plan(CommittedPlan) -> void
   K0 read path + WAL write path
```

**Underlying protocol**: `IBridgePort` (`k1/fabric/ports/bridge_port.py`)

The Fabric's IBridgePort is a general-purpose K0 access interface with 5 methods.
The Planner's BridgeAdapter wraps only the subset the Planner needs:

| Fabric IBridgePort Method | Planner Usage | Planner Wrapper |
| ------------------------- | ------------- | --------------- |
| `query(operation, selectors)` | `memory.recall` | `recall(query, selectors)` -> uses `query("memory.recall", ...)` |
| `send_command(operation, payload)` | `persist_plan` | `persist_plan(committed_plan)` -> uses `send_command("memory.store", ...)` |
| `route_ifl(route, payload)` | Not used | Planner never executes tools via IFL (PLAN-06) |
| `is_available()` | Health check | Used for degraded-mode decisions |
| `get_health()` | Not used directly | Adapter may log health for observability |

**Recall** (read path, used by `recall_for_planning()` tool in SKETCH):

```text
 ToolCallRouter.recall_for_planning(query):
   |-- adapter.recall(query, selectors=["preferences", "outcomes", "constraints"])
   |     -> IBridgePort.query("memory.recall", {query, selectors})
   |     -> BridgeCommandResult
   |          success: true, data: {facts: [...], scores: [...]}
   |     -> Adapter extracts .data, returns to ToolCallRouter
   |
   Latency: <100ms (K0 in-process bridge, FAISS index lookup)
```

**Persist** (write path, used by CommitService in Stage 4 COMMIT):

```text
 CommitService.execute():
   |-- adapter.persist_plan(committed_plan)
   |     -> IBridgePort.send_command("memory.store", committed_plan.to_dict())
   |     -> BridgeCommandResult
   |          success: true (or false -- fire-and-forget, log on failure)
   |
   Fire-and-forget: CommitService does NOT wait for confirmation.
   WAL write is best-effort.  If K0 is offline, the plan is still
   delivered via IEventPort (the plan.ready event is the primary delivery).
```

**Offline handling**:

When `is_available()` returns `False` (K0 offline):

- `recall()` returns empty result (no long-term memory context)
- `persist_plan()` silently drops (plan still delivered via event bus)
- Planning quality degrades (no historical context) but does NOT fail

**BridgeCommandResult** type (from `k1/fabric/ports/bridge_port.py`):

```yaml
BridgeCommandResult:
  success: bool                          # Whether the command succeeded
  data: Dict[str, Any]                   # Response payload (empty on failure)
  error_code: str                        # Machine-readable error code
  error_message: str                     # Human-readable error message
  k0_mode: str                           # K0 health mode at response time
  latency_ms: int                        # Round-trip latency
  trace_id: str                          # Echoed for correlation
```

### 15.7 Port 6: IDeltaEmitPort (Outbound, Fire-and-Forget)

The delta emission port broadcasts planning progress to the Delta Bus.  Every
stage transition, tool call result, and plan outcome generates a delta event.

**Source**: `planner.mmd` PORT_DELTA definition

```text
 IDeltaEmitPort
   emit(delta) -> void (fire-and-forget)
   All planning deltas: k1.planner.delta.v1
   NEVER writes SessionState directly
```

**Underlying protocol**: `IDeltaBusPort` (`k1/fabric/ports/delta_bus.py`)

| Method | Direction | Return | Semantics |
| ------ | --------- | ------ | --------- |
| `emit_delta(agent_id, delta_type, section, data)` | Out | `None` | Fire-and-forget; MUST NOT block; thread-safe |

**DeltaPayload** type (frozen dataclass):

```yaml
DeltaPayload:
  agent_id: str                          # "planner" for all Planner deltas
  delta_type: str                        # e.g., "stage_transition", "plan_update", "tool_result"
  section: str                           # e.g., "plan", "pipeline", "tools"
  data: Dict[str, Any]                   # Arbitrary delta payload
  trace_id: str                          # cognitive_trace_id (observability)
```

**Emission points** (PipelineController is the sole emitter):

| When | delta_type | section | data contents |
| ---- | ---------- | ------- | ------------- |
| Stage start | `"stage_transition"` | `"pipeline"` | `{stage: "SKETCH", status: "started", timestamp_ms}` |
| Stage complete | `"stage_transition"` | `"pipeline"` | `{stage: "SKETCH", status: "completed", tokens_used, latency_ms}` |
| Tool call result | `"tool_result"` | `"tools"` | `{tool: "discover_capabilities", result_count, latency_ms}` |
| Plan ready | `"plan_update"` | `"plan"` | `{plan_id, step_count, status: "committed"}` |
| Plan failed | `"plan_update"` | `"plan"` | `{request_id, stage, reason, status: "failed"}` |

**Fire-and-forget contract**:

`emit_delta()` is synchronous and MUST NOT block.  The bus adapter is responsible
for internal buffering or async dispatch.  If the bus is unavailable, the adapter
logs the failure and drops the delta.  Delta loss is acceptable -- these are
observability signals, not control-plane messages.

**PLAN-01 emphasis**: Delta emission is NOT a SessionState write.  Deltas go to the
Delta Bus (`k1.planner.delta.v1` topic), which is a separate pub/sub channel.
SessionState consumers may subscribe to deltas and incorporate them, but the
Planner has no knowledge of or dependency on this.

### 15.8 Port 7: IEventPort (Inbound + Outbound)

The event port is the only **bidirectional** port on the Planner.  It publishes
plan lifecycle events and subscribes to inbound control events and HIL responses.

**Source**: `planner.mmd` PORT_EVENT definition

```text
 IEventPort
   publish(topic, payload) -> void
   subscribe(topic, handler) -> Subscription
   Pub: plan.ready, plan.failed, plan.cancelled
   Sub: plan.request, plan.cancel,
        k1.hil.clarification_response.v1,
        k1.hil.approval_response.v1
```

**Underlying protocol**: `IEventPort` (`k1/fabric/ports/event_port.py`)

| Method | Direction | Return | Semantics |
| ------ | --------- | ------ | --------- |
| `emit(topic, payload)` | Out | `None` | Fire-and-forget; MUST NOT raise even if no subscribers |
| `subscribe(topic, handler)` | In | `SubscriptionHandle` | Register callback for topic; handler called synchronously during emit |
| `unsubscribe(handle)` | -- | `bool` | Remove subscription; returns `True` if removed |

**Published topics** (outbound):

| Topic | Emitter | Payload | When |
| ----- | ------- | ------- | ---- |
| `k1.planner.plan.ready.v1` | CommitService (Stage 4) | `CommittedPlan` serialized | Plan committed, WAL persisted |
| `k1.planner.plan.failed.v1` | PipelineController | `{request_id, reason, stage, trace_id}` | Pipeline failed at any stage |
| `k1.planner.plan.cancelled.v1` | PipelineController | `{request_id, reason, trace_id}` | Cancel received and honored |
| `k1.hil.clarification.v1` | HILCoordinator | `{request_id, question, context, trace_id}` | SKETCH needs user clarification |
| `k1.hil.approval_request.v1` | HILCoordinator | `{request_id, summary, options, side_effects, safety_assessment}` | VALIDATE needs user approval |

**Subscribed topics** (inbound):

| Topic | Subscriber | Handler | Response To |
| ----- | ---------- | ------- | ----------- |
| `k1.hil.clarification_response.v1` | HILCoordinator | Correlate by `request_id`, unblock SKETCH | User's answer to clarification |
| `k1.hil.approval_response.v1` | HILCoordinator | Correlate by `request_id`, unblock VALIDATE | User's approve/modify/reject |

**Subscription lifecycle**:

```text
 INIT phase:
   handler_clarification = subscribe("k1.hil.clarification_response.v1", on_clarification)
   handler_approval = subscribe("k1.hil.approval_response.v1", on_approval)

 SHUTDOWN phase:
   unsubscribe(handler_clarification)
   unsubscribe(handler_approval)
```

**Event correlation**:

Every published payload MUST carry `trace_id` (cognitive_trace_id for FAB-09
compliance).  HIL events MUST carry `request_id` for correlation with
PENDING_CLARIFICATIONS in the Concierge (Section 12.4).

**Note on plan.request / plan.cancel**:

The planner.mmd lists `plan.request` and `plan.cancel` as subscribed topics.
In the V1 architecture these are handled by the mailbox path (PlannerAdapter
-> IPlannerMailbox.enqueue / send_cancel), not by direct event subscription.
Event-driven plan request is a V2 path for decoupled orchestration.

### 15.9 Port Mapping: Planner Names vs Fabric Names

The Planner defines its own port names to establish a clean hexagonal boundary.
Some ports directly wrap a Fabric port interface; others are Planner-specific
abstractions that have no Fabric equivalent.

| Planner Port | Fabric Port | Relationship | Why Different? |
| ------------ | ----------- | ------------ | -------------- |
| IMailboxPort | `IPlannerMailbox` (Orchestrator-defined) | Consumer-driven contract | Orchestrator defines what it needs; Planner satisfies |
| ILLMPort | `IModelHubPort` (Model Hub) | Planner-specific wrapper | Planner uses `execute(HubRequest)`, not `create_handle()` / agent lifecycle |
| IFabricRetrievalPort | `FabricRetrieval` class (Fabric Role 1) | Direct method-call wrapper | Fabric exposes 3 roles; Planner touches Role 1 only |
| IStateReadPort | `ISessionStateReader` (5.1.1) | Thin wrapper, same methods | Port name reflects Planner's perspective (read only, no write) |
| IBridgePort | `IBridgePort` (5.1.3) | Subset wrapper | Planner uses `recall()` + `persist_plan()`, not `route_ifl()` |
| IDeltaEmitPort | `IDeltaBusPort` (5.1.6) | Thin wrapper, same methods | Port name emphasizes fire-and-forget, no-read semantics |
| IEventPort | `IEventPort` (5.1.2) | Thin wrapper, same methods | Identical interface; Planner configures topics at subscription time |

### 15.10 Port Dependency Matrix by Service

Each internal service receives only the ports it needs.  No service has access to
all 7 ports.  This follows the principle of least privilege.

| Service | Mailbox | LLM | FabricRetrieval | StateRead | Bridge | DeltaEmit | Event |
| ------- | ------- | --- | --------------- | --------- | ------ | --------- | ----- |
| PipelineController | **Yes** (dequeue) | No | No | No | No | **Yes** (stage deltas) | **Yes** (plan lifecycle) |
| SketchService | No | **Yes** | No (via ToolCallRouter) | No (via ToolCallRouter) | No (via ToolCallRouter) | No | No |
| ExpandService | No | **Yes** | No (via ToolCallRouter) | No | No | No | No |
| ValidateService | No | **Yes** | **Yes** (capability existence) | No | No | No | No |
| CommitService | No | **No** (PLAN-03) | No | No | **Yes** (persist) | **Yes** | **Yes** (plan.ready) |
| ToolCallRouter | No | No | **Yes** | **Yes** | **Yes** (recall) | No | No |
| HILCoordinator | No | **Yes** (question/summary gen) | No | No | No | No | **Yes** (HIL pub/sub) |

**Reading the table**:

- "**Yes**" = Service receives this port at construction.
- "No" = Service does not receive this port.
- "No (via ToolCallRouter)" = Service accesses the backend indirectly through
  ToolCallRouter, which holds the port.  The service itself has no port reference.

**Invariant enforcement through construction**:

- CommitService has **No** ILLMPort -> PLAN-03 (deterministic commit) enforced
  at the constructor level.  Even if a developer modifies CommitService internals,
  they cannot issue an LLM call because the port is not available.
- SketchService / ExpandService access Fabric Retrieval / SessionState / Bridge
  only through ToolCallRouter, which enforces PLAN-05 (max 6 tool calls) and
  PLAN-02 (read-only tools).
- No service receives a SessionState write port -> PLAN-01 enforced globally.
- No service receives a capability execution port -> PLAN-06 enforced globally.

### 15.11 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| Mailbox protocol and design | 4.1, 4.2, 4.3 | Full mailbox specification, IPlannerMailbox, PlannerAdapter |
| Two-phase plan delivery | 4.4 | How IMailboxPort + IEventPort combine for request/response |
| Message envelopes | 4.5 | PlanRequest, MicroReplanRequest, PlanAck, CommittedPlan schemas |
| LLM Call Matrix | 13.1 | All 5 LLM call sites with budget/capability per call |
| HubRequest/HubResponse protocol | 13.2 | Envelope structure, payload types, constraints fields |
| Budget enforcement (PLAN-11) | 13.3 | PipelineController budget injection and Model Hub enforcement |
| Model selection boundary | 13.4 | What Planner controls vs what Model Hub decides |
| Discovery tools specification | 11.1-11.4 | Tool signatures, routing through IFabricRetrievalPort, IStateReadPort, IBridgePort |
| Tool call routing | 11.5 | ToolCallRouter dispatch, PLAN-05 counter |
| SessionState access (PLAN-01) | 14.1-14.3 | Reader-never-writer, section catalog, context flow |
| Snapshot freshness | 14.4 | Two-snapshot model, staleness impact |
| HIL event flow | 12.2-12.3 | IEventPort topics for clarification and approval |
| Concierge correlation | 12.4 | PENDING_CLARIFICATIONS map for HIL request-response |
| Adapter specifications | 16 | Production and test adapter implementations for all 7 ports |

---

## 16. Adapter Specifications (14 Total: 7 Production + 7 Test)

Each port (Section 15) has exactly one production adapter and one test adapter.
Adapters are the only code that touches infrastructure.  The Planner's services
never import an adapter -- they receive port-typed objects via constructor injection.

### 16.1 Production Adapters (7)

Production adapters bridge Planner ports to real K1/K0 infrastructure.  They are
wired at kernel boot time by the DI container.

#### 16.1.1 MailboxAdapter

**Port**: IMailboxPort (Section 15.2)

```text
 Constructor:
   MailboxAdapter(max_depth: int = 5, priority_class: str = "INTERACTIVE")

 Behavior:
   - In-memory MPSC queue with FIFO dequeue semantics
   - Single priority class (INTERACTIVE) -- no WFQ weighting
   - Rejects with MailboxFullError when depth >= max_depth
   - MicroReplanRequest bypasses queue (direct method call via micro_replan())

 Internal state:
   _queue: asyncio.Queue[PlanRequest]     -- bounded at max_depth
   _cancel_set: Set[str]                  -- request_ids pending cancellation
   _plan_lock: asyncio.Lock               -- V1 single-plan guard

 Thread safety:
   enqueue() is safe for concurrent callers (asyncio.Queue is task-safe)
   dequeue() is called from PlannerAgent's single mailbox loop
   micro_replan() acquires _plan_lock (waits for current plan to complete)
```

| Method | Implementation |
| ------ | -------------- |
| `enqueue(PlanRequest)` | `_queue.put_nowait()`, raises `MailboxFullError` if full |
| `send_cancel(request_id)` | Adds to `_cancel_set`; PlannerAgent checks set between stages |
| `micro_replan(MicroReplanRequest)` | Acquires `_plan_lock`, delegates to PipelineController, returns `CommittedPlan` |

#### 16.1.2 LLMGatewayAdapter

**Port**: ILLMPort (Section 15.3)

```text
 Constructor:
   LLMGatewayAdapter(
     llm_request_bus: ILLMRequestBus,     -- Async request-reply channel to Model Hub
     consumer_id: str = "planner",        -- Cost tracking label (MH-11)
   )

 Behavior:
   - Wraps IModelHubPort.execute(HubRequest) -> HubResponse
   - Routes via LLM_REQUEST_BUS (async request-reply, not direct method call)
   - Stamps every HubRequest.constraints.consumer_id = "planner" for cost attribution
   - Does NOT select models -- Model Hub's ModelSelector chooses (Section 13.4)
   - Inherits per-provider circuit breaker protection (MH-05) from Model Hub

 V1 NOTE:
   V1 runs TestLLMAdapter in all environments (deterministic, per-stage canned
   responses).  LLMGatewayAdapter is the V2 production path when Model Hub is live.

 Error handling:
   - Model Hub timeout: raises LLMTimeoutError after constraints.timeout_ms
   - Model Hub rejection (budget exceeded MH-04): raises BudgetExceededError
   - Provider CB OPEN: Model Hub handles fallback internally (MH-06)
   - Network / bus failure: raises AdapterException(DEGRADED)
```

| Method | Implementation |
| ------ | -------------- |
| `execute(HubRequest)` | Stamp `consumer_id`, send via `_bus.request(hub_request)`, await `HubResponse` |

#### 16.1.3 FabricRetrievalAdapter

**Port**: IFabricRetrievalPort (Section 15.4)

```text
 Constructor:
   FabricRetrievalAdapter(
     fabric_retrieval: FabricRetrieval,    -- Direct reference to FabricRetrieval API object
     timeout_ms: int = 50,                -- Per-call timeout
     max_retries: int = 1,                -- Retry count on failure
   )

 Behavior:
   - In-process method call (NOT HTTP, NOT event-based)
   - Same Python runtime as Fabric -- direct object reference
   - Wraps FabricRetrieval.discover_capabilities() and find_relevant_prompts()
   - Returns RetrievalResult (Top-K scored capabilities)
   - Timeout: 50ms per call, retry once on failure
   - No circuit breaker (in-process call, failure means Fabric itself is broken)

 Error handling:
   - Timeout: return empty RetrievalResult (degraded, not fatal)
   - Exception: log and return empty RetrievalResult
   - Fabric unhealthy: discover_capabilities returns 0 results
```

| Method | Implementation |
| ------ | -------------- |
| `discover_capabilities(domain, intent, safety_band, session_context, top_k)` | `asyncio.wait_for(_fabric.discover_capabilities(...), timeout=_timeout_ms/1000)` |
| `find_relevant_prompts(intent, domain, safety_band, top_k)` | `asyncio.wait_for(_fabric.find_relevant_prompts(...), timeout=_timeout_ms/1000)` |

#### 16.1.4 SessionStateReadAdapter

**Port**: IStateReadPort (Section 15.5)

```text
 Constructor:
   SessionStateReadAdapter(
     reader: ISessionStateReader,         -- Fabric port 5.1.1
     session_id: str,                     -- Bound at construction (one adapter per session)
   )

 Behavior:
   - Wraps ISessionStateReader.read_sections() with pre-bound session_id
   - Multi-reader lock-free (ISessionStateReader guarantees thread safety)
   - No write capability (PLAN-01 enforced at type level -- no write method exists)
   - Reads HOT CORE + WARM sections (FlatBuffer-backed, <100us serialization)

 Error handling:
   - SessionState unavailable: return empty Dict (ToolCallRouter degrades gracefully)
   - Individual section missing: omitted from result dict (not None-valued)
```

| Method | Implementation |
| ------ | -------------- |
| `read_sections(sections)` | `_reader.read_sections(_session_id, sections)` |
| `get_snapshot()` | `_reader.get_snapshot(_session_id)` |

#### 16.1.5 BridgeAdapter

**Port**: IBridgePort (Section 15.6)

```text
 Constructor:
   BridgeAdapter(
     bridge_port: IBridgePort,            -- Fabric port 5.1.3 (K0 Bridge client)
   )

 Behavior:
   - Wraps IBridgePort.query() for recall and IBridgePort.send_command() for persist
   - recall(query, selectors) -> calls bridge.query("memory.recall", {...})
   - persist_plan(committed_plan) -> calls bridge.send_command("memory.store", plan.to_dict())
   - persist is fire-and-forget: does NOT wait for confirmation
   - Offline handling: if bridge.is_available() == False, recall returns empty, persist drops

 Error handling:
   - K0 offline: recall returns empty BridgeCommandResult, persist silently drops
   - K0 degraded: recall may be slow (extended timeout), persist still fire-and-forget
   - Exception: catch, log, return empty result (planning degrades, does not fail)
```

| Method | Implementation |
| ------ | -------------- |
| `recall(query, selectors)` | `_bridge.query("memory.recall", {query, selectors})` -> extract `.data` |
| `persist_plan(committed_plan)` | `_bridge.send_command("memory.store", committed_plan.to_dict())` -- fire-and-forget |
| `is_available()` | `_bridge.is_available()` |

#### 16.1.6 DeltaBusAdapter

**Port**: IDeltaEmitPort (Section 15.7)

```text
 Constructor:
   DeltaBusAdapter(
     delta_bus: IDeltaBusPort,            -- Fabric port 5.1.6
     agent_id: str = "planner",           -- All Planner deltas tagged with this ID
   )

 Behavior:
   - Wraps IDeltaBusPort.emit_delta() with pre-bound agent_id
   - Publishes to topic: k1.planner.delta.v1
   - Fire-and-forget: MUST NOT block, MUST NOT raise
   - Thread-safe (IDeltaBusPort guarantees concurrent call safety)

 Error handling:
   - Bus unavailable: log warning, drop delta (observability loss, not functional)
   - Exception: catch and log (never propagate -- delta loss is acceptable)
```

| Method | Implementation |
| ------ | -------------- |
| `emit(delta_type, section, data, trace_id)` | `_bus.emit_delta(_agent_id, delta_type, section, data)` |

#### 16.1.7 EventBusAdapter

**Port**: IEventPort (Section 15.8)

```text
 Constructor:
   EventBusAdapter(
     event_port: IEventPort,              -- Fabric port 5.1.2
   )

 Behavior:
   - Wraps IEventPort.emit() for publishing and IEventPort.subscribe() for listening
   - Published topics: k1.planner.plan.ready.v1, plan.failed.v1, plan.cancelled.v1,
     k1.hil.clarification.v1, k1.hil.approval_request.v1
   - Subscribed topics: k1.hil.clarification_response.v1, k1.hil.approval_response.v1
   - FAB-09: all payloads MUST carry cognitive_trace_id

 Error handling:
   - Emit failure: log and continue (fire-and-forget for lifecycle events)
   - Subscription failure: re-subscribe with backoff (HIL responses are critical)
   - Handler exception: IEventPort catches and logs (does not propagate to other handlers)
```

| Method | Implementation |
| ------ | -------------- |
| `publish(topic, payload)` | `_event_port.emit(topic, payload)` |
| `subscribe(topic, handler)` | `_event_port.subscribe(topic, handler)` -> `SubscriptionHandle` |
| `unsubscribe(handle)` | `_event_port.unsubscribe(handle)` |

### 16.2 Test Adapters (7)

Test adapters are in-memory implementations that replace infrastructure with
injectable, assertable, deterministic behavior.  Every test adapter follows the
same design pattern:

1. **Constructor injection** -- receive preset data or behavior configuration
2. **Capture mode** -- record all calls for post-test assertion
3. **No I/O** -- purely in-memory, zero external dependencies
4. **Protocol compliance** -- structurally compatible with production port protocol

#### 16.2.1 TestMailboxAdapter

**Port**: IMailboxPort

```text
 TestMailboxAdapter(preset_requests: List[PlanRequest] = [])

 Features:
   - Pre-loaded queue: tests inject PlanRequest(s) at construction
   - Capture: records all enqueue/cancel/micro_replan calls
   - Assertions: test verifies dequeue order, cancel handling, micro_replan routing
   - No async I/O: synchronous queue operations for deterministic test execution

 Test patterns:
   - Empty mailbox: verify PlannerAgent waits correctly
   - Single request: verify full pipeline end-to-end
   - Multiple requests: verify FIFO ordering
   - Overflow: verify rejection at depth > 5
   - Cancel during plan: verify inter-stage cancel check
```

#### 16.2.2 TestLLMAdapter

**Port**: ILLMPort

```text
 TestLLMAdapter(
   stage_responses: Dict[str, HubResponse] = {},   -- Keyed by stage name
   error_stages: Set[str] = {},                     -- Stages that should fail
   latency_ms: int = 0,                             -- Simulated latency (asyncio.sleep)
 )

 Features:
   - Per-stage configurable responses: SKETCH returns X, EXPAND returns Y, etc.
   - Deterministic: same input always produces same output (no LLM randomness)
   - Error injection: configure specific stages to fail (timeout / error response)
   - Capture: records all HubRequest(s) for assertion (verify budget, capability, prompt)
   - Token counting: returns pre-configured usage in ResponseMetadata

 Test patterns:
   - Happy path: all stages return valid responses
   - Partial failure: SKETCH succeeds, EXPAND fails -> verify fallback
   - Budget assertion: verify constraints.max_tokens matches PLAN-11 budget
   - Prompt assertion: verify prompt slot composition (no hardcoded text)
   - Schema assertion: verify HubRequest.payload.output_schema matches stage contract
```

#### 16.2.3 TestFabricRetrievalAdapter

**Port**: IFabricRetrievalPort

```text
 TestFabricRetrievalAdapter(
   preset_capabilities: List[ScoredCapability] = [],
   preset_prompts: List[ScoredCapability] = [],
 )

 Features:
   - Preset discovery results: tests inject known capabilities
   - Capture: records all discover_capabilities() and find_relevant_prompts() calls
   - Empty results: return empty list to test degraded paths
   - Assertions: verify safety_band passed correctly, domain filter applied

 Test patterns:
   - Rich discovery: 10+ capabilities for SKETCH to choose from
   - Empty discovery: zero results -> verify SKETCH still produces a plan
   - Filtered results: verify safety_band filtering is requested
```

#### 16.2.4 TestStateReadAdapter

**Port**: IStateReadPort

```text
 TestStateReadAdapter(
   preset_snapshot: SessionSnapshot = SessionSnapshot(),
   preset_sections: Dict[str, Dict[str, Any]] = {},
 )

 Features:
   - In-memory SessionSnapshot: tests inject known beliefs, persona, control, etc.
   - Capture: records all read_sections() and get_snapshot() calls
   - Empty state: return empty sections to test degraded paths
   - Assertions: verify correct sections requested per stage

 Test patterns:
   - Full context: all 3 canonical sections populated
   - Partial context: beliefs only, no persona -> verify graceful degradation
   - Empty context: no sections -> verify SESSION_CONTEXT slot renders fallback message
```

#### 16.2.5 TestBridgeAdapter

**Port**: IBridgePort

```text
 TestBridgeAdapter(
   preset_recall: Dict[str, Any] = {},    -- Recall results to return
   persist_capture: List[Dict] = [],      -- Captures all persist_plan() calls
   available: bool = True,                -- Simulate online/offline
 )

 Features:
   - Preset recall: inject known long-term memory results
   - Persist capture: record all committed plans for assertion (verify plan_id, steps)
   - Offline mode: set available=False to simulate K0 offline
   - Assertions: verify recall query structure, persist payload correctness

 Test patterns:
   - K0 online: recall returns facts, persist succeeds -> verify full path
   - K0 offline: recall empty, persist drops -> verify degraded path
   - Persist assertion: verify CommittedPlan structure matches contract
```

#### 16.2.6 TestDeltaAdapter

**Port**: IDeltaEmitPort

```text
 TestDeltaAdapter(capture: List[DeltaPayload] = [])

 Features:
   - Captures all emitted deltas in order
   - Assertions: verify delta_type, section, data contents per stage
   - Count assertions: verify correct number of deltas per pipeline run
   - No side effects: purely in-memory collection

 Test patterns:
   - Full pipeline: verify 4+ stage_transition deltas (SKETCH, EXPAND, VALIDATE, COMMIT)
   - Failed pipeline: verify partial deltas + failure delta
   - Micro-replan: verify MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE deltas
   - LLM call deltas: verify llm_call_complete deltas with token counts
```

#### 16.2.7 TestEventAdapter

**Port**: IEventPort

```text
 TestEventAdapter(capture: List[Tuple[str, Dict]] = [])

 Features:
   - Captures all published events (topic + payload) in order
   - Injectable handlers: test can register handlers that fire on subscribe()
   - Simulate inbound events: test calls emit() to simulate HIL responses
   - Assertions: verify topic names, payload schemas, trace_id presence

 Test patterns:
   - Plan success: verify k1.planner.plan.ready.v1 emitted with CommittedPlan
   - Plan failure: verify k1.planner.plan.failed.v1 emitted with error details
   - HIL flow: inject clarification_response.v1, verify SKETCH resumes
   - HIL flow: inject approval_response.v1 with "modify", verify re-validation
   - Cancellation: verify k1.planner.plan.cancelled.v1 emitted
```

### 16.3 Adapter Wiring (Port -> Adapter -> Infrastructure)

Each port is wired to exactly one adapter at construction time.  The wiring is
1:1 -- there is no adapter multiplexing or dynamic switching.

```text
 Production wiring (kernel boot):

   PORT_MAILBOX         -->  MailboxAdapter           --> in-process asyncio.Queue
   PORT_LLM             -->  LLMGatewayAdapter        --> LLM_REQUEST_BUS --> Model Hub
   PORT_FABRIC_RETRIEVAL -->  FabricRetrievalAdapter   --> FabricRetrieval API (in-process)
   PORT_STATE_READ      -->  SessionStateReadAdapter   --> ISessionStateReader (in-process)
   PORT_BRIDGE           -->  BridgeAdapter             --> IBridgePort --> K0 Bridge
   PORT_DELTA            -->  DeltaBusAdapter           --> IDeltaBusPort --> Delta Bus
   PORT_EVENT            -->  EventBusAdapter           --> IEventPort --> K1 Event Bus

 Test wiring (test fixture):

   PORT_MAILBOX         -->  TestMailboxAdapter        --> in-memory queue
   PORT_LLM             -->  TestLLMAdapter             --> deterministic responses
   PORT_FABRIC_RETRIEVAL -->  TestFabricRetrievalAdapter --> preset capabilities
   PORT_STATE_READ      -->  TestStateReadAdapter       --> in-memory snapshot
   PORT_BRIDGE           -->  TestBridgeAdapter          --> in-memory recall + capture
   PORT_DELTA            -->  TestDeltaAdapter           --> capture list
   PORT_EVENT            -->  TestEventAdapter           --> capture list + injectable handlers
```

### 16.4 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| Port specifications (7 ports) | 15.2-15.8 | Port protocol that each adapter implements |
| Port-to-service dependency matrix | 15.10 | Which services receive which ports (least privilege) |
| Port mapping: Planner vs Fabric names | 15.9 | How adapter wraps Fabric port |
| IPlannerMailbox protocol | 4.2 | Consumer-driven contract that MailboxAdapter satisfies |
| PlannerAdapter (Orchestrator side) | 4.3 | CB_PLANNER wrapper around IPlannerMailbox |
| HubRequest/HubResponse envelope | 13.2 | What LLMGatewayAdapter sends/receives |
| Budget enforcement (PLAN-11) | 13.3 | PipelineController injects, Model Hub enforces |
| FabricRetrieval API | `k1/fabric/fabric.py` line 1088 | discover_capabilities() + find_relevant_prompts() signatures |
| ISessionStateReader protocol | `k1/fabric/ports/state_reader.py` | read_section(), read_sections(), get_snapshot() |
| IBridgePort protocol | `k1/fabric/ports/bridge_port.py` | send_command(), query(), route_ifl() |
| IDeltaBusPort protocol | `k1/fabric/ports/delta_bus.py` | emit_delta() signature |
| IEventPort protocol | `k1/fabric/ports/event_port.py` | emit(), subscribe(), unsubscribe() |

---

## 17. Internal Services (~335 Tests)

7 services with no circular dependencies.  Each service receives ports and
peer services via constructor injection.  This section provides an architectural
summary -- detailed stage behavior, prompt composition, and error recovery are
in the deep-dive sections referenced below.

### 17.1 Service Dependency Graph

```text
PipelineController
  |-- SketchService    -> ToolCallRouter, HILCoordinator
  |-- ExpandService    -> ToolCallRouter
  |-- ValidateService  -> HILCoordinator
  |-- CommitService    (no service deps)

ToolCallRouter (shared by SketchService, ExpandService)
HILCoordinator (shared by SketchService, ValidateService)
```

No circular dependencies.  PipelineController sits at the top; ToolCallRouter and
HILCoordinator are leaf services shared by stage services.

### 17.2 PipelineController (~80 tests)

**Role**: Top-level pipeline orchestrator.  Owns stage sequencing, budget injection,
state machine transitions, cancel checking between stages, and micro-replan
abbreviated-mode routing.

```text
 Constructor:
   PipelineController(
     sketch:     SketchService,
     expand:     ExpandService,
     validate:   ValidateService,
     commit:     CommitService,
     delta_port: IDeltaEmitPort,
     event_port: IEventPort,
   )
```

**Ports used (direct)**: IDeltaEmitPort, IEventPort

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-03 | CommitService is last stage; no LLM call in commit path |
| PLAN-04 | Checks `_cancel_set` between every stage transition |
| PLAN-11 | Injects per-stage budget into HubRequest.constraints before each LLM call |
| PLAN-12 | Wraps execute() in try/except; any uncaught exception -> PLAN FAILED + emit |

**Key behaviors**:

- `execute(PlanRequest)` -> runs SKETCH -> EXPAND -> VALIDATE -> COMMIT sequentially
- Between each stage: checks cancel flag, emits stage_transition delta
- Budget injection: stamps `max_tokens`, `timeout_ms`, `temperature` per stage (Section 13.3)
- `micro_replan(MicroReplanRequest)` -> abbreviated mode: SKETCH -> VALIDATE -> COMMIT (skips EXPAND)
- On failure: emits `plan.failed.v1` event with error details and partial state

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| Happy-path sequencing | ~15 | Full 4-stage and micro-replan 3-stage |
| Budget injection correctness | ~15 | Per-stage token/timeout/temperature values |
| Cancel between stages | ~10 | Cancel at each inter-stage boundary |
| Error propagation | ~15 | Each stage failure -> correct lifecycle event |
| State machine transitions | ~15 | PENDING -> PLANNING -> stage states -> COMMITTED/FAILED |
| Delta emission | ~10 | Correct delta_type per transition |

**Deep dive**: Section 5 (Pipeline Flow), Section 10 (Micro-Replan), Section 13.3 (Budget)

### 17.3 SketchService (~60 tests)

**Role**: Stage 1 -- transforms raw user intent into a SketchPlan (high-level
goal decomposition with capability references).

```text
 Constructor:
   SketchService(
     llm_port:      ILLMPort,
     tool_router:   ToolCallRouter,
     hil_coord:     HILCoordinator,
     pipeline_ctrl: PipelineController,   -- for budget lookup
   )
```

**Ports used**: ILLMPort (direct), IFabricRetrievalPort + IStateReadPort + IBridgePort (via ToolCallRouter)

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-02 | LLM call uses slot-based prompt; output_schema = SketchPlanSchema |

**Key behaviors**:

- Calls ToolCallRouter to populate discovery slots (DISCOVERED_CAPS, SESSION_CONTEXT, LTM_RECALL)
- Assembles SYSTEM prompt: ROLE_DEFINITION + OUTPUT_SCHEMA(SketchPlanSchema)
- Assembles USER prompt: GOAL_SLOT + DISCOVERED_CAPS + SESSION_CONTEXT + LTM_RECALL + CONSTRAINTS
- Single LLM call -> parse SketchPlan from JSON response
- If parse fails: re-parse with relaxed extraction, then retry LLM call
- Triggers HILCoordinator clarification if intent is ambiguous (confidence < threshold)

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| Prompt slot composition | ~15 | Verify each slot populated correctly |
| LLM call correctness | ~10 | Budget, schema, model selection |
| Parse success | ~10 | Valid SketchPlan extraction |
| Parse failure + retry | ~10 | Re-parse and retry paths |
| HIL clarification trigger | ~10 | Confidence threshold, round counting |
| Error recovery (ERR_SKETCH_FAIL) | ~5 | Simplified prompt retry, final failure |

**Deep dive**: Section 6 (Stage 1 SKETCH)

### 17.4 ExpandService (~50 tests)

**Role**: Stage 2 -- expands SketchPlan into concrete PlanSteps with tool
mappings, parameter schemas, capability bindings, and dependency edges.

```text
 Constructor:
   ExpandService(
     llm_port:    ILLMPort,
     tool_router: ToolCallRouter,
   )
```

**Ports used**: ILLMPort (direct), IFabricRetrievalPort + IBridgePort (via ToolCallRouter)

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-02 | LLM call uses slot-based prompt; output_schema = ExpandedPlanSchema |

**Key behaviors**:

- Receives SketchPlan from PipelineController
- Calls ToolCallRouter for capability re-discovery (narrowed by SketchPlan goals)
- Assembles prompt with SKETCH_RESULT + DISCOVERED_CAPS + MEMORY_CONTEXT slots
- Single LLM call -> parse ExpandedPlan (List of PlanStep with tool bindings)
- Maps each SketchPlan goal to one or more PlanSteps
- Infers output_schema for each PlanStep based on tool capability contract
- Constructs dependency DAG edges between PlanSteps

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| Prompt slot composition | ~10 | SKETCH_RESULT + discovery slots |
| Tool mapping correctness | ~10 | Each goal maps to valid PlanSteps |
| Dependency DAG construction | ~10 | Correct edges, no cycles |
| Schema inference | ~5 | output_schema matches tool contract |
| Error recovery (ERR_EXPAND_FAIL) | ~10 | Fallback to degraded PlanSteps |
| Edge cases | ~5 | Empty sketch, single-goal, max-step plans |

**Deep dive**: Section 7 (Stage 2 EXPAND)

### 17.5 ValidateService (~45 tests)

**Role**: Stage 3 -- validates ExpandedPlan against structural rules, capability
existence, and (optionally) LLM-as-arbiter semantic review, then triggers HIL
approval for non-deterministic plans.

```text
 Constructor:
   ValidateService(
     llm_port:         ILLMPort,
     fabric_retrieval:  IFabricRetrievalPort,
     hil_coord:        HILCoordinator,
   )
```

**Ports used**: ILLMPort (direct), IFabricRetrievalPort (direct -- not via ToolCallRouter)

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-02 | LLM arbiter uses slot-based prompt; output_schema = ValidationResultSchema |
| PLAN-06 | DAG cycle check: topological sort; reject if cycles detected |
| PLAN-07 | Capability existence: every PlanStep.tool_id exists in Fabric registry |
| PLAN-08 | Parameter schema compatibility: PlanStep params match tool input_schema |
| PLAN-09 | Safety band check: no PlanStep exceeds session safety_band |

**Key behaviors**:

- Structural validation (deterministic): DAG acyclicity, capability existence, schema match, safety band
- If structural checks fail: return ValidationResult with specific failure reasons
- LLM arbiter (optional): semantic review of plan coherence, goal coverage, risk
- HIL approval trigger: if plan is non-deterministic or high-risk, delegate to HILCoordinator
- Revise loop: if arbiter finds issues, return to ExpandService for targeted fix (max 1 retry)

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| DAG cycle detection (PLAN-06) | ~8 | Various cycle patterns |
| Capability existence (PLAN-07) | ~8 | Missing, renamed, deprecated capabilities |
| Schema compatibility (PLAN-08) | ~5 | Type mismatches, missing required params |
| Safety band check (PLAN-09) | ~5 | Escalation, boundary values |
| LLM arbiter call | ~8 | Approve, reject, partial-reject |
| HIL approval flow | ~6 | Approve, modify, reject |
| Error recovery (ERR_VALIDATE_FAIL) | ~5 | Revise loop, arbiter timeout, final failure |

**Deep dive**: Section 8 (Stage 3 VALIDATE)

### 17.6 CommitService (~30 tests)

**Role**: Stage 4 -- assembles the final CommittedPlan, persists to WAL via
Bridge, emits lifecycle events.  Makes ZERO LLM calls (PLAN-03).

```text
 Constructor:
   CommitService(
     bridge_port: IBridgePort,
     delta_port:  IDeltaEmitPort,
     event_port:  IEventPort,
   )
```

**Ports used**: IBridgePort, IDeltaEmitPort, IEventPort (all direct)

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-03 | No ILLMPort in constructor -- compile-time guarantee: commit never calls LLM |

**Key behaviors**:

- Receives validated ExpandedPlan + ValidationResult
- Assembles CommittedPlan: stamps plan_id, version, timestamps, cognitive_trace_id
- Calls `bridge_port.persist_plan(committed_plan)` -- fire-and-forget WAL write
- Emits `k1.planner.plan.ready.v1` event with CommittedPlan payload
- Emits stage_transition delta (VALIDATE -> COMMITTED)
- If Bridge offline: plan still committed in-memory, persist retried on reconnect

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| Plan assembly correctness | ~8 | plan_id, version, timestamps, trace_id |
| WAL persist call | ~6 | Correct payload, fire-and-forget behavior |
| Event emission | ~6 | plan.ready.v1 topic, payload schema |
| Delta emission | ~4 | stage_transition delta correctness |
| Bridge offline | ~3 | Graceful degradation, retry semantics |
| Cancel during commit | ~3 | Cancel respected before persist, not after |

**Deep dive**: Section 9 (Stage 4 COMMIT)

### 17.7 ToolCallRouter (~35 tests)

**Role**: Shared service that routes tool-class discovery calls to the appropriate
port.  Used by SketchService (3 tool types) and ExpandService (2 tool types).
Enforces PLAN-05 per-stage tool call budget.

```text
 Constructor:
   ToolCallRouter(
     fabric_retrieval: IFabricRetrievalPort,
     state_read:       IStateReadPort,
     bridge_port:      IBridgePort,
   )
```

**Ports used**: IFabricRetrievalPort, IStateReadPort, IBridgePort (all direct)

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-05 | Per-stage call counter; raises ToolBudgetExceeded if limit reached |

**Key behaviors**:

- `discover(intent, domain, safety_band)` -> calls FabricRetrieval.discover_capabilities()
- `read_context(sections)` -> calls StateRead.read_sections()
- `recall_memory(query, selectors)` -> calls Bridge.recall()
- Counts calls per stage via internal counter (reset at stage boundary)
- PLAN-05 budget: configurable max calls per tool type per stage
- Degraded mode: if any port fails, returns empty result (does not block pipeline)

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| Routing correctness | ~8 | Each tool type dispatches to correct port |
| Call counting (PLAN-05) | ~8 | Budget enforcement, counter reset |
| Degraded paths | ~8 | Each port failure -> empty result |
| Concurrent calls | ~5 | Multiple tools called in parallel |
| Input validation | ~3 | Malformed queries, empty inputs |
| Cross-stage reset | ~3 | Counter resets between SKETCH and EXPAND |

**Deep dive**: Section 11 (Discovery Tools)

### 17.8 HILCoordinator (~35 tests)

**Role**: Manages Human-in-the-Loop interaction rounds.  Handles clarification
requests (SKETCH stage) and approval requests (VALIDATE stage).  Enforces
PLAN-10 maximum round budget.

```text
 Constructor:
   HILCoordinator(
     llm_port:   ILLMPort,
     event_port: IEventPort,
   )
```

**Ports used**: ILLMPort (for disambiguation prompt assembly), IEventPort (pub/sub for HIL messages)

**Invariants enforced**:

| Invariant | How Enforced |
| --------- | ------------ |
| PLAN-10 | Per-plan round counter; raises HILBudgetExceeded at max_rounds |

**Key behaviors**:

- `request_clarification(ambiguity, context)` -> publishes `k1.hil.clarification.v1`, awaits response
- `request_approval(plan, risk_assessment)` -> publishes `k1.hil.approval_request.v1`, awaits response
- Timeout handling: configurable per-round timeout; on expiry -> best-effort (clarification) or auto-approve (if safe)
- Response correlation: matches inbound response events by `request_id`
- Round counting: tracks total HIL rounds across all interaction types per plan
- LLM usage: assembles disambiguation prompts when clarification response needs interpretation

**Test categories**:

| Category | Count | Coverage |
| -------- | ----- | -------- |
| Clarification round-trip | ~8 | Publish, correlate, resume pipeline |
| Approval round-trip | ~8 | Approve, modify, reject responses |
| Round budget (PLAN-10) | ~5 | Max rounds, budget exceeded |
| Timeout handling | ~5 | Expiry, best-effort, auto-approve |
| Event correlation | ~5 | Correct request_id matching |
| Edge cases | ~4 | Duplicate responses, out-of-order, unknown request_id |

**Deep dive**: Section 12 (HIL System)

### 17.9 Service Summary Matrix

| Service | Tests | Ports (direct) | Ports (via peer) | Invariants | Deep Dive |
| ------- | ----- | -------------- | ---------------- | ---------- | --------- |
| PipelineController | ~80 | DeltaEmit, Event | (none) | PLAN-03,04,11,12 | Section 5, 10, 13.3 |
| SketchService | ~60 | LLM | Fabric, StateRead, Bridge (via ToolCallRouter) | PLAN-02 | Section 6 |
| ExpandService | ~50 | LLM | Fabric, Bridge (via ToolCallRouter) | PLAN-02 | Section 7 |
| ValidateService | ~45 | LLM, FabricRetrieval | (none) | PLAN-02,06,07,08,09 | Section 8 |
| CommitService | ~30 | Bridge, DeltaEmit, Event | (none) | PLAN-03 | Section 9 |
| ToolCallRouter | ~35 | FabricRetrieval, StateRead, Bridge | (none) | PLAN-05 | Section 11 |
| HILCoordinator | ~35 | LLM, Event | (none) | PLAN-10 | Section 12 |
| **Total** | **~335** | | | | |

### 17.10 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| Port specifications (7 ports) | 15.2-15.8 | Ports each service receives |
| Port-to-service dependency matrix | 15.10 | Which service uses which port |
| Adapter specifications (14 adapters) | 16.1-16.2 | Infrastructure behind each port |
| Full pipeline flow (26 steps) | 5 | PipelineController step-by-step orchestration |
| SKETCH deep dive | 6 | SketchService internals |
| EXPAND deep dive | 7 | ExpandService internals |
| VALIDATE deep dive | 8 | ValidateService internals |
| COMMIT deep dive | 9 | CommitService internals |
| Micro-Replan | 10 | PipelineController abbreviated mode |
| Discovery tools | 11 | ToolCallRouter backends |
| HIL system | 12 | HILCoordinator interaction model |
| LLM call patterns and budget | 13 | Budget tables, prompt composition |
| Invariant catalog | 19 (planned) | PLAN-01 through PLAN-12 master list |

---

## 18. Plan State Machine

The `PLAN_FSM` is owned by `PipelineController` and tracks the lifecycle of a
single plan from arrival through terminal outcome.  Every state change is:

1. **Logged** -- structured log with previous state, new state, and trigger
2. **Delta-emitted** -- `k1.planner.delta.v1{type: "stage_transition", from, to}`
3. **Monotonic** -- no backward transitions except the explicit `COMPLETED -> IDLE` reset

The FSM is NOT a separate runtime object -- it is an enum field
(`_current_state: PlanState`) inside PipelineController, mutated at each stage
boundary.

### 18.1 State Catalog

```text
 PlanState Enum (10 states):

 TRANSIENT STATES (active pipeline):
   IDLE              Initial and resting state.  No plan in progress.
   SKETCHING         Stage 1 active -- discovery tools + LLM sketch call.
   EXPANDING         Stage 2 active -- tool mapping + LLM expand call.
   VALIDATING        Stage 3 active -- deterministic checks + LLM arbiter + optional HIL.
   COMMITTING        Stage 4 active -- plan assembly + WAL persist + event emit.

 MICRO-REPLAN STATES (abbreviated pipeline):
   MICRO_SKETCH      Micro-replan Stage 1 -- re-sketch remaining steps.
   MICRO_EXPAND      Micro-replan Stage 2 -- re-map tools for replacement steps.
   MICRO_VALIDATE    Micro-replan Stage 3 -- validate replacement steps.
                     (COMMITTING is reused for micro-replan Stage 4)

 TERMINAL STATES (plan outcome resolved):
   COMPLETED         Plan successfully committed and delivered.
   FAILED            Plan failed at any stage (unrecoverable after retry).
   CANCELLED         Plan cancelled by Orchestrator via send_cancel().
```

### 18.2 State Diagram (Full Pipeline)

```text
                              FULL PLANNING PIPELINE
                              ======================

  PlanRequest                                                       plan.ready.v1
  dequeued                                                          emitted
     |                                                                 |
     v                                                                 v
  [IDLE] --PLAN_START--> [SKETCHING] --stage_complete--> [EXPANDING]
                              |                              |
                              |  (ERR_SKETCH_FAIL            |  (ERR_EXPAND_FAIL after
                              |   after retry)               |   retry + fallback)
                              |                              |
                              v                              v
                          [FAILED]                       [FAILED]
                                                             |
                         [EXPANDING] --stage_complete--> [VALIDATING]
                                                             |
                                         +-------------------+-------------------+
                                         |                                       |
                                   approved / auto-approve               reject after retry
                                         |                                       |
                                         v                                       v
                                    [COMMITTING] --commit_complete-->       [FAILED]
                                         |
                                         v
                                    [COMPLETED] --lock_released--> [IDLE]


                              CANCELLATION (any active state)
                              ===============================

  [SKETCHING|EXPANDING|VALIDATING|COMMITTING] --cancel_received--> [CANCELLED]
                                                                        |
                                                                        v
                                                                   plan.cancelled.v1
                                                                   emitted, then
                                                                   [CANCELLED] --lock_released--> [IDLE]
```

### 18.3 State Diagram (Micro-Replan Pipeline)

```text
                              MICRO-REPLAN PIPELINE
                              =====================

  MicroReplanRequest                                         CommittedPlan
  received (direct call)                                     returned sync
     |                                                          |
     v                                                          v
  [IDLE] --micro_start--> [MICRO_SKETCH] --stage_complete--> [MICRO_EXPAND]
                               |                                 |
                               |  (failure)                      |  (failure)
                               v                                 v
                           [FAILED]                          [FAILED]
                                                                 |
                     [MICRO_EXPAND] --stage_complete--> [MICRO_VALIDATE]
                                                             |
                                     +-----------------------+-----------+
                                     |                                   |
                               approved / revise                  reject
                               (revise = approved                        |
                                in micro-replan)                         v
                                     |                               [FAILED]
                                     v                           (return None)
                                [COMMITTING] --commit_complete--> [COMPLETED]
                                                                      |
                                                                      v
                                                                 [IDLE]
```

### 18.4 Transition Table

Every legal state transition with its trigger, guard condition, and side effects.

| From | To | Trigger | Guard | Side Effects |
| ---- | -- | ------- | ----- | ------------ |
| IDLE | SKETCHING | PlanRequest dequeued | Plan lock acquired | Reset counters, emit delta(SKETCH started) |
| IDLE | MICRO_SKETCH | MicroReplanRequest received | Plan lock acquired | Reset counters, emit delta(MICRO_SKETCH started) |
| SKETCHING | EXPANDING | SketchService returns SketchResult | No cancel pending | Emit delta(SKETCH completed, tokens), log |
| SKETCHING | FAILED | ERR_SKETCH_FAIL (retry exhausted) | -- | Emit plan.failed.v1, emit delta(SKETCH failed) |
| SKETCHING | CANCELLED | cancel_received | Cancel flag set | Emit plan.cancelled.v1, emit delta(cancelled) |
| EXPANDING | VALIDATING | ExpandService returns ExpandedPlan | No cancel pending | Emit delta(EXPAND completed, tokens), log |
| EXPANDING | FAILED | ERR_EXPAND_FAIL (retry + fallback exhausted) | -- | Emit plan.failed.v1, emit delta(EXPAND failed) |
| EXPANDING | CANCELLED | cancel_received | Cancel flag set | Emit plan.cancelled.v1, emit delta(cancelled) |
| VALIDATING | COMMITTING | Verdict approved (or auto-approved) | No cancel pending | Emit delta(VALIDATE completed, tokens), log |
| VALIDATING | EXPANDING | Verdict "revise" (1 retry allowed) | revise_count < 1 | Increment revise_count, emit delta(revise) |
| VALIDATING | FAILED | Verdict "reject" after retry EXPAND | -- | Emit plan.failed.v1, emit delta(VALIDATE rejected) |
| VALIDATING | FAILED | HIL reject response | -- | Emit plan.failed.v1, emit delta(HIL rejected) |
| VALIDATING | CANCELLED | cancel_received | Cancel flag set | Emit plan.cancelled.v1, emit delta(cancelled) |
| COMMITTING | COMPLETED | CommitService finishes | -- | Emit plan.ready.v1, emit delta(COMMIT completed), log |
| COMMITTING | CANCELLED | cancel_received (before persist) | Cancel flag set | Emit plan.cancelled.v1 (WAL NOT written) |
| COMPLETED | IDLE | Lock released, state cleared | -- | Clear counters, PlannerAgent resumes mailbox loop |
| FAILED | IDLE | Lock released, state cleared | -- | Clear counters, PlannerAgent resumes mailbox loop |
| CANCELLED | IDLE | Lock released, state cleared | -- | Clear counters, PlannerAgent resumes mailbox loop |
| MICRO_SKETCH | MICRO_EXPAND | Micro-SketchService returns | No cancel pending | Emit delta(MICRO_SKETCH completed) |
| MICRO_SKETCH | FAILED | LLM failure (no retry in micro) | -- | Return None to caller |
| MICRO_EXPAND | MICRO_VALIDATE | Micro-ExpandService returns | No cancel pending | Emit delta(MICRO_EXPAND completed) |
| MICRO_EXPAND | FAILED | LLM failure (no retry in micro) | -- | Return None to caller |
| MICRO_VALIDATE | COMMITTING | Verdict approved or "revise" (treated as approved) | -- | Emit delta(MICRO_VALIDATE completed) |
| MICRO_VALIDATE | FAILED | Verdict "reject" | -- | Return None to caller |

**Illegal transitions**: Any transition not listed above is a programming error.
PipelineController raises `IllegalStateTransitionError` if attempted, which triggers
PLAN-12 (uncaught exception -> FAILED).

### 18.5 Terminal States

Three states represent final plan outcomes.  All three share the same cleanup
sequence but differ in what they emit.

#### 18.5.1 COMPLETED

**Meaning**: Plan successfully committed, persisted to K0 WAL, and delivered to
Orchestrator via `k1.planner.plan.ready.v1`.

**Entry path**: COMMITTING -> COMPLETED (step 22 of pipeline flow, Section 5.2)

**Side effects on entry**:

1. `k1.planner.plan.ready.v1` event emitted with `CommittedPlan` payload
2. `k1.planner.delta.v1{type: "stage_transition", to: "COMPLETED"}` emitted
3. Plan lock released
4. Counters cleared (token usage, tool calls, HIL rounds)
5. Transition to IDLE (ready for next PlanRequest)

**Micro-replan variant**: COMMITTING -> COMPLETED, but:

- CommittedPlan returned synchronously (no event bus delivery)
- `k1.planner.micro_replan.ready.v1` emitted as TELEMETRY-ONLY
- Plan lock released immediately

#### 18.5.2 FAILED

**Meaning**: Plan could not be completed after all retry and fallback attempts.

**Entry paths** (5 distinct paths):

| Source State | Cause | Error Code |
| ------------ | ----- | ---------- |
| SKETCHING | ERR_SKETCH_FAIL (LLM fail after retry) | `SKETCH_EXHAUSTED` |
| EXPANDING | ERR_EXPAND_FAIL (LLM + fallback fail) | `EXPAND_EXHAUSTED` |
| VALIDATING | Reject verdict after retry EXPAND | `VALIDATE_REJECTED` |
| VALIDATING | HIL "reject" response | `HIL_REJECTED` |
| Any active | Uncaught exception (PLAN-12) | `INTERNAL_ERROR` |

**Side effects on entry**:

1. `k1.planner.plan.failed.v1` event emitted with payload:

   ```yaml
   plan_failed_payload:
     request_id: str          # Correlates to original PlanRequest
     stage: str               # Which stage failed (SKETCH, EXPAND, VALIDATE)
     error_code: str          # Machine-readable failure reason
     error_message: str       # Human-readable description
     partial_state: Dict      # Any partial results (SketchResult, ExpandedPlan)
     tokens_used: int         # Total tokens consumed before failure
     duration_ms: int         # Wall time from PLAN_START to failure
     trace_id: str            # Cognitive trace ID
   ```

2. `k1.planner.delta.v1{type: "plan_failed", stage, error_code}` emitted
3. Plan lock released
4. Counters cleared
5. Transition to IDLE

**Orchestrator response**: `PendingPlanContext` timeout reaper cleans up on failure
event.  Orchestrator does NOT retry planning -- the original TaskEnvelope is either
re-dispatched at a lower tier (HIGH -> MEDIUM) or abandoned depending on policy.

**Micro-replan variant**: FAILED does NOT emit `plan.failed.v1` (micro-replan is
best-effort).  PipelineController returns `None` to the caller.  CB_PLANNER may
trip on accumulated micro-replan failures.

#### 18.5.3 CANCELLED

**Meaning**: Plan cancelled by Orchestrator via `send_cancel(request_id)` before
the plan reached COMMITTING (or before WAL persist in COMMITTING).

**Entry paths**:

| Source State | Mechanism |
| ------------ | --------- |
| SKETCHING | Cancel flag checked at next await boundary |
| EXPANDING | Cancel flag checked between stages |
| VALIDATING | Cancel flag checked between stages |
| COMMITTING | Cancel flag checked before WAL persist |

**Cancel semantics (V1)**:

```text
 Cancellation is cooperative, not preemptive:
   1. Orchestrator calls PlannerAdapter.cancel_plan(request_id)
   2. PlannerAdapter calls IPlannerMailbox.send_cancel(request_id)
   3. MailboxAdapter adds request_id to _cancel_set
   4. PipelineController checks _cancel_set between each stage
   5. If current request_id is in _cancel_set: transition to CANCELLED

 Timing:
   - Cancel between stages: immediate effect (next stage never starts)
   - Cancel mid-LLM call: checked at next await boundary after LLM returns
   - Cancel during COMMIT: checked before WAL persist
     - Before persist: CANCELLED (plan never written)
     - After persist: too late, plan is COMPLETED (cancel has no effect)
   - Cancel after COMPLETED/FAILED: no-op (already terminal)
```

**Side effects on entry**:

1. `k1.planner.plan.cancelled.v1` event emitted with payload:

   ```yaml
   plan_cancelled_payload:
     request_id: str          # Correlates to original PlanRequest
     cancelled_at_stage: str  # Stage where cancel was detected
     tokens_used: int         # Tokens consumed before cancellation
     trace_id: str            # Cognitive trace ID
   ```

2. `k1.planner.delta.v1{type: "plan_cancelled", stage}` emitted
3. Any in-flight LLM call result is discarded (not an error, just unused)
4. Plan lock released
5. Counters cleared
6. Transition to IDLE

### 18.6 Lifecycle Phase to FSM State Mapping

The 6 lifecycle phases (from planner.mmd LIFECYCLE) map to FSM states:

| Lifecycle Phase | FSM State(s) | Description |
| --------------- | ------------ | ----------- |
| INIT | (pre-IDLE) | Services created, ports wired, event subscriptions registered. FSM set to IDLE on completion. |
| PLAN_START | IDLE -> SKETCHING (or MICRO_SKETCH) | PlanRequest dequeued, lock acquired, counters reset. |
| STAGE_TRANSITION | SKETCHING -> EXPANDING -> VALIDATING -> COMMITTING | PipelineController advances state between stages. |
| PLAN_END | COMMITTING -> COMPLETED -> IDLE | Plan delivered, lock released, counters cleared. |
| SHUTDOWN | Any -> (process exit) | Mailbox drained, deltas flushed, in-flight LLM calls cancelled. Partial plan state persisted for recovery. |
| CRASH_RECOVERY | (process start) -> IDLE | WAL checked for in-flight plan. If found: resume at last completed stage. If not: discard partial state, set IDLE. |

### 18.7 Crash Recovery and WAL Resume

If the Planner process crashes mid-pipeline, the `CRASH_RECOVERY` lifecycle phase
attempts to resume:

```text
 CRASH_RECOVERY sequence:

   1. Check K0 WAL via IBridgePort for any in-flight plan:
      bridge.query("planner.inflight", {agent_id: "planner"})

   2. IF in-flight plan found:
      a. Determine last completed stage from WAL metadata
      b. Restore PipelineController state (counters, partial results)
      c. Resume pipeline at next stage after last completed
         Example: SKETCH completed -> resume at EXPAND
      d. Emit recovery delta: k1.planner.delta.v1{type: "crash_recovery",
           resumed_at: "EXPANDING", plan_id: "..."}

   3. IF no in-flight plan found:
      a. Discard any partial state in memory
      b. Set FSM to IDLE
      c. Emit recovery delta: k1.planner.delta.v1{type: "crash_recovery",
           resumed_at: "IDLE", clean: true}

   4. Resume normal mailbox loop
```

**V1 limitation**: Crash recovery is best-effort.  If the crash occurred mid-LLM
call, the partial response is lost and the stage is retried from scratch.  The LLM
call is idempotent (same prompt produces equivalent output), so retry is safe.

### 18.8 Concurrency and the Plan Lock

V1 enforces single-plan execution via an `asyncio.Lock` held by PipelineController:

```text
 Plan lock lifecycle:

   IDLE state:        lock is FREE
   PLAN_START:        lock ACQUIRED (blocks additional PlanRequests at dequeue)
   Active states:     lock HELD (SKETCHING, EXPANDING, VALIDATING, COMMITTING)
   Terminal states:   lock RELEASED (COMPLETED, FAILED, CANCELLED)

 Mailbox behavior when lock is held:
   - PlanRequests enqueue normally (up to depth 5)
   - PlannerAgent dequeue loop waits on lock before starting next plan
   - MicroReplanRequest waits for lock (IPlannerMailbox.micro_replan acquires lock)

 V2 evolution:
   Per-plan state isolation (each plan gets its own PipelineController instance)
   Multiple plans can be in different stages concurrently
   Plan lock replaced by per-plan lock + global concurrency limiter
```

### 18.9 FSM Invariant Enforcement

The FSM enforces several invariants implicitly through its transition rules:

| Invariant | FSM Enforcement |
| --------- | --------------- |
| PLAN-03 | COMMITTING state has no LLM->port path (CommitService lacks ILLMPort) |
| PLAN-04 | PipelineController checks elapsed time at each transition; if > 45s -> FAILED |
| PLAN-11 | Budget injected into HubRequest at each SKETCHING/EXPANDING/VALIDATING entry |
| PLAN-12 | Uncaught exception in any state -> FAILED (try/except wraps execute()) |

### 18.10 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| Full pipeline flow (26 steps with FSM transitions) | 5.2 | Steps 4, 9, 12, 17, 22, 26 show state changes |
| Micro-replan abbreviated pipeline | 10.3 | MICRO_SKETCH -> MICRO_EXPAND -> MICRO_VALIDATE -> COMMITTING |
| PipelineController (FSM owner) | 17.2 | Service that mutates current\_state field |
| Error recovery paths | 19 (planned) | ERR\_SKETCH\_FAIL, ERR\_EXPAND\_FAIL, etc. -> FAILED transitions |
| Cancel protocol | 4.2 | IPlannerMailbox.send\_cancel() -> cancel\_set -> cooperative cancel |
| Lifecycle phases | planner.mmd LIFECYCLE | 6 phases mapped to FSM states (Section 18.6) |
| CB_PLANNER (Orchestrator-side) | 4.3 | 45s timeout; no direct FSM involvement (external observer) |
| Plan lock and concurrency | 18.8 | Lock held during active states, released on terminal |

---

## 19. Error Recovery Paths

Per-stage failure handling with graceful degradation.  Six named error recovery
paths are defined in `planner.mmd ERROR_RECOVERY` and wired to services via
explicit edges.  This section provides the consolidated cross-cutting view.
Stage-specific deep dives are in Sections 6.6, 7.6, 8.6, 9.6, and 10.6.

### 19.1 Recovery Path Catalog

```text
 Path              Trigger Service    Recovery Target     Terminal if Exhausted?
 ────────────────  ─────────────────  ──────────────────  ─────────────────────
 ERR_SKETCH_FAIL   SketchService      SketchService       YES -> FAILED
 ERR_EXPAND_FAIL   ExpandService      ExpandService / V   NO  -> fallback to SKETCH output
 ERR_VALIDATE_FAIL ValidateService    ExpandService / C   YES -> FAILED (after retry)
 ERR_COMMIT_FAIL   CommitService      CommitService       NO  -> plan.ready emitted anyway
 ERR_HIL_TIMEOUT   HILCoordinator     SketchService / V   NO  -> best-effort / auto-approve
 ERR_CB_OPEN       (Orchestrator)     (no Planner path)   N/A -> Orchestrator degrades tier
```

### 19.2 Global Error Decision Tree

The following tree covers every failure a plan can encounter, from first tool
call through final event delivery.  Each leaf is either a recovery action or
a terminal FAILED state.

```text
 PLAN_START
   |
   +-- SKETCHING
   |     |
   |     +-- Tool call failure (any of 3)
   |     |     -> Retry once within tool latency budget
   |     |     -> Second failure: proceed without that tool (degraded context)
   |     |     -> Pipeline continues (NOT a stage failure)
   |     |
   |     +-- HIL clarification timeout (60s)
   |     |     -> Best-effort interpretation (ERR_HIL_TIMEOUT)
   |     |     -> Pipeline continues (NOT a stage failure)
   |     |
   |     +-- LLM timeout/error [attempt 1]
   |     |     -> RETRY with SIMPLIFIED prompt:
   |     |         Remove K0 memory context
   |     |         Reduce capability list to top-3
   |     |         Same budget: {max_tokens: 2048, timeout_ms: 8000}
   |     |
   |     +-- LLM timeout/error [attempt 2]
   |     |     -> PLAN FAILED (ERR_SKETCH_FAIL)
   |     |     -> FSM: SKETCHING -> FAILED
   |     |     -> Emit: plan.failed.v1{stage: SKETCH, error: ERR_SKETCH_FAIL}
   |     |
   |     +-- JSON parse failure
   |           -> Re-parse once (strip fences, attempt recovery)
   |           -> Still malformed: treat as LLM error, follow retry path above
   |
   +-- EXPANDING
   |     |
   |     +-- Tool call failure (discovery or prompts)
   |     |     -> Retry once within 50ms budget
   |     |     -> Second failure: use SKETCH capability_candidates as fallback
   |     |     -> Pipeline continues (degraded input)
   |     |
   |     +-- LLM timeout/error [attempt 1]
   |     |     -> RETRY with same prompt, same budget
   |     |
   |     +-- LLM timeout/error [attempt 2]
   |     |     -> FALLBACK: convert SketchResult.rough_steps to minimal PlanSteps
   |     |        PlanStep{capability: rough_step.suggested or "UNRESOLVED", params: {}}
   |     |     -> Proceed to VALIDATE (degraded PlanSteps)
   |     |     -> Delta: status="degraded", degradation_reason="expand_llm_fallback"
   |     |
   |     +-- Invalid capability reference
   |     |     -> Replace with best match from SKETCH candidates
   |     |     -> No match: mark step is_optional=true
   |     |
   |     +-- Invalid dependency graph (cycles)
   |           -> Remove circular edges, flatten to sequential
   |           -> Log warning in delta
   |
   +-- VALIDATING
   |     |
   |     +-- Deterministic check failure (DAG cycle or unknown capability)
   |     |     -> Route suggested_fixes to EXPAND (revise loop, max 1 retry)
   |     |     -> Re-run also fails: PLAN FAILED
   |     |
   |     +-- LLM arbiter timeout/error + deterministic checks PASSED
   |     |     -> AUTO-APPROVE (structural integrity confirmed, LLM check is additive)
   |     |     -> Delta: verdict="auto_approved"
   |     |
   |     +-- LLM arbiter timeout/error + deterministic checks FAILED
   |     |     -> PLAN FAILED (cannot auto-approve without structural integrity)
   |     |
   |     +-- Verdict = "revise"
   |     |     -> Retry EXPAND once with suggested_fixes
   |     |     -> Second revise: treat as "approved" (best-effort)
   |     |
   |     +-- Verdict = "reject" (after revise loop)
   |     |     -> PLAN FAILED (ERR_VALIDATE_FAIL)
   |     |     -> FSM: VALIDATING -> FAILED
   |     |     -> Emit: plan.failed.v1{stage: VALIDATE, error: ERR_VALIDATE_FAIL}
   |     |
   |     +-- HIL approval timeout (120s)
   |     |     -> All steps GREEN: auto-approve (ERR_HIL_TIMEOUT)
   |     |     -> Any step RED: PLAN FAILED
   |     |
   |     +-- HIL approval "reject"
   |           -> PLAN FAILED (explicit user rejection is final)
   |
   +-- COMMITTING
   |     |
   |     +-- WAL persist failure
   |     |     -> Retry once (idempotent via plan_id dedup)
   |     |     -> Second failure: proceed anyway (WAL is durability, not correctness)
   |     |     -> Plan delivery is NEVER blocked by WAL failure
   |     |
   |     +-- Event bus publish failure
   |     |     -> Retry once
   |     |     -> Second failure: plan COMPLETED but undeliverable
   |     |     -> Orchestrator PendingPlanContext times out (45s CB_PLANNER)
   |     |
   |     +-- CommittedPlan validation error (__post_init__ raises)
   |           -> PLAN FAILED (INTERNAL_ERROR -- bug in VALIDATE)
   |           -> Should NEVER happen in production
   |
   +-- MICRO-REPLAN (any stage failure)
         -> Return None to caller
         -> Orchestrator continues with original plan
         -> No retry within micro-replan (time budget too tight)
         -> CB_PLANNER may trip on accumulated failures
```

### 19.3 Stage 1 SKETCH Failure (ERR\_SKETCH\_FAIL)

**Wiring**: `SVC_SKETCH -> ERR_SKETCH_FAIL -> retry SVC_SKETCH | PLAN_FSM(FAILED)`

**Retry strategy**: Single retry with simplified prompt (remove memory context,
reduce capabilities to top-3).  Same token budget.

**Why SKETCH failure is terminal**: SKETCH produces the foundational plan structure.
Without a SketchResult, no downstream stage has input to work with.  There is no
fallback -- if the LLM cannot produce even a rough plan, the intent is either
genuinely ambiguous or the LLM is unavailable.

**Tool call failures are NOT stage failures**: Discovery tools degrade gracefully.
Missing capabilities, empty context, or K0 offline all produce valid (but reduced)
input for the LLM call.  Only LLM failure terminates SKETCH.

| Scenario | Retry? | Outcome | FSM |
| -------- | ------ | ------- | --- |
| Tool timeout (any) | Tool-level retry (1x) | Proceed with degraded input | Stays SKETCHING |
| LLM fail (1st) | Stage retry (simplified prompt) | Retry SKETCH | Stays SKETCHING |
| LLM fail (2nd) | No | PLAN FAILED | SKETCHING -> FAILED |
| Parse fail | Re-parse once, then LLM retry | Up to 2 LLM attempts total | Stays SKETCHING |
| HIL timeout | No stage retry | Best-effort, pipeline continues | Stays SKETCHING |

**Deep dive**: Section 6.6

### 19.4 Stage 2 EXPAND Failure (ERR\_EXPAND\_FAIL)

**Wiring**: `SVC_EXPAND -> ERR_EXPAND_FAIL -> retry SVC_EXPAND | fallback -> SVC_VALIDATE`

**Retry strategy**: Single retry with same prompt.  On second failure: FALLBACK to
degraded PlanSteps derived from SketchResult.

**Why EXPAND failure is NOT terminal**: The SketchResult contains enough structure
(rough steps, capability candidates, rationale) to construct minimal PlanSteps.
These degraded steps have empty params and default timeouts, but they carry valid
capability references that VALIDATE can check and the Orchestrator can attempt.

**Degraded PlanStep construction**:

```text
 For each rough_step in SketchResult.rough_steps:
   PlanStep{
     id: "s<n>",
     capability: rough_step.suggested_capability or "UNRESOLVED",
     params: {},                          -- Empty (Orchestrator best-effort)
     deps: <from rough_step.depends_on>,
     output_schema: null,
     timeout_ms: 10000                    -- Default fallback
   }
```

| Scenario | Retry? | Outcome | FSM |
| -------- | ------ | ------- | --- |
| Tool timeout (discovery/prompts) | Tool-level retry (1x) | Use SKETCH candidates | Stays EXPANDING |
| LLM fail (1st) | Stage retry (same prompt) | Retry EXPAND | Stays EXPANDING |
| LLM fail (2nd) | No | FALLBACK to degraded PlanSteps | EXPANDING -> VALIDATING |
| Parse fail | Re-parse, then LLM retry, then fallback | Up to fallback | Stays EXPANDING |
| Invalid capability ref | No retry | Replace with best match or mark optional | Stays EXPANDING |
| Invalid deps (cycles) | No retry | Flatten to sequential | Stays EXPANDING |

**Deep dive**: Section 7.6

### 19.5 Stage 3 VALIDATE Failure (ERR\_VALIDATE\_FAIL)

**Wiring**: `SVC_VALIDATE -> ERR_VALIDATE_FAIL -> retry SVC_EXPAND | auto-approve SVC_COMMIT | PLAN_FSM(FAILED)`

**Retry strategy**: Most complex recovery path.  Decision depends on WHICH component
failed (deterministic checks, LLM arbiter, or HIL) and whether structural integrity
is confirmed.

**Auto-approve rule**: If the LLM arbiter is unavailable but BOTH deterministic checks
(DAG acyclicity and capability existence) PASSED, the plan is auto-approved.  This is
the key graceful degradation: structural integrity is the hard requirement, LLM
semantic review is additive.

**Revise loop**: If the arbiter returns "revise", EXPAND is re-run once with the
arbiter's `suggested_fixes` injected into the prompt.  Maximum 1 revise cycle.
A second "revise" verdict is treated as "approved" (best-effort).

| Scenario | Retry? | Outcome | FSM |
| -------- | ------ | ------- | --- |
| DAG cycle / unknown cap | Revise loop (retry EXPAND 1x) | Re-expand with fixes | VALIDATING -> EXPANDING -> VALIDATING |
| DAG cycle (2nd attempt) | No | PLAN FAILED | VALIDATING -> FAILED |
| Arbiter timeout + determ. pass | No | AUTO-APPROVE | VALIDATING -> COMMITTING |
| Arbiter timeout + determ. fail | No | PLAN FAILED | VALIDATING -> FAILED |
| Verdict "revise" (1st) | Retry EXPAND 1x | Re-expand | VALIDATING -> EXPANDING -> VALIDATING |
| Verdict "revise" (2nd) | No | Treat as approved | VALIDATING -> COMMITTING |
| Verdict "reject" (after retry) | No | PLAN FAILED | VALIDATING -> FAILED |
| HIL timeout + all GREEN | No | Auto-approve | VALIDATING -> COMMITTING |
| HIL timeout + any RED | No | PLAN FAILED | VALIDATING -> FAILED |
| HIL "reject" | No | PLAN FAILED | VALIDATING -> FAILED |

**Deep dive**: Section 8.6

### 19.6 Stage 4 COMMIT Failure (ERR\_COMMIT\_FAIL)

**Wiring**: `SVC_COMMIT -> ERR_COMMIT_FAIL -> retry SVC_COMMIT`

**Retry strategy**: Simplest recovery path.  The plan is already validated.
Failures are infrastructure (WAL, Event Bus) not logic.

**Core principle**: WAL failure NEVER blocks plan delivery.  The plan is valid
regardless of persistence.  WAL is a durability optimization (K0 crash recovery),
not a correctness gate.

| Scenario | Retry? | Outcome | FSM |
| -------- | ------ | ------- | --- |
| WAL persist fail (1st) | Retry persist (idempotent) | Proceed to event delivery | Stays COMMITTING |
| WAL persist fail (2nd) | No | Proceed anyway (durability loss) | COMMITTING -> COMPLETED |
| Event publish fail (1st) | Retry publish | Plan delivery | Stays COMMITTING |
| Event publish fail (2nd) | No | Plan valid but undeliverable | COMMITTING -> COMPLETED |
| CommittedPlan validation | No | PLAN FAILED (bug, should never happen) | COMMITTING -> FAILED |

**Worst case**: Event bus publish fails twice.  The plan was computed, validated,
and possibly persisted to WAL, but the Orchestrator never receives it.  The
Orchestrator's PendingPlanContext timeout reaper cleans up after 45s.  CB\_PLANNER
may trip, degrading future HIGH requests.

**Deep dive**: Section 9.6

### 19.7 HIL Timeout (ERR\_HIL\_TIMEOUT)

**Wiring**: `SVC_HIL -> ERR_HIL_TIMEOUT -> SVC_SKETCH (best-effort) | SVC_VALIDATE (auto-approve)`

HIL timeouts are NOT stage failures.  They trigger graceful degradation within the
current stage.

#### 19.7.1 Clarification Timeout (Stage 1, 60s per round)

```text
 Trigger: HILCoordinator awaits k1.hil.clarification_response.v1 for 60s
 Recovery: Proceed with best-effort interpretation of ambiguous intent
 Impact: Plan may be less precise (LLM generates from ambiguous input)
 FSM: No transition (stays SKETCHING)
 Max rounds: PLAN-10 (2 rounds), each with independent 60s timeout
```

#### 19.7.2 Approval Timeout (Stage 3, 120s)

```text
 Trigger: HILCoordinator awaits k1.hil.approval_response.v1 for 120s
 Recovery: Conditional auto-approve
   IF all steps have safety_band_min == "GREEN" (or null):
     -> Auto-approve (low risk, no high-impact operations)
     -> Delta: verdict="auto_approved", reason="hil_timeout_safe"
   ELSE (any step has safety_band_min == "AMBER" or "RED"):
     -> PLAN FAILED (high-impact operations require explicit approval)
     -> Emit: plan.failed.v1{stage: VALIDATE, error: HIL_TIMEOUT_UNSAFE}
 FSM: VALIDATING -> COMMITTING (auto-approve) or VALIDATING -> FAILED (unsafe)
```

### 19.8 CB\_PLANNER OPEN (ERR\_CB\_OPEN)

**Wiring**: `CB_PLANNER -> ORCH_SENDS` (no Planner involvement)

This path is entirely Orchestrator-owned.  The Planner has no role and no
awareness of CB state.

```text
 Trigger: CB_PLANNER is OPEN (3 consecutive failures, 60s reset timer)
 Location: PlannerAdapter._check_cb_open() -- Orchestrator side
 Effect: PlannerAdapter.request_plan() raises AdapterException(DEGRADED) immediately
 Planner awareness: NONE (Planner is never called)

 Orchestrator response:
   1. _dispatch_high() catches AdapterException(DEGRADED)
   2. Orchestrator degrades request: HIGH-tier -> MEDIUM-tier processing path
   3. MEDIUM-tier: direct Fabric capability execution (no planning)
   4. Plan quality: significantly reduced (no DAG, no multi-step orchestration)

 CB recovery:
   After 60s: CB_PLANNER transitions to HALF_OPEN
   Next request: single probe call to Planner
   If probe succeeds: CB_PLANNER -> CLOSED (normal operation resumes)
   If probe fails: CB_PLANNER -> OPEN (60s reset restarts)
```

### 19.9 Micro-Replan Error Recovery

Micro-replan uses no named error recovery paths.  ALL failures produce the same
outcome: return None to caller, continue with original plan.

```text
 Failure mode               | Planner action        | Orchestrator action
 ──────────────────────────  ──────────────────────  ────────────────────
 Micro-SKETCH LLM fail      | Return None           | Continue original plan
 Micro-EXPAND LLM fail      | Return None           | Continue original plan
 Micro-VALIDATE "reject"    | Return None           | Continue original plan
 Any stage exception         | Return None           | Continue original plan
 10s timeout exceeded        | (killed by caller)    | Continue original plan
 CB_PLANNER OPEN             | (never called)        | Continue original plan
```

**No retry within micro-replan**: The 10s total budget is too tight for retries.
Each micro-stage gets one attempt.

**No revise loop**: Verdict "revise" is treated as "approved" (best-effort).

**No HIL interaction**: Time budget insufficient, original plan already approved.

**Deep dive**: Section 10.6

### 19.10 Degradation Severity Ranking

Not all errors are equal.  The following ranks error paths by impact on plan
quality and system health:

| Rank | Path | Plan Impact | System Impact | Frequency (expected) |
| ---- | ---- | ----------- | ------------- | -------------------- |
| 1 (lowest) | ERR\_HIL\_TIMEOUT (clarification) | Slightly less precise plan | None | Occasional (user away) |
| 2 | ERR\_COMMIT\_FAIL (WAL) | None (plan valid) | Durability loss | Rare (K0 outage) |
| 3 | ERR\_EXPAND\_FAIL (fallback) | Degraded tool mapping | None | Uncommon (LLM outage) |
| 4 | ERR\_VALIDATE\_FAIL (auto-approve) | No semantic review | Reduced safety net | Uncommon (LLM outage) |
| 5 | ERR\_HIL\_TIMEOUT (approval) | Possible unsafe auto-approve | Reduced oversight | Rare (user away + risk) |
| 6 | ERR\_SKETCH\_FAIL | Plan lost | CB\_PLANNER may trip | Uncommon (LLM outage) |
| 7 | ERR\_COMMIT\_FAIL (event bus) | Plan undeliverable | Timeout reaper cost | Rare (bus outage) |
| 8 (highest) | ERR\_CB\_OPEN | No planning at all | Degraded to MEDIUM tier | Rare (sustained outage) |

### 19.11 Error Recovery Wiring Summary (from planner.mmd)

```text
 Service          Error Path           Recovery 1              Recovery 2 (exhausted)
 ───────────────  ───────────────────  ─────────────────────── ──────────────────────
 SVC_SKETCH       ERR_SKETCH_FAIL      retry SVC_SKETCH        PLAN_FSM -> FAILED
 SVC_EXPAND       ERR_EXPAND_FAIL      retry SVC_EXPAND        fallback -> SVC_VALIDATE
 SVC_VALIDATE     ERR_VALIDATE_FAIL    retry SVC_EXPAND        PLAN_FSM -> FAILED
                                       (or auto-approve ->     SVC_COMMIT)
 SVC_COMMIT       ERR_COMMIT_FAIL      retry SVC_COMMIT        plan.ready emitted anyway
 SVC_HIL          ERR_HIL_TIMEOUT      best-effort SVC_SKETCH  auto-approve SVC_VALIDATE
 (Orchestrator)   ERR_CB_OPEN          (no Planner path)       MEDIUM-tier direct exec
```

### 19.12 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| ERR\_SKETCH\_FAIL deep dive | 6.6 | Full failure scenarios, decision tree, cascading impact |
| ERR\_EXPAND\_FAIL deep dive | 7.6 | Fallback PlanStep construction, delta emission |
| ERR\_VALIDATE\_FAIL deep dive | 8.6 | Revise loop, auto-approve rule, HIL rejection |
| ERR\_COMMIT\_FAIL deep dive | 9.6 | WAL vs event bus failure, invariant enforcement |
| Micro-replan error recovery | 10.6 | All-failures-return-None simplification |
| Plan State Machine (FAILED) | 18.5.2 | 5 entry paths to FAILED, payload schema |
| Plan State Machine (CANCELLED) | 18.5.3 | Cooperative cancel vs error recovery |
| CB\_PLANNER configuration | 4.3 | 60s reset, 3 failures threshold, half-open probe |
| Pipeline flow failure table | 5.6 | 10-row failure scenario summary |
| PipelineController | 17.2 | PLAN-12: uncaught exception -> FAILED wrap |

---

## 20. Circuit Breakers & Fault Tolerance

Two circuit breakers protect the Planner.  CB\_PLANNER is owned by the Orchestrator
and gates **all** traffic into the Planner mailbox.  CB\_LLM\_INHERIT (a.k.a. CB\_MODEL)
is owned by Model Hub, inherited per-provider by LLMGatewayAdapter, and gates every
LLM call inside the pipeline.  The Planner itself never trips, resets, or probes a
circuit breaker -- it is always the *protected component*, never the *owner*.

**Source**: planner.mmd TOUCHPOINTS > TP\_CIRCUIT\_BREAKERS (lines 569-575),
CIRCUIT BREAKER PROTECTION edges (lines 847-849).

### 20.1 Circuit Breaker Inventory

| ID | Name | Owner | Protected Resource | Config Source | Threshold | Reset Window | Half-Open Probes | Fallback |
| -- | ---- | ----- | ------------------ | ------------- | --------- | ------------ | ---------------- | -------- |
| CB-1 | CB\_PLANNER | Orchestrator PlannerAdapter | PLANNER\_MAILBOX (all inbound traffic) | `OrchestratorConfig.cb_planner_*` | 3 consecutive failures | 60 s | 1 | Skip planning, MEDIUM-tier direct execution |
| CB-2 | CB\_LLM\_INHERIT | Model Hub (MH-05) | PORT\_LLM (per-provider) | Provider manifest (default 3/60 s) | 3 failures per provider | 30 s (default, per manifest) | 1 (default) | Capability-aware provider fallback (MH-06) |

### 20.2 CB\_PLANNER -- Orchestrator-Owned Gate

CB\_PLANNER is the outermost resilience boundary.  It wraps the Planner as a whole,
not individual pipeline stages.

**Wiring** (planner.mmd):

```text
 CB_PLANNER -.-> PLANNER_MAILBOX        -- "protects" edge
 CB_PLANNER -->  ORCH_SENDS             -- "OPEN: skip planning" edge
```

#### 20.2.1 State Machine

```text
                       3 failures
 CLOSED ──────────────────────────────> OPEN
    ^                                     |
    |                                     | 60s timer expires
    |         1 probe success             v
    +<────────────────────────────── HALF_OPEN
    |         1 probe failure             |
    |                                     |
    +- - - - (stays CLOSED) - -     OPEN (restart 60s)
```

| State | PlannerAdapter.request\_plan() Behavior |
| ----- | --------------------------------------- |
| CLOSED | Normal: enqueue PlanRequest to mailbox, return PlanAck(ACCEPTED) on success. On failure: `cb.trip()`, return PlanAck(REJECTED). On success: `cb.reset()`. |
| OPEN | Immediate: raise `AdapterException(DEGRADED)` -- Planner is never called. |
| HALF\_OPEN | Probe: one request allowed through. If succeeds: `cb.reset()` -> CLOSED. If fails: `cb.trip()` -> OPEN (60 s restart). |

#### 20.2.2 Configuration Fields

```text
 OrchestratorConfig fields:
   cb_planner_failure_threshold:   3          -- Consecutive failures to trip
   cb_planner_reset_timeout_ms:    60000      -- OPEN -> HALF_OPEN delay (ms)
   cb_planner_half_open_probes:    1          -- Probe count before CLOSED
```

All three fields are hot-reloadable via Orchestrator config refresh.

#### 20.2.3 What Counts as a Failure?

The PlannerAdapter considers these events as CB failures:

| Event | Counts as CB Failure? | Reason |
| ----- | --------------------- | ------ |
| `IPlannerMailbox.enqueue()` raises exception | Yes | Planner mailbox unreachable |
| `IPlannerMailbox.enqueue()` returns rejection | Yes | Planner overloaded (mailbox depth > 5) |
| Plan times out (45 s, no plan.ready/plan.failed received) | Yes | Planner unresponsive |
| `plan.failed.v1` event received | **No** | Pipeline ran but plan could not be produced -- functional failure, not availability failure |
| `plan.cancelled.v1` event received | **No** | Cooperative cancellation, not a fault |

This distinction is critical: CB\_PLANNER tracks **availability** (can the Planner
accept and process requests?), not **plan quality** (did the plan succeed or fail?).

#### 20.2.4 Orchestrator Behavior When OPEN

When CB\_PLANNER is OPEN, the Orchestrator degrades the request tier:

```text
 1. Orchestrator._dispatch_high(task_envelope)
 2.   -> PlannerAdapter.request_plan(plan_request)
 3.   -> CB check: state == OPEN
 4.   -> raise AdapterException(DEGRADED)
 5. Orchestrator catches AdapterException(DEGRADED)
 6.   -> Reclassify task: HIGH-tier -> MEDIUM-tier
 7.   -> Execute MEDIUM-tier path: direct Fabric capability call (no DAG, no multi-step)
 8. Plan quality: significantly reduced (single capability, no orchestration)
```

**Micro-replan when OPEN**: PlannerAdapter.micro\_replan() also checks CB\_PLANNER.
If OPEN, raises immediately.  Orchestrator continues with original plan (Section 19.9).

**Planner awareness**: None. The Planner never knows CB\_PLANNER is OPEN.  No message
reaches the mailbox. No side effects inside the Planner.

#### 20.2.5 HALF\_OPEN Probe Behavior

After 60 s, CB\_PLANNER transitions to HALF\_OPEN. The next `request_plan()` call
becomes the probe:

```text
 1. CB state: HALF_OPEN
 2. PlannerAdapter allows ONE request through to mailbox
 3. Mailbox enqueue succeeds:
      -> cb.reset() -> CLOSED
      -> Normal plan pipeline runs
 4. Mailbox enqueue fails:
      -> cb.trip() -> OPEN (60s restart)
      -> AdapterException(DEGRADED) for THIS request
```

The probe is a real PlanRequest from a real user task -- there is no synthetic health
check.  If the probe succeeds at enqueue but the plan later times out (45 s), the CB
stays CLOSED because the enqueue itself was healthy; the timeout increments the failure
counter normally and may re-trip the breaker.

### 20.3 CB\_LLM\_INHERIT -- Model Hub Per-Provider Gate

CB\_LLM\_INHERIT is not a single circuit breaker but a **family of per-provider
breakers** maintained by Model Hub (MH-05).  The Planner inherits their protection
transparently through LLMGatewayAdapter.

**Wiring** (planner.mmd):

```text
 CB_LLM_INHERIT -.-> PORT_LLM            -- "protects" edge
```

#### 20.3.1 Ownership and Configuration

| Aspect | Detail |
| ------ | ------ |
| Owner | Model Hub (`k1/model_hub/`) |
| Config source | Per-provider manifest (e.g., `providers/openai.yaml`) |
| Default threshold | 3 failures per provider |
| Default reset window | 30 s |
| Default half-open probes | 1 |
| Scope | Per provider (openai, azure-openai, anthropic, etc.). Multiple providers can be CLOSED while one is OPEN. |

#### 20.3.2 How the Planner Inherits Protection

```text
 Planner stage (e.g., SketchService)
   -> ILLMPort.execute(HubRequest)
   -> LLMGatewayAdapter
   -> LLM_REQUEST_BUS
   -> Model Hub
   -> ModelSelector picks provider
   -> Provider CB check:
        CLOSED -> route to provider
        OPEN   -> ModelSelector tries next capable provider (MH-06)
        All OPEN -> Model Hub returns ProviderUnavailableError
   -> LLMGatewayAdapter receives HubResponse or error
```

The Planner never interacts with provider CBs directly.  It sees one of:

| Model Hub Outcome | LLMGatewayAdapter Translation | Planner Impact |
| ----------------- | ----------------------------- | -------------- |
| HubResponse (success) | Return parsed LLM output | Stage proceeds normally |
| Provider CB OPEN, fallback provider available | Transparent (Model Hub handles) | No impact -- different provider used |
| All providers OPEN | `LLMTimeoutError` or `AdapterException(DEGRADED)` | Stage enters error recovery path (Section 19) |
| Budget exceeded (MH-04) | `BudgetExceededError` | Stage fails, plan FAILED |

#### 20.3.3 Per-Stage Impact When All Providers Are OPEN

When Model Hub cannot find any available provider, each stage responds according to
its error recovery path (Section 19):

| Stage | Error Recovery Path | Behavior |
| ----- | ------------------- | -------- |
| SKETCH | ERR\_SKETCH\_FAIL | Retry once with simplified prompt. If still fails: plan.failed.v1 emitted. |
| EXPAND | ERR\_EXPAND\_FAIL | Retry once. If still fails: fallback to SKETCH output as-is (degraded). |
| VALIDATE | ERR\_VALIDATE\_FAIL | LLM arbiter unavailable: auto-approve if deterministic checks pass. |
| COMMIT | (no LLM call) | Not affected -- Stage 4 is deterministic. |

**Cascading effect**: Sustained LLM unavailability across all stages causes
`plan.failed.v1`.  Three consecutive plan failures trip CB\_PLANNER (Section 20.2.3),
degrading all subsequent HIGH-tier requests to MEDIUM-tier.

### 20.4 Fault Tolerance by Port

Every hexagonal port has a defined fault tolerance strategy.  The Planner's design
philosophy: **degrade gracefully, never crash**.  No port failure terminates the
PlannerAgent actor -- the worst outcome is plan.failed.v1, which the Orchestrator
handles cleanly.

| Port | Direction | CB Protected? | Failure Mode | Planner Response | Severity |
| ---- | --------- | ------------- | ------------ | ---------------- | -------- |
| IPlannerMailbox | Inbound | CB\_PLANNER (external) | Mailbox full (depth > 5) | Reject at enqueue (PlanAck REJECTED) | Low (caller retries) |
| ILLMPort | Outbound | CB\_LLM\_INHERIT (external) | Provider timeout, all providers OPEN | Stage error recovery (per Section 19) | High (plan may fail) |
| IFabricRetrievalPort | Outbound | None (in-process) | Fabric timeout / exception | Return empty RetrievalResult, proceed with fewer tools | Low (degraded quality) |
| IStateReadPort | Outbound | None (in-process) | SessionState unavailable | Return empty Dict, ToolCallRouter degrades | Low (degraded context) |
| IBridgePort | Outbound | None | K0 WAL timeout | Log warning, retry once, proceed | Low (durability loss, not correctness) |
| IDeltaEmitPort | Outbound | None | Bus failure | Fire-and-forget: no failure propagation | None (best-effort) |
| IEventPort | Outbound | None | Bus failure | Retry once. If fails: plan completed but undeliverable | Medium (Orchestrator timeout reaper) |

### 20.5 Fire-and-Forget Resilience Pattern

Three outbound ports use the fire-and-forget pattern, meaning their failure is
**never** propagated back to the pipeline:

| Port | What Fires | Why Fire-and-Forget |
| ---- | ---------- | ------------------- |
| IDeltaEmitPort | Cognitive deltas (ORCH\_PLAN\_REQUESTED, SKETCH\_COMPLETE, etc.) | Deltas are observability hints, not correctness requirements. Missing a delta does not invalidate the plan. |
| IBridgePort (WAL persist) | `committed_plan` to K0 WAL | WAL is durability insurance. Plan is valid even without WAL. Idempotent via `plan_id` dedup key. |
| IEventPort (progress events) | `k1.hil.progress.v1` (Orchestrator -> Concierge) | User notification only. Planner does not emit progress events directly. |

**Contract**: Fire-and-forget ports MUST NOT raise exceptions.  Adapters catch all
errors internally and log them.  The pipeline continues regardless (Sections 15.6,
15.7, 15.8).

### 20.6 Resilience Design Philosophy

The Planner's fault tolerance follows three principles:

**Principle 1: Degrade, Never Crash**

No single port failure, LLM outage, or infrastructure fault terminates the PlannerAgent
actor.  The worst case is always `plan.failed.v1`, which the Orchestrator handles by
degrading the task.  The PlannerAgent remains alive, mailbox intact, ready for the
next request.

```text
 Failure severity ladder (Planner-internal):
   Level 0: No impact         -- fire-and-forget port failure (IDeltaEmitPort, IBridgePort WAL)
   Level 1: Degraded quality  -- discovery tool timeout, SessionState unavailable
   Level 2: Stage retry       -- LLM timeout, arbiter reject, WAL persist failure
   Level 3: Stage fallback    -- EXPAND fails and falls back to SKETCH output
   Level 4: Plan failure      -- SKETCH fails after retry, VALIDATE reject after retry
   Level 5: External gate     -- CB_PLANNER OPEN (Orchestrator-owned, Planner bypassed)
```

**Principle 2: The Planner Does Not Own Its Own Circuit Breakers**

The Planner is a **protected component**, never a **protector**.  CB\_PLANNER is owned
by the Orchestrator.  CB\_LLM\_INHERIT is owned by Model Hub.  The Planner's code
contains zero imports from any circuit breaker library.  This separation means:

- The Planner cannot accidentally reset or suppress its own breaker
- CB policy changes do not require Planner code changes
- Testing the Planner never requires mocking CB state -- test adapters bypass CBs

**Principle 3: Uncaught Exceptions Are Plan Failures, Not Actor Crashes**

PipelineController wraps the entire pipeline in a top-level exception handler
(PLAN-12).  Any uncaught exception from any stage is caught, wrapped in
`plan.failed.v1{reason: "uncaught", stage, error_detail}`, and emitted.  The
PlannerAgent actor is never killed by a pipeline exception.

```text
 PipelineController.run_pipeline():
   try:
     run Stage 1..4
   except Exception as e:
     plan_fsm.transition(FAILED)
     emit plan.failed.v1{
       request_id,
       reason: "uncaught_exception",
       stage: current_stage,
       error_detail: str(e)
     }
     # Actor survives. Mailbox processing continues.
```

### 20.7 Circuit Breaker Interaction Matrix

Both circuit breakers can be in any state simultaneously.  This matrix shows outcomes:

| CB\_PLANNER | CB\_LLM\_INHERIT (all providers) | Request Outcome |
| ----------- | --------------------------------- | --------------- |
| CLOSED | CLOSED | Normal planning pipeline. All stages use LLM. |
| CLOSED | Partial OPEN (some providers) | Normal pipeline. Model Hub routes to available providers (transparent). |
| CLOSED | All OPEN | Pipeline starts. LLM stages fail. Error recovery paths activate. Likely plan.failed.v1. |
| OPEN | (irrelevant) | Planner bypassed entirely. MEDIUM-tier direct execution. |
| HALF\_OPEN | CLOSED | Probe request sent. If enqueue succeeds, normal pipeline with LLM. |
| HALF\_OPEN | All OPEN | Probe request sent. If enqueue succeeds, pipeline starts but LLM fails. Plan.failed.v1. CB\_PLANNER failure count incremented (timeout). |

### 20.8 Monitoring and Observability

Circuit breaker state changes are observable through structured telemetry:

| Event | Emitter | Topic / Log |
| ----- | ------- | ----------- |
| CB\_PLANNER trip (CLOSED -> OPEN) | PlannerAdapter | `k1.orchestrator.cb.planner.tripped` + structured log (WARN) |
| CB\_PLANNER probe (HALF\_OPEN -> CLOSED or OPEN) | PlannerAdapter | `k1.orchestrator.cb.planner.probe_result` + structured log (INFO) |
| CB\_LLM provider trip | Model Hub | `k1.model_hub.cb.provider.tripped` (per-provider) |
| CB\_LLM provider recovery | Model Hub | `k1.model_hub.cb.provider.recovered` (per-provider) |
| Plan failed due to LLM unavailability | PlannerAgent | `k1.planner.plan.failed.v1{reason: "llm_unavailable"}` |

The Planner does not emit CB-specific telemetry because it does not own any CBs.
All CB telemetry originates from the Orchestrator or Model Hub.

### 20.9 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| CB\_PLANNER config and PlannerAdapter wrapping | 4.3 | State machine, methods, config fields |
| Two-Phase Plan Delivery (CB affects Phase 1) | 4.4 | How CB\_PLANNER blocks Phase 1 enqueue |
| Pipeline flow failure scenarios (CB row) | 5.6 | "All: Total > 45s -> CB trips" row |
| LLMGatewayAdapter (CB\_LLM\_INHERIT) | 16.1.2 | Per-provider CB inheritance from Model Hub |
| ERR\_CB\_OPEN recovery path | 19.8 | Orchestrator-side MEDIUM-tier degradation |
| Error recovery wiring summary | 19.11 | All 6 error paths + CB\_PLANNER row |
| Degradation severity ranking | 19.10 | ERR\_SKETCH\_FAIL as highest-impact path |
| PipelineController PLAN-12 safety net | 17.2 | Uncaught exception wrapping |

---

## 21. Performance Targets

### 21.1 Planner-owned latencies

| Operation | Target (P50) | Target (P99) | Tokens | Notes |
|-----------|-------------|-------------|--------|-------|
| Stage 1 SKETCH | 4s | 8s | ~2K | LLM + 3 discovery tools |
| Stage 2 EXPAND | 3s | 5s | ~1K | LLM + 2-3 discovery tools |
| Stage 3 VALIDATE | 2s | 3s | ~500 | Deterministic checks + LLM arbiter |
| Stage 4 COMMIT | 20ms | 100ms | 0 | Deterministic, no LLM |
| Total Planning | 12s | 30s | ~3.5K | All 4 stages |
| Micro-Replan | 8s | 15s | ~2K | 3 abbreviated stages |
| Plan Delivery | 2ms | 10ms | 0 | Event publish only |
| Discovery tool call | -- | <50ms | 0 | Fabric Retrieval (not Planner-owned) |
| HIL round-trip | user-bound | user-bound | ~300-400 | Not system-controllable |

### 21.2 Resource budgets

| Resource | Budget | Notes |
|----------|--------|-------|
| Total tokens per plan | ~3.5K | Across all 3 LLM stages |
| Total tokens per micro-replan | ~2K | Reduced budget |
| Discovery tool calls per plan | Max 6 | PLAN-05 |
| HIL rounds per plan | Max 2 | PLAN-10 |
| Mailbox depth | Max 5 | Rejects beyond |
| Concurrent plans (V1) | 1 | Single plan at a time |

---

## 22. Observability & Telemetry

The Planner produces three categories of observable output: **trace propagation**
(cognitive\_trace\_id threaded through every port call), **structured logs** (per-
operation log events with machine-parseable fields), **metrics** (counters,
histograms, gauges for SLI dashboards), and **delta emissions** (fire-and-forget
cognitive deltas via IDeltaEmitPort).  The Planner owns no circuit breaker
telemetry -- that belongs to the Orchestrator and Model Hub (Section 20.8).

### 22.1 Trace Propagation

Every operation inside the Planner carries `cognitive_trace_id` (aliased as
`trace_id` in all message types).  This is the single correlation key that
connects a user utterance through Concierge, Orchestrator, Planner, Fabric,
Model Hub, and K0 into one end-to-end trace.

**Source**: FAB-09 (Fabric traceability contract).

#### 22.1.1 Trace Origin

```text
 Concierge -> TaskEnvelope{cognitive_trace_id}
   -> Orchestrator._dispatch_high()
   -> PlanRequest{trace_id: cognitive_trace_id}
   -> Planner mailbox
```

The Planner receives `trace_id` inside `PlanRequest` (Section 4.5).  It NEVER
generates its own trace ID -- always echoes the caller's.

#### 22.1.2 Trace Propagation Map

Every outbound port call stamps `trace_id` from the active PlanRequest:

| Port | Call | trace\_id Source | Downstream Consumer |
| ---- | ---- | ---------------- | ------------------- |
| ILLMPort | `execute(HubRequest)` | `HubRequest.trace_id = PlanRequest.trace_id` | Model Hub (MH-03 tracing) |
| IFabricRetrievalPort | `discover_capabilities(...)` | Method parameter `trace_id` | Fabric Retrieval |
| IFabricRetrievalPort | `find_relevant_prompts(...)` | Method parameter `trace_id` | Fabric Retrieval |
| IStateReadPort | `read_sections(...)` | Method parameter `trace_id` | SessionState |
| IBridgePort | `recall(...)` | Method parameter `trace_id` | K0 Bridge |
| IBridgePort | `persist_plan(...)` | `CommittedPlan.trace_id` | K0 WAL |
| IDeltaEmitPort | `emit_delta(...)` | `DeltaPayload.trace_id` | Delta Bus subscribers |
| IEventPort | `publish(topic, payload)` | `payload.trace_id` | Event Bus subscribers |

#### 22.1.3 Trace in Output Messages

All output events echo `trace_id` so the Orchestrator can correlate:

| Output Event | trace\_id Field |
| ------------ | --------------- |
| `k1.planner.plan.ready.v1` (CommittedPlan) | `CommittedPlan.trace_id` |
| `k1.planner.plan.failed.v1` | `payload.trace_id` |
| `k1.planner.plan.cancelled.v1` | `payload.trace_id` |
| `k1.planner.micro_replan.ready.v1` (telemetry-only) | `payload.trace_id` |
| `k1.hil.clarification.v1` | `payload.trace_id` |
| `k1.hil.approval_request.v1` | `payload.trace_id` |
| `k1.planner.delta.v1` (all deltas) | `DeltaPayload.trace_id` |

#### 22.1.4 Trace Invariant

```text
 INVARIANT: For every PlanRequest with trace_id T,
   ALL port calls, ALL emitted events, ALL structured logs,
   and ALL deltas produced during that plan MUST carry trace_id == T.

 Enforcement: PipelineController stores trace_id at pipeline start.
              All services receive it via their StageContext parameter.
              No service generates or modifies trace_id.
```

### 22.2 Structured Logs

Every log event is a structured JSON record.  No free-form string logs.  All
log records include the fields `trace_id`, `timestamp_ms`, `level`, and
`component` (always `"planner"`).

#### 22.2.1 Log Event Catalog

| Event Name | Level | Emitter | When | Key Fields |
| ---------- | ----- | ------- | ---- | ---------- |
| `plan.received` | INFO | PlannerAgent | PlanRequest dequeued from mailbox | `request_id`, `intent` (truncated 80 chars), `trace_id` |
| `plan.lock_acquired` | DEBUG | PlannerAgent | Plan lock acquired (V1 single-plan) | `request_id` |
| `pipeline.started` | INFO | PipelineController | Pipeline begins | `request_id`, `timeout_ms` |
| `stage.started` | INFO | PipelineController | Stage N begins | `request_id`, `stage` (SKETCH/EXPAND/VALIDATE/COMMIT) |
| `stage.completed` | INFO | PipelineController | Stage N finishes successfully | `request_id`, `stage`, `duration_ms`, `tokens_used` |
| `stage.failed` | WARN | PipelineController | Stage N fails (before recovery) | `request_id`, `stage`, `error_type`, `error_detail` |
| `stage.retry` | INFO | PipelineController | Stage retrying after failure | `request_id`, `stage`, `retry_attempt`, `simplified` |
| `llm.call_started` | DEBUG | Service (Sketch/Expand/Validate) | LLM call dispatched via ILLMPort | `request_id`, `stage`, `capability`, `max_tokens`, `timeout_ms` |
| `llm.call_completed` | DEBUG | Service (Sketch/Expand/Validate) | LLM response received | `request_id`, `stage`, `model_id`, `provider_id`, `tokens_used`, `latency_ms`, `cost_usd` |
| `llm.call_failed` | WARN | Service (Sketch/Expand/Validate) | LLM call error | `request_id`, `stage`, `error_type` (timeout/budget/degraded) |
| `tool.call_started` | DEBUG | ToolCallRouter | Discovery tool dispatched | `request_id`, `tool_name`, `tool_call_index` (1-6) |
| `tool.call_completed` | DEBUG | ToolCallRouter | Discovery tool returned | `request_id`, `tool_name`, `result_count`, `latency_ms` |
| `tool.call_failed` | WARN | ToolCallRouter | Discovery tool error/timeout | `request_id`, `tool_name`, `error_type` |
| `hil.clarification_sent` | INFO | HILCoordinator | Clarification question emitted | `request_id`, `plan_id`, `round` (1 or 2) |
| `hil.clarification_received` | INFO | HILCoordinator | User response received | `request_id`, `plan_id`, `round`, `latency_ms` |
| `hil.clarification_timeout` | WARN | HILCoordinator | 60s timeout, best-effort proceed | `request_id`, `plan_id`, `round` |
| `hil.approval_sent` | INFO | HILCoordinator | Approval request emitted | `request_id`, `plan_id`, `step_count`, `has_high_impact` |
| `hil.approval_received` | INFO | HILCoordinator | User approval/modify/reject received | `request_id`, `plan_id`, `response_type`, `latency_ms` |
| `hil.approval_timeout` | WARN | HILCoordinator | 120s timeout, auto-approve if safe | `request_id`, `plan_id`, `auto_approved` |
| `validate.deterministic_passed` | DEBUG | ValidateService | All deterministic checks pass | `request_id`, `checks_passed` (list) |
| `validate.deterministic_failed` | WARN | ValidateService | Deterministic check failure | `request_id`, `check_name`, `failure_detail` |
| `validate.arbiter_verdict` | INFO | ValidateService | LLM arbiter returned verdict | `request_id`, `verdict` (approved/revise/reject), `confidence` |
| `commit.plan_built` | INFO | CommitService | CommittedPlan assembled | `request_id`, `plan_id`, `step_count`, `total_tokens` |
| `commit.wal_persisted` | DEBUG | CommitService | K0 WAL persist succeeded | `request_id`, `plan_id` |
| `commit.wal_failed` | WARN | CommitService | K0 WAL persist failed | `request_id`, `plan_id`, `error_detail` |
| `commit.event_published` | INFO | CommitService | plan.ready.v1 published | `request_id`, `plan_id`, `publish_latency_ms` |
| `commit.event_failed` | ERROR | CommitService | plan.ready.v1 publish failed | `request_id`, `plan_id`, `error_detail` |
| `plan.completed` | INFO | PlannerAgent | Plan lock released, IDLE | `request_id`, `plan_id`, `total_duration_ms`, `total_tokens`, `outcome` (ready/failed/cancelled) |
| `plan.failed` | WARN | PipelineController | Pipeline produced plan.failed.v1 | `request_id`, `reason`, `stage`, `error_detail` |
| `plan.cancelled` | INFO | PlannerAgent | Cooperative cancel processed | `request_id`, `cancel_reason` |
| `micro_replan.started` | INFO | PipelineController | Micro-replan pipeline begins | `original_plan_id`, `remaining_steps` |
| `micro_replan.completed` | INFO | PipelineController | Micro-replan succeeded | `original_plan_id`, `replacement_step_count`, `duration_ms` |
| `micro_replan.failed` | WARN | PipelineController | Micro-replan returned None | `original_plan_id`, `reason` |
| `recovery.fallback` | WARN | PipelineController | Error recovery fallback activated | `request_id`, `stage`, `recovery_path` (ERR\_SKETCH\_FAIL, etc.) |
| `recovery.auto_approve` | WARN | ValidateService | Arbiter down, deterministic auto-approve | `request_id`, `deterministic_only` |

#### 22.2.2 Log Level Policy

| Level | Usage | Example |
| ----- | ----- | ------- |
| DEBUG | Internal flow steps, individual tool/LLM calls | `llm.call_started`, `tool.call_completed` |
| INFO | Plan lifecycle boundaries, stage boundaries, HIL events | `plan.received`, `stage.completed`, `plan.completed` |
| WARN | Recoverable failures, degradation, timeouts | `stage.failed`, `hil.approval_timeout`, `commit.wal_failed` |
| ERROR | Non-recoverable failures (plan undeliverable) | `commit.event_failed` |

No FATAL/CRITICAL level: the PlannerAgent actor never crashes (Section 20.6,
Principle 3).  The worst outcome is ERROR-level followed by `plan.failed`.

#### 22.2.3 Sensitive Data Handling

Logs MUST NOT contain:

- Raw user intent (truncate to 80 characters in `plan.received`)
- SessionState section contents (log section names only, not data)
- LLM prompt text (log token counts and model metadata only)
- HIL user responses (log response\_type and latency only)
- PlanStep parameters (log step\_id and capability\_name only)

This complies with the privacy classification rules (copilot-instructions.md
Security & Privacy section).

### 22.3 Metrics

Planner metrics are emitted via the K1 telemetry subsystem (`k1/telemetry/`).
All metric names are prefixed with `planner.` to avoid namespace collisions.

#### 22.3.1 Counters

| Metric Name | Labels | Incremented When |
| ----------- | ------ | ---------------- |
| `planner.plan.total` | `outcome={ready,failed,cancelled}` | Plan lifecycle ends |
| `planner.plan.degraded` | `stage={SKETCH,EXPAND,VALIDATE}` | Error recovery fallback activated |
| `planner.stage.total` | `stage={SKETCH,EXPAND,VALIDATE,COMMIT}`, `outcome={success,retry,fallback,failed}` | Stage completes (any outcome) |
| `planner.llm.calls` | `stage={SKETCH,EXPAND,VALIDATE,HIL}`, `outcome={success,timeout,error}` | LLM call completes |
| `planner.tool.calls` | `tool={discover_capabilities,find_relevant_prompts,recall}`, `outcome={success,timeout,empty}` | Discovery tool call completes |
| `planner.hil.rounds` | `type={clarification,approval}`, `outcome={responded,timeout,auto_approved}` | HIL round completes |
| `planner.micro_replan.total` | `outcome={success,failed}` | Micro-replan completes |
| `planner.mailbox.rejected` | (none) | Mailbox rejects due to depth > 5 |
| `planner.recovery.activated` | `path={ERR_SKETCH_FAIL,ERR_EXPAND_FAIL,ERR_VALIDATE_FAIL,ERR_COMMIT_FAIL,ERR_HIL_TIMEOUT}` | Named error recovery path entered |

#### 22.3.2 Histograms

| Metric Name | Unit | Buckets (suggested) | Recorded When |
| ----------- | ---- | ------------------- | ------------- |
| `planner.plan.duration_ms` | ms | 1000, 5000, 10000, 15000, 30000, 45000 | Plan lifecycle ends (ready or failed) |
| `planner.stage.duration_ms` | ms | 500, 1000, 2000, 5000, 8000, 15000 | Stage completes (any outcome) |
| `planner.llm.latency_ms` | ms | 500, 1000, 2000, 5000, 8000 | LLM call returns |
| `planner.llm.tokens` | tokens | 256, 512, 1024, 2048, 4096 | LLM call returns |
| `planner.tool.latency_ms` | ms | 10, 25, 50, 100, 200 | Discovery tool call returns |
| `planner.micro_replan.duration_ms` | ms | 1000, 3000, 5000, 8000, 10000 | Micro-replan completes |

Labels on histograms: `stage` label on `planner.stage.duration_ms` and
`planner.llm.latency_ms` to distinguish per-stage performance.

#### 22.3.3 Gauges

| Metric Name | Unit | Updated When |
| ----------- | ---- | ------------ |
| `planner.mailbox.depth` | count | After every enqueue/dequeue |
| `planner.plan.in_flight` | 0 or 1 | Plan lock acquire/release (V1: always 0 or 1) |
| `planner.tokens.budget_remaining` | tokens | After each LLM call (3500 - used) |
| `planner.tool.budget_remaining` | count | After each tool call (6 - used) |

#### 22.3.4 SLI Alignment

Metrics map to the performance targets in Section 21:

| SLI | Metric | P50 Target | P99 Target |
| --- | ------ | ---------- | ---------- |
| SKETCH latency | `planner.stage.duration_ms{stage=SKETCH}` | 4 s | 8 s |
| EXPAND latency | `planner.stage.duration_ms{stage=EXPAND}` | 3 s | 5 s |
| VALIDATE latency | `planner.stage.duration_ms{stage=VALIDATE}` | 2 s | 3 s |
| COMMIT latency | `planner.stage.duration_ms{stage=COMMIT}` | 20 ms | 100 ms |
| Total planning | `planner.plan.duration_ms` | 12 s | 30 s |
| Micro-replan latency | `planner.micro_replan.duration_ms` | 8 s | 15 s |
| Plan success rate | `planner.plan.total{outcome=ready}` / `planner.plan.total` | > 95% | -- |
| Token budget utilization | `planner.llm.tokens` sum per plan | ~3.5K | < 4K |

### 22.4 Delta Emissions

Deltas are fire-and-forget cognitive signals emitted via IDeltaEmitPort (Section
15.7) through DeltaBusAdapter to the `k1.planner.delta.v1` topic.  They are
observability signals for the Learning Loop, SessionState subscribers, and
debugging tools -- NOT control-plane messages.

#### 22.4.1 Delta Payload Schema

```yaml
DeltaPayload:                                    # frozen dataclass
  agent_id: str                                  # Always "planner"
  delta_type: str                                # See catalog below
  section: str                                   # "pipeline" | "plan" | "tools"
  data: Dict[str, Any]                           # Type-specific payload
  trace_id: str                                  # cognitive_trace_id (FAB-09)
```

#### 22.4.2 Delta Event Catalog

| delta\_type | section | Emitter | When | data Contents |
| ----------- | ------- | ------- | ---- | ------------- |
| `"stage_transition"` | `"pipeline"` | PipelineController | Stage start | `{stage, status: "started", timestamp_ms}` |
| `"stage_transition"` | `"pipeline"` | PipelineController | Stage complete | `{stage, status: "completed", tokens_used, duration_ms}` |
| `"stage_transition"` | `"pipeline"` | PipelineController | Stage failed | `{stage, status: "failed", error_type, recovery_path}` |
| `"tool_result"` | `"tools"` | ToolCallRouter (via PipelineController) | Tool call returns | `{tool, result_count, latency_ms}` |
| `"hil_event"` | `"pipeline"` | HILCoordinator (via PipelineController) | HIL round starts | `{type: "clarification" or "approval", round, plan_id}` |
| `"hil_event"` | `"pipeline"` | HILCoordinator (via PipelineController) | HIL round ends | `{type: "clarification" or "approval", round, outcome, latency_ms}` |
| `"plan_update"` | `"plan"` | CommitService (via PipelineController) | Plan committed | `{plan_id, step_count, total_tokens, status: "committed"}` |
| `"plan_update"` | `"plan"` | PipelineController | Plan failed | `{request_id, stage, reason, status: "failed"}` |
| `"plan_update"` | `"plan"` | PipelineController | Plan cancelled | `{request_id, reason, status: "cancelled"}` |
| `"plan_end"` | `"pipeline"` | PipelineController | Plan lifecycle ends | `{plan_id, total_tokens, total_duration_ms, outcome}` |
| `"micro_replan"` | `"pipeline"` | PipelineController | Micro-replan completes | `{original_plan_id, outcome, replacement_steps, duration_ms}` |

#### 22.4.3 Emission Points in Pipeline Flow

```text
 Pipeline flow with delta emission markers:

 1. PlanRequest dequeued
    -> (no delta here -- structured log only: plan.received)

 2. Stage 1 SKETCH start
    -> DELTA: stage_transition{stage: "SKETCH", status: "started"}

 3. Tool calls (up to 3)
    -> DELTA: tool_result{tool: "discover_capabilities", ...}  (per call)

 4. LLM call
    -> (no delta -- LLM call details are structured logs only)

 5. Stage 1 complete
    -> DELTA: stage_transition{stage: "SKETCH", status: "completed", tokens_used}

 6. Stage 2 EXPAND start
    -> DELTA: stage_transition{stage: "EXPAND", status: "started"}

 7. (Tool calls, LLM call as above)

 8. Stage 2 complete
    -> DELTA: stage_transition{stage: "EXPAND", status: "completed", tokens_used}

 9. Stage 3 VALIDATE start
    -> DELTA: stage_transition{stage: "VALIDATE", status: "started"}

10. (Deterministic checks, LLM arbiter)

11. Stage 3 complete
    -> DELTA: stage_transition{stage: "VALIDATE", status: "completed", tokens_used}

12. Stage 4 COMMIT start
    -> DELTA: stage_transition{stage: "COMMIT", status: "started"}

13. Plan committed
    -> DELTA: plan_update{plan_id, step_count, status: "committed"}

14. Stage 4 complete
    -> DELTA: stage_transition{stage: "COMMIT", status: "completed"}

15. Plan lifecycle end
    -> DELTA: plan_end{plan_id, total_tokens, total_duration_ms, outcome}
```

#### 22.4.4 Delta vs Structured Log vs Event

| Signal | Transport | Delivery Guarantee | Audience | Blocks Pipeline? |
| ------ | --------- | ------------------ | -------- | ---------------- |
| Structured log | K1 telemetry (local) | Best-effort | Ops dashboards, debugging | No |
| Delta | Delta Bus (`k1.planner.delta.v1`) | Fire-and-forget | Learning Loop, SessionState subscribers | No |
| Event | Event Bus (`k1.planner.plan.*.v1`) | At-least-once | Orchestrator (control plane) | No (async publish) |

**Key distinction**: Deltas carry **partial progress** (stage transitions, tool
results).  Events carry **final outcomes** (plan.ready, plan.failed, plan.cancelled).
Structured logs carry **internal operational detail** (LLM latency, model\_id,
provider\_id) that is too granular for the event bus.

### 22.5 Observability During Error Recovery

When an error recovery path activates, observability output intensifies:

| Recovery Path | Additional Logs | Additional Deltas | Additional Metrics |
| ------------- | --------------- | ----------------- | ------------------ |
| ERR\_SKETCH\_FAIL | `stage.failed`, `stage.retry`, `recovery.fallback` | `stage_transition{status: "failed"}`, then `stage_transition{status: "started"}` (retry) | `planner.recovery.activated{path=ERR_SKETCH_FAIL}`, `planner.stage.total{outcome=retry}` |
| ERR\_EXPAND\_FAIL | `stage.failed`, `stage.retry` or `recovery.fallback` | `stage_transition{status: "failed"}` | `planner.recovery.activated{path=ERR_EXPAND_FAIL}`, `planner.plan.degraded{stage=EXPAND}` |
| ERR\_VALIDATE\_FAIL | `stage.failed`, `recovery.auto_approve` (if arbiter down) | `stage_transition{status: "failed"}` | `planner.recovery.activated{path=ERR_VALIDATE_FAIL}`, `planner.plan.degraded{stage=VALIDATE}` |
| ERR\_COMMIT\_FAIL | `commit.wal_failed` or `commit.event_failed` | `stage_transition{status: "failed"}` | `planner.recovery.activated{path=ERR_COMMIT_FAIL}` |
| ERR\_HIL\_TIMEOUT | `hil.clarification_timeout` or `hil.approval_timeout` | `hil_event{outcome: "timeout"}` | `planner.recovery.activated{path=ERR_HIL_TIMEOUT}`, `planner.hil.rounds{outcome=timeout}` |

### 22.6 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| FAB-09 trace contract | 4.5, 6.1 | trace\_id field definition in PlanRequest |
| IDeltaEmitPort specification | 15.7 | Port contract, DeltaPayload type, fire-and-forget semantics |
| DeltaBusAdapter | 16.1.6 | Production adapter, pre-bound agent\_id, topic |
| IEventPort specification | 15.8 | Published topics (plan.ready, plan.failed, plan.cancelled) |
| Performance targets | 21 | SLI targets that metrics track against |
| CB telemetry (Orchestrator/Model Hub) | 20.8 | CB state change events NOT owned by Planner |
| Error recovery paths | 19 | Recovery-specific observability intensification |
| PipelineController (sole delta emitter) | 17.2 | Centralized emission point for all deltas |

---

## 23. Lifecycle (6 Phases)

The Planner has six lifecycle phases.  Four run during normal operation (INIT,
PLAN\_START, STAGE\_TRANSITION, PLAN\_END).  Two are exceptional (SHUTDOWN,
CRASH\_RECOVERY).  Every phase interacts with specific services and ports, and
every phase drives the Plan FSM (Section 18).

**Source**: planner.mmd LIFECYCLE subgraph (lines 476-498), LIFECYCLE -> SERVICE
DELEGATION edges (lines 768-790), LIFECYCLE -> PORT USAGE edges (lines 796-812),
LIFECYCLE STATE FLOW edges (lines 876-881).

### 23.1 INIT

The INIT phase runs once at PlannerAgent startup.  It creates all 7 internal
services, wires all 7 ports, subscribes to the plan request event, and sets
the Plan FSM to IDLE.

```text
 INIT sequence:

 1. CREATE SERVICES
    PlannerAgent constructs all 7 internal services with their port dependencies:

    ToolCallRouter(
      fabric_port:  IFabricRetrievalPort,
      state_port:   IStateReadPort,
      bridge_port:  IBridgePort,
      max_calls:    6,                       -- PLAN-05
    )

    HILCoordinator(
      llm_port:     ILLMPort,
      event_port:   IEventPort,
      max_rounds:   2,                       -- PLAN-10
    )

    SketchService(
      llm_port:     ILLMPort,
      tool_router:  ToolCallRouter,
      hil_coord:    HILCoordinator,
    )

    ExpandService(
      llm_port:     ILLMPort,
      tool_router:  ToolCallRouter,
    )

    ValidateService(
      llm_port:     ILLMPort,
      hil_coord:    HILCoordinator,
      fabric_port:  IFabricRetrievalPort,    -- capability existence check (PLAN-08)
    )

    CommitService(
      bridge_port:  IBridgePort,
      event_port:   IEventPort,
      delta_port:   IDeltaEmitPort,
    )

    PipelineController(
      sketch:       SketchService,
      expand:       ExpandService,
      validate:     ValidateService,
      commit:       CommitService,
      delta_port:   IDeltaEmitPort,
      event_port:   IEventPort,
    )

 2. WIRE 7 PORTS
    All port references are injected at construction (Section 16).
    No port is fetched lazily or resolved at runtime.

    PORT_MAILBOX      -> MailboxAdapter (bounded queue, depth 5)
    PORT_LLM          -> TestLLMAdapter (V1) / LLMGatewayAdapter (V2)
    PORT_FABRIC_RET   -> FabricRetrievalAdapter (in-process)
    PORT_STATE_READ   -> SessionStateReadAdapter (lock-free)
    PORT_BRIDGE       -> BridgeAdapter (K0 client)
    PORT_DELTA        -> DeltaBusAdapter (fire-and-forget)
    PORT_EVENT        -> EventBusAdapter (pub/sub)

 3. SUBSCRIBE EVENTS
    IEventPort.subscribe("k1.planner.plan.request.v1", _on_plan_request)
    IEventPort.subscribe("k1.planner.plan.cancel.v1", _on_plan_cancel)
    IEventPort.subscribe("k1.hil.clarification_response.v1", _on_hil_clarification)
    IEventPort.subscribe("k1.hil.approval_response.v1", _on_hil_approval)

 4. SET STATE
    Plan FSM -> IDLE
    _plan_lock: asyncio.Lock (released)
    _cancel_set: Set[str] (empty)
    Mailbox: empty, accepting enqueues
```

**Wiring edges** (planner.mmd):

| Edge | Target |
| ---- | ------ |
| `LC_INIT -> SVC_PIPELINE` | Create + wire PipelineController |
| `LC_INIT -> SVC_SKETCH` | Create SketchService |
| `LC_INIT -> SVC_EXPAND` | Create ExpandService |
| `LC_INIT -> SVC_VALIDATE` | Create ValidateService |
| `LC_INIT -> SVC_COMMIT` | Create CommitService |
| `LC_INIT -> SVC_TOOL_ROUTER` | Create ToolCallRouter |
| `LC_INIT -> SVC_HIL` | Create HILCoordinator |
| `LC_INIT -.-> PORT_MAILBOX` | Connect mailbox port |
| `LC_INIT -.-> PORT_EVENT` | Subscribe plan.request event |

**Post-condition**: PlannerAgent enters its mailbox dequeue loop, awaiting the first
PlanRequest.

### 23.2 PLAN\_START

PLAN\_START runs each time a PlanRequest is dequeued from the mailbox.  It acquires
the plan lock, initializes pipeline state, and transitions the FSM from IDLE to
SKETCHING.

```text
 PLAN_START sequence:

 1. MAILBOX DEQUEUE
    PlannerAgent awaits _queue.get() (blocks until PlanRequest available).
    If mailbox is empty: PlannerAgent sleeps on asyncio event.

 2. CANCEL CHECK (pre-execution)
    If dequeued request_id is in _cancel_set:
      -> Remove from _cancel_set
      -> Emit plan.cancelled.v1{request_id, reason: "cancelled_before_start"}
      -> Return to step 1 (do not acquire lock)

 3. ACQUIRE PLAN LOCK
    await _plan_lock.acquire()
    V1: Single plan at a time.  If lock is held (should not happen in V1,
    because dequeue only runs when idle), the agent blocks until released.

 4. INITIALIZE PIPELINE STATE
    PipelineController.reset():
      stage_token_usage   = {SKETCH: 0, EXPAND: 0, VALIDATE: 0, COMMIT: 0}
      tool_call_count     = 0
      hil_round_count     = 0
      current_request     = PlanRequest
      plan_start_time     = now()
    ToolCallRouter.reset():   call_count = 0
    HILCoordinator.reset():   round_count = 0

 5. FSM TRANSITION
    Plan FSM: IDLE -> SKETCHING

 6. LOG
    Structured log: plan.received{request_id, intent (truncated 80 chars), trace_id}
    Structured log: plan.lock_acquired{request_id}
    Structured log: pipeline.started{request_id, timeout_ms}
```

**Wiring edges** (planner.mmd):

| Edge | Target |
| ---- | ------ |
| `LC_PLAN_START -> SVC_PIPELINE` | Acquire lock + execute pipeline |
| `LC_PLAN_START -> SVC_TOOL_ROUTER` | Clear buffers |
| `LC_PLAN_START -> SVC_HIL` | Reset counters |
| `LC_PLAN_START -.-> PORT_MAILBOX` | Dequeue from mailbox |

**Post-condition**: Pipeline execution begins with Stage 1 SKETCH.

### 23.3 STAGE\_TRANSITION

STAGE\_TRANSITION runs between every pipeline stage.  PipelineController advances
the Plan FSM, records token usage, checks for cancellation, and emits a delta.

```text
 STAGE_TRANSITION sequence (runs 3 times per full plan: SKETCH->EXPAND,
 EXPAND->VALIDATE, VALIDATE->COMMIT):

 1. RECORD STAGE COMPLETION
    stage_token_usage[completed_stage] += HubResponse.metadata.usage.total_tokens
    stage_duration_ms = now() - stage_start_time

 2. CHECK CANCEL FLAG
    If current request_id is in _cancel_set:
      -> Plan FSM: current_state -> CANCELLED
      -> Emit plan.cancelled.v1{request_id, reason: "cancelled_between_stages"}
      -> Jump to PLAN_END (skip remaining stages)

 3. ADVANCE FSM
    Plan FSM transitions:
      SKETCHING   -> EXPANDING
      EXPANDING   -> VALIDATING
      VALIDATING  -> COMMITTING

 4. EMIT STAGE DELTA
    IDeltaEmitPort.emit_delta("planner", "stage_transition", "pipeline", {
      stage: completed_stage,
      status: "completed",
      tokens_used: stage_token_usage[completed_stage],
      duration_ms: stage_duration_ms,
    })

 5. LOG
    Structured log: stage.completed{request_id, stage, duration_ms, tokens_used}

 6. INJECT NEXT STAGE BUDGET
    PipelineController stamps the next stage's HubRequest.constraints:
      Stage 2 EXPAND:    {max_tokens: 1024, timeout_ms: 5000, temperature: 0.3}
      Stage 3 VALIDATE:  {max_tokens: 512,  timeout_ms: 3000, temperature: 0.1}
      Stage 4 COMMIT:    (no LLM call -- no budget injection)
    See Section 13.3 for budget table.
```

**Wiring edges** (planner.mmd):

| Edge | Target |
| ---- | ------ |
| `LC_STAGE_TRANSITION -> SVC_PIPELINE` | Log + delta |
| `LC_STAGE_TRANSITION -.-> PORT_DELTA` | Emit delta per stage |
| `LC_STAGE_TRANSITION -> PLAN_FSM` | Stage complete |

**Micro-replan variant**: Only 2 transitions: MICRO\_SKETCH -> MICRO\_EXPAND ->
MICRO\_VALIDATE -> COMMITTING.  Same delta emission pattern.

### 23.4 PLAN\_END

PLAN\_END runs after a plan reaches a terminal state (COMPLETED, FAILED, or
CANCELLED).  It releases resources and returns PlannerAgent to the mailbox
dequeue loop.

```text
 PLAN_END sequence:

 1. EMIT FINAL EVENT (depends on terminal state)

    COMPLETED:
      CommitService has already emitted:
        k1.planner.plan.ready.v1{CommittedPlan payload}
        k1.planner.delta.v1{stage: "COMMIT", status: "completed", plan_id}

    FAILED:
      PipelineController has already emitted:
        k1.planner.plan.failed.v1{request_id, stage, error_code, partial_state}
        k1.planner.delta.v1{type: "plan_failed", stage, error_code}

    CANCELLED:
      PipelineController has already emitted:
        k1.planner.plan.cancelled.v1{request_id, reason}
        k1.planner.delta.v1{type: "plan_cancelled", request_id}

 2. RELEASE PLAN LOCK
    _plan_lock.release()
    V1: Immediately allows next dequeued request to proceed.

 3. CLEAR PIPELINE STATE
    PipelineController.clear():
      stage_token_usage   = cleared
      tool_call_count     = 0
      hil_round_count     = 0
      current_request     = None
      plan_start_time     = None
    ToolCallRouter:    call_count = 0
    HILCoordinator:    round_count = 0

 4. EMIT PLAN_END DELTA
    IDeltaEmitPort.emit_delta("planner", "plan_end", "pipeline", {
      plan_id:            plan_id (or None if FAILED/CANCELLED),
      total_tokens:       sum(stage_token_usage.values()),
      total_duration_ms:  now() - plan_start_time,
      outcome:            "ready" | "failed" | "cancelled",
    })

 5. FSM TRANSITION
    Plan FSM: terminal_state -> IDLE
    (COMPLETED -> IDLE, FAILED -> IDLE, CANCELLED -> IDLE)

 6. LOG
    Structured log: plan.completed{request_id, plan_id, total_duration_ms,
                                    total_tokens, outcome}

 7. RESUME MAILBOX LOOP
    PlannerAgent returns to PLAN_START step 1 (await _queue.get()).
```

**Wiring edges** (planner.mmd):

| Edge | Target |
| ---- | ------ |
| `LC_PLAN_END -> SVC_COMMIT` | Emit plan + release lock |
| `LC_PLAN_END -.-> PORT_EVENT` | Emit plan.ready (if COMPLETED) |
| `LC_PLAN_END -.-> PORT_BRIDGE` | Persist to WAL (if COMPLETED) |
| `LC_PLAN_END -> PLAN_FSM` | Plan delivered |

### 23.5 SHUTDOWN

SHUTDOWN runs when the PlannerAgent receives a process-level shutdown signal
(e.g., K1 runtime termination, container stop).  It aims to minimize data loss
and leave the system in a recoverable state.

```text
 SHUTDOWN sequence:

 1. STOP ACCEPTING NEW REQUESTS
    MailboxAdapter rejects all new enqueue() calls with ShutdownError.
    PlannerAdapter (Orchestrator side) sees AdapterException(SHUTTING_DOWN).

 2. DRAIN MAILBOX QUEUE
    For each queued PlanRequest:
      Emit plan.cancelled.v1{request_id, reason: "shutdown"}
      Remove from queue.
    This ensures the Orchestrator's PendingPlanContext timeout reaper can clean up.

 3. CANCEL IN-FLIGHT PLAN (if any)
    If a plan is currently executing:
      a. Set cancel flag for current request_id
      b. PipelineController checks flag at next await boundary
      c. On detection: Plan FSM -> CANCELLED, emit plan.cancelled.v1
      d. If mid-LLM call: LLMGatewayAdapter cancels async wait
         (Model Hub handles provider-side cancellation)

 4. FLUSH PENDING DELTAS
    IDeltaEmitPort: flush any buffered deltas to Delta Bus.
    Best-effort -- if bus is unavailable, deltas are dropped.

 5. PERSIST PARTIAL PLAN STATE (for crash recovery)
    If a plan was in-flight:
      IBridgePort.persist_plan(partial_committed_plan)
      Partial plan includes: request_id, completed stages, current stage,
      stage outputs (SketchResult, ExpandedPlan if available).
      Fire-and-forget: shutdown does not block on persist.

 6. RELEASE PLAN LOCK
    _plan_lock.release() if held.

 7. UNSUBSCRIBE EVENTS
    IEventPort.unsubscribe() for all 4 subscriptions.

 8. LOG
    Structured log: shutdown.complete{plans_drained, in_flight_cancelled, deltas_flushed}
```

**Wiring edges** (planner.mmd):

| Edge | Target |
| ---- | ------ |
| `LC_SHUTDOWN -> SVC_PIPELINE` | Cancel in-flight, flush deltas |
| `LC_SHUTDOWN -.-> PORT_DELTA` | Flush deltas |
| `LC_SHUTDOWN -.-> PORT_LLM` | Cancel LLM calls |
| `LC_SHUTDOWN -> PLAN_FSM` | Process exit |

**Timing**: Graceful shutdown has a configurable timeout (default 5 s).  If the
in-flight plan does not reach a terminal state within 5 s, the agent force-cancels
and proceeds to steps 4-8 without waiting.

### 23.6 CRASH\_RECOVERY

CRASH\_RECOVERY runs when PlannerAgent starts and detects that a previous
instance may have crashed mid-plan.  It checks K0 WAL for partial plan state
and either resumes or discards.

```text
 CRASH_RECOVERY sequence (runs during INIT, before entering mailbox loop):

 1. CHECK WAL FOR IN-FLIGHT PLAN
    IBridgePort.recall(query="planner_in_flight", selectors=["partial_plan"])
    Returns: List[RecallResult]

    If empty: no crash recovery needed -> proceed to mailbox loop.

 2. EVALUATE PARTIAL STATE
    For each partial plan found in WAL:
      a. Read last completed stage (SKETCH, EXPAND, VALIDATE, or none)
      b. Read partial outputs (SketchResult, ExpandedPlan)
      c. Check staleness: if plan_start_time + 120s < now(), discard
         (plan is too old to be useful -- context has drifted)

 3a. RESUME AT LAST COMPLETED STAGE (if not stale)
     If last completed stage == SKETCH:
       Resume pipeline at EXPAND with saved SketchResult.
     If last completed stage == EXPAND:
       Resume pipeline at VALIDATE with saved ExpandedPlan.
     If last completed stage == VALIDATE:
       Resume pipeline at COMMIT.

     Resume means: Plan FSM -> appropriate state, PipelineController
     runs remaining stages normally.

     Trace_id: The original PlanRequest.trace_id is preserved from WAL.

 3b. DISCARD PARTIAL STATE (if stale or unrecoverable)
     If no completed stages or plan is too old:
       Emit plan.failed.v1{request_id, reason: "crash_recovery_discard",
                           stage: last_known_stage}
       Clear partial plan from WAL.
       Plan FSM -> IDLE

 4. EMIT RECOVERY DELTA
    IDeltaEmitPort.emit_delta("planner", "crash_recovery", "pipeline", {
      action: "resumed" | "discarded",
      request_id: original_request_id,
      last_stage: last_completed_stage,
      staleness_ms: now() - plan_start_time,
    })

 5. LOG
    Structured log: crash_recovery.complete{action, request_id, last_stage,
                                             staleness_ms}
```

**Wiring edges** (planner.mmd):

| Edge | Target |
| ---- | ------ |
| `LC_CRASH_RECOVERY -> SVC_PIPELINE` | Check WAL + resume |
| `LC_CRASH_RECOVERY -> SVC_COMMIT` | Restore state |
| `LC_CRASH_RECOVERY -.-> PORT_BRIDGE` | Check WAL |
| `LC_CRASH_RECOVERY -.-> PORT_DELTA` | Emit recovery delta |
| `LC_CRASH_RECOVERY -> PLAN_FSM` | Recovered |

**V1 simplification**: V1 does NOT implement full crash recovery.  If the process
restarts, any in-flight plan is treated as lost.  The Orchestrator's stale-context
reaper (45 s timeout) emits a DEGRADED event and the task is re-dispatched at MEDIUM
tier.  Full crash recovery (stages 2-3) is a V2 feature requiring reliable WAL
reads from K0.

### 23.7 Lifecycle Phase Summary

| Phase | Trigger | Frequency | FSM Effect | Key Ports Used |
| ----- | ------- | --------- | ---------- | -------------- |
| INIT | PlannerAgent startup | Once | -> IDLE | IEventPort (subscribe), all 7 ports wired |
| PLAN\_START | PlanRequest dequeued | Per plan | IDLE -> SKETCHING | IMailboxPort (dequeue) |
| STAGE\_TRANSITION | Stage N completes | 3 per plan (2 for micro-replan) | State -> next state | IDeltaEmitPort (delta) |
| PLAN\_END | Terminal state reached | Per plan | Terminal -> IDLE | IEventPort (publish), IBridgePort (WAL), IDeltaEmitPort (plan\_end) |
| SHUTDOWN | Process exit signal | Once | -> (terminated) | IDeltaEmitPort (flush), ILLMPort (cancel) |
| CRASH\_RECOVERY | Startup + WAL check | Once (if partial plan found) | -> IDLE or resume | IBridgePort (WAL read), IDeltaEmitPort (recovery delta) |

### 23.8 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| Pipeline flow (full 26-step walkthrough) | 5.2 | Steps 1-26 map to PLAN\_START through PLAN\_END |
| PipelineController constructor and behaviors | 17.2 | Service that implements stage sequencing |
| Plan State Machine states and transitions | 18 | FSM transitions driven by each lifecycle phase |
| Terminal states (COMPLETED, FAILED, CANCELLED) | 18.5 | Side effects at each terminal entry |
| Cancel semantics (cooperative) | 18.5.3 | Cancel flag checked in STAGE\_TRANSITION |
| MailboxAdapter (queue, lock, cancel\_set) | 16.1.1 | Internal state managed across lifecycle phases |
| PlannerAgent constructor (\_plan\_lock) | 16.1.1 | Lock acquire/release in PLAN\_START/PLAN\_END |
| Observability (logs, deltas, metrics per phase) | 22 | Per-phase structured log and delta catalog |

---

## 24. Concurrency Model

The Planner runs as a single-threaded async actor.  V1 enforces one plan at a
time via an `asyncio.Lock`.  The mailbox queues additional requests.  Cancellation
is cooperative (flag-based, checked between stages).  Micro-replan waits for the
current plan to complete before running.

**Source**: planner.mmd CONCURRENCY subgraph (lines 504-518).

### 24.1 V1: Single Plan

V1 uses `asyncio` cooperative multitasking within a single Python event loop.
There is no thread pool, no multiprocessing, no parallel plan execution.

#### 24.1.1 Plan Lock

```text
 _plan_lock: asyncio.Lock

 Acquired:  PLAN_START step 3 (after mailbox dequeue)
 Released:  PLAN_END step 2 (after terminal state reached)

 Semantics:
   - Exclusive: only one plan pipeline runs at a time
   - Non-reentrant: PlannerAgent never re-acquires during a plan
   - Fair: asyncio.Lock is FIFO for waiters (but V1 has at most 1 waiter
     because micro_replan is the only code that might await the lock
     while a plan is in flight)
```

#### 24.1.2 Execution Model

```text
 PlannerAgent event loop:

 while not shutdown:
   request = await _mailbox.dequeue()      # Blocks until request available
   if request.request_id in _cancel_set:
     emit plan.cancelled.v1
     continue

   await _plan_lock.acquire()
   try:
     await _pipeline.execute(request)       # Runs SKETCH -> EXPAND -> VALIDATE -> COMMIT
   finally:
     _plan_lock.release()
     # PLAN_END cleanup (clear state, emit plan_end delta)
```

All pipeline stages run sequentially within `_pipeline.execute()`.  Each stage
contains async calls (LLM, tools, HIL) that yield to the event loop at `await`
points.  Between stages, PipelineController checks the cancel flag.

#### 24.1.3 Mailbox Queuing Under Load

When a plan is in flight and new PlanRequests arrive:

| Event | Behavior |
| ----- | -------- |
| Orchestrator calls `enqueue(PlanRequest)` | Queued in `_queue` (FIFO, max depth 5) |
| Queue depth reaches 5 | `enqueue()` raises `MailboxFullError` -> PlannerAdapter returns `PlanAck(REJECTED)` -> CB\_PLANNER counts as failure |
| Current plan completes | PlannerAgent dequeues next request from `_queue` |
| Multiple requests queued | Processed in FIFO order (no priority weighting in V1) |

#### 24.1.4 Why Single Plan?

The V1 single-plan constraint simplifies:

- **State isolation**: No risk of cross-contamination between plans
- **Token budgeting**: PLAN-11 per-stage budgets apply to the single active plan
- **Tool call counting**: PLAN-05 (max 6 tools) is per-plan, no shared counter
- **HIL routing**: Only one plan can be in HIL clarification/approval at a time
- **Cancel semantics**: Cancel flag applies to one plan unambiguously
- **Testing**: No concurrent race conditions to test in V1

### 24.2 Cancellation Support

Cancellation is cooperative -- the Planner checks a flag at defined checkpoints
rather than being preempted.

#### 24.2.1 Cancel Protocol

```text
 1. Orchestrator decides to cancel (timeout, user abort, task superseded)
 2. PlannerAdapter.cancel_plan(request_id)
      NOTE: cancel_plan() does NOT check CB_PLANNER (always attempted)
 3. PlannerAdapter calls IPlannerMailbox.send_cancel(request_id)
 4. MailboxAdapter adds request_id to _cancel_set: Set[str]
 5. PipelineController checks _cancel_set at defined checkpoints
 6. If match: Plan FSM -> CANCELLED
```

#### 24.2.2 Cancel Checkpoints

| Checkpoint | Location | Timing |
| ---------- | -------- | ------ |
| Pre-execution | Mailbox dequeue (PLAN\_START step 2) | Before lock acquired |
| Between SKETCH and EXPAND | PipelineController stage transition | After SKETCH LLM returns |
| Between EXPAND and VALIDATE | PipelineController stage transition | After EXPAND LLM returns |
| Between VALIDATE and COMMIT | PipelineController stage transition | After VALIDATE arbiter returns |
| Before WAL persist | CommitService (COMMIT stage) | Before IBridgePort.persist\_plan() |

**Not a checkpoint**: Mid-LLM call.  If an LLM call is in flight, the cancel flag
is not checked until the LLM returns (or times out).  The LLM call completes (or
errors), then PipelineController detects the cancel flag.

#### 24.2.3 Cancel Side Effects

When cancellation is detected:

```text
 1. Plan FSM: current_state -> CANCELLED
 2. Emit k1.planner.plan.cancelled.v1 {
      request_id: str,
      reason: "cancelled_before_start" | "cancelled_between_stages" | "cancelled_before_persist",
      stage: last_completed_stage,
      trace_id: str,
    }
 3. Emit k1.planner.delta.v1{type: "plan_cancelled", request_id, reason}
 4. Continue to PLAN_END (lock release, state clear)
```

**Partial results discarded**: Any partial outputs (SketchResult, ExpandedPlan) are
dropped.  The Orchestrator cannot use partial plan outputs from a cancelled plan.

#### 24.2.4 Cancel Edge Cases

| Scenario | Outcome |
| -------- | ------- |
| Cancel after COMPLETED (plan.ready already emitted) | No-op: plan already delivered, cancel has no effect |
| Cancel after FAILED (plan.failed already emitted) | No-op: plan already in terminal state |
| Cancel for unknown request\_id | `send_cancel()` adds to \_cancel\_set but no match ever found; set is cleared on PLAN\_END |
| Cancel arrives before enqueue | request\_id in \_cancel\_set; when PlanRequest dequeues, immediate cancel at PLAN\_START step 2 |
| Double cancel (same request\_id) | Idempotent: \_cancel\_set is a Set, second add has no effect |

### 24.3 Micro-Replan Concurrency

Micro-replan uses a different concurrency path than `request_plan()`.

#### 24.3.1 V1 Behavior

```text
 PlannerAdapter.micro_replan(MicroReplanRequest):
   1. CB_PLANNER check (OPEN -> raise immediately)
   2. Call IPlannerMailbox.micro_replan(request)
   3. MailboxAdapter.micro_replan():
      a. await _plan_lock.acquire()          -- BLOCKS until current plan completes
      b. PipelineController.micro_replan(request)
      c. _plan_lock.release()
      d. Return Optional[CommittedPlan]
```

**Key difference from request\_plan()**:

| Aspect | request\_plan() | micro\_replan() |
| ------ | --------------- | --------------- |
| Delivery | Fire-and-forget + event bus | Synchronous return |
| Queuing | FIFO in \_queue | Direct \_plan\_lock acquire (bypasses queue) |
| Timeout | 45 s (Orchestrator-side) | 10 s (caller-side) |
| CB check | Yes (CB\_PLANNER) | Yes (CB\_PLANNER) |
| Priority | INTERACTIVE | Elevated (bypasses queue, waits for lock) |
| On failure | plan.failed.v1 event | Returns None |
| Concurrent with plan | Queues behind current plan | Waits for lock, then runs exclusively |

#### 24.3.2 Micro-Replan Under Load

If a plan is currently in flight and micro\_replan() is called:

```text
 Timeline:
   T0:  Plan A (request_plan) is in EXPANDING stage
   T1:  micro_replan() called for Plan A (DAG mid-execution failure)
   T2:  micro_replan() awaits _plan_lock (blocked)
   ...
   T10: Plan A might still be running (hasn't completed yet)
   T11: micro_replan() 10s timeout expires on CALLER side
   T12: Caller: PlannerAdapter.micro_replan() returns None (timeout)
         Orchestrator: continues with original plan

   Eventually:
   T20: Plan A completes, _plan_lock released
         micro_replan() is no longer waiting (caller already timed out)
```

In V1, this means micro\_replan effectively cannot run while any plan is in
flight.  The 10 s timeout is shorter than most full plans (12 s P50), so micro-replan
will almost always time out if called during an active plan.  This is by design --
the Orchestrator falls back to the original plan.

#### 24.3.3 V1 Micro-Replan Ordering Guarantee

Because micro\_replan() acquires \_plan\_lock and bypasses the queue:

- It runs AFTER the current plan completes (if any)
- It runs BEFORE any queued PlanRequests (lock is acquired directly)
- Only one micro-replan can be pending at a time (Orchestrator sends max 1 per DAG)

### 24.4 V2: Multi-Plan (Future)

V2 concurrency is not yet designed.  The planner.mmd notes the direction:

```text
 V2: Multi-plan concurrent pipeline
 with per-plan state isolation
```

#### 24.4.1 V2 Design Constraints

Any V2 multi-plan design must preserve:

| Invariant | V1 Enforcement | V2 Challenge |
| --------- | -------------- | ------------ |
| PLAN-05 (max 6 tool calls per plan) | Single ToolCallRouter counter | Per-plan ToolCallRouter instance or per-plan counter |
| PLAN-10 (max 2 HIL rounds per plan) | Single HILCoordinator counter | HIL routing must correlate responses to correct plan |
| PLAN-11 (per-stage budget) | PipelineController budget injection | Per-plan PipelineController instance |
| PLAN-04 (45 s timeout) | Single timer per plan | Multiple concurrent timers |
| Plan FSM | Single FSM instance | Per-plan FSM instance |

#### 24.4.2 V2 Likely Architecture

```text
 V2 candidate pattern (not committed):

   PlannerAgent
     _active_plans: Dict[request_id, PlanContext]
     _max_concurrent: int = 3                     -- configurable

   PlanContext (per-plan isolated state):
     pipeline_controller: PipelineController
     plan_fsm: PlanStateMachine
     tool_call_count: int
     hil_round_count: int
     stage_token_usage: Dict[str, int]
     cancel_flag: bool

   Mailbox dequeue:
     if len(_active_plans) < _max_concurrent:
       dequeue next PlanRequest
       create PlanContext
       spawn asyncio.Task for pipeline execution

   Shared resources (must be thread-safe):
     ILLMPort (Model Hub handles concurrent calls)
     IFabricRetrievalPort (Fabric Retrieval is stateless)
     IStateReadPort (multi-reader, lock-free by design)
     IBridgePort (K0 Bridge handles concurrent requests)
     IDeltaEmitPort (fire-and-forget, thread-safe)
     IEventPort (bus is multi-publisher)
```

V2 decisions will be captured in a dedicated ADR when implementation is planned.

### 24.5 Thread Safety Summary

| Component | Thread-Safe? | Mechanism |
| --------- | ------------ | --------- |
| MailboxAdapter.\_queue | Yes | `asyncio.Queue` (task-safe) |
| MailboxAdapter.\_cancel\_set | Yes (V1) | Single event loop, no concurrent mutation |
| \_plan\_lock | Yes | `asyncio.Lock` (FIFO, task-safe) |
| PipelineController | No (by design) | V1: single plan, never concurrent access |
| ToolCallRouter | No (by design) | V1: single plan, counter resets per plan |
| HILCoordinator | No (by design) | V1: single plan, round counter resets per plan |
| All port adapters | Yes | Adapters wrap external resources that handle concurrency |

### 24.6 Cross-Reference Summary

| Topic | Section | Relevance |
| ----- | ------- | --------- |
| MailboxAdapter (\_queue, \_cancel\_set, \_plan\_lock) | 16.1.1 | Internal state and thread safety |
| PlannerAgent mailbox loop | 23.2 | PLAN\_START dequeue and lock acquisition |
| Cancel semantics in FSM | 18.5.3 | CANCELLED state entry paths and side effects |
| Micro-replan protocol | 10 | Full micro-replan pipeline and 10 s timeout |
| PlannerAdapter CB check on micro\_replan | 4.3 | CB\_PLANNER wrapping for both request\_plan and micro\_replan |
| PLAN-05 tool budget | 12.1 | Max 6 discovery calls, enforced per plan |
| PLAN-10 HIL rounds | 12.3 | Max 2 rounds, enforced per plan |

---

## 25. External Touchpoints Summary

### 25.1 Inbound (who sends TO Planner)

| Source | Message | Channel | When |
| ------ | ------- | ------- | ---- |
| Orchestrator | PlanRequest | Planner Mailbox (via PlannerAdapter.request\_plan()) | HIGH-tier task dispatch |
| Orchestrator | MicroReplanRequest | Direct call (via PlannerAdapter.micro\_replan()) | Mid-DAG replan (ORCH-13) |
| Orchestrator | cancel\_plan(request\_id) | Direct call (via PlannerAdapter.cancel\_plan()) | Timeout, user abort, task superseded |
| Event Bus | HILClarificationResponse | k1.hil.clarification\_response.v1 | User answers clarification |
| Event Bus | HILApprovalResponse | k1.hil.approval\_response.v1 | User approves/modifies/rejects plan |

### 25.2 Outbound (who Planner sends TO)

| Destination | Message | Channel | When |
| ----------- | ------- | ------- | ---- |
| Orchestrator | PlanAck | Sync return via mailbox ack | Immediate on request receipt |
| Orchestrator | CommittedPlan | k1.planner.plan.ready.v1 via Event Bus | Plan completed (Stage 4) |
| Orchestrator | plan.failed payload | k1.planner.plan.failed.v1 via Event Bus | Planning failed at any stage |
| Orchestrator | plan.cancelled payload | k1.planner.plan.cancelled.v1 via Event Bus | Plan cancelled |
| Model Hub | HubRequest | ILLMPort -> LLM Request Bus | 3 LLM stages + 2 HIL prompts |
| Fabric Retrieval | discover/find queries | IFabricRetrievalPort (direct call) | SKETCH + EXPAND |
| SessionState | read\_sections queries | IStateReadPort (multi-reader, lock-free) | SKETCH (via ToolCallRouter) |
| K0 Bridge | recall\_for\_planning | IBridgePort.recall() | SKETCH (via ToolCallRouter) |
| K0 Bridge | persist\_plan | IBridgePort.persist\_plan() (fire-and-forget) | COMMIT |
| Delta Bus | planning deltas | IDeltaEmitPort -> k1.planner.delta.v1 | Per-stage progress (fire-and-forget) |
| Concierge (via Event Bus) | HIL clarification | k1.hil.clarification.v1 | Stage 1 ambiguous intent |
| Concierge (via Event Bus) | HIL approval request | k1.hil.approval\_request.v1 | Stage 3 high-impact plan |
| Learning Loop (telemetry) | micro\_replan.ready | k1.planner.micro\_replan.ready.v1 via Event Bus | Micro-replan completed (telemetry-only, not delivery) |

### 25.3 Reads (what Planner reads FROM)

| Source | What | How |
| ------ | ---- | --- |
| SessionState | beliefs\_active, persona, control, temporal | IStateReadPort -- multi-reader, lock-free (PLAN-01) |
| Fabric Retrieval | Available capabilities + prompt templates | IFabricRetrievalPort -- in-process direct call, read-only |
| K0 Bridge | Long-term memory (preferences, outcomes) | IBridgePort.recall() -- cross-kernel read path |

---

## 26. Delta Bus & Event Bus Integration

The Planner uses two separate pub/sub channels.  The **Delta Bus** carries
fire-and-forget cognitive deltas (`k1.planner.delta.v1`).  The **Event Bus**
carries lifecycle events (plan.ready, plan.failed, plan.cancelled) and HIL
messages.  These are distinct transports with different delivery guarantees
(Section 22.4.4).

### 26.1 Delta Bus: What Planner Emits

All deltas flow through IDeltaEmitPort -> DeltaBusAdapter -> `k1.planner.delta.v1`
topic.  PipelineController is the sole emitter.  Fire-and-forget: delta loss is
acceptable.

| delta\_type | section | When | data Contents |
| ----------- | ------- | ---- | ------------- |
| `"stage_transition"` | `"pipeline"` | Stage start | `{stage, status: "started", timestamp_ms}` |
| `"stage_transition"` | `"pipeline"` | Stage complete | `{stage, status: "completed", tokens_used, duration_ms}` |
| `"stage_transition"` | `"pipeline"` | Stage failed | `{stage, status: "failed", error_type, recovery_path}` |
| `"tool_result"` | `"tools"` | Tool call returns | `{tool, result_count, latency_ms}` |
| `"hil_event"` | `"pipeline"` | HIL round starts/ends | `{type, round, plan_id, outcome, latency_ms}` |
| `"plan_update"` | `"plan"` | Plan committed | `{plan_id, step_count, total_tokens, status: "committed"}` |
| `"plan_update"` | `"plan"` | Plan failed | `{request_id, stage, reason, status: "failed"}` |
| `"plan_update"` | `"plan"` | Plan cancelled | `{request_id, reason, status: "cancelled"}` |
| `"plan_end"` | `"pipeline"` | Plan lifecycle ends | `{plan_id, total_tokens, total_duration_ms, outcome}` |
| `"micro_replan"` | `"pipeline"` | Micro-replan completes | `{original_plan_id, outcome, replacement_steps, duration_ms}` |
| `"crash_recovery"` | `"pipeline"` | Crash recovery runs | `{action, request_id, last_stage, staleness_ms}` |

**Consumers**: Learning Loop (drift detection), SessionState subscribers
(optional delta incorporation), debugging/tracing tools.

**Deep dive**: Section 22.4 (Delta Emissions).

### 26.2 Event Bus: What Planner Publishes

All events flow through IEventPort -> EventBusAdapter -> K1 Event Bus.
At-least-once delivery for lifecycle events.

| Topic | Emitter | Payload | When |
| ----- | ------- | ------- | ---- |
| `k1.planner.plan.ready.v1` | CommitService | CommittedPlan (full) | Plan committed + WAL persisted |
| `k1.planner.plan.failed.v1` | PipelineController | `{request_id, stage, error_code, error_message, partial_state, tokens_used, duration_ms, trace_id}` | Pipeline failed at any stage |
| `k1.planner.plan.cancelled.v1` | PipelineController | `{request_id, reason, stage, trace_id}` | Cancel received and honored |
| `k1.planner.micro_replan.ready.v1` | PipelineController | Partial CommittedPlan | Micro-replan completed (TELEMETRY-ONLY, not delivery) |
| `k1.hil.clarification.v1` | HILCoordinator | `{request_id, question, context, trace_id}` | Stage 1 ambiguous intent |
| `k1.hil.approval_request.v1` | HILCoordinator | `{request_id, summary, options, side_effects, safety_assessment}` | Stage 3 high-impact plan |

**Primary consumer**: Orchestrator (`plan.ready` for DAG execution, `plan.failed`
and `plan.cancelled` for PendingPlanContext cleanup).

**Secondary consumer**: Learning Loop (`plan.failed`, `plan.cancelled` for drift
detection -- see `k1/learning/learning.mmd`).

### 26.3 Event Bus: What Planner Subscribes To

| Topic | Subscriber | Handler | Response To |
| ----- | ---------- | ------- | ----------- |
| `k1.hil.clarification_response.v1` | HILCoordinator | Correlate by `request_id`, unblock SKETCH | User answers clarification |
| `k1.hil.approval_response.v1` | HILCoordinator | Correlate by `request_id`, unblock VALIDATE | User approves/modifies/rejects |

### 26.4 Delta Bus vs Event Bus Summary

| Aspect | Delta Bus | Event Bus |
| ------ | --------- | --------- |
| Topic | `k1.planner.delta.v1` | `k1.planner.plan.*.v1`, `k1.hil.*` |
| Transport | IDeltaEmitPort -> DeltaBusAdapter | IEventPort -> EventBusAdapter |
| Delivery | Fire-and-forget (best-effort) | At-least-once (lifecycle events) |
| Blocks pipeline? | Never | Never (async publish) |
| Audience | Learning Loop, SessionState, debugging | Orchestrator (control plane), Concierge (HIL) |
| Carries | Partial progress (stage transitions, tool results) | Final outcomes (plan.ready, plan.failed, plan.cancelled) |

---

## 27. Relationship to Other Components

Seven external components interact with the Planner.  Each relationship is
mediated by a hexagonal port (Section 15) and a production adapter (Section 16).
This section describes the interaction protocol, data flow, and ownership
boundaries for each relationship.

### 27.1 Planner <-> Orchestrator

The Orchestrator is the Planner's sole caller and primary consumer.

```text
 Interaction pattern: Async request -> event-based delivery
 Port (Orchestrator side): IPlannerPort (implemented by PlannerAdapter)
 CB protection: CB_PLANNER (Orchestrator-owned, Section 20.2)

 Request flow:
   Orchestrator._dispatch_high()
     -> PlannerAdapter.request_plan(PlanRequest)
     -> CB_PLANNER check (OPEN -> raise, CLOSED -> proceed)
     -> IPlannerMailbox.enqueue(PlanRequest)
     -> PlanAck{ACCEPTED} returned synchronously
     -> Orchestrator saves PendingPlanContext{request_id}

 Delivery flow (asynchronous, decoupled):
   Planner runs 4-stage pipeline -> emits one of:
     k1.planner.plan.ready.v1     -> CommittedPlan
     k1.planner.plan.failed.v1    -> {request_id, reason, stage}
     k1.planner.plan.cancelled.v1 -> {request_id, reason}
   Orchestrator correlates via request_id -> PendingPlanContext

 Cancel flow:
   PlannerAdapter.cancel_plan(request_id)  -- no CB check, always attempted
   -> IPlannerMailbox.send_cancel(request_id)
   -> PipelineController checks cancel flag between stages

 Micro-replan flow (synchronous, 10s timeout):
   PlannerAdapter.micro_replan(MicroReplanRequest)
   -> CB_PLANNER check
   -> IPlannerMailbox.micro_replan(request)  -- acquires _plan_lock
   -> Returns Optional[CommittedPlan] directly (no event bus)
   -> Telemetry: k1.planner.micro_replan.ready.v1 (observers only)
```

**Ownership boundary**: The Orchestrator owns PlannerAdapter, CB\_PLANNER
configuration, PendingPlanContext lifecycle, and tier degradation policy.  The
Planner owns the pipeline, plan FSM, error recovery, and all internal services.

**Deep dive**: Section 4 (Interface with Orchestrator).

### 27.2 Planner <-> Model Hub

Model Hub provides all LLM capabilities.  The Planner does NOT select models
or manage providers.

```text
 Interaction pattern: Async request-reply via LLM Request Bus
 Port (Planner side): ILLMPort
 Adapter: LLMGatewayAdapter (V2) / TestLLMAdapter (V1)
 CB protection: CB_LLM_INHERIT (Model Hub-owned, per-provider, Section 20.3)

 Call flow:
   Stage service (Sketch/Expand/Validate/HIL)
     -> ILLMPort.execute(HubRequest)
     -> LLMGatewayAdapter stamps consumer_id = "planner" (MH-11 cost tracking)
     -> LLM_REQUEST_BUS -> Model Hub RequestRouter
     -> ModelSelector picks provider (Planner has no say)
     -> Provider executes, returns HubResponse
     -> LLMGatewayAdapter returns HubResponse to stage service

 Capabilities used:
   CHAT          -- Stages 1-3 main LLM calls + HIL prompt generation
   STRUCTURED    -- Stage 3 arbiter verdict (V2)
   TOOL_CALL     -- Stages 1-2 tool routing (V2)

 Budget per plan: ~3.5K tokens total
   Stage 1 SKETCH:   max_tokens=2048, timeout_ms=8000
   Stage 2 EXPAND:   max_tokens=1024, timeout_ms=5000
   Stage 3 VALIDATE: max_tokens=512,  timeout_ms=3000
   HIL prompts:      max_tokens=300,  timeout_ms=3000
```

**Ownership boundary**: Model Hub owns model selection, provider CB management,
cost enforcement (MH-04), and rate limiting.  The Planner owns prompt construction,
output parsing, and per-stage budget injection (PLAN-11).

**Deep dive**: Section 13 (LLM Integration), Section 16.1.2 (LLMGatewayAdapter).

### 27.3 Planner <-> Fabric Retrieval

Fabric Retrieval provides read-only capability and prompt discovery.

```text
 Interaction pattern: In-process direct method call (NOT HTTP, NOT event-based)
 Port (Planner side): IFabricRetrievalPort
 Adapter: FabricRetrievalAdapter
 CB protection: None (in-process call; failure means Fabric itself is broken)

 Methods used:
   discover_capabilities(domain, intent, safety_band, session_context, top_k)
     -> RetrievalResult[] (Top-K scored capabilities)
     -> Used in SKETCH (3 calls) and EXPAND (up to 3 calls)
     -> Timeout: 50ms per call, retry once on failure

   find_relevant_prompts(intent, domain, safety_band, top_k)
     -> RetrievalResult[] (Top-K prompt templates with variable definitions)
     -> Used in EXPAND
     -> Timeout: 50ms per call, retry once on failure

 Failure handling:
   Timeout or exception: return empty RetrievalResult (degraded, not fatal)
   Impact: fewer capabilities known, less precise plan
```

**Ownership boundary**: Fabric owns capability registry, embedding index, and
retrieval ranking.  The Planner owns query construction and result interpretation.

**Deep dive**: Section 12.1 (Discovery Tools), Section 16.1.3 (FabricRetrievalAdapter).

### 27.4 Planner <-> SessionState

SessionState provides hot-tier context for plan grounding.

```text
 Interaction pattern: In-process read-only access
 Port (Planner side): IStateReadPort
 Adapter: SessionStateReadAdapter (pre-bound session_id)
 CB protection: None (in-process, lock-free)

 Methods used:
   read_sections(sections: List[str]) -> Dict[str, Dict]
   get_snapshot() -> SessionSnapshot

 Sections consumed (SKETCH stage):
   beliefs_active  -- entities, relationships, facts -> ground plan in known facts
   persona         -- tone, formality -> shape LLM prompt style
   control         -- safety_band, preferences -> constrain capability selection
   temporal        -- time, timezone, schedules -> time-aware step sequencing

 PLAN-01 enforcement:
   IStateReadPort has NO write methods.
   The Planner NEVER writes to SessionState directly.
   Cognitive deltas go to the Delta Bus, not SessionState.
   SessionState subscribers MAY incorporate deltas, but the Planner has no
   knowledge of this.

 Failure handling:
   SessionState unavailable: return empty Dict
   Individual section missing: omitted from result dict
   Impact: degraded context, less precise plan
```

**Ownership boundary**: SessionState owns data storage, section schemas, and
concurrency control.  The Planner owns which sections to read and how to
interpret them for prompt construction.

**Deep dive**: Section 6.1 (SKETCH Inputs), Section 16.1.4 (SessionStateReadAdapter).

### 27.5 Planner <-> K0 Bridge

The K0 Bridge provides two-path access to the cross-kernel layer.

```text
 Interaction pattern: Cross-kernel RPC (via Fabric Bridge port)
 Port (Planner side): IBridgePort
 Adapter: BridgeAdapter
 CB protection: None (Bridge has its own resilience)

 Path 1 -- Read (SKETCH stage):
   IBridgePort.recall(query, selectors) -> RecallResponse
   Used by: ToolCallRouter (routed by discover tool call #3)
   Content: long-term memory (user preferences, past outcomes, entity history)
   Timeout: 500ms
   Failure: return empty RecallResponse (degraded context)

 Path 2 -- Write (COMMIT stage):
   IBridgePort.persist_plan(CommittedPlan) -> void
   Fire-and-forget: CommitService does NOT await confirmation
   Purpose: WAL durability insurance (plan valid even without WAL)
   Idempotent: plan_id is dedup key
   Failure: log warning, retry once, proceed anyway (ERR_COMMIT_FAIL)

 K0 degraded:
   Recall may be slow (extended timeout)
   Persist still fire-and-forget
   Neither blocks the pipeline
```

**Ownership boundary**: K0 owns storage, recall ranking, and WAL persistence.
The Planner owns query construction and the decision to persist (always in
COMMIT stage).

**Deep dive**: Section 9.3 (K0 WAL Persist), Section 16.1.5 (BridgeAdapter).

### 27.6 Planner <-> Delta Bus / Event Bus

The Planner is a publisher on both buses but subscribes only on the Event Bus.

```text
 Delta Bus (IDeltaEmitPort -> DeltaBusAdapter):
   Direction: Publish-only (outbound)
   Topic: k1.planner.delta.v1
   Delivery: Fire-and-forget (best-effort)
   Content: Stage transitions, tool results, plan outcomes, plan_end
   Emitter: PipelineController (sole emitter, centralized)
   Failure: Log and drop (no retry, no pipeline impact)

 Event Bus (IEventPort -> EventBusAdapter):
   Direction: Bidirectional (publish + subscribe)
   Published topics:
     k1.planner.plan.ready.v1       -- CommittedPlan
     k1.planner.plan.failed.v1      -- failure payload
     k1.planner.plan.cancelled.v1   -- cancel payload
     k1.planner.micro_replan.ready.v1 -- telemetry-only
     k1.hil.clarification.v1        -- HIL question to Concierge
     k1.hil.approval_request.v1     -- HIL approval to Concierge
   Subscribed topics:
     k1.hil.clarification_response.v1 -- user's clarification answer
     k1.hil.approval_response.v1      -- user's approval/modify/reject
   Delivery: At-least-once for lifecycle events
   Failure: Retry once. If still fails: plan completed but undeliverable
            (Orchestrator timeout reaper cleans up)
```

**Ownership boundary**: The bus infrastructure is owned by Fabric (K1 runtime).
The Planner owns topic names, payload schemas, and emission timing.

**Deep dive**: Section 15.7 (IDeltaEmitPort), Section 15.8 (IEventPort),
Section 26.1-26.4 (bus integration tables).

### 27.7 Planner <-> Concierge (via HIL)

The Planner communicates with users indirectly through the Concierge module.
All HIL communication routes through the Event Bus -- there is no direct
Planner-to-Concierge call.

```text
 Interaction pattern: Event-driven, async, correlated by request_id
 Port (Planner side): IEventPort (publish + subscribe)
 Adapter: EventBusAdapter

 Clarification flow (Stage 1 SKETCH):
   1. SketchService detects ambiguous intent
   2. HILCoordinator generates clarification question via ILLMPort (~300 tokens)
   3. Publish k1.hil.clarification.v1{request_id, question, context, trace_id}
   4. Event Bus -> Concierge -> User prompt
   5. User responds
   6. Concierge publishes k1.hil.clarification_response.v1{request_id, user_response}
   7. HILCoordinator receives (subscription), correlates by request_id
   8. SKETCH resumes with user's answer
   Timeout: 60s per round. If timeout: best-effort interpretation (ERR_HIL_TIMEOUT)
   Max rounds: 2 (PLAN-10)

 Approval flow (Stage 3 VALIDATE):
   1. ValidateService determines plan has high-impact operations
   2. HILCoordinator generates approval summary via ILLMPort (~400 tokens)
   3. Publish k1.hil.approval_request.v1{request_id, summary, options, safety_assessment}
   4. Event Bus -> Concierge -> User prompt
   5. User responds: approve / modify / reject
   6. Concierge publishes k1.hil.approval_response.v1{request_id, response_type, modifications}
   7. HILCoordinator receives, correlates by request_id
   8. VALIDATE acts on response:
        approve -> proceed to COMMIT
        modify  -> re-run EXPAND with modifications, then re-VALIDATE
        reject  -> Plan FSM -> FAILED, emit plan.failed.v1
   Timeout: 120s. If timeout: auto-approve if all steps are safe (ERR_HIL_TIMEOUT)
   Max rounds: shares 2-round budget with clarification (PLAN-10)
```

**Ownership boundary**: Concierge owns user-facing rendering, output channel
selection, and response routing.  The Planner owns question/summary generation,
correlation, timeout policy, and response interpretation.

**Deep dive**: Section 11 (Human-in-the-Loop Integration).

### 27.8 Component Relationship Summary

| Component | Planner Role | Port | Adapter | CB | Section |
| --------- | ------------ | ---- | ------- | -- | ------- |
| Orchestrator | Receives requests, delivers plans | IPlannerMailbox | MailboxAdapter | CB\_PLANNER (external) | 4 |
| Model Hub | Consumes LLM capabilities | ILLMPort | LLMGatewayAdapter | CB\_LLM\_INHERIT (external) | 13 |
| Fabric Retrieval | Reads capabilities + prompts | IFabricRetrievalPort | FabricRetrievalAdapter | None | 12.1 |
| SessionState | Reads hot-tier context | IStateReadPort | SessionStateReadAdapter | None | 6.1 |
| K0 Bridge | Reads memory, writes WAL | IBridgePort | BridgeAdapter | None | 9.3 |
| Delta Bus | Publishes cognitive deltas | IDeltaEmitPort | DeltaBusAdapter | None | 22.4 |
| Event Bus | Publishes events, subscribes HIL | IEventPort | EventBusAdapter | None | 15.8 |
| Concierge | Routes HIL to user (via Event Bus) | IEventPort (shared) | EventBusAdapter (shared) | None | 11 |

---

## 28. Complete Event Catalog

All events emitted or consumed by the Planner, organised by transport.
Payloads match the authoritative definitions in Section 26.

### 28.1 Event Bus -- Published by Planner

At-least-once delivery via IEventPort -> EventBusAdapter -> K1 Event Bus.

| Topic | Emitter | Payload | Primary Consumer | Notes |
| ----- | ------- | ------- | ---------------- | ----- |
| `k1.planner.plan.ready.v1` | CommitService | CommittedPlan (full serialised object) | Orchestrator (DAG execution) | Terminal success -- triggers PendingPlanContext cleanup |
| `k1.planner.plan.failed.v1` | PipelineController | `{request_id, stage, error_code, error_message, partial_state, tokens_used, duration_ms, trace_id}` | Orchestrator, Learning Loop | Terminal failure at any stage |
| `k1.planner.plan.cancelled.v1` | PipelineController | `{request_id, reason, stage, trace_id}` | Orchestrator | Cancel honoured (user abort, timeout, shutdown) |
| `k1.planner.micro_replan.ready.v1` | PipelineController | Partial CommittedPlan (replacement steps only) | Learning Loop | TELEMETRY-ONLY -- not delivery; Orchestrator receives CommittedPlan synchronously |
| `k1.hil.clarification.v1` | HILCoordinator | `{request_id, question, context, trace_id}` | Concierge -> User | Stage 1: ambiguous intent, max 2 rounds (PLAN-10) |
| `k1.hil.approval_request.v1` | HILCoordinator | `{request_id, summary, options, side_effects, safety_assessment}` | Concierge -> User | Stage 3: HIGH-impact plan review |

**Deep dive**: Section 26.2 (Event Bus published topics).

### 28.2 Event Bus -- Subscribed by Planner

At-least-once delivery.  Subscriptions created during INIT (Section 23.1).

| Topic | Source | Subscriber | Handler | Notes |
| ----- | ------ | ---------- | ------- | ----- |
| `k1.hil.clarification_response.v1` | Concierge | HILCoordinator | Correlate by `request_id`, unblock SKETCH | 60 s timeout per round, then best-effort |
| `k1.hil.approval_response.v1` | Concierge | HILCoordinator | Correlate by `request_id`, unblock VALIDATE | 120 s timeout, approve/modify/reject |

**Note on plan.request / plan.cancel**: The planner.mmd IEventPort spec lists
`plan.request` and `plan.cancel` as subscribed topics.  In V1, these requests
arrive through the direct mailbox path (`PlannerAdapter.request_plan()` ->
`IPlannerMailbox.enqueue()` and `PlannerAdapter.cancel_plan()` ->
`IPlannerMailbox.send_cancel()`).  The event bus subscriptions
(`k1.planner.plan.request.v1`, `k1.planner.plan.cancel.v1`) registered during
INIT (Section 23.1) serve as the async alternative path described in kernel.md
Section 9.4.  Both paths funnel into the same mailbox.

**Deep dive**: Section 26.3 (Event Bus subscriptions).

### 28.3 Delta Bus -- Published by Planner

Fire-and-forget via IDeltaEmitPort -> DeltaBusAdapter -> `k1.planner.delta.v1`
topic.  PipelineController is the sole emitter.  Delta loss is acceptable.

| delta\_type | section | When | Payload | Notes |
| ----------- | ------- | ---- | ------- | ----- |
| `"stage_transition"` | `"pipeline"` | Stage start | `{stage, status: "started", timestamp_ms}` | One per stage (SKETCH, EXPAND, VALIDATE, COMMIT) |
| `"stage_transition"` | `"pipeline"` | Stage complete | `{stage, status: "completed", tokens_used, duration_ms}` | Includes per-stage token count |
| `"stage_transition"` | `"pipeline"` | Stage failed | `{stage, status: "failed", error_type, recovery_path}` | error\_type from CB or LLM |
| `"tool_result"` | `"tools"` | Tool call returns | `{tool, result_count, latency_ms}` | Up to 6 per plan (PLAN-05) |
| `"hil_event"` | `"pipeline"` | HIL round starts/ends | `{type, round, plan_id, outcome, latency_ms}` | Clarification or approval |
| `"plan_update"` | `"plan"` | Plan committed | `{plan_id, step_count, total_tokens, status: "committed"}` | Final plan shape |
| `"plan_update"` | `"plan"` | Plan failed | `{request_id, stage, reason, status: "failed"}` | Mirrors plan.failed (shadow) |
| `"plan_update"` | `"plan"` | Plan cancelled | `{request_id, reason, status: "cancelled"}` | Mirrors plan.cancelled (shadow) |
| `"plan_end"` | `"pipeline"` | Plan lifecycle ends | `{plan_id, total_tokens, total_duration_ms, outcome}` | Emitted after plan.ready / plan.failed / plan.cancelled |
| `"micro_replan"` | `"pipeline"` | Micro-replan completes | `{original_plan_id, outcome, replacement_steps, duration_ms}` | Outcome: success / timeout / error |
| `"crash_recovery"` | `"pipeline"` | Crash recovery runs | `{action, request_id, last_stage, staleness_ms}` | Action: resume / discard |

**Consumers**: Learning Loop (drift detection), SessionState subscribers (optional
delta incorporation), debugging/tracing tools.

**Deep dive**: Section 26.1 (Delta Bus emissions), Section 22.4 (Observability
delta details).

### 28.4 Event Summary Matrix

| Transport | Direction | Count | Delivery Guarantee |
| --------- | --------- | ----- | ------------------ |
| Event Bus | Published | 6 topics | At-least-once |
| Event Bus | Subscribed | 2 topics (+ 2 async-path) | At-least-once |
| Delta Bus | Published | 1 topic, 11 delta\_types | Fire-and-forget |
| **Total** | | **9 distinct topics, 11 delta types** | |

**Cross-references**: Section 22 (Observability), Section 25 (External
Touchpoints), Section 26 (Delta Bus and Event Bus Integration).

---

## 29. Bootstrap & Kernel Integration

This section documents how the Planner module integrates into the K1 kernel
bootstrap sequence, how the Orchestrator connects to the Planner at runtime,
and where the Planner sits in the shutdown order.

### 29.1 Phase 5 in Kernel Bootstrap

The kernel bootstrap sequence (kernel.md Section 7) wires modules in dependency
order.  The Planner is Phase 5 -- it depends on the Fabric bus (Phase 3) and
SessionState (Phase 3) being available.

**Current state (V1)**: Phase 5 is a commented-out TODO in kernel.md.  The
Orchestrator is wired with `MockPlannerAdapter()` in Phase 4:

```text
 kernel.md Phase 4 (current):

   orchestrator = await OrchestratorFactory.create_production(
       orch_config,
       mailbox  = MailboxAdapter(max_depth=orch_config.mailbox_capacity),
       fabric   = FabricGatewayAdapter(fabric),
       planner  = MockPlannerAdapter(),            <-- Phase 5 will replace
       state    = StateReadAdapter(state_reader),
       delta    = DeltaEmitAdapter(fabric_bus, fabric_bus),
       bridge   = MockBridgeAdapter(),
       event    = EventSubscriptionAdapter(fabric_bus),
       storage  = WorkflowStorageAdapter(SQLiteWorkflowAdapter(...)),
   )
```

**Phase 5 wiring (TODO)**: When the Planner module is ready, the commented-out
block in kernel.md will be activated:

```text
 Phase 5: Planner cross-wiring

 1. CREATE PLANNER MODULE
    planner_module = PlannerFactory.create_standalone(
        llm_port      = LLMGatewayAdapter(model_hub),
        fabric_port   = FabricRetrievalAdapter(fabric),
        state_port    = SessionStateReadAdapter(state_reader),
        bridge_port   = BridgeAdapter(bridge_client),
        delta_port    = DeltaBusAdapter(fabric_bus),
        event_port    = EventBusAdapter(fabric_bus),
        mailbox_port  = MailboxAdapter(max_depth=5),
    )
    -- PlannerFactory wires all 7 ports, creates PlannerAgent,
    -- runs INIT phase (Section 23.1), returns ready module.

 2. EXTRACT MAILBOX REFERENCE
    planner_mailbox = planner_module.get_mailbox()
    -- Returns the IMailboxPort instance for the Orchestrator to enqueue into.

 3. CREATE CB_PLANNER (Orchestrator-owned circuit breaker)
    from k1.fabric.circuit_breaker.breaker import CircuitBreaker
    cb_planner = CircuitBreaker("CB_PLANNER",
        failure_threshold = orch_config.cb_planner_failure_threshold,   -- default 3
        reset_timeout_s   = orch_config.cb_planner_reset_timeout_ms / 1000,  -- default 60s
    )

 4. CREATE PRODUCTION PlannerAdapter
    planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)

 5. HOT-SWAP MOCK FOR REAL
    orchestrator._planner_port = planner_adapter
    -- Replaces MockPlannerAdapter with production PlannerAdapter.
    -- Orchestrator does not need restart; port is swapped in-place.
```

**Source**: kernel.md lines 231-238 (commented-out Phase 5 block).

**Post-condition**: After Phase 5 completes, every `PlannerAdapter.request_plan()`
call from the Orchestrator reaches the real Planner mailbox, protected by
CB\_PLANNER.

### 29.2 PlannerAdapter (Orchestrator-side)

The `PlannerAdapter` is the Orchestrator's production `IPlannerPort`
implementation.  It wraps the Planner's `IPlannerMailbox` with CB\_PLANNER
circuit breaker logic.

```text
 PlannerAdapter(planner_mailbox: IPlannerMailbox, cb_planner: CircuitBreaker)

 +-----------------+------+---------------+-----------------------+------------------------+
 | Method          | CB?  | On Success    | On Failure            | Returns                |
 +-----------------+------+---------------+-----------------------+------------------------+
 | request_plan()  | Yes  | cb.reset(),   | cb.trip(),            | PlanAck                |
 |                 |      | PlanAck(ACC)  | PlanAck(REJECTED)     |                        |
 +-----------------+------+---------------+-----------------------+------------------------+
 | cancel_plan()   | No   | silent        | log warning           | None                   |
 +-----------------+------+---------------+-----------------------+------------------------+
 | micro_replan()  | Yes  | cb.reset(),   | Timeout: cb.trip(),   | Optional[CommittedPlan]|
 |                 |      | CommittedPlan | return None           |                        |
 +-----------------+------+---------------+-----------------------+------------------------+
```

**Key protocol properties**:

- `request_plan()` is **fire-and-forget**: returns PlanAck immediately.
  CommittedPlan arrives later via `k1.planner.plan.ready.v1` event.
- `micro_replan()` is **synchronous**: blocks up to 10 s, returns
  `Optional[CommittedPlan]` directly.  Bypasses mailbox queue.
- `cancel_plan()` is **best-effort**: always attempted regardless of CB state.
  Bypasses mailbox queue via `send_cancel()`.
- PlanAck is constructed by PlannerAdapter (not by the Planner mailbox).

**CB_PLANNER configuration**: 3 failures -> OPEN, 60 s reset, 1 half-open probe.

**Deep dive**: Section 4.3 (PlannerAdapter full specification),
Section 20.1 (CB\_PLANNER circuit breaker details).

### 29.3 Planner in the Shutdown Order

The kernel shutdown sequence (kernel.md Section 8 and Section 16) tears down
components in consumer-first order.  The Planner module must shut down
**after** the Orchestrator stops sending new requests but **before** the
infrastructure (Fabric, Bus) is torn down.

```text
 Shutdown order (Phase 5 integrated):

 1. Orchestrator: stop accepting new TaskEnvelopes (mailbox rejects)
 2. Orchestrator: drain active DAG (30 s grace, config.shutdown_grace_period_ms)
    -- During drain, Orchestrator may still call micro_replan() for in-flight DAG.
    -- cancel_plan() for any pending plan is sent.

 3. Planner: PlannerAgent.shutdown()  (Section 23.5, 8 steps)
    a. Stop accepting new enqueue() -> ShutdownError
    b. Drain mailbox queue -> emit plan.cancelled.v1 per queued request
    c. Cancel in-flight plan (if any) -> plan.cancelled.v1
    d. Flush pending deltas (best-effort)
    e. Persist partial plan state via IBridgePort (fire-and-forget)
    f. Release plan lock
    g. Unsubscribe 4 event subscriptions
    h. Log: shutdown.complete{plans_drained, in_flight_cancelled, deltas_flushed}
    -- Graceful timeout: 5 s (force-cancel if exceeded)

 4. Orchestrator: complete remaining shutdown steps
    -- Stop scheduler, unsubscribe events, persist trigger states
    -- Final audit write (orphaned_plans count includes Planner-drained plans)
    -- Cancel background tasks (_reaper_task, _loop_task)

 5. Fabric:          drain pending executions
 6. SessionState:    final checkpoint, flush events
 7. Bus:             drain subscribers, close ring buffer
 8. Mailbox Router:  drain all mailboxes
```

**Ordering invariant**: Consumers shut down before infrastructure.
`Orchestrator (partial) -> Planner -> Orchestrator (complete) -> Fabric ->
SessionState -> Bus -> Mailbox Router`.

**Current state**: The Planner shutdown step (step 3) is not yet wired in
kernel.md because Phase 5 is TODO.  When activated, it will be inserted between
Orchestrator DAG drain (step 2) and Orchestrator final teardown (step 4).

### 29.4 MockPlannerAdapter (Pre-Phase-5)

Until Phase 5 is activated, the Orchestrator uses `MockPlannerAdapter` which
provides the `IPlannerPort` interface with stub behaviour:

```text
 MockPlannerAdapter:

   request_plan(PlanRequest) -> PlanAck(ACCEPTED)
     -- Immediately returns accepted, but never produces a CommittedPlan.
     -- Orchestrator's PendingPlanContext will eventually time out (45 s).

   cancel_plan(request_id) -> None
     -- No-op.

   micro_replan(MicroReplanRequest) -> None
     -- Always returns None (no replan available).
```

**Source**: `k1/orchestrator/adapters/mock_planner_adapter.py`

This allows the Orchestrator, DAGExecutor, and all downstream components to be
tested and run without a real Planner module.  Phase 5 replaces this mock with
the production `PlannerAdapter` via hot-swap (Section 29.1, step 5).

### 29.5 Cross-Reference Summary

| Topic | Section |
| ----- | ------- |
| PlannerAdapter full specification | 4.3 |
| Two-phase plan delivery protocol | 4.4 |
| CB\_PLANNER circuit breaker | 20.1 |
| Planner INIT lifecycle | 23.1 |
| Planner SHUTDOWN lifecycle | 23.5 |
| PlannerFactory and wiring | 16.1 |
| Kernel bootstrap (kernel.md) | kernel.md Section 7 |
| Kernel shutdown (kernel.md) | kernel.md Section 8, 16 |

---

## 30. Directory Structure

This section defines the authoritative file layout for the Planner module.  The
structure is derived from three sources:

1. **wiring.contract.yaml** (39 required files) -- binding contract, final arbiter
   of what MUST exist.
2. **planner.mmd** (913 lines) -- architectural components, ports, services, wiring.
3. **planner.md Sections 1-29** -- deep-dive specifications for every file's purpose,
   interface, collaborators, and test plan.

All file paths below are relative to the repository root.

### 30.1 Current State

```text
k1/planner/
  __init__.py                                    # empty -- no implementation yet
  planner.mmd                                    # 913-line authoritative architecture spec
  planner.md                                     # this document

k1/contracts/modules/planner/
  wiring.contract.yaml                           # 593-line wiring contract (39 required files)
  module.contract.yaml                           # 173-line module contract

tests/k1/planner/                                # does not exist yet
```

No implementation code exists.  The two contract files and the architecture
spec (planner.mmd + planner.md) are the only artifacts.

### 30.2 Implementation Structure (39 Required Files)

The structure below matches `wiring.contract.yaml code.required_files` exactly.
Every file listed is REQUIRED for the module to be considered implementable.

```text
k1/planner/
  __init__.py                                    # [F01] Package facade + re-exports
  planner_agent.py                               # [F02] PlannerAgent actor
  pipeline_controller.py                         # [F03] PipelineController orchestrator
  plan_fsm.py                                    # [F04] Plan state machine (10 states)
  types.py                                       # [F05] Planner-internal types
  events.py                                      # [F06] Event topic constants + payloads
  config.py                                      # [F07] PlannerConfig frozen dataclass
  factory.py                                     # [F08] PlannerFactory (3 creation modes)
  metrics.py                                     # [F09] Metric definitions (counters/histograms/gauges)
  tracing.py                                     # [F10] Trace propagation helpers

  ports/                                         # 7 hexagonal port Protocols
    __init__.py                                  # [F11] Re-exports all 7 port Protocols
    mailbox_port.py                              # [F12] IMailboxPort
    llm_port.py                                  # [F13] ILLMPort
    fabric_retrieval_port.py                     # [F14] IFabricRetrievalPort
    state_read_port.py                           # [F15] IStateReadPort
    bridge_port.py                               # [F16] IBridgePort
    delta_emit_port.py                           # [F17] IDeltaEmitPort
    event_port.py                                # [F18] IEventPort

  stages/                                        # 4-stage pipeline services
    __init__.py                                  # [F19] Re-exports stage services
    sketch_service.py                            # [F20] SketchService (Stage 1)
    expand_service.py                            # [F21] ExpandService (Stage 2)
    validate_service.py                          # [F22] ValidateService (Stage 3)
    commit_service.py                            # [F23] CommitService (Stage 4)

  services/                                      # Shared internal services
    __init__.py                                  # [F24] Re-exports ToolCallRouter, HILCoordinator
    tool_call_router.py                          # [F25] ToolCallRouter (4 tools, PLAN-05)
    hil_coordinator.py                           # [F26] HILCoordinator (clarification + approval)

  adapters/                                      # 7 production port implementations
    __init__.py                                  # [F27] Re-exports all 7 production adapters
    mailbox_adapter.py                           # [F28] MailboxAdapter
    llm_gateway_adapter.py                       # [F29] LLMGatewayAdapter
    fabric_retrieval_adapter.py                  # [F30] FabricRetrievalAdapter
    session_state_adapter.py                     # [F31] SessionStateReadAdapter
    bridge_adapter.py                            # [F32] BridgeAdapter
    delta_bus_adapter.py                         # [F33] DeltaBusAdapter
    event_bus_adapter.py                         # [F34] EventBusAdapter

  planner.mmd                                    # Architecture spec (unchanged)
  planner.md                                     # This document (unchanged)
```

**File count**: 34 files in `k1/planner/` (10 root + 8 ports/ + 5 stages/ +
3 services/ + 8 adapters/).

The wiring contract lists 39 paths.  34 are production files above.  The
remaining 5 are the `__init__.py` re-export files in each subdirectory which
are also listed as required:

| Subpackage | `__init__.py` count |
| ---------- | ------------------- |
| `ports/` | 1 (F11) |
| `stages/` | 1 (F19) |
| `services/` | 1 (F24) |
| `adapters/` | 1 (F27) |
| **Total `__init__.py`** | **4 sub + 1 root = 5** |

Total: 10 root files + 8 port files + 5 stage files + 3 service files +
8 adapter files + 5 `__init__.py` = **39 required files**.

### 30.3 Test Adapters (7 In-Memory Implementations)

Test adapters are NOT in `wiring.contract.yaml required_files` -- they are part
of the test infrastructure in `tests/k1/planner/`.  Each test adapter satisfies
the same Protocol as its production counterpart using in-memory / deterministic
behaviour.

```text
tests/k1/planner/
  __init__.py
  conftest.py                                    # Shared fixtures: test adapters, PlannerFactory.create_for_testing()

  adapters/
    __init__.py
    test_mailbox_adapter.py                      # TestMailboxAdapter -- in-memory queue, inspectable
    test_llm_adapter.py                          # TestLLMAdapter -- per-stage canned responses
    test_fabric_retrieval_adapter.py             # TestFabricRetrievalAdapter -- configurable results
    test_state_read_adapter.py                   # TestStateReadAdapter -- preset snapshot
    test_bridge_adapter.py                       # TestBridgeAdapter -- in-memory WAL + recall
    test_delta_adapter.py                        # TestDeltaAdapter -- captures emitted deltas
    test_event_adapter.py                        # TestEventAdapter -- captures published events
```

**Design principle**: Test adapters live in the test tree (not `k1/planner/adapters/`)
so they are never importable from production code.  This prevents accidental
import of test stubs in kernel bootstrap.

### 30.4 Test File Structure (~335 Tests)

Test files mirror the production structure.  Each production file has a
corresponding test file.  Test naming follows the Orchestrator conventions
established in `tests/k1/orchestrator/`.

```text
tests/k1/planner/
  __init__.py
  conftest.py                                    # Shared fixtures: wired PlannerAgent, test adapters

  # --- Core ---
  test_planner_agent.py                          # PlannerAgent lifecycle, mailbox loop, lock semantics
  test_pipeline_controller.py                    # Stage sequencing, budget injection, cancel between stages, error propagation
  test_plan_fsm.py                               # State transitions (10 states), monotonicity, reset
  test_factory.py                                # PlannerFactory 3 modes: standalone, testing, with_ports

  # --- Stages ---
  test_sketch_service.py                         # Prompt slots, LLM call, parse, HIL clarification, retry
  test_expand_service.py                         # Tool mapping, dependency DAG, schema inference, fallback
  test_validate_service.py                       # DAG cycle check, capability existence, LLM arbiter, HIL approval
  test_commit_service.py                         # Plan assembly, WAL persist, event emission, bridge offline

  # --- Services ---
  test_tool_call_router.py                       # Routing, call counting (PLAN-05), degraded paths, reset
  test_hil_coordinator.py                        # Clarification, approval, round budget (PLAN-10), timeout

  # --- Adapters (production) ---
  test_mailbox_adapter.py                        # Queue bounded at 5, MailboxFullError, send_cancel, micro_replan
  test_llm_gateway_adapter.py                    # HubRequest construction, timeout, budget exceeded
  test_fabric_retrieval_adapter.py               # discover_capabilities routing, empty result
  test_session_state_adapter.py                  # read_sections, lock-free multi-reader
  test_bridge_adapter.py                         # recall, persist_plan, fire-and-forget
  test_delta_bus_adapter.py                      # emit, fire-and-forget, agent_id stamp
  test_event_bus_adapter.py                      # publish, subscribe, unsubscribe, topic routing

  # --- Integration ---
  test_full_pipeline_e2e.py                      # End-to-end: PlanRequest -> CommittedPlan (all 4 stages)
  test_micro_replan_e2e.py                       # End-to-end: MicroReplanRequest -> CommittedPlan (3 stages)
  test_cancel_e2e.py                             # Cancel at each inter-stage boundary
  test_hil_e2e.py                                # Clarification + approval round-trip
  test_error_recovery_e2e.py                     # ERR_SKETCH_FAIL, ERR_EXPAND_FAIL, ERR_VALIDATE_FAIL, ERR_COMMIT_FAIL
  test_observability.py                          # Structured logs, metrics, deltas emitted correctly
  test_shutdown.py                               # Graceful shutdown: drain, cancel in-flight, flush deltas

  # --- Test adapters (in-memory) ---
  adapters/
    __init__.py
    test_mailbox_adapter.py
    test_llm_adapter.py
    test_fabric_retrieval_adapter.py
    test_state_read_adapter.py
    test_bridge_adapter.py
    test_delta_adapter.py
    test_event_adapter.py

  helpers.py                                     # Test utilities: plan builders, assertion helpers
```

**Test distribution** (from Section 17.9):

| Component | Test Count | Test File |
| --------- | ---------- | --------- |
| PipelineController | ~80 | test\_pipeline\_controller.py |
| SketchService | ~60 | test\_sketch\_service.py |
| ExpandService | ~50 | test\_expand\_service.py |
| ValidateService | ~45 | test\_validate\_service.py |
| ToolCallRouter | ~35 | test\_tool\_call\_router.py |
| HILCoordinator | ~35 | test\_hil\_coordinator.py |
| CommitService | ~30 | test\_commit\_service.py |
| **Total** | **~335** | |

Additional tests for agent lifecycle, FSM, factory, adapters, integration,
observability, and shutdown add approximately ~100 more tests on top of the
service-level ~335.

### 30.5 File Specifications (F01-F34)

Each file below specifies: what it defines, its dependencies, related sections
in this document, and the invariants it enforces.

#### 30.5.1 Root Files (F01-F10)

**[F01] `__init__.py`** -- Package Facade

```text
 Purpose:
   Re-exports all public symbols for external consumers.
   Provides single import point: from k1.planner import PlannerAgent, CommittedPlan, ...

 Exports (module.contract.yaml):
   PlannerAgent             (from planner_agent)
   PipelineController       (from pipeline_controller)
   PlanStateMachine         (from plan_fsm)

   IMailboxPort             (from ports)
   ILLMPort                 (from ports)
   IFabricRetrievalPort     (from ports)
   IStateReadPort           (from ports)
   IBridgePort              (from ports)
   IDeltaEmitPort           (from ports)
   IEventPort               (from ports)

   CommittedPlan            (re-export from k1.orchestrator.types)
   PlanAck                  (re-export from k1.orchestrator.types)
   PlanStep                 (re-export from k1.orchestrator.types)

 Note:
   Re-exports only -- defines NO classes.  Source of truth for shared types
   remains k1/orchestrator/types.py (Section 32).
```

**[F02] `planner_agent.py`** -- PlannerAgent Actor

```text
 Purpose:
   Single-threaded async coordinator.  Owns the mailbox dequeue loop, plan
   lock (V1 single-plan), and cancel set.  Drives PipelineController.

 Defines:
   class PlannerAgent:
     __init__(ports: dict, config: PlannerConfig)
     async start()                  -> None             # INIT phase (Section 23.1)
     async shutdown()               -> None             # SHUTDOWN phase (Section 23.5)
     async _mailbox_loop()          -> None             # Dequeue + dispatch
     async _on_plan_request(req)    -> None             # Event handler (plan.request)
     async _on_plan_cancel(req)     -> None             # Event handler (plan.cancel)
     health() -> HealthStatus
     ready() -> bool

 Dependencies:
   PipelineController, PlannerConfig, IMailboxPort (for dequeue),
   IEventPort (for subscriptions)

 Sections: 3.1 (identity), 23.1 (INIT), 23.5 (SHUTDOWN), 24 (concurrency)
```

**[F03] `pipeline_controller.py`** -- PipelineController

```text
 Purpose:
   Top-level pipeline orchestrator.  Owns stage sequencing, budget injection,
   cancel checking between stages, delta emission, and micro-replan routing.

 Defines:
   class PipelineController:
     __init__(sketch, expand, validate, commit, delta_port, event_port)
     async execute(PlanRequest, StageContext) -> CommittedPlan
     async micro_replan(MicroReplanRequest, StageContext) -> CommittedPlan
     cancel_check(request_id) -> bool

 Constructor params:
   sketch:     SketchService
   expand:     ExpandService
   validate:   ValidateService
   commit:     CommitService
   delta_port: IDeltaEmitPort
   event_port: IEventPort

 Ports (direct): IDeltaEmitPort, IEventPort
 Invariants: PLAN-03, PLAN-04, PLAN-11, PLAN-12
 Sections: 5 (pipeline flow), 10 (micro-replan), 13.3 (budget), 17.2 (~80 tests)
```

**[F04] `plan_fsm.py`** -- Plan State Machine

```text
 Purpose:
   Enum-based FSM tracking plan lifecycle.  10 states, monotonic transitions.

 Defines:
   class PlanState(Enum):
     IDLE, SKETCHING, EXPANDING, VALIDATING, COMMITTING,
     MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE,
     COMPLETED, FAILED, CANCELLED

   class PlanStateMachine:
     __init__()
     transition(from_state, to_state, trigger) -> None
     current -> PlanState
     is_terminal -> bool
     reset() -> None                                  # COMPLETED/FAILED/CANCELLED -> IDLE

 State transitions:
   Section 18.1 (state catalog), 18.2-18.4 (diagrams), 18.5 (rules)

 Sections: 18 (full FSM specification)
```

**[F05] `types.py`** -- Planner-Internal Types

```text
 Purpose:
   Types that do NOT cross the Planner boundary.  These flow between stages
   inside the pipeline but are never exposed to Orchestrator or other modules.

 Defines:
   @dataclass(frozen=True)
   class RoughStep:                               # Section 6.5 -- SKETCH output unit
     intent: str
     suggested_capability: Optional[str]
     depends_on: List[str]
     confidence: float

   @dataclass(frozen=True)
   class SketchResult:                            # Section 6.5 -- SKETCH full output
     rough_steps: List[RoughStep]
     capability_candidates: List[ScoredCapability]
     rationale: str

   @dataclass(frozen=True)
   class ExpandedPlan:                            # Section 7.4 -- EXPAND full output
     steps: List[PlanStep]
     dependencies: Dict[str, List[str]]
     tool_mappings: Dict[str, str]
     rationale: str

   @dataclass(frozen=True)
   class ValidationVerdict:                       # Section 8.3.3 -- VALIDATE output
     status: str                                  # "approved" | "revise" | "reject"
     issues: List[ValidationIssue]
     confidence: float
     rationale: str

   @dataclass(frozen=True)
   class ValidationIssue:
     check_name: str
     severity: str                                # "error" | "warning"
     step_id: Optional[str]
     detail: str

   @dataclass(frozen=True)
   class StageContext:                            # Passed to every stage
     request_id: str
     trace_id: str
     timeout_remaining_ms: int
     token_budget_remaining: int
     cancel_check: Callable[[], bool]

   @dataclass(frozen=True)
   class DeltaPayload:                            # Section 22.4.1 -- delta envelope
     agent_id: str                                # Always "planner"
     delta_type: str
     section: str                                 # "pipeline" | "plan" | "tools"
     data: Dict[str, Any]
     trace_id: str

 Note:
   Shared types (PlanRequest, PlanAck, CommittedPlan, PlanStep, MicroReplanRequest)
   are NOT defined here -- they live in k1/orchestrator/types.py (Section 32).
   Planner imports them but MUST NOT redefine them.

 External type imports:
   ScoredCapability from k1/fabric/types.py
   PlanStep from k1/orchestrator/types.py (used inside ExpandedPlan)

 Sections: 6.5 (SketchResult), 7.4 (ExpandedPlan), 8.3.3 (ValidationVerdict),
   22.4.1 (DeltaPayload)
```

**[F06] `events.py`** -- Event Topic Constants and Payload Schemas

```text
 Purpose:
   Central registry of all event topic strings and event payload dataclasses.
   Prevents topic string duplication across services.

 Defines:
   # Topic constants
   TOPIC_PLAN_READY         = "k1.planner.plan.ready.v1"
   TOPIC_PLAN_FAILED        = "k1.planner.plan.failed.v1"
   TOPIC_PLAN_CANCELLED     = "k1.planner.plan.cancelled.v1"
   TOPIC_MICRO_REPLAN_READY = "k1.planner.micro_replan.ready.v1"
   TOPIC_DELTA              = "k1.planner.delta.v1"
   TOPIC_HIL_CLARIFICATION  = "k1.hil.clarification.v1"
   TOPIC_HIL_APPROVAL_REQ   = "k1.hil.approval_request.v1"
   TOPIC_PLAN_REQUEST       = "k1.planner.plan.request.v1"
   TOPIC_PLAN_CANCEL        = "k1.planner.plan.cancel.v1"
   TOPIC_HIL_CLARIFICATION_RESP = "k1.hil.clarification_response.v1"
   TOPIC_HIL_APPROVAL_RESP  = "k1.hil.approval_response.v1"

   # Event payload dataclasses (frozen)
   @dataclass(frozen=True)
   class PlanFailedPayload:
     request_id: str
     stage: str
     error_code: str
     error_message: str
     partial_state: Optional[Dict]
     tokens_used: int
     duration_ms: int
     trace_id: str

   @dataclass(frozen=True)
   class PlanCancelledPayload:
     request_id: str
     reason: str
     stage: str
     trace_id: str

   @dataclass(frozen=True)
   class HILClarificationPayload:
     request_id: str
     question: str
     context: Dict[str, Any]
     trace_id: str

   @dataclass(frozen=True)
   class HILApprovalRequestPayload:
     request_id: str
     summary: str
     options: List[str]
     side_effects: List[str]
     safety_assessment: str

 Note:
   CommittedPlan is the payload for TOPIC_PLAN_READY -- no wrapper needed.

 Sections: 26 (Delta Bus & Event Bus), 28 (Complete Event Catalog)
```

**[F07] `config.py`** -- PlannerConfig

```text
 Purpose:
   Frozen dataclass holding all tunable Planner parameters.  Loaded from
   K1 configuration at boot time.  Immutable after construction.

 Defines:
   @dataclass(frozen=True)
   class PlannerConfig:
     # Mailbox
     mailbox_max_depth: int = 5

     # Pipeline timeouts
     pipeline_timeout_ms: int = 45000              # PLAN-04
     sketch_timeout_ms: int = 8000
     expand_timeout_ms: int = 5000
     validate_timeout_ms: int = 3000
     commit_timeout_ms: int = 1000

     # LLM token budgets (PLAN-11)
     sketch_max_tokens: int = 2000
     expand_max_tokens: int = 1000
     validate_max_tokens: int = 500
     total_token_budget: int = 3500

     # LLM temperatures
     sketch_temperature: float = 0.7
     expand_temperature: float = 0.3
     validate_temperature: float = 0.2

     # Tool budgets (PLAN-05)
     max_tool_calls_per_plan: int = 6

     # HIL (PLAN-10)
     max_hil_rounds: int = 2
     hil_clarification_timeout_ms: int = 60000
     hil_approval_timeout_ms: int = 120000

     # Micro-replan
     micro_replan_timeout_ms: int = 10000
     micro_replan_max_tokens: int = 2000

     # Shutdown
     shutdown_grace_period_ms: int = 5000

     @classmethod
     def from_dict(cls, overrides: Dict[str, Any]) -> "PlannerConfig": ...

 Sections: 21 (performance targets), 13.3 (budget injection), 24.2 (cancel),
   20.1 (CB_PLANNER references these values from OrchestratorConfig side)
```

**[F08] `factory.py`** -- PlannerFactory

```text
 Purpose:
   Creates fully wired PlannerAgent instances.  Three creation modes support
   production bootstrap, unit testing, and custom-port wiring.

 Defines:
   class PlannerFactory:
     @staticmethod
     async def create_standalone(
       llm_port, fabric_port, state_port, bridge_port,
       delta_port, event_port, mailbox_port,
       config: PlannerConfig = PlannerConfig(),
     ) -> PlannerAgent:
       """Full production wiring.  Called by kernel Phase 5 (Section 29.1)."""

     @staticmethod
     async def create_for_testing(
       config: PlannerConfig = PlannerConfig(),
       **overrides,
     ) -> PlannerAgent:
       """Injects test adapters for all 7 ports.  For integration tests."""

     @staticmethod
     async def create_with_ports(
       ports: Dict[str, Any],
       config: PlannerConfig = PlannerConfig(),
     ) -> PlannerAgent:
       """Selective port injection.  For unit tests that override specific ports."""

 Wiring steps (all modes):
   1. Construct ToolCallRouter(fabric_port, state_port, bridge_port)
   2. Construct HILCoordinator(llm_port, event_port)
   3. Construct SketchService(llm_port, tool_router, hil_coord)
   4. Construct ExpandService(llm_port, tool_router)
   5. Construct ValidateService(llm_port, fabric_port, hil_coord)
   6. Construct CommitService(bridge_port, delta_port, event_port)
   7. Construct PipelineController(sketch, expand, validate, commit, delta_port, event_port)
   8. Construct PlannerAgent(pipeline_ctrl, mailbox_port, event_port, config)
   9. Call planner_agent.start() -> INIT phase (Section 23.1)
   10. Return planner_agent

 Sections: 16.1 (adapter specs), 23.1 (INIT), 29.1 (kernel Phase 5)
```

**[F09] `metrics.py`** -- Metric Definitions

```text
 Purpose:
   Defines all Planner metric objects (counters, histograms, gauges) with
   names, labels, and bucket definitions.  Services call these objects;
   the telemetry subsystem handles export.

 Defines:
   # Counters (9) -- Section 22.3.1
   plan_total           Counter("planner.plan.total", labels=["outcome"])
   plan_degraded        Counter("planner.plan.degraded", labels=["stage"])
   stage_total          Counter("planner.stage.total", labels=["stage", "outcome"])
   llm_calls            Counter("planner.llm.calls", labels=["stage", "outcome"])
   tool_calls           Counter("planner.tool.calls", labels=["tool", "outcome"])
   hil_rounds           Counter("planner.hil.rounds", labels=["type", "outcome"])
   micro_replan_total   Counter("planner.micro_replan.total", labels=["outcome"])
   mailbox_rejected     Counter("planner.mailbox.rejected")
   recovery_activated   Counter("planner.recovery.activated", labels=["path"])

   # Histograms (6) -- Section 22.3.2
   plan_duration_ms     Histogram("planner.plan.duration_ms", buckets=[...])
   stage_duration_ms    Histogram("planner.stage.duration_ms", labels=["stage"], buckets=[...])
   llm_latency_ms       Histogram("planner.llm.latency_ms", labels=["stage"], buckets=[...])
   llm_tokens           Histogram("planner.llm.tokens", labels=["stage"], buckets=[...])
   tool_latency_ms      Histogram("planner.tool.latency_ms", buckets=[...])
   micro_replan_ms      Histogram("planner.micro_replan.duration_ms", buckets=[...])

   # Gauges (4) -- Section 22.3.3
   mailbox_depth        Gauge("planner.mailbox.depth")
   plan_in_flight       Gauge("planner.plan.in_flight")
   tokens_remaining     Gauge("planner.tokens.budget_remaining")
   tool_budget_remaining Gauge("planner.tool.budget_remaining")

 Sections: 22.3 (full metric catalog), 22.3.4 (SLI alignment)
```

**[F10] `tracing.py`** -- Trace Propagation Helpers

```text
 Purpose:
   Utilities for cognitive_trace_id propagation across all port calls.
   Ensures FAB-09 compliance: every outbound call carries trace_id.

 Defines:
   def stamp_trace_id(hub_request: HubRequest, trace_id: str) -> HubRequest: ...
   def create_stage_context(plan_request, config, cancel_check) -> StageContext: ...
   def log_event(event_name: str, trace_id: str, **fields) -> None: ...

 Sections: 22.1 (trace propagation), 22.1.4 (trace invariant)
```

#### 30.5.2 Port Files (F11-F18)

All ports are `typing.Protocol` classes with `@runtime_checkable`.  Full
specifications are in Section 15.

**[F11] `ports/__init__.py`** -- Port Re-exports

```text
 Re-exports:
   IMailboxPort, ILLMPort, IFabricRetrievalPort, IStateReadPort,
   IBridgePort, IDeltaEmitPort, IEventPort
```

**[F12] `ports/mailbox_port.py`** -- IMailboxPort

```text
 Defines:
   class IMailboxPort(Protocol):
     async def enqueue(self, request: PlanRequest) -> None: ...
     async def send_cancel(self, request_id: str) -> None: ...
     async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan: ...

 Note: Consumer-driven contract defined on Orchestrator side (IPlannerMailbox).
       Planner's IMailboxPort is structurally identical.
 Sections: 4.2 (protocol), 15.2 (port spec)
```

**[F13] `ports/llm_port.py`** -- ILLMPort

```text
 Defines:
   class ILLMPort(Protocol):
     async def execute(self, request: HubRequest) -> HubResponse: ...

 Sections: 15.3 (port spec), 13.1 (LLM call matrix)
```

**[F14] `ports/fabric_retrieval_port.py`** -- IFabricRetrievalPort

```text
 Defines:
   class IFabricRetrievalPort(Protocol):
     async def discover_capabilities(self, query: str, top_k: int = 5,
                                      trace_id: str = "") -> List[RetrievalResult]: ...
     async def find_relevant_prompts(self, query: str, top_k: int = 3,
                                      trace_id: str = "") -> List[RetrievalResult]: ...

 Sections: 15.4 (port spec), 11.1-11.2 (tool deep dives)
```

**[F15] `ports/state_read_port.py`** -- IStateReadPort

```text
 Defines:
   class IStateReadPort(Protocol):
     async def read_sections(self, sections: List[str],
                              trace_id: str = "") -> StateSnapshot: ...

 Invariant: No write methods.  PLAN-01 enforced at interface level.
 Sections: 15.5 (port spec), 14 (SessionState access)
```

**[F16] `ports/bridge_port.py`** -- IBridgePort

```text
 Defines:
   class IBridgePort(Protocol):
     async def recall(self, query: str, trace_id: str = "") -> RecallResponse: ...
     async def persist_plan(self, plan: CommittedPlan) -> None: ...

 Sections: 15.6 (port spec), 11.4 (recall tool), 9 (COMMIT persist)
```

**[F17] `ports/delta_emit_port.py`** -- IDeltaEmitPort

```text
 Defines:
   class IDeltaEmitPort(Protocol):
     def emit(self, delta: DeltaPayload) -> None: ...

 Note: Synchronous fire-and-forget.  Never raises.  Never blocks.
 Sections: 15.7 (port spec), 22.4 (delta emissions)
```

**[F18] `ports/event_port.py`** -- IEventPort

```text
 Defines:
   class IEventPort(Protocol):
     async def publish(self, topic: str, payload: Any) -> None: ...
     async def subscribe(self, topic: str, handler: Callable) -> Subscription: ...
     async def unsubscribe(self, handle: Subscription) -> None: ...

 Sections: 15.8 (port spec), 26 (Event Bus integration)
```

#### 30.5.3 Stage Files (F19-F23)

Full specifications in Section 17.

**[F19] `stages/__init__.py`** -- Stage Re-exports

```text
 Re-exports: SketchService, ExpandService, ValidateService, CommitService
```

**[F20] `stages/sketch_service.py`** -- SketchService

```text
 Constructor:
   SketchService(llm_port: ILLMPort, tool_router: ToolCallRouter,
                 hil_coord: HILCoordinator)

 Ports (direct): ILLMPort
 Ports (via ToolCallRouter): IFabricRetrievalPort, IStateReadPort, IBridgePort

 Defines:
   class SketchService:
     async def execute(self, request: PlanRequest, ctx: StageContext) -> SketchResult: ...

 Invariant: PLAN-02 (read-only discovery, slot-based prompt)
 Sections: 6 (full deep dive), 17.3 (~60 tests)
```

**[F21] `stages/expand_service.py`** -- ExpandService

```text
 Constructor:
   ExpandService(llm_port: ILLMPort, tool_router: ToolCallRouter)

 Ports (direct): ILLMPort
 Ports (via ToolCallRouter): IFabricRetrievalPort, IBridgePort

 Defines:
   class ExpandService:
     async def execute(self, sketch: SketchResult, request: PlanRequest, ctx: StageContext)
                -> ExpandedPlan: ...

 Invariant: PLAN-02 (read-only discovery, slot-based prompt)
 Sections: 7 (full deep dive), 17.4 (~50 tests)
```

**[F22] `stages/validate_service.py`** -- ValidateService

```text
 Constructor:
   ValidateService(llm_port: ILLMPort, fabric_retrieval: IFabricRetrievalPort,
                   hil_coord: HILCoordinator)

 Ports (direct): ILLMPort, IFabricRetrievalPort

 Defines:
   class ValidateService:
     async def execute(self, expanded: ExpandedPlan, request: PlanRequest, ctx: StageContext)
                -> ValidationVerdict: ...

 Performs: DAG cycle detection, capability existence check, LLM arbiter, HIL approval
 Invariants: PLAN-02, PLAN-06, PLAN-07, PLAN-08, PLAN-09
 Sections: 8 (full deep dive), 17.5 (~45 tests)
```

**[F23] `stages/commit_service.py`** -- CommitService

```text
 Constructor:
   CommitService(bridge_port: IBridgePort, delta_port: IDeltaEmitPort,
                 event_port: IEventPort)

 Ports (direct): IBridgePort, IDeltaEmitPort, IEventPort
 NO ILLMPort -- PLAN-03 enforced at constructor level.

 Defines:
   class CommitService:
     async def execute(self, expanded: ExpandedPlan, verdict: ValidationVerdict,
                       request: PlanRequest, ctx: StageContext) -> CommittedPlan: ...

 Invariant: PLAN-03 (deterministic commit, zero LLM calls)
 Sections: 9 (full deep dive), 17.6 (~30 tests)
```

#### 30.5.4 Service Files (F24-F26)

**[F24] `services/__init__.py`** -- Service Re-exports

```text
 Re-exports: ToolCallRouter, HILCoordinator
```

**[F25] `services/tool_call_router.py`** -- ToolCallRouter

```text
 Constructor:
   ToolCallRouter(fabric_retrieval: IFabricRetrievalPort,
                  state_read: IStateReadPort,
                  bridge_port: IBridgePort)

 Ports (direct): IFabricRetrievalPort, IStateReadPort, IBridgePort

 Defines:
   class ToolCallRouter:
     async def discover(self, intent, domain, safety_band, ctx) -> List[RetrievalResult]: ...
     async def find_prompts(self, query, ctx) -> List[RetrievalResult]: ...
     async def read_context(self, sections, ctx) -> StateSnapshot: ...
     async def recall_memory(self, query, ctx) -> RecallResponse: ...
     def reset_counter() -> None: ...

 Invariant: PLAN-05 (max 6 tool calls per plan)
 Sections: 11 (full deep dive), 17.7 (~35 tests)
```

**[F26] `services/hil_coordinator.py`** -- HILCoordinator

```text
 Constructor:
   HILCoordinator(llm_port: ILLMPort, event_port: IEventPort)

 Ports (direct): ILLMPort, IEventPort

 Defines:
   class HILCoordinator:
     async def request_clarification(self, ambiguity, context, ctx) -> Optional[str]: ...
     async def request_approval(self, plan, risk_assessment, ctx) -> str: ...
     async def on_clarification_response(self, event) -> None: ...
     async def on_approval_response(self, event) -> None: ...

 Invariant: PLAN-10 (max 2 HIL rounds per plan)
 Sections: 12 (full deep dive), 17.8 (~35 tests)
```

#### 30.5.5 Adapter Files (F27-F34)

Full specifications in Section 16.

**[F27] `adapters/__init__.py`** -- Adapter Re-exports

```text
 Re-exports:
   MailboxAdapter, LLMGatewayAdapter, FabricRetrievalAdapter,
   SessionStateReadAdapter, BridgeAdapter, DeltaBusAdapter, EventBusAdapter
```

**[F28] `adapters/mailbox_adapter.py`** -- MailboxAdapter

```text
 Implements: IMailboxPort
 Constructor: MailboxAdapter(max_depth: int = 5)
 Internal state: asyncio.Queue, cancel_set, plan_lock
 Raises: MailboxFullError on depth > 5, ShutdownError after shutdown
 Sections: 16.1.1
```

**[F29] `adapters/llm_gateway_adapter.py`** -- LLMGatewayAdapter

```text
 Implements: ILLMPort
 Constructor: LLMGatewayAdapter(llm_request_bus, consumer_id="planner")
 Routes: HubRequest -> LLM_REQUEST_BUS -> Model Hub
 Raises: LLMTimeoutError, BudgetExceededError, AdapterException(DEGRADED)
 Note: V1 uses TestLLMAdapter.  This is the V2 production path.
 Sections: 16.1.2
```

**[F30] `adapters/fabric_retrieval_adapter.py`** -- FabricRetrievalAdapter

```text
 Implements: IFabricRetrievalPort
 Constructor: FabricRetrievalAdapter(fabric_retrieval)
 Wraps: Fabric Retrieval API (Role 1).  Read-only, <50ms.
 Sections: 16.1.3
```

**[F31] `adapters/session_state_adapter.py`** -- SessionStateReadAdapter

```text
 Implements: IStateReadPort
 Constructor: SessionStateReadAdapter(state_reader)
 Wraps: ISessionStateReader (Fabric 5.1.1).  Lock-free multi-reader, <10ms.
 No write methods.  PLAN-01.
 Sections: 16.1.4
```

**[F32] `adapters/bridge_adapter.py`** -- BridgeAdapter

```text
 Implements: IBridgePort
 Constructor: BridgeAdapter(bridge_client)
 Wraps: K0 Bridge client.  recall() <100ms.  persist_plan() fire-and-forget.
 Sections: 16.1.5
```

**[F33] `adapters/delta_bus_adapter.py`** -- DeltaBusAdapter

```text
 Implements: IDeltaEmitPort
 Constructor: DeltaBusAdapter(delta_bus, agent_id="planner")
 Pre-stamps: agent_id and topic (k1.planner.delta.v1).
 Fire-and-forget.  Logs on failure, never raises.
 Sections: 16.1.6
```

**[F34] `adapters/event_bus_adapter.py`** -- EventBusAdapter

```text
 Implements: IEventPort
 Constructor: EventBusAdapter(event_bus)
 Wraps: K1 Event Bus.  Publish, subscribe, unsubscribe.
 Sections: 16.1.7
```

### 30.6 Dependency Flow (No Circular Imports)

Import direction is strictly top-down.  No file imports from a layer above it.

```text
 Layer 0: types.py, events.py, config.py, plan_fsm.py              (no internal deps)
 Layer 1: ports/*                                                   (imports types)
 Layer 2: adapters/*                                                (imports ports, types)
 Layer 3: services/*                                                (imports ports, types)
 Layer 4: stages/*                                                  (imports ports, types, services)
 Layer 5: pipeline_controller.py                                    (imports stages, ports, types)
 Layer 6: planner_agent.py                                          (imports pipeline_controller, ports, config)
 Layer 7: factory.py                                                (imports everything)
 Layer 8: __init__.py                                               (re-exports only)
```

**Circular import guard**: No file in Layer N imports from Layer N+1 or higher.
`factory.py` is the only file permitted to import across all layers because
it constructs the entire object graph.

### 30.7 Port-to-Service Assignment Matrix

Each service receives ONLY the ports it needs (Section 15.10, principle of least
privilege).

```text
                    Mailbox  LLM  FabricRet  StateRead  Bridge  DeltaEmit  Event
                    -------  ---  ---------  ---------  ------  ---------  -----
 PlannerAgent         [X]                                                   [X]
 PipelineController                                             [X]        [X]
 SketchService                [X]  via TCR    via TCR   via TCR
 ExpandService                [X]  via TCR              via TCR
 ValidateService              [X]    [X]
 CommitService                                          [X]     [X]        [X]
 ToolCallRouter                      [X]       [X]      [X]
 HILCoordinator               [X]                                          [X]

 Legend:  [X] = direct port injection
          via TCR = accessed through ToolCallRouter (not injected directly)
```

### 30.8 Contract File Locations

```text
k1/contracts/modules/planner/
  wiring.contract.yaml                           # 593 lines -- 39 required files, port specs, events
  module.contract.yaml                           # 173 lines -- exports, entrypoints, invariants

k1/contracts/schemas/orchestrator/
  plan_request.v1.json                           # PlanRequest JSON Schema
  micro_replan_request.v1.json                   # MicroReplanRequest JSON Schema

k1/contracts/schemas/orchestrator/events/consumed/
  plan_ready.v1.json                             # CommittedPlan event schema
  plan_failed.v1.json                            # PlanFailed event schema
  plan_cancelled.v1.json                         # PlanCancelled event schema
```

### 30.9 Implementation Priorities

Recommended implementation order based on dependency layering (Section 30.6)
and test-first development:

| Phase | Files | Rationale |
| ----- | ----- | --------- |
| P1 - Foundation | types.py, events.py, config.py, plan\_fsm.py | Zero dependencies.  Can be tested immediately. |
| P2 - Ports | all 7 port files + ports/\_\_init\_\_.py | Depend only on types.  Protocol-only (no logic). |
| P3 - Test Adapters | all 7 test adapter files + conftest.py | Implement port contracts in-memory.  Test harness. |
| P4 - Services | tool\_call\_router.py, hil\_coordinator.py | Leaf services.  Testable with test adapters. |
| P5 - Stages | sketch\_service.py, expand\_service.py, validate\_service.py, commit\_service.py | Depend on services + ports.  Stage-level tests. |
| P6 - Pipeline | pipeline\_controller.py | Depends on all stages.  Integration tests. |
| P7 - Agent | planner\_agent.py, factory.py | Top-level wiring.  End-to-end tests. |
| P8 - Production Adapters | all 7 production adapter files | Require running K1 infrastructure.  Last to implement. |
| P9 - Metrics/Tracing | metrics.py, tracing.py | Cross-cutting.  Can be stubbed until P8. |

### 30.10 Cross-Reference Summary

| Topic | Section |
| ----- | ------- |
| Wiring contract (39 files) | wiring.contract.yaml |
| Module contract (exports, invariants) | module.contract.yaml |
| Port specifications (7 ports) | 15 |
| Adapter specifications (14 total) | 16 |
| Service specifications (7 services) | 17 |
| Internal types (SketchResult, ExpandedPlan, ValidationVerdict) | 6.5, 7.4, 8.3.3 |
| Event catalog (topics + payloads) | 26, 28 |
| Configuration parameters | 21 (targets), 13.3 (budgets) |
| Metric catalog | 22.3 |
| Trace propagation | 22.1 |
| Dependency layering (no circular imports) | 30.6 |
| Implementation order | 30.9 |
| Test structure (~335+ tests) | 30.4 |
| Kernel Phase 5 wiring | 29.1 |

---

## 31. Open Questions for Design Sessions

### 31.1 Resolved Questions (Q1-Q4)

These questions were originally open but have been fully answered by the deep-dive
sections written during architecture elaboration.  Retained for traceability.

| # | Question | Status | Resolution | Authoritative Sections |
| --- | -------- | ------ | ---------- | ---------------------- |
| 1 | **Prompt template management**: Where do SKETCH/EXPAND/VALIDATE prompt templates live? | RESOLVED | The Planner's own stage prompts are **slot-based compositions assembled in code** by each service (SketchService, ExpandService, ValidateService).  They are NOT stored externally or retrieved from Fabric.  Each service owns a `SYSTEM SEGMENT` (ROLE_DEFINITION + OUTPUT_SCHEMA) and a `USER SEGMENT` (data slots filled from tool call results, PlanRequest fields, and pipeline context).  The `find_relevant_prompts()` Fabric call retrieves **agent-step prompt templates** (for `PlanStep.prompt_template` field assignment in EXPAND), not the Planner's own prompts. | 6.3.1 (SKETCH prompt), 7.3.1 (EXPAND prompt), 8.3.1 (VALIDATE prompt), 7.2.2 (find_relevant_prompts for agent steps) |
| 2 | **SketchResult schema**: What exact fields does the LLM return in Stage 1? | RESOLVED | Fully defined.  LLM output JSON Schema requires `rough_steps` (array, minItems:1, each item has required `intent: str` + optional `suggested_capability: str` and `depends_on: int[]`) and `rationale: str` (non-empty) + optional `needs_clarification: bool` and `clarification_question: str`.  Parsed into `SketchResult{rough_steps: List[RoughStep], capability_candidates: List[ScoredCapability], rationale: str}`.  4 validation rules enforced before construction. | 6.3.1 (JSON Schema output contract), 6.5 (SketchResult type + validation rules) |
| 3 | **ExpandedPlan schema**: What exact intermediate format before COMMIT? | RESOLVED | Fully defined.  `ExpandedPlan{steps: List[PlanStep], dependencies: Dict[str, List[str]]}`.  Each PlanStep carries all 14 frozen fields from `k1/orchestrator/types.py`.  LLM output JSON Schema requires `steps` (array, minItems:1, each with required `id`, `capability`, `params`) and `dependencies` (object).  7 of 14 fields are LLM-generated; 7 are deterministically enriched by ExpandService from `CapabilityContract` metadata post-LLM. | 7.3.1 (JSON Schema output contract), 7.4 (ExpandedPlan type), 7.4.2 (field population source matrix) |
| 4 | **Discovery overlap heuristic**: How does micro-replan detect discoveries affecting remaining steps? | RESOLVED | Fully defined.  3-way match: `discovery.field == param_name` (exact, case-insensitive) OR `discovery.field IN param_name` (substring) OR `param_name IN discovery.field` (substring).  Complexity O(D *S* P), <1ms for typical plans.  Per ADR-1.1.11 Q8.  Concrete example documented: "restaurant_closed" overlaps "restaurant_name". | 10.2.2 (Overlap Heuristic full specification + example + performance) |

### 31.2 Resolved Questions (Q5-Q10)

| # | Question | Status | Resolution | Authoritative Sections |
| --- | -------- | ------ | ---------- | ---------------------- |
| 5 | **Micro-replan timeout budget**: Does 10s include LLM latency or just Planner overhead? | RESOLVED | 10s total **including all LLM latency**.  This is the `asyncio.wait_for(10.0)` timeout on the caller side (PlannerAdapter / MicroReplanCheckpoint).  Per-stage breakdown: Micro-SKETCH timeout_ms=5000, Micro-EXPAND timeout_ms=3000, Micro-VALIDATE timeout_ms=2000, COMMIT <100ms.  Theoretical max ~10.1s, practical p50 ~8s, p99 ~15s.  When p99 exceeds 10s, the caller times out and the Orchestrator continues with the original plan (graceful fallback by design). | 10.3.6 (timing budget breakdown), 10.3.1 (pipeline comparison table), 10.5.3 (timeout + graceful fallback), 24.3.2 (micro-replan under load) |
| 6 | **Plan WAL format**: What serialization format for K0 WAL persistence? | RESOLVED | The WAL serialization format is **opaque to the Planner**.  CommitService passes `CommittedPlan.to_dict()` (Python dict) to `IBridgePort.persist_plan()`.  The K0 Bridge owns the actual WAL write mechanics -- the Planner never touches raw bytes.  Persistence is fire-and-forget (plan validity does NOT depend on WAL success) with idempotent upsert via `plan_id` dedup key.  JSON vs FlatBuffer is a K0 decision, not a Planner design question. | 9.3 (full WAL persistence protocol), 9.3.1 (fire-and-forget properties), 9.3.2 (why fire-and-forget), 9.6.2 (WAL failure recovery) |
| 7 | **Concurrent micro-replan**: Can `micro_replan()` be called while a regular plan is in progress? | RESOLVED | **No in V1**.  PlannerAgent uses a single `asyncio.Lock` (`_plan_lock`).  `micro_replan()` bypasses the mailbox queue but still `await`s `_plan_lock.acquire()`.  If a plan is in flight, micro-replan blocks on the lock.  Since the 10s caller-side timeout is shorter than most full plans (12s p50), micro-replan will almost always time out during an active plan -- this is by design.  Orchestrator falls back to the original plan.  V2 may support preemption of SKETCH stage (Section 24.4 notes direction only, not yet designed). | 24.3 (micro-replan concurrency, full analysis), 24.3.1 (V1 behavior + lock acquisition), 24.3.2 (micro-replan under load timeline), 24.1.1 (plan lock semantics) |
| 8 | **LLM response parsing**: How to handle malformed LLM output in SKETCH/EXPAND? | RESOLVED | Three-tier strategy differentiated by stage: **SKETCH** (Section 6.6.2 path 4): re-parse once (strip markdown fences), if still malformed treat as LLM error -> retry with simplified prompt (reduced capabilities, no K0 memory), if retry also malformed -> PLAN FAILED.  **EXPAND** (Section 7.6.2 path 4): re-parse once, if still malformed -> retry LLM with same prompt, if retry also malformed -> FALLBACK to SKETCH output as degraded PlanSteps (pipeline continues).  **VALIDATE** (Section 8.3.2): uses `capability: STRUCTURED` with `strict: true`, Model Hub enforces `response_schema` at decode time -- parse failures eliminated by design.  Key difference: SKETCH failure is terminal; EXPAND failure degrades gracefully. | 6.6.2 (SKETCH recovery decision tree, paths 2-4), 7.6.2 (EXPAND recovery decision tree, paths 2-4), 8.3.2 (STRUCTURED capability eliminates parse failures), 13.2.2 (ChatPayload vs StructuredOutputPayload) |
| 9 | **Stage timeout independence**: Does each stage get its own 45s budget or shared? | RESOLVED | **Per-stage budgets are independent**.  Each service's LLM call carries its own `timeout_ms` in `RequestConstraints` (SKETCH=8000, EXPAND=5000, VALIDATE=3000).  `LLMGatewayAdapter` enforces each timeout independently.  The 45s figure is the **CB_PLANNER timeout** owned by the Orchestrator's PlannerAdapter -- it covers the entire plan lifecycle (all stages + HIL wait + overhead) as an outer boundary.  PipelineController does NOT enforce a shared timer that all stages decrement from.  Stage timeouts sum to 16s (normal path) or 22s (with HIL), both well within 45s.  Worst-case with 2 revise loops: ~19s computational + up to 240s HIL wait. | 13.3.1 (per-stage budget table + injection protocol), 13.3.3 (token usage tracking), 13.1 (LLM call matrix with per-stage timeouts), 8.5.2 (revise loop timing bounds) |
| 10 | **Deterministic seed for tests**: How to make LLM calls reproducible in tests? | RESOLVED | `TestLLMAdapter` in-memory implementation lives at `tests/k1/planner/adapters/test_llm_adapter.py`.  It implements `ILLMPort` Protocol with deterministic `HubResponse` construction.  Responses are keyed by stage name (SKETCH/EXPAND/VALIDATE) so each stage gets its own canned response.  The adapter returns pre-configured `CapabilityResult.content` (valid JSON matching each stage's OUTPUT_SCHEMA) and `ResponseMetadata` (token counts, latency, model_id).  No real LLM is invoked in any unit or integration test.  `conftest.py` wires `TestLLMAdapter` via `PlannerFactory.create_for_testing()`. | 30.3 (test adapter list + design principle), 30.5.1 F08 (PlannerFactory.create_for_testing), 30.4 (test file structure), 13.1 (LLM call matrix -- what each stage expects) |

### 31.3 Summary

All 10 original open questions have been resolved by the deep-dive sections
(Sections 6-13, 24, 30).  No design session decisions remain outstanding for V1
implementation.  V2 topics noted in Q7 (preemptive micro-replan) and Q6 (K0 WAL
format optimization) are deferred and tracked outside this document.

---

## 32. Type Ownership Reference

All shared planning types are defined in `k1/orchestrator/types.py` (source of truth). Planner re-exports from `k1/planner/__init__.py` for convenience.

| Type | Owner | Fields | Used By |
|------|-------|--------|---------|
| PlanRequest | k1/orchestrator/types.py | intent, trace_id, context, request_id, constraints, timeout_ms | Orchestrator -> Planner |
| PlanAck | k1/orchestrator/types.py | request_id, status, estimated_duration_ms | Planner -> Orchestrator |
| CommittedPlan | k1/orchestrator/types.py | plan_id, request_id, intent, steps, trace_id, dependencies, estimated_duration_ms, created_at | Planner -> Orchestrator -> DAGExecutor |
| PlanStep | k1/orchestrator/types.py | 14 frozen fields | CommittedPlan.steps[], DAGExecutor, Guards |
| MicroReplanRequest | k1/orchestrator/types.py | original_plan_id, completed_results, remaining_steps, trace_id, request_id, discoveries, failure_context | Orchestrator -> Planner |
| ConditionExpr | k1/orchestrator/types.py | structured expression tree | PlanStep.condition |
| Discovery | k1/orchestrator/types.py | runtime discoveries | MicroReplanRequest.discoveries |
| FailureContext | k1/orchestrator/types.py | step_id, error_code, error_message, partial_result | MicroReplanRequest.failure_context |
| HubRequest | k1/model_hub/types.py | capability, payload, constraints, trace_id | Planner -> Model Hub |
| HubResponse | k1/model_hub/types.py | result, metadata | Model Hub -> Planner |
