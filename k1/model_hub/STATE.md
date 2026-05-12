# K1 Model Hub — STATE

---

## 1. Summary: what state lives where

Model Hub is primarily stateless per-request but owns several shared mutable structures:

| Component | Mutable state | Lifetime |
|---|---|---|
| `ProviderRegistry` | `_providers`, `_capability_index` | Lifetime of hub instance; grows on `register()`, shrinks on `unregister()` |
| `CircuitBreakerManager` | Per-provider `_CircuitBreakerState` | Lifetime of hub; mutated on every dispatch |
| `RateLimiter` | Per-provider `_BucketState` (RPM + TPM token buckets) | Lifetime of hub; refilled continuously |
| `ResponseCache` | `_cache: OrderedDict`, `_total_hits`, `_total_misses` | Lifetime of hub; bounded LRU (max 1000 entries) |
| `AuditLogger` | `_records: List[AuditRecord]` | Lifetime of hub; unbounded growth (cleared manually) |
| `RequestRouter` | `_active_requests: int` | Per-request; +1 on start, -1 in `finally` |
| `HealthReportAdapter` | `_statuses: Dict[str, HealthStatus]` | Lifetime of hub; mutated by component callbacks |
| `EventBusAdapter` (standalone) | `_handlers: Dict[str, List[Callable]]` | Lifetime of hub |

---

## 2. `ProviderRegistry` mutable state

```
_providers: Dict[str, Tuple[ProviderManifest, IProviderPlugin, ProviderInfo]]
_capability_index: Dict[CapabilityType, List[ProviderInfo]]
```

Mutated by:
- `register(manifest, plugin)` → inserts into `_providers`, rebuilds `_capability_index`
- `unregister(provider_id)` → removes from `_providers`, rebuilds `_capability_index`

`_rebuild_capability_index()` is called on every register/unregister — O(N providers × M models).
Reads via `get_providers_for_capability(cap)` are O(1) index lookups but NOT thread-safe
(no lock; relies on GIL for dict reads).

---

## 3. `CircuitBreakerManager` — per-provider state machine

**`_CircuitBreakerState` fields (internal class):**

| Field | Type | Meaning |
|---|---|---|
| `state` | `CircuitState` | CLOSED / OPEN / HALF_OPEN |
| `failure_timestamps` | `deque[float]` | Sliding window of failure times (pruned on each failure) |
| `consecutive_successes` | `int` | Incremented by `record_success()`; cleared on state change |
| `half_open_probe_in_flight` | `bool` | True when `acquire()` marks a HALF_OPEN probe |
| `last_opened_at` | `Optional[float]` | Timestamp when last transitioned to OPEN |
| `config` | `CircuitBreakerConfig` | Per-provider thresholds |

**Transition trigger table:**

| Trigger | From state | To state | Condition |
|---|---|---|---|
| `record_failure()` | CLOSED | OPEN | `len(failure_timestamps) >= failure_threshold` after pruning |
| `record_failure()` | HALF_OPEN | OPEN | always (probe failed) |
| `record_success()` | HALF_OPEN | CLOSED | always |
| `get_state()` | OPEN | HALF_OPEN | `time.time() - last_opened_at > cooldown_s` |

**Lazy transitions:** `OPEN → HALF_OPEN` only happens when `get_state()` is called.
There is NO background timer or periodic check. A provider can remain OPEN indefinitely
if no request asks for it.

`transitions: List[CircuitTransition]` — append-only log of every state change, kept
for monitoring/debugging.

---

## 4. `RateLimiter` — per-provider token bucket state

**`_BucketState` fields (internal class):**

| Field | Type | Meaning |
|---|---|---|
| `rpm_tokens` | `float` | Current RPM bucket fill (≤ `rpm_capacity`) |
| `tpm_tokens` | `float` | Current TPM bucket fill (≤ `tpm_capacity`) |
| `last_refill_time` | `float` | `time.time()` of last refill |
| `rpm_capacity` | `float` | `floor(rpm_limit × headroom_pct)` |
| `tpm_capacity` | `float` | `floor(tpm_limit × headroom_pct)` |
| `rpm_refill_rate` | `float` | `rpm_capacity / 60.0` tokens/sec |
| `tpm_refill_rate` | `float` | `tpm_capacity / 60.0` tokens/sec |

**Refill algorithm (called in `has_capacity` and `acquire`):**
```
elapsed = now - last_refill_time
rpm_tokens = min(rpm_capacity, rpm_tokens + elapsed * rpm_refill_rate)
tpm_tokens = min(tpm_capacity, tpm_tokens + elapsed * tpm_refill_rate)
last_refill_time = now
```

**Known issue (non-atomic 2-phase consume):** `acquire()` consumes from RPM bucket first;
if TPM is insufficient, RPM token is NOT refunded. This results in minor RPM undercounting
under TPM pressure.

---

## 5. `ResponseCache` mutable state

| Field | Type | Mutation |
|---|---|---|
| `_cache` | `OrderedDict[str, CacheEntry]` | `get()` moves to end (LRU); `put()` removes+re-inserts; `popitem(last=False)` on eviction |
| `_total_hits` | `int` | Incremented on cache hit |
| `_total_misses` | `int` | Incremented on cache miss |

