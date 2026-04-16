# 14 — Epic 1.5: Orchestrator Audit

> Generated from 3 parallel subagent code reads across `k1/orchestrator/`.

---

## Summary Verdict

| Issue | What To Check | Verdict |
|-------|--------------|---------|
| 1.5.1 | 9 port definitions | ✅ All 9 Protocol ports, all `@runtime_checkable`, zero ABC. 55 methods total. |
| 1.5.2 | OrchestratorFactory | ✅ 4 static methods, 15-step `_construct_orchestrator()`, full DI, 560 LOC |
| 1.5.3 | All adapters (9 prod + 4 mock + 4 test) | ✅ **ALL 9 prod adapters REAL** — zero stubs. 4 mock + 4 test = 17 total |
| 1.5.4 | DeltaEmitAdapter TWO args? | ✅ YES — `(event_port: IEventPort, delta_bus: IDeltaBusPort)` exactly |
| 1.5.5 | PlannerAdapter hot-swap? | ❌ NO hot-swap mechanism. `_mailbox` set once in `__init__`, `__slots__` prevents patching |
| 1.5.6 | MockPlannerAdapter Phase 1? | ✅ Fully scriptable — per-request accept/reject, async plan delivery callback |

---

## Issue 1.5.1 — Port Definitions (9 Ports)

All 9 use **`Protocol` (structural typing)** with **`@runtime_checkable`**. Zero ABC. Consistent with Bus/Fabric/ModelHub pattern.

| ID | Port | File | Sync/Async | Methods | LOC |
|---|---|---|---|---|---|
| OR-P1 | `IMailboxPort` | `ports/mailbox_port.py` | SYNC | 4 | 123 |
| OR-P2 | `IFabricGatewayPort` | `ports/fabric_gateway_port.py` | ASYNC | 4 | 118 |
| OR-P3 | `IPlannerPort` | `ports/planner_port.py` | ASYNC | 3 | 107 |
| OR-P4 | `IStateReadPort` | `ports/state_read_port.py` | ASYNC | 3 | 108 |
| OR-P5 | `IDeltaEmitPort` | `ports/delta_emit_port.py` | ASYNC | 3 | 105 |
| OR-P6 | `IBridgeWritePort` | `ports/bridge_write_port.py` | ASYNC | 6 | 136 |
| OR-P7 | `IEventSubscriptionPort` | `ports/event_subscription_port.py` | SYNC | 3 | 109 |
| OR-P8 | `IWorkflowStoragePort` | `ports/workflow_storage_port.py` | ASYNC | 11 | 95 |
| OR-P9 | `IAdminPort` | `ports/admin_port.py` | ASYNC | 18 | 198 |

**Total: 55 abstract methods across 9 ports, ~1,099 LOC.**

### Key Signatures

**OR-P1 IMailboxPort** (in-process priority mailbox):

- `enqueue(message: MailboxMessage, priority: str = "INTERACTIVE") -> int`
- `dequeue() -> Optional[MailboxMessage]`
- `depth() -> int`
- `peek_priority() -> Optional[str]`
- Supporting: `MailboxMessage = Union[TaskEnvelope, CommittedPlan, WorkflowRunRequest, WorkflowSaveRequest, InterruptRequest]`

**OR-P2 IFabricGatewayPort** (Fabric facade):

- `async execute(request: CapabilityRequest) -> CapabilityResult`
- `async execute_batch(requests) -> List[CapabilityResult]`
- `async query_registry(capability_name) -> Optional[RegistryEntry]`
- `async query_registry_by_category(category_prefix) -> List[RegistryEntry]`

**OR-P3 IPlannerPort** (Planner delegation):

- `async request_plan(request: PlanRequest) -> PlanAck`
- `async cancel_plan(request_id: str) -> None`
- `async micro_replan(request: MicroReplanRequest) -> Optional[CommittedPlan]`

**OR-P4 IStateReadPort** (read-only SessionState — ORCH-01 invariant):

- `async read_section(session_id, section) -> Optional[Dict]`
- `async read_sections(session_id, names) -> Dict[str, Any]`
- `async get_snapshot(session_id) -> SessionSnapshot`

**OR-P5 IDeltaEmitPort** (fire-and-forget events):

- `async emit(event_topic, payload, trace_id) -> None`
- `async emit_progress(step_id, summary, trace_id) -> None`
- `async emit_hil_request(hil_request: HILRequest, trace_id) -> None`

**OR-P6 IBridgeWritePort** (K0 Bridge persistence):

- `async submit_audit(run_manifest, trace_id) -> None`
- `async write_wal(dag_id, entry_type, payload, trace_id) -> None`
- `async read_wal(dag_id) -> Optional[List[Dict]]` ← read on "write" port (crash recovery)
- `async list_wal_ids() -> List[str]` ← read on "write" port
- `async submit_deferred_result(result, workflow_id, trace_id) -> None`

**OR-P7 IEventSubscriptionPort** (bus subscriptions, SYNC):

- `subscribe(topic, handler) -> SubscriptionHandle`
- `unsubscribe(handle) -> bool`
- `emit(topic, payload) -> None`

**OR-P8 IWorkflowStoragePort** (workflow persistence, 11 methods):

- CRUD: `save_workflow`, `get_workflow`, `list_workflows`, `delete_workflow`, `purge_workflow`
- Triggers: `save_trigger`, `get_due_triggers`, `update_trigger_state`
- Runs: `save_run(manifest: object)`, `get_runs(workflow_id, limit=10) -> list`
- Gaps: `save_gap`, `get_pending_gaps`

**OR-P9 IAdminPort** (18 admin endpoints):

- Health (3), DAG (3), Circuit Breakers (2), Scheduler (2), Drain (1), Config (1), Mailbox (2), MCP (2), Metrics (1), Version (1)

### Cross-Module Imports from Ports

- `k1.fabric.types` → `CapabilityRequest`, `CapabilityResult` (OR-P2)
- `k1.fabric.ports.state_reader` → `SessionSnapshot` (OR-P4)
- `k1.fabric.ports.event_port` → `SubscriptionHandle` (OR-P7)

### Port Anomalies

1. **`ports/__init__.py` docstring says "8 ports"** but `__all__` correctly lists 9 (IAdminPort added later). Stale docstring.
2. **`IBridgeWritePort` has read methods** — `read_wal()` and `list_wal_ids()` violate name contract. Consider `IBridgePersistencePort`.
3. **`IWorkflowStoragePort.save_run()` takes `object`** — type safety deferred to runtime (circular import avoidance).
4. **`IWorkflowStoragePort.get_runs()` returns bare `list`** — same circular import dodge.

---

## Issue 1.5.2 — OrchestratorFactory (560 LOC)

**File:** `k1/orchestrator/factory.py`

### Factory Methods (all `@staticmethod`, all `async`)

| Method | Signature | `init()` called? |
|--------|-----------|-----------------|
| `create_standalone()` | `async () -> OrchestratorService` | NO |
| `create_for_testing()` | `async (overrides, *, config) -> OrchestratorService` | NO |
| `create_with_ports()` | `async (*, config, mailbox, fabric, planner, state, delta, bridge, event, storage) -> OrchestratorService` | NO |
| `create_production()` | `async (config, *, mailbox, fabric, planner, state, delta, bridge, event, storage) -> OrchestratorService` | **YES** |

### Private Methods

- `_build_policies(config)` → `OrchestratorPolicies`
- `_build_test_adapters()` → `Dict[str, Any]`
- `_build_guards(planner_port, delta_port)` → `list`
- `_construct_orchestrator(config, adapters)` → `OrchestratorService`

### 15-Step `_construct_orchestrator()` Wiring

