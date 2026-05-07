# 15 — Epic 1.6: Planner Audit

> Generated from 3 parallel subagent code reads across `k1/planner/`.

---

## Summary Verdict

| Issue | What To Check | Verdict |
|-------|--------------|---------|
| 1.6.1 | 7 port definitions | ✅ All 7 Protocol, all `@runtime_checkable`, 15 methods, ~537 LOC |
| 1.6.2 | PlannerFactory | ✅ 4 static methods, 10-step `_wire()`, 573 LOC, full DI + 3-pass validation |
| 1.6.3 | 7 production adapters | ✅ 6 REAL + 1 SEMI-REAL (MailboxAdapter: in-memory asyncio.Queue) |
| 1.6.4 | SessionStateAdapter = SnapshotStateReadAdapter pattern? | ✅ YES — `SessionStateReadAdapter(reader: Any, session_id: str)` — per-session, read-only |
| 1.6.5 | EventBusAdapter ≠ DeltaBusAdapter? | ✅ YES — separate classes, separate Fabric port types, CANNOT share instance |

---

## Issue 1.6.1 — Port Definitions (7 Ports)

All 7 use **`Protocol` (structural typing)** with **`@runtime_checkable`**. Zero ABC. Consistent with Bus/Fabric/ModelHub/Orchestrator.

| ID | Port | File | Sync/Async | Methods | LOC |
|----|------|------|-----------|---------|-----|
| PL-P1 | `ILLMPort` | `ports/llm_port.py` | ASYNC | 1 | 60 |
| PL-P2 | `IFabricRetrievalPort` | `ports/fabric_retrieval_port.py` | ASYNC | 2 | 83 |
| PL-P3 | `IStateReadPort` | `ports/state_read_port.py` | ASYNC | 1 | 64 |
| PL-P4 | `IBridgePort` | `ports/bridge_port.py` | ASYNC | 2 | 81 |
| PL-P5 | `IDeltaEmitPort` | `ports/delta_emit_port.py` | **SYNC** | 1 | 58 |
| PL-P6 | `IEventPort` | `ports/event_port.py` | **SYNC** | 3 | 101 |
| PL-P7 | `IMailboxPort` | `ports/mailbox_port.py` | **MIXED** | 5 | 90 |

**Total: 15 methods across 7 ports, ~537 LOC.**

### Key Signatures

**PL-P1 ILLMPort** (single LLM inference):

- `async execute(request: PlannerLLMRequest) -> PlannerLLMResponse`

**PL-P2 IFabricRetrievalPort** (Fabric capability/prompt discovery):

- `async discover_capabilities(domain, intent, safety_band, session_context, top_k) -> RetrievalResult`
- `async find_relevant_prompts(intent, domain, safety_band, top_k) -> RetrievalResult`

**PL-P3 IStateReadPort** (read-only session state — PLAN-01):

- `async read_sections(sections: List[str], trace_id: str = "") -> SessionSnapshot`

**PL-P4 IBridgePort** (K0 memory recall + plan persistence):

- `async recall(query, selectors, *, trace_id) -> RecallResponse`
- `async persist_plan(plan: CommittedPlan, *, trace_id) -> None`

**PL-P5 IDeltaEmitPort** (fire-and-forget delta stream, SYNC):

- `emit(delta: DeltaPayload) -> None`

**PL-P6 IEventPort** (full pub/sub, SYNC):

- `emit(topic: str, payload: Any) -> None`
- `subscribe(topic, handler) -> SubscriptionHandle`
- `unsubscribe(handle: SubscriptionHandle) -> bool`

**PL-P7 IMailboxPort** (MIXED sync/async, receive-side of Orchestrator→Planner):

- `async dequeue() -> PlanRequest` — blocks until available
- `async enqueue(request: PlanRequest) -> None` — raises `MailboxFullError`
- `async send_cancel(request_id: str) -> None`
- `drain() -> List[PlanRequest]` — SYNC, for shutdown
- `async micro_replan(request: MicroReplanRequest) -> CommittedPlan`

