# Fabric ↔ Orchestrator ↔ Planner — Cross-Reference & Gap Analysis

> Generated: 2026-04-12 · Companion docs: `15_orchestrator_api_mapping.md`, `15_planner_api_mapping.md`, `16_fabric_api_mapping.md`, `15_orchestrator_planner_cross_reference.md`

---

## 1. Interface Contracts: How Orchestrator & Planner Call Fabric

### 1.1 Orchestrator → Fabric (IFabricGatewayPort)

| Orch Method | Fabric Receives | Adapter | Translation |
|---|---|---|---|
| `execute(CapabilityRequest)` | `CapabilityFabric.execute(CapabilityRequest)` | `FabricGatewayAdapter` | **Pass-through** — both use `k1.fabric.types.CapabilityRequest` |
| `execute_batch(List[CapabilityRequest])` | `CapabilityFabric.execute_batch(requests, strategy)` | `FabricGatewayAdapter` | Pass-through. Orch doesn't use in V1 |
| `query_registry(name)` | `CapabilityRegistryAPI.lookup(name)` | `FabricGatewayAdapter._contract_to_entry()` | **Lossy mapping**: `CapabilityContract` (26 fields) → `RegistryEntry` (6 fields) |
| `query_registry_by_category(prefix)` | `CapabilityRegistryAPI.list_all()` + filter | `FabricGatewayAdapter` | Adapter-side prefix filtering |

### 1.2 Planner → Fabric (IFabricRetrievalPort)

| Planner Method | Fabric Receives | Adapter | Translation |
|---|---|---|---|
| `discover_capabilities(domain, intent, safety_band, session_context, top_k)` | `FabricRetrieval.discover_capabilities(...)` | `FabricRetrievalAdapter` | Direct proxy. 50ms timeout, 1 retry |
| `find_relevant_prompts(intent, domain, safety_band, top_k)` | `FabricRetrieval.find_relevant_prompts(...)` | `FabricRetrievalAdapter` | Direct proxy. 50ms timeout, 1 retry |

### 1.3 Fabric → Orchestrator (Event Bus)

| Fabric Topic | Orch Handler | Payload | Status |
|---|---|---|---|
| `k1.capability.completed.v1` | (None — Orchestrator waits on sync return) | N/A | **Not subscribed** — Orch gets results from synchronous `execute()` call |
| `k1.capability.failed.v1` | (None — same reason) | N/A | **Not subscribed** |
| `k1.fabric.learning.signal.v1` | (None) | N/A | Learning layer consumer (future) |

**Observation:** Orchestrator↔Fabric is **fully synchronous**. Orchestrator calls `execute()` and awaits the `CapabilityResult`. Fabric events are for telemetry/learning, not for Orchestrator consumption.

### 1.4 Fabric → Planner (Event Bus)

| Fabric Topic | Planner Handler | Status |
|---|---|---|
| (None) | — | Planner does not subscribe to any Fabric events |

**Observation:** Planner↔Fabric is **request-response only** — Planner calls `discover_capabilities()` and gets `RetrievalResult` synchronously.

---

## 2. Shared Types — Contract Alignment

### 2.1 CapabilityRequest (k1.fabric.types)

**Used by both Orchestrator and Fabric. Single canonical type.**

| Field | Set By Orchestrator (StepRunner) | Read By Fabric | Status |
|---|---|---|---|
| `request_id` | ✅ auto uuid4() | ✅ tracking + events | ✅ |
| `capability_name` | ✅ from PlanStep.capability | ✅ registry lookup → Resolver | ✅ |
| `params` | ✅ from resolved_params (ParamResolver) | ✅ ContextBuilder → ExecutionContext | ✅ |
| `prompt_template` | ✅ from PlanStep.prompt_template | ✅ ContextBuilder → PromptSystem.resolve() | ✅ |
| `context_override` | ✅ `{"tools_granted": [...]}` if set | ✅ ContextBuilder merges into context | ✅ |
| `tier` | ✅ hardcoded `"HIGH"` | ✅ used in event payload | ✅ |
| `wfq_priority` | ✅ default `"INTERACTIVE"` | ✅ FabricDispatcher priority routing | ✅ |
| `safety_band` | ✅ from Concierge classification | ✅ PolicyEngine security gate | ✅ |
| `timeout_ms` | ✅ from PlanStep.timeout_ms or 30s default | ✅ asyncio.wait_for deadline | ✅ |
| `retry_count` | ❌ not set by Orch (default 0) | ✅ internal retry tracking | ✅ N/A |
| `caller` | ✅ `"orchestrator"` | ✅ event payload | ✅ |
| `caller_id` | ✅ step.id | ✅ event payload | ✅ |
| `trace_id` | ✅ from ProcessingContext | ✅ propagated to all port calls | ✅ |
| `session_id` | ✅ from TaskEnvelope.session_id | ✅ SessionStateReader + ContextBuilder | ✅ |
| `plan_id` | ✅ from CommittedPlan.plan_id | ✅ event payload | ✅ |
| `step_id` | ✅ step.id | ✅ event payload | ✅ |

