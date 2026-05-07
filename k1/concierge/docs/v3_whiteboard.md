# K1 Concierge V3 Whiteboard

## 1) Purpose

Define the **V3 execution plan** for continuous, human-like conversation where asynchronous task execution, HITL pauses, interruptions, and proactive updates are coordinated without rigid turn-by-turn behavior.

V3 focus:

- Keep conversation natural and continuous.
- Make HITL weaving reliable and non-chaotic.
- Prevent state races across multi-device and concurrent inputs.
- Resolve V2 spec ambiguities before implementation.

---

## 2) What We Keep From V2

These design choices remain correct and are retained:

- Split actor model: **Front (conversation)** + **Back (execution)**.
- Event-driven orchestration with explicit task lifecycle.
- Closed-loop HITL protocol with persisted pending state.
- Session state ownership discipline (single-writer sections).
- Back side-effect gating through policy/enforcement layer.

---

## 3) Core V3 Changes (Planned)

### A. Event-Sourced Conversation Ledger (Source of Truth)

- Introduce append-only **conversation ledger** as the canonical timeline.
- Session state becomes a **derived projection** (materialized view), not the source of truth.
- Every user input, system action, HITL request/response, task transition, and weave action is recorded as immutable event.

Why:

- Handles chaotic ordering safely.
- Enables replay/recovery/debugging.
- Eliminates hidden state drift between actors.

### B. Conversation Arbiter (New Service)

- Add an explicit **Arbiter** before Front/Back routing.
- Classify incoming user intent against inflight work into:
  - `cancel`
  - `modify_inflight`
  - `parallel_new`
  - `defer`
- Arbiter outputs deterministic routing/priority metadata for FSM.

Why:

- Removes implicit turn assumptions.
- Supports non-linear, human interruptions safely.

### C. BackPool + Task Lease Model

- Replace single Back worker bottleneck with **BackPool**.
- Each task gets a lease/owner and cancellation token.
- Allow parallel execution with explicit ordering constraints per session/topic.

Why:

- Avoids queue head-of-line blocking.
- Improves responsiveness under concurrent family activity.

### D. Adaptive Weave Policy (Not Fixed Window)

- Replace fixed weave window with **adaptive batching**.
- Inputs to policy:
  - urgency
  - user currently typing/speaking
  - conversational load
  - number/type of pending completions
- Arbiter decides immediate weave vs delayed bundle vs summarized digest.

Why:

### E. HITL as First-Class Blocking Sub-Task

- Model HITL request as explicit blocking sub-task attached to parent task.
- Persist `pending_hil_id`, `hil_type`, `hil_deadline`, `resume_token`.
- Back execution path remains blocked for side-effecting steps until resolve event.

Why:

- Makes suspend/resume deterministic.
- Prevents silent policy bypass.

### F. FSM Hard Guards + Dead-Letter Handling

- Add guard table for valid state/event transitions.
- Reject invalid transitions with explicit fault events.
- Route orphan/late events to dead-letter stream for reconciliation.

Why:

- Prevents hidden corruption from async race conditions.

---

## 4) V3 Event Contract Additions

Planned canonical events:

- `conversation.user_input.received`
- `conversation.intent.arbitrated`
- `task.created`
- `task.leased`
- `task.progressed`
- `task.hil.requested`
- `task.hil.resolved`
- `task.suspended`
- `task.resumed`
- `task.cancelled`
- `task.completed`
- `task.failed`
- `conversation.weave.candidate`
- `conversation.weave.decided`
- `conversation.weave.emitted`
- `conversation.dead_lettered`

Required fields (minimum):

- `event_id`, `event_type`, `session_id`, `correlation_id`, `causation_id`, `parent_event_id`, `task_id` (if applicable), `actor`, `ts_utc`, `priority`, `payload_schema_version`.

---

## 5) V3 HITL Weaving Rules

1. Back emits `task.hil.requested` with strict typed payload (`clarify`, `approve`, `select`).
2. Front receives and presents user-facing HITL interaction.
3. User response emits `task.hil.resolved` (or timeout/cancel path).
4. FSM/Arbiter validates resolution completeness.
5. Back resumes only with valid `resume_token`.
6. Async completions during active chat go to `conversation.weave.candidate`.
7. Arbiter applies adaptive policy and emits `conversation.weave.decided`.
8. Front emits weave response in correct tone/timing context.

Non-negotiable safety:

- No side-effect tool call after HITL request unless resolved.

---

## 6) Multi-Device / Concurrent Input Policy

For same session with overlapping user signals:

- Define deterministic precedence (example):
  1) explicit cancel/stop
  2) safety-critical response
  3) direct response to pending HITL
  4) new unrelated request
- Use device metadata + recency + confirmation threshold.
- Require confirmation for conflicting high-impact actions.

