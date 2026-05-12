# K1 Orchestrator — CONTRACT

The orchestrator is the **task execution engine** for MEDIUM and HIGH complexity
requests. It owns the DAG wave-executor, the planner round-trip, constraint
resolution, workflow scheduling, and MCP connector lifecycle. It is the only K1
component that calls Fabric capabilities.

---

## 1. What the orchestrator promises callers

### 1.1 Task execution guarantees

| Guarantee | Detail |
|---|---|
| **At-most-once execution per step** | Each `PlanStep` is dispatched exactly once. Retries are isolated: a retry re-calls the same capability with the same or augmented params. |
| **DAG ordering** | Steps within a wave execute concurrently. Steps in a later wave never start until all steps in the preceding wave have resolved (COMPLETED, FAILED, CANCELLED, or SKIPPED). |
| **Dependency cancellation** | When a step fails, `cancel_dependents()` BFS-cancels all transitively dependent steps. Independent steps in the same or later waves continue. |
| **ORCH-01: SS read-only** | The orchestrator never writes SessionState. All SS access is read-only via `IStateReadPort`. |
| **ORCH-02: One active DAG at a time (V1)** | `ConcurrencyGuard` (asyncio.Lock) enforces a single active DAG. Re-entrant plans are re-queued as DEFERRED until the guard is released. |
| **ORCH-10: MEDIUM tier ≤ 2 capabilities** | `_dispatch_medium()` accepts at most 2 capability names per task. |
| **Crash recovery** | On restart, WAL entries are replayed to reconstruct in-flight DAGs and re-enqueue them for execution. |
| **Result delivery** | For HIGH tier, `handle_task()` returns only after the DAG completes (resolved via `asyncio.Future`). |

### 1.2 What the orchestrator does NOT promise

- No message ordering across different DAG executions (first-in, first-out within the mailbox only).
- No guaranteed delivery to slow-start workflows — WorkflowScheduler trigger is best-effort based on its tick interval.
- No pre-emptive cancellation — interrupt is cooperative (max latency = one step execution).
- No concurrent DAGs in V1 (`max_concurrent_dags=1`).
- No `PAUSE` interrupt type in V1 (deferred to V2).
- `save_workflow()` plan-lookup from WAL is not implemented in V1 (deferred to M4).

---

## 2. External interface

### 2.1 `OrchestratorService` — the single entry point

```python
async def init() -> None
    # 10-step startup: validate ports → crash recovery → MCP discovery →
    # load workflows → start scheduler → subscribe events → start reaper →
    # start mailbox loop → start admin. Idempotent.

async def shutdown() -> None
    # Graceful drain (drain_timeout_ms=30s) + unsubscribe + stop tasks.

async def handle_task(envelope: TaskEnvelope) -> ProcessResult
    # Enqueues to mailbox and awaits completion for HIGH tier.
    # For MEDIUM tier: completes synchronously in _dispatch_medium().
    # Returns ProcessResult: COMPLETED | FAILED | DEGRADED | CANCELLED | DEFERRED

async def handle_interrupt(request: InterruptRequest) -> None
    # Sets interrupt_flag on the active DAGExecutor.
    # Maximum latency = current step execution duration.

def bind_planner(planner_port: IPlannerPort) -> None
    # Late-bind planner port after construction (S6b cross-wire).
```

### 2.2 `IMailboxPort` — internal priority queue (injected, not called by external code)

```python
def enqueue(message: MailboxMessage, priority: str = "INTERACTIVE") -> int
    # priority: "REALTIME" (60% WFQ weight) | "INTERACTIVE" (30%) | "BACKGROUND" (10%)
    # Raises: MailboxFullError (capacity=100), ValueError (unknown priority)

def dequeue() -> Optional[MailboxMessage]
def depth() -> int
def peek_priority() -> Optional[str]
```

`MailboxMessage = Union[TaskEnvelope, CommittedPlan, WorkflowRunRequest, WorkflowSaveRequest, InterruptRequest]`

---

## 3. Port contracts (what the orchestrator requires)

### 3.1 `IFabricGatewayPort` (async)

```python
async def execute(request: CapabilityRequest) -> CapabilityResult
    # Raises: AdapterError(DEGRADED) — triggers circuit breaker, step FAILED

async def execute_batch(requests: List[CapabilityRequest]) -> List[CapabilityResult]
    # MEDIUM tier path. max len = 2 (ORCH-10).

async def query_registry(capability_name: str) -> Optional[RegistryEntry]
    # Returns None if capability not found — ConstraintResolver treats as missing.

async def query_registry_by_category(category_prefix: str) -> List[RegistryEntry]
    # Used by ConstraintResolver.find_alternatives() prefix scan.
```

### 3.2 `IPlannerPort` (async)