**✅ ALIGNED** — All 16 fields produced by Orchestrator and consumed by Fabric correctly.

### 2.2 CapabilityResult (k1.fabric.types)

**Returned by Fabric, consumed by Orchestrator.**

| Field | Set By Fabric | Read By Orchestrator (StepRunner) | Status |
|---|---|---|---|
| `request_id` | ✅ from CapabilityRequest | ✅ correlation | ✅ |
| `trace_id` | ✅ from CapabilityRequest | ✅ propagated | ✅ |
| `success` | ✅ true/false | ✅ → StepResult.status (COMPLETED/FAILED) | ✅ |
| `data` | ✅ provider output (Optional[Dict]) | ✅ → StepResult.result.data | ✅ |
| `error` | ✅ ErrorInfo (Optional) | ✅ → StepResult.error_detail | ✅ |
| `provider_id` | ✅ from ResolvedProvider | ❌ Orch does not read | ✅ (telemetry) |
| `duration_ms` | ✅ measured | ✅ logged (not used for StepResult.duration_ms — Orch measures own) | ✅ |
| `retrieval_time_ms` | ✅ internal timing | ❌ Orch does not read | ✅ (telemetry) |
| `resolution_time_ms` | ✅ internal timing | ❌ Orch does not read | ✅ (telemetry) |
| `execution_time_ms` | ✅ internal timing | ❌ Orch does not read | ✅ (telemetry) |

**✅ ALIGNED** — Orchestrator reads the 5 fields it needs (request_id, trace_id, success, data, error). Remaining fields are observability-only.

### 2.3 RegistryEntry (k1.orchestrator.types) ← CapabilityContract (k1.fabric.types)

**Lossy mapping in FabricGatewayAdapter._contract_to_entry():**

| RegistryEntry Field | Source in CapabilityContract | Status |
|---|---|---|
| `name` | `contract.name` | ✅ |
| `provider_type` | `contract.provider_type` | ✅ |
| `safety_band_min` | `contract.safety_band_min` | ✅ |
| `availability` | `contract.availability` | ✅ |
| `estimated_duration_ms` | `contract.avg_latency_ms` | ✅ (mapped) |
| `compensation_capability` | `contract.compensation_capability` | **⚠ XREF-FAB-01** — this field may not exist on all contracts |

**20 contract fields dropped:** version, domain, description, capabilities, limitations, required_inputs, optional_inputs, required_context, optional_context, output, provider_id, provider_endpoint, cost_per_call, max_latency_ms, registered_at, last_updated, success_rate_30d, total_invocations_30d, ephemeral, session_scoped.

**Impact:** Orchestrator's ConstraintResolver has limited info for alternative capability selection. It cannot see `required_inputs`, `output`, `cost_per_call`, or `success_rate_30d`.

### 2.4 RetrievalResult (k1.fabric.types)

**Returned by Fabric retrieval, consumed by Planner.**

| Field | Set By Fabric | Read By Planner (ToolCallRouter) | Status |
|---|---|---|---|
| `capabilities` | ✅ `List[ScoredCapability]` | ✅ Passed to LLM as tool result | ✅ |
| `total_matched` | ✅ count | ✅ Included in tool result | ✅ |
| `query_latency_ms` | ✅ measured | ✅ Logged | ✅ |
| `query_intent` | ✅ echo of input | ❌ Not read | ✅ (telemetry) |
| `index_size` | ✅ FAISS index count | ❌ Not read | ✅ (telemetry) |
| `embedding_model` | ✅ model identifier | ❌ Not read | ✅ (telemetry) |

