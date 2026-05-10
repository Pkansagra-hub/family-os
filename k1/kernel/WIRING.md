# K1 Kernel — WIRING

This document traces every constructor call, every adapter instantiation, and every
dependency injection performed by `KernelService`. It covers both the shared Tier 1
startup (S1–S7+S6b) and the per-session Tier 2 creation sequence (P1–P6).

---

## Tier 1 — Shared startup (`_startup_tier1`)

### S1 — Bus + Router

```python
self._bus = BusFactory.create_local_ordered(
    capture=config.capture_bus,
    outbox=BusOutbox(config.bus_outbox_path) if config.bus_outbox_path else None,
    durable_topics=set(config.bus_durable_topics) or None,
)
self._async_bus = AsyncBusBridge(self._bus)
self._router   = BusFactory.create_mailbox_router()
```

Backend selection: `K1_BUS_BACKEND` env var. `"auto"` = Rust (`k1_bus_core`) if importable,
else Python `LocalBus`. `"rust"` / `"python"` force the choice.

**Nothing depends on anything else yet.**

---

### S2 — ModelHub

Two paths, controlled by `config.model_mode`:

```python
# model_mode == "hub"  (production)
self._model_hub, _load_result = await ModelHubFactory.from_config(
    ProviderConfig.default(),
    ports={
        "credential_port": CredentialStoreAdapter(),
        "event_port":      MHEventBusAdapter(bus=self._bus),
        "state_read_port": SessionStateProdAdapter(
                               _FirstSessionSSMShim(self._sessions)
                           ),
        "metrics_port":    PrometheusAdapter(),
        "config_port":     ConfigAdapter(),
    },
)

# model_mode == "test"
self._model_hub = ModelHubFactory.create_with_ports(ports=mh_ports)
# + StubProviderPlugin registered into the hub
```

`_FirstSessionSSMShim` is a closure over `self._sessions` (the live session dict).
It returns `sessions[first_key].get_section(name)` — see OPEN_ISSUES §1.

Cleanup on failure: `bus.close()` + `router.close()`.

---

### S2.5 — HIL (conditional on `config.enable_hil_service`)

```python
self._hil_service = HumanInTheLoopService(
    event_port=KernelHILEventAdapter(
        bus=self._bus,
        loop=asyncio.get_running_loop(),
    ),
    ledger=HILLedgerAdapter(None),
    suspension_mgr=None,
    safety_policy=SafetyBandPolicy(),
    config=HILConfig(
        max_clarification_rounds=config.hil_max_clarification_rounds,
        clarification_timeout_ms=config.hil_clarification_timeout_ms,
        approval_timeout_ms=config.hil_approval_timeout_ms,
        needs_human_timeout_ms=config.hil_needs_human_timeout_ms,
        override_timeout_ms=config.hil_override_timeout_ms,
        capability_gate_timeout_ms=config.hil_capability_gate_timeout_ms,
        enable_audit_topic=config.hil_enable_audit_topic,
        enable_llm_synthesis=config.hil_enable_llm_synthesis,
    ),
    llm_port=None,
)
```

If `enable_hil_service=False`, `self._hil_service = None`. All downstream components
receive `None` and use their internal `_NullHILAdapter`.

---

### S2.6 — SelfModel bundle (conditional on `config.enable_self_model`)

```python
self._self_model_bundle = build_self_model_bundle(
    bus=self._async_bus,
    hil_service=self._hil_service,
    projection_db_path=config.selfmodel_projection_db_path,
    family_space_id=config.selfmodel_family_space_id,
)
```

Cleanup on failure: `hil_service.shutdown()` + `bus.close()` + `router.close()`.

---

### S4 — Bridge adapter

```python
# bridge_enabled=True
bridge_adapter = SinkBridgeAdapter(outbox_path=config.bridge_outbox_path)

# bridge_enabled=False
bridge_adapter = OfflineBridgeAdapter()

self._bridge = bridge_adapter
bridge_client = bridge_adapter.get_client()   # SinkBridgeClient | None
```

Bridge is wired **before** Fabric because Fabric takes a bridge adapter as input.

---

### pre-S3 — SessionRoutingStateReader

```python
self._session_routing_reader = SessionRoutingStateReader(
    lookup=lambda session_id: self._sessions.get(session_id)
)
```

This closure provides a live view of the `_sessions` dict to all shared components
that need to resolve per-session state at request time.

---

### S3 — Shared CapabilityFabric

```python
self._shared_fabric = FabricFactory.create_shared(
    event_port=EventPortProdAdapter(self._bus),
    bridge=BridgeConnectionAdapter(client=bridge_client),
    model_gateway=ModelGatewayBridgeAdapter(hub=self._model_hub),
    prompt_system=PromptSystemProdAdapter("k1/contracts/prompts"),
    delta_bus=DeltaBusProdAdapter(self._bus),
    state_reader=self._session_routing_reader,
    hil_port=self._hil_service,
)
```

