# K1 Kernel — Live Component Inventory

**Purpose:** Authoritative, live document tracking every component wired into the K1 kernel. Update this file whenever a component is added, removed, or its semantics change.
**Source:** `k1/kernel/service.py` — `_startup_tier1()` (S1→S8) + `_create_session_tier2()` (P1→P5.5)
**Last Updated:** 2026-06-17
**Branch:** `feature/prompt-architecture-refactor`

---

# S1 — Bus + AsyncBusBridge + MailboxRouter

**File:** `k1/bus/factory.py`, `k1/bus/impl/`, `k1/bus/ports/`, `k1/bus/middleware/`, `k1/bus/outbox/`, `k1/bus/timing/`, `k1/bus/async_bridge.py`, `k1/bus/envelope/`
**Init:** `_startup_tier1()` L1631 — `BusFactory.create_local_ordered()` + `BusFactory.create_mailbox_router()` + `AsyncBusBridge(bus)`
**Lifecycle:** Created first, closed last. Shared across all sessions.
**Config:** `K1_BUS_BACKEND` env var (`"auto"`|`"python"`|`"rust"`). Optional SQLite WAL outbox via `bus_outbox_path` + `bus_durable_topics`.

## Sub-Components

### Core Bus Implementation

| Component | File | Purpose |
|-----------|------|---------|
| `LocalBus` | `impl/local_bus.py` | In-process pub/sub bus. Thread-safe with RWLock on subscription trie. Hot path (publish) takes READ lock. Sub/unsub takes WRITE lock. |
| `TopicTrie` | `impl/topic_trie.py` | Radix-compressed topic trie for O(k) matching. Supports exact match, single wildcard (`*`), greedy wildcard (`>`). Rust port via `k1_bus_core.TopicTrie`. |
| `_SequenceGenerator` | `impl/local_bus.py` | Per-topic monotonic uint64 sequence counters. `threading.Lock` per topic (zero cross-topic contention). |
| `RustBusAdapter` | `impl/rust_bus_adapter.py` | Rust backend adapter. Available when `k1_bus_core` native extension is compiled. |

### Bus Protocol (`ports/`)

| Component | File | Purpose |
|-----------|------|---------|
| `IBus` | `ports/bus.py` | `@runtime_checkable` Protocol. `publish(envelope)`, `subscribe(pattern, handler)`, `unsubscribe(handle)`, `close()`. |
| `SubscriptionHandle` | `ports/bus.py` | Frozen dataclass. Opaque handle returned by `subscribe()`, passed to `unsubscribe()`. Fields: `subscription_id`, `pattern`. |
| `BusHandler` | `ports/bus.py` | `Callable[[Envelope], None]` — synchronous handler signature. |
| `AsyncBusHandler` | `ports/async_bus.py` | `Callable[[Envelope], Coroutine]` — async handler signature for `AsyncBusBridge`. |

### Envelope (`envelope/`)

| Component | File | Purpose |
|-----------|------|---------|
| `Envelope` | `envelope/envelope.py` | Frozen dataclass. `topic`, `payload` (opaque bytes), `envelope_id`, `sequence`, `priority`, `parent_id`, `cognitive_trace_id`, `ttl_ms`, `payload_format`, `created_ns`, `request_id`, `session_id`. |
| `Priority` | `envelope/envelope.py` | IntEnum: `URGENT=1`, `REALTIME=2`, `INTERACTIVE=3`, `BACKGROUND=4`. WFQ scheduling weights. |
| `DeliveryMode` | `envelope/envelope.py` | IntEnum: `STRICT=1` (ordered), `RELAXED=2` (monitor reorders), `BEST_EFFORT=3` (no timing chain). |
| `PayloadFormat` | `envelope/envelope.py` | IntEnum: `OPAQUE=0`, `JSON=1`, `MSGPACK=2`. |
| FlatBuffers V2 | `envelope/_fb_generated.py`, `envelope/schema.fbs` | Zero-copy wire format. 4-byte `b'FB02'` magic prefix. Auto-detected on `from_bytes()`. JSON V1 fallback. |

### Mailbox System (`impl/` + `ports/`)

| Component | File | Purpose |
|-----------|------|---------|
| `LocalMailbox` | `impl/local_mailbox.py` | Bounded per-actor inbox. 4 sub-queues (URGENT/REALTIME/INTERACTIVE/BACKGROUND) with strict priority scheduling. Thread-safe via Condition + mutex. |
| `LocalMailboxRouter` | `impl/local_mailbox.py` | Actor registry mapping `actor_id → LocalMailbox`. RLock for thread safety. `register()`, `unregister()`, `deliver()`. |
| `IMailbox` | `ports/mailbox.py` | `@runtime_checkable` Protocol. `receive(timeout)`, `deliver(envelope)`, `close()`, `pending()`. |
| `IMailboxRouter` | `ports/mailbox.py` | `@runtime_checkable` Protocol. `register(actor_id, config)`, `unregister(actor_id)`, `deliver(actor_id, envelope)`, `close()`. |
| `MailboxConfig` | `ports/mailbox.py` | Dataclass: `capacity`, `priority_wfq` (bool), `delivery_mode`. |
| `BackpressureError` | `ports/mailbox.py` | Raised when mailbox is full. Carries `actor_id` + `capacity`. |
| `TtlExpiredError` | `ports/mailbox.py` | Raised/recorded when envelope TTL expires before delivery. |
| `RustMailboxRouterAdapter` | `impl/rust_mailbox_adapter.py` | Rust backend. Available when `k1_bus_core` is compiled. |

### Async Bridge

| Component | File | Purpose |
|-----------|------|---------|
| `AsyncBusBridge` | `async_bridge.py` | Async wrapper around sync `IBus`. Offloads blocking calls via `asyncio.to_thread()`. Async handlers wrapped via `asyncio.run_coroutine_threadsafe()`. Tracks `async_handler_errors` counter (P6.1). |
| `AsyncMailboxBridge` | `async_bridge.py` | Async wrapper around `IMailbox`. `deliver()` → `to_thread`, `receive()` → `to_thread`. |
| `AsyncMailboxRouterBridge` | `async_bridge.py` | Async wrapper around `IMailboxRouter`. `register()` → `to_thread`, `deliver()` → `to_thread`. |

### Middleware Pipeline (`middleware/`)

Runs AFTER envelope stamping, BEFORE trie matching and handler dispatch.

| Component | File | Purpose |
|-----------|------|---------|
| `Middleware` | `middleware/__init__.py` | `@runtime_checkable` Protocol. `process(envelope) → Envelope or None` (None = drop). Never reads payload. |
| `MiddlewareChain` | `middleware/__init__.py` | Ordered pipeline of Middleware instances. Runs in order: tracing → metrics → topic_validation. |
| `TopicValidationMiddleware` | `middleware/topic_validation.py` | Validates topic against `TopicRegistry`. SOFT mode: unknown topics log WARNING but are still delivered. |
| `TopicRegistry` | `middleware/topic_validation.py` | Registry of known topics. Exact match + prefix + wildcard. Thread-safe. |
| `PayloadValidator` | `middleware/topic_validation.py` | Callable `(bytes, Envelope) → None` for schema validation (P6.11). |
| `get_default_registry()` | `middleware/default_registry.py` | Lazy singleton pre-populated with ~40 `k1.*` topic prefixes covering all production subsystems. |
| `TracingMiddleware` | `middleware/tracing.py` | OpenTelemetry trace context injection (optional, degrades gracefully if OTEL not installed). |
| `MetricsMiddleware` | `middleware/metrics.py` | Prometheus metrics: publish count, latency histogram, handler errors (optional). |
| `IdempotencyMiddleware` | `middleware/idempotency.py` | Deduplication by `envelope.idem_key`. |

### Timing Chain (`timing/`)

Enforces causal ordering and per-topic sequence ordering. Only in Python backend.

| Component | File | Purpose |
|-----------|------|---------|
| `TimingChain` | `timing/timing_chain.py` | Sits between bus stamping and handler dispatch. Two constraints: parent_id causal ordering + per-topic sequence gap buffering. Thread-safe with per-topic locks. |
| `TimingConfig` | `timing/timing_config.py` | Config: per-topic delivery mode (STRICT/RELAXED/BEST_EFFORT), timeout, buffer limits. |
| `CausalTracker` | `timing/timing_chain.py` | Tracks parent_id → delivered status. Holds children until parent delivered. |
| `GapBuffer` | `timing/timing_chain.py` | Per-topic sequence gap buffer. Holds out-of-order envelopes until missing sequence arrives. |
| `default_timing_config()` | `timing/defaults.py` | Built-in timing rules for K1 topic prefixes (k1.response.*, k1.orchestration.*, k1.tool.*). |

### Durable Outbox (`outbox/`)

| Component | File | Purpose |
|-----------|------|---------|
| `BusOutbox` | `outbox/sqlite_outbox.py` | SQLite WAL-backed durable envelope persistence. Two tables: `envelopes` + `acks`. Envelope appended BEFORE dispatch. Consumer acks after handler success. `replay_unacked()` on restart. |
| `BusOutboxConfig` | `outbox/sqlite_outbox.py` | Dataclass: db_path, compact_interval, max_envelope_age. |

### Bus Adapters (`adapters/`)

| Component | File | Purpose |
|-----------|------|---------|
| `FabricBusAdapter` | `adapters/fabric_adapter.py` | Adapts IBus for Fabric event emission. |
| `SessionBusAdapter` | `adapters/session_adapter.py` | Adapts per-session bus for SessionState operations. |

### Factory

| Method | Returns | Purpose |
|--------|---------|---------|
| `BusFactory.create_local_ordered()` | `LocalBus` | Production bus with `TimingChain` + `TopicValidationMiddleware` + optional outbox. |
| `BusFactory.create_local()` | `LocalBus` or `RustBusAdapter` | Plain bus, no timing chain. `backend=` selects Python/Rust. |
| `BusFactory.create_for_testing()` | `LocalBus` or `RustBusAdapter` | Capture mode — `bus.captured` records all envelopes. |
| `BusFactory.create_mailbox_router()` | `LocalMailboxRouter` or `RustMailboxRouterAdapter` | Actor mailbox registry. |

---

# S2 — ModelHub

**File:** `k1/model_hub/` — 45 Python files across factory, services, plugins, adapters, ports, types
**Init:** `_startup_tier1()` L1644 — `ModelHubFactory.from_config(ProviderConfig.from_env(), ports=mh_ports)` or `ModelHubFactory.create_with_ports(ports=mh_ports)` (test mode)
**Lifecycle:** Created after Bus, before HIL/Fabric/Concierge. Shared across all sessions.
**Config:** `LLM_PROVIDER` env var (`"vertex"` for production). `model_mode=` — `"hub"` (production) or `"test"` (stub).
**Architecture:** 4-layer design — Layer 0 (types/config/manifest/events/metrics), Layer 1 (7 port protocols), Layer 2 (plugin base), Layer 3 (10 services + 9 adapters + factory + loader), Layer 4 (9 provider plugins).
**Invariant:** ALL LLM traffic goes through a single `IModelHubPort` gateway (MH-16). No direct provider access.

## Sub-Components

### Domain Types (`types.py` — 8 enums + 28 dataclasses)

| Type | Purpose |
|------|---------|
| `CapabilityType` | 15-member taxonomy: CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH, MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS, IMAGE_GEN, WEB_SEARCH, CODE_EXEC |
| `Priority` | REALTIME(10s), INTERACTIVE(30s), BACKGROUND(60s) |
| `FinishReason` | STOP, TOOL_CALLS, LENGTH, ERROR, SAFETY, MALFORMED_TOOL_CALL |
| `HealthStatus` | HEALTHY, DEGRADED, UNHEALTHY |
| `CircuitState` | CLOSED, OPEN, HALF_OPEN |
| `PlacementType` | REMOTE, LOCAL_GPU, LOCAL_CPU |
| `ModelTier` | FAST, STANDARD, PREMIUM |
| `HubRequest` | **Single entry point** for ALL LLM capabilities (MH-16). Capability payload discriminated by `capability` enum. Consumer ID, priority, constraints, messages, trace_id. |
| `HubResponse` | Unified response: result + `ResponseMetadata` (request_id, model, provider, usage, cost, latency, cache_hit, fallback). |
| `HubChunk` | Streaming chunk: content, thought, done, metadata, tool_calls. |
| `Message` | Provider-agnostic message: role, content, tool_call_id, name, tool_calls. |
| `ToolDefinition` | Function-calling schema: name, description, parameters. |
| `ToolSchema` | Tool definition with `actor`, `category`, `side_effects` fields. |
| `ToolCallPayload` | LLM tool-call payload: system_prompt, messages, tools, constraints, use_streaming, force_text. |
| `RequestConstraints` | Per-request: max_tokens, timeout_ms, priority, temperature, cost_limit, reasoning_effort. |
| `TokenUsage` | prompt_tokens, completion_tokens, total_tokens. |
| `ModelInfo` | Provider-agnostic model metadata: id, provider_id, capabilities, cost, context_window, tier. |
| `ModelPreference` | User preferences from SessionState persona. |

**Error hierarchy:** `ModelHubError` → `ProviderError`, `NoEligibleProviderError`, `CircuitOpenError`, `RateLimitError`, `HubTimeoutError`, `ValidationError`.

**Capability payloads (14):** ChatPayload, ToolCallPayload, StructuredOutputPayload, ReasonPayload, EmbedPayload, VisionPayload, BatchPayload, ModeratePayload, TokenCountPayload, CachePromptPayload, AudioInputPayload, TTSPayload, ImageGenPayload, WebSearchPayload, CodeExecPayload.

### Port Protocols (`ports/` — 7 protocols)

| Protocol | File | Purpose |
|----------|------|---------|
| `IModelHubPort` | `ports/hub_port.py` | **THE single gateway.** `execute()`, `stream_execute()`, `discover_capabilities()`, `discover_models()`, `health()`. `@runtime_checkable`. |
| `IEventPort` | `ports/event_port.py` | Pub/sub: `publish(topic, payload)`, `subscribe(topic, handler)` → `Subscription`. |
| `IStateReadPort` | `ports/state_read_port.py` | READ-ONLY SS access: `read(section_names)` → `StateSnapshot`. NO write methods (MH-01). |
| `IMetricsPort` | `ports/metrics_port.py` | Fire-and-forget: `emit(name, value, labels)`. |
| `IConfigPort` | `ports/config_port.py` | Config: `get(key)`, `watch(keys, callback)` → `ConfigSubscription`. |
| `ICredentialPort` | `ports/credential_port.py` | Credential store: `get_key(provider_id)` → str. Keys NEVER in manifest YAML (MH-02). |
| `IHealthPort` | `ports/health_port.py` | Health: `report_health()`, `check_health()` → `HealthReport`. |

### Configuration & Manifest (`config.py`, `manifest.py`, `loader.py`)

| Component | File | Purpose |
|-----------|------|---------|
| `ModelHubConfig` | `config.py` | Frozen config: max_concurrent, cache TTL (5min, MH-09), entry limits, priority timeouts, rate_limit_headroom (80%, MH-12), health_check_interval, manifest_dir, shutdown_grace, daily/monthly budgets. |
| `ProviderManifest` | `manifest.py` | Parsed YAML per provider: provider_id, display_name, plugin_class, api_base, auth (bearer/api_key), capabilities[], models[], circuit_breaker config, health_check, concurrency, rate_limits (rpm/tpm), placement. MH-18: sole source of capability truth. |
| `ProviderConfig` | `loader.py` | Ordered tuple of `ProviderEntry` (provider_id, manifest_path, plugin_class, enabled). `default()` = google+openai+anthropic. `from_env()` reads `LLM_PROVIDER` env var with aliases. |
| `ProviderLoader` | `loader.py` | Declarative loader. Resolves manifest → credentials → plugin class → `initialize()` → `register_plugin()`. Idempotent. Never raises on per-provider failure — inspect `ProviderLoadResult`. |
| `ProviderLoadResult` | `loader.py` | Outcome: `registered`, `skipped`, `failed` tuples. |

### Core Services (`services/` — 10 services)

**9-step request pipeline:** validate → budget → priority → route → select → cache → normalize → dispatch → post-process.

| Component | File | Purpose |
|-----------|------|---------|
| `RequestRouter` | `services/request_router.py` | **THE single entry point (MH-16).** 9-step pipeline. `route(request)` → `HubResponse`, `stream_route(request)` → `AsyncIterator[HubChunk]`. Rejects invalid/missing capability field, enforces budget limits, queues by priority. |
| `CapabilityRouter` | `services/capability_router.py` | 5-step filtering: capability match → circuit breaker → rate limit → health → placement. Output: `EligibleProvider` list sorted by score. |
| `ModelSelector` | `services/model_selector.py` | Tier-based routing: REALTIME/INTERACTIVE → FAST tier, BACKGROUND → PREMIUM. Health-gated fallback chain (max 3 fallbacks, MH-06). Output: `ModelChoice`, `FallbackEntry`. |
| `ProviderDispatcher` | `services/provider_dispatcher.py` | Dispatch pipeline: CB acquire → rate limit check → credential injection → `plugin.execute()`/`plugin.stream_execute()`. Fallback chain walking (MH-06). |
| `NormalizationLayer` | `services/normalization_layer.py` | Bidirectional: `HubRequest` → `NormalizedRequest` (14 capability extractors), `ProviderResponse` → `HubResponse`. |
| `ProviderRegistry` | `services/provider_registry.py` | Runtime plugin registry + capability→providers index. `register(manifest, plugin)`, `unregister()`, `get_capability_index()`. |
| `ResponseCache` | `services/response_cache.py` | LRU cache. Keys: capability + payload_hash + model_id + temperature. Skip rules: non-cacheable capabilities (TOOL_CALL, etc.). TTL: 5min (MH-09). |
| `CircuitBreakerManager` | `services/circuit_breaker_manager.py` | Per-provider state machine: CLOSED→OPEN→HALF_OPEN. Sliding-window failure counting. Config from provider manifest. MH-05. |
| `RateLimiter` | `services/rate_limiter.py` | Per-provider token bucket (RPM + TPM) with configurable headroom (80% default, MH-12). |
| `AuditLogger` | `services/audit_logger.py` | In-memory circular buffer (10K records). Logs every call with full metadata. MH-11. |

### Provider Plugins (`plugins/` — 7 production + 2 test)

| Plugin | File | Provider | Auth | Notes |
|--------|------|----------|------|-------|
| `VertexPlugin` | `plugins/vertex_plugin.py` | Vertex AI / Gemini Enterprise Agent Platform | ADC/service account or API key | **PRODUCTION DEFAULT.** Extends `GooglePlugin`. Uses `google-genai` SDK. gemini-3.5-flash (Front/Back), gemini-2.5-flash-lite (MemoryWriter, SectionUpdate). |
| `GooglePlugin` | `plugins/google_plugin.py` | Google Gemini (AI Studio) | API key | Base class for Vertex. Thinking budget, tool calling, streaming, structured JSON output. Prompt dump support. |
| `OpenAIPlugin` | `plugins/openai_plugin.py` | OpenAI | Bearer token | Chat Completions + Embeddings. SSE streaming. Reasoning models (o3, o4-mini) with `reasoning_effort`. |
| `AnthropicPlugin` | `plugins/anthropic_plugin.py` | Anthropic | `x-api-key` header | Messages API. Extended thinking. Token counting. |
| `OllamaPlugin` | `plugins/ollama_plugin.py` | Ollama (self-hosted) | None | Native `/api/chat`. NDJSON streaming. Embeddings via `/api/embed`. |
| `VLLMPlugin` | `plugins/vllm_plugin.py` | vLLM (self-hosted) | None or `--api-key` | OpenAI-compatible `/v1/*` endpoints. Health via `/health`. |
| `StubProviderPlugin` | `plugins/stub_plugin.py` | In-process stub | None | **TEST MODE ONLY.** Supports ALL capabilities. Returns canned "OK" text. Never emits tool_calls. Coarse word-count token estimates. |
| `TestProviderPlugin` | `plugins/test_plugin.py` | Deterministic test | None | Fully configurable. Records all calls (`ExecuteCall`). Failure injection, delay simulation, canned responses. |

**Plugin Protocol (`IProviderPlugin`):** `initialize(manifest)`, `supports(capability)`, `execute(request)` → `ProviderResponse`, `stream_execute(request)` → `AsyncIterator[ProviderChunk]`, `estimate_tokens(messages)`, `health_check()` → `ProviderHealth`, `close()`.

### Production Adapters (`adapters/` — 9 adapters)

| Adapter | File | Implements | Purpose |
|---------|------|-----------|---------|
| `CredentialStoreAdapter` | `adapters/credential_store_adapter.py` | `ICredentialPort` | ADC/service-account key resolution. Override dict → env `MH_KEY_<PROVIDER_ID>`. MH-02: keys NEVER in manifest. |
| `EventBusAdapter` | `adapters/event_bus_adapter.py` | `IEventPort` | K1 bus pub/sub. Standalone mode: in-memory. Production: forwards to `IBus`. |
| `SessionStateProdAdapter` | `adapters/session_state_prod.py` | `IStateReadPort` | Real SS reads via `SessionStateManager`. `persona` + `control` sections. MH-01: NO writes. |
| `PrometheusAdapter` | `adapters/prometheus_adapter.py` | `IMetricsPort` | In-memory accumulator: counters, histograms, gauges. |
| `ConfigAdapter` | `adapters/config_adapter.py` | `IConfigPort` | YAML from `k1/config/model_hub.yaml` + env overrides. Hot-reload via `watch()`. |
| `HealthReportAdapter` | `adapters/health_report_adapter.py` | `IHealthPort` | In-memory status tracking. Aggregates sub-component health. |
| `LLMRequestBusAdapter` | `adapters/llm_request_bus_adapter.py` | `IModelHubPort` | Bridges K1 LLM Request Bus → Model Hub. Wraps inner `IModelHubPort`. |
| `BusEnvelopeDeserializer` | `adapters/bus_envelope_deserializer.py` | — | Subscribes to `TOPIC_HUB_EXECUTE` on K1 bus, deserializes → `HubRequest`, publishes response on `TOPIC_HUB_RESPONSE`. |
| `SessionStateReadAdapter` | `adapters/session_state_read_adapter.py` | `IStateReadPort` | Stub: in-memory dict. Empty snapshot on error. |

### Factory (`factory.py`)

| Method | Returns | Purpose |
|--------|---------|---------|
| `ModelHubFactory.from_config(config, ports)` | `(IModelHubPort, ProviderLoadResult)` | **Recommended production entry point.** Creates hub + loads providers. Never raises on partial failure. |
| `ModelHubFactory.create_standalone(config, plugins)` | `IModelHubPort` | Production mode with real adapters. 11-step wiring sequence. |
| `ModelHubFactory.create_with_ports(ports, config, plugins)` | `IModelHubPort` | Custom mode. Caller-supplied port implementations. Validates via `_validate_ports()`. |
| `ModelHubFactory.create_for_testing(overrides)` | `(IModelHubPort, adapters_dict)` | Test mode. Returns adapters_dict for direct test access. |

### Observability (`events.py`, `metrics.py`, `tracing.py`)

