# Epic 1.4: ModelHub Audit — Complete Findings

**Date:** 2026-04-11
**Status:** COMPLETE — All 4 issues audited
**Verdict:** Core hub is **PRODUCTION READY** (standalone mode). 6 of 9 adapters are SEMI-REAL (functional in-memory, no production backend). API collision CONTAINED by adapters.

---

## Summary Verdict

| Aspect | Status | Notes |
| ------ | ------ | ----- |
| Port definitions (7 Protocols) | ✅ COMPLETE | All Protocol + @runtime_checkable, 15 methods total |
| ModelHubFactory | ✅ COMPLETE | 3 methods, _HubCore lives inside factory.py |
| LLMRequestBusAdapter (MH-A4) | ✅ REAL | Pure delegation decorator over IModelHubPort |
| BusEnvelopeDeserializer (MH-A9) | ✅ REAL | Full bus wiring, only adapter with external k1.bus imports |
| SessionStateProdAdapter (MH-A2) | ✅ REAL | Wraps actual SessionStateManager |
| HealthReportAdapter (MH-A5) | ✅ REAL | Per-component aggregation logic |
| SessionStateReadAdapter (MH-A1) | ⚠️ SEMI-REAL | In-memory dict, dev/test only |
| PrometheusAdapter (MH-A3) | ⚠️ SEMI-REAL | In-memory accumulator, no prometheus_client |
| EventBusAdapter (MH-A6) | ⚠️ SEMI-REAL | In-memory pub/sub, not K1 bus |
| CredentialStoreAdapter (MH-A7) | ⚠️ SEMI-REAL | Env vars only, no OS keychain/Vault |
| ConfigAdapter (MH-A8) | ⚠️ SEMI-REAL | In-memory dict, no YAML loading |
| execute() vs chat() collision | ✅ CONTAINED | MemoryWriter has own IModelHubPort with chat(), adapters translate correctly |

**Total LOC:** ~3,500+ across model_hub package (ports + adapters + services + factory)
**Stubs found:** ZERO (none raise NotImplementedError). 6 are semi-real (functional but in-memory).

---

## Issue 1.4.1: Port Definitions (7 Protocols) ✅

**Key finding: All 7 ports use Protocol (structural) + @runtime_checkable. Zero ABCs. Zero concrete defaults. Mixed sync/async.**

| ID | Port | #Methods | Sync/Async | Supporting Types | LOC |
| -- | ---- | -------- | ---------- | ---------------- | --- |
| MH-P1 | IModelHubPort | 5 | all async | — (uses types.py) | ~55 |
| MH-P2 | IEventPort | 2 | all async | Subscription | ~46 |
| MH-P3 | IStateReadPort | 1 | all async | StateSnapshot | ~37 |
| MH-P4 | IMetricsPort | 1 | all sync | — | ~31 |
| MH-P5 | IConfigPort | 2 | all sync | ConfigSubscription | ~38 |
| MH-P6 | ICredentialPort | 2 | all async | — | ~29 |
| MH-P7 | IHealthPort | 2 | all sync | HealthReport | ~38 |

### MH-P1: IModelHubPort (`k1/model_hub/ports/hub_port.py`, ~55 LOC)

| Method | Signature |
| ------ | --------- |
| `execute` | `async (self, request: HubRequest) -> HubResponse` |
| `stream_execute` | `async (self, request: HubRequest) -> AsyncIterator[HubChunk]` |
| `discover_capabilities` | `async (self) -> Dict[CapabilityType, List[str]]` |
| `discover_models` | `async (self, capability: CapabilityType \| None = None) -> List[ModelInfo]` |
| `health` | `async (self) -> HubHealthReport` |

**Canonical API:** `execute()` + `stream_execute()` with `HubRequest` envelopes. **No `chat()` method.** Chat is expressed as `HubRequest(capability=CapabilityType.CHAT, payload=ChatPayload(...))`.

### MH-P2: IEventPort (`k1/model_hub/ports/event_port.py`, ~46 LOC)

| Method | Signature |
| ------ | --------- |
| `publish` | `async (self, topic: str, payload: Any) -> None` |
| `subscribe` | `async (self, topics: List[str], handler: Callable[[str, Any], Awaitable[None]]) -> Subscription` |

Supporting: `Subscription` frozen dataclass (`subscription_id`, `topics`).

**Note:** Async handler signature `Callable[[str, Any], Awaitable[None]]` — different from Fabric's sync handler.

### MH-P3: IStateReadPort (`k1/model_hub/ports/state_read_port.py`, ~37 LOC)

| Method | Signature |
| ------ | --------- |
| `read` | `async (self, sections: List[str]) -> StateSnapshot` |

Supporting: `StateSnapshot` frozen dataclass (`sections: Dict[str, Any]`).

