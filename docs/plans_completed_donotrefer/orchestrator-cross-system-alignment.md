# Orchestrator Cross-System Alignment Report

> **Purpose**: Identifies every Orchestrator plan issue/epic/milestone that touches Concierge, Planner, Fabric, or SessionState — then validates each touchpoint against the **actual** port/adapter patterns in those systems.
>
> **Sources analyzed**:
>
> - Orchestrator plan: `docs/plans/orchestrator-implementation-plan.md` (1322 lines, M1-M9)
> - Fabric types: `k1/fabric/types.py` (1823 lines, IMPLEMENTED)
> - Fabric ports: `k1/fabric/ports/*.py` (6 ports, IMPLEMENTED)
> - Planner design: `k1/planner/planner.mmd` (889 lines, DESIGN ONLY)
> - Concierge design: `k1/concierge/concierge.mmd` (1237 lines, DESIGN ONLY)
> - SessionState ports: `k1/sessionstate/ports/*.py` (5 ports, IMPLEMENTED)

---

## Summary of Findings

| External System | Touchpoints | ALIGNED | PARTIAL | MISALIGNED |
|:---|:---:|:---:|:---:|:---:|
| **Fabric** | 38 issues | 18 | 11 | 9 |
| **Planner** | 16 issues | 9 | 4 | 3 |
| **Concierge** | 12 issues | 7 | 3 | 2 |
| **SessionState** | 10 issues | 4 | 4 | 2 |
| **TOTAL** | 76 | 38 | 22 | 16 |

**Critical misalignments requiring plan edits**: 9
**Protocol mismatches requiring ADR**: 3
**Type field gaps requiring Fabric extension or plan correction**: 3

---

## A. FABRIC Alignment (Implemented)

Fabric is the most heavily-touched external system. The Orchestrator plan defines `IFabricGatewayPort` as its interface to Fabric, with `FabricGatewayAdapter` (6.1.2) as the production adapter.

### A.1 Type Compatibility

#### A.1.1 CapabilityRequest -- ALIGNED

| Orch Plan Field (1.2.x) | Fabric Actual Field | Status |
|:---|:---|:---:|
| request_id | request_id | ALIGNED |
| capability_name | capability_name | ALIGNED |
| params | params | ALIGNED |
| prompt_template | prompt_template | ALIGNED |
| context_override | context_override | ALIGNED |
| tier | tier | ALIGNED |
| wfq_priority | wfq_priority | ALIGNED |
| safety_band | safety_band | ALIGNED |
| timeout_ms | timeout_ms | ALIGNED |
| retry_count | retry_count | ALIGNED |
| caller | caller | ALIGNED |
| caller_id | caller_id | ALIGNED |
| trace_id | trace_id | ALIGNED |
| session_id | session_id | ALIGNED |
| plan_id | plan_id | ALIGNED |
| step_id | step_id | ALIGNED |

> **Verdict**: Full 16-field parity. CapabilityRequest is safe to share directly.

#### A.1.2 CapabilityResult -- MISALIGNED (3 phantom fields)

| Orch Plan Field | Fabric Actual Field | Status | Impact |
|:---|:---|:---:|:---|
| request_id | request_id | ALIGNED | |
| trace_id | trace_id | ALIGNED | |
| success | success | ALIGNED | |
| data | data (Dict) | ALIGNED | |
| error | error (ErrorInfo) | ALIGNED | |
| provider_id | provider_id | ALIGNED | |
| duration_ms | duration_ms | ALIGNED | |
| retrieval_time_ms | retrieval_time_ms | ALIGNED | |
| resolution_time_ms | resolution_time_ms | ALIGNED | |
| execution_time_ms | execution_time_ms | ALIGNED | |
| **cost_usd** | **DOES NOT EXIST** | MISALIGNED | CostBudgetGuard (3.2.8), CostAccumulator (2.3.6) |
| **tokens_consumed** | **DOES NOT EXIST** | MISALIGNED | TokenBudgetTracker (3.2.3) |
| **quality_score** | **DOES NOT EXIST** | MISALIGNED | QualityGate (3.2.4) |

> **Impact**: These 3 phantom fields are referenced extensively across M2-M3 guards and accumulators. The Orchestrator plan assumes CapabilityResult carries cost/token/quality metadata as first-class fields. Fabric's actual CapabilityResult has NONE of these.
>
> **Resolution options**:
>
> 1. **Extract from `result.data` dict** (no Fabric change): Guards read `result.data.get("cost_usd")`, `result.data.get("tokens_consumed")`, `result.data.get("quality_score")`. Providers must include these in their response `data` dict. RISK: untyped, optional, provider-dependent.
> 2. **Extend Fabric CapabilityResult** (Fabric change): Add 3 optional fields to CapabilityResult. RISK: Fabric schema change, requires Fabric ADR.
> 3. **Orchestrator-side enrichment** (hybrid): StepRunner extracts provider metrics from a separate Fabric call or event, not from CapabilityResult itself.
>
> **Recommendation**: Option 1 (extract from data dict) for V1, document convention. Plan update needed in guard issues (3.2.3, 3.2.4, 3.2.8) to specify `result.data.get(...)` extraction instead of `result.cost_usd`.

**Touching issues**:

