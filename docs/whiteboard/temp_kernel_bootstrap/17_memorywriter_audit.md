# 17 — Epic 1.8: MemoryWriter Audit

> Generated from 2 parallel subagent code reads across `k1/memory_writer/`.
> MemoryWriter is the **cleanest component** — zero cross-module port imports, all 5 ports required, consistent Protocol pattern, and a proper anti-corruption layer for ModelHub.

---

## Summary Verdict

| Issue | What To Check | Verdict |
| ----- | ------------- | ------- |
| 1.8.1 | Read 5 port definitions | ✅ All 5 Protocol, `@runtime_checkable`, all-async, 11 methods, 371 LOC. Zero ABC usage |
| 1.8.2 | Read MemoryWriterFactory — create methods | ✅ 1 static method `create()`, all 5 ports required, 11-step pipeline wiring, 143 LOC |
| 1.8.3 | Read 5 production adapters + test bundle | ✅ 4 REAL + 1 SEMI-REAL. 5 Fake test doubles in single file. Zero null adapters |
| 1.8.4 | Check ModelHubAdapter — chat() vs execute() collision | ✅ CONTAINED — MW has own `IModelHubPort(chat())`, adapter translates to K1 `IModelHubPort(execute())` via anti-corruption layer |

---

## Package Structure

```
k1/memory_writer/
├── __init__.py
├── ARCHITECTURE.md
├── config.py                          (MWConfig)
├── context_assembly.py
├── events.py
├── fabric_registration.py
├── factory.py                         (143 LOC — MemoryWriterFactory)
├── invariants.py
├── place_resolver.py
├── service.py                         (MemoryWriterService)
├── types.py                           (ChatResponse, HealthStatus, Subscription)
├── adapters/
│   ├── __init__.py                    (re-export shim, 15 LOC)
│   ├── bridge_command_adapter.py      (73 LOC)
│   ├── event_subscription_adapter.py  (80 LOC)
│   ├── health_adapter.py             (54 LOC)
│   ├── model_hub_adapter.py          (120 LOC)
│   ├── session_read_adapter.py       (131 LOC)
│   └── test_adapters.py              (160 LOC — 5 Fake classes)
├── batch/
├── context/
├── envelope/
├── extraction/
├── filter/
├── health/
├── pipeline/
└── ports/
    ├── __init__.py                    (re-export, 34 LOC)
    ├── bridge_command_port.py         (78 LOC)
    ├── event_subscription_port.py     (88 LOC)
    ├── health_port.py                (48 LOC)
    ├── model_hub_port.py             (64 LOC)
    └── session_read_port.py          (93 LOC)
```

---

## Issue 1.8.1 — Port Definitions (5 Ports, 371 LOC)

All 5 ports follow identical convention: `Protocol` base, `@runtime_checkable`, all-async, docstrings on every method, `... # pragma: no cover` stubs. Zero ABC usage.

### MW-P1: `ISessionReadPort` (93 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `snapshot` | `async (sections: List[str])` | `Dict[str, Any]` |
| `read_section` | `async (name: str)` | `Optional[Dict[str, Any]]` |
| `list_sections` | `async ()` | `FrozenSet[str]` |

Invariants: MW-01 (read-only, NO write methods), MW-02 (lock-free <1ms P99).

### MW-P2: `IModelHubPort` (64 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `chat` | `async (messages: List[Dict[str, str]], budget_tokens: int, model_hint: str)` | `ChatResponse` |

Invariants: MW-06 (2000 token budget), MW-07 (RelevanceFilter must NOT use this port).

**CRITICAL:** This is MW's **own** `IModelHubPort` — NOT the same as `k1.model_hub.ports.hub_port.IModelHubPort` which has `execute()`. Two distinct protocols, same name, different packages.

### MW-P3: `IHealthPort` (48 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `is_ready` | `async ()` | `bool` |
| `health_check` | `async ()` | `HealthStatus` |

### MW-P4: `IEventSubscriptionPort` (88 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `subscribe` | `async (topic: str, handler: Callable[..., Coroutine])` | `Subscription` |
| `unsubscribe` | `async (subscription_id: str)` | `None` |
| `publish` | `async (topic: str, payload: dict)` | `None` |

**Note:** Bidirectional — serves both input (subscribe) and output (publish observability). Mild design smell but well-documented.

