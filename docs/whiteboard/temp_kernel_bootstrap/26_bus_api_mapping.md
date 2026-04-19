# Bus — Formal API Mapping

> Generated: 2025-07-12 · Scope: Every port, implementation, adapter, middleware, envelope, timing, and factory surface in `k1/bus/`
>
> **Updated for Phase 6 (branch `bus-hardening`, HEAD `7164a26`); P6.10 (model_hub timing rules in YAML) still open.**
>
> Phase 6 additions covered below: `IBus.flush`, async dispatch + DLQ on `LocalBus`, durable replay via `BusOutbox`, payload validators on `TopicRegistry`, strict schema mode on `TopicValidationMiddleware`, new `IdempotencyMiddleware`, P6.1/P6.2/P6.3 fixes for `AsyncBusBridge` and `RustBusAdapter`, P6.8 / P6.9 topic renames.

---

## 0. Package Topology

```
k1/bus/
├── ports/          3 port protocols (IBus, IMailbox/IMailboxRouter, IAsyncBus/IAsyncMailbox/IAsyncMailboxRouter)
├── impl/           LocalBus, LocalMailbox, LocalMailboxRouter, TopicTrie, Rust adapters
├── envelope/       Envelope dataclass, Priority, DeliveryMode, PayloadFormat, FlatBuffers V2
├── middleware/      Middleware protocol, MiddlewareChain, Metrics, TopicValidation, Tracing
├── timing/         TimingConfig, TimingChain, TimingStats, DeliveryMode rules
├── adapters/       FabricBusAdapter, SessionBusAdapter
├── factory.py      BusFactory (4 static methods)
├── config.py       BusConfig, load_bus_config() from YAML
├── async_bridge.py AsyncBusBridge, AsyncMailboxBridge, AsyncMailboxRouterBridge
└── __init__.py     42 public symbols
```

**Public symbols** (from `__all__`, 42 total):
`Envelope`, `Priority`, `DeliveryMode`, `PayloadFormat`, `IBus`, `SubscriptionHandle`, `BusHandler`, `IAsyncBus`, `IAsyncMailbox`, `IAsyncMailboxRouter`, `AsyncBusHandler`, `AsyncBusBridge`, `AsyncMailboxBridge`, `AsyncMailboxRouterBridge`, `LocalBus`, `BusFactory`, `BusStats`, `TopicTrie`, `IMailbox`, `IMailboxRouter`, `MailboxConfig`, `BackpressureError`, `UnknownActorError`, `LocalMailbox`, `LocalMailboxRouter`, `Middleware`, `MiddlewareChain`, `TracingMiddleware`, `MetricsMiddleware`, `TopicRegistry`, `TopicValidationMiddleware`, `FabricBusAdapter`, `SessionBusAdapter`, `BusConfig`, `load_bus_config`, `TimingChain`, `TimingConfig`, `TimingStats`, `default_timing_config`, `DEFAULT_RULES`, `DEFAULT_MODE`

---

## 1. Envelope — The Wire Unit

### 1.1 Enums

#### `Priority(IntEnum)`

| Member | Value | WFQ Weight |
| --- | --- | --- |
| `URGENT` | 0 | 4× |
| `REALTIME` | 1 | 3× |
| `INTERACTIVE` | 2 | 2× |
| `BACKGROUND` | 3 | 1× |

#### `DeliveryMode(IntEnum)`

| Member | Value | Behaviour |
| --- | --- | --- |
| `STRICT` | 0 | Ordered delivery, buffer on sequence gap, causal wait |
| `RELAXED` | 1 | Deliver as-is, log reorder (monitoring only) |
| `BEST_EFFORT` | 2 | Deliver immediately, drop OK under pressure |

#### `PayloadFormat(IntEnum)`

| Member | Value | Description |
| --- | --- | --- |
| `OPAQUE` | 0 | Raw bytes, adapter must interpret |
| `JSON` | 1 | JSON-encoded UTF-8 |
| `MSGPACK` | 2 | MessagePack-encoded |

### 1.2 `Envelope` Dataclass (frozen)

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `topic` | `str` | `""` | Hierarchical dot-separated topic |
| `priority` | `int` | `Priority.INTERACTIVE` (2) | WFQ scheduling priority 0–3 |
| `envelope_id` | `int` | `0` | Global monotonic ID (stamped by bus) |
| `sequence` | `int` | `0` | Per-topic monotonic sequence (stamped by bus) |
| `cognitive_trace_id` | `str` | `""` | Cross-K0/K1 correlation key |
| `session_id` | `str` | `""` | Session scope |
| `request_id` | `str` | `""` | Request scope within session |
| `parent_id` | `int` | `0` | Causal parent envelope_id (0 = root) |
| `created_ns` | `int` | `0` | Monotonic clock timestamp in ns (stamped by bus) |
| `payload` | `bytes` | `b""` | Opaque payload bytes |
| `ttl_ms` | `int` | `0` | Time-to-live ms (0 = no expiry) — V2 |
| `payload_format` | `int` | `PayloadFormat.OPAQUE` (0) | Payload type hint — V2 |

**Validation (`__post_init__`)**: `topic` must be `str`; `payload` must be `bytes|bytearray`; `priority` in {0,1,2,3}; `envelope_id >= 0`; `sequence >= 0`; `parent_id >= 0`; `ttl_ms >= 0`; `payload_format` in {0,1,2}.

**Properties:**

| Property | Returns | Description |
| --- | --- | --- |
| `payload_len` | `int` | `len(self.payload)` |
| `priority_enum` | `Priority` | `Priority(self.priority)` |
| `payload_format_enum` | `PayloadFormat` | `PayloadFormat(self.payload_format)` |
| `is_root` | `bool` | `parent_id == 0` |
| `is_expired` | `bool` | `ttl_ms > 0` |

**Methods:**

| Method | Signature | Description |
| --- | --- | --- |
| `to_bytes` | `() → bytes` | Serialize; dispatches V1 or V2 based on `K1_ENVELOPE_FORMAT` env var |
| `from_bytes` | `(cls, data: bytes) → Envelope` | Deserialize; auto-detects V1/V2 by `b"FB02"` magic prefix |
| `with_bus_fields` | `(envelope_id, sequence, created_ns) → Envelope` | Returns NEW envelope with bus-assigned fields stamped |

### 1.3 Wire Formats

| Format | Header | Encoding | Zero-Copy |
| --- | --- | --- | --- |
| V1 | `[4B header_len][JSON header][raw payload]` | JSON + raw bytes | No |
| V2 | `[b"FB02"][FlatBuffers table]` | FlatBuffers (12-field table) | Yes (payload) |

`K1_ENVELOPE_FORMAT` env var controls `to_bytes()` output (`"v1"` or `"v2"`, default `"v2"`). `from_bytes()` auto-detects.

---

## 2. Port Protocols

### 2.1 `IBus` — Pub/Sub Event Lane

```python
@runtime_checkable
class IBus(Protocol):
    def publish(self, envelope: Envelope) -> None: ...
    def subscribe(
        self,
        pattern: str,
        handler: BusHandler,
        *,
        consumer_id: str | None = None,
    ) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
    def flush(self, timeout_ms: int = 5000) -> bool: ...  # P6
```

See [k1/bus/ports/bus.py](k1/bus/ports/bus.py).

**Type alias**: `BusHandler = Callable[[Envelope], None]`

**`SubscriptionHandle`** (frozen dataclass): `subscription_id: str`, `pattern: str`

**`flush(timeout_ms=5000) -> bool`** (Phase 6): Block until in-flight envelopes have been delivered to all subscribed handlers. Sync implementations may return `True` immediately; async-dispatch / Rust implementations drain their internal queues. Returns `False` on timeout. MUST NOT raise for normal payloads.

**`subscribe(..., consumer_id=...)`** (Phase 6): Optional keyword-only argument. When set on a `LocalBus` configured with an outbox + durable topic, the bus wraps the handler in an `_acking_handler` shim that calls `outbox.ack(consumer_id, topic, envelope_id)` after the handler returns successfully — providing at-least-once semantics with replay support.