1. Validate 8 adapter keys present
2. Unpack adapters → typed variables
3. `OrchestratorPolicies` ← `_build_policies(config)`
4. `OrchestratorMetrics` ← `OrchestratorMetrics(enabled=config.metrics_enabled)`
5. **Step 1:** `ErrorRouter(delta_port)`
6. **Step 2:** `ConcurrencyGuard()` (zero deps)
7. **Step 11:** `StepRunner(fabric_port, error_router, policies, metrics)`
8. **Step 12:** `Guards` ← `[OutputSchemaGuard, ConditionalEdgeEvaluator, MicroReplanCheckpoint, ExecutionMonitor(service_ref=None)]`
9. **Step 13:** `DAGExecutor` ← 10 args (fabric, planner, delta, state, bridge, step_runner, error_router, guards, ParamResolver, metrics)
10. **Step 14a:** `ConstraintResolver(fabric_port, delta_port, event_port)`
11. **Step 14b:** Workflow subsystem — 9 objects:
    - `SystemClock`, `WorkflowRegistry(storage)`, `WorkflowCompiler(fabric, delta, storage, state, clock)`
    - `WorkflowScheduler(storage, mailbox, state, clock, tick_interval, metrics)`
    - `WorkflowDepthGuard(max_depth)`, `CrossWorkflowResolver`, `WorkflowRunSupervisor`
    - `ProactiveGapDetector`, `WorkflowEngine` (10+ args)
12. **Step 15:** Connector subsystem — `MCPToolDiscovery`, `MCPRegistrationBridge`, `ConnectorLifecycleManager`
13. **FINAL:** `OrchestratorService` ← 15 keyword args
14. **POST:** Lazy init — `guards[3]._service_ref = service` (ExecutionMonitor circular dep)
15. **Step 15.5:** `AdminHttpAdapter(service, config)` → `service._admin` (only if `config.admin_enabled`)

### DI Pattern

Full explicit constructor injection. No service locator, no globals, no singletons. Factory `__init__` raises `TypeError` to prevent instantiation.

### Two-Phase / Late-Binding

- **ExecutionMonitor**: created with `service_ref=None`, patched after OrchestratorService construction
- **AdminHttpAdapter**: created after service, injected via `service._admin`
- **No Planner hot-swap**: planner port injected once at construction, no rebinding

### `_ALL_PORT_KEYS` = 8 (not 9)

Admin port is NOT in the adapter dict — created post-construction. `create_with_ports()` does NOT accept an admin adapter.

---

## Issue 1.5.3 — All 17 Adapters

### Production Adapters (9) — ALL REAL

| # | Adapter | Port | Constructor | LOC | Classification |
|---|---------|------|-------------|-----|---------------|
| OR-A1 | `MailboxAdapter` | `IMailboxPort` | `(max_depth=100, wfq_weights=None)` | ~250 | **REAL** — full WFQ, 3 priority queues, threading.Lock |
| OR-A2 | `FabricGatewayAdapter` | `IFabricGatewayPort` | `(fabric: Fabric)` | ~290 | **REAL** — shared Fabric pass-through + error mapping + batch fallback |
| OR-A3 | `PlannerAdapter` | `IPlannerPort` | `(planner_mailbox: Any, cb_planner: CircuitBreaker)` | ~240 | **REAL** — CB integration, mailbox delegation, micro-replan w/ timeout |
| OR-A4 | `StateReadAdapter` | `IStateReadPort` | `(state_reader: ISessionStateReader)` | ~165 | **REAL** — thin pass-through, enforces ORCH-01 (no writes) |
| OR-A5 | `DeltaEmitAdapter` | `IDeltaEmitPort` | `(event_port: IEventPort, delta_bus: IDeltaBusPort)` | ~150 | **REAL** — dual-publish, fire-and-forget, never raises |
| OR-A6 | `BridgeWriteAdapter` | `IBridgeWritePort` | `(bridge_client: IBridgeClient)` | ~215 | **REAL** — fire-and-forget writes + WAL reads for crash recovery |
| OR-A7 | `EventSubscriptionAdapter` | `IEventSubscriptionPort` | `(event_port: IEventPort)` | ~145 | **REAL** — subscription tracking, bulk shutdown |
| OR-A8 | `WorkflowStorageAdapter` | `IWorkflowStoragePort` | `(storage: IWorkflowStoragePort)` | ~210 | **REAL** — 12 CRUD methods → SQLite backend |
| OR-A9 | `AdminHttpAdapter` | `IAdminPort` | `(service: OrchestratorService, config: OrchestratorConfig)` | ~560 | **REAL** — full aiohttp server, 18 HTTP endpoints |

### Mock Adapters (4)

| # | Adapter | Port | Key Feature |
|---|---------|------|------------|
| OR-M1 | `MockPlannerAdapter` | `IPlannerPort` | Script per-request accept/reject + async plan delivery callback (~148 LOC) |
| OR-M2 | `MockFabricAdapter` | `IFabricGatewayPort` | Script results/errors/timeouts per capability, default success (~142 LOC) |
| OR-M3 | `MockBridgeAdapter` | `IBridgeWritePort` | In-memory WAL, pre-populate for crash recovery tests (~132 LOC) |
| OR-M4 | `MockStateReadAdapter` | `IStateReadPort` | In-memory sections, snapshot builder, safety band helpers (~119 LOC) |

### Test Adapters (4)

| # | Adapter | Port | Key Feature |
|---|---------|------|------------|
| OR-T1 | `TestMailboxAdapter` | `IMailboxPort` | FIFO (not WFQ) for deterministic ordering, unbounded (~107 LOC) |
| OR-T2 | `TestEventAdapter` | `IEventSubscriptionPort` | Wildcard matching via `fnmatch`, sync dispatch (~124 LOC) |
| OR-T3 | `TestDeltaAdapter` | `IDeltaEmitPort` | Capture-only, never raises (~97 LOC) |
| OR-T4 | `TestWorkflowStorageAdapter` | `IWorkflowStoragePort` | Full CRUD in-memory, soft/hard delete, 5 stores (~222 LOC) |

### Coverage Matrix

| Port | Prod | Mock | Test |
|------|------|------|------|
| `IMailboxPort` | OR-A1 | — | OR-T1 |
| `IFabricGatewayPort` | OR-A2 | OR-M2 | — |
| `IPlannerPort` | OR-A3 | OR-M1 | — |
| `IStateReadPort` | OR-A4 | OR-M4 | — |
| `IDeltaEmitPort` | OR-A5 | — | OR-T3 |
| `IBridgeWritePort` | OR-A6 | OR-M3 | — |
| `IEventSubscriptionPort` | OR-A7 | — | OR-T2 |
| `IWorkflowStoragePort` | OR-A8 | — | OR-T4 |
| `IAdminPort` | OR-A9 | — | — |

**IAdminPort has NO test double at all.**

---

## Issue 1.5.4 — DeltaEmitAdapter Constructor: TWO Args Confirmed

```python
def __init__(self, event_port: IEventPort, delta_bus: IDeltaBusPort) -> None:
```

- **`event_port: IEventPort`** — Fabric's sync module-to-module event bus (`emit()`)
- **`delta_bus: IDeltaBusPort`** — Fabric's sync user-facing delta stream (`emit_delta()`)
- Both stored in `__slots__` as `_event_port` and `_delta_bus`
- Dual-publish: `k1.hil.*` and `k1.orchestration.*` topics → BOTH buses; internal-only → event_port only
- **NEVER raises** — all exceptions caught and logged (fire-and-forget contract)

**Kernel wiring implication:** Must inject TWO separate Fabric bus instances (or the same bus if IEventPort and IDeltaBusPort are both satisfied by a single object — check FabricFactory output).

---

## Issue 1.5.5 — PlannerAdapter Hot-Swap: NOT SUPPORTED

```python
def __init__(self, planner_mailbox: Any, cb_planner: CircuitBreaker) -> None:
```

- `self._mailbox` set once in `__init__`, stored in `__slots__`
- **No setter**, no `swap()`, no `replace_planner()` method
- `__slots__` prevents dynamic attribute addition (monkey-patching impossible)
- `IPlannerMailbox` Protocol defined in-file but param typed as `Any` (documentation only)
- CB also not swappable (same `__slots__` pattern)

**To enable hot-swap for Phase 2:**

- Add `replace_mailbox(new_mailbox)` method
- Add a `threading.Lock` to serialize in-flight calls during swap
- Or: use a `PlannerProxy` wrapper that delegates to a mutable inner reference

---

