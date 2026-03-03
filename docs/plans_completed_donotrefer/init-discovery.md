# init() Lifecycle Discovery Document (6.2.2)

> **Purpose**: Comprehensive reference for implementing `async def init(self) -> None` in OrchestratorService.
> Gathered from orchestrator-implementation-plan.md 6.2.2 + full code discovery of OrchestratorService,
> ConnectorLifecycleManager, WorkflowEngine, event system, guards, and config.
>
> **Target file**: `k1/orchestrator/orchestration/orchestrator_service.py` (exists, 1612 lines)

---

## 1. Plan Specification (10 Steps)

```
Step  1: Validate all 8 ports injected (non-None). Log port types.
Step  2: Connect ports that need initialization.
Step  3: Assert concurrency guard not locked.
Step  4: connector_lifecycle.discover_and_register(). Log result.
Step  5: (Commentary) Tools now available for DAG execution.
Step  6: Load active workflows via workflow_engine.registry.list_active(). Log count.
Step  7: Start WorkflowScheduler via workflow_engine.scheduler.start().
Step  8: Subscribe to all consumed events per 1.4.7 spec (8 subscriptions).
Step  9: Start connector lifecycle monitoring + timeout reaper task.
Step 10: Start mailbox processing loop task.
```

---

## 2. CRITICAL FINDING: Missing Constructor Dependencies

OrchestratorService constructor currently accepts 13 kwargs:
```python
__init__(self, *, mailbox, dag_executor, constraint_resolver,
         workflow_engine, connector_lifecycle, error_router,
         concurrency_guard, fabric_port, planner_port, state_port,
         delta_port, bridge_port, config)
```

**MISSING from constructor (needed by init):**

| Dependency | Needed By | Reason |
|-----------|-----------|--------|
| `event_port: IEventSubscriptionPort` | Step 8 | `event_port.subscribe(topic, handler)` for 8+ event subscriptions |

**NOT missing (accessible via WorkflowEngine properties):**
- `workflow_engine.registry` -> Step 6 (WorkflowRegistry.list_active)
- `workflow_engine.scheduler` -> Step 7 (WorkflowScheduler.start)
- `workflow_engine.gap_detector` -> Step 9 (ProactiveGapDetector.start)

**Resolution**: Add `event_port: IEventSubscriptionPort` to:
1. OrchestratorService `__init__` kwargs
2. OrchestratorService `__slots__` (as `_event_port`)
3. OrchestratorFactory `_construct_orchestrator` FINAL step (pass event_port)

---

## 3. CRITICAL FINDING: Missing __slots__ for Lifecycle State

Current `__slots__` (14 entries):
```python
__slots__ = (
    "_dag_executor", "_constraint_resolver", "_workflow_engine",
    "_connector_lifecycle", "_error_router", "_concurrency_guard",
    "_fabric_port", "_planner_port", "_state_port", "_delta_port",
    "_bridge_port", "_mailbox", "_config",
    "_pending_plans", "_pending_hil", "_executed_plans",
    "_requeued_envelope_ids", "_started_at",
)
```

**MUST ADD for init():**

| Slot | Type | Purpose |
|------|------|---------|
| `_event_port` | `IEventSubscriptionPort` | Event subscription port (Step 8) |
| `_initialized` | `bool` | Idempotency guard (plan gotcha) |
| `_running` | `bool` | Mailbox loop control flag |
| `_loop_task` | `Optional[asyncio.Task]` | Step 10: mailbox loop task |
| `_reaper_task` | `Optional[asyncio.Task]` | Step 9: stale context reaper task |
| `_subscriptions` | `list[SubscriptionHandle]` | Step 8: for shutdown unsubscribe (6.2.3) |

---

## 4. Protocol Stub Gaps

### 4.1 ConnectorLifecycleLike (EMPTY)

**File**: `orchestrator_service.py:130`
```python
class ConnectorLifecycleLike(Protocol):
    """Placeholder protocol for ConnectorLifecycleManager (5.x)."""
    ...
```

**Needs for init():**
- `discover_and_register() -> RegistrationResult` (Step 4)
- `start_lifecycle_monitoring() -> None` (Step 9, sync)
- `stop_lifecycle_monitoring() -> None` (shutdown, sync)

