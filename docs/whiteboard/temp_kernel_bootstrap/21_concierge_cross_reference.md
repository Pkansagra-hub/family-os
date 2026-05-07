# Concierge ↔ Fabric ↔ Orchestrator ↔ Planner ↔ SessionState — Cross-Reference & Gap Analysis

> Generated: 2026-04-12 · Companion docs: `20_concierge_api_mapping.md`, `18_sessionstate_api_mapping.md`, `16_fabric_api_mapping.md`, `15_orchestrator_api_mapping.md`, `15_planner_api_mapping.md`, `17_fabric_orchestrator_planner_cross_reference.md`, `19_sessionstate_cross_reference.md`

---

## 1. Concierge Integration Topology

Concierge is the **central orchestration nexus** of K1. It is the sole user-facing component and the primary writer to SessionState. All task execution flows through Concierge's FSM, which routes to Fabric (LOW), OrchestratorStub (MEDIUM), or the full Orchestrator+Planner pipeline (HIGH, interface-only).

```text
                    ┌─────────────┐
                    │   User      │
                    └──────┬──────┘
                           │ IInputPort (BusInputAdapter)
                           ▼
                    ┌─────────────────────────────────────────────────┐
                    │                  CONCIERGE                      │
                    │                                                 │
                    │  ┌──────────┐    ┌────────────┐    ┌────────┐  │
                    │  │ Phase1   │───►│    FSM      │───►│ Front  │  │
                    │  │ Pipeline │    │ Controller  │    │ Actor  │  │
                    │  └──────────┘    └─────┬──────┘    └───┬────┘  │
                    │                        │               │       │
                    │              ┌─────────┼───────────┐   │       │
                    │              ▼         ▼           ▼   │       │
                    │         ┌────────┐ ┌───────┐ ┌──────┐ │       │
                    │         │  Back  │ │ HITL  │ │Weave │ │       │
                    │         │ Actor  │ │ Coord │ │Batch │ │       │
                    │         └───┬────┘ └───────┘ └──────┘ │       │
                    │             │                          │       │
                    └─────────────┼──────────────────────────┼───────┘
                                  │                          │
                 IDispatchPort    │    IStatePort    IMemoryPort  ILLMPort
                 (dispatch_direct)│    (get_section)  (recall)   (execute)
                                  │         │           │           │
                    ┌─────────────┼─────────┼───────────┼───────────┼────┐
                    │             ▼         ▼           ▼           ▼    │
                    │         ┌───────┐ ┌───────┐ ┌──────────┐ ┌──────┐ │
                    │         │Fabric │ │Session│ │K0 Memory │ │Model │ │
                    │         │       │ │ State │ │(Bridge)  │ │ Hub  │ │
                    │         └───┬───┘ └───────┘ └──────────┘ └──────┘ │
                    │  dispatch_  │                                      │
                    │  envelope   │   ┌──────────────┐                  │
                    │             └──►│ Orchestrator  │                  │
                    │                 │ (Stub/Full)   │                  │
                    │                 └───────┬───────┘                  │
                    │                         │                         │
                    │                    ┌────┴────┐                    │
                    │                    │ Planner │ (HIGH only,        │
                    │                    │         │  interface-only)   │
                    │                    └─────────┘                    │
                    └───────────────────────────────────────────────────┘
```

---

## 2. Concierge → SessionState

### 2.1 Write Path (Concierge is SOLE WRITER)

All SS mutations flow through Concierge's Front actor cognitive tools → IWriterPort → SessionStateManager.