### MW-P5: `IBridgeCommandPort` (78 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `submit` | `async (topic: str, schema_uri: str, body: Dict)` | `None` |
| `submit_batch` | `async (envelopes: List[Dict])` | `None` |

Invariants: MW-03 (ONLY output path to K0), MW-09 (offline-safe with LocalOutbox), MW-10 (cognitive_trace_id required).

### Cross-Module Imports from Ports

| Port | Imports |
| ---- | ------- |
| `ISessionReadPort` | stdlib only |
| `IModelHubPort` | `k1.memory_writer.types.ChatResponse` |
| `IHealthPort` | `k1.memory_writer.types.HealthStatus` |
| `IEventSubscriptionPort` | `k1.memory_writer.types.Subscription` |
| `IBridgeCommandPort` | stdlib only |

**Zero cross-k1-module imports** — all port types come from `k1.memory_writer.types` or stdlib. The cleanest port boundary of any component audited.

---

## Issue 1.8.2 — MemoryWriterFactory (143 LOC)

**File:** `k1/memory_writer/factory.py`

### Single Public Method

```python
@staticmethod
def create(
    session_read_port: ISessionReadPort,
    model_hub_port: IModelHubPort,
    bridge_command_port: IBridgeCommandPort,
    event_subscription_port: IEventSubscriptionPort,
    health_port: IHealthPort,
    config: MWConfig | None = None,
) -> MemoryWriterService
```

**All 5 ports required** (None → `TypeError`). Config optional (defaults to `MWConfig()`).

### 11-Step Wiring Flow

| Step | Action | Components Created |
| ---- | ------ | ------------------ |
| 1 | Default config if None | `MWConfig()` |
| 2 | Port validation — `isinstance` check all 5 ports | — |
| 3 | Invariant validation — `validate_init_invariants()` | — |
| 4 | **Stage 1 — Filter** | `RelevanceFilter(config)` |
| 5 | **Stage 2 — Context** | `MWSessionReader`, `PlaceResolver([])`, `ContextBuilder` |
| 6 | **Stage 3 — Extraction** | `PromptLoader`, `MemoryWriterAgent(model_hub_port)`, `PersonResolver`, `ExtractionValidator`, `CircuitBreaker` |
| 7 | **Stage 4 — Envelope** | `FieldMapper`, `EnvelopeBuilder`, `PrivacyEnforcer` |
| 8 | **Stage 5 — Batch** | `DeltaAggregator`, `BatchEmitter(bridge_command_port)` |
| 9 | Wire pipeline | `MemoryWriterPipeline(…12 args…)` |
| 10 | Create dispatcher | `TurnDispatcher(pipeline, event_subscription_port)` |
| 11 | Return service | `MemoryWriterService(pipeline, dispatcher, circuit_breaker, health_port, config)` |

### Observations

- **Smallest factory** at 143 LOC — Bus (200), SSM (180), Fabric (350), ModelHub (280), Orchestrator (560), Planner (573), Concierge (860)
- **No internal helper classes** — flat function body, no nested dataclasses or PortBundle
- **5-stage pipeline** is MW-specific: Filter → Context → Extraction → Envelope → Batch
- `PlaceResolver([])` initialized empty — populated per-turn from SessionState at runtime
- `PromptLoader` loads from `…/prompts` directory (file system dependency)

---

## Issue 1.8.3 — Production Adapters (5) + Test Bundle (5 Fakes)

### Production Adapters

| # | Class | Port | Constructor | LOC | Classification |
| -- | ----- | ---- | ----------- | --- | -------------- |
| MW-A1 | `SessionReadAdapter` | `ISessionReadPort` | `(manager: Any)` | 131 | **SEMI-REAL** — wraps SSM, `Any`-typed |
| MW-A2 | `ModelHubAdapter` | MW `IModelHubPort` | `(hub: K1ModelHubPort, *, trace_id=None, consumer_id="memory_writer")` | 120 | **REAL** — full anti-corruption layer |
| MW-A3 | `HealthAdapter` | `IHealthPort` | `(circuit_breaker: Any, get_pending_count: Callable, get_started: Callable)` | 54 | **REAL** — composition of 3 callables |
| MW-A4 | `EventSubscriptionAdapter` | `IEventSubscriptionPort` | `(bus_adapter: Any)` | 80 | **REAL** — async→sync bridge for K1 Bus |
| MW-A5 | `BridgeCommandAdapter` | `IBridgeCommandPort` | `(command_port: Any)` | 73 | **REAL** — delegation + envelope translation |

