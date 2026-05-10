# K1 Orchestrator — WIRING

This document traces every construction path, adapter instantiation, and internal
dependency wiring for `OrchestratorService`.

---

## 1. `OrchestratorFactory` — construction entry points

All construction goes through `OrchestratorFactory` (static methods only — no instance).

### Production path

```python
service = await OrchestratorFactory.create_production(config=OrchestratorConfig(...))
# Assembles all production adapters, calls service.init() before returning.
```

### Integration test path

```python
service = OrchestratorFactory.create_for_testing(
    fabric_port=MyFabricAdapter(),   # override specific adapters
    hil_port=MockHILAdapter(),
)
# Remaining adapters are test doubles. Does NOT call init().
```

### Standalone (unit test) path

```python
service = OrchestratorFactory.create_standalone()
# All test adapters. No init(). Immediately ready for direct method calls.
```

### Caller-provided path

```python
service = OrchestratorFactory.create_with_ports(
    mailbox=..., dag_executor=..., constraint_resolver=...,
    workflow_engine=..., connector_lifecycle=..., error_router=...,
    concurrency_guard=..., fabric_port=..., planner_port=...,
    state_port=..., delta_port=..., bridge_port=..., event_port=...,
    config=..., metrics=None, hil_port=None,
)
# Caller must call service.init() manually.
```

---

## 2. `OrchestratorService` construction graph

```python
OrchestratorService.__init__(
    mailbox,           # IMailboxPort   → production: MailboxAdapter (WFQ priority queue)
    dag_executor,      # DAGExecutorLike
    constraint_resolver,
    workflow_engine,
    connector_lifecycle,
    error_router,
    concurrency_guard, # ConcurrencyGuardLike
    fabric_port,       # IFabricGatewayPort
    planner_port,      # IPlannerPort | None  (late-bound via bind_planner())
    state_port,        # IStateReadPort
    delta_port,        # IDeltaEmitPort
    bridge_port,       # IBridgeWritePort
    event_port,        # IEventSubscriptionPort
    config,            # OrchestratorConfig (frozen)
    metrics,           # OrchestratorMetrics | None
    hil_port,          # IHILPort | None → falls back to _NullHILAdapter()
)
│
├─ _mailbox: IMailboxPort
├─ _dag_executor: DAGExecutorLike
├─ _constraint_resolver: ConstraintResolver
├─ _workflow_engine: WorkflowEngineLike
├─ _connector_lifecycle: ConnectorLifecycleManager
├─ _error_router: ErrorRouterLike
├─ _concurrency_guard: ConcurrencyGuardLike
├─ _fabric_port: IFabricGatewayPort
├─ _planner_port: IPlannerPort | None
├─ _state_port: IStateReadPort
├─ _delta_port: IDeltaEmitPort
├─ _bridge_port: IBridgeWritePort
├─ _event_port: IEventSubscriptionPort
├─ _config: OrchestratorConfig
├─ _metrics: OrchestratorMetrics
├─ _hil_port: IHILPort           # effective_hil = hil_port or _NullHILAdapter()
├─ _pending_plans: Dict[str, PendingPlanContext]   # request_id → pending context
├─ _executed_plans: LRU[str]     # plan_id dedup (max 100)
├─ _handle_task_waiters: Dict[str, asyncio.Future]  # trace_id → future
├─ _subscriptions: List[SubscriptionHandle]         # for unsubscribe on shutdown
├─ _initialized: bool = False
└─ _running: bool = False
```

---

## 3. `DAGExecutor` construction

```python
DAGExecutor.__init__(
    fabric_port,      # IFabricGatewayPort
    planner_port,     # IPlannerPort
    delta_port,       # IDeltaEmitPort
    state_port,       # IStateReadPort
    bridge_port,      # IBridgeWritePort
    step_runner,      # StepRunner
    error_router,     # ErrorRouterLike
    guards,           # List[DAGGuard] | None → see §4 guard assembly
    param_resolver,   # ParamResolver | None
    metrics,          # OrchestratorMetrics | None
)
│
├─ _fabric_port, _planner_port, _delta_port, _state_port, _bridge_port
├─ _step_runner: StepRunner
├─ _error_router: ErrorRouterLike
├─ _guards: List[DAGGuard]    # execution-ordered
├─ _param_resolver: ParamResolver
├─ _metrics: OrchestratorMetrics | None
│
├─ interrupt_flag: bool = False      # mutable, reset per execute()
├─ merged_results: Dict[str, Any]    # mutable, reset per execute()
└─ _cancelled_steps: Set[str]        # mutable, reset per execute()
```

### `StepRunner` construction

```python
StepRunner.__init__(
    fabric_port,   # IFabricGatewayPort
    error_router,  # ErrorRouterLike
    policies,      # OrchestratorPolicies (frozen)
    metrics,       # OrchestratorMetrics | None
)
```

---