**Invariants:**

- Thread-safe implementations required
- Handlers invoked on dispatch thread or caller's thread
- Handler exceptions MUST be caught, logged, MUST NOT propagate to publisher
- `publish()` MUST NOT raise for normal payloads
- Bus stamps `envelope_id` (global monotonic), `sequence` (per-topic monotonic), `created_ns` (monotonic clock)
- Original envelope NOT mutated; handlers receive a NEW envelope
- Topic matching: exact + prefix wildcard (`*`) + greedy wildcard (`>`)

### 2.2 `IMailbox` / `IMailboxRouter` — Actor Mailbox Lane

```python
@runtime_checkable
class IMailbox(Protocol):
    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]: ...
    def pending(self) -> int: ...

@runtime_checkable
class IMailboxRouter(Protocol):
    def deliver(self, actor_id: str, envelope: Envelope) -> None: ...
    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox: ...
    def unregister(self, actor_id: str) -> bool: ...
    def registered_actors(self) -> list[str]: ...
```

**`MailboxConfig`** (frozen dataclass): `capacity: int = 256`, `priority_wfq: bool = True`. Raises `ValueError` if `capacity <= 0`.

**Exceptions:**

| Exception | Raised When |
| --- | --- |
| `BackpressureError(actor_id, capacity)` | Mailbox at capacity |
| `UnknownActorError(actor_id)` | Actor not registered |

**Invariants:**

- At-least-once delivery (vs at-most-once for IBus)
- Per-actor bounded queue with backpressure
- WFQ priority across actors
- Point-to-point (unicast) vs IBus pub/sub (multicast)
- `deliver()` raises `UnknownActorError` / `BackpressureError`
- `register()` raises `ValueError` for already-registered actor_id
- `unregister()` discards pending envelopes

### 2.3 `IAsyncBus` / `IAsyncMailbox` / `IAsyncMailboxRouter` — Async Variants

```python
@runtime_checkable
class IAsyncBus(Protocol):
    async def publish(self, envelope: Envelope) -> None: ...
    async def subscribe(self, pattern: str, handler: AsyncBusHandler) -> SubscriptionHandle: ...
    async def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...

@runtime_checkable
class IAsyncMailbox(Protocol):
    async def receive(self, timeout_ms: int = 0) -> Optional[Envelope]: ...
    def pending(self) -> int: ...  # sync, lock-free

@runtime_checkable
class IAsyncMailboxRouter(Protocol):
    async def deliver(self, actor_id: str, envelope: Envelope) -> None: ...
    async def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IAsyncMailbox: ...
    async def unregister(self, actor_id: str) -> bool: ...
    def registered_actors(self) -> list[str]: ...  # sync, lock-free
```

**Type alias**: `AsyncBusHandler = Callable[[Envelope], Coroutine[Any, Any, None]]`

---

## 3. Implementations

### 3.1 `LocalBus`

In-memory bus with read-write lock, topic trie, optional timing chain, middleware, async dispatch, DLQ, and durable outbox replay. See [k1/bus/impl/local_bus.py](k1/bus/impl/local_bus.py).

**Constructor** (Phase 6, all keyword-only):

```python
LocalBus(
    *,
    capture: bool = False,
    timing_chain: TimingChain | None = None,
    middleware: MiddlewareChain | None = None,
    async_dispatch: bool = False,                  # P6: per-subscription daemon thread + LocalMailbox
    subscription_mailbox_capacity: int = 1024,     # P6: capacity for async-dispatch mailbox
    retry_resolver: Callable[[str], RetryPolicy | None] | None = None,  # P6
    dlq_callback: Callable[[Envelope, BaseException, int], None] | None = None,  # P6
    outbox: BusOutbox | None = None,               # P6: durable persistence
    durable_topics: Iterable[str] | None = None,   # P6: topics persisted to outbox
)
```

**New constructor kwargs (Phase 6)**:

| Kwarg | Type | Default | Purpose |
| --- | --- | --- | --- |
| `async_dispatch` | `bool` | `False` | Run each subscription on its own daemon thread fed by a `LocalMailbox`. Decouples slow handlers from publishers. |
| `subscription_mailbox_capacity` | `int` | `1024` | Bound for the per-subscription mailbox when `async_dispatch=True`. Overflow → `mailbox_full_drops++`. |
| `retry_resolver` | `Callable[[str], RetryPolicy \| None] \| None` | `None` | Returns retry policy per topic for async-dispatch handlers. None = no retries. |
| `dlq_callback` | `Callable[[Envelope, BaseException, int], None] \| None` | `None` | Invoked after retries are exhausted; signature `(envelope, exc, attempts)`. Increments `async_handler_dlq`. |
| `outbox` | `BusOutbox \| None` | `None` | SQLite-backed durable store. Envelopes for durable topics are appended before dispatch. |
| `durable_topics` | `Iterable[str] \| None` | `None` | Topics whose envelopes are persisted to `outbox`. Frozen at construction. |

**New `__slots__` (Phase 6)**: `_async_dispatch`, `_async_capacity`, `_async_subs`, `_async_subs_lock`, `_retry_resolver`, `_dlq_callback`, `_outbox`, `_durable_topics`, `_durable_consumers`, `_durable_consumers_lock`.

**IBus methods**: `publish()`, `subscribe(pattern, handler, *, consumer_id=None)`, `unsubscribe()`, `flush(timeout_ms=5000)` (P6)

**`subscribe(..., consumer_id=...)`** (Phase 6): When `consumer_id` is provided AND the topic is in `durable_topics` AND an outbox is configured, the handler is wrapped by `_acking_handler` which calls `outbox.ack(consumer_id, topic, envelope.envelope_id)` on successful return. The consumer_id is also recorded in `_durable_consumers` for `replay_durable_topics()` to target.

**New methods (Phase 6)**:

| Method | Signature | Description |
| --- | --- | --- |
| `flush` | `(timeout_ms: int = 5000) → bool` | Drains all per-subscription async mailboxes; returns `False` on timeout. No-op (returns `True`) when `async_dispatch=False`. |
| `replay_durable_topics` | `(*, consumer_id: str \| None = None) → int` | Re-dispatches unacked envelopes from the outbox to their durable subscriptions. Returns count replayed. If `consumer_id` is given, only that consumer is replayed. |

**Async dispatch internals**: `_AsyncSubscription` (inner class) owns a daemon thread and a `LocalMailbox` of `subscription_mailbox_capacity`. On publish, the envelope is enqueued; the worker dequeues and invokes the handler with retry policy from `retry_resolver(topic)`. After exhausting retries, `dlq_callback(envelope, exc, attempts)` is invoked and `async_handler_dlq` is incremented.

**IBus methods**: `publish()`, `subscribe()`, `unsubscribe()`

**Publish pipeline** (happy path):

```
validate topic → stamp (envelope_id, sequence, created_ns)
  → middleware chain → capture (if enabled)
    → trie match (READ lock) → dispatch (outside lock)
      → [if timing chain] route through TimingChain
      → [else] call handlers directly
```

**Observability:**

| Property / Method | Returns | Description |
| --- | --- | --- |
| `stats` | `BusStats` | 11-field mutable stats snapshot (P6: +4) |
| `subscription_count` | `int` | Active subscription count |
| `topic_sequence(topic)` | `int` | Current sequence for topic |
| `last_envelope_id` | `int` | Last assigned global ID |
| `timing_chain` | `TimingChain \| None` | Configured timing chain |
| `middleware` | `MiddlewareChain \| None` | Configured middleware |
| `durable_topics` | `frozenset[str]` | P6: Topics persisted to outbox (frozen at construction) |
| `outbox` | `object \| None` | P6: Configured `BusOutbox` instance, if any |

**Testing helpers**: `captured` (property → `list[Envelope]`), `drain() → list[Envelope]`

**Lifecycle**: `close()`, `closed` (property), `sweep() → int` (delegates to timing chain)

