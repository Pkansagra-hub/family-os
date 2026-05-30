# K1 Planner — WIRING

---

## 1. Construction entry points

`PlannerFactory` (`factory.py`) is a pure static factory — `__init__` raises `TypeError`.
All construction goes through one of four static methods:

| Method | Purpose | Returns |
|---|---|---|
| `create_standalone(config?, hil_port?)` | Self-contained with test adapters | `PlannerAgent` |
| `create_for_testing(config?, hil_port?, **overrides)` | Test adapters + per-port overrides | `Tuple[PlannerAgent, Dict[str, Any]]` |
| `create_with_ports(*, 7 explicit ports, hil_port?, config?)` | Caller-supplied ports (integration test or kernel) | `PlannerAgent` |
| `create_production(*, 7 explicit ports, hil_port?, config?)` | Production adapters, port validation enforced | `PlannerAgent` |

All four paths call the internal `_wire(ports, config, hil_port)` method.

**Caller responsibility:** `PlannerFactory` does NOT call `start()`. The caller must
`asyncio.create_task(agent.start())` to activate the dequeue loop.

---

## 2. `_wire()` — 10-step construction sequence

```
ports = {
    "llm_port": ILLMPort,
    "fabric_retrieval": IFabricRetrievalPort,
    "state_read": IStateReadPort,
    "bridge_port": IPlannerWritePort,
    "delta_port": IDeltaEmitPort,
    "event_port": IEventPort,
    "mailbox_port": IMailboxPort,
}

Step 0:  _validate_ports(ports)
         → isinstance(port, Protocol) check for all 7
         → MissingPortError if any is None
         → InvalidPortError if isinstance fails
         → DuplicatePortError if any id(a) == id(b) pair

Step 1:  tool_router = ToolCallRouter(
             fabric_retrieval=ports["fabric_retrieval"],
             state_read=ports["state_read"],
             bridge_port=ports["bridge_port"],
             config=config
         )

Step 2:  [hil_port comes from caller, not constructed here]

Step 3:  sketch = SketchService(
             llm_port=ports["llm_port"],
             tool_router=tool_router,
             hil_port=hil_port   # may be None
         )

Step 4:  expand = ExpandService(
             llm_port=ports["llm_port"],
             tool_router=tool_router
             # NO hil_port — EXPAND has no HIL
         )

Step 5:  validate = ValidateService(
             llm_port=ports["llm_port"],
             fabric_retrieval=ports["fabric_retrieval"],
             hil_port=hil_port   # may be None
         )

Step 6:  commit = CommitService(
             bridge_port=ports["bridge_port"],
             delta_port=ports["delta_port"],
             event_port=ports["event_port"]
             # NO llm_port — PLAN-03
         )

Step 7:  pipeline = PipelineController(
             sketch=sketch,
             expand=expand,
             validate=validate,
             commit=commit,
             delta_port=ports["delta_port"],
             event_port=ports["event_port"],
             config=config,
             hil_port=hil_port
         )

Step 8:  agent = PlannerAgent(
             mailbox=ports["mailbox_port"],
             pipeline=pipeline,
             event_port=ports["event_port"],
             config=config
         )

Step 8b: if hasattr(ports["mailbox_port"], "set_pipeline_controller"):
             ports["mailbox_port"].set_pipeline_controller(pipeline)
         # MailboxAdapter stores pipeline ref for direct micro_replan()

Step 9:  return agent
         # Caller must: asyncio.create_task(agent.start())

Step 10: [KERNEL PHASE 5 — IMPLEMENTED in service.py:1322-1422]
         # S5: Orchestrator built with MockPlannerAdapter placeholder
         # S6a: PlannerFactory.create_production(...) builds real PlannerAgent
         # S6b: PlannerAdapter(mailbox, cb_planner) and orchestrator.bind_planner()
         # S7: asyncio.create_task(planner.start()) + cross-wire verification
         # MockPlannerAdapter is replaced before _running = True
         # Live coverage: tests/integration/k1/live/m2/test_m2_l2_planner_orchestrator_crosswire.py
```