## 4. Guard assembly

The factory assembles 6 guards in a specific execution order:

```python
def _build_guards(planner_port, delta_port, hil_port, config):
    return [
        ConditionalEdgeEvaluator(),                       # 1. pre-wave SKIP
        ExecutionMonitor(delta_port, hil_port, config),   # 2. interrupt + progress
        OutputSchemaGuard(),                              # 3. schema validation
        MicroReplanCheckpoint(planner_port),              # 4. discovery micro-replan
        FailureReplanCheckpoint(planner_port),            # 5. failure micro-replan
        # 6th guard slot reserved; empty in V1 (guard_order has 6 entries in config)
    ]
```

Guard invocation in `DAGExecutor`:

```
before_wave():  [ConditionalEdgeEvaluator]      → SKIP decisions
after_step():   [OutputSchemaGuard, ExecutionMonitor]  → RETRY | HARD_STOP | CONTINUE
after_wave():   [ExecutionMonitor, MicroReplanCheckpoint, FailureReplanCheckpoint]
```

---

## 5. `ConstraintResolver` construction

```python
ConstraintResolver.__init__(
    fabric_port,   # IFabricGatewayPort — for registry queries
    hil_port,      # Optional[IHILPort] → None if not configured
)
```

Used by both `OrchestratorService.receive_plan()` and `WorkflowEngine.execute_workflow()`.

---

## 6. `WorkflowEngine` construction (facade)

```python
WorkflowEngine.__init__(
    supervisor=WorkflowRunSupervisor(registry, bridge_port),
    dag_executor=dag_executor,          # shared with OrchestratorService
    constraint_resolver=constraint_resolver,  # shared with OrchestratorService
    registry=WorkflowRegistry(storage_port),
    compiler=WorkflowCompiler(fabric_port),
    scheduler=WorkflowScheduler(event_port, config),
    cross_resolver=CrossWorkflowResolver(registry, config.max_workflow_depth),
    gap_detector=ProactiveGapDetector(event_port, fabric_port, delta_port),
    delta=delta_port,
    bridge=bridge_port,
)
```

`WorkflowRegistry`, `WorkflowCompiler`, `WorkflowScheduler`, `WorkflowRunSupervisor`,
and `ProactiveGapDetector` are all internal to `WorkflowEngine` — not exposed directly.

`WorkflowScheduler` starts a background asyncio task on `init()` that ticks every
`scheduler_tick_interval_ms=1s`. On each tick, it evaluates CRON and EVENT triggers
against `list_active()` workflow specs.

---

## 7. `ConnectorLifecycleManager` construction

```python
ConnectorLifecycleManager.__init__(
    discovery=MCPToolDiscovery(config),   # reads mcp_servers.yaml
    registrar=MCPRegistrationBridge(fabric_port, delta_port),
    events=event_port,
    delta=delta_port,
    metrics=metrics,
)
```

On `discover_and_register()` (called from `init()` step 3), enumerates all MCP servers
from the YAML config and registers their tools into Fabric via
`MCPRegistrationBridge.register_tool()` → emits `ORCH_MCP_TOOL_REGISTERED`.

`start_lifecycle_monitoring()` subscribes to `k1.fabric.provider.health.changed.v1`.
On health change → `refresh(server_id)` → re-discovery for that server.

---

## 8. Adapter instantiation (production path)

```python
# All instantiated inside OrchestratorFactory._build_production_adapters(config)

mailbox      = MailboxAdapter(capacity=config.mailbox_capacity)        # WFQ priority queue
fabric_port  = FabricGatewayAdapter(session_fabric)                   # wraps Fabric execute
planner_port = PlannerAdapter(config)                                  # HTTP client to Planner
state_port   = StateReadAdapter(ssm)                                   # wraps SessionStateManager
delta_port   = DeltaEmitAdapter(bus)                                   # wraps IBus publish
bridge_port  = BridgeWriteAdapter(bridge_client)                       # wraps K0 bridge client
event_port   = EventSubscriptionAdapter(bus)                           # wraps IBus subscribe/emit
storage_port = SQLiteWorkflowAdapter(config.workflow_db_path)          # SQLite WAL
admin_port   = AdminHttpAdapter(config)                                # HTTP admin server
```

---

## 9. `init()` 10-step startup sequence

```python
async def init():
    1. validate_ports()          # isinstance checks on all 8 ports
    2. crash_recovery()          # scan WAL → re-enqueue incomplete DAGs
    3. connector_lifecycle.discover_and_register()  # MCP tool discovery
    4. workflow_engine.registry.load_active()        # load WorkflowSpecs from SQLite
    5. workflow_engine.scheduler.start()             # start scheduler asyncio task
    6. _subscribe_events()       # subscribe to 10 consumed topics via event_port
    7. _start_reaper()           # asyncio.create_task(_reap_loop) — stale context cleanup
    8. _start_mailbox_loop()     # asyncio.create_task(_mailbox_loop)
    9. admin_port.start(config.admin_port)   # start HTTP admin
    10. _initialized = True
```

