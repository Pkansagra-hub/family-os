# K1 SessionState — OPEN ISSUES

---

## SS-01 · `task_state`, `task_artifacts`, and `artifacts_warm` serialize JSON, not FlatBuffer — wiring gap, not missing schemas

**Severity:** Medium
**Category:** Contract violation / serialization correctness
**Location:** `k1/sessionstate/sections/task_state.py`, `sections/task_artifacts.py`, `sections/artifacts_warm.py`

> **CORRECTION (May 2026):** The original description said "POC -- no FlatBuffer schema"
> and implied schemas needed to be written. **This is wrong.** Generated FlatBuffer
> bindings already exist:
> - `k1/sessionstate/generated/flatbuffers/K1/SessionState/TaskStateSection.py`
> - `k1/sessionstate/generated/flatbuffers/K1/SessionState/TaskArtifactsSection.py`
> - `k1/sessionstate/generated/flatbuffers/K1/SessionState/ArtifactsWarmSection.py`
>
> The docstring comment "POC -- no FlatBuffer schema for task_state" is **stale and wrong**.
> The work is purely in **wiring** the existing generated bindings into the section classes.
> Also: `artifacts_warm` is a **third affected section** not mentioned in the original text.

`ISection.to_flatbuffer()` is specified to return FlatBuffer bytes. All three sections
(`task_state`, `task_artifacts`, `artifacts_warm`) still return `json.dumps(...).encode()`
instead, despite generated bindings existing.

**Failure mode:** Checkpoint and restore use JSON deserialization for these three sections.
Any FlatBuffer-aware deserializer (migration tooling, schema evolution tooling) will fail
to decode them. The divergence is undocumented at the `ISection` contract level.

**Fix:** Wire the existing generated bindings: update each section class's `to_flatbuffer()`
to use the generated builder. Remove stale "POC" comments.

---

## SS-02 · `SQLiteStorageAdapter` and `LocalColdArchive` share one SQLite file with inconsistent table sets

**Severity:** Medium
**Category:** Data integrity / architecture duplication
**Location:** `k1/sessionstate/adapters/sqlite_storage.py`, `k1/sessionstate/local_cold.py`

Both classes open `~/.familyos/k1/sessionstate.db`. `LocalColdArchive` has 7 tables
(adds `st_telemetry_archive`, `st_persona_archive`, `st_artifacts_archive`).
`SQLiteStorageAdapter` has only 4.

Consequences:
- It is unclear which class is authoritative for which operations.
- `SQLiteStorageAdapter` cannot restore telemetry, persona, or artifact cold archives
  created by `LocalColdArchive`, and vice versa.
- `KernelService` may construct both for the same session, resulting in schema
  contention or silent missing-table errors for the 3 additional tables.

**Fix:** Merge into one class (or make `SQLiteStorageAdapter` the `IStoragePort` façade
that delegates all raw SQL to `LocalColdArchive`). A single table-creation `_init_db()`
call should own the full 7-table schema.

---

## SS-03 · Double-lock acquisition: `DirectWriterAdapter._lock` then `SessionStateManager._write_lock`

**Severity:** Medium
**Category:** Concurrency correctness
**Location:** `k1/sessionstate/adapters/direct_writer.py`, `k1/sessionstate/manager.py`, `k1/sessionstate/guard.py`

`DirectWriterAdapter.request_mutation()` acquires `DWA._lock: RLock`, then calls
`manager.mutate()` which acquires `SSM._write_lock: RLock`. Both are `threading.RLock`
(reentrant per-thread), so a single-threaded caller is safe. But:

> **CORRECTION (May 2026):** Original description said the third lock was `_section_lock`.
> **Actual attribute name is `_lock`** on `MutationGuard` (`guard.py:327`).
> Unlike all other locks in the module (RLock), `MutationGuard._lock` is a plain
> `threading.Lock` (non-reentrant). Calling any `MutationGuard` method twice from
> the same thread deadlocks on the guard's own `_lock`.

- Lock ordering `DWA._lock → SSM._write_lock → guard._lock` is confirmed correct
  **only** if all callers follow this order.
- **Latent deadlock:** If a `MutationApprovedEvent` subscriber (dispatched on the
  same thread that holds `DWA._lock`) calls back into `DirectWriterAdapter`, the
  dispatch thread will deadlock on `DWA._lock` (which is already held, and `RLock`
  *would* allow re-entry — but `DWA._lock` is a plain `Lock`, not `RLock`; verify
  the actual type).
