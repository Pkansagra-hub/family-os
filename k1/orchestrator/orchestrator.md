# Orchestrator -- Deep Architecture Discussion

> **Status**: Design Discussion (Hyper-Detailed)
> **Date**: 2026-02-06
> **Layer**: L2 in K1 Cognitive Architecture Skeleton
> **Position**: Between Concierge (L1) and Capability Fabric (L2.5)
> **Governing Documents**:
>
> - `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` (L2_ORCHESTRATOR subgraph)
> - `docs/architecture/whiteboard_k1/whiteboard_concierge_orchestrator_planner_fabric.md` (Sections 4, 6, 9, 10, 11, 12)
> - `k1/fabric/fabric.mmd` (caller touchpoints, execution flow)
> - `k1/concierge/concierge.mmd` (FabricOrchestratorAdapter, DeltaBusAdapter)
> **ADRs**: ADR-0006 (superseded -- Contract-Net -> Blind DAG), ADR-0005 (Agent Lifecycle), ADR-0007 (4-Stage Planner), ADR-0017 (Single Writer), ADR-0028 (Performance Scheduling)

---

## 1. Identity & Position in K1

The Orchestrator is Layer 2 of the K1 Cognitive Kernel. It sits between the Concierge (L1 -- user-facing intelligence) and the Capability Fabric (L2.5 -- execution engine). The Orchestrator is a **pure deterministic actor**: it has NO LLM, NO tools, and NEVER writes SessionState. It is the blind muscle of the system -- Concierge tells it what to do (MEDIUM tier) or the Planner gives it a plan (HIGH tier), and it mechanically executes the work through Fabric.

**Key analogy**: Orchestrator = LangGraph execution engine. Someone (the Planner) gives it explicit instructions on what to do. It does not think. It follows.

### Position in call chain

```
User -> Concierge (L1) -> Orchestrator (L2) -> Planner (L3, conditional)
                                             -> Fabric (L2.5) -> Sub-Agents (L4) / Tools
```

### When Orchestrator is involved

| Tier | Orchestrator? | What happens |
|------|------|------|
| LOW | No | Concierge calls Fabric directly via `invoke_capability()` |
| MEDIUM | Yes | Concierge sends TaskEnvelope, Orchestrator coordinates 1-2 Fabric calls |
| HIGH | Yes | Concierge sends TaskEnvelope, Orchestrator routes to Planner, executes CommittedPlan DAG |
| CRISIS | No | Safety Agent handles immediately |

### What Orchestrator is NOT (non-negotiable)

- NOT an LLM consumer (zero LLM calls, zero token budget)
- NOT a tool caller (zero tools -- it directly invokes Fabric APIs)
- NOT a state writer (NEVER writes SessionState, INV-04)
- NOT a planner (walks a plan, does not create one)
- NOT a negotiator (Contract-Net Protocol from ADR-0006 is superseded)
- NOT a decision maker (deterministic: follow DAG, retry, cancel, aggregate)

---

## 2. Hard Invariants

These are non-negotiable rules. Violation means rejection.

| ID | Invariant | Enforced By |
|----|-----------|-------------|
| ORCH-01 | Orchestrator NEVER writes SessionState | OrchestratorActor (no IStatePort) |
| ORCH-02 | Orchestrator has NO LLM -- zero model calls | Architecture constraint (no model gateway port) |
| ORCH-03 | Orchestrator has ZERO tools -- it calls Fabric APIs directly | Architecture constraint (no tool registration) |
| ORCH-04 | Every step execution goes through Fabric (never direct provider invocation) | FabricGateway routing |
| ORCH-05 | DAG execution follows topological order (no out-of-order execution) | TopologicalWalker |
| ORCH-06 | Step retry limit: 2 retries, then graceful failure | StepRetry policy |
| ORCH-07 | Dependent steps CANCELLED on parent failure; independent steps CONTINUE | StepCancellation policy |
| ORCH-08 | Workflow execution depth: max 3 (workflow -> workflow -> workflow) | WorkflowDepthGuard |
| ORCH-09 | All orchestration events emitted to DeltaBus with `cognitive_trace_id` | OrchestratorActor |
| ORCH-10 | MEDIUM tier: max 2 Fabric calls (no planning involved) | OrchestratorActor routing logic |
| ORCH-11 | HIGH tier: CommittedPlan required from Planner before execution | OrchestratorActor routing logic |
| ORCH-12 | Cross-workflow triggers validated for cycles before execution | CrossWorkflowResolver + Planner Stage 3 |
| ORCH-13 | Max 1 micro-replan per DAG execution (prevents infinite replan loops) | DAGExecutor checkpoint guard |
| ORCH-14 | DAG total tokens MUST NOT exceed `plan.token_budget_max` | TokenBudgetTracker |
| ORCH-15 | Every agent step result validated against `output_schema` before parameter resolution | OutputSchemaGuard |
| ORCH-16 | Conditional edges evaluated only at wave boundaries using deterministic boolean expressions | ConditionalEdgeEvaluator |

---

## 3. Core Architecture Components

The L2_ORCHESTRATOR subgraph contains 4 major subsystems:

### 3.1 Orchestrator Core

| Component | Purpose | Notes |
|-----------|---------|-------|
| **OrchestratorActor** | Pure deterministic logic, central dispatch | Receives TaskEnvelope, routes MEDIUM/HIGH, aggregates results |
| **Orchestrator Mailbox** | MPSC queue with WFQ priority (REALTIME) | Single inbound entry point, dequeues to OrchestratorActor |
| **Fabric Gateway** | Bridge to Capability Fabric | All Fabric calls go through this gateway |
| **Workflow Orchestrator** | Capability-based workflow execution | Coordinates workflow runs using Fabric |

### 3.2 Blind DAG Executor

The heart of HIGH-tier execution. Supersedes ADR-0006 Contract-Net Protocol.

| Component | Purpose | Notes |
|-----------|---------|-------|
| **Topological Walker** | Walks `CommittedPlan.steps[]` in dependency order | Uses topological sort on `dependencies` graph |
| **Parallel DAG** | Concurrent execution of independent steps | Steps with no unmet deps run in parallel via `execute_batch()` |
| **DAG Engine** | Dependency resolution and ordering | Builds execution waves from dependency graph |
| **Step Retry** | 2 retries then graceful failure | Same capability, same params per retry |
| **Step Cancellation** | Cancel dependent steps on parent failure | Independent steps unaffected |
| **Saga Recovery** | Compensating transactions for partial rollback | When steps with side effects fail |
| **Constraint Resolution Engine** | Iterative validation and HIL support | Max 3 cycles, Fabric-aware |

### 3.3 User Workflow System

Manages saved plans as scheduled or event-driven workflows.

| Component | Purpose | Notes |
|-----------|---------|-------|
| **Workflow Registry** | Stores `WorkflowSpec` + `TriggerSpec` | Persistent store for all workflows |
| **Workflow Version Pointer** | Active version per workflow | Version bump on re-plan |
| **Workflow Compiler** | Rehydrates frozen DAG from `WorkflowSpec` | Intent -> Capability DAG |
| **Workflow Scheduler** | Time/Event/Proactive triggers | Cron + Relative + Absolute time support |
| **System Clock** | UTC time source + `device_local_time()` | Shared by temporal resolution and scheduler |
| **Workflow Run Supervisor** | Leases + Guards + Lifecycle per run | Creates Run Manifest, monitors execution |
| **Run Manifest** | Pinned version + Compiled hash per run | Audit trail for every workflow execution |
| **Cross-Workflow Resolver** | `workflow.run.*` triggers sub-workflows | Resolves nested workflow references |
| **Workflow Depth Guard** | Max depth: 3, cycle detection | Hard limit on recursive workflow nesting |

### 3.4 Connector Ecosystem

MCP server management and tool registration.

| Component | Purpose | Notes |
|-----------|---------|-------|
| **Local MCP Servers** | Device-hosted personal tools | Always available (Edge-First) |
| **Remote MCP Servers** | Company-hosted external systems | Requires network |
| **K0 Connector Proxy** | Cloud-hosted auth/routing/caching | Optional enhancement |
| **Connector Sandbox** | Isolation and security | Per-connector sandboxing |
| **MCP Capability Registrar** | Auto-registers tools as capabilities | Populates Fabric Capability Registry |
| **MCP Tool Discovery** | Auto-discovers tool capabilities | Scans MCP servers for available tools |
| **MCP Provider Factory** | Creates capability handlers | Instantiates MCP-backed providers for Fabric |

---

## 4. Mailbox & Message Protocol

### 4.1 Orchestrator Mailbox

The Orchestrator Mailbox is an MPSC (Multiple-Producer, Single-Consumer) queue with Weighted Fair Queuing at REALTIME priority.

**Producers** (who can enqueue):

- Concierge DISPATCHING state (via FabricOrchestratorAdapter) -- sends `TaskEnvelope`
- Planner (via `k1.planner.plan.ready` event) -- sends `CommittedPlan`
- Workflow Scheduler (on trigger fire) -- sends `WorkflowRunRequest`
- Workflow Provider (from Fabric, for sub-workflow triggers) -- sends rehydrated plan

**Consumer**: OrchestratorActor (single consumer, dequeues and processes sequentially or fans out to DAG)

### 4.2 Message Envelopes

Every message flowing through the Orchestrator has a specific schema:

**TaskEnvelope** (Concierge -> Orchestrator)

```yaml
TaskEnvelope:
  envelope_id: uuid
  cognitive_trace_id: uuid     # traces the entire user turn
  intent: string               # classified intent from UltraBERT + LLM
  context:
    beliefs_snapshot: object   # relevant beliefs from SessionState
    entities: object[]         # resolved entities (PERSON, LOC, TIME, etc.)
    temporal_context: object   # resolved absolute times
    safety_band: enum          # GREEN | AMBER | RED
    persona_hints: object      # conversational style preferences
  tier: enum                   # MEDIUM | HIGH (LOW bypasses Orchestrator)
  capabilities: string[]       # (MEDIUM only) specific capabilities to invoke
  params: object               # (MEDIUM only) parameters for capability calls
  created_at: datetime
  timeout_ms: number           # from budget envelope (MEDIUM: 10000, HIGH: 45000)
```

**PlanRequest** (Orchestrator -> Planner)

```yaml
PlanRequest:
  request_id: uuid
  cognitive_trace_id: uuid
  intent: string
  constraints:
    budget: object | null
    safety_band: enum
    time_constraints: object | null
    permissions: string[]
  context:
    beliefs_snapshot: object
    entities: object[]
    temporal_context: object
  created_at: datetime
  timeout_ms: number           # Planner budget: 4 stages x ~10s each
```

**CommittedPlan** (Planner -> Orchestrator)

```yaml
CommittedPlan:
  plan_id: uuid
  cognitive_trace_id: uuid
  intent: string
  created_at: datetime
  token_budget_max: number     # max total LLM tokens across all agent steps (ORCH-14)
  steps:
    - id: string               # e.g., "s1", "s2"
      capability: string       # e.g., "tool.execute.restaurant_booking"
      prompt_template: string | null
      params: object
      tools_granted: string[]  # for agent capabilities (FAB-07 scoping)
      output_schema: JsonSchema | null  # expected output shape for agent validation (ORCH-15)
      deps:                    # dependency step IDs -- can be string or conditional object
        - string               # unconditional: "s1"
        - step: string         # conditional: {step: "s1", condition: "s1.status == COMPLETED"}
          condition: string    # deterministic boolean expression (ORCH-16)
      timeout_ms: number       # per-step timeout
  dependencies:
    <step_id>: [<dep_spec>, ...]  # explicit DAG edges (unconditional or conditional)
  wal_offset: number           # K0 WAL write position (crash recovery)
```

**CapabilityRequest** (Orchestrator -> Fabric)

```yaml
CapabilityRequest:
  request_id: uuid
  cognitive_trace_id: uuid
  step_id: string | null       # null for MEDIUM direct calls
  capability_name: string      # e.g., "tool.execute.restaurant_booking"
  params: object
  prompt_template: string | null
  tools_granted: string[]      # for agent spawning (FAB-07)
  output_schema: JsonSchema | null  # expected output shape for agent validation
  schema_hint: string | null   # injected on retry when schema validation failed
  context:
    beliefs_snapshot: object
    entities: object[]
    temporal_context: object
    persona_hints: object
  timeout_ms: number
  retry_attempt: number        # 0, 1, or 2
```

**MicroReplanRequest** (Orchestrator -> Planner, max 1 per DAG, ORCH-13)

```yaml
MicroReplanRequest:
  request_id: uuid
  cognitive_trace_id: uuid
  original_plan_id: uuid
  checkpoint:
    completed_steps: object[]   # {step_id, result_data}
    completed_waves: number
  discoveries: object[]         # new info from agent results
  remaining_steps: object[]     # not yet executed steps from original plan
  constraints:                  # same as original PlanRequest.constraints
    budget: object | null
    safety_band: enum
    time_constraints: object | null
    permissions: string[]
  created_at: datetime
  timeout_ms: number            # reduced: remaining budget only
```

**CapabilityResult** (Fabric -> Orchestrator)

```yaml
CapabilityResult:
  result_id: uuid
  request_id: uuid             # matches CapabilityRequest.request_id
  cognitive_trace_id: uuid
  step_id: string | null
  success: boolean
  data: object | null          # result payload (tool output, agent response, etc.)
  error:
    code: string               # error classification
    message: string
    retryable: boolean
    provider_id: string
  duration_ms: number
  tokens_consumed: number      # LLM tokens used (0 for pure tools)
  quality_score: float | null  # 0.0-1.0, null for non-agent steps
  discoveries: object[] | null # new info that may invalidate plan assumptions
  provider_id: string
  provider_type: enum          # MCP | WASM | BRIDGE | AGENT | WORKFLOW | CONCIERGE
```

---

## 5. MEDIUM Tier Execution Flow

MEDIUM tasks need 1-2 specialized agents or tools but no full planning pipeline. Concierge already knows WHAT to do (it has read tools like `discover_capabilities()`). It sends a detailed TaskEnvelope to Orchestrator. Orchestrator coordinates 1-2 Fabric calls and returns results.

### 5.1 Sequence

```
1. Concierge DISPATCHING creates TaskEnvelope{tier=MEDIUM, capabilities[], params}
2. TaskEnvelope -> Orchestrator Mailbox
3. Concierge FSM -> COMPANIONING (LLM preliminary ack ~200 tokens + cognitive tools)
4. OrchestratorActor dequeues, emits k1.orchestration.task.accepted
5. OrchestratorActor constructs 1-2 CapabilityRequest(s) from envelope
6. Each CapabilityRequest -> Fabric Gateway -> Capability Fabric
7. Fabric resolves, builds context, executes, returns CapabilityResult
8. If 2 calls: both run concurrently (no dependency between them)
9. OrchestratorActor aggregates results
10. Aggregated results -> Concierge COMPANIONING -> TOOL_RESULT_BUFFER
11. Orchestration delta -> DeltaBus -> Aggregation Window -> Concierge FSM
12. Concierge DELIVERING: LLM final response (~2K tokens) + cognitive tools -> OUTPUT_CHANNEL
```

### 5.2 Key constraints

- Max 2 Fabric calls (ORCH-10)
- No Planner involvement
- No DAG -- direct capability invocation
- TaskEnvelope.capabilities[] explicitly lists what to invoke
- Timeout: 10s budget envelope

### 5.3 Example

```
User: "What's the weather in San Jose and set a reminder for 3pm"

UltraBERT: 2 intents (check_weather + set_reminder), 1 domain (PERSONAL)
Complexity: MEDIUM (multi-intent, single domain, both simple)

TaskEnvelope{
  tier: MEDIUM,
  intent: "check_weather + set_reminder",
  capabilities: ["tool.execute.weather_check", "tool.execute.set_reminder"],
  params: {
    weather: {location: "San Jose"},
    reminder: {time: "2026-02-06T15:00:00-08:00", text: "3pm reminder"}
  }
}

Orchestrator: 2 concurrent CapabilityRequests -> Fabric
  Both return within ~2s
  Aggregate: {weather: "72F sunny", reminder: "set for 3:00 PM"}
  -> Concierge DELIVERING: "It's 72 and sunny in San Jose! I've also set your 3pm reminder."
```

---

## 6. HIGH Tier Execution Flow

HIGH tasks require multi-step planning with dependency management. The Orchestrator routes to the Planner for plan construction, then executes the resulting DAG.

### 6.1 Sequence

```
1. Concierge DISPATCHING creates TaskEnvelope{tier=HIGH, intent, context}
2. TaskEnvelope -> Orchestrator Mailbox
3. Concierge FSM -> COMPANIONING (LLM preliminary ack ~200 tokens + cognitive tools)
4. OrchestratorActor dequeues, emits k1.orchestration.task.accepted
5. OrchestratorActor constructs PlanRequest{intent, constraints, context}
6. PlanRequest -> Planner Mailbox

--- PLANNER PIPELINE (see Planner design doc) ---
7. Planner Stage 1 (SKETCH): LLM + discovery tools -> rough plan
8. Planner Stage 2 (EXPAND): LLM + find_relevant_prompts -> tool mapping + dependency graph
9. Planner Stage 3 (VALIDATE): LLM arbiter -> all capabilities exist, DAG acyclic, no safety violations
10. Planner Stage 4 (COMMIT): Deterministic -- persist CommittedPlan to K0 WAL
11. Planner emits k1.planner.plan.ready -> Orchestrator Mailbox
--- END PLANNER ---

12. OrchestratorActor receives CommittedPlan
13. DAG Engine builds execution waves from dependencies
14. TopologicalWalker walks waves:
    - Wave 1: All steps with deps=[] -> run concurrently via Fabric
    - Wave 2: Steps whose deps are in Wave 1 -> wait for Wave 1, then run
    - ...continue until all waves complete
15. Per step: CapabilityRequest -> Fabric Gateway -> Fabric -> CapabilityResult
16. Per step: emit progress delta -> DeltaBus -> Concierge PROGRESSING -> OUTPUT_CHANNEL
17. All steps complete: OrchestratorActor aggregates all results
18. Aggregated results -> Concierge COMPANIONING -> TOOL_RESULT_BUFFER
19. Concierge DELIVERING: LLM final response (~8K tokens) + cognitive tools -> OUTPUT_CHANNEL
```

### 6.2 Example (Birthday party)

