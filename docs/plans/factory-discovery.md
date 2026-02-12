# OrchestratorFactory Discovery Document

> **Purpose**: Comprehensive reference for building issue 6.2.1 (OrchestratorFactory).
> Gathered from orchestrator-implementation-plan.md M1-M6.2 + full code discovery.
>
> **Target file**: `k1/orchestrator/factory.py` (does NOT exist yet)

---

## 1. Factory Methods (Static, No Constructor)

```
OrchestratorFactory            -- NO constructor, static methods only
  create_production(config)    -- async, full prod stack, calls init() automatically
  create_standalone()          -- async, all test adapters, NO init(), < 10ms
  create_for_testing(overrides)-- async, test adapters + optional overrides, NO init()
  create_with_ports(**ports)   -- async, caller provides exact adapters, NO init()
  _construct_orchestrator(config, adapters) -- private, 15-step wiring
```

---

## 2. OrchestratorConfig (Already Exists)

**File**: `k1/orchestrator/config.py:47`
**Class**: `OrchestratorConfig` -- frozen dataclass, validated in `__post_init__`

| Group | Key Fields | Defaults |
|-------|-----------|----------|
| Concurrency | `max_concurrent_dags=1`, `max_wave_parallelism=5`, `mailbox_capacity=100` | |
| Timeouts | `default_step_timeout_ms=30000`, `plan_request_timeout_ms=45000`, `hil_timeout_ms=120000`, `drain_timeout_ms=30000`, `shutdown_grace_period_ms=30000`, `context_reap_interval_ms=5000` | |
| Retry | `step_max_retries=2`, `step_retry_base_delay_ms=100`, `step_retry_max_delay_ms=5000` | |
| Guards | `guard_order=[ConcurrencyGuard, ConditionalEdgeEvaluator, OutputSchemaGuard, ExecutionMonitor, MicroReplanCheckpoint, SafetyBandReRead]`, `max_micro_replans=1`, `substep_rate_limit_ms=500` | |
| Workflow | `max_workflow_depth=3`, `workflow_db_path="data/orchestrator_workflows.db"`, `scheduler_tick_interval_ms=1000` | |
| MCP | `mcp_config_path="k1/connectors/mcp_servers.yaml"`, `mcp_discovery_interval_ms=300000`, `mcp_max_servers=10` | |
| CB | `cb_planner_failure_threshold=3`, `cb_planner_reset_timeout_ms=60000`, `cb_planner_half_open_probes=1` | |
| Telemetry | `metrics_enabled=True`, `admin_enabled=True`, `admin_port=8081` | |
| Pending | `max_pending_plans=50`, `max_pending_hil=20` | |

**Factory methods**:
- `OrchestratorConfig.default()` -- all defaults
- `OrchestratorConfig.from_dict(d)` -- from dict, unknown keys silently ignored

---

## 3. OrchestratorPolicies (Already Exists)

**File**: `k1/orchestrator/types.py:207`
**Class**: `OrchestratorPolicies` -- plain dataclass

| Field | Default | Consumer |
|-------|---------|----------|
| `normal_retries` | 2 | StepRunner |
| `schema_retries` | 1 | StepRunner |
| `step_timeout_default_ms` | 30000 | StepRunner |
| `max_steps_per_plan` | 50 | DAGExecutor |
| `max_waves_per_plan` | 20 | DAGExecutor |
| `max_concurrent_per_wave` | 10 | DAGExecutor |

**Note**: StepRunner needs OrchestratorPolicies, not OrchestratorConfig. Factory must create OrchestratorPolicies from OrchestratorConfig fields at construction time.

---

## 4. The 8 Ports (All Exist)

