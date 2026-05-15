# K1 Model Hub — OPEN ISSUES

---

## ISSUE-M01 — `create_standalone()` still has no event-port wiring

**Severity:** High
**Location:** `factory.py:create_standalone()`

**Current behavior:**
`ModelHubFactory.create_with_ports()` and `from_config(..., ports=...)` now wire
`event_port` into `RequestRouter`, `ProviderDispatcher`, `CircuitBreakerManager`, and
`ProviderLoader`. The live kernel path uses this wiring and emits request, response,
fallback, and circuit-state events.

`ModelHubFactory.create_standalone()` still accepts no `event_port` and constructs
`RequestRouter`, `ProviderDispatcher`, and `CircuitBreakerManager` with `event_port=None`.
Standalone hubs therefore suppress all ModelHub bus publications.

Remaining related gaps:

- `config_port` is validated by `create_with_ports()` but not connected to a live
  `ConfigAdapter`.
- `state_read_port` reaches `RequestRouter` but is currently held for future routing or
  policy logic; `route()` does not read SessionState yet.

**Failure mode:** Callers using `create_standalone()` assume documented topics such as
`k1.model_hub.request.received.v1`, `k1.model_hub.response.complete.v1`, and
`k1.model_hub.circuit.state.v1` are emitted. They receive zero events unless they use
`create_with_ports()` / `from_config(..., ports=...)` or patch private fields manually.

**Fix:** Add optional `event_port`, `metrics_port`, and `state_read_port` parameters to
`create_standalone()` or route standalone construction through `create_with_ports()` with
default production adapters. Preserve the explicit no-bus mode for isolated scripts.

---

## ISSUE-M02 — `AuditLogger` is in-memory only with no eviction — unbounded growth in long sessions

**Severity:** Medium
**Location:** `services/audit_logger.py`

**Current behavior:**
`_records: List[AuditRecord]` grows indefinitely. Every request appends one record
(success or failure). No eviction policy, no max size, no TTL. `clear()` must be
called manually.

**Failure mode:** In a long-running production session (hours/days), `_records` can grow
to millions of entries consuming hundreds of MB of RAM. Python's `list.append()` is
amortized O(1) but the memory is never freed between requests.

**Fix:** Bounded deque: `_records = collections.deque(maxlen=10_000)`. Expose
`max_records` via `ModelHubConfig`. Or route audit records to the K1 bus
(`k1.model_hub.audit.v1`) and don't store in-memory at all.

---

## ISSUE-M03 — ~~`RateLimiter.acquire()` is non-atomic: RPM consumed before TPM check~~ ✅ FIXED

**Severity:** Medium → **CLOSED**
**Location:** `services/rate_limiter.py`

> **UPDATE (May 2026):** Already fixed. `rate_limiter.py:~196-218` implements a two-phase
> check-both-before-consume pattern:
> ```python
> rpm_ok = rate.rpm_bucket.available >= 1
> tpm_ok = rate.tpm_bucket.available >= tokens_needed
> if rpm_ok and tpm_ok:
>     rate.rpm_bucket.try_consume(1)
>     rate.tpm_bucket.try_consume(tokens_needed)
> ```
> The docstring confirms: "Both must succeed or neither is consumed."
> See **ISSUE-M03a** for the remaining thread-safety gap in this service.

~~**Fix:** Two-phase: check both without consuming, then consume both atomically.~~

---

## ISSUE-M04 — `ResponseCache` key uses `repr(payload)` — fragile across Python versions and field ordering

**Severity:** Medium
**Location:** `services/response_cache.py:build_cache_key()`

**Current behavior:**
```python
key_material = f"{capability.value}|{repr(payload)}|{model_id}|{temperature:.4f}"
cache_key = SHA-256(key_material.encode())
```
`repr()` output for frozen dataclasses depends on Python version and field declaration
order. Any change to a payload dataclass (new field, reordering, type annotation change)
silently invalidates all existing cache entries. Between Python 3.11 and 3.12, repr
output for nested structures can differ.

**Failure mode:** After a Python upgrade or payload schema change, all SHA-256 keys
change. The cache is effectively reset (all misses). Functionally safe, but misleading
cache metrics (hit_rate drops to 0 unexpectedly).

**Fix:** Use a stable serialization: `json.dumps(dataclasses.asdict(payload), sort_keys=True)`.
Explicitly version the key format: prefix with a schema version constant.

---

## ISSUE-M05 — ~~`CircuitBreakerManager.get_state()` HALF_OPEN probes can stack~~ ✅ FIXED

**Severity:** Medium → **CLOSED**
**Location:** `services/circuit_breaker_manager.py`

> **UPDATE (May 2026):** Already fixed. `circuit_breaker_manager.py:~148-162` already has:
> ```python
> if circuit and state == CircuitState.HALF_OPEN:
>     if circuit.half_open_in_flight:
>         return CircuitState.OPEN  # guard present
>     circuit.half_open_in_flight = True
> ```
> **Note:** OPEN_ISSUES.md (this file) referenced field as `half_open_probe_in_flight`;
> actual field name in code is `half_open_in_flight` — documentation drift only.
> See **ISSUE-M05a** for the remaining thread-safety gap in this service.

