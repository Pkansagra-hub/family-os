# Epic 1.1: Bus Audit — Complete Findings

**Date:** 2026-04-11 (original) · 2026-04-18 (Phase 6 hardening update)
**Status:** ✅ COMPLETE — All 6 issues audited; Phase 6 hardening landed on `bus-hardening` (HEAD `7164a26`)
**Verdict:** Bus is **PRODUCTION READY** — zero stubs, full dual-backend (Python+Rust), rich middleware, causal ordering, async dispatch + retry/DLQ + durability

---

## Phase 6 Hardening — Status

Branch `bus-hardening` cut from `POC_Migration`. Three commits land P6.1–P6.14; P6.10 remains open.

| ID | Scope | Status | Commit | Notes |
|----|-------|--------|--------|-------|
| P6.0 | Branch cut from POC_Migration | ✅ Done | — | `bus-hardening` |
| P6.1 | Async bridge swallowed handler errors → counter + log | ✅ Done | `44006c8` | `_async_handler_errors` counter; `Future.add_done_callback` |
| P6.2 | RustBusAdapter bypassed middleware on publish | ✅ Done | `44006c8` | Middleware runs before Rust dispatch; `None` drops |
| P6.3 | RustBusAdapter `drain()` non-advancing | ✅ Done | `44006c8` | `_drain_offset` slot; advances on read |
| P6.4 | `flush()` semantics on `IBus` | ✅ Done | `44006c8` | New `flush(timeout_ms=5000) -> bool` on `IBus`; Rust returns `True` (sync) |
| P6.5 | Async dispatch path for slow handlers | ✅ Done | `47c7f10` | `LocalBus(async_dispatch=True)`, `_AsyncSubscription` daemon thread + `LocalMailbox` |
| P6.6 | Retry policy resolver per topic | ✅ Done | `47c7f10` | `retry_resolver(topic) -> RetryPolicy \| None` |
| P6.7 | Dead-letter callback after retry exhaustion | ✅ Done | `47c7f10` | `dlq_callback(envelope, exc, attempts)` |
| P6.8 | Memory-writer turn-complete topic rename | ✅ Done | `47c7f10` | `TOPIC_TURN_COMPLETE = "k1.session.turn.complete.v1"` (distinct from concierge `…turn.completed.v1`) |
| P6.9 | SessionBusAdapter prefix flatten for `sessionstate.*` | ✅ Done | `47c7f10` | `_FLATTEN_PREFIXES = ("sessionstate.",)`; no double-nesting |
| P6.10 | k1.model_hub STRICT rule in `bus.yaml` | ⚠️ **OPEN** | — | Not present in `k1/config/bus.yaml`; falls to default RELAXED |
| P6.11 | Schema-validation mode (permissive/strict) | ✅ Done | `7164a26` | `TopicValidationMiddleware(schema_validation_mode=...)`, `SchemaValidationError` |
| P6.12 | Idempotency middleware | ✅ Done | `7164a26` | `IdempotencyMiddleware` (new file, stdlib only, opt-in) |
| P6.13 | Durable topics + SQLite outbox + replay | ✅ Done | `7164a26` | `BusOutbox` (WAL), `LocalBus(durable_topics=…, outbox=…)`, `replay_durable_topics()` |
| P6.14 | End-to-end Phase 6 test suite | ✅ Done | `7164a26` | 40 new tests (schema 11 / idem 9 / durability 13 / e2e 8); bus suite 1108 passing |

**Open item:** P6.10 — add `k1.model_hub` to STRICT in [k1/config/bus.yaml](k1/config/bus.yaml). All other Phase 6 risks called out by this audit are resolved.

---

## Summary Verdict

| Aspect | Status | Notes |
|--------|--------|-------|
| Port definitions | ✅ COMPLETE | 3 protocols, all `@runtime_checkable`, well-typed |
| Envelope types | ✅ COMPLETE | 12-field frozen dataclass, V1 JSON + V2 FlatBuffers |
| Factory | ✅ COMPLETE | 4 methods, Python/Rust auto-selection, env override |
| Impl (LocalBus) | ✅ COMPLETE | ~610 LOC, TopicTrie, RWLock, middleware chain |
| Impl (Mailbox) | ✅ COMPLETE | ~475 LOC, WFQ priority queuing, bounded |
| Impl (Rust) | ✅ COMPLETE | RustBusAdapter + RustMailboxRouterAdapter via PyO3 |
| Adapters | ✅ COMPLETE | SessionBusAdapter + FabricBusAdapter, real logic |
| Middleware | ✅ COMPLETE | Tracing + Metrics + TopicValidation, all real |
| Timing | ✅ COMPLETE | ~990 LOC, causal ordering + gap buffering |
| Config | ✅ COMPLETE | YAML loader with defaults |
| Docs | ✅ COMPLETE | ARCHITECTURE.md + README.md + Mermaid diagram |