**✅ ALIGNED** — Planner reads the 3 fields it needs.

### 2.5 PlanStep Type Collision — CRITICAL

**Two different `PlanStep` types exist in the codebase:**

| Attribute | Fabric PlanStep (k1.fabric.types) | Orchestrator PlanStep (k1.orchestrator.types) |
|---|---|---|
| **Import** | `from k1.fabric.types import PlanStep` | `from k1.orchestrator.types import PlanStep` |
| **Field Count** | 6 | 14 |
| **Fields** | `id, capability, prompt_template, params, tools_granted, deps` | `id, capability, params, deps, prompt_template, tools_granted, output_schema, condition, is_optional, has_side_effects, compensation, timeout_ms, required_context, safety_band_min` |
| **Used By** | WorkflowContract, WorkflowProvider | Planner, DAGExecutor, StepRunner |
| **Where Defined** | `k1/fabric/types.py` | `k1/orchestrator/types.py` |

**Overlap:** First 6 fields are semantically equivalent. Orchestrator PlanStep is a **strict superset**.

**Risk:** If WorkflowProvider or Fabric internals import the wrong `PlanStep`, field access will fail silently (missing attributes return AttributeError at runtime).

---

## 3. Data Flow Trace — Full Execution Lifecycle

### 3.1 Orchestrator → Fabric Execution Path

```
Orchestrator                         Fabric
═══════════                          ══════

1. DAGExecutor runs wave of steps

2. Per step — StepRunner._build_request():
   PlanStep (14 fields, k1.orchestrator.types)
   → CapabilityRequest (16 fields, k1.fabric.types)

   capability_name = step.capability
   params = resolved_params (ParamResolver)
   prompt_template = step.prompt_template
   tier = "HIGH"
   caller = "orchestrator"
   caller_id = step.id
   trace_id = ctx.trace_id
   session_id = ctx.session_id
   plan_id = committed_plan.plan_id
   step_id = step.id
   timeout_ms = step.timeout_ms or 30s
   context_override = {tools_granted} if set
   safety_band = from Concierge

3. fabric_port.execute(request) ─────► Fabric._execute_impl()
                                        │
                                        ├─ STEP 1: emit invoked event
                                        ├─ STEP 2: Resolver 5-substep
                                        │   lookup contract → match providers
                                        │   → PolicyEngine score → select
                                        ├─ STEP 3: ContextBuilder 6-substep
                                        │   read SS sections → inject params
                                        │   → resolve prompt → budget compress
                                        │   → ExecutionContext
                                        ├─ STEP 4: ProviderFactory.create()
                                        │   → MCP/WASM/Bridge/Agent/WF/Conc
                                        ├─ STEP 5: CircuitBreaker.call()
                                        │   → provider.execute(request, ctx)
                                        │   → CapabilityResult
                                        ├─ STEP 6: OutputValidation 3-tier
                                        ├─ STEP 7: emit completed/failed
                                        ├─ STEP 8: update registry metrics
                                        └─ STEP 9: emit learning signal
                                        │
4. CapabilityResult ◄───────────────── return

5. StepRunner translates:
   result.success → StepResult.status
   result.data → StepResult.result
   result.error → StepResult.error_detail
```

### 3.2 Planner → Fabric Discovery Path

```
Planner                              Fabric
═══════                              ══════

1. SketchService or ExpandService
   makes LLM tool call: fabric_search

2. ToolCallRouter intercepts:
   tool_name = "fabric_search"
   args = {intent, domain, safety_band}

3. fabric_port.discover_capabilities( ─► FabricRetrieval.discover_capabilities()
     domain, intent, safety_band,       │
     session_context=None, top_k=10     ├─ Gather contracts
   )                                    ├─ Embed query (IEmbeddingPort)
                                        ├─ Hard filter (safety, availability)
                                        ├─ Soft rank (4 weights)
                                        └─ Top-K select
                                        │
4. RetrievalResult ◄─────────────────── return
   {capabilities, total_matched,
    query_latency_ms}

5. ToolCallRouter formats result
   as tool response to LLM

6. LLM uses capabilities list
   to generate PlanStep.capability
   references in the plan
```

### 3.3 Full Triangle — Task Lifecycle