| # | Port | File | Methods |
|---|------|------|---------|
| 1 | `IMailboxPort` | `ports/mailbox_port.py` | `enqueue`, `dequeue`, `depth`, `peek_priority` |
| 2 | `IFabricGatewayPort` | `ports/fabric_gateway_port.py` | `execute`, `execute_batch`, `query_registry` |
| 3 | `IPlannerPort` | `ports/planner_port.py` | `request_plan`, `cancel_plan`, `micro_replan` |
| 4 | `IStateReadPort` | `ports/state_read_port.py` | `read_section`, `read_sections`, `get_snapshot` |
| 5 | `IDeltaEmitPort` | `ports/delta_emit_port.py` | `emit`, `emit_progress`, `emit_hil_request` |
| 6 | `IBridgeWritePort` | `ports/bridge_write_port.py` | `submit_audit`, `write_wal`, `read_wal` |
| 7 | `IEventSubscriptionPort` | `ports/event_subscription_port.py` | `subscribe`, `unsubscribe`, `emit` |
| 8 | `IWorkflowStoragePort` | `ports/workflow_storage_port.py` | 11 methods (save/get/list/delete workflow, triggers, runs, gaps) |

---

## 5. The 16 Adapters (All Exist -- Epic 6.1 COMPLETE)

### 5.1 Production Adapters (8)

| Adapter | File | Constructor Signature | External Dep |
|---------|------|----------------------|--------------|
| `MailboxAdapter` | `adapters/mailbox_adapter.py:94` | `(max_depth=100, wfq_weights=None)` | None |
| `FabricGatewayAdapter` | `adapters/fabric_gateway_adapter.py:69` | `(fabric: Fabric)` | k1.fabric Fabric instance |
| `PlannerAdapter` | `adapters/planner_adapter.py:105` | `(planner_mailbox: Any, cb_planner: CircuitBreaker)` | Planner mailbox + CB |
| `StateReadAdapter` | `adapters/state_read_adapter.py:64` | `(state_reader: ISessionStateReader)` | k1.sessionstate reader |
| `DeltaEmitAdapter` | `adapters/delta_emit_adapter.py:78` | `(event_port: IEventPort, delta_bus: IDeltaBusPort)` | K1 event + delta buses |
| `BridgeWriteAdapter` | `adapters/bridge_write_adapter.py:87` | `(bridge_client: IBridgeClient)` | K0 bridge client |
| `EventSubscriptionAdapter` | `adapters/event_subscription_adapter.py:58` | `(event_port: IEventPort)` | K1 event bus |
| `WorkflowStorageAdapter` | `adapters/workflow_storage_adapter.py:68` | `(storage: IWorkflowStoragePort)` | Inner impl (SQLiteWorkflowAdapter) |

### 5.2 Test Adapters (8)

| Adapter | File | Constructor Signature | Notes |
|---------|------|----------------------|-------|
| `TestMailboxAdapter` | `adapters/test_mailbox_adapter.py:43` | `()` | FIFO, unbounded |
| `MockFabricAdapter` | `adapters/mock_fabric_adapter.py:49` | `()` | Scriptable results/errors |
| `MockPlannerAdapter` | `adapters/mock_planner_adapter.py:52` | `(plan_callback=None)` | Optional callback |
| `MockStateReadAdapter` | `adapters/mock_state_read_adapter.py:45` | `()` | In-memory sections |
| `TestDeltaAdapter` | `adapters/test_delta_adapter.py:38` | `()` | Captures all events |
| `MockBridgeAdapter` | `adapters/mock_bridge_adapter.py:39` | `(wal_store=None)` | Optional pre-populated WAL |
| `TestEventAdapter` | `adapters/test_event_adapter.py:47` | `()` | Wildcard matching |
| `TestWorkflowStorageAdapter` | `adapters/test_workflow_storage_adapter.py:58` | `()` | In-memory dicts |

---

## 6. Service Constructor Signatures (All Exist)

### 6.1 OrchestratorService

**File**: `orchestration/orchestrator_service.py:204`
**Constructor**: ALL kwargs (keyword-only `*`):

```python
def __init__(
    self,
    *,
    mailbox: IMailboxPort,
    dag_executor: DAGExecutorLike,
    constraint_resolver: ConstraintResolverLike,
    workflow_engine: WorkflowEngineLike,
    connector_lifecycle: ConnectorLifecycleLike,
    error_router: ErrorRouterLike,
    concurrency_guard: ConcurrencyGuardLike,
    fabric_port: IFabricGatewayPort,
    planner_port: IPlannerPort,
    state_port: IStateReadPort,
    delta_port: IDeltaEmitPort,
    bridge_port: IBridgeWritePort,
    config: OrchestratorConfig,
) -> None
```

