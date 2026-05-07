# Orchestrator — Formal API Mapping

> Generated: 2026-04-12 · Scope: Inputs, Outputs, Processing for every Orchestrator boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 Mailbox — Single Inbound Channel

All work enters via `IMailboxPort.dequeue()` in `_mailbox_loop()`.

| Message Type | Fields | Enqueued By | Priority |
|---|---|---|---|
| `TaskEnvelope` | `request_id: str`, `session_id: str`, `trace_id: str`, `intent: str`, `tier: str` ("MEDIUM" / "HIGH"), `capabilities: List[str]`, `params: Dict[str, Any]`, `context: Dict[str, Any]`, `timeout_ms: int`, `safety_band: Optional[str]` | Kernel (Concierge → Bus → Mailbox) | INTERACTIVE |
| `CommittedPlan` | `plan_id: str`, `request_id: str`, `trace_id: str`, `steps: List[PlanStep]`, `dependencies: Dict[str, List[str]]`, `metadata: Dict[str, Any]` | Event bus → `_on_plan_ready()` handler | INTERACTIVE |
| `WorkflowRunRequest` | `workflow_id: str`, `trigger_type: TriggerType`, `trigger_context: Dict[str, Any]`, `trace_id: str` | WorkflowScheduler or manual | BACKGROUND |
| `WorkflowSaveRequest` | `name: str`, `committed_plan_id: str`, `trigger: Dict[str, Any]`, `trace_id: str` | Admin / Concierge | INTERACTIVE |
| `InterruptRequest` | `dag_id: str`, `action: str` ("CANCEL_DAG"), `trace_id: str`, `reason: Optional[str]` | Admin / HIL | REALTIME |

### 1.2 Event Subscriptions (Async Inbound)

Registered at `init()` via `IEventSubscriptionPort.subscribe()`:

| Topic | Handler | Payload Shape | Effect |
|---|---|---|---|
| `k1.planner.plan.ready.v1` | `_on_plan_ready` | `{"plan_id", "request_id", "trace_id", "steps": [...], "dependencies": {...}, "metadata": {...}}` | Deserialize → `CommittedPlan`, enqueue to mailbox |
| `k1.planner.plan.failed.v1` | `_on_plan_failed` | `{"request_id", "reason", "error_detail?", "trace_id"}` | Pop `PendingPlanContext`, call `receive_plan_failed()` |
| `k1.planner.plan.cancelled.v1` | `_on_plan_cancelled` | `{"request_id", "trace_id"}` | Pop `PendingPlanContext`, call `receive_plan_cancelled()` |
| `k1.hil.override_response.v1` | `_on_hil_override` | `{"request_id", "selected_option", "trace_id"}` | Resolve `PendingHILContext` with user choice |
| `k1.hil.fallback_response.v1` | `_on_hil_fallback` | `{"request_id", "trace_id"}` | Resolve `PendingHILContext` with fallback |

---

## 2. Exit Points (What Goes OUT)

### 2.1 Port Calls — What the Orchestrator Sends

#### IFabricGatewayPort (→ Fabric)

| Method | When Called | Input | Output |
|---|---|---|---|
| `execute(request)` | StepRunner per step, Compensation | `CapabilityRequest(capability_name, params, prompt_template, tier="HIGH", caller="orchestrator", caller_id=step.id, trace_id, plan_id, step_id, timeout_ms, context_override)` | `CapabilityResult(request_id, trace_id, success: bool, data: Optional[Dict], error: Optional[str], duration_ms: int)` |
| `execute_batch(requests)` | Not used in V1 | `List[CapabilityRequest]` | `List[CapabilityResult]` |
| `query_registry(cap_name)` | ConstraintResolver, Compensation lookup | `str` | `Optional[RegistryEntry(name, provider_type, safety_band_min, availability, estimated_duration_ms, compensation_capability)]` |
| `query_registry_by_category(prefix)` | ConstraintResolver alternatives | `str` (e.g. `"tool.calendar"`) | `List[RegistryEntry]` |

