# K1 Planner — OPEN ISSUES

---

## ISSUE-P01 — ~~Kernel Phase 5 wiring is a TODO; production always uses `MockPlannerAdapter`~~ ✅ FIXED

**Severity:** Critical → **CLOSED**
**Location:** `k1/kernel/service.py:1291-1341`

> **UPDATE (May 2026):** Fully implemented. `kernel/service.py` startup sequence confirms:
> - S5: `OrchestratorFactory.create_production(planner=MockPlannerAdapter())` — mock as placeholder only
> - S6a: `PlannerFactory.create_production(...)` — real planner agent created with all 7 ports
> - S6b: `asyncio.create_task(planner_agent.start())` — planner started
> - S6c: `planner_adapter = PlannerAdapter(mailbox, circuit_breaker)` — real adapter built
> - S6d: `orchestrator.bind_planner(planner_adapter)` — hot-swap to real adapter
> - S7: `_verify_planner_orchestrator_crosswire()` asserts `not isinstance(orchestrator._planner_port, MockPlannerAdapter)` before `_running = True`
>
> All 6 steps are implemented. The mock is replaced before any request can be served.

> **AUDIT NOTE (May 2026 — M4 Epic 4.1):** Three minor discrepancies between the UPDATE
> text above and the actual `service.py` implementation — admin-only, no code changes
> required:
>
> 1. **Phase label inversion**: UPDATE labels the task-start step "S6b", but in code it
>    is the **S7** block (`── S7: Start Planner Background Task`, `service.py:1412`).
>    Code's S6b is the cross-wire (lines 1400-1410). The plan/UPDATE labels are inverted
>    relative to the code's section banners.
> 2. **Port count**: UPDATE says "all 7 ports"; `PlannerFactory.create_production()`
>    actually receives **8** arguments — the 7 named ports plus `hil_port`
>    (`service.py:1395`).
> 3. **Stale planning docs (NOT FIXED — discoverability risk)**: `k1/planner/WIRING.md:102`,
>    `k1/planner/planner_v2.mmd:490`, and `k1/planner/planner.md:9467/9486/9610` still
>    describe Phase 5 as a "TODO — commented out in kernel.md". These should be updated
>    to reference the live S5–S7 implementation.
>
> All 6 implementation steps are confirmed present in `service.py:1309-1451`.
> The mock is replaced before `_running = True`. Issue remains **CLOSED**.

~~**Failure mode:** Every HIGH-tier task in production silently receives a mock plan.~~

~~**Fix:** Activate Kernel Phase 5.~~

---

## ISSUE-P02 — `LLMGatewayAdapter` uses `_build_payload` from `model_hub.adapters` — a private import

**Severity:** High
**Location:** `k1/planner/adapters/llm_gateway_adapter.py`

**Current behavior:**
`from k1.model_hub.adapters.bus_envelope_deserializer import _build_payload` — imports a
private function (underscore prefix) from inside `k1.model_hub.adapters`. This is an
undocumented internal of `model_hub` that could be refactored or removed without notice.
`_build_payload` coerces the planner's plain `dict` payload into a typed `ChatPayload` or
`StructuredPayload` before passing to the Model Hub.

**Failure mode:** If `model_hub` is refactored to rename, move, or remove `_build_payload`,
the planner fails at import time with `ImportError`. This silently prevents the planner
(and by extension, all HIGH-tier tasks) from starting.

**Fix:** Expose a public `build_payload(dict) -> ChatPayload | StructuredPayload` function
from `k1.model_hub.adapters.__init__` (or a new `k1.model_hub.utils` module). Planner
imports from the public API. The migration note in `types.py` about moving `PlannerLLMRequest`
to `k1.model_hub.types` is the correct long-term direction.

---

## ISSUE-P03 — `ToolCallRouter.get_schema()` uses `discover_capabilities` as a schema lookup — semantic mismatch

**Severity:** Medium
**Location:** `k1/planner/services/tool_call_router.py:get_schema()`

**Current behavior:**
```python
# Pragmatic bridge: use discover with exact capability_name as intent.
# Future: replace with IFabricRegistryPort.lookup(name, version).
result = await self._fabric_retrieval.discover_capabilities(intent=capability_name, top_k=1)
```
`discover_capabilities` is a semantic search (embed intent → cosine similarity). Using
it with a capability name as the `intent` query returns the capability only if the name
is semantically similar to the embedding. If a capability name is technical (e.g.
`"calendar.recurrence.expand_rrule"`) and the embedding space maps it differently, the
top-1 result may be a different capability.

**Failure mode:** During EXPAND stage, `get_schema()` for a specific capability returns
the wrong `CapabilityContract`. EXPAND injects wrong `output_schema`, `timeout_ms`, and
`safety_band` into the `PlanStep`. The committed plan contains steps configured for the
wrong capability. Execution proceeds with incorrect params.

**Fix:** Add `IFabricRegistryPort.lookup(name: str, version: Optional[str]) -> CapabilityContract`
as a new port (or extend `IFabricRetrievalPort`). `get_schema()` calls exact-match lookup, not
semantic search. This resolves the placeholder comment in the code.

