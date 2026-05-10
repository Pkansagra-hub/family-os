# K1 Planner — STATE

---

## 1. `PlannerAgent` mutable fields

| Field | Type | Mutated by | Read by |
|---|---|---|---|
| `_cancel_set` | `Set[str]` | `_on_plan_cancel()` (add), `_run_loop()` (discard) | `cancel_check` closure, `_run_loop()` pre-check |
| `_running` | `bool` | `start()` → True; `stop()` → False | `_run_loop()` while guard |
| `_subscriptions` | `List[SubscriptionHandle]` | `start()` appends, `stop()` clears | `stop()` for unsubscribe |
| `_in_flight_request_id` | `Optional[str]` | Set before lock acquire; cleared in `finally` | `stop()` to issue cancel |

---

## 2. Service lifecycle state machine

```
NOT_STARTED
    │
    └─ start() ─────────────────────────────────────► RUNNING
              subscribes 2 topics; enters _run_loop()    │
              (blocks indefinitely on mailbox.dequeue())  │
                                                          │
                                                stop() ───┘
                                                    │
                                                    ▼
                                                 STOPPING
                                                    │ drains mailbox
                                                    │ cancels in-flight
                                                    │ unsubscribes
                                                    ▼
                                                  STOPPED
```

`start()` is a long-running coroutine — caller must `asyncio.create_task(agent.start())`.
`stop()` is `async def` — waits up to `shutdown_grace_period_ms=5,000ms` for the lock.

---

## 3. `PlanStateMachine` mutable state

**Single mutable field:** `_current_state: PlanState`

### Full-plan state transition table

Valid transitions are enforced by `TRANSITION_TABLE`. `transition(trigger)` raises
`IllegalStateTransitionError` on invalid transitions.

```
IDLE          ──[start_sketch]──────────► SKETCHING
SKETCHING     ──[sketch_done]─────────── ► EXPANDING
SKETCHING     ──[plan_failed]──────────► FAILED
SKETCHING     ──[plan_cancelled]────────► CANCELLED
EXPANDING     ──[expand_done]──────────► VALIDATING
EXPANDING     ──[plan_failed]──────────► FAILED
EXPANDING     ──[plan_cancelled]────────► CANCELLED
VALIDATING    ──[validate_approved]─────► COMMITTING
VALIDATING    ──[validate_revise]───────► EXPANDING
VALIDATING    ──[plan_failed]──────────► FAILED
VALIDATING    ──[plan_cancelled]────────► CANCELLED
COMMITTING    ──[commit_done]──────────► COMPLETED
COMMITTING    ──[plan_failed]──────────► FAILED
```

### Micro-replan state transition table

```
IDLE         ──[micro_start_sketch]──► MICRO_SKETCH
MICRO_SKETCH ──[micro_sketch_done]──► MICRO_EXPAND
MICRO_SKETCH ──[plan_failed]────────► FAILED
MICRO_SKETCH ──[plan_cancelled]─────► CANCELLED
MICRO_EXPAND ──[micro_expand_done]──► MICRO_VALIDATE
MICRO_EXPAND ──[plan_failed]────────► FAILED
MICRO_EXPAND ──[plan_cancelled]─────► CANCELLED
MICRO_VALIDATE ──[validate_approved]► COMMITTING
MICRO_VALIDATE ──[plan_failed]──────► FAILED
MICRO_VALIDATE ──[plan_cancelled]───► CANCELLED
```

`force_failed(trigger)` — bypasses table; sets `_current_state = FAILED` unconditionally.
`force_cancelled(trigger)` — bypasses table; sets `_current_state = CANCELLED` unconditionally.
`reset()` — sets `_current_state = IDLE`.

**Terminal states:** `COMPLETED`, `FAILED`, `CANCELLED` — no further transitions allowed.

---

## 4. `PipelineController` per-plan mutable state

All fields are reset by `reset()` at the start of every `execute()` or `micro_replan()` call.

| Field | Type | Reset to | Mutated by | Semantics |
|---|---|---|---|---|
| `_stage_token_usage` | `Dict[str, int]` | `{}` | After each LLM call | Stage → tokens used |
| `_stage_cost` | `Dict[str, float]` | `{}` | After each LLM call | Stage → cost (if model provides it) |
| `_stage_latency` | `Dict[str, int]` | `{}` | After each LLM call | Stage → latency ms |
| `_total_plan_tokens` | `int` | `0` | After each LLM call (accumulate) | Total across all stages |
| `_tool_call_count` | `int` | `0` (via `tool_router.reset()`) | After each tool call | PLAN-05 budget counter |
| `_hil_round_count` | `int` | `0` | After each HIL round | PLAN-10 budget counter |
| `_current_request` | `Any` | `None` | `execute()` set; `reset()` clear | Current `PlanRequest` |
| `_plan_start_time` | `Optional[float]` | `None` | `execute()` sets to `time.time()` | For timeout computation |
| `_revise_count` | `int` | `0` | On each `verdict.status=REVISE` or `REJECT` | Max-1 revise loop |
| `_active_cancel_check` | `Callable[[], bool]` | `lambda: False` | Set in `execute()` from agent | Per-plan cancel closure |
| `_fsm` | `PlanStateMachine` | FSM reset to IDLE | `execute()` via transitions | Plan state machine |