---

## 3. Adapter construction and what they wrap

| Adapter | Constructor | Wraps | Key translation |
|---|---|---|---|
| `LLMGatewayAdapter(bus, consumer_id="planner")` | `llm_gateway_adapter.py` | `ILLMRequestBus` (Model Hub) | `PlannerLLMRequest` → `HubRequest(CapabilityType, ChatPayload/StructuredPayload, Priority.INTERACTIVE)` via `_build_payload()`; response `text`/`json_output` backfilled to `content` |
| `FabricRetrievalAdapter(fabric, timeout_ms=50, max_retries=1)` | `fabric_retrieval_adapter.py` | `IRetrievalEngine` (Fabric) | Direct in-process call; `asyncio.wait_for(50ms)` timeout; retry-once; returns empty `RetrievalResult` on failure |
| `SessionStateReadAdapter(reader, session_id)` | `session_state_adapter.py` | `ISessionStateReader` (Fabric) | Pre-binds `session_id`; wraps result in `SessionSnapshot` |
| `BridgeAdapter(bridge_port)` | `bridge_adapter.py` | `IFabricK0Port` (Bridge/K0) | `recall()` → `bridge.query("memory.recall", {...})`; `persist_plan()` → `bridge.send_command("memory.store", plan.to_dict())` fire-and-forget |
| `DeltaBusAdapter(bus, agent_id="planner")` | `delta_bus_adapter.py` | `IDeltaBusPort` (Fabric) | `emit(DeltaPayload)` → `bus.emit_delta(agent_id, delta_type, section, data)` |
| `EventBusAdapter(event_port)` | `event_bus_adapter.py` | `IEventPort` (Fabric) | Thin passthrough; `emit()` wraps in `try/except` |
| `MailboxAdapter(max_depth=5, priority_class="INTERACTIVE")` | `mailbox_adapter.py` | `asyncio.Queue[PlanRequest]` | `enqueue` → `put_nowait`; `dequeue` → `get()`; `drain` → `get_nowait()` loop |

**Structural typing note:** `BridgeAdapter` uses a local `IFabricK0Port` structural Protocol
to avoid a circular import from `k1.fabric`. The real fabric bridge is duck-typed.

---

## 4. `ToolCallRouter` routing table

`ToolCallRouter` is a shared dependency injected into both `SketchService` and `ExpandService`.
It owns a frozen `_ROUTING_TABLE`:

```python
_ROUTING_TABLE = MappingProxyType({
    "discover_capabilities":  "_fabric_retrieval",   # IFabricRetrievalPort
    "find_relevant_prompts":  "_fabric_retrieval",   # IFabricRetrievalPort
    "query_planning_context": "_state_read",          # IStateReadPort
    "recall_for_planning":    "_bridge_port",         # IPlannerWritePort
})
```

`get_schema(capability_name)` is routed to `_fabric_retrieval.discover_capabilities(intent=name, top_k=1)`
(pragmatic workaround — see Open Issues).

Retry policy per tool (from `_RETRY_POLICY`):

| Tool | timeout_ms | max_retries |
|---|---|---|
| `discover_capabilities` | 50 | 1 |
| `find_relevant_prompts` | 50 | 1 |
| `query_planning_context` | 10 | 0 |
| `recall_for_planning` | 100 | 0 |

Retries do NOT increment PLAN-05 budget counter. `get_schema()` bypasses counter entirely.

`ExpandService` may also receive an injected prompt inventory. EXPAND uses that inventory only to preserve exact `prompt_template` names when `find_prompts` was not called or did not return the exact name. If no inventory is injected, unverified prompt names are cleared; EXPAND does not read prompt-contract files or Fabric adapters directly.

---

## 5. `PlannerAgent.start()` — activation sequence

