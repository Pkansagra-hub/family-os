# ModelHub — Formal API Mapping

> Generated: 2026-04-14 · Scope: Inputs, Outputs, Processing for every ModelHub boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 Primary API — IModelHubPort (Facade)

Single entry point for all LLM interactions. Implemented by `_HubCore` (created by `ModelHubFactory`).

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `execute(request)` | `HubRequest` | `HubResponse` | Concierge Front/Back (via ModelHubPOCBridge), Fabric Agent Factory, MemoryWriter |
| `stream_execute(request)` | `HubRequest` | `AsyncIterator[HubChunk]` | Concierge Front (streaming responses) |
| `discover_capabilities()` | — | `Dict[CapabilityType, List[str]]` | Capability discovery |
| `discover_models(capability)` | `CapabilityType \| None` | `List[ModelInfo]` | Model discovery |
| `health()` | — | `HubHealthReport` | Health checks, monitoring |

### 1.2 Bus Event Entry — BusEnvelopeDeserializer

The **only external-boundary adapter** (imports `k1.bus`). Subscribes to a bus topic and converts JSON envelopes into `HubRequest`.

| Topic | Handler | Payload Shape | Effect |
| --- | --- | --- | --- |
| `k1.model_hub.execute.v1` | `BusEnvelopeDeserializer._on_message` | JSON → `HubRequest` | Deserialize → `IModelHubPort.execute()` → publish response |
| Response: `k1.model_hub.execute.response.v1` | — | `HubResponse` serialized | Published after execution |

### 1.3 Configuration — IConfigPort

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `get(key)` | `str` | `Any` | Internal services |
| `watch(key, callback)` | `str`, `Callable[[str, Any], None]` | `ConfigSubscription` | Hot-reload watchers |

**Production adapter**: `ConfigAdapter` — in-memory dict with hot-reload watcher callbacks.

### 1.4 Credential Supply — ICredentialPort

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `get_key(provider_id)` | `str` | `str` | ProviderDispatcher (before plugin.execute) |
| `refresh_key(provider_id)` | `str` | `str` | Key rotation |

**Production adapter**: `CredentialStoreAdapter` — env-var lookup (`MH_KEY_<PROVIDER_ID>`), production → Vault/keychain (MH-02).

### 1.5 State Read — IStateReadPort

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `read(sections)` | `List[str]` | `StateSnapshot` | Model selection (affective routing, cognitive load) |

**Invariant MH-01**: NO write methods exist. ModelHub is read-only for SessionState.

**Production adapter**: `SessionStateProdAdapter` — wraps real `SessionStateManager` (injected as `Any`), reads via `get_section()` → `to_dict()`/`get_metadata()`.

---

## 2. Exit Points (What Goes OUT)

### 2.1 LLM Provider Calls — IProviderPlugin

All actual LLM calls go through provider plugins via `ProviderDispatcher`.

| Method | Input | Output | Target |
| --- | --- | --- | --- |
| `execute(request)` | `NormalizedRequest` | `ProviderResponse` | LLM API (OpenAI/Anthropic/Google/Ollama/vLLM) |
| `stream_execute(request)` | `NormalizedRequest` | `AsyncIterator[ProviderChunk]` | LLM API (streaming) |
| `health_check()` | — | `ProviderHealth` | LLM API health endpoint |

### 2.2 Event Emissions — IEventPort