## Issue 1.5.6 — MockPlannerAdapter: Ready for Phase 1

```python
class MockPlannerAdapter:  # implements IPlannerPort
    def __init__(self, plan_callback: Optional[Callable[[CommittedPlan], Any]] = None):
```

**Scripting API:**

- `script_plan(request_id, plan)` — pre-configure a `CommittedPlan` response
- `script_failure(request_id)` — pre-configure `REJECTED`
- `script_micro_replan(request_id, plan)` — pre-configure micro-replan result

---

## EXHAUSTIVE PORT & CONTRACT REFERENCE

> Every port Protocol method signature and every dataclass/DTO field, with file paths, line numbers, and direction classification.

---

### PORT 1: `IMailboxPort` — [ports/mailbox_port.py](k1/orchestrator/ports/mailbox_port.py)

**Direction:** INBOUND (Orchestrator implements internally via MailboxAdapter)
**Sync/Async:** SYNC (in-process, no I/O)

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `enqueue` | `message: MailboxMessage`, `priority: str = "INTERACTIVE"` | `int` (queue position) | L102-L121 |
| `dequeue` | *(none)* | `Optional[MailboxMessage]` | L123-L134 |
| `depth` | *(none)* | `int` | L136-L142 |
| `peek_priority` | *(none)* | `Optional[str]` | L144-L152 |

**Supporting types:**
- `MailboxMessage = Union[TaskEnvelope, CommittedPlan, WorkflowRunRequest, WorkflowSaveRequest, InterruptRequest]` (L51-L56)
- `MailboxFullError(Exception)` — raised when `depth >= max_depth (100)` (L65-L69)

---

### PORT 2: `IFabricGatewayPort` — [ports/fabric_gateway_port.py](k1/orchestrator/ports/fabric_gateway_port.py)

**Direction:** OUTBOUND (Orchestrator calls through to Fabric)
**Sync/Async:** ASYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `execute` | `request: CapabilityRequest` | `CapabilityResult` | L62-L76 |
| `execute_batch` | `requests: List[CapabilityRequest]` | `List[CapabilityResult]` | L78-L100 |
| `query_registry` | `capability_name: str` | `Optional[RegistryEntry]` | L108-L125 |
| `query_registry_by_category` | `category_prefix: str` | `List[RegistryEntry]` | L127-L148 |

**External imports:** `CapabilityRequest`, `CapabilityResult` from `k1.fabric.types`; `RegistryEntry` from `k1.orchestrator.types`

---

### PORT 3: `IPlannerPort` — [ports/planner_port.py](k1/orchestrator/ports/planner_port.py)

**Direction:** OUTBOUND (Orchestrator delegates to Planner)
**Sync/Async:** ASYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `request_plan` | `request: PlanRequest` | `PlanAck` | L62-L84 |
| `cancel_plan` | `request_id: str` | `None` | L86-L100 |
| `micro_replan` | `request: MicroReplanRequest` | `Optional[CommittedPlan]` | L110-L138 |

**Contract types used:** `PlanRequest`, `MicroReplanRequest`, `PlanAck`, `CommittedPlan` (all from `k1.orchestrator.types`)

---

### PORT 4: `IStateReadPort` — [ports/state_read_port.py](k1/orchestrator/ports/state_read_port.py)

**Direction:** OUTBOUND (Orchestrator reads SessionState — NEVER writes, ORCH-01)
**Sync/Async:** ASYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `read_section` | `session_id: str`, `section: str` | `Optional[Dict[str, Any]]` | L68-L84 |
| `read_sections` | `session_id: str`, `names: List[str]` | `Dict[str, Any]` | L86-L102 |
| `get_snapshot` | `session_id: str` | `SessionSnapshot` | L104-L124 |

**External imports:** `SessionSnapshot` from `k1.fabric.ports.state_reader`

---

### PORT 5: `IDeltaEmitPort` — [ports/delta_emit_port.py](k1/orchestrator/ports/delta_emit_port.py)

**Direction:** OUTBOUND (Orchestrator emits events — fire-and-forget, never raises)
**Sync/Async:** ASYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `emit` | `event_topic: str`, `payload: Dict[str, Any]`, `trace_id: str` | `None` | L60-L82 |
| `emit_progress` | `step_id: str`, `summary: str`, `trace_id: str` | `None` | L84-L103 |
| `emit_hil_request` | `hil_request: HILRequest`, `trace_id: str` | `None` | L111-L130 |

**Contract types used:** `HILRequest` from `k1.orchestrator.types`

---

### PORT 6: `IBridgeWritePort` — [ports/bridge_write_port.py](k1/orchestrator/ports/bridge_write_port.py)

**Direction:** OUTBOUND (Orchestrator writes to K0 Bridge — fire-and-forget for writes, raises for reads)
**Sync/Async:** ASYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `submit_audit` | `run_manifest: Dict[str, Any]`, `trace_id: str` | `None` | L63-L82 |
| `write_wal` | `dag_id: str`, `entry_type: str`, `payload: Dict[str, Any]`, `trace_id: str` | `None` | L84-L111 |
| `read_wal` | `dag_id: str` | `Optional[List[Dict[str, Any]]]` | L113-L133 |
| `list_wal_ids` | *(none)* | `List[str]` | L135-L150 |
| `submit_deferred_result` | `result: Dict[str, Any]`, `workflow_id: str`, `trace_id: str` | `None` | L152-L172 |

**Note:** `read_wal` and `list_wal_ids` are READ methods on a "write" port — used only for crash recovery (6.2.4).

---

### PORT 7: `IEventSubscriptionPort` — [ports/event_subscription_port.py](k1/orchestrator/ports/event_subscription_port.py)

**Direction:** OUTBOUND (Orchestrator subscribes to external events)
**Sync/Async:** SYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `subscribe` | `topic: str`, `handler: Callable[[str, Dict[str, Any]], None]` | `SubscriptionHandle` | L76-L93 |
| `unsubscribe` | `handle: SubscriptionHandle` | `bool` | L101-L114 |
| `emit` | `topic: str`, `payload: Dict[str, Any]` | `None` | L116-L132 |

**External imports:** `SubscriptionHandle` from `k1.fabric.ports.event_port`

---

### PORT 8: `IWorkflowStoragePort` — [ports/workflow_storage_port.py](k1/orchestrator/ports/workflow_storage_port.py)

**Direction:** OUTBOUND (Orchestrator persists workflow data to SQLite)
**Sync/Async:** ASYNC

| Method | Parameters | Return | Lines |
|--------|-----------|--------|-------|
| `save_workflow` | `spec: WorkflowSpec` | `None` | L62 |
| `get_workflow` | `workflow_id: str` | `Optional[WorkflowSpec]` | L65 |
| `list_workflows` | `active_only: bool = True` | `List[WorkflowSpec]` | L68 |
| `delete_workflow` | `workflow_id: str` | `None` | L71 |
| `purge_workflow` | `workflow_id: str` | `None` | L74 |
| `save_trigger` | `workflow_id: str`, `trigger: TriggerSpec` | `None` | L78 |
| `get_due_triggers` | `now: float` | `List[Tuple[str, TriggerSpec]]` | L80-L85 |
| `update_trigger_state` | `workflow_id: str`, `next_fire: float`, `last_fire: float` | `None` | L101-L104 |
| `save_run` | `manifest: object` | `None` | L108-L112 |
| `get_runs` | `workflow_id: str`, `limit: int = 10` | `list` | L114 |
| `save_gap` | `gap: ProactiveGap` | `None` | L118 |
| `get_pending_gaps` | *(none)* | `List[ProactiveGap]` | L121 |

**TYPE_CHECKING imports:** `ProactiveGap`, `TriggerSpec` from `k1.orchestrator.types`; `WorkflowSpec` from `k1.orchestrator.workflows.workflow_types`

---

### PORT 9: `IAdminPort` — [ports/admin_port.py](k1/orchestrator/ports/admin_port.py)

**Direction:** INBOUND (Orchestrator implements for admin HTTP server)
**Sync/Async:** ASYNC