---

## 7) Consistency Fixes to Apply from V2 Before Build

- Normalize weave timing policy (remove 300ms vs 500ms ambiguity).
- Align WEAVE mode tool policy with scenarios (whether acknowledge allowed).
- Normalize topic namespaces for HITL/orchestration signaling.
- Clarify internal topic naming for weave batch events.
- Explicitly define stale-read policy for long-running Back tasks.

---

## 8) Minimal V3 Build Sequence

1. Finalize event schemas and metadata invariants.
2. Implement ledger writer + projection reader.
3. Implement Conversation Arbiter decision table.
4. Add BackPool with lease/cancel primitives.
5. Implement HITL sub-task model + resume token validation.
6. Implement adaptive weave policy.
7. Add FSM guard matrix + dead-letter pipeline.
8. Run chaos/concurrency scenario tests (multi-device + interruption storms).

---

## 9) Success Criteria (V3)

- User can interrupt, switch, and resume naturally without losing context.
- HITL paths never deadlock or bypass approvals.
- Async completions are woven without derailing active conversation.
- System remains deterministic under concurrent events.
- Replay of ledger reconstructs session behavior accurately.

---

## 10) Open Questions To Resolve Next

- BackPool sizing and lease expiry defaults.
- Adaptive weave threshold tuning signals and weights.
- Cross-session family context boundaries and escalation rules.
- Memory retrieval SLOs required for real-time conversational continuity.
- Failure strategy for IoT/event floods and degraded mode behavior.

---

## 11) Immediate Next Step

Use this whiteboard to derive:

- V3 ADR set
- contract deltas (events/FSM/state)
- implementation tickets mapped to milestones

---

## 12) Deep Review: `poc/k1_poc/protocols`

Review scope completed (all files):

- `__init__.py`
- `cancellation.py`, `cancel_handler.py`, `cancel_events.py`
- `suspension.py`, `suspension_manager.py`, `suspension_events.py`
- `hitl.py`, `hitl_coordinator.py`, `hitl_flow.py`, `hitl_pipeline.py`, `hitl_persistence.py`, `hitl_wiring.py`
- `weave_state.py`, `weave_batcher.py`

### 12.1 What is strong (keep)

- Protocol boundaries are clear: cancel, suspend, HITL, weave are separated and composable.
- Safety posture is good: RED blocking, side-effect escalation, and L2 pre-invoke checks exist.
- Timeout/recovery concepts are present: pending HITL persistence model + recovery scan utilities.
- Resume-context design is strong: explicit instruction + preserved findings/tool history for Back resume.
- Weave model is practical: queue + batch + front-busy buffering already implemented.

### 12.2 Key protocol gaps found

#### A) Timeout configuration drift risk

- `suspension.py` and `hitl.py` both define default timeout maps.
- Runtime may use config lookups, but multiple default maps still create future drift risk.

V3 action:

- Single source of truth for all HITL/suspension timeouts in config + one protocol accessor.

#### B) Suspension limit source inconsistency

- `SuspensionManager` enforces `MAX_SUSPENSIONS_PER_TASK` via imported constant.
- `HILCoordinator` uses `HILCoordinatorConfig.max_rounds`.
- Two independent limit sources can diverge.

V3 action:

- Enforce one canonical limit source (coordinator config), and make suspension manager consume it.

#### C) Weave timing policy still static

- `weave_batcher.py` uses fixed window behavior.
- Good for baseline, but not enough for chaotic conversation timing.

V3 action:

- Replace fixed-only batching with adaptive policy input (urgency, user-active typing, queue pressure, cognitive load).

#### D) Async/concurrency semantics are mostly in-memory

- Pending HITL and suspend contexts are managed in-process maps.
- Crash recovery model exists in `hitl_persistence.py`, but runtime path should ensure every lifecycle mutation is event-ledgered and persisted atomically.

V3 action:

- Move protocol lifecycle to event-sourced ledger first, with projections for runtime maps.

#### E) Event contract fragmentation

- Multiple event dataclasses exist across cancel/suspend/HITL/weave with partially overlapping payload shapes.
- No single canonical protocol schema registry in this folder.

V3 action:

- Define canonical v3 protocol event schemas with required metadata (`correlation_id`, `causation_id`, `parent_event_id`, `schema_version`).

#### F) Mixed sync/async context paths in suspension manager

- `SuspensionManager` exposes async request lifecycle and separate sync context store/pop methods.
- Useful for FSM integration today, but it increases ambiguity in invariants and teardown responsibilities.

V3 action:

- Consolidate through one lifecycle API (event-driven state transitions) and keep sync helpers as compatibility shim only.

### 12.3 File-by-file assessment