| Component | Purpose |
|-----------|---------|
| 10 event topics | `TOPIC_REQUEST_RECEIVED`, `TOPIC_REQUEST_ROUTED`, `TOPIC_RESPONSE_COMPLETE`, `TOPIC_CACHE_HIT`, `TOPIC_PROVIDER_FAILURE`, `TOPIC_FALLBACK_TRIGGERED`, `TOPIC_CIRCUIT_STATE`, `TOPIC_PROVIDER_HEALTH`, `TOPIC_PROVIDER_REGISTERED`, `TOPIC_CAPABILITY_AVAILABLE` |
| 5 counters | `hub_requests_total`, `hub_errors_total`, `hub_cache_hits_total`, `hub_fallbacks_total`, `hub_budget_rejections_total` |
| 4 histograms | `hub_latency_ms`, `provider_latency_ms`, `hub_tokens_used`, `hub_cost_usd` |
| 2 gauges | `hub_active_requests`, `provider_circuit_state` |
| 34 trace phases | Structured JSON log phases covering full 9-step pipeline + lifecycle + circuit breaker events. PII/API-key redaction built in. |

### Invariants

| ID | Rule |
|----|------|
| MH-01 | IStateReadPort is READ-ONLY — no write methods |
| MH-02 | API keys live in CredentialStore ONLY, never in manifest YAML |
| MH-03 | trace_id required on every HubRequest |
| MH-05 | Circuit breaker per provider, config from manifest |
| MH-06 | Capability-aware fallback chain, max 3 providers |
| MH-09 | Response cache TTL = 5 minutes |
| MH-11 | Full audit trail (10K in-memory circular buffer) |
| MH-12 | Rate limit headroom = 80% of declared limits |
| MH-16 | ALL LLM traffic through single IModelHubPort gateway |
| MH-17 | Plugin isolation — one plugin per provider, no shared state |
| MH-18 | Provider manifest is sole source of capability truth |

---

# S2.5 — HumanInTheLoopService

**File:** `k1/hil/` — service.py, config.py, safety.py, ledger.py, suspension.py, sqlite_writer.py, topics.py, types.py, adapters/, ports/
**Init:** `_startup_tier1()` L1727 — `HumanInTheLoopService(event_port, ledger, suspension_mgr, safety_policy, config, llm_port=None)`
**Config gate:** `enable_hil_service` (True in production)
**Lifecycle:** Shared instance, wired into Fabric/Concierge/Planner/Orchestrator. **Two instances:** one kernel-level (S2.5, on kernel bus, serves Orchestrator/Planner/shared-Fabric) and one per-session (P1.5, on session bus, serves Concierge + per-session Fabric).
**Architecture:** Unified HIL coordinator handling 5 request kinds through a single publish/await pattern over the bus. Safety decisions are pure-function, stateless.

## Architecture Flow

```
Caller (Back/Planner/Fabric/Orchestrator)
  → svc.<method>(request)
    → SafetyBandPolicy.decide() [gate only]
    → _request() publishes HILEnvelope on k1.hil.request.v1
      → ConciergeController._on_hil_request()
        → persist pending_hil_data → CLARIFYING_WORKER → Front HITL_RELAY
          → User responds
            → Front publishes HILResponseEnvelope on k1.hil.response.v1
              → svc._on_response() resolves asyncio.Future
                → Caller's await returns typed response
```

## Sub-Components

### Core Types (`types.py` — 5 enums + 16 dataclasses)

| Type | Purpose |
|------|---------|
| `HILKind` (Enum) | Discriminator: `CLARIFICATION`, `APPROVAL`, `NEEDS_HUMAN`, `OVERRIDE`, `CAPABILITY_GATE` |
| `GateOutcome` (Enum) | Gate decision: `ALLOW`, `DENY`, `ASK_APPROVED`, `ASK_REJECTED`, `TIMEOUT` |
| `ClarificationRequest` | Planner SKETCH ambiguity resolution |
| `ApprovalRequest` | Planner VALIDATE high-impact plan approval |
| `NeedsHumanRequest` | Concierge Back→FSM clarification/approval/selection |
| `OverrideRequest` | Orchestrator ConstraintResolver fallback |
| `CapabilityGateRequest` | Fabric pre-execution gate check. Carries `CapabilityContractView`. |
| `ClarificationResponse` | `answer`, `timed_out`, `round_budget_exhausted` |
| `ApprovalResponse` | `decision` (approve/modify/reject), `modifications` |
| `NeedsHumanResponse` | `decision`, `resolution`, `raw_user_text` |
| `OverrideResponse` | `choice` (override/fallback/abort), `selected_alternative` |
| `GateDecision` | `outcome`, `hil_request_id`, `reason`, `user_approved`, `audit_only` |
| `HILEnvelope` | **Outbound** on `k1.hil.request.v1`. `to_dict()`/`from_dict()` serialization. |
| `HILResponseEnvelope` | **Inbound** on `k1.hil.response.v1`. `to_dict()`/`from_dict()`. |
| `HILPresentedEnvelope` | Presentation ack on `k1.hil.presented.v1` (GAP-HIL-009). Front publishes when prompt is rendered. |
| `HILRequestedEvent` | Ledger: request opened. |
| `HILResolvedEvent` | Ledger: request closed by user/system. Carries `resolver_id`. |
| `HILTimedOutEvent` | Ledger: watcher fired before resolution. |
| `HILBlockedEvent` | Ledger: request rejected before reaching user. |

### Service (`service.py`)

| Component | Purpose |
|-----------|---------|
| `HumanInTheLoopService` | **Unified HIL coordinator.** Constructor: `event_port`, `ledger`, `suspension_mgr`, `safety_policy`, `config`, optional `llm_port`. All five HIL kinds go through the same publish/await pattern. |
| `ask_clarification(req)` → `ClarificationResponse` | Planner SKETCH. Round budget enforcement per `caller_key`. Optional LLM question synthesis. |
| `request_approval(req)` → `ApprovalResponse` | Planner VALIDATE. High-impact plan approval. |
| `needs_human(req)` → `NeedsHumanResponse` | Concierge Back→FSM. Suspends BEFORE publishing (crash-recovery). |
| `request_override(req)` → `OverrideResponse` | Orchestrator ConstraintResolver. Fallback resolution. |
| `gate_capability(req)` → `GateDecision` | Fabric pre-execution. Runs `SafetyBandPolicy.decide()` first. ALLOW short-circuits without bus publish. |
| `reset_round_budget(caller_key)` | Clear clarification round counter. Called by Planner lifecycle hooks. |
| `get_counters()` → dict | Shallow copy: `unknown_id`, `legacy_bridge_ignored`, `resolved`, `timed_out`. |
| `shutdown()` | Unsubscribe all topics, cancel all pending futures. Idempotent. |
| `_request(kind, caller_key, trace_id, payload, timeout_ms)` | **Internal core.** Create envelope → create Future → register in `_pending` → write ledger → publish on bus → two-phase wait (presentation ack + human response, GAP-HIL-009) → handle timeout → cleanup. |
| `_on_presented(topic, data)` | GAP-HIL-009: resolves presentation Future when Front acks prompt is visible. |
| `_on_response(topic, data)` | Subscribed to `k1.hil.response.v1`. Parses response, resolves pending Future, handles unknown/legacy IDs. |

### Safety Policy (`safety.py`)

| Component | Purpose |
|-----------|---------|
| `SafetyDecision` (Enum) | `ALLOW`, `ASK`, `DENY` (reserved, not used today) |
| `SafetyBandPolicy` | **Pure-function, stateless policy.** `decide(contract, params)` implements the decision matrix: explicit `requires_human_confirmation=True` → ASK; explicit False → ALLOW (except RED/CRISIS always ASK); inferred: GREEN+no side_effects → ALLOW, GREEN+side_effects → ASK, AMBER → ASK, RED → ASK, CRISIS → ASK. Also `is_audit_only(contract)` for governance-flagged outcomes. |

**Decision matrix:**

- RED/CRISIS → always ASK (explicit False cannot override down)
- Explicit `requires_human_confirmation=True` → ASK
- Explicit False on non-restricted band → ALLOW
- AMBER → ASK (inferred)
- GREEN + side_effects → ASK (escalate)
- GREEN + no side_effects → ALLOW

### Configuration (`config.py`)

| Field | Default | Purpose |
|-------|---------|---------|
| `max_clarification_rounds` | 2 | Max planner clarification rounds |
| `clarification_timeout_ms` | 60000 | SKETCH clarification timeout |
| `approval_timeout_ms` | 120000 | VALIDATE approval timeout |
| `needs_human_timeout_ms` | 60000 | Back needs_human timeout |
| `override_timeout_ms` | 60000 | Orchestrator override timeout |
| `capability_gate_timeout_ms` | 120000 | Fabric capability gate timeout |
| `enable_audit_topic` | False | Emit to `k1.hil.audit.v1` |
| `enable_llm_synthesis` | False | LLM-synthesized natural-language questions |
| `require_presentation_ack` | False | GAP-HIL-009: wait for Front ack before arming timer |
| `presentation_timeout_ms` | 5000 | Max wait for presentation ack |
| `enable_front_fast_path` | True | GAP-HIL-007: direct Front relay |
| `enable_llm_relay_rewrite` | False | LLM rewrite of relay messages |

### Suspension Manager (`suspension.py`)

| Component | Purpose |
|-----------|---------|
| `SuspensionManager` | **FSM-side suspension lifecycle.** Coordinates Back→SUSPENDED→Front→user→resume→Back. Enforces: max 2 suspensions per task, max 1 concurrent, per-type timeouts. |
| `suspend(request, ledger)` | Validate limits, write-before-mutate to ledger, start timeout watcher |
| `resolve(resolution, ledger)` | Cancel timeout, return original request for Back resume |
| `_watch_timeout(task_id, timeout)` | Auto-cancel on timeout |
| `is_suspended(task_id)` | Check if task currently suspended |
| `get_request(task_id)` | Get active suspension request |
| `active_count` (property) | Number of active suspensions |
| `cleanup_task(task_id)` | Full state cleanup |
| `store_context/pop_context/get_context/has_context(task_id)` | Sync context management for FSM controller |
| `set_ledger(writer)` | Attach ledger post-construction (M9 E9.2.1) |
| `rebuild_from_events(entries)` | Rebuild state from ledger events after crash (M9 E9.2.4) |

### Ledger (`ledger.py`)

| Component | Purpose |
|-----------|---------|
| `HILLedgerAdapter` | **Best-effort persistence wrapper.** `write_requested(env)`, `write_resolved(env, resp)`, `write_timed_out(env)`, `write_blocked(env, reason)`. Failures logged, never raised. Duck-types `write_event`/`append`/`write` interface shapes. |

### SQLite Writer (`sqlite_writer.py`)

| Component | Purpose |
|-----------|---------|
| `SQLiteHILEventWriter` | **Append-only SQLite store for crash-safe HIL event replay.** Schema: `hil_events(id, hil_request_id, event_type, timestamp_ms, resolver_id, payload)`. Methods: `append(event)`, `append_sync`, `read_all(hil_request_id)`, `pending_request_ids()` (crash-recovery replay), `close()`. Thread-safe via `threading.Lock`. |

### Topics (`topics.py`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `TOPIC_HIL_REQUEST` | `k1.hil.request.v1` | Outbound to user (Front bridge subscribes) |
| `TOPIC_HIL_RESPONSE` | `k1.hil.response.v1` | Inbound from user (service subscribes) |
| `TOPIC_HIL_AUDIT` | `k1.hil.audit.v1` | Optional audit stream |
| `TOPIC_HIL_PRESENTED` | `k1.hil.presented.v1` | Presentation ack (GAP-HIL-009) |

**Caller-key namespaces:** `planner:<plan_id>`, `concierge:<task_id>`, `orchestrator:<plan_id>`, `fabric:<capability_name>`, `back:<task_id>`.

### Ports (`ports/`)

| Protocol | File | Purpose |
|----------|------|---------|
| `IEventPort` | `ports/event_port.py` | `@runtime_checkable`. `publish(topic, payload)`, `subscribe(topic, handler)` → `SubscriptionHandle`, `unsubscribe(handle)`. HIL-local minimal bus surface. |
| `ILLMPort` | `ports/llm_port.py` | `@runtime_checkable`. `synthesize_question(context, max_tokens, trace_id)` → `str | None`. Best-effort LLM access for natural-language question synthesis. |

### Adapters (`adapters/`)

| Adapter | File | Purpose |
|---------|------|---------|
| `KernelHILEventAdapter` | `adapters/event_bus.py` | Bridges K1 sync `IBus` to HIL-local async `IEventPort`. Serializes dict→JSON bytes on publish. Wraps sync bus handlers to deserialize and schedule async handlers via `asyncio.run_coroutine_threadsafe`. Thread-safe via `threading.RLock`. |

---

## Where HIL Is Consumed

### Injection Points (from `k1/kernel/service.py`)

| Consumer | HIL Instance | Bus | Purpose |
|----------|-------------|-----|---------|
| Shared Fabric | Kernel-level (S2.5) | Kernel bus | Pre-execution capability gating |
| OrchestratorService | Kernel-level (S2.5) | Kernel bus | ExecutionMonitor override requests |
| PlannerAgent | Kernel-level (S2.5) | Kernel bus | SKETCH clarification + VALIDATE approval |
| ConciergeRuntime | Per-session (P1.5) | Session bus | Back needs_human → FSM → Front rendering |
| Per-session Fabric | Per-session (P1.5) | Session bus | Session-scoped capability gates |

### Concierge FSM HIL Flow

1. **FSM subscribes** to `k1.hil.request.v1` → `_on_hil_request()` handler (line 1335)
2. Parses `HILEnvelope`, extracts `hil_request_id`, `kind`, `caller_key`, payload
3. `NEEDS_HUMAN` binds to back task's `task_id`; other kinds synthesize transient slot `hil:{hil_request_id}`
4. Persists `pending_hil_data` on TaskBridge with full envelope dict
5. Transitions to `CLARIFYING_WORKER`, delivers to Front for `HITL_RELAY` rendering
6. Front publishes `HILResponseEnvelope` on `k1.hil.response.v1`
7. `HumanInTheLoopService._on_response()` resolves the awaiting Future
8. Back `react_loop` resumes with HIL answer injected as message

### Fabric Capability Gate

1. `CapabilityFabric._run_hil_gate()` called at Step 2.5 of execute pipeline (BEFORE provider execution)
2. Builds `CapabilityGateRequest` with `view_from_capability_contract(contract)`
3. Calls `hil_port.gate_capability(gate_req)`
4. `ALLOW`/`ASK_APPROVED` → proceed; `DENY`/`ASK_REJECTED`/`TIMEOUT` → blocks pipeline with failure result
5. If `hil_port is None` → gate disabled, always allow

### Planner HIL Usage

- **SKETCH**: `ask_clarification()` for ambiguity resolution, enforces round budget (max 2)
- **VALIDATE**: `request_approval()` for high-impact plan approval
- **Lifecycle**: `reset_round_budget(caller_key)` on plan completion/cancellation

### Orchestrator HIL Usage

- **ExecutionMonitor**: `request_override()` for wave-level override prompts when constraints are violated
- **ConstraintResolver**: Fallback resolution when automated resolution fails

### Back Unified HIL (live path)

1. `react_loop` returns `status="suspended"`
2. `_resolve_needs_human_in_process()` calls `hil_port.needs_human(NeedsHumanRequest(...))`
3. Service suspends via `SuspensionManager`, publishes envelope, awaits Future
4. On response, `_resume_task_after_unified_hil()` converts response to message, re-enters `react_loop`

---

# S2.6 — SelfModelServiceBundle

**File:** `k1/selfmodel/` — kernel/bootstrap.py, kernel/handle.py, service/ (11 files), adapters/ (12 files), contracts/ (13 files), ports/ (11 files), events/, obs/, migrations/
**Init:** `_startup_tier1()` L1766 — `build_self_model_bundle(bus=async_bus, hil_service=..., projection_db_path=..., space_id=...)`
**Config gate:** `enable_self_model` (True in production)
**Lifecycle:** Shared bundle built once at S2.6. Per-session `SelfModelHandle` built at P3.5 referencing this bundle.
**Architecture:** 5-layer projection model — L1 (Identity), L2 (Preferences/Routines/Hobbies/Goals), L3 (Patterns/Habits), L4 (Session ephemera), L5 (Perception). Policy evaluation is conscience-first (M8+): forbidden_acts → must_ask_acts → tier_floor → risk_overrides → legacy matrix.

## Sub-Components

### Kernel Wiring (`kernel/`)

| Component | File | Purpose |
|-----------|------|---------|
| `SelfModelServiceBundle` | `kernel/bootstrap.py` | **Tier-1 container.** Holds all shared selfmodel services: store, self_model, space_graph, constitution, composer, evaluator, identity, amendments, validator, capsule_builder, citation_builder. Owns projection store lifecycle. |
| `build_self_model_bundle()` | `kernel/bootstrap.py` | Factory. 12-step build: projection store → validator → bootstrap constitution → ConstitutionService → SelfModelService → SpaceGraphService → SituationFrameComposer → PolicyEvaluator → IdentitySessionManager → AmendmentService → GroundingCapsuleBuilder → CitationPackBuilder. |
| `SelfModelHandle` | `kernel/handle.py` | **Per-session handle.** Holds reference to bundle + session identity. Creates `ConciergePolicyGate` and `GroundingCapsuleRenderer`. `install_into_session()` / `uninstall_from_session()`. |
| `build_self_model_handle()` | `kernel/handle.py` | Factory. Creates frame provider closure → `ConciergePolicyGate` → `GroundingCapsuleRenderer`. |
| `DEFAULT_SITUATION_KIND` | `kernel/handle.py` | `"caregiver_context_briefing"` (S12 — broadest read-only V0 situation) |

### Service Layer (`service/` — 11 files)

| Component | File | Purpose |
|-----------|------|---------|
| `SelfModelService` | `service/self_model.py` | Thread-safe reader/writer for S(actor) 5-layer projection. Reads L1/L2/L3 from store; maintains RAM-only L4/L5. Seeds L1/L2 from SS `MetaSection.identity` on first touch. |
| `SpaceGraphService` | `service/space_graph.py` | Projects space-graph snapshot for viewing actor — filters edges adjacent to actor, subsets members per visibility rules. |
| `ConstitutionService` | `service/constitution.py` | Read-only service over active constitution row. Optionally validates signature chain; enters safe-mode if chain validation fails. |
| `SituationFrameComposer` | `service/situation_composer.py` | Stateless composer: `S(actor) ∩ F(space) ∩ C(constitution)` at `(T, D, situation_kind)`. 6 Empty-Set Invariants. p95 ≤ 5ms. |
| `PolicyEvaluator` | `service/policy_evaluator.py` | Pure-function evaluator. Conscience-first (M8+): `forbidden_acts` → `must_ask_acts` → `tier_floor` → `risk_overrides` → legacy matrix. |
| `AmendmentService` | `service/amendment.py` | DRAFT→PENDING→APPROVED→ACTIVE FSM for constitution amendments. Quorum-gated activation. |
| `ensure_bootstrap_constitution()` | `service/bootstrap_constitution.py` | Idempotent first-run loader. Loads YAML, signs with synthetic Ed25519 key, writes ACTIVE row. |
| `IdentitySessionManager` | `service/identity_session.py` | Tier-aware session manager. Hard TTL (12h default). Supports PIN (scrypt) + passkey (Ed25519) verification. |
| `Ed25519SignatureChainValidator` | `service/signature_chain.py` | Validates Ed25519 signatures on canonical JSON body. Parent-chain walking, signer registration, quorum enforcement. |
| `GroundingCapsuleBuilder` | `service/capsule_builder.py` | Pure renderer: `SituationFrame` → `GroundingCapsule`. 2KB hard cap, BLACK redaction, freshness footer. M7 typed blocks. |
| `CitationPackBuilder` | `service/citation_builder.py` | Wraps recall hits → `CitationPack` with provenance (source_layer, revision, freshness, confidence). |

### Adapters (`adapters/` — 12 files)

| Adapter | File | Purpose |
|---------|------|---------|
| `ConciergePolicyGate` | `adapters/concierge_policy_gate.py` | **Step-0 hook for ToolDispatcher.** Wires `PolicyEvaluator` + `SituationFrame` + HIL + IBus. Returns `None` on ALLOW, `ToolResult` on block. Unwraps `invoke_capability` wrappers. |
| `GroundingCapsuleRenderer` | `adapters/grounding_capsule_renderer.py` | Renders capsule block for Front prompt builder. Called by `DynamicPromptBuilder` at OPP-7 stage. Outputs self-block (name, role, preferences, routines, conscience digest). |
| `FabricRiskCatalog` | `adapters/fabric_risk_catalog.py` | Maps Fabric capability registry → `RiskClass` per capability. Fail-closed: unknown → `RiskClass.HIGH`. |
| `InMemoryProjectionStore` | `adapters/memory_projection_store.py` | RAM-only store for tests. |
| `SQLiteProjectionStore` | `adapters/sqlite_projection_store.py` | Production projection store. Schema: self/space/constitution projections. |
| `ConstitutionConsciencePort` | `adapters/constitution_conscience_port.py` | Derives `ConscienceDigest` from constitution body (M10). |
| `RecallCitationWrapper` | `adapters/recall_citation_wrapper.py` | Wraps concierge `recall_fn` → `CitationPack` (M5 P3.5). |
| `Ed25519CredentialVerifier` | `adapters/credential_verifier.py` | PIN (scrypt) + passkey (Ed25519) verification. |
| `BridgeAmendmentSyncAdapter` | `adapters/bridge_amendment_sync.py` | K1↔K0 amendment sync via bridge (M4). |
| `L3PortBundle` | `adapters/l3_ports.py` | 7 narrow L3 reader/writer adapters (M10). |
| `StaticRiskCatalog` | `adapters/fabric_risk_catalog.py` | In-memory fallback risk catalog. |

### Contracts (`contracts/` — 13 files)

| Contract | Purpose |
|----------|---------|
| `SituationFrame` | S(actor) ∩ F ∩ C at (T, D, situation_kind). Main policy input. |
| `K1SelfModelSnapshot` | 5-layer projection: L1 Identity, L2 Preferences/Routines, L3 Patterns, L4 Session, L5 Perception. |
| `SpaceGraphSnapshot` | Family space members, edges, routines. |
| `ConstitutionSnapshot` | Active constitution with signature chain, body V1 keys. |
| `ConscienceDigest` | Derived from constitution: forbidden_acts, must_ask_acts, tier_floor, risk_overrides. |
| `PolicyVerdict` | Gate outcome: ALLOW, ASK, DENY with ReasonCode. |
| `RiskClass` | LOW, MEDIUM, HIGH, CRITICAL per capability. |
| `GroundingCapsule` | Prompt-safe SituationFrame block (2KB cap). |
| `CitationPack` | Provenance-rich memory references. |
| `AmendmentProposal` | DRAFT→PENDING→APPROVED→ACTIVE amendment lifecycle. |
| `IdentityTier` | Tier-aware session identity. |
| `DEFAULT_DECISION_MATRIX` | 5-step conscience-first evaluation matrix. |
| Bootstrap V1 YAML | `bootstrap_constitution.v1.yaml` — conscience-first constitution. |

### Ports (`ports/` — 11 files)

| Port | Purpose |
|------|---------|
| `IConsciencePort` | Digest-only conscience access. |
| `IConstitutionPort` | Constitution amendment lifecycle. |
| `ICredentialPort` | Verify PIN/passkey/webauthn credentials. |
| `IIdentityPort` | Identity sessions + tier + device context. |
| `IPolicyPort` | Gate evaluator backed by SituationFrame. |
| `IProjectionStorePort` (ABC) | Durable read/write of 5-layer projections. |
| `IRiskCatalogPort` | Per-capability risk + social-act metadata. |
| `ISelfSpacePort` | Read self / space-graph snapshots. |
| `ISituationFramePort` | Compose S∩F∩C at (T,D,situation). |
| `IPreferenceReader` et al. | 13 narrow L3 preference reader/writer ports. |