| # | Method | Parameters | Return | Lines |
|---|--------|-----------|--------|-------|
| 1 | `health_live` | *(none)* | `Dict[str, Any]` | L66-L72 |
| 2 | `health_ready` | *(none)* | `Dict[str, Any]` | L74-L80 |
| 3 | `health_status` | *(none)* | `HealthStatus` | L82-L94 |
| 4 | `list_active_dags` | *(none)* | `List[ActiveDAGInfo]` | L100-L105 |
| 5 | `get_dag_detail` | `dag_id: str` | `Optional[Dict[str, Any]]` | L107-L114 |
| 6 | `cancel_dag` | `dag_id: str` | `bool` | L116-L124 |
| 7 | `list_circuit_breakers` | *(none)* | `Dict[str, CircuitBreakerState]` | L130-L135 |
| 8 | `set_cb_state` | `name: str`, `state: str` | `bool` | L137-L148 |
| 9 | `list_triggers` | *(none)* | `List[Dict[str, Any]]` | L154-L159 |
| 10 | `get_trigger` | `workflow_id: str` | `Optional[Dict[str, Any]]` | L161-L170 |
| 11 | `drain` | `timeout_ms: int = 30000` | `DrainResult` | L176-L187 |
| 12 | `get_config` | *(none)* | `Dict[str, Any]` | L193-L198 |
| 13 | `get_mailbox_depth` | *(none)* | `Dict[str, Any]` | L204-L209 |
| 14 | `get_mailbox_stats` | *(none)* | `Dict[str, Any]` | L211-L218 |
| 15 | `list_mcp_servers` | *(none)* | `List[Dict[str, Any]]` | L224-L229 |
| 16 | `trigger_mcp_rediscovery` | *(none)* | `Dict[str, Any]` | L231-L236 |
| 17 | `get_metrics` | *(none)* | `Dict[str, Any]` | L242-L247 |
| 18 | `get_version` | *(none)* | `Dict[str, Any]` | L253-L258 |

**Contract types used:** `HealthStatus`, `ActiveDAGInfo`, `CircuitBreakerState`, `DrainResult` (all from `k1.orchestrator.types`)

---

### GUARD PROTOCOLS (4 protocols, in types.py)

These are NOT ports but are Protocol classes used in the guard pipeline.

**File:** [types.py](k1/orchestrator/types.py)

| Protocol | Method | Parameters | Return | Line |
|----------|--------|-----------|--------|------|
| `PreDispatchGuard` | `check` | `envelope: TaskEnvelope`, `ctx: ProcessingContext` | `GuardDecision` | ~L1393 |
| `IPreWaveGuard` | `evaluate_pre_wave` | `wave: Wave`, `ctx: ProcessingContext` | `List[GuardDecision]` | ~L1400 |
| `IPostStepGuard` | `evaluate_post_step` | `step: PlanStep`, `result: StepResult`, `ctx: ProcessingContext` | `GuardDecision` | ~L1408 |
| `IPostWaveGuard` | `evaluate_post_wave` | `wave_result: WaveResult`, `ctx: ProcessingContext` | `GuardDecision` | ~L1415 |

---

## EXHAUSTIVE CONTRACT / DTO REFERENCE

> Every dataclass, enum, and type alias in `k1/orchestrator/types.py` and `k1/orchestrator/workflows/workflow_types.py`.

**File:** [types.py](k1/orchestrator/types.py) (~1500 lines)

---

### ENUMS (Layer 1)

| Enum | Values | Used By | Lines |
|------|--------|---------|-------|
| `StepStatus(str, Enum)` | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `SKIPPED` | `StepResult.status`, DAGExecutor | ~L49-L62 |
| `TriggerType(str, Enum)` | `CRON`, `EVENT`, `MANUAL` | `TriggerSpec.type`, `WorkflowRunRequest.trigger_type` | ~L65-L72 |
| `ProcessResult(str, Enum)` | `COMPLETED`, `FAILED`, `DEGRADED`, `CANCELLED`, `DEFERRED` | `OrchestratorService.process()` return | ~L75-L85 |
| `ErrorSeverity(str, Enum)` | `RECOVERABLE`, `DEGRADED`, `TERMINAL` | `AdapterError.severity`, ErrorRouter | ~L88-L100 |
| `ProactiveGapStatus(str, Enum)` | `PENDING`, `ASKED`, `RESOLVED`, `AUTO_RESOLVED` | `ProactiveGap.status` | ~L103-L113 |
| `GuardAction(str, Enum)` | `ALLOW`, `REJECT`, `CONTINUE`, `RETRY`, `SKIP`, `HARD_STOP`, `DEGRADE`, `DEFER`, `BYPASS` | `GuardDecision.action` | ~L116-L143 |

---

### FROZEN DATACLASSES (Layer 2 — leaf types)

#### `AdapterError` (frozen) — ~L159-L181
| Field | Type | Default |
|-------|------|---------|
| `severity` | `ErrorSeverity` | *(required)* |
| `adapter_name` | `str` | *(required)* |
| `operation` | `str` | *(required)* |
| `error_code` | `str` | *(required)* |
| `error_message` | `str` | *(required)* |
| `original_exception` | `Optional[Exception]` | `None` |
| `fallback_action` | `str` | `""` |
| `trace_id` | `str` | `""` |
**Used by:** All adapter error wrapping → ErrorRouter.route_error()

#### `ErrorAction` (frozen) — ~L184-L199
| Field | Type | Default |
|-------|------|---------|
| `action` | `str` | *(required)* — `"RETRY"` / `"FALLBACK"` / `"DEGRADE"` / `"ABORT"` |
| `retry_count` | `int` | `0` |
| `fallback_value` | `Optional[Any]` | `None` |
| `reason` | `str` | `""` |
**Used by:** Return of ErrorRouter.route_error()

#### `OrchestratorPolicies` (frozen) — ~L202-L214
| Field | Type | Default |
|-------|------|---------|
| `normal_retries` | `int` | `2` |
| `schema_retries` | `int` | `1` |
| `step_timeout_default_ms` | `int` | `30000` |
| `max_steps_per_plan` | `int` | `50` |
| `max_waves_per_plan` | `int` | `20` |
| `max_concurrent_per_wave` | `int` | `10` |
**Used by:** StepRunner (retry budgets, timeouts), DAGExecutor (caps)

#### `CompensationRecord` (mutable) — ~L217-L237
| Field | Type | Default |
|-------|------|---------|
| `dag_id` | `str` | *(required)* |
| `step_id` | `str` | *(required)* |
| `compensation_capability` | `str` | *(required)* |
| `compensation_params` | `Dict[str, Any]` | `{}` |
| `record_id` | `str` | `uuid4()` |
| `status` | `str` | `"PENDING"` |
| `initiated_at` | `float` | `time.time()` |
| `completed_at` | `Optional[float]` | `None` |
| `error_detail` | `Optional[str]` | `None` |
**Used by:** DAGExecutor._compensate() → AggregatedResult.compensations

#### `MCPServerRegistration` (frozen) — ~L250-L263
| Field | Type | Default |
|-------|------|---------|
| `server_id` | `str` | *(required)* |
| `server_type` | `str` | *(required)* — `"local"` or `"remote"` |
| `endpoint` | `str` | *(required)* |
| `registered_capabilities` | `List[str]` | `[]` |
| `registered_at` | `float` | `0.0` |
| `critical` | `bool` | `False` |
**Used by:** ConnectorLifecycleManager (5.1.3)

#### `InterruptRequest` (frozen) — ~L266-L294
| Field | Type | Default |
|-------|------|---------|
| `target_dag_id` | `Optional[str]` | `None` |
| `interrupt_type` | `str` | `"CANCEL_DAG"` — allowed: `{"CANCEL_DAG", "PAUSE"}` |
| `reason` | `str` | `""` |
| `trace_id` | `str` | `""` (validated non-empty) |
| `request_id` | `str` | `uuid4()` |
**Used by:** MailboxMessage union, OrchestratorService.handle_interrupt()
**Validation:** `interrupt_type` must be in `_ALLOWED_TYPES`; `trace_id` required