**Resolution**: Update Protocol stub to declare these methods.

### 4.2 ConcurrencyGuardLike (Missing `active` property)

**File**: `orchestrator_service.py:151`
```python
class ConcurrencyGuardLike(Protocol):
    def acquire(self, ctx: ProcessingContext) -> bool: ...
    def release(self, ctx: ProcessingContext) -> None: ...
```

**Actual ConcurrencyGuard has:**
- `active: bool` property (returns `self._active`)
- `acquire()` -- async, NO ctx param
- `release()` -- sync, NO ctx param

**Pre-existing mismatch**: acquire/release arity. For init() step 3, we need `self._concurrency_guard.active` to assert not locked. The `.active` property exists on ConcurrencyGuard but not on the Protocol.

**Resolution**: Either add `active` to Protocol, or use `type: ignore` at call site (pattern consistent with existing mismatches).

---

## 5. ConnectorLifecycleManager API (Step 4 + Step 9)

**File**: `k1/orchestrator/connectors/connector_lifecycle.py`
**Class**: `ConnectorLifecycleManager`

### 5.1 discover_and_register()

```python
async def discover_and_register(self) -> RegistrationResult:
```

**RegistrationResult** (`mcp_registrar.py:64`, frozen dataclass):
```python
@dataclass(frozen=True)
class RegistrationResult:
    registered: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
```

**Plan says**: Log `"{registration.registered} MCP tools registered in Fabric, {registration.skipped} skipped"`

### 5.2 start_lifecycle_monitoring()

```python
def start_lifecycle_monitoring(self) -> None:  # SYNC, NOT async!
```

Subscribes to `k1.fabric.provider.health.changed.v1`.
Returns `None`. Cannot be wrapped in `asyncio.create_task()`.

**Plan says**: `self._lifecycle_task = asyncio.create_task(self.connector_lifecycle.start_lifecycle_monitoring())`

**Reality**: `start_lifecycle_monitoring()` is sync, returns None. Just call it directly:
```python
self._connector_lifecycle.start_lifecycle_monitoring()
```
No task needed. No `_lifecycle_task` slot needed for this specific call.

### 5.3 stop_lifecycle_monitoring()

```python
def stop_lifecycle_monitoring(self) -> None:  # SYNC
```

Unsubscribes from health events. Used by shutdown (6.2.3).

---

## 6. WorkflowEngine Sub-Component Access (Steps 6, 7, 9)

**File**: `k1/orchestrator/workflows/workflow_engine.py`

WorkflowEngine exposes read-only properties for lifecycle wiring:

| Property | Type | Used By |
|----------|------|---------|
| `.registry` | `WorkflowRegistry` | Step 6: `list_active()` |
| `.scheduler` | `WorkflowScheduler` | Step 7: `start()` |
| `.gap_detector` | `ProactiveGapDetector` | Step 9: `start()` (own lifecycle) |
| `.supervisor` | `WorkflowRunSupervisor` | Not in init |
| `.cross_resolver` | `CrossWorkflowResolver` | Not in init |
| `.compiler` | `WorkflowCompiler` | Not in init |

### 6.1 WorkflowRegistry.list_active()

```python
async def list_active(self) -> List[WorkflowSpec]:
    """Filters by active=True via storage."""
    return await self._storage.list_workflows(active_only=True)
```

Returns list of WorkflowSpec. Init logs the count.

### 6.2 WorkflowScheduler.start()

```python
async def start(self) -> None:
    """Creates asyncio.Task for tick loop. Idempotent (no-op if running)."""
    if self._running:
        return
    self._running = True
    self._task = asyncio.create_task(self._tick_loop())
```

### 6.3 ProactiveGapDetector.start()

```python
async def start(self) -> None:
    """Subscribe to contract updates and start processing loop. Idempotent."""
    if self._running:
        return
    self._running = True
    self._subscription_handle = self._events.subscribe(
        _CONTRACT_UPDATED_TOPIC, self._on_contract_updated,
    )
    self._process_task = asyncio.create_task(self._process_loop())
```