```
1. _running = True
2. Subscribe: event_port.subscribe(TOPIC_PLAN_REQUEST, _on_plan_request)
              → stored in _subscriptions
   Subscribe: event_port.subscribe(TOPIC_PLAN_CANCEL, _on_plan_cancel)
              → stored in _subscriptions
   (E5 note: HIL topic subscriptions removed — now via IHILPort)
3. Enter _run_loop():
   while _running:
       request = await mailbox.dequeue()       ← blocks until plan arrives
       if request.request_id in _cancel_set:   ← cancel pre-check (checkpoint 1)
           _emit_cancelled(request, "pre_dequeue")
           _cancel_set.discard(request_id)
           continue
       _in_flight_request_id = request.request_id
       async with _plan_lock:
           cancel_check = lambda: request_id in _cancel_set
           try:
               committed = await pipeline.execute(request, cancel_check)
               _cancel_set.discard(request_id)
           except PlanCancelledError:
               pass  # pipeline already emitted cancelled.v1
           except Exception as exc:
               pass  # pipeline already emitted failed.v1
           finally:
               _in_flight_request_id = None
```

---

## 6. `PlannerAgent.stop()` — shutdown sequence

```
1. _running = False
2. await mailbox.begin_shutdown()      ← sets _shutdown flag; drain() returns pending
3. if _in_flight_request_id:
       await mailbox.send_cancel(_in_flight_request_id)
       wait up to shutdown_grace_period_ms=5,000ms for _plan_lock
4. for handle in _subscriptions:
       event_port.unsubscribe(handle)
5. _subscriptions.clear()
```

---

## 7. `PipelineController` — internal call graph per plan

```
execute(request, cancel_check):
    reset()       ← clears per-plan state, FSM to IDLE
    hil_port.reset_round_budget("planner:sketch:{plan_id}")  [E5]
    hil_port.reset_round_budget("planner:validate:{plan_id}") [E5]

    FSM: IDLE → SKETCHING
    _emit_stage_delta(SKETCH, STARTED)

    ctx = _create_stage_context(SKETCH)
    sketch_result = await sketch.execute(request, ctx)

    _check_cancel(checkpoint 2)
    _check_timeout(checkpoint 2)
    FSM: SKETCHING → EXPANDING
    _emit_stage_delta(EXPAND, STARTED)

    while revise_count <= 1:
        ctx = _create_stage_context(EXPAND)
        expanded_plan = await expand.execute(sketch_result, request, ctx,
                                              arbiter_feedback=last_verdict.suggested_fixes)
        _check_cancel(checkpoint 3)
        _check_timeout(checkpoint 3)
        FSM: EXPANDING → VALIDATING
        _emit_stage_delta(VALIDATE, STARTED)

        ctx = _create_stage_context(VALIDATE)
        verdict = await validate.execute(expanded_plan, request, ctx)

        if verdict.status == APPROVED: break
        if revise_count == 0 and verdict.status in (REVISE, REJECT):
            revise_count += 1
            FSM: VALIDATING → EXPANDING
            continue
        if verdict.status == REVISE: break  # second revise = best-effort
        raise ValidateRejectedError        # second reject

    _check_cancel(checkpoint 4)
    _check_timeout(checkpoint 4)
    FSM: VALIDATING → COMMITTING
    _emit_stage_delta(COMMIT, STARTED)

    ctx = _create_stage_context(COMMIT)
    committed = await commit.execute(expanded_plan, request, verdict, ctx)
    # commit.execute() emits TOPIC_PLAN_READY

    FSM: COMMITTING → COMPLETED
    _emit_plan_end_delta()
    return committed
```

---

## 8. `PipelineController` budget injection (`_create_stage_context`)

```python
def _create_stage_context(self, phase: StagePhase) -> StageContext:
    elapsed_ms = int((time.time() - self._plan_start_time) * 1000)
    return StageContext(
        request_id=self._current_request.request_id,
        trace_id=self._current_request.trace_id,
        timeout_remaining_ms=max(1, self._config.pipeline_timeout_ms - elapsed_ms),
        token_budget_remaining=max(0, self._config.total_token_budget - self._total_plan_tokens),
        cancel_check=self._active_cancel_check,
        stage_budget=PlannerConstraints(
            max_tokens=getattr(self._config, f"{phase.value.lower()}_max_tokens"),
            timeout_ms=getattr(self._config, f"{phase.value.lower()}_timeout_ms"),
            temperature=getattr(self._config, f"{phase.value.lower()}_temperature"),
        )
    )
```