**Protocol stubs used** (file lines 80-148):
- `DAGExecutorLike` -- `execute(plan, ctx) -> AggregatedResult`
- `ConstraintResolverLike` -- `validate(plan, ctx) -> ValidationResultLike`
- `WorkflowEngineLike` -- `execute_workflow(request, ctx)`, `save_workflow(request, ctx)`
- `ConnectorLifecycleLike` -- empty Protocol
- `ErrorRouterLike` -- `classify(error, ctx) -> ErrorSeverity`
- `ConcurrencyGuardLike` -- `acquire(ctx) -> bool`, `release(ctx) -> None`

**IMPORTANT**: OrchestratorService does NOT take event_port (IEventSubscriptionPort) or storage_port (IWorkflowStoragePort) directly. Those are consumed by sub-services (workflow engine, gap detector, etc).

### 6.2 DAGExecutor

**File**: `orchestration/dag_executor.py:116`
**Constructor**: positional args

```python
def __init__(
    self,
    fabric_port: IFabricGatewayPort,
    planner_port: IPlannerPort,
    delta_port: IDeltaEmitPort,
    state_port: IStateReadPort,
    bridge_port: IBridgeWritePort,
    step_runner: Any,
    error_router: Any,
    guards: Optional[List[Any]] = None,
    param_resolver: Optional[Any] = None,
) -> None
```

9 deps total (5 ports + step_runner + error_router + guards + param_resolver).

### 6.3 ErrorRouter

**File**: `orchestration/error_router.py:44`
**Constructor**: 1 dep

```python
def __init__(self, delta_port: Any) -> None
```

### 6.4 StepRunner

**File**: `orchestration/step_runner.py:60`
**Constructor**: 3 deps

```python
def __init__(
    self,
    fabric_port: IFabricGatewayPort,
    error_router: ErrorRouter,
    policies: OrchestratorPolicies,
) -> None
```

### 6.5 ParamResolver

**File**: `orchestration/param_resolver.py:115`
**Constructor**: 1 optional dep

```python
def __init__(self, registry: Optional[RegistryPort] = None) -> None
```

### 6.6 ConstraintResolver

**File**: `orchestration/constraint_resolver.py:235`
**Constructor**: 4 deps (1 required, 3 optional)

```python
def __init__(
    self,
    fabric: IFabricGatewayPort,
    delta: Optional[IDeltaEmitPort] = None,
    events: Optional[IEventSubscriptionPort] = None,
    max_cycles: int = 3,  # DEFAULT_MAX_CYCLES
) -> None
```

---

## 7. Guard Constructors (All Exist)

### 7.1 ConcurrencyGuard (NOT a DAGGuard)

**File**: `orchestration/guards/concurrency_guard.py:36`
```python
def __init__(self) -> None
```
Zero deps. Uses asyncio.Lock internally.

### 7.2 OutputSchemaGuard (DAGGuard)

**File**: `orchestration/guards/output_schema_guard.py:93`
No explicit `__init__` -- zero deps, stateless.

### 7.3 ConditionalEdgeEvaluator (DAGGuard)

**File**: `orchestration/guards/conditional_eval.py:280`
No explicit `__init__` -- zero deps, stateless.

### 7.4 MicroReplanCheckpoint (DAGGuard)

**File**: `orchestration/guards/micro_replan.py:161`
```python
def __init__(
    self,
    planner: IPlannerPort,
    max_replans: int = 1,
) -> None
```

### 7.5 ExecutionMonitor (DAGGuard)

**File**: `orchestration/guards/execution_monitor.py:117`
```python
def __init__(
    self,
    delta: IDeltaEmitPort,
    service_ref: OrchestratorService,
) -> None
```
**CIRCULAR DEPENDENCY**: Needs OrchestratorService reference, but OrchestratorService needs DAGExecutor which needs guards.
**Resolution**: Pass placeholder/None initially. Set `service_ref` AFTER OrchestratorService is created (lazy init).