### Cross-Module Imports (ports importing outside `k1/planner/`)

| Port | External Import | Type |
|------|----------------|------|
| PL-P2 | `k1.fabric.types` | `RetrievalResult` |
| PL-P3 | `k1.fabric.ports.state_reader` | `SessionSnapshot` |
| PL-P4 | `k1.orchestrator.types` | `CommittedPlan` |
| PL-P6 | `k1.fabric.ports.event_port` | `SubscriptionHandle` |
| PL-P7 | `k1.orchestrator.types` | `CommittedPlan`, `MicroReplanRequest`, `PlanRequest` |

**Internal-only:** PL-P1 (ILLMPort), PL-P5 (IDeltaEmitPort) — zero external imports.

---

## Issue 1.6.2 — PlannerFactory (573 LOC)

**File:** `k1/planner/factory.py`

### Factory Methods (all `@staticmethod`, all `async`)

| Method | Signature | Returns |
|--------|-----------|---------|
| `create_standalone()` | `async (config=None) -> PlannerAgent` | All 7 ports default to Test*Adapter |
| `create_for_testing()` | `async (config=None, **overrides) -> (PlannerAgent, Dict)` | Returns agent + adapter dict |
| `create_with_ports()` | `async (*, llm, fabric, state, bridge, delta, event, mailbox, config=None) -> PlannerAgent` | All 7 required keyword-only |
| `create_production()` | `async (*, llm, fabric, state, bridge, delta, event, mailbox, config=None) -> PlannerAgent` | All 7 required keyword-only |

**`init()` / `start()` NOT called** — caller is responsible. Documented as intentional.

### 10-Step `_wire()` Sequence

| Step | Object | Dependencies |
|------|--------|-------------|
| 1 | `ToolCallRouter` | fabric_port, state_port, bridge_port, config |
| 2 | `HILCoordinator` | llm_port, event_port, config |
| 3 | `SketchService` | llm_port, tool_router, hil_coord |
| 4 | `ExpandService` | llm_port, tool_router |
| 5 | `ValidateService` | llm_port, fabric_port, hil_coord |
| 6 | `CommitService` | bridge_port, delta_port, event_port (**NO llm_port — PLAN-03**) |
| 7 | `PipelineController` | sketch, expand, validate, commit, delta_port, event_port, config |
| 8 | `PlannerAgent` | mailbox_port, pipeline, event_port, config |

### 3-Pass Port Validation

1. **Completeness:** all 7 slots non-None → `MissingPortError`
2. **Protocol compliance:** `isinstance(v, protocol)` → `InvalidPortError`
3. **Uniqueness:** `id()` comparison across all pairs → `DuplicatePortError`

### Config Validation — 10 bounds

`mailbox_max_depth >= 1`, `pipeline_timeout_ms > 0`, `max_tool_calls_per_plan >= 1`, `max_hil_rounds >= 0`, `total_token_budget > 0`, plus 4 per-stage timeouts and `shutdown_grace_period_ms`.

### Structural Enforcement

- **PLAN-01** (no state writes): `IStateReadPort` has only `read_sections()` — no write methods
- **PLAN-03** (no LLM in commit): `CommitService` gets bridge, delta, event — NOT llm_port
- **PLAN-06** (no execution): `IFabricRetrievalPort` has only discovery methods — no `execute()`

---

## Issue 1.6.3 — All 7 Production Adapters

