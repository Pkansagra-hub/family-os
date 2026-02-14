# K1 Kernel Wiring Specification

Status: PLANNING -- fill as implementation proceeds.

---

## 1. Purpose

This document is the single reference for wiring Bus, Fabric, SessionState,
and Orchestrator into a unified K1 kernel runtime.  Each component is
self-contained with hexagonal ports.  The kernel bootstrap creates shared
infrastructure (Bus, MailboxRouter) and injects real adapters into each
component's factory.  Four managed components total.

---

## 2. Component Inventory

| Component | Factory | Ports (count) | Standalone Adapters | Bus Adapter |
|-----------|---------|---------------|---------------------|-------------|
| Bus | `BusFactory.create_local()` | 3 (IBus, IMailbox, IMailboxRouter) | n/a (IS the infrastructure) | n/a |
| Fabric | `FabricFactory.create_with_ports()` | 6 | Test stubs for all 6 | `FabricBusAdapter` |
| SessionState | `SessionStateFactory.create_with_ports()` | 5 (4 mandatory + 1 optional) | Local/in-memory for all | `SessionBusAdapter` |
| Orchestrator | `OrchestratorFactory.create_production()` | 9 (8 core + IAdminPort): IMailboxPort, IFabricGatewayPort, IPlannerPort, IStateReadPort, IDeltaEmitPort, IBridgeWritePort, IEventSubscriptionPort, IWorkflowStoragePort, IAdminPort | 17 adapters (8 production + 8 test + AdminHttpAdapter) | Reuses `FabricBusAdapter` via EventSubscriptionAdapter + DeltaEmitAdapter |
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

---

## 6. Topic Namespace Registry

| Prefix | Owner | Purpose |
|--------|-------|---------|
| `k1.session.*` | SessionBusAdapter | Session state events (mutations, checkpoints) |
| `k1.agent.{id}.delta.v1` | FabricBusAdapter | Agent delta broadcasts |
| `k1.fabric.*` | FabricBusAdapter | Fabric lifecycle/execution events |
| `k1.orchestration.*` | DeltaEmitAdapter | Orchestrator task/DAG/step/workflow/saga events (17 emitted topics via `events.py`) |
| `k1.planner.*` | PlannerAdapter / Bus | Planner plan lifecycle events (consumed by Orchestrator: plan.ready, plan.failed, plan.cancelled, micro_replan.ready) |
| `k1.hil.*` | DeltaEmitAdapter / Bus | Human-in-the-loop request/response events (emitted by Orchestrator, consumed: override_response, fallback_response) |
| `k1.capability.*` | Fabric / Bus | Capability completion/failure events (consumed by Orchestrator via EventSubscriptionAdapter) |
| `k1.bus.lifecycle.*` | RustBus/LocalBus | Internal bus lifecycle (subscribe/unsubscribe) |
| `k1.kernel.*` | Kernel bootstrap | Kernel-level events (startup, shutdown, health) |

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

# Phase 5: Planner cross-wiring (TODO: when Planner module is ready)
# from k1.fabric.circuit_breaker.breaker import CircuitBreaker
# planner_mailbox = planner_module.get_mailbox()
# cb_planner = CircuitBreaker("CB_PLANNER",
#     failure_threshold=orch_config.cb_planner_failure_threshold,
#     reset_timeout_s=orch_config.cb_planner_reset_timeout_ms / 1000)
# planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
# orchestrator._planner_port = planner_adapter  # hot-swap planner port

# Phase 6: Start lifecycle
session_manager.start()

# Phase 7: Expose kernel API
return KernelRuntime(bus=bus, mailbox_router=mailbox_router,
                     session=session_manager, fabric=fabric,
                     orchestrator=orchestrator)
```

---

## 8. Shutdown Sequence

```
1. orchestrator.shutdown()    -- stop admin HTTP, drain active DAG (30s), stop scheduler, unsubscribe events, persist trigger states, cancel loops
2. fabric.shutdown()          -- drain pending executions
3. session_manager.stop()     -- final checkpoint, flush events
4. bus.close()                -- drain subscribers, close ring buffer
5. mailbox_router.close()     -- drain all mailboxes
```

Order matters: consumers shut down before infrastructure.
Orchestrator is a consumer of Fabric, Fabric is a consumer of SessionState.

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
| W-08 | Shutdown order correct | Stop orchestrator, stop fabric, stop session, close bus -- no errors | [ ] |
| W-09 | No circular imports | `python -c "from k1.kernel.bootstrap import KernelRuntime"` succeeds | [ ] |
| W-10 | All 172 Rust + 1005 Python bus tests still pass | `cargo test` + `pytest tests/k1/bus/` | [ ] |
| W-11 | Orchestrator factory completes < 500ms | `time OrchestratorFactory.create_production(config)` | [ ] |
| W-12 | All 8 Orchestrator ports + admin injected | All 8 core ports non-None + _admin set if admin_enabled after factory | [ ] |
| W-13 | FabricGatewayAdapter wraps real Fabric | `adapter.execute(request)` returns valid CapabilityResult | [ ] |
| W-14 | StateReadAdapter reads real SessionState | `adapter.read_section(sid, "cognitive") is not None` after session.start() | [ ] |
| W-15 | EventSub receives events through Bus | Subscribe to `k1.planner.plan.ready.v1`, fire event via Bus, assert handler called | [ ] |
| W-16 | DeltaEmit events visible on Bus | emit via DeltaEmitAdapter, subscribe on Bus, assert received | [ ] |
| W-17 | Orchestrator processes TaskEnvelope E2E | enqueue -> mailbox -> process -> dag events emitted on Bus | [ ] |
| W-18 | Shutdown order correct (Orch before Fabric) | Stop orchestrator, stop fabric, stop session, close bus -- no errors | [ ] |
| W-19 | No Orchestrator circular imports | `python -c "from k1.orchestrator.factory import OrchestratorFactory"` succeeds | [ ] |
| W-20 | Orchestrator health ready after init | `orchestrator.health_ready() == True` after init() completes | [ ] |

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