### 7.6 SubStepObserver (NOT a DAGGuard)

**File**: `orchestration/guards/execution_monitor.py:296`
```python
def __init__(
    self,
    events: IEventSubscriptionPort,
    delta: IDeltaEmitPort,
    rate_limit_ms: int = 500,
) -> None
```

### Guard List (Order Matters -- for DAGExecutor)

```python
guards = [
    OutputSchemaGuard(),              # post-step, stateless
    ConditionalEdgeEvaluator(),       # before_wave, stateless
    MicroReplanCheckpoint(planner_port, max_replans=1),  # after_wave
    ExecutionMonitor(delta_port, service_ref=PLACEHOLDER),  # after_step + after_wave
]
```

ConcurrencyGuard is NOT in the guards list -- it wraps `_process_one()`.
SubStepObserver is NOT a guard -- managed by DAGExecutor lifecycle.

---

## 8. Workflow Component Constructors (All Exist)

### 8.1 WorkflowRegistry

**File**: `workflows/workflow_registry.py:50`
```python
def __init__(self, storage: IWorkflowStoragePort) -> None
```

### 8.2 WorkflowCompiler

**File**: `workflows/workflow_compiler.py:91`
```python
def __init__(
    self,
    fabric: IFabricGatewayPort,
    delta: IDeltaEmitPort,
    storage: IWorkflowStoragePort,
    state_port: IStateReadPort,
    clock: SystemClock,
) -> None
```

### 8.3 WorkflowScheduler

**File**: `workflows/workflow_scheduler.py:119`
```python
def __init__(
    self,
    storage: IWorkflowStoragePort,
    mailbox: IMailboxPort,
    state_port: IStateReadPort,
    clock: SystemClock,
    tick_interval_s: float = 1.0,
) -> None
```

### 8.4 WorkflowRunSupervisor

**File**: `workflows/workflow_supervisor.py:102`
```python
def __init__(
    self,
    registry: WorkflowRegistry,
    compiler: WorkflowCompiler,
    storage: IWorkflowStoragePort,
    delta: IDeltaEmitPort,
    bridge: IBridgeWritePort,
) -> None
```

### 8.5 CrossWorkflowResolver

**File**: `workflows/cross_workflow_resolver.py:164`
```python
def __init__(
    self,
    registry: WorkflowRegistry,
    compiler: WorkflowCompiler,
    depth_guard: WorkflowDepthGuard,
) -> None
```

### 8.6 WorkflowDepthGuard

**File**: `workflows/cross_workflow_resolver.py:106`
```python
def __init__(self, max_depth: int = 3) -> None
```

### 8.7 ProactiveGapDetector

**File**: `workflows/gap_detector.py:89`
```python
def __init__(
    self,
    registry: WorkflowRegistry,
    compiler: WorkflowCompiler,
    storage: IWorkflowStoragePort,
    events: IEventSubscriptionPort,
    delta: IDeltaEmitPort,
) -> None
```

### 8.8 SystemClock / FrozenClock

**File**: `workflows/system_clock.py:31`
- `SystemClock()` -- no args, trivial utility
- `FrozenClock(frozen_time: float)` -- test double

---

## 9. Connector Component Constructors (All Exist)

### 9.1 MCPToolDiscovery

**File**: `connectors/mcp_discovery.py:200`
```python
def __init__(
    self,
    config_path: str = "k1/connectors/mcp_servers.yaml",
    transport: Optional[IMCPTransportDiscovery] = None,
) -> None
```

### 9.2 MCPRegistrationBridge

**File**: `connectors/mcp_registrar.py:154`
```python
def __init__(self, fabric: Any, delta: Any) -> None
```

### 9.3 ConnectorLifecycleManager

**File**: `connectors/connector_lifecycle.py:98`
```python
def __init__(
    self,
    discovery: MCPToolDiscovery,
    registrar: MCPRegistrationBridge,
    events: Any,  # IEventSubscriptionPort
    delta: Any,    # IDeltaEmitPort
) -> None
```