#### IPlannerPort (→ Planner)

| Method | When Called | Input | Output |
|---|---|---|---|
| `request_plan(request)` | `_dispatch_high()` | `PlanRequest(request_id, intent, snapshot: SessionSnapshot, constraints: Dict, trace_id, timeout_ms)` | `PlanAck(request_id, status: "ACCEPTED"/"REJECTED", estimated_duration_ms)` |
| `cancel_plan(request_id)` | `reap_stale_contexts()` | `str` | `None` (best-effort, fire-and-forget) |
| `micro_replan(request)` | MicroReplanCheckpoint guard | `MicroReplanRequest(request_id, original_plan_id, completed_steps: List[str], failed_step_id, error_detail, discoveries: List[Discovery], trace_id)` | `Optional[CommittedPlan]` (None on timeout) |

#### IStateReadPort (→ SessionState)

| Method | When Called | Input | Output |
|---|---|---|---|
| `read_section(session_id, section)` | Safety band check (`_check_safety_band`) | `str, "control"` | `Optional[Dict[str, Any]]` (e.g. `{"safety_band": "GREEN"}`) |
| `read_sections(session_id, names)` | Not used in V1 | `str, List[str]` | `Dict[str, Any]` |
| `get_snapshot(session_id)` | `_dispatch_high()` (planning context), `_receive_plan()` (fresh snapshot) | `str` | `SessionSnapshot(session_id, sections: Dict, timestamp_ms: int)` |

**NOTE:** Currently wired to `MockStateReadAdapter` in production (always returns empty). Not yet connected to real SessionState.

#### IDeltaEmitPort (→ Event Bus + Delta Bus)

| Method | When Called | Input | Output |
|---|---|---|---|
| `emit(topic, payload, trace_id)` | ~15 call sites | `str, Dict[str, Any], str` | `None` (fire-and-forget) |
| `emit_progress(step_id, summary, trace_id)` | After each wave | `str, str, str` | `None` |
| `emit_hil_request(hil_request, trace_id)` | ConstraintResolver, ExecutionMonitor | `HILRequest, str` | `None` |

**Events Emitted:**

| Event Topic | Payload Shape | Source |
|---|---|---|
| `k1.orchestration.task.accepted.v1` | `{request_id, session_id, tier, intent, trace_id, timestamp_ms}` | `_route_task()` |
| `k1.orchestration.plan.requested.v1` | `{request_id, intent, trace_id, timestamp_ms}` | `_dispatch_high()` |
| `k1.orchestration.dag.started.v1` | `{plan_id, trace_id, wave_count, step_count, timestamp_ms}` | `DAGExecutor.execute()` |
| `k1.orchestration.step.completed.v1` | `{plan_id, step_id, capability, status, duration_ms, trace_id}` | `DAGExecutor._execute_step()` |
| `k1.orchestration.dag.completed.v1` | `{plan_id, status, duration_ms, total_steps, completed, failed, trace_id}` | `_emit_result()` |
| `k1.orchestration.workflow.saved.v1` | `{workflow_id, name, source_plan_id, trace_id}` | `_save_workflow()` |
| `k1.orchestration.error.routed.v1` | `{severity, adapter, error_message, action, trace_id}` | `ErrorRouter.route_error()` |
| `k1.hil.progress.v1` | `{step_id, summary, trace_id}` | `emit_progress()` |
| `k1.hil.request.v1` | `{request_id, question, options, context, timeout_ms, trace_id}` | `emit_hil_request()` |
| `k1.mcp.tool.discovered.v1` | `{server_id, tool_name, capability_id}` | `MCPRegistrationBridge` |

#### IBridgeWritePort (→ K0 via Bridge)

