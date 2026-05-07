# Model Hub — Architecture Reference (E-0.4)

> **Generated**: Code scan of `k1/model_hub/` — 35+ source files, 44 test files, 1 diagram.
> **Diagram source**: [model_hub.mmd](model_hub.mmd) (680 lines)
> **ADRs**: 0001b, 0027, 0027c, 0027d

---

## §1 Port Surface (I-0.4.1)

7 Protocol ports, 15 methods total. All `@runtime_checkable Protocol` — pure structural subtyping, zero ABC/abstractmethod usage.

### Port Matrix

| Port | File | Direction | Async | Methods | Co-types | External Deps |
|------|------|-----------|:-----:|:-------:|----------|---------------|
| `IModelHubPort` | `ports/hub_port.py` | Inbound | 5/5 | 5 | 0 | `k1.model_hub.types` |
| `IEventPort` | `ports/event_port.py` | Both | 2/2 | 2 | `Subscription` | stdlib |
| `IStateReadPort` | `ports/state_read_port.py` | Inbound | 1/1 | 1 | `StateSnapshot` | stdlib |
| `IMetricsPort` | `ports/metrics_port.py` | Outbound | 0/1 | 1 | 0 | stdlib |
| `IConfigPort` | `ports/config_port.py` | Inbound | 0/2 | 2 | `ConfigSubscription` | stdlib |
| `ICredentialPort` | `ports/credential_port.py` | Inbound | 2/2 | 2 | 0 | stdlib |
| `IHealthPort` | `ports/health_port.py` | Outbound | 0/2 | 2 | `HealthReport` | `k1.model_hub.types` |

### Port Signatures

**IModelHubPort** (THE single gateway — MH-16):

```
execute(request: HubRequest) → HubResponse
stream_execute(request: HubRequest) → AsyncIterator[HubChunk]
discover_capabilities() → Dict[CapabilityType, List[str]]
discover_models(capability: CapabilityType | None = None) → List[ModelInfo]
health() → HubHealthReport
```

**IEventPort**:

```
publish(topic: str, payload: Any) → None
subscribe(topics: List[str], handler: Callable[[str, Any], Awaitable[None]]) → Subscription
```

**IStateReadPort** (MH-01 — read-only, NO write methods):

```
read(sections: List[str]) → StateSnapshot
```

**IMetricsPort** (sync, fire-and-forget):

```
emit(metric_name: str, value: float, labels: Dict[str, Any] | None = None) → None
```

**IConfigPort** (sync):

```
get(key: str) → Any
watch(key: str, callback: Callable[[str, Any], None]) → ConfigSubscription
```

**ICredentialPort** (MH-02 — keys NEVER in manifest):

```
get_key(provider_id: str) → str
refresh_key(provider_id: str) → str
```

**IHealthPort** (sync):

```
report_health(component: str, status: HealthStatus) → None
check_health() → HealthReport
```

### Co-defined Port Types

| Type | Port | Fields |
|------|------|--------|
| `Subscription` | IEventPort | `subscription_id: str`, `topics: List[str]` |
| `StateSnapshot` | IStateReadPort | `sections: Dict[str, Any]` |
| `ConfigSubscription` | IConfigPort | `subscription_id: str`, `key: str` |
| `HealthReport` | IHealthPort | `component: str`, `status: HealthStatus`, `details: Dict[str, str]` |

### Package Exports (`ports/__init__.py`)

11 symbols: `IModelHubPort`, `IEventPort`, `IStateReadPort`, `IMetricsPort`, `IConfigPort`, `ICredentialPort`, `IHealthPort`, `Subscription`, `StateSnapshot`, `ConfigSubscription`, `HealthReport`.

### Adapter Conformance Matrix

| Port | Production Adapter | Sync/Async | Error Default |
|------|--------------------|:----------:|---------------|
| `IModelHubPort` | `LLMRequestBusAdapter` | async | re-raise (execute), `HubHealthReport(UNHEALTHY)` (health) |
| `IEventPort` | `EventBusAdapter` | async | log + swallow |
| `IStateReadPort` | `SessionStateReadAdapter` | async | `StateSnapshot({})` |
| `IMetricsPort` | `PrometheusAdapter` | sync | log + swallow |
| `IConfigPort` | `ConfigAdapter` | sync | `None` |
| `ICredentialPort` | `CredentialStoreAdapter` | async | `""` |
| `IHealthPort` | `HealthReportAdapter` | sync | `HealthReport(UNHEALTHY)` |

