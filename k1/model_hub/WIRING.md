# K1 Model Hub — WIRING

---

## 1. Construction entry points

`ModelHubFactory` is a pure static factory. Four static methods + one async method:

| Method | Returns | When used |
|---|---|---|
| `create_standalone(config?, plugins?)` | `IModelHubPort` | Standalone / self-contained |
| `create_for_testing(overrides?)` | `Tuple[IModelHubPort, Dict[str, Any]]` | Unit tests with port overrides |
| `create_with_ports(ports, config?, plugins?)` | `IModelHubPort` | Integration or kernel wiring |
| `from_config(config, ports?, *, hub_config?, manifest_root?)` | `Tuple[IModelHubPort, ProviderLoadResult]` | Recommended production path |

`from_config` is `async` — it awaits `ProviderLoader.load(config)`. All others are synchronous.

---

## 2. `create_standalone` — 11-step construction

```
Step 1:  config = config or ModelHubConfig()
Step 2:  credential_adapter = CredentialStoreAdapter()
Step 3:  registry = ProviderRegistry(config)
Step 4a: circuit_mgr = CircuitBreakerManager(event_port=None)
Step 4b: rate_limiter = RateLimiter(default_headroom_pct=config.rate_limit_headroom_pct)
Step 5:  response_cache = ResponseCache(config)
Step 6a: health_adapter = HealthReportAdapter()
Step 6b: health_query = _DefaultHealthQuery(health_adapter)
Step 6c: capability_router = CapabilityRouter(registry, circuit_mgr, rate_limiter, health_query)
Step 6d: model_selector = ModelSelector()
Step 7:  normalization = NormalizationLayer()
Step 8:  dispatcher = ProviderDispatcher(circuit_mgr, rate_limiter, credential_adapter,
                                          plugins=plugins or {}, event_port=None)
Step 9:  router = RequestRouter(
             capability_router, model_selector, response_cache,
             normalization, dispatcher,
             audit_logger=AuditLogger(), event_port=None
         )
Step 10: hub = _HubCore(router, registry, health_adapter)
Step 11: return hub
```

`metrics_port` and `event_port` are NOT wired in `create_standalone` — the caller must
attach private fields manually or use `create_with_ports` / `from_config(..., ports=...)`.
This is the remaining ISSUE-M01 gap: standalone hubs suppress ModelHub bus events.

---

## 3. `from_config` — production path

```python
async def from_config(
    config: ProviderConfig,
    ports: Dict[str, Any] | None,
    *,
    hub_config: ModelHubConfig | None,
    manifest_root: Path | None
) -> Tuple[IModelHubPort, ProviderLoadResult]:
```

1. `hub = create_standalone(hub_config)` or `create_with_ports(ports, hub_config)` if ports given
2. `loader = ProviderLoader(hub, manifest_root=manifest_root or _DEFAULT_MANIFEST_ROOT, event_port=ports.get("event_port"))`
3. `result = await loader.load(config)` — never raises; inspect `result.failed`
4. Returns `(hub, result)`

With `ports` provided, `create_with_ports` wires `event_port` into `RequestRouter`,
`ProviderDispatcher`, and `CircuitBreakerManager`; `metrics_port` and `state_read_port`
also reach `RequestRouter`. `health_port` becomes the `_HubCore.health()` adapter.
`config_port` is still only validated, not connected to a live `ConfigAdapter`.

---

## 4. `ProviderLoader.load()` — per-entry sequence

`_DEFAULT_MANIFEST_ROOT = Path(__file__).resolve().parents[1] / "config" / "providers"`

For each `entry: ProviderEntry` in `ProviderConfig.providers`:

```
_load_one(entry):
  1. Resolve manifest_path:
        entry.manifest_path
        or f"{manifest_root}/{entry.provider_id}.manifest.yaml"
  2. load_manifest(manifest_path) → ProviderManifest (YAML parse + validation)
  3. Resolve plugin_class:
        entry.plugin_class  (override)
        or manifest.plugin_class  (dotted import path e.g. "k1.model_hub.plugins.openai_plugin.OpenAIPlugin")
     → importlib.import_module + getattr
  4. plugin = PluginCls(); await plugin.initialize(manifest)
  5. Credential resolution:
        api_key = os.environ.get(manifest.auth.credential_key, "")
        if auth.type != "none" and not api_key:
            return ("skipped", f"no credential for {manifest.auth.credential_key}")
        if api_key and hasattr(plugin, "set_api_key"):
            plugin.set_api_key(api_key)
  6. hub.register_plugin(manifest, plugin)  ← Step 10 below
      publish TOPIC_PROVIDER_REGISTERED if event_port is wired
Returns ("registered"|"skipped"|"failed", detail_str)
```

