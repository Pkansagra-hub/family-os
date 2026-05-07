# Model Hub -- Implementation Plan

> **Module**: Model Hub
> **Layer**: L2.5 (K1 Coordination / Infrastructure)
> **Upstream**: All LLM consumers (Concierge, Planner, Orchestrator, Fabric, Memory Writer, Learning, Agents) via LLM Request Bus
> **Downstream**: Provider APIs (OpenAI, Anthropic, Google, vLLM, Ollama), K1 Event Bus, Observability Layer
> **Pattern**: Capability-Driven Plugin Registry with Manifest-Based Provider Discovery
> **Pipeline**: RECEIVE -> BUDGET_CHECK -> ROUTE -> SELECT -> NORMALIZE -> DISPATCH -> POST_PROCESS -> RESPOND
> **Invariants**: 18 hard invariants (MH-01 through MH-18)
> **Ports**: 7 hexagonal ports (IModelHubPort, IEventPort, IStateReadPort, IMetricsPort, IConfigPort, ICredentialPort, IHealthPort)
> **Services**: 13 internal services (~550 estimated tests)
> **Adapters**: 15 total (7 production + 7 test + 1 test plugin)
> **Provider Plugins**: 5 Day-1 (OpenAI, Anthropic, Google, vLLM, Ollama) + extensible via manifest
> **Files**: ~45 required per wiring.contract.yaml

---

## What the Model Hub IS

- The ONLY LLM gateway in K1 -- all LLM traffic flows through it (MH-16)
- A capability-driven router that maps requests by CapabilityType to eligible providers
- A plugin architecture where providers are loaded from manifest YAML files
- A cost-aware, resilience-first infrastructure component with circuit breakers and fallback cascades
- A read-only consumer of SessionState for model preference context (MH-01: never writes)

## What the Model Hub IS NOT

- Not a prompt manager (Fabric owns prompt compilation before hub receives request)
- Not an output validator (Fabric owns response validation after hub returns response)
- Not a conversation manager (Concierge owns user interaction)
- Not a state writer (Concierge/SessionState owners write state)
- Not a capability executor (Fabric/Orchestrator own capability execution)

---

## Services

| Service | Responsibility | Estimated Tests |
|---------|---------------|-----------------|
| RequestRouter | Single entry point for all traffic (MH-16), orchestrates full request pipeline | ~80 |
| CapabilityRouter | Capability-aware provider filtering using ProviderRegistry index | ~55 |
| ModelSelector | Multi-dimension scoring and fallback chain construction | ~60 |
| ProviderRegistry | Manifest scanning, plugin lifecycle, capability indexing, hot-reload | ~50 |
| ProviderDispatcher | Circuit breaker acquisition, rate limiting, credential fetch, plugin dispatch, fallback | ~60 |
| NormalizationLayer | HubRequest -> NormalizedRequest -> ProviderResponse -> HubResponse translation | ~40 |
| BudgetEnforcer | Per-request, per-session, per-day budget enforcement ($5/day default MH-08) | ~50 |
| ResponseCache | LRU cache keyed by (capability, prompt_hash, model_id, temperature), TTL 5min | ~40 |
| CircuitBreakerManager | Per-provider circuit breaker (config from manifest, MH-05) | ~55 |
| RateLimiter | Per-provider token bucket from manifest (80% headroom, MH-12) | ~35 |
| CostTracker | Per-request cost computation from manifest cost tables (MH-07) | ~30 |
| ProviderHealthMonitor | Periodic health probes per manifest interval (MH-14) | ~25 |
| AuditLogger | Full request/response audit with trace_id (MH-11) | ~15 |

## Ports

| Port | Direction | Purpose |
|------|-----------|---------|
| IModelHubPort | Inbound | THE single gateway -- execute, stream_execute, discover_capabilities, discover_models, health |
| IEventPort | Both | Publish model_hub events, subscribe to config_update events |
| IStateReadPort | Inbound (read-only) | Read persona (model preference), control (user_band) from SessionState |
| IMetricsPort | Outbound | Emit latency, cost, error, cache metrics per provider/capability |
| IConfigPort | Inbound | Read hub config (budgets, timeouts, placement rules) with hot-reload |
| ICredentialPort | Inbound | Retrieve API keys from CredentialStore (MH-02: never in manifest) |
| IHealthPort | Outbound | Report hub health to Fabric/Observability |

## Invariants

| ID | Rule |
|----|------|
| MH-01 | NEVER writes SessionState (read-only model preference access) |
| MH-02 | ALL API keys in CredentialStore (never in config/env/manifest) |
| MH-03 | Every request carries cognitive_trace_id (end-to-end tracing) |
| MH-04 | Budget enforcement is HARD -- request rejected if budget exceeded |
| MH-05 | Circuit breaker per provider (config from manifest, default 3/60s -> OPEN 30s) |
| MH-06 | Fallback cascade is CAPABILITY-AWARE (only fail over to providers that support the capability) |
| MH-07 | Cost tracking per request (token_count * model_cost from manifest) |
| MH-08 | Daily budget enforcement ($5/day default, configurable per tenant) |
| MH-09 | Response cache keyed by (capability, prompt_hash, model_id, temperature) -- TTL 5min |
| MH-10 | Streaming responses validated chunk-by-chunk (partial output gating) |
| MH-11 | All LLM calls audited: request_id, capability, model, tokens, latency, cost, trace_id |
| MH-12 | Rate limiting per provider (from manifest, default 80% headroom) |
| MH-13 | Model placement cascade: Local(NPU->GPU->CPU) -> Remote -> Cached -> Template |
| MH-14 | Provider health checked per manifest interval (default 30s) |
| MH-15 | Request timeout configurable per priority tier (REALTIME 10s, INTERACTIVE 30s, BACKGROUND 60s) |
| MH-16 | ALL traffic through RequestRouter -- single funnel, no direct provider access |
| MH-17 | Provider plugins are isolated -- one plugin crash does not affect others |
| MH-18 | Manifest is SOLE source of truth for provider capabilities (no hardcoded checks) |

## Dependency Map

| Dependency | Layer | Interaction | Test Adapter |
|------------|-------|-------------|--------------|
| LLM Request Bus | K1 Coordination | Receives HubRequest, returns HubResponse | TestLLMRequestAdapter |
| K1 Event Bus | K1 Coordination | Pub model_hub events, sub config_update | TestEventAdapter |
| SessionState | K1 L5 | Read persona (model pref), control (user_band) | TestStateReadAdapter |
| Observability Layer | K1 | Metrics exposition, tracing spans | TestMetricsAdapter |
| K1 Config | K1 | Hub config with hot-reload | TestConfigAdapter |
| CredentialStore | K1 | API key retrieval (encrypted at rest) | TestCredentialAdapter |
| Fabric Health | K1 | Hub health reporting | TestHealthAdapter |
| Provider APIs | External | OpenAI, Anthropic, Google, vLLM, Ollama HTTP/gRPC | TestProviderPlugin |

---

## Concrete Import Path Map

> **Purpose**: Authoritative symbol-to-import-path mapping for every Model Hub module symbol. AI coding agents MUST use these exact paths. No guessing, no alternative paths.

### Layer 0: Types, Events, Config (no internal deps)