#### `TriggerSpec` (frozen) — ~L297-L326
| Field | Type | Default |
|-------|------|---------|
| `type` | `TriggerType` | *(required)* |
| `schedule` | `Optional[str]` | `None` |
| `timezone` | `str` | `"UTC"` |
| `event_topic` | `Optional[str]` | `None` |
| `enabled` | `bool` | `True` |
**Used by:** WorkflowSaveRequest.trigger_spec, WorkflowSpec.trigger, IWorkflowStoragePort
**Validation:** CRON→schedule required; EVENT→event_topic required; MANUAL→both None

#### `ConditionExpr` (frozen) — ~L329-L342
| Field | Type | Default |
|-------|------|---------|
| `type` | `str` | *(required)* — `AND`, `OR`, `NOT`, `EQ`, `NEQ`, `GT`, `LT` |
| `operands` | `List[Any]` | `[]` |
| `path` | `Optional[str]` | `None` |
| `literal` | `Optional[Any]` | `None` |
**Used by:** PlanStep.condition (ORCH-16 conditional edges)

#### `Discovery` (frozen) — ~L345-L352
| Field | Type | Default |
|-------|------|---------|
| `field` | `str` | *(required)* |
| `value` | `Any` | `None` |
| `source_step_id` | `str` | `""` |
**Used by:** MicroReplanRequest.discoveries

#### `FailureContext` (frozen) — ~L355-L365
| Field | Type | Default |
|-------|------|---------|
| `step_id` | `str` | *(required)* |
| `error_code` | `str` | *(required)* |
| `error_message` | `str` | *(required)* |
| `partial_result` | `Optional[Dict[str, Any]]` | `None` |
**Used by:** MicroReplanRequest.failure_context

#### `SchemaResult` (frozen) — ~L368-L377
| Field | Type | Default |
|-------|------|---------|
| `valid` | `bool` | *(required)* |
| `errors` | `List[str]` | `[]` |
| `suggestion` | `Optional[str]` | `None` |
**Used by:** OutputSchemaGuard (ORCH-15)

#### `AlternativeMapping` (frozen) — ~L380-L389
| Field | Type | Default |
|-------|------|---------|
| `original_capability` | `str` | *(required)* |
| `replacement_capability` | `str` | *(required)* |
| `reason` | `str` | *(required)* |
**Used by:** ValidationResult.alternatives_applied, ResolutionResult.alternatives_applied

#### `AlternativeCapability` (frozen) — ~L392-L406
| Field | Type | Default |
|-------|------|---------|
| `capability_id` | `str` | *(required)* |
| `score` | `float` | *(required)* |
| `param_mapping` | `Dict[str, str]` | `{}` |
| `safety_band` | `str` | `"GREEN"` |
**Used by:** ConstraintResolver.find_alternatives() (3.1.3)

#### `ValidationResult` (frozen) — ~L409-L428
| Field | Type | Default |
|-------|------|---------|
| `valid` | `bool` | *(required)* |
| `errors` | `List[str]` | `[]` |
| `warnings` | `List[str]` | `[]` |
| `alternatives_applied` | `List[AlternativeMapping]` | `[]` |
| `time_pressure` | `bool` | `False` |
| `hil_required` | `bool` | `False` |
| `hil_request` | `Optional[HILRequest]` | `None` |
**Used by:** ConstraintResolver.validate() return

#### `CapabilityCheck` (frozen) — ~L431-L446
| Field | Type | Default |
|-------|------|---------|
| `step_id` | `str` | *(required)* |
| `capability` | `str` | *(required)* |
| `available` | `bool` | *(required)* |
| `contract_entry` | `Optional[RegistryEntry]` | `None` |
| `alternatives` | `List[str]` | `[]` |
**Used by:** ConstraintResolver.check_capabilities() return, ResolutionResult.unresolved

#### `ResolutionResult` (frozen) — ~L449-L466
| Field | Type | Default |
|-------|------|---------|
| `resolved` | `bool` | *(required)* |
| `modified_plan` | `Optional[Any]` | `None` |
| `unresolved` | `List[CapabilityCheck]` | `[]` |
| `hil_requested` | `bool` | `False` |
| `cycles_used` | `int` | `0` |
| `alternatives_applied` | `List[AlternativeMapping]` | `[]` |
**Used by:** ConstraintResolver.resolve_iteratively() return

#### `RegistryEntry` (frozen) — ~L469-L481
| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | *(required)* |
| `provider_type` | `str` | *(required)* |
| `safety_band_min` | `str` | *(required)* |
| `availability` | `str` | *(required)* |
| `compensation_capability` | `Optional[str]` | `None` |
| `estimated_duration_ms` | `Optional[int]` | `None` |
**Used by:** IFabricGatewayPort.query_registry() return, CapabilityCheck.contract_entry

#### `HILRequest` (frozen) — ~L484-L494
| Field | Type | Default |
|-------|------|---------|
| `request_id` | `str` | *(required)* |
| `question` | `str` | *(required)* |
| `options` | `List[str]` | `[]` |
| `context` | `Dict[str, Any]` | `{}` |
| `timeout_ms` | `int` | `120_000` |
**Used by:** IDeltaEmitPort.emit_hil_request() input, ValidationResult.hil_request

#### `PlanAck` (frozen) — ~L497-L504
| Field | Type | Default |
|-------|------|---------|
| `request_id` | `str` | *(required)* |
| `status` | `str` | *(required)* — `"ACCEPTED"` or `"REJECTED"` |
| `estimated_duration_ms` | `Optional[int]` | `None` |
**Used by:** IPlannerPort.request_plan() return

#### `TaskAck` (frozen) — ~L507-L514
| Field | Type | Default |
|-------|------|---------|
| `envelope_id` | `str` | *(required)* |
| `status` | `str` | *(required)* — `"ACCEPTED"`, `"DUPLICATE"`, `"REJECTED_FULL"` |
| `estimated_duration_ms` | `Optional[int]` | `None` |
**Used by:** OrchestratorService.process() → Concierge acknowledgment

---

### CORE ENVELOPES (Layer 3)

#### `TaskEnvelope` (frozen) — ~L522-L571
| Field | Type | Default |
|-------|------|---------|
| `intent` | `str` | *(required, validated non-empty)* |
| `trace_id` | `str` | *(required, validated non-empty)* |
| `caller_id` | `str` | `""` |
| `envelope_id` | `str` | `uuid4()` |
| `context` | `Dict[str, Any]` | `{}` |
| `tier` | `str` | `"MEDIUM"` — validated: `{"MEDIUM", "HIGH"}` only |
| `capabilities` | `List[str]` | `[]` — MEDIUM: required non-empty, max 2 |
| `params` | `Dict[str, Dict[str, Any]]` | `{}` |
| `constraints` | `Dict[str, Any]` | `{}` |
| `timeout_ms` | `int` | `30_000` |
**Used by:** IMailboxPort (MailboxMessage union), OrchestratorService.process() input

#### `StepResult` (frozen) — ~L574-L630
| Field | Type | Default |
|-------|------|---------|
| `step_id` | `str` | *(required)* |
| `capability_name` | `str` | *(required)* |
| `status` | `StepStatus` | *(required)* |
| `duration_ms` | `int` | `0` |
| `result` | `Optional[CapabilityResult]` | `None` |
| `retry_attempts` | `int` | `0` |
| `schema_retry` | `bool` | `False` |
| `error_detail` | `Optional[str]` | `None` |
**Methods:** `to_dict() -> Dict`, `from_dict(data) -> StepResult`
**Used by:** DAGExecutor → AggregatedResult.step_results, MicroReplanRequest.completed_results

