# K1 Orchestrator — OPEN ISSUES

---

## ISSUE-O01 — Cancellation is cooperative; long tool calls cannot be interrupted

**Severity:** High
**Location:** `k1/orchestrator/orchestration/dag_executor.py`, `step_runner.py`

> **CORRECTION (May 2026):** Original description said `asyncio.wait_for(fabric_port.execute(), timeout=step.timeout_ms)`.
> The actual implementation in `StepRunner._execute_with_retry()` calls
> `await self._fabric_port.execute(current_request)` with **no `asyncio.wait_for()` wrapper**.
> The 30s default is `config.default_step_timeout_ms = 30_000` in `config.py:77`, but it
> is passed to Fabric as a parameter in the request, not enforced at the orchestrator level.
> So the orchestrator has **zero timeout enforcement** on step execution — worse than described.

**Current behavior:**
`interrupt_flag` is checked at wave boundaries and by `ExecutionMonitor.after_step()`.
A step executing via `self._fabric_port.execute(request)` cannot be interrupted until
the step completes. If Fabric does not honour the timeout parameter, the step blocks
indefinitely. A cancel request must wait for the current step to complete naturally.

**Failure mode:** User requests cancel via Concierge. FSM transitions to CANCELLING.
Concierge's user-visible state shows "cancelling" indefinitely while the current
step blocks. For tools that call external APIs or run local subprocess tools, the
underlying work is not terminated.

**Fix:** Add `asyncio.wait_for(self._fabric_port.execute(request), timeout=step_timeout_s)`
in `StepRunner._execute_with_retry()`. Propagate a `CancellationToken` into
`IFabricGatewayPort.execute()` as a second step. In the short term: add the
`asyncio.wait_for` wrapper and ensure `default_step_timeout_ms` is enforced there.

---

## ISSUE-O02 — `ConcurrencyGuard` non-blocking acquire re-enqueues silently; no depth limit

**Severity:** Medium
**Location:** `k1/orchestrator/orchestration/guards/concurrency_guard.py`, `orchestrator_service.py:receive_plan()`

**Current behavior:**
When `ConcurrencyGuard.acquire()` returns `False` (DAG already running), the
`CommittedPlan` is re-enqueued via `mailbox.enqueue(plan, "INTERACTIVE")`. This re-enqueue
can succeed many times. A burst of parallel HIGH-tier requests (e.g. 10 Concierge tasks
dispatched in quick succession) results in 10 `CommittedPlan` messages accumulating in
the mailbox. There is no maximum depth for re-queued plans, and the reaper only removes
stale `PendingPlanContext` entries (not already-queued `CommittedPlan` objects).

**Failure mode:** Mailbox fills with 100 deferred plans (`mailbox_capacity=100`). New
`TaskEnvelope` messages are rejected with `MailboxFullError`. The session appears frozen
from the user's perspective — no new tasks accepted.

**Fix:** Track re-enqueue count per `CommittedPlan` (add `retry_count` field or use a
side dict). After `max_deferred_plan_retries=5`, fail the plan with FAILED and resolve
its waiter. Also add a `deferred_plan_depth` gauge to `OrchestratorMetrics`.

---

## ISSUE-O03 — `WorkflowScheduler._last_run` is not persisted; CRON workflows fire on restart

**Severity:** Medium
**Location:** `k1/orchestrator/workflows/workflow_scheduler.py`

> **NOTE (May 2026):** Code audit could not confirm `_last_run` attribute exists by
> that exact name. If the attribute was renamed or the scheduler was refactored, the
> file:line citation should be reverified. The design gap (in-memory only, no SQLite
> persistence) is confirmed regardless of the attribute name.

**Current behavior:**
`_last_run: Dict[str, float]` (or equivalent) is an in-memory dict reset to empty on
every service start. On restart, all active CRON workflows whose schedule was due during
downtime will fire immediately on the first scheduler tick (within 1s of startup).

**Failure mode:** A daily CRON workflow (e.g. `0 6 * * *`) runs at 06:00. If the
service restarts at 06:02, the workflow fires again on startup. Depending on the
workflow's idempotency, this can cause duplicate bookings, emails, or reminders.

**Fix:** Persist `last_run_at` to the workflow SQLite database alongside `WorkflowSpec`.
Add a `WorkflowRunRecord.last_triggered_at: Optional[float]` field to
`IWorkflowStoragePort`. On startup, load from DB rather than defaulting to `0.0`.