| Source | Tool / Mechanism | SS Section | Operation | Frequency |
| --- | --- | --- | --- | --- |
| Front: `update_beliefs` | cognitive tool | `beliefs_active` | `add_fact` | Per extracted SVO fact |
| Front: `update_scoreboard` | cognitive tool | `scoreboard` | `push_question` / `push_topic` | Per discourse update |
| Front: `update_clarifications` | cognitive tool | `clarifications` | `push_question` | On ambiguity |
| Front: `update_narrative` | cognitive tool | `narrative_active` | `create_thread` / `update_thread` | On topic shift |
| Front: `refine_affect` | cognitive tool | `affective_now` | `set` | Every turn |
| Front: `promote_belief` | cognitive tool | `beliefs_active` | `update_confidence` | On evidence |
| Front: `update_session_bundle` | bundle tool | Multiple (beliefs + scoreboard + narrative + affect) | Batch | Every turn |
| FSM: turn lifecycle | Direct via IStatePort | `control` | `set` | Every turn |
| FSM: task routing | Direct via IStatePort | `task_state` | `set` | On task create/update |
| FSM: session meta | Direct via IStatePort | `meta` | `update` | Session events |
| Front: telemetry | Direct | `telemetry` | `record_turn` | Every turn |
| Front: history | HistoryWriter | `history_active` | `add_turn` | Every turn |
| Front: task artifacts | Direct | `task_artifacts` | `append` | On task complete |

### 2.2 Read Path

| Reader | Adapter | Sections Read | Purpose |
| --- | --- | --- | --- |
| Front Actor | `SSMStateAdapter.get_snapshot()` | ALL HOT + WARM | Prompt assembly (beliefs, history, scoreboard, narrative, affect, tasks, clarifications) |
| Front Actor | `SSMStateAdapter.get_section(name)` | Individual sections | Specific context for PromptMode-driven section selection |
| Back Actor | `SSMStateAdapter.get_snapshot()` | ALL (read ONCE at start) | Snapshot-at-start contract — Back reads SS once, works from snapshot |
| FSM Controller | `SSMStateAdapter.get_section("control")` | `control` | FSM state decisions, intent routing |
| FSM Controller | `SSMStateAdapter.get_section("task_state")` | `task_state` | Task lifecycle management |
| OrchestratorStub | `_StateReadAdapter.snapshot(["beliefs_active", "task_artifacts"])` | `beliefs_active`, `task_artifacts` | Context for Fabric capability execution |

### 2.3 Type Translation (Concierge → SS)

| Concierge Type | SS Operation | SS Data Shape |
| --- | --- | --- |
| Front cognitive tool args (dict) | `mutate(section, op, data)` | `MutationRequest` → `MutationResponse` |
| TaskDispatch (task routing) | `mutate("task_state", "set", task_dict)` | Task state dict |
| Phase1Result | `mutate("control", "set", control_dict)` | Control dict (intent, domain, safety_band) |
| Turn metrics | `mutate("telemetry", "record_turn", metrics)` | Telemetry dict |

### 2.4 Cross-Reference with SS API Mapping (doc 18)

| SS Writer Port Method | Concierge Caller | Verified |
| --- | --- | --- |
| `request_mutation(MutationRequest)` | Front cognitive tools via DirectWriterAdapter | ✅ |
| `batch_mutations(BatchRequest)` | Front `update_session_bundle` tool | ✅ |
| `validate_writer(writer_id)` | Pre-check (optional) | ✅ |

| SS Read Method | Concierge Adapter | Verified |
| --- | --- | --- |
| `get_section(name)` | SSMStateAdapter (wraps SSM) | ✅ |
| `get_snapshot()` | SSMStateAdapter.get_snapshot() | ✅ |

---

## 3. Concierge → Fabric

### 3.1 Direct Dispatch (Back Actor Tools → Fabric)

Back actor tools call Fabric via `IDispatchPort.dispatch_direct()` which maps to `FabricDispatchAdapter → IFabricPort.execute()`.

| Back Tool | Fabric Method | Input Type | Output Type |
| --- | --- | --- | --- |
| `invoke_capability` | `execute(CapabilityRequest)` | K1 `CapabilityRequest` (16 fields) | K1 `CapabilityResult` |
| `batch_invoke` | `execute(CapabilityRequest)` × N | K1 `CapabilityRequest` × N | K1 `CapabilityResult` × N |
| `spawn_via_fabric` | `execute(CapabilityRequest)` (spawn type) | K1 `CapabilityRequest` | K1 `CapabilityResult` |
| `execute_workflow` | `execute(CapabilityRequest)` (workflow type) | K1 `CapabilityRequest` | K1 `CapabilityResult` |
| `discover_capabilities` | `discover_capabilities(domain, intent, ...)` | Domain + intent strings | `RetrievalResult` |

