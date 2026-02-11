# Milestone 2: Core DAG Engine -- Work Tickets

> **Module**: Orchestrator (Layer 2 in K1 Cognitive Architecture)
> **Milestone**: M2 -- Core DAG Engine
> **Goal**: Implement the OrchestratorService message router, DAGExecutor topological walker, and StepRunner single-step execution with retry policy.
> **Prerequisite**: M1 Foundation complete (all types, ports, contracts, and event schemas exist)
> **Estimated Epics**: 3 (2.1 OrchestratorService, 2.2 DAGExecutor, 2.3 StepRunner + ParamResolver)
> **Estimated Issues**: 19

---

## How to Use These Tickets

Each ticket is self-contained. Before starting:

1. Read **Context Files** listed in the ticket
2. Check **Blocked By** -- all listed tickets must be complete
3. Follow **Anti-Hallucination Rules** strictly
4. Verify all items in **Done When** checklist upon completion

---

## Global Anti-Hallucination Rules (ALL M2 Tickets)

- OrchestratorService does NOT call `fabric_port.execute()` for HIGH tier -- that goes through DAGExecutor
- OrchestratorService calls `fabric_port.execute()` directly ONLY for MEDIUM tier (2.1.3)
- DAGExecutor does NOT dequeue from mailbox -- that is `_mailbox_loop()` (M6)
- DAGExecutor does NOT call `planner_port.request_plan()` -- that is `dispatch_high()` (2.1.4)
- StepRunner calls `fabric_port.execute()` (single step), NEVER `execute_batch()`
- StepRunner does NOT check interrupt_flag -- that is ExecutionMonitor's job (M3)
- StepRunner does NOT write WAL -- that is DAGExecutor's job
- ParamResolver is a pure function with NO I/O -- does NOT call any port
- Do NOT add LLM calls anywhere
- Do NOT write to SessionState (ORCH-01: read-only)

---

## Epic 2.1: OrchestratorService

> **File**: `k1/orchestrator/orchestration/orchestrator_service.py`
> **Constructor**: 12 dependencies, wired by OrchestratorFactory (M6 Epic 6.2.1)
> **Key invariant**: OrchestratorService is the ONLY entry point -- all messages flow through `process()` via the mailbox

---

### WT-2.1.1: OrchestratorService Class Skeleton + Constructor

**Deliverable**: `k1/orchestrator/orchestration/orchestrator_service.py`

**Blocked By**: All M1 types (WT-1.2.*), All M1 ports (WT-1.4.*)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 351-370 -- Epic 2.1 wiring section)
- [orchestrator.mmd](k1/orchestrator/orchestrator.mmd) (S "OrchestratorService")
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S1 -- ProcessingContext)

**Specification**:
Create `OrchestratorService` class with 12 constructor dependencies:

```python
class OrchestratorService:
    def __init__(
        self,
        mailbox: IMailboxPort,
        fabric_port: IFabricGatewayPort,
        planner_port: IPlannerPort,
        state_port: IStateReadPort,
        delta_port: IDeltaEmitPort,
        bridge_port: IBridgeWritePort,
        event_port: IEventSubscriptionPort,
        dag_executor: "DAGExecutor",            # forward ref, M2
        constraint_resolver: "ConstraintResolver",  # forward ref, M3
        workflow_engine: "WorkflowEngine",       # forward ref, M4
        connector_manager: "ConnectorManager",   # forward ref, M5
        error_router: "ErrorRouter",             # M2
    ): ...
```

Internal state: `self.pending_plans: Dict[str, PendingPlanContext] = {}` (max 50), `self.pending_hil: Dict[str, PendingHILContext] = {}` (max 20), `self.concurrency_guard: ConcurrencyGuard`, `self._running: bool = False`.

Primary dispatch method: `async def process(self, msg: Any) -> ProcessResult` -- routes by isinstance:
- `TaskEnvelope` -> `route_task()`
- `CommittedPlan` -> `receive_plan()`
- `WorkflowRunRequest` -> `dispatch_workflow()`
- `WorkflowSaveRequest` -> `save_workflow()`
- `InterruptRequest` -> `handle_interrupt()`
- Unknown type -> log warning, return FAILED

Wrap `process()` body in try/except calling `error_router.route_error()`.

**Anti-Hallucination Rules**:
- Forward references for M3/M4/M5 deps are acceptable -- they will be None/stub until those milestones
- Do NOT implement `_mailbox_loop()` here (that is M6 Epic 6.2.5)
- `process()` is called BY the mailbox loop, not the other way around

**Done When**:
- [ ] File exists at `k1/orchestrator/orchestration/orchestrator_service.py`
- [ ] Constructor accepts 12 dependencies
- [ ] `process()` routes by isinstance to 5 handlers
- [ ] `pending_plans` and `pending_hil` dicts initialized with hard caps
- [ ] error_router.route_error() in catch block
- [ ] No I/O in constructor

---

### WT-2.1.2: Implement route_task() — Task Routing by Tier

**Deliverable**: `k1/orchestrator/orchestration/orchestrator_service.py` (add `route_task` method)

**Blocked By**: WT-2.1.1 (class skeleton), WT-1.2.1 (TaskEnvelope), WT-1.2.17 (event catalog)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 351-360 -- message routing call chain)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S1 -- ProcessingContext, S3 -- TASK_ACCEPTED event schema)

**Specification**:
```python
async def route_task(self, envelope: TaskEnvelope) -> ProcessResult:
```