---

## ISSUE-O04 — `save_workflow()` WAL plan-lookup deferred to M4

**Severity:** Medium
**Location:** `k1/orchestrator/orchestration/orchestrator_service.py` line 2139, `workflow_engine.py` line 27

**Current behavior:**
`save_workflow()` saves the `WorkflowSpec` to the SQLite registry. The V1 design also
intended to attach the `CommittedPlan` from the most recent successful execution (so
the workflow can be re-executed without re-planning). That lookup is deferred to M4
with a `TODO` comment.

**Failure mode:** Saved workflows always re-compile (`WorkflowCompiler.compile()`) on
every execution, which re-validates all capabilities and re-resolves `DynamicExpr`
references. If any capability has been removed from Fabric since the workflow was saved,
the compile fails and the workflow cannot run — even if it ran successfully last time.

**Fix:** Implement WAL plan lookup: on `save_workflow()`, scan the WAL for the most
recent `PLAN_START` entry matching `source_plan_id`, serialize that `CommittedPlan` into
the `WorkflowSpec.metadata["committed_plan"]` field. On `compile()`, short-circuit to
the stored plan if it is fresh (age < `config.workflow_plan_max_age_ms`).

---

## ISSUE-O05 — `ConstraintResolver.find_alternatives()` scoring is schema-overlap heuristic only

**Severity:** Medium
**Location:** `k1/orchestrator/orchestration/constraint_resolver.py:find_alternatives()`

**Current behavior:**
Alternative capability scoring uses a weighted sum:


- Schema overlap score (W=0.6): counts shared param keys
- Safety band score (W=0.2): whether alternative matches `step.safety_band_min`
- Name similarity score (W=0.2): string edit distance

No semantic understanding of capability intent. A step requiring `calendar.book_event`
may receive `calendar.list_events` as an alternative (both are `calendar.*`, high name
similarity) even though they are semantically incompatible.

**Failure mode:** ConstraintResolver selects a wrong alternative capability; the HIL
fallback is not triggered because the score is above the 0.3 threshold. The wrong
capability executes and produces an incorrect result that Back silently accepts.

**Fix:** Add a LLM-based capability intent matching call (via `ILLMPort` or an inline
embedding comparison) as a post-filter on the top-3 scored candidates. Alternatively,
require capabilities to declare an `intent_tags: List[str]` field in `RegistryEntry`;
alternatives must share at least one intent tag.

---

## ISSUE-O06 — `ExecutionMonitor` HIL override fires on every post-wave with >3 steps

**Severity:** Low
**Location:** `k1/orchestrator/orchestration/guards/execution_monitor.py:after_wave()`

**Current behavior:**
The HIL override prompt is triggered whenever a wave has `> 3 steps OR duration > 5s`.
For HIGH-tier tasks with large plans (e.g. 5-step plan = two waves of 3+2 steps), the
HIL fires after every wave, asking the user "Wave N complete: proceed?". This can mean
2–3 user confirmations for a single task.

**Failure mode:** Not a correctness issue, but severe UX degradation. A user who asks
the AI to "plan my vacation" receives 3 interruptions mid-execution asking them to
confirm each wave. The `timed_out=True → CONTINUE` fallback means it silently continues
after 30s, but only if the user doesn't respond — users who do see and respond to the
prompt are forced to interact with internal system mechanics.

**Fix:** Replace the `> 3 steps OR > 5s` condition with an explicit `requires_hitl: bool`
flag on `CommittedPlan` (set by Planner for high-risk plans). Default to no HIL. Or
gate on `control.privacy_band` == RESTRICTED — require confirmation only for sensitive
operations (financial, health, identity).

---

## ISSUE-O07 — Crash recovery re-runs already-compensated steps

**Severity:** Medium
**Location:** `k1/orchestrator/orchestration/dag_executor.py:recover_from_wal()`

**Current behavior:**
`recover_from_wal()` determines resume state from WAL entries. If a DAG was cancelled
mid-execution, `_compensate()` runs and writes `DAG_COMPLETE` to the WAL. However, if
the process crashes during compensation (after some but not all steps are compensated),
the WAL shows `DAG_COMPLETE` is absent. On recovery, the system sees an incomplete DAG
and re-enqueues the `CommittedPlan` for a fresh execution from the last completed wave.
It does NOT know that some steps were already partially compensated.