### 3.2 POC Fabric (Inside Concierge)

Concierge has its own POC Fabric (`k1/concierge/fabric/`) with:

| Component | Purpose | Capability Count |
| --- | --- | --- |
| `CapabilityRegistry` | Local capability registration | 40 capabilities |
| Demo capabilities | Demo/testing | 7 |
| Family capabilities | Family domain | 31 |
| Web capabilities | Web integration | 2 |
| `POCMockBridgeAdapter` | IBridgePort mock for testing | — |
| `contract_converter` | Convert POC contracts → K1 contracts | — |

### 3.3 Cross-Reference with Fabric API Mapping (doc 16)

| Fabric Entry Point | Concierge Caller | Path | Verified |
| --- | --- | --- | --- |
| `execute(CapabilityRequest)` | Back tools via FabricDispatchAdapter.dispatch_direct() | Direct | ✅ |
| `execute_batch(requests, strategy)` | Back batch_invoke tool | Via adapter | ✅ |
| `discover_capabilities(domain, intent, ...)` | Back discover_capabilities tool | Via adapter | ✅ |
| `lookup(capability_name)` | Not directly — via OrchestratorStub context | Indirect | ✅ |
| Event: `k1.orchestration.step.execute.v1` | Not used by Concierge directly | OrchestratorStub handles internally | N/A |

### 3.4 Type Translation (Concierge → Fabric)

| Direction | Concierge Type | Fabric Type | Adapter |
| --- | --- | --- | --- |
| Concierge → Fabric (Back tools) | K1 `CapabilityRequest` | K1 `CapabilityRequest` | Direct (same types) |
| Concierge → Fabric (OrchestratorStub) | POC `CapabilityRequest(name=...)` | K1 `CapabilityRequest(capability_name=...)` | `_FabricGatewayAdapter` converts |
| Fabric → Concierge (Back tools) | K1 `CapabilityResult` | K1 `CapabilityResult` | Direct |
| Fabric → Concierge (OrchestratorStub) | K1 `CapabilityResult` | POC `CapabilityResult` | `_FabricGatewayAdapter` converts back |

**Key field mapping** (`_FabricGatewayAdapter`):

| POC Field | K1 Field |
| --- | --- |
| `CapabilityRequest.name` | `CapabilityRequest.capability_name` |
| `CapabilityResult.error: str` | `CapabilityResult.error: Optional[ErrorInfo]` |

---

## 4. Concierge → Orchestrator

### 4.1 Internal OrchestratorStub (MEDIUM Tier)

Wired at factory Step 14. Only handles MEDIUM-tier tasks.

| Method | Input | Output | Budget |
| --- | --- | --- | --- |
| `handle_task(TaskEnvelope)` | POC `TaskEnvelope` | POC `AggregatedResult` | max 2 Fabric calls |
| `handle_multi_step(TaskEnvelope, cap_names)` | POC `TaskEnvelope` + `list[str]` | POC `AggregatedResult` | max 2 Fabric calls |

### 4.2 Full Orchestrator (HIGH Tier — Interface-only)

The routing code creates the correct `TaskEnvelope` with HIGH-tier budget (`max_fabric_calls=10, max_planner_tokens=3500`) but the actual K1 Orchestrator integration is not wired.

| Routing Code | K1 Orchestrator Method (from doc 15) | Status |
| --- | --- | --- |
| `route_task_sync(task, HIGH)` creates envelope | `Orchestrator.execute_plan(plan)` | **NOT WIRED** |
| — | `Orchestrator.handle_request(request)` | **NOT WIRED** |
| — | `DAGExecutor.execute(dag, context)` | **NOT WIRED** |

