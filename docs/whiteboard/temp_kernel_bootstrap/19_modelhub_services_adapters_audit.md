# ModelHub Services & Adapters — Full Audit Report

**Date:** 2026-04-14
**Scope:** `k1/model_hub/services/` (12 files) + `k1/model_hub/adapters/` (9 files)

---

## PART 1: SERVICES (12 files)

---

### 1. `services/model_selector.py` — Multi-Dimension Weighted Scoring [F42]

**Cross-module imports:**
- `k1.model_hub.manifest.ModelSpec`
- `k1.model_hub.services.capability_router.EligibleProvider`
- `k1.model_hub.types`: `CapabilityType`, `HealthStatus`, `HubRequest`, `ModelPreference`, `ModelTier`, `PlacementType`, `Priority`

**Dataclasses:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `ModelChoice` | `provider_id: str`, `model_id: str`, `fallback_chain: List[FallbackEntry]`, `score: float = 0.0` | Yes |
| `FallbackEntry` | `provider_id: str`, `model_id: str`, `score: float = 0.0` | Yes |

- `ModelChoice.__post_init__` validates `provider_id` is non-empty.

**Constants:**

| Name | Value | Purpose |
|------|-------|---------|
| `_PRIORITY_WEIGHTS[REALTIME]` | cost=0.1, latency=0.5, pref=0.2, placement=0.0, health=0.2 | Latency-dominated |
| `_PRIORITY_WEIGHTS[INTERACTIVE]` | cost=0.2, latency=0.3, pref=0.3, placement=0.0, health=0.2 | Balanced |
| `_PRIORITY_WEIGHTS[BACKGROUND]` | cost=0.5, latency=0.1, pref=0.1, placement=0.0, health=0.3 | Cost-dominated |
| `_TIER_LATENCY_SCORES` | FAST=1.0, STANDARD=0.6, PREMIUM=0.3 | Faster = higher |
| `_PLACEMENT_SCORES` | LOCAL_GPU=1.0, LOCAL_CPU=0.7, REMOTE=0.4 | Local > remote (MH-13) |
| `_HEALTH_SCORES` | HEALTHY=1.0, DEGRADED=0.5, UNHEALTHY=0.0 | |
| `_MAX_FALLBACK_DEPTH` | 3 | MH-06 |

**Class `ModelSelector`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(*, budget_usage_pct: float = 0.0)` | — | Stores `_budget_usage_pct` |
| `budget_usage_pct` (property) | — | `float` | Getter |
| `budget_usage_pct` (setter) | `(value: float)` | — | Setter (updated by BudgetEnforcer) |
| `select` | `(eligible_providers: List[EligibleProvider], request: HubRequest, *, preference: Optional[ModelPreference] = None)` | `Optional[ModelChoice]` | Score all → apply cost rules → sort desc → build primary + fallback top-3 |
| `_score_all_candidates` | `(eligible_providers, priority, capability, preference)` | `List[tuple]` | Returns `(provider_id, model_id, score, total_cost)` tuples |
| `_score_candidate` | `(ep, model, weights, preference, max_cost)` | `float` | 5-dimension weighted sum |
| `_score_provider_only` | `(ep, weights, preference)` | `float` | Neutral 0.5 for cost/latency |
| `_compute_preference_score` | `(provider_id, model_id, preference)` (static) | `float` | +0.3 preferred provider, +0.2 preferred model, 0.0 if avoided |
| `_apply_cost_rules` | `(candidates, priority, capability)` | `List[tuple]` | Force cheapest: budget>95% ALL, budget>80% non-REALTIME, BACKGROUND always |

**5-Dimension Scoring Algorithm:**
1. **cost_score** = `1.0 - (total_cost / max_cost)` — cheaper = higher, normalized 0–1
2. **latency_score** = tier lookup (FAST=1.0, STANDARD=0.6, PREMIUM=0.3)
3. **preference_score** = base 0.5 + 0.3 (preferred provider) + 0.2 (preferred model), 0.0 if avoided
4. **placement_score** = LOCAL_GPU=1.0, LOCAL_CPU=0.7, REMOTE=0.4
5. **health_score** = HEALTHY=1.0, DEGRADED=0.5, UNHEALTHY=0.0

**Final score** = Σ(weight_i × dimension_i) using priority-specific weights.

**Cost Optimization Rules:**
- Budget > 95%: cheapest model for ALL priorities
- Budget > 80%: cheapest model for non-REALTIME
- BACKGROUND priority: always cheapest model
- When forced cheapest: cheapest candidate gets `best_score + 0.1` to guarantee top

---

### 2. `services/provider_registry.py` — Provider Registration & Capability Index [F43]

**Cross-module imports:**
- `k1.model_hub.config.ModelHubConfig`
- `k1.model_hub.manifest`: `ModelSpec`, `ProviderManifest`
- `k1.model_hub.plugins.base.IProviderPlugin`
- `k1.model_hub.types`: `CapabilityType`, `HealthStatus`, `PlacementType`

**Dataclasses:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `ProviderInfo` | `provider_id: str`, `capabilities: List[CapabilityType]`, `models: List[ModelSpec]`, `placement_type: PlacementType = REMOTE`, `health_status: HealthStatus = HEALTHY` | Yes |

- `ProviderInfo.__post_init__` validates `provider_id` non-empty.

**Class `ProviderRegistry`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(config: ModelHubConfig)` | — | Inits `_plugins`, `_manifests`, `_provider_info`, `_capability_index` dicts |
| `register` | `(manifest: ProviderManifest, plugin: IProviderPlugin)` | `None` | Builds ProviderInfo from manifest, updates capability index. Raises ValueError on duplicate |
| `unregister` | `(provider_id: str)` | `None` | Removes all state. Raises KeyError if not found |
| `get_plugin` | `(provider_id: str)` | `IProviderPlugin` | Raises KeyError |
| `get_manifest` | `(provider_id: str)` | `ProviderManifest` | Raises KeyError |
| `get_provider_info` | `(provider_id: str)` | `ProviderInfo` | Raises KeyError |
| `list_providers` | `()` | `List[ProviderInfo]` | All registered |
| `get_capability_index` | `()` | `Dict[CapabilityType, List[ProviderInfo]]` | O(1) capability lookup |
| `get_providers_for_capability` | `(capability: CapabilityType)` | `List[ProviderInfo]` | Empty if none |
| `is_registered` | `(provider_id: str)` | `bool` | |
| `provider_count` (property) | — | `int` | |
| `_rebuild_capability_index` | `()` | `None` | Union of manifest-level + model-level capabilities (MH-18) |

