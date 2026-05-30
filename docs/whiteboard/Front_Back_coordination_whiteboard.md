# Whiteboard - Front/Back Coordination Audit

**Date:** 2026-05-27
**Branch:** `feature/prompt-architecture-refactor`
**Scope:** Concierge Front actor, Back actor, FSM controller, HIL service, weave delivery, and the runtime glue that makes separate actors behave like one assistant.

**Core question:** Are Front and Back actually separate in execution while coherent as one user-facing mind? If not, where are the gaps, race windows, deprecated paths, or unconnected wiring?

---

## Current Mental Model

Front is the family-facing voice. It receives user input, builds the dynamic prompt, interprets cognitive SessionState, chooses whether to answer directly or dispatch work, and presents HIL/weave/result output.

Back is the executor. It receives structured task dispatches, runs task-oriented ReAct loops with Back tools, asks for human help through the unified HIL port, and emits structured result/failure/suspension events. Back should not write user-visible prose as the final family voice; it should provide typed facts, artifacts, confidence, blockers, and presentation guidance.

The FSM/controller is the unifier. It owns turn number, FrontLock, task state, idempotency, HIL correlation, Back result ownership, weave timing, history writes, and the routing choices that make the split actors feel like one coherent conversation.

The bus and mailboxes provide separation. Pub/sub topics feed the FSM; point-to-point mailbox delivery sends an envelope to Front or Back. The runtime has separate Front and Back consumer tasks, so a Back await should not starve Front presentation.

---

## Verified Architecture Facts

### A1 - Front and Back mailboxes are split

Current runtime starts independent Front and Back consumer tasks in [k1/concierge/session.py](../../k1/concierge/session.py#L112). This addresses the old starvation class where a Back HIL await could block Front from presenting the HIL prompt.

Evidence:

- `start()` creates `_front_consumer_task` and `_back_consumer_task`.
- `_front_consumer()` calls `front_handler(...)`.
- `_back_consumer()` calls `route_back_envelope(..., hil_port=self._hil_port, ...)`.
- `_mailbox_consumer()` is now legacy compatibility that gathers both consumers.

Status: **Current architecture is correct for Front-vs-Back separation.**

### A2 - FSM is the coordination authority

The controller subscribes to user input, final response, task dispatch/complete/failed/cancel/suspend/resume, unified HIL request, weave batch, UI typing, and config update topics in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1316).

The FSM owns:

- Normal user turn routing and arbiter metadata enrichment in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2468).
- Task dispatch registration and routing in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2776).
- Unified HIL request presentation state in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4160).
- Task completion cleanup and weave decision routing in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3118).
- Response-final state transitions, FrontLock release, and turn finalization in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4465).

Status: **Correct design center. The actors are not peers negotiating state; the FSM is the single coordination boundary.**

### A3 - Front dispatches Back work through structured tool output

`dispatch_task` is a Front tool that returns structured `_dispatch` data and does not itself publish bus events. See [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1225).

Front consumes the ReAct result and publishes `k1.orchestration.task.dispatch.v1` before `response.final` in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1649). That ordering matters: dispatch must reach the FSM before the user-visible final response closes the turn.

Status: **Current ordering is intentional and good.**

### A4 - Back inbound routing is topic-aware

The runtime calls `route_back_envelope(...)`, which dispatches by envelope topic to `back_handler`, `back_resume_handler`, or `back_cancel_handler`; unknown topics are dead-lettered. See [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L1660).

Status: **The old claim that every Back envelope goes through generic `back_handler` is stale.**

### A5 - Unified HIL presentation ack exists

Front emits `TOPIC_HIL_PRESENTED` when it has actually rendered a HIL question in chat. See [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L83) and [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1729).

`HumanInTheLoopService` subscribes to `TOPIC_HIL_PRESENTED` and resolves a presentation future in [k1/hil/service.py](../../k1/hil/service.py#L112) and [k1/hil/service.py](../../k1/hil/service.py#L552).

Status: **The old claim that presentation ack is missing is stale. The remaining issue is config/wiring, not absence.**

### A6 - UI typing and weave decision topics are guard-table aware

`TOPIC_UI_TYPING` and `TOPIC_WEAVE_DECIDED` are in the transition table as observe-only topics. See [k1/concierge/fsm/transition_table.py](../../k1/concierge/fsm/transition_table.py#L280).

Status: **The old dead-letter-storm concern for these topics is stale.**

---

## Lane 1 - Front Dispatches Task To Back

### Lane 1 Flow

1. User input arrives on `k1.session.user.input.v1`.
2. FSM `_on_user_input` starts or routes the turn in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1828).
3. FSM `_route_user_turn` writes session context, classifies with arbiter, emits `intent.arbitrated`, enriches the envelope, and delivers it to Front in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2468).
4. Runtime Front consumer invokes `front_handler` in [k1/concierge/session.py](../../k1/concierge/session.py#L367).
5. Front builds prompt/context and runs the ReAct loop in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1145).
6. If the LLM calls `dispatch_task`, the tool returns `_dispatch` from [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1225).
7. Front publishes `task.dispatch` before `response.final` in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1649).
8. FSM `_on_task_dispatch` registers the task, cancel token, running handle, task bridge state, and routes by tier in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2776).
9. FSM `_route_via_orchestrator` either routes LOW/MEDIUM directly to Back, or HIGH through orchestrator if present in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2855).
10. Back consumer calls `route_back_envelope`; `task.dispatch` invokes `back_handler` in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L1660).

### Lane 1 Strengths

- Dispatch payload is structured, not freeform text.
- FSM injects canonical `task_id`, trace/session metadata, referents, narrative thread, and turn-state overlay before Back sees the task.
- Final response ordering prevents the old race where Front closes the turn before the task dispatch is registered.
- Unknown Back topics are observable via dead-letter instead of silent drop.

### Lane 1 Gaps

See issue register: `FB-RUNTIME-001`, `FB-RUNTIME-002`, `FB-BACKPOOL-001`, `FB-BACKPOOL-002`, `FB-BACKPOOL-003`, `FB-BACKPOOL-004`, `FB-BACKPOOL-005`, `FB-HIGH-001`, `FB-CANCEL-001`, `FB-CANCEL-002`, `FB-GROUNDING-001`.

---

## Lane 2 - Back HIL To Front And Back Resume

### Lane 2 Unified Live Flow

1. Back ReAct returns `ReactResult(status="suspended")` or `submit_result(result_type="needs_human")` semantics.
2. `_resolve_needs_human_in_process` detects unified `hil_port.needs_human` and builds a `NeedsHumanRequest` in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L659).
3. `HumanInTheLoopService.needs_human` publishes a `HILEnvelope` on `k1.hil.request.v1` and awaits a correlated response future in [k1/hil/service.py](../../k1/hil/service.py#L180).
4. FSM `_on_hil_request` parses the envelope, binds it to a Back task when `task_id` exists, persists `pending_hil_data.envelope`, writes history/observability, and delivers the request to Front in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4160).
5. Front HITL_RELAY unwraps the HIL envelope and renders the question via chat in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L520).
6. Front publishes `HILPresented` after text is actually emitted in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1729).
7. User answers while FSM is in `CLARIFYING_WORKER`; next input routes as HITL_RESOLVE from [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1878).
8. Front builds and publishes `HILResponseEnvelope` in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1763).
9. `HumanInTheLoopService._on_response` resolves the pending future in [k1/hil/service.py](../../k1/hil/service.py#L590).
10. Back resumes in-process by appending an HIL response message and re-entering the Back ReAct loop in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L727).