```
                    Orchestrator
                   ╱            ╲
           PlanRequest     CapabilityRequest
          (k1.orch.types)  (k1.fabric.types)
                ╱                    ╲
               ▼                      ▼
           Planner ──────────────► Fabric
               fabric_search         ▲
           (IFabricRetrievalPort)    │
                                     │
           CommittedPlan ────────────┘
           (k1.orch.types,       Orch builds CapReqs
            event bus)            from PlanSteps
```

**Data Lineage:**

1. Orchestrator receives `TaskEnvelope` → sends `PlanRequest` to Planner
2. Planner calls Fabric's `discover_capabilities()` to learn what capabilities exist
3. Planner builds `PlanStep` entries referencing Fabric capabilities by name
4. Planner returns `CommittedPlan` (via event bus) to Orchestrator
5. Orchestrator's DAGExecutor converts each `PlanStep` → `CapabilityRequest`
6. Orchestrator calls Fabric's `execute()` per step → gets `CapabilityResult`

---

## 4. Cross-Component Event Matrix

### 4.1 Events Orchestrator Publishes That Fabric Consumes

| Topic | Orch Publisher | Fabric Consumer | Status |
|---|---|---|---|
| `k1.orchestration.step.execute.v1` | (Not published in V1 — Orch calls Fabric directly) | Fabric has handler wired | **⚠ XREF-FAB-02** — Event path exists in Fabric but Orch never publishes it |

### 4.2 Events Fabric Publishes That Orchestrator Consumes

| Topic | Fabric Publisher | Orch Consumer | Status |
|---|---|---|---|
| (None) | — | — | Orch uses sync calls only |

### 4.3 Events Fabric Publishes That Planner Consumes

| Topic | Fabric Publisher | Planner Consumer | Status |
|---|---|---|---|
| (None) | — | — | Planner uses sync calls only |

### 4.4 Cross-Component Event Summary

| Event Direction | Current Path | Event Bus Alternative | Status |
|---|---|---|---|
| Orch → Fabric (execute) | Direct sync call via IFabricGatewayPort | `step.execute.v1` event → Fabric handler | **Direct call used** (correct for sync) |
| Fabric → Orch (result) | Direct sync return (CapabilityResult) | `capability.completed.v1` / `failed.v1` | **Direct return used** (correct for sync) |
| Planner → Fabric (discover) | Direct sync call via IFabricRetrievalPort | `discovery.request.v1` event → Fabric handler | **Direct call used** (correct for sync) |
| Fabric → Planner (result) | Direct sync return (RetrievalResult) | N/A | **Direct return used** |

**Observation:** All three components correctly use **sync call** for request-response and **event bus** only for fire-and-forget notifications. Fabric's event subscription handlers (`step.execute.v1`, `discovery.request.v1`) are **defense-in-depth** for future decoupled deployment but unused in current wiring.

---

## 5. Gap Analysis — Integration Issues

### 5.1 CRITICAL

| ID | Issue | Components | Impact | Fix |
|---|---|---|---|---|
| **XREF-FAB-01** | `RegistryEntry.compensation_capability` assumes field exists on `CapabilityContract` | Orch ← Fabric | `_contract_to_entry()` may raise `AttributeError` if contract lacks this field. ConstraintResolver compensation lookup fails. | Add `getattr(contract, 'compensation_capability', None)` in adapter or add field with default to `CapabilityContract` |
| **XREF-FAB-02** | `NullSessionStateReaderAdapter` in shared Fabric → no session context during execution | Fabric ← Kernel | Fabric's ContextBuilder builds empty context. PolicyEngine Affective/Cognitive scoring always 0. Provider decisions are context-blind. | Wire per-session `SessionStateReaderAdapter` in Fabric factory, or pass session state via `CapabilityRequest.context_override` |
| **XREF-FAB-03** | `IEmbeddingPort` not wired in kernel S4 for shared Fabric | Planner → Fabric | `FabricRetrieval.discover_capabilities()` cannot embed queries. Falls back to empty/degraded results. Planner's `fabric_search` tool is non-functional. | Wire `IEmbeddingPort` adapter (MiniLM-L6 or equivalent) in `FabricFactory.create_shared()` |

### 5.2 MEDIUM

