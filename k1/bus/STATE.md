# K1 Bus — STATE

Unlike Concierge, the bus does not drive LLM behavior — its state is traditional
software state. However, understanding it precisely is important because every other
K1 component's correctness depends on the bus's internal state being consistent.

---

## 1. Mutable fields — `LocalBus`

| Field | Type | Mutated by | Protected by |
|---|---|---|---|
| `_closed` | `bool` | `close()` | `_rwlock` (write) |
| `_trie` | `TopicTrie` | `subscribe()`, `unsubscribe()` | `_rwlock` (write) |
| `_subscriptions` | `dict[str, _Subscription]` | `subscribe()`, `unsubscribe()` | `_rwlock` (write) |
| `_async_subs` | `list[_AsyncSubscription]` | `subscribe()`, `unsubscribe()`, `sweep()` | `_rwlock` (write) |
| `_seq_gen._seqs` | `dict[str, int]` | `publish()` — per-topic sequence increment | Per-topic `threading.Lock` (double-checked locking) |
| `_id_gen._counter` | `int` | `publish()` — global envelope ID increment | `threading.Lock` |
| `_stats` | `BusStats` | `publish()`, handler dispatch | No lock (int fields, eventually consistent) |
| `_captured` | `list[Envelope]` | `publish()` (capture mode only) | No lock (test mode only, single-threaded assumption) |
| `_outbox` | `BusOutbox` | `publish()` (durable topics only) | SQLite transaction |
| `_timing_chain._causal_tracker._buffer` | `dict[int, ...]` | `publish()` → causal ordering | `threading.Lock` |
| `_timing_chain._gap_buffers[topic]._buffer` | `deque` | `publish()` → gap ordering | Per-topic `threading.Lock` |

---

## 2. Bus lifecycle states

```
CREATED → RUNNING → CLOSED
```

| State | Condition | Behaviour |
|---|---|---|
| `CREATED` | After `__init__`, before first `publish()` | All operations valid |
| `RUNNING` | After first `publish()` or `subscribe()` | Normal operation |
| `CLOSED` | After `close()` | `publish()` raises `RuntimeError`. `subscribe()` raises. Async worker threads draining. |

`CLOSED` is irreversible. A closed bus cannot be reopened. Sessions that need a new bus
must call `BusFactory.create_*()` again.

---

## 3. Per-subscription state machine

### Sync subscription (`_Subscription`)

```
ACTIVE → TOMBSTONED (via unsubscribe)
```

Tombstoned entries remain in the trie as `None` sentinels. Compaction (reaping
tombstones) runs automatically in `_trie.remove()` when >50% of a node's slots are
tombstoned.

### Async subscription (`_AsyncSubscription`)

```
STARTING → ACTIVE → DRAINING → STOPPED
```

| State | Triggered by | Behaviour |
|---|---|---|
| `STARTING` | `start()` called | Worker thread launching |
| `ACTIVE` | Thread running | Accepts envelopes, calls handler |
| `DRAINING` | `shutdown()` called (via `unsubscribe()`) | No new envelopes; drains existing mailbox |
| `STOPPED` | Thread exits | Thread dead; object can be GC'd |

Async subscription fields:
- `_mailbox: LocalMailbox` — bounded deque (capacity configurable, default 1024)
- `_inflight: int` — count of currently executing handler invocations
- `_inflight_lock: threading.Lock`
- `_shutdown_event: threading.Event`
- `_thread: threading.Thread` (daemon=True, name=`"bus-sub-{sub_id[:12]}"`)
- `_retry_policy: RetryPolicy | None`
- `_attempt_counts: dict[int, int]` — per-envelope-id retry counter

---

## 4. Envelope stamping — the publish() state transitions

Every `publish()` call produces a new stamped envelope. The original is immutable.

```
envelope_in (unstamped)
    │
    ├─ envelope_id = _id_gen.next()          # global monotonic int, thread-safe
    ├─ sequence   = _seq_gen.next(topic)     # per-topic monotonic int, thread-safe
    ├─ created_ns = time.monotonic_ns()      # monotonic clock, not wall clock
    └─ envelope_out (stamped, new frozen dataclass instance)
```

After stamping, `envelope_out` passes through the middleware chain. If middleware
returns `None`, the stamped envelope is discarded — but the `envelope_id` and
`sequence` numbers have already been consumed. **Sequence numbers can have gaps**
when middleware drops envelopes.

---

## 5. Timing chain internal state

### `_CausalTracker` (global, across all topics)