### 4.3 Cross-Reference with Orchestrator API Mapping (doc 15)

| Orchestrator Entry Point | Concierge Integration | Status |
| --- | --- | --- |
| `handle_request(OrchestratorRequest)` | Not called — would be HIGH tier path | **INTERFACE ONLY** |
| `execute_plan(CommittedPlan)` | Not called — would receive plan from Planner | **INTERFACE ONLY** |
| `DAGExecutor.execute(dag)` | Not called — part of full orchestration | **INTERFACE ONLY** |
| `StepRunner.run_step(step)` | Not called — part of DAG execution | **INTERFACE ONLY** |
| `ConstraintResolver.resolve(step)` | Not called — part of step execution | **INTERFACE ONLY** |
| `CompensationManager.compensate(step)` | Not called — part of error handling | **INTERFACE ONLY** |
| Bus: `k1.orchestration.task.accepted.v1` | OrchestratorStub emits this | ✅ (MEDIUM only) |
| Bus: `k1.orchestration.dag.completed.v1` | OrchestratorStub emits this | ✅ (MEDIUM only) |

### 4.4 Type Translation (Concierge → Orchestrator)

| Direction | Source Type | Target Type | Mechanism |
| --- | --- | --- | --- |
| Front → Stub | `TaskDispatch` → `TaskEnvelope` | POC `TaskEnvelope` | `route_task_sync()` builds envelope |
| Stub → Fabric | POC `CapabilityRequest` | K1 `CapabilityRequest` | `_FabricGatewayAdapter` |
| Stub → Concierge | POC `AggregatedResult` | → bus event | Emitted as `k1.orchestration.dag.completed.v1` |

---

## 5. Concierge → Planner (Indirect)

### 5.1 Current State

Concierge has **no direct integration** with Planner. The intended path is:

```text
Concierge (HIGH tier) → Orchestrator → Planner → CommittedPlan → Orchestrator → DAGExecutor → Fabric
```

This entire chain is interface-only in the POC.

### 5.2 Cross-Reference with Planner API Mapping (doc 15_planner)

| Planner Entry Point | Would-Be Caller | Status |
| --- | --- | --- |
| `PlannerEngine.plan(PlanRequest)` | Orchestrator (on HIGH-tier task from Concierge) | **NOT WIRED** |
| `PlannerEngine.replan(ReplanRequest)` | Orchestrator (on step failure) | **NOT WIRED** |
| `ToolCallRouter` (fabric_search) | Planner's own tool | N/A (Planner internal) |
| Bus: `k1.planner.plan.committed.v1` | Planner → Orchestrator | **NOT WIRED** |

### 5.3 Planned Data Flow (HIGH Tier)

When implemented, the expected flow:

| Step | Actor | Input | Output | Type System |
| --- | --- | --- | --- | --- |
| 1 | Concierge Front | dispatch_task(tier=HIGH) | TaskDispatch | Concierge types |
| 2 | Concierge routing | route_task_sync(HIGH) | TaskEnvelope(budget=Budget(max_fabric=10, planner_tokens=3500)) | POC types |
| 3 | Orchestrator | handle_request(envelope) | PlanRequest | K1 Orchestrator types |
| 4 | Planner | plan(PlanRequest) | CommittedPlan | K1 Planner types |
| 5 | Orchestrator | execute_plan(plan) | Build DAG | K1 Orchestrator types |
| 6 | DAGExecutor | execute(dag) | Per-step CapabilityRequest | K1 Fabric types |
| 7 | Fabric | execute(CapabilityRequest) | CapabilityResult | K1 Fabric types |
| 8 | Orchestrator | aggregate results | OrchestratorResult | K1 Orchestrator types |
| 9 | Concierge | receive result | AggregatedResult → FSM → Front | POC types (need bridge) |

---

## 6. Concierge → ModelHub (ILLMPort)

### 6.1 Integration Points