**Total LOC:** ~3,500+ across bus package
**Stubs found:** ZERO — every file is real, production implementation

---

## Issue 1.1.1: Port Definitions — IBus, IMailbox, IMailboxRouter ✅

### IBus (`k1/bus/ports/bus.py`)

```
Type:     Protocol, @runtime_checkable
Alias:    BusHandler = Callable[[Envelope], None]
```

| Method | Signature | Return |
|--------|-----------|--------|
| `publish` | `(self, envelope: Envelope) -> None` | None |
| `subscribe` | `(self, pattern: str, handler: BusHandler, *, consumer_id: str \| None = None) -> SubscriptionHandle` | SubscriptionHandle |
| `unsubscribe` | `(self, handle: SubscriptionHandle) -> bool` | bool |
| `flush` | `(self, timeout_ms: int = 5000) -> bool` | bool |

**SubscriptionHandle** (frozen dataclass): `subscription_id: str`, `pattern: str`

**Phase 6 additions** (commit `44006c8` for `flush`; `47c7f10` for `consumer_id`):

- `flush(timeout_ms)` drains async-dispatch worker mailboxes; returns `True` on full drain, `False` on timeout. Rust adapter is sync and always returns `True`. See [k1/bus/ports/bus.py](k1/bus/ports/bus.py).
- `subscribe(..., consumer_id=…)` enables at-least-once delivery via the durable-outbox path; `LocalBus` wraps the handler in `_acking_handler` so the outbox `ack` only fires on successful return. Required when the topic is in `durable_topics`.

**Topic model:** Dot-separated hierarchical strings (e.g. `k1.capability.completed.v1`). Supports exact match, `*` (single-segment wildcard), `>` (greedy trailing wildcard) via TopicTrie.

### IMailbox (`k1/bus/ports/mailbox.py`)

```
Type:     Protocol, @runtime_checkable
```

| Method | Signature | Return |
|--------|-----------|--------|
| `receive` | `(self, timeout_ms: int = 0) -> Optional[Envelope]` | Optional[Envelope] |
| `pending` | `(self) -> int` | int |

No `send` or `peek`. Send-side is `IMailboxRouter.deliver()`.

### IMailboxRouter (`k1/bus/ports/mailbox.py`)

```
Type:     Protocol, @runtime_checkable
```

| Method | Signature | Return |
|--------|-----------|--------|
| `deliver` | `(self, actor_id: str, envelope: Envelope) -> None` | None (raises BackpressureError, UnknownActorError) |
| `register` | `(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox` | IMailbox |
| `unregister` | `(self, actor_id: str) -> bool` | bool |
| `registered_actors` | `(self) -> list[str]` | list[str] |

**MailboxConfig** (frozen dataclass): `capacity: int = 256`, `priority_wfq: bool = True`

**Verdict 1.1.1:** ✅ All three port protocols are clean, minimal, `@runtime_checkable`. No issues found.

---

## Issue 1.1.2: BusFactory ✅

### BusFactory (`k1/bus/factory.py`)

```
Type:     Static factory (no state, all @staticmethod)
Backend:  "auto" | "rust" | "python" — env K1_BUS_BACKEND overrides
```

| Factory Method | Key Params | Returns |
|---------------|------------|---------|
| `create_local` | `capture, timing_chain, middleware, backend="auto"` | `LocalBus \| RustBusAdapter` |
| `create_local_ordered` | `config, timeout_ms=5000, capture, middleware, backend="python"` | `LocalBus` (always Python — TimingChain requires it) |
| `create_for_testing` | `ordered, middleware, backend="auto"` | `LocalBus \| RustBusAdapter` |
| `create_mailbox_router` | `backend="auto"` | `LocalMailboxRouter \| RustMailboxRouterAdapter` |