Logic:
1. Validate envelope (tier in {"MEDIUM", "HIGH"}, trace_id non-empty)
2. Emit `TASK_ACCEPTED` event via `delta_port.emit(ORCH_TASK_ACCEPTED, {...}, envelope.trace_id)`
3. Branch by tier:
   - `MEDIUM` -> `return await self.dispatch_medium(envelope)`
   - `HIGH` -> `return await self.dispatch_high(envelope)`
4. Unknown tier -> return `ProcessResult.FAILED`

**Done When**:
- [ ] `route_task()` method implemented
- [ ] TASK_ACCEPTED event emitted before dispatch
- [ ] Tier branching: MEDIUM vs HIGH
- [ ] Validation rejects invalid tiers
- [ ] Returns ProcessResult enum value

---

### WT-2.1.3: Implement dispatch_medium() — Direct Fabric Execution

**Deliverable**: `k1/orchestrator/orchestration/orchestrator_service.py` (add `dispatch_medium` method)

**Blocked By**: WT-2.1.2, WT-1.4.2 (IFabricGatewayPort), WT-1.4.4 (IStateReadPort), WT-1.2.5 (StepResult), WT-1.2.4 (AggregatedResult)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 355-358 -- dispatch_medium call chain)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S7 -- safety_band read pattern)
- [types.py stub from M1](k1/orchestrator/types.py) (TaskEnvelope, StepResult, AggregatedResult)

**Specification**:
```python
async def dispatch_medium(self, envelope: TaskEnvelope) -> ProcessResult:
```

Logic:
1. Read safety_band: `band = await self.state_port.read("control.safety_band")`
2. For each capability in `envelope.capabilities` (max 2 per ORCH-10):
   a. Query registry: `entry = await self.fabric_port.query_registry(cap_name)`
   b. If not found -> skip with warning
   c. Build `CapabilityRequest`: capability_name, params from envelope.params[cap_name], tier="MEDIUM", caller="orchestrator", trace_id, timeout_ms from envelope
3. Execute: single capability -> `fabric_port.execute(request)`, multiple -> `fabric_port.execute_batch(requests)`
4. Wrap results in `StepResult` list
5. Aggregate: `result = AggregatedResult.from_medium(step_results, envelope.trace_id)`
6. Emit completion event
7. Return `ProcessResult.COMPLETED` or `ProcessResult.FAILED`

**Anti-Hallucination Rules**:
- MEDIUM tier calls `fabric_port.execute()` or `execute_batch()` DIRECTLY
- MEDIUM does NOT go through DAGExecutor
- Max 2 capabilities for MEDIUM (ORCH-10)

**Example Input/Output**:
```python
# Input: TaskEnvelope(tier="MEDIUM", capabilities=["tool.calendar.search"], ...)
# Output: ProcessResult.COMPLETED + AggregatedResult with 1 StepResult
```

**Done When**:
- [ ] `dispatch_medium()` reads safety_band from state_port
- [ ] Builds CapabilityRequest per capability
- [ ] Calls fabric_port.execute() or execute_batch()
- [ ] Wraps in StepResult -> AggregatedResult.from_medium()
- [ ] Emits completion event
- [ ] Handles missing capabilities gracefully

---

### WT-2.1.4: Implement dispatch_high() + receive_plan() — Event-Driven Planning

**Deliverable**: `k1/orchestrator/orchestration/orchestrator_service.py` (add `dispatch_high` + `receive_plan` methods)

**Blocked By**: WT-2.1.2, WT-1.2.2 (PlanRequest), WT-1.2.3 (CommittedPlan), WT-1.2.19 (PendingPlanContext), WT-1.4.3 (IPlannerPort), WT-1.1.12 (ADR for event-driven pattern)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 356-359 -- dispatch_high and receive_plan)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S10 -- Planner-Orchestrator protocol)
- ADR-1.1.12 (event-driven HIGH tier)

**Specification**:

**dispatch_high()**:
```python
async def dispatch_high(self, envelope: TaskEnvelope) -> ProcessResult:
```
Logic:
1. `snapshot = await self.state_port.snapshot(["user", "session", "control"])`
2. Build `PlanRequest(request_id=uuid4(), intent=envelope.intent, constraints=envelope.constraints, context=snapshot, trace_id=envelope.trace_id, timeout_ms=45000)`
3. `ack = await self.planner_port.request_plan(plan_request)` -- fire-and-forget
4. Park context: `self.pending_plans[plan_request.request_id] = PendingPlanContext(request_id=plan_request.request_id, task_envelope=envelope, state_snapshot=snapshot, created_at=time.time(), timeout_ms=45000)`
5. Check hard cap: `if len(self.pending_plans) > 50: reject oldest`
6. Emit PLAN_REQUESTED event
7. Return `ProcessResult.DEFERRED` -- NOT blocking

**receive_plan()**:
```python
async def receive_plan(self, plan: CommittedPlan) -> ProcessResult:
```
Logic:
1. Dedup check: if plan.request_id not in self.pending_plans -> log warning, return (stale/duplicate)
2. Pop context: `ctx = self.pending_plans.pop(plan.request_id)`
3. Fresh snapshot: `fresh_snapshot = await self.state_port.snapshot(["user", "session", "control"])`
4. Validate via constraint_resolver (M3, stub for now): `validation = await self.constraint_resolver.validate(plan)`
5. Execute DAG: `result = await self.dag_executor.execute(plan, fresh_snapshot)`
6. Aggregate and emit
7. Return `ProcessResult.COMPLETED` or `ProcessResult.FAILED`