- `cancellation.py`: solid cooperative token design; idempotent cancel/check path is good.
- `cancel_handler.py`: good dedup and late-completion handling; token lifecycle cleanup is explicit.
- `cancel_events.py`: payload model is clear, but should align to v3 canonical event metadata.
- `suspension.py`: good request/resolution shape and timeout semantics; needs single timeout authority.
- `suspension_manager.py`: core flow good; unify config/limits and simplify dual sync-async API.
- `hitl.py`: request/response schema and safety escalation are good; remove duplicate timeout defaults.
- `hitl_coordinator.py`: strongest orchestration piece; keep, but bind to canonical event ledger + single limits source.
- `hitl_flow.py`: strong typed helpers for clarification/approval/selection.
- `hitl_pipeline.py`: good policy logic for approval/selection; should emit canonical protocol events for each decision branch.
- `hitl_persistence.py`: valuable recovery model; should become projection over event ledger in v3.
- `hitl_wiring.py`: strong cross-layer validation; should be expanded with arbiter checks for multi-device conflicts.
- `weave_state.py`: clear state-action mapping; add explicit dead-letter/fallback transitions for invalid states.
- `weave_batcher.py`: clean batching primitive; promote to adaptive policy engine in v3.

### 12.4 V3 protocol decisions (proposed)

1. Keep current protocol decomposition (cancel/suspend/HITL/weave) as the package shape.
2. Introduce canonical event ledger contracts and make protocol state derived from events.
3. Unify timeout and suspension limits under one config authority.
4. Add protocol-level arbitration hooks for concurrent/multi-device user inputs.
5. Upgrade weave batcher from fixed window to adaptive policy module.
6. Keep `validate_hitl_wiring()` and extend it with runtime arbitration + schema conformance checks.

### 12.5 Protocol-first implementation sequence

1. Create v3 event schemas for cancel/suspend/HITL/weave lifecycle.
2. Add protocol ledger writer and idempotency keys.
3. Refactor coordinator/manager classes to consume ledger-backed projections.
4. Implement adaptive weave decision policy.
5. Add concurrency tests for: late completion after cancel, timeout recovery, overlapping HITL responses, multi-device conflicting responses.

---

## 13) Deep Review: Coordinator + FSM (End-to-End)

Scope reviewed end-to-end:

- `poc/k1_poc/demo/coordinator.py`
- `poc/k1_poc/demo/coordinator_old.py` (legacy reference)
- `poc/k1_poc/fsm/__init__.py`
- `poc/k1_poc/fsm/states.py`
- `poc/k1_poc/fsm/errors.py`
- `poc/k1_poc/fsm/front_lock.py`
- `poc/k1_poc/fsm/turn_state.py`
- `poc/k1_poc/fsm/transition_table.py`
- `poc/k1_poc/fsm/interrupt_handler.py`
- `poc/k1_poc/fsm/history_writer.py`
- `poc/k1_poc/fsm/control_extension.py`
- `poc/k1_poc/fsm/phase1.py`
- `poc/k1_poc/fsm/task_bridge.py`
- `poc/k1_poc/fsm/controller.py`

### 13.1 Runtime composition reality

Current runtime path (active):

1. `coordinator.py` Phase 2 calls `kernel.bootstrap.start_kernel()`.
2. Kernel wires bus, FSM, model, session state, protocols, orchestrator, delta, experience.
3. Demo coordinator starts its own mailbox consumer (`auto_start_consumer=False` in kernel config).
4. Front mailbox is processed inline; Back mailbox is processed in background tasks.

Legacy path (not primary):

- `coordinator_old.py` contains old 6-phase direct composition and `boot(ordered=False)` flow.

Implication:

- Any behavior analysis must prioritize `coordinator.py` + `fsm/controller.py`.

### 13.2 End-to-end execution table

| Stage | Primary Owner | Input Event | Core Action | Output / Next Event |
| --- | --- | --- | --- | --- |
| 1 | Coordinator Consumer | `k1.session.user.input.v1` in front mailbox | Calls `front_handler` through FSM-routed delivery | Front emits `ack`, optional `task.dispatch`, optional `final.response` |
| 2 | FSM (`_on_user_input`) | user input topic | Turn increment (except worker clarification path), history write, Phase1 run, transition to `DISPATCHING`, deliver to Front | `turn.started`, then Front work begins |
| 3 | FSM (`_on_task_dispatch`) | `k1.orchestration.task.dispatch.v1` | Register task, add cancellation token, update task state, transition to `COMPANIONING` | Route LOW/MEDIUM/HIGH via orchestrator router |
| 4 | Back Handler | task dispatch in back mailbox | ReAct execution with tools | emits `task.complete` or `task.failed` or `task.suspended` |
| 5 | FSM (`_on_task_complete/_failed/_suspended`) | back result events | Updates task bridge, transitions to `DELIVERING` or `CLARIFYING_WORKER` or queue/defer | Deliver to Front or queue for weave |
| 6 | FSM (`_on_response_final`) | `k1.response.final.v1` | Final state resolution, history sink write, weave check, queue drain, turn completion | `LISTENING` or `WEAVING` or `COMPANIONING` |
| 7 | FSM Weave Path | pending results present | Start/flush weave window, build weave envelope, deliver to Front | Single woven response to user |