- Acquisition ordering is undocumented and not enforced by assertions.

**Fix:** Document and enforce global lock acquisition order:
`DirectWriterAdapter._lock → SessionStateManager._write_lock → MutationGuard._lock`.
Add assertions (in debug mode) that this order is always followed. Ensure
`MutationApprovedEvent` dispatch happens **after** all locks are released.

---

## SS-04 · No mutation audit trail

**Severity:** Medium
**Category:** Observability / security
**Location:** `k1/sessionstate/manager.py` (absent)

There is no record of which writer, at what timestamp, wrote what operation to which
section. `MutationRequest.writer_id` and `cognitive_trace_id` are accepted but not
persisted beyond the in-flight event emission.

This means:
- Post-mortem debugging of unexpected state requires replaying bus events (only available
  in testing capture mode).
- Security audits for SS-01 (Concierge-only writes) cannot be verified after the fact.
- `delegation_chain` in `MutationRequest` is accepted but has no enforcement contract.

**Fix:** Write a compact mutation log row to SQLite (section, operation, writer_id,
cognitive_trace_id, bytes_delta, timestamp_ms) on every `MutationApprovedEvent`.
Keep a rolling window of the last N=1000 rows in the audit table.

---

## SS-05 · `k1/coordination/sessionstate_concurrency/` is an empty stub

**Severity:** Low (current) / High (future multi-process)
**Category:** Missing feature / architecture gap
**Location:** `k1/coordination/sessionstate_concurrency/__init__.py`

`k1/coordination/` has three empty sub-packages. No distributed locking, consensus,
or leader election is implemented. The current threading model assumes a single Python
process owns each `SessionStateManager`.

If a future deployment runs multiple K1 processes sharing the same SQLite file
(e.g., for hot standby or session migration), concurrent writes will corrupt state
because SQLite WAL serialises at the file level but HOT/WARM in-memory state is not
shared.

**Fix:** Before any multi-process deployment: implement a file-based leader-lock
(e.g., `fcntl.flock`) or move to a shared memory store (Redis/Valkey).
At minimum, document that one process per session is a hard constraint.

---

## SS-06 · No write-rate limiting on `IWriterPort`

**Severity:** Low (current) / Medium (buggy caller scenarios)
**Category:** Resource protection
**Location:** `k1/sessionstate/guard.py` (absent), `k1/sessionstate/manager.py` (absent)

`MutationGuard.preflight()` enforces capacity but not write throughput. A misbehaving
Concierge (or any caller with access to `DirectWriterAdapter`) can issue mutations in a
tight loop, fully consuming CPU on the lock + preflight path even if every write is
approved.

**Fix:** Add a per-writer token-bucket rate limiter in `MutationGuard`. Configurable via
`SessionStateConfig` (e.g., `max_mutations_per_second: int = 0` where 0 = unlimited).

---

## SS-07 · `LocalEventAdapter` dispatch queue has unbounded growth

**Severity:** Medium (raised from Low)
**Category:** Resource protection / correctness
**Location:** `k1/sessionstate/adapters/local_events.py`

> **CORRECTION (May 2026):** The original description said `emit()` calls
> `_queue.put_nowait()` with a `_drop_count` path for queue full. **This is wrong.**
> Actual code uses **blocking `_queue.put()`** with NO `put_nowait` and NO `_drop_count`.
> The queue is constructed as `queue.Queue()` with no `maxsize`.

**Actual behavior:** `emit()` calls `_queue.put(item)` which blocks the caller
thread if the queue is full (it cannot be full since it has no maxsize). The queue
grows unbounded. There is **no drop path** and **no backpressure signal**.

**Failure mode:** If the dispatch thread falls behind (slow handler), queue grows without
bound consuming heap. The emitting thread never blocks (since queue is unbounded), so
there is no natural backpressure. Under sustained load the process OOMs silently.

**Fix:** Construct `queue.Queue(maxsize=N)` with a configurable cap (e.g., 10,000).
Switch `emit()` to `_queue.put_nowait()` with a `try/except queue.Full` drop path.
Increment a `_drop_count` metric and log a WARNING. Document the drop behaviour in
`IEventPort`.

---

## SS-08 · `SectionDataAdapter._overflow` buffer is never drained on error

**Severity:** Low
**Category:** Memory leak / silent correctness failure
**Location:** `k1/sessionstate/adapters/section_data_adapter.py`

