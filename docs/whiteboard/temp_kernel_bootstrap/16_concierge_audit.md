# 16 — Epic 1.7: Concierge Audit

> Generated from 4 parallel subagent code reads across `k1/concierge/`.
> Concierge is the most complex component — 28 subdirectories, no standard ports/ folder, all 9 ports in a single file, heavy deferred imports, and TWO parallel runtime types.

---

## Summary Verdict

| Issue | What To Check | Verdict |
|-------|--------------|---------|
| 1.7.1 | 8 Protocol definitions in ports.py | ✅ Actually **9 ports** in 155 LOC — 5 new Protocols + 4 re-exported aliases. All `@runtime_checkable` |
| 1.7.2 | ConciergeFactory + PortBundle | ✅ 860 LOC, `PortBundle(frozen)` with 5 required + 3 optional, 16-step wiring, `create_with_ports()` takes 8 params |
| 1.7.3 | 8 production adapters | ✅ 3 REAL + 2 SEMI-REAL + 3 RE-EXPORT (thin shims to canonical classes) |
| 1.7.4 | 4 null adapters | ✅ All 4 exist — safe no-op for two-tier bootstrap. Return None/empty/False, never raise |
| 1.7.5 | 8 test adapters | ✅ All 8 exist — mixed quality: 4 proper mocks, 2 re-exports, 1 factory fn, 1 in-memory |
| 1.7.6 | SnapshotStateRead adapter | ✅ `bind(snapshot)` / `read_sections()` pattern — late-bound per-request for shared Planner |
| 1.7.7 | bootstrap.py — start_kernel() | ⚠️ 743 LOC, 25-step flow, imports from `poc.k1_poc.main.boot()`, `KernelRuntime` mutable dataclass with 24 fields (many `Any`) |
| 1.7.8 | session.py — ConciergeRuntime | ⚠️ 448 LOC, **duplicates ~200 LOC** from bootstrap.py. TWO parallel runtime types — `KernelRuntime` vs `ConciergeRuntime` |
| 1.7.9 | Config files | ✅ `KernelConfig` (29 LOC, mutable, no validation) vs `ConciergeConfig` (91 LOC, frozen, validated). Config loader is a re-export shim to `poc/` |

---

## Issue 1.7.1 — Port Definitions (9 Ports in 1 File)

**File:** `k1/concierge/ports.py` — **155 LOC**

Unlike all other components (which have `ports/` directories with 1 file per port), Concierge defines ALL ports in a single file. 5 are new `Protocol` classes, 4 are re-exported aliases.

### New Protocols (5)

| Port | `@runtime_checkable` | Methods | Sync/Async |
|------|---------------------|---------|------------|
| **IInputPort** | Yes | `async receive() -> Envelope`, `has_buffered() -> bool` | Mixed |
| **IOutputPort** | Yes | `async send(envelope: Envelope) -> None` | Async |
| **IStatePort** | Yes | `get_section(name: str) -> Any`, `get_snapshot() -> dict` | **Sync** |
| **IDispatchPort** | Yes | `async dispatch_direct(CapabilityRequest) -> CapabilityResult`, `async dispatch_envelope(TaskEnvelope) -> AggregatedResult` | Async |
| **IMemoryPort** | Yes | `async recall(query, memory_types, max_results) -> list[dict]` | Async |

### Re-Exported Aliases (4)

| Alias | Source Class | Source Module |
|-------|-------------|---------------|
| `IClassificationPort` | `Phase1Pipeline` | `k1.concierge.fsm.phase1` |
| `ILLMPort` | `IModelHubPort` | `k1.model_hub.ports.hub_port` |
| `IDeltaPort` | `IBus` | `k1.bus.ports.bus` |
| `IFabricPort` | `IFabricPort` | `k1.concierge.fabric.ports` |

**Total: 9 ports, ~12 methods.**

### Cross-Module Imports from ports.py