**4 REAL + 1 SEMI-REAL = 5 total. Zero stubs.**

All production adapters use structural subtyping (no explicit `class Foo(IPort)` inheritance) — `@runtime_checkable` Protocol + `isinstance()` checks in factory.

4 of 5 adapters type their main dependency as `Any` to avoid import coupling. Only `ModelHubAdapter` uses a typed import (`K1ModelHubPort`).

### Test Adapters (5 Fakes in 1 file — 160 LOC)

**File:** `k1/memory_writer/adapters/test_adapters.py`

| Class | Port | Type | Capabilities |
| ----- | ---- | ---- | ------------ |
| `FakeSessionReadPort` | `ISessionReadPort` | Canned dict | Configurable sections, `fail_on` set raises `RuntimeError` |
| `FakeModelHubPort` | `IModelHubPort` | Canned response | Call capture (`.calls`), `fail=True` always raises, `fail_count=N` fails first N |
| `FakeBridgeCommandPort` | `IBridgeCommandPort` | Capture list | `.submitted` + `.batches` capture, `fail=True` raises |
| `FakeEventSubscriptionPort` | `IEventSubscriptionPort` | In-memory bus | Full subscribe/unsubscribe/publish cycle, `.published` capture |
| `FakeHealthPort` | `IHealthPort` | Configurable | `ready`, `healthy`, `circuit_open` constructor flags |

### Test Adapter Gaps

| Gap | Severity |
| --- | -------- |
| **No `reset()`/`clear()` on any Fake** — must create new instances per test | LOW |
| **`FakeSessionReadPort` missing `list_sections()` and `snapshot_all()`** — tests using full contract would `AttributeError` | MEDIUM |
| `FakeModelHubPort` returns `prompt_tokens=0`, `completion_tokens=0` — only `total_tokens` set | LOW |

### Null Adapters

**None.** Zero null adapter files anywhere under `k1/memory_writer/`. All 5 ports must be satisfied or tests use Fakes. No graceful degradation path.

---

## Issue 1.8.4 — ModelHubAdapter: chat() vs execute() (CRITICAL)

### The Two `IModelHubPort` Protocols

| Protocol | Package | Key Method | Purpose |
| -------- | ------- | ---------- | ------- |
| `IModelHubPort` | `k1.model_hub.ports.hub_port` | `execute(request: HubRequest) -> HubResponse` | K1-wide LLM gateway |
| `IModelHubPort` | `k1.memory_writer.ports.model_hub_port` | `chat(messages, budget_tokens, model_hint) -> ChatResponse` | MW-specific chat interface |

**Same name, different packages, different methods.**

### Anti-Corruption Layer Translation

```
MW pipeline calls:
    chat(messages, budget_tokens=2000, model_hint="cheapest")
         │
         ▼
ModelHubAdapter.chat():
    1. messages: List[Dict] → List[Message]
    2. Extract system_prompt from first message (if role=="system")
    3. Build ChatPayload(messages, system_prompt)
    4. Build RequestConstraints(max_tokens=budget, timeout_ms=60000,
           priority=BACKGROUND, temperature=0.7, provider_preference=...)
    5. Build HubRequest(capability=CHAT, payload, constraints, trace_id)
         │
         ▼
K1 ModelHub.execute(request: HubRequest) → HubResponse
         │
         ▼
ModelHubAdapter extracts:
    6. content = response.result["content"] or str(result)
    7. tokens = response.metadata.usage
    8. model = response.metadata.model_id
    9. latency_ms from monotonic timer
         │
         ▼
Returns ChatResponse(content, total_tokens, prompt_tokens,
                      completion_tokens, model, latency_ms)
```

### Collision Verdict: **CONTAINED**

- MW defines its own `IModelHubPort` with `chat()` — completely decoupled from K1's `IModelHubPort`
- `ModelHubAdapter` imports K1's port as `K1ModelHubPort` (explicit alias) to avoid name collision
- Translation is 1:1 — `chat()` → `execute(HubRequest(CHAT, ChatPayload, …))` → `ChatResponse`
- No `execute()` method exists on MW's port or adapter — MW never speaks K1 ModelHub's language directly
- `consumer_id="memory_writer"` tags all requests for observability/quota tracking
- `priority=BACKGROUND` ensures MW extraction never competes with interactive Concierge requests

