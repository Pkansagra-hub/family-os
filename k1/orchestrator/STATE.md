# K1 Orchestrator — STATE

---

## 1. `OrchestratorService` mutable fields

| Field | Type | Mutated by | Thread-safe? |
|---|---|---|---|
| `_initialized` | `bool` | `init()` | No (asyncio only) |
| `_running` | `bool` | `init()`, `shutdown()` | No |
| `_planner_port` | `IPlannerPort \| None` | `bind_planner()` | No — must be called before tasks arrive |
| `_pending_plans` | `Dict[str, PendingPlanContext]` | `_dispatch_high()`, `receive_plan()`, reaper | asyncio only |
| `_executed_plans` | `LRU[str]` (max 100) | `receive_plan()` (dedup insert) | asyncio only |
| `_handle_task_waiters` | `Dict[str, asyncio.Future]` | `handle_task()`, `receive_plan()` | asyncio only |
| `_subscriptions` | `List[SubscriptionHandle]` | `_subscribe_events()`, `shutdown()` | asyncio only |

---

## 2. Service lifecycle state machine

```
NOT_INITIALIZED
    │
    └─ init() ─────────────────────────────────────────────────────────────────┐
              (10 steps; raises if any step fails)                              │
              ┌─────────────────────────────────────────────────────────────── ▼
RUNNING  ◄────┘                                                       INIT_FAILED
    │                                                                  (no recovery)
    ├─ handle_task() / handle_interrupt() (normal operation)
    │
    └─ shutdown() ───────────────────────────────────────────────────► STOPPED
              (drain → unsubscribe → cancel tasks)
```

`init()` is idempotent only in that calling it twice raises rather than
corrupting state — it is not designed for repeated calls.

---

## 3. Task lifecycle state machine

A task envelope goes through the following states:

```
ENQUEUED (MailboxPort)
    │
    └─ dequeued by _mailbox_loop()
         │
         ├─ MEDIUM tier ──► EXECUTING (_dispatch_medium → execute_batch)
         │                      │
         │                      ├─ COMPLETED (all capabilities succeeded)
         │                      ├─ FAILED    (capability failed)
         │                      └─ DEGRADED  (partial success)
         │
         └─ HIGH tier ───► PLAN_REQUESTED (_dispatch_high → request_plan)
                               │
                               ├─ REJECTED ──► FAILED (immediate)
                               │
                               └─ DEFERRED (PendingPlanContext stored; future registered)
                                    │
                                    └─ CommittedPlan arrives via bus
                                         │
                                         └─ EXECUTING (receive_plan → DAGExecutor.execute)
                                              │
                                              ├─ COMPLETED
                                              ├─ FAILED
                                              ├─ DEGRADED
                                              └─ CANCELLED (interrupt received mid-execution)
```

---

## 4. DAG execution state machine (per `DAGExecutor.execute()`)

```
RESET (interrupt_flag=False, merged_results={}, _cancelled_steps=set())
    │
    └─ build_waves(steps, dependencies)
         │
         ├─ CycleError / WaveLimitExceeded / StepLimitExceeded ──► FAILED
         │
         └─ Waves built
              │
              └─ For each Wave:
                   │
                   ├─ interrupt_flag=True ──► break → CANCELLED (compensation)
                   │
                   ├─ before_wave guards (ConditionalEdgeEvaluator)
                   │     step SKIP decisions → added to _cancelled_steps
                   │
                   ├─ execute_wave() [asyncio.gather, Semaphore(max_wave_parallelism)]
                   │     For each step in wave:
                   │       ├─ step in _cancelled_steps → emit STEP_CANCELLED, skip
                   │       ├─ ParamResolver.resolve() ($ refs)
                   │       ├─ StepRunner.run() → StepResult
                   │       │     ├─ activity_profile → CapabilityRequest.context_override
                   │       │     ├─ COMPLETED → merged_results[step_id] = result
                   │       │     ├─ FAILED → cancel_dependents(BFS) → _cancelled_steps
                   │       │     ├─ SCHEMA_RETRY → re-run once with __schema_hint
                   │       │     └─ TIMEOUT → asyncio.TimeoutError → FAILED
                   │       └─ after_step guards → RETRY | HARD_STOP | CONTINUE
                   │
                   ├─ after_wave guards:
                   │     ExecutionMonitor → emit progress, optional HIL (30s wait)
                   │     MicroReplanCheckpoint → optional micro_replan (10s wait)
                   │     FailureReplanCheckpoint → optional failure micro_replan (10s wait)
                   │
                   └─ WAL write WAVE_COMPLETE
              │
              └─ All waves complete ──► collect_results()
                   │
                   ├─ all required COMPLETED ──► AggregatedResult(success=True)
                   ├─ some FAILED, some COMPLETED ──► AggregatedResult(success=False, DEGRADED)
                   └─ compensation run if CANCELLED / ABORT
```

