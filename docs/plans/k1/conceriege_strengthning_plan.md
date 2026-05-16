# Concierge Hardening Plan

<!-- markdownlint-disable MD036 -->
We should run this as a milestone train, not one huge refactor. The goal is: Front and Back remain distinct actors, but the user experiences one continuous conversational mind. The control plane becomes explicit, typed, replayable, and testable.

## M0 -- Contract Freeze And Evidence Cleanup

**Purpose:** Make the tracker and open-issue docs match the code before behavior changes begin. M0 is mostly documentation and focused probe work. Do not refactor runtime code in this milestone unless a verification probe proves the code does not match the statements below.

**State/API coherence rule for M0:** A tracker row may be marked closed only when the production symbol exists, the runtime call path reaches it, and a focused test or existing live probe proves the behavior. Do not close a row because a design doc says it should exist.

**Epic M0.E1 -- Reconcile Tracker With Code**

### Issue M0.E1.I1 -- ReAct tool timeout is implemented; lock it with focused tests

**Files to inspect/change:**

- `k1/concierge/react/loop.py`
- `tests/k1/concierge/react/test_loop_tool_timeout.py` (create if absent)
- `docs/architecture/kernel_sweep_status.md`

**Current code fact:** `react_loop()` defines an inner `_run_tool()` that dispatches tools through `asyncio.wait_for(...)`. It reads `get_config().react.tool_timeout_ms` for normal tools and uses the larger HIL-aware timeout for `invoke_capability` and `batch_invoke_capabilities`.

**Implementation directive:**

- Add a focused unit test that sets `react.tool_timeout_ms` to a tiny value, uses a fake `ToolDispatcher.dispatch()` that never returns, and asserts the loop returns a `ToolResult` with `status="error"` and an error string containing `tool_timeout`.
- Add a second focused unit assertion for the HIL branch: when the tool name is `invoke_capability` or `batch_invoke_capabilities`, the effective timeout must be `max(tool_timeout_ms, hil_capability_gate_timeout_ms + 30000ms)`.
- Update any tracker/open-issue wording that still says ReAct tool timeout is missing. The correct tracker language is: timeout exists; focused coverage was added in M0.

**API contract:** timeout must never raise out of `react_loop()` as a raw `asyncio.TimeoutError`. It must be converted into a `ToolResult` so Back can either repair, retry, or fail in a typed way.

**Run:** `pytest tests/k1/concierge/react/test_loop_tool_timeout.py -v`

### Issue M0.E1.I2 -- `ResponseDelivered` exists; document remaining delivery-intent semantics

**Files to inspect/change:**

- `k1/concierge/events/conversation.py`
- `k1/concierge/events/registry.py`
- `k1/concierge/fsm/controller.py`
- `k1/concierge/ledger/recovery.py`
- `k1/concierge/OPEN_ISSUES.md`
- `tests/k1/concierge/test_m01_event_validator.py`
- `tests/k1/concierge/fsm/test_response_delivered.py` (create if absent)

**Current code fact:** `ResponseDelivered` exists, is registered as `conversation.response.delivered.v1`, and is appended by `_on_response_final()` before `_execute_response_final_decision(...)` runs.

**Implementation directive:**

- Update `k1/concierge/OPEN_ISSUES.md` if it still says `ResponseDelivered` does not exist.
- In `docs/architecture/kernel_sweep_status.md`, do not track this as "missing." Track any remaining concern as "delivery intent vs delivery completion semantics."
- Add a focused controller test that uses a fake ledger and a spy around `_execute_response_final_decision(...)`. The test must prove `ResponseDelivered` is appended before the side-effect executor is called.
- Do not rename the event in M0. If a later milestone wants separate `ResponseDeliveryIntent` and `ResponseDeliveryCompleted`, create that as a new issue after the tracker is corrected.

**State/API coherence:** recovery currently treats `conversation.response.delivered.v1` as proof that delivery should not be replayed. Because the event is written before side effects, this is intentionally a delivery-intent marker. M0 must document that fact instead of pretending it is post-stream confirmation.

**Run:** `pytest tests/k1/concierge/test_m01_event_validator.py tests/k1/concierge/fsm/test_response_delivered.py -v`

### Issue M0.E1.I3 -- Update stale tracker and open-issue rows

**Files to change:**

- `docs/architecture/kernel_sweep_status.md`
- `k1/concierge/OPEN_ISSUES.md`
- `k1/concierge/STATE.md` if it repeats stale status

**Implementation directive:**

- Keep `M1-L7` as xfail/open: `EpisodicCompressor` is not wired into the live `ExperienceLayer` path.
- Keep `M1-X9` as xfail/open: `WriteElisionGate` is still design-only.
- `M1-X10` is closed by M1: legacy HITL now emits bridge-only `k1.hil.response.v1` before `task.resume.v1`.
- Close or annotate any row claiming ReAct tool timeout is absent.
- Close or annotate any row claiming `ResponseDelivered` is absent.

**Acceptance:** a reviewer can open the tracker and know exactly which gaps are real, which are stale, and which are deliberately deferred to M1-M4.

### Issue M0.E1.I4 -- Publish the true remaining M1-M4 gap register

**Files to change:**

- `docs/architecture/kernel_sweep_status.md`
- `docs/plans/k1/conceriege_strengthning_plan.md`

**Implementation directive:** add a short "true gap register" note that points to these future milestones:

- HIL protocol drift and structured Front resolution -> M1.
- Typed Back/Front handoff frames -> M2.
- ReAct checkpoint/control events/tool records -> M3.
- Weave side-effect split, queue coherence, and proactive fill -> M4.
- `WriteElisionGate` and `EpisodicCompressor` remain later M5/M6 work unless pulled forward explicitly.

**Acceptance:** the next implementer does not spend time rediscovering which items are stale.

**M0 completion evidence (May 2026):**

- ReAct tool timeout is implemented in `k1/concierge/react/loop.py` and locked by `tests/k1/concierge/react/test_loop_tool_timeout.py`.
- `ResponseDelivered` exists, is registered, and is written before `_execute_response_final_decision(...)`; `tests/k1/concierge/fsm/test_response_delivered.py` locks the delivery-intent ordering.
- `k1/concierge/OPEN_ISSUES.md` now marks ISSUE-C03 and ISSUE-C04 closed with residual semantics documented.
- `docs/architecture/kernel_sweep_status.md` now carries the true remaining Concierge gap register for M1-M6.

## M1 -- HIL Unification

**Purpose:** Human-in-the-loop must feel like one conversation, even when a Back worker, Fabric, Planner, or Orchestrator is waiting for a human decision.

**Canonical runtime flow:**

- Unified path: `HumanInTheLoopService._request(...)` publishes `k1.hil.request.v1`; `ConciergeController._on_hil_request(...)` stores pending HIL metadata; `front_handler(...)` renders `HITL_RELAY`; user input enters `HITL_RESOLVE`; Front publishes `k1.hil.response.v1`; `HumanInTheLoopService._on_response(...)` resolves the waiting future. No `task.resume.v1` is emitted on this path.
- Legacy path: Back emits `task.suspended.v1`; FSM moves to `CLARIFYING_WORKER`; Front asks the user; user reply causes `task.resume.v1`; `back_resume_handler(...)` resumes from stored context. This path exists only for recovery, legacy tests, or no-HIL-service fallback.

**State/API coherence rule for M1:** For one human decision, exactly one canonical `hil_request_id` must exist. Unified path consumes it through `k1.hil.response.v1`. Legacy bridge may also emit a compatibility `k1.hil.response.v1`, but must mark it as bridge-only and must still resume Back exactly once.

**M1 completion evidence (May 2026):**

- Unified HIL remains service-owned: `TOPIC_HIL_REQUEST` routes to the FSM for presentation state, while `TOPIC_HIL_RESPONSE` is not routed to the FSM and resolves through `HumanInTheLoopService`.
- Legacy `task.suspended.v1` now persists a compatibility `HILEnvelope` with `legacy_bridge=True`; Front publishes the bridge-only `k1.hil.response.v1` before the legacy `task.resume.v1`.
- Front `HITL_RESOLVE` scenario data now carries `_hil_envelope`, HIL kind, options, side effects, pending HIL id, `legacy_bridge`, and `task_id`; `_build_resolution(...)` parses approval, capability gate, needs-human selection, override, and clarification answers into structured resolution fields.
- `back_resume_handler(...)` accepts both `react_history` and `findings_so_far` resume-context keys, so HILSubTask resume history is not dropped.
- Verification: `tests/k1/concierge/test_front_hil_unified_envelope.py` + `tests/k1/hil/test_service_front_roundtrip.py` (`55 passed`), `tests/k1/concierge/fsm/test_hil_resume_guard.py` (`1 passed`), `test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume` (`1 passed`), and `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` (`3 passed`).

**Epic M1.E1 -- Make Unified HIL The Live Path**

### Issue M1.E1.I1 -- Declare and enforce canonical HIL topics

**Files to inspect/change:**

- `k1/hil/topics.py`
- `k1/concierge/bus/topics.py`
- `k1/hil/service.py`
- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_front_hil_unified_envelope.py`

**Implementation directive:**

- Confirm both `k1/hil/topics.py` and `k1/concierge/bus/topics.py` use the exact strings `k1.hil.request.v1` and `k1.hil.response.v1`.
- In `ConciergeController._subscribe_all()`, keep `TOPIC_HIL_REQUEST` routed only to `_on_hil_request(...)`. Do not route `TOPIC_HIL_RESPONSE` to the FSM; the HIL service owns response future resolution.
- In `front_handler(...)`, keep the current split: when pending HIL contains a real `HILEnvelope`, publish `build_hil_response(...)` and do not call `emit_task_resume(...)`.
- Add/extend a test proving unified HIL response does not publish `TOPIC_TASK_RESUME` for the same `hil_request_id`.

**API contract:** `HILEnvelope.to_dict()` must contain `hil_request_id`, `kind`, `caller_key`, `trace_id`, `created_at_ms`, `timeout_ms`, and `payload`. `HILResponseEnvelope.to_dict()` must contain `hil_request_id`, `kind`, `responded_at_ms`, `payload`, and `timed_out`.

**Run:** `pytest tests/k1/concierge/test_front_hil_unified_envelope.py tests/k1/hil/test_service_front_roundtrip.py -v`

### Issue M1.E1.I2 -- Keep legacy suspension/resume as an explicit adapter

**Files to inspect/change:**

- `k1/concierge/actors/back.py`
- `k1/concierge/fsm/controller.py`
- `k1/concierge/protocols/hitl_persistence.py`
- `k1/concierge/protocols/hitl_wiring.py`
- `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py`

**Implementation directive:**

- Leave `_emit_back_result(..., status="suspended")`, `_on_task_suspended(...)`, `_on_task_resume(...)`, and `back_resume_handler(...)` in place.
- Add comments and docstrings that say this lane is legacy/recovery/no-HIL-service fallback only.
- Ensure every legacy suspended payload includes enough data for `back_resume_handler(...)`: `task_id`, `hil_type`, `question`, `options`, `react_history` or `react_checkpoint` after M3, and `original_task`.
- Do not allow new live code to call `task.suspended.v1` when `IHILPort` is available and the caller can await unified HIL in-process.

**State coherence:** legacy storage is task-keyed; unified storage is `hil_request_id`-keyed. The adapter must always record the mapping `task_id -> pending_hil_id` so dedup and recovery can reason about the same human decision.

**Run:** `pytest tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py -v`

### Issue M1.E1.I3 -- Add legacy compatibility response before resume

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/front.py`
- `k1/concierge/actors/front_hil_envelope.py` only if helper support is missing
- `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`

**Current behavior:** legacy HITL now goes `task.suspended.v1 -> user input -> bridge-only k1.hil.response.v1 -> task.resume.v1`, preserving protocol evidence before Back resumes. M1-X10 is no longer strict-xfail.

**Implementation directive:**

- In `_on_task_suspended(...)`, after creating the `HILSubTask`, also store a compatibility HIL envelope under task pending-HIL data. Use `hil_request_id = hil_subtask.pending_hil_id`, `kind = needs_human` unless the legacy `hil_type` maps more specifically, `caller_key = f"legacy:{task_id}"`, and payload containing `task_id`, `hil_type`, `question`, `options`, `side_effects`, `safety_band`, and `legacy_bridge=True`.
- In `front_handler(...)` HITL_RESOLVE post-loop, branch on pending HIL metadata:
  - Real unified envelope with no `legacy_bridge`: publish only `TOPIC_HIL_RESPONSE`.
  - Compatibility envelope with `legacy_bridge=True`: publish `TOPIC_HIL_RESPONSE` first, then call `emit_task_resume(...)` for Back.
  - No envelope: keep old fallback and publish only `task.resume.v1`.
- Make the test assert ordering: for the legacy bridge case, the first `TOPIC_HIL_RESPONSE` must appear before the first `TOPIC_TASK_RESUME` for the same `task_id`.