| Topic | Payload | When |
| --- | --- | --- |
| `k1.model_hub.request.received.v1` | `RequestReceivedPayload` (request_id, consumer_id, capability, budget_remaining_pct, trace_id) | Every request received |
| `k1.model_hub.request.routed.v1` | `RequestRoutedPayload` (request_id, provider_id, model_id, capability, trace_id) | After provider selection |
| `k1.model_hub.response.complete.v1` | `ResponseCompletePayload` (request_id, tokens_used, latency_ms, cost_usd, provider_id, model_id, capability, cache_hit, trace_id) | After response |
| `k1.model_hub.cache.hit.v1` | `CacheHitPayload` (request_id, cache_key, capability, age_ms, trace_id) | Cache hit |
| `k1.model_hub.provider.failure.v1` | `ProviderFailurePayload` (request_id, provider_id, error_type, error_message, will_fallback, trace_id) | Provider failure |
| `k1.model_hub.fallback.triggered.v1` | `FallbackTriggeredPayload` (request_id, from_provider, to_provider, reason, trace_id) | Fallback chain activation |
| `k1.model_hub.circuit.state.v1` | `CircuitStatePayload` (provider_id, old_state, new_state, failure_count) | Circuit breaker transition |
| `k1.model_hub.budget.alert.v1` | `BudgetAlertPayload` (tenant_id, level=WARNING\|EXCEEDED, pct, action) | Budget threshold crossed |
| `k1.model_hub.provider.health.v1` | `ProviderHealthPayload` (provider_id, status, latency_p50, error_rate) | Health check result |
| `k1.model_hub.provider.registered.v1` | `ProviderRegisteredPayload` (provider_id, capabilities, model_count) | Plugin registered |
| `k1.model_hub.capability.available.v1` | `CapabilityAvailablePayload` (capability, provider_ids, model_count) | New capability available |

**Production adapter**: `EventBusAdapter` — in-memory pub/sub with UUID subscriptions.

### 2.3 Metrics Emissions — IMetricsPort

12 metrics emitted via `IMetricsPort.emit()`:

| Metric | Type | Labels |
| --- | --- | --- |
| `model_hub.requests_total` | counter | provider, model, consumer, capability, priority |
| `model_hub.errors_total` | counter | provider, model, consumer, capability, priority, error_type |
| `model_hub.cache_hits_total` | counter | capability |
| `model_hub.fallbacks_total` | counter | from_provider, to_provider, capability |
| `model_hub.budget_rejections_total` | counter | capability, consumer |
| `model_hub.latency_ms` | histogram | provider, model, consumer, capability, priority |
| `model_hub.provider_latency_ms` | histogram | provider, model, capability |
| `model_hub.tokens_used` | histogram | provider, model, consumer, capability, priority |
| `model_hub.cost_usd` | histogram | provider, model, consumer, capability, priority |
| `model_hub.active_requests` | gauge | (none) |
| `model_hub.provider_circuit_state` | gauge | provider |
| `model_hub.budget_pct` | gauge | (none) |

**Production adapter**: `PrometheusAdapter` — in-memory counter accumulator.

### 2.4 Health Reports — IHealthPort

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `report_health(component, status)` | `str`, `HealthStatus` | — | Internal sub-components |
| `check_health()` | — | `HealthReport` | `_HubCore.health()` |

**Production adapter**: `HealthReportAdapter` — worst-of aggregation across sub-components.

---

## 3. Processing Pipeline

### 3.1 Request Pipeline — 9 Steps (Invariant MH-16)