`FabricFactory.create_shared` defaults `production_mode=True`.
When `state_reader=None`, Fabric uses a `NullSessionStateReaderAdapter` internally.

Structural validation: `assert hasattr(self._shared_fabric, 'execute')`.

---

### S5 — OrchestratorService

```python
event_port = EventPortProdAdapter(self._bus)
delta_bus  = DeltaBusProdAdapter(self._bus)

self._orchestrator = await OrchestratorFactory.create_production(
    config=OrchestratorConfig.from_dict({
        "workflow_db_path": config.workflow_db_path,
        "admin_enabled": False,
    }),
    mailbox=MailboxAdapter(),
    fabric=FabricGatewayAdapter(fabric=self._shared_fabric),
    planner=MockPlannerAdapter(),          # temporary; replaced at S6b
    state=StateReadAdapter(
        state_reader=self._session_routing_reader
    ),
    delta=DeltaEmitAdapter(
        event_port=event_port,
        delta_bus=delta_bus,
    ),
    bridge=(
        BridgeWriteAdapter(BridgeClientShim(bridge_client))
        if bridge_client is not None
        else MockBridgeAdapter()
    ),
    event=EventSubscriptionAdapter(event_port=event_port),
    storage=WorkflowStorageAdapter(
        SQLiteWorkflowAdapter(db_path=config.workflow_db_path)
    ),
    hil_port=self._hil_service,
)
```

Structural validations:
```python
assert hasattr(self._orchestrator, 'process')
assert callable(self._orchestrator._dag_executor._guards[3].after_step)
```

---

### S6 — PlannerAgent

```python
self._planner = await PlannerFactory.create_production(
    llm_port=LLMGatewayAdapter(
        llm_request_bus=ModelHubRequestBus(self._model_hub)
    ),
    fabric_port=FabricRetrievalAdapter(
        fabric_retrieval=self._shared_fabric.retrieval
    ),
    state_port=PlannerStateAdapter(
        reader=self._session_routing_reader,
        session_id="__shared__",
    ),
    bridge_port=PlannerBridgeAdapter(bridge_port=bridge_adapter),
    delta_port=PlannerDeltaBusAdapter(delta_bus=delta_bus),
    event_port=PlannerEventBusAdapter(event_port=event_port),
    mailbox_port=PlannerMailboxAdapter(),
    hil_port=self._hil_service,
)
```

`bridge_adapter` is the S4 `SinkBridgeAdapter` or `OfflineBridgeAdapter` instance
(not the client — the adapter itself). `bridge_port` in Planner is `IBridgePort`
for writing back to K0.

`state_port` uses `session_id="__shared__"`. The routing reader resolves this at
planning request time from the request envelope's session_id, not from the literal
key — see OPEN_ISSUES §2.

---

### S6b — Planner cross-wire into Orchestrator

Replaces the `MockPlannerAdapter` installed at S5:

```python
planner_mailbox = self._planner.get_mailbox()

self._orchestrator.bind_planner(
    PlannerAdapter(
        planner_mailbox=planner_mailbox,
        cb_planner=CircuitBreaker(
            provider_id="planner",
            config=CircuitBreakerConfig(),
        ),
    )
)
```

Post-wire verification:
```python
assert not isinstance(self._orchestrator._planner_port, MockPlannerAdapter)
assert self._planner.mailbox.has_pipeline_controller()
```

**Window between S5 and S6b:** orchestrator holds `MockPlannerAdapter`. Any task
arriving in this window would be handled by the mock — see OPEN_ISSUES §5.

---

### S7 — Planner task + Phase1 pipeline

```python
# planner.start() is an infinite coroutine — MUST be create_task, never awaited
self._planner_task = asyncio.create_task(
    self._planner.start(),
    name="planner-agent",
)

self._phase1_pipeline = self._build_shared_phase1_pipeline()
# phase1_pipeline == "ultrabert" → UltraBERTPhase1Pipeline (optionally warmed up)
# else                           → StubPhase1Pipeline

self._running = True
```

Five post-wire verifications run before `_running = True`:
1. `hasattr(self._orchestrator, 'process')`
2. `hasattr(self._shared_fabric, 'execute')`
3. `hasattr(self._model_hub, 'execute')`
4. `callable(self._orchestrator._dag_executor._guards[3].after_step)`
5. `not isinstance(self._orchestrator._planner_port, MockPlannerAdapter)`

---

## Tier 2 — Per-session creation (`_create_session_tier2`)

