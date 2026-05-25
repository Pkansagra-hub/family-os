<!-- markdownlint-disable MD013 MD024 -->

# K1 Living Gap Register

Status: living engineering gap register
Last updated: 2026-05-24
Scope: K1 kernel, Concierge, HIL, grounding, SessionState, K0 persistence, UI/web bridges.

This document is the durable register for known architectural and runtime gaps. It is not tied to one incident, one plan, or one milestone. Each entry should state the failure shape, the affected code boundary, the required outcome, and the focused tests that should close the gap.

Primary planning references:

- Temporal/spatial grounding plan: `../../../docs/plans/k1_temporal_spatial_grounding_plan.md`
- HIL timing incident source: live barber appointment flow from 2026-05-23 logs

## Maintenance Rules

- Keep active gaps in the index until a targeted regression test covers the closure.
- Prefer root-cause boundaries over symptom notes.
- Link each gap to code ownership boundaries and validation tests.
- Move fixed items to `Recently Closed` with a short close note instead of deleting the history.
- Do not use this register as a scratchpad for broad ideas; every gap must have an observable risk.

## Status Legend

- `Open`: known gap with no committed implementation.
- `Planned`: accepted scope with a plan milestone or owner boundary.
- `In Progress`: implementation exists but is not fully validated.
- `Blocked`: cannot proceed until an upstream decision or dependency lands.
- `Closed`: code and targeted tests are complete.
- `Deferred`: intentionally postponed, with accepted risk.

## Active Gap Index

| ID | Area | Status | Risk | Summary |
| --- | --- | --- | --- | --- |
| GAP-HIL-001 | HIL/runtime scheduling | Open | Critical | Single runtime mailbox consumer lets a Back HIL wait starve Front presentation. |
| GAP-HIL-002 | HIL/Back actor | Open | High | Back treats `needs_human` as a blocking in-process await inside the actor loop. |
| GAP-HIL-003 | HIL timing | Open | Critical | Human timeout starts at request publish, not user presentation. |
| GAP-HIL-004 | UI/web HIL bridge | Open | High | Free-text HIL has no answerable widget path and depends on Front chat presentation. |
| GAP-HIL-005 | FSM lifecycle | Open | High | `CLARIFYING_WORKER` can close after timeout because active task state is gone. |
| GAP-HIL-006 | HIL cleanup | Open | High | Pending HIL mirrors are not cleared atomically on timeout/cancel/fail. |
| GAP-HIL-007 | Front latency | Open | Medium | Simple `HITL_RELAY` questions pay an avoidable Front LLM call. |
| GAP-HIL-008 | Front/Back contract | Open | Medium | Dispatch is a hard invocation boundary and needs explicit tests/docs. |
| GAP-HIL-009 | HIL lifecycle | Open | Critical | There is no presentation acknowledgement for HIL requests. |
| GAP-HIL-010 | HIL recovery | Open | Medium | Late answers to recently expired HIL prompts have no recovery route. |
| GAP-HIL-011 | HIL state ownership | Open | High | HIL live state has no single source of truth. |
| GAP-HIL-012 | Test coverage | Open | High | No targeted integration test locks the observed HIL timing failure. |
| GAP-TSG-M5-001 | Spatial/K0 persistence | Planned | High | Place registry and geofences are still local/session-first, not K0 Bridge-backed. |
| GAP-TSG-M6-001 | Memory/K0/UI/finalization | Planned | High | Grounding metadata, time/place memory recall, UI inspection, and final flag removal are not complete. |
| GAP-EGRESS-001 | Front egress / FSM history sink | Open | High | `history_active` writes are gated to Front-only and silently skipped on canned-fallback turns; multi-producer `response.final` is not supported. |
| GAP-EGRESS-002 | Bus egress sanitization | Open | High | Leaked-reasoning / system-block / Back-frame stripping is bolted into Front only; no actor besides Front can publish user-visible text safely. |
| GAP-EGRESS-003 | Worker speaker protocol | Open | Critical | Back has no protocol to publish user-visible text directly during HIL; every HIL round forces +2 Front hops (HITL_RELAY + HITL_RESOLVE). Planner/Fabric will multiply this. |
| GAP-EGRESS-004 | Back result narration policy | Open | High | Every `task.complete` triggers a Front PRESENT hop, even when Back's `final_answer` is already user-ready. Adds +1 LLM call per task and double-quotes the result risk. |
| GAP-EGRESS-005 | HITL_RELAY default substitution | Open | Medium | Back's `hil_question` is only forwarded verbatim on Front degenerate retry; the default path is still a Front LLM rephrase that mostly wastes a call. |
| GAP-EGRESS-006 | WEAVE/PRESENT mode duplication | Open | Low | Two near-identical modes carry duplicated prompt scaffolding and inflate `PromptMode` surface; both deliver Back results to the user. |
| GAP-EGRESS-007 | Planner subtask delivery aggregation | Open | High | Once Planner lands, every subtask completion will trip a Front PRESENT hop; N subtasks = N PRESENT hops with no batching path. |
| GAP-EGRESS-008 | Fabric agent direct egress | Open | Medium | Fabric agents (Spatial / Temporal / Grounding / future) currently can only surface text by routing through Front; no `voice_token` channel exists. |
| GAP-EGRESS-009 | Task-widget UI HIL channel | Open | Medium | All HIL is serialized through the chat thread; concurrent background HIL (planner, fabric) will jam the conversation channel. No parallel widget channel exists. |
| GAP-EGRESS-010 | Deterministic intent router | Open | Low | Every Front STANDARD turn invokes Gemini even for trivial confirmations (yes/ok/cancel). Mandate-compliant pre-LLM router could short-circuit. |

## Recently Closed

### CLOSE-TSG-2026-05-24: M0-M3 Formal Exit Cleanup

Status: Closed in current working tree.

Closed items:

- `KernelConfig` temporal, grounding, and spatial defaults are on after the M3 exit gate, while explicit disable remains available for isolated tests or rollback.
- Kernel top-level port exports include spatial and grounding protocols and supporting payload types.
- Default bus topic registry accepts `k1.temporal.`, `k1.spatial.`, and `k1.grounding.` event families.
- Planner temporal test no longer expects the retired `constraints["temporal"]` prompt path; Planner grounding is sourced from `PlanRequest.grounding`.
- Concierge diagram no longer keeps a standalone `TEMPORAL_ANCHOR` runtime node.
- Old prompt identity text now points models at injected `== NOW ==` and `== PLACE ==` grounding blocks.
- The stale write-elision `temporal_anchor` marker was removed from the FSM write payload.

Validation boundary:

- `tests/k1/kernel/test_config_temporal_spatial_grounding_flags.py`
- `tests/k1/kernel/ports/test_spatial_port_protocol.py`
- `tests/k1/kernel/ports/test_grounding_port_protocol.py`
- `tests/k1/bus/middleware/test_default_registry_temporal.py`
- `tests/k1/concierge/test_bus_temporal_topics.py`
- `tests/k1/planner/test_expand_service_temporal.py`