```text
HubRequest arrives at _HubCore.execute()
  → delegates to RequestRouter.route(request)

Step 1: VALIDATE
  → capability present? trace_id non-empty? (MH-03)
  → Raises ValidationError on failure

Step 2: BUDGET CHECK
  → BudgetEnforcer.check(request) → BudgetDecision
    → ALLOW:          proceed normally
    → ALLOW_DEGRADED:  proceed with cost-optimization (cheaper model)
    → REJECT:          raise BudgetExceededError (MH-04, MH-08)
  → Default: $5/day, 80% → WARNING event, 95% → degraded mode

Step 3: PRIORITY CLASSIFICATION
  → Map Priority to timeout:
    REALTIME:    10,000ms (MH-15)
    INTERACTIVE: 30,000ms
    BACKGROUND:  60,000ms

Step 4: CAPABILITY ROUTING (5-step filter)
  → CapabilityRouter.route(request) → list of eligible providers
    4a. Capability lookup (provider supports CapabilityType?)
    4b. Model filter (model supports capability?)
    4c. Circuit breaker filter (provider CLOSED or HALF_OPEN?)
    4d. Rate limiter filter (tokens available?)
    4e. Health filter (provider HEALTHY or DEGRADED?)
  → Raises NoEligibleProviderError if empty (MH-06, MH-18)

Step 5: MODEL SELECTION (5-dimension weighted scoring)
  → ModelSelector.select(eligible, request) → (provider, model, fallback_chain)
    Dimensions: cost (0.3), latency (0.25), preference (0.2), placement (0.15), health (0.1)
    Priority-specific weights:
      REALTIME:    latency 0.4, cost 0.15
      BACKGROUND:  cost 0.4, latency 0.1
    Cost optimization: at 80% budget → cost weight +0.2; at 95% → cheapest only
    Fallback chain: top 3 by score (MH-13)

Step 6: CACHE CHECK
  → ResponseCache.get(capability, messages_hash, model, temperature) → HubResponse | None
    LRU (1000 entries), 5min TTL (MH-09)
    Skip rules: TOOL_CALL, BATCH, MODERATE, temp > 0, streaming
  → If hit: emit CacheHitPayload, return immediately

Step 7: NORMALIZATION
  → NormalizationLayer.normalize(HubRequest, model_id) → NormalizedRequest
    15-capability dispatch table (CHAT through CODE_EXEC)
    Extracts messages, tools, system_prompt, output_schema etc. from typed payloads

Step 8: DISPATCH (with resilience)
  → ProviderDispatcher.dispatch(normalized, provider, model) → ProviderResponse
    8a. Circuit breaker acquire (fail → CircuitOpenError)
    8b. Rate limiter acquire (fail → RateLimitError)
    8c. Set API key via credential port
    8d. plugin.execute(normalized_request) — 1 retry on transient failure
    8e. On failure: walk fallback chain (max 3 deep) (MH-05)
    8f. plugin isolation: bare except per provider (MH-12)

Step 9: POST-PROCESS
  → Denormalize ProviderResponse → HubResponse
  → Cache store (if cacheable)
  → CostTracker.record(tokens × cost_per_1M / 1M) (per consumer, model, capability)
  → AuditLogger.log() — full MH-11 audit trail
  → Emit ResponseCompletePayload
  → Return HubResponse
```

### 3.2 Streaming Pipeline

Same steps 1–8, but step 8 uses `plugin.stream_execute()` → yields `ProviderChunk` → converted to `HubChunk`. Final chunk includes `ResponseMetadata`. Cache is skipped for streaming.

---

## 4. Type System

### 4.1 Request Envelope

**HubRequest** (frozen):

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `capability` | `CapabilityType` | — | Required |
| `payload` | `Any` | — | One of 15 typed payloads |
| `constraints` | `RequestConstraints` | `RequestConstraints()` | — |
| `trace_id` | `str` | `""` | **Must be non-empty (MH-03)** |
| `idempotency_key` | `Optional[str]` | `None` | For dedup |
| `request_id` | `str` | `uuid4()` | Auto-generated |

**RequestConstraints** (frozen):

| Field | Type | Default | Validation |
| --- | --- | --- | --- |
| `max_tokens` | `int` | `65536` | > 0 |
| `timeout_ms` | `int` | `30000` | > 0 |
| `priority` | `Priority` | `INTERACTIVE` | REALTIME / INTERACTIVE / BACKGROUND |
| `temperature` | `float` | `0.7` | [0.0, 2.0] |
| `model_preference` | `Optional[ModelPreference]` | `None` | Preferred provider/model/tier |
| `provider_preference` | `Optional[str]` | `None` | — |
| `cost_limit` | `Optional[float]` | `None` | Per-request $ limit |
| `consumer_id` | `str` | `""` | Caller identifier for tracking |

### 4.2 Response Envelope

**HubResponse** (frozen):

| Field | Type |
| --- | --- |
| `result` | `Any` (one of 9 typed results) |
| `metadata` | `ResponseMetadata` |

**ResponseMetadata** (frozen):