**Anti-Hallucination Rules**:
- dispatch_high() RETURNS IMMEDIATELY after parking context (DEFERRED)
- dispatch_high() does NOT await a plan -- it sends request and returns
- receive_plan() is called when CommittedPlan arrives as a mailbox message
- request_id is a NEW UUID (not envelope_id) -- Planner echoes it back

**Done When**:
- [ ] `dispatch_high()` sends PlanRequest, parks PendingPlanContext, returns DEFERRED
- [ ] `receive_plan()` pops PendingPlanContext by request_id
- [ ] Dedup check on receive_plan (stale/duplicate plan)
- [ ] Fresh state snapshot in receive_plan (not reusing dispatch_high snapshot)
- [ ] Hard cap on pending_plans (50)
- [ ] PLAN_REQUESTED event emitted

---

### WT-2.1.5: Implement aggregate() — Pure Result Aggregation

**Deliverable**: `k1/orchestrator/orchestration/orchestrator_service.py` (add `aggregate` method)

**Blocked By**: WT-1.2.4 (AggregatedResult), WT-1.2.5 (StepResult)

**Context Files**:
- [types.py stub from M1](k1/orchestrator/types.py) (AggregatedResult factory methods)

**Specification**:
```python
def aggregate(
    self,
    step_results: List[StepResult],
    plan_id: Optional[str],
    trace_id: str,
    compensations: Optional[List[CompensationRecord]] = None,
    token_budget_max: Optional[int] = None,
) -> AggregatedResult:
```

Logic -- PURE FUNCTION (no I/O, no side effects):
1. Count: completed, failed, cancelled, skipped from step_results
2. Sum: total_tokens_consumed, total_cost_usd from step_results
3. Compute: success = (failed == 0 and cancelled == 0)
4. Compute: budget_utilization = total_tokens / token_budget_max (0.0 if None)
5. Compute: duration_ms from first to last step started_at/completed_at
6. Delegate to `AggregatedResult.from_medium()` or `AggregatedResult.from_dag()` factory

**Done When**:
- [ ] `aggregate()` is a pure function (no async, no I/O)
- [ ] Correctly counts all 4 status categories
- [ ] success computation: failed==0 AND cancelled==0
- [ ] Division-by-zero protection on budget_utilization
- [ ] Works for both MEDIUM (no plan_id) and HIGH (with plan_id) tiers

---

### WT-2.1.6: Implement save_workflow() — Workflow Save Handler

**Deliverable**: `k1/orchestrator/orchestration/orchestrator_service.py` (add `save_workflow` method)

**Blocked By**: WT-2.1.1, WT-1.2.11 (WorkflowSaveRequest + TriggerSpec)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 360-361 -- save_workflow call chain)

**Specification**:
```python
async def save_workflow(self, request: WorkflowSaveRequest) -> ProcessResult:
```

Logic:
1. Look up plan from DAGExecutor cache or WAL: `plan = ...` (lookup mechanism TBD by M4)
2. Build WorkflowSpec from request + plan
3. `await self.workflow_engine.registry.save(spec)`
4. `await self.workflow_engine.scheduler.register_trigger(spec.trigger)`
5. Emit workflow_saved delta
6. Return ProcessResult.COMPLETED

**Note**: This method's full implementation depends on M4 (WorkflowEngine). For M2, create the method stub with the routing logic and a TODO for M4 dependencies.

**Done When**:
- [ ] `save_workflow()` skeleton exists
- [ ] WorkflowSaveRequest handled in process() isinstance routing
- [ ] TODO markers for M4-dependent logic
- [ ] Emits delta on success

---

### WT-2.1.7: Implement ErrorRouter — Stateless Error Classification

**Deliverable**: `k1/orchestrator/orchestration/error_router.py`

**Blocked By**: WT-1.2.10 (ErrorSeverity, AdapterError), WT-1.4.5 (IDeltaEmitPort)

**Context Files**:
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S7 -- circuit breakers, error classification matrix)
- [types.py stub from M1](k1/orchestrator/types.py) (AdapterError, ErrorSeverity)

**Specification**:
```python
class ErrorRouter:
    def __init__(self, delta_port: IDeltaEmitPort):
        self.delta_port = delta_port  # for diagnostic deltas
```

Primary method:
```python
def route_error(self, error: AdapterError, context: ProcessingContext) -> ErrorAction:
```

`ErrorAction = Enum: RETRY, DEGRADE, ABORT, FALLBACK, LOG_ONLY, CIRCUIT_BREAK, DEAD_LETTER`

Classification matrix (7 classifications per WB S7):
| Adapter | Error Severity | Action |
|---------|---------------|--------|
| Mailbox | RECOVERABLE | RETRY |
| Fabric | DEGRADED | DEGRADE |
| Planner | DEGRADED | FALLBACK (trigger tier degradation) |
| StateRead | DEGRADED | DEGRADE (use stale snapshot) |
| DeltaEmit | RECOVERABLE | LOG_ONLY (fire-and-forget) |
| BridgeWrite | RECOVERABLE | LOG_ONLY (best-effort) |
| EventSub | RECOVERABLE | RETRY (reconnect) |

ErrorRouter is **stateless** and **side-effect-free** (except diagnostic deltas). Caller executes the returned action.