**Internal state:**
- `_plugins: Dict[str, IProviderPlugin]`
- `_manifests: Dict[str, ProviderManifest]`
- `_provider_info: Dict[str, ProviderInfo]`
- `_capability_index: Dict[CapabilityType, List[ProviderInfo]]`

**Invariants:** MH-17 (plugin isolation), MH-18 (manifest sole capability truth).

---

### 3. `services/provider_dispatcher.py` — Dispatch Pipeline with CB/RL/Fallback [F44]

**Cross-module imports:**
- `k1.model_hub.plugins.base`: `IProviderPlugin`, `NormalizedRequest`, `ProviderChunk`, `ProviderResponse`
- `k1.model_hub.ports.credential_port.ICredentialPort`
- `k1.model_hub.services.circuit_breaker_manager.CircuitBreakerManager`
- `k1.model_hub.services.rate_limiter.RateLimiter`
- `k1.model_hub.types`: `CircuitState`, `ProviderError`

**Dataclass:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `DispatchResult` | `response: ProviderResponse`, `provider_id: str`, `latency_ms: int`, `fallback_used: bool = False`, `attempts: List[str]` | Yes |

**Constants:** `_MAX_FALLBACK_DEPTH = 3`, `_MAX_RETRIES = 1`

**Class `ProviderDispatcher`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(*, circuit_mgr: CircuitBreakerManager, rate_limiter: RateLimiter, credential_port: ICredentialPort, plugins: Optional[Dict[str, IProviderPlugin]] = None)` | — | |
| `register_plugin` | `(provider_id: str, plugin: IProviderPlugin)` | `None` | |
| `has_plugin` | `(provider_id: str)` | `bool` | |
| `dispatch` | `(request: NormalizedRequest, provider_id: str, *, fallback_chain: Optional[List[str]] = None, token_estimate: int = 1)` | `DispatchResult` | async. Tries primary + fallback (max 4 total). Raises CircuitOpenError/RateLimitError/ProviderError |
| `stream` | `(request: NormalizedRequest, provider_id: str, *, fallback_chain: Optional[List[str]] = None, token_estimate: int = 1)` | `AsyncIterator[ProviderChunk]` | async generator. Same fallback logic |
| `_try_provider` | `(request: NormalizedRequest, provider_id: str, *, token_estimate: int = 1)` | `Optional[tuple[ProviderResponse, int]]` | async. 1. CB acquire → 2. RL acquire → 3. plugin.execute() with 1 retry → records success/failure |

**Pipeline per attempt:**
1. Acquire circuit breaker (reject if OPEN)
2. Acquire rate limiter (reject if exhausted)
3. Get credential via `ICredentialPort` (MH-02) — *referenced in docstring, credential_port injected but actual get_key call not shown in try_provider*
4. Call `plugin.execute(request)`
5. Record success/failure for circuit breaker
6. On failure: retry once, then next fallback (MH-06)

**Plugin isolation (MH-17):** Bare `except Exception` catches all plugin crashes.

---

### 4. `services/request_router.py` — THE Single Entry Point [F40]

**Cross-module imports:**
- `k1.model_hub.plugins.base.NormalizedRequest`
- `k1.model_hub.services.*`: `AuditLogger`, `BudgetEnforcer`, `CapabilityRouter`, `CostTracker`, `ModelSelector`, `NormalizationLayer`, `ProviderDispatcher`, `ResponseCache`
- `k1.model_hub.types`: `BudgetDecision`, `BudgetExceededError`, `CapabilityType`, `HubChunk`, `HubRequest`, `HubResponse`, `NoEligibleProviderError`, `ResponseMetadata`, `TokenUsage`, `ValidationError`

**Protocol:**

| Protocol | Method | Signature |
|----------|--------|-----------|
| `_MetricsEmitter` | `emit` | `(metric_name: str, value: float, labels: dict[str, Any] \| None = None) -> None` |

**Class `RequestRouter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(*, capability_router, model_selector, budget_enforcer, response_cache, normalization_layer, dispatcher, cost_tracker=None, audit_logger=None, metrics_port=None)` | — | All services injected. Tracks `_active_requests` gauge |
| `route` | `(request: HubRequest)` | `HubResponse` | async. 9-step pipeline. Emits metrics for active_requests, requests_total, latency_ms, errors |
| `_route_inner` | `(request, std_labels)` | `HubResponse` | async. Steps 2–9 |
| `stream_route` | `(request: HubRequest)` | `AsyncIterator[HubChunk]` | async generator. Steps 1–7 same, Step 8 via dispatcher.stream() |
| `_emit` | `(metric_name, value, labels)` | `None` | Fire-and-forget via `_MetricsEmitter` |
| `_validate` | `(request: HubRequest)` (static) | `None` | Validates capability is CapabilityType, raises ValidationError |

**9-Step Pipeline:**
1. **Validate** — schema, trace_id (MH-03)
2. **Budget check** — `budget_enforcer.check()` → REJECT raises `BudgetExceededError` (MH-04)
3. **Priority → timeout** — already in constraints
4. **CapabilityRouter** → eligible providers
5. **ModelSelector** → provider + model + fallback chain (budget_usage_pct synced)
6. **Cache check** — `response_cache.should_cache()` + `get()` (MH-09)
7. **NormalizationLayer** → `NormalizedRequest` (with model_id from choice)
8. **ProviderDispatcher** → `dispatch()` or `stream()`
9. **Post-process** — denormalize, budget track, cache put, audit log, metrics (tokens_used, cost_usd, budget_pct, provider_latency_ms, fallbacks_total)

**Metrics emitted:** `model_hub.active_requests`, `model_hub.requests_total`, `model_hub.latency_ms`, `model_hub.budget_rejections_total`, `model_hub.errors_total`, `model_hub.cache_hits_total`, `model_hub.provider_latency_ms`, `model_hub.fallbacks_total`, `model_hub.tokens_used`, `model_hub.cost_usd`, `model_hub.budget_pct`

---

### 5. `services/capability_router.py` — 5-Step Filtering Pipeline [F41]

**Cross-module imports:**
- `k1.model_hub.manifest.ModelSpec`
- `k1.model_hub.services.provider_registry`: `ProviderInfo`, `ProviderRegistry`
- `k1.model_hub.types`: `CapabilityType`, `CircuitState`, `HealthStatus`, `RequestConstraints`

**Protocols:**

| Protocol | Method | Signature |
|----------|--------|-----------|
| `ICircuitBreakerQuery` | `get_state` | `(provider_id: str) -> CircuitState` |
| `IRateLimiterQuery` | `has_capacity` | `(provider_id: str, token_estimate: int) -> bool` |
| `IHealthQuery` | `get_status` | `(provider_id: str) -> HealthStatus` |

**Dataclass:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `EligibleProvider` | `provider_info: ProviderInfo`, `eligible_models: List[ModelSpec]`, `circuit_state: CircuitState = CLOSED`, `health_status: HealthStatus = HEALTHY` | Yes |

**Class `CapabilityRouter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(registry: ProviderRegistry, circuit_breaker: ICircuitBreakerQuery, rate_limiter: IRateLimiterQuery, health_monitor: IHealthQuery)` | — | |
| `route` | `(capability: CapabilityType, constraints: RequestConstraints, *, token_estimate: int = 0)` | `List[EligibleProvider]` | 5-step filter pipeline |
| `_filter_models_by_capability` | `(models: List[ModelSpec], capability: CapabilityType)` (static) | `List[ModelSpec]` | Filter models with matching capability |

**5-Step Filtering Pipeline:**
1. **Capability lookup** in `ProviderRegistry` capability index (MH-18)
2. **Model-level filter** — models supporting the specific capability
3. **Circuit breaker filter** — skip if `CircuitState.OPEN`
4. **Rate limit filter** — skip if `has_capacity()` returns False
5. **Health filter** — skip if `HealthStatus.UNHEALTHY`

Returns empty list if no providers pass all 5 filters.

---

### 6. `services/circuit_breaker_manager.py` — Per-Provider State Machine [F48]

**Cross-module imports:**
- `k1.model_hub.manifest.CircuitBreakerConfig`
- `k1.model_hub.types.CircuitState`

**Dataclasses:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `_ProviderCircuit` | `state: CircuitState = CLOSED`, `config: CircuitBreakerConfig`, `failure_timestamps: List[float]`, `opened_at: float = 0.0`, `half_open_in_flight: bool = False` | No (mutable) |
| `CircuitTransition` | `provider_id: str`, `old_state: CircuitState`, `new_state: CircuitState`, `failure_count: int = 0`, `timestamp: float = 0.0` | Yes |

**Class `CircuitBreakerManager`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `()` | — | Inits `_circuits` dict, `_transitions` list |
| `register_provider` | `(provider_id: str, config: Optional[CircuitBreakerConfig] = None)` | `None` | No-op if already registered |
| `unregister_provider` | `(provider_id: str)` | `None` | `.pop()` |
| `get_state` | `(provider_id: str)` | `CircuitState` | Auto-transitions OPEN→HALF_OPEN on cooldown expiry. Returns CLOSED for unknown |
| `acquire` | `(provider_id: str)` | `CircuitState` | For HALF_OPEN: marks probe in-flight; if already in-flight returns OPEN |
| `record_success` | `(provider_id: str)` | `None` | HALF_OPEN → CLOSED (clears failures) |
| `record_failure` | `(provider_id: str, error: Optional[str] = None)` | `None` | CLOSED: adds timestamp, prunes window, checks threshold → OPEN. HALF_OPEN → OPEN |
| `transitions` (property) | — | `List[CircuitTransition]` | |
| `failure_count` | `(provider_id: str)` | `int` | Current count in sliding window |
| `is_registered` | `(provider_id: str)` | `bool` | |
| `_transition` | `(circuit, provider_id, new_state)` | `None` | Records transition |

**State machine (MH-05):**
- **CLOSED** → all requests pass. Failures counted in sliding window. If `failure_threshold` breached within `failure_window_s` → **OPEN**
- **OPEN** → all requests rejected. After `cooldown_s` elapsed → **HALF_OPEN**
- **HALF_OPEN** → single probe request. Success → **CLOSED** (reset). Failure → **OPEN** (restart cooldown)

**Default thresholds (from CircuitBreakerConfig):**
- `failure_threshold`: 3
- `failure_window_s`: 60
- `cooldown_s`: 30

---

### 7. `services/rate_limiter.py` — Per-Provider Token Bucket [F49]

**Cross-module imports:**
- `k1.model_hub.manifest.RateLimitConfig` (referenced in docstring, not directly imported)

**Dataclasses:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `RateDecision` | `allowed: bool`, `provider_id: str`, `tokens_remaining: int = 0`, `requests_remaining: int = 0`, `retry_after_s: float = 0.0` | Yes |
| `_ProviderRate` | `rpm_bucket: _TokenBucket`, `tpm_bucket: _TokenBucket`, `headroom_pct: float = 0.80` | No (mutable) |

**Class `_TokenBucket`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(capacity: int, refill_rate: float)` | — | Starts full |
| `_refill` | `()` | `None` | Adds elapsed × refill_rate, capped at capacity |
| `try_consume` | `(amount: int = 1)` | `bool` | Refills, consumes if available |
| `available` (property) | — | `int` | |
| `capacity` (property) | — | `int` | |
| `retry_after` | `(amount: int = 1)` | `float` | Seconds until amount available |