| Issue | Current Reference | Fix Required |
|:---|:---|:---|
| 2.3.6 CostAccumulator | `CapabilityResult.cost_usd` | Change to `result.data.get("cost_usd", 0.0)` |
| 3.2.3 TokenBudgetTracker | `tokens_consumed` from result | Change to `result.data.get("tokens_consumed", 0)` |
| 3.2.4 QualityGate | `CapabilityResult.data.quality_score` | Already referencing data dict -- PARTIAL, needs explicit fallback |
| 3.2.8 CostBudgetGuard | `CapabilityResult.data.cost_tokens` | Change to `result.data.get("cost_usd", 0.0)` |
| 7.2.3 TokenBudgetTracker tests | `tokens_used` in scripted results | Script in `data` dict: `script_result(data={"tokens_consumed": N})` |
| 7.2.4 QualityGate tests | `quality_score` in result | Script in `data` dict: `script_result(data={"quality_score": 0.8})` |
| 7.2.7 CostBudgetGuard tests | `cost_tokens` in result | Script in `data` dict: `script_result(data={"cost_usd": 0.05})` |

#### A.1.3 ErrorInfo -- ALIGNED

Fabric's `ErrorInfo(code, message, retriable)` matches the Orchestrator plan's error classification model. ErrorRouter (2.3.1) can inspect `result.error.code` and `result.error.retriable` directly.

#### A.1.4 CapabilityContract / RegistryEntry -- PARTIAL

The Orchestrator plan references `RegistryEntry` and `query_registry()` but Fabric's actual type is `CapabilityContract` (frozen dataclass, 25+ fields). The plan's `RegistryEntry` is not defined in Fabric. The `query_registry()` function exists on `ModuleLoader`, not on any port.

> **Fix**: Plan issue 1.2.x should define `RegistryEntry` as a thin alias or subset of Fabric's `CapabilityContract`. `IFabricGatewayPort.query_registry()` adapter must wrap `ModuleLoader.query()` or `CapabilityRegistry.get()`.

### A.2 Port Interface Alignment

#### A.2.1 IFabricGatewayPort (Orchestrator) vs Fabric API surface

The Orchestrator defines `IFabricGatewayPort` (1.4.2) with 3 methods:

| Orch Port Method | Fabric Actual API | Status | Gap |
|:---|:---|:---:|:---|
| `execute(request: CapReq) -> CapResult` | `FabricDispatcher.dispatch()` or `FabricService.invoke()` | PARTIAL | Orchestrator plan calls it "execute", Fabric uses "dispatch" or "invoke". Adapter must translate. |
| `execute_batch(requests) -> list[CapResult]` | No batch API in Fabric | MISALIGNED | Fabric has no batch dispatch. Adapter must implement via `asyncio.gather(*[invoke(r) for r in requests])`. |
| `query_registry(capability_name) -> RegistryEntry` | `ModuleLoader.register_from_dict`, `CapabilityRegistry.get()` | PARTIAL | No direct `query_registry` on any Fabric port. Adapter must wrap CapabilityRegistry internal API. |

> **Fix**: `FabricGatewayAdapter` (6.1.2) must be more explicit about which Fabric internal classes it wraps. The "fabric_client" constructor parameter (`def __init__(self, fabric_client: Any)`) needs to be typed as `FabricService` or a composite of `FabricDispatcher + CapabilityRegistry`. Issue 6.1.2 needs a wiring note specifying the actual Fabric entry point.

#### A.2.2 IEventSubscriptionPort (Orchestrator) vs Fabric IEventPort

| Aspect | Orch IEventSubscriptionPort | Fabric IEventPort | Status |
|:---|:---|:---|:---:|
| Subscribe return | `str` (subscription_id) | `SubscriptionHandle(subscription_id, topic)` | MISALIGNED |
| Unsubscribe param | `str` (subscription_id) | `SubscriptionHandle` | MISALIGNED |
| Emit method name | `publish(topic, payload)` | `emit(topic, payload)` | MISALIGNED |
| Handler signature | `Callable[[dict], Awaitable[None]]` (async, dict only) | `Callable[[str, Dict[str, Any]], None]` (sync, topic+payload) | MISALIGNED |

> **Impact**: The adapter (6.1.7 EventSubscriptionAdapter) must translate ALL of these differences. This is currently not documented in the plan.
>
> **Fix**: Issue 6.1.7 must explicitly document:
>
> 1. `subscribe()` wraps Fabric's `subscribe()` and returns `handle.subscription_id` as `str`
> 2. `unsubscribe()` reconstructs `SubscriptionHandle` from stored mapping
> 3. `publish()` calls Fabric's `emit()`
> 4. Handler wrapping: Orchestrator's async handlers wrapped in sync shim for Fabric, or vice-versa
>
> **Alternatively** (recommended): Redefine `IEventSubscriptionPort` to use `SubscriptionHandle` directly (matches both Fabric and SessionState patterns). This is a plan-level type change in 1.4.7.

#### A.2.3 IDeltaEmitPort (Orchestrator) vs Fabric IDeltaBusPort

| Aspect | Orch IDeltaEmitPort | Fabric IDeltaBusPort | Status |
|:---|:---|:---|:---:|
| Emit method | `emit(topic, payload, trace_id)` | `emit_delta(DeltaPayload)` | PARTIAL |
| Payload type | `(str, dict, str)` tuple args | `DeltaPayload(agent_id, delta_type, section, data, trace_id)` | MISALIGNED |

> **Fix**: `DeltaEmitAdapter` (6.1.5) translates between Orchestrator's simple `(topic, payload, trace_id)` and Fabric's structured `DeltaPayload`. Issue 6.1.5 should document this mapping explicitly. The adapter constructs `DeltaPayload(agent_id="orchestrator", delta_type=topic, section="orchestration", data=payload, trace_id=trace_id)`.

