# End-to-End Kernel Wiring Requirements

**Source:** Synthesis from files 01-07 in this directory
**Date:** 2026-04-11
**Goal:** Everything needed to wire the K1 kernel from cold start to first user turn

---

## Table of Contents

1. [What "Wired" Means](#1-what-wired-means)
2. [Files That Must Exist Before Wiring](#2-files-that-must-exist-before-wiring)
3. [Files That Must Be Created](#3-files-that-must-be-created)
4. [Tier 1 Wiring — Shared Components (S1-S7)](#4-tier-1-wiring--shared-components)
5. [Tier 2 Wiring — Per-Session Components (P1-P7)](#5-tier-2-wiring--per-session-components)
6. [Cross-Wire Phase (S6b)](#6-cross-wire-phase)
7. [Shutdown Wiring](#7-shutdown-wiring)
8. [Adapter Build List (What to Code)](#8-adapter-build-list)
9. [Factory Pseudocode](#9-factory-pseudocode)
10. [Config Requirements](#10-config-requirements)
11. [Constructor Gotchas](#11-constructor-gotchas)
12. [Wiring Validation Checklist](#12-wiring-validation-checklist)
13. [Dependency Resolution Order](#13-dependency-resolution-order)
14. [Error Handling During Bootstrap](#14-error-handling-during-bootstrap)
15. [What Blocks V1 vs What Can Wait](#15-what-blocks-v1-vs-what-can-wait)

---

## 1. What "Wired" Means

The kernel is "wired end-to-end" when:

1. `KernelService.startup()` completes — all 6 shared components alive
2. `KernelService.create_session(device_id)` completes — all 5 per-session components alive
3. A user message enters via WebSocket → FSM processes → response exits via SSE
4. All 52 ports have production adapters (or null stubs for deferred features)
5. Shutdown reverses cleanly with no leaked resources

**Minimum viable wiring (V1):**

- 38/52 ports already have adapters
- 14 need new adapters (~465 lines total code)
- 3 ports can use null stubs (IK0SyncPort, IAdminPort, IKernelSSEPort)

---

## 2. Files That Must Exist Before Wiring

These are files that already exist in the codebase and are consumed during bootstrap. Each must be importable and functional.

### Bus

| File | What It Provides |
| --- | --- |
| `k1/bus/factory.py` | `BusFactory.create_local()`, `create_local_ordered()` |
| `k1/bus/local.py` | `LocalBus` implementation |
| `k1/bus/mailbox.py` | `LocalMailboxRouter`, `LocalMailbox` |
| `k1/bus/trie.py` | Topic matching engine |

### SessionState

| File | What It Provides |
| --- | --- |
| `k1/sessionstate/factory.py` | `SessionStateFactory.create_with_ports()`, `create_standalone()` |
| `k1/sessionstate/manager.py` | `SessionStateManager` (IS IStatePort) |
| `k1/sessionstate/sections/` | 12 section implementations |

### Fabric

| File | What It Provides |
| --- | --- |
| `k1/fabric/factory.py` | `FabricFactory.create_with_ports()` |
| `k1/fabric/fabric.py` | `CapabilityFabric` |
| `k1/fabric/ports.py` | 6 ABC port definitions |

### ModelHub

| File | What It Provides |
| --- | --- |
| `k1/model_hub/factory.py` | `ModelHubFactory.create_standalone()` |
| `k1/model_hub/service.py` | `ModelHub` service |
| `k1/model_hub/ports.py` | 7 port definitions |

### Orchestrator

| File | What It Provides |
| --- | --- |
| `k1/orchestrator/factory.py` | `OrchestratorFactory.create_production()` |
| `k1/orchestrator/service.py` | `OrchestratorService` |
| `k1/orchestrator/ports.py` | 9 port definitions |

### Planner

| File | What It Provides |
| --- | --- |
| `k1/planner/factory.py` | `PlannerFactory.create_production()` |
| `k1/planner/agent.py` | Planner agent |
| `k1/planner/ports.py` | 7 port definitions |

### Concierge (partial — monolith exists, hexagonal shell missing)

| File | What It Provides |
| --- | --- |
| `k1/concierge/kernel/bootstrap.py` | EXISTING monolith (~1150 lines) — to be replaced |
| `k1/concierge/fsm/` | FSM with 12 states |
| `k1/concierge/actors/` | Front/Back actors |
| `k1/concierge/tools/` | 16 tool implementations |

### Bridge (partial)

| File | What It Provides |
| --- | --- |
| `bridge/core/` | BridgeConfig, EnvelopeBuilder, Signing, HttpTransport |
| `bridge/kernel/command.py` | `IKernelCommandPort` + `HttpCommandAdapter` |
| `bridge/sync/outbox.py` | `LocalOutbox` |

---

## 3. Files That Must Be Created

### 3.1 Kernel Runtime (~700 lines across ~6 files)

| File | Purpose | Est. Lines |
| --- | --- | --- |
| `k1/kernel/__init__.py` | Package init | 5 |
| `k1/kernel/runtime.py` | `KernelRuntime` dataclass — holds all shared components | 50 |
| `k1/kernel/config.py` | `KernelConfig` + `ConfigLoader` | 100 |
| `k1/kernel/service.py` | `KernelService` — startup(), create_session(), shutdown() | 250 |
| `k1/kernel/session.py` | `SessionInstance` dataclass — per-session component bag | 40 |
| `k1/kernel/household.py` | `HouseholdProjection` + `hydrate_household()` | 60 |
| `k1/kernel/bootstrap.py` | 8-phase bootstrap orchestration (S1-S7 + error recovery) | 200 |

### 3.2 Concierge Hexagonal Shell (~950 lines across ~11 files)

| File | Purpose | Est. Lines |
| --- | --- | --- |
| `k1/concierge/ports.py` | 8 Protocol definitions (IInputPort through IMemoryPort) | 200 |
| `k1/concierge/factory.py` | `ConciergeFactory.create_with_ports()` | 400 |
| `k1/concierge/adapters/__init__.py` | Package | 5 |
| `k1/concierge/adapters/ws_input.py` | `WebSocketInputAdapter` (IInputPort) | 50 |
| `k1/concierge/adapters/sse_output.py` | `SSEOutputAdapter` (IOutputPort) | 50 |
| `k1/concierge/adapters/ultrabert.py` | `UltraBERTv4Adapter` (IClassificationPort) | 50 |
| `k1/concierge/adapters/model_gateway.py` | `ModelGatewayAdapter` (ILLMPort) | 80 |
| `k1/concierge/adapters/session_kernel.py` | `SessionKernelAdapter` (IStatePort) | 100 |
| `k1/concierge/adapters/fabric_orchestrator.py` | `FabricOrchestratorAdapter` (IDispatchPort) | 150 |
| `k1/concierge/adapters/delta_bus.py` | `DeltaBusAdapter` (IDeltaPort) | 80 |
| `k1/concierge/adapters/bridge_recall.py` | `BridgeRecallAdapter` (IMemoryPort) | 60 |
| `k1/concierge/adapters/test_adapters.py` | 8 test adapter classes | 200 |

### 3.3 Missing Adapters for Existing Components (~265 lines across ~8 files)

| File | Purpose | Est. Lines |
| --- | --- | --- |
| `k1/fabric/adapters/null_state.py` | `NullSessionStateReaderAdapter` | 10 |
| `k1/planner/adapters/snapshot_state.py` | `SnapshotStateReadAdapter` | 15 |
| `k1/fabric/adapters/model_gateway.py` | `ModelHubGatewayAdapter` (fix) | 30 |
| `k1/bus/middleware/tracing.py` | `TracingMiddleware` (session stamping fix) | 50 |
| `k1/sessionstate/adapters/session_bus.py` | `SessionBusAdapter` | 30 |
| `bridge/kernel/http_client.py` | `HttpBridgeClient` facade | 80 |
| `bridge/kernel/query.py` | `HttpQueryAdapter` (IKernelQueryPort) | 80 |
| `k1/model_hub/adapters/chat.py` | `ModelHubChatAdapter` (collision fix) | 25 |

### 3.4 Summary

| Category | Files | Lines |
| --- | --- | --- |
| Kernel Runtime | 7 | ~705 |
| Concierge Shell | 12 | ~1,425 |
| Missing Adapters | 8 | ~320 |
| **Total** | **27** | **~2,450** |

---

## 4. Tier 1 Wiring — Shared Components

### S1: Bus (Infrastructure Foundation)

```python
# WHAT: Create shared bus, router, and middleware
bus = BusFactory.create_local(backend="auto")  # "python" or "rust"
router = LocalMailboxRouter()
# Middleware for OTel tracing (stamps session_id, cognitive_trace_id)
tracing = TracingMiddleware(spans_enabled=config.otel_enabled)
bus.use(tracing)
```

**Produces:** `bus: IBus`, `router: IMailboxRouter`
**Consumed by:** Every other phase
**Failure mode:** FATAL — cannot proceed without bus

### S2: ModelHub (LLM Gateway)

```python
# WHAT: Create shared stateless LLM gateway with provider plugins
model_hub = await ModelHubFactory.create_standalone(
    config=config.model_hub,
    plugins={"openai": ..., "anthropic": ..., "google": ..., "vllm": ..., "ollama": ...}
)
await model_hub.connect()
```

**Produces:** `model_hub: ModelHub`
**Consumed by:** S3 (Fabric GW adapter), S6 (Planner LLM adapter), P4 (Concierge ILLMPort)
**Failure mode:** DEGRADED — kernel starts but LLM calls fail

### S3: Shared Fabric (NullStateReader)

```python
# WHAT: Create shared Fabric with no session state access
# WHY: Orchestrator and Planner are shared — cannot bind to one session

fabric_bus_adapter = FabricBusAdapter(bus)  # SINGLE instance, dual-role

shared_fabric = await FabricFactory.create_with_ports(
    state_reader=NullSessionStateReaderAdapter(),       # returns empty dict
    event_port=fabric_bus_adapter,                      # IEventPort
    delta_bus=fabric_bus_adapter,                        # IDeltaBusPort (SAME instance!)
    bridge=BridgeAdapter(bridge_client) if bridge_client else NullBridgeAdapter(),
    model_gateway=ModelHubGatewayAdapter(model_hub),
    prompt_system=PromptSystemAdapter()                  # test stub Phase 1
)
```

**Produces:** `shared_fabric: Fabric`
**Consumed by:** S5 (Orchestrator), S6 (Planner)
**GOTCHA:** `FabricBusAdapter` is ONE instance passed to TWO ports (IEventPort + IDeltaBusPort)
**Failure mode:** DEGRADED — capability registry scan may fail

### S4: Bridge (K0 Connection)

```python
# WHAT: Connect to K0 kernel (optional — can be None for offline mode)
try:
    bridge_client = await BridgeClient.connect(config.bridge)
except ConnectionError:
    bridge_client = None  # OFFLINE MODE — NullBridge adapters used everywhere
```

**Produces:** `bridge_client: BridgeClient | None`
**Consumed by:** S3 (Fabric bridge port), S5 (Orch bridge port), S6 (Planner bridge port), P4 (Concierge IMemoryPort), P5 (Household hydration)
**Failure mode:** NORMAL — offline is expected behavior

### S5: Orchestrator (Task Dispatch)

```python
# WHAT: Create shared orchestrator with 9 ports
# NOTE: Planner port starts as MockPlannerAdapter, hot-swapped in S6b

orch_mailbox = router.create_mailbox("orchestrator", config.orch_mailbox)

orchestrator = await OrchestratorFactory.create_production(
    mailbox=MailboxAdapter(orch_mailbox),
    fabric=FabricGatewayAdapter(shared_fabric),
    planner=MockPlannerAdapter(),                          # Phase 1 stub
    state=StateReadAdapter(NullSessionStateReaderAdapter()),
    delta=DeltaEmitAdapter(fabric_bus_adapter, fabric_bus_adapter),  # TWO args!
    bridge=BridgeWriteAdapter(bridge_client),
    event=EventSubscriptionAdapter(bus),
    storage=WorkflowStorageAdapter(SQLiteWorkflowAdapter(config.workflow_db)),
    config=OrchestratorConfig(...)
)
```

**Produces:** `orchestrator: OrchestratorService`
**Consumed by:** S6b (cross-wire), P4 (Concierge IDispatchPort)
**GOTCHA:** `DeltaEmitAdapter(event_port, delta_bus)` takes TWO args, not one
**Failure mode:** FATAL — orchestrator required for MED/HIGH dispatch

### S6: Planner (Planning Engine)

```python
# WHAT: Create shared planner with 7 ports + start as background task

planner_mailbox = router.create_mailbox("planner", config.planner_mailbox)

planner = await PlannerFactory.create_production(
    llm=LLMGatewayAdapter(model_hub),
    fabric=FabricRetrievalAdapter(shared_fabric),
    state=SnapshotStateReadAdapter(reader=None, session_id=None),  # pre-bound later
    bridge=BridgeAdapter(bridge_client),
    delta=DeltaBusAdapter(bus, agent_id_stamp="planner"),
    event=EventBusAdapter(bus),                                    # different from delta!
    mailbox=MailboxAdapter(planner_mailbox),
    config=PlannerConfig(...)
)

planner_task = asyncio.create_task(planner.start())
```

**Produces:** `planner: Planner`, `planner_task: asyncio.Task`
**Consumed by:** S6b (cross-wire)
**GOTCHA:** `EventBusAdapter` ≠ `DeltaBusAdapter` — two separate bus adapters for different Fabric interfaces
**Failure mode:** DEGRADED — CB_PLANNER opens, HIGH tasks skip planning

### S7: Return KernelRuntime

```python
runtime = KernelRuntime(
    bus=bus,
    router=router,
    model_hub=model_hub,
    fabric_shared=shared_fabric,
    bridge=bridge_client,
    orchestrator=orchestrator,
    planner=planner,
    config=config
)
```

---

## 5. Tier 2 Wiring — Per-Session Components

### P1: Per-Session Bus

```python
# WHAT: Create isolated bus for this session only
session_bus = BusFactory.create_local_ordered()
session_tracing = TracingMiddleware(spans_enabled=True)
session_bus.use(session_tracing)
```

**Produces:** `session_bus: IBus`
**GOTCHA:** Per-session bus is independent — no cross-session topic interference

### P2: SessionState

```python
# WHAT: Create per-session state manager with 5 ports
# NOTE: SessionStateManager IS IStatePort — no wrapper needed (SIM-D-17)

session_state = await SessionStateFactory.create_with_ports(
    storage=SQLiteStorageAdapter(db_path=f"{config.ss_dir}/{session_id}.db"),
    events=SessionBusAdapter(session_bus),        # wires SS events to session bus
    writer=DirectWriterAdapter(),
    lifecycle=StandaloneLifecycle(checkpoint_interval_ms=config.checkpoint_ms),
    k0_sync=NullSyncPort()                        # Phase 1: no K0 sync
)
```

**Produces:** `session_state: SessionStateManager` (this IS IStatePort)
**GOTCHA:** Pass `session_state` directly as IStatePort — do NOT wrap it

### P3: Per-Session Fabric

```python
# WHAT: Create per-session Fabric with real SSM access
# WHY: Concierge needs capability execution with session state context

session_fabric_bus = FabricBusAdapter(session_bus)  # per-session bus adapter

session_fabric = await FabricFactory.create_with_ports(
    state_reader=SessionStateReaderAdapter(session_state, session_id),  # TWO args!
    event_port=session_fabric_bus,                    # per-session bus
    delta_bus=session_fabric_bus,                      # SAME instance (dual-role)
    bridge=BridgeAdapter(runtime.bridge) if runtime.bridge else NullBridgeAdapter(),
    model_gateway=ModelHubGatewayAdapter(runtime.model_hub),
    prompt_system=PromptSystemAdapter()
)
```

**Produces:** `session_fabric: Fabric`
**GOTCHA:** `SessionStateReaderAdapter(session_state, session_id)` takes TWO args — binds to one session permanently

### P4: Concierge

```python
# WHAT: Create per-session Concierge with 8 hexagonal ports injected

concierge = await ConciergeFactory.create_with_ports(
    input_port=WebSocketInputAdapter(ws_url, auth_handler),
    output_port=SSEOutputAdapter(sse_endpoint, heartbeat_ms=30000),
    classification_port=UltraBERTv4Adapter(model_path, tokenizer),
    llm_port=ModelGatewayAdapter(runtime.model_hub),
    state_port=session_state,                                         # direct SSM, no wrapper
    dispatch_port=FabricOrchestratorAdapter(
        fabric=session_fabric,
        orchestrator=runtime.orchestrator,
        tier_router=TierRouter(config.tier_thresholds)
    ),
    delta_port=DeltaBusAdapter(session_bus, agent_id="concierge"),
    memory_port=BridgeRecallAdapter(runtime.bridge) if runtime.bridge else NullMemoryAdapter(),
    config=ConciergeConfig(...)
)

concierge_task = asyncio.create_task(concierge.start())
```

**Produces:** `concierge: Concierge`, `concierge_task: asyncio.Task`
**GOTCHA:** `state_port=session_state` — NOT `SessionKernelAdapter(session_state)`. SSM IS the port.
**GOTCHA:** ConciergeController takes (bus, router) in constructor, then 9 late-wired setters for subsystems

### P5: Household Hydration

```python
# WHAT: Fetch family model from K0 (or fallback to local cache)

if runtime.bridge:
    try:
        household = await runtime.bridge.query("household.projection.v1")
    except (TimeoutError, ConnectionError):
        household = await HouseholdProjection.load_from_cache(session_id)
else:
    household = await HouseholdProjection.load_from_cache(session_id)
```

**Produces:** `household: HouseholdProjection`
**NOTE:** Frozen in-memory, NOT in SessionState. Per-turn access = 0ms.

### P6: Start Lifecycle

```python
await session_state.start()    # starts checkpoint timer
```

### P7: Register Session

```python
session = SessionInstance(
    session_id=session_id,
    member_id=member_id,
    bus=session_bus,
    state=session_state,
    fabric=session_fabric,
    concierge=concierge,
    household=household,
    concierge_task=concierge_task,
    created_at=datetime.utcnow()
)
runtime.sessions[session_id] = session
```

---

## 6. Cross-Wire Phase

### S6b: Orchestrator ↔ Planner Hot-Swap

This must happen AFTER S5 (Orchestrator created) and S6 (Planner started).

```python
# WHAT: Replace MockPlannerAdapter with real PlannerAdapter
# WHY: Orchestrator was created with stub because Planner didn't exist yet

planner_mailbox = planner.get_mailbox()
cb_planner = CircuitBreaker("CB_PLANNER", config.circuit_breakers.planner)

orchestrator._planner_port = PlannerAdapter(
    mailbox=planner_mailbox,
    circuit_breaker=cb_planner
)
```

**Effect:** HIGH-tier TaskEnvelopes now route from Orchestrator → Planner via real mailbox.
**Before S6b:** HIGH-tier tasks get mock/empty plan responses.
**After S6b:** Full planning pipeline active.

---

## 7. Shutdown Wiring

### Per-Session Shutdown (reverse of P1-P7)

```python
async def destroy_session(session_id: str):
    session = runtime.sessions.pop(session_id)

    # P7: Unregister
    # P6: Stop lifecycle
    await session.state.stop()

    # P4: Stop concierge
    await session.concierge.stop()
    session.concierge_task.cancel()

    # P3: Shutdown per-session fabric
    await session.fabric.shutdown()

    # P2: (SSM stopped in P6)

    # P1: Close per-session bus
    session.bus.close()
```

### Startup Shutdown (after all sessions destroyed)

```python
async def shutdown():
    # Destroy all sessions first
    for sid in list(runtime.sessions):
        await destroy_session(sid)

    # S6: Stop planner
    await planner.stop()
    planner_task.cancel()

    # S5: Shutdown orchestrator
    await orchestrator.shutdown()

    # S4: Close bridge
    if bridge_client:
        await bridge_client.close()

    # S3: Shutdown shared fabric
    await shared_fabric.shutdown()

    # S2: Close model hub
    await model_hub.close()

    # S1: Close bus (LAST — everything depends on it)
    router.close()
    bus.close()
```

**Rule:** Bus created FIRST, closed LAST. Reverse order for everything else.

---

## 8. Adapter Build List

### P0 — Required for V1 Bootstrap (Sprint 1)

| # | Adapter | Port | Lines | Why Blocking |
| --- | --- | --- | --- | --- |
| 1 | `NullSessionStateReaderAdapter` | ISessionStateReader | 10 | Shared Fabric cannot start without it |
| 2 | `SnapshotStateReadAdapter` | IStatePort (Planner) | 15 | Planner reads pre-bound snapshots, not live SSM |
| 3 | `ModelHubGatewayAdapter` | IModelGatewayPort | 30 | Fabric capability execution needs LLM handles |
| 4 | `TracingMiddleware` (fix) | Bus middleware | 50 | Session/trace stamping for observability |
| 5 | `ConciergeFactory.create_with_ports()` | (factory) | 400 | Entire Concierge hexagonal shell |
| 6 | 8× Concierge port Protocols | IInputPort..IMemoryPort | 200 | Port definitions for type checking |

**Total P0:** ~705 lines → unblocks startup + session creation

### P1 — Required for K0 Integration (Sprint 2)

| # | Adapter | Port | Lines | Why Blocking |
| --- | --- | --- | --- | --- |
| 7 | `HttpBridgeClient` facade | IBridgeClient | 80 | K0 command/query/SSE routing |
| 8 | `HttpQueryAdapter` | IKernelQueryPort | 80 | K0 queries (household, recall) |
| 9 | `BridgeRecallAdapter` | IMemoryPort | 40 | recall_memory tool |
| 10 | `SessionBusAdapter` | IEventPort (SS) | 30 | SS events to session bus |
| 11 | `ModelHubChatAdapter` | IModelHubPort (collision) | 25 | Memory Writer LLM calls |
| 12 | `HouseholdProjection` | (container) | 60 | Family context at boot |

**Total P1:** ~315 lines → unblocks K0 recall, household hydration

### P2 — Deferred (Sprint 3)

| # | Adapter | Port | Lines | Why Deferred |
| --- | --- | --- | --- | --- |
| 13 | `NullDeltaBusAdapter` | IDeltaBusPort | 10 | Degradation fallback |
| 14 | `NullEventPortAdapter` | IEventPort | 10 | Degradation fallback |
| 15 | `FabricConnectionAdapter` | (pooling) | 40 | Performance optimization |
| 16 | `SSEBridgeAdapter` | IKernelSSEPort | 100 | K0 streaming events |
| 17 | 8× Concierge production adapters | C-1..C-8 | 620 | Full WebSocket/SSE/UltraBERT |

**Total P2:** ~780 lines → full production adapters

### Concierge Production Adapters Detail (P2)

| Adapter | File | Lines | Notes |
| --- | --- | --- | --- |
| `WebSocketInputAdapter` | ws_input.py | 50 | Wraps WS server, implements receive() |
| `SSEOutputAdapter` | sse_output.py | 50 | Wraps SSE stream, polymorphic send() |
| `UltraBERTv4Adapter` | ultrabert.py | 50 | Wraps UltraBERT model for classify() |
| `ModelGatewayAdapter` | model_gateway.py | 80 | Wraps ModelHub for execute()/stream_execute() |
| `SessionKernelAdapter` | session_kernel.py | 100 | Wraps SSM for read()/write() |
| `FabricOrchestratorAdapter` | fabric_orchestrator.py | 150 | Routes LOW→Fabric, MED/HIGH→Orch |
| `DeltaBusAdapter` | delta_bus.py | 80 | Wraps session bus, pre-stamps agent_id |
| `BridgeRecallAdapter` | bridge_recall.py | 60 | Wraps BridgeClient for recall() |

---

## 9. Factory Pseudocode

### KernelService — Complete Bootstrap

```python
class KernelService:
    async def startup(self, config: KernelConfig) -> KernelRuntime:
        """Tier 1: Create all shared components."""

        # S1: Bus
        bus = BusFactory.create_local(backend=config.bus_backend)
        router = LocalMailboxRouter()
        bus.use(TracingMiddleware(spans_enabled=config.otel_enabled))

        # S2: ModelHub
        model_hub = await ModelHubFactory.create_standalone(config.model_hub)
        await model_hub.connect()

        # S4: Bridge (before S3 because S3 may use it)
        bridge = None
        try:
            bridge = await BridgeClient.connect(config.bridge)
        except ConnectionError:
            pass  # OFFLINE — normal

        # S3: Shared Fabric
        fabric_bus = FabricBusAdapter(bus)
        shared_fabric = await FabricFactory.create_with_ports(
            state_reader=NullSessionStateReaderAdapter(),
            event_port=fabric_bus,
            delta_bus=fabric_bus,
            bridge=BridgeAdapter(bridge) if bridge else NullBridgeAdapter(),
            model_gateway=ModelHubGatewayAdapter(model_hub),
            prompt_system=PromptSystemAdapter()
        )

        # S5: Orchestrator
        orch_mailbox = router.create_mailbox("orchestrator")
        orchestrator = await OrchestratorFactory.create_production(
            mailbox=MailboxAdapter(orch_mailbox),
            fabric=FabricGatewayAdapter(shared_fabric),
            planner=MockPlannerAdapter(),
            state=StateReadAdapter(NullSessionStateReaderAdapter()),
            delta=DeltaEmitAdapter(fabric_bus, fabric_bus),
            bridge=BridgeWriteAdapter(bridge),
            event=EventSubscriptionAdapter(bus),
            storage=WorkflowStorageAdapter(SQLiteWorkflowAdapter(config.workflow_db)),
            config=OrchestratorConfig.from_kernel_config(config)
        )

        # S6: Planner
        planner_mailbox = router.create_mailbox("planner")
        planner = await PlannerFactory.create_production(
            llm=LLMGatewayAdapter(model_hub),
            fabric=FabricRetrievalAdapter(shared_fabric),
            state=SnapshotStateReadAdapter(reader=None, session_id=None),
            bridge=BridgeAdapter(bridge) if bridge else NullBridgeAdapter(),
            delta=DeltaBusAdapter(bus, agent_id_stamp="planner"),
            event=EventBusAdapter(bus),
            mailbox=MailboxAdapter(planner_mailbox),
            config=PlannerConfig.from_kernel_config(config)
        )
        planner_task = asyncio.create_task(planner.start())

        # S6b: Cross-wire
        cb_planner = CircuitBreaker("CB_PLANNER", config.circuit_breakers["planner"])
        orchestrator._planner_port = PlannerAdapter(
            mailbox=planner.get_mailbox(),
            circuit_breaker=cb_planner
        )

        # S7: Return runtime
        return KernelRuntime(
            bus=bus, router=router, model_hub=model_hub,
            fabric_shared=shared_fabric, bridge=bridge,
            orchestrator=orchestrator, planner=planner,
            planner_task=planner_task, config=config
        )

    async def create_session(self, runtime: KernelRuntime, device_id: str) -> SessionInstance:
        """Tier 2: Create per-session components."""

        session_id = generate_session_id()
        member_id = await resolve_member(device_id, runtime.bridge)

        # P1: Per-session Bus
        session_bus = BusFactory.create_local_ordered()
        session_bus.use(TracingMiddleware(spans_enabled=True))

        # P2: SessionState
        session_state = await SessionStateFactory.create_with_ports(
            storage=SQLiteStorageAdapter(f"{runtime.config.ss_dir}/{session_id}.db"),
            events=SessionBusAdapter(session_bus),
            writer=DirectWriterAdapter(),
            lifecycle=StandaloneLifecycle(runtime.config.checkpoint_ms),
            k0_sync=NullSyncPort()
        )

        # P3: Per-session Fabric
        sfb = FabricBusAdapter(session_bus)
        session_fabric = await FabricFactory.create_with_ports(
            state_reader=SessionStateReaderAdapter(session_state, session_id),
            event_port=sfb,
            delta_bus=sfb,
            bridge=BridgeAdapter(runtime.bridge) if runtime.bridge else NullBridgeAdapter(),
            model_gateway=ModelHubGatewayAdapter(runtime.model_hub),
            prompt_system=PromptSystemAdapter()
        )

        # P4: Concierge
        concierge = await ConciergeFactory.create_with_ports(
            input_port=WebSocketInputAdapter(runtime.config.ws_url),
            output_port=SSEOutputAdapter(runtime.config.sse_url),
            classification_port=UltraBERTv4Adapter(runtime.config.ultrabert_path),
            llm_port=ModelGatewayAdapter(runtime.model_hub),
            state_port=session_state,       # SSM IS IStatePort — no wrapper
            dispatch_port=FabricOrchestratorAdapter(session_fabric, runtime.orchestrator),
            delta_port=DeltaBusAdapter(session_bus, agent_id="concierge"),
            memory_port=BridgeRecallAdapter(runtime.bridge) if runtime.bridge else NullMemoryAdapter(),
            config=ConciergeConfig.from_kernel_config(runtime.config)
        )
        concierge_task = asyncio.create_task(concierge.start())

        # P5: Household
        household = await hydrate_household(runtime.bridge, session_id)

        # P6: Start lifecycle
        await session_state.start()

        # P7: Register
        session = SessionInstance(
            session_id=session_id,
            member_id=member_id,
            bus=session_bus,
            state=session_state,
            fabric=session_fabric,
            concierge=concierge,
            household=household,
            concierge_task=concierge_task
        )
        runtime.sessions[session_id] = session
        return session
```

---

## 10. Config Requirements

### KernelConfig Fields

```python
@dataclass(frozen=True)
class KernelConfig:
    # Bus
    bus_backend: str = "auto"            # "python" | "rust" | "auto"
    otel_enabled: bool = True

    # ModelHub
    model_hub: ModelHubConfig            # plugins, API keys, routing rules

    # Bridge
    bridge: BridgeConfig                 # K0 endpoint, API key, timeout

    # SessionState
    ss_dir: str = "./data/sessions"      # SQLite storage dir
    checkpoint_ms: int = 50              # Checkpoint interval SLA

    # Fabric
    # (uses shared ModelHub, Bridge, Bus — no extra config)

    # Orchestrator
    workflow_db: str = "./data/workflows.db"
    orch_config: OrchestratorConfig      # 32 fields

    # Planner
    planner_config: PlannerConfig        # bounds validation

    # Circuit Breakers
    circuit_breakers: dict[str, CBConfig]  # CB_SSE, CB_MODEL, CB_SESSIONSTATE, CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC, CB_MCP

    # Concierge
    ws_url: str
    sse_url: str
    ultrabert_path: str
    concierge_config: ConciergeConfig    # frozen dataclass

    # Session Management
    max_sessions: int = 100
    idle_timeout_minutes: int = 30
```

---

## 11. Constructor Gotchas

These are the constructor signatures that are surprising or error-prone:

| Component | Gotcha | Correct Call |
| --- | --- | --- |
| `SessionStateReaderAdapter` | Takes TWO args | `SessionStateReaderAdapter(ssm, session_id)` not just `(ssm)` |
| `DeltaEmitAdapter` | Takes TWO args | `DeltaEmitAdapter(event_port, delta_bus)` not just `(event_port)` |
| `FabricBusAdapter` | Single instance, dual-role | Pass SAME instance to both `event_port=` and `delta_bus=` |
| `DeltaBusAdapter` (Planner) | Pre-stamps agent_id | `DeltaBusAdapter(bus, agent_id_stamp="planner")` |
| `EventBusAdapter` vs `DeltaBusAdapter` | Different adapters! | Planner uses BOTH — one for events, one for deltas |
| `SessionStateManager` | IS IStatePort | Pass directly — do NOT wrap in adapter |
| `ConciergeController` | 9 late-wired setters | Constructor takes (bus, router), rest set via setters post-creation |
| `ExperienceLayer` | ZERO parameters | Fully hardcoded internal — no injection |
| `AdminHttpAdapter` | Post-injected | `orchestrator._admin = AdminHttpAdapter(...)` — not in constructor |
| `ExecutionMonitor` | Circular reference | `monitor._service_ref = orchestrator` — post-constructed |
| `WorkflowStorageAdapter` | Wraps another adapter | `WorkflowStorageAdapter(SQLiteWorkflowAdapter)` — not raw db_path |
| `Fabric` itself | IS IFabricPort | Pass directly to consumers — no wrapper needed |
| `SnapshotStateReadAdapter` | Pre-bound snapshot | Reads from `PlanRequest.context`, NOT live SSM |
| `MockPlannerAdapter` | Replaced at S6b | `orchestrator._planner_port` mutated after construction |

---

## 12. Wiring Validation Checklist

### At Startup Complete (S7)

- [ ] `bus.publish()` does not throw
- [ ] `router.create_mailbox()` returns valid mailbox
- [ ] `model_hub.execute(test_request)` returns response (or CB opens)
- [ ] `shared_fabric.dispatch_direct(test_cap)` returns result (or CB opens)
- [ ] `bridge.is_available()` returns True/False (not exception)
- [ ] `orchestrator.health_check()` returns OK
- [ ] `planner` background task is running
- [ ] `orchestrator._planner_port` is PlannerAdapter (not MockPlannerAdapter)

### At Session Create Complete (P7)

- [ ] `session_bus.publish()` isolated from shared bus
- [ ] `session_state.read(["control"])` returns valid Snapshot
- [ ] `session_state.write("control", "set", {...})` succeeds
- [ ] `session_fabric` can dispatch LOW-tier capability
- [ ] `concierge.start()` transitions FSM to LISTENING
- [ ] All 8 Concierge ports satisfy `isinstance` / `runtime_checkable` Protocol
- [ ] `household` is populated (even if from cache)

### Integration Smoke Test

- [ ] User message → FSM LISTENING→DISPATCHING
- [ ] Classification returns tier + domain + safety
- [ ] LOW tier → session_fabric.dispatch_direct() → result
- [ ] LLM call → ModelHub.execute() → response
- [ ] Response → SSE stream → client
- [ ] Delta aggregation → bus event → state update
- [ ] FSM → LISTENING (turn complete)

---

## 13. Dependency Resolution Order

### Clean DAG — No Circular Dependencies

```
Layer 0 (Leaf — no dependencies):
  Config, Bus, TracingMiddleware

Layer 1 (needs Layer 0):
  ModelHub (needs Config)
  Bridge (needs Config)

Layer 2 (needs Layer 1):
  Shared Fabric (needs Bus, ModelHub, Bridge)

Layer 3 (needs Layer 2):
  Orchestrator (needs Shared Fabric, Bus, Bridge)
  Planner (needs Shared Fabric, Bus, ModelHub, Bridge)

Layer 4 (needs Layer 3):
  Cross-wire S6b (needs Orchestrator, Planner)

--- Per-session boundary ---

Layer 5 (session leaf):
  Session Bus

Layer 6 (needs Layer 5):
  SessionState (needs Session Bus)

Layer 7 (needs Layer 6):
  Session Fabric (needs Session Bus, SessionState, shared ModelHub, shared Bridge)

Layer 8 (needs Layer 7):
  Concierge (needs Session Bus, SessionState, Session Fabric, shared Orchestrator, shared ModelHub, shared Bridge)

Layer 9 (needs Layer 8):
  Household hydration (needs Bridge, Concierge context)
  Lifecycle start (needs SessionState)
  Session registration (needs all above)
```

**Rule:** Never create a component before its dependencies exist. The layer numbering guarantees this.

---

## 14. Error Handling During Bootstrap

### Phase Failure Recovery

| Phase | Failure | Recovery Strategy |
| --- | --- | --- |
| S1: Bus | Cannot create | **FATAL** — abort kernel start |
| S2: ModelHub | Plugin load fails | **DEGRADED** — continue, LLM calls will fail |
| S3: Shared Fabric | Registry scan fails | **DEGRADED** — continue, capabilities incomplete |
| S4: Bridge | K0 unreachable | **NORMAL** — offline mode expected |
| S5: Orchestrator | Factory fails | **FATAL** — abort kernel start |
| S6: Planner | Factory fails | **DEGRADED** — CB_PLANNER opens, HIGH tasks skip planning |
| S6b: Cross-wire | Planner mailbox unavailable | **DEGRADED** — keep MockPlannerAdapter |
| P1: Session Bus | Cannot create | **SESSION FATAL** — abort session, don't affect kernel |
| P2: SessionState | SQLite init fails | **SESSION FATAL** — abort session |
| P3: Session Fabric | Factory fails | **SESSION FATAL** — abort session |
| P4: Concierge | Factory fails | **SESSION FATAL** — abort session |
| P5: Household | Query fails | **DEGRADED** — use LOCAL COLD cache |
| P6: Lifecycle | Start fails | **DEGRADED** — no checkpointing |

### Session Failure Does NOT Crash Kernel

```python
async def create_session(self, device_id):
    try:
        return await self._create_session_inner(device_id)
    except Exception as e:
        # Cleanup any partially-created resources
        await self._cleanup_partial_session(session_id)
        raise SessionCreationError(session_id, e) from e
```

### Tier Degradation Cascade at Runtime

```
HIGH → CB_PLANNER open → degrade to MED
MED  → CB_ORCHESTRATOR open → degrade to LOW
LOW  → CB_FABRIC open → canned response
ALL  → CB_MODEL open → canned response (last resort)
```

---

## 15. What Blocks V1 vs What Can Wait

### BLOCKS V1 (Must be done before first user turn)

| Item | Why | Lines |
| --- | --- | --- |
| `KernelService.startup()` | No kernel = nothing works | 250 |
| `KernelService.create_session()` | No session = no user interaction | 200 |
| `KernelRuntime` dataclass | Holds shared components | 50 |
| `SessionInstance` dataclass | Holds per-session components | 40 |
| `KernelConfig` + `ConfigLoader` | Config needed by every phase | 100 |
| `k1/concierge/ports.py` (8 Protocols) | Type definitions for factory | 200 |
| `ConciergeFactory.create_with_ports()` | Replaces monolith bootstrap | 400 |
| `NullSessionStateReaderAdapter` | Shared Fabric needs it | 10 |
| `SnapshotStateReadAdapter` | Planner needs it | 15 |
| `TracingMiddleware` fix | Session stamping | 50 |

**V1 Total:** ~1,315 lines across ~10 files

### V1 WITH TEST ADAPTERS (use stubs for production adapters)

For V1, Concierge production adapters can be test stubs:

```python
concierge = await ConciergeFactory.create_with_ports(
    input_port=TestInputAdapter(),          # stub
    output_port=TestOutputAdapter(),        # stub
    classification_port=MockClassificationAdapter(),  # returns LOW tier
    llm_port=TestLLMAdapter(),              # returns canned response
    state_port=session_state,               # REAL SSM
    dispatch_port=FabricOrchestratorAdapter(session_fabric, orchestrator),  # REAL
    delta_port=DeltaBusAdapter(session_bus, "concierge"),  # REAL
    memory_port=TestMemoryAdapter(),        # returns empty
    config=ConciergeConfig.testing()
)
```

This proves the wiring works without building all 8 production adapters.

### CAN WAIT FOR V2

| Item | Why It Can Wait | Lines |
| --- | --- | --- |
| 8× production Concierge adapters | Test stubs work for V1 | 620 |
| `HttpBridgeClient` facade | NullBridgeAdapter for V1 | 80 |
| `HttpQueryAdapter` | K0 queries deferred | 80 |
| `SSEBridgeAdapter` | K0 SSE deferred | 100 |
| `ModelHubChatAdapter` | Memory Writer can construct HubRequest manually | 25 |
| `HouseholdProjection` | Cache fallback for V1 | 60 |
| `SessionBusAdapter` | LocalEventAdapter works for V1 | 30 |
| Null fallback adapters | Not needed until degradation testing | 20 |

**V2 Total:** ~1,015 lines — can be done after V1 proves wiring

---

## Summary

### What Must Happen (Ordered)

1. **Create `k1/kernel/` package** — KernelRuntime, KernelConfig, KernelService, SessionInstance
2. **Create `k1/concierge/ports.py`** — 8 Protocol definitions
3. **Create `ConciergeFactory.create_with_ports()`** — replaces monolith bootstrap.py
4. **Create `NullSessionStateReaderAdapter`** — 10 lines, unblocks shared Fabric
5. **Create `SnapshotStateReadAdapter`** — 15 lines, unblocks Planner
6. **Fix `TracingMiddleware`** — session/trace stamping
7. **Wire `KernelService.startup()`** — S1 through S7 in order
8. **Wire `KernelService.create_session()`** — P1 through P7 in order
9. **Wire `KernelService.shutdown()`** — reverse order
10. **Integration test** — user message → response via test adapters

### Key Numbers

| Metric | Value |
| --- | --- |
| Total ports | 52 (48 mandatory + 4 optional) |
| Already wired | 38 (63%) |
| Need new adapters | 14 |
| V1 code to write | ~1,315 lines |
| V2 code to write | ~1,015 lines |
| Files to create | 27 |
| Circular dependencies | 0 (clean DAG) |
| Architectural blockers | 0 |