| Field | Type | Default |
| --- | --- | --- |
| `request_id` | `str` | — |
| `model_id` | `str` | — |
| `provider_id` | `str` | — |
| `usage` | `TokenUsage` | — |
| `cost_usd` | `float` | — |
| `latency_ms` | `int` | — |
| `cache_hit` | `bool` | — |
| `capability` | `CapabilityType` | — |
| `trace_id` | `str` | — |
| `fallback_used` | `bool` | `False` |
| `finish_reason` | `FinishReason` | `STOP` |

**HubChunk** (frozen, streaming):

| Field | Type | Default |
| --- | --- | --- |
| `content` | `str` | `""` |
| `done` | `bool` | `False` |
| `metadata` | `Optional[ResponseMetadata]` | `None` (present on final chunk) |
| `tool_calls` | `Optional[List[ToolCallResult]]` | `None` |

### 4.3 Capability Types (15 values)

| CapabilityType | Payload Class | Result Class |
| --- | --- | --- |
| `CHAT` | `ChatPayload` (messages, system_prompt) | `ChatResult` (text) |
| `TOOL_CALL` | `ToolCallPayload` (messages, tools, tool_choice, parallel_tool_calls) | `ToolCallResultSet` (text, tool_calls) |
| `STRUCTURED` | `StructuredOutputPayload` (messages, output_schema, strict) | `StructuredResult` (json_output) |
| `REASON` | `ReasonPayload` (messages, reasoning_effort, include_thinking) | `ReasonResult` (text, thinking) |
| `EMBED` | `EmbedPayload` (texts, dimensions, encoding_format) | `EmbedResult` (embeddings) |
| `VISION` | `VisionPayload` (messages, image_inputs, detail) | `ChatResult` |
| `BATCH` | `BatchPayload` (requests, callback_topic) | (per-request) |
| `MODERATE` | `ModeratePayload` (text, categories) | `ModerateResult` (flagged, categories) |
| `TOKEN_COUNT` | `TokenCountPayload` (messages, model_id) | `TokenCountResult` (count) |
| `CACHE_PROMPT` | `CachePromptPayload` (cache_key, messages, ttl_s) | `ChatResult` |
| `AUDIO_IN` | `AudioInputPayload` (messages, audio, voice_config) | `ChatResult` |
| `TTS` | `TTSPayload` (text, voice, format, speed) | `Any` |
| `IMAGE_GEN` | `ImageGenPayload` (prompt, size, quality, n) | `Any` |
| `WEB_SEARCH` | `WebSearchPayload` (query, max_results) | `Any` |
| `CODE_EXEC` | `CodeExecPayload` (code, language, timeout_s) | `Any` |

### 4.4 Conversation Primitives

**Message** (frozen): `role: str`, `content: str`, `tool_call_id: Optional[str]`, `name: Optional[str]`, `tool_calls: Optional[List[ToolCallResult]]`

**ToolDefinition** (frozen): `name: str`, `description: str`, `parameters: Dict[str, Any]`

**ToolCallResult** (frozen): `id: str`, `name: str`, `arguments: str`

**TokenUsage** (frozen): `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`

### 4.5 Enums

| Enum | Values |
| --- | --- |
| `CapabilityType` | 15 values (see §4.3) |
| `Priority` | `REALTIME`, `INTERACTIVE`, `BACKGROUND` |
| `FinishReason` | `STOP`, `TOOL_CALLS`, `LENGTH`, `ERROR`, `SAFETY` |
| `HealthStatus` | `HEALTHY`, `DEGRADED`, `UNHEALTHY` |
| `CircuitState` | `CLOSED`, `OPEN`, `HALF_OPEN` |
| `BudgetDecision` | `ALLOW`, `ALLOW_DEGRADED`, `REJECT` |
| `PlacementType` | `REMOTE`, `LOCAL_GPU`, `LOCAL_CPU` |
| `ModelTier` | `FAST`, `STANDARD`, `PREMIUM` |

### 4.6 Error Hierarchy

