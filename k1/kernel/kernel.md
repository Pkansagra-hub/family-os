# K1 Kernel Wiring Specification

Status: PLANNING -- fill as implementation proceeds.

---

## 1. Purpose

This document is the single reference for wiring Fabric, Bus, and SessionState
into a unified K1 kernel runtime.  Each component is self-contained with
hexagonal ports.  The kernel bootstrap creates shared infrastructure (Bus,
MailboxRouter) and injects real adapters into each component's factory.

---

## 2. Component Inventory

| Component | Factory | Ports (count) | Standalone Adapters | Bus Adapter |
|-----------|---------|---------------|---------------------|-------------|
| Bus | `BusFactory.create_local()` | 3 (IBus, IMailbox, IMailboxRouter) | n/a (IS the infrastructure) | n/a |
| Fabric | `FabricFactory.create_with_ports()` | 6 | Test stubs for all 6 | `FabricBusAdapter` |
| SessionState | `SessionStateFactory.create_with_ports()` | 5 (4 mandatory + 1 optional) | Local/in-memory for all | `SessionBusAdapter` |
| Orchestrator | `OrchestratorFactory.create_production()` | 8 (IMailboxPort, IFabricGatewayPort, IPlannerPort, IStateReadPort, IDeltaEmitPort, IBridgeWritePort, IEventSubscriptionPort, IWorkflowStoragePort) | Test adapters for all 8 (6.1.8-6.1.16) | Reuses `FabricBusAdapter` via EventSubscriptionAdapter + DeltaEmitAdapter |
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
  |     mailbox:       MailboxAdapter(config.mailbox_depth)        <-- standalone, no external dep
  |     planner:       PlannerAdapter(planner_mailbox, cb_planner) <-- requires Planner module
  |     bridge_write:  BridgeWriteAdapter(bridge_client)           <-- requires Bridge connector
  |     workflow_store: WorkflowStorageAdapter(config.db_path)     <-- standalone SQLite
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

### 4.3 Orchestrator Ports (8 total)

| Port | Protocol | Wired Adapter | Source Module | Notes |
|------|----------|---------------|---------------|-------|
| `IMailboxPort` | `Protocol` (structural) | `MailboxAdapter(config.mailbox_depth)` | `k1.orchestrator.adapters.mailbox_adapter` | Standalone in-process WFQ priority queue. No external dep. |
| `IFabricGatewayPort` | `Protocol` (structural) | `FabricGatewayAdapter(fabric)` | `k1.orchestrator.adapters.fabric_gateway_adapter` | Wraps Fabric facade from Phase 3. execute() -> Fabric.execute(). No CB (Concierge owns CB_FABRIC). |
| `IPlannerPort` | `Protocol` (structural) | `PlannerAdapter(planner_mailbox, cb_planner)` | `k1.orchestrator.adapters.planner_adapter` | Orchestrator owns CB_PLANNER. Requires Planner module mailbox (Phase 5 wiring). |
| `IStateReadPort` | `Protocol` (structural) | `StateReadAdapter(state_reader)` | `k1.orchestrator.adapters.state_read_adapter` | Wraps same SessionStateReaderAdapter used by Fabric. Read-only (ORCH-01). |
| `IDeltaEmitPort` | `Protocol` (structural) | `DeltaEmitAdapter(event_port, delta_bus)` | `k1.orchestrator.adapters.delta_emit_adapter` | Dual-publish: event_port for internal events + delta_bus for user-facing deltas. Reuses FabricBusAdapter instances from Phase 3. Fire-and-forget, never raises. |
| `IBridgeWritePort` | `Protocol` (structural) | `BridgeWriteAdapter(bridge_client)` | `k1.orchestrator.adapters.bridge_write_adapter` | Phase 1: TestBridgeAdapter (fire-and-forget stubs). Phase 2: real Bridge connector. Write methods never raise; only read_wal() surfaces errors. |
| `IEventSubscriptionPort` | `Protocol` (structural) | `EventSubscriptionAdapter(event_port)` | `k1.orchestrator.adapters.event_subscription_adapter` | Wraps FabricBusAdapter IEventPort from Phase 3. subscribe/unsubscribe/emit. Tracks handles for bulk cleanup at shutdown. |
| `IWorkflowStoragePort` | `Protocol` (structural) | `WorkflowStorageAdapter(config.db_path)` | `k1.orchestrator.adapters.workflow_storage_adapter` | Standalone SQLite. Wraps SQLiteWorkflowAdapter. No external dep beyond local filesystem. |

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
from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter

orch_config = OrchestratorConfig.from_env()
orchestrator = await OrchestratorFactory.create_with_ports(
    mailbox=MailboxAdapter(orch_config.mailbox_depth),
    fabric_gateway=FabricGatewayAdapter(fabric),           # reuse Fabric from Phase 3
    planner=None,                                           # Phase 5: wired when Planner ready
    state_read=StateReadAdapter(state_reader),              # reuse state_reader from Phase 3
    delta_emit=DeltaEmitAdapter(fabric_bus, fabric_bus),    # reuse bus adapters from Phase 3
    bridge_write=BridgeWriteAdapter(TestBridgeAdapter()),   # Phase 1 stub
    event_subscription=EventSubscriptionAdapter(fabric_bus), # reuse FabricBusAdapter
    workflow_storage=WorkflowStorageAdapter(orch_config.workflow_db_path),
)
await orchestrator.init()

# Phase 5: Start lifecycle
session_manager.start()

# Phase 6: Expose kernel API
return KernelRuntime(bus=bus, mailbox_router=mailbox_router,
                     session=session_manager, fabric=fabric,
                     orchestrator=orchestrator)
```

---

## 8. Shutdown Sequence

```
1. orchestrator.shutdown()    -- drain active DAG (30s), persist trigger states
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
| W-08 | Shutdown order correct | Stop fabric, stop session, close bus -- no errors | [ ] |
| W-09 | No circular imports | `python -c "from k1.kernel.bootstrap import KernelRuntime"` succeeds | [ ] |
| W-10 | All 172 Rust + 1005 Python bus tests still pass | `cargo test` + `pytest tests/k1/bus/` | [ ] |
| W-11 | Orchestrator factory completes < 500ms | `time OrchestratorFactory.create_production(config)` | [ ] |
| W-12 | All 8 Orchestrator ports injected | All ports non-None after factory construction | [ ] |
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
| Orchestrator ports | `k1/orchestrator/ports/*.py` (8 files) |
| Orchestrator adapters | `k1/orchestrator/adapters/*.py` (8 files) |
| Orchestrator services | `k1/orchestrator/orchestration/*.py` |
| DAGExecutor | `k1/orchestrator/orchestration/dag_executor.py` |
| StepRunner | `k1/orchestrator/orchestration/step_runner.py` |
| Kernel bootstrap (TODO) | `k1/kernel/bootstrap.py` |
| This document | `k1/kernel/kernel.md` |
