# K1 Bus — WIRING

This document traces every construction path that produces an `IBus` instance, every
adapter instantiation, and how buses are plumbed into the components that depend on them.

---

## 1. `BusFactory` — the single construction entry point

```python
# k1/bus/factory.py
BusFactory.create_local(
    backend: str = "auto",        # "auto" | "rust" | "python"
    capture: bool = False,        # record all envelopes for tests
    async_dispatch: bool = False, # per-subscription worker threads
    subscription_mailbox_capacity: int = 1024,
    timing_config: TimingConfig | None = None,
    middleware: MiddlewareChain | None = None,
    retry_resolver: object | None = None,
    dlq_callback: Callable | None = None,
    outbox: BusOutbox | None = None,
    durable_topics: set[str] | None = None,
) -> IBus
```

Backend selection (`backend="auto"`):

```
try:
    import k1_bus_core              # Rust extension (.pyd / .so)
    → RustBusAdapter(k1_bus_core.RustBus(...))
except ImportError:
    → LocalBus(...)                 # pure Python fallback (always available)
```

`K1_BUS_BACKEND` env var overrides `backend` argument.

`BusFactory.create_ordered()` — convenience wrapper with
`timing_config=default_timing_config()` pre-set. Used by kernel for production buses.

`BusFactory.create_testing()` — `capture=True`, Python backend always, no timing overhead.

---

## 2. `LocalBus` construction graph

```python
LocalBus.__init__(
    capture, timing_chain, middleware, async_dispatch,
    subscription_mailbox_capacity, retry_resolver, dlq_callback,
    outbox, durable_topics
)
│
├─ _trie: TopicTrie            # try k1_bus_core.TopicTrie, else Python TopicTrie
├─ _seq_gen: _SequenceGenerator# per-topic monotonic counters (dict[str, int])
├─ _id_gen: _EnvelopeIdGenerator# global envelope_id counter (starts 1)
├─ _rwlock: _ReadWriteLock     # threading.Condition + threading.Lock
├─ _subscriptions: dict[str, _Subscription | _AsyncSubscription]
├─ _stats: BusStats            # counters (no locks; read eventually consistent)
├─ _async_subs: list[_AsyncSubscription]  # only if async_dispatch=True
├─ _timing_chain: TimingChain | None      # set if timing_config provided
├─ _middleware: MiddlewareChain | None    # set if provided
├─ _outbox: BusOutbox | None             # set if provided
└─ _captured: list[Envelope] | None      # set if capture=True
```

`TimingChain` construction (when provided):

```python
TimingChain(config=timing_config)
│
├─ _causal_tracker: _CausalTracker    # global causal buffer (max 50,000 entries)
├─ _gap_buffers: dict[str, _GapBuffer]# per-topic (max 10,000 entries, 5,000 ms TTL)
└─ _timing_config: TimingConfig       # per-prefix DeliveryMode rules
```

---

## 3. Per-session bus construction (kernel wiring)

The kernel creates one `LocalBus` per session at `SessionInstance` construction:

```python
# k1/kernel/kernel.py (simplified)
session_bus = BusFactory.create_ordered()   # timing_config=default_timing_config()
session_router = LocalMailboxRouter()

# Mailboxes for Concierge
front_mailbox = session_router.register("ACTOR_FRONT", MailboxConfig(capacity=256))
back_mailbox  = session_router.register("ACTOR_BACK",  MailboxConfig(capacity=256))

# Additional per-component subscriptions wired during start()
```

Each call to `BusFactory.create_ordered()` produces a **new isolated bus instance**.
There is no global bus. Session A and session B have completely separate bus objects.

---

## 4. Adapter instantiation

### 4.1 `AsyncBusBridge` — wraps sync `IBus` for async callers

```python
AsyncBusBridge(
    bus: IBus,
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop(),
)
```

Used by components running in an asyncio event loop (e.g. Concierge FSM controller).
All mutating calls go through `asyncio.to_thread`. Async handlers are scheduled back
via `asyncio.run_coroutine_threadsafe(coro, loop)`.

### 4.2 `FabricBusAdapter` — IBus ↔ Fabric event port

```python
FabricBusAdapter(bus: IBus)
```

Provides the `IEventPort[Dict]` surface for Fabric and the `IDeltaBusPort` surface
for delta events. Translates between `Dict` payloads and `Envelope(payload=json_bytes)`.

Delta events use topic `k1.agent.{agent_id}.delta.v1` and wrap the delta in a
`DeltaPayload` before JSON serialization.

### 4.3 `SessionBusAdapter(IEventPort)` — IBus ↔ SessionState event port

```python
SessionBusAdapter(bus: IBus, session_id: str)
```

Extends `IEventPort` ABC. Topic translation:

- `sessionstate.X` → `k1.sessionstate.X` (P6.9 flattening; no double-nesting)
- All other types → `k1.session.{event_type}`

Exposes `emit_batch(events)` which publishes all events atomically within the bus's
read-lock window (single `publish()` loop with no inter-event gaps from other threads).

---

## 5. Middleware assembly