| Concierge Actor | When | Method | Purpose |
| --- | --- | --- | --- |
| Front Actor (step 9) | Every user turn | `ILLMPort.execute(HubRequest)` | ReAct loop LLM calls |
| Back Actor (step 6) | Every task execution | `ILLMPort.execute(HubRequest)` | ReAct loop LLM calls |
| Front Actor | Streaming responses | `ILLMPort.stream_execute(HubRequest)` | Token-by-token streaming |

**Production adapter**: `ModelHubPOCBridge` — wraps ModelHub's `complete()` / `stream()` into `HubRequest` / `HubResponse` types.

### 6.2 LLM Call Budget

| Tier | Max ReAct Iterations | Max LLM Calls (approx) |
| --- | --- | --- |
| Front (any) | Not budget-limited (conversation) | Typically 1-3 |
| Back LOW | 6 | Up to 6 |
| Back MEDIUM | 10 | Up to 10 |
| Back HIGH | 14 | Up to 14 |
| CRISIS | 0 | Hardcoded response, no LLM |

---

## 7. Concierge → K0 Memory (IMemoryPort)

### 7.1 Integration Points

| Tool | Actor | Method | Purpose |
| --- | --- | --- | --- |
| `recall_memory` (front) | Front | `IMemoryPort.recall(query, memory_types, max_results)` | Retrieve user memories for context |
| `recall_memory` (back) | Back | `IMemoryPort.recall(query, memory_types, max_results)` | Retrieve memories for task execution |

**Production adapter**: `RecallMemoryAdapter` / `BridgeRecallAdapter` — wraps K0 Bridge `recall_fn` closure.

### 7.2 Memory Types

The `memory_types` parameter filters by K0 memory layer:

| Memory Type | K0 Source | Description |
| --- | --- | --- |
| `episodic` | Episodic memory | Past events, experiences |
| `semantic` | Semantic memory | Facts, knowledge |
| `procedural` | Procedural memory | How-to knowledge |
| `working` | Working memory | Current context (may overlap with SS) |

---

## 8. Concierge → Bus (IDeltaPort)

### 8.1 Bus as Central Nervous System

The bus is the backbone for all async communication within Concierge. The FSM, both actors, and all protocol handlers communicate exclusively via bus events.

| Direction | Publisher Count | Subscriber Count | Total Topics |
| --- | --- | --- | --- |
| Inbound (to FSM) | 10+ external sources | FSM (20 subscriptions) | 20 |
| Outbound (from actors) | Front (6 categories) + Back (8 categories) | Various handlers | 14 |
| Internal (protocol) | HITL, Weave, Cancel, Pool | Various handlers | 11 |
| **Total** | — | — | **45** (35 STRICT + 10 RELAXED) |

### 8.2 Bus Topic Cross-Reference (What Crosses Component Boundaries)

| Topic | Source Component | Target Component | Data Shape |
| --- | --- | --- | --- |
| `k1.user.input.v1` | **External** → Concierge | Front mailbox | User text + metadata |
| `k1.orchestration.task.dispatch.v1` | **Concierge** Front | **Concierge** FSM → Back/Orch | TaskDispatch serialized |
| `k1.orchestration.task.complete.v1` | **Concierge** Back | **Concierge** FSM → Front | TaskComplete |
| `k1.orchestration.task.failed.v1` | **Concierge** Back | **Concierge** FSM → Front | TaskFailed |
| `k1.orchestration.task.accepted.v1` | **Concierge** OrchestratorStub | Observability | {task_id, tier} |
| `k1.orchestration.dag.completed.v1` | **Concierge** OrchestratorStub | **Concierge** FSM | AggregatedResult |
| `k1.orchestration.task.suspended.v1` | **Concierge** Back | **Concierge** HILCoordinator | HITL request |
| `k1.orchestration.task.resumed.v1` | **Concierge** HILCoordinator | **Concierge** Back resume | Resume payload |

Note: All `k1.orchestration.*` topics are currently **internal to Concierge** — when full K1 Orchestrator is wired, these will become cross-component boundaries.

---

## 9. Data Flow Chains (End-to-End)

