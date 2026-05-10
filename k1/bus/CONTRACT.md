# K1 Bus — CONTRACT

The bus is the **sole inter-component communication mechanism in K1**. Every event,
task dispatch, tool result, HITL signal, and affect update flows as an `Envelope`
through an `IBus` instance. The bus does NOT understand payloads — it is a typed
byte-array router.

---

## 1. What the bus promises callers

### 1.1 Core delivery guarantees

| Guarantee | Detail |
|---|---|
| **At-most-once delivery (default)** | An envelope is delivered once per matching subscriber. If the subscriber mailbox is full (async dispatch) or the handler raises, the envelope is not retried unless `retry_resolver` is configured. |
| **Per-topic monotonic sequence** | Every envelope published to topic `T` receives a strictly increasing `sequence` number. Across topics there is no ordering guarantee. |
| **Causal ordering (STRICT topics)** | For topics governed by `DeliveryMode.STRICT`, envelopes with `parent_id` chains are held in the gap buffer and delivered only after their causal parent has been dispatched. |
| **Handler isolation** | A handler exception on subscriber A does not prevent subscriber B from receiving the same envelope. |
| **Payload opacity** | The bus never deserializes `payload`. It is opaque `bytes` from the bus's perspective. |
| **No shared state** | Each `LocalBus` instance is fully isolated. There is no singleton or global registry. Per-session isolation is by object identity. |

### 1.2 What the bus does NOT promise

- No persistence across process restart (unless `BusOutbox` is wired in for specific topics).
- No guaranteed delivery to slow consumers — async dispatch mailboxes that fill up drop envelopes silently.
- No guaranteed ordering across topics.
- No TTL enforcement in Python `LocalBus` (TTL is a V2 envelope field; enforcement is Rust-only).
- No fan-out to disconnected subscribers (subscriptions are in-process only).

---

## 2. Public interface — `IBus`

```python
class IBus(Protocol):
    def publish(self, envelope: Envelope) -> None: ...
    def subscribe(self, pattern: str, handler: BusHandler) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
    def flush(self, timeout_ms: int = 5000) -> bool: ...
```

`BusHandler = Callable[[Envelope], None]`

### `publish(envelope)`

- Stamps `envelope_id` (global monotonic int), `sequence` (per-topic monotonic int), `created_ns` (monotonic clock ns). The original frozen envelope is NOT mutated — a new stamped instance is created.
- Runs `MiddlewareChain.process(stamped)` — if any middleware returns `None`, the envelope is dropped silently.
- Delivers to all handlers whose subscription pattern matches the envelope topic.
- **Never raises** for normal payloads. Handler exceptions are caught, logged, and attributed to `stats.handler_errors`. Publication continues to remaining subscribers.
- Raises `RuntimeError("Bus is closed")` if the bus has been closed via `close()`.

### `subscribe(pattern, handler)`

- Registers a handler for a topic pattern. Patterns use segment notation (`k1.agent.*.delta.v1`). Wildcards: `*` = exactly one segment, `>` = one or more trailing segments.
- Returns `SubscriptionHandle(subscription_id: str, pattern: str)`.
- Thread-safe: acquires write lock on the topic trie.

### `unsubscribe(handle)`

- Removes the subscription identified by `handle.subscription_id`.
- Returns `True` if found and removed, `False` if already gone.
- Thread-safe: acquires write lock.

### `flush(timeout_ms)`

- Sync dispatch (default): no-op, always returns `True`.
- Async dispatch (`async_dispatch=True`): blocks until all per-subscription worker mailboxes are drained or timeout elapses. Returns `True` on clean drain, `False` on timeout.

---

## 3. Public interface — `IMailbox` and `IMailboxRouter`

```python
class IMailbox(Protocol):
    def receive(self, timeout_ms: int = 0) -> Optional[Envelope]: ...
    def pending(self) -> int: ...

class IMailboxRouter(Protocol):
    def deliver(self, actor_id: str, envelope: Envelope) -> None: ...
    def register(self, actor_id: str, config: Optional[MailboxConfig] = None) -> IMailbox: ...
    def unregister(self, actor_id: str) -> bool: ...
    def registered_actors(self) -> list[str]: ...
```

`IMailboxRouter.deliver()` raises:

- `BackpressureError` — actor mailbox is full.
- `UnknownActorError` — `actor_id` not registered.

`MailboxConfig(capacity: int = 256, priority_wfq: bool = True)`.

---

## 4. `Envelope` contract

```python
@dataclass(frozen=True)
class Envelope:
    topic:              str   = ""
    priority:           int   = Priority.INTERACTIVE  # 0=URGENT, 1=REALTIME, 2=INTERACTIVE, 3=BACKGROUND
    envelope_id:        int   = 0     # assigned by bus.publish()
    sequence:           int   = 0     # per-topic monotonic, assigned by bus.publish()
    cognitive_trace_id: str   = ""    # cross-K0/K1 correlation
    session_id:         str   = ""
    request_id:         str   = ""
    parent_id:          int   = 0     # causal chain (0 = root)
    created_ns:         int   = 0     # assigned by bus.publish()
    payload:            bytes = b""   # opaque to bus
    ttl_ms:             int   = 0     # 0 = no expiry; enforced by Rust only
    payload_format:     int   = PayloadFormat.OPAQUE
```