**Design invariant MH-01:** NO write methods. Read-only by design.

### MH-P4: IMetricsPort (`k1/model_hub/ports/metrics_port.py`, ~31 LOC)

| Method | Signature |
| ------ | --------- |
| `emit` | `(self, metric_name: str, value: float, labels: Dict[str, Any] \| None = None) -> None` |

**Sync, fire-and-forget.** Only sync port with a single method.

### MH-P5: IConfigPort (`k1/model_hub/ports/config_port.py`, ~38 LOC)

| Method | Signature |
| ------ | --------- |
| `get` | `(self, key: str) -> Any` |
| `watch` | `(self, key: str, callback: Callable[[str, Any], None]) -> ConfigSubscription` |

Supporting: `ConfigSubscription` frozen dataclass (`subscription_id`, `key`).

**Both sync.** `watch` enables hot-reload callbacks.

### MH-P6: ICredentialPort (`k1/model_hub/ports/credential_port.py`, ~29 LOC)

| Method | Signature |
| ------ | --------- |
| `get_key` | `async (self, provider_id: str) -> str` |
| `refresh_key` | `async (self, provider_id: str) -> str` |

**Design invariant MH-02:** ALL API keys in CredentialStore, never in config/env/manifest.

### MH-P7: IHealthPort (`k1/model_hub/ports/health_port.py`, ~38 LOC)

| Method | Signature |
| ------ | --------- |
| `report_health` | `(self, component: str, status: HealthStatus) -> None` |
| `check_health` | `(self) -> HealthReport` |

Supporting: `HealthReport` frozen dataclass (`component`, `status: HealthStatus`, `details`).

---

## Issue 1.4.2: ModelHubFactory ✅

### ModelHubFactory (`k1/model_hub/factory.py`, ~450 LOC)

**Key discovery: The main `IModelHubPort` implementation (`_HubCore`) lives INSIDE factory.py. There is no separate `hub.py` or `manager.py`.**

### _HubCore (implements IModelHubPort)

```
__init__(self, router: RequestRouter, registry: ProviderRegistry, health_adapter: HealthReportAdapter)
```

| Method | Delegates To |
| ------ | ------------ |
| `execute(request)` | `self._router.route(request)` |
| `stream_execute(request)` | `self._router.stream_route(request)` |
| `discover_capabilities()` | `self._registry.get_capability_index()` |
| `discover_models(capability?)` | `self._registry.list_providers()` + filter |
| `health()` | `self._health.check_health()` → `HubHealthReport` |

### Factory Methods (3)

| Method | Signature | DI Pattern |
| ------ | --------- | ---------- |
| `create_standalone` | `(config?, plugins?) -> IModelHubPort` | Zero injection — all defaults |
| `create_for_testing` | `(overrides?) -> Tuple[IModelHubPort, Dict[str, Any]]` | Full injection with test defaults, returns internals dict |
| `create_with_ports` | `(ports: Dict[str, Any], config?, plugins?) -> IModelHubPort` | Partial — only `credential_port` required |

### `create_standalone` Wiring (11 steps)

1. `CredentialStoreAdapter()` (env vars)
2. `ProviderRegistry(cfg)`
3. `CircuitBreakerManager()`, `RateLimiter(cfg.rate_limit_headroom_pct)`
4. `CostTracker()`, `ResponseCache(cfg)`, `BudgetEnforcer(cfg)`
5. `HealthReportAdapter()`, `_DefaultHealthQuery(health_adapter)`
6. `CapabilityRouter(registry, circuit_breaker, rate_limiter, health_monitor)`
7. `ModelSelector()`
8. `NormalizationLayer()`
9. `ProviderDispatcher(circuit_mgr, rate_limiter, credential_port, plugins)`
10. `RequestRouter(capability_router, model_selector, budget_enforcer, response_cache, normalization, dispatcher, cost_tracker, audit_logger)`
11. Returns `_HubCore(router, registry, health_adapter)`

**Ports NOT used in standalone:** IEventPort, IStateReadPort, IMetricsPort, IConfigPort, IHealthPort — none wired. Standalone is minimal.

### Services Pipeline (12 services in `k1/model_hub/services/`)

`audit_logger`, `budget_enforcer`, `capability_router`, `circuit_breaker_manager`, `cost_tracker`, `model_selector`, `normalization_layer`, `provider_dispatcher`, `provider_registry`, `rate_limiter`, `request_router`, `response_cache`

### Plugin System (6 providers in `k1/model_hub/plugins/`)

`openai_plugin`, `anthropic_plugin`, `google_plugin`, `ollama_plugin`, `vllm_plugin`, `test_plugin` — all implement `IProviderPlugin`.

### Cross-Component Imports: NONE

Factory imports only from `k1.model_hub.*`. Clean component boundary.