### Events & Observability (`events/`, `obs/`)

| Component | Purpose |
|-----------|---------|
| 17 topic constants | `k1.selfmodel.startup.complete.v1`, `k1.selfmodel.safe_mode.active.v1`, `k1.selfmodel.policy.verdict.v1`, etc. |
| `PolicyVerdictEvent` | Published on every gate decision. |
| `SelfModelMetrics` | Typed emitters: composer latency, policy verdicts, amendment proposals. |
| `trace_span()` | Fail-soft OpenTelemetry span contextmanager. |

---

## Per-Session Install Flow (P3.5 → Concierge)

1. `build_self_model_handle()` creates handle with `ConciergePolicyGate` + `GroundingCapsuleRenderer`
2. `handle.install_into_session()` installs policy gate on Concierge dispatchers as Step-0 hook
3. `handle.render_capsule()` called by `DynamicPromptBuilder` at OPP-7 stage to inject self-block into Front prompt
4. On every `invoke_capability`, policy gate evaluates: `SituationFrame` → `PolicyEvaluator` → ALLOW/ASK/DENY
5. If ASK → gate uses `HumanInTheLoopService` for user confirmation (ConscienceGate flow)
6. `handle.uninstall_from_session()` on session teardown

## Policy Evaluation (Conscience-First Matrix)

```
1. forbidden_acts: does the capability name match a forbidden pattern? → DENY
2. must_ask_acts: does it match must_ask? → ASK (HIL confirmation)
3. tier_floor: does caller's tier satisfy the capability's minimum tier? → DENY if below
4. risk_overrides: does the RiskCatalog classify this as HIGH/CRITICAL? → ASK
5. Legacy matrix: GREEN+no_side_effects → ALLOW, AMBER → ASK, RED → ASK
```

---

# S2.7 — TemporalServiceBundle

**File:** `k1/temporal/` — kernel/bootstrap.py, kernel/handle.py, service/ (3 files), adapters/ (1 file), ports/ (2 files), contract/ (1 file)
**Init:** `_startup_tier1()` L1800 — `build_temporal_bundle(bus=bus, device_context_port=DeviceContextAdapter(device_context_port))`
**Config gate:** `enable_temporal` (True when `K1_ENABLE_TEMPORAL=true`)
**Lifecycle:** Shared bundle built once at S2.7. Per-session `TemporalHandle` built at P3.6 referencing this bundle.
**Architecture:** Clock + device timezone → temporal grounding → "now" block injected into Front/Back prompts. Refreshes every turn from device context. 11-dimensional temporal context: now_utc, now_local, timezone, local_date, day_of_week, week_start, week_end, tomorrow, next_week_start, weekend_start, weekend_end.

## Sub-Components

### Kernel Wiring (`kernel/`)

| Component | File | Purpose |
|-----------|------|---------|
| `TemporalServiceBundle` | `kernel/bootstrap.py` | **Tier-1 container.** Holds: `TemporalClock` (shared), `TemporalNowRenderer` (shared), `_bus` (for event publishing). |
| `build_temporal_bundle()` | `kernel/bootstrap.py` | Factory. Creates `TemporalClock` + `TemporalNowRenderer`, publishes `k1.temporal.service.ready.v1`. Parameters: `bus`, `device_context_port`, `clock` (optional IClock callable). |
| `TemporalHandle` | `kernel/handle.py` | **Per-session handle.** Holds reference to bundle + session identity. `install_into_session()` writes temporal section to SS, `refresh_turn()` updates each turn. |
| `build_temporal_handle()` | `kernel/handle.py` | Factory. Creates handle from bundle + session_id + principal_id + device_id + installation_id + state_manager. |

### Service Layer (`service/` — 3 files)

| Component | File | Purpose |
|-----------|------|---------|
| `TemporalClock` | `service/clock.py` | **Core clock service.** Computes "now" (UTC epoch ms → typed NowSnapshot). Pure-function, stateless. Methods: `snapshot(now_epoch_ms, timezone_str)` → `NowSnapshot`, `resolve_temporal_refs(text, anchor)` → dict, `describe_now(anchor)` → human-readable prose block. |
| `NowSnapshot` | `service/clock.py` | Frozen dataclass with 16 fields: `now_utc_iso`, `now_local_iso`, `timezone` (IANA), `date`, `day_of_week`, `weekday_name`, `week_start`, `week_end`, `week_number`, `tomorrow_date`, `tomorrow_weekday`, `next_week_start`, `next_week_end`, `weekend_start`, `weekend_end`, `month_name`. |
| `TemporalAnchor` | `service/anchor.py` | Frozen dataclass: `anchor_id` (UUID), `captured_at_utc`, `now_utc`, `now_local`, `timezone`, `timezone_source` ("device"|"fallback"), `local_date`, `day_of_week`, `weekday_name`, `week_range`, `tomorrow_date`, `tomorrow_weekday`, `next_week_start`, `weekend_dates`, `month_name`. |
| `TemporalNowRenderer` | `service/renderer.py` | Pure renderer: `TemporalAnchor` → human-readable prose (11-sentence natural language block like "It is Wednesday afternoon, Wednesday, June 17, 2026 — the local time is 2:42 PM..."). |
| `TemporalGroundingContext` | `service/grounding_bridge.py` | Bridge between Temporal service and Grounding bundle. Produces `temporal_context` dict for prompt injection. |
| `resolve_temporal_refs()` | `service/clock.py` | Resolves "today", "tomorrow", "next week", "this weekend" to absolute dates. Returns `{key: iso_date}` dict. |

### Device Context (`adapters/`, `ports/`)

| Component | File | Purpose |
|-----------|------|---------|
| `DeviceContextAdapter` | `adapters/device_context_adapter.py` | Wraps `IDeviceContextPort` to extract timezone. Production: reads from `InMemoryDeviceContextPort`. |
| `InMemoryDeviceContextPort` | `k1/kernel/adapters/device_context.py` | Stores device timezone/locale. Set at session creation from device metadata. Default: `"America/Chicago"`. |
| `IDeviceContextPort` | `ports/device_context.py` | Protocol: `get_timezone()` → IANA string, `get_locale()` → locale string. |
| `IClock` | `ports/clock.py` | Protocol: `__call__()` → epoch milliseconds. Default: `int(time.time() * 1000)`. |

### Contract (`contract/`)

| Contract | File | Purpose |
|----------|------|---------|
| `NowBlock` | `contract/now_block.py` | Rendered prose + structured data for prompt injection. Fields: `rendered` (natural language text), `anchor_id`, `now_utc_iso`, `now_local_iso`, `timezone`, `local_date`, `day_of_week`. |

---

## Temporal Flow (Per-Turn)

```
1. Device sends timezone + locale in WebSocket handshake
   → InMemoryDeviceContextPort stores "America/Chicago"
2. Each turn: TemporalHandle.refresh_turn(session_id, device_id, installation_id)
   → InMemoryDeviceContextPort.get_timezone() → "America/Chicago"
   → IClock() → epoch_ms
   → TemporalClock.snapshot(epoch_ms, "America/Chicago") → NowSnapshot
   → TemporalAnchor captures snapshot with anchor_id UUID
   → SSM temporal section written with anchor
3. Grounding: GroundingHandle reads temporal anchor
   → TemporalNowRenderer.render(anchor) → 11-sentence prose block
   → Injected into Front/Back prompts as SITUATIONAL CONTEXT
4. Real-time: "now" block appears in every prompt with live date/time
```

## Prompt Injection

The rendered temporal block appears in both Front and Back prompts:

```
It is Wednesday afternoon, Wednesday, June 17, 2026 — the local time
is 2:42 PM in the America/Chicago timezone (from the user's device).
Today is Wednesday, June 17; tomorrow is Thursday, June 18.
This week runs Monday, June 15 through Sunday, June 21;
next week begins Monday, June 22.
The upcoming weekend is Saturday, June 20 through Sunday, June 21,
and the following weekend starts Saturday, June 27.
```

Also provides structured `temporal_anchor_id` in task dispatch for Back LLM grounding.

---

# S4 — Bridge

**File:** `bridge/` + kernel adapters
**Init:** `_startup_tier1()` L1820
**Lifecycle:** Created before Fabric (S3), used by all downstream components.

**Three modes:**

| Mode | Adapter | Condition |
|------|---------|-----------|
| LIVE | `LiveBridgeAdapter` (HttpBridgeClient) | `k0_endpoint` set |
| OFFLINE | `SinkBridgeAdapter` (outbox mode) | `bridge_enabled=True`, no endpoint |
| DISABLED | `OfflineBridgeAdapter` (null object) | Neither flag set |

**Production default:** OFFLINE (SinkBridgeClient). K0 operations queue to `./data/bridge_outbox.db`.

---

# S2.8 — SpatialServiceBundle

**File:** `k1/spatial/` — 47 Python files: kernel/ (3 files), service/ (16 files), adapters/ (13 files), ports/ (10 files), plus types/config/events/factory/serialization
**Init:** `_startup_tier1()` L1880 — `build_spatial_bundle(bus=bus, device_context_port=SpatialDeviceContextAdapter(device_context_port), bridge_client=...)`
**Config gate:** `enable_spatial` (True by default after M3 exit gate; currently gated off in production pending M3 completion)
**Lifecycle:** Shared bundle built once at S2.8. Per-session `SpatialHandle` built at P3.7 referencing this bundle. Shutdown between Grounding and Temporal (L701).
**Architecture:** Full hexagonal ports & adapters. 10 protocol ports, 13 adapter implementations, 16 pure-logic service files. Central orchestrator (`SpatialService`) drives a 13-step refresh pipeline: device surface → location fix → place registry → candidate extraction → place resolution (with geofence + reverse-geocode fallback) → presence → context → projection → state persistence → event emission. Privacy engine enforces per-consumer precision (6 levels: hidden → raw) via policy port backed by SelfModel constitution.

## Sub-Components

### Kernel Wiring (`kernel/` — 3 files)

| Component | File | Purpose |
|-----------|------|---------|
| `SpatialServiceBundle` | `kernel/bootstrap.py` | **Tier-1 container.** Frozen dataclass holding: `service` (SpatialService), `renderer`, `config` (SpatialConfig), plus all 10 port references. Method `build_service()` creates per-session SpatialService from shared ports. |
| `build_spatial_bundle()` | `kernel/bootstrap.py` | Factory. Resolves all 10 ports with production defaults: `BrowserDeviceLocationAdapter`, `BridgePlaceRegistryAdapter` (or `LocalPlaceRegistryAdapter` fallback), `NominatimGeocoderAdapter` (gated by `K1_SPATIAL_GEOCODER` env), `NullPresenceAdapter`, `SelfModelSpatialPolicyAdapter`, `SpatialStateAdapter`, `UUIDSpatialIdAdapter`, `SpatialEventBusAdapter`, `NullSpatialMetricsAdapter`. |
| `SpatialHandle` | `kernel/handle.py` | **Per-session facade.** Mutable dataclass structurally satisfying `ISpatialPort`. Holds bundle + `SpatialSessionBinding` + per-session policy port (from SelfModel). Methods: `install_into_session()`, `uninstall_from_session()`, `refresh_turn()`, `get_context()`, `resolve_place()`, `build_projection()`, `get_projection()`, `shutdown()`. Auto-refreshes context on cache miss. |
| `build_spatial_handle()` | `kernel/handle.py` | Factory. Creates `SpatialStateAdapter(ssm)` + `SelfModelSpatialPolicyAdapter(selfmodel_handle)` → `bundle.build_service()` → `SpatialSessionBinding` → `SpatialHandle`. |
| `SpatialSessionBinding` | `kernel/session_binding.py` | Frozen dataclass: `session_id`, `principal_id`, `actor_id`, `device_id`, `installation_id`. |

### Service Layer (`service/` — 16 files)

| Component | File | Purpose |
|-----------|------|---------|
| `SpatialService` | `service/spatial_service.py` | **Central orchestrator.** 13-step `refresh_turn()` pipeline: (1) device snapshot, (2) DeviceSurface resolution, (3) raw location fix, (4) fix normalization, (5) registry places/geofences, (6) candidate extraction, (7) active place resolution (candidate → geofence match → reverse geocode → semantic fallback), (8) co-presence resolution, (9) SpatialContext construction with provenance, (10) SpatialProjection build, (11) state persistence, (12) event emission, (13) return SpatialTurnSnapshot. Also: `get_context()`, `resolve_place()`, `build_projection()`, `health()`, `shutdown()`. |
| `DeviceSurfaceResolver` | `service/device_surface_resolver.py` | Normalizes raw surface labels (browser, phone, tablet, car, hub, watch, voice, desktop, web) → canonical `DeviceSurfaceKind` via `_SURFACE_ALIASES` dict. Extracts capabilities and surface metadata from `DeviceContextSnapshot`. |
| `SpatialEventEmitter` | `service/event_emitter.py` | Converts spatial outcomes → bus events. 5 methods: `context_created()`, `context_refreshed()`, `place_resolved()`, `context_redacted()`, `location_unavailable()`. Gracefully no-ops when event port is None. |
| `match_geofences()` | `service/geofence_matcher.py` | Haversine-based geofence membership. Circle (point-in-radius with accuracy buffer) + polygon (ray-casting). Returns matching `Geofence` tuples. |
| `normalize_location_fix()` | `service/location_normalizer.py` | Validates and normalizes raw location: lat∈[-90,90], lon∈[-180,180], accuracy≥0. Computes confidence from accuracy (≤50m→0.95, ≤250m→0.75, ≤1km→0.45, else 0.25). Redacts when permission≠"granted" or coordinates missing. |
| `normalize_permission_state()` | `service/permission_normalizer.py` | Maps aliases (allow→granted, blocked→denied, private→hidden) → canonical `LocationPermissionState`. `is_location_usable()` → True only for "granted". |
| `DEFAULT_PLACE_ALIASES` | `service/place_alias_catalog.py` | Predefined alias map: home, school, work, vehicle. `normalize_place_label()` + `expanded_aliases()` for fuzzy matching. |
| `candidates_from_*()` | `service/place_candidate_source.py` | 4 candidate extractors: `from_device_context` (semantic_place_hint, conf=0.72), `from_mapping` (task params, conf=0.65), `from_beliefs_active` (mentioned_location, conf≤0.45), `from_session_state` (wraps beliefs extractor). |
| `load_place_registry()` | `service/place_registry_service.py` | Atomically loads places + geofences + metadata via `IPlaceRegistryPort`. Returns `PlaceRegistrySnapshot`. |
| `resolve_place_candidate()` | `service/place_resolver.py` | Matches candidate text against expanded place aliases (label + kind). Merged `PlaceRef` with max confidence. Falls back to `place_id="unknown"` (conf≤0.45). |
| `select_consumer_precision()` | `service/precision_selector.py` | Delegates to `ISpatialPolicyPort.allowed_precision()` if available, then `clamp_precision()` to enforce the stronger of requested vs allowed. Falls back to `DEFAULT_CONSUMER_PRECISION` per consumer. |
| `resolve_presence()` | `service/presence_resolver.py` | Filters presence entries with confidence>0. Returns empty when port is None. |
| `project_context()` | `service/privacy_projector.py` | **Core privacy engine.** Maps precision level → projection: `hidden` (all redacted), `semantic` (label only, no coordinates), `approximate` (rounded coordinates), `place_id` (IDs only), `address`/`raw` (full place_refs + raw_location). Downgrades address-level PlaceRefs to locality labels. Always adds `raw_location_denied` redaction when precision≠"raw". |
| `SpatialProjectionBuilder` | `service/projection_builder.py` | Policy-aware builder. Selects precision → gets redaction reasons → delegates to `build_spatial_projection()`. |
| `render_place_block()` | `service/projection_renderer.py` | Front `== PLACE ==` block: surface, active place, precision, freshness. |
| `render_execution_place_block()` | `service/projection_renderer.py` | Back `== EXECUTION PLACE CONTEXT ==` block: context_id, surface, semantic_place, precision, permission, relevant_places, raw_coordinates, redactions. |
| `render_planning_spatial_block()` | `service/projection_renderer.py` | Planner `== PLANNING SPATIAL ==` block: context_id, semantic_place, precision, freshness, place_ids. |

### Port Protocols (`ports/` — 10 protocols, all `@runtime_checkable`)

| Protocol | File | Methods |
|----------|------|---------|
| `ISpatialDeviceContextPort` | `ports/device_context_port.py` | `get_device_snapshot(session_id, device_id, installation_id) → DeviceContextSnapshot` |
| `IDeviceLocationPort` | `ports/device_location_port.py` | `get_location_fix(session_id, device_id, installation_id) → LocationFix \| None` |
| `ISpatialEventPort` | `ports/event_port.py` | `publish(topic, payload) → None` |
| `IGeocoderPort` | `ports/geocoder_port.py` | `geocode(session_id, candidate) → Sequence[PlaceRef]`, `reverse_geocode(session_id, fix) → Sequence[PlaceRef]` |
| `ISpatialIdPort` | `ports/id_port.py` | `new_context_id()`, `new_place_id()`, `new_geofence_id()`, `new_fix_id()`, `new_projection_id()` → all `str` |
| `ISpatialMetricsPort` | `ports/metrics_port.py` | `incr(name, value, tags)`, `timing(name, value_ms, tags)` |
| `IPlaceRegistryPort` | `ports/place_registry_port.py` | `list_places()`, `list_geofences()`, `member_default_places()`, `timezone_for_place()`, `registry_metadata()` |
| `ISpatialPolicyPort` | `ports/policy_port.py` | `allowed_precision(session_id, consumer, subject_ref, task_scope, capability, requested_precision) → str`, `redaction_reasons(...) → tuple[str, ...]` |
| `IPresencePort` | `ports/presence_port.py` | `list_presence(session_id, subject_ref) → Sequence[PresenceRef]` |
| `ISpatialStatePort` | `ports/state_port.py` | `write_spatial_section()`, `read_spatial_section()`, `write_place_registry_section()`, `read_place_registry_section()` |

### Adapters (`adapters/` — 13 implementations)

| Adapter | File | Implements | Purpose |
|---------|------|-----------|---------|
| `SpatialDeviceContextAdapter` | `adapters/device_context_adapter.py` | `ISpatialDeviceContextPort` | Adapts kernel's generic device-context port → spatial port shape. Type-validates return is `DeviceContextSnapshot`. |
| `BrowserDeviceLocationAdapter` | `adapters/browser_device_location_adapter.py` | `IDeviceLocationPort` | Reads `snapshot.location_fix` from device context. |
| `NullDeviceLocationAdapter` | `adapters/null_device_location_adapter.py` | `IDeviceLocationPort` | Always returns None (explicit location-unavailable). |
| `SpatialEventBusAdapter` | `adapters/event_bus_adapter.py` | `ISpatialEventPort` | JSON-envelope publish on K1 bus with `Priority.INTERACTIVE`. Records `published` list for testability. |
| `NominatimGeocoderAdapter` | `adapters/nominatim_geocoder_adapter.py` | `IGeocoderPort` | OpenStreetMap Nominatim geocoding. Configurable endpoint/user_agent/timeout. Coordinate rounding + reverse-geocode cache. Sync HTTP via `asyncio.to_thread`. |
| `NullGeocoderAdapter` | `adapters/null_geocoder_adapter.py` | `IGeocoderPort` | Always returns empty sequences. |
| `UUIDSpatialIdAdapter` | `adapters/uuid_id_adapter.py` | `ISpatialIdPort` | Prefixed UUID hex IDs: `spatial_`, `place_`, `geofence_`, `fix_`, `spatial_projection_` prefixes. |
| `NullSpatialMetricsAdapter` | `adapters/null_metrics_adapter.py` | `ISpatialMetricsPort` | No-op `incr()` and `timing()`. |
| `LocalPlaceRegistryAdapter` | `adapters/local_place_registry_adapter.py` | `IPlaceRegistryPort` | In-memory registry for standalone/test. Configurable places, geofences, member_defaults, place_timezones. |
| `BridgePlaceRegistryAdapter` | `adapters/bridge_place_registry_adapter.py` | `IPlaceRegistryPort` | Delegates to bridge client for durable storage-backed registry (M5). Duck-types bridge methods; returns empty on unavailable. |
| `SelfModelSpatialPolicyAdapter` | `adapters/selfmodel_policy_adapter.py` | `ISpatialPolicyPort` | Maps SelfModel/constitution decisions → spatial precision. Falls back to `SpatialConfig.consumer_precision` defaults. |
| `NullPresenceAdapter` | `adapters/null_presence_adapter.py` | `IPresencePort` | Always returns empty co-presence. |
| `SpatialStateAdapter` | `adapters/session_state_adapter.py` | `ISpatialStatePort` | Writes spatial/place-registry payloads through SessionState. Supports multiple manager API surfaces with in-memory fallback. |

### Domain Types (`types.py` — 10 dataclasses, all frozen)

| Type | Fields | Purpose |
|------|--------|---------|
| `DeviceSurface` | surface_id, surface_kind, device_id, installation_id, capabilities, metadata | Observed client surface (browser, mobile, car, watch, etc.) |
| `LocationFix` | lat, lon, accuracy, timestamp, permission, source, confidence, altitude, heading, speed, precision, redactions | Raw/approximate location before privacy projection |
| `PlaceRef` | place_id, label, place_kind, confidence, source, aliases, timezone, parent_place_id, geofence_ids | Semantic place reference (10 place kinds: home, school, work, store, vehicle, room, address, street, outdoor, unknown) |
| `Geofence` | geofence_id, place_id, shape, parameters, source, confidence | Policy-safe geofence declaration (circle or polygon) |
| `PlaceCandidate` | raw_text, normalized_text, source, confidence, subject_ref | Structured place evidence from device/task/calendar/conversation |
| `PresenceRef` | subject_ref, place_ref, confidence, source, captured_at_utc | Co-presence signal for a subject at a place |
| `SpatialRedaction` | field, reason, precision | Audit record for hidden/downgraded spatial fields |
| `SpatialContext` | context_id, session_id, active_place, active_device_surface, location_fix, co_presence, freshness, redactions, precision, place_refs, mentioned_places, device_context, provenance | **Authoritative spatial context** for a session |
| `SpatialProjection` | projection_id, context_id, consumer, semantic_place, precision, place_refs, co_presence, raw_location, approximate_location, relevant_place_refs | **Policy-shaped payload** for one downstream consumer |
| `SpatialTurnSnapshot` | context_id, projection, freshness, precision, place_label, timezone | Spatial state written after turn refresh |

### Configuration (`config.py`)

| Field | Default | Purpose |
|-------|---------|---------|
| `context_ttl_ms` | 60000 | Context cache TTL (1 min) |
| `stale_after_ms` | 120000 | Stale threshold (2 min) |
| `default_precision` | `"semantic"` | Fallback precision level |
| `raw_location_allowed_by_default` | False | Raw GPS never exposed by default |
| `unknown_place_label` | `"unknown"` | Label for unresolved places |
| `max_location_age_ms` | 120000 | Max acceptable fix age |
| `max_acceptable_accuracy_m` | 1000 | Max acceptable GPS accuracy |
| `geofence_match_radius_m` | 75 | Default geofence circle radius |
| `approximate_decimal_places` | 2 | Coordinate rounding for "approximate" precision |
| `consumer_precision` | dict | Per-consumer defaults: front→address, back→semantic, planner→place_id, fabric→place_id, agent→semantic, tool→place_id, memory→place_id |

### Precision Levels (6-tier, `constants.py`)

