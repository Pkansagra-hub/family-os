# K1 Bus V2 -- Rust Core Migration Plan

> **Status**: DRAFT -- Post-V1 completion design
> **Prerequisite**: V1 complete (M1-M6, 446 tests, 3464 source lines, 4504 test lines)
> **Goal**: Replace hot-path internals with Rust via PyO3.  Same `IBus`/`IMailboxRouter` interfaces.  Zero module code changes.  Python V1 stays as permanent fallback.

---

## Table of Contents

1. [V1 Audit & Improvement Opportunities](#1-v1-audit--improvement-opportunities)
2. [World-Class Bus Design Patterns](#2-world-class-bus-design-patterns)
3. [V2 Architecture](#3-v2-architecture)
4. [Milestones, Epics & Issues](#4-milestones-epics--issues)
5. [Performance Targets](#5-performance-targets)
6. [Risk Matrix](#6-risk-matrix)
7. [Migration Strategy](#7-migration-strategy)

---

## 1. V1 Audit & Improvement Opportunities

### 1.1 Current V1 Architecture Inventory

| Component | File | Lines | Hot Path? |
|---|---|---|---|
| TopicTrie | `k1/bus/impl/topic_trie.py` | 204 | YES -- every publish |
| LocalBus | `k1/bus/impl/local_bus.py` | 478 | YES -- stamp + route |
| TimingChain | `k1/bus/timing/timing_chain.py` | 565 | YES -- causal + gap |
| LocalMailbox | `k1/bus/impl/local_mailbox.py` | 367 | YES -- actor queues |
| Envelope | `k1/bus/envelope/envelope.py` | 213 | YES -- every message |
| TimingConfig | `k1/bus/timing/timing_config.py` | 143 | YES -- prefix lookup |
| Ports | `k1/bus/ports/` | 231 | NO -- type declarations |
| Middleware | `k1/bus/middleware/` | 444 | WARM -- once per publish |
| Adapters | `k1/bus/adapters/` | 368 | NO -- module-side serialization |
| Factory | `k1/bus/factory.py` | 125 | NO -- startup-only |
| Timing defaults | `k1/bus/timing/defaults.py` | 56 | NO -- loaded once |
| **Total** | **15 .py files** | **3464** | |

### 1.2 Identified Weaknesses & Improvement Opportunities

#### CRITICAL -- Dispatch Model

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-01 | **Synchronous dispatch on publisher thread** | Publisher blocks until ALL handlers complete.  A slow handler (50ms DB write) blocks all subsequent handlers AND the publisher.  Under fan-out=10, a single slow handler creates 500ms tail latency for the entire publish chain. | `local_bus.py` `_dispatch()` loops through handlers sequentially |
| W-02 | **No true WFQ in pub/sub dispatch** | V1 claims WFQ but only implements strict priority in mailbox.  For `IBus.publish()`, envelopes are dispatched in arrival order regardless of priority -- there is no scheduling queue between publish and handler invocation. | `local_bus.py` docstring says "WFQ-aware priority dispatch" but `_dispatch()` just iterates handlers in trie match order |
| W-03 | **No dispatch batching** | Each `publish()` call independently walks the trie and dispatches.  Under burst load (100 envelopes in 1ms), there is no opportunity to batch trie lookups or consolidate handler invocations. | Direct call path, no internal queue |

#### HIGH -- Serialization & Memory

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-04 | **JSON serialization in adapters** | `json.dumps`/`json.loads` on every publish/receive through Fabric or Session adapter.  JSON is 5-10x slower than FlatBuffers/msgpack for structured data and produces 2-3x larger payloads. | `fabric_adapter.py`, `session_adapter.py` |
| W-05 | **Python object overhead per Envelope** | Each Envelope is a frozen dataclass with 10 fields.  CPython allocates ~800 bytes per instance (object header + field slots + string interning for topic/tracing IDs).  At 10K envelopes/sec, that is 8MB/sec of object churn triggering GC pressure. | `envelope.py` -- pure Python dataclass |
| W-06 | **`with_bus_fields()` creates a full copy** | Every `publish()` creates a new Envelope via `dataclasses.replace()` to stamp bus fields.  This allocates a second object just to add envelope_id + sequence + created_ns. | `local_bus.py` line ~340: `stamped = envelope.with_bus_fields(...)` |

#### HIGH -- Concurrency & Locking

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-07 | **RWLock is Python-level, not OS-level** | `_ReadWriteLock` uses `threading.Condition` which acquires the GIL on every lock/unlock.  Under contention, this degrades to serial execution. | `local_bus.py` -- custom `_ReadWriteLock` class |
| W-08 | **Per-topic sequence lock contention** | `_SequenceGenerator` uses one `threading.Lock` per topic.  With 50+ topics, the double-checked locking in `_get_lock()` creates global lock contention during topic discovery. | `local_bus.py` `_SequenceGenerator._get_lock()` |
| W-09 | **GIL prevents true parallelism** | Even with `_ReadWriteLock`, CPython's GIL serializes all Python execution.  Multiple threads publishing concurrently gain zero actual parallelism. | Fundamental Python limitation |
| W-10 | **CausalTracker global lock** | Single `threading.Lock` across ALL topics for parent_id tracking.  Every STRICT publish must acquire this global lock even if topics are independent. | `timing_chain.py` `_CausalTracker._lock` |

#### MEDIUM -- Trie & Routing

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-11 | **Trie match allocates a new list per publish** | `match()` creates `result: list[T] = []` on every call.  At 10K calls/sec, this is 10K list allocations/sec. | `topic_trie.py` `match()` line ~167 |
| W-12 | **No subscription caching** | If a topic has been matched before, the trie re-walks the entire tree.  High-frequency topics (e.g., `k1.response.final.v1` at 1000/sec) repeat identical work. | No cache in `TopicTrie` |
| W-13 | **Tombstone compaction is lazy** | Unsubscribe uses None tombstones.  Compaction triggers only when >50% are tombstones.  In long-running systems with frequent subscribe/unsubscribe cycles (agents spawning/dying), tombstone density can cause match() to iterate dead entries. | `topic_trie.py` `_maybe_compact()` |
| W-14 | **No topic validation at publish time** | The trie validates patterns on subscribe, but `publish()` accepts any string including malformed/empty-segment topics.  Middleware catches this too late (after stamping). | `local_bus.py` only checks `if not topic` |

#### MEDIUM -- Mailbox & Backpressure

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-15 | **Strict priority, not true WFQ in mailbox** | `LocalMailbox._try_dequeue()` always drains URGENT before REALTIME.  Under sustained URGENT load, BACKGROUND messages starve indefinitely ~ even though their latency target is "< 500ms". | `local_mailbox.py` strict priority dequeue |
| W-16 | **No dead-letter queue** | When a mailbox is full, `BackpressureError` is thrown to the sender.  There is no dead-letter queue (DLQ) to capture rejected envelopes for later retry or forensic analysis. | `local_mailbox.py` `_deliver()` raises immediately |
| W-17 | **No delivery acknowledgment** | `IMailboxRouter.deliver()` is fire-and-forget.  The sender has no way to know if the envelope was actually consumed (not just enqueued) by the target actor. | `local_mailbox.py` -- enqueue only |
| W-18 | **Mailbox receive blocks thread** | `receive(timeout_ms)` uses `threading.Condition.wait()` which holds the GIL.  In a bus with 20 actors all blocking on receive, 20 threads are parked on Condition objects adding scheduling overhead. | `local_mailbox.py` `receive()` |

#### MEDIUM -- Observability & Operations

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-19 | **No per-handler latency tracking** | `BusStats` tracks `envelopes_delivered` count but not per-handler execution time.  Cannot identify a slow handler without external profiling. | `local_bus.py` `BusStats` |
| W-20 | **No envelope TTL or expiry** | Once published, an envelope lives forever in buffers (until timeout sweep).  There is no way for a publisher to say "this message is only valid for 500ms". | Envelope has no TTL field |
| W-21 | **No backpressure on IBus (pub/sub)** | `publish()` always succeeds (or silently drops if closed).  If subscribers cannot keep up, the publisher has no signal.  Memory grows unbounded in the timing chain gap buffer. | `local_bus.py` `publish()` returns None |
| W-22 | **Stats are approximate under concurrency** | `BusStats` uses plain int fields incremented without locks.  Under GIL this is currently safe, but moving to Rust would expose data races. | `local_bus.py` `BusStats` dataclass |
| W-23 | **No subscription lifecycle events** | No way to observe when a subscription is created/removed.  Operators cannot monitor "Orchestrator lost its k1.planner.plan.ready.v1 subscription" without scraping stats. | No subscription events emitted |
| W-24 | **No middleware ordering guarantee** | `MiddlewareChain` processes in list order but there is no priority or dependency system.  If `MetricsMiddleware` must run after `TracingMiddleware` (to include trace_id in metrics), the caller must manually order them correctly. | `middleware/__init__.py` -- list order |

#### LOW -- Safety & Resilience

| ID | Issue | Impact | Current State |
|---|---|---|---|
| W-25 | **No circuit breaker on handler dispatch** | If a handler throws on every call (bug), the bus catches + logs but continues dispatching to it at full rate, filling logs. | `local_bus.py` `_dispatch()` always retries |
| W-26 | **No replay capability** | In-process bus has no persistence.  If the process restarts, all in-flight and captured envelopes are lost.  Testing workaround: `capture=True` is memory-only. | By design (V1 is ephemeral) |
| W-27 | **Sweep timer is external** | `LocalBus.sweep()` must be called by an external timer.  If the caller forgets, buffered STRICT envelopes are permanently stuck until process restart. | `local_bus.py` `sweep()` is manual |
| W-28 | **No publish retry on middleware failure** | If middleware chain throws, the envelope is dropped silently with a log.  No DLQ or retry. | `local_bus.py` line ~355 |

---

## 2. World-Class Bus Design Patterns

Reference systems studied for V2 design: NATS (Go), Aeron (Java/C), Disruptor (LMAX), ZeroMQ,
Kafka (JVM), DPDK-based user-space networking, Seastar (C++), io_uring (Linux), tokio (Rust).

### 2.1 Patterns to Adopt

| Pattern | From | What It Solves | V1 WeaknessID |
|---|---|---|---|
| **Ring-buffer dispatch** | LMAX Disruptor / Aeron | Eliminate per-publish allocation.  Single pre-allocated ring buffer.  Publisher writes to slot, consumers read.  Zero-copy, cache-line aligned, mechanical sympathy. | W-03, W-05, W-06, W-11 |
| **Async dispatch with fan-out pool** | NATS / Kafka consumer groups | Decouple publisher from handler execution.  Handlers run on a bounded thread pool.  Publisher never blocks on slow handlers. | W-01, W-09 |
| **True WFQ with deficit round-robin** | NATS JetStream / Linux tc | Weighted scheduling that prevents starvation.  URGENT gets 4x bandwidth but BACKGROUND always makes progress.  Deficit counter ensures fairness over time. | W-02, W-15 |
| **FlatBuffers zero-copy envelope** | Aeron / Cap'n Proto | Envelope is a single contiguous byte buffer.  Fields accessed via offset, no deserialization.  Bus reads header without parsing.  Cross-language (Rust, Python, C++). | W-04, W-05, W-06 |
| **Lock-free concurrent data structures** | crossbeam / tokio | `AtomicU64` for envelope ID + sequence.  `DashMap` for subscription registry.  `parking_lot::RwLock` (twice as fast as `std::RwLock`).  No GIL involvement. | W-07, W-08, W-09, W-10 |
| **Subscription cache (topic -> handler[])**  | NATS | Cache trie match results.  Invalidate on subscribe/unsubscribe.  Reduces 99th percentile match latency from O(k*W) to O(1) for repeat topics. | W-12 |
| **Dead-letter queue (DLQ)** | Kafka / RabbitMQ | Capture rejected envelopes (backpressure, handler errors, expired TTL) for retry or forensic analysis. | W-16, W-25, W-28 |
| **Envelope TTL with lazy expiry** | NATS / Redis Streams | Publisher sets optional TTL on Envelope.  Bus checks TTL at dispatch time.  Expired envelopes go to DLQ, not handlers.  No background timer needed. | W-20 |
| **Circuit breaker per handler** | Hystrix / resilience4j | After N consecutive failures, circuit opens: handler is skipped for a cooldown period.  Prevents log flooding from broken handlers. | W-25 |
| **Built-in sweep timer** | Aeron conductor | TimingChain runs its own sweep on a dedicated thread (or co-op via `select!` in async).  No external caller needed. | W-27 |
| **Publish-side backpressure** | Disruptor / Aeron | When ring buffer is full, publisher either blocks or gets `BusFullError`.  Prevents unbounded memory growth. | W-21 |
| **Handler latency histogram** | Prometheus / Datadog | Per-handler-pattern latency percentiles (p50/p95/p99).  Identifies slow handlers without profiling. | W-19 |
| **Subscription lifecycle events** | NATS / gRPC | Bus emits internal events (`k1.bus.subscription.created`, `k1.bus.subscription.removed`) on the bus itself.  Operators subscribe to monitor. | W-23 |
| **Epoch-based subscription compaction** | Read-Copy-Update (RCU) | Instead of tombstones + lazy compaction, use epoch-based reclamation.  Publish reads never see garbage.  Unsubscribe marks epoch; compaction happens after all readers from that epoch finish. | W-13 |

### 2.2 Patterns Evaluated but Deferred

| Pattern | Why Deferred |
|---|---|
| **Persistent WAL (write-ahead log)** | Adds disk I/O.  V2 scope is in-process speed.  Defer to V3 (distributed bus). |
| **Multi-node replication** | Requires consensus protocol.  V2 is single-node.  Defer to V3. |
| **DPDK / io_uring user-space networking** | Only relevant for cross-process/cross-node transport.  V2 is in-process. |
| **Content-based routing** | Bus is BLIND to payload (design decision #1).  Would violate the fundamental architecture. |
| **Schema registry (Avro/Protobuf)** | Payload schema validation belongs in modules, not the bus.  Bus stays blind. |

---

## 3. V2 Architecture

### 3.1 Component Layout

```text
                    Python Land                          Rust Land (PyO3)
                    ──────────                           ────────────────
                                                         k1_bus_core/
                    k1/bus/ports/         <-- Protocol      src/
                    k1/bus/adapters/      <-- Dict/Any        envelope.rs
                    k1/bus/middleware/     <-- OTel/Prom       topic_trie.rs
                    k1/bus/factory.py     <-- Wiring          subscription_cache.rs
                                                              ring_buffer.rs
                    ─ ─ ─ PyO3 FFI ─ ─ ─ ─ ─ ─              local_bus.rs
                                                              timing_chain.rs
                                                              timing_config.rs
                                                              mailbox.rs
                                                              wfq.rs
                                                              circuit_breaker.rs
                                                              dlq.rs
                                                              sweep.rs
                                                              lib.rs
```

### 3.2 What Moves to Rust vs Stays Python

| Component | Destination | Rationale |
|---|---|---|
| Envelope (FlatBuffers) | **Rust** | Zero-copy read, single memcpy on publish, shared `.fbs` schema |
| TopicTrie + SubscriptionCache | **Rust** | Hot path, lock-free with `DashMap`, cache invalidation via epoch |
| Ring Buffer (Disruptor-style) | **Rust** | Pre-allocated, cache-line padded, eliminates per-publish allocation |
| LocalBus core (stamp + route) | **Rust** | GIL released during route, acquired only for Python handler callback |
| WFQ Scheduler (deficit round-robin) | **Rust** | True weighted fairness, shared between pub/sub dispatch and mailbox |
| TimingChain (causal + gap) | **Rust** | Lock-free causal tracker via `AtomicU64` + epoch reclamation |
| TimingConfig (prefix trie) | **Rust** | Prefix match as trie, not linear scan |
| Mailbox (bounded ring + WFQ) | **Rust** | `crossbeam::channel` + 4-priority ring with deficit counter |
| Circuit Breaker | **Rust** | Per-handler state machine, zero-cost when circuit closed |
| DLQ | **Rust** | Bounded ring buffer, exposed to Python for drain/inspect |
| Sweep Timer | **Rust** | Dedicated thread with `park`/`unpark`, no external caller needed |
| Ports (IBus, IMailbox, etc.) | **Python** | Type declarations only, zero runtime code |
| Adapters (Fabric, Session) | **Python** | Module-side serialization, runs once per publish, not hot path |
| Middleware (tracing, metrics) | **Python** | OTel + Prometheus SDKs are Python.  Middleware runs once per envelope O(1), middleware operates on a Python view of the Envelope header |
| Factory | **Python** | Startup-only wiring |

### 3.3 Data Flow (V2)

```text
publish(Envelope)
  |
  v
[Rust] stamp(envelope_id: AtomicU64, seq: AtomicU64, created_ns)
  |
  v
[Rust] ring_buffer.write(FlatBuffers bytes)           <-- zero-copy, no Python alloc
  |
  v
[Python] middleware_chain.process(envelope_header)     <-- GIL acquired, header-only view
  |                                                         (still Python: OTel, Prometheus)
  v
[Rust] topic_trie.match(topic) -> cached handler_ids  <-- GIL released, lock-free DashMap
  |
  v
[Rust] timing_chain.process(envelope, mode)            <-- causal + gap: lock-free atomics
  |
  v
[Rust -> Python] for handler in matched_handlers:
  |                 GIL.acquire()                      <-- acquired once per batch
  |                 handler(envelope_view)              <-- Python handler called
  |                 GIL.release()
  |
  v
[Rust] circuit_breaker.record(handler_id, success/fail)
  |
  v
[Rust] stats.update(AtomicU64 counters)               <-- lock-free
```

### 3.4 Ring Buffer Design (Disruptor Pattern)

```text
Ring Buffer (pre-allocated, fixed-size, cache-line padded)
+-------+-------+-------+-------+-------+-------+-------+-------+
| slot0 | slot1 | slot2 | slot3 | slot4 | slot5 | slot6 | slot7 |
+-------+-------+-------+-------+-------+-------+-------+-------+
    ^                       ^                               ^
    |                       |                               |
  consumer              publisher                      wrap point
  cursor                cursor

  - Publisher writes FlatBuffers bytes to next slot (CAS on cursor)
  - Consumer(s) read from their own cursor position
  - When publisher reaches wrap point: BACKPRESSURE (block or error)
  - Zero allocation: slots are pre-allocated byte buffers
  - Cache-line padded: publisher and consumer cursors on different lines
```

### 3.5 Deficit Round-Robin WFQ

```text
Replaces strict priority in both pub/sub dispatch and mailbox:

  Queues:    URGENT(w=4)  REALTIME(w=3)  INTERACTIVE(w=2)  BACKGROUND(w=1)
  Deficit:       0             0              0                 0

  Round 1: deficit += weight
             4             3              2                 1
           Serve 4        Serve 3        Serve 2           Serve 1

  Round 2: deficit += weight (carry over remainder)
             8             6              4                 2
           Serve 4        Serve 3        Serve 2           Serve 1

  - BACKGROUND always makes progress (gets 1 slot per round)
  - Under sustained URGENT flood, BACKGROUND latency = round_time * N
  - Configurable weights per-topic-prefix (TimingConfig extended)
  - Starvation IMPOSSIBLE (deficit always accumulates)
```

---

## 4. Milestones, Epics & Issues

### Overview

| Milestone | Name | Epics | Issues | Est. Effort |
|---|---|---|---|---|
| **V2-M1** | FlatBuffers Envelope + Schema | 2 | 8 | 1 week |
| **V2-M2** | Rust Crate Scaffold + CI | 2 | 7 | 1 week |
| **V2-M3** | Rust TopicTrie + Subscription Cache | 3 | 12 | 2 weeks |
| **V2-M4** | Rust Envelope + Ring Buffer | 3 | 11 | 2 weeks |
| **V2-M5** | Rust LocalBus Core | 4 | 16 | 3 weeks |
| **V2-M6** | Rust TimingChain + WFQ | 4 | 14 | 3 weeks |
| **V2-M7** | Rust Mailbox + DLQ | 3 | 10 | 2 weeks |
| **V2-M8** | Async Dispatch + Circuit Breaker | 3 | 10 | 2 weeks |
| **V2-M9** | Integration + Factory Switch | 2 | 8 | 1 week |
| **V2-M10** | Benchmarks + Production Hardening | 2 | 9 | 2 weeks |

**Total: 10 milestones, 28 epics, 105 issues, ~19 weeks**

---

### V2-M1: FlatBuffers Envelope + Schema

> Replace V1's `struct.pack + json` with FlatBuffers zero-copy.
> Python-side first (no Rust yet).  Shared `.fbs` schema used by both.

#### Epic 1.1: FlatBuffers Schema Definition

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M1-001 | Write `envelope.fbs` FlatBuffers schema | task | Define `BusEnvelope` table in `k1/bus/envelope/schema.fbs` matching all 10 V1 Envelope fields.  Add optional `ttl_ms: uint32 = 0` field for V2 TTL support (W-20).  Add `payload_format: uint8 = 0` field (0=opaque, 1=JSON, 2=msgpack) for future typed payloads.  Include `// FROZEN` comment on V1 fields. | W-04 |
| V2-M1-002 | Add `flatc` codegen build step | task | Install `flatc` compiler.  Add `scripts/codegen_envelope.py` that runs `flatc --python -o k1/bus/envelope/generated/ schema.fbs` and `flatc --rust -o k1_bus_core/src/generated/ schema.fbs`.  Integrate into `pyproject.toml` build hooks. | W-04 |
| V2-M1-003 | Generate Python FlatBuffers bindings | task | Run codegen.  Verify generated Python module imports.  Add `generated/` to `.gitignore` (or commit -- decide). | W-04 |

#### Epic 1.2: Swap Envelope Serialization

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M1-004 | Implement `Envelope.to_bytes()` via FlatBuffers | task | Replace `struct.pack + json.dumps` with FlatBuffers builder.  Keep V1 as `_to_bytes_v1()` fallback.  Add `ENVELOPE_FORMAT` config toggle. | W-04, W-05 |
| V2-M1-005 | Implement `Envelope.from_bytes()` via FlatBuffers | task | Replace `struct.unpack + json.loads` with FlatBuffers zero-copy reader.  Verify round-trip with all existing 29 tests. | W-04, W-05 |
| V2-M1-006 | Add `ttl_ms` field to Envelope dataclass | task | Add `ttl_ms: int = 0` to Envelope.  Default 0 = no expiry.  Bus will check at dispatch time in V2-M5. | W-20 |
| V2-M1-007 | Add `payload_format` field to Envelope | task | Add `payload_format: int = 0` to Envelope.  0=opaque (V1 behavior), 1=JSON, 2=msgpack.  Adapters can set this for type-safe deserialization hints. | W-04 |
| V2-M1-008 | Validate all 29 envelope tests pass | test | Run full envelope test suite.  No behavior change expected.  Performance benchmark: FlatBuffers `to_bytes()/from_bytes()` must be <= V1 latency. | -- |

---

### V2-M2: Rust Crate Scaffold + CI

> Create the `k1_bus_core` Rust crate with PyO3 bindings.
> Set up maturin build, CI pipeline, Python fallback switch.

#### Epic 2.1: Crate Structure

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M2-001 | Create `k1_bus_core/` Rust crate with `Cargo.toml` | task | Initialize crate: `pyo3`, `flatbuffers`, `crossbeam`, `dashmap`, `parking_lot` dependencies.  `crate-type = ["cdylib"]` for PyO3. | W-09 |
| V2-M2-002 | Create `lib.rs` with `#[pymodule]` skeleton | task | Define empty PyO3 module `k1_bus_core` with version/name.  Export placeholder `hello()` function to verify build. | W-09 |
| V2-M2-003 | Configure `maturin` build | task | Add `pyproject.toml` integration for `maturin develop --release`.  Verify `import k1_bus_core` works in Python. | W-09 |
| V2-M2-004 | Add FlatBuffers codegen to `build.rs` | task | `build.rs` runs `flatc --rust` on `envelope.fbs`.  Generated Rust bindings available at `src/generated/`. | W-04 |

#### Epic 2.2: CI Pipeline

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M2-005 | Add Rust toolchain to CI | task | GitHub Actions: install `rustup`, `maturin`, `flatc`.  Matrix: Python 3.10-3.13, Rust stable. | -- |
| V2-M2-006 | Add Python-only fallback CI job | task | CI job that runs ALL 446 tests WITHOUT Rust crate installed.  Verifies fallback path works. | -- |
| V2-M2-007 | Add `k1_bus_core` Rust unit test target | task | `cargo test` runs Rust-native tests (no Python).  Separate from pytest. | -- |

---

### V2-M3: Rust TopicTrie + Subscription Cache

> Port TopicTrie to Rust.  Add subscription cache for O(1) repeat-topic matches.
> Addresses W-11, W-12, W-13.

#### Epic 3.1: Rust TopicTrie

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M3-001 | Implement `TrieNode` in Rust | task | `HashMap<String, TrieNode>` with `handlers: Vec<u64>` (handler IDs, not Python objects).  Support `*` (single) and `>` (greedy) wildcards. | W-11 |
| V2-M3-002 | Implement `TopicTrie::insert()` | task | Pattern validation (empty segment, `>` must be last).  Returns `SubscriptionId(u64)`.  `DashMap` for concurrent insert/remove. | W-13 |
| V2-M3-003 | Implement `TopicTrie::match_topic()` | task | DFS walk matching exact + `*` + `>`.  Returns `Vec<u64>` (handler IDs).  GIL not needed during match. | W-11 |
| V2-M3-004 | Implement `TopicTrie::remove()` | task | Epoch-based reclamation instead of tombstones.  `crossbeam_epoch` for safe deferred cleanup. | W-13 |
| V2-M3-005 | Expose `TopicTrie` to Python via PyO3 | task | `#[pyclass]` with `insert`, `match_topic`, `remove`, `len`.  Handler IDs mapped to Python callables via internal `HashMap<u64, PyObject>`. | -- |

#### Epic 3.2: Subscription Cache

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M3-006 | Implement `SubscriptionCache` in Rust | task | `DashMap<String, Vec<u64>>` mapping concrete topic -> cached handler IDs.  `generation: AtomicU64` incremented on every subscribe/unsubscribe. | W-12 |
| V2-M3-007 | Cache invalidation on subscribe/unsubscribe | task | On any trie mutation, increment `generation`.  Cache entries tagged with generation at creation time.  Stale entries discarded on access. | W-12 |
| V2-M3-008 | Benchmark: cached vs uncached match latency | perf | Measure p50/p99 for 100-subscriber trie: cold match vs cached match.  Target: cached < 100ns. | W-12 |

#### Epic 3.3: Integration with Python V1

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M3-009 | Add `TopicTrie` import switch in `local_bus.py` | task | `try: from k1_bus_core import TopicTrie except ImportError: from k1.bus.impl.topic_trie import TopicTrie`.  Transparent fallback. | -- |
| V2-M3-010 | Run all 38 trie tests against Rust impl | test | Parametrize `test_topic_trie.py` with `@pytest.fixture(params=["python", "rust"])`.  Both must pass identically. | -- |
| V2-M3-011 | Run all 51 LocalBus tests with Rust trie | test | Swap trie only, keep Python LocalBus.  All 51 tests must pass. | -- |
| V2-M3-012 | Benchmark: Python trie vs Rust trie | perf | Comparative bench: 100 patterns, 10K match calls.  Report p50/p95/p99 latency and throughput. | -- |

---

### V2-M4: Rust Envelope + Ring Buffer

> Port Envelope to Rust with FlatBuffers.  Introduce ring buffer for dispatch.
> Addresses W-05, W-06, W-03.

#### Epic 4.1: Rust Envelope

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M4-001 | Implement Rust `Envelope` struct | task | `#[pyclass(frozen)]` matching all 12 fields (10 V1 + `ttl_ms` + `payload_format`).  `#[pyo3(get)]` on all fields for Python access. | W-05 |
| V2-M4-002 | Implement `Envelope::from_bytes()` via FlatBuffers | task | Zero-copy reader using Rust FlatBuffers generated code.  Returns Rust `Envelope`.  Exposed as `#[staticmethod]`. | W-05, W-06 |
| V2-M4-003 | Implement `Envelope::to_bytes()` via FlatBuffers | task | FlatBuffers builder.  Single allocation for entire envelope. | W-05 |
| V2-M4-004 | Implement `Envelope::with_bus_fields()` in Rust | task | Returns new `Envelope` with stamped `envelope_id`, `sequence`, `created_ns`.  In Rust this is a cheap struct copy (~128 bytes). | W-06 |
| V2-M4-005 | Run all 29 + envelope tests against Rust Envelope | test | Parametrize `test_envelope.py`.  Cross-language round-trip: Python `to_bytes()` -> Rust `from_bytes()` and vice versa. | -- |

#### Epic 4.2: Ring Buffer (Disruptor Pattern)

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M4-006 | Design ring buffer slot layout | design | Fixed-size slots (configurable, default 64KB for max envelope size).  Cache-line padded cursors (`#[repr(align(64))]`).  Power-of-2 size for bitwise modulo. | W-03, W-05 |
| V2-M4-007 | Implement `RingBuffer` in Rust | task | `capacity: usize`, `slots: Vec<UnsafeCell<[u8; SLOT_SIZE]>>`, `publisher_cursor: AtomicU64`, `consumer_cursors: Vec<AtomicU64>`.  CAS-based publish. | W-03 |
| V2-M4-008 | Implement publish-side backpressure | task | When ring is full (publisher catches consumer): configurable strategy -- `Block` (spin-wait), `Error(BusFullError)`, `DropOldest`.  Default: Error. | W-21 |
| V2-M4-009 | Implement multi-consumer fan-out read | task | Each subscriber group has its own consumer cursor.  Fan-out = multiple consumer cursors advancing independently.  No copying. | W-03 |
| V2-M4-010 | Expose `RingBuffer` to Python (testing only) | task | `#[pyclass]` for testing: `write(bytes) -> slot_id`, `read(consumer_id) -> bytes`.  Not part of public API. | -- |
| V2-M4-011 | Benchmark: ring buffer vs V1 list append | perf | 10K publishes, compare allocation count, p99 latency, throughput. | W-03 |

---

### V2-M5: Rust LocalBus Core

> The big one.  Port LocalBus routing core to Rust.
> Addresses W-01, W-02, W-07, W-08, W-09, W-14, W-22.

#### Epic 5.1: Stamp + Route Path

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M5-001 | Implement `AtomicU64` envelope ID generator | task | `AtomicU64::fetch_add(1, Ordering::Relaxed)`.  No lock, no GIL.  Global monotonic across all topics. | W-08 |
| V2-M5-002 | Implement per-topic `AtomicU64` sequence generator | task | `DashMap<String, AtomicU64>`.  Per-topic monotonic.  Get-or-insert with `entry()` API.  Zero contention across topics. | W-08 |
| V2-M5-003 | Implement `RustBus::publish()` | task | Steps: (1) validate topic, (2) stamp via atomics, (3) write to ring buffer, (4) GIL release during trie match, (5) check timing chain, (6) fan-out dispatch.  Return `envelope_id: u64`. | W-07, W-09 |
| V2-M5-004 | Implement topic validation at publish time | task | Reject empty topics, empty segments, and topics with only dots.  Return `Err(InvalidTopic)`.  Catches malformed topics BEFORE stamping. | W-14 |
| V2-M5-005 | Implement TTL check at dispatch time | task | If `envelope.ttl_ms > 0` and `now_ns - created_ns > ttl_ms * 1_000_000`, route to DLQ instead of handlers.  Zero cost when TTL=0. | W-20 |

#### Epic 5.2: Handler Dispatch

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M5-006 | Implement fan-out dispatch with GIL batching | task | Collect all handler IDs from trie match (no GIL).  Acquire GIL once.  Invoke all Python handlers in batch.  Release GIL.  Minimizes GIL acquisitions per publish. | W-01, W-09 |
| V2-M5-007 | Implement per-handler error isolation | task | `catch_unwind()` around each `handler.call1()`.  Record success/fail in circuit breaker.  Log error.  Never propagate. | W-25 |
| V2-M5-008 | Implement handler latency tracking | task | `Instant::now()` before/after each handler call.  Store in `DashMap<u64, LatencyHistogram>` (per handler_id).  Expose via `handler_stats() -> dict[str, dict]`. | W-19 |
| V2-M5-009 | Implement publish-side backpressure signal | task | `RustBus::publish()` returns `Result<u64, BusError>`.  `BusError::Full` when ring buffer is at capacity.  Python side maps to `BusFullError` exception. | W-21 |

#### Epic 5.3: Subscribe/Unsubscribe

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M5-010 | Implement `RustBus::subscribe()` | task | Calls `TopicTrie::insert()`.  Invalidates subscription cache.  Returns `SubscriptionHandle(u64)`.  Stores `PyObject` handler in internal map. | -- |
| V2-M5-011 | Implement `RustBus::unsubscribe()` | task | Calls `TopicTrie::remove()`.  Invalidates subscription cache.  Drops `PyObject` handler.  Returns `bool`. | -- |
| V2-M5-012 | Emit subscription lifecycle events | task | On subscribe: `RustBus` internally publishes to `k1.bus.subscription.created` with metadata.  On unsubscribe: `k1.bus.subscription.removed`.  Uses internal fast-path (no ring buffer, direct dispatch). | W-23 |

#### Epic 5.4: Observability

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M5-013 | Implement `AtomicU64` bus stats | task | Replace Python `BusStats` dataclass with Rust atomic counters.  `Ordering::Relaxed` for all -- approximate is fine.  Expose `stats() -> dict` to Python. | W-22 |
| V2-M5-014 | Implement `RustBus.__repr__()` | task | Match V1 format: `RustBus(subscriptions=N, published=N, ...)`. | -- |
| V2-M5-015 | Run all 51 LocalBus tests against RustBus | test | Parametrize.  All tests pass identically. | -- |
| V2-M5-016 | Run all 9 integration tests against RustBus | test | Cross-module tests with RustBus backend.  All pass. | -- |

---

### V2-M6: Rust TimingChain + WFQ

> Port timing chain and implement true deficit round-robin WFQ.
> Addresses W-02, W-10, W-15.

#### Epic 6.1: Rust CausalTracker

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M6-001 | Implement lock-free `CausalTracker` | task | `DashMap<u64, Vec<BufferedEnvelope>>` for pending children.  `DashSet<u64>` for delivered IDs.  Per-parent granularity, no global lock. | W-10 |
| V2-M6-002 | Implement causal cascade delivery | task | `mark_delivered(id)` returns children.  Recursive cascade as in V1 but without global lock re-acquisition on each step. | W-10 |
| V2-M6-003 | Implement bounded buffer with emergency release | task | `AtomicUsize` for total buffer size.  When > limit, `force_release_oldest()` drops oldest 10%. | W-10 |

#### Epic 6.2: Rust GapBuffer

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M6-004 | Implement per-topic `GapBuffer` | task | `DashMap<String, TopicGapState>` where `TopicGapState` has `expected: AtomicU64` + `BTreeMap<u64, BufferedEnvelope>`.  Per-topic lock via `DashMap` entry. | -- |
| V2-M6-005 | Implement gap fill + successor release | task | Same logic as V1 `check_and_buffer()` but using `BTreeMap::range()` for efficient successor scan instead of linear while-loop. | -- |
| V2-M6-006 | Implement per-topic buffer limit | task | `AtomicUsize` per topic.  Force-release when exceeded. | -- |

#### Epic 6.3: Rust TimingConfig (Prefix Trie)

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M6-007 | Replace linear scan with prefix trie | task | V1 `TimingConfig.resolve()` does longest-prefix match via sorted list.  Replace with trie for O(k) lookup instead of O(n*k). | -- |
| V2-M6-008 | Implement runtime reload via `Arc<RwLock>` | task | `reload()` swaps inner trie atomically.  Readers never block on reload. | -- |

#### Epic 6.4: Deficit Round-Robin WFQ

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M6-009 | Implement `WfqScheduler` in Rust | task | 4 queues (URGENT/REALTIME/INTERACTIVE/BACKGROUND).  Deficit counters `[AtomicI64; 4]`.  `next() -> Option<Envelope>` returns from highest-deficit non-empty queue. | W-02, W-15 |
| V2-M6-010 | Configurable weights per priority | task | Default weights: `[4, 3, 2, 1]`.  Configurable via `WfqConfig`.  Hot-reloadable via `Arc<AtomicU64>` per weight. | W-02 |
| V2-M6-011 | Integrate WFQ into publish dispatch | task | After trie match, envelopes enter WFQ scheduler before handler invocation.  Under no contention, WFQ is zero-cost passthrough. | W-02 |
| V2-M6-012 | Integrate WFQ into mailbox dequeue | task | Replace strict priority dequeue in `LocalMailbox` with `WfqScheduler`.  BACKGROUND always makes progress. | W-15 |
| V2-M6-013 | Run all 119 timing tests against Rust impl | test | Parametrize.  All pass. | -- |
| V2-M6-014 | Starvation test: sustained URGENT flood | test | Publish 10K URGENT + 100 BACKGROUND.  Assert BACKGROUND delivered within N rounds (not starved to zero). | W-15 |

---

### V2-M7: Rust Mailbox + DLQ

> Port mailbox to Rust with true WFQ.  Add dead-letter queue.
> Addresses W-15, W-16, W-17, W-18.

#### Epic 7.1: Rust LocalMailbox

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M7-001 | Implement `RustMailbox` with ring buffer per priority | task | 4 bounded ring buffers (one per priority) inside each mailbox.  Uses `WfqScheduler` from V2-M6 for dequeue. | W-15, W-18 |
| V2-M7-002 | Implement async `receive()` via `crossbeam::channel` | task | Replace `threading.Condition.wait()` with `crossbeam::channel::recv_timeout()`.  Python side calls `receive()` which releases GIL during wait. | W-18 |
| V2-M7-003 | Implement delivery acknowledgment | task | `receive()` returns `(Envelope, AckHandle)`.  Sender can call `ack_handle.wait(timeout)` to block until consumer acks.  Optional -- default still fire-and-forget. | W-17 |
| V2-M7-004 | Implement `RustMailboxRouter` | task | `DashMap<String, Arc<RustMailbox>>`.  Lock-free lookup.  `deliver()` never blocks on registry lock. | -- |

#### Epic 7.2: Dead-Letter Queue

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M7-005 | Implement `DeadLetterQueue` in Rust | task | Bounded ring buffer of `(Envelope, DlqReason)`.  Reasons: `BackpressureFull`, `HandlerError`, `TtlExpired`, `CircuitOpen`, `MiddlewareDropped`.  FIFO drain from Python. | W-16, W-28 |
| V2-M7-006 | Route backpressure rejects to DLQ | task | When mailbox is full, envelope goes to DLQ instead of (or in addition to) raising `BackpressureError`.  Configurable: `dlq_only` or `dlq_and_raise`. | W-16 |
| V2-M7-007 | Route expired TTL envelopes to DLQ | task | Envelopes failing TTL check in `RustBus::publish()` go to DLQ with reason `TtlExpired`. | W-20, W-16 |
| V2-M7-008 | Expose DLQ to Python | task | `dlq.drain() -> list[tuple[Envelope, str]]`.  `dlq.depth -> int`.  `dlq.peek(n) -> list[...]`. | W-16 |
| V2-M7-009 | Run all 58 mailbox tests against Rust impl | test | Parametrize.  All pass. | -- |
| V2-M7-010 | DLQ integration test | test | Fill mailbox, attempt delivery, verify DLQ captured the rejected envelope with correct reason. | W-16 |

---

### V2-M8: Async Dispatch + Circuit Breaker

> Decouple publish from handler execution.  Add per-handler circuit breaker.
> Addresses W-01, W-25, W-27.

#### Epic 8.1: Async Handler Dispatch

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M8-001 | Implement dispatch thread pool in Rust | task | `rayon::ThreadPool` with configurable size (default: num_cpus).  Publisher writes to ring buffer and returns immediately.  Dispatch threads read from ring buffer and invoke handlers. | W-01 |
| V2-M8-002 | Implement sync/async dispatch modes | task | `BusConfig::dispatch_mode` = `Sync` (V1 behavior, publish blocks on handlers) or `Async` (publisher returns immediately, dispatch on thread pool).  Default: `Sync` for backward compat. | W-01 |
| V2-M8-003 | Implement GIL acquisition strategy for async | task | Async dispatch thread acquires GIL in batches (N handlers per GIL acquisition).  Configurable batch size.  Minimizes GIL contention. | W-01, W-09 |
| V2-M8-004 | Ordering guarantee in async mode | task | Within a single topic, handlers see envelopes in sequence order (ring buffer is ordered).  Cross-topic ordering governed by TimingChain (causal + gap). | W-01 |

#### Epic 8.2: Circuit Breaker

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M8-005 | Implement per-handler `CircuitBreaker` | task | States: `Closed` (normal), `Open` (skipping), `HalfOpen` (probing).  Transition: N consecutive failures -> Open for cooldown_ms -> HalfOpen (try 1) -> Closed or re-Open. | W-25 |
| V2-M8-006 | Configurable circuit breaker thresholds | task | `failure_threshold: u32 = 5`, `cooldown_ms: u64 = 10_000`, `probe_interval: u32 = 1`.  Per-handler or global default. | W-25 |
| V2-M8-007 | Expose circuit breaker state to Python | task | `bus.handler_circuits() -> dict[str, str]` (handler pattern -> state).  `bus.reset_circuit(handler_id)`. | W-25 |

#### Epic 8.3: Built-in Sweep Timer

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M8-008 | Implement auto-sweep thread in Rust | task | Dedicated thread with `thread::park_timeout(Duration::from_secs(1))`.  Calls `timing_chain.sweep()` on wake.  Auto-starts when TimingChain is configured.  `Drop` impl joins thread. | W-27 |
| V2-M8-009 | Configurable sweep interval | task | `TimingChainConfig::sweep_interval_ms: u64 = 1000`.  Changeable at runtime via atomic. | W-27 |
| V2-M8-010 | Remove external `bus.sweep()` requirement | task | `LocalBus.sweep()` becomes a no-op when Rust auto-sweep is active.  Still callable for manual testing. | W-27 |

---

### V2-M9: Integration + Factory Switch

> Wire everything together.  Factory transparently switches between Python and Rust.

#### Epic 9.1: Factory Upgrade

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M9-001 | Update `BusFactory.create_local()` with Rust backend | task | `try: from k1_bus_core import RustBus; return RustBus(...)` with `except ImportError` fallback to Python `LocalBus`. | -- |
| V2-M9-002 | Update `BusFactory.create_for_testing()` with Rust backend | task | Rust backend with capture mode.  `RustBus(capture=True)` pre-allocates capture ring buffer. | -- |
| V2-M9-003 | Add `BusFactory.create_local(backend="python"/"rust"/"auto")` | task | Explicit backend selection for testing and debugging.  `"auto"` (default) prefers Rust. | -- |
| V2-M9-004 | Update `BusFactory.create_mailbox_router()` with Rust backend | task | Same import-switch pattern for `RustMailboxRouter`. | -- |

#### Epic 9.2: Full Integration Validation

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M9-005 | Run ALL 446 V1 tests against full Rust backend | test | Complete test suite.  Zero behavioral differences.  All pass. | -- |
| V2-M9-006 | Run ALL tests against Python fallback (no Rust) | test | CI job without Rust crate installed.  All pass (validates fallback). | -- |
| V2-M9-007 | Cross-module integration: Fabric adapter + RustBus | test | FabricBusAdapter works identically with RustBus backend. | -- |
| V2-M9-008 | Cross-module integration: Session adapter + RustBus | test | SessionBusAdapter works identically with RustBus backend. | -- |

---

### V2-M10: Benchmarks + Production Hardening

> Performance validation.  Stress testing.  Documentation.

#### Epic 10.1: Benchmarks

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M10-001 | Micro-benchmark: publish-to-handler latency | perf | 1 subscriber, 100K envelopes.  Measure p50/p95/p99/p999.  Compare V1 vs V2. | -- |
| V2-M10-002 | Micro-benchmark: trie match throughput | perf | 100 patterns, 100K topics.  Cached vs uncached.  Compare V1 vs V2. | -- |
| V2-M10-003 | Micro-benchmark: mailbox send-receive latency | perf | 1 sender, 1 receiver, 100K envelopes.  All 4 priority levels.  Compare V1 vs V2. | -- |
| V2-M10-004 | Macro-benchmark: full system throughput | perf | Fabric + Session + raw subscribers, 50 subscriptions, 4 priority levels, timing chain enabled.  Measure max sustained envelopes/sec. | -- |
| V2-M10-005 | Macro-benchmark: WFQ fairness under load | perf | 10K URGENT + 1K REALTIME + 100 INTERACTIVE + 10 BACKGROUND.  Measure per-priority delivery latency percentiles.  Verify no starvation. | W-02, W-15 |
| V2-M10-006 | Stress test: 1M envelopes, 100 subscribers | perf | Sustained 1M publishes.  Monitor memory, GC pauses, DLQ depth, circuit breaker activations. | -- |

#### Epic 10.2: Production Hardening

| Issue | Title | Type | Description | Fixes |
|---|---|---|---|---|
| V2-M10-007 | Memory leak test: 24h soak | test | Run bus under sustained load for 24h.  Monitor RSS.  No unbounded growth. | -- |
| V2-M10-008 | Thread safety: `loom` model checking | test | Use `loom` crate to model-check `RustBus` publish/subscribe/unsubscribe concurrency.  No data races. | W-07, W-09 |
| V2-M10-009 | Update `k1-bus-implementation-plan.md` with V2 results | docs | Performance comparison table.  Architecture decision records for V2 choices. | -- |

---

## 5. Performance Targets

| Metric | V1 (Python) | V2 Target (Rust) | Improvement |
|---|---|---|---|
| Publish-to-handler (p50) | ~100us | < 5us | 20x |
| Publish-to-handler (p99) | ~500us | < 20us | 25x |
| Trie match (100 subs, cached) | ~50us | < 0.1us | 500x |
| Trie match (100 subs, cold) | ~50us | < 2us | 25x |
| Envelope stamp | ~5us | < 0.05us | 100x |
| Envelope `to_bytes()` (FlatBuffers) | ~10us (JSON) | < 0.5us | 20x |
| Envelope `from_bytes()` (FlatBuffers) | ~10us (JSON) | < 0.1us (zero-copy) | 100x |
| Mailbox send-receive | ~100us | < 2us | 50x |
| Max sustained throughput | 10K env/sec | 500K+ env/sec | 50x |
| Memory per envelope | ~800B | ~128B (FlatBuffers) | 6x less |
| WFQ starvation | INFINITE (strict priority) | ZERO (deficit round-robin) | -- |
| GC pressure (10K msg/sec) | ~8MB/sec churn | ~0 (ring buffer reuse) | -- |

---

## 6. Risk Matrix

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| PyO3 GIL contention bottleneck | Medium | High | Batch GIL acquisitions.  Async dispatch decouples publishers from handlers.  GIL released during all Rust computation. |
| FlatBuffers schema migration breaks V1 compat | Low | High | V1 `Envelope.to_bytes()`/`from_bytes()` kept as fallback.  `ENVELOPE_FORMAT` config toggle.  Cross-language round-trip tests. |
| `maturin` build complexity for contributors | Medium | Medium | Python-only fallback always works.  Rust build optional.  Docker image pre-builds Rust crate. |
| `crossbeam_epoch` reclamation latency spikes | Low | Medium | Fallback to parking_lot RwLock if epoch-based cleanup causes p999 outliers.  Benchmark both approaches. |
| Ring buffer size tuning | Medium | Low | Configurable capacity.  Default 8192 slots.  Monitoring: `ring_buffer.utilization()` exposed to Python. |
| Rust compile times slow CI | Medium | Low | Cache `target/` directory in CI.  `sccache` for incremental builds.  Rust tests run in parallel. |
| Python fallback diverges from Rust behavior | Low | High | Parametrized test suite runs ALL tests against BOTH backends.  CI enforces identical behavior. |

---

## 7. Migration Strategy

### 7.1 Phased Rollout (No Big Bang)

```text
V1 (today)     V2-Phase1        V2-Phase2        V2-Phase3          V2-Full
===========    ===========      ===========      ===========        ===========
All Python     FlatBuffers      Rust Trie +      Rust Bus +         All Rust
               (Python FB)      Envelope         TimingChain +      internals
                                (Rust PyO3)      Mailbox + WFQ
                                                 + Async Dispatch

Tests:  446    Tests: 446+      Tests: 446+      Tests: 446+        Tests: 446+
Backend: Py    Backend: Py       Backend: mixed   Backend: Rust      Backend: Rust
                                 (trie=Rust,      (everything        Fallback: Py
                                  bus=Python)      except ports/
                                                   adapters/mw)
```

### 7.2 Backward Compatibility Contract

1. **Zero module code changes**: Fabric, SessionState, Orchestrator, Planner, Concierge -- none of these change.
2. **Python V1 is permanent fallback**: `BusFactory` auto-detects Rust availability.  `import k1_bus_core` fails -> Python backend used.
3. **All V1 tests = V2 acceptance tests**: Every single one of the 446 tests serves as the behavioral contract.  V2 passes if and only if all V1 tests pass against the Rust backend.
4. **Parametrized test matrix**: `@pytest.fixture(params=["python", "rust"])` on all test classes.  CI runs both.
5. **No API changes**: `IBus`, `IMailbox`, `IMailboxRouter`, `Envelope`, `SubscriptionHandle` -- all unchanged.  New features (TTL, DLQ, circuit breaker, WFQ) are additive.

### 7.3 Dependency Additions (V2)

| Crate | Purpose | License |
|---|---|---|
| `pyo3 0.22+` | Python <-> Rust FFI | Apache-2.0 / MIT |
| `flatbuffers 24.3+` | Zero-copy serialization | Apache-2.0 |
| `crossbeam 0.8+` | Lock-free concurrent primitives | Apache-2.0 / MIT |
| `dashmap 6+` | Concurrent HashMap | MIT |
| `parking_lot 0.12+` | Fast RwLock / Mutex | Apache-2.0 / MIT |
| `rayon 1.10+` | Thread pool for async dispatch | Apache-2.0 / MIT |

| Python Package | Purpose | License |
|---|---|---|
| `maturin 1.7+` | Rust build tool for PyO3 | MIT |
| `flatbuffers 24.3+` | Python FlatBuffers runtime | Apache-2.0 |

---

## Appendix A: Issue Priority Matrix

| Priority | Issues | Criteria |
|---|---|---|
| P0 (Critical) | V2-M5-003, V2-M5-006, V2-M6-009 | Core publish path, GIL strategy, WFQ -- defines V2 identity |
| P1 (High) | V2-M3-001 to 005, V2-M4-001 to 004, V2-M6-001 to 006 | Trie, Envelope, TimingChain -- hot path components |
| P2 (Medium) | V2-M1-*, V2-M2-*, V2-M7-*, V2-M8-* | Schema, CI, Mailbox, Async -- important but not gating |
| P3 (Low) | V2-M9-*, V2-M10-* | Integration, benchmarks -- final validation |

## Appendix B: V1 Weakness to V2 Issue Traceability

| Weakness | V2 Issues |
|---|---|
| W-01 Sync dispatch | V2-M8-001, V2-M8-002, V2-M8-003, V2-M8-004 |
| W-02 No true WFQ pub/sub | V2-M6-009, V2-M6-010, V2-M6-011, V2-M6-014 |
| W-03 No dispatch batching | V2-M4-006, V2-M4-007, V2-M4-009 |
| W-04 JSON serialization | V2-M1-001 to 005, V2-M1-007 |
| W-05 Python object overhead | V2-M4-001 to 004 |
| W-06 `with_bus_fields()` copy | V2-M4-004 |
| W-07 Python RWLock | V2-M5-003, V2-M10-008 |
| W-08 Per-topic lock contention | V2-M5-001, V2-M5-002 |
| W-09 GIL prevents parallelism | V2-M5-003, V2-M5-006, V2-M8-001, V2-M8-003 |
| W-10 CausalTracker global lock | V2-M6-001, V2-M6-002, V2-M6-003 |
| W-11 Match allocates list | V2-M3-001, V2-M3-003 |
| W-12 No subscription cache | V2-M3-006, V2-M3-007, V2-M3-008 |
| W-13 Tombstone compaction | V2-M3-004 |
| W-14 No publish-time validation | V2-M5-004 |
| W-15 Strict priority starvation | V2-M6-009, V2-M6-012, V2-M6-014 |
| W-16 No dead-letter queue | V2-M7-005, V2-M7-006, V2-M7-007, V2-M7-008 |
| W-17 No delivery ack | V2-M7-003 |
| W-18 Mailbox blocks thread | V2-M7-002 |
| W-19 No per-handler latency | V2-M5-008 |
| W-20 No envelope TTL | V2-M1-006, V2-M5-005, V2-M7-007 |
| W-21 No pub/sub backpressure | V2-M4-008, V2-M5-009 |
| W-22 Approximate stats | V2-M5-013 |
| W-23 No subscription events | V2-M5-012 |
| W-24 No middleware ordering | (deferred -- low impact) |
| W-25 No circuit breaker | V2-M8-005, V2-M8-006, V2-M8-007 |
| W-26 No replay | (deferred to V3 -- requires persistence) |
| W-27 External sweep timer | V2-M8-008, V2-M8-009, V2-M8-010 |
| W-28 No publish retry on MW fail | V2-M7-005 (DLQ captures) |

---

*End of V2 Plan.  This document is the single source of truth for the V1 -> V2 migration.*