#### `PlanStep` (frozen, 14 fields) — ~L633-L772
| Field | Type | Default | Origin |
|-------|------|---------|--------|
| `id` | `str` | `""` (validated non-empty) | Fabric-aligned |
| `capability` | `str` | `""` (validated non-empty) | Fabric-aligned |
| `params` | `Dict[str, Any]` | `{}` | Fabric-aligned |
| `deps` | `List[str]` | `[]` | Fabric-aligned |
| `prompt_template` | `Optional[str]` | `None` | Fabric-aligned |
| `tools_granted` | `Optional[List[str]]` | `None` | Fabric-aligned |
| `output_schema` | `Optional[Dict[str, Any]]` | `None` | Orch extension |
| `condition` | `Optional[ConditionExpr]` | `None` | Orch extension |
| `is_optional` | `bool` | `False` | Orch extension |
| `has_side_effects` | `bool` | `False` | Orch extension |
| `compensation` | `Optional[str]` | `None` | Orch extension |
| `timeout_ms` | `Optional[int]` | `None` (validated >0) | Orch extension |
| `required_context` | `Optional[List[str]]` | `None` | Orch extension |
| `safety_band_min` | `Optional[str]` | `None` | Orch extension |
**Methods:** `to_dict()`, `from_dict(data)`, `from_fabric(fabric_step, **extensions)`
**Used by:** CommittedPlan.steps, Wave.steps, WorkflowSpec.steps

#### `Wave` (mutable) — ~L775-L786
| Field | Type | Default |
|-------|------|---------|
| `wave_index` | `int` | *(required)* |
| `steps` | `List[PlanStep]` | `[]` |
| `resolved_params` | `Dict[str, Dict[str, Any]]` | `{}` |
**Used by:** DAGExecutor internal, IPreWaveGuard.evaluate_pre_wave(), PendingHILContext.remaining_waves

---

### PLAN & RESULT TYPES (Layer 4)

#### `WaveResult` (frozen) — ~L794-L802
| Field | Type | Default |
|-------|------|---------|
| `wave_index` | `int` | *(required)* |
| `step_results` | `List[StepResult]` | `[]` |
| `duration_ms` | `int` | `0` |
**Used by:** PendingHILContext.completed_waves, IPostWaveGuard.evaluate_post_wave()

#### `PlanRequest` (frozen) — ~L805-L833
| Field | Type | Default |
|-------|------|---------|
| `intent` | `str` | *(required, validated non-empty)* |
| `trace_id` | `str` | *(required, validated non-empty)* |
| `context` | `Optional[SessionSnapshot]` | `None` |
| `request_id` | `str` | `uuid4()` |
| `constraints` | `Dict[str, Any]` | `{}` |
| `timeout_ms` | `int` | `45_000` |
**Used by:** IPlannerPort.request_plan() input