---

## 10. Event subscriptions wired at `init()` step 6

```python
_subscriptions = [
    event_port.subscribe("k1.planner.plan.ready.v1",       _on_plan_ready),
    event_port.subscribe("k1.planner.plan.failed.v1",      _on_plan_failed),
    event_port.subscribe("k1.planner.plan.cancelled.v1",   _on_plan_cancelled),
    event_port.subscribe("k1.planner.micro_replan.ready.v1", _on_micro_replan_telemetry),
    event_port.subscribe("k1.capability.completed.v1",     step_runner._on_cap_completed),
    event_port.subscribe("k1.capability.failed.v1",        step_runner._on_cap_failed),
    event_port.subscribe("k1.fabric.contract.updated.v1",  gap_detector._on_contract_updated),
    event_port.subscribe("k1.fabric.agent.tool_call.v1",   sub_step_observer._on_tool_call),
    event_port.subscribe("k1.fabric.agent.llm_call.v1",    sub_step_observer._on_llm_call),
    event_port.subscribe("k1.orchestration.workflow.trigger_due.v1", scheduler._on_trigger_due),
    # ConnectorLifecycleManager adds:
    event_port.subscribe("k1.fabric.provider.health.changed.v1", _on_provider_health_changed),
]
```

---

## 11. Late binding — `bind_planner()`

The orchestrator may start before the planner is ready (kernel startup order S6b).
`bind_planner(planner_port)` sets `_planner_port` and propagates to:
- `DAGExecutor._planner_port`
- `MicroReplanCheckpoint._planner_port`
- `FailureReplanCheckpoint._planner_port`
- `WorkflowEngine._dag_executor._planner_port` (via same shared reference)

HIGH-tier tasks arriving before `bind_planner()` is called fail immediately with
`ProcessResult.FAILED` (no planner → no plan).

---

## 12. Shutdown sequence

```python
async def shutdown():
    1. _running = False
    2. admin_port.stop()
    3. scheduler.stop()
    4. connector_lifecycle.stop_lifecycle_monitoring()
    5. gap_detector.stop()
    6. for handle in _subscriptions: event_port.unsubscribe(handle)
    7. mailbox_loop_task.cancel(); await asyncio.gather(mailbox_loop_task, ...)
    8. reaper_task.cancel(); await asyncio.gather(reaper_task, ...)
    9. await asyncio.wait_for(drain(), timeout=config.drain_timeout_ms/1000)
    10. bridge_port.close() if applicable
```

---

## 13. Dependency graph

```
OrchestratorService
  ├─ MailboxAdapter (WFQ, capacity=100)
  ├─ DAGExecutor
  │     ├─ StepRunner
  │     │     ├─ FabricGatewayAdapter  → Fabric.execute()
  │     │     └─ ErrorRouter → DeltaEmitAdapter
  │     ├─ ParamResolver ($ reference expansion)
  │     └─ Guards (5 active)
  │           ├─ ConditionalEdgeEvaluator
  │           ├─ ExecutionMonitor → DeltaEmitAdapter + IHILPort
  │           ├─ OutputSchemaGuard
  │           ├─ MicroReplanCheckpoint → PlannerAdapter
  │           └─ FailureReplanCheckpoint → PlannerAdapter
  ├─ ConstraintResolver
  │     ├─ FabricGatewayAdapter (registry queries)
  │     └─ IHILPort (optional fallback)
  ├─ WorkflowEngine (facade)
  │     ├─ WorkflowRegistry → SQLiteWorkflowAdapter
  │     ├─ WorkflowCompiler → FabricGatewayAdapter
  │     ├─ WorkflowScheduler → EventSubscriptionAdapter
  │     ├─ WorkflowRunSupervisor → WorkflowRegistry + BridgeWriteAdapter
  │     ├─ CrossWorkflowResolver → WorkflowRegistry
  │     ├─ ProactiveGapDetector → EventSubscriptionAdapter + FabricGatewayAdapter
  │     └─ (shares DAGExecutor + ConstraintResolver from above)
  ├─ ConnectorLifecycleManager
  │     ├─ MCPToolDiscovery (reads mcp_servers.yaml)
  │     └─ MCPRegistrationBridge → FabricGatewayAdapter + DeltaEmitAdapter
  ├─ FabricGatewayAdapter  → session Fabric
  ├─ PlannerAdapter        → Planner (HTTP)
  ├─ StateReadAdapter      → SessionStateManager
  ├─ DeltaEmitAdapter      → IBus.publish()
  ├─ BridgeWriteAdapter    → K0 bridge client
  ├─ EventSubscriptionAdapter → IBus.subscribe()/emit()
  └─ AdminHttpAdapter      → HTTP :8081
```