| Exception | Parent | Key Fields |
| --- | --- | --- |
| `ModelHubError` | `Exception` | `message`, `request_id`, `trace_id`, `capability` |
| `ProviderError` | `ModelHubError` | `provider_id`, `status_code` |
| `BudgetExceededError` | `ModelHubError` | `budget_pct`, `daily_limit` |
| `NoEligibleProviderError` | `ModelHubError` | — |
| `RateLimitError` | `ModelHubError` | `provider_id`, `retry_after_ms` |
| `CircuitOpenError` | `ModelHubError` | `provider_id`, `cooldown_remaining_ms` |
| `HubTimeoutError` | `ModelHubError` | — |
| `ValidationError` | `ModelHubError` | — |

---

## 5. Plugin System

### 5.1 IProviderPlugin Protocol

7 required methods (structural subtyping, `@runtime_checkable`):

| Method | Signature | Async | Purpose |
| --- | --- | --- | --- |
| `initialize(manifest)` | `ProviderManifest → None` | ✅ | Setup connections, validate keys |
| `supports(capability)` | `CapabilityType → bool` | ❌ | O(1) capability check |
| `execute(request)` | `NormalizedRequest → ProviderResponse` | ✅ | Single-shot LLM call |
| `stream_execute(request)` | `NormalizedRequest → AsyncIterator[ProviderChunk]` | ✅ | Streaming LLM call |
| `estimate_tokens(messages)` | `List[Message] → int` | ❌ | Fast local token estimate |
| `health_check()` | `→ ProviderHealth` | ✅ | Health probe |
| `close()` | `→ None` | ✅ | Cleanup connections |

Lifecycle: `initialize()` → runtime → `close()`

### 5.2 Intermediate Types (Plugin Boundary)

**NormalizedRequest** (frozen): capability, messages, system_prompt, tools, tool_choice, output_schema, max_tokens, timeout_ms, temperature, model_id, trace_id, consumer_id, reasoning_effort, extra

**ProviderResponse** (frozen): text, tool_calls, prompt_tokens, completion_tokens, model_id, finish_reason, raw_response

**ProviderChunk** (frozen): text, done, tool_calls, metadata

**ProviderHealth** (frozen): status, latency_ms, error_rate, details

### 5.3 Provider Plugins (6)

| Plugin | Capabilities | API Protocol | Auth | Placement | Default Base URL |
| --- | --- | --- | --- | --- | --- |
| `OpenAIPlugin` | 14 of 15 | REST (chat/completions) | Bearer token | remote | `https://api.openai.com/v1` |
| `AnthropicPlugin` | 7 | REST (/v1/messages) | x-api-key + version header | remote | `https://api.anthropic.com/v1` |
| `GooglePlugin` | 9 | google-genai SDK | API key | remote | SDK-managed |
| `OllamaPlugin` | 4 | REST (native /api/chat) | None | local_cpu | `http://localhost:11434` |
| `VLLMPlugin` | 4 | REST (OpenAI-compat) | Optional Bearer | local_gpu | `http://localhost:8000/v1` |
| `TestProviderPlugin` | Configurable | In-memory | None | N/A | N/A |

### 5.4 Provider-Specific Details

**OpenAI**: Uses `max_completion_tokens` (not deprecated `max_tokens`). Reasoning models (o3, o4-mini, o3-mini, o1, o1-mini) get `reasoning_effort` param, no temperature, `developer` role for system prompt.

**Anthropic**: System prompt in TOP-LEVEL `system` field (NOT in messages). `max_tokens` REQUIRED. Tools use `input_schema` key. Extended thinking via `thinking: {type: "enabled", budget_tokens: ...}`.

**Google**: Lazy SDK import. `run_in_executor` wraps sync SDK calls. Thinking budget: low=1024, medium=8192, high=24576 tokens.

**Ollama**: NDJSON streaming (not SSE). No auth. Tool arguments returned as object (serialized to string by plugin).

**vLLM**: OpenAI-compatible. Single model per instance. Optional auth.

---

## 6. Services (Internal Pipeline Components)

### 6.1 RequestRouter — Central Pipeline Orchestrator

THE single 9-step pipeline entry point. Emits 11 named metrics.

| Method | Signature |
| --- | --- |
| `route(request)` | `HubRequest → HubResponse` |
| `stream_route(request)` | `HubRequest → AsyncIterator[HubChunk]` |

