# K1 Memory Writer — STATE

---

## 1. `MemoryWriterService` mutable fields

| Field | Type | Mutated by | Read by |
|---|---|---|---|
| `_started` | `bool` | `start()`, `stop()` | `is_started`, `health_check()` |

All other `MemoryWriterService` state is delegated to `_dispatcher`, `_circuit_breaker`, and `_pipeline`.

---

## 2. Service lifecycle state machine

```
NOT_STARTED
    │
    └─ start() ────────────────────────────────────► RUNNING
              (calls dispatcher.start(); raises on error)       │
                                                                 │
                                                      stop() ───┘
                                                          │
                                                          ▼
                                                       STOPPED
```

`start()` is not idempotent — calling twice raises `RuntimeError("already started")`.
`stop()` on a non-running service raises `RuntimeError("not started")`.

---

## 3. `TurnDispatcher` mutable state

| Field | Type | Protected by | Mutated by | Notes |
|---|---|---|---|---|
| `_subscription` | `Subscription \| None` | asyncio single-task | `start()`, `stop()` | Bus subscription handle |
| `_processed_ids` | `set[str]` | asyncio single-task | `_process_turn()` | Per-session dedup; lost on restart |
| `_processing` | `bool` | asyncio single-task | `_process_turn()` | True while pipeline is executing |
| `_queued_payload` | `TurnCompletePayload \| None` | asyncio single-task | `_on_turn_complete()` | Newest-wins queue; at most 1 waiting |

### Backpressure state machine:

```
_processing=False, _queued=None
    │
    ├─ turn arrives ──► asyncio.create_task(_process_turn(payload))
    │                      _processing=True
    │                      │
    │                      │── turn arrives during processing ──► _queued = payload (newest wins)
    │                      │
    │                      └─ processing done → _processing=False
    │                              if _queued: _process_turn(_queued); _queued=None
    │
    └─ (steady state: no turns buffered beyond 1)
```

`_processed_ids` is never pruned during a session — unbounded growth for very long sessions.

---

## 4. `SessionBatchDispatcher` mutable state

| Field | Type | Protected by | Mutated by | Notes |
|---|---|---|---|---|
| `_subscription` | `Subscription \| None` | asyncio Lock | `start()`, `stop()` | Bus subscription handle |
| `_buffer` | `list[TurnCompletePayload]` | `asyncio.Lock` | `_on_turn_completed()`, `_flush_buffer()` | Turn accumulation buffer |
| `_processed_ids` | `set[str]` | `asyncio.Lock` | `_on_turn_completed()` | Per-session dedup; lost on restart |
| `_last_arrival_ts` | `float` | `asyncio.Lock` | `_on_turn_completed()` | `time.time()` at last buffered turn |
| `_idle_task` | `asyncio.Task \| None` | asyncio single-task | `start()`, `stop()` | Background idle-flush loop |
| `_stopping` | `bool` | asyncio single-task | `stop()` | Signals idle loop to exit |

**Lock scope:** `asyncio.Lock` protects `_buffer`, `_processed_ids`, `_last_arrival_ts` as a unit.
`_idle_task` and `_stopping` are only accessed from the coroutine that owns `start()`/`stop()`.

### Flush trigger state machine:

```
ACCUMULATING
    │
    ├─ len(_buffer) >= flush_turn_threshold (default 20) ──► FLUSHING
    │                                                              │
    ├─ idle loop: time since last arrival >= flush_idle_seconds ──┤
    │                                                              │
    └─ stop() called ──────────────────────────────────────────────┤
                                                                   │
                                                                   ▼
                                                             pipeline.process_session(buffer)
                                                                   │
                                                                   └─ ACCUMULATING (empty buffer)
```

Multiple concurrent flush tasks are possible (threshold flush racing idle flush) but both
acquire the `asyncio.Lock` and drain `_buffer` atomically — the second flush sees an
empty buffer and exits early.

---

## 5. `CircuitBreaker` mutable state

Shared instance across `MemoryWriterPipeline` and (if `MemoryWriterFabricRegistration` is used)
`HealthAdapter`. All state transitions are synchronous; no locking (single asyncio task assumption).

| Field | Type | Mutated by |
|---|---|---|
| `_state` | `CircuitBreakerState` | `record_failure()`, `record_success()`, `reset()` |
| `_consecutive_failures` | `int` | `record_failure()` (increment), `record_success()` (reset to 0), `reset()` |
| `_last_failure_time` | `float \| None` | `record_failure()` sets to `clock()` |
| `_total_trips` | `int` | `record_failure()` increments when threshold crossed |

### State machine:

```
CLOSED
  │  record_failure() × failure_threshold ──► OPEN; _total_trips += 1
  │
OPEN
  │  clock() - _last_failure_time >= recovery_probe_seconds ──► HALF_OPEN (lazy check in is_open)
  │
HALF_OPEN
  ├─ record_success() ──► CLOSED; _consecutive_failures=0
  └─ record_failure() ──► OPEN; _last_failure_time = now
```

`is_open` property does the OPEN→HALF_OPEN transition lazily:
```python
if self._state == OPEN and elapsed >= probe_seconds:
    self._state = HALF_OPEN
    return False  # allow one probe
```

**Circuit breaker scope:** One instance per `MemoryWriterService` session. No cross-session bleed.

---

## 6. `DeltaAggregator` mutable state

| Field | Type | Mutated by | Cleared by |
|---|---|---|---|
| `_pending` | `list[dict]` | `add()` | `flush()` |
| `_seen_hashes` | `set[str]` | `add()` | `flush()` |

### State invariants:
- `_pending` and `_seen_hashes` are always reset together in `flush()`.
- Hash key: `sha256(f"{sorted(participants)}:{sorted(topics)}".encode()).hexdigest()[:16]`
- `add()` returns `False` (deduped) if hash already in `_seen_hashes`; atom is not added.
- `flush()` sorts `_pending` by `(conversation_turn, extraction_sequence)` before returning.
- After `flush()`: `_pending=[]`, `_seen_hashes=set()`.

`DeltaAggregator` is NOT thread-safe. Assumed single-asyncio-task access.

---

## 7. `EventSubscriptionAdapter` mutable state

| Field | Type | Mutated by |
|---|---|---|
| `_subscriptions` | `dict[str, Subscription]` | `subscribe()` (adds), `unsubscribe()` (removes) |

`subscribe()` registers the MW async handler with the underlying FabricBusAdapter using a
sync wrapper: `loop.create_task(async_handler(payload))`. This means bus delivery is decoupled
from the handler coroutine — the task runs on the next event loop iteration.

---

## 8. `PromptLoader` mutable state (lazy cache)

| Field | Type | Mutated by |
|---|---|---|
| `_cache` | `dict[str, str]` | `load(path)` on first call per path |

`PromptLoader.load(path)` reads `memory_writer_persona.md` from disk on first call, caches the
string. Subsequent calls return cached value. One read per `MemoryWriterAgent` lifetime.

---

## 9. `MemoryWriterPipeline` — no mutable state

`MemoryWriterPipeline` itself has no mutable fields. All state is in the injected components:
`RelevanceFilter` (contains `DedupRingBuffer`), `DeltaAggregator`, `CircuitBreaker`.

`RelevanceFilter` contains a `DedupRingBuffer` (window=300s). The ring buffer's mutable state:

| Field | Type | Mutated by |
|---|---|---|
| `_ring` | `deque[tuple[str, float]]` | `_add_hash(hash, timestamp)` on each pass |
| Implicit eviction | via deque maxlen OR time-based scan | `evaluate()` prunes entries older than window |

The ring buffer dedup key is `sha256(sorted_participants:sorted_topics)[:16]` — same as
`DeltaAggregator`. They are independent: filter runs before extraction, aggregator runs after.

---

## 10. Session-level state lifetime

All mutable state in MW is scoped to a single `MemoryWriterService` instance. There is no
shared global state. On `stop()` / teardown, the following state is permanently lost:

| State | Lost on stop? | Recovery possible? |
|---|---|---|
| `_processed_ids` (TurnDispatcher / SBD) | Yes — in-memory only | No — redelivered turns re-extracted |
| `CircuitBreaker` state | Yes — reset to CLOSED on new instance | Yes — effectively self-heals |
| `DeltaAggregator._pending` | Yes — if not flushed before stop | Partially — SBD flush is called in stop() |
| `SBD._buffer` | Yes — flushed in stop() (best-effort) | If flush fails, turns are lost |
| `DedupRingBuffer` entries | Yes | No — dedup window resets |
| `PromptLoader._cache` | Yes | Auto-reloads from disk on next access |

---

## 11. Concurrency model summary

| Component | Model | Mechanism |
|---|---|---|
| `TurnDispatcher` | Single asyncio task | No lock; backpressure via `_processing` flag |
| `SessionBatchDispatcher` | Multiple asyncio tasks | `asyncio.Lock` for buffer mutations; `asyncio.Task` for idle loop |
| `MemoryWriterPipeline` | Fully sequential per call | `await` chain; no parallelism inside pipeline |
| `CircuitBreaker` | Single asyncio task assumed | No lock; transitions are synchronous property checks |
| `DeltaAggregator` | Single asyncio task assumed | No lock |
| `EventSubscriptionAdapter` | Sync wrapper → async task | `loop.create_task()` decouples delivery from handler |

MW does not use threads, `asyncio.run_in_executor`, or `asyncio.gather` within the pipeline.
All concurrency is event-driven via the bus dispatcher.