```
User: "Plan a birthday party for Mom next Saturday -- book a restaurant,
       order a cake, and send invitations to family"

TaskEnvelope{tier=HIGH, intent="plan_event_birthday"}

PlanRequest{intent="plan birthday party for Mom...", constraints={safety=GREEN}}

CommittedPlan{
  steps: [
    s1: {capability: "tool.execute.restaurant_booking", deps: [], params: {date, party_size, cuisine}}
    s2: {capability: "tool.execute.cake_order", deps: [], params: {type, flavor, date}}
    s3: {capability: "tool.read.k0_recall", deps: [], params: {query: "family contact info"}}
    s4: {capability: "agent.execute.invitation_sender", deps: [s1, s3],
         tools_granted: ["tool.execute.send_message", "tool.read.contact_lookup"],
         prompt_template: "invitation_drafter_v1",
         params: {event: "birthday_party", recipients: "$s3.result", venue: "$s1.result.venue"}}
  ]
  dependencies: {s4: [s1, s3]}
}

Wave 1: s1, s2, s3 (all concurrent -- no deps)
Wave 2: s4 (waits for s1 + s3)

Progress: "Booking restaurant..." | "Ordering cake..." | "Getting family contacts..."
         -> "Sending invitations to 8 family members..."
```

---

## 7. Blind DAG Executor -- Topological Walking

### 7.1 Algorithm

The DAG executor is the core of HIGH-tier execution. It operates as follows:

```python
def execute_dag(committed_plan: CommittedPlan) -> AggregatedResult:
    """
    Adaptive Blind DAG Executor.
    Walks CommittedPlan in topological order with:
    - Output Schema Guard (ORCH-15): validates agent results before param resolution
    - Conditional edge evaluation (ORCH-16): branches at wave boundaries
    - Token budget tracking (ORCH-14): cumulative LLM spend enforcement
    - Quality gate: soft-fail detection for technically-successful-but-useless results
    - Mid-DAG micro-replan (ORCH-13): max 1 replan when discoveries change plan
    """
    steps = committed_plan.steps
    deps = committed_plan.dependencies
    results: dict[str, CapabilityResult] = {}
    token_budget = TokenBudgetTracker(committed_plan.token_budget_max)
    replan_used = False

    # Build execution waves (respects conditional edges)
    waves = topological_waves(steps, deps)

    for wave_idx, wave in enumerate(waves):

        # --- WAVE BOUNDARY CHECKS ---
        # 1. Re-read safety_band from SessionState (freshness)
        safety_band = state_read_port.read("control.safety_band")

        # 2. Check interrupt flag (user cancel via Concierge)
        if interrupt_flag.is_set():
            compensate_completed(results)
            return aggregate(results, status="interrupted")

        # 3. Token budget check (ORCH-14)
        if token_budget.exceeded(threshold=0.95):
            emit_delta(type="budget_exhausted", consumed=token_budget.total)
            break  # skip remaining waves, aggregate what we have

        # 4. Evaluate conditional edges for this wave (ORCH-16)
        active_steps = []
        for step in wave:
            if step.id in cancelled:
                continue
            if has_conditions(step, deps):
                if not evaluate_conditions(step, deps, results):
                    skipped.add(step.id)
                    emit_delta(step.id, None, status="skipped_condition")
                    continue
            active_steps.append(step)

        # --- EXECUTE WAVE ---
        pending = []
        for step in active_steps:
            resolved_params = resolve_references(step.params, results)
            request = CapabilityRequest(
                step_id=step.id,
                capability_name=step.capability,
                params=resolved_params,
                prompt_template=step.prompt_template,
                tools_granted=step.tools_granted,
                output_schema=step.output_schema,
                timeout_ms=step.timeout_ms,
                retry_attempt=0
            )
            pending.append(fabric.execute_async(request))

        wave_results = await_all(pending)

        # --- POST-WAVE: validate, track, detect ---
        discoveries = []
        for step_id, result in wave_results:

            # Token budget accumulation (ORCH-14)
            token_budget.add(result.tokens_consumed)

            # Quality gate: detect soft failures
            if result.success and result.quality_score is not None:
                if result.quality_score < 0.3:
                    # Treat as soft failure -- retry with quality hint
                    result = retry_step(step_id, request, quality_hint=True, max_retries=1)
                    if result.quality_score < 0.3:
                        result.success = False
                        result.error = {"code": "quality_below_threshold"}

            if result.success:
                # Output Schema Guard (ORCH-15)
                step = get_step(step_id, steps)
                if step.output_schema:
                    schema_valid = validate_output_schema(result.data, step.output_schema)
                    if not schema_valid:
                        # Retry with schema_hint injected into agent prompt
                        result = retry_step(step_id, request,
                                            schema_hint=step.output_schema, max_retries=1)
                        if not validate_output_schema(result.data, step.output_schema):
                            result.success = False
                            result.error = {"code": "output_schema_mismatch"}

            if result.success:
                results[step_id] = result
                emit_delta(step_id, result, status="completed")
                emit_progress(step_id, result.summary)
                # Collect discoveries for potential micro-replan
                if result.discoveries:
                    discoveries.extend(result.discoveries)
            else:
                result = retry_step(step_id, request, max_retries=2)
                if not result.success:
                    results[step_id] = result
                    emit_delta(step_id, result, status="failed")
                    for dependent in transitive_dependents(step_id, deps):
                        cancelled.add(dependent)
                        emit_delta(dependent, None, status="cancelled")

        # --- MID-DAG MICRO-REPLAN (ORCH-13) ---
        if discoveries and not replan_used and wave_idx < len(waves) - 1:
            remaining = [s for w in waves[wave_idx+1:] for s in w if s.id not in cancelled]
            if micro_replan_needed(discoveries, remaining):
                replan_used = True
                emit_delta(type="micro_replan_triggered", discoveries=discoveries)
                updated_plan = planner_port.micro_replan(
                    MicroReplanRequest(
                        checkpoint=results,
                        discoveries=discoveries,
                        remaining_steps=remaining
                    )
                )
                if updated_plan:
                    # Rebuild waves from checkpoint
                    waves = topological_waves(updated_plan.steps, updated_plan.dependencies)
                    # Continue from next wave (completed waves already done)
                    continue

    return aggregate(results)
```

### 7.2 Topological Wave Construction

```
Input DAG:
  s1 -> []
  s2 -> []
  s3 -> []
  s4 -> [s1, s3]
  s5 -> [s4]

Wave 0: [s1, s2, s3]   # no deps
Wave 1: [s4]            # deps on s1, s3 (both in Wave 0)
Wave 2: [s5]            # deps on s4 (in Wave 1)
```

Steps within the same wave execute concurrently via `execute_batch()`. Steps in different waves execute sequentially (each wave waits for the previous wave to complete).

### 7.3 Parameter Reference Resolution

Steps can reference results from earlier steps using `$<step_id>.result.<path>` syntax:

```yaml
params:
  recipients: "$s3.result"         # entire result of step s3
  venue: "$s1.result.venue"        # nested field from s1's result
  date: "2026-02-14"               # literal value (no reference)
```

Resolution happens at step execution time (not at plan creation). If a referenced step failed, the current step is already cancelled by dependency cancellation, so this case never arises.

---

## 8. Step Retry & Failure Handling

### 8.1 Retry Policy

When a plan step fails:

```
Attempt 0: Execute step normally
  -> failure? ->
Attempt 1: Same capability, same params (transient failure assumption)
  -> failure? ->
Attempt 2: Same capability, same params (confirm persistent failure)
  -> failure? ->
Graceful failure:
  - Mark step as FAILED
  - Continue independent steps
  - Cancel all transitive dependents
```

### 8.2 Dependent Cancellation

When step `s1` fails (after 2 retries):

```
s1 FAILED
s4 depends on s1 -> s4 CANCELLED
s5 depends on s4 -> s5 CANCELLED (transitive)

s2 and s3 have no deps on s1 -> s2, s3 CONTINUE
```

### 8.3 Partial Result Aggregation

Even with failures, the Orchestrator aggregates ALL results (success + failure + cancelled) and sends the aggregated result to Concierge:

```yaml
AggregatedResult:
  cognitive_trace_id: uuid
  plan_id: uuid
  steps:
    s1: {status: FAILED, error: {code: "provider_timeout", message: "..."}}
    s2: {status: COMPLETED, data: {cake_order_id: "..."}}
    s3: {status: COMPLETED, data: {contacts: [...]}}
    s4: {status: CANCELLED, reason: "dependency s1 failed"}
    s5: {status: CANCELLED, reason: "dependency s4 cancelled (transitive)"}
  total_steps: 5
  completed_steps: 2
  failed_steps: 1
  cancelled_steps: 2
  success: false  # at least one step failed
```

Concierge's DELIVERING LLM call receives this and generates a polite user-facing message:

> "I was able to order the cake and get the family contacts, but the restaurant booking didn't go through. Would you like me to try a different restaurant service, or would you prefer to book manually?"

No automatic re-planning. User decides next action.

---

## 9. Saga Pattern & Compensating Transactions

### 9.1 When Saga applies

The Saga pattern applies when a step with **side effects** fails and earlier steps with side effects already succeeded. Example:

```
s1: Book restaurant  -> SUCCESS (side effect: reservation created)
s2: Order cake       -> SUCCESS (side effect: order placed)
s3: Charge card      -> FAILED  (payment declined)

Without Saga: Restaurant booked, cake ordered, but no payment -> inconsistent
With Saga: Compensate s1 (cancel reservation), compensate s2 (cancel order)
```

