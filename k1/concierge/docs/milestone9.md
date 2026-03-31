## M9: Protocol Lifecycle Migration to Ledger — Implementation Plan

### Codebase State Summary

**What's ready (M1-M8 complete):**

| Infrastructure | File | Status |
|---|---|---|
| Ledger store | ledger/store.py (210 lines) | `ILedgerStore` protocol, `InMemoryLedgerStore`, `LedgerEntry` frozen dataclass |
| Ledger writer | ledger/writer.py (~140 lines) | `LedgerWriter` with `append()` (async) + `append_sync()`, idempotency via event_id |
| Projections | ledger/projections.py (387 lines) | `project_history()`, `project_task_states()`, `project_pending_results()`, `project_dead_letters()` — all pure functions |
| Canonical events | events/ (10 files, 30 event classes) | Full coverage: task lifecycle (6), HITL (4), conversation (4), weave (4), pool (7), mutation (1) — 26 in `EVENT_TYPE_REGISTRY` |
| Controller dual-write | controller.py | `_write_history()` already does ledger-before-memory via `_emit_ledger_event()` |
| Bootstrap ledger wiring | bootstrap.py | Creates `InMemoryLedgerStore` + `LedgerWriter`, calls `fsm.set_ledger()` |

**What's partially wired (ledger param exists but never used):**

| Component | Param Exists At | Writes to Ledger? |
|---|---|---|
| `CancellationHandler.cancel_task()` | `ledger: Any = None` | NO |
| `CancellationHandler.request_cancel()` | `ledger: Any = None` | NO |
| `SuspensionManager.suspend()` | `ledger: Any = None` | NO |
| `SuspensionManager.resolve()` | `ledger: Any = None` | NO |
| `HILCoordinator.handle_needs_human()` | `ledger: Any = None` | NO |
| `HILCoordinator.handle_user_response()` | `ledger: Any = None` | NO |

**What's NOT wired at all:**

| Component | File | Gap |
|---|---|---|
| `TaskBridge` | task_bridge.py (496 lines) | No ledger param anywhere. 7 lifecycle methods write directly to in-memory `TaskStateSection` |
| `FSMTurnState` | turn_state.py (251 lines) | No ledger param. `enqueue_result()` / `drain_results()` are pure in-memory |
| `_active_task_ids` / `_task_dispatch_turns` | controller.py | Set/dict mutations at ~15 locations with zero ledger writes |
| `CrashRecoveryOrchestrator` | Does not exist | M9 creates this |
| `rebuild_from_events()` | None of the 6 protocol classes have it | M9 adds to all |

**What already exists as projections (M9 can use directly):**

| Projection | In projections.py | Rebuilds |
|---|---|---|
| `project_history()` | L111 | `list[dict]` matching `TypedHistoryEntry.to_dict()` |
| `project_task_states()` | L170 | `dict[str, TaskStateEntry]` with full lifecycle + pending_hil + hil_history |
| `project_pending_results()` | L292 | `deque[dict]` matching `FSMTurnState.pending_results` shape |
| `project_dead_letters()` | L341 | `list[dict]` for observability |

**New projections needed:** `project_cancel_state()`, `project_suspension_state()`, `project_hitl_state()`

---

### Execution Plan (5 Epics, 22 Issues)

**New canonical events needed:** Only 1 — `task.cancel.confirmed` (confirms cancel cleanup). The rest (`task.created`, `task.cancelled`, `task.suspended`, `task.resumed`, `hil.requested`, `hil.resolved`, `conversation.weave.candidate`, `conversation.weave.emitted`) already exist.

---

#### PHASE 1: Foundation — TaskBridge + Cancel (E9.1 + E9.4.1-2)

**Do first because all other protocols depend on task state being in the ledger.**

##### Step 1: E9.4.1 — TaskBridge ledger integration

**File:** task_bridge.py