### 9.4 K0ConnectorProxyClient

**File**: `connectors/k0_proxy_client.py:183`
```python
def __init__(
    self,
    bridge: Any,  # IBridgeWritePort
    proxy_endpoint: Optional[str] = None,
    transport: Optional[IProxyTransport] = None,
) -> None
```

---

## 10. The 15-Step Construction Order

This is the dependency-safe construction sequence inside `_construct_orchestrator(config, adapters)`.

```
STEP  1: error_router     = ErrorRouter(delta_port)
STEP  2: concurrency_guard = ConcurrencyGuard()
STEP  3: mailbox_port      = adapters["mailbox"] or MailboxAdapter(config.mailbox_capacity)
STEP  4: fabric_port       = adapters["fabric"] or FabricGatewayAdapter(ext.fabric)
STEP  5: planner_port      = adapters["planner"] or PlannerAdapter(ext.planner_mailbox, cb)
STEP  6: state_port        = adapters["state"] or StateReadAdapter(ext.state_reader)
STEP  7: delta_port        = adapters["delta"] or DeltaEmitAdapter(ext.event_port, ext.delta_bus)
STEP  8: bridge_port       = adapters["bridge"] or BridgeWriteAdapter(ext.bridge_client)
STEP  9: event_port        = adapters["event"] or EventSubscriptionAdapter(ext.event_bus)
STEP 10: storage_port      = adapters["storage"] or WorkflowStorageAdapter(SQLiteWorkflowAdapter(config.workflow_db_path))
STEP 11: step_runner       = StepRunner(fabric_port, error_router, policies)
STEP 12: guards            = [OutputSchemaGuard(), ConditionalEdgeEvaluator(),
                              MicroReplanCheckpoint(planner_port, config.max_micro_replans),
                              ExecutionMonitor(delta_port, PLACEHOLDER)]
STEP 13: dag_executor      = DAGExecutor(fabric_port, planner_port, delta_port, state_port,
                              bridge_port, step_runner, error_router, guards,
                              ParamResolver(registry=None))
STEP 14: constraint_resolver = ConstraintResolver(fabric_port, delta_port, event_port)
          clock              = SystemClock()
          registry           = WorkflowRegistry(storage_port)
          compiler           = WorkflowCompiler(fabric_port, delta_port, storage_port, state_port, clock)
          scheduler          = WorkflowScheduler(storage_port, mailbox_port, state_port, clock,
                                config.scheduler_tick_interval_ms / 1000.0)
          depth_guard        = WorkflowDepthGuard(config.max_workflow_depth)
          cross_resolver     = CrossWorkflowResolver(registry, compiler, depth_guard)
          supervisor         = WorkflowRunSupervisor(registry, compiler, storage_port, delta_port, bridge_port)
          gap_detector       = ProactiveGapDetector(registry, compiler, storage_port, event_port, delta_port)
          workflow_engine    = <WorkflowEngineLike facade wrapping: registry, compiler, scheduler, supervisor, cross_resolver, gap_detector>
STEP 15: discovery       = MCPToolDiscovery(config.mcp_config_path)
          registrar       = MCPRegistrationBridge(fabric_port, delta_port)
          connector_lifecycle = ConnectorLifecycleManager(discovery, registrar, event_port, delta_port)
          k0_proxy (optional) = K0ConnectorProxyClient(bridge_port, config.k0_proxy_endpoint if exists)

FINAL:   orchestrator_service = OrchestratorService(
           mailbox=mailbox_port,
           dag_executor=dag_executor,
           constraint_resolver=constraint_resolver,
           workflow_engine=workflow_engine,
           connector_lifecycle=connector_lifecycle,
           error_router=error_router,
           concurrency_guard=concurrency_guard,
           fabric_port=fabric_port,
           planner_port=planner_port,
           state_port=state_port,
           delta_port=delta_port,
           bridge_port=bridge_port,
           config=config,
         )

POST:    # Resolve lazy init for ExecutionMonitor circular ref
         execution_monitor_guard = guards[3]  # ExecutionMonitor
         execution_monitor_guard._service_ref = orchestrator_service
```