**Anti-Hallucination Rules**:
- ErrorRouter does NOT execute recovery actions -- it classifies and returns
- Caller (OrchestratorService.process() catch block) executes the action
- ErrorRouter does NOT track circuit breaker state (CB state is per-adapter)

**Done When**:
- [ ] `ErrorRouter` class in `error_router.py`
- [ ] `route_error()` returns ErrorAction based on adapter_name + severity
- [ ] All 7 classifications from matrix implemented
- [ ] ErrorAction enum with 7 values
- [ ] Diagnostic delta emitted for each error
- [ ] Stateless: no mutable internal state

---

## Epic 2.2: DAGExecutor

> **File**: `k1/orchestrator/orchestration/dag_executor.py`
> **Constructor**: 8 dependencies (fabric_port, planner_port, delta_port, state_port, bridge_port, step_runner, error_router, guards)
> **Key invariant**: DAGExecutor is called by OrchestratorService.receive_plan() -- NEVER directly by mailbox loop

---

### WT-2.2.1: Implement build_waves() — Topological Sort (Kahn's Algorithm)

**Deliverable**: `k1/orchestrator/orchestration/dag_executor.py` (DAGExecutor class + build_waves method)

**Blocked By**: WT-1.2.18 (PlanStep), WT-1.2.7 (Wave), WT-1.2.3 (CommittedPlan)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 396-410 -- build_waves spec with Kahn's algorithm)

**Specification**:
Create `DAGExecutor` class with 8-dep constructor:
```python
class DAGExecutor:
    def __init__(
        self,
        fabric_port: IFabricGatewayPort,
        planner_port: IPlannerPort,
        delta_port: IDeltaEmitPort,
        state_port: IStateReadPort,
        bridge_port: IBridgeWritePort,
        step_runner: "StepRunner",
        error_router: ErrorRouter,
        guards: List["DAGGuard"],  # empty in M2, populated by M3
    ): ...
```

Internal state: `self.interrupt_flag: bool = False`, `self.merged_results: Dict[str, CapabilityResult] = {}`, `self._cancelled_steps: Set[str] = set()`.

```python
def build_waves(self, steps: List[PlanStep], dependencies: Dict[str, List[str]]) -> List[Wave]:
```

Algorithm (Kahn's topological sort):
1. Compute in_degree for each step from dependencies dict
2. Initialize queue with steps having in_degree == 0
3. While queue non-empty: pop all zero-in_degree steps -> form `Wave(wave_index, steps, {})`
4. Decrement in_degree of dependents. Add newly-zero steps to queue
5. If steps remain after queue empty -> cycle detected -> raise `CycleError`
6. Validate: `len(waves) <= 20` (max_waves), total steps <= 50

**Anti-Hallucination Rules**:
- `build_waves()` is a PURE FUNCTION -- no I/O, no async
- Uses `dependencies` dict from CommittedPlan directly (not re-derived from PlanStep.deps)
- Unit-testable with just PlanStep lists

**Example Input/Output**:
```python
# Input:
steps = [PlanStep(id="s1", ...), PlanStep(id="s2", ...), PlanStep(id="s3", ...)]
deps = {"s2": ["s1"], "s3": ["s1"]}
# Output:
[Wave(0, [s1], {}), Wave(1, [s2, s3], {})]  # s2 and s3 are parallel in wave 1
```

**Done When**:
- [ ] DAGExecutor class with 8-dep constructor
- [ ] `build_waves()` implements Kahn's algorithm
- [ ] Cycle detection raises CycleError
- [ ] Validation: max 20 waves, max 50 steps
- [ ] Returns List[Wave] ordered by wave_index
- [ ] Pure function, no I/O

---

### WT-2.2.2: Implement execute() + execute_wave() — Parallel Wave Executor

**Deliverable**: `k1/orchestrator/orchestration/dag_executor.py` (add execute + execute_wave methods)

**Blocked By**: WT-2.2.1, WT-2.3.1 (StepRunner), WT-2.3.5 (ParamResolver), WT-1.4.6 (IBridgeWritePort for WAL)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 410-440 -- execute and execute_wave spec)
- [schema_whiteboard.md](docs/whiteboard/schema_whiteboard.md) (S7 -- safety_band read pattern)

**Specification**:

**execute()**:
```python
async def execute(self, plan: CommittedPlan, snapshot: ContextSnapshot) -> AggregatedResult:
```
Logic:
1. Reset state: `self.interrupt_flag = False`, `self.merged_results = {}`, `self._cancelled_steps = set()`
2. Init token tracker + cost accumulator from plan budgets
3. `waves = self.build_waves(plan.steps, plan.dependencies)`
4. WAL write: `await bridge_port.write_wal(plan.plan_id, "PLAN_START", plan.to_dict(), plan.trace_id)`
5. For each wave: `result = await self.execute_wave(wave, plan, snapshot)`
6. Collect wave_results. If abort condition -> break
7. Run guards post-wave (no-op in M2 -- guards list is empty)
8. Return `collect_results(wave_results, plan, compensations)`