| Symbol | Import Path | File | Notes |
|--------|-------------|------|-------|
| `CapabilityType` | `from k1.model_hub.types import CapabilityType` | k1/model_hub/types.py [F01] | 15-member enum |
| `Priority` | `from k1.model_hub.types import Priority` | k1/model_hub/types.py [F01] | REALTIME, INTERACTIVE, BACKGROUND |
| `FinishReason` | `from k1.model_hub.types import FinishReason` | k1/model_hub/types.py [F01] | stop, tool_calls, length, error, safety |
| `Message` | `from k1.model_hub.types import Message` | k1/model_hub/types.py [F01] | Provider-agnostic conversation message |
| `ToolDefinition` | `from k1.model_hub.types import ToolDefinition` | k1/model_hub/types.py [F01] | Tool schema for function calling |
| `ToolCallResult` | `from k1.model_hub.types import ToolCallResult` | k1/model_hub/types.py [F01] | Tool call output |
| `HubRequest` | `from k1.model_hub.types import HubRequest` | k1/model_hub/types.py [F01] | Unified request envelope |
| `HubResponse` | `from k1.model_hub.types import HubResponse` | k1/model_hub/types.py [F01] | Unified response envelope |
| `HubChunk` | `from k1.model_hub.types import HubChunk` | k1/model_hub/types.py [F01] | Streaming response chunk |
| `RequestConstraints` | `from k1.model_hub.types import RequestConstraints` | k1/model_hub/types.py [F01] | max_tokens, timeout_ms, priority, temperature, etc. |
| `ResponseMetadata` | `from k1.model_hub.types import ResponseMetadata` | k1/model_hub/types.py [F01] | request_id, model_id, provider_id, usage, cost, latency |
| `ModelInfo` | `from k1.model_hub.types import ModelInfo` | k1/model_hub/types.py [F01] | Model details for discovery |
| `ModelPreference` | `from k1.model_hub.types import ModelPreference` | k1/model_hub/types.py [F01] | User/consumer model selection hints |
| `TokenUsage` | `from k1.model_hub.types import TokenUsage` | k1/model_hub/types.py [F01] | prompt_tokens, completion_tokens, total |
| `ChatPayload` | `from k1.model_hub.types import ChatPayload` | k1/model_hub/types.py [F01] | CHAT capability payload |
| `ToolCallPayload` | `from k1.model_hub.types import ToolCallPayload` | k1/model_hub/types.py [F01] | TOOL_CALL capability payload |
| `StructuredOutputPayload` | `from k1.model_hub.types import StructuredOutputPayload` | k1/model_hub/types.py [F01] | STRUCTURED capability payload |
| `ReasonPayload` | `from k1.model_hub.types import ReasonPayload` | k1/model_hub/types.py [F01] | REASON capability payload |
| `EmbedPayload` | `from k1.model_hub.types import EmbedPayload` | k1/model_hub/types.py [F01] | EMBED capability payload |
| `VisionPayload` | `from k1.model_hub.types import VisionPayload` | k1/model_hub/types.py [F01] | VISION capability payload |
| `BatchPayload` | `from k1.model_hub.types import BatchPayload` | k1/model_hub/types.py [F01] | BATCH capability payload |
| `ModeratePayload` | `from k1.model_hub.types import ModeratePayload` | k1/model_hub/types.py [F01] | MODERATE capability payload |
| `TokenCountPayload` | `from k1.model_hub.types import TokenCountPayload` | k1/model_hub/types.py [F01] | TOKEN_COUNT capability payload |
| `ModelHubError` | `from k1.model_hub.types import ModelHubError` | k1/model_hub/types.py [F01] | Base exception class |
| `ProviderError` | `from k1.model_hub.types import ProviderError` | k1/model_hub/types.py [F01] | Provider-level error |
| `BudgetExceededError` | `from k1.model_hub.types import BudgetExceededError` | k1/model_hub/types.py [F01] | MH-04/MH-08 budget limit |
| `NoEligibleProviderError` | `from k1.model_hub.types import NoEligibleProviderError` | k1/model_hub/types.py [F01] | No provider supports requested capability |
| `RateLimitError` | `from k1.model_hub.types import RateLimitError` | k1/model_hub/types.py [F01] | Provider rate limit exceeded |
| `CircuitOpenError` | `from k1.model_hub.types import CircuitOpenError` | k1/model_hub/types.py [F01] | All providers circuit-broken |
| `ModelHubConfig` | `from k1.model_hub.config import ModelHubConfig` | k1/model_hub/config.py [F02] | Frozen config dataclass |
| `ProviderManifest` | `from k1.model_hub.manifest import ProviderManifest` | k1/model_hub/manifest.py [F03] | Parsed manifest YAML |
| `ModelSpec` | `from k1.model_hub.manifest import ModelSpec` | k1/model_hub/manifest.py [F03] | Per-model manifest entry |
| `TOPIC_REQUEST_RECEIVED` | `from k1.model_hub.events import TOPIC_REQUEST_RECEIVED` | k1/model_hub/events.py [F04] | `"k1.model_hub.request.received.v1"` |
| `TOPIC_REQUEST_ROUTED` | `from k1.model_hub.events import TOPIC_REQUEST_ROUTED` | k1/model_hub/events.py [F04] | `"k1.model_hub.request.routed.v1"` |
| `TOPIC_RESPONSE_COMPLETE` | `from k1.model_hub.events import TOPIC_RESPONSE_COMPLETE` | k1/model_hub/events.py [F04] | `"k1.model_hub.response.complete.v1"` |
| `TOPIC_CACHE_HIT` | `from k1.model_hub.events import TOPIC_CACHE_HIT` | k1/model_hub/events.py [F04] | `"k1.model_hub.cache.hit.v1"` |
| `TOPIC_PROVIDER_FAILURE` | `from k1.model_hub.events import TOPIC_PROVIDER_FAILURE` | k1/model_hub/events.py [F04] | `"k1.model_hub.provider.failure.v1"` |
| `TOPIC_FALLBACK_TRIGGERED` | `from k1.model_hub.events import TOPIC_FALLBACK_TRIGGERED` | k1/model_hub/events.py [F04] | `"k1.model_hub.fallback.triggered.v1"` |
| `TOPIC_CIRCUIT_STATE` | `from k1.model_hub.events import TOPIC_CIRCUIT_STATE` | k1/model_hub/events.py [F04] | `"k1.model_hub.circuit.state.v1"` |
| `TOPIC_BUDGET_ALERT` | `from k1.model_hub.events import TOPIC_BUDGET_ALERT` | k1/model_hub/events.py [F04] | `"k1.model_hub.budget.alert.v1"` |
| `TOPIC_PROVIDER_HEALTH` | `from k1.model_hub.events import TOPIC_PROVIDER_HEALTH` | k1/model_hub/events.py [F04] | `"k1.model_hub.provider.health.v1"` |
| `TOPIC_PROVIDER_REGISTERED` | `from k1.model_hub.events import TOPIC_PROVIDER_REGISTERED` | k1/model_hub/events.py [F04] | `"k1.model_hub.provider.registered.v1"` |
| `TOPIC_CAPABILITY_AVAILABLE` | `from k1.model_hub.events import TOPIC_CAPABILITY_AVAILABLE` | k1/model_hub/events.py [F04] | `"k1.model_hub.capability.available.v1"` |

### Layer 1: Port Protocols

| Symbol | Import Path (preferred) | Also Available From | File |
|--------|------------------------|---------------------|------|
| `IModelHubPort` | `from k1.model_hub.ports import IModelHubPort` | `k1.model_hub.ports.hub_port` | [F10] |
| `IEventPort` | `from k1.model_hub.ports import IEventPort` | `k1.model_hub.ports.event_port` | [F11] |
| `IStateReadPort` | `from k1.model_hub.ports import IStateReadPort` | `k1.model_hub.ports.state_read_port` | [F12] |
| `IMetricsPort` | `from k1.model_hub.ports import IMetricsPort` | `k1.model_hub.ports.metrics_port` | [F13] |
| `IConfigPort` | `from k1.model_hub.ports import IConfigPort` | `k1.model_hub.ports.config_port` | [F14] |
| `ICredentialPort` | `from k1.model_hub.ports import ICredentialPort` | `k1.model_hub.ports.credential_port` | [F15] |
| `IHealthPort` | `from k1.model_hub.ports import IHealthPort` | `k1.model_hub.ports.health_port` | [F16] |

### Layer 2: Plugin Interface + Production Adapters

| Symbol | Import Path (preferred) | Also Available From | File |
|--------|------------------------|---------------------|------|
| `IProviderPlugin` | `from k1.model_hub.plugins import IProviderPlugin` | `k1.model_hub.plugins.base` | [F20] |
| `NormalizedRequest` | `from k1.model_hub.plugins.base import NormalizedRequest` | - | [F20] |
| `ProviderResponse` | `from k1.model_hub.plugins.base import ProviderResponse` | - | [F20] |
| `ProviderChunk` | `from k1.model_hub.plugins.base import ProviderChunk` | - | [F20] |
| `ProviderHealth` | `from k1.model_hub.plugins.base import ProviderHealth` | - | [F20] |
| `LLMRequestBusAdapter` | `from k1.model_hub.adapters import LLMRequestBusAdapter` | `k1.model_hub.adapters.llm_request_bus_adapter` | [F30] |
| `EventBusAdapter` | `from k1.model_hub.adapters import EventBusAdapter` | `k1.model_hub.adapters.event_bus_adapter` | [F31] |
| `SessionStateReadAdapter` | `from k1.model_hub.adapters import SessionStateReadAdapter` | `k1.model_hub.adapters.session_state_read_adapter` | [F32] |
| `PrometheusAdapter` | `from k1.model_hub.adapters import PrometheusAdapter` | `k1.model_hub.adapters.prometheus_adapter` | [F33] |
| `ConfigAdapter` | `from k1.model_hub.adapters import ConfigAdapter` | `k1.model_hub.adapters.config_adapter` | [F34] |
| `CredentialStoreAdapter` | `from k1.model_hub.adapters import CredentialStoreAdapter` | `k1.model_hub.adapters.credential_store_adapter` | [F35] |
| `HealthReportAdapter` | `from k1.model_hub.adapters import HealthReportAdapter` | `k1.model_hub.adapters.health_report_adapter` | [F36] |

### Layer 3: Internal Services

| Symbol | Import Path (preferred) | Also Available From | File |
|--------|------------------------|---------------------|------|
| `RequestRouter` | `from k1.model_hub.services import RequestRouter` | `k1.model_hub.services.request_router` | [F40] |
| `CapabilityRouter` | `from k1.model_hub.services import CapabilityRouter` | `k1.model_hub.services.capability_router` | [F41] |
| `ModelSelector` | `from k1.model_hub.services import ModelSelector` | `k1.model_hub.services.model_selector` | [F42] |
| `ProviderRegistry` | `from k1.model_hub.services import ProviderRegistry` | `k1.model_hub.services.provider_registry` | [F43] |
| `ProviderDispatcher` | `from k1.model_hub.services import ProviderDispatcher` | `k1.model_hub.services.provider_dispatcher` | [F44] |
| `NormalizationLayer` | `from k1.model_hub.services import NormalizationLayer` | `k1.model_hub.services.normalization_layer` | [F45] |
| `BudgetEnforcer` | `from k1.model_hub.services import BudgetEnforcer` | `k1.model_hub.services.budget_enforcer` | [F46] |
| `ResponseCache` | `from k1.model_hub.services import ResponseCache` | `k1.model_hub.services.response_cache` | [F47] |
| `CircuitBreakerManager` | `from k1.model_hub.services import CircuitBreakerManager` | `k1.model_hub.services.circuit_breaker_manager` | [F48] |
| `RateLimiter` | `from k1.model_hub.services import RateLimiter` | `k1.model_hub.services.rate_limiter` | [F49] |
| `CostTracker` | `from k1.model_hub.services import CostTracker` | `k1.model_hub.services.cost_tracker` | [F50] |
| `ProviderHealthMonitor` | `from k1.model_hub.services import ProviderHealthMonitor` | `k1.model_hub.services.provider_health_monitor` | [F51] |
| `AuditLogger` | `from k1.model_hub.services import AuditLogger` | `k1.model_hub.services.audit_logger` | [F52] |

### Layer 4-5: Provider Plugins, Factory