- `_buffer: dict[int, list[_BufferedEnvelope]]` — keyed by `parent_id`; groups
  children waiting for their causal parent to be dispatched.
- Max capacity: 50,000 entries. When full, oldest entry is force-released.
- `_lock: threading.Lock`
- Cleared by `sweep()` every 5,000 ms (TTL).

### `_GapBuffer[topic]` (per-topic)

- `_buffer: deque[_BufferedEnvelope]` — envelopes waiting for their sequence
  predecessor to arrive.
- `_last_dispatched_seq: int` — highest sequence dispatched for this topic.
- Max capacity: 10,000 entries.
- `_lock: threading.Lock`
- Force-released after 5,000 ms.

A topic's gap buffer is created lazily on first use and never destroyed (retained for
the lifetime of the bus). Gap buffers for rarely-used topics consume memory permanently.

---

## 6. `BusStats` — observable state

`BusStats` is a plain counter bag. Fields:

| Field | Incremented when |
|---|---|
| `published` | Each `publish()` call (before middleware) |
| `dispatched` | Each handler invocation |
| `handler_errors` | Handler raises (sync or async) |
| `mailbox_full_drops` | Async dispatch mailbox full → envelope dropped |
| `async_handler_dlq` | Retry exhaustion → DLQ callback called |
| `middleware_drops` | Middleware returns `None` |
| `sequence_gaps_detected` | Gap buffer sees out-of-order sequence |
| `gap_buffer_force_releases` | Gap buffer TTL expired, force-dispatched |

Not thread-safe (int increment without lock). Values are eventually consistent under
concurrent publish. Use for monitoring, not for invariant enforcement.

---

## 7. `LocalMailbox` internal state

| Field | Type | Notes |
|---|---|---|
| `_queue` | `collections.deque[Envelope]` | Bounded by `capacity` |
| `_cond` | `threading.Condition` | `receive(timeout_ms)` blocks on this |
| `_closed` | `bool` | Set by `close()` — unblocks waiting receivers |
| `_delivered_count` | `int` | Total envelopes enqueued |
| `_received_count` | `int` | Total envelopes consumed by `receive()` |

`pending() = _delivered_count - _received_count`. This is approximate under concurrent
access (no lock on the subtraction).

`receive(timeout_ms=0)`: returns immediately if queue non-empty; blocks for `timeout_ms`
ms if empty; returns `None` on timeout or close.

---

## 8. `LocalMailboxRouter` internal state

| Field | Type | Mutated by |
|---|---|---|
| `_actors` | `dict[str, LocalMailbox]` | `register()`, `unregister()` |
| `_lock` | `threading.RLock` | All actor registry operations |

`_actors` is the source of truth for which actors exist. `register()` creates a
`LocalMailbox` and inserts it. `unregister()` calls `mailbox.close()` then removes it.

---

## 9. `IdempotencyMiddleware` state

```python
IdempotencyMiddleware(cache_size: int = 4096, ttl_ms: int = 60_000)
│
├─ _cache: OrderedDict[(topic, request_id), expiry_ns]  # LRU bounded
└─ _lock: threading.Lock
```

On `process(envelope)`:
1. If `envelope.request_id == ""`: passthrough (no dedup for anonymous events).
2. Key = `(envelope.topic, envelope.request_id)`.
3. If key in cache AND not expired: return `None` (drop duplicate).
4. Else: insert key with TTL, evict LRU if at capacity, return envelope.

Cache is never cleared except by LRU eviction and TTL expiry. Memory footprint is
bounded by `cache_size` entries × ~200 bytes = ~800 KB at default size.

---

## 10. Concurrency invariants

The following invariants hold under concurrent use of `LocalBus`:

1. **No two envelopes on the same topic share a sequence number.** Guaranteed by per-topic lock in `_SequenceGenerator`.
2. **No two envelopes share an `envelope_id`.** Guaranteed by global lock in `_EnvelopeIdGenerator`.
3. **A handler that completes without raising has processed the envelope.** The bus makes no guarantees about what the handler did with it.
4. **Handler A does not see envelope E before handler B if both subscribed before E was published.** Order within a single `publish()` call follows the order handlers appear in the trie match result (insertion order, not priority order, for sync dispatch).
5. **Subscribing while publish is in-flight does not cause a race.** The read/write lock ensures subscribe acquires an exclusive write lock; publish holds a shared read lock. They are mutually exclusive.
6. **`close()` is idempotent.** Multiple calls do not panic.