`ProviderLoadResult` aggregates: `registered: List[str]`, `skipped: List[str]`, `failed: List[str]`.
`load()` accumulates all results — partial success is normal.

---

## 5. `hub.register_plugin()` — dual seam (P0.1 shim)

`_HubCore.register_plugin(manifest, plugin)` performs TWO writes:

```python
# Seam 1: update ProviderRegistry capability index
registry.register(manifest, plugin)

# Seam 2: install plugin into ProviderDispatcher's plugin map
dispatcher.register_plugin(manifest.provider_id, plugin)

# Seam 3: install provider circuit-breaker config
dispatcher._circuit_mgr.register_provider(manifest.provider_id, manifest.circuit_breaker)

# Seam 4 (shutdown): _HubCore.shutdown() reaches into
#   self._router._dispatcher._plugins to close all plugins
```

This private-attribute seam is tagged for cleanup in P2.3. Registry and Dispatcher
currently maintain independent maps (ProviderInfo vs IProviderPlugin).

---

## 6. Adapter construction and what they wrap

| Adapter | Constructor | Wraps | Key translation |
|---|---|---|---|
| `CredentialStoreAdapter(overrides={})` | — | Environment variables | Lookup order: `overrides[pid]` → `os.environ["MH_KEY_{PID.upper()}"]` → `""` |
| `EventBusAdapter(bus?, event_loop?)` | — | K1 `IBus` or in-memory fan-out | Standalone: direct `_handlers` dict. Production: JSON `Envelope` encode/decode; sync bus handler bridges async via `asyncio.run_coroutine_threadsafe(coro, event_loop)` |
| `HealthReportAdapter()` | — | In-memory `Dict[str, HealthStatus]` | Aggregates: UNHEALTHY beats DEGRADED beats HEALTHY |
| `LLMRequestBusAdapter(hub)` | — | `IModelHubPort` | Thin delegate; logs and re-raises |
| `ConfigAdapter(initial={})` | — | In-memory dict | `reload(new_dict)` diffs keys → fires watcher callbacks |
| `PrometheusAdapter()` | — | In-memory accumulator | `metric_name{labels}` keyed sum; placeholder for real prometheus_client |
| `SessionStateReadAdapter(data={})` | — | `Dict[str, Any]` | Section lookup, no I/O (dev/test) |
| `SessionStateProdAdapter(manager)` | — | `SessionStateManager` (local Protocol) | `manager.get_section(name)` → `to_dict()` or `get_metadata()`; `SectionNotFoundError` → section omitted silently |
| `BusEnvelopeDeserializer(adapter, bus, loop)` | — | K1 IBus | Subscribes `TOPIC_HUB_EXECUTE`; JSON decode → `HubRequest` → `adapter.execute()` → JSON → `TOPIC_HUB_RESPONSE`; sync bus handler bridges async via `run_coroutine_threadsafe` |

---

## 7. `RequestRouter` internal call graph

```
route(request):
    ├── _validate(request)          → ValidationError if trace_id empty or unknown cap
    ├── event: request.received     → includes request_id, trace_id, consumer_id, capability
    ├── metrics.emit(active+1)
    ├── capability_router.route(cap, constraints, token_estimate)
    │       ├── registry.get_providers_for_capability(cap)    O(1) index
    │       ├── [filter model-level capability]
    │       ├── [filter CB != OPEN]
    │       ├── [filter RL has_capacity]
    │       └── [filter health != UNHEALTHY]  → List[EligibleProvider]
    ├── model_selector.select(eligible, request)
    │       ├── [score: preference + placement + health]
    │       ├── [avoid_providers exclusion]
    │       └── ModelChoice(primary, fallbacks[:2])
    ├── response_cache.get(cache_key)       → HubResponse on hit (emit response.complete cache_hit=True)
    ├── normalization.normalize(request, provider_id)
    │       └── _CAPABILITY_EXTRACTORS[cap](payload) → NormalizedRequest
    ├── dispatcher.dispatch(normalized, primary_id, fallback_chain=fallbacks)
    │       ├── for each provider in [primary] + fallbacks:
    │       │     circuit_mgr.acquire(pid)
    │       │     rate_limiter.acquire(pid, token_estimate)
    │       │     credential = await credential_port.get_key(pid)
    │       │     plugin.execute(normalized)       [try, retry once on failure]
    │       │     circuit_mgr.record_success/failure(pid)
    │       └── DispatchResult(response, provider_id, fallback_used)
    ├── normalization.denormalize(provider_response, request, ...)
    ├── response_cache.put(cache_key, hub_response)   [if should_cache]
    ├── audit_logger.log(request, response)
    ├── event: request.completed    → legacy topic kept for compatibility
    ├── event: response.complete    → documented completion topic
    └── metrics.emit(tokens, latency, active-1) → HubResponse
```