### 13.3 State/Event trace tables

#### A) Normal request flow (no interrupt, no HITL)

| Step | State Before | Event | State After | Notes |
| --- | --- | --- | --- | --- |
| 1 | `LISTENING` | `user.input` | `DISPATCHING` | Phase1 runs first; user entry written |
| 2 | `DISPATCHING` | `task.dispatch` (from Front) | `COMPANIONING` | Task registered and routed to Back |
| 3 | `COMPANIONING` | `tool.started` (optional) | `PROGRESSING` | Back active |
| 4 | `PROGRESSING` | `tool.completed` (optional) | `COMPANIONING` | Back continues/finishes |
| 5 | `COMPANIONING` | `task.complete` | `DELIVERING` | Front PRESENT path |
| 6 | `DELIVERING` | `final.response` | `LISTENING` | turn.completed emitted |

#### B) Interrupt chat flow (user changes topic while Back still working)

| Step | State Before | Event | State After | Notes |
| --- | --- | --- | --- | --- |
| 1 | `COMPANIONING` or `PROGRESSING` | `user.input` | `INTERRUPT_HANDLING` | Interrupt classifier invoked |
| 2 | `INTERRUPT_HANDLING` | synthetic `interrupt.routed` | `DISPATCHING` | New turn starts |
| 3 | `DISPATCHING` | Front processing | `COMPANIONING` or `LISTENING` | Depends on whether new tasks dispatched |
| 4 | (later) | older task completion arrives | `DELIVERING` or queued/weave | Async completion merged with ongoing convo |

#### C) Cancel race flow (cancel vs completion overlap)

| Step | State Before | Event | State After | Notes |
| --- | --- | --- | --- | --- |
| 1 | `COMPANIONING/PROGRESSING` | `task.cancel` | `CANCELLING` (forced path) | Cancellation token set |
| 2 | `CANCELLING` | late `task.complete` | completion ignored | Dedup logic checks cancelled set |
| 3 | `CANCELLING` | `task.failed(reason=cancelled)` | `DELIVERING` | User gets cancel result |
| 4 | `DELIVERING` | `final.response` | `LISTENING` | Queue drained |

#### D) HITL suspend/resume flow

| Step | State Before | Event | State After | Notes |
| --- | --- | --- | --- | --- |
| 1 | `COMPANIONING/PROGRESSING` | `task.suspended` | `CLARIFYING_WORKER` | Suspension context stored |
| 2 | `CLARIFYING_WORKER` | Front HITL relay final | `COMPANIONING` or `LISTENING` | Depends on active tasks |
| 3 | `CLARIFYING_WORKER` | user response -> `task.resume` | `COMPANIONING` | Resume context built and sent to Back |
| 4 | `COMPANIONING` | resumed task completes | `DELIVERING` | Normal result presentation |

#### E) Weave burst flow (multiple completions during active conversation)

| Step | State Before | Event | State After | Notes |
| --- | --- | --- | --- | --- |
| 1 | `DISPATCHING/COMPANIONING/DELIVERING` | `task.complete` while Front busy | queue in `pending_results` | Not dropped |
| 2 | `DELIVERING/WEAVING` | `final.response` | `WEAVING` (if pending exists) | Weave flush scheduled |
| 3 | `WEAVING` | weave flush timer | `WEAVING` | Batch envelope delivered to Front |
| 4 | `WEAVING` | final weave response | `LISTENING` | turn.completed + queue drain |

### 13.4 Why coordination feels hard (actual hotspots)

Primary hotspots observed:

1. `FSM._on_response_final` is a high-branch decision hub (state resolution + weave + history + queue drain).
2. Deferred HITL surfacing path adds another asynchronous re-entry point after returning to `LISTENING`.
3. Coordinator consumer runs Front inline and Back in background, which is correct for responsiveness but increases interleaving complexity.
4. Same-turn-complete suppression logic is necessary to avoid duplicate presentation but is race-sensitive.

### 13.5 Keep vs Change (Coordinator/FSM)

Keep:

- Front/Back split with mailbox routing.
- FrontLock gating and pending_results queue.
- Deferred HITL surfacing model.
- Same-turn completion suppression (prevents duplicate PRESENT response).

Change in V3:

1. Externalize `_on_response_final` branching into explicit transition/action table (guard-driven, testable).
2. Introduce canonical event-ledgered idempotency keys for user input and task lifecycle transitions.
3. Move weave trigger decision from fixed timing into adaptive arbiter policy.
4. Replace forced CANCELLING shortcut with validated transition contract + explicit fault/dead-letter on illegal transition attempt.
5. Add deterministic multi-device arbitration before FSM consumes user input.

### 13.6 Immediate test matrix to stabilize current behavior

1. Interrupt during `PROGRESSING` + simultaneous task completion.
2. Cancel request followed by late completion and then failed(cancelled).
3. Suspend in incompatible state (`DISPATCHING`) then deferred surfacing from `LISTENING`.
4. Three task completions inside weave window while user sends a new message.
5. Same-turn dispatch+complete ensuring no duplicate PRESENT output.

---

## 14) Deep Review: `poc/k1_poc/actors`

Scope reviewed end-to-end:

- `poc/k1_poc/actors/__init__.py`
- `poc/k1_poc/actors/front.py`
- `poc/k1_poc/actors/back.py`

### 14.1 Why this folder is critical

- `actors/front.py` is where user-facing behavior is actually generated (mode selection, prompt build, ReAct output, event emission ordering).
- `actors/back.py` is where execution behavior is produced (tool planning/execution, completion/suspend/fail emission).
- FSM can route perfectly, but if actor semantics drift, conversation quality and HITL safety still fail.

### 14.2 Front actor behavior (what is happening)

Core runtime flow in `front_handler`:

1. Guard out observability-only topics to prevent accidental loops.
2. Resolve `PromptMode` from FSM state + event + SS.
3. Build mode-specific scenario data (`STANDARD`, `PRESENT`, `WEAVE`, `HITL_RELAY`, `HITL_RESOLVE`, etc.).
4. Build prompt via `DynamicPromptBuilder`.
5. Run ReAct loop.
6. Emit events in strict order: cancels first, then dispatches, then final response.

Strong points:

- Correct post-loop emission order protects FSM transition correctness.
- Explicit skip list for observability topics reduces recursive loops.
- HITL_RESOLVE auto-emits resume path and resolution payload.

### 14.3 Back actor behavior (what is happening)

Core runtime flow in `back_handler`:

1. Parse dispatch payload + tier.
2. Read selective SS snapshot once.
3. Build static execution-oriented back prompt.
4. Build short history context + task JSON as active user message.
5. Run ReAct with tier-filtered tool set + budget.
6. Emit `task.complete` / `task.suspended` / `task.failed`.

Strong points:

- Clean separation: Back does not produce user-facing text.
- Tier-based tool allowlists and budgets are explicit.
- Result emission is centralized and consistent.

### 14.4 Confirmed high-priority gaps

#### A) Resume path implementation is present but not wired in runtime

Observed:

- `back_resume_handler` exists, but no call site uses it.
- Coordinator and kernel consumers call only `back_handler` for all back mailbox events.

Risk:

- Resume-specific logic (context replay, remaining budget handling, pending-context cleanup) is effectively bypassed.

V3 action:

- Introduce explicit back event router in consumer (`dispatch` -> `back_handler`, `resume` -> `back_resume_handler`, `cancel` -> `back_cancel_handler`).

#### B) Cancellation callback path is weakly wired

Observed:

- `back_handler` supports `fsm_state` cancellation checks.
- Active runtime call sites do not pass `fsm_state` into `back_handler`.

Risk:

- Cooperative cancellation may not interrupt running back loops as intended.

V3 action:

- Pass canonical cancellation token/context explicitly from FSM->Back via envelope/task lease, not optional handler arg.

#### C) Back pending-context helpers appear underused

Observed:

- `store_pending_context` / `_get_pending_context` / `_clear_pending_context` exist.
- Runtime path relies more on FSM-side suspension context and resume_context injection.

Risk:

- Two partial resume designs can drift and create maintenance bugs.

V3 action:

- Keep one resume design: ledger-backed `resume_context` contract as source of truth.

### 14.5 Actor folder keep/change summary

Keep:

- Front mode-driven prompt assembly + strict post-loop emission ordering.
- Back executor identity separation and tiered tools.
- Structured emit helpers for task/tool/artifact events.

Change:

1. Add explicit Back mailbox topic router in consumer.
2. Make cancel/resume context mandatory protocol fields, not optional side params.
3. Remove duplicate/legacy resume storage paths after canonicalization.
4. Add actor-level conformance tests for emission ordering and topic-specific handler routing.

### 14.6 Minimum actor conformance tests

1. Front emits `task.dispatch` before `final.response` for mixed responses.
2. Back `task.resume` envelope is routed to resume handler (not generic dispatch handler).
3. Cancel during long back execution trips cancellation check and yields failed(cancelled).
4. HITL_RESOLVE emits exactly one resume with valid resolution schema.