**`BusStats`** (mutable dataclass):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `envelopes_published` | `int` | 0 | |
| `envelopes_delivered` | `int` | 0 | |
| `handler_errors` | `int` | 0 | |
| `subscriptions_active` | `int` | 0 | |
| `subscriptions_total` | `int` | 0 | |
| `unsubscribe_count` | `int` | 0 | |
| `topics_seen` | `int` | 0 | |
| `mailbox_full_drops` | `int` | 0 | **P6** — async-dispatch mailbox at capacity; envelope dropped |
| `mailbox_high_water_mark` | `int` | 0 | **P6** — max observed depth across async-dispatch mailboxes |
| `async_handler_retries` | `int` | 0 | **P6** — retries triggered by `retry_resolver` policy |
| `async_handler_dlq` | `int` | 0 | **P6** — envelopes routed to DLQ after retry exhaustion |

**Internal concurrency primitives:**

- `_ReadWriteLock` — readers-writer lock for trie access
- `_SequenceGenerator` — per-topic monotonic sequences (double-checked locking per topic)
- `_EnvelopeIdGenerator` — global monotonic envelope ID

**Invariants:**

- Closed bus silently drops publishes
- Empty topic → logged warning, envelope dropped
- Middleware runs after stamping, before dispatch; returns `None` → dropped
- Capture records after middleware, before dispatch
- Subscribe generates `sub-{uuid.uuid4().hex[:12]}`

### 3.2 `LocalMailbox` / `LocalMailboxRouter`

**`LocalMailbox`** constructor: `LocalMailbox(actor_id: str, config: MailboxConfig)`

| Method | Signature | Description |
| --- | --- | --- |
| `receive` | `(timeout_ms=0) → Optional[Envelope]` | Blocking with Condition wait |
| `pending` | `() → int` | Current queue depth |
| `_deliver` | `(envelope) → None` | Internal; raises `BackpressureError` if full |
| `close` | `() → None` | Prevents new deliveries, allows drain |

**WFQ mode**: 4 sub-queues indexed by `Priority.value` (0–3). Strict priority dequeue: URGENT > REALTIME > INTERACTIVE > BACKGROUND.
**FIFO mode**: Single `deque`.

**Observability**: `actor_id`, `capacity`, `delivered_count`, `received_count`, `depth_by_priority() → dict[str, int]`

**`LocalMailboxRouter`** constructor: `LocalMailboxRouter()`

| Method | Signature | Description |
| --- | --- | --- |
| `deliver` | `(actor_id, envelope) → None` | Looks up mailbox under lock, delivers outside lock |
| `register` | `(actor_id, config?) → LocalMailbox` | Creates and stores mailbox |
| `unregister` | `(actor_id) → bool` | Closes + removes mailbox |
| `registered_actors` | `() → list[str]` | All registered actor IDs |

**Observability**: `actor_count`, `mailbox_for(actor_id)`, `stats_snapshot() → {actor_id: {pending, delivered, received, capacity}}`

### 3.3 `TopicTrie`

Generic trie for hierarchical dot-separated topic matching.

| Method | Signature | Description |
| --- | --- | --- |
| `insert` | `(pattern, handler, subscription_id) → None` | Validates pattern, inserts into trie |
| `remove` | `(subscription_id) → bool` | Tombstones + lazy compact (>50% threshold) |
| `match` | `(topic) → list[T]` | DFS: exact → `*` (one segment) → `>` (greedy) |
| `clear` | `() → None` | Removes all subscriptions |

**Invariants:**

- NOT thread-safe internally (LocalBus wraps with `_ReadWriteLock`)
- `*` matches exactly one segment; `>` matches one or more trailing segments; `>` must be last segment
- Empty patterns / empty segments → `ValueError`
- `_sub_index` maps `subscription_id → (node, idx)` for O(1) removal
- Match complexity: O(k × W) where k = segments, W = wildcard fan-out

### 3.4 Rust Adapters

#### `RustBusAdapter`

Drop-in `IBus` replacement backed by `k1_bus_core` Rust native extension. Raises `ImportError` if Rust unavailable. See [k1/bus/impl/rust_bus_adapter.py](k1/bus/impl/rust_bus_adapter.py).

**Same interface as LocalBus** plus:

- `handler_circuits() → dict[str, str]` — circuit breaker state per pattern
- `reset_circuit(pattern) → bool` — reset circuit breaker
- `flush(timeout_ms: int = 5000) → bool` (**P6**) — returns `True` immediately (Rust dispatches synchronously)

**Phase 6 fixes:**

- **P6.2** — `publish()` now runs `self._middleware.process(envelope)` before `_envelope_to_rust()`. If middleware returns `None`, the envelope is dropped and never crosses the Python→Rust boundary. Previously middleware was stored but never invoked on the Rust path.
- **P6.3** — New slot `_drain_offset: int = 0`. `drain()` returns `captured[_drain_offset:]` and advances `_drain_offset = len(captured)`; the `captured` property slices the same way. This restores LocalBus-equivalent semantics where successive `drain()` calls return only newly captured envelopes (without requiring a Rust-side clear).

**Behavioral differences from LocalBus (post-P6):**

- `sweep()` is a no-op (Rust handles internally)
- Timing chain stored but NOT wired into Rust dispatch (middleware now IS wired — P6.2)

#### `RustMailboxRouterAdapter`

Drop-in `IMailboxRouter` replacement. Same interface as `LocalMailboxRouter`.

**⚠️ Known issue**: `RustMailboxAdapter.receive()` uses keyword-only `timeout_ms` (`*, timeout_ms`) while `IMailbox` protocol declares it positional. Calling `mailbox.receive(100)` positionally will raise `TypeError` with Rust adapter.

**Conversion functions**: `_envelope_to_rust(env) → RustEnvelope`, `_rust_to_envelope(renv) → Envelope` — preserve all fields including `payload_format`.

---

## 4. AsyncBusBridge — Sync-to-Async Bridge

Wraps sync `IBus` / `IMailbox` / `IMailboxRouter` for async callers.

| Class | Wraps | Strategy |
| --- | --- | --- |
| `AsyncBusBridge` | `IBus` → `IAsyncBus` | `asyncio.to_thread` for write ops; async handler → sync shim via `run_coroutine_threadsafe` |
| `AsyncMailboxBridge` | `IMailbox` → `IAsyncMailbox` | `asyncio.to_thread` for `receive`; `pending()` direct passthrough |
| `AsyncMailboxRouterBridge` | `IMailboxRouter` → `IAsyncMailboxRouter` | `asyncio.to_thread` for write ops; `registered_actors()` direct passthrough |

**Constructor**: `AsyncBusBridge(sync_bus: IBus, loop: Optional[asyncio.AbstractEventLoop] = None)` — defaults to `asyncio.get_running_loop()`.

**Invariants:**

- Write/blocking calls offloaded via `asyncio.to_thread`
- Lock-free reads (`pending`, `registered_actors`) are direct pass-throughs
- Event loop captured at construction time

**Phase 6 fix (P6.1):** Async handler exceptions are no longer silently swallowed. `AsyncBusBridge` registers a `Future.add_done_callback` on the `run_coroutine_threadsafe` result that logs the exception and increments `_async_handler_errors`. Exposed via the new property `async_handler_errors → int`. See [k1/bus/async_bridge.py](k1/bus/async_bridge.py).

---

## 5. Middleware

### 5.1 `Middleware` Protocol

```python
@runtime_checkable
class Middleware(Protocol):
    def process(self, envelope: Envelope) -> Optional[Envelope]: ...
```

Returns envelope to continue chain, `None` to drop.

### 5.2 `MiddlewareChain`

| Method | Signature | Description |
| --- | --- | --- |
| `__init__` | `(middlewares: list[Middleware] \| None)` | Copies list or empty |
| `process` | `(envelope) → Optional[Envelope]` | Runs chain in order; short-circuits on `None` |
| `append` | `(middleware) → None` | Adds to end |
| `prepend` | `(middleware) → None` | Inserts at position 0 |
| `size` / `__len__` | `→ int` | Number of middlewares |

### 5.3 `MetricsMiddleware`

