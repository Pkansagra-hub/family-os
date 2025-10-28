got it. you already have stubs and your **k1/contracts** is the source of truth. here’s the **exact folder-by-folder order** with **what code to write in each file** (short, surgical). copy/paste this checklist and go straight down the list.

---

# Implementation Order: “folder 1, then code; folder 2, then code…”

## FOLDER 1 — `k1/l5_infrastructure/observability/`

**Only depend on `k1/contracts/*` types for envelopes/trace ids.**

* `metrics.py`

  * Implement thin wrappers over your metrics backend: `counter(name, labels)`, `gauge(...)`, `histogram(...)`.
  * Prebind hot labels (`tenant`, `priority`, `topic`) to avoid per-call dict allocs.
* `tracing.py`

  * Context propagation with `contextvars`.
  * `Tracer.start_span(name, attrs={}) → AsyncContextManager[Span]` that attaches `cognitive_trace_id` from envelope (from contracts).
* `logging.py`

  * JSON logger: fields `ts, level, module, trace_id, span_id, tenant, msg`.
* `k0_client.py`

  * Stub that buffers metrics/logs/traces and NO-OPs on network (flag-gated).

**Exit checks**

* span across `await` preserves trace id.
* histograms record: `*_latency_seconds`.

---

## FOLDER 2 — `k1/l5_infrastructure/resilience/`

* `circuit_fsm.py`

  * Closed/Open/HalfOpen with thresholds (fail count, cooldown).
* `call_wrapper.py`

  * `async def call_wrapper(fn, *, timeout, retries, circuit_id):`
  * timeouts via `asyncio.wait_for`, retry w/ jitter, circuit decisions from `circuit_fsm`.
* `circuit_breaker_manager.py`

  * registry keyed by `circuit_id`, emits metrics `circuit_state`.

**Exit checks**

* circuit trips, half-open probes, metrics/log lines present.

---

## FOLDER 3 — `k1/l5_infrastructure/serialization/`

* `serializer.py`

  * `dumps/loads` for pydantic models from **k1/contracts** only.
* `deserializer.py`

  * strict schema validation, raises `SchemaError`.
* `buffer_pool.py`

  * simple bytearray pool to reduce allocs on hot paths.
* `alignment.py`, `zero_copy.py`, `string_dedup.py`

  * keep as helpers; wire only where measured beneficial.

**Exit checks**

* JSON round-trip parity with contracts’ models.
* size & latency metrics emitted.

---

## FOLDER 4 — `k1/l5_infrastructure/caching/`

* `kv_cache.py` (already stubbed) — **implement interface shim to contracts.KVCache if present**.
* `in_memory_cache.py`

  * LRU + TTL + max_bytes; async API.
* `persistent_cache.py`

  * Stub to local file/SQLite (feature-flag OFF).
* `cache_warmer.py`, `connection_pool.py`, `kv_cache_local.py`, `cache_integration.py`

  * minimal pass to satisfy imports; log “not enabled”.

**Exit checks**

* `hit/miss/evict` counters, `get p95 < 0.2ms` locally.

---

## FOLDER 5 — `k1/l5_infrastructure/event_bus/`

* **IMPORTANT**: use `k1/contracts/events.py` for Envelope/Topic types.
* `schemas.py`

  * registry `register(topic: str, model: BaseModel)`.
* `event_bus.py`

  * In-proc pub/sub: `publish(topic, envelope)`, `subscribe(topic, cb)`, `start/stop`.
  * Validate envelope via `schemas.py`; wrap subscriber execution with `resilience.call_wrapper`.
* `subscribers.py`

  * Provide `Subscription` handle with `unsubscribe()`; add sample echo handler guarded by feature flag.

**Exit checks**

* publish→dispatch p95 < 2ms; invalid schema increments `bus_schema_error_total`.

---

## FOLDER 6 — `k1/l5_infrastructure/scheduling/`

*(you listed scheduling twice; keep **this** as the single source)*

* `weighted_queue.py`

  * 3 priorities (HIGH/NORM/LOW), configurable weights, no starvation.
* `scheduler.py`

  * `enqueue(task)`, `run(workers:int)`; drains by weights; yields to Event Bus (`task.accepted`).

**Exit checks**

* fairness ε-bounded across 100k ops; `queue_depth{priority}` metrics.

---

## FOLDER 7 — `k1/l5_infrastructure/rate_limiting/`

* `token_bucket.py`

  * per-tenant/user/route keys; monotonic clock refill.
* `rate_limiter.py`

  * `check_allow(key, cost=1) → bool, reason`.
* `limiter.py`

  * glue for multi-bucket strategies (global + per-tenant).
* `config.yml`

  * defaults: burst, refill rate; load with sane fallbacks.

**Exit checks**

* drift <2% over 60s steady load; `rl_allow_total/deny_total` present.

