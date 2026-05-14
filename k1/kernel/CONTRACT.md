# K1 Kernel — CONTRACT

`KernelService` is the composition root of K1. It satisfies two public contracts
and derives a contract from each of its eight dependencies.

---

## 1. Public contracts (what kernel promises its callers)

### 1.1 `ILifecyclePort`

```python
async def startup(self) -> None
async def shutdown(self) -> None
async def health_check(self) -> HealthStatus
@property
def is_running(self) -> bool
```

| Method | Precondition | Postcondition | Raises |
|--------|-------------|---------------|--------|
| `startup()` | not yet started | all subsystems live; `is_running == True` | `RuntimeError("already running")` if called twice; partial-startup errors propagate as-is |
| `shutdown()` | any state | all subsystems stopped; `is_running == False` | `RuntimeError("shutdown: N error(s): …")` aggregating all per-step failures; idempotent — safe to call on a kernel that never started |
| `health_check()` | any state | returns `HealthStatus` reflecting current liveness | never raises |
| `is_running` | — | `True` after `startup()` completes; `False` before or after `shutdown()` | — |

### 1.1.1 Diagnostics API

These methods are observability-only and are not part of production control flow:

```python
def describe_wiring(self) -> dict[str, Any]
def lifecycle_events(self) -> list[dict[str, Any]]
```

`describe_wiring()` returns a plain dict snapshot of Tier 1 component types,
selected Tier 1 port adapter types, selected PORT-IDENTITY booleans, per-session
component types, bridge mode, running state, and planner task name.
`lifecycle_events()` returns append-only phase-completion records with `phase`,
`component`, and monotonic timestamp `ts`. Live-kernel tests use these methods for
PORT-IDENTITY and LIFECYCLE-ORDER probes; production code must not branch on them.

### 1.2 `ISessionManagerPort`

```python
async def create_session(
    self, session_id: str, device_id: str | None = None
) -> SessionInstance

async def destroy_session(self, session_id: str) -> None
def get_session(self, session_id: str) -> SessionInstance | None
def list_sessions(self) -> list[str]
```

| Method | Precondition | Postcondition | Raises |
|--------|-------------|---------------|--------|
| `create_session(session_id, device_id)` | kernel running; `session_id` not already registered | per-session bus, SSM, fabric, concierge, memory writer all started; session registered in `_sessions` | `RuntimeError` if any per-session component fails to start |
| `destroy_session(session_id)` | kernel running | all per-session components stopped; session removed from `_sessions` | `KeyError` if `session_id` not found |
| `get_session(session_id)` | any state | returns `SessionInstance` or `None` | never raises |
| `list_sessions()` | any state | returns list of registered session ids | never raises |

### 1.3 `SessionInstance` — exposed fields

```python
@dataclass
class SessionInstance:
    session_id: str
    device_id: str | None
    bus: IBus
    router: IMailboxRouter
    session_state: SessionStateManager
    fabric: CapabilityFabric        # per-session
    memory_writer: MemoryWriterService
    concierge: ConciergeRuntime
    concierge_task: asyncio.Task    # concierge.start() coroutine (infinite)
    consumer_task: asyncio.Task     # mailbox consumer loop (infinite)
```

---

## 2. Dependency contracts (what kernel requires from each dependency)

### 2.1 Bus — `IBus` + `IMailboxRouter`

The bus is the **only dependency kernel constructs itself** (via `BusFactory`).
Everything else takes the bus as input. Kernel calls:

```python
# Construction (S1, P1)
IBus  = BusFactory.create_local_ordered(
    capture: bool,
    outbox: BusOutbox | None,
    durable_topics: set | None
) -> IBus

IMailboxRouter = BusFactory.create_mailbox_router() -> IMailboxRouter

# Router usage (P1)
mailbox: IMailbox = router.register(actor_id: str, config: MailboxConfig | None = None)
router.unregister(actor_id: str) -> bool          # session teardown
router.close()                                     # kernel shutdown
router.is_closed: bool

# Bus teardown (kernel shutdown, session teardown)
bus.close()
bus.is_closed: bool
```

Backend is selected via `K1_BUS_BACKEND` env var (`"auto"` / `"rust"` / `"python"`).
`"auto"` probes `k1_bus_core` import and uses Rust if available.

**Required contract from IBus:** publish, subscribe, unsubscribe, flush, close, is_closed.
**Required contract from IMailboxRouter:** deliver, register, unregister, registered_actors, close, is_closed.

### 2.2 ModelHub

