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

### GAP-HIL-001: Single Consumer Blocks Front While Back Waits

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

Status: Open
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

## Run Discipline

- Run only targeted tests for touched code and directly related regression files.
- Do not run the full `tests/k1/kernel/` suite.
- Do not run the full Fabric suite without an explicit request.
- For live-kernel probes, prefer sequential targeted runs to avoid shared-state interference.