**Class `RateLimiter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(*, default_headroom_pct: float = 0.80)` | — | |
| `register_provider` | `(provider_id: str, rpm: int = 60, tpm: int = 100000, headroom_pct: Optional[float] = None)` | `None` | Effective limits = limit × headroom |
| `unregister_provider` | `(provider_id: str)` | `None` | |
| `has_capacity` | `(provider_id: str, token_estimate: int)` | `bool` | IRateLimiterQuery protocol. True for unknown providers |
| `acquire` | `(provider_id: str, token_estimate: int = 1)` | `RateDecision` | Atomic: both RPM+TPM must succeed or neither consumed. Returns retry_after on denial |
| `is_registered` | `(provider_id: str)` | `bool` | |
| `get_remaining` | `(provider_id: str)` | `tuple[int, int]` | (requests_remaining, tokens_remaining) |

**Key mechanics:**
- Two token buckets per provider: RPM (requests/minute) and TPM (tokens/minute)
- **Headroom**: only `headroom_pct` (default 80%) of capacity usable (MH-12)
- Effective RPM = `rpm × headroom_pct`, refill rate = effective_rpm / 60 tokens/sec
- `acquire()` checks both buckets atomically — both must pass or neither consumed

---

### 8. `services/budget_enforcer.py` — Daily Budget Enforcement [F46]