Wire format: `K1_ENVELOPE_FORMAT=v2` (default) → FlatBuffers with `b'FB02'` prefix. `v1` → JSON header. `Envelope.from_bytes()` auto-detects.

Validation invariants (enforced in `__post_init__`):

- `priority` in `{0, 1, 2, 3}`
- `payload` must be `bytes`
- All int fields must be ≥ 0

---

## 5. Topic routing contract

| Pattern syntax | Matches |
|---|---|
| `"k1.capability.completed.v1"` | Exact topic string only |
| `"k1.agent.*.delta.v1"` | `*` = exactly one segment at that position |
| `"k1.agent.>"` | `>` = one or more trailing segments; must be the last segment |

Unroutable envelopes (no subscribers) are silently dropped. No error, no dead-letter
entry for unrouted events.

---

## 6. Middleware contract

```python
class Middleware(Protocol):
    def process(self, envelope: Envelope) -> Optional[Envelope]:
        # Return envelope (same or transformed) to continue.
        # Return None to DROP the envelope — no handlers are called.
```

Middlewares are chained in order. The first `None` return short-circuits the chain.

Built-in middlewares:

- `TracingMiddleware` — injects OpenTelemetry span context into `cognitive_trace_id`.
- `MetricsMiddleware` — increments Prometheus publish/handler counters and histograms.
- `TopicValidationMiddleware` — validates topic against `TopicRegistry` schema; drops unknown topics.
- `IdempotencyMiddleware` — drops duplicate `(topic, request_id)` pairs (LRU+TTL bounded cache).

---

## 7. Delivery ordering modes

Configured per-topic-prefix by `TimingConfig`. Three modes:

| Mode | Behaviour |
|---|---|
| `STRICT` | Causal ordering enforced. Envelopes with `parent_id` are buffered until their parent has been dispatched. Gap buffer holds at most 10,000 entries per topic; held for at most 5,000 ms before force-release. |
| `RELAXED` | Best-effort causal ordering. No gap buffering. Delivery in publish order within a single thread. |
| `BEST_EFFORT` | No ordering guarantees. Envelopes dispatched immediately without any sequencing overhead. |

Default STRICT topics: `k1.capability`, `k1.orchestration`, `k1.planner`, `k1.hil`,
`k1.hitl`, `k1.response`, `k1.session`, `k1.agent`, `k1.internal`, `k1.tool`,
`k1.arbiter`, `k1.backpool`, `k1.model_hub`, `k1.selfmodel.*`.

Default RELAXED topics: `k1.affect`, `k1.constraint`, `k1.proactive`, `k1.workflow`.

Default BEST_EFFORT topics: `k1.k0.sse`, `k1.fabric.learning`.

---

## 8. Durable outbox contract (`BusOutbox`)

Optional. Wired via `LocalBus(outbox=BusOutbox(...), durable_topics={...})`.

- Envelopes published to `durable_topics` are written to SQLite (WAL mode) before dispatch.
- `BusOutbox.replay_unacked(consumer_id, pattern) -> int` — re-publishes all unacknowledged envelopes matching pattern for a given consumer.
- `BusOutbox.ack(consumer_id, envelope_id)` — marks an envelope as delivered.
- Use case: cross-session event replay; crash recovery for durable command topics.

---

## 9. Async bridge contract (`IAsyncBus`)

```python
class IAsyncBus(Protocol):
    async def publish(self, envelope: Envelope) -> None: ...
    async def subscribe(self, pattern: str, handler: AsyncBusHandler) -> SubscriptionHandle: ...
    async def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
```

`AsyncBusBridge(bus: IBus)` is the adapter. All calls go through `asyncio.to_thread`.
Async handlers are scheduled back on the captured event loop via
`asyncio.run_coroutine_threadsafe`.

---

## 10. Caller invariants

1. **Never publish before subscribing** — there is no replay for events published before a subscription is registered.
2. **Handlers must be non-blocking (sync dispatch mode)** — sync handlers run on the publisher's thread while the read lock is held. Blocking handlers stall all concurrent publishers.
3. **Call `flush()` before `close()`** — ensures all in-flight async dispatch mailboxes are drained before the bus is torn down.
4. **Do not modify envelopes** — `Envelope` is frozen. Create new instances for any changes.
5. **`unsubscribe()` before object teardown** — leaked subscriptions in async dispatch mode keep daemon worker threads alive.
6. **`request_id` must be unique per logical operation** — `IdempotencyMiddleware` deduplicates on `(topic, request_id)`; reusing IDs will cause silent drops.