**Key observations:**

- `create_local_ordered` defaults to Python-only because TimingChain is Python-side
- Auto-detection: tries `import k1_bus_core` → Rust if available, else Python
- `_to_chain()` helper normalizes `list[Middleware]` → `MiddlewareChain`
- No async — all synchronous construction

**Phase 6 additions** ([k1/bus/factory.py](k1/bus/factory.py), commits `47c7f10`/`7164a26`): `create_local()` accepts new kwargs `async_dispatch`, `subscription_mailbox_capacity`, `retry_resolver`, `dlq_callback`, `outbox`, `durable_topics`. If any of `timing_chain`, `async_dispatch`, or `outbox` is set, the factory forces the Python backend; `backend="rust"` with Rust missing now raises `ImportError` (was a silent fallback).

**Verdict 1.1.2:** ✅ Factory is complete. 4 methods cover all bus creation scenarios. Backend selection is clean.

---

## Issue 1.1.3: SessionBusAdapter ✅

### SessionBusAdapter (`k1/bus/adapters/session_adapter.py`, ~235 LOC)

```
Inherits:  IEventPort (ABC from k1.sessionstate.ports.events)
Injects:   bus: LocalBus (concrete type, NOT IBus protocol)
Purpose:   Adapts LocalBus → SessionState's IEventPort interface
```

| Method | Signature | Notes |
|--------|-----------|-------|
| `emit` | `(self, event_type: str, payload: Any) -> None` | Maps `event_type` → `"k1.session.{event_type}"` topic |
| `subscribe` | `(self, event_type: str, handler: Callable[[Any], None]) -> str` | Returns `str` subscription_id (not Handle) |
| `unsubscribe` | `(self, subscription_id: str) -> bool` | Looks up internal handle dict |
| `is_connected` | `@property -> bool` | `not self._bus.closed` |
| `bus` | `@property -> LocalBus` | Exposes underlying bus |
| `active_subscriptions` | `@property -> int` | Count |

**Translation layer:**

- `event_type` string → `"k1.session.{event_type}"` bus topic by default
- **P6.9 (commit `47c7f10`):** `_FLATTEN_PREFIXES = ("sessionstate.",)` — event types already prefixed with `sessionstate.` are mapped to `k1.sessionstate.X` (no double-nesting under `k1.session.`); all other event types still get `k1.session.X`. See `_map_topic` in [k1/bus/adapters/session_adapter.py](k1/bus/adapters/session_adapter.py).
- `Any` payload → JSON `{"payload": value}` → bytes
- Reverse on subscribe: bytes → JSON → unwrap `"payload"` key → handler

**Important:** Does NOT create a per-session bus — wraps the SINGLE shared bus. Session isolation is via topic prefix `k1.session.`.

**Verdict 1.1.3:** ✅ Real implementation. Correctly adapts bytes-based bus to SessionState's `IEventPort`. One concern: takes `LocalBus` concrete type, not `IBus` protocol — tight coupling but acceptable since factory controls creation.

---

## Issue 1.1.4: FabricBusAdapter ✅

### FabricBusAdapter (`k1/bus/adapters/fabric_adapter.py`, ~245 LOC)

```
Inherits:  Nothing (structural subtyping)
Injects:   bus: LocalBus (concrete type)
Purpose:   DUAL-ROLE — satisfies both IEventPort AND IDeltaBusPort for Fabric
```

| Method | Signature | Port Satisfied |
|--------|-----------|----------------|
| `emit` | `(self, topic: str, payload: Dict[str, Any]) -> None` | IEventPort |
| `subscribe` | `(self, topic: str, handler: Callable[[str, Dict[str, Any]], None]) -> FabricSubscriptionHandle` | IEventPort |
| `unsubscribe` | `(self, handle: FabricSubscriptionHandle) -> bool` | IEventPort |
| `emit_delta` | `(self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]) -> None` | IDeltaBusPort |
| `bus` | `@property -> LocalBus` | — |

**Dual-role details:**

- **IEventPort side:** General Fabric event pub/sub, `Dict[str, Any]` ↔ JSON bytes
- **IDeltaBusPort side:** `emit_delta()` publishes to `k1.agent.{agent_id}.delta.v1` with `Priority.REALTIME`
- Preserves `cognitive_trace_id` from payload dict into Envelope header

