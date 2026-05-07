# Model Hub (`k1.model_hub`)

> Layer L2.5 — Unified LLM access gateway with provider abstraction, cost management, and resilience.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      IModelHubPort (Facade)                      │
│                  execute() / stream_execute()                    │
│              discover_capabilities() / discover_models()         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     RequestRouter (MH-16)                        │
│  9-Step Pipeline: Validate → Budget → Priority → Route →        │
│  Select → Cache → Normalize → Dispatch → Post-Process           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   CapabilityRouter   ModelSelector   ProviderDispatcher
        │                  │                  │
   ProviderRegistry   BudgetEnforcer     Plugins
        │                  │                  │
   RateLimiter      CostTracker       CircuitBreaker
        │                  │                  │
   ResponseCache    AuditLogger     NormalizationLayer
```

All traffic flows through `RequestRouter` (invariant **MH-16**). No shortcut paths exist.

## 9-Step Request Pipeline

| Step | Service | Description |
|------|---------|-------------|
| 1 | `RequestRouter._validate()` | Schema validation, trace_id enforcement (MH-03) |
| 2 | `BudgetEnforcer.check()` | Daily budget check → ALLOW / ALLOW_DEGRADED / REJECT (MH-04, MH-08) |
| 3 | Priority classification | Timeout from `RequestConstraints.priority` (MH-15) |
| 4 | `CapabilityRouter.route()` | 5-step filtering → eligible providers (MH-06, MH-18) |
| 5 | `ModelSelector.select()` | Weighted scoring → provider + model + fallback chain (MH-13) |
| 6 | `ResponseCache.get()` | Cache lookup → hit returns immediately (MH-09) |
| 7 | `NormalizationLayer.normalize()` | HubRequest → NormalizedRequest (provider-agnostic) |
| 8 | `ProviderDispatcher.dispatch()` | Execute plugin with circuit breaker + rate limiter + retry (MH-05, MH-12) |
| 9 | Post-process | Denormalize, cache store, cost tracking (MH-07), audit logging (MH-11) |

## 18 Hard Invariants

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| MH-01 | Hub NEVER writes session state | No `IStateWritePort` dependency |
| MH-02 | API keys from CredentialStore only | `ICredentialPort`, never from manifest |
| MH-03 | trace_id required on every request | `HubRequest.__post_init__` raises `ValueError` |
| MH-04 | HARD rejection on budget exceeded | `BudgetEnforcer.check()` → `BudgetExceededError` |
| MH-05 | Circuit breaker per provider | `CircuitBreakerManager` per-provider state machine |
| MH-06 | Fallback chain from capability routing | `ModelSelector` builds ordered fallback list |
| MH-07 | Cost from manifest model cost tables | `CostTracker.compute_cost()` uses `ModelSpec` |
| MH-08 | $5/day default daily budget | `ModelHubConfig.daily_budget_usd = 5.0` |
| MH-09 | Cache TTL 5min default, LRU eviction | `ResponseCache` with configurable TTL |
| MH-10 | Streaming via async generators | `stream_execute()` yields `HubChunk` |
| MH-11 | Full audit trail per request | `AuditLogger.log()` captures all metadata |
| MH-12 | Rate limiting per provider 80% headroom | `RateLimiter` token bucket with headroom |
| MH-13 | Model selection by priority-weighted scoring | `ModelSelector` with per-priority weights |
| MH-14 | No hardcoded model names in hub code | All model references via manifest `ModelSpec` |
| MH-15 | Priority-based timeouts | `RequestConstraints.priority` → timeout_ms |
| MH-16 | ALL traffic through RequestRouter | Single entry point, no bypass |
| MH-17 | Plugin isolation (one crash doesn't affect others) | Exception handling in `_try_provider()` |
| MH-18 | Manifest sole source of truth for capabilities | `ProviderManifest` drives all routing |

## Hexagonal Ports (7)

| Port | Protocol | Purpose |
|------|----------|---------|
| `IModelHubPort` | Hub facade | `execute()`, `stream_execute()`, `discover_*()`, `health()` |
| `IEventPort` | Event bus | `publish(topic, payload)` for integration events |
| `IStateReadPort` | State reading | Read-only session state access |
| `IMetricsPort` | Metrics | `emit(metric_name, value, labels)` fire-and-forget |
| `IConfigPort` | Configuration | `get(key)` / `watch(key, callback)` |
| `ICredentialPort` | Credentials | `get_key(provider_id)` / `refresh_key()` (MH-02) |
| `IHealthPort` | Health | `report_health()` / `check_health()` |

## Provider Plugin Contract

Every provider implements `IProviderPlugin` (7 methods):

```python
class IProviderPlugin(Protocol):
    async def initialize(self, manifest: ProviderManifest) -> None: ...
    def supports(self, capability: CapabilityType) -> bool: ...
    async def execute(self, request: NormalizedRequest) -> ProviderResponse: ...
    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]: ...
    def estimate_tokens(self, messages: list) -> int: ...
    async def health_check(self) -> ProviderHealth: ...
    async def close(self) -> None: ...