`_overflow: Dict[str, List[MigrationItem]]` accumulates items when `add_items(section,
items)` is called before `accept_demoted()` succeeds. If the target section never
accepts the items (e.g., WARM tier is full when a demotion is attempted), overflow items
remain in `_overflow` indefinitely, occupying heap memory outside the tracked budgets.

This means `SizeTracker` can under-count actual heap usage, and `MutationGuard`
capacity checks may approve mutations that would push actual usage above the limit.

**Fix:** If `accept_demoted()` fails, either retry with back-off, raise a
`MigrationError`, or evict items from overflow before inserting new ones. Document the
recovery path in `IMigrationSectionProvider`.

---

## SS-09 · `StandaloneLifecycle` timer not reset after manual checkpoint

**Severity:** Low
**Category:** Correctness / unnecessary I/O
**Location:** `k1/sessionstate/adapters/standalone_lifecycle.py`

The periodic checkpoint is implemented with `threading.Timer` (one-shot, re-armed in
`_on_timer_tick()`). If the caller invokes `manager.checkpoint()` manually (e.g., in
response to pressure), the timer is not cancelled and rescheduled from that point.
The timer fires again at its original deadline, potentially issuing a checkpoint seconds
after a manual one.

Under high pressure, this can cause multiple redundant checkpoints within a single
interval window, adding SQLite write amplification.

**Fix:** After any manual `checkpoint()` call (from outside the timer path), cancel the
current timer and reschedule a fresh one from the current time.

---

## SS-10 · `InMemoryStorageAdapter` provides no session isolation in test mode

**Severity:** Low
**Category:** Test correctness
**Location:** `k1/sessionstate/adapters/memory_storage.py`

`create_for_testing()` creates an `InMemoryStorageAdapter` backed by a module-level
(or instance-level) `Dict`. If two test functions create managers with the same
`session_id` without resetting the adapter, the second test restores data written by
the first.

This can cause non-deterministic test failures when tests are run in parallel or in
certain orderings.

**Fix:** `InMemoryStorageAdapter` should default to an empty dict per instance (confirmed
by code, but each test must create a new factory call — this should be documented as a
test constraint). Alternatively, add a `clear_all()` method and call it in test fixtures.

---

## SS-GEN-01 · Triple `return builder.EndObject()` dead code in generated FlatBuffer binding

**Severity:** Low
**Category:** Generated code quality / confusion
**Location:** `k1/sessionstate/generated/flatbuffers/K1/SessionState/TaskStateEntry.py:181-182`

`TaskStateEntry.py` in the generated FlatBuffer bindings contains three sequential
`return builder.EndObject()` statements. Only the first `return` is ever executed;
the other two are dead code introduced by a generator bug or manual edit.

**Failure mode:** No runtime failure — Python never executes the second and third
`return` statements. But the dead code is confusing and may cause future readers
to assume the function has multiple exit points.

**Fix:** Remove the two extra `return builder.EndObject()` lines. Alternatively, regenerate
the binding from the FlatBuffer schema to produce clean output.

---

## SS-04-PRE · `MutationApprovedEvent` is defined but never emitted — prerequisite blocker for SS-04

**Severity:** High (blocker for SS-04 audit trail)
**Category:** Missing implementation
**Location:** `k1/sessionstate/manager.py:mutate()`, `k1/sessionstate/events.py`

`MutationApprovedEvent` is fully defined in `events.py` and is factory-built in
`manager.py`. However, `manager.mutate()` docstring lists event emission as step 8 of
the mutation flow, but the actual implementation **never calls `_event_port.emit()`**
on the success path. The event is built but thrown away.

**Failure mode:** Subscribers registered for `MutationApprovedEvent` (including any
audit trail implementation that closes SS-04) are never called. The entire event
infrastructure for mutation approval is silently no-op.

**Fix:** Add `await self._event_port.emit(MutationApprovedEvent(...))` on the success
path of `manager.mutate()`, after the mutation is committed but before releasing
`_write_lock`. This is a prerequisite for implementing SS-04.

---

## SS-NEW-A · `writer_id` accepted but never validated — ADR-0017g enforcement missing

**Severity:** Medium
**Category:** Security / contract enforcement
**Location:** `k1/sessionstate/guard.py:preflight()`

`MutationRequest.writer_id` is accepted and carried through the mutation chain, but
`MutationGuard.preflight()` does not validate it. Any caller can pass any arbitrary
`writer_id` string, including the reserved `"concierge"` writer ID required by
ADR-0017g (Concierge-only write constraint).

**Failure mode:** A component other than Concierge can pass `writer_id="concierge"` and
bypass intended write-origin enforcement. The audit trail (SS-04, once built) would
record the wrong writer.