---

## Issue 1.4.3: All 9 Adapters ✅

### Production-Ready (3 fully REAL)

| ID | Adapter | Port | LOC | External Deps | Key Detail |
| -- | ------- | ---- | --- | ------------- | ---------- |
| MH-A2 | SessionStateProdAdapter | IStateReadPort | ~105 | SSM (via Any) | Per-section to_dict/get_metadata conversion |
| MH-A4 | LLMRequestBusAdapter | IModelHubPort | ~87 | IModelHubPort | Pure delegation decorator, error logging |
| MH-A9 | BusEnvelopeDeserializer | (utility) | ~290 | k1.bus.IBus, Envelope | Full bus wiring, JSON→HubRequest→execute→response→bus |

### Functional but In-Memory (6 SEMI-REAL)

| ID | Adapter | Port | LOC | Limitation |
| -- | ------- | ---- | --- | ---------- |
| MH-A1 | SessionStateReadAdapter | IStateReadPort | ~53 | Plain dict, dev/test only |
| MH-A3 | PrometheusAdapter | IMetricsPort | ~48 | In-memory accumulator, no prometheus_client |
| MH-A5 | HealthReportAdapter | IHealthPort | ~72 | Real aggregation logic (actually REAL) |
| MH-A6 | EventBusAdapter | IEventPort | ~56 | In-memory pub/sub, no K1 bus |
| MH-A7 | CredentialStoreAdapter | ICredentialPort | ~55 | Env vars only (MH_KEY_<ID>), no keychain |
| MH-A8 | ConfigAdapter | IConfigPort | ~60 | In-memory dict, no YAML loading |

**Correction:** MH-A5 (HealthReportAdapter) is actually REAL — it has genuine aggregation logic. The "SEMI-REAL" applies to the other 5.

**Zero pure stubs.** None raise `NotImplementedError`. All are functional, just with simpler backends than production would need.

### MH-A1 vs MH-A2 Comparison

| Aspect | MH-A1 SessionStateReadAdapter | MH-A2 SessionStateProdAdapter |
| ------ | ------------------------------ | ----------------------------- |
| Purpose | Dev/test | Production |
| Data source | Plain `Dict[str, Any]` | Real `SessionStateManager` |
| Section conversion | None (dict values as-is) | `to_dict()` → `get_metadata()` → raw dict |
| Error handling | Single try/except | Per-section with KeyError → omit |
| Uses `__slots__` | No | Yes |
| LOC | ~53 | ~105 |

### MH-A9 Data Flow (Bus Integration)

```
K1 Bus → BusEnvelopeDeserializer._on_envelope() → deserialize_hub_request()
       → LLMRequestBusAdapter.execute() → _HubCore(RequestRouter).execute()
       → HubResponse → serialize_hub_response() → bus.publish(TOPIC_HUB_RESPONSE)
```

Topics: `TOPIC_HUB_EXECUTE = "k1.model_hub.execute.v1"`, `TOPIC_HUB_RESPONSE = "k1.model_hub.execute.response.v1"`

---

## Issue 1.4.4: execute() vs chat() Collision ✅ CONTAINED

### The Collision

**Two different `IModelHubPort` protocols exist with the same class name but different interfaces:**

| Protocol | Location | Key Method | Signature |
| -------- | -------- | ---------- | --------- |
| ModelHub's `IModelHubPort` | `k1/model_hub/ports/hub_port.py` | `execute()` | `async (request: HubRequest) -> HubResponse` |
| MemoryWriter's `IModelHubPort` | `k1/memory_writer/ports/model_hub_port.py` | `chat()` | `async (messages, budget_tokens, model_hint) -> ChatResponse` |

### What Each Consumer Expects

| Consumer | Port Interface | Method Called | Translation |
| -------- | -------------- | ------------ | ----------- |
| **Fabric** | `IModelGatewayPort` → `ILLMHandle` | `generate(prompt, params)` | `ModelGatewayBridgeAdapter` builds `HubRequest(CHAT)` → calls `hub.execute()` ✅ |
| **MemoryWriter** | Own `IModelHubPort` | `chat(messages, budget_tokens, model_hint)` | `ModelHubAdapter` aliases `K1ModelHubPort`, builds `HubRequest(CHAT)` → calls `hub.execute()` ✅ |
| **Concierge** | K1's `IModelHubPort` | `execute(request: HubRequest)` | Direct — `ModelHubPOCBridge.execute()` translates to POC `generate()` ✅ |

### Verdict

**Collision EXISTS but is CONTAINED.** All adapters correctly translate:

- Fabric: `generate()` → `execute(HubRequest(CHAT))`
- MemoryWriter: `chat()` → `execute(HubRequest(CHAT))`
- Concierge: `execute()` directly

