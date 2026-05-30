# K1 Kernel — STATE

This document covers the lifecycle state machine, all mutable fields, concurrency
model, timeout behavior, and teardown ordering of `KernelService`.

---

## 1. Mutable state fields

All fields are instance-level on `KernelService`. They are set during `startup()` and
cleared implicitly by `shutdown()`.

### 1.1 Tier 1 shared fields (set during S1–S7)

| Field | Type | Set at | Cleared at |
|-------|------|--------|------------|
| `_bus` | `IBus` | S1 | `bus.close()` in shutdown |
| `_async_bus` | `AsyncBusBridge` | S1 | (wrapped; closed via `_bus`) |
| `_router` | `IMailboxRouter` | S1 | `router.close()` in shutdown |
| `_model_hub` | `ModelHub` | S2 | `model_hub.shutdown()` in shutdown |
| `_hil_service` | `HumanInTheLoopService \| None` | S2.5 | `hil_service.shutdown()` in shutdown |
| `_self_model_bundle` | `SelfModelServiceBundle \| None` | S2.6 | `bundle.shutdown()` in shutdown |
| `_bridge` | `SinkBridgeAdapter \| OfflineBridgeAdapter` | S4 | `bridge.disconnect()` in shutdown |
| `_session_routing_reader` | `SessionRoutingStateReader` | pre-S3 | (not explicitly closed) |
| `_prompt_system` | `PromptSystemProdAdapter \| None` | S3 | cleared during cleanup/shutdown |
| `_shared_fabric` | `CapabilityFabric` | S3 | `fabric.shutdown()` in shutdown |
| `_orchestrator` | `OrchestratorService` | S5 | `orchestrator.shutdown()` in shutdown |
| `_orch_storage` | `WorkflowStorageAdapter \| None` | S5 | `orch_storage.close()` in shutdown |
| `_planner` | `PlannerAgent` | S6 | `planner.stop()` + `planner_task.cancel()` in shutdown |
| `_planner_task` | `asyncio.Task` | S7 | cancelled in shutdown |
| `_phase1_pipeline` | `UltraBERTPhase1Pipeline \| StubPhase1Pipeline` | S7 | (not explicitly stopped) |
| `_running` | `bool` | S7 | set `False` in `finally` block of shutdown |
| `_lifecycle_log` | `list[dict]` | every Tier 1 phase completion | retained for diagnostics |

### 1.2 Per-session fields (one entry per active session in `_sessions`)

| Field | Type | Set at | Cleared at |
|-------|------|--------|------------|
| `_sessions` | `dict[str, SessionInstance]` | P6 per session | `del _sessions[session_id]` in `destroy_session` |

`SessionInstance` contains:

| Attribute | Type | Notes |
|-----------|------|-------|
| `session_id` | `str` | — |
| `device_id` | `str \| None` | — |
| `bus` | `IBus` | per-session bus, closed at P8 |
| `router` | `IMailboxRouter` | per-session router, closed at P8 |
| `session_state` | `SessionStateManager` | SSM backed by SQLite |
| `fabric` | `CapabilityFabric` | **never explicitly shut down** — see OPEN_ISSUES §3 |
| `memory_writer` | `MemoryWriterService` | stopped at session teardown step 2 |
| `concierge` | `ConciergeRuntime` | stopped at session teardown step 3 |
| `concierge_task` | `asyncio.Task` | `concierge.consumer_task` |
| `consumer_task` | `asyncio.Task` | same object as `concierge_task` — see OPEN_ISSUES §6 |

---

## 2. Lifecycle state machine

```
           ┌──────────────────────────────────────────┐
           │                                          │
           ▼                                          │
        [UNSTARTED]                                   │
           │                                          │
           │ startup() called                         │
           ▼                                          │
        [STARTING]  ◄── RuntimeError if startup()     │
           │             called again here            │
           │ all S1-S7 phases succeed                 │
           ▼                                          │
        [RUNNING]   ── is_running == True             │
           │                                          │
           │ create_session()                         │
           ├──────────────────────────────────────────►[SESSION_STARTING]
           │                                             │
           │◄────────────────────────────────────────────┘
           │ SessionInstance registered in _sessions
           │
           │ destroy_session()
           ├──────────────────────────────────────────►[SESSION_STOPPING]
           │                                             │
           │◄────────────────────────────────────────────┘
           │ session removed from _sessions
           │
           │ shutdown() called
           ▼
        [STOPPING]
           │ all sessions destroyed first
           │ all Tier 1 components stopped in reverse order
           │ _running = False (always, in finally)
           ▼
        [STOPPED]   ── is_running == False
```

Transitions:


- `[UNSTARTED] → [STARTING] → [RUNNING]` — normal path
- `[RUNNING] → [STOPPING] → [STOPPED]` — normal shutdown
- `[RUNNING] → [STOPPING] → [STOPPED]` — shutdown after partial startup also valid
- `startup()` in `[RUNNING]` → `RuntimeError("already running")`
- `shutdown()` in `[UNSTARTED]` or `[STOPPED]` → idempotent (no-op beyond `_running = False`)