| Source | Types |
|--------|-------|
| `k1.bus.envelope` | `Envelope` |
| `k1.bus.ports.bus` | `IBus` |
| `k1.concierge.fsm.phase1` | `Phase1Pipeline`, `Phase1Result` |
| `k1.concierge.orchestrator.types` | `AggregatedResult`, `TaskEnvelope` |
| `k1.concierge.fabric.ports` | `IFabricPort` |
| `k1.fabric.types` | `CapabilityRequest`, `CapabilityResult` |
| `k1.model_hub.ports.hub_port` | `IModelHubPort` |
| `k1.model_hub.types` | `HubChunk`, `HubRequest`, `HubResponse` |

**Key observation:** `IFabricPort` is in `__all__` but NOT in `PortBundle` — it's passed separately as `fabric_port: Any` to the factory.

---

## Issue 1.7.2 — ConciergeFactory (860 LOC)

**File:** `k1/concierge/factory.py`

### PortBundle (frozen dataclass)

```python
@dataclass(frozen=True)
class PortBundle:
    # REQUIRED (ValueError if None)
    delta:          IDeltaPort
    input_:         IInputPort
    output:         IOutputPort
    state:          IStatePort
    llm:            ILLMPort
    # OPTIONAL (default None → null/no-op)
    classification: IClassificationPort | None = None
    dispatch:       IDispatchPort | None = None
    memory:         IMemoryPort | None = None
```

**5 required + 3 optional = 8 ports.** `validate_required()` raises `ValueError` for missing required ports.

### Factory Methods

| Method | Signature | Returns |
|--------|-----------|---------|
| `create_with_ports` | `(cls, *, bus, router, front_mailbox, back_mailbox, ports: PortBundle, config, fabric_port, orchestrator)` | `ConciergeRuntime` |
| `create_standalone` | `(cls)` | `ConciergeRuntime` |
| `create_for_testing` | `(cls, *, overrides, config)` | `ConciergeRuntime` |
| `create_request_scope` | `(runtime, *, trace_id, device_id, task_id)` | `ConciergeSession` (static) |

**`init()` NOT called** — factory returns un-started runtime. Caller must `await runtime.start()`.

### 16-Step `_construct_concierge` Wiring

| Step | Action | Guard |
|------|--------|-------|
| 1 | `ConciergeController(bus, router)` — FSM | — |
| 2 | Wire Phase1 classification → FSM | `ports.classification` |
| 3 | `LedgerWriter` + `InMemoryLedgerStore` → FSM | `config.enable_ledger` |
| 4 | Wire history sink from state | try/except |
| 5 | Wire session state → FSM | — |
| 6 | Extract `recall_fn` from `ports.memory.recall` | — |
| 7 | Build 2× `ToolContext` (front + back) | — |
| 8 | Build front + back `ToolDispatcher` | — |
| 9 | `ExperienceLayer` | `config.enable_experience` |
| 10 | `DeltaAggregator` + `DeltaApplicator` | `config.enable_delta` |
| 11 | `HILCoordinator` → 3 bus callbacks → FSM | `config.enable_hitl` |
| 12 | `WeaveBatcher` + `WeavePolicy` + `UserActivityTracker` → FSM | `hasattr` guards |
| 13 | `DeadLetterConsumer` | `config.enable_dead_letter_consumer` |
| 14 | `OrchestratorStub` (with 3 internal adapters) or passed-in orchestrator | `orchestrator` or `config.enable_orchestrator` |
| 15 | Subscribe front events | `router is not None` |
| 16 | Build and return `ConciergeRuntime` (18 named args) | — |

### 3 Private Helper Adapters (inside factory.py)

| Class | Purpose |
|-------|---------|
| `_FabricGatewayAdapter` | Translates POC orchestrator types ↔ K1 fabric types |
| `_StateReadAdapter` | Wraps session_state for orchestrator snapshot/read |
| `_DeltaEmitAdapter` | Routes delta events through aggregator or bus |