### 6.2 CapabilityRouter — 5-Step Filtering

| Step | Filter | Criteria |
| --- | --- | --- |
| 1 | Capability lookup | Provider supports `CapabilityType`? |
| 2 | Model filter | Model supports capability? |
| 3 | Circuit breaker | Provider CLOSED or HALF_OPEN? |
| 4 | Rate limiter | Tokens available? |
| 5 | Health filter | Provider HEALTHY or DEGRADED? |

### 6.3 ModelSelector — 5-Dimension Weighted Scoring

| Dimension | Default Weight | Purpose |
| --- | --- | --- |
| Cost | 0.30 | Lower cost scores higher |
| Latency | 0.25 | Faster scores higher |
| Preference | 0.20 | Match user/consumer preference |
| Placement | 0.15 | Local > remote for latency |
| Health | 0.10 | Healthier scores higher |

Priority adjustments: REALTIME → latency=0.4 cost=0.15; BACKGROUND → cost=0.4 latency=0.1.

Budget pressure: 80% → cost weight +0.2; 95% → cheapest model only.

Fallback chain: top 3 providers by score.

### 6.4 ProviderDispatcher — Dispatch with Resilience

| Step | Action |
| --- | --- |
| 1 | Circuit breaker acquire |
| 2 | Rate limiter acquire |
| 3 | Set API key via credential port |
| 4 | `plugin.execute(request)` with 1 retry |
| 5 | On failure: walk fallback chain (max 3 deep) |

Plugin isolation: bare except per provider call.

### 6.5 CircuitBreakerManager

State machine: CLOSED → OPEN → HALF_OPEN → CLOSED

| Parameter | Default |
| --- | --- |
| Failure threshold | 3 failures in 60s → OPEN |
| Cooldown | 30s before HALF_OPEN |
| Probe | Single request in HALF_OPEN |

### 6.6 RateLimiter

Dual token bucket per provider: RPM + TPM. 80% headroom by default. Atomic acquire.

### 6.7 BudgetEnforcer

| Budget Level | Decision | Action |
| --- | --- | --- |
| < 80% | ALLOW | Normal processing |
| 80–95% | ALLOW_DEGRADED | Cost-optimize (cheaper model) |
| > 95% | REJECT | Raise BudgetExceededError |

Default: $5/day, $100/month.

### 6.8 ResponseCache

LRU OrderedDict with SHA-256 keys. 5min TTL. 1000 max entries.

Skip rules: `TOOL_CALL`, `BATCH`, `MODERATE`, temperature > 0, streaming.

### 6.9 CostTracker

Cost = tokens × cost_per_1M / 1_000_000. Aggregation by consumer, model, capability.

### 6.10 NormalizationLayer

Bidirectional translation with 15-capability dispatch table. Converts `HubRequest` payload → `NormalizedRequest`, and `ProviderResponse` → `HubResponse`.

### 6.11 AuditLogger

Full MH-11 audit trail: request metadata, response metadata, errors. Structured JSON logging.

---

## 7. Manifest System

### 7.1 ProviderManifest (YAML-driven)

Each provider is defined by a YAML manifest loaded from `k1/config/providers/`.

**ProviderManifest** (frozen):

| Field | Type | Default |
| --- | --- | --- |
| `provider_id` | `str` | — |
| `display_name` | `str` | `""` |
| `plugin_class` | `str` | `""` |
| `api_base` | `str` | `""` |
| `auth` | `AuthConfig` | `AuthConfig()` |
| `capabilities` | `List[CapabilityType]` | `[]` |
| `models` | `List[ModelSpec]` | `[]` |
| `circuit_breaker` | `CircuitBreakerConfig` | `CircuitBreakerConfig()` |
| `health_check` | `HealthCheckConfig` | `HealthCheckConfig()` |
| `concurrency` | `ConcurrencyConfig` | `ConcurrencyConfig()` |
| `rate_limits` | `RateLimitConfig` | `RateLimitConfig()` |
| `placement` | `PlacementConfig` | `PlacementConfig()` |

### 7.2 ModelSpec (per model within provider)