**Constructor**: `MetricsMiddleware(*, prefix: str = "k1_bus", enabled: bool = True)`

**Prometheus instruments** (no-op if `prometheus_client` missing):

- Counter: `{prefix}_envelopes_total` — labels: `topic_prefix` (first 2 segments), `priority`
- Histogram: `{prefix}_envelope_latency_seconds` — labels: `topic_prefix`, 9 buckets (100µs–1s)

**`process()`**: Increments counter, records latency. **Never drops**. Returns envelope unchanged.

### 5.4 `TopicValidationMiddleware`

**Constructor** (Phase 6):

```python
TopicValidationMiddleware(
    registry: TopicRegistry,
    *,
    schema_validation_mode: str = "permissive",  # "permissive" | "strict"
)
```

Any value other than `"permissive"` or `"strict"` raises `ValueError` from the constructor. See [k1/bus/middleware/topic_validation.py](k1/bus/middleware/topic_validation.py).

**New type alias (P6)**: `PayloadValidator = Callable[[bytes, Envelope], None]` — validators raise `SchemaValidationError` (or any `Exception`) to signal failure.

**New exception (P6)**: `class SchemaValidationError(ValueError)` — raised by validators registered with `TopicRegistry`.

**Counters (instance properties)**:

| Property | Type | Description |
| --- | --- | --- |
| `warning_count` | `int` | Unknown-topic warnings (existing) |
| `schema_violation_count` | `int` | **P6** — validator raised in `permissive` mode (logged + passed through) |
| `schema_drop_count` | `int` | **P6** — validator raised in `strict` mode (envelope dropped) |

**`TopicRegistry`** methods (Phase 6 — payload validators):

| Method | Signature | Description |
| --- | --- | --- |
| `register` | `(topic: str, validator: PayloadValidator \| None = None) → None` | Exact or wildcard (`*`/`?`). **P6**: optional `validator` stored and resolved by `lookup_validator`. |
| `register_prefix` | `(prefix: str, validator: PayloadValidator \| None = None) → None` | Prefix match. **P6**: optional `validator` (longest-prefix wins). |
| `is_known` | `(topic) → bool` | Checks exact → prefix → wildcard (short-circuit) |
| `lookup_validator` | `(topic: str) → PayloadValidator \| None` | **P6** — Resolution order: exact → longest-prefix → first wildcard `fnmatch`. |
| `unregister` | `(topic) → bool` | Removes from any category. **P6**: also removes the associated validator. |
| `clear` | `() → None` | Removes all topics. **P6**: also clears all validators. |

New slot **`_validators`** stores validator functions keyed parallel to topic/prefix/wildcard registries.

**`process(envelope)` behavior (Phase 6)**:

1. **Unknown topic** → log a warning, increment `warning_count`. Envelope still proceeds to validator lookup.
2. **Validator lookup** via `registry.lookup_validator(topic)`. If a validator exists, invoke it.
3. **Validator raises** in `"strict"` mode → log error, increment `schema_drop_count`, **return `None` (drop envelope)**.
4. **Validator raises** in `"permissive"` mode → log warning, increment `schema_violation_count`, **return envelope (pass through)**.
5. **Validator returns normally** → envelope passes through unchanged.

### 5.5 `IdempotencyMiddleware` (Phase 6 — NEW)

Opt-in middleware that drops duplicate envelopes by `(topic, request_id)` within a TTL window. **Stdlib only** (no external dependencies — `OrderedDict` + `threading.Lock` + `time.monotonic`). NOT included in the default middleware chain. See [k1/bus/middleware/idempotency.py](k1/bus/middleware/idempotency.py).

**Constructor**:

```python
IdempotencyMiddleware(max_entries: int = 10_000, ttl_s: float = 300.0)
```

**Methods**:

| Method | Signature | Description |
| --- | --- | --- |
| `process` | `(envelope) → Envelope \| None` | Drops duplicates by `(topic, request_id)` within TTL. Empty `request_id` bypasses dedup and always passes through. |
| `clear` | `() → None` | Test helper — empties the cache. |

**Counters (properties)**:

| Property | Description |
| --- | --- |
| `drop_count` | Envelopes dropped as duplicates |
| `pass_count` | Envelopes that passed through (key not yet seen or TTL expired) |
| `no_key_count` | Envelopes that bypassed dedup due to empty `request_id` |
| `cache_size` | Current entries in the LRU cache |

**Behavior**:

- Cache is a bounded `OrderedDict` of size `max_entries`; oldest entry evicted on insert when full.
- Each entry stores the insertion `monotonic()` time; on lookup, entries older than `ttl_s` are treated as misses (and overwritten).
- All mutations protected by a single `threading.Lock`.
- Empty `request_id` (`""`) is the documented bypass — used for events that legitimately fan out (e.g., metrics) and must never be deduplicated.

### 5.6 `TracingMiddleware`

**Constructor**: `TracingMiddleware(*, tracer_name: str = "k1.bus", enabled: bool = True)` — no-op if `opentelemetry` missing.

**`process()`**: Creates OTel span `"bus.publish {topic}"` with attributes:

| Attribute | Source |
| --- | --- |
| `bus.topic` | `envelope.topic` |
| `bus.envelope_id` | `envelope.envelope_id` |
| `bus.sequence` | `envelope.sequence` |
| `bus.priority` | `envelope.priority` |
| `bus.parent_id` | `envelope.parent_id` |
| `bus.cognitive_trace_id` | If non-empty |
| `bus.session_id` | If non-empty |

Ends span immediately. **Never drops**.

---

## 6. Timing Chain — Ordered Delivery

### 6.1 `TimingConfig`

| Method | Signature | Description |
| --- | --- | --- |
| `__init__` | `(rules: dict[str, DeliveryMode]?, default: DeliveryMode)` | Validates rules, builds sorted prefix cache |
| `resolve` | `(topic) → DeliveryMode` | Longest-prefix match: exact → walk segments → default. O(k) |
| `reload` | `(rules) → None` | Atomic rule replacement under lock |
| `set_default` | `(mode) → None` | Changes default mode |

**Validation**: Raises `ValueError` on empty prefix, `TypeError` if value is not `DeliveryMode`.

### 6.2 Default Timing Rules (18 prefixes)

| Prefix | Mode | Prefix | Mode |
| --- | --- | --- | --- |
| `k1.capability` | STRICT | `k1.affect` | RELAXED |
| `k1.orchestration` | STRICT | `k1.constraint` | RELAXED |
| `k1.planner` | STRICT | `k1.proactive` | RELAXED |
| `k1.hil` | STRICT | `k1.workflow` | RELAXED |
| `k1.hitl` | STRICT | `k1.k0.sse` | BEST_EFFORT |
| `k1.response` | STRICT | `k1.fabric.learning` | BEST_EFFORT |
| `k1.session` | STRICT | | |
| `k1.agent` | STRICT | | |
| `k1.internal` | STRICT | | |
| `k1.tool` | STRICT | | |
| `k1.arbiter` | STRICT | | |
| `k1.backpool` | STRICT | | |

### 6.3 `TimingChain`

**Constructor**: `TimingChain(config: TimingConfig? = None, timeout_ms: int = 5000, causal_buffer_limit: int = 50_000, gap_buffer_limit: int = 10_000)`

**`process(envelope, dispatch_fn)`** routing:

| DeliveryMode | Behaviour |
| --- | --- |
| `BEST_EFFORT` | `dispatch(envelope)` immediately, increment `dropped_best_effort` if dispatch fails |
| `RELAXED` | Deliver immediately, log reorder, update gap state |
| `STRICT` | Causal check → gap check → deliver or buffer → cascade release |

**`sweep(dispatch_fn) → int`**: Releases timed-out envelopes from both causal and gap buffers.

**`TimingStats`** (9 fields):