**API coherence:** compatibility responses must be valid `HILResponseEnvelope` payloads, but their `payload` must include `legacy_bridge=True` so `HumanInTheLoopService._on_response(...)` can ignore unknown bridge IDs without treating them as service-owned futures.

**Run:** `pytest tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume -v`

### Issue M1.E1.I4 -- Prevent unified/legacy double-resume

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_front_hil_unified_envelope.py`

**Implementation directive:**

- Extend `_hitl_responded_tasks` or add a sibling set keyed by `hil_request_id`, not only `task_id` and device id.
- In `_on_task_resume(...)`, after idempotency/topic guard and before Back delivery, check whether the pending HIL for that task has already been consumed by unified response. If consumed, log and return without delivering to Back.
- In Front HITL_RESOLVE, never publish both unified response and legacy resume unless pending HIL metadata explicitly says `legacy_bridge=True`.
- Add a focused test that manually sends both `TOPIC_HIL_RESPONSE` and `TOPIC_TASK_RESUME` for the same pending HIL and asserts Back receives only one resume path.

**State coherence:** `task_id`, `hil_request_id`, and `pending_hil_id` must all refer to the same decision. If any one has been marked resolved, the others must be treated as resolved.

**Epic M1.E2 -- Structured Front Resolution**

### Issue M1.E2.I1 -- Pass HIL metadata into HITL_RESOLVE scenario data

**Files to change:**

- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_front_hil_unified_envelope.py`

**Current behavior:** `_extract_scenario_data(..., PromptMode.HITL_RESOLVE, ...)` returns only `suspended_task_summary`, `original_question`, and `user_answer`. It drops the stored `_hil_envelope`, HIL kind, options, side effects, and pending id, so `_build_resolution(...)` cannot produce a typed answer.

**Implementation directive:**

- In the HITL_RESOLVE branch, read `pending_hil = _task_pending_hil_payload(suspended)`.
- Add these keys to the returned dict: `_hil_envelope`, `hil_type`, `hil_options`, `hil_side_effects`, `pending_hil_id`, `legacy_bridge`, and `task_id`.
- `hil_type` should prefer `_hil_envelope["kind"]` when present, then fall back to `pending_hil["hil_type"]`.
- Keep existing keys for backward compatibility.

**Acceptance:** a unit test can build a suspended task with pending HIL data and prove `_extract_scenario_data(HITL_RESOLVE, ...)` returns all keys required by `_build_resolution(...)`.

### Issue M1.E2.I2 -- Replace `_build_resolution(...)` stub with kind-aware parsing

**Files to change:**

- `k1/concierge/actors/front.py`
- `k1/concierge/protocols/hitl_flow.py` only if helper behavior is insufficient
- `tests/k1/concierge/test_front_hil_unified_envelope.py`

**Current behavior:** `_build_resolution(...)` returns `selected_option=None`, `target=None`, `approval=None`, and `additional_info=user_answer` for every HIL kind.

**Implementation directive:**

- Dispatch by `HILKind` using `_hil_envelope["kind"]` or `hil_type` from scenario data.
- For `clarification`, return an answer/additional-info resolution containing the user's free text.
- For `approval`, parse yes/no/modify/cancel. Reuse `parse_approval_resolution(...)` from `k1.concierge.protocols.hitl_flow` once you have normalized the raw user answer into a dict shape such as `decision=approve|reject|modify|cancel` and optional `modifications`.
- For `needs_human`, keep raw text as audit context and match the user's answer against `hil_options` when options exist.
- For `override`, match the selected alternative from the original envelope payload and set `selected_option`, `target`, and fallback text.
- For `capability_gate`, set `approval=True` for approve/yes/allow/ok and `approval=False` for reject/no/deny/block.
- Unknown kinds must fall back to clarification shape, never crash.

**API contract:** the dict returned by `_build_resolution(...)` must be acceptable to `build_hil_response_envelope_dict(...)` in `front_hil_envelope.py`. That helper maps `approval` to approval/capability-gate payloads, `selected_option` to override/needs-human choices, and `additional_info` to clarification text.

**Run:** `pytest tests/k1/concierge/test_front_hil_unified_envelope.py -v`

### Issue M1.E2.I3 -- Keep response builder as the only unified response serializer

**Files to inspect/change:**

- `k1/concierge/actors/front_hil_envelope.py`
- `k1/concierge/actors/front.py`

**Implementation directive:**

- Do not hand-build `HILResponseEnvelope` payloads in `front.py` for the unified path.
- Always call `build_hil_response_envelope_dict(incoming_envelope, resolution, raw_user_text=...)`.
- If a new HIL kind is added later, extend `_build_response_payload(...)` in `front_hil_envelope.py`, not the post-loop block in `front.py`.

**Acceptance:** tests verify `clarification`, `approval`, `needs_human`, `override`, and `capability_gate` all round-trip through `build_hil_response_envelope_dict(...)`.

### Issue M1.E2.I4 -- Feed approval and selection helpers instead of ad hoc string-only parsing

**Files to inspect/change:**

- `k1/concierge/protocols/hitl_flow.py`
- `k1/concierge/protocols/hitl_pipeline.py`
- `k1/concierge/actors/front.py`

**Implementation directive:**

- Use `parse_approval_resolution(...)` after normalizing the user's approval text into the dict it expects.
- Use `parse_selection_resolution(...)` when options contain stable ids/labels and `_build_resolution(...)` can produce a candidate `selected_option`.
- Do not call pipeline functions that require a full `HILResponse` object from Front unless you create that object with all required fields. Front's job is parsing the human answer, not executing pipeline side effects.

**State coherence:** raw user text is for audit and UI history. Back execution should read structured fields only.

## M2 -- Typed Actor Handoffs

**Purpose:** Back can be technical internally, but Front must receive typed presentation material rather than loose worker prose. This milestone prevents Back's scratchpad, JSON, tool traces, or `final_answer` from leaking into the user-visible voice.

**State/API coherence rule for M2:** Back owns execution facts. Front owns language. `final_answer` remains a legacy compatibility field only; new Front prompt paths consume typed frames.

**M2 completion evidence (May 2026):**

- `k1/concierge/actors/frames.py` now defines frozen/slotted `BackResultFrame`, `HILResolutionFrame`, and `WeavePresentationFrame` handoff types.
- Back complete payloads now include `frame` while preserving legacy `final_answer`, `results`, and `artifacts_created` fields.
- Front PRESENT and WEAVE scenario data now prefer typed frame facts/artifacts/next actions; WEAVE skips before ReAct when no concrete result summary exists.
- Front HIL resolution now builds `HILResolutionFrame` internally; unified HIL still uses `build_hil_response_envelope_dict(...)`, while legacy resume carries `resolution_frame` and Back consumes typed command fields instead of raw user text for approval/gate authority.
- Front final text cleanup now strips Back frame JSON, tool traces, scratchpad/iteration markers, and `<think>...</think>` blocks before publishing.
- Verification: `tests/k1/concierge/test_back_result_frame.py`, `test_front_present_frame.py`, `test_front_weave_frame.py`, `test_weave_presentation_frame.py`, `test_front_leak_guards.py`, `test_hil_resolution_frame.py`, and `test_back_resume_resolution_frame.py` (`14 passed`), plus existing `tests/k1/concierge/test_front_hil_unified_envelope.py` (`26 passed`). Diagnostics are clean on touched implementation and test files.

**Epic M2.E1 -- Back Result Frame**

### Issue M2.E1.I1 -- Introduce `BackResultFrame`

**Files to change:**

- `k1/concierge/actors/frames.py` (create)
- `k1/concierge/actors/back.py`
- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_back_result_frame.py` (create)

**Implementation directive:**

- Create a frozen/slotted frame type named `BackResultFrame`.
- Required fields: `task_id`, `status`, `result_type`, `facts`, `artifacts`, `confidence`, `blockers`, `suggested_next_action`, `tool_call_summaries`, and `raw_final_answer`.
- Add `to_dict()` and `from_dict()` methods. `from_dict()` must tolerate legacy payloads that only have `final_answer`, `results`, and `artifacts_created`.
- In `_emit_back_result(...)`, when `result.status == "complete"`, construct a frame from `ReactResult.data`, original task action, and `tool_call_summaries`. Add it to the existing `task.complete.v1` payload as `frame`. Keep old fields for compatibility.

**API contract:** `frame["task_id"]` must equal the task id in the task-complete envelope. `frame["raw_final_answer"]` is never user-presentable by itself.

**Run:** `pytest tests/k1/concierge/test_back_result_frame.py -v`

### Issue M2.E1.I2 -- Stop using Back `final_answer` as Front's primary presentation input

**Files to change:**

- `k1/concierge/actors/front.py`
- `k1/concierge/prompt/builder.py` if scenario keys are enumerated there
- Front prompt template files under `k1/concierge/prompt/` if templates require explicit keys
- `tests/k1/concierge/test_front_present_frame.py` (create)

**Implementation directive:**

- In `_extract_scenario_data(PRESENT, ...)`, read `payload["frame"]` using `BackResultFrame.from_dict(...)`.
- Return structured keys such as `task_facts`, `task_artifacts`, `task_confidence`, `task_blockers`, and `suggested_next_action`.
- Keep `task_result_summary` only as a fallback string derived from the frame. Do not pass raw `payload["final_answer"]` directly unless no frame exists.
- Update PRESENT prompt assembly so Front is asked to explain confirmed facts and next steps in its own voice.

**Acceptance:** a test sends a `task.complete.v1` payload whose `final_answer` is JSON-like worker text and whose frame has clean facts. The final Front prompt/scenario data must prefer frame facts.

### Issue M2.E1.I3 -- Make WEAVE consume frame data as well

**Files to change:**

- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_front_weave_frame.py` (create)

**Implementation directive:**

- In `_extract_scenario_data(WEAVE, ...)`, when iterating pending results, unwrap each result and check for `frame`.
- Build `results_summary` from `BackResultFrame.facts`, `artifacts`, and `suggested_next_action` when frame exists.
- Use legacy `action: final_answer` summary only if no frame is present.
- Preserve current web-search result expansion for `results` items.

**State coherence:** WEAVE must not invent facts. It can summarize frame facts and artifacts only.

### Issue M2.E1.I4 -- Add Back leakage guard before final response publish

**Files to change:**

- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_front_leak_guards.py` (create or extend)

**Implementation directive:**

- Add a helper near `_strip_leaked_reasoning(...)` and `_strip_leaked_system_blocks(...)` that removes or rejects Back-internal artifacts from user-visible text.
- Detect at least these patterns: JSON objects containing `task_id`, `final_answer`, `result_type`, `tool_call_summaries`; tool trace labels; `<think>...</think>` blocks; obvious iteration/scratchpad markers.
- Call the guard in the same final-cleaning path that currently strips leaked reasoning and system blocks.
- If stripping produces empty text in PRESENT/WEAVE, suppress the final response rather than publishing a blank or raw frame.

**Acceptance:** a test passes a response containing a serialized Back frame and verifies the published final text contains none of the frame keys.

**Epic M2.E2 -- HIL Resolution Frame**

### Issue M2.E2.I1 -- Introduce `HILResolutionFrame`

**Files to change:**

- `k1/concierge/actors/frames.py`
- `k1/concierge/actors/front.py`
- `k1/concierge/actors/front_hil_envelope.py`
- `tests/k1/concierge/test_hil_resolution_frame.py` (create)

**Implementation directive:**

- Add `HILResolutionFrame` with fields: `task_id`, `hil_request_id`, `kind`, `raw_user_text`, `selected_option`, `target`, `approval`, `additional_info`, `modifications`, and `legacy_bridge`.
- Add `to_resolution_dict()` for existing builders and `from_resolution_dict()` for compatibility.
- Change `_build_resolution(...)` to create a frame internally. During M2, callers may still pass `frame.to_resolution_dict()` to existing bus builders.

**API contract:** `raw_user_text` is audit/history only. Back resume and HIL service payloads must consume typed fields from `to_resolution_dict()`.

### Issue M2.E2.I2 -- Preserve raw user text without making it executable instruction

**Files to change:**

- `k1/concierge/actors/front.py`
- `k1/concierge/actors/front_hil_envelope.py`
- `k1/concierge/actors/back.py`

**Implementation directive:**

- In unified response, pass `raw_user_text` only through `build_hil_response_envelope_dict(..., raw_user_text=...)`.
- In legacy resume payload, include raw text under an audit-only key if needed, but make `back_resume_handler(...)` build its resume instruction from structured resolution fields.
- Update `back_resume_handler(...)` so it does not treat arbitrary raw user text as a direct instruction when typed fields are available.

**State coherence:** user text is evidence, not command authority. Approval/selection/override fields are command authority.

### Issue M2.E2.I3 -- Back resume consumes typed resolution only

**Files to change:**

- `k1/concierge/actors/back.py`
- `k1/concierge/protocols/hitl_wiring.py`
- `tests/k1/concierge/test_back_resume_resolution_frame.py` (create)

**Implementation directive:**

- In `back_resume_handler(...)`, prefer a `resolution_frame` key if present in the resume payload.
- Build the resume instruction from `kind`, `approval`, `selected_option`, `target`, `additional_info`, and `modifications`.
- Keep old `resolution` and `answer` fallback paths only for legacy payloads.
- If required typed fields are missing for approval/capability-gate, fail typed with `SUSPENSION_RESOLUTION_NOT_FOUND` instead of asking Back to infer from free text.

**Epic M2.E3 -- Weave Presentation Frame**

### Issue M2.E3.I1 -- Introduce `WeavePresentationFrame`

**Files to change:**

- `k1/concierge/actors/frames.py`
- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_weave_presentation_frame.py` (create)

