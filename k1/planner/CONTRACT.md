# K1 Planner — CONTRACT

---

## 1. Purpose

`PlannerAgent` converts a `PlanRequest` into a `CommittedPlan` by running a
4-stage LLM pipeline (SKETCH → EXPAND → VALIDATE → COMMIT) and delivers the
result via the event bus. It is an async single-actor component: one active plan at a
time (PLAN-02), all state in-memory, bus-driven trigger.

---

## 2. Core invariants

| ID | Statement | Enforcement point |
|---|---|---|
| PLAN-01 | Planner never writes SessionState | `IStateReadPort` has no write method; `SessionStateReadAdapter` wraps read-only reader |
| PLAN-02 | One active plan at a time (V1) | `PlannerAgent._plan_lock: asyncio.Lock` — non-reentrant |
| PLAN-03 | `CommitService` never calls LLM | `CommitService.__init__` has no `llm_port` parameter |
| PLAN-04 | Total pipeline timeout ≤ 45s; per-stage timeouts enforced | `PipelineController._create_stage_context()` injects `timeout_remaining_ms` |
| PLAN-05 | Max 6 tool calls per plan (SKETCH+EXPAND total) | `ToolCallRouter.call()` raises `BudgetExhaustedError` when exceeded |
| PLAN-06 | Planner never executes capabilities | `IFabricRetrievalPort` is read-only; no execute path |
| PLAN-10 | Max 2 HIL rounds per plan (clarification + approval) | `PipelineController._hil_round_count` |
| PLAN-11 | Per-stage and total token budgets injected, not assumed | `PipelineController._create_stage_context()` passes `stage_budget` |
| PLAN-12 | Micro-replan never modifies completed steps | `_enforce_plan12()` strips completed step IDs from micro-expanded plan |

---

## 3. Delivery guarantees

- **At-most-once plan delivery** — `CommitService` emits `k1.planner.plan.ready.v1` with retry-once. If the event bus is unavailable after two attempts, the plan is lost (no persisted outbox). WAL write to K0 may still succeed independently.
- **Fire-and-forget WAL** — `CommitService._persist_to_wal()` calls `bridge_port.persist_plan()` retry-once; failure never blocks plan delivery. Plan reaches Orchestrator even if K0 WAL write fails.
- **Micro-replan is synchronous** — `PipelineController.micro_replan()` returns `Optional[CommittedPlan]` directly (no bus delivery path). Orchestrator receives the result as a return value from `IMailboxPort.micro_replan()`.
- **Cancellation is cooperative** — 5 cancel checkpoints in the pipeline; max latency = one LLM call duration (up to `sketch_timeout_ms=8s` worst case).
- **Queue is bounded** — `MailboxAdapter` rejects new `PlanRequest` with `MailboxFullError` when depth ≥ `mailbox_max_depth=5`.

---

## 4. Trigger and entry points

Planner has two external triggers:

| Topic | Handler | Behaviour |
|---|---|---|
| `k1.planner.plan.request.v1` | `PlannerAgent._on_plan_request()` | Validates, enqueues `PlanRequest` to `MailboxAdapter` |
| `k1.planner.plan.cancel.v1` | `PlannerAgent._on_plan_cancel()` | Adds `request_id` to `_cancel_set` |

Both handlers are **synchronous** (bus delivers synchronously). Enqueue happens via `loop.create_task(self._safe_enqueue(request))`.

`IMailboxPort.micro_replan()` is a direct async call from Orchestrator — not bus-triggered.

---

## 5. Pipeline stages and contracts

Four sequential stages, each independently timeout-bounded.

### Stage 1: SKETCH (`SketchService.execute()`)

```
Input:   PlanRequest (intent, session_snapshot, constraints)
Output:  SketchResult(rough_steps, capability_candidates, rationale)
LLM:     CHAT mode, max_tokens=2000, temperature=0.7
Tools:   discover_capabilities, query_session_context,
         recall_long_term_memory, find_prompts  (max 6 total across SKETCH+EXPAND)
HIL:     Yes — clarification request if LLM sets needs_clarification=true
         and hil_rounds_remaining > 0
Timeout: sketch_timeout_ms=8,000ms
```