| Field | Type | Default |
| --- | --- | --- |
| `id` | `str` | — |
| `capabilities` | `List[CapabilityType]` | `[]` |
| `cost_per_1m_input` | `float` | `0.0` |
| `cost_per_1m_output` | `float` | `0.0` |
| `max_context` | `int` | `128000` |
| `max_output` | `Optional[int]` | `None` |
| `supports_streaming` | `bool` | `True` |
| `supports_parallel_tools` | `Optional[bool]` | `None` |
| `embedding_dimensions` | `Optional[int]` | `None` |
| `rate_limit_rpm` | `Optional[int]` | `None` |
| `rate_limit_tpm` | `Optional[int]` | `None` |
| `tier` | `ModelTier` | `STANDARD` |

### 7.3 Sub-Configs

| Config | Key Fields |
| --- | --- |
| `AuthConfig` | `type` (bearer/api_key_header/none), `credential_key`, `header_name` |
| `CircuitBreakerConfig` | `failure_threshold` (3), `failure_window_s` (60), `cooldown_s` (30) |
| `RateLimitConfig` | `rpm` (60), `tpm` (100000), `headroom_pct` (0.80) |
| `PlacementConfig` | `type` (REMOTE/LOCAL_GPU/LOCAL_CPU), `device_requirements` |
| `HealthCheckConfig` | `endpoint`, `interval_s` (30), `timeout_s` (5) |
| `ConcurrencyConfig` | `max_concurrent` (10) |

---

## 8. Factory Wiring

### 8.1 ModelHubFactory

| Method | Purpose | Returns |
| --- | --- | --- |
| `create_standalone(config, plugins)` | Production wiring | `IModelHubPort` |
| `create_for_testing(overrides)` | Test wiring (all test adapters) | `(IModelHubPort, adapters_dict)` |
| `create_with_ports(ports, config, plugins)` | Custom port injection | `IModelHubPort` |

### 8.2 Wiring Sequence (11 steps)

| Step | Component Created | Injected With |
| --- | --- | --- |
| 1 | `ModelHubConfig` | — |
| 2 | `CredentialStoreAdapter` | — |
| 3 | `ProviderRegistry(cfg)` | Config |
| 4 | `CircuitBreakerManager()`, `RateLimiter(headroom)` | Config |
| 5 | `CostTracker()`, `ResponseCache(cfg)`, `BudgetEnforcer(cfg)` | Config |
| 6 | `HealthReportAdapter()`, `CapabilityRouter(registry, cb, rl, health)`, `ModelSelector()` | Registry, CircuitBreaker, RateLimiter, Health |
| 7 | `NormalizationLayer()` | — |
| 8 | `ProviderDispatcher(cb, rl, credentials, plugins)` | CircuitBreaker, RateLimiter, Credentials, Plugins |
| 9 | `RequestRouter(cap_router, selector, budget, cache, norm, dispatcher, cost, audit)` | All services |
| 10 | `AuditLogger()` | — |
| 11 | `_HubCore(router, registry, health)` | Router, Registry, Health |

---

## 9. Configuration

### 9.1 ModelHubConfig

| Field | Default | Invariant |
| --- | --- | --- |
| `daily_budget_usd` | `5.0` | MH-08 |
| `monthly_budget_usd` | `100.0` | — |
| `max_concurrent_requests` | `50` | — |
| `cache_max_entries` | `1000` | MH-09 |
| `cache_ttl_s` | `300` (5min) | MH-09 |
| `realtime_timeout_ms` | `10000` | MH-15 |
| `interactive_timeout_ms` | `30000` | MH-15 |
| `background_timeout_ms` | `60000` | MH-15 |
| `rate_limit_headroom_pct` | `0.80` | MH-12 |
| `health_check_interval_s` | `30` | MH-14 |
| `manifest_dir` | `"k1/config/providers"` | — |
| `shutdown_grace_period_ms` | `10000` | — |

---

## 10. Tracing

### 10.1 Phase Constants (34 phases)