```python
async def request_plan(request: PlanRequest) -> PlanAck
    # Fire-and-forget; CommittedPlan arrives async via bus (k1.planner.plan.ready.v1).
    # PlanAck.status: "ACCEPTED" (store context) | "REJECTED" (fail immediately).
    # Timeout: plan_request_timeout_ms=45s (reaper cancels stale contexts).
    # Raises: AdapterError(DEGRADED) → degrade HIGH→MEDIUM, cb_planner trips.

async def cancel_plan(request_id: str) -> None
    # Best-effort; no acknowledgement expected.

async def micro_replan(request: MicroReplanRequest) -> Optional[CommittedPlan]
    # SYNCHRONOUS with asyncio.wait_for timeout=10s.
    # Returns None on timeout or failure → caller continues original plan.
    # Raises: AdapterError(DEGRADED) → same as None return.
```

### 3.3 `IStateReadPort` (async, read-only)

```python
async def read_section(session_id: str, section: str) -> Optional[Dict[str, Any]]
async def read_sections(session_id: str, names: List[str]) -> Dict[str, Any]
async def get_snapshot(session_id: str) -> SessionSnapshot
```

Sections read by orchestrator: `"beliefs"`, `"persona"`, `"control"`, `"scoreboard"`.

On adapter failure: `ErrorRouter` classifies as DEGRADED → orchestrator uses empty/stale snapshot and continues.

### 3.4 `IDeltaEmitPort` (async, fire-and-forget)

```python
async def emit(event_topic: str, payload: Dict[str, Any], trace_id: str) -> None
async def emit_progress(step_id: str, summary: str, trace_id: str) -> None
```

Failures are classified as RECOVERABLE → retried once. Second failure: silently dropped (emit is best-effort).

### 3.5 `IBridgeWritePort` (async)

```python
async def submit_audit(run_manifest: Dict[str, Any], trace_id: str) -> None
    # Fire-and-forget; failures classified as RECOVERABLE.

async def write_wal(dag_id: str, entry_type: str, payload: Dict[str, Any], trace_id: str) -> None
    # entry_type: "PLAN_START" | "STEP_COMPLETE" | "WAVE_COMPLETE" | "DAG_COMPLETE"
    # Failures: RECOVERABLE; WAL gaps are tolerated (crash recovery skips missing entries).

async def read_wal(dag_id: str) -> Optional[List[Dict[str, Any]]]
    # Raises: AdapterError(DEGRADED) if K0 unreachable — crash recovery aborts for that dag_id.

async def list_wal_ids() -> List[str]
    # Raises: AdapterError(DEGRADED) — crash_recovery() skips WAL scan on failure.
```

### 3.6 `IEventSubscriptionPort` (sync)

```python
def subscribe(topic: str, handler: Callable[[str, Dict[str, Any]], None]) -> SubscriptionHandle
def unsubscribe(handle: SubscriptionHandle) -> bool
def emit(topic: str, payload: Dict[str, Any]) -> None
```

Used to subscribe to planner and fabric events (see §5 for all topics).

### 3.7 `IWorkflowStoragePort` (async)

```python
async def save(spec: WorkflowSpec) -> None
async def load(workflow_id: str) -> Optional[WorkflowSpec]
async def list_active() -> List[WorkflowSpec]
async def delete(workflow_id: str) -> bool
```

Backed by SQLite WAL. Path: `config.workflow_db_path = "data/orchestrator_workflows.db"`.

### 3.8 `IAdminPort` (async)

```python
async def start(port: int) -> None
async def stop() -> None
async def health() -> HealthStatus
async def drain() -> DrainResult
```

HTTP server on `config.admin_port=8081` (when `config.admin_enabled=True`).

---

## 4. Key envelope types

### `TaskEnvelope`

```python
@dataclass(frozen=True)
class TaskEnvelope:
    intent: str
    trace_id: str
    caller_id: str = ""
    envelope_id: str          # auto uuid4
    context: Dict[str, Any]
    tier: str                 # "MEDIUM" | "HIGH"
    capabilities: List[str]   # MEDIUM: 1–2; HIGH: may be empty (Planner decides)
    params: Dict[str, Dict[str, Any]]  # keyed by capability_name
    constraints: Dict[str, Any]
    timeout_ms: int = 30_000
```

### `CommittedPlan`

```python
@dataclass(frozen=True)
class CommittedPlan:
    plan_id: str
    request_id: str
    trace_id: str
    tier: str
    steps: List[PlanStep]
    dependencies: Dict[str, List[str]]  # step_id → [dep_ids]
    session_id: str = ""
    created_at: float
    metadata: Dict[str, Any] = {}
```

### `PlanStep` (ORCH-010 — 14-field extension of Fabric's 6-field base)