| Method | When Called | Input | Output |
|---|---|---|---|
| `submit_audit(manifest, trace_id)` | `_emit_result()` after DAG complete | `Dict[str, Any]` (run manifest), `str` | `None` (fire-and-forget) |
| `write_wal(dag_id, entry_type, payload, trace_id)` | 4 WAL checkpoints | `str, str` ∈ {PLAN_START, WAVE_COMPLETE, STEP_COMPLETE, DAG_COMPLETE}, `Dict`, `str` | `None` (fire-and-forget) |
| `read_wal(dag_id)` | `crash_recovery()`, `save_workflow()` | `str` | `Optional[List[Dict[str, Any]]]` |
| `list_wal_ids()` | `crash_recovery()` | (none) | `List[str]` |
| `submit_deferred_result(result, workflow_id, trace_id)` | WorkflowEngine post-run | `Dict, str, str` | `None` (fire-and-forget) |

#### IEventSubscriptionPort (→ Event Bus)

| Method | When Called | Input | Output |
|---|---|---|---|
| `subscribe(topic, handler)` | `init()` — 5 subscriptions | `str, Callable[[str, Dict], None]` | `SubscriptionHandle` |
| `unsubscribe(handle)` | `shutdown()` | `SubscriptionHandle` | `bool` |
| `emit(topic, payload)` | Via DeltaEmitAdapter dual-publish | `str, Dict[str, Any]` | `None` |

#### IWorkflowStoragePort (→ SQLite)

| Method | When Called | Input | Output |
|---|---|---|---|
| `save_workflow(spec)` | `_save_workflow()` | `WorkflowSpec` | `None` |
| `get_workflow(id)` | WorkflowRegistry | `str` | `Optional[WorkflowSpec]` |
| `list_workflows(active_only)` | `init()`, Admin | `bool` | `List[WorkflowSpec]` |
| `delete_workflow(id)` | Admin | `str` | `None` (soft delete) |
| `purge_workflow(id)` | Admin | `str` | `None` (hard delete) |
| `save_trigger(wf_id, trigger)` | `_save_workflow()` | `str, TriggerSpec` | `None` |
| `get_due_triggers(now)` | WorkflowScheduler tick | `float` | `List[Tuple[str, TriggerSpec]]` |
| `update_trigger_state(wf_id, next_fire, last_fire)` | WorkflowScheduler post-fire | `str, float, float` | `None` |
| `save_run(manifest)` | WorkflowRunSupervisor | `object` | `None` |
| `get_runs(wf_id, limit)` | Admin | `str, int` | `list` |
| `save_gap(gap)` | ProactiveGapDetector | `ProactiveGap` | `None` |
| `get_pending_gaps()` | ProactiveGapDetector | (none) | `List[ProactiveGap]` |

---

## 3. Processing Pipelines (What Gets Processed and How)

### 3.1 MEDIUM Tier — Direct Fabric Execution (no Planner)

```
IN:  TaskEnvelope(tier="MEDIUM", capabilities=["cap_a", "cap_b?"])
     ↓
     _validate_envelope() → check trace_id, intent, tier
     ↓
     _emit_task_accepted() → delta: ORCH_TASK_ACCEPTED
     ↓
     _read_safety_band(session_id) → state_port.read_section("control")
     ↓
     For each capability in envelope.capabilities:
       fabric_port.query_registry(cap_name) → RegistryEntry
       Validate: exists? safety_band_min OK?
       Build: CapabilityRequest(cap_name, params, tier=HIGH, caller="orchestrator")
       Execute: fabric_port.execute(request) → CapabilityResult
       Wrap: StepResult(step_id, capability, status, duration_ms, result)
     ↓
     aggregate(step_results) → AggregatedResult
     ↓
     _emit_result() → delta: ORCH_DAG_COMPLETED + bridge: submit_audit()
     ↓
OUT: ProcessResult.COMPLETED | DEGRADED | FAILED
```

**Type transformations:**
- `TaskEnvelope.capabilities[i]` → `CapabilityRequest.capability_name`
- `TaskEnvelope.params` → `CapabilityRequest.params`
- `TaskEnvelope.trace_id` → `CapabilityRequest.trace_id`
- `CapabilityResult.success` → `StepResult.status` (COMPLETED/FAILED)
- `List[StepResult]` → `AggregatedResult` (counts, duration, status)