Agentic loop (max `_MAX_TOOL_ROUNDS=6`): LLM called → tool_calls dispatched via
`ToolCallRouter` → results appended to messages → LLM re-called until no tool_calls.
Parse final JSON into `RoughStep` list. `depends_on` uses integer indices (0-based) that
are resolved to intent strings before returning.

### Stage 2: EXPAND (`ExpandService.execute()`)

```
Input:   SketchResult + PlanRequest + optional arbiter_feedback (on revise retry)
Output:  ExpandedPlan(steps, dependencies, tool_mappings, rationale)
LLM:     CHAT mode, max_tokens=1000, temperature=0.3
Tools:   discover_capabilities, get_capability_schema, find_prompts,
         query_session_context
HIL:     None
Timeout: expand_timeout_ms=5,000ms
```

LLM produces step IDs shaped as `s` followed by digits. Each step becomes a
`PlanStep` (from `k1.orchestrator.types`). Infrastructure fields are injected
from `CapabilityContract` metadata (timeout_ms, output_schema,
compensation_fn, safety_band, required_context, etc.) — not from LLM.

Prompt/profile binding is exact-evidence only. If the LLM proposes
`prompt_template`, EXPAND preserves it only when the name is returned by
`find_prompts` or present in the injected prompt inventory. Unverified prompt
names are cleared and logged. EXPAND does not infer replacements from domain
labels, prompt scores, compatible prompt metadata, or capability-name text.
`activity_profile` is copied from capability-contract metadata or from the
exact validated prompt descriptor.

### Stage 3: VALIDATE (`ValidateService.execute()`)

```
Input:   ExpandedPlan + PlanRequest + optional cached_capabilities
Output:  ValidationVerdict(status, issues, confidence, rationale, safety_assessment)
Phase 1: Deterministic checks — no LLM, <5ms
Phase 2: LLM Arbiter — STRUCTURED mode, max_tokens=500 (micro: 256), temperature=0.1
Phase 3: Optional HIL approval if safety_assessment in ("caution", "unsafe")
Timeout: validate_timeout_ms=3,000ms (arbiter hardcoded to 3,000ms)
```

**Phase 1 checks (deterministic):**
- `CHECK_STEP_ID_DUPLICATE` — duplicate step IDs
- `CHECK_SELF_REFERENCE` — step depends on itself
- `CHECK_DAG_CYCLE` — Kahn's topological sort for cycles
- `CHECK_DANGLING_DEPENDENCY` — dep not in step set (warning if in completed steps)
- `CHECK_INTER_STEP_REF` — `$<step_id>.result.<field>` consistency
- `CHECK_CAPABILITY_MISSING` — capability not in fabric registry
- `CHECK_UNSAFE_CAPABILITY` — capability safety_band exceeds request band
- `CHECK_TOOL_BUDGET_EXCEEDED`, `CHECK_PARAM_TYPE_MISMATCH`

If Phase 1 returns `severity="error"`: `VERDICT_REJECT` immediately, no LLM called.

**Arbiter unavailable:** auto-approve if deterministic pass (Section 8.6 Path 2).

### Stage 4: COMMIT (`CommitService.execute()`)

```
Input:   ExpandedPlan + PlanRequest + ValidationVerdict
Output:  CommittedPlan
LLM:     None (PLAN-03)
Timeout: commit_timeout_ms=1,000ms
```