**Cross-module imports:**
- `k1.model_hub.config.ModelHubConfig`
- `k1.model_hub.types`: `BudgetDecision`, `HubRequest`, `HubResponse`

**Dataclasses:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `BudgetCheckResult` | `decision: BudgetDecision`, `daily_spent_usd: float`, `daily_budget_usd: float`, `daily_remaining_usd: float`, `usage_pct: float`, `reason: str = ""` | Yes |
| `SpendingRecord` | `request_id: str`, `cost_usd: float`, `consumer_id: str = ""`, `capability: str = ""`, `provider_id: str = ""`, `model_id: str = ""` | Yes |

**Class `BudgetEnforcer`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(config: ModelHubConfig)` | — | Reads `config.daily_budget_usd` |
| `check` | `(request: HubRequest)` | `BudgetCheckResult` | 3-tier decision |
| `track` | `(response: HubResponse)` | `None` | Adds `response.metadata.cost_usd` to daily total |
| `reset_daily` | `()` | `None` | Resets spent + records |
| `daily_spent_usd` (property) | — | `float` | |
| `daily_budget_usd` (property) | — | `float` | |
| `usage_pct` (property) | — | `float` | 0–100 |
| `spending_records` (property) | — | `List[SpendingRecord]` | |

**Decision logic:**
1. `daily_spent >= daily_budget` → **REJECT** (MH-04)
2. `remaining < request.constraints.cost_limit` → **REJECT**
3. `usage_pct >= 80%` → **ALLOW_DEGRADED** (forces cheapest model)
4. Otherwise → **ALLOW**

**Default daily budget:** $5/day (MH-08, from ModelHubConfig).

---

### 9. `services/cost_tracker.py` — Per-Request Cost Computation [F50]

**Cross-module imports:**
- `k1.model_hub.manifest.ModelSpec`
- `k1.model_hub.types`: `CapabilityType`, `TokenUsage`

**Dataclass:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `CostRecord` | `cost_usd: float`, `input_cost_usd: float`, `output_cost_usd: float`, `model_id: str`, `provider_id: str`, `prompt_tokens: int`, `completion_tokens: int`, `capability: CapabilityType`, `consumer_id: str = ""` | Yes |

**Class `CostTracker`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `()` | — | Inits `_records`, `_by_consumer`, `_by_model`, `_by_capability` |
| `compute_cost` | `(usage: TokenUsage, model_spec: ModelSpec)` (static) | `tuple[float, float]` | `(input_cost, output_cost)` |
| `track` | `(usage, model_spec, *, provider_id, capability, consumer_id="")` | `CostRecord` | Computes + records + aggregates |
| `records` (property) | — | `List[CostRecord]` | |
| `total_cost_usd` (property) | — | `float` | |
| `by_consumer` (property) | — | `Dict[str, float]` | |
| `by_model` (property) | — | `Dict[str, float]` | |
| `by_capability` (property) | — | `Dict[str, float]` | |
| `reset` | `()` | `None` | Clears everything |

**Cost formula (MH-07):**
- `input_cost = prompt_tokens × cost_per_1m_input / 1,000,000`
- `output_cost = completion_tokens × cost_per_1m_output / 1,000,000`
- Cost tables from `ModelSpec` in provider manifest, never hardcoded.

---

### 10. `services/response_cache.py` — LRU Cache with Capability-Aware Keying [F47]

**Cross-module imports:**
- `k1.model_hub.config.ModelHubConfig`
- `k1.model_hub.types`: `CapabilityType`, `HubRequest`, `HubResponse`

**Dataclasses:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `_CacheEntry` | `response: HubResponse`, `created_at: float`, `ttl_s: int`, `cache_key: str`, `hit_count: int = 0` + properties `is_expired`, `age_ms` | No (mutable) |
| `CacheResult` | `hit: bool`, `response: Optional[HubResponse] = None`, `cache_key: str = ""`, `age_ms: int = 0` | Yes |

**Constants:**
- `_SKIP_CAPABILITIES`: `{TOOL_CALL, BATCH, MODERATE}` — never cached
- `_HIGH_TEMPERATURE_THRESHOLD`: 0.9

**Class `ResponseCache`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(config: ModelHubConfig)` | — | Reads `config.cache_max_entries`, `config.cache_ttl_s`. Uses `OrderedDict` + `threading.Lock` |
| `build_cache_key` | `(capability, payload, model_id="", temperature=0.7)` (static) | `str` | SHA-256 of `capability\|repr(payload)\|model_id\|temperature` |
| `should_cache` | `(request: HubRequest, *, streaming: bool = False)` (static) | `bool` | False for TOOL_CALL/BATCH/MODERATE, temp>0.9, streaming |
| `get` | `(cache_key: str)` | `CacheResult` | LRU move-to-end on hit, evicts expired |
| `put` | `(cache_key: str, response: HubResponse, ttl_s: Optional[int] = None)` | `None` | Evicts LRU if full |
| `invalidate` | `(cache_key: str)` | `bool` | |
| `clear` | `()` | `None` | |
| `size` (property) | — | `int` | |
| `max_entries` (property) | — | `int` | |
| `total_hits` (property) | — | `int` | |
| `total_misses` (property) | — | `int` | |
| `hit_rate` (property) | — | `float` | 0.0–1.0 |