---

## Cross-Module Import Map

| Source | Imports From |
| ------ | ------------ |
| ports/*.py | `k1.memory_writer.types` only (or stdlib) |
| `SessionReadAdapter` | `k1.sessionstate.sizetracker.ALL_SECTIONS` (lazy) |
| `ModelHubAdapter` | `k1.model_hub.ports.hub_port.IModelHubPort`, `k1.model_hub.types.*` (6 types) |
| `EventSubscriptionAdapter` | `k1.memory_writer.types.Subscription` |
| `BridgeCommandAdapter` | `bridge.core.envelope_builder.CommandEnvelope` (lazy) |
| `HealthAdapter` | `k1.memory_writer.types.HealthStatus` |
| `factory.py` | 16 internal MW submodules only |

**Observation:** MW has the lowest cross-module coupling of any component. Ports import nothing from outside MW. Only 2 adapters have external deps (`SessionReadAdapter` → SSM, `ModelHubAdapter` → ModelHub types).

---

## Anomalies & Risks

| # | Anomaly | Severity | Impact |
| -- | ------- | -------- | ------ |
| 1 | **Two `IModelHubPort` protocols** with same name in different packages | **MEDIUM** | Grep confusion — developers must know which is which. Alias import in adapter is correct |
| 2 | **`FakeSessionReadPort` incomplete** — missing `list_sections()` + `snapshot_all()` | **MEDIUM** | Tests using full ISessionReadPort contract will `AttributeError` |
| 3 | **`HealthAdapter.last_extraction_ms` hardcoded `0.0`** | **LOW** | Placeholder — either not tracked yet or wired elsewhere |
| 4 | **No null adapters** — all 5 ports mandatory | **LOW** | No graceful degradation (MW either works or doesn't). Acceptable for Tier-2 per-session component |
| 5 | **4 of 5 adapters typed `Any`** for constructor deps | **LOW** | Intentional decoupling trade — `isinstance` checks in factory provide runtime safety |
| 6 | **`EventSubscriptionAdapter._sync_wrapper` swallows errors** on missing event loop | **LOW** | Could silently drop events in edge cases |
| 7 | **`PlaceResolver([])` initialized empty** | **LOW** | Not a bug — populated per-turn from SessionState at runtime |
| 8 | **No explicit Protocol inheritance** on any adapter class | **LOW** | Idiomatic structural subtyping — works with `@runtime_checkable` but less visible |

---

## Comparison With Prior Epics

| Dimension | Bus (1.1) | SSM (1.2) | Fabric (1.3) | ModelHub (1.4) | Orch (1.5) | Planner (1.6) | Concierge (1.7) | **MemWriter (1.8)** |
| --------- | --------- | --------- | ------------ | -------------- | ---------- | -------------- | --------------- | ------------------- |
| Port style | Protocol | ABC | Protocol | Protocol | Protocol | Protocol | Protocol (5+4) | **Protocol** |
| Port count | 3 | 5 | 6 | 7 | 9 | 7 | 9 | **5** |
| Port files | 3 | 5 | 6 | 7 | 9 | 7 | 1 file | **5 files** |
| Methods | 7 | ~20 | ~18 | 15 | 55 | 15 | ~12 | **11** |
| Factory LOC | ~200 | ~180 | ~350 | ~280 | 560 | 573 | 860 | **143** |
| Factory methods | 4 | 3 | 3 | 3 | 4 | 4 | 4 | **1** |
| Prod adapters | 2 | 4+5 stub | 9 REAL | 3+6 semi | 9 REAL | 6+1 semi | 3+2+3 | **4 REAL + 1 SEMI** |
| Null adapters | 0 | 0 | 0 | 0 | 0 | 0 | 4 | **0** |
| Test doubles | 3 MW | 1 | 0 | 0 | 4M+4T | 7 | 8 | **5 Fakes** |
| Cross-module deps | low | low | low | medium | high | high | very high | **lowest** |

**MemoryWriter is the simplest and cleanest component** — smallest factory (143 LOC), fewest ports (5), lowest cross-module coupling, and the most consistent adapter pattern. The ModelHub anti-corruption layer is the most well-designed boundary in the codebase.