**Imports from Fabric:**

- `k1.fabric.ports.delta_bus.DeltaPayload`
- `k1.fabric.ports.event_port.SubscriptionHandle` (as `FabricSubscriptionHandle`)

**Verdict 1.1.4:** ✅ Real dual-role implementation. Confirmed both event and delta pathways. Clean JSON serialization at boundary.

---

## Issue 1.1.5: TracingMiddleware ✅

### TracingMiddleware (`k1/bus/middleware/tracing.py`, ~133 LOC)

```
Implements: Middleware protocol (structural)
Dependency: opentelemetry (optional, gracefully degrades)
```

| Method | Signature | Behavior |
|--------|-----------|----------|
| `process` | `(self, envelope: Envelope) -> Optional[Envelope]` | Always returns envelope (never drops) |

**What it does:** Creates an OpenTelemetry span named `"bus.publish {topic}"` with these attributes:

| Span Attribute | Source | Conditional? |
|----------------|--------|-------------|
| `bus.topic` | `envelope.topic` | Always |
| `bus.envelope_id` | `envelope.envelope_id` | Always |
| `bus.sequence` | `envelope.sequence` | Always |
| `bus.priority` | `envelope.priority` | Always |
| `bus.parent_id` | `envelope.parent_id` | Always |
| `bus.cognitive_trace_id` | `envelope.cognitive_trace_id` | Only if truthy |
| `bus.session_id` | `envelope.session_id` | Only if truthy |

**CRITICAL FINDING:** TracingMiddleware does **NOT stamp** `session_id` or `cognitive_trace_id` onto envelopes. It only **reads** them for tracing. The publisher must set these fields when creating the Envelope. This is correct — envelope is frozen (immutable), so middleware can't modify it.

**Verdict 1.1.5:** ✅ Real implementation with OpenTelemetry. Read-only tracing (correct for frozen envelopes). Graceful degradation when OTel not installed.

---

## Issue 1.1.6: MetricsMiddleware + TopicValidation ✅

### MetricsMiddleware (`k1/bus/middleware/metrics.py`, ~175 LOC)

```
Implements: Middleware protocol (structural)
Dependency: prometheus_client (optional, gracefully degrades)
```

| Metric | Type | Labels |
|--------|------|--------|
| `k1_bus_envelopes_total` | Counter | `topic_prefix`, `priority` |
| `k1_bus_envelope_latency_seconds` | Histogram | `topic_prefix` |

- **Topic prefix:** First 2 segments (e.g. `"k1.capability"`) to avoid cardinality explosion
- **Histogram buckets:** 100μs → 1s (9 buckets)
- **Priority labels:** urgent, realtime, interactive, background
- Always returns envelope (never drops)

### TopicValidationMiddleware (`k1/bus/middleware/topic_validation.py`, ~240 LOC)

```
Implements: Middleware protocol (structural)
Companion:  TopicRegistry
```

**TopicRegistry** — 3-tier topic validation:

1. **Exact:** `"k1.capability.completed.v1"`
2. **Prefix:** `"k1.agent."` (matches anything starting with prefix)
3. **Wildcard:** `"k1.agent.*.delta.*"` (fnmatch glob)

| Method | Signature | Notes |
|--------|-----------|-------|
| `register` | `(self, topic: str, validator: PayloadValidator \| None = None) -> None` | P6.11: optional validator |
| `register_prefix` | `(self, prefix: str, validator: PayloadValidator \| None = None) -> None` | P6.11: optional validator |
| `lookup_validator` | `(self, topic: str) -> PayloadValidator \| None` | P6.11: exact → longest-prefix → first-wildcard fnmatch |
| `is_known` | `(self, topic: str) -> bool` | |
| `unregister` | `(self, topic: str) -> bool` | Also drops associated validator |
| `clear` | `(self) -> None` | Drops all validators |

**Phase 6.11 — schema validation (commit `7164a26`)**, [k1/bus/middleware/topic_validation.py](k1/bus/middleware/topic_validation.py):