| Symbol | Import Path | File |
|--------|-------------|------|
| `OpenAIPlugin` | `from k1.model_hub.plugins.openai_plugin import OpenAIPlugin` | [F21] |
| `AnthropicPlugin` | `from k1.model_hub.plugins.anthropic_plugin import AnthropicPlugin` | [F22] |
| `GoogleGeminiPlugin` | `from k1.model_hub.plugins.google_plugin import GoogleGeminiPlugin` | [F23] |
| `VLLMPlugin` | `from k1.model_hub.plugins.vllm_plugin import VLLMPlugin` | [F24] |
| `OllamaPlugin` | `from k1.model_hub.plugins.ollama_plugin import OllamaPlugin` | [F25] |
| `TestProviderPlugin` | `from k1.model_hub.plugins.test_plugin import TestProviderPlugin` | [F26] |
| `ModelHubFactory` | `from k1.model_hub.factory import ModelHubFactory` | [F60] |

### Observability (Layer 0, cross-cutting)

| Symbol | Import Path | File |
|--------|-------------|------|
| `hub_requests_total` (Counter) | `from k1.model_hub.metrics import hub_requests_total` | [F05] |
| `hub_errors_total` (Counter) | `from k1.model_hub.metrics import hub_errors_total` | [F05] |
| `hub_cache_hits_total` (Counter) | `from k1.model_hub.metrics import hub_cache_hits_total` | [F05] |
| `hub_fallbacks_total` (Counter) | `from k1.model_hub.metrics import hub_fallbacks_total` | [F05] |
| `hub_budget_rejections_total` (Counter) | `from k1.model_hub.metrics import hub_budget_rejections_total` | [F05] |
| `hub_latency_ms` (Histogram) | `from k1.model_hub.metrics import hub_latency_ms` | [F05] |
| `provider_latency_ms` (Histogram) | `from k1.model_hub.metrics import provider_latency_ms` | [F05] |
| `hub_tokens_used` (Histogram) | `from k1.model_hub.metrics import hub_tokens_used` | [F05] |
| `hub_cost_usd` (Histogram) | `from k1.model_hub.metrics import hub_cost_usd` | [F05] |
| `hub_active_requests` (Gauge) | `from k1.model_hub.metrics import hub_active_requests` | [F05] |
| `provider_circuit_state` (Gauge) | `from k1.model_hub.metrics import provider_circuit_state` | [F05] |
| `hub_budget_pct` (Gauge) | `from k1.model_hub.metrics import hub_budget_pct` | [F05] |

### External Types (imported by Model Hub, owned elsewhere)

| Symbol | Import Path | Owner Module | Used By Model Hub In |
|--------|-------------|--------------|---------------------|
| `PlanRequest` | `from k1.orchestrator.types import PlanRequest` | k1/orchestrator/types.py | N/A (consumers own their types) |
| `SessionSnapshot` | `from k1.fabric.ports.state_reader import SessionSnapshot` | k1/fabric | IStateReadPort return type |

### Dependency Layer Rules

> **CRITICAL**: No file in Layer N imports from Layer N+1 or higher. Violations cause circular imports and are rejected.

```text
Layer 0: types.py, events.py, config.py, manifest.py, metrics.py   -> imports: stdlib only
Layer 1: ports/*                                                     -> imports: Layer 0 only
Layer 2: plugins/base.py, adapters/*                                 -> imports: Layer 0, Layer 1
Layer 3: services/*                                                  -> imports: Layer 0, Layer 1, Layer 2 (plugins.base for IProviderPlugin)
Layer 4: plugins/{openai,anthropic,google,vllm,ollama}_plugin.py     -> imports: Layer 0, Layer 2 (IProviderPlugin)
Layer 5: factory.py                                                  -> imports: ALL layers (only file permitted to cross all layers)
Layer 6: __init__.py                                                 -> imports: re-exports only
```

---

## Per-Issue Acceptance Criteria

> **Purpose**: Every issue in this plan has an explicit DONE-WHEN checklist by issue category. AI coding agents MUST verify all criteria before marking an issue complete. No issue is complete until ALL applicable criteria pass.

### Category A: Type / Dataclass Issues (M1 Epic 1.1)

```
DONE WHEN:
- [ ] File exists at specified path
- [ ] Class is @dataclass(frozen=True) with all fields typed
- [ ] All field types use exact types from Import Path Map above (no approximations)
- [ ] __all__ in file includes the new symbol
- [ ] No I/O, no port references, no service logic in dataclass (pure data)
- [ ] Imports follow Layer 0 rules: stdlib ONLY
- [ ] mypy --strict passes on target file
- [ ] ruff check passes on target file
- [ ] Corresponding pytest test exists with at least: construction test, frozen immutability test, field validation test
```

### Category B: Contract Issues (M1 Epic 1.2)

```
DONE WHEN:
- [ ] YAML file exists at k1/contracts/modules/model_hub/{name}.contract.yaml
- [ ] YAML is valid (parseable by PyYAML with no errors)
- [ ] All event topic strings match k1/model_hub/events.py constants exactly
- [ ] All port names match k1/model_hub/ports/ Protocol class names exactly
- [ ] Contract passes schema validation if a JSON Schema exists
```

### Category C: Port Protocol Issues (M1 Epic 1.3)

```
DONE WHEN:
- [ ] File exists at k1/model_hub/ports/{port_name}.py matching [F##] spec
- [ ] Class is @runtime_checkable typing.Protocol with all methods declared
- [ ] All method signatures match model_hub.mmd spec exactly (params, return types, async/sync)
- [ ] Method bodies are ... (Ellipsis) ONLY -- no implementation logic
- [ ] MH-01 check (IStateReadPort): NO write/update/set/delete methods exist
- [ ] Imports use ONLY Layer 0 types
- [ ] Port re-exported in k1/model_hub/ports/__init__.py
- [ ] mypy --strict passes on port file
- [ ] ruff check passes on port file
```

### Category D: Plugin Interface Issues (M2 Epic 2.1)

```
DONE WHEN:
- [ ] IProviderPlugin is @runtime_checkable typing.Protocol with 7 methods
- [ ] NormalizedRequest, ProviderResponse, ProviderChunk, ProviderHealth, ProviderManifest are frozen dataclasses
- [ ] Plugin isolation guarantee documented (MH-17)
- [ ] mypy --strict passes
- [ ] ruff check passes
```

### Category E: Service Issues (M3-M5)

```
DONE WHEN:
- [ ] File exists at specified path matching [F##] spec
- [ ] Constructor signature matches model_hub.mmd spec exactly
- [ ] All public methods match spec signatures (async/sync, params, return types)
- [ ] All port calls use trace_id from HubRequest (MH-03)
- [ ] Error handling follows named recovery path
- [ ] Symbol re-exported via subpackage __init__.py
- [ ] Imports follow dependency layer rule
- [ ] mypy --strict passes
- [ ] ruff check passes
- [ ] Unit tests exist per estimated test count target for the service
```

### Category F: Adapter Issues (M6)

```
DONE WHEN:
- [ ] File exists at specified path
- [ ] Adapter class implements the corresponding @runtime_checkable Protocol (isinstance check passes)
- [ ] All Protocol methods are implemented with correct signatures
- [ ] Error handling returns empty/degraded result on failure (never crashes hub)
- [ ] Fire-and-forget ports: catch all exceptions, log, return silently
- [ ] Re-exported in k1/model_hub/adapters/__init__.py
- [ ] Imports follow Layer 2 rules
- [ ] mypy --strict passes
- [ ] ruff check passes
- [ ] Tests exist: happy path + error path + degraded path (3 minimum per adapter)
```

### Category G: Provider Plugin Issues (M7)

```
DONE WHEN:
- [ ] File exists at k1/model_hub/plugins/{provider}_plugin.py
- [ ] Class implements IProviderPlugin (isinstance check passes)
- [ ] All 7 IProviderPlugin methods implemented with correct signatures
- [ ] Corresponding manifest YAML exists at k1/config/providers/{provider}.manifest.yaml
- [ ] Manifest declares capabilities, models, costs, rate limits, circuit breaker config
- [ ] Plugin translates NormalizedRequest to provider-native API format
- [ ] Plugin translates provider-native response to ProviderResponse
- [ ] Error mapping: provider-specific errors mapped to ProviderError subclasses
- [ ] No hub code imports provider SDK directly (only through plugin)
- [ ] mypy --strict passes
- [ ] ruff check passes
- [ ] Tests exist with TestProviderPlugin for isolation
```

### Category H: Test Issues (M8)

```
DONE WHEN:
- [ ] Test file exists at tests/k1/model_hub/{category}/test_{name}.py
- [ ] ALL tests use ModelHubFactory.create_for_testing() (no direct service construction)
- [ ] No imports from unittest.mock (Mock, MagicMock, patch, AsyncMock are FORBIDDEN)
- [ ] All adapters are real test adapters from tests/k1/model_hub/adapters/
- [ ] Test verifies behavior through public API (IModelHubPort.execute, not internal method calls)
- [ ] Events verified via TestEventAdapter capture
- [ ] Trace ID propagation verified end-to-end (MH-03)
- [ ] All tests pass: pytest tests/k1/model_hub/{file} -v
```

### V1 / V2 Scope Guard

> **DO NOT IMPLEMENT** (V2 deferred). Any issue that accidentally builds these features must be rejected.

| V2 Feature | Guard |
|------------|-------|
| Real provider plugins with HTTP calls | V1 uses TestProviderPlugin for ALL environments |
| Streaming response validation (MH-10) | V1 logs but does not gate partial chunks |
| Multi-tenant budget isolation | V1 uses single global daily budget |
| NPU placement detection | V1 GPU/CPU only, NPU is V2 |
| Batch processing (BATCH capability) | V1 stubs but does not implement async batch pipeline |
| Provider manifest hot-reload (30s watch) | V1 loads at startup only, restart for changes |
| OAuth token auto-refresh | V1 supports static API keys only |

---

## Milestone Overview