| Field | Description |
| --- | --- |
| `envelopes_processed` | Total processed |
| `delivered_immediate` | Delivered without buffering |
| `buffered_causal` | Buffered waiting for parent |
| `buffered_gap` | Buffered on sequence gap |
| `released_causal` | Released from causal buffer |
| `released_gap` | Released from gap buffer |
| `released_timeout` | Released on timeout |
| `reorders_detected` | Out-of-order detected (RELAXED) |
| `dropped_best_effort` | Dropped under BEST_EFFORT |

**Internal components:**

- `_CausalTracker` — tracks `parent_id` dependencies; buffers children until parent delivered; max buffer limit → force-release oldest 10%
- `_GapBuffer` — per-topic sequence gap tracking; buffers out-of-sequence; releases successors; per-topic lock with double-checked locking

---

## 7. BusFactory — Static Creation Methods

See [k1/bus/factory.py](k1/bus/factory.py).

| Method | Signature | Returns | Notes |
| --- | --- | --- | --- |
| `create_local` | `(*, capture, timing_chain, middleware, backend="auto", async_dispatch=False, subscription_mailbox_capacity=1024, retry_resolver=None, dlq_callback=None, outbox=None, durable_topics=None)` | `LocalBus \| RustBusAdapter` | **P6**: forwards new kwargs to `LocalBus`; forces Python backend if `timing_chain`, `async_dispatch`, or `outbox` is set |
| `create_local_ordered` | `(*, config, timeout_ms=5000, capture, middleware, backend="python")` | `LocalBus` | `backend="rust"` raises `ValueError` |
| `create_for_testing` | `(*, ordered, middleware, backend="auto")` | `LocalBus \| RustBusAdapter` | `ordered=True` forces Python + capture + TimingChain |
| `create_mailbox_router` | `(*, backend="auto")` | `LocalMailboxRouter \| RustMailboxRouterAdapter` | — |

**`create_local` Phase 6 kwargs** (forwarded verbatim to `LocalBus.__init__`):

| Kwarg | Default | Forces Python backend? |
| --- | --- | --- |
| `async_dispatch` | `False` | **Yes** when `True` |
| `subscription_mailbox_capacity` | `1024` | No (only meaningful with `async_dispatch=True`) |
| `retry_resolver` | `None` | No (only meaningful with `async_dispatch=True`) |
| `dlq_callback` | `None` | No (only meaningful with `async_dispatch=True`) |
| `outbox` | `None` | **Yes** when not `None` |
| `durable_topics` | `None` | No (only meaningful with `outbox`) |

**Backend forcing rules (post-P6):** If any of `timing_chain`, `async_dispatch`, or `outbox` is set, the factory forces `backend="python"` regardless of the requested backend (these features are not implemented in the Rust core). Explicit `backend="rust"` combined with these features is silently downgraded.

**Backend resolution** (`_resolve_backend`):

1. `K1_BUS_BACKEND` env var overrides programmatic parameter (highest priority)
2. `"auto"` → `"rust"` if `k1_bus_core` available, else `"python"`
3. Invalid env var logged and ignored
4. `"rust"` when unavailable → `ImportError`

**Factory is stateless** — all methods are `@staticmethod`.

---

## 8. BusConfig — YAML Configuration

**`BusConfig`** (frozen dataclass):

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `default_mode` | `DeliveryMode` | `RELAXED` | Default delivery mode |
| `timing_rules` | `dict[str, DeliveryMode]` | `{}` | Per-prefix rules |
| `source` | `str` | `"defaults"` | Config source identifier |

**`load_bus_config(path?)`**: Loads from YAML at `k1/config/bus.yaml`. **NEVER raises** — all errors fall back to defaults with logged warnings. Uses `yaml.safe_load`.

**`k1/config/bus.yaml` (post-Phase 6 snapshot)** — see [k1/config/bus.yaml](k1/config/bus.yaml):

| Mode | Prefixes |
| --- | --- |
| Default | `RELAXED` |
| `STRICT` | `k1.capability`, `k1.orchestration`, `k1.planner`, `k1.hil`, `k1.hitl`, `k1.response`, `k1.session`, `k1.agent`, `k1.internal`, `k1.tool`, `k1.arbiter`, `k1.backpool` |
| `RELAXED` | `k1.affect`, `k1.constraint`, `k1.proactive`, `k1.workflow` |
| `BEST_EFFORT` | `k1.k0.sse`, `k1.fabric.learning` |

