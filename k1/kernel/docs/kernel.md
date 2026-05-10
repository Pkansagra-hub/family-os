# K1 Kernel Wiring Specification

Status: PLANNING -- fill as implementation proceeds.

---

## 1. Purpose

This document is the single reference for wiring Bus, Fabric, SessionState,
Orchestrator, Planner, Model Hub, and Concierge into a unified K1 kernel runtime.  Each
component is self-contained with hexagonal ports.  The kernel bootstrap creates
shared infrastructure (Bus, MailboxRouter) and injects real adapters into each
component's factory.  Seven managed components total.

Concierge is the user-facing intelligence — the FSM, the LLM host, the
conversation conductor.  It is the only K1 component that talks to the user
and the only writer to SessionState (Single Writer Pattern, ADR-0017).  It
consumes Bus, Fabric, SessionState, Orchestrator, and the LLM Model Hub
through 8 hexagonal ports defined in `k1/concierge/concierge.mmd`.

---

## 2. Component Inventory

| Component | Factory | Ports (count) | Standalone Adapters | Bus Adapter |
|-----------|---------|---------------|---------------------|-------------|
| Bus | `BusFactory.create_local()` | 3 (IBus, IMailbox, IMailboxRouter) | n/a (IS the infrastructure) | n/a |
| Fabric | `FabricFactory.create_with_ports()` | 6 | Test stubs for all 6 | `FabricBusAdapter` |
| SessionState | `SessionStateFactory.create_with_ports()` | 5 (4 mandatory + 1 optional) | Local/in-memory for all | `SessionBusAdapter` |
| Orchestrator | `OrchestratorFactory.create_production()` | 9 (8 core + IAdminPort): IMailboxPort, IFabricGatewayPort, IPlannerPort, IStateReadPort, IDeltaEmitPort, IBridgeWritePort, IEventSubscriptionPort, IWorkflowStoragePort, IAdminPort | 17 adapters (8 production + 8 test + AdminHttpAdapter) | Reuses `FabricBusAdapter` via EventSubscriptionAdapter + DeltaEmitAdapter |
| Planner | `PlannerFactory.create_production()` | 7: IMailboxPort, ILLMPort, IFabricRetrievalPort, IStateReadPort, IBridgePort, IDeltaEmitPort, IEventPort | 7 test adapters (all 7 slots) | Reuses `FabricBusAdapter` via EventBusAdapter + DeltaBusAdapter |
| Model Hub | `ModelHubFactory.create_standalone()` / `create_for_testing()` / `create_with_ports()` | 7: IModelHubPort (facade), IEventPort, IStateReadPort, IMetricsPort, IConfigPort, ICredentialPort, IHealthPort | Test adapters for all 7 | n/a (consumers use LLMGatewayAdapter / ModelGatewayAdapter) |
| Concierge | `ConciergeFactory.create_with_ports()` | 8: IInputPort, IOutputPort, IClassificationPort, ILLMPort, IStatePort, IDispatchPort, IDeltaPort, IMemoryPort | 8 test adapters (all 8 slots) | Reuses `FabricBusAdapter` via DeltaBusAdapter; owns front/back mailboxes via MailboxRouter |
| Kernel | `k1/kernel/` | 0 | n/a | n/a |

---

## 3. Dependency Graph

```
k1.kernel.bootstrap
  |
  +-- creates --> BusFactory.create_local(backend="auto")  --> IBus
  +-- creates --> BusFactory.create_mailbox_router()        --> IMailboxRouter
  |
  +-- creates --> FabricBusAdapter(bus)
  |     implements: Fabric.IEventPort + Fabric.IDeltaBusPort
  |
  +-- creates --> SessionBusAdapter(bus)
  |     implements: SessionState.IEventPort (ABC)
  |
  +-- creates --> SessionStateFactory.create_with_ports(...)
  |     storage:   SQLiteStorageAdapter(db_path)
  |     events:    SessionBusAdapter(bus)         <-- wired
  |     writer:    DirectWriterAdapter()          <-- standalone OK
  |     lifecycle: StandaloneLifecycle(config)    <-- standalone OK
  |     k0_sync:   NullSyncPort()                <-- optional
  |
  +-- creates --> SessionStateReaderAdapter(session_manager)
  |     implements: Fabric.ISessionStateReader
  |
  +-- creates --> FabricFactory.create_with_ports(...)
  |     state_reader:  SessionStateReaderAdapter(session_manager)  <-- wired
  |     event_port:    FabricBusAdapter(bus)                       <-- wired
  |     delta_bus:     FabricBusAdapter(bus)                       <-- wired (same instance)
  |     bridge:        TestBridgeAdapter() | BridgeConnectionAdapter()
  |     model_gateway: TestModelGatewayAdapter() | real gateway
  |     prompt_system: TestPromptSystemAdapter() | real prompts
  |
  +-- creates --> ModelHubFactory.create_standalone(config, plugins)
  |     # Model Hub is Layer L2.5 -- created AFTER Fabric, BEFORE Orchestrator.
  |     # Consumers (Planner, Concierge) wrap it via their own adapters:
  |     #   Planner:   LLMGatewayAdapter(model_hub)    -> ILLMPort
  |     #   Concierge: ModelGatewayAdapter(model_hub)   -> ILLMPort
  |     config:         ModelHubConfig.from_dict(config.model_hub_overrides)
  |     plugins:        {"openai": OpenAIPlugin(), "anthropic": AnthropicPlugin(), ...}
  |     # Internal wiring (NOT injected by kernel):
  |     #   RequestRouter (9-step pipeline), CapabilityRouter,
  |     #   ModelSelector, BudgetEnforcer, ProviderDispatcher,
  |     #   ProviderRegistry, RateLimiter, ResponseCache,
  |     #   NormalizationLayer, CostTracker, AuditLogger,
  |     #   CircuitBreakerManager, HealthReportAdapter
  |
  +-- creates --> OrchestratorFactory.create_production(config)
  |     # Orchestrator reuses existing Bus, Fabric, SessionState instances:
  |     fabric_gateway: FabricGatewayAdapter(fabric)               <-- wraps Fabric facade from Phase 3
  |     state_read:    StateReadAdapter(state_reader)              <-- wraps same SessionStateReaderAdapter
  |     event_sub:     EventSubscriptionAdapter(fabric_bus)        <-- wraps same FabricBusAdapter IEventPort
  |     delta_emit:    DeltaEmitAdapter(fabric_bus, fabric_bus)    <-- wraps same bus adapter (event + delta)
  |     mailbox:       MailboxAdapter(max_depth=config.mailbox_capacity) <-- standalone WFQ priority queue
  |     planner:       PlannerAdapter(planner_mailbox, cb_planner) <-- requires Planner module
  |     bridge_write:  BridgeWriteAdapter(bridge_client)           <-- requires Bridge connector
  |     workflow_store: WorkflowStorageAdapter(SQLiteWorkflowAdapter(config.workflow_db_path)) <-- standalone SQLite
  |
  +-- creates --> PlannerFactory.create_production(config)
  |     # Planner reuses existing Bus, Fabric, SessionState instances:
  |     llm_port:     LLMGatewayAdapter(model_hub)                 <-- wraps Model Hub (Phase 2: TestLLMAdapter)
  |     fabric_port:  FabricRetrievalAdapter(fabric)               <-- wraps Fabric capability/prompt retrieval
  |     state_port:   SessionStateReadAdapter(state_reader)        <-- wraps same SessionStateReaderAdapter
  |     bridge_port:  BridgeAdapter(bridge_client)                 <-- K0 recall + persist (Phase 1: TestBridgeAdapter)
  |     delta_port:   DeltaBusAdapter(fabric_bus)                  <-- wraps FabricBusAdapter delta bus
  |     event_port:   EventBusAdapter(fabric_bus)                  <-- wraps FabricBusAdapter event port
  |     mailbox_port: MailboxAdapter(max_depth=config.mailbox_max_depth) <-- standalone FIFO queue
  |
  +-- cross-wires --> Orchestrator.IPlannerPort
  |     planner_mailbox = planner.get_mailbox()                    <-- extract Planner's mailbox
  |     cb_planner = CircuitBreaker("CB_PLANNER", orch_config)     <-- Orchestrator owns CB
  |     planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
  |     orchestrator._planner_port = planner_adapter               <-- hot-swap MockPlannerAdapter
  |
  +-- creates --> ConciergeFactory.create_with_ports(...)
  |     # Concierge is the user-facing intelligence. It receives ALL other
  |     # components through ports -- never creates Bus, SS, Fabric, etc.
  |     # 8 ports per concierge.mmd Epic 1.
  |     input_port:      WebSocketInputAdapter(ws_server)           <-- Phase 2; Phase 1: TestInputAdapter
  |     output_port:     SSEOutputAdapter(sse_server)               <-- Phase 2; Phase 1: TestOutputAdapter
  |     classification:  UltraBERTv4Adapter()                       <-- Phase 2; Phase 1: MockClassificationAdapter / stub
  |     llm_port:        ModelGatewayAdapter(model_hub)             <-- wraps Model Hub; Phase 1: ModelHubPOCBridge(GeminiAdapter)
  |     state_port:      SessionKernelAdapter(session_manager)      <-- wraps SessionState from Phase 2; Phase 1: direct SS access
  |     dispatch_port:   FabricOrchestratorAdapter(fabric, orch)    <-- routes by tier: LOW->Fabric, MED/HIGH->Orchestrator
  |     delta_port:      DeltaBusAdapter(fabric_bus, bus)           <-- emit events + subscribe deltas via Bus
  |     memory_port:     BridgeRecallAdapter(bridge_client)         <-- K0 long-term recall; Phase 1: recall_fn closure
  |     config:          ConciergeConfig
  |
  |     # Concierge-internal wiring (NOT injected by kernel):
  |     #   FSM (ConciergeController), Front/Back actors,
  |     #   ToolDispatchers, ExperienceLayer, DeltaAggregator,
  |     #   HILCoordinator, WeaveBatcher, OppPipeline,
  |     #   DynamicPromptBuilder, MutationGuard, FrontLock
  |
  +-- exposes --> Kernel API surface
```

---

## 4. Port Wiring Matrix

### 4.1 Fabric Ports (6 total)

| Port | Protocol | Wired Adapter | Source Module | Notes |
|------|----------|---------------|---------------|-------|
| `IEventPort` | `Protocol` (structural) | `FabricBusAdapter(bus)` | `k1.bus.adapters.fabric_adapter` | `emit(topic: str, payload: Dict)` maps to `bus.publish(Envelope)` |
| `IDeltaBusPort` | `Protocol` (structural) | `FabricBusAdapter(bus)` | `k1.bus.adapters.fabric_adapter` | Same adapter instance; `emit_delta()` publishes to `k1.agent.{id}.delta.v1` |
| `ISessionStateReader` | `Protocol` (structural) | `SessionStateReaderAdapter(mgr)` | `k1.fabric.adapters.sessionstate_reader` | Wraps real `SessionStateManager`; read-only (FAB-01) |
| `IBridgePort` | `Protocol` (structural) | `TestBridgeAdapter()` | `k1.fabric.adapters.test_bridge` | Phase 1: test stub. Phase 2: `BridgeConnectionAdapter` |
| `IModelGatewayPort` | `Protocol` (structural) | `TestModelGatewayAdapter()` | `k1.fabric.adapters.test_model_gateway` | Phase 1: test stub. Phase 2: real LLM gateway |
| `IPromptSystemPort` | `Protocol` (structural) | `TestPromptSystemAdapter()` | `k1.fabric.adapters.test_prompt_system` | Phase 1: test stub. Phase 2: real prompt registry |

### 4.3 Orchestrator Ports (9 total: 8 core + IAdminPort)

| Port | Protocol | Wired Adapter | Source Module | Notes |
|------|----------|---------------|---------------|-------|
| `IMailboxPort` | `Protocol` (structural) | `MailboxAdapter(max_depth=config.mailbox_capacity)` | `k1.orchestrator.adapters.mailbox_adapter` | Standalone in-process WFQ priority queue. Three priority classes: REALTIME(0.6), INTERACTIVE(0.3), BACKGROUND(0.1). Thread-safe. |
| `IFabricGatewayPort` | `Protocol` (structural) | `FabricGatewayAdapter(fabric)` | `k1.orchestrator.adapters.fabric_gateway_adapter` | Wraps Fabric facade from Phase 3. execute() -> Fabric.execute(). No CB (Concierge owns CB_FABRIC). |
| `IPlannerPort` | `Protocol` (structural) | `PlannerAdapter(planner_mailbox, cb_planner)` | `k1.orchestrator.adapters.planner_adapter` | Orchestrator owns CB_PLANNER. Requires Planner module mailbox (Phase 5 wiring). |
| `IStateReadPort` | `Protocol` (structural) | `StateReadAdapter(state_reader)` | `k1.orchestrator.adapters.state_read_adapter` | Wraps same SessionStateReaderAdapter used by Fabric. Read-only (ORCH-01). |
| `IDeltaEmitPort` | `Protocol` (structural) | `DeltaEmitAdapter(event_port, delta_bus)` | `k1.orchestrator.adapters.delta_emit_adapter` | Dual-publish: event_port for internal events + delta_bus for user-facing deltas. Reuses FabricBusAdapter instances from Phase 3. Fire-and-forget, never raises. |
| `IBridgeWritePort` | `Protocol` (structural) | `BridgeWriteAdapter(bridge_client)` | `k1.orchestrator.adapters.bridge_write_adapter` | Phase 1: TestBridgeAdapter (fire-and-forget stubs). Phase 2: real Bridge connector. Write methods never raise; only read_wal() surfaces errors. |
| `IEventSubscriptionPort` | `Protocol` (structural) | `EventSubscriptionAdapter(event_port)` | `k1.orchestrator.adapters.event_subscription_adapter` | Wraps FabricBusAdapter IEventPort from Phase 3. subscribe/unsubscribe/emit. Tracks handles for bulk cleanup at shutdown. |
| `IWorkflowStoragePort` | `Protocol` (structural) | `WorkflowStorageAdapter(SQLiteWorkflowAdapter(config.workflow_db_path))` | `k1.orchestrator.adapters.workflow_storage_adapter` | Standalone SQLite. Constructor takes `IWorkflowStoragePort` impl, typically `SQLiteWorkflowAdapter` from `k1.orchestrator.workflows.persistence.sqlite_adapter`. |
| `IAdminPort` | `Protocol` (structural, runtime_checkable) | `AdminHttpAdapter(service, config)` | `k1.orchestrator.adapters.admin_http_adapter` | Lightweight aiohttp HTTP server on port 8081 (config.admin_port). 18 JSON endpoints for health, DAG inspection, CB control, drain. Created post-construction (circular dep on OrchestratorService). Disabled in test configs (admin_enabled=False). |

### 4.2 SessionState Ports (5 total, 4 mandatory)

| Port | ABC | Wired Adapter | Source Module | Notes |
|------|-----|---------------|---------------|-------|
| `IStoragePort` | ABC | `SQLiteStorageAdapter(db_path)` | `k1.sessionstate.adapters.sqlite_storage` | LOCAL COLD tier |
| `IEventPort` | ABC | `SessionBusAdapter(bus)` | `k1.bus.adapters.session_adapter` | `emit(event_type, payload)` maps to `k1.session.{event_type}` |
| `IWriterPort` | ABC | `DirectWriterAdapter()` | `k1.sessionstate.adapters.direct_writer` | Single-process: direct mutation OK |
| `ILifecyclePort` | ABC | `StandaloneLifecycle(config)` | `k1.sessionstate.adapters.standalone_lifecycle` | Self-managed checkpointing |
| `IK0SyncPort` | ABC (optional) | `NullSyncPort()` | `k1.sessionstate.ports.k0_sync` | No cloud sync until Bridge ready |

### 4.4 Planner Ports (7 total)

| Port | Protocol | Wired Adapter | Source Module | Notes |
|------|----------|---------------|---------------|-------|
| `IMailboxPort` | `Protocol` (structural) | `MailboxAdapter(max_depth=config.mailbox_max_depth)` | `k1.planner.adapters.mailbox_adapter` | FIFO async queue: `enqueue(PlanRequest)`, `dequeue()`, `drain()`. Standalone in-process. |
| `ILLMPort` | `Protocol` (structural) | `LLMGatewayAdapter(model_hub)` | `k1.planner.adapters.llm_gateway_adapter` | Phase 1: `TestLLMAdapter`. Phase 2: real Model Hub gateway. `generate()`, `generate_structured()`. |
| `IFabricRetrievalPort` | `Protocol` (structural) | `FabricRetrievalAdapter(fabric)` | `k1.planner.adapters.fabric_retrieval_adapter` | Wraps Fabric facade. `discover_capabilities()`, `search_prompts()`. Read-only. |
| `IStateReadPort` | `Protocol` (structural) | `SessionStateReadAdapter(state_reader)` | `k1.planner.adapters.session_state_adapter` | Wraps same `SessionStateReaderAdapter` used by Fabric and Orchestrator. Read-only (PLAN-01). |
| `IBridgePort` | `Protocol` (structural) | `BridgeAdapter(bridge_client)` | `k1.planner.adapters.bridge_adapter` | Phase 1: `TestBridgeAdapter`. K0 long-term recall + plan persistence. |
| `IDeltaEmitPort` | `Protocol` (structural) | `DeltaBusAdapter(fabric_bus)` | `k1.planner.adapters.delta_bus_adapter` | Wraps `FabricBusAdapter` delta bus. Fire-and-forget: `emit_delta(topic, payload)`. |
| `IEventPort` | `Protocol` (structural) | `EventBusAdapter(fabric_bus)` | `k1.planner.adapters.event_bus_adapter` | Wraps `FabricBusAdapter` event port. `emit()`, `subscribe()`, `unsubscribe()`. Tracks handles for bulk cleanup at shutdown. |

### 4.5 Concierge Ports (8 total)

Architecture reference: `k1/concierge/concierge.mmd` Epic 1 (Hexagonal Architecture).
POC implementation reference: `poc/k1_poc/concierge_poc_architecture.mmd`.
Ported code: `k1/concierge/` (M5 Big Copy + M6 Fabric wiring).

The Concierge is the conversation conductor — the only component that talks to
the user and the only writer to SessionState (ADR-0017 Single Writer Pattern).
It hosts: FSM (12 states), Front/Back dual-LLM actors, 16 tools (10 Front + 6 Back),
ExperienceLayer (6 components), DynamicPromptBuilder (10 prompt modes),
HILCoordinator (3 variants), WeaveBatcher, OppPipeline (8 primitives),
DeltaAggregator, MutationGuard, FrontLock, and the ReAct loop.

All external dependencies are accessed through ports. Internal services
call ports, never external systems directly (INV-16).

| Port | Protocol | Direction | Wired Adapter | Source Module | Phase 1 (POC) Stub | Notes |
|------|----------|-----------|---------------|---------------|--------------------|----- |
| `IInputPort` | `Protocol` (structural) | Inbound | `WebSocketInputAdapter(ws)` / `RESTInputAdapter(http)` | `k1.concierge.adapters.ws_input` | `TestInputAdapter` — inject messages programmatically | `receive() → UserMessage`. Entry point for all user input. |
| `IOutputPort` | `Protocol` (structural) | Outbound | `SSEOutputAdapter(sse)` / `WebSocketOutputAdapter(ws)` | `k1.concierge.adapters.sse_output` | `TestOutputAdapter` — capture + assert on messages | `send(OutputEvent) → DeliveryReceipt`. All output goes through OUTPUT_CHANNEL. Priority routing: REALTIME (3 retries), PROGRESS (1 retry), BACKGROUND (0 retries). CB_SSE owner. |
| `IClassificationPort` | `Protocol` (structural) | Outbound | `UltraBERTv4Adapter()` | `k1.concierge.adapters.ultrabert` | `MockClassificationAdapter` — scripted ClassificationResult | `classify(text) → ClassificationResult`. Phase 1 deterministic pre-LLM: intent classification, entity extraction, safety band, emotion, domain detection. 12 heads, 22ms target. Heuristic fallback when CB_MODEL open (<1ms). |
| `ILLMPort` | `Protocol` (structural) | Outbound | `ModelGatewayAdapter(model_hub)` | `k1.concierge.adapters.model_gateway` | `ModelHubPOCBridge(GeminiConciergeAdapter)` — already ported (M1) | `execute(HubRequest) → HubResponse`, `stream_execute(HubRequest) → AsyncIterator[HubChunk]`. Capabilities: CHAT, TOOL_CALL, STRUCTURED, VISION, REASON. LLM cascade: RETRY → CB HALF-OPEN → CANNED_RESPONSE. Prompt injection boundary: LLM text is non-operative; side effects only via tool_call. |
| `IStatePort` | `Protocol` (structural) | Both | `SessionKernelAdapter(session_manager)` | `k1.concierge.adapters.session_kernel` | Direct `session_state.get_section()` / `MutationGuard` writes | `read(sections[]) → Snapshot`, `write(section, op, data) → WriteResult`. Concierge is the ONLY writer (ADR-0017). MutationGuard inside adapter: 3-tier validation (section capacity → tier capacity → total capacity). Emergency mode at ≥95% pressure. CB_SESSIONSTATE owner. |
| `IDispatchPort` | `Protocol` (structural) | Outbound | `FabricOrchestratorAdapter(fabric, orchestrator)` | `k1.concierge.adapters.fabric_orchestrator` | `OrchestratorStub` (185 lines, MEDIUM only, 1-2 Fabric calls) + `ToolContext.fabric_port` | `dispatch_direct(CapReq) → CapResult`, `dispatch_envelope(TaskEnv) → void`. Routes by tier: LOW → Fabric direct, MED/HIGH → Orchestrator. Tier degradation cascade: HIGH(CB_PLANNER open)→MED, MED(CB_ORCH open)→LOW, LOW(CB_FABRIC open)→canned. CB_ORCHESTRATOR + CB_PLANNER + CB_FABRIC + CB_MCP owner. |
| `IDeltaPort` | `Protocol` (structural) | Both | `DeltaBusAdapter(fabric_bus, bus)` | `k1.concierge.adapters.delta_bus` | `DeltaAggregator` + direct `bus.publish()` | `subscribe(topics[]) → DeltaStream`, `publish(event) → void`, `errors() → ErrorStream`. Emit failure = log + skip (RECOVERABLE). Never TERMINAL (Edge-First: best-effort). |
| `IMemoryPort` | `Protocol` (structural) | Outbound | `BridgeRecallAdapter(bridge_client)` | `k1.concierge.adapters.bridge_recall` | `recall_fn` closure — keyword-scoring over seed memories | `recall(query, selectors[]) → MemoryResult`. K0 long-term memory query via Bridge → K0 Query Port. Recall timeout = skip memory (RECOVERABLE). Never TERMINAL (Edge-First: respond without memory). |

**Circuit Breakers (7 total, owned by Concierge adapters):**

| CB Name | Owner Adapter | Trigger | Fallback |
|---------|---------------|---------|----------|
| `CB_SSE` | SSEOutputAdapter | SSE connection failure | Buffer 5 msgs, flush on reconnect |
| `CB_MODEL` | UltraBERTv4Adapter / ModelGatewayAdapter | LLM timeout/5xx | Heuristic fallback (<1ms) / CANNED_RESPONSE |
| `CB_SESSIONSTATE` | SessionKernelAdapter | SS read timeout | Stale cached data (DEGRADED) |
| `CB_ORCHESTRATOR` | FabricOrchestratorAdapter | Orchestrator failure | Tier degradation HIGH→MED→LOW |
| `CB_PLANNER` | FabricOrchestratorAdapter | Planner failure | Tier degradation HIGH→MED |
| `CB_FABRIC` | FabricOrchestratorAdapter | Fabric failure | Canned response |
| `CB_MCP` | FabricOrchestratorAdapter | MCP server failure | Mark tool unavailable |

---

## 5. Bus Adapter Contracts

### 5.1 FabricBusAdapter

- Location: `k1/bus/adapters/fabric_adapter.py`
- Constructor: `FabricBusAdapter(bus: LocalBus)`
- Satisfies: Fabric `IEventPort` + `IDeltaBusPort` (structural)
- Serialization: JSON (dict <-> bytes via Envelope payload)
- Topic mapping:
  - `emit(topic, payload)` --> `bus.publish(Envelope(topic=topic, payload=json(payload)))`
  - `emit_delta(agent_id, ...)` --> topic `k1.agent.{agent_id}.delta.v1`
  - `subscribe(topic, handler)` --> `bus.subscribe(topic, wrapper_that_deserializes)`

### 5.2 SessionBusAdapter

- Location: `k1/bus/adapters/session_adapter.py`
- Constructor: `SessionBusAdapter(bus: LocalBus)`
- Satisfies: SessionState `IEventPort` (ABC inheritance)
- Serialization: JSON (Any <-> bytes via Envelope payload)
- Topic mapping:
  - `emit(event_type, payload)` --> topic `k1.session.{event_type}`
  - `subscribe(event_type, handler)` --> `bus.subscribe("k1.session.{event_type}", wrapper)`
- Properties: `is_connected` (returns `not bus.closed`), `active_subscriptions`

### 5.3 SessionStateReaderAdapter

- Location: `k1/fabric/adapters/sessionstate_reader.py`
- Constructor: `SessionStateReaderAdapter(manager: SessionStateManager)`
- Satisfies: Fabric `ISessionStateReader` (structural)
- Delegates: `read_section()`, `read_sections()`, `get_snapshot()` to the real manager

### 5.4 PlannerEventBusAdapter

- Location: `k1/planner/adapters/event_bus_adapter.py`
- Constructor: `EventBusAdapter(event_port: Any)` -- wraps Fabric `IEventPort` (5.1.2)
- Satisfies: Planner `IEventPort` (SS15.8, structural Protocol)
- Serialization: passthrough (Planner and Fabric `IEventPort` are interface-identical per SS15.9)
- Topic mapping:
  - `emit(topic, payload)` --> `fabric_event_port.emit(topic, payload)` (direct passthrough)
  - `subscribe(topic, handler)` --> `fabric_event_port.subscribe(topic, handler)` --> returns `SubscriptionHandle`
  - `unsubscribe(handle)` --> `fabric_event_port.unsubscribe(handle)` --> returns `bool`
- Fire-and-forget: `emit()` catches all exceptions and logs; NEVER raises to caller
- Slots: `_bus` (single slot, the wrapped Fabric `IEventPort`)
- Used by: PlannerAgent (4 subscriptions at INIT), CommitService (plan.ready emission), HILCoordinator (clarification/approval emission)

### 5.5 PlannerDeltaBusAdapter

- Location: `k1/planner/adapters/delta_bus_adapter.py`
- Constructor: `DeltaBusAdapter(delta_bus: Any, agent_id: str = "planner")` -- wraps Fabric `IDeltaBusPort` (5.1.6)
- Satisfies: Planner `IDeltaEmitPort` (SS15.7, structural Protocol)
- Serialization: maps Planner `DeltaPayload` fields to Fabric `IDeltaBusPort.emit_delta()` positional args
- Topic mapping:
  - `emit(delta: DeltaPayload)` --> `fabric_delta_bus.emit_delta(agent_id, delta.delta_type, delta.section, delta.data)`
  - Topic on wire: `k1.agent.planner.delta.v1` (pre-stamped `agent_id="planner"`)
- Fire-and-forget: `emit()` catches all exceptions and logs; NEVER raises to caller
- Slots: `_bus`, `_agent_id`
- Delta loss is acceptable (observability signals, not control-plane)
- Used by: PipelineController (stage transition deltas), CommitService (commit result delta)

### 5.6 ConciergeSessionAdapter

- Location: `k1/concierge/adapters/session_kernel.py` (TODO: extract from bootstrap)
- Constructor: `SessionKernelAdapter(manager: SessionStateManager)`
- Satisfies: Concierge `IStatePort` (structural)
- Delegates: `read(sections)` → `manager.get_section(name)` for each section; `write(section, op, data)` → `MutationGuard.preflight()` → section method call
- MutationGuard inside: 3-tier validation (section capacity → tier capacity → total capacity)
- Emergency mode: ≥95% pressure → ALL writes rejected
- CB_SESSIONSTATE owner: read timeout → stale cached data (DEGRADED)
- ADR-0017 enforced: Concierge is the ONLY component wired with write access
- POC Phase 1 stub: Direct `session_state.get_section()` + `MutationGuard` writes in tool implementations

### 5.7 ConciergeDeltaBusAdapter

- Location: `k1/concierge/adapters/delta_bus.py` (TODO: extract from bootstrap)
- Constructor: `DeltaBusAdapter(event_port: FabricBusAdapter, bus: LocalBus)`
- Satisfies: Concierge `IDeltaPort` (structural)
- Subscribe side: `subscribe(topics)` → registers handlers via `bus.subscribe()` for each topic → returns DeltaStream
- Publish side: `publish(event)` → `event_port.emit(topic, payload)` (fire-and-forget)
- Error side: `errors()` → ErrorStream of failed deliveries (logged, never raised)
- Used by: FSM Controller (subscribe to `k1.orchestration.task.*`, `k1.orchestration.dag.*`), DeltaAggregator (batch window 500ms → FSM.apply_deltas()), Front actor (subscribe to `k1.orchestration.task.complete.v1`, `task.failed.v1`, `task.suspended.v1`, `findings.ready.v1`)
- POC Phase 1 stub: DeltaAggregator + direct `bus.publish()` + `subscribe_front_events()`

### 5.8 ConciergeFabricOrchestratorAdapter

- Location: `k1/concierge/adapters/fabric_orchestrator.py` (TODO: extract from bootstrap)
- Constructor: `FabricOrchestratorAdapter(fabric: Fabric, orchestrator: OrchestratorService)`
- Satisfies: Concierge `IDispatchPort` (structural)
- Routing logic:
  - `dispatch_direct(CapReq)` → `fabric.execute(request)` (LOW tier: direct Fabric call)
  - `dispatch_envelope(TaskEnv)` → `orchestrator.mailbox.enqueue(envelope)` (MED/HIGH tier)
- Circuit breakers: CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP
- Tier degradation: HIGH(CB_PLANNER open)→MED, MED(CB_ORCH open)→LOW, LOW(CB_FABRIC open)→canned
- POC Phase 1 stub: `OrchestratorStub` (185 lines, MEDIUM only, 1-2 Fabric calls) + `ToolContext.fabric_port` for LOW tier

---

## 6. Topic Namespace Registry

| Prefix | Owner | Purpose |
|--------|-------|---------|
| `k1.session.*` | SessionBusAdapter | Session state events (mutations, checkpoints) |
| `k1.agent.{id}.delta.v1` | FabricBusAdapter | Agent delta broadcasts |
| `k1.fabric.*` | FabricBusAdapter | Fabric lifecycle/execution events |
| `k1.orchestration.*` | DeltaEmitAdapter | Orchestrator task/DAG/step/workflow/saga events (17 emitted topics via `events.py`) |
| `k1.planner.plan.request.v1` | Orchestrator (via PlannerAdapter) | Plan request enqueued to Planner mailbox |
| `k1.planner.plan.ready.v1` | PlannerAgent (CommitService) | Committed plan emitted; consumed by Orchestrator EventSubscriptionAdapter |
| `k1.planner.plan.failed.v1` | PlannerAgent | Planning pipeline failed (stage error or timeout); consumed by Orchestrator |
| `k1.planner.plan.cancelled.v1` | PlannerAgent | Plan cancelled (cancel set or shutdown drain); consumed by Orchestrator |
| `k1.planner.plan.cancel.v1` | Orchestrator (via PlannerAdapter) | Cancel request for in-flight/queued plan |
| `k1.planner.micro_replan.ready.v1` | PlannerAgent | Micro-replan completed; consumed by Orchestrator |
| `k1.planner.delta.v1` | PlannerAgent (PipelineController) | Stage progress deltas (sketch/expand/validate/commit transitions) |
| `k1.hil.clarification.v1` | PlannerAgent (HILCoordinator) | HIL clarification question emitted to user via Bridge |
| `k1.hil.approval_request.v1` | PlannerAgent (HILCoordinator) | HIL approval request emitted to user via Bridge |
| `k1.hil.clarification_response.v1` | Bridge / Bus | User clarification response; consumed by PlannerAgent |
| `k1.hil.approval_response.v1` | Bridge / Bus | User approval response; consumed by PlannerAgent |
| `k1.capability.*` | Fabric / Bus | Capability completion/failure events (consumed by Orchestrator via EventSubscriptionAdapter) |
| `k1.bus.lifecycle.*` | RustBus/LocalBus | Internal bus lifecycle (subscribe/unsubscribe) |
| `k1.kernel.*` | Kernel bootstrap | Kernel-level events (startup, shutdown, health) |
| `k1.session.user.input.v1` | Concierge (FSM) | User input received; routed to Front actor mailbox (URGENT) |
| `k1.response.ack.v1` | Concierge (Front) | Acknowledgment streamed to user (URGENT) |
| `k1.response.final.v1` | Concierge (Front) | Final response to user (URGENT) |
| `k1.response.clarification.v1` | Concierge (Front) | Clarification question to user (URGENT) |
| `k1.response.stream.v1` | Concierge (Front) | Streaming text delta chunks to OutputChannel |
| `k1.orchestration.task.dispatch.v1` | Concierge (Front) | Front dispatches task to Back actor (INTERACTIVE) |
| `k1.orchestration.task.complete.v1` | Concierge (Back) | Task completed; consumed by Front (INTERACTIVE) |
| `k1.orchestration.task.failed.v1` | Concierge (Back) | Task failed; consumed by Front (INTERACTIVE) |
| `k1.orchestration.task.cancel.v1` | Concierge (Front) | Cancel in-flight task (URGENT) |
| `k1.orchestration.task.suspended.v1` | Concierge (Back) | Task suspended for HITL; consumed by Front (INTERACTIVE) |
| `k1.orchestration.task.resume.v1` | Concierge (Front) | Resume suspended task after HITL (INTERACTIVE) |
| `k1.orchestration.task.accepted.v1` | Concierge (Orchestrator) | Orchestrator accepted TaskEnvelope (INTERACTIVE) |
| `k1.orchestration.findings.ready.v1` | Concierge (Back) | Intermediate findings for Front (INTERACTIVE) |
| `k1.affect.update.v1` | Concierge (Experience) | Affect update from ExperienceLayer (RELAXED/BACKGROUND) |
| `k1.proactive.fill.v1` | Concierge (Experience) | Proactive fill message during idle (RELAXED/BACKGROUND) |
| `k1.internal.weave.batch.v1` | Concierge (WeaveBatcher) | Internal: batched async results for weaving (INTERNAL) |
| `k1.hil.request.v1` | Concierge (Front) | HITL relay to user (INTERACTIVE) |
| `k1.hil.response.v1` | Concierge (Front) | HITL resolve from user answer (INTERACTIVE) |
| `k1.tool.started.v1` | Concierge (Back) | Tool execution started; observability (INTERACTIVE) |
| `k1.tool.completed.v1` | Concierge (Back) | Tool execution completed; observability (INTERACTIVE) |
| `k1.concierge.turn.complete.v1` | Concierge (FSM) | Turn completed; consumed by Memory Writer, Learning Loop (BACKGROUND) |

---

## 7. Bootstrap Sequence (Pseudocode)

```python
# Phase 1: Infrastructure
bus = BusFactory.create_local(backend="auto")
mailbox_router = BusFactory.create_mailbox_router(backend="auto")

# Phase 2: SessionState (needs bus only)
session_events = SessionBusAdapter(bus)
session_manager = SessionStateFactory.create_with_ports(
    session_id=generate_session_id(),
    storage=SQLiteStorageAdapter(db_path=config.db_path),
    events=session_events,
    writer=DirectWriterAdapter(),
    lifecycle=StandaloneLifecycle(
        config=LifecycleConfig(checkpoint_interval_s=config.checkpoint_s)
    ),
    k0_sync=NullSyncPort(),
)

# Phase 3: Fabric (needs bus + session_manager)
fabric_bus = FabricBusAdapter(bus)
state_reader = SessionStateReaderAdapter(session_manager)
fabric = FabricFactory.create_with_ports(
    state_reader=state_reader,
    event_port=fabric_bus,
    delta_bus=fabric_bus,                    # same instance
    bridge=TestBridgeAdapter(),              # Phase 1 stub
    model_gateway=TestModelGatewayAdapter(), # Phase 1 stub
    prompt_system=TestPromptSystemAdapter(), # Phase 1 stub
    production_mode=False,
    contracts_dir=str(config.contracts_dir),
)

# Phase 3.5: Model Hub (needs config + plugins; no bus/fabric/session deps)
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.config import ModelHubConfig
from k1.model_hub.plugins.openai_plugin import OpenAIPlugin
from k1.model_hub.plugins.anthropic_plugin import AnthropicPlugin
from k1.model_hub.plugins.google_plugin import GooglePlugin
from k1.model_hub.plugins.vllm_plugin import VLLMPlugin
from k1.model_hub.plugins.ollama_plugin import OllamaPlugin

model_hub_config = ModelHubConfig.from_dict(config.model_hub_overrides)
model_hub = ModelHubFactory.create_standalone(
    config=model_hub_config,
    plugins={
        "openai": OpenAIPlugin(),
        "anthropic": AnthropicPlugin(),
        "google": GooglePlugin(),
        # Local providers (optional, enabled by config):
        # "vllm": VLLMPlugin(),
        # "ollama": OllamaPlugin(),
    },
)
# model_hub implements IModelHubPort -- single gateway for ALL LLM traffic (MH-16).
# Consumers wrap it in their own adapters:
#   Planner:   LLMGatewayAdapter(model_hub)    -> Planner.ILLMPort
#   Concierge: ModelGatewayAdapter(model_hub)   -> Concierge.ILLMPort
# Model Hub is stateless w.r.t. kernel -- no bus subscriptions, no session writes (MH-01).
# Internal services: RequestRouter (9-step pipeline), BudgetEnforcer ($5/day default),
# CapabilityRouter, ModelSelector, ProviderDispatcher, CircuitBreakerManager, etc.

# Phase 4: Orchestrator (needs bus + fabric + session_manager)
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.workflows.persistence.sqlite_adapter import SQLiteWorkflowAdapter

orch_config = OrchestratorConfig.from_dict(config.orchestrator_overrides)
# NOTE: create_production() calls init() automatically -- returns ready-to-use service.
# Factory kwargs use short names: mailbox, fabric, planner, state, delta, bridge, event, storage.
orchestrator = await OrchestratorFactory.create_production(
    orch_config,
    mailbox=MailboxAdapter(max_depth=orch_config.mailbox_capacity),
    fabric=FabricGatewayAdapter(fabric),                          # wraps Fabric facade from Phase 3
    planner=MockPlannerAdapter(),                                  # Phase 5: replaced with real PlannerAdapter
    state=StateReadAdapter(state_reader),                          # wraps SessionStateReaderAdapter from Phase 3
    delta=DeltaEmitAdapter(fabric_bus, fabric_bus),                # reuses FabricBusAdapter (event_port + delta_bus)
    bridge=MockBridgeAdapter(),                                    # Phase 1 stub; Phase 2: BridgeWriteAdapter(bridge_client)
    event=EventSubscriptionAdapter(fabric_bus),                    # wraps FabricBusAdapter IEventPort from Phase 3
    storage=WorkflowStorageAdapter(SQLiteWorkflowAdapter(orch_config.workflow_db_path)),
)
# orchestrator is now initialized: ports validated, MCP discovered, scheduler started,
# events subscribed, mailbox loop running, admin HTTP server started (if admin_enabled).

# Phase 5: Planner (needs bus + fabric + session_manager)
from k1.planner.factory import PlannerFactory
from k1.planner.config import PlannerConfig
from k1.planner.adapters.llm_gateway_adapter import LLMGatewayAdapter        # Phase 2; use TestLLMAdapter for Phase 1
from k1.planner.adapters.fabric_retrieval_adapter import FabricRetrievalAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter
from k1.planner.adapters.bridge_adapter import BridgeAdapter                  # Phase 2; use TestBridgeAdapter for Phase 1
from k1.planner.adapters.delta_bus_adapter import DeltaBusAdapter
from k1.planner.adapters.event_bus_adapter import EventBusAdapter
from k1.planner.adapters.mailbox_adapter import PlannerMailboxAdapter as PlannerMailbox

planner_config = PlannerConfig.from_dict(config.planner_overrides)  # or PlannerConfig() for defaults
planner = await PlannerFactory.create_production(
    llm_port=TestLLMAdapter(),                                        # Phase 1 stub; Phase 2: LLMGatewayAdapter(model_hub)
    fabric_port=FabricRetrievalAdapter(fabric),                       # wraps Fabric facade from Phase 3
    state_port=SessionStateReadAdapter(state_reader),                 # wraps same SessionStateReaderAdapter
    bridge_port=TestBridgeAdapter(),                                  # Phase 1 stub; Phase 2: BridgeAdapter(bridge_client)
    delta_port=DeltaBusAdapter(fabric_bus),                           # wraps FabricBusAdapter delta bus
    event_port=EventBusAdapter(fabric_bus),                           # wraps FabricBusAdapter event port
    mailbox_port=PlannerMailbox(max_depth=planner_config.mailbox_max_depth),
    config=planner_config,
)
# planner is now wired but NOT started -- start() enters infinite dequeue loop.
# Kernel spawns it as a background task:
planner_task = asyncio.create_task(planner.start())

# Phase 5b: Cross-wire Orchestrator.IPlannerPort with real Planner
from k1.fabric.circuit_breaker.breaker import CircuitBreaker
planner_mailbox = planner.get_mailbox()      # extract Planner's IMailboxPort
cb_planner = CircuitBreaker(
    "CB_PLANNER",
    failure_threshold=orch_config.cb_planner_failure_threshold,
    reset_timeout_s=orch_config.cb_planner_reset_timeout_ms / 1000,
)
planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
orchestrator._planner_port = planner_adapter  # hot-swap MockPlannerAdapter -> real PlannerAdapter

# Phase 5.5: Bridge Client (needs config; connects to K0 backend)
# bridge_client is used by Concierge (IMemoryPort), Orchestrator (IBridgeWritePort),
# and Planner (IBridgePort). Phase 1: None (stubs used). Phase 2: real connection.
from k1.bridge.connector.client import BridgeClient
from k1.bridge.connector.config import BridgeConfig

bridge_config = BridgeConfig.from_dict(config.bridge_overrides)  # host, port, timeout, retry
bridge_client = await BridgeClient.connect(bridge_config)         # Phase 1: None / TestBridgeClient
# bridge_client implements query(), send_command(), subscribe(), close().
# If K0 unreachable: bridge_client = None → adapters fall back to offline stubs.
# Orchestrator bridge=MockBridgeAdapter() (Phase 1) → BridgeWriteAdapter(bridge_client) (Phase 2).
# Planner bridge_port=TestBridgeAdapter() (Phase 1) → BridgeAdapter(bridge_client) (Phase 2).

# Phase 6: Concierge (needs bus + fabric + session + orchestrator + planner)
from k1.concierge.factory import ConciergeFactory
from k1.concierge.config import ConciergeConfig
from k1.concierge.adapters.ws_input import WebSocketInputAdapter
from k1.concierge.adapters.sse_output import SSEOutputAdapter
from k1.concierge.adapters.ultrabert import UltraBERTv4Adapter
from k1.concierge.adapters.model_gateway import ModelGatewayAdapter
from k1.concierge.adapters.session_kernel import SessionKernelAdapter
from k1.concierge.adapters.fabric_orchestrator import FabricOrchestratorAdapter
from k1.concierge.adapters.delta_bus import DeltaBusAdapter as ConciergeDeltaBusAdapter
from k1.concierge.adapters.bridge_recall import BridgeRecallAdapter

concierge_config = ConciergeConfig.from_dict(config.concierge_overrides)
concierge = await ConciergeFactory.create_with_ports(
    input_port=TestInputAdapter(),                                   # Phase 1 stub; Phase 2: WebSocketInputAdapter(ws)
    output_port=TestOutputAdapter(),                                 # Phase 1 stub; Phase 2: SSEOutputAdapter(sse)
    classification_port=MockClassificationAdapter(),                 # Phase 1 stub; Phase 2: UltraBERTv4Adapter()
    llm_port=ModelGatewayAdapter(model_hub),                         # wraps Model Hub; Phase 1: ModelHubPOCBridge(Gemini)
    state_port=SessionKernelAdapter(session_manager),                # wraps SessionState from Phase 2
    dispatch_port=FabricOrchestratorAdapter(fabric, orchestrator),   # routes by tier: LOW->Fabric, MED/HIGH->Orchestrator
    delta_port=ConciergeDeltaBusAdapter(fabric_bus, bus),             # emit events + subscribe deltas via Bus
    memory_port=BridgeRecallAdapter(bridge_client),                  # Phase 1: TestBridgeAdapter; Phase 2: real Bridge
    config=concierge_config,
)
# ConciergeFactory.create_with_ports() internally creates:
#   - ConciergeController (FSM, 12 states)
#   - Front/Back actors with ToolDispatchers (10 Front + 6 Back tools)
#   - ExperienceLayer (6 components: EP, AM, NW, AR, PS, RC)
#   - DeltaAggregator (500ms batch window → FSM.apply_deltas())
#   - HILCoordinator (3 variants: clarification, approval, selection)
#   - WeaveBatcher (async result batching for natural delivery)
#   - OppPipeline (8 primitives, 9 lifecycle hooks)
#   - DynamicPromptBuilder (10 prompt modes, 128K context window)
#   - MutationGuard (3-tier validation for SS writes)
#   - FrontLock (concurrency gate, priority queue)
#   - front/back mailboxes via MailboxRouter
#
# All internal wiring uses only the 8 injected ports -- no direct dependencies.
# Concierge is the ONLY writer to SessionState (ADR-0017, enforced structurally).

# Concierge consumer task (dequeues front/back mailboxes, dispatches to actors):
concierge_task = asyncio.create_task(concierge.start())

# Phase 6.5: Household Projection Hydration (D-14, D-15, D-16)
# Family identity, safety-critical health (allergies), access levels, device registry,
# and household governance are NOT SessionState sections. They live in a frozen
# HouseholdProjection cached in-memory inside Concierge.
# See §126 for the full hydration protocol.
if bridge_client is not None:
    household_snapshot = await bridge_client.query(
        "household.projection.v1",
        params={"session_id": session_manager.session_id},
    )
    # Returns: members[], devices[], governance{}, version
    await concierge.hydrate_household(household_snapshot)
    # Subscribe to live deltas (member added/removed, governance changed, device registered)
    await bridge_client.subscribe(
        "household.delta.v1",
        handler=concierge.apply_household_delta,
    )
else:
    # Offline: load from LOCAL COLD (last known good) — edge-first (D-15)
    await concierge.hydrate_household_from_local_cold()
    # Flag: projection_stale = True → Concierge works fine but warns on safety-sensitive ops

# Phase 7: Start lifecycle
session_manager.start()

# Phase 8: Expose kernel API
return KernelRuntime(bus=bus, mailbox_router=mailbox_router,
                     session=session_manager, fabric=fabric,
                     orchestrator=orchestrator, planner=planner,
                     model_hub=model_hub, concierge=concierge,
                     bridge=bridge_client)
```

---

## 8. Shutdown Sequence

```
1. concierge.stop()           -- flush DeltaAggregator, cancel FrontLock queue, stop WeaveBatcher, teardown FSM, unsubscribe all bus topics, log dead-letter summary
2. concierge_task.cancel()    -- cancel the background asyncio task spawned in Phase 6
3. orchestrator.shutdown()    -- stop admin HTTP, drain active DAG (30s), stop scheduler, unsubscribe events, persist trigger states, cancel loops
4. planner.stop()             -- set _running=False, drain mailbox (emit plan.cancelled for each), cancel in-flight plan (grace period), unsubscribe 4 events, log shutdown.complete
5. planner_task.cancel()      -- cancel the background asyncio task spawned in Phase 5
6. model_hub.close()          -- close all provider plugins (await plugin.close()), flush metrics, stop rate limiter, clear response cache, log shutdown summary
7. fabric.shutdown()          -- drain pending executions
8. session_manager.stop()     -- final checkpoint, flush events
9. bus.close()                -- drain subscribers, close ring buffer
10. mailbox_router.close()    -- drain all mailboxes
```

Order matters: consumers shut down before infrastructure.
Concierge is a consumer of Orchestrator (via IDispatchPort), Fabric (via IDispatchPort LOW tier), SessionState (via IStatePort), Bus (via IDeltaPort), and Model Hub (via ILLMPort).
Orchestrator is a consumer of Planner (via PlannerAdapter).
Planner is a consumer of Fabric (via FabricRetrievalAdapter), Bus (via EventBusAdapter), and Model Hub (via ILLMPort → LLMGatewayAdapter).
Model Hub is stateless infrastructure -- no upstream consumers to drain, but plugins hold connections to external APIs.
Fabric is a consumer of SessionState.

---

## 9. Event Flow Examples

### 9.1 Agent Delta (Fabric -> Bus -> any subscriber)

```
AgentProvider.execute()
  --> fabric.delta_bus.emit_delta("agent-1", "state_update", "beliefs", {...})
  --> FabricBusAdapter.emit_delta()
  --> bus.publish(Envelope(topic="k1.agent.agent-1.delta.v1", payload=json))
  --> trie match --> deliver to all subscribers on "k1.agent.agent-1.delta.v1"
                     or wildcard "k1.agent.*.delta.v1"
```

### 9.2 Session Mutation Event (SessionState -> Bus -> Fabric)

```
session_manager.mutate(section="cognitive", ...)
  --> events.emit("mutation_applied", {section, operation, bytes_delta, ...})
  --> SessionBusAdapter.emit()
  --> bus.publish(Envelope(topic="k1.session.mutation_applied", payload=json))
  --> trie match --> Fabric subscriber (if subscribed to k1.session.*)
```

### 9.3 Fabric reads SessionState (direct, no bus)

```
fabric.execute(capability_request)
  --> state_reader.read_section(session_id, "affective_now")
  --> SessionStateReaderAdapter.read_section()
  --> session_manager.read_section(session_id, "affective_now")
  --> returns Dict[str, Any]
```

### 9.4 TaskEnvelope -> Orchestrator -> Planner -> DAG -> Fabric (full path)

```
Concierge enqueues TaskEnvelope to Orchestrator mailbox
  --> MailboxAdapter.enqueue(envelope, "INTERACTIVE")
  --> _mailbox_loop() dequeues
  --> OrchestratorService.process(envelope)
  --> PlannerAdapter.request_plan(PlanRequest)
  --> Bus.publish(Envelope(topic="k1.planner.plan_request.v1", ...))
  --> Planner receives, produces CommittedPlan
  --> Bus.publish(Envelope(topic="k1.planner.plan.ready.v1", ...))
  --> EventSubscriptionAdapter handler fires
  --> CommittedPlan enqueued to Orchestrator mailbox
  --> DAGExecutor.execute(plan, snapshot)
  --> StepRunner.execute(step)
  --> FabricGatewayAdapter.execute(CapabilityRequest)
  --> Fabric.execute(request)
  --> returns CapabilityResult
  --> AggregatedResult emitted as dag.completed.v1
```

### 9.5 Orchestrator delta -> Bus -> Concierge

```
DAGExecutor completes a step
  --> DeltaEmitAdapter.emit("k1.orchestration.step.completed.v1", payload, trace_id)
  --> FabricBusAdapter.emit(topic, payload)  [internal event bus]
  --> FabricBusAdapter.emit_delta("orchestrator", ...)  [user-facing delta stream]
  --> Bus delivers to all subscribers on matching topics
  --> Concierge receives delta, streams to user
```

### 9.6 Planner plan.ready -> Bus -> Orchestrator (inbound event path)

```
Planner completes planning for request_id "r-42"
  --> Bus.publish(Envelope(topic="k1.planner.plan.ready.v1", payload={request_id, plan}))
  --> trie match --> EventSubscriptionAdapter handler (Orchestrator subscribed at init step 8)
  --> handler calls MailboxAdapter.enqueue(CommittedPlan, "INTERACTIVE")
  --> _mailbox_loop() dequeues CommittedPlan
  --> OrchestratorService._process_one(CommittedPlan)
  --> matches pending_plans[request_id]
  --> StateReadAdapter.read_section(session_id, "cognitive") -> SessionSnapshot
  --> DAGExecutor.execute(committed_plan, snapshot)
  --> waves execute steps via StepRunner -> FabricGatewayAdapter -> Fabric
  --> AggregatedResult assembled
  --> DeltaEmitAdapter.emit("k1.orchestration.dag.completed.v1", result, trace_id)
```

### 9.7 Planner Internal Pipeline (PlanRequest -> 4-stage pipeline -> plan.ready)

```
PlannerAgent._run_loop() blocks on mailbox.dequeue()
  --> PlanRequest arrives (enqueued by EventBusAdapter subscription handler)
  --> Cancel pre-check: request_id in _cancel_set? Yes -> emit plan.cancelled.v1, skip
  --> Acquire _plan_lock (V1 single-plan exclusion)
  --> _in_flight_request_id = request.request_id
  --> PipelineController.execute(request, cancel_check)
      |
      |-- DeltaBusAdapter.emit(DeltaPayload(stage="SKETCH", status="STARTED"))
      |-- Stage 1: SketchService.execute(request, state_snapshot, cancel_check)
      |     --> ILLMPort.generate(sketch_prompt) -> raw sketch
      |     --> ToolCallRouter dispatches tool calls (IFabricRetrievalPort, IStateReadPort, IBridgePort)
      |     --> HILCoordinator: if ambiguous -> emit k1.hil.clarification.v1, await response
      |     --> returns SketchResult(intent_graph, capabilities_needed, tool_results)
      |
      |-- Cancel checkpoint #2: cancel_check() -> if True, raise PlanCancelledError
      |-- DeltaBusAdapter.emit(DeltaPayload(stage="EXPAND", status="STARTED"))
      |-- Stage 2: ExpandService.execute(sketch_result, cancel_check)
      |     --> ILLMPort.generate(expand_prompt) -> expanded steps
      |     --> ToolCallRouter: additional discovery/refinement tool calls
      |     --> returns ExpandResult(steps, dependencies, resource_estimates)
      |
      |-- Cancel checkpoint #3: cancel_check() -> if True, raise PlanCancelledError
      |-- DeltaBusAdapter.emit(DeltaPayload(stage="VALIDATE", status="STARTED"))
      |-- Stage 3: ValidateService.execute(expand_result, cancel_check)
      |     --> Deterministic checks (dependency cycles, resource bounds, safety band)
      |     --> ILLMPort.generate(arbiter_prompt) -> LLM arbiter verdict
      |     --> HILCoordinator: if high-risk -> emit k1.hil.approval_request.v1, await response
      |     --> IFabricRetrievalPort.discover_capabilities() -> verify all steps resolvable
      |     --> returns ValidateResult(approved, issues, arbiter_verdict)
      |
      |-- Cancel checkpoint #4: cancel_check() -> if True, raise PlanCancelledError
      |-- DeltaBusAdapter.emit(DeltaPayload(stage="COMMIT", status="STARTED"))
      |-- Stage 4: CommitService.execute(validate_result)  [NO ILLMPort -- PLAN-03]
      |     --> IBridgePort.persist_plan(frozen_plan) -> fire-and-forget to K0
      |     --> IDeltaEmitPort.emit(DeltaPayload(stage="COMMIT", status="COMPLETED"))
      |     --> IEventPort.emit("k1.planner.plan.ready.v1", {request_id, committed_plan})
      |     --> returns CommittedPlan
      |
  --> PipelineController returns CommittedPlan to PlannerAgent
  --> _in_flight_request_id = None
  --> pipeline.reset() -> FSM back to IDLE
  --> _plan_lock.release()
  --> Loop back to mailbox.dequeue()

Error path:
  --> Any stage raises PlannerError
  --> PipelineController catches, emits plan.failed.v1 via IEventPort
  --> DeltaBusAdapter.emit(DeltaPayload(stage=current, status="FAILED"))
  --> PlannerAgent logs, resets pipeline, releases lock, continues loop

Cancel path:
  --> cancel_check() returns True at any checkpoint
  --> PipelineController raises PlanCancelledError
  --> PlannerAgent emits plan.cancelled.v1 via IEventPort
  --> Resets pipeline, releases lock, continues loop
```

### 9.8 Concierge LOW Tier: User Input -> Front -> Back -> Fabric -> Response

```
User sends "What's the weather in Mumbai?"
  --> IInputPort.receive() -> UserMessage
  --> FSM LISTENING -> ACKING
  --> IClassificationPort.classify(text) -> ClassificationResult(tier=LOW, domain=weather, safety=GREEN)
  --> IStatePort.write("control", classification_result)
  --> IStatePort.write("scoreboard", intents + entities)
  --> Bus.publish(Envelope(topic="k1.session.user.input.v1", payload))
  --> Front actor receives (subscribed via IDeltaPort)
  --> Front ReAct loop iteration 1: acknowledge() tool call
  --> IOutputPort.send(ack_event) -> k1.response.ack.v1
  --> Front ReAct iteration 2: recall_memory() via IMemoryPort.recall()
  --> Front ReAct iteration 3: update_beliefs() via IStatePort.write("beliefs_active", ...)
  --> Front ReAct iteration 4: dispatch_task(intents=[weather_lookup])
  --> FSM ACKING -> DISPATCHING
  --> Bus.publish(Envelope(topic="k1.orchestration.task.dispatch.v1", payload))
  --> Back actor receives via back mailbox
  --> Back ReAct iteration 1: discover_capabilities() via IDispatchPort -> Fabric
  --> Back ReAct iteration 2: invoke_capability("weather_lookup") via IDispatchPort.dispatch_direct(CapReq)
  --> Fabric.execute(request) -> CapabilityResult(temperature=32C, ...)
  --> Back ReAct iteration 3: submit_result(result_type="complete", data={...})
  --> Bus.publish(Envelope(topic="k1.orchestration.task.complete.v1", payload))
  --> Front actor receives task.complete
  --> FSM DISPATCHING -> DELIVERING
  --> Front generates natural language response with results
  --> IOutputPort.send(final_event) -> k1.response.final.v1
  --> FSM DELIVERING -> LISTENING
```

### 9.9 Concierge MEDIUM Tier: User Input -> Front -> Orchestrator -> Fabric -> Weave

```
User sends "Book a table at Taj and create a calendar event"
  --> IInputPort.receive() -> UserMessage
  --> IClassificationPort.classify() -> ClassificationResult(tier=MEDIUM, intents=2)
  --> FSM LISTENING -> ACKING -> DISPATCHING
  --> Front dispatches: dispatch_task(intents=[restaurant_booking, calendar_create])
  --> IDispatchPort.dispatch_envelope(TaskEnvelope(tier=MEDIUM, intents=[...]))
  --> OrchestratorService.mailbox.enqueue(envelope)
  --> FSM DISPATCHING -> COMPANIONING (Front can accept new user input)
  --> Orchestrator processes: 2 Fabric calls (sequential per MEDIUM rules)
  --> FabricGatewayAdapter.execute(restaurant_booking_request) -> CapabilityResult
  --> FabricGatewayAdapter.execute(calendar_create_request) -> CapabilityResult
  --> DeltaEmitAdapter.emit("k1.orchestration.dag.completed.v1", AggregatedResult)
  --> IDeltaPort subscription handler fires in Concierge
  --> DeltaAggregator batches (500ms window)
  --> If Front is busy (FrontLock.busy=True):
        WeaveBatcher queues result
        On FrontLock release: WeaveBatcher.flush() -> Front receives batched results
  --> FSM COMPANIONING -> WEAVING (if pending_results)
  --> Front generates weave response: addresses user's topic first, then presents results
  --> IOutputPort.send(final_event)
  --> FSM WEAVING -> LISTENING (queue drained)
```

### 9.10 Concierge HITL Flow: Back Suspends -> Front Translates -> User Answers -> Back Resumes

```
Back executing invoke_capability("hotel_booking")
  --> Back detects: missing required param "checkout_date"
  --> submit_result(result_type="needs_human", hil_type="clarification", question="When do you check out?")
  --> Bus.publish(Envelope(topic="k1.orchestration.task.suspended.v1", payload))
  --> FSM -> CLARIFYING_WORKER
  --> Front receives task.suspended via IDeltaPort subscription
  --> Front translates to natural language: "I'd love to help book that! When are you checking out?"
  --> IOutputPort.send(clarification_event) -> k1.response.clarification.v1
  --> User responds: "Sunday the 15th"
  --> IInputPort.receive() -> UserMessage
  --> Front parses answer, emits: Bus.publish(topic="k1.orchestration.task.resume.v1", resolution={checkout_date: "2026-06-15"})
  --> FSM CLARIFYING_WORKER -> PROGRESSING
  --> Back resumes from ReAct message history with resolution
  --> Back retries invoke_capability("hotel_booking", {checkin: ..., checkout: "2026-06-15"})
  --> Back: submit_result(result_type="complete", data={confirmation_number: ...})
  --> Bus.publish(topic="k1.orchestration.task.complete.v1")
  --> FSM -> DELIVERING -> Front presents result -> LISTENING
```

### 9.11 Concierge HIGH Tier: Front -> Orchestrator -> Planner -> DAG -> Agents via Fabric

```
User sends "Plan a weekend trip to Goa for the family — flights, hotel, and activities"
  --> IInputPort.receive() -> UserMessage
  --> IClassificationPort.classify() -> ClassificationResult(tier=HIGH, domain=travel, intents=3)
  --> FSM LISTENING -> ACKING -> DISPATCHING
  --> Front dispatches: dispatch_task(intents=[flight_search, hotel_booking, activity_planner])
  --> Bus.publish(Envelope(topic="k1.orchestration.task.dispatch.v1", payload))

FSM._on_task_dispatch():
  --> route_task_sync(dispatch, tier=HIGH) -> DispatchRecord
        Budget: max_fabric_calls=10, max_planner_tokens=3500, timeout from config
  --> PassthroughPlannerStub wraps as 1-step committed plan (M10 E10.3.2)
        committed_plan = {task_id, steps: [{intent, step_id}]}
  --> Re-route as MEDIUM → asyncio.create_task(_run_medium_orchestration(TaskEnvelope))
  --> Inject reference_context from scoreboard (Gap 6: pronoun resolution)
  --> Inject narrative_thread from narrative_active (Gap 5: context drift prevention)

OrchestratorStub.handle_task(TaskEnvelope):
  --> Step 1: emit k1.orchestration.task.accepted
  --> Step 2: state_read.snapshot(["beliefs_active", "task_artifacts"]) -> context
  --> Step 3: CapabilityRequest(name=envelope.intent, params=context)
  --> Step 4: fabric_gateway.execute(cap_request) → budget check via _check_budget()
        |
        |  Fabric 9-step pipeline:
        |  1. emit k1.capability.invoked.v1
        |  2. Resolve provider (Registry -> Policy -> Selector)
        |  3. Build ExecutionContext (SessionState + prompts + budget)
        |  4. ProviderFactory instantiates by ProviderType
        |     |
        |     |--> ProviderType.AGENT → AgentProvider.execute()
        |     |      AgentFactory.spawn_and_execute():
        |     |        Step 1: Load AgentContract via contract_loader
        |     |        Step 2: Create MPSC Mailbox (WFQ INTERACTIVE priority)
        |     |        Step 3: Grant LLM access via IModelGatewayPort.create_handle(budget_tokens)
        |     |        Step 4: Grant SessionState read (scoped to declared sections)
        |     |        Step 5: Scope tool access via ToolScope (from contract.tools_granted)
        |     |        Step 6: Build ExecutionContext via ContextBuilder
        |     |        Step 7: Instantiate Agent (lifecycle: PENDING → WARMING → ACTIVE)
        |     |        Step 8: Agent.execute(params) → result
        |     |        Agent emits deltas via DeltaEmitter → IDeltaBusPort (500ms batch, LWW merge)
        |     |        On success: AgentPool.put(agent) → IDLE (60s TTL, FIFO reuse)
        |     |      Returns AgentResult → CapabilityResult
        |     |
        |     |--> ProviderType.BRIDGE → BridgeProvider.execute() (K0 tools)
        |     |--> ProviderType.MCP → MCPProvider.execute() (external tools)
        |     |--> ProviderType.WORKFLOW → WorkflowProvider.execute()
        |     |
        |  5. Execute via CircuitBreaker (timeout FAB-04)
        |  6. Validate output (3-tier: structural → schema → semantic)
        |  7. emit k1.capability.completed.v1 or k1.capability.failed.v1
        |
  --> Step 5: AggregatedResult.from_medium(capability_result)
  --> Step 6: emit k1.orchestration.dag.completed

FSM._on_dag_completed():
  --> Normalize to k1.orchestration.task.complete.v1
  --> FSM routing: if FrontLock.busy → WeaveBatcher.on_task_complete(result)
        |
        WeavePolicy.decide(WeaveSignal) using 6 signal categories:
          1. FSM state (COMPANIONING, LISTENING, etc.)
          2. Urgency profile (pending urgency counts + has_critical)
          3. User activity (typing? idle_ms?)
          4. Queue depth (pending_count)
          5. Affect band (emotional gate: OPEN, SUPPRESS_TRIVIAL, SUPPRESS_ALL_NON_SAFETY)
          6. Backpool utilization + HITL pending
        → WeaveDecision: IMMEDIATE | BATCH(200-5000ms) | DEFER | DIGEST(10-30s) | SUPPRESS
        |
  --> On FrontLock release: WeaveBatcher.flush() → deliver batched results
  --> FSM → WEAVING → Front generates weave response → DELIVERING → LISTENING

HITL branch (if capability has side_effects or safety_band >= AMBER):
  --> HILCoordinator.handle_needs_human(task_id, hil_type, question, safety_band, ...)
        Safety band escalation: GREEN + side_effects → AMBER
        Suspension limits: check max_rounds (default 2)
        TrustAccumulator: if trust >= 0.85 AND risk="low" → auto_approve (skip HITL)
  --> on_emit_suspended() → Bus.publish(task.suspended)
  --> FSM → CLARIFYING_USER or CLARIFYING_WORKER
  --> User responds → HILPipeline.process_approval_response()
        Decisions: approve | approve+mods | modify+mods (re-present) | cancel
  --> on_emit_resume() → Bus.publish(task.resume)
  --> Back resumes with resolution
  --> TrustAccumulator.record(outcome) → adjusts future auto-approve threshold
```

### 9.12 Specialized Agent Invocation via Fabric

```
OrchestratorStub (or DAG executor) invokes capability "agent.execute.empathy_writer"
  --> Fabric.execute(CapabilityRequest("agent.execute.empathy_writer", params))

  Step 1: CapabilityRegistry resolves contract for "agent.execute.empathy_writer"
  Step 2: ProviderMatcher finds AgentProvider (ProviderType.AGENT)
  Step 3: ProviderSelector picks best available provider (circuit breaker, affinity)

  AgentProvider.execute(request, context, trace_id):
    --> AgentFactory.spawn_and_execute(request, context, trace_id)

    Pool check: AgentPool.get("empathy_writer")
      --> If IDLE agent available: reactivate (IDLE → ACTIVE), skip steps 1-7
      --> If not: spawn fresh agent (8 steps below)

    Step 1: Load AgentContract("empathy_writer")
              - Declared sections: ["affective_now", "persona"]
              - tools_granted: ["memory_recall", "tone_suggest"]
              - llm_budget_tokens: 2000
    Step 2: Create MPSC mailbox (WFQ INTERACTIVE priority)
    Step 3: IModelGatewayPort.create_handle(budget_tokens=2000) → ILLMHandle
    Step 4: SessionState reader scoped to ["affective_now", "persona"] only
              # Family identity (name, role, allergies) comes from HouseholdProjection (§126), not SS
    Step 5: ToolScope enforces only ["memory_recall", "tone_suggest"] callable
    Step 6: ContextBuilder assembles ExecutionContext
    Step 7: Agent instantiated (PENDING → WARMING → ACTIVE)

    Agent.execute(params):
      --> LLM generation with budget (via ILLMHandle)
      --> Tool calls filtered by ToolScope
      --> State deltas emitted (NEVER writes SS directly):
            DeltaEmitter.queue(AgentDelta(section, key, value))
            500ms batch window, LWW merge on (section, key) collisions
            Flush → IDeltaBusPort → Delta Bus → Concierge → MutationGuard → SessionState

    On success:
      --> AgentPool.put(agent) → IDLE (60s TTL)
      --> AgentPool: max 5 per contract, FIFO reuse, TTL sweep eviction
      --> Return CapabilityResult to Fabric

  Fabric pipeline continues:
    --> Validate result (structural → schema → semantic)
    --> emit k1.capability.completed.v1 with metrics
    --> emit k1.fabric.learning.signal.v1 (capability quality feedback)
    --> Return CapabilityResult to OrchestratorStub

Agent Lifecycle FSM:
  PENDING → WARMING → ACTIVE → IDLE (pooled, 60s TTL)
                              → DRAINING → TERMINATED

Invariants:
  - FAB-01: Agent NEVER writes SessionState directly (deltas only)
  - FAB-07: ToolScope enforced on ALL tool invocations
  - Agent deltas flow: Agent → DeltaEmitter → Delta Bus → Concierge MutationGuard → SS
```

---

## 10. Validation Checklist

Use this when implementing the bootstrap. Each row must pass before kernel
is considered wired.

| # | Check | How to Verify | Status |
|---|-------|---------------|--------|
| W-01 | Bus starts clean | `bus.stats.published == 0` after create | [ ] |
| W-02 | SessionBusAdapter satisfies ABC | `isinstance(session_events, IEventPort)` | [ ] |
| W-03 | FabricBusAdapter satisfies Protocol | Fabric factory accepts without error | [ ] |
| W-04 | StateReader wraps real manager | `state_reader.read_section(sid, "cognitive") is not None` after `session.start()` | [ ] |
| W-05 | Session events flow through bus | Subscribe to `k1.session.*`, mutate, assert handler called | [ ] |
| W-06 | Fabric deltas flow through bus | Subscribe to `k1.agent.*.delta.v1`, execute agent, assert | [ ] |
| W-07 | Fabric can read session state | Execute capability that reads `affective_now`, assert data | [ ] |
| W-08 | Shutdown order correct | Stop orchestrator, stop planner, stop fabric, stop session, close bus -- no errors | [ ] |
| W-09 | No circular imports | `python -c "from k1.kernel.bootstrap import KernelRuntime"` succeeds | [ ] |
| W-10 | All 172 Rust + 1005 Python bus tests still pass | `cargo test` + `pytest tests/k1/bus/` | [ ] |
| W-11 | Orchestrator factory completes < 500ms | `time OrchestratorFactory.create_production(config)` | [ ] |
| W-12 | All 8 Orchestrator ports + admin injected | All 8 core ports non-None + _admin set if admin_enabled after factory | [ ] |
| W-13 | FabricGatewayAdapter wraps real Fabric | `adapter.execute(request)` returns valid CapabilityResult | [ ] |
| W-14 | StateReadAdapter reads real SessionState | `adapter.read_section(sid, "cognitive") is not None` after session.start() | [ ] |
| W-15 | EventSub receives events through Bus | Subscribe to `k1.planner.plan.ready.v1`, fire event via Bus, assert handler called | [ ] |
| W-16 | DeltaEmit events visible on Bus | emit via DeltaEmitAdapter, subscribe on Bus, assert received | [ ] |
| W-17 | Orchestrator processes TaskEnvelope E2E | enqueue -> mailbox -> process -> dag events emitted on Bus | [ ] |
| W-18 | Shutdown order correct (Orch before Planner before Fabric) | Stop orchestrator, stop planner, stop fabric, stop session, close bus -- no errors | [ ] |
| W-19 | No Orchestrator circular imports | `python -c "from k1.orchestrator.factory import OrchestratorFactory"` succeeds | [ ] |
| W-20 | Orchestrator health ready after init | `orchestrator.health_ready() == True` after init() completes | [ ] |
| W-21 | Planner factory completes < 500ms | `time PlannerFactory.create_production(...)` | [ ] |
| W-22 | All 7 Planner ports injected | All 7 port slots non-None after factory returns | [ ] |
| W-23 | Planner ready after start | `planner.ready() == True` after `start()` sets `_running = True` | [ ] |
| W-24 | Planner health reports correctly | `planner.health()` returns `HealthStatus` with `running=True` | [ ] |
| W-25 | Planner receives plan.request via Bus | Publish to `k1.planner.plan.request.v1`, assert Planner handler fires | [ ] |
| W-26 | Planner emits plan.ready via Bus | Complete a plan, subscribe to `k1.planner.plan.ready.v1`, assert event received | [ ] |
| W-27 | Planner stop() drains mailbox cleanly | Enqueue requests, call `planner.stop()`, assert `plan.cancelled.v1` emitted for each | [ ] |
| W-28 | No Planner circular imports | `python -c "from k1.planner.factory import PlannerFactory"` succeeds | [ ] |
| W-29 | Orchestrator IPlannerPort hot-swapped | After Phase 5b cross-wiring, `orchestrator._planner_port` is `PlannerAdapter` (not Mock) | [ ] |
| W-30 | Planner get_mailbox() returns IMailboxPort | `planner.get_mailbox()` returns the injected mailbox_port instance | [ ] |
| W-31 | Concierge factory completes < 500ms | `time ConciergeFactory.create_with_ports(...)` | [ ] |
| W-32 | All 8 Concierge ports injected | All 8 port slots non-None after factory returns | [ ] |
| W-33 | Concierge FSM starts in LISTENING | `concierge.fsm.state == LISTENING` after `start()` | [ ] |
| W-34 | Concierge IStatePort reads real SessionState | `state_port.read(["cognitive"])` returns data after `session.start()` | [ ] |
| W-35 | Concierge IStatePort writes via MutationGuard | `state_port.write("beliefs_active", op, data)` succeeds; verify section updated | [ ] |
| W-36 | Concierge IDispatchPort LOW routes to Fabric | `dispatch_port.dispatch_direct(CapReq)` returns valid CapabilityResult from real Fabric | [ ] |
| W-37 | Concierge IDispatchPort MED routes to Orchestrator | `dispatch_port.dispatch_envelope(TaskEnv)` enqueues to Orchestrator mailbox | [ ] |
| W-38 | Concierge IDeltaPort receives bus events | Subscribe to `k1.orchestration.task.complete.v1`, emit via Bus, assert Concierge handler called | [ ] |
| W-39 | Concierge ILLMPort calls real Model Hub | `llm_port.execute(HubRequest)` returns HubResponse via ModelGatewayAdapter | [ ] |
| W-40 | Concierge IMemoryPort recalls via Bridge | `memory_port.recall(query)` returns MemoryResult (stub or real) | [ ] |
| W-41 | Concierge Front actor processes user.input | Publish `k1.session.user.input.v1`, assert Front ReAct loop invoked | [ ] |
| W-42 | Concierge Back actor processes task.dispatch | Publish `k1.orchestration.task.dispatch.v1`, assert Back ReAct loop invoked | [ ] |
| W-43 | Concierge HITL flow round-trips | Trigger HITL suspension, provide user answer, assert task resumes | [ ] |
| W-44 | Concierge Weave merges async results | Complete task while Front busy, assert WeaveBatcher delivers after FrontLock release | [ ] |
| W-45 | Concierge shutdown drains cleanly | `concierge.stop()` flushes DeltaAggregator, unsubscribes bus topics, no errors | [ ] |
| W-46 | No Concierge circular imports | `python -c "from k1.concierge.factory import ConciergeFactory"` succeeds | [ ] |
| W-47 | Concierge single-writer enforced | Only Concierge's IStatePort has write access; Orchestrator/Planner have read-only adapters | [ ] |
| W-48 | Model Hub factory completes < 200ms | `time ModelHubFactory.create_standalone(config, plugins)` | [ ] |
| W-49 | All 7 Model Hub ports satisfied | IModelHubPort, IEventPort, IStateReadPort, IMetricsPort, IConfigPort, ICredentialPort, IHealthPort non-None after factory | [ ] |
| W-50 | Model Hub implements IModelHubPort | `isinstance(model_hub, IModelHubPort)` is True | [ ] |
| W-51 | BudgetEnforcer active on startup | `model_hub.execute(HubRequest(...))` with budget=0 raises `BudgetExceededError` (MH-04) | [ ] |
| W-52 | RequestRouter processes E2E | `model_hub.execute(HubRequest(capability=CHAT, ...))` returns HubResponse via full 9-step pipeline | [ ] |
| W-53 | Provider plugins initialize | Each registered plugin `supports(capability)` returns True for declared capabilities | [ ] |
| W-54 | Circuit breaker per provider | `circuit_mgr.get_state(provider_id)` returns CLOSED after startup | [ ] |
| W-55 | Model Hub NEVER writes session state | No IStateWritePort in Model Hub dependency graph (MH-01) | [ ] |
| W-56 | No Model Hub circular imports | `python -c "from k1.model_hub.factory import ModelHubFactory"` succeeds | [ ] |
| W-57 | Planner LLMGatewayAdapter wraps real Model Hub | `planner_llm_port.execute(req)` delegates to `model_hub.execute(req)` | [ ] |
| W-58 | Concierge ModelGatewayAdapter wraps real Model Hub | `concierge_llm_port.execute(req)` delegates to `model_hub.execute(req)` | [ ] |
| W-59 | Model Hub shutdown drains cleanly | `model_hub.close()` closes all plugins, flushes metrics, no errors | [ ] |
| W-60 | All 1010 Model Hub tests pass | `pytest tests/k1/model_hub/ -q` | [ ] |

---

## 11. Open Questions

| # | Question | Decision | ADR |
|---|----------|----------|-----|
| Q-01 | Should FabricBusAdapter use JSON or FlatBuffers for event serialization? | JSON for now (human-readable, debuggable). FlatBuffers when perf requires. | -- |
| Q-02 | Should Kernel own the session_id or receive it from outside? | TBD -- depends on multi-session support. | -- |
| Q-03 | When do we replace test stubs (Bridge, ModelGateway, PromptSystem) with real adapters? | After kernel bootstrap is proven with stubs. One adapter at a time. | -- |
| Q-04 | Does the MailboxRouter need to be wired to Fabric agents? | Yes -- each agent could have a dedicated mailbox for ordered delivery. Not wired yet. | -- |
| Q-05 | How does K0 enter the picture? | Via `IBridgePort` (Fabric) and `IK0SyncPort` (SessionState). Stubs until Bridge is live. | -- |
| Q-06 | Is a single Bus instance shared or do we need isolated bus domains? | Single shared bus with topic namespacing. Revisit if topic collision risk grows. | -- |
| Q-07 | When does Concierge bootstrap move from monolith to ConciergeFactory? | After M10 (Integration & Hardening). Current `k1/concierge/kernel/bootstrap.py` is the Phase 1 monolith; `ConciergeFactory` is the production target. | -- |
| Q-08 | Should Concierge IStatePort be split into IStateReadPort + IStateWritePort? | No for now — Concierge is the ONLY writer (ADR-0017), so a combined bidirectional port is cleaner. Revisit if another component ever needs write access. | -- |
| Q-09 | How does Concierge Front/Back actor mailbox wiring work with MailboxRouter? | Concierge creates its own front/back mailboxes via MailboxRouter. These are Concierge-internal; the kernel does not manage them. | -- |
| Q-10 | Does the Concierge need a direct Planner port? | No — Concierge talks to Planner indirectly via IDispatchPort → Orchestrator → IPlannerPort. No direct coupling. | -- |

---

## 12. File Locations Reference

| What | Path |
|------|------|
| Bus factory | `k1/bus/factory.py` |
| Bus ports | `k1/bus/ports/bus.py`, `k1/bus/ports/mailbox.py` |
| FabricBusAdapter | `k1/bus/adapters/fabric_adapter.py` |
| SessionBusAdapter | `k1/bus/adapters/session_adapter.py` |
| Fabric factory | `k1/fabric/factory.py` |
| Fabric ports | `k1/fabric/ports/*.py` (6 files) |
| Fabric adapters | `k1/fabric/adapters/*.py` (12 files) |
| SessionStateReaderAdapter | `k1/fabric/adapters/sessionstate_reader.py` |
| SessionState factory | `k1/sessionstate/factory.py` |
| SessionState ports | `k1/sessionstate/ports/*.py` (5 files) |
| SessionState adapters | `k1/sessionstate/adapters/*.py` (5 files) |
| Orchestrator factory | `k1/orchestrator/factory.py` |
| Orchestrator config | `k1/orchestrator/config.py` |
| Orchestrator types | `k1/orchestrator/types.py` |
| Orchestrator events | `k1/orchestrator/events.py` |
| Orchestrator ports | `k1/orchestrator/ports/*.py` (9 files: 8 core + admin_port.py) |
| Orchestrator adapters | `k1/orchestrator/adapters/*.py` (17 files: 8 prod + 8 test + admin_http_adapter.py) |
| IAdminPort protocol | `k1/orchestrator/ports/admin_port.py` |
| AdminHttpAdapter | `k1/orchestrator/adapters/admin_http_adapter.py` |
| Orchestrator services | `k1/orchestrator/orchestration/*.py` |
| DAGExecutor | `k1/orchestrator/orchestration/dag_executor.py` |
| StepRunner | `k1/orchestrator/orchestration/step_runner.py` |
| Guards | `k1/orchestrator/orchestration/guards/*.py` |
| WorkflowEngine | `k1/orchestrator/workflows/workflow_engine.py` |
| WorkflowRegistry | `k1/orchestrator/workflows/registry.py` |
| WorkflowCompiler | `k1/orchestrator/workflows/compiler.py` |
| WorkflowScheduler | `k1/orchestrator/workflows/scheduler.py` |
| ProactiveGapDetector | `k1/orchestrator/workflows/gap_detector.py` |
| ConnectorLifecycleManager | `k1/orchestrator/connectors/connector_lifecycle.py` |
| MCPToolDiscovery | `k1/orchestrator/connectors/mcp_discovery.py` |
| MCPRegistrationBridge | `k1/orchestrator/connectors/mcp_registration.py` |
| ErrorRouter | `k1/orchestrator/orchestration/error_router.py` |
| ConcurrencyGuard | `k1/orchestrator/orchestration/guards/concurrency_guard.py` |
| Kernel bootstrap (TODO) | `k1/kernel/bootstrap.py` |
| This document | `k1/kernel/kernel.md` |
| Planner factory | `k1/planner/factory.py` |
| Planner config | `k1/planner/config.py` |
| Planner types | `k1/planner/types.py` |
| Planner events | `k1/planner/events.py` |
| Planner ports | `k1/planner/ports/*.py` (7 files) |
| Planner adapters (production) | `k1/planner/adapters/*.py` (7 files: mailbox, llm_gateway, fabric_retrieval, session_state, bridge, delta_bus, event_bus) |
| Planner adapters (test) | `tests/k1/planner/adapters/*.py` (7 test adapters) |
| PlannerAgent | `k1/planner/planner_agent.py` |
| PipelineController | `k1/planner/pipeline_controller.py` |
| Stage services | `k1/planner/stages/*.py` (4 files: sketch, expand, validate, commit) |
| Leaf services | `k1/planner/services/*.py` (tool_call_router, hil_coordinator) |
| Concierge architecture spec | `k1/concierge/concierge.mmd` |
| Concierge POC architecture | `poc/k1_poc/concierge_poc_architecture.mmd` |
| Concierge factory (TODO) | `k1/concierge/factory.py` |
| Concierge config | `k1/concierge/config/` (shimmed to `poc.k1_poc.config`) |
| Concierge bootstrap (Phase 1 monolith) | `k1/concierge/kernel/bootstrap.py` |
| Concierge kernel runner | `k1/concierge/kernel/runner.py` |
| Concierge FSM controller | `k1/concierge/fsm/controller.py` |
| Concierge FSM states | `k1/concierge/fsm/states.py` |
| Concierge FSM transition table | `k1/concierge/fsm/transition_table.py` |
| Concierge FSM FrontLock | `k1/concierge/fsm/front_lock.py` |
| Concierge FSM dead letter | `k1/concierge/fsm/dead_letter_consumer.py` |
| Concierge Front actor | `k1/concierge/actors/front.py` |
| Concierge Back actor | `k1/concierge/actors/back.py` |
| Concierge Back router | `k1/concierge/actors/back_router.py` |
| Concierge ReAct loop | `k1/concierge/react/loop.py` |
| Concierge tools (implementations) | `k1/concierge/tools/implementations.py` |
| Concierge tools (dispatcher) | `k1/concierge/tools/dispatcher.py` |
| Concierge tools (front schemas) | `k1/concierge/tools/schemas_front.py` |
| Concierge tools (back schemas) | `k1/concierge/tools/schemas_back.py` |
| Concierge LLM port | `k1/concierge/llm/ports.py` (IConciergeModelPort) |
| Concierge LLM types | `k1/concierge/llm/types.py` |
| Concierge LLM bridge (POC) | `k1/concierge/llm/model_hub_bridge.py` (ModelHubPOCBridge) |
| Concierge LLM adapter (Gemini) | `k1/concierge/llm/gemini_adapter.py` |
| Concierge LLM validator | `k1/concierge/llm/validator.py` |
| Concierge Orchestrator stub | `k1/concierge/orchestrator/stub.py` |
| Concierge Orchestrator ports | `k1/concierge/orchestrator/ports.py` |
| Concierge Orchestrator types | `k1/concierge/orchestrator/types.py` |
| Concierge Orchestrator routing | `k1/concierge/orchestrator/routing.py` |
| Concierge DeltaAggregator | `k1/concierge/delta/aggregator.py` |
| Concierge DeltaApplicator | `k1/concierge/delta/applicator.py` |
| Concierge ExperienceLayer | `k1/concierge/experience/layer.py` |
| Concierge EmotionalProcessor | `k1/concierge/experience/emotional_processor.py` |
| Concierge AffectiveMirror | `k1/concierge/experience/affective_mirror.py` |
| Concierge RhythmController | `k1/concierge/experience/rhythm_controller.py` |
| Concierge ProactiveAgent | `k1/concierge/experience/proactive_agent.py` |
| Concierge HILCoordinator | `k1/concierge/protocols/hitl_coordinator.py` |
| Concierge HITL pipeline | `k1/concierge/protocols/hitl_pipeline.py` |
| Concierge TrustAccumulator | `k1/concierge/protocols/trust_accumulator.py` |
| Concierge WeaveBatcher | `k1/concierge/protocols/weave_batcher.py` |
| Concierge WeavePolicy | `k1/concierge/protocols/weave_policy.py` |
| Concierge OppPipeline | `k1/concierge/protocols/opp_pipeline.py` |
| Concierge DeliveryStrategy | `k1/concierge/protocols/delivery_strategy.py` |
| Concierge Cancellation | `k1/concierge/protocols/cancellation.py` |
| Concierge Fabric contracts | `k1/concierge/fabric/contract_converter.py` |
| Concierge POC bridge adapter | `k1/concierge/fabric/poc_bridge_adapter.py` |
| Concierge capability registry | `k1/concierge/fabric/capability_registry.py` |
| Concierge UltraBERT adapter | `k1/concierge/fsm/ultrabert_adapter.py` |
| Concierge UltraBERT Phase1 | `k1/concierge/fsm/ultrabert_phase1.py` |
| Concierge Ledger writer | `k1/concierge/ledger/writer.py` |
| Concierge bus builders | `k1/concierge/bus/builders.py` |
| Model Hub factory | `k1/model_hub/factory.py` |
| Model Hub config | `k1/model_hub/config.py` |
| Model Hub types | `k1/model_hub/types.py` |
| Model Hub events | `k1/model_hub/events.py` |
| Model Hub metrics | `k1/model_hub/metrics.py` |
| Model Hub tracing | `k1/model_hub/tracing.py` |
| Model Hub manifest | `k1/model_hub/manifest.py` |
| Model Hub architecture diagram | `k1/model_hub/model_hub.mmd` |
| IModelHubPort (facade) | `k1/model_hub/ports/hub_port.py` |
| IEventPort | `k1/model_hub/ports/event_port.py` |
| IStateReadPort | `k1/model_hub/ports/state_read_port.py` |
| IMetricsPort | `k1/model_hub/ports/metrics_port.py` |
| IConfigPort | `k1/model_hub/ports/config_port.py` |
| ICredentialPort | `k1/model_hub/ports/credential_port.py` |
| IHealthPort | `k1/model_hub/ports/health_port.py` |
| RequestRouter (9-step pipeline) | `k1/model_hub/services/request_router.py` |
| CapabilityRouter | `k1/model_hub/services/capability_router.py` |
| ModelSelector | `k1/model_hub/services/model_selector.py` |
| BudgetEnforcer | `k1/model_hub/services/budget_enforcer.py` |
| ProviderDispatcher | `k1/model_hub/services/provider_dispatcher.py` |
| ProviderRegistry | `k1/model_hub/services/provider_registry.py` |
| RateLimiter | `k1/model_hub/services/rate_limiter.py` |
| ResponseCache | `k1/model_hub/services/response_cache.py` |
| NormalizationLayer | `k1/model_hub/services/normalization_layer.py` |
| CostTracker | `k1/model_hub/services/cost_tracker.py` |
| AuditLogger | `k1/model_hub/services/audit_logger.py` |
| CircuitBreakerManager | `k1/model_hub/services/circuit_breaker_manager.py` |
| IProviderPlugin (base protocol) | `k1/model_hub/plugins/base.py` |
| OpenAIPlugin | `k1/model_hub/plugins/openai_plugin.py` |
| AnthropicPlugin | `k1/model_hub/plugins/anthropic_plugin.py` |
| GooglePlugin | `k1/model_hub/plugins/google_plugin.py` |
| VLLMPlugin | `k1/model_hub/plugins/vllm_plugin.py` |
| OllamaPlugin | `k1/model_hub/plugins/ollama_plugin.py` |
| TestPlugin | `k1/model_hub/plugins/test_plugin.py` |
| ConfigAdapter | `k1/model_hub/adapters/config_adapter.py` |
| CredentialStoreAdapter | `k1/model_hub/adapters/credential_store_adapter.py` |
| EventBusAdapter (Model Hub) | `k1/model_hub/adapters/event_bus_adapter.py` |
| HealthReportAdapter | `k1/model_hub/adapters/health_report_adapter.py` |
| LLMRequestBusAdapter | `k1/model_hub/adapters/llm_request_bus_adapter.py` |
| PrometheusAdapter | `k1/model_hub/adapters/prometheus_adapter.py` |
| SessionStateReadAdapter (Model Hub) | `k1/model_hub/adapters/session_state_read_adapter.py` |
| Model Hub README | `k1/model_hub/README.md` |

---

## 13. OrchestratorService Constructor Reference

The `OrchestratorService` constructor accepts **14 keyword-only parameters**.
After construction, the factory post-injects `_admin` to break the circular dependency.

### 13.1 Constructor Kwargs

```python
OrchestratorService(
    *,
    mailbox:              IMailboxPort,               # WFQ priority queue
    dag_executor:         DAGExecutorLike,            # executes CommittedPlan as wave-based DAG
    constraint_resolver:  ConstraintResolverLike,     # resolves workflow constraints
    workflow_engine:      WorkflowEngineLike,         # facade over workflow subsystem
    connector_lifecycle:  ConnectorLifecycleLike,     # MCP server lifecycle monitoring
    error_router:         ErrorRouterLike,            # classifies errors -> ErrorAction
    concurrency_guard:    ConcurrencyGuardLike,       # asyncio.Lock gate, max 1 DAG at a time
    fabric_port:          IFabricGatewayPort,         # execute capabilities via Fabric
    planner_port:         IPlannerPort,               # request plans / micro-replans
    state_port:           IStateReadPort,             # read SessionState (read-only ORCH-01)
    delta_port:           IDeltaEmitPort,             # emit events + user-facing deltas
    bridge_port:          IBridgeWritePort,           # WAL writes (audit, plan_start, wave_complete)
    event_port:           IEventSubscriptionPort,     # subscribe to bus topics
    config:               OrchestratorConfig,         # immutable config (frozen dataclass)
)
```

### 13.2 Post-Construction Injection

```python
# Done by factory step 15.5 ONLY if config.admin_enabled:
service._admin = AdminHttpAdapter(service, config)
```

### 13.3 Slots (25 total)

```text
_dag_executor, _constraint_resolver, _workflow_engine, _connector_lifecycle,
_error_router, _concurrency_guard, _fabric_port, _planner_port, _state_port,
_delta_port, _bridge_port, _event_port, _mailbox, _config,
_pending_plans,              # Dict[str, PendingPlanContext] -- active plan requests
_pending_hil,                # Dict[str, PendingHILContext] -- active HIL questions
_executed_plans,             # OrderedDict[str, float] -- dedup LRU
_requeued_envelope_ids,      # OrderedDict[str, float] -- once-guard LRU
_started_at,                 # time.time() at construction
_initialized,                # False until init() completes
_running,                    # False until init() step 9c
_loop_task,                  # asyncio.Task for _mailbox_loop()
_reaper_task,                # asyncio.Task for _reap_loop()
_subscriptions,              # List[SubscriptionHandle] from _subscribe_events()
_admin                       # Optional[AdminHttpAdapter] -- injected post-construction
```

### 13.4 Read-Only Properties

| Property | Type | Description |
| -------- | ---- | ----------- |
| `pending_plans` | `Dict[str, PendingPlanContext]` | Active plan requests awaiting Planner response |
| `pending_hil` | `Dict[str, PendingHILContext]` | Active HIL questions awaiting user response |
| `executed_plans` | `OrderedDict[str, float]` | Recently executed plan IDs for dedup (bounded LRU) |
| `requeued_envelope_ids` | `OrderedDict[str, float]` | Envelope IDs re-enqueued via once guard (bounded LRU) |
| `config` | `OrchestratorConfig` | Immutable config |
| `initialized` | `bool` | Whether `init()` completed successfully |
| `running` | `bool` | Whether mailbox loop and reaper are active |

---

## 14. Factory Internal Wiring (_construct_orchestrator -- 15 Steps)

The factory method `_construct_orchestrator(config, adapters)` builds all internal
collaborators and wires them into `OrchestratorService`. The `adapters` dict has 8
keys: `mailbox`, `fabric`, `planner`, `state`, `delta`, `bridge`, `event`, `storage`.

### 14.1 Step-by-Step Wiring Order

```
Step 1:  ErrorRouter(delta_port=adapters["delta"])
           -- stateless error classifier, needs only delta for diagnostic events

Step 2:  ConcurrencyGuard()
           -- zero deps, internal asyncio.Lock, max 1 active DAG

Step 11: StepRunner(
           fabric_port=adapters["fabric"],
           error_router=error_router,           # from step 1
           policies=OrchestratorPolicies(config) # normal_retries=2, schema_retries=1
         )

Step 12: guards = _build_guards(
           planner_port=adapters["planner"],
           delta_port=adapters["delta"],
           max_micro_replans=config.max_micro_replans
         )
         Returns ordered list:
           [0] OutputSchemaGuard()                              -- no deps
           [1] ConditionalEdgeEvaluator()                       -- no deps
           [2] MicroReplanCheckpoint(planner, max_replans=1)    -- needs planner
           [3] ExecutionMonitor(delta, service_ref=None)        -- lazy init

Step 13: DAGExecutor(
           fabric_port=adapters["fabric"],
           planner_port=adapters["planner"],
           delta_port=adapters["delta"],
           state_port=adapters["state"],
           bridge_port=adapters["bridge"],
           step_runner=step_runner,              # from step 11
           error_router=error_router,            # from step 1
           guards=guards,                        # from step 12
           param_resolver=ParamResolver(registry=None)
         )
         Constants: MAX_WAVES=20, MAX_STEPS=50, _MAX_CONCURRENT_PER_WAVE=10

Step 14a: ConstraintResolver(
            fabric_port=adapters["fabric"],
            delta_port=adapters["delta"],
            event_port=adapters["event"]
          )

Step 14b: Workflow subsystem (9 components in dependency order):
          clock      = SystemClock()
          registry   = WorkflowRegistry(storage_port=adapters["storage"])
          compiler   = WorkflowCompiler(
                         fabric_port=adapters["fabric"],
                         delta_port=adapters["delta"],
                         storage_port=adapters["storage"],
                         state_port=adapters["state"],
                         clock=clock
                       )
          scheduler  = WorkflowScheduler(
                         storage_port=adapters["storage"],
                         mailbox_port=adapters["mailbox"],
                         state_port=adapters["state"],
                         clock=clock,
                         tick_interval_s=config.scheduler_tick_interval_ms / 1000.0
                       )
          depth      = WorkflowDepthGuard(max_depth=config.max_workflow_depth)
          cross      = CrossWorkflowResolver(registry, compiler, depth)
          supervisor = WorkflowRunSupervisor(
                         registry, compiler, adapters["storage"],
                         adapters["delta"], adapters["bridge"]
                       )
          gap        = ProactiveGapDetector(
                         registry, compiler, adapters["storage"],
                         adapters["event"], adapters["delta"]
                       )
          engine     = WorkflowEngine(
                         supervisor=supervisor,
                         dag_executor=dag_executor,        # from step 13
                         constraint_resolver=constraint,   # from step 14a
                         registry=registry,
                         compiler=compiler,
                         scheduler=scheduler,
                         cross_resolver=cross,
                         gap_detector=gap,
                         delta=adapters["delta"]
                       )

Step 15: Connector subsystem (3 components):
          discovery  = MCPToolDiscovery(config_path=config.mcp_config_path)
          registrar  = MCPRegistrationBridge(
                         adapters["fabric"], adapters["delta"]
                       )
          lifecycle  = ConnectorLifecycleManager(
                         discovery, registrar,
                         adapters["event"], adapters["delta"]
                       )

FINAL:   service = OrchestratorService(
           mailbox=adapters["mailbox"],
           dag_executor=dag_executor,            # step 13
           constraint_resolver=constraint,       # step 14a
           workflow_engine=engine,               # step 14b
           connector_lifecycle=lifecycle,        # step 15
           error_router=error_router,            # step 1
           concurrency_guard=guard,              # step 2
           fabric_port=adapters["fabric"],
           planner_port=adapters["planner"],
           state_port=adapters["state"],
           delta_port=adapters["delta"],
           bridge_port=adapters["bridge"],
           event_port=adapters["event"],
           config=config,
         )

POST:    guards[3]._service_ref = service       # ExecutionMonitor lazy-init (circular dep fix)

15.5:    if config.admin_enabled:
           service._admin = AdminHttpAdapter(service, config)
```

### 14.2 Factory Public Methods

| Method | Auto-init | Admin | Use Case |
| ------ | --------- | ----- | -------- |
| `create_production(config, *, mailbox, fabric, planner, state, delta, bridge, event, storage)` | Yes (calls `await service.init()`) | config.admin_enabled (default True) | Kernel bootstrap |
| `create_standalone(*, config=None)` | No | admin_enabled=False | Quick testing, REPL |
| `create_for_testing(overrides=None, *, config=None)` | No | admin_enabled=False (default) | Unit tests with real internals |
| `create_with_ports(*, config, mailbox, fabric, planner, state, delta, bridge, event, storage)` | No | admin_enabled from config | Integration tests needing custom ports |

GOTCHA: Only `create_production()` calls `init()`. All other methods require manual `await service.init()`.

---

## 15. init() Startup Sequence (10 Steps)

`init()` is idempotent -- second call logs `"init.already_initialized"` and returns.
Target: entire init completes in < 500ms.

```
Step 1:   _validate_ports()
            -- Asserts all 14 constructor params + internal collaborators are non-None.
            -- Raises RuntimeError("port X is None") on first failure.
            -- MUST pass before any async work begins.

Step 2:   (reserved -- no-op in V1)
            -- Future: event bus connection handshake, adapter readiness probe.

Step 2b:  await crash_recovery()
            -- Reads WAL via bridge_port.read_wal().
            -- Re-enqueues incomplete DAGs to mailbox as recovery envelopes.
            -- GOTCHA: Must run BEFORE mailbox loop (step 10) starts.
            -- Logs: "init.crash_recovery" {recovered: int, failed: int, skipped: int}

Step 3:   Assert concurrency guard not locked
            -- assert not getattr(self._concurrency_guard, "active", False)
            -- Catches state corruption from improper prior shutdown.

Step 4:   await _discover_mcp_tools()
            -- MCPToolDiscovery.discover() with 500ms timeout.
            -- Registers discovered tools via MCPRegistrationBridge.
            -- Logs: "init.mcp_discovery" {registered: int, skipped: int, errors: int}
            -- Non-fatal: errors logged, init continues.

Step 5:   (commentary, no-op) -- "Tools now available for DAG execution."

Step 6:   await _workflow_engine.registry.list_active()
            -- Loads persisted active workflows from SQLite.
            -- Logs: "init.workflows_loaded" {count: int}

Step 7:   await _workflow_engine.scheduler.start()
            -- Starts WorkflowScheduler tick loop (asyncio.Task).
            -- Tick interval: config.scheduler_tick_interval_ms (default 1000ms).

Step 8:   _subscribe_events()  (sync method)
            -- Subscribes to 5 event topics (see Section 18.2 for details):
              1. k1.planner.plan.ready.v1       -> _on_plan_ready
              2. k1.planner.plan.failed.v1      -> _on_plan_failed
              3. k1.planner.plan.cancelled.v1   -> _on_plan_cancelled
              4. k1.hil.override_response.v1    -> _on_hil_override
              5. k1.hil.fallback_response.v1    -> _on_hil_fallback
            -- Each subscribe() returns SubscriptionHandle stored in _subscriptions[].
            -- Note: GapDetector and SubStepObserver manage own subscriptions separately.

Step 9a:  await _workflow_engine.gap_detector.start()
            -- Starts ProactiveGapDetector (manages own contract_updated subscription).

Step 9b:  _connector_lifecycle.start_lifecycle_monitoring()  (sync)
            -- Subscribes to "k1.fabric.provider.health.changed.v1".
            -- Begins monitoring MCP server health.

Step 9c:  _running = True
            -- Enables mailbox processing and reaper.
            _reaper_task = asyncio.create_task(_reap_loop())
            -- Reaper runs every config.context_reap_interval_ms (default 5s).
            -- Reaps timed-out pending_plans (plan_request_timeout_ms)
              and pending_hil (hil_timeout_ms) contexts.

Step 10:  _loop_task = asyncio.create_task(_mailbox_loop())
            -- Starts mailbox dequeue loop.
            -- Calls _process_one(item) for each dequeued item.
            -- ConcurrencyGuard checked inside _process_one(), NOT here.

Step 10.5: if _admin is not None and config.admin_enabled:
              await _admin.start(config.admin_port)
            -- Binds aiohttp to 127.0.0.1:admin_port (default 8081).
            -- Logs: "init.step10_5.admin_started" {port: int}
            -- Non-fatal: errors logged via "init.step10_5.admin_start_error".

FINAL:    _initialized = True
            -- Logs: "init.complete" {elapsed_ms: float, subscriptions: int}
```

---

## 16. shutdown() Teardown Sequence (9 Steps)

Guard: if `not self._initialized` then log `"shutdown.not_initialized"` and return immediately.
Generates `trace_id = f"shutdown-{uuid4()}"`.

```
Step 1:   _running = False
            -- Signals mailbox loop and reaper to exit on next iteration.

Step 2:   _connector_lifecycle.stop_lifecycle_monitoring()  (sync)
            -- Unsubscribes from provider health events.
            -- Clears pending refresh list.
            -- Error: log.exception("shutdown.step2.connector_lifecycle_error")

Step 3:   Wait for active DAG completion (30s timeout)
            -- Polls concurrency_guard.active every 0.1s.
            -- If no active DAG: log "shutdown.step3.no_active_dag", skip.
            -- If active: log "shutdown.step3.waiting_for_active_dag".
            -- If completes: log "shutdown.step3.dag_completed".
            -- If 30s timeout: log "shutdown.step3.dag_timeout" (proceeds anyway).
            -- Timeout is config.shutdown_grace_period_ms (default 30000).

Step 4:   Force-compensate timed-out DAG (V1: DEFERRED)
            -- Saga.compensate() not wired in V1.
            -- Logs: "shutdown.step4.force_compensate_deferred"
            -- Future: will invoke saga compensation for interrupted DAG.

Step 5:   await _workflow_engine.scheduler.stop()
            -- Stops scheduler tick loop task.
            -- Error: log.exception("shutdown.step5.scheduler_error")

Step 6:   await _workflow_engine.gap_detector.stop()
            -- Stops gap detector, unsubscribes its internal events.
            -- Then: unsubscribe ALL event subscriptions from _subscriptions[].
              for handle in _subscriptions:
                  await _event_port.unsubscribe(handle)
              _subscriptions.clear()
            -- Logs: "shutdown.step6.events_unsubscribed" {count: int}
            -- Error: per-handle "shutdown.step6.unsubscribe_error"

Step 7:   Trigger state persistence (V1: DEFERRED)
            -- WorkflowScheduler lacks get_next_fire/get_last_fire in V1.
            -- Logs: "shutdown.step7.trigger_persistence_deferred"
            -- Future: persists next-fire times for all active triggers.

Step 8:   Final audit write
            -- Counts orphaned contexts:
              orphaned_plans = len(pending_plans)
              orphaned_hil = len(pending_hil)
            -- If orphaned > 0: warn "shutdown.step8.orphaned_contexts"
            -- Writes: await bridge_port.submit_audit(
                {event: "orchestrator_shutdown", trace_id, orphaned_plans, orphaned_hil},
                trace_id
              )
            -- Error: log.exception("shutdown.step8.audit_error")

Step 8.5: if _admin is not None:
              await _admin.stop()
            -- Shuts down aiohttp runner + site.
            -- Logs: "shutdown.step8_5.admin_stopped"
            -- Error: log.exception("shutdown.step8_5.admin_stop_error")

Step 9:   Cancel background tasks
            -- _reaper_task.cancel(); await _reaper_task (catch CancelledError)
            -- _loop_task.cancel(); await _loop_task (catch CancelledError)
            -- _reaper_task = None; _loop_task = None
            -- _initialized = False
            -- Logs: "shutdown.step9.tasks_cancelled"

FINAL:    Logs "shutdown.complete" {elapsed_ms: float, trace_id: str}
```

Shutdown order contract: Orchestrator shuts down BEFORE Fabric, Fabric BEFORE
SessionState, SessionState BEFORE Bus (consumers before infrastructure).

---

## 17. OrchestratorConfig Field Reference

`@dataclass` with `__post_init__` validation. Immutable after creation.
Factory methods: `OrchestratorConfig.default()`, `OrchestratorConfig.from_dict(d)` (ignores unknown keys),
`config.to_dict()`.

### 17.1 Concurrency

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `max_concurrent_dags` | `int` | `1` | Max DAGs executing simultaneously (V1: always 1) |
| `max_wave_parallelism` | `int` | `5` | Max steps per wave in DAGExecutor |
| `mailbox_capacity` | `int` | `100` | MailboxAdapter max_depth (WFQ queue size) |

### 17.2 Timeouts (all in milliseconds)

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `default_step_timeout_ms` | `int` | `30_000` | Per-step execution timeout in StepRunner |
| `plan_request_timeout_ms` | `int` | `45_000` | PlannerAdapter request timeout (includes CB_PLANNER) |
| `hil_timeout_ms` | `int` | `120_000` | HIL question timeout before fallback |
| `drain_timeout_ms` | `int` | `30_000` | Mailbox drain timeout during admin drain operation |
| `shutdown_grace_period_ms` | `int` | `30_000` | Max wait for active DAG at shutdown step 3 |
| `context_reap_interval_ms` | `int` | `5_000` | Reaper loop interval (checks pending_plans + pending_hil) |

### 17.3 Retry

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `step_max_retries` | `int` | `2` | Normal step retries (StepRunner policies.normal_retries) |
| `step_retry_base_delay_ms` | `int` | `100` | Base delay for exponential backoff (V1: immediate retry, 0ms) |
| `step_retry_max_delay_ms` | `int` | `5_000` | Max delay cap for exponential backoff |

### 17.4 Guards

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `guard_order` | `List[str]` | `list(_DEFAULT_GUARD_ORDER)` | Ordered guard class names for DAGExecutor |
| `max_micro_replans` | `int` | `1` | Max micro-replans per DAG (MicroReplanCheckpoint budget) |
| `substep_rate_limit_ms` | `int` | `500` | SubStep rate limit (throttle rapid sub-step creation) |

### 17.5 Workflow

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `max_workflow_depth` | `int` | `3` | Max workflow nesting depth (WorkflowDepthGuard) |
| `workflow_db_path` | `str` | `"data/orchestrator_workflows.db"` | SQLite path for WorkflowStorageAdapter |
| `scheduler_tick_interval_ms` | `int` | `1_000` | WorkflowScheduler poll interval |

### 17.6 MCP Connectors

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `mcp_config_path` | `str` | `"k1/connectors/mcp_servers.yaml"` | Path to MCP server config file |
| `mcp_discovery_interval_ms` | `int` | `300_000` | Re-discovery interval (5 min) |
| `mcp_max_servers` | `int` | `10` | Max concurrent MCP servers |

### 17.7 Circuit Breaker (CB_PLANNER only -- Orchestrator-owned)

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `cb_planner_failure_threshold` | `int` | `3` | Failures before CB opens |
| `cb_planner_reset_timeout_ms` | `int` | `60_000` | Time in OPEN before transition to HALF_OPEN |
| `cb_planner_half_open_probes` | `int` | `1` | Probe calls in HALF_OPEN before closing |

### 17.8 Telemetry

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `metrics_enabled` | `bool` | `True` | Enable structured metrics emission |
| `metrics_interval_ms` | `int` | `10_000` | Metrics collection interval |
| `structured_log_level` | `str` | `"INFO"` | Log level for structured logs |
| `trace_sample_rate` | `float` | `1.0` | Trace sampling rate (1.0 = all traces) |
| `trace_propagation` | `bool` | `True` | Propagate trace context across boundaries |

### 17.9 Admin

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `admin_enabled` | `bool` | `True` | Enable AdminHttpAdapter (disabled in test factories) |
| `admin_port` | `int` | `8081` | HTTP port for admin endpoints |

### 17.10 Pending Context Limits

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| `max_pending_plans` | `int` | `50` | Max concurrent plan requests before rejection |
| `max_pending_hil` | `int` | `20` | Max concurrent HIL questions before rejection |

---

## 18. Event Topic Reference

### 18.1 Emitted Topics (19 constants in events.py, 17 active in V1)

| Constant | Topic String | Emitter | Description |
| -------- | ------------ | ------- | ----------- |
| `ORCH_TASK_ACCEPTED` | `k1.orchestration.task.accepted.v1` | `_process_one` | TaskEnvelope accepted from mailbox |
| `ORCH_PLAN_REQUESTED` | `k1.orchestration.plan.requested.v1` | `_process_one` | Plan request sent to Planner |
| `ORCH_DAG_STARTED` | `k1.orchestration.dag.started.v1` | DAGExecutor | DAG execution begins |
| `ORCH_DAG_MICRO_REPLAN` | `k1.orchestration.dag.micro_replan.v1` | MicroReplanCheckpoint | Micro-replan requested mid-DAG |
| `ORCH_DAG_COMPLETED` | `k1.orchestration.dag.completed.v1` | DAGExecutor | DAG finished (success or failure) |
| `ORCH_STEP_STARTED` | `k1.orchestration.step.started.v1` | StepRunner | Step execution begins |
| `ORCH_STEP_COMPLETED` | `k1.orchestration.step.completed.v1` | StepRunner | Step completed successfully |
| `ORCH_STEP_FAILED` | `k1.orchestration.step.failed.v1` | StepRunner | Step failed after retries exhausted |
| `ORCH_STEP_CANCELLED` | `k1.orchestration.step.cancelled.v1` | DAGExecutor | Step cancelled (interrupt or skip) |
| `ORCH_STEP_SKIPPED` | `k1.orchestration.step.skipped.v1` | ConditionalEdgeEval | Step skipped by condition guard |
| `ORCH_STEP_RETRYING` | `k1.orchestration.step.retrying.v1` | StepRunner | Step retry initiated |
| `ORCH_STEP_SCHEMA_RETRY` | `k1.orchestration.step.schema_retry.v1` | OutputSchemaGuard | Schema validation failed, retrying |
| `ORCH_SAGA_COMPENSATING` | `k1.orchestration.saga.compensating.v1` | Saga | Compensation started for failed DAG |
| `ORCH_DELTA_V1` | `k1.orchestration.delta.v1` | DeltaEmitAdapter | User-facing delta (streamed to Concierge) |
| `ORCH_WORKFLOW_TRIGGERED` | `k1.orchestration.workflow.triggered.v1` | WorkflowScheduler | Scheduled workflow trigger fired |
| `ORCH_WORKFLOW_COMPLETED` | `k1.orchestration.workflow.completed.v1` | WorkflowRunSupervisor | Workflow run completed |
| `ORCH_WORKFLOW_SAVED` | `k1.orchestration.workflow.saved.v1` | WorkflowEngine | Workflow definition persisted |
| `ORCH_ERROR_ROUTED` | `k1.orchestration.error.routed.v1` | ErrorRouter | Error classified and action decided |
| `ORCH_MCP_TOOL_REGISTERED` | `k1.orchestration.mcp.tool_registered.v1` | MCPRegistrationBridge | MCP tool registered with Fabric |

V1 removed (constants exist but not emitted): `STEP_QUALITY_RETRY`, `DAG_BUDGET_WARNING`, `DAG_BUDGET_EXHAUSTED`.

### 18.2 Consumed Topics (12 constants, 5 subscribed at init step 8)

| Constant | Topic String | Handler | Subscribed At |
| -------- | ------------ | ------- | ------------- |
| `PLAN_READY` | `k1.planner.plan.ready.v1` | `_on_plan_ready` | init step 8 |
| `PLAN_FAILED` | `k1.planner.plan.failed.v1` | `_on_plan_failed` | init step 8 |
| `PLAN_CANCELLED` | `k1.planner.plan.cancelled.v1` | `_on_plan_cancelled` | init step 8 |
| `MICRO_REPLAN_READY` | `k1.planner.micro_replan.ready.v1` | (MicroReplanCheckpoint internal) | Guard internal |
| `CAPABILITY_COMPLETED` | `k1.capability.completed.v1` | (DAGExecutor internal) | DAG execution |
| `CAPABILITY_FAILED` | `k1.capability.failed.v1` | (DAGExecutor internal) | DAG execution |
| `CONTRACT_UPDATED` | `k1.fabric.contract.updated.v1` | (ProactiveGapDetector) | GapDetector.start() |
| `AGENT_TOOL_CALL` | `k1.fabric.agent.tool_call.v1` | (SubStepObserver) | Observer internal |
| `AGENT_LLM_CALL` | `k1.fabric.agent.llm_call.v1` | (SubStepObserver) | Observer internal |
| `WORKFLOW_TRIGGER_DUE` | `k1.orchestration.workflow.trigger_due.v1` | (WorkflowScheduler) | Scheduler tick |
| `HIL_OVERRIDE_RESPONSE` | `k1.hil.override_response.v1` | `_on_hil_override` | init step 8 |
| `HIL_FALLBACK_RESPONSE` | `k1.hil.fallback_response.v1` | `_on_hil_fallback` | init step 8 |

### 18.3 Aggregate Sets

- `ALL_EMITTED`: frozenset of 19 emitted topic strings
- `ALL_CONSUMED`: frozenset of 12 consumed topic strings

---

## 19. Guard Registry

Guards run inside DAGExecutor during wave-based plan execution. They are
called at three lifecycle points: `before_wave`, `after_step`, `after_wave`.

### 19.1 Active Guards (4, in factory step 12 order)

| Index | Guard | Lifecycle Hook | Constructor | Purpose |
| ----- | ----- | -------------- | ----------- | ------- |
| [0] | `OutputSchemaGuard` | `after_step` (G9) | `OutputSchemaGuard()` -- no deps, stateless | Validates step output against `step.output_schema` via jsonschema Draft 2020-12. No schema = BYPASS. Invalid + first try = RETRY. Invalid + retried = HARD_STOP. |
| [1] | `ConditionalEdgeEvaluator` | `before_wave` (G1) | `ConditionalEdgeEvaluator()` -- no deps, stateless | Evaluates `PlanStep.condition` (ConditionExpr tree) against merged_results. Ops: EQ/NEQ/GT/GTE/LT/LTE/CONTAINS + AND/OR/NOT. Path format: `"step_id.status"`, `"step_id.data.field"`. FALSE = SKIP step. |
| [2] | `MicroReplanCheckpoint` | `after_wave` (G8) | `MicroReplanCheckpoint(planner, max_replans=1)` -- stateful | Tracks `_replans_used` (max 1 per DAG). Detects discoveries in CapabilityResult.data["discoveries"]. Calls planner.micro_replan() with 10s timeout. Has `reset()` called by DAGExecutor at DAG start. Overlap heuristic: exact/substring match. |
| [3] | `ExecutionMonitor` | `after_step` + `after_wave` (G8) | `ExecutionMonitor(delta, service_ref=None)` -- lazy init | `after_step`: checks `ctx.interrupt_flag` -> HARD_STOP. `after_wave`: emits progress delta + optionally HIL override prompt (>3 steps OR >5s). `_service_ref` set post-construction (factory POST step). |

### 19.2 ConcurrencyGuard (NOT a DAGGuard)

- **Checked in `_process_one()` BEFORE dispatch**, not in DAG walk.
- Constructor: `ConcurrencyGuard()` -- zero deps, internal `asyncio.Lock`.
- `acquire() -> bool`: non-blocking, returns False if already locked.
- `release()`: safe even if not held.
- `active` property: whether a DAG is currently executing.
- V1: `max_concurrent_dags = 1` (single DAG at a time).

### 19.3 Guard Decision Types

| Decision | Meaning |
| -------- | ------- |
| `CONTINUE` | Proceed with execution |
| `SKIP` | Skip this step (ConditionalEdgeEvaluator) |
| `RETRY` | Retry the step (OutputSchemaGuard) |
| `HARD_STOP` | Abort entire DAG immediately (interrupt flag or repeated schema fail) |
| `BYPASS` | Guard does not apply (no schema defined) |

---

## 20. Workflow Engine Composition

The workflow subsystem is built in factory step 14b as 9 components wired into
`WorkflowEngine`. The engine is a facade delegating to specialized components.

### 20.1 Component Dependency Graph

```text
SystemClock (no deps)
  |
  +---> WorkflowRegistry(storage_port)
  +---> WorkflowCompiler(fabric, delta, storage, state, clock)
  +---> WorkflowScheduler(storage, mailbox, state, clock, tick_interval_s)
  +---> WorkflowDepthGuard(max_depth=config.max_workflow_depth)
  |
  +---> CrossWorkflowResolver(registry, compiler, depth_guard)
  +---> WorkflowRunSupervisor(registry, compiler, storage, delta, bridge)
  +---> ProactiveGapDetector(registry, compiler, storage, event, delta)
  |
  +---> WorkflowEngine(
          supervisor, dag_executor, constraint_resolver,
          registry, compiler, scheduler,
          cross_resolver, gap_detector, delta
        )
```

### 20.2 Component Responsibilities

| Component | Responsibility | Lifecycle |
| --------- | -------------- | --------- |
| `SystemClock` | Real time provider (now(), monotonic()) | Static |
| `WorkflowRegistry` | CRUD for workflow definitions (SQLite-backed) | Static |
| `WorkflowCompiler` | Compiles workflow YAML to executable DAG plans | Static |
| `WorkflowScheduler` | Tick-based trigger evaluation + mailbox enqueue | init step 7: `start()`, shutdown step 5: `stop()` |
| `WorkflowDepthGuard` | Prevents infinite workflow nesting (max_depth=3) | Static |
| `CrossWorkflowResolver` | Resolves cross-workflow dependencies + triggers | Static |
| `WorkflowRunSupervisor` | Manages workflow run lifecycle (start, complete, fail) | Static |
| `ProactiveGapDetector` | Detects capability gaps from contract changes | init step 9a: `start()`, shutdown step 6: `stop()` |
| `WorkflowEngine` | Facade: `execute_workflow()`, `save_workflow()` | Via OrchestratorService |

### 20.3 WorkflowEngine Slots (9)

```text
_supervisor, _dag_executor, _constraint_resolver, _registry, _compiler,
_scheduler, _cross_resolver, _gap_detector, _delta
```

Properties exposed: `registry`, `compiler`, `scheduler`, `gap_detector` (used by init/shutdown).

---

## 21. Connector Lifecycle

The connector subsystem manages MCP (Model Context Protocol) server discovery,
tool registration, and health monitoring. Built in factory step 15.

### 21.1 Components

| Component | Constructor | Responsibility |
| --------- | ----------- | -------------- |
| `MCPToolDiscovery` | `MCPToolDiscovery(config_path=config.mcp_config_path)` | Reads `mcp_servers.yaml`, discovers available MCP servers and their tool manifests |
| `MCPRegistrationBridge` | `MCPRegistrationBridge(fabric_port, delta_port)` | Registers discovered tools with Fabric's capability registry, emits `ORCH_MCP_TOOL_REGISTERED` |
| `ConnectorLifecycleManager` | `ConnectorLifecycleManager(discovery, registrar, event_port, delta_port)` | Orchestrates discovery + registration, monitors server health via `k1.fabric.provider.health.changed.v1` |

### 21.2 Lifecycle

```text
init step 4:   _discover_mcp_tools()
                 -> MCPToolDiscovery.discover()       (500ms timeout)
                 -> MCPRegistrationBridge.register()   (per tool)
                 -> Emits ORCH_MCP_TOOL_REGISTERED for each

init step 9b:  ConnectorLifecycleManager.start_lifecycle_monitoring()
                 -> Subscribes to k1.fabric.provider.health.changed.v1
                 -> Populates server_capabilities: Dict[str, List[str]]

shutdown step 2: ConnectorLifecycleManager.stop_lifecycle_monitoring()
                 -> Unsubscribes health events
                 -> Clears _pending_refresh
```

### 21.3 ConnectorLifecycleManager Slots (7)

```text
_discovery, _registrar, _events, _delta,
server_capabilities,     # Dict[str, List[str]] -- server_id -> tool names
_health_handle,          # Optional[SubscriptionHandle]
_pending_refresh         # List[str] -- servers awaiting re-discovery
```

---

## 22. Admin API Endpoint Reference

`AdminHttpAdapter` provides 18 HTTP endpoints via aiohttp on `127.0.0.1:{admin_port}`.
All responses are JSON with `X-Trace-Id` header. No auth in V1.

### 22.1 Health Endpoints

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| GET | `/health/live` | Liveness probe (always 200) | `{status: "alive"}` |
| GET | `/health/ready` | Readiness probe (200 if initialized) | `{status: "ready"/"not_ready", initialized: bool}` |
| GET | `/health/status` | Full status snapshot | `{initialized, running, uptime_s, pending_plans, pending_hil, active_dag, mailbox_depth}` |

### 22.2 DAG Management

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| GET | `/admin/dags` | List active/recent DAGs | `{dags: [...]}` |
| GET | `/admin/dags/{dag_id}` | Get DAG detail | `{dag_id, status, steps, waves, ...}` |
| POST | `/admin/dags/{dag_id}/cancel` | Cancel active DAG | `{cancelled: bool}` |

### 22.3 Circuit Breaker Control

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| GET | `/admin/circuit-breakers` | List CB states | `{circuit_breakers: [{name, state, ...}]}` |
| POST | `/admin/circuit-breakers/{name}/state` | Force CB state change | `{name, new_state}` |

### 22.4 Workflow Scheduler

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| GET | `/admin/scheduler/triggers` | List active triggers | `{triggers: [...]}` |
| GET | `/admin/scheduler/triggers/{workflow_id}` | Get trigger detail | `{workflow_id, next_fire, ...}` |

### 22.5 Mailbox

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| POST | `/admin/drain` | Drain mailbox (graceful stop) | `{drained: bool, timeout_ms}` |
| GET | `/admin/mailbox/depth` | Current mailbox depth | `{depth: int, capacity: int}` |
| GET | `/admin/mailbox/stats` | WFQ queue statistics | `{realtime, interactive, background, total}` |

### 22.6 MCP Connectors

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| GET | `/admin/mcp/servers` | List MCP servers | `{servers: [{id, tools, healthy}]}` |
| POST | `/admin/mcp/rediscover` | Force MCP re-discovery | `{discovered: int, registered: int}` |

### 22.7 Observability

| Method | Path | Purpose | Key Response Fields |
| ------ | ---- | ------- | ------------------- |
| GET | `/admin/config` | Current config (read-only) | Full OrchestratorConfig as dict |
| GET | `/admin/metrics` | Prometheus-style metrics | `{metrics: {...}}` |
| GET | `/admin/version` | Orchestrator version info | `{version, build, python}` |

---

## 23. Circuit Breaker Reference

### 23.1 Ownership Model

| CB Name | Owner | Config Source |
| ------- | ----- | ------------- |
| `CB_PLANNER` | Orchestrator (PlannerAdapter) | `OrchestratorConfig.cb_planner_*` fields |
| `CB_FABRIC` | Concierge | Concierge config (NOT Orchestrator) |
| `CB_MCP` | Concierge | Concierge config (NOT Orchestrator) |
| `CB_BRIDGE` | Concierge | Concierge config (NOT Orchestrator) |

GOTCHA: Orchestrator uses Fabric via `FabricGatewayAdapter` but does NOT own CB_FABRIC.
The Concierge wraps Fabric calls with its own circuit breaker. Orchestrator calls Fabric
directly through the adapter (no CB wrapping).

### 23.2 CB_PLANNER State Machine

```text
CLOSED --[3 failures]--> OPEN --[60s]--> HALF_OPEN --[1 probe success]--> CLOSED
                                              |
                                        [probe fails]
                                              |
                                              v
                                            OPEN
```

- `failure_threshold`: 3 consecutive failures (config.cb_planner_failure_threshold)
- `reset_timeout_s`: 60s (config.cb_planner_reset_timeout_ms / 1000)
- `half_open_probes`: 1 (config.cb_planner_half_open_probes)
- When OPEN: PlannerAdapter.request_plan() raises immediately (no Planner call)
- Admin can force state via `POST /admin/circuit-breakers/CB_PLANNER/state`

### 23.3 Bootstrap Wiring (Phase 5)

```python
from k1.fabric.circuit_breaker.breaker import CircuitBreaker
cb_planner = CircuitBreaker(
    "CB_PLANNER",
    failure_threshold=orch_config.cb_planner_failure_threshold,
    reset_timeout_s=orch_config.cb_planner_reset_timeout_ms / 1000
)
planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
```

---

## 24. Error Handling Patterns

### 24.1 ErrorRouter

- Location: `k1/orchestrator/orchestration/error_router.py`
- Constructor: `ErrorRouter(delta_port)` -- single dependency
- Two interfaces:
  - `route_error(error, context) -> ErrorAction` -- async, emits `ORCH_ERROR_ROUTED` diagnostic delta
  - `classify(error) -> ErrorSeverity` -- sync, classification only (no delta)

### 24.2 Error Classification Matrix

| Adapter | RECOVERABLE | DEGRADED | TERMINAL |
| ------- | ----------- | -------- | -------- |
| Mailbox | RETRY(1) | -- | ABORT |
| DeltaEmit | RETRY(1) | -- | ABORT |
| BridgeWrite | RETRY(1) | -- | ABORT |
| EventSub | RETRY(1) | -- | ABORT |
| FabricGW | -- | DEGRADE | ABORT |
| Planner | -- | FALLBACK | ABORT |
| StateRead | -- | DEGRADE | ABORT |

### 24.3 AdapterException vs AdapterError

- `AdapterException(message, *, detail: AdapterError)` -- **raiseable**, wraps AdapterError
- `AdapterError(code, message, severity, adapter, timestamp, context)` -- **frozen dataclass**, NOT raiseable
- `ErrorSeverity` enum: `RECOVERABLE`, `DEGRADED`, `TERMINAL`
- GOTCHA: Use `exception.detail` to access the AdapterError (NOT `.error`)

### 24.4 ErrorAction Enum

| Action | Meaning | When |
| ------ | ------- | ---- |
| `RETRY` | Retry the operation (1 attempt) | RECOVERABLE severity |
| `DEGRADE` | Continue with degraded behavior | DEGRADED on Fabric/State |
| `FALLBACK` | Use fallback path | DEGRADED on Planner (skip planning) |
| `ABORT` | Abort the DAG | TERMINAL severity on any adapter |

### 24.5 Saga Compensation (V1: DEFERRED)

- Saga tracks completed steps during DAG execution.
- On DAG failure: would invoke compensating actions in reverse order.
- V1: `Saga.compensate()` exists but is not wired. Shutdown step 4 logs
  `"shutdown.step4.force_compensate_deferred"`.
- Future: compensation will be triggered on DAG timeout at shutdown and on
  unrecoverable step failures.

---

## 25. Bootstrap Gotchas

Critical ordering and wiring traps to avoid during kernel bootstrap implementation.

| # | Gotcha | Consequence if Violated |
| - | ------ | ----------------------- |
| G-01 | `crash_recovery()` must run BEFORE mailbox loop starts (init step 2b before step 10) | Recovery envelopes skipped, data loss |
| G-02 | `create_production()` auto-calls `init()`. All other factory methods do NOT. | Service stuck in uninitialized state, mailbox never starts |
| G-03 | Factory kwargs use **short names**: `mailbox`, `fabric`, `planner`, `state`, `delta`, `bridge`, `event`, `storage` | TypeError on factory call |
| G-04 | `MockPlannerAdapter` is Phase 1 stub only. Phase 5 must hot-swap to `PlannerAdapter(planner_mailbox, cb_planner)` | Plan requests silently fail or return canned responses |
| G-05 | `AdminHttpAdapter` injected post-construction via `service._admin = ...` (NOT a constructor param) | AttributeError or admin never starts |
| G-06 | `ExecutionMonitor._service_ref` set post-construction (factory POST step). Circular dep. | ExecutionMonitor HIL prompts fail with NoneType |
| G-07 | `DeltaEmitAdapter(event_port, delta_bus)` takes TWO args, both can be same `FabricBusAdapter` instance | Missing delta stream or missing internal events |
| G-08 | `WorkflowStorageAdapter` wraps `SQLiteWorkflowAdapter(db_path)`, NOT raw db_path | TypeError: expected IWorkflowStoragePort, got str |
| G-09 | Shutdown order: Orchestrator -> Fabric -> SessionState -> Bus. Reversing causes event loss. | Orphaned events, broken audit trail |
| G-10 | `OrchestratorConfig.from_dict()` ignores unknown keys silently + validates in `__post_init__` | Missing config keys use defaults (may surprise), invalid values raise ValueError |
| G-11 | Test factories set `admin_enabled=False` by default. Do NOT create AdminHttpAdapter for tests. | Port conflict if multiple tests run admin servers |
| G-12 | `MailboxAdapter` capacity (`mailbox_capacity`) must match between config and adapter constructor | Queue silently drops envelopes at wrong depth |

### 25.1 Planner Bootstrap Gotchas

| # | Gotcha | Consequence if Violated |
| - | ------ | ----------------------- |
| P-01 | `PlannerFactory.create_production()` does NOT call `agent.start()` -- it returns an unwired agent. Kernel MUST spawn `asyncio.create_task(planner.start())` as a separate background task. | Planner never enters dequeue loop, plan requests silently queue forever |
| P-02 | `planner.stop()` must be called BEFORE `planner_task.cancel()` in shutdown. `stop()` drains the mailbox and emits `plan.cancelled.v1` per queued request; `cancel()` just kills the task. | Queued plan requests silently lost (no cancelled event, Orchestrator never notified) |
| P-03 | `EventBusAdapter(event_port)` wraps Fabric `IEventPort`. `DeltaBusAdapter(delta_bus)` wraps Fabric `IDeltaBusPort`. These are DIFFERENT Fabric interfaces, though both may originate from the same `FabricBusAdapter` instance. | Passing `FabricBusAdapter` for both is correct; passing a non-dual-interface object for one causes AttributeError at runtime |
| P-04 | `DeltaBusAdapter` pre-stamps `agent_id="planner"` at construction. All deltas publish to topic `k1.agent.planner.delta.v1` regardless of request. | Passing wrong agent_id causes deltas to route to wrong topic; subscribers miss Planner progress |
| P-05 | `SessionStateReadAdapter(reader, session_id)` requires a pre-bound `session_id`. In V1, the kernel must determine the active session before creating the Planner. | Passing wrong `session_id` causes Planner to read stale/wrong session state for plan context |
| P-06 | All 7 port slots must be distinct `id()` objects -- `DuplicatePortError` raised if two slots share identity. The only acceptable sharing is the underlying `FabricBusAdapter` BEHIND two different adapter wrappers (`EventBusAdapter` and `DeltaBusAdapter`). | `DuplicatePortError` at factory validation; factory refuses to wire |
| P-07 | `TestLLMAdapter` and `TestBridgeAdapter` are Phase 1 stubs. Production requires `LLMGatewayAdapter` and `BridgeAdapter`. Phase 1 bootstrap uses test stubs for these two ports only. | Test stubs return canned responses -- plans are deterministic but not real |
| P-08 | `PlannerConfig.from_dict(overrides)` validates all 10 config bounds (mailbox_max_depth >= 1, pipeline_timeout_ms > 0, etc.). Invalid values raise `InvalidConfigError` at factory creation, not at runtime. | Misconfigured Planner silently wired; errors surface at plan execution time with confusing symptoms |
| P-09 | `MailboxAdapter(max_depth=N)` must use `planner_config.mailbox_max_depth` for N. Mismatched depth between config and adapter causes silent queue pressure differences. | Config says depth=10 but adapter uses default 5 -- requests rejected at wrong threshold |
| P-10 | Phase 5b cross-wire (`orchestrator._planner_port = planner_adapter`) must happen AFTER `PlannerFactory.create_production()` returns and BEFORE any `TaskEnvelope` arrives at the Orchestrator that requires planning. There is no locking -- the hot-swap is a single attribute assignment. | Plan requests routed to `MockPlannerAdapter` (canned responses) instead of real Planner |

---

## PART B: Fabric Deep Dive

---

## 26. Fabric Architecture Overview

The Fabric is the **capability execution engine** of K1. It resolves capability
requests to providers, enforces policy, executes through circuit breakers, validates
output, and emits events. The `Fabric` dataclass is a container holding three
public facades plus internal infrastructure.

### 26.1 Fabric Container (dataclass)

```python
@dataclass
class Fabric:
    facade:        CapabilityFabric       # Primary execution engine (9-step pipeline)
    retrieval:     FabricRetrieval         # Semantic capability discovery
    registry_api:  CapabilityRegistryAPI   # CRUD for capability contracts
    registry:      Any = None             # CapabilityRegistry (internal)
    module_loader: Any = None             # ModuleLoader (contract watcher)
    health_checker: Any = None            # HealthChecker (provider health monitoring)
    event_port:    Any = None             # IEventPort (for bus access)
    event_emitter: Optional[EventEmitter] = None  # Typed event emission
```

Convenience delegates on `Fabric`: `execute()`, `execute_batch()`,
`discover_capabilities()`, `find_relevant_prompts()`, `register(contract)`,
`unregister(name)`, `lookup(name)`, `health()`, `start_health_checker()`, `shutdown()`.

### 26.2 FabricConfig

```python
@dataclass(frozen=True)
class FabricConfig:
    max_batch_size: int = 50         # Max requests in execute_batch()
    default_timeout_ms: int = 30000  # Default execution timeout per step
```

Defined inline in `k1/fabric/fabric.py`. No separate config file.

---

## 27. Fabric Ports (6 total)

All Fabric ports use `@runtime_checkable` Protocol (structural typing).

### 27.1 ISessionStateReader

```python
class ISessionStateReader(Protocol):
    def read_section(self, session_id: str, section: str) -> Optional[Dict[str, Any]]: ...
    def read_sections(self, session_id: str, names: List[str]) -> Dict[str, Any]: ...
    def get_snapshot(self, session_id: str) -> SessionSnapshot: ...
```

Supporting type: `SessionSnapshot(session_id, sections, timestamp_ms, section_names)`.
Wired to: PolicyEngine (AffectiveRouting, CognitiveLoadRouting), ContextBuilder,
OutputValidationPipeline, AgentProvider.

### 27.2 IEventPort

```python
class IEventPort(Protocol):
    def emit(self, topic: str, payload: Dict[str, Any]) -> None: ...
    def subscribe(self, topic: str, handler: Callable) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
```

Supporting type: `SubscriptionHandle(subscription_id, topic)`.
Wired to: CapabilityRegistry, ModuleLoader, ProviderRegistry, OutputValidationPipeline,
AvailabilityTracker, HealthChecker, EventEmitter, ProactiveGapDetector.

### 27.3 IBridgePort

```python
class IBridgePort(Protocol):
    async def send_command(self, operation: str, payload: Dict, *, trace_id: str="", timeout_ms: int=0) -> BridgeCommandResult: ...
    async def query(self, operation: str, selectors: Dict, *, trace_id: str="", timeout_ms: int=0) -> BridgeCommandResult: ...
    async def route_ifl(self, route: IFLRoute, payload: Dict, *, trace_id: str="") -> BridgeCommandResult: ...
    def is_available(self) -> bool: ...
    def get_health(self) -> BridgeHealth: ...
```

Supporting types: `BridgeHealth(available, mode, last_heartbeat_ms, latency_ms, error_message)`,
`BridgeCommandResult(success, data, error_code, error_message, k0_mode, latency_ms, trace_id)`,
`IFLRoute(address, namespace, function_name, timeout_ms)`.
Wired to: ProviderFactory -> BridgeProvider.

### 27.4 IModelGatewayPort

```python
class IModelGatewayPort(Protocol):
    def create_handle(self, budget_tokens: int, model_preference: Optional[str]=None,
                      capabilities: Optional[List[str]]=None, trace_id: str="") -> ILLMHandle: ...
    def is_model_loaded(self, model_id: str) -> bool: ...
    def list_models(self) -> List[ModelInfo]: ...
    def find_model(self, required_capabilities: List[str]) -> Optional[str]: ...
```

`ILLMHandle` Protocol: `async generate(prompt, params) -> str`, properties `model_id`, `budget_tokens`.
Supporting: `ModelCapability(CHAT, TOOL_CALL, STRUCTURED, EMBED, VISION, BATCH)`,
`ModelInfo(model_id, capabilities, loaded, max_tokens, provider)`.
Wired to: ProviderFactory -> AgentProvider.

### 27.5 IPromptSystemPort

```python
class IPromptSystemPort(Protocol):
    def resolve(self, template_name: str) -> Optional[PromptTemplate]: ...
    def compile(self, template: str, variables: Dict[str, Any]) -> str: ...
```

Supporting: `PromptTemplate(name, template, version, variables, metadata)`.
Wired to: ContextBuilder.

### 27.6 IDeltaBusPort

```python
class IDeltaBusPort(Protocol):
    def emit_delta(self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]) -> None: ...
```

Supporting: `DeltaPayload(agent_id, delta_type, section, data, trace_id)`.
Fire-and-forget, synchronous, must not block.
Topic pattern: `k1.agent.{agent_id}.delta.v1`.
Wired to: ProviderFactory -> AgentProvider -> DeltaEmitter.

---

## 28. Fabric Adapters (12 total: 6 production + 6 test)

### 28.1 Production Adapters

| Adapter | Satisfies Port | Constructor | Notes |
| ------- | -------------- | ----------- | ----- |
| `SessionStateReaderAdapter` | `ISessionStateReader` | `(manager, session_id)` | Wraps real `SessionStateManager`. Production adapter for kernel. |
| `FabricBusAdapter` | `IEventPort` + `IDeltaBusPort` | `(bus: LocalBus)` | Dual-role: event emission + delta bus. Single instance shared across both protocols. Lives in `k1/bus/adapters/`. |
| `BridgeConnectionAdapter` | `IBridgePort` | `(client=None, config=BridgeConnectionConfig())` | If no client, starts in LOCAL_COLD mode. Has `reconnect()`. Phase 2 adapter. |
| `AutoDiscoveryMCPTransport` | `IMCPTransport` | Scans `k1/tools/mcp_servers/` | Auto-discovers JSON-RPC and FastMCP servers. Zero code changes to add new MCP servers. |
| `AutoDiscoveryWASMRuntime` | `IWASMRuntime` | Scans `k1/tools/wasm_modules/` | Auto-discovers WASM executor modules by directory name. |
| (Real model gateway) | `IModelGatewayPort` | TBD | Phase 2: real LLM gateway adapter. |

### 28.2 Test Adapters

| Adapter | Satisfies Port | Constructor | Test Features |
| ------- | -------------- | ----------- | ------------- |
| `TestSessionStateReaderAdapter` | `ISessionStateReader` | `()` | Dict-based. `load(session_id, section, data)` for test setup. |
| `LocalEventAdapter` | `IEventPort` | `(capture_mode=False)` | RLock-protected. `drain()`, `get_captured()`, `assert_emitted()` in capture mode. |
| `TestBridgeAdapter` | `IBridgePort` | `(available=True)` | Canned responses via `set_response(op, result)`. Capture mode. |
| `TestModelGatewayAdapter` | `IModelGatewayPort` | `()` | Returns `TestLLMHandle`. Model catalog via `add_model()`/`remove_model()`. |
| `TestPromptSystemAdapter` | `IPromptSystemPort` | `()` | Dict-based. `add_template(name, ...)`. Simple `{var}` substitution. |
| `TestDeltaBusAdapter` | `IDeltaBusPort` | `()` | Stores `CapturedDelta`. `drain()`, `get_deltas()`, `assert_emitted()`. |
| `TestMCPTransport` | `IMCPTransport` | `(connected=True)` | Canned `MCPResponse` by tool_name. `CapturedMCPCall` records. |
| `TestWASMRuntime` | `IWASMRuntime` | `(available=True)` | Canned `WASMExecutionResult` by function_name. `CapturedWASMCall` records. |

---

## 29. Fabric Factory Internal Wiring (20 Steps)

`FabricFactory._construct_fabric()` builds all internal components and returns a `Fabric` container.
Adapters are passed as params (6 port adapters + optional `mcp_transport`, `wasm_runtime`).

### 29.1 Step-by-Step Wiring Order

```text
Step 1:   Adapters (passed as params)
             state_reader, event_port, bridge, model_gateway, prompt_system,
             delta_bus, mcp_transport, wasm_runtime

Step 2:   ContractValidator()
             -- No deps. 12 semantic rules + JSON Schema validation.

Step 3:   CapabilityRegistry(validator, event_port)
             -- Central contract store. Emit registered/unregistered events.

Step 4:   ModuleLoader(registry, contracts_dir, event_port, validator)
             -- Scans contracts_dir for YAML contract files.
             -- poll_interval_s=2.0 for file watching.

Step 5:   PolicyEngine(
             security=SecurityContext(),
             affective=AffectiveRouting(state_reader),
             cognitive=CognitiveLoadRouting(state_reader),
             qos=QoSIntegration()
           )
             -- 4 dimensions: Security (hard gate), Affective (+0.2),
                Cognitive (+0.15), QoS (+0.2).
             -- Composite score = 1.0 + affective + cognitive + qos.

Step 6:   ProviderRegistry(event_port)
             -- Tracks provider configs and health state.

Step 7:   circuit_breakers: Dict[str, CircuitBreaker] = {}
             -- Shared mutable dict. HealthChecker and CapabilityFabric both
                hold reference to same dict. Populated lazily per provider.

Step 8:   ContextBuilder(state_reader, prompt_system)
             -- 6-step pipeline: contract reqs -> SessionState -> params ->
                prompt template -> token budget -> ExecutionContext.

Step 9:   ProviderFactory(
             bridge, model_gateway, state_reader, delta_bus,
             context_builder, registry, mcp_transport, wasm_runtime
           )
             -- Registers 6 handler constructors:
                MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE.

Step 10:  Resolver(
             capability_registry=registry,
             provider_matcher=ProviderMatcher(provider_registry),
             provider_selector=ProviderSelector(),
             provider_factory=provider_factory,
             policy_engine=policy_engine
           )
             -- 5-step resolve: lookup -> match -> policy -> select -> done.

Step 11:  RetrievalEngine(
             EmbeddingIndex(), HardFilter(), SoftRanker(), TopKSelector(),
             embedding_port, registry_port=registry
           )
             -- Semantic capability discovery.

Step 12:  OutputValidationPipeline(state_reader, event_port)
             -- 3-tier: Structural (hard) -> Schema (hard+coercion) -> Semantic (soft).

Step 13:  HealthChecker(
             provider_registry, AvailabilityTracker(event_port, registry.update_availability),
             circuit_breakers, event_port
           )
             -- Monitors provider health, syncs CB state, emits health_changed.

Step 14:  Bidirectional CB <-> HealthChecker reference
             -- Both hold same circuit_breakers dict. HealthChecker resets/trips
                breakers based on health transitions.

Step 15:  FabricDispatcher(event_callback)  -- production_mode ONLY
             -- Bounded parallelism: max_concurrent=10 (FAB-003).
             -- Backpressure levels: NORMAL/WARNING/SHEDDING/SATURATED.
             -- Not created in standalone/testing modes.

Step 16:  EventEmitter(event_port)
             -- Typed emission methods for all 16 Fabric events.
             -- Injects cognitive_trace_id into every payload (FAB-09).

Step 17:  CapabilityFabric(
             resolver=resolver,
             context_builder=context_builder,
             validation_pipeline=validation_pipeline,
             event_emitter=event_emitter,
             registry=registry,
             provider_factory=provider_factory,
             circuit_breakers=circuit_breakers,
             dispatcher=dispatcher,       # None if not production_mode
             config=config
           )
             -- Primary execution facade. 9-step pipeline.

Step 18:  FabricRetrieval(retrieval_engine)
             -- Semantic capability discovery facade.

Step 19:  CapabilityRegistryAPI(registry)
             -- CRUD facade for capabilities.

Step 20:  module_loader.start(watch=False)
             -- Initial contract scan (no file watching at bootstrap).
             _auto_register_providers(registry, provider_registry)
             -- Auto-registers ProviderConfig from loaded contracts.
             ProactiveGapDetector.wire_subscriptions()
             -- Subscribes to registered/unregistered/version_conflict events.
```

### 29.2 Factory Public Methods

| Method | Adapters | Dispatcher | Use Case |
| ------ | -------- | ---------- | -------- |
| `create_standalone(*, contracts_dir, config)` | All test stubs | No | Dev/unit tests |
| `create_for_testing(*, capture_events, contracts_dir, config, mcp_transport, wasm_runtime)` | Test stubs + capture | No | Integration tests |
| `create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus, *, production_mode, contracts_dir, config, embedding_port)` | Custom injection | If `production_mode=True` | Kernel bootstrap (production) |

GOTCHA: `production_mode=True` enables `FabricDispatcher` for bounded parallelism.
Without it, execution runs unbounded (fine for tests, dangerous for production).

---

## 30. Fabric Execution Pipeline (9 Steps)

`CapabilityFabric.execute(request)` is the primary entry point. Routes through
`FabricDispatcher` if configured (production_mode), then runs 9-step `_execute_impl`.

### 30.1 CapabilityFabric Slots (9)

```text
_resolver, _context_builder, _validation_pipeline, _event_emitter,
_registry, _provider_factory, _circuit_breakers, _dispatcher, _config
```

### 30.2 Execution Steps

```text
Step 1:  _event_emitter.emit_invoked()
           -> k1.capability.invoked.v1
           -> Logs request capability_name, trace_id.

Step 2:  _resolve(request)
           -> Resolver.resolve(request) -> ResolvedProvider
           -> 5-step: Registry lookup -> ProviderMatcher -> PolicyEngine -> ProviderSelector -> done
           -> Returns: contract, provider_config, policy_result
           -> Fails: ResolutionFailedError("capability_not_found" / "no_provider" / "access_denied")

Step 3:  _build_context(request, contract)
           -> ContextBuilder.build(contract, params, session_id, trace_id)
           -> 6-step: contract reqs -> SessionState fetch -> param injection ->
              prompt template -> token budget -> ExecutionContext

Step 4:  _provider_factory.create(resolved.provider_config)
           -> Instantiates appropriate provider (MCP/WASM/BRIDGE/AGENT/WORKFLOW/CONCIERGE)
           -> Dispatches to registered handler constructor

Step 5:  _execute_with_breaker(provider, provider_id, request, context, trace_id)
           -> If circuit_breakers[provider_id] exists: CB.call(provider.execute, ...)
           -> Otherwise: direct provider.execute(request, context, trace_id)
           -> CB retry: up to max_retries (default 2)
           -> asyncio.wait_for(timeout_ms)
           -> CB state machine: CLOSED -> OPEN -> HALF_OPEN -> CLOSED

Step 6:  _validate_output(result, contract, provider_type, request, context)
           -> OutputValidationPipeline.validate()
           -> Tier 1: Structural (hard fail -> fallback)
           -> Tier 2: Schema (hard fail with coercion attempt)
           -> Tier 3: Semantic (soft fail, annotate only)
           -> Short-circuits on Tier 1/2 hard failure.

Step 7:  _emit_success() or _emit_failure()
           -> k1.capability.completed.v1 or k1.capability.failed.v1

Step 8:  _update_metrics(capability_name, elapsed_ms, success)
           -> Registry.update_metrics()

Step 9:  _emit_learning(...)
           -> k1.fabric.learning.signal.v1 (K0 P09 learning loop)
```

### 30.3 Batch Execution Strategies

`execute_batch(requests, strategy)` supports three strategies:

| Strategy | Execution | Dependency Handling |
| -------- | --------- | ------------------- |
| `PARALLEL` | `asyncio.gather()` all requests | None |
| `SEQUENTIAL` | One-by-one in order | Ordered but no explicit deps |
| `DAG` | Topological wave execution | `request.params["_depends_on"]` (list of request_ids). Wave-based. Cycle detection. |

Max batch size: `config.max_batch_size` (default 50).

---

## 31. Fabric Provider System

### 31.1 Provider Protocol

```python
class CapabilityProvider(Protocol):
    async def execute(self, request: CapabilityRequest, context: ExecutionContext, trace_id: str) -> CapabilityResult: ...
    async def health_check(self) -> ProviderHealth: ...
    def capabilities(self) -> List[str]: ...
```

### 31.2 Provider Types (6)

| Provider | Type Enum | Constructor | Port Dependencies | Description |
| -------- | --------- | ----------- | ----------------- | ----------- |
| `MCPProvider` | `MCP` | `(config, transport: IMCPTransport)` | IMCPTransport | Model Context Protocol tool calls (JSON-RPC) |
| `WASMProvider` | `WASM` | `(config, runtime: IWASMRuntime)` | IWASMRuntime | WebAssembly module execution |
| `BridgeProvider` | `BRIDGE` | `(config, bridge: IBridgePort)` | IBridgePort | K0 bridge commands (cross-kernel) |
| `AgentProvider` | `AGENT` | `(config, model_gateway, state_reader, delta_bus, context_builder)` | IModelGatewayPort, ISessionStateReader, IDeltaBusPort, ContextBuilder | LLM-backed agent execution with tool calls |
| `WorkflowProvider` | `WORKFLOW` | `(config, workflow_registry, capability_lookup, orchestrator)` | IWorkflowRegistry, ICapabilityLookup, IOrchestrator | Composite workflow execution |
| `ConciergeProvider` | `CONCIERGE` | `(config, router: IConciergeRouter)` | IConciergeRouter | Concierge state routing |

### 31.3 AgentProvider Internals

The `AgentProvider` is the most complex provider, managing LLM-backed agents
with their own lifecycle, tool scoping, and delta emission.

**Agent Slots (13):**

```text
_id, _contract, _mailbox, _llm_handle, _state_reader, _tool_scope,
_context, _delta_bus, _delta_emitter, _lifecycle_state, _created_at,
_idle_since, _tokens_used, _tool_calls
```

**Agent Lifecycle FSM:**

```text
PENDING -> WARMING -> ACTIVE -> IDLE (pooled, 60s TTL) -> TERMINATED
                        |                                      ^
                        +-> DRAINING --------------------------+
```

**AgentFactory** -- 8-step instantiation:

1. Load contract (AgentContract from registry)
2. Create mailbox (per-agent ordered delivery)
3. Grant LLM handle (`model_gateway.create_handle(budget_tokens)`)
4. Grant SessionState reader (`state_reader` scoped to session)
5. Scope tools (`contract.tools_granted[]` via FAB-07)
6. Build context (ContextBuilder for agent-specific context)
7. Instantiate Agent
8. Start (transition PENDING -> WARMING -> ACTIVE)

**AgentPool** -- Keyed by contract name. Recycles IDLE agents. TTL sweep (60s).
Configurable max pool size.

**DeltaEmitter** -- Batched delta emission in 500ms window. LWW (Last Writer Wins)
merge within batch. Emits via `IDeltaBusPort` to `k1.agent.{agent_id}.delta.v1`.

### 31.4 ProviderFactory Handler Registration

Factory step 9 registers these handler constructors via `_register_provider_handlers()`:

```text
MCP       -> MCPProviderHandler(mcp_transport)
WASM      -> WASMProviderHandler(wasm_runtime)
BRIDGE    -> BridgeProviderHandler(bridge_port)
AGENT     -> AgentProviderHandler(model_gateway, state_reader, delta_bus, context_builder)
WORKFLOW  -> WorkflowProviderHandler(registry)
CONCIERGE -> ConciergeProviderHandler()
```

---

## 32. Fabric Internal Components

### 32.1 Resolver (5-step pipeline)

**Constructor:**

```python
Resolver(
    capability_registry=CapabilityRegistry,
    provider_matcher=ProviderMatcher(provider_registry),
    provider_selector=ProviderSelector(),
    provider_factory=ProviderFactory,
    policy_engine=PolicyEngine
)
```

**Resolution pipeline:**

| Step | Action | Failure |
| ---- | ------ | ------- |
| 1 | Registry lookup: `registry.lookup(capability_name)` -> contract | `ResolutionFailedError("capability_not_found")` |
| 2 | Provider matching: `provider_matcher.match(contract)` -> [ProviderConfig] | `ResolutionFailedError("no_provider")` |
| 3 | Policy evaluation: `policy_engine.evaluate(candidates, contract, request)` -> [ScoredCandidate] | Errors return neutral score (fault-isolated) |
| 4 | Provider selection: `provider_selector.select(scored)` -> ResolvedProvider | `ResolutionFailedError("access_denied")` or `("no_provider")` |
| 5 | (Caller creates provider via `provider_factory.create()` separately) | -- |

### 32.2 PolicyEngine (4 dimensions)

**Constructor:**

```python
PolicyEngine(
    security=SecurityContext(),          # REQUIRED (ValueError if None)
    affective=AffectiveRouting(state_reader),   # Optional, +0.0 to +0.2
    cognitive=CognitiveLoadRouting(state_reader), # Optional, +0.0 to +0.15
    qos=QoSIntegration(),               # Optional, +0.0 to +0.2
    tools_granted=None                   # Optional FrozenSet for sub-agent scoping
)
```

**Score formula:** `final_score = 1.0 + affective + cognitive + qos`

| Dimension | Type | Range | Failure Mode |
| --------- | ---- | ----- | ------------ |
| Security | Hard gate | allowed=True/False | Rejected immediately (score=0.0) |
| Affective | Soft scoring | +0.0 to +0.2 | Neutral 0.0 on error |
| Cognitive | Soft scoring | +0.0 to +0.15 | Neutral 0.0 on error |
| QoS | Per-provider soft | +0.0 to +0.2 | Neutral 0.0 on error |

Each dimension is fault-isolated: errors in soft dimensions return neutral score.
Deterministic per FAB-10.

### 32.3 ContextBuilder (6-step pipeline)

**Constructor:** `ContextBuilder(state_reader=None, prompt_system=None, config=None)`

| Step | Action |
| ---- | ------ |
| 1 | Read contract context requirements |
| 2 | Fetch from SessionState (via `state_reader`) |
| 3 | Inject request params |
| 4 | Resolve prompt template (via `prompt_system`) |
| 5 | Apply token budget (ContextBudget) |
| 6 | Package into ExecutionContext |

Ports can be `None` for graceful degradation.

### 32.4 OutputValidationPipeline (3 tiers)

**Constructor:** `OutputValidationPipeline(state_reader=None, event_port=None, config=None, schema_compiler=None)`

| Tier | Validator | Failure Mode | Behavior |
| ---- | --------- | ------------ | -------- |
| 1 | `StructuralValidator` | Hard fail | Rejects malformed results. Invokes `ValidationFallback.handle()`. |
| 2 | `SchemaValidator` | Hard fail + coercion | Runs on success results with data. Coercion attempt on failure. |
| 3 | `SemanticValidator` | Soft fail | Never rejects. Annotates only. Only for `SEMANTIC_PROVIDER_TYPES`. |

Pipeline short-circuits on Tier 1 or Tier 2 hard failures.

### 32.5 ContractValidator

**Constructor:** `ContractValidator()` -- no deps.

12 semantic rules + JSON Schema validation. All contracts validated before
registration (FAB-12). Four contract parsers share the validator:

| Parser | Root Key | Output Type |
| ------ | -------- | ----------- |
| `ToolContractParser` | `tool_contract` | `CapabilityContract` |
| `AgentContractParser` | `agent_contract` | `AgentContract` |
| `WorkflowContractParser` | `workflow_contract` | `WorkflowContract` |
| `PromptContractParser` | `prompt_contract` | `PromptContract` |

### 32.6 ModuleLoader

**Constructor:** `ModuleLoader(registry, contracts_dir, event_port, validator, poll_interval_s=2.0)`

| Method | Type | Description |
| ------ | ---- | ----------- |
| `start(watch=True)` | sync | Initial `scan_directory()` + optional `start_watching()` daemon thread |
| `stop()` | sync | Calls `stop_watching()`. Idempotent. |
| `scan_directory()` | sync | Walks contracts_dir, parses YAML, registers contracts |
| `start_watching()` | sync | Daemon thread (`fabric-module-watcher`), polls for new/modified/deleted files |
| `stop_watching()` | sync | Sets stop event, joins thread with timeout |

GOTCHA: At bootstrap, `start(watch=False)` is called (step 20). File watching
is not enabled until explicit call to `start_watching()`.

---

## 33. Fabric Health Infrastructure

### 33.1 HealthChecker

**Constructor:**

```python
HealthChecker(
    provider_registry=ProviderRegistry,         # required
    availability_tracker=AvailabilityTracker,   # required
    provider_instances=None,                    # Dict[str, ICapabilityProvider]
    circuit_breakers=None,                      # Dict[str, ICircuitBreaker] (shared with Fabric)
    event_port=None,                            # IEventPort
    config=None                                 # HealthCheckerConfig
)
```

**Lifecycle:**

| Method | Action |
| ------ | ------ |
| `start()` | `_running = True`, creates `asyncio.ensure_future(_run_loop())` |
| `stop()` | `_running = False`, cancels task, awaits with CancelledError handling |

**What it monitors (per check cycle):**

1. Calls `provider.health_check()` with `asyncio.wait_for(timeout=check_timeout_s)`
2. Maps result to `ProviderStatus` (HEALTHY/UNHEALTHY/DEGRADED)
3. Tracks consecutive failures per provider
4. After `failure_threshold` consecutive failures -> forces UNHEALTHY
5. Updates `ProviderRegistry` health cache
6. Updates `AvailabilityTracker` on state change
7. Syncs `CircuitBreaker` on state change (bidirectional integration)
8. Emits `k1.fabric.provider.health.changed.v1` on state change

### 33.2 AvailabilityTracker

**Constructor:** `AvailabilityTracker(event_port=None, registry_updater=None, max_history=DEFAULT_MAX_HISTORY, enforce_progressive_recovery=True)`

**State machine:** `ONLINE <-> DEGRADED <-> OFFLINE`

CRITICAL: **OFFLINE -> ONLINE is blocked**. Must recover through DEGRADED first
(progressive recovery enforcement). Same-state updates are no-ops.

Thread-safe via RLock on all mutations.

### 33.3 FabricDispatcher (production_mode only)

**Constructor:** `FabricDispatcher(config=None, event_callback=None)`

**Config:**

| Field | Default | Description |
| ----- | ------- | ----------- |
| `max_concurrent` | `10` (FAB-003) | Semaphore limit for in-flight requests |
| `warning_threshold` | `0.80` | 80% utilization -> WARNING |
| `shedding_threshold` | `0.95` | 95% utilization -> SHEDDING |
| `emit_events` | `True` | Emit backpressure events |

**Pressure levels:**

| Level | Condition | Behavior |
| ----- | --------- | -------- |
| NORMAL | utilization < 80% | All requests pass |
| WARNING | utilization >= 80% | Emits `k1.fabric.pressure.warning.v1` |
| SHEDDING | utilization >= 95% | Emits `k1.fabric.pressure.shedding.v1`. BACKGROUND priority rejected. |
| SATURATED | utilization >= 100% | ALL requests rejected |

GOTCHA: Dispatcher is ONLY created when `production_mode=True` in `create_with_ports()`.
Standalone/testing factories skip it entirely.

---

## 34. Fabric Circuit Breaker System

### 34.1 CircuitBreaker

**Slots (8):**

```text
_provider_id, _config, _on_state_change, _lock, _state,
_failures, _opened_at_ms, _half_open_permit, _consecutive_successes
```

**Constructor:** `CircuitBreaker(provider_id, config: CircuitBreakerConfig, on_state_change=None)`

**State Machine:**

```text
CLOSED --[failure_threshold in failure_window]--> OPEN
OPEN   --[half_open_after_ms elapsed]-----------> HALF_OPEN
HALF_OPEN --[probe success]---------------------> CLOSED
HALF_OPEN --[probe fails]-----------------------> OPEN
```

**Public interface:**

| Method | Signature | Description |
| ------ | --------- | ----------- |
| `call` | `async (execute_fn, request, context, trace_id) -> CapabilityResult` | Execute through CB with retry (max_retries). Never raises. |
| `reset` | `()` | Force to CLOSED (HealthChecker recovery) |
| `trip` | `()` | Force to OPEN |
| `allow_probe` | `()` | Allow single HALF_OPEN probe |

### 34.2 Per-Provider CB Configs

| Config | Timeout | Threshold | Window | Half-Open | Retries | Fallback Error |
| ------ | ------- | --------- | ------ | --------- | ------- | -------------- |
| `MCP_LOCAL_CONFIG` | 10s | 3/min | 60s | 30s | 2 | `tool_offline` |
| `MCP_REMOTE_CONFIG` | 15s | 3/min | 60s | 30s | 2 | `tool_offline` |
| `WASM_CONFIG` | 5s | 5/min | 60s | 15s | 2 | `computation_failed` |
| `BRIDGE_CONFIG` | 10s | 3/min | 60s | 30s | 2 | `bridge_offline` |
| `AGENT_CONFIG` | 30s | 2/min | 60s | 30s | 2 | `agent_execution_failed` |
| `WORKFLOW_CONFIG` | 60s | 1/min | 60s | 60s | 1 | `workflow_failed` |
| `CONCIERGE_CONFIG` | 5s | 5/min | 60s | 10s | 2 | `concierge_state_failed` |
| `DEFAULT_CONFIG` | 30s | 5/min | 60s | 30s | 2 | `capability_unavailable` |

Resolution order: explicit override > MCP local/remote detection > type-specific > default.

### 34.3 Ownership

Circuit breakers are stored in a shared `Dict[str, CircuitBreaker]` created in
factory step 7. Both `CapabilityFabric` and `HealthChecker` hold references to
the same dict. HealthChecker `reset()`/`trip()` breakers based on health transitions.
New breakers are created lazily on first request to a provider.

---

## 35. Fabric Event Reference

### 35.1 Emitted Topics (16)

| Constant | Topic String | Emitter | Description |
| -------- | ------------ | ------- | ----------- |
| `TOPIC_CAPABILITY_INVOKED` | `k1.capability.invoked.v1` | CapabilityFabric step 1 | Execution request received |
| `TOPIC_CAPABILITY_COMPLETED` | `k1.capability.completed.v1` | CapabilityFabric step 7 | Execution succeeded |
| `TOPIC_CAPABILITY_FAILED` | `k1.capability.failed.v1` | CapabilityFabric step 7 | Execution failed |
| `TOPIC_LEARNING_SIGNAL` | `k1.fabric.learning.signal.v1` | CapabilityFabric step 9 | K0 P09 learning loop signal |
| `TOPIC_CAPABILITY_REGISTERED` | `k1.fabric.capability.registered.v1` | Registry / Fabric.register() | New contract registered |
| `TOPIC_CAPABILITY_UNREGISTERED` | `k1.fabric.capability.unregistered.v1` | Registry / Fabric.unregister() | Contract removed |
| `TOPIC_VERSION_CONFLICT` | `k1.fabric.capability.version.conflict.v1` | Registry version handling | Contract version collision |
| `TOPIC_CONTRACT_VALIDATION_FAILED` | `k1.fabric.contract.validation.failed.v1` | ContractValidator | Contract failed validation |
| `TOPIC_OUTPUT_VALIDATION_FAILED` | `k1.fabric.output.validation.failed.v1` | OutputValidationPipeline | Output failed validation |
| `TOPIC_PROVIDER_HEALTH_CHANGED` | `k1.fabric.provider.health.changed.v1` | HealthChecker | Provider health state changed |
| `TOPIC_CONTRACT_UPDATED` | `k1.fabric.capability.contract_updated.v1` | ProactiveGapDetector | Contract updated (re-emit of registered/unregistered) |
| `TOPIC_PRESSURE_WARNING` | `k1.fabric.pressure.warning.v1` | FabricDispatcher | Utilization >= 80% |
| `TOPIC_PRESSURE_SHEDDING` | `k1.fabric.pressure.shedding.v1` | FabricDispatcher | Utilization >= 95%, shedding BACKGROUND |
| `TOPIC_AGENT_CREATED` | `k1.fabric.agent.created.v1` | BuildAgentHandler | New agent instantiated |
| `TOPIC_AGENT_EXPIRED` | `k1.fabric.agent.expired.v1` | Session cleanup | Agent expired from pool |
| `TOPIC_META_OP_BLOCKED` | `k1.fabric.meta.operation.blocked.v1` | MetaOperationValidator | Meta-operation blocked by policy |

### 35.2 Consumed Topics (4)

| Constant | Topic String | Consumer | Description |
| -------- | ------------ | -------- | ----------- |
| `TOPIC_STEP_EXECUTE` | `k1.orchestration.step.execute.v1` | Fabric | Step execution request from Orchestrator |
| `TOPIC_DISCOVERY_REQUEST` | `k1.planner.discovery.request.v1` | Fabric | Discovery request from Planner |
| `TOPIC_HEALTH_CHECK_REQUEST` | `k1.fabric.provider.health.check.v1` | HealthChecker | On-demand health check trigger |
| `TOPIC_MCP_TOOL_DISCOVERED` | `k1.mcp.tool.discovered.v1` | GapDetector/ModuleLoader | MCP tool auto-registration |

### 35.3 EventEmitter

**Constructor:** `EventEmitter(event_port=None)` -- single dependency.

All `_emit()` calls inject `cognitive_trace_id` into payload (FAB-09).
If no `event_port` configured, events are silently dropped.

Typed methods: `emit_invoked`, `emit_completed`, `emit_failed`, `emit_learning_signal`,
`emit_registered`, `emit_unregistered`, `emit_contract_updated`, `emit_version_conflict`,
`emit_contract_validation_failed`, `emit_output_validation_failed`, `emit_health_changed`,
`emit_pressure_warning`, `emit_pressure_shedding`, `emit_agent_created`,
`emit_agent_expired`, `emit_meta_blocked`.

### 35.4 ProactiveGapDetector

Subscribes at factory step 20 (`wire_subscriptions()`) to:

- `k1.fabric.capability.registered.v1`
- `k1.fabric.capability.unregistered.v1`
- `k1.fabric.capability.version.conflict.v1`
- `k1.mcp.tool.discovered.v1`

Re-emits as `k1.fabric.capability.contract_updated.v1` (unified signal consumed by
Orchestrator's ProactiveGapDetector at init step 9a).
Also auto-registers MCP tools via `ModuleLoader.register_from_dict()`.

---

## 36. Fabric Shutdown Sequence

`Fabric.shutdown()` performs two steps:

```text
Step 1:  await health_checker.stop()
           -- Sets _running=False, cancels health check loop task.
           -- Wrapped in try/except (logs warning on failure).
           -- Guarded by: if health_checker is not None.

Step 2:  module_loader.stop()  (sync)
           -- Calls stop_watching(). Joins watcher daemon thread.
           -- Wrapped in try/except (logs warning on failure).
           -- Guarded by: if module_loader is not None.
```

Note: Fabric shutdown must happen AFTER Orchestrator shutdown (Orchestrator uses
FabricGatewayAdapter which wraps the Fabric facade) and BEFORE SessionState shutdown
(Fabric uses SessionStateReaderAdapter which wraps SessionStateManager).

---

## 37. Fabric Core Types

### 37.1 Enums

| Enum | Values | Used By |
| ---- | ------ | ------- |
| `ProviderType` | `MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE` | ProviderFactory, CB config selection |
| `WFQPriority` | `URGENT, REALTIME, INTERACTIVE, BACKGROUND` | FabricDispatcher shedding |
| `SafetyBand` | `GREEN, AMBER, RED, CRISIS` | PolicyEngine routing |
| `Availability` | `ONLINE, DEGRADED, OFFLINE` | AvailabilityTracker |
| `Tier` | `LOW, MEDIUM, HIGH` | QoS integration |
| `RequestStatus` | `PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED, TIMED_OUT` | Capability execution |
| `BatchStrategy` | `PARALLEL, SEQUENTIAL, DAG` | execute_batch() |
| `AgentLifecycleState` | `PENDING, WARMING, ACTIVE, IDLE, DRAINING, TERMINATED` | AgentProvider |

### 37.2 Key Dataclasses

| Type | Frozen | Key Fields |
| ---- | ------ | ---------- |
| `CapabilityRequest` | Yes | `capability_name, params, session_id, trace_id, priority, timeout_ms` |
| `CapabilityResult` | Yes | `success, data, error, latency_ms, provider_id, trace_id` + factory methods |
| `ErrorInfo` | -- | `code, message, details` |
| `ProviderConfig` | -- | `provider_id, provider_type, capabilities, health_endpoint` |
| `ExecutionContext` | -- | `contract, params, session_data, prompt, budget, trace_id` |
| `CapabilityContract` | -- | `name, version, domain, input_schema, output_schema, provider_id` |
| `AgentContract` | -- | `name, tools_granted, model_preference, budget_tokens, context_requirements` |
| `WorkflowContract` | -- | `name, steps, edges, acyclicity_validated` |
| `PromptContract` | -- | `name, template, version, variables, metadata` |

---

## 38. Fabric Bootstrap Gotchas

| # | Gotcha | Consequence if Violated |
| - | ------ | ----------------------- |
| F-01 | `FabricBusAdapter` is a SINGLE instance satisfying BOTH `IEventPort` and `IDeltaBusPort` | Two instances means events and deltas go to different buses |
| F-02 | `SessionStateReaderAdapter(manager, session_id)` takes TWO args -- the manager AND a session_id | AttributeError or wrong session reads |
| F-03 | `production_mode=True` must be passed to `create_with_ports()` for production kernel | No FabricDispatcher -> unbounded parallelism, no backpressure, no shedding |
| F-04 | `module_loader.start(watch=False)` at bootstrap. Call `start_watching()` explicitly if hot-reload wanted | Missing contracts if added after bootstrap, or unwanted daemon thread in tests |
| F-05 | HealthChecker and CapabilityFabric share the SAME `circuit_breakers` dict reference (step 7/14) | Stale CB state, health checker and execution out of sync |
| F-06 | AvailabilityTracker enforces progressive recovery: OFFLINE -> DEGRADED -> ONLINE (cannot skip DEGRADED) | State transition rejected, provider stuck in OFFLINE |
| F-07 | Fabric shutdown AFTER Orchestrator, BEFORE SessionState | Orchestrator uses FabricGatewayAdapter; SessionState needed by Fabric's SessionStateReader |
| F-08 | `FabricConfig` only has 2 fields (`max_batch_size`, `default_timeout_ms`). Most config lives in component-level configs. | Looking for config fields in wrong place |
| F-09 | Contract files must be in `contracts_dir` at bootstrap time for `scan_directory()` to find them | Empty capabilities registry if contracts_dir is wrong or empty |
| F-10 | `EventEmitter` silently drops events if `event_port=None` | No events emitted, but no error either -- silent failure |
| F-11 | CB per-provider configs (`MCP_LOCAL_CONFIG` vs `MCP_REMOTE_CONFIG`) auto-selected by provider characteristics | Wrong timeout/threshold if provider type mismatch |
| F-12 | `create_with_ports()` requires ALL 6 port adapters -- no optional ports (unlike Orchestrator's IAdminPort) | TypeError on factory call |

---

## 39. Fabric File Locations Reference

| What | Path |
| ---- | ---- |
| Factory | `k1/fabric/factory.py` |
| Fabric container + facades | `k1/fabric/fabric.py` |
| FabricConfig | `k1/fabric/fabric.py` (inline, line ~181) |
| ISessionStateReader | `k1/fabric/ports/state_reader.py` |
| IEventPort | `k1/fabric/ports/event_port.py` |
| IBridgePort | `k1/fabric/ports/bridge_port.py` |
| IModelGatewayPort | `k1/fabric/ports/model_gateway.py` |
| IPromptSystemPort | `k1/fabric/ports/prompt_system.py` |
| IDeltaBusPort | `k1/fabric/ports/delta_bus.py` |
| SessionStateReaderAdapter | `k1/fabric/adapters/sessionstate_reader.py` |
| BridgeConnectionAdapter | `k1/fabric/adapters/bridge_connection.py` |
| Test adapters | `k1/fabric/adapters/test_*.py` (6 files) |
| LocalEventAdapter | `k1/fabric/adapters/local_event.py` |
| FabricBusAdapter | `k1/bus/adapters/fabric_adapter.py` |
| Providers | `k1/fabric/providers/*.py` |
| AgentProvider | `k1/fabric/providers/agent_provider.py` |
| Resolver | `k1/fabric/provider_resolution/resolver.py` |
| PolicyEngine | `k1/fabric/policy/policy_engine.py` |
| ContextBuilder | `k1/fabric/core/context_builder.py` |
| ModuleLoader | `k1/fabric/core/module_loader.py` |
| OutputValidationPipeline | `k1/fabric/output_validation/pipeline.py` |
| HealthChecker | `k1/fabric/health/health_checker.py` |
| AvailabilityTracker | `k1/fabric/health/availability_tracker.py` |
| CircuitBreaker | `k1/fabric/circuit_breaker/breaker.py` |
| CB configs | `k1/fabric/circuit_breaker/breaker_config.py` |
| FabricDispatcher | `k1/fabric/concurrency/dispatcher.py` |
| EventEmitter | `k1/fabric/events/event_emitter.py` |
| Event topic constants | `k1/fabric/events/topics.py` |
| ContractValidator | `k1/fabric/contracts/validator.py` |
| Contract parsers | `k1/fabric/contracts/*.py` (4 parsers) |
| Types | `k1/fabric/types.py` |

---

## PART C: SessionState Deep Dive

---

## 40. SessionState Architecture Overview

SessionState is the **structured memory system** of K1. It manages a 96KB tiered
data model (HOT + WARM) with FlatBuffer serialization, SQLite-backed LOCAL COLD
archival, pressure-based eviction, and tier migration. The `SessionStateManager`
is the central facade coordinating all subsystems.

### 40.1 Memory Budget

| Tier | Budget | Sections | Evictable |
| ---- | ------ | -------- | --------- |
| HOT | 48KB (49,152 bytes) | 8 sections | 6 of 8 (control + meta NEVER evict) |
| WARM | 48KB (49,152 bytes) | 4 sections | All 4 |
| LOCAL COLD | Unbounded (SQLite) | Archive store | n/a |
| **TOTAL** | **96KB (98,304 bytes)** | **12 sections** | |

### 40.2 ManagerState FSM

```text
CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED
               |                      |
               +-> ERROR              +-> ERROR
```

Valid transitions: `CREATED/STOPPED -> STARTING`, `STARTING -> RUNNING/ERROR`,
`RUNNING -> STOPPING`, `STOPPING -> STOPPED/ERROR`.

---

## 41. SessionState Ports (5 total: 4 mandatory + 1 optional)

All SessionState ports use ABC (abstract base classes), NOT structural Protocol.

### 41.1 IStoragePort (ABC)

```python
class IStoragePort(ABC):
    @property is_available -> bool
    @property storage_type -> str
    def archive(self, section: str, data: bytes, metadata: Dict) -> ArchiveResult
    def restore(self, section: str, filters: Dict) -> RestoreResult
    def list_archives(self, session_id: str) -> List[ArchiveEntry]
    def delete(self, archive_id: str) -> bool
```

Supporting types:

- `ArchiveResult(success, archive_id, size_bytes, duration_ms, error)`
- `RestoreResult(success, data, archive_id, size_bytes, duration_ms, error)`
- `ArchiveEntry(archive_id, session_id, section, size_bytes, created_at_ms, metadata)`

### 41.2 IEventPort (ABC)

```python
class IEventPort(ABC):
    @property is_connected -> bool
    def emit(self, event_type: str, payload: Any) -> None
    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> str
    def unsubscribe(self, subscription_id: str) -> bool
    def emit_batch(self, events: list[tuple[str, Any]]) -> None  # default impl
```

NOTE: SessionState `IEventPort` is an ABC (not Protocol) and uses different topic
format than Fabric's `IEventPort`. Topics: `sessionstate.{category}.{action}`.
The `SessionBusAdapter` bridges this to the Bus.

### 41.3 IWriterPort (ABC)

```python
class IWriterPort(ABC):
    @property writer_id -> str
    @property is_connected -> bool
    def request_mutation(self, request: MutationRequest) -> MutationResponse
    def batch_mutations(self, batch: BatchRequest) -> BatchResult
    def validate_writer(self, writer_id: str) -> WriterAuthorization
    def cancel_request(self, request_id: str) -> bool        # default: False
    def get_pending_count(self) -> int                        # default: 0
    def get_stats(self) -> Dict[str, Any]                     # default: {}
```

Key types:

- `MutationRequest` -- request_id, section, operation, data, estimated_bytes, writer_id,
  cognitive_trace_id, priority(MutationPriority), delegation_chain, created_at_ms, timeout_ms, metadata
- `MutationResponse` -- request_id, status(MutationStatus), approved, new_size_bytes, bytes_delta,
  available_bytes, section, operation, reason, rejection_category, error, duration_ms
- `BatchRequest` -- batch_id, requests, writer_id, cognitive_trace_id, stop_on_rejection
- `BatchResult` -- batch_id, total_requests, applied/rejected/failed/cancelled count, responses,
  total_bytes_delta, duration_ms, stopped_early

Enums:

- `MutationPriority` -- CRITICAL, HIGH, NORMAL, LOW, DEFERRED
- `MutationStatus` -- PENDING, VALIDATING, APPROVED, APPLIED, REJECTED, FAILED, CANCELLED
- `RejectionCategory` -- CAPACITY, AUTHORIZATION, VALIDATION, LOCKED, EMERGENCY, INTERNAL

### 41.4 ILifecyclePort (ABC)

```python
class ILifecyclePort(ABC):
    @property state -> LifecycleState
    @property session_id -> str
    @property config -> LifecycleConfig
    @property started_at_ms -> int
    @property checkpoint_count -> int
    @property last_checkpoint_ms -> int
    def start(self, restore_if_exists: bool = True) -> StartResult
    def stop(self, checkpoint_before_stop: bool = True) -> StopResult
    def health(self) -> HealthStatus
    def checkpoint(self, trigger: CheckpointTrigger = MANUAL) -> CheckpointResult
    def request_shutdown(self) -> None          # default: calls stop()
    def get_uptime_ms(self) -> int              # default impl
    def is_running(self) -> bool                # default impl
    def can_checkpoint(self) -> bool            # default impl
```

Key types:

- `LifecycleConfig` -- checkpoint_interval_ms(30000), restore_on_start(True),
  checkpoint_on_stop(True), max_start_duration_ms(5000), max_stop_duration_ms(5000),
  health_check_interval_ms(0). Factories: `.default()`, `.testing()` (interval=0, restore=False)
- `HealthStatus` -- healthy, state, pressure_level, hot/warm_utilization_pct,
  total_size_bytes, last_checkpoint_ms, checkpoint_count, uptime_ms, turn_count, mutation_count, error
- `CheckpointResult` -- success, checkpoint_id, trigger, size_bytes, sections_checkpointed,
  duration_ms, sla_met, error. `SLA_THRESHOLD_MS = 50.0`

Enums:

- `LifecycleState` -- CREATED, STARTING, RUNNING, STOPPING, STOPPED, ERROR
  (with `can_start()`, `can_stop()`, `can_checkpoint()`, `is_operational()`, `is_terminal()`)
- `CheckpointTrigger` -- PERIODIC, MANUAL, STOP, PRESSURE, EMERGENCY, MIGRATION, EVICTION
- `RestoreSource` -- FRESH, LOCAL_COLD, K0, CHECKPOINT
- `PressureLevel` -- NORMAL, ELEVATED, HIGH, CRITICAL

### 41.5 IK0SyncPort (ABC, optional)

```python
class IK0SyncPort(ABC):
    @property is_available -> bool
    def sync_to_k0(self, session_id: str) -> SyncResult
    def restore_from_k0(self, session_id: str) -> RestoreFromK0Result
    def get_sync_status(self, session_id: str) -> SyncStatus
    def cancel_sync(self, session_id: str) -> bool
```

`SyncStatus` enum: PENDING, SYNCING, SYNCED, FAILED, OFFLINE.

**NullSyncPort** (concrete, in same file): `is_available` always False, all operations
return offline/failure results. Used until Bridge is live.

---

## 42. SessionState Adapters (5 total: 2 storage + 1 event + 1 writer + 1 lifecycle)

### 42.1 Storage Adapters

| Adapter | Implements | Constructor | Notes |
| ------- | ---------- | ----------- | ----- |
| `SQLiteStorageAdapter` | `IStoragePort` | `(db_path: Optional[Path]=None)` | Default: `~/.familyos/k1/sessionstate.db`. WAL mode, NORMAL sync. 4 tables. Production. |
| `InMemoryStorageAdapter` | `IStoragePort` | `()` | Dict-based. `storage_type="memory"`. Testing only. |

**SQLite tables:**

| Table | Purpose |
| ----- | ------- |
| `st_session_checkpoints` | Checkpoint snapshots (FlatBuffer-serialized sections) |
| `st_beliefs_archive` | Evicted/demoted beliefs data |
| `st_history_archive` | Evicted/demoted history data |
| `st_narrative_archive` | Evicted/demoted narrative data |

All tables: `id TEXT PK, session_id TEXT NOT NULL, section TEXT, data BLOB NOT NULL,
size_bytes INTEGER, created_at_ms INTEGER, metadata TEXT`.
SQLite PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`.

### 42.2 Event Adapter

| Adapter | Implements | Constructor | Notes |
| ------- | ---------- | ----------- | ----- |
| `LocalEventAdapter` | `IEventPort` | `(capture_mode: bool=False)` | Internal dispatch thread (daemon). `_handlers` dict, `_event_queue`. `is_connected` always True. Capture mode stores events for test assertions. |

NOTE: For kernel bootstrap, use `SessionBusAdapter(bus)` instead (lives in `k1/bus/adapters/`).
`LocalEventAdapter` is for standalone/testing; `SessionBusAdapter` bridges to the Bus.

### 42.3 Writer Adapter

| Adapter | Implements | Constructor | Notes |
| ------- | ---------- | ----------- | ----- |
| `DirectWriterAdapter` | `IWriterPort` | `(manager, guard: MutationGuard, writer_id="direct", authorized_writers=None)` | Bypasses Concierge, calls MutationGuard directly. `authorized_writers=None` means all allowed. Slots: `_manager`, `_guard`, `_writer_id`, `_authorized_writers`, `_lock`, `_stats`. |

### 42.4 Lifecycle Adapter

| Adapter | Implements | Constructor | Notes |
| ------- | ---------- | ----------- | ----- |
| `StandaloneLifecycle` | `ILifecyclePort` | `(manager, config=None, checkpoint_interval_s=None)` | Context manager (`__enter__`/`__exit__`). Daemon `threading.Timer` for periodic checkpoints. Slots: `_manager`, `_config`, `_state`, `_checkpoint_timer`, `_started_at_ms`, `_last_checkpoint_ms`, `_checkpoint_count`, `_lock`, `_error_message`. |

---

## 43. SessionStateManager Constructor Reference

### 43.1 Constructor

```python
SessionStateManager(
    session_id: str,
    storage_port: IStoragePort,
    event_port: IEventPort,
    writer_port: IWriterPort,
    lifecycle_port: ILifecyclePort,
    local_cold_archive: Optional[LocalColdArchive] = None,
)
```

### 43.2 Slots (18)

```text
_session_id,                  # str
_storage_port,                # IStoragePort (SQLite or InMemory)
_event_port,                  # IEventPort (LocalEventAdapter or SessionBusAdapter)
_writer_port,                 # IWriterPort (DirectWriterAdapter)
_lifecycle_port,              # ILifecyclePort (StandaloneLifecycle)
_hot,                         # HotTier (8 sections, 48KB)
_warm,                        # WarmTier (4 sections, 48KB)
_local_cold,                  # LocalColdTier (SQLite-backed archive)
_local_cold_archive,          # LocalColdArchive (raw SQLite wrapper)
_size_tracker,                # SizeTracker (byte accounting for all sections)
_mutation_guard,              # MutationGuard (preflight validation)
_eviction_engine,             # EvictionEngine (pressure-based eviction)
_migration_engine,            # MigrationEngine (tier migration: HOT -> WARM)
_state,                       # ManagerState (CREATED -> RUNNING -> STOPPED)
_write_lock,                  # threading.RLock (single-writer protection)
_last_mutation_ms,            # int (timestamp of last mutation)
_started_at_ms,               # int (timestamp of start())
_mutation_count,              # int (total mutations applied)
```

### 43.3 Internal Wiring in Constructor

```text
Step 1:   Store all ports (storage, event, writer, lifecycle)
Step 2:   _state = ManagerState.CREATED
Step 3:   _write_lock = threading.RLock()
Step 4:   _last_mutation_ms = 0, _started_at_ms = 0, _mutation_count = 0
Step 5:   _size_tracker = SizeTracker()
Step 6:   _mutation_guard = MutationGuard(size_tracker)
Step 7:   _local_cold_archive = local_cold_archive or LocalColdArchive()
Step 8:   _hot = HotTier(session_id=session_id)       # creates 8 sections
Step 9:   _warm = WarmTier(session_id=session_id, local_cold=local_cold_archive)  # creates 4 sections
Step 10:  _local_cold = LocalColdTier(storage=local_cold_archive, session_id=session_id)
Step 11:  _eviction_engine = EvictionEngine(size_tracker, local_cold, mutation_guard, session_id)
Step 12:  _migration_engine = MigrationEngine(size_tracker, mutation_guard, session_id)
```

### 43.4 Properties

| Property | Type | Description |
| -------- | ---- | ----------- |
| `session_id` | `str` | Session identifier |
| `state` | `ManagerState` | Current lifecycle state |
| `is_running` | `bool` | `state == RUNNING` |
| `hot` | `HotTier` | HOT tier (8 sections) |
| `warm` | `WarmTier` | WARM tier (4 sections) |
| `local_cold` | `LocalColdTier` | LOCAL COLD tier |
| `size_tracker` | `SizeTracker` | Byte accounting |
| `mutation_guard` | `MutationGuard` | Preflight validation |
| `eviction_engine` | `EvictionEngine` | Pressure-based eviction |
| `migration_engine` | `MigrationEngine` | Tier migration engine |

---

## 44. SessionState Factory Internal Wiring

### 44.1 create_standalone

```python
SessionStateFactory.create_standalone(
    session_id: Optional[str] = None,      # default: "session-{uuid[:12]}"
    db_path: Optional[Path] = None,        # default: ~/.familyos/k1/sessionstate.db
    checkpoint_interval_s: float = 30.0,   # periodic checkpoint interval
) -> SessionStateManager
```

**Wiring steps:**

```text
Step 1:  session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
Step 2:  Resolve db_path, mkdir parent
Step 3:  storage = SQLiteStorageAdapter(db_path=resolved_path)
Step 4:  events = LocalEventAdapter(capture_mode=False)
Step 5:  archive = LocalColdArchive(db_path=resolved_path)
Step 6:  manager = SessionStateManager(session_id, storage, events,
           writer_port=None, lifecycle_port=None,
           local_cold_archive=archive)
Step 7:  writer = DirectWriterAdapter(manager, guard=manager.mutation_guard, writer_id="direct")
Step 8:  lifecycle = StandaloneLifecycle(manager, checkpoint_interval_s=checkpoint_interval_s)
Step 9:  manager._writer_port = writer      # post-construction injection
Step 10: manager._lifecycle_port = lifecycle # post-construction injection
```

GOTCHA: Writer and Lifecycle are injected POST-CONSTRUCTION because they need
the manager reference (circular dependency, same pattern as Orchestrator's AdminHttpAdapter).

### 44.2 create_for_testing

```python
SessionStateFactory.create_for_testing(
    session_id: Optional[str] = None,  # default: "test-{uuid[:8]}"
) -> SessionStateManager
```

**Wiring:**

```text
Step 1:  storage = InMemoryStorageAdapter()
Step 2:  events = LocalEventAdapter(capture_mode=True)
Step 3:  manager = SessionStateManager(session_id, storage, events,
           writer_port=None, lifecycle_port=None, local_cold_archive=None)
Step 4:  writer = DirectWriterAdapter(manager, guard=manager.mutation_guard, writer_id="test")
Step 5:  lifecycle = StandaloneLifecycle(manager, config=LifecycleConfig.testing())
Step 6:  Post-inject writer + lifecycle into manager
```

### 44.3 create_with_ports (kernel bootstrap)

```python
SessionStateFactory.create_with_ports(
    session_id: str,                      # required
    storage: IStoragePort,                # required (validates isinstance)
    events: IEventPort,                   # required (validates isinstance)
    writer: IWriterPort,                  # required (validates isinstance)
    lifecycle: ILifecyclePort,            # required (validates isinstance)
    k0_sync: Optional[IK0SyncPort] = None, # optional
) -> SessionStateManager
```

- Validates all 4 mandatory ports via `_validate_port()` -- raises `PortProtocolError` if `isinstance()` fails.
- Creates manager with all ports injected directly (NO post-construction injection needed).
- If `k0_sync` provided: `manager._k0_sync_port = k0_sync`.

GOTCHA: `create_with_ports()` does NOT create writer or lifecycle internally; they must
be pre-constructed by the caller. This is the method used in kernel bootstrap.

---

## 45. SessionState Lifecycle

### 45.1 start() Sequence

```text
Step 1:  Validate state is CREATED or STOPPED
Step 2:  Transition -> STARTING
Step 3:  if restore_if_exists:
           await restore(session_id)   # restore from LOCAL COLD checkpoint
Step 4:  Transition -> RUNNING
Step 5:  _started_at_ms = current_time_ms
Step 6:  _sync_size_tracker()          # sync tracker with actual section sizes
Step 7:  Return StartResult(success, session_id, duration_ms, restored, restore_source)
```

### 45.2 stop() Sequence

```text
Step 1:  Validate state is RUNNING or STARTING
Step 2:  Transition -> STOPPING
Step 3:  if checkpoint_before_stop:
           checkpoint(trigger=CheckpointTrigger.STOP)
Step 4:  Transition -> STOPPED
Step 5:  Return StopResult(success, checkpoint_id, duration_ms)
```

### 45.3 checkpoint() Sequence

SLA target: < 50ms.

```text
Step 1:  Get snapshot (SessionSnapshot)
Step 2:  For each HOT section:
           section.to_flatbuffer() -> bytes -> base64 encode
Step 3:  For each WARM section:
           section.to_flatbuffer() -> bytes -> base64 encode
Step 4:  Build checkpoint dict:
           {"metadata": snapshot.to_dict(),
            "section_data": {name: b64_data, ...},
            "version": 2}
Step 5:  JSON encode -> local_cold.archive(section="checkpoint", data, metadata)
Step 6:  Return CheckpointResult(success, checkpoint_id, size_bytes, duration_ms, sla_met)
```

FlatBuffer serialization: each section implements `ISection.to_flatbuffer()` using
`flatbuffers.Builder`. Cached - only re-serializes if data changed since last call.

### 45.4 restore() Sequence

```text
Step 1:  Try LOCAL COLD: local_cold.restore(section="checkpoint")
Step 2:  If found:
           _hydrate_from_checkpoint(checkpoint_data)
             Version 2: base64 decode -> section.from_flatbuffer(fb_bytes) per section
             Version 1 (legacy): size metadata only
Step 3:  If not found: return fresh session (no error)
Step 4:  Return RestoreResult(success, source, sections_restored, duration_ms, sla_met)
```

### 45.5 StandaloneLifecycle Adapter

Wraps the manager lifecycle with timer-based periodic checkpoints.

**start():** validate state -> STARTING -> `manager.start()` -> start checkpoint timer (daemon thread) -> RUNNING

**stop():** validate state -> STOPPING -> cancel timer -> final checkpoint (STOP trigger) ->
`manager.stop(checkpoint_before_stop=False)` -> STOPPED

**health():** reads SizeTracker snapshot, returns `HealthStatus` with pressure level.

Context manager: `__enter__` calls `start()`, `__exit__` calls `stop()`.

---

## 46. Session Data Model (12 Sections)

### 46.1 ISection Protocol

All sections implement `ISection` (runtime_checkable Protocol):

| Member | Type | Description |
| ------ | ---- | ----------- |
| `name` | property -> str | Section identifier |
| `tier` | property -> str | "hot" or "warm" |
| `budget_bytes` | property -> int | Maximum size budget |
| `can_evict` | property -> bool | Whether evictable |
| `get_size_bytes()` | -> int | Current serialized size |
| `to_flatbuffer()` | -> bytes | Serialize (cached, <100us) |
| `from_flatbuffer(data)` | -> None | Deserialize from FlatBuffer |
| `clear()` | -> None | Clear all data |
| `get_metadata()` | -> Dict | Telemetry/debug metadata |

### 46.2 HOT Tier Sections (8 sections, 48KB)

| Section | Class | Budget | Eviction Priority | Can Migrate | Demotes To |
| ------- | ----- | ------ | ----------------- | ----------- | ---------- |
| `control` | `ControlSection` | 8KB | NEVER EVICT | No | -- |
| `beliefs_active` | `BeliefsActiveSection` | 8KB | 5 | Yes | `beliefs_history` |
| `scoreboard` | `ScoreboardSection` | 6KB | 6 | Yes | -- |
| `history_active` | `HistoryActiveSection` | 8KB | 4 | Yes | `history_recent` |
| `clarifications` | `ClarificationsSection` | 4KB | 7 | Yes | -- |
| `affective_now` | `AffectiveNowSection` | 4KB | 8 | Yes | -- |
| `narrative_active` | `NarrativeActiveSection` | 8KB | 9 | Yes | -- |
| `meta` | `MetaSection` | 2KB | NEVER EVICT | No | -- |

**NEVER_DEMOTE:** `frozenset(["control", "meta"])`
**DEMOTE_ORDER:** `["history_active", "beliefs_active", "narrative_active"]`

### 46.3 WARM Tier Sections (4 sections, 48KB)

| Section | Class | Budget | Eviction Priority | Notes |
| ------- | ----- | ------ | ----------------- | ----- |
| `telemetry` | `TelemetrySection` | 8KB | 1 (first to evict) | Metrics/diagnostics |
| `beliefs_history` | `BeliefsHistorySection` | 12KB | 2 | Archived beliefs from HOT |
| `history_recent` | `HistoryRecentSection` | 20KB | 3 | Summarized history from HOT |
| `persona` | `PersonaSection` | 8KB | 10 (last to evict) | Stable personality traits |

### 46.4 Section Content Summary

| Section | Key Data | Operations |
| ------- | -------- | ---------- |
| `control` | mode, turn counter, focus agent, agent leases, capabilities | set, update |
| `beliefs_active` | Active belief facts with confidence scores | add_fact, delete, clear, accept_demoted |
| `scoreboard` | Active task progress tracking | set, update, clear |
| `history_active` | Current conversation turns (input/output pairs) | add_turn, record_turn, clear |
| `clarifications` | Pending clarification questions | request, clear |
| `affective_now` | Current emotional state (valence, arousal, dominance) | set, update |
| `narrative_active` | Active narrative threads | create_thread, switch_to, archive_thread, update_thread |
| `meta` | Schema version, session metadata | set (rarely mutated) |
| `telemetry` | Performance metrics, error counts | record_turn, record_error |
| `beliefs_history` | Archived beliefs (demoted from HOT) | accept_demoted, add_compressed |
| `history_recent` | Summarized conversation history | add_summarized, set_session_summary |
| `persona` | Stable personality traits, vocabulary | update, add_vocabulary |

---

## 47. Mutation Pipeline

### 47.1 Mutation Flow

```text
caller -> SessionStateManager.mutate(section, operation, data, estimated_bytes)
  |
  Step 1:  Estimate bytes if not provided (_estimate_bytes)
  Step 2:  MutationGuard.preflight(section, operation, estimated_bytes)
             -> 3-tier check: validate section/operation, check locks,
                check emergency mode, check capacities
  Step 3:  If rejected -> return MutationResult.rejected(reason)
  Step 4:  _apply_mutation(section, operation, data) -> actual bytes delta
             -> Dispatches to section-specific method (set/append/add_turn/etc.)
  Step 5:  SizeTracker.update(section, actual_bytes)
  Step 6:  Update _last_mutation_ms, _mutation_count
  Step 7:  Check pressure -> trigger eviction/migration if CRITICAL/EMERGENCY
  Step 8:  Return MutationResult(success=True, bytes_delta, new_size, pressure)
```

### 47.2 MutationGuard Preflight

**Constructor:** `MutationGuard(size_tracker: SizeTracker)`

**Slots:** `_size_tracker`, `_emergency_mode`, `_locked_sections`, `_lock`

**Preflight checks (ordered):**

| Check | Rejection Reason | Description |
| ----- | ---------------- | ----------- |
| 1 | `INVALID_SECTION` | Section name not in known sections list |
| 2 | `INVALID_OPERATION` | Operation not in 26 valid operations |
| 3 | `SECTION_LOCKED` | Section is currently locked (eviction in progress) |
| 4 | `EMERGENCY_MODE` | Global emergency mode active (>95% capacity) |
| 5 | `SECTION_CAPACITY` | Section would exceed its budget_bytes |
| 6 | `TIER_CAPACITY` | Tier (HOT/WARM) would exceed 48KB |
| 7 | `TOTAL_CAPACITY` | Total would exceed 96KB |

Capacity checks only apply to positive byte deltas.

**26 valid operations:**
`set`, `append`, `add_turn`, `add_fact`, `create_thread`, `switch_to`, `pause_thread`,
`resolve_thread`, `archive_thread`, `update_thread`, `update`, `register_agent`,
`add_referent`, `request`, `add_compressed`, `add_summarized`, `set_session_summary`,
`add_vocabulary`, `clear`, `delete`, `record_turn`, `record_error`, `accept_demoted`

### 47.3 SizeTracker

**Constructor:** `SizeTracker()` -- all sections initialized at 0 bytes.

**Slots:** `_section_sizes`, `_lock`, `_hot_total_cached`, `_warm_total_cached`, `_cache_valid`

**Pressure levels:**

| Level | Threshold | Description |
| ----- | --------- | ----------- |
| NORMAL | < 80% | All mutations allowed |
| ELEVATED | 80-90% | Warning, no restrictions |
| CRITICAL | 90-95% | Triggers eviction on mutation |
| EMERGENCY | > 95% | Blocks non-CRITICAL mutations, triggers emergency eviction |

---

## 48. Eviction and Migration

### 48.1 EvictionEngine

**Constructor:** `EvictionEngine(size_tracker, local_cold, mutation_guard=None, section_provider=None, session_id="")`

**Slots:** `_size_tracker`, `_local_cold`, `_mutation_guard`, `_section_provider`, `_eviction_in_progress`, `_session_id`

**Eviction priority (ascending -- lower = evict first):**

| Priority | Section | Tier |
| -------- | ------- | ---- |
| 1 | `telemetry` | WARM |
| 2 | `beliefs_history` | WARM |
| 3 | `history_recent` | WARM |
| 10 | `persona` | WARM |

**NEVER EVICT:** `control`, `meta` (always in HOT).

**evict() algorithm:**

```text
Step 1:  Get candidates sorted by priority (ascending)
Step 2:  For each candidate:
           a. Lock section (mutation_guard)
           b. Calculate bytes to free
           c. Get section data
           d. Archive to LOCAL COLD (SQLite)
           e. Clear section data
           f. Update SizeTracker
           g. Unlock section
           h. Check if target_bytes reached -> stop if so
Step 3:  Target utilization after eviction: 70%
```

Prevents concurrent eviction via `_eviction_in_progress` flag.

Also has `evict_to_normal_pressure()` -- auto-calculates target bytes to reach NORMAL.

### 48.2 MigrationEngine

**Constructor:** `MigrationEngine(size_tracker, mutation_guard=None, section_provider=None, session_id="", compress_fn=None, summarize_fn=None)`

**Slots:** `_size_tracker`, `_mutation_guard`, `_section_provider`, `_migration_in_progress`, `_session_id`, `_compress_fn`, `_summarize_fn`

**Migration pairs (HOT -> WARM):**

| Source (HOT) | Target (WARM) | Demotion Priority |
| ------------ | ------------- | ----------------- |
| `history_active` | `history_recent` | 1 (first to demote) |
| `beliefs_active` | `beliefs_history` | 2 |
| `narrative_active` | (archivable) | 3 |

**NEVER MIGRATE:** `control`, `meta`.

**Key methods:**

| Method | Signature | Description |
| ------ | --------- | ----------- |
| `demote` | `(section, items, trigger)` | Move items from HOT to WARM |
| `promote` | `(section, items, trigger)` | Move items from WARM to HOT |
| `demote_on_pressure` | `()` | Auto-demote based on current pressure |
| `demote_turn_beliefs` | `(turn_id)` | Demote beliefs associated with a specific turn |
| `demote_history_overflow` | `()` | Demote oldest history entries when HOT overflows |

---

## 49. SessionState Event Reference

### 49.1 Event Types (8)

| EventType | Topic String | When Emitted |
| --------- | ------------ | ------------ |
| `MUTATION_REQUESTED` | `sessionstate.mutation.requested` | Before preflight check |
| `MUTATION_APPROVED` | `sessionstate.mutation.approved` | After successful mutation |
| `MUTATION_REJECTED` | `sessionstate.mutation.rejected` | When preflight rejects mutation |
| `EVICTION_TRIGGERED` | `sessionstate.eviction.triggered` | When EvictionEngine starts eviction |
| `EVICTION_COMPLETED` | `sessionstate.eviction.completed` | After eviction completes |
| `EMERGENCY_ACTIVATED` | `sessionstate.emergency.activated` | Capacity exceeds 90%/95% threshold |
| `EMERGENCY_RESOLVED` | `sessionstate.emergency.resolved` | Capacity drops below threshold |
| `RECONSTRUCTION_STARTED` | `sessionstate.reconstruction.started` | When restore() begins |

### 49.2 Event Payloads

All events extend `BaseEvent` with: `event_id`, `event_type`, `session_id`,
`cognitive_trace_id`, `timestamp_ms`.

| Event | Additional Fields |
| ----- | ----------------- |
| `MutationRequestedEvent` | section, operation, estimated_bytes, writer_id |
| `MutationApprovedEvent` | section, operation, previous/new_size_bytes, tier/total_utilization_pct |
| `MutationRejectedEvent` | section, operation, reason, section/tier/total_available_bytes |
| `EvictionTriggeredEvent` | tier, target_reduction_bytes, pressure_level, candidates |
| `EvictionCompletedEvent` | tier, sections_evicted, bytes_freed, bytes_archived, new_pressure_level, duration_ms |
| `EmergencyActivatedEvent` | level, total/hot/warm_size_bytes, utilization_pct, writes_blocked |
| `EmergencyResolvedEvent` | previous_level, resolution_method, new_utilization_pct, duration_ms |
| `ReconstructionStartedEvent` | source, sections_requested, expected_duration_ms |

### 49.3 Bus Topic Mapping

SessionState events use topic format `sessionstate.{category}.{action}`.
The `SessionBusAdapter(bus)` maps these to Bus topics as `k1.session.{event_type}`:

```text
SessionStateManager.mutate()
  -> event_port.emit("mutation_approved", payload)
  -> SessionBusAdapter.emit("mutation_approved", payload)
  -> bus.publish(Envelope(topic="k1.session.mutation_approved", payload=json))
```

---

## 50. SessionState Shutdown Sequence

```text
Step 1:  StandaloneLifecycle.stop(checkpoint_before_stop=True)
           a. Cancel checkpoint timer (daemon thread)
           b. Final checkpoint (CheckpointTrigger.STOP)
              -> Serializes all 12 sections via FlatBuffer -> base64
              -> Archives to LOCAL COLD SQLite
           c. manager.stop(checkpoint_before_stop=False)
              -> Transition RUNNING -> STOPPING -> STOPPED
           d. Transition lifecycle -> STOPPED

Step 2:  (At kernel level) Bus continues running until after SessionState stops
```

SessionState must stop AFTER Fabric shutdown (Fabric uses SessionStateReaderAdapter)
and BEFORE Bus close (SessionState events flow through Bus via SessionBusAdapter).

---

## 51. SessionState Bootstrap Gotchas

| # | Gotcha | Consequence if Violated |
| - | ------ | ----------------------- |
| S-01 | `create_standalone()` and `create_for_testing()` use POST-CONSTRUCTION injection for writer and lifecycle (circular dep) | manager._writer_port is None, mutations fail |
| S-02 | `create_with_ports()` requires ALL 4 mandatory ports pre-constructed. Validates via `isinstance()`. | `PortProtocolError` raised if wrong type |
| S-03 | SessionState `IEventPort` is an ABC, not Protocol. `SessionBusAdapter` must inherit from it. | `isinstance()` check fails in factory |
| S-04 | `LocalColdArchive` and `SQLiteStorageAdapter` can share the same `db_path` -- they access different tables | Use same path for both to keep data co-located |
| S-05 | `SessionStateReaderAdapter(manager, session_id)` takes TWO args | Missing session_id causes wrong reads |
| S-06 | `session_manager.start()` must be called BEFORE any reads/mutations | SectionNotFoundError or stale data |
| S-07 | Checkpoint SLA is 50ms. FlatBuffer serialization is cached (<100us per section). | Large sections with frequent mutations may bust SLA if cache invalidated |
| S-08 | `StandaloneLifecycle` starts a daemon timer thread for periodic checkpoints | Thread not cleaned up if `stop()` not called |
| S-09 | Eviction archive goes to LOCAL COLD (SQLite), not to K0. K0 sync is entirely optional. | Data stays local until Bridge is wired |
| S-10 | `LifecycleConfig.testing()` sets `checkpoint_interval_ms=0` and `restore_on_start=False` | Tests don't checkpoint or restore -- intentional |
| S-11 | 96KB total budget is per-session. Multiple sessions each get full 96KB. | Memory scales linearly with concurrent sessions |
| S-12 | Mutation operations must be from the 26 valid operations set. Unknown ops rejected by MutationGuard. | `INVALID_OPERATION` rejection, silent failure path |

---

## 52. SessionState File Locations Reference

| What | Path |
| ---- | ---- |
| Factory | `k1/sessionstate/factory.py` |
| Manager | `k1/sessionstate/manager.py` |
| Events | `k1/sessionstate/events.py` |
| MutationGuard | `k1/sessionstate/guard.py` |
| SizeTracker | `k1/sessionstate/sizetracker.py` |
| EvictionEngine | `k1/sessionstate/eviction.py` |
| MigrationEngine | `k1/sessionstate/migration.py` |
| LocalColdArchive | `k1/sessionstate/local_cold.py` |
| Snapshot API | `k1/sessionstate/snapshot.py` |
| Metrics | `k1/sessionstate/metrics.py` |
| Logging | `k1/sessionstate/logging.py` |
| IStoragePort | `k1/sessionstate/ports/storage.py` |
| IEventPort | `k1/sessionstate/ports/events.py` |
| IWriterPort | `k1/sessionstate/ports/writer.py` |
| ILifecyclePort | `k1/sessionstate/ports/lifecycle.py` |
| IK0SyncPort + NullSyncPort | `k1/sessionstate/ports/k0_sync.py` |
| SQLiteStorageAdapter | `k1/sessionstate/adapters/sqlite_storage.py` |
| InMemoryStorageAdapter | `k1/sessionstate/adapters/memory_storage.py` |
| LocalEventAdapter | `k1/sessionstate/adapters/local_events.py` |
| DirectWriterAdapter | `k1/sessionstate/adapters/direct_writer.py` |
| StandaloneLifecycle | `k1/sessionstate/adapters/standalone_lifecycle.py` |
| SessionBusAdapter | `k1/bus/adapters/session_adapter.py` |
| HOT sections (8) | `k1/sessionstate/sections/*.py` |
| WARM sections (4) | `k1/sessionstate/sections/*.py` |
| Tier implementations | `k1/sessionstate/tiers/*.py` |
| FlatBuffer schemas | `k1/sessionstate/generated/flatbuffers/` |

---

## PART D: Bus Deep Dive

---

## 53. Bus Architecture Overview

The Bus is the **event backbone** of K1. Every inter-module message flows through it:
Orchestrator events, Fabric capability results, SessionState mutations, planner deltas,
HIL requests, and K0 SSE relay. It is the first component created and the last shut down.

### 53.1 Design Principles

- **Fire-and-forget, at-most-once** -- publish returns void, no delivery receipt
- **Topic-matched fan-out** -- multiple subscribers per topic, wildcard support
- **Handler error isolation** -- exceptions never propagate to publisher
- **Zero-allocation hot path** -- frozen Envelope, pre-stamped IDs, RWLock favoring readers
- **Dual backend** -- Python (default) or Rust (`k1_bus_core`) with identical API
- **Causal + sequence ordering** -- optional TimingChain for STRICT topics
- **Middleware pipeline** -- pluggable tracing, metrics, topic validation

### 53.2 Dual Backend

| Backend | When Used | Features |
| ------- | --------- | -------- |
| Python (`LocalBus`) | Default, or when TimingChain needed | Full feature set, `_ReadWriteLock`, capture mode |
| Rust (`RustBusAdapter`) | `backend="auto"` if `k1_bus_core` crate available | Circuit breakers, DLQ, WFQ deficit round-robin, lock-free hot path, TTL expiry, sweep timer thread |

`BusFactory` resolves at import time: probes for `k1_bus_core` module, sets `_RUST_AVAILABLE` flag.
Valid backends: `"auto"` (Rust if available else Python), `"rust"` (force), `"python"` (force).

### 53.3 Package Structure

```text
k1/bus/
  __init__.py           -- public exports
  factory.py            -- BusFactory (4 factory methods)
  envelope/
    envelope.py         -- Envelope dataclass + V1/V2 serialization
    schema.fbs          -- FlatBuffers schema (V2 wire format)
    _fb_generated.py    -- flatc codegen
  ports/
    bus.py              -- IBus Protocol + SubscriptionHandle + BusHandler
    mailbox.py          -- IMailbox, IMailboxRouter, MailboxConfig, errors
  impl/
    local_bus.py        -- LocalBus (Python V1 implementation)
    local_mailbox.py    -- LocalMailbox + LocalMailboxRouter
    topic_trie.py       -- TopicTrie[T] (generic radix trie)
    rust_bus_adapter.py -- RustBusAdapter (wraps k1_bus_core.RustBus)
    rust_mailbox_adapter.py -- RustMailboxRouterAdapter
  middleware/
    __init__.py         -- Middleware Protocol + MiddlewareChain
    tracing.py          -- TracingMiddleware (OpenTelemetry spans)
    metrics.py          -- MetricsMiddleware (Prometheus counters)
    topic_validation.py -- TopicRegistry + TopicValidationMiddleware
  adapters/
    fabric_adapter.py   -- FabricBusAdapter (Dict <-> bytes bridge)
    session_adapter.py  -- SessionBusAdapter (ABC extends IEventPort)
  timing/
    timing_chain.py     -- TimingChain (causal + gap ordering)
    timing_config.py    -- TimingConfig (per-topic delivery mode rules)
    defaults.py         -- DEFAULT_RULES + DEFAULT_MODE

k1/k1_bus_core/         -- Companion Rust crate (pyo3 0.23)
  src/
    lib.rs, local_bus.rs, topic_trie.rs, envelope.rs, rust_envelope.rs,
    mailbox.rs, causal_tracker.rs, gap_buffer.rs, timing_config.rs,
    circuit_breaker.rs, dlq.rs, ring_buffer.rs, sweep.rs, wfq.rs
```

---

## 54. Bus Ports (2 Protocols, both runtime_checkable)

### 54.1 IBus Protocol

```python
@runtime_checkable
class IBus(Protocol):
    def publish(self, envelope: Envelope) -> None: ...
    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
```

Supporting types:

- `BusHandler = Callable[[Envelope], None]`
- `SubscriptionHandle(frozen dataclass)` -- `subscription_id: str`, `pattern: str`

Semantics: fire-and-forget, at-most-once delivery, topic-matched, handler error isolation.

### 54.2 IMailbox Protocol

```python
@runtime_checkable
class IMailbox(Protocol):
    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]: ...
    def pending(self) -> int: ...
```

### 54.3 IMailboxRouter Protocol

```python
@runtime_checkable
class IMailboxRouter(Protocol):
    def deliver(self, actor_id: str, envelope: Envelope) -> None: ...
    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox: ...
    def unregister(self, actor_id: str) -> bool: ...
    def registered_actors(self) -> list[str]: ...
```

### 54.4 Mailbox Config and Errors

```python
@dataclass(frozen=True)
class MailboxConfig:
    capacity: int = 256        # must be > 0
    priority_wfq: bool = True  # weighted fair queueing vs FIFO
```

Errors:

- `BackpressureError(actor_id, capacity)` -- mailbox full
- `UnknownActorError(actor_id)` -- actor not registered

---

## 55. Envelope Reference

### 55.1 Fields

```python
@dataclass(frozen=True)
class Envelope:
    topic: str = ""                             # dotted hierarchy
    priority: int = Priority.INTERACTIVE        # 0-3 (URGENT/REALTIME/INTERACTIVE/BACKGROUND)
    envelope_id: int = 0                        # global monotonic, bus-assigned
    sequence: int = 0                           # per-topic monotonic, bus-assigned
    cognitive_trace_id: str = ""                # cross-K0/K1 correlation key
    session_id: str = ""
    request_id: str = ""
    parent_id: int = 0                          # causal parent (0 = root)
    created_ns: int = 0                         # monotonic clock ns, bus-assigned
    payload: bytes = b""                        # OPAQUE: bus NEVER reads this
    ttl_ms: int = 0                             # V2: time-to-live (0 = no expiry)
    payload_format: int = PayloadFormat.OPAQUE   # V2: hint for adapters
```

### 55.2 Priority Enum

| Value | Name | WFQ Weight | Latency Target |
| ----- | ---- | ---------- | -------------- |
| 0 | URGENT | 4x | < 5ms |
| 1 | REALTIME | 3x | < 10ms |
| 2 | INTERACTIVE | 2x | < 50ms |
| 3 | BACKGROUND | 1x | < 500ms |

### 55.3 DeliveryMode Enum

| Value | Name | Behavior |
| ----- | ---- | -------- |
| 0 | STRICT | Buffer on sequence gap, enforce causal parent ordering |
| 1 | RELAXED | Deliver as-is, log reorder (monitoring only) |
| 2 | BEST_EFFORT | Deliver immediately, droppable under pressure |

### 55.4 PayloadFormat Enum

| Value | Name | Description |
| ----- | ---- | ----------- |
| 0 | OPAQUE | Raw bytes, adapter must interpret |
| 1 | JSON | UTF-8 JSON |
| 2 | MSGPACK | MessagePack |

### 55.5 Wire Formats

**V1 (legacy):** `[4B header_len (big-endian uint32)][JSON header][raw payload]`

**V2 (default):** `[4B b'FB02' magic][FlatBuffers BusEnvelope table]`

Format selected by `ENVELOPE_FORMAT` env var (default `"v2"`).
`from_bytes()` auto-detects by checking for `b'FB02'` magic prefix.

### 55.6 Bus Stamping

Publisher creates Envelope with topic + payload. Bus stamps three fields:

```text
envelope.with_bus_fields(
    envelope_id = _id_gen.next(),           # global monotonic
    sequence    = _seq_gen.next(topic),     # per-topic monotonic
    created_ns  = time.monotonic_ns(),      # wall clock
)
```

Returns new frozen Envelope (immutable copy).

---

## 56. LocalBus Implementation

### 56.1 Slots

```python
class LocalBus:
    __slots__ = (
        "_trie",           # TopicTrie[BusHandler]
        "_rw_lock",        # _ReadWriteLock (custom)
        "_seq_gen",        # _SequenceGenerator (per-topic monotonic)
        "_id_gen",         # _EnvelopeIdGenerator (global monotonic)
        "_stats",          # BusStats
        "_capture",        # bool (capture mode for testing)
        "_captured",       # list[Envelope]
        "_topics_seen",    # set[str]
        "_closed",         # bool
        "_timing_chain",   # TimingChain | None
        "_middleware",     # MiddlewareChain | None
    )
```

### 56.2 Constructor

```python
def __init__(
    self,
    *,
    capture: bool = False,
    timing_chain: TimingChain | None = None,
    middleware: MiddlewareChain | None = None,
) -> None
```

Creates: `TopicTrie[BusHandler]`, `_ReadWriteLock`, `_SequenceGenerator`,
`_EnvelopeIdGenerator`, `BusStats`, empty `_captured` list, `_topics_seen` set.

### 56.3 publish() -- The Hot Path (8 steps)

```text
Step 1:  Guard: check _closed, check empty topic -> silently drop
Step 2:  STAMP: envelope_id (global mono), sequence (per-topic mono),
         created_ns (monotonic clock) via envelope.with_bus_fields()
Step 3:  Track topic in _topics_seen set
Step 4:  MIDDLEWARE: _middleware.process(stamped)
           -> returns modified Envelope or None (drop)
           -> exceptions caught and logged, never propagate
Step 5:  CAPTURE: if capture mode, append to _captured list
Step 6:  MATCH: acquire READ lock on _trie, call _trie.match(topic), release
Step 7:  DISPATCH: if _timing_chain set, route through TimingChain
         with closure capturing handlers. Otherwise direct _dispatch().
Step 8:  _dispatch(stamped, handlers): iterate handlers, call each in
         try/except. Exceptions caught, logged, NEVER propagate to publisher.
         Update envelopes_delivered and handler_errors stats.
```

### 56.4 subscribe() and unsubscribe()

`subscribe(pattern, handler)` -- acquires WRITE lock, inserts into trie with
`sub-{uuid12}` subscription ID, updates stats. Returns `SubscriptionHandle`.

`unsubscribe(handle)` -- acquires WRITE lock, removes from trie by subscription ID.

### 56.5 Topic Pattern Matching

| Pattern | Matches | Example |
| ------- | ------- | ------- |
| `k1.capability.completed.v1` | Exact topic only | Only `k1.capability.completed.v1` |
| `k1.agent.*.delta.v1` | `*` = one segment | `k1.agent.abc123.delta.v1` |
| `k1.agent.>` | `>` = one or more trailing | `k1.agent.abc.delta.v1`, `k1.agent.x.y.z` |

`*` matches exactly ONE segment at that position.
`>` matches ONE OR MORE trailing segments (must be last segment in pattern).

### 56.6 BusStats

```python
@dataclass
class BusStats:
    envelopes_published: int = 0
    envelopes_delivered: int = 0
    handler_errors: int = 0
    subscriptions_active: int = 0
    subscriptions_total: int = 0
    unsubscribe_count: int = 0
    topics_seen: int = 0
```

### 56.7 Lifecycle

| Method | Description |
| ------ | ----------- |
| `close()` | Sets `_closed = True`, subsequent publishes silently dropped |
| `closed` | Property: `bool` |
| `sweep()` | Releases timed-out envelopes from TimingChain. No-op if no chain. |

Existing handlers are NOT unsubscribed on close -- they just stop firing.

---

## 57. TopicTrie Implementation

Generic `TopicTrie[T]` with radix-compressed DFS matching.

### 57.1 Node Structure

```python
class _TrieNode(Generic[T]):
    __slots__ = ("children", "handlers", "subscription_ids")
    children: dict[str, _TrieNode[T]]
    handlers: list[T]
    subscription_ids: list[str]
```

### 57.2 Operations

| Method | Complexity | Description |
| ------ | ---------- | ----------- |
| `insert(pattern, handler, sub_id)` | O(k) segments | Add handler at pattern leaf |
| `remove(subscription_id)` | O(1) via `_sub_index` | Tombstones handler, auto-compacts at >50% dead |
| `match(topic)` | O(k * branching) | DFS: exact + `*` (one) + `>` (greedy) |
| `clear()` | O(1) | Reset root |
| `size` / `__len__` | O(1) | Active subscription count |

`_sub_index: dict[str, tuple[_TrieNode, int]]` enables O(1) removal by subscription ID.

**Thread safety:** None internal. `LocalBus` wraps all access with `_ReadWriteLock`.

---

## 58. Mailbox System

### 58.1 LocalMailbox

```python
class LocalMailbox:
    __slots__ = (
        "_actor_id", "_capacity", "_priority_wfq", "_queues",
        "_single_queue", "_size", "_lock", "_not_empty",
        "_closed", "_delivered_count", "_received_count",
    )
```

**Constructor:** `__init__(self, actor_id: str, config: MailboxConfig)`

**WFQ mode** (`priority_wfq=True`): 4 deques indexed by `Priority` value (0-3).
`receive()` drains highest-priority non-empty queue first (strict priority V1).

**FIFO mode** (`priority_wfq=False`): single deque.

**Thread safety:** `threading.Lock` + `threading.Condition` for blocking `receive(timeout_ms)`.

| Method | Description |
| ------ | ----------- |
| `receive(timeout_ms=0)` | Blocking dequeue. Returns `None` on timeout. |
| `pending()` | Current queue depth |
| `_deliver(envelope)` | Internal. Raises `BackpressureError` if full. |
| `close()` | Prevents new deliveries, allows drain |
| `depth_by_priority()` | Dict of per-priority depths |

### 58.2 LocalMailboxRouter

```python
class LocalMailboxRouter:
    __slots__ = ("_mailboxes", "_lock", "_closed")
```

**Thread safety:** `threading.RLock` on `_mailboxes` dict. Registry lock released BEFORE
calling `mailbox._deliver()` to avoid holding lock during dispatch.

| Method | Description |
| ------ | ----------- |
| `deliver(actor_id, envelope)` | Raises `UnknownActorError` / `BackpressureError` |
| `register(actor_id, config)` | Returns `LocalMailbox`. Raises if duplicate. |
| `unregister(actor_id)` | Closes and removes mailbox |
| `registered_actors()` | List of actor IDs |
| `close()` | Closes router + all mailboxes |
| `mailbox_for(actor_id)` | Direct mailbox access |
| `stats_snapshot()` | Per-actor `{pending, delivered, received, capacity}` |

---

## 59. Bus Factory Internal Wiring

### 59.1 create_local (production)

```python
BusFactory.create_local(
    *,
    capture: bool = False,
    timing_chain: Optional[TimingChain] = None,
    middleware: list[Middleware] | MiddlewareChain | None = None,
    backend: str = "auto",
) -> BusType
```

**Wiring:**

```text
Step 1:  Resolve backend ("auto" -> Rust if _RUST_AVAILABLE, else Python)
Step 2:  Convert middleware list -> MiddlewareChain (if list provided)
Step 3:  If timing_chain + backend="rust": FALLBACK to Python
         (TimingChain is Python-only)
Step 4:  Construct LocalBus(capture, timing_chain, middleware)
         or RustBusAdapter(capture, timing_chain, middleware)
Step 5:  Return bus instance
```

### 59.2 create_local_ordered (causal ordering)

```python
BusFactory.create_local_ordered(
    *,
    config: Optional[TimingConfig] = None,
    timeout_ms: int = 5000,
    capture: bool = False,
    middleware: list[Middleware] | MiddlewareChain | None = None,
    backend: str = "python",          # forces Python
) -> LocalBus
```

**Wiring:**

```text
Step 1:  config = config or TimingConfig(DEFAULT_RULES, DEFAULT_MODE)
Step 2:  timing_chain = TimingChain(config, timeout_ms)
Step 3:  Convert middleware -> MiddlewareChain
Step 4:  LocalBus(capture, timing_chain, middleware)
```

### 59.3 create_for_testing

```python
BusFactory.create_for_testing(
    *,
    ordered: bool = False,
    middleware: list[Middleware] | MiddlewareChain | None = None,
    backend: str = "auto",
) -> BusType
```

Always sets `capture=True`. If `ordered=True`, forces Python + TimingChain.

### 59.4 create_mailbox_router

```python
BusFactory.create_mailbox_router(
    *,
    backend: str = "auto",
) -> MailboxRouterType
```

Returns `LocalMailboxRouter` or `RustMailboxRouterAdapter`.

---

## 60. Middleware Pipeline

### 60.1 Middleware Protocol

```python
@runtime_checkable
class Middleware(Protocol):
    def process(self, envelope: Envelope) -> Optional[Envelope]: ...
```

Returns `None` to DROP the envelope. Must NOT read payload, block for I/O, or raise.

### 60.2 MiddlewareChain

```python
class MiddlewareChain:
    __slots__ = ("_middlewares",)
```

Runs each middleware in sequence. If any returns `None`, subsequent middlewares skipped
and envelope is dropped (never dispatched).

**Canonical order:** tracing -> metrics -> topic_validation.

| Method | Description |
| ------ | ----------- |
| `process(envelope)` | Run chain. Returns final Envelope or None. |
| `append(middleware)` | Add to end |
| `prepend(middleware)` | Add to front |
| `size` | Number of middlewares |

### 60.3 TracingMiddleware

```python
class TracingMiddleware:
    __slots__ = ("_tracer", "_enabled")
    def __init__(self, *, tracer_name: str = "k1.bus", enabled: bool = True)
```

- Graceful degradation: no-op if `opentelemetry` not installed
- Creates span per envelope: `"bus.publish {topic}"`
- Span attributes: `bus.topic`, `bus.envelope_id`, `bus.sequence`, `bus.priority`,
  `bus.parent_id`, `bus.cognitive_trace_id`, `bus.session_id`
- NEVER drops envelopes

### 60.4 MetricsMiddleware

```python
class MetricsMiddleware:
    __slots__ = ("_enabled", "_counter", "_histogram")
    def __init__(self, *, prefix: str = "k1_bus", enabled: bool = True)
```

- Graceful degradation: no-op if `prometheus_client` not installed
- `{prefix}_envelopes_total` -- Counter by `{topic_prefix, priority}`
- `{prefix}_envelope_latency_seconds` -- Histogram by `{topic_prefix}`
- Topic prefix = first 2 segments (e.g., `"k1.capability"`) to limit cardinality
- NEVER drops envelopes

### 60.5 TopicValidationMiddleware + TopicRegistry

```python
class TopicRegistry:
    __slots__ = ("_exact", "_prefixes", "_wildcards", "_lock")
```

| Method | Description |
| ------ | ----------- |
| `register(topic)` | Add exact or wildcard (if contains `*` or `?`) |
| `register_prefix(prefix)` | Add prefix match |
| `is_known(topic)` | Check: exact -> prefix -> wildcard (fnmatch) |
| `unregister(topic)` | Remove |

```python
class TopicValidationMiddleware:
    __slots__ = ("_registry", "_warn_count")
```

**SOFT validation** -- unknown topics produce WARNING log but are ALWAYS delivered.
Never drops. `warning_count` property for observability.

---

## 61. TimingChain (Causal + Sequence Ordering)

### 61.1 TimingConfig

```python
class TimingConfig:
    __slots__ = ("_rules", "_default", "_lock", "_sorted_prefixes")
    def __init__(
        self,
        rules: Optional[dict[str, DeliveryMode]] = None,
        default: DeliveryMode = DeliveryMode.RELAXED,
    )
```

**Resolution:** longest-prefix match. Exact match first, then walk down segments.
Thread-safe `reload(rules)` via atomic reference swap.

### 61.2 Default Delivery Mode Rules

| Topic Prefix | Mode | Module |
| ------------ | ---- | ------ |
| `k1.capability` | STRICT | Fabric |
| `k1.orchestration` | STRICT | Orchestrator |
| `k1.planner` | STRICT | Planner |
| `k1.hil` | STRICT | HIL |
| `k1.response` | STRICT | Concierge |
| `k1.session` | STRICT | SessionState |
| `k1.agent` | STRICT | Agent deltas |
| `k1.affect` | RELAXED | Affect |
| `k1.constraint` | RELAXED | Constraint |
| `k1.proactive` | RELAXED | Proactive |
| `k1.workflow` | RELAXED | Workflow |
| `k1.k0.sse` | BEST_EFFORT | K0 Bridge |
| `k1.fabric.learning` | BEST_EFFORT | Fabric learning |
| **(default)** | **RELAXED** | Everything else |

### 61.3 TimingChain

```python
class TimingChain:
    __slots__ = ("_config", "_causal", "_gap", "_stats", "_timeout_ns", "_last_sweep_ns")
    def __init__(
        self,
        config: Optional[TimingConfig] = None,
        timeout_ms: int = 5000,
        causal_buffer_limit: int = 50_000,
        gap_buffer_limit: int = 10_000,
    )
```

### 61.4 process() Decision Tree

```text
1. Resolve DeliveryMode via _config.resolve(topic)
2. BEST_EFFORT -> deliver immediately, no tracking
3. RELAXED     -> deliver immediately, log if out-of-order
4. STRICT      ->
     a. Causal check: is parent_id delivered?
        NO  -> buffer child in CausalTracker
        YES -> continue
     b. Sequence gap check: is this the expected sequence for this topic?
        NO  -> buffer in GapBuffer
        YES -> deliver + release buffered successors + cascade causal children
```

### 61.5 sweep()

`sweep(dispatch_fn) -> int` -- releases timed-out envelopes from both causal and gap
buffers. Safety net for lost messages. Default timeout: 5000ms.

### 61.6 Internal Buffers

**CausalTracker:**

- `_delivered: set[int]` -- delivered envelope IDs
- `_waiting: dict[int, list[_BufferedEnvelope]]` -- parent_id -> waiting children
- Overflow safety: force-release oldest 10% when max_buffer (50,000) exceeded

**GapBuffer:**

- Per-topic locks (zero cross-topic contention)
- `_expected: dict[str, int]` -- next expected sequence per topic
- `_buffers: dict[str, SortedContainers]` -- out-of-order envelopes per topic
- Overflow safety: force-release oldest 10% per topic when max (10,000) exceeded

### 61.7 TimingStats

```python
@dataclass
class TimingStats:
    envelopes_processed: int = 0
    delivered_immediate: int = 0
    buffered_causal: int = 0
    buffered_gap: int = 0
    released_causal: int = 0
    released_gap: int = 0
    released_timeout: int = 0
    reorders_detected: int = 0
    dropped_best_effort: int = 0
```

---

## 62. Bus Adapters (2 total)

### 62.1 FabricBusAdapter

```python
class FabricBusAdapter:
    __slots__ = ("_bus",)
    def __init__(self, bus: LocalBus) -> None
```

Bridges Fabric's `IEventPort(Dict)` + `IDeltaBusPort` to `IBus(bytes)`.

| Method | Signature | Notes |
| ------ | --------- | ----- |
| `emit` | `(topic: str, payload: Dict) -> None` | JSON-serializes Dict, publishes at INTERACTIVE priority |
| `subscribe` | `(topic: str, handler: (str, Dict)->None) -> FabricSubscriptionHandle` | Wrapper deserializes bytes -> Dict for handler |
| `unsubscribe` | `(handle) -> bool` | Converts to bus SubscriptionHandle |
| `emit_delta` | `(agent_id, delta_type, section, data: Dict) -> None` | Topic: `k1.agent.{agent_id}.delta.v1`, REALTIME priority |
| `bus` | property | Underlying bus instance |

### 62.2 SessionBusAdapter

```python
class SessionBusAdapter(IEventPort):           # Extends ABC for isinstance() check
    __slots__ = ("_bus", "_subscriptions")
    def __init__(self, bus: LocalBus) -> None
```

Bridges SessionState's `IEventPort(Any)` to `IBus(bytes)`.

Topic mapping: `event_type` -> `"k1.session." + event_type`

| Method | Signature | Notes |
| ------ | --------- | ----- |
| `is_connected` | property -> bool | `not self._bus.closed` |
| `emit` | `(event_type: str, payload: Any) -> None` | JSON wraps as `{"payload": value}`, INTERACTIVE priority |
| `subscribe` | `(event_type: str, handler) -> str` | Returns subscription_id string (not handle) |
| `unsubscribe` | `(subscription_id: str) -> bool` | Looks up stored SubscriptionHandle |
| `emit_batch` | inherited from IEventPort ABC | Calls emit() per event |
| `active_subscriptions` | property -> int | Count of active subscriptions |

GOTCHA: `SessionBusAdapter` extends the SessionState `IEventPort` ABC (not Protocol)
so it passes the `isinstance()` check in `SessionStateFactory.create_with_ports()`.

---

## 63. Bus Topic Registry

### 63.1 Event Topics (fire-and-forget fan-out)

| Topic Pattern | Mode | Module |
| ------------- | ---- | ------ |
| `k1.response.final.v1` | STRICT | Concierge |
| `k1.response.ack.v1` | STRICT | Concierge |
| `k1.response.progress.v1` | STRICT | Concierge |
| `k1.capability.invoked.v1` | STRICT | Fabric |
| `k1.capability.completed.v1` | STRICT | Fabric |
| `k1.capability.failed.v1` | STRICT | Fabric |
| `k1.orchestration.task.accepted` | STRICT | Orchestrator |
| `k1.orchestration.execution.*` | STRICT | Orchestrator |
| `k1.orchestration.step.progress` | STRICT | Orchestrator |
| `k1.planner.plan.ready.v1` | STRICT | Planner |
| `k1.planner.plan.failed.v1` | STRICT | Planner |
| `k1.hil.clarification.v1` | STRICT | HIL |
| `k1.hil.approval_request.v1` | STRICT | HIL |
| `k1.session.checkpoint.v1` | STRICT | SessionState |
| `k1.session.eviction.v1` | STRICT | SessionState |
| `k1.session.emergency.v1` | STRICT | SessionState |
| `k1.affect.analyzed.v1` | RELAXED | Affect |
| `k1.constraint.progress.v1` | RELAXED | Constraint |
| `k1.constraint.resolved.v1` | RELAXED | Constraint |
| `k1.proactive.question.v1` | RELAXED | Proactive |
| `k1.proactive.message.v1` | RELAXED | Proactive |
| `k1.workflow.trigger.due` | RELAXED | Workflow |
| `k1.workflow.run.*` | RELAXED | Workflow |
| `k1.k0.sse.received.v1` | BEST_EFFORT | K0 Bridge |
| `k1.k0.sse.curiosity.intent.v1` | BEST_EFFORT | K0 Bridge |
| `k1.fabric.learning.signal.v1` | BEST_EFFORT | Fabric learning |

### 63.2 Delta Topics

| Topic Pattern | Mode | Description |
| ------------- | ---- | ----------- |
| `k1.agent.{id}.delta.v1` | STRICT | Per-agent state deltas |
| `k1.planner.delta.v1` | STRICT | Planner state deltas |
| `k1.orchestration.delta.v1` | STRICT | Orchestrator state deltas |
| `k1.memory.delta.v1` | STRICT | Memory deltas |

### 63.3 Bus Internal Topics

| Topic | Purpose |
| ----- | ------- |
| `k1.bus.subscription.created` | Lifecycle: new subscription |
| `k1.bus.subscription.removed` | Lifecycle: subscription removed |
| `k1.bus.dlq.overflow` | DLQ overflow (Rust backend only) |

---

## 64. Concurrency Model

| Component | Mechanism | Scope |
| --------- | --------- | ----- |
| `LocalBus._rw_lock` | Custom `_ReadWriteLock` (Condition+Lock) | Trie access: readers=publish, writer=sub/unsub |
| `_SequenceGenerator` | Per-topic `threading.Lock` | Zero cross-topic contention |
| `_EnvelopeIdGenerator` | Global `threading.Lock` | Effectively free under GIL |
| `LocalMailbox` | `threading.Lock` + `Condition` | Per-mailbox, blocking receive |
| `LocalMailboxRouter` | `threading.RLock` | Actor registry |
| `_CausalTracker` | Global `threading.Lock` | Cross-topic parent tracking |
| `_GapBuffer` | Per-topic `threading.Lock` | Double-checked lock creation |
| `TimingConfig` | Atomic reference swap | Lock only for `reload()` |
| `TopicRegistry` | `threading.RLock` | Registration only |
| Rust backend | `AtomicU64`, `DashMap`, `parking_lot::RwLock` | Lock-free hot path |

**RWLock pattern:** Publish (hot path) takes READ lock (concurrent). Subscribe/unsubscribe
takes WRITE lock (exclusive). This means publish is never blocked by other publishes.

---

## 65. Rust Backend Extras (V2)

These features exist ONLY in the Rust `k1_bus_core` crate, not in Python V1:

| Feature | Rust Module | Description |
| ------- | ----------- | ----------- |
| Circuit Breaker | `circuit_breaker.rs` | Per-handler FSM: CLOSED -> OPEN (N failures) -> HALF_OPEN (cooldown) -> CLOSED |
| Dead Letter Queue | `dlq.rs` | Bounded ring buffer: backpressure rejects, handler errors, expired TTL |
| TTL Expiry | `sweep.rs` | At dispatch: `now_ns - created_ns > ttl_ms * 1_000_000` -> DLQ. Zero cost when `ttl_ms=0` |
| Sweep Timer | `sweep.rs` | Dedicated background thread (not caller-driven like Python) |
| WFQ Dispatch | `wfq.rs` | True weighted fair queueing with deficit round-robin, starvation impossible |
| Lock-free Path | `local_bus.rs` | `AtomicU64` for IDs, `DashMap` for subscriptions |

Python V1: failed handlers are caught/logged. No DLQ, no circuit breakers. TTL check not enforced.

---

## 66. Bus Lifecycle

### 66.1 Creation (Kernel Bootstrap)

```text
Step 1:  BusFactory.create_local(backend="auto") or create_local_ordered()
Step 2:  Backend resolved (Rust if available, else Python)
Step 3:  Middleware assembled: TracingMiddleware + MetricsMiddleware + TopicValidationMiddleware
Step 4:  MiddlewareChain created with canonical order
Step 5:  If ordered: TimingConfig(DEFAULT_RULES) + TimingChain(config, timeout_ms=5000)
Step 6:  Bus instance constructed
Step 7:  Bus instance returned to kernel
Step 8:  Kernel passes bus to Fabric, SessionState, Orchestrator factories
Step 9:  Adapters created: FabricBusAdapter(bus), SessionBusAdapter(bus)
Step 10: Adapters injected into component factories as port implementations
```

### 66.2 Shutdown

```text
Step 1:  Kernel stops Orchestrator (no new tasks)
Step 2:  Kernel stops Fabric (no new capabilities, drain in-flight)
Step 3:  Kernel stops SessionState (final checkpoint through bus)
Step 4:  bus.close()
           -> sets _closed = True
           -> subsequent publish() calls silently drop
           -> existing handlers NOT unsubscribed (they just never fire)
Step 5:  If mailbox router: router.close()
           -> closes all mailboxes (no new deliveries, existing drain allowed)
```

Bus is **LAST to close** -- all other components depend on it for event delivery.

---

## 67. Bus Bootstrap Gotchas

| # | Gotcha | Consequence if Violated |
| - | ------ | ----------------------- |
| B-01 | Bus MUST be created FIRST (before Fabric, SessionState, Orchestrator) | Components cannot publish or subscribe |
| B-02 | Bus MUST be closed LAST (after all components stop) | Late events silently dropped, potential data loss |
| B-03 | `SessionBusAdapter` extends `IEventPort` ABC (not Protocol) | Required for `isinstance()` in SessionState factory |
| B-04 | `FabricBusAdapter` bridges Dict <-> bytes. Fabric publishes Dict, Bus expects bytes. | Wrong adapter = serialization failure |
| B-05 | TimingChain is Python-only. `create_local_ordered()` forces `backend="python"` | Rust + TimingChain = auto-fallback to Python |
| B-06 | Middleware NEVER reads payload (opaque bytes). Middleware processes envelope metadata only. | Payload inspection violates bus contract |
| B-07 | `publish()` silently drops after `close()`. No error raised. | Hard to debug missed events during shutdown |
| B-08 | TopicValidationMiddleware is SOFT: warns but never drops unknown topics | Unknown topics still flow. Only observability, not enforcement. |
| B-09 | `*` matches ONE segment, `>` matches ONE OR MORE trailing segments (must be last) | Wrong wildcard = missed or extra matches |
| B-10 | `capture=True` stores ALL published envelopes in memory (testing only) | Production use = unbounded memory growth |
| B-11 | Envelope is `frozen=True` dataclass. Bus stamps via `with_bus_fields()` returning NEW instance. | Cannot mutate in-place |
| B-12 | Per-topic sequence is monotonic starting at 1. GapBuffer expects sequence=1 as first. | Custom sequence numbers break ordering |
| B-13 | `ENVELOPE_FORMAT` env var controls wire format (`"v2"` default). V1 is JSON legacy. | Mixed formats between services = deserialization failure |

---

## 68. Bus File Locations Reference

| What | Path |
| ---- | ---- |
| Package exports | `k1/bus/__init__.py` |
| Factory | `k1/bus/factory.py` |
| Envelope | `k1/bus/envelope/envelope.py` |
| FlatBuffers schema | `k1/bus/envelope/schema.fbs` |
| FB codegen | `k1/bus/envelope/_fb_generated.py` |
| IBus Protocol | `k1/bus/ports/bus.py` |
| IMailbox + IMailboxRouter | `k1/bus/ports/mailbox.py` |
| LocalBus | `k1/bus/impl/local_bus.py` |
| TopicTrie | `k1/bus/impl/topic_trie.py` |
| LocalMailbox + Router | `k1/bus/impl/local_mailbox.py` |
| RustBusAdapter | `k1/bus/impl/rust_bus_adapter.py` |
| RustMailboxAdapter | `k1/bus/impl/rust_mailbox_adapter.py` |
| Middleware Protocol + Chain | `k1/bus/middleware/__init__.py` |
| TracingMiddleware | `k1/bus/middleware/tracing.py` |
| MetricsMiddleware | `k1/bus/middleware/metrics.py` |
| TopicRegistry + Validation | `k1/bus/middleware/topic_validation.py` |
| FabricBusAdapter | `k1/bus/adapters/fabric_adapter.py` |
| SessionBusAdapter | `k1/bus/adapters/session_adapter.py` |
| TimingChain | `k1/bus/timing/timing_chain.py` |
| TimingConfig | `k1/bus/timing/timing_config.py` |
| Default rules | `k1/bus/timing/defaults.py` |
| Rust crate | `k1/k1_bus_core/src/*.rs` |

---

## PART E: Planner Deep Dive

---

## 69. Planner Architecture Overview

The Planner is the **planning engine** of K1. It receives plan requests from the
Orchestrator (via mailbox), runs them through a 4-stage pipeline
(Sketch -> Expand -> Validate -> Commit), and emits `CommittedPlan` events back
to the Orchestrator for DAG execution. The Planner also supports micro-replan
(mid-execution plan amendments) and Human-in-the-Loop (HIL) clarification and
approval flows.

### 69.1 Planner Container

Unlike Fabric (which uses a `@dataclass` container), the Planner is organised
around `PlannerAgent` as the top-level actor. The factory builds the full object
graph and returns the agent.

```
PlannerAgent (top-level actor)
  |-- IMailboxPort (inbound plan requests)
  |-- IEventPort   (pub/sub lifecycle events)
  |-- PipelineController (4-stage orchestrator)
  |     |-- SketchService  (stage 1)
  |     |-- ExpandService  (stage 2)
  |     |-- ValidateService (stage 3)
  |     |-- CommitService  (stage 4)
  |     |-- IDeltaEmitPort (stage transition deltas)
  |     |-- IEventPort     (plan lifecycle events)
  |     |-- PlanStateMachine (FSM)
  |-- PlannerConfig
```

Leaf services shared across stages:

```
ToolCallRouter (used by Sketch, Expand)
  |-- IFabricRetrievalPort
  |-- IStateReadPort
  |-- IBridgePort

HILCoordinator (used by Sketch, Validate)
  |-- ILLMPort
  |-- IEventPort
```

### 69.2 Design Principles

| # | Principle | Implementation |
|---|-----------|----------------|
| 1 | Hexagonal architecture | 7 port Protocols, 7 production adapters, 7 test adapters |
| 2 | Single-threaded async actor | One asyncio event loop, one plan at a time (V1) |
| 3 | Cooperative cancellation | Flag-based cancel set, checked between stages |
| 4 | Fire-and-forget deltas | Delta loss acceptable (observability, not control-plane) |
| 5 | PLAN-01: Read-only state | No writes to SessionState (IStateReadPort only) |
| 6 | PLAN-03: No LLM at commit | CommitService has zero ILLMPort (structural) |
| 7 | PLAN-05: Tool budget | Max 6 tool calls per plan (configurable) |
| 8 | PLAN-10: HIL budget | Max 2 HIL rounds per plan (configurable) |

---

## 70. Planner Ports (7 total)

All Planner ports use `@runtime_checkable` Protocol (structural typing).

### 70.1 IMailboxPort

```python
class IMailboxPort(Protocol):
    async def dequeue(self) -> PlanRequest: ...
    async def enqueue(self, request: PlanRequest) -> None: ...
    async def send_cancel(self, request_id: str) -> None: ...
    def drain(self) -> List[PlanRequest]: ...
    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan: ...
```

Supporting types: `PlanRequest(intent, trace_id, request_id, ...)` from `k1.orchestrator.types`,
`MicroReplanRequest(request_id, completed_results, remaining_steps, ...)` from `k1.orchestrator.types`.
Wired to: PlannerAgent (dequeue loop, shutdown drain), Kernel (via PlannerAdapter).

### 70.2 ILLMPort

```python
class ILLMPort(Protocol):
    async def execute(self, request: HubRequest) -> HubResponse: ...
```

Supporting types: `HubRequest(capability, payload, constraints, trace_id)`,
`HubResponse(result, metadata)`, `RequestConstraints(max_tokens, timeout_ms, priority, temperature, consumer_id)`.
Wired to: SketchService, ExpandService, ValidateService, HILCoordinator.
NOT wired to: CommitService (PLAN-03).

### 70.3 IFabricRetrievalPort

```python
class IFabricRetrievalPort(Protocol):
    async def discover_capabilities(self, domain=None, intent="", safety_band="GREEN",
                                     session_context=None, top_k=10) -> RetrievalResult: ...
    async def find_relevant_prompts(self, intent="", domain=None, safety_band="GREEN",
                                     top_k=10) -> RetrievalResult: ...
```

Supporting type: `RetrievalResult` from `k1.fabric.types`.
Wired to: ToolCallRouter (discover_capabilities, find_relevant_prompts),
ValidateService (capability existence verification).

### 70.4 IStateReadPort

```python
class IStateReadPort(Protocol):
    async def read_sections(self, sections: List[str], trace_id: str = "") -> SessionSnapshot: ...
```

Supporting type: `SessionSnapshot(session_id, sections)` from `k1.fabric.ports.state_reader`.
Wired to: ToolCallRouter (query_planning_context).
PLAN-01: read-only, no mutations.

### 70.5 IBridgePort

```python
class IBridgePort(Protocol):
    async def recall(self, query: str, selectors: Optional[List[str]] = None,
                     *, trace_id: str = "") -> RecallResponse: ...
    async def persist_plan(self, plan: CommittedPlan, *, trace_id: str = "") -> None: ...
```

Supporting type: `RecallResponse(facts, scores, trace_id)`.
Wired to: ToolCallRouter (recall_for_planning), CommitService (WAL persist).

### 70.6 IDeltaEmitPort

```python
class IDeltaEmitPort(Protocol):
    def emit(self, delta: DeltaPayload) -> None: ...
```

Synchronous. Fire-and-forget. Must not raise.
Supporting type: `DeltaPayload(agent_id, delta_type, section, data, trace_id)`.
Wired to: PipelineController (stage transitions), CommitService (commit deltas).

### 70.7 IEventPort

```python
class IEventPort(Protocol):
    def emit(self, topic: str, payload: Any) -> None: ...
    def subscribe(self, topic: str, handler: Callable[[str, Any], None]) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
```

All synchronous. `emit()` is fire-and-forget.
Supporting type: `SubscriptionHandle(subscription_id, topic)` from `k1.fabric.ports.event_port`.
Wired to: PlannerAgent (4 subscriptions), PipelineController (plan.ready, plan.failed, plan.cancelled),
CommitService (plan.ready delivery), HILCoordinator (clarification/approval pub/sub).

---

## 71. Planner Adapters (7 production + 7 test)

### 71.1 Production Adapters

| Adapter | Satisfies Port | Constructor | Location | Notes |
| ------- | -------------- | ----------- | -------- | ----- |
| `MailboxAdapter` | `IMailboxPort` | `(max_depth=5, priority_class="INTERACTIVE")` | `k1/planner/adapters/mailbox_adapter.py` | asyncio.Queue-backed FIFO. Cancel set. Plan lock. Shutdown rejection. |
| `LLMGatewayAdapter` | `ILLMPort` | `(llm_request_bus: ILLMRequestBus, consumer_id="planner")` | `k1/planner/adapters/llm_gateway_adapter.py` | Maps TimeoutError -> LLMTimeoutError, budget errors -> BudgetExceededError. Phase 2 adapter. |
| `FabricRetrievalAdapter` | `IFabricRetrievalPort` | `(fabric_retrieval: Any, timeout_ms=50, max_retries=1)` | `k1/planner/adapters/fabric_retrieval_adapter.py` | In-process call to `FabricRetrieval`. Returns empty `RetrievalResult` on exhaustion (degraded). |
| `SessionStateReadAdapter` | `IStateReadPort` | `(reader: Any, session_id: str)` | `k1/planner/adapters/session_state_adapter.py` | Pre-bound session_id. Returns empty `SessionSnapshot` on error. |
| `BridgeAdapter` | `IBridgePort` | `(bridge_port: Any)` | `k1/planner/adapters/bridge_adapter.py` | Wraps Fabric IBridgePort. `recall` -> `bridge.query("memory.recall")`. `persist_plan` -> `bridge.send_command("memory.store")`. Offline: degraded (empty recall, drop persist). |
| `DeltaBusAdapter` | `IDeltaEmitPort` | `(delta_bus: Any, agent_id="planner")` | `k1/planner/adapters/delta_bus_adapter.py` | Pre-stamps agent_id. Maps `DeltaPayload` -> `emit_delta()`. Fire-and-forget. |
| `EventBusAdapter` | `IEventPort` | `(event_port: Any)` | `k1/planner/adapters/event_bus_adapter.py` | Thin passthrough to Fabric IEventPort (interface-identical per SS15.9). Fire-and-forget emit. |

### 71.2 Test Adapters

| Adapter | Satisfies Port | Constructor | Location | Test Features |
| ------- | -------------- | ----------- | -------- | ------------- |
| `TestMailboxAdapter` | `IMailboxPort` | `(max_depth=10)` | `tests/k1/planner/adapters/test_mailbox_adapter.py` | In-memory. Direct enqueue/dequeue. Sync drain. |
| `TestLLMAdapter` | `ILLMPort` | `(stage_responses=DEFAULT)` | `tests/k1/planner/adapters/test_llm_adapter.py` | Deterministic responses per stage. Capture mode. Error injection via `error_stages`. |
| `TestFabricRetrievalAdapter` | `IFabricRetrievalPort` | `(preset_capabilities=DEFAULT)` | `tests/k1/planner/adapters/test_fabric_retrieval_adapter.py` | Canned `RetrievalResult`. Capture mode. |
| `TestStateReadAdapter` | `IStateReadPort` | `(preset_sections=DEFAULT)` | `tests/k1/planner/adapters/test_state_read_adapter.py` | Dict-based. `load(section, data)` for setup. |
| `TestBridgeAdapter` | `IBridgePort` | `()` | `tests/k1/planner/adapters/test_bridge_adapter.py` | Canned responses. Capture mode. |
| `TestDeltaAdapter` | `IDeltaEmitPort` | `()` | `tests/k1/planner/adapters/test_delta_adapter.py` | Stores `DeltaPayload` list. `drain()`, `get_deltas()`. |
| `TestEventAdapter` | `IEventPort` | `()` | `tests/k1/planner/adapters/test_event_adapter.py` | Stores emitted events. `drain()`, `get_captured()`. Subscription handling. |

---

## 72. PlannerAgent Constructor Reference

```python
class PlannerAgent:
    __slots__ = (
        "_mailbox",                  # IMailboxPort -- inbound request queue
        "_pipeline",                 # PipelineController -- 4-stage orchestrator
        "_event_port",               # IEventPort -- pub/sub lifecycle events
        "_config",                   # PlannerConfig -- budgets, timeouts, temps
        "_plan_lock",                # asyncio.Lock -- V1 single-plan exclusion
        "_cancel_set",               # Set[str] -- pending cancel request IDs
        "_running",                  # bool -- dequeue loop active
        "_subscriptions",            # List[SubscriptionHandle] -- 4 active subs
        "_in_flight_request_id",     # Optional[str] -- current plan request ID
    )
```

Constructor: `PlannerAgent(mailbox, pipeline, event_port, config)` -- 4 injected deps.
All validated non-None (raises `ValueError`).

### 72.1 Properties

| Property | Return Type | Semantics |
|----------|-------------|-----------|
| `mailbox` | `IMailboxPort` | Injected mailbox port (read-only) |
| `pipeline` | `PipelineController` | Injected pipeline controller (read-only) |
| `event_port` | `IEventPort` | Injected event port (read-only) |
| `config` | `PlannerConfig` | Planner configuration (read-only) |
| `plan_lock` | `asyncio.Lock` | V1 single-plan exclusion lock reference |
| `cancel_set` | `Set[str]` | Shallow copy of pending cancellation IDs |
| `running` | `bool` | True when dequeue loop is active |
| `subscriptions` | `List[SubscriptionHandle]` | Copy of active event subscriptions |
| `in_flight_request_id` | `Optional[str]` | Request ID of currently executing plan |

### 72.2 Public Query Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_mailbox()` | `-> IMailboxPort` | Returns injected mailbox. Used by kernel Phase 5 to connect PlannerAdapter. |
| `ready()` | `-> bool` | Returns `_running` flag. True after successful `start()`. |
| `health()` | `-> HealthStatus` | Returns `HealthStatus(status="HEALTHY/UNHEALTHY", details={...})`. Details include: `running`, `subscriptions` count, `cancel_set_size`, `plan_lock_locked`, `in_flight_request_id`. |

---

## 73. PlannerFactory Internal Wiring (10 Steps)

`PlannerFactory._wire(ports, config)` builds all internal components and returns a
`PlannerAgent`. Adapters are passed as a dict. All factory methods are `@staticmethod`.
`PlannerFactory.__init__` raises `TypeError` (pure static, no instance state).

### 73.1 Step-by-Step Wiring Order

```text
Step 1:   ToolCallRouter(fabric_retrieval=fabric_port, state_read=state_port,
                          bridge_port=bridge_port, config=config)
             -- Leaf service. Routes tool calls to 3 backend ports.
             -- Routing table: 4 tools -> 3 ports.

Step 2:   HILCoordinator(llm_port=llm_port, event_port=event_port, config=config)
             -- Leaf service. Manages HIL clarification/approval flow.
             -- Pub/sub on event bus for human responses.

Step 3:   SketchService(llm_port=llm_port, tool_router=tool_router, hil_coord=hil_coord)
             -- Stage 1. Agentic sketch with tool use + HIL clarification.

Step 4:   ExpandService(llm_port=llm_port, tool_router=tool_router)
             -- Stage 2. Agentic expand with tool use. No HIL.

Step 5:   ValidateService(llm_port=llm_port, fabric_retrieval=fabric_port,
                           hil_coord=hil_coord)
             -- Stage 3. Deterministic checks + LLM arbiter + HIL approval.

Step 6:   CommitService(bridge_port=bridge_port, delta_port=delta_port,
                         event_port=event_port)
             -- Stage 4. ZERO LLM (PLAN-03 structurally enforced).
             -- WAL persist + plan delivery event.

Step 7:   PipelineController(sketch=sketch, expand=expand, validate=validate,
                              commit=commit, delta_port=delta_port,
                              event_port=event_port, config=config)
             -- 4-stage pipeline orchestrator. Owns FSM + cancel checks.

Step 8:   PlannerAgent(mailbox=mailbox_port, pipeline=pipeline,
                        event_port=event_port, config=config)
             -- Top-level actor. Owns dequeue loop + plan lock.

Step 9:   (reserved -- start() NOT called here)
             -- start() enters infinite dequeue loop.
             -- Kernel must spawn: asyncio.create_task(agent.start())

Step 10:  return agent
```

### 73.2 Port-to-Service Wiring Matrix

| Port Slot | ToolCallRouter | HILCoordinator | Sketch | Expand | Validate | Commit | Pipeline | Agent |
|-----------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `llm_port` | | X | X | X | X | | | |
| `fabric_port` | X | | | | X | | | |
| `state_port` | X | | | | | | | |
| `bridge_port` | X | | | | | X | | |
| `delta_port` | | | | | | X | X | |
| `event_port` | | X | | | | X | X | X |
| `mailbox_port` | | | | | | | | X |

### 73.3 Port Validation (3 Passes)

| Pass | Check | Error |
|------|-------|-------|
| 1 | Completeness: all 7 ports non-None | `MissingPortError(port_name)` |
| 2 | Protocol compliance: `isinstance(port, Protocol)` | `InvalidPortError(port_name, expected_protocol, actual_type)` |
| 3 | Uniqueness: no two slots share `id()` | `DuplicatePortError(port_a, port_b)` |

### 73.4 Config Validation (10 Bounds)

| Field | Constraint |
|-------|-----------|
| `mailbox_max_depth` | >= 1 |
| `pipeline_timeout_ms` | > 0 |
| `max_tool_calls_per_plan` | >= 1 |
| `max_hil_rounds` | >= 0 |
| `total_token_budget` | > 0 |
| `sketch_timeout_ms` | > 0 |
| `expand_timeout_ms` | > 0 |
| `validate_timeout_ms` | > 0 |
| `commit_timeout_ms` | > 0 |
| `shutdown_grace_period_ms` | > 0 |

---

## 74. PlannerFactory Public Methods (4 total)

| Method | Signature | Returns | Use Case |
|--------|-----------|---------|----------|
| `create_standalone` | `async (config=None) -> PlannerAgent` | Agent with all 7 test adapters | Zero-dep unit tests |
| `create_for_testing` | `async (config=None, **overrides) -> Tuple[PlannerAgent, Dict[str, Any]]` | `(agent, adapters_dict)` -- selective overrides | Integration tests |
| `create_with_ports` | `async (*, 7 typed ports, config=None) -> PlannerAgent` | Agent with explicit ports | Cross-subsystem tests |
| `create_production` | `async (*, 7 typed ports, config=None) -> PlannerAgent` | Agent with production adapters | Kernel Phase 5 bootstrap |

All methods: validate config -> validate ports (except `create_standalone`) -> `_wire()` -> return.

`create_standalone` defers test adapter imports inside function body (prevents production
code from depending on test infrastructure).

`create_for_testing` validates override keys against known port slot names. Returns tuple
`(agent, ports_dict)` so tests can access capture adapters for assertion.

`create_with_ports` and `create_production` have identical signatures (7 keyword-only
typed port args). Both validate ports. Semantic difference: `create_production` is for
kernel bootstrap; `create_with_ports` is for cross-subsystem tests mixing real and test adapters.

---

## 75. PlannerAgent start() Sequence (5 Steps, SS23.1)

```python
async def start(self) -> None:
```

`start()` blocks indefinitely (enters dequeue loop at step 5). The kernel must
spawn it as a background task: `asyncio.create_task(planner.start())`.

```text
Step 1:  VALIDATE WIRING
           Log confirmation that mailbox, pipeline, and event_port are wired.
           In V1, all deps injected at construction; __init__ already validates non-None.

Step 2:  (no-op) Ports injected at construction.

Step 3:  SUBSCRIBE 4 EVENT TOPICS
           _subscriptions.append(event_port.subscribe(TOPIC_PLAN_REQUEST, _on_plan_request))
           _subscriptions.append(event_port.subscribe(TOPIC_PLAN_CANCEL, _on_plan_cancel))
           _subscriptions.append(event_port.subscribe(TOPIC_HIL_CLARIFICATION_RESP, _on_hil_clarification))
           _subscriptions.append(event_port.subscribe(TOPIC_HIL_APPROVAL_RESP, _on_hil_approval))
           Log: subscriptions_created {count: 4}

Step 4:  SET STATE
           _pipeline.reset()              -- FSM -> IDLE
           _cancel_set.clear()
           _in_flight_request_id = None
           _running = True

Step 4b: CRASH_RECOVERY (SS23.6)
           V1 simplified: log "v1_discard", no WAL check, no partial state resume.
           Full crash recovery (WAL-based resume) deferred to V2.

Step 5:  ENTER DEQUEUE LOOP (_run_loop)
           Blocks until _running = False. See Section 78 for loop details.
```

### 75.1 Event Handlers Registered at Step 3

| Handler | Topic | Behaviour |
|---------|-------|-----------|
| `_on_plan_request` | `k1.planner.plan.request.v1` | Parse PlanRequest from payload (dict or instance). If not running, reject. Schedule `_safe_enqueue(request)` via `loop.create_task()`. |
| `_on_plan_cancel` | `k1.planner.plan.cancel.v1` | Extract `request_id`. Add to `_cancel_set`. |
| `_on_hil_clarification` | `k1.hil.clarification_response.v1` | V1 stub: log warning, discard. HILCoordinator handles via its own subscription. |
| `_on_hil_approval` | `k1.hil.approval_response.v1` | V1 stub: log warning, discard. HILCoordinator handles via its own subscription. |

---

## 76. PlannerAgent stop() Sequence (8 Steps, SS23.5)

```python
async def stop(self) -> None:
```

Graceful shutdown with configurable grace period (`config.shutdown_grace_period_ms`,
default 5000ms).

```text
Step 1:  STOP ACCEPTING
           _running = False
           (dequeue loop will exit on next iteration)

Step 2:  DRAIN MAILBOX
           drained_requests = _mailbox.drain()      -- synchronous, non-blocking
           For each drained request:
             event_port.emit(TOPIC_PLAN_CANCELLED, PlanCancelledPayload(
               request_id=req.request_id, reason="shutdown",
               stage="QUEUED", trace_id=req.trace_id
             ))
           (best-effort: emit failures logged and swallowed)

Step 3:  CANCEL IN-FLIGHT PLAN
           If _plan_lock.locked() AND _in_flight_request_id is set:
             _cancel_set.add(_in_flight_request_id)
             Wait for in-flight plan to finish:
               asyncio.wait_for(_plan_lock.acquire(), timeout=grace_s)
               On success: release lock (plan finished cleanly)
               On TimeoutError: log warning, continue
           Inject sentinel PlanRequest(intent="__shutdown_sentinel__") to
           unblock dequeue() if loop is waiting (best-effort).

Step 4:  FLUSH PENDING DELTAS
           V1: no-op. Future: flush buffered deltas to DeltaBusAdapter.

Step 5:  PERSIST PARTIAL PLAN STATE
           V1: no-op (skip). Future: fire-and-forget IBridgePort.persist_plan().

Step 6:  SAFETY RELEASE LOCK
           If _plan_lock.locked():
             try: _plan_lock.release()
             except RuntimeError: pass    -- lock not owned by this task

Step 7:  UNSUBSCRIBE ALL EVENTS
           For each sub in _subscriptions:
             event_port.unsubscribe(sub)   -- catch + log failures
           _subscriptions.clear()

Step 8:  LOG SHUTDOWN COMPLETE
           Log: planner_agent.shutdown_complete {plans_drained: N, in_flight_cancelled: bool}
```

---

## 77. PlannerConfig Field Reference

`@dataclass(frozen=True)`. Defined in `k1/planner/config.py`.

### 77.1 Mailbox

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `mailbox_max_depth` | `int` | `5` | [1, 20] |

### 77.2 Pipeline Timeouts

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `pipeline_timeout_ms` | `int` | `45_000` | > 0 |
| `sketch_timeout_ms` | `int` | `8_000` | > 0 |
| `expand_timeout_ms` | `int` | `5_000` | > 0 |
| `validate_timeout_ms` | `int` | `3_000` | > 0 |
| `commit_timeout_ms` | `int` | `1_000` | > 0 |

### 77.3 Token Budgets

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `total_token_budget` | `int` | `3_500` | > 0, >= sketch + expand + validate |
| `sketch_max_tokens` | `int` | `2_000` | > 0 |
| `expand_max_tokens` | `int` | `1_000` | > 0 |
| `validate_max_tokens` | `int` | `500` | > 0 |

### 77.4 Temperatures

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `sketch_temperature` | `float` | `0.7` | [0.0, 2.0] |
| `expand_temperature` | `float` | `0.3` | [0.0, 2.0] |
| `validate_temperature` | `float` | `0.2` | [0.0, 2.0] |

### 77.5 Tool and HIL Limits

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `max_tool_calls_per_plan` | `int` | `6` | [1, 20] PLAN-05 |
| `max_hil_rounds` | `int` | `2` | [0, 5] PLAN-10 |
| `hil_clarification_timeout_ms` | `int` | `60_000` | > 0 |
| `hil_approval_timeout_ms` | `int` | `120_000` | > 0 |

### 77.6 Micro-Replan

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `micro_replan_timeout_ms` | `int` | `10_000` | > 0 |
| `micro_replan_max_tokens` | `int` | `2_000` | > 0, >= micro_sketch + micro_expand + micro_validate |
| `micro_sketch_max_tokens` | `int` | `1_024` | > 0 |
| `micro_sketch_timeout_ms` | `int` | `5_000` | > 0 |
| `micro_expand_max_tokens` | `int` | `512` | > 0 |
| `micro_expand_timeout_ms` | `int` | `3_000` | > 0 |
| `micro_validate_max_tokens` | `int` | `256` | > 0 |
| `micro_validate_timeout_ms` | `int` | `2_000` | > 0 |

### 77.7 Shutdown

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `shutdown_grace_period_ms` | `int` | `5_000` | > 0 |

### 77.8 Construction

`PlannerConfig()` -- all defaults.
`PlannerConfig.from_dict(overrides)` -- class method, validates unknown keys, raises
`ValueError` on unknown. `__post_init__` validates cross-field constraints
(total_token_budget >= stage sum, micro_replan_max_tokens >= micro stage sum).

---

## 78. Planner Dequeue Loop (_run_loop)

The dequeue loop is the central execution driver. It runs inside `PlannerAgent.start()`
(step 5) and blocks until `_running` is set to False.

```text
while _running:
  1. request = await _mailbox.dequeue()     -- BLOCKS until a PlanRequest arrives
  2. Shutdown guard: if not _running, break
  3. CANCEL PRE-CHECK (checkpoint 1):
       if request.request_id in _cancel_set:
         _cancel_set.discard(request.request_id)
         emit TOPIC_PLAN_CANCELLED(request_id, reason="cancelled_before_start",
                                    stage="PRE_CHECK", trace_id)
         continue   -- skip to next request
  4. _in_flight_request_id = request.request_id
  5. await _plan_lock.acquire()
  6. try:
       cancel_check = lambda: request.request_id in self._cancel_set
       await _pipeline.execute(request, cancel_check)
     except PlanCancelledError:
       (already handled by PipelineController -- emit plan.cancelled.v1)
     except PlannerError as e:
       log plan_failed {stage, error}
     except Exception as e:
       log unexpected_error
       emit TOPIC_PLAN_FAILED(PlanFailedPayload(
         request_id, stage="INTERNAL", error_code="INTERNAL_ERROR",
         error_message=str(e), tokens_used=0, duration_ms=0, trace_id
       ))
     finally:
       _in_flight_request_id = None
       _cancel_set.discard(request.request_id)
       _pipeline.reset()    -- FSM -> IDLE
       _plan_lock.release()
```

---

## 79. PipelineController Reference

### 79.1 Constructor

```python
class PipelineController:
    __slots__ = (
        "_sketch", "_expand", "_validate", "_commit",
        "_delta_port", "_event_port", "_config", "_fsm",
        "_stage_token_usage", "_stage_cost", "_stage_latency",
        "_total_plan_tokens", "_tool_call_count", "_hil_round_count",
        "_current_request", "_plan_start_time", "_revise_count",
        "_active_cancel_check",
    )
```

Constructor: `PipelineController(sketch, expand, validate, commit, delta_port, event_port, config)`
-- 7 injected deps. All validated non-None.

### 79.2 FSM (PlanStateMachine)

```python
class PlanState(str, Enum):
    IDLE          = "IDLE"           # Resting
    SKETCHING     = "SKETCHING"      # Stage 1
    EXPANDING     = "EXPANDING"      # Stage 2
    VALIDATING    = "VALIDATING"     # Stage 3
    COMMITTING    = "COMMITTING"     # Stage 4
    MICRO_SKETCH  = "MICRO_SKETCH"   # Micro Stage 1
    MICRO_EXPAND  = "MICRO_EXPAND"   # Micro Stage 2
    MICRO_VALIDATE= "MICRO_VALIDATE" # Micro Stage 3
    COMPLETED     = "COMPLETED"      # Terminal
    FAILED        = "FAILED"         # Terminal
    CANCELLED     = "CANCELLED"      # Terminal
```

| Property | Logic |
|----------|-------|
| `is_terminal` | COMPLETED, FAILED, CANCELLED |
| `is_micro` | MICRO_SKETCH, MICRO_EXPAND, MICRO_VALIDATE |
| `is_active` | not IDLE and not terminal |

Transition table:

| Source | Legal Targets |
|--------|---------------|
| IDLE | {SKETCHING, MICRO_SKETCH} |
| SKETCHING | {EXPANDING, FAILED, CANCELLED} |
| EXPANDING | {VALIDATING, FAILED, CANCELLED} |
| VALIDATING | {COMMITTING, EXPANDING, FAILED, CANCELLED} |
| COMMITTING | {COMPLETED, CANCELLED} |
| COMPLETED | {IDLE} |
| FAILED | {IDLE} |
| CANCELLED | {IDLE} |
| MICRO_SKETCH | {MICRO_EXPAND, FAILED} |
| MICRO_EXPAND | {MICRO_VALIDATE, FAILED} |
| MICRO_VALIDATE | {COMMITTING, FAILED} |

Special methods: `reset()` (terminal -> IDLE, no callback), `force_failed()` (active -> FAILED,
bypass table), `force_cancelled()` (active -> CANCELLED, bypass table).

### 79.3 execute() Orchestration (14 Steps)

```text
Step 1:   reset(), set _current_request, _plan_start_time, _active_cancel_check
Step 2:   FSM: IDLE -> SKETCHING (trigger "plan_start")
Step 3:   SKETCH: ctx = _create_stage_context(SKETCH)
            sketch_result = await _sketch.execute(request, ctx)
Step 4:   Cancel check + timeout check
Step 5:   FSM: SKETCHING -> EXPANDING (trigger "sketch_complete")

--- EXPAND + VALIDATE LOOP (revise routing) ---
Step 6:   EXPAND: ctx = _create_stage_context(EXPAND)
            expanded_plan = await _expand.execute(sketch_result, ctx)
Step 7:   Cancel check + timeout check
Step 8:   FSM: EXPANDING -> VALIDATING (trigger "expand_complete")
Step 9:   VALIDATE: ctx = _create_stage_context(VALIDATE)
            verdict = await _validate.execute(expanded_plan, ctx)
Step 10:  VERDICT ROUTING:
            approved -> break to COMMIT
            revise (1st) -> _revise_count++, FSM -> EXPANDING, continue loop
            revise (2nd) -> treat as approved, break
            reject (1st) -> _revise_count++, FSM -> EXPANDING, continue loop
            reject (2nd) -> force_failed(), raise ValidateRejectedError
Step 10b: Cancel check + timeout check (checkpoint 4)
--- END LOOP ---

Step 11:  FSM: VALIDATING -> COMMITTING (trigger "verdict_approved")
Step 12:  COMMIT: await _commit.execute(expanded_plan, verdict, ctx)
Step 13:  FSM: COMMITTING -> COMPLETED (trigger "commit_complete")
Step 14:  Emit plan_end delta. Return CommittedPlan.

Error: any stage exception -> force_failed(), emit plan.failed.v1, re-raise.
Cancel: PlanCancelledError -> re-raise (FSM already CANCELLED).
```

### 79.4 micro_replan() Flow

Abbreviated 3-stage flow (SKETCH -> EXPAND -> VALIDATE -> COMMIT):

```text
1. Validate request fields, reset counters, set micro context
2. _validate_overlap(request) -- 3-way match (exact, substring)
3. FSM: IDLE -> MICRO_SKETCH
4. micro_sketch = await _sketch.micro_execute(request, ctx)
5. Cancel + timeout check
6. FSM: MICRO_SKETCH -> MICRO_EXPAND
7. micro_expand = await _expand.micro_execute(micro_sketch, ctx)
8. _enforce_plan12(replacement_plan, completed_ids)
9. Cancel + timeout check
10. FSM: MICRO_EXPAND -> MICRO_VALIDATE
11. verdict = await _validate.micro_execute(micro_expand, ctx)
12. Verdict routing: reject -> None; approved/revise -> COMMIT
13. FSM: MICRO_VALIDATE -> COMMITTING
14. Commit + emit telemetry + return CommittedPlan
All failures -> return None (no plan.failed.v1).
```

### 79.5 Per-Plan Telemetry State

| Field | Type | Reset Value | Purpose |
|-------|------|-------------|---------|
| `_stage_token_usage` | `Dict[str, int]` | `{SKETCH: 0, EXPAND: 0, VALIDATE: 0, COMMIT: 0}` | Token count per stage |
| `_stage_cost` | `Dict[str, float]` | `{SKETCH: 0.0, ...}` | Cost per stage |
| `_stage_latency` | `Dict[str, int]` | `{SKETCH: 0, ...}` | Latency ms per stage |
| `_total_plan_tokens` | `int` | `0` | Running total across stages |
| `_tool_call_count` | `int` | `0` | PLAN-05 counter |
| `_hil_round_count` | `int` | `0` | PLAN-10 counter |
| `_revise_count` | `int` | `0` | Validate revise loop counter (max 1) |

---

## 80. Planner Event Reference

### 80.1 Events Emitted by Planner

| Topic | Constant | Producer | Payload | When |
|-------|----------|----------|---------|------|
| `k1.planner.plan.ready.v1` | `TOPIC_PLAN_READY` | CommitService | `CommittedPlan` | Plan committed successfully |
| `k1.planner.plan.failed.v1` | `TOPIC_PLAN_FAILED` | PipelineController / PlannerAgent | `PlanFailedPayload(request_id, stage, error_code, error_message, tokens_used, duration_ms, trace_id, partial_state)` | Stage error, timeout, or internal error |
| `k1.planner.plan.cancelled.v1` | `TOPIC_PLAN_CANCELLED` | PlannerAgent | `PlanCancelledPayload(request_id, reason, stage, trace_id)` | Cancel at pre-check, between stages, or shutdown drain |
| `k1.planner.micro_replan.ready.v1` | `TOPIC_MICRO_REPLAN_READY` | PipelineController | `CommittedPlan` | Micro-replan committed |
| `k1.planner.delta.v1` | `TOPIC_DELTA` | PipelineController | `DeltaPayload` | Stage transitions, tool results, plan end |
| `k1.hil.clarification.v1` | `TOPIC_HIL_CLARIFICATION` | HILCoordinator | `HILClarificationPayload(request_id, question, context, trace_id)` | Ambiguous intent needs user clarification |
| `k1.hil.approval_request.v1` | `TOPIC_HIL_APPROVAL_REQ` | HILCoordinator | `HILApprovalRequestPayload(request_id, summary, options, side_effects, safety_assessment)` | High-risk plan needs user approval |

### 80.2 Events Consumed by Planner

| Topic | Constant | Consumer | Handler | Behaviour |
|-------|----------|----------|---------|-----------|
| `k1.planner.plan.request.v1` | `TOPIC_PLAN_REQUEST` | PlannerAgent | `_on_plan_request` | Parse PlanRequest, schedule enqueue to mailbox |
| `k1.planner.plan.cancel.v1` | `TOPIC_PLAN_CANCEL` | PlannerAgent | `_on_plan_cancel` | Add request_id to cancel set |
| `k1.hil.clarification_response.v1` | `TOPIC_HIL_CLARIFICATION_RESP` | PlannerAgent (stub) + HILCoordinator (real) | PlannerAgent: log + discard (V1). HILCoordinator: correlate by request_id, resolve asyncio.Event | User clarification response |
| `k1.hil.approval_response.v1` | `TOPIC_HIL_APPROVAL_RESP` | PlannerAgent (stub) + HILCoordinator (real) | PlannerAgent: log + discard (V1). HILCoordinator: correlate by request_id, resolve asyncio.Event | User approval response |

### 80.3 Delta Payload Types

| `delta_type` Constant | When Emitted | `section` | `data` Contents |
|-----------------------|-------------|-----------|-----------------|
| `DELTA_STAGE_TRANSITION` | FSM state change | `"pipeline"` | `{from_state, to_state, trigger}` |
| `DELTA_TOOL_RESULT` | Tool call completes | `"tools"` | `{tool_name, status, result}` |
| `DELTA_HIL_EVENT` | HIL interaction | `"pipeline"` | `{type, request_id, question/response}` |
| `DELTA_PLAN_UPDATE` | Intermediate progress | `"plan"` | `{stage, step_count, ...}` |
| `DELTA_PLAN_END` | Plan completes/fails | `"plan"` | `{status, duration_ms, tokens_used}` |
| `DELTA_PLAN_CANCELLED` | Plan cancelled | `"plan"` | `{reason, stage, request_id}` |
| `DELTA_MICRO_REPLAN` | Micro-replan progress | `"plan"` | `{stage, status}` |
| `DELTA_CRASH_RECOVERY` | Recovery at startup | `"pipeline"` | `{action: "v1_discard"}` |

---

## 81. Pipeline Stages Reference

### 81.1 SketchService (Stage 1)

- Location: `k1/planner/stages/sketch_service.py` (1307 lines)
- Constructor: `SketchService(llm_port, tool_router, hil_coord)`
- Slots: `_llm_port`, `_tool_router`, `_hil_coord`
- Input: `PlanRequest` + `StageContext`
- Output: `SketchResult(rough_steps, capability_candidates, rationale)`
- Ports used: `ILLMPort` (CHAT capability), `ToolCallRouterLike` (4 tools), `HILCoordinatorLike` (clarification)
- LLM config: `sketch_max_tokens`, `sketch_temperature` (0.7)
- Max tool rounds: 6 (`_MAX_TOOL_ROUNDS`)
- Output schema: `SKETCH_OUTPUT_SCHEMA` (rough_steps array, rationale string, needs_clarification boolean)
- Retry: on `SketchFailedError`, retry once simplified (no tools, no HIL). Second failure raises.
- HIL: if `needs_clarification=true` in LLM response and `allow_hil=True`, call
  `hil_coord.request_clarification()`, re-run with clarification addendum.
- 4 available tools: `discover_capabilities`, `query_session_context`, `recall_long_term_memory`, `find_prompts`
- Micro variant: `micro_execute(request: MicroReplanRequest, ctx)` -- no HIL, no retry, abbreviated prompt

### 81.2 ExpandService (Stage 2)

- Location: `k1/planner/stages/expand_service.py` (1562 lines)
- Constructor: `ExpandService(llm_port, tool_router)`
- Slots: `_llm_port`, `_tool_router`
- Input: `SketchResult` + `PlanRequest` + `StageContext` + optional `arbiter_feedback: List[str]`
- Output: `ExpandedPlan(steps, dependencies, tool_mappings, rationale)`
- Ports used: `ILLMPort` (STRUCTURED capability), `ExpandToolRouterLike` (4 tools)
- LLM config: `expand_max_tokens`, `expand_temperature` (0.3)
- Max tool rounds: 6
- Output schema: `EXPAND_OUTPUT_SCHEMA` (steps array, dependencies object, rationale string)
- Retry: on failure, retry simplified. Second failure: `_build_degraded_plan(sketch_result)` (direct-map rough_steps -> Plan Steps)
- Post-LLM enrichment (`_enrich_steps`): fills 6 infra fields per step from CapabilityContract metadata
  (`has_side_effects`, `compensation`, `timeout_ms`, `required_context`, `safety_band_min`, `condition`)
- 4 available tools: `discover_capabilities`, `get_capability_schema`, `find_prompts`, `query_session_context`
- Step ID pattern: `^s[0-9]+$` (enforced by regex, `_STEP_ID_RE`)
- Default step timeout: 10000ms
- Micro variant: `micro_execute(micro_sketch_result, completed_results, ctx)` -- no retry, no degraded fallback

### 81.3 ValidateService (Stage 3)

- Location: `k1/planner/stages/validate_service.py` (1216 lines)
- Constructor: `ValidateService(llm_port, fabric_retrieval, hil_coord)`
- Slots: `_llm_port`, `_fabric_retrieval`, `_hil_coord`
- Input: `ExpandedPlan` + `PlanRequest` + `StageContext` + optional `cached_capabilities`
- Output: `ValidationVerdict(status, issues, confidence, rationale, deterministic_pass, safety_assessment, suggested_fixes)`
- Ports used: `ILLMPort` (STRUCTURED capability), `IFabricRetrievalPort` (capability existence), `HILCoordinatorLike` (approval)
- NO ToolCallRouter (validate does NOT use tools)
- Phase 1: Deterministic checks (DAG acyclicity via Kahn's algorithm, capability existence, structural)
- Phase 2: LLM arbiter (STRUCTURED, 512 tokens, 0.1 temperature, 3s timeout). If LLM unavailable + det pass -> auto-approve.
- Phase 3: HIL approval for high-impact plans (side effects or caution/unsafe safety)
- Verdict schema: `VALIDATE_VERDICT_SCHEMA` (status, reasons array, coherence_score, safety_assessment, completeness)
- 10 deterministic check names: `CHECK_DAG_CYCLE`, `CHECK_CAPABILITY_MISSING`, `CHECK_PARAM_TYPE_MISMATCH`,
  `CHECK_UNSAFE_CAPABILITY`, `CHECK_LLM_ARBITER_REJECT`, `CHECK_TOOL_BUDGET_EXCEEDED`, `CHECK_STEP_ID_DUPLICATE`,
  `CHECK_DANGLING_DEPENDENCY`, `CHECK_SELF_REFERENCE`, `CHECK_INTER_STEP_REF`
- Meta-capability `tool.meta.build_agent` always passes capability existence check
- Micro variant: `micro_execute(expanded_plan, ctx, cached_capabilities, completed_step_ids)` -- det checks with cross-boundary allowance, reduced arbiter (256 tokens, 2s), no HIL, `revise` upgraded to `approved`

### 81.4 CommitService (Stage 4)

- Location: `k1/planner/stages/commit_service.py` (538 lines)
- Constructor: `CommitService(bridge_port, delta_port, event_port)` -- **NO LLM** (PLAN-03)
- Slots: `_bridge_port`, `_delta_port`, `_event_port`
- Input: `ExpandedPlan` + `ValidationVerdict` + `StageContext`
- Output: `CommittedPlan(plan_id, request_id, intent, steps, trace_id, dependencies, estimated_duration_ms, created_at)`
- Ports used: `IBridgePort` (WAL persist), `IDeltaEmitPort` (deltas), `IEventPort` (plan.ready delivery)
- 11-step assembly: `plan_id = uuid4()`, `created_at = time.time()`, `steps = expanded_plan.steps`,
  `dependencies = expanded_plan.dependencies`, `estimated_duration_ms` via critical path
  (Kahn's DP on DAG), assemble `CommittedPlan`
- WAL persist: `bridge_port.persist_plan(plan, trace_id=trace_id)` -- retry once, fire-and-forget on failure
- Delivery: `event_port.emit(TOPIC_PLAN_READY, committed_plan)` -- retry once
- Emit stage delta + plan_end delta after delivery
- Deterministic: zero non-determinism, zero LLM calls, pure assembly

---

## 82. Leaf Services Reference

### 82.1 ToolCallRouter

- Location: `k1/planner/services/tool_call_router.py` (411 lines)
- Constructor: `ToolCallRouter(fabric_retrieval, state_read, bridge_port, *, config=None)`
- Slots: `_fabric_retrieval`, `_state_read`, `_bridge_port`, `_tool_call_count`, `_config`
- Purpose: routes tool calls from SketchService and ExpandService to the 3 backend ports

Routing table (frozen `MappingProxyType`):

| Tool Name | Port | Method |
|-----------|------|--------|
| `discover_capabilities` | `IFabricRetrievalPort` | `discover_capabilities(domain, intent, safety_band, session_context, top_k)` |
| `find_relevant_prompts` | `IFabricRetrievalPort` | `find_relevant_prompts(intent, domain, safety_band, top_k)` |
| `query_planning_context` | `IStateReadPort` | `read_sections(sections, trace_id)` |
| `recall_for_planning` | `IBridgePort` | `recall(query, selectors, trace_id)` |

Retry policy:

| Tool Name | Timeout | Retries |
|-----------|---------|---------|
| `discover_capabilities` | 50ms | 1 |
| `find_relevant_prompts` | 50ms | 1 |
| `query_planning_context` | 10ms | 0 |
| `recall_for_planning` | 100ms | 0 |

Key methods:

- `call(tool_name, **params)` -- route + dispatch + increment `_tool_call_count`
- `discover(intent, *, domain, safety_band, top_k)` -- convenience
- `find_prompts(intent, *, domain, top_k)` -- convenience
- `read_context(session_id, sections)` -- convenience
- `recall_memory(query, trace_id)` -- convenience
- `get_schema(capability_name, *, version)` -- bypasses routing table, does NOT count against PLAN-05
- `reset()` -- sets `_tool_call_count = 0`

Budget enforcement (PLAN-05): `_check_budget()` raises `BudgetExhaustedError` if
`_tool_call_count >= config.max_tool_calls_per_plan`.

### 82.2 HILCoordinator

- Location: `k1/planner/services/hil_coordinator.py` (575 lines)
- Constructor: `HILCoordinator(llm_port, event_port, *, config=None)`
- Slots: `_llm_port`, `_event_port`, `_config`, `_round_count`, `_pending_request_id`, `_hil_type`, `_waiting`
- Purpose: manages Human-in-the-Loop clarification and approval flows

Protocol: `HILCoordinatorLike(Protocol)` with `round_count`, `reset()`,
`request_clarification(request_id, question_context)`, `request_approval(request_id, plan_summary, side_effects, safety_assessment, estimated_duration_ms)`.

Key methods:

`request_clarification(request_id, question_context) -> Optional[str]` (7 steps):

```text
1. Check round budget: _round_count < max_hil_rounds (PLAN-10). Exhausted -> return None.
2. Generate question via LLM (CHAT, 300 tokens, 3s). Failure -> return None.
3. Emit TOPIC_HIL_CLARIFICATION with HILClarificationPayload.
4. Set pending state (_pending_request_id, _hil_type="clarification", _waiting=True).
5. _wait_for_response(TOPIC_HIL_CLARIFICATION_RESP, request_id, hil_clarification_timeout_ms).
   Timeout -> increment round, return None.
6. Clear pending state.
7. Increment _round_count, return user response text.
```

`request_approval(request_id, plan_summary, side_effects, safety_assessment, estimated_duration_ms) -> str` (5 steps):

```text
1. Generate summary via LLM (CHAT, 400 tokens, 3s). Failure -> _evaluate_auto_approve_decision.
2. Emit TOPIC_HIL_APPROVAL_REQ with HILApprovalRequestPayload(options=["approve", "modify", "reject"]).
3. Set pending state.
4. _wait_for_response(TOPIC_HIL_APPROVAL_RESP, request_id, hil_approval_timeout_ms).
   Timeout -> _evaluate_auto_approve_decision.
5. Parse response -> one of "approve", "modify", "reject".
```

`_evaluate_auto_approve_decision`: if safety == "safe" or no side effects -> "approve",
else raise `HILTimeoutError`.

`_wait_for_response(topic, request_id, timeout_ms)`: subscribe inline handler that
correlates by `request_id` and sets `asyncio.Event`. `asyncio.wait_for(event.wait(), timeout)`.
Unsubscribe in `finally`.

`reset()`: `_round_count = 0`, clear pending state.

---

## 83. Planner Error Hierarchy

All Planner errors extend `PlannerError(Exception)`.

```text
PlannerError(stage, request_id, trace_id)
  |-- SketchFailedError          -- SKETCH failed after retries
  |-- ExpandFailedError          -- EXPAND failed after retries
  |-- ValidateRejectedError      -- Plan rejected by VALIDATE (2nd reject)
  |-- CommitFailedError          -- COMMIT stage failed
  |-- BudgetExhaustedError       -- Total token budget exhausted (PLAN-04)
  |-- MailboxFullError           -- Mailbox at max depth
  |-- ShutdownError              -- Planner shutting down, rejecting requests
  |-- PlanCancelledError         -- Cancelled by Orchestrator (cancel set)
  |-- HILTimeoutError            -- HIL response timed out
  |-- HILBudgetExceededError     -- PLAN-10 HIL round budget exceeded
  |-- LLMTimeoutError            -- Model Hub request timed out
  |-- BudgetExceededError        -- Token budget exceeded (MH-04)
  |-- AdapterException(degraded) -- Adapter infrastructure failure
  |-- UnknownToolError           -- Unknown tool name in ToolCallRouter
```

Factory errors (not thrown during planning):

```text
  |-- InvalidPortError(port_name, expected_protocol, actual_type)
  |-- MissingPortError(port_name)
  |-- DuplicatePortError(port_a, port_b)
  |-- InvalidConfigError(field_name, value, constraint)
  |-- PlannerInitError(detail)
```

FSM error:

```text
  |-- IllegalStateTransitionError(from_state, to_state, trigger)
```

---

## 84. Planner Types Reference

### 84.1 Core Dataclasses

| Type | Frozen | Fields | Validation |
|------|--------|--------|------------|
| `RoughStep` | Yes | `intent: str`, `suggested_capability: Optional[str]`, `depends_on: List[str]`, `confidence: float` | intent non-empty, confidence [0.0, 1.0] |
| `SketchResult` | Yes | `rough_steps: List[RoughStep]`, `capability_candidates: List[ScoredCapability]`, `rationale: str` | rough_steps non-empty, rationale non-empty |
| `ExpandedPlan` | Yes | `steps: List[PlanStep]`, `dependencies: Dict[str, List[str]]`, `tool_mappings: Dict[str, str]`, `rationale: str` | steps non-empty, rationale non-empty |
| `ValidationIssue` | Yes | `check_name: str`, `severity: str`, `step_id: Optional[str]`, `detail: str` | check_name non-empty, severity in {"error", "warning"} |
| `ValidationVerdict` | Yes | `status: str`, `issues: List[ValidationIssue]`, `confidence: float`, `rationale: str`, `deterministic_pass: bool`, `safety_assessment: str`, `suggested_fixes: List[str]` | status in {"approved", "revise", "reject"}, rationale non-empty |
| `StageContext` | Yes | `request_id: str`, `trace_id: str`, `timeout_remaining_ms: int`, `token_budget_remaining: int`, `cancel_check: Callable[[], bool]`, `stage_budget: Optional[RequestConstraints]` | request_id/trace_id non-empty, timeout > 0 |
| `DeltaPayload` | Yes | `agent_id: str`, `delta_type: str`, `section: str`, `data: Dict[str, Any]`, `trace_id: str` | agent_id/trace_id non-empty, delta_type/section from valid sets |
| `RequestConstraints` | Yes | `max_tokens: int`, `timeout_ms: int`, `priority: str`, `temperature: float`, `consumer_id: str` | max_tokens > 0, timeout_ms > 0, temperature [0.0, 1.0] |
| `HubRequest` | Yes | `capability: str`, `payload: Dict[str, Any]`, `constraints: RequestConstraints`, `trace_id: str` | capability in {"CHAT", "STRUCTURED"} |
| `HubResponse` | Yes | `result: Dict[str, Any]`, `metadata: Dict[str, Any]` | (none) |
| `RecallResponse` | Yes | `facts: List[Dict[str, Any]]`, `scores: List[float]`, `trace_id: str` | (none) |
| `TokenUsageRecord` | **Mutable** | `stage: str`, `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int` | stage non-empty, all counts >= 0 |
| `HealthStatus` | Yes | `status: str`, `details: Dict[str, Any]` | (none) |

### 84.2 Enums

| Enum | Values |
|------|--------|
| `StagePhase(str, Enum)` | `SKETCH`, `EXPAND`, `VALIDATE`, `COMMIT` |
| `ToolCallStatus(str, Enum)` | `SUCCESS`, `TIMEOUT`, `ERROR`, `BUDGET_EXHAUSTED` |

### 84.3 Constants

| Category | Constants |
|----------|-----------|
| Verdict statuses | `VERDICT_APPROVED`, `VERDICT_REVISE`, `VERDICT_REJECT` |
| Severities | `SEVERITY_ERROR`, `SEVERITY_WARNING` |
| Check names | `CHECK_DAG_CYCLE`, `CHECK_CAPABILITY_MISSING`, `CHECK_PARAM_TYPE_MISMATCH`, `CHECK_UNSAFE_CAPABILITY`, `CHECK_LLM_ARBITER_REJECT`, `CHECK_TOOL_BUDGET_EXCEEDED`, `CHECK_STEP_ID_DUPLICATE`, `CHECK_DANGLING_DEPENDENCY`, `CHECK_SELF_REFERENCE`, `CHECK_INTER_STEP_REF` |
| Safety levels | `SAFETY_SAFE`, `SAFETY_CAUTION`, `SAFETY_UNSAFE`, `SAFETY_UNKNOWN` |
| Delta types | `DELTA_STAGE_TRANSITION`, `DELTA_TOOL_RESULT`, `DELTA_HIL_EVENT`, `DELTA_PLAN_UPDATE`, `DELTA_PLAN_END`, `DELTA_PLAN_CANCELLED`, `DELTA_MICRO_REPLAN`, `DELTA_CRASH_RECOVERY` |
| Sections | `SECTION_PIPELINE`, `SECTION_PLAN`, `SECTION_TOOLS` |
| Agent ID | `PLANNER_AGENT_ID = "planner"` |

---

## 85. Planner Concurrency Model

### 85.1 V1: Single-Plan Exclusion

One plan at a time. `asyncio.Lock` (`_plan_lock`) acquired at dequeue loop step 5,
released in `finally` after pipeline completes or errors. Additional requests queue
in the mailbox (max depth 5, configurable).

### 85.2 Cancel Protocol (SS24.2)

Cooperative flag-based cancellation checked at 5 checkpoints:

| # | Location | Guard |
|---|----------|-------|
| 1 | Dequeue loop pre-check | `request_id in _cancel_set` before acquire |
| 2 | After SKETCH | `cancel_check()` in PipelineController |
| 3 | After EXPAND | `cancel_check()` in PipelineController |
| 4 | After VALIDATE | `cancel_check()` in PipelineController |
| 5 | At shutdown | `_cancel_set.add(_in_flight_request_id)` during stop() |

On cancel: FSM -> CANCELLED, emit `plan.cancelled.v1`, raise `PlanCancelledError`.
`_cancel_set` is the sole source of truth. Idempotent (Set ignores duplicate adds).

### 85.3 Micro-Replan Concurrency

`micro_replan()` acquires `_plan_lock` -- blocks until any in-flight plan completes.
With 10s caller-side timeout and typical plan duration ~12s p50, micro-replan will
almost always timeout during active plan (by design -- Orchestrator falls back to
original plan). Micro-replan bypasses the mailbox queue.

---

## 86. Planner Gotchas

| # | Gotcha | Consequence if Violated |
| - | ------ | ----------------------- |
| PG-01 | `PipelineController.reset()` must be called after every plan (in loop `finally`), not just on success | FSM stuck in terminal state, next plan gets `IllegalStateTransitionError` |
| PG-02 | `SketchService` retry uses simplified mode (no tools, no HIL). If both attempts fail, `SketchFailedError` propagates to PlannerAgent. | Swallowing error = plan silently lost |
| PG-03 | `ExpandService` degraded fallback (`_build_degraded_plan`) creates a direct-map plan from `SketchResult.rough_steps`. Degraded plans may not have valid capability bindings. | Degraded plan reaches COMMIT but Orchestrator DAG may fail at execution |
| PG-04 | `ValidateService` arbiter uses 0.1 temperature (near-deterministic). If LLM unavailable AND deterministic checks pass, auto-approve kicks in. | No LLM arbiter = only deterministic validation, may miss semantic issues |
| PG-05 | `CommitService` has zero ILLMPort (PLAN-03). Adding LLM to commit breaks the `no LLM at commit` invariant structurally enforced by the constructor. | Factory `_wire()` step 6 does not pass `llm_port` -- changing this requires architectural review |
| PG-06 | `ToolCallRouter._tool_call_count` is per-plan (reset by `reset()`). If reset is missed between plans, PLAN-05 budget carries over. | Second plan immediately hits budget limit from first plan's count |
| PG-07 | `HILCoordinator._round_count` is per-plan (reset by `reset()`). If reset is missed, PLAN-10 budget carries over. | HIL requests rejected even for fresh plan |
| PG-08 | `_on_plan_request` handler uses `loop.create_task(_safe_enqueue)` -- enqueue is async. If the event loop is blocked, enqueue is deferred. | Plan request delivery latency increases under load |
| PG-09 | `_on_hil_clarification` and `_on_hil_approval` in PlannerAgent are V1 stubs (log + discard). Real handling is via HILCoordinator's own inline subscriptions. | Do not add logic to PlannerAgent handlers -- it would conflict with HILCoordinator's subscription |
| PG-10 | `micro_replan()` returns `None` on all failures (never raises, never emits `plan.failed.v1`). The caller (Orchestrator) must handle None = keep original plan. | Treating None as success = executing a stale plan |
| PG-11 | Validate revise loop allows exactly 1 retry. Second `revise` is treated as `approved`. Second `reject` raises `ValidateRejectedError`. | Infinite revise loop impossible by design; but 2nd-revise auto-approval may pass a marginal plan |
| PG-12 | `MailboxAdapter.set_pipeline_controller(controller)` must be called after both `MailboxAdapter` and `PipelineController` are created. Factory `_wire()` does not call this -- manual step if micro_replan is used. | `micro_replan()` raises `RuntimeError("PipelineController not set")` |

---

## 87. Planner File Locations Reference

| What | Path |
| ---- | ---- |
| Package facade | `k1/planner/__init__.py` |
| PlannerAgent | `k1/planner/planner_agent.py` |
| PlannerFactory | `k1/planner/factory.py` |
| PipelineController | `k1/planner/pipeline_controller.py` |
| PlanStateMachine | `k1/planner/plan_fsm.py` |
| PlannerConfig | `k1/planner/config.py` |
| Types + errors | `k1/planner/types.py` |
| Events + payloads | `k1/planner/events.py` |
| Port: IMailboxPort | `k1/planner/ports/mailbox_port.py` |
| Port: ILLMPort | `k1/planner/ports/llm_port.py` |
| Port: IFabricRetrievalPort | `k1/planner/ports/fabric_retrieval_port.py` |
| Port: IStateReadPort | `k1/planner/ports/state_read_port.py` |
| Port: IBridgePort | `k1/planner/ports/bridge_port.py` |
| Port: IDeltaEmitPort | `k1/planner/ports/delta_emit_port.py` |
| Port: IEventPort | `k1/planner/ports/event_port.py` |
| Adapter: MailboxAdapter | `k1/planner/adapters/mailbox_adapter.py` |
| Adapter: LLMGatewayAdapter | `k1/planner/adapters/llm_gateway_adapter.py` |
| Adapter: FabricRetrievalAdapter | `k1/planner/adapters/fabric_retrieval_adapter.py` |
| Adapter: SessionStateReadAdapter | `k1/planner/adapters/session_state_adapter.py` |
| Adapter: BridgeAdapter | `k1/planner/adapters/bridge_adapter.py` |
| Adapter: DeltaBusAdapter | `k1/planner/adapters/delta_bus_adapter.py` |
| Adapter: EventBusAdapter | `k1/planner/adapters/event_bus_adapter.py` |
| Stage: SketchService | `k1/planner/stages/sketch_service.py` |
| Stage: ExpandService | `k1/planner/stages/expand_service.py` |
| Stage: ValidateService | `k1/planner/stages/validate_service.py` |
| Stage: CommitService | `k1/planner/stages/commit_service.py` |
| Service: ToolCallRouter | `k1/planner/services/tool_call_router.py` |
| Service: HILCoordinator | `k1/planner/services/hil_coordinator.py` |
| Test Adapters | `tests/k1/planner/adapters/` |
| Factory Tests | `tests/k1/planner/test_factory.py` |

---

## 88. Concierge Architecture Overview

The Concierge is the user-facing conversational agent in K1. It owns the
entire request–response lifecycle: receive user input, classify intent,
dispatch to the correct tier (LOW / MEDIUM / HIGH), stream responses back,
manage affect and proactive fills, and coordinate human-in-the-loop (HITL)
approvals.

### 88.1 Dual-LLM Architecture

```text
┌─────────────────────────────────────────────────────┐
│                   Concierge                         │
│                                                     │
│  ┌──────────┐         ┌──────────┐                  │
│  │  Front    │  ──→──  │  Back     │                │
│  │  (Voice)  │  topic  │  (Worker) │                │
│  │  10 tools │  route  │  6 tools  │                │
│  └──────────┘         └──────────┘                  │
│       │                    │                         │
│       │                    ├─── LOW: Back → Fabric   │
│       │                    ├─── MED: Orchestrator    │
│       │                    └─── HIGH: Planner → DAG  │
│       │                                              │
│  ┌──────────────────────────────────────────────┐   │
│  │  FSM Controller (12 states, FrontLock)       │   │
│  │  ExperienceLayer (6 components)              │   │
│  │  DeltaAggregator → DeltaApplicator           │   │
│  │  WeaveBatcher (500ms) + WeavePolicy          │   │
│  │  HILCoordinator (3 variants)                 │   │
│  │  OppPipeline (8 primitives, 9 hooks)         │   │
│  │  Ledger (event sourcing)                     │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

- **Front actor** ("voice"): Faces the user. Runs ReAct loop with 10 tool schemas.
  Produces streaming responses, affect updates, proactive fills.
- **Back actor** ("worker"): Handles dispatched tasks. Runs separate ReAct loop with
  6 tool schemas. Routes by complexity tier to Fabric, Orchestrator, or Planner.

### 88.2 Complexity Tiers

| Tier | Route | Budget | Latency Target | Example |
| ---- | ----- | ------ | -------------- | ------- |
| LOW | Front → Back → Fabric direct | 1 Fabric call, 0 planner tokens | < 2 s | "Turn on the lights" |
| MEDIUM | Front → OrchestratorStub (1–2 Fabric calls) | 2 Fabric calls, 0 planner tokens | 2–10 s | "Set a reminder for tomorrow" |
| HIGH | Front → PassthroughPlannerStub → reroute as MEDIUM (Phase 1) | 10 Fabric calls, 3500 planner tokens | 10–60 s | "Plan a trip to Paris" |

**Phase 1 HIGH tier behavior**: `route_task_sync()` wraps HIGH as a 1-step committed plan
via `PassthroughPlannerStub`, then re-routes as MEDIUM through `OrchestratorStub`.
Production HIGH tier (Epic 2+) will use the real Planner for multi-step DAG execution.

**Budget enforcement**: `OrchestratorStub._check_budget()` enforces max Fabric calls per
tier. Budget is frozen in `Budget(frozen=True)` dataclass, immutable after creation.

### 88.3 Eight Hexagonal Ports

| # | Port | Direction | Protocol | Purpose |
| - | ---- | --------- | -------- | ------- |
| 1 | IInputPort | Inbound | `receive() → UserMessage` | Receive user input |
| 2 | IOutputPort | Outbound | `send(OutputEvent) → DeliveryReceipt` | Stream responses to user |
| 3 | IClassificationPort | Outbound | `classify(text) → ClassificationResult` | Intent + tier classification |
| 4 | ILLMPort | Outbound | `execute(HubRequest) → HubResponse` / `stream_execute → AsyncIterator[HubChunk]` | LLM calls via Model Hub |
| 5 | IStatePort | Both | `read(sections[]) → Snapshot` / `write(section, op, data) → WriteResult` | SessionState read/write |
| 6 | IDispatchPort | Outbound | `dispatch_direct(CapReq) → CapResult` / `dispatch_envelope(TaskEnv) → void` | Fabric + Orchestrator dispatch |
| 7 | IDeltaPort | Both | `subscribe(topics[]) → DeltaStream` / `publish(event) → void` | Bus events + deltas |
| 8 | IMemoryPort | Outbound | `recall(query, selectors[]) → MemoryResult` | Memory recall for context |

### 88.4 Seven Circuit Breakers

| CB Name | Owner Adapter | Trip Condition | Degraded Behavior |
| ------- | ------------- | -------------- | ------------------ |
| CB_SSE | SSEOutputAdapter | 3 consecutive send failures | Buffer up to 5 messages, flush on reconnect |
| CB_MODEL | ModelGatewayAdapter | LLM timeout / 5xx | Canned response in DEGRADED mode |
| CB_SESSIONSTATE | SessionKernelAdapter | Read timeout | Return stale cached data |
| CB_ORCHESTRATOR | FabricOrchestratorAdapter | Orchestrator unresponsive | Tier degradation HIGH → MED → LOW |
| CB_PLANNER | FabricOrchestratorAdapter | Planner timeout | Fall back to MED tier |
| CB_FABRIC | FabricOrchestratorAdapter | Fabric capability failure | Mark capability unavailable |
| CB_MCP | FabricOrchestratorAdapter | MCP tool timeout | Mark tool unavailable |

---

## 89. Concierge Ports (8 total)

### 89.1 IInputPort

```python
@runtime_checkable
class IInputPort(Protocol):
    async def receive(self) -> UserMessage:
        """Block until next user message arrives."""
        ...
```

**Production adapter**: `WebSocketInputAdapter` / `RESTInputAdapter`
**Test adapter**: `TestInputAdapter` (inject messages programmatically)

### 89.2 IOutputPort

```python
@runtime_checkable
class IOutputPort(Protocol):
    async def send(self, event: OutputEvent) -> DeliveryReceipt:
        """Send response chunk/event to user. Returns delivery confirmation."""
        ...
```

**Production adapter**: `SSEOutputAdapter` / `WebSocketOutputAdapter`
**Test adapter**: `TestOutputAdapter` (capture + assert on messages)
**Circuit breaker**: CB_SSE (3 retries for REALTIME, 1 for PROGRESS, 0 for BACKGROUND)

### 89.3 IClassificationPort

```python
@runtime_checkable
class IClassificationPort(Protocol):
    async def classify(self, text: str) -> ClassificationResult:
        """Classify user intent and complexity tier (LOW/MEDIUM/HIGH)."""
        ...
```

**Production adapter**: `UltraBERTv4Adapter` (12 heads, 22ms)
**Test adapter**: `MockClassificationAdapter` (scripted results)
**Circuit breaker**: CB_MODEL (heuristic fallback when open)
**Heuristic fallback** (< 1ms): CRISIS keywords → hardcoded scan; question + < 20 words →
conversational/LOW; remind/schedule/set → task/MED; plan/help → planning/HIGH; default → LOW.

### 89.4 ILLMPort (IConciergeModelPort in Phase 1)

```python
@runtime_checkable
class ILLMPort(Protocol):
    async def execute(self, request: HubRequest) -> HubResponse:
        """Single-shot LLM call. Capabilities: CHAT, TOOL_CALL, STRUCTURED, VISION, REASON."""
        ...

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Streaming LLM call. Yields chunks as they arrive."""
        ...
```

**Phase 1 implementation**: `IConciergeModelPort` (`k1/concierge/llm/ports.py`)
  with methods `generate()` and `generate_stream()` wrapping Gemini directly.
**Production adapter**: `ModelGatewayAdapter` (routes via Model Hub LLM Request Bus)
**Test adapter**: `MockLLMAdapter` (scripted responses + tool calls)
**Circuit breaker**: CB_MODEL (L1: retry once, L2: half-open probe 30s, L3: canned response)

### 89.5 IStatePort

```python
@runtime_checkable
class IStatePort(Protocol):
    async def read(self, sections: list[str]) -> Snapshot:
        """Read one or more SessionState sections."""
        ...

    async def write(self, section: str, op: str, data: Any) -> WriteResult:
        """Write to a SessionState section with mutation guard."""
        ...
```

**Production adapter**: `SessionKernelAdapter` (wraps SessionStateManager, MutationGuard inside)
**Test adapter**: `InMemoryStateAdapter` (dict-based, tracks writes)
**Circuit breaker**: CB_SESSIONSTATE (read timeout → stale cache, emergency mode at ≥ 95KB)

**Phase 1 status**: Concierge directly holds `SessionStateManager` reference. The port
boundary does not yet exist; reads/writes go through `session_state.get_section()` and
section-specific methods.

### 89.6 IDispatchPort

```python
@runtime_checkable
class IDispatchPort(Protocol):
    async def dispatch_direct(self, request: CapabilityRequest) -> CapabilityResult:
        """Execute a single capability via Fabric (LOW tier)."""
        ...

    async def dispatch_envelope(self, envelope: TaskEnvelope) -> None:
        """Submit a task envelope to Orchestrator (MEDIUM/HIGH tier)."""
        ...
```

**Production adapter**: `FabricOrchestratorAdapter` (routes by tier)
**Test adapter**: `MockDispatchAdapter` (captures envelopes + requests)
**Circuit breakers**: CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP
**Tier degradation**: HIGH → MED → LOW → canned response

**Phase 1 status**: `OrchestratorStub` (`k1/concierge/orchestrator/stub.py`) implements
dispatch for LOW tier via `IFabricGatewayPort`. MEDIUM/HIGH stubs return mock results.

### 89.7 IDeltaPort

```python
@runtime_checkable
class IDeltaPort(Protocol):
    async def subscribe(self, topics: list[str]) -> DeltaStream:
        """Subscribe to bus topics for delta events."""
        ...

    async def publish(self, event: Any) -> None:
        """Publish a delta event to the bus."""
        ...

    async def errors(self) -> ErrorStream:
        """Get error stream for diagnostic routing."""
        ...
```

**Production adapter**: `DeltaBusAdapter` (subscription + error routing)
**Test adapter**: `TestDeltaAdapter` (emit test deltas on demand)
**Emit failure policy**: log + skip (RECOVERABLE, never TERMINAL — Edge-First best-effort)

**Phase 1 status**: `DeltaAggregator` + `DeltaApplicator` are directly wired. Bus
publish/subscribe is done through the `IBus` reference held by bootstrap.

### 89.8 IMemoryPort

```python
@runtime_checkable
class IMemoryPort(Protocol):
    async def recall(self, query: str, selectors: list[str]) -> MemoryResult:
        """Recall memories matching query and selector filters."""
        ...
```

**Production adapter**: `BridgeRecallAdapter` (QueryPort + offline fallback)
**Test adapter**: `MockMemoryAdapter` (canned recall results)
**Timeout policy**: skip memory (RECOVERABLE, never TERMINAL — respond without memory)

**Phase 1 status**: `recall_fn` callback built by `_build_recall_fn()` in bootstrap.
Returns empty results when no memory backend is configured.

---

## 90. Concierge Adapters (8 production + 8 test)

| Port | Production Adapter | Test Adapter |
| ---- | ------------------ | ------------ |
| IInputPort | WebSocketInputAdapter, RESTInputAdapter | TestInputAdapter |
| IOutputPort | SSEOutputAdapter, WebSocketOutputAdapter | TestOutputAdapter |
| IClassificationPort | UltraBERTv4Adapter | MockClassificationAdapter |
| ILLMPort | ModelGatewayAdapter | MockLLMAdapter |
| IStatePort | SessionKernelAdapter | InMemoryStateAdapter |
| IDispatchPort | FabricOrchestratorAdapter | MockDispatchAdapter |
| IDeltaPort | DeltaBusAdapter | TestDeltaAdapter |
| IMemoryPort | BridgeRecallAdapter | MockMemoryAdapter |

**Phase 1 note**: Production adapters are not yet implemented. The POC uses direct
references to internal objects (model, session_state, bus, fabric_instance). Production
adapters will be created during Epic 1 (Hexagonal Boundary) of the Concierge roadmap.

---

## 91. Concierge FSM Controller

The `ConciergeController` is the central state machine governing all concierge behavior.

### 91.1 Twelve States

| State | Description | Entry Condition |
| ----- | ----------- | --------------- |
| LISTENING | Idle, awaiting user input | Initial state / after response delivered |
| ACKING | Acknowledged input, classifying | User message received |
| DISPATCHING | Routing to correct tier handler | Classification complete |
| COMPANIONING | Generating conversational (LOW) response | LOW tier dispatch |
| PROGRESSING | Reporting progress on multi-step task | MEDIUM/HIGH tier in progress |
| DELIVERING | Streaming final response to user | Response ready |
| CLARIFYING_USER | Asking user for clarification | Ambiguous input detected |
| CLARIFYING_WORKER | Asking back worker for details | Back needs more context |
| CANCELLING | Handling user cancellation request | User says "cancel" / "stop" |
| INTERRUPT_HANDLING | Processing user interrupt mid-task | New input while task running |
| PROACTIVE_WAKE | Sending proactive notification | Timer/event-triggered fill |
| WEAVING | Batching multiple background results | WeaveBatcher flush triggers delivery |

### 91.2 FrontLock

The FSM enforces a `FrontLock` to ensure only one Front actor turn executes at a time.
This prevents concurrent LLM calls from producing interleaved streaming output.

```text
FrontLock rules:
- acquire() before any Front ReAct loop iteration
- release() after response fully streamed or tool call completed
- Interrupt: new user message while locked → INTERRUPT_HANDLING state
- WeaveBatcher: queues results until FrontLock released → WEAVING state
```

### 91.3 Phase 1 Pipeline (UltraBERT)

When `config.phase1.pipeline == "ultrabert"`, the FSM uses `UltraBERTPhase1Pipeline`
for fast intent classification at the ACKING → DISPATCHING transition:

```text
K1UltraBERTAdapter.classify(text) → ClassificationResult
  ├── Available: 12-head model, ~22ms latency
  └── Unavailable: Heuristic fallback (<1ms, keyword-based)
```

---

## 92. Concierge Actors (Front + Back)

### 92.1 Front Actor

**File**: `k1/concierge/actors/front.py`
**Function**: `front_handler(envelope, model, ss, bus, tool_dispatcher, all_tool_schemas, fsm_state)`

The Front actor is the user-facing conversational agent:

1. Receives user message envelope from front mailbox
2. Builds prompt from SessionState sections (history, affective_now, scoreboard, etc.)
3. Runs ReAct loop: LLM call → tool calls → LLM call → ... → final response
4. Emits response via bus (`concierge.response.*` topics)
5. Triggers ExperienceLayer tick for affect updates

**10 Front tool schemas** (from `schemas_front.py`): conversation, memory recall,
session read, classification, affect update, proactive scheduling, weave control,
HITL initiation, context switching, and metacognitive reflection.

### 92.2 Back Actor + Back Router

**File**: `k1/concierge/actors/back.py` (topic router: `back_router.py`)
**Function**: `route_back_envelope(envelope, model, ss, bus, tool_dispatcher, fsm_state)`

The Back actor handles dispatched work via a topic-based router:

**Back Router topic routing table** (M7 E7.3):

| Topic | Handler | Async? | Notes |
| ----- | ------- | ------ | ----- |
| `task.dispatch.v1` | `back_handler` | Yes (pool worker) | Main task execution |
| `task.resume.v1` | `back_resume_handler` | Yes (pool worker) | Resume after HITL response |
| `task.cancel.v1` | `back_cancel_handler` | **No (sync)** | Immediate, bypasses pool |
| `clarification.response.v1` | `back_resume_handler` | Yes (pool worker) | Resume after clarification |

**Cancel bypass**: Cancel envelopes are dispatched synchronously (no pool worker needed)
for immediate termination. `CancellationToken` is extracted from `TaskLease` and injected
into the handler. Back checks `token.check()` at tool boundaries (cooperative cancellation).

**Late-envelope discard** (E7.3.4): If the task's `TaskLease` status is already
`RELEASED` or `CANCELLED`, the envelope is discarded silently.

**6 Back tool schemas** (from `schemas_back.py`): fabric execute, orchestrator dispatch,
planner request, state write, delta publish, and result packaging.

**Max iterations by tier** (from config):

- LOW: 10 iterations
- MEDIUM: 14 iterations
- HIGH: 24 iterations
- Budget floor: 4 iterations (minimum regardless of tier)

**GOTCHA**: Back actor subscriptions are NOT wired directly to bus. The FSM is the sole
routing authority — it delivers to back via `_route_via_orchestrator → _deliver_to_back`.
Direct subscription would cause duplicate deliveries.

---

## 93. Concierge ReAct Loop

**File**: `k1/concierge/react/loop.py`

Both Front and Back actors use a shared ReAct (Reason + Act) loop implementation.

### 93.1 Loop Steps

```text
1. Build prompt (system + history + tools + user message)
2. LLM call (generate or generate_stream)
3. Parse response:
   a. If tool_call → validate schema → execute tool → append result → goto 2
   b. If text response → emit to bus → done
   c. If max iterations reached → emit partial response → done
4. Tool execution:
   a. Validate against ToolDispatcher (tier + safety + state checks)
   b. Execute tool function
   c. Append tool result to conversation history
   d. Return to step 2
```

### 93.2 Tool Dispatch

**File**: `k1/concierge/tools/dispatcher.py`

```python
create_front_dispatcher(tier: str, ctx: ToolContext, bus: IBus) -> ToolDispatcher
create_back_dispatcher(tier: str, ctx: ToolContext, bus: IBus) -> ToolDispatcher
```

Each dispatcher filters available tools by:

- **Tier**: LOW exposes basic tools, MEDIUM adds orchestrator tools, HIGH adds planner tools
- **Safety**: MutationGuard checks prevent dangerous state writes
- **State**: FSM state determines which tools are allowed (e.g., no dispatch during CANCELLING)

### 93.3 ToolContext

```python
@dataclass
class ToolContext:
    session_manager: Any           # SessionStateManager reference
    cognitive_trace_id: str        # Trace correlation ID
    actor: str                     # "front" or "back"
    recall_fn: Callable | None     # Memory recall function
    fabric_port: Any               # Fabric instance for capability execution
    writer_port: Any               # SessionState writer port for mutations
```

---

## 94. Concierge Internal Components

### 94.1 DeltaAggregator

**File**: `k1/concierge/delta/aggregator.py`

Batches delta events before flushing to the DeltaApplicator. Reduces bus chatter
by coalescing multiple small updates into a single batch.

```text
Config: batch_window_ms (from config.delta.batch_window_ms)
Flow:  event → buffer → timer expires → flush_fn(batch) → DeltaApplicator.apply()
```

### 94.2 DeltaApplicator

**File**: `k1/concierge/delta/applicator.py`

Applies batched deltas to SessionState sections. Built by `_build_delta_applicator()`
in bootstrap.

### 94.3 ExperienceLayer (6 Components)

**File**: `k1/concierge/experience/layer.py`

The ExperienceLayer provides emotional intelligence and conversational quality:

| Component | File | Purpose |
| --------- | ---- | ------- |
| ExperienceLayer | `layer.py` | Orchestrator for all experience components |
| EmotionalProcessor | `emotional_processor.py` | Process user emotion signals |
| AffectiveMirror | `affective_mirror.py` | Mirror appropriate emotional responses |
| RhythmController | `rhythm_controller.py` | Control response pacing and style |
| ProactiveAgent | `proactive_agent.py` | Generate proactive notifications |
| ToneGenerator | (internal to ExperienceLayer) | Generate tone adjustments |

**Tick cycle**: After each Front actor response, `ExperienceLayer.tick(fsm_state, context)`
is called. Returns `{emotional, tone, fill}` outputs that are routed to bus topics
and SessionState sections.

### 94.4 HILCoordinator (3 Variants + Safety Bands + Trust Integration)

**File**: `k1/concierge/protocols/hitl_coordinator.py`

Manages human-in-the-loop approvals with three variants:

| Variant | Trigger | User Sees |
| ------- | ------- | --------- |
| Clarification | Ambiguous input | "Did you mean X or Y?" |
| Confirmation | Destructive/expensive action | "This will cost $50. Proceed?" |
| Override | System suggests, user decides | "I recommend A. You can choose B." |

**`handle_needs_human()` signature** (V2 Section 9.1):

```python
async def handle_needs_human(
    self,
    task_id: str,
    hil_type: str,           # clarification | approval | selection
    question: str,
    options: list[dict] | None = None,
    side_effects: list[str] | None = None,
    context: dict | None = None,
    safety_band: SafetyBand | str = SafetyBand.GREEN,
    react_history: list[dict] | None = None,
    ledger: Any = None,
) -> HILRequest
```

**Internal steps**:

1. Safety band escalation: `GREEN + side_effects → AMBER`
2. RED band check: Block if `config.block_red=True`
3. Suspension limits: Check `max_rounds` (default 2)
4. Build `HILRequest` with type-specific timeout
5. Persist to `_pending_requests[task_id]`
6. Delegate to `SuspensionManager` for timeout tracking
7. Write-before-mutate: Emit `HILRequested` to ledger
8. Callback: `on_emit_suspended()` → bus emission

**Safety band escalation** (V2 Section 9.3):

| Input Band | Side Effects? | Result Band |
| ---------- | ------------- | ----------- |
| GREEN | No | GREEN (safe, no HITL needed) |
| GREEN | Yes | AMBER (escalate, requires approval) |
| AMBER | Any | AMBER (requires approval) |
| RED | Any | RED (blocked if config.block_red) |

**Callbacks** (injected by bootstrap):

- `on_emit_suspended(request)` → publishes `task.suspended` envelope
- `on_emit_resume(response)` → publishes `task.resume` envelope
- `on_timeout(task_id)` → publishes `task.failed` envelope with `HITL_TIMEOUT`

**HIL Pipeline** (`k1/concierge/protocols/hitl_pipeline.py`):

```python
detect_approval_required(capability_contract) -> bool
    # True if: has_side_effects OR safety_band >= AMBER

process_approval_response(response, original_params) -> ApprovalResult
    # Decisions:
    #   approve           → execute with original params
    #   approve + mods    → execute with merged params (mods applied BEFORE execution)
    #   modify + mods     → re-present for approval
    #   cancel            → do NOT execute
```

### 94.5 WeaveBatcher (500ms Window + Overflow Eviction)

**File**: `k1/concierge/protocols/weave_batcher.py`

Queues background task results when the Front actor is busy (FrontLock held).
Flushes after a configurable window (default 500ms) to deliver batched results
as a single coherent response instead of interleaved fragments.

**`on_task_complete()` logic**:

```text
If Front busy (FrontLock held):
  → Queue result in _queued[]
  → If overflow (len >= max_queued_depth): evict oldest (FIFO, dead-letter)
Otherwise:
  → Add to _pending[] batch
  → Start 500ms timer if not running → flush_fn(batch) on expiry
```

**WeaveResult**:

```python
@dataclass
class WeaveResult:
    task_id: str
    task_description: str
    result_data: dict[str, Any]
    completed_at_ns: int

    def to_prompt_block(self) -> str:
        """Format as [ASYNC RESULT ARRIVED] injection for Front prompt."""
```

### 94.6 WeavePolicy + UserActivityTracker (6-Signal Decision Engine)

**File**: `k1/concierge/protocols/weave_policy.py`

Adaptive delivery strategy based on 6 signal categories:

| # | Signal Category | Source | Examples |
| - | --------------- | ------ | -------- |
| 1 | FSM state | ConciergeController | COMPANIONING, LISTENING, WEAVING |
| 2 | Urgency profile | Pending results | urgency counts, has_critical flag |
| 3 | User activity | UserActivityTracker | is_typing, idle_ms |
| 4 | Queue depth | WeaveBatcher | pending_count |
| 5 | Affect band | ExperienceLayer | valence, emotional_gate |
| 6 | Pool + HITL | BackPool, HILCoordinator | backpool_utilization, hitl_pending |

**WeaveDecision enum**:

| Decision | Behavior | When |
| -------- | -------- | ---- |
| IMMEDIATE | Deliver now | Critical result, user idle > threshold |
| BATCH | Dynamic window (200–5000ms) | Multiple results arriving, user not typing |
| DEFER | Hold until next user input | User actively typing |
| DIGEST | Accumulate 10–30s, synthesize | Many low-priority results |
| SUPPRESS | Do not deliver | Emotional gate SUPPRESS_ALL_NON_SAFETY |

**Emotional gate thresholds**:

```text
OPEN                    ← valence >= 0 (deliver normally)
SUPPRESS_TRIVIAL        ← valence < -0.5 (skip low-priority)
SUPPRESS_ALL_NON_SAFETY ← crisis | RED band (only safety-critical)
```

**UserActivityTracker** (E8.1.2–E8.1.3):

```python
class UserActivityTracker:
    def on_typing_start(self) -> None
    def on_typing_stop(self) -> None
    def on_user_input(self) -> None

    @property
    def is_typing(self) -> bool
    @property
    def idle_ms(self) -> int
```

**Pacing strategy** (OPP-1):

| Strategy | Behavior |
| -------- | -------- |
| NONE | No pacing, deliver as-is |
| STAGGER | Inter-result delay |
| GROUP_BY_DOMAIN | Group related results together |
| PRIORITY_CASCADE | High-priority first, then others |

### 94.7 OPP Pipeline (8 Primitives wired to FSM Lifecycle Hooks)

**File**: `k1/concierge/protocols/opp_pipeline.py`

Output Post-Processing pipeline wires 8 OPP primitives into FSM lifecycle hooks:

| OPP | Primitive | Hook | Returns |
| --- | --------- | ---- | ------- |
| OPP-1 | Paced Delivery | `on_weave_flush()` | `PacingResult` (strategy + group delays) |
| OPP-2 | Recency Bias Decay | `on_classify()` | `ClassifyEnrichment` (recency decay flag) |
| OPP-3 | Affect Hard Caps | `on_pre_llm_call()` | `LlmParamOverrides` (token caps, vocab tier, tool budget) |
| OPP-4 | Trust Accumulator | `on_hitl_outcome()`, `on_pre_invoke()` | `TrustGate` (auto_approved, dynamic_max_rounds) |
| OPP-5 | Proactive Scheduler | `on_idle_tick()` | `ProactiveTriggerResult` (should_trigger, trigger_type) |
| OPP-6 | Episodic Compression | `on_pre_prompt_build()` | `PromptEnrichment` (compressed context) |
| OPP-7 | Dynamic Identity | `on_pre_prompt_build()` | `PromptEnrichment` (identity block) |
| OPP-8 | Natural Flow Delivery | `on_task_complete()` | `DeliveryDecision` (delivery_mode, prompt_mode_hint) |

**Hook result dataclasses**:

```python
ClassifyEnrichment    # recency_decay_applied: bool
PromptEnrichment      # compressed_context: str, identity_block: str
LlmParamOverrides     # max_tokens: int, vocabulary_tier: str, tool_budget: int
DeliveryDecision      # delivery_mode: DeliveryMode, prompt_mode_hint: str
TrustGate             # auto_approved: bool, dynamic_max_rounds: int
ProactiveTriggerResult # should_trigger: bool, trigger_type: str
PacingResult          # strategy: PacingStrategy, groups: list, inter_group_delay_ms: list
```

### 94.8 MutationGuard (3-Tier)

Embedded in SessionKernelAdapter, prevents dangerous state mutations:

| Tier | Policy | Example |
| ---- | ------ | ------- |
| ALLOW | Write proceeds | Updating conversation history |
| WARN | Write proceeds + log warning | Modifying user preferences |
| BLOCK | Write rejected (RECOVERABLE) | Deleting critical sections |

### 94.9 Ledger (Event Sourcing)

**File**: `k1/concierge/ledger/writer.py`

Optional event sourcing for audit trail. `LedgerWriter` records all FSM transitions,
tool calls, and LLM interactions into an `InMemoryLedgerStore` (Phase 1).

---

## 95. Concierge Bootstrap (Phase 1 Monolith)

**File**: `k1/concierge/kernel/bootstrap.py`

Phase 1 uses a monolith bootstrap that creates all dependencies internally.
Future phases will replace this with `ConciergeFactory` receiving ports from
the kernel bootstrap.

### 95.1 KernelConfig Fields

| Field | Type | Default | Purpose |
| ----- | ---- | ------- | ------- |
| ordered_bus | bool | True | Use ordered bus delivery |
| capture_bus | bool | False | Enable bus message capture for testing |
| test_mode | bool | False | Enable test mode |
| tool_tier | str | "LOW" | Tool tier (LOW / MEDIUM / HIGH) |
| session_mode | str | "standalone" | standalone / testing |
| session_id | str \| None | None | Explicit session ID (auto-generated if None) |
| enable_experience | bool | True | Enable ExperienceLayer |
| enable_delta | bool | True | Enable DeltaAggregator + DeltaApplicator |
| enable_hitl | bool | True | Enable HILCoordinator |
| enable_orchestrator | bool | True | Enable OrchestratorStub |
| auto_start_consumer | bool | True | Auto-start mailbox consumer task |
| enable_ledger | bool | True | Enable LedgerWriter |
| enable_dead_letter_consumer | bool | True | Enable DeadLetterConsumer |
| seed_memories | list[dict] | [] | Seed memories for testing |

### 95.2 start_kernel() Wiring Order (Phase 1)

```text
Step 1:   boot() → {bus, router, adapter, front_mailbox, back_mailbox}
Step 2:   _create_model(cfg) → IConciergeModelPort (Gemini adapter)
Step 3:   _create_session_state(cfg) → SessionStateManager
Step 4:   _create_capability_registry() → CapabilityRegistry
Step 5:   _create_fabric(capability_registry) → Fabric (M6: real K1 Fabric via FabricFactory)
Step 6:   Create LedgerWriter + InMemoryLedgerStore (if enable_ledger)
Step 7:   ConciergeController(bus, router) → FSM
Step 8:   Wire Phase 1 pipeline (UltraBERT if configured)
Step 9:   Wire ledger into FSM (set_ledger)
Step 10:  Wire history_active section into FSM (set_history_sink)
Step 11:  Wire SessionStateManager into FSM (set_session_state)
Step 12:  Build ToolContext (front + back) with recall_fn, fabric_port, writer_port
Step 13:  Create ToolDispatchers (front + back) via create_*_dispatcher()
Step 14:  Build KernelRuntime dataclass
Step 15:  Wire ExperienceLayer (if enable_experience)
Step 16:  Wire DeltaAggregator + DeltaApplicator (if enable_delta)
Step 17:  Wire HILCoordinator with 3 callbacks (if enable_hitl)
Step 18:  Wire WeaveBatcher + WeavePolicy + UserActivityTracker
Step 19:  Wire DeadLetterConsumer (if enable_dead_letter_consumer + config.fsm.dead_letter_enabled)
Step 20:  Wire OrchestratorStub with FabricGateway/StateRead/DeltaEmit adapters (if enable_orchestrator)
Step 21:  Subscribe front events via subscribe_front_events(bus, route_fn)
Step 22:  Start mailbox consumer task (if auto_start_consumer)
```

### 95.3 stop_kernel() Teardown Order

```text
Step 1:   Cancel consumer_task
Step 2:   Flush ledger + log entry count
Step 3:   Log dead-letter summary
Step 4:   Flush DeltaAggregator
Step 5:   FSM teardown
Step 6:   Close SessionStateManager
Step 7:   Close model
Step 8:   Set started = False
```

### 95.4 KernelRuntime Dataclass

The `KernelRuntime` holds all live references for the running concierge:

```python
@dataclass
class KernelRuntime:
    config: KernelConfig
    bus: IBus
    router: IMailboxRouter
    adapter: Any
    front_mailbox: IMailbox
    back_mailbox: IMailbox
    session_state: Any
    capability_registry: Any
    model: Any
    fsm: ConciergeController
    front_dispatcher: Any
    back_dispatcher: Any
    experience_layer: Any = None
    delta_aggregator: Any = None
    delta_applicator: Any = None
    hitl_coordinator: Any = None
    orchestrator: Any = None
    front_subscriptions: list[Any] = field(default_factory=list)
    back_subscriptions: list[Any] = field(default_factory=list)
    consumer_task: asyncio.Task | None = None
    ledger: Any = None
    ledger_store: Any = None
    dead_letter_consumer: Any = None
    started: bool = False
```

---

## 96. Concierge Mailbox Consumer

**File**: `k1/concierge/kernel/bootstrap.py` (`_mailbox_consumer`)

The mailbox consumer is an async task that polls front and back mailboxes:

```text
Loop:
  1. front_mailbox.receive(timeout_ms=0) → front_env
  2. Dedup check (seen_front_ids, bounded set, cleared at dedup_cache_size)
  3. If front_env: await front_handler(...) → await _tick_experience(runtime)
  4. back_mailbox.receive(timeout_ms=0) → back_env
  5. Dedup check (seen_back_ids)
  6. If back_env: await route_back_envelope(...)
  7. If did_work: yield (sleep 0)  else: sleep poll_interval
```

**Config**: `kernel.poll_interval_s`, `kernel.dedup_cache_size`

---

## 97. Concierge Session Data

The Concierge reads and writes the following SessionState sections.
See §46 for the canonical 12-section data model.

**Family context note (D-14, D-15):** Family member identity, allergies, access
levels, and device registry are NOT SessionState sections. They live in the
`HouseholdProjection` — hydrated at boot from K0 via Bridge (Phase 6.5),
cached in-memory, and kept current via `household.delta.v1` SSE subscription.
See §126 for the hydration protocol.

### 97.1 HOT Tier (~52KB)

| Section | Access | Purpose |
| ------- | ------ | ------- |
| history_active | Read + Write | Recent conversation turns (Front context window) |
| affective_now | Read + Write | Current emotional state, tone, response style |
| scoreboard | Read | Active task status and progress |
| narrative_active | Read | Long-running family narrative context |
| control | Read | Mode, turn counter, focus agent, capabilities |
| beliefs_active | Read + Write | Active belief facts with confidence scores |
| clarifications | Read + Write | Pending clarification questions |
| meta | Read | Schema version, session metadata |

### 97.2 WARM Tier (~48KB)

| Section | Access | Purpose |
| ------- | ------ | ------- |
| telemetry | Read | Performance metrics, error counts |
| beliefs_history | Read | Archived beliefs demoted from HOT |
| history_recent | Read | Summarized conversation history |
| persona | Read | Stable personality traits, vocabulary |

### 97.3 Prompt Modes (10 total)

The Front actor selects from 10 prompt modes based on FSM state and classification:
conversational, task_dispatch, progress_report, clarification, confirmation, override,
cancellation, interrupt, proactive, and weave_delivery.

---

## 98. Concierge Event Reference

### 98.1 Published Topics

| Topic | Publisher | Payload Summary |
| ----- | --------- | --------------- |
| concierge.session.started.v1 | bootstrap | session_id, timestamp |
| concierge.session.ended.v1 | bootstrap | session_id, duration, turn_count |
| concierge.response.text.v1 | Front actor | text, turn_id, latency_ms |
| concierge.response.stream_chunk.v1 | Front actor | chunk, sequence, turn_id |
| concierge.response.tool_result.v1 | Front/Back actor | tool_name, result, duration_ms |
| concierge.orchestration.dispatched.v1 | FSM | task_id, tier, envelope |
| concierge.orchestration.completed.v1 | Back actor | task_id, tier, result |
| concierge.orchestration.failed.v1 | Back actor | task_id, error_code, reason |
| concierge.affect.updated.v1 | ExperienceLayer | emotional state, tone |
| concierge.affect.tone_shift.v1 | RhythmController | old_tone, new_tone, trigger |
| concierge.proactive.scheduled.v1 | ProactiveAgent | fill_id, trigger, delay_ms |
| concierge.proactive.delivered.v1 | Front actor | fill_id, text |
| concierge.proactive.suppressed.v1 | WeavePolicy | fill_id, reason |
| concierge.weave.queued.v1 | WeaveBatcher | batch_id, item_count |
| concierge.weave.flushed.v1 | WeaveBatcher | batch_id, item_count, latency_ms |
| concierge.hitl.suspended.v1 | HILCoordinator | task_id, hil_type, question |
| concierge.hitl.resumed.v1 | HILCoordinator | task_id, decision, answer |
| concierge.hitl.timeout.v1 | HILCoordinator | task_id, timeout_ms |
| concierge.tool.invoked.v1 | ToolDispatcher | tool_name, actor, tier |
| concierge.tool.completed.v1 | ToolDispatcher | tool_name, duration_ms, success |
| concierge.turn.started.v1 | Front actor | turn_id, user_message_preview |
| concierge.turn.completed.v1 | Front actor | turn_id, response_length, tool_count |
| concierge.turn.error.v1 | Front actor | turn_id, error_code, fallback_used |

### 98.2 Subscribed Topics

| Topic | Handler | Purpose |
| ----- | ------- | ------- |
| k1.orchestrator.task.completed.v1 | FSM routing | Task completion from Orchestrator |
| k1.orchestrator.task.failed.v1 | FSM routing | Task failure from Orchestrator |
| k1.orchestrator.task.progress.v1 | FSM routing | Progress updates for PROGRESSING state |
| k1.planner.plan.ready.v1 | FSM routing | Plan ready for HIGH tier execution |
| k1.hil.override_response.v1 | HILCoordinator | User override decision |
| k1.hil.fallback_response.v1 | HILCoordinator | User fallback selection |
| k1.fabric.provider.health.changed.v1 | Capability registry | Provider health for tier degradation |
| k1.sessionstate.eviction.v1 | DeltaApplicator | Section eviction notification |

---

## 99. Concierge Concurrency Model

### 99.1 FrontLock Semantics

```text
- Single async lock per Concierge instance
- Acquired: before Front ReAct loop iteration
- Released: after response delivery or tool call completion
- Interrupt detection: new user message while lock held → INTERRUPT_HANDLING
- Weave queuing: background results while lock held → buffer in WeaveBatcher
```

### 99.2 Mailbox Isolation

```text
- Front mailbox: user-originated messages only
- Back mailbox: FSM-routed task dispatches only
- No cross-posting between mailboxes
- Back does NOT subscribe directly to bus topics (FSM routes)
```

### 99.3 Async Task Inventory

| Task | Created By | Lifecycle |
| ---- | ---------- | --------- |
| consumer_task | start_kernel() | Lives until stop_kernel() |
| WeaveBatcher timer | WeaveBatcher | Per-batch, auto-cancels on flush |
| HITL timeout timer | HILCoordinator | Per-request, auto-cancels on response |
| ExperienceLayer tick | _tick_experience() | Per-turn, completes synchronously |
| DeltaAggregator flush | DeltaAggregator | Timer-based, batch_window_ms |

---

## 100. Concierge Shutdown Sequence

```text
Step 1:  Cancel consumer_task (stops mailbox polling)
Step 2:  Flush LedgerWriter (persist event trail)
Step 3:  Log DeadLetterConsumer summary
Step 4:  Flush DeltaAggregator (apply pending deltas)
Step 5:  FSM teardown (release FrontLock, cancel timers)
Step 6:  Close SessionStateManager (flush dirty sections)
Step 7:  Close model (release LLM connections)
Step 8:  Set runtime.started = False
```

**Order rationale**: Consumer stops first (no new work), then internal components
flush in dependency order (ledger → delta → FSM → state → model). Model closes
last because FSM teardown may need to emit a final response.

---

## 101. Concierge Bootstrap Gotchas

1. **Back subscriptions are intentionally empty** — `runtime.back_subscriptions = []`.
   The FSM is the sole routing authority for back-bound topics. Subscribing back directly
   to bus topics causes duplicate deliveries (learned during M3 E3.1.3).

2. **Phase 1 pipeline fallback** — If `familyos_ultrabert` package is unavailable, the
   FSM falls back to STUB classification. The heuristic fallback only activates when
   UltraBERT adapter reports `is_available() == False` at boot.

3. **LedgerWriter has no async flush** — `InMemoryLedgerStore` is synchronous. The
   `stop_kernel()` shutdown guard handles this safely.

4. **DeadLetterConsumer requires config flag** — Both `enable_dead_letter_consumer=True`
   in KernelConfig AND `config.fsm.dead_letter_enabled=True` in YAML config must be
   set for the consumer to be created.

5. **Fabric is real since M6** — `_create_fabric()` now creates a real K1 Fabric instance
   via `FabricFactory` with `POCMockBridgeAdapter`. This is NOT a stub.

6. **OrchestratorStub internal adapters** — `_FabricGatewayAdapter`, `_StateReadAdapter`,
   `_DeltaEmitAdapter` are private adapter classes defined at module level in bootstrap.py.
   They will be replaced by kernel-level port injection in Epic 1.

7. **Experience tick is synchronous** — `_tick_experience()` is awaited inline after every
   Front handler call. If ExperienceLayer becomes expensive, consider making it async with
   a dedicated task.

---

## 102. Concierge File Locations Reference

| What | Path |
| ---- | ---- |
| Architecture spec | `k1/concierge/concierge.mmd` |
| POC architecture ref | `poc/k1_poc/concierge_poc_architecture.mmd` |
| Bootstrap (Phase 1) | `k1/concierge/kernel/bootstrap.py` |
| Kernel runner | `k1/concierge/kernel/runner.py` |
| Config (shimmed) | `k1/concierge/config/` |
| FSM controller | `k1/concierge/fsm/controller.py` |
| FSM states | `k1/concierge/fsm/states.py` |
| FSM transition table | `k1/concierge/fsm/transition_table.py` |
| FSM FrontLock | `k1/concierge/fsm/front_lock.py` |
| FSM dead letter | `k1/concierge/fsm/dead_letter_consumer.py` |
| UltraBERT adapter | `k1/concierge/fsm/ultrabert_adapter.py` |
| UltraBERT Phase 1 | `k1/concierge/fsm/ultrabert_phase1.py` |
| Front actor | `k1/concierge/actors/front.py` |
| Back actor | `k1/concierge/actors/back.py` |
| Back router | `k1/concierge/actors/back_router.py` |
| ReAct loop | `k1/concierge/react/loop.py` |
| Tool implementations | `k1/concierge/tools/implementations.py` |
| Tool dispatcher | `k1/concierge/tools/dispatcher.py` |
| Front tool schemas | `k1/concierge/tools/schemas_front.py` |
| Back tool schemas | `k1/concierge/tools/schemas_back.py` |
| LLM port (Phase 1) | `k1/concierge/llm/ports.py` |
| LLM types | `k1/concierge/llm/types.py` |
| LLM bridge (POC) | `k1/concierge/llm/model_hub_bridge.py` |
| LLM adapter (Gemini) | `k1/concierge/llm/gemini_adapter.py` |
| LLM validator | `k1/concierge/llm/validator.py` |
| Orchestrator stub | `k1/concierge/orchestrator/stub.py` |
| Orchestrator ports | `k1/concierge/orchestrator/ports.py` |
| Orchestrator types | `k1/concierge/orchestrator/types.py` |
| Orchestrator routing | `k1/concierge/orchestrator/routing.py` |
| DeltaAggregator | `k1/concierge/delta/aggregator.py` |
| DeltaApplicator | `k1/concierge/delta/applicator.py` |
| ExperienceLayer | `k1/concierge/experience/layer.py` |
| EmotionalProcessor | `k1/concierge/experience/emotional_processor.py` |
| AffectiveMirror | `k1/concierge/experience/affective_mirror.py` |
| RhythmController | `k1/concierge/experience/rhythm_controller.py` |
| ProactiveAgent | `k1/concierge/experience/proactive_agent.py` |
| HILCoordinator | `k1/concierge/protocols/hitl_coordinator.py` |
| HITL pipeline | `k1/concierge/protocols/hitl_pipeline.py` |
| TrustAccumulator | `k1/concierge/protocols/trust_accumulator.py` |
| WeaveBatcher | `k1/concierge/protocols/weave_batcher.py` |
| WeavePolicy | `k1/concierge/protocols/weave_policy.py` |
| OppPipeline | `k1/concierge/protocols/opp_pipeline.py` |
| DeliveryStrategy | `k1/concierge/protocols/delivery_strategy.py` |
| Cancellation | `k1/concierge/protocols/cancellation.py` |
| Fabric contract converter | `k1/concierge/fabric/contract_converter.py` |
| POC bridge adapter | `k1/concierge/fabric/poc_bridge_adapter.py` |
| Capability registry | `k1/concierge/fabric/capability_registry.py` |
| Ledger writer | `k1/concierge/ledger/writer.py` |
| Bus builders | `k1/concierge/bus/builders.py` |

---

## 103. Concierge Delivery Strategy

**File**: `k1/concierge/protocols/delivery_strategy.py`

Determines HOW to present results to the user based on WHAT arrived and WHERE
the conversation is.

### 103.1 Result Classification (WHAT arrived)

| Classification | Meaning | Example |
| -------------- | ------- | ------- |
| AWAITED | User explicitly asked for this (in active dispatch) | "Book that hotel" → booking confirmation |
| FOLLOW_UP | Chained/dependent task from user's initiated sequence | Calendar event after hotel booking |
| BACKGROUND | Speculative or low-priority task | Proactive weather check |
| TIME_SENSITIVE | Urgent task with deadline | Reminder about to expire |
| INFORMATIONAL | Status update / FYI | "Your booking was confirmed" |

### 103.2 Delivery Modes (HOW to present)

| Mode | Prompt Mode | Behavior |
| ---- | ----------- | -------- |
| DIRECT_PRESENT | PRESENT | Result is focus, user was waiting |
| CONVERSATIONAL_WEAVE | WEAVE | Weave into ongoing conversation |
| CONTEXTUAL_INJECT | STANDARD + silent async_context | Don't present explicitly, available in context |
| BRIEF_NOTIFY | PRESENT + brief flag | One-liner confirmation |
| DEFERRED_QUEUE | None (no LLM call) | Store for later presentation |

### 103.3 Conversation Flow Signals

```python
@dataclass
class ConversationFlowSignal:
    topic_match_score: float        # 0.0-1.0: how related is result to current topic
    conversation_depth: int         # Consecutive turns on same topic
    is_natural_pause: bool          # Topic shift, lull, or explicit "what else?"
    user_awaiting_result: bool      # From last user message pattern
    turns_since_dispatch: int       # Delivery freshness
```

The delivery strategy combines result classification, conversation flow signals,
and WeavePolicy decisions to select the optimal delivery mode.

---

## 104. Concierge Cancellation Protocol

**File**: `k1/concierge/protocols/cancellation.py`

### 104.1 Cooperative Cancellation (Not Preemptive)

The Back actor uses cooperative cancellation — it checks a `CancellationToken` at
tool boundaries rather than being forcibly killed:

```text
1. User says "cancel that" or "stop"
2. FSM → CANCELLING state
3. CancellationToken.cancel(reason) called
4. Back checks token.check() between tool invocations
5. If is_cancelled=True: raise TaskCancelledError
6. Back aborts ReAct loop → emits task.failed
7. FSM → LISTENING
```

### 104.2 Cancel Reasons

| Reason | Trigger | Behavior |
| ------ | ------- | -------- |
| USER_REQUESTED | User said "cancel" / "stop" | Immediate token cancellation |
| TIMEOUT | Task exceeded time budget | Timer-triggered cancellation |
| SUPERSEDED | New task replaces current | Old task cancelled, new task dispatched |

### 104.3 Race Condition Handling

If task completes before cancel is checked, `completed_before_cancel=True`. The FSM
deduplicates: shows "it went through" to the user instead of "cancelled".

### 104.4 Cancel in Back Router

Cancel envelopes (`task.cancel.v1`) bypass the pool worker and are dispatched
**synchronously** for immediate termination. This is the only sync handler in
the back router — all other topics use async pool workers.

---

## 105. Concierge Trust Accumulator (OPP-4)

**File**: `k1/concierge/protocols/trust_accumulator.py`

Reduces HITL interruptions over time based on interaction outcomes. As the system
builds trust with the user, low-risk actions can be auto-approved.

### 105.1 Trust Config

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| initial_trust | 0.5 | Starting trust level |
| reward_approve | +0.05 | User approves HITL request |
| penalty_reject | -0.10 | User rejects HITL request |
| penalty_cancel | -0.07 | User cancels during HITL |
| penalty_modify | -0.03 | User modifies before approving |
| reward_auto_success | +0.08 | Auto-approved action succeeds |
| auto_approve_threshold | 0.85 | Trust level for auto-approval |

### 105.2 Auto-Approve Logic

```python
def should_auto_approve(self, risk_level: str) -> bool:
    """Auto-approve if trust >= threshold AND risk is 'low'."""
    return self.trust >= self.config.auto_approve_threshold and risk_level == "low"
```

### 105.3 Events Tracked

| Event | Trust Change | Example |
| ----- | ------------ | ------- |
| approve | +0.05 | User confirms hotel booking |
| reject | -0.10 | User declines suggested action |
| cancel | -0.07 | User cancels mid-approval |
| modify | -0.03 | User changes params before approving |
| auto_success | +0.08 | Auto-approved action completed without issue |
| timeout | -0.05 | HITL request timed out (no user response) |

### 105.4 Integration with HILCoordinator

Before presenting a HITL request, the pipeline checks `TrustAccumulator.should_auto_approve()`.
If trust is high enough and risk is low, the request is auto-approved (no user interruption).
After each HITL outcome, `TrustAccumulator.record(outcome)` adjusts the trust score.

---

## 106. Agent-as-Provider Pattern (Fabric Integration)

**File**: `k1/fabric/providers/agent_provider.py`

Specialized agents are first-class Fabric providers. They are invoked through the
standard Fabric capability pipeline, not through Concierge directly.

### 106.1 AgentProvider

```python
class AgentProvider(BaseProvider):
    """Wraps agents as Fabric providers for capabilities like 'agent.execute.empathy_writer'."""

    async def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        return await self.agent_factory.spawn_and_execute(request, context, trace_id)
```

Registered in Fabric factory:

```python
provider_factory.register(ProviderType.AGENT, _create_agent)
```

### 106.2 AgentFactory (8-Step Spawn)

```text
Step 1: Load AgentContract via contract_loader
          - Declared sections, tools_granted, llm_budget_tokens
Step 2: Create MPSC Mailbox (WFQ INTERACTIVE priority)
Step 3: Grant LLM access via IModelGatewayPort.create_handle(budget_tokens)
Step 4: Grant SessionState read (scoped to declared sections ONLY)
Step 5: Scope tool access via ToolScope (from contract.tools_granted)
Step 6: Build ExecutionContext via ContextBuilder
Step 7: Instantiate Agent (lifecycle: PENDING → WARMING → ACTIVE)
Step 8: Agent.execute(params) → AgentResult
```

### 106.3 Agent Lifecycle FSM

```text
PENDING → WARMING → ACTIVE → IDLE (pooled, 60s TTL)
                             → DRAINING → TERMINATED
```

### 106.4 AgentPool

| Property | Value |
| -------- | ----- |
| Key | Contract name (fungible agents) |
| Max per contract | 5 |
| Reuse strategy | FIFO (oldest IDLE first) |
| TTL | 60s (sweep evicts expired) |
| Thread safety | RLock |

### 106.5 DeltaEmitter (Agent State Output)

Agents NEVER write SessionState directly (FAB-01). State changes flow through:

```text
Agent → DeltaEmitter.queue(AgentDelta(section, key, value))
  → 500ms batch window
  → LWW merge on (section, key) collisions
  → Flush → IDeltaBusPort
  → Delta Bus
  → Concierge MutationGuard
  → SessionState
```

### 106.6 Agent Invariants

| Invariant | Rule |
| --------- | ---- |
| FAB-01 | Agent NEVER writes SessionState directly (deltas only) |
| FAB-07 | ToolScope enforced on ALL tool invocations |
| Budget | LLM token budget enforced per AgentContract |
| Sections | Read access scoped to declared sections only |

### 106.7 Capability Types

```python
class CapabilityType:
    AGENT_SPAWN = "agent.spawn."     # Spawn transient agent
    AGENT_EXECUTE = "agent.execute."  # Execute agent capability
    TOOL_EXECUTE = "tool.execute."    # Direct tool execution
    WORKFLOW_RUN = "workflow.run."    # Workflow orchestration
```

Domain agent definitions live in `k1/modules/*/agents/*.yaml` and are loaded by
the kernel at startup. The `k1/agents/` module is the L4 (Workers) runtime layer
for ephemeral agent instances and dynamic mailbox allocation.

---

## 107. Concierge OrchestratorStub Reference

**File**: `k1/concierge/orchestrator/stub.py`

### 107.1 Constructor (3 Ports — Structural Enforcement)

```python
class OrchestratorStub:
    def __init__(
        self,
        fabric_gateway: IFabricGatewayPort,  # ORCH-04: only execution path
        state_read: IStateReadPort,           # ORCH-01: read-only
        delta_emit: IDeltaEmitPort,           # Fire-and-forget events
    ) -> None
```

### 107.2 Structural Invariants

| Code | Invariant | Enforcement |
| ---- | --------- | ----------- |
| ORCH-01 | No write port → no session state mutations | Constructor has no write port |
| ORCH-02 | No LLM port → no LLM calls | Constructor has no LLM port |
| ORCH-03 | No tool executor → no tool execution | Constructor has no tool port |
| ORCH-04 | All execution through Fabric only | Only `fabric_gateway` port |
| ORCH-10 | Max 2 Fabric calls (MEDIUM) | `_check_budget()` enforcement |

### 107.3 handle_task() (6-Step Flow)

```text
Step 1: emit k1.orchestration.task.accepted
Step 2: state_read.snapshot(["beliefs_active", "task_artifacts"]) → context
Step 3: CapabilityRequest(name=envelope.intent, params=context)
Step 4: fabric_gateway.execute(cap_request) [budget check enforced]
Step 5: AggregatedResult.from_medium(capability_result)
Step 6: emit k1.orchestration.dag.completed with full result payload
```

### 107.4 Type System

```python
@dataclass(frozen=True)
class Budget:
    max_fabric_calls: int = 2
    max_planner_tokens: int = 0
    timeout_ms: int = 0  # Resolved from config in __post_init__

@dataclass(frozen=True)
class TaskEnvelope:
    intent: str                    # Required, non-empty
    task_id: str                   # Auto: "task-{uuid8}"
    context: dict                  # Enriched by FSM (referents, narrative)
    tier: ComplexityTier           # MEDIUM (after HIGH reroute)
    budget: Budget                 # Frozen, immutable
    session_id: str
    trace_id: str                  # Auto: "trace-{uuid8}"

@dataclass(frozen=True)
class AggregatedResult:
    total_steps: int
    completed: int
    failed: int
    results: list
    success: bool
    step_results: list[StepResult]
    duration_ms: int
    plan_id: Optional[str]

    @classmethod
    def from_medium(cls, capability_result, trace_id, duration_ms) -> AggregatedResult
    @classmethod
    def from_multi_step(cls, capability_results, trace_id, duration_ms) -> AggregatedResult
```

### 107.5 HIGH Tier Deferred Ports (Interface Only — Not Implemented)

```python
@runtime_checkable
class IPlannerPort(Protocol):
    async def request_plan(self, request: PlanRequest) -> str    # Returns request_id
    async def cancel_plan(self, request_id: str) -> None

@runtime_checkable
class IWorkflowPort(Protocol):
    async def run(self, request: Any) -> Any

@runtime_checkable
class ISagaPort(Protocol):
    # Compensate on partial failure (interface only)
```

These ports exist as interfaces in `k1/concierge/orchestrator/ports.py` but have no
implementations yet. They will be wired when the real K1 Orchestrator replaces the stub.

---

## 108. Concierge FSM Routing Deep-Dive

**File**: `k1/concierge/fsm/controller.py`

### 108.1 Task Dispatch Entry Point

```python
def _on_task_dispatch(self, envelope: Envelope) -> None:
    """Receives k1.orchestration.task.dispatch.v1 from Front.
    Routes to orchestrator if tier is MEDIUM/HIGH.
    Falls back to Back if orchestrator unavailable."""
    payload = _parse_payload(envelope)
    task = _task_dispatch_from_payload(payload)
    self._route_via_orchestrator(envelope, task)
```

### 108.2 Single Routing Authority: _route_via_orchestrator()

```text
1. route_task_sync(dispatch, dispatch.tier) → DispatchRecord
2. If HIGH: PassthroughPlannerStub wraps as 1-step committed plan
     committed_plan = {task_id, steps: [{intent, step_id}]}
     Re-route as MEDIUM
3. Inject scoreboard referents (Gap 6: pronoun resolution)
     reference_context = {referent.text: referent.entity_id}
4. Inject narrative thread (Gap 5: context drift prevention)
     narrative_thread = narrative_active.get_active_thread_name()
5. If MEDIUM + orchestrator available:
     asyncio.create_task(_run_medium_orchestration(task_envelope))
6. If LOW or orchestrator unavailable:
     _deliver_to_back(envelope)
```

### 108.3 route_task_sync() Budget Table

**File**: `k1/concierge/orchestrator/routing.py`

```python
TIER_FABRIC_BUDGET = {LOW: 1, MEDIUM: 2, HIGH: 10}
TIER_PLANNER_TOKEN_BUDGET = {LOW: 0, MEDIUM: 0, HIGH: 3500}
```

### 108.4 Completion Normalization

```python
def _on_dag_completed(self, envelope: Envelope) -> None:
    """Receives k1.orchestration.dag.completed from OrchestratorStub.
    Normalizes to k1.orchestration.task.complete.v1 for FSM state transitions."""
```

### 108.5 Error Handling

```python
async def _run_medium_orchestration(self, task_envelope, parent_envelope_id) -> None:
    """On OrchestratorStub failure: emit k1.orchestration.task.failed.v1
    with error_code=ORCH_MEDIUM_FAILED."""
```

---

## 109. Concierge Bus Builders Reference

**File**: `k1/concierge/bus/builders.py`

28 POC topic envelope builders. Each produces a ready-to-publish `Envelope` with correct
topic, Priority (per V2 Section 3), and JSON payload.

### 109.1 Envelope ID Generation

```python
next_synthetic_envelope_id() -> int
    # Starts at 1_000_000_000 for synthetic (non-bus) envelopes
    # Used for direct mailbox delivery
```

### 109.2 Payload Enrichment

All payloads auto-enriched with canonical metadata:

```python
{
    "event_id": str,              # UUID
    "ts_utc": str,                # ISO 8601
    "payload_schema_version": int  # Schema version
}
```

### 109.3 Causal Chain Rules

| Event | parent_id |
| ----- | --------- |
| User input | 0 (root) |
| Task dispatch | User input envelope_id |
| Task complete/failed | Task dispatch envelope_id |
| Tool started | Parent tool/task envelope_id |
| Tool completed | Tool started envelope_id |

---

## 110. Concierge Config Reference

**File**: `k1/concierge/config/defaults.yaml` (shimmed from `poc.k1_poc.config.loader`)

### 110.1 Back Actor Config

| Key | Default | Description |
| --- | ------- | ----------- |
| actors.back.max_iterations.LOW | 10 | Max ReAct loop iterations for LOW tier |
| actors.back.max_iterations.MEDIUM | 14 | Max ReAct loop iterations for MEDIUM tier |
| actors.back.max_iterations.HIGH | 24 | Max ReAct loop iterations for HIGH tier |
| actors.back.hitl_timeout_s | 60 | HITL request timeout |
| actors.back.budget_floor | 4 | Minimum iterations regardless of tier |

### 110.2 Front Actor Config

| Key | Default | Description |
| --- | ------- | ----------- |
| actors.front.history_window_fallback | 20 | Max conversation turns in prompt context |
| actors.front.default_tier | "LOW" | Default tier if classification fails |

### 110.3 Back Pool Config

| Key | Default | Description |
| --- | ------- | ----------- |
| back_pool.pool_size | 3 | Max concurrent back workers |
| back_pool.max_concurrent_per_session | 2 | Max concurrent tasks per session |
| back_pool.lease_ttl_s | 300 | Task lease timeout |
| back_pool.grace_period_s | 5 | Grace period before lease expiry |

### 110.4 Bus Config

| Key | Default | Description |
| --- | ------- | ----------- |
| bus.mailbox_capacity | 64 | Max messages per mailbox |
| bus.gap_timeout_ms | 5000 | Gap detection timeout |
| bus.validate_canonical_events | false | Skip validation for performance |

### 110.5 Delta Config

| Key | Default | Description |
| --- | ------- | ----------- |
| delta.batch_window_ms | 500 | DeltaAggregator flush interval |
| delta.overflow.hot_budget_total | 53248 | HOT tier total bytes (52KB) |

### 110.6 Kernel Config

| Key | Default | Description |
| --- | ------- | ----------- |
| kernel.poll_interval_s | 0.05 | Mailbox consumer poll interval |
| kernel.dedup_cache_size | 1000 | Dedup set size before clear |

---

## PART F: Model Hub Deep Dive

---

## 111. Model Hub Architecture Overview

The Model Hub is the **unified LLM access gateway** of K1 (Layer L2.5). All LLM
traffic flows through a single facade (`IModelHubPort`) into a 9-step request
pipeline backed by provider plugins. The hub handles capability routing, model
selection, cost management, caching, normalization, circuit breaking, rate
limiting, and audit logging. It is consumed by Planner (via `LLMGatewayAdapter`)
and Concierge (via `ModelGatewayAdapter`) — no other component talks to LLM
providers directly.

### 111.1 Layered Architecture

```
Layer 0 (types):   types.py, config.py, events.py, metrics.py, manifest.py, tracing.py
Layer 1 (ports):   ports/*.py (7 port protocols)
Layer 2 (services): services/*.py (12 services)
Layer 3 (factory): factory.py (DI wiring)
Layer 4 (plugins): plugins/*.py (5 provider plugins + 1 test plugin)
Layer 5 (adapters): adapters/*.py (7 adapters bridging to Bus, SessionState, etc.)
```

Import rules:

- Layer N may import from Layer N-1 or below, never from N+1.
- Plugins (Layer 4) import only from types + base protocol.
- Factory (Layer 3) imports everything to wire the object graph.

### 111.2 Hub Container

Unlike Fabric (dataclass) or Planner (agent), the Model Hub is organised around
`_HubCore` as the IModelHubPort implementation. The factory builds the full
service graph and returns `_HubCore` wrapping `RequestRouter` + `ProviderRegistry`
\+ `HealthReportAdapter`.

```python
class _HubCore:
    """IModelHubPort implementation bridging RequestRouter + Registry."""
    _router: RequestRouter      # 9-step pipeline
    _registry: ProviderRegistry # provider manifest index
    _health: HealthReportAdapter

    async def execute(request: HubRequest) -> HubResponse
    async def stream_execute(request: HubRequest) -> AsyncIterator[HubChunk]
    async def discover_capabilities() -> Dict[CapabilityType, List[str]]
    async def discover_models(capability?) -> List[ModelInfo]
    async def health() -> HubHealthReport
```

### 111.3 Kernel Integration Points

| Consumer | Adapter | Wraps | Purpose |
|----------|---------|-------|---------|
| Planner | `LLMGatewayAdapter(model_hub)` | Planner's `ILLMPort` | Plan generation, expansion, validation LLM calls |
| Concierge | `ModelGatewayAdapter(model_hub)` | Concierge's `ILLMPort` | Conversation, tool calling, structured output |
| Fabric | `IModelGatewayPort` (test stub Phase 1) | Fabric port | Agent-based LLM invocation (Phase 2) |

---

## 112. Model Hub Ports (7)

All ports are `@runtime_checkable Protocol` classes in `k1/model_hub/ports/`.

### 112.1 IModelHubPort (Facade)

**File**: `k1/model_hub/ports/hub_port.py`

THE single gateway for all LLM traffic (MH-16). All LLM consumers call
`execute()` or `stream_execute()`. No direct provider access allowed.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `execute` | `async (HubRequest) -> HubResponse` | Request-reply LLM call |
| `stream_execute` | `async (HubRequest) -> AsyncIterator[HubChunk]` | Streaming LLM call |
| `discover_capabilities` | `async () -> Dict[CapabilityType, List[str]]` | Available capabilities → provider IDs |
| `discover_models` | `async (capability?) -> List[ModelInfo]` | Available models, optionally filtered |
| `health` | `async () -> HubHealthReport` | Aggregate health report |

### 112.2 IEventPort

**File**: `k1/model_hub/ports/event_port.py`

Event bus integration for publishing hub lifecycle and operational events.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `publish` | `async (topic: str, payload: Any) -> None` | Publish integration event |
| `subscribe` | `async (topics: List[str], handler) -> Subscription` | Subscribe to event topics |

### 112.3 IStateReadPort

**File**: `k1/model_hub/ports/state_read_port.py`

Read-only session state access (MH-01: Model Hub NEVER writes session state).

| Method | Signature | Purpose |
|--------|-----------|---------|
| `read` | `async (sections: List[str]) -> StateSnapshot` | Read session state sections |

### 112.4 IMetricsPort

**File**: `k1/model_hub/ports/metrics_port.py`

Synchronous fire-and-forget metrics emission.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `emit` | `(metric_name: str, value: float, labels?) -> None` | Emit metric datapoint |

### 112.5 IConfigPort

**File**: `k1/model_hub/ports/config_port.py`

Read hub configuration with optional hot-reload watch.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get` | `(key: str) -> Any` | Read config value |
| `watch` | `(key: str, callback) -> ConfigSubscription` | Watch for config changes |

### 112.6 ICredentialPort

**File**: `k1/model_hub/ports/credential_port.py`

Credential store access (MH-02: API keys from CredentialStore only, never
from config, env, or manifest).

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_key` | `async (provider_id: str) -> str` | Retrieve API key for provider |
| `refresh_key` | `async (provider_id: str) -> str` | Force-refresh API key |

### 112.7 IHealthPort

**File**: `k1/model_hub/ports/health_port.py`

Health reporting to Fabric/Observability.

| Method | Signature | Purpose |
|--------|-----------|---------|
| `report_health` | `(component: str, status: HealthStatus) -> None` | Report component health |
| `check_health` | `() -> HealthReport` | Get aggregate health report |

---

## 113. Model Hub Adapters (7)

All adapters are in `k1/model_hub/adapters/`. Each implements one port
protocol and bridges to a kernel infrastructure component.

| Adapter | Port | Bridges To | Notes |
|---------|------|------------|-------|
| `ConfigAdapter` | `IConfigPort` | `ModelHubConfig` | Read-only config access |
| `CredentialStoreAdapter` | `ICredentialPort` | Kernel credential store | API key retrieval (MH-02) |
| `EventBusAdapter` | `IEventPort` | K1 Bus (`IBus`) | Publishes hub events to bus topics |
| `HealthReportAdapter` | `IHealthPort` | Internal health aggregation | Used by `_HubCore.health()` |
| `LLMRequestBusAdapter` | `IModelHubPort` | K1 Bus | Forwards LLM requests over bus (optional) |
| `PrometheusAdapter` | `IMetricsPort` | Prometheus client | Exposes 12 metrics as Prometheus gauges/counters/histograms |
| `SessionStateReadAdapter` | `IStateReadPort` | SessionState reader | Read-only session data for context enrichment |

---

## 114. Model Hub Factory Internal Wiring

**File**: `k1/model_hub/factory.py`

`ModelHubFactory` provides three creation modes. All modes follow the same
11-step wiring sequence.

### 114.1 Creation Modes

| Mode | Method | Returns | Use Case |
|------|--------|---------|----------|
| Standalone | `create_standalone(config, plugins)` | `IModelHubPort` | Production: kernel bootstrap (Phase 3.5) |
| Testing | `create_for_testing(overrides?)` | `(IModelHubPort, dict)` | Tests: facade + all services for inspection |
| Custom | `create_with_ports(ports, config, plugins)` | `IModelHubPort` | Integration: caller supplies ports |

### 114.2 Wiring Sequence (11 steps)

```
Step  1: Load config (ModelHubConfig.from_dict or default)
Step  2: Initialize CredentialStore (CredentialStoreAdapter)
Step  3: Create ProviderRegistry (cfg)
Step  4: Create resilience services
          - CircuitBreakerManager (per-provider state machine)
          - RateLimiter (token bucket with headroom_pct)
Step  5: Create cost/cache/budget services
          - CostTracker
          - ResponseCache (LRU, TTL=5min default)
          - BudgetEnforcer ($5/day default, MH-08)
Step  6: Create routing services
          - HealthReportAdapter → _DefaultHealthQuery
          - CapabilityRouter (registry, circuit_breaker, rate_limiter, health_monitor)
          - ModelSelector (weighted scoring)
Step  7: Create NormalizationLayer
Step  8: Create ProviderDispatcher (circuit_mgr, rate_limiter, credential_port, plugins)
Step  9: Create RequestRouter wiring all services
          - capability_router, model_selector, budget_enforcer,
            response_cache, normalization_layer, dispatcher,
            cost_tracker, audit_logger, [metrics_port]
Step 10: Create HealthMonitor + AuditLogger
Step 11: Return _HubCore(router, registry, health_adapter)
```

### 114.3 DI Validation

All 7 ports are checked via `isinstance(port, Protocol)` at factory creation
time. Invalid ports raise `TypeError` immediately — no silent wiring failures.

---

## 115. Request Pipeline (9 Steps)

**File**: `k1/model_hub/services/request_router.py`

ALL traffic flows through `RequestRouter.route()` or `.stream_route()` (MH-16).
No shortcut paths exist.

### 115.1 Pipeline Steps

```
HubRequest
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Step 1: _validate()                                      │
│   Schema validation, trace_id enforcement (MH-03)        │
├─────────────────────────────────────────────────────────┤
│ Step 2: BudgetEnforcer.check()                           │
│   ALLOW / ALLOW_DEGRADED / REJECT (MH-04, MH-08)        │
├─────────────────────────────────────────────────────────┤
│ Step 3: Priority classification                          │
│   Timeout from RequestConstraints.priority (MH-15)       │
├─────────────────────────────────────────────────────────┤
│ Step 4: CapabilityRouter.route()                         │
│   5-step filtering → eligible providers (MH-06, MH-18)   │
├─────────────────────────────────────────────────────────┤
│ Step 5: ModelSelector.select()                           │
│   Weighted scoring → provider + model + fallback (MH-13) │
├─────────────────────────────────────────────────────────┤
│ Step 6: ResponseCache.get()                              │
│   Cache hit → return immediately (MH-09)                 │
├─────────────────────────────────────────────────────────┤
│ Step 7: NormalizationLayer.normalize()                   │
│   HubRequest → NormalizedRequest (provider-agnostic)     │
├─────────────────────────────────────────────────────────┤
│ Step 8: ProviderDispatcher.dispatch()                    │
│   Plugin execute + circuit breaker + rate limiter (MH-05)│
├─────────────────────────────────────────────────────────┤
│ Step 9: Post-process                                     │
│   Denormalize, cache store, cost tracking, audit log     │
└─────────────────────────────────────────────────────────┘
    │
    ▼
HubResponse
```

### 115.2 Service Reference

| Step | Service | File | Key Method |
|------|---------|------|------------|
| 1 | `RequestRouter` | `services/request_router.py` | `_validate(request)` |
| 2 | `BudgetEnforcer` | `services/budget_enforcer.py` | `check(request) -> BudgetDecision` |
| 3 | (inline) | `services/request_router.py` | Priority → timeout mapping |
| 4 | `CapabilityRouter` | `services/capability_router.py` | `route(request) -> List[EligibleProvider]` |
| 5 | `ModelSelector` | `services/model_selector.py` | `select(eligible, request) -> Selection` |
| 6 | `ResponseCache` | `services/response_cache.py` | `get(cache_key) -> CachedResponse?` |
| 7 | `NormalizationLayer` | `services/normalization_layer.py` | `normalize(request, provider) -> NormalizedRequest` |
| 8 | `ProviderDispatcher` | `services/provider_dispatcher.py` | `dispatch(normalized, selection) -> ProviderResponse` |
| 9 | `CostTracker` / `AuditLogger` | `services/cost_tracker.py`, `services/audit_logger.py` | `compute_cost()`, `log()` |

---

## 116. Provider Plugin System

**File**: `k1/model_hub/plugins/base.py`

Every provider implements `IProviderPlugin` (7 methods). Plugins are isolated —
one crash doesn't affect others (MH-17).

### 116.1 IProviderPlugin Protocol

```python
class IProviderPlugin(Protocol):
    async def initialize(self, manifest: ProviderManifest) -> None: ...
    def supports(self, capability: CapabilityType) -> bool: ...
    async def execute(self, request: NormalizedRequest) -> ProviderResponse: ...
    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]: ...
    def estimate_tokens(self, messages: list) -> int: ...
    async def health_check(self) -> ProviderHealth: ...
    async def close(self) -> None: ...
```

### 116.2 Day-1 Plugins

| Plugin | File | Provider | Capabilities |
|--------|------|----------|-------------|
| `OpenAIPlugin` | `plugins/openai_plugin.py` | OpenAI (GPT-4o, etc.) | CHAT, TOOL_CALL, STRUCTURED, VISION, EMBED |
| `AnthropicPlugin` | `plugins/anthropic_plugin.py` | Anthropic (Claude) | CHAT, TOOL_CALL, STRUCTURED, REASON |
| `GooglePlugin` | `plugins/google_plugin.py` | Google (Gemini) | CHAT, TOOL_CALL, STRUCTURED, VISION |
| `VLLMPlugin` | `plugins/vllm_plugin.py` | vLLM (local GPU) | CHAT, EMBED |
| `OllamaPlugin` | `plugins/ollama_plugin.py` | Ollama (local CPU) | CHAT, EMBED |
| `TestPlugin` | `plugins/test_plugin.py` | Test harness | All (configurable) |

### 116.3 Adding a New Provider

1. Create `k1/model_hub/plugins/my_plugin.py` implementing `IProviderPlugin`
2. Create a `ProviderManifest` YAML/dict with capabilities, models, costs
3. Register via `ProviderRegistry.register(manifest, plugin)`
4. The hub automatically routes traffic based on manifest capabilities

No hub service code changes required — the manifest is the sole source of truth
for capabilities (MH-18).

---

## 117. Model Hub Invariants (18)

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| MH-01 | Hub NEVER writes session state | No `IStateWritePort` dependency |
| MH-02 | API keys from CredentialStore only | `ICredentialPort`, never from manifest |
| MH-03 | trace_id required on every request | `HubRequest.__post_init__` raises `ValueError` |
| MH-04 | HARD rejection on budget exceeded | `BudgetEnforcer.check()` → `BudgetExceededError` |
| MH-05 | Circuit breaker per provider | `CircuitBreakerManager` per-provider state machine |
| MH-06 | Fallback chain from capability routing | `ModelSelector` builds ordered fallback list |
| MH-07 | Cost from manifest model cost tables | `CostTracker.compute_cost()` uses `ModelSpec` |
| MH-08 | $5/day default daily budget | `ModelHubConfig.daily_budget_usd = 5.0` |
| MH-09 | Cache TTL 5min default, LRU eviction | `ResponseCache` with configurable TTL |
| MH-10 | Streaming via async generators | `stream_execute()` yields `HubChunk` |
| MH-11 | Full audit trail per request | `AuditLogger.log()` captures all metadata |
| MH-12 | Rate limiting per provider 80% headroom | `RateLimiter` token bucket with headroom |
| MH-13 | Model selection by priority-weighted scoring | `ModelSelector` with per-priority weights |
| MH-14 | No hardcoded model names in hub code | All model references via manifest `ModelSpec` |
| MH-15 | Priority-based timeouts | `RequestConstraints.priority` → timeout_ms |
| MH-16 | ALL traffic through RequestRouter | Single entry point, no bypass |
| MH-17 | Plugin isolation (one crash doesn't affect others) | Exception handling in `_try_provider()` |
| MH-18 | Manifest sole source of truth for capabilities | `ProviderManifest` drives all routing |

---

## 118. Model Hub Event Reference (11 Topics)

All events published via `IEventPort.publish(topic, payload)`.
Topic pattern: `k1.model_hub.{domain}.{action}.v1`.

| Topic | Payload Class | Key Fields | When |
|-------|---------------|------------|------|
| `k1.model_hub.request.received.v1` | `RequestReceivedPayload` | request_id, consumer_id, capability | Step 1: request enters pipeline |
| `k1.model_hub.request.routed.v1` | `RequestRoutedPayload` | request_id, provider_id, model_id | Step 5: model selected |
| `k1.model_hub.response.complete.v1` | `ResponseCompletePayload` | request_id, tokens_used, cost_usd, latency_ms | Step 9: response returned |
| `k1.model_hub.cache.hit.v1` | `CacheHitPayload` | request_id, cache_key, age_ms | Step 6: cache hit |
| `k1.model_hub.provider.failure.v1` | `ProviderFailurePayload` | request_id, provider_id, error_type, will_fallback | Step 8: provider error |
| `k1.model_hub.fallback.triggered.v1` | `FallbackTriggeredPayload` | request_id, from_provider, to_provider | Step 8: fallback chain activated |
| `k1.model_hub.circuit.state.v1` | `CircuitStatePayload` | provider_id, old_state, new_state | Circuit breaker state change |
| `k1.model_hub.budget.alert.v1` | `BudgetAlertPayload` | tenant_id, level (WARNING/EXCEEDED), pct | Budget threshold crossed |
| `k1.model_hub.provider.health.v1` | `ProviderHealthPayload` | provider_id, status, latency_p50, error_rate | Health check result |
| `k1.model_hub.provider.registered.v1` | `ProviderRegisteredPayload` | provider_id, capabilities, model_count | Plugin registration |
| `k1.model_hub.capability.available.v1` | `CapabilityAvailablePayload` | capability, provider_ids, model_count | Capability becomes available |

---

## 119. Model Hub Metrics (12 Definitions)

**File**: `k1/model_hub/metrics.py`

All metrics emitted via `IMetricsPort.emit()` (fire-and-forget).

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `model_hub.requests_total` | Counter | consumer_id, capability | Total requests received |
| `model_hub.errors_total` | Counter | error_type | Total errors |
| `model_hub.cache_hits_total` | Counter | capability | Response cache hits |
| `model_hub.fallbacks_total` | Counter | from_provider, to_provider | Provider fallback events |
| `model_hub.budget_rejections_total` | Counter | tenant_id | Budget-rejected requests |
| `model_hub.latency_ms` | Histogram | capability, provider_id | End-to-end hub latency |
| `model_hub.provider_latency_ms` | Histogram | provider_id, model_id | Provider plugin latency |
| `model_hub.tokens_used` | Histogram | capability, model_id | Tokens per request |
| `model_hub.cost_usd` | Histogram | provider_id | Cost per request in USD |
| `model_hub.active_requests` | Gauge | — | Currently active requests |
| `model_hub.provider_circuit_state` | Gauge | provider_id | Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN) |
| `model_hub.budget_pct` | Gauge | tenant_id | Daily budget usage percentage |

---

## 120. Model Hub Config Reference

**File**: `k1/model_hub/config.py`

`ModelHubConfig` is a frozen dataclass with `__post_init__` validation.

| Key | Default | Description |
|-----|---------|-------------|
| `daily_budget_usd` | 5.0 | Daily budget cap (MH-08) |
| `monthly_budget_usd` | 100.0 | Monthly budget cap |
| `max_concurrent_requests` | 50 | Max concurrent hub requests |
| `cache_max_entries` | 1000 | LRU cache capacity |
| `cache_ttl_s` | 300 | Cache TTL in seconds (MH-09) |
| `realtime_timeout_ms` | 10000 | REALTIME priority timeout |
| `interactive_timeout_ms` | 30000 | INTERACTIVE priority timeout |
| `background_timeout_ms` | 60000 | BACKGROUND priority timeout |
| `rate_limit_headroom_pct` | 0.80 | Rate limit headroom (MH-12) |
| `health_check_interval_s` | 30 | Health check poll interval |
| `manifest_dir` | `k1/config/providers` | Provider manifest YAML directory |
| `shutdown_grace_period_ms` | 10000 | Plugin close grace period |

All fields validated in `__post_init__`: positive numerics, headroom in (0, 1].

---

## 121. Model Hub Shutdown

Model Hub shutdown sequence (called as step 6 in kernel shutdown):

```
1. Stop accepting new requests (set _accepting = False)
2. Wait for active requests to drain (up to shutdown_grace_period_ms)
3. Close all provider plugins (await plugin.close() for each)
4. Flush metrics (final emit of active_requests=0)
5. Clear response cache
6. Log shutdown summary (total_requests, total_cost, uptime)
```

Invariant: No requests in-flight after step 2 completes. Step 3 closes
external API connections (HTTP sessions, gRPC channels). Plugin close
failures are logged but don't block shutdown.

---

## 122. Model Hub Bootstrap Gotchas

| # | Gotcha | Consequence if Ignored |
|---|--------|----------------------|
| MH-G01 | Model Hub must be created BEFORE Planner and Concierge (Phase 3.5). If created after, `LLMGatewayAdapter(model_hub)` and `ModelGatewayAdapter(model_hub)` receive a None reference. | `NoneType` errors on first LLM call |
| MH-G02 | Plugin initialization is synchronous in `create_standalone()`. Long plugin init (e.g., loading local models for vLLM/Ollama) blocks the bootstrap thread. Consider deferring heavy plugins to a background task. | Bootstrap latency > 500ms target |
| MH-G03 | `BudgetEnforcer` starts tracking from creation time. If kernel restarts mid-day, the daily budget resets to $0 spent. Persist budget state to survive restarts. | Budget overspend after restart |
| MH-G04 | `ResponseCache` is in-memory (not shared). Each kernel instance has its own cache. If running multiple instances, cache hit rate drops. | Duplicate LLM calls across instances |
| MH-G05 | `ICredentialPort.get_key()` is async. Factory creation is sync. Credential retrieval happens on first request, not at startup. If the credential store is down, the first request fails. | First request latency spike or error |
| MH-G06 | Model Hub does NOT subscribe to bus events. It's purely request-driven. Integration events are published (outbound) only. | No gotcha per se, but don't expect hub to react to bus events |
| MH-G07 | The `model_hub` variable must be passed to BOTH Planner and Concierge adapters. Forgetting one means that component falls back to its test stub (which may return canned responses). | Silent wrong behavior — LLM calls return stubs |

---

## 123. Model Hub Types Reference

**File**: `k1/model_hub/types.py`

All types are frozen dataclasses with no I/O and no port references.

### 123.1 Enums

| Enum | Values | Purpose |
|------|--------|---------|
| `CapabilityType` | CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH, MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS, IMAGE_GEN, WEB_SEARCH, CODE_EXEC | 15-member capability taxonomy |
| `Priority` | REALTIME, INTERACTIVE, BACKGROUND | Request priority tier (MH-15) |
| `FinishReason` | stop, tool_calls, length, error, safety | Provider response completion reason |
| `HealthStatus` | HEALTHY, DEGRADED, UNHEALTHY | Component/provider health |
| `CircuitState` | CLOSED, OPEN, HALF_OPEN | Circuit breaker state (MH-05) |
| `BudgetDecision` | ALLOW, ALLOW_DEGRADED, REJECT | Budget enforcement decision |
| `PlacementType` | remote, local_gpu, local_cpu | Provider placement (ADR-0027) |
| `ModelTier` | FAST, STANDARD, PREMIUM | Performance tier hint |

### 123.2 Request/Response Types

| Type | Key Fields | Purpose |
|------|------------|---------|
| `HubRequest` | capability, messages, consumer_id, trace_id, constraints | Inbound LLM request |
| `HubResponse` | content, finish_reason, tokens_used, cost_usd, model_id, provider_id | LLM response |
| `HubChunk` | delta, is_final, accumulated_tokens | Streaming chunk |
| `RequestConstraints` | priority, max_tokens, temperature, tools, response_format | Request parameters |
| `NormalizedRequest` | messages, provider_config, timeout_ms | Provider-agnostic normalized request |
| `ProviderResponse` | content, finish_reason, usage, raw_response | Raw provider response |
| `ModelInfo` | id, provider_id, capabilities, cost, max_context, supports_streaming | Model discovery result |
| `HubHealthReport` | status (HealthStatus) | Aggregate hub health |

---

## 124. Model Hub Tracing (34 Phases)

**File**: `k1/model_hub/tracing.py`

All log events use structured logging with fields:
`trace_id`, `request_id`, `consumer_id`, `capability`, `model_id`, `provider_id`,
`timestamp`, `level`, `phase`.

**Privacy**: Raw prompts and API keys are NEVER logged. All message content
passes through `redact_messages()`. Labels pass through `safe_labels()`.

---

## 125. Model Hub Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Budget check | < 1ms | In-memory arithmetic |
| Capability routing | < 2ms | Registry index lookup + 5-step filter |
| Model selection | < 5ms | Weighted scoring over eligible models |
| Cache lookup | < 2ms | LRU dict lookup |
| Normalization | < 1ms | Dataclass construction |
| **Total hub overhead** | **< 12ms** | Excludes LLM inference time |

These targets ensure the hub adds negligible latency to LLM calls.
Benchmarked via `tests/k1/model_hub/benchmarks/`.

---

## PART G: Family Context & Household Projection

---

## 126. Household Projection Hydration Protocol (D-14, D-15, D-16)

Family member identity, safety-critical health data, access levels, device registry,
and household governance are NOT stored in SessionState sections. They live in a
frozen `HouseholdProjection` cached in-memory inside Concierge.

### 126.1 Design Principle — Data Ownership Separation

> **Profile knows WHO. Tools know WHAT. K0 knows WHY/WHEN/HOW.**

| Category | Owner | Storage | Swappable? |
|----------|-------|---------|------------|
| Identity & Safety | HouseholdProjection | K1 local (hydrated from K0 at boot) | No — core contract |
| Operational Data | M11 MCP Tools (44 contracts) | Per-tool SQLite (provider-swappable) | Yes — MCP → IFL |
| Learned Knowledge | K0 Memory Layers (st_sem, st_epi, st_procedural, st_social, st_kg) | K0 PostgreSQL | No — canonical |
| Session Persona | PersonaSection (.fbs) | SessionState WARM tier | No — already exists |

### 126.2 What Lives in HouseholdProjection

```python
@dataclass(frozen=True)
class MemberProfile:
    member_id: str              # stable UUID, maps to K0 actor_id
    display_name: str           # "Alex"
    nicknames: list[str]        # ["Al", "Dad"]
    date_of_birth: str          # ISO 8601
    role_in_family: str         # "parent", "child", "grandparent", "caretaker"
    languages: list[str]        # ["en", "es"]
    access_level: str           # "full_adult", "supervised", "child", "limited", "guest"
    # Safety-critical (always in-memory, 0ms lookup):
    allergies: list[Allergy]    # substance, category, severity
    chronic_conditions: list[str]
    emergency_contact: str | None

@dataclass(frozen=True)
class DeviceRegistration:
    device_id: str              # maps to K0 device_id
    owner_member_id: str
    device_type: str            # "iPhone", "iPad", "Hub"
    is_shared: bool             # kitchen_hub = True

@dataclass(frozen=True)
class HouseholdGovernance:
    screen_time_rules: dict[str, Any]
    quiet_hours: str | None
    content_policies: dict[str, str]
    financial_authority: list[str]  # member_ids
    data_sharing_policy: str

@dataclass(frozen=True)
class HouseholdProjection:
    household_id: str           # maps to K0 tenant_id + space_id
    family_name: str
    timezone: str
    members: dict[str, MemberProfile]         # member_id -> profile
    devices: dict[str, DeviceRegistration]     # device_id -> registration
    governance: HouseholdGovernance
    version: int                               # monotonic, incremented on each delta
    stale: bool = False                        # True when K0 unreachable at boot
```

### 126.3 Boot-Time Hydration (Phase 6.5)

```
SESSION BOOT (after ConciergeFactory.create_with_ports, before Phase 7):

  1. bridge_client.query("household.projection.v1", session_id)
     → K0 responds with versioned HouseholdProjection snapshot
     → Concierge caches in-memory as frozen dataclass
     → Persisted to LOCAL COLD (SQLite) as backup

  2. If K0 unreachable (bridge_client is None or timeout):
     → Load from LOCAL COLD (last known good)
     → Flag: projection.stale = True
     → Concierge works fine — edge-first (D-15)

  3. bridge_client.subscribe("household.delta.v1", handler)
     → K0 pushes member/device/governance changes via SSE
     → Concierge applies deltas to in-memory cache + LOCAL COLD
     → projection.version increments monotonically
```

### 126.4 Per-Turn Usage (Fast, Local Only)

```
turn_start:
  device_id (from WebSocket / IInputPort metadata)
    → projection.devices[device_id] → owner_member_id  (0ms, in-memory)
    → projection.members[member_id] → access_level      (0ms, in-memory)
    → Safety gate: allergies, chronic_conditions          (0ms, in-memory)

during turn:
  "What's for dinner?"
    → Recipes MCP serves meal plan (tool's own SQLite)
    → projection.members[member_id].allergies for safety filter (0ms)

NEVER per-turn:
  ✗ bridge_client.query(anything)
  ✗ K0 round-trip for family context
  ✗ Full HouseholdProjection reload
```

### 126.5 K0 Deep-Query Pattern (IMemoryPort.recall)

K0 is NOT for per-turn lookups. K0 is invoked via `IMemoryPort.recall()` when
Concierge needs cross-session patterns that no tool or profile field can answer.

**When K0 IS invoked:**

| Trigger | K0 Query | Returns |
|---------|----------|---------|
| Multi-day mood pattern | `recall(mood, last_7d)` | Affect trajectory from st_epi |
| "Remember when we..." | `recall(event, semantic)` | Episodic + semantic matches |
| Behavioral change | `recall(routine, member)` | st_procedural lifecycle state |
| Relationship question | `recall(person, social)` | st_social relationship strength |
| Gift suggestion | `recall(preferences, member)` | st_sem learned preferences |

**When K0 is NOT invoked:**

| Request | Served By | Latency |
|---------|-----------|---------|
| "What's Jordan's allergy?" | HouseholdProjection (in-memory) | 0ms |
| "What's on the calendar?" | Calendar MCP (local SQLite) | < 5ms |
| "Add milk to grocery list" | Tasks MCP (local SQLite) | < 5ms |
| "Who's picking up Riley?" | Transport MCP (local SQLite) | < 5ms |

### 126.6 What Does NOT Belong in HouseholdProjection

Operational data (calendar events, medication schedules, chores, budget) lives in
M11 MCP tool servers. Learned data (preferences, routines, relationships) lives in
K0 memory layers. See whiteboard §13.3 for the full 20+ item mapping.

| Data | NOT HouseholdProjection Because | Actual Owner |
|------|--------------------------------|--------------|
| Medication schedules | Tool data; swappable | Health MCP (E11.9) |
| Calendar events | Tool data; swappable to Google/Apple | Calendar MCP (E11.1) |
| Favorite foods | Learned from conversations | K0 st_sem |
| Morning routines | Auto-detected patterns | K0 st_procedural |
| Communication style | Per-session calibration | PersonaSection (.fbs) |

### 126.7 Shutdown

```
concierge.stop():
  → Unsubscribe from household.delta.v1
  → Final LOCAL COLD checkpoint of HouseholdProjection
  → (projection is frozen dataclass — no flush needed)
```

### 126.8 Validation Checklist

| # | Check | How to Verify | Status |
|---|-------|---------------|--------|
| W-50 | HouseholdProjection hydrated at boot | `concierge.household.members` non-empty after Phase 6.5 | [ ] |
| W-51 | Offline fallback works | Start with bridge_client=None, verify LOCAL COLD load + stale flag | [ ] |
| W-52 | SSE deltas apply | Emit household.delta.v1, verify projection.version incremented | [ ] |
| W-53 | Per-turn device→member lookup | `projection.devices[device_id].owner_member_id` resolves | [ ] |
| W-54 | Allergies available without K0 | `projection.members[id].allergies` returns data when K0 offline | [ ] |
| W-55 | No SessionState identity_core section | `session_manager.list_sections()` has no "identity_core" | [ ] |