| Method | Current | Change |
|---|---|---|
| `__init__()` | No ledger param | Add `ledger: LedgerWriter | None = None` |
| `dispatch_task()` L186 | Direct `_task_state.add_task()` | Emit `TaskCreated` -> then `_task_state.add_task()` |
| `activate_task()` L202 | Direct `_task_state.update_status()` | Emit `TaskProgressed` -> then update |
| `suspend_task()` L216 | Direct `_task_state.update_status()` | Emit `TaskSuspended` -> then update |
| `resume_task()` L243 | Direct `update_status()` | Emit `TaskResumed` -> then update |
| `complete_task()` L300 | Direct completion | Emit `TaskCompleted` -> then update |
| `fail_task()` L323 | Direct failure | Emit `TaskFailed` -> then update |
| `cancel_task()` L341 | Direct cancel | Emit `TaskCancelled` -> then update |

**Pattern for every method:**
```python
def dispatch_task(self, task_id: str, action: str, ...) -> TaskStateEntry:
    # M9 E9.4.1: Ledger write is the commitment point
    if self._ledger is not None:
        self._ledger.append_sync(TaskCreated(
            session_id=self._ledger.session_id,
            task_id=task_id, action=action, ...
        ))
    # Then in-memory update (cache)
    return self._task_state.add_task(task_id, action, ...)
```

**Test:** `tests/poc/test_m09_e94_task_state.py`

##### Step 2: E9.4.2 — Task state projection already exists

`project_task_states()` in projections.py already handles all 7 task lifecycle events + HITL enrichment. **No new code needed** — just add test that verifies roundtrip: write via TaskBridge -> project from ledger -> compare.

##### Step 3: E9.1.1 — CancellationHandler ledger integration

**File:** cancel_handler.py