### 3.2 HIGH Tier — Two-Phase Planner + DAG Execution

#### Phase 1: Request Plan (Synchronous)

```
IN:  TaskEnvelope(tier="HIGH", intent="...", capabilities=[...])
     ↓
     _validate_envelope()
     ↓
     _emit_task_accepted() → delta: ORCH_TASK_ACCEPTED
     ↓
     state_port.get_snapshot(session_id) → SessionSnapshot
     ↓
     Build: PlanRequest(
       request_id = envelope.request_id,
       intent     = envelope.intent,
       snapshot   = SessionSnapshot,
       constraints = {capabilities, safety_band, timeout_ms},
       trace_id   = envelope.trace_id,
       timeout_ms = config.plan_request_timeout_ms (45s)
     )
     ↓
     planner_port.request_plan(request) → PlanAck(status="ACCEPTED"/"REJECTED")
     ↓
     Park: PendingPlanContext(request_id, envelope, snapshot, timestamp_ms)
     ↓
     delta: ORCH_PLAN_REQUESTED
     ↓
OUT: ProcessResult.DEFERRED
```

#### Phase 2: Execute Plan (Async via Event)

```
IN:  CommittedPlan (via k1.planner.plan.ready.v1 event → mailbox)
     ↓
     Dedup: plan_id ∉ executed_plans?
     ↓
     Correlate: PendingPlanContext = pending_plans.pop(request_id)
     ↓
     state_port.get_snapshot(session_id) → fresh SessionSnapshot (RACE-1)
     ↓
     constraint_resolver.validate(plan, ctx) → ValidationResult
       ├─ check_capabilities() → query_registry per step
       ├─ find_alternatives() if missing → query_registry_by_category, score
       ├─ resolve_iteratively() → auto-apply alternatives (max 3 cycles)
       └─ trigger_hil_fallback() if unresolved → emit HIL request
     ↓
     concurrency_guard.acquire()
     ↓
     dag_executor.execute(plan, snapshot) → AggregatedResult
       ├─ build_waves(steps, deps) → List[Wave] (Kahn topo sort)
       ├─ WAL: PLAN_START
       ├─ delta: ORCH_DAG_STARTED
       ├─ [per wave, sequential]:
       │   ├─ Safety band check
       │   ├─ param_resolver.resolve() per step → resolved_params
       │   ├─ Pre-wave guards (ConditionalEdgeEvaluator → SKIP filtered steps)
       │   ├─ [per step, parallel, Semaphore(10)]:
       │   │   ├─ step_runner.run():
       │   │   │   ├─ _build_request(PlanStep → CapabilityRequest)
       │   │   │   ├─ fabric_port.execute() + retry (max 4 calls)
       │   │   │   ├─ Schema validate + schema retry if needed
       │   │   │   └─ → StepResult
       │   │   ├─ Post-step guards (OutputSchema, ExecutionMonitor)
       │   │   └─ WAL: STEP_COMPLETE
       │   ├─ cancel_dependents() for failed steps (BFS cascade)
       │   ├─ Post-wave guards (MicroReplan, ExecutionMonitor)
       │   └─ WAL: WAVE_COMPLETE
       ├─ Saga _compensate() (reverse order, LIFO)
       └─ collect_results() → AggregatedResult
     ↓
     concurrency_guard.release()
     ↓
     _emit_result() → delta: ORCH_DAG_COMPLETED + bridge: submit_audit()
     ↓
OUT: ProcessResult.COMPLETED | DEGRADED | FAILED | CANCELLED
```

### 3.3 Workflow Execution

```
IN:  WorkflowRunRequest(workflow_id, trigger_type, trigger_context, trace_id)
     ↓
     concurrency_guard.acquire()
     ↓
     workflow_engine.execute_workflow():
       ├─ supervisor.start_run(request) → (compiled_plan, manifest)
       ├─ constraint_resolver.validate(plan, ctx)
       ├─ dag_executor.execute(plan, ctx) → AggregatedResult
       └─ supervisor.complete_run() or fail_run()
     ↓
     concurrency_guard.release()
     ↓
OUT: ProcessResult.COMPLETED | DEGRADED | FAILED
```