**execute_wave()**:
```python
async def execute_wave(self, wave: Wave, plan: CommittedPlan, snapshot: ContextSnapshot) -> WaveResult:
```
Logic:
1. Safety band re-read: `band = await self.state_port.read("control.safety_band")` -- if RED/BLACK: abort DAG
2. Filter out cancelled steps: `active_steps = [s for s in wave.steps if s.id not in self._cancelled_steps]`
3. Resolve params via ParamResolver for each active step
4. `sem = asyncio.Semaphore(10)` -- max 10 concurrent
5. Create tasks: `asyncio.create_task(self._execute_step(step, params, trace_id))` per step
6. `asyncio.as_completed()` -- after EACH step: check `self.interrupt_flag` (SPEC-5), store in `self.merged_results[step.id]`
7. WAL write: `WAVE_COMPLETE`
8. Emit delta progress
9. Return WaveResult

**_execute_step()**: delegates to `step_runner.run()`, updates `merged_results`, token_tracker, cost_accumulator.

**Done When**:
- [ ] `execute()` resets state, builds waves, iterates with WAL writes
- [ ] `execute_wave()` re-reads safety_band, filters cancelled, runs parallel with Semaphore(10)
- [ ] `_execute_step()` delegates to step_runner, updates merged_results
- [ ] Interrupt flag checked after EACH step completion (not just wave boundary)
- [ ] WAL writes at PLAN_START + WAVE_COMPLETE points
- [ ] Safety band RED/BLACK causes immediate DAG abort

---

### WT-2.2.3: Implement collect_results() — DAG Result Aggregation

**Deliverable**: `k1/orchestrator/orchestration/dag_executor.py` (add `collect_results` method)

**Blocked By**: WT-2.2.2, WT-1.2.4 (AggregatedResult), WT-1.2.13 (CompensationRecord)

**Specification**:
```python
def collect_results(
    self,
    wave_results: List[WaveResult],
    plan: CommittedPlan,
    compensations: List[CompensationRecord],
) -> AggregatedResult:
```

Logic:
1. Flatten all StepResults from all WaveResults
2. For steps not in any WaveResult (cancelled/skipped dependents): create synthetic `StepResult(status=CANCELLED)`
3. Sum: tokens_consumed, cost_usd
4. Compute: duration_ms (wall clock from DAG start to now)
5. Delegate to `AggregatedResult.from_dag()` factory

**Anti-Hallucination Rules**:
- Must handle partial wave_results (DAG aborted mid-execution)
- Steps not present in ANY WaveResult get status=CANCELLED

**Done When**:
- [ ] `collect_results()` flattens wave results
- [ ] Creates synthetic CANCELLED StepResults for missing steps
- [ ] Handles partial DAG execution gracefully
- [ ] Correctly sums tokens and costs
- [ ] Returns AggregatedResult via from_dag() factory

---

### WT-2.2.4: Implement cancel_dependents() — BFS Dependent Cancellation

**Deliverable**: `k1/orchestrator/orchestration/dag_executor.py` (add `cancel_dependents` method)

**Blocked By**: WT-2.2.1, WT-1.2.3 (CommittedPlan -- for dependency info)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 440-455 -- cancel_dependents BFS algorithm)

**Specification**:
```python
def cancel_dependents(self, failed_step_id: str, plan: CommittedPlan) -> List[str]:
```

Algorithm:
1. Build reverse dependency map: for each step, which steps depend on it
2. BFS from `failed_step_id` through reverse deps (transitive closure)
3. Mark all reachable steps as CANCELLED
4. Add to `self._cancelled_steps` set
5. Return list of cancelled step_ids

**Invariant (ORCH-07)**: "dependent cancel on parent failure"
- If s2 depends on s1 and s1 fails: s2 is CANCELLED
- If s3 is independent of s1: s3 CONTINUES normally

**Example**:
```python
# Dependencies: s2 -> [s1], s3 -> [s1], s4 -> [s2], s5 -> []
# s1 fails
# Result: [s2, s3, s4] cancelled, s5 still runs
```

**Done When**:
- [ ] BFS traversal through reverse dependency graph
- [ ] Transitive closure computed (s1 fails -> s2 cancelled -> s4 also cancelled)
- [ ] Independent steps NOT cancelled
- [ ] Results stored in `self._cancelled_steps` set
- [ ] Future waves filter steps against cancelled set

---

### WT-2.2.5: Implement Saga Recovery — LIFO Compensation

**Deliverable**: `k1/orchestrator/orchestration/dag_executor.py` (add saga compensation methods)

**Blocked By**: WT-2.2.2, WT-1.2.13 (CompensationRecord), WT-1.4.2 (IFabricGatewayPort for compensation execution), WT-1.1.8 (ADR for LIFO ordering)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 455-475 -- saga compensation spec)
- ADR-1.1.8 (Saga Compensation LIFO ordering)

**Specification**:
When a step with `has_side_effects=True` fails after earlier side-effect steps completed:

1. Collect all COMPLETED steps with `has_side_effects=True`
2. Sort in **REVERSE DECLARATION ORDER** -- by position in CommittedPlan.steps list (INV-2: s3 before s2 before s1, regardless of actual completion timing)
3. Sequential execution, NOT concurrent (per ADR-1.1.8)
4. For each step, lookup compensation capability:
   a. `step.compensation` field (Planner pre-resolved from capability contract)
   b. If None: `fabric_port.query_registry(step.capability).compensation_capability` (runtime lookup)
   c. If still None: no compensation -- log + dead-letter
5. Execute compensation: `await fabric_port.execute(compensation_request)`
6. Create `CompensationRecord` per compensation
7. If compensation fails: dead-letter + telemetry alert + record status=DEAD_LETTERED

