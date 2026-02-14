# Orchestrator Integration Guide

> **Deliverable**: 9.3.1 — How Concierge, Planner, and Fabric connect to Orchestrator.
>
> **Source of truth**: Written from implemented code. All class names, port Protocols,
> event constants, and factory wiring steps match the actual codebase at time of writing.
> Do NOT edit this document without verifying against the code.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Message Flow Diagrams](#2-message-flow-diagrams)
3. [Port Usage Reference](#3-port-usage-reference)
4. [Envelope Schemas](#4-envelope-schemas)
5. [Event Wiring](#5-event-wiring)
6. [Error Handling](#6-error-handling)
7. [Tier Degradation](#7-tier-degradation)

---

## 1. Architecture Overview

### 1.1 Hexagonal 8-Port Design (ORCH-002)

The Orchestrator follows a strict hexagonal (ports-and-adapters) architecture.
All external dependencies are abstracted behind Protocol interfaces defined in
`k1/orchestrator/ports/`. The service core (`OrchestratorService`) depends only
on these Protocols, never on concrete adapters.

```
                    +--------------------+
                    |   Concierge        |
                    +--------+-----------+
                             |
                             | TaskEnvelope / InterruptRequest
                             v
                    +--------+-----------+
                    |  IMailboxPort       |  (1)
                    +--------+-----------+
                             |
          +------------------+------------------+
          |                                     |
          v                                     v
+---------+---------+             +-------------+-------------+
| IFabricGatewayPort| (2)        |    IPlannerPort            | (3)
| execute()         |            |    request_plan()          |
| execute_batch()   |            |    cancel_plan()           |
| query_registry()  |            |    micro_replan()          |
+---------+---------+            +-------------+--------------+
          |                                     |
          |          +---------------------------+
          |          |
          v          v
+---------+----------+---------+
|    OrchestratorService       |
|    (Central Dispatch)        |
|                              |
|  - process() routes by type  |
|  - _dispatch_medium()        |
|  - _dispatch_high()          |
|  - _receive_plan()           |
|  - _dispatch_workflow()      |
|  - crash_recovery()          |
+---------+----+----+----------+
          |    |    |
     +----+   |    +----+
     |         |         |
     v         v         v
+----+---+ +---+----+ +-+--------+------+
|IState  | |IDelta  | |IBridge   |IEvent|
|ReadPort| |EmitPort| |WritePort |SubPrt| (4-7)
+--------+ +--------+ +---------+------+

                    +--------------------+
                    | IWorkflowStorage   |  (8)
                    | Port               |
                    +--------------------+
```

**8 ports** (each with production + test adapter):

| # | Port Protocol | File | Purpose |
|---|--------------|------|---------|
| 1 | `IMailboxPort` | `ports/mailbox_port.py` | In-process priority mailbox (WFQ). Single entry point for all messages. |
| 2 | `IFabricGatewayPort` | `ports/fabric_gateway_port.py` | Async gateway to Capability Fabric for step execution + registry queries. |
| 3 | `IPlannerPort` | `ports/planner_port.py` | Async interface to Planner for plan creation + micro-replan. |
| 4 | `IStateReadPort` | `ports/state_read_port.py` | Read-only async access to SessionState. **ORCH-01: NO write methods.** |
| 5 | `IDeltaEmitPort` | `ports/delta_emit_port.py` | Fire-and-forget event emission + progress deltas to DeltaBus. |
| 6 | `IBridgeWritePort` | `ports/bridge_write_port.py` | Fire-and-forget K0 Bridge writes (audit, WAL, deferred results). |
| 7 | `IEventSubscriptionPort` | `ports/event_subscription_port.py` | Sync event bus port for subscribing + emitting events. |
| 8 | `IWorkflowStoragePort` | `ports/workflow_storage_port.py` | Async workflow persistence (specs, triggers, runs, gaps). |

### 1.2 Actor Model (ORCH-001)

The Orchestrator is a **single-mailbox actor**:

- **One inbound channel**: All messages (tasks, plans, workflow requests, interrupts) enter
  through `IMailboxPort.enqueue()`.
- **One processing loop**: `OrchestratorService._mailbox_loop()` dequeues messages and calls
  `process()` sequentially.
- **Weighted Fair Queuing (WFQ)**: Three priority classes with dequeue weights:
  - `REALTIME` (60%) — interrupts, safety band changes
  - `INTERACTIVE` (30%) — user tasks, plan results
  - `BACKGROUND` (10%) — workflow triggers, gap scans
- **Max depth**: 100 messages. `MailboxFullError` raised when full (Concierge CB catches this).

### 1.3 Single-DAG Concurrency (ConcurrencyGuard)

**V1 invariant**: Only one DAG executes at a time.

- `ConcurrencyGuard` wraps an `asyncio.Lock`.
- `_receive_plan()` and `_dispatch_workflow()` call `acquire()` before DAG execution.
- If a DAG is already active, new plans return `ProcessResult.DEFERRED`.
- The guard is released in a `finally` block to prevent deadlocks.

### 1.4 Factory Construction (15-Step Wiring)

`OrchestratorFactory` in `k1/orchestrator/factory.py` is the composition root.
Static methods only — no constructor, no singletons, no service locator.

| Step | Component | Dependencies |
|------|-----------|-------------|
| 1  | `ErrorRouter` | `IDeltaEmitPort` |
| 2  | `ConcurrencyGuard` | (none — internal `asyncio.Lock`) |
| 11 | `StepRunner` | `IFabricGatewayPort`, `ErrorRouter`, `OrchestratorPolicies`, `Metrics` |
| 12 | Guards (4 total) | `IPlannerPort`, `IDeltaEmitPort` |
| 13 | `DAGExecutor` | 5 ports + `StepRunner` + `ErrorRouter` + guards + `ParamResolver` + `Metrics` |
| 14a | `ConstraintResolver` | `IFabricGatewayPort`, `IDeltaEmitPort`, `IEventSubscriptionPort` |
| 14b | Workflow subsystem | `SystemClock`, `WorkflowRegistry`, `WorkflowCompiler`, `WorkflowScheduler`, `CrossWorkflowResolver`, `WorkflowRunSupervisor`, `ProactiveGapDetector`, `WorkflowEngine` |
| 15 | Connector subsystem | `MCPToolDiscovery`, `MCPRegistrationBridge`, `ConnectorLifecycleManager` |
| FINAL | `OrchestratorService` | All ports + all collaborators |
| POST | ExecutionMonitor lazy init | `service` reference injected into `guards[3]._service_ref` |
| 15.5 | AdminHttpAdapter (optional) | `OrchestratorService`, `OrchestratorConfig` |

**Guard order** (for DAGExecutor):

1. `OutputSchemaGuard` — post-step schema validation, triggers schema retry
2. `ConditionalEdgeEvaluator` — pre-wave conditional edge evaluation
3. `MicroReplanCheckpoint` — post-wave micro-replan check (max 1 per DAG)
4. `ExecutionMonitor` — post-wave anomaly detection, HIL override

**Factory methods**:

| Method | Use Case | Calls `init()`? |
|--------|----------|-----------------|
| `create_standalone()` | Unit tests, all test adapters, zero deps | No |
| `create_for_testing(overrides)` | Integration tests, selective adapter overrides | No |
| `create_with_ports(...)` | Cross-subsystem tests, all ports explicit | No |
| `create_production(config, ...)` | Production deployment, all real adapters | **Yes** |

### 1.5 Startup Sequence (10-Step `init()`)

`OrchestratorService.init()` executes these steps in order:

1. **Validate ports** — assert all 8 ports and collaborators are non-None.
2. **Reserved** — no-op for V1 in-process adapters.
2b. **Crash recovery** — scan WAL via `IBridgeWritePort`, re-enqueue incomplete DAGs.
3. **Assert ConcurrencyGuard** — must not be locked at boot.
4. **MCP discover + register** — `ConnectorLifecycleManager.discover_and_register()` (500ms timeout).
5. (Commentary) — Tools now available for DAG execution.
6. **Load active workflows** — `WorkflowRegistry.list_active()`.
7. **Start scheduler** — `WorkflowScheduler.start()` (tick loop).
8. **Subscribe to events** — 5 subscriptions via `IEventSubscriptionPort`.
9. **Start monitors** — `GapDetector.start()`, `ConnectorLifecycle.start_lifecycle_monitoring()`, timeout reaper task.
10. **Start mailbox loop** — `asyncio.create_task(_mailbox_loop())`.
10.5. **Admin HTTP server** (optional) — `AdminHttpAdapter.start()` if configured.

---

## 2. Message Flow Diagrams

### 2.1 MEDIUM Tier Flow

MEDIUM tier tasks have 1-2 pre-resolved capabilities. No Planner involvement.

```
Concierge                 Orchestrator                    Fabric
    |                         |                              |
    |--- TaskEnvelope ------->|                              |
    |    (tier=MEDIUM,        |                              |
    |     capabilities=[...]) |                              |
    |                         |                              |
    |                     mailbox.enqueue()                   |
    |                     _mailbox_loop()                     |
    |                     process(TaskEnvelope)               |
    |                         |                              |
    |                     _route_task()                       |
    |                       |-- emit TASK_ACCEPTED           |
    |                       |-- _dispatch_medium()           |
    |                         |                              |
    |                     1. Validate ORCH-10 (max 2 caps)   |
    |                     2. Read safety_band (IStateRead)   |
    |                     3. Query registry per capability   |
    |                     4. Build CapabilityRequest[]       |
    |                         |                              |
    |                     5. Per-step execution:             |
    |                         |--- execute(req_1) ---------->|
    |                         |<-- CapabilityResult ---------|
    |                         |--- execute(req_2) ---------->|
    |                         |<-- CapabilityResult ---------|
    |                         |                              |
    |                     6. Aggregate results               |
    |                     7. Emit DAG_COMPLETED + audit      |
    |                         |                              |
    |<-- AggregatedResult ----|                              |
```

**Key behavior**:

- Per-step error isolation: if step 1 fails, step 2 still executes.
- No ConcurrencyGuard needed (no DAG).
- Safety band check: each capability's `safety_band_min` must be <= current safety band.

### 2.2 HIGH Tier Flow (Two-Phase Protocol)

HIGH tier tasks require Planner involvement. The flow is asynchronous:
Phase 1 sends a plan request; Phase 2 executes the returned plan.

```
Concierge          Orchestrator              Planner            Fabric
    |                   |                       |                  |
    |-- TaskEnvelope -->|                       |                  |
    |   (tier=HIGH)     |                       |                  |
    |                   |                       |                  |
    |               _route_task()               |                  |
    |               _dispatch_high()            |                  |
    |                   |                       |                  |
    |               1. get_snapshot(IStateRead) |                  |
    |               2. Build PlanRequest        |                  |
    |               3. request_plan() --------->|                  |
    |                   |<-- PlanAck(ACCEPTED) -|                  |
    |               4. Park PendingPlanContext   |                  |
    |               5. Emit PLAN_REQUESTED      |                  |
    |               6. Return DEFERRED          |                  |
    |                   |                       |                  |
    |                   |    (async, 20-60s)     |                  |
    |                   |                       |                  |
    |                   |<- plan.ready.v1 event-|                  |
    |                   |   (CommittedPlan)      |                  |
    |                   |                       |                  |
    |               Event handler routes to mailbox               |
    |               _receive_plan()             |                  |
    |                   |                       |                  |
    |               1. RACE-3 dedup             |                  |
    |               2. Correlate via request_id |                  |
    |               3. Re-read state (RACE-1)   |                  |
    |               4. ConstraintResolver.validate()               |
    |               5. ConcurrencyGuard.acquire()|                 |
    |               6. DAGExecutor.execute() ----|---------------->|
    |                   |  (waves of steps)      |                 |
    |                   |<-- AggregatedResult ---|-----------------|
    |               7. ConcurrencyGuard.release()|                 |
    |               8. Emit DAG_COMPLETED + audit|                 |
    |                   |                       |                  |
    |<- AggregatedResult|                       |                  |
```

**Key behavior**:

- `request_id` correlation: Orchestrator generates UUID, Planner echoes it in CommittedPlan.
- `PendingPlanContext` stores parked state (envelope, snapshot) keyed by `request_id`.
- RACE-1: state re-read before DAG execution (staleness may be 20-60s).
- RACE-3: `executed_plans` LRU (max 100) prevents duplicate plan execution.
- RACE-2: orphan plan handling if timeout expires before plan arrives.

### 2.3 Workflow Flow

```
Scheduler/User          Orchestrator              Fabric
    |                       |                       |
    |-- WorkflowRunRequest->|                       |
    |                       |                       |
    |                   process(WorkflowRunRequest) |
    |                   _dispatch_workflow()         |
    |                       |                       |
    |                   1. ConcurrencyGuard.acquire()|
    |                   2. WorkflowEngine            |
    |                      .execute_workflow()       |
    |                       |                       |
    |                   3. Supervisor checks         |
    |                      single-active-run         |
    |                   4. Compiler builds            |
    |                      CommittedPlan from spec   |
    |                   5. DAGExecutor.execute() --->|
    |                       |  (waves of steps)     |
    |                       |<- AggregatedResult ---|
    |                   6. Save RunManifest          |
    |                   7. ConcurrencyGuard.release()|
    |                       |                       |
    |<-- ProcessResult -----|                       |
```

**Key behavior**:

- Workflows compete for the same ConcurrencyGuard as HIGH tier DAGs.
- `WorkflowRunSupervisor` enforces single-active-run per workflow (abort previous on re-trigger).
- `WorkflowCompiler` converts `WorkflowSpec` to `CommittedPlan`.
- Cron-triggered workflows with no user session store results via `IBridgeWritePort.submit_deferred_result()`.

### 2.4 Interrupt Flow

```
External Source         Orchestrator
    |                       |
    |-- InterruptRequest -->|  (via mailbox)
    |   (CANCEL_DAG)        |
    |                       |
    |                   process(InterruptRequest)
    |                   _handle_interrupt()
    |                       |
    |                   1. Find active DAG by target_dag_id
    |                   2. Set DAGExecutor.interrupt_flag = True
    |                   3. DAGExecutor checks flag at each step completion
    |                   4. Cooperative cancellation (max latency = 1 step)
    |                   5. Saga compensation for side-effect steps
    |                       |
    |<-- CANCELLED ---------|
```

---

## 3. Port Usage Reference

### 3.1 Port-Caller Mapping

| Port | External Caller | Internal User | Direction |
|------|----------------|---------------|-----------|
| `IMailboxPort` | Concierge (enqueue tasks), Event handlers (route plans/interrupts) | `OrchestratorService._mailbox_loop()` (dequeue) | Inbound |
| `IFabricGatewayPort` | — | `StepRunner.run()`, `_dispatch_medium()`, `ConstraintResolver`, `DAGExecutor` | Outbound |
| `IPlannerPort` | — | `_dispatch_high()` (request_plan), `MicroReplanCheckpoint` (micro_replan) | Outbound |
| `IStateReadPort` | — | `_dispatch_medium()` (safety band), `_dispatch_high()` (snapshot), `_receive_plan()` (RACE-1 re-read), `DAGExecutor` (wave safety band) | Outbound |
| `IDeltaEmitPort` | — | `OrchestratorService` (task/DAG events), `DAGExecutor` (step events), `StepRunner` (retry events), `ErrorRouter` (diagnostic), `ExecutionMonitor` (HIL) | Outbound |
| `IBridgeWritePort` | — | `DAGExecutor` (WAL writes), `_receive_plan()` (audit), `crash_recovery()` (WAL read), `WorkflowScheduler` (deferred results) | Outbound |
| `IEventSubscriptionPort` | Planner (plan.ready events), Fabric (capability events), HIL (override responses) | `OrchestratorFactory` (subscribe at startup), `OrchestratorService.init()` (5 subscriptions) | Bidirectional |
| `IWorkflowStoragePort` | — | `WorkflowRegistry`, `WorkflowScheduler`, `WorkflowCompiler`, `WorkflowRunSupervisor`, `ProactiveGapDetector` | Outbound |

### 3.2 Port Method Reference

#### IMailboxPort (1.4.1) — Sync, In-Process

| Method | Signature | Description |
|--------|-----------|-------------|
| `enqueue()` | `(message: MailboxMessage, priority: str = "INTERACTIVE") -> int` | Enqueue message at priority. Returns queue position. Raises `MailboxFullError` at depth >= 100. |
| `dequeue()` | `() -> Optional[MailboxMessage]` | WFQ dequeue. REALTIME 60%, INTERACTIVE 30%, BACKGROUND 10%. Returns `None` if empty. |
| `depth()` | `() -> int` | Current total queue size across all priorities. |
| `peek_priority()` | `() -> Optional[str]` | Priority class of next message without removing. |

`MailboxMessage` union type:

```python
MailboxMessage = Union[
    TaskEnvelope,
    CommittedPlan,
    WorkflowRunRequest,
    WorkflowSaveRequest,
    InterruptRequest,
]
```

#### IFabricGatewayPort (1.4.2) — Async

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute()` | `async (request: CapabilityRequest) -> CapabilityResult` | Execute single capability. Raises `AdapterError(DEGRADED)` on failure. |
| `execute_batch()` | `async (requests: List[CapabilityRequest]) -> List[CapabilityResult]` | Parallel execution via `asyncio.gather()`. Partial failure model. |
| `query_registry()` | `async (capability_name: str) -> Optional[RegistryEntry]` | Lookup capability metadata. Returns `None` if not found. |
| `query_registry_by_category()` | `async (category_prefix: str) -> List[RegistryEntry]` | Find all capabilities in a category (for `ConstraintResolver.find_alternatives()`). |

#### IPlannerPort (1.4.3) — Async

| Method | Signature | Description |
|--------|-----------|-------------|
| `request_plan()` | `async (request: PlanRequest) -> PlanAck` | Fire-and-forget plan request. CommittedPlan arrives via event bus. |
| `cancel_plan()` | `async (request_id: str) -> None` | Best-effort cancel. No effect if plan already committed. |
| `micro_replan()` | `async (request: MicroReplanRequest) -> Optional[CommittedPlan]` | Synchronous mid-DAG replan (10s timeout, PROTOCOL-3). Max 1 per DAG (ORCH-13). |

#### IStateReadPort (1.4.4) — Async, READ-ONLY

| Method | Signature | Description |
|--------|-----------|-------------|
| `read_section()` | `async (session_id: str, section: str) -> Optional[Dict]` | Single named section (e.g., `"control"`, `"beliefs"`). |
| `read_sections()` | `async (session_id: str, names: List[str]) -> Dict[str, Any]` | Multiple sections in one call. |
| `get_snapshot()` | `async (session_id: str) -> SessionSnapshot` | Point-in-time snapshot of all sections. |

**ORCH-01 invariant**: This port has NO write methods. Orchestrator NEVER writes SessionState.

#### IDeltaEmitPort (1.4.5) — Async, Fire-and-Forget

| Method | Signature | Description |
|--------|-----------|-------------|
| `emit()` | `async (event_topic: str, payload: Dict, trace_id: str) -> None` | Typed event emission. Never raises. |
| `emit_progress()` | `async (step_id: str, summary: str, trace_id: str) -> None` | Human-readable progress delta for Concierge PROGRESSING state. |
| `emit_hil_request()` | `async (hil_request: HILRequest, trace_id: str) -> None` | Surface HIL question to user via Concierge. |

#### IBridgeWritePort (1.4.6) — Async

| Method | Signature | Write/Read | Description |
|--------|-----------|-----------|-------------|
| `submit_audit()` | `async (run_manifest: Dict, trace_id: str) -> None` | Write (F&F) | DAG execution record to K0. |
| `write_wal()` | `async (dag_id: str, entry_type: str, payload: Dict, trace_id: str) -> None` | Write (F&F) | WAL checkpoint. |
| `read_wal()` | `async (dag_id: str) -> Optional[List[Dict]]` | Read | WAL entries for crash recovery. Raises `AdapterError(DEGRADED)`. |
| `list_wal_ids()` | `async () -> List[str]` | Read | All active WAL dag_ids. Raises `AdapterError(DEGRADED)`. |
| `submit_deferred_result()` | `async (result: Dict, workflow_id: str, trace_id: str) -> None` | Write (F&F) | Workflow result when no session active. |

WAL `entry_type` values: `"PLAN_START"`, `"STEP_COMPLETE"`, `"WAVE_COMPLETE"`, `"DAG_COMPLETE"`.

#### IEventSubscriptionPort (1.4.7) — Sync

| Method | Signature | Description |
|--------|-----------|-------------|
| `subscribe()` | `(topic: str, handler: Callable[[str, Dict], None]) -> SubscriptionHandle` | Subscribe handler to topic. Supports wildcards (e.g. `k1.capability.*`). |
| `unsubscribe()` | `(handle: SubscriptionHandle) -> bool` | Remove subscription. Returns True if found. |
| `emit()` | `(topic: str, payload: Dict) -> None` | Publish event to all subscribers. Fire-and-forget. |

**Handler semantics**: Handlers are sync. For async processing, handlers enqueue to the mailbox (sync call), and the mailbox loop performs async work.

#### IWorkflowStoragePort (4.1.6) — Async

| Group | Methods | Description |
|-------|---------|-------------|
| Workflow CRUD | `save_workflow()`, `get_workflow()`, `list_workflows()`, `delete_workflow()`, `purge_workflow()` | Workflow spec persistence (soft/hard delete). |
| Trigger state | `save_trigger()`, `get_due_triggers(now)`, `update_trigger_state()` | Scheduler trigger management. `get_due_triggers()` called every ~1s. |
| Run manifests | `save_run()`, `get_runs(workflow_id, limit)` | Execution history. |
| Proactive gaps | `save_gap()`, `get_pending_gaps()` | Gap detection persistence. |

### 3.3 Port-to-Adapter Mapping

| Port Key | Port Protocol | Production Adapter | Test Adapter | Factory Step |
|----------|--------------|-------------------|-------------|-------------|
| `mailbox` | `IMailboxPort` | `MailboxAdapter` (6.1.1) | `TestMailboxAdapter` (6.1.8) | _build_test_adapters |
| `fabric` | `IFabricGatewayPort` | `FabricGatewayAdapter` (6.1.2) | `MockFabricAdapter` (6.1.9) | _build_test_adapters |
| `planner` | `IPlannerPort` | `PlannerAdapter` (6.1.3) | `MockPlannerAdapter` (6.1.10) | _build_test_adapters |
| `state` | `IStateReadPort` | `StateReadAdapter` (6.1.4) | `MockStateReadAdapter` (6.1.11) | _build_test_adapters |
| `delta` | `IDeltaEmitPort` | `DeltaEmitAdapter` (6.1.5) | `TestDeltaAdapter` (6.1.12) | _build_test_adapters |
| `bridge` | `IBridgeWritePort` | `BridgeWriteAdapter` (6.1.6) | `MockBridgeAdapter` (6.1.13) | _build_test_adapters |
| `event` | `IEventSubscriptionPort` | `EventSubscriptionAdapter` (6.1.7) | `TestEventAdapter` (6.1.14) | _build_test_adapters |
| `storage` | `IWorkflowStoragePort` | `SQLiteWorkflowAdapter` (4.1.5) | `TestWorkflowStorageAdapter` (6.1.16) | _build_test_adapters |

---

## 4. Envelope Schemas

### 4.1 TaskEnvelope

Inbound task from Concierge. Routed by `OrchestratorService.process()`.

```python
@dataclass(frozen=True)
class TaskEnvelope:
    intent: str                              # User intent (required, non-empty)
    trace_id: str                            # Cognitive trace ID (required)
    caller_id: str = ""                      # Concierge caller identifier
    envelope_id: str = uuid4()               # Unique envelope ID
    context: Dict[str, Any] = {}             # Session context (includes session_id)
    tier: str = "MEDIUM"                     # "MEDIUM" or "HIGH" only
    capabilities: List[str] = []             # Pre-resolved capabilities (MEDIUM)
    params: Dict[str, Dict[str, Any]] = {}   # Per-capability params, keyed by cap name
    constraints: Dict[str, Any] = {}         # Planning constraints (HIGH)
    timeout_ms: int = 30_000                 # Request timeout
```

**Validation rules**:

- `tier` must be `"MEDIUM"` or `"HIGH"` (LOW/CRISIS never reach Orchestrator).
- `intent` must be non-empty.
- `trace_id` must be non-empty.
- MEDIUM tier: `capabilities` must be non-empty and `len(capabilities) <= 2` (ORCH-10).
- HIGH tier: `capabilities` may be empty (Planner decides).

**Example (MEDIUM)**:

```json
{
  "intent": "Search calendar for tomorrow's meetings",
  "trace_id": "ct-abc123",
  "caller_id": "concierge-main",
  "envelope_id": "env-7890",
  "context": {"session_id": "sess-001"},
  "tier": "MEDIUM",
  "capabilities": ["tool.calendar.search"],
  "params": {
    "tool.calendar.search": {"query": "tomorrow's meetings", "limit": 10}
  },
  "timeout_ms": 30000
}
```

**Example (HIGH)**:

```json
{
  "intent": "Plan a family dinner for Saturday including restaurant search and invitation",
  "trace_id": "ct-def456",
  "caller_id": "concierge-main",
  "envelope_id": "env-1234",
  "context": {"session_id": "sess-001"},
  "tier": "HIGH",
  "capabilities": [],
  "constraints": {"budget_usd": 100, "location": "downtown"},
  "timeout_ms": 45000
}
```

### 4.2 CommittedPlan

Planner-produced DAG ready for execution. Arrives via event bus on `k1.planner.plan.ready.v1`.

```python
@dataclass(frozen=True)
class CommittedPlan:
    plan_id: str                                 # Unique plan ID (required)
    request_id: str                              # Echoed from PlanRequest (required)
    intent: str                                  # Original intent
    steps: List[PlanStep]                        # DAG steps (required, non-empty)
    trace_id: str                                # Cognitive trace ID
    dependencies: Dict[str, List[str]] = {}      # Step dependency graph
    estimated_duration_ms: Optional[int] = None  # Planner time estimate
    created_at: float = 0.0                      # Planner timestamp
```

**PlanStep** (14-field Orchestrator extension of Fabric's 6-field PlanStep):

```python
@dataclass(frozen=True)
class PlanStep:
    # Fabric-aligned fields (1-6)
    id: str                                      # Step ID (required)
    capability: str                              # Capability name (required)
    params: Dict[str, Any] = {}                  # Capability parameters
    deps: List[str] = []                         # Step IDs this step depends on
    prompt_template: Optional[str] = None        # LLM prompt template
    tools_granted: Optional[List[str]] = None    # Granted tool names

    # Orchestrator extensions (7-14)
    output_schema: Optional[Dict] = None         # JSON Schema for output validation
    condition: Optional[ConditionExpr] = None    # Conditional execution expression
    is_optional: bool = False                    # If True, failure does not block DAG
    has_side_effects: bool = False               # If True, requires saga compensation
    compensation: Optional[str] = None           # Compensation capability name
    timeout_ms: Optional[int] = None             # Per-step timeout override
    required_context: Optional[List[str]] = None # SessionState sections needed
    safety_band_min: Optional[str] = None        # Minimum safety band required
```

**Validation rules**:

- `plan_id` and `request_id` must be non-empty.
- `steps` must be non-empty.
- All `dependencies` keys and values must reference valid step IDs.
- Dependency graph must be acyclic (Kahn's algorithm validation).

**Serialization**: `CommittedPlan.to_dict()` / `CommittedPlan.from_dict()` for event bus transport and WAL persistence.

**Example**:

```json
{
  "plan_id": "plan-abc",
  "request_id": "req-xyz",
  "intent": "Plan a family dinner",
  "trace_id": "ct-def456",
  "steps": [
    {"id": "s1", "capability": "tool.restaurant.search", "params": {"cuisine": "italian"}},
    {"id": "s2", "capability": "tool.calendar.create", "params": {"title": "Family Dinner"}, "deps": ["s1"]},
    {"id": "s3", "capability": "tool.email.send", "params": {"to": "family"}, "deps": ["s2"], "has_side_effects": true, "compensation": "tool.email.recall"}
  ],
  "dependencies": {"s2": ["s1"], "s3": ["s2"]},
  "estimated_duration_ms": 15000,
  "created_at": 1700000000.0
}
```

### 4.3 AggregatedResult

Final result of task processing (MEDIUM or HIGH tier).

```python
@dataclass(frozen=True)
class AggregatedResult:
    total_steps: int                 # Total step count
    completed: int                   # Steps with COMPLETED status
    failed: int                      # Steps with FAILED status
    cancelled: int                   # Steps with CANCELLED status
    skipped: int                     # Steps with SKIPPED status
    step_results: List[StepResult]   # Per-step results
    success: bool                    # Computed: failed == 0 and cancelled == 0
    duration_ms: int                 # Total elapsed time
    trace_id: str                    # Cognitive trace ID
    result_id: str = uuid4()         # Unique result ID
    plan_id: Optional[str] = None    # Plan ID (None for MEDIUM)
    compensations: List[CompensationRecord] = []  # Saga compensations
```

**StepResult** (per-step):

```python
@dataclass(frozen=True)
class StepResult:
    step_id: str                         # Step identifier
    capability_name: str                 # Capability executed
    status: StepStatus                   # PENDING/RUNNING/COMPLETED/FAILED/CANCELLED/SKIPPED
    duration_ms: int = 0                 # Step execution time
    result: Optional[CapabilityResult] = None  # Fabric result
    retry_attempts: int = 0             # Normal retry count
    schema_retry: bool = False          # Whether schema retry was used
    error_detail: Optional[str] = None  # Error message on failure
```

**Factory methods**:

- `AggregatedResult.from_medium()` — for MEDIUM tier (no plan_id).
- `AggregatedResult.from_dag()` — for HIGH tier (with plan_id + compensations).

### 4.4 WorkflowRunRequest

Request to execute a saved workflow.

```python
@dataclass(frozen=True)
class WorkflowRunRequest:
    workflow_id: str                    # Workflow ID (required)
    version: str                       # Workflow spec version
    trigger_type: TriggerType          # CRON, EVENT, or MANUAL
    trace_id: str                      # Cognitive trace ID
    request_id: str = uuid4()          # Unique request ID
    trigger_context: Dict[str, Any] = {}  # Trigger-specific context
    param_overrides: Dict[str, Any] = {}  # Runtime parameter overrides
    priority: str = "INTERACTIVE"      # Mailbox priority
```

**TriggerType enum**: `CRON`, `EVENT`, `MANUAL`.

### 4.5 InterruptRequest

Request to cancel or pause a running DAG.

```python
@dataclass(frozen=True)
class InterruptRequest:
    target_dag_id: Optional[str] = None  # DAG to interrupt (None = current)
    interrupt_type: str = "CANCEL_DAG"   # "CANCEL_DAG" or "PAUSE" (V2 only)
    reason: str = ""                     # Human-readable reason
    trace_id: str = ""                   # Required, non-empty
    request_id: str = uuid4()            # Unique request ID
```

**Validation**: `interrupt_type` must be in `{"CANCEL_DAG", "PAUSE"}`. `trace_id` required.

**Delivery**: Cooperative cancellation via `DAGExecutor.interrupt_flag` (atomic bool checked at each step completion). Max latency = one step execution.

### 4.6 Supporting Types

| Type | Purpose | Key Fields |
|------|---------|-----------|
| `PlanRequest` | Orchestrator -> Planner (HIGH tier) | `intent`, `trace_id`, `context: SessionSnapshot`, `request_id`, `constraints`, `timeout_ms` |
| `PlanAck` | Planner -> Orchestrator (immediate) | `request_id`, `status` (ACCEPTED/REJECTED) |
| `MicroReplanRequest` | DAGExecutor -> Planner (mid-DAG) | `original_plan_id`, `completed_results`, `remaining_steps`, `discoveries`, `failure_context` |
| `WorkflowSaveRequest` | Concierge -> Orchestrator | `committed_plan_id`, `workflow_name`, `trigger_spec: TriggerSpec` |
| `ProcessingContext` | Request-scoped trace correlation | `trace_id`, `request_id`, `tier`, `dag_id`, `workflow_id`, `interrupt_flag` |
| `PendingPlanContext` | Parked HIGH tier awaiting plan | `request_id`, `task_envelope`, `state_snapshot`, `timeout_ms` |
| `PendingHILContext` | Parked DAG awaiting HIL response | `request_id`, `dag_execution_id`, `completed_waves`, `remaining_waves`, `timeout_fallback` |
| `RecoveryResult` | crash_recovery() output | `recovered_dags`, `failed_recoveries`, `skipped` |

---

## 5. Event Wiring

All event constants live in `k1/orchestrator/events.py`. Do NOT hardcode topic strings anywhere else.

### 5.1 Emitted Events (19)

Events the Orchestrator publishes to the event bus via `IDeltaEmitPort.emit()`.

| Constant | Topic String | Producer | Consumer(s) | Payload Summary |
|----------|-------------|----------|-------------|-----------------|
| `ORCH_TASK_ACCEPTED` | `k1.orchestration.task.accepted.v1` | `_route_task()` | Concierge (PROGRESSING state) | `envelope_id`, `intent`, `tier`, `trace_id` |
| `ORCH_PLAN_REQUESTED` | `k1.orchestration.plan.requested.v1` | `_dispatch_high()` | Monitoring | `request_id`, `intent`, `tier`, `trace_id` |
| `ORCH_DAG_STARTED` | `k1.orchestration.dag.started.v1` | `DAGExecutor.execute()` | Monitoring, K0 audit | `dag_id`, `plan_id`, `step_count`, `trace_id` |
| `ORCH_DAG_MICRO_REPLAN` | `k1.orchestration.dag.micro_replan.v1` | `MicroReplanCheckpoint` | Monitoring | `dag_id`, `original_plan_id`, `new_plan_id`, `trace_id` |
| `ORCH_DAG_COMPLETED` | `k1.orchestration.dag.completed.v1` | `_emit_result()` | Concierge (COMPLETE state), K0 audit | `AggregatedResult.to_dict()` |
| `ORCH_STEP_STARTED` | `k1.orchestration.step.started.v1` | `StepRunner.run()` | Monitoring, Concierge progress | `step_id`, `capability`, `wave_index`, `trace_id` |
| `ORCH_STEP_COMPLETED` | `k1.orchestration.step.completed.v1` | `StepRunner.run()` | Monitoring, Concierge progress | `step_id`, `capability`, `duration_ms`, `trace_id` |
| `ORCH_STEP_FAILED` | `k1.orchestration.step.failed.v1` | `StepRunner.run()` | Monitoring, ErrorRouter diagnostic | `step_id`, `capability`, `error_detail`, `trace_id` |
| `ORCH_STEP_CANCELLED` | `k1.orchestration.step.cancelled.v1` | `DAGExecutor` (interrupt) | Monitoring | `step_id`, `reason`, `trace_id` |
| `ORCH_STEP_SKIPPED` | `k1.orchestration.step.skipped.v1` | `ConditionalEdgeEvaluator` | Monitoring | `step_id`, `condition`, `trace_id` |
| `ORCH_STEP_RETRYING` | `k1.orchestration.step.retrying.v1` | `StepRunner` (normal retry) | Monitoring | `step_id`, `attempt`, `max_retries`, `trace_id` |
| `ORCH_STEP_SCHEMA_RETRY` | `k1.orchestration.step.schema_retry.v1` | `OutputSchemaGuard` | Monitoring | `step_id`, `validation_errors`, `trace_id` |
| `ORCH_SAGA_COMPENSATING` | `k1.orchestration.saga.compensating.v1` | `DAGExecutor._compensate()` | K0 audit | `dag_id`, `step_id`, `compensation_capability`, `trace_id` |
| `ORCH_DELTA_V1` | `k1.orchestration.delta.v1` | Various (progress updates) | Concierge (PROGRESSING state) | `type`, `summary`, `step_id`, `trace_id` |
| `ORCH_WORKFLOW_TRIGGERED` | `k1.orchestration.workflow.triggered.v1` | `WorkflowScheduler` | Monitoring | `workflow_id`, `trigger_type`, `trace_id` |
| `ORCH_WORKFLOW_COMPLETED` | `k1.orchestration.workflow.completed.v1` | `WorkflowRunSupervisor` | Monitoring, K0 audit | `workflow_id`, `run_id`, `success`, `trace_id` |
| `ORCH_WORKFLOW_SAVED` | `k1.orchestration.workflow.saved.v1` | `_save_workflow()` | Concierge (confirmation) | `workflow_name`, `workflow_id`, `trigger_type`, `trace_id` |
| `ORCH_ERROR_ROUTED` | `k1.orchestration.error.routed.v1` | `ErrorRouter.route_error()` | Monitoring, diagnostics | `adapter`, `severity`, `action`, `error_code`, `trace_id` |
| `ORCH_MCP_TOOL_REGISTERED` | `k1.orchestration.mcp.tool_registered.v1` | `MCPRegistrationBridge` | Monitoring | `server_id`, `capability_ids`, `trace_id` |

### 5.2 Consumed Events (12)

Events the Orchestrator subscribes to via `IEventSubscriptionPort.subscribe()`.

| Constant | Topic String | Producer | Handler | Routing |
|----------|-------------|----------|---------|---------|
| `PLAN_READY` | `k1.planner.plan.ready.v1` | Planner | Event handler -> mailbox | Deserialize to `CommittedPlan`, enqueue INTERACTIVE |
| `PLAN_FAILED` | `k1.planner.plan.failed.v1` | Planner | Event handler -> `receive_plan_failed()` | Extract `request_id`, `reason` |
| `PLAN_CANCELLED` | `k1.planner.plan.cancelled.v1` | Planner | Event handler -> `receive_plan_cancelled()` | Extract `request_id` |
| `MICRO_REPLAN_READY` | `k1.planner.micro_replan.ready.v1` | Planner | `MicroReplanCheckpoint` | Synchronous response to `micro_replan()` |
| `CAPABILITY_COMPLETED` | `k1.capability.completed.v1` | Fabric | `StepRunner` | Step result delivery |
| `CAPABILITY_FAILED` | `k1.capability.failed.v1` | Fabric | `StepRunner` | Step failure delivery |
| `CONTRACT_UPDATED` | `k1.fabric.contract.updated.v1` | Fabric | `ProactiveGapDetector` | Triggers gap scan for affected workflows |
| `AGENT_TOOL_CALL` | `k1.fabric.agent.tool_call.v1` | Fabric | `ExecutionMonitor` | Sub-step tracking |
| `AGENT_LLM_CALL` | `k1.fabric.agent.llm_call.v1` | Fabric | `ExecutionMonitor` | Sub-step tracking |
| `WORKFLOW_TRIGGER_DUE` | `k1.orchestration.workflow.trigger_due.v1` | `WorkflowScheduler` | Event handler -> mailbox | Self-emitted, creates `WorkflowRunRequest` |
| `HIL_OVERRIDE_RESPONSE` | `k1.hil.override_response.v1` | Concierge (user) | `PendingHILContext` resolver | Resolves parked DAG |
| `HIL_FALLBACK_RESPONSE` | `k1.hil.fallback_response.v1` | Concierge (user) | `PendingHILContext` resolver | Resolves parked DAG |

### 5.3 Event Subscription Registration

Subscriptions are registered at startup by `OrchestratorService._subscribe_events()` (called during `init()` step 8):

```
Required subscriptions (from event_subscription_port.py docstring):
  k1.planner.plan.ready.v1      -> route to mailbox as CommittedPlan
  k1.planner.plan.failed.v1     -> route to mailbox as PlanFailedEvent
  k1.planner.plan.cancelled.v1  -> route to mailbox as PlanCancelledEvent
  k1.hil.override_response.v1   -> route to PendingHILContext resolver
  k1.hil.fallback_response.v1   -> route to PendingHILContext resolver
  k1.fabric.contract.updated.v1 -> route to GapDetector
  k1.fabric.agent.tool_call.v1  -> route to ExecutionMonitor
  k1.fabric.agent.llm_call.v1   -> route to ExecutionMonitor
  k1.orchestration.workflow.trigger_due.v1 -> route to WorkflowScheduler
  k1.capability.completed.v1    -> route to StepRunner
  k1.capability.failed.v1       -> route to StepRunner
```

### 5.4 Aggregate Test Sets

For bulk validation in tests, `events.py` exports two frozen sets:

```python
ALL_EMITTED: frozenset   # 19 emitted event constants
ALL_CONSUMED: frozenset  # 12 consumed event constants (actually 12, including MICRO_REPLAN_READY)
```

---

## 6. Error Handling

### 6.1 AdapterError / AdapterException

All port adapters wrap raw exceptions into structured errors:

```python
@dataclass(frozen=True)
class AdapterError:
    severity: ErrorSeverity      # RECOVERABLE, DEGRADED, or TERMINAL
    adapter_name: str            # Port key (e.g., "fabric_gateway", "planner")
    operation: str               # Failed operation (e.g., "execute", "request_plan")
    error_code: str              # Error classification code
    error_message: str           # Human-readable message
    original_exception: Optional[Exception] = None
    fallback_action: str = ""
    trace_id: str = ""
```

`AdapterException` wraps `AdapterError` as a raiseable exception:

```python
class AdapterException(Exception):
    detail: AdapterError
    adapter_name: str
    operation: str
    error_code: str
    error_message: str
    severity: ErrorSeverity
    trace_id: str
```

### 6.2 ErrorRouter Classification Matrix

`ErrorRouter` (in `orchestration/error_router.py`) classifies errors into actions.
**Stateless** — no mutable internal state. Decision-only; caller executes the action.

| Adapter | Severity | Action | Details |
|---------|----------|--------|---------|
| `mailbox` | RECOVERABLE | `RETRY(1)` | Re-enqueue once |
| `delta_emit` | RECOVERABLE | `RETRY(1)` | Retry once, then silent drop |
| `bridge_write` | RECOVERABLE | `RETRY(1)` | Retry once, then silent drop |
| `event_sub` | RECOVERABLE | `RETRY(1)` | Resubscribe |
| `fabric_gateway` | DEGRADED | `DEGRADE` | Step fails, independent steps continue |
| `planner` | DEGRADED | `FALLBACK` | Degrade HIGH to MEDIUM |
| `state_read` | DEGRADED | `DEGRADE(fallback={})` | Use stale/empty context |
| Any | TERMINAL | `ABORT` | Unrecoverable, stop execution |

### 6.3 ErrorAction

```python
@dataclass(frozen=True)
class ErrorAction:
    action: str       # "RETRY", "FALLBACK", "DEGRADE", "ABORT"
    retry_count: int = 0
    fallback_value: Optional[Any] = None
    reason: str = ""
```

### 6.4 Error Flow by Tier

**MEDIUM tier** (`_dispatch_medium()`):

- Per-step error isolation: `AdapterException` on one step records FAILED for that step;
  other steps still execute.
- Route-level `AdapterException` (from `_route_task()`):
  - RECOVERABLE -> re-enqueue envelope once (guard prevents infinite loop).
  - DEGRADED -> `ProcessResult.DEGRADED`.
  - TERMINAL -> `ProcessResult.FAILED`.

**HIGH tier** (`_dispatch_high()` / `_receive_plan()`):

- Planner unreachable -> `ProcessResult.FAILED`.
- Planner rejects (PlanAck status != ACCEPTED) -> `ProcessResult.FAILED`.
- ConstraintResolver validation failure -> `ProcessResult.FAILED`.
- DAG execution: errors handled by `StepRunner` retry policy + `ErrorRouter`:
  - Normal retries: `normal_retries=2` (from `OrchestratorPolicies`).
  - Schema retries: `schema_retries=1`.

**Workflow** (`_dispatch_workflow()`):

- Same error handling as HIGH tier (goes through DAGExecutor).

### 6.5 StepRunner Retry Policy

`StepRunner` (in `orchestration/step_runner.py`) manages per-step execution:

| Parameter | Value | Source |
|-----------|-------|--------|
| `normal_retries` | 2 | `OrchestratorPolicies` (from config `step_max_retries`) |
| `schema_retries` | 1 | Hardcoded V1 |
| `step_timeout_default_ms` | 30000 | `OrchestratorPolicies` |
| `max_steps_per_plan` | 50 | Hardcoded V1 |
| `max_waves_per_plan` | 20 | Hardcoded V1 |
| `max_concurrent_per_wave` | 10 | Config `max_wave_parallelism` |

Retry flow:

1. `StepRunner` calls `fabric_port.execute()`.
2. On exception: wraps as failure with `retriable=False`.
3. On `CapabilityResult(success=False, retriable=True)`: retries up to `normal_retries`.
4. After retry exhaustion: returns `StepResult(status=FAILED)`.

---

## 7. Tier Degradation

### 7.1 Circuit Breaker Ownership

| CB Name | Owner | Effect on Orchestrator |
|---------|-------|----------------------|
| `CB_ORCHESTRATOR` | Concierge | Concierge stops sending TaskEnvelopes when Orchestrator mailbox full. |
| `CB_FABRIC` | Concierge/Fabric | Fabric step execution fails. Orchestrator sees `AdapterError(DEGRADED)`. |
| `CB_PLANNER` | Orchestrator | Orchestrator owns. Controls plan request flow. |
| `CB_MCP` | Fabric | MCP server offline. Fabric-side handling. |
| `CB_BRIDGE` | Concierge/Bridge | K0 writes fail. Orchestrator sees `AdapterError(RECOVERABLE)`. |

### 7.2 CB_PLANNER State Machine

```python
@dataclass
class CircuitBreakerState:
    config: CircuitBreakerConfig
    state: str = "CLOSED"        # CLOSED -> OPEN -> HALF_OPEN -> CLOSED
    failure_count: int = 0
    last_failure_at: Optional[float] = None
    opened_at: Optional[float] = None
```

State transitions:

- `CLOSED` -> `OPEN`: when `failure_count >= config.failure_threshold`.
- `OPEN` -> `HALF_OPEN`: when `time.time() - opened_at >= config.reset_timeout_ms / 1000`.
- `HALF_OPEN` -> `CLOSED`: on successful probe.
- `HALF_OPEN` -> `OPEN`: on probe failure (reset timer).

### 7.3 Tier Degradation Cascade

When Planner is unavailable (CB_PLANNER OPEN):

```
HIGH tier task arrives
    |
    v
_dispatch_high() calls planner_port.request_plan()
    |
    v
AdapterException(DEGRADED, adapter="planner")
    |
    v
ErrorRouter._classify_error() -> FALLBACK
    (reason: "degrade HIGH to MEDIUM")
    |
    v
OrchestratorService falls back:
    - If capabilities present in envelope: treat as MEDIUM tier
    - If no capabilities: return ProcessResult.FAILED
```

When Fabric is unavailable (CB_FABRIC OPEN):

```
Step execution via fabric_port.execute()
    |
    v
AdapterException(DEGRADED, adapter="fabric_gateway")
    |
    v
ErrorRouter._classify_error() -> DEGRADE
    (reason: "Fabric step failed")
    |
    v
StepResult(status=FAILED) for that step
Independent steps in same wave still execute
DAG result: DEGRADED (partial success)
```

When K0 Bridge is unavailable:

```
WAL write / audit submit
    |
    v
AdapterException(RECOVERABLE, adapter="bridge_write")
    |
    v
ErrorRouter._classify_error() -> RETRY(1)
    |
    v
Retry once. If still fails: silent drop.
Edge-First architecture: local execution > audit persistence.
Crash recovery gracefully handles K0 offline.
```

When SessionState is unavailable:

```
state_port.get_snapshot() / read_section()
    |
    v
AdapterException(DEGRADED, adapter="state_read")
    |
    v
ErrorRouter._classify_error() -> DEGRADE(fallback_value={})
    |
    v
Proceed with empty/stale context.
Planner works without context; safety band defaults to most permissive.
```

### 7.4 HealthStatus

The `HealthStatus` type reflects degradation state:

```python
@dataclass(frozen=True)
class HealthStatus:
    status: str          # "HEALTHY", "DEGRADED", "UNHEALTHY"
    uptime_ms: int
    active_dags: int
    mailbox_depth: int
    circuit_breakers: Dict[str, str]  # CB name -> state
    last_error: Optional[str]
```

Status derivation:

- `HEALTHY`: CB_PLANNER closed, mailbox < 80% capacity.
- `DEGRADED`: CB_PLANNER open/half-open OR consumed CB issues.
- `UNHEALTHY`: CB_PLANNER open AND mailbox at capacity.

### 7.5 Caller Responsibilities

| Caller | Failure Signal | Expected Response |
|--------|---------------|-------------------|
| Concierge | `TaskAck(REJECTED_FULL)` | Back off, show user "busy" state. Respect CB_ORCHESTRATOR. |
| Concierge | `AggregatedResult(success=False)` | Show error to user. May retry with different tier. |
| Planner | `PlanAck(REJECTED)` from Orchestrator | Do not retry same request. |
| Fabric | `CapabilityResult(success=False)` | Orchestrator handles via StepRunner retry policy. |
| WorkflowScheduler | `ProcessResult.DEFERRED` | Re-enqueue on next tick (workflow competes for ConcurrencyGuard). |

---

## Appendix A: Key Invariants

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| ORCH-01 | Orchestrator NEVER writes SessionState | `IStateReadPort` has no write methods |
| ORCH-02 | Orchestrator NEVER calls LLM | No LLM port exists |
| ORCH-03 | All execution via Fabric port | `IFabricGatewayPort.execute()` is the only execution path |
| ORCH-09 | `trace_id` on every emitted event | `IDeltaEmitPort.emit(trace_id=...)` required parameter |
| ORCH-10 | MEDIUM tier max 2 capabilities | `TaskEnvelope.__post_init__()` + `_dispatch_medium()` defense-in-depth |
| ORCH-11 | HIGH tier requires CommittedPlan from Planner | `_dispatch_high()` sends PlanRequest; `_receive_plan()` executes plan |
| ORCH-13 | Max 1 micro-replan per DAG | `MicroReplanCheckpoint` tracks `replan_count` |
| ORCH-16 | Conditional edges via `ConditionExpr` | `ConditionalEdgeEvaluator` pre-wave guard |

## Appendix B: File Reference

| Component | File Path |
|-----------|-----------|
| OrchestratorService | `k1/orchestrator/orchestration/orchestrator_service.py` |
| OrchestratorFactory | `k1/orchestrator/factory.py` |
| ErrorRouter | `k1/orchestrator/orchestration/error_router.py` |
| DAGExecutor | `k1/orchestrator/orchestration/dag_executor.py` |
| StepRunner | `k1/orchestrator/orchestration/step_runner.py` |
| ConstraintResolver | `k1/orchestrator/orchestration/constraint_resolver.py` |
| Guards | `k1/orchestrator/orchestration/guards.py` |
| ParamResolver | `k1/orchestrator/orchestration/param_resolver.py` |
| Types | `k1/orchestrator/types.py` |
| Events | `k1/orchestrator/events.py` |
| Config | `k1/orchestrator/config.py` |
| Metrics | `k1/orchestrator/metrics.py` |
| WorkflowEngine | `k1/orchestrator/workflows/workflow_engine.py` |
| WorkflowRegistry | `k1/orchestrator/workflows/workflow_registry.py` |
| WorkflowScheduler | `k1/orchestrator/workflows/workflow_scheduler.py` |
| WorkflowCompiler | `k1/orchestrator/workflows/workflow_compiler.py` |
| WorkflowRunSupervisor | `k1/orchestrator/workflows/workflow_supervisor.py` |
| ProactiveGapDetector | `k1/orchestrator/workflows/gap_detector.py` |
| CrossWorkflowResolver | `k1/orchestrator/workflows/cross_workflow_resolver.py` |
| ConnectorLifecycleManager | `k1/orchestrator/connectors/connector_lifecycle.py` |
| MCPToolDiscovery | `k1/orchestrator/connectors/mcp_discovery.py` |
| MCPRegistrationBridge | `k1/orchestrator/connectors/mcp_registrar.py` |
| Port interfaces | `k1/orchestrator/ports/*.py` |
| Production adapters | `k1/orchestrator/adapters/*_adapter.py` |
| Test adapters | `k1/orchestrator/adapters/test_*_adapter.py`, `mock_*_adapter.py` |
| Admin port | `k1/orchestrator/ports/admin_port.py` |
| Admin adapter | `k1/orchestrator/adapters/admin_http_adapter.py` |