**All 7 adapters import ONLY from `k1.model_hub` internals + stdlib.** Zero cross-component imports (no k0, no k1.bus, no k1.sessionstate). Clean hexagonal — external wiring deferred to composition root.

**Universal error pattern**: log exception, return safe default, never crash the hub. Only exception: `LLMRequestBusAdapter.execute/stream_execute` logs then re-raises.

**No locks or semaphores in any adapter.** 3 sync, 4 async. All currently in-memory implementations.

---

## §2 Internal Architecture (I-0.4.2)

### Type System (`types.py` — Layer 0)

**Enums (8)**:

- `CapabilityType` (15 members): CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH, MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS, IMAGE_GEN, WEB_SEARCH, CODE_EXEC
- `Priority` (3): REALTIME (10s), INTERACTIVE (30s), BACKGROUND (60s)
- `FinishReason` (5): STOP, TOOL_CALLS, LENGTH, ERROR, SAFETY
- `HealthStatus` (3): HEALTHY, DEGRADED, UNHEALTHY
- `CircuitState` (3): CLOSED, OPEN, HALF_OPEN
- `BudgetDecision` (3): ALLOW, ALLOW_DEGRADED, REJECT
- `PlacementType` (3): remote, local_gpu, local_cpu
- `ModelTier` (3): FAST, STANDARD, PREMIUM

**Request/Response Envelope**:

- `HubRequest`: `capability: CapabilityType`, `payload: Any`, `constraints: RequestConstraints`, `trace_id: str` (MH-03: must be non-empty), `idempotency_key: Optional[str]`, `request_id: str = uuid4()`
- `RequestConstraints`: `max_tokens: int = 65536`, `timeout_ms: int = 30000`, `priority: Priority = INTERACTIVE`, `temperature: float = 0.7`, `model_preference: Optional[ModelPreference]`, `provider_preference: Optional[str]`, `cost_limit: Optional[float]`, `consumer_id: str = ""`
- `HubResponse`: `result: Any`, `metadata: ResponseMetadata`
- `ResponseMetadata`: `request_id`, `model_id`, `provider_id`, `usage: TokenUsage`, `cost_usd`, `latency_ms`, `cache_hit`, `capability`, `trace_id`, `fallback_used`, `finish_reason`
- `HubChunk`: `content: str`, `done: bool`, `metadata: Optional[ResponseMetadata]`, `tool_calls: Optional[List[ToolCallResult]]`

**15 Capability Payloads** (one per CapabilityType): `ChatPayload`, `ToolCallPayload`, `StructuredOutputPayload`, `ReasonPayload`, `EmbedPayload`, `VisionPayload`, `BatchPayload`, `ModeratePayload`, `TokenCountPayload`, `CachePromptPayload`, `AudioInputPayload`, `TTSPayload`, `ImageGenPayload`, `WebSearchPayload`, `CodeExecPayload`.

**Error Hierarchy** (7 exceptions): `ModelHubError` → `ProviderError`, `BudgetExceededError`, `NoEligibleProviderError`, `RateLimitError`, `CircuitOpenError`, `HubTimeoutError`, `ValidationError`.

### 12 Internal Services

#### Core LLM Call Flow (6 services)

**RequestRouter** — THE single entry point (MH-16), 9-step pipeline:

1. `_validate()` — CapabilityType + trace_id (MH-03)
2. `BudgetEnforcer.check()` — hard reject on REJECT (MH-04, MH-08)
3. Priority → timeout classification (MH-15)
4. `CapabilityRouter.route()` → eligible providers (MH-06, MH-18)
5. `ModelSelector.select()` → primary + fallback chain
6. `ResponseCache.get()` — cache check (MH-09)
7. `NormalizationLayer.normalize()` → NormalizedRequest
8. `ProviderDispatcher.dispatch()` → ProviderResponse
9. Post-process: denormalize, cache put, cost track, audit log, metrics