---

## 5. `DAGExecutor` mutable state

| Field | Scope | Mutated by | Reset by |
|---|---|---|---|
| `interrupt_flag` | per-execute | `handle_interrupt()` (external), `ExecutionMonitor.after_step()` | `execute()` start |
| `merged_results` | per-execute | `execute_wave()` on COMPLETED step | `execute()` start |
| `_cancelled_steps` | per-execute | `cancel_dependents()`, `ConditionalEdgeEvaluator.before_wave()` | `execute()` start |

All three fields are reset at the top of every `execute()` call. This means there is no
persistent state across DAG executions within a single `DAGExecutor` instance.

---

## 6. `PendingPlanContext` — in-flight plan state

For HIGH-tier tasks, `_pending_plans: Dict[str, PendingPlanContext]` tracks plans
that have been sent to the Planner but whose `CommittedPlan` has not yet arrived.

```python
@dataclass
class PendingPlanContext:
    request_id: str
    trace_id: str
    envelope: TaskEnvelope
    created_at: float          # time.time()
    timeout_ms: int            # from config.plan_request_timeout_ms
```

**Lifecycle:**
- Created in `_dispatch_high()` after `PlanAck.status="ACCEPTED"`.
- Consumed in `receive_plan()` — looked up by `CommittedPlan.request_id`.
- Reaped by `_reap_loop()` every `context_reap_interval_ms=5s` when
  `time.time() - created_at > timeout_ms / 1000`.
  On reap: resolve waiter future with FAILED, emit `ORCH_PLAN_FAILED`, delete entry.
- Maximum entries: `config.max_pending_plans=50`.

---

## 7. `ConcurrencyGuard` state

```python
ConcurrencyGuard:
    _lock: asyncio.Lock    # single-DAG gate (V1)
    _active: bool          # True while lock is held
```

| State | Condition | Behaviour |
|---|---|---|
| `active=False` | Lock free | `acquire()` → True; sets `_active=True` |
| `active=True` | Lock held (DAG running) | `acquire()` → False immediately (non-blocking); caller re-enqueues as DEFERRED |

`release()` must be called in `finally` — the orchestrator always releases even on DAG
failure or exception. An unreleased guard would deadlock all subsequent HIGH-tier tasks.

---

## 8. `CircuitBreaker` state (`degradation.py`)

Three module-level singletons: `cb_planner`, `cb_orchestrator`, `cb_fabric`.

```
CLOSED ──► (failure_threshold=3 failures in failure_window_ms=60s) ──► OPEN
OPEN   ──► (half_open_after_ms=30s) ──► HALF_OPEN
HALF_OPEN ──► (probe succeeds) ──► CLOSED
HALF_OPEN ──► (probe fails) ──► OPEN
```

| State | `is_open()` | `is_half_open()` | `is_closed()` |
|---|---|---|---|
| CLOSED | False | False | True |
| OPEN | True | False | False |
| HALF_OPEN | False | True | False |

`cb_planner` gates `_dispatch_high()`. When OPEN: HIGH-tier tasks immediately degrade
to MEDIUM (if capabilities are provided) or FAILED.