### 9.1 Simple Conversation (LOW complexity)

```text
User → BusInputAdapter → bus "k1.user.input.v1"
  → Front mailbox → Phase1Pipeline.classify()
    → Phase1Result{complexity=LOW, domain=..., safety_band=GREEN}
      → FSM → COMPANIONING
        → Front 10-step:
          → SSMStateAdapter.get_snapshot() [READ SS]
          → DynamicPromptBuilder (9-stage)
          → ModelHubPOCBridge.execute(HubRequest) [LLM CALL]
          → Cognitive tools: update_beliefs, update_scoreboard, refine_affect [WRITE SS via IWriterPort]
          → BusOutputAdapter.send(response) [USER RESPONSE]
```

**Components touched**: User → Concierge → SessionState (read + write) → ModelHub → User

### 9.2 Medium Task (MEDIUM complexity)

```text
User → ... → Phase1Result{complexity=MEDIUM, ...}
  → FSM → DISPATCHING
    → Front 10-step:
      → dispatch_task(intents, tier=MEDIUM)
        → classify_intents → SINGLE
        → build_dispatches → TaskDispatch(tier=MEDIUM)
        → bus "k1.orchestration.task.dispatch.v1"

  → FSM._on_task_dispatch:
    → route_task_sync(task, MEDIUM)
      → TaskEnvelope(intent=..., budget=Budget(max_fabric_calls=2))
        → FabricDispatchAdapter.dispatch_envelope(envelope)
          → OrchestratorStub.handle_task(envelope):
            1. Emit "k1.orchestration.task.accepted"
            2. _StateReadAdapter.snapshot(["beliefs_active", "task_artifacts"]) [READ SS]
            3. Build POC CapabilityRequest(name=...)
            4. _FabricGatewayAdapter.execute(poc_req):
               → Convert: POC CapReq(name=X) → K1 CapReq(capability_name=X)
               → Fabric.execute(k1_req) [FABRIC CALL]
               → Convert: K1 CapResult → POC CapResult
            5. AggregatedResult.from_medium(result)
            6. Emit "k1.orchestration.dag.completed"

  → FSM → DELIVERING
    → Front PRESENT mode:
      → DynamicPromptBuilder (task_results section)
      → ModelHubPOCBridge.execute() [LLM CALL to compose response]
      → BusOutputAdapter.send(response) [USER RESPONSE]
```

**Components touched**: User → Concierge → SessionState (read) → Fabric (execute) → ModelHub → User

### 9.3 HITL Flow

```text
[Inside Back actor ReAct loop]
  → Back calls submit_result(result_type="needs_human", question="...", options=[...])
    → ToolResult.data._submission stashed
      → FSM intercept → bus "k1.orchestration.task.suspended.v1"
        → HILCoordinator.on_suspend(task_id):
          → Start timeout timer (5 min)
          → FSM → CLARIFYING_WORKER

  → Front HITL_RELAY mode:
    → DynamicPromptBuilder (hitl_context section)
    → ModelHubPOCBridge.execute() [LLM CALL to relay question]
    → BusOutputAdapter.send(relay_response) [ASK USER]

  → User responds → Phase1 → FSM HITL_RESOLVE:
    → Front extracts answer
    → bus "k1.concierge.hitl.resolved.v1"
      → HILCoordinator.on_resolve(task_id, answer):
        → Cancel timeout
        → bus "k1.orchestration.task.resumed.v1"
          → Back resume_handler(10-step):
            → Continue from suspended state
            → ... → submit_result(complete) → bus → FSM → DELIVERING
```

**Components touched**: Back → FSM → HILCoordinator → Front → ModelHub → User → Front → HILCoordinator → Back → ... → User

---

## 10. Invariant Matrix

### 10.1 Write Authority