| ID | Issue | Components | Impact | Fix |
|---|---|---|---|---|
| **XREF-FAB-04** | Fabric `PlanStep` (6 fields) vs Orchestrator `PlanStep` (14 fields) — same name, different types | Fabric / Orch | Name collision across modules. Any cross-import or future unification risks silent attribute errors. WorkflowProvider uses Fabric PlanStep; DAGExecutor uses Orch PlanStep. | Rename Fabric PlanStep to `WorkflowStep` or `FabricPlanStep` to disambiguate |
| **XREF-FAB-05** | `RegistryEntry` only has 6 fields from 26-field `CapabilityContract` | Orch ← Fabric | Orchestrator ConstraintResolver cannot evaluate `required_inputs`, `output` schema, `cost_per_call`, or `success_rate_30d` when finding alternatives. Alternative selection is name-prefix only. | Extend RegistryEntry or add `query_registry_detail()` method that returns full contract |
| **XREF-FAB-06** | `WorkflowProvider` needs `IOrchestrator` — not wired in kernel S4 | Fabric ← Orch | Workflows cannot be executed through Fabric. WorkflowProvider guard will reject all workflow capability requests. | Wire Orchestrator reference into WorkflowProvider at S6+ (circular dep requires lazy injection) |
| **XREF-FAB-07** | `ConciergeProvider` needs `IConciergeRouter` — not wired | Fabric ← Concierge | Concierge-type capabilities cannot be executed through Fabric. | Wire Concierge router when Concierge component is integrated |
| **XREF-FAB-08** | Fabric dispatcher max 10 concurrent vs Orchestrator Semaphore(10) per wave | Orch + Fabric | Effective concurrency is min(10, 10) = 10. But Orch submits 10 steps simultaneously → Fabric dispatcher could hit 80% threshold and start shedding if other callers (Concierge) also submit. | Coordinate capacity: either increase Fabric concurrency or add Orch-side awareness of Fabric backpressure |
| **XREF-FAB-09** | Planner `FabricRetrievalAdapter` has 50ms timeout | Planner → Fabric | If retrieval pipeline (embed → filter → rank → select) exceeds 50ms, discovery returns empty. Planner generates plan without capability knowledge. No retry escalation beyond 1 attempt. | Increase timeout to 200ms or add degraded fallback (return cached/stale results) |

### 5.3 LOW

| ID | Issue | Components | Impact | Fix |
|---|---|---|---|---|
| **XREF-FAB-10** | Fabric event handler for `step.execute.v1` exists but Orch never publishes it | Orch → Fabric | Dead code in Fabric. No functional impact — Orch uses direct call. | Remove handler or document as future decoupled path |
| **XREF-FAB-11** | Fabric event handler for `discovery.request.v1` exists but Planner never publishes it | Planner → Fabric | Dead code in Fabric. No functional impact — Planner uses direct call. | Remove handler or document as future decoupled path |
| **XREF-FAB-12** | `mcp.tool.discovered.v1` emitted by Orch's MCPRegistrationBridge, consumed by Fabric's ProactiveGapDetector | Orch → Fabric | Only cross-component event in actual use. Works correctly — auto-registers discovered MCP tools into Fabric registry. | ✅ Working as designed |
| **XREF-FAB-13** | Fabric `CapabilityContract.compensation_capability` links back to Orchestrator's CompensationEngine | Fabric ← Orch | Compensation capability name must exist in Fabric registry. If Orchestrator requests compensation for a step, it calls `fabric.execute(compensation_cap)` — Fabric must have that capability registered. | Ensure compensation capabilities are registered at module load time |

---

## 6. Type Mapping Summary

### 6.1 Orchestrator → Fabric (Execution Path)

```
Orchestrator Types                    Fabric Types
══════════════════                    ════════════

TaskEnvelope
  │ (_dispatch_high)
  ▼
PlanRequest ──► Planner ──►
  CommittedPlan
    │
    ├─ PlanStep (14 fields)
    │   │ (StepRunner._build_request)
    │   ▼
    │  CapabilityRequest (16 fields) ──► same type (k1.fabric.types)
    │                                     │
    │                                     ▼
    │                                  ExecutionContext (internal)
    │                                     │
    │                                     ▼
    │                                  CapabilityResult ──► same type back
    │   (StepRunner.run)
    │   ▼
    ├─ StepResult
    │
    ▼
AggregatedResult
```

### 6.2 Planner → Fabric (Discovery Path)