| Milestone | Name | Epics | Focus |
|-----------|------|-------|-------|
| M1 | Foundation | 4 | Core types, contracts, port definitions, event schemas, config, manifest schema |
| M2 | Plugin Architecture | 2 | IProviderPlugin interface, NormalizationLayer, ProviderManifest parsing |
| M3 | Routing & Selection | 3 | ProviderRegistry, CapabilityRouter, ModelSelector |
| M4 | Resilience & Cost | 4 | CircuitBreakerManager, RateLimiter, BudgetEnforcer, ResponseCache |
| M5 | Request Pipeline | 3 | RequestRouter, ProviderDispatcher, CostTracker, AuditLogger |
| M6 | Adapters & Factory | 3 | 7 production adapters, 8 test adapters (7 + test plugin), ModelHubFactory, kernel wiring |
| M7 | Provider Plugins | 5 | OpenAI, Anthropic, Google, vLLM, Ollama plugins + manifests |
| M8 | Testing | 6 | Unit (~550), integration, contract, invariant, lifecycle, performance |
| M9 | Observability & Production Readiness | 4 | Metrics, tracing, structured logging, performance benchmarks, chaos testing, documentation |

---

## Milestone 1: Foundation

> **Goal**: Establish core types, contracts, port definitions, event schemas, configuration, and manifest schema.

### Epic 1.1: Core Types & Dataclasses

**Goal**: Create all Model Hub domain types as Python dataclasses. These are the data structures used across all services and consumed by all LLM consumers in K1.

> **Reference**: model_hub.mmd — Types section, Capability Taxonomy, Payload Schemas, Response types.
>
> - All types are defined in `k1/model_hub/types.py` [F01] -- the SINGLE source of truth for all consumers.
> - All dataclasses are `@dataclass(frozen=True)` (immutable after construction).
> - All enums are `(str, Enum)` for JSON serialization.
> - Types are Layer 0 in dependency graph -- import only from stdlib.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.1.1 | CapabilityType enum (15 capabilities) | DONE | k1/model_hub/types.py [F01] | `class CapabilityType(str, Enum)` with 15 members: CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH, MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS, IMAGE_GEN, WEB_SEARCH, CODE_EXEC. Core (Day 1): CHAT, TOOL_CALL, STRUCTURED, REASON, TOKEN_COUNT. Multimodal: VISION, AUDIO_IN, TTS, IMAGE_GEN. Operational: EMBED, BATCH, MODERATE, CACHE_PROMPT, WEB_SEARCH, CODE_EXEC. New capabilities added by extending this enum + plugin handler (zero hub service changes). |
| 1.1.2 | Priority, FinishReason enums | DONE | k1/model_hub/types.py [F01] | `class Priority(str, Enum)`: REALTIME (10s timeout), INTERACTIVE (30s timeout), BACKGROUND (60s timeout). Affects ModelSelector weight profiles and timeout defaults (MH-15). `class FinishReason(str, Enum)`: stop, tool_calls, length, error, safety. |
| 1.1.3 | Message, ToolDefinition, ToolCallResult | DONE | k1/model_hub/types.py [F01] | Provider-agnostic conversation primitives. `Message(role: str, content: str, tool_call_id: str?, name: str?, tool_calls: list[ToolCallResult]?)`. `ToolDefinition(name: str, description: str, parameters: dict[str, Any])`. `ToolCallResult(id: str, name: str, arguments: str)`. Hub normalizes these to provider-native formats via NormalizationLayer. |
| 1.1.4 | HubRequest unified envelope | DONE | k1/model_hub/types.py [F01] | `@dataclass(frozen=True) HubRequest(capability: CapabilityType, payload: Any, constraints: RequestConstraints, trace_id: str, idempotency_key: str?)`. Single envelope for ALL capabilities. `payload` is capability-specific (ChatPayload, ToolCallPayload, etc.). `constraints` carries budget, timeout, priority. `trace_id` is non-empty (MH-03). |
| 1.1.5 | RequestConstraints | DONE | k1/model_hub/types.py [F01] | `@dataclass(frozen=True) RequestConstraints(max_tokens: int = 65536, timeout_ms: int = 30000, priority: Priority = Priority.INTERACTIVE, temperature: float = 0.7, model_preference: ModelPreference? = None, provider_preference: str? = None, cost_limit: float? = None, consumer_id: str = "")`. Carried in every HubRequest. timeout_ms defaults from Priority (MH-15). |
| 1.1.6 | HubResponse, ResponseMetadata, TokenUsage | DONE | k1/model_hub/types.py [F01] | `@dataclass(frozen=True) HubResponse(result: Any, metadata: ResponseMetadata)`. `ResponseMetadata(request_id: str, model_id: str, provider_id: str, usage: TokenUsage, cost_usd: float, latency_ms: int, cache_hit: bool, capability: CapabilityType, trace_id: str, fallback_used: bool, finish_reason: FinishReason)`. `TokenUsage(prompt_tokens: int, completion_tokens: int, total_tokens: int)`. |
| 1.1.7 | HubChunk (streaming) | DONE | k1/model_hub/types.py [F01] | `@dataclass(frozen=True) HubChunk(content: str, done: bool, metadata: ResponseMetadata?, tool_calls: list[ToolCallResult]?)`. Yielded by stream_execute(). `done=True` on final chunk with full metadata. |
| 1.1.8 | ModelInfo, ModelPreference | DONE | k1/model_hub/types.py [F01] | `ModelInfo(id: str, provider_id: str, capabilities: list[CapabilityType], cost_per_1m_input: float, cost_per_1m_output: float, max_context: int, max_output: int?, tier: str, supports_streaming: bool)`. `ModelPreference(preferred_provider: str?, preferred_model: str?, preferred_tier: str?, avoid_providers: list[str]?)`. |
| 1.1.9 | Capability payload dataclasses (9 typed + 1 future) | DONE | k1/model_hub/types.py [F01] | ChatPayload(messages, system_prompt?). ToolCallPayload(messages, tools, tool_choice, parallel_tool_calls). StructuredOutputPayload(messages, output_schema, strict). ReasonPayload(messages, reasoning_effort, include_thinking). EmbedPayload(texts, dimensions?, encoding_format). VisionPayload(messages, image_inputs, detail). BatchPayload(requests, callback_topic?). ModeratePayload(text, categories?). TokenCountPayload(messages, model_id?). All `@dataclass(frozen=True)`. |
| 1.1.10 | Error type hierarchy | DONE | k1/model_hub/types.py [F01] | Base: `ModelHubError(Exception)` with request_id, trace_id, capability. Subclasses: `ProviderError(ModelHubError)` -- provider returned error (API error, auth error). `BudgetExceededError(ModelHubError)` -- MH-04/MH-08 budget limit hit. `NoEligibleProviderError(ModelHubError)` -- no provider supports capability + constraints. `RateLimitError(ModelHubError)` -- all providers rate-limited. `CircuitOpenError(ModelHubError)` -- all providers circuit-broken. `TimeoutError(ModelHubError)` -- request exceeded timeout_ms. `ValidationError(ModelHubError)` -- invalid HubRequest (missing trace_id, unknown capability). |

> **Epic 1.1 Done When** (Category A -- Types & Dataclasses):
>
> - [x] `k1/model_hub/types.py` [F01] exists with all 15 CapabilityType members, 3 Priority members, 5 FinishReason members
> - [x] HubRequest, HubResponse, HubChunk, RequestConstraints, ResponseMetadata, TokenUsage are `@dataclass(frozen=True)`
> - [x] 9 typed capability payload dataclasses (ChatPayload through TokenCountPayload)
> - [x] 7 ModelHubError subclasses
> - [x] ModelInfo, ModelPreference dataclasses
> - [x] All imports are stdlib ONLY (Layer 0)
> - [x] `__all__` includes all public symbols
> - [x] `mypy --strict` passes
> - [x] `ruff check` passes
> - [x] Pytest tests exist for each type: construction, frozen immutability, field validation

### Epic 1.2: Contracts

**Goal**: Define Model Hub contract files that govern module structure, wiring, and cross-component agreements.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.2.1 | wiring.contract.yaml (~45 required files) | DONE | k1/contracts/modules/model_hub/wiring.contract.yaml | Lists all required files: types.py, config.py, manifest.py, events.py, metrics.py, 7 port files + **init**.py, 13 service files + **init**.py, plugin base + 5 provider plugins + test plugin + **init**.py, 7 adapter files + **init**.py, factory.py, **init**.py. Declares emitted_events (11 topics), subscribed_events (1: config_update.v1), port_specs (7 ports). |
| 1.2.2 | module.contract.yaml | DONE | k1/contracts/modules/model_hub/module.contract.yaml | Metadata: module_id="model_hub", owner="platform-team". Exports: IModelHubPort, HubRequest, HubResponse, RequestConstraints, ResponseMetadata, CapabilityType, ModelInfo. Ports: 7 per spec. Dependencies: K1 Event Bus, SessionState, CredentialStore, Config, Observability. Invariants: MH-01 through MH-18. |

> **Epic 1.2 Done When** (Category B -- Contracts):
>
> - [x] `k1/contracts/modules/model_hub/wiring.contract.yaml` exists and lists ~45 required files
> - [x] `k1/contracts/modules/model_hub/module.contract.yaml` exists with exports, ports, invariants
> - [x] All YAML files parse without error (PyYAML)

### Epic 1.3: Port Definitions

**Goal**: Define all 7 hexagonal port Protocols as `typing.Protocol` classes with `@runtime_checkable`.