## HIL Timing and Front/Back Loop Gaps

> **CLOSURE: CLOSE-HIL-2026-05-24** — GAP-HIL-001 through GAP-HIL-012 closed
> by the HIL Unification slices. Summary at the end of this section; the
> per-gap entries below are retained for archaeology with `Status: Closed`.

### GAP-HIL-001: Single Consumer Blocks Front While Back Waits

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: Critical

Current behavior:

- `ConciergeRuntime._mailbox_consumer` drains Front and Back mailboxes in one async loop.
- It awaits `front_handler(...)` inline and then awaits `route_back_envelope(...)` inline.
- When Back awaits a human response, the same consumer cannot pull the queued Front HIL relay.

Evidence boundary:

- `k1/concierge/session.py`
- `ConciergeRuntime._mailbox_consumer`
- Front mailbox branch: `_front_mailbox` -> `front_handler(...)`
- Back mailbox branch: `_back_mailbox` -> `route_back_envelope(...)`

Required outcome:

- Front and Back mailbox draining must be independent enough that a blocked Back await cannot starve Front presentation.
- Existing runtime lifecycle, dedup behavior, `_tick_experience()`, and shutdown semantics must remain intact.

Validation:

- Add `tests/k1/concierge/test_session_actor_mailbox_concurrency.py`.
- Simulate Back waiting on HIL while a Front HIL relay is queued.
- Assert Front handler runs before the HIL timeout and before the Back future resolves.

### GAP-HIL-002: Back Treats HIL as Blocking In-Process Await Inside Actor Loop

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: High

Current behavior:

- Back resolves `needs_human` through `await hil_port.needs_human(req)`.
- The API shape is valid, but unsafe when Back runs inside the same consumer that must process Front presentation.
- On timeout, Back returns a cancelled `ReactResult` with `HIL_TIMEOUT`.

Evidence boundary:

- `k1/concierge/actors/back.py`
- `_resolve_needs_human_in_process(...)`
- `back_handler(...)`
- Future resume boundary: `back_resume_handler(...)` if Back moves to event resume.

Required outcome:

- Short term: actor mailbox loops must be split so Back can await without blocking Front.
- Stronger model: Back should yield a suspended task lifecycle and resume on `TOPIC_HIL_RESPONSE` or an explicit resume envelope.

Validation:

- Back HIL wait must not prevent Front HIL relay processing.
- Back timeout behavior must remain deterministic when no answer arrives after presentation-aware budget expires.

### GAP-HIL-003: HIL Timeout Starts at Request Publish, Not User Presentation

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: Critical

Current behavior:

- `HumanInTheLoopService._request(...)` creates the envelope, publishes `TOPIC_HIL_REQUEST`, and immediately starts `asyncio.wait_for(...)`.
- The timeout measures time since kernel request creation, not time since the user saw an answerable prompt.

Evidence boundary:

- `k1/hil/service.py`
- `HumanInTheLoopService._request(...)`
- `_pending[hil_id] = fut`
- `await self._event_port.publish(TOPIC_HIL_REQUEST, env.to_dict())`
- `await asyncio.wait_for(fut, timeout=timeout_ms / 1000.0)`

Required outcome:

- Add presentation-aware lifecycle states: `requested`, `routed_to_front`, `presented`, `awaiting_human`, `resolved`, `expired`.
- Human response timeout must start after presentation acknowledgement, or the request must have separate presentation and human-response budgets.

Validation:

- Add `tests/k1/concierge/test_hil_timing_lifecycle.py`.
- Assert a request does not expire its human-response budget before Front presentation acknowledgement.

### GAP-HIL-004: Web HIL Event Is Not an Answerable Free-Text Path

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: High

Current behavior:

- Browser HIL widgets intentionally ignore `needs_human` and `clarification` requests.
- That split is correct for conversation continuity, but it means free-text HIL is answerable only through Front chat.
- If Front is blocked, the user has no valid way to answer before timeout.

Evidence boundary:

- `ui/web/static/app.js`
- `handleHilRequest(msg)` ignores free-text HIL widget requests.
- `sendHilResponse(hilMsg, approved)` is guarded against stale free-text widget responses.
- `ui/web/app.py` publishes widget-lane responses to `TOPIC_HIL_RESPONSE`.

Required outcome:

- Keep lane separation:
  - `needs_human` and `clarification`: chat lane through Front.
  - `capability_gate`, `approval`, and `override`: widget lane.
- Add explicit chat presentation acknowledgement and pending HIL binding so the chat input can be associated with the active HIL request.

Validation:

- Widget HIL tests must keep free-text HIL out of approval widgets.
- Chat HIL tests must bind the next user answer to the active HIL request after presentation.

### GAP-HIL-005: FSM Closes HIL Turn After Timeout Because Active Task Is Gone

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: High

Current behavior:

- If Back times out and fails the task, the active task is removed.
- A late Front HIL prompt can still publish `response.final`.
- `response_final_table` keeps `CLARIFYING_WORKER` open only while active tasks exist, so the state can fall back to `LISTENING` before the user answer arrives.

Evidence boundary:

- `k1/concierge/fsm/response_final_table.py`
- `decide_response_final(...)`
- `k1/concierge/fsm/controller.py`
- `_on_response_final(...)`
- `_on_task_failed(...)`

Required outcome:

- `CLARIFYING_WORKER` should be tied to pending HIL lifecycle, not only active task ids.
- Stale prompts must be suppressed or marked expired after HIL expiry.

Validation:

- FSM tests should pass pending HIL lifecycle state into response-final decisions.
- A late `response.final` for an expired HIL must not leave the next user input as unrelated `STANDARD` input.

### GAP-HIL-006: HIL Cleanup Is Not Atomic Across Mirrors

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: High

Current behavior:

- HIL live state is mirrored across service futures, FSM maps, task state fields, suspension manager state, active task ids, and queued Front envelopes.
- Timeout, cancel, fail, and complete paths do not clear all mirrors in one boundary.
- The observed coherence anomaly was `pending_data_invisible_to_has_pending_hitl`.

Evidence boundary:

- `k1/hil/service.py`: `_pending`
- `k1/concierge/fsm/controller.py`: `_pending_hil_subtasks`, `_has_pending_hitl()`, `_after_task_cleanup(...)`
- `k1/concierge/fsm/task_bridge.py`: `cancel_task(...)`, `fail_task(...)`
- `k1/sessionstate/sections/task_state.py`: `pending_hil`, `pending_hil_data`
- `k1/hil/suspension.py`: `SuspensionManager`

Required outcome:

- Introduce one terminal HIL cleanup boundary for timeout, cancel, fail, and complete.
- Cleanup must clear service pending futures, task-state pending fields, FSM pending maps, suspension state, stale Front queue entries, and lifecycle events consistently.

Validation:

- Add `tests/k1/concierge/fsm/test_hil_timeout_cleanup.py`.
- Assert all HIL mirrors are empty/terminal after timeout, cancel, fail, and complete paths.

### GAP-HIL-007: HITL_RELAY Uses a Full Front LLM Call for Simple Back Questions

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: Medium

Current behavior:

- Back already supplies the clarification question.
- Front enters `HITL_RELAY`, builds a prompt, and may spend one or two LLM calls just to rephrase it.
- Deterministic fallback occurs only after degenerate output.

Evidence boundary:

- `k1/concierge/actors/front.py`
- `front_handler(...)`
- `k1/concierge/prompt/mode.py`
- `PromptMode.HITL_RELAY`

Required outcome:

- For simple `needs_human` and `clarification`, render the Back question directly as chat output by default.
- Publish presentation acknowledgement after deterministic render.
- Keep LLM rewrite only for high-sensitivity or policy-selected cases.

Validation:

- Add `tests/k1/concierge/test_front_hil_fast_path.py`.
- Assert simple HIL relay emits the supplied question without invoking Front LLM.

### GAP-HIL-008: Front ReAct Loop Ends at Dispatch Boundary by Design

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: Medium

Current behavior:

- Local Front tools feed observations back into the same `react_loop`.
- `dispatch_task` is a hard boundary: once dispatch succeeds, the loop ends and later Back results/HILs start new Front invocations.

Evidence boundary:

- `k1/concierge/react/loop.py`
- `react_loop(...)`
- `k1/concierge/actors/front.py`
- `k1/concierge/tools/implementations.py`

Required outcome:

- Keep the dispatch boundary.
- Document and test that Back result/HIL continuity comes from SessionState/history/task state and a later Front invocation.
- Ensure later invocations have enough task/HIL context to answer naturally.

Validation:

- Dispatch-boundary tests should assert Front does not stay alive waiting for Back.
- HIL relay tests should assert the later invocation is prompt and context-rich.

### GAP-HIL-009: HIL Request Has No Presentation Acknowledgement

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: Critical

Current behavior:

- HIL service knows request publish time and response/timeout.
- It does not know when Front rendered an answerable prompt.
- FSM delivers HIL to Front but does not complete a presentation lifecycle step.

Evidence boundary:

- `k1/hil/service.py`
- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/front.py`

Required outcome:

- Add an explicit presentation event or ledger record such as `k1.hil.presented.v1`.
- Payload should include `hil_request_id`, `task_id`, `kind`, `presented_at_ms`, `presentation_channel`, and `trace_id`.
- Use acknowledgement to start/adjust human response timeout and suppress stale prompts.

Validation:

- HIL request lifecycle tests must prove the service/FSM can distinguish requested, routed, presented, awaiting answer, resolved, and expired states.

### GAP-HIL-010: Late User Answers Have No Expired-HIL Recovery Path

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: Medium

Current behavior:

- If a HIL prompt appears after timeout, the next user answer enters `LISTENING` and is routed as a normal turn.
- The kernel does not recognize that the text likely answers a recently expired HIL question.

Evidence boundary:

- `k1/concierge/fsm/controller.py`
- `_on_user_input(...)`
- `k1/concierge/prompt/mode.py`
- `determine_mode(...)`

Required outcome:

- Add recent-expired-HIL lookup before normal `LISTENING` routing.
- Either revive the request if safe or tell the user the task expired and offer restart using the supplied answer.

Validation:

- Add `tests/k1/concierge/test_late_hil_answer_recovery.py`.
- Assert late answers route to recovery, not ordinary `STANDARD`.

### GAP-HIL-011: HIL State Has No Single Source of Truth

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: High

Current behavior:

- HIL state is spread across service futures, task state fields, FSM maps, suspension manager, FrontLock, and history/ledger events.
- Some mirrors are authoritative in one path and derived in another.

Evidence boundary:

- `k1/hil/service.py`
- `k1/concierge/fsm/controller.py`
- `k1/sessionstate/sections/task_state.py`
- `k1/hil/suspension.py`
- `k1/concierge/protocols/hitl_persistence.py`

Required outcome:

- Define one live HIL lifecycle owner.
- Recommended ownership:
  - `HumanInTheLoopService`: request future and response resolution.
  - FSM/controller: conversation state, task binding, Front routing.
  - TaskState: durable projection only.
  - SuspensionManager: crash/recovery support only.
- One lifecycle mutation path should project changes into all mirrors.

Validation:

- Coherence tests must fail if any mirror still claims pending HIL after terminal cleanup.

### GAP-HIL-012: Test Coverage Does Not Lock the Failing Timing Path

Status: Closed (CLOSE-HIL-2026-05-24)
Risk: High

Current behavior:

- Existing tests cover HIL envelopes, Front HIL response emission, FSM resume guards, and service roundtrips.
- The observed failure was an integration timing issue: Back waits on HIL while Front must still process HIL relay.

Required outcome:

- Add focused regression tests before broad refactors.
- Do not run broad kernel/fabric suites for this work.

Targeted test boundary:

- `tests/k1/concierge/test_session_actor_mailbox_concurrency.py`
- `tests/k1/concierge/test_hil_timing_lifecycle.py`
- `tests/k1/concierge/fsm/test_hil_timeout_cleanup.py`
- `tests/k1/concierge/test_front_hil_fast_path.py`
- `tests/k1/concierge/test_late_hil_answer_recovery.py`

### CLOSE-HIL-2026-05-24 -- HIL Unification closure summary

GAP-HIL-001..012 closed end-to-end through the following slices. Each slice
shipped with targeted regression tests; no broad kernel or fabric suites were
run (per test discipline).

Slice 1 -- Split mailbox consumers (GAP-HIL-001, GAP-HIL-002):

- `ConciergeRuntime` now starts independent `_front_consumer_task` and
  `_back_consumer_task` so a Back await cannot starve Front presentation.
- Validation: `tests/k1/concierge/test_session_actor_mailbox_concurrency.py`.

Slice 2 -- HIL presentation lifecycle (GAP-HIL-003, GAP-HIL-009):

- New bus topic `k1.hil.presented.v1` (`TOPIC_HIL_PRESENTED`) and
  `HILPresentedEnvelope`. `HumanInTheLoopService._request` performs a
  two-phase wait: presentation-ack timer first, then per-kind human-response
  timer. Counter `presentation_timed_out` records ack misses.
- `HILConfig` adds `require_presentation_ack`, `presentation_timeout_ms`,
  `enable_front_fast_path`, `enable_llm_relay_rewrite`.
- Validation: `tests/k1/hil/test_presentation_lifecycle.py`.

Slice 3 -- Front HITL_RELAY fast-path + presented ack (GAP-HIL-007,
GAP-HIL-009):

- `front_handler` deterministic fast-path for HITL_RELAY skips the LLM
  rewrite when policy permits, publishes `response.final`, and emits
  `TOPIC_HIL_PRESENTED`. The post-LLM degenerate-replacement branch also
  emits the presented ack.
- Validation: existing `tests/k1/concierge/test_front_hil_unified_envelope.py`.

Slice 4 -- Atomic terminal cleanup + priority bump (GAP-HIL-006,
GAP-HIL-011):

- `_on_task_failed` now calls `_cleanup_terminal_hitl_state(task_id)` so
  service futures, FSM maps, queued Front entries, and suspension state
  drop together.
- `front_lock.TOPIC_PRIORITY` now serves `TOPIC_HIL_REQUEST` at INTERACTIVE.
- Validation: `tests/k1/concierge/fsm/test_front_lock_hil_priority.py`.

Slice 5 -- Pending-HIL STAY (GAP-HIL-005):

- `decide_response_final` gains `pending_hitl: bool`. CLARIFYING_WORKER
  Branch 11 stays open when HIL is still pending, even with no active
  tasks. `_on_response_final` threads `self._has_pending_hitl()` through.
- Validation:
  `tests/k1/concierge/fsm/test_response_final_pending_hitl_stay.py`.

Slice 6 -- Late-answer recovery + UI surface (GAP-HIL-004, GAP-HIL-010):

- Controller keeps a bounded `_recently_expired_hil` ring; on user input,
  `_route_user_turn` consumes a recent expiry and tags arbiter routing
  metadata with `late_hil_recovery=True`. `determine_mode` honours the
  flag and returns `PromptMode.HITL_RESOLVE`.
- UI: `renderer.send_hil_presented`, coordinator subscription to
  `TOPIC_HIL_PRESENTED`, and `static/app.js` binds the chat input to the
  active HIL request via `data-hil-*` attributes.
- Validation: `tests/k1/concierge/test_late_hil_recovery_mode.py`.

Slice 7 -- Regression locking (GAP-HIL-012):

- All five focused test files above plus the prior HIL/Front suites pass
  in the targeted sequential pytest sweep documented per slice.

## Temporal/Spatial Grounding Persistence Gaps

### GAP-TSG-M5-001: Place Registry and Geofences Are Not K0 Durable Yet

Status: Planned
Risk: High
Planning source: `../../../docs/plans/k1_temporal_spatial_grounding_plan.md`, M5: Place Registry + Geofences + K0 Persistence

Current behavior:

- Spatial runtime can use browser/device fixes, local registry state, geofence matching, and reverse geocoding.
- The production place registry is still local/session-first unless a port is injected.
- The Bridge adapter is a shell/delegator and not backed by an explicit K0 schema/contract in this tree.

Evidence boundary:

- `k1/spatial/factory.py`: production factory falls back to `LocalPlaceRegistryAdapter`.
- `k1/spatial/adapters/bridge_place_registry_adapter.py`: adapter delegates only when bridge methods are present.
- Missing expected M5 artifacts:
  - `k0/schemas/place_registry.json`
  - `bridge/contracts/place_registry.py`
  - `tests/k1/spatial/adapters/test_bridge_place_registry_adapter.py`
  - `tests/k1/spatial/test_geofence_matcher_real.py`
  - `tests/k1/grounding/test_projection_builder_planner_spatial.py`

Impact:

- Place identity can remain geocoder-dependent and session-local.
- Correct home/place names may not survive restarts.
- Geocoder locality can be wrong or too coarse for household semantics.
- Planner/tool consumers cannot rely on durable spatial constraints from K0.

Required outcome:

- Add K0-backed place registry schema and Bridge contract.
- Make `BridgePlaceRegistryAdapter` a real durable adapter with explicit failure modes.
- Select bridge-backed registry in production wiring when bridge is online.
- Preserve local adapter behavior for isolated tests.
- Add production geofence fixtures that validate real household/place boundaries without leaking raw location to unauthorized consumers.

Validation:

- Add and run only targeted M5 tests:
  - `tests/k1/spatial/adapters/test_bridge_place_registry_adapter.py`
  - `tests/k1/spatial/test_geofence_matcher_real.py`
  - `tests/k1/grounding/test_projection_builder_planner_spatial.py`
  - Existing touched spatial/grounding factory tests.

Deferral note:

- This can be deferred for local live browser prompt work, but it should not be skipped for production-grade place correctness.

### GAP-TSG-M6-001: MemoryWriter, K0 Recall, UI Inspector, and Final Flag Removal Are Pending

Status: Planned
Risk: High
Planning source: `../../../docs/plans/k1_temporal_spatial_grounding_plan.md`, M6: K0 Memory + UI + MemoryWriter Schema + Final Cleanup

Current behavior:

- Grounding projections can flow through Concierge and Planner, but grounding metadata is not yet fully persisted into K0 memory/write paths.
- Time/place recall indexes and UI inspector surfaces are not complete.
- Temporal, grounding, and spatial feature flags still exist for rollback even after defaults are on.

Evidence boundary:

- Missing expected M6 artifacts:
  - `k1/memory_writer/grounding_metadata.py`
  - `k1/memory_writer/spatial_redaction.py`
  - `k0/memory/time_place_index.py`
  - `tests/k0/memory/test_time_place_index.py`
- Remaining planned cleanup from the grounding plan:
  - MemoryWriter schemas align with optional grounding fields.
  - SessionState UI exposes temporal, spatial, grounding, and place registry sections.
  - Feature flags are removed only after the always-on path is production-safe.

Impact:

- Memories may lose authoritative time/place context or store it inconsistently.
- Recall cannot reliably filter or rank by time/place facets.
- Operators cannot fully inspect the grounding state from UI surfaces.
- Keeping flags after final closeout leaves a split runtime posture.

Required outcome:

- Add MemoryWriter grounding metadata support.
- Enforce raw spatial redaction before memory writes.
- Add K0 time/place indexing and recall query support.
- Add UI inspector coverage for new SessionState sections.
- Remove temporal/spatial/grounding flags only after M5 and M6 validation are green.

Validation:

- Add and run only targeted M6 tests:
  - MemoryWriter grounding metadata tests.
  - Spatial redaction tests for memory writes.
  - `tests/k0/memory/test_time_place_index.py`.
  - UI inspector tests for temporal, spatial, grounding, and place registry sections.
  - Config/finalization tests proving flags are no longer needed after final closeout.

Deferral note:

- This can be deferred after M4/M5 if the immediate goal is live prompt grounding. It should not be skipped for production closeout because it owns durable memory semantics and final removal of transitional flags.

## Front Egress and Hop-Reduction Gaps

> Context: K1 Concierge today routes **every user-visible utterance through Front**.
> Front is both the *conversation actor* (persona, affect, history, narration) and
> the *sole egress channel* to the user. This conflation forces every Back / Planner /
> Fabric utterance to round-trip through a Front LLM call. A 1-HIL task is **6 hops,
> ~7 LLM calls**; once Planner ships with 3 subtasks × 1 HIL each, the same request
> becomes **18 hops, ~25 LLM calls**.
>
> These gaps are the deload path for that bloat. They land **after** the
> Front-deloading whiteboard
> (`../../../whiteboard_front_deloading.md`) because that work:
>
> 1. Removes Front's hidden cognitive-write ReAct iterations (3-6 LLM calls per turn → 1-2).
> 2. Builds the `SectionUpdatePlan` → `BatchRequest` → writer_port path that
>    Back-as-egress will reuse for post-turn `history_active` projection.
> 3. Establishes the `FrontPromptContextProjection` layer that future
>    worker-speaker hand-offs can reuse.
>
> Each entry below states its dependency on whiteboard deliverables explicitly.
> Acceptance criteria record both **hop-count delta** and **regression test boundary**.
>
> Architectural framing: **Front is the conversation actor, not the egress actor.**
> Anybody (Back, Planner, Fabric agent) can be an egress source under the same
> mandate (LLM-authored, sanitized at egress, recorded to `history_active`) without
> needing Front to rewrite them.

### GAP-EGRESS-001: FSM History Sink Is Front-Only and Silently Drops Fallback Turns

Status: Open
Risk: High

Current behavior:

- `ConciergeController._on_response_final` (file: `k1/concierge/fsm/controller.py`, ~L4216-L4232) gates `history_active.add_turn(...)` behind four conditions:
  `if self._history_sink and text and self._current_turn_user_text and not is_fallback`.
- `is_fallback` is true whenever the Front react_loop returns `front_degenerate_fallback` ("Let me think about that for a moment.") or `front_budget_fallback` ("Let me get back to you on that.").
- The gate `self._current_turn_user_text` is empty for event-driven turns (PRESENT/WEAVE/HITL_RELAY initiated by Back results, not user input). Those turns are also dropped from history.
- `factory.py:595-617` wires the sink with a silent `except: pass`, so a wiring failure is invisible.
- Observed live in `logs.txt` (2026-05-24 19:14:49): sink IS attached, but a HITL_RESOLVE turn with degenerate Front output created a visible chat reply that was excluded from `history_active`. The next turn's Front prompt had no record of the prior exchange → user perceived "no continuity."
- After the 2026-05-24 fix in `k1/concierge/actors/front.py`, non-HITL_RELAY modes (HITL_RESOLVE / WEAVE / PRESENT / ERROR / CANCEL) now suppress publish of canned fallback strings entirely (so `_on_response_final` doesn't fire), but the underlying gate logic is still fragile and Front-only.

Evidence boundary:

- `k1/concierge/fsm/controller.py`: `_on_response_final(...)`, `_history_sink`, `set_history_sink(...)`, `_current_turn_user_text`, `_write_history(...)`.
- `k1/concierge/factory.py`: silent-swallow wiring of `history_active` section.
- `k1/sessionstate/sections/history_active.py`: `add_turn(...)`, `get_typed_entries(...)`.
- `k1/concierge/actors/front.py`: post-2026-05-24 suppression of canned fallback per mode.

Required outcome:

- FSM `history_active` write path must accept turns from any actor (Front, Back, Planner, Fabric), not only Front response.final.
- Remove the `not is_fallback` gate. If a turn became user-visible, it must be in history. Mandate enforcement against canned strings belongs upstream at the producer (already done in `front.py` for non-HITL_RELAY modes); the sink must trust its input.
- Loosen the `_current_turn_user_text` gate so event-driven turns (no prior user text) still write the assistant side. Use sentinel `user_message=""` or `<event:topic.name>` where appropriate.
- Replace silent `except: pass` in factory wiring with `logger.warning` and expose `controller.has_history_sink()` for runtime health.

Dependencies:

- **Soft dependency on whiteboard `SectionUpdateClassifier`**: once the classifier owns `history_active` post-turn writes, this gap becomes "wire the classifier so it fires regardless of egress producer."
- Must precede GAP-EGRESS-003 (Back-as-egress) because Back's direct publish must land in `history_active` for Front to see continuity on the next turn.

Validation:

- Add `tests/k1/concierge/fsm/test_history_sink_multi_producer.py`:
  - Front response.final → history_active gains 1 typed entry.
  - Back-published response.final (synthetic) → history_active gains 1 typed entry.
  - Event-driven PRESENT turn with empty `_current_turn_user_text` → assistant side recorded.
  - Wiring missing → factory emits `logger.warning`; `controller.has_history_sink()` returns False.

Hop-count delta: 0 (correctness fix; precondition for other EGRESS gaps).

### GAP-EGRESS-002: Egress Sanitization Lives in Front Only

Status: Open
Risk: High

Current behavior:

- Front strips leaked reasoning / system blocks / Back frames inline in `front_handler` (`k1/concierge/actors/front.py`, calls to `_strip_leaked_reasoning(...)`, `_strip_leaked_system_blocks(...)`, `_strip_leaked_back_frame(...)`).
- These helpers are imported and applied per-mode by Front; no other actor calls them before publish.
- If Back or any future worker publishes user-visible text directly, none of these sanitizers run.
- Result: today the kernel cannot safely let any actor besides Front publish to the user, even though the underlying scrubbing logic is pure-functional and reusable.

Evidence boundary:

- `k1/concierge/actors/front.py`: `_strip_leaked_reasoning`, `_strip_leaked_system_blocks`, `_strip_leaked_back_frame`.
- `k1/concierge/bus/builders.py`: response envelope builders (no sanitization).
- `k1/bus/middleware/`: existing middleware layer where an `egress_sanitizer` could be added.

Required outcome:

- Promote leak-scrubbers into a bus-side egress middleware module `k1/concierge/bus/egress_sanitizer.py` (or similar).
- Middleware activates on any envelope targeting `k1.session.response.final.v1` / `k1.session.response.stream.v1` regardless of producer.
- Front handler loses inline scrubbing (single source of truth in middleware).
- Middleware exposes a list of registered sanitizers so additional patterns (PII, profanity per policy, etc.) can be added without touching producers.

Dependencies:

- Precondition for GAP-EGRESS-003, GAP-EGRESS-007, GAP-EGRESS-008 (any actor other than Front publishing user text).
- Independent of whiteboard plan; can land before or after.

Validation:

- Add `tests/k1/concierge/bus/test_egress_sanitizer_middleware.py`:
  - Reasoning-leak text submitted by any producer → middleware scrubs → final envelope clean.
  - System-block leak submitted by Back-synthetic publisher → scrubbed.
  - Front handler no longer needs to call sanitizers locally (regression check).

Hop-count delta: 0 (precondition; enables GAP-EGRESS-003).

### GAP-EGRESS-003: Back Has No Direct-Speak Protocol During HIL (Worker Speaker Protocol)

Status: Open
Risk: Critical

Current behavior:

- Back's `submit_result(needs_human, ...)` publishes `k1.hil.request.v1`.
- FSM/HIL routes the request to Front; Front enters `HITL_RELAY` and rephrases the question via a Front LLM call.
- User answers in chat → routed to Front; Front enters `HITL_RESOLVE`, emits `task.resume` → Back resumes.
- Two extra Front hops per HIL round, each with its own ReAct loop, prompt build, and (frequently) a degenerate retry.
- Total today for 1-HIL task: **6 hops**, ~7 LLM calls. Verified in `logs.txt` 2026-05-24 boot.

Evidence boundary:

- `k1/concierge/actors/back.py`: `submit_result(needs_human, ...)`, `_resolve_needs_human_in_process(...)`.
- `k1/concierge/actors/front.py`: `front_handler(...)` mode=HITL_RELAY / HITL_RESOLVE branches.
- `k1/concierge/prompt/mode.py`: `PromptMode.HITL_RELAY`, `PromptMode.HITL_RESOLVE`.
- `k1/hil/service.py`: `_request(...)`, `_pending`.
- `k1/concierge/fsm/controller.py`: FSM states `LISTENING / DISPATCHING / CLARIFYING_WORKER`.

Required outcome:

- Define a **Worker Speaker Protocol**:
  - Add `voice_token` field to `submit_result(...)` payload. When present and HIL service validates, Back's `hil_question` text is published directly as `k1.session.response.final.v1` by an egress proxy.
  - Add FSM state `WORKER_SPEAKING` representing "a worker actor currently owns the chat mic." Front does not invoke LLM while in this state.
  - Define hand-off back to Front: when HIL is resolved (user answer received), or when user interrupts mid-HIL (Front reclaims for INTERRUPT mode).
  - Route user answer in `WORKER_SPEAKING` state directly to the suspended task as a `task.resume` envelope without invoking Front LLM. Front receives a notification turn for history bookkeeping only (no LLM call).
- Define a single-speaker lock and a FIFO queue for the case where multiple workers want the mic concurrently (Planner subtasks, parallel Fabric calls).
- Define interrupt protocol: a user input arriving in `WORKER_SPEAKING` that is **not** an answer to the pending HIL (heuristic: arrives faster than expected, contains imperative verb, or matches cancel/redirect patterns) forces Front to reclaim the mic with mode INTERRUPT; the suspended task is informed via `task.interrupted` so it can decide to resume, restart, or cancel.

Dependencies:

- **Hard dependency on GAP-EGRESS-001** (multi-producer history sink) — Back's direct publish must land in `history_active`.
- **Hard dependency on GAP-EGRESS-002** (egress sanitizer middleware) — Back-published text must be scrubbed.
- **Soft dependency on whiteboard plan**: classifier post-turn writes pick up Back-published turns for cognitive section updates; without classifier, Front would still need a courtesy LLM hop to update beliefs/scoreboard.
- Should land after whiteboard plan completes its M0/M1 milestones (classifier infrastructure live).

Validation:

- Add `tests/k1/concierge/test_worker_speaker_protocol.py`:
  - Back with valid `voice_token` publishes hil_question; user sees text without Front LLM call.
  - User answer in `WORKER_SPEAKING` state routes directly to `task.resume`; Front sees notification turn only.
  - User interrupt during `WORKER_SPEAKING` reclaims mic; suspended task receives `task.interrupted` envelope.
  - Two workers concurrently request mic → second queues; assertion on FIFO order.
- Add `tests/k1/concierge/fsm/test_worker_speaking_state.py`:
  - FSM transitions `DISPATCHING → WORKER_SPEAKING → CLARIFYING_WORKER → LISTENING` for full HIL cycle.
  - Stale Front HIL envelopes do not bypass the lock.
- Update `tests/k1/concierge/test_front_event_fallbacks.py` to assert HITL_RELAY remains valid as a **fallback-only** mode (when `voice_token` absent or invalid).

Hop-count delta:

- 1-HIL task: **6 → 3 hops** (Front dispatch, Back full cycle including HIL, optional Front PRESENT).
- LLM calls: 7 → 3-4.
- 3-subtask Planner with 1 HIL each: 18 → 8 hops.

### GAP-EGRESS-004: PRESENT Mode Fires on Every Back Completion

Status: Open
Risk: High

Current behavior:

- Back's `submit_result(complete, final_answer="...")` always triggers FSM to invoke Front in PRESENT mode.
- Front then runs a ReAct loop just to wrap or restate Back's already-user-ready `final_answer`.
- Adds 1 hop and 1-2 LLM calls per task. For deterministic-result tools (calendar add, reminder set, settings change), Back's `final_answer` is already complete and natural; rewrap is pure overhead.
- Worse: rewrap can degrade or contradict Back's output (paraphrase drift), and degenerate retries can publish kernel-canned fallbacks (recently mitigated by 2026-05-24 fix but logic still active).

Evidence boundary:

- `k1/concierge/actors/back.py`: `submit_result(...)` payload shape; no `needs_narration` flag.
- `k1/concierge/fsm/controller.py`: PRESENT routing on `task.complete`.
- `k1/concierge/prompt/mode.py`: `PromptMode.PRESENT` with iter cap 3, tools cap 2.
- `k1/concierge/actors/front.py`: PRESENT mode branch in `front_handler`.

Required outcome:

- Add `needs_narration: bool = False` (or richer `narration_policy: "skip" | "wrap" | "summarize"`) to `submit_result` payload.
- Back sets `needs_narration=True` only when:
  - `final_answer` is structured data (JSON, table) that needs prose framing.
  - Task touched persona-sensitive content where Front's style adds value.
  - Multi-step task summary across subtasks is needed.
- Otherwise FSM publishes Back's `final_answer` directly (via worker speaker channel from GAP-EGRESS-003, or via a deterministic "passthrough" presenter that adds zero text).
- Default `needs_narration` must be `False` to flip the default policy.

Dependencies:

- Soft dependency on GAP-EGRESS-002 (sanitizer) and GAP-EGRESS-003 (worker speaker channel).
- Independent of whiteboard.

Validation:

- Add `tests/k1/concierge/test_back_present_opt_in.py`:
  - Back result with `needs_narration=False` → no Front PRESENT hop; user sees Back's `final_answer` verbatim.
  - Back result with `needs_narration=True` → Front PRESENT runs and wraps.
  - Migrate existing PRESENT tests to set `needs_narration=True` explicitly (regression).
- Hop-count metric assertion: deterministic-tool tasks complete in **≤ 2 hops** (dispatch + Back).

Hop-count delta:

- Simple-task path: **3 → 2 hops**, 3-6 → 2-4 LLM calls.
- 3-subtask Planner: each subtask saves 1 hop → -3 hops baseline.

### GAP-EGRESS-005: HITL_RELAY Default Path Still Pays a Front LLM Call

Status: Open
Risk: Medium

Current behavior:

- After 2026-05-24 fix in `k1/concierge/actors/front.py` (~L1789), HITL_RELAY falls back to Back's `hil_question` verbatim **only when** Front LLM produces empty or canned fallback text.
- The default path still invokes Front LLM to "rephrase" Back's question, often degenerating and triggering the substitution anyway.
- Each HIL round pays 1 unnecessary Gemini call (sometimes 2 with degenerate retry).

Evidence boundary:

- `k1/concierge/actors/front.py` L1784-1800 (post 2026-05-24): substitution branch.
- `k1/concierge/prompt/mode.py`: `PromptMode.HITL_RELAY` with iter cap 2, tools cap 0 — already minimal.
- Test: `tests/k1/concierge/test_front_event_fallbacks.py::test_hitl_relay_falls_back_to_back_question_when_front_llm_empty`.

Required outcome:

- Promote verbatim substitution to **default** path: if Back's `hil_question` is non-empty and passes a "user-ready" heuristic (length, no template markers, no JSON), publish it directly without a Front LLM call.
- Reserve Front rephrase only for cases where Back's question carries `style_hint="rephrase"` or matches policy criteria (sensitive content, accessibility needs).
- This becomes mostly subsumed by GAP-EGRESS-003 (worker speaker protocol). Until that lands, this is the cheap interim win.

Dependencies:

- Independent of whiteboard.
- Largely supplanted by GAP-EGRESS-003 once it lands; tracked separately as the interim gain.

Validation:

- Update `tests/k1/concierge/test_front_event_fallbacks.py`:
  - `test_hitl_relay_default_passes_through_back_question_without_llm` — assert react_loop is **not** invoked when Back's `hil_question` is user-ready.
  - Keep existing fallback test as the rephrase-on-style-hint case.

Hop-count delta:

- Per HIL round: -1 LLM call (the rephrase). Hop count unchanged unless GAP-EGRESS-003 also lands.

### GAP-EGRESS-006: WEAVE and PRESENT Duplicate Mode Surface

Status: Open
Risk: Low

Current behavior:

- `PromptMode.WEAVE` and `PromptMode.PRESENT` both serve the same user-facing semantic: "deliver a Back result to the user."
- They differ only in whether the user is mid-conversation (`WEAVE`) or has been waiting (`PRESENT`).
- Each carries duplicated prompt scaffolding, SS_READ_CONFIGS entries, scenario data extraction, and per-mode tests.

Evidence boundary:

- `k1/concierge/prompt/mode.py`: both modes defined with similar TOOL_ALLOWLIST and SS_READ_CONFIGS.
- `k1/concierge/prompt/builder.py`: per-mode prompt fragments.
- `k1/concierge/actors/front.py`: dual handling.

Required outcome:

- Merge into single `PromptMode.DELIVER` with payload field `is_async: bool` (True = WEAVE-style, False = PRESENT-style).
- Single prompt fragment with conditional `is_async` block.
- Reduces TOOL_ALLOWLIST surface and prompt-mode count from 10 to 9.

Dependencies:

- Should land **after** GAP-EGRESS-004 (most PRESENT/WEAVE invocations gone once narration is opt-in).
- Independent of whiteboard.

Validation:

- Refactor: replace `PromptMode.WEAVE` / `PromptMode.PRESENT` usage with `PromptMode.DELIVER` + flag.
- Migrate `tests/k1/concierge/test_front_event_fallbacks.py::test_weave_*` and `test_present_*` to single parameterized fixture.
- Update `SS_READ_CONFIGS` tests.

Hop-count delta: 0 (codepath cleanup; minor LLM-call savings from simpler prompt).

### GAP-EGRESS-007: Planner Subtask Delivery Has No Aggregation Path

Status: Open
Risk: High

Current behavior:

- Today: no Planner. Each Back dispatch is independent → one PRESENT per task.
- Once Planner ships, a single user request may produce N subtasks (3-10 typical), each completing asynchronously, each triggering a PRESENT hop, each running a Front LLM call.
- 3 subtasks × 1 HIL each × current architecture = **18 hops, ~25 LLM calls** for one user request (estimated from documented per-mode iter caps in `k1/concierge/prompt/mode.py:177-199`).

Evidence boundary:

- `k1/concierge/planner/` (not yet wired; per `docs/plans/` Planner milestone).
- `k1/concierge/orchestrator/` (similar — pending).
- `k1/concierge/fsm/controller.py`: PRESENT routing per-task-complete.
- `k1/concierge/actors/front.py`: per-completion handler.

Required outcome:

- Define **Planner Delivery Aggregator**:
  - When a `plan_id` correlates N subtasks, individual `task.complete` envelopes are buffered and only the final completion (or a periodic flush, e.g. 2s idle or progress milestone) triggers a single `PRESENT`/`DELIVER` hop.
  - Aggregator output is structured `subtask_results: [...]` that Front (or a passthrough presenter) summarizes once.
  - Buffer drains immediately on plan-level error, plan-level cancel, or user input arriving mid-plan.
- Integrates with GAP-EGRESS-003 (worker speaker channel) and GAP-EGRESS-004 (narration opt-in).

Dependencies:

- **Hard dependency on Planner milestone landing** (currently planned, not implemented).
- **Hard dependency on GAP-EGRESS-003 and GAP-EGRESS-004**.
- **Soft dependency on whiteboard** for classifier handling of multi-result turns.

Validation:

- Add (when Planner lands) `tests/k1/concierge/planner/test_delivery_aggregator.py`:
  - 3 subtasks complete within 100ms → 1 PRESENT hop with all 3 in `subtask_results`.
  - 1 subtask errors → buffer flushes immediately with partial results.
  - User input arrives mid-plan → buffer flushes; INTERRUPT mode handles user.
- Hop-count regression: N-subtask plan with no HIL must complete in ≤ 3 hops total (dispatch + N parallel Back + 1 aggregated delivery).

Hop-count delta:

- 3-subtask plan with HIL: **18 → 8** (combined with GAP-EGRESS-003/004).
- 5-subtask plan no HIL: **6 → 3** (was 1 dispatch + 5 PRESENT; becomes 1 dispatch + 1 aggregator + 1 delivery).

### GAP-EGRESS-008: Fabric Agents Cannot Speak Directly

Status: Open
Risk: Medium

Current behavior:

- Fabric agents (Spatial, Temporal, Grounding, and future capabilities) operate as tools or services consumed by Front/Back.
- If a Fabric agent ever needs to surface user-visible text (e.g. Spatial requests location permission, Temporal flags ambiguous date), the only path today is round-trip through Front.
- This is identical to the HIL bloat (GAP-EGRESS-003) but for a different worker class.

Evidence boundary:

- `k1/fabric/` agents (Spatial, Temporal, Grounding).
- No fabric egress channel exists in `k1/bus/` or `k1/concierge/bus/`.

Required outcome:

- Extend the **Worker Speaker Protocol** (GAP-EGRESS-003) to issue `voice_token`s to Fabric agents per-invocation under capability gate.
- Fabric agents that need to ask the user route through the same task-widget or chat channel (per GAP-EGRESS-009) without invoking Front LLM for rephrase.
- Token issuance is capability-bound: only specific Fabric agents with `voice_capability=True` flag in their registry record can request.

Dependencies:

- **Hard dependency on GAP-EGRESS-003**.
- **Hard dependency on GAP-EGRESS-002** (sanitizer).
- Independent of whiteboard.

Validation:

- Add (when first Fabric agent needs egress) `tests/k1/fabric/test_fabric_voice_token.py`:
  - Capability-gated Fabric agent receives `voice_token`, publishes user-visible text directly.
  - Non-capable agent attempting publish → rejected by egress middleware.

Hop-count delta: equivalent to GAP-EGRESS-003 per Fabric utterance: 2 → 0.

### GAP-EGRESS-009: Single Chat Channel Cannot Carry Concurrent HIL Surfaces

Status: Open
Risk: Medium

Current behavior:

- All HIL is funneled through the chat thread.
- With Planner + concurrent Fabric calls, multiple HIL requests may exist simultaneously. The chat thread serializes them, blocking later requests until earlier are resolved.
- UX cost: user can be answering Q1 while Q2 (different subtask) silently times out.

Evidence boundary:

- `ui/web/` UI is single chat-stream surface.
- `ui/web/static/app.js` already separates `capability_gate` / `approval` / `override` (widget lane) from `needs_human` / `clarification` (chat lane) per GAP-HIL-004 closure.

Required outcome:

- Extend the widget lane to optionally carry free-text HIL with per-request widget rendering.
- HIL request payload gains `channel_hint: "chat" | "widget"` set by the producer (Planner/Fabric defaults to "widget", solo Back HIL defaults to "chat").
- Widget displays question text, captures user free-text input, posts response to `k1.hil.response.v1`.
- Each widget is independent; multiple widgets render concurrently.
- "You have N pending tasks needing input" indicator pinned in main chat.
- Voice/mobile/headless surfaces downgrade widget HIL to chat HIL automatically.

Dependencies:

- **Hard dependency on Planner milestone**.
- **Hard dependency on GAP-EGRESS-003** (worker speaker protocol carries `channel_hint`).
- UI work in `ui/web/static/`.

Validation:

- Add `tests/k1/hil/test_multi_channel_routing.py`:
  - HIL with `channel_hint="widget"` does not produce a chat envelope.
  - Two concurrent widget HILs do not interfere (independent timeouts, independent responses).
  - Voice surface downgrades all widget HIL to chat HIL.
- UI tests under `ui/web/` if applicable.

Hop-count delta: 0 directly (UX gain); enables Planner concurrency without serialization.

### GAP-EGRESS-010: Trivial User Inputs Always Invoke Front LLM

Status: Open
Risk: Low

Current behavior:

- Every Front STANDARD turn invokes Gemini, even for trivial confirmations ("yes", "ok", "cancel", "nevermind").
- These inputs already have clear routing semantics in HITL_RESOLVE / CANCEL detection, but the routing decision itself is made by `determine_mode(...)`, which then still hands off to a full Front LLM call.
- Mandate constraint: "all visible text must be LLM-authored." A deterministic router that **decides which mode to enter** is mandate-compliant; the visible response is still LLM-authored (Back's `final_answer`, HIL `hil_question`, etc.).

Evidence boundary:

- `k1/concierge/prompt/mode.py`: `determine_mode(...)` — already deterministic for mode selection.
- `k1/concierge/fsm/arbiter.py`: cancel/defer keyword sets exist.
- `k1/concierge/actors/front.py`: every mode enters react_loop.

Required outcome:

- Define `PreLLMRouter` that handles trivial deterministic cases before invoking react_loop:
  - Confirmation tokens ("yes", "ok", "confirmed") when a pending action awaits → emit `task.confirm` envelope, skip LLM.
  - Cancel tokens ("cancel", "nevermind", "stop") → emit `task.cancel`, skip LLM.
  - Backchannels ("got it", "uh huh") → skip publish entirely.
- All matches still publish a Back/worker-authored response if appropriate (mandate-compliant).
- High-tier mode (STANDARD with no pending action, INTERRUPT, CLARIFY_*) always proceeds to react_loop.

Dependencies:

- Independent of whiteboard.
- Independent of all other EGRESS gaps (orthogonal).

Validation:

- Add `tests/k1/concierge/test_pre_llm_router.py`:
  - "yes" with pending action → no Gemini call, `task.confirm` published.
  - "yes" with no pending action → react_loop runs as normal.
  - "cancel" → no Gemini call, `task.cancel` published.
  - Backchannel → no Gemini call, no publish.
- Hop-count metric: confirmation responses complete in 0 LLM calls.

Hop-count delta: -1 LLM call per trivial input. No structural hop change.

### EGRESS Roadmap (consolidated)

Recommended landing order (after whiteboard plan):

1. **GAP-EGRESS-001** (multi-producer history sink) — precondition for any non-Front producer.
2. **GAP-EGRESS-002** (egress sanitizer middleware) — precondition for any non-Front producer.
3. **GAP-EGRESS-005** (HITL_RELAY default substitution) — cheap interim win, independent.
4. **GAP-EGRESS-004** (PRESENT opt-in via `needs_narration`) — high-value, low-risk.
5. **GAP-EGRESS-010** (deterministic pre-LLM router) — independent, can land any time.
6. **GAP-EGRESS-003** (worker speaker protocol + `WORKER_SPEAKING` state) — the keystone.
7. **GAP-EGRESS-006** (WEAVE/PRESENT merge into DELIVER) — cleanup after #4 lands.
8. **GAP-EGRESS-008** (Fabric voice tokens) — opportunistic once #3 lands.
9. **GAP-EGRESS-009** (multi-channel HIL widgets) — gated by Planner milestone.
10. **GAP-EGRESS-007** (Planner delivery aggregation) — gated by Planner milestone.

Hop-count summary (current → target):

| Scenario | Today (hops / LLM calls) | After EGRESS roadmap (hops / LLM calls) |
| --- | --- | --- |
| Simple chat | 1 / 1-3 | 1 / 1-3 (unchanged) |
| Simple deterministic task | 3 / 3-6 | **2 / 2-3** |
| Task with 1 HIL | 6 / 6-12 | **3 / 3-4** |
| Task with 2 HIL rounds | 9 / 9-15 | **3 / 3-5** |
| 3-subtask Planner, 1 HIL each | 18 / ~25 | **5-6 / 7-10** |
| 5-subtask Planner, no HIL | 7 / 8-14 | **3 / 3-5** |
| Confirmation ("yes") | 1 / 1 | **0 / 0** |

## Run Discipline

- Run only targeted tests for touched code and directly related regression files.
- Do not run the full `tests/k1/kernel/` suite.
- Do not run the full Fabric suite without an explicit request.
- For live-kernel probes, prefer sequential targeted runs to avoid shared-state interference.