**KEY**: GapDetector manages its OWN contract_updated subscription internally via `start()`.
Init step 8 lists `k1.fabric.capability.contract_updated.v1 -> route to GapDetector`, but
GapDetector subscribes to `k1.fabric.contract.updated.v1` (slightly different topic) inside
`start()`. We should call `gap_detector.start()` in init rather than duplicating the subscription.

---

## 7. Event Subscription System (Step 8)

### 7.1 IEventSubscriptionPort.subscribe()

```python
def subscribe(
    self,
    topic: str,
    handler: Callable[[str, Dict[str, Any]], None],
) -> SubscriptionHandle:
```

- Subscribe is **SYNC** (not async)
- Handler is **SYNC**: `(topic: str, payload: Dict[str, Any]) -> None`
- Returns `SubscriptionHandle` (for unsubscribe in shutdown)
- Supports wildcard patterns (e.g., `k1.hil.*`)

### 7.2 SubscriptionHandle

```python
@dataclass
class SubscriptionHandle:
    subscription_id: str = ""
    topic: str = ""
```

From `k1/fabric/ports/event_port.py:56`.

### 7.3 Event Topic Constants (events.py)

All consumed events are defined in `k1/orchestrator/events.py`:

```python
# Planner responses
PLAN_READY = "k1.planner.plan.ready.v1"
PLAN_FAILED = "k1.planner.plan.failed.v1"
PLAN_CANCELLED = "k1.planner.plan.cancelled.v1"

# HIL responses
HIL_OVERRIDE_RESPONSE = "k1.hil.override_response.v1"
HIL_FALLBACK_RESPONSE = "k1.hil.fallback_response.v1"

# Fabric contract changes
CONTRACT_UPDATED = "k1.fabric.contract.updated.v1"

# Fabric agent sub-step events
AGENT_TOOL_CALL = "k1.fabric.agent.tool_call.v1"
AGENT_LLM_CALL = "k1.fabric.agent.llm_call.v1"
```

---

## 8. Subscription Routing Map (Step 8 Detail)

### 8.1 Planner Events -> Mailbox Routing

| Topic | Handler Action | Priority |
|-------|---------------|----------|
| `PLAN_READY` | Deserialize payload -> `CommittedPlan`, enqueue to mailbox | `INTERACTIVE` |
| `PLAN_FAILED` | Build error context, clean up `pending_plans[request_id]`, emit fail delta | N/A (direct) |
| `PLAN_CANCELLED` | Clean up `pending_plans[request_id]`, emit cancel delta | N/A (direct) |

**PlanFailedEvent / PlanCancelledEvent types DO NOT EXIST as dataclasses.**
Per `mailbox_port.py` docstring: "they are Dict[str, Any] payloads deserialized into these types by the handler -- not separate dataclasses enqueued directly."

For PLAN_FAILED and PLAN_CANCELLED, the handler should:
1. Extract `request_id` from payload
2. Pop the `PendingPlanContext` from `self._pending_plans`
3. Emit failure/cancellation delta
4. Log the event

These handlers act directly (no mailbox enqueue needed) because they only touch internal state + fire-and-forget deltas.

### 8.2 HIL Response Events -> PendingHILContext Resolver

| Topic | Handler Action |
|-------|---------------|
| `HIL_OVERRIDE_RESPONSE` | Resolve `pending_hil[request_id]` with user's choice |
| `HIL_FALLBACK_RESPONSE` | Resolve `pending_hil[request_id]` with fallback |

Handler:
1. Extract `request_id` and `choice`/`fallback_action` from payload
2. Pop `PendingHILContext` from `self._pending_hil`
3. Resume DAG execution based on choice (CONTINUE/CANCEL_DAG)

**NOTE**: Resuming a DAG from HIL requires complex state restoration that may
not be fully implemented yet. For init(), we wire the handler; the handler
body can be a stub that logs + cleans up pending_hil if full resumption
isn't ready.

### 8.3 Contract Updated -> GapDetector

**Handled by `gap_detector.start()` internally** -- subscribes to
`k1.fabric.contract.updated.v1` and runs async processing loop.

init() calls `await self._workflow_engine.gap_detector.start()` instead
of manually subscribing.

### 8.4 Agent Sub-Step Events -> SubStepObserver