---

## 9. `WorkflowScheduler` timer state

`WorkflowScheduler` maintains a background asyncio task that ticks every
`scheduler_tick_interval_ms=1s`. On each tick it evaluates each `WorkflowSpec.trigger`:

| Trigger type | Evaluation | Fires when |
|---|---|---|
| `CRON` | `croniter.get_current(float) >= last_run_at + interval` | Schedule is due |
| `EVENT` | Subscription handle is live; fires on bus event delivery | Event arrives |
| `MANUAL` | No auto-trigger | Only on explicit `WorkflowRunRequest` |

Per-workflow `last_run_at: float` is tracked in `WorkflowScheduler._last_run`. Not
persisted — lost on restart. CRON workflows may fire once immediately on restart if
the schedule was due while the service was down.

---

## 10. Compensation state (`CompensationRecord`)

When a DAG is cancelled or aborted, `_compensate()` iterates completed steps in
reverse order and attempts to run their `compensation_capability`.

```python
@dataclass
class CompensationRecord:
    dag_id: str
    step_id: str
    compensation_capability: str
    compensation_params: Dict[str, Any]
    record_id: str      # auto uuid4
    status: str         # lifecycle below
    initiated_at: float
    completed_at: Optional[float]
    error_detail: Optional[str]
```

```
PENDING ──► (compensation capability executed) ──► EXECUTED
PENDING ──► (Fabric raises AdapterError) ──► FAILED
FAILED  ──► (max retries exceeded) ──► DEAD_LETTERED
```

`CompensationRecord`s are included in `AggregatedResult.compensations` and written
to the WAL (entry_type="DAG_COMPLETE") for audit. They are not persisted separately.

---

## 11. Crash recovery state reconstruction

On `init()` step 2, `crash_recovery()` reads all WAL entries to reconstruct
in-flight state:

```
list_wal_ids() → [dag_id_1, dag_id_2, ...]
  For each dag_id:
    read_wal(dag_id) → List[WALEntry]
    recover_from_wal(entries) → ResumeInfo{
        plan_id, last_completed_wave, completed_step_ids, status
    }
    if status != DAG_COMPLETE:
        Re-build CommittedPlan from WAL entries
        enqueue(CommittedPlan, priority="INTERACTIVE")
```

**What WAL entries exist per DAG:**
- `PLAN_START` — CommittedPlan serialized as JSON
- `STEP_COMPLETE` — step_id + StepResult
- `WAVE_COMPLETE` — wave_index + wave summary
- `DAG_COMPLETE` — AggregatedResult summary

On resume, `DAGExecutor.recover_from_wal()` skips already-completed steps by
pre-populating `merged_results` from WAL. This means a resumed DAG re-runs from the
wave after the last completed wave, not from scratch.

---

## 12. Concurrency model summary

| Layer | Model | Mechanism |
|---|---|---|
| Service | Single asyncio event loop | `asyncio.create_task` for mailbox + reaper loops |
| Wave execution | Concurrent within a wave | `asyncio.gather()` + `asyncio.Semaphore(max_wave_parallelism=5)` |
| Cross-DAG concurrency | Single DAG at a time (V1) | `ConcurrencyGuard` (asyncio.Lock) |
| Planner round-trip | Async decoupled | Fire-and-forget `request_plan()`, CommittedPlan arrives via bus |
| HIL blocking | Awaited coroutine | `asyncio.wait_for(hil_port.request_override(), timeout=30s)` |
| Micro-replan | Awaited coroutine | `asyncio.wait_for(planner_port.micro_replan(), timeout=10s)` |
| Step execution | Awaited coroutine | `asyncio.wait_for(fabric_port.execute(), timeout=step.timeout_ms)` |
| Circuit breaker | Thread-safe singleton | `threading.Lock` (utility, not hot path) |
| Metrics | Context-local | `contextvars.ContextVar` per-request overhead tracking |