**Anti-Hallucination Rules**:
- REVERSE DECLARATION ORDER -- not reverse completion order
- Sequential, not concurrent (ADR-1.1.8)
- Orchestrator follows the compensation contract -- no special-casing for meta-agents

**Done When**:
- [ ] Compensation steps collected (has_side_effects=True + COMPLETED)
- [ ] Sorted in reverse declaration order
- [ ] Executed sequentially
- [ ] 3-level compensation lookup chain (step field -> registry -> dead-letter)
- [ ] CompensationRecord created per compensation
- [ ] Failed compensation -> DEAD_LETTERED status

---

### WT-2.2.6: Implement WAL Interaction Protocol

**Deliverable**: `k1/orchestrator/orchestration/dag_executor.py` (consolidated WAL write points)

**Blocked By**: WT-2.2.2, WT-1.4.6 (IBridgeWritePort)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 475-500 -- WAL protocol)

**Specification**:
4 write points via `bridge_port.write_wal()` (all async, fire-and-forget):

| Write Point | When | entry_type | Payload |
|-------------|------|-----------|---------|
| 1 | Before wave 0 | `"PLAN_START"` | `{"plan": plan.to_dict()}` |
| 2 | After each step | `"STEP_COMPLETE"` | `{"step_id": step.id, "status": result.status.value, "result_summary": ...}` |
| 3 | After each wave | `"WAVE_COMPLETE"` | `{"wave_index": wave.wave_index, "completed_steps": [...]}` |
| 4 | DAG finish | `"DAG_COMPLETE"` | `{"status": "COMPLETED"}` + `bridge_port.submit_audit(run_manifest, trace_id)` |

**Recovery protocol** (used by M6 crash_recovery):
- Read WAL: `entries = await bridge_port.read_wal(dag_id)`
- Find last WAVE_COMPLETE -> resume from `wave_index + 1`
- If STEP_COMPLETE exists after last WAVE_COMPLETE -> re-execute entire wave (idempotent)
- If no entries -> DAG never started, re-execute from scratch

**V1 limitation**: WAL writes are fire-and-forget to K0. If K0 offline, entries lost. Acceptable for Edge-First.

**Done When**:
- [ ] All 4 WAL write points implemented in execute/execute_wave/_execute_step
- [ ] Correct entry_type strings at each point
- [ ] submit_audit() called at DAG_COMPLETE
- [ ] WAL writes wrapped in try/except (fire-and-forget, never fail the DAG)
- [ ] Recovery protocol documented in code comments

---

## Epic 2.3: StepRunner + ParamResolver

> **Files**: `k1/orchestrator/orchestration/step_runner.py` + `k1/orchestrator/orchestration/param_resolver.py`
> **StepRunner constructor**: 3 dependencies (fabric_port, error_router, policies)
> **ParamResolver**: No constructor deps -- pure function class

---

### WT-2.3.1: Implement StepRunner Class + run() Method

**Deliverable**: `k1/orchestrator/orchestration/step_runner.py`

**Blocked By**: WT-1.4.2 (IFabricGatewayPort), WT-2.1.7 (ErrorRouter), WT-1.3.3 (policies.contract.yaml for OrchestratorPolicies)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 520-550 -- StepRunner spec)
- [types.py stub from M1](k1/orchestrator/types.py) (PlanStep, StepResult, StepStatus)
- [k1/fabric/types.py](k1/fabric/types.py) (CapabilityRequest, CapabilityResult)

**Specification**:
```python
class StepRunner:
    def __init__(
        self,
        fabric_port: IFabricGatewayPort,
        error_router: ErrorRouter,
        policies: OrchestratorPolicies,
    ): ...
```

Primary method:
```python
async def run(
    self,
    step: PlanStep,
    resolved_params: Dict[str, Any],
    prior_results: Dict[str, CapabilityResult],
    trace_id: str,
) -> StepResult:
```

Logic:
1. Build `CapabilityRequest`:
   - capability_name = step.capability
   - params = resolved_params
   - prompt_template = step.prompt_template
   - tier = "HIGH"
   - caller = "orchestrator"
   - caller_id = step.id
   - trace_id = trace_id
   - timeout_ms = step.timeout_ms or policies.step_timeout_default_ms
   - If step.tools_granted: set in request
2. `result, attempts, schema_retried, quality_retried = await self._execute_with_retry(request, step)`
3. Wrap: `StepResult(step_id=step.id, capability_name=step.capability, status=COMPLETED if result.success else FAILED, result=result, duration_ms=..., retry_attempts=attempts, schema_retry=schema_retried, quality_retry=quality_retried, cost_usd=getattr(result, 'cost_usd', 0.0) or 0.0, tokens_consumed=getattr(result, 'tokens_consumed', 0) or 0, error_detail=result.error.message if result.error else None)`

**Anti-Hallucination Rules**:
- StepRunner calls `fabric_port.execute()` (single step), NEVER `execute_batch()`
- step.capability is already resolved by ParamResolver before run() is called
- Treat None cost_usd as 0.0

**Done When**:
- [ ] StepRunner class with 3-dep constructor
- [ ] `run()` builds CapabilityRequest from PlanStep
- [ ] Delegates to _execute_with_retry()
- [ ] Wraps result in StepResult with all fields populated
- [ ] Handles None cost_usd / tokens_consumed gracefully

---

### WT-2.3.2: Implement _execute_with_retry() — Retry State Machine