**Cache rules (MH-09):**
- Key: `SHA256(capability + payload_repr + model_id + temperature)`
- TTL: 5 min default (from config)
- Eviction: LRU via OrderedDict
- Thread-safe: `threading.Lock` for put + eviction

---

### 11. `services/normalization_layer.py` — Bidirectional Request/Response Translation [F45]

**Cross-module imports:**
- `k1.model_hub.plugins.base`: `NormalizedRequest`, `ProviderResponse`
- `k1.model_hub.types`: `AudioInputPayload`, `BatchPayload`, `CachePromptPayload`, `CapabilityType`, `ChatPayload`, `CodeExecPayload`, `EmbedPayload`, `HubRequest`, `HubResponse`, `ImageGenPayload`, `Message`, `ModeratePayload`, `ReasonPayload`, `ResponseMetadata`, `StructuredOutputPayload`, `TokenCountPayload`, `TokenUsage`, `ToolCallPayload`, `TTSPayload`, `VisionPayload`, `WebSearchPayload`

**Capability Dispatch Table (`_CAPABILITY_EXTRACTORS`):**

| CapabilityType | Extractor | Extracts |
|----------------|-----------|----------|
| `CHAT` | `_extract_chat` | messages, system_prompt |
| `TOOL_CALL` | `_extract_tool_call` | messages, tools (name/desc/params), tool_choice |
| `STRUCTURED` | `_extract_structured` | messages, output_schema |
| `REASON` | `_extract_reason` | messages, reasoning_effort |
| `EMBED` | `_extract_embed` | messages (from texts), extra (encoding_format, dimensions) |
| `VISION` | `_extract_vision` | messages, extra (image_inputs, detail) |
| `BATCH` | `_extract_batch` | extra (requests, callback_topic) |
| `MODERATE` | `_extract_moderate` | messages (from text), extra (categories) |
| `TOKEN_COUNT` | `_extract_token_count` | messages, extra (target_model_id) |
| `CACHE_PROMPT` | `_extract_cache_prompt` | messages, extra (cache_key, ttl_s) |
| `AUDIO_IN` | `_extract_audio_in` | messages, extra (audio, voice_config) |
| `TTS` | `_extract_tts` | messages (from text), extra (voice, format, speed) |
| `IMAGE_GEN` | `_extract_image_gen` | messages (from prompt), extra (size, quality, n) |
| `WEB_SEARCH` | `_extract_web_search` | messages (from query), extra (max_results) |
| `CODE_EXEC` | `_extract_code_exec` | messages (from code), extra (language, timeout_s) |

**Class `NormalizationLayer`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `normalize` | `(request: HubRequest, target_provider_id: str)` | `NormalizedRequest` | Dispatches to capability extractor, builds NormalizedRequest with constraints |
| `denormalize` | `(response: ProviderResponse, original_request: HubRequest, *, provider_id="", latency_ms=0, cache_hit=False, cost_usd=0.0, fallback_used=False)` | `HubResponse` | Builds TokenUsage, ResponseMetadata, result |
| `_build_result` | `(response: ProviderResponse, capability: CapabilityType)` | `Any` | For TOOL_CALL: returns dict with text + tool_calls. Otherwise: returns text |