Kernel constructs ModelHub at S2 via `ModelHubFactory`. Kernel does NOT call any
`IModelHubPort` method directly after construction — ModelHub is passed wholesale
to adapters for Fabric, Planner, Orchestrator, MemoryWriter, and Concierge.

**Structural check kernel performs:**
```python
assert hasattr(model_hub, 'execute')   # _validate_ports()
```

**Teardown kernel calls:**
```python
await model_hub.shutdown()             # drains aiohttp ClientSessions
```

**Dependency kernel injects into ModelHub:**
```python
ports = {
    "credential_port": CredentialStoreAdapter(),
    "event_port":      MHEventBusAdapter(bus=self._bus),
    "state_read_port": SessionStateProdAdapter(_FirstSessionSSMShim(self._sessions)),
    "metrics_port":    PrometheusAdapter(),
    "config_port":     ConfigAdapter(),
}
```

`_FirstSessionSSMShim`: reads `_sessions[0].get_section(name)` for `persona`/`control`.
Returns `None` if no sessions are active. See OPEN_ISSUES §1.

### 2.3 HIL (`HumanInTheLoopService`)

Kernel constructs HIL at S2.5 if `enable_hil_service=True`. It is passed through —
kernel only calls one method on it directly:

```python
await hil_service.shutdown()     # cancels pending futures, unsubscribes from bus
```

All other interaction happens inside Fabric, Orchestrator, Planner, and Concierge.
When `hil_service is None`, each subsystem falls back to its internal `_NullHILAdapter`.

**Required constructor inputs:**
```python
HumanInTheLoopService(
    event_port=KernelHILEventAdapter(bus, loop=asyncio.get_running_loop()),
    ledger=HILLedgerAdapter(None),
    suspension_mgr=None,
    safety_policy=SafetyBandPolicy(),
    config=HILConfig(...),
    llm_port=None,
)
```

### 2.4 SelfModel

Kernel constructs a `SelfModelServiceBundle` at S2.6 if `enable_self_model=True`.
Per session, a `SelfModelHandle` is built and installed.

**Kernel calls:**
```python
# S2.6 — one bundle for the whole kernel
bundle = build_self_model_bundle(
    bus=self._async_bus,
    hil_service=self._hil_service,
    projection_db_path=config.selfmodel_projection_db_path,
    family_space_id=config.selfmodel_family_space_id,
)

# P3.5 — one handle per session (non-fatal; session continues if this fails)
handle = build_self_model_handle(
    bundle=bundle,
    session_id=session_id,
    actor_id=actor_id,
    device_id=device_meta,
    situation_kind=config.selfmodel_situation_kind,
    hil_service=hil_service,
)

handle.install_into_session(
    front_dispatcher=concierge.front_dispatcher,
    back_dispatcher=concierge.back_dispatcher,
    front_ctx=concierge.front_ctx,
    back_ctx=concierge.back_ctx,
)
concierge.set_self_model(handle)    # non-fatal if fails

# Session teardown
handle.uninstall_from_session()     # before concierge.stop()

# Kernel shutdown
bundle.shutdown()
```

### 2.5 Bridge

Kernel constructs a bridge adapter at S4. The adapter wraps an underlying `IBridgeRuntime`.

**Contract kernel requires from IBridgeRuntime:**
```python
await bridge.connect() -> None
await bridge.disconnect() -> None
bridge.is_connected: bool
bridge.get_client() -> Any | None    # None when OfflineBridgeAdapter
```

Two implementations:
- `OfflineBridgeAdapter` — `get_client()` returns `None`; all consuming adapters handle None gracefully.
- `SinkBridgeAdapter(outbox_path)` — writes to SQLite outbox; `get_client()` returns `SinkBridgeClient`.

Bridge client is fanned out to:
- Fabric (S3, P3) via `BridgeConnectionAdapter(client=bridge_client)`
- Orchestrator (S5) via `BridgeWriteAdapter(BridgeClientShim(bridge_client))` or `MockBridgeAdapter()` when `None`
- Planner (S6) via `PlannerBridgeAdapter` (shares the S3 `bridge_adapter` reference)
- Concierge (P4) via `RecallMemoryAdapter(build_recall_fn(bridge.get_client()))` — returns `[]` when `None`
- MemoryWriter (P5) via `BridgeCommandAdapter(command_port=bridge.get_client())`

### 2.6 Fabric (`CapabilityFabric`)

Kernel constructs fabric directly via `FabricFactory` — the `IFabricPort` in
`k1/kernel/ports/` is **not used** (scaffolding only).