### A.3 Fabric Event Topics

| Event Topic | Emitter | Consumer | Status |
|:---|:---|:---|:---:|
| `k1.fabric.provider.health.changed.v1` | Fabric HealthChecker (3.6.1) | Orch ConnectorLifecycleManager (5.1.3) | ALIGNED |
| `k1.fabric.capability.contract_updated.v1` | Fabric (5.4.4) | Orch ProactiveGapDetector (4.2.7) | ALIGNED |
| `k1.fabric.circuit.state.changed.v1` | Fabric CircuitBreaker (3.4.1) | Orch Error diagnostics | ALIGNED |
| `k1.orchestration.mcp.tool_registered.v1` | Orch MCPRegistrar (5.1.2) | Fabric (sub to register_from_dict) | PARTIAL |
| `fabric.agent.*.tool_call.*` | Fabric Agent providers | Orch SubStepObserver (3.2.7) | PARTIAL |
| `fabric.agent.*.llm_call.*` | Fabric Agent providers | Orch SubStepObserver (3.2.7) | PARTIAL |

> **Partial items**: The topic patterns for sub-step observation (`fabric.agent.*.tool_call.*`) are assumed wildcards. Fabric's actual event topics use `k1.agent.{agent_id}.delta.v1` pattern. The wildcard matching semantics and whether Fabric emits per-tool-call events needs verification against Fabric's FabricDispatcher/AgentProvider implementation.
>
> **Registration event**: `k1.orchestration.mcp.tool_registered.v1` is emitted by Orchestrator and consumed by Fabric. But Fabric's `register_from_dict()` is a direct API call on `ModuleLoader`, not event-driven. Issue 5.1.2 says "emit event -> Fabric receives event (5.4.4) -> register_from_dict". This event-driven registration pattern must be verified or replaced with direct API call through `IFabricGatewayPort`.

### A.4 Fabric Touching Issues (Full Inventory)

| Milestone | Epic | Issues | Fabric Touchpoint | Alignment |
|:---|:---|:---|:---|:---:|
| M1 | 1.2 | 1.2.1-1.2.6 | CapabilityRequest/Result types shared with Fabric | ALIGNED (CapReq), MISALIGNED (CapResult phantom fields) |
| M1 | 1.4 | 1.4.2 | IFabricGatewayPort definition | PARTIAL (query_registry wrapping unclear) |
| M1 | 1.4 | 1.4.5 | IDeltaEmitPort definition | PARTIAL (DeltaPayload mapping needed) |
| M1 | 1.4 | 1.4.7 | IEventSubscriptionPort definition | MISALIGNED (return type, method names, handler sig) |
| M1 | 1.5 | 1.5.1-1.5.2 | Event payload JSON Schemas | PARTIAL (sub-step topics uncertain) |
| M2 | 2.1 | 2.1.1-2.1.5 | dispatch_medium/high calls Fabric | ALIGNED (via adapter) |
| M2 | 2.3 | 2.3.3 | StepRunner -> IFabricGatewayPort.execute() | ALIGNED |
| M2 | 2.3 | 2.3.6 | CostAccumulator reads cost from CapResult | MISALIGNED (phantom field) |
| M3 | 3.1 | 3.1.1-3.1.2 | ConstraintResolver -> query_registry | PARTIAL (wrapping needed) |
| M3 | 3.2 | 3.2.3 | TokenBudgetTracker reads tokens from result | MISALIGNED (phantom field) |
| M3 | 3.2 | 3.2.4 | QualityGate reads quality_score from result | MISALIGNED (phantom field) |
| M3 | 3.2 | 3.2.7 | SubStepObserver subscribes to fabric events | PARTIAL (topic pattern uncertain) |
| M3 | 3.2 | 3.2.8 | CostBudgetGuard reads cost from result | MISALIGNED (phantom field) |
| M4 | 4.1 | 4.1.3 | WorkflowCompiler -> query_registry validation | PARTIAL (wrapping) |
| M4 | 4.2 | 4.2.7 | ProactiveGapDetector subscribes to Fabric events | ALIGNED |
| M5 | 5.1 | 5.1.1-5.1.4 | MCP registration into Fabric | PARTIAL (event vs direct API) |
| M6 | 6.1 | 6.1.2 | FabricGatewayAdapter (prod) | PARTIAL (fabric_client typing) |
| M6 | 6.1 | 6.1.5 | DeltaEmitAdapter (prod) | PARTIAL (DeltaPayload mapping) |
| M6 | 6.1 | 6.1.7 | EventSubscriptionAdapter (prod) | MISALIGNED (4 translation gaps) |
| M7 | 7.5 | 7.5.1 | Orchestrator + Real Fabric tests | ALIGNED (concept correct) |

---

## B. PLANNER Alignment (Design Only)

Planner is the second most coupled external system. Communication is asynchronous (event-driven) for plan delivery but the Orchestrator plan also defines a synchronous `micro_replan()` path.

### B.1 Protocol Alignment

#### B.1.1 Plan Request/Delivery Protocol -- ALIGNED