---

## 11. Circular Dependency Resolution

**Problem**: ExecutionMonitor (guard in step 12) needs `service_ref: OrchestratorService`, but OrchestratorService (FINAL step) needs DAGExecutor (step 13) which needs guards (step 12).

**Solution**: Lazy init pattern:
1. Create ExecutionMonitor with `service_ref=None` (or a placeholder)
2. After OrchestratorService is fully constructed, set `execution_monitor._service_ref = service`

This is explicitly called out in the plan:
> "ExecutionMonitor needs `orchestrator_ref` (CIRCULAR -- resolved via lazy init: pass placeholder, set after OrchestratorService created)"

---

## 12. WorkflowEngineLike Facade

OrchestratorService expects `workflow_engine: WorkflowEngineLike` with methods:
- `execute_workflow(request, ctx) -> ProcessResult`
- `save_workflow(request, ctx) -> ProcessResult`

The individual workflow components (registry, compiler, scheduler, supervisor, cross_resolver, gap_detector) need to be composed into a single object that satisfies this Protocol. Options:

1. **WorkflowEngine class**: New facade class that holds all sub-components and implements WorkflowEngineLike
2. **Direct delegation**: OrchestratorService accesses sub-components through a simple container

The factory must create this facade and inject it.

---

## 13. OrchestratorPolicies from OrchestratorConfig

StepRunner takes `OrchestratorPolicies`, not `OrchestratorConfig`. Factory must build policies:

```python
policies = OrchestratorPolicies(
    normal_retries=config.step_max_retries,
    schema_retries=1,  # hardcoded V1
    step_timeout_default_ms=config.default_step_timeout_ms,
    max_steps_per_plan=50,   # from config if added, else hardcoded
    max_waves_per_plan=20,
    max_concurrent_per_wave=config.max_wave_parallelism,
)
```

---

## 14. Factory Methods -- Adapter Selection

### create_production(config: OrchestratorConfig) -> OrchestratorService

- All production adapters (MailboxAdapter, FabricGatewayAdapter, etc.)
- External deps must be provided (Fabric instance, planner mailbox, state reader, event bus, delta bus, bridge client)
- Calls `_construct_orchestrator(config, prod_adapters)`
- Calls `await service.init()` automatically
- Returns fully initialized, ready-to-use service

**Open question**: How are external deps provided? Options:
  A. `config` contains refs to external objects
  B. Separate `ExternalDependencies` dataclass
  C. Additional kwargs to `create_production()`

### create_standalone() -> OrchestratorService

- ALL test adapters, zero external deps
- Default OrchestratorConfig
- Does NOT call init()
- Must complete in < 10ms (no I/O)
- Used for unit testing

### create_for_testing(overrides: dict = {}) -> OrchestratorService

- ALL test adapters by default
- Caller can override specific ports via `overrides` dict
  e.g., `overrides={"fabric": real_fabric_adapter}`
- Does NOT call init() (tests control lifecycle)
- Event capture enabled on TestEventAdapter

### create_with_ports(**ports) -> OrchestratorService

- Caller provides exact adapter instances for each port
- Used for cross-subsystem integration tests mixing real + test adapters
- Does NOT call init()

---

## 15. Event Wiring (init() step 8)

These subscriptions are registered during init() via IEventSubscriptionPort:

| Topic | Handler Target |
|-------|---------------|
| `k1.planner.plan.ready.v1` | Route to mailbox as CommittedPlan |
| `k1.planner.plan.failed.v1` | Route as PlanFailedEvent |
| `k1.planner.plan.cancelled.v1` | Route as PlanCancelledEvent |
| `k1.hil.override_response.*` | Route to PendingHILContext resolver |
| `k1.hil.fallback_response.*` | Route to PendingHILContext resolver |
| `k1.fabric.capability.contract_updated.v1` | Route to ProactiveGapDetector |
| `fabric.agent.*.tool_call.*` | Route to SubStepObserver |
| `fabric.agent.*.llm_call.*` | Route to SubStepObserver |