### 20+ Deferred Imports
Heavy in-function imports to avoid circular deps — covers FSM, delta, ledger, experience, tools, orchestrator, protocols.

---

## Issue 1.7.3 — Production Adapters (8)

| # | Adapter | Port | Constructor | LOC | Classification |
|---|---------|------|-------------|-----|---------------|
| CO-A1 | `BusInputAdapter` | `IInputPort` | `(bus: IBus)` | 48 | **REAL** — subscribes TOPIC_USER_INPUT, buffers in asyncio.Queue |
| CO-A2 | `BusOutputAdapter` | `IOutputPort` | `(bus: IBus)` | 31 | **REAL** — thinnest adapter, `bus.publish(envelope)` |
| CO-A3 | `UltraBERTPhase1Pipeline` | `IClassificationPort` | *(re-export)* | 12 | **RE-EXPORT** → `k1.concierge.fsm.ultrabert_phase1` |
| CO-A4 | `ModelHubPOCBridge` | `ILLMPort` | *(re-export)* | 12 | **RE-EXPORT** → `k1.concierge.llm.model_hub_bridge` |
| CO-A5 | `SSMStateAdapter` | `IStatePort` | `(session_state: Any)` | 41 | **SEMI-REAL** — duck-typed SSM wrapper |
| CO-A6 | `FabricDispatchAdapter` | `IDispatchPort` | `(fabric_port: Any, orchestrator: Any = None)` | 40 | **REAL** — tier routing: LOW→Fabric, MED/HIGH→Orchestrator |
| CO-A7 | `BusFactory` | `IDeltaPort` | *(re-export)* | 15 | **RE-EXPORT** → `k1.bus.factory.BusFactory` |
| CO-A8 | `RecallMemoryAdapter` | `IMemoryPort` | `(recall_fn: Callable)` | 30 | **SEMI-REAL** — wraps closure |

**Key observations:**
- 3 adapters are pure **re-exports** (thin shim files for import ergonomics)
- 2 adapters typed as `Any` — correctness deferred to runtime
- `FabricDispatchAdapter` unifies two dispatch tiers: `dispatch_direct()` → Fabric, `dispatch_envelope()` → Orchestrator (raises `RuntimeError` if orchestrator not wired)

---

## Issue 1.7.4 — Null Adapters (4)

| # | Adapter | Port | LOC | Returns |
|---|---------|------|-----|---------|
| CO-N1 | `NullSessionStateReaderAdapter` | `ISessionStateReader` (Fabric) | 37 | `None`, `{}`, empty `SessionSnapshot` |
| CO-N2 | `NullEventSubscriptionAdapter` | `IEventSubscriptionPort` (Orch) | 37 | dummy `SubscriptionHandle("null")`, `False`, silent pass |
| CO-N3 | `NullDeltaBusAdapter` | `IDeltaBusPort` (Fabric) | 30 | silent pass (drop all) |
| CO-N4 | `NullBridgeWriteAdapter` | `IBridgeWritePort` (Orch) | 43 | silent pass, `None`, `[]` |

**Purpose:** Two-tier bootstrap — shared Fabric/Orchestrator singletons need port dependencies at construction before any session exists. Null adapters satisfy constructor contracts with safe no-ops.

**Note:** CO-N1 was already identified in Epic 1.3 audit as existing but NOT wired into FabricFactory — kernel bootstrap must inject it manually for S3 shared Fabric.

---

## Issue 1.7.5 — Test Adapters (8)