~~**Fix:** `acquire()` should check `half_open_probe_in_flight` and return `OPEN` if True.~~

---

## ISSUE-M06 — `GooglePlugin.stream_execute()` is not true async streaming — materializes all chunks in thread executor

**Severity:** Medium
**Location:** `plugins/google_plugin.py:stream_execute()`

**Current behavior:**
```python
async def stream_execute(request):
    def _do_stream():
        chunks = []
        for chunk in client.models.generate_content_stream(...):
            chunks.append(ProviderChunk(...))
        return chunks
    all_chunks = await asyncio.run_in_executor(None, _do_stream)
    for chunk in all_chunks:
        yield chunk
```
All chunks are received in the thread executor before the first `HubChunk` is yielded
to the caller. The caller's `stream_route()` is blocked for the full model response
duration before it can yield the first character.

**Failure mode:** For `REALTIME` priority requests (10s timeout) with Google/Gemini as
the provider, the caller gets no output until the full generation is complete. Any
latency advantage of streaming is eliminated. Users see no response for potentially 10s.

**Fix:** Use a `queue.Queue` bridge: the thread puts chunks into the queue; the async
generator awaits `asyncio.get_event_loop().run_in_executor` per-chunk, or use
`asyncio.Queue` with `put_nowait` from the thread. This gives true first-token delivery.

---

## ISSUE-M07 — `ProviderRegistry._rebuild_capability_index()` called on every register/unregister — O(N×M) rebuild

**Severity:** Low
**Location:** `services/provider_registry.py`

**Current behavior:**
Every `register()` or `unregister()` triggers a full rebuild of `_capability_index`
by iterating all `_providers` and all models per provider. At startup with 5 providers
and 10 models each, this is 5 rebuilds × 50 model iterations = 250 iterations at boot.

**Failure mode:** With many providers registered concurrently (e.g., `ProviderLoader`
loading 20 providers), the rebuild is triggered 20 times each rebuilding 20× context.
No functional error — only a boot-time O(N²) spike. In steady state (no hot-reload),
this is benign.

**Fix:** Incremental index update: on `register()`, iterate only the new manifest's
models and append to `_capability_index`. On `unregister()`, rebuild only affected
capability entries.

---

## ISSUE-M08 — ~~`OllamaPlugin` tool call `arguments` type mismatch~~ ✅ FIXED

**Severity:** Medium → **CLOSED**
**Location:** `plugins/ollama_plugin.py`

> **UPDATE (May 2026):** Already fixed. `ollama_plugin.py:249-267` has:
> ```python
> if isinstance(args, dict):
>     args_str = json.dumps(args)
> elif isinstance(args, str):
>     args_str = args
> ```
> Guard exists with an explicit comment. OPEN_ISSUES.md was written before the fix landed.

~~**Original description:** OpenAI and Anthropic return tool call arguments as a JSON string.
Ollama returns arguments as a parsed dict object. The Ollama plugin has a comment:
`# NOTE: Ollama returns arguments as an OBJECT (not a JSON string)`.~~

~~**Current behavior:** downstream consumers (Concierge's tool-call dispatcher, Planner's
`ToolCallResultSet`) receive a Python dict where they expect a string. FIXED — see UPDATE above.~~

---

## ISSUE-M09 — Streaming token usage is always `TokenUsage()` (zeroes) — three-layer bug

**Severity:** Low → Medium (cost tracking completely broken for streaming)
**Location:** `services/request_router.py:stream_route()`, all streaming plugins

**Current behavior — three compounding layers:**

**Root cause (Layer 3):** `request_router.py:388` hardcodes `usage=TokenUsage()` in the
done-chunk branch, discarding `chunk.metadata` entirely. Even if all plugins emitted
perfect usage, the router throws it away.

**OpenAI (Layer 2):** `openai_plugin.py:133` sends `stream_options: {include_usage: true}`
but OpenAI returns usage in a final chunk where `choices: []`. The plugin skips this chunk
with `if not choices: continue`. Usage never reaches `ProviderChunk`.

**Anthropic (Layer 2):** `anthropic_plugin.py:~158` captures `output_tokens` from `message_delta`
but misses `input_tokens` from the `message_start` event.

**Google (Layer 2):** `google_plugin.py:~240` streaming chunk loop never reads `usage_metadata`;
`_normalize_response()` (non-streaming only) handles it correctly.

**Schema gap (Layer 1):** `ProviderChunk` in `plugins/base.py:76-82` has no typed usage fields —
usage floats through `metadata: Dict[str, Any]` with no schema.