- `TopicValidationMiddleware(schema_validation_mode: str = "permissive")` — modes are `"permissive"` (warn + pass) and `"strict"` (raise `SchemaValidationError` and drop the envelope by returning `None`).
- New type alias: `PayloadValidator = Callable[[bytes, Envelope], None]` — a validator raises to indicate failure.
- New exception: `SchemaValidationError(ValueError)`.
- New counters on the middleware: `schema_violation_count`, `schema_drop_count` (in addition to the original soft-validation warn counter).
- New slot on `TopicRegistry`: `_validators` (mapping by exact / prefix / wildcard buckets).

**Topic-known validation** remains SOFT (warn-only) for backward compat; only schema validation can drop in `"strict"` mode.

**Verdict 1.1.6:** ✅ Both are real, production implementations. MetricsMiddleware has proper Prometheus histograms. TopicValidation is now two-layered (soft topic-known + opt-in strict schema). Both gracefully degrade when deps missing.

---

## Issue 1.1.7 (P6.12): IdempotencyMiddleware ✅ NEW

### IdempotencyMiddleware ([k1/bus/middleware/idempotency.py](k1/bus/middleware/idempotency.py)) — new file, commit `7164a26`

```
Implements: Middleware protocol (structural)
Dependency: stdlib only (collections.OrderedDict, time.monotonic)
Opt-in:     Not added to default chain; callers wire it explicitly
```

| Constructor | Default |
|-------------|---------|
| `IdempotencyMiddleware(max_entries=10_000, ttl_s=300.0)` | LRU + TTL |

- **Key:** `(envelope.topic, envelope.request_id)`. Empty `request_id` bypasses the cache entirely (counted in `no_key_count`).
- **Storage:** `OrderedDict` LRU bounded by `max_entries`; per-entry expiry by `time.monotonic()` against `ttl_s`. Opportunistic GC on access.
- **Drop semantics:** Duplicate hit → middleware returns `None`, envelope is dropped by `MiddlewareChain`.
- **Counters:** `drop_count`, `pass_count`, `no_key_count`, `cache_size`.

**Verdict 1.1.7:** ✅ Real, stdlib-only, opt-in middleware. 9 dedicated tests in `tests/k1/bus/middleware/test_idempotency.py`.

---

## Envelope Details

### Envelope (`k1/bus/envelope/envelope.py`)

Frozen dataclass with **12 fields**:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `topic` | `str` | `""` | Dot-separated hierarchical topic |
| `priority` | `int` | `Priority.INTERACTIVE (2)` | 4 levels: URGENT/REALTIME/INTERACTIVE/BACKGROUND |
| `envelope_id` | `int` | `0` | Global monotonic ID (stamped by bus) |
| `sequence` | `int` | `0` | Per-topic monotonic sequence (stamped by bus) |
| `cognitive_trace_id` | `str` | `""` | Cross-component trace correlation |
| `session_id` | `str` | `""` | Session scope |
| `request_id` | `str` | `""` | Request correlation |
| `parent_id` | `int` | `0` | Causal parent envelope_id |
| `created_ns` | `int` | `0` | Nanosecond timestamp (stamped by bus) |
| `payload` | `bytes` | `b""` | Opaque payload (bus never reads) |
| `ttl_ms` | `int` | `0` | Time-to-live (0 = no expiry) |
| `payload_format` | `int` | `PayloadFormat.OPAQUE (0)` | JSON=1, MSGPACK=2 |

**Serialization:** V2 FlatBuffers (default) or V1 JSON (fallback). Env var `K1_ENVELOPE_FORMAT` selects.

### Priority Enum

| Level | Int | Weight (WFQ) |
|-------|-----|-------------|
| URGENT | 0 | 4× |
| REALTIME | 1 | 3× |
| INTERACTIVE | 2 | 2× |
| BACKGROUND | 3 | 1× |

### DeliveryMode Enum

| Mode | Int | Behavior |
|------|-----|----------|
| STRICT | 0 | Buffer on gap, enforce causal ordering |
| RELAXED | 1 | Deliver immediately, log reorders |
| BEST_EFFORT | 2 | Deliver immediately, droppable under pressure |

---

## Concrete Implementation Details

### LocalBus ([k1/bus/impl/local_bus.py](k1/bus/impl/local_bus.py), ~610 LOC + Phase 6 additions)

**Publish happy path:**