---

## 15) Deep Review: `poc/k1_poc/react`

Scope reviewed end-to-end:

- `poc/k1_poc/react/__init__.py`
- `poc/k1_poc/react/history.py`
- `poc/k1_poc/react/loop.py`

### 15.1 Why this folder is critical

- `react/loop.py` is the shared cognitive execution loop for both Front and Back.
- Any termination, retry, streaming, or tool-execution bug here affects all conversational and task flows.

### 15.2 What is strong (keep)

- Single shared loop with actor-specific termination semantics is clean and maintainable.
- Validation hook (`LLMOutputValidator`) is integrated before tool execution.
- Degenerate-response handling and fallback paths are explicit.
- Front streaming path is integrated via `generate_stream` with fallback to non-stream.
- Capturing `dispatch_task` outputs into `dispatched_tasks` cleanly supports post-loop event emission in Front.

### 15.3 Confirmed behavior details

- Front termination: text-without-tools returns `ReactResult(status="complete", text=...)`.
- Back termination: requires `submit_result` tool call; plain text from Back is treated as non-terminal.
- Last-iteration behavior: Front forces text-only (no tools), and Back adds explicit nudge to call `submit_result`.
- Non-terminal tool calls are executed via `asyncio.gather` in parallel per iteration.

### 15.4 Confirmed high-priority gaps

#### A) Parallel execution policy mismatch with task safety documentation

Observed:

- `react/loop.py` executes non-terminal tools in parallel (`asyncio.gather`).
- `task/parallel_safety.py` module doc still states POC react loop is sequential.

Risk:

- Safety assumptions may drift, especially for side-effect or order-dependent tools.

V3 action:

- Unify policy: either (1) classify and enforce safe parallel groups, or (2) revert to sequential until explicit safety classifier is wired into `react_loop`.

#### B) Back cancellation depends on optional external callback context

Observed:

- Cancellation checks in loop rely on callback input from caller.
- Active runtime wiring currently does not consistently pass cancel state into Back execution path.

Risk:

- Cancellation can appear accepted at protocol layer but not stop in-flight execution promptly.

V3 action:

- Make cancellation context mandatory in back execution contract (lease/token in event payload).

#### C) Mixed fallback strategy can hide root-cause regressions

Observed:

- Loop has multiple resilience fallbacks (degenerate + budget + mixed-text recovery).

Risk:

- User experience stays alive, but latent model/tool regressions may remain unnoticed without metrics.

V3 action:

- Add explicit counters/events for fallback-path usage and set alert thresholds.

### 15.5 React/Actors combined priority view

Priority 0 (must fix first):

1. Back mailbox topic router to ensure `resume` and `cancel` hit specialized handlers.
2. Mandatory cancellation context propagation into back loop.
3. Parallel tool policy consistency between `react/loop.py` and `task/parallel_safety.py` assumptions.

Priority 1:

1. Remove duplicate resume-context pathways and standardize on one contract.
2. Add actor+react conformance tests for ordering, cancellation, resume, and parallel safety.

Priority 2:

1. Telemetry for fallback-path frequencies (`degenerate`, `budget_exhausted`, forced-text retries).
2. Mode-specific quality metrics for Front (`STANDARD`, `PRESENT`, `WEAVE`, `HITL_*`).

### 15.6 Immediate react conformance tests

1. Front degenerate response recovery path emits final response exactly once.
2. Back text-without-tools does not terminate and eventually reaches submit_result or budget exhaustion deterministically.
3. Parallel tool execution does not reorder side-effect tools (or is blocked by policy).
4. Validator rejection path never executes disallowed tool names.

---

## 16) SessionState Utilization Audit (`poc/k1_poc/sessionstate` + callsites)

Audit scope reviewed:

- `sessionstate/sections/*`
- `sessionstate/manager.py`, `sessionstate/factory.py`, `sessionstate/adapters/*`
- Runtime callsites in `tools/implementations.py`, `actors/front.py`, `actors/back.py`, `fsm/controller.py`, `fsm/task_bridge.py`, `kernel/bootstrap.py`, `demo/coordinator.py`, `prompt/builder.py`

### 16.1 Section inventory vs actual runtime usage

Defined sections (15):

- HOT: `control`, `beliefs_active`, `scoreboard`, `history_active`, `clarifications`, `affective_now`, `narrative_active`, `meta`, `task_state`, `task_artifacts`
- WARM: `beliefs_history`, `history_recent`, `persona`, `telemetry`, `artifacts_warm`

Observed runtime usage pattern:

- Frequently written by LLM cognitive tools: `beliefs_active`, `scoreboard`, `clarifications`, `narrative_active`, `affective_now`
- Written by FSM history bridge: `history_active`
- Written by demo setup: `persona`
- Read often but weakly/indirectly updated: `control`, `task_state`, `task_artifacts`
- Mostly lifecycle/migration internal, not conversation-updated: `meta`, `beliefs_history`, `history_recent`, `telemetry`, `artifacts_warm`

### 16.2 Read/write ownership matrix (actual behavior)

| Section | Read by | Written by (actual) | Notes |
| --- | --- | --- | --- |
| `beliefs_active` | Front, Back, tools, prompt flows | `update_beliefs`, `promote_belief` | Active and healthy |
| `scoreboard` | Front/FSM/Back | `update_scoreboard` | Active and healthy |
| `clarifications` | Front/tools | `update_clarifications` | Active and healthy |
| `narrative_active` | Front/FSM/tools | `update_narrative`, FSM `record_turn()` | Active and healthy |
| `affective_now` | Front/tools | `refine_affect` | Active and healthy |
| `history_active` | Front/Back | FSM history sink `add_turn()` | Active and healthy |
| `persona` | Front/Back | Demo coordinator `set_preference()` | Used, mostly bootstrap-time |
| `task_state` | Front/Back/FSM | FSM `TaskBridge` (but not clearly SS-bound) | High drift risk |
| `task_artifacts` | Front/Back/FSM | FSM `TaskBridge` (but not clearly SS-bound) | High drift risk |
| `control` | Front/Back/prompt mode logic | `ConciergeControlExtension` (separate object) | High drift risk |
| `meta` | Session internals | Internal only | Not LLM-oriented |
| `beliefs_history` | Session migration/eviction | Migration/demotion | Cold path |
| `history_recent` | Session migration/eviction | Migration/demotion | Cold path |
| `telemetry` | Session internals | Mostly internal operations | Underused by runtime actors |
| `artifacts_warm` | Session migration/eviction | Demotion from `task_artifacts` | Cold path |

### 16.3 Root causes of underutilization

1. **Tool writes bypass manager/writer path**

- Front cognitive tools mutate sections directly via `ctx.session_manager.get_section(...).<method>()`.
- This bypasses `SessionStateManager.mutate()` and bypasses `IWriterPort` (`request_mutation` / `batch_mutations`) in runtime flow.

1. **Single-writer contract exists but is not runtime-enforced end-to-end**

- `manager.mutate()` + `DirectWriterAdapter` + writer batch API exist.
- Runtime callsites do not use `request_mutation()` / `batch_mutations()`; direct section mutation dominates.

1. **Control/task state split-brain risk**

- FSM uses `ConciergeControlExtension` and `TaskBridge` as local objects.
- Front/Back read `control` / `task_state` / `task_artifacts` from SessionState sections.
- `set_session_state()` currently attaches SS for reads; it does not clearly rebind FSM extension/bridge to SS section instances.

1. **Prompt builder SS read config is mostly declarative today**

- `SS_READ_CONFIGS` is rich, but `DynamicPromptBuilder` marks stage 8 as placeholder.
- Front currently builds prompt context mainly via manual extractors, not a full config-driven section read pipeline.

1. **Warm sections are designed as pressure/archive layers, not conversationally authored**

- `beliefs_history`, `history_recent`, `artifacts_warm`, `telemetry`, `meta` are mostly lifecycle/migration internals.
- This is expected, but it means “all sections” should not be interpreted as “all LLM-writable.”

### 16.4 Can the LLM write all sections in one tool call?

Short answer: **not safely with current contracts**.

- Current Front tools are section-specific and mutate direct section objects.
- No runtime tool currently performs validated multi-section write through writer batch API.
- `DirectWriterAdapter.batch_mutations()` exists, but semantics are **not atomic by default** (partial success possible).

### 16.5 Recommended V3 write model (single-call bundle, safe)

Add one Front tool:

- `update_session_bundle` (single tool call, structured payload)

Payload shape:

- `mutations: [{section, operation, data, estimated_bytes}]`
- `idempotency_key`
- `stop_on_rejection` (default `true`)

Execution path:

1. Tool builds `MutationRequest` list.
2. Tool calls `writer_port.batch_mutations(BatchRequest(...))`.
3. Reject entire bundle on first failure for conversational consistency.
4. Emit one summarized result object back to ReAct loop.

Important constraints:

- Keep **LLM-writable allowlist** limited to cognitive sections:
  - `beliefs_active`, `scoreboard`, `clarifications`, `narrative_active`, `affective_now`.
- Keep FSM/system-owned sections non-LLM writable:
  - `control`, `task_state`, `task_artifacts`, `meta`, warm/archive sections.

Optional enhancement (true atomicity):

- Add a transactional writer adapter path (all-or-nothing) instead of current partial-success batch semantics.

### 16.6 Immediate fixes before adding bundle tool