### P1 — Per-session Bus + Router + Mailboxes

```python
session_bus    = BusFactory.create_local_ordered(capture=False)
session_router = BusFactory.create_mailbox_router()
front_mailbox  = session_router.register(ACTOR_FRONT)
back_mailbox   = session_router.register(ACTOR_BACK)
```

The session bus is completely isolated from the shared Tier 1 bus.

---

### P2 — SessionStateManager

```python
ssm = SessionStateFactory.create_with_ports(
    session_id=session_id,
    storage=SQLiteStorageAdapter(db_path=config.sessionstate_db_path),
    events=LocalEventAdapter(capture_mode=False),
    writer=DirectWriterAdapter(writer_id="direct"),
    lifecycle=StandaloneLifecycle(),
    k0_sync=None,
)
ss_writer.bind_manager(ssm, ssm.mutation_guard)
ss_lifecycle.bind_manager(ssm)
ssm.start()
async_ssm = AsyncSSMBridge(ssm)
```

All sessions share the same `sessionstate_db_path` SQLite file; session isolation
is by `session_id` key within the schema.

---

### P3 — Per-session CapabilityFabric

```python
session_fabric = FabricFactory.create_with_ports(
    state_reader=SessionStateReaderAdapter(ssm, session_id),
    event_port=EventPortProdAdapter(session_bus),
    bridge=BridgeConnectionAdapter(client=bridge_client),
    model_gateway=ModelGatewayBridgeAdapter(hub=self._model_hub),
    prompt_system=PromptSystemProdAdapter("k1/contracts/prompts"),
    delta_bus=DeltaBusProdAdapter(session_bus),
    production_mode=True,
    hil_port=self._hil_service,
)
```

`model_hub` is the shared Tier 1 instance.
`bridge_client` is the shared Tier 1 bridge client.
Per-session fabric is **not torn down** on `destroy_session()` — see OPEN_ISSUES §3.

---

### P3.5 — SelfModel handle (optional, non-fatal)

```python
# conditional on config.enable_self_model and self._self_model_bundle is not None
actor_id, device_meta = self._derive_session_actor(ssm, session_id, device_id)
session_self_model = build_self_model_handle(
    bundle=self._self_model_bundle,
    session_id=session_id,
    actor_id=actor_id,
    device_id=device_meta,
    situation_kind=config.selfmodel_situation_kind,
    hil_service=self._hil_service,
)
```

If any exception is raised, it is caught and logged. `session_self_model = None`.
The session continues to start without a self-model handle.

---

### P4 — ConciergeRuntime

```python
concierge = ConciergeFactory.create_with_ports(
    bus=session_bus,
    router=session_router,
    front_mailbox=front_mailbox,
    back_mailbox=back_mailbox,
    ports=PortBundle(
        delta=DeltaPortAdapter(delta_bus),
        input_=InputPortAdapter(front_mailbox),
        output=OutputPortAdapter(back_mailbox),
        state=SSMStateAdapter(ssm),
        llm=model_hub,
        classification=phase1_pipeline,
        dispatch=FabricDispatchAdapter(
            fabric=session_fabric,
            orchestrator=self._orchestrator,
            bus=session_bus,
            workflow_engine=...,
        ),
        memory=RecallMemoryAdapter(
            recall_fn=build_recall_fn(bridge_client)
            # returns [] when bridge_client is None (offline mode)
        ),
        writer=ss_writer,
    ),
    config=ConciergeConfig.from_kernel_config(config),
    hil_port=self._hil_service,
)
```

`phase1_pipeline` is the shared `UltraBERTPhase1Pipeline` or `StubPhase1Pipeline`
built at S7.

---

### P5 — MemoryWriterService

```python
memory_writer = MemoryWriterFactory.create(
    session_read_port=SessionReadAdapter(
        ssm=ssm,
        cold_archive=ssm.get_local_cold_archive(),
    ),
    model_hub_port=ModelHubAdapter(hub=self._model_hub),
    bridge_command_port=BridgeCommandAdapter(command_port=bridge_client),
    event_subscription_port=MWEventSubscriptionAdapter(
        FabricBusAdapter(session_bus)
    ),
    health_port=HealthAdapter(
        circuit_breaker=cb,
        ...
    ),
    config=MWConfig(),
)
```

---

### pre-P6 — SelfModel install + Concierge bind

```python
if session_self_model is not None:
    session_self_model.install_into_session(
        front_dispatcher=concierge.front_dispatcher,
        back_dispatcher=concierge.back_dispatcher,
        front_ctx=concierge.front_ctx,
        back_ctx=concierge.back_ctx,
    )
    try:
        concierge.set_self_model(session_self_model)
    except Exception:
        pass    # non-fatal
```