---

### 12. `services/audit_logger.py` — Full Audit Trail [F52]

**Cross-module imports:**
- `k1.model_hub.types`: `CapabilityType`, `HubRequest`, `HubResponse`

**Dataclass:**

| Class | Fields | Frozen |
|-------|--------|--------|
| `AuditRecord` | `request_id: str`, `trace_id: str`, `consumer_id: str`, `capability: CapabilityType`, `model_id: str`, `provider_id: str`, `prompt_tokens: int`, `completion_tokens: int`, `cost_usd: float`, `latency_ms: int`, `cache_hit: bool`, `fallback_used: bool = False`, `fallback_chain: List[str]`, `error: Optional[str] = None` | Yes |

**Class `AuditLogger`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `()` | — | Inits `_records: List[AuditRecord]` |
| `log` | `(request: HubRequest, response: HubResponse, *, fallback_chain: Optional[List[str]] = None)` | `AuditRecord` | Extracts metadata from response, builds record |
| `log_error` | `(request: HubRequest, error: str, *, fallback_chain: Optional[List[str]] = None)` | `AuditRecord` | Error record with zeroed metrics |
| `records` (property) | — | `List[AuditRecord]` | |
| `count` (property) | — | `int` | |
| `clear` | `()` | `None` | |

**Invariant MH-11:** Every call logged with full metadata (request_id, trace_id, consumer_id, capability, model_id, provider_id, tokens, cost, latency, cache_hit, fallback_chain).

---

## PART 2: ADAPTERS (9 files)

---

### 1. `adapters/session_state_read_adapter.py` — In-Memory SessionState Reader [F32]

**Cross-module imports:**
- `k1.model_hub.ports.state_read_port.StateSnapshot`

**Class `SessionStateReadAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(state_source: Dict[str, Any] \| None = None)` | — | In-memory dict |
| `read` | `(sections: List[str])` | `StateSnapshot` | async. Reads requested sections from dict. Returns empty StateSnapshot on any error |

**Design:** MH-01 enforced — NO write methods. Lock-free. Error → empty snapshot (degraded mode).

---

### 2. `adapters/session_state_prod.py` — Production SessionState Reader [E-0.5.10]

**Cross-module imports:**
- `k1.model_hub.ports.state_read_port.StateSnapshot`

**Class `SessionStateProdAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(manager: Any)` | — | `manager` is `SessionStateManager`, typed as `Any` to avoid import coupling |
| `read` | `(sections: List[str])` | `StateSnapshot` | async. Iterates sections, calls `_read_one()` for each |
| `_read_one` | `(name: str)` | `Optional[Dict[str, Any]]` | `manager.get_section(name)` → `_section_to_dict()`. Returns None on KeyError |
| `_section_to_dict` | `(section_obj: Any)` (static) | `Optional[Dict[str, Any]]` | Tries `to_dict()` → `get_metadata()` → isinstance dict → None |

**Design:**
- Uses `__slots__ = ("_manager",)` for memory efficiency
- MH-01 enforced — NO write methods
- `SectionNotFoundError` (KeyError subclass) → silently omitted
- Catastrophic error → empty StateSnapshot
- Reads `persona` and `control` sections from real SessionStateManager

---

### 3. `adapters/event_bus_adapter.py` — K1 Event Bus Pub/Sub [F31]

**Cross-module imports:**
- `k1.model_hub.ports.event_port.Subscription`