Middleware is assembled before bus construction, passed as `MiddlewareChain`:

```python
chain = MiddlewareChain([
    IdempotencyMiddleware(cache_size=4096, ttl_ms=60_000),
    TracingMiddleware(),            # requires opentelemetry; no-op if absent
    MetricsMiddleware(),            # requires prometheus_client; no-op if absent
    TopicValidationMiddleware(registry=topic_registry),  # optional
])
bus = BusFactory.create_ordered(middleware=chain)
```

Middleware order is significant: `IdempotencyMiddleware` must run first to avoid paying
the cost of tracing and metrics for duplicate events.

---

## 6. Durable outbox assembly

```python
outbox = BusOutbox(db_path="data/bus_outbox.db")   # SQLite WAL
bus = BusFactory.create_ordered(
    outbox=outbox,
    durable_topics={"k1.hil.requested.v1", "k1.hitl.suspended.v1"},
)
```

Only topics in `durable_topics` are written to SQLite before dispatch. All other
topics flow through without persistence overhead.

---

## 7. `RustBusAdapter` construction (when `k1_bus_core` present)

```python
RustBusAdapter(
    inner: k1_bus_core.RustBus,
    timing_config: RustTimingConfig | None = None,
    wfq_scheduler: PyWfqScheduler | None = None,
)
```

`RustBusAdapter` owns the Rust objects. On every `publish()` call:

```
Python Envelope → RustEnvelope (FlatBuffers zero-copy serialize)
  → k1_bus_core.RustBus.publish(rust_env)
  → trie match in Rust (lock-free DashMap)
  → ring buffer dispatch
  → per-subscriber worker threads (Rust, parking_lot Mutex)
  → deserialize result Envelope back to Python for handler calls
```

Handler callbacks are Python callables passed into the Rust side via PyO3.
Rust calls back into Python on its own worker threads.

---

## 8. `LocalMailboxRouter` construction

```python
LocalMailboxRouter()
│
├─ _actors: dict[str, LocalMailbox]   # protected by threading.RLock
└─ _lock: threading.RLock
```

`LocalMailboxRouter.register(actor_id, config)` creates and stores a new
`LocalMailbox(capacity=config.capacity or 256)`.

`LocalMailbox` internal structure:

```python
LocalMailbox(capacity: int)
│
├─ _queue: collections.deque[Envelope]  # bounded by capacity
├─ _cond: threading.Condition
├─ _closed: bool
├─ _delivered_count: int
└─ _received_count: int
```

---

## 9. Subscription wiring in `LocalBus.subscribe()`

```python
def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle:
    with self._rwlock.write():
        sub_id = str(uuid4())
        if self._async_dispatch:
            sub = _AsyncSubscription(
                sub_id=sub_id,
                handler=handler,
                mailbox_capacity=self._subscription_mailbox_capacity,
                retry_policy=self._retry_resolver(pattern) if self._retry_resolver else None,
                dlq_callback=self._dlq_callback,
            )
            sub.start()           # launches daemon thread "bus-sub-{sub_id[:12]}"
            self._async_subs.append(sub)
        else:
            sub = _Subscription(sub_id=sub_id, handler=handler)
        self._trie.insert(pattern, sub)
        self._subscriptions[sub_id] = sub
        return SubscriptionHandle(subscription_id=sub_id, pattern=pattern)
```

---

## 10. Dependency graph

```
BusFactory
  └─ LocalBus (or RustBusAdapter)
        │
        ├─ TopicTrie (Rust if available, Python fallback)
        ├─ _SequenceGenerator (per-topic threading.Lock)
        ├─ _EnvelopeIdGenerator (global threading.Lock)
        ├─ _ReadWriteLock (subscribe/publish contention)
        ├─ TimingChain (optional)
        │     ├─ _CausalTracker (cross-topic gap ordering)
        │     └─ _GapBuffer[] (per-topic buffering)
        ├─ MiddlewareChain (optional)
        │     ├─ IdempotencyMiddleware (LRU bounded)
        │     ├─ TracingMiddleware (OTel optional)
        │     ├─ MetricsMiddleware (Prometheus optional)
        │     └─ TopicValidationMiddleware (optional)
        └─ BusOutbox (optional, SQLite WAL)

LocalMailboxRouter
  └─ LocalMailbox[] (one per registered actor)

AsyncBusBridge
  └─ wraps IBus (any impl)

FabricBusAdapter
  └─ wraps IBus

SessionBusAdapter
  └─ wraps IBus
```

---

## 11. Teardown sequence

```python
# Ordered teardown for a session bus
1. bus.flush(timeout_ms=5000)          # drain async dispatch mailboxes
2. session_router.unregister("ACTOR_FRONT")
3. session_router.unregister("ACTOR_BACK")
4. bus.close()                          # sets _closed=True; future publish() raises
5. outbox.close() if outbox             # close SQLite connection
```

All subscriptions registered by component `X` must be unsubscribed before step 4 to
avoid lingering daemon worker threads. In practice, each component calls
`bus.unsubscribe(handle)` in its own `stop()` method before the bus is closed.