1. Validate envelope
2. Stamp: `envelope_id` (global monotonic), `sequence` (per-topic), `created_ns`
3. Run `MiddlewareChain.process()` — drop if returns None
4. Capture (if enabled)
5. **P6.13:** if `topic in durable_topics`, append the stamped envelope to `outbox` before dispatch
6. TopicTrie match → collect handlers
7. Dispatch to handlers (error-isolated per handler) — sync inline OR (P6.5) push to per-subscription `_AsyncSubscription` mailbox
8. Optional: TimingChain for ordering enforcement

**Concurrency:** `_ReadWriteLock` — publish = read lock, subscribe/unsubscribe = write lock. Zero contention between concurrent publishes.

**Phase 6 additions on `LocalBus`** (commits `47c7f10`, `7164a26`):

- New `__init__` kwargs: `async_dispatch: bool`, `subscription_mailbox_capacity: int`, `retry_resolver: Callable[[str], RetryPolicy | None] | None`, `dlq_callback: Callable[[Envelope, BaseException, int], None] | None`, `outbox: BusOutbox | None`, `durable_topics: Iterable[str] | None`.
- New `__slots__`: `_async_dispatch`, `_async_capacity`, `_async_subs`, `_async_subs_lock`, `_retry_resolver`, `_dlq_callback`, `_outbox`, `_durable_topics`, `_durable_consumers`, `_durable_consumers_lock`.
- New methods: `flush(timeout_ms=5000) -> bool` (P6.4), `replay_durable_topics(*, consumer_id=None)` (P6.13).
- New properties: `durable_topics: frozenset[str]`, `outbox: BusOutbox | None`.
- `subscribe(..., consumer_id=...)`: keyword-only; when set on a durable topic, the handler is wrapped in `_acking_handler` so the outbox `ack` only fires on a successful return (at-least-once semantics).
- Inner class `_AsyncSubscription` (P6.5): spawns a daemon thread `bus-sub-{id}` consuming from a `LocalMailbox`; the retry loop calls `retry_resolver(topic)` and, on exhaustion, invokes `dlq_callback(envelope, exc, attempts)`.