**Deliverable**: `k1/orchestrator/orchestration/step_runner.py` (add retry method)

**Blocked By**: WT-2.3.1

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 550-575 -- retry state machine)
- [policies.contract.yaml](k1/contracts/modules/orchestrator/policies.contract.yaml) (retry limits)

**Specification**:
```python
async def _execute_with_retry(
    self,
    request: CapabilityRequest,
    step: PlanStep,
) -> Tuple[CapabilityResult, int, bool, bool]:
    # Returns: (result, retry_count, schema_retried, quality_retried)
```

State machine:
- `normal_attempts = 0`, `schema_retried = False`, `quality_retried = False`

Loop:
1. `result = await self.fabric_port.execute(request)`
2. If `result.success`:
   - Check output schema (WT-2.3.3) if step.output_schema is not None
   - Check quality (WT-2.3.4)
   - If both pass: return
3. If not `result.success` AND error is retriable AND `normal_attempts < 2`:
   - `normal_attempts += 1`, retry same request
4. If result.success but schema_invalid AND `not schema_retried`:
   - `schema_retried = True`, retry with schema_hint
5. If result.success but quality_low AND `not quality_retried`:
   - `quality_retried = True`, retry with quality_hint
6. Else: return result as-is

**Key rules**:
- Retry delay: 0ms (immediate per ORCH-06, Fabric handles backoff)
- Max calls per step: 2 normal + 1 schema + 1 quality = 4
- ALL attempts count toward token budget (INV-1)
- AdapterError(TERMINAL) is NOT retriable

**Done When**:
- [ ] State machine with normal_attempts, schema_retried, quality_retried flags
- [ ] Max 4 calls per step (2 normal + 1 schema + 1 quality)
- [ ] Immediate retry (no delay)
- [ ] Non-retriable errors exit loop immediately
- [ ] Returns tuple of (result, count, schema_flag, quality_flag)

---

### WT-2.3.3: Implement _build_schema_retry_request() — Schema Hint Retry

**Deliverable**: `k1/orchestrator/orchestration/step_runner.py` (add schema retry methods)

**Blocked By**: WT-2.3.2, WT-1.2.20 (SchemaResult type)

**Specification**:

```python
def validate_output_schema(
    self, result: CapabilityResult, schema: Dict[str, Any]
) -> SchemaResult:
```
Validates `result.data` against `step.output_schema` (JSON Schema Draft 2020-12). Returns `SchemaResult(valid=True/False, errors=[], suggestion="")`.

```python
def _build_schema_retry_request(
    self,
    original_request: CapabilityRequest,
    step: PlanStep,
    schema_result: SchemaResult,
) -> CapabilityRequest:
```
Creates new request with `params["__schema_hint"] = schema_result.suggestion`.

**Anti-Hallucination Rules**:
- Only triggers if `step.output_schema is not None`
- Max 1 schema retry per step
- `__schema_hint` is a reserved param key -- Fabric ContextBuilder extracts it
- Schema retry tokens count toward INV-1 budget

**Done When**:
- [ ] `validate_output_schema()` validates against JSON Schema
- [ ] `_build_schema_retry_request()` creates new request with __schema_hint
- [ ] Only fires when output_schema is set
- [ ] Returns SchemaResult with human-readable suggestion

---

### WT-2.3.4: Implement _build_quality_retry_request() — Quality Hint Retry

**Deliverable**: `k1/orchestrator/orchestration/step_runner.py` (add quality retry methods)

**Blocked By**: WT-2.3.2, WT-1.2.20 (QualityDecision type)

**Specification**:

```python
def assess_quality(self, result: CapabilityResult) -> QualityDecision:
```
Reads `result.data.quality_score` (float 0.0-1.0). Thresholds from policies:
- `< 0.3` -> `SOFT_FAIL` (no retry, step fails gracefully)
- `0.3 - 0.7` -> `RETRY`
- `> 0.7` -> `PASS`
- `None` (no quality_score) -> `PASS`

```python
def _build_quality_retry_request(
    self,
    original_request: CapabilityRequest,
    result: CapabilityResult,
) -> CapabilityRequest:
```
Creates new request with `params["__quality_hint"] = "Previous response scored {score:.2f}. Please provide a more detailed/accurate response."`.