**Handled by `SubStepObserver.start()` per DAG** -- NOT a service-level subscription.
SubStepObserver subscribes to `fabric.agent.*.tool_call.*` and `fabric.agent.*.llm_call.*`
per DAG execution (DAGExecutor lifecycle).

init() does NOT subscribe to these -- DAGExecutor manages SubStepObserver lifecycle.

### 8.5 Summary: Subscriptions init() Must Register

| # | Topic Constant | Handler Target | Notes |
|---|---------------|----------------|-------|
| 1 | `PLAN_READY` | `_on_plan_ready` | Deserialize + enqueue to mailbox |
| 2 | `PLAN_FAILED` | `_on_plan_failed` | Direct: clean pending_plans + emit delta |
| 3 | `PLAN_CANCELLED` | `_on_plan_cancelled` | Direct: clean pending_plans + emit delta |
| 4 | `HIL_OVERRIDE_RESPONSE` | `_on_hil_override` | Resolve pending_hil |
| 5 | `HIL_FALLBACK_RESPONSE` | `_on_hil_fallback` | Resolve pending_hil |

GapDetector topics: Managed by `gap_detector.start()` (called in init step 9).
SubStepObserver topics: Managed by DAGExecutor per-DAG lifecycle.

---

## 9. Timeout Reaper (Step 9)

### 9.1 Existing Method

```python
async def reap_stale_contexts(self) -> int:
```

**File**: `orchestrator_service.py:1214`

One-shot method: iterates `_pending_plans` and `_pending_hil`, expires entries
where `(now - created_at) > (timeout_ms / 1000.0)`.

Returns count of reaped contexts.

### 9.2 Reaper Loop (MUST CREATE)

The plan says: `self._reaper_task = asyncio.create_task(self._reap_stale_contexts())`

But `reap_stale_contexts()` is one-shot, not a loop. Need a wrapper:

```python
async def _reap_loop(self) -> None:
    """Periodic reaper for stale pending contexts."""
    interval_s = self._config.context_reap_interval_ms / 1000.0
    while self._running:
        await asyncio.sleep(interval_s)
        try:
            reaped = await self.reap_stale_contexts()
            if reaped > 0:
                log.info("reap_loop: reaped %d stale contexts", reaped)
        except Exception:
            log.exception("reap_loop: error during reap")
```

Config field: `context_reap_interval_ms: int = 5_000` (5 seconds).

---

## 10. Mailbox Loop (Step 10)

### 10.1 Issue 6.2.5 Defines _mailbox_loop

The plan says `_mailbox_loop()` is issue 6.2.5 (separate from init).

For init() to start the loop, we need at minimum:
- `_mailbox_loop()` method on OrchestratorService
- `self._running` flag for loop control

**Approach for 6.2.2**: Implement `_mailbox_loop` as part of init because:
1. init() step 10 starts the loop (`self._loop_task = asyncio.create_task(self._mailbox_loop())`)
2. The loop body is simple: dequeue -> process -> sleep(1ms)
3. Can't have init() without the loop it starts

OR: Defer step 10 with a TODO and leave it to 6.2.5. init() is still
functional for testing without the loop (tests call process() directly).

**Recommendation**: Implement the loop in init() since the plan step 10
explicitly says to start it. The loop is inextricable from init().

### 10.2 _mailbox_loop Signature (from 6.2.5 spec)

```python
async def _mailbox_loop(self) -> None:
    while self._running:
        msg = self._mailbox.dequeue()
        if msg is None:
            await asyncio.sleep(0.001)  # 1ms yield
            continue
        await self._process_one(msg)
```

### 10.3 _process_one (simplified for init-only scope)

```python
async def _process_one(self, msg: MailboxMessage) -> None:
    try:
        result = await self.process(msg)
        # process() already handles all logging and error routing
    except Exception:
        log.exception("_mailbox_loop: unhandled exception in process()")
```

---

## 11. Concurrency Guard Check (Step 3)

ConcurrencyGuard has:
```python
@property
def active(self) -> bool:
    return self._active

async def acquire(self) -> bool:  # NOTE: No ctx parameter!
def release(self) -> None:         # NOTE: No ctx parameter!
```

Step 3: "Acquire concurrency guard initial state (assert not locked)"

```python
assert not self._concurrency_guard.active, \
    "ConcurrencyGuard must not be active at init time"
```