| Component | Can Write SS? | Can Call LLM? | Can Call Fabric? | Can Emit Bus? |
| --- | --- | --- | --- | --- |
| Concierge Front Actor | ✅ (sole writer via cognitive tools) | ✅ (ReAct loop) | ❌ (only dispatches tasks) | ✅ |
| Concierge Back Actor | ❌ (snapshot-at-start, read-only) | ✅ (ReAct loop) | ✅ (via IDispatchPort) | ✅ |
| Concierge FSM | ✅ (control, task_state, meta only) | ❌ | ❌ | ✅ |
| OrchestratorStub | ❌ (IStateReadPort only, ORCH-01) | ❌ (no model port, ORCH-02) | ✅ (IFabricGatewayPort) | ✅ (IDeltaEmitPort) |
| K1 Orchestrator | ❌ (read-only, from doc 15) | ❌ | ✅ | ✅ |
| Planner | ❌ (read-only, from doc 15_planner) | ✅ (planning LLM) | ❌ (read-only discovery) | ✅ |
| Fabric | ❌ (read-only, from doc 16) | ✅ (capability execution) | N/A (is Fabric) | ✅ |
| SessionState | N/A (is the store) | ❌ | ❌ | ✅ (pressure events) |

### 10.2 Read Authority

| Component | SS Sections Readable | Via Adapter |
| --- | --- | --- |
| Concierge Front | ALL 15 sections | SSMStateAdapter |
| Concierge Back | ALL 15 sections (snapshot-at-start) | SSMStateAdapter |
| OrchestratorStub | `beliefs_active`, `task_artifacts` | _StateReadAdapter |
| K1 Orchestrator | TBD (MockStateReadAdapter is stub) | — |
| Planner | `beliefs_active`, `history_active`, `task_state` | PlannerStateAdapter |
| Fabric | `beliefs_active`, `history_active`, `task_state`, `control`, `affective_now`, `meta` | SessionStateReaderAdapter |
| ModelHub | Various | MHStateReadAdapter |

---

## 11. Adapter Bridge Map

All cross-component communication passes through adapters. This section maps every adapter in the Concierge boundary.

### 11.1 Production Adapters (8)

| Adapter | Port | Target | Location |
| --- | --- | --- | --- |
| `BusInputAdapter` | IInputPort | Bus → internal buffer | `adapters/bus_input.py` |
| `BusOutputAdapter` | IOutputPort | Internal → bus | `adapters/bus_output.py` |
| `SSMStateAdapter` | IStatePort | SessionStateManager | `adapters/ssm_state.py` |
| `FabricDispatchAdapter` | IDispatchPort | Fabric + OrchestratorStub | `adapters/fabric_dispatch.py` |
| `RecallMemoryAdapter` | IMemoryPort | K0 recall_fn closure | `adapters/recall_memory.py` |
| `ModelHubPOCBridge` | ILLMPort | ModelHub | `llm/model_hub_bridge.py` |
| `UltraBERTAdapter` | IClassificationPort | UltraBERT model | `fsm/phase1_adapter.py` |
| `Phase1Pipeline` | IClassificationPort | Multi-model pipeline | `fsm/phase1.py` |

### 11.2 Factory Bridge Adapters (3, private)

| Adapter | Port | Target | Converts |
| --- | --- | --- | --- |
| `_FabricGatewayAdapter` | IFabricGatewayPort | IFabricPort | POC CapReq ↔ K1 CapReq |
| `_StateReadAdapter` | IStateReadPort | IStatePort | snapshot/read_section → get_section |
| `_DeltaEmitAdapter` | IDeltaEmitPort | DeltaAggregator + IBus | Route delta/artifact vs general events |

### 11.3 Test Adapters (8)

| Adapter | Port | Purpose |
| --- | --- | --- |
| `StubInputAdapter` | IInputPort | Test harness |
| `StubOutputAdapter` | IOutputPort | Capture output |
| `MockStateAdapter` | IStatePort | Configurable state |
| `NullDispatchAdapter` | IDispatchPort | No-op dispatch |
| `NullMemoryAdapter` | IMemoryPort | Empty recall |
| `MockLLMAdapter` | ILLMPort | Scripted responses |
| `NullClassificationAdapter` | IClassificationPort | Default Phase1Result |
| `SnapshotStateAdapter` | IStatePort | Frozen snapshot |