### 3.4 Workflow Save

```
IN:  WorkflowSaveRequest(name, committed_plan_id, trigger, trace_id)
     ↓
     bridge_port.read_wal(committed_plan_id) → WAL entries
     ↓
     Find PLAN_START entry → extract plan payload
     ↓
     CommittedPlan.from_dict(payload)
     ↓
     Build: WorkflowSpec(
       workflow_id     = f"wf-{uuid4()}",
       name            = request.name,
       source_plan_id  = plan_id,
       version         = "1.0.0",
       trigger         = request.trigger,
       steps           = plan.steps,
       dependencies    = plan.dependencies,
       active          = True,
     )
     ↓
     registry.save(spec) + storage.save_trigger(wf_id, trigger_spec)
     ↓
     delta: ORCH_WORKFLOW_SAVED
     ↓
OUT: ProcessResult.COMPLETED | FAILED
```

### 3.5 Interrupt

```
IN:  InterruptRequest(dag_id, action="CANCEL_DAG", trace_id, reason)
     ↓
     V1: only CANCEL_DAG supported (PAUSE → FAILED)
     ↓
     dag_executor.interrupt_flag = True (cooperative)
     ↓
OUT: ProcessResult.CANCELLED
```

---

## 4. Key Type Transformations

### 4.1 PlanStep → CapabilityRequest (StepRunner._build_request)

| CapabilityRequest Field | Source | Notes |
|---|---|---|
| `capability_name` | `step.capability` | May be resolved from `$ref` by ParamResolver |
| `params` | `resolved_params` (from ParamResolver) | Deep-copied, `$step_1a.result.x` refs resolved |
| `prompt_template` | `step.prompt_template` | Optional, pass-through |
| `tier` | `Tier.HIGH.value` | Hardcoded |
| `caller` | `"orchestrator"` | Hardcoded |
| `caller_id` | `step.id` | |
| `trace_id` | `trace_id` (from ProcessingContext) | |
| `plan_id` | `step.id` | Same as step_id in V1 |
| `step_id` | `step.id` | |
| `timeout_ms` | `step.timeout_ms` or `policies.step_timeout_default_ms` (30s) | |
| `context_override` | `{"tools_granted": list(step.tools_granted)}` | Only if step.tools_granted set |

### 4.2 CapabilityResult → StepResult (StepRunner.run)

| StepResult Field | Source | Notes |
|---|---|---|
| `step_id` | `step.id` | |
| `capability` | `step.capability` | |
| `status` | `StepStatus.COMPLETED` if `result.success` else `FAILED` | |
| `duration_ms` | Measured (`time.monotonic()` delta) | |
| `result` | `CapabilityResult` | Full object preserved |
| `retry_count` | Counter from retry loop | 0-2 normal + 0-1 schema |
| `schema_retried` | `bool` | |
| `error_detail` | `result.error` | Only on failure |

### 4.3 List[StepResult] → AggregatedResult (AggregatedResult.from_dag)

| AggregatedResult Field | Derivation |
|---|---|
| `plan_id` | From CommittedPlan |
| `trace_id` | From ProcessingContext |
| `success` | All steps COMPLETED |
| `total_steps` | `len(plan.steps)` |
| `completed_steps` | Count where status == COMPLETED |
| `failed_steps` | Count where status == FAILED |
| `cancelled_steps` | Count where status == CANCELLED |
| `step_results` | `List[StepResult]` |
| `compensations` | `List[CompensationRecord]` |
| `duration_ms` | Total DAG wall-clock time |
| `status` | `"SUCCESS"` / `"PARTIAL"` / `"FAILED"` / `"CANCELLED"` |

### 4.4 TaskEnvelope → PlanRequest (_dispatch_high)