**Type mismatch note**: ConcurrencyGuardLike Protocol says `acquire(self, ctx)` and
`release(self, ctx)`. Actual ConcurrencyGuard takes NO ctx. This is a pre-existing
mismatch (documented in factory with `type: ignore`). For init() step 3, we access
`.active` which is on the real class but not the Protocol.

---

## 12. Idempotency Guard (Plan Gotcha)

> init() must be idempotent -- calling twice should be safe (guard with self._initialized flag)

```python
if self._initialized:
    log.warning("init() called but already initialized, skipping")
    return
# ... 10 steps ...
self._initialized = True
```

Set `self._initialized = False` in `__init__`.

---

## 13. Port Validation (Step 1)

OrchestratorService has access to these ports:

| Port | Attribute | Type |
|------|-----------|------|
| mailbox | `self._mailbox` | `IMailboxPort` |
| fabric | `self._fabric_port` | `IFabricGatewayPort` |
| planner | `self._planner_port` | `IPlannerPort` |
| state | `self._state_port` | `IStateReadPort` |
| delta | `self._delta_port` | `IDeltaEmitPort` |
| bridge | `self._bridge_port` | `IBridgeWritePort` |
| event | `self._event_port` | `IEventSubscriptionPort` (MUST ADD) |
| config | `self._config` | `OrchestratorConfig` |

**Missing from injection**: `storage_port` (IWorkflowStoragePort) -- not needed by init()
directly (WorkflowEngine sub-components hold their own storage refs).

Step 1 validates these 7 port refs (mailbox + 5 infra ports + event_port) plus
the 5 service collaborators (dag_executor, constraint_resolver, workflow_engine,
connector_lifecycle, error_router, concurrency_guard) are non-None.

Log each port type for diagnostics:
```python
log.info("init.port_types",
    extra={
        "mailbox": type(self._mailbox).__name__,
        "fabric": type(self._fabric_port).__name__,
        ...
    },
)
```

---

## 14. Async MCP Handling (SPEC-10)

> init() proceeds after 500ms regardless. If MCP discovery is slow, continue in background.

The `discover_and_register()` call in step 4 could be slow. Plan says use timeout:

```python
try:
    registration = await asyncio.wait_for(
        self._connector_lifecycle.discover_and_register(),
        timeout=0.5,  # 500ms
    )
except asyncio.TimeoutError:
    log.warning("init: MCP discovery timed out after 500ms, continuing in background")
    registration = RegistrationResult()  # empty result
    # Background task handles late-arriving registrations
```

---

## 15. Event Handler Implementations

### 15.1 _on_plan_ready (PLAN_READY)

```python
def _on_plan_ready(self, topic: str, payload: Dict[str, Any]) -> None:
    """Route CommittedPlan from Planner to mailbox (sync handler)."""
    try:
        plan = CommittedPlan(
            plan_id=payload["plan_id"],
            request_id=payload["request_id"],
            intent=payload.get("intent", ""),
            steps=...,  # Must deserialize PlanStep list
            trace_id=payload.get("trace_id", ""),
            dependencies=payload.get("dependencies", {}),
        )
        self._mailbox.enqueue(plan, priority="INTERACTIVE")
    except Exception:
        log.exception("_on_plan_ready: failed to deserialize/enqueue CommittedPlan")
```

**Complexity**: Deserializing `steps` from payload dict -> List[PlanStep]
requires knowing PlanStep structure. For V1, this is the most complex handler.

### 15.2 _on_plan_failed / _on_plan_cancelled

```python
def _on_plan_failed(self, topic: str, payload: Dict[str, Any]) -> None:
    """Handle plan failure from Planner (sync handler)."""
    request_id = payload.get("request_id", "")
    pending = self._pending_plans.pop(request_id, None)
    if pending is None:
        log.warning("_on_plan_failed: no pending context for request_id=%s", request_id)
        return
    log.warning("_on_plan_failed: plan failed for request_id=%s", request_id)
    # Fire-and-forget: emit failure delta (sync handler can't await)
    # Enqueue a synthetic failure message or handle directly
```