```
Planner Types                         Fabric Types
═════════════                         ════════════

LLM tool call: fabric_search
  │ (ToolCallRouter)
  ▼
kwargs: {intent, domain,
         safety_band, top_k}
  │
  ▼
IFabricRetrievalPort                  FabricRetrieval
  .discover_capabilities() ──────────► .discover_capabilities()
                                        │
                                        ▼
                                      RetrievalResult ──► same type back
  │
  ▼
Tool response → LLM
  → SketchResult / ExpandedPlan
    → PlanStep.capability = "cap_name"
```

### 6.3 Orchestrator → Fabric (Registry Query Path)

```
Orchestrator Types                    Fabric Types
══════════════════                    ════════════

ConstraintResolver
  │
  ▼
IFabricGatewayPort                    CapabilityRegistryAPI
  .query_registry(name) ────────────► .lookup(name)
                                        │
                                        ▼
                                      CapabilityContract (26 fields)
                                        │ (_contract_to_entry)
                                        ▼
                                      RegistryEntry (6 fields) ◄── LOSSY
  │
  ▼
ConstraintResolver uses:
  .name, .provider_type,
  .safety_band_min, .availability,
  .compensation_capability
```

---

## 7. Compatibility Matrix

| Interface | Type Match | Serialization | Direction | Sync/Async | Verdict |
|---|---|---|---|---|---|
| `execute(CapabilityRequest)` | ✅ Same type (k1.fabric.types) | N/A (in-process) | Orch → Fabric | Sync call + await | **FUNCTIONAL** |
| `CapabilityResult` return | ✅ Same type (k1.fabric.types) | N/A (in-process) | Fabric → Orch | Sync return | **FUNCTIONAL** |
| `query_registry(name)` → RegistryEntry | ⚠ Lossy (26→6 fields) | N/A (in-process) | Orch → Fabric | Sync call | **FUNCTIONAL** (XREF-FAB-05 caveat) |
| `discover_capabilities()` → RetrievalResult | ✅ Same type (k1.fabric.types) | N/A (in-process) | Planner → Fabric | Sync call | **⚠ BROKEN** (XREF-FAB-03: no embedding port) |
| `mcp.tool.discovered.v1` event | ✅ Dict payload matches | JSON via EventBus | Orch → Fabric | Async event | **FUNCTIONAL** |
| PlanStep (Fabric) vs PlanStep (Orch) | ❌ Different types, same name | Separate modules | Cross-module | N/A | **⚠ NAME COLLISION** (XREF-FAB-04) |

---

## 8. Prior Cross-Reference Gap Interactions

### 8.1 Impact of Orch↔Planner Gaps on Fabric