| PlanRequest Field | Source |
|---|---|
| `request_id` | `envelope.request_id` |
| `intent` | `envelope.intent` |
| `snapshot` | `state_port.get_snapshot(session_id)` |
| `constraints` | `{"capabilities": envelope.capabilities, "safety_band": envelope.safety_band, "timeout_ms": envelope.timeout_ms}` |
| `trace_id` | `envelope.trace_id` |
| `timeout_ms` | `config.plan_request_timeout_ms` (45s default) |

### 4.5 CommittedPlan Steps → Waves (build_waves)

| Input | Algorithm | Output |
|---|---|---|
| `List[PlanStep]` + `Dict[str, List[str]]` dependencies | Kahn's topological sort | `List[Wave]` — steps grouped by wave_index, sorted by ID within each wave |

Constraints: `len(steps) ≤ 50`, `len(waves) ≤ 20`, no cycles.

### 4.6 Parameter Resolution ($-references)

| Reference Pattern | Resolution |
|---|---|
| `$step_1a.result.agent_name` | `prior_results["step_1a"].data["agent_name"]` |
| `$step_1a.result` | `prior_results["step_1a"].data` (entire data dict) |
| `$step_1a.status` | `"COMPLETED"` or `"FAILED"` |
| `$capability_ref` (capability field) | Registry lookup → actual capability name |

---

## 5. Adapter Boundary Map

### 5.1 Production Adapters (S5 Wiring in KernelService)

| Port | Adapter | Constructor Deps | S-Stage Source |
|---|---|---|---|
| `IMailboxPort` | `MailboxAdapter(max_depth=100)` | Self-contained WFQ deque | Fresh |
| `IFabricGatewayPort` | `FabricGatewayAdapter(fabric=shared_fabric)` | `Fabric` instance | S3 |
| `IPlannerPort` | `MockPlannerAdapter()` → hot-swapped at S6b to `PlannerAdapter(planner_mailbox, cb_planner)` | Planner mailbox + CircuitBreaker | S6/S6b |
| `IStateReadPort` | `MockStateReadAdapter()` | ⚠️ NEVER REPLACED — returns empty | Fresh |
| `IDeltaEmitPort` | `DeltaEmitAdapter(event_port, delta_bus)` | `EventPortProdAdapter(bus)`, `DeltaBusProdAdapter(bus)` | S3 locals |
| `IBridgeWritePort` | `BridgeWriteAdapter(BridgeClientShim(client))` or `MockBridgeAdapter()` | `SinkBridgeClient` via S4 bridge | S4 |
| `IEventSubscriptionPort` | `EventSubscriptionAdapter(event_port)` | `EventPortProdAdapter(bus)` | S3 local |
| `IWorkflowStoragePort` | `WorkflowStorageAdapter(SQLiteWorkflowAdapter(db_path))` | `config.workflow_db_path` | Config |

### 5.2 Adapter Translation Details

| Adapter | Orch Calls | Adapter Translates To | External Target |
|---|---|---|---|
| `FabricGatewayAdapter` | `execute(CapabilityRequest)` | `Fabric.execute(CapabilityRequest)` | Pass-through |
| `FabricGatewayAdapter` | `query_registry(name)` | `Fabric.lookup(name)` → `_contract_to_entry(CapabilityContract)` → `RegistryEntry` | Extracts 5 fields |
| `PlannerAdapter` | `request_plan(PlanRequest)` | CB check → `mailbox.enqueue(request)` → `PlanAck` | Planner mailbox |
| `PlannerAdapter` | `micro_replan(MicroReplanRequest)` | CB check → `mailbox.micro_replan(request)` with 10s timeout | Planner mailbox |
| `DeltaEmitAdapter` | `emit(topic, payload, trace_id)` | Inject trace_id → `event_port.emit()` + conditional `delta_bus.emit_delta()` | Dual publish |
| `BridgeWriteAdapter` | `submit_audit(manifest, trace_id)` | `bridge_client.write("audit", manifest, trace_id=trace_id)` | K0 bridge |
| `BridgeWriteAdapter` | `write_wal(dag_id, type, payload, trace_id)` | `bridge_client.write("wal", {dag_id, entry_type, payload}, trace_id=trace_id)` | K0 bridge |
| `BridgeClientShim` | `write(channel, payload, trace_id)` | `client.submit_command(topic=channel, body=payload, trace_id=trace_id)` | SinkBridgeClient |
| `BridgeClientShim` | `read(channel, key)` | Returns `None` (offline) | N/A |
| `EventSubscriptionAdapter` | `subscribe(topic, handler)` | `event_port.subscribe(topic, handler)` | Pass-through + handle tracking |
| `WorkflowStorageAdapter` | All 12 methods | Delegate to `SQLiteWorkflowAdapter` | Pass-through + error wrapping |