**Fix:** Add an allowlist of valid `writer_id` values to `SessionStateConfig`. In
`preflight()`, reject any `writer_id` not in the allowlist with a `PrefightError`.

---

## SS-NEW-B · `ThrashConfig` is dead config — `_ss_cfg.thrash` is never read

**Severity:** Low
**Category:** Dead code / configuration surface confusion
**Location:** `k1/sessionstate/config.py:78-88`

`ThrashConfig` dataclass (`max_evictions_per_second`, `thrash_window_s`,
`auto_expand_on_thrash: bool`) is defined and has a `thrash: ThrashConfig` field on
`SessionStateConfig`. But nowhere in the codebase is `_ss_cfg.thrash` (or any variant)
accessed. The thrash detection and auto-expand logic is completely absent.

**Fix:** Either implement thrash detection in the migration layer and wire `ThrashConfig`
there, or remove the config fields with a comment explaining the planned future use.

---

## SS-SECURITY-01 · `SectionDataAdapter._serialize()` uses `pickle.dumps()` fallback — RCE vector

**Severity:** HIGH — Security
**Category:** Security vulnerability / unsafe deserialization
**Location:** `k1/sessionstate/adapters/section_data_adapter.py:84`

`_serialize(sec)` falls through to `pickle.dumps(sec)` when no other serializer matches.
Any data path that reaches this fallback serializes Python objects as pickle bytes and
stores them in SQLite. On restore, `pickle.loads()` would deserialize this data.

**Risk:** If an attacker can influence the content stored in a session section (e.g., via
a prompt injection that populates a task artifact), they can store a malicious pickle
payload that executes arbitrary code when the session is restored.

**Fix (immediate):** Remove the `pickle.dumps()` fallback entirely. Replace with an
explicit `raise SerializationError(f"No serializer for {type(sec)}")`. All section types
must have explicit serializers registered before reaching `_serialize()`.

**Fix (long-term):** If pickle is required for developer convenience in test mode, gate
it behind `if self._config.allow_pickle_fallback` (default `False`, only `True` in dev).
Never allow pickle fallback in production.

---

## SS-NEW-C · `LocalEventAdapter._running` written without lock in `stop()` — memory visibility

**Severity:** Low
**Category:** Thread safety
**Location:** `k1/sessionstate/adapters/local_events.py:stop()`

`stop()` sets `self._running = False` on the main thread while the dispatch thread reads
`self._running` in its loop. No lock or memory barrier protects this write. Python's
GIL provides de-facto atomicity for simple assignments, but this is an undocumented
assumption that may not hold under all Python implementations.

**Fix:** Use a `threading.Event` (`_stop_event`) instead of a bare bool flag. `stop()`
calls `_stop_event.set()`. The dispatch loop checks `_stop_event.is_set()`.

---

## SS-NEW-D · `LocalEventAdapter` has no `__del__` or context manager — daemon thread leak

**Severity:** Low
**Category:** Resource management
**Location:** `k1/sessionstate/adapters/local_events.py`

`LocalEventAdapter` starts a `threading.Thread(daemon=True)` for event dispatch.
There is no `__del__`, `__enter__`/`__exit__`, or explicit `close()` method.
If the adapter is garbage-collected without `stop()` being called, the daemon thread
is abandoned. In tests or repeated start/stop cycles, this creates accumulated daemon
thread debt.

**Fix:** Implement `close()` (alias for `stop()`) and `__enter__`/`__exit__` to ensure
the adapter is usable as a context manager.

---

## SS-NEW-E · `_overflow` bytes never reported to `SizeTracker` — amplifies SS-08

**Severity:** Low
**Category:** Silent capacity undercounting
**Location:** `k1/sessionstate/adapters/section_data_adapter.py`

`SectionDataAdapter._overflow` accumulates migration items when `accept_demoted()`
fails (see SS-08). These bytes are on the heap but are not reported to `SizeTracker`.
As a result, `MutationGuard.preflight()` reads understated usage from `SizeTracker`
and approves writes that would push actual heap usage above the configured limit.

The undercount compounds with SS-08: not only are overflow items never drained,
their size is invisible to the capacity enforcement system.

**Fix:** After any item is added to `_overflow`, call
`self._size_tracker.record_overflow(bytes_used)`. When overflow is drained, call
`self._size_tracker.release_overflow(bytes_used)`. Fix SS-08 first (drain logic), then
SS-NEW-E (size tracking) to restore capacity accuracy.