| Prior Gap | Fabric Impact |
|---|---|
| **XREF-01** (`PlanStep.to_dict()` omits `safety_band_min`) | Fabric's PolicyEngine checks `CapabilityRequest.safety_band` (from Concierge, not from PlanStep). No direct impact on Fabric — but Orchestrator's pre-execution safety gate is weakened. |
| **XREF-02** (`PlannerStateAdapter(reader=None)`) | Planner sends `session_context=None` to `discover_capabilities()`. Fabric's retrieval hard filter cannot check input satisfiability against session state. Degraded retrieval quality. |
| **PLN-GAP-01** (Planner state_read always empty) | Compounds with XREF-FAB-02 — neither Planner NOR Fabric have session state. Both operate context-blind. |
| **PLN-GAP-05** (No CB on Planner's internal calls) | Planner's `FabricRetrievalAdapter` has no circuit breaker. If Fabric retrieval is slow/broken, Planner retries once then degrades silently. |

### 8.2 Compound Gaps — Session State Blindness

Three independent gaps create a **systemic session-state blindness**:

| Component | Gap | Effect |
|---|---|---|
| Orchestrator | `MockStateReadAdapter()` never replaced | Orch reads empty session state, sends empty snapshot to Planner |
| Planner | `PlannerStateAdapter(reader=None)` | Planner's `state_read` tool returns empty |
| Fabric | `NullSessionStateReaderAdapter` (shared mode) | Fabric ContextBuilder has no session context, PolicyEngine scoring is flat |

**Combined impact:** The entire Orch→Planner→Fabric pipeline operates without any session awareness. Plans are generated without knowing user state, capabilities are selected without affective/cognitive context, and output validation has no semantic grounding.

**Single fix point:** Wire real `ISessionStateReader` adapter (from SessionState module) into kernel bootstrap. Propagate to all three components:

1. Orchestrator S5: Replace `MockStateReadAdapter` with `StateReadAdapter(ssm)`
2. Planner S6: Replace `PlannerStateAdapter(reader=None)` with `PlannerStateAdapter(reader=ssm_reader)`
3. Fabric S4: Replace `create_shared()` with `create_with_ports(state_reader=ssm_reader, ...)`

---

## 9. Recommended Priority Fixes

### Before MS-4 Integration Testing

| Priority | ID | Fix | Effort | Components |
|---|---|---|---|---|
| P0 | **XREF-FAB-03** | Wire `IEmbeddingPort` in `FabricFactory.create_shared()` | MEDIUM | Fabric + Kernel bootstrap |
| P0 | **XREF-FAB-02** | Wire per-session `SessionStateReaderAdapter` or pass state via context_override | MEDIUM | Fabric + Kernel bootstrap |
| P0 | **XREF-01** (prior) | Fix `PlanStep.to_dict()` to include `safety_band_min` | LOW | Orchestrator types |

### Before MS-5 End-to-End Testing

| Priority | ID | Fix | Effort | Components |
|---|---|---|---|---|
| P1 | **XREF-FAB-01** | Guard `compensation_capability` with getattr in `_contract_to_entry()` | LOW | Fabric adapter |
| P1 | **XREF-FAB-04** | Rename Fabric `PlanStep` → `WorkflowStep` | LOW | Fabric types |
| P1 | **XREF-FAB-06** | Wire Orchestrator into WorkflowProvider (lazy injection) | MEDIUM | Fabric + Orch |
| P1 | **XREF-FAB-07** | Wire ConciergeRouter into ConciergeProvider | MEDIUM | Fabric + Concierge |
| P1 | **XREF-FAB-09** | Increase Planner FabricRetrieval timeout to 200ms | LOW | Planner adapter |

### Before Production

| Priority | ID | Fix | Effort | Components |
|---|---|---|---|---|
| P2 | **XREF-FAB-05** | Extend RegistryEntry or add `query_registry_detail()` | MEDIUM | Orch + Fabric |
| P2 | **XREF-FAB-08** | Coordinate concurrency limits across Orch + Fabric | LOW | Config |
| P2 | Compound session gap | Wire real SSM adapter into all three components | HIGH | Kernel bootstrap |

---

## 10. Port Wiring Status (Kernel Bootstrap)

### 10.1 Fabric Ports — What's Wired vs Missing

| Fabric Port | Adapter | Wired At | Status |
|---|---|---|---|
| `ISessionStateReader` | `NullSessionStateReaderAdapter` | S4 `create_shared()` | **⚠ NULL** — no session context |
| `IEventPort` | `EventPortProdAdapter(bus)` | S4 | ✅ Working |
| `IBridgePort` | `BridgeConnectionAdapter(bridge)` | S4 | ✅ Working |
| `IModelGatewayPort` | `ModelGatewayBridgeAdapter(model_hub)` | S4 | ✅ Working |
| `IPromptSystemPort` | `PromptSystemProdAdapter(prompts_dir)` | S4 | ✅ Working |
| `IDeltaBusPort` | `DeltaBusProdAdapter(bus)` | S4 | ✅ Working |
| `IEmbeddingPort` | (not passed) | S4 | **⚠ MISSING** — retrieval broken |
| `IMCPTransport` | `AutoDiscoveryMCPTransport` | S4 internal | ✅ Working |
| `IWASMRuntime` | `AutoDiscoveryWASMRuntime` | S4 internal | ✅ Working |

### 10.2 Cross-Component Wiring at Kernel Level

| Wire | From | To | Method | Stage |
|---|---|---|---|---|
| Orch → Fabric | `FabricGatewayAdapter(shared_fabric)` | Orch `_fabric_port` | Port injection | S5 |
| Planner → Fabric | `FabricRetrievalAdapter(shared_fabric.retrieval)` | Planner `fabric_port` | Port injection | S6 |
| Orch → Planner | `PlannerAdapter(planner.get_mailbox(), cb)` | Orch `_planner_port` | Hot-swap at S6b | S6b |
| Planner → Orch | Event bus (`plan.ready.v1` etc.) | Orch event handlers | Event subscription | S5 init |
| Orch → Fabric events | `mcp.tool.discovered.v1` | Fabric `ProactiveGapDetector` | Event subscription | S4 init |