---

## FOLDER 8 — `k1/l5_infrastructure/backpressure/`

* `watermark_tracker.py`

  * tracks queue depths & latencies; emits states `WARN/DEGRADE/REJECT` with hysteresis.
* `watermark_checker.py`

  * fast read-only query for admission pipeline.
* `cascade_coordinator.py`, `cascade_actions.py`

  * on `DEGRADE`: reduce batch size; on `REJECT`: signal admission short-circuit.
* `global_limits_enforcer.py`

  * optional cap across tenants (flag).
* `voice_pipeline_monitor.py`, `privacy_override.py`, `metrics.py`

  * implement minimal monitoring + counters.

**Exit checks**

* no flapping under oscillatory load; transitions logged once per state change.

---

## FOLDER 9 — `k1/l5_infrastructure/admission/`

* `task_validator.py`

  * structural & policy-lite checks using **contracts.Task** schemas.
* `policies.py`

  * GREEN-band only initially; return `POLICY_DENY` when violated.
* `admission_controller.py`

  * Pipeline: `validate → rate_limit → backpressure → policy → enqueue(scheduler)`.
  * Decision codes: `OK | RL_DENY | BP_REJECT | POLICY_DENY`.

**Exit checks**

* p95 < 10ms with rate limiter/backpressure enabled; decision metrics by `reason`.

---

## FOLDER 10 — `k1/l5_infrastructure/storage/`

* `tier_manager.py`

  * interfaces: `put/get/delete` with tier hint from **contracts.StorageTier**.
* `cold_tier.py`

  * file blob store (path hashing), background compaction stub.
* `lifecycle_manager.py`

  * promotions/demotions timers; metrics only at first.

**Exit checks**

* hot path (in-mem via caching) p95 < 1ms; promotions run without blocking.

---

## FOLDER 11 — `k1/l5_infrastructure/modules/`

* `plugin_discovery.py`

  * scan entry points / folders; ignore on errors.
* `plugin_loader.py`

  * lifecycle `load/start/health/stop`; isolation: catch & log exceptions, never crash kernel.

**Exit checks**

* two dummy plugins load; disable/enable doesn’t affect callers.

---

## FOLDER 12 — `k1/l5_infrastructure/placement/`

* `capability_matcher.py`

  * read device caps (CPU/GPU/NPU), RAM, thermal hints; produce `PlacementAdvice`.
* `placement_policy.py`

  * local-only enforcement OFF (advice only).
* `cascade_engine.py`, `circuit_breaker.py`, `provider_adapters.py`, `cost_tracker.py`, `metrics.py`

  * stub except: compute & emit advice metrics.

**Exit checks**

* advice generated; no routing side effects unless `PLACEMENT_ENFORCE=1`.

---

## FOLDER 13 — `k1/l5_infrastructure/thermal/`

* `sensors.py`

  * adapters to OS/driver; provide simulator if not available.
* `device_capability.py`

  * normalize readings → `ThermalState: COOL/NORMAL/HOT/CRITICAL`.
* `placement_manager.py`

  * feeds `placement` with thermal state (advice).
* `metrics.py`

  * state durations, transition counters.

**Exit checks**

* state machine behaves; transitions have hysteresis.

---

## FOLDER 14 — `k1/l5_infrastructure/extensions/`

* `extension_registry.py`

  * typed registration points: `metrics_exporter`, `trace_exporter`, `security_policy`, `placement_strategy`, etc.
* `config_provider.py`

  * read env/INI/YAML with precedence.
* `metrics_exporter.py`, `trace_exporter.py`, `log_handler.py`

  * default in-proc exporters; K0 forwarding is **flagged**.
* `security_policy.py`, `placement_strategy.py`, `thermal_policy.py`, `storage_tier.py`, `performance_optimizer.py`, `circuit_breaker_strategy.py`

  * supply defaults that delegate to the implemented modules.

**Exit checks**

* disabling any single extension doesn’t break layer; safe defaults apply.

---

# Wiring (last mile)

* `__init__.py` at layer root:

  * export factory funcs: `make_admission()`, `make_scheduler()`, `make_event_bus()`, etc.
  * **No** global singletons; DI all dependencies.
* Remove duplicate `scheduling/` if you had a second copy elsewhere. This one is canonical.

---

# What not to do

* do **not** rebuild contracts in L5. import from `k1/contracts/...` only.
* do **not** add cross-layer deps (L5 must not import L4+).
* do **not** enable external buses/storage until all in-proc passes are green (use feature flags).

---

# Quick CI targets to add

```
make fmt         # black/isort
make lint        # ruff + mypy --strict
make test        # unit + integration
make perf        # runs microbench; fails if budgets breached
```

---

if you want, i’ll spit out **starter implementations** for Folder 1–3 (observability, resilience, serialization) exactly matching this plan so you can paste and move.