**Class `EventBusAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `()` | — | Inits `_handlers: dict[str, List[Callable]]`, `_subscriptions: List[Subscription]` |
| `publish` | `(topic: str, payload: Any)` | `None` | async. Iterates handlers for topic, calls each. Logs and swallows errors |
| `subscribe` | `(topics: List[str], handler: Callable[[str, Any], Awaitable[None]])` | `Subscription` | async. Registers handler for all topics. Returns `Subscription` with UUID |

**Design:** In-memory pub/sub for single-process. Production: delegates to K1 bus transport. Publishes all model_hub events with trace_id. Subscribes to config_update events for hot-reload.

---

### 4. `adapters/config_adapter.py` — YAML Config with Hot-Reload [F34]

**Cross-module imports:**
- `k1.model_hub.ports.config_port.ConfigSubscription`

**Class `ConfigAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(data: Dict[str, Any] \| None = None)` | — | In-memory dict + watcher registry |
| `get` | `(key: str)` | `Any` | Returns `_data.get(key)`. Returns None on error |
| `watch` | `(key: str, callback: Callable[[str, Any], None])` | `ConfigSubscription` | Registers watcher. Returns subscription with UUID |
| `reload` | `(data: Dict[str, Any])` | `None` | Replaces config, notifies watchers of changed keys |

**Design:** Production reads from `k1/config/model_hub.yaml` + `MH_*` env overrides. Supports hot-reload with watcher callbacks for changed keys.

---

### 5. `adapters/credential_store_adapter.py` — Encrypted Credential Store [F35]

**Cross-module imports:** None (stdlib only — `os`)

**Class `CredentialStoreAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(key_overrides: Dict[str, str] \| None = None)` | — | Optional override dict |
| `get_key` | `(provider_id: str)` | `str` | async. Lookup: overrides dict → env `MH_KEY_<PROVIDER_ID>` → empty string |
| `refresh_key` | `(provider_id: str)` | `str` | async. Same as get_key (no rotation yet) |

**Design:** MH-02: ALL API keys in CredentialStore, never in config/env/manifest. Current impl reads from env vars `MH_KEY_<PROVIDER_ID>`. Production: OS keychain / Vault / encrypted store (AES256-GCM at rest). Error → empty string.

---

### 6. `adapters/health_report_adapter.py` — Fabric Health Reporting [F36]

**Cross-module imports:**
- `k1.model_hub.ports.health_port.HealthReport`
- `k1.model_hub.types.HealthStatus`

**Class `HealthReportAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(component: str = "model_hub")` | — | Inits component name + status dict |
| `report_health` | `(component: str, status: HealthStatus)` | `None` | Stores status for sub-component |
| `check_health` | `()` | `HealthReport` | Aggregates: any UNHEALTHY → UNHEALTHY, any DEGRADED → DEGRADED, else HEALTHY |

**Design:** Production publishes health to Fabric health-check endpoint. Current: in-memory status tracking. Aggregation: worst-of across all sub-components. Error → UNHEALTHY.

---

### 7. `adapters/llm_request_bus_adapter.py` — LLM Request Bus Binding [F30]

**Cross-module imports:**
- `k1.model_hub.ports.hub_port.IModelHubPort`
- `k1.model_hub.types`: `CapabilityType`, `HealthStatus`, `HubChunk`, `HubHealthReport`, `HubRequest`, `HubResponse`, `ModelInfo`

**Class `LLMRequestBusAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(inner: IModelHubPort)` | — | Wraps inner port (RequestRouter facade) |
| `execute` | `(request: HubRequest)` | `HubResponse` | async. Delegates to `inner.execute()`. Logs and re-raises on error |
| `stream_execute` | `(request: HubRequest)` | `AsyncIterator[HubChunk]` | async generator. Delegates to `inner.stream_execute()` |
| `discover_capabilities` | `()` | `Dict[CapabilityType, List[str]]` | async. Delegates |
| `discover_models` | `(capability: Optional[CapabilityType] = None)` | `List[ModelInfo]` | async. Delegates |
| `health` | `()` | `HubHealthReport` | async. Delegates. Error → UNHEALTHY |

**Design:** Decorator/facade pattern. Receives HubRequest from K1 LLM Request Bus, delegates to inner IModelHubPort (RequestRouter). Returns HubResponse via bus reply channel. All methods are passthrough with error logging.

---

### 8. `adapters/prometheus_adapter.py` — Prometheus Metrics [F33]

**Cross-module imports:** None (stdlib only)

**Class `PrometheusAdapter`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `()` | — | Inits `_counters: Dict[str, float]` |
| `emit` | `(metric_name: str, value: float, labels: Dict[str, Any] \| None = None)` | `None` | Accumulates by `metric_name{label_key=value,...}`. Fire-and-forget, logs errors |

**Design:** Production: delegates to `prometheus_client` library. Current: in-memory accumulator. Labels: provider, model, consumer, capability, priority. Conforms to `_MetricsEmitter` protocol in RequestRouter.

---

### 9. `adapters/bus_envelope_deserializer.py` — Bus→ModelHub Transport Bridge [E-0.5.9]

**Cross-module imports:**
- `k1.bus.envelope`: `Envelope`, `PayloadFormat` ← **EXTERNAL MODULE (k1.bus)**
- `k1.bus.ports.bus`: `IBus`, `SubscriptionHandle` ← **EXTERNAL MODULE (k1.bus)**
- `k1.model_hub.adapters.llm_request_bus_adapter.LLMRequestBusAdapter`
- `k1.model_hub.types`: `CapabilityType`, `ChatPayload`, `HubRequest`, `HubResponse`, `Message`, `RequestConstraints`, `ToolCallPayload`, `Priority`

**Module-level constants:**
- `TOPIC_HUB_EXECUTE = "k1.model_hub.execute.v1"` — inbound topic
- `TOPIC_HUB_RESPONSE = "k1.model_hub.execute.response.v1"` — outbound topic

**Payload builders (`_PAYLOAD_BUILDERS`):**

| CapabilityType | Builder Logic |
|----------------|---------------|
| `CHAT` | `ChatPayload(messages=[Message(**m) for m in data["messages"]], system_prompt=data.get("system_prompt"))` |
| `TOOL_CALL` | `ToolCallPayload(messages=..., tools=..., tool_choice=..., parallel_tool_calls=...)` |
| Other | Raw dict passthrough |

**Module-level functions:**

| Function | Signature | Returns | Logic |
|----------|-----------|---------|-------|
| `_build_payload` | `(capability: CapabilityType, raw: Dict[str, Any])` | `Any` | Dispatches to registered builder or returns raw dict |
| `_build_constraints` | `(raw: Optional[Dict[str, Any]])` | `RequestConstraints` | Parses priority string → enum, defaults: max_tokens=65536, timeout_ms=30000, temperature=0.7 |
| `deserialize_hub_request` | `(data: Dict[str, Any])` | `HubRequest` | Full deserialization: capability → enum, payload → typed, constraints → typed |
| `serialize_hub_response` | `(response: HubResponse)` | `bytes` | `json.dumps(asdict(response))` with enum value coercion |

**Class `BusEnvelopeDeserializer`:**

| Method | Signature | Returns | Logic |
|--------|-----------|---------|-------|
| `__init__` | `(bus: IBus, adapter: LLMRequestBusAdapter, loop: Optional[asyncio.AbstractEventLoop] = None)` | — | Subscribes to `TOPIC_HUB_EXECUTE` |
| `_on_envelope` | `(envelope: Envelope)` | `None` | Sync bus handler. Rejects non-JSON payloads. Deserializes → HubRequest. Schedules async dispatch via `run_coroutine_threadsafe` |
| `_dispatch` | `(request: HubRequest, source_envelope: Envelope)` | `None` | async. Calls `adapter.execute()`, serializes response, publishes to `TOPIC_HUB_RESPONSE` as new Envelope |
| `_on_dispatch_done` | `(future: asyncio.Future)` (static) | `None` | Logs unhandled dispatch errors |
| `close` | `()` | `None` | Unsubscribes from bus |
| `is_subscribed` (property) | — | `bool` | |

**Response envelope construction:**
```python
Envelope(
    topic=TOPIC_HUB_RESPONSE,
    priority=source_envelope.priority,
    cognitive_trace_id=request.trace_id,
    session_id=source_envelope.session_id,
    request_id=request.request_id,
    parent_id=source_envelope.envelope_id,
    payload=response_payload,  # JSON bytes
    payload_format=PayloadFormat.JSON,
)
```

**Design:**
- IBus handlers are synchronous → async execute scheduled via `asyncio.run_coroutine_threadsafe`
- Only `PayloadFormat.JSON` (hint=1) accepted; OPAQUE/MSGPACK dropped with log
- Malformed payloads never crash the bus
- This is the **only adapter that imports from k1.bus** (external module boundary)

---

## PART 3: CROSS-CUTTING OBSERVATIONS

### Import Boundary Summary

| Adapter | External Modules Referenced |
|---------|---------------------------|
| `bus_envelope_deserializer` | `k1.bus.envelope`, `k1.bus.ports.bus` |
| `session_state_prod` | `SessionStateManager` (injected as `Any`, no import) |
| `llm_request_bus_adapter` | `k1.model_hub.ports.hub_port.IModelHubPort` |
| All others | Only `k1.model_hub.ports.*`, `k1.model_hub.types`, stdlib |

### Service Dependency Graph (constructor injection)

```
RequestRouter
  ├── CapabilityRouter
  │     ├── ProviderRegistry (config: ModelHubConfig)
  │     ├── ICircuitBreakerQuery (= CircuitBreakerManager)
  │     ├── IRateLimiterQuery (= RateLimiter)
  │     └── IHealthQuery
  ├── ModelSelector (budget_usage_pct: float)
  ├── BudgetEnforcer (config: ModelHubConfig)
  ├── ResponseCache (config: ModelHubConfig)
  ├── NormalizationLayer ()
  ├── ProviderDispatcher
  │     ├── CircuitBreakerManager ()
  │     ├── RateLimiter (default_headroom_pct=0.80)
  │     └── ICredentialPort (= CredentialStoreAdapter)
  ├── CostTracker ()  [optional]
  ├── AuditLogger ()  [optional]
  └── _MetricsEmitter  [optional] (= PrometheusAdapter)