---

## 6. Error Classification Matrix

### 6.1 AdapterException Classification (ErrorRouter)

| Adapter Source | Severity | Action | Orchestrator Behavior |
|---|---|---|---|
| `fabric_gateway` | DEGRADED | DEGRADE | `ProcessResult.DEGRADED` — partial results accepted |
| `planner` | DEGRADED | FALLBACK | HIGH→MEDIUM degradation (not impl in V1) |
| `state_read` | DEGRADED | DEGRADE | Stale/empty state used, proceed |
| `mailbox` | RECOVERABLE | RETRY(1) | Re-enqueue once (with once-guard) |
| `delta_emit` | RECOVERABLE | RETRY(1) | Re-enqueue once |
| `bridge_write` | RECOVERABLE | RETRY(1) | Re-enqueue once |
| `event_sub` | RECOVERABLE | RETRY(1) | Re-enqueue once |
| Any | TERMINAL | ABORT | `ProcessResult.FAILED` — immediate |

### 6.2 Fire-and-Forget Patterns

These calls NEVER fail the parent operation:
- All `delta_port.emit()` calls — logged warning on failure
- `bridge_port.write_wal()` — WAL writes are best-effort
- `bridge_port.submit_audit()` — audit submission is best-effort
- `planner_port.cancel_plan()` — cleanup is best-effort

---

## 7. Internal Component Wiring

### 7.1 Factory Construction (15 steps)

```
OrchestratorConfig + 8 Port Adapters
  ↓
  OrchestratorPolicies ← config
  OrchestratorMetrics ← config.metrics_enabled
  ↓
  ErrorRouter(delta_port)
  ConcurrencyGuard()
  ↓
  StepRunner(fabric_port, error_router, policies, metrics)
  ↓
  Guards[4]: OutputSchemaGuard, ConditionalEdgeEvaluator,
             MicroReplanCheckpoint(planner_port), ExecutionMonitor(delta_port)
  ↓
  DAGExecutor(fabric, planner, delta, state, bridge, step_runner,
              error_router, guards, ParamResolver(), metrics)
  ↓
  ConstraintResolver(fabric, delta, event)
  WorkflowRegistry(storage) → WorkflowCompiler → WorkflowScheduler
  WorkflowRunSupervisor → CrossWorkflowResolver → ProactiveGapDetector
  ↓
  WorkflowEngine(supervisor, dag_executor, constraint_resolver,
                 registry, compiler, scheduler, cross_resolver,
                 gap_detector, delta, bridge)
  ↓
  MCPToolDiscovery → MCPRegistrationBridge → ConnectorLifecycleManager
  ↓
  OrchestratorService(mailbox, dag_executor, constraint_resolver,
                      workflow_engine, connector_lifecycle, error_router,
                      concurrency_guard, 7 ports, config, metrics)
```

### 7.2 Init Sequence (10 steps)

```
init()
  1. _validate_ports() — assert 13 deps non-None
  2. (reserved)
  3. crash_recovery() — WAL scan via bridge_port
  4. Assert ConcurrencyGuard not locked
  5. _discover_mcp_tools() — 500ms timeout
  6. (commentary)
  7. Load active workflows from registry
  8. Start WorkflowScheduler tick loop
  9. _subscribe_events() — 5 topic subscriptions
  10. Start GapDetector, ConnectorLifecycle, reaper, mailbox loop, admin HTTP
```