```

**Day-1 plugins**: OpenAI, Anthropic, Google (google-genai SDK), vLLM, Ollama.

### Adding a New Provider

1. Create `k1/model_hub/plugins/my_plugin.py` implementing `IProviderPlugin`
2. Create a `ProviderManifest` YAML/dict with capabilities, models, costs
3. Register via `ProviderRegistry.register(manifest, plugin)`
4. The hub automatically routes traffic based on manifest capabilities

## Observability

### Metrics (12 definitions)

| Metric | Type | Description |
|--------|------|-------------|
| `model_hub.requests_total` | Counter | Total requests received |
| `model_hub.errors_total` | Counter | Total errors (label: `error_type`) |
| `model_hub.cache_hits_total` | Counter | Response cache hits |
| `model_hub.fallbacks_total` | Counter | Provider fallback events |
| `model_hub.budget_rejections_total` | Counter | Budget-rejected requests |
| `model_hub.latency_ms` | Histogram | End-to-end hub latency |
| `model_hub.provider_latency_ms` | Histogram | Provider plugin latency |
| `model_hub.tokens_used` | Histogram | Tokens per request |
| `model_hub.cost_usd` | Histogram | Cost per request in USD |
| `model_hub.active_requests` | Gauge | Currently active requests |
| `model_hub.provider_circuit_state` | Gauge | Circuit breaker state per provider |
| `model_hub.budget_pct` | Gauge | Daily budget usage percentage |

### Structured Logging (34 phases)

All log events via `k1.model_hub.tracing` with fields:

- `trace_id`, `request_id`, `consumer_id` (correlation)
- `capability`, `model_id`, `provider_id` (context)
- `timestamp`, `level`, `phase` (structure)

**Privacy**: Raw prompts and API keys are NEVER logged. Use `redact_messages()` and `safe_labels()`.

## Factory & Dependency Injection

```python
from k1.model_hub.factory import ModelHubFactory

# Production
hub = ModelHubFactory.create_standalone(config=cfg, plugins=plugins)

# Testing (returns facade + all services for inspection)
hub, adapters = ModelHubFactory.create_for_testing(overrides={...})

# Custom ports
hub = ModelHubFactory.create_with_ports(ports={"credential_port": my_cred})
```

## Performance Targets

| Operation | Target | Measured |
|-----------|--------|----------|
| Budget check | < 1ms | ✅ |
| Capability routing | < 2ms | ✅ |
| Model selection | < 5ms | ✅ |
| Cache lookup | < 2ms | ✅ |
| Normalization | < 1ms | ✅ |
| **Total hub overhead** | **< 12ms** | ✅ |

(Excludes LLM inference time)

## Test Coverage

| Category | File | Tests |
|----------|------|-------|
| Unit tests | `tests/k1/model_hub/test_*.py` | ~820 |
| Contract tests | `tests/k1/model_hub/contract/` | 61 |
| Integration tests | `tests/k1/model_hub/integration/` | 28 |
| Lifecycle tests | `tests/k1/model_hub/lifecycle/` | 39 |
| Benchmarks | `tests/k1/model_hub/benchmarks/` | 11 |
| Chaos tests | `tests/k1/model_hub/chaos/` | 22 |
| Tracing tests | `tests/k1/model_hub/test_tracing.py` | 26 |

**Total: ~1000+ tests** | Zero `unittest.mock` imports | All 18 invariants tested

## Running Tests

```bash
# All model hub tests
python -m pytest tests/k1/model_hub/ -q

# Specific categories
python -m pytest tests/k1/model_hub/contract/ -q
python -m pytest tests/k1/model_hub/integration/ -q
python -m pytest tests/k1/model_hub/lifecycle/ -q
python -m pytest tests/k1/model_hub/benchmarks/ -q
python -m pytest tests/k1/model_hub/chaos/ -q

# Live Google integration tests (requires GOOGLE_API_KEY)
python -m pytest tests/k1/model_hub/test_google_live.py -v -s
```
