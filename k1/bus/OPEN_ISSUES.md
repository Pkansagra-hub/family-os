# K1 Bus — OPEN ISSUES

---

## ISSUE-B01 — TTL expiry not enforced in Python `LocalBus`

**Severity:** Medium
**Location:** `k1/bus/impl/local_bus.py`, `k1/bus/envelope/envelope.py`

**Current behavior:**
`Envelope` has a `ttl_ms: int` field (V2 addition). The Python `LocalBus` never checks
it. Envelopes with `ttl_ms > 0` are delivered to handlers regardless of how long they
waited in async dispatch mailboxes or gap buffers.

**Failure mode:** A HITL suspension envelope that sat in a gap buffer for >5,000 ms
may still be delivered after its intended expiry, triggering a stale HITL flow. In
BEST_EFFORT topics with slow consumers, outdated affect signals may override current
emotional state after a significant delay.

**Fix:** In `_dispatch_sync` and `_dispatch_async`, check
`time.monotonic_ns() > envelope.created_ns + envelope.ttl_ms * 1_000_000` before
invoking handlers. If expired: log at DEBUG, increment `stats.ttl_drops`, invoke
`dlq_callback(envelope, TtlExpiredError(), 0)` if configured. The Rust `dlq.rs`
already has `DlqReason.TtlExpired` — this is a Python parity gap.

> **Note (May 2026):** `_dispatch_sync` and `_dispatch_async` are the correct method names
> to search for in `local_bus.py`. Verify exact names if the file was renamed.

---

## ISSUE-B02 — Sequence numbers silently gap when middleware drops envelopes

**Severity:** Low
**Location:** `k1/bus/impl/local_bus.py:publish()`

**Current behavior:**
`envelope_id` and `sequence` are stamped before the middleware chain runs. If any
middleware returns `None` (e.g. `IdempotencyMiddleware` drops a duplicate), the
sequence counter for that topic has been incremented but the envelope was never
delivered. Downstream consumers using sequence numbers for gap detection will see a
gap and hold envelopes in the gap buffer for the full 5,000 ms TTL before force-release.

**Failure mode:** A batch of 10 duplicate events (same `request_id`) all pass through
the `_SequenceGenerator` and increment the per-topic sequence counter 10 times, but
9 are dropped. The 10th legitimate envelope arrives with sequence=N+9. Any STRICT-mode
consumer waiting for the full sequence chain will buffer for 5,000 ms before
force-releasing.

**Fix:** Move sequence stamping to after the middleware chain, or stamp optimistically
and pass a `_seq_hint` through the middleware so `IdempotencyMiddleware` can return
`SKIP_SEQUENCE_STAMP` rather than `None`. The simplest fix: stamp `sequence=0` before
middleware, stamp real sequence only in `_dispatch_*` if middleware did not drop.

---

## ISSUE-B03 — Gap buffer and `_expected` per-topic state grows unbounded for inactive topics

**Severity:** Low
**Location:** `k1/bus/timing/timing_chain.py:_CausalTracker`, `_GapBuffer`

> **CORRECTION (May 2026):** Original description said "50 separate `_GapBuffer` objects".
> There is **ONE `_GapBuffer` per bus** (attribute `_gap`), not one per topic.
> Per-topic state that leaks is `_expected[topic]: int` (sequence counter) and
> `_locks[topic]: threading.Lock` — both are Python dicts that grow without bound
> and are **never deleted** even when the topic is inactive. 1 Lock + 1 int leak per
> unique topic seen.

**Current behavior:**
`_expected` and `_locks` are created lazily per topic and never destroyed for the
lifetime of the bus. A session with 50 distinct task topics retains 50 threading.Lock
objects and 50 integer counters indefinitely.

**Failure mode:** Long-lived sessions with many distinct task IDs in topic names (e.g.
`k1.tool.{task_id}.started.v1`) accumulate O(N) locks where N = number of distinct
topics seen. For sessions with 1,000+ tool calls, this is 1,000+ lock objects.