### 7.3 Shutdown Sequence (9 steps)

```
shutdown()
  1. Signal _running = False
  2. Stop connector lifecycle
  3. Wait active DAG (drain_timeout_ms = 30s)
  4. Force-compensate (V1: deferred)
  5. Stop scheduler
  6. Unsubscribe all events
  7. Persist triggers (V1: deferred)
  8. Audit write
  9. Cancel background tasks (reaper, mailbox loop)
```

---

## 8. Config Fields Affecting Processing

| Field | Default | Affects |
|---|---|---|
| `max_concurrent_dags` | 1 | ConcurrencyGuard (single DAG at a time) |
| `max_wave_parallelism` | 5 | Not used in V1 (Semaphore is 10 per wave) |
| `default_step_timeout_ms` | 30,000 | StepRunner per-step timeout |
| `plan_request_timeout_ms` | 45,000 | PlanRequest.timeout_ms |
| `hil_timeout_ms` | 120,000 | PendingHILContext expiry |
| `step_max_retries` | 2 | StepRunner retry budget |
| `max_micro_replans` | 1 | MicroReplanCheckpoint guard |
| `max_workflow_depth` | 3 | WorkflowDepthGuard |
| `context_reap_interval_ms` | 5,000 | Reaper loop frequency |
| `max_pending_plans` | 50 | PendingPlanContext capacity |
| `max_pending_hil` | 20 | PendingHILContext capacity |
| `mailbox_capacity` | 100 | MailboxAdapter max_depth |

---

## 9. Guard Pipeline Detail

### Execution Order per Wave

```
PRE-WAVE:
  1. ConditionalEdgeEvaluator.before_wave(wave, ctx, merged_results)
     → evaluates step.condition trees against prior results
     → returns SKIP decisions for false conditions

PER-STEP (parallel within wave):
  2. All guards.before_step(step, params) — no-op in M2
  3. StepRunner.run(step) → StepResult
  4. OutputSchemaGuard.after_step(step, result, ctx)
     → validates result.data against step.output_schema
     → RETRY on first failure, HARD_STOP on second
  5. ExecutionMonitor.after_step(step, result, ctx)
     → checks ctx.interrupt_flag → HARD_STOP

POST-WAVE:
  6. MicroReplanCheckpoint.after_wave(wave_result, ctx, remaining, plan_id)
     → detects discoveries in completed results
     → calls planner.micro_replan() if overlap with remaining steps
     → max 1 per DAG
  7. ExecutionMonitor.after_wave(wave_result, ctx, remaining, plan_id)
     → emits progress delta
     → HIL override request for significant waves (>3 steps or >5s)
```

---

## 10. Flags & Gaps

| # | Item | Status | Impact |
|---|---|---|---|
| F1 | `IStateReadPort` wired to `MockStateReadAdapter` | ⚠️ PLACEHOLDER | Safety band reads return empty, `get_snapshot()` returns empty. No session context for planning. |
| F2 | `IPlannerPort` hot-swapped at S6b | ✅ WORKING | `MockPlannerAdapter` → `PlannerAdapter` after Planner boots |
| F3 | `IBridgeWritePort.read()` returns `None` (BridgeClientShim) | ⚠️ OFFLINE | WAL reads fail → crash recovery no-ops, workflow save fails |
| F4 | `execute_batch()` not used by Orchestrator | ℹ️ INFO | All executions are per-step `execute()` calls |
| F5 | HIGH→MEDIUM degradation on planner failure | ⚠️ NOT IMPL | ErrorRouter classifies as FALLBACK but service doesn't act on it |
| F6 | Force-compensate on shutdown | ⚠️ V1 DEFERRED | Step 4 of shutdown is a no-op |
| F7 | Persist triggers on shutdown | ⚠️ V1 DEFERRED | Step 7 of shutdown is a no-op |