**Risk:** LOW. The MemoryWriter import aliases `K1ModelHubPort` to disambiguate. But the duplicate class name is a maintenance hazard — wrong import would cause silent protocol mismatch.

**Recommendation:** Rename MemoryWriter's port to `IMemoryWriterLLMPort` to eliminate ambiguity (MS-3 task).

---

## ModelHub Core Architecture

### _HubCore — The IModelHubPort Implementation

Lives inside `factory.py` (not a separate file). Thin facade over `RequestRouter`.

### Request Pipeline (12 services)

```
HubRequest → CapabilityRouter → ModelSelector → BudgetEnforcer
           → ResponseCache → NormalizationLayer → ProviderDispatcher
           → [Plugin.execute()] → HubResponse
           → CostTracker → AuditLogger → back to caller
```

With circuit breakers and rate limiting at ProviderDispatcher level.

### Plugin System

| Plugin | Provider |
| ------ | -------- |
| `openai_plugin` | OpenAI / Azure OpenAI |
| `anthropic_plugin` | Anthropic Claude |
| `google_plugin` | Google Gemini |
| `ollama_plugin` | Ollama (local) |
| `vllm_plugin` | vLLM (local) |
| `test_plugin` | Canned responses for testing |

All implement `IProviderPlugin(ABC)` from `k1/model_hub/plugins/base.py`.

### Sync vs Async

- **All IModelHubPort methods are async** (execute, stream_execute, discover_*, health)
- **IMetricsPort, IConfigPort, IHealthPort are sync** (fire-and-forget / config reads)
- **IEventPort, IStateReadPort, ICredentialPort are async**
- **Same sync/async bridging concern as Bus and SSM** for kernel wiring

---

## Cross-Component Dependencies

| From | To | Nature |
| ---- | -- | ------ |
| MH-A2 (SessionStateProd) | SessionStateManager | Duck-typed via `Any` |
| MH-A9 (BusEnvelopeDeserializer) | k1.bus.IBus, Envelope | Direct import — only external coupling |
| MH-A7 (CredentialStore) | os.environ | `MH_KEY_<PROVIDER_ID>` env vars |
| Factory | **NONE external** | Fully self-contained |

---

## Anomalies & Concerns

1. **_HubCore lives in factory.py.** No separate hub.py/manager.py. The main class is a private implementation detail of the factory. This is fine for encapsulation but unusual.

2. **6 secondary ports not wired in standalone.** `create_standalone()` only wires CredentialStore + Health. IEventPort, IStateReadPort, IMetricsPort, IConfigPort are not connected. ModelHub works without them but misses observability.

3. **ConfigAdapter.get() doesn't check env overrides.** Docstring says it does but implementation only reads from in-memory dict.

4. **EventBusAdapter has no unsubscribe().** The protocol defines `subscribe()` returning `Subscription` but the adapter stores subscriptions without removal support.

5. **No `isinstance()` checks at construction in adapters.** All rely on structural subtyping. Only `_validate_ports()` in the factory does runtime checks.

6. **PrometheusAdapter has no prometheus_client.** In-memory counter dict only. Production metrics require real Prometheus integration.

---

## Wiring Requirements for Kernel Bootstrap

### Tier-1 (Shared) — S2: ModelHub Creation

```python
# Standalone mode (works today)
model_hub = ModelHubFactory.create_standalone(config=model_hub_config)

# Production mode with bus integration
model_hub = ModelHubFactory.create_standalone(config=cfg, plugins=plugins)
deserializer = BusEnvelopeDeserializer(
    bus=shared_bus,
    adapter=LLMRequestBusAdapter(model_hub),
    loop=asyncio.get_event_loop(),
)
```

### Open Questions for MS-2

| # | Question | Impact |
| - | -------- | ------ |
| Q1 | Should secondary ports (Event, State, Metrics, Config) be wired in S2? | Observability vs complexity |
| Q2 | BusEnvelopeDeserializer needs event loop — who owns it? | Async lifecycle |
| Q3 | Rename MemoryWriter's IModelHubPort to eliminate name collision? | Maintenance safety |
| Q4 | PrometheusAdapter → real prometheus_client integration timing? | MS-3 or later? |

---

## 09_wiring_plan.md Status Updates

| Issue | Status | Verdict |
| ----- | ------ | ------- |
| 1.4.1 | ✅ | All 7 ports complete — Protocol + @runtime_checkable, 15 methods, mixed sync/async |
| 1.4.2 | ✅ | Factory complete — 3 methods, _HubCore inside factory, 11-step standalone wiring |
| 1.4.3 | ✅ | 3 REAL + 6 SEMI-REAL + 0 stubs. All functional, some need production backends |
| 1.4.4 | ✅ | CONTAINED — MemoryWriter has own IModelHubPort(chat()), adapters translate correctly |