**`BusStats` ([k1/bus/impl/local_bus.py L952](k1/bus/impl/local_bus.py#L952))** — new fields: `mailbox_full_drops`, `mailbox_high_water_mark`, `async_handler_retries`, `async_handler_dlq`.

### TopicTrie (`k1/bus/impl/topic_trie.py`, ~260 LOC)

Generic radix trie for O(k) topic matching where k = segment count.

- Supports: exact, `*` (single wildcard), `>` (greedy wildcard)
- O(1) removal by subscription_id via flat index
- Tombstoning with lazy compaction

### LocalMailbox + LocalMailboxRouter (`k1/bus/impl/local_mailbox.py`, ~475 LOC)

- Bounded queue per actor with optional WFQ (Weighted Fair Queuing across 4 priority sub-queues)
- `BackpressureError` on full, `UnknownActorError` on unregistered actor
- `Condition.wait(timeout)` for blocking receive

### RustBusAdapter ([k1/bus/impl/rust_bus_adapter.py](k1/bus/impl/rust_bus_adapter.py))

**Phase 6 fixes (commit `44006c8`):**

- **P6.2:** `publish()` now runs the middleware chain *before* Rust dispatch; a `None` return from middleware drops the envelope (previously bypassed).
- **P6.3:** new `_drain_offset` slot; `drain()` returns the unread tail and advances the offset (previously re-returned the full backlog).
- **P6.4:** `flush()` returns `True` immediately (Rust dispatch is synchronous).

### BusOutbox ([k1/bus/outbox/sqlite_outbox.py](k1/bus/outbox/sqlite_outbox.py)) — NEW (P6.13, commit `7164a26`)

SQLite-backed durable buffer for at-least-once topics. Opened in WAL mode: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`.

**Schema:**

- `envelopes(envelope_id PK, topic, payload BLOB, priority, created_ns, request_id, session_id, deleted)` + index `(topic, envelope_id)`
- `acks((consumer_id, topic) PK, last_acked_envelope_id)`

**API:**

| Method | Purpose |
|--------|---------|
| `append(envelope)` | `INSERT OR IGNORE` by `envelope_id` |
| `ack(consumer_id, topic, envelope_id)` | UPSERT with `MAX(...)` so acks are monotonic |
| `unacked(consumer_id, topic) -> Iterator[OutboxRecord]` | Replay backlog |
| `prune_acked(retain_below=0)` | Tombstone old rows |
| `last_envelope_id() / count(topic=None)` | Diagnostics |
| `close()` | Close connection |

`OutboxRecord` is a frozen dataclass with `to_envelope()`. `LocalBus.replay_durable_topics(*, consumer_id=None)` iterates `unacked()` for each `consumer_id` registered against a durable topic and re-publishes through the normal dispatch path (re-running middleware and respecting retry/DLQ).

---

## Timing Subsystem

### TimingChain (`k1/bus/timing/timing_chain.py`, ~710 LOC)

Two ordering enforcement mechanisms:

1. **CausalTracker** — buffers envelopes whose `parent_id` hasn't been delivered yet
2. **GapBuffer** — buffers envelopes when per-topic sequence gaps detected

**Default rules** (16 topic prefixes, from [k1/config/bus.yaml](k1/config/bus.yaml)):

- **STRICT (12):** `k1.capability`, `k1.orchestration`, `k1.planner`, `k1.hil`, `k1.hitl`, `k1.response`, `k1.session`, `k1.agent`, `k1.internal`, `k1.tool`, `k1.arbiter`, `k1.backpool`
- **RELAXED (4):** `k1.affect`, `k1.constraint`, `k1.proactive`, `k1.workflow`
- **BEST_EFFORT (2):** `k1.k0.sse`, `k1.fabric.learning`
- **Default for unmapped prefixes:** RELAXED
- **⚠️ Open (P6.10):** `k1.model_hub` is **not** present in `bus.yaml` and falls through to the RELAXED default. Adding it under STRICT is the single remaining Phase 6 item.

Safety nets: 5000ms timeout sweep, buffer overflow (50K causal / 10K gap per-topic) → force-release oldest 10%.

### Topic renames (Phase 6.8 / 6.9, commit `47c7f10`)

- **P6.8** — [k1/memory_writer/events.py](k1/memory_writer/events.py): `TOPIC_TURN_COMPLETE = "k1.session.turn.complete.v1"`; `TurnDispatcher.TOPIC` matches. **Distinct** from concierge's `TOPIC_TURN_COMPLETED = "k1.session.turn.completed.v1"` (past-tense; separate event with separate consumers).
- **P6.9** — [k1/bus/adapters/session_adapter.py](k1/bus/adapters/session_adapter.py): `_FLATTEN_PREFIXES = ("sessionstate.",)`; `_map_topic` flattens `sessionstate.X` → `k1.sessionstate.X` (avoids the previous `k1.session.sessionstate.X` double-nesting). All other event types continue to map to `k1.session.X`.

---

## Bus Subscriber Map (from Architecture Diagram)

| Component | Publishes | Subscribes | Mailbox |
|-----------|-----------|------------|---------|
| **Concierge** | `k1.response.*`, `k1.affect.*` | `k1.capability.completed.*`, `k1.hil.*`, `k1.k0.sse.*`, `k1.agent.*.delta.*`, `k1.*.delta.*` | `concierge` |
| **Orchestrator** | `k1.orchestration.*`, `k1.constraint.*`, `k1.*.delta.*` | `k1.planner.plan.ready.*`, `k1.capability.completed.*` | `orchestrator` |
| **Fabric** | `k1.capability.*`, `k1.fabric.learning.signal.*`, `k1.agent.{id}.delta.*` | (via FabricBusAdapter) | `fabric` |
| **Planner** | `k1.planner.plan.ready.*`, `k1.hil.clarification.*`, `k1.planner.delta.*` | `k1.hil.*_response.*` | `planner` |
| **SessionState** | `k1.session.*` | `k1.session.mutation.*` | (via SessionBusAdapter) |
| **K0 Bridge** | `k1.k0.sse.received.*` | — | — |
| **Sub-Agents** | `k1.agent.{id}.delta.*` | — | `agent.{id}` |

---

## Concurrency Model

**Important discovery: Bus core is fully synchronous/threaded. No asyncio anywhere.**

- `threading.Lock`, `threading.RLock`, `threading.Condition` throughout
- Default handler dispatch is synchronous on publisher's thread
- `LocalMailbox.receive()` blocks via `Condition.wait(timeout)` — NOT `await`
- No `async def`, no `await`, no `asyncio` in any bus code

**Phase 6.5 addition — opt-in async dispatch:** when `LocalBus(async_dispatch=True)`, each subscription gets a daemon thread (`bus-sub-{id}`) with its own bounded `LocalMailbox`. Publishes enqueue and return; the worker thread invokes the handler with retry (`retry_resolver`) and DLQ (`dlq_callback`). `flush(timeout_ms)` drains those mailboxes. The publisher thread is *still* sync — this just decouples slow handlers from publishers, it does not introduce asyncio.

**`async_bridge.py` fix (P6.1, commit `44006c8`):** the bridge previously swallowed handler exceptions silently when adapting sync handlers via `Future`. It now installs `Future.add_done_callback` to log the exception and increment a new `_async_handler_errors` counter.

**Implication for kernel wiring:** If the rest of K1 is async (asyncio event loop), bus operations will still need to be called from sync context or wrapped in `asyncio.to_thread()` / `run_in_executor()`. Async dispatch only changes *handler* execution context, not the publisher API.

---

## Wiring Requirements for Kernel Bootstrap

Based on this audit, here's what the kernel needs to do with Bus:

### Tier-1 (Shared) — `KernelService.startup()`

1. **Create shared bus:** `BusFactory.create_local(middleware=chain)` where chain = `[TracingMiddleware(), MetricsMiddleware(), TopicValidationMiddleware(registry)]`
2. **Create mailbox router:** `BusFactory.create_mailbox_router()`
3. **Register shared actors:** `router.register("orchestrator")`, `router.register("planner")`, `router.register("fabric")`
4. **Populate TopicRegistry:** Register all known topic prefixes from the subscriber map above

### Tier-2 (Per-Session) — `KernelService.create_session()`

1. **Create per-session bus:** `BusFactory.create_local(middleware=chain)` (separate instance per session)
2. **Register session actors:** `router.register("concierge")`, `router.register(f"agent.{id}")` per dynamic agent
3. **Create SessionBusAdapter:** `SessionBusAdapter(session_bus)` → inject as `IEventPort` into SessionState
4. **Create FabricBusAdapter:** `FabricBusAdapter(shared_bus)` → inject as `IEventPort + IDeltaBusPort` into Fabric
5. **Wire bus subscriptions:** Each component subscribes to its topics per the subscriber map

### Open Questions for MS-2

| # | Question | Impact |
|---|----------|--------|
| Q1 | Shared bus vs per-session bus — or both? | Architecture decision |
| Q2 | Sync bus + async kernel — how to bridge? `asyncio.to_thread()`? | Performance + correctness |
| Q3 | Should `SessionBusAdapter` take `IBus` protocol instead of `LocalBus` concrete? | Testability |
| Q4 | Is one FabricBusAdapter shared or per-session? | Memory + isolation |
| Q5 | How does MailboxRouter relate to per-session scope? | Actor lifecycle |

---

## 09_wiring_plan.md Status Updates

| Issue | Status | Verdict |
|-------|--------|---------|
| 1.1.1 | ✅ | All 3 ports complete, `@runtime_checkable`, well-typed; `flush()` added (P6.4) |
| 1.1.2 | ✅ | Factory complete, 4 methods, dual-backend; new P6 kwargs (`async_dispatch`, `outbox`, `durable_topics`, `retry_resolver`, `dlq_callback`) |
| 1.1.3 | ✅ | SessionBusAdapter real (~235 LOC), adapts IEventPort; P6.9 prefix flatten for `sessionstate.*` |
| 1.1.4 | ✅ | FabricBusAdapter real (~245 LOC), dual-role IEventPort + IDeltaBusPort |
| 1.1.5 | ✅ | TracingMiddleware real (~133 LOC), OpenTelemetry, read-only (does NOT stamp) |
| 1.1.6 | ✅ | MetricsMiddleware real (~175 LOC); TopicValidation real (~240 LOC) — soft topic-known + opt-in strict schema (P6.11) |
| 1.1.7 | ✅ | IdempotencyMiddleware (P6.12) — stdlib-only, opt-in, LRU+TTL |
| 1.1.8 | ✅ | BusOutbox + durable topics + replay (P6.13) |
| 1.1.9 | ✅ | Phase 6 E2E suite (P6.14) — 40 new tests; bus suite 1108 passing |
| P6.10 | ⚠️ Open | `k1.model_hub` STRICT rule still missing from `k1/config/bus.yaml` |