---

## 12. Gap Analysis

### 12.1 Integration Gaps

| # | Gap | Severity | Components | Detail |
| --- | --- | --- | --- | --- |
| 1 | **HIGH tier not wired** | **P1** | Concierge ↔ Orchestrator ↔ Planner | `route_task_sync(HIGH)` creates correct TaskEnvelope but full Orchestrator+Planner pipeline is interface-only. No code path exercises HIGH tier end-to-end. |
| 2 | **Type bridge needed for HIGH tier** | **P2** | Concierge ↔ Orchestrator | POC `TaskEnvelope`/`AggregatedResult` must bridge to K1 `OrchestratorRequest`/`OrchestratorResult`. No bridge adapter exists. |
| 3 | **FabricDispatchAdapter unused by factory** | **P3** | Concierge (internal) | `PortBundle.dispatch: IDispatchPort` is defined, `FabricDispatchAdapter` implements it, but factory Step 14 wires OrchestratorStub directly via private adapters. The IDispatchPort from PortBundle is not used. |
| 4 | **Orchestrator SS read is stub** | **P3** | Orchestrator ↔ SessionState | K1 Orchestrator uses `MockStateReadAdapter()` (from doc 19). When Concierge HIGH-tier wires to it, real SS read adapter needed. |
| 5 | **Planner SS read is partial** | **P3** | Planner ↔ SessionState | `PlannerStateAdapter(reader=None)` placeholder in some paths (from doc 19). |
| 6 | **POC type divergence** | **P3** | Concierge ↔ Fabric | POC `CapabilityRequest.name` vs K1 `CapabilityRequest.capability_name`. Handled by `_FabricGatewayAdapter` but adds a translation layer. |
| 7 | **Deferred orchestrator ports** | **P2** | Concierge ↔ Orchestrator | `IPlannerPort`, `IWorkflowPort`, `IConnectorPort`, `IConstraintPort`, `ISagaPort` — interface-only in POC. |
| 8 | **ToolContext typed as Any** | **P4** | Concierge (internal) | All optional port references in ToolContext and ConciergeRuntime are `Any`. |

### 12.2 Consistency Checks

| Check | Result | Detail |
| --- | --- | --- |
| Bus topics: Concierge emits vs Fabric/Orch subscribe | ✅ Consistent | OrchestratorStub uses same topic names as K1 Orchestrator would |
| SS sections: Concierge writes vs SS manager accepts | ✅ Consistent | All 30 valid operations documented in doc 18 cover Concierge's writes |
| Type bridging: POC → K1 for Fabric calls | ✅ Handled | `_FabricGatewayAdapter` converts `name` → `capability_name` |
| Budget enforcement: Concierge tiers vs Fabric/Orch limits | ✅ Consistent | TIER_FABRIC_BUDGET matches OrchestratorStub's `_check_budget()` |
| HITL cycle: suspend/resume events match between actors | ✅ Consistent | 8-step closed cycle verified: suspend → relay → resolve → resume |

### 12.3 Recommended Actions

| Priority | Action | Effort |
| --- | --- | --- |
| P1 | Wire HIGH-tier path: Concierge → K1 Orchestrator → K1 Planner → Fabric | Large |
| P2 | Build type bridge: POC TaskEnvelope → K1 OrchestratorRequest | Medium |
| P2 | Implement deferred ports (IPlannerPort, IWorkflowPort, etc.) in OrchestratorStub or K1 Orchestrator | Medium |
| P3 | Wire FabricDispatchAdapter into factory or remove PortBundle.dispatch | Small |
| P3 | Wire real SS adapter for K1 Orchestrator (replace MockStateReadAdapter) | Small |
| P3 | Wire real SS adapter for Planner (replace None placeholder) | Small |
| P4 | Replace `Any` types with proper protocol imports in ToolContext / ConciergeRuntime | Small |