> **P6.10 (open):** `k1.model_hub` is missing from the YAML and falls through to the default (`RELAXED`). The 13 `k1.model_hub.*` topics in [§10.11](#1011-model-hub-prefix-k1model_hub-13-topics) currently have no explicit timing rule. Tracked as P6.10 — unimplemented.

---

## 8a. BusOutbox — Durable Persistence (Phase 6 — NEW)

SQLite-backed durable store for at-least-once delivery and replay. Used by `LocalBus` when `outbox=` is configured. See [k1/bus/outbox/sqlite_outbox.py](k1/bus/outbox/sqlite_outbox.py).

**Constructor**: `BusOutbox(path: str | Path)` — opens (or creates) a SQLite DB in WAL mode at `path`.

**SQL pragmas applied at open**:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

**Schema**:

```sql
CREATE TABLE envelopes (
    envelope_id  INTEGER PRIMARY KEY,
    topic        TEXT,
    payload      BLOB,
    priority     INTEGER,
    created_ns   INTEGER,
    request_id   TEXT,
    session_id   TEXT,
    deleted      INTEGER
);
CREATE INDEX idx_envelopes_topic ON envelopes(topic, envelope_id);

CREATE TABLE acks (
    consumer_id              TEXT,
    topic                    TEXT,
    last_acked_envelope_id   INTEGER,
    PRIMARY KEY (consumer_id, topic)
);
```

**Methods**:

| Method | Signature | Description |
| --- | --- | --- |
| `append` | `(envelope: Envelope) → None` | `INSERT OR IGNORE` on `envelope_id` (idempotent on replay). |
| `ack` | `(consumer_id: str, topic: str, envelope_id: int) → None` | UPSERT into `acks` taking `MAX(last_acked_envelope_id, envelope_id)`. Monotonic — replays cannot rewind acks. |
| `unacked` | `(consumer_id: str, topic: str) → Iterator[OutboxRecord]` | Yields `envelopes` rows where `envelope_id > last_acked_envelope_id` for this consumer/topic. |
| `prune_acked` | `(retain_below: int = 0) → int` | Deletes envelopes with `envelope_id ≤ min(last_acked across consumers per topic)`. Returns rows deleted. |
| `last_envelope_id` | `() → int` | Current MAX `envelope_id` (0 if empty). |
| `count` | `(topic: str \| None = None) → int` | Row count, optionally filtered by topic. |
| `close` | `() → None` | Closes the SQLite connection. |

**`OutboxRecord`** (frozen dataclass):

| Field | Type |
| --- | --- |
| `envelope_id` | `int` |
| `topic` | `str` |
| `payload` | `bytes` |
| `priority` | `int` |
| `created_ns` | `int` |
| `request_id` | `str` |
| `session_id` | `str` |

Method **`to_envelope() → Envelope`** rebuilds an `Envelope` from the record (used by `LocalBus.replay_durable_topics`).

**Invariants**:

- `append` is idempotent: re-inserting the same `envelope_id` is a no-op.
- `ack` is monotonic: a stale ack with an older `envelope_id` is silently ignored.
- `prune_acked` only deletes envelopes that have been acked by **every** consumer subscribed to that topic.
- All operations are thread-safe via SQLite's own locking + the `busy_timeout=5000` retry window.

---

## 9. Adapters — Component-Facing Wrappers

### 9.1 `FabricBusAdapter`

Bridges Fabric's `IEventPort(Dict)` + `IDeltaBusPort` to `LocalBus`.

| Method | Signature | Description |
| --- | --- | --- |
| `emit` | `(topic, payload: Dict) → None` | Serializes JSON, extracts `cognitive_trace_id`, publishes `Priority.INTERACTIVE` |
| `subscribe` | `(topic, handler: Callable[[str, Dict], None]) → FabricSubscriptionHandle` | Wraps handler to deserialize JSON → Dict |
| `unsubscribe` | `(handle) → bool` | Delegates to bus |
| `emit_delta` | `(agent_id, delta_type, section, data) → None` | Publishes to `k1.agent.{agent_id}.delta.v1`, `Priority.REALTIME` |

### 9.2 `SessionBusAdapter`

Bridges SessionState's `IEventPort` ABC to `LocalBus`. **P6.9**: only event types prefixed `sessionstate.` are flattened by stripping the leading `sessionstate.` and re-prefixing `k1.`; other event types receive the legacy `k1.session.` prefix.

| Method | Signature | Description |
| --- | --- | --- |
| `emit` | `(event_type, payload: Any) → None` | Topic via `_map_topic`, serializes, `Priority.INTERACTIVE` |
| `subscribe` | `(event_type, handler: Callable[[Any], None]) → str` | Maps topic via `_map_topic`, wraps handler, returns `subscription_id` |
| `unsubscribe` | `(subscription_id) → bool` | Looks up handle from internal dict |
| `is_connected` | (property) → `bool` | `not self._bus.closed` |

**`_FLATTEN_PREFIXES = ("sessionstate.",)`** (P6.9). **`_map_topic`** behavior:

| Input event_type | Mapped topic |
| --- | --- |
| `sessionstate.mutation.requested` | `k1.sessionstate.mutation.requested` (no double-nesting) |
| `turn.started` (no flatten prefix) | `k1.session.turn.started` |

This fixes the previous bug where `sessionstate.X` events became `k1.session.sessionstate.X`. See [k1/bus/adapters/session_bus_adapter.py](k1/bus/adapters/session_bus_adapter.py).

---

## 10. Complete Topic Registry (~120 unique topics)

### 10.1 Session / Concierge (prefix: `k1.session` — STRICT)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.session.user.input.v1` | `TOPIC_USER_INPUT` | Transport | Front Actor (FSM) |
| `k1.session.artifact.created.v1` | `TOPIC_ARTIFACT_CREATED` | Back Actor | DeltaAggregator, FSM |
| `k1.session.turn.started.v1` | `TOPIC_TURN_STARTED` | FSM Controller | Observability |
| `k1.session.turn.completed.v1` | `TOPIC_TURN_COMPLETED` | FSM Controller | MemoryWriter, Learning, Obs |
| `k1.session.state.updated.v1` | `TOPIC_STATE_UPDATED` | DeltaAggregator | Observability |
| `k1.session.task.state.v1` | `TASK_STATE_CHANGED` | Back Actor | DeltaAggregator |

### 10.2 Response (prefix: `k1.response` — STRICT)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.response.stream.v1` | `TOPIC_RESPONSE_STREAM` | Front Actor | Transport/SSE |
| `k1.response.final.v1` | `TOPIC_FINAL_RESPONSE` | Front Actor | Transport/SSE |
| `k1.response.clarification.v1` | `TOPIC_CLARIFICATION_OUT` | Front Actor | Transport |

### 10.3 Orchestration (prefix: `k1.orchestration` — STRICT, 31 topics)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.orchestration.task.dispatch.v1` | `TOPIC_TASK_DISPATCH` | FSM / dispatch_task tool | Back Actor, Orchestrator |
| `k1.orchestration.task.complete.v1` | `TOPIC_TASK_COMPLETE` | Back Actor, Orchestrator | FSM Controller |
| `k1.orchestration.task.failed.v1` | `TOPIC_TASK_FAILED` | Back Actor, Orchestrator | FSM Controller |
| `k1.orchestration.task.cancel.v1` | `TOPIC_TASK_CANCEL` | FSM Controller | Back Actor, Orchestrator |
| `k1.orchestration.task.suspended.v1` | `TOPIC_TASK_SUSPENDED` | Back Actor | FSM Controller |
| `k1.orchestration.task.resume.v1` | `TOPIC_TASK_RESUME` | FSM Controller | Back Actor |
| `k1.orchestration.task.accepted.v1` | `ORCH_TASK_ACCEPTED` | Orchestrator | Concierge |
| `k1.orchestration.task.modify.v1` | `TOPIC_TASK_MODIFY` | FSM Controller | Back Actor |
| `k1.orchestration.findings.ready.v1` | `TOPIC_FINDINGS_READY` | Orchestrator | Concierge Front |
| `k1.orchestration.clarification.request.v1` | `TOPIC_CLARIFICATION_REQUEST` | Orchestrator | Concierge Front |
| `k1.orchestration.clarification.response.v1` | `TOPIC_CLARIFICATION_RESPONSE` | Concierge Front | Orchestrator |
| `k1.orchestration.delta.v1` | `ORCH_DELTA_V1` | Orchestrator | Concierge, Obs |
| `k1.orchestration.dag.completed.v1` | `ORCH_DAG_COMPLETED` | Orchestrator | Concierge, MW, Learning |
| `k1.orchestration.plan.requested.v1` | `ORCH_PLAN_REQUESTED` | Orchestrator | Planner |
| `k1.orchestration.dag.started.v1` | `ORCH_DAG_STARTED` | Orchestrator | Obs |
| `k1.orchestration.dag.micro_replan.v1` | `ORCH_DAG_MICRO_REPLAN` | Orchestrator | Obs |
| `k1.orchestration.step.started.v1` | `ORCH_STEP_STARTED` | Orchestrator | Obs |
| `k1.orchestration.step.completed.v1` | `ORCH_STEP_COMPLETED` | Orchestrator | Obs |
| `k1.orchestration.step.failed.v1` | `ORCH_STEP_FAILED` | Orchestrator | Obs |
| `k1.orchestration.step.cancelled.v1` | `ORCH_STEP_CANCELLED` | Orchestrator | Obs |
| `k1.orchestration.step.skipped.v1` | `ORCH_STEP_SKIPPED` | Orchestrator | Obs |
| `k1.orchestration.step.retrying.v1` | `ORCH_STEP_RETRYING` | Orchestrator | Obs |
| `k1.orchestration.step.schema_retry.v1` | `ORCH_STEP_SCHEMA_RETRY` | Orchestrator | Obs |
| `k1.orchestration.step.execute.v1` | `TOPIC_STEP_EXECUTE` | Orchestrator | Fabric |
| `k1.orchestration.saga.compensating.v1` | `ORCH_SAGA_COMPENSATING` | Orchestrator | Obs |
| `k1.orchestration.workflow.triggered.v1` | `ORCH_WORKFLOW_TRIGGERED` | Orchestrator | Obs |
| `k1.orchestration.workflow.completed.v1` | `ORCH_WORKFLOW_COMPLETED` | Orchestrator | Obs |
| `k1.orchestration.workflow.saved.v1` | `ORCH_WORKFLOW_SAVED` | Orchestrator | Obs |
| `k1.orchestration.workflow.trigger_due.v1` | `WORKFLOW_TRIGGER_DUE` | Workflow Scheduler | Orchestrator |
| `k1.orchestration.error.routed.v1` | `ORCH_ERROR_ROUTED` | Orchestrator | Obs |
| `k1.orchestration.mcp.tool_registered.v1` | `ORCH_MCP_TOOL_REGISTERED` | MCP Connector | Obs |

### 10.4 Tool (prefix: `k1.tool` — STRICT)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.tool.started.v1` | `TOPIC_TOOL_STARTED` | Tool Dispatcher | FSM, Obs |
| `k1.tool.completed.v1` | `TOPIC_TOOL_COMPLETED` | Tool Dispatcher | FSM, Obs |

### 10.5 HIL / HITL (prefix: `k1.hil` / `k1.hitl` — STRICT, 12 topics)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.hil.request.v1` | `TOPIC_HIL_REQUEST` | Front Actor | Back Actor |
| `k1.hil.response.v1` | `TOPIC_HIL_RESPONSE` | Front Actor | Back Actor |
| `k1.hitl.requested.v1` | `TOPIC_HITL_REQUESTED` | FSM/Coordinator | Obs |
| `k1.hitl.resolved.v1` | `TOPIC_HITL_RESOLVED` | FSM/Coordinator | Obs |
| `k1.hitl.timed_out.v1` | `TOPIC_HITL_TIMED_OUT` | FSM/Coordinator | Obs |
| `k1.hitl.blocked_red.v1` | `TOPIC_HITL_BLOCKED_RED` | FSM/Coordinator | Obs |
| `k1.hil.clarification.v1` | `TOPIC_HIL_CLARIFICATION` | Planner HIL | Concierge |
| `k1.hil.approval_request.v1` | `TOPIC_HIL_APPROVAL_REQ` | Planner HIL | Concierge |
| `k1.hil.clarification_response.v1` | `TOPIC_HIL_CLARIFICATION_RESP` | Concierge | Planner |
| `k1.hil.approval_response.v1` | `TOPIC_HIL_APPROVAL_RESP` | Concierge | Planner |
| `k1.hil.override_response.v1` | `HIL_OVERRIDE_RESPONSE` | Concierge | Orchestrator |
| `k1.hil.fallback_response.v1` | `HIL_FALLBACK_RESPONSE` | Concierge | Orchestrator |

### 10.6 Planner (prefix: `k1.planner` — STRICT, 8 topics)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.planner.plan.ready.v1` | `TOPIC_PLAN_READY` | Planner CommitService | Orchestrator |
| `k1.planner.plan.failed.v1` | `PLAN_FAILED` | Planner Pipeline | Orchestrator |
| `k1.planner.plan.cancelled.v1` | `PLAN_CANCELLED` | Planner Pipeline | Orchestrator |
| `k1.planner.micro_replan.ready.v1` | `MICRO_REPLAN_READY` | Planner Pipeline | Orchestrator |
| `k1.planner.delta.v1` | `TOPIC_DELTA` | Planner | Obs |
| `k1.planner.plan.request.v1` | `TOPIC_PLAN_REQUEST` | Orchestrator | Planner |
| `k1.planner.plan.cancel.v1` | `TOPIC_PLAN_CANCEL` | Orchestrator | Planner |
| `k1.planner.discovery.request.v1` | `TOPIC_DISCOVERY_REQUEST` | Planner | Fabric |

### 10.7 Fabric — Capability (prefix: `k1.capability` — STRICT)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.capability.invoked.v1` | `TOPIC_CAPABILITY_INVOKED` | Fabric EventEmitter | Obs |
| `k1.capability.completed.v1` | `CAPABILITY_COMPLETED` | Fabric EventEmitter | Orchestrator |
| `k1.capability.failed.v1` | `CAPABILITY_FAILED` | Fabric EventEmitter | Orchestrator |

### 10.8 Fabric — Infrastructure (prefix: `k1.fabric.*`, 21 topics)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.fabric.learning.signal.v1` | `TOPIC_LEARNING_SIGNAL` | Fabric | Learning Loop |
| `k1.fabric.capability.registered.v1` | `EVENT_CAPABILITY_REGISTERED` | Registry | GapDetector, Obs |
| `k1.fabric.capability.unregistered.v1` | `EVENT_CAPABILITY_UNREGISTERED` | Registry | GapDetector, Obs |
| `k1.fabric.capability.version.conflict.v1` | `TOPIC_VERSION_CONFLICT` | Fabric | Obs |
| `k1.fabric.contract.validation.failed.v1` | `TOPIC_CONTRACT_VALIDATION_FAILED` | Fabric | Obs |
| `k1.fabric.output.validation.failed.v1` | `TOPIC_OUTPUT_VALIDATION_FAILED` | Fabric | Obs |
| `k1.fabric.provider.health.changed.v1` | `TOPIC_PROVIDER_HEALTH_CHANGED` | Fabric | Obs |
| `k1.fabric.capability.contract_updated.v1` | `CONTRACT_UPDATED` | Fabric | Orch GapDetector |
| `k1.fabric.pressure.warning.v1` | `PRESSURE_WARNING_TOPIC` | FabricDispatcher | Obs |
| `k1.fabric.pressure.shedding.v1` | `PRESSURE_SHEDDING_TOPIC` | FabricDispatcher | Obs |
| `k1.fabric.agent.created.v1` | `TOPIC_AGENT_CREATED` | Fabric | Obs |
| `k1.fabric.agent.expired.v1` | `TOPIC_AGENT_EXPIRED` | Fabric | Obs |
| `k1.fabric.meta.operation.blocked.v1` | `TOPIC_META_OP_BLOCKED` | Fabric | Obs |
| `k1.fabric.provider.health.check.v1` | `TOPIC_HEALTH_CHECK_REQUEST` | External | Fabric HealthChecker |
| `k1.fabric.provider.registered.v1` | `EVENT_PROVIDER_REGISTERED` | ProviderRegistry | Obs |
| `k1.fabric.provider.unregistered.v1` | `EVENT_PROVIDER_UNREGISTERED` | ProviderRegistry | Obs |
| `k1.fabric.registry.reloaded.v1` | `EVENT_REGISTRY_RELOADED` | Registry | Obs |
| `k1.fabric.contract.hot_reloaded.v1` | `EVENT_CONTRACT_HOT_RELOADED` | ModuleLoader | Obs |
| `k1.fabric.contract.removed.v1` | `EVENT_CONTRACT_REMOVED` | ModuleLoader | Obs |
| `k1.fabric.health.check_cycle.v1` | `EVENT_HEALTH_CHECK_CYCLE` | HealthChecker | Obs |
| `k1.fabric.agent.tool_call.v1` | `AGENT_TOOL_CALL` | Fabric Agent | Orch Monitor |
| `k1.fabric.agent.llm_call.v1` | `AGENT_LLM_CALL` | Fabric Agent | Orch Monitor |

### 10.9 Agent Delta (dynamic pattern)

| Pattern | Publisher | Subscriber |
| --- | --- | --- |
| `k1.agent.{agent_id}.delta.v1` | `FabricBusAdapter.emit_delta()` | Wildcard `k1.agent.*.delta.v1` |

### 10.10 MCP

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.mcp.tool.discovered.v1` | `TOPIC_MCP_TOOL_DISCOVERED` | MCP Connector | ProactiveGapDetector |

### 10.11 Model Hub (prefix: `k1.model_hub`, 13 topics)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.model_hub.request.received.v1` | `TOPIC_REQUEST_RECEIVED` | RequestRouter | Obs |
| `k1.model_hub.request.routed.v1` | `TOPIC_REQUEST_ROUTED` | RequestRouter | Obs |
| `k1.model_hub.response.complete.v1` | `TOPIC_RESPONSE_COMPLETE` | RequestRouter | Obs |
| `k1.model_hub.cache.hit.v1` | `TOPIC_CACHE_HIT` | RequestRouter | Obs |
| `k1.model_hub.provider.failure.v1` | `TOPIC_PROVIDER_FAILURE` | RequestRouter | Obs |
| `k1.model_hub.fallback.triggered.v1` | `TOPIC_FALLBACK_TRIGGERED` | RequestRouter | Obs |
| `k1.model_hub.circuit.state.v1` | `TOPIC_CIRCUIT_STATE` | RequestRouter | Obs |
| `k1.model_hub.budget.alert.v1` | `TOPIC_BUDGET_ALERT` | RequestRouter | Obs |
| `k1.model_hub.provider.health.v1` | `TOPIC_PROVIDER_HEALTH` | RequestRouter | Obs |
| `k1.model_hub.provider.registered.v1` | `TOPIC_PROVIDER_REGISTERED` | ModelHub | Obs |
| `k1.model_hub.capability.available.v1` | `TOPIC_CAPABILITY_AVAILABLE` | ModelHub | Obs |
| `k1.model_hub.execute.v1` | `TOPIC_HUB_EXECUTE` | Concierge/Orch | ModelHub Deserializer |
| `k1.model_hub.execute.response.v1` | `TOPIC_HUB_RESPONSE` | ModelHub Deserializer | Concierge/Orch |

### 10.12 Memory Writer (prefix: `k1.mw`, 6 topics)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.session.turn.complete.v1` | `TOPIC_TURN_COMPLETE` | Concierge FSM | MW `TurnDispatcher` (matches `TurnDispatcher.TOPIC`) |
| `k1.mw.filter.decision.v1` | `TOPIC_FILTER_DECISION` | MW Pipeline | Obs |
| `k1.mw.extraction.complete.v1` | `TOPIC_EXTRACTION_COMPLETE` | MW Pipeline | Obs |
| `k1.mw.batch.submitted.v1` | `TOPIC_BATCH_SUBMITTED` | MW Pipeline | Obs |
| `k1.mw.pipeline.error.v1` | `TOPIC_PIPELINE_ERROR` | MW Pipeline | Obs |
| `k1.mw.circuit.open.v1` | `TOPIC_CIRCUIT_OPEN` | MW Pipeline | Obs |

> **P6.8 — distinct topics:** `TOPIC_TURN_COMPLETE = "k1.session.turn.complete.v1"` (memory writer; see [k1/memory_writer/events.py](k1/memory_writer/events.py)) is **distinct from** the concierge `TOPIC_TURN_COMPLETED = "k1.session.turn.completed.v1"` (§10.1). The renamed `TurnDispatcher.TOPIC` matches the new `complete` form; do not collapse them.

### 10.13 Internal / Bus Mechanics (prefix: `k1.internal` — STRICT)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.internal.weave.batch.v1` | `TOPIC_WEAVE_BATCH` | WeaveBatcher | Front Actor |
| `k1.internal.dead_letter.v1` | `TOPIC_DEAD_LETTER` | Bus middleware | Obs |

### 10.14 BackPool (prefix: `k1.backpool` — STRICT)

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.backpool.worker.acquired.v1` | `TOPIC_BACKPOOL_WORKER_ACQUIRED` | BackPool | Obs |
| `k1.backpool.worker.released.v1` | `TOPIC_BACKPOOL_WORKER_RELEASED` | BackPool | Obs |
| `k1.backpool.task.leased.v1` | `TOPIC_TASK_LEASED` | BackPool TaskLease | Obs |

### 10.15 Arbiter / Phase1 / Routing

| Topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- |
| `k1.arbiter.intent.v1` | `TOPIC_INTENT_ARBITRATED` | FSM Arbiter | Obs |
| `k1.phase1.classified.v1` | `TOPIC_PHASE1_CLASSIFIED` | FSM Phase1 | Obs |
| `k1.task.routed.v1` | `TOPIC_TASK_ROUTED` | FSM Task Router | Obs |

### 10.16 Relaxed / Metrics / Affect

| Topic | Constant | Delivery | Publisher |
| --- | --- | --- | --- |
| `k1.affect.update.v1` | `TOPIC_AFFECT_UPDATE` | RELAXED | Concierge session |
| `k1.proactive.fill.v1` | `TOPIC_PROACTIVE_FILL` | RELAXED | Concierge session |
| `k1.ui.typing.v1` | `TOPIC_UI_TYPING` | RELAXED | Transport |
| `k1.conversation.weave.decided.v1` | `TOPIC_WEAVE_DECIDED` | RELAXED | WeavePolicy |
| `k1.metrics.weave.v1` | `TOPIC_WEAVE_METRICS` | RELAXED | WeavePolicy |
| `k1.metrics.emitted.v1` | `TOPIC_METRIC_EMITTED` | RELAXED | MetricsCollector |
| `k1.metrics.alert.v1` | `TOPIC_METRIC_ALERT` | RELAXED | Alert Engine |
| `k1.metrics.session_summary.v1` | `TOPIC_METRIC_SESSION_SUMMARY` | RELAXED | MetricsCollector |

### 10.17 SessionState Internal Events (mapped via SessionBusAdapter → `k1.sessionstate.*`)

**P6.9**: events with the `sessionstate.` prefix are flattened to `k1.sessionstate.X` (no double-nesting under `k1.session.sessionstate.X`).

| Event | Mapped topic | Constant | Publisher | Subscriber |
| --- | --- | --- | --- | --- |
| `sessionstate.mutation.requested` | `k1.sessionstate.mutation.requested` | `MUTATION_REQUESTED` | Writer | Policy Engine |
| `sessionstate.mutation.approved` | `k1.sessionstate.mutation.approved` | `MUTATION_APPROVED` | Policy Engine | DeltaAggregator |
| `sessionstate.mutation.rejected` | `k1.sessionstate.mutation.rejected` | `MUTATION_REJECTED` | Policy Engine | Obs |
| `sessionstate.eviction.triggered` | `k1.sessionstate.eviction.triggered` | `EVICTION_TRIGGERED` | EvictionEngine | Obs |
| `sessionstate.eviction.completed` | `k1.sessionstate.eviction.completed` | `EVICTION_COMPLETED` | EvictionEngine | Obs |
| `sessionstate.emergency.activated` | `k1.sessionstate.emergency.activated` | `EMERGENCY_ACTIVATED` | Emergency handler | Obs |
| `sessionstate.emergency.resolved` | `k1.sessionstate.emergency.resolved` | `EMERGENCY_RESOLVED` | Emergency handler | Obs |

### 10.18 Bridge / Cross-Boundary (K0↔K1)

| Topic | Publisher | Subscriber | Direction |
| --- | --- | --- | --- |
| `memory.delta` | K1 MemoryWriter | K0 Command Port (via Bridge) | K1→K0 |
| `k1.memory.delta.v1` | MemoryWriter (internal) | Bridge adapter | K1→Bridge |
| `k1.k0.sse.*` | K0 SSE Bridge | Concierge | K0→K1 |

---

## 11. Summary Statistics

| Category | Count |
| --- | --- |
| **Port protocols** | 6 (IBus, IMailbox, IMailboxRouter + 3 async) |
| **Implementations** | 5 (LocalBus, LocalMailbox, LocalMailboxRouter, RustBusAdapter, RustMailboxRouterAdapter) |
| **Adapters** | 2 (FabricBusAdapter, SessionBusAdapter) |
| **Bridges** | 3 (AsyncBusBridge, AsyncMailboxBridge, AsyncMailboxRouterBridge) |
| **Middleware** | 3 (Metrics, TopicValidation, Tracing) |
| **Envelope enums** | 3 (Priority, DeliveryMode, PayloadFormat) |
| **Factory methods** | 4 |
| **Total public symbols** | 42 |
| **Total unique topics** | ~120 |
| **Timing prefix rules** | 18 (12 STRICT, 4 RELAXED, 2 BEST_EFFORT) |

---

## 12. Known Issues & Findings

| # | Severity | Location | Finding |
| --- | --- | --- | --- |
| 1 | **Medium** | `rust_mailbox_adapter.py` | `RustMailboxAdapter.receive(*, timeout_ms)` is keyword-only but `IMailbox` protocol declares it positional. Callers using `receive(100)` will get `TypeError` with Rust adapter. |
| 2 | **Open (P6.10)** | `k1/config/bus.yaml` | `k1.model_hub` prefix is missing from the YAML; the 13 `k1.model_hub.*` topics inherit the default `RELAXED` mode. Tracked as P6.10. |
| 3 | **Resolved (P6.3)** | `rust_bus_adapter.py` | `drain()` previously returned cumulative captured (no Rust-side clear). Now uses `_drain_offset` to return only newly captured envelopes. |
| 4 | **Resolved (P6.2)** | `rust_bus_adapter.py` | `publish()` previously skipped middleware. Now runs `self._middleware.process(envelope)` before crossing into Rust; `None` drops. |
| 5 | **Resolved (P6.1)** | `async_bridge.py` | `_wrap_async_handler`'s `Future` was never awaited — errors were fire-and-forget. Now uses `Future.add_done_callback` to log + count via `async_handler_errors`. |
| 6 | **Low** | `impl/__init__.py` | Does not re-export `LocalMailbox`, `LocalMailboxRouter`, Rust adapters. They're exported from `k1.bus.__init__` directly. Inconsistent layering. |
| 7 | **Info** | `config.py` | `load_bus_config()` never raises — robust for production but may mask config errors in development. |