**Fix:** Add a LRU eviction policy to `_locks` and `_expected`: cap at 512 topics,
evict least-recently-used when at capacity. Force-release pending entries before eviction.

---

## ISSUE-B04 — Async dispatch `BusStats.mailbox_full_drops` counter is not observable

**Severity:** Low
**Location:** `k1/bus/impl/local_bus.py:_AsyncSubscription.enqueue()`

**Current behavior:**
When async dispatch mailbox is full, the envelope is dropped and `stats.mailbox_full_drops`
is incremented. However, there is no alerting hook, no structured log field for the
subscription ID or pattern, and no DLQ callback invoked for backpressure drops. The
only signal is a WARNING log line.

**Failure mode:** A slow HITL handler causes its subscription mailbox to fill. Every
subsequent HITL envelope is silently dropped. `stats.mailbox_full_drops` increments
but nobody is watching it. The system appears healthy (no exceptions) but HITL
suspensions are lost.

**Fix:** Invoke `dlq_callback(envelope, BackpressureError(), 0)` for
backpressure drops (same path as retry exhaustion). This makes mailbox-full drops
observable via the same DLQ sink as handler errors. Also add `subscription_id` and
`pattern` to the WARNING log structured fields.

---

## ISSUE-B05 — `RustBusAdapter` envelope conversion overhead is not profiled

**Severity:** Medium
**Location:** `k1/bus/impl/rust_bus_adapter.py`

**Current behavior:**
Every `publish()` via `RustBusAdapter` performs:
1. Python `Envelope → RustEnvelope` (FlatBuffers serialize in Rust, Python attr copy)
2. Rust trie match + ring buffer dispatch
3. `RustEnvelope → Python Envelope` for each handler callback

For K1's publish rate (~2,000–5,000 envelopes/minute per session), the conversion
overhead may negate the Rust trie-matching benefit. There are no benchmarks comparing
end-to-end latency for Python `LocalBus` vs `RustBusAdapter` at K1 publish rates
(the Criterion benchmarks in `benches/` test Rust-only throughput, not the Python
boundary cost).

**Failure mode:** No crash — but the "Rust is faster" assumption may be wrong for
K1's actual workload profile. A session with 10 concurrent subscribers and 20 topics
may see HIGHER latency with `RustBusAdapter` than with `LocalBus(TopicTrie=Rust)` due
to double serialization on every publish.

**Fix:** Add a Python-level benchmark (`tests/k1/bus/bench_roundtrip.py`) that measures
`LocalBus` vs `RustBusAdapter` publish latency at K1-realistic fan-out (10 subscribers,
20 topics, mixed payload sizes). Run in CI on a pinned hardware profile.

---

## ISSUE-B06 — `SessionBusAdapter.emit_batch()` is not truly atomic

**Severity:** Low
**Location:** `k1/bus/adapters/session_adapter.py:emit_batch()`

**Current behavior:**
`emit_batch(events)` calls `bus.publish(envelope)` in a loop. Between the first and
last publish, other threads can publish envelopes that interleave. The docstring says
"batch emit within a single lock window" but there is no actual single-lock batch
operation in `IBus` — it calls `publish()` N times, each acquiring and releasing the
read lock independently.

**Failure mode:** If a SessionState update consists of 5 field mutations published as
a batch (e.g. updating `control.fsm_state`, `control.active_task_ids`,
`control.complexity_tier`, `history.entries`, `task_state.status`), another component
subscribing to any of these topics may see a partially-applied update — e.g. `fsm_state`
updated but `active_task_ids` not yet updated.

**Fix:** Add `IBus.publish_batch(envelopes: list[Envelope]) -> None` that acquires the
read lock once and dispatches all envelopes before releasing. For the Python `LocalBus`,
this is a trivial single-lock loop. For `RustBusAdapter`, delegate to
`k1_bus_core.RustBus.publish_batch()`.

---

## ISSUE-B07 — `TopicValidationMiddleware` has no enforcement in production

**Severity:** Low
**Location:** `k1/bus/middleware/topic_validation.py`