| Method | Change |
|---|---|
| `__init__()` | Add `ledger: LedgerWriter | None = None` to constructor |
| `register_task()` | Ledger write: reuse `TaskCreated` (already emitted by TaskBridge, so NO duplicate — just ensure CancellationHandler doesn't re-emit. Instead, read from ledger for rebuild.) |
| `cancel_task()` / `request_cancel()` | Activate the existing `ledger` param: `ledger.append_sync(TaskCancelled(...))` before `_cancelled_tasks.add()` |
| `confirm_cancel()` | New event: `task.cancel.confirmed` (or reuse existing cleanup semantics) |

**Key insight:** `register_task()` does NOT need to emit `task.created` — TaskBridge already does that. CancellationHandler just needs to be rebuildable FROM those events.

##### Step 4: E9.1.2 — Cancel state projection

**New function in projections.py:**

```python
def project_cancel_state(entries: list[LedgerEntry]) -> tuple[set[str], set[str]]:
    """Returns (active_task_ids, cancelled_task_ids)."""
    active: set[str] = set()
    cancelled: set[str] = set()
    for entry in entries:
        if entry.event_type == "task.created":
            active.add(entry.payload.get("task_id", ""))
        elif entry.event_type == "task.cancelled":
            tid = entry.payload.get("task_id", "")
            cancelled.add(tid)
        elif entry.event_type in ("task.completed", "task.failed"):
            tid = entry.payload.get("task_id", "")
            active.discard(tid)
    return active, cancelled
```

##### Step 5: E9.1.3 — `CancellationHandler.rebuild_from_events()`

```python
def rebuild_from_events(self, entries: list[LedgerEntry]) -> None:
    active, cancelled = project_cancel_state(entries)
    for task_id in active:
        if task_id not in self._tokens:
            self._tokens[task_id] = CancellationToken()
    for task_id in cancelled:
        self._cancelled_tasks.add(task_id)
        if task_id in self._tokens:
            self._tokens[task_id].cancel()
```

**Test:** `tests/poc/test_m09_e91_cancel_recovery.py`

---

#### PHASE 2: Suspension + HITL (E9.2 + E9.3)

##### Step 6: E9.2.1 — SuspensionManager ledger integration

**File:** suspension_manager.py

| Method | Change |
|---|---|
| `__init__()` | Add `ledger: LedgerWriter | None = None` |
| `suspend()` | Activate ledger param: emit `TaskSuspended` with full `react_history` in payload before `_active[task_id] = request` |
| `resolve()` | Emit `TaskResumed` before removing from `_active` |
| `_watch_timeout()` | Emit `hil.timed_out` (reuse existing event via `HILTimedOutEvent` or bus topic) before cleanup |

**Critical payload in `task.suspended`:** Must include `react_history` (list of prior messages), `tool_history`, `last_iteration`. This is the data that makes crash recovery zero-waste.

##### Step 7: E9.2.2 — Consolidate dual API

- Make `store_context()` and `pop_context()` delegate to `suspend()` / `resolve()`
- Remove `_contexts` dict — the `_active` dict (holding `SuspensionRequest` with full payload) becomes the single SOT
- Controller's `_on_task_suspended` changes from `store_context(task_id, payload)` to `suspend(SuspensionRequest.from_payload(payload))`
- **BUT:** Controller handlers are sync. Two options:
  - **Option A (preferred):** Keep `store_context_sync()` as a thin wrapper that does: `_active[task_id] = SuspensionRequest.from_payload(payload)` + `ledger.append_sync(...)`. No async needed for the mutation itself — only the timeout watcher is async.
  - **Option B:** Make `_on_task_suspended` async (big refactor, defer).

**I recommend Option A** — it's the minimal change that eliminates the dual-dict problem.

##### Step 8: E9.2.3 — Suspension state projection

**New function in projections.py:**

```python
def project_suspension_state(
    entries: list[LedgerEntry],
) -> tuple[dict[str, dict], dict[str, int]]:
    """Returns (active_suspensions, suspension_counts).

    active_suspensions: task_id -> full suspension payload (including react_history)
    suspension_counts: task_id -> number of suspensions
    """
```

##### Step 9: E9.2.4 — `SuspensionManager.rebuild_from_events()`

Rebuilds `_active` and `_suspension_counts` from projected state. Does NOT restart timeout watchers (that's Step 14).

##### Step 10: E9.3.1 — HILCoordinator ledger integration

**File:** hitl_coordinator.py

| Method | Change |
|---|---|
| `__init__()` | Add `ledger: LedgerWriter | None = None` |
| `handle_needs_human()` | Activate ledger param: emit `HILRequested` before `_pending_requests[task_id] = request` |
| `handle_user_response()` | Emit `HILResolved` before `_pending_requests.pop()` |
| `_handle_timeout()` | Emit timeout event before cleanup |

**Key:** `validate_before_invoke()` (L2 defense) currently reads `task_history` passed as argument. After M9, it can read hil_history from the ledger projection instead of relying on the caller to pass it. This makes L2 crash-safe.

##### Step 11: E9.3.2 — HITL state projection

**New function in projections.py:**

```python
def project_hitl_state(
    entries: list[LedgerEntry],
) -> tuple[dict[str, dict], dict[str, int], dict[str, list[dict]]]:
    """Returns (pending_requests, hil_counts, hil_histories)."""
```

##### Step 12: E9.3.3 — `HILCoordinator.rebuild_from_events()`

Rebuilds `_pending_requests`, `_hil_counts`, and injects `hil_history` into task state entries.

**Test:** `tests/poc/test_m09_e92_suspension_recovery.py`, `tests/poc/test_m09_e93_hitl_recovery.py`

---

#### PHASE 3: History + Weave Queue (E9.4.3-4)

##### Step 13: E9.4.3 — History already ledger-projected

`_write_history()` already emits canonical events to ledger (M1 E1.2.3). `project_history()` already rebuilds the history list. **The gap:** `_active_task_ids` and `_task_dispatch_turns` are NOT ledger-projected. They are derived from task lifecycle events. Add:

```python
# In controller, after ledger replay:
for task_id, entry in projected_task_states.items():
    if entry.status in (TaskStatus.DISPATCHED, TaskStatus.IN_PROGRESS, TaskStatus.SUSPENDED):
        self._active_task_ids.add(task_id)
```

##### Step 14: E9.4.4 — Pending results already projected

`project_pending_results()` already exists. **The gap:** `enqueue_result()` and `drain_results()` don't emit ledger events. Add:

| Method | Change |
|---|---|
| `enqueue_result()` L62 | Emit `WeaveCandidateArrived` to ledger before deque append |
| `drain_results()` L106 | Emit `WeaveEmitted` to ledger before deque clear |

**File:** turn_state.py — add `ledger: LedgerWriter | None = None` to constructor.

---

#### PHASE 4: Unified Recovery + Bootstrap (E9.5)

##### Step 15: E9.5.1 — CrashRecoveryOrchestrator

**New file:** `poc/k1_poc/ledger/recovery.py`

```python
class CrashRecoveryOrchestrator:
    async def recover(
        self, fsm: ConciergeController, ledger_store: ILedgerStore, session_id: str
    ) -> CrashRecoveryReport:
        # 1. Read all events
        entries = ledger_store.read_all(session_id=session_id)
        if not entries:
            return CrashRecoveryReport(recovered=False)

        # 2. Project task states -> rebuild TaskBridge
        task_states = project_task_states(entries)
        fsm._task_bridge.rebuild_from_projection(task_states)

        # 3. Project cancel state -> rebuild CancellationHandler
        fsm._cancel_handler.rebuild_from_events(entries)

        # 4. Project suspension state -> rebuild SuspensionManager
        fsm._suspension_manager.rebuild_from_events(entries)

        # 5. Project HITL state -> rebuild HILCoordinator
        if fsm._hil_coordinator is not None:
            fsm._hil_coordinator.rebuild_from_events(entries)

        # 6. Project pending results -> rebuild FSMTurnState
        pending = project_pending_results(entries)
        fsm._turn_state.rebuild_from_projection(pending)

        # 7. Project history -> rebuild _history
        history = project_history(entries)
        fsm.rebuild_history_from_projection(history)

        # 8. Rebuild _active_task_ids from task_states
        # 9. Restart timeout watchers
        # 10. Derive FSM state
```

##### Step 16: E9.5.3 — FSM state derivation

Derive `ConciergeState` from latest events:

| Last Event Pattern | Derived State |
|---|---|
| `task.suspended` without `task.resumed` | `CLARIFYING_WORKER` |
| Pending results non-empty + last `response.final` processed | `WEAVING` |
| Active tasks exist | `COMPANIONING` |
| `user_input` without `response.final` | `DISPATCHING` |
| Otherwise | `LISTENING` |

##### Step 17: E9.5.2 — Wire recovery into bootstrap

**File:** bootstrap.py

```python
# After FSM creation + SS binding + ledger wiring:
if cfg.enable_ledger and cfg.ledger_crash_recovery_enabled:
    from poc.k1_poc.ledger.recovery import CrashRecoveryOrchestrator
    orchestrator = CrashRecoveryOrchestrator()
    report = await orchestrator.recover(runtime.fsm, ledger_store, session_id)
    if report.recovered:
        logger.info("Crash recovery: %s", report.summary())
```

**Also wire ledger into protocol components:**

```python
# Pass ledger to protocol components (currently not done):
runtime.hitl_coordinator = HILCoordinator(ledger=ledger_writer, ...)
runtime.fsm._suspension_manager.set_ledger(ledger_writer)
runtime.fsm._cancel_handler.set_ledger(ledger_writer)
runtime.fsm._turn_state.set_ledger(ledger_writer)
```

##### Step 18: E9.2.5 — Restart timeout watchers after recovery

In `CrashRecoveryOrchestrator.recover()`, after rebuilding suspension state:

```python
for task_id, suspension in active_suspensions.items():
    remaining_ms = suspension["timeout_ms"] - elapsed_since_suspension
    if remaining_ms <= 0:
        # Immediately trigger timeout
        await fsm._hitl_timeout_watcher(task_id, 0, hil_subtask)
    else:
        fsm._suspension_manager._timeout_tasks[task_id] = asyncio.create_task(
            fsm._hitl_timeout_watcher(task_id, remaining_ms / 1000, hil_subtask)
        )
```

##### Step 19-22: Integration tests + observability + fallback

| Issue | Test File | What It Tests |
|---|---|---|
| 9.1.4 | `tests/poc/test_m09_e91_cancel_recovery.py` | Cancel -> crash -> restart -> late completion dedup |
| 9.3.4 | `tests/poc/test_m09_e93_hitl_recovery.py` | 2 HITL rounds -> crash -> restart -> counts correct -> L2 defense works |
| 9.5.4 | `tests/poc/test_m09_e95_recovery.py` | Recovery observability events emitted |
| 9.5.5 | `tests/poc/test_m09_e95_recovery.py` | Fallback when ledger unavailable |

---

### File Change Matrix

| File | Epic | Change Type | Lines Est. |
|---|---|---|---|
| task_bridge.py | E9.4 | Add ledger param + write-before-mutate in 7 methods + `rebuild_from_projection()` | +80 |
| cancel_handler.py | E9.1 | Activate ledger writes + `rebuild_from_events()` | +60 |
| suspension_manager.py | E9.2 | Activate ledger writes + consolidate API + `rebuild_from_events()` | +100 |
| hitl_coordinator.py | E9.3 | Activate ledger writes + `rebuild_from_events()` | +70 |
| turn_state.py | E9.4 | Add ledger param + write-before-mutate in enqueue/drain | +40 |
| projections.py | E9.1-3 | Add `project_cancel_state()`, `project_suspension_state()`, `project_hitl_state()` | +120 |
| **recovery.py** (NEW) | E9.5 | `CrashRecoveryOrchestrator` + `CrashRecoveryReport` | +250 |
| controller.py | E9.4-5 | `rebuild_history_from_projection()`, derive FSM state, wire active_task_ids | +60 |
| bootstrap.py | E9.5 | Wire ledger to protocols, call recovery orchestrator | +30 |
| events/registry.py | E9.1 | Register `task.cancel.confirmed` if new event added | +5 |
| fixtures.py | E9.5 | Add `with_ledger_recovery` param, helpers | +60 |
| bus/topics.py | E9.5 | Add recovery observability topics (2) | +10 |

**New test files:**

| File | Tests Est. |
|---|---|
| `tests/poc/test_m09_e91_cancel_recovery.py` | ~15 |
| `tests/poc/test_m09_e92_suspension_recovery.py` | ~15 |
| `tests/poc/test_m09_e93_hitl_recovery.py` | ~20 |
| `tests/poc/test_m09_e94_task_state.py` | ~15 |
| `tests/poc/test_m09_e95_recovery.py` | ~25 |

**Estimated total: ~90 tests, ~885 new/modified lines across 12 files + 1 new file.**

---

### Dependency Graph

```
E9.4.1 (TaskBridge ledger) ──┐
E9.4.2 (task state proj.)  ──┤
                              ├──> E9.1.1 (Cancel ledger) ──> E9.1.2 (cancel proj.) ──> E9.1.3 (cancel rebuild)
                              │
                              ├──> E9.2.1 (Suspension ledger) ──> E9.2.2 (consolidate API) ──> E9.2.3 (susp. proj.) ──> E9.2.4 (susp. rebuild)
                              │
                              └──> E9.3.1 (HITL ledger) ──> E9.3.2 (HITL proj.) ──> E9.3.3 (HITL rebuild)
                                                                                          │
E9.4.3 (history proj.) ──────────────────────────────────────────────────────────────────────┤
E9.4.4 (pending results) ────────────────────────────────────────────────────────────────────┤
                                                                                          │
                                                                                          v
                                                                              E9.5.1 (Recovery Orchestrator)
                                                                                          │
                                                                              E9.5.3 (FSM state derivation)
                                                                                          │
                                                                              E9.5.2 (Bootstrap wiring)
                                                                                          │
                                                                              E9.2.5 (Timeout restart)
                                                                                          │
                                                                     E9.1.4 + E9.3.4 (Integration tests)
                                                                                          │
                                                                     E9.5.4 + E9.5.5 (Observability + Fallback)
```

---

### Key Design Decisions

1. **Write-before-mutate pattern:** Every protocol mutation emits a canonical event to the ledger FIRST. If the ledger write fails, the in-memory mutation is skipped. This makes the ledger the source of truth and in-memory state a cache.

2. **Reuse existing canonical events:** 28 of the 30 existing event classes cover M9's needs. Only `task.cancel.confirmed` may be new (or can be skipped — confirm_cancel can be derived from `task.cancelled` + `task.completed` sequence).

3. **Reuse existing projections:** `project_task_states()`, `project_history()`, `project_pending_results()` already exist and handle the complex event replay logic. M9 adds 3 new projections for cancel/suspension/HITL state.

4. **Sync vs async:** Keep `append_sync()` for protocol mutations (they happen in sync FSM handlers). The writer already has this method from M1.

5. **Suspension API consolidation (Option A):** `store_context_sync()` delegates to a sync path that writes to `_active` + ledger. No need to make FSM handlers async. The `_contexts` dict becomes an alias or is removed.

6. **Fallback safety:** If ledger is corrupt/unavailable, recovery falls back to current behavior (empty state). M9 never makes things worse than pre-M9.