---

## 16. Lifecycle Methods (6.2.2-6.2.5 -- TODO, Not factory)

These are OrchestratorService methods, NOT factory methods. The factory calls `init()` for production only.

- `init()` -- 10-step startup (6.2.2)
- `shutdown()` -- 9-step teardown (6.2.3)
- `crash_recovery()` -- WAL-based DAG resume (6.2.4)
- `_mailbox_loop()` -- message processing (6.2.5)

Factory issue 6.2.1 ONLY creates the factory and the wiring. Lifecycle methods are separate issues (6.2.2-6.2.5).

---

## 17. Import Map for Factory

```python
# Config
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.types import OrchestratorPolicies

# Ports
from k1.orchestrator.ports.mailbox_port import IMailboxPort
from k1.orchestrator.ports.fabric_gateway_port import IFabricGatewayPort
from k1.orchestrator.ports.planner_port import IPlannerPort
from k1.orchestrator.ports.state_read_port import IStateReadPort
from k1.orchestrator.ports.delta_emit_port import IDeltaEmitPort
from k1.orchestrator.ports.bridge_write_port import IBridgeWritePort
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
from k1.orchestrator.ports.workflow_storage_port import IWorkflowStoragePort

# Production Adapters
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter
from k1.orchestrator.adapters.bridge_write_adapter import BridgeWriteAdapter
from k1.orchestrator.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.orchestrator.adapters.workflow_storage_adapter import WorkflowStorageAdapter

# Test Adapters
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.mock_planner_adapter import MockPlannerAdapter
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.mock_bridge_adapter import MockBridgeAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import TestWorkflowStorageAdapter

# Core Services
from k1.orchestrator.orchestration.orchestrator_service import OrchestratorService
from k1.orchestrator.orchestration.dag_executor import DAGExecutor
from k1.orchestrator.orchestration.error_router import ErrorRouter
from k1.orchestrator.orchestration.step_runner import StepRunner
from k1.orchestrator.orchestration.param_resolver import ParamResolver
from k1.orchestrator.orchestration.constraint_resolver import ConstraintResolver

# Guards
from k1.orchestrator.orchestration.guards import (
    ConcurrencyGuard,
    ConditionalEdgeEvaluator,
    ExecutionMonitor,
    MicroReplanCheckpoint,
    OutputSchemaGuard,
    SubStepObserver,
)

# Workflow System
from k1.orchestrator.workflows.workflow_registry import WorkflowRegistry
from k1.orchestrator.workflows.workflow_compiler import WorkflowCompiler
from k1.orchestrator.workflows.workflow_scheduler import WorkflowScheduler
from k1.orchestrator.workflows.workflow_supervisor import WorkflowRunSupervisor
from k1.orchestrator.workflows.cross_workflow_resolver import (
    CrossWorkflowResolver,
    WorkflowDepthGuard,
)
from k1.orchestrator.workflows.gap_detector import ProactiveGapDetector
from k1.orchestrator.workflows.system_clock import SystemClock, FrozenClock

# Connectors
from k1.orchestrator.connectors.mcp_discovery import MCPToolDiscovery
from k1.orchestrator.connectors.mcp_registrar import MCPRegistrationBridge
from k1.orchestrator.connectors.connector_lifecycle import ConnectorLifecycleManager
from k1.orchestrator.connectors.k0_proxy_client import K0ConnectorProxyClient

# External deps (production only)
from k1.fabric.fabric import Fabric  # for FabricGatewayAdapter
from k1.fabric.ports.event_port import IEventPort  # for DeltaEmitAdapter + EventSubscriptionAdapter
from k1.fabric.ports.state_reader import ISessionStateReader  # for StateReadAdapter
# IDeltaBusPort, IBridgeClient -- from Fabric/Bridge modules
```

---

## 18. Key Anti-Hallucination Rules