| # | Adapter | Port | Constructor | LOC | Classification |
|---|---------|------|-------------|-----|---------------|
| PL-A1 | `LLMGatewayAdapter` | `ILLMPort` | `(llm_request_bus: ILLMRequestBus, consumer_id="planner")` | 121 | **REAL** — Model Hub bus dispatch |
| PL-A2 | `FabricRetrievalAdapter` | `IFabricRetrievalPort` | `(fabric_retrieval: Any, timeout_ms=50, max_retries=1)` | 123 | **REAL** — in-process Fabric call |
| PL-A3 | `SessionStateReadAdapter` | `IStateReadPort` | `(reader: Any, session_id: str)` | 113 | **REAL** — per-session read-only |
| PL-A4 | `BridgeAdapter` | `IBridgePort` | `(bridge_port: Any)` | 144 | **REAL** — K0 recall + persist |
| PL-A5 | `DeltaBusAdapter` | `IDeltaEmitPort` | `(delta_bus: Any, agent_id="planner")` | 78 | **REAL** — fire-and-forget deltas |
| PL-A6 | `EventBusAdapter` | `IEventPort` | `(event_port: Any)` | 89 | **REAL** — thin pub/sub passthrough |
| PL-A7 | `MailboxAdapter` | `IMailboxPort` | `(max_depth=5, priority_class="INTERACTIVE")` | 150 | **SEMI-REAL** — asyncio.Queue |

**Total: ~818 LOC across 7 adapters. All use structural conformance (no explicit inheritance).**

### Adapter Details

**PL-A1 LLMGatewayAdapter** — full V2 production path via Model Hub bus:

- Stamps `consumer_id` on request for cost attribution (MH-11)
- Coerces non-`PlannerLLMResponse` results
- Maps errors to `LLMTimeoutError`, `BudgetExceededError`, `AdapterException(DEGRADED)`
- Defines local `ILLMRequestBus` Protocol

**PL-A2 FabricRetrievalAdapter** — in-process method call to Fabric:

- 50ms timeout, 1 retry
- Degraded path returns empty `RetrievalResult()` — never raises
- No circuit breaker (in-process)

**PL-A3 SessionStateReadAdapter** — the SnapshotStateReadAdapter pattern:

- `reader` is `ISessionStateReader` (Fabric port 5.1.1), NOT `SessionStateManager`
- `session_id` bound at construction — one instance per session
- `read_sections()` calls reader synchronously despite being `async def`
- Extra `get_snapshot()` convenience method (not on port interface)

**PL-A4 BridgeAdapter** — K0 offline-tolerant:

- Checks `_bridge.is_available()` before every operation
- Offline: `recall()` → empty `RecallResponse`; `persist_plan()` → silent drop
- Uses `plan.to_dict()` if available, fallback to `str(plan)`

**PL-A5 DeltaBusAdapter** — wraps Fabric `IDeltaBusPort`:

- SYNC, fire-and-forget, never raises
- Pre-stamps `agent_id` at construction
- Maps `DeltaPayload` fields to `bus.emit_delta(agent_id, delta_type, section, data)`

**PL-A6 EventBusAdapter** — wraps Fabric `IEventPort`:

- SYNC, thin passthrough
- Planner and Fabric `IEventPort` interfaces are nearly identical (SS15.9)
- Subscribe in INIT, unsubscribe all handles on SHUTDOWN

**PL-A7 MailboxAdapter** — in-memory asyncio.Queue:

- Bounded FIFO (`max_depth=5`), single `INTERACTIVE` priority class
- `_cancel_set: Set[str]` for best-effort cancellation
- `_plan_lock: asyncio.Lock` serializes plans (V1 single-plan)
- `set_pipeline_controller()` injected post-construction by factory
- `micro_replan()` acquires `_plan_lock` directly, bypasses queue

---

## Issue 1.6.4 — SessionStateAdapter = SnapshotStateReadAdapter Pattern? **YES**

```python
class SessionStateReadAdapter:
    def __init__(self, reader: Any, session_id: str) -> None:
```

| Question | Answer |
|----------|--------|
| Follows SnapshotStateRead pattern? | **YES** — wraps reader, provides read-only access |
| What does constructor take? | `reader: Any` (typed `ISessionStateReader` per docs) + `session_id: str` |
| Per-session binding? | **YES** — `session_id` bound at construction, one instance per session |
| Write methods? | **NONE** — PLAN-01 enforced at type level |
| Reader sync/async? | Reader calls are **synchronous** despite adapter being `async def` |