Constructor: `capability_router`, `model_selector`, `budget_enforcer`, `response_cache`, `normalization_layer`, `dispatcher`, `cost_tracker?`, `audit_logger?`, `metrics_port?`

**CapabilityRouter** — 5-step filtering:

1. Registry capability index lookup (MH-18)
2. Model-level capability filter
3. Circuit breaker filter (skip OPEN)
4. Rate limit filter (skip exhausted)
5. Health filter (skip UNHEALTHY)

Returns `List[EligibleProvider]`. Co-defines 3 query protocols: `ICircuitBreakerQuery`, `IRateLimiterQuery`, `IHealthQuery`.

**ModelSelector** — multi-dimension weighted scoring:

- 5 dimensions: cost, latency, preference, placement, health
- Weights vary by Priority:
  - REALTIME: lat=0.5, cost=0.1, pref=0.2, health=0.2
  - INTERACTIVE: lat=0.3, cost=0.2, pref=0.3, health=0.2
  - BACKGROUND: cost=0.5, lat=0.1, pref=0.1, health=0.3
- Cost rules: BACKGROUND → cheapest always; budget>80% → cheapest non-REALTIME; budget>95% → cheapest ALL
- Output: `ModelChoice(provider_id, model_id, fallback_chain[max 3], score)`

**ProviderDispatcher** — dispatch with fallback:

- Pipeline per provider: CB acquire → rate limit acquire → plugin.execute()
- 1 retry per provider, then next in fallback chain (max depth 3)
- Plugin crash → `except Exception` → record failure → fallback (MH-17)
- Co-defines: `DispatchResult(response, provider_id, latency_ms, fallback_used, attempts)`

**NormalizationLayer** — stateless bidirectional transform:

- 15 capability extractors (dispatch table `_CAPABILITY_EXTRACTORS`)
- `normalize(HubRequest, target_provider_id) → NormalizedRequest`
- `denormalize(ProviderResponse, original_request, ...) → HubResponse`

**ProviderRegistry** — in-memory capability index:

- `register(manifest, plugin)`, `unregister(provider_id)`
- `get_providers_for_capability(cap) → List[ProviderInfo]` — O(1) lookup
- Hot-reload support (rebuild index on re-register)
- Co-defines: `ProviderInfo(provider_id, capabilities, models, placement_type, health_status)`

#### Supporting Services (6 services)

| Service | Key Methods | Invariant | Config |
|---------|-------------|-----------|--------|
| `BudgetEnforcer` | `check(HubRequest) → BudgetCheckResult`, `track(HubResponse)`, `reset_daily()` | MH-04, MH-08 | `daily_budget_usd=$5` |
| `CircuitBreakerManager` | `get_state()`, `acquire()`, `record_success()`, `record_failure()` | MH-05 | `threshold=3, window=60s, cooldown=30s` |
| `CostTracker` | `compute_cost(usage, model_spec)`, `track(...)` | MH-07 | manifest cost tables |
| `RateLimiter` | `has_capacity()`, `acquire()` + `_TokenBucket` | MH-12 | `headroom=80%` |
| `ResponseCache` | `get()`, `put()`, `should_cache()`, `build_cache_key()` | MH-09 | `max=1000, ttl=300s` |
| `AuditLogger` | `log(request, response)`, `log_error(request, error)` | MH-11 | none |

**Cache skip rules**: TOOL_CALL, BATCH, MODERATE capabilities; temperature > 0.9; streaming requests.

**⚠️ ResponseCache thread-safety**: docstring claims "lock-free reads, write lock for put + eviction" but **no actual locks exist** in implementation. OrderedDict ops not thread-safe.

### Plugin Architecture (`plugins/`)

**IProviderPlugin** (7-method `@runtime_checkable Protocol`):

```
initialize(manifest: ProviderManifest) → None
supports(capability: CapabilityType) → bool
execute(request: NormalizedRequest) → ProviderResponse
stream_execute(request: NormalizedRequest) → AsyncIterator[ProviderChunk]
estimate_tokens(messages: List[Message]) → int
health_check() → ProviderHealth
close() → None
```