1. **OrchestratorFactory has NO constructor** -- static methods only
2. **Construction order is STRICT** -- later steps depend on earlier steps
3. **ExecutionMonitor circular dep** -- resolved via lazy init (placeholder then set after)
4. **create_production() calls init()** -- create_for_testing() and create_standalone() do NOT
5. **ConcurrencyGuard NOT in guards list** -- it wraps _process_one(), not DAG walk
6. **SubStepObserver NOT in guards list** -- managed by DAGExecutor lifecycle
7. **_mailbox_loop is 1ms polling** -- NOT asyncio.Queue
8. **AdapterError is frozen dataclass** -- adapters raise `AdapterException(AdapterError(...))`
9. **AdapterException.detail** -- NOT `.error`
10. **OrchestratorService uses keyword-only args** (`*` in constructor)
11. **DAGExecutor uses positional args**
12. **ErrorSeverity values**: RECOVERABLE, DEGRADED, TERMINAL
13. **Factory does NOT implement lifecycle** -- that's 6.2.2-6.2.5
14. **Shutdown disconnect order is LIFO** (reverse of init)
15. **WorkflowEngineLike is a Protocol** -- factory must provide an object satisfying it

---

## 19. Test Strategy for Factory

Per plan, factory tests should verify:
- `create_standalone()` returns service with all test adapters, < 10ms
- `create_for_testing()` allows port overrides
- `create_with_ports()` accepts arbitrary adapters
- Construction order is enforced (earlier deps available to later steps)
- ExecutionMonitor lazy init resolves correctly
- Guard list is correct size and order
- OrchestratorPolicies correctly derived from OrchestratorConfig

---

## 20. Files to Create

| File | Purpose |
|------|---------|
| `k1/orchestrator/factory.py` | OrchestratorFactory static class |
| `tests/k1/orchestrator/test_factory.py` | Factory unit tests |

**Files to potentially modify**:
| File | Change |
|------|--------|
| `k1/orchestrator/__init__.py` | Add factory re-export |
| `k1/orchestrator/orchestration/guards/execution_monitor.py` | May need `service_ref` to accept None for lazy init |

---

## 21. Dependency Graph (Visual)

```
OrchestratorConfig ─────────────────────────────────────────────────────┐
                                                                        v
                    ┌──> ErrorRouter(delta_port)                   OrchestratorPolicies
                    │                                                   │
delta_port ─────────┤                                                   │
                    │                                                   v
                    │   ┌──> StepRunner(fabric_port, error_router, policies)
                    │   │
fabric_port ────────┤───┤
                    │   │   ┌──> OutputSchemaGuard()
                    │   │   │    ConditionalEdgeEvaluator()
planner_port ───────┤   │   │    MicroReplanCheckpoint(planner_port, 1)
                    │   │   │    ExecutionMonitor(delta_port, PLACEHOLDER)
state_port ─────────┤   │   │
                    │   │   v
bridge_port ────────┤   ├──> DAGExecutor(5_ports, step_runner, error_router, guards, param_resolver)
                    │   │
event_port ─────────┤   │
                    │   │   ┌──> ConstraintResolver(fabric_port, delta_port, event_port)
storage_port ───────┤   │   │
                    │   │   ├──> WorkflowRegistry(storage_port)
mailbox_port ───────┤   │   │    WorkflowCompiler(fabric_port, delta_port, storage_port, state_port, clock)
                    │   │   │    WorkflowScheduler(storage_port, mailbox_port, state_port, clock)
ConcurrencyGuard ───┤   │   │    WorkflowRunSupervisor(registry, compiler, storage_port, delta_port, bridge_port)
                    │   │   │    CrossWorkflowResolver(registry, compiler, depth_guard)
                    │   │   │    ProactiveGapDetector(registry, compiler, storage_port, event_port, delta_port)
                    │   │   │    -> WorkflowEngine facade
                    │   │   │
                    │   │   ├──> ConnectorLifecycleManager(discovery, registrar, event_port, delta_port)
                    │   │   │
                    v   v   v
                OrchestratorService(mailbox, dag_executor, constraint_resolver,
                                   workflow_engine, connector_lifecycle,
                                   error_router, concurrency_guard,
                                   5_ports, config)
                    │
                    v
                ExecutionMonitor._service_ref = service  (lazy init)
```