```
hidden < semantic < approximate < place_id < address < raw
```

- **hidden**: No location data exposed. Semantic place downgraded to "unknown".
- **semantic**: Place label only (e.g., "home", "school"). No coordinates, no place_refs.
- **approximate**: Semantic label + rounded lat/lon (2 decimal places).
- **place_id**: PlaceRef IDs available. No raw coordinates.
- **address**: Full address-level place details. PlaceRefs with labels.
- **raw**: Full `raw_location` (LocationFix) exposed. All place_refs available.

### Serialization (`serialization.py`)

Bidirectional dict conversion for all 10 domain types: `device_surface_to_dict`/`dict_to_device_surface`, `location_fix_to_dict`/`dict_to_location_fix`, `place_ref_to_dict`/`dict_to_place_ref`, `geofence_to_dict`/`dict_to_geofence`, `place_candidate_to_dict`/`dict_to_place_candidate`, `presence_ref_to_dict`/`dict_to_presence_ref`, `redaction_to_dict`/`dict_to_redaction`, `spatial_context_to_dict`/`dict_to_spatial_context`, `spatial_projection_to_dict`/`dict_to_spatial_projection`, `turn_snapshot_to_dict`/`dict_to_turn_snapshot`.

### Events (`events.py` — 5 topics)

| Topic Constant | Value | Payload |
|---------------|-------|---------|
| `SPATIAL_CONTEXT_CREATED` | `k1.spatial.context.created.v1` | `SpatialContextCreatedPayload` |
| `SPATIAL_CONTEXT_REFRESHED` | `k1.spatial.context.refreshed.v1` | `SpatialContextRefreshedPayload` |
| `SPATIAL_PLACE_RESOLVED` | `k1.spatial.place.resolved.v1` | `SpatialPlaceResolvedPayload` |
| `SPATIAL_CONTEXT_REDACTED` | `k1.spatial.context.redacted.v1` | `SpatialContextRedactedPayload` |
| `SPATIAL_LOCATION_UNAVAILABLE` | `k1.spatial.location.unavailable.v1` | `SpatialLocationUnavailablePayload` |

### Factory (`factory.py`)

| Method | Returns | Purpose |
|--------|---------|---------|
| `SpatialFactory.create_standalone(config)` | `SpatialServiceBundle` | Unknown-device standalone mode (no device context port needed) |
| `SpatialFactory.create_for_testing(config, **overrides)` | `(bundle, adapters_dict)` | Test mode with adapter overrides |
| `SpatialFactory.create_production(...)` | `SpatialServiceBundle` | Production bundle from explicit ports |
| `SpatialFactory.create_with_ports(...)` | `SpatialServiceBundle` | Core wiring; validates all 10 ports, constructs SpatialService |

---

## Spatial Refresh Pipeline (Per-Turn)

```
1. Device sends WebSocket handshake with device metadata
   → InMemoryDeviceContextPort stores device_id, installation_id, locale, timezone
2. Each turn: SpatialHandle.refresh_turn(session_id, consumer="front")
   → SpatialDeviceContextAdapter.get_device_snapshot() → DeviceContextSnapshot
   → DeviceSurfaceResolver.resolve() → DeviceSurface (surface_kind, capabilities)
3. BrowserDeviceLocationAdapter.get_location_fix()
   → snapshot.location_fix (raw GPS from browser Geolocation API)
   → normalize_location_fix() validates coords, computes confidence
4. Place Registry: load_place_registry() → places + geofences
5. Candidate extraction: candidates_from_device_context() → PlaceCandidate
6. Place resolution (cascade):
   a. resolve_place_candidate() — text → PlaceRef via alias matching
   b. match_geofences() — location fix → geofence membership
   c. NominatimGeocoderAdapter.reverse_geocode() — lat/lon → address
   d. _fallback_place_from_semantic_hint() — unregistered semantic hint
7. Presence: resolve_presence() → co-presence entries (confidence > 0)
8. SpatialContext assembled with provenance metadata + freshness stamp
9. SpatialProjectionBuilder.build() → policy-shaped projection
   → select_consumer_precision() via SelfModelSpatialPolicyAdapter
   → project_context() applies privacy engine (6 precision levels)
10. State persistence: SpatialStateAdapter writes spatial + place_registry SS sections
11. Event emission: SpatialEventEmitter publishes context_created/refreshed events
12. Return SpatialTurnSnapshot
```

## Prompt Injection (3 Consumers)

### Front Prompt (`render_place_block`)

```
== PLACE ==
You are interacting on a "browser" device surface.
The user appears to be at "home" (precision: semantic; freshness: live).
```

### Back Prompt (`render_execution_place_block`)

```
== EXECUTION PLACE CONTEXT ==
context_id: spatial_abc123
device_surface: browser
semantic_place: home
precision: semantic
permission: granted
relevant_places: home (place_home_001), school (place_school_002)
redactions: raw_location_denied
```

### Planner Prompt (`render_planning_spatial_block`)

```
== PLANNING SPATIAL ==
context_id: spatial_abc123
semantic_place: home
precision: place_id
freshness: live
place_ids: place_home_001, place_school_002
```

## Where Spatial Is Consumed

| Consumer | Bus | How |
|----------|-----|-----|
| **GroundingHandle** (P3.8) | Session bus | Receives `spatial_handle` at construction. Reads spatial projection for grounding context assembly. |
| **Concierge Front** | Session bus | `spatial` port on PortBundle. Injects `render_place_block()` into Front prompt. |
| **Concierge Back** | Session bus | `spatial` port on PortBundle (Phase 2 Epic 15.1). Injects `render_execution_place_block()` into Back prompt. |
| **Planner** | Kernel bus | Consumes spatial projection via `ISpatialPolicyPort` for planning-level place awareness. |
| **MemoryWriter** | Session bus | Place context attached to memory atoms for recall filtering. |
| **SectionUpdate** | — | Explicitly excluded: "Never target spatial" in classifier vocabulary. |

### Geocoder Selection

Controlled by `K1_SPATIAL_GEOCODER` env var:

- `"nominatim"` / `"osm"` / `"openstreetmap"` → `NominatimGeocoderAdapter` (production)
- Unset or other → `NullGeocoderAdapter` (no geocoding)

---

# S2.9 — GroundingServiceBundle

**File:** `k1/grounding/` — ~40 Python files: kernel/ (3 files), service/ (14 files), adapters/ (8 files), ports/ (8 files), plus types/config/events/factory/serialization
**Init:** `_startup_tier1()` L1905 — `build_grounding_bundle(bus=self._bus)`
**Config gate:** `enable_grounding` (True when `K1_ENABLE_GROUNDING=true`)
**Lifecycle:** Shared bundle built once at S2.9. Per-session `GroundingHandle` built at P3.8 referencing this bundle. Shutdown after Spatial (S2.8), before Bridge (S4).
**Architecture:** Hexagonal ports & adapters. 8 protocol ports, 8 adapter implementations, 14 service-layer files. Central orchestrator (`GroundingService`) binds identity + time + place + device + policy into a canonical per-turn `GroundingEnvelope`, then produces consumer-specific `GroundingProjection` payloads and TTL-bound `AgentGroundingLease` objects for spawned agents. Feeds temporal/spatial/identity/state surfaces into Fabric context builder and Concierge Front/Back prompt injection. 7 consumer types: front, back, planner, fabric, agent, tool, memory. 6 prompt-block renderers.

## Sub-Components

### Kernel Wiring (`kernel/` — 3 files)

| Component | File | Purpose |
|-----------|------|---------|
| `GroundingServiceBundle` | `kernel/bootstrap.py` | **Tier-1 container.** Frozen dataclass holding: `service` (GroundingService), `renderer`, `config` (GroundingConfig), plus all 8 port references. Method `build_service()` creates per-session GroundingService from shared ports. |
| `build_grounding_bundle()` | `kernel/bootstrap.py` | Factory. Takes `bus` + optional port overrides. Resolves all 8 ports with production defaults: `TemporalHandleAdapter`, `SpatialHandleAdapter` (with unknown-spatial fallback), `UuidIdAdapter`, `GroundingStateAdapter`, `StaticIdentityAdapter`, `SelfModelPolicyAdapter`, `EventBusAdapter`, `NullMetricsAdapter`. Falls back to standalone mode when no temporal port provided. |
| `GroundingHandle` | `kernel/handle.py` | **Per-session facade.** Mutable dataclass structurally satisfying `IGroundingPort`. Holds bundle + `GroundingSessionBinding` + per-session adapters. Methods: `install_into_session()`, `uninstall_from_session()`, `refresh_turn()`, `build_envelope()`, `create_envelope()` (kernel alias), `build_projection()`, `project_envelope()`, `get_projection()`, `issue_agent_lease()`, `build_agent_lease()` (kernel alias), `refresh_if_stale()`, `shutdown()`. |
| `build_grounding_handle()` | `kernel/handle.py` | Factory. Creates `GroundingStateAdapter(ssm)` + wraps temporal/spatial/selfmodel handles into adapters → `bundle.build_service()` → `GroundingSessionBinding` → `GroundingHandle`. Parameters: `bundle`, `session_id`, `principal_id`, `actor_id`, `device_id`, `installation_id`, `state_manager`, `temporal_handle`, `spatial_handle`, `selfmodel_handle`. |
| `GroundingSessionBinding` | `kernel/session_binding.py` | Frozen dataclass: `session_id`, `principal_id`, `actor_id`, `device_id`, `installation_id`. |

### Service Layer (`service/` — 14 files)

| Component | File | Purpose |
|-----------|------|---------|
| `GroundingService` | `service/grounding_service.py` | **Central orchestrator.** Coordinates all 8 ports. `refresh_turn()` refreshes temporal + spatial then builds envelope. `build_envelope()` creates canonical `GroundingEnvelope` with identity/group refs, policy scope, provenance, freshness, and state persistence. `build_projection()` builds envelope then projects it. `project_envelope()` applies policy authorization and freshness checks. `issue_agent_lease()` builds projection + issues TTL-bound lease. `health()`, `shutdown()`. |
| `build_envelope()` | `service/envelope_builder.py` | Pure function. Assembles `GroundingEnvelope` from `TemporalProjection` + `SpatialProjection` + identity/group refs + device surface + policy scope. Computes aggregate `GroundingFreshness` (live/stale/degraded) from temporal + spatial status. Builds provenance `GroundingSource` records for each input. |
| `build_projection()` | `service/projection_builder.py` | Pure function. Produces `GroundingProjection` from `GroundingEnvelope` + `ConsumerScope`. Merges envelope redactions with scope's denied sections. Copies session/identity metadata. |
| `assert_projection_allowed()` | `service/projection_policy.py` | Raises `ProjectionDeniedError` if scope consumer doesn't match envelope consumer or scope is empty. |
| `default_consumer_scope()` | `service/projection_policy.py` | Returns `ConsumerScope` per consumer type: front/planner get temporal+spatial+identity_refs; agent/tool/fabric add `execution_metadata`; all get `device_surface`. Spatial precision from `DEFAULT_CONSUMER_PRECISION`. |
| `build_agent_lease()` | `service/lease_builder.py` | Issues TTL-bound `AgentGroundingLease` from `GroundingProjection` + `ConsumerScope`. Computes `issued_at_utc` and `expires_at_utc` (default 900s). Carries subject_ref, group_refs, role_refs, allowed/denied sections, redactions, `refresh_allowed`, `status="active"`. |
| `build_device_context_snapshot()` | `service/context_snapshot_builder.py` | Builds `DeviceContextSnapshot` from session/device params: surface, timezone, locale, clock_skew, location_permission, location_fix, semantic_place_hint. |
| `GroundingEventEmitter` | `service/event_emitter.py` | 5 typed methods: `publish_envelope_created()`, `publish_projection_created()`, `publish_lease_created()`, `publish_envelope_stale()`, `publish_projection_denied()`. Serializes dataclass payloads → dict → `IGroundingEventPort`. |
| `build_propagation_metadata()` | `service/propagation.py` | Extracts propagation fields from `GroundingProjection` into dict: `grounding_envelope_id`, `temporal_anchor_id`, `spatial_context_id`, `resolved_temporal_refs`, `resolved_spatial_refs`. |
| `attach_propagation_metadata()` | `service/propagation.py` | Merges propagation fields into an existing payload dict (used for task dispatch). |
| `build_invocation_metadata()` | `service/invocation_metadata.py` | Builds dict binding an invocation (tool/task/agent call) to grounding references: `grounding_envelope_id`, `grounding_projection_id`, `temporal_anchor_id`, `spatial_context_id`. |
| `build_reference_context()` | `service/reference_context_builder.py` | Compact dict with `grounding_envelope_id`, `temporal_anchor_id`, `spatial_context_id`, `projection_id`, `consumer`. |
| `is_stale()` / `envelope_age_ms()` | `service/stale_envelope_checker.py` | Computes envelope age from `created_at_utc`. `is_stale()` → True when age > `config.envelope_ttl_ms` (60s). |
| `GroundingHealthStatus` | `service/health.py` | Frozen dataclass: `ready`, `temporal_connected`, `spatial_connected`, `state_connected`, `identity_connected`, `policy_connected`, `event_connected` (all bool). |

### Prompt Block Renderers (`service/prompt_block_renderer.py` — 6 renderers)

| Function | Block Header | Target Consumer | Content |
|----------|-------------|-----------------|---------|
| `render_grounding_meta_block_v2()` | `== GROUNDING ==` | All | Envelope metadata, freshness, redactions |
| `render_time_block_v2()` | `== TIME ==` | Front/Back | Temporal anchor, windows, resolved expressions |
| `render_place_and_device_block_v2()` | `== PLACE AND DEVICE ==` | Front/Back | Spatial projection, device surface, co-presence |
| `render_now_block()` | `== NOW ==` | Front (legacy v1) | Concise user-facing time |
| `render_place_block()` | `== PLACE ==` | Front (legacy v1) | Concise user-facing place + surface |
| `render_execution_grounding_block()` | `== EXECUTION GROUNDING ==` | Back/Agent | Task-facing grounding with optional lease |
| `render_planning_grounding_block()` | `== PLANNING GROUNDING ==` | Planner | Minimal grounding: context_id, time, place |

### Port Protocols (`ports/` — 8 protocols, all `@runtime_checkable`)

| Protocol | File | Methods |
|----------|------|---------|
| `IGroundingTemporalPort` | `ports/temporal_port.py` | `build_projection(session_id, consumer) → TemporalProjection`, `refresh_turn(...) → TemporalTurnSnapshot` |
| `IGroundingSpatialPort` | `ports/spatial_port.py` | `refresh_turn(session_id, consumer, ...) → SpatialProjection`, `build_projection(session_id, consumer, ...) → SpatialProjection` |
| `IGroundingStatePort` | `ports/state_port.py` | `write_section(session_id, payload)`, `read_section(session_id) → Mapping \| None` |
| `IGroundingIdentityPort` | `ports/identity_port.py` | `get_identity_ref(session_id) → str \| None`, `get_group_refs(session_id) → tuple[str, ...]`, `get_role_refs(session_id) → tuple[str, ...]` |
| `IGroundingPolicyPort` | `ports/policy_port.py` | `get_consumer_scope(consumer, task_scope, privacy_scope) → ConsumerScope`, `authorize_projection(envelope, scope) → bool` |
| `IGroundingIdPort` | `ports/id_port.py` | `new_envelope_id()`, `new_projection_id()`, `new_lease_id()` → all `str` |
| `IGroundingEventPort` | `ports/event_port.py` | `publish(topic, payload) → None` |
| `IGroundingMetricsPort` | `ports/metrics_port.py` | `incr(name, value)`, `gauge(name, value)`, `timer(name, ms)` |

### Adapters (`adapters/` — 8 implementations)

| Adapter | File | Implements | Purpose |
|---------|------|-----------|---------|
| `TemporalHandleAdapter` | `adapters/temporal_handle_adapter.py` | `IGroundingTemporalPort` | Wraps `TemporalHandle`, delegates `build_projection()` and `refresh_turn()`. |
| `SpatialHandleAdapter` | `adapters/spatial_handle_adapter.py` | `IGroundingSpatialPort` | Wraps `SpatialHandle` with unknown-spatial fallback. `build_unknown_spatial_projection()` returns `semantic_place="unknown"`, `precision="hidden"`, `freshness="unavailable"` placeholder. |
| `GroundingStateAdapter` | `adapters/session_state_adapter.py` | `IGroundingStatePort` | Reads/writes `"grounding"` section through SessionState manager. Supports in-memory fallback when manager unavailable. |
| `SelfModelIdentityAdapter` | `adapters/selfmodel_identity_adapter.py` | `IGroundingIdentityPort` | Reads identity/group/role refs from SelfModel handle. `get_group_refs()` returns `bundle.space_id`. `get_role_refs()` extracts from `current_frame().actor.role`. |
| `StaticIdentityAdapter` | `adapters/selfmodel_identity_adapter.py` | `IGroundingIdentityPort` | Testing adapter returning static `identity_ref`, `group_refs`, `role_refs`. |
| `SelfModelPolicyAdapter` | `adapters/selfmodel_policy_adapter.py` | `IGroundingPolicyPort` | Default-deny-aware scope adapter. `get_consumer_scope()` returns allowed sections per consumer type. Optional override via `selfmodel_handle.get_grounding_consumer_scope()`. |
| `UuidIdAdapter` | `adapters/uuid_id_adapter.py` | `IGroundingIdPort` | UUID4 hex IDs for envelopes, projections, leases. |
| `EventBusAdapter` | `adapters/event_bus_adapter.py` | `IGroundingEventPort` | JSON-envelope publish on K1 bus with `Priority.INTERACTIVE`. Gracefully handles import/publish failures. |
| `NullMetricsAdapter` | `adapters/null_metrics_adapter.py` | `IGroundingMetricsPort` | No-op `incr()`, `gauge()`, `timer()`. |

### Domain Types (`types.py` — 4 type aliases + 7 frozen dataclasses)

| Type | Purpose |
|------|---------|
| `Consumer` (Literal) | `"front"`, `"back"`, `"planner"`, `"fabric"`, `"agent"`, `"tool"`, `"memory"` |
| `GroundingFreshnessState` (Literal) | `"live"`, `"stale"`, `"degraded"`, `"unavailable"` |
| `GroundingSourceKind` (Literal) | `"temporal"`, `"spatial"`, `"identity"`, `"device"`, `"policy"`, `"selfmodel"` |
| `LeaseStatus` (Literal) | `"active"`, `"expired"`, `"revoked"`, `"refresh_required"` |
| `DeviceContextSnapshot` | Device observation: surface, timezone, locale, clock_skew, location_permission, location_fix, semantic_place_hint |
| `GroundingFreshness` | Aggregated status + `generated_at_utc` + `age_ms` + per-source status dict |
| `GroundingSource` | Provenance record: source kind, source_id, captured_at_utc, confidence |
| `ConsumerScope` | Policy scope: consumer type, allowed/denied context sections, temporal_precision, spatial_precision, privacy_scope |
| `GroundingEnvelope` | **Canonical per-turn binding.** envelope_id, session_id, turn_id, trace_id, created_at_utc, consumer, identity_ref, temporal (TemporalProjection), spatial (SpatialProjection), group_refs, device_surface, policy_scope, freshness, provenance (tuple of GroundingSource), redactions |
| `GroundingProjection` | **Policy-filtered consumer payload.** projection_id, envelope_id, consumer, temporal, spatial, freshness, redactions |
| `AgentGroundingLease` | **TTL-bound agent lease.** lease_id, envelope_id, issued_at_utc, expires_at_utc, temporal, spatial, subject_ref, group_refs, role_refs, task_scope, privacy_scope, allowed/denied sections, redactions, refresh_allowed, status |

### Configuration (`config.py`)

| Field | Default | Purpose |
|-------|---------|---------|
| `envelope_ttl_ms` | 60000 | Envelope freshness TTL (60s) |
| `agent_lease_ttl_seconds` | 900 | Agent lease lifetime (15 min) |
| `raw_spatial_allowed_by_default` | False | Raw GPS never exposed by default |
| `default_consumer` | `"front"` | Fallback consumer type |

### Events (`events.py` — 5 topics)

| Topic Constant | Value | Payload |
|---------------|-------|---------|
| `GROUNDING_ENVELOPE_CREATED` | `k1.grounding.envelope.created.v1` | `GroundingEnvelopeCreatedPayload` |
| `GROUNDING_PROJECTION_CREATED` | `k1.grounding.projection.created.v1` | `GroundingProjectionCreatedPayload` |
| `GROUNDING_LEASE_CREATED` | `k1.grounding.lease.created.v1` | `GroundingLeaseCreatedPayload` |
| `GROUNDING_ENVELOPE_STALE` | `k1.grounding.envelope.stale.v1` | `GroundingEnvelopeStalePayload` |
| `GROUNDING_PROJECTION_DENIED` | `k1.grounding.projection.denied.v1` | `GroundingProjectionDeniedPayload` |

### Factory (`factory.py`)

| Method | Returns | Purpose |
|--------|---------|---------|
| `GroundingFactory.create_standalone(config)` | `GroundingServiceBundle` | Standalone mode (in-memory, UTC-only temporal, unknown spatial) |
| `GroundingFactory.create_for_testing(config, **overrides)` | `(bundle, adapters_dict)` | Test mode with adapter overrides |
| `GroundingFactory.create_production(...)` | `GroundingServiceBundle` | Production bundle from explicit ports |
| `GroundingFactory.create_with_ports(...)` | `GroundingServiceBundle` | Core wiring; validates all 8 ports, constructs GroundingService |

---

## Grounding Data Flow (Per-Turn)

```
1. P3.8: build_grounding_handle() wires per-session adapters:
   → TemporalHandleAdapter(temporal_handle)
   → SpatialHandleAdapter(spatial_handle)   [unknown-spatial fallback]
   → SelfModelIdentityAdapter(selfmodel_handle)
   → SelfModelPolicyAdapter(selfmodel_handle)
   → GroundingStateAdapter(ssm)
2. Early refresh: grounding_handle.refresh_turn(session_id, consumer="front")
   → GroundingService.refresh_turn()
     → IGroundingTemporalPort.refresh_turn()  → TemporalTurnSnapshot
     → IGroundingTemporalPort.build_projection()  → TemporalProjection
     → IGroundingSpatialPort.refresh_turn()   → SpatialProjection
     → IGroundingIdentityPort.get_identity_ref()  → identity_ref
     → IGroundingIdentityPort.get_group_refs()    → group_refs
     → IGroundingPolicyPort.get_consumer_scope()  → ConsumerScope
     → build_envelope()  → GroundingEnvelope
       → Compute aggregate freshness (live/stale/degraded)
       → Build provenance GroundingSource records
     → IGroundingStatePort.write_section()  → persist to SS "grounding"
     → GroundingEventEmitter.publish_envelope_created()
3. Concierge Front: grounding.build_projection(envelope, consumer="front")
   → assert_projection_allowed()  → policy gate
   → build_projection()  → GroundingProjection
   → build_propagation_metadata()  → dispatch payload fields
   → render_time_block_v2() + render_place_and_device_block_v2()  → prompt blocks
4. Concierge Back: receives grounding_projection in task dispatch payload
   → _extract_identity_ref() from grounding metadata
   → render_execution_grounding_block()  → execution context
5. Planner: render_planning_grounding_block()  → minimal planning context
6. Agent spawn: grounding.issue_agent_lease(session_id, task_scope, privacy_scope)
   → build_agent_lease()  → AgentGroundingLease (TTL 900s)
```

## Prompt Injection (6 Blocks)

### Front — Grounding Meta (`render_grounding_meta_block_v2`)