`ToolCallRouter._tool_call_count` is shared — `PipelineController.reset()` calls
`tool_router.reset()` which zeroes it.

---

## 5. Cancel checkpoint state

5 cooperative cancel checkpoints in `PipelineController`. Each calls
`_check_cancel()` which evaluates the closure injected from `PlannerAgent`:
`cancel_check = lambda: request.request_id in agent._cancel_set`.

```
Checkpoint 1: PlannerAgent._run_loop() — before acquiring _plan_lock
              (pre-dequeue check)
Checkpoint 2: PipelineController.execute() — after sketch_result returned
Checkpoint 3: PipelineController.execute() — after expand_result returned
Checkpoint 4: PipelineController.execute() — after verdict returned (before COMMIT)
Checkpoint 5: PipelineController.execute() — inside each stage after LLM call
              (SketchService, ExpandService, ValidateService each call ctx.cancel_check())
```

When `cancel_check()` returns `True`:
- `_check_cancel()` calls `force_cancelled()` on FSM
- Emits `k1.planner.plan.cancelled.v1`
- Raises `PlanCancelledError`

`PlanCancelledError` is NOT caught by the `plan.failed.v1` emitter — it has its own
cancel path. The `_plan_failed_emitted` flag prevents double-emit.

---

## 6. `MailboxAdapter` mutable state

| Field | Type | Mutated by | Notes |
|---|---|---|---|
| `_queue` | `asyncio.Queue[PlanRequest]` | `enqueue()` puts; `dequeue()` gets; `drain()` drains | `maxsize=max_depth` |
| `_cancel_set` | `Set[str]` | `send_cancel()` adds | Read by `is_cancel_requested()` |
| `_shutdown` | `bool` | `begin_shutdown()` | Blocks `enqueue()` and `micro_replan()` after shutdown |
| `_pipeline_controller` | `Optional[object]` | `set_pipeline_controller()` post-construction | Used for direct `micro_replan()` dispatch |

`MailboxAdapter.micro_replan()` calls `_pipeline_controller.micro_replan(request, cancel_check)` directly — not through the queue. It uses its own `_plan_lock` to serialize with the main dequeue loop.

---

## 7. `ToolCallRouter` mutable state

**Single mutable field:** `_tool_call_count: int`

- Incremented on every `call()` invocation (not on retries).
- `get_schema()` does NOT increment.
- `reset()` → `_tool_call_count = 0`.
- Exceeding `config.max_tool_calls_per_plan` raises `BudgetExhaustedError`.

---

## 8. Plan request lifecycle

```
1. Bus event: k1.planner.plan.request.v1
       ↓
2. PlannerAgent._on_plan_request(payload) [sync]
   → deserialize PlanRequest
   → if mailbox full: emit plan.failed.v1 immediately
   → loop.create_task(_safe_enqueue(request))
       ↓
3. MailboxAdapter._queue.put_nowait(request)
       ↓
4. PlannerAgent._run_loop() dequeues:
   → cancel pre-check (checkpoint 1)
   → _in_flight_request_id = request_id
   → async with _plan_lock:
       ↓
5. PipelineController.execute(request, cancel_check)
   → [SKETCH → EXPAND → VALIDATE → COMMIT]
       ↓
6. CommitService emits k1.planner.plan.ready.v1
   returns CommittedPlan
       ↓
7. _run_loop() finally: _in_flight_request_id = None; _cancel_set.discard(request_id)
```

---

## 9. `PlanStateMachine` FSM transition callback

On every `transition(trigger)` call, if `_on_transition` callback is set:
```python
self._on_transition(old_state, new_state, trigger)
```

`PipelineController.__init__` registers this as:
```python
_fsm = PlanStateMachine(on_transition=self._on_fsm_transition)
```

`PipelineController._on_fsm_transition(old, new, trigger)`:
- Emits `DeltaPayload(delta_type="FSM_TRANSITION", section="pipeline", data={old, new, trigger, trace_id})`
- Tracks stage-start timestamps

This callback fires synchronously inside `transition()` — it must not block.

---

## 10. Concurrency model summary

| Layer | Model | Mechanism |
|---|---|---|
| Planner actor loop | Single asyncio task | `while _running: request = await mailbox.dequeue()` |
| Plan exclusion | Single plan at a time (V1) | `asyncio.Lock` (`_plan_lock`) in agent + mailbox |
| Micro-replan | Synchronized with main loop | `MailboxAdapter._plan_lock` — acquires same lock |
| Cancel signal delivery | Concurrent bus callback | Set add is GIL-protected; closure read is cooperative |
| FSM transitions | Synchronous | No async — state mutation in-event-loop only |
| HIL round-trips | Awaited coroutine | `await hil_port.request_clarification(timeout=60s)` / `request_approval(timeout=120s)` |
| Arbiter LLM call | Awaited coroutine | `await asyncio.wait_for(llm_port.execute(request), timeout=3s)` |
| Tool calls | Sequential | Each tool dispatched and awaited before next |
| Delta/event emit | Fire-and-forget sync | `IDeltaEmitPort.emit()`, `IEventPort.emit()` must not block |

Planner does not use `asyncio.gather`, thread pools, or any form of parallelism within the pipeline.