**Structural check kernel performs:**
```python
assert hasattr(fabric, 'execute')    # _validate_ports() + _validate_session()
```

**Required factory signatures:**
```python
# Shared fabric (S3) — one instance, no session state initially
FabricFactory.create_shared(
    event_port: IEventPort,
    bridge: IFabricK0Port,
    model_gateway: IModelGatewayPort,
    prompt_system: IPromptSystemPort,
    delta_bus: IDeltaBusPort,
    *,
    state_reader: ISessionStateReader | None = None,
    hil_port: Any = None,
) -> Fabric

# Per-session fabric (P3)
FabricFactory.create_with_ports(
    state_reader: ISessionStateReader,
    event_port: IEventPort,
    bridge: IFabricK0Port,
    model_gateway: IModelGatewayPort,
    prompt_system: IPromptSystemPort,
    delta_bus: IDeltaBusPort,
    *,
    production_mode: bool = False,
    hil_port: Any = None,
) -> Fabric
```

**Teardown:** `await shared_fabric.shutdown()`.
Per-session fabric has **no shutdown call** — see OPEN_ISSUES §3.

**Fabric port types kernel supplies:**

| Port | Adapter used |
|------|-------------|
| `event_port` | `EventPortProdAdapter(bus)` |
| `bridge` | `BridgeConnectionAdapter(client=bridge_client)` |
| `model_gateway` | `ModelGatewayBridgeAdapter(hub=model_hub)` |
| `prompt_system` | `PromptSystemProdAdapter("k1/contracts/prompts")` |
| `delta_bus` | `DeltaBusProdAdapter(bus)` |
| `state_reader` (shared) | `SessionRoutingStateReader(lambda sid: _sessions.get(sid))` |
| `state_reader` (per-session) | `SessionStateReaderAdapter(ssm, session_id)` |

### 2.7 Orchestrator

Kernel constructs via `OrchestratorFactory` — the `IOrchestratorPort` in
`k1/kernel/ports/` is **not used** (scaffolding only).

**Structural check:**
```python
assert hasattr(orchestrator, 'process')
assert orchestrator._dag_executor._guards[3].after_step is callable   # ExecutionMonitor
assert not isinstance(orchestrator._planner_port, MockPlannerAdapter) # after S6b
```

**Kernel calls:**
```python
# S6b — replaces MockPlannerAdapter installed at S5
orchestrator.bind_planner(
    PlannerAdapter(
        planner_mailbox=planner.get_mailbox(),
        cb_planner=CircuitBreaker(provider_id="planner", config=CircuitBreakerConfig()),
    )
)

# Shutdown
await orchestrator.shutdown()
```

**Port bundle injected at S5:**

| Port | Adapter |
|------|---------|
| `mailbox` | `MailboxAdapter()` |
| `fabric` | `FabricGatewayAdapter(fabric=shared_fabric)` |
| `planner` | `MockPlannerAdapter()` (replaced at S6b) |
| `state` | `StateReadAdapter(session_routing_reader)` |
| `delta` | `DeltaEmitAdapter(event_port, delta_bus)` |
| `bridge` | `BridgeWriteAdapter(BridgeClientShim(bridge_client))` or `MockBridgeAdapter()` |
| `event` | `EventSubscriptionAdapter(event_port)` |
| `storage` | `WorkflowStorageAdapter(SQLiteWorkflowAdapter(db_path=workflow_db_path))` |
| `hil_port` | `hil_service` (or `None`) |

### 2.8 Planner

Kernel constructs via `PlannerFactory` — the `IPlannerPort` in `k1/kernel/ports/`
is **not used** (scaffolding only).

**Structural checks:**
```python
assert hasattr(planner, 'start')
assert planner.mailbox.has_pipeline_controller()    # after S6b
```

**Kernel calls:**
```python
# S6b — mailbox used to wire into orchestrator
mailbox = planner.get_mailbox()

# S7 — planner.start() is an infinite coroutine, NEVER awaited directly
self._planner_task = asyncio.create_task(planner.start(), name="planner-agent")

# Shutdown
await planner.stop()                   # drains mailbox, unsubscribes
self._planner_task.cancel()
```

**Port bundle injected at S6:**