```
== GROUNDING ==
envelope_id: grd_abc123
session_id: sess_xyz
created: 2026-06-17T14:42:00Z
freshness: live
redactions: raw_location_denied
```

### Front — Time (`render_time_block_v2`)

```
== TIME ==
It is Wednesday afternoon, Wednesday, June 17, 2026 — the local time
is 2:42 PM in the America/Chicago timezone (from the user's device).
Today is Wednesday, June 17; tomorrow is Thursday, June 18.
This week runs Monday, June 15 through Sunday, June 21.
```

### Front — Place and Device (`render_place_and_device_block_v2`)

```
== PLACE AND DEVICE ==
The user appears to be at "home" (precision: semantic; freshness: live).
Device surface: browser.
```

### Back — Execution Grounding (`render_execution_grounding_block`)

```
== EXECUTION GROUNDING ==
envelope_id: grd_abc123
context_id: spatial_def456
semantic_place: home
precision: semantic
permission: granted
relevant_places: home (place_home_001)
redactions: raw_location_denied
```

### Planner — Planning Grounding (`render_planning_grounding_block`)

```
== PLANNING GROUNDING ==
context_id: spatial_def456
semantic_place: home
precision: place_id
freshness: live
place_ids: place_home_001
```

## Where Grounding Is Consumed

| Consumer | Bus | How |
|----------|-----|-----|
| **Fabric Context Builder** | Session bus | `set_grounding_port(grounding_handle)` called at P3.8. Grounding feeds temporal/spatial/identity into Fabric's context assembly. |
| **Concierge Front** | Session bus | `grounding` port on PortBundle. Refreshes envelope each turn, builds projection, injects 3 prompt blocks (grounding_meta, time, place_and_device). Propagation fields attached to dispatch payload. |
| **Concierge Back** | Session bus | `grounding` port on PortBundle. Receives projection in dispatch payload. Extracts identity_ref. Renders execution_grounding block. |
| **Planner** | Kernel bus | Consumes `render_planning_grounding_block()` for planning-level spatial/temporal awareness. |
| **Agent spawn** | Session bus | `issue_agent_lease()` issues TTL-bound `AgentGroundingLease` with subject/group/role refs + allowed sections. |
| **MemoryWriter** | Session bus | Grounding envelope ID + temporal/spatial context IDs attached to memory atoms for recall provenance. |
| **SectionUpdate** | — | Explicitly excluded: "Never target grounding" in classifier vocabulary. |

### Concierge Bus Registration

`k1.grounding.*` prefix registered on Concierge bus (`k1/concierge/bus/setup.py`) alongside `k1.agent.*` and `k1.session.*` for dynamic topic families emitted outside the static Concierge topic list.

### Propagation Fields (Attached to Every Task Dispatch)

| Field | Source |
|-------|--------|
| `grounding_envelope_id` | `GroundingEnvelope.envelope_id` |
| `temporal_anchor_id` | `TemporalProjection.anchor_id` |
| `spatial_context_id` | `SpatialProjection.context_id` |
| `resolved_temporal_refs` | `{raw_text: normalized_label}` dict |
| `resolved_spatial_refs` | `{place_id: label}` dict |

---

---

# P1.1 — SessionRoutingStateReader

**File:** `k1/kernel/adapters/session_routing_reader.py` (166 lines)
**Init:** `_startup_tier1()` L1922 — pre-S3, before shared Fabric/Orchestrator/Planner
**Lifecycle:** Single shared instance. Created once, injected into three Tier-1 consumers (Fabric, Orchestrator, Planner). Never destroyed until kernel shutdown.
**Architecture:** Closure-based adapter that bridges Tier-1 singleton components to Tier-2 per-session `SessionStateManager` instances. Satisfies `ISessionStateReader` via structural subtyping. Constructor takes `session_lookup: Callable[[str], Any]` — a live closure over `KernelService._sessions` that resolves `session_id → SessionStateManager` at read time.

## Sub-Components

| Component | Purpose |
|-----------|---------|
| `SessionRoutingStateReader(session_lookup)` | **Single shared instance.** Constructor accepts a closure `lambda sid: self._sessions[sid].session_state if sid in self._sessions else None`. All three methods are synchronous, structural implementations of `ISessionStateReader`. |
| `read_section(session_id, section) → dict \| None` | Resolves SSM via `session_lookup`, calls `ssm.read_section(section)`. Returns `None` gracefully when session doesn't exist. |
| `read_sections(session_id, names) → dict` | Batches `read_section` calls across multiple section names. Returns `{name: payload}` dict. |
| `get_snapshot(session_id) → SessionSnapshot` | Iterates all known section names (from `manager.get_all_section_sizes()` or hardcoded K1 list), reads each, returns immutable `SessionSnapshot`. |
| `_resolve_manager(session_id) → SSM \| None` | Internal helper. Calls `session_lookup(session_id)`. Returns `None` for unknown sessions — callers handle gracefully. |
| `_get_section_names(manager) → list[str]` | Discovers section names: tries `manager.get_all_section_sizes()` first, falls back to hardcoded K1 section list. |

## Protocol Contract

Satisfies `ISessionStateReader` (`k1/fabric/ports/state_reader.py`) via structural subtyping:

| Method | Return | Contract |
|--------|--------|----------|
| `read_section(session_id, section)` | `dict \| None` | Read a single SS section by name |
| `read_sections(session_id, names)` | `dict` | Batch read multiple sections |
| `get_snapshot(session_id)` | `SessionSnapshot` | Full point-in-time SS snapshot |

`SessionSnapshot` is a frozen dataclass with an immutable `sections: Mapping[str, Any]` dict.

## Wiring Diagram

```
                        ┌─────────────────────────────────┐
                        │     SessionRoutingStateReader    │
                        │  (k1/kernel/adapters/)           │
                        │                                  │
                        │  session_lookup: sid → SSM       │
                        │  satisfies ISessionStateReader   │
                        │  (structural subtyping)          │
                        └──────┬───────────────────────────┘
                               │  single instance, created pre-S3
               ┌───────────────┼───────────────────────────────┐
               ▼               ▼                               ▼
        ┌──────────┐   ┌───────────────┐            ┌──────────────────┐
        │  Fabric   │   │  Orchestrator │            │     Planner       │
        │  (S3)     │   │  (S5)         │            │     (S6)          │
        │           │   │               │            │                   │
        │  direct   │   │ StateRead     │            │ PlannerState      │
        │  ISession │   │ Adapter       │            │ Adapter           │
        │  State    │   │ (sync→async)  │            │ (pre-bound sid)   │
        │  Reader   │   │               │            │                   │
        └──────────┘   └───────────────┘            └───────────────────┘
```

## Three Injection Points

### 1. Shared Fabric (S3, L1972)

Passed directly as `state_reader=session_routing_reader` to `FabricFactory.create_shared(...)`. Fabric consumes it as `ISessionStateReader` for:

- `ContextBuilder` — fetching SessionState sections for prompt context assembly
- `PolicyEngine` — AffectiveRouting + CognitiveLoadRouting decisions
- `SemanticValidator` — grounding checks against beliefs
- `AgentFactory` — declared read-only sections
- `HardFilter` — input satisfiability
- `OutputValidationPipeline` — output validation

**Invariant FAB-01:** Fabric NEVER writes SessionState — enforced by the read-only port contract.

### 2. Orchestrator (S5, L2013)

```python
orch_state = StateReadAdapter(state_reader=session_routing_reader)
```

`StateReadAdapter` (`k1/orchestrator/adapters/state_read_adapter.py`) wraps the sync `ISessionStateReader` as an async `IStateReadPort`:

- All methods are `async`, wrapping the sync reader calls
- Translates exceptions into `AdapterException(DEGRADED, "stale context")`
- **Invariant ORCH-01:** exposes NO write methods

### 3. Planner (S6, L2078)

```python
pl_state = PlannerStateAdapter(reader=self._session_routing_reader, session_id="")
```

`PlannerStateAdapter` (`k1/planner/adapters/session_state_adapter.py`, aliased as `SessionStateReadAdapter`):

- Wraps `ISessionStateReader` with a pre-bound `session_id=""` fallback
- **Session ID resolution (3.2.2):** caller-provided `session_id` (from `PlanRequest.context.session_id` → `ToolCallRouter`) wins over the pre-bound empty string
- Methods: `read_sections(sections, trace_id, session_id)` and `get_snapshot(trace_id)` — both async
- Returns `SessionSnapshot`, wrapping raw dict if needed
- Gracefully returns empty `SessionSnapshot` on failure

## Design Rationale

Orchestrator and Planner are **Tier-1 singletons** (one instance for all sessions), but need to read **per-session state**. The `SessionRoutingStateReader` solves this by:

1. **Live closure** over `KernelService._sessions` — always sees the latest session map without needing re-injection when sessions are created or destroyed
2. **Lazy resolution** — `session_id → SSM` lookup happens at read time, not construction time
3. **Graceful degradation** — returns `None` / empty snapshots for unknown sessions instead of raising
4. **Read-only** — satisfies `ISessionStateReader` which has no write methods, enforcing the invariant that Tier-1 components never mutate per-session state

---

# S2.10 — GlobalProjectionStore + IdempotencyStore

**File:** `k1/fabric/stores/global_projection_store.py` (~1918 lines), `k1/fabric/stores/idempotency_store.py` (~177 lines)
**Init:** `_startup_tier1()` L1930 — `GlobalProjectionStore(db_path).open()` + `IdempotencyStore(db_path).open()`
**Config gate:** `enable_fabric_stores` (True in production)
**Lifecycle:** Shared SQLite WAL stores. GPS at `./data/global_projection.db`, Idempotency at `./data/idempotency.db`. Both opened at S2.10, passed to shared Fabric (S3, step 21 wiring), reused by per-session Fabric. Closed at kernel shutdown.
**Architecture:** GPS is the canonical source of truth for all connector metadata, capability contracts, constitutions, taxonomy, and graph ontology. Combines SQLite FTS5 full-text search with MiniLM-L6 dense vector retrieval (384-dim). IdempotencyStore provides a simple 4-state machine for idempotency key tracking. No formal protocol interfaces — stores are duck-typed directly.

---

## GlobalProjectionStore

### SQL Schema (10 data tables + 2 FTS5 virtual tables + 1 compound index)

#### Core Tables

| Table | PK | Key Columns | Purpose |
|-------|-----|-------------|---------|
| `connectors` | `connector_id` | label, connector_type (native/bridge/ifl), provider_type, version, admission_verdict, registration_type, constitution_json, policy_json, resource_kinds_json, guide_cards_json, domain_id | All registered connector metadata |
| `capabilities` | `capability_name` | connector_id (FK→connectors CASCADE), invocation_mode (read/execute), action_name, effect (read/write/delete/compute), resource_kind, domain_id, family_id, description, required_inputs_json, optional_inputs_json, safety_band_min, risk_class, idempotency, compensation_capability, record_type, contract_json, synthetic | All capability contracts. Domain/family backfilled on migration |
| `resource_kinds` | `kind_id` | connector_id (FK), label, schema_json, verifier_affordances_json | Per-connector resource kind schemas |
| `connector_constitutions` | `connector_id` (FK) | constitution_id, schema_version, authored_by, authored_at, last_proven_at, execution_phases_json, prerequisite_reads_json, conflict_analysis_rules_json, hil_gates_json, mutation_sequencing_json, verification_requirements_json, companion_resource_roles_json, how_to_sequence_json, what_to_verify_json, when_to_ask_human_json, companion_connectors_json, conflict_rules_json, summaries | Per-connector constitution documents |
| `connector_backends` | `(connector_id, backend_id)` | backend_label, schema_version, registered_at | Multi-backend connector registration (RES-000c) |
| `connector_resource_families` | `(connector_id, family_id)` | is_primary | Links connectors to resource families |

#### Taxonomy Tables (Phase 2.6)

| Table | PK | Seed Data | Purpose |
|-------|-----|-----------|---------|
| `domains` | `domain_id` | 16 domains (family, finance, health, education, home, transport, food, fitness, entertainment, productivity, communication, government, legal, utilities, agriculture, automotive) | FamilyOS-governed domain vocabulary |
| `resource_families` | `family_id` | 56 families (event, task, reminder, item, record, contact, setting, metric, subscription, message, order, chore, recipe, account, transaction, budget, ...) | Canonical resource family types |
| `domain_resource_families` | `(domain_id, family_id)` | 130+ mappings | Which resource families belong to which domains |

#### Graph Ontology Tables (6 tables)

| Table | PK | Purpose |
|-------|-----|---------|
| `concept_aliases` | `(alias, canonical_concept, domain)` | Maps user words → canonical concepts with weight |
| `concept_resource_edges` | `(concept, resource_family, domain)` | Links concepts to resource families |
| `resource_connector_edges` | `(domain, resource_family, connector_id)` | Links resource families to connectors with role (primary/companion/verifier/prerequisite) |
| `operation_aliases` | `(alias, operation_family)` | Maps user verbs → canonical operations with effect |
| `operation_equivalences` | `(canonical_operation, equivalent_operation, resource_family, domain)` | Declares equivalent operations |
| `capability_type_index` | `(capability_name, resource_family, operation_family, effect)` | Multi-row per-capability resolution index |

#### FTS5 Virtual Tables

| Table | Type | Content | Purpose |
|-------|------|---------|---------|
| `capabilities_fts` | Content-sync (capabilities) | capability_name, action_name, description, family_id, connector_id, domain_id | BM25 keyword search over capabilities |
| `connectors_fts` | Standalone (manual) | connector_id, label, description, search_text | BM25 keyword search over connectors |

#### Index

| Index | Columns |
|-------|---------|
| `idx_capability_lookup` | `(family_id, resource_kind, invocation_mode, effect, domain_id, connector_id, record_type, safety_band_min)` |

### Return-Type Dataclasses

| Dataclass | Key Fields |
|-----------|------------|
| `ConnectorRecord` | connector_id, label, connector_type, provider_type, version, admission_verdict, registration_type, constitution (dict), policy_declarations, resource_kinds, guide_cards, domain_id |
| `CapabilityRecord` | capability_name, connector_id, invocation_mode, action_name, effect, resource_kind, domain_id, family_id, description, required_inputs, optional_inputs, safety_band_min, risk_class, idempotency, compensation_capability, record_type, contract_json, synthetic |
| `ResourceKindRecord` | kind_id, connector_id, label, schema, verifier_affordances |
| `ConstitutionRecord` | connector_id, constitution_id, schema_version, authored_by, authored_at, last_proven_at, execution_phases, prerequisite_reads, conflict_analysis_rules, hil_gates, mutation_sequencing, verification_requirements, companion_resource_roles, summaries |
| `LoadResult` | total_connectors, total_capabilities, admitted, rejected, errors |
| `CapabilityRegistrationBatch` | connector (ConnectorRecord), capabilities (list[CapabilityRecord]), resource_kinds, constitution |

### MiniLM Embedding Index

| Attribute | Value |
|-----------|-------|
| Model | `all-MiniLM-L6-v2` (SentenceTransformer, 22MB) |
| Encoding | Label-only (not full search_text) — prevents signal dilution from long FTS text |
| Dimension | 384 (float32, normalized) |
| Index shape | `(n_connectors, 384)` |
| Build trigger | Lazy on first `search_connectors()` call; invalidated on connector FTS changes |
| Search method | Cosine similarity via dot product (vectors are L2-normalized) |
| Domain gating | `active_os_domains` parameter filters connector_ids by domain membership |

### Method Inventory (33 methods)

#### Lifecycle

| Method | Purpose |
|--------|---------|
| `open()` | WAL mode, FK=ON, row_factory=Row, `_ensure_schema()`, seeds taxonomy |
| `close()` | Close connection |
| `_db` (property) | Raises RuntimeError if not open |

#### Connector CRUD (6 methods)

`upsert_connector()`, `get_connector()`, `list_connectors()`, `delete_connector()` (CASCADE), `connector_exists()`

#### Capability CRUD (7 methods)

`upsert_capability()`, `bulk_upsert_capabilities()` (chunked 25K, delete-all→insert→rebuild FTS), `get_capability()`, `get_capabilities_by_connector()`, `delete_capability()`, `capability_exists()`, `count_capabilities()`, `list_all_capabilities()`

#### FTS5 Search (3 methods)

`_sanitize_fts_query()` (tokenize → OR-wildcard, drops <2 char tokens), `search_capabilities()` (BM25 with top_k + connector_id filter), `search_capabilities_by_domain()` (domain-filtered with auto-retry without domain filter on zero results), `rebuild_fts_index()`

#### Connector FTS5 (1 method)

`upsert_connector_fts_text()` — DELETE old + INSERT new; invalidates embedding index

#### MiniLM Embedding (3 methods)

`_ensure_embedding_index()` (lazy build, idempotent), `search_connectors()` (cosine similarity, returns `[{connector_id, label, description, domain_id, score}]`), `invalidate_embedding_index()`

#### Taxonomy Queries (3 methods)

`get_domains()`, `get_resource_families_for_domain()`, `get_connector_resource_families()`

#### Structured Lookup (1 method)

`find_capabilities()` — Pass 2 exact-match query for `CapabilityBinderService` using `idx_capability_lookup`

#### Resource Kind CRUD (3 methods)

`upsert_resource_kind()`, `get_resource_kinds_by_connector()`, `get_resource_kind()`

#### Constitution CRUD (3 methods)

`upsert_constitution()`, `get_constitution()`, `list_constitutions()`

#### Bulk Admission (1 method)

`load_from_manifest_batch()` — Atomic `BEGIN IMMEDIATE` transaction: connector + capabilities + resource_kinds + constitution. Single FTS5 rebuild at end. Rolls back on error.

#### Graph Ontology Queries (4 methods)

`resolve_concept()` (alias→concept), `get_concept_resource_family()`, `resolve_operation()` (verb→operation), `lookup_capability_by_type()` (domain/resource_family/operation/effect→capabilities, domain-agnostic when domain="")

#### Graph Ontology Upserts (7 methods)

`upsert_concept_alias()`, `upsert_concept_resource_edge()`, `upsert_resource_connector_edge()`, `upsert_operation_alias()`, `upsert_operation_equivalence()`, `get_operation_equivalences()`, `upsert_capability_type_index()`

#### Private Deserializers (4 methods)

`_row_to_connector()`, `_row_to_capability()`, `_row_to_resource_kind()`, `_row_to_constitution()`

### Key Consumers Within Fabric (Step 21 Wiring)

| Component | Created From | Purpose |
|-----------|-------------|---------|
| `ConstitutionLoader` | GPS | Read constitution for a connector_id |
| `ConnectorResolver` | GPS | MiniLM-L6 dense retrieval + FTS5 keyword fallback. `resolve(action_text)` → ranked connector list |
| `CapabilityBinderService` | GPS | Assemble tools + constitution for resolved connectors. `bind(connector_id)` → tools list + constitution |
| `ResolveSituationService` | GPS + LPS | Single-pass resolver. Orchestrates connector resolution → capability binding → resolution envelope |
| `VerificationPlanRunner` | GPS | (Post-S8) Runs verification plans from constitution |

### Registry Hints (Post-S8)

`_build_registry_hints(gps)` at L2356 queries GPS for:

1. Domains with ≥1 admitted connector
2. Per-domain resource families linked via `connector_resource_families` → `resource_families` JOIN

These hints are injected into `self._registry_hints` and passed to Concierge Back for LLM prompt context.

---

## IdempotencyStore

### SQL Schema

```sql
CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key  TEXT PRIMARY KEY,
    state            TEXT NOT NULL DEFAULT 'not_seen'
                     CHECK(state IN ('not_seen','in_flight','succeeded','failed')),
    invocation_id    TEXT NOT NULL DEFAULT '',
    observation_json TEXT NOT NULL DEFAULT '{}',
    error            TEXT,
    created_at       TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL DEFAULT ''
)
```

No indexes beyond implicit PK. No FTS5. No foreign keys.

### 4-State Machine

```
not_seen ──→ in_flight ──→ succeeded
                │
                └──→ failed
```

**Immutable succeeded guard:** `mark_in_flight()` uses `WHERE state NOT IN ('succeeded')` — once a key reaches `succeeded`, it can never be moved back to `in_flight`.

### Method Inventory

| Method | Signature | Behavior |
|--------|-----------|----------|
| `open()` | `→ None` | WAL mode, row_factory=Row, `_ensure_schema()` |
| `close()` | `→ None` | Close connection |
| `check()` | `(idempotency_key) → IdempotencyCheckResult` | SELECT by PK. Returns `state="not_seen"` if absent. Deserializes `observation_json` from prior success |
| `mark_in_flight()` | `(key, invocation_id) → None` | `INSERT ... ON CONFLICT DO UPDATE SET state='in_flight' WHERE state NOT IN ('succeeded')` |
| `mark_success()` | `(key, observation: dict) → None` | `UPDATE SET state='succeeded', observation_json=? WHERE key=? AND state='in_flight'`. Logs warning if rowcount==0 |
| `mark_failed()` | `(key, error: str) → None` | `UPDATE SET state='failed', error=? WHERE key=? AND state='in_flight'`. Logs warning if rowcount==0 |
| `cleanup_expired()` | `(max_age_hours=24) → int` | `DELETE WHERE updated_at < ? AND state != 'in_flight'`. Caller-driven — no automatic TTL trigger |

### Return Type

`IdempotencyCheckResult` (frozen dataclass):

- `state: str` — `"not_seen"`, `"in_flight"`, `"succeeded"`, or `"failed"`
- `prior_observation: dict | None` — stored observation from prior success
- `error: str | None` — error string if state == `"failed"`

---

## Wiring Flow

```
S2.10 (L1930):
  GPS = GlobalProjectionStore("./data/global_projection.db").open()
  IDM = IdempotencyStore("./data/idempotency.db").open()
  → stored as self._global_projection_store, self._idempotency_store

S3 (L1974):
  FabricFactory.create_shared(global_projection_store=gps, idempotency_store=idm)
  → _wire_phase1():
    fabric.global_projection_store = gps
    fabric.idempotency_store = idm
    ConstitutionLoader(gps)              → constitution lookup
    ConnectorResolver(gps)               → MiniLM + FTS5 connector search
    CapabilityBinderService(gps)         → tools + constitution assembly
    ResolveSituationService(gps, lps, …) → single-pass resolver

Post-S8 (L2155):
  _build_registry_hints(gps)             → live domain/family snapshots
  → self._registry_hints injected into Back LLM prompt

P3 (L2782):
  Per-session LocalProjectionStore(":memory:") created
  → situated_resolver wired from shared fabric
  → GPS + LPS + IDM passed to session Concierge factory

Shutdown (L767):
  gps.close() → idm.close()
```

---

---

# S3 — Shared Fabric

**File:** `k1/fabric/` — ~122 Python files across 23 subdirectories + 6 top-level .py files + 4 .md docs
**Init:** `_startup_tier1()` L1970 — `FabricFactory.create_shared(event_port=..., bridge=..., model_gateway=..., prompt_system=..., delta_bus=..., state_reader=session_routing_reader, hil_port=..., global_projection_store=gps, idempotency_store=idm)`
**Config gate:** Always created (no feature flag). Production mode when `model_mode="hub"`.
**Lifecycle:** Created once at S3, shared across ALL sessions. Per-session Fabric (P3) reuses the shared registry, circuit breakers, health checker, and module loader. Closed at kernel shutdown after S5 (orchestrator), before S2.10 (stores).
**Architecture:** Hexagonal ports & adapters. 6 port protocols, 7 production adapters, 3 specialized sub-pipelines (execution, retrieval, resolution). 21-step factory construction order. Central `CapabilityFabric` facade drives a 14-step execution pipeline with HIL gate, conscience gate, circuit breaking, output validation, and learning signal emission. Provider resolution: 5-step pipeline (registry lookup → matching → policy evaluation → selection → instantiation). Retrieval: 4-step pipeline (embedding → hard filter → soft rank → top-K). Single shared `CapabilityRegistry` with multi-index lookup (by_name, by_domain, by_type, by_provider). 7 provider types: MCP, WASM, Bridge, Agent, Workflow, Concierge, Local Stub.