#### `CommittedPlan` (frozen) — ~L836-L942
| Field | Type | Default |
|-------|------|---------|
| `plan_id` | `str` | *(required, validated non-empty)* |
| `request_id` | `str` | *(required, validated non-empty)* |
| `intent` | `str` | *(required)* |
| `steps` | `List[PlanStep]` | *(required, validated non-empty)* |
| `trace_id` | `str` | *(required)* |
| `dependencies` | `Dict[str, List[str]]` | `{}` (validated: keys/values ⊆ step IDs, acyclic) |
| `estimated_duration_ms` | `Optional[int]` | `None` |
| `created_at` | `float` | `0.0` |
**Methods:** `to_dict()`, `from_dict(data)`, `_check_acyclic()` (Kahn's)
**Used by:** MailboxMessage union, IPlannerPort.micro_replan() return, DAGExecutor input, WorkflowCompiler output

#### `AggregatedResult` (frozen) — ~L945-L1050
| Field | Type | Default |
|-------|------|---------|
| `total_steps` | `int` | *(required)* |
| `completed` | `int` | *(required)* |
| `failed` | `int` | *(required)* |
| `cancelled` | `int` | *(required)* |
| `skipped` | `int` | *(required)* |
| `step_results` | `List[StepResult]` | *(required)* |
| `success` | `bool` | *(required)* — computed: `failed == 0 and cancelled == 0` |
| `duration_ms` | `int` | *(required)* |
| `trace_id` | `str` | *(required)* |
| `result_id` | `str` | `uuid4()` |
| `plan_id` | `Optional[str]` | `None` |
| `compensations` | `List[CompensationRecord]` | `[]` |
**Factory methods:** `from_medium(step_results, trace_id, duration_ms)`, `from_dag(plan_id, step_results, compensations, trace_id, duration_ms)`
**Methods:** `to_dict()`
**Used by:** OrchestratorService return → IDeltaEmitPort, IBridgeWritePort.submit_audit()

#### `MicroReplanRequest` (frozen) — ~L1053-L1104
| Field | Type | Default |
|-------|------|---------|
| `original_plan_id` | `str` | *(required, validated non-empty)* |
| `completed_results` | `Dict[str, StepResult]` | *(required)* |
| `remaining_steps` | `List[PlanStep]` | *(required, validated non-empty)* |
| `trace_id` | `str` | *(required)* |
| `request_id` | `str` | `uuid4()` |
| `discoveries` | `List[Discovery]` | `[]` |
| `failure_context` | `Optional[FailureContext]` | `None` |
**Methods:** `to_dict()`
**Used by:** IPlannerPort.micro_replan() input

---

### WORKFLOW TYPES (Layer 5)

#### `WorkflowRunRequest` (frozen) — ~L1113-L1140
| Field | Type | Default |
|-------|------|---------|
| `workflow_id` | `str` | *(required, validated non-empty)* |
| `version` | `str` | *(required)* |
| `trigger_type` | `TriggerType` | *(required)* |
| `trace_id` | `str` | *(required)* |
| `request_id` | `str` | `uuid4()` |
| `trigger_context` | `Dict[str, Any]` | `{}` |
| `param_overrides` | `Dict[str, Any]` | `{}` |
| `priority` | `str` | `"INTERACTIVE"` |
**Used by:** MailboxMessage union, WorkflowScheduler → IMailboxPort

#### `WorkflowSaveRequest` (frozen) — ~L1143-L1166
| Field | Type | Default |
|-------|------|---------|
| `committed_plan_id` | `str` | *(required, validated non-empty)* |
| `workflow_name` | `str` | *(required, validated non-empty)* |
| `trigger_spec` | `TriggerSpec` | *(required)* |
| `trace_id` | `str` | *(required)* |
| `request_id` | `str` | `uuid4()` |
**Used by:** MailboxMessage union, Concierge → IMailboxPort

#### `ProactiveGap` (mutable) — ~L1169-L1198
| Field | Type | Default |
|-------|------|---------|
| `workflow_id` | `str` | *(required)* |
| `gap_type` | `str` | *(required)* — `SCHEMA_DRIFT`, `CAPABILITY_REMOVED`, `PERMISSION_CHANGE` |
| `affected_step_id` | `str` | *(required)* |
| `capability_name` | `str` | *(required)* |
| `old_contract_version` | `str` | *(required)* |
| `new_contract_version` | `str` | *(required)* |
| `description` | `str` | *(required)* |
| `justification` | `str` | *(required)* |
| `gap_id` | `str` | `uuid4()` |
| `detected_at` | `float` | `time.time()` |
| `question` | `Optional[str]` | `None` |
| `status` | `ProactiveGapStatus` | `PENDING` |
| `resolved_value` | `Optional[str]` | `None` |
**Used by:** IWorkflowStoragePort, GapDetector, CompilationResult.gaps

---

### CONTEXT TYPES (Layer 6)

#### `ProcessingContext` (mutable) — ~L1207-L1244
| Field | Type | Default |
|-------|------|---------|
| `trace_id` | `str` | *(required, validated non-empty)* |
| `request_id` | `str` | *(required, validated non-empty)* |
| `tier` | `str` | *(required)* |
| `created_at` | `float` | `time.time()` |
| `deadline_ms` | `Optional[int]` | `None` |
| `dag_id` | `Optional[str]` | `None` |
| `workflow_id` | `Optional[str]` | `None` |
| `parent_trace_id` | `Optional[str]` | `None` |
| `current_wave` | `Optional[int]` | `None` |
| `current_step_id` | `Optional[str]` | `None` |
| `session_id` | `Optional[str]` | `None` |
| `user_id` | `Optional[str]` | `None` |
| `interrupt_flag` | `bool` | `False` |
**Used by:** All guard Protocol methods, DAGExecutor, StepRunner, ErrorRouter — threaded through every internal call

#### `PendingPlanContext` (mutable) — ~L1250-L1263
| Field | Type | Default |
|-------|------|---------|
| `request_id` | `str` | *(required)* |
| `task_envelope` | `TaskEnvelope` | *(required)* |
| `state_snapshot` | `SessionSnapshot` | *(required)* |
| `created_at` | `float` | `time.time()` |
| `timeout_ms` | `int` | `45_000` |
**Used by:** OrchestratorService.pending_plans dict (keyed by request_id)

#### `PendingHILContext` (mutable) — ~L1266-L1289
| Field | Type | Default |
|-------|------|---------|
| `request_id` | `str` | *(required)* |
| `dag_execution_id` | `str` | *(required)* |
| `current_wave_index` | `int` | *(required)* |
| `completed_waves` | `List[WaveResult]` | *(required)* |
| `remaining_waves` | `List[Wave]` | *(required)* |
| `question` | `str` | *(required)* |
| `options` | `List[str]` | *(required)* |
| `timeout_fallback` | `str` | *(required)* — `"CONTINUE"` or `"GRACEFUL_FAIL"` |
| `created_at` | `float` | `time.time()` |
| `timeout_ms` | `int` | `120_000` |
**Used by:** OrchestratorService.pending_hil dict (keyed by request_id)

---

### CB / GUARD / ADMIN TYPES (Layer 7)

#### `CircuitBreakerConfig` (frozen) — ~L1298-L1309
| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | *(required)* |
| `failure_threshold` | `int` | *(required)* |
| `reset_timeout_ms` | `int` | *(required)* |
| `half_open_max_probes` | `int` | `1` |
**Used by:** CircuitBreakerState.config

#### `CircuitBreakerState` (mutable) — ~L1312-L1376
| Field | Type | Default |
|-------|------|---------|
| `config` | `CircuitBreakerConfig` | *(required)* |
| `state` | `str` | `"CLOSED"` — `CLOSED` / `OPEN` / `HALF_OPEN` |
| `failure_count` | `int` | `0` |
| `last_failure_at` | `Optional[float]` | `None` |
| `last_success_at` | `Optional[float]` | `None` |
| `opened_at` | `Optional[float]` | `None` |
| `_half_open_probes` | `int` | `0` |
**Methods:** `record_success()`, `record_failure()`, `should_allow_request() -> bool`, `check_reset_timeout() -> bool`
**Used by:** PlannerAdapter (CB_PLANNER), IAdminPort.list_circuit_breakers()

#### `GuardDecision` (frozen) — ~L1379-L1389
| Field | Type | Default |
|-------|------|---------|
| `guard_name` | `str` | *(required)* |
| `action` | `GuardAction` | *(required)* |
| `reason` | `str` | *(required)* |
| `degraded_to` | `Optional[str]` | `None` |
| `metadata` | `Dict[str, Any]` | `{}` |
**Used by:** All 4 Guard Protocol returns

#### `HealthStatus` (frozen) — ~L1449-L1459
| Field | Type | Default |
|-------|------|---------|
| `status` | `str` | *(required)* — `HEALTHY` / `DEGRADED` / `UNHEALTHY` |
| `uptime_ms` | `int` | *(required)* |
| `active_dags` | `int` | *(required)* |
| `mailbox_depth` | `int` | *(required)* |
| `circuit_breakers` | `Dict[str, str]` | `{}` |
| `last_error` | `Optional[str]` | `None` |
**Used by:** IAdminPort.health_status() return

#### `ActiveDAGInfo` (frozen) — ~L1462-L1476
| Field | Type | Default |
|-------|------|---------|
| `dag_id` | `str` | *(required)* |
| `plan_id` | `str` | *(required)* |
| `current_wave` | `int` | *(required)* |
| `total_waves` | `int` | *(required)* |
| `steps_completed` | `int` | *(required)* |
| `steps_failed` | `int` | *(required)* |
| `started_at` | `float` | *(required)* |
| `trace_id` | `str` | *(required)* |
**Used by:** IAdminPort.list_active_dags() return

#### `DrainResult` (frozen) — ~L1479-L1490
| Field | Type | Default |
|-------|------|---------|
| `drained` | `bool` | *(required)* |
| `active_dags_remaining` | `int` | *(required)* |
| `timeout_reached` | `bool` | *(required)* |
| `duration_ms` | `int` | *(required)* |
**Used by:** IAdminPort.drain() return

#### `RecoveryResult` (mutable) — ~L1493-L1506
| Field | Type | Default |
|-------|------|---------|
| `recovered_dags` | `int` | `0` |
| `failed_recoveries` | `int` | `0` |
| `skipped` | `int` | `0` |
**Used by:** OrchestratorService.crash_recovery() return

---

### WORKFLOW-SPECIFIC TYPES (in `k1/orchestrator/workflows/workflow_types.py`)

#### `DynamicExpr` (frozen) — [workflow_types.py](k1/orchestrator/workflows/workflow_types.py) ~L70-L98
| Field | Type | Default |
|-------|------|---------|
| `raw` | `str` | *(required)* |
| `namespace` | `str` | *(required)* |
| `field` | `str` | *(required)* |
| `offset` | `Optional[str]` | `None` |
**Static method:** `parse(value: str) -> Optional[DynamicExpr]`
**Used by:** WorkflowCompiler resolves these in PlanStep.params values

#### `WorkflowSpec` (frozen) — ~L104-L148
| Field | Type | Default |
|-------|------|---------|
| `workflow_id` | `str` | *(required)* |
| `name` | `str` | *(required, validated non-empty)* |
| `source_plan_id` | `str` | *(required)* |
| `version` | `str` | *(required, validated semver)* |
| `trigger` | `TriggerSpec` | *(required)* |
| `steps` | `List[PlanStep]` | `[]` (validated non-empty) |
| `dependencies` | `Dict[str, List[str]]` | `{}` |
| `active` | `bool` | `True` |
| `created_at` | `float` | `time.time()` |
| `updated_at` | `float` | `time.time()` |
| `created_by` | `str` | `"system"` |
**Used by:** IWorkflowStoragePort, WorkflowRegistry, WorkflowCompiler

#### `VersionEntry` (frozen) — ~L155-L163
| Field | Type | Default |
|-------|------|---------|
| `version` | `str` | *(required)* |
| `created_at` | `float` | *(required)* |
| `source_plan_id` | `str` | *(required)* |
| `step_count` | `int` | *(required)* |
| `change_summary` | `str` | *(required)* |
**Used by:** WorkflowVersionPointer.version_history

#### `WorkflowVersionPointer` (mutable) — ~L166-L177
| Field | Type | Default |
|-------|------|---------|
| `workflow_id` | `str` | *(required)* |
| `active_version` | `str` | *(required)* |
| `version_history` | `List[VersionEntry]` | `[]` |
**Used by:** WorkflowRegistry internal

#### `CompilationResult` (mutable) — ~L184-L197
| Field | Type | Default |
|-------|------|---------|
| `success` | `bool` | *(required)* |
| `compiled_plan` | `Optional[CommittedPlan]` | `None` |
| `gaps` | `List[ProactiveGap]` | `[]` |
| `auto_resolved` | `List[str]` | `[]` |
| `compiled_hash` | `Optional[str]` | `None` |
**Used by:** WorkflowCompiler.compile() return → WorkflowRunSupervisor

#### `RunStatus(Enum)` — ~L204-L217
| Value | Meaning |
|-------|---------|
| `RUNNING` | Execution in progress |
| `COMPLETED` | DAG finished successfully |
| `FAILED` | DAG failed or compilation failed |
| `ABORTED` | Concurrent run policy aborted this run |
**Used by:** RunManifest.status

#### `RunManifest` (frozen) — ~L222-L280+
| Field | Type | Default |
|-------|------|---------|
| `run_id` | `str` | *(required)* |
| `workflow_id` | `str` | *(required)* |
| `version` | `str` | *(required)* |
| `compiled_hash` | `str` | *(required)* |
| `trigger_type` | `str` | *(required)* |
| `status` | `RunStatus` | *(required)* |
| `started_at` | `float` | *(required)* |
| `completed_at` | `Optional[float]` | `None` |
| `result_summary` | `Optional[Dict[str, Any]]` | `None` |
| `error_message` | `Optional[str]` | `None` |
| `steps_completed` | `int` | `0` |
| `steps_total` | `int` | `0` |
**Factory:** `create(workflow_id, version, compiled_hash, trigger_type, total_steps) -> RunManifest`
**Transitions:** `complete(result_summary)`, `fail(error_message)`, `abort()`
**Used by:** IWorkflowStoragePort.save_run(), WorkflowRunSupervisor

---

### EXTERNAL TYPES CONSUMED (from Fabric)

| Type | Source | Used By |
|------|--------|---------|
| `CapabilityRequest` | `k1.fabric.types` (L118) | IFabricGatewayPort.execute/execute_batch |
| `CapabilityResult` | `k1.fabric.types` (L306) | IFabricGatewayPort return, StepResult.result |
| `PlanStep` (as `FabricPlanStep`) | `k1.fabric.types` | PlanStep.from_fabric() mapping source |
| `Tier` | `k1.fabric.types` | TaskEnvelope._VALID_TIERS |
| `SessionSnapshot` | `k1.fabric.ports.state_reader` (L48) | IStateReadPort.get_snapshot() return, PlanRequest.context |
| `SubscriptionHandle` | `k1.fabric.ports.event_port` (L56) | IEventSubscriptionPort.subscribe() return |

---

### TOTALS SUMMARY

| Category | Count |
|----------|-------|
| Port Protocols | **9** (IMailbox, IFabricGateway, IPlanner, IStateRead, IDeltaEmit, IBridgeWrite, IEventSubscription, IWorkflowStorage, IAdmin) |
| Guard Protocols | **4** (PreDispatch, IPreWave, IPostStep, IPostWave) |
| Total port methods | **55** |
| Total guard methods | **4** |
| Enums | **7** (StepStatus, TriggerType, ProcessResult, ErrorSeverity, ProactiveGapStatus, GuardAction, RunStatus) |
| Frozen dataclasses | **30** |
| Mutable dataclasses | **8** (CompensationRecord, CircuitBreakerState, ProcessingContext, PendingPlanContext, PendingHILContext, ProactiveGap, WorkflowVersionPointer, CompilationResult + RecoveryResult) |
| Type aliases | **1** (MailboxMessage) |
| External types consumed | **6** (from k1.fabric) |
| Event topic constants | **31** (19 emitted + 12 consumed) |

**Async delivery:** If callback provided + plan scripted, schedules `_deliver_plan()` with 0.01s delay — correctly simulates event-driven planner.

**Assertion API:** `assert_plan_requested()`, `assert_cancel_requested()`, `assert_micro_replan_requested()`, `reset()`

**Phase 1 verdict:** Fully ready. Tests can pre-script exactly what plans the mock returns per request_id, including failure paths and async delivery.

---

## OrchestratorService Core (2,257 LOC)

**File:** `k1/orchestrator/orchestration/orchestrator_service.py`

### Constructor (keyword-only, 15 params)

```python
def __init__(self, *, mailbox, dag_executor, constraint_resolver, workflow_engine,
             connector_lifecycle, error_router, concurrency_guard,
             fabric_port, planner_port, state_port, delta_port,
             bridge_port, event_port, config, metrics=None)
```

- 7 port references (IMailboxPort, IFabricGatewayPort, IPlannerPort, IStateReadPort, IDeltaEmitPort, IBridgeWritePort, IEventSubscriptionPort)
- 6 collaborator protocols (DAGExecutorLike, ConstraintResolverLike, WorkflowEngineLike, ConnectorLifecycleLike, ErrorRouterLike, ConcurrencyGuardLike)
- config + optional metrics
- Uses `__slots__` (21 slots), fully async

### 6 Collaborator Protocols (defined in same file)

`DAGExecutorLike`, `ConstraintResolverLike`, `WorkflowEngineLike`, `ConnectorLifecycleLike`, `ErrorRouterLike`, `ConcurrencyGuardLike` — all `@runtime_checkable Protocol`.

### Key Public Methods

- `init()` — 10-step async startup
- `shutdown()` — graceful teardown
- `crash_recovery()` → `RecoveryResult`
- `process(message: MailboxMessage)` → `ProcessResult` (isinstance dispatch)

---

## Full Package Structure

```
k1/orchestrator/
├── __init__.py
├── ARCHITECTURE.md
├── config.py / events.py / metrics.py / tracing.py / types.py
├── factory.py                              (560 LOC)
├── ports/                                  (9 ports, ~1,099 LOC)
├── orchestration/
│   ├── orchestrator_service.py             (2,257 LOC)
│   ├── dag_executor.py / step_runner.py / error_router.py
│   ├── constraint_resolver.py / param_resolver.py
│   └── guards/
├── adapters/                               (9 prod + 4 mock + 4 test = 17)
├── connectors/                             (MCP: lifecycle, discovery, registrar, k0_proxy)
├── workflows/                              (engine, compiler, scheduler, supervisor, registry, gap_detector, cross_resolver)
│   └── persistence/
└── docs/
```

---

## Anomalies & Risks

| # | Anomaly | Severity | Action |
|---|---------|----------|--------|
| 1 | `ports/__init__.py` says "8 ports", actually 9 | Low | Fix docstring |
| 2 | `IBridgeWritePort` has read methods (`read_wal`, `list_wal_ids`) | Medium | Consider rename to `IBridgePersistencePort` |
| 3 | `IWorkflowStoragePort.save_run(manifest: object)` — lost type safety | Medium | Use `TYPE_CHECKING` forward ref |
| 4 | No Planner hot-swap — Phase 2 will need `PlannerProxy` wrapper | High | Track in Milestone 3 |
| 5 | `AdminHttpAdapter` accesses 6 private OrchestratorService fields | Medium | Known boundary violation — admin is "god adapter" |
| 6 | `AdminHttpAdapter.list_circuit_breakers()` — `isinstance` bug (checks `CircuitBreakerState` on `CircuitBreaker` object) | High | Always returns empty dict — fix needed |
| 7 | `WorkflowStorageAdapter` wraps `IWorkflowStoragePort` interface (adapter-over-adapter) | Low | Extra indirection, functional |
| 8 | `adapters/__init__.py` docstring says "16 adapters", actually 17 | Low | Fix docstring |
| 9 | `PlannerAdapter` types `planner_mailbox: Any` despite defining `IPlannerMailbox` Protocol | Low | Type should be `IPlannerMailbox` |
| 10 | `IAdminPort` has NO mock or test adapter | Medium | Need one for integration tests |
| 11 | `TestMailboxAdapter` missing `reset()` method | Low | Must re-instantiate between tests |
| 12 | `MockFabricAdapter` has unused `cancel_log` | Low | Dead code |
| 13 | Factory step numbering non-sequential (1,2,11,12,13,14a,14b,15) | Low | Matches external spec but confusing |

---

## Comparison With Prior Epics

| Dimension | Bus (1.1) | SessionState (1.2) | Fabric (1.3) | ModelHub (1.4) | **Orchestrator (1.5)** |
|-----------|----------|-------------------|-------------|---------------|----------------------|
| Port style | Protocol | ABC | Protocol | Protocol | **Protocol** |
| Port count | 3 | 5 | 6 | 7 | **9** |
| Factory LOC | ~200 | ~180 | ~350 | ~280 | **560** |
| Prod adapters | 2 | 4+5 stub | 9 all REAL | 3+6 semi | **9 all REAL** |
| Test doubles | 3 middleware | 1 test | 0 | 0 | **4 mock + 4 test** |
| Stubs | 0 | 5 (NotImplementedError) | 0 | 0 | **0** |
| Core LOC | ~800 | ~2,430 | ~1,400 | ~1,100 | **2,257** |
| Cross-module imports | 0 | 1 (fabric) | 0 | 1 (bus) | **3 (fabric types, snapshot, handle)** |

**Orchestrator is the LARGEST and MOST COMPLETE component** — 9 ports, 17 adapters (all real), 560-LOC factory, 2,257-LOC service. It is the most complex wiring target for the kernel bootstrap.