This must happen **before** `concierge.start()` so the self-model gates are in place
before the first message is processed.

---

### P6 — Start lifecycle + register session

```python
await session_concierge.start()
await session_memory_writer.start()

session = SessionInstance(
    session_id=session_id,
    device_id=device_id,
    bus=session_bus,
    router=session_router,
    session_state=ssm,
    fabric=session_fabric,
    memory_writer=memory_writer,
    concierge=concierge,
    concierge_task=concierge.consumer_task,
    consumer_task=concierge.consumer_task,
)
self._sessions[session_id] = session
```

---

## Teardown sequences

### Session teardown (reverse P6→P1), per step capped at `_TEARDOWN_TIMEOUT = 10.0s`

```
1.  handle.uninstall_from_session()              if self_model installed
2.  await memory_writer.stop()                   10s timeout
3.  await concierge.stop()                       10s timeout
4.  [NO per-session fabric.shutdown()]           ← gap; see OPEN_ISSUES §3
5.  ssm.stop()                                   sync, no timeout
6.  await asyncio.sleep(0)                       drain in-flight bus callbacks
7.  session_bus.close()
8.  session_router.close()
```

### Kernel shutdown (reverse S7→S1), per step capped at `_TEARDOWN_TIMEOUT = 10.0s`

```
1.  destroy all active sessions (above sequence, session order unspecified)
2.  await planner.stop()  +  planner_task.cancel()
3.  await orchestrator.shutdown()
4.  await hil_service.shutdown()                 if hil_service is not None
5.  self_model_bundle.shutdown()                 if bundle is not None
6.  await bridge.disconnect()
7.  await shared_fabric.shutdown()
8.  await model_hub.shutdown()
9.  bus.close()
10. router.close()
11. self._running = False                        always, even on errors
```

All per-step errors are collected. If any non-zero count: raises
`RuntimeError("shutdown: N error(s): <details>")` after step 11.

---

## Full dependency graph (construction order)

```
BusFactory
 └─ IBus  ──────────────────────────────────────────────────────────────────┐
 └─ IMailboxRouter                                                           │
                                                                             │
ModelHubFactory ← CredentialStoreAdapter                                    │
               ← MHEventBusAdapter(IBus) ◄──────────────────────────────────┘
               ← SessionStateProdAdapter(_FirstSessionSSMShim(_sessions))   │
               ← PrometheusAdapter                                          │
               ← ConfigAdapter                                              │
 └─ ModelHub ──────────────────────────────────────────────────────────────┐│
                                                                            ││
HumanInTheLoopService ← KernelHILEventAdapter(IBus) ◄──────────────────────┘│
 └─ HILService ─────────────────────────────────────────────────────────┐   │
                                                                        │   │
SinkBridgeAdapter | OfflineBridgeAdapter                                │   │
 └─ bridge_client ──────────────────────────────────────────────┐       │   │
                                                                │       │   │
FabricFactory.create_shared ← EventPortProdAdapter(IBus) ◄──────────────────┘
                            ← BridgeConnectionAdapter(bridge_client) ◄──┘   │
                            ← ModelGatewayBridgeAdapter(ModelHub) ◄─────────┘
                            ← PromptSystemProdAdapter                        │
                            ← DeltaBusProdAdapter(IBus) ◄───────────────────┐│
                            ← SessionRoutingStateReader(_sessions)           ││
                            ← HILService ◄──────────────────────────────────┘│
 └─ SharedFabric ──────────────────────────────────────────────────┐         │
                                                                   │         │
OrchestratorFactory ← FabricGatewayAdapter(SharedFabric) ◄─────────┘         │
                    ← MockPlannerAdapter [temporary]                          │
                    ← BridgeWriteAdapter(bridge_client)                       │
                    ← EventSubscriptionAdapter(IBus) ◄────────────────────────┘
                    ← WorkflowStorageAdapter(SQLiteWorkflowAdapter)
                    ← HILService
 └─ Orchestrator ──────────────────────────────────────────────┐
                                                               │
PlannerFactory ← LLMGatewayAdapter(ModelHubRequestBus(ModelHub))
               ← FabricRetrievalAdapter(SharedFabric.retrieval)
               ← PlannerBridgeAdapter(bridge_adapter)
               ← HILService
 └─ Planner
      └── bind_planner(PlannerAdapter(Planner.mailbox)) ──────► Orchestrator
      └── asyncio.create_task(Planner.start())                [infinite task]
```

Per-session graph adds: `SessionBus → SSM → SessionFabric → MemoryWriter → Concierge`
all wired over the shared `ModelHub`, `bridge_client`, `HILService`, and
`SharedOrchestrator` (via `FabricDispatchAdapter`).