| # | Adapter | Port | LOC | Type |
|---|---------|------|-----|------|
| CO-T1 | `TestInputAdapter` | `IInputPort` | 37 | In-memory asyncio.Queue + inject helpers |
| CO-T2 | `TestOutputAdapter` | `IOutputPort` | 36 | Capture list + `get_sent()` filter |
| CO-T3 | `StubPhase1Pipeline` | `IClassificationPort` | ~97 | Re-export from `fsm/phase1.py`, keyword-based |
| CO-T4 | `TestModelHubBridge` | `ILLMPort` | ~90 | Re-export, extends `ModelHubPOCBridge` with scripting |
| CO-T5 | `InMemoryStateAdapter` | `IStatePort` | 38 | In-memory dict with `seed()` / `seed_dict()` |
| CO-T6 | `MockDispatchAdapter` | `IDispatchPort` | 53 | Scriptable results + call capture |
| CO-T7 | `create_test_bus()` | `IDeltaPort` | 16 | ⚠️ Factory fn returning real `LocalBus` — NOT a test double |
| CO-T8 | `MockMemoryAdapter` | `IMemoryPort` | 41 | In-memory + type filtering + call log |

### Coverage Matrix

| Port | Prod | Test | Null |
|------|------|------|------|
| `IInputPort` | CO-A1 | CO-T1 | — |
| `IOutputPort` | CO-A2 | CO-T2 | — |
| `IClassificationPort` | CO-A3 | CO-T3 | — |
| `ILLMPort` | CO-A4 | CO-T4 | — |
| `IStatePort` | CO-A5 | CO-T5 | — |
| `IDispatchPort` | CO-A6 | CO-T6 | — |
| `IDeltaPort` | CO-A7 | CO-T7 ⚠️ | — |
| `IMemoryPort` | CO-A8 | CO-T8 | — |
| `ISessionStateReader` (Fabric) | — | — | CO-N1 |
| `IDeltaBusPort` (Fabric) | — | — | CO-N3 |
| `IEventSubscriptionPort` (Orch) | — | — | CO-N2 |
| `IBridgeWritePort` (Orch) | — | — | CO-N4 |

**Gap:** CO-T7 is NOT a true test double — it's the same production `LocalBus`. No scripting, no assertion capture.

---

## Issue 1.7.6 — SnapshotStateRead Adapter

**File:** `k1/concierge/adapters/snapshot_state_read.py` — **51 LOC**

```python
class SnapshotStateReadAdapter:
    def __init__(self) -> None  # no args — late-bound
    def bind(snapshot: Optional[SessionSnapshot]) -> None
    async def read_sections(sections: List[str], trace_id: str = "") -> SessionSnapshot
```

- Solves SIM-GAP-49: shared Planner serves ALL sessions but `IStateReadPort` was session-locked
- **Before each pipeline run**, `PlannerAgent` calls `bind(request.context)` to set active snapshot
- `read_sections()` filters bound snapshot to requested section names
- If unbound, returns empty `SessionSnapshot()`
- Classification: **REAL** (proper typed contract, just late-bound)

---

## Issue 1.7.7 — bootstrap.py (743 LOC)

**File:** `k1/concierge/kernel/bootstrap.py`

### `start_kernel(config: KernelConfig | None = None) -> KernelRuntime`

**25-step flow:**

1. Load config (`KernelConfig()` default)
2. Boot infrastructure via **`poc.k1_poc.main.boot()`** ← critical POC dependency
3. Create LLM model (TestModelHubBridge or GeminiConciergeAdapter)
4. Create SessionState (standalone or testing)
5. Create capability registry (`create_demo_registry()`)
6. Create Fabric (FabricFactory with POC mock adapters, register 40 POC capabilities)
7. Create Ledger (if enabled)
8. Create FSM (`ConciergeController`)
9. Wire Phase1 pipeline (UltraBERT or stub)
10. Wire Ledger → FSM
11. Wire FSM ↔ session state
12. Build recall_fn (keyword-matching in-memory, ~100 LOC)
13. Create ToolContexts (front + back)
14. Create dispatchers
15. Assemble `KernelRuntime` dataclass
16. Wire ExperienceLayer
17. Wire DeltaAggregator + DeltaApplicator
18. Wire HILCoordinator (3 bus callbacks)
19. Wire WeaveBatcher
20. Wire WeavePolicy + UserActivityTracker
21. Wire DeadLetterConsumer
22. Wire OrchestratorStub (with 3 private adapter classes)
23. Subscribe front events
24. Start mailbox consumer (`asyncio.create_task`)
25. Return `KernelRuntime`