| Port | Adapter |
|------|---------|
| `llm_port` | `LLMGatewayAdapter(ModelHubRequestBus(model_hub))` |
| `fabric_port` | `FabricRetrievalAdapter(shared_fabric.retrieval)` |
| `state_port` | `PlannerStateAdapter(session_routing_reader, session_id="__shared__")` |
| `bridge_port` | `PlannerBridgeAdapter(bridge_adapter)` (reuses S3 bridge_adapter) |
| `delta_port` | `PlannerDeltaBusAdapter(delta_bus)` |
| `event_port` | `PlannerEventBusAdapter(event_port)` |
| `mailbox_port` | `PlannerMailboxAdapter()` |
| `hil_port` | `hil_service` (or `None`) |

### 2.9 SessionState (`SessionStateManager`)

Kernel constructs per session at P2. After construction kernel calls:

```python
# P2
ssm.start()                                # starts lifecycle, opens SQLite
async_ssm = AsyncSSMBridge(ssm)

# Used by _FirstSessionSSMShim and _derive_session_actor:
ssm.get_section(name: str) -> Section | None

# Session teardown
ssm.stop()                                 # sync, no timeout applied
```

**Structural check:**
```python
assert hasattr(session_state, 'get_section')    # _validate_session()
```

**Constructor call:**
```python
SessionStateFactory.create_with_ports(
    session_id=session_id,
    storage=SQLiteStorageAdapter(db_path=config.sessionstate_db_path),
    events=LocalEventAdapter(capture_mode=False),
    writer=DirectWriterAdapter(writer_id="direct"),
    lifecycle=StandaloneLifecycle(),
    k0_sync=None,
)
```

---

## 3. Error surface

| Error | Condition |
|-------|-----------|
| `RuntimeError("already running")` | `startup()` called while `is_running == True` |
| `RuntimeError("shutdown: N error(s): …")` | one or more teardown steps failed; all errors aggregated |
| `RuntimeError` (propagated) | any factory (`ModelHubFactory`, `FabricFactory`, `OrchestratorFactory`, `PlannerFactory`) raises during `startup()` |
| `ValueError` | `model_mode` set to a value other than `"hub"` or `"test"` |
| `KeyError` | `destroy_session(session_id)` where `session_id` not in `_sessions` |

---

## 4. Configuration surface

`KernelConfig` fields that affect wiring decisions:

| Field | Type | Default | Effect |
|-------|------|---------|--------|
| `model_mode` | `str` | `"test"` | `"hub"` → real ModelHub via `from_config`; `"test"` → `StubProviderPlugin`; else `ValueError` |
| `bridge_enabled` | `bool` | `True` | `True` → `SinkBridgeAdapter`; `False` → `OfflineBridgeAdapter` |
| `bridge_outbox_path` | `str` | `"./data/bridge_outbox.db"` | path for `SinkBridgeAdapter` |
| `enable_hil_service` | `bool` | `True` | `True` → `HumanInTheLoopService` at S2.5; `False` → `None` propagated |
| `enable_self_model` | `bool` | `False` | `True` → `SelfModelServiceBundle` at S2.6 + handle at P3.5 |
| `selfmodel_projection_db_path` | `str \| None` | `None` | SQLite projection store path; `None` → in-memory |
| `selfmodel_family_space_id` | `str` | `"family:default"` | passed to `build_self_model_bundle` |
| `selfmodel_situation_kind` | `str` | `"caregiver_context_briefing"` | passed to `build_self_model_handle` per session |
| `phase1_pipeline` | `str` | `"ultrabert"` | `"ultrabert"` → `UltraBERTPhase1Pipeline`; else → `StubPhase1Pipeline` |
| `phase1_warmup_on_startup` | `bool` | `False` | warm UltraBERT at boot if `True` |
| `workflow_db_path` | `str` | `"./data/workflows.db"` | `OrchestratorConfig` + `SQLiteWorkflowAdapter` |
| `sessionstate_db_path` | `str` | `"./data/k1/sessionstate.db"` | `SQLiteStorageAdapter` per session |
| `bus_outbox_path` | `str \| None` | `None` | `None` → durability disabled; set → `BusOutbox` at S1 |
| `bus_durable_topics` | `tuple[str, ...]` | `()` | topics written to WAL outbox |
| `capture_bus` | `bool` | `False` | passed to `BusFactory.create_local_ordered` |
| `max_sessions` | `int` | `100` | declared but not enforced — see OPEN_ISSUES §4 |
| `allow_planner_passthrough` | `bool` | `False` | Concierge HIGH-tier stub fallback |
| `allow_dispatch_passthrough` | `bool` | `False` | back-actor tool dispatch stub |
| `hil_*` fields | various | — | map 1-to-1 onto `HILConfig` |