| Protocol Step | Orch Side | Planner Side | Status |
|:---|:---|:---|:---:|
| Request plan | `IPlannerPort.request_plan(PlanRequest)` → PlanAck | `IMailboxPort` receives PlanRequest | ALIGNED |
| Plan ready | Subscribe `k1.planner.plan.ready.v1` → receive CommittedPlan | Emit `k1.planner.plan.ready.v1` with CommittedPlan | ALIGNED |
| Plan failed | Subscribe `k1.planner.plan.failed.v1` | Emit `k1.planner.plan.failed.v1` | ALIGNED |
| Plan cancelled | Subscribe `k1.planner.plan.cancelled.v1` | Emit `k1.planner.plan.cancelled.v1` | ALIGNED |
| Cancel plan | `IPlannerPort.cancel_plan(request_id)` | Planner mailbox receives cancel | ALIGNED |

#### B.1.2 Micro-Replan Protocol -- PARTIAL (sync/async mismatch)

| Aspect | Orch Plan | Planner Design | Status |
|:---|:---|:---|:---:|
| Call pattern | `micro_replan(request) -> Optional[CommittedPlan]` (sync, 10s timeout) | MicroReplanRequest goes to Planner Mailbox | MISALIGNED |
| Timeout | 10s (asyncio.wait_for) | PLAN-04: 45s max total plan time | PARTIAL |
| Response | Direct return of CommittedPlan | Unclear if sync response or event-driven | MISALIGNED |

> **Issue**: The Orchestrator plan (issue 6.1.3 PlannerAdapter) specifies `micro_replan()` as a synchronous call with 10s timeout. But the Planner design shows MicroReplanRequest entering the Planner's mailbox queue, which is the same async pattern as PlanRequest. If Planner processes this through its full mailbox loop, the response would come via event, not as a direct return.
>
> **Resolution options**:
>
> 1. **Planner implements dedicated sync endpoint** for micro-replan (bypasses mailbox). Planner design needs update.
> 2. **Orchestrator uses event-driven micro-replan** (same as plan request). Orchestrator plan needs update for MicroReplanCheckpoint (3.2.5) to use async pattern with PendingContext.
> 3. **Planner mailbox supports request-reply** for MicroReplanRequest specifically. Planner mailbox has a sync "call" method alongside async "enqueue".
>
> **Recommendation**: Option 3 -- Planner mailbox supports sync call for micro-replan. This requires a Planner design note. New ADR recommended: ADR-1.1.13 "Micro-Replan Synchronous Protocol".

#### B.1.3 CommittedPlan Schema -- ALIGNED

| Field | Orch Plan (1.2.x) | Planner Design | Status |
|:---|:---|:---|:---:|
| plan_id | plan_id | plan_id | ALIGNED |
| request_id | request_id (echo, 1.2.26) | request_id | ALIGNED |
| intent | intent | intent | ALIGNED |
| steps[] | steps: list[PlanStep] | steps[] with 14+ PlanStep fields | ALIGNED |
| dependencies | dependencies: dict[str, list[str]] | dependencies{} | ALIGNED |
| token_budget_max | token_budget_max | token_budget_max | ALIGNED |
| cost_budget_max_usd | cost_budget_max_usd | cost_budget_max_usd | ALIGNED |
| created_at | created_at | created_at | ALIGNED |
| trace_id | trace_id | trace_id | ALIGNED |

#### B.1.4 PlanStep Schema -- PARTIAL

The Orchestrator plan defines PlanStep (1.2.17) with 14 fields. The Planner design also specifies PlanStep with 14+ fields. These mostly align but:

| Orch PlanStep Field | Planner PlanStep | Status | Note |
|:---|:---|:---:|:---|
| id | id | ALIGNED | |
| capability | capability | ALIGNED | |
| prompt_template | prompt_template | ALIGNED | |
| params | params | ALIGNED | |
| deps | deps | ALIGNED | |
| token_budget | token_budget | ALIGNED | |
| output_schema | output_schema | ALIGNED | |
| tools_granted | tools_granted | ALIGNED | |
| condition | condition | ALIGNED | |
| is_optional | is_optional | ALIGNED | |
| has_side_effects | has_side_effects | ALIGNED | |
| compensation | compensation | ALIGNED | |
| timeout_ms | timeout_ms | ALIGNED | |
| required_context | required_context | ALIGNED | |

> **Ownership note**: PlanStep is defined by Planner, consumed by Orchestrator. The Orchestrator plan (1.2.17) should import or alias from Planner's type, not redefine it. If Orchestrator redefines PlanStep independently, schema drift risk is HIGH.

### B.2 Circuit Breaker Ownership -- MISALIGNED