**Plugin data types**: `NormalizedRequest`, `ProviderResponse`, `ProviderChunk`, `ProviderHealth`.

**5 Production Plugins**:

| Plugin | Capabilities | API | Auth | Placement |
|--------|-------------|-----|------|-----------|
| `OpenAIPlugin` | 14 (all except CODE_EXEC) | chat.completions + others | Bearer | remote |
| `AnthropicPlugin` | 7 (CHAT, TOOL_CALL, STRUCTURED, REASON, VISION, TOKEN_COUNT, CACHE_PROMPT) | /v1/messages | x-api-key | remote |
| `GooglePlugin` | 9 (CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, WEB_SEARCH, CODE_EXEC, TOKEN_COUNT) | google-genai SDK | API key | remote |
| `VLLMPlugin` | 4 (CHAT, TOOL_CALL, STRUCTURED, VISION) | OpenAI-compat /v1/* | Optional Bearer | local_gpu |
| `OllamaPlugin` | 4 (CHAT, TOOL_CALL, VISION, EMBED) | /api/chat, /api/embed | none | local_cpu |

**TestProviderPlugin**: fully configurable fake — response text, tokens, latency, fail count, capabilities. Records all calls.

### Manifest Schema (`manifest.py`)

**ProviderManifest** (frozen): `provider_id`, `display_name`, `plugin_class`, `api_base`, `auth: AuthConfig`, `capabilities: List[CapabilityType]`, `models: List[ModelSpec]`, `circuit_breaker: CircuitBreakerConfig`, `health_check: HealthCheckConfig`, `concurrency: ConcurrencyConfig`, `rate_limits: RateLimitConfig`, `placement: PlacementConfig`.

**ModelSpec**: `id`, `capabilities`, `cost_per_1m_input`, `cost_per_1m_output`, `max_context=128000`, `max_output`, `supports_streaming=True`, `supports_parallel_tools`, `embedding_dimensions`, `rate_limit_rpm`, `rate_limit_tpm`, `tier: ModelTier=STANDARD`.

`load_manifest(path) → ProviderManifest` — loads YAML, parses all sub-structures.

### Events (`events.py`)

11 event topics, 11 payload dataclasses:

| Topic | Payload | Key Fields |
|-------|---------|------------|
| `k1.model_hub.request.received.v1` | `RequestReceivedPayload` | request_id, consumer_id, capability, budget_remaining_pct, trace_id |
| `k1.model_hub.request.routed.v1` | `RequestRoutedPayload` | request_id, provider_id, model_id, capability, trace_id |
| `k1.model_hub.response.complete.v1` | `ResponseCompletePayload` | request_id, tokens_used, latency_ms, cost_usd, cache_hit, trace_id |
| `k1.model_hub.cache.hit.v1` | `CacheHitPayload` | request_id, cache_key, capability, age_ms, trace_id |
| `k1.model_hub.provider.failure.v1` | `ProviderFailurePayload` | request_id, provider_id, error_type, will_fallback, trace_id |
| `k1.model_hub.fallback.triggered.v1` | `FallbackTriggeredPayload` | request_id, from_provider, to_provider, reason, trace_id |
| `k1.model_hub.circuit.state.v1` | `CircuitStatePayload` | provider_id, old_state, new_state, failure_count |
| `k1.model_hub.budget.alert.v1` | `BudgetAlertPayload` | tenant_id, level (WARNING\|EXCEEDED), pct, action |
| `k1.model_hub.provider.health.v1` | `ProviderHealthPayload` | provider_id, status, latency_p50, error_rate |
| `k1.model_hub.provider.registered.v1` | `ProviderRegisteredPayload` | provider_id, capabilities[], model_count |
| `k1.model_hub.capability.available.v1` | `CapabilityAvailablePayload` | capability, provider_ids[], model_count |

### Metrics (`metrics.py`)

12 metrics (5 counters, 4 histograms, 3 gauges):

| Name | Type | Labels |
|------|------|--------|
| `model_hub.requests_total` | counter | provider, model, consumer, capability, priority |
| `model_hub.errors_total` | counter | +error_type |
| `model_hub.cache_hits_total` | counter | capability |
| `model_hub.fallbacks_total` | counter | from_provider, to_provider, capability |
| `model_hub.budget_rejections_total` | counter | capability, consumer |
| `model_hub.latency_ms` | histogram | standard |
| `model_hub.provider_latency_ms` | histogram | provider, model, capability |
| `model_hub.tokens_used` | histogram | standard |
| `model_hub.cost_usd` | histogram | standard |
| `model_hub.active_requests` | gauge | — |
| `model_hub.provider_circuit_state` | gauge | provider |
| `model_hub.budget_pct` | gauge | — |

### Tracing (`tracing.py`)

34 phase constants across pipeline/lifecycle/circuit. Functions: `build_trace_log()`, `emit_trace_log()`, `redact_messages()`, `safe_labels()`. Never logs raw prompts or API keys.

### Concurrency Model

All async on single event loop. No locks anywhere. Single-threaded assumption throughout. Token buckets use `time.monotonic()`. Plugin isolation via `except Exception` boundaries.

---

## §3 Factory & Config (I-0.4.3)

### `ModelHubFactory` (static methods)

**`create_standalone(config?, plugins?) → IModelHubPort`** — 11-step wiring:

1. `ModelHubConfig()` (defaults or provided)
2. `CredentialStoreAdapter()`
3. `ProviderRegistry(config)`
4. `CircuitBreakerManager()` + `RateLimiter(headroom_pct)`
5. `CostTracker()` + `ResponseCache(config)` + `BudgetEnforcer(config)`
6. `HealthReportAdapter()` → `_DefaultHealthQuery` → `CapabilityRouter(registry, cb, rl, health)` + `ModelSelector()`
7. `NormalizationLayer()`
8. `ProviderDispatcher(circuit_mgr, rate_limiter, credential_port, plugins)`
9. Register each plugin → `ProviderDispatcher` + `ProviderRegistry`
10. `AuditLogger()` → `RequestRouter(all services)`
11. Return `_HubCore(router, registry, health_adapter)` (implements `IModelHubPort`)

**`create_for_testing(overrides?) → (IModelHubPort, Dict[str, Any])`** — same wiring but uses 6 test adapters + validates all port implementations. Returns dict with all services for test inspection.

**`create_with_ports(ports, config?, plugins?) → IModelHubPort`** — caller-supplied ports (required: `credential_port`).

**`_HubCore`**: bridges `RequestRouter` internal API to `IModelHubPort`:

- `execute()` → `router.route()`
- `stream_execute()` → `router.stream_route()`
- Plus discovery and health delegation.

**`_DefaultHealthQuery`**: returns `HealthStatus.HEALTHY` for all providers (stub).

### `ModelHubConfig` (frozen dataclass)

| Field | Type | Default | Invariant |
|-------|------|---------|-----------|
| `daily_budget_usd` | float | 5.0 | MH-08 |
| `monthly_budget_usd` | float | 100.0 | — |
| `max_concurrent_requests` | int | 50 | — |
| `cache_max_entries` | int | 1000 | MH-09 |
| `cache_ttl_s` | int | 300 | MH-09 |
| `realtime_timeout_ms` | int | 10000 | MH-15 |
| `interactive_timeout_ms` | int | 30000 | MH-15 |
| `background_timeout_ms` | int | 60000 | MH-15 |
| `rate_limit_headroom_pct` | float | 0.80 | MH-12 |
| `health_check_interval_s` | int | 30 | MH-14 |
| `manifest_dir` | str | `"k1/config/providers"` | — |
| `shutdown_grace_period_ms` | int | 10000 | — |

All validated > 0 in `__post_init__`. `from_dict(data)` class method.

---

## §4 Cross-Component Connections (I-0.4.4)

### Connection Matrix

| # | Connection | Consumer Port | ModelHub Port | Type Status | Adapter Status |
|---|-----------|--------------|---------------|:-----------:|----------------|
| 1 | ModelHub → Bus | N/A (bus transport) | `LLMRequestBusAdapter` | ✅ COMPATIBLE | Bus transport NOT wired |
| 2 | ModelHub → SessionState | `IStateReadPort` | `SessionStateReadAdapter` | ✅ COMPATIBLE (MH-01) | Stub only — no prod binding |
| 3 | Concierge → ModelHub | `ILLMPort = IModelHubPort` | `IModelHubPort` | ✅ COMPATIBLE | `ModelHubPOCBridge` exists |
| 4 | Planner → ModelHub | `ILLMPort` (local types) | `IModelHubPort` | 🔴 TYPE MISMATCH | Translation adapter MISSING |
| 5 | Fabric → ModelHub | `IModelGatewayPort` | `IModelHubPort` | 🔴 INCOMPATIBLE | Bridge adapter MISSING |
| 6 | MemoryWriter → ModelHub | `IModelHubPort.chat()` | `IModelHubPort.execute()` | 🔴 INCOMPATIBLE | Bridge adapter MISSING |
| 7 | Learning → ModelHub | N/A | N/A | ⚪ N/A | Not implemented |

### Connection Details

**1. ModelHub → Bus**

- `LLMRequestBusAdapter` wraps an inner `IModelHubPort` (decorator pattern)
- Zero imports from `k1.bus` — adapter is a passthrough, bus transport layer expected to sit outside model_hub
- **Gap**: No code in `k1.bus` deserializes bus envelopes into `HubRequest`

**2. ModelHub → SessionState**

- `SessionStateReadAdapter` uses in-memory `Dict[str, Any]` — reads `persona` + `control` sections
- No imports from `k1.sessionstate` — production binding to real SessionState store is MISSING
- MH-01 properly enforced: no write methods exist on port or adapter

**3. Concierge → ModelHub** ✅

- Concierge imports `IModelHubPort` from `k1.model_hub.ports.hub_port` and aliases as `ILLMPort`
- Direct port call (not via bus): `react_loop()` accepts `model: IModelHubPort`, calls `model.execute(HubRequest)`
- `ModelHubPOCBridge` at `k1/concierge/llm/model_hub_bridge.py` implements `IModelHubPort` structurally
- **🟡 Import bug**: `model_hub_bridge.py` line 18: `from k1.model_hub.ports import HubHealthReport, ProviderHealthStatus` — these are NOT exported from `ports/__init__.py`, should import from `k1.model_hub.types`

**4. Planner → ModelHub** 🔴

- Planner defines its OWN `HubRequest`/`HubResponse` in `k1.planner.types` — DIFFERENT from `k1.model_hub.types`
  - `capability: str` vs `CapabilityType` (Enum)
  - `payload: Dict[str, Any]` vs typed payloads
  - `metadata: Dict[str, Any]` vs `ResponseMetadata` dataclass
  - Missing `idempotency_key`, `request_id` fields
  - No trace_id validation (MH-03 not enforced)
- Code comment at `k1/planner/types.py` acknowledges: *"These types should migrate to k1/model_hub/types.py"* — not done
- `LLMGatewayAdapter` routes through `ILLMRequestBus` using planner-local types — type translation adapter MISSING

**5. Fabric → ModelHub** 🔴

- Fabric's `IModelGatewayPort`: `create_handle(budget_tokens, model_preference, capabilities, trace_id) → ILLMHandle`; `ILLMHandle.generate(prompt, params) → str`
- ModelHub's `IModelHubPort`: `execute(HubRequest) → HubResponse`
- Completely different interfaces, different `ModelInfo` definitions
- Zero imports from `k1.model_hub` in `k1/fabric/`
- Only `TestModelGatewayAdapter` exists — no production bridge

**6. MemoryWriter → ModelHub** 🔴

- MemoryWriter defines own `IModelHubPort` (same name!) with `chat(messages, budget_tokens, model_hint) → ChatResponse`
- ModelHub's `IModelHubPort`: `execute(HubRequest) → HubResponse`
- Same port name, completely different method signatures
- Zero imports from `k1.model_hub` in `k1/memory_writer/`
- No adapter exists

**7. Learning → ModelHub** ⚪

- `k1/learning/` contains only design docs + empty `__init__.py` — no code

### Critical Wiring Gaps

| Priority | Gap | Impact |
|----------|-----|--------|
| 🔴 HIGH | Planner `HubRequest`/`HubResponse` type duplication | Planner cannot send requests to real ModelHub |
| 🔴 HIGH | Fabric `IModelGatewayPort` → `IModelHubPort` bridge missing | Fabric dynamic agents cannot access LLM |
| 🔴 HIGH | MemoryWriter `IModelHubPort.chat()` → `IModelHubPort.execute()` bridge missing | MemoryWriter cannot call LLM |
| 🟡 MED | Concierge `model_hub_bridge.py` import bug (L18) | Runtime ImportError on `HubHealthReport`/`ProviderHealthStatus` |
| 🟡 MED | SessionState production adapter missing | ModelSelector uses default preferences only |
| 🟡 MED | Bus transport adapter (envelope → HubRequest) missing | No bus-mediated LLM routing |

---

## §5 Test Inventory (I-0.4.5)

### Summary

| Metric | Count |
|--------|------:|
| Test files (excl. `__init__.py`) | 37 |
| `def test_` functions | 982 |
| `class Test` entries | 280 |
| Total lines | ~10,400 |

### By Directory

| Directory | Files | test_ funcs | Classes | Lines | Purpose |
|-----------|:-----:|:-----------:|:-------:|------:|---------|
| root | 25 | 821 | 224 | 7,303 | Unit tests for all services, ports, adapters, plugins, types |
| adapters/ | 7 | 0 | 7 | 390 | Test double implementations (not test suites) |
| benchmarks/ | 1 | 11 | 6 | 307 | Perf: budget <1ms, routing <2ms, selection <5ms, pipeline <12ms |
| chaos/ | 1 | 22 | 8 | 495 | Fault injection: crash fallback, all-down, cascade failures |
| contract/ | 1 | 61 | 18 | 794 | All 18 invariants (MH-01→MH-18) |
| integration/ | 1 | 28 | 10 | 529 | Full pipeline: happy path, streaming, budget, cache, fallback |
| lifecycle/ | 1 | 39 | 7 | 566 | Init→health→ready→running→degraded→shutdown |

### Key Test Files by Coverage

| File | Funcs | Lines | Covers |
|------|:-----:|------:|--------|
| `test_types.py` | 101 | 551 | 8 enums, all dataclasses, 15 payloads, 7 error classes |
| `test_provider_plugins.py` | 77 | 919 | 5 provider plugins: lifecycle, request building, response parsing |
| `test_adapters.py` | 70 | 507 | 8 test adapter suites |
| `test_contract/test_invariants.py` | 61 | 794 | All 18 MH invariants |
| `test_model_selector.py` | 38 | 664 | Scoring, fallback chains, priority weights, cost optimization |
| `test_response_cache.py` | 38 | 264 | LRU, TTL, skip rules, eviction |
| `test_production_adapters.py` | 38 | 307 | All 7 production adapters |
| `test_normalization_layer.py` | 34 | 459 | All 15 capability payload transformations |
| `test_provider_registry.py` | 32 | 325 | Registration, capability index, MH-17/18 |
| `test_circuit_breaker_manager.py` | 31 | 267 | State transitions, sliding window, multi-provider |
| `test_budget_enforcer.py` | 31 | 245 | Allow/degraded/reject, cost limits, daily reset |
| `test_factory.py` | 31 | 200 | create_standalone, create_for_testing, port validation |
| `test_lifecycle/test_lifecycle.py` | 39 | 566 | Full lifecycle with recovery |
| `test_integration/test_full_pipeline.py` | 28 | 529 | End-to-end pipeline |
| `test_chaos/test_chaos.py` | 22 | 495 | 8 chaos scenarios |

---

## §6 Spec vs Code Delta

### Invariant Coverage

| Invariant | Spec | Code Status |
|-----------|------|-------------|
| MH-01 | Never writes SessionState | ✅ `IStateReadPort` has no write methods. Tests enforce. |
| MH-02 | All keys in CredentialStore | ✅ `ICredentialPort` injected. Keys from env/overrides only. |
| MH-03 | trace_id on every request | ✅ `HubRequest.__post_init__` raises `ValueError` if empty. |
| MH-04 | Hard budget rejection | ✅ `BudgetEnforcer.check()` returns REJECT. `RequestRouter` raises `BudgetExceededError`. |
| MH-05 | Circuit breaker per provider | ✅ `CircuitBreakerManager` — full CLOSED→OPEN→HALF_OPEN state machine. |
| MH-06 | Capability-aware fallback | ✅ `CapabilityRouter` filters by capability. `ModelSelector` builds top-3 chain. |
| MH-07 | Cost from manifest | ✅ `CostTracker.compute_cost()` uses `ModelSpec.cost_per_1m_*`. |
| MH-08 | $5/day default | ✅ `ModelHubConfig.daily_budget_usd=5.0`. `BudgetEnforcer` enforces. |
| MH-09 | Cache TTL 5min, LRU 1000 | ✅ `ResponseCache` — TTL 300s, max 1000, skip TOOL_CALL/BATCH/MODERATE. |
| MH-10 | Stream chunk validation | 🟡 Not visible in current code — no per-chunk validation logic found. |
| MH-11 | Full audit logging | ✅ `AuditLogger.log()` records all fields per spec. |
| MH-12 | Rate limit with 80% headroom | ✅ `RateLimiter` — token buckets, default headroom 0.80. |
| MH-13 | Placement cascade | ✅ `ModelSelector._PLACEMENT_SCORES` — LOCAL_GPU:1.0, LOCAL_CPU:0.7, REMOTE:0.4. |
| MH-14 | Health check per manifest | ✅ `ModelHubConfig.health_check_interval_s=30`. Plugin `health_check()` method. |
| MH-15 | Priority-based timeouts | ✅ `ModelHubConfig` — REALTIME:10s, INTERACTIVE:30s, BACKGROUND:60s. |
| MH-16 | ALL traffic through RequestRouter | ✅ `_HubCore.execute()` → `router.route()`. Single funnel. |
| MH-17 | Plugin isolation | ✅ `ProviderDispatcher._try_provider()` — `except Exception` catches all. |
| MH-18 | Manifest sole capability truth | ✅ `ProviderRegistry.register()` builds index from manifest capabilities. |

### Diagram vs Code Discrepancies

| Item | Diagram | Code | Severity |
|------|---------|------|----------|
| Health monitor service | Named `ProviderHealthMonitor` | No standalone class — `_DefaultHealthQuery` returns HEALTHY for all | 🟡 Missing service |
| Events emission | RequestRouter emits `request.received.v1`, `request.routed.v1` | `RequestRouter` emits via `_emit()` metrics but **no event bus publish calls found in route pipeline** | 🟡 Events not emitted |
| Stream chunk validation (MH-10) | "Streaming responses validated chunk-by-chunk" | No per-chunk validation logic in `stream_route()` or `ProviderDispatcher.stream()` | 🟡 Not implemented |
| Manifest hot-reload | "HOT RELOAD: watch manifest dir (30s interval)" | `ProviderRegistry` has no file watcher or periodic reload | 🟡 Not implemented |
| PrometheusAdapter | "Histograms, Counters, Gauges" | In-memory dict accumulator, no `prometheus_client` dependency | 🟡 Stub |
| ResponseCache thread-safety | "Thread-safe: lock-free reads, write lock" | No locks exist in implementation | 🟡 Aspirational |
| `_active_requests` counter | Used in `RequestRouter` | Not thread-safe — assumes single event loop | ℹ️ OK for async |

### Findings Summary

| Severity | Count | Items |
|----------|:-----:|-------|
| 🔴 Critical gaps | 3 | Planner type mismatch, Fabric bridge missing, MemoryWriter bridge missing |
| 🟡 Medium gaps | 6 | Concierge import bug, SessionState prod adapter, Bus transport, ProviderHealthMonitor missing, Events not emitted, MH-10 unimplemented |
| 🟡 Stubs | 2 | PrometheusAdapter (in-memory), ResponseCache thread-safety |
| ✅ Solid | 16/18 | Invariants MH-01 through MH-18 (except MH-10) |
| ✅ Test coverage | 982 | test functions across 37 files, 61 contract tests for all 18 invariants |