### 9.2 Compensating transactions

Each capability contract CAN declare a compensation action:

```yaml
tool_contract:
  name: "tool.execute.restaurant_booking"
  compensation:
    capability: "tool.execute.restaurant_cancel"
    params_from_result: ["confirmation_id"]
```

When the Saga recovery fires:

1. Collect all completed steps with compensation actions
2. Execute compensations in reverse order (s2 first, then s1)
3. If compensation fails: log to dead-letter, alert via telemetry (human intervention)
4. Report compensation status in AggregatedResult

### 9.3 When Saga does NOT apply

- Tool-only steps with no side effects (read-only queries): no compensation needed
- Steps that failed before producing side effects: no compensation needed
- Steps where the user has already been notified of success: compensation + user notification

---

## 10. Constraint Resolution Engine

The Constraint Resolution Engine sits inside the Blind DAG Executor and handles iterative constraint validation with optional HIL (Human-in-the-Loop) support.

### 10.1 Components

| Component | Purpose |
|-----------|---------|
| **Constraint Manager** | Oversees the iterative validation flow |
| **Iteration Controller** | Enforces max 3 resolution cycles |
| **Constraint Graph** | Priority and dependency graph of constraints |
| **Solution Validator** | LLM + Rule-based validation (lives in Planner, results consumed here) |
| **Fallback Trigger** | Routes to HIL when automated resolution stalls |
| **Capability Constraint Resolver** | Fabric-aware validation (checks real capability availability) |

### 10.2 Flow

```
1. CommittedPlan arrives at Orchestrator
2. Pre-execution constraint check:
   a. All referenced capabilities exist in Fabric registry?
   b. All required params satisfiable from context + step deps?
   c. All safety band requirements met?
   d. Total estimated time within budget envelope?
3. If all constraints pass: proceed to DAG execution
4. If constraints fail:
   Cycle 1: Capability Constraint Resolver queries Fabric for alternatives
   Cycle 2: Try alternative capabilities, re-validate
   Cycle 3: Fallback Trigger -> HIL question to user
   After 3 cycles: graceful failure with explanation
```

### 10.3 Fabric-aware validation

The Capability Constraint Resolver queries Fabric's Capability Registry during constraint checking:

```
Step references "tool.execute.restaurant_booking"
  -> Resolver asks Fabric: "Is this capability available?"
  -> Fabric checks: registry entry exists, provider ONLINE, safety band OK
  -> Result: yes/no + reason
```

If a capability is unavailable, the resolver can suggest alternatives (e.g., `tool.execute.restaurant_booking_v2`) from the registry lookup.

---

## 11. Result Aggregation & Return Path

### 11.1 Aggregation

As each step completes, the OrchestratorActor collects results into an aggregated structure:

```
Per step:
  - CapabilityResult from Fabric
  - Execution duration
  - Step status (COMPLETED | FAILED | CANCELLED)
  - Error details (if any)
  - Retry attempts consumed
```

### 11.2 Return path

```
Orchestrator aggregates all results
  -> aggregated results sent to Concierge COMPANIONING
  -> COMPANIONING stages results in TOOL_RESULT_BUFFER
  -> DELIVERING: LLM reads TOOL_RESULT_BUFFER, generates final response
  -> OUTPUT_CHANNEL -> User
```

### 11.3 Progress reporting

During execution, each step completion triggers a progress delta:

```
emit_delta{
  type: "k1.orchestration.delta.v1",
  cognitive_trace_id: <trace>,
  payload: {
    type: "step_complete",
    step_id: "s1",
    result_summary: "Restaurant booked: Olive Garden, Feb 14, 8 guests"
  }
}
```

This delta flows: DeltaBus -> Aggregation Window (500ms batching) -> Concierge FSM -> PROGRESSING -> OUTPUT_CHANNEL (user sees streaming progress updates).

---

## 12. Delta Bus Integration

### 12.1 What Orchestrator emits

| Delta Type | When | Content |
|------------|------|---------|
| `k1.orchestration.task.accepted` | Task dequeued from mailbox | `{envelope_id, tier}` |
| `k1.orchestration.step.started` | Step execution begins | `{step_id, capability}` |
| `k1.orchestration.step.complete` | Step finishes (success) | `{step_id, result_summary, duration_ms}` |
| `k1.orchestration.step.failed` | Step fails (after retries) | `{step_id, error, retry_attempts}` |
| `k1.orchestration.step.cancelled` | Dependent step cancelled | `{step_id, reason, parent_step}` |
| `k1.orchestration.plan.complete` | All steps done | `{plan_id, completed, failed, cancelled}` |
| `k1.orchestration.delta.v1` | Any state change | Aggregated orchestration delta |

### 12.2 What Orchestrator reads

The Orchestrator reads from the DeltaBus only for the Planner's plan-ready signal:

```
k1.planner.plan.ready -> contains CommittedPlan -> dequeue and execute
```

### 12.3 Delta flow

```
OrchestratorActor emits orchestration deltas
  -> K1 Event Bus (pub/sub topics)
  -> DeltaBus subscriber in Concierge (DeltaBusAdapter)
  -> Aggregation Window (500ms batching, LWW merge)
  -> Concierge FSM receives aggregated batch
  -> Concierge applies to SessionState via MutationGuard (Single Writer, INV-01)
```

---

## 13. SessionState Access Pattern

### 13.1 Reader, never writer

The Orchestrator reads SessionState via the multi-reader lock-free interface. It NEVER writes.

| Operation | Allowed? | How |
|-----------|----------|-----|
| Read beliefs_active | Yes | Multi-reader, lock-free |
| Read entities | Yes | From TaskEnvelope context snapshot |
| Read persona | Yes | Multi-reader |
| Read temporal_context | Yes | From TaskEnvelope context snapshot |
| Write anything | **NO** | INV-04 prohibits this |

### 13.2 Context passing

The Orchestrator passes SessionState context to Fabric through `CapabilityRequest.context`. Fabric's Context Builder uses this to assemble agent/tool context windows. The Orchestrator does NOT inject context itself -- it passes the raw snapshot and lets Fabric handle token budgeting and prompt compilation.

### 13.3 Snapshot freshness

For MEDIUM tier: Context comes from the TaskEnvelope snapshot (captured at DISPATCHING time). This is at most ~200ms stale, which is acceptable for 2-10s operations.

For HIGH tier: Context captured at DISPATCHING time may be 10-60s stale by the time later steps execute. For critical context (e.g., safety_band), the Orchestrator re-reads from SessionState at each wave boundary to ensure freshness.

---

## 14. User Workflow System

### 14.1 How a Plan Becomes a Workflow

```
1. HIGH-tier task runs successfully (Planner + Orchestrator + Fabric)
2. User says: "Do this every Monday morning" or "Make this a workflow"
3. Concierge recognizes intent (UltraBERT: save_workflow)
4. CommittedPlan saved to Workflow Registry as WorkflowSpec
5. TriggerSpec attached based on user request
```

### 14.2 WorkflowSpec Schema

```yaml
WorkflowSpec:
  workflow_id: uuid
  name: string                    # user-friendly name
  source_plan_id: uuid            # reference to original CommittedPlan
  version: number                 # monotonic version (bumps on re-plan)
  trigger:
    type: enum                    # "cron" | "event" | "manual"
    schedule: string | null       # cron expression (e.g., "0 8 * * MON")
    event_topic: string | null    # event trigger topic
    timezone: string              # IANA timezone (e.g., "America/Los_Angeles")
  steps: <same as CommittedPlan.steps[]>
  dependencies: <same as CommittedPlan.dependencies>
  created_at: datetime
  updated_at: datetime
  last_run: datetime | null
  active: boolean
```

### 14.3 Workflow Execution (No Re-Planning)

```
Workflow Scheduler (cron fires or event triggers)
  -> Workflow Compiler rehydrates DAG from WorkflowSpec
  -> Workflow Run Supervisor creates Run Manifest (pinned version + hash)
  -> OrchestratorActor executes DAG via Fabric (same as HIGH tier execution)
  -> Results delivered to user (or logged if no active session)
```

No Planner involved. The plan is frozen. Orchestrator just runs it.

---

## 15. Workflow Scheduler

### 15.1 Trigger types

| Type | Description | Example |
|------|-------------|---------|
| `cron` | Standard cron expression with timezone | `"0 8 * * MON"` (Mondays at 8am) |
| `event` | Fires when a specific event occurs | `"k1.k0.sse.weather_alert"` |
| `manual` | User-triggered only | "Run my meal prep workflow" |

### 15.2 Temporal integration

The Workflow Scheduler shares the System Clock with the Concierge's Temporal Resolution Engine:

```
System Clock provides: UTC now, device_local_time()
Workflow Scheduler:
  1. Reads user timezone from SessionState (control.timezone or persona)
  2. Converts cron schedule to UTC
  3. Checks: is next trigger time due?
  4. If due: create WorkflowRunRequest -> Orchestrator Mailbox
```

### 15.3 Relative triggers

Users can say "every evening" or "30 minutes after dinner". The Temporal Resolution Engine resolves these to concrete cron expressions + timezone during workflow creation:

```
"every evening" -> cron: "0 18 * * *" (6pm user-local)
"30 minutes after dinner" -> requires dinner event -> event trigger with delay
```

---

## 16. Workflow Compiler

### 16.1 Rehydration

When a workflow triggers, the Workflow Compiler rehydrates the frozen DAG:

```
1. Read WorkflowSpec from Workflow Registry
2. Validate: all referenced capabilities still exist (schema compatibility check)
3. Resolve: any dynamic parameters (e.g., "today's date", "current weather")
4. Build: execution-ready CommittedPlan from frozen steps
5. Return: ready-to-execute plan to Orchestrator
```

### 16.2 Schema mismatch detection

If a capability's contract changed since the plan was saved:

| Change Type | Compiler Action |
|-------------|-----------------|
| New optional field added | Continue (auto-fill with defaults) |
| Required field added | STOP -- proactive gap detection (see Section 17) |
| Field type changed | STOP -- proactive gap detection |
| Capability removed | STOP -- proactive gap detection |
| New version (backward compatible) | Continue with new version |

### 16.3 Run Manifest

Every workflow execution creates a Run Manifest:

```yaml
RunManifest:
  run_id: uuid
  workflow_id: uuid
  workflow_version: number        # pinned to the version at trigger time
  compiled_hash: string           # hash of the rehydrated plan (for audit)
  trigger_type: string            # what triggered this run
  trigger_time: datetime
  start_time: datetime
  end_time: datetime | null
  status: enum                    # RUNNING | COMPLETED | FAILED | ABORTED
  steps_summary: object           # per-step status
```

---

## 17. Workflow Invalidation & Proactive Gap Detection

When a tool schema changes and a saved workflow references it:

### 17.1 Detection

```
1. Capability Registry emits: k1.capability.contract_updated.v1
2. Workflow Compiler proactively scans all active WorkflowSpecs
3. Identifies workflows referencing the changed capability
4. Runs schema diff: old contract vs new contract
5. Classifies gap: SMALL (new optional field) or LARGE (breaking change)
```

### 17.2 Resolution

**SMALL gap** (new optional field):

- Auto-fill with default value from new contract
- Notify user next time they're free: "Heads up -- I updated your weekly brunch workflow to include a cuisine preference. I defaulted to 'any'. Want to change it?"

**LARGE gap** (breaking change or removed capability):

- Store gap in proactive gap detection memory (follows K0 P06 curiosity pattern)
- When user is free (not mid-conversation, not busy):
  - Concierge proactively asks with justification:
    > "Hey, the restaurant booking tool updated and now requires a preferred cuisine. For your weekly Mom brunch workflow -- what cuisine should I use?"
  - Always explain WHY we're asking and WHAT changed
- If capability removed entirely: offer re-planning with original intent

### 17.3 Proactive gap storage

```yaml
ProactiveGap:
  gap_id: uuid
  workflow_id: uuid
  detected_at: datetime
  gap_type: enum                  # SCHEMA_DRIFT | CAPABILITY_REMOVED | PERMISSION_CHANGE
  affected_step: string           # step ID in workflow
  old_contract_version: string
  new_contract_version: string | null
  question: string                # formulated question for user
  justification: string           # why we're asking
  status: enum                    # PENDING | ASKED | RESOLVED | AUTO_RESOLVED
  resolved_value: object | null
```

---

## 18. Cross-Workflow Resolution

### 18.1 How workflows trigger other workflows

A plan step can reference another workflow:

```yaml
step:
  id: s3
  capability: "workflow.run.weekly_grocery_list"
  params:
    trigger_reason: "birthday_party_prep"
    override_params:
      extra_items: ["birthday cake ingredients"]
  deps: [s1]
```

### 18.2 Resolution flow

```
1. Orchestrator encounters step with capability "workflow.run.*"
2. Cross-Workflow Resolver looks up referenced workflow in Workflow Registry
3. Workflow Compiler rehydrates the sub-workflow's DAG
4. Workflow Depth Guard checks current depth (must be < 3)
5. Sub-workflow executes as a nested DAG (Orchestrator recursion)
6. CapabilityResult returns to parent DAG step
```

### 18.3 Guard rails

| Guard | Value | Enforcement |
|-------|-------|-------------|
| Max workflow depth | 3 | WorkflowDepthGuard (ORCH-08) |
| Cycle detection | Pre-validated | Planner Stage 3 VALIDATE |
| Sub-workflow timeout | Inherited from parent step | Step timeout_ms |
| Sub-workflow audit | Own Run Manifest | Workflow Run Supervisor |

---

## 19. Connector Ecosystem

### 19.1 Overview

The Connector Ecosystem manages MCP (Model Context Protocol) servers that provide tools to the system. Connectors live in the Orchestrator layer because they bridge the gap between external tool providers and the Capability Fabric.

### 19.2 MCP Server Types

| Type | Location | Availability | Examples |
|------|----------|-------------|----------|
| **Local MCP** | Device-hosted | Always (Edge-First) | Calendar, contacts, notes, file system |
| **Remote MCP** | Company-hosted | Requires network | Restaurant booking, weather API, banking |
| **K0 Proxy** | Cloud-hosted | Optional | Auth proxy, caching layer, rate limiting |

### 19.3 Tool Registration Pipeline

```
1. MCP Tool Discovery scans MCP servers for available tools
2. For each discovered tool:
   a. Extract tool schema (name, params, description)
   b. Map to FamilyOS capability naming: "tool.execute.<name>"
   c. Generate tool contract YAML
3. MCP Capability Registrar registers in Fabric's Capability Registry
4. MCP Provider Factory creates capability handlers
5. Tools now available for Planner discovery and Fabric execution
```

### 19.4 Connector Sandbox

Every connector (MCP server) runs in an isolated sandbox:

| Isolation | Mechanism |
|-----------|-----------|
| Process isolation | Each MCP server in own process |
| Resource limits | CPU, memory, file system caps |
| Network policy | Allowlist per connector |
| Timeout enforcement | Per-call timeout (CB_MCP: 10s) |
| Output validation | Schema validation before result acceptance |

---

## 20. Circuit Breakers & Fault Tolerance

### 20.1 Owned circuit breakers