---

## ISSUE-P04 — `ValidationVerdict.__post_init__` can be bypassed by constructing with `deterministic_pass=True` and error issues

**Severity:** Medium
**Location:** `k1/planner/types.py:ValidationVerdict.__post_init__()`

**Current behavior:**
`__post_init__` validates:
1. `approved` requires `deterministic_pass=True`
2. `approved` must not have `severity="error"` issues
3. `revise`/`reject` requires ≥1 issue

However, `ValidateService` sets `deterministic_pass=True` when Phase 1 passes, then
calls the LLM arbiter. If the arbiter returns `status="approved"` but the Phase 1 issues
list was mutated between Phase 1 and `ValidationVerdict` construction (e.g. race, or a
subtle ordering bug), the invariant would be violated silently in `__post_init__` only if
the issues list contains `severity="error"` items. In practice, the issue list is built
from deterministic Phase 1 results and passed straight through — but the data flow
(`ValidationVerdict(status=arbiter.status, issues=deterministic_issues, ...)`) makes
the combined object difficult to reason about.

**Failure mode (latent):** An approved verdict with a hidden `severity="error"` issue
propagates to `CommitService` and becomes a `CommittedPlan`. Orchestrator executes a plan
that VALIDATE had identified as containing a cycle or missing capability.

**Fix:** Separate the Phase 1 issues from the arbiter verdict in two explicit data classes:
`DeterministicValidationResult(issues, passed: bool)` and `ArbiterVerdict(status, reasons, score, safety)`.
`ValidationVerdict` assembles from both with explicit invariant checks. This makes the
contract explicit and prevents partial construction bugs.

---

## ISSUE-P05 — `MailboxAdapter.micro_replan()` holds `_plan_lock` for the full 10s micro-replan duration

**Severity:** Low (reduced from Medium)
**Location:** `k1/planner/adapters/mailbox_adapter.py:micro_replan()`

> **CORRECTION (May 2026):** Original description claimed deadlock between
> `MailboxAdapter._plan_lock` and `PlannerAgent._plan_lock`. These are **two different
> Python lock instances** (separate objects on separate classes). No actual deadlock can
> occur across them. Severity reduced from Medium to Low.

**Actual current behavior:**
`MailboxAdapter.micro_replan()` acquires its own `_plan_lock` before calling
`pipeline_controller.micro_replan()`. This is the same lock that the main
`_run_loop()` tries to acquire before the next `execute()`. The full micro-replan
takes up to 10s. During that window, the main loop cannot pick up the next `PlanRequest`
from the queue.

**Failure mode:** A new HIGH-tier task `PlanRequest` arrives during the 10s micro-replan
window. The main loop is blocked — it cannot dequeue the new request. If `mailbox_max_depth=5`
is reached, the new request is rejected with `MailboxFullError`.

**Fix:** Rename `MailboxAdapter._plan_lock` to `_micro_replan_lock` to distinguish it
from `PlannerAgent._plan_lock` in code review. Or use a separate `asyncio.Lock` for
the micro-replan to allow the main plan loop and micro-replan to execute independently.

---

## ISSUE-P06 — `PlannerAgent._cancel_set` is never pruned; unbounded growth for repeated cancels

**Severity:** Low
**Location:** `k1/planner/planner_agent.py`

**Current behavior:**
`_on_plan_cancel()` adds `request_id` to `_cancel_set`. The set is pruned only in two
paths: (a) `_run_loop()` discards after plan completes or is cancelled; (b) `stop()`
issues a cancel for `_in_flight_request_id` only.

Cancel events for plans that were never enqueued (e.g. arrived after `MailboxFullError`
rejection), plans that completed before the cancel arrived, or duplicate cancel events
accumulate in `_cancel_set` without removal.

**Failure mode:** In a long session with frequent cancel events (e.g. user cancels many
plans), `_cancel_set` grows without bound. More importantly, a future plan whose
`request_id` (UUIDv4) happens to share 4 bytes with a stale entry would be incorrectly
cancelled at pre-dequeue checkpoint 1. This is astronomically unlikely with UUID4, but
the set growth is still a memory leak.

**Fix:** Prune stale entries: use `_cancel_set: Dict[str, float]` (request_id → timestamp).
On each `_run_loop()` iteration, sweep entries older than `pipeline_timeout_ms + 5s`.

---

## ISSUE-P07 — `CommitService` WAL write failure is silently ignored; K0 plan persistence is best-effort only

**Severity:** Medium
**Location:** `k1/planner/stages/commit_service.py:_persist_to_wal()`

**Current behavior:**
```python
for attempt in range(2):
    try:
        await self._bridge_port.persist_plan(committed_plan, trace_id=ctx.trace_id)
        return  # success
    except Exception:
        pass  # retry or give up
# After 2 failures: silently continue
```
Plan is delivered via `k1.planner.plan.ready.v1` regardless of WAL write outcome. No
metric, no log, no bus event is emitted on WAL failure.

