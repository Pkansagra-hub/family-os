# K1 Bus — Architecture Document

> **Component**: Bus (Event Transport Layer)
> **Location**: `k1/bus/`
> **Diagram**: `k1/bus/k1_bus_core.mmd`
> **Status**: Production-ready (V1 Python + V2 Rust optional)
> **Scan Date**: 2025-07-05
> **Epic**: E-0.1 (MS-0 Phase A)

---

## Table of Contents

1. [Port Surface](#1-port-surface)
2. [Internal Architecture](#2-internal-architecture)
3. [Factory & Configuration](#3-factory--configuration)
4. [Cross-Component Connections](#4-cross-component-connections)
5. [Test Surface](#5-test-surface)
6. [Spec vs Code Delta](#6-spec-vs-code-delta)

---

## 1. Port Surface

### 1.1 Protocol Inventory

| Protocol | File | Lines | Type | Methods |
|----------|------|-------|------|---------|
| **IBus** | `ports/bus.py` | 91–144 | `@runtime_checkable Protocol` | `publish`, `subscribe`, `unsubscribe` |
| **IMailbox** | `ports/mailbox.py` | 115–147 | `@runtime_checkable Protocol` | `receive`, `pending` |
| **IMailboxRouter** | `ports/mailbox.py` | 155–231 | `@runtime_checkable Protocol` | `deliver`, `register`, `unregister`, `registered_actors` |

### 1.2 IBus Protocol

| Method | Signature | Async | Notes |
|--------|-----------|-------|-------|
| `publish` | `(self, envelope: Envelope) → None` | Sync | Stamps envelope_id (global mono), sequence (per-topic mono), created_ns. Dispatches to matching handlers. Fire-and-forget. |
| `subscribe` | `(self, pattern: str, handler: BusHandler) → SubscriptionHandle` | Sync | Pattern can be exact or wildcard (`k1.capability.*`). Returns opaque handle. |
| `unsubscribe` | `(self, handle: SubscriptionHandle) → bool` | Sync | Returns True if found and removed. |

**Type Aliases:**

- `BusHandler` = `Callable[[Envelope], None]` (line 62–65)
- `SubscriptionHandle` = frozen dataclass with `subscription_id: str, pattern: str` (line 31–48)

**Concurrency**: Thread-safe. Publish concurrent OK. Subscribe/unsubscribe exclusive.
**Error Handling**: Handler exceptions caught by bus, logged, never propagate.

### 1.3 IMailbox Protocol

| Method | Signature | Async | Notes |
|--------|-----------|-------|-------|
| `receive` | `(self, timeout_ms: int = 0) → Optional[Envelope]` | Sync | Blocking with timeout. 0 = non-blocking. |
| `pending` | `(self) → int` | Sync | Number of envelopes in queue. |

**Priority Levels**: URGENT > REALTIME > INTERACTIVE > BACKGROUND (strict priority V1).

### 1.4 IMailboxRouter Protocol

| Method | Signature | Async | Raises | Notes |
|--------|-----------|-------|--------|-------|
| `deliver` | `(self, actor_id: str, envelope: Envelope) → None` | Sync | `UnknownActorError`, `BackpressureError` | Route to actor mailbox. |
| `register` | `(self, actor_id: str, config: Optional[MailboxConfig] = None) → IMailbox` | Sync | `ValueError` | Create mailbox. Raises if already registered. |
| `unregister` | `(self, actor_id: str) → bool` | Sync | — | Remove actor + close mailbox. |
| `registered_actors` | `(self) → list[str]` | Sync | — | List all active actor IDs. |

**Config**: `MailboxConfig` (frozen dataclass, line 72–87) — `capacity: int = 256`, `priority_wfq: bool = True`
**Exceptions**: `BackpressureError(actor_id, capacity)`, `UnknownActorError(actor_id)`

### 1.5 Ports Exports (`ports/__init__.py`)

```python
__all__ = [
    "IBus", "SubscriptionHandle",
    "IMailbox", "IMailboxRouter", "MailboxConfig",
    "BackpressureError", "UnknownActorError",
]
```

### 1.6 Protocol Conformance Matrix

| Implementation | IBus | IMailbox | IMailboxRouter | Fabric IEventPort | SS IEventPort |
|----------------|:----:|:-------:|:--------------:|:-----------------:|:------------:|
| LocalBus | ✅ (Protocol) | — | — | — | — |
| LocalMailbox | — | ✅ (Protocol) | — | — | — |
| LocalMailboxRouter | — | — | ✅ (Protocol) | — | — |
| FabricBusAdapter | — | — | — | ✅ (structural) | — |
| SessionBusAdapter | — | — | — | — | ✅ (ABC inherit) |
| RustBusAdapter | ✅ (API surface) | — | — | — | — |
| RustMailboxAdapter | — | ✅ (API surface) | — | — | — |
| RustMailboxRouterAdapter | — | — | ✅ (API surface) | — | — |

---

## 2. Internal Architecture

### 2.1 Class Inventory

| Class | File | Lines | Responsibility | Mutable State | Thread Safety |
|-------|------|-------|----------------|---------------|---------------|
| **LocalBus** | `impl/local_bus.py` | 242–570 | Production IBus; trie match, WFQ dispatch | `_trie`, `_rw_lock`, `_seq_gen`, `_id_gen`, `_stats`, `_captured`, `_timing_chain`, `_middleware` | RWLock (publish=read, sub/unsub=write) |
| **_SequenceGenerator** | `impl/local_bus.py` | 86–145 | Per-topic monotonic uint64 counters | `_counters`, `_locks`, `_global_lock` | Per-topic locks (zero cross-topic contention) |
| **_EnvelopeIdGenerator** | `impl/local_bus.py` | 148–173 | Global monotonic uint64 counter | `_counter`, `_lock` | Single lock (atomic increment) |
| **_ReadWriteLock** | `impl/local_bus.py` | 176–223 | Read-heavy lock for trie access | `_read_ready`, `_readers`, `_lock` | Condition + lock |
| **BusStats** | `impl/local_bus.py` | 226–239 | Observable bus metrics (approximate) | 7 counter fields | Approximate (no global lock) |
| **TopicTrie** | `impl/topic_trie.py` | 125–500 | Radix-compressed O(k) pattern matching | `_root`, `_size`, `_sub_index` | NOT thread-safe; wrapped by RWLock |
| **Envelope** | `envelope/envelope.py` | 150–700 | Immutable frozen dataclass; message unit | None (frozen) | Immutable by design |
| **Priority** | `envelope/envelope.py` | 40–65 | IntEnum: URGENT(0)=4×, REALTIME(1)=3×, INTERACTIVE(2)=2×, BACKGROUND(3)=1× | None | N/A |
| **DeliveryMode** | `envelope/envelope.py` | 70–80 | IntEnum: STRICT(0), RELAXED(1), BEST_EFFORT(2) | None | N/A |
| **PayloadFormat** | `envelope/envelope.py` | 85–100 | IntEnum: OPAQUE(0), JSON(1), MSGPACK(2) | None | N/A |
| **LocalMailbox** | `impl/local_mailbox.py` | 59–281 | Bounded queue per actor; optional WFQ | `_queues`, `_single_queue`, `_size`, `_lock`, `_not_empty`, `_closed` | Condition + lock per mailbox |
| **LocalMailboxRouter** | `impl/local_mailbox.py` | 285–482 | Actor registry + delivery dispatcher | `_mailboxes`, `_lock`, `_closed` | RLock; released before ._deliver() |
| **RustBusAdapter** | `impl/rust_bus_adapter.py` | 60–307 | Wraps k1_bus_core.RustBus | `_bus`, `_capture`, `_sub_patterns` | Delegates to Rust (thread-safe) |
| **RustMailboxAdapter** | `impl/rust_mailbox_adapter.py` | 58–133 | Wraps RustMailbox instance | `_inner`, `_actor_id`, `_capacity` | Delegates to Rust |
| **RustMailboxRouterAdapter** | `impl/rust_mailbox_adapter.py` | 136–313 | Wraps RustMailboxRouter | `_router`, `_configs` | Delegates to Rust |
| **Middleware (Protocol)** | `middleware/__init__.py` | 30–50 | Contract: `process(Envelope) → Envelope \| None` | N/A | Caller's responsibility |
| **MiddlewareChain** | `middleware/__init__.py` | 55–120 | Ordered pipeline of middleware | `_middlewares` | Thread-safe if each middleware is |
| **TracingMiddleware** | `middleware/tracing.py` | 60–150 | OpenTelemetry integration (graceful degradation) | `_tracer`, `_enabled` | OTel's thread-safe tracer |
| **MetricsMiddleware** | `middleware/metrics.py` | 100–250 | Prometheus counter + histogram | `_counter`, `_histogram`, `_enabled` | Prometheus objects thread-safe |
| **TopicRegistry** | `middleware/topic_validation.py` | 35–160 | Known topics (exact + prefix + wildcard) | `_exact`, `_prefixes`, `_wildcards`, `_lock` | RLock on registration; snapshot reads |
| **TopicValidationMiddleware** | `middleware/topic_validation.py` | 165–240 | Soft validation (warns, never drops) | `_registry`, `_warn_count` | Thread-safe (delegated) |
| **TimingChain** | `timing/timing_chain.py` | 200–900 | Deadline-agnostic ordering (causal + gap) | `_config`, `_causal`, `_gap`, `_stats` | Per-topic locks + global causal lock |
| **_CausalTracker** | `timing/timing_chain.py` | 100–250 | Parent-child ordering enforcement | `_delivered`, `_waiting`, `_lock` | Single global lock (cross-topic) |
| **_GapBuffer** | `timing/timing_chain.py` | 255–500 | Per-topic sequence gap buffering | `_expected`, `_buffers`, `_locks` | Per-topic locks (zero cross-topic) |
| **TimingStats** | `timing/timing_chain.py` | 60–85 | Observable timing metrics | 9 counter fields | Approximate (no lock) |
| **TimingConfig** | `timing/timing_config.py` | 40–250 | Topic prefix → DeliveryMode resolution | `_rules`, `_default`, `_lock`, `_sorted_prefixes` | Atomic snapshot read; lock on reload() |

### 2.2 Message Flow — Publish (Happy Path)

```
Publisher Thread
  │
  └→ LocalBus.publish(Envelope)
      ├─ [Validation] not closed? ✓  topic non-empty? ✓
      ├─ [Stamping] (no lock)
      │   ├→ envelope_id = _id_gen.next()     [global monotonic]
      │   ├→ sequence    = _seq_gen.next(topic) [per-topic monotonic]
      │   └→ created_ns  = time.monotonic_ns()
      ├─ [Middleware Chain] (no lock)
      │   ├→ TracingMiddleware  → OTel span
      │   ├→ MetricsMiddleware  → Prometheus counter/histogram
      │   └→ TopicValidation    → warn if unknown (never drop)
      ├─ [Capture] optional → _captured.append()
      ├─ [Trie Match] (READ lock, concurrent)
      │   └→ handlers = _trie.match(topic) → DFS walk
      └─ [Dispatch]
          ├─ Path A (no TimingChain): invoke handlers directly
          └─ Path B (with TimingChain):
              ├→ STRICT:      causal check → gap check → dispatch or buffer
              ├→ RELAXED:     monitor only → dispatch immediately
              └→ BEST_EFFORT: dispatch immediately, no tracking
```

### 2.3 Causal + Gap Buffering (STRICT Mode)

**Causal**: If parent_id not yet delivered → buffer child → cascade on parent arrival.
**Gap**: If sequence > expected → buffer → release when gap fills or timeout.
**Timeout**: `sweep()` force-releases buffered envelopes after `timeout_ms` (default 5000ms).
**Overflow**: Buffer > max → force-release oldest 10%.

### 2.4 Mailbox Delivery & Reception

```
Sender Thread                          Receiver Thread (Actor)
  │                                      │
  └→ Router.deliver(actor_id, env)       └→ mailbox.receive(timeout_ms)
      ├─ acquire registry lock               ├─ acquire lock + condition
      ├─ mailbox = lookup(actor_id)          ├─ _try_dequeue()
      ├─ release lock (before deliver!)      │   └→ strict priority: URGENT→...→BACKGROUND
      └→ mailbox._deliver(env)               ├─ if empty: wait(timeout)
          ├─ capacity check → BackpressureError  └→ return envelope or None
          ├─ enqueue to priority sub-queue
          └─ notify() → wake receiver
```

### 2.5 Concurrency Model — Lock Hierarchy

| Priority | Lock | Scope | Held For | Contention |
|----------|------|-------|----------|------------|
| 1 | RWLock on TopicTrie | IBus | trie match/insert/remove | Read=concurrent, Write=exclusive |
| 2 | Per-topic _SequenceGenerator | IBus | counter increment | Zero cross-topic |
| 3 | Per-topic _GapBuffer | TimingChain | gap check + buffer | Zero cross-topic |
| 4 | Global _CausalTracker | TimingChain | parent lookup + child buffer | Cross-topic (less frequent) |
| 5 | Per-mailbox Condition+Lock | IMailbox | enqueue/dequeue | Zero inter-mailbox |
| 6 | Registry RLock | IMailboxRouter | actor lookup | Released before delivery |

### 2.6 Serialization Architecture

**V2 FlatBuffers (default)**: `[4B: b'FB02' magic][N B: FlatBuffers BusEnvelope table]` — zero-copy payload access.
**V1 JSON (fallback)**: `[4B: big-endian uint32 header_len][header bytes: JSON][payload bytes]`

Auto-detection in `Envelope.from_bytes()`:

```python
if data[:4] == b'FB02':  # V2 path
else:                     # V1 path
```

Control: `K1_ENVELOPE_FORMAT` env var — `"v2"` (default) or `"v1"`.

### 2.7 Error Handling & Failure Isolation

| Scenario | Catch Point | Behavior | Impact |
|----------|-------------|----------|--------|
| Handler exception | LocalBus._dispatch | Caught, logged, isolated | Other handlers + publisher unaffected |
| Middleware exception | LocalBus.publish | Caught, logged, envelope dropped | Observability error only |
| Empty/invalid topic | LocalBus.publish | Logged, dropped | Silent |
| Closed bus | LocalBus.publish | Returns early | Graceful shutdown |
| Backpressure | Router.deliver | Raises BackpressureError | Sender must handle |
| Unknown actor | Router.deliver | Raises UnknownActorError | Sender must handle |
| Timed-out buffered | TimingChain.sweep | Force-released out-of-order | Logged warning |
| Buffer overflow | CausalTracker/GapBuffer | Force-release oldest 10% | Logged warning |

### 2.8 Observability

**BusStats**: `envelopes_published`, `envelopes_delivered`, `handler_errors`, `subscriptions_active`, `subscriptions_total`, `unsubscribe_count`, `topics_seen`
**MetricsMiddleware**: `k1_bus_envelopes_total{topic_prefix, priority}`, `k1_bus_envelope_latency_seconds{topic_prefix}`
**TimingStats**: `envelopes_processed`, `delivered_immediate`, `buffered_causal`, `buffered_gap`, `released_causal`, `released_gap`, `released_timeout`, `reorders_detected`, `dropped_best_effort`
**Per-mailbox**: `pending()`, `delivered_count`, `received_count`, `depth_by_priority()`
**Router**: `actor_count`, `stats_snapshot()` (per-actor dict)

### 2.9 Rust/Python Boundary

```
k1_bus_core module (optional):
  RustBus, RustEnvelope, RustMailboxRouter, RustMailbox, TopicTrie
```

- **Envelope conversion**: `_envelope_to_rust()` / `_rust_to_envelope()` at boundary
- **Handler wrapping**: Subscribe wraps Python handler to accept RustEnvelope → convert → invoke
- **Import-time detection**: `_HAS_RUST` flag; `BusFactory` auto-selects

**V1/V2 API Parity**:

| Feature | LocalBus (V1) | RustBusAdapter (V2) | Notes |
|---------|:---:|:---:|-------|
| publish/subscribe/unsubscribe | ✅ | ✅ | Conversion at boundary |
| .captured / .drain() | ✅ | ✅/⚠️ | Rust has no drain; returns all |
| .stats | ✅ | ✅ | Rust dict → Python BusStats |
| .timing_chain | ✅ | ❌ | Stored but not wired to Rust dispatch |
| .middleware | ✅ | ❌ | Stored but not wired to Rust dispatch |
| handler_circuits() [M8] | ❌ | ✅ | Rust-only circuit breaker |

### 2.10 Key Design Decisions

| Decision | Rationale | Trade-off |
|----------|-----------|-----------|
| Frozen Envelope | Immutability = thread-safe, cacheable | Must rebuild on field change (rare) |
| Opaque payload | Bus doesn't read payload | Adapter layer for deserialization |
| RWLock on trie | Publish 100× more frequent than subscribe | Subscribe gets exclusive lock (acceptable) |
| Per-topic sequence gen | Zero cross-topic contention | Slightly more memory |
| Strict priority (V1) | Simple, deterministic | May starve BACKGROUND under sustained URGENT |
| SOFT topic validation | Bus liveness | Unknown topics flow (operators monitor warnings) |
| Timeout-based release | Prevents permanent blocking | Out-of-order on timeout |
| Rust optional | Backward compatibility | Conversion overhead at boundary |
| FlatBuffers default | Performance + cross-language | Requires env var for V1 fallback |

---

## 3. Factory & Configuration

### 3.1 Factory Methods (`factory.py`)

#### `BusFactory.create_local()`

```python
def create_local(*, capture=False, timing_chain=None, middleware=None, backend="auto") → BusType
```

- Resolves backend ("auto" → "rust" if available, else "python")
- If timing_chain provided + Rust → auto-downgrades to Python (logged)
- Returns `LocalBus` or `RustBusAdapter`

#### `BusFactory.create_local_ordered()`

```python
def create_local_ordered(*, config=None, timeout_ms=5000, capture=False, middleware=None, backend="python") → LocalBus
```

- **Python-only** — raises `ValueError` if Rust requested
- If config=None → uses `default_timing_config()`
- Creates `TimingChain(config, timeout_ms)` → wires to `LocalBus`

#### `BusFactory.create_for_testing()`

```python
def create_for_testing(*, ordered=False, middleware=None, backend="auto") → BusType
```

- **Always capture=True** — all envelopes recorded
- If ordered=True → Python forced with TimingChain + default config
- Else → auto backend selection

#### `BusFactory.create_mailbox_router()`

```python
def create_mailbox_router(*, backend="auto") → MailboxRouterType
```

- Returns `LocalMailboxRouter` or `RustMailboxRouterAdapter`
- Independent of event bus; no timing chain

### 3.2 Backend Selection Matrix

| Scenario | Backend Param | Resolution | Result |
|----------|---------------|------------|--------|
| No arg, Rust compiled | `"auto"` | Probes `_RUST_AVAILABLE` | Rust |
| No arg, no Rust | `"auto"` | `_RUST_AVAILABLE = False` | Python (graceful) |
| Explicit "rust" + no Rust | `"rust"` | `_RUST_AVAILABLE = False` | **ImportError** |
| Explicit "python" | `"python"` | Always valid | Python |
| timing_chain + "rust" | `"rust"` + timing_chain | Downgrades | Python + debug log |
| ordered bus + "rust" | create_local_ordered | Enforced | **ValueError** |

### 3.3 Default Timing Configuration (`timing/defaults.py`)

**18 prefix rules:**

| Mode | Topic Prefixes | Count |
|------|---------------|-------|
| **STRICT** | `k1.capability`, `k1.orchestration`, `k1.planner`, `k1.hil`, `k1.hitl`, `k1.response`, `k1.session`, `k1.agent`, `k1.internal`, `k1.tool`, `k1.arbiter`, `k1.backpool` | 12 |
| **RELAXED** | `k1.affect`, `k1.constraint`, `k1.proactive`, `k1.workflow` | 4 |
| **BEST_EFFORT** | `k1.k0.sse`, `k1.fabric.learning` | 2 |

**Default for unmatched**: `RELAXED`

### 3.4 TimingConfig Runtime Behavior

- **Reads**: Atomic dict reference (no locks) — safe for concurrent `resolve()` calls
- **Writes**: `reload(new_rules)` acquires lock, performs atomic swap
- **Resolution**: Longest-prefix match, O(k) where k = segment count (3–7 typical)

### 3.5 Configuration Gaps

| Gap | Impact | Mitigation |
|-----|--------|------------|
| No `K1_BUS_BACKEND` env var | Can't configure externally | Wrap factory in kernel.py |
| No YAML/JSON config loading | Hardcoded only | Programmatic injection via `config=` param |
| No distributed bus | In-process only | Future work |
| Rust + TimingChain incompatible | Auto-fallback to Python | Acceptable for correctness |
| Middleware is global | No per-topic filtering | Compose at middleware layer |

---

## 4. Cross-Component Connections

### 4.1 Connection Inventory

| # | From → To | Bus Side | External Side | Mechanism | Status |
|---|-----------|----------|---------------|-----------|--------|
| 1 | Bus → SessionState | `SessionBusAdapter` | `IEventPort` (ABC) | ABC inheritance | ✅ PERFECT |
| 2 | Bus → Fabric (events) | `FabricBusAdapter` | `IEventPort` (Protocol) | Structural subtyping (Dict⊆Any) | ✅ EXACT |
| 3 | Bus → Fabric (deltas) | `FabricBusAdapter` | `IDeltaBusPort` (Protocol) | Structural subtyping | ✅ EXACT |
| 4 | Bus → Concierge (input) | `BusInputAdapter` | `IInputPort` | `async receive() → Envelope, has_buffered() → bool` | ✅ EXACT |
| 5 | Bus → Concierge (output) | `BusOutputAdapter` | `IOutputPort` | `async send(envelope) → None` | ✅ EXACT |
| 6 | Bus → Orchestrator | `IMailbox` | `IMailboxPort` | Adapter wraps sync → high-level | ✅ COMPATIBLE |
| 7 | Bus → Planner | `IMailbox` | `IMailboxPort` | Async wrapper pattern | ✅ COMPATIBLE |

### 4.2 Risk Assessment

🟢 **ALL 7 CONNECTIONS TYPE COMPATIBLE — No breaking changes detected.**

### 4.3 Connection Details

**Bus → SessionState**: `SessionBusAdapter` inherits from SessionState's `IEventPort` ABC directly. Methods: `emit(event_type, payload)`, `subscribe(event_type, handler) → str`, `unsubscribe(subscription_id) → bool`, `is_connected → bool`. Topic prefix: `k1.session.{event_type}`.

**Bus → Fabric**: `FabricBusAdapter` satisfies Fabric's `IEventPort` (Dict payload) and `IDeltaBusPort` (delta envelope) via structural subtyping. JSON serialization at boundary. Delta topic: `k1.agent.{agent_id}.delta.v1`.

**Bus → Concierge**: `BusInputAdapter` wraps IBus subscribe into `async receive()` returning Envelope. `BusOutputAdapter` wraps IBus publish into `async send()`. Both satisfy Concierge port protocols exactly.

**Bus → Orchestrator/Planner**: IMailbox (sync receive) wrapped by adapter to satisfy IMailboxPort (higher-level API). Compatible via wrapping pattern.

---

## 5. Test Surface

### 5.1 Test File Inventory (23 files)

| File | Tests | Area |
|------|-------|------|
| `tests/k1/bus/ports/test_bus_protocol.py` | ~11 | IBus protocol compliance |
| `tests/k1/bus/ports/test_mailbox_protocol.py` | ~20+ | IMailbox/IMailboxRouter protocol |
| `tests/k1/bus/impl/test_local_bus.py` | ~70+ | **LARGEST**: publish, subscribe, stamping, error isolation, capture, thread safety, 100K stress |
| `tests/k1/bus/impl/test_local_mailbox.py` | ~80+ | LocalMailbox FIFO/WFQ, priority, backpressure, LocalMailboxRouter, thread safety |
| `tests/k1/bus/impl/test_topic_trie.py` | ~60+ | Exact, wildcard (*), greedy (>), overlapping, compaction, real K1 patterns |
| `tests/k1/bus/impl/test_rust_bus_parity.py` | ~60+ | **PARAMETRIZED**: LocalBus + RustBus parity |
| `tests/k1/bus/envelope/test_envelope.py` | ~40+ | V1 construction, frozen immutability, serialization round-trip |
| `tests/k1/bus/envelope/test_envelope_v2.py` | ~60+ | V2 FlatBuffers, cross-format interop, large payloads, benchmarks |
| `tests/k1/bus/middleware/test_middleware_chain.py` | ~35+ | Chain ordering, drop short-circuits, LocalBus integration |
| `tests/k1/bus/middleware/test_metrics.py` | ~20+ | Prometheus counter/histogram, graceful degradation |
| `tests/k1/bus/middleware/test_tracing.py` | ~20+ | OTel span creation, graceful degradation |
| `tests/k1/bus/middleware/test_topic_validation.py` | ~35+ | TopicRegistry, soft validation, warns-never-drops |
| `tests/k1/bus/adapters/test_session_adapter.py` | ~30+ | **Cross-module**: IEventPort compliance, round-trip |
| `tests/k1/bus/adapters/test_fabric_adapter.py` | ~40+ | **Cross-module**: IEventPort + IDeltaBusPort, wildcard, delta round-trip |
| `tests/k1/bus/integration/test_cross_module.py` | ~50+ | **E2E**: Fabric→raw bus, delta aggregation, multi-adapter coexistence |
| `tests/k1/bus/timing/test_timing_config.py` | ~25+ | Prefix resolution, reload, thread safety |
| `tests/k1/bus/timing/test_timing_chain.py` | ~50+ | **COMPLEX**: STRICT/RELAXED/BEST_EFFORT, causal, gap, timeout sweep |
| `tests/k1/bus/test_rust_core.py` | ~40+ | Rust module smoke, cross-language round-trip, RingBuffer, RustBus |
| `tests/k1/bus/test_rust_m6.py` | ~30+ | RustTimingConfig, WfqScheduler, parity |
| `tests/k1/bus/test_rust_m7.py` | ~45+ | RustMailbox, RustMailboxRouter, DeadLetterQueue |
| `tests/k1/bus/test_rust_m8.py` | ~35+ | Async dispatch, CircuitBreaker, SweepTimer |
| `tests/k1/bus/test_rust_m9.py` | ~40+ | Factory backend switching, adapter integration |
| `tests/k1/bus/bench_v2_m10.py` | ~30+ | **BENCHMARKS**: Latency p50/p95/p99, throughput, memory |

### 5.2 Aggregate Statistics

| Metric | Value |
|--------|-------|
| Total test files | 23 |
| Estimated test functions | ~1,100+ |
| Lines of test code | ~8,000–10,000 |
| Largest files | test_local_mailbox.py (~900 lines), test_local_bus.py (~800 lines) |
| Parametrized tests | Parity (LocalBus+RustBus), TopicTrie (Python+Rust) |

### 5.3 Coverage by Area

| Area | Tests | Status |
|------|-------|--------|
| Core Bus (publish/subscribe/trie) | ~210+ | ✅ EXCELLENT |
| Envelope Serialization (V1+V2) | ~100+ | ✅ EXCELLENT |
| Middleware (chain + 3 impls) | ~110+ | ✅ GOOD |
| Adapters (Session + Fabric) | ~70+ | ✅ GOOD |
| Integration (cross-module E2E) | ~50+ | ✅ EXCELLENT |
| Ordering (causal + gap + timing) | ~75+ | ✅ GOOD |
| Rust Extension (M4–M10) | ~220+ | ✅ COMPREHENSIVE |
| Thread Safety | Spread across | ✅ Concurrent publish, deliver+receive, register+deliver, resolve+reload |
| Stress / High-Volume | ~5+ dedicated | ✅ 100K publishes, 10K parity, backpressure |

### 5.4 Cross-Component Test Imports

- `test_session_adapter.py` imports `k1.sessionstate.ports.events.IEventPort` → validates Bus↔SessionState integration
- `test_fabric_adapter.py` imports `k1.fabric.ports.event_port.IEventPort` + `k1.fabric.ports.delta_bus.IDeltaBusPort` → validates Bus↔Fabric integration
- `test_cross_module.py` imports both adapters + both port sets → full multi-component orchestration

### 5.5 Coverage Gaps

| Gap | Notes |
|-----|-------|
| Distributed/Network bus | In-process only (by design) |
| Real OTel integration | Tested at mock level |
| Real Prometheus scraping | Tested at mock level |
| Bus federation (multi-bus) | Not designed for this |

---

## 6. Spec vs Code Delta

### 6.1 Diagram vs Implementation Alignment

Comparing `k1/bus/k1_bus_core.mmd` (spec) against actual code:

| Spec Feature | Code Status | Notes |
|--------------|:-----------:|-------|
| IBus: publish(topic, payload:bytes)→u64 | ✅ | Signature uses `Envelope` (richer), returns `None` (fire-and-forget) |
| IBus: subscribe(pattern, handler)→handle | ✅ | Returns `SubscriptionHandle` dataclass |
| IBus: unsubscribe(handle)→bool | ✅ | Exact match |
| IBus: stats()→BusStats | ✅ | Property instead of method |
| IBus: close() | ✅ | Exact match |
| IMailboxRouter: register/send_to/get_mailbox/unregister | ✅ | `send_to` → `deliver` (name difference only) |
| IMailbox: send/receive/depth/close | ✅ | `send` is internal `_deliver`; `depth` → `pending` |
| FlatBuffers envelope (12 fields) | ✅ | All 12 fields present + `payload_format` (13th) |
| LMAX ring buffer | ✅ | Rust side; Python uses deque |
| Trie-based topic matching | ✅ | Radix-compressed, exact + wildcard + greedy |
| WFQ deficit round-robin | ✅ | V1=strict priority (4-level); V2 Rust=true WFQ |
| TimingChain (STRICT/RELAXED/BEST_EFFORT) | ✅ | Full causal + gap buffering + timeout sweep |
| TracingMiddleware | ✅ | OTel with graceful degradation |
| MetricsMiddleware | ✅ | Prometheus counter + histogram |
| TopicValidation | ✅ | Soft (warns, never drops) |
| BusFactory V1/V2 switching | ✅ | Capability-based auto-detection via `_RUST_AVAILABLE` |
| Performance targets (p50<1μs, >1M msg/sec) | ⚠️ | Targets specified for Rust; Python meets ~50μs publish |

### 6.2 Naming Differences (Spec → Code)

| Spec Name | Code Name | Notes |
|-----------|-----------|-------|
| `send_to(actor_id, envelope)` | `deliver(actor_id, envelope)` | IMailboxRouter method |
| `depth` | `pending` | IMailbox property |
| `send(envelope)` | `_deliver(envelope)` | IMailbox internal (not public) |
| `stats()` method | `.stats` property | IBus |

### 6.3 Code Extras Not in Spec

| Extra | Location | Purpose |
|-------|----------|---------|
| `PayloadFormat` enum | `envelope.py` | V2 deserialization hint (OPAQUE/JSON/MSGPACK) |
| `capture` mode | `LocalBus` | Testing helper — records all published envelopes |
| `handler_circuits()` | `RustBusAdapter` | M8 circuit breaker (Rust-only) |
| `DeadLetterQueue` | `RustMailboxRouter` | M7 dead letter handling (Rust-only) |
| `SweepTimer` | Rust M8 | Auto-sweep for timed-out buffered envelopes |

### 6.4 Open Questions

| # | Question | Impact |
|---|----------|--------|
| 1 | Should `K1_BUS_BACKEND` env var be added to factory? | Low — easy to add in kernel.py |
| 2 | Should TimingChain work with Rust backend? | Medium — V2.1 feature (pending Rust TimingChain impl) |
| 3 | Should per-topic middleware filtering be supported? | Low — compose at middleware layer |

---

## File Index

| File | Lines | Purpose |
|------|-------|---------|
| `ports/bus.py` | ~144 | IBus Protocol, BusHandler, SubscriptionHandle |
| `ports/mailbox.py` | ~231 | IMailbox, IMailboxRouter, MailboxConfig, exceptions |
| `ports/__init__.py` | — | Exports: IBus, IMailbox, IMailboxRouter, etc. |
| `impl/local_bus.py` | ~570 | LocalBus, _SequenceGenerator,_EnvelopeIdGenerator, _ReadWriteLock, BusStats |
| `impl/local_mailbox.py` | ~482 | LocalMailbox, LocalMailboxRouter |
| `impl/topic_trie.py` | ~500 | TopicTrie, _TrieNode |
| `impl/rust_bus_adapter.py` | ~307 | RustBusAdapter |
| `impl/rust_mailbox_adapter.py` | ~313 | RustMailboxAdapter, RustMailboxRouterAdapter |
| `envelope/envelope.py` | ~700 | Envelope (frozen dataclass), Priority, DeliveryMode, PayloadFormat |
| `envelope/_fb_generated.py` | — | FlatBuffers auto-generated code |
| `middleware/__init__.py` | ~120 | Middleware Protocol, MiddlewareChain |
| `middleware/tracing.py` | ~150 | TracingMiddleware (OTel) |
| `middleware/metrics.py` | ~250 | MetricsMiddleware (Prometheus) |
| `middleware/topic_validation.py` | ~240 | TopicRegistry, TopicValidationMiddleware |
| `timing/timing_chain.py` | ~900 | TimingChain, _CausalTracker,_GapBuffer, TimingStats |
| `timing/timing_config.py` | ~250 | TimingConfig (prefix → DeliveryMode) |
| `timing/defaults.py` | ~100 | DEFAULT_RULES (18 prefixes), default_timing_config() |
| `factory.py` | ~319 | BusFactory (create_local, create_local_ordered, create_for_testing, create_mailbox_router) |
| `__init__.py` | — | Package init |
| `README.md` | — | Component README |
| `k1_bus_core.mmd` | ~300 | Architecture diagram (Mermaid) |