**Implementation directive:**

- Add `WeavePresentationFrame` with fields: `result_count`, `results_summary`, `current_thread`, `urgency_label`, `emotional_context`, `presentation_mode`, and `source_task_ids`.
- Add `from_payload_and_pending(payload, pending, ss)` so `_extract_scenario_data(WEAVE, ...)` can be a thin caller.
- Preserve digest handling: when payload contains a digest item, frame must use `digest_count` and `digest_summary`.

**API contract:** `result_count == 0` means no Front LLM call should be made for WEAVE.

### Issue M2.E3.I2 -- Include urgency, emotional gate, and recommended presentation mode

**Files to change:**

- `k1/concierge/actors/front.py`
- `k1/concierge/protocols/weave_policy.py` if mode labels need exposing

**Implementation directive:**

- Populate `urgency_label` using existing critical/urgent logic.
- Populate `emotional_context` from `_build_emotional_context(_get_affect_dict(ss))`.
- Add `presentation_mode` from payload metadata when available. If unavailable, infer from topic/path: `weave`, `digest`, `batch`, or `immediate`.

**State coherence:** Front phrasing must follow the policy decision; Front should not turn a suppressed/deferred result into an immediate result.

### Issue M2.E3.I3 -- Prevent empty WEAVE summaries

**Files to change:**

- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_front_weave_frame.py`

**Implementation directive:**

- Before calling `react_loop(...)` for WEAVE mode, if the `WeavePresentationFrame` has `result_count == 0` or an empty `results_summary`, return `ReactResult(status="skipped", text="")` and publish no final response.
- Keep the existing degenerate-fallback suppression after the loop as a second guard.

**Acceptance:** no user-visible "I wanted to let you know your request is done" message may be emitted without concrete result content.

## M3 -- ReAct Loop Strengthening

**Purpose:** Make ReAct robust under cancellation, HIL, retries, malformed tool calls, repeated tools, and modify-in-flight pressure.

**State/API coherence rule for M3:** `react_loop(...)` owns iteration state. Back owns task execution state. The FSM may send control events, but it must not mutate Back's message list directly.

**Epic M3.E1 -- ReAct Checkpoint**

### Issue M3.E1.I1 -- Introduce versioned `ReActCheckpoint`

**Files to change:**

- `k1/concierge/react/checkpoint.py` (create)
- `k1/concierge/actors/back.py`
- `k1/concierge/protocols/suspension.py`
- `tests/k1/concierge/test_react_checkpoint.py` (create)

**Implementation directive:**

- Create `ReActCheckpoint` with version `1`.
- Required fields: `task_id`, `messages`, `tool_history`, `completed_tool_call_ids`, `suspension_count`, `budget_remaining`, `last_iteration`, and `scratchpad`.
- Add serializer/deserializer methods. Unknown versions must raise a typed error, not silently drop fields.
- Use existing `_serialize_messages(...)` and `_deserialize_messages(...)` behavior for the `messages` field during the first migration.

**API contract:** checkpoint serialization must be JSON-safe and stable across process restart.

### Issue M3.E1.I2 -- Store checkpoint data on suspension

**Files to change:**

- `k1/concierge/actors/back.py`
- `k1/concierge/protocols/suspension.py`
- `k1/concierge/protocols/hitl_persistence.py`

**Implementation directive:**

- In `_emit_back_result(..., status="suspended")`, include `react_checkpoint` alongside existing `react_history`.
- In `SuspensionRequest`, add optional `react_checkpoint` while keeping `react_history` for compatibility.
- In `TaskStateEntry`/HIL persistence, persist the checkpoint under pending HIL data so recovery can restore it.
- Do not remove `react_history` until all live/recovery tests read `react_checkpoint` first.

**Run:** `pytest tests/k1/concierge/test_m09_e92_suspension_recovery.py tests/k1/concierge/test_react_checkpoint.py -v`

### Issue M3.E1.I3 -- Prefer checkpoint on resume

**Files to change:**

- `k1/concierge/actors/back.py`
- `k1/concierge/protocols/hitl_wiring.py`

**Implementation directive:**

- In `back_resume_handler(...)`, read `resume_context["react_checkpoint"]` first.
- Fall back to `resume_context["react_history"]` only for legacy contexts.
- Rebuild prior messages from checkpoint messages.
- Calculate remaining budget from `budget_remaining` instead of only counting prior tool messages when checkpoint is available.

**Acceptance:** resume from a checkpoint preserves prior messages and remaining budget exactly.

### Issue M3.E1.I4 -- Do not re-run successful tools after resume

**Files to change:**

- `k1/concierge/react/loop.py`
- `k1/concierge/tools/dispatcher.py`
- `k1/concierge/actors/back.py`

**Implementation directive:**

- Store `completed_tool_call_ids` and/or `args_hash` in the checkpoint.
- When Back resumes, pass the completed set into the dispatcher or loop context.
- If the model repeats the same completed tool call, return the previous observation or a typed "already completed" observation instead of executing the tool again.

**State coherence:** idempotency belongs to the checkpoint, not the LLM prompt. The prompt may remind the model, but the runtime must enforce no duplicate side effects.

**Epic M3.E2 -- Tool Execution Envelope**

### Issue M3.E2.I1 -- Introduce `ToolExecutionRecord`

**Files to change:**

- `k1/concierge/tools/dispatcher.py`
- `k1/concierge/tools/result_protocol.py` only if result status enum is needed
- `tests/k1/concierge/test_tool_execution_record.py` (create)

**Implementation directive:**

- Add `ToolExecutionRecord` next to `DispatchRecord` or in a new helper module.
- Required fields: `tool_name`, `call_id`, `args_hash`, `start_time_ms`, `end_time_ms`, `duration_ms`, `timeout_ms`, `result_status`, `retryable`, and `iteration`.
- Keep `DispatchRecord` for compatibility if existing tests depend on it.

**API contract:** `args_hash` must be deterministic: JSON-dump arguments with sorted keys, default string conversion, then hash and store a short stable prefix.

### Issue M3.E2.I2 -- Record timing, timeout, status, and retryability

**Files to change:**

- `k1/concierge/tools/dispatcher.py`
- `k1/concierge/react/loop.py`

**Implementation directive:**

- `ToolDispatcher.dispatch(...)` already records start/duration for successful dispatch. Extend it to produce `ToolExecutionRecord` for every accepted execution.
- For errors that happen before implementation dispatch (allowlist, budget, schema, safety), create a record with `result_status="error"`, `retryable=False`, and zero or measured duration.
- For actual implementation exceptions, record `retryable=True` unless policy says otherwise.
- `react_loop._run_tool(...)` owns timeout wrapping. When it catches timeout, create a timeout-style record or call a dispatcher helper to record timeout with the effective timeout used.

**Acceptance:** `get_call_summaries()` can derive duration from real `ToolExecutionRecord.duration_ms` instead of estimating from adjacent timestamps.

### Issue M3.E2.I3 -- Add retry policy

**Files to change:**

- `k1/concierge/react/loop.py`
- `k1/concierge/tools/dispatcher.py`
- `k1/concierge/config.py` if retry count is configurable

**Implementation directive:**

- Define retryable errors: timeout and generic implementation exception are retryable once; allowlist, budget, schema validation, crisis side-effect block, and no-work guard are terminal.
- In `react_loop(...)`, after a retryable tool error, append a typed observation telling the model it may retry once with adjusted args.
- If the same retryable error repeats for the same `tool_name + args_hash`, mark terminal and push the loop toward `submit_result` or typed failure.

**State coherence:** retry must not hide side effects. Only retry if the record indicates no successful side effect was produced.

### Issue M3.E2.I4 -- Preserve existing timeout behavior

**Files to change:**

- `k1/concierge/react/loop.py`
- `tests/k1/concierge/react/test_loop_tool_timeout.py`

**Implementation directive:**

- Keep `asyncio.wait_for(...)` around tool dispatch.
- Do not move timeout handling solely into `ToolDispatcher`; dispatcher does not know HIL-aware timeout policy today.
- If timeout record capture is added, thread the effective timeout from loop to dispatcher through a small helper rather than removing the loop timeout.

**Epic M3.E3 -- Loop Budget And Degenerate Control**

### Issue M3.E3.I1 -- Emit explicit forced-text/last-iteration metrics

**Files to change:**

- `k1/concierge/react/loop.py`
- `k1/concierge/protocols/react_metrics.py` if present or create if metrics live elsewhere

**Implementation directive:**

- When Front is on its last iteration and tools are stripped to force text, record a structured log/metric event with actor, scenario, iteration, max_iterations, and trace id.
- When Back receives the final submit-result nudge, record a structured log/metric event with task scenario and trace id.

**Acceptance:** a focused test can assert the loop records a forced-text marker without parsing anonymous prompt text.

### Issue M3.E3.I2 -- Make Back submit-result terminal contract explicit

**Files to change:**

- `k1/concierge/react/loop.py`
- `k1/concierge/tools/dispatcher.py`
- `k1/concierge/tools/schemas_back.py`

**Implementation directive:**

- Keep the existing dispatcher no-work guard: Back cannot call `submit_result(complete)` before any `invoke_capability` or `batch_invoke_capabilities` call while budget is healthy.
- Add a named terminal error code when the loop exits without `submit_result`: `REACT_MISSING_SUBMIT_RESULT`.
- Ensure `back_handler(...)` maps this status to `task.failed.v1` with typed `error_code` rather than a generic budget failure.

### Issue M3.E3.I3 -- Add bad-loop detector

**Files to change:**

- `k1/concierge/react/loop.py`
- `tests/k1/concierge/react/test_loop_degenerate_control.py` (create)

**Implementation directive:**

- Track repeated `tool_name + args_hash` across iterations.
- Track repeated empty assistant text or repeated invalid schema repair messages.
- On the third identical retry, append a typed recovery event and force the next step toward `submit_result` or typed failure.
- If the loop keeps repeating after recovery, return status `loop_degenerate` and include `error_code="REACT_LOOP_DEGENERATE"`.

**API contract:** `loop_degenerate` must be handled by `_emit_back_result(...)` and mapped to `task.failed.v1` with `error_code="REACT_LOOP_DEGENERATE"`.

### Issue M3.E3.I4 -- Convert recovery nudges into typed loop events

**Files to change:**

- `k1/concierge/react/loop.py`
- `k1/concierge/react/control.py` (create if using shared event types)

**Implementation directive:**

- Define a small internal event shape for `forced_text`, `last_iteration_submit`, `schema_repair`, `degenerate_loop`, and `parameter_update`.
- The loop may still append a user-visible message to the model, but it must also record the typed event in `ReactResult` or the checkpoint so tests can assert behavior without string matching.

**Epic M3.E4 -- Modify-In-Flight Reliability**

### Issue M3.E4.I1 -- Replace direct Back message-list mutation with `BackControlEvent`

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/back.py`
- `k1/concierge/react/loop.py`
- `k1/concierge/react/control.py` (create)
- `tests/k1/concierge/test_m05_arbiter.py`

**Current behavior:** `back_handler(...)` registers its live `messages` list with the FSM. `_handle_arbiter_modify(...)` appends a synthetic message directly into that list.

**Implementation directive:**

- Create `BackControlEvent` with fields `event_type`, `task_id`, `payload`, `created_at_ns`, and `received_at_iteration`.
- Add `register_running_task_control_queue(task_id, queue)` to `ConciergeController` alongside the old `register_running_task_messages(...)` during migration.
- `back_handler(...)` creates an `asyncio.Queue[BackControlEvent]`, registers it, and passes it to `react_loop(...)`.
- `_handle_arbiter_modify(...)` enqueues a `parameter_update` event instead of mutating messages.

**State coherence:** the Back ReAct loop owns its message list. The FSM owns control routing. Communication between them is a queue.

### Issue M3.E4.I2 -- Poll control events between iterations

**Files to change:**

- `k1/concierge/react/loop.py`

**Implementation directive:**

- Add optional `control_queue` parameter to `react_loop(...)`.
- At the top of each iteration, after cancellation check and before building the LLM request, drain all queued control events.
- Convert `parameter_update` into a typed `ModelMessage` with a stable prefix and JSON payload.
- Convert `cancel` into the same path as cancellation check.

**Acceptance:** a test can enqueue a parameter update after iteration 1 and prove the next LLM request includes it.

### Issue M3.E4.I3 -- Reserve one bounded extra iteration for late modifications

**Files to change:**