**Anti-Hallucination Rules**:
- Only applies to agent-type capabilities (tool results don't have quality_score)
- Max 1 quality retry per step
- `__quality_hint` is a V1 workaround using reserved param key

**Done When**:
- [ ] `assess_quality()` checks quality_score against thresholds
- [ ] Returns PASS/RETRY/SOFT_FAIL
- [ ] `_build_quality_retry_request()` adds __quality_hint
- [ ] None quality_score -> PASS (assume acceptable)

---

### WT-2.3.5: Implement ParamResolver — Reference Resolution

**Deliverable**: `k1/orchestrator/orchestration/param_resolver.py`

**Blocked By**: WT-1.2.18 (PlanStep), WT-1.2.20 (ResolutionResult)

**Context Files**:
- [orchestrator-implementation-plan.md](docs/plans/orchestrator-implementation-plan.md) (lines 575-600 -- ParamResolver spec)

**Specification**:
```python
class ParamResolver:
    def resolve(
        self,
        step: PlanStep,
        prior_results: Dict[str, CapabilityResult],
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        # Returns: (resolved_params, resolved_capability_name)
```

Logic:
1. Deep-copy `step.params`
2. Walk all string values recursively (nested dicts, lists of strings)
3. For each value matching `$<step_id>.result.<dotted.path>`:
   a. Check step_id in prior_results. If not -> raise `ResolutionError`
   b. Navigate path through `result.data` dict (dot-separated)
   c. Replace reference with resolved value
4. If `step.capability` starts with `$`: resolve same way, return as resolved_capability_name
5. Non-string values pass through unchanged

**Path syntax**: `$<step_id>.result.<dotted.path>`
- "result" is literal keyword
- Dots navigate the data dict
- V1: NO array indexing (`items[0]` not supported)

**Validation**:
- Referenced step FAILED/CANCELLED -> raise ResolutionError
- Path doesn't exist in result.data -> raise ResolutionError

**Example**:
```python
# Prior results: {"s1": CapabilityResult(data={"summary": "Meeting notes"})}
# Step params: {"input": "$s1.result.summary"}
# Resolved: {"input": "Meeting notes"}
```

**Anti-Hallucination Rules**:
- ParamResolver is a PURE FUNCTION -- no async, no I/O, no port calls
- Only resolves STRING values -- ints, lists, dicts pass through
- Nested dicts must be walked recursively

**Done When**:
- [ ] `ParamResolver` class with `resolve()` method
- [ ] Deep-copy of params before mutation
- [ ] Recursive walk of all string values
- [ ] Reference syntax: `$<step_id>.result.<path>`
- [ ] Dynamic capability resolution ($ prefix)
- [ ] ResolutionError for missing step, failed step, missing path
- [ ] Non-string values pass through unchanged
- [ ] No I/O, no async

---

### WT-2.3.6: Implement CostAccumulator Integration in StepRunner

**Deliverable**: `k1/orchestrator/orchestration/step_runner.py` + `k1/orchestrator/orchestration/dag_executor.py` (integration points)

**Blocked By**: WT-2.3.1, WT-2.2.2, WT-1.2.16 (CostAccumulator type)

**Specification**:
This is an integration ticket connecting StepRunner output to DAGExecutor's CostAccumulator:

**In StepRunner.run()** (already partially done in WT-2.3.1):
- After each execute() call (including retries): extract cost = `getattr(result, 'cost_usd', None) or 0.0`
- Report total cost in `StepResult.cost_usd`

**In DAGExecutor._execute_step()** (integration point):
- After StepRunner returns: `self.cost_accumulator.add(step.id, step_result.cost_usd)`

**In DAGExecutor.execute_wave()** (post-wave check):
- `if self.cost_accumulator.is_warning()`: emit DAG_BUDGET_WARNING event
- `if self.cost_accumulator.is_exceeded()`: skip optional steps (`step.is_optional=True`) in remaining waves, emit DAG_BUDGET_EXHAUSTED

**Key rules**:
- `cost_usd` may not be present on all CapabilityResults -- treat missing as 0.0
- `cost_budget_max_usd` from CommittedPlan may be None -- CostAccumulator disabled if no budget
- Non-billable capabilities (internal tools) report None cost -> 0.0

**Done When**:
- [ ] StepRunner reports cost_usd in StepResult
- [ ] DAGExecutor calls cost_accumulator.add() after each step
- [ ] DAG_BUDGET_WARNING emitted at 80% threshold
- [ ] DAG_BUDGET_EXHAUSTED emitted at 100%
- [ ] Optional steps skipped when budget exceeded
- [ ] None cost treated as 0.0

---

## Dependency Summary

### Epic Build Order (within M2)

```
WT-2.1.7 (ErrorRouter)        -- standalone, only needs M1 types
    |
    v
WT-2.3.1 (StepRunner)         -- needs ErrorRouter + M1 ports
WT-2.3.5 (ParamResolver)      -- standalone pure function
    |
    v
WT-2.3.2 (retry policy)       -- needs StepRunner
WT-2.3.3 (schema retry)       -- needs retry policy
WT-2.3.4 (quality retry)      -- needs retry policy
WT-2.3.6 (cost integration)   -- needs StepRunner + DAGExecutor
    |
    v
WT-2.2.1 (build_waves)        -- needs M1 types only
WT-2.2.4 (cancel_dependents)  -- needs M1 types only
    |
    v
WT-2.2.2 (execute/wave)       -- needs StepRunner + ParamResolver + build_waves
WT-2.2.3 (collect_results)    -- needs execute
WT-2.2.5 (saga)               -- needs execute
WT-2.2.6 (WAL protocol)       -- integrated into execute
    |
    v
WT-2.1.1 (OrchestratorService)-- needs DAGExecutor + ErrorRouter
WT-2.1.2 (route_task)         -- needs OrchestratorService
WT-2.1.3 (dispatch_medium)    -- needs route_task
WT-2.1.4 (dispatch_high)      -- needs route_task + DAGExecutor
WT-2.1.5 (aggregate)          -- needs StepResult types
WT-2.1.6 (save_workflow)      -- stub, M4 dependency
```

### Cross-Milestone Dependencies

| M2 Ticket | Depends on M3+ | Notes |
|-----------|----------------|-------|
| WT-2.1.1 | constraint_resolver (M3), workflow_engine (M4), connector_manager (M5) | Forward refs, None/stub until milestones complete |
| WT-2.2.2 | Guards list (M3) | Empty list in M2, populated by OrchestratorFactory in M3 |
| WT-2.1.6 | WorkflowEngine (M4) | Stub method with TODO in M2 |