Failure paths publish `k1.model_hub.request.failed.v1`. Provider fallback paths publish
`provider.failure.v1` and `fallback.triggered.v1` from `ProviderDispatcher` before the
router publishes the final completion event.

---

## 8. `NormalizationLayer` capability dispatch table

`_CAPABILITY_EXTRACTORS: Dict[CapabilityType, Callable[[Any], Dict]]` — 15 entries.
Each callable receives the typed payload and returns a `dict` with keys:
`messages, system_prompt, tools, tool_choice, output_schema, stream, max_tokens, temperature, extra`.

Key extractions:

| Capability | Key fields extracted |
|---|---|
| `CHAT` | `messages, system_prompt` |
| `TOOL_CALL` | `messages, tools, tool_choice, parallel_tool_calls → extra.parallel_tool_calls` |
| `STRUCTURED` | `messages, output_schema, strict → extra.strict` |
| `REASON` | `messages, reasoning_effort → extra.reasoning_effort, include_thinking → extra.include_thinking` |
| `EMBED` | `texts → extra.texts, dimensions → extra.dimensions, encoding_format → extra.encoding_format` |
| `VISION` | `messages, image_inputs → extra.image_inputs, detail → extra.detail` |

`denormalize._build_result(cap, raw)` converts raw `ProviderResponse` fields to typed result objects.
The Concierge `_unwrap_response()` helper depends on these exact typed result objects.

---

## 9. `ProviderDispatcher` dispatch algorithm

```
dispatch(request, provider_id, fallback_chain, token_estimate):
    attempt_chain = [provider_id] + fallback_chain[:_MAX_FALLBACK_DEPTH-1]
    last_error = None
    for pid in attempt_chain:
        cb_state = circuit_mgr.acquire(pid)
        if cb_state == OPEN: continue
        rl_decision = rate_limiter.acquire(pid, token_estimate)
        if not rl_decision.allowed: continue
        try:
            key = await credential_port.get_key(pid)
            plugin.set_api_key(key)   [if supported]
            response = await plugin.execute(request)
            circuit_mgr.record_success(pid)
            return DispatchResult(response, pid, fallback_used=(pid != provider_id))
        except Exception as exc:
            circuit_mgr.record_failure(pid, str(exc))
            last_error = exc
            if attempt == 0:   # retry once on primary
                retry attempt on same pid
        if next fallback exists:
            publish provider.failure.v1
            publish fallback.triggered.v1
    if last_error: raise last_error
    raise NoEligibleProviderError(...)
```

Stream path (`stream()`) follows the same outer logic but calls `plugin.stream_execute(request)`.
No cache on streaming path.

---

## 10. `CircuitBreakerManager` wiring

`CircuitBreakerManager` is shared between `CapabilityRouter` (read: `get_state()`) and
`ProviderDispatcher` (write: `acquire()`, `record_success()`, `record_failure()`).

Per-provider `_CircuitBreakerState` internal class:

```python
state: CircuitState = CLOSED
failure_timestamps: deque[float]   # sliding window
consecutive_successes: int = 0
half_open_probe_in_flight: bool = False
last_opened_at: Optional[float]
config: CircuitBreakerConfig
```

`get_state(pid)` auto-transitions `OPEN → HALF_OPEN` if `time.time() - last_opened_at > cooldown_s`.
This is a lazy transition — no background timer. When constructed with `event_port`, every
state transition publishes `k1.model_hub.circuit.state.v1` asynchronously from the active loop.

---

## 11. `ResponseCache` key construction

```python
cache_key = SHA-256(f"{capability.value}|{repr(payload)}|{model_id}|{temperature:.4f}")
```

`repr(payload)` is used (not JSON). This means key stability depends on Python's `repr`
output for frozen dataclasses, which is deterministic within a single Python version.

Skip rules (`should_cache` returns `False`):

