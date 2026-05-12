# K1 Kernel — OPEN ISSUES

Issues discovered during end-to-end inventory of `KernelService`. Each entry
identifies the defect, the exact code location, the failure mode, and a suggested fix.

---

## Issue 1 — `_FirstSessionSSMShim` breaks multi-session ModelHub state

**Severity:** High — silent correctness bug in multi-session mode
**File:** `k1/kernel/service.py` (S2, `_FirstSessionSSMShim`)

### What the code does

At S2, `ModelHub` is constructed with a `state_read_port` backed by
`_FirstSessionSSMShim`. This shim looks up `persona` and `control` sections by
returning `sessions[first_key].get_section(name)` — always session 0, regardless of
which session originated the request.

### Failure mode

With two or more sessions active, ModelHub routing decisions (persona, control sections)
are always driven by the first session's state. A request from session B will be
processed with session A's persona and control settings.

### Root cause

`ModelHubFactory.from_config` requires a `state_read_port` at construction time, but
the per-request session context is not threaded into the ModelHub call path. The shim
was introduced as a bootstrap workaround and never replaced.

### Suggested fix

Thread `session_id` through the `ModelHub.execute()` call or its payload, and resolve
the `state_read_port` lookup per-request using a request-scoped session reader rather
than a shim over the sessions dict.

---

## Issue 2 — Planner `state_port` initialized with `session_id="__shared__"`

**Severity:** Medium — may silently return `None` for all state lookups during planning
**File:** `k1/kernel/service.py` (S6, `PlannerFactory.create_production`)

### What the code does

`PlannerStateAdapter(reader=session_routing_reader, session_id="__shared__")` is passed
to the planner at construction. The `session_routing_reader` resolves by looking up
`_sessions["__shared__"]` — a key that never exists.

### Failure mode

Any Planner code path that calls `state_port.get_section(name)` (or equivalent) will
receive `None` because the routing reader finds no session for `"__shared__"`. Planning
decisions that depend on state context silently degrade.

### Root cause

The Planner is a shared component operating outside any single session. The
`session_id="__shared__"` was intended as a sentinel, but the routing reader was not
extended to handle it.

### Suggested fix

Either: (a) pass a `NullSessionStateReaderAdapter` to the planner explicitly, so the
`None` returns are intentional and documented; or (b) thread the requesting session's
`session_id` into each planning invocation and resolve state at call time.

---

## Issue 3 — Per-session Fabric is never torn down

**Severity:** Medium — resource leak on session destruction
**File:** `k1/kernel/service.py` (`destroy_session` / `_teardown_session`)

### What the code does

`destroy_session` stops `memory_writer`, `concierge`, `ssm`, and closes the
per-session bus and router. It does **not** call `session.fabric.shutdown()`.

### Failure mode

If `CapabilityFabric` holds background tasks, open database handles, or active module
loaders (MCP/WASM), they will continue running after the session is destroyed. Over
many sessions, this accumulates leaked resources.

### Suggested fix

Add `await session.fabric.shutdown()` after `concierge.stop()` and before `ssm.stop()`
in the session teardown sequence. Wrap with the standard `_with_timeout` guard.

---

## Issue 4 — `max_sessions` declared but never enforced

**Severity:** Low — configuration field has no effect
**File:** `k1/kernel/config.py`, `k1/kernel/service.py` (`create_session`)

### What the code does

`KernelConfig.max_sessions: int = 100` exists, but `create_session()` has no check
against `len(self._sessions)`.

### Failure mode

Under load or in tests that create many sessions without destroying them, memory and
SQLite handles will grow unbounded without any backpressure.

### Suggested fix

Add a guard at the start of `create_session()`:

```python
if len(self._sessions) >= self._config.max_sessions:
    raise RuntimeError(
        f"session limit reached ({self._config.max_sessions})"
    )
```

---

## Issue 5 — MockPlannerAdapter window between S5 and S6b

**Severity:** Low — only relevant in race conditions during startup
**File:** `k1/kernel/service.py` (S5, S6b)

### What the code does

`OrchestratorFactory.create_production` is called at S5 with `planner=MockPlannerAdapter()`.
The real planner is not wired in until S6b. Both S5 and S6b are in the same `startup()`
coroutine on the same event loop, so no real concurrency risk during startup itself.

### Failure mode

If `startup()` is exposed to callers before it completes (e.g., via a reference leak or
test hook that fires after S5 yields), any task routed to the orchestrator will hit the
mock planner. Mock responses may be silently accepted by the workflow engine.

### Current mitigation

S7's post-wire verification asserts
`not isinstance(self._orchestrator._planner_port, MockPlannerAdapter)` before setting
`_running = True`, so this cannot persist past a successful startup.

### Suggested fix

No change required for production use. For test isolation, avoid injecting tasks into
orchestrator between the `OrchestratorFactory.create_production` call and the
`bind_planner` call.

---

## Issue 6 — `concierge_task` and `consumer_task` are the same object

**Severity:** Low — redundant field, not a functional bug
**File:** `k1/kernel/service.py` (P6, `SessionInstance` constructor)

### What the code does

`SessionInstance` is constructed with:

```python
concierge_task=concierge.consumer_task,
consumer_task=concierge.consumer_task,
```

Both fields reference the same `asyncio.Task`.

### Impact

No functional impact. Code that cancels or awaits either field operates on the same
task, so the duplication is harmless. However, it suggests the original design intended
two separate tasks (concierge start task + mailbox consumer task) that were later merged.

### Suggested fix