**Sync handler constraint**: Handlers are sync (`Callable[[str, Dict], None]`).
Cannot `await` delta_port.emit() or planner_port.cancel_plan().
Options:
  A. Directly call sync cleanup (pop pending_plans) and log. Delta emission deferred.
  B. Enqueue a failure message to mailbox for async processing.

Simplest V1: Pop pending context, log. Delta emission is best-effort -- if delta_port.emit
is actually sync under the hood (TestDeltaAdapter.emit is sync), it works. For production
DeltaEmitAdapter, emit() is async -- needs asyncio.get_event_loop().create_task() or similar.

### 15.3 _on_hil_override / _on_hil_fallback

```python
def _on_hil_override(self, topic: str, payload: Dict[str, Any]) -> None:
    request_id = payload.get("request_id", "")
    choice = payload.get("choice", "CONTINUE")
    pending = self._pending_hil.pop(request_id, None)
    if pending is None:
        log.warning("_on_hil_override: no pending HIL for request_id=%s", request_id)
        return
    log.info("_on_hil_override: resolved request_id=%s with choice=%s", request_id, choice)
    # V1: Log the resolution. Full DAG resume deferred.
```

---

## 16. Changes Required to Factory (6.2.1)

Adding `event_port` to OrchestratorService constructor requires updating factory.py:

```python
# In _construct_orchestrator, FINAL step:
service = OrchestratorService(
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
    event_port=event_port,  # NEW
    config=config,
)
```

---

## 17. Changes Required to Test Infrastructure

Existing tests create OrchestratorService with 13 kwargs.
Adding `event_port` means all test fixtures must pass `event_port=<adapter>`.

Affected test files:
- `tests/k1/orchestrator/test_orchestrator_service.py` (105 tests)
- `tests/k1/orchestrator/test_factory.py` (27 tests -- factory handles it)
- Any other file that constructs OrchestratorService directly

---

## 18. Full init() Implementation Outline

```python
async def init(self) -> None:
    # Idempotency guard
    if self._initialized:
        log.warning("init.already_initialized")
        return

    t0 = time.monotonic()

    # Step 1: Validate ports non-None
    self._validate_ports()  # raises RuntimeError if any None

    # Step 2: Connect ports (no-op for V1 in-process adapters)
    # Reserved for future: event bus connection setup

    # Step 3: Assert concurrency guard not locked
    assert not self._concurrency_guard.active  # type: ignore[union-attr]

    # Step 4: MCP discover + register (500ms timeout)
    registration = await self._discover_mcp_tools()

    # Step 5: (logged in step 4)

    # Step 6: Load active workflows
    workflows = await self._workflow_engine.registry.list_active()
    log.info("init.workflows_loaded", extra={"count": len(workflows)})

    # Step 7: Start scheduler
    await self._workflow_engine.scheduler.start()

    # Step 8: Subscribe to consumed events
    self._subscribe_events()

    # Step 9a: Start gap detector
    await self._workflow_engine.gap_detector.start()

    # Step 9b: Start connector lifecycle monitoring (sync)
    self._connector_lifecycle.start_lifecycle_monitoring()  # type: ignore[union-attr]

    # Step 9c: Start timeout reaper task
    self._running = True
    self._reaper_task = asyncio.create_task(self._reap_loop())

    # Step 10: Start mailbox processing loop
    self._loop_task = asyncio.create_task(self._mailbox_loop())

    self._initialized = True

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.info("init.complete", extra={"elapsed_ms": elapsed_ms})
```

---

## 19. Anti-Hallucination Rules for init()

1. **init() must be idempotent** -- guard with `_initialized` flag
2. **Handlers are SYNC** -- IEventSubscriptionPort handlers receive `(topic, payload)` sync
3. **start_lifecycle_monitoring() is SYNC** -- cannot be asyncio.create_task'd
4. **reap_stale_contexts() is one-shot** -- need a _reap_loop() wrapper
5. **PlanFailedEvent/PlanCancelledEvent do NOT exist as types** -- handlers receive dict payloads
6. **GapDetector manages its OWN contract_updated subscription** -- call `gap_detector.start()`, NOT manual subscribe
7. **SubStepObserver subscriptions are per-DAG** -- NOT registered in init(), managed by DAGExecutor
8. **OrchestratorService does NOT have event_port** -- MUST ADD to constructor
9. **ConcurrencyGuard.acquire() takes NO parameters** -- Protocol says ctx but real class doesn't
10. **discover_and_register() should have 500ms timeout** -- SPEC-10 async MCP handling
11. **_mailbox_loop is 1ms polling** -- `await asyncio.sleep(0.001)` when empty
12. **Step 2 is a no-op in V1** -- in-process adapters don't need connection setup
13. **WorkflowEngine has property accessors** -- `.registry`, `.scheduler`, `.gap_detector`
14. **Factory must be updated** -- add event_port kwarg to OrchestratorService construction