**Failure mode:** K0 WAL write fails (bridge unreachable, SQLite locked, disk full).
Orchestrator receives and executes `CommittedPlan`. The plan is lost from K0 persistent
storage. On next session, `recall_for_planning()` (SKETCH tool) cannot find this plan
for reference. More critically, if the Orchestrator crashes mid-execution, `crash_recovery()`
cannot find the WAL entry and the resumed plan has no K0 audit trail.

**Fix:** Emit `k1.planner.delta.v1` with `delta_type="WAL_WRITE_FAILED"` when both attempts
fail. This allows monitoring to alert on WAL failure rate. Optionally persist to a local
sidecar file (same pattern as BusOutbox in the bus module) as a fallback.

---

## ISSUE-P08 — SKETCH agentic loop `depends_on` uses integer indices resolved to intent strings; fragile under reordering

**Severity:** Low
**Location:** `k1/planner/stages/sketch_service.py` (response parsing)

**Current behavior:**
The SKETCH LLM response `depends_on` field contains zero-based integer indices into the
`steps` array: `[{"intent": "book flight", "depends_on": [0]}, ...]`. After parsing,
`sketch_service` resolves index 0 → `steps[0].intent` string. If the LLM returns steps
out of order, or repeats a step, or returns a `depends_on` index that is out of bounds,
the resolution silently returns `None` or wraps to the wrong step.

**Failure mode:** LLM returns `"depends_on": [3]` in a 3-step plan (0-indexed max = 2).
Index 3 is out of bounds. Resolution either raises `IndexError` (unhandled, bubbles to
`SketchFailedError`) or returns `None` (depends_on becomes empty, DAG loses an edge).
In the second case, EXPAND produces a plan with missing dependencies that VALIDATE's
cycle check does not catch (missing edge, not a cycle).

**Fix:** After index resolution, emit a validation error and retry clarification if any
`depends_on` index is out of bounds. Or change the prompt to use intent strings directly
in `depends_on` instead of integer indices — intent strings are stable, integers are not.

---

## ISSUE-P09 — Arbiter LLM auto-approve fallback path has no observability

**Severity:** Low
**Location:** `k1/planner/stages/validate_service.py` (Section 8.6 Path 2)

**Current behavior:**
If the LLM arbiter call raises any exception (`LLMTimeoutError`, `AdapterException`, or
any other), `ValidateService` falls back to auto-approve:
```python
except Exception:
    return ValidationVerdict(
        status=VERDICT_APPROVED,
        deterministic_pass=True,
        confidence=0.0,   # arbiter unavailable
        rationale="arbiter unavailable, deterministic checks passed",
        safety_assessment=SAFETY_UNKNOWN,
    )
```
This is correct behaviour (Section 8.6 Path 2 design) but the fallback is fully silent —
no log, no delta event, no bus event.

**Failure mode:** The arbiter LLM becomes consistently unavailable (model hub degraded).
All plans auto-approve with `confidence=0.0` and `safety_assessment="unknown"`. Orchestrator
executes plans that the arbiter would have flagged as `revise` or `reject`. From monitoring,
all plans appear to have `status=approved` — no signal that quality validation is bypassed.

**Fix:** Emit a `DeltaPayload(delta_type="ARBITER_FALLBACK", section="validate", ...)` when
the fallback fires. Increment a `mw_planner_arbiter_fallback_total` counter (or add to the
`plan.failed.v1` metadata if it later fails). At minimum, add a `DEBUG` log line.

---

## ISSUE-P10 — `ExpandService` has no HIL but arbiter `suggested_fixes` is injected as `arbiter_feedback` on revise — LLM may not follow structured suggestions

**Severity:** Low
**Location:** `k1/planner/pipeline_controller.py` (revise loop), `k1/planner/stages/expand_service.py`

**Current behavior:**
On `VERDICT_REVISE`, `PipelineController` calls:
```python
expanded_plan = await expand.execute(
    sketch_result, request, ctx,
    arbiter_feedback=last_verdict.suggested_fixes  # List[str]
)
```
`arbiter_feedback` is injected into the EXPAND system prompt as a bulleted list of textual
suggestions from the arbiter. The LLM (temperature=0.3) may or may not follow them — there
is no validation that the revised plan addresses the specific issues flagged. A second
VALIDATE call may return `VERDICT_REVISE` again for the same issues, but since the second
revise is treated as best-effort approve, the original issues are ignored.

**Failure mode:** Plan with arbiter issue "step s3 references missing capability" goes
to EXPAND revise. EXPAND re-generates but still includes s3 with the same capability
(LLM hallucination or misinterpretation of suggestion). Second VALIDATE flags same issue.
Second revise → best-effort approve. `CommittedPlan` contains a step with a missing
capability that `CHECK_CAPABILITY_MISSING` already identified. Orchestrator step s3 fails
at execution time.

**Fix:** Pass structured `ValidationIssue` objects (not string suggestions) as EXPAND
context. Require EXPAND to explicitly address each `step_id` mentioned in the issues list
— either by replacing the step or by a rationale entry that explains why the issue is
resolved. Add a targeted re-check in Phase 1 of the second VALIDATE pass.