```

### Adapter → Port Mappings

| Adapter | Implements Port |
|---------|----------------|
| `SessionStateReadAdapter` | `IStateReadPort` (implied) |
| `SessionStateProdAdapter` | `IStateReadPort` (implied) |
| `EventBusAdapter` | `IEventPort` (implied) |
| `ConfigAdapter` | `IConfigPort` (implied) |
| `CredentialStoreAdapter` | `ICredentialPort` (implied) |
| `HealthReportAdapter` | `IHealthPort` (implied) |
| `LLMRequestBusAdapter` | `IModelHubPort` (explicit import) |
| `PrometheusAdapter` | `IMetricsPort` / `_MetricsEmitter` (implied) |
| `BusEnvelopeDeserializer` | Bridges `IBus` → `LLMRequestBusAdapter` |

### Invariant Reference Index

| ID | Rule | Enforced In |
|----|------|-------------|
| MH-01 | Never write SessionState | `SessionStateReadAdapter`, `SessionStateProdAdapter` |
| MH-02 | Credentials from CredentialStore only | `ProviderDispatcher`, `CredentialStoreAdapter` |
| MH-03 | trace_id required on every request | `RequestRouter._validate()` |
| MH-04 | HARD rejection on budget exceeded | `BudgetEnforcer.check()`, `RequestRouter._route_inner()` |
| MH-05 | Circuit breaker per provider | `CircuitBreakerManager` |
| MH-06 | Fallback is capability-aware (top 3) | `ModelSelector.select()`, `ProviderDispatcher.dispatch()` |
| MH-07 | Cost from manifest model cost table | `CostTracker.compute_cost()`, `ModelSelector._score_candidate()` |
| MH-08 | $5/day default daily budget | `BudgetEnforcer` (from ModelHubConfig) |
| MH-09 | Cache TTL 5min default, LRU eviction | `ResponseCache` |
| MH-11 | Full audit trail for every call | `AuditLogger` |
| MH-12 | Rate limiting per provider with 80% headroom | `RateLimiter` |
| MH-13 | Placement cascade (Local → Remote → Cached → Template) | `ModelSelector._PLACEMENT_SCORES` |
| MH-15 | Priority-based timeouts | `RequestRouter` (in constraints) |
| MH-16 | ALL traffic through RequestRouter | `RequestRouter` |
| MH-17 | Plugin isolation | `ProviderDispatcher._try_provider()` |
| MH-18 | Manifest is SOLE capability truth | `ProviderRegistry`, `CapabilityRouter` |