---

## 20. Import Map for init()

```python
# Already imported in orchestrator_service.py:
import asyncio          # NEW -- for create_task, wait_for, sleep
import logging
import time
from typing import Dict, List, Optional
from uuid import uuid4

# Already imported (types):
from k1.orchestrator.config import OrchestratorConfig
from k1.orchestrator.types import (
    CommittedPlan, PendingHILContext, PendingPlanContext,
    ProcessingContext, ProcessResult,
    ...
)

# NEW imports needed:
from k1.orchestrator.events import (
    PLAN_READY, PLAN_FAILED, PLAN_CANCELLED,
    HIL_OVERRIDE_RESPONSE, HIL_FALLBACK_RESPONSE,
)
from k1.orchestrator.ports.event_subscription_port import IEventSubscriptionPort
from k1.orchestrator.connectors.mcp_registrar import RegistrationResult
from k1.fabric.ports.event_port import SubscriptionHandle
```

---

## 21. Files to Modify

| File | Change |
|------|--------|
| `k1/orchestrator/orchestration/orchestrator_service.py` | Add init(), event handlers, _reap_loop, _mailbox_loop, new slots, event_port param |
| `k1/orchestrator/factory.py` | Add event_port= to OrchestratorService() constructor call |
| `tests/k1/orchestrator/test_factory.py` | May need updates if factory tests verify constructor kwargs |
| `tests/k1/orchestrator/test_orchestrator_service.py` | Add event_port= to all service construction calls |
| `tests/k1/orchestrator/test_init_lifecycle.py` | NEW: init() lifecycle tests |

---

## 22. Test Strategy for init()

Per plan, init() tests should verify:

1. **Idempotency**: Calling init() twice is safe (second call is no-op)
2. **Port validation**: init() with None port raises RuntimeError
3. **Concurrency guard check**: init() with active guard raises AssertionError
4. **MCP discovery called**: discover_and_register() invoked, result logged
5. **MCP timeout**: If discover_and_register() takes > 500ms, init continues
6. **Workflows loaded**: registry.list_active() called
7. **Scheduler started**: WorkflowScheduler.start() called
8. **Events subscribed**: 5 subscriptions registered (PLAN_READY, PLAN_FAILED, PLAN_CANCELLED, HIL_OVERRIDE, HIL_FALLBACK)
9. **Gap detector started**: gap_detector.start() called
10. **Lifecycle monitoring started**: start_lifecycle_monitoring() called
11. **Reaper task created**: _reaper_task is not None
12. **Loop task created**: _loop_task is not None
13. **_initialized flag set**: True after init completes
14. **_running flag set**: True after init completes
15. **Elapsed time logged**: init.complete log emitted

---

## 23. Dependency Graph for init() Steps

```
Step 1: _validate_ports()
         |
Step 2: (no-op V1)
         |
Step 3: assert not concurrency_guard.active
         |
Step 4: await discover_and_register() [500ms timeout]
         |
Step 5: (commentary)
         |
Step 6: await workflow_engine.registry.list_active()
         |
Step 7: await workflow_engine.scheduler.start()
         |
Step 8: _subscribe_events() [sync, 5 subscriptions]
         |
Step 9: await gap_detector.start()
        connector_lifecycle.start_lifecycle_monitoring()
        self._reaper_task = create_task(_reap_loop())
         |
Step 10: self._loop_task = create_task(_mailbox_loop())
         |
         v
       _initialized = True
```

All steps are sequential (no parallelism within init).
Steps 4 and 6 do I/O (adapter calls).
Steps 7, 9, 10 create background tasks.
Step 8 is sync (subscribe calls are sync).