1. Rebind FSM `TaskBridge` to real SessionState `task_state` + `task_artifacts` sections.
2. Mirror/persist FSM control extension state into SessionState `control` (or replace extension with section-backed implementation).
3. Route Front cognitive writes through writer/manager path (not direct section mutation).
4. Make prompt section ingestion truly config-driven (use `SS_READ_CONFIGS` as executable read plan, not placeholder).

---

## 17) Fit to K1 Skeleton + Tiering Decision (UltraBERT-first)

Question answered: **yes** — initial pass can and should be done by UltraBERT.

### 17.1 How current POC fits the larger architecture

- `Front` maps to conversational reasoning + cognitive SessionState updates.
- `Back` maps to execution for dispatched work.
- `FSM` remains the authoritative event router and sequencing layer.
- `Orchestrator/Planner` are the MEDIUM/HIGH path targets in the full K1 skeleton.

### 17.2 ACKING removal is fine if we preserve ACKING responsibilities

We keep ACKING removed as a separate FSM state, but retain its responsibilities as a
**micro-phase inside `DISPATCHING`**:

1. Deterministic initial pass (UltraBERT heads).
2. Complexity + domain + safety decision.
3. Optional short acknowledgement emission.
4. Route to LOW / MEDIUM / HIGH path.

This keeps Front/Back interoperability simpler while preserving the architecture intent.

### 17.3 Tier decision contract (recommended)

Tier must be decided before Front dispatch payload is finalized:

- `LOW`: Front + Back direct execution path.
- `MEDIUM`: Front + Back with Orchestrator-managed execution path.
- `HIGH`: Orchestrator + Planner planning path before execution.

### 17.4 UltraBERT-first policy (authoritative)

For each user turn:

1. Run UltraBERT deterministic pass first (intent/domain/safety/complexity).
2. Persist these outputs to SessionState `control` (single source of truth).
3. Front reads from `control` and uses that tier for `dispatch_task`.
4. FSM routes by tier through the single routing authority.

### 17.5 Immediate implementation note

Current POC has tier contracts and router structure, but to fully match the skeleton:

1. Ensure UltraBERT complexity tier is persisted to SessionState `control` each turn.
2. Ensure Front dispatch always uses that persisted tier (not implicit defaults).
3. Replace HIGH-tier fail-fast branch with real Orchestrator/Planner handoff.

### 17.6 UltraBERT + SessionState feed at conversation start

At session start and turn-0, feed **deterministic UltraBERT outputs** into SessionState before Front prompt build.

Minimum feed contract (turn bootstrap):

1. `control` (authoritative routing context)
   - `intent_classification.primary_intent`
   - `intent_classification.all_intents[]`
   - `domain_context.primary_domain`
   - `domain_context.active_domains[]`
   - `safety.band` (GREEN/AMBER/RED/CRISIS)
   - `complexity_tier` (LOW/MEDIUM/HIGH)

2. `scoreboard` (discourse anchors)
   - `last_user_intent`
   - `last_user_intent_confidence`
   - referent seed entries from NER (when available)
   - salience seeds for detected entities

3. `affective_now` (tone and empathy seed)
   - `current_emotion`
   - `intensity`
   - `valence`
   - `arousal`
   - `confidence`

4. Optional initial enrichments (non-blocking)
   - temporal parse hints (for follow-up scheduling tools)
   - relation/entity links (family NER/relation outputs)

Practical rule:

- If only one write path is available, prioritize `control` first, then `affective_now`, then `scoreboard`.
- Front should not dispatch tasks until `control.complexity_tier` and `control.safety.band` are available for that turn.

Turn-0 bootstrap example (conceptual payload):

```json
{
  "control": {
    "intent_classification": {
      "primary_intent": "scheduling",
      "all_intents": ["scheduling", "family_coordination"]
    },
    "domain_context": {
      "primary_domain": "health",
      "active_domains": ["health"]
    },
    "safety": { "band": "GREEN" },
    "complexity_tier": "MEDIUM"
  },
  "scoreboard": {
    "last_user_intent": "scheduling",
    "last_user_intent_confidence": 0.91,
    "referents": [
      { "text": "dentist", "entity_id": "provider:dental", "entity_type": "provider" }
    ]
  },
  "affective_now": {
    "current_emotion": "neutral",
    "intensity": 0.35,
    "valence": 0.1,
    "arousal": 0.4,
    "confidence": 0.82
  }
}
```

Why this works with current architecture:

- Matches UltraBERT head outputs documented in modeling README (intent/ingress/safety/emotion/NER).
- Matches current Front read needs (`control`, `scoreboard`, `affective_now`) before tool reasoning.
- Keeps ACKING removed while preserving ACKING responsibilities inside DISPATCHING.