Remove one of the two fields, or document which is the canonical reference. If a
separate `concierge.start()` coroutine task is intended in future, the second field
should be reserved for it.

---

## Issue 7 — Dead `KernelConfig` flags (`enable_orchestrator`, `enable_experience`, etc.)

**Severity:** Low — configuration surface confusion
**File:** `k1/kernel/config.py`, `k1/kernel/service.py`

### What the code does

The following fields exist on `KernelConfig` but are **never read** in `_startup_tier1`
or `_create_session_tier2`:

- `enable_orchestrator`
- `enable_experience`
- `enable_delta`
- `enable_hitl`

The gated fields that **are** read: `enable_hil_service`, `enable_self_model`.

### Impact

Callers setting these flags expect them to gate startup behavior. They have no effect.
`enable_hitl` is especially confusing — it appears to be a synonym for `enable_hil_service`
but is never checked.

### Suggested fix

Either wire these flags into the startup sequence or remove them from `KernelConfig`
with a comment explaining the replacement fields. At minimum, add a deprecation warning
in the `KernelConfig.__post_init__` or `__init__` if they are set.

---

## Issue 8 — `IFabricPort`, `IOrchestratorPort`, `IPlannerPort` are scaffolding, not enforced

**Severity:** Low — type safety gap
**File:** `k1/kernel/ports/`

### What the code does

`k1/kernel/ports/` defines port protocols for the three largest dependencies. These are
never used as type annotations in `KernelService`. Kernel calls `FabricFactory`,
`OrchestratorFactory`, and `PlannerFactory` directly and performs `hasattr` structural
checks rather than Protocol `isinstance` checks.

### Impact

Any change to the factory return type or the underlying service class that removes
`execute`, `process`, or `start` will only be caught at runtime via the structural
`hasattr` check, not at import/type-check time.

### Suggested fix

Either delete the scaffolding port files (they mislead readers into thinking kernel
uses them), or add type annotations to `_shared_fabric`, `_orchestrator`, and `_planner`
fields using the port protocols and add `isinstance(..., IFabricPort)` checks at S3/S5/S6.

---

## Issue 9 — `ssm.stop()` has no timeout in session teardown

**Severity:** Low — potential indefinite hang
**File:** `k1/kernel/service.py` (`_teardown_session`)

### What the code does

All other session teardown steps are wrapped with the `_TEARDOWN_TIMEOUT = 10.0s` guard.
`ssm.stop()` is called synchronously with no timeout.

### Failure mode

If `ssm.stop()` blocks (e.g., SQLite WAL checkpoint takes too long on a large database),
the entire session teardown — and by extension the entire kernel shutdown — hangs
indefinitely at that point.

### Suggested fix

Wrap `ssm.stop()` in `asyncio.wait_for(asyncio.to_thread(ssm.stop), timeout=10.0)` or
convert `ssm.stop()` to `async def` and apply the standard timeout guard.

---

## Issue 10 — `SessionStateManager.stop()` blocks event loop thread during teardown

**Severity:** Low — potential latency spike during teardown
**File:** `k1/kernel/service.py` (`_teardown_session`), `k1/sessionstate/manager.py`

### What the code does

`ssm.stop()` is synchronous and performs a SQLite WAL checkpoint on the calling thread.
Even if called from within an async context (which it is, in `_teardown_session`),
it will block the event loop thread for the duration of the checkpoint.

### Failure mode

During session teardown with many pending writes, the SQLite checkpoint can take
several seconds. All other coroutines on the event loop are blocked during this time.
In a multi-session kernel, all other active sessions are paused while one session's
SSM flushes to disk.

### Suggested fix

Replace the synchronous call with:
```python
await asyncio.wait_for(asyncio.to_thread(ssm.stop), timeout=10.0)
```
This runs the checkpoint in a thread pool without blocking the event loop.

---

## Issue 11 — `experience_layer`, `delta_aggregator`, `delta_applicator` have no teardown in `_teardown_session`

**Severity:** Low — resource leak on session destroy
**File:** `k1/kernel/service.py` (`_teardown_session`), `k1/kernel/contracts/session_instance.py`

### What the code does

`SessionInstance` fields `experience_layer`, `delta_aggregator`, and `delta_applicator`
are set during session construction but have zero lines in `_teardown_session` that
stop, close, or cancel them. If these objects hold background tasks, open handles, or
subscriptions, they are silently abandoned when the session is destroyed.

### Failure mode

Over many create/destroy session cycles (e.g., in tests or long-running kernels),
abandoned tasks accumulate. Background tasks with references to closed SQLite handles
may raise `sqlite3.ProgrammingError` asynchronously after teardown.

### Suggested fix

Add `await session.experience_layer.stop()` (or equivalent) in `_teardown_session`,
wrapped with the standard `_with_timeout` guard.

---

## Issue 12 — `dead_letter_consumer` on `SessionInstance` not explicitly stopped

**Severity:** Low — resource management
**File:** `k1/kernel/service.py` (`_teardown_session`), `k1/kernel/contracts/session_instance.py`

### What the code does

`SessionInstance.dead_letter_consumer` is a background consumer task. The teardown
sequence cancels `concierge_task` and `consumer_task` but does not explicitly
cancel or await `dead_letter_consumer`.

### Failure mode

`dead_letter_consumer` may continue running after session teardown, attempting to
read from a closed bus or cancelled mailbox. Produces `asyncio.CancelledError` noise
or silently leaks the task.

### Suggested fix

Add `session.dead_letter_consumer.cancel()` and `await asyncio.gather(session.dead_letter_consumer, return_exceptions=True)` in the teardown sequence.