### Lane 2 Legacy/Recovery Flow

`_on_task_suspended` and `_on_task_resume` still exist for no-HIL-port fallback, legacy tests, and crash recovery compatibility. They are explicitly documented as legacy/recovery in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3546) and [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3750).

### Lane 2 Strengths

- Unified HIL correlation uses `hil_request_id` rather than ambiguous task-only matching.
- Front preserves the original HIL envelope under `_hil_envelope`, so HITL_RESOLVE can build a properly correlated response.
- FSM stores pending HIL data on the task bridge so Front can find suspended tasks by task state, not only by transient service internals.
- Front emits presentation ack for chat HIL.
- Legacy `task.resume` is suppressed for unified HIL to avoid double resume.

### Lane 2 Gaps

See issue register: `FB-HIL-001`, `FB-HIL-002`, `FB-HIL-003`, `FB-HIL-004`, `FB-HIL-005`, `FB-HIL-006`, `FB-BACKPOOL-003`, `FB-BACKPOOL-005`, `FB-CANCEL-002`.

---

## Lane 3 - Back Result To Front Weave/Present

### Lane 3 Flow

1. Back emits `task.complete` through `_emit_back_result` in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L783).
2. FSM `_on_task_complete` handles cancel dedup, same-turn suppression, BackPool release if wired, task bridge completion, history, running-task cleanup, and HIL cleanup in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3118).
3. If `WeavePolicy` is wired, `_on_task_complete_adaptive` enqueues the result, collects a `WeaveSignal`, gets a `WeaveDecision`, emits `weave.decided`, calls OPP delivery strategy if present, and applies the weave decision in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3284).
4. `WeavePolicy.decide` considers FSM state, urgency, typing, idle, affect, HITL pending, pending count, and BackPool utilization in [k1/concierge/protocols/weave_policy.py](../../k1/concierge/protocols/weave_policy.py#L790).
5. FSM `_apply_weave_decision` maps IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS to controller side effects in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1165).
6. Flush helpers build a synthetic weave envelope and deliver to Front in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4947).
7. Front WEAVE builds a `WeavePresentationFrame` from payload/pending state in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L515).

### Lane 3 Strengths

- `WeavePolicy.decide()` is pure; side effects live in controller application methods.
- Result ownership is centralized around `FSMTurnState.pending_results` and `deferred_results` in the current active path.
- HIL pending suppresses non-critical weave delivery.
- Same-turn completion is not dropped; it is stored for proactive delivery or chained into the current response.
- Synthetic weave response parenting uses `parent_id` rather than synthetic envelope id to avoid causal-buffer holds.

### Lane 3 Gaps

See issue register: `FB-WEAVE-001`, `FB-WEAVE-002`, `FB-WEAVE-003`, `FB-WEAVE-004`, `FB-RUNTIME-001`, `FB-BACKPOOL-002`, `FB-BACKPOOL-004`.

---

## BackPool Deep Audit - 2026-05-27

**Conclusion:** BackPool is **not wired end-to-end** in the live Concierge runtime. The codebase has the worker pool primitives, task leases, router, ready queue, topics, guard-table entries, event classes, and a focused runtime-wiring test file. But the canonical `KernelConfig` -> `ConciergeConfig` -> `ConciergeFactory` -> `ConciergeRuntime` path does not construct or expose the pool, and the Back consumer still awaits the Back handler inline.

### Expected Pool Flow

1. Kernel/Concierge config exposes BackPool sizing, per-session limit, lease TTL, reclaim interval, dependency-ordering, renewal, and grace-period fields.
2. Factory constructs `BackPool`, `BackTopicRouter`, and `ReadyQueue` from those config values.
3. Factory wires BackPool callbacks to publish `TOPIC_BACKPOOL_WORKER_ACQUIRED`, `TOPIC_BACKPOOL_WORKER_RELEASED`, and `TOPIC_TASK_LEASED`.
4. Factory calls `fsm.set_back_pool(back_pool)` so arbiter and weave signals see real pool utilization.
5. Runtime stores and exposes `back_pool`, `back_topic_router`, and `ready_queue`.
6. Runtime starts/stops the BackPool lease watcher with the runtime lifecycle.
7. Runtime Back consumer routes cancel synchronously through `BackTopicRouter`, and routes dispatch/resume/clarification through ReadyQueue -> BackPool acquire -> worker `asyncio.Task` -> handler.
8. Runtime passes the FSM `CancellationToken` into `BackPool.acquire_worker(...)`, then passes the same token into Back handlers.
9. Runtime drains overflow and ReadyQueue when workers release or dependencies complete.
10. FSM completion/failure/cancel/HIL suspension paths release, cancel, suspend, or resume leases exactly once.

### Live Source Facts