> **CORRECTION (May 2026):** Original description said `BusFactory.create_ordered()`.
> **Actual method name is `BusFactory.create_local_ordered()`**. Fix accordingly when
> wiring `TopicValidationMiddleware`.
>
> **New gap:** `DEFAULT_TOPIC_REGISTRY` referenced in the fix description below
> **does not exist anywhere** in the codebase. It must be created before
> `TopicValidationMiddleware` can be wired with a registry (see ISSUE-B-REGISTRY).

**Current behavior:**
`TopicValidationMiddleware` exists and is fully implemented, but it is wired via
`MiddlewareChain` only in the test factory (`BusFactory.create_testing()`). Production
buses constructed via `BusFactory.create_local_ordered()` never include it.

**Failure mode:** Components can publish to arbitrary topic strings (e.g. typos like
`k1.agent.task_complete.v1` instead of `k1.agent.task.completed.v1`) with no
detection. The envelope is published, no subscriber matches, and the event silently
disappears.

**Fix:**
1. Create `DEFAULT_TOPIC_REGISTRY` (see ISSUE-B-REGISTRY).
2. Wire `TopicValidationMiddleware(registry=DEFAULT_TOPIC_REGISTRY)` into
   `BusFactory.create_local_ordered()`. Log at WARNING for unknown topics initially.

---

## ISSUE-B08 — WFQ in `LocalMailbox` is not yet implemented (V1 priority only)

**Severity:** Low
**Location:** `k1/bus/impl/local_mailbox.py`

**Current behavior:**
`MailboxConfig.priority_wfq: bool = True` is accepted but has no effect. The
`LocalMailbox` uses a single `collections.deque` — FIFO, no priority. The code
comment says: "V1 is STRICT priority (not weighted round-robin). V2 (future): true
weighted fair queueing to prevent BACKGROUND starvation."

`MailboxConfig(priority_wfq=True)` is passed for both `ACTOR_FRONT` and `ACTOR_BACK`
mailboxes, implying callers expect WFQ behavior — but they are getting plain FIFO.

**Failure mode:** BACKGROUND-priority envelopes (e.g. `k1.fabric.learning` events)
sent to a mailbox that is also receiving URGENT HITL events will be served in arrival
order. A burst of BACKGROUND events can delay URGENT event processing in the `ACTOR_FRONT`
mailbox. For HITL, this means the user-facing suspension relay is delayed behind
learning metrics.

**Fix:** Implement a proper WFQ (Deficit Round-Robin) in `LocalMailbox`. Use 4 priority
buckets corresponding to `Priority.URGENT/REALTIME/INTERACTIVE/BACKGROUND`. On `receive()`,
serve from highest non-empty bucket. The Rust `PyWfqScheduler` already implements DRR —
expose it or port the algorithm to Python.

---

## ISSUE-B-REGISTRY — `DEFAULT_TOPIC_REGISTRY` referenced in B07 fix does not exist

**Severity:** Low (blocker for B07)
**Location:** `k1/bus/middleware/topic_validation.py`, `k1/bus/factory.py`

`TopicValidationMiddleware` requires a `registry` argument that maps known topic names
to their schema/version metadata. The fix for ISSUE-B07 references
`DEFAULT_TOPIC_REGISTRY`, but **this object does not exist anywhere** in the codebase.

**Failure mode:** ISSUE-B07 cannot be resolved without first creating
`DEFAULT_TOPIC_REGISTRY`. Attempting to wire `TopicValidationMiddleware` without a
registry will either raise `TypeError` at construction or produce an empty no-op validation.

**Fix:**
1. Create `k1/bus/registry/topic_registry.py` with `class TopicRegistry` that stores
   known topic patterns (e.g., `k1.agent.task.completed.v1`) with optional schema refs.
2. Populate a `DEFAULT_TOPIC_REGISTRY` instance with all topics defined in
   `k1/contracts/` and `k1/*/events.py`.
3. Export from `k1/bus/__init__.py` so `BusFactory.create_local_ordered()` can import it.