## Dead Code & Legacy Audit

| Finding | File | Detail |
|---------|------|--------|
| `ResolvedIntentType` (DEPRECATED) | `resolver/capability_type_resolver.py:67` | Legacy typed output — superseded by `RankedConnectorSet` |
| Legacy graph traversal | `resolver/capability_type_resolver.py:158-177` | Deleted RES-006 (2026-06-17), comments preserved |
| `resource_kind` field legacy | `stores/global_projection_store.py:51` | `family_id` is Phase 2.6 replacement |
| `_DEPRECATED_GROUNDING_OVERRIDE_KEYS` | `core/context_builder.py:45` | Actively filters deprecated grounding keys |
| HIL gate `None` fallback legacy | `fabric.py:326,841,904` | Preserves legacy/test harness paths |
| Versionless contract check | `core/registry.py:414` | Falls back to legacy duplicate check |
| Legacy `"cognitive"` section fallback | `policy/cognitive_load_routing.py:149` | Tries legacy SS section name |
| `domain_id` LIKE prefix hack | `stores/global_projection_store.py:1058` | TODO: use domain_id column (Phase 2.6) |

**No dead imports found.** All `from k1.fabric.*` imports resolve to existing files.

---

## Top-Level Files

| File | ~Lines | Purpose |
|------|--------|---------|
| `__init__.py` | 18 | Exports: `CapabilityFabric`, `FabricRetrieval`, `CapabilityRegistryAPI`, `Fabric`, `FabricConfig`, `BatchStrategy`, `FabricFactory` |
| `fabric.py` | ~700 | **CapabilityFabric** (14-step execution pipeline), **FabricRetrieval** (discovery API), **CapabilityRegistryAPI** (registry management), **Fabric** (container dataclass), `FabricConfig`, `BatchStrategy` (PARALLEL/SEQUENTIAL/DAG) |
| `factory.py` | ~600 | **FabricFactory** — 4 factory methods + 21-step `_construct_fabric()` + `_wire_phase1()` + `_register_provider_handlers()` + `_auto_register_providers()` |
| `types.py` | ~700 | 8 enums + 25 frozen dataclasses: `CapabilityRequest`, `CapabilityResult`, `ErrorInfo`, `CapabilityContract`, `AgentContract`, `PromptContract`, `WorkflowContract`, `ProviderConfig`, `ScoredCapability`, `RetrievalResult`, `FabricPlanStep`, etc. |
| `manifest_admission.py` | ~350 | `ManifestAdmissionService` — validates & ingests `ConnectorDefinition` → GPS. 7 validation constant sets |
| `manifest_translator.py` | ~400 | `ToolDefinition` → `CapabilityContract` bridge. Naming: `tool.{read|execute}.{adapter_id}.{action_name}` |
| `metrics.py` | ~400 | `FabricMetrics` — 5 histograms, 4 gauges, 6 counters. `get_default_metrics()` singleton |
| `logging.py` | ~250 | Structured JSON logging — 5 Fabric execution phases. `FabricJsonFormatter`, `FabricLogger` |

### Core Types (`types.py`)

| Enum | Values |
|------|--------|
| `WFQPriority` | URGENT, REALTIME, INTERACTIVE, BACKGROUND |
| `RequestStatus` | PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED, TIMED_OUT |
| `Tier` | LOW, MEDIUM, HIGH |
| `SafetyBand` | GREEN < AMBER < RED < CRISIS |
| `Availability` | ONLINE, DEGRADED, OFFLINE |
| `ProviderType` | MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE, LOCAL_STUB |

**Key dataclasses (all frozen):** `CapabilityRequest` (request_id, capability_name, params, tier, wfq_priority, safety_band, timeout_ms, caller, trace_id, session_id, plan_id, step_id, context_override), `CapabilityResult` (request_id, trace_id, success, data, error, provider_id, duration_ms), `ErrorInfo` (code, message, retriable), `CapabilityContract` (name, version, domain, required_inputs, required_context, provider_type, safety_band_min, requires_human_confirmation, side_effects, risk_class, social_act, context_precision), `AgentContract` (extends CapabilityContract: prompt_template, tools_granted, llm_budget_tokens, max_tool_calls)

---

## 14-Step Execution Pipeline (`CapabilityFabric.execute()`)

```
execute(request)
  ├─ [Dispatcher] → dispatch(request, _execute_impl) or direct if no dispatcher
  └─ _execute_impl(request):
       STEP 1:  emit_invoked(capability_name, request_id, trace_id)
       STEP 2:  resolver.resolve(request) → ResolvedProvider (provider_id, provider_type, contract)
       STEP 2.4: _run_conscience_gate() → checks social_act against forbidden acts
       STEP 2.5: _run_hil_gate() → ALLOW/ASK_APPROVED proceed; DENY/ASK_REJECTED/TIMEOUT block
       STEP 3:  context_builder.build_async() → ExecutionContext
       STEP 4:  provider_factory.create(resolved.provider_config) → provider instance
       STEP 5:  _execute_with_breaker() → CB-protected provider.execute(request, context)
       STEP 6:  validation_pipeline.validate() → reject/coerce/pass
       STEP 7:  emit_completed or emit_failed
       STEP 8:  registry.update_metrics(capability_name, duration_ms, success)
       STEP 9:  emit_learning_signal(request, provider_id, success, duration_ms, error_code)
```

Never raises — all exceptions caught and wrapped as `CapabilityResult.failure`.

### Batch Execution (`execute_batch()`)

| Strategy | Implementation |
|----------|---------------|
| `PARALLEL` | `asyncio.gather(*[execute(req) for req in requests])` |
| `SEQUENTIAL` | `[await execute(req) for req in requests]` |
| `DAG` | Topological sort → wave-by-wave parallel execution |

### Configuration

| Field | Default | Purpose |
|-------|---------|---------|
| `max_batch_size` | 50 | Max parallel batch size |
| `default_timeout_ms` | 30000 | Default execution timeout |
| `hil_gate_timeout_ms` | 120000 | HIL gate decision timeout |

---

## 21-Step Factory Construction (`_construct_fabric()`)

| Step | Component | Dependencies |
|------|-----------|-------------|
| 1 | Adapters | (provided by factory method) |
| 2 | `ContractValidator()` | Stateless |
| 3 | `CapabilityRegistry(validator, event_port)` | validator, event_port |
| 4 | `ModuleLoader(registry, contracts_dir, event_port, validator)` | registry, contracts_dir |
| 5a | `SecurityContext()` | Stateless |
| 5b | `AffectiveRouting(state_reader)` | state_reader |
| 5c | `CognitiveLoadRouting(state_reader)` | state_reader |
| 5d | `QoSIntegration()` | Stateless |
| 5e | `PolicyEngine(security, affective, cognitive, qos)` | All 4 above |
| 6 | `ProviderRegistry(event_port)` | event_port |
| 7 | `circuit_breakers: Dict[str, CircuitBreaker] = {}` | Empty, populated later |
| 8 | `ContextBuilder(state_reader, prompt_system, grounding_port)` | state_reader, prompt_system, grounding_port |
| 9a | MCP transport: `AutoDiscoveryMCPTransport()` or `TestMCPTransport` | |
| 9b | WASM runtime: `AutoDiscoveryWASMRuntime()` or `TestWASMRuntime` | |
| 9c | `ProviderFactory(bridge, model_gateway, state_reader, delta_bus, context_builder, grounding_port, registry, mcp_transport, wasm_runtime)` | 8 port deps + registry |
| 9d | `_register_provider_handlers()` — 7 handler constructors | provider_factory |
| 10a | `ProviderMatcher(provider_registry)` | provider_registry |
| 10b | `ProviderSelector()` | Stateless |
| 10c | `Resolver(capability_registry, provider_matcher, provider_selector, provider_factory, policy_engine)` | All 5 deps |
| 11a | `EmbeddingIndex()` | Stateless |
| 11b | `HardFilter()` | Stateless |
| 11c | `SoftRanker()` | Stateless |
| 11d | `TopKSelector()` | Stateless |
| 11e | `RetrievalEngine(embedding_index, hard_filter, soft_ranker, top_k_selector, embedding_port, registry_port)` | All 6 deps |
| 12 | `OutputValidationPipeline(state_reader, event_port)` | state_reader, event_port |
| 13a | `AvailabilityTracker(event_port, registry.update_availability)` | event_port, registry |
| 13b | `HealthChecker(provider_registry, availability_tracker, circuit_breakers, event_port)` | 4 deps |
| 14 | Wire bidirectional CB↔HealthChecker callbacks | |
| 15 | `FabricDispatcher(event_callback)` | Only if `production_mode=True` |
| 16 | `EventEmitter(event_port)` | event_port |
| 17 | `CapabilityFabric(resolver, context_builder, validation_pipeline, event_emitter, registry, provider_factory, circuit_breakers, dispatcher, config, hil_port, conscience_port)` | 11 constructor kwargs |
| 18 | `FabricRetrieval(retrieval_engine)` | retrieval_engine |
| 19 | `CapabilityRegistryAPI(registry)` | registry |
| 19b | Wire meta-tools: `BuildAgentHandler` on MCP transport | |
| 20a | `module_loader.start(watch=False)` | Scans contract YAML files |
| 20b | `_auto_register_providers(registry, provider_registry)` | Auto-populates provider configs |
| 20c | `ProactiveGapDetector(event_port, event_emitter, module_loader)` | Subscribes to contract_updated |
| 20d | `Fabric(facade, retrieval, registry_api, registry, module_loader, health_checker, event_port, event_emitter, gap_detector, context_builder)` | 10 constructor args |
| 21 | `_wire_phase1(fabric, gps, lps, idm)` | Only if GPS is not None |

### Phase 1 Wiring (Step 21)

Gated on `global_projection_store is not None`:

| Sub-step | Component | Purpose |
|----------|-----------|---------|
| 21a | `fabric.global_projection_store = gps` | Attach GPS to Fabric container |
| 21a | `fabric.idempotency_store = idm` | Attach IdempotencyStore |
| 21b | `ConstitutionLoader(gps)` | Constitution read path |
| 21c | `LocalProjectionStore(":memory:")` | Per-session in-memory store (fallback) |
| 21d | `ConnectorResolver(gps)` | MiniLM-L6 dense connector search |
| 21d | `CapabilityBinderService(gps)` | Tools + constitution assembly |
| 21e | `ResolveSituationService(gps, lps, connector_resolver, capability_binder, constitution_loader)` | Single-pass resolver |
| 21f | `fabric.facade._idempotency_store = idm` | Future Step-0 idempotency check |

**NOT wired in Phase 1:** `VerificationPlanRunner` (needs S8 native provider), `PolicySelectorService`, `PromptPackBuilder`.

---

## Port Protocols (`ports/` — 6 protocols)

| Protocol | Purpose | Methods |
|----------|---------|---------|
| `ISessionStateReader` | Read-only SS access (FAB-01: Fabric NEVER writes SS) | `read_section(session_id, section)`, `read_sections(session_id, names)`, `get_snapshot(session_id)` |
| `IEventPort` | Event emission + subscription (FAB-09: cognitive_trace_id) | `emit(topic, payload)`, `subscribe(topic, handler)`, `unsubscribe(handle)` |
| `IFabricK0Port` (IBridgePort) | K0 access via Cross-Kernel Bridge | `send_command()`, `query()`, `route_ifl()`, `is_available()`, `get_health()` |
| `IModelGatewayPort` | LLM access via ModelHub (capability-driven model selection) | `create_handle(budget_tokens, model_preference, capabilities, trace_id)`, `is_model_loaded()`, `list_models()`, `find_model()` |
| `IPromptSystemPort` | Prompt template resolve/compile | `resolve(template_name)`, `compile(template, variables)` |
| `IDeltaBusPort` | Agent delta emission (fire-and-forget) | `emit_delta(agent_id, delta_type, section, data)` |

**Supporting types:** `SessionSnapshot` (frozen, session_id + sections + timestamp_ms), `SubscriptionHandle`, `BridgeHealth` (available/mode/last_heartbeat/latency), `BridgeCommandResult`, `IFLRoute`, `ILLMHandle` (Protocol), `ModelCapability` (Enum: CHAT/TOOL_CALL/STRUCTURED/EMBED/VISION/BATCH), `ModelInfo`, `PromptTemplate`, `DeltaPayload`

---

## Production Adapters (`adapters/` — 7 production + 9 test)

| Adapter | Implements | Purpose |
|---------|-----------|---------|
| `SessionStateReaderAdapter` | `ISessionStateReader` | Wraps SSM, bound to single session_id. Supports dotted section paths |
| `EventPortProdAdapter` | `IEventPort` | JSON-envelope publish on K1 bus |
| `BridgeConnectionAdapter` | `IFabricK0Port` | Starts LOCAL COLD. Async send_command/query/route_ifl. Thread-safe via RLock |
| `ModelGatewayBridgeAdapter` | `IModelGatewayPort` | Bridges to ModelHub `IModelHubPort`. `LLMHandleBridge` translates generate() → HubRequest(CHAT) |
| `PromptSystemProdAdapter` | `IPromptSystemPort` | Loads YAML prompt contracts from directory. Caches + hot-reload |
| `DeltaBusProdAdapter` | `IDeltaBusPort` | Publishes delta as Envelope to `k1.agent.{agent_id}.delta.v1` |
| `NullSessionStateReaderAdapter` | `ISessionStateReader` | Returns empty for all reads (shared Fabric fallback) |
| `AutoDiscoveryMCPTransport` | IMCPTransport | Auto-discovery MCP transport |
| `AutoDiscoveryWASMRuntime` | IWASMRuntime | Auto-discovery WASM runtime |
| `LocalEventAdapter` | `IEventPort` | In-process dispatch + capture mode for tests |

---

## Resolver Subsystem (`resolver/` — 10 files)

The **single-pass resolution pipeline** called by Back/Concierge via `ResolveSituationService`.

### Core Types

| Class | Purpose |
|-------|---------|
| `RequestFrame` (frozen) | Input from Back: request_id, task_id, trace_id, actor_id, space_id, intents (list of `RequestFrameIntent`), time_window_hint, person_refs, resource_refs, safety_context |
| `RequestFrameIntent` (frozen) | intent_id, action, domain, operation_hint, resource_kind_hint, subject_hint, params |
| `BackTaskEnvelope` (frozen) | Incoming task format: envelope_id, task_id, trace_id, session_id, actor_id, space_id, tier, safety_band, task_dispatch, grounding_envelope_id, temporal_anchor_id, spatial_context_id |
| `ResolveSituationRequest` (frozen) | Input envelope: request_id, frame (RequestFrame), actor_id, space_id, session_id, tier, safety_band, disclosure_phase |
| `ResolutionEnvelope` (frozen) | Output: verdict (always `"can_execute"`), connectors (list of dict with tools + constitution), search_confidence |
| `RankedConnectorSet` | primary (dict), alternatives (list of dict) |

### Services

| Service | File | Purpose |
|---------|------|---------|
| `RequestFrameBuilder` | `request_frame_builder.py` | Maps `BackTaskEnvelope` → `RequestFrame`. Deterministic date math (NOT LLM): resolves "tomorrow", "next Monday", "3pm" → ISO 8601 |
| `ConnectorResolver` | `capability_type_resolver.py` | MiniLM-L6 dense retrieval via `gps.search_connectors(action_text, top_k=5, active_os_domains=...)`. Old 4-step graph traversal DELETED (RES-006). `UNIVERSAL_OPERATION_ALIASES` maps LLM verbs → (operation_family, effect) |
| `CapabilityBinderService` | `capability_binder.py` | `bind(connector_hits)` → list of connector dicts with tools + constitution. Primary gets full info; alternatives get summaries |
| `ResolveSituationService` | `situated_resolver.py` | **Single-pass orchestrator.** Pipeline: `frame.intents[0].action → ConnectorResolver.resolve() → CapabilityBinder.bind() → _inject_session_aware_enums() → ResolutionEnvelope`. `_inject_session_aware_enums()` populates dynamic enums from LPS connected backends |
| `ResolveResourcesService` | `resource_projection.py` | Resolves person/entity aliases + connected resources from LPS → `ResourceUniverse`. Consults GPS for connector admission status. 3-step: person_refs → resource_refs → permission/freshness/completeness checks |

### Deprecated

- `ResolvedIntentType` — explicitly marked DEPRECATED, superseded by `RankedConnectorSet`
- Legacy graph traversal — deleted RES-006 (2026-06-17), comments preserved for archaeology

---

## Provider Resolution Subsystem (`provider_resolution/` — 6 files)

5-step pipeline per execution request:

| Step | Component | Purpose |
|------|-----------|---------|
| 1 | `ProviderRegistry` | Maps `provider_id` → `ProviderConfig`. Thread-safe via RLock |
| 2 | `ProviderMatcher` | Finds providers for a contract; filters UNHEALTHY |
| 3 | `PolicyEngine` | Composite scorer: Security(3 hard gates) → Affective(+0.0–0.2) → Cognitive(+0.0–0.15) → QoS(+0.0–0.2) |
| 4 | `ProviderSelector` | Deterministic highest-scorer: policy → avg_latency → alphabetical (FAB-10) |
| 5 | `ProviderFactory` | Handler registry pattern. Instantiates from `ProviderConfig` |

## Provider Implementations (`providers/` — 11 files)

7 registered handler constructors:

| Provider | Handler | Required Port Dependencies | Notes |
|----------|---------|---------------------------|-------|
| `MCP` | `MCPProvider` | mcp_transport | stdio/SSE/streamable-http transports |
| `WASM` | `WASMProvider` | wasm_runtime | 64MB default memory, 5s default timeout |
| `BRIDGE` | `BridgeProvider` | bridge_port | K0 connector proxy via Bridge; LOCAL COLD fallback |
| `AGENT` | `AgentProvider` | registry, context_builder, model_gateway, state_reader, delta_bus, grounding_port | Most complex handler. Constructs `AgentFactory` with contract_loader + capability_names. M19.E1 audit fix prevents silent stub-mode failures |
| `WORKFLOW` | `WorkflowProvider` | workflow_registry, capability_lookup, orchestrator | Shared Fabric mode: raises ValueError (needs per-session orchestrator) |
| `CONCIERGE` | `ConciergeProvider` | concierge_router | Shared Fabric mode: raises ValueError (needs per-session concierge) |
| `LOCAL_STUB` | `LocalStubProvider` | none | In-process stub for tests |

## Core Subsystem (`core/` — 8 files)

| Component | File | Purpose |
|-----------|------|---------|
| `CapabilityRegistry` | `registry.py` | In-memory indexed catalog (by_name, by_domain, by_type, by_provider). Lifecycle tracking for created agents. Thread-safe via RLock. Version-aware duplicate detection; legacy versionless fallback |
| `ContractValidator` | `contract_validator.py` | Two-phase validation: JSON Schema Draft-07 structural + 12 semantic rules. Name pattern enforcement (FAB-11) |
| `ModuleLoader` | `module_loader.py` | Contract lifecycle: initial scan, hot-reload watching (polling daemon), programmatic registration |
| `ContextBuilder` | `context_builder.py` | 6-step execution context assembly: read required_context → fetch from SessionState → inject params → resolve prompt → apply budget → package. Filters `_DEPRECATED_GROUNDING_OVERRIDE_KEYS` |
| `ContextBudget` | `context_budget.py` | 128K token ceiling. 5-level compression: drop optional → truncate history → summarize beliefs → summarize scoreboard → keep HOT only. tiktoken/fallback counting |
| `AgentComposer` | `agent_builder.py` | 8-step agent creation: validate spec → resolve capabilities → build AgentContract → register → create AgentProvider → wire delta bus → start health check → return agent_id |
| `BuildAgentHandler` | `agent_builder.py` | MCP-callable handler. Registered as `tool.write.build_agent` on MCP transport (Step 19b) |
| `DiscoverCapabilitiesHandler` | `discovery_tools.py` | 3 MCP-callable discovery tools: discover_capabilities, find_prompts, get_capability_schema |

## Policy Engine (`policy/` — 9 files)

Composite scoring: `base_score + affective(0.0–0.2) + cognitive(0.0–0.15) + qos(0.0–0.2)`

| Dimension | Component | Purpose |
|-----------|-----------|---------|
| Security (3.2.1) | `SecurityContext` | 3 hard gates: safety band, sub-agent tool scoping, rate limiting |
| Affective (3.2.2) | `AffectiveRouting` | Soft score based on user emotional state from SS |
| Cognitive (3.2.3) | `CognitiveLoadRouting` | Soft score based on cognitive load. Falls back to legacy `"cognitive"` section |
| QoS (3.2.4) | `QoSIntegration` | Soft score based on budget/latency constraints |
| Composite (3.2.5) | `PolicyEngine` | Orchestrates all 4 dimensions |
| Tool Scope (3.2.6) | `ToolScope` | Enforces sub-agent `tools_granted[]` before each invocation (FAB-07) |
| Selector (Epic 4.1) | `PolicySelectorService` | Evaluates connector policy declarations against actor, typed intents, safety context |
| Meta-Op (4.5.5) | `MetaOperationValidator` | 5 gates for agent creation: tool pattern, restricted domains, safety band, rate limit, scope |

## Output Validation (`output_validation/` — 6 files)

3-tier pipeline: Structural → Schema → Semantic. Short-circuits on hard failure.

| Tier | Validator | Checks |
|------|-----------|--------|
| 1 | `StructuralValidator` | Required fields, well-formed data, truncation detection, size limits (1 MiB) |
| 2 | `SchemaValidator` | JSON Schema compliance. `SchemaCompiler` caches compiled schemas. Coercion helpers |
| 3 | `SemanticValidator` | Hallucination detection for agent/LLM outputs. Soft failure only |
| Fallback | `ValidationFallback` | Structural→REJECT, Schema→coerce→REJECT, Semantic→annotate. Emits `k1.fabric.output.validation.failed.v1` |

## Retrieval Subsystem (`retrieval/` — 6 files)

4-step pipeline for capability discovery:

| Step | Component | Purpose |
|------|-----------|---------|
| 1 | `EmbeddingIndex` | Dense vector embedding for semantic search |
| 2 | `HardFilter` | Filters by required constraints (safety_band, tier, context_precision) |
| 3 | `SoftRanker` | Composite scoring: semantic similarity + recency + success rate + policy score |
| 4 | `TopKSelector` | Selects top-K results |

`RetrievalEngine` orchestrates all 4 steps. Used by `FabricRetrieval.retrieve()` for discovery.

## Other Subsystems