**Thread safety:** `threading.Lock` acquired on all `get()`, `put()`, `invalidate()`, `clear()`.
**Eviction:** lazy on `put()` — if `len >= max_entries`, evict oldest until under limit.
**TTL:** lazy on `get()` — if `entry.expires_at < time.time()`, treat as miss (not removed immediately).

---

## 6. `AuditLogger` mutable state

| Field | Type | Mutation |
|---|---|---|
| `_records` | `List[AuditRecord]` | `log()` and `log_error()` append; `clear()` resets to `[]` |

`_records` grows without bound. No auto-eviction. In production the audit log is expected
to be periodically drained or sampled externally. `AuditRecord` includes: `request_id`,
`trace_id`, `consumer_id`, `capability`, `provider_id`, `model_id`, `prompt_tokens`,
`completion_tokens`, `cost_usd`, `latency_ms`, `cache_hit`, `fallback_used`, `error`.

---

## 7. `RequestRouter` request-scoped state

`_active_requests: int` — incremented at request entry, decremented in `finally`.
This is a gauge used for monitoring (`model_hub.active_requests`). It is NOT
thread-safe (no lock) — race is accepted as a monitoring approximation.

No other per-request mutable state in `RequestRouter`. All other state lives in
the service objects it delegates to.

---

## 8. `_HubCore` component lifecycle

```
NOT_REGISTERED  (plugin has no entry in registry + dispatcher)
        │
        └── hub.register_plugin(manifest, plugin)
                │
                ▼
        REGISTERED (capabilities in index; plugin in dispatcher map)
                │
                └── hub.unregister_plugin(provider_id)  [if ever called]
                        │
                        ▼
                NOT_REGISTERED

hub.shutdown():
    await all_plugins.close() [concurrently, 5s timeout each]
    → each plugin transitions to CLOSED state (plugin-internal)
```

---

## 9. Per-provider runtime state summary

For each registered provider, the following state is maintained:

```
CircuitBreakerManager._states[provider_id]:
    state: CLOSED | OPEN | HALF_OPEN
    failure_timestamps: deque (sliding 60s window)
    half_open_probe_in_flight: bool

RateLimiter._buckets[provider_id]:
    rpm_tokens: float (0..rpm_capacity)
    tpm_tokens: float (0..tpm_capacity)
    last_refill_time: float

ProviderRegistry._providers[provider_id]:
    (ProviderManifest, IProviderPlugin, ProviderInfo)

ProviderDispatcher._plugins[provider_id]:
    IProviderPlugin
```

These are all in-memory, process-local, and lost on restart.

---

## 10. Streaming state (per-call local, not shared)

`stream_route()` accumulates streaming state locally per call:

| Variable | Type | Purpose |
|---|---|---|
| `accumulated_text` | `str` | Concatenated content across all chunks |
| `accumulated_tool_calls` | `List[ToolCallResult]` | Accumulated tool call deltas |
| `first_chunk_received` | `bool` | Tracks whether any chunk has arrived |

These are local to the `stream_route()` coroutine — not shared across calls.
The final chunk (`done=True`) builds `ResponseMetadata` from accumulated values.

---

## 11. Plugin internal state

Each plugin maintains its own aiohttp session:

| Plugin | Session field | Notes |
|---|---|---|
| `OpenAIPlugin` | `_session: aiohttp.ClientSession` | Recreated if closed; total timeout 120s |
| `AnthropicPlugin` | `_session: aiohttp.ClientSession` | Same |
| `OllamaPlugin` | `_session: aiohttp.ClientSession` | Same |
| `VLLMPlugin` | `_session: aiohttp.ClientSession` | Same |
| `GooglePlugin` | `_client: genai.Client` | Created lazily on first `_ensure_genai()` call |

All plugins store `_manifest: ProviderManifest` (set in `initialize()`).
All plugins store `_api_key: str` (set via `set_api_key()` during ProviderLoader credential step, or per-request via `ProviderDispatcher.dispatch()`).

---

## 12. Concurrency model summary

| Layer | Model | Mechanism |
|---|---|---|
| Request execution | Async per-request coroutine | `await route(request)` |
| Cache reads/writes | Thread-safe | `threading.Lock` on all operations |
| Circuit breaker reads | Lock-free (GIL) | `dict` access; mutation assumed single-threaded async |
| Rate limiter reads | Lock-free (GIL) | Same |
| Registry reads | Lock-free (GIL) | `get_providers_for_capability` is dict lookup |
| Audit log append | Lock-free (GIL) | `list.append()` is GIL-protected |
| Google plugin | Thread pool | `asyncio.run_in_executor(None, ...)` |
| EventBusAdapter (production) | Thread-safe bridge | `asyncio.run_coroutine_threadsafe` |
| BusEnvelopeDeserializer | Thread-safe bridge | `asyncio.run_coroutine_threadsafe` |
| Plugin sessions | Per-instance | Not shared across concurrent requests to same plugin |