11-step assembly:
1. `plan_id = uuid4()`
2. `created_at = time.time()`
3. Steps and dependencies copied frozen from `ExpandedPlan`
4. `estimated_duration_ms` = critical-path DP (Kahn's + longest-path)
5. `CommittedPlan.__post_init__()` validation
6. WAL persist: `bridge_port.persist_plan()` retry-once (fire-and-forget)
7. Event delivery: `event_port.emit(TOPIC_PLAN_READY, committed_plan)` retry-once
8. Stage delta + plan-end delta emitted

---

## 6. Revise loop contract

```
First VERDICT_REVISE → arbiter_feedback injected → re-run EXPAND → re-run VALIDATE
Second VERDICT_REVISE → treated as approved (best-effort, PLAN degraded)
First VERDICT_REJECT → re-run EXPAND → re-run VALIDATE
Second VERDICT_REJECT → raise ValidateRejectedError → emit plan.failed.v1
Max revise loop iterations: 1 (config not exposed)
```

---

## 7. Micro-replan contract

`IMailboxPort.micro_replan(request: MicroReplanRequest) → CommittedPlan`

| Aspect | Full plan | Micro-replan |
|---|---|---|
| Total timeout | 45,000ms | 10,000ms |
| Token budget | 3,500 | 2,000 |
| Max tool calls | 6 | 3 |
| HIL | Yes (SKETCH + VALIDATE) | None (PLAN-12, SS10.5.4) |
| Revise loop | 1 retry | None — first revise → best-effort approve |
| Verdict "reject" | emit plan.failed.v1 + raise | Returns `None` silently |
| Failure result | raises + emits `plan.failed.v1` | Returns `None` |
| Delivery | bus event `k1.planner.plan.ready.v1` | Synchronous return to caller |
| Completed steps | not applicable | PLAN-12: frozen, never in output |
| FSM path | IDLE→SKETCH→EXPAND→VALIDATE→COMMIT | IDLE→MICRO_SKETCH→MICRO_EXPAND→MICRO_VALIDATE→COMMITTING |

`MicroReplanRequest` contains: `remaining_steps`, `completed_results`, `reason`, `trigger_wave_index` — injected into LLM prompt for context.

---

## 8. Port contracts

### `ILLMPort`

```python
async def execute(self, request: PlannerLLMRequest) -> PlannerLLMResponse
```

`PlannerLLMRequest.capability`: `"CHAT"` (SKETCH, EXPAND) or `"STRUCTURED"` (VALIDATE arbiter).
`PlannerLLMRequest.constraints.max_tokens`: per-stage budget.
Response `metadata["usage.total_tokens"]` is read after each call for budget tracking.

### `IFabricRetrievalPort`

```python
async def discover_capabilities(domain, intent, safety_band, session_context, top_k=10) -> RetrievalResult
async def find_relevant_prompts(intent, domain, safety_band, top_k=10) -> RetrievalResult
```

Read-only (PLAN-06). Called by `ToolCallRouter.discover()` and `ToolCallRouter.find_prompts()`.
`FabricRetrievalAdapter` enforces 50ms timeout + 1 retry.

### `IStateReadPort`

```python
async def read_sections(sections: List[str], trace_id: str = "") -> SessionSnapshot
```

Read-only (PLAN-01). Called by `ToolCallRouter.read_context()` when LLM issues
`query_session_context` tool call. Default sections: `["beliefs_active", "control", "history_recent"]`.

### `IPlannerWritePort` (bridge)

```python
async def recall(query: str, selectors: List[str], trace_id: str) -> RecallResponse
async def persist_plan(plan: CommittedPlan, trace_id: str) -> None
```

`recall` → K0 memory query. `persist_plan` → K0 WAL write (fire-and-forget).

### `IDeltaEmitPort`

```python
def emit(self, delta: DeltaPayload) -> None  # sync, must not raise
```

Emitted on every FSM transition and at plan start/end. Observer only — failures swallowed.

### `IEventPort`

```python
def emit(topic: str, payload: Any) -> None          # sync, fire-and-forget
def subscribe(topic: str, handler: Callable) -> SubscriptionHandle
def unsubscribe(handle: SubscriptionHandle) -> bool
```

### `IMailboxPort`

```python
async def dequeue() -> PlanRequest
async def enqueue(request: PlanRequest) -> None
async def send_cancel(request_id: str) -> None
def drain() -> List[PlanRequest]
async def micro_replan(request: MicroReplanRequest) -> CommittedPlan
```

---

## 9. Key types

### `PlanRequest` (from `k1.orchestrator.types`)
Input to the planner. Contains: `request_id`, `trace_id`, `intent`, `session_snapshot`, `constraints`, `priority`.

### `CommittedPlan` (from `k1.orchestrator.types`)
Output of the planner. Contains: `plan_id`, `request_id`, `intent`, `steps: List[PlanStep]`, `dependencies: Dict[str, List[str]]`, `trace_id`, `estimated_duration_ms`, `created_at`.

### `PlanStep` (from `k1.orchestrator.types`)
One executable step. Fields: `step_id` (`s` followed by digits), `capability`, `params`, `timeout_ms`, `output_schema`, `compensation_fn`, `safety_band`, `is_optional`, `tools_granted`, `prompt_template`, `activity_profile`.

### `MicroReplanRequest` (from `k1.orchestrator.types`)
Micro-replan input. Contains: `request_id`, `trace_id`, `original_plan_id`, `remaining_steps`, `completed_results: Dict[str, StepResult]`, `reason`, `trigger_wave_index`.

### `SketchResult` (internal)
`rough_steps: List[RoughStep]`, `capability_candidates: List[ScoredCapability]`, `rationale: str`.

### `ExpandedPlan` (internal)
`steps: List[PlanStep]`, `dependencies: Dict[str, List[str]]`, `tool_mappings: Dict[str, str]`, `rationale: str`.

### `ValidationVerdict` (internal)
`status: str` ("approved"|"revise"|"reject"), `issues: List[ValidationIssue]`, `confidence: float`, `safety_assessment: str`, `suggested_fixes: List[str]`, `deterministic_pass: bool`.

`__post_init__` invariant: `approved` → no `severity="error"` issues + `deterministic_pass=True`.

---

## 10. Bus topics

### Consumed

| Topic | Handler | When |
|---|---|---|
| `k1.planner.plan.request.v1` | `PlannerAgent._on_plan_request()` | Orchestrator fires HIGH-tier request |
| `k1.planner.plan.cancel.v1` | `PlannerAgent._on_plan_cancel()` | Orchestrator requests cancel |

### Produced

| Topic | Payload | When |
|---|---|---|
| `k1.planner.plan.ready.v1` | `CommittedPlan` | Stage 4 COMMIT success |
| `k1.planner.plan.failed.v1` | `PlanFailedPayload` | Any stage exception (not cancel) |
| `k1.planner.plan.cancelled.v1` | `PlanCancelledPayload` | Cancel checkpoint fires or pre-dequeue cancel |
| `k1.planner.micro_replan.ready.v1` | `CommittedPlan` | Micro-replan COMMIT success (V2 — not emitted in V1; returned synchronously) |
| `k1.planner.delta.v1` | `DeltaPayload` | Every FSM transition + plan start/end |

---

## 11. Error surface

| Exception | Raised by | Propagates to |
|---|---|---|
| `SketchFailedError` | `SketchService` | `PipelineController` → `plan.failed.v1` |
| `ExpandFailedError` | `ExpandService` | `PipelineController` → `plan.failed.v1` |
| `ValidateRejectedError` | `PipelineController` (second reject) | `PipelineController` → `plan.failed.v1` |
| `CommitFailedError` | `CommitService` | `PipelineController` → `plan.failed.v1` |
| `BudgetExhaustedError` | `ToolCallRouter` | Stage service → `PipelineController` → `plan.failed.v1` |
| `PlanCancelledError` | `PipelineController._check_cancel()` | `PlannerAgent._run_loop()` → `plan.cancelled.v1` |
| `HILTimeoutError` | `SketchService`/`ValidateService` | `PipelineController` → `plan.failed.v1` |
| `HILBudgetExceededError` | `PipelineController` | `PipelineController` → `plan.failed.v1` |
| `LLMTimeoutError` | `LLMGatewayAdapter` | Stage service → `plan.failed.v1` |
| `MailboxFullError` | `MailboxAdapter` | `PlannerAgent._safe_enqueue` — emits `plan.failed.v1` directly |
| `AdapterException(degraded=True)` | `FabricRetrievalAdapter` | Stage service continues with empty result |

`plan.failed.v1` is emitted by `PipelineController._emit_plan_failed()`. It is emitted **exactly once** per failed plan: the `_plan_failed_emitted=True` attribute is set on the exception to prevent double-emit.

---

## 12. What Planner does NOT do

- Does **not** write SessionState (PLAN-01)
- Does **not** execute capabilities (PLAN-06)
- Does **not** generate embeddings
- Does **not** run concurrent plans (PLAN-02, V1)
- Does **not** use circuit breakers internally — degraded adapters return empty results
- Does **not** have an HTTP/RPC interface — bus-driven only + direct `micro_replan()` call
- Does **not** own its process — lives inside the K1 kernel event loop
- Does **not** persist any state besides the K0 WAL write in CommitService