```python
@dataclass(frozen=True)
class PlanStep:
    id: str
    capability: str
    params: Dict[str, Any]
    tier: Tier
    deps: List[str] = []
    timeout_ms: Optional[int] = None
    tools_granted: List[str] = []
    condition: Optional[ConditionExpr] = None
    output_schema: Optional[Dict[str, Any]] = None
    safety_band_min: str = "GREEN"
    # ... 4 additional fields
```

### `ProcessResult`

```python
class ProcessResult(str, Enum):
    COMPLETED  # All required steps succeeded
    FAILED     # Required steps failed (no degraded partial success)
    DEGRADED   # Some steps failed; independent branches succeeded
    CANCELLED  # Interrupt received; compensation run
    DEFERRED   # HIGH tier Phase 1 complete; waiting for CommittedPlan
```

---

## 5. Bus topics

### Published (emitted)

| Topic | When |
|---|---|
| `k1.orchestration.task.accepted.v1` | TaskEnvelope dequeued |
| `k1.orchestration.plan.requested.v1` | PlanRequest sent to planner |
| `k1.orchestration.dag.started.v1` | DAGExecutor.execute() begins |
| `k1.orchestration.dag.micro_replan.v1` | Micro-replan triggered |
| `k1.orchestration.dag.node_failed.v1` | Step fails in wave |
| `k1.orchestration.dag.completed.v1` | DAG finishes (success or failure) |
| `k1.orchestration.step.started.v1` | Step begins execution |
| `k1.orchestration.step.completed.v1` | Step succeeds |
| `k1.orchestration.step.failed.v1` | Step fails after retries |
| `k1.orchestration.step.cancelled.v1` | Step dependency-cancelled |
| `k1.orchestration.step.skipped.v1` | Step skipped by condition guard |
| `k1.orchestration.step.retrying.v1` | Normal retry attempt |
| `k1.orchestration.step.schema_retry.v1` | Schema-hint retry attempt |
| `k1.orchestration.saga.compensating.v1` | Compensation step started |
| `k1.orchestration.delta.v1` | Final delta after DAG completes |
| `k1.orchestration.workflow.triggered.v1` | WorkflowScheduler fires |
| `k1.orchestration.workflow.completed.v1` | Workflow run finishes |
| `k1.orchestration.workflow.saved.v1` | WorkflowSpec persisted |
| `k1.orchestration.error.routed.v1` | ErrorRouter classification |
| `k1.orchestration.mcp.tool_registered.v1` | MCP tool registered in Fabric |

### Subscribed (consumed)

| Topic | Handler |
|---|---|
| `k1.planner.plan.ready.v1` | `_on_plan_ready()` → enqueue CommittedPlan |
| `k1.planner.plan.failed.v1` | `_on_plan_failed()` → resolve pending future FAILED |
| `k1.planner.plan.cancelled.v1` | `_on_plan_cancelled()` |
| `k1.planner.micro_replan.ready.v1` | Telemetry only (not plan delivery) |
| `k1.capability.completed.v1` | StepRunner event-driven result |
| `k1.capability.failed.v1` | StepRunner error result |
| `k1.fabric.contract.updated.v1` | ProactiveGapDetector |
| `k1.fabric.agent.tool_call.v1` | SubStepObserver (rate-limited) |
| `k1.fabric.agent.llm_call.v1` | SubStepObserver (rate-limited) |
| `k1.orchestration.workflow.trigger_due.v1` | WorkflowScheduler self-trigger |
| `k1.fabric.provider.health.changed.v1` | MCP re-discovery |

---

## 6. Error surface

| Error class | Raised by | Meaning |
|---|---|---|
| `MailboxFullError` | `IMailboxPort.enqueue()` | Mailbox at capacity (100 items) — caller must handle |
| `AdapterError` | Any port | Adapter-specific error; `.severity` classifies recovery |
| `CycleError` | `DAGExecutor.build_waves()` | Dependencies form a cycle — plan is rejected |
| `WaveLimitExceeded` | `DAGExecutor.build_waves()` | Plan exceeds `max_waves_per_plan=20` |
| `StepLimitExceeded` | `DAGExecutor.build_waves()` | Plan exceeds `max_steps_per_plan=50` |

---

## 7. Caller invariants

1. Call `init()` before `handle_task()`. The service will reject tasks if `initialized=False`.
2. Call `shutdown()` to drain before process exit — ensures WAL writes and audit submissions complete.
3. `handle_task()` for HIGH tier blocks until DAG completion. Callers must be prepared for latency up to `plan_request_timeout_ms (45s) + all step timeouts`.
4. `bind_planner()` must be called before any HIGH-tier task arrives, or HIGH-tier tasks will fail immediately with DEGRADED (no planner port).
5. `InterruptRequest.trace_id` must be populated — used for WAL and telemetry correlation.
6. Do not modify `CommittedPlan.steps` or `CommittedPlan.dependencies` after construction — they are frozen.