- `k1/concierge/react/loop.py`
- `k1/concierge/config.py` if hard limit needs a setting

**Implementation directive:**

- If a `parameter_update` arrives when `iteration == max_iterations - 1`, allow exactly one extra iteration for that event.
- Hard cap: original max plus one. Do not permit unbounded extension.
- If hard cap is already consumed, return or emit a typed `cannot_apply_parameter_update` event so Front can tell the user honestly.

### Issue M3.E4.I4 -- Never acknowledge an update Back cannot consume

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_m05_arbiter.py`

**Implementation directive:**

- `_handle_arbiter_modify(...)` must enqueue the control event and receive/record an accepted/rejected status.
- Front may tell the user the change was accepted only after the queue accepts it.
- If the Back loop is already complete, cancelled, suspended, or at hard cap, Front should acknowledge that the change cannot be applied and offer a new task path.

## M4 -- Weave And Conversation Attention

**Purpose:** Make async task results arrive with conversational timing. The user should feel that the assistant knows when to speak, when to wait, and when not to interrupt.

**State/API coherence rule for M4:** A task result may exist in exactly one place at a time: `FSMTurnState.pending_results`, `FSMTurnState.deferred_results`, or `WeaveBatcher` queue. Suppression and delivery must remove the result from all other queues.

**Epic M4.E1 -- Pure Weave Policy**

### Issue M4.E1.I1 -- Split adaptive task-complete handling into named decision/apply steps

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `tests/k1/concierge/test_m04_weave_controller_steps.py` (create)

**Current behavior:** `_on_task_complete_adaptive(...)` already calls pure `WeavePolicy.decide(signal)`, but it also collects signal, emits observability, calls OPP hooks, and applies side effects in one long method.

**Implementation directive:**

- Extract `_collect_weave_signal(task_id) -> WeaveSignal`.
- Extract `_decide_weave(signal) -> WeaveDecisionResult` or call `self._weave_policy.decide(signal)` from a tiny wrapper that handles fallback.
- Extract `_apply_weave_decision(decision, task_id, envelope) -> None`.
- Keep behavior identical in this issue. The goal is readability and testability, not policy change.

**Acceptance:** a unit test can instantiate a controller-like object, call `_collect_weave_signal(...)`, and assert signal fields without publishing to the bus.

### Issue M4.E1.I2 -- Clarify canonical decision type

**Files to change:**

- `k1/concierge/protocols/weave_policy.py`
- `k1/concierge/protocols/weave_state.py`

**Implementation directive:**

- Treat `WeaveDecision` in `weave_policy.py` as the canonical M4+ type: `IMMEDIATE`, `BATCH`, `DEFER`, `DIGEST`, `SUPPRESS`.
- Do not rename or collapse legacy `WeaveAction` in `weave_state.py`; add a comment that it is the pre-M8 state-table primitive used by legacy fallback.
- Verify the fallback map covers all legacy `WeaveAction` values.

**Acceptance:** no implementer confuses `WeaveAction.QUEUE` with canonical `WeaveDecision.DEFER`.

### Issue M4.E1.I3 -- Document HIL/typing/affect/urgency/pool ordering in policy

**Files to change:**

- `k1/concierge/protocols/weave_policy.py`
- `tests/k1/concierge/test_m08_e82_weave_decision.py`

**Implementation directive:**

- Add a comment above `WeavePolicy.decide(...)` explaining rule priority: critical urgency, user typing, crisis/affect gate, grief/distress gate, HIL pending, digest, idle batch, pool pressure, default batch.
- Add or confirm tests for: typing defers, HIL pending defers non-critical, crisis suppresses normal urgency, critical urgency only breaks through when emotional gate is open.

**Run:** `pytest tests/k1/concierge/test_m08_e82_weave_decision.py tests/k1/concierge/test_m08_e81_weave_signal.py -v`

### Issue M4.E1.I4 -- Keep policy pure and side effects outside policy

**Files to inspect/change:**

- `k1/concierge/protocols/weave_policy.py`
- `k1/concierge/fsm/controller.py`

**Implementation directive:**

- `WeavePolicy.decide(...)` must not publish, mutate controller state, drain queues, or call Front.
- Side effects belong only in `_apply_weave_decision(...)`, `_emit_weave_decided(...)`, `_schedule_weave_flush_adaptive(...)`, `_mark_results_deferred(...)`, `_schedule_digest_flush(...)`, and `_suppress_result(...)`.
- Add a focused test that monkeypatches bus/publisher objects and proves `WeavePolicy.decide(...)` never touches them.

**Epic M4.E2 -- Natural Delivery Strategy**

### Issue M4.E2.I1 -- Same-turn completion should try to chain before deferring

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/fsm/front_lock.py`
- `k1/concierge/bus/topics.py` only if an internal context topic is needed
- `tests/k1/concierge/test_m04_weave_fsm_paths.py` (create)

**Current behavior:** same-turn completion while Front is still working is stored as a deferred proactive result, then delivered later by timer or next user input.

**Implementation directive:**

- Add `_try_chain_into_current_response(task_id, payload, envelope) -> bool` to the controller.
- In the same-turn branch of `_on_task_complete(...)`, call it before appending to `deferred_results`.
- Add `FrontLock.is_accepting_context() -> bool`. It may return `False` initially if mid-generation context injection is not supported. That is acceptable; the method makes the limitation explicit.
- If chaining returns `False`, keep the existing deferred proactive path.

**State coherence:** never place the same result in both chained context and deferred queue.

### Issue M4.E2.I2 -- Prove typing/HIL deferral at FSM path level

**Files to change:**

- `tests/k1/concierge/test_m04_weave_fsm_paths.py`

**Implementation directive:**

- Add a controller-level test where user typing is active, a task completes, policy returns `DEFER`, and the controller moves the result into `deferred_results` without Front delivery.
- Add a second test where pending HIL exists and non-critical task completion is deferred.
- These tests complement policy-only tests; they prove the controller applies the decision correctly.

**Run:** `pytest tests/k1/concierge/test_m04_weave_fsm_paths.py -v`

### Issue M4.E2.I3 -- Apply OPP weave-flush hook on batch path

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `tests/k1/concierge/test_m04_weave_fsm_paths.py`

**Implementation directive:**

- Inspect `_flush_weave_now(...)`. If it builds a weave envelope from drained results without calling `self._opp_pipeline.on_weave_flush(...)`, add that hook before envelope construction.
- Ensure `_deliver_weave_immediate(...)` and `_flush_weave_now(...)` use the same OPP pacing/enrichment semantics.

**Acceptance:** test with fake `opp_pipeline` proves `_flush_weave_now(...)` calls `on_weave_flush(...)` exactly once per batch flush.