---

## 3. Concurrency model

`KernelService` is **single-threaded asyncio**. All public methods are `async def` and
must be called from the same event loop. There is no internal locking on `_sessions` or
any Tier 1 field — concurrent `create_session` calls from different tasks are not safe.

| Component | Concurrency model |
|-----------|-----------------|
| `IBus` (Rust backend) | thread-safe; internally uses RWLock |
| `IBus` (Python backend) | `LocalBus` uses threading.RWLock; asyncio-safe via `AsyncBusBridge` |
| `IMailboxRouter` | sync, not thread-safe; must be called from event loop thread only |
| `KernelService._sessions` | plain `dict`; no lock; callers must not call `create_session` concurrently |
| `SessionStateManager` | sync with internal `mutation_guard`; SSM mutations are serialized |
| `HumanInTheLoopService` | asyncio-based with internal `asyncio.Lock` |
| `OrchestratorService` | asyncio-based; `bind_planner()` is synchronous and not concurrency-safe if called while tasks process |

`AsyncBusBridge` wraps `LocalBus` and provides `async def publish()/subscribe()` that
delegate to the sync bus via `loop.run_in_executor` or direct call, depending on the
backend.

---

## 4. Timeout behavior

All teardown steps are individually wrapped with a `_TEARDOWN_TIMEOUT = 10.0s` guard.

```python
async def _with_timeout(coro, label: str) -> None:
    try:
        await asyncio.wait_for(coro, timeout=_TEARDOWN_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("shutdown step '%s' timed out after %.1fs", label, _TEARDOWN_TIMEOUT)
    except Exception as exc:
        _errors.append(f"{label}: {exc!r}")
```

Steps that time out log a warning and **continue** — they do not abort the remaining
teardown steps. This means a hung concierge or memory writer will not prevent the bus
from being closed.

`ssm.stop()` is synchronous and has **no timeout applied**. If it blocks, the entire
teardown hangs indefinitely at that point.

---

## 5. Startup failure handling

If any Tier 1 phase raises, cleanup up to that point is attempted in reverse:

| Failed phase | Cleanup attempted |
|-------------|------------------|
| S1 | nothing (first step) |
| S2 | `bus.close()`, `router.close()` |
| S2.5 | `model_hub.shutdown()`, `bus.close()`, `router.close()` |
| S2.6 | `hil_service.shutdown()`, `model_hub.shutdown()`, `bus.close()`, `router.close()` |
| S4 | as S2.6 |
| S3 | `bridge.disconnect()`, as S2.6 |
| S5 | `fabric.shutdown()`, `bridge.disconnect()`, as S2.6 |
| S6 | `orchestrator.shutdown()`, as S5 |
| S7 | `planner.stop()`, `planner_task.cancel()`, as S6 |

`_running` is never set to `True` if startup raises. The kernel is left in `[UNSTARTED]`
state and can be started again (though factory state from partial teardown may differ).

---

## 6. Key invariants

1. `_running == True` iff all 9 Tier 1 components are live and S7 completed.
2. `_sessions[session_id]` exists iff the session's P6 completed without exception.
3. `_planner_task` is the only asyncio background task kernel manages directly; all other
   background activity is owned by individual components.
4. `_shared_fabric.retrieval` must be accessible before `_planner` is constructed (S6
   depends on it).
5. `_orchestrator._planner_port` is `MockPlannerAdapter` between S5 and S6b; after S6b
   it is `PlannerAdapter`, and its `_mailbox` is `self._planner.get_mailbox()`.
6. `_hil_service` is the exact same instance shared across Fabric, Orchestrator, Planner,
   and every per-session Concierge. Mutations to HIL state are globally visible.
7. `bridge_client` (`bridge.get_client()`) is the same object shared across all per-session
   adapters. It is not session-scoped; all sessions write to the same bridge outbox.
8. `_prompt_system` is the verified production prompt adapter for `k1/contracts/prompts`.
   Startup logs its template count. Empty prompt inventory warns by default and only
   fails startup when `enable_activity_profiles_strict=True`; native family tools still
   register when the prompt inventory is absent or empty.
9. Per-session Fabric reuses the shared CapabilityRegistry and the verified prompt
   adapter. Family tool `CapabilityContract.prompt_template` and `activity_profile`
   metadata is therefore visible through session Fabric discovery without being copied
   into business params.

---

## 7. Lifecycle diagnostics

`lifecycle_events()` returns a copy of `_lifecycle_log`. Each event is a plain dict
with `phase`, `component`, and monotonic timestamp `ts`. The log records Tier 1
startup completion markers (`S1_complete` ... `S7_complete`, plus `S6b_complete`
and optional `S8_*`) and shutdown markers (`S7_shutdown_complete` ...
`S1_shutdown_complete`). It is observability-only; production control flow must not
depend on it.