- `capability in {TOOL_CALL, BATCH, MODERATE}`
- `streaming=True`
- `constraints.temperature > 0.9`

---

## 12. `BusEnvelopeDeserializer` — async bridge

```
Bus (sync callback) ──► _on_execute_message(topic, raw_bytes)
                              │
                              ▼ JSON decode → Envelope
                              ▼ _build_hub_request(envelope) → HubRequest
                              │
                              │  # bridge sync→async
                              ├─ asyncio.run_coroutine_threadsafe(
                              │      _dispatch(request), loop
                              │  ).result(timeout=constraints.timeout_ms/1000)
                              │
                              ▼ JSON encode HubResponse → Envelope
                              ▼ bus.publish(TOPIC_HUB_RESPONSE, envelope_bytes)
```

`_build_hub_request(envelope)` calls the public `build_payload(envelope, capability)` function
(this is the function imported by `LLMGatewayAdapter` in the planner module — see
ISSUE-P02 in planner OPEN_ISSUES.md regarding the private import path).

---

## 13. `ModelHubConfig` schema

```python
@dataclass(frozen=True)
class ModelHubConfig:
    max_concurrent_requests: int = 50
    cache_max_entries: int = 1000       # MH-09
    cache_ttl_s: int = 300              # MH-09 default 5 min
    realtime_timeout_ms: int = 10_000  # MH-15
    interactive_timeout_ms: int = 30_000
    background_timeout_ms: int = 60_000
    rate_limit_headroom_pct: float = 0.80  # MH-12
    health_check_interval_s: int = 30      # MH-14
    manifest_dir: str = "k1/config/providers"
    shutdown_grace_period_ms: int = 10_000
```

`from_dict(data)` validates no unknown keys; raises `ValueError` on unknown key.
`__post_init__` validates all numeric ranges.

---

## 14. K1 inter-component dependencies (imports)

| Dependency | Module imported | Imported by | Purpose |
|---|---|---|---|
| `IBus, SubscriptionHandle` | `k1.bus.ports.bus` | `bus_envelope_deserializer.py`, `event_bus_adapter.py` | Bus subscription and transport |
| `Envelope, PayloadFormat` | `k1.bus.envelope` | `bus_envelope_deserializer.py` | Wire format |
| `SessionStateManager` | local `_ISessionStateManager` Protocol (avoids import) | `session_state_prod.py` | Duck-typed via Protocol to avoid circular dep |

Model Hub does NOT import from: `k1.concierge`, `k1.planner`, `k1.orchestrator`,
`k1.fabric`, `k1.sessionstate` directly. All dependencies are injected via ports.

---

## 15. `_HubCore.shutdown()` sequence

```python
async def shutdown():
    plugins = list(self._router._dispatcher._plugins.values())
    await asyncio.gather(
        *[asyncio.wait_for(p.close(), timeout=_PLUGIN_CLOSE_TIMEOUT_S) for p in plugins],
        return_exceptions=True   # timeout / exceptions are non-fatal
    )
```

`_PLUGIN_CLOSE_TIMEOUT_S = 5.0` seconds per plugin. All plugins closed concurrently.
Errors or timeouts on close are logged and suppressed.

---

## 16. Event subscription graph

Model Hub PRODUCES events but does not subscribe to `k1.model_hub.*` internally.
The `BusEnvelopeDeserializer` subscribes to `k1.model_hub.execute.v1` (inbound requests).
`ConfigAdapter` may subscribe to `k1.model_hub.config_update.v1` if wired by caller.

```
BusEnvelopeDeserializer
    └── bus.subscribe(["k1.model_hub.execute.v1"], _on_execute_message)

Produced by RequestRouter (via event_port.publish):
    k1.model_hub.request.received.v1
    k1.model_hub.response.complete.v1
    k1.model_hub.request.completed.v1   # legacy compatibility topic
    k1.model_hub.request.failed.v1      # legacy compatibility topic

Produced by ProviderDispatcher:
    k1.model_hub.provider.failure.v1
    k1.model_hub.fallback.triggered.v1

Produced by CircuitBreakerManager:
    k1.model_hub.circuit.state.v1

Produced by ProviderLoader (via hub._event_port if wired):
    k1.model_hub.provider.registered.v1
```

Declared but not emitted by the current request path: `request.routed.v1`, `cache.hit.v1`,
`capability.available.v1`, and `provider.health.v1`. `k1.model_hub.budget.alert.v1`
is not declared in `events.py` and has no enforcer in this revision.