**Pipeline phases (27)**: REQUEST_RECEIVED → VALIDATE_OK → BUDGET_CHECK → PRIORITY_CLASSIFIED → ROUTE_START → ROUTE_ELIGIBLE → SELECT_MODEL → CACHE_HIT/MISS → NORMALIZE → DISPATCH_START → DISPATCH_OK/RETRY/FAILED/FALLBACK → STREAM_START/CHUNK/DONE → POSTPROCESS_COST → POSTPROCESS_AUDIT → RESPONSE_SENT

**Lifecycle phases (5)**: INIT, HEALTH_CHECK, READY, DEGRADED, SHUTDOWN

**Circuit breaker phases (2)**: CIRCUIT_OPEN, CIRCUIT_CLOSE

### 10.2 Trace Functions

| Function | Purpose |
| --- | --- |
| `build_trace_log(phase, trace_id, ...)` | Build structured trace dict |
| `emit_trace_log(phase, trace_id, ...)` | Build + log via `k1.model_hub` logger |
| `redact_messages(messages)` | Replace all content with `<REDACTED>` |
| `safe_labels(labels)` | Strip secret-looking keys (api_key, token, secret, etc.) |

---

## 11. Invariants (18 Hard Constraints)

| ID | Invariant | Status |
| --- | --- | --- |
| MH-01 | No SessionState writes (read-only) | ✅ Enforced (IStateReadPort has no write methods) |
| MH-02 | Credentials via ICredentialPort only | ✅ Enforced |
| MH-03 | trace_id required on every request | ✅ Validated in step 1 |
| MH-04 | Budget enforcement before dispatch | ✅ Step 2 |
| MH-05 | Automatic fallback on provider failure | ✅ Step 8 (max 3 deep) |
| MH-06 | Capability-based routing (no hardcoded models) | ✅ Step 4 |
| MH-07 | Plugin isolation (one plugin failure ≠ hub failure) | ✅ Bare except in dispatcher |
| MH-08 | Daily budget limit ($5 default) | ✅ BudgetEnforcer |
| MH-09 | Response caching (5min TTL, 1000 entries) | ✅ ResponseCache |
| MH-10 | Stream validation | ⚠️ Stub |
| MH-11 | Audit logging for every request | ✅ AuditLogger |
| MH-12 | Rate limit headroom (80%) | ✅ RateLimiter |
| MH-13 | Fallback chain (top 3 providers) | ✅ ModelSelector |
| MH-14 | Health checks (30s interval) | ✅ HealthCheckConfig |
| MH-15 | Priority-based timeouts | ✅ Step 3 |
| MH-16 | 9-step pipeline invariant | ✅ RequestRouter |
| MH-17 | Manifest hot-reload | ⚠️ Stub |
| MH-18 | No eligible provider → clear error | ✅ NoEligibleProviderError |

---

## 12. Gaps & TODOs

| # | Gap | Severity | Detail |
| --- | --- | --- | --- |
| 1 | **MH-10 stream validation** | P3 | Stream validation is stub — not actively validating streaming chunks |
| 2 | **MH-17 manifest hot-reload** | P3 | Manifest hot-reload stub — requires filesystem watcher |
| 3 | **POC bridge layer** | P2 | Concierge uses `ModelHubPOCBridge` wrapping `GeminiConciergeAdapter` instead of production `ModelHubFactory`. Two parallel paths exist: POC bridge and full ModelHub |
| 4 | **Bus adapter not wired in kernel** | P3 | `BusEnvelopeDeserializer` exists but not wired in `k1.kernel.bootstrap` — direct injection used instead |
| 5 | **EventBusAdapter is in-memory** | P4 | Not connected to K1 event bus — events stay local to ModelHub |

---

## 13. Test Coverage

- **37 test files**, **982 test functions**, **280 test classes**, **~10,400 lines**
- Zero `unittest.mock` imports
- Coverage areas: all 18 invariants (contract tests), all 5 plugins, 9-step pipeline, lifecycle, benchmarks, chaos scenarios, integration
- Benchmarks: budget <1ms, routing <2ms, selection <5ms, full pipeline <12ms