| Subsystem | Directory | # Files | Purpose |
|-----------|-----------|---------|---------|
| Circuit Breaker | `circuit_breaker/` | 3 | Per-provider CB: CLOSED→OPEN→HALF_OPEN. Sliding-window failure tracking, max 2 retries. Thread-safe. 7 provider-specific configs |
| Concurrency | `concurrency/` | 3 | `FabricDispatcher`: bounded semaphore with backpressure (NORMAL→WARNING 80%→SHEDDING 95%→SATURATED). `TimeoutGuard`: deadline enforcement |
| Health | `health/` | 3 | `AvailabilityTracker`: ONLINE/DEGRADED/OFFLINE per provider. `HealthChecker`: periodic async probes, bidirectional CB integration |
| Events | `events/` | 3 | `EventEmitter` wraps `IEventPort`. 16 emitted + 4 consumed event payload types. 20 topic constants. `ProactiveGapDetector` (5.4.4) |
| Contracts | `contracts/` | 6 | 4 YAML parsers (tool, agent, prompt, workflow). Auto-detection via root key. DAG acyclicity validation for workflows |
| Constitution | `constitution/` | 3 | `ConstitutionArtifact` typed shape + two-phase validation. `ConstitutionLoader` reads from GPS |
| Connectors | `connectors/` | 3 | `ConnectorDefinition` typed dataclasses. 50 `ServiceDefinitions` across 5 domains (family, enterprise, health, education, home) |
| Prompt Pack | `prompt_pack/` | 2 | `PromptPackBuilder`: 5 disclosure phases, triple-checked redaction, constitution cards |
| Verification | `verification/` | 2 | `VerificationPlanRunner` — post-write verification (wired post-S8) |
| Stores | `stores/` | 4 | GPS + LPS + IdempotencyStore (see S2.10) |

---

## Fabric Container (`Fabric` dataclass)

```python
@dataclass
class Fabric:
    facade: CapabilityFabric          # execute(), execute_batch()
    retrieval: FabricRetrieval        # retrieve(), discover()
    registry_api: CapabilityRegistryAPI  # register(), unregister(), list()
    registry: CapabilityRegistry      # Low-level registry access
    module_loader: ModuleLoader       # Contract lifecycle
    health_checker: HealthChecker     # Provider health monitoring
    event_port: IEventPort            # Event bus
    event_emitter: EventEmitter       # Typed event emission
    gap_detector: ProactiveGapDetector  # Contract-gap detection
    context_builder: ContextBuilder   # Execution context assembly
    global_projection_store: Optional[Any] = None  # Phase 1 GPS
    idempotency_store: Optional[Any] = None        # Phase 1 idempotency
```

## Factory Methods Summary

| Method | Production Mode | State Reader | Session | Use Case |
|--------|----------------|--------------|---------|----------|
| `create_standalone()` | False | Test adapter | No | Dev/examples/unit tests |
| `create_for_testing()` | False | Test adapter (capture mode) | No | Integration tests |
| `create_with_ports()` | Configurable | Required | Yes (bound) | Production per-session |
| `create_shared()` | True | Optional (Null adapter fallback) | No (routing reader) | Kernel shared tier |

## 4 Factory Methods

| Method | Production | Session | Use Case |
|--------|-----------|---------|----------|
| `create_standalone(**kwargs)` | False | No | Dev, examples, unit tests. All test adapters |
| `create_for_testing(**kwargs)` | False | No | Integration tests with event capture |
| `create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus, **kwargs)` | Configurable | Yes | Production per-session deployment |
| `create_shared(event_port, bridge, model_gateway, prompt_system, delta_bus, **kwargs)` | True | Optional | Kernel-level shared (Orchestrator, Planner) |

---

## Where Fabric Is Consumed

| Consumer | Bus | How |
|----------|-----|-----|
| **Concierge Front/Back** | Session bus | `FabricDispatchAdapter` wraps per-session Fabric. `dispatch_direct()` for LOW tier, `dispatch_envelope()` routes MED/HIGH to orchestrator. Tools: `invoke_capability`, `batch_invoke_capabilities` |
| **Orchestrator** | Kernel bus | `FabricGatewayAdapter(fabric=self._shared_fabric)`. StepRunner gets fabric for capability execution. MCPRegistrationBridge for dynamic tool registration |
| **Planner** | Kernel bus | `FabricRetrievalAdapter(fabric_retrieval=self._shared_fabric.retrieval)` for semantic Top-K discovery. `FabricRegistryAdapter(registry=self._shared_fabric)` for exact-name capability lookup (P03 fix) |
| **Back LLM** | Session bus | `ResolveSituationService` (Phase 1, wired at step 21) for connector search → tools assembly |

### Event Topics

19 topic constants emitted by Fabric:
`k1.fabric.capability.invoked.v1`, `k1.fabric.capability.completed.v1`, `k1.fabric.capability.failed.v1`, `k1.fabric.learning.signal.v1`, `k1.fabric.capability.registered.v1`, `k1.fabric.capability.unregistered.v1`, `k1.fabric.version.conflict.v1`, `k1.fabric.contract.validation.failed.v1`, `k1.fabric.output.validation.failed.v1`, `k1.fabric.provider.health.changed.v1`, `k1.fabric.contract.updated.v1`, `k1.fabric.pressure.warning.v1`, `k1.fabric.pressure.shedding.v1`, `k1.fabric.agent.created.v1`, `k1.fabric.agent.expired.v1`, `k1.fabric.meta.operation.blocked.v1`

---

---

# S5 — OrchestratorService

**File:** `k1/orchestrator/` — ~69 Python files across 6 subdirectories + 8 top-level .py files + 8 .md docs
**Init:** `_startup_tier1()` L2001 — `OrchestratorFactory.create_production(config, adapters, hil_port=self._hil_service)`. MockPlannerAdapter installed; hot-swapped to real PlannerAdapter at S6b.
**Config gate:** Always created (no feature flag). Config from `OrchestratorConfig.from_dict(...)`.
**Lifecycle:** Created at S5 after shared Fabric (S3), before Planner (S6). Runs background `asyncio.Task` dequeue loop. Shutdown at kernel close after Planner task, before shared Fabric.
**Architecture:** Hexagonal ports & adapters. 8 port protocols, 15 adapter implementations, 6-guard DAG execution pipeline. Central `OrchestratorService` actor processes tasks from a WFQ priority mailbox. Routes MEDIUM tasks directly to Fabric; HIGH tasks follow Plan→DAG→Execute→Aggregate pipeline with Planner integration. Owns `CB_PLANNER` circuit breaker and `WorkflowEngine` for scheduled workflow execution. Admin HTTP server with 18 endpoints on port 8081. 20 emitted + 10 consumed event topics.

## Dead Code & Legacy Audit

| Finding | File | Detail |
|---------|------|--------|
| Legacy dict-based API | `orchestration/param_resolver.py:207-264` | `resolve_step()` wrapping `resolve_params()`. Comment: "remove in M7" |
| Legacy step-id-keyed buckets | `orchestration/dag_executor.py:1228` | Legacy/contract behavior comment |
| Legacy `TriggerType.CRON` string | `workflows/persistence/sqlite_adapter.py:316` | Legacy EnumMember string form |
| Unused V1 params | `orchestration/guards/execution_monitor.py:196-197` | `remaining_steps`, `plan_id` unused by this guard |
| Unused context | `orchestration/error_router.py:135` | `ctx` parameter reserved for future |
| MockPlannerAdapter window | `kernel/service.py` S5→S6b | Any task arriving before S6b cross-wire gets canned responses |

**No FIXME/HACK/XXX/DEPRECATED markers** found in production code. Legacy paths are well-documented with `# Legacy` or `# remove in M7` comments.

---

## Top-Level Files (8 files)

| File | ~Lines | Purpose |
|------|--------|---------|
| `__init__.py` | ~180 | Public API — re-exports ~100+ names: config, services, ports, enums, dataclasses, event constants, workflow types |
| `config.py` | ~260 | `OrchestratorConfig` frozen dataclass — 10 config groups, 40+ fields. `default()`, `from_dict()`, `to_dict()`. Comprehensive `__post_init__` validation |
| `types.py` | ~900+ | All domain types — 6 enums, 30+ frozen dataclasses, 4 guard protocols. NO I/O or port references |
| `events.py` | ~160 | Event catalog — 20 emitted + 10 consumed topic string constants. `ALL_EMITTED`, `ALL_CONSUMED` frozensets |
| `factory.py` | ~600+ | `OrchestratorFactory` — static composition root. 4 factory methods + 15-step `_construct_orchestrator()` |
| `metrics.py` | ~300 | `OrchestratorMetrics` — 20+ timing methods + 10+ counter/gauge helpers. Zero-overhead `NullMetricsCollector` |
| `tracing.py` | ~80 | Structured JSON trace logging. `new_trace_id()`, `ensure_trace_id()`, `build_trace_log()`, `trace_phase()` |
| `degradation.py` | ~200 | `CircuitBreaker` — Thread-safe 3-state breaker (CLOSED/OPEN/HALF_OPEN). Per-owner instance (no singletons) |

---

## Configuration (`OrchestratorConfig` — 10 Groups, 40+ Fields)

| Group | Key Fields | Defaults |
|-------|-----------|----------|
| **Concurrency** | max_concurrent_dags, max_wave_parallelism, mailbox_capacity | 1, 5, 100 |
| **Timeouts (ms)** | default_step_timeout_ms, plan_request_timeout_ms, drain_timeout_ms, shutdown_grace_period_ms | 10000, 45000, 30000, 30000 |
| **Retry** | step_max_retries, step_retry_base_delay_ms, step_retry_max_delay_ms, max_deferred_plan_retries | 2, 100, 5000, 5 |
| **Guards** | guard_order (6 guards), max_micro_replans, substep_rate_limit_ms | [ConcurrencyGuard, ConditionalEdgeEvaluator, OutputSchemaGuard, ExecutionMonitor, MicroReplanCheckpoint, SafetyBandReRead], 1, 500 |
| **Workflow** | max_workflow_depth, workflow_db_path, scheduler_tick_interval_ms, workflow_plan_max_age_ms | 3, `data/orchestrator_workflows.db`, 1000, 30000 |
| **MCP** | mcp_config_path, mcp_discovery_interval_ms, mcp_max_servers | `k1/connectors/mcp_servers.yaml`, 300000, 10 |
| **CB** | cb_planner_failure_threshold, cb_planner_reset_timeout_ms | 3, 60000 |
| **Telemetry** | metrics_enabled, structured_log_level, trace_sample_rate | True, INFO, 1.0 |
| **Admin** | admin_enabled, admin_port | True, 8081 |
| **Pending Limits** | max_pending_plans | 50 |

---

## Domain Types (`types.py` — 6 Enums + 30+ Dataclasses)

### Enums

| Enum | Values |
|------|--------|
| `StepStatus` | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, SKIPPED |
| `TriggerType` | CRON, EVENT, MANUAL |
| `ProcessResult` | COMPLETED, FAILED, DEGRADED, CANCELLED, DEFERRED |
| `ErrorSeverity` | RECOVERABLE, DEGRADED, TERMINAL |
| `ProactiveGapStatus` | PENDING, ASKED, RESOLVED, AUTO_RESOLVED |
| `GuardAction` | ALLOW, REJECT, CONTINUE, RETRY, SKIP, HARD_STOP, DEGRADE, DEFER, BYPASS |

### Key Dataclasses (all frozen)