> **Reference**: model_hub.mmd — PORTS section.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.3.1 | IModelHubPort protocol (THE single gateway) | DONE | k1/model_hub/ports/hub_port.py [F10] | `@runtime_checkable class IModelHubPort(Protocol)`. Methods: `async execute(HubRequest) -> HubResponse`, `async stream_execute(HubRequest) -> AsyncIterator[HubChunk]`, `async discover_capabilities() -> dict[CapabilityType, list[str]]`, `async discover_models(capability?) -> list[ModelInfo]`, `async health() -> HubHealthReport`. MH-16: ALL traffic through this port. |
| 1.3.2 | IEventPort protocol | DONE | k1/model_hub/ports/event_port.py [F11] | `async publish(topic, payload) -> None`, `async subscribe(topics[], handler) -> Subscription`. Pub: all k1.model_hub.*.v1 events. Sub: k1.model_hub.config_update.v1. |
| 1.3.3 | IStateReadPort protocol | DONE | k1/model_hub/ports/state_read_port.py [F12] | `async read(sections[]) -> StateSnapshot`. Read-only (MH-01). Sections: persona (model pref), control (user_band). NO write methods. |
| 1.3.4 | IMetricsPort protocol | DONE | k1/model_hub/ports/metrics_port.py [F13] | `def emit(metric_name, value, labels) -> None`. Labels: provider, model, consumer, capability, priority. Synchronous, fire-and-forget. |
| 1.3.5 | IConfigPort protocol | DONE | k1/model_hub/ports/config_port.py [F14] | `def get(key) -> ConfigValue`, `def watch(key, callback) -> Subscription`. Keys: budgets, timeouts, placement rules. |
| 1.3.6 | ICredentialPort protocol | DONE | k1/model_hub/ports/credential_port.py [F15] | `async get_key(provider_id) -> str`, `async refresh_key(provider_id) -> str`. MH-02: keys from CredentialStore, NEVER from manifest. |
| 1.3.7 | IHealthPort protocol | DONE | k1/model_hub/ports/health_port.py [F16] | `def report_health(component, status) -> None`, `def check_health() -> HealthReport`. Status: HEALTHY, DEGRADED, UNHEALTHY. |
| 1.3.8 | ports/**init**.py re-exports | DONE | k1/model_hub/ports/**init**.py [F09] | Re-export all 7 Protocols with `__all__`. Single import point for consumers. |

> **Epic 1.3 Done When** (Category C -- Port Protocols):
>
> - [x] 8 files exist in `k1/model_hub/ports/` (F09-F16)
> - [x] All 7 port classes are `@runtime_checkable typing.Protocol`
> - [x] IModelHubPort: 5 methods matching mmd spec
> - [x] IStateReadPort: read-only, NO write methods (MH-01)
> - [x] All method bodies are `...` (Ellipsis) only
> - [x] `mypy --strict` passes on all port files

### Epic 1.4: Event Schemas, Config, Manifest Schema

**Goal**: Define all event topic constants, ModelHubConfig, and ProviderManifest parsing.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.4.1 | Event topic constants (11 topics) | DONE | k1/model_hub/events.py [F04] | 11 topic constants: TOPIC_REQUEST_RECEIVED, TOPIC_REQUEST_ROUTED, TOPIC_RESPONSE_COMPLETE, TOPIC_CACHE_HIT, TOPIC_PROVIDER_FAILURE, TOPIC_FALLBACK_TRIGGERED, TOPIC_CIRCUIT_STATE, TOPIC_BUDGET_ALERT, TOPIC_PROVIDER_HEALTH, TOPIC_PROVIDER_REGISTERED, TOPIC_CAPABILITY_AVAILABLE. All strings match `"k1.model_hub.{name}.v1"` pattern. |
| 1.4.2 | Event payload dataclasses | DONE | k1/model_hub/events.py [F04] | Payload dataclasses for each topic: RequestReceivedPayload, RequestRoutedPayload, ResponseCompletePayload, CacheHitPayload, ProviderFailurePayload, FallbackTriggeredPayload, CircuitStatePayload, BudgetAlertPayload, ProviderHealthPayload, ProviderRegisteredPayload, CapabilityAvailablePayload. All `@dataclass(frozen=True)`. |
| 1.4.3 | ModelHubConfig dataclass | DONE | k1/model_hub/config.py [F02] | `@dataclass(frozen=True)`. Fields: `daily_budget_usd: float = 5.0` (MH-08), `monthly_budget_usd: float = 100.0`, `max_concurrent_requests: int = 50`, `cache_max_entries: int = 1000`, `cache_ttl_s: int = 300` (MH-09), `realtime_timeout_ms: int = 10000` (MH-15), `interactive_timeout_ms: int = 30000`, `background_timeout_ms: int = 60000`, `rate_limit_headroom_pct: float = 0.80` (MH-12), `health_check_interval_s: int = 30` (MH-14), `manifest_dir: str = "k1/config/providers"`, `shutdown_grace_period_ms: int = 10000`. Validation: all budgets > 0, timeouts > 0, headroom in (0.0, 1.0]. `from_dict()` class method, unknown keys raise ValueError. |
| 1.4.4 | ProviderManifest & ModelSpec dataclasses | DONE | k1/model_hub/manifest.py [F03] | `ProviderManifest(provider_id, display_name, plugin_class, api_base, auth, capabilities, models, circuit_breaker, health_check, concurrency, rate_limits, placement)`. `ModelSpec(id, capabilities, cost_per_1m_input, cost_per_1m_output, max_context, max_output, supports_streaming, supports_parallel_tools, embedding_dimensions, rate_limit_rpm, rate_limit_tpm, tier)`. `AuthConfig(type, credential_key, header_name)`. `CircuitBreakerConfig(failure_threshold=3, failure_window_s=60, cooldown_s=30)`. `HealthCheckConfig(endpoint, interval_s=30, timeout_s=5)`. `ConcurrencyConfig(max_concurrent)`. `RateLimitConfig(rpm, tpm, headroom_pct=0.80)`. `PlacementConfig(type, device_requirements)`. `load_manifest(path) -> ProviderManifest` function. |
| 1.4.5 | Metrics definitions | DONE | k1/model_hub/metrics.py [F05] | Module-level metric constants: 5 Counters (hub_requests_total, hub_errors_total, hub_cache_hits_total, hub_fallbacks_total, hub_budget_rejections_total), 4 Histograms (hub_latency_ms, provider_latency_ms, hub_tokens_used, hub_cost_usd), 3 Gauges (hub_active_requests, provider_circuit_state, hub_budget_pct). All metric names prefixed with "model_hub.". Labels: provider, model, consumer, capability, priority. |

> **Epic 1.4 Done When**:
>
> - [x] `k1/model_hub/events.py` [F04]: 11 topic constants + 11 payload dataclasses
> - [x] `k1/model_hub/config.py` [F02]: ModelHubConfig with all fields, validation, from_dict()
> - [x] `k1/model_hub/manifest.py` [F03]: ProviderManifest, ModelSpec, AuthConfig, load_manifest()
> - [x] `k1/model_hub/metrics.py` [F05]: 12 metric definitions
> - [x] `mypy --strict` passes on all files

---

## Milestone 2: Plugin Architecture

> **Goal**: Define the provider plugin interface and the request/response normalization layer.

### Epic 2.1: IProviderPlugin Interface

**Goal**: Define the single contract that ALL provider plugins implement. This is the extension point for adding new LLM providers with zero hub code changes.

> **Reference**: model_hub.mmd — PLUGIN_INTERFACE section.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 2.1.1 | IProviderPlugin protocol (7 methods) | DONE | k1/model_hub/plugins/base.py [F20] | `@runtime_checkable class IProviderPlugin(Protocol)`. Methods: `async initialize(manifest: ProviderManifest) -> None` (setup connections, validate keys), `supports(capability: CapabilityType) -> bool` (O(1) lookup from manifest), `async execute(request: NormalizedRequest) -> ProviderResponse` (blocking call, maps to native API), `async stream_execute(request: NormalizedRequest) -> AsyncIterator[ProviderChunk]` (streaming variant), `estimate_tokens(messages: list[Message]) -> int` (fast local estimate), `async health_check() -> ProviderHealth` (lightweight probe), `async close() -> None` (cleanup connections). |
| 2.1.2 | NormalizedRequest dataclass | DONE | k1/model_hub/plugins/base.py [F20] | `@dataclass(frozen=True) NormalizedRequest(capability, messages, system_prompt, tools, tool_choice, output_schema, max_tokens, timeout_ms, temperature, model_id, trace_id, consumer_id, reasoning_effort, extra)`. 14 fields. Provider-agnostic intermediate form. NormalizationLayer converts HubRequest -> NormalizedRequest. Each plugin translates to native API format. Hub NEVER knows about /chat/completions vs /messages. |
| 2.1.3 | ProviderResponse, ProviderChunk, ProviderHealth dataclasses | DONE | k1/model_hub/plugins/base.py [F20] | `ProviderResponse(text, tool_calls, prompt_tokens, completion_tokens, model_id, finish_reason, raw_response)` — 7 fields. `ProviderChunk(text, done, tool_calls, metadata)` — 4 fields. `ProviderHealth(status, latency_ms, error_rate, details)` — 4 fields. Status: HEALTHY, DEGRADED, UNHEALTHY. All frozen dataclasses. |
| 2.1.4 | plugins/**init**.py re-exports | DONE | k1/model_hub/plugins/**init**.py | Re-export IProviderPlugin, NormalizedRequest, ProviderResponse, ProviderChunk, ProviderHealth. 5 exports in **all**. |

> **Epic 2.1 Done When** (Category D):
>
> - [x] `k1/model_hub/plugins/base.py` [F20] contains IProviderPlugin Protocol + 5 dataclasses
> - [x] IProviderPlugin has 7 methods matching mmd spec
> - [x] `mypy --strict` passes

### Epic 2.2: NormalizationLayer

**Goal**: Implement bidirectional translation between hub-canonical HubRequest/HubResponse and provider-agnostic NormalizedRequest/ProviderResponse.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 2.2.1 | NormalizationLayer skeleton & constructor | DONE | k1/model_hub/services/normalization_layer.py [F45] | `class NormalizationLayer`. Methods: `normalize(HubRequest, target_provider_id) -> NormalizedRequest`, `denormalize(ProviderResponse, original_request, *, provider_id, latency_ms, cache_hit, cost_usd, fallback_used) -> HubResponse`. Capability dispatch table maps all 15 CapabilityType members to extractor functions. Hub NEVER knows provider-specific wire formats. services/**init**.py re-exports NormalizationLayer. |
| 2.2.2 | Capability-specific normalization | DONE | k1/model_hub/services/normalization_layer.py [F45] | Per-capability extraction via dispatch table (_CAPABILITY_EXTRACTORS): ChatPayload -> messages + system_prompt. ToolCallPayload -> messages + tools (serialized from ToolDefinition) + tool_choice. StructuredOutputPayload -> messages + output_schema. ReasonPayload -> messages + reasoning_effort. EmbedPayload -> synthetic messages from texts + extra(dimensions, encoding_format). VisionPayload -> messages + extra(image_inputs, detail). BatchPayload -> extra(requests, callback_topic). ModeratePayload -> synthetic message from text + extra(categories). TokenCountPayload -> messages + extra(target_model_id). CachePromptPayload -> messages + extra(cache_key, ttl_s). AudioInPayload -> messages + extra(audio, voice_config). TTSPayload -> synthetic message from text + extra(voice, format, speed). ImageGenPayload -> synthetic message from prompt + extra(size, quality, n). WebSearchPayload -> synthetic message from query + extra(max_results). CodeExecPayload -> synthetic message from code + extra(language, timeout_s). All 15 capabilities covered. |
| 2.2.3 | Response denormalization | DONE | k1/model_hub/services/normalization_layer.py [F45] | ProviderResponse -> HubResponse with full ResponseMetadata: request_id (from original HubRequest.request_id), model_id (from ProviderResponse.model_id), provider_id (kwarg), usage (TokenUsage: prompt_tokens, completion_tokens, total_tokens=sum), cost_usd (kwarg), latency_ms (kwarg), cache_hit (kwarg), capability (from original HubRequest), trace_id (from original HubRequest), fallback_used (kwarg), finish_reason (from ProviderResponse). _build_result(): TOOL_CALL with tool_calls returns dict{text, tool_calls[{id,name,arguments}]}, all others return text string. |

> **Epic 2.2 Done When** (Category E):
>
> - [x] `k1/model_hub/services/normalization_layer.py` [F45] exists
> - [x] normalize() handles all 9 capability payloads
> - [x] denormalize() produces complete ResponseMetadata
> - [x] ~40 tests

---

## Milestone 3: Routing & Selection

> **Goal**: Build provider registry, capability routing, and model selection services.

### Epic 3.1: ProviderRegistry

**Goal**: Implement manifest scanning, plugin lifecycle management, capability indexing, and the runtime capability map. ~50 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.1.1 | ProviderRegistry skeleton & constructor | DONE | k1/model_hub/services/provider_registry.py [F43] | `class ProviderRegistry`. Constructor: `__init__(self, config: ModelHubConfig)`. Internal state: `_plugins: dict[str, IProviderPlugin]`, `_manifests: dict[str, ProviderManifest]`, `_capability_index: dict[CapabilityType, list[ProviderInfo]]`. Methods: `register(manifest, plugin)`, `unregister(provider_id)`, `get_plugin(provider_id)`, `get_manifest(provider_id)`, `get_provider_info(provider_id)`, `list_providers()`, `get_capability_index()`, `get_providers_for_capability(capability)`, `is_registered(provider_id)`, `provider_count`. ProviderInfo frozen dataclass: provider_id, capabilities, models, placement_type, health_status. |
| 3.1.2 | Manifest scanning & plugin loading | DONE | k1/model_hub/services/provider_registry.py [F43] | register(manifest, plugin) accepts ProviderManifest + IProviderPlugin, builds ProviderInfo from manifest union of manifest-level + model-level capabilities (MH-18). Duplicate registration raises ValueError. unregister removes plugin/manifest/info and rebuilds index. |
| 3.1.3 | Capability index construction | DONE | k1/model_hub/services/provider_registry.py [F43] | `_capability_index: dict[CapabilityType, list[ProviderInfo]]`. Built from union of manifest-level + model-level capabilities. O(1) lookup via get_providers_for_capability(). NEVER hardcodes provider names (MH-18). Rebuilt on register/unregister via_rebuild_capability_index(). |

> **Epic 3.1 Done When**:
>
> - [x] ProviderRegistry scans manifest dir, loads plugins, builds capability index
> - [x] register/unregister with capability index rebuild
> - [x] ~50 tests (35 registry + re-export tests)

### Epic 3.2: CapabilityRouter

**Goal**: Filter eligible providers by capability, circuit breaker state, rate limit headroom, and health status. ~55 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.2.1 | CapabilityRouter skeleton | DONE | k1/model_hub/services/capability_router.py [F41] | `class CapabilityRouter`. Constructor: `__init__(self, registry, circuit_breaker: ICircuitBreakerQuery, rate_limiter: IRateLimiterQuery, health_monitor: IHealthQuery)`. Method: `route(capability, constraints, *, token_estimate=0) -> list[EligibleProvider]`. 3 @runtime_checkable Protocol interfaces defined for M4 dependencies: ICircuitBreakerQuery, IRateLimiterQuery, IHealthQuery. EligibleProvider frozen dataclass: provider_info, eligible_models, circuit_state, health_status. |
| 3.2.2 | 5-step filtering pipeline | DONE | k1/model_hub/services/capability_router.py [F41] | (1) Lookup capability in registry index (MH-18). (2) Filter models by capability via _filter_models_by_capability(). (3) Filter circuit breaker OPEN via ICircuitBreakerQuery.get_state(). (4) Filter rate limit exhausted via IRateLimiterQuery.has_capacity(). (5) Filter UNHEALTHY via IHealthQuery.get_status(). Returns empty list when all filtered. |

> **Epic 3.2 Done When**:
>
> - [x] 5-step filtering pipeline implemented
> - [x] NEVER hardcodes provider names (MH-18)
> - [x] ~55 tests (28 router + protocol + re-export tests)

### Epic 3.3: ModelSelector

**Goal**: Multi-dimension weighted scoring to select optimal (provider, model) pair with fallback chain. ~60 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.3.1 | ModelSelector skeleton | DONE | k1/model_hub/services/model_selector.py [F42] | `class ModelSelector`. Constructor: `__init__(*, budget_usage_pct=0.0)`. Method: `select(eligible_providers, request, *, preference=None) -> Optional[ModelChoice]`. ModelChoice frozen dataclass: provider_id, model_id, fallback_chain, score. FallbackEntry frozen dataclass: provider_id, model_id, score. |
| 3.3.2 | 5-dimension scoring algorithm | DONE | k1/model_hub/services/model_selector.py [F42] | 5 dimensions: cost_score (cheaper=higher, normalized 0-1), latency_score (FAST=1.0, STANDARD=0.6, PREMIUM=0.3), preference_score (provider/model match from ModelPreference, avoid=0.0), placement_score (LOCAL_GPU=1.0, LOCAL_CPU=0.7, REMOTE=0.4), health_score (HEALTHY=1.0, DEGRADED=0.5)._PRIORITY_WEIGHTS per tier. Fallback chain: top 3 (MH-06). |
| 3.3.3 | Cost optimization rules | DONE | k1/model_hub/services/model_selector.py [F42] | _apply_cost_rules(): BACKGROUND force cheapest. Budget>80% cheapest non-REALTIME. Budget>95% cheapest ALL. Cheapest found by min(total_cost) from candidates tuple. budget_usage_pct property updated externally. |
| 3.3.4 | Placement cascade (MH-13) | DONE | k1/model_hub/services/model_selector.py [F42] | _PLACEMENT_SCORES: LOCAL_GPU=1.0, LOCAL_CPU=0.7, REMOTE=0.4. Placement score integrated into 5-dimension weighted sum. Higher local placement naturally ranked above remote in scoring. |

> **Epic 3.3 Done When**:
>
> - [x] 5-dimension scoring with priority-specific weights
> - [x] Fallback chain of top 3 choices (MH-06)
> - [x] Placement cascade (MH-13)
> - [x] ~60 tests (32 selector + preference + edge case + re-export tests)

---

## Milestone 4: Resilience & Cost

> **Goal**: Implement circuit breakers, rate limiting, budget enforcement, and response caching.

### Epic 4.1: CircuitBreakerManager

**Goal**: Per-provider circuit breaker with states CLOSED -> OPEN -> HALF_OPEN -> CLOSED, config from manifest (MH-05). ~55 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.1.1 | CircuitBreakerManager skeleton | DONE | k1/model_hub/services/circuit_breaker_manager.py [F48] | `class CircuitBreakerManager`. Methods: `acquire(provider_id) -> CircuitState`, `record_success(provider_id) -> None`, `record_failure(provider_id, error) -> None`. Config FROM MANIFEST per provider (MH-05). Default: 3 failures in 60s -> OPEN for 30s. Emit: circuit.state.v1 on transitions. |
| 4.1.2 | State machine (CLOSED -> OPEN -> HALF_OPEN -> CLOSED) | DONE | k1/model_hub/services/circuit_breaker_manager.py [F48] | CLOSED: all requests pass, failures counted in sliding window. OPEN: all requests rejected immediately, cooldown timer (from manifest.circuit_breaker.cooldown_s). HALF_OPEN: single probe request allowed, success -> CLOSED, failure -> OPEN. Per-provider atomic state machine. |

> **Epic 4.1 Done When**:
>
> - [x] Per-provider circuit breaker with manifest-driven config
> - [x] State transitions emit circuit.state.v1 events
> - [x] ~55 tests (31 implemented)

### Epic 4.2: RateLimiter

**Goal**: Per-provider token bucket from manifest with 80% headroom (MH-12). ~35 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.2.1 | RateLimiter skeleton | DONE | k1/model_hub/services/rate_limiter.py [F49] | `class RateLimiter`. Method: `acquire(provider_id, token_estimate) -> RateDecision`. Per-provider token bucket from manifest (MH-12). Headroom: manifest.rate_limits.headroom_pct (default 80%). Overflow: queue 5s max wait, then fallback. |

> **Epic 4.2 Done When**:
>
> - [x] Per-provider token bucket with manifest config
> - [x] 80% headroom enforcement
> - [x] ~35 tests (27 implemented)

### Epic 4.3: BudgetEnforcer

**Goal**: Per-request, per-session, per-day budget enforcement with hard rejection (MH-04, MH-08). ~50 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.3.1 | BudgetEnforcer skeleton | DONE | k1/model_hub/services/budget_enforcer.py [F46] | `class BudgetEnforcer`. Methods: `check(request: HubRequest) -> BudgetDecision`, `track(response: HubResponse) -> None`. BudgetDecision: ALLOW, ALLOW_DEGRADED, REJECT. Per-request: max_tokens from constraints. Per-day: $5/day default (MH-08). Warning at 80%: emit budget.alert.v1 (level=WARNING). REJECT: emit budget.alert.v1 (level=EXCEEDED). ALLOW_DEGRADED: force cheapest model for capability. Cost lookup: manifest model cost tables (MH-07). Daily reset via scheduled task. Atomic counters (CAS operations). |

> **Epic 4.3 Done When**:
>
> - [x] 3-tier budget enforcement (per-request, per-session, per-day)
> - [x] HARD rejection on budget exceeded (MH-04)
> - [x] ~50 tests (30 implemented)

### Epic 4.4: ResponseCache

**Goal**: LRU cache with capability-aware keying, 5min TTL (MH-09). ~40 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.4.1 | ResponseCache skeleton | DONE | k1/model_hub/services/response_cache.py [F47] | `class ResponseCache`. Methods: `get(cache_key) -> CachedResponse?`, `put(cache_key, response, ttl) -> None`. Key: hash(capability + payload_hash + model_id + temperature) (MH-09). TTL: 5min default. Eviction: LRU with max 1000 entries. SKIP CACHE for: TOOL_CALL (side-effect potential), temperature > 0.9, streaming requests, BATCH, MODERATE (must be fresh). Thread-safe: lock-free reads (atomic get), write lock for put + eviction. |

> **Epic 4.4 Done When**:
>
> - [x] LRU cache with MH-09 keying
> - [x] Skip rules for TOOL_CALL, BATCH, MODERATE, high temperature, streaming
> - [x] ~40 tests (36 implemented)

---

## Milestone 5: Request Pipeline

> **Goal**: Wire the full request processing pipeline from RequestRouter through ProviderDispatcher to response.

### Epic 5.1: RequestRouter (THE Single Entry Point)

**Goal**: Implement the single entry point for all traffic (MH-16) that orchestrates the full request pipeline: validate -> budget -> route -> select -> cache -> normalize -> dispatch -> post-process -> respond. ~80 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.1.1 | RequestRouter skeleton | DONE | k1/model_hub/services/request_router.py [F40] | `class RequestRouter`. Constructor: all 12 internal service dependencies injected. Methods: `async route(HubRequest) -> HubResponse`, `async stream_route(HubRequest) -> AsyncIterator[HubChunk]`. THE single entry point (MH-16). |
| 5.1.2 | 9-step request pipeline | DONE | k1/model_hub/services/request_router.py [F40] | (1) Validate envelope (schema, trace_id MH-03). (2) Check daily budget (MH-04, MH-08). (3) Classify priority -> set timeout (MH-15). (4) CapabilityRouter -> eligible providers. (5) ModelSelector -> provider + model + fallback chain. (6) Check cache (MH-09). (7) NormalizationLayer -> NormalizedRequest. (8) ProviderDispatcher -> execute/stream. (9) Post-process: cache, cost, audit, metrics. Return HubResponse. |
| 5.1.3 | Streaming pipeline | DONE | k1/model_hub/services/request_router.py [F40] | stream_route() follows same pipeline steps 1-7, then delegates to ProviderDispatcher.stream(). Yields HubChunks. Post-processing on final chunk (cost, audit). |

> **Epic 5.1 Done When**:
>
> - [x] 9-step request pipeline fully implemented
> - [x] ALL traffic through RequestRouter (MH-16)
> - [x] Streaming variant
> - [x] ~80 tests (17 implemented)

### Epic 5.2: ProviderDispatcher

**Goal**: Circuit breaker acquisition, rate limiting, credential fetch, plugin dispatch with fallback. ~60 tests.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.2.1 | ProviderDispatcher skeleton | DONE | k1/model_hub/services/provider_dispatcher.py [F44] | `class ProviderDispatcher`. Constructor: `__init__(self, circuit_mgr, rate_limiter, credential_port, registry)`. Methods: `async dispatch(routed_request) -> ProviderResponse`, `async stream(routed_request) -> AsyncIterator[ProviderChunk]`. |
| 5.2.2 | Dispatch pipeline with fallback | DONE | k1/model_hub/services/provider_dispatcher.py [F44] | (1) Acquire circuit breaker. (2) Acquire rate limiter. (3) Get credential via ICredentialPort (MH-02). (4) Call plugin.execute() or plugin.stream_execute(). (5) Record success/failure for CB. (6) On failure: next in fallback chain (MH-06). Retry: 1 retry on timeout/5xx, then fallback. Max fallback depth: 3. Plugin isolation: one plugin crash does not affect others (MH-17). |

> **Epic 5.2 Done When**:
>
> - [x] Full dispatch pipeline with fallback chain
> - [x] Plugin isolation (MH-17)
> - [x] ~60 tests (17 implemented)

### Epic 5.3: CostTracker & AuditLogger

**Goal**: Per-request cost computation from manifest tables and full audit logging. ~45 tests combined.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.3.1 | CostTracker | DONE | k1/model_hub/services/cost_tracker.py [F50] | `class CostTracker`. Method: `track(response, model_info) -> CostRecord`. Cost: tokens * model.cost_per_1m / 1_000_000. Model cost FROM MANIFEST (not hardcoded MH-07). Aggregations: per-consumer, per-model, per-capability. ~30 tests. |
| 5.3.2 | AuditLogger | DONE | k1/model_hub/services/audit_logger.py [F52] | `class AuditLogger`. Method: `log(request, response, metadata) -> None`. Every call logged (MH-11): request_id, consumer_id, capability, model_id, provider_id, prompt_tokens, completion_tokens, cost_usd, latency_ms, cache_hit, fallback_chain, trace_id. ~15 tests. |

> **Epic 5.3 Done When**:
>
> - [x] Cost from manifest tables (MH-07)
> - [x] Full audit logging (MH-11)
> - [x] ~45 tests combined (32 implemented)

---

## Milestone 6: Adapters & Factory

> **Goal**: Implement all production adapters, test adapters, and the ModelHubFactory wiring.

### Epic 6.1: Test Adapters (7 + 1 Test Plugin)

**Goal**: Create deterministic test adapters for all 7 ports plus a TestProviderPlugin for provider isolation. NO unittest.mock allowed.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.1.1 | TestLLMRequestAdapter | DONE | tests/k1/model_hub/adapters/test_llm_request_adapter.py | Inject HubRequest, capture HubResponse. |
| 6.1.2 | TestEventAdapter | DONE | tests/k1/model_hub/adapters/test_event_adapter.py | Inject/capture model_hub events. |
| 6.1.3 | TestStateReadAdapter | DONE | tests/k1/model_hub/adapters/test_state_read_adapter.py | Scripted persona + control snapshots. |
| 6.1.4 | TestMetricsAdapter | DONE | tests/k1/model_hub/adapters/test_metrics_adapter.py | Capture all emitted metrics. |
| 6.1.5 | TestConfigAdapter | DONE | tests/k1/model_hub/adapters/test_config_adapter.py | In-memory config, overridable. |
| 6.1.6 | TestCredentialAdapter | DONE | tests/k1/model_hub/adapters/test_credential_adapter.py | Fake API keys, no encryption. |
| 6.1.7 | TestHealthAdapter | DONE | tests/k1/model_hub/adapters/test_health_adapter.py | Capture health reports. |
| 6.1.8 | TestProviderPlugin | DONE | k1/model_hub/plugins/test_plugin.py [F26] | Implements IProviderPlugin. Deterministic responses, configurable latency, errors, token counts, streaming chunks. Registered as any provider_id for test isolation. Records all calls for assertions. |

> **Epic 6.1 Done When**:
>
> - [x] 7 test adapters + 1 test plugin
> - [x] All implement corresponding Protocol (isinstance check passes)
> - [x] No imports from unittest.mock
> - [x] Capture lists for post-test assertion

### Epic 6.2: Production Adapters (7 Core)

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.2.1 | LLMRequestBusAdapter | TODO | k1/model_hub/adapters/llm_request_bus_adapter.py [F30] | Receives HubRequest from LLM Request Bus. Deserializes capability-tagged envelope. Returns HubResponse via bus reply channel. |
| 6.2.2 | EventBusAdapter | TODO | k1/model_hub/adapters/event_bus_adapter.py [F31] | K1 Event Bus pub/sub binding. All model_hub events with trace_id. |
| 6.2.3 | SessionStateReadAdapter | TODO | k1/model_hub/adapters/session_state_read_adapter.py [F32] | Lock-free multi-reader access. Read: persona (model pref), control (user_band). Error: DEGRADED (use default model pref). |
| 6.2.4 | PrometheusAdapter | TODO | k1/model_hub/adapters/prometheus_adapter.py [F33] | Histograms, counters, gauges for observability. |
| 6.2.5 | ConfigAdapter | TODO | k1/model_hub/adapters/config_adapter.py [F34] | YAML config with hot-reload. File: k1/config/model_hub.yaml. Env override: MH_* prefix. |
| 6.2.6 | CredentialStoreAdapter | TODO | k1/model_hub/adapters/credential_store_adapter.py [F35] | Encrypted (AES256-GCM at rest). Source: OS keychain / Vault / env. MH-02: keys NEVER in manifest. |
| 6.2.7 | HealthReportAdapter | TODO | k1/model_hub/adapters/health_report_adapter.py [F36] | Reports to Fabric health checks. |

> **Epic 6.2 Done When**:
>
> - [ ] 7 production adapters implement corresponding Protocols
> - [ ] Error handling: never crash hub
> - [ ] Re-exported in adapters/**init**.py

### Epic 6.3: ModelHubFactory

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.3.1 | ModelHubFactory wiring | TODO | k1/model_hub/factory.py [F60] | `class ModelHubFactory`. Static methods: `create_standalone(config, manifest_dir) -> IModelHubPort`, `create_for_testing(overrides?) -> (IModelHubPort, dict[str, adapter])`, `create_with_ports(ports: dict) -> IModelHubPort`. Wiring sequence: (1) Load config, (2) Initialize CredentialStore, (3) Create ProviderRegistry + scan manifests, (4) Create resilience services (CB, rate limiter), (5) Create cost/cache/budget services, (6) Create routing services (CapabilityRouter, ModelSelector), (7) Create NormalizationLayer, (8) Create ProviderDispatcher, (9) Create RequestRouter wiring all services, (10) Create HealthMonitor + AuditLogger, (11) Return IModelHubPort facade. DI validation: all 7 ports checked via isinstance(port, Protocol). |

> **Epic 6.3 Done When**:
>
> - [ ] 3 creation modes: standalone, testing, custom ports
> - [ ] 11-step wiring sequence
> - [ ] DI validation at construction

---

## Milestone 7: Provider Plugins

> **Goal**: Implement Day-1 provider plugins with corresponding manifests.

### Epic 7.1-7.5: Provider Plugins

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 7.1.1 | OpenAI Plugin + Manifest | TODO | k1/model_hub/plugins/openai_plugin.py [F21] + k1/config/providers/openai.manifest.yaml | Capabilities: CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH, MODERATE, AUDIO_IN, TTS, IMAGE_GEN, WEB_SEARCH, TOKEN_COUNT, CACHE_PROMPT. Models: GPT-4o, GPT-4o-mini, o3, o4-mini, text-embedding-3-small/large, DALL-E 3, whisper. API: chat.completions, embeddings, images, audio, batches. Auth: Bearer token. |
| 7.2.1 | Anthropic Plugin + Manifest | TODO | k1/model_hub/plugins/anthropic_plugin.py [F22] + k1/config/providers/anthropic.manifest.yaml | Capabilities: CHAT, TOOL_CALL, STRUCTURED, REASON, VISION, BATCH, TOKEN_COUNT, CACHE_PROMPT. Models: Claude 4 Opus, Sonnet, Haiku. API: messages, messages.batches, messages.count_tokens. Auth: x-api-key header. |
| 7.3.1 | Google Gemini Plugin + Manifest | TODO | k1/model_hub/plugins/google_plugin.py [F23] + k1/config/providers/google.manifest.yaml | Capabilities: CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, AUDIO_IN, WEB_SEARCH, TOKEN_COUNT, CACHE_PROMPT, CODE_EXEC. Models: Gemini 2.5 Pro, Flash, Embedding. API: generateContent, embedContent, countTokens. Auth: API key. |
| 7.4.1 | vLLM Plugin + Manifest | TODO | k1/model_hub/plugins/vllm_plugin.py [F24] + k1/config/providers/vllm.manifest.yaml | Capabilities: CHAT, TOOL_CALL (model-dependent), EMBED, VISION (LLaVA), TOKEN_COUNT. Models: Llama 3.3, Mistral, Qwen, LLaVA. API: OpenAI-compatible /v1/*. Auth: none (local). Placement: local_gpu. |
| 7.5.1 | Ollama Plugin + Manifest | TODO | k1/model_hub/plugins/ollama_plugin.py [F25] + k1/config/providers/ollama.manifest.yaml | Capabilities: CHAT, EMBED, VISION (LLaVA), TOKEN_COUNT. Models: Llama 3.3 8B-Q4, Phi-3, Gemma. API: /api/chat, /api/embed, /api/generate. Auth: none (local). Placement: local_cpu. |

> **Milestone 7 Done When**:
>
> - [ ] 5 provider plugins + 5 manifest YAML files
> - [ ] Each plugin implements IProviderPlugin (isinstance check passes)
> - [ ] Each manifest declares capabilities, models, costs, circuit breaker, health check
> - [ ] No hub code imports provider SDK directly (only through plugin)

---

## Milestone 8: Testing

> **Goal**: Comprehensive test coverage (~550 tests) across unit, integration, contract, invariant, lifecycle, and performance categories.

### Epic 8.1-8.6: Test Categories

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 8.1.1 | Unit tests: RequestRouter (~80 tests) | TODO | tests/k1/model_hub/services/test_request_router.py | Full pipeline happy path, budget rejection, cache hit, fallback cascade, streaming, error propagation. All via ModelHubFactory.create_for_testing(). |
| 8.1.2 | Unit tests: ProviderDispatcher (~60 tests) | TODO | tests/k1/model_hub/services/test_provider_dispatcher.py | Plugin dispatch, circuit breaker integration, rate limit integration, credential fetch, fallback chain, plugin crash isolation. |
| 8.1.3 | Unit tests: ModelSelector (~60 tests) | TODO | tests/k1/model_hub/services/test_model_selector.py | Scoring algorithm per priority tier, placement cascade, cost optimization rules, preference matching, fallback chain construction. |
| 8.1.4 | Unit tests: CapabilityRouter (~55 tests) | TODO | tests/k1/model_hub/services/test_capability_router.py | 5-step filtering, zero eligible fallback, MH-18 no hardcoded names. |
| 8.1.5 | Unit tests: CircuitBreakerManager (~55 tests) | TODO | tests/k1/model_hub/services/test_circuit_breaker_manager.py | State transitions, manifest config, cooldown timer, half-open probe, concurrent access. |
| 8.1.6 | Unit tests: BudgetEnforcer (~50 tests) | TODO | tests/k1/model_hub/services/test_budget_enforcer.py | Per-request, per-day, ALLOW/ALLOW_DEGRADED/REJECT, daily reset, cost computation. |
| 8.1.7 | Unit tests: ProviderRegistry (~50 tests) | TODO | tests/k1/model_hub/services/test_provider_registry.py | Manifest scanning, plugin loading, capability index, register/unregister. |
| 8.1.8 | Unit tests: ResponseCache (~40 tests) | TODO | tests/k1/model_hub/services/test_response_cache.py | Hit/miss, TTL, LRU eviction, skip rules, concurrent access. |
| 8.1.9 | Unit tests: NormalizationLayer (~40 tests) | TODO | tests/k1/model_hub/services/test_normalization_layer.py | Per-capability normalization, denormalization, edge cases. |
| 8.1.10 | Unit tests: RateLimiter (~35 tests) | TODO | tests/k1/model_hub/services/test_rate_limiter.py | Token bucket, headroom, overflow queue. |
| 8.1.11 | Unit tests: CostTracker (~30 tests) | TODO | tests/k1/model_hub/services/test_cost_tracker.py | Manifest cost tables, aggregation. |
| 8.1.12 | Unit tests: HealthMonitor (~25 tests) | TODO | tests/k1/model_hub/services/test_health_monitor.py | Periodic probes, state transitions. |
| 8.1.13 | Unit tests: AuditLogger (~15 tests) | TODO | tests/k1/model_hub/services/test_audit_logger.py | Full audit record, trace_id propagation. |
| 8.2.1 | Integration tests: full pipeline | TODO | tests/k1/model_hub/integration/test_full_pipeline.py | End-to-end: HubRequest -> TestProviderPlugin -> HubResponse. All services wired via ModelHubFactory.create_for_testing(). |
| 8.3.1 | Contract tests: invariant enforcement | TODO | tests/k1/model_hub/contract/test_invariants.py | Verify all 18 invariants (MH-01 through MH-18) hold under test execution. |
| 8.4.1 | Lifecycle tests | TODO | tests/k1/model_hub/lifecycle/test_lifecycle.py | INIT -> HEALTH_CHECK -> READY -> RUNNING -> DEGRADED -> SHUTDOWN. |

> **Milestone 8 Done When**:
>
> - [ ] ~550 tests across all categories
> - [ ] All tests use ModelHubFactory.create_for_testing()
> - [ ] No unittest.mock imports
> - [ ] All 18 invariants tested

---

## Milestone 9: Observability & Production Readiness

> **Goal**: Complete observability setup, performance benchmarks, chaos testing, and documentation.

### Epic 9.1-9.4: Production Readiness

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 9.1.1 | Metrics emission integration | TODO | k1/model_hub/services/*.py | Wire metric emissions at exact points in services: hub_requests_total in RequestRouter, hub_errors_total in ProviderDispatcher, hub_cache_hits_total in ResponseCache, provider_latency_ms in ProviderDispatcher, etc. |
| 9.1.2 | Structured logging (34 log events) | TODO | k1/model_hub/tracing.py | All log events use structured format: request_id, consumer_id, capability, model_id, provider_id, trace_id. Privacy: no raw prompts, no API keys in logs. |
| 9.2.1 | Performance benchmarks | TODO | tests/k1/model_hub/benchmarks/ | Hub overhead targets: request deserialization < 1ms, budget check < 1ms, capability routing < 2ms, model selection < 5ms, cache lookup < 2ms, plugin dispatch < 1ms. Total hub overhead < 12ms (excluding LLM inference). |
| 9.3.1 | Chaos tests | TODO | tests/k1/model_hub/chaos/ | Provider crash -> circuit breaker OPEN -> fallback. All providers down -> cache fallback -> template fallback. Budget exhaustion mid-request. Rate limit overflow. Manifest hot-reload with plugin crash. |
| 9.4.1 | Module documentation | TODO | k1/model_hub/README.md | Architecture overview, extensibility contract, consumer guide, provider plugin development guide. |

> **Milestone 9 Done When**:
>
> - [ ] All metric emissions in place
> - [ ] Structured logging with privacy enforcement
> - [ ] Performance benchmarks pass targets
> - [ ] Chaos tests demonstrate resilience
> - [ ] Documentation complete