---

## 9. `CommitService` — critical-path duration algorithm

```python
def _compute_critical_path_duration(steps, dependencies) -> int:
    # Kahn's topological sort + longest-path DP
    dist = {s.step_id: s.timeout_ms for s in steps}
    in_degree = {s.step_id: 0 for s in steps}
    for step_id, deps in dependencies.items():
        in_degree[step_id] += len(deps)

    queue = deque([s.step_id for s in steps if in_degree[s.step_id] == 0])
    topo = []
    while queue:
        node = queue.popleft()
        topo.append(node)
        for successor, deps in dependencies.items():
            if node in deps:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

    for node in topo:
        for successor, deps in dependencies.items():
            if node in deps:
                dist[successor] = max(dist[successor], dist[node] + step_timeout[successor])

    return max(dist.values()) if dist else 0
    # For fully parallel plans (no dependencies): returns max(step.timeout_ms)
    # For linear chains: returns sum(step.timeout_ms)
```

---

## 10. Event subscription registration graph

```
PlannerAgent.start()
    ├── event_port.subscribe("k1.planner.plan.request.v1", _on_plan_request)
    └── event_port.subscribe("k1.planner.plan.cancel.v1", _on_plan_cancel)

PlannerAgent.stop()
    ├── event_port.unsubscribe(handle_plan_request)
    └── event_port.unsubscribe(handle_plan_cancel)
```

`CommitService` emits (not subscribes) via `event_port.emit()`:
- `k1.planner.plan.ready.v1`

`PipelineController` emits via `delta_port.emit()` and `event_port.emit()`:
- `k1.planner.plan.failed.v1`
- `k1.planner.plan.cancelled.v1`
- `k1.planner.delta.v1` (every FSM transition + plan-start + plan-end)

---

## 11. K1 inter-component dependencies (imports)

| Dependency | Module | Imported by | Purpose |
|---|---|---|---|
| `CommittedPlan, PlanRequest, PlanStep, MicroReplanRequest, StepResult, PlanAck` | `k1.orchestrator.types` | `types.py`, `planner_agent.py`, `stages/` | Shared plan types |
| `ScoredCapability, RetrievalResult` | `k1.fabric.types` | `types.py`, `stages/sketch_service.py` | Capability discovery results |
| `IRetrievalEngine` | `k1.fabric.fabric` | `adapters/fabric_retrieval_adapter.py` | Wrapped by FabricRetrievalAdapter |
| `ISessionStateReader, SessionSnapshot` | `k1.fabric.ports.state_reader` | `adapters/session_state_adapter.py` | Wrapped by SessionStateReadAdapter |
| `IFabricK0Port` | `k1.fabric.ports.bridge_port` | `adapters/bridge_adapter.py` | Wrapped by BridgeAdapter |
| `IDeltaBusPort` | `k1.fabric.ports.delta_bus` | `adapters/delta_bus_adapter.py` | Wrapped by DeltaBusAdapter |
| `SubscriptionHandle, IEventPort` | `k1.fabric.ports.event_port` | `adapters/event_bus_adapter.py`, `planner_agent.py` | Bus subscription handles |
| `IModelHubPort, CapabilityType, HubRequest, Priority, RequestConstraints` | `k1.model_hub.types` + `k1.model_hub.adapters` | `adapters/llm_gateway_adapter.py` | LLM call translation |
| `IHILPort` | `k1.kernel.ports.hil_port` | `stages/sketch_service.py`, `stages/validate_service.py`, `pipeline_controller.py` | HIL clarification/approval |
| `ClarificationRequest, ApprovalRequest` | `k1.hil.types` | `stages/sketch_service.py`, `stages/validate_service.py` | HIL payload types |

Planner does NOT import from: `k1.concierge`, `k1.memory_writer`, `k1.sessionstate` (direct).