**Fix (must be done in order):**
1. Add typed `prompt_tokens: int = 0` and `completion_tokens: int = 0` to `ProviderChunk` (`base.py:76`).
2. Fix per-plugin extraction: OpenAI — remove `if not choices: continue` guard for usage-only final chunk;
   Anthropic — capture `input_tokens` from `message_start` event; Google — read `chunk.usage_metadata` on done-chunk.
3. Replace `usage=TokenUsage()` hardcode with usage read from final chunk in `request_router.py:388`.

---

## ISSUE-M10 — `ProviderLoader` skips providers with missing credentials silently — split into M10-A (log) and M10-B (bus event)

**Severity:** Low
**Location:** `loader.py:214-215`

**Current behavior:**
`loader.py:214-215` returns `("skipped", f"env var {env_var!r} not set")` on missing
credentials. A warning log is emitted, but there is no bus emission. The skip is also
visible if the caller explicitly inspects `ProviderLoadResult.skipped`.

**Additional context from code audit:**

- `ProviderRegisteredPayload` (`events.py`) has only `provider_id`, `capabilities`,
  `model_count` — no `status` or `reason` fields.
- `ProviderLoader` now accepts `event_port` for registered providers, but skipped providers
  still only appear in `ProviderLoadResult.skipped` plus a warning log.

**Failure mode:** A production deployment misconfigures `ANTHROPIC_API_KEY` environment
variable (typo, secret not mounted). Anthropic provider is silently skipped. If no other
provider supports `REASON`, `NoEligibleProviderError` is raised at runtime with no prior warning.

**Fix (M10-A — no dependencies):** Add `logger.warning("ProviderLoader: skipping %s — %s",
provider_id, reason)` at `loader.py:214`. XS fix, immediately actionable.

**Fix (M10-B):** Add `status: str = "registered"` and `reason: str = ""`
to `ProviderRegisteredPayload`; emit `TOPIC_PROVIDER_REGISTERED` with `status="skipped"`
on credential-missing skip.

**Fix:** Emit `k1.model_hub.provider.registered.v1` with `status="skipped"` and reason
when a provider is skipped. Or emit a `WARNING`-level structured log at the kernel/hub
startup boundary. At minimum, expose `ProviderLoadResult.skipped` to the kernel startup
log.

---

## ISSUE-M11 — `budget.alert.v1` exists only in diagrams; `cost_limit` is not enforced

**Severity:** Medium
**Location:** `types.py:RequestConstraints.cost_limit`, `events.py`, `services/request_router.py`

**Current behavior:**
`RequestConstraints.cost_limit` is accepted and carried through `HubRequest`, but the
router has no budget-enforcement step. `events.py` does not define
`k1.model_hub.budget.alert.v1`, and no service emits that topic.

**Failure mode:** Callers can pass `cost_limit=0.0` and still receive a normal response.
Budget dashboards subscribing to `k1.model_hub.budget.alert.v1` receive zero events.

**Fix:** Add a budget/cost guard before provider dispatch, define a typed budget-alert
payload, and decide whether budget rejection is a hard `ValidationError`, a typed
`BudgetExceededError`, or a soft fallback to cheaper provider selection.

---

## ISSUE-M03a — `RateLimiter` has no threading lock — concurrent asyncio + thread-pool can overdraft buckets

**Severity:** Medium
**Location:** `services/rate_limiter.py`

**Current behavior:**
`RateLimiter.acquire()` now correctly does a two-phase check (see ISSUE-M03 CLOSED).
However, the entire method is unprotected by a `threading.Lock`. K1's model hub uses an
asyncio event loop BUT `run_in_executor` calls can invoke `acquire()` from the thread-pool
threads concurrently with the event loop. Between the "check both" step and the "consume
both" step, another thread can slip in and consume the same tokens.

**Failure mode:** Under concurrent thread-pool usage with high token demand, two threads
simultaneously pass the availability check and both consume from the same bucket.
RPM/TPM limits can be exceeded by exactly 2× at peak concurrency.

**Fix:** Wrap the refill + check + consume block in `threading.Lock()` (not asyncio.Lock
— the method is called from both sync and async contexts).

---

## ISSUE-M05a — `CircuitBreakerManager` HALF_OPEN check-and-set lacks threading lock — TOCTOU survives the guard

**Severity:** Medium
**Location:** `services/circuit_breaker_manager.py`

**Current behavior:**
`circuit_breaker_manager.py:~148-162` now guards against double probes (see ISSUE-M05
CLOSED). However the check `if circuit.half_open_in_flight` and the set
`circuit.half_open_in_flight = True` are not atomic — no lock protects the read-modify-write.
Two threads executing `acquire()` concurrently can both read `False` before either writes
`True`.

**Failure mode:** Same stacking probe behaviour as the original ISSUE-M05, but now only
races at the read-modify-write boundary (microsecond window, not millisecond). Rare in
production but reproducible in stress tests.

**Fix:** Wrap the full HALF_OPEN transition block in `threading.Lock()`. Use the same
instance-level `_lock` already present on `CircuitBreakerState` (verify attribute) or
add one to `CircuitBreakerManager`.