### KernelRuntime (mutable dataclass, 24+ fields)

| Field | Type |
|-------|------|
| `config` | `KernelConfig` |
| `bus` | `IBus` |
| `router` | `IMailboxRouter` |
| `adapter` | `Any` |
| `front_mailbox` / `back_mailbox` | `IMailbox` |
| `session_state` | `Any` |
| `capability_registry` | `Any` |
| `model` | `Any` |
| `fsm` | `ConciergeController` |
| `front_dispatcher` / `back_dispatcher` | `Any` |
| `experience_layer` | `Any` (optional) |
| `delta_aggregator` / `delta_applicator` | `Any` (optional) |
| `hitl_coordinator` | `Any` (optional) |
| `orchestrator` | `Any` (optional) |
| `front_subscriptions` / `back_subscriptions` | `list[Any]` |
| `consumer_task` | `asyncio.Task | None` |
| `ledger` / `ledger_store` | `Any` (optional) |
| `dead_letter_consumer` | `Any` (optional) |
| `started` | `bool` |

**Extra undeclared fields set via `setattr`:** `weave_batcher`, `weave_policy`, `activity_tracker`.

---

## Issue 1.7.8 — session.py (448 LOC)

**File:** `k1/concierge/session.py`

### ConciergeRuntime (class, NOT dataclass)

```python
def __init__(self, *, bus, router, front_mailbox, back_mailbox, fsm, model,
             session_state, front_dispatcher, back_dispatcher, front_subscriptions,
             front_ctx=None, back_ctx=None, experience_layer=None,
             delta_aggregator=None, hitl_coordinator=None, orchestrator=None,
             ledger=None, ledger_store=None, dead_letter_consumer=None)
```

**Key methods:**
- `async start()` — creates mailbox consumer task, idempotent
- `async stop()` — reverse teardown (cancel consumer → flush → close)
- `inject(envelope)` — user input entry point (publishes to bus)

### ConciergeSession (`@dataclass`, per-request scope)

```python
@dataclass
class ConciergeSession:
    runtime: ConciergeRuntime
    trace_id: str  # uuid hex
    front_ctx: Any
    back_ctx: Any
    active_device_id: str | None = None
    active_task_id: str | None = None
```

- `inject(*, hil_coordinator, dispatch, memory)` — late-binds optional ports
- `async close()` — clears per-request caches

### CRITICAL: Two Parallel Runtime Types

| | `KernelRuntime` (bootstrap.py) | `ConciergeRuntime` (session.py) |
|--|------|------|
| Type | `@dataclass` (mutable) | Regular class |
| Fields | 24+ (many `Any`) | 19 constructor params |
| Start | `_mailbox_consumer()` standalone fn | `self._mailbox_consumer()` method |
| Stop | `stop_kernel(runtime)` standalone fn | `runtime.stop()` method |
| Used by | `runner.py`, `chat_repl.py` | `factory.py` |
| Code duplicated | ~200 LOC | ~200 LOC |

**~200 LOC duplicated** between bootstrap and session: `_mailbox_consumer`, `_tick_experience`, `_build_experience_context`, stop logic.

---

## Issue 1.7.9 — Config Files

### KernelConfig (29 LOC, mutable, NO validation)

```python
@dataclass
class KernelConfig:
    ordered_bus: bool = True
    capture_bus: bool = False
    test_mode: bool = False
    tool_tier: str = "LOW"
    session_mode: str = "standalone"
    session_id: str | None = None
    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    auto_start_consumer: bool = True
    enable_ledger: bool = True
    enable_dead_letter_consumer: bool = True
    seed_memories: list[dict] = []
```

### ConciergeConfig (91 LOC, frozen, validated)