**Kernel wiring implication:** For each session, create `SessionStateReadAdapter(reader=fabric_state_reader, session_id=sid)`. The `reader` is `ISessionStateReader` from Fabric (same type Fabric's `SessionStateReader` adapter wraps).

---

## Issue 1.6.5 — EventBusAdapter ≠ DeltaBusAdapter? **YES — Separate**

| Dimension | PL-A5 DeltaBusAdapter | PL-A6 EventBusAdapter |
|-----------|----------------------|----------------------|
| Port | `IDeltaEmitPort` (1 method) | `IEventPort` (3 methods) |
| Constructor | `(delta_bus: Any, agent_id="planner")` | `(event_port: Any)` |
| Wraps | Fabric `IDeltaBusPort` (5.1.6) | Fabric `IEventPort` (5.1.2) |
| Interface | `emit_delta(agent_id, delta_type, section, data)` | `emit(topic, payload)`, `subscribe()`, `unsubscribe()` |
| Direction | Write-only (fire-and-forget) | Bidirectional pub/sub |
| Purpose | Observability deltas | Control-plane events |
| Sync/Async | SYNC | SYNC |

**CANNOT share the same bus instance** — they wrap different Fabric port types (`IDeltaBusPort` vs `IEventPort`) with incompatible interfaces.

---

## PlannerAgent Core (733 LOC)

**File:** `k1/planner/planner_agent.py`

### Constructor

```python
def __init__(self, mailbox: IMailboxPort, pipeline: PipelineController,
             event_port: IEventPort, config: PlannerConfig) -> None
```

- Single-threaded async actor
- Owns dequeue loop, plan lock (`asyncio.Lock` — V1 single-plan), cancel set
- Lifecycle: INIT → RUNNING → SHUTDOWN

### PipelineController (1,301 LOC)

```python
def __init__(self, sketch, expand, validate, commit,
             delta_port: IDeltaEmitPort, event_port: IEventPort, config: PlannerConfig)
```

- 4-stage sequencing: SKETCH → EXPAND → VALIDATE → COMMIT
- Budget injection, cancel checking between stages
- Owns `PlanStateMachine` (11-state FSM, 273 LOC)

---

## Mailbox Flow (Orchestrator → Planner)

```
Orchestrator PlannerAdapter
    ─── enqueue(PlanRequest) ──→  MailboxAdapter._queue (asyncio.Queue)
                                       │
PlannerAgent dequeue loop              │
    ←── dequeue() ─────────────────────┘
    │
    └── acquires _plan_lock → PipelineController.execute()
```

- `micro_replan()` bypasses queue, acquires `_plan_lock` directly
- `send_cancel()` adds to `_cancel_set` — checked between pipeline stages

---

## PlannerConfig (203 LOC, frozen dataclass)

24 fields including:

- `mailbox_max_depth=5`, `pipeline_timeout_ms=45_000`
- Per-stage timeouts: sketch 8s, expand 5s, validate 3s, commit 1s
- Token budgets: sketch 2000, expand 1000, validate 500, total 3500
- Temperatures: sketch 0.7, expand 0.3, validate 0.2
- `max_tool_calls_per_plan=6`, `max_hil_rounds=2`
- `shutdown_grace_period_ms=5000`

---

## Test Adapters (7, under `tests/k1/planner/adapters/`)

| File | Class | Port | LOC |
|------|-------|------|-----|
| `test_mailbox_adapter.py` | `TestMailboxAdapter` | `IMailboxPort` | 124 |
| `test_llm_adapter.py` | `TestLLMAdapter` | `ILLMPort` | 185 |
| `test_fabric_retrieval_adapter.py` | `TestFabricRetrievalAdapter` | `IFabricRetrievalPort` | 139 |
| `test_state_read_adapter.py` | `TestStateReadAdapter` | `IStateReadPort` | 95 |
| `test_bridge_adapter.py` | `TestBridgeAdapter` | `IBridgePort` | 108 |
| `test_delta_adapter.py` | `TestDeltaAdapter` | `IDeltaEmitPort` | 73 |
| `test_event_adapter.py` | `TestEventAdapter` | `IEventPort` | 128 |

**All 7 ports have test doubles.** All live outside the production package in `tests/`.

---

## Full Package Structure

```
k1/planner/
├── __init__.py
├── ARCHITECTURE.md / planner.md / planner.mmd / planner_v2.mmd
├── config.py                    (203 LOC — PlannerConfig, 24 fields)
├── events.py                    (141 LOC — 10 topic constants)
├── factory.py                   (573 LOC — PlannerFactory)
├── pipeline_controller.py       (1,301 LOC — stage sequencing)
├── plan_fsm.py                  (273 LOC — 11-state FSM)
├── planner_agent.py             (733 LOC — async actor)
├── tracing.py                   (48 LOC)
├── types.py                     (819 LOC — frozen dataclasses)
├── ports/                       (7 ports, ~537 LOC)
├── adapters/                    (7 prod adapters, ~818 LOC)
├── services/
│   ├── tool_call_router.py      (352 LOC)
│   └── hil_coordinator.py       (482 LOC)
└── stages/
    ├── sketch_service.py        (1,132 LOC)
    ├── expand_service.py        (1,357 LOC)
    ├── validate_service.py      (1,063 LOC)
    └── commit_service.py        (454 LOC)
```

**Total Planner package: ~8,700+ LOC** (excluding tests).

---

## Anomalies & Risks

| # | Anomaly | Severity | Action |
|---|---------|----------|--------|
| 1 | `SessionStateReadAdapter` calls `reader.read_sections()` synchronously inside `async def` | Medium | May block event loop if reader is slow — verify reader is lock-free |
| 2 | `LLMGatewayAdapter` defines local `ILLMRequestBus` Protocol | Low | Could be shared type, but isolation prevents circular imports |
| 3 | All adapter constructor params typed `Any` (not their actual Protocol) | Medium | Type safety deferred to runtime. Factory's `_validate_ports()` compensates |
| 4 | `MailboxAdapter.set_pipeline_controller()` — post-construction injection | Low | Two-phase init, same pattern as Orchestrator's ExecutionMonitor |
| 5 | `PlannerAgent.start()` not called by factory | Medium | Caller must `asyncio.create_task(agent.start())` — easy to forget |
| 6 | `DeltaBusAdapter` and `EventBusAdapter` both SYNC but ports they wrap (Fabric) are also SYNC | Low | Consistent, no async bridging needed |
| 7 | No mock adapters in production package | Low | Test adapters live in `tests/` — clean separation |

---

## Comparison With Prior Epics

| Dimension | Bus (1.1) | SSM (1.2) | Fabric (1.3) | ModelHub (1.4) | Orch (1.5) | **Planner (1.6)** |
|-----------|----------|----------|-------------|---------------|-----------|------------------|
| Port style | Protocol | ABC | Protocol | Protocol | Protocol | **Protocol** |
| Port count | 3 | 5 | 6 | 7 | 9 | **7** |
| Factory LOC | ~200 | ~180 | ~350 | ~280 | 560 | **573** |
| Prod adapters | 2 | 4+5 stub | 9 REAL | 3+6 semi | 9 REAL | **6 REAL + 1 SEMI** |
| Test doubles | 3 middleware | 1 test | 0 | 0 | 4 mock + 4 test | **7 test (in tests/)** |
| Core LOC | ~800 | ~2,430 | ~1,400 | ~1,100 | 2,257 | **733 agent + 1,301 pipeline** |
| Cross-module imports | 0 | 1 | 0 | 1 | 3 | **5 (3 fabric, 2 orchestrator)** |

**Planner has the MOST cross-module imports (5)** — heavily coupled to both Fabric types and Orchestrator types. It also has the **largest stage pipeline** (4 stages, ~4,006 LOC in services/stages).