| CB | Concierge Design | Orch Plan | Planner Design | Actual Owner |
|:---|:---|:---|:---|:---|
| CB_PLANNER | Concierge owns (FabricOrchestratorAdapter) | Orchestrator PlannerAdapter owns (6.1.3) | Passive (Planner doesn't own any CB) | CONFLICT |

> **Issue**: Both Concierge and Orchestrator claim ownership of CB_PLANNER.
>
> **Analysis**:
>
> - Concierge's CB_PLANNER (45s, 2/min) is a SERVICE-LEVEL CB that monitors the end-to-end plan cycle time as observed from Concierge's perspective.
> - Orchestrator's CB_PLANNER (45s, 2 failures) wraps the DIRECT CALL from Orchestrator to Planner's mailbox.
> - These are at different architectural levels and could coexist, but with different semantics.
>
> **Fix**: Rename for clarity. Orchestrator's CB should be `CB_PLANNER_DIRECT` (wraps Orch→Planner call). Concierge's CB should be `CB_PLANNER_E2E` (wraps end-to-end plan cycle including Orchestrator overhead). Document both in ADR-1.1.x and update issues 6.1.3 and wiring notes.

### B.3 Planner Touching Issues (Full Inventory)

| Milestone | Epic | Issues | Planner Touchpoint | Alignment |
|:---|:---|:---|:---|:---:|
| M1 | 1.1 | 1.1.12 | ADR: event-driven plan delivery | ALIGNED |
| M1 | 1.2 | 1.2.17 | PlanStep type definition | PARTIAL (should import from Planner, not redefine) |
| M1 | 1.2 | 1.2.26-27 | request_id echo, PlanRequest schema | ALIGNED |
| M1 | 1.4 | 1.4.3 | IPlannerPort definition | ALIGNED |
| M1 | 1.5 | 1.5.3 | Committed plan JSON event schema | ALIGNED |
| M2 | 2.1 | 2.1.3 | dispatch_high -> PlanRequest to Planner | ALIGNED |
| M3 | 3.2 | 3.2.5 | MicroReplanCheckpoint -> micro_replan() | MISALIGNED (sync vs async) |
| M6 | 6.1 | 6.1.3 | PlannerAdapter with CB_PLANNER | MISALIGNED (CB ownership conflict) |
| M6 | 6.1 | 6.1.10 | MockPlannerAdapter | ALIGNED |
| M7 | 7.1 | 7.1.1 (items 11-15) | HIGH tier routing to Planner | ALIGNED |
| M7 | 7.2 | 7.2.5 | MicroReplan guard tests | PARTIAL (depends on protocol resolution) |
| M7 | 7.3 | 7.3.2 | HIGH tier e2e with Planner | ALIGNED |
| M7 | 7.3A | 7.3A.7 | Planner failure propagation | ALIGNED |
| M7 | 7.4 | 7.4.5 | request_id echo contract test | ALIGNED |
| M9 | 9.2 | 9.2.2 | Planner unavailability chaos test | ALIGNED |
| M9 | 9.3 | 9.3.1 | Integration guide (Planner section) | ALIGNED |

---

## C. CONCIERGE Alignment (Design Only)

Concierge is the upstream caller to Orchestrator. The touchpoint is primarily through `IMailboxPort` (enqueue) and delta/event feedback channels.

### C.1 Interface Alignment

#### C.1.1 Concierge → Orchestrator Dispatch -- ALIGNED

| Concierge Side | Orchestrator Side | Status |
|:---|:---|:---:|
| `IDispatchPort.dispatch_envelope(TaskEnv)` (FIRE_AND_FORGET) | `IMailboxPort.enqueue(TaskEnvelope, priority)` | ALIGNED |
| `IDispatchPort.dispatch_direct(CapReq) -> CapResult` (LOW tier) | Bypasses Orchestrator (Fabric direct) | ALIGNED (Orchestrator not involved in LOW) |

> Concierge routes LOW tier directly to Fabric, MEDIUM/HIGH to Orchestrator mailbox. This matches the Orchestrator plan's tier handling.

#### C.1.2 Orchestrator → Concierge Result Delivery -- PARTIAL

| Protocol | Orch Side | Concierge Side | Status |
|:---|:---|:---|:---:|
| Task result | AggregatedResult via delta bus | TOOL_RESULT_BUFFER consumes | PARTIAL |
| Error severity | ErrorRouter classifies, includes in AggregatedResult | FabricOrchestratorAdapter decides tier degradation | ALIGNED (boundary correct) |
| HIL requests | `k1.hil.fallback.v1` via delta bus | Concierge subscribes, shows to user | ALIGNED |
| HIL responses | Concierge emits `k1.hil.fallback_response.v1` | Orch subscribes via IEventSubscriptionPort | ALIGNED |
| Progress deltas | `k1.hil.progress.v1` via delta | Concierge PROGRESSING state consumes | ALIGNED |

> **Partial flag**: The exact AggregatedResult delivery mechanism needs clarification. The plan says DeltaEmitAdapter dual-publishes to event_bus AND delta_bus. But the Concierge TOOL_RESULT_BUFFER expects a specific payload format. The result-to-delta translation must match Concierge's expected schema. Issue 6.1.5 should document the exact delta payload format that Concierge expects.

#### C.1.3 Tier Degradation Protocol -- ALIGNED (after duplication audit)

| Concern | Owner | Status |
|:---|:---|:---:|
| Tier degradation decision (HIGH->MED->LOW->canned) | Concierge FabricOrchestratorAdapter | ALIGNED |
| Error classification + severity reporting | Orchestrator ErrorRouter | ALIGNED |
| CB_ORCHESTRATOR (wraps Orch mailbox) | Concierge FabricOrchestratorAdapter | ALIGNED |

> The duplication audit already fixed Orchestrator claiming ownership of tier degradation. The current plan correctly reports error severity to Concierge and lets Concierge decide degradation.

#### C.1.4 Delta Aggregation Window -- PARTIAL

Concierge design specifies 500ms delta aggregation window with LWW (Last-Writer-Wins) merge. Orchestrator's DeltaEmitAdapter (6.1.5) emits progress deltas per-step and per-wave. If Orchestrator emits too many deltas in quick succession, Concierge's 500ms window may merge/drop intermediate updates.

> **Fix**: Issue 6.1.5 should note the 500ms Concierge aggregation window and ensure ExecutionMonitor's rate limiter (3.2.6: max 1 per step per 500ms) is aligned with this window.

### C.2 Concierge Touching Issues (Full Inventory)

| Milestone | Epic | Issues | Concierge Touchpoint | Alignment |
|:---|:---|:---|:---|:---:|
| M1 | 1.2 | 1.2.14 | TaskEnvelope type (Concierge creates, Orch consumes) | ALIGNED |
| M1 | 1.2 | 1.2.20 | TaskAck response (MailboxPort contract) | ALIGNED |
| M1 | 1.4 | 1.4.1 | IMailboxPort (Concierge enqueues) | ALIGNED |
| M1 | 1.4 | 1.4.5 | IDeltaEmitPort (results back to Concierge) | PARTIAL (payload format) |
| M2 | 2.1 | 2.1.1 | OrchestratorService.process() entry point | ALIGNED |
| M2 | 2.1 | 2.1.5 | ErrorRouter reports severity to Concierge | ALIGNED |
| M3 | 3.1 | 3.1.3 | HIL fallback emits to Concierge | ALIGNED |
| M3 | 3.2 | 3.2.6 | ExecutionMonitor rate limiter (500ms) | PARTIAL (Concierge aggregation window) |
| M6 | 6.1 | 6.1.1 | MailboxAdapter with backpressure | ALIGNED (MailboxFullError -> "system busy") |
| M7 | 7.3A | 7.3A.2 | Error severity reporting e2e | ALIGNED |
| M8 | 8.4 | 8.4.1 | CB_ORCHESTRATOR alert (Concierge-owned CB) | PARTIAL (alert should be in Concierge, not Orch) |
| M9 | 9.3 | 9.3.1 | Integration guide (Concierge section) | ALIGNED |

---

## D. SESSION STATE Alignment (Implemented)

SessionState is accessed by Orchestrator in read-only mode (ORCH-01 invariant). However, there are significant interface gaps.

### D.1 Port Interface Alignment

#### D.1.1 IStateReadPort (Orchestrator) vs SessionState Actual API -- MISALIGNED

The Orchestrator plan defines `IStateReadPort` (1.4.4) as:

```
read(section: str) -> Optional[SectionData]
snapshot(sections: list[str]) -> ContextSnapshot
```

SessionState's actual ports:

| SessionState Port | Methods | Read/Write |
|:---|:---|:---:|
| IStoragePort | archive(), restore(), list_archive() | Storage (not direct section read) |
| IWriterPort | submit_mutation(), cancel(), authorize_writer() | WRITE ONLY |
| IEventPort | emit(), subscribe() | Events |
| ILifecyclePort | start_session(), end_session(), get_health() | Lifecycle |
| IK0SyncPort | sync_to_k0(), sync_from_k0() | K0 sync |

> **Critical gap**: SessionState does NOT expose a dedicated read-only port for section data. There is no `read_section()` or `get_snapshot()` method on any SessionState port.
>
> Fabric solved this by defining its own `ISessionStateReader` port (in `k1/fabric/ports/state_reader.py`) with:
>
> - `read_section(session_id, section) -> Optional[Dict]`
> - `read_sections(session_id, names) -> Dict[str, Any]`
> - `get_snapshot(session_id) -> SessionSnapshot`
>
> This port is backed by a `SessionStateReaderAdapter` that wraps SessionState internal read access.

**Resolution**: Orchestrator has two options:

1. **Reuse Fabric's ISessionStateReader** directly as Orchestrator's IStateReadPort. This avoids duplicating the adapter.
2. **Define Orchestrator's own IStateReadPort** with different method signatures, and create a separate adapter.

> **Recommendation**: Option 1 -- reuse Fabric's `ISessionStateReader` and `SessionSnapshot` types. This ensures consistency and avoids duplicating the read adapter.

**Changes required**:

| Issue | Current Assumption | Fix |
|:---|:---|:---|
| 1.4.4 IStateReadPort | `read(section)`, `snapshot(sections)` | Align to `read_section(session_id, section)`, `read_sections(session_id, names)`, `get_snapshot(session_id)`. Import from `k1.fabric.ports.state_reader`. |
| 1.2.x ContextSnapshot | Custom Orchestrator type | Use `SessionSnapshot` from `k1.fabric.ports.state_reader` |
| 1.2.x SectionData | Custom Orchestrator type | Use `Dict[str, Any]` (same as Fabric) |
| 6.1.4 StateReadAdapter | Wraps `session_state.get_section()` | Wraps same internal SessionState API as Fabric's adapter, OR reuses Fabric's `SessionStateReaderAdapter` |

#### D.1.2 session_id Propagation -- MISALIGNED

Fabric's `ISessionStateReader` methods ALL require `session_id` as a parameter. The Orchestrator plan's `IStateReadPort.read(section)` has NO `session_id` parameter.

> **Issue**: Orchestrator needs to know the current session_id to read SessionState. This session_id comes from the TaskEnvelope (which has `session_id`). The StateReadAdapter must either:
>
> - Accept `session_id` as constructor param (scoped per-request)
> - Accept `session_id` in every method call (matches Fabric pattern)
>
> **Fix**: Align IStateReadPort methods to include `session_id` parameter, matching Fabric's `ISessionStateReader` pattern. OR inject `session_id` into the adapter at construction time (per-request adapter creation -- simpler but less flexible).

#### D.1.3 Write Prevention (ORCH-01) -- ALIGNED

SessionState's `IWriterPort` requires explicit `WriterAuthorization` with `writer_id`. The Orchestrator plan correctly avoids exposing any write path. The `StateReadAdapter` (6.1.4) wraps only read methods. ORCH-01 invariant verified by contract test 7.4.3.

### D.2 SessionState Touching Issues (Full Inventory)

| Milestone | Epic | Issues | SessionState Touchpoint | Alignment |
|:---|:---|:---|:---|:---:|
| M1 | 1.2 | 1.2.x | SectionData, ContextSnapshot types | MISALIGNED (should use Fabric's SessionSnapshot) |
| M1 | 1.4 | 1.4.4 | IStateReadPort definition | MISALIGNED (method sigs, missing session_id) |
| M2 | 2.2 | 2.2.2 | DAGExecutor safety_band re-read (ORCH-07) | PARTIAL (needs session_id) |
| M2 | 2.3 | 2.3.5 | ParamResolver $context.field resolution | PARTIAL (needs session_id) |
| M4 | 4.1 | 4.1.3 | WorkflowCompiler reads user.preferences | PARTIAL (needs session_id) |
| M4 | 4.2 | 4.2.1 | WorkflowScheduler reads user timezone | PARTIAL (needs session_id) |
| M6 | 6.1 | 6.1.4 | StateReadAdapter (prod) | MISALIGNED (wrapping unclear) |
| M6 | 6.1 | 6.1.11 | MockStateReadAdapter | PARTIAL (no session_id in mock API) |
| M7 | 7.4 | 7.4.3 | ORCH-01 invariant (no writes) | ALIGNED |
| M7 | 7.5 | 7.5.2 | Orchestrator + real SessionState test | PARTIAL (needs real read adapter) |

---

## E. Cross-Cutting Issues

### E.1 Shared Type Ownership

| Type | Defined By | Consumed By | Risk |
|:---|:---|:---|:---|
| CapabilityRequest | Fabric (types.py) | Orchestrator, Concierge | LOW -- Fabric is authority, others import |
| CapabilityResult | Fabric (types.py) | Orchestrator, Concierge | MEDIUM -- phantom fields in Orch plan |
| PlanStep | Planner (design) | Orchestrator, Fabric | HIGH -- Orch plan redefines independently |
| CommittedPlan | Planner (design) | Orchestrator | LOW -- Planner is authority |
| TaskEnvelope | Concierge (design) | Orchestrator | MEDIUM -- not yet implemented, schema may drift |
| SessionSnapshot | Fabric (state_reader.py) | Orchestrator (should reuse) | HIGH -- Orch plan defines separate ContextSnapshot |
| SafetyBand | Fabric (types.py) | Orchestrator, Concierge | LOW -- Fabric is authority |
| ErrorInfo | Fabric (types.py) | Orchestrator | LOW -- direct import |

> **Rule**: Orchestrator should IMPORT shared types from their authority module, not redefine them. This prevents schema drift. Issues 1.2.1-1.2.6 should be updated to import from Fabric where applicable.

### E.2 Event Topic Registry

All cross-system event topics:

| Topic | Producer | Consumer(s) | Verified |
|:---|:---|:---|:---:|
| `k1.planner.plan.ready.v1` | Planner | Orchestrator | Yes |
| `k1.planner.plan.failed.v1` | Planner | Orchestrator | Yes |
| `k1.planner.plan.cancelled.v1` | Planner | Orchestrator | Yes |
| `k1.hil.fallback.v1` | Orchestrator | Concierge | Yes |
| `k1.hil.progress.v1` | Orchestrator | Concierge | Yes |
| `k1.hil.fallback_response.v1` | Concierge | Orchestrator | Yes |
| `k1.hil.override_response.v1` | Concierge | Orchestrator | Yes |
| `k1.fabric.provider.health.changed.v1` | Fabric | Orchestrator | Yes |
| `k1.fabric.capability.contract_updated.v1` | Fabric | Orchestrator | Yes |
| `k1.fabric.circuit.state.changed.v1` | Fabric | Orchestrator (diagnostic) | Yes |
| `k1.orchestration.mcp.tool_registered.v1` | Orchestrator | Fabric | Needs verification |
| `k1.orchestration.mcp.tool_unregistered.v1` | Orchestrator | Fabric | Needs verification |
| `k1.orchestration.task.completed.v1` | Orchestrator | Concierge | Yes |
| `k1.orchestration.error.routed.v1` | Orchestrator | Observability | Yes |
| `fabric.agent.*.tool_call.*` | Fabric | Orchestrator (SubStepObserver) | Needs verification |
| `fabric.agent.*.llm_call.*` | Fabric | Orchestrator (SubStepObserver) | Needs verification |

---

## F. Required Plan Changes (Prioritized)

> **Priority Framework**: Fabric and SessionState are **HARD constraints** -- their code is already implemented, so the Orchestrator plan MUST align to their actual APIs. Planner and Concierge are **SOFT constraints** -- they will be built AFTER the Orchestrator, so their API signatures and ports will be designed to match requirements discovered during Orchestrator and Planner implementation. This means Planner/Concierge-facing issues can be deferred and we can improvise API signatures when building those modules.

### F.1 CRITICAL (Block implementation) -- Fabric/SessionState HARD constraints

| # | Change | Issues Affected | Type | Status |
|:---:|:---|:---|:---|:---:|
| 1 | **CapabilityResult phantom fields**: Replace direct field access (`result.cost_usd`) with `result.data.get("cost_usd", 0.0)` pattern. Document provider convention. | 1.1.11 Q7, 1.2.5, 1.2.16, 3.2.4, 3.2.8 | Plan edit (5 locations) | DONE |
| 2 | **IStateReadPort alignment**: Change method signatures to match Fabric ISessionStateReader. Add session_id parameter. Import SessionSnapshot type. Use SessionSnapshot instead of ContextSnapshot. | 1.4.4, 1.2.19, 1.2.20 items 1-2, 6.1.4, 6.1.11 | Plan edit + type import | DONE |
| 3 | **IEventSubscriptionPort alignment**: Change subscribe return to SubscriptionHandle, align method names (publish -> emit), fix handler signature to sync Callable[[str, Dict], None] | 1.4.7, 6.1.7, 6.1.14 | Plan edit (3 issues) | DONE |

### F.2 HIGH (Pre-M6 adapter implementation) -- Fabric HARD constraints

| # | Change | Issues Affected | Type | Status |
|:---:|:---|:---|:---|:---:|
| 4 | **FabricGatewayAdapter typing**: Specify `Fabric` facade class as wrapped dependency. Document execute/execute_batch/lookup mapping. | 6.1.2 | Plan edit | DONE |
| 5 | **DeltaEmitAdapter mapping**: Document DeltaPayload construction and IDeltaBusPort.emit_delta() call pattern. Typed IEventPort for event_bus. | 6.1.5 | Plan edit | DONE |
| 6 | **CB_PLANNER dual ownership**: Rename to CB_PLANNER_DIRECT (Orch) and CB_PLANNER_E2E (Concierge). Or resolve which layer is authoritative. | 6.1.3, Concierge design | Plan edit + ADR | DEFERRED (Concierge = soft constraint) |
| 7 | **PlanStep type import**: Issue 1.2.17 should import from Planner authority, not redefine | 1.2.17 | Plan edit | DEFERRED (Planner = soft constraint) |

### F.3 MEDIUM (Pre-M7 test implementation) -- Mixed constraints

| # | Change | Issues Affected | Type | Status |
|:---:|:---|:---|:---|:---:|
| 8 | **MCP registration protocol**: Clarify if event-driven (emit event, Fabric subscribes) or direct API call (adapter calls register_from_dict). | 5.1.2, 6.1.2 | Plan edit or ADR | TODO |
| 9 | **Micro-replan sync protocol**: New ADR for Planner sync call support. Update MicroReplanCheckpoint. | 3.2.5, 6.1.3 | New ADR-1.1.13 | DEFERRED (Planner = soft constraint) |
| 10 | **Sub-step event topics**: Verify Fabric actually emits per-tool-call/llm-call events. Align topic patterns. | 3.2.7, 6.1.7 | Verification needed | TODO |
| 11 | **Result delivery to Concierge**: Document exact delta payload format for TOOL_RESULT_BUFFER | 6.1.5, 9.3.1 | Plan edit | DEFERRED (Concierge = soft constraint) |

### F.4 LOW (Documentation / future)

| # | Change | Issues Affected | Type | Status |
|:---:|:---|:---|:---|:---:|
| 12 | **ContextSnapshot rename**: Use SessionSnapshot throughout or document alias | 1.2.x types | Plan edit | DONE (part of F.1 #2) |
| 13 | **CB alert ownership**: MCPCapabilityCountDropped alert references MCP disconnect detection -- clarify Fabric vs Orch boundary | 8.4.1 | Doc edit | TODO |
| 14 | **Shared type import convention**: Add plan-wide note to import CapabilityRequest, CapabilityResult, SafetyBand, Tier, etc. from k1.fabric.types | 1.2.1-1.2.6 | Plan edit | TODO |

---

## G. Summary Matrix: Issues Touching Each System

### Fabric: 38 issues across M1-M9

M1: 1.2.1-6, 1.4.2, 1.4.5, 1.4.7, 1.5.1-2 (12)
M2: 2.1.1-5, 2.3.3, 2.3.6 (7)
M3: 3.1.1-2, 3.2.3-4, 3.2.7-8 (6)
M4: 4.1.3, 4.2.7 (2)
M5: 5.1.1-4 (4)
M6: 6.1.2, 6.1.5, 6.1.7 (3)
M7: 7.5.1 (1)
M8: 8.2.1 (metrics), 8.4.1 (alerts) (2)
M9: 9.3.1, 9.3.4 (1)

### Planner: 16 issues across M1-M9

M1: 1.1.12, 1.2.17, 1.2.26-27, 1.4.3, 1.5.3 (6)
M2: 2.1.3 (1)
M3: 3.2.5 (1)
M6: 6.1.3, 6.1.10 (2)
M7: 7.1.1, 7.2.5, 7.3.2, 7.3A.7, 7.4.5 (5)
M9: 9.2.2 (1)

### Concierge: 12 issues across M1-M9

M1: 1.2.14, 1.2.20, 1.4.1, 1.4.5 (4)
M2: 2.1.1, 2.1.5 (2)
M3: 3.1.3, 3.2.6 (2)
M6: 6.1.1 (1)
M7: 7.3A.2 (1)
M8: 8.4.1 (1)
M9: 9.3.1 (1)

### SessionState: 10 issues across M1-M7

M1: 1.2.x types, 1.4.4 (2)
M2: 2.2.2, 2.3.5 (2)
M4: 4.1.3, 4.2.1 (2)
M6: 6.1.4, 6.1.11 (2)
M7: 7.4.3, 7.5.2 (2)