### Issue M4.E2.I4 -- Suppress stale/cancelled results from all queues

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/fsm/turn_state.py`
- `tests/k1/concierge/test_m04_weave_fsm_paths.py`

**Current behavior:** `_suppress_result(...)` removes from `pending_results`; deferred queue cleanup is not guaranteed.

**Implementation directive:**

- Extend `_suppress_result(task_id, reason)` so it removes the task from both `pending_results` and `deferred_results`.
- Add a helper on `FSMTurnState`, for example `remove_result(task_id) -> int`, so queue cleanup is not open-coded in the controller.
- Add a max depth for `deferred_results`, suggested `16`, matching the pending queue default. On overflow, either evict oldest with dead-letter or force-deliver oldest; choose one behavior and document it in the helper.

**State coherence:** after cancellation or suppression, a task id must not remain in any pending/deferred/weave queue.

**Epic M4.E3 -- Proactive Fill**

### Issue M4.E3.I1 -- Implement minimal proactive fill source

**Files to inspect/change:**

- Search existing experience/proactive modules under `k1/concierge/**` before creating a new file.
- If no live module exists, create `k1/concierge/protocols/proactive_agent.py` or use the existing ExperienceLayer location if found.
- `k1/concierge/fsm/controller.py`
- `tests/k1/concierge/test_m04_proactive_fill.py` (create)

**Implementation directive:**

- Provide `generate_fill(...)` or equivalent that returns a short Front-voice fill candidate only when Back has been working longer than the configured threshold and no HIL/crisis block is active.
- Do not call Back or Fabric from proactive fill.
- Deliver fill through existing `TOPIC_PROACTIVE_FILL` handling in the FSM/Front path.

**Acceptance:** when a long-running task is active and all gates pass, one fill is emitted; when HIL or crisis is active, zero fills are emitted.

### Issue M4.E3.I2 -- Use Front voice only

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/actors/front.py`

**Implementation directive:**

- Proactive fill payloads must be delivered to Front, not published as raw final text by the controller.
- Front must produce the final wording using existing prompt/mode machinery.
- Back worker status may be included as facts, but never as user-visible prose.

### Issue M4.E3.I3 -- Never interrupt HIL or crisis flow

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/protocols/weave_policy.py` if shared gates are reused

**Implementation directive:**

- Before scheduling or emitting proactive fill, check `_has_pending_hitl()` and current safety/affect gate.
- If `CLARIFYING_WORKER`, crisis/RED safety, or `hitl_pending=True`, suppress proactive fill.

### Issue M4.E3.I4 -- Add rate limit and dedup

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/fsm/turn_state.py` or controller fields

**Implementation directive:**

- Track last proactive fill timestamp and task id.
- Do not emit more than one fill per task per configured window.
- Dedup by `task_id + fill_kind`.

**Run for M4:** `pytest tests/k1/concierge/test_m08_e82_weave_decision.py tests/k1/concierge/test_m08_e83_dynamic_batch.py tests/k1/concierge/test_m08_e84_policy_integration.py tests/k1/concierge/test_m08_e81_weave_signal.py tests/k1/concierge/test_m04_weave_fsm_paths.py tests/k1/concierge/test_m04_proactive_fill.py -v`

## M5 -- State Ownership And Replay

**Purpose:** Remove dual source-of-truth risks. Recovery and the live runtime must reconstruct the same conversation state from the same committed events. In-memory dicts are caches. The ledger and Session State persistence records are the rebuild sources.

**State/API coherence rule for M5:** A runtime cache may exist only if it can be rebuilt from a projection. `ConciergeController._history`, `FSMTurnState.pending_results`, `TaskBridge`, `SuspensionManager._active`, and `ConciergeController._pending_hil_subtasks` must either be rebuilt in recovery or explicitly documented as live-only and reconstructable from Session State. If two structures can describe the same pending HIL, one structure owns writes and the other is a read-through/cache.

**Verified code facts before implementation:**

- `FSMTurnState.rebuild_from_projection(projected: deque[dict]) -> int` already exists in `k1/concierge/fsm/turn_state.py`. Do not re-add it.
- `SuspensionManager.rebuild_from_events(entries) -> int` already exists in `k1/hil/suspension.py` and uses `project_suspension_state(...)`. Do not duplicate it.
- `CrashRecoveryOrchestrator._do_recover(...)` already calls `project_task_states(...)`, `rebuild_from_events(...)`, and `FSMTurnState.rebuild_from_projection(...)`.
- `CrashRecoveryOrchestrator._do_recover(...)` projects history but only stores it in `report._details["history"]`; it does not apply it to `ConciergeController._history` or `history_active`.
- `_build_canonical_event(...)` maps `entry_type="hil_request"` and `entry_type="hil_response"`, but the controller writes `entry_type="hitl_request"` and `entry_type="hitl_response"` in the live HITL paths. That mismatch means some live HIL history writes do not produce canonical `hil.requested` / `hil.resolved` ledger rows.
- `_on_hil_request(...)` emits `hitl.lifecycle.requested` on the bus, persists `pending_hil_data` into task state, and writes history, but it does not commit a unified `hil.requested` row with `hil_request_id`, `kind`, and `caller_key` into the concierge ledger.

**Epic M5.E1 -- Ledger-First Projection**

### Issue M5.E1.I1 -- Normalize HIL ledger writes before recovery relies on them

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/events/hitl.py`
- `k1/concierge/ledger/projections.py`
- `tests/k1/concierge/ledger/test_ledger_hitl_projection.py` (create)

**Current behavior:** HIL state is visible on the bus and in `task_state.pending_hil_data`, but the concierge ledger does not receive a consistent `hil.requested` row for every unified HIL request. Legacy history writes use `entry_type="hitl_request"`, while `_build_canonical_event(...)` only recognizes `"hil_request"`.

**Implementation directive:**

- In `_build_canonical_event(...)`, accept both spellings: `"hil_request"` and `"hitl_request"` must construct `HILRequested`; `"hil_response"` and `"hitl_response"` must construct `HILResolved`.
- Extend `HILRequested` in `k1/concierge/events/hitl.py` with optional fields needed by the unified lane: `hil_request_id: str = ""`, `kind: str = ""`, `caller_key: str = ""`, `created_at_ms: int = 0`, and `timeout_ms: int = 0`. Keep existing fields (`hil_type`, `question`, `options`, `context`, `side_effects`, `safety_band`, `timeout_s`, `max_rounds`) for legacy compatibility.
- Extend `HILResolved` with optional `hil_request_id: str = ""` and `kind: str = ""` so projections can join request/response by `hil_request_id` when task id is synthetic.
- In `_on_hil_request(...)`, after parsing `env_payload` and before delivery to Front, append a canonical `HILRequested` to `self._ledger` when a ledger is attached. Use `append_sync(...)` because `_on_hil_request` is synchronous.
- The payload written from `_on_hil_request(...)` must include: `task_id`, `hil_request_id`, `kind`, `caller_key`, `hil_type`, `question`, `options`, `side_effects`, `context`, `safety_band`, `created_at_ms`, and `timeout_ms`.
- Source the fields from `env_payload`, `inner = env_payload.get("payload") or {}`, and `unwrap_hil_request_payload(...)` so `project_hitl_state(...)` does not need per-kind bus-envelope parsing.
- Update `project_hitl_state(...)` to prefer `payload["hil_request_id"]` as the HIL identity and `payload["kind"] or payload["hil_type"]` as the kind. If `hil_request_id` is absent, fall back to `payload["pending_hil_id"]`, then `payload["event_id"]`.
- Add a unit test that writes both a unified `HILRequested(hil_request_id="h1", task_id="hil:h1", kind="clarification")` and a legacy `HILRequested(task_id="t1", hil_type="clarification")`; assert both appear in the projection with the same normalized field names.

**API contract:** All ledger rows with `event_type="hil.requested"` must be consumable by one projection path. Future code must not branch on bus topic origin (`TOPIC_HIL_REQUEST` vs `TOPIC_TASK_SUSPENDED`) to recover pending HIL state.

**State coherence:** `task_id` is the parent task slot. `hil_request_id` is the HIL protocol identity. `pending_hil_id` is the legacy `HILSubTask` identity. Recovery must retain all three when present and never overwrite one with another.

**Run:** `pytest tests/k1/concierge/ledger/test_ledger_hitl_projection.py -v`

### Issue M5.E1.I2 -- Apply projected history back onto the controller

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/ledger/recovery.py`
- `tests/k1/concierge/ledger/test_ledger_full_recovery_probe.py` (create)

**Current behavior:** `project_history(entries)` returns history dicts, and recovery records the list in `report._details["history"]`; the controller cache remains empty.

**Implementation directive:**

- Add `ConciergeController.rebuild_history_from_projection(self, history: list[dict[str, Any]]) -> int`.
- The method must clear `self._history`, convert each projection dict to `TypedHistoryEntry`, append it to `self._history`, and return the count.
- Projection dict fields are named `turn`, `type`, `role`, `text`, `timestamp_ms`, `source`, optional `task_id`, optional `metadata`. Convert them to `TypedHistoryEntry(turn_number=..., entry_type=..., role=..., text=..., timestamp_ms=..., source=..., task_id=..., metadata=...)`.
- Do not call `_write_history(...)` from this rebuild method. `_write_history(...)` emits ledger events, and recovery must not write new ledger rows.
- In `CrashRecoveryOrchestrator._do_recover(...)`, after `history = project_history(entries)`, call the new method when present:
  `report.history_entries = fsm.rebuild_history_from_projection(history)`.
- Keep `report._details["history"] = history` for debugging.
- If a `history_active` Session State sink exists and exposes `clear()` plus `add_turn(...)`, add a separate helper `rebuild_history_sink_from_projection(...)`; call it only after `self._history` is rebuilt. If the sink API is not stable, leave SS write-back out and record a `report._details["history_sink_rebuilt"] = False` flag.

**API contract:** Recovery history rebuild is replace-only and side-effect-free. Calling it twice with the same projection must leave the same `self._history` length and content.

**State coherence:** After recovery, `len(fsm.history)` must equal `len(project_history(entries))`, and each entry's `turn_number`, `entry_type`, `role`, `text`, and `task_id` must match the projected dict.

**Run:** `pytest tests/k1/concierge/ledger/test_ledger_full_recovery_probe.py -v -k "history"`

### Issue M5.E1.I3 -- Recover pending HIL into the correct live caches without duplicate APIs

**Files to change:**

- `k1/concierge/ledger/recovery.py`
- `k1/concierge/ledger/projections.py`
- `k1/concierge/protocols/hitl_persistence.py`
- `k1/hil/suspension.py`
- `tests/k1/concierge/ledger/test_ledger_hitl_projection.py`

**Current behavior:** Recovery step 4 is a stub comment. `SuspensionManager.rebuild_from_events(entries)` already restores legacy suspensions from `task.suspended` rows, but unified HIL rows are not projected into a typed model and not represented in `_pending_hil_subtasks`.

**Implementation directive:**

- Do not add another `SuspensionManager.rebuild_from_projection(...)`. Use the existing `rebuild_from_events(...)` for legacy `task.suspended` recovery.
- Add a frozen/slotted dataclass `HILStateRecord` in `k1/concierge/protocols/hitl_persistence.py` with fields: `task_id`, `hil_request_id`, `pending_hil_id`, `kind`, `hil_type`, `question`, `options`, `side_effects`, `safety_band`, `caller_key`, `created_at_ms`, `timeout_ms`, `status`, and `react_snapshot`.
- Add `HILStateRecord.from_projection_payload(task_id: str, payload: dict[str, Any]) -> HILStateRecord`.
- Update `project_hitl_state(entries)` so its first return value is `dict[str, HILStateRecord]`, keyed by `task_id`. Keep the second and third return values (`counts`, `histories`) for compatibility until all callers migrate.
- In `CrashRecoveryOrchestrator._do_recover(...)`, call `pending_hil, hil_counts, hil_histories = project_hitl_state(entries)` after suspension recovery.
- Add `report.hitl_pending_restored = len(pending_hil)` and store `report._details["pending_hil"] = {task_id: record for ...}`. If report serialization requires plain dicts, use `record.__dict__` or `dataclasses.asdict(record)`.
- If the controller has a method from M5.E2.I2 named `rebuild_pending_hil_from_projection(...)`, call it here. Otherwise, do not mutate private `_pending_hil_subtasks` from the recovery orchestrator; record the projection in report details and let M5.E2 own the cache rebuild.
- Add a test that verifies resolved rows are absent: `hil.requested` followed by `hil.resolved` for the same `hil_request_id` must produce no pending record.

**API contract:** The projector is pure. It must not import `ConciergeController`, `SuspensionManager`, the bus, or Session State.

**State coherence:** A task with terminal `task.completed`, `task.failed`, or `task.cancelled` after `hil.requested` must not remain in `pending_hil`, even if no `hil.resolved` row was observed.

**Run:** `pytest tests/k1/concierge/ledger/test_ledger_hitl_projection.py -v`

### Issue M5.E1.I4 -- Add recovery coherence checks after rebuild

**Files to change:**

- `k1/concierge/ledger/recovery.py`
- `tests/k1/concierge/ledger/test_ledger_full_recovery_probe.py`

**Implementation directive:**

- Add private helper `_check_recovery_coherence(fsm, task_states, pending_results, pending_hil) -> list[str]` in `recovery.py`.
- Run it at the end of `_do_recover(...)` and store the returned list in `report._details["coherence_anomalies"]`.
- Log each anomaly at `WARNING`; never raise from the coherence checker.
- Checks required:
  - Every non-terminal `TaskStateEntry` in `task_states` must be represented in `report._details["active_task_ids"]`.
  - Every `TaskStatus.SUSPENDED` task must have either a `SuspensionManager` context, a `TaskBridge` pending HIL record, or a `pending_hil` projection record.
  - `FSMTurnState.pending_results` must not contain a task id whose projected task status is `COMPLETED`, `FAILED`, or `CANCELLED` and whose result has already been delivered by `conversation.response.delivered.v1` or `conversation.weave.emitted`.
  - `report.active_task_count` must equal the count of projected `DISPATCHED`, `IN_PROGRESS`, and `SUSPENDED` tasks.
- Add one healthy-stream test and one corrupted-stream test. The corrupted test should assert anomalies are reported but recovery still returns `recovered=True`.

**State coherence:** The checker is observability only. It does not repair state and it does not decide FSM state. `_derive_fsm_state(...)` remains the state derivation authority.

**Run:** `pytest tests/k1/concierge/ledger/test_ledger_full_recovery_probe.py -v`

**Epic M5.E2 -- HIL State Single Owner**

**Ownership model:**

- Unified live lane: `HumanInTheLoopService._pending` owns the waiting `Future` keyed by `hil_request_id`; `task_state.pending_hil_data` owns Front-presentable envelope data; controller cache is optional and must mirror Session State.
- Legacy task suspension lane: `ConciergeController._pending_hil_subtasks` owns `HILSubTask` keyed by `task_id`; `SuspensionManager` owns timeout/context lifecycle for that legacy task; `TaskBridge` persists `pending_hil_data`.
- Recovery lane: ledger projectors restore projections; Session State `task_state.pending_hil_data` restores live presentation data; private dicts are caches.

### Issue M5.E2.I1 -- Define `HILStateRecord` as the projection join model

**Files to change:**

- `k1/concierge/protocols/hitl_persistence.py`
- `k1/concierge/ledger/projections.py`
- `tests/k1/concierge/test_m5e2_hil_state_owner.py` (create)

**Implementation directive:**

- Implement `HILStateRecord` as specified in M5.E1.I3.
- Normalize names:
  - `kind` is the unified `HILKind` string from `HILEnvelope.kind`.
  - `hil_type` is legacy-compatible and should equal `kind` when no separate legacy value exists.
  - `hil_request_id` is the request/response correlation key.
  - `pending_hil_id` is the legacy `HILSubTask.pending_hil_id` when available, otherwise `hil_request_id`.
- Add `to_pending_hil_data(self) -> dict[str, Any]` to support writing the record back to `TaskBridge.set_pending_hil_data(...)` without leaking dataclass instances into Session State.
- Add tests for unified and legacy rows, including missing optional fields.

**API contract:** Code outside `hitl_persistence.py` must not construct pending-HIL projection dicts by hand after this issue. Use `HILStateRecord.from_projection_payload(...)`.

**Run:** `pytest tests/k1/concierge/test_m5e2_hil_state_owner.py -v -k "record"`

### Issue M5.E2.I2 -- Fix pending-HIL cache rebuild and pending-HIL detection

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/concierge/protocols/hitl_persistence.py`
- `tests/k1/concierge/test_m5e2_hil_state_owner.py`

**Current behavior:** `_has_pending_hitl()` returns `bool(self._pending_hil_subtasks)`. Unified HIL requests handled by `_on_hil_request(...)` persist data into task state but do not populate `_pending_hil_subtasks`, so weave policy can miss active unified HIL.

**Implementation directive:**

- Add `ConciergeController.rebuild_pending_hil_from_projection(self, records: dict[str, HILStateRecord]) -> int`.
- For legacy records with `pending_hil_id` and `react_snapshot`, rebuild `HILSubTask` values in `_pending_hil_subtasks` keyed by `task_id`.
- For unified records, do not create fake `HILSubTask` objects unless all fields required by `HILSubTask.from_persistence(...)` exist. Instead, call `self._task_bridge.set_pending_hil_data(task_id, record.to_pending_hil_data())` and return the count.
- Update `_has_pending_hitl()` to return true if any of the following are true: `_pending_hil_subtasks` non-empty, `TaskBridge.get_suspended_tasks()` contains a task with `pending_hil_data`, or `task_state.get_all()` contains a SUSPENDED task whose pending HIL payload has `hil_request_id`.
- Keep `HumanInTheLoopService._pending` private. The controller must not inspect the service future dict.

**State coherence:** Unified live HIL is considered pending if `task_state.pending_hil_data.hil_request_id` exists and no matching `hil.resolved` or `k1.hil.response.v1` has been processed. Legacy live HIL is considered pending if `_pending_hil_subtasks[task_id]` exists or the task bridge says the task is suspended with pending data.

**Run:** `pytest tests/k1/concierge/test_m5e2_hil_state_owner.py -v -k "pending"`

### Issue M5.E2.I3 -- Detect HIL divergence at request, resolve, timeout, and cleanup boundaries

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `k1/hil/service.py`
- `tests/k1/concierge/test_m5e2_hil_state_owner.py`
- `tests/k1/hil/test_service.py`

**Implementation directive:**

- Add `ConciergeController._check_hil_state_coherence(self, *, task_id: str = "", hil_request_id: str = "", context: str = "") -> list[str]`.
- Required checks:
  - If `_pending_hil_subtasks[task_id]` exists, `TaskBridge` must mark the task suspended or in progress with pending HIL data.
  - If `TaskBridge` has pending HIL data for a task, `_has_pending_hitl()` must return true.
  - If a task is terminal, it must not remain in `_pending_hil_subtasks`, `SuspensionManager._contexts`, or `SuspensionManager._active`.
  - If the pending data contains a `hil_request_id`, it must match the request id in the incoming or outgoing HIL envelope at that boundary.
- Call the helper at the end of `_on_hil_request(...)`, after `_on_task_resume(...)`, after `_hitl_timeout_watcher(...)` cleanup, and from `SuspensionManager.cleanup_task(...)` callers when task terminalization happens.
- Log `ERROR` with a structured message for every anomaly. Do not raise.
- In `HumanInTheLoopService._on_response(...)`, keep the existing `hil_response_unknown_id` warning for unmatched responses and add a counter/log field that includes `kind` and `hil_request_id`. Do not expose `_pending` to the controller.

**API contract:** Coherence checks must be safe in tests where `_ss`, `_ledger`, or `_hil_port` is `None`.

**Run:** `pytest tests/k1/concierge/test_m5e2_hil_state_owner.py tests/k1/hil/test_service.py -v -k "hil_response_unknown_id or coherence or pending"`

**Epic M5.E3 -- Write Elision Gate**

**Current code fact:** The broad old `_write_phase1_to_ss` path no longer exists. The current controller writes only temporal anchor and crisis safety escalation in `_write_session_context_to_ss(...)`; richer intent/affect/belief writes are owned by Front tools and delta writers. The gate must therefore be explicit about what it controls.

### Issue M5.E3.I1 -- Create `WriteElisionGate` as a pure decision module

**Files to change:**

- `k1/concierge/acking/__init__.py` (create)
- `k1/concierge/acking/write_elision.py` (create)
- `tests/k1/concierge/acking/test_write_elision_gate.py` (create)

**Implementation directive:**

- Create `WriteElisionDecision` dataclass with fields: `write_safety_band`, `write_temporal`, `write_control`, `write_intents`, `write_beliefs`, `write_affect`, `elided_sections`, and `reason`.
- Create `WriteElisionGate.evaluate(phase1_output: dict[str, Any]) -> WriteElisionDecision`.
- The gate is stateless. If safety comparison is needed, the caller passes `prior_safety_band` in `phase1_output`.
- Required rules:
  - `write_safety_band=True` always.
  - `write_temporal=True` for the current `_write_session_context_to_ss(...)` temporal anchor write.
  - `write_control=True` when `safety_band != prior_safety_band`, when `intent_class` is not `backchannel` or `filler`, or when `control_signals` is non-empty.
  - `write_intents=True` only when `intent_class` is not `backchannel` or `filler` and `intents` is non-empty.
  - `write_beliefs=True` only when `beliefs` is a non-empty list or dict.
  - `write_affect=True` when `affect_detected=True`, or when `affect_label` is not empty and not `neutral`.
- Add tests for neutral backchannel, task request with beliefs, affect-only backchannel, and safety escalation.

**API contract:** The gate returns a decision only. It must not import Session State, mutate sections, publish events, or read controller state.

**Run:** `pytest tests/k1/concierge/acking/test_write_elision_gate.py -v`

### Issue M5.E3.I2 -- Wire the gate into `ConciergeController` without suppressing safety or time

**Files to change:**

- `k1/concierge/fsm/controller.py`
- `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`

**Implementation directive:**

- In `ConciergeController.__init__(...)`, instantiate `self._write_elision_gate = WriteElisionGate()`.
- In `_write_session_context_to_ss(...)`, build a small `phase1_output` dict with at least `intent_class`, `safety_band`, `prior_safety_band`, `beliefs`, `affect_label`, `affect_detected`, and `temporal_anchor`.
- Always perform the temporal anchor write and the safety-band write if crisis detection requires it.
- Use `decision.write_control` only for optional non-safety control metadata. Do not suppress `control.set_temporal_anchor(...)` and do not suppress `control.escalate_safety(...)`.
- Emit one `DEBUG` log when sections are elided.
- Do not use this gate to suppress Front cognitive tool writes or HIL/task/weave writes.

**State coherence:** The current minimum user-turn state write remains: temporal anchor is updated every turn, and crisis safety escalation always writes. The gate only prevents low-signal optional sections from being added later or reintroduced by phase-1 expansions.

**Run:** `pytest tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x9_backchannel_write_elision_gate_is_wired -v`

### Issue M5.E3.I3 -- Add mutation-level regression for neutral backchannel

**Files to change:**

- `tests/k1/concierge/acking/test_write_elision_gate.py`
- `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`

**Implementation directive:**

- Extend the unit test to assert neutral backchannel yields `elided_sections` containing `intents`, `beliefs`, and `affect` while `write_safety_band` and `write_temporal` remain true.
- Extend the live M1-X9 test after its existing module/controller assertions. Send `"ok"`, inspect the relevant Session State sections before and after, and assert no new `beliefs_active` fact and no non-neutral affect write were added by the controller path.
- If the live section APIs make mutation-count inspection hard, use a spy writer/mutation guard in the test fixture rather than peeking at private fields.

**Run:** `pytest tests/k1/concierge/acking/test_write_elision_gate.py tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x9_backchannel_write_elision_gate_is_wired -v`

### Issue M5.E3.I4 -- Close M1-X9 only after the gate is live

**Files to change:**

- `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`
- `docs/architecture/kernel_sweep_status.md`
- `k1/concierge/OPEN_ISSUES.md`

**Implementation directive:**

- Remove the strict xfail marker from `test_m1_x9_backchannel_write_elision_gate_is_wired` only after M5.E3.I1-I3 pass.
- Update the tracker row to say the production module is `k1.concierge.acking.write_elision.WriteElisionGate` and the controller attribute is `_write_elision_gate`.
- Update `OPEN_ISSUES.md` so the old design-only wording is either removed or marked closed by M5.E3.I4.

**Run:** `pytest tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x9_backchannel_write_elision_gate_is_wired -v`

**Run for M5:** `pytest tests/k1/concierge/ledger/test_ledger_hitl_projection.py tests/k1/concierge/ledger/test_ledger_full_recovery_probe.py tests/k1/concierge/test_m5e2_hil_state_owner.py tests/k1/concierge/acking/test_write_elision_gate.py tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x9_backchannel_write_elision_gate_is_wired -v`

**Acceptance:** A crash-recovered controller and a never-crashed controller expose the same projected history, pending result queue, task status, and pending-HIL state for the same ledger stream. Neutral backchannels do not pollute belief/affect state, while temporal and safety state remain intact.

## M6 -- Memory, Identity, And Continuity

**Purpose:** Strengthen the "same mind over time" feeling without letting Back become conversational. Front gets compressed context, narrative continuity, and dynamic identity overlays. Back remains a neutral executor.

**Verified code facts before implementation:**

- `EpisodicCompressor`, `CompressionConfig`, and `CompressedEpisode` exist in `k1/concierge/compression/episodic_compressor.py` and have targeted tests in `tests/k1/concierge/test_episodic_compressor.py`.
- `OppPipeline` has `set_episodic_compressor(...)`, `set_dynamic_identity(...)`, and `on_pre_prompt_build(...)`, but `ConciergeFactory` does not instantiate or attach an `OppPipeline` to the controller.
- `front_handler(...)` accepts `opp_pipeline`, but `ConciergeRuntime._run_consumer(...)` does not pass it when calling `front_handler(...)`.
- `front_handler(...)` currently builds `turns_for_opp` as `[{"role": e.get("role", ""), "text": e.get("text", "")}]`, which does not match `EpisodicCompressor`'s expected turn shape and can fail when history entries are objects.
- `DynamicPromptBuilder` receives `compressed_context` and `identity_block` only as generic `scenario_data`; templates do not place either block where it belongs in the prompt.
- `NarrativeWeaver.weave(...)` is implemented, but `ConciergeRuntime._build_experience_context()` gives history dicts with `entry_type` and `text`, not `intent`, `thread`, or `topic`, so real sessions often produce empty narrative signals.
- `ConciergeRuntime._tick_experience()` handles `emotional`, `tone`, `timing`, and `fill`, but does not write `outputs["narrative"]` into the `narrative_active` Session State section.
- `DynamicIdentityContext` exists and is tested in `tests/k1/concierge/test_dynamic_identity.py`, but it is not attached to live prompt assembly.

**Epic M6.E1 -- Episodic Compression**

### Issue M6.E1.I1 -- Instantiate one compressor and one OPP pipeline per session

**Files to change:**

- `k1/concierge/factory.py`
- `k1/concierge/experience/layer.py`
- `k1/concierge/protocols/opp_pipeline.py`
- `tests/k1/concierge/test_concierge_factory.py`
- `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py`

**Implementation directive:**

- In `ConciergeFactory`'s 16-step wiring sequence, after `ExperienceLayer` is created and before `ConciergeRuntime` is returned, instantiate:
  - `OppPipeline(OppPipelineConfig())`
  - `EpisodicCompressor(CompressionConfig())`
  - `DynamicIdentityContext(DynamicIdentityConfig())`
- Call `opp_pipeline.set_episodic_compressor(compressor)` and `opp_pipeline.set_dynamic_identity(identity_context)`.
- Call `fsm.set_opp_pipeline(opp_pipeline)`.
- Expose the same compressor on the experience layer as `experience.episodic_compressor` so the existing M1-L7 live probe can observe compression state.
- Prefer adding optional constructor parameters to `ExperienceLayer.__init__(episodic_compressor: Any | None = None)` instead of assigning arbitrary attributes after construction. If constructor change is too broad, assign the attribute in the factory and add a comment in the plan implementation PR.
- Add a factory test that creates a runtime with `enable_experience=True` and asserts `runtime.fsm._opp_pipeline.status()["opp6_episodic_compression"] is True`, `status()["opp7_dynamic_identity"] is True`, and `runtime.experience_layer.episodic_compressor is not None`.

**State coherence:** The compressor instance attached to `OppPipeline` and the one exposed as `ExperienceLayer.episodic_compressor` must be the same object. Do not create one compressor for live prompt assembly and a second one for tests/experience telemetry.

**Run:** `pytest tests/k1/concierge/test_concierge_factory.py tests/k1/concierge/test_episodic_compressor.py -v`

### Issue M6.E1.I2 -- Pass OPP pipeline into live Front calls

**Files to change:**

- `k1/concierge/session.py`
- `tests/k1/concierge/test_concierge_factory.py`
- `tests/k1/concierge/test_m6_e1_episodic_compression.py` (create)

**Current behavior:** `front_handler(...)` has an `opp_pipeline` parameter, but `ConciergeRuntime._run_consumer(...)` omits it.

**Implementation directive:**

- In `ConciergeRuntime._run_consumer(...)`, update the `front_handler(...)` call to pass `opp_pipeline=getattr(self._fsm, "_opp_pipeline", None)`.
- Do not pass OPP pipeline to `route_back_envelope(...)` or `back_handler(...)`.
- Add a focused test with a fake Front envelope and a fake OPP pipeline whose `on_pre_prompt_build(...)` increments a counter. Assert the counter increments exactly once for a Front invocation and zero times for Back invocation.

**API contract:** OPP-6 and OPP-7 are Front-only prompt enrichment. Back must not receive `identity_block` or conversational compression artifacts.

**Run:** `pytest tests/k1/concierge/test_m6_e1_episodic_compression.py -v -k "opp_pipeline_front_only"`

### Issue M6.E1.I3 -- Fix Front history-to-compressor turn shape

**Files to change:**

- `k1/concierge/actors/front.py`
- `tests/k1/concierge/test_m6_e1_episodic_compression.py`

**Implementation directive:**

- Replace the current `turns_for_opp` list comprehension in `front_handler(...)` with a helper `_history_entries_to_opp_turns(history_active) -> list[dict[str, Any]]`.
- The helper must support both dict entries and object entries.
- For each entry, produce the shape expected by `EpisodicCompressor`: `turn_number`, `user_message`, `response`, `intent`, `entities`, `has_hitl`, and `safety_band`.
- Mapping rules:
  - user entries: `user_message = text`, `response = ""`.
  - assistant/final/weave/task_complete entries: `response = text`, `user_message = ""`.
  - HIL entries (`hitl_request`, `hitl_response`, `hil_request`, `hil_response`) set `has_hitl=True`.
  - Safety band comes from `metadata["safety_band"]` if present, else `"GREEN"`.
  - Intent comes from `metadata["arbiter"]["decision"]`, `metadata["intent"]`, or `entry_type` fallback.
- Add a test that feeds object-style `TypedHistoryEntry` instances and dict-style history rows and asserts compressor key facts include user messages.

**State coherence:** This conversion is prompt-only. It must never mutate `history_active`, `self._history`, or Session State.

**Run:** `pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_episodic_compressor.py -v`

### Issue M6.E1.I4 -- Inject compressed context where history would have been read

**Files to change:**

- `k1/concierge/prompt/builder.py`
- `tests/k1/concierge/test_m6_e1_episodic_compression.py`
- `tests/k1/concierge/test_m04_e44_prompt_ss.py`

**Current behavior:** `compressed_context` is appended through scenario-data fallback or ignored by templates; it does not replace `history_active` in Stage 8.

**Implementation directive:**

- In `DynamicPromptBuilder.build(...)`, read `compressed_context = (scenario_data or {}).get("compressed_context", "")` before Stage 8.
- When `compressed_context` is non-empty, Stage 8 must omit the `history_active` `SSReadConfig` for that prompt build and append `compressed_context` at the point where history would normally appear.
- Preserve all other SS sections for the mode.
- Do not put `compressed_context` in `SCENARIO_DATA_TEMPLATES`; it is not scenario data. It is a replacement history block.
- Add a test that builds a STANDARD or WEAVE prompt with `compressed_context` and asserts raw history text beyond the recent window is absent while `== CONVERSATION HISTORY (COMPRESSED) ==` and `== RECENT CONVERSATION ==` are present.

**API contract:** `compressed_context` is a formatted string produced only by `EpisodicCompressor.build_compressed_context(...)` and begins with `== CONVERSATION HISTORY (COMPRESSED) ==` when episodes exist.

**Run:** `pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m04_e44_prompt_ss.py -v`

### Issue M6.E1.I5 -- Close M1-L7 with a live compression path

**Files to change:**

- `k1/concierge/experience/layer.py`
- `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py`
- `docs/architecture/kernel_sweep_status.md`
- `k1/concierge/OPEN_ISSUES.md`

**Implementation directive:**

- Add `self.episodic_compressor` to `ExperienceLayer`.
- In `ExperienceLayer.tick(...)`, when `context["conversation_history"]` reaches the compressor threshold, convert the history dicts to compressor turns and call `self.episodic_compressor.compress_all(turns)`.
- Store only metrics/output in the layer, not a replacement history. Suggested fields: `self.last_compressed_context`, `self.last_episodes_used`, `self.last_recent_turns_kept`.
- Keep prompt injection in `OppPipeline` / `DynamicPromptBuilder`; ExperienceLayer should not mutate Session State history.
- Remove the strict xfail marker from `test_m1_l7_experience_layer_compresses_after_sixteen_turns` only when `compressor.compression_count > 0` passes.
- Update tracker `M1-L7` to point to the live compressor path and mark it closed by M6.E1.I5.

**Run:** `pytest tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py::test_m1_l7_experience_layer_compresses_after_sixteen_turns -v`

**Epic M6.E2 -- Narrative Weaving**

### Issue M6.E2.I1 -- Preserve narrative signals in experience context

**Files to change:**

- `k1/concierge/session.py`
- `k1/concierge/experience/layer.py`
- `tests/k1/concierge/test_m6_e2_narrative_weaving.py` (create)
- `tests/k1/concierge/test_m15_experience_layer.py`

**Current behavior:** `ConciergeRuntime._build_experience_context()` emits history dicts with `entry_type`, `text`, `timestamp_ms`, and `source`, but `NarrativeWeaver.weave(...)` reads `thread`, `topic`, or `intent`.

**Implementation directive:**

- In `_build_experience_context()`, include `metadata` when available from history entries.
- Add `intent` to each history dict using this precedence: `metadata["arbiter"]["decision"]`, `metadata["intent"]`, `entry.entry_type`, then empty string.
- Add `topic` if metadata has `domain`, `topic`, or `current_thread`.
- Add `thread` if metadata has `thread` or if `task_id` maps to an active narrative thread.
- In `ExperienceLayer.tick(...)`, before calling `narrative_weaver.weave(...)`, normalize object-style entries and dict-style entries into dicts with at least `intent` and `text`.
- Add tests proving real `entry_type`-style history produces non-empty `NarrativeContext.active_threads` once repeated entries exist.

**State coherence:** Narrative extraction reads history and memory recalls only. It must not mutate history entries.

**Run:** `pytest tests/k1/concierge/test_m6_e2_narrative_weaving.py tests/k1/concierge/test_m15_experience_layer.py -v -k "narrative"`

### Issue M6.E2.I2 -- Write `NarrativeContext` into `narrative_active`

**Files to change:**

- `k1/concierge/session.py`
- `k1/sessionstate/sections/narrative_active.py` only if an existing public API is insufficient
- `tests/k1/concierge/test_m6_e2_narrative_weaving.py`
- `tests/k1/sessionstate/sections/test_narrative_active.py` only if the section API changes

**Implementation directive:**

- In `ConciergeRuntime._tick_experience()`, read `narrative = outputs.get("narrative")`.
- If `narrative` is absent, `narrative.active_threads` is empty, or current FSM state is `CLARIFYING_WORKER` / HITL mode, do nothing.
- Get `section = self._session_state.get_section("narrative_active")`.
- If `section.has_active_thread()` is false, call `section.create_thread(title=narrative.active_threads[0], goal=narrative.weave_suggestion, turn_number=self._fsm.turn_number, related_intents=narrative.active_threads[:5])`.
- If a primary thread exists and `section.primary_thread.title != narrative.active_threads[0]`, create a new thread with `auto_switch=True` only when salience for the new top thread is greater than the current top thread by at least `0.25`; otherwise update the existing thread goal/context summary.
- If a primary thread exists and matches, call `section.update_thread(primary.id, goal=narrative.weave_suggestion, turn_number=self._fsm.turn_number)`.
- Do not write the raw `NarrativeContext` object into Session State; use the section public methods.

**Prompt integration:** `DynamicPromptBuilder` already reads `narrative_active` in STANDARD, PRESENT, WEAVE, INTERRUPT, CANCEL, and ERROR modes. Once the section has a primary thread and goal, `_render_narrative_active_full(...)` and `_render_narrative_active_slim(...)` will surface it.

**State coherence:** ExperienceLayer may propose narrative context; Session State owns the durable active thread. During HITL relay/resolve, do not switch threads.

**Run:** `pytest tests/k1/concierge/test_m6_e2_narrative_weaving.py tests/k1/sessionstate/sections/test_narrative_active.py -v`

### Issue M6.E2.I3 -- Verify narrative prompt appearance in Front modes

**Files to change:**

- `tests/k1/concierge/test_m6_e2_narrative_weaving.py`
- `k1/concierge/prompt/builder.py` only if renderer gaps are found

**Implementation directive:**

- Add a prompt-builder test that creates a `narrative_active` section with primary thread title `travel_planning` and goal `Continue thread: travel_planning`.
- Build prompts for STANDARD, WEAVE, and PRESENT.
- Assert the prompt contains `Thread: travel_planning` in all three modes.
- Assert HITL_RELAY prompt does not contain `Thread: travel_planning`, because HITL prompt context is intentionally narrow.

**Run:** `pytest tests/k1/concierge/test_m6_e2_narrative_weaving.py -v -k "prompt"`

**Epic M6.E3 -- Dynamic Identity**

### Issue M6.E3.I1 -- Wire `DynamicIdentityContext` into OPP-7

**Files to change:**

- `k1/concierge/factory.py`
- `k1/concierge/protocols/opp_pipeline.py`
- `k1/concierge/session.py`
- `tests/k1/concierge/test_m6_e3_dynamic_identity.py` (create)

**Implementation directive:**

- This shares the factory work from M6.E1.I1: attach one `DynamicIdentityContext` per session to `OppPipeline`.
- Extend `OppPipeline.on_pre_prompt_build(...)` with `has_inflight_tasks: bool = False` and pass it into `DynamicIdentityContext.compute(...)`.
- In `front_handler(...)`, derive `has_inflight_tasks` from `task_state` or controller-injected scenario context and pass it to `opp_pipeline.on_pre_prompt_build(...)`.
- Derive `active_user_id` and `active_user_name` from Session State `meta` or `persona` when available. If no user name is available, pass empty strings.
- Add a test that exercises 11 calls and asserts OPP-7 role shifts from GUIDE to PEER, crisis affect returns SUPPORTER, and inflight tasks return EXECUTOR.

**State coherence:** One `DynamicIdentityContext` instance per session. It accumulates turn count and domain familiarity. Do not create one per prompt build.

**Run:** `pytest tests/k1/concierge/test_dynamic_identity.py tests/k1/concierge/test_m6_e3_dynamic_identity.py -v`

### Issue M6.E3.I2 -- Place `identity_block` after live grounding, not in scenario fallback

**Files to change:**

- `k1/concierge/prompt/builder.py`
- `tests/k1/concierge/test_m6_e3_dynamic_identity.py`

**Current behavior:** `identity_block` is appended through generic scenario-data formatting if no template consumes it. That buries the dynamic identity overlay instead of giving it high recency.

**Implementation directive:**

- In `DynamicPromptBuilder.build(...)`, read `identity_block = (scenario_data or {}).get("identity_block", "")`.
- Do not include `identity_block` in `_format_scenario_data(...)` fallback output. Filter it out of the scenario-data dict before calling `_format_scenario_data(...)`.
- Append `identity_block` after Stage 9.5 promoted blocks (`== NOW ==`, `== AFFECT STATE ==`, `== CONSCIENCE ==`) and before generic scenario data if possible. If preserving exact current stage order is simpler, append it immediately after Stage 9.5 and before final assembly.
- Keep the static `IDENTITY` prompt section unchanged. The dynamic identity block is a live overlay, not a replacement.

**Prompt contract:** The dynamic block must start with `== DYNAMIC IDENTITY CONTEXT ==` because `IdentitySnapshot.to_prompt_block()` is the single formatting entrypoint.

**Run:** `pytest tests/k1/concierge/test_m6_e3_dynamic_identity.py -v -k "prompt"`

### Issue M6.E3.I3 -- Prove identity remains Front-only

**Files to change:**

- `tests/k1/concierge/test_m6_e3_dynamic_identity.py`
- `k1/concierge/actors/back.py` only if a leak is found
- `k1/concierge/session.py` only if Back receives OPP by accident

**Implementation directive:**

- Add a test that spies on `DynamicPromptBuilder.build(...)` for a Back invocation and asserts `scenario_data` does not include `identity_block`.
- Add a session-level test that `front_handler(...)` receives `opp_pipeline` and `route_back_envelope(...)` does not.
- Add a leak-guard assertion that no Back prompt contains `== DYNAMIC IDENTITY CONTEXT ==`.

**State coherence:** Dynamic identity adapts Front voice only. Back task planning and capability invocation must remain deterministic executor behavior.

**Run:** `pytest tests/k1/concierge/test_m6_e3_dynamic_identity.py -v -k "front_only or back"`

**Run for M6:** `pytest tests/k1/concierge/test_episodic_compressor.py tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m6_e2_narrative_weaving.py tests/k1/concierge/test_dynamic_identity.py tests/k1/concierge/test_m6_e3_dynamic_identity.py tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py::test_m1_l7_experience_layer_compresses_after_sixteen_turns -v`

**Acceptance:** Front receives compressed history, narrative thread state, and dynamic identity context in the prompt. Back receives none of the identity overlay. HIL and safety turns remain uncompressed or preserved in recent context.

## M7 -- End-To-End Probes And Docs

**Purpose:** Lock the whole flow with focused probes that prove the user experiences one coordinated conversational mind while Front and Back remain distinct actors.

**Dependency rule for M7:** M7 is a probe milestone. If a probe depends on a symbol introduced by M2, M3, M5, or M6 and the symbol does not exist yet, mark the test `xfail(strict=True, reason="...")` with the exact missing issue id. Do not fake-pass by replacing the production symbol with a mock assertion subject.

**Known preconditions from the current plan:**

- M2 symbols such as `BackResultFrame`, `HILResolutionFrame`, and `WeavePresentationFrame` are plan-defined and may not exist until M2 lands.
- M3 symbols such as `ReActCheckpoint`, `ToolExecutionRecord`, and `BackControlEvent` are plan-defined and may not exist until M3 lands.
- M5 `WriteElisionGate` and M6 live OPP wiring are prerequisite for some M7 probes to be green instead of strict xfail.
- Existing test `test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume` already asserts `TOPIC_HIL_RESPONSE` appears before `TOPIC_TASK_RESUME`; do not duplicate that assertion elsewhere.

**Epic M7.E1 -- One-Brain Illusion Probes**

### Issue M7.E1.I1 -- No raw HIL JSON reaches final response

**Files to change:**

- `tests/k1/concierge/test_m7_e1_one_brain_illusion.py` (create)
- `k1/concierge/actors/front.py` only if the test exposes a leak
- `k1/concierge/actors/front_hil_envelope.py` only if envelope building loses fields

**Implementation directive:**

- Build a real `HILEnvelope` dict with `kind="clarification"`, a `hil_request_id`, and payload question/options.
- Put that dict under `pending_hil.envelope` in a fake suspended task-state section.
- Drive `front_handler(...)` through HITL_RESOLVE using a fake model that attempts to echo scenario data.
- Capture `TOPIC_FINAL_RESPONSE` and `TOPIC_HIL_RESPONSE`.
- Assert final response text does not contain `hil_request_id`, raw JSON keys such as `"kind":`, `HILEnvelope`, `caller_key`, or `trace_id`.
- Assert the emitted HIL response envelope does contain the original `hil_request_id` and `kind`.
- Round-trip the HIL response through `HILResponseEnvelope.from_dict(resp.to_dict())` or dict equivalent and assert no field loss.

**Acceptance:** The user sees a natural acknowledgement/confirmation. The protocol bus still receives the exact envelope identity.

**Run:** `pytest tests/k1/concierge/test_m7_e1_one_brain_illusion.py::test_m7_e1_i1_no_raw_hil_json_in_final_response -v`

### Issue M7.E1.I2 -- No Back `final_answer` is surfaced verbatim

**Files to change:**

- `tests/k1/concierge/test_m7_e1_one_brain_illusion.py`
- `k1/concierge/actors/front.py` only if leak occurs
- `k1/concierge/actors/frames.py` if M2 frame types are not yet present

**Implementation directive:**

- Build a `task.complete.v1` payload where `final_answer` is deliberately machine-like and contains sentinel text `INTERNAL_RESULT_DO_NOT_SURFACE`.
- If `BackResultFrame` exists, include a frame with user-safe facts like `Dinner at 7pm confirmed`.
- Drive `_extract_scenario_data(PRESENT, ...)` and the prompt path used by `front_handler(...)`.
- Assert scenario data and final text do not contain the sentinel.
- If `BackResultFrame` is absent, mark this specific test strict xfail with reason `M2.E1.I1 BackResultFrame not implemented`.

**State coherence:** Back may carry raw executor output for audit/debug, but Front presentation input must use typed facts/artifacts. `final_answer` is never the canonical user-facing field after M2.

**Run:** `pytest tests/k1/concierge/test_m7_e1_one_brain_illusion.py::test_m7_e1_i2_back_final_answer_not_surfaced_verbatim -v`

### Issue M7.E1.I3 -- No WEAVE delivery during active HIL unless critical

**Files to change:**

- `tests/k1/concierge/test_m08_e82_weave_decision.py`
- `k1/concierge/protocols/weave_policy.py` only if policy fails
- `k1/concierge/fsm/controller.py` only if `_has_pending_hitl()` is wrong

**Implementation directive:**

- Add a focused test to the existing weave policy file.
- Build `WeaveSignal` with `hil_pending=True` and normal urgency. Assert decision is `DEFER` or `SUPPRESS` according to the M4 policy priority chosen there.
- Build the same signal with `urgency="critical"`. Assert it is not deferred/suppressed solely because of HIL.
- Add a controller-level variant after M5.E2.I2 that proves unified pending HIL makes `_has_pending_hitl()` true.

**Run:** `pytest tests/k1/concierge/test_m08_e82_weave_decision.py -v -k "hil_pending"`

### Issue M7.E1.I4 -- Accepted modification reaches Back

**Files to change:**

- `tests/k1/concierge/test_m7_e1_one_brain_illusion.py`
- `k1/concierge/react/loop.py` only if control-event injection fails
- `k1/concierge/fsm/controller.py` only if `_handle_arbiter_modify(...)` swallows the event

**Implementation directive:**

- If `BackControlEvent` and `react_loop(control_queue=...)` from M3 exist, create an `asyncio.Queue`, enqueue a parameter update after iteration 1, and run a two-iteration fake Back loop.
- Assert the second model request contains a message describing the accepted modification.
- Spy on the queue insertion from `_handle_arbiter_modify(...)`; assert it inserts exactly one control event for the target task.
- If `BackControlEvent` is absent, mark strict xfail with reason `M3.E4.I1 BackControlEvent not implemented`.

**Run:** `pytest tests/k1/concierge/test_m7_e1_one_brain_illusion.py::test_m7_e1_i4_accepted_modification_reaches_back -v`

**Epic M7.E2 -- ReAct Robustness Probes**

### Issue M7.E2.I1 -- Hung tool times out and exits typed

**Files to change:**

- `tests/k1/concierge/react/__init__.py` (create if absent)
- `tests/k1/concierge/react/test_m7_e2_react_robustness.py` (create)
- `k1/concierge/react/loop.py` only if raw timeout leaks

**Implementation directive:**

- Configure `react.tool_timeout_ms` to a tiny value.
- Use a fake dispatcher whose `dispatch(...)` awaits forever.
- Run `react_loop(...)` with a model response that calls the slow tool.
- Assert the loop returns a `ReactResult` and does not raise raw `asyncio.TimeoutError`.
- Assert error text or code contains `tool_timeout`.
- If `ToolExecutionRecord` exists after M3, assert the record has `result_status="timeout"` and `duration_ms >= tool_timeout_ms`.

**Run:** `pytest tests/k1/concierge/react/test_m7_e2_react_robustness.py::test_m7_e2_i1_hung_tool_times_out_typed -v`

### Issue M7.E2.I2 -- Cancel during tool execution exits within bounded time

**Files to change:**

- `tests/k1/concierge/react/test_m7_e2_react_robustness.py`
- `k1/concierge/react/loop.py` only if cancellation waits for a hung tool

**Implementation directive:**

- Start `react_loop(...)` with a slow tool and a real cancellation token.
- Cancel the token shortly after the tool begins.
- Wrap the await in `asyncio.wait_for(..., timeout=0.5)`.
- Assert the result status is `cancelled`, `failed`, or another typed terminal status; do not accept a raw `CancelledError` escaping the loop.
- Snapshot `asyncio.all_tasks()` before and after; exclude the current pytest task and assert no new pending task remains.

**Run:** `pytest tests/k1/concierge/react/test_m7_e2_react_robustness.py::test_m7_e2_i2_cancel_during_tool_exits_bounded -v`

### Issue M7.E2.I3 -- Resume from checkpoint does not repeat successful tools

**Files to change:**

- `tests/k1/concierge/react/test_m7_e2_react_robustness.py`
- `k1/concierge/react/checkpoint.py` if M3 checkpoint type is not yet implemented
- `k1/concierge/actors/back.py` only if resume path ignores checkpoint

**Implementation directive:**

- If `ReActCheckpoint` is absent, mark strict xfail with reason `M3.E1.I1 ReActCheckpoint not implemented`.
- Build a checkpoint whose completed tool call id set contains `call_001` and whose messages contain the prior observation.
- Resume via `react_loop(...)` or `back_resume_handler(...)` depending on M3 implementation.
- Spy on `ToolDispatcher.dispatch` and assert it is never called for `call_001` or the same `args_hash`.
- Assert the prior observation appears in the first resumed model request.

**Run:** `pytest tests/k1/concierge/react/test_m7_e2_react_robustness.py::test_m7_e2_i3_resume_from_checkpoint_no_tool_repeat -v`

### Issue M7.E2.I4 -- Invalid tool args produce typed repair loop and degenerate stop

**Files to change:**

- `tests/k1/concierge/react/test_m7_e2_react_robustness.py`
- `k1/concierge/react/loop.py` only if repair messages or degenerate detection are missing
- `k1/concierge/tools/dispatcher.py` only if schema errors are untyped

**Implementation directive:**

- Use a fake dispatcher that returns a typed schema validation error for invalid args, not a thrown exception.
- Use a fake model that repeats the same invalid tool call.
- Assert the loop appends a repair message that includes the schema error code.
- After the configured identical-failure threshold, assert the loop returns `ReactResult.status="failed"` with `error_code="REACT_LOOP_DEGENERATE"` or the exact M3-defined code.
- Assert no raw exception escapes.

**Run:** `pytest tests/k1/concierge/react/test_m7_e2_react_robustness.py::test_m7_e2_i4_invalid_tool_args_typed_repair -v`

**Epic M7.E3 -- HIL End-To-End Probes**

### Issue M7.E3.I1 -- Unified clarification round trip

**Files to change:**

- `tests/k1/concierge/test_m7_e3_hil_e2e.py` (create)
- `tests/k1/hil/test_service_front_roundtrip.py` may be extended instead if duplication is lower

**Implementation directive:**

- Reuse the `InMemoryBus` and `FrontEcho` pattern from `tests/k1/hil/test_service_front_roundtrip.py`.
- Start `HumanInTheLoopService` with `HILLedgerAdapter(None)`, `SafetyBandPolicy()`, and default `HILConfig()`.
- Call `ask_clarification(...)` with a `ClarificationRequest`.
- Simulate Front by publishing `TOPIC_HIL_RESPONSE` with a `HILResponseEnvelope` for the same `hil_request_id` and payload containing an answer.
- Assert the returned typed clarification response contains the answer and `timed_out is False`.
- Assert no `TOPIC_TASK_RESUME` was published.
- Assert `HILResponseEnvelope.from_dict(envelope.to_dict()) == envelope`.

**Run:** `pytest tests/k1/concierge/test_m7_e3_hil_e2e.py::test_m7_e3_i1_unified_clarification_round_trip -v`

### Issue M7.E3.I2 -- Approval approve/reject/modify round trip

**Files to change:**

- `tests/k1/concierge/test_m7_e3_hil_e2e.py`
- `k1/concierge/actors/front_hil_envelope.py` only if mapping fails

**Implementation directive:**

- Parametrize cases `approve`, `reject`, and `modify`.
- Use `HumanInTheLoopService.request_approval(...)` with an `ApprovalRequest` containing side-effect summary.
- Simulate Front responses through `build_hil_response_envelope_dict(...)` or direct `HILResponseEnvelope` construction.
- Assert approve maps to `decision == "approve"`; reject maps to `decision == "reject"`; modify maps to `decision == "modify"` and preserves modifications.
- Assert every published response has the original `hil_request_id`.

**Run:** `pytest tests/k1/concierge/test_m7_e3_hil_e2e.py::test_m7_e3_i2_approval_round_trip -v`

### Issue M7.E3.I3 -- Capability gate approve/deny round trip

**Files to change:**

- `tests/k1/concierge/test_m7_e3_hil_e2e.py`
- `k1/hil/service.py` only if gate mapping fails

**Implementation directive:**

- Parametrize `allow` and `deny` responses for `gate_capability(...)`.
- Build `CapabilityGateRequest` with `CapabilityContractView(safety_band_min="AMBER")`.
- Assert allow returns `GateOutcome.ASK_APPROVED` or the current approved enum, and deny returns the current denied enum.
- Assert no task resume topic is published.
- Assert response envelope round-trip preserves `hil_request_id`, `kind`, `payload`, and `timed_out`.

**Run:** `pytest tests/k1/concierge/test_m7_e3_hil_e2e.py::test_m7_e3_i3_capability_gate_round_trip -v`

### Issue M7.E3.I4 -- Legacy bridge ordering stays locked

**Files to change:**

- `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`
- `docs/architecture/kernel_sweep_status.md`

**Current behavior:** The existing `test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume` already records `TOPIC_HIL_RESPONSE` and `TOPIC_TASK_RESUME` and asserts HIL response index is less than task resume index. It is currently strict xfail because the legacy path does not yet emit protocol-level `hil.response.v1` consistently.

**Implementation directive:**

- Do not create a duplicate test for this ordering.
- When M1/M5 HIL unification fixes the production path, remove the strict xfail marker and keep the existing ordering assertion.
- Add a same-task assertion if not already present at implementation time: the HIL response and task resume must refer to the same `task_id` or correlated `hil_request_id`.
- Update tracker M1-X10 or M7-C-E3-I4 to point at this test.

**Run:** `pytest tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume -v`

**M7 documentation updates:**

- Add a `M7-C -- Concierge End-To-End Probes` section to `docs/architecture/kernel_sweep_status.md` with rows for M7.E1.I1-I4, M7.E2.I1-I4, and M7.E3.I1-I4. Keep rows open until tests exist and are green or confirmed strict xfail.
- Add `ISSUE-C09` to `k1/concierge/OPEN_ISSUES.md` if M2 frame symbols are still absent when M7 tests land: `BackResultFrame`, `HILResolutionFrame`, and `WeavePresentationFrame` are required by M7 presentation/leak probes.
- Add `ISSUE-C10` to `k1/concierge/OPEN_ISSUES.md` if M3 ReAct symbols are still absent when M7 tests land: `ReActCheckpoint`, `ToolExecutionRecord`, and `BackControlEvent` are required by M7 ReAct/control probes.
- Every strict xfail must cite either `ISSUE-C09`, `ISSUE-C10`, or the exact milestone issue (`M2.E1.I1`, `M3.E1.I1`, `M3.E4.I1`, etc.).

**Run for M7:** `pytest tests/k1/concierge/test_m7_e1_one_brain_illusion.py tests/k1/concierge/react/test_m7_e2_react_robustness.py tests/k1/concierge/test_m7_e3_hil_e2e.py tests/k1/concierge/test_m08_e82_weave_decision.py -v`

**Additional live run for M7.E3.I4 only:** `pytest tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py::test_m1_x10_legacy_hitl_resolution_emits_hil_response_before_resume -v`

**Test discipline:** only run each issue's targeted tests and directly touched regression tests. Do not run broad kernel or fabric suites.

## Suggested Build Order

1. **M0:** reconcile tracker and stale gaps.
2. **M1:** HIL unification and structured resolution.
3. **M3:** ReAct checkpoint/control-event hardening.
4. **M2:** typed Back/Front handoff frames.
5. **M4:** weave policy and natural delivery.
6. **M5:** ledger/state ownership.
7. **M6:** memory and continuity.
8. **M7:** complete end-to-end probes and docs.

My strongest recommendation: start with **M1 + M3**. HIL unification fixes the most visible split-brain behavior, and ReAct checkpoint/control events make every later enhancement safer.