```python
@dataclass(frozen=True)
class ConciergeConfig:
    tool_tier: str = "LOW"                    # validated: {"LOW", "MED", "HIGH"}
    enable_experience: bool = True
    enable_delta: bool = True
    enable_hitl: bool = True
    enable_orchestrator: bool = True
    auto_start_consumer: bool = True
    enable_ledger: bool = True
    enable_dead_letter_consumer: bool = True
    session_id: str | None = None
    seed_memories: list[dict] = []
    phase1_pipeline: str = "stub"             # validated: {"stub", "ultrabert"}
    phase1_warmup: bool = False
    delta_batch_window_ms: int = 100          # validated: > 0
    dead_letter_enabled: bool = False
```

Constructors: `from_kernel_config()`, `from_dict()`, `for_testing()`, `with_overrides()`.

### Config Loader (16 LOC)
Pure re-export shim → `poc.k1_poc.config.loader` → loads `defaults.yaml`.

### `tool_tier` Mismatch
`KernelConfig` accepts any string (no validation). `ConciergeConfig` validates `{"LOW", "MED", "HIGH"}`. `runner.py` argparse offers `"MEDIUM"/"HIGH"/"CRISIS"` which don't match `ConciergeConfig`'s allowed set.

---

## Full Package Structure

```
k1/concierge/                              (28 subdirectories)
├── __init__.py                            (empty)
├── ports.py                               (155 LOC — 9 ports)
├── factory.py                             (860 LOC — ConciergeFactory + PortBundle)
├── session.py                             (448 LOC — ConciergeRuntime + ConciergeSession)
├── adapters/                              (22 files: 8 prod + 4 null + 1 snapshot + 8 test + __init__)
├── actors/                                (front, back, back_pool, back_router, ready_queue, shared)
├── affective/, empathy/, rhythm/          (placeholder — empty __init__.py)
├── bus/                                   (builders, deserialize, setup, topics)
├── compression/                           (episodic_compressor)
├── config/                                (kernel.py, concierge.py, loader.py, defaults.yaml)
├── delta/                                 (aggregator, applicator, emitters, overflow, snapshot_reader, writer_registry)
├── docs/, docs_depricated/                (design docs, audit artifacts)
├── events/                                (base, conversation, hitl, mutation, pool, registry, task, validator, weave)
├── experience/                            (affective_mirror, anticipatory, emotional, layer, narrative, proactive, rhythm)
├── fabric/                                (capability_registry, contract_converter, demo_capabilities, poc_bridge)
├── fsm/                                   (arbiter, controller, states, transitions, ultrabert, dead_letter, idempotency, etc.)
├── identity/                              (dynamic_identity)
├── kernel/                                (bootstrap.py, runner.py, chat_repl.py)
├── ledger/                                (projections, recovery, store, writer)
├── llm/                                   (gemini_adapter, model_hub_adapter, model_hub_bridge, model_selection, test adapters)
├── obs/                                   (9 metrics files: actor, alerts, arbiter, fsm, hitl, phase1, react, weave)
├── orchestrator/                          (degradation, interfaces, ports, routing, stub, types)
├── prompt/                                (affect, back_prompt, builder, clarify, domain_rules, mode, scenarios, sections)
├── protocols/                             (cancellation, delivery, hitl_*, opp_pipeline, suspension_*, task_lease, trust, weave_*)
├── react/                                 (history, loop)
├── scheduler/                             (proactive_scheduler)
├── task/                                  (bundled_executor, classifier, complexity, dependency_queue, dispatch, envelope_bridge, intent, parallel_safety, receiver, tools, topics)
└── types/                                 (empty __init__.py)
```

---

## Anomalies & Risks