**Failure mode:** Compensation is partial (3 of 5 steps compensated before crash). On
recovery, the DAG re-executes from wave 2 (say), then is cancelled again, then
re-compensates steps 4 and 5 — which were already compensated. If compensation is
idempotent (e.g. delete a resource), the second compensation is a no-op. If it is not
(e.g. refund a charge), the user is refunded twice.

**Fix:** Write a `COMPENSATION_STARTED` and `COMPENSATION_COMPLETE` WAL entry per step.
`recover_from_wal()` should detect partial compensation and either skip already-compensated
steps or complete the compensation chain rather than re-executing the plan.

---

## ISSUE-O08 — `MicroReplanCheckpoint` and `FailureReplanCheckpoint` share `max_micro_replans=1` per DAG but track separately

**Severity:** Low
**Location:** `k1/orchestrator/orchestration/guards/micro_replan.py`, `failure_replan.py`

> **CORRECTION (May 2026):** Original description said `_replan_used: bool`.
> **Actual field name is `_replan_done: bool`** in both checkpoint classes.
> The fix description below uses the correct name.

**Current behavior:**
Each guard tracks `_replan_done: bool` independently. `MicroReplanCheckpoint` sets its
own flag; `FailureReplanCheckpoint` sets its own. A DAG can receive one micro-replan
from each guard: total of 2 replans per DAG, exceeding the documented `max_micro_replans=1`.

**Failure mode:** A DAG with both discoveries and failures triggers two replans. The
second replan may produce a `CommittedPlan` that is structurally different from the
first. At minimum, the `max_micro_replans=1` config invariant (ORCH-13) is silently violated.

**Fix:** Move the `_replan_done` flag to `ProcessingContext` so it is shared across all
guards. Both checkpoints check `ctx.micro_replan_done` before calling `micro_replan()`
and set it after. This enforces the 1-per-DAG limit globally.

---

## ISSUE-O09 — `cb_planner` circuit breaker uses module-level singletons (not per-session)

**Severity:** Medium
**Location:** `k1/orchestrator/degradation.py`

**Current behavior:**
`cb_planner`, `cb_orchestrator`, `cb_fabric` are module-level singletons instantiated
at import time. If the orchestrator is instantiated multiple times (e.g. multiple test
sessions, or future multi-session orchestrators), all instances share the same circuit
breakers. A flaky planner in session A trips `cb_planner` and causes session B's HIGH
tier tasks to immediately degrade — even if the planner is healthy for session B.

**Failure mode:** In multi-session scenarios (or concurrent test runs), circuit breaker
state bleeds across sessions. Tests that inject failures in one orchestrator instance
leave `cb_planner` tripped, causing subsequent tests to fail with degradation even
without injecting any failures.

**Fix:** Move circuit breakers into `OrchestratorService.__init__` as instance-level
objects (passed to components via factory). `degradation.py` should export
`CircuitBreaker` class only; callers instantiate. Remove module-level singletons.

---

## ISSUE-O10 — `ProactiveGapDetector` has no backoff on repeated gap detection

**Severity:** Low
**Location:** `k1/orchestrator/workflows/gap_detector.py`

**Current behavior:**
`ProactiveGapDetector` subscribes to `k1.fabric.contract.updated.v1`. On every
CONTRACT_UPDATED event, it scans ALL active workflows for capability gaps and emits
`ProactiveGap` records. If a Fabric provider is cycling through health states (e.g.
a flaky MCP server), repeated health-change events may cause `CONTRACT_UPDATED` to fire
every few seconds. With 50 active workflows, this means 50 capability checks per event.

**Failure mode:** Under a flaky provider, `ProactiveGapDetector` runs O(50) registry
queries every few seconds, saturating `IFabricGatewayPort.query_registry()` and
introducing latency into legitimate step executions (all share the same Fabric adapter).

**Fix:** Add a debounce/cooldown: `_last_scan_at: Dict[str, float]` per workflow_id.
Skip gap re-check if `time.time() - _last_scan_at[wf_id] < config.gap_scan_cooldown_ms`
(suggested 60s). Also cap total concurrent registry queries via a semaphore.