The FabricOrchestratorAdapter (in Concierge's hexagonal architecture) owns these circuit breakers:

| Circuit Breaker | Timeout | Threshold | Fallback |
|---|---|---|---|
| **CB_ORCHESTRATOR** | 60s | 2 failures/min | Degrade to LOW tier |
| **CB_PLANNER** | 45s | 2 failures/min | Skip planning, direct execution |
| **CB_FABRIC** | 30s | 5 failures/min | Capability unavailable |
| **CB_MCP** | 10s | 3 failures/min | Mark tool offline |

### 20.2 Tier degradation cascade

When circuit breakers trip, the system degrades gracefully:

```
HIGH -> CB_PLANNER OPEN -> degrade to MEDIUM (skip planning, direct Fabric calls)
MEDIUM -> CB_ORCHESTRATOR OPEN -> degrade to LOW (Concierge calls Fabric directly)
LOW -> CB_FABRIC OPEN -> degrade to canned response
Canned -> hardcoded message: "I'm having trouble with that right now. Let me try again in a moment."
```

Degradation is: **HIGH -> MEDIUM -> LOW -> canned**. Each level peels off a component.

### 20.3 MCP failure handling

When `CB_MCP` opens for a specific MCP server:

```
1. Mark all capabilities from that MCP server as UNAVAILABLE in Fabric Registry
2. Planner's discover_capabilities() will no longer surface those tools
3. Running workflows with affected tools: step retry -> fail -> graceful partial result
4. CB_MCP half-open probe: every 30s, try one call to see if server recovered
5. Server recovers -> mark capabilities ONLINE, resume normal
```

---

## 21. Performance Targets

### 21.1 Orchestrator-owned latencies

| Operation | Target (P99) | Notes |
|-----------|-------------|-------|
| TaskEnvelope dispatch (envelope creation + mailbox enqueue) | 2ms | From Concierge measurements |
| Mailbox dequeue + routing decision | < 1ms | In-memory, hash-based |
| DAG wave construction (topological sort) | < 5ms | For plans up to 50 steps |
| CapabilityRequest construction | < 1ms | Serial per step |
| Result aggregation | < 2ms | Collect + summarize |
| Progress delta emission | < 1ms | Fire-and-forget to DeltaBus |
| Total Orchestrator overhead (excl. Fabric + Planner) | < 15ms | Sum of above |

### 21.2 End-to-end tier budgets

| Tier | Total Budget | Orchestrator Overhead | Fabric Time | Planner Time |
|------|-------------|----------------------|-------------|-------------|
| MEDIUM | 10s | < 15ms | 1-9.9s | N/A |
| HIGH | 45s (15s headroom before CB 60s) | < 15ms | Varies per step | 10-30s (4 stages) |

### 21.3 DAG execution targets

| Metric | Target |
|--------|--------|
| Steps per plan (typical) | 3-8 |
| Steps per plan (max) | 50 |
| Concurrent steps per wave | Up to 10 |
| Step timeout (default) | 30s |
| Retry delay | 0ms (immediate retry) |

---

## 22. Observability & Telemetry

### 22.1 Trace propagation

Every operation carries `cognitive_trace_id` from the original user turn:

```
User message -> cognitive_trace_id: "abc-123"
  -> TaskEnvelope.cognitive_trace_id: "abc-123"
  -> PlanRequest.cognitive_trace_id: "abc-123"
  -> CommittedPlan.cognitive_trace_id: "abc-123"
  -> CapabilityRequest.cognitive_trace_id: "abc-123"
  -> CapabilityResult.cognitive_trace_id: "abc-123"
  -> All deltas carry "abc-123"
```

This allows end-to-end trace reconstruction from user message to final response.

### 22.2 Structured logs

| Log Event | Level | Data |
|-----------|-------|------|
| task_received | INFO | envelope_id, tier, intent |
| plan_requested | INFO | request_id, intent |
| plan_received | INFO | plan_id, step_count, dep_count |
| wave_started | INFO | wave_number, step_count |
| step_started | INFO | step_id, capability, attempt |
| step_completed | INFO | step_id, duration_ms, success |
| step_failed | WARN | step_id, error_code, attempt |
| step_cancelled | INFO | step_id, reason, parent_step |
| step_skipped_condition | INFO | step_id, condition, evaluation_result |
| schema_validation_failed | WARN | step_id, expected_schema, actual_keys |
| quality_below_threshold | WARN | step_id, quality_score, threshold |
| micro_replan_triggered | INFO | plan_id, wave_idx, discovery_count |
| micro_replan_completed | INFO | plan_id, new_step_count, removed_steps |
| token_budget_warning | WARN | plan_id, consumed, budget_max, threshold |
| token_budget_exhausted | ERROR | plan_id, consumed, budget_max |
| aggregation_complete | INFO | plan_id, completed, failed, cancelled |
| tier_degradation | WARN | from_tier, to_tier, reason |

### 22.3 Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `orch.task.total` | Counter | tier, status |
| `orch.task.duration_ms` | Histogram | tier |
| `orch.step.total` | Counter | capability_type, status |
| `orch.step.duration_ms` | Histogram | capability_type |
| `orch.step.retries` | Counter | capability_type |
| `orch.step.schema_failures` | Counter | capability_type |
| `orch.step.quality_score` | Histogram | capability_type |
| `orch.dag.wave_count` | Histogram | plan_complexity |
| `orch.dag.parallel_steps` | Histogram | wave_number |
| `orch.dag.tokens_consumed` | Counter | plan_id |
| `orch.dag.micro_replans` | Counter | plan_id |
| `orch.dag.conditional_branches` | Counter | condition_result |
| `orch.workflow.runs` | Counter | workflow_id, trigger_type, status |
| `orch.circuit_breaker.state` | Gauge | cb_name, state |

---

## 22A. Adaptive Blind DAG -- Agent-Aware Extensions

The following six subsystems extend the Blind DAG Executor to handle the non-deterministic nature of LLM agent steps. These are deterministic, schema-driven mechanisms that require NO LLM in the Orchestrator -- they observe, validate, and route based on structured data. Together they transform the "Blind DAG" into an "Adaptive Blind DAG."

### 22A.1 Output Schema Guard (ORCH-15)

**Problem**: LLM agent results are non-deterministic. Step s1 might return `{"venue": "Olive Garden"}` on one run and `{"restaurant": "Olive Garden"}` on another. When step s4 uses `$s1.result.venue`, it gets `null` on run 2 -- silent data corruption in the DAG chain.

**Solution**: Every agent step in CommittedPlan declares `output_schema: JsonSchema`. The Orchestrator validates the result against the schema before allowing parameter reference resolution.

**Mechanism**:

```
1. Agent step completes with CapabilityResult.data
2. OutputSchemaGuard validates data against step.output_schema (JSON Schema)
3. PASS: proceed to parameter resolution
4. FAIL: retry with schema_hint injected into CapabilityRequest
   - Fabric passes schema_hint to agent prompt: "Your response MUST conform to: {schema}"
   - Max 1 schema retry (not counted against normal retry budget)
5. FAIL after retry: treat as hard failure (step FAILED, dependents CANCELLED)
```

**What sets output_schema**: The Planner (Stage 2 EXPAND) generates output_schema for each step based on downstream parameter references. If step s4 needs `$s1.result.venue`, Planner infers s1 must produce `{venue: string}`.

**Cost**: < 1ms per validation (JSON Schema validators are O(n) in field count). Zero LLM cost.

**Example**:

```yaml
# Planner generates this in CommittedPlan
step s1:
  capability: "agent.execute.restaurant_finder"
  output_schema:
    type: object
    required: [venue, address, confirmation_id]
    properties:
      venue: {type: string}
      address: {type: string}
      confirmation_id: {type: string}
```

### 22A.2 Conditional DAG Edges (ORCH-16)

**Problem**: Current DAG is static -- all edges unconditional. Every step either completes or gets cancelled. But real tasks branch: "Book restaurant. IF booked, send invites. IF booking failed, ask user for alternative."

**Solution**: Allow conditional dependencies in CommittedPlan. Conditions are deterministic boolean expressions evaluated on prior step results at wave boundaries.

**Syntax**:

```yaml
# Unconditional (existing)
s4: {deps: ["s1"]}  # s4 waits for s1, runs if s1 COMPLETED

# Conditional (new)
s4a: {deps: [{step: "s1", condition: "s1.status == COMPLETED"}]}    # success path
s4b: {deps: [{step: "s1", condition: "s1.status == FAILED"}]}        # failure path
s5:  {deps: [{step: "s3", condition: "s3.result.count > 5"}]}        # data-driven branch
```

**Condition language** (deterministic, no LLM):

```
<step_id>.status == COMPLETED | FAILED | CANCELLED
<step_id>.result.<path> == <literal>
<step_id>.result.<path> > <number>
<step_id>.result.<path> != null
AND | OR | NOT operators
```

**Evaluation**:

- Happens at wave boundary, BEFORE dispatching steps in the next wave
- Steps whose conditions evaluate to `false` are marked `SKIPPED` (not CANCELLED -- SKIPPED is intentional branching, CANCELLED is failure propagation)
- Topological sort still works: conditional edges are edges -- they just have a guard predicate
- DAG remains acyclic: Planner Stage 3 VALIDATE checks this with conditions flattened

**Example** (restaurant booking with fallback):

```yaml
steps:
  s1: {capability: "tool.execute.restaurant_booking", deps: []}
  s2: {capability: "tool.execute.cake_order", deps: []}
  s3: {capability: "tool.read.k0_recall", deps: [], params: {query: "family contacts"}}
  s4a: {capability: "agent.execute.invitation_sender",
        deps: [{step: "s1", condition: "s1.status == COMPLETED"}, "s3"]}
  s4b: {capability: "agent.execute.alternative_suggester",
        deps: [{step: "s1", condition: "s1.status == FAILED"}]}

Wave 0: s1, s2, s3 (concurrent)
Wave 1: evaluate conditions
  s1 COMPLETED -> s4a active, s4b SKIPPED
  s1 FAILED    -> s4b active, s4a SKIPPED
```

### 22A.3 Mid-DAG Micro-Replan (ORCH-13)

**Problem**: LLM agents are generative -- they create new information, not just fetch it. Step s3 (recall family contacts) might discover "Mom has a peanut allergy." This should change s1 (restaurant booking) to a peanut-free restaurant, but s1 already ran in Wave 0. The plan is now invalidated by a discovery.

**Solution**: At wave boundaries, check for "discoveries" in agent results. If discoveries would invalidate remaining steps, checkpoint progress and ask Planner to adjust the remaining plan.

**Mechanism**:

```
1. After each wave completes, Orchestrator checks CapabilityResult.discoveries[]
2. Discovery = agent-reported new information (facts, constraints, corrections)
   Example: {type: "constraint", field: "dietary", value: "peanut_allergy", confidence: 0.95}
3. Orchestrator evaluates: do any discoveries affect remaining steps?
   - Simple heuristic: do discovery.field names overlap with remaining step param keys?
   - Zero LLM -- string matching on field names
4. If yes AND replan not already used (ORCH-13: max 1 per DAG):
   a. Checkpoint: save completed results + wave progress
   b. Send MicroReplanRequest to Planner (reduced timeout, remaining budget)
   c. Planner adjusts remaining steps only (keeps completed, modifies future)
   d. Orchestrator replaces remaining waves with updated plan
   e. Resume execution from checkpoint
5. If no: continue normally
6. If replan already used: log discovery, continue with original plan
```

**Guard rails**:

- **ORCH-13**: Max 1 micro-replan per DAG. Second discovery logged but not acted on.
- Micro-replan timeout: remaining time budget only (not fresh 45s)
- Planner receives completed step results as context (no re-executing finished work)
- If Planner micro-replan fails (timeout, error): continue with original plan

**Example**:

```
Wave 0: s1 (book restaurant), s2 (order cake), s3 (recall contacts)
  s3 result: {contacts: [...], discoveries: [{type: "dietary", value: "peanut_allergy"}]}

Orchestrator: "peanut_allergy" overlaps with s1.params.cuisine? No direct overlap.
              But s4 (invitation_sender) has override_message referencing venue...
              Heuristic: discovery.dietary + remaining step with restaurant -> flag it

MicroReplanRequest{
  checkpoint: {s1: COMPLETED, s2: COMPLETED, s3: COMPLETED},
  discoveries: [{type: "dietary", value: "peanut_allergy"}],
  remaining: [s4]
}

Planner adjusts: add s1b (change restaurant to peanut-free), update s4 to use $s1b.result
Updated plan resumes from Wave 1 with s1b -> s4
```

### 22A.4 DAG Token Budget Tracker (ORCH-14)

**Problem**: Each agent step has its own LLM budget (from AgentContract), but there is no aggregate tracking across the whole DAG. A 5-step agent plan could burn 200K+ tokens with no guardrail. On-device inference makes this an economics and latency issue.

**Solution**: Planner sets `plan.token_budget_max` in CommittedPlan. Orchestrator accumulates `tokens_consumed` from CapabilityResults and enforces the budget at wave boundaries.

**Mechanism**:

```
1. CommittedPlan.token_budget_max set by Planner (based on model, step count, complexity)
2. TokenBudgetTracker: cumulative counter, initialized to 0
3. After each step: tracker.add(result.tokens_consumed)
4. At each wave boundary:
   consumed / budget_max >= 0.80 -> WARN event + compress remaining step prompts
   consumed / budget_max >= 0.95 -> EXHAUSTED event + skip remaining optional steps
   consumed / budget_max >= 1.00 -> HARD STOP + aggregate what we have
5. "Optional steps" = steps not on the critical path (no downstream dependents)
6. AggregatedResult includes: total_tokens_consumed, budget_max, budget_utilization
```

**Cost**: O(1) per step (counter increment + threshold check). Zero overhead.

### 22A.5 Agent Sub-Step Observability Pass-Through

**Problem**: Current progress reporting shows "Step s1 started..." then silence for 10 seconds... then "Step s1 completed." But agent s1 internally executes multiple LLM calls and tool calls. User sees nothing during those 10 seconds.

**Solution**: Fabric emits sub-step deltas for agent executions. Orchestrator forwards these to DeltaBus for user-facing progress streaming. This is primarily a Fabric change, but Orchestrator needs to pass through the events.

**Fabric-emitted sub-step events** (new):

```
k1.fabric.agent.{step_id}.tool_call.started    -> "Searching restaurants..."
k1.fabric.agent.{step_id}.tool_call.completed   -> "Found 5 options"
k1.fabric.agent.{step_id}.llm_call.started      -> "Evaluating options..."
k1.fabric.agent.{step_id}.llm_call.streaming    -> partial token stream
k1.fabric.agent.{step_id}.iteration.completed   -> "Iteration 2 of 3 complete"
```

**Orchestrator role**:

- Subscribes to `k1.fabric.agent.*.{tool_call,llm_call,iteration}.*` events
- Forwards to DeltaBus -> Concierge PROGRESSING -> user output
- Sub-step events are **informational only**: Orchestrator does NOT act on them, does NOT change DAG execution based on sub-step progress
- Provides `step_id` context so Concierge can attribute progress to the right step

**User experience**:

```
"Planning your birthday party..."
  [Wave 0]
    "Booking restaurant..." -> "Searching options..." -> "Found 3 restaurants..." -> "Booked Olive Garden"
    "Ordering cake..." -> "Selected chocolate cake..." -> "Order placed"
    "Getting family contacts..." -> "Found 8 contacts"
  [Wave 1]
    "Sending invitations..." -> "Drafting invitation..." -> "Sent to 8 people"
"All done! Here's your party plan..."
```

### 22A.6 Quality Gate (Soft Failure Detection)

**Problem**: Tools return binary success/error. LLM agents can return a "technically successful but useless result": agent asked to "find a restaurant" returns "I found some restaurants" with no actual data. This passes through as success and corrupts downstream steps.

**Solution**: Add `quality_score: 0.0-1.0` to CapabilityResult. Fabric calculates this using deterministic heuristics (no LLM). Orchestrator uses the score to decide retry vs. proceed vs. soft-fail.

**Quality scoring** (Fabric-side, deterministic):

```
Score components:
1. Schema completeness: % of output_schema required fields populated (0.0-1.0)
2. Content density: response length vs expected length from contract (0.0-1.0)
3. Null field ratio: % of fields that are null or empty (penalty)

quality_score = 0.5 * schema_completeness + 0.3 * content_density + 0.2 * (1.0 - null_ratio)
```

**Orchestrator decision** (deterministic thresholds):

```
quality >= 0.7  -> PASS: proceed normally
0.3 <= quality < 0.7  -> RETRY: retry with quality hint
   ("Provide complete structured data for all required fields")
   Max 1 quality retry (not counted against normal retry budget)
quality < 0.3  -> SOFT FAIL: treat as FAILED for dependency purposes
   Dependents CANCELLED, independent steps CONTINUE
   quality_score=null for non-agent steps -> always PASS (bypass gate)
```

**Cost**: Quality scoring is O(n) in field count (Fabric-side). Orchestrator threshold check is O(1).

---

## 23. Superseded Decisions

### 23.1 ADR-0006: Contract-Net Protocol -- SUPERSEDED

**Original ADR-0006**: Defined a 3-Phase Orchestration protocol:

1. Task Announcement (broadcast available work)
2. Proposal Bidding (agents bid on tasks)
3. Multi-Criteria Scoring (select best bidder)

**Superseded because**: Fabric's Provider Resolution Engine handles all provider selection with its Policy Engine (QoS + affective + security + cognitive load routing). The Orchestrator does not need to negotiate or bid -- Fabric already picks the best provider.

**New Orchestrator role**: Pure DAG executor:

- Receives CommittedPlan from Planner (HIGH) or TaskEnvelope from Concierge (MEDIUM)
- Walks DAG in topological order
- Calls Fabric per step (Fabric handles provider selection)
- Aggregates results, emits deltas
- No negotiation, no bidding, no scoring

**Action**: ADR-0006 should be revised to describe the Orchestrator purely as a blind DAG executor. Reference this discussion and the whiteboard.

---

## 24. External Touchpoints Summary

### 24.1 Inbound (who sends TO Orchestrator)

| Source | Message | Channel | When |
|--------|---------|---------|------|
| Concierge DISPATCHING | TaskEnvelope | Orchestrator Mailbox | MEDIUM/HIGH tier |
| Planner | CommittedPlan (via k1.planner.plan.ready) | Orchestrator Mailbox | HIGH tier, after planning |
| Workflow Scheduler | WorkflowRunRequest | Orchestrator Mailbox | Cron/event trigger fires |
| Workflow Provider (Fabric) | Rehydrated sub-workflow plan | Orchestrator Mailbox | Cross-workflow trigger |

### 24.2 Outbound (who Orchestrator sends TO)

| Destination | Message | Channel | When |
|-------------|---------|---------|------|
| Planner | PlanRequest | Planner Mailbox | HIGH tier, request plan |
| Fabric | CapabilityRequest | Fabric Gateway | Per step execution |
| Fabric | SpawnRequest | Fabric Gateway | Agent step execution |
| Concierge COMPANIONING | Aggregated results | Direct | All steps complete |
| DeltaBus | Orchestration deltas | K1 Event Bus | Per step progress |
| Bridge | Memory writes | Bridge Client | Workflow audit records |

### 24.3 Reads (what Orchestrator reads FROM)

| Source | What | How |
|--------|------|-----|
| SessionState | beliefs, entities, persona, temporal | Multi-reader, lock-free (INV-04 compliant) |
| Workflow Registry | WorkflowSpec definitions | Direct read |
| Fabric Capability Registry | Capability existence checks | Via Constraint Resolution Engine |

---

## 25. Directory Structure

Current code layout at `k1/orchestrator/`:

```
k1/orchestrator/
  __init__.py
  connectors/
    __init__.py
  orchestration/
    __init__.py
    constraint_resolution_engine/
      __init__.py
  spawning/
    __init__.py
  workflows/
    __init__.py
```

### 25.1 Proposed expanded structure

```
k1/orchestrator/
  __init__.py
  actor.py                           # OrchestratorActor (core dispatch logic)
  mailbox.py                         # Orchestrator Mailbox (MPSC + WFQ)
  gateway.py                         # Fabric Gateway (bridge to Fabric)

  orchestration/
    __init__.py
    dag_executor.py                  # Adaptive Blind DAG Executor (topological walk)
    dag_engine.py                    # Wave construction, dependency resolution
    step_runner.py                   # Per-step execution with retry
    step_retry.py                    # Retry policy (2 retries, graceful failure)
    step_cancellation.py             # Dependent cancellation logic
    saga_recovery.py                 # Compensating transactions
    result_aggregator.py             # Collect step results into AggregatedResult
    param_resolver.py                # $step.result reference resolution
    output_schema_guard.py           # JSON Schema validation of agent results (ORCH-15)
    conditional_edge_evaluator.py    # Boolean condition evaluation at wave boundaries (ORCH-16)
    token_budget_tracker.py          # Cumulative LLM token spend tracking (ORCH-14)
    quality_gate.py                  # Soft failure detection from quality_score thresholds
    micro_replan_checkpoint.py       # Checkpoint + MicroReplanRequest builder (ORCH-13)
    discovery_detector.py            # Heuristic: do discoveries affect remaining steps?
    constraint_resolution_engine/
      __init__.py
      constraint_manager.py          # Oversees iterative validation
      iteration_controller.py        # Max 3 cycles
      constraint_graph.py            # Priority + dependency graph
      capability_resolver.py         # Fabric-aware constraint checks
      fallback_trigger.py            # HIL routing when stuck

  workflows/
    __init__.py
    workflow_registry.py             # Store + retrieve WorkflowSpec
    workflow_compiler.py             # Rehydrate frozen DAG
    workflow_scheduler.py            # Cron/event/manual trigger management
    workflow_supervisor.py           # Run Manifest + leases + guards
    cross_workflow_resolver.py       # workflow.run.* nesting
    workflow_depth_guard.py          # Max depth 3 + cycle detection
    workflow_version.py              # Version pointer management
    gap_detector.py                  # Schema drift + proactive gap detection

  connectors/
    __init__.py
    mcp_discovery.py                 # Auto-discover MCP server tools
    mcp_registrar.py                 # Register discovered tools in Fabric registry
    mcp_provider_factory.py          # Create capability handlers for MCP tools
    connector_sandbox.py             # Isolation + resource limits
    local_mcp.py                     # Local MCP server management
    remote_mcp.py                    # Remote MCP server management
    k0_proxy.py                      # K0 Connector Proxy (cloud-hosted)

  spawning/
    __init__.py
    # NOTE: Agent Factory lives in Fabric (L2.5), not Orchestrator
    # This module handles Orchestrator-side spawn requests only
    spawn_request_builder.py         # Build SpawnRequest from plan step
```

---

## 26. Open Questions for Design Sessions

| # | Question | Impact | Proposed Answer |
|---|----------|--------|-----------------|
| 1 | **Saga compensation ordering**: Should compensations run in strict reverse order, or can they run concurrently? | Affects rollback latency | Strict reverse (safest, deterministic) |
| 2 | **Workflow Scheduler persistence**: Where does the scheduler store trigger state (next fire time, last fire)? | Affects crash recovery | K1 SQLite LOCAL COLD (Edge-First: always available) |
| 3 | **MCP server health monitoring**: Active probing (heartbeat) or passive (track failures)? | Affects connector reliability | Passive (track failures via CB_MCP), switch to active for critical tools |
| 4 | **Context freshness for HIGH tier**: Re-read SessionState at each wave boundary, or trust initial snapshot? | Affects correctness vs latency | Re-read safety_band at wave boundary, trust rest |
| 5 | **Concurrent workflow runs**: Can the same workflow have multiple active runs? | Affects resource management | No (V1): single active run per workflow. Abort previous if trigger fires while running |
| 6 | **Sub-workflow parameter override**: How do parent step params merge with sub-workflow's own params? | Affects cross-workflow contract | Parent overrides take precedence, sub-workflow defaults fill gaps |
| 7 | **Orchestrator metering**: Should Orchestrator track per-step cost for budget enforcement? | Affects QoS integration | Yes: accumulate cost from CapabilityResult.cost_usd, abort if budget exceeded |
| 8 | **Discovery heuristic threshold**: How aggressively should discoveries trigger micro-replan? | Affects replan frequency vs missed corrections | Conservative (V1): discovery field must match remaining step param key exactly. Fuzzy matching in V2 |
| 9 | **Quality gate thresholds**: Should 0.3/0.7 be configurable per capability type? | Affects agent reliability | Yes (V1.5): quality thresholds in capability contract YAML. V1: hardcoded 0.3/0.7 |
| 10 | **Conditional edge complexity**: Should conditions support function calls (e.g., `len(s3.result.contacts) > 5`)? | Affects branching expressiveness | No (V1): simple comparisons only. Eval safety risk with arbitrary expressions |
| 11 | **Sub-step event volume**: How to prevent sub-step events from flooding DeltaBus? | Affects UX responsiveness | Rate limit: max 1 sub-step event per step per 500ms. Batch intermediate events |

---

## 27. Relationship to Other Components

### 27.1 Orchestrator <-> Concierge

- Concierge OWNS the Orchestrator lifecycle (created during session init)
- Concierge sends TaskEnvelope, receives aggregated results
- FabricOrchestratorAdapter is the port adapter on Concierge side
- Circuit breakers owned by the adapter (CB_ORCHESTRATOR, CB_PLANNER)
- Tier degradation: CB_ORCHESTRATOR open -> degrade to LOW (bypass Orchestrator)

### 27.2 Orchestrator <-> Planner

- Orchestrator sends PlanRequest, receives CommittedPlan
- One-shot: request plan, wait for plan, execute plan
- Planner failure: CB_PLANNER trips, degrade to MEDIUM (skip planning)
- No iterative communication (Planner handles its own HIL cycles)

### 27.3 Orchestrator <-> Fabric

- Orchestrator sends CapabilityRequest per step, receives CapabilityResult
- Fabric is stateless per-request: doesn't know or care about the DAG
- Each CapabilityRequest is independent from Fabric's perspective
- Orchestrator handles sequencing, Fabric handles execution

### 27.4 Orchestrator <-> SessionState

- Read-only via multi-reader lock-free interface
- Primary reads: beliefs_active (entities), temporal_context, safety_band
- Re-reads safety_band at wave boundaries for HIGH tier (freshness)
- NEVER writes (INV-04, ORCH-01)

### 27.5 Orchestrator <-> DeltaBus

- Emits orchestration deltas for progress tracking
- Deltas flow to Concierge FSM -> apply to SessionState (Single Writer)
- DeltaBus is fire-and-forget (RECOVERABLE if emit fails)

### 27.6 Orchestrator <-> Bridge (K0)

- Writes workflow audit records to K0 via Bridge Client
- Writes CommittedPlan to K0 WAL (crash recovery, done by Planner Stage 4)
- Fire-and-forget: Orchestrator continues even if K0 write fails (Edge-First)

---

## 28. Complete Event Catalog

All events emitted or consumed by the Orchestrator:

### 28.1 Events emitted

| Event | Topic | Payload | Notes |
|-------|-------|---------|-------|
| `k1.orchestration.task.accepted` | `k1.orchestration` | `{envelope_id, tier, intent}` | After mailbox dequeue |
| `k1.orchestration.plan.requested` | `k1.orchestration` | `{request_id, intent}` | HIGH tier only |
| `k1.orchestration.dag.started` | `k1.orchestration` | `{plan_id, wave_count, step_count, token_budget_max}` | DAG execution begins |
| `k1.orchestration.step.started` | `k1.orchestration` | `{step_id, capability, wave}` | Per step |
| `k1.orchestration.step.completed` | `k1.orchestration` | `{step_id, duration_ms, tokens_consumed, quality_score}` | Per step success |
| `k1.orchestration.step.failed` | `k1.orchestration` | `{step_id, error, retries}` | After all retries exhausted |
| `k1.orchestration.step.cancelled` | `k1.orchestration` | `{step_id, parent_step}` | Dependency cancellation |
| `k1.orchestration.step.skipped` | `k1.orchestration` | `{step_id, condition, reason}` | Conditional edge evaluated false (ORCH-16) |
| `k1.orchestration.step.retrying` | `k1.orchestration` | `{step_id, attempt, reason}` | Before retry attempt |
| `k1.orchestration.step.schema_retry` | `k1.orchestration` | `{step_id, schema, violations}` | Output schema guard retry (ORCH-15) |
| `k1.orchestration.step.quality_retry` | `k1.orchestration` | `{step_id, quality_score, threshold}` | Quality gate retry |
| `k1.orchestration.saga.compensating` | `k1.orchestration` | `{step_id, compensation}` | Saga compensation fired |
| `k1.orchestration.dag.micro_replan` | `k1.orchestration` | `{plan_id, checkpoint_wave, discoveries, remaining_steps}` | Micro-replan triggered (ORCH-13) |
| `k1.orchestration.dag.budget_warning` | `k1.orchestration` | `{plan_id, consumed, budget_max, utilization}` | Token budget >= 80% (ORCH-14) |
| `k1.orchestration.dag.budget_exhausted` | `k1.orchestration` | `{plan_id, consumed, budget_max}` | Token budget >= 95%, skipping optional steps |
| `k1.orchestration.dag.completed` | `k1.orchestration` | `{plan_id, completed, failed, cancelled, skipped, duration_ms, tokens_consumed}` | DAG done |
| `k1.orchestration.delta.v1` | `k1.orchestration.delta` | Generic delta payload | For DeltaBus aggregation |
| `k1.orchestration.workflow.triggered` | `k1.workflow` | `{workflow_id, run_id, trigger_type}` | Workflow execution started |
| `k1.orchestration.workflow.completed` | `k1.workflow` | `{workflow_id, run_id, status}` | Workflow execution done |

### 28.2 Events consumed

| Event | From | Action |
|-------|------|--------|
| `k1.planner.plan.ready` | Planner | Dequeue CommittedPlan, start DAG execution |
| `k1.planner.micro_replan.ready` | Planner | Receive adjusted plan after micro-replan (ORCH-13) |
| `k1.capability.completed.v1` | Fabric | Process CapabilityResult for step |
| `k1.capability.failed.v1` | Fabric | Process failure, trigger retry or cancel |
| `k1.capability.contract_updated.v1` | Fabric Registry | Trigger workflow gap detection |
| `k1.fabric.agent.*.tool_call.*` | Fabric | Forward sub-step progress to DeltaBus (pass-through) |
| `k1.fabric.agent.*.llm_call.*` | Fabric | Forward sub-step progress to DeltaBus (pass-through) |
| `k1.workflow.trigger.due` | Workflow Scheduler | Start workflow execution |