| # | Anomaly | Severity | Impact |
|---|---------|----------|--------|
| 1 | **Two parallel runtime types** — `KernelRuntime` (dataclass) vs `ConciergeRuntime` (class) | **HIGH** | Unclear which is canonical. ~200 LOC duplicated. Must converge for MS-2 |
| 2 | **bootstrap.py calls `poc.k1_poc.main.boot()`** | **HIGH** | Hard dependency on POC layer violates clean architecture boundary |
| 3 | **KernelConfig has NO validation** | **MEDIUM** | `tool_tier` mismatch: runner.py offers "MEDIUM"/"CRISIS", ConciergeConfig validates {"LOW","MED","HIGH"} |
| 4 | **`KernelRuntime` has undeclared fields** via `setattr` | **MEDIUM** | `weave_batcher`, `weave_policy`, `activity_tracker` not in dataclass definition |
| 5 | **24+ fields typed as `Any`** in both runtime types | **MEDIUM** | Defeats static analysis entirely |
| 6 | **PortBundle has 8 ports, ports.py has 9** — `IFabricPort` excluded from bundle | **MEDIUM** | Passed separately as `fabric_port: Any`, losing type safety |
| 7 | **CO-T7 `create_test_bus()` returns real `LocalBus`** — not a test double | **LOW** | No call capture, no assertion API |
| 8 | **3 adapter files are pure re-exports** (CO-A3, CO-A4, CO-A7) | **LOW** | Import convenience, not real adapters |
| 9 | **20+ deferred imports** in factory.py | **LOW** | Circular dep avoidance — works but fragile |
| 10 | **`factory.py.bak` left in source** | **LOW** | Dead file |
| 11 | **Placeholder packages** — `affective/`, `empathy/`, `rhythm/`, `types/` empty | **LOW** | Not implemented yet |
| 12 | **`chat_repl.py` mutates `runtime.model` directly** after boot | **LOW** | Breaks encapsulation |
| 13 | **Config loader is triple-indirection** shim chain | **LOW** | k1.concierge.config → poc.k1_poc.config → loader |

---

## How Kernel Is Started Today

### `runner.py` (61 LOC) — Headless daemon
```
python -m k1.concierge.kernel.runner [--test-mode] [--tool-tier LOW|MEDIUM|HIGH|CRISIS]
```
Constructs `KernelConfig` → `start_kernel(cfg)` → blocks on `stop_event` (SIGINT/SIGTERM).

### `chat_repl.py` (214 LOC) — Interactive REPL
```
python -m k1.concierge.kernel.chat_repl [--model-hub] [--no-test-mode]
```
Always boots `test_mode=True`, then swaps `runtime.model` at composition root. Interactive `input()` loop publishing envelopes.

---

## Comparison With Prior Epics

| Dimension | Bus (1.1) | SSM (1.2) | Fabric (1.3) | ModelHub (1.4) | Orch (1.5) | Planner (1.6) | **Concierge (1.7)** |
|-----------|----------|----------|-------------|---------------|-----------|--------------|-------------------|
| Port style | Protocol | ABC | Protocol | Protocol | Protocol | Protocol | **Protocol (5 new + 4 alias)** |
| Port count | 3 | 5 | 6 | 7 | 9 | 7 | **9** |
| Port files | 3 | 5 | 6 | 7 | 9 | 7 | **1 file** |
| Factory LOC | ~200 | ~180 | ~350 | ~280 | 560 | 573 | **860** |
| Prod adapters | 2 | 4+5 stub | 9 REAL | 3+6 semi | 9 REAL | 6+1 semi | **3 REAL + 2 SEMI + 3 RE-EXPORT** |
| Null adapters | 0 | 0 | 0 | 0 | 0 | 0 | **4** |
| Test doubles | 3 MW | 1 | 0 | 0 | 4M+4T | 7 test | **8 test** |
| Subdirectories | 3 | 2 | 5 | 4 | 5 | 4 | **28** |

**Concierge is the MOST COMPLEX component** — 28 subdirectories, the largest factory (860 LOC), 4 unique null adapters for two-tier bootstrap, 3 re-export adapters, TWO parallel runtime types, and hard POC dependency. MS-2 (KernelService) will need to replace both `KernelRuntime` and `ConciergeRuntime` with a unified design.