| Layer | Types |
|-------|-------|
| **Core Envelopes** | `TaskEnvelope` (intent, trace_id, caller_id, context, tier, capabilities, params, constraints, grounding, timeout_ms), `StepResult` (step_id, capability_name, status, duration_ms, result, retry_attempts), `PlanStep` (15 fields: 6 Fabric-aligned + 9 Orchestrator extensions), `Wave` (wave_index, steps, resolved_params) |
| **Plan & Result** | `PlanRequest`, `CommittedPlan` (cycle detection via Kahn's algorithm in `__post_init__`), `AggregatedResult` (factory methods `from_medium()`, `from_dag()`), `MicroReplanRequest`, `WaveResult` |
| **Workflow** | `WorkflowRunRequest`, `WorkflowSaveRequest`, `ProactiveGap` |
| **Leaf Types** | `AdapterError`, `OrchestratorPolicies`, `CompensationRecord`, `MCPServerRegistration`, `InterruptRequest`, `TriggerSpec`, `ConditionExpr`, `Discovery`, `FailureContext`, `ValidationResult`, `AlternativeCapability`, `CapabilityCheck`, `ResolutionResult`, `RegistryEntry` |
| **Guard/Admin** | `GuardDecision`, `CircuitBreakerConfig`, `ActiveDAGInfo`, `DrainResult`, `RecoveryResult`, `HealthStatus` |

### Guard Protocols (all `@runtime_checkable`)

| Protocol | Signature | Purpose |
|----------|-----------|---------|
| `IPreWaveGuard` | `async evaluate(wave, dag_id, ctx, ...) -> GuardDecision` | Pre-wave gate (edge pruning, condition eval) |
| `IPostStepGuard` | `async evaluate(step_result, step, dag_id, ctx, ...) -> GuardDecision` | Post-step gate (schema validation) |
| `IPostWaveGuard` | `async evaluate(wave_result, wave, dag_id, ctx, ...) -> GuardDecision` | Post-wave gate (monitoring, replan triggers) |
| `PreDispatchGuard` | `async evaluate(task_envelope, processing_ctx, ...) -> GuardDecision` | Pre-dispatch gate |

---

## 15-Step Factory Construction (`_construct_orchestrator()`)

| Step | Component | Dependencies | Notes |
|------|-----------|-------------|-------|
| 1 | `Policies = _build_policies(config)` | config | Runtime policy limits |
| 2 | `ErrorRouter(policies)` | policies | Classifies errors → RECOVERABLE/DEGRADED/TERMINAL |
| 3 | `ConstraintResolver(fabric_port, hil_port, max_cycles=2)` | fabric_port, hil_port | Alternative capability resolution |
| 4 | `ParamResolver()` | none | Stateless param resolution with legacy return-path |
| 5 | `StepRunner(fabric_port, param_resolver, policies, event_port)` | fabric_port, param_resolver, policies, event_port | Single-step execution with retry + schema retry |
| 6 | `Guards = _build_guards(planner_port, delta_port, hil_port, max_micro_replans)` | planner_port, delta_port, hil_port | Ordered guard list (5 guards V1) |
| 7 | `DAGExecutor(step_runner, guards, error_router, policies, event_port)` | step_runner, guards, error_router, policies, event_port | Wave-based DAG execution |
| 8 | `WorkflowScheduler(storage_port, mailbox_port, config)` | storage_port, mailbox_port | Tick-based trigger firing |
| 9 | `WorkflowCompiler(fabric_port, storage_port, config)` | fabric_port, storage_port | Plan→workflow compilation |
| 10 | `WorkflowRegistry(storage_port)` | storage_port | Workflow CRUD facade |
| 11 | `CrossWorkflowResolver(storage_port)` | storage_port | Cross-workflow dependency resolution |
| 12 | `GapDetector(fabric_port, storage_port, config)` | fabric_port, storage_port | Proactive capability gap detection |
| 13 | `WorkflowSupervisor(dag_executor, constraint_resolver)` | dag_executor, constraint_resolver | Workflow execution supervision |
| 14 | `WorkflowEngine(supervisor, dag_executor, constraint_resolver, registry, compiler, scheduler, cross_resolver, gap_detector, delta_port, bridge_port)` | 10 dependencies | Workflow subsystem facade |
| 15 | `OrchestratorService(mailbox_port, fabric_port, planner_port, state_port, delta_port, bridge_port, event_port, storage_port, config, policies, dag_executor, error_router, workflow_engine, metrics, hil_port)` | 15 constructor args | **The main service** |

### Factory Methods

| Method | Mailbox | Fabric | Planner | State | Bridge | Event | Storage | HIL | Use Case |
|--------|---------|--------|---------|-------|--------|-------|---------|-----|----------|
| `create_standalone()` | Test | Mock | Mock | Mock | Mock | Test | Test | None | Dev/examples |
| `create_for_testing(**overrides)` | Test | Mock | Mock | Mock | Mock | Test | Test | None | Integration tests |
| `create_with_ports(**adapters)` | Required | Required | Required | Required | Required | Required | Required | Required | Custom deployment |
| `create_production(config)` | Required | Required | Mock→Real | Required | Required | Required | Required | Required | Full production |

`create_production()` calls `init()` automatically after construction.

---

## Port Protocols (`ports/` — 8 protocols)

| Protocol | Purpose | Key Methods |
|----------|---------|-------------|
| `IMailboxPort` | WFQ priority inbox (3 classes: REALTIME 0.6, INTERACTIVE 0.3, BACKGROUND 0.1) | `enqueue(msg, priority)`, `dequeue()`, `depth()` |
| `IFabricGatewayPort` | Capability Fabric execution + registry queries | `execute(request, cancellation_token)`, `execute_batch()`, `query_registry()` |
| `IPlannerPort` | Planner integration with CB gating | `request_plan(request)`, `cancel_plan()`, `micro_replan()` |
| `IStateReadPort` | Read-only SessionState access (ORCH-01: NEVER writes) | `read_section()`, `read_sections()`, `get_snapshot()` |
| `IDeltaEmitPort` | Fire-and-forget event + progress emission | `emit(topic, payload, trace_id)`, `emit_progress()` |
| `IBridgeWritePort` | K0 audit/WAL/deferred-result writes (Edge-First) | `submit_audit()`, `write_wal()`, `read_wal()`, `submit_deferred_result()` |
| `IEventSubscriptionPort` | Event bus subscription management | `subscribe(topic, handler)`, `unsubscribe(handle)`, `emit()` |
| `IWorkflowStoragePort` | Workflow/trigger/run/gap CRUD persistence | `save_workflow()`, `get_due_triggers()`, `save_gap()` |

---

## Production Adapters (`adapters/` — 11 production + 6 test)

| Adapter | Implements | Purpose |
|---------|-----------|---------|
| `MailboxAdapter` | `IMailboxPort` | In-process WFQ priority mailbox. Thread-safe via Lock. Max depth 100 |
| `FabricGatewayAdapter` | `IFabricGatewayPort` | Wraps shared `Fabric` facade. Pure pass-through, NO CB owned (PROTOCOL-4: Concierge owns CB_FABRIC). Supports cooperative cancellation |
| `PlannerAdapter` | `IPlannerPort` | Wraps planner mailbox. OWNS `CB_PLANNER`. `micro_replan()`: sync 10s timeout (PROTOCOL-3). `_check_cb_open()` on all outbound calls |
| `StateReadAdapter` | `IStateReadPort` | Wraps `ISessionStateReader`. Read-only pass-through (ORCH-01) |
| `BridgeWriteAdapter` | `IBridgeWritePort` | Wraps K0 bridge client. Fire-and-forget writes (Edge-First). Blocking reads for crash recovery. 6 WAL entry types |
| `DeltaEmitAdapter` | `IDeltaEmitPort` | Dual-publishes to `IEventPort` + `IDeltaBusPort`. NEVER raises |
| `EventSubscriptionAdapter` | `IEventSubscriptionPort` | Wraps Fabric `IEventPort`. Tracks handles for shutdown bulk-unsubscribe |
| `WorkflowStorageAdapter` | `IWorkflowStoragePort` | Thin pass-through wrapping `SQLiteWorkflowAdapter`. Error→AdapterException translation |
| `AdminHttpAdapter` | `IAdminPort` | Lightweight aiohttp HTTP server. 18 endpoints across 10 groups. Binds 127.0.0.1:8081 |
| `BridgeClientShim` | IBridgeClient | Adapts `SinkBridgeClient` (`submit_command`) → `write`/`read` protocol |
| `MockPlannerAdapter` | `IPlannerPort` | Scriptable test adapter. Used as factory default at S5; hot-swapped to `PlannerAdapter` at S6b |

---

## 6-Guard DAG Execution Pipeline

Applied in order per wave. Guards return `GuardDecision(action, reason)`:

| # | Guard | Phase | Purpose |
|---|-------|-------|---------|
| 1 | `ConcurrencyGuard` | Pre-dispatch (wraps `_process_one`) | Ensures max 1 concurrent DAG (ORCH-02). Enqueues overflow as DEFERRED |
| 2 | `ConditionalEdgeEvaluator` | Pre-wave | Evaluates `PlanStep.condition` expressions. Prunes unsatisfied edges. |
| 3 | `OutputSchemaGuard` | Post-step | Validates step output against `PlanStep.output_schema`. Triggers schema retry (1 attempt with corrected params) |
| 4 | `ExecutionMonitor` | Post-wave | Emits progress deltas. Requests HIL override on constraint violations. Skips if `hil_port is None` |
| 5 | `MicroReplanCheckpoint` | Post-wave | Discovery heuristic: if ≥1 step failed with `Discovery` hints, requests micro-replan from Planner (max 1 replan, ORCH-13) |
| 6 | `FailureReplanCheckpoint` | Post-wave (last) | M16.E2.I2: Failure-driven replan. Runs LAST to capture all failures after other guards have run |
| * | `SafetyBandReRead` | Pre-step | Re-reads safety band from SessionState before each step execution. Ensures real-time policy compliance |
| * | `SubStepObserver` | DAGExecutor lifecycle | Internal observer for step lifecycle events (not a guard, but part of the pipeline) |

### Guard Configuration

```python
_DEFAULT_GUARD_ORDER = [
    "ConcurrencyGuard",
    "ConditionalEdgeEvaluator",
    "OutputSchemaGuard",
    "ExecutionMonitor",
    "MicroReplanCheckpoint",
    "SafetyBandReRead"
]
```

V2 guards registered but not active: `TokenBudgetTracker`, `CostBudgetGuard`, `QualityGate`.

---

## OrchestratorService — Central Dispatch Actor (~2900 lines)

### Constructor (15 dependencies)

`__init__(mailbox_port, fabric_port, planner_port, state_port, delta_port, bridge_port, event_port, storage_port, config, policies, dag_executor, error_router, workflow_engine, metrics, hil_port)`

### Properties

`hil_port`, `planner_port`, `planner_port_is_real_planner_adapter`, `planner_port_is_mock`, `planner_port_mailbox_is_planner_mailbox`, `dag_executor`

### Core Methods

| Method | Purpose |
|--------|---------|
| `async init()` | Subscribes to PLAN_READY/PLAN_FAILED/PLAN_CANCELLED events. Starts admin HTTP server. Starts workflow scheduler. |
| `async run()` | **Main dequeue loop.** `while not _draining: msg = await mailbox.dequeue(); await _process_one(msg)` |
| `async process(task_envelope) -> ProcessResult` | Public entry point for external callers. Enqueues to mailbox; returns COMPLETED/DEFERRED immediately |
| `async _process_one(msg) -> ProcessResult` | Internal dispatch. ConcurrencyGuard gate → classify tier → `dispatch_medium()` or `dispatch_high()` |
| `async dispatch_medium(envelope) -> AggregatedResult` | MEDIUM tier: re-read safety band from SS → Fabric.execute_batch() with `max_wave_parallelism` parallel execution |
| `async dispatch_high(envelope) -> AggregatedResult` | HIGH tier: save pending context → request_plan from Planner → await PLAN_READY → receive_plan → DAGExecutor → aggregate |
| `async receive_plan(committed_plan) -> AggregatedResult` | Receives committed plan from Planner. Re-reads safety band. Runs DAGExecutor with full guard pipeline |
| `async bind_planner(planner_adapter)` | **Hot-swap** at S6b. Replaces `MockPlannerAdapter` with real `PlannerAdapter`. Rebuilds guards |
| `async shutdown()` | Drains mailbox → cancels pending plans → stops scheduler → stops admin → closes storage |
| `async drain()` | Graceful drain: stops accepting new tasks, completes in-flight DAGs, returns `DrainResult` |
| `async cancel_plan(request_id)` | Cancels a pending plan by request_id |
| `async interrupt(interrupt_request)` | CANCEL_DAG or PAUSE a running DAG |

### Event Handlers (subscribed at `init()`)

| Handler | Topic | Action |
|---------|-------|--------|
| `_on_plan_ready()` | `k1.planner.plan.ready.v1` | Resolves pending Future for `request_plan()` |
| `_on_plan_failed()` | `k1.planner.plan.failed.v1` | Resolves with failure |
| `_on_plan_cancelled()` | `k1.planner.plan.cancelled.v1` | Resolves with cancellation |

---

## DAG Executor (`orchestration/dag_executor.py`)

Wave-based parallel execution with full guard pipeline.

### Execution Flow

```
execute_dag(committed_plan, ctx)
  ├─ Build waves (topological sort by dependencies)
  ├─ FOR each wave:
  │   ├─ Pre-wave guards (ConditionalEdgeEvaluator)
  │   ├─ Execute wave steps in parallel (up to max_wave_parallelism)
  │   │   ├─ SafetyBandReRead (pre-step)
  │   │   ├─ StepRunner.run(step) → StepResult
  │   │   ├─ Post-step guard (OutputSchemaGuard)
  │   │   └─ Retry logic (max step_max_retries, schema retry 1)
  │   ├─ Post-wave guards (ExecutionMonitor, MicroReplanCheckpoint, FailureReplanCheckpoint)
  │   ├─ IF micro_replan triggered → re-plan remaining steps → continue
  │   └─ Saga compensation for failed side-effect steps
  └─ Aggregate results → AggregatedResult
```

### StepRunner

Executes a single step through Fabric with retry:

1. `resolve_params()` — parameter resolution with discovery lookups
2. Build `CapabilityRequest` from `PlanStep`
3. `fabric_port.execute(request, cancellation_token)` — with cooperative cancellation
4. Retry on failure (exponential backoff: 100ms → 5000ms max, 2 retries)
5. Schema retry (1 attempt): if OutputSchemaGuard fails, re-execute with corrected params

---

## Constraint Resolver (`orchestration/constraint_resolver.py`)

Alternative capability resolution when a step's primary capability fails:

1. Query Fabric registry for alternative capabilities matching same `(domain, resource_family, operation_family, effect)`
2. Score alternatives by: semantic similarity + safety_band match + availability + cost
3. If no automated alternative found → HIL override request (falls back if `hil_port is None`)
4. Max 2 resolution cycles
5. Returns `ResolutionResult` with modified plan or `hil_requested=True`

---

## Workflow Subsystem (`workflows/` — 11 files)

| Component | Purpose |
|-----------|---------|
| `WorkflowEngine` | Facade: `execute_workflow(request)`, `save_workflow(request)`. Hides all subsystem complexity |
| `WorkflowScheduler` | 1s tick loop. `croniter` for CRON triggers. Fires due triggers as INTERACTIVE priority mailbox messages |
| `WorkflowCompiler` | Compiles `CommittedPlan` → workflow spec. Cached with TTL (30s). Validates max_depth (3, ORCH-12) |
| `WorkflowRegistry` | CRUD facade over `IWorkflowStoragePort` |
| `CrossWorkflowResolver` | Resolves dependencies between workflows. Upstream/downstream chain walking |
| `WorkflowSupervisor` | Oversees DAG execution for workflows. Delegates to `DAGExecutor` + `ConstraintResolver` |
| `GapDetector` | Proactive capability gap detection. Scans for missing/outdated capabilities. Cooldown 5s, concurrency 5 |
| `SQLiteWorkflowAdapter` | SQLite WAL persistence at `./data/orchestrator_workflows.db`. Workflow/trigger/run/gap tables |

### Workflow Tables (SQLite)

- `workflows` — workflow_id, name, plan_json, trigger_spec, created_at, updated_at
- `triggers` — workflow_id, trigger_type, next_fire_at, last_fired_at, enabled
- `runs` — run_id, workflow_id, dag_id, status, started_at, completed_at, result_json
- `gaps` — gap_id, capability_name, status, discovered_at, resolved_at

---

## Connector Lifecycle (`connectors/` — 4 files)

| Component | Purpose |
|-----------|---------|
| `ConnectorLifecycleManager` | Monitors connector health events. Subscribes to `k1.fabric.provider.health.changed.v1` |
| `MCPDiscovery` | Periodic MCP server discovery (5min interval). Reads `k1/connectors/mcp_servers.yaml` |
| `MCPRegistrar` | Registers discovered MCP tools into Fabric registry |
| `K0ProxyClient` | Proxies K0 connector calls through Bridge |

---

## Event Catalog (30 Topics)

### Emitted (20)

`k1.orchestration.task.accepted.v1`, `k1.orchestration.plan.requested.v1`, `k1.orchestration.dag.started.v1`, `k1.orchestration.dag.micro_replan.v1`, `k1.orchestration.dag.node_failed.v1`, `k1.orchestration.dag.completed.v1`, `k1.orchestration.step.started.v1`, `k1.orchestration.step.completed.v1`, `k1.orchestration.step.failed.v1`, `k1.orchestration.step.cancelled.v1`, `k1.orchestration.step.skipped.v1`, `k1.orchestration.step.retrying.v1`, `k1.orchestration.step.schema_retry.v1`, `k1.orchestration.saga.compensating.v1`, `k1.orchestration.delta.v1`, `k1.orchestration.workflow.triggered.v1`, `k1.orchestration.workflow.completed.v1`, `k1.orchestration.workflow.saved.v1`, `k1.orchestration.error.routed.v1`, `k1.orchestration.mcp.tool_registered.v1`

### Consumed (10)

`k1.planner.plan.ready.v1`, `k1.planner.plan.failed.v1`, `k1.planner.plan.cancelled.v1`, `k1.planner.micro_replan.ready.v1`, `k1.capability.completed.v1`, `k1.capability.failed.v1`, `k1.fabric.contract.updated.v1`, `k1.fabric.agent.tool_call.v1`, `k1.fabric.agent.llm_call.v1`, `k1.orchestration.workflow.trigger_due.v1`

---

## Admin HTTP API (18 Endpoints)

| Group | Endpoints |
|-------|-----------|
| Health | `/health/live`, `/health/ready`, `/health/status` |
| DAG | `GET /admin/dags`, `GET /admin/dags/{dag_id}`, `POST /admin/dags/{dag_id}/cancel` |
| CB | `GET /admin/circuit-breakers`, `POST /admin/circuit-breakers/{name}/state` |
| Scheduler | `GET /admin/scheduler/triggers`, `GET /admin/scheduler/triggers/{workflow_id}` |
| Drain | `POST /admin/drain` |
| Config | `GET /admin/config` |
| Mailbox | `GET /admin/mailbox/depth`, `GET /admin/mailbox/stats` |
| MCP | `GET /admin/mcp/servers`, `POST /admin/mcp/rediscover` |
| Metrics | `GET /admin/metrics` |
| Version | `GET /admin/version` |

---

## Where Orchestrator Is Consumed

| Consumer | Bus | How |
|----------|-----|-----|
| **Concierge** | Session bus → kernel bus | `FabricDispatchAdapter.dispatch_envelope()` publishes MED/HIGH tasks to `k1.orchestration.task.dispatch.v1`. Orchestrator subscribes via mailbox |
| **Planner** | Kernel bus | Orchestrator requests plans via `IPlannerPort` (mailbox + event-driven PLAN_READY). S6b hot-swaps MockPlannerAdapter→PlannerAdapter |
| **Fabric** | Kernel bus | `FabricGatewayAdapter` wraps shared Fabric for step execution + registry queries |
| **HIL** | Kernel bus | `ExecutionMonitor` requests overrides. `ConstraintResolver` requests human fallback |
| **Bridge (K0)** | Kernel bus | `BridgeWriteAdapter` writes audit/WAL/deferred results. Edge-First: writes fire-and-forget |
| **SessionState** | Session bus | `StateReadAdapter` reads safety band + user preferences (ORCH-01: NEVER writes) |
| **Admin** | HTTP | `AdminHttpAdapter` on 127.0.0.1:8081 for operational control |

### Task Routing (Tier-Based)

```
Concierge → FabricDispatchAdapter
  ├─ LOW tier    → dispatch_direct() → Fabric.execute() directly
  └─ MED/HIGH tier → dispatch_envelope() → k1.orchestration.task.dispatch.v1
                       └─ OrchestratorService mailbox
                            ├─ MEDIUM → dispatch_medium() → Fabric.execute_batch() (parallel)
                            └─ HIGH   → dispatch_high() → Planner → DAG → Execute → Aggregate
```

---

---

# S6 — PlannerAgent

**File:** `k1/planner/factory.py` → `PlannerFactory.create_production()`
**Init:** `_startup_tier1()` L2080
**Lifecycle:** Shared Tier-1 component. 4-stage pipeline (Sketch→Expand→Validate→Commit) for HIGH tier tasks. Runs as background `asyncio.Task`.

| Adapter | Purpose |
|---------|---------|
| `LLMGatewayAdapter` | LLM calls via ModelHub `ModelHubRequestBus` |
| `FabricRetrievalAdapter` | Semantic Top-K capability discovery |
| `FabricRegistryAdapter` | Exact-name capability lookup (P03 fix) |
| `PlannerStateAdapter` | Per-session SS reads |
| `PlannerBridgeAdapter` | Bridge operations |
| `PlannerDeltaBusAdapter` | Delta emission |
| `PlannerEventBusAdapter` | Event subscriptions |
| `PlannerMailboxAdapter` | Message routing |
| HIL port | `HumanInTheLoopService` (S2.5) |

**Crash recovery:** Planner task has done-callback watchdog. Monitored by `_verify_planner_task_running()`.

---

# S6b — Orchestrator↔Planner Cross-Wire

**Init:** `_startup_tier1()` L2110
Replaces `MockPlannerAdapter` with real `PlannerAdapter` on the orchestrator. Wires `CircuitBreaker` for planner health.

---

# S7 — Planner Background Task

**Init:** `_startup_tier1()` L2116
`asyncio.create_task(planner.start(), name="planner-agent")`. Long-running dequeue loop.

---

# S8 — FamilyToolsBundle

**File:** `k1/tools/family/bootstrap.py`
**Init:** `_startup_tier1()` L2144
**Config gate:** `enable_family_tools` (True in production)
**Lifecycle:** Shared bundle. Owns `K1FamilyStore` SQLite connection and `ToolRegistry`.

| Component | Purpose |
|-----------|---------|
| `K1FamilyStore` | SQLite WAL storage at `./data/k1_family.db` |
| `ToolRegistry` | Registers all 6 family adapters + 52 capabilities into shared Fabric |
| `NativeToolProvider` | LOCAL provider type, re-registered per session at P3.1 |

**6 FamilyOS adapters registered:**

| Adapter | Capabilities |
|---------|-------------|
| `family.calendar` | 10 (create_event, update_event, delete_event, list_events, get_event, respond_to_invite, set_visibility, connect_feed, disconnect_feed, list_feeds) |
| `family.shopping` | 11 (create_list, delete_list, list_lists, add_item, update_item, approve_item, reject_item, check_off_item, delete_item, list_items, get_item) |
| `family.tasks` | 10 (create_task, update_task, complete_task, reopen_task, reassign_task, delete_task, list_tasks, get_task, create_list, list_lists) |
| `family.reminders` | 8 (create_reminder, update_reminder, snooze_reminder, dismiss_reminder, fire_reminder, delete_reminder, list_reminders, get_reminder) |
| `family.chores` | 9 (create_template, update_template, delete_template, assign_chore, complete_chore, skip_chore, reopen_chore, list_chores, chore_summary) |
| `family.family_settings` | 4 (get_visibility_policy, update_visibility_policy, list_feature_flags, set_feature_flag) |

---

# Post-S8 — Phase 1 Domain Catalog + Registry Hints

**Init:** `_startup_tier1()` L2160
**Config gate:** `enable_fabric_stores` + GPS present.

- `_load_phase1_catalog_and_verifier()` — loads domain catalog into GPS, wires `VerificationPlanRunner`
- `_build_registry_hints(gps)` — snapshots live domains + resource_families from GPS for Back prompt injection

---

# MemoryWriterService

**File:** `k1/memory_writer/service.py`
**Init:** Background service started per-session at P5.
**Lifecycle:** Per-session. Processes turn completions into memory atoms, submits batches to K0 via bridge.

| Adapter | Purpose |
|---------|---------|
| `SessionReadAdapter` | Reads SS sections for context building |
| `ModelHubAdapter` | LLM calls for memory summarization (gemini-3.5-flash, background priority) |
| `BridgeCommandAdapter` | Submits memory batches to K0 via bridge command port |
| `FabricBusAdapter` | Bus integration |
| `EventSubscriptionAdapter` | Subscribes to turn completion events |
| `HealthAdapter` + `MWCircuitBreaker` | Health monitoring and circuit breaking |
| `SessionBatchDispatcher` | Batches atoms, threshold=20 turns or idle=300s |

---

# SectionUpdateBackgroundWorker

**File:** `k1/concierge/section_update/worker.py`
**Init:** Per-session at P5.5.
**Config gate:** `K1_ENABLE_SECTION_UPDATE_WORKER=true`, `enable_section_update_worker=True`
**Lifecycle:** Per-session background worker. Classifies turn completions and applies deltas in background.

| Component | Purpose |
|-----------|---------|
| `LLMSectionUpdateClassifier` | LLM-powered classification (gemini-2.5-flash-lite, timeout 75s) |
| `DeterministicSectionUpdateClassifier` | Rule-based fallback |
| `SectionUpdateBackgroundWorker` | Queue-based async worker (max 128 queue depth) |

---

# TIER 2 — Per-Session Components (P1→P5.5)

Built for each `create_session()` call. Destroyed in reverse order (`destroy_session()`).

---

# P1 — Per-Session Bus + Mailboxes

**Init:** `_create_session_tier2()` L2658

| Component | Purpose |
|-----------|---------|
| `BridgeAwareLocalBus` | Session-scoped ordered pub/sub bus with bridge contract validation |
| `IMailboxRouter` | Session-scoped mailbox registry |
| `ACTOR_FRONT` mailbox | Front LLM message routing |
| `ACTOR_BACK` mailbox | Back LLM message routing |

---

# P1.5 — Per-Session HumanInTheLoopService

**Init:** `_create_session_tier2()` L2692
**Config gate:** `enable_hil_service`
**Lifecycle:** Session-scoped HIL bound to `session_bus`. Separate from kernel-level HIL (S2.5). Kernel HIL serves Orchestrator/Planner; session HIL serves Concierge FSM + per-session Fabric.

---

# P2 — SessionStateManager

**File:** `k1/sessionstate/factory.py` → `SessionStateFactory.create_with_ports()`
**Init:** `_create_session_tier2()` L2718

| Adapter | Purpose |
|---------|---------|
| `SQLiteStorageAdapter` | Persistent SS storage at `data/k1/sessionstate.db` |
| `LocalEventAdapter` | In-process event capture |
| `DirectWriterAdapter` | Direct section writes (writer_id=direct) |
| `StandaloneLifecycle` | Checkpoint timer (30s interval) |
| `AsyncSSMBridge` | Async wrapper for sync SSM operations |

**SS Tiers:**

- **Hot (14 sections):** 52KB budget — beliefs, clarifications, narrative, scoreboard, persona, grounding, temporal, spatial, control, meta, affective_now, trust_level, active_intents
- **Warm (6 sections):** 48KB budget — artifacts, task_state, task_artifacts, history_recent, telemetry
- **Cold:** SQLite archive — beliefs_history, history_archive, narrative_archive, persona_archive, telemetry_archive, artifacts_archive

**Internal components:**

- `SizeTracker` — 20 sections tracked
- `MutationGuard` — preflight validation, emergency mode
- `EvictionEngine` — target 70% utilization
- `MigrationEngine` — hot↔warm pairs (beliefs_active↔beliefs_history, history_active↔history_recent)
- `LocalColdArchive` — 7 archive tables

---

# P3 — Per-Session Fabric

**File:** `k1/fabric/factory.py` → `FabricFactory.create_with_ports()`
**Init:** `_create_session_tier2()` L2755

| Adapter | Purpose |
|---------|---------|
| `SessionStateReaderAdapter(ssm, session_id)` | Per-session SS reads for context building |
| `EventPortProdAdapter(session_bus)` | Session-scoped event emission |
| `DeltaBusProdAdapter(session_bus)` | Session-scoped delta propagation |
| `ModelGatewayBridgeAdapter(hub)` | LLM calls via shared ModelHub |
| `PromptSystemProdAdapter` | Activity profile prompt templates |
| `BridgeConnectionAdapter(client)` | Bridge client |
| Shared `GlobalProjectionStore` | GPS (shared, read-only from session perspective) |
| `LocalProjectionStore(":memory:")` | LPS — per-session connected_resources, household members |

**Phase 1 wiring (factory step 21):**

- `ConstitutionLoader(gps)`
- `ConnectorResolver(gps)` — MiniLM-L6 dense retrieval
- `CapabilityBinderService(gps)`
- `ResolveSituationService(gps, local_store, ...)` — single-pass resolver

**P3.1 re-registration:** `NativeToolProvider` from shared FamilyToolsBundle re-registered on per-session Fabric so `invoke_capability` resolves to actual tool implementations.

---

# P3.5 — SelfModelHandle

**File:** `k1/selfmodel/kernel/bootstrap.py` → `build_self_model_handle()`
**Init:** `_create_session_tier2()` L2835
**Config gate:** `enable_self_model` + bundle built at S2.6
**Lifecycle:** Per-session handle referencing shared bundle. Installed into session before Concierge (P4).

| Component | Purpose |
|-----------|---------|
| `FabricRiskCatalog` | Built from Fabric registry + session bus, injected into handle |
| Capsule renderer | Grounding capsule + self-model projection rendering |
| Risk gate | Installed on Concierge dispatchers |

---

# P3.6 — TemporalHandle

**File:** `k1/temporal/kernel/bootstrap.py` → `build_temporal_handle()`
**Init:** `_create_session_tier2()` L2857
**Config gate:** `enable_temporal` + bundle built at S2.7
**Lifecycle:** Per-session. Installs temporal sections into SS, refreshes each turn.

---

# P3.7 — SpatialHandle

**File:** `k1/spatial/kernel/bootstrap.py` → `build_spatial_handle()`
**Init:** `_create_session_tier2()` L2876
**Config gate:** `enable_spatial` + bundle built at S2.8
**Lifecycle:** Per-session. Installs spatial sections into SS.

---

# P3.8 — GroundingHandle

**File:** `k1/grounding/kernel/bootstrap.py` → `build_grounding_handle()`
**Init:** `_create_session_tier2()` L2914
**Config gate:** `enable_grounding` + bundle built at S2.9
**Lifecycle:** Per-session. Injects temporal/spatial/identity/state surfaces into Fabric context builder. Refreshes each turn.

---

# P4 — ConciergeRuntime

**File:** `k1/concierge/factory.py` → `ConciergeFactory.create_with_ports()`
**Init:** `_create_session_tier2()` L3005

| Port | Adapter | Purpose |
|------|---------|---------|
| `delta` | `session_bus` | Delta/state-change propagation |
| `input_` | `BusInputAdapter` | User input from bus |
| `output` | `BusOutputAdapter` | Response output to bus |
| `state` | `SSMStateAdapter` | SessionState reads/writes |
| `llm` | `ModelHub` (shared) | LLM calls for Front + Back |
| `dispatch` | `FabricDispatchAdapter` | Capability dispatch via Fabric + Orchestrator |
| `temporal` | `TemporalHandle` | Time/date grounding |
| `spatial` | `SpatialHandle` | Location grounding |
| `grounding` | `GroundingHandle` | Full grounding context |
| `registry_hints` | dict | Live GPS registry snapshot for Back prompt |
| `memory` | `RecallMemoryAdapter` | K0 recall via bridge contract |
| `writer` | `DirectWriterAdapter` | SS writes |
| HIL port | `HumanInTheLoopService` | Session-scoped HIL |

**Internal components:**

| Component | Purpose |
|-----------|---------|
| `ConciergeController` (FSM) | 11-state FSM — LISTENING→DISPATCHING→COMPANIONING→... 19 handlers wired |
| `FrontLock` | Serializes Front LLM calls (max_queue_depth=8) |
| `CancellationHandler` | Task cancellation tokens |
| `SuspensionManager` | HIL suspension tracking |
| `ControlExtension` | FSM state extension |
| `TaskBridge` | TaskState + TaskArtifacts bridging |
| `InterruptClassifier` | 9 cancel keywords |
| `ConversationArbiter` | Domain/entity arbitration (domain_thresh=0.70, entity_thresh=0.50) |
| `ProactiveWakeHandler` | Proactive task result delivery |
| `LedgerWriter` | Conversation event ledger |
| `OppPipeline` | 8-stage pipeline (paced_delivery, recency_decay, affect_hard_caps, episodic_compression, dynamic_identity, ...) |
| `EpisodicCompressor` | 10-turn recent window, 5-episode compression |
| `DynamicIdentityContext` | Role-based identity injection |
| `ExperienceLayer` | 6 components: EP, AM, NW, AR, PA, RC |
| `DeltaApplicator` + `DeltaAggregator` | Batch delta writes (100ms window) |
| `WeaveBatcher` | Proactive weave batching (500ms window, max 16 depth) |
| `FrontDispatcher` | 10-tool allowlist (Front LLM tools) |
| `BackDispatcher` | 5-tool allowlist (resolve_situation, recall_memory, invoke_capability, batch_invoke_capabilities, submit_result) |

---

# P5 — MemoryWriter

**File:** `k1/memory_writer/factory.py` → `MemoryWriterFactory.create()`
**Init:** `_create_session_tier2()` L3055
**Lifecycle:** Per-session. Processes turn completions into memory atoms.

See [MemoryWriterService](#memorywriterservice) above for adapter details.

---

# P5.5 — SectionUpdateBackgroundWorker

**File:** `k1/concierge/section_update/worker.py`
**Init:** `_create_session_tier2()` (after P5)
**Config gate:** `enable_section_update_worker`
**Lifecycle:** Per-session background worker. Auto-wires `LLMSectionUpdateClassifier` when no external classifier provided.

See [SectionUpdateBackgroundWorker](#sectionupdatebackgroundworker) above for details.

---

# Shutdown Order (reverse)

```
P5.5 → P5 → P4 → P1.5 → P3.8 → P3.7 → P3.6 → P3.5 → P3 → P2 → P1
  → S8 → S7 → S6b → S5 → S3 → S2.10 → S4 → S2.9 → S2.8 → S2.7 → S2.6 → S2.5 → S2 → S1
```

---

# Config Flags Summary

| Flag | Env Var | Default | Controls |
|------|---------|---------|----------|
| `model_mode` | — | `"hub"` | `"hub"` = Vertex, `"test"` = stub |
| `enable_hil_service` | — | True | HumanInTheLoopService |
| `enable_self_model` | — | True | SelfModel bundle + handles |
| `enable_temporal` | `K1_ENABLE_TEMPORAL` | False | Temporal grounding |
| `enable_spatial` | — | False | Spatial grounding |
| `enable_grounding` | `K1_ENABLE_GROUNDING` | False | Full grounding bundle |
| `enable_fabric_stores` | — | True | GPS + IdempotencyStores |
| `enable_family_tools` | — | True | 6 FamilyOS adapters |
| `enable_section_update_worker` | `K1_ENABLE_SECTION_UPDATE_WORKER` | False | Background SS updates |
| `bridge_enabled` | — | True | SinkBridgeAdapter (offline outbox) |
| `k0_endpoint` | — | None | Live K0 bridge endpoint |
| `module_loader_watch` | — | False | Hot-reload contract watcher |