- Pool primitives exist: `BackPool`, `BackPoolConfig`, worker slots, overflow queue, lease watcher, and state snapshots in [k1/concierge/actors/back_pool.py](../../k1/concierge/actors/back_pool.py#L42).
- Task lease supports `ACTIVE`, `SUSPENDED`, `EXPIRED`, `RELEASED`, and `CANCELLED`, including explicit `suspend()` and `resume()` methods in [k1/concierge/protocols/task_lease.py](../../k1/concierge/protocols/task_lease.py#L35).
- Topic router exists and knows dispatch/resume/cancel/clarification routing in [k1/concierge/actors/back_router.py](../../k1/concierge/actors/back_router.py#L56).
- ReadyQueue exists and can enqueue, release, fail dependencies, and expose queue state in [k1/concierge/actors/ready_queue.py](../../k1/concierge/actors/ready_queue.py#L42).
- BackPool topics and guard-table entries exist for worker acquired/released and task leased in [k1/concierge/bus/topics.py](../../k1/concierge/bus/topics.py#L126) and [k1/concierge/fsm/transition_table.py](../../k1/concierge/fsm/transition_table.py#L277).
- Event classes and registry entries exist for pool lifecycle events in [k1/concierge/events/pool.py](../../k1/concierge/events/pool.py#L39) and [k1/concierge/events/registry.py](../../k1/concierge/events/registry.py#L102).
- Config loader/defaults contain a nested actors/back-pool config, but canonical `KernelConfig` and `ConciergeConfig` used by `KernelService`/`ConciergeFactory` do not expose the `backpool_*` fields expected by tests.
- `ConciergeFactory._construct_concierge(...)` wires ledger, SessionState, tools, HIL, weave, activity tracker, dead letters, and orchestrator, but it does not construct `BackPool`, `BackTopicRouter`, or `ReadyQueue` and does not call `fsm.set_back_pool(...)`.
- `ConciergeRuntime.__init__(...)` has no `back_pool`, `back_topic_router`, or `ready_queue` parameters/properties, and `_back_consumer()` still awaits `route_back_envelope(...)` inline in [k1/concierge/session.py](../../k1/concierge/session.py#L393).
- `ConciergeController.set_back_pool(...)` exists and `build_inflight_context(...)`/`WeaveSignal.from_runtime(...)` can read it, but the field remains `None` in live construction.
- `_on_task_complete(...)` releases `self._back_pool` if present, but ReadyQueue notification and dependent auto-dispatch are explicitly placeholders in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3118).

### Targeted Test Result

Focused command run during this audit:

```powershell
pytest tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py -v
```

Result: **0 passed, 20 reported failures**. The failures are not behavioral edge cases; they show missing wiring surfaces:

- `ConciergeConfig.__init__()` rejects `backpool_size`.
- `KernelConfig.__init__()` rejects `backpool_size`.
- `ConciergeRuntime.__init__()` rejects `back_pool`.
- `ConciergeRuntime` has no `back_pool` attribute.

### Practical Runtime Effect

Front can still dispatch Back tasks correctly, and Front can still present while Back awaits HIL because Front and Back mailboxes are split. But Back itself is still effectively a single awaited consumer path. There is no live pool of Back workers, no worker lease lifecycle, no pool overflow drain, no ReadyQueue dependency ordering, no pool-aware cancel bypass, and no real BackPool utilization signal for arbiter/weave decisions.

---

## Issue Register

Severity legend:

- **P0:** Can break user-visible correctness, hang an interaction, lose HIL/cancel state, or cause unsafe autonomy.
- **P1:** Architecture mismatch or race likely to create confusing behavior under normal use.
- **P2:** Dead weight, misleading status, partial wiring, or maintainability risk.
- **P3:** Cleanup/documentation/test coverage item.

### FB-HIL-001 - HIL service durability is weaker than the live design claims

**Severity:** P0
**Status:** Open
**Finding:** `HumanInTheLoopService` can suspend before publishing if a `SuspensionManager` is provided, and can write request/resolved/timeout events if a ledger adapter has a writer. Current kernel/session construction passes `suspension_mgr=None` and `HILLedgerAdapter(None)`.

Evidence:

- Kernel global HIL service constructed with `suspension_mgr=None` and `HILLedgerAdapter(None)` in [k1/kernel/service.py](../../k1/kernel/service.py#L1710).
- Session HIL service constructed with `suspension_mgr=None` and `HILLedgerAdapter(None)` in [k1/kernel/service.py](../../k1/kernel/service.py#L2497).
- HIL ledger adapter is no-op with `writer=None` in [k1/hil/ledger.py](../../k1/hil/ledger.py#L13).
- Service only calls `suspension_mgr.suspend(...)` when non-null in [k1/hil/service.py](../../k1/hil/service.py#L180).

Impact:

- Request and response futures live in memory only.
- A process restart can lose the service-owned pending future even though the FSM may have recorded pending HIL data after receiving the request.
- The design statement "suspend before publish for crash recovery" is not true in the current production wiring.

Preferred fix:

- Wire the session FSM `SuspensionManager` or a kernel-level HIL suspension store into `HumanInTheLoopService`.
- Pass a real HIL ledger writer/adapter when the session ledger is enabled.
- Add a focused recovery test for `needs_human`: publish request, persist before Front answer, simulate restart/replay, re-present or resolve deterministically.

### FB-HIL-002 - Presentation-aware HIL timeout exists but is disabled by default and not surfaced in kernel config

**Severity:** P1
**Status:** Open/partial
**Finding:** The two-phase timer is implemented, but `require_presentation_ack` defaults to false and kernel config does not expose/pass it.

Evidence:

- `HILConfig.require_presentation_ack: bool = False` in [k1/hil/config.py](../../k1/hil/config.py#L43).
- `_request()` only creates `_pending_presentation[hil_id]` when `require_ack` is true in [k1/hil/service.py](../../k1/hil/service.py#L424).
- Kernel config exposes per-kind timeouts and synthesis/audit flags, but not `require_presentation_ack` or `presentation_timeout_ms`, in [k1/concierge/config/kernel.py](../../k1/concierge/config/kernel.py#L140).
- Kernel service constructs `HILConfig(...)` without those fields in [k1/kernel/service.py](../../k1/kernel/service.py#L1710) and [k1/kernel/service.py](../../k1/kernel/service.py#L2497).

Impact:

- Human-response timeout currently starts at request publish, not at actual user presentation, unless code is manually configured elsewhere.
- Slow Front rendering or queued Front delivery can consume the user's answer window.

Preferred fix:

- Surface `hil_require_presentation_ack` and `hil_presentation_timeout_ms` in kernel config.
- Only enable after `FB-HIL-003` is fixed for direct widget HIL.

### FB-HIL-003 - Direct widget HIL lane does not appear to emit `HILPresented`

**Severity:** P1
**Status:** Open
**Finding:** Inline HIL widget kinds (`capability_gate`, `approval`, `override`) bypass Front HITL_RELAY and go straight to browser widget presentation. The browser/web path forwards requests and sends responses, but this audit did not find a widget-lane publish of `TOPIC_HIL_PRESENTED`.

Evidence:

- FSM skips Front HITL_RELAY for `_INLINE_HIL_WIDGET_KINDS` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4261).
- Web coordinator forwards `TOPIC_HIL_REQUEST` to browser in [ui/web/coordinator.py](../../ui/web/coordinator.py#L814).
- Browser renders widget and sends `hil_response` in [ui/web/static/app.js](../../ui/web/static/app.js#L968).
- Browser handles incoming `hil_presented` messages for chat input arming in [ui/web/static/app.js](../../ui/web/static/app.js#L950), but that is consumption, not a widget ack publish.

Impact:

- If `require_presentation_ack=True`, approval/capability/override HIL may presentation-timeout even though the widget is visible.
- If the flag remains false, widget lane works but human timeout starts before actual widget render.

Preferred fix:

- When the browser renders an inline HIL widget, send a `hil_presented` event back to coordinator.
- Coordinator should publish `TOPIC_HIL_PRESENTED` with `hil_request_id`, kind, task_id, channel, and timestamp.
- Add a targeted widget-lane test before enabling presentation ack globally.

### FB-HIL-004 - Unified and legacy HIL paths coexist and can drift

**Severity:** P1
**Status:** Open/accepted compatibility
**Finding:** `_on_task_suspended`, `_on_task_resume`, `back_resume_handler`, and legacy bridge envelope logic remain for recovery/tests/no-port fallback. They are documented as compatibility, but they still carry real behavior and can diverge from the unified HIL path.

Evidence:

- `_on_task_suspended` is documented as legacy/recovery/no-HIL-service fallback in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3546).
- `_on_task_resume` is documented as legacy/recovery fallback in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3750).
- Front still has a legacy `emit_task_resume` branch when no unified envelope exists in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1825).
- Back still emits legacy `task.suspended` when no HIL port is callable in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L678).

Impact:

- More than one HIL lifecycle can be exercised by tests and runtime fallbacks.
- Bugs can be fixed in unified path while legacy path keeps old behavior.
- Front duplicate/stale HIL prompt handling remains fragile if both paths accidentally fire.

Preferred fix:

- Keep legacy path only under explicit feature/test flag or recovery boundary.
- Add assertions/tests that unified HIL never also emits `task.resume` or legacy `task.suspended` when `hil_port` is wired.
- Eventually retire Back resume round-trip after recovery model is fully service/FSM durable.

### FB-HIL-005 - Back consumer can still block other Back envelopes while awaiting HIL

**Severity:** P1
**Status:** Open
**Finding:** Split Front/Back consumers prevent Front starvation, but `_back_consumer()` still awaits `route_back_envelope(...)` inline. If Back is awaiting `hil_port.needs_human()`, the Back consumer is occupied and cannot process other Back mailbox envelopes until that await resolves.

Evidence:

- `_back_consumer()` awaits `route_back_envelope(...)` directly in [k1/concierge/session.py](../../k1/concierge/session.py#L407).
- Unified HIL path awaits `needs_human(req)` inside Back handling in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L727).
- BackPool/BackTopicRouter exist but are not wired into the production runtime path; see `FB-RUNTIME-001`.

Impact:

- Front can present HIL, but Back-side cancel/resume/second task handling may be delayed behind the awaiting Back handler.
- The architecture claim "BackPool handles parallel workers/cancel immediately" is not true in current runtime wiring.

Preferred fix:

- Wire BackPool/BackTopicRouter so Back dispatch/resume run in task workers and cancel bypasses pool synchronously.
- Or explicitly document the single Back worker invariant and avoid claiming runtime parallelism.

### FB-HIL-006 - HIL pending state has multiple mirrors

**Severity:** P2
**Status:** Open/managed by coherence checks
**Finding:** Pending HIL can exist in `_pending_hil_subtasks`, `task_state.pending_hil_data`, `SuspensionManager`, and `HumanInTheLoopService._pending`. The controller has coherence checks, but source-of-truth boundaries are still complex.

Evidence:

- Controller `_has_pending_hitl()` scans both `_pending_hil_subtasks` and task bridge/task state in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L948).
- Controller `rebuild_pending_hil_from_projection()` rebuilds task state and legacy subtask cache in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L988).
- Controller `_check_hil_state_coherence()` logs divergence in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1028).
- Service pending futures remain private to `HumanInTheLoopService` in [k1/hil/service.py](../../k1/hil/service.py#L100).

Impact:

- Recovery and late-answer behavior can diverge if only one mirror is rebuilt.
- Bugs are more likely when a task terminalizes, times out, or receives duplicate answers.

Preferred fix:

- Declare the canonical durable HIL state explicitly: likely ledger projection plus `task_state.pending_hil_data` for Front presentation.
- Treat service `_pending` as an in-process await cache only.
- Keep coherence checks, but reduce mirror writes after unified durability is wired.

### FB-RUNTIME-001 - Back runtime still runs through the non-pool consumer path

**Severity:** P0/P1
**Status:** Open
**Finding:** BackPool/BackTopicRouter/ReadyQueue primitives exist, but current production factory/runtime path still runs Back envelopes through a single awaited `_back_consumer()` call to `route_back_envelope(...)`. This means the "Back pool of workers" architecture is not live end-to-end.

Evidence:

- `ConciergeRuntime.__init__(...)` has no `back_pool`, `back_topic_router`, or `ready_queue` fields/properties in [k1/concierge/session.py](../../k1/concierge/session.py#L31).
- Runtime `_back_consumer()` imports and awaits `route_back_envelope(...)` directly in [k1/concierge/session.py](../../k1/concierge/session.py#L393).
- `ConciergeFactory._construct_concierge(...)` does not construct `BackPool`, `BackTopicRouter`, or `ReadyQueue`, and it does not call `fsm.set_back_pool(...)` before creating `ConciergeRuntime` in [k1/concierge/factory.py](../../k1/concierge/factory.py#L569).
- `ConciergeController.set_back_pool(...)` exists in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L834), and `_on_task_complete(...)` has release hooks if `_back_pool` is non-null in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3118), but there is no live production attach point.
- Focused test file [tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py](../../tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py) currently reports `0 passed` with failures for missing config/runtime pool surfaces.

Impact:

- Back concurrency, lease expiry, immediate cancel routing, and ready queue behavior are architectural promises but not live runtime behavior.
- WeaveSignal `backpool_utilization` is usually blind because `_back_pool` remains `None`.
- Cancellation and HIL waits can block Back mailbox progress.
- Test coverage is ahead of implementation: the focused wiring test asserts a runtime API that does not exist.

Preferred fix:

- Wire BackPool/BackTopicRouter/ReadyQueue into `ConciergeFactory` and `ConciergeRuntime` as production runtime components.
- Add runtime scheduler methods for queueing, worker acquisition, token binding, overflow drain, and worker release callbacks.
- Keep the current direct `route_back_envelope(...)` function as the handler implementation under the pool worker, not as the mailbox consumer owner.
- Use [tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py](../../tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py) as the targeted acceptance suite; do not run broad kernel tests.

### FB-RUNTIME-002 - Back topic routing exists twice

**Severity:** P2
**Status:** Open
**Finding:** There is a standalone `BackTopicRouter` class and a function-level `route_back_envelope(...)` that performs topic routing. The live runtime uses the function, while docs/plans often describe the class/router/pool path.

Evidence:

- Function router in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L1660).
- Class router in [k1/concierge/actors/back_router.py](../../k1/concierge/actors/back_router.py#L1).
- Runtime `_back_consumer()` imports and calls `route_back_envelope` directly in [k1/concierge/session.py](../../k1/concierge/session.py#L407).

Impact:

- Maintainers may fix one router and not the other.
- Tests can pass against class router while runtime uses function router.

Preferred fix:

- Collapse to one routing boundary or make `route_back_envelope` delegate to `BackTopicRouter`.
- Keep a single routing table and a single set of stats/dead-letter behavior.

### FB-BACKPOOL-001 - Canonical config does not expose BackPool settings

**Severity:** P1
**Status:** Open
**Finding:** BackPool config exists in the config loader/defaults path, but the canonical dataclasses used by `KernelService` and `ConciergeFactory` do not expose the `backpool_*` fields that the focused runtime test expects.

Evidence:

- `KernelConfig` in [k1/concierge/config/kernel.py](../../k1/concierge/config/kernel.py#L28) has no `backpool_size`, `backpool_max_concurrent_per_session`, or `backpool_lease_ttl_s` fields.
- `ConciergeConfig` in [k1/concierge/config/concierge.py](../../k1/concierge/config/concierge.py#L17) has no BackPool fields and `from_kernel_config(...)` does not map any.
- The separate loader config has `BackPoolConfig` in [k1/concierge/config/loader.py](../../k1/concierge/config/loader.py#L332), but that object is not consumed by the factory runtime path.
- Targeted test failures include `TypeError: ConciergeConfig.__init__() got an unexpected keyword argument 'backpool_size'` and `TypeError: KernelConfig.__init__() got an unexpected keyword argument 'backpool_size'`.

Impact:

- Operators cannot configure pool size, per-session concurrency, lease TTL, lease watcher cadence, dependency ordering, renewals, or grace period through the active kernel/factory path.
- Test fixtures and docs are describing a configuration surface that production code does not own.

Preferred fix:

- Add BackPool fields to canonical `KernelConfig` and `ConciergeConfig`, or bridge the loader's nested `actors.back_pool` config into the canonical factory config.
- Update `ConciergeConfig.from_kernel_config(...)` and `for_testing(...)` to carry those values.
- Keep naming consistent; either use flat `backpool_*` everywhere or nested `back_pool.*` everywhere.

### FB-BACKPOOL-002 - Factory does not construct or attach pool/router/queue

**Severity:** P0/P1
**Status:** Open
**Finding:** The factory creates many live Concierge dependencies, but it does not create `BackPool`, `BackTopicRouter`, or `ReadyQueue`, does not attach pool observability callbacks, and does not call `fsm.set_back_pool(...)`.

Evidence:

- Factory `_construct_concierge(...)` wires ledger, SessionState, tools, HIL, weave, activity tracker, dead-letter consumer, orchestrator, and runtime construction in [k1/concierge/factory.py](../../k1/concierge/factory.py#L569).
- The same method creates `ConciergeRuntime(...)` without pool/router/queue arguments in [k1/concierge/factory.py](../../k1/concierge/factory.py#L796).
- `ConciergeController.set_back_pool(...)` exists in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L834), but production `k1/**` search found no caller outside docs/tests.
- Targeted test failures include `AttributeError: 'ConciergeRuntime' object has no attribute 'back_pool'`.

Impact:

- Pool utilization signals in arbiter/weave remain zero/blind.
- Pool lifecycle events cannot be emitted because no pool instance is owned by the session runtime.
- BackPool acceptance tests fail at object construction/attribute lookup before behavioral assertions even run.

Preferred fix:

- In factory step ordering, create `BackPool(BackPoolConfig(...))`, `BackTopicRouter(back_pool)`, and `ReadyQueue()` before runtime creation.
- Attach callbacks that publish `build_backpool_worker_acquired`, `build_backpool_worker_released`, and `build_task_leased`.
- Call `fsm.set_back_pool(back_pool)` before runtime start.
- Pass the pool/router/queue into `ConciergeRuntime` and expose read-only properties.

### FB-BACKPOOL-003 - Runtime Back consumer does not schedule pool workers

**Severity:** P0/P1
**Status:** Open
**Finding:** Runtime has split Front/Back consumer tasks, but the Back side is still a single awaited consumer. There is no live `_enqueue_or_run_back_envelope`, `_schedule_ready_back_envelopes`, `active_back_tasks`, worker binding, overflow drain, or lease watcher task in `ConciergeRuntime`.

Evidence:

- `_back_consumer()` receives one Back envelope and awaits `route_back_envelope(...)` inline in [k1/concierge/session.py](../../k1/concierge/session.py#L393).
- `BackPool.acquire_worker(...)`, `enqueue_overflow(...)`, and `start_lease_watcher(...)` exist in [k1/concierge/actors/back_pool.py](../../k1/concierge/actors/back_pool.py#L243), [k1/concierge/actors/back_pool.py](../../k1/concierge/actors/back_pool.py#L683), and [k1/concierge/actors/back_pool.py](../../k1/concierge/actors/back_pool.py#L543), but runtime does not call them.
- `BackTopicRouter.is_cancel_topic(...)` and `get_cancel_token_for_task(...)` exist in [k1/concierge/actors/back_router.py](../../k1/concierge/actors/back_router.py#L142), but runtime does not use the class router.
- Targeted test failures include `TypeError: ConciergeRuntime.__init__() got an unexpected keyword argument 'back_pool'`, so the runtime scheduler surface expected by tests is absent.

Impact:

- A Back task awaiting HIL no longer blocks Front presentation, but it can still block other Back mailbox work because the Back consumer itself is awaiting the task handler.
- Cancel/resume/second dispatch envelopes can queue behind a long Back handler rather than bypassing or entering a separate worker slot.
- `max_concurrent_per_session` and `pool_size` are not enforceable because no scheduler asks the pool for slots.

Preferred fix:

- Replace direct Back handler await with a scheduler.
- Scheduler requirement: cancel topics route synchronously through `back_cancel_handler` and do not acquire a worker.
- Scheduler requirement: dispatch/resume/clarification enqueue into `ReadyQueue` and then acquire a worker if capacity exists.
- Scheduler requirement: worker tasks call `route_back_envelope(...)` with the shared cancel token.
- Scheduler requirement: done callbacks release workers and drain overflow/ready queues.
- Start and stop the BackPool lease watcher in `ConciergeRuntime.start()` / `stop()`.

### FB-BACKPOOL-004 - ReadyQueue is implemented but not live in task lifecycle

**Severity:** P1
**Status:** Open
**Finding:** ReadyQueue supports dependency ordering, but live task dispatch/completion does not enqueue by `depends_on`, notify completion, or auto-dispatch dependent envelopes.

Evidence:

- `ReadyQueue.enqueue(...)`, `dequeue_ready(...)`, and `notify_completed(...)` are implemented in [k1/concierge/actors/ready_queue.py](../../k1/concierge/actors/ready_queue.py#L91), [k1/concierge/actors/ready_queue.py](../../k1/concierge/actors/ready_queue.py#L209), and [k1/concierge/actors/ready_queue.py](../../k1/concierge/actors/ready_queue.py#L228).
- `_on_task_complete(...)` labels ReadyQueue notification as a placeholder in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3118).
- `_on_task_complete_adaptive(...)` labels dependent auto-dispatch as a placeholder in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3295).
- Runtime owns no `ready_queue`, so there is no consumer-side place to drain ready envelopes.

Impact:

- Dependent tasks can start before predecessors finish, or the dependency field can be ignored by the live Back execution path.
- A dependent Back worker can read a SessionState snapshot before predecessor artifacts/status are synced.
- Cycle/unknown-dependency handling in `ReadyQueue` is not protecting runtime dispatch.

Preferred fix:

- Runtime dispatch path should enqueue every Back-bound dispatch/resume envelope through ReadyQueue with `depends_on` metadata.
- FSM completion/failure/cancel should call `ready_queue.notify_completed(task_id, status)` after TaskBridge sync and worker release.
- Released envelopes should flow back through the normal pool scheduler, not call Back directly.

### FB-BACKPOOL-005 - Lease and HIL suspension lifecycle is not integrated with pool ownership

**Severity:** P1
**Status:** Open
**Finding:** `TaskLease` has explicit suspend/resume semantics, but current runtime never owns a live lease. If BackPool is wired naively, unified HIL can either hold a worker slot for the whole human wait or accidentally mark a suspended lease as released.

Evidence:

- `TaskLease.suspend()` and `TaskLease.resume(...)` exist in [k1/concierge/protocols/task_lease.py](../../k1/concierge/protocols/task_lease.py#L171).
- `BackPool.release_worker(...)` treats `cancelled` and `lease_expired` specially, but all other reasons call `slot.lease.release()` in [k1/concierge/actors/back_pool.py](../../k1/concierge/actors/back_pool.py#L350). A future `release_worker(reason="suspended")` would therefore release, not suspend, unless a separate suspend path is added.
- Unified HIL currently awaits `hil_port.needs_human(...)` inside Back handling and resumes in-process in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L727).
- Runtime has no worker done callback that can distinguish complete/failed/suspended/HIL-wait outcomes and update lease state accordingly.

Impact:

- With a pool wired around the current in-process HIL await, a worker slot can be occupied for the full human timeout.
- If the worker is released on suspension without preserving/suspending the lease, resume cannot preserve the same cancellation token/lease state.
- Lease expiry semantics during HITL wait remain undefined in live runtime.

Preferred fix:

- Add explicit BackPool methods for `suspend_worker(task_id)` and `resume_worker(task_id)` or equivalent lease-preserving ownership transfer.
- On unified HIL, decide whether Back remains in-process awaiting the HIL future or returns a suspended outcome to the runtime scheduler; do not mix both models accidentally.
- Ensure suspended leases are skipped by expiry watcher and cancelled on HIL timeout.
- Add focused tests for dispatch -> HIL suspend -> worker released/lease suspended -> resume -> same cancel token -> complete.

### FB-CANCEL-001 - CancellationHandler ledger is not wired when controller ledger is attached

**Severity:** P0/P1
**Status:** Open
**Finding:** `CancellationHandler` supports ledger writes, but controller construction creates it with no ledger, and `ConciergeController.set_ledger()` only stores the controller ledger. It does not call `self._cancel_handler.set_ledger(ledger)`.

Evidence:

- `CancellationHandler` initialized with `has_callback=False ledger=no` by default in [k1/concierge/protocols/cancel_handler.py](../../k1/concierge/protocols/cancel_handler.py#L43).
- Controller creates `CancellationHandler()` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L498).
- Controller `set_ledger()` only assigns `self._ledger = ledger` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L792).
- `cancel_handler.set_ledger(...)` appears only in docs, not live production code.

Impact:

- Cancel dedup and late-completion protection rely on in-memory sets unless another path writes equivalent ledger events.
- Crash recovery can lose cancelled task state and present a late completion as normal.

Preferred fix:

- In `ConciergeController.set_ledger()`, also call `self._cancel_handler.set_ledger(ledger)` and equivalent durable wiring for suspension/turn-state if intended.
- Add targeted cancel recovery test: cancel, simulate late completion after recovery, verify dedup/presentation mode.

### FB-CANCEL-002 - Cancellation callback path is unused in live controller

**Severity:** P1
**Status:** Open/partially mitigated by token checks
**Finding:** `CancellationHandler` accepts an async callback but controller constructs it with no callback. Runtime cancellation depends on tokens being checked between Back ReAct iterations and on Back mailbox cancel events being processed. Because BackPool/router is not wired, cancel may not be immediate under Back await/load.

Evidence:

- `CancellationHandler.__init__` has optional `on_cancel_fn`, default `None`, in [k1/concierge/protocols/cancel_handler.py](../../k1/concierge/protocols/cancel_handler.py#L43).
- Controller constructs with no callback in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L498).
- Back cancel handler falls back to token or legacy flag in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L1593).
- Runtime Back consumer is single awaited call; see `FB-HIL-005`.

Impact:

- User "cancel that" may be delayed until Back reaches a cooperative check or until the Back consumer is free.
- Cancel is less "one assistant responds immediately" than the architecture promises.

Preferred fix:

- Wire BackPool/BackTopicRouter so cancel bypasses worker queue.
- Consider a controller-level cancel callback that directly signals running task control queues/tokens.

### FB-WEAVE-001 - `WeaveBatcher` is wired but mostly vestigial in the live result path

**Severity:** P1/P2
**Status:** Open
**Finding:** The factory constructs a `WeaveBatcher` with a logging-only flush function and attaches it to the FSM. The active task-complete path uses `_turn_state`, `WeavePolicy`, and controller timers instead of `WeaveBatcher.on_task_complete(...)`.

Evidence:

- Factory wires `WeaveBatcher(flush_fn=_weave_flush)` where `_weave_flush` only logs in [k1/concierge/factory.py](../../k1/concierge/factory.py#L738).
- `_on_task_complete_adaptive` enqueues into `_turn_state` and applies `WeavePolicy`, not `WeaveBatcher`, in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3284).
- Controller only signals `set_front_busy(True/False)` and `discard_task` to `_weave_batcher` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2627), [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4537), and [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1186).

Impact:

- Docs/tests can imply `WeaveBatcher` owns batching, but runtime timing is controller-owned.
- If anything external calls `WeaveBatcher.on_task_complete`, it may start an independent timer and logging-only flush path.
- Maintainers have to reason about two possible result owners.

Preferred fix:

- Rename `WeaveBatcher` to a legacy/test helper, or rewire controller to use it as the real queue owner.
- Enforce result ownership rule: a result lives in exactly one of `FSMTurnState.pending_results`, `FSMTurnState.deferred_results`, or a batcher/queue.

### FB-WEAVE-002 - OPP-8 `DeliveryDecision` is computed/logged but not applied

**Severity:** P1
**Status:** Open
**Finding:** `_on_task_complete_adaptive` calls `opp_pipeline.on_task_complete(...)` and logs the delivery mode/result class/reasoning, but no later code uses `delivery_decision` to alter timing, presentation mode, prompt mode, or payload.

Evidence:

- `delivery_decision` is assigned and logged in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3315).
- Search shows no further use of `delivery_decision` after the log.
- `_apply_weave_decision(decision, ...)` ignores `delivery_decision` and only applies `WeaveDecisionResult` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1165).

Impact:

- OPP-8 natural-flow delivery can show as active in logs while having no behavioral effect.
- Presentation mode may remain generic WEAVE/BATCH even when delivery strategy classified a more natural mode.

Preferred fix:

- Either apply `DeliveryDecision` to envelope payload/presentation mode/timing, or mark OPP-8 delivery strategy as observability-only until wired.
- Add a test where delivery strategy returns a distinct mode and assert Front receives it.

### FB-WEAVE-003 - Typing signals do not pause/re-evaluate active weave timers

**Severity:** P1
**Status:** Open
**Finding:** `WeavePolicy` has a rule that user typing should defer non-critical delivery, and `_on_ui_typing` updates `UserActivityTracker`. But an already scheduled `_weave_flush_task` is not cancelled or re-evaluated when typing starts.

Evidence:

- `_on_ui_typing` only calls `on_typing_start()` or `on_typing_stop()` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L5506).
- `_schedule_weave_flush_adaptive` creates `_delayed_flush()` that sleeps and then flushes without checking the latest typing signal in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L5049).
- `WeavePolicy.decide` Rule 3 returns DEFER for `signal.user_typing` in [k1/concierge/protocols/weave_policy.py](../../k1/concierge/protocols/weave_policy.py#L858), but that rule runs at decision time, not during an active timer.
- `TypingPolicyReEvaluator` appears in protocol/tests, but this audit did not find controller usage.

Impact:

- A task can complete, schedule a weave, then the user starts typing, and the weave can still fire mid-composition.
- This creates the exact conversational ordering confusion the typing signal was meant to avoid.

Preferred fix:

- On typing_start, if `_weave_flush_task` is active and pending results are non-critical, cancel timer and mark/defer results.
- On typing_stop after debounce, re-evaluate and reschedule if appropriate.
- Re-check typing/HIL/affect gate immediately before `_flush_weave_now` as a final guard.

### FB-WEAVE-004 - Weave policy sees BackPool utilization only if BackPool is wired

**Severity:** P2
**Status:** Open, dependent on `FB-RUNTIME-001`
**Finding:** `WeaveSignal.from_runtime` can read BackPool utilization, and `WeavePolicy` has pool-pressure rules. But `_back_pool` is usually `None` in production because BackPool is not wired.

Evidence:

- Controller passes `self._back_pool` into `WeaveSignal.from_runtime` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1134).
- `WeaveSignal.from_runtime` reads `back_pool.get_pool_state()` only if `back_pool is not None` in [k1/concierge/protocols/weave_policy.py](../../k1/concierge/protocols/weave_policy.py#L604).
- No production `set_back_pool` caller found; see `FB-RUNTIME-001`.

Impact:

- Pool-pressure batching rules are effectively dormant.

Preferred fix:

- Wire BackPool, or remove pool utilization from live weave status claims.

### FB-OPP-001 - OPP trust accumulator is enabled in config but not attached

**Severity:** P1
**Status:** Open
**Finding:** `OppPipelineConfig.enable_trust_accumulator` defaults true, but factory only attaches episodic compressor and dynamic identity. It does not create or attach `TrustAccumulator`, so `opp4_trust_accumulator=False` and `trust_level=None` in pipeline status are expected.

Evidence:

- `OppPipelineConfig.enable_trust_accumulator: bool = True` in [k1/concierge/protocols/opp_pipeline.py](../../k1/concierge/protocols/opp_pipeline.py#L73).
- `OppPipeline.set_trust_accumulator(...)` exists in [k1/concierge/protocols/opp_pipeline.py](../../k1/concierge/protocols/opp_pipeline.py#L259).
- Factory creates `OppPipeline`, attaches compressor and identity, then `fsm.set_opp_pipeline(...)` in [k1/concierge/factory.py](../../k1/concierge/factory.py#L694).
- Pipeline status reports accumulator active only if both enabled and attached in [k1/concierge/protocols/opp_pipeline.py](../../k1/concierge/protocols/opp_pipeline.py#L842).

Impact:

- Logs can say OPP pipeline is wired while OPP-4 trust behavior is dormant.
- HIL auto-approval and dynamic clarification rounds are not affected by the new trust posture unless separately wired.

Preferred fix:

- Either attach `TrustAccumulator` or set `enable_trust_accumulator=False` until attached.
- Prefer unifying OPP trust with the canonical SessionState `trust_level` section rather than running two trust systems.

### FB-TRUST-001 - SessionState `trust_level` and OPP TrustAccumulator are divergent trust systems

**Severity:** P1
**Status:** Open
**Finding:** Front prompt now reads SessionState `trust_level` and uses it for action posture. OPP pipeline has a separate `TrustAccumulator` concept for HIL/pre-invoke autonomy, but that accumulator is not attached and does not appear connected to SessionState `trust_level`.

Evidence:

- Front prompt builder reads/renders `trust_level` in [k1/concierge/prompt/builder.py](../../k1/concierge/prompt/builder.py).
- OPP pipeline trust hooks call `_trust_accumulator` when attached in [k1/concierge/protocols/opp_pipeline.py](../../k1/concierge/protocols/opp_pipeline.py#L606) and [k1/concierge/protocols/opp_pipeline.py](../../k1/concierge/protocols/opp_pipeline.py#L646).
- Factory does not attach the OPP accumulator; see `FB-OPP-001`.

Impact:

- Front voice may become more autonomous based on SessionState trust, while tool/HIL gates remain unchanged.
- Or, if OPP trust is later attached separately, the two scores can disagree.

Preferred fix:

- Make `trust_level` the canonical trust projection and have OPP read/write through it, or clearly separate "relationship trust" from "operational auto-approval trust" with conversion rules.

### FB-HIGH-001 - HIGH-tier dispatch can fail hard when orchestrator is absent

**Severity:** P1
**Status:** Open/intentional production-strict behavior
**Finding:** Front can escalate a dispatch to HIGH by passing `complexity="HIGH"`. If no orchestrator is wired and `allow_planner_passthrough=False`, the FSM publishes `task.failed` and raises `OrchestratorNotWired`.

Evidence:

- `dispatch_task` derives HIGH from explicit `complexity="HIGH"` in [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1251).
- `_route_via_orchestrator` raises when HIGH tier has no orchestrator and passthrough is disabled in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2880).
- Factory only wires orchestrator when `ports.dispatch is not None and config.enable_orchestrator` in [k1/concierge/factory.py](../../k1/concierge/factory.py#L758).

Impact:

- Trust-driven "use your judgment" autonomy can route into a hard failure if Front chooses HIGH in a session without orchestrator.
- User sees less fluent behavior exactly when trust posture encourages fewer clarification loops.

Preferred fix:

- Gate Front exposure of HIGH complexity on an explicit orchestrator-present/self-model capability signal.
- Prompt Front to use LOW/MEDIUM direct Back dispatch unless the capability capsule says HIGH orchestration is live.
- Keep production-strict failure for true misconfiguration.

### FB-GROUNDING-001 - Front/Back context handoff depends on optional grounding/spatial handles and status can mislead

**Severity:** P2
**Status:** Open/needs verification in live boot profile
**Finding:** Front can refresh grounding and attach propagation metadata to dispatch, and Back can receive a grounding handle. But logs in this session showed spatial disabled while temporal/grounding were enabled, and location/semantic place handling was recently fixed. This is adjacent to Front/Back coordination because dispatch context quality depends on these handles being live and coherent.

Evidence:

- Front refreshes grounding and builds dispatch metadata when `grounding is not None` in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1220).
- Front falls back to temporal when grounding is absent in [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1260).
- Back route receives `grounding=self._grounding` from runtime in [k1/concierge/session.py](../../k1/concierge/session.py#L407).

Impact:

- Back may receive less situational context than Front had, or logs may imply handles are wired when one projection is disabled.
- User-visible "unknown location" or stale context can look like a Front/Back coordination failure.

Preferred fix:

- Add a boot/session wiring diagnostic that lists Front handle and Back handle availability together: temporal, spatial, grounding, self_model.
- Add a targeted dispatch test that confirms grounding propagation metadata survives Front -> FSM -> Back envelope canonicalization.

### FB-STATE-001 - FSM state and FrontLock remain a subtle race surface

**Severity:** P1/P2
**Status:** Open/partially mitigated
**Finding:** FrontLock queues user input while Front is presenting or weaving, and response-final releases/drains. This is correct, but many handlers also call `try_deliver` directly. Stale HIL prompts and queued events are actively managed, which indicates a known race surface.

Evidence:

- `_on_user_input` queues input in DELIVERING/WEAVING/PROACTIVE_WAKE via FrontLock in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L1956).
- `_execute_response_final_decision` releases FrontLock and optionally schedules weave/finalizes turn in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L4565).
- `_drop_queued_front_hitl_for_task` exists to remove stale HIL prompts in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2668).
- Many event handlers call `try_deliver` directly after state mutation.

Impact:

- Duplicate or stale Front presentations remain possible around HIL timeout/resolution, task terminalization, and queued user input.
- The correctness burden is distributed across handlers.

Preferred fix:

- Keep direct delivery but add focused race tests for: HIL request then timeout then user answer; task completes while Front busy; user input arrives during weave timer; task terminalizes while HIL prompt queued.
- Consider a single helper for "mutate state, check FrontLock, deliver or queue" with standardized stale-HIL cleanup.

### FB-DOCS-001 - Architecture docs mix current runtime, planned runtime, and stale gaps

**Severity:** P2
**Status:** Open
**Finding:** Subagent reports and older docs still mentioned gaps that are now fixed, while some planned components are documented as if live. This audit found both stale-negative and stale-positive claims.

Stale-negative claims now fixed:

- Split Front/Back consumers missing: fixed.
- `HILPresented` missing: fixed for Front chat lane.
- `TOPIC_UI_TYPING` / `TOPIC_WEAVE_DECIDED` guard entries missing: fixed.
- Back topic routing absent: function-level topic routing is live.

Stale-positive claims not fully live:

- BackPool/BackTopicRouter/ReadyQueue production runtime wiring.
- HIL suspend-before-publish durability.
- OPP-4 trust accumulator wiring.
- OPP-8 delivery strategy behavioral effect.
- Presentation-aware HIL timeout in production config.

Impact:

- Engineers can chase non-bugs or trust planned wiring that is not actually active.

Preferred fix:

- Update the main Concierge wiring docs to mark each component as one of: LIVE, LIVE-PARTIAL, COMPATIBILITY, PLANNED, TEST-ONLY.
- Keep this whiteboard as the source for current gaps until those docs are reconciled.

---

## Deprecated / Compatibility / Dead-Weight Inventory

| Item | Current role | Risk | Recommendation |
| --- | --- | --- | --- |
| `_mailbox_consumer` in [k1/concierge/session.py](../../k1/concierge/session.py#L429) | Legacy compatibility wrapper over split consumers | Low confusion | Keep only as compatibility; do not reference as active runtime architecture. |
| `_on_task_suspended` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3546) | Legacy/recovery/no-HIL-port path | Drift from unified HIL | Gate or keep only for recovery/tests. |
| `_on_task_resume` in [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L3750) | Legacy/recovery path | Double-resume risk if unified envelope leaks into legacy path | Keep guard that drops unified HIL task.resume; add regression. |
| `back_resume_handler` in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py) | Legacy resume execution | Maintained but not live unified path | Keep until recovery model is durable; mark compatibility. |
| `WeaveBatcher` in [k1/concierge/protocols/weave_batcher.py](../../k1/concierge/protocols/weave_batcher.py) | Wired helper/test queue, not active task-complete owner | Misleading timing owner | Rename, remove live wiring, or make it the actual owner. |
| `BackTopicRouter` in [k1/concierge/actors/back_router.py](../../k1/concierge/actors/back_router.py) | Planned/isolated router with BackPool integration | Runtime bypasses it | Delegate live route function to it or remove duplicate router. |
| BackPool / ReadyQueue | Implemented primitives plus red runtime-wiring tests | Not production-wired; tests assert missing runtime/config APIs | Wire end-to-end or mark planned-only. |
| OPP TrustAccumulator | Implemented primitive | Config enabled but object absent | Attach to canonical trust or disable flag. |
| OPP DeliveryStrategy result | Computed/logged when engine exists | Not applied | Apply or mark observability-only. |

---

## Race Windows To Test Directly

Do not run broad kernel/fabric suites for these. Use targeted files or create focused probes.

1. **HIL presentation timeout window**
   - `needs_human` request is published while Front is busy.
   - Verify timeout starts only after `HILPresented` once ack mode is enabled.
   - Add separate test for inline widget `approval`/`capability_gate` presentation ack.

2. **Back await blocks Back mailbox**
   - Back task A enters unified HIL await.
   - Back task B or cancel envelope arrives.
   - Verify whether current runtime queues B/cancel until A resolves; this should drive BackPool wiring decision.

3. **Typing starts after weave timer scheduled**
   - Task complete schedules BATCH.
   - `k1.ui.typing.v1` typing=true arrives during window.
   - Verify timer cancels/defer behavior after fix.

4. **Cancel then late complete across recovery**
   - User cancels task.
   - Simulate restart or rebuild.
   - Late `task.complete` arrives.
   - Verify result is not presented as normal completion.

5. **Unified HIL duplicate answer / multi-device answer**
   - Two user answers arrive for same `hil_request_id`.
   - Verify first wins, second is ignored, and service future is resolved once.

6. **Stale queued HIL prompt cleanup**
   - HIL prompt queued in FrontLock.
   - Task terminalizes before prompt delivery.
   - Verify queued HIL envelope is removed.

7. **HIGH dispatch with no orchestrator**
   - Front emits `complexity="HIGH"` with orchestrator absent.
   - Verify user-visible failure path is clean and Front does not silently collapse to lower tier unless passthrough is explicitly enabled.

8. **Grounding propagation across dispatch**
   - Front has grounding projection/device place hint.
   - Dispatch task.
   - Verify canonical Back envelope retains relevant propagation metadata.

---

## Targeted Verification Commands

These are intentionally narrow. Do not run the full kernel suite.

Potential existing tests to use or extend:

```powershell
pytest tests/k1/concierge/test_front_hil_unified_envelope.py -v
pytest tests/k1/concierge/test_m04_weave_fsm_paths.py -v
pytest tests/k1/concierge/test_m04_weave_controller_steps.py -v
pytest tests/k1/concierge/test_m08_e81_weave_signal.py -v
pytest tests/k1/concierge/test_m08_e84_policy_integration.py -v
pytest tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py -v
pytest tests/k1/concierge/test_trust_accumulator.py -v
```

Current BackPool verification result from this audit:

- `pytest tests/k1/concierge/test_m8_e5_backpool_runtime_wiring.py -v` reports `0 passed` with constructor/attribute failures for missing `backpool_*` config fields and missing `ConciergeRuntime.back_pool` surfaces.
- Do not treat this as a flaky behavior test. It is a direct signal that the BackPool runtime wiring surface is absent.

Potential new focused tests:

- `tests/k1/concierge/test_hil_presentation_ack_widget_lane.py`
- `tests/k1/concierge/test_hil_service_session_durability.py`
- `tests/k1/concierge/test_weave_typing_timer_reeval.py`
- `tests/k1/concierge/test_cancel_handler_ledger_wiring.py`
- `tests/k1/concierge/test_opp_delivery_decision_applied.py`
- `tests/k1/concierge/test_grounding_dispatch_propagation.py`

---

## Recommended Fix Order

1. **HIL durability first:** wire service suspension/ledger, then enable presentation-aware lifecycle.
2. **Widget presentation ack:** make direct UI widgets publish `TOPIC_HIL_PRESENTED`; only then turn on `require_presentation_ack`.
3. **BackPool config bridge:** add canonical BackPool config fields and map KernelConfig -> ConciergeConfig.
4. **BackPool runtime owner:** construct pool/router/queue in factory, pass them to runtime, expose properties, call `fsm.set_back_pool(...)`, and wire observability callbacks.
5. **BackPool scheduler:** replace direct Back handler await with pool worker scheduling, cancel bypass, overflow drain, ReadyQueue drain, and lease watcher lifecycle.
6. **BackPool lifecycle correctness:** wire completion/failure/cancel/HIL suspension/resume to release, cancel, suspend, or resume leases exactly once.
7. **Cancel durability:** wire `CancellationHandler.set_ledger()` and add recovery/late-completion tests.
8. **Weave timer correctness:** pause/re-evaluate active weave timers on typing and just before flush.
9. **Weave ownership cleanup:** decide whether `WeaveBatcher` is active owner or legacy helper.
10. **Trust unification:** connect SessionState `trust_level` with OPP trust or disable dormant OPP-4 status.
11. **OPP delivery behavior:** apply `DeliveryDecision` to presentation or mark it observability-only.
12. **Docs reconciliation:** label current components as LIVE, LIVE-PARTIAL, COMPATIBILITY, PLANNED, or TEST-ONLY.

---

## Bottom Line

The Front/Back split is real and much healthier than older docs imply: independent consumers, structured dispatch, unified HIL envelopes, Front presentation ack, typed result frames, and FSM-owned state are all present.

The main remaining problem is not actor separation. The main problem is **partial production wiring**: BackPool is not live, HIL durability is not live, OPP trust is not attached, OPP delivery is not applied, and weave typing re-evaluation is incomplete. Those gaps make the system look architecturally complete on paper while important runtime behaviors still run through simpler compatibility paths.
