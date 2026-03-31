# K1 Concierge V3 -- Milestones, Epics & Issues

> Derived from `v3_whiteboard.md`. This is the execution skeleton.
> Each milestone has a clear gate. Epics group related work. Issues are
> specific tasks to be refined after POC exploration.
>
> Status legend: `[ ]` not started, `[~]` in progress, `[x]` done

---

## M0: V2 Stabilization & Pre-Build Fixes

**Goal:** Eliminate V2 ambiguities and stabilize current POC behavior so V3
work starts from a known-good baseline.

**Gate:** All V2 consistency fixes applied. Current FSM trace tables (WB 13.3
A-E) pass as automated tests. No duplicate timeout/limit sources remain.

**Existing test files (M0 baseline):**

- `tests/poc/test_m08_fsm_controller.py` -- FSM states, transition table, controller event handlers, cancel handler, suspension manager, FrontLock, weave path
- `tests/poc/test_m08_epics_9_12.py` -- ConciergeControlExtension, TaskBridge
- `tests/poc/test_m06_front_handler.py` -- PromptMode enum, determine_mode routing
- `tests/poc/test_m05_react_loop.py` -- ReactResult, ReAct iteration constants, tool choice resolution
- `tests/poc/test_m07_back_handler.py` -- Back handler

**Key config file:** `poc/k1_poc/config/defaults.yaml` -- single YAML with all runtime-tunable values.

---

### E0.1 -- V2 Consistency Cleanup

Source: WB 7, 12.2

#### 0.1.1 -- Normalize weave timing policy (300ms vs 500ms)

**Problem:** Three sources disagree on WeaveBatcher batch window duration:

| Source | Value | Location |
|--------|-------|----------|
| Code constant | 500ms | `poc/k1_poc/protocols/weave_batcher.py:42` -- `WEAVE_BATCH_WINDOW_MS: int = 500` |
| Config default | 500ms | `poc/k1_poc/config/defaults.yaml:309` -- `weave_batch_window_ms: 500` |
| V2 design doc scenario | 300ms | `poc/k1_poc/concierge_poc_design_v2.md:8309` -- "Two async events arrive within the WeaveBatcher window (300ms)" |
| Architecture diagram | 300ms | `poc/k1_poc/concierge_poc_architecture.mmd:543` -- "WeaveBatcher 300ms batch window" |

The code and config both use 500ms. The V2 design doc and architecture diagram say 300ms.

**DECIDED: 500ms is the authoritative value.** Code and config are correct. Fix docs only.

**Action:**

1. Update `concierge_poc_design_v2.md` lines 8309, 8323, 8355: change "300ms" to "500ms".
2. Update `concierge_poc_architecture.mmd` line 543: change "300ms batch window" to "500ms batch window".
3. Verify no other doc references to 300ms weave window exist.

**Files to touch:** `concierge_poc_design_v2.md`, `concierge_poc_architecture.mmd` (doc-only fix).

---

#### 0.1.2 -- Align WEAVE mode tool policy with scenarios

**Problem:** WEAVE mode tool allowlist may be too narrow for some scenarios.

**Current state (code):**

`poc/k1_poc/prompt/mode.py:96-99`:

```python
PromptMode.WEAVE: [
    "update_beliefs",
    "update_narrative",
],
```

WEAVE mode allows only `update_beliefs` and `update_narrative`. Compare to PRESENT mode (same list) and STANDARD mode (8 tools including `recall_memory`, `dispatch_task`, etc.).

**Question:** Should WEAVE mode also allow `update_scoreboard` (to update salience after async results land)? The V2 design doc scenarios imply the LLM may want to update scoreboard when weaving results. Current code does not allow it.

Also: should WEAVE mode allow `acknowledge` as a tool? The V2 design doc is ambiguous. Current code does not have an `acknowledge` tool defined anywhere -- acknowledgements are handled by Front emit ordering, not a tool call.

**DECIDED: Add `update_scoreboard` to WEAVE mode allowlist.** Rationale: when async results are woven, salience scoring should be updated in the same turn.

**Action:**

1. In `poc/k1_poc/prompt/mode.py:96-99`, add `"update_scoreboard"` to the WEAVE allowlist so it becomes: `["update_beliefs", "update_narrative", "update_scoreboard"]`.
2. Add a docstring comment explaining why scoreboard is allowed during WEAVE.
3. The `acknowledge` tool does NOT exist -- no change needed for it.

**Files to touch:** `poc/k1_poc/prompt/mode.py` (lines 96-99).

---

#### 0.1.3 -- Normalize topic namespaces for HITL/orchestration signaling

**Current state (code):** Topics are well-defined in `poc/k1_poc/bus/topics.py`:

| Namespace | Topics | Count |
|-----------|--------|-------|
| `k1.session.*` | user.input, artifact.created, turn.started, turn.completed, state.updated | 5 |
| `k1.response.*` | stream, final, clarification | 3 |
| `k1.orchestration.*` | task.dispatch/complete/failed/cancel/suspended/resume/accepted, findings.ready, clarification.request/response, delta, dag.completed | 12 |
| `k1.tool.*` | started, completed | 2 |
| `k1.hil.*` | request, response | 2 |
| `k1.planner.*` | plan.ready | 1 |
| `k1.internal.*` | weave.batch | 1 |
| `k1.affect.*` | update (RELAXED) | 1 |
| `k1.proactive.*` | fill (RELAXED) | 1 |

**Problem:** HITL events use TWO different topic namespaces:

- `k1.orchestration.task.suspended.v1` / `k1.orchestration.task.resume.v1` -- the FSM lifecycle path (suspension/resume as task lifecycle events)
- `k1.hil.request.v1` / `k1.hil.response.v1` -- the HITL-specific path

This creates ambiguity: when Back needs HITL, does it emit `task.suspended` (which FSM routes) or `hil.request` (which Front subscribes to)? Currently the FSM handler `_on_task_suspended` handles the lifecycle while `hil.*` topics are in Front subscriptions but their routing is separate.

**Action:**

1. Document the authoritative routing: `task.suspended` is FSM lifecycle; `hil.request/response` are protocol-level detail within the suspension flow.
2. Add a comment block in `bus/topics.py` clarifying the relationship.
3. Verify that `FRONT_SUBSCRIPTIONS` includes `TOPIC_HIL_REQUEST` (line ~174: yes, it does) and that `BACK_SUBSCRIPTIONS` includes `TOPIC_HIL_RESPONSE` (line ~185: yes, it does).

**Files to touch:** `poc/k1_poc/bus/topics.py` (documentation comment only).

**Decision needed:** None -- the routing is correct, just needs documentation.

---

#### 0.1.4 -- Eliminate topic constant duplication across modules

**Current state:** Topic constants are defined in THREE independent locations with different naming conventions but identical string values:

| Source | Naming Pattern | Count | Example |
|--------|---------------|-------|---------|
| `poc/k1_poc/bus/topics.py` | `TOPIC_TASK_DISPATCH` | 28 | `"k1.orchestration.task.dispatch.v1"` |
| `poc/k1_poc/task/topics.py` | `TASK_DISPATCH` | 10 | `"k1.orchestration.task.dispatch.v1"` |
| `poc/k1_poc/prompt/mode.py:221` | `_TOPIC_WEAVE_BATCH` | 1 | `"k1.internal.weave.batch.v1"` |

**The 10 duplicate constants in `task/topics.py`:**

```
TASK_DISPATCH, TASK_COMPLETE, TASK_FAILED, TASK_CANCEL,
TASK_SUSPENDED, TASK_RESUME, TASK_ACCEPTED,
ORCHESTRATION_DELTA, DAG_COMPLETED, WEAVE_BATCH
```

Plus `ALL_TASK_TOPICS` frozenset that aggregates them.

**Problem:** Same string values, different Python constant names (`TOPIC_*` vs bare names). If either file changes, the other silently drifts. This is the EXACT same anti-pattern as 0.2.1 (dual timeout sources).

**Import sites for `task/topics.py` (14 total):**

- `poc/k1_poc/task/envelope_bridge.py:28` -- imports `TASK_COMPLETE, TASK_DISPATCH, TASK_FAILED`
- `poc/k1_poc/task/__init__.py:78` -- re-exports all 10 constants
- `poc/k1_poc/protocols/cancel_events.py:25` -- imports `TASK_FAILED`
- `tests/poc/test_m13_epics_7_8_9.py:81` -- imports `TASK_RESUME, TASK_SUSPENDED`
- `tests/poc/test_m12_epics_4_5_6.py:41,614,619` -- imports `WEAVE_BATCH, ALL_TASK_TOPICS`
- `tests/poc/test_m12_epics_1_2_3.py:51` -- imports `TASK_RESUME, TASK_SUSPENDED`
- `tests/poc/test_m10_epics_4_5_6.py:28` -- imports multiple
- `tests/poc/test_m10_epics_10_11_12.py:35` -- imports multiple
- `poc/k1_poc/docs/concierge_poc_plan.md` (4 doc references)

**Action:**

1. **`bus/topics.py` is the single source of truth.** All topic constants must be imported from there.
2. In `poc/k1_poc/task/topics.py`: replace all 10 constant definitions with re-exports from `poc.k1_poc.bus.topics`. Keep `ALL_TASK_TOPICS` frozenset but build it from the imported constants. Add deprecation comment directing future imports to `bus/topics.py`.
3. In `poc/k1_poc/prompt/mode.py:221`: replace `_TOPIC_WEAVE_BATCH = "k1.internal.weave.batch.v1"` with `from poc.k1_poc.bus.topics import TOPIC_WEAVE_BATCH`. Update reference at `mode.py:314`.
4. Add a comment block at top of `bus/topics.py` stating: "This module is the SINGLE SOURCE OF TRUTH for all POC topic constants. Do not define topic strings elsewhere."
5. Verify no other files define inline topic strings (search for `"k1.orchestration."` and `"k1.internal."` as string literals outside `bus/topics.py`).

**Files to touch:**

- `poc/k1_poc/task/topics.py` (replace definitions with re-exports)
- `poc/k1_poc/prompt/mode.py` (lines 221, 314)
- `poc/k1_poc/bus/topics.py` (add authoritative-source comment)

---

#### 0.1.5 -- Formalize FRONT_SUBSCRIPTIONS / BACK_SUBSCRIPTIONS routing contract

**Current state:** `bus/topics.py` lines 162-178 contain a critical code comment explaining why `FRONT_SUBSCRIPTIONS` is intentionally only 4 topics:

```
FRONT_SUBSCRIPTIONS = {TOPIC_TASK_ACCEPTED, TOPIC_ORCHESTRATION_DELTA, TOPIC_HIL_REQUEST, TOPIC_PLAN_READY}
```

The comment explains: FSM is the sole routing authority for `task.complete`, `task.failed`, `task.suspended`, `findings.ready`, `clarification.request`, `dag.completed`, `weave.batch`, `proactive.fill`. Including them in `FRONT_SUBSCRIPTIONS` causes **DUPLICATE delivery** (bus delivers to subscription + FSM routes to Front separately).

`BACK_SUBSCRIPTIONS` has 7 topics:

```
BACK_SUBSCRIPTIONS = {TOPIC_USER_INPUT, TOPIC_TASK_DISPATCH, TOPIC_TASK_CANCEL, TOPIC_TASK_RESUME, TOPIC_CLARIFICATION_RESPONSE, TOPIC_HIL_RESPONSE, TOPIC_AFFECT_UPDATE}
```

**Problem:** This routing contract is buried in comments. Any developer adding a new topic could add it to `FRONT_SUBSCRIPTIONS` and create a duplicate delivery loop. No test validates the subscription sets are correct.

**Action:**

1. Promote the comment at `bus/topics.py:162-178` to a formal docstring/architecture note explaining the routing invariant: "FSM-routed topics MUST NOT appear in FRONT_SUBSCRIPTIONS."
2. Add a `FSM_ROUTED_TOPICS` frozenset that explicitly lists the topics FSM routes directly:

   ```python
   FSM_ROUTED_TOPICS = {TOPIC_TASK_COMPLETE, TOPIC_TASK_FAILED, TOPIC_TASK_SUSPENDED,
                         TOPIC_FINDINGS_READY, TOPIC_CLARIFICATION_REQUEST,
                         TOPIC_DAG_COMPLETED, TOPIC_WEAVE_BATCH, TOPIC_PROACTIVE_FILL}
   ```

3. Add a `assert FSM_ROUTED_TOPICS.isdisjoint(FRONT_SUBSCRIPTIONS)` check (or test).
4. Add conformance test (issue 0.3.14) validating `FRONT_SUBSCRIPTIONS` and `BACK_SUBSCRIPTIONS` disjointness with `FSM_ROUTED_TOPICS`.

**Files to touch:** `poc/k1_poc/bus/topics.py` (lines 155-185).

---

#### 0.1.6 -- Define stale-read policy for long-running Back tasks

**Current state:** Back reads SS once at task start via `_read_ss_snapshot()` in `poc/k1_poc/actors/back.py:159`. The V2 design doc (line 5070 of `concierge_poc_plan.md`) states:

> "Back reads SS ONCE at task start. It does NOT re-read SS during ReAct iterations. The dispatch snapshot is the contract."

**Problem:** This policy exists in the design doc but is not formalized in code as an enforced contract. There is no guard preventing Back from accessing SS after the initial snapshot. For resumed tasks, `concierge_poc_plan.md:5811` says SS is re-read at resume time.

**Action:**

1. Add a docstring/contract comment at the top of `back_handler()` (`back.py:343`) explicitly stating: snapshot-at-start, no mid-loop re-reads, re-read on resume.
2. Consider adding a lightweight guard: after `_read_ss_snapshot()`, Back's execution context should not hold a reference to the live SS manager. Currently `back_handler` receives `ss` as a parameter and calls `_read_ss_snapshot(ss)` once, but the `ss` reference remains available.
3. Document the resume re-read contract in `back_resume_handler` (note: this handler exists but is not currently wired -- see M3 issue 3.1.2).

**Files to touch:** `poc/k1_poc/actors/back.py` (documentation + optional guard).

**DECIDED: Documentation-only for M0.** Add contract comments to `back.py`. A runtime guard (read-only SS proxy) is out of scope for M0 and would be a V3 enhancement if needed.

**Files to touch:** `poc/k1_poc/actors/back.py` (documentation comments only).

---

### E0.2 -- Protocol Config Unification

Source: WB 12.2.A, 12.2.B

#### 0.2.1 -- Create single timeout authority

**Problem:** Timeout defaults are defined in two places with different units:

| Location | Type | Values | Unit |
|----------|------|--------|------|
| `protocols/suspension.py:50-53` | `SUSPENSION_TIMEOUTS` | clarification=60.0, approval=120.0, selection=90.0 | **seconds** |
| `protocols/hitl.py:63-66` | `HIL_TIMEOUTS` | clarification=60000, approval=120000, selection=90000 | **milliseconds** |

Both have `_get_*_timeouts()` helpers that read from central config (`defaults.yaml`). But the module-level constants remain as fallback defaults and create drift risk.

**Central config current state** (`defaults.yaml:301-312`):

```yaml
protocols:
  suspension_timeouts:
    clarification: 160.0    # NOTE: 160s here vs 60s in suspension.py constant!
    approval: 120.0
    selection: 90.0
  hil_timeouts:
    clarification: 60000
    approval: 120000
    selection: 90000
```

**Actual drift found:** `suspension_timeouts.clarification` in `defaults.yaml` is **160.0s** but the module constant in `suspension.py:51` is **60.0s**. If config loading fails or is skipped, the fallback uses 60s instead of the intended 160s.

**DECIDED: Seconds everywhere. Clarification timeout is 60s (fix defaults.yaml).**

Rationale: Python-native convention. HITL millisecond values will be converted to seconds.

**Action:**

1. Remove module-level `SUSPENSION_TIMEOUTS` dict from `suspension.py:50-53`. Make `_get_suspension_timeouts()` the sole accessor.
2. Remove module-level `HIL_TIMEOUTS` dict from `hitl.py:63-66`. Make `_get_hil_timeouts()` the sole accessor.
3. Convert `hil_timeouts` values in `defaults.yaml` from milliseconds to seconds: `{clarification: 60.0, approval: 120.0, selection: 90.0}`.
4. Fix `suspension_timeouts.clarification` in `defaults.yaml` from 160.0 to 60.0.
5. Update `_get_hil_timeouts()` return type to float (seconds). Remove any ms-to-s conversion at call sites if present.
6. Add `_s` suffix to config keys if desired for clarity (e.g., `clarification_s: 60.0`).

**Canonical timeout values (seconds):**

- clarification: 60.0
- approval: 120.0
- selection: 90.0

**Files to touch:**

- `poc/k1_poc/protocols/suspension.py` (lines 50-53, 61-63)
- `poc/k1_poc/protocols/hitl.py` (lines 63-66, 70-72)
- `poc/k1_poc/config/defaults.yaml` (lines 301-312)

---

#### 0.2.2 -- Unify suspension limit source

**Problem:** Two independent limit sources for max suspensions per task:

| Location | Constant/Field | Value | Used By |
|----------|---------------|-------|---------|
| `protocols/suspension.py:57` | `MAX_SUSPENSIONS_PER_TASK = 2` | 2 | `suspension_manager.py:105` -- `if count > MAX_SUSPENSIONS_PER_TASK` |
| `protocols/hitl_coordinator.py:81` | `HILCoordinatorConfig.max_rounds = MAX_SUSPENSIONS_PER_TASK` | 2 (default) | `HILCoordinator` config |
| `config/defaults.yaml:298` | `max_suspensions_per_task: 2` | 2 | `suspension.py:69` via `_get_max_suspensions_per_task()` |

Currently `hitl_coordinator.py:81` imports `MAX_SUSPENSIONS_PER_TASK` from `suspension.py` as its default. The config path (`_get_max_suspensions_per_task()`) exists but `suspension_manager.py:105` uses the imported constant directly instead of calling the config accessor.

**Action:**

1. In `suspension_manager.py`, replace direct use of `MAX_SUSPENSIONS_PER_TASK` constant with `_get_max_suspensions_per_task()` call (or inject via constructor).
2. In `hitl_coordinator.py:81`, replace `MAX_SUSPENSIONS_PER_TASK` import with config read from `get_config().protocols.max_suspensions_per_task`.
3. Remove the module-level `MAX_SUSPENSIONS_PER_TASK` constant from `suspension.py` (keep only the config accessor).
4. Keep `MAX_CONCURRENT_SUSPENSIONS = 1` as a true invariant (or also move to config).

**Files to touch:**

- `poc/k1_poc/protocols/suspension.py` (line 57 -- remove constant, line 69 -- keep accessor)
- `poc/k1_poc/protocols/suspension_manager.py` (line 29 -- remove import, line 105 -- use config)
- `poc/k1_poc/protocols/hitl_coordinator.py` (line 52 -- remove import, line 81 -- use config)

---

#### 0.2.3 -- Remove stale backward-compat hardcodes from bus/setup.py

**Problem:** `poc/k1_poc/bus/setup.py` lines 49-54 define four module-level constants that duplicate values already read from config at runtime:

```python
POC_MAILBOX_CAPACITY = 64       # backward-compat; runtime reads from config
POC_GAP_TIMEOUT_MS = 5000       # backward-compat; runtime reads from config
ACTOR_FRONT = "front_half"      # backward-compat; runtime reads from config
ACTOR_BACK = "back_half"        # backward-compat; runtime reads from config
```

This is the EXACT same anti-pattern as 0.2.1 (dual timeout sources) and 0.2.2 (dual suspension limit sources). The runtime functions (`create_poc_bus`, `register_poc_actors`) correctly read from `get_config().bus.*`, but the stale module-level constants invite confusion.

**Consumers of these constants:**

- `POC_MAILBOX_CAPACITY`: No import found outside `setup.py` itself. Stale alias.
- `POC_GAP_TIMEOUT_MS`: No import found outside `setup.py` itself. Stale alias.
- `ACTOR_FRONT` / `ACTOR_BACK`: Used in `setup.py:register_poc_actors()` but could be replaced with config reads. Also re-exported via `bus/__init__.py:45`.

**Config equivalents** (`defaults.yaml`):

```yaml
bus:
  mailbox_capacity: 64
  gap_timeout_ms: 5000
  actor_ids:
    front: "front_half"
    back: "back_half"
```

Note: Need to verify `actor_ids` section exists in `defaults.yaml`. If not, add it.

**Action:**

1. Remove `POC_MAILBOX_CAPACITY` and `POC_GAP_TIMEOUT_MS` constants from `setup.py`. They are unused outside the module and the runtime already reads config.
2. Replace `ACTOR_FRONT` / `ACTOR_BACK` in `register_poc_actors()` with config reads: `get_config().bus.actor_ids.front` and `.back` (add to `defaults.yaml` if missing).
3. Remove re-exports from `bus/__init__.py` for the deleted constants.
4. Verify no other import site references these constants (grep confirms: none outside `setup.py` and `__init__.py`).

**Files to touch:**

- `poc/k1_poc/bus/setup.py` (lines 49-54 -- remove constants, update `register_poc_actors`)
- `poc/k1_poc/bus/__init__.py` (remove re-exports)
- `poc/k1_poc/config/defaults.yaml` (add `actor_ids` section if missing)

---

### E0.3 -- Current-Behavior Conformance Tests

Source: WB 13.6, 14.6, 15.6

**Test location:** All new tests go in `tests/poc/` directory following existing naming: `test_m00_v3_conformance.py` (suggested).

**Test infrastructure:** Existing tests in `test_m08_fsm_controller.py` provide patterns for:

- Building `ConciergeController` with mock bus, model, session state
- Creating envelopes via `poc/k1_poc/bus/builders.py`
- Asserting state transitions and emitted events

**What already has test coverage (partial -- not the specific race/ordering scenarios):**

| Area | Existing Tests | File |
|------|---------------|------|
| Interrupt from COMPANIONING | `test_8_2_5` | `test_m08_fsm_controller.py:530` |
| Interrupt from PROGRESSING | `test_8_2_9` | `test_m08_fsm_controller.py:569` |
| Cancel dedup | `test_8_2_16` | `test_m08_fsm_controller.py:644` |
| Cancel confirm (failed+cancelled) | `test_8_2_19` | `test_m08_fsm_controller.py:686` |
| Task suspended -> CLARIFYING_WORKER | `test_8_2_23` | `test_m08_fsm_controller.py:742` |
| Weave path (DELIVERING->WEAVING->LISTENING) | `test_8_2_37` | `test_m08_fsm_controller.py:969` |
| Queues when front busy | `test_8_2_17` | `test_m08_fsm_controller.py:659` |

**What is NOT tested (the M0 conformance gaps):**

---

#### 0.3.1 -- Test: interrupt during PROGRESSING + simultaneous task completion

**Scenario:** FSM in PROGRESSING. User sends input (triggers interrupt). At the same time, Back emits task.complete.

**Expected:** Interrupt takes precedence. Task complete is queued in `pending_results`. After interrupt resolves, queued result is woven.

**Key code paths:**

- `fsm/controller.py:560` `_on_user_input` from PROGRESSING -> INTERRUPT_HANDLING
- `fsm/controller.py:1063` `_on_task_complete` -- must check FrontLock and queue
- `protocols/weave_state.py` -- `get_weave_action(INTERRUPT_HANDLING)` returns QUEUE

**Setup pattern:** Build controller, advance to PROGRESSING via dispatch+tool_started. Then deliver user_input and task_complete in rapid succession. Assert: state goes to INTERRUPT_HANDLING, pending_results has 1 entry.

---

#### 0.3.2 -- Test: cancel followed by late completion then failed(cancelled)

**Scenario:** Task in COMPANIONING. User cancels. Late task.complete arrives (should be ignored). Then task.failed(reason=cancelled) arrives.

**Expected:** Late task.complete is deduped (cancelled_tasks set). task.failed transitions to DELIVERING.

**Key code paths:**

- `fsm/controller.py:1245` `_on_task_cancel` -- registers cancel, transitions to CANCELLING
- `fsm/controller.py:1063` `_on_task_complete` -- checks `self._cancel_handler.is_cancelled(task_id)` for dedup
- `fsm/controller.py:686` (test_8_2_19 pattern) -- failed(cancelled) confirms cancel

**Setup pattern:** Build controller at COMPANIONING with active task. Emit task.cancel. Emit task.complete (assert ignored). Emit task.failed(reason=cancelled). Assert: state=DELIVERING, cancelled set cleared.

---

#### 0.3.3 -- Test: suspend in incompatible state (DISPATCHING) then deferred surfacing

**Scenario:** Back emits task.suspended while FSM is in DISPATCHING (Front still processing). Suspension should be deferred. When FSM returns to LISTENING, deferred HITL surfaces.

**Expected:** task.suspended is queued/deferred during DISPATCHING. After response_final -> LISTENING, deferred HITL is surfaced.

**Key code paths:**

- `fsm/transition_table.py` -- DISPATCHING does NOT have TOPIC_TASK_SUSPENDED as a legal trigger
- `fsm/controller.py:1292` `_on_task_suspended` -- needs to handle illegal state gracefully
- FSM deferred HITL surfacing path (post-LISTENING check)

**NOTE:** This may reveal a gap -- the current transition table does not allow task.suspended from DISPATCHING. The test should verify whether the FSM correctly defers or rejects this event.

---

#### 0.3.4 -- Test: three task completions inside weave window + user sends new message

**Scenario:** FSM in LISTENING. Three task.complete events arrive within 500ms. User sends input during the weave window.

**Expected:** First task.complete triggers IMMEDIATE weave. Remaining two are batched. User input takes priority (URGENT). After Front handles user input, pending results are checked.

**Key code paths:**

- `protocols/weave_state.py:67` -- `LISTENING -> IMMEDIATE`
- `protocols/weave_batcher.py:42` -- 500ms window
- `protocols/weave_batcher.py` -- `WeaveBatcher.add_result()` starts timer, collects batch
- `fsm/controller.py:560` `_on_user_input` -- user input during weave

**Setup pattern:** Build controller at LISTENING. Emit 3 task.complete rapidly. Emit user_input during batch window. Assert: user input processed, remaining results queued for weave after.

---

#### 0.3.5 -- Test: same-turn dispatch+complete ensuring no duplicate PRESENT output

**Scenario:** Front dispatches a task AND the task completes before Front's final response.

**Expected:** `TRIGGER_SAME_TURN_COMPLETE` fires. FSM goes directly to LISTENING (skips DELIVERING/PRESENT). No duplicate presentation.

**Key code paths:**

- `fsm/transition_table.py:68` -- COMPANIONING + `same_turn.task.complete` -> LISTENING
- `fsm/controller.py:1063` `_on_task_complete` -- same-turn-complete detection logic
- The turn state tracks whether current turn already has a response pending

**Setup pattern:** Build controller. Emit user_input -> DISPATCHING. Emit task.dispatch -> COMPANIONING. Emit task.complete with same turn_id. Assert: state=LISTENING (not DELIVERING), Front invoked exactly once.

---

#### 0.3.6 -- Test: Front emits task.dispatch before final.response

**Scenario:** Front ReAct loop produces both a dispatch_task call and a text response.

**Expected:** Post-loop emission in `actors/front.py` emits: (1) cancels, (2) dispatches, (3) final.response -- in that strict order.

**Key code paths:**

- `actors/front.py` -- post-loop emission ordering (~line 6 in WB 14.2 description)
- `react/loop.py` -- `dispatched_tasks` list accumulated during loop

**Setup pattern:** Mock LLM to return both a dispatch_task tool call and text. Run front_handler. Capture bus emissions in order. Assert: task.dispatch envelope appears before final.response envelope.

---

#### 0.3.7 -- Test: Back task.resume routed to resume handler (not generic dispatch)

**Scenario:** task.resume event arrives in Back mailbox.

**Expected:** Currently this is a known gap (WB 14.4.A). The test should verify current behavior (resume goes to generic `back_handler`) and document that it is wrong. This test becomes the regression anchor for M3 issue 3.1.2.

**Key code paths:**

- `actors/back.py:343` `back_handler` -- currently handles all back mailbox events
- `actors/back.py` -- `back_resume_handler` exists but is not wired
- Coordinator consumer (`demo/coordinator.py`) or `kernel/bootstrap.py` -- consumer routing

**Setup pattern:** Emit task.resume event to back mailbox. Verify which handler is invoked. Assert: (currently) back_handler is called (documenting the gap). After M3 fix: back_resume_handler should be called.

---

#### 0.3.8 -- Test: cancel during long back execution yields failed(cancelled)

**Scenario:** Back is mid-ReAct loop. Cancel signal arrives.

**Expected:** Cancellation check in react loop (`react/loop.py:250`) detects cancel and returns `ReactResult(status="cancelled")`. Back emits task.failed(reason=cancelled).

**Key code paths:**

- `react/loop.py:249-251` -- cancellation check at top of each iteration
- `react/loop.py:197` -- `cancellation_check` callback parameter
- `actors/back.py` -- how cancel state is passed to react loop

**NOTE:** WB 14.4.B identified that runtime does not consistently pass `fsm_state` into `back_handler`. This test should verify whether the cancellation_check callback actually receives cancel signals from FSM.

**Setup pattern:** Mock cancellation_check to return True after N iterations. Run react_loop. Assert: result.status == "cancelled".

---

#### 0.3.9 -- Test: HITL_RESOLVE emits exactly one resume with valid schema

**Scenario:** Front in HITL_RESOLVE mode processes user's response to a HITL request.

**Expected:** Front emits exactly one task.resume event with valid resolution payload (task_id, resume_token, resolution data).

**Key code paths:**

- `actors/front.py` -- HITL_RESOLVE mode handler, auto-emits resume
- `protocols/hitl.py` -- HILResponse schema
- `bus/builders.py` -- task.resume envelope builder

**Setup pattern:** Set up Front with HITL_RESOLVE mode context (pending HITL request, user response). Run front_handler. Capture bus emissions. Assert: exactly 1 task.resume event, valid payload.

---

#### 0.3.10 -- Test: Front degenerate response recovery emits final response exactly once

**Scenario:** LLM returns empty/degenerate response. Front fallback activates.

**Expected:** Fallback text is used. Exactly one final.response is emitted (not zero, not two).

**Key code paths:**

- `react/loop.py` -- degenerate response detection and fallback
- `config/defaults.yaml:339` -- `front_degenerate_fallback: "Let me think about that for a moment."`
- `actors/front.py` -- post-loop emit of final.response

**Setup pattern:** Mock LLM to return empty response. Run react_loop for Front. Assert: result.status=="complete", result.text==fallback text. Run front_handler. Assert: exactly 1 final.response emitted.

---

#### 0.3.11 -- Test: Back text-without-tools reaches submit_result or budget exhaustion

**Scenario:** Back LLM returns plain text without calling submit_result.

**Expected:** Text is treated as non-terminal for Back. Loop continues. Eventually reaches submit_result call or budget exhaustion.

**Key code paths:**

- `react/loop.py` -- Back termination requires submit_result tool call; plain text is non-terminal
- Last-iteration behavior: Back adds explicit nudge to call submit_result
- `config/defaults.yaml:335` -- `default_back_max_iterations: 16`

**Setup pattern:** Mock LLM to return text-only responses (no tool calls). Run react_loop for Back with max_iterations=3. Assert: result.status=="budget_exhausted" (not "complete").

---

#### 0.3.12 -- Test: parallel tool execution does not reorder side-effect tools

**Scenario:** LLM returns multiple tool calls in one iteration including side-effect tools.

**Current state:** `react/loop.py:497-508` executes all non-terminal tools via `asyncio.gather` in parallel. `task/parallel_safety.py:6` says "POC react_loop() processes tools sequentially" -- this is **stale documentation**.

**Expected behavior to verify:** All tools execute via gather. Order of results in `paired_results` matches order of input tool calls.

**Key code paths:**

- `react/loop.py:508` -- `await asyncio.gather(*[_exec(tc) for tc in non_terminal])`
- `task/parallel_safety.py:6` -- stale claim of sequential execution
- `config/defaults.yaml:393-407` -- parallel_safety tool groups

**Setup pattern:** Mock 3 tool calls (1 read + 1 write + 1 action). Run through react loop iteration. Assert: all 3 executed, results paired correctly with original tool calls.

**Additional action:** Fix `task/parallel_safety.py:6` docstring to reflect actual parallel behavior.

**Files to touch:** `poc/k1_poc/task/parallel_safety.py` (line 6 -- fix stale docstring).

---

#### 0.3.13 -- Test: validator rejection path never executes disallowed tool names

**Scenario:** LLM attempts to call a tool not in the current mode's allowlist.

**Expected:** `LLMOutputValidator` rejects the tool call before execution. Tool is never invoked.

**Key code paths:**

- `react/loop.py` -- validation hook before tool execution
- `prompt/mode.py:78-112` -- `MODE_TOOL_ALLOWLISTS` per PromptMode
- Tools dispatcher validation

**Setup pattern:** Set up Front in WEAVE mode (allowlist: `update_beliefs`, `update_narrative`). Mock LLM to call `dispatch_task` (not in allowlist). Run react iteration. Assert: dispatch_task is NOT executed, validator rejection logged.

---

#### 0.3.14 -- Test: bus subscription routing invariant (FSM-routed topics disjoint from FRONT_SUBSCRIPTIONS)

**Scenario:** Validate that `FRONT_SUBSCRIPTIONS` and `FSM_ROUTED_TOPICS` are disjoint. If a topic appears in both, the system creates duplicate delivery.

**Expected:** `FRONT_SUBSCRIPTIONS.isdisjoint(FSM_ROUTED_TOPICS)` is True. `BACK_SUBSCRIPTIONS.isdisjoint(FRONT_SUBSCRIPTIONS)` is True (no topic routed to both actors via subscriptions).

**Key code paths:**

- `bus/topics.py` -- `FRONT_SUBSCRIPTIONS`, `BACK_SUBSCRIPTIONS`, `FSM_ROUTED_TOPICS` (new in 0.1.5)
- `bus/topics.py:162-178` -- critical comment explaining why FRONT_SUBSCRIPTIONS is only 4 topics
- `fsm/transition_table.py` -- the topic-to-handler mapping that defines FSM routing

**Setup pattern:** Import all three sets. Assert disjointness. Also verify `ALL_TOPICS == FRONT_SUBSCRIPTIONS | BACK_SUBSCRIPTIONS | FSM_ROUTED_TOPICS | RESPONSE_TOPICS | {relaxed topics}` (complete coverage, no orphan topics).

---

#### 0.3.15 -- Test: builder priority matches _TOPIC_PRIORITY mapping

**Scenario:** Verify that the hardcoded `Priority` in each of the 28 builder functions matches the `_TOPIC_PRIORITY` mapping in `bus/topics.py`.

**Problem:** Two independent priority sources exist:

1. `bus/builders.py` -- each builder function has a hardcoded `Priority` enum value.
2. `bus/topics.py:_TOPIC_PRIORITY` dict -- maps topic string to priority int. `get_priority()` defaults to INTERACTIVE (2).

If a builder's priority diverges from `_TOPIC_PRIORITY`, mailbox WFQ scheduling and `URGENT_TOPICS` classification become inconsistent.

**Current state:** Manual audit confirms all 28 builders match `_TOPIC_PRIORITY`. But this is not enforced by any test.

**Key code paths:**

- `bus/builders.py` -- all 28 `build_*` functions and the `BUILDERS` registry dict
- `bus/topics.py:_TOPIC_PRIORITY` -- priority mapping
- `k1/bus/impl/local_mailbox.py` -- WFQ uses envelope.priority for sub-queue selection

**Setup pattern:** Iterate over `BUILDERS` dict. For each (topic, builder_fn): build an envelope, extract its `.priority.value`. Compare with `get_priority(topic)`. Assert all match.

---

#### 0.3.16 -- Test: topic constant deduplication (bus/topics.py vs task/topics.py)

**Scenario:** Verify that `task/topics.py` constants resolve to the same string values as `bus/topics.py` constants. This is a regression guard for issue 0.1.4.

**Expected:** For each duplicated constant (10 total), `bus.topics.TOPIC_X == task.topics.X`.

**Key code paths:**

- `bus/topics.py` -- 28 TOPIC_* constants (authoritative source)
- `task/topics.py` -- 10 constants with bare names (should be re-exports after 0.1.4)

**Setup pattern:** Import both modules. For each constant name in `ALL_TASK_TOPICS`, verify the value matches the corresponding `TOPIC_*` constant in `bus/topics.py`. After 0.1.4 fix, they should be the same objects (identity check via `is`).

---

#### 0.3.17 -- Test: bus envelope stamping and causal ordering

**Scenario:** Publish envelopes with parent_id chain and verify TimingChain delivers in causal order.

**Expected:** Child envelope with `parent_id=X` is not delivered until envelope X is delivered. Sequence gaps are buffered. Timeout safety net releases after 5000ms.

**Key code paths:**

- `k1/bus/impl/local_bus.py` -- `_SequenceGenerator`, `_EnvelopeIdGenerator`, stamp at publish
- `k1/bus/timing/timing_chain.py` -- `CausalTracker`, `GapBuffer`, timeout release
- `bus/setup.py:create_poc_bus()` -- wires TimingChain with `gap_timeout_ms` from config

**Setup pattern:**

1. `bus = create_poc_bus(capture=True)` -- enable capture mode for assertion.
2. Publish parent envelope P (parent_id=0). Publish child envelope C (parent_id=P.envelope_id). Verify C is delivered AFTER P.
3. Publish envelopes with sequence gap (seq 1, seq 3). Verify seq 3 is buffered until seq 2 arrives or timeout fires.
4. Verify `TimingStats` counters match expectations (buffered_causal, delivered_immediate, etc.).

---

## M1: Canonical Event Schemas & Ledger Foundation

**Goal:** Define V3 event contracts and build the append-only conversation
ledger that becomes the source of truth for all session activity.

**Gate:** All 16 canonical event types have finalized schemas with required
metadata. Ledger writer persists events. Projection reader materializes
session state from event stream. Round-trip replay test passes.

**Pre-requisite:** M0 complete (timeout/limit unification, conformance tests green).

**Key codebase context for this milestone:**

| Component | Current Location | Current State |
|-----------|-----------------|---------------|
| K1 Envelope | `k1/bus/envelope/envelope.py:135` | Frozen dataclass. Has `topic`, `priority`, `envelope_id`, `sequence`, `cognitive_trace_id`, `session_id`, `request_id`, `parent_id`, `created_ns`, `payload`, `ttl_ms`, `payload_format`. |
| Bus builders | `poc/k1_poc/bus/builders.py` | 28 builder functions. Payloads are `dict[str,Any]` -- no schema validation, no required metadata enforcement. `_build()` helper serializes via `_serialize()` (JSON bytes). `BUILDERS` registry maps topic -> builder fn. |
| Bus topics | `poc/k1_poc/bus/topics.py` | 28 topic constants, 8 namespaces, `FRONT_SUBSCRIPTIONS` (4), `BACK_SUBSCRIPTIONS` (7), `URGENT_TOPICS` (6), `_TOPIC_PRIORITY` dict, `get_priority()` utility. `FSM_ROUTED_TOPICS` set after M0 0.1.5. |
| Bus setup | `poc/k1_poc/bus/setup.py` | Factory functions: `create_poc_bus(capture)` -> `BusFactory.create_local_ordered()`, `create_poc_router()` -> `BusFactory.create_mailbox_router()`, `register_poc_actors()` wires front_half + back_half with MailboxConfig(capacity, priority_wfq). |
| Bus factory | `k1/bus/factory.py` | `BusFactory` with `create_local()`, `create_local_ordered()`, `create_for_testing()`. Wires TimingChain for ordered mode. Backend selection: auto/rust/python. |
| Bus timing | `k1/bus/timing/timing_chain.py` | CausalTracker (parent_id ordering), GapBuffer (sequence gap buffering), STRICT/RELAXED/BEST_EFFORT modes. Timeout 5000ms (configurable). |
| Timing defaults | `k1/bus/timing/defaults.py` | DEFAULT_RULES: STRICT for k1.capability/orchestration/planner/hil/response/session/agent/internal/tool. RELAXED for k1.affect/constraint/proactive/workflow. BEST_EFFORT for k1.k0.sse/k1.fabric.learning. Default=RELAXED. |
| Bus ports | `k1/bus/ports/bus.py`, `ports/mailbox.py` | `IBus` Protocol (publish/subscribe/unsubscribe, fire-and-forget). `IMailbox`/`IMailboxRouter` (at-least-once, bounded queue, WFQ priority, BackpressureError). |
| Bus impl | `k1/bus/impl/local_bus.py` | Per-topic monotonic sequence, global monotonic envelope_id. RWLock concurrency. Middleware chain. CaptureMode for testing. |
| Bus mailbox | `k1/bus/impl/local_mailbox.py` | 4 priority sub-queues (URGENT/REALTIME/INTERACTIVE/BACKGROUND). V1 = strict priority. BackpressureError when capacity exceeded. |
| Bus middleware | `k1/bus/middleware/` | Middleware Protocol (`process(Envelope) -> Envelope or None`). Chain: TracingMiddleware (OpenTelemetry) -> MetricsMiddleware (Prometheus) -> TopicValidationMiddleware (SOFT -- log unknown topics, never drop). |
| Session adapter | `k1/bus/adapters/session_adapter.py` | SessionBusAdapter bridges IEventPort ABC to IBus. Maps `event_type` -> `"k1.session.{event_type}"` topic. Pattern for domain-event-to-bus bridging. |
| Fabric adapter | `k1/bus/adapters/fabric_adapter.py` | FabricBusAdapter bridges IEventPort(Dict) + IDeltaBusPort to IBus(bytes). JSON serialization. Delta topics: `k1.agent.{agent_id}.delta.v1`. |
| Cancel events | `poc/k1_poc/protocols/cancel_events.py` | `TaskCancelEvent` (line 33), `TaskFailedCancelledEvent` (line 81). Flat dataclasses with `to_payload()`/`from_payload()`. No common base class. |
| Suspension events | `poc/k1_poc/protocols/suspension_events.py` | `TaskSuspendedEvent` (line 23), `TaskResumeEvent` (line 72). Same flat pattern. No common base. |
| HITL events | `poc/k1_poc/protocols/hitl.py` | `HILRequest` (line 108), `HILResponse` (line ~210). Richer schema with `to_persistence()`. No common base. |
| HITL timeout | `poc/k1_poc/protocols/hitl_persistence.py` | `HILTimeoutEvent` (line 266). Yet another standalone dataclass. |
| Weave events | `poc/k1_poc/protocols/weave_batcher.py` | `WeaveResult` (line 46), `PendingResult` in `weave_state.py:101`. No common base. |
| SS events | `poc/k1_poc/sessionstate/events.py` | `BaseEvent` (line 80) -- closest to V3 canonical. Has `event_id`, `event_type`, `session_id`, `cognitive_trace_id`, `timestamp_ms`. 8 SS event types. |
| History | `poc/k1_poc/fsm/controller.py:174` | `TypedHistoryEntry` -- in-memory only, no event_id, no correlation chain. FSM sole writer via `_write_history()` (line 526). |
| FSM turn state | `poc/k1_poc/fsm/turn_state.py:31` | `FSMTurnState` -- ephemeral in-memory deque for `pending_results`. Not persisted. |
| Task state | `poc/k1_poc/protocols/hitl_persistence.py:69` | `TaskStateEntry` -- per-task persistence model. Has `pending_hil`, `hil_suspensions_count`, lifecycle methods. |
| Ledger | -- | **Does not exist.** No append-only log, no event store, no replay infrastructure. |

**Bus layer dependency map for M1 (50+ import sites across POC):**

| Consumer Module | Bus Imports | Why M1 Cares |
|----------------|-------------|--------------|
| `fsm/controller.py` | `Envelope`, `IBus`, `IMailboxRouter`, 12 builders, 10 topics | Every FSM event handler publishes via builders. Ledger integration (1.2.3) must intercept BEFORE these publish calls. |
| `actors/front.py` | `Envelope`, `IBus`, 8 builders, `FRONT_SUBSCRIPTIONS` | Front uses builders for emit ordering. Canonical events (1.1.6) change builder signatures. |
| `actors/back.py` | `Envelope`, `IBus`, 6 builders | Back emits task.complete/failed/suspended. Canonical events change payload shape. |
| `kernel/bootstrap.py` | 8 builders, `Envelope`, `Priority`, `PayloadFormat` | Bootstrap creates Envelope inline for edge cases. Must adopt canonical events. |
| `task/envelope_bridge.py` | `TASK_COMPLETE`, `TASK_DISPATCH`, `TASK_FAILED` from task/topics.py | Uses duplicate topic module (fixed in M0 0.1.4). Envelope-to-event bridge is exactly where canonical deserialization belongs. |
| `tools/dispatcher.py` | `build_tool_completed`, `build_tool_started` | Tool events need canonical metadata for ledger tracing. |
| `protocols/cancel_events.py` | `TASK_FAILED` from task/topics.py | Cancel event serialization must adopt canonical base. |
| `fsm/transition_table.py` | 10 topics from bus/topics.py | Transition table references topic strings for handler routing. New V3 topics need entries here. |
| `demo/spinner.py`, `demo/output_channel.py`, `demo/web/app.py` | `Envelope`, `IBus`, various topics | Demo layer consumes bus events. Must handle both legacy and canonical payloads during migration. |

---

### E1.1 -- V3 Event Schema Definition

Source: WB 4, 12.2.E, 12.4.2

#### 1.1.1 -- Define canonical event envelope metadata

**Problem:** The K1 `Envelope` (bus transport layer) carries routing metadata but NOT event-level metadata. The payload is opaque bytes. V3 needs every event payload to carry canonical metadata fields for correlation, causation tracking, and schema versioning.

**Current K1 Envelope fields** (`k1/bus/envelope/envelope.py:135-176`):

```
topic, priority, envelope_id, sequence, cognitive_trace_id,
session_id, request_id, parent_id, created_ns, payload,
ttl_ms, payload_format
```

**V3 canonical event metadata** (from WB 4) -- fields that go INSIDE the payload:

```
event_id:              UUID, unique per event (NOT envelope_id -- envelopes are transport, events are domain)
event_type:            Canonical type string (e.g., "task.completed")
session_id:            Session scope (can be copied from envelope)
correlation_id:        Request-level correlation (maps to envelope.cognitive_trace_id)
causation_id:          ID of the event that CAUSED this event
parent_event_id:       ID of the logical parent event (not envelope parent)
task_id:               Task scope (null for conversation-level events)
actor:                 Who emitted this event ("front", "back", "fsm", "arbiter")
ts_utc:                Wall-clock UTC timestamp (ISO 8601)
priority:              Event priority (can differ from envelope priority)
payload_schema_version: Schema version string (e.g., "1.0.0")
```

**Gap analysis (what Envelope has vs what V3 needs in payload):**

| V3 Field | Envelope Equivalent | In Payload Today? | Action |
|----------|--------------------|--------------------|--------|
| event_id | -- | No | Add to payload schema |
| event_type | topic (implicit) | No | Add explicit field |
| session_id | session_id | Sometimes | Require in payload |
| correlation_id | cognitive_trace_id | No | Map from envelope |
| causation_id | -- | No | Add to payload schema |
| parent_event_id | parent_id | No | Add to payload schema |
| task_id | -- | Inconsistent | Require in payload |
| actor | -- | No | Add to payload schema |
| ts_utc | created_ns (monotonic) | No | Add wall-clock UTC |
| payload_schema_version | -- | No | Add to payload schema |

**Action:**

1. Create `poc/k1_poc/events/base.py` with a `CanonicalEventMeta` dataclass containing all 11 V3 metadata fields.
2. Create `poc/k1_poc/events/__init__.py` exporting the base.
3. Design pattern: every V3 event payload extends `CanonicalEventMeta`. The `to_payload()` method produces a dict that always includes these fields. The `from_payload()` class method validates them.
4. Add a `validate_canonical_metadata(payload: dict) -> bool` function that checks all required fields are present.
5. Decide: should `event_id` be auto-generated (UUID4) at event creation time? (Recommend: yes, with `uuid.uuid4()` default.)
6. Decide: should `ts_utc` be auto-populated from `datetime.utcnow().isoformat()`? (Recommend: yes.)

**Reference:** `poc/k1_poc/sessionstate/events.py:80` (`BaseEvent`) is the closest existing pattern. It already has `event_id`, `event_type`, `session_id`, `cognitive_trace_id`, `timestamp_ms`. Extend this pattern to cover all 11 fields.

**Files to create:**

- `poc/k1_poc/events/__init__.py`
- `poc/k1_poc/events/base.py`

**Files to reference (pattern source):**

- `poc/k1_poc/sessionstate/events.py:80-100` (BaseEvent pattern)
- `k1/bus/envelope/envelope.py:135-176` (Envelope field names for mapping)

---

#### 1.1.2 -- Define conversation event schemas

**V3 canonical conversation events (3 types):**

1. `conversation.user_input.received` -- User sent a message.
2. `conversation.intent.arbitrated` -- Arbiter classified intent (M4 dependency, but schema defined now).
3. `conversation.dead_lettered` -- Event routed to dead-letter stream (M2 dependency, but schema defined now).

**Current state:** No dedicated conversation event dataclasses exist. User input arrives as a bus envelope on topic `k1.session.user.input.v1` with ad-hoc payload `{"text": ..., "session_id": ...}`. The payload shape is not validated.

**For `user_input.received`:**

Current payload in builders (`bus/builders.py:101`):

```python
build_user_input(payload={"text": "...", "session_id": "s1"}, parent_id=0)
```

V3 payload must include: all canonical metadata + `text`, `input_type` (text/voice/gesture), `device_id` (for multi-device, M6), `raw_input` (original form).

**For `intent.arbitrated`:**

Does not exist yet. This is the output of the Conversation Arbiter (M4). Schema should include: all canonical metadata + `intent_class` (cancel/modify_inflight/parallel_new/defer), `confidence`, `target_task_id` (if modifying existing), `routing_metadata`.

**For `dead_lettered`:**

Does not exist yet. This is the output of the dead-letter pipeline (M2). Schema should include: all canonical metadata + `original_event` (serialized), `reason` (invalid_transition/orphan/expired), `fsm_state_at_rejection`.

**Action:**

1. Create `poc/k1_poc/events/conversation.py` with three dataclasses extending `CanonicalEventMeta`:
   - `UserInputReceived`
   - `IntentArbitrated` (schema only; implementation in M4)
   - `DeadLettered` (schema only; implementation in M2)
2. Each class has `to_payload()`, `from_payload()`, and type-specific fields.

**Files to create:**

- `poc/k1_poc/events/conversation.py`

---

#### 1.1.3 -- Define task lifecycle event schemas

**V3 canonical task events (6 types):**

1. `task.created` -- Task created by arbiter/dispatcher.
2. `task.leased` -- Task claimed by a Back worker (BackPool model, M5).
3. `task.progressed` -- Incremental progress update from Back.
4. `task.completed` -- Task finished successfully.
5. `task.failed` -- Task failed (error, timeout, cancel-reason).
6. `task.cancelled` -- Task explicitly cancelled.

**Current state (fragmented dataclasses):**

| V3 Event | Current Dataclass | Location | Fields |
|----------|------------------|----------|--------|
| task.created | -- | Does not exist | -- |
| task.leased | -- | Does not exist | -- |
| task.progressed | -- | Does not exist (progress_pct is in TaskStateEntry) | -- |
| task.completed | -- | No dataclass; payload is ad-hoc dict in builders | -- |
| task.failed | `TaskFailedCancelledEvent` | `cancel_events.py:81` | task_id, completed_before_cancel, tool_calls_completed, error_message |
| task.cancelled | `TaskCancelEvent` | `cancel_events.py:33` | task_id, reason, priority, new_task_id |

**Gap:** Only cancel/failed have dataclasses, and they lack canonical metadata. Created, leased, progressed, and completed have no dataclass -- payloads are built ad-hoc in `bus/builders.py`.

**How task.complete payload is built today** (`fsm/controller.py` callers of `build_task_complete`):
The payload is assembled inline by the caller -- typically `{"task_id": ..., "result": ..., "action": ...}`. No validation.

**Action:**

1. Create `poc/k1_poc/events/task.py` with six dataclasses extending `CanonicalEventMeta`:
   - `TaskCreated` -- task_id, action, depends_on, priority, dispatch_context
   - `TaskLeased` -- task_id, worker_id, lease_expires_at (schema only; M5 dependency)
   - `TaskProgressed` -- task_id, progress_pct, status_message, findings_so_far
   - `TaskCompleted` -- task_id, result_data, action, tool_calls_count, elapsed_ms
   - `TaskFailed` -- task_id, reason, error_code, completed_before_cancel, tool_calls_completed
   - `TaskCancelled` -- task_id, reason, new_task_id, priority
2. These REPLACE the existing `TaskCancelEvent` and `TaskFailedCancelledEvent` in `cancel_events.py`.
3. Keep `cancel_events.py` for backward compat but mark as deprecated, importing from `events/task.py`.

**Files to create:**

- `poc/k1_poc/events/task.py`

**Files to deprecate:**

- `poc/k1_poc/protocols/cancel_events.py` (mark with deprecation notice, re-export from events/task.py)

---

#### 1.1.4 -- Define HITL event schemas

**V3 canonical HITL events (4 types):**

1. `task.hil.requested` -- Back requests human input.
2. `task.hil.resolved` -- User provided response.
3. `task.suspended` -- Task suspended pending HITL.
4. `task.resumed` -- Task resumed after HITL resolution.

**Current state (fragmented dataclasses):**

| V3 Event | Current Dataclass | Location | Notes |
|----------|------------------|----------|-------|
| hil.requested | `HILRequest` | `hitl.py:108` | Rich schema (task_id, hil_type, question, options, context, side_effects, safety_band, timeout_ms, max_rounds). Has `to_persistence()`. |
| hil.resolved | `HILResponse` exists | `hitl.py:~210` | Has task_id, resolution, resolution_type. |
| task.suspended | `TaskSuspendedEvent` | `suspension_events.py:23` | task_id, suspension_type, question, options, suspension_count. Overlaps with HILRequest fields. |
| task.resumed | `TaskResumeEvent` | `suspension_events.py:72` | task_id, resolution, resolution_type. Overlaps with HILResponse. |

**Key problem (WB 12.2.E):** `TaskSuspendedEvent` and `HILRequest` carry overlapping data. `TaskResumeEvent` and `HILResponse` carry overlapping data. These are conceptually the same events at different protocol layers but with different shapes.

**V3 decision:** `task.suspended` is the FSM lifecycle event (carries canonical metadata + `suspension_context` referencing the HITL request). `hil.requested` is the protocol-detail event (carries the full HILRequest payload). One CAUSES the other: `hil.requested.event_id` is the `causation_id` of `task.suspended`.

**Action:**

1. Create `poc/k1_poc/events/hitl.py` with four dataclasses extending `CanonicalEventMeta`:
   - `HILRequested` -- extends canonical meta + all HILRequest fields (hil_type, question, options, context, side_effects, safety_band, timeout_s, max_rounds)
   - `HILResolved` -- extends canonical meta + resolution, resolution_type, elapsed_s
   - `TaskSuspended` -- extends canonical meta + suspension_type, hil_request_event_id (causation link), suspension_count
   - `TaskResumed` -- extends canonical meta + hil_resolved_event_id (causation link), resume_instruction
2. Map current `HILRequest.to_payload()` fields into `HILRequested` schema.
3. Map current `TaskSuspendedEvent.to_payload()` fields into `TaskSuspended` schema.

**Files to create:**

- `poc/k1_poc/events/hitl.py`

**Files to deprecate (with re-exports):**

- `poc/k1_poc/protocols/suspension_events.py`
- `poc/k1_poc/protocols/hitl.py` (the `HILRequest`/`HILResponse` dataclasses, not the module)

---

#### 1.1.5 -- Define weave event schemas

**V3 canonical weave events (3 types):**

1. `conversation.weave.candidate` -- A task result is available for weaving.
2. `conversation.weave.decided` -- Weave policy made a decision (immediate/batch/defer).
3. `conversation.weave.emitted` -- Weave content was delivered to user.

**Current state:**

| V3 Event | Current Dataclass | Location | Notes |
|----------|------------------|----------|-------|
| weave.candidate | `WeaveResult` | `weave_batcher.py:46` | task_id, task_description, result_data, completed_at_ns. |
| weave.decided | -- | Does not exist | Weave decision is implicit in `get_weave_action()` return value in `weave_state.py:87`. |
| weave.emitted | -- | Does not exist | Weave emission is implicit in FSM `_on_response_final` path. |

Also: `PendingResult` in `weave_state.py:101` is nearly identical to `WeaveResult` (same fields + `queued_at_ns` instead of `completed_at_ns`).

**Action:**

1. Create `poc/k1_poc/events/weave.py` with three dataclasses extending `CanonicalEventMeta`:
   - `WeaveCandidateArrived` -- task_id, task_description, result_data, completed_at_ns
   - `WeaveDecisionMade` -- candidate_event_id (causation), decision (WeaveAction value), reason, fsm_state, batch_window_ms
   - `WeaveEmitted` -- candidate_event_ids (list of woven candidates), response_text_preview, delivery_mode
2. `WeaveResult` and `PendingResult` continue to exist as internal runtime structs but are populated FROM these canonical events.

**Files to create:**

- `poc/k1_poc/events/weave.py`

**Files to keep (internal runtime, not deprecated):**

- `poc/k1_poc/protocols/weave_batcher.py` (WeaveResult stays as runtime struct)
- `poc/k1_poc/protocols/weave_state.py` (PendingResult stays as runtime struct)

---

#### 1.1.6 -- Align existing event dataclasses to canonical envelope + migrate bus builders

**Problem (WB 12.2.E):** The six existing event dataclasses across `cancel_events.py`, `suspension_events.py`, `hitl.py`, and `weave_batcher.py` all have:

- `to_payload() -> dict` and `from_payload(dict) -> Self`
- No common base class
- No canonical metadata fields (event_id, correlation_id, causation_id, actor, ts_utc, payload_schema_version)
- Overlapping fields between suspension and HITL events

The 28 bus builders in `bus/builders.py` are the serialization gateway for ALL bus events. Every builder:

- Accepts `payload: dict[str, Any]` with ZERO validation
- Calls `_serialize(payload)` (JSON bytes via `json.dumps`)
- Calls `_build(topic, priority, payload, parent_id)` which constructs an Envelope
- Has a hardcoded `Priority` enum value per function (verified consistent with `_TOPIC_PRIORITY` in M0 0.3.15)

The `BUILDERS` registry dict maps all 28 topics to their builder function. This registry is the natural place to also register the expected canonical event type per topic.

**Action (migration strategy):**

1. After 1.1.1-1.1.5 create the new `events/` package with canonical schemas:
   - Add `from_legacy(old_event) -> CanonicalEvent` class methods on each new event class.
   - Add `to_legacy() -> OldEvent` methods for backward compatibility during migration.
2. In `bus/builders.py`, update the core infrastructure:
   - Update `_serialize()` (line 77) to handle both `dict[str, Any]` and `CanonicalEventMeta` subclass. When given a canonical event, call `event.to_payload()` then serialize. When given a raw dict, serialize directly with deprecation log.
   - Update `_build()` (line 84) to optionally accept a `CanonicalEventMeta` and call `validate_canonical_metadata()` before serialization.
   - Each of the 28 builder functions keeps its signature `(payload: dict[str, Any], parent_id: int = 0)` but gains an overload accepting `(event: CanonicalEventMeta, parent_id: int = 0)`. Use `@overload` typing or a union type.
3. Extend the `BUILDERS` registry from `dict[str, Callable]` to `dict[str, BuilderEntry]` where `BuilderEntry` is a `NamedTuple(builder_fn, canonical_type: type[CanonicalEventMeta] | None, priority: Priority)`. This enables:
   - Runtime validation: given a topic, look up the expected canonical type.
   - Priority consistency: single source of truth (eliminates the dual builder/`_TOPIC_PRIORITY` maintenance issue from M0 0.3.15).
   - Event deserialization: given a topic from an incoming envelope, look up the canonical type for `from_payload()`.
4. Create `poc/k1_poc/events/registry.py` that maps `event_type` string to its canonical dataclass for deserialization. This is separate from `BUILDERS` because event_type (domain concept) != topic (transport concept). One topic can carry multiple event types.
5. Add a `poc/k1_poc/bus/deserialize.py` helper: given an Envelope, look up the canonical type from the registry, deserialize payload bytes -> dict -> canonical event. This is the inverse of the builder path.

**Files to modify:**

- `poc/k1_poc/bus/builders.py` (lines 77-87 `_serialize` + `_build`, all 28 builders, `BUILDERS` registry)
- `poc/k1_poc/bus/__init__.py` (export new `BuilderEntry`, `deserialize_envelope`)

**Files to create:**

- `poc/k1_poc/events/registry.py`
- `poc/k1_poc/bus/deserialize.py`

**Migration timeline:** Builders accept both old and new format. Full migration happens incrementally in M2-M5 as each subsystem adopts canonical events.

**Bus import site impact (50+ consumers):** During migration, ALL existing call sites that use `build_*()` with dict payloads continue to work. The deprecation warning helps track migration progress. Key high-traffic call sites:

- `fsm/controller.py` -- 12 builder imports, multiple emit paths
- `actors/front.py` -- 8 builder imports, post-loop emission ordering
- `actors/back.py` -- 6 builder imports (task_complete, task_failed, task_suspended, etc.)
- `kernel/bootstrap.py` -- 8 builder imports, inline Envelope construction for edge cases
- `tools/dispatcher.py` -- 2 builder imports (tool_started, tool_completed)

---

#### 1.1.7 -- Register V3 topic prefixes in timing defaults

**Problem:** `k1/bus/timing/defaults.py` maps topic prefixes to `DeliveryMode` (STRICT/RELAXED/BEST_EFFORT). If V3 introduces new topic prefixes (e.g., `k1.ledger.*`, `k1.arbiter.*`), they default to RELAXED (the catch-all default).

**Current DEFAULT_RULES** (`k1/bus/timing/defaults.py`):

| Prefix | Mode |
|--------|------|
| `k1.capability` | STRICT |
| `k1.orchestration` | STRICT |
| `k1.planner` | STRICT |
| `k1.hil` | STRICT |
| `k1.response` | STRICT |
| `k1.session` | STRICT |
| `k1.agent` | STRICT |
| `k1.internal` | STRICT |
| `k1.tool` | STRICT |
| `k1.affect` | RELAXED |
| `k1.constraint` | RELAXED |
| `k1.proactive` | RELAXED |
| `k1.workflow` | RELAXED |
| `k1.k0.sse` | BEST_EFFORT |
| `k1.fabric.learning` | BEST_EFFORT |

**V3 decision needed:** For new topic namespaces:

- `k1.ledger.*` events (if ledger publishes events to bus) -- STRICT (critical data path) or RELAXED (observability only)?
- `k1.arbiter.*` events (M5 conversation arbiter) -- STRICT (routing decisions must be ordered)?
- `k1.conversation.*` events (1.1.2 conversation events) -- STRICT?

**Action:**

1. Decide on DeliveryMode for each new V3 topic prefix.
2. Add entries to `DEFAULT_RULES` in `k1/bus/timing/defaults.py`.
3. If V3 event topics reuse EXISTING prefixes (e.g., canonical `task.completed` still uses `k1.orchestration.*`), no change needed -- existing STRICT rule applies.
4. Register new topic strings in TopicValidationMiddleware's topic registry (`k1/bus/middleware/topic_validation.py`) to suppress "unknown topic" warnings.

**Files to touch:**

- `k1/bus/timing/defaults.py` (add new prefix rules)
- `k1/bus/middleware/topic_validation.py` (register new topics)

**Decision needed:** Do V3 canonical events use new topic strings or reuse existing V2 topic strings? If `task.completed` canonical event uses the same `k1.orchestration.task.complete.v1` topic, no timing default changes are needed. If it uses a new topic string like `k1.task.completed.v1`, timing defaults must be updated.

**Recommendation:** Reuse existing topic strings. The canonical event metadata lives INSIDE the payload, not in the topic. This avoids changes to `DEFAULT_RULES`, `FRONT_SUBSCRIPTIONS`, `BACK_SUBSCRIPTIONS`, `transition_table.py`, and all 50+ import sites.

---

#### 1.1.8 -- Update FRONT_SUBSCRIPTIONS and BACK_SUBSCRIPTIONS for V3 events

**Problem:** If V3 adds new event types that use NEW topic strings (not reusing existing V2 topics), the subscription sets in `bus/topics.py` must be updated. Otherwise these events would be published but never delivered to any actor.

**Current subscription sets:**

- `FRONT_SUBSCRIPTIONS` = {`TOPIC_TASK_ACCEPTED`, `TOPIC_ORCHESTRATION_DELTA`, `TOPIC_HIL_REQUEST`, `TOPIC_PLAN_READY`} -- only 4 topics (rest are FSM-routed)
- `BACK_SUBSCRIPTIONS` = {`TOPIC_USER_INPUT`, `TOPIC_TASK_DISPATCH`, `TOPIC_TASK_CANCEL`, `TOPIC_TASK_RESUME`, `TOPIC_CLARIFICATION_RESPONSE`, `TOPIC_HIL_RESPONSE`, `TOPIC_AFFECT_UPDATE`} -- 7 topics

**V3 new event types that might need subscription routing:**

| V3 Event | Likely Topic | Subscription Target | Notes |
|----------|-------------|---------------------|-------|
| `conversation.intent.arbitrated` | `k1.arbiter.intent.v1` (new?) | FSM-routed | Arbiter output goes to FSM, not direct subscription |
| `conversation.dead_lettered` | `k1.internal.dead_letter.v1` (new?) | Observability only | No actor subscription needed |
| `task.leased` | `k1.orchestration.task.leased.v1` (new?) | FSM-routed | BackPool lease event (M7) |
| `task.progressed` | `k1.orchestration.task.progressed.v1` (new?) | FSM-routed | Progress tracking |

**Action (conditional on 1.1.7 decision):**

1. If V3 reuses existing topic strings (recommended): NO changes to subscription sets. Canonical metadata is in payload, not topic.
2. If V3 uses new topic strings: add to `FRONT_SUBSCRIPTIONS`, `BACK_SUBSCRIPTIONS`, or `FSM_ROUTED_TOPICS` as appropriate. Update `ALL_TOPICS` set. Add to `transition_table.py` handler mapping.
3. Either way: add V3-specific topics to `bus/topics.py` as constants (even if aliases to existing topics, for semantic clarity).

**Files to touch (conditional):**

- `poc/k1_poc/bus/topics.py` (add new topic constants, update subscription sets)
- `poc/k1_poc/fsm/transition_table.py` (add handlers for new topics)
- `poc/k1_poc/bus/builders.py` (add builder functions for new event types, update `BUILDERS` registry)

---

### E1.2 -- Conversation Ledger Infrastructure

Source: WB 3.A, 12.2.D, 12.5.1-2

#### 1.2.1 -- Implement append-only ledger writer with idempotency keys

**Problem:** No event persistence exists in the POC. All state is in-memory:

- `controller._history` (list of `TypedHistoryEntry`) -- in-memory, lost on crash
- `FSMTurnState.pending_results` -- in-memory deque
- `TaskStateEntry` -- in-memory dict in controller
- `SuspensionManager._active` -- in-memory dict
- `CancellationHandler._cancelled_tasks` -- in-memory set

**What "conversation ledger" means (WB 3.A):**

An append-only, ordered log of all canonical events for a session. Every event is assigned a monotonic sequence number within the session. Events are immutable once written. The ledger is the source of truth; all other state is a derived projection.

**Action:**

1. Create `poc/k1_poc/ledger/__init__.py`.
2. Create `poc/k1_poc/ledger/writer.py` with class `LedgerWriter`:
   - `async append(event: CanonicalEventMeta) -> int` -- appends event, returns sequence number.
   - Idempotency: if `event.event_id` already exists, return existing sequence (no duplicate write).
   - Storage backend: start with in-memory `list[dict]` + optional SQLite persistence.
   - Each entry: `{seq: int, event_id: str, event_type: str, session_id: str, payload: dict, written_at_utc: str}`.
3. Create `poc/k1_poc/ledger/store.py` with protocol `ILedgerStore`:
   - `append(entry: LedgerEntry) -> int`
   - `read(session_id: str, from_seq: int, to_seq: int | None) -> list[LedgerEntry]`
   - `read_by_type(session_id: str, event_type: str) -> list[LedgerEntry]`
   - `exists(event_id: str) -> bool` (for idempotency check)
4. Implement `InMemoryLedgerStore` for POC/testing.
5. Design for future: `SqliteLedgerStore` (production path, not M1 scope).

**Idempotency key:** `event_id` (UUID4, generated at event creation in `CanonicalEventMeta.__post_init__`).

**Files to create:**

- `poc/k1_poc/ledger/__init__.py`
- `poc/k1_poc/ledger/writer.py`
- `poc/k1_poc/ledger/store.py`

**Design reference:** `poc/k1_poc/sessionstate/events.py:80` (BaseEvent.event_id pattern).

**Bus integration design decision (CRITICAL):**

The ledger can integrate with the bus in three architectural patterns:

| Pattern | Mechanism | Pros | Cons |
|---------|-----------|------|------|
| A. Explicit append | Each mutation site calls `ledger.append()` before in-memory mutation | Fine-grained control, clear causation | Must wire ledger to 11+ mutation sites |
| B. Bus middleware | Add `LedgerMiddleware` to bus middleware chain (tracing -> metrics -> **ledger** -> topic_validation) | Captures ALL bus events automatically | Captures transport-level events, not domain events. May record events that are rejected by downstream handlers. |
| C. Hybrid | Middleware records all bus events for observability. Explicit append records canonical domain events with validated metadata. | Best of both worlds | Two write paths to maintain |

**Recommendation: Pattern C (Hybrid).** Use bus middleware for observability/replay (all envelopes logged). Use explicit `ledger.append()` at mutation points for canonical events with full metadata. The middleware captures the raw bus flow; the explicit appends capture the validated domain flow.

**Bus middleware integration path** (if Pattern B or C chosen):

- `k1/bus/middleware/__init__.py` defines `Middleware` Protocol: `process(envelope: Envelope) -> Envelope | None`. Returning `None` drops the envelope. Ledger middleware MUST return the envelope unchanged (never drop).
- Add to `BusFactory.create_local_ordered()` middleware chain or to `create_poc_bus()` in `bus/setup.py`.
- The existing middleware chain order is: TracingMiddleware -> MetricsMiddleware -> TopicValidationMiddleware. Ledger middleware should go LAST (after validation) or FIRST (to capture even invalid events).

**Backpressure consideration:** Ledger writes MUST NOT block bus publish (hot path). If using Pattern B/C, the middleware should write to a buffer that is flushed asynchronously. The bus's RWLock (readers=publish) means blocking in middleware blocks ALL concurrent publishes.

---

#### 1.2.2 -- Implement projection reader that materializes session state

**Problem:** Currently, session state is the source of truth (written directly by FSM). In V3, session state becomes a **derived projection** materialized from the ledger event stream.

**What "projection reader" means (WB 3.A):**

A function that reads events from the ledger and builds a materialized view. Different projections serve different consumers:

| Projection | Consumer | What It Produces |
|------------|----------|-----------------|
| History projection | Front LLM | `list[TypedHistoryEntry]` -- last N entries in chat format |
| Task state projection | FSM | `dict[str, TaskStateEntry]` -- current task lifecycle states |
| Pending results projection | WeaveBatcher | `deque[PendingResult]` -- queued results for weave |
| HITL state projection | HILCoordinator | Active suspensions, pending HIL requests |
| Turn metadata projection | FSM | Turn number, FrontLock state, active task IDs |

**Action:**

1. Create `poc/k1_poc/ledger/projections.py` with:
   - `project_history(events: list[LedgerEntry]) -> list[TypedHistoryEntry]` -- replays conversation events into history entries.
   - `project_task_states(events: list[LedgerEntry]) -> dict[str, TaskStateEntry]` -- replays task lifecycle events into task state map.
   - `project_pending_results(events: list[LedgerEntry]) -> deque[dict]` -- replays weave.candidate events minus weave.emitted events.
2. Each projection is a pure function: `events in -> state out`. No side effects.
3. Projections are used for:
   - Crash recovery (replay all events from ledger)
   - Debugging (materialize state at any point in time)
   - Testing (verify state by replaying known event sequences)

**Key mapping (current -> ledger-projected):**

| Current Source | Currently Written By | Ledger Event That Replaces It |
|---------------|---------------------|-------------------------------|
| `controller._history` | `_write_history()` at line 526 | `user_input.received`, `task.completed`, `hil.requested`, `weave.emitted`, etc. |
| `controller._task_states` | Direct dict mutation in event handlers | `task.created`, `task.progressed`, `task.completed`, `task.failed`, `task.cancelled` |
| `turn_state.pending_results` | `enqueue_result()` at turn_state.py:48 | `weave.candidate` (enqueue) minus `weave.emitted` (dequeue) |
| `suspension_manager._active` | `request_suspension()` | `task.suspended` (add) minus `task.resumed` (remove) |

**Files to create:**

- `poc/k1_poc/ledger/projections.py`

**Files to reference:**

- `poc/k1_poc/fsm/controller.py:174` (TypedHistoryEntry to produce)
- `poc/k1_poc/protocols/hitl_persistence.py:69` (TaskStateEntry to produce)
- `poc/k1_poc/fsm/turn_state.py:31` (FSMTurnState.pending_results shape)
- `poc/k1_poc/fsm/history_writer.py:1` (current history write patterns)

---

#### 1.2.3 -- Ensure every protocol lifecycle mutation is event-ledgered

**Problem (WB 12.2.D):** Protocol state changes happen via direct in-memory mutations:

| Protocol | Mutation | Current Code Path |
|----------|----------|-------------------|
| Cancel | Register cancel | `cancel_handler.py` -- `CancellationHandler.register_cancel()` adds to `_cancelled_tasks` set |
| Cancel | Confirm cancel | `cancel_handler.py` -- `confirm_cancelled()` removes from set |
| Suspend | Request suspension | `suspension_manager.py` -- `_active[task_id] = SuspensionRequest` |
| Suspend | Resolve suspension | `suspension_manager.py` -- `del _active[task_id]` |
| HITL | Start HITL | `hitl_coordinator.py` -- `HILCoordinator.start_round()` |
| HITL | Complete HITL | `hitl_coordinator.py` -- `complete_round()` |
| Task state | Suspend task | `hitl_persistence.py:125` -- `TaskStateEntry.suspend()` |
| Task state | Resume task | `hitl_persistence.py:142` -- `TaskStateEntry.resume()` |
| Task state | Cancel task | `hitl_persistence.py:155` -- `TaskStateEntry.cancel()` |
| Task state | Complete task | `hitl_persistence.py:165` -- `TaskStateEntry.complete()` |
| History | Write entry | `controller.py:526` -- `_write_history()` appends to list |

**Action:**

1. At each mutation point above, add a `ledger.append(canonical_event)` call BEFORE the in-memory mutation.
2. The ledger write is the commitment point. If it succeeds, the in-memory mutation proceeds. If it fails, the operation is rejected.
3. This is an incremental migration: in M1, both the ledger write and the in-memory mutation happen. In later milestones (M2+), the in-memory state becomes a cached projection rebuilt from the ledger.

**Integration points (files to modify in M1):**

- `poc/k1_poc/fsm/controller.py` -- `_write_history()` (line 526) emits canonical conversation events to ledger
- `poc/k1_poc/protocols/cancel_handler.py` -- `register_cancel()` emits `task.cancelled` to ledger
- `poc/k1_poc/protocols/suspension_manager.py` -- `request_suspension()` emits `task.suspended` to ledger
- `poc/k1_poc/protocols/hitl_coordinator.py` -- `start_round()` emits `hil.requested` to ledger, `complete_round()` emits `hil.resolved`
- `poc/k1_poc/protocols/hitl_persistence.py` -- `TaskStateEntry.suspend/resume/cancel/complete()` emit corresponding task lifecycle events

**Pattern:** Each mutation method gains an optional `ledger: LedgerWriter | None = None` parameter. If provided, event is appended before mutation. This keeps backward compatibility for tests that don't use the ledger.

**Bus interaction at each mutation point (how the bus event relates to the ledger event):**

Every mutation above is TRIGGERED by a bus event (an Envelope delivered via IBus/IMailbox). The flow is:

```
Bus delivers Envelope -> FSM handler unpacks payload -> handler calls mutation method -> ledger.append() -> in-memory mutation
```

The ledger event is the canonical domain event (with full metadata from 1.1.1). The bus Envelope is the transport wrapper. Key relationship:

- `Envelope.envelope_id` (bus-stamped monotonic) != `CanonicalEventMeta.event_id` (domain UUID4)
- `Envelope.parent_id` (causal chain for bus ordering) maps to `CanonicalEventMeta.causation_id` (domain causation)
- `Envelope.created_ns` (monotonic clock) is for bus timing; `CanonicalEventMeta.ts_utc` (wall clock) is for domain auditing
- `Envelope.sequence` (per-topic monotonic) is for bus gap detection; ledger has its own `seq` (per-session monotonic)

The FSM handler is the bridge: it receives a bus Envelope, extracts/validates the payload, constructs a canonical event (populating metadata from both the Envelope and the domain context), appends to ledger, then performs the in-memory mutation.

**Envelope-to-canonical mapping helper:** Create a utility function in `poc/k1_poc/events/base.py`:

```python
def from_envelope(envelope: Envelope, actor: str, causation_id: str | None = None) -> dict:
    """Extract canonical metadata seed from a bus Envelope.
    Returns a dict of metadata fields that can be passed to CanonicalEventMeta constructor."""
    return {
        "session_id": envelope.session_id,
        "correlation_id": envelope.cognitive_trace_id,
        "causation_id": causation_id or str(envelope.parent_id),
        "ts_utc": datetime.utcnow().isoformat(),
        "actor": actor,
    }
```

This helper ensures consistent Envelope-to-canonical mapping across all 11 mutation points.

---

#### 1.2.4 -- Replay test: reconstruct session from ledger and verify state matches runtime

**Problem (WB 9):** "Replay of ledger reconstructs session behavior accurately" is a V3 success criterion. No replay infrastructure exists.

**Test scenario:**

1. Run a multi-turn session through the FSM (user input -> dispatch -> tool_started -> tool_completed -> task_complete -> weave -> final_response). Include at least one HITL cycle (suspend -> user response -> resume -> complete).
2. Collect the runtime state at the end: `controller._history`, `controller._task_states`, `turn_state.pending_results`.
3. Take the ledger's event stream.
4. Run all projection functions on the event stream.
5. Assert: projected state matches runtime state exactly.

**Test location:** `tests/poc/test_m01_ledger_replay.py`

**Setup pattern:**

1. Create `LedgerWriter` with `InMemoryLedgerStore`.
2. Create `ConciergeController` wired with ledger.
3. Feed a scripted sequence of envelopes (user_input, task_dispatch, task_complete, task_suspended, hil_response, task_resume, task_complete, final_response).
4. After each event, verify ledger.length increments.
5. At end, call `project_history(ledger.read_all())` and compare with `controller._history`.
6. Call `project_task_states(ledger.read_all())` and compare with controller's task state map.

**Key assertion:** The projected state and runtime state must be structurally identical. Any divergence means the ledger missed an event or a projection is wrong.

**Test complexity notes:**

- Needs mock LLM (existing test infrastructure in `test_m08_fsm_controller.py` provides this)
- Needs mock bus (existing `create_poc_bus(capture=True)` in `bus/setup.py:60`)
- HITL cycle requires: `build_task_suspended` -> controller processes -> `build_hil_response` -> controller processes -> `build_task_resume`
- Weave cycle requires: `build_task_complete` while Front busy -> `pending_results` queued -> Front finishes -> weave drains

**Files to create:**

- `tests/poc/test_m01_ledger_replay.py`

**Files to reference (test patterns):**

- `tests/poc/test_m08_fsm_controller.py` (controller setup, mock bus, envelope builders)

---

### E1.3 -- Event Schema Validation Infrastructure

Source: WB 12.4.6 (validate_hitl_wiring extended)

#### 1.3.1 -- Create event schema registry and runtime validator

**Problem:** Currently, bus payloads are unvalidated `dict[str, Any]`. Any caller can pass any shape. The `to_payload()`/`from_payload()` pattern provides serialization but not validation.

**Existing bus validation infrastructure:**

The bus already has `TopicValidationMiddleware` (`k1/bus/middleware/topic_validation.py`) which validates that topic strings are registered but uses SOFT mode (log unknown topics, never drop). This validates ROUTING but not PAYLOAD SCHEMA.

V3 needs a complementary payload schema validation layer. Two integration options:

1. **In-builder validation** (recommended for M1): Add validation in `bus/builders.py:_build()` when given a canonical event. Fast, catches errors at the source. Does NOT catch events constructed outside builders (e.g., `kernel/bootstrap.py` creates Envelopes inline).
2. **Bus middleware validation** (future M2): Add `SchemaValidationMiddleware` to the middleware chain. Catches ALL events regardless of construction path. More comprehensive but adds latency to the hot publish path.

**Action:**

1. Create `poc/k1_poc/events/validator.py` with:
   - `EVENT_SCHEMA_REGISTRY: dict[str, type[CanonicalEventMeta]]` -- maps event_type string to its canonical class.
   - `validate_event(payload: dict) -> tuple[bool, list[str]]` -- validates payload has all required canonical metadata fields and type-specific fields. Returns (valid, list_of_errors).
   - `validate_event_chain(events: list[dict]) -> tuple[bool, list[str]]` -- validates causation chain integrity (every `causation_id` references an existing `event_id`).
2. Wire validator into `bus/builders.py:_build()` as an optional validation step. Control via config flag `defaults.yaml: bus.validate_canonical_events: false` (off in production, on in tests).
3. Extend `hitl_wiring.py:validate_hitl_wiring()` (existing validation function at `poc/k1_poc/protocols/hitl_wiring.py`) to also check that HITL events conform to canonical schema.
4. Register all V3 event types in `TopicValidationMiddleware`'s topic registry to suppress "unknown topic" warnings (if new topic strings are used per 1.1.7/1.1.8 decision).

**Files to create:**

- `poc/k1_poc/events/validator.py`

**Files to modify:**

- `poc/k1_poc/bus/builders.py` (add optional validation in `_build`)
- `poc/k1_poc/protocols/hitl_wiring.py` (extend validation)
- `poc/k1_poc/config/defaults.yaml` (add `bus.validate_canonical_events` flag)

---

### E1.4 -- End-to-End Wiring & System Integration

Source: Bootstrap analysis, bus/setup.py, kernel/bootstrap.py, demo/coordinator.py, fsm/controller.py

**Why this epic exists:** E1.1-E1.3 create new packages (`events/`, `ledger/`, validators, deserializer, registry) but NONE of them are wired into the running system. Without this epic, M1 produces dead code that sits next to the existing system without touching it. Every downstream milestone (M2-M12) assumes M1 artifacts are live and integrated. If this wiring is missing, M2 cannot use the ledger, M5 cannot use canonical events, and M9 cannot replay from the event store. **This is the make-or-break epic for the entire V3 plan.**

**Wiring audit -- current system initialization chain:**

```
demo/web/app.py
  -> demo/coordinator.py::K1DemoCoordinator.initialize_system()
    -> Phase 2: kernel/bootstrap.py::start_kernel()
      -> main.py::boot()
        -> bus/setup.py::create_poc_bus()         -- LocalBus + TimingChain
        -> bus/setup.py::create_poc_router()       -- LocalMailboxRouter
        -> bus/setup.py::create_poc_session_adapter() -- SessionBusAdapter
        -> bus/setup.py::register_poc_actors()     -- front_half + back_half mailboxes
      -> ConciergeController(bus, router)          -- FSM subscribes to 19 topics
      -> set_history_sink(history_section)          -- SS history write path
      -> set_session_state(ss)                      -- SS reads (scoreboard, narrative)
      -> create_front_dispatcher / create_back_dispatcher -- tool dispatchers
      -> ExperienceLayer()                          -- affect pipeline
      -> DeltaAggregator + DeltaApplicator          -- delta pipeline
      -> HILCoordinator(on_suspended, on_resume, on_timeout) -- HITL protocol
      -> set_hitl_coordinator(coordinator)          -- wires into FSM
      -> WeaveBatcher(flush_fn)                     -- weave queue
      -> set_weave_batcher(batcher)                 -- wires into FSM
      -> OrchestratorStub(fabric, state_read, delta_emit) -- task dispatch
      -> set_orchestrator(orchestrator)             -- wires into FSM
      -> subscribe_front_events(bus, route_fn)      -- front subscription routing
      -> _mailbox_consumer(runtime)                 -- poll loop
    -> Phase 3: Attach demo data to SS
    -> Phase 4: Wire output channel, IoT, enhanced consumer
    -> Phase 5: Health check
```

**M1 artifacts that must be injected into this chain:**

| New Artifact | Integration Point | What Changes |
|-------------|-------------------|-------------|
| `events/` package (16 canonical event types) | `bus/builders.py` (28 builders) | Builders must accept canonical events, not just raw dicts |
| `events/registry.py` (event_type -> class map) | `bus/deserialize.py` (new) | Incoming envelopes deserialized to typed events |
| `events/validator.py` (schema validator) | `bus/builders.py:_build()` | Optional validation on publish path |
| `ledger/writer.py` (LedgerWriter) | `kernel/bootstrap.py::start_kernel()` | Ledger must be created and injected into FSM |
| `ledger/store.py` (InMemoryLedgerStore) | `kernel/bootstrap.py::start_kernel()` | Store backend created at boot |
| `ledger/projections.py` (projection functions) | `ConciergeController` | Crash recovery path, debug tooling |
| `bus/deserialize.py` (envelope -> canonical event) | `ConciergeController._parse_payload()` | FSM handlers receive typed events instead of raw dicts |
| `CanonicalEventMeta.from_envelope()` helper | Every FSM handler that creates canonical events for ledger | Envelope metadata mapped to canonical metadata |

**What "wired" means concretely:**

1. The system boots and the ledger is alive (not just importable).
2. Bus events published through builders carry canonical metadata.
3. FSM handlers that receive envelopes can deserialize to typed events.
4. Every state mutation in the FSM appends to the ledger before mutating.
5. The demo web app works exactly as before (no regressions).
6. Tests can inject a test ledger and verify events were recorded.
7. A health check confirms ledger + canonical events are operational.

---

#### 1.4.1 -- Wire LedgerWriter into kernel bootstrap

**Problem:** `kernel/bootstrap.py::start_kernel()` creates every runtime component (bus, router, FSM, HITL coordinator, weave batcher, orchestrator, delta pipeline, experience layer) but has NO concept of a ledger. After E1.2 creates the ledger package, it is dead code unless bootstrap creates it and injects it.

**Current `start_kernel()` component creation order** (`kernel/bootstrap.py`):

```python
infra = boot(capture=cfg.capture_bus, ordered=cfg.ordered_bus)  # bus, router, adapter, mailboxes
model = _create_model(cfg)
session_state = _create_session_state(cfg)
capability_registry = _create_capability_registry()
fsm = ConciergeController(bus=bus, router=router)
# ... set_history_sink, set_session_state, dispatchers, experience, delta, hitl, weave, orchestrator
```

**Ledger must be created BEFORE the FSM** because the FSM needs it for event recording. The FSM must receive the ledger via a `set_ledger()` setter (same pattern as `set_hitl_coordinator`, `set_orchestrator`, etc.).

**Action:**

1. Add `enable_ledger: bool = True` to `KernelConfig` dataclass in `kernel/bootstrap.py`.
2. Add `ledger: Any = None` to `KernelRuntime` dataclass.
3. In `start_kernel()`, after `session_state` creation and before `ConciergeController`:

   ```python
   if cfg.enable_ledger:
       from poc.k1_poc.ledger.store import InMemoryLedgerStore
       from poc.k1_poc.ledger.writer import LedgerWriter
       store = InMemoryLedgerStore()
       ledger = LedgerWriter(store=store)
       runtime.ledger = ledger
   ```

4. After FSM creation, wire the ledger:

   ```python
   if runtime.ledger is not None:
       fsm.set_ledger(runtime.ledger)
   ```

5. In `stop_kernel()`, add ledger flush/close step before FSM teardown:

   ```python
   if runtime.ledger is not None:
       try:
           await runtime.ledger.flush()  # ensure all buffered events are persisted
       except Exception:
           logger.debug("Ledger flush failed during shutdown", exc_info=True)
   ```

**Files to modify:**

- `poc/k1_poc/kernel/bootstrap.py` (KernelConfig, KernelRuntime, start_kernel, stop_kernel)

**Dependency:** E1.2.1 (LedgerWriter exists)

---

#### 1.4.2 -- Add `set_ledger()` to ConciergeController and wire mutation points

**Problem:** `ConciergeController` has setter methods for every optional dependency (`set_orchestrator`, `set_hitl_coordinator`, `set_weave_batcher`, `set_session_state`, `set_history_sink`) but NO setter for the ledger. The 11 mutation points identified in 1.2.3 are listed but the actual `set_ledger()` method and per-handler integration does not exist.

**Current FSM handler -> mutation flow (representative example):**

```python
# _on_task_complete handler (simplified):
def _on_task_complete(self, envelope: Envelope) -> None:
    payload = _parse_payload(envelope)
    task_id = payload.get("task_id", "")
    # Direct in-memory mutation -- NO ledger write:
    self._active_task_ids.discard(task_id)
    self._write_history(TypedHistoryEntry(...))
    self._transition(ConciergeState.WEAVING, ...)
```

**V3 flow with ledger:**

```python
def _on_task_complete(self, envelope: Envelope) -> None:
    payload = _parse_payload(envelope)
    task_id = payload.get("task_id", "")
    # Create canonical event:
    event = TaskCompleted(
        task_id=task_id,
        result_data=payload.get("result", {}),
        **from_envelope(envelope, actor="fsm")
    )
    # Ledger write BEFORE mutation:
    if self._ledger is not None:
        self._ledger.append(event)
    # Then in-memory mutation (unchanged):
    self._active_task_ids.discard(task_id)
    self._write_history(TypedHistoryEntry(...))
    self._transition(ConciergeState.WEAVING, ...)
```

**Action:**

1. Add `set_ledger(self, ledger: Any) -> None` to `ConciergeController`, following the exact pattern of `set_hitl_coordinator()`:

   ```python
   def set_ledger(self, ledger: Any) -> None:
       """Attach LedgerWriter for event persistence.
       When set, FSM handlers append canonical events to the ledger
       BEFORE performing in-memory mutations."""
       self._ledger = ledger
       logger.info("ConciergeController.set_ledger: attached %s", type(ledger).__name__)
   ```

2. Add `self._ledger: Any | None = None` in `__init__`.
3. Create a private helper `_ledger_append(self, event: CanonicalEventMeta) -> None` that safely appends (catches exceptions, logs warnings, never blocks the FSM hot path):

   ```python
   def _ledger_append(self, event: Any) -> None:
       if self._ledger is None:
           return
       try:
           self._ledger.append(event)
       except Exception:
           logger.warning("Ledger append failed for event_type=%s", getattr(event, 'event_type', '?'), exc_info=True)
   ```

4. Wire `_ledger_append()` into the following handlers (the 11 mutation points from 1.2.3):

| Handler | Canonical Event | Mutation That Follows |
|---------|----------------|----------------------|
| `_on_user_input` | `UserInputReceived` | `_write_history()`, turn increment |
| `_on_task_dispatch` | `TaskCreated` | `_active_task_ids.add()`, `_task_dispatch_turns[tid] = turn` |
| `_on_task_complete` | `TaskCompleted` | `_active_task_ids.discard()`, `_write_history()` |
| `_on_task_failed` | `TaskFailed` | `_active_task_ids.discard()`, `_cancel_handler` update |
| `_on_task_cancel` | `TaskCancelled` | `_cancel_handler.register_cancel()` |
| `_on_task_suspended` | `TaskSuspended` | `_suspension_manager.request_suspension()` |
| `_on_task_resume` | `TaskResumed` | `_suspension_manager.resolve()` |
| `_on_response_final` | `WeaveEmitted` | `_write_history()`, turn completion |
| `_on_clarification_request` | `HILRequested` | HITL coordinator `start_round()` |
| `_on_clarification_response` | `HILResolved` | HITL coordinator `complete_round()` |
| `_on_weave_batch` | `WeaveDecisionMade` | Weave batcher state update |

1. Each handler constructs the canonical event using `from_envelope()` helper (1.2.3), then calls `self._ledger_append(event)`, then proceeds with existing in-memory mutation.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (`__init__`, `set_ledger`, `_ledger_append`, 11 event handlers)

**Dependency:** E1.1.1-1.1.5 (canonical event classes exist), E1.2.1 (LedgerWriter exists), 1.4.1 (bootstrap wires ledger to FSM)

---

#### 1.4.3 -- Wire canonical event deserialization into FSM payload parsing

**Problem:** Every FSM handler calls `_parse_payload(envelope) -> dict` to extract the raw dict from envelope bytes. After E1.1.6 creates `bus/deserialize.py`, the FSM COULD receive typed canonical events instead of raw dicts. But `_parse_payload` is the chokepoint -- it returns an untyped dict and every handler destructures it with `.get()` calls.

**Current flow (all 19 FSM handlers):**

```python
payload = _parse_payload(envelope)  # -> dict[str, Any]
task_id = payload.get("task_id", "")
```

**V3 flow (dual-mode during migration):**

```python
payload = _parse_payload(envelope)  # still returns dict for backward compat
canonical = _try_deserialize(envelope)  # -> CanonicalEventMeta | None (typed, or None if legacy)
# Handlers use canonical if available, fall back to raw dict
```

**Action:**

1. Add a `_try_deserialize(self, envelope: Envelope) -> Any | None` method to `ConciergeController`:

   ```python
   def _try_deserialize(self, envelope: Envelope) -> Any | None:
       """Attempt to deserialize envelope payload to a canonical event.
       Returns None if payload is legacy (no event_type field) or
       if deserialization fails."""
       try:
           from poc.k1_poc.bus.deserialize import deserialize_envelope
           return deserialize_envelope(envelope)
       except Exception:
           return None  # Legacy payload, handler uses raw dict
   ```

2. Update `_parse_payload` to also populate canonical metadata fields when detected:

   ```python
   def _parse_payload(envelope: Envelope) -> dict[str, Any]:
       # existing JSON parse...
       result = json.loads(envelope.payload)
       # If payload has canonical metadata, tag it for handler awareness:
       if "event_type" in result and "event_id" in result:
           result["_canonical"] = True
       return result
   ```

3. In M1, handlers do NOT change their dict-destructuring logic. The canonical event is only used for ledger recording (1.4.2). Full migration of handlers from dict to typed events happens incrementally in M2-M5. This is explicitly a dual-mode bridge.

**Rationale for NOT converting all handlers in M1:** 19 handlers with complex destructuring logic. Converting all at once risks regressions. M1 establishes the infrastructure. M2+ issues individually convert each handler.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (`_parse_payload`, add `_try_deserialize`)

**Dependency:** E1.1.6 (deserialize.py exists), E1.1.1 (canonical metadata fields defined)

---

#### 1.4.4 -- Wire LedgerMiddleware into bus middleware chain

**Problem:** E1.2.1 recommends Pattern C (Hybrid) for ledger integration -- bus middleware for observability, explicit appends for domain events. The bus middleware piece is designed but not wired into the actual bus middleware chain.

**Current bus middleware chain** (`k1/bus/middleware/`):

```
TracingMiddleware -> MetricsMiddleware -> TopicValidationMiddleware
```

Middleware is wired in `BusFactory.create_local_ordered()` (`k1/bus/factory.py`). The POC calls this via `bus/setup.py::create_poc_bus()`.

**Problem nuance:** The middleware chain is configured in the K1 bus layer (`k1/bus/`), not the POC layer (`poc/k1_poc/`). Adding middleware from the POC into the K1 chain requires either:

- **Option A:** Modify `BusFactory.create_local_ordered()` to accept additional middleware (clean, but changes K1 core).
- **Option B:** Add middleware after bus creation via `bus.add_middleware()` (if the API supports it).
- **Option C:** Create a `create_poc_bus()` variant that extends the middleware chain at the POC layer.

**Action:**

1. Create `poc/k1_poc/ledger/middleware.py` with class `LedgerMiddleware`:

   ```python
   class LedgerMiddleware:
       """Bus middleware that records all envelopes to the ledger for observability.
       This captures the raw bus flow. Canonical domain events are recorded
       separately via explicit ledger.append() in FSM handlers (1.4.2).
       MUST return the envelope unchanged -- never drops."""

       def __init__(self, store: ILedgerStore) -> None:
           self._store = store

       def process(self, envelope: Envelope) -> Envelope:
           # Async-safe: write to buffer, not blocking
           try:
               self._store.append_raw(envelope)
           except Exception:
               pass  # Never block the bus
           return envelope  # Always pass through
   ```

2. In `bus/setup.py::create_poc_bus()`, after creating the bus, append the ledger middleware:

   ```python
   def create_poc_bus(*, capture: bool = False, ledger_store: ILedgerStore | None = None) -> LocalBus:
       bus = BusFactory.create_local_ordered(...)
       if ledger_store is not None:
           from poc.k1_poc.ledger.middleware import LedgerMiddleware
           bus.add_middleware(LedgerMiddleware(ledger_store))
       return bus
   ```

3. In `kernel/bootstrap.py::start_kernel()`, pass the ledger store to `create_poc_bus()` if ledger is enabled. This requires creating the store BEFORE the bus (reorder initialization):

   ```python
   # New order:
   store = InMemoryLedgerStore() if cfg.enable_ledger else None
   infra = boot(capture=cfg.capture_bus, ordered=cfg.ordered_bus, ledger_store=store)
   # ... later:
   ledger = LedgerWriter(store=store) if store else None
   ```

4. Update `main.py::boot()` to accept and forward `ledger_store` parameter.

**Files to create:**

- `poc/k1_poc/ledger/middleware.py`

**Files to modify:**

- `poc/k1_poc/bus/setup.py` (accept ledger_store parameter)
- `poc/k1_poc/main.py` (forward ledger_store parameter)
- `poc/k1_poc/kernel/bootstrap.py` (reorder: create store before bus)

**Dependency:** E1.2.1 (LedgerWriter/ILedgerStore exist), K1 bus `add_middleware()` API (verify exists in `k1/bus/impl/local_bus.py`)

**Risk:** If `LocalBus` does not expose `add_middleware()`, need to either add it to K1 or use constructor injection. Check `k1/bus/impl/local_bus.py` and `k1/bus/factory.py` for middleware injection API.

---

#### 1.4.5 -- Wire canonical builders into existing publish call sites (migration shim)

**Problem:** E1.1.6 updates `bus/builders.py` to accept both `dict[str,Any]` and `CanonicalEventMeta` subclasses. But the 50+ existing call sites across the codebase still pass raw dicts. These call sites will NOT automatically use canonical events. A migration shim is needed so that:

1. Existing code continues to work (raw dict path, with deprecation warning).
2. New code in M2+ can pass canonical events directly.
3. The builder internally upgrades raw dicts to canonical events when possible (auto-enrichment).

**Current high-traffic call sites that publish bus events:**

| File | Builder Calls | Usage Pattern |
|------|--------------|---------------|
| `fsm/controller.py` | `build_state_updated`, `build_task_complete`, `build_task_dispatch`, `build_task_failed`, `build_turn_completed`, `build_turn_started` | Constructs payload dict inline, passes to builder |
| `actors/front.py` | `build_final_response`, `build_clarification_request`, `build_findings_ready`, `build_affect_update`, `build_proactive_fill`, `build_weave_batch`, `build_task_accepted`, `build_state_updated` | Constructs payload dict inline |
| `actors/back.py` | `build_task_complete`, `build_task_failed`, `build_task_suspended`, `build_tool_started`, `build_tool_completed`, `build_findings_ready` | Constructs payload dict inline |
| `kernel/bootstrap.py` | `build_task_suspended`, `build_task_resume`, `build_task_failed`, `build_affect_update`, `build_proactive_fill` | Inline Envelope construction in HITL/experience callbacks |
| `tools/dispatcher.py` | `build_tool_started`, `build_tool_completed` | Tool lifecycle events |

**Action:**

1. In `bus/builders.py`, update `_serialize()` to auto-enrich dict payloads with canonical metadata when missing:

   ```python
   def _serialize(payload: dict[str, Any] | CanonicalEventMeta) -> bytes:
       if isinstance(payload, CanonicalEventMeta):
           return json.dumps(payload.to_payload(), separators=(',', ':')).encode('utf-8')
       # Legacy dict path -- inject canonical metadata if missing
       if "event_id" not in payload:
           payload["event_id"] = str(uuid.uuid4())
       if "ts_utc" not in payload:
           payload["ts_utc"] = datetime.utcnow().isoformat()
       if "payload_schema_version" not in payload:
           payload["payload_schema_version"] = "0.1.0"  # pre-migration marker
       return json.dumps(payload, separators=(',', ':')).encode('utf-8')
   ```

2. This ensures that even legacy dict payloads get `event_id`, `ts_utc`, and schema version. The ledger can record them. Downstream consumers see consistent fields.
3. Add a `_LEGACY_ENRICH_WARNING_EMITTED` flag to emit ONE deprecation log per builder function (not per call -- too noisy):

   ```python
   _warned: set[str] = set()
   def _serialize(payload, topic: str = ""):
       if isinstance(payload, dict) and topic and topic not in _warned:
           logger.debug("Legacy dict payload for topic=%s; consider using canonical event", topic)
           _warned.add(topic)
   ```

4. Do NOT change any existing call site in M1. They keep passing dicts. The auto-enrichment ensures ledger compatibility. Full migration of individual call sites is M2+ work (one issue per module).

**Files to modify:**

- `poc/k1_poc/bus/builders.py` (`_serialize` enrichment, `_build` logging)

**Dependency:** E1.1.6 (updated builders exist), E1.1.1 (canonical metadata fields defined)

---

#### 1.4.6 -- Wire ledger into demo coordinator and add health check

**Problem:** The demo coordinator (`demo/coordinator.py`) has a 5-phase initialization sequence with a health check in Phase 5. The ledger is not mentioned anywhere. If a developer runs the demo web app, the ledger is invisible. The health check does not verify ledger operational status.

**Current Phase 5 health check** (`demo/coordinator.py`):

```python
async def _phase5_health_check(self) -> None:
    # Checks: bus alive, FSM in LISTENING, model responds, SS sections accessible
```

**Action:**

1. Add `self.ledger: Any = None` slot to `K1DemoCoordinator.__init__()`.
2. In Phase 2 (`_phase2_kernel_startup`), after `start_kernel()`, copy the ledger reference:

   ```python
   self.ledger = self._kernel.ledger
   self._record("phase2", "ledger", "ledger.attached",
                 f"LedgerWriter attached (store={type(self._kernel.ledger._store).__name__})"
                 if self._kernel.ledger else "Ledger disabled")
   ```

3. Extend Phase 5 health check to verify ledger:

   ```python
   # Ledger health check
   if self.ledger is not None:
       # Write a boot event and verify it can be read back
       from poc.k1_poc.events.conversation import UserInputReceived
       boot_event = UserInputReceived(
           text="__health_check__",
           session_id=self.session_state.session_id if self.session_state else "boot",
           actor="system",
       )
       seq = self.ledger.append(boot_event)
       assert seq >= 0, "Ledger append returned invalid sequence"
       self._record("phase5", "ledger", "ledger.health_ok",
                     f"Ledger write/read verified (seq={seq})")
   ```

4. Add a `/api/ledger/stats` endpoint to the web app for debugging:

   ```python
   @app.get("/api/ledger/stats")
   async def get_ledger_stats() -> dict:
       if _coordinator is None or _coordinator.ledger is None:
           return {"enabled": False}
       store = _coordinator.ledger._store
       return {
           "enabled": True,
           "total_events": store.count(),
           "store_type": type(store).__name__,
       }
   ```

**Files to modify:**

- `poc/k1_poc/demo/coordinator.py` (init, phase2, phase5)
- `poc/k1_poc/demo/web/app.py` (add `/api/ledger/stats` endpoint)

**Dependency:** 1.4.1 (kernel bootstrap creates ledger), E1.2.1 (LedgerWriter exists)

---

#### 1.4.7 -- Wire canonical events into existing test infrastructure

**Problem:** The POC has extensive tests (`tests/poc/test_m08_fsm_controller.py` and others) that create bus infrastructure, publish envelopes, and verify FSM behavior. These tests use raw dict payloads. After M1, tests should be able to:

1. Inject a test ledger and verify events were recorded.
2. Use canonical event builders instead of raw dicts.
3. Verify ledger round-trip (publish -> ledger -> projection -> state match).

But the test helpers do NOT know about the ledger. `ConciergeController` tests create the FSM without a ledger. New tests in 1.2.4 (replay test) will fail if the FSM has no `set_ledger()` in the test setup.

**Action:**

1. Create `poc/k1_poc/testing/__init__.py` and `poc/k1_poc/testing/fixtures.py` with reusable test fixtures:

   ```python
   def create_test_ledger() -> tuple[LedgerWriter, InMemoryLedgerStore]:
       store = InMemoryLedgerStore()
       writer = LedgerWriter(store=store)
       return writer, store

   def create_wired_fsm(*, capture: bool = True, with_ledger: bool = True) -> dict:
       """Create a fully wired FSM with bus, ledger, and test infrastructure."""
       bus = create_poc_bus(capture=capture)
       router = create_poc_router()
       fsm = ConciergeController(bus=bus, router=router)
       result = {"bus": bus, "router": router, "fsm": fsm}
       if with_ledger:
           writer, store = create_test_ledger()
           fsm.set_ledger(writer)
           result["ledger"] = writer
           result["ledger_store"] = store
       return result
   ```

2. Update the M1 replay test (1.2.4) to use `create_wired_fsm()` fixture.
3. Add a `conftest.py` at `tests/poc/conftest.py` (if not exists) that provides `@pytest.fixture` for wired FSM with ledger.
4. Add an assertion helper:

   ```python
   def assert_ledger_contains(store: InMemoryLedgerStore, event_type: str, count: int = 1) -> None:
       events = store.read_by_type("*", event_type)
       assert len(events) == count, f"Expected {count} {event_type} events, found {len(events)}"
   ```

**Files to create:**

- `poc/k1_poc/testing/__init__.py`
- `poc/k1_poc/testing/fixtures.py`

**Files to modify:**

- `tests/poc/conftest.py` (add ledger fixtures)

**Dependency:** E1.2.1 (LedgerWriter/InMemoryLedgerStore exist), 1.4.2 (`set_ledger()` exists on FSM)

---

#### 1.4.8 -- Backward compatibility verification: full regression test

**Problem:** M1 adds new packages and modifies core paths (builders, FSM, bootstrap). Any regression in the existing system is a showstopper. The existing test suite was written for raw dicts and no ledger. After M1 wiring, ALL existing tests must still pass with ZERO changes.

**Invariants to verify:**

1. `start_kernel()` with `enable_ledger=False` produces the exact same `KernelRuntime` as before M1.
2. All 28 bus builders still accept `dict[str, Any]` payloads and produce identical Envelope bytes (modulo auto-enriched `event_id`/`ts_utc` which are additive, not breaking).
3. All 19 FSM handlers process envelopes exactly as before (ledger append is additive, never blocking, never error-propagating).
4. Demo web app boots and handles a user message round-trip.
5. `_parse_payload()` returns a dict that is a superset of the previous dict (new fields are additive).
6. No import errors from new packages (events/, ledger/, testing/).

**Test plan:**

1. Run the entire existing test suite with ledger enabled:

   ```
   pytest tests/poc/ -x -q
   ```

   All tests must pass. Any failure is a bug in the wiring, not the tests.

2. Run with ledger disabled:

   ```
   K1_LEDGER_ENABLED=false pytest tests/poc/ -x -q
   ```

   Identical results (proves the ledger is truly optional).

3. Boot the demo web app and execute a 3-turn conversation:
   - User sends "What's on the agenda today?"
   - Verify FSM transitions: LISTENING -> PHASE1_CLASSIFY -> DISPATCHING_WORKER -> MONITORING_WORKER -> WEAVING -> RESPONDING -> LISTENING
   - Check `/api/ledger/stats` shows events recorded.
   - Check `/api/status` shows system_ready=True.

4. Run the new replay test (1.2.4):
   - 5-turn session with HITL cycle
   - Projected state matches runtime state

**Files to create:**

- `tests/poc/test_m01_backward_compat.py` (regression guard)

**Files to reference:**

- All existing test files in `tests/poc/`
- `poc/k1_poc/demo/web/app.py` (manual smoke test)

**Acceptance criteria:** Zero test failures. Zero import errors. Demo web app functional. Ledger records events. Ledger can be disabled without affecting any behavior.

---

#### 1.4.9 -- Integration touchpoint matrix: document all M2-M12 handoff contracts

**Problem:** Every subsequent milestone assumes M1 artifacts are available. Without an explicit handoff contract, each milestone team will guess at how to use the ledger, canonical events, and validators. This causes inconsistent adoption and eventual drift.

**Action:** Create a touchpoint matrix that maps each M2-M12 milestone to the specific M1 artifacts it depends on and how it should use them.

**Touchpoint Matrix:**

| Milestone | M1 Artifact Used | How It Uses It | Handoff Contract |
|-----------|-----------------|----------------|-----------------|
| **M2** (FSM Hardening) | `events/validator.py`, `ledger/writer.py`, dead-letter canonical event | Guard matrix uses validator to reject invalid events. Dead-letter pipeline writes rejected events to ledger. `DeadLettered` event schema from 1.1.2. | M2 issues reference `validate_event()` for guard checks. Dead-letter handler calls `ledger.append(DeadLettered(...))`. |
| **M3** (Actor Hardening) | `events/task.py`, `bus/deserialize.py` | Back mailbox topic router deserializes envelopes to canonical task events. Cancel propagation uses `TaskCancelled` event. Resume context uses `TaskResumed`. | M3 handlers call `deserialize_envelope()` instead of raw `json.loads()`. |
| **M4** (SessionState) | `events/registry.py`, `ledger/projections.py` | SS write path enforcement uses event registry to validate writes. Prompt builder reads canonical event types for context assembly. | SS sections validate incoming data against canonical event schemas. |
| **M5** (Arbiter) | `events/conversation.py`, `events/task.py`, `ledger/writer.py` | Arbiter emits `IntentArbitrated` canonical event. Task creation emits `TaskCreated`. Multi-device conflict resolution emits canonical events for audit trail. | Every arbiter decision appends to ledger before FSM mutation. |
| **M6** (HITL V3) | `events/hitl.py`, `ledger/writer.py`, `ledger/projections.py` | HITL sub-task model uses canonical HITL events. Back resume path reads from ledger projection. HITL crash recovery replays from ledger. | HITL coordinator calls `ledger.append()` for every state change. Recovery calls `project_hitl_state()`. |
| **M7** (BackPool) | `events/task.py` (`TaskLeased`), `ledger/writer.py` | Worker lease lifecycle emits `TaskLeased` events. Dependency ordering reads task events from ledger for DAG reconstruction. | BackPool manager calls `ledger.append(TaskLeased(...))` on claim. |
| **M8** (Weave Policy) | `events/weave.py`, `ledger/writer.py` | Weave signal collector records `WeaveCandidateArrived`. Decision engine records `WeaveDecisionMade`. Emission records `WeaveEmitted`. | All weave decisions are ledger-backed for replay and debugging. |
| **M9** (Ledger Migration) | ALL ledger artifacts, `ledger/projections.py` | Full migration: in-memory state becomes cached projection. Explicit crash recovery from ledger. Protocol state (cancel, suspend, HITL) rebuilt from events. | This milestone converts dual-write (ledger + in-memory) to ledger-primary (project on demand). |
| **M10** (UltraBERT) | `events/conversation.py` (`UserInputReceived`) | Phase 1 pipeline reads canonical user input event for classification. Tier routing decision recorded as canonical event. | Phase 1 receives `UserInputReceived` instead of raw dict. |
| **M11** (Observability) | `ledger/store.py` (read API), `events/registry.py` | Metrics collector reads ledger for event counts and timing. Alert engine evaluates rules against ledger-derived metrics. Session summary materializes from ledger. | MetricsCollector uses `store.read_by_type()` for metric computation. |
| **M12** (Chaos Tests) | ALL M1 artifacts | Chaos tests verify ledger survives concurrent writes, crash recovery replays correctly, race conditions don't corrupt event stream. | Tests use `create_wired_fsm()` fixture with ledger injection. |

**Output:** Add this matrix as a reference section at the end of M1 in the milestones document. Each M2-M12 milestone issue that depends on M1 must reference the specific artifact and usage pattern from this matrix.

**Files to create:** None (this is documentation within the milestones doc, appended here).

**Handoff rule:** Any M2-M12 issue that touches an M1 artifact MUST include a "M1 Dependency" section in its description stating:

- Which M1 artifact (package/module/class/function)
- How it is accessed (import path)
- What method/API it calls
- What the expected behavior is

---

## M2: FSM Hardening & Transition Contracts

**Goal:** Make FSM transitions deterministic, guarded, and auditable. Eliminate
hidden corruption from async race conditions. Dead-letter invalid events.

**Gate:** Guard table covers all state/event combinations. Invalid transitions
produce explicit fault events. Dead-letter stream captures orphan/late events.
`_on_response_final` branching is externalized into testable action table.

**Dependency:** M1 (canonical bus topics, envelope validation, builder migration).

---

### M2 Context Table

Full audit of every file touched by M2, with current state and what M2 changes.

| File | Current Lines | Current State | M2 Changes |
|------|--------------|---------------|------------|
| `poc/k1_poc/fsm/transition_table.py` | ~120 | 11 states, 28 legal transitions using only 9 bus topics + 6 synthetic triggers. Topics imported: USER_INPUT, FINAL_RESPONSE, TASK_COMPLETE, TASK_DISPATCH, TASK_FAILED, TASK_RESUME, TASK_SUSPENDED, TOOL_COMPLETED, TOOL_STARTED. Missing from table: TASK_CANCEL, DAG_COMPLETED, FINDINGS_READY, CLARIFICATION_REQUEST, CLARIFICATION_RESPONSE, ARTIFACT_CREATED, AFFECT_UPDATE, PROACTIVE_FILL, WEAVE_BATCH, TASK_ACCEPTED. | Expand to FULL_GUARD_TABLE covering all 19+ subscribed topics. Add handler-action enum per cell. Add `get_guard_action(state, topic)` returning `(transition, action)` or `DEAD_LETTER`. |
| `poc/k1_poc/fsm/controller.py` | 1979 | 18 `_on_*` handlers. 25+ inline `self._state ==` / `self._state in` checks that bypass transition table. `_on_task_cancel` (line 1270) directly sets `self._state = ConciergeState.CANCELLING` bypassing `_transition()`. `_on_response_final` (lines 1472-1689) has 8+ state branches across 217 lines. Topic guard pattern copy-pasted 4 times (lines 586, 1073, 1306, 1478). COMPANIONING/PROGRESSING interrupt paths (lines 633-663 vs 669-698) are 7-step identical sequences. `_emit_turn_completed + _drain_front_lock_queue` combo repeated 3 times (lines 1128-1129, 1581-1582, 1685-1689). Hardcoded `"front_half"`/`"back_half"` actor names (lines 815, 832). Duplicate `dag.completed` subscription (lines 434-435: both `TOPIC_DAG_COMPLETED` and bare string `"k1.orchestration.dag.completed"`). | Refactor handlers to use guard table lookup. Replace all inline state checks with guard-driven dispatch. Extract `_on_response_final` branching to action table. Replace CANCELLING force-set with validated transition. Extract topic guard to decorator. Extract interrupt handler duplication. Add dead-letter publish on guard rejection. |
| `poc/k1_poc/fsm/errors.py` | ~38 | `IllegalTransitionError(from_state, trigger)` -- logged as warning, does NOT crash. `FrontLockOverflowError(rejected_topic, queue_depth)` -- backpressure signal. | Add `DeadLetterEvent` dataclass. Add `GuardRejectionError` for structured dead-letter metadata. |
| `poc/k1_poc/fsm/states.py` | ~55 | `ConciergeState` enum with 11 values. Docstring has state-to-event mapping table. | No structural change. Update docstring table to reflect expanded guard matrix coverage. |
| `poc/k1_poc/fsm/front_lock.py` | ~180 | `TOPIC_PRIORITY` dict (lines 48-54) uses HARDCODED topic strings: `"k1.session.user.input.v1"`, `"k1.orchestration.task.suspended.v1"`, etc. Does NOT import from `bus/topics.py`. `DEFAULT_MAX_QUEUE_DEPTH = 8`. | Replace hardcoded topic strings with imported constants from `bus/topics.py` (same fix pattern as M0 0.2.3 setup.py hardcodes). |
| `poc/k1_poc/fsm/turn_state.py` | ~100 | `FSMTurnState` with `pending_results: deque[dict]`. No TTL, no max depth, no dead-letter drain. Results can queue indefinitely. | Add `max_pending_depth` from config. Add `queued_at_ns` TTL check on drain. Emit dead-letter for expired/overflow results. |
| `poc/k1_poc/fsm/interrupt_handler.py` | ~200 | `InterruptClassifier` (keyword-based), `ProactiveWakeHandler`. Both are clean standalone classes. | No structural change. Wire into extracted `_handle_interrupt()` helper. |
| `poc/k1_poc/fsm/control_extension.py` | ~200 | `ConciergeControlExtension` tracks `fsm_state`, `active_task_ids`, `complexity_tier`. Single-writer. | Ensure `set_fsm_state()` is called on ALL state transitions including CANCELLING path (currently skipped by force-set). |
| `poc/k1_poc/fsm/task_bridge.py` | 407 | `TaskBridge` manages task lifecycle in SS. Clean status transitions: DISPATCHED -> ACTIVE -> COMPLETED/FAILED/CANCELLED/SUSPENDED. | No structural change for M2. |
| `poc/k1_poc/fsm/phase1.py` | 325 | `Phase1Pipeline` protocol, `StubPhase1Pipeline`, `Phase1Result`, `TurnLock`. | No change for M2. |
| `poc/k1_poc/fsm/history_writer.py` | 237 | `HistoryWriter` wraps TypedHistoryEntry creation. Converters for Front/Back. | No change for M2. |
| `poc/k1_poc/protocols/weave_state.py` | ~200 | `STATE_ACTION_TABLE` maps all 11 ConciergeState values to `WeaveAction` enum (IMMEDIATE, QUEUE_WEAVE, QUEUE, CHAIN). `PendingResultsQueue` has no max depth, no TTL, no dead-letter. | Add fallback/dead-letter action for stuck QUEUE states. Add max depth + TTL to `PendingResultsQueue`. |
| `poc/k1_poc/protocols/weave_batcher.py` | 339 | `WeaveBatcher` with fixed 500ms window. `_pending`, `_queued` lists. No overflow protection on `_queued`. | Add max queued depth. Emit dead-letter when overflow threshold hit. |
| `poc/k1_poc/protocols/cancel_handler.py` | 241 | `CancellationHandler` with `_tokens`, `_cancelled_tasks`. `request_cancel()` is sync, `cancel_task()` is async. Clean dedup via `confirm_cancel()`. | Wire into guard table so CANCELLING transition goes through `_transition()` instead of force-set. |
| `poc/k1_poc/bus/topics.py` | M1 SOT | All topic constants. | Add `TOPIC_DEAD_LETTER = "k1.internal.dead_letter.v1"` (new topic for dead-letter stream). |
| `poc/k1_poc/config/defaults.yaml` | 584 | Config tree. `fsm.front_lock_max_queue_depth: 8`. | Add `fsm.pending_results_max_depth`, `fsm.pending_results_ttl_seconds`, `fsm.dead_letter_enabled`. |
| `tests/poc/test_m08_fsm_controller.py` | ~1200 | 90+ tests covering state enum, init, transition table, transition engine, user input, task dispatch, task complete, task failed, task cancel, task suspended, task resume, response final, tools, happy path, weave path, turn state, front lock. NO tests for: guard matrix completeness, dead-letter capture, response-final action table isolation, handler-vs-table agreement, passthrough handler state safety. | Add M2 conformance tests: guard table completeness, dead-letter emission, action table coverage, interrupt dedup extraction, CANCELLING transition validation. |

---

### M2 Duplication Inventory

Complete catalog of all duplications found across FSM code that M2 must resolve.

| # | Duplication | Location | Severity | Resolution |
|---|-------------|----------|----------|------------|
| D1 | COMPANIONING interrupt path identical to PROGRESSING interrupt path | `controller.py` lines 633-663 vs 669-698. Both execute: classify -> increment turn -> write history -> transition(INTERRUPT_HANDLING) -> transition(DISPATCHING) -> emit turn_started -> run_phase1. 7-step identical sequence. | HIGH -- maintenance risk, divergence risk on future edits. | Extract to `_handle_interrupt(envelope, text)` in 2.1.5. |
| D2 | Topic guard pattern copy-pasted 4 times | `controller.py` lines 586-596 (`_on_user_input`), 1073-1081 (`_on_task_complete`), 1306-1315 (`_on_task_suspended`), 1478-1488 (`_on_response_final`). Same 8-line block: `if envelope.topic != TOPIC_X: logger.debug(...); return`. | MEDIUM -- 4 copies, grows with new handlers. | Extract to `_topic_guard(envelope, expected_topic)` decorator or helper in 2.3.3. |
| D3 | `_emit_turn_completed` + `_drain_front_lock_queue` combo | `controller.py` lines 1128-1129, 1581-1582, 1685-1689. Always called together, never independently. | LOW-MEDIUM -- 3 call sites, always paired. | Extract to `_finalize_turn(envelope)` in 2.3.4. |
| D4 | Duplicate `dag.completed` subscription | `controller.py` lines 434-435. Subscribes to BOTH `TOPIC_DAG_COMPLETED` (with `.v1`) AND bare `"k1.orchestration.dag.completed"` string. Both map to same `_on_dag_completed` handler. | MEDIUM -- wastes subscription, bare string bypasses constant system. | Remove bare string subscription in 2.1.1. Rely on M1 canonical constant only. |
| D5 | Hardcoded topic strings in FrontLock priority map | `front_lock.py` lines 48-54. `TOPIC_PRIORITY` dict uses 6 bare strings: `"k1.session.user.input.v1"`, `"k1.orchestration.task.suspended.v1"`, etc. Same anti-pattern fixed in M0 0.2.3 (setup.py hardcodes). | MEDIUM -- drift risk if topic constants change. | Replace with imported constants from `bus/topics.py` in 2.1.6. |
| D6 | Hardcoded actor names `"front_half"` / `"back_half"` | `controller.py` lines 815, 832 in `_deliver_to_front()` / `_deliver_to_back()`. Same string-literal anti-pattern. | LOW -- 2 occurrences, unlikely to change, but violates M0 0.2.3 principle. | Extract to `FRONT_ACTOR_NAME` / `BACK_ACTOR_NAME` constants. Fix in 2.1.6 alongside FrontLock fix. |
| D7 | Inline state-check branches duplicate what guard table should provide | 25+ `self._state ==` / `self._state in` checks across 9 handler methods. Each handler reimplements its own "which states am I allowed in?" logic. The transition table already encodes this but only covers 9/19 topics. | HIGH -- the core problem M2 solves. | Full guard table expansion (2.1.1) + handler refactoring (2.1.2) to use table-driven dispatch. |

---

### E2.1 -- FSM Guard Matrix

Source: WB 3.F, 13.5

| # | Issue | Source |
|---|-------|--------|
| 2.1.1 | Expand TRANSITION_TABLE to full guard matrix covering all subscribed topics | WB 3.F |
| 2.1.2 | Introduce handler guard middleware using table-driven dispatch | WB 3.F |
| 2.1.3 | Replace forced CANCELLING shortcut with validated transition contract | WB 13.5 |
| 2.1.4 | Extract COMPANIONING/PROGRESSING interrupt duplication into shared handler | WB 13.4 |
| 2.1.5 | Remove duplicate `dag.completed` subscription and bare-string topic | WB 13.2 |
| 2.1.6 | Replace hardcoded topic strings in FrontLock and controller with constants | WB 12.3, M0 0.2.3 pattern |
| 2.1.7 | Add guard matrix completeness conformance test | WB 13.6 |

---

#### 2.1.1 Expand TRANSITION_TABLE to full guard matrix covering all subscribed topics

**Problem:**

`transition_table.py` defines `TRANSITION_TABLE` with 11 states and 28 legal transitions, but only uses 9 bus topics + 6 synthetic triggers as keys. The controller's `_subscribe_all()` (controller.py line 422) wires 20 subscriptions to 18 distinct handlers. This means 10+ topics that the FSM handles are **completely invisible to the transition table**.

**Current coverage gap (topics subscribed but NOT in TRANSITION_TABLE):**

| Subscribed Topic | Handler | Current State Guard | Guard Source |
|-----------------|---------|-------------------|-------------|
| `TOPIC_TASK_CANCEL` | `_on_task_cancel` | Inline `self._state in (COMPANIONING, PROGRESSING, DISPATCHING)` at line 1263 | controller.py only |
| `TOPIC_DAG_COMPLETED` | `_on_dag_completed` | None -- normalizes to task.complete/failed | controller.py only |
| `"k1.orchestration.dag.completed"` | `_on_dag_completed` | Bare string duplicate of above | controller.py only |
| `TOPIC_FINDINGS_READY` | `_on_findings_ready` | None -- passthrough to FrontLock | No guard |
| `TOPIC_CLARIFICATION_REQUEST` | `_on_clarification_request` | None -- passthrough to FrontLock | No guard |
| `TOPIC_CLARIFICATION_RESPONSE` | `_on_clarification_response` | None -- passthrough to Back | No guard |
| `TOPIC_ARTIFACT_CREATED` | `_on_artifact_created` | None -- history write only | No guard |
| `TOPIC_AFFECT_UPDATE` | `_on_affect_update` | None -- log only (RELAXED) | No guard |
| `TOPIC_PROACTIVE_FILL` | `_on_proactive_fill` | None -- log only (RELAXED) | No guard |
| `TOPIC_WEAVE_BATCH` | `_on_weave_batch` | None -- passthrough to FrontLock | No guard |

**What to do:**

1. Introduce `GuardAction` enum in `transition_table.py`:

   ```
   class GuardAction(str, Enum):
       TRANSITION = "transition"       # Normal: validate + transition
       PASSTHROUGH = "passthrough"     # Forward without state change (findings, clarification)
       OBSERVE = "observe"             # Log/history only, no routing (artifact, affect)
       DEAD_LETTER = "dead_letter"     # Reject: publish to dead-letter stream
   ```

2. Expand `TRANSITION_TABLE` into `FULL_GUARD_TABLE: dict[ConciergeState, dict[str, tuple[GuardAction, ConciergeState | None]]]` covering ALL 11 states x ALL subscribed topics. Every cell must have an explicit action. No implicit passthrough.

3. Add `get_guard_action(state, topic) -> tuple[GuardAction, ConciergeState | None]` function. Returns `(DEAD_LETTER, None)` for any state/topic pair not in the table (closed-world assumption).

4. Keep existing `is_legal()` and `target_state()` as thin wrappers over the new table for backward compatibility until all handlers are migrated (2.1.2).

5. Remove bare string `"k1.orchestration.dag.completed"` from subscription list (D4).

**Files:**

- `poc/k1_poc/fsm/transition_table.py` -- expand table, add enum, add lookup function
- `poc/k1_poc/bus/topics.py` -- no change needed (constants already exist)

**Acceptance:**

- `FULL_GUARD_TABLE` has an entry for every `(ConciergeState, subscribed_topic)` pair -- 11 states x 19 unique topics = 209 cells
- `get_guard_action()` returns explicit action for every cell
- Unknown topics return `DEAD_LETTER`
- Existing `is_legal()` / `target_state()` tests still pass (backward compat wrapper)

---

#### 2.1.2 Introduce handler guard middleware using table-driven dispatch

**Problem:**

Each handler method has its own inline `self._state ==` / `self._state in` branching to decide whether to process, queue, or drop an event. There are 25+ such checks across 9 handlers (see Duplication D7). This creates:

- Divergence risk: each handler can independently drift from intended state policy
- No single audit point: correctness requires reading ALL 1979 lines of controller.py
- No dead-letter: events in incompatible states are silently dropped or queued with only a log warning

**Inline state checks to be replaced (complete list from grep):**

| Handler | Line(s) | State Check | Current Behavior |
|---------|---------|-------------|------------------|
| `_on_user_input` | 609, 633, 669, 702, 739 | 5 branches: CLARIFYING_WORKER, COMPANIONING, PROGRESSING, (LISTENING/CLARIFYING_USER), (DELIVERING/WEAVING/PROACTIVE_WAKE) | Process, interrupt, interrupt, normal, queue, drop |
| `_on_task_dispatch` | 873 | `!= COMPANIONING` (idempotent skip) | Skip if already COMPANIONING |
| `_on_task_complete` | 1112, 1132, 1150 | same-turn + COMPANIONING, LISTENING, (COMPANIONING/PROGRESSING) | Skip, proactive, deliver, queue |
| `_on_task_failed` | 1214 | `in (COMPANIONING, PROGRESSING, CANCELLING)` | Deliver or queue |
| `_on_task_cancel` | 1263 | `in (COMPANIONING, PROGRESSING, DISPATCHING)` | Force state or no-op |
| `_on_task_suspended` | 1348 | `not in (COMPANIONING, PROGRESSING)` | Store context but skip transition |
| `_on_response_final` | 1506-1673 | 8+ branches (see 2.3.1 for full breakdown) | Complex decision tree |
| `_on_tool_started` | 1874 | `== COMPANIONING` | Transition or no-op |
| `_on_tool_completed` | 1892 | `== PROGRESSING` | Transition or no-op |

**What to do:**

1. Create `_guard_dispatch(envelope) -> GuardAction` method that calls `get_guard_action(self._state, envelope.topic)`.
2. Add `_publish_dead_letter(envelope, reason)` method for rejected events.
3. At the TOP of each handler, call `_guard_dispatch(envelope)`. If `DEAD_LETTER`, publish and return. If `PASSTHROUGH` or `OBSERVE`, proceed with current logic. If `TRANSITION`, proceed to state-specific handler logic.
4. Migrate handlers incrementally: start with simple passthrough handlers (`_on_findings_ready`, `_on_clarification_request`, `_on_affect_update`, `_on_proactive_fill`, `_on_weave_batch`) then move to complex handlers.
5. Keep complex handlers' internal branching for now (full externalization is 2.3.1 for response_final). The guard adds a FIRST gate, not a replacement of all internal logic.

**Files:**

- `poc/k1_poc/fsm/controller.py` -- add `_guard_dispatch()`, `_publish_dead_letter()`, wire into handlers

**Acceptance:**

- Every `_on_*` handler starts with guard check
- Events in incompatible states produce dead-letter publish (not silent drop)
- All 90+ existing tests pass (guard matches current inline behavior)
- New test: deliver `task.complete` in `CLARIFYING_USER` state -> dead-letter emitted

---

#### 2.1.3 Replace forced CANCELLING shortcut with validated transition contract

**Problem:**

`_on_task_cancel` (controller.py line 1270) directly mutates `self._state`:

```python
self._state = ConciergeState.CANCELLING
```

This BYPASSES `_transition()` entirely, which means:

- `is_legal()` is never checked -- no validation that CANCELLING is reachable from current state
- `control_ext.set_fsm_state()` is NOT called -- `ConciergeControlExtension` still shows previous state
- The `state_updated` observability event is published via manual `self._bus.publish(build_state_updated(...))` (lines 1273-1283) instead of through `_transition()` -- different code path with different payload shape
- If `TRANSITION_TABLE` doesn't include `TASK_CANCEL` transitions (it doesn't), the force-set is the only way in -- but this means CANCELLING is completely ungoverned

**Current allowed-in check (inline guard):**

```python
if self._state in (ConciergeState.COMPANIONING, ConciergeState.PROGRESSING, ConciergeState.DISPATCHING):
    self._state = ConciergeState.CANCELLING  # FORCE
```

States NOT in this check but potentially receiving task.cancel: LISTENING, DELIVERING, WEAVING, CLARIFYING_USER, CLARIFYING_WORKER, INTERRUPT_HANDLING, PROACTIVE_WAKE, CANCELLING itself.

**What to do:**

1. Add `TOPIC_TASK_CANCEL` transitions to `FULL_GUARD_TABLE` (from 2.1.1):
   - `COMPANIONING + task.cancel -> CANCELLING` (TRANSITION)
   - `PROGRESSING + task.cancel -> CANCELLING` (TRANSITION)
   - `DISPATCHING + task.cancel -> CANCELLING` (TRANSITION)
   - All other states + task.cancel -> `DEAD_LETTER` (cancel in incompatible state)

2. Replace the force-set block (lines 1263-1290) with:

   ```python
   self._transition(ConciergeState.CANCELLING, TOPIC_TASK_CANCEL, envelope)
   ```

   This ensures:
   - `is_legal()` validates the transition
   - `control_ext.set_fsm_state()` syncs
   - `state_updated` observability follows the standard code path
   - Dead-letter fires if state is incompatible

3. Remove the manual `build_state_updated` publish block (lines 1273-1283) -- `_transition()` already emits this.

**Files:**

- `poc/k1_poc/fsm/transition_table.py` -- add TASK_CANCEL rows (part of 2.1.1 expansion)
- `poc/k1_poc/fsm/controller.py` -- replace force-set with `_transition()` call

**Acceptance:**

- `_on_task_cancel` uses `_transition()` -- zero direct `self._state =` assignments outside `__init__` and `teardown`
- `control_ext.fsm_state` reads `"CANCELLING"` after cancel in compatible state
- `state_updated` event payload matches standard transition payload shape
- Cancel in incompatible state (e.g., LISTENING) produces dead-letter, not silent no-op
- `test_8_2_22_transitions_to_cancelling` still passes

---

#### 2.1.4 Extract COMPANIONING/PROGRESSING interrupt duplication into shared handler

**Problem (Duplication D1):**

`_on_user_input` has two nearly identical 7-step blocks for interrupt handling:

**COMPANIONING path** (controller.py lines 633-663):

```
1. classify = self._interrupt_classifier.classify(text)
2. self._turn_number += 1
3. self._write_history(entry_type="user", ...)
4. self._transition(ConciergeState.INTERRUPT_HANDLING, ...)
5. self._transition(ConciergeState.DISPATCHING, ...)
6. self._bus.publish(build_turn_started(...))
7. self._run_phase1(...)
```

**PROGRESSING path** (controller.py lines 669-698):

```
1. classify = self._interrupt_classifier.classify(text)  # IDENTICAL
2. self._turn_number += 1                                 # IDENTICAL
3. self._write_history(entry_type="user", ...)            # IDENTICAL
4. self._transition(ConciergeState.INTERRUPT_HANDLING, ...)# IDENTICAL
5. self._transition(ConciergeState.DISPATCHING, ...)       # IDENTICAL
6. self._bus.publish(build_turn_started(...))              # IDENTICAL
7. self._run_phase1(...)                                   # IDENTICAL
```

The ONLY difference is the `if self._state ==` check that leads into each block. The 7-step body is character-for-character identical.

**What to do:**

1. Extract to `_handle_interrupt(self, envelope: Envelope, text: str) -> None` method.
2. Replace both blocks with:

   ```python
   if self._state in (ConciergeState.COMPANIONING, ConciergeState.PROGRESSING):
       self._handle_interrupt(envelope, text)
       return
   ```

3. The guard table (2.1.1) should encode `COMPANIONING + user.input -> INTERRUPT_HANDLING` and `PROGRESSING + user.input -> INTERRUPT_HANDLING` with `TRANSITION` action, which this method fulfills.

**Files:**

- `poc/k1_poc/fsm/controller.py` -- add `_handle_interrupt()`, simplify `_on_user_input`

**Acceptance:**

- Zero duplicated interrupt logic in `_on_user_input`
- `test_8_2_5_companioning_interrupt` and `test_8_2_9_progressing_interrupt` still pass
- New `_handle_interrupt` is independently testable

---

#### 2.1.5 Remove duplicate `dag.completed` subscription and bare-string topic

**Problem (Duplication D4):**

`_subscribe_all()` (controller.py lines 434-435) subscribes to BOTH:

```python
(TOPIC_DAG_COMPLETED, self._on_dag_completed),        # "k1.orchestration.dag.completed.v1"
("k1.orchestration.dag.completed", self._on_dag_completed),  # bare string without .v1
```

Both map to the same handler. The bare string `"k1.orchestration.dag.completed"` bypasses the constant system established in M0 and violates M1's canonical topic regime.

The handler `_on_dag_completed` (lines 1021-1060) already handles both variants by checking for `.v1` suffix. After M1 enforces canonical topics, only the `.v1` variant should exist.

**What to do:**

1. Remove the bare-string subscription line (`"k1.orchestration.dag.completed"`, ...).
2. Verify that `_on_dag_completed` still works with only the `.v1` topic.
3. If backward compat is needed for transition, add a TODO comment citing M1 completion.

**Files:**

- `poc/k1_poc/fsm/controller.py` line 435 -- remove bare string subscription

**Acceptance:**

- `_subscribe_all()` has exactly 19 subscriptions (not 20)
- No bare string topic literals in `_subscribe_all()`
- `_on_dag_completed` handler still processes `dag.completed.v1` events correctly

---

#### 2.1.6 Replace hardcoded topic strings in FrontLock and controller with constants

**Problem (Duplications D5, D6):**

**FrontLock** (`front_lock.py` lines 48-54):

```python
TOPIC_PRIORITY: dict[str, int] = {
    "k1.session.user.input.v1": PRIORITY_URGENT,
    "k1.orchestration.task.suspended.v1": PRIORITY_INTERACTIVE,
    "k1.orchestration.task.complete.v1": PRIORITY_RESULT,
    "k1.orchestration.task.failed.v1": PRIORITY_ERROR,
    "k1.orchestration.findings.ready.v1": PRIORITY_INFO,
    "k1.internal.weave.batch.v1": PRIORITY_RESULT,
}
```

Six hardcoded strings. Same anti-pattern fixed in M0 issue 0.2.3 (setup.py hardcodes).

**Controller** (`controller.py` lines 815, 832):

```python
self._router.deliver("front_half", envelope)   # line 815
self._router.deliver("back_half", envelope)     # line 832
```

Two hardcoded actor name strings.

**What to do:**

1. **FrontLock**: Import constants from `bus/topics.py` and rebuild `TOPIC_PRIORITY`:

   ```python
   from poc.k1_poc.bus.topics import (
       TOPIC_USER_INPUT, TOPIC_TASK_SUSPENDED, TOPIC_TASK_COMPLETE,
       TOPIC_TASK_FAILED, TOPIC_FINDINGS_READY, TOPIC_WEAVE_BATCH,
   )
   TOPIC_PRIORITY: dict[str, int] = {
       TOPIC_USER_INPUT: PRIORITY_URGENT,
       TOPIC_TASK_SUSPENDED: PRIORITY_INTERACTIVE,
       ...
   }
   ```

2. **Controller**: Extract actor names to module constants:

   ```python
   FRONT_ACTOR_NAME = "front_half"
   BACK_ACTOR_NAME = "back_half"
   ```

   Replace both `self._router.deliver("front_half", ...)` and `"back_half"` with constants.

**Files:**

- `poc/k1_poc/fsm/front_lock.py` -- import bus/topics constants, rebuild TOPIC_PRIORITY
- `poc/k1_poc/fsm/controller.py` -- extract FRONT_ACTOR_NAME/BACK_ACTOR_NAME constants

**Acceptance:**

- Zero hardcoded topic strings in `front_lock.py`
- Zero hardcoded actor strings in `controller.py` delivery methods
- `test_8_4_4_enqueue_priority_order` still passes
- Conformance test (from M0 0.3.15): no bare `"k1."` string literals outside `bus/topics.py`

---

#### 2.1.7 Add guard matrix completeness conformance test

**Problem:**

No test currently verifies that the guard table covers all state/topic pairs. Existing `test_8_1_13_covers_all_12_states` only checks that TRANSITION_TABLE has an entry for each state -- it does NOT check topic coverage.

**What to do:**

1. Add `test_2_1_7a_guard_table_covers_all_states()`:
   - Assert `set(FULL_GUARD_TABLE.keys()) == set(ConciergeState)`

2. Add `test_2_1_7b_guard_table_covers_all_subscribed_topics()`:
   - Collect all topics from `_subscribe_all()` subscription list
   - For every state, assert every subscribed topic has an entry
   - Formula: `len(states) * len(subscribed_topics)` cells == entries in table

3. Add `test_2_1_7c_no_unknown_actions_in_guard_table()`:
   - Assert all actions are valid `GuardAction` enum members

4. Add `test_2_1_7d_handler_state_checks_agree_with_guard_table()`:
   - For each handler, verify that the states where it processes events match the guard table's TRANSITION/PASSTHROUGH entries for that topic
   - This is the "transition table vs handler agreement" test -- catches when someone adds a state check to a handler without updating the table

**Files:**

- `tests/poc/test_m08_fsm_controller.py` -- add `TestGuardMatrixConformance` class

**Acceptance:**

- All 4 conformance tests pass on the new FULL_GUARD_TABLE
- Tests FAIL if a new topic is added to `_subscribe_all()` without a guard table entry (closed-world enforcement)

---

### E2.2 -- Dead-Letter Pipeline

Source: WB 3.F, 12.3, 12.5

| # | Issue | Source |
|---|-------|--------|
| 2.2.1 | Define dead-letter envelope schema and topic constant | WB 4, M1 1.2.3 |
| 2.2.2 | Route guard-rejected events to dead-letter stream | WB 3.F |
| 2.2.3 | Add pending_results TTL and max-depth overflow to dead-letter | WB 12.3 |
| 2.2.4 | Build reconciliation consumer for dead-letter events | WB 3.F |
| 2.2.5 | Add weave queue overflow guard with dead-letter fallback | WB 12.3 (weave_state) |

---

#### 2.2.1 Define dead-letter envelope schema and topic constant

**Problem:**

M1 issue 1.2.3 defined the schema placeholder for `conversation.dead_lettered` mapped to `k1.internal.dead_letter.v1`. But no actual dead-letter infrastructure exists. There is no:

- Topic constant in `bus/topics.py`
- Builder in `bus/builders.py`
- Schema definition for the dead-letter payload
- No handler or consumer wired to the dead-letter topic

**What to do:**

1. Add topic constant to `bus/topics.py`:

   ```python
   TOPIC_DEAD_LETTER = "k1.internal.dead_letter.v1"
   ```

   Add to `INTERNAL_TOPICS` set (from M1 1.1.4 topic partition).

2. Add builder to `bus/builders.py`:

   ```python
   def build_dead_letter(*, payload: dict, parent_id: int = 0) -> Envelope:
       return _build(TOPIC_DEAD_LETTER, payload, parent_id=parent_id)
   ```

3. Define `DeadLetterPayload` schema (in `fsm/errors.py` or new `fsm/dead_letter.py`):

   ```python
   @dataclass
   class DeadLetterPayload:
       original_topic: str          # topic of the rejected envelope
       original_envelope_id: int    # envelope_id of the rejected event
       reason: str                  # "invalid_transition" | "orphan" | "expired" | "overflow"
       fsm_state_at_rejection: str  # ConciergeState name when rejection occurred
       turn_number: int             # Current turn number
       task_id: str                 # If applicable
       original_payload_summary: str # Truncated JSON of original payload (for debugging)
       rejected_at_ns: int          # Monotonic timestamp
   ```

4. Register in M1's topic partitions (`INTERNAL_TOPICS`).

**Files:**

- `poc/k1_poc/bus/topics.py` -- add constant
- `poc/k1_poc/bus/builders.py` -- add builder
- `poc/k1_poc/fsm/dead_letter.py` (new) -- `DeadLetterPayload` dataclass, `build_dead_letter_payload()` helper

**Acceptance:**

- `TOPIC_DEAD_LETTER` importable from `bus/topics.py`
- `build_dead_letter()` produces valid Envelope with correct topic
- `DeadLetterPayload` has all required fields
- Schema matches M1 1.2.3 specification: `original_event` (serialized), `reason`, `fsm_state_at_rejection`

---

#### 2.2.2 Route guard-rejected events to dead-letter stream

**Problem:**

Currently when an event arrives in an incompatible FSM state, the behavior varies by handler:

- `_on_task_failed` (line 1235): logs warning + queues in pending_results
- `_on_task_suspended` (line 1354): logs warning + returns (stores context but skips transition)
- `_on_user_input` during DISPATCHING (line 751): drops silently ("re-entrant, ignoring")
- Passthrough handlers: attempt delivery regardless of state (no guard at all)
- `_on_task_cancel` in incompatible state: delivers to Back but skips transition

None of these publish a dead-letter event. The rejection is invisible to observability.

**What to do:**

1. Add `_publish_dead_letter(self, envelope, reason)` to `ConciergeController`:

   ```python
   def _publish_dead_letter(self, envelope: Envelope, reason: str) -> None:
       if not get_config().fsm.dead_letter_enabled:
           return
       payload = DeadLetterPayload(
           original_topic=envelope.topic,
           original_envelope_id=envelope.envelope_id,
           reason=reason,
           fsm_state_at_rejection=self._state.name,
           turn_number=self._turn_number,
           task_id=_parse_payload(envelope).get("task_id", ""),
           original_payload_summary=str(envelope.payload)[:500],
           rejected_at_ns=time.monotonic_ns(),
       )
       self._bus.publish(build_dead_letter(
           payload=payload.to_dict(),
           parent_id=envelope.envelope_id,
       ))
       logger.warning(
           "DEAD-LETTER: topic=%s reason=%s state=%s envelope_id=%d",
           envelope.topic, reason, self._state.name, envelope.envelope_id,
       )
   ```

2. Wire into guard dispatch (from 2.1.2):
   - When `_guard_dispatch()` returns `DEAD_LETTER`, call `_publish_dead_letter(envelope, "invalid_transition")`.

3. Wire into existing silent-drop paths:
   - `_on_user_input` DISPATCHING drop (line 751) -> `_publish_dead_letter(envelope, "re_entrant_drop")`
   - `_on_task_cancel` in incompatible state -> `_publish_dead_letter(envelope, "cancel_incompatible_state")`

4. Add `fsm.dead_letter_enabled: true` to `config/defaults.yaml`.

**Files:**

- `poc/k1_poc/fsm/controller.py` -- add `_publish_dead_letter()`, wire into handlers
- `poc/k1_poc/config/defaults.yaml` -- add `dead_letter_enabled` flag

**Acceptance:**

- Every event rejected by guard publishes a dead-letter envelope to bus
- Dead-letter envelope contains: original topic, reason, FSM state, envelope ID
- Existing silent drops now produce dead-letter events
- Can be disabled via config flag (for test isolation)
- New test: force FSM to CLARIFYING_USER, send task.cancel -> dead-letter published

---

#### 2.2.3 Add pending_results TTL and max-depth overflow to dead-letter

**Problem:**

`FSMTurnState.pending_results` (turn_state.py) is an unbounded `deque[dict]`. Results can queue indefinitely if the FSM gets stuck or if `_on_response_final` never drains them. There is:

- No max depth limit (unlike FrontLock which has `max_queue_depth: 8`)
- No TTL check -- a result queued 10 minutes ago is treated the same as one queued 100ms ago
- No overflow protection -- memory grows without bound

Similarly, `PendingResultsQueue` in `weave_state.py` is an unbounded `list[PendingResult]` with no guards.

**What to do:**

1. Add config values to `config/defaults.yaml`:

   ```yaml
   fsm:
     pending_results_max_depth: 16
     pending_results_ttl_seconds: 300  # 5 minutes
   ```

2. Add depth guard to `FSMTurnState.enqueue_result()`:

   ```python
   if len(self.pending_results) >= self._max_depth:
       # Evict oldest result and dead-letter it
       evicted = self.pending_results.popleft()
       return evicted  # caller publishes dead-letter
   ```

3. Add TTL check to `FSMTurnState.drain_results()`:

   ```python
   now = time.monotonic_ns()
   ttl_ns = self._ttl_seconds * 1_000_000_000
   valid = [r for r in self.pending_results if now - r.get("queued_at_ns", 0) < ttl_ns]
   expired = [r for r in self.pending_results if now - r.get("queued_at_ns", 0) >= ttl_ns]
   # Return expired list for dead-letter publishing
   ```

4. Wire overflow/expiry into controller's dead-letter publish.

5. Apply same pattern to `PendingResultsQueue` in `weave_state.py`.

**Files:**

- `poc/k1_poc/fsm/turn_state.py` -- add max_depth, TTL check, return evicted/expired
- `poc/k1_poc/protocols/weave_state.py` -- add max_depth to `PendingResultsQueue`
- `poc/k1_poc/config/defaults.yaml` -- add depth/TTL config
- `poc/k1_poc/fsm/controller.py` -- wire eviction into dead-letter publish

**Acceptance:**

- `pending_results` rejects enqueue at `max_depth` and returns evicted result
- `drain_results()` filters expired results and returns them separately
- Dead-letter published for both overflow and TTL expiry
- Config-driven limits
- New test: enqueue 17 results with max_depth=16 -> oldest evicted -> dead-letter

---

#### 2.2.4 Build reconciliation consumer for dead-letter events

**Problem:**

Dead-letter events need a consumer that can:

- Log structured dead-letter entries for observability dashboards
- Track dead-letter rates per topic and per state (detect systematic routing problems)
- Optionally retry events that were transiently rejected (e.g., task.complete during DISPATCHING that should have been queued)

Currently no consumer exists. M2 defines the minimal viable consumer.

**What to do:**

1. Create `poc/k1_poc/fsm/dead_letter_consumer.py`:

   ```python
   class DeadLetterConsumer:
       """Subscribes to TOPIC_DEAD_LETTER and records events for observability."""
       def __init__(self, bus: IBus):
           self._bus = bus
           self._events: list[DeadLetterPayload] = []
           self._counts_by_reason: dict[str, int] = defaultdict(int)
           self._counts_by_state: dict[str, int] = defaultdict(int)
           self._handle = bus.subscribe(TOPIC_DEAD_LETTER, self._on_dead_letter)

       def _on_dead_letter(self, envelope: Envelope) -> None:
           payload = DeadLetterPayload.from_dict(json.loads(envelope.payload))
           self._events.append(payload)
           self._counts_by_reason[payload.reason] += 1
           self._counts_by_state[payload.fsm_state_at_rejection] += 1
           logger.warning("DeadLetterConsumer: %s", payload)

       @property
       def total_dead_letters(self) -> int: ...
       def get_events_by_reason(self, reason: str) -> list[DeadLetterPayload]: ...
       def snapshot(self) -> dict: ...
   ```

2. Wire into kernel bootstrap (optional for POC; mandatory for production).

3. For POC: consumer is instantiated in test fixtures and demo coordinator.

**Files:**

- `poc/k1_poc/fsm/dead_letter_consumer.py` (new) -- consumer class
- `poc/k1_poc/fsm/__init__.py` -- export consumer

**Acceptance:**

- Consumer subscribes to `TOPIC_DEAD_LETTER` and records all events
- `total_dead_letters` property returns count
- `get_events_by_reason()` filters by reason
- `snapshot()` returns summary dict for observability

---

#### 2.2.5 Add weave queue overflow guard with dead-letter fallback

**Problem:**

`WeaveBatcher._queued` (weave_batcher.py) is an unbounded `list[WeaveResult]`. If Front stays busy indefinitely (e.g., stuck LLM call), results accumulate without bound. Similarly, `_pending` has no limit.

`PendingResultsQueue` in `weave_state.py` has `_queue: list[PendingResult]` with no max size.

The `STATE_ACTION_TABLE` in `weave_state.py` maps all 11 states to actions, but has no fallback for when the chosen action (QUEUE) exceeds capacity.

**What to do:**

1. Add `max_queued_depth` to `WeaveBatcher`:

   ```python
   def __init__(self, ..., max_queued_depth: int | None = None):
       self._max_queued_depth = max_queued_depth or get_config().protocols.weave_max_queued_depth
   ```

2. In `on_task_complete()`, check depth before queuing:

   ```python
   if self._front_busy:
       if len(self._queued) >= self._max_queued_depth:
           # Dead-letter the oldest queued result
           evicted = self._queued.pop(0)
           logger.warning("WeaveBatcher overflow: dead-lettering task %s", evicted.task_id)
           return evicted  # caller publishes dead-letter
       self._queued.append(result)
   ```

3. Add `protocols.weave_max_queued_depth: 16` to `config/defaults.yaml`.

4. Add `DEAD_LETTER` action to `WeaveAction` enum for explicit dead-letter transitions:

   ```python
   class WeaveAction(str, Enum):
       IMMEDIATE = "immediate"
       QUEUE_WEAVE = "queue_weave"
       QUEUE = "queue"
       CHAIN = "chain"
       DEAD_LETTER = "dead_letter"  # NEW: explicit rejection
   ```

**Files:**

- `poc/k1_poc/protocols/weave_batcher.py` -- add overflow guard
- `poc/k1_poc/protocols/weave_state.py` -- add DEAD_LETTER to enum, add depth limit to PendingResultsQueue
- `poc/k1_poc/config/defaults.yaml` -- add `weave_max_queued_depth`

**Acceptance:**

- WeaveBatcher rejects at max depth and returns evicted result
- PendingResultsQueue has bounded depth
- Dead-letter event published for overflows
- Config-driven limit
- New test: queue 17 results with max_depth=16 -> overflow -> dead-letter

---

### E2.3 -- Response-Final Externalization

Source: WB 13.4, 13.5

| # | Issue | Source |
|---|-------|--------|
| 2.3.1 | Extract `_on_response_final` branching into explicit state/action decision table | WB 13.5 |
| 2.3.2 | Add ledger-backed idempotency keys for user input and task lifecycle transitions | WB 13.5 |
| 2.3.3 | Extract topic guard pattern to reusable decorator or helper | WB 13.4 (D2) |
| 2.3.4 | Extract `_finalize_turn` from repeated `emit_turn_completed + drain_front_lock_queue` combo | WB 13.4 (D3) |
| 2.3.5 | Fix `_seen_user_input_ids` unbounded dedup set to use LRU eviction | WB 13.4 |

---

#### 2.3.1 Extract `_on_response_final` branching into explicit state/action decision table

**Problem:**

`_on_response_final` (controller.py lines 1472-1689) is 217 lines with 8+ state-dependent branches. It is the single most complex method in the FSM. The branching logic:

| Current State | Condition | Action | Target State |
|---------------|-----------|--------|-------------|
| DISPATCHING | has_pending_results | weave flush | WEAVING |
| DISPATCHING | active_task_ids not empty | wait for tasks | COMPANIONING |
| DISPATCHING | no pending, no active | conversational-only turn done | LISTENING |
| DELIVERING | has_pending_results | weave transition | WEAVING |
| WEAVING | has_pending_results + no flush running | re-weave | WEAVING (self) |
| WEAVING | has_pending_results + flush running | skip (flush handles it) | WEAVING (stay) |
| DELIVERING | no pending | turn done | LISTENING |
| WEAVING | no pending | turn done | LISTENING |
| COMPANIONING | active_task_ids not empty | stay, wait for tasks | COMPANIONING (stay) |
| COMPANIONING | no active tasks | race-condition safe exit | LISTENING |
| CLARIFYING_WORKER | active_task_ids not empty | resume companion wait | COMPANIONING |
| CLARIFYING_WORKER | no active tasks | turn done | LISTENING |
| LISTENING | spurious final | ignore, no turn.completed | LISTENING (stay) |

Plus: history entry type resolution (4 branches: weave, proactive_fallback, proactive, final), history sink push, WeaveBatcher notification, FrontLock release strategy.

**What to do:**

1. Create `poc/k1_poc/fsm/response_final_table.py` (new file):

   ```python
   class ResponseFinalAction(str, Enum):
       TRANSITION_LISTENING = "transition_listening"
       TRANSITION_WEAVING = "transition_weaving"
       TRANSITION_COMPANIONING = "transition_companioning"
       STAY = "stay"                    # No state change
       IGNORE = "ignore"               # Spurious, do nothing
       DEAD_LETTER = "dead_letter"     # Incompatible state

   @dataclass
   class ResponseFinalDecision:
       action: ResponseFinalAction
       target_state: ConciergeState | None
       emit_turn_completed: bool
       drain_front_lock: bool
       schedule_weave: bool
       entry_type: str  # "final", "weave", "proactive", "proactive_fallback"

   def decide_response_final(
       fsm_state: ConciergeState,
       has_pending_results: bool,
       has_active_tasks: bool,
       is_fallback: bool,
       weave_flush_running: bool,
   ) -> ResponseFinalDecision:
       """Pure function: given FSM state + conditions, return the decision."""
   ```

2. Replace the 217-line `_on_response_final` method body with:

   ```python
   decision = decide_response_final(
       self._state, self._turn_state.has_pending_results,
       bool(self._active_task_ids), is_fallback,
       bool(self._weave_flush_task and not self._weave_flush_task.done()),
   )
   # Execute decision
   ```

3. The `decide_response_final()` function is a PURE FUNCTION with no side effects. It can be tested exhaustively in isolation with truth-table style tests.

**Files:**

- `poc/k1_poc/fsm/response_final_table.py` (new) -- action enum, decision dataclass, pure decision function
- `poc/k1_poc/fsm/controller.py` -- replace `_on_response_final` body with decision dispatch
- `poc/k1_poc/fsm/__init__.py` -- export new module

**Acceptance:**

- `decide_response_final()` is a pure function with zero side effects
- ALL 13 branches from the table above are covered by explicit `ResponseFinalDecision` entries
- `_on_response_final` body is under 60 lines (down from 217)
- All existing `TestOnResponseFinal` tests pass (8_2_29 through 8_2_32)
- New truth-table test covers all 13 decision paths

---

#### 2.3.2 Add ledger-backed idempotency keys for user input and task lifecycle transitions

**Problem:**

The FSM uses `_seen_user_input_ids` (a Python set, bounded at 200) to deduplicate user input. Task lifecycle transitions have no idempotency check -- if `task.complete` is delivered twice (e.g., bus retry), the FSM processes it twice.

Current dedup mechanisms:

- `_seen_user_input_ids` set (controller.py ~line 600): clears entirely at 200 entries
- `cancel_handler.is_cancelled()` for cancel dedup: works but is in-memory only
- No dedup for task.complete, task.failed, task.suspended, task.resume

**What to do:**

1. Create `poc/k1_poc/fsm/idempotency.py` (new file):

   ```python
   class IdempotencyLedger:
       """Tracks processed envelope IDs to prevent duplicate processing.

       Uses envelope_id as the idempotency key. Maintains a bounded
       LRU cache of recently processed IDs.
       """
       def __init__(self, max_entries: int = 500):
           self._processed: OrderedDict[int, int] = OrderedDict()  # envelope_id -> turn_number
           self._max_entries = max_entries

       def check_and_mark(self, envelope_id: int, turn_number: int) -> bool:
           """Returns True if this is a NEW event. False if duplicate."""
           if envelope_id in self._processed:
               return False  # duplicate
           self._processed[envelope_id] = turn_number
           if len(self._processed) > self._max_entries:
               self._processed.popitem(last=False)  # evict oldest
           return True
   ```

2. Replace `_seen_user_input_ids` set with `IdempotencyLedger` instance.

3. Add idempotency check to lifecycle handlers: `_on_task_complete`, `_on_task_failed`, `_on_task_suspended`, `_on_task_resume`.

4. Guard pattern in each handler:

   ```python
   if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
       logger.debug("Duplicate envelope_id=%d, skipping", envelope.envelope_id)
       return
   ```

**Files:**

- `poc/k1_poc/fsm/idempotency.py` (new) -- `IdempotencyLedger` class
- `poc/k1_poc/fsm/controller.py` -- replace `_seen_user_input_ids` with ledger, add to lifecycle handlers

**Acceptance:**

- `IdempotencyLedger` uses LRU eviction (not clear-all-at-N pattern)
- User input dedup still works (existing behavior preserved)
- Task lifecycle events are idempotent (duplicate envelope_id -> skip)
- `max_entries` is configurable
- New test: send same envelope twice -> second is silently skipped

---

#### 2.3.3 Extract topic guard pattern to reusable decorator or helper

**Problem (Duplication D2):**

The topic guard pattern is copy-pasted 4 times across handlers:

```python
# Pattern repeated at lines 586, 1073, 1306, 1478
if envelope.topic != TOPIC_EXPECTED:
    logger.debug(
        "FSM._on_<handler>: TOPIC GUARD -- ignoring topic=%s envelope_id=%d",
        envelope.topic,
        envelope.envelope_id,
    )
    return
```

The comment explains why: "TimingChain _cascade_causal can dispatch child envelopes through the parent's handler chain." This is a defense against the bus dispatching observability child events (like `state.updated.v1`) through the parent's handler.

**What to do:**

1. Extract to helper method:

   ```python
   def _topic_guard(self, envelope: Envelope, expected_topic: str) -> bool:
       """Return True if envelope matches expected topic. Log and return False otherwise."""
       if envelope.topic == expected_topic:
           return True
       logger.debug(
           "FSM topic guard: handler expects %s, got %s (envelope_id=%d)",
           expected_topic, envelope.topic, envelope.envelope_id,
       )
       return False
   ```

2. Replace all 4 guard blocks:

   ```python
   # Before (8 lines):
   if envelope.topic != TOPIC_USER_INPUT:
       logger.debug("FSM._on_user_input: TOPIC GUARD -- ...")
       return

   # After (2 lines):
   if not self._topic_guard(envelope, TOPIC_USER_INPUT):
       return
   ```

**Files:**

- `poc/k1_poc/fsm/controller.py` -- add `_topic_guard()`, replace 4 guard blocks

**Acceptance:**

- Zero copy-pasted topic guard blocks in controller.py
- `_topic_guard()` is a single method called from 4 handlers
- All existing tests pass (guard behavior unchanged)
- Log message is consistent across all handlers

---

#### 2.3.4 Extract `_finalize_turn` from repeated emit + drain combo

**Problem (Duplication D3):**

The `_emit_turn_completed(envelope)` + `_drain_front_lock_queue()` pair is called together 3 times (lines 1128-1129, 1581-1582, 1685-1689). They are ALWAYS called together, never independently.

**What to do:**

1. Extract to `_finalize_turn(self, envelope: Envelope) -> None`:

   ```python
   def _finalize_turn(self, envelope: Envelope) -> None:
       """Emit turn.completed and drain FrontLock queue. Always called together."""
       self._emit_turn_completed(envelope)
       self._drain_front_lock_queue()
   ```

2. Replace all 3 call sites:
   - `_on_task_complete` same-turn completion path (line 1128-1129)
   - `_on_response_final` DISPATCHING conversational-only path (lines 1581-1582)
   - `_on_response_final` end-of-method (lines 1685-1689)

**Files:**

- `poc/k1_poc/fsm/controller.py` -- add `_finalize_turn()`, replace 3 call sites

**Acceptance:**

- Zero bare `_emit_turn_completed + _drain_front_lock_queue` sequences
- `_finalize_turn` called from 3 locations
- All existing tests pass

---

#### 2.3.5 Fix `_seen_user_input_ids` unbounded dedup set to use LRU eviction

**Problem:**

`_seen_user_input_ids` (controller.py ~line 600) is a `set()` that clears entirely when it reaches 200 entries:

```python
if len(self._seen_user_input_ids) > 200:
    self._seen_user_input_ids.clear()
```

This is dangerous: immediately after clearing, ALL recent envelope IDs are forgotten, creating a window where duplicate events can be processed.

**What to do:**

This is RESOLVED by 2.3.2 (`IdempotencyLedger` with LRU eviction). The ledger evicts the OLDEST entry when at capacity, not all entries. This issue tracks the specific migration of `_seen_user_input_ids` to the new ledger.

1. Replace `self._seen_user_input_ids: set[int] = set()` with `self._idempotency = IdempotencyLedger(max_entries=500)`.
2. Replace `envelope.envelope_id in self._seen_user_input_ids` check with `self._idempotency.check_and_mark()`.
3. Remove the `if len(...) > 200: .clear()` block.

**Files:**

- `poc/k1_poc/fsm/controller.py` -- replace set with IdempotencyLedger

**Acceptance:**

- Zero `_seen_user_input_ids` references in controller.py
- Dedup uses LRU eviction, not clear-all
- No dedup window vulnerability after eviction
- `max_entries` configurable (default 500)

---

### E2.4 -- M2 Conformance Tests

Source: WB 13.6

| # | Issue | Source |
|---|-------|--------|
| 2.4.1 | Guard matrix completeness and handler agreement test | WB 13.6 |
| 2.4.2 | Dead-letter capture and reconciliation test | WB 12.5 |
| 2.4.3 | Response-final action table exhaustive truth-table test | WB 13.6 |
| 2.4.4 | Interrupt during PROGRESSING with simultaneous task completion | WB 13.6 |
| 2.4.5 | Cancel race: cancel -> late completion -> failed(cancelled) | WB 13.6 |
| 2.4.6 | Suspend in incompatible state -> deferred surfacing from LISTENING | WB 13.6 |
| 2.4.7 | Weave burst: 3 completions in window + user input | WB 13.6 |
| 2.4.8 | Pending results TTL expiry and overflow dead-letter test | WB 12.3 |

---

#### 2.4.1 Guard matrix completeness and handler agreement test

**Covered by 2.1.7.** This issue tracks the test implementation.

**Tests:**

- `test_2_4_1a_guard_table_11x19_complete`: Assert `FULL_GUARD_TABLE` has 209 cells (11 states x 19 topics).
- `test_2_4_1b_every_cell_has_valid_action`: Assert no `None` actions.
- `test_2_4_1c_handler_allows_match_table`: For each handler, the states where it processes events == the states where guard table says TRANSITION or PASSTHROUGH.
- `test_2_4_1d_dead_letter_default_for_unknown_topic`: `get_guard_action(LISTENING, "bogus.topic")` returns `(DEAD_LETTER, None)`.

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.2 Dead-letter capture and reconciliation test

**Tests:**

- `test_2_4_2a_invalid_transition_emits_dead_letter`: Force FSM to CLARIFYING_USER, send `task.cancel` -> dead-letter published with `reason="invalid_transition"`.
- `test_2_4_2b_dead_letter_consumer_records`: Wire `DeadLetterConsumer`, trigger dead-letter -> consumer has 1 event with correct metadata.
- `test_2_4_2c_pending_overflow_dead_letter`: Enqueue `max_depth + 1` results -> dead-letter published with `reason="overflow"`.
- `test_2_4_2d_pending_ttl_dead_letter`: Enqueue result, advance time past TTL, drain -> dead-letter published with `reason="expired"`.
- `test_2_4_2e_dead_letter_disabled_config`: Set `dead_letter_enabled=false`, trigger rejection -> no dead-letter published.

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.3 Response-final action table exhaustive truth-table test

**Tests:**

Test `decide_response_final()` pure function with all 13 decision paths:

| # | State | pending | active | fallback | flush_running | Expected Action | Expected Target |
|---|-------|---------|--------|----------|--------------|-----------------|-----------------|
| 1 | DISPATCHING | True | any | any | any | TRANSITION_WEAVING | WEAVING |
| 2 | DISPATCHING | False | True | any | any | TRANSITION_COMPANIONING | COMPANIONING |
| 3 | DISPATCHING | False | False | any | any | TRANSITION_LISTENING | LISTENING |
| 4 | DELIVERING | True | any | any | any | TRANSITION_WEAVING | WEAVING |
| 5 | WEAVING | True | any | any | False | TRANSITION_WEAVING | WEAVING |
| 6 | WEAVING | True | any | any | True | STAY | WEAVING |
| 7 | DELIVERING | False | any | any | any | TRANSITION_LISTENING | LISTENING |
| 8 | WEAVING | False | any | any | any | TRANSITION_LISTENING | LISTENING |
| 9 | COMPANIONING | any | True | any | any | STAY | COMPANIONING |
| 10 | COMPANIONING | any | False | any | any | TRANSITION_LISTENING | LISTENING |
| 11 | CLARIFYING_WORKER | any | True | any | any | TRANSITION_COMPANIONING | COMPANIONING |
| 12 | CLARIFYING_WORKER | any | False | any | any | TRANSITION_LISTENING | LISTENING |
| 13 | LISTENING | any | any | any | any | IGNORE | LISTENING |

Plus entry_type tests:

- WEAVING -> `entry_type = "weave"`
- DELIVERING + fallback -> `entry_type = "proactive_fallback"`
- DELIVERING + not fallback -> `entry_type = "proactive"`
- Any other -> `entry_type = "final"`

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.4 Interrupt during PROGRESSING with simultaneous task completion

**Scenario (WB 13.6 test 1):**

1. FSM in PROGRESSING (Back tool running)
2. `user.input` arrives -> interrupt classified -> INTERRUPT_HANDLING -> DISPATCHING
3. Simultaneously, `task.complete` arrives for the original task
4. Verify: task.complete is queued (not processed during DISPATCHING), no crash, no duplicate presentation

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.5 Cancel race: cancel -> late completion -> failed(cancelled)

**Scenario (WB 13.6 test 2):**

1. FSM in COMPANIONING, task T1 active
2. `task.cancel` -> CANCELLING (now via `_transition()`, not force-set)
3. `task.complete` arrives for T1 -> CANCELLED dedup -> discarded
4. `task.failed(reason=cancelled)` arrives -> DELIVERING -> confirm cancel
5. Verify: no duplicate presentation, cancel dedup works, dead-letter NOT emitted (completion correctly discarded)

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.6 Suspend in incompatible state -> deferred surfacing from LISTENING

**Scenario (WB 13.6 test 3):**

1. FSM in DISPATCHING (Front running Phase1)
2. `task.suspended` arrives -> state incompatible -> context stored, transition skipped
3. Front finishes -> `final.response` -> LISTENING
4. `_surface_deferred_hitl` fires -> CLARIFYING_WORKER -> HITL presented
5. Verify: suspension context preserved, deferred surfacing happens automatically, no dead-letter (intentional defer, not rejection)

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.7 Weave burst: 3 completions in window + user input

**Scenario (WB 13.6 test 4):**

1. FSM in COMPANIONING, 3 tasks active
2. Task T1 completes -> DELIVERING, deliver to Front
3. Task T2 completes while Front busy -> queued in pending_results
4. Task T3 completes while Front busy -> queued in pending_results
5. `user.input` arrives during DELIVERING -> queued in FrontLock (PRIORITY_URGENT)
6. Front finishes T1 -> `final.response` -> WEAVING (pending_results not empty)
7. Weave flush drains T2+T3, delivers to Front
8. Front finishes weave -> `final.response` -> LISTENING
9. FrontLock drain -> queued user.input delivered -> new turn starts
10. Verify: all 3 completions presented, user input not lost, turn numbers correct

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

#### 2.4.8 Pending results TTL expiry and overflow dead-letter test

**Tests:**

- `test_2_4_8a_overflow_eviction`: 17 results with max_depth=16 -> oldest evicted, dead-letter with reason="overflow"
- `test_2_4_8b_ttl_expiry`: Queue result, advance monotonic clock past TTL, drain -> expired result returned, dead-letter with reason="expired"
- `test_2_4_8c_weave_batcher_overflow`: Queue 17 WeaveResults with max_depth=16 -> oldest evicted, dead-letter

**Files:** `tests/poc/test_m08_fsm_controller.py`

---

### M2 Issue Summary

| Epic | # | Title | Depends On |
|------|---|-------|-----------|
| E2.1 | 2.1.1 | Expand TRANSITION_TABLE to full guard matrix | M1 (canonical topics) |
| E2.1 | 2.1.2 | Introduce handler guard middleware | 2.1.1 |
| E2.1 | 2.1.3 | Replace forced CANCELLING shortcut | 2.1.1 |
| E2.1 | 2.1.4 | Extract interrupt handler duplication | -- |
| E2.1 | 2.1.5 | Remove duplicate dag.completed subscription | M1 (canonical topics) |
| E2.1 | 2.1.6 | Replace hardcoded strings in FrontLock and controller | M0 0.2.3 pattern |
| E2.1 | 2.1.7 | Guard matrix completeness conformance test | 2.1.1 |
| E2.2 | 2.2.1 | Define dead-letter envelope schema and topic | M1 1.2.3 |
| E2.2 | 2.2.2 | Route guard-rejected events to dead-letter | 2.1.2, 2.2.1 |
| E2.2 | 2.2.3 | Pending results TTL and max-depth overflow | 2.2.1 |
| E2.2 | 2.2.4 | Build reconciliation consumer | 2.2.1 |
| E2.2 | 2.2.5 | Weave queue overflow guard | 2.2.1 |
| E2.3 | 2.3.1 | Extract response-final decision table | 2.1.1 |
| E2.3 | 2.3.2 | Ledger-backed idempotency keys | -- |
| E2.3 | 2.3.3 | Extract topic guard to helper | -- |
| E2.3 | 2.3.4 | Extract _finalize_turn combo | -- |
| E2.3 | 2.3.5 | Fix dedup set LRU eviction | 2.3.2 |
| E2.4 | 2.4.1 | Guard matrix completeness test | 2.1.1 |
| E2.4 | 2.4.2 | Dead-letter capture test | 2.2.1, 2.2.2 |
| E2.4 | 2.4.3 | Response-final truth-table test | 2.3.1 |
| E2.4 | 2.4.4 | Interrupt + simultaneous completion test | 2.1.4 |
| E2.4 | 2.4.5 | Cancel race test | 2.1.3 |
| E2.4 | 2.4.6 | Deferred HITL surfacing test | -- |
| E2.4 | 2.4.7 | Weave burst + user input test | 2.2.5 |
| E2.4 | 2.4.8 | Pending results TTL/overflow test | 2.2.3 |

**Total: 25 issues across 4 epics (E2.1-E2.4) + 8 issues in E2.5 wiring = 33 issues across 5 epics.**

**Implementation order:**

1. 2.1.4, 2.1.5, 2.1.6, 2.3.3, 2.3.4, 2.3.5 (standalone cleanup, no dependencies)
2. 2.1.1 (guard table expansion -- foundation for all guard work)
3. 2.1.2, 2.1.3 (handler middleware + CANCELLING fix, depend on 2.1.1)
4. 2.1.7 (conformance test for guard table)
5. 2.2.1 (dead-letter schema)
6. 2.2.2, 2.2.3, 2.2.5 (dead-letter routing)
7. 2.2.4 (reconciliation consumer)
8. 2.3.1 (response-final externalization)
9. 2.3.2 (idempotency ledger)
10. 2.4.* (conformance tests)
11. 2.5.* (end-to-end wiring -- MUST be last, depends on all above)

---

### E2.5 -- End-to-End Wiring & System Integration

**Why this epic exists:** E2.1-E2.4 create new FSM guard infrastructure (guard table, dead-letter pipeline, response-final decision table, idempotency ledger, extracted helpers) but these are INTERNAL to the FSM module. They must be wired into the live system that M1 left behind. M1 gave us: a running ledger, canonical events flowing through builders, `_ledger_append()` on every mutation, a `_try_deserialize()` bridge, demo health checks, and test fixtures. M2's artifacts must plug into ALL of those M1 touchpoints or the two milestones exist as parallel universes that never connect.

**System state after M1 (E1.4 wiring complete) -- what M2 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created
  -> LedgerMiddleware appended to bus middleware chain
  -> ConciergeController(bus, router)
     -> set_ledger(writer)           # M1 1.4.1 -- ledger wired
     -> _ledger_append() in 11 handlers  # M1 1.4.2 -- canonical events recorded
     -> _try_deserialize() bridge    # M1 1.4.3 -- dual-mode payload parsing
  -> builders auto-enrich legacy dicts with event_id/ts_utc  # M1 1.4.5
  -> demo coordinator has ledger health check  # M1 1.4.6
  -> test fixtures: create_wired_fsm(with_ledger=True)  # M1 1.4.7
```

**M2 artifacts that must integrate into this M1-wired system:**

| M2 Artifact | Where It Lives After E2.1-E2.4 | M1 Touchpoint It Must Connect To |
|-------------|-------------------------------|----------------------------------|
| `FULL_GUARD_TABLE` + `get_guard_action()` | `transition_table.py` | M1 `_ledger_append()` -- guard rejections must also record to ledger |
| `_guard_dispatch()` + `_publish_dead_letter()` | `controller.py` | M1 LedgerWriter -- dead-letter events must be ledger-recorded |
| `DeadLetterPayload` + `build_dead_letter()` | `dead_letter.py` + `builders.py` | M1 canonical event base -- dead-letter must extend `CanonicalEventMeta` |
| `DeadLetterConsumer` | `dead_letter_consumer.py` | M1 `start_kernel()` -- consumer must be created at boot |
| `decide_response_final()` | `response_final_table.py` | M1 ledger -- response-final decisions must be ledger-auditable |
| `IdempotencyLedger` | `idempotency.py` | M1 LedgerWriter -- dedup decisions should be correlated with ledger events |
| Pending results TTL/overflow | `turn_state.py` | M1 `_ledger_append()` -- evictions must record to ledger |
| Weave overflow | `weave_batcher.py`, `weave_state.py` | M1 `_ledger_append()` -- weave overflow must record to ledger |

---

#### 2.5.1 -- Wire DeadLetterConsumer into kernel bootstrap

**Problem:** E2.2.4 creates `DeadLetterConsumer` as a standalone class that subscribes to `TOPIC_DEAD_LETTER`. But `kernel/bootstrap.py::start_kernel()` has no concept of it. After M2, dead-letter events are published to the bus but nobody is listening unless the consumer is instantiated at boot.

**Post-M1 bootstrap creates:** bus, router, adapter, mailboxes, model, session_state, ledger, FSM, dispatchers, experience, delta, HITL coordinator, weave batcher, orchestrator. No dead-letter consumer.

**Action:**

1. Add `enable_dead_letter_consumer: bool = True` to `KernelConfig`.
2. Add `dead_letter_consumer: Any = None` to `KernelRuntime`.
3. In `start_kernel()`, after FSM creation and guard table wiring:

   ```python
   if cfg.enable_dead_letter_consumer and get_config().fsm.dead_letter_enabled:
       from poc.k1_poc.fsm.dead_letter_consumer import DeadLetterConsumer
       runtime.dead_letter_consumer = DeadLetterConsumer(bus=bus)
       logger.info("DeadLetterConsumer attached to bus")
   ```

4. In `stop_kernel()`, log dead-letter summary:

   ```python
   if runtime.dead_letter_consumer is not None:
       summary = runtime.dead_letter_consumer.snapshot()
       if summary.get("total", 0) > 0:
           logger.warning("Session dead-letter summary: %s", summary)
   ```

**Files to modify:**

- `poc/k1_poc/kernel/bootstrap.py` (KernelConfig, KernelRuntime, start_kernel, stop_kernel)

**Dependency:** E2.2.4 (DeadLetterConsumer exists), M1 1.4.1 (bootstrap pattern established)

---

#### 2.5.2 -- Wire dead-letter events into M1 ledger

**Problem:** M1's `_ledger_append()` records canonical domain events (task.completed, user_input.received, etc.) in the 11 FSM mutation handlers. M2 introduces dead-letter events published via `_publish_dead_letter()`. These dead-letter events are published to the bus but are NOT recorded in the ledger. This means:

- Ledger replay (M1 1.2.4) will not see rejected events
- M9 crash recovery will not know about events that were dead-lettered
- M11 observability metrics cannot count dead-letters from ledger reads

The `DeadLetterPayload` from E2.2.1 is a standalone dataclass, NOT extending `CanonicalEventMeta`. It must either extend it or have a bridge.

**Action:**

1. Make `DeadLetterPayload` extend `CanonicalEventMeta` (from M1 1.1.1). Add canonical metadata fields: `event_id`, `event_type="conversation.dead_lettered"`, `session_id`, `correlation_id`, `causation_id` (the original envelope's envelope_id), `actor="fsm"`, `ts_utc`, `payload_schema_version`.

2. In `_publish_dead_letter()` (from E2.2.2), add ledger append BEFORE bus publish:

   ```python
   def _publish_dead_letter(self, envelope: Envelope, reason: str) -> None:
       payload = DeadLetterPayload(
           # ... existing fields ...
           # Plus canonical metadata from_envelope():
           **from_envelope(envelope, actor="fsm", causation_id=str(envelope.envelope_id))
       )
       # Record in ledger (M1 infrastructure):
       self._ledger_append(payload)
       # Then publish to bus (existing M2 logic):
       self._bus.publish(build_dead_letter(payload=payload.to_dict(), ...))
   ```

3. Update M1's `events/registry.py` to register `DeadLetterPayload` as a canonical event type so `deserialize_envelope()` can reconstruct it.

4. Update M1's `ledger/projections.py` to add `project_dead_letters(events) -> list[DeadLetterPayload]` -- materializes all dead-letter events from the ledger stream.

**Files to modify:**

- `poc/k1_poc/fsm/dead_letter.py` (extend CanonicalEventMeta)
- `poc/k1_poc/fsm/controller.py` (_publish_dead_letter adds ledger append)
- `poc/k1_poc/events/registry.py` (register DeadLetterPayload)
- `poc/k1_poc/ledger/projections.py` (add project_dead_letters)

**Dependency:** M1 1.4.2 (_ledger_append exists), M1 1.1.2 (DeadLettered schema defined), E2.2.1-2.2.2 (dead-letter infrastructure)

---

#### 2.5.3 -- Wire guard table into M1's _try_deserialize and _ledger_append flow

**Problem:** M1's FSM handler flow is:

```
envelope arrives -> _parse_payload() -> _try_deserialize() -> _ledger_append(canonical_event) -> in-memory mutation
```

M2 inserts guard dispatch at the TOP:

```
envelope arrives -> _guard_dispatch() -> [DEAD_LETTER | PASSTHROUGH | TRANSITION] -> handler body
```

These two flows must be sequenced correctly. If `_guard_dispatch()` fires BEFORE `_try_deserialize()`, the dead-letter path cannot construct a canonical event (it only has raw envelope). If `_guard_dispatch()` fires AFTER `_ledger_append()`, rejected events are already in the ledger (wrong -- they should NOT be in the domain ledger, only the dead-letter stream).

**Correct combined flow:**

```
1. envelope arrives
2. _guard_dispatch(envelope) -> action
3. IF action == DEAD_LETTER:
     _publish_dead_letter(envelope, reason)  # records in ledger as DeadLettered event
     return
4. IF action == OBSERVE:
     _try_deserialize(envelope)  # optional, for observability enrichment
     handler body (log/history only, no state mutation)
     return
5. IF action == PASSTHROUGH:
     handler body (forward to mailbox, no state change)
     return
6. IF action == TRANSITION:
     canonical = _try_deserialize(envelope)  # typed event or None
     handler body:
       construct canonical event (using canonical or raw dict)
       _ledger_append(canonical_event)  # domain event in ledger
       in-memory mutation
       _transition(target_state, ...)
```

**Action:**

1. Refactor the combined flow in `ConciergeController` into a `_dispatch_envelope(self, envelope, handler_fn)` orchestrator method:

   ```python
   def _dispatch_envelope(self, envelope: Envelope, expected_topic: str, handler_fn: Callable) -> None:
       # Step 1: Topic guard (M2 2.3.3)
       if not self._topic_guard(envelope, expected_topic):
           return
       # Step 2: Idempotency check (M2 2.3.2)
       if not self._idempotency.check_and_mark(envelope.envelope_id, self._turn_number):
           return
       # Step 3: Guard dispatch (M2 2.1.2)
       action = self._guard_dispatch(envelope)
       if action == GuardAction.DEAD_LETTER:
           self._publish_dead_letter(envelope, "invalid_transition")
           return
       # Step 4: Handler body (includes M1 _ledger_append)
       handler_fn(envelope, action)
   ```

2. Each handler is refactored from `_on_X(self, envelope)` to `_handle_X(self, envelope, action)` which is called by `_dispatch_envelope`. The subscription still points to `_on_X`, but `_on_X` becomes a one-liner:

   ```python
   def _on_task_complete(self, envelope: Envelope) -> None:
       self._dispatch_envelope(envelope, TOPIC_TASK_COMPLETE, self._handle_task_complete)
   ```

3. This ensures the flow is: topic guard -> idempotency -> guard table -> handler (with ledger append inside).

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (add _dispatch_envelope, refactor all _on_* methods)

**Dependency:** M1 1.4.2-1.4.3 (ledger/deserialize in handlers), E2.1.2 (_guard_dispatch), E2.3.2 (IdempotencyLedger), E2.3.3 (_topic_guard)

---

#### 2.5.4 -- Wire response-final decision table into ledger audit trail

**Problem:** E2.3.1 extracts `decide_response_final()` as a pure function returning `ResponseFinalDecision`. This decision determines the FSM's next state, whether to emit turn.completed, whether to schedule a weave, etc. But the decision itself is NOT recorded anywhere. For M9 crash recovery (ledger replay), M11 observability (response-final analytics), and debugging (why did the FSM go to WEAVING instead of LISTENING?), the decision must be auditable.

**Action:**

1. Create a `ResponseFinalEvent` canonical event extending `CanonicalEventMeta`:

   ```python
   @dataclass
   class ResponseFinalEvent(CanonicalEventMeta):
       event_type: str = "conversation.response_final.decided"
       decision_action: str = ""         # ResponseFinalAction value
       target_state: str = ""            # ConciergeState name
       has_pending_results: bool = False
       has_active_tasks: bool = False
       emit_turn_completed: bool = False
       schedule_weave: bool = False
       entry_type: str = ""              # "final", "weave", "proactive", "proactive_fallback"
   ```

2. In the refactored `_on_response_final` (after E2.3.1), after calling `decide_response_final()`, record the decision:

   ```python
   decision = decide_response_final(self._state, ...)
   event = ResponseFinalEvent(
       decision_action=decision.action.value,
       target_state=decision.target_state.name if decision.target_state else "",
       has_pending_results=has_pending,
       has_active_tasks=bool(self._active_task_ids),
       emit_turn_completed=decision.emit_turn_completed,
       schedule_weave=decision.schedule_weave,
       entry_type=decision.entry_type,
       **from_envelope(envelope, actor="fsm"),
   )
   self._ledger_append(event)
   # Then execute the decision...
   ```

3. Register `ResponseFinalEvent` in M1's event registry.

**Files to create:**

- Add `ResponseFinalEvent` to `poc/k1_poc/events/conversation.py` (or new `events/fsm.py`)

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (_on_response_final records decision)
- `poc/k1_poc/events/registry.py` (register ResponseFinalEvent)

**Dependency:** E2.3.1 (decide_response_final exists), M1 1.4.2 (_ledger_append exists)

---

#### 2.5.5 -- Wire dead-letter and overflow events into demo coordinator and health check

**Problem:** M1's E1.4.6 added ledger health check and `/api/ledger/stats` to the demo coordinator. M2 adds dead-letter events and overflow/TTL evictions that are critical for system health monitoring. The demo web app has no visibility into dead-letter rates.

**Action:**

1. Add `self.dead_letter_consumer: Any = None` to `K1DemoCoordinator.__init__()`.

2. In Phase 2 (`_phase2_kernel_startup`), copy the dead-letter consumer reference:

   ```python
   self.dead_letter_consumer = self._kernel.dead_letter_consumer
   self._record("phase2", "dead_letter", "dead_letter.attached",
                 "DeadLetterConsumer attached" if self.dead_letter_consumer else "Dead-letter disabled")
   ```

3. Extend Phase 5 health check to verify dead-letter pipeline:

   ```python
   if self.dead_letter_consumer is not None:
       # Verify consumer is subscribed and operational
       assert hasattr(self.dead_letter_consumer, 'total_dead_letters')
       self._record("phase5", "dead_letter", "dead_letter.health_ok",
                     f"DeadLetterConsumer operational (count={self.dead_letter_consumer.total_dead_letters})")
   ```

4. Add `/api/dead-letters` endpoint to the web app:

   ```python
   @app.get("/api/dead-letters")
   async def get_dead_letters() -> dict:
       if _coordinator is None or _coordinator.dead_letter_consumer is None:
           return {"enabled": False}
       consumer = _coordinator.dead_letter_consumer
       return {
           "enabled": True,
           "total": consumer.total_dead_letters,
           "by_reason": dict(consumer._counts_by_reason),
           "by_state": dict(consumer._counts_by_state),
           "recent": [e.to_dict() for e in consumer._events[-10:]],
       }
   ```

5. Extend `/api/ledger/stats` (from M1 1.4.6) to include dead-letter count:

   ```python
   return {
       "enabled": True,
       "total_events": store.count(),
       "dead_letter_events": store.count_by_type("conversation.dead_lettered"),
       "store_type": type(store).__name__,
   }
   ```

**Files to modify:**

- `poc/k1_poc/demo/coordinator.py` (init, phase2, phase5)
- `poc/k1_poc/demo/web/app.py` (add `/api/dead-letters`, extend `/api/ledger/stats`)

**Dependency:** 2.5.1 (bootstrap creates consumer), M1 1.4.6 (demo health check pattern)

---

#### 2.5.6 -- Wire M2 artifacts into M1 test fixtures

**Problem:** M1's E1.4.7 created test fixtures: `create_wired_fsm(with_ledger=True)` and `create_test_ledger()`. M2 adds guard table, dead-letter consumer, idempotency ledger, and response-final decision table. The test fixtures must be updated so M2 tests (E2.4) and all downstream milestone tests get a fully wired FSM with both M1 AND M2 infrastructure.

**Action:**

1. Extend `create_wired_fsm()` in `testing/fixtures.py`:

   ```python
   def create_wired_fsm(
       *,
       capture: bool = True,
       with_ledger: bool = True,
       with_dead_letter_consumer: bool = True,
   ) -> dict:
       bus = create_poc_bus(capture=capture)
       router = create_poc_router()
       fsm = ConciergeController(bus=bus, router=router)
       result = {"bus": bus, "router": router, "fsm": fsm}

       if with_ledger:
           writer, store = create_test_ledger()
           fsm.set_ledger(writer)
           result["ledger"] = writer
           result["ledger_store"] = store

       if with_dead_letter_consumer:
           from poc.k1_poc.fsm.dead_letter_consumer import DeadLetterConsumer
           consumer = DeadLetterConsumer(bus=bus)
           result["dead_letter_consumer"] = consumer

       return result
   ```

2. Add dead-letter assertion helper:

   ```python
   def assert_dead_letter_count(consumer: DeadLetterConsumer, expected: int) -> None:
       actual = consumer.total_dead_letters
       assert actual == expected, f"Expected {expected} dead-letters, got {actual}"

   def assert_dead_letter_reason(consumer: DeadLetterConsumer, reason: str, count: int = 1) -> None:
       events = consumer.get_events_by_reason(reason)
       assert len(events) == count, f"Expected {count} dead-letters with reason={reason}, got {len(events)}"
   ```

3. Add guard table assertion helpers:

   ```python
   def assert_guard_action(state: ConciergeState, topic: str, expected: GuardAction) -> None:
       action, _ = get_guard_action(state, topic)
       assert action == expected, f"Guard({state.name}, {topic}) = {action}, expected {expected}"
   ```

4. Update `conftest.py` fixtures to include dead-letter consumer.

**Files to modify:**

- `poc/k1_poc/testing/fixtures.py` (extend create_wired_fsm, add assertion helpers)
- `tests/poc/conftest.py` (update fixtures)

**Dependency:** M1 1.4.7 (fixtures exist), E2.2.4 (DeadLetterConsumer), E2.1.1 (guard table)

---

#### 2.5.7 -- Backward compatibility: verify M1 ledger integration survives M2 refactoring

**Problem:** M2 significantly refactors `controller.py` -- extracting helpers, adding guard dispatch, replacing inline state checks, refactoring `_on_response_final`. Every one of these changes touches code paths where M1's `_ledger_append()` calls live. If M2 refactoring accidentally removes or reorders a `_ledger_append()` call, the ledger silently stops recording events and M9/M11/M12 break.

**Action:**

1. Create `tests/poc/test_m02_ledger_survival.py` that verifies M1's ledger recording survives M2's refactoring:

   **Test matrix (one test per M1 mutation point):**

   | Test | Trigger | Expected Ledger Event | M2 Code Path That Could Break It |
   |------|---------|----------------------|-----------------------------------|
   | `test_user_input_still_ledgered` | Send user.input in LISTENING | `UserInputReceived` in ledger | 2.5.3 _dispatch_envelope refactor |
   | `test_task_dispatch_still_ledgered` | Phase1 dispatches task | `TaskCreated` in ledger | 2.5.3 _dispatch_envelope refactor |
   | `test_task_complete_still_ledgered` | task.complete arrives | `TaskCompleted` in ledger | 2.1.2 guard middleware insertion |
   | `test_task_failed_still_ledgered` | task.failed arrives | `TaskFailed` in ledger | 2.1.2 guard middleware insertion |
   | `test_task_cancel_still_ledgered` | task.cancel arrives | `TaskCancelled` in ledger | 2.1.3 CANCELLING transition fix |
   | `test_task_suspended_still_ledgered` | task.suspended arrives | `TaskSuspended` in ledger | 2.1.2 guard middleware insertion |
   | `test_response_final_still_ledgered` | response.final arrives | `WeaveEmitted` in ledger | 2.3.1 response-final externalization |
   | `test_dead_letter_also_ledgered` | invalid event -> dead-letter | `DeadLettered` in ledger | 2.5.2 dead-letter ledger integration |

2. Each test:
   - Creates a wired FSM (with ledger + dead-letter consumer) via `create_wired_fsm()`
   - Drives through the trigger scenario
   - Asserts the expected event type appears in `ledger_store.read_by_type()`
   - Asserts no unexpected dead-letters (unless testing dead-letter path)

3. This test file is the M1<->M2 contract enforcer. If any future M2 change breaks ledger recording, this file catches it immediately.

**Files to create:**

- `tests/poc/test_m02_ledger_survival.py`

**Dependency:** M1 1.4.7 (test fixtures), 2.5.2 (dead-letter in ledger), 2.5.3 (dispatch flow)

---

#### 2.5.8 -- Full regression: demo web app smoke test with guard table + dead-letter active

**Problem:** M2 changes the core FSM dispatch path. The demo web app (`demo/web/app.py`) is the user-facing integration surface. If guard table dispatch introduces any regression (e.g., a PASSTHROUGH topic that should have been TRANSITION, or a dead-letter that should have been processed), the demo breaks.

**Action:**

1. Create `tests/poc/test_m02_demo_smoke.py`:

   **Scenario A: Happy path with guard table active**
   - Boot kernel via `start_kernel()` with default config
   - Send "What's on the agenda today?" as user input envelope
   - Verify FSM transitions through: LISTENING -> PHASE1_CLASSIFY -> DISPATCHING -> ...
   - Verify zero dead-letters in consumer
   - Verify ledger has: UserInputReceived, TaskCreated, TaskCompleted, WeaveEmitted (or ResponseFinalEvent)
   - Verify `/api/status` returns system_ready=True
   - Verify `/api/dead-letters` returns total=0

   **Scenario B: Invalid event triggers dead-letter**
   - Boot kernel
   - Manually publish `task.cancel` while FSM in LISTENING (incompatible state)
   - Verify dead-letter consumer has 1 event with reason="invalid_transition"
   - Verify `/api/dead-letters` returns total=1
   - Verify FSM is still in LISTENING (not corrupted)
   - Send normal user input -> still works correctly

   **Scenario C: Guard table does not regress M1 ledger health check**
   - Boot kernel
   - Verify `/api/ledger/stats` returns enabled=True, total_events > 0 (boot event from health check)
   - Send user input -> verify total_events increases

2. These are integration-level tests that exercise the full stack: bootstrap -> bus -> FSM -> guard table -> dead-letter -> ledger -> demo endpoints.

**Files to create:**

- `tests/poc/test_m02_demo_smoke.py`

**Dependency:** 2.5.1 (bootstrap wires consumer), 2.5.5 (demo endpoints), M1 1.4.6 (demo health check)

**Acceptance criteria for ALL of E2.5:**

- Dead-letter consumer is live at boot (not just importable)
- Dead-letter events appear in both the bus AND the ledger
- Guard dispatch -> idempotency -> ledger append flow is correctly sequenced
- Response-final decisions are ledger-auditable
- Demo web app has `/api/dead-letters` endpoint
- All M1 ledger recording survives M2 refactoring (test_m02_ledger_survival.py)
- Full demo smoke test passes with zero regressions
- Zero dead-letters in happy-path scenarios
- Dead-letters fire correctly in invalid-state scenarios

---

### M2 Touchpoint Matrix: What M3-M12 Inherit from M2

| Milestone | M2 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M3** (Actor Hardening) | `FULL_GUARD_TABLE`, `_dispatch_envelope()` | Back mailbox topic router uses guard table pattern. New back-bound topics added to guard table. |
| **M4** (SessionState) | `IdempotencyLedger` | SS write path uses idempotency pattern for delta dedup. |
| **M5** (Arbiter) | `FULL_GUARD_TABLE`, `_guard_dispatch()`, dead-letter pipeline | Arbiter output topic added to guard table. Arbiter misrouting -> dead-letter. Multi-device conflict events use guard table for state validation. |
| **M6** (HITL V3) | `_dispatch_envelope()` flow, dead-letter pipeline | HITL timeout events flow through guard dispatch. Orphan HITL responses (after task cancel) -> dead-letter instead of silent drop. |
| **M7** (BackPool) | `FULL_GUARD_TABLE`, dead-letter | Task lease events added to guard table. Expired lease -> dead-letter. |
| **M8** (Weave Policy) | `decide_response_final()`, weave overflow guards | Adaptive weave policy reads response-final decision table. Overflow guards from E2.2.5 feed into weave policy pressure signals. |
| **M9** (Ledger Migration) | `IdempotencyLedger`, dead-letter projections, `ResponseFinalEvent` | Crash recovery uses idempotency ledger to skip already-processed events. Dead-letter projection shows system health. Response-final events enable accurate state reconstruction. |
| **M10** (UltraBERT) | `_dispatch_envelope()` flow | Phase1 classify results flow through guard dispatch. |
| **M11** (Observability) | Dead-letter consumer metrics, `ResponseFinalEvent`, guard action counts | Alert rules evaluate dead-letter rates. Metrics collector counts guard actions per state. Response-final decision distribution tracked. |
| **M12** (Chaos Tests) | ALL M2 artifacts | Chaos tests verify guard table under concurrent load. Dead-letter consumer validates no events silently dropped. Race conditions tested against idempotency ledger. |

---

## M3: Actor & React Runtime Fixes

**Goal:** Wire missing runtime paths (resume, cancel, back routing). Make
cancellation mandatory. Resolve parallel tool execution policy. Remove
duplicate resume designs.

**Gate:** Back mailbox has explicit topic router. Cancellation token propagates
end-to-end (FSM -> envelope -> back loop). Single resume-context contract.
Parallel tool policy documented and enforced.

### M3 Context Table

| File | Lines | Current State | M3 Changes |
|------|-------|---------------|------------|
| `poc/k1_poc/actors/back.py` | 951 | `back_handler` (L339-477), `back_resume_handler` (L499-656), `back_cancel_handler` (L664-700), `store_pending_context` (L709-744), `_get_pending_context` (L935-940), `_clear_pending_context` (L943-948), `subscribe_back_events` (L752-793), `_build_cancellation_check` (L916-928), `_never_cancel` (L931-933) | E3.1: route by topic. E3.2: make `fsm_state` non-optional. E3.3: remove back-side pending_context helpers |
| `poc/k1_poc/actors/front.py` | 946 | `front_handler` (L426-766), `_parse_payload` (L59-67), `_safe_get_section` (L321-326), `_never_cancel` (L943-945), emission order enforced at L671-741 | E3.1: no change (reference for conformance). Duplication source for D1-D3 |
| `poc/k1_poc/react/loop.py` | 562 | `react_loop` (L216-562), parallel `asyncio.gather` at L492-497, `MODE_MAX_ITERATIONS` (L52-63), `CRISIS_MAX_ITERATIONS` (L65-77), `cancellation_check` called at L237, `_resolve_tool_choice` (L112-123) | E3.4: add parallel safety gate before gather. D4: stale iteration constants |
| `poc/k1_poc/react/history.py` | 91 | `build_chat_history` (L24-60), `build_chat_history_for_back` (L63-91) | No changes required |
| `poc/k1_poc/demo/coordinator.py` | 1175 | `_mailbox_consumer` (L618-809), `_run_back_handler` (L884-920). Consumer calls `back_handler` for ALL back envelopes at L907, no topic routing. `fsm_state` never passed to `back_handler` at L907 | E3.1: add topic router in consumer. E3.2: pass `fsm_state` to back handlers |
| `poc/k1_poc/kernel/bootstrap.py` | 841 | `_mailbox_consumer` (L295-388), calls `back_handler` for all back envelopes at L370-376, no topic routing. `fsm_state` never passed. Comment at L262: "Do NOT call subscribe_back_events" | E3.1: add topic router. E3.2: pass `fsm_state` |
| `poc/k1_poc/task/parallel_safety.py` | 100 | `PARALLEL_SAFE_GROUPS` (L35-43), `ALWAYS_SEQUENTIAL` (L49-56), `is_parallel_safe` (L59-67), `classify_tool_batch` (L70-98). Module docstring L7: "POC react loop is SEQUENTIAL" -- this is FALSE | E3.4: align docstring to reality, integrate into react_loop |
| `poc/k1_poc/protocols/cancellation.py` | 155 | `CancellationToken` (L61-142), `TaskCancelledError` (L145-155). Clean design, but NEVER instantiated by FSM or coordinator. `back_handler` uses ad-hoc `fsm_state.cancellation_requested` bool instead | E3.2: replace ad-hoc bool with CancellationToken |
| `poc/k1_poc/protocols/suspension.py` | 186 | `SuspensionRequest` (L67-140), `SuspensionResolution` (L143-166). Clean protocol. | E3.3: becomes canonical resume carrier |
| `poc/k1_poc/protocols/suspension_manager.py` | 266 | `SuspensionManager._active` (async path), `SuspensionManager._contexts` (sync path). `store_context`/`pop_context` at L221-248 used by FSM controller. Separate from `back.py` `store_pending_context`/`_get_pending_context` | E3.3: unify to single path |

### M3 Duplication Inventory

| ID | What | Location A | Location B | Risk |
|----|------|-----------|-----------|------|
| D1 | `_parse_payload(envelope)` -- identical 8-line JSON parser | `actors/front.py` L59-67 | `actors/back.py` L251-259 | Also exists in `fsm/controller.py`. Three copies; bug fix in one misses others |
| D2 | `_safe_get_section(ss, name)` -- identical 4-line try/except wrapper | `actors/front.py` L321-326 | `actors/back.py` L151-156 | Behavioral divergence if error handling changes in one copy |
| D3 | `_never_cancel()` -- identical async bool-returning no-op | `actors/front.py` L943-945 | `actors/back.py` L930-933 | Trivial but signals missing shared utility module |
| D4 | `MODE_MAX_ITERATIONS` / `CRISIS_MAX_ITERATIONS` hardcoded dicts | `react/loop.py` L52-77 | `config/defaults.yaml` prompt.max_iterations / prompt.crisis_iterations | Self-documented at L49: "duplicate the tables". New code reads config; stale constants remain importable |
| D5 | Resume context storage: `back.py` `store_pending_context`/`_get_pending_context`/`_clear_pending_context` (L709-948) | `actors/back.py` (writes/reads `fsm_state.pending_context`) | `protocols/suspension_manager.py` `store_context`/`pop_context` (L221-248, writes `_contexts` dict) | TWO parallel resume storage paths: back.py writes to `fsm_state.pending_context`, FSM controller writes to `suspension_manager._contexts`. On resume, `back_resume_handler` reads from `fsm_state.pending_context` but FSM `_on_task_resume` reads from `suspension_manager.pop_context`. If FSM path runs first and pops context, `back_resume_handler` finds empty `fsm_state.pending_context` and fails with NO_PENDING_CONTEXT |
| D6 | Cancellation state: ad-hoc `fsm_state.cancellation_requested` bool | `actors/back.py` `_build_cancellation_check` L916-928 (reads bool) | `protocols/cancellation.py` `CancellationToken` L61-142 (full protocol with reason, timing, wait) | Back ignores the well-designed CancellationToken and uses a raw bool. No cancel reason, no timing, no TaskCancelledError integration |

### E3.1 -- Back Mailbox Topic Router (5 issues)

Source: WB 14.4.A, 15.5 P0

**Problem:** Both consumers (`coordinator.py` `_run_back_handler` L907 and
`bootstrap.py` `_mailbox_consumer` L370) call `back_handler()` for every
envelope that arrives in the back mailbox. Topics `task.resume.v1`,
`task.cancel.v1`, and `clarification.response.v1` all hit `back_handler`,
which treats them as a new task dispatch. The existing `back_resume_handler`
(back.py L499-656, 158 lines of real resume logic) and `back_cancel_handler`
(back.py L664-700) are never called at runtime. The `subscribe_back_events`
function (back.py L752-793) subscribes to 4 topics but is explicitly
commented out in bootstrap.py L262-266 ("Do NOT call subscribe_back_events
here").

#### 3.1.1 -- Create `route_back_envelope` dispatcher function

**Problem:** No centralized topic-to-handler mapping exists for back-bound
envelopes.

**What to do:**

1. Add a new function `route_back_envelope(envelope, ...)` in `actors/back.py`
   (or a new `actors/back_router.py`) that inspects `envelope.topic` and
   dispatches:
   - `k1.orchestration.task.dispatch.v1` -> `back_handler()`
   - `k1.orchestration.task.resume.v1` -> `back_resume_handler()`
   - `k1.orchestration.task.cancel.v1` -> `back_cancel_handler()`
   - `k1.orchestration.clarification.response.v1` -> `back_resume_handler()`
   - Unknown topic -> log warning + return without calling any handler
2. The function signature must accept the same kwargs as `back_handler` so
   callers only need one call site.
3. Import topic constants from `poc.k1_poc.bus.topics` -- do NOT hardcode
   topic strings.

**Files:** `poc/k1_poc/actors/back.py` (add ~40 lines)

**Acceptance:**

- `route_back_envelope` exists and uses topic constants, not string literals
- Unit test sends envelopes with each of the 4 topics and asserts the correct
  handler is called (mock each handler)

#### 3.1.2 -- Wire `route_back_envelope` into coordinator consumer

**Problem:** `coordinator.py` `_run_back_handler` (L907) calls
`back_handler` directly, ignoring topic.

**What to do:**

1. In `K1DemoCoordinator._run_back_handler` (L884-920), replace the direct
   `back_handler(envelope=env, ...)` call with
   `route_back_envelope(envelope=env, ...)`.
2. Pass `fsm_state=self.fsm` (or the FSMTurnState) as an argument so that
   `back_resume_handler` and `back_cancel_handler` receive it (currently
   `_run_back_handler` never passes `fsm_state` -- see L907).

**Files:** `poc/k1_poc/demo/coordinator.py` (change ~5 lines in `_run_back_handler`)

**Acceptance:**

- Coordinator consumer calls `route_back_envelope`, not `back_handler` directly
- `fsm_state` kwarg is passed to the router function

#### 3.1.3 -- Wire `route_back_envelope` into kernel bootstrap consumer

**Problem:** `bootstrap.py` `_mailbox_consumer` (L370-376) calls
`back_handler` directly, ignoring topic. Comment at L262-266 says
"subscribe_back_events" is disabled.

**What to do:**

1. In `_mailbox_consumer` in bootstrap.py (L370-376), replace the direct
   `back_handler(envelope=back_env, ...)` call with
   `route_back_envelope(envelope=back_env, ...)`.
2. Pass `fsm_state=runtime.fsm` (or derive the turn state).
3. Update the import at L37 to include `route_back_envelope`.

**Files:** `poc/k1_poc/kernel/bootstrap.py` (change ~5 lines)

**Acceptance:**

- Kernel consumer routes back envelopes through `route_back_envelope`
- Existing test suite for bootstrap still passes

#### 3.1.4 -- Validate FSM `_deliver_to_back` delivers correct topics

**Problem:** FSM controller `_on_task_cancel` (L1246-1290) and
`_on_task_resume` (L1394-1461) both call `_deliver_to_back(envelope)`.
The envelope's `.topic` is preserved, so the new router will work. But
we need to verify that no FSM code path mutates or replaces the envelope
topic before delivery.

**What to do:**

1. Read every `_deliver_to_back` call site in controller.py (L970, L988,
   L1290, L1461, L1915) and verify the envelope passed retains its
   original topic.
2. In `_on_task_resume` (L1442-1455), a NEW Envelope is constructed with
   enriched payload. Verify `topic=envelope.topic` is preserved in the
   reconstruction at L1442.
3. Add a debug assertion in `_deliver_to_back` that logs the envelope
   topic for traceability.

**Files:** `poc/k1_poc/fsm/controller.py` (verify + add 2-line assertion)

**Acceptance:**

- All 5 `_deliver_to_back` call sites verified to preserve envelope topic
- Assertion/log added to `_deliver_to_back`

#### 3.1.5 -- Remove or deprecate `subscribe_back_events`

**Problem:** `subscribe_back_events` (back.py L752-793) subscribes directly
to 4 bus topics, but this is explicitly disabled in bootstrap.py L262-266
with a comment explaining why. The function is dead code.

**What to do:**

1. Add a deprecation docstring to `subscribe_back_events` explaining that
   the FSM is the sole routing authority for back-bound topics.
2. Remove the function from `actors/__init__.py` exports if present.
3. Add a `# TODO: Remove in M8` comment.

**Files:** `poc/k1_poc/actors/back.py` (edit docstring), `poc/k1_poc/actors/__init__.py` (remove export if listed)

**Acceptance:**

- `subscribe_back_events` has deprecation notice
- No production code calls it

### E3.2 -- Mandatory Cancellation Propagation (5 issues)

Source: WB 14.4.B, 15.4.B, 15.5 P0

**Problem:** Cancellation is currently optional and uses a raw boolean.
`back_handler` accepts `fsm_state: Any | None = None` (back.py L343). When
`fsm_state` is `None` (which it always is in both consumers -- coordinator
L907 never passes it, bootstrap L370 never passes it), the cancellation
check becomes `_never_cancel` (L922: `if fsm_state is None: return _never_cancel`).
This means Back tasks are NEVER cancellable at runtime. Meanwhile,
`protocols/cancellation.py` defines a well-designed `CancellationToken`
(L61-142) with cancel reason, timing, and `TaskCancelledError`, but it is
never instantiated.

#### 3.2.1 -- Pass FSMTurnState to back handlers via consumers

**Problem:** Neither consumer passes `fsm_state` to `back_handler`.
In coordinator.py `_run_back_handler` (L907):

```python
result = await back_handler(
    envelope=env,
    model=self.model,
    ss=self.session_state,
    bus=self.bus,
    tool_dispatcher=self.back_dispatcher,
)  # no fsm_state kwarg
```

In bootstrap.py `_mailbox_consumer` (L370):

```python
await back_handler(
    envelope=back_env,
    model=runtime.model,
    ss=runtime.session_state,
    bus=runtime.bus,
    tool_dispatcher=runtime.back_dispatcher,
)  # no fsm_state kwarg
```

**What to do:**

1. Both consumers must pass `fsm_state` to `route_back_envelope` (from 3.1.2/3.1.3).
   - Coordinator: `fsm_state=self.fsm` (or `self.fsm._turn_state` if FSMTurnState is the contract)
   - Bootstrap: `fsm_state=runtime.fsm` (or `runtime.fsm._turn_state`)
2. Verify the FSM exposes the turn state or the cancellation flag on a public attribute.

**Files:** `poc/k1_poc/demo/coordinator.py` (1 line), `poc/k1_poc/kernel/bootstrap.py` (1 line)

**Acceptance:**

- Both consumers pass `fsm_state` to the back router
- `back_handler` receives non-None `fsm_state` at runtime

#### 3.2.2 -- Instantiate CancellationToken per task dispatch

**Problem:** `CancellationToken` (cancellation.py L61-142) is never
instantiated. FSM `_on_task_cancel` sets `fsm_state.cancellation_requested = True`
(via `cancel_handler.request_cancel`), which is a global flag affecting ALL
active tasks, not per-task.

**What to do:**

1. In FSM `_route_via_orchestrator` (controller.py ~L840), create a
   `CancellationToken(task_id=task_id)` when dispatching a task.
2. Store the token in a dict on FSM: `self._cancel_tokens: dict[str, CancellationToken]`.
3. In `_on_task_cancel`, call `token.cancel(reason)` instead of setting a global bool.
4. Pass the token to Back via the envelope payload or via the fsm_state accessor.

**Files:** `poc/k1_poc/fsm/controller.py` (~15 lines), `poc/k1_poc/protocols/cancellation.py` (no change)

**Acceptance:**

- Each task dispatch creates a CancellationToken
- `_on_task_cancel` calls `token.cancel()` on the correct per-task token
- Token is retrievable by task_id for back handler use

#### 3.2.3 -- Replace ad-hoc cancellation check in `_build_cancellation_check`

**Problem:** `_build_cancellation_check` (back.py L916-928) reads
`fsm_state.cancellation_requested` (a raw bool). This should use the
per-task CancellationToken from 3.2.2.

**What to do:**

1. Change `_build_cancellation_check` to accept a `CancellationToken | None`
   instead of `fsm_state: Any | None`.
2. The returned async callable should call `token.is_cancelled` instead of
   `getattr(fsm_state, 'cancellation_requested', False)`.
3. Update `back_handler` (L432) and `back_resume_handler` (L644) to extract
   the token from the new FSM accessor (or envelope payload) and pass it to
   `_build_cancellation_check`.

**Files:** `poc/k1_poc/actors/back.py` (change ~15 lines across 3 functions)

**Acceptance:**

- `_build_cancellation_check` uses `CancellationToken.is_cancelled`
- Back handler cancellation is per-task, not global

#### 3.2.4 -- Make `back_cancel_handler` use CancellationToken

**Problem:** `back_cancel_handler` (back.py L664-700) sets
`fsm_state.cancellation_requested = True` and adds to
`fsm_state.cancelled_tasks` set. With per-task tokens, this is redundant.

**What to do:**

1. `back_cancel_handler` should receive the CancellationToken for the task
   and call `token.cancel(reason)`.
2. Remove the `fsm_state.cancellation_requested = True` assignment (L693).
3. Remove the `fsm_state.cancelled_tasks.add(task_id)` assignment (L698).
4. The cancel handler is now just: look up token, call `.cancel()`, done.

**Files:** `poc/k1_poc/actors/back.py` (simplify ~20 lines)

**Acceptance:**

- `back_cancel_handler` uses CancellationToken API
- No direct `fsm_state` attribute mutation

#### 3.2.5 -- Add cancellation context to back handler function signature contract

**Problem:** `back_handler` signature has `fsm_state: Any | None = None`
(optional, duck-typed). The cancellation design is invisible in the
function signature.

**What to do:**

1. Add a required `cancel_token: CancellationToken | None` parameter to
   `back_handler`, `back_resume_handler`, and `back_cancel_handler`.
2. Remove `fsm_state` from `back_handler` and `back_resume_handler` signatures
   (it was only used for cancellation and pending_context; pending_context
   moves to suspension_manager in E3.3).
3. Update all callers (route_back_envelope, tests).

**Files:** `poc/k1_poc/actors/back.py` (signature changes), all test files that call back_handler

**Acceptance:**

- `back_handler` has explicit `cancel_token` parameter (not hidden in `fsm_state: Any`)
- Tests updated to pass `cancel_token`

### E3.3 -- Resume Context Canonicalization (5 issues)

Source: WB 14.4.C, 15.5 P1

**Problem:** Two independent resume-context storage paths exist (see D5):

**Path A (Back-side, back.py):**

- `store_pending_context` (L709-744) writes to `fsm_state.pending_context[task_id]`
- `_get_pending_context` (L935-940) reads from `fsm_state.pending_context[task_id]`
- `_clear_pending_context` (L943-948) deletes from `fsm_state.pending_context[task_id]`
- Used by `back_resume_handler` (L548) to retrieve prior messages

**Path B (FSM-side, suspension_manager.py):**

- `SuspensionManager.store_context` (L221-232) writes to `self._contexts[task_id]`
- `SuspensionManager.pop_context` (L234-244) reads+deletes from `self._contexts[task_id]`
- Used by FSM `_on_task_resume` (L1413) to build ResumeContext
- Also: `SuspensionManager._active` stores `SuspensionRequest.react_history` via async `suspend()`

The two paths are NOT synchronized. FSM pops from Path B in `_on_task_resume`
(L1413: `stored_context = self._suspension_manager.pop_context(task_id)`),
then delivers the enriched envelope to Back. But `back_resume_handler` reads
from Path A (`_get_pending_context` reading `fsm_state.pending_context`).
If `store_pending_context` was never called (it's not called by the FSM),
Path A is empty and `back_resume_handler` returns `NO_PENDING_CONTEXT` error.

#### 3.3.1 -- Elect SuspensionManager as single resume-context owner

**Problem:** Need one source of truth for resume context.

**What to do:**

1. Document the decision: SuspensionManager (`protocols/suspension_manager.py`)
   is the canonical owner of suspension context.
2. FSM `_on_task_suspended` already calls `self._suspension_manager.store_context`
   (controller.py L1349). This is the write path.
3. FSM `_on_task_resume` already calls `self._suspension_manager.pop_context`
   (controller.py L1413). This is the read path.
4. The enriched envelope from `_on_task_resume` (L1442-1455) already injects
   `resume_context` into the payload. This is the delivery path.
5. Formalize: `back_resume_handler` should read from `envelope.payload.resume_context`,
   NOT from `fsm_state.pending_context`.

**Files:** `poc/k1_poc/actors/back.py` (update `back_resume_handler` ~10 lines)

**Acceptance:**

- `back_resume_handler` reads resume context from envelope payload, not fsm_state
- Works with the enriched envelope FSM already produces

#### 3.3.2 -- Update `back_resume_handler` to use envelope-carried resume context

**Problem:** `back_resume_handler` (back.py L548-550) calls
`_get_pending_context(fsm_state, task_id)` which reads from
`fsm_state.pending_context`. This path is empty at runtime.

**What to do:**

1. In `back_resume_handler`, extract `resume_context` from the envelope
   payload (which FSM already enriches at controller.py L1442-1455).
2. Extract `original_task` and `prior_messages` from the resume_context
   fields (`findings_so_far`, `original_task`).
3. If resume_context is missing from payload, fall back to the old
   `_get_pending_context` path for backward compatibility.
4. Log which path was used.

**Files:** `poc/k1_poc/actors/back.py` (change ~15 lines in `back_resume_handler`)

**Acceptance:**

- `back_resume_handler` works with FSM-enriched envelopes (primary path)
- Fallback to `_get_pending_context` logged as warning

#### 3.3.3 -- Deprecate `store_pending_context` / `_get_pending_context` / `_clear_pending_context`

**Problem:** These three functions in back.py (L709-744, L935-940, L943-948)
represent the old resume storage path that is not used by the FSM.

**What to do:**

1. Add deprecation docstrings to all three functions.
2. Add `# TODO: Remove in M8` comments.
3. Remove calls from `back_resume_handler` (replaced in 3.3.2) except
   the fallback path.
4. Do NOT delete yet -- tests may reference them.

**Files:** `poc/k1_poc/actors/back.py` (add deprecation notices)

**Acceptance:**

- All three functions marked deprecated
- No production path depends on them (only fallback)

#### 3.3.4 -- Ensure FSM enriches resume envelope with prior messages

**Problem:** FSM `_on_task_resume` builds a `ResumeContext` (controller.py
L1428-1438) using `build_resume_context()`. This carries `findings_so_far`
from `stored_context.get("react_history", [])`. But `store_context` in
FSM `_on_task_suspended` (L1349) stores the raw task.suspended payload,
which may NOT contain `react_history` unless Back explicitly included it
in the suspension payload.

**What to do:**

1. Verify that `build_task_suspended` in `bus/builders.py` includes the
   react history in its payload. If not, Back must include
   `react_history` in the suspension emission.
2. In `_emit_back_result` (back.py L270-326), when status is "suspended",
   include `react_history: [serialized messages]` in the payload.
3. Verify the FSM `store_context` -> `pop_context` -> `build_resume_context`
   pipeline preserves the react history end-to-end.

**Files:** `poc/k1_poc/actors/back.py` (add react_history to suspended payload), `poc/k1_poc/fsm/controller.py` (verify pipeline)

**Acceptance:**

- Task.suspended payload includes react_history
- FSM resume pipeline delivers react_history to back_resume_handler via envelope

#### 3.3.5 -- Verify `SuspensionManager.cleanup_task` removes all paths

**Problem:** `SuspensionManager.cleanup_task` (suspension_manager.py L203-216)
cleans `_active`, `_contexts`, `_timeout_tasks`, `_suspension_counts`. This
is correct for Path B. But Path A (`fsm_state.pending_context`) has its own
cleanup in `_clear_pending_context`. After unification, verify no stale state.

**What to do:**

1. Verify that `SuspensionManager.cleanup_task` is called on task completion
   (task.complete), task failure (task.failed), and task cancellation (task.cancel).
2. Verify FSM `_on_task_complete` and `_on_task_failed` call cleanup.
3. Add cleanup call in `_on_task_cancel` if missing.

**Files:** `poc/k1_poc/fsm/controller.py` (verify/add cleanup calls), `poc/k1_poc/protocols/suspension_manager.py` (no change expected)

**Acceptance:**

- `cleanup_task` called on all 3 terminal states (complete, failed, cancelled)
- No stale suspension context remains after task terminates

### E3.4 -- Parallel Tool Execution Policy (5 issues)

Source: WB 15.4.A

**Problem:** `react/loop.py` executes ALL non-terminal tool calls in
parallel via `asyncio.gather` (L492-497):

```python
paired_results: list[tuple[Any, ToolResult]] = await asyncio.gather(
    *[_run_tool(tc) for tc in non_terminal]
)
```

But `task/parallel_safety.py` module docstring (L7) says: "The POC
react_loop() processes tools sequentially (one per iteration)." This is
factually wrong. The parallel_safety module defines `PARALLEL_SAFE_GROUPS`
and `ALWAYS_SEQUENTIAL` sets, and exports `classify_tool_batch()` and
`is_parallel_safe()`, but these are NEVER called by `react_loop`. The
result: side-effect tools like `invoke_capability`, `dispatch_task`,
and `promote_belief` run in parallel, violating the safety classification.

#### 3.4.1 -- Fix `parallel_safety.py` docstring (factual error)

**Problem:** Module docstring L7 says "The POC react_loop() processes tools
sequentially (one per iteration)." This is false since at least the current
implementation uses `asyncio.gather` at loop.py L492-497.

**What to do:**

1. Update the module docstring to state the truth: "The POC react_loop()
   executes non-terminal tool calls in parallel via asyncio.gather. This
   module provides safety classification that should be integrated to
   enforce sequential execution for side-effect tools."
2. Remove references to "sequential one per iteration" throughout the module.

**Files:** `poc/k1_poc/task/parallel_safety.py` (docstring edit)

**Acceptance:**

- Docstring accurately describes current behavior
- No false claims about sequential execution

#### 3.4.2 -- Integrate `classify_tool_batch` into `react_loop`

**Problem:** The safety classifier exists but is not called.

**What to do:**

1. In `react_loop` (loop.py), before the `asyncio.gather` at L492-497,
   call `classify_tool_batch([tc.name for tc in non_terminal])` to split
   tools into parallel-safe and sequential groups.
2. Execute parallel-safe tools with `asyncio.gather`.
3. Execute sequential tools one at a time, in order.
4. Import `classify_tool_batch` from `poc.k1_poc.task.parallel_safety`.

**Files:** `poc/k1_poc/react/loop.py` (change ~15 lines around L485-500)

**Acceptance:**

- `classify_tool_batch` called before every parallel execution
- `invoke_capability`, `dispatch_task`, `promote_belief` run sequentially
- `recall_memory`, `update_beliefs`, `update_scoreboard` can run in parallel
- Existing react_loop tests still pass

#### 3.4.3 -- Add config toggle for parallel execution

**Problem:** Need ability to disable parallel execution entirely for
debugging or safety.

**What to do:**

1. Add `react.parallel_tools_enabled: true` to `config/defaults.yaml`.
2. In `react_loop`, check this flag. If false, execute ALL tools sequentially.
3. Log whether parallel mode is active.

**Files:** `poc/k1_poc/config/defaults.yaml` (~2 lines), `poc/k1_poc/react/loop.py` (~5 lines)

**Acceptance:**

- Config toggle exists and defaults to true
- Setting to false forces sequential execution
- Behavior logged

#### 3.4.4 -- Remove stale `MODE_MAX_ITERATIONS` / `CRISIS_MAX_ITERATIONS` from loop.py

**Problem:** (D4) These hardcoded dicts at loop.py L52-77 duplicate the
config tables and are self-documented as duplicates (L49: "NOTE:
MODE_MAX_ITERATIONS and CRISIS_MAX_ITERATIONS duplicate the tables in
prompt.max_iterations / prompt.crisis_iterations"). They are exported
via `react/__init__.py` and imported by tests.

**What to do:**

1. Replace the hardcoded dicts with lazy accessors that read from config:

   ```python
   def get_mode_max_iterations() -> dict[str, int]:
       return get_config().prompt.max_iterations
   ```

2. Keep the old constant names as aliases for backward compat but add
   deprecation comments.
3. Update `react/__init__.py` exports.

**Files:** `poc/k1_poc/react/loop.py` (replace ~25 lines), `poc/k1_poc/react/__init__.py` (update exports)

**Acceptance:**

- No hardcoded iteration dicts in loop.py
- Config is single source of truth
- Tests that import the constants still work

#### 3.4.5 -- Add `submit_result` guard to parallel batch

**Problem:** The current code has a `submit_result` early-return before the
parallel gather (loop.py L475-484). But if the LLM returns `submit_result`
AND other tools in the same response, the `submit_result` is processed first
and the other tools are skipped. This is correct behavior but relies on
iteration order of `response.tool_calls`. Need explicit guard.

**What to do:**

1. Before the parallel execution block, explicitly filter out `submit_result`
   from the batch (already done at L489: `non_terminal = [tc for tc in response.tool_calls if tc.name != "submit_result"]`).
2. Add a log warning if `submit_result` appears alongside other tool calls
   (indicates LLM confusion).
3. Add a comment explaining why this is safe.

**Files:** `poc/k1_poc/react/loop.py` (~5 lines)

**Acceptance:**

- Warning logged if submit_result + other tools in same response
- Comment documents the guard

### E3.5 -- Shared Actor Utilities Extraction (3 issues)

Source: D1, D2, D3

**Problem:** Three utility functions are duplicated between `actors/front.py`
and `actors/back.py` (see D1-D3 in duplication inventory).

#### 3.5.1 -- Extract `_parse_payload` to shared actor utility module

**Problem:** (D1) Identical 8-line `_parse_payload` exists in front.py L59-67
and back.py L251-259. Also duplicated in fsm/controller.py.

**What to do:**

1. Create `poc/k1_poc/actors/shared.py` with `parse_envelope_payload(envelope)`.
2. Import and use in front.py, back.py.
3. FSM controller.py has its own copy -- defer its unification to M4
   (controller changes are heavy).

**Files:** New: `poc/k1_poc/actors/shared.py` (~15 lines). Edit: `actors/front.py`, `actors/back.py` (replace local def with import)

**Acceptance:**

- Single `parse_envelope_payload` in shared.py
- Both actors import from shared.py
- No behavioral change

#### 3.5.2 -- Extract `_safe_get_section` to shared actor utility module

**Problem:** (D2) Identical 4-line `_safe_get_section` in front.py L321-326
and back.py L151-156.

**What to do:**

1. Add `safe_get_section(ss, name)` to `poc/k1_poc/actors/shared.py`.
2. Import and use in front.py, back.py.

**Files:** `poc/k1_poc/actors/shared.py` (add ~6 lines). Edit: `actors/front.py`, `actors/back.py`

**Acceptance:**

- Single `safe_get_section` in shared.py
- Both actors import from shared.py

#### 3.5.3 -- Extract `_never_cancel` to shared actor utility module

**Problem:** (D3) Identical async no-op in front.py L943-945 and back.py
L930-933.

**What to do:**

1. Add `never_cancel()` to `poc/k1_poc/actors/shared.py`.
2. Import and use in front.py, back.py.

**Files:** `poc/k1_poc/actors/shared.py` (add ~4 lines). Edit: `actors/front.py`, `actors/back.py`

**Acceptance:**

- Single `never_cancel` in shared.py
- Both actors import from shared.py

### E3.6 -- Actor & React Conformance Tests (4 issues)

Source: WB 14.6, 15.6, 15.5 P1

#### 3.6.1 -- Test: front emission ordering (dispatches before final.response)

**Problem:** Front handler (front.py L671-741) enforces that task dispatches
are emitted BEFORE response.final. This prevents FSM from transitioning to
LISTENING before dispatches arrive. Need a conformance test.

**What to do:**

1. Create test that invokes `front_handler` with a mock model that returns
   a dispatch_task tool call followed by text.
2. Capture bus.publish calls in order.
3. Assert: `task.dispatch.v1` appears BEFORE `response.final.v1` in the
   publish sequence.
4. Assert: cancel dispatches (`task.cancel.v1`) appear before normal dispatches.

**Setup pattern:** Use the existing mock patterns from `test_m06_front_handler.py`.

**Files:** New test in `tests/poc/test_m3_actor_react_conformance.py`

**Acceptance:**

- Test proves dispatch-before-final ordering
- Test proves cancel-before-normal ordering

#### 3.6.2 -- Test: resume envelope routes to `back_resume_handler`

**Problem:** After 3.1.1-3.1.3, need to verify the routing works end-to-end.

**What to do:**

1. Create test that sends a `task.resume.v1` envelope through
   `route_back_envelope`.
2. Mock `back_resume_handler` and `back_handler`.
3. Assert: `back_resume_handler` is called, NOT `back_handler`.
4. Repeat for `task.cancel.v1` -> `back_cancel_handler`.
5. Repeat for `clarification.response.v1` -> `back_resume_handler`.

**Files:** `tests/poc/test_m3_actor_react_conformance.py`

**Acceptance:**

- Each back topic routes to its correct handler
- Unknown topic logs warning and calls no handler

#### 3.6.3 -- Test: cancel propagation reaches back loop

**Problem:** After 3.2.1-3.2.5, need end-to-end cancel test.

**What to do:**

1. Create test with a CancellationToken.
2. Start `back_handler` with a model that returns multiple tool calls.
3. After first tool call, set `token.cancel()`.
4. Assert: react_loop exits with status="cancelled".
5. Assert: token.is_cancelled is True, cancel_reason is set.

**Files:** `tests/poc/test_m3_actor_react_conformance.py`

**Acceptance:**

- Cancel propagates from token through react_loop
- ReactResult.status == "cancelled"

#### 3.6.4 -- Test: parallel tool safety enforcement

**Problem:** After 3.4.2, need to verify that sequential tools are not
parallelized.

**What to do:**

1. Create test with a model that returns 3 tool calls:
   `recall_memory`, `invoke_capability`, `update_beliefs`.
2. Mock `tool_dispatcher.dispatch` to record call timestamps.
3. Assert: `recall_memory` and `update_beliefs` may overlap (parallel-safe).
4. Assert: `invoke_capability` does NOT overlap with any other call (sequential).

**Files:** `tests/poc/test_m3_actor_react_conformance.py`

**Acceptance:**

- Parallel-safe tools execute concurrently
- Sequential tools execute one at a time

### M3 Implementation Order

1. 3.5.1, 3.5.2, 3.5.3 (extract shared utilities -- prerequisite for clean diffs)
2. 3.1.1 (create route_back_envelope)
3. 3.1.2, 3.1.3 (wire into consumers)
4. 3.1.4, 3.1.5 (verify FSM delivery, deprecate subscribe_back_events)
5. 3.2.1 (pass fsm_state to consumers)
6. 3.2.2 (instantiate CancellationToken)
7. 3.2.3, 3.2.4, 3.2.5 (replace ad-hoc cancellation, update signatures)
8. 3.3.1, 3.3.2 (elect SuspensionManager, update back_resume_handler)
9. 3.3.3, 3.3.4, 3.3.5 (deprecate old path, verify pipeline, cleanup)
10. 3.4.1 (fix docstring)
11. 3.4.2, 3.4.3 (integrate classifier, add toggle)
12. 3.4.4, 3.4.5 (remove stale constants, guard submit_result)
13. 3.6.1, 3.6.2, 3.6.3, 3.6.4 (conformance tests)
14. 3.7.1-3.7.9 (end-to-end wiring -- AFTER all E3.1-E3.6 issues complete)

### E3.7 -- End-to-End Wiring & System Integration

Source: Bootstrap analysis, actors/back.py, react/loop.py, protocols/cancellation.py, protocols/suspension_manager.py, task/parallel_safety.py, demo/coordinator.py, kernel/bootstrap.py

**Why this epic exists:** E3.1-E3.6 create new runtime infrastructure -- topic-based back routing (`route_back_envelope`), per-task CancellationTokens, unified SuspensionManager context, parallel tool safety classification, shared actor utilities -- but these changes interact with M1's ledger + canonical events and M2's guard table + dead-letter pipeline + idempotency ledger in ways the individual issues do not address. Without this epic, M3 creates a working back router that never records routing decisions in the ledger, per-task cancellation tokens whose lifecycle is invisible to observability, parallel tool safety that silently classifies without audit trail, and modified back handler signatures that break M1+M2 test suites. **Every M3 artifact must plug into the cumulative M1+M2 infrastructure or the three milestones drift into disconnected layers.**

**System state after M1+M2 (E1.4 + E2.5 wiring complete) -- what M3 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created          # M1 1.4.1
  -> LedgerMiddleware in bus middleware chain             # M1 1.4.4
  -> ConciergeController(bus, router)
     -> set_ledger(writer)                               # M1 1.4.1
     -> _ledger_append() in 11 handlers                  # M1 1.4.2
     -> _try_deserialize() bridge                        # M1 1.4.3
     -> _dispatch_envelope() flow:                       # M2 2.5.3
          topic_guard -> idempotency -> guard_dispatch -> handler
     -> FULL_GUARD_TABLE + _guard_dispatch()             # M2 2.1.1-2.1.2
     -> _publish_dead_letter() with ledger recording     # M2 2.5.2
     -> IdempotencyLedger                                # M2 2.3.2
     -> decide_response_final() + ResponseFinalEvent     # M2 2.3.1, 2.5.4
  -> DeadLetterConsumer subscribed to bus                 # M2 2.5.1
  -> builders auto-enrich legacy dicts                   # M1 1.4.5
  -> Demo: ledger health + /api/ledger/stats             # M1 1.4.6
  -> Demo: dead-letter health + /api/dead-letters        # M2 2.5.5
  -> Fixtures: create_wired_fsm(with_ledger,
               with_dead_letter_consumer)                # M1 1.4.7, M2 2.5.6
```

**M3 artifacts that must integrate into this M1+M2-wired system:**

| M3 Artifact | Where It Lives After E3.1-E3.6 | M1+M2 Touchpoint It Must Connect To |
|-------------|-------------------------------|--------------------------------------|
| `route_back_envelope()` (topic router) | `actors/back.py` or `actors/back_router.py` | M2 dead-letter pipeline -- unknown back topics must dead-letter, not silently drop |
| Per-task `CancellationToken` on FSM `_cancel_tokens` dict | `fsm/controller.py` | M1 `_ledger_append()` -- token creation and cancellation events must be auditable |
| `back_handler` / `back_resume_handler` new `cancel_token` param (fsm_state removed) | `actors/back.py` | M1+M2 test fixtures -- all callers updated, test create_wired_fsm flows work |
| `SuspensionManager` as sole resume-context owner | `protocols/suspension_manager.py` | M1 ledger -- resume path (pop_context -> envelope -> back_resume_handler) must remain ledger-auditable |
| `classify_tool_batch` integrated into `react_loop` | `react/loop.py` | M1 ledger / M2 observability -- parallel vs sequential execution decisions trackable |
| `actors/shared.py` (parse_envelope_payload, safe_get_section, never_cancel) | `actors/shared.py` | `actors/__init__.py` -- clean export chain, no circular imports |
| `react.parallel_tools_enabled` config toggle | `config/defaults.yaml` | Demo health endpoint -- config state visible in diagnostics |
| Deprecated functions (store_pending_context, _get_pending_context, subscribe_back_events) | `actors/back.py` | M1+M2 tests -- no test still depends on deprecated path as primary |

---

#### 3.7.1 -- Wire `route_back_envelope` unknown-topic path into M2 dead-letter pipeline

**Problem:** E3.1.1 creates `route_back_envelope()` which dispatches by topic. For unknown topics, the spec says "log warning + return without calling any handler." But M2 established that rejected/unroutable events must flow to the dead-letter pipeline (not silently drop). In the FSM, invalid state-topic combinations produce dead-letter events via `_publish_dead_letter()`. The back router should follow the same pattern for back-side unknown topics.

Currently, the only path to the back mailbox is via FSM `_deliver_to_back()`, which means envelopes are already guard-table-validated. But:

- Tests may inject directly into the back mailbox (bypassing FSM)
- Future milestones (M7 BackPool, M12 Chaos Tests) inject synthetic envelopes
- Defensive coding requires the back router to handle the unknown case

**What to do:**

1. In `route_back_envelope()` (created by 3.1.1), for the unknown-topic branch, publish a dead-letter event to the bus instead of just logging:

   ```python
   if topic not in _BACK_TOPIC_HANDLERS:
       logger.warning("route_back_envelope: unknown topic=%s envelope_id=%d", topic, env_id)
       bus.publish(build_dead_letter(
           payload={
               "original_envelope_id": env_id,
               "original_topic": topic,
               "reason": "unknown_back_topic",
               "actor": "back_router",
           },
           parent_id=env_id,
       ))
       return
   ```

2. The `route_back_envelope` signature must accept `bus: IBus` as a parameter (it already needs it for handler dispatch). Verify the bus is passed from both consumers (coordinator 3.1.2, bootstrap 3.1.3).

3. Add test: inject an envelope with topic `"k1.fake.unknown.v1"` into route_back_envelope. Assert: dead-letter event published to bus. Assert: DeadLetterConsumer (from M2 2.5.1) receives it with reason `"unknown_back_topic"`.

**Files to modify:**

- `poc/k1_poc/actors/back.py` (or `actors/back_router.py`) -- dead-letter emission in unknown branch
- `tests/poc/test_m3_actor_react_conformance.py` -- add unknown-topic dead-letter test

**Dependency:** E3.1.1 (route_back_envelope exists), M2 2.5.1 (DeadLetterConsumer in bootstrap), M2 2.2.1 (build_dead_letter builder)

**Acceptance:**

- Unknown back topics produce dead-letter events on the bus, not silent drops
- DeadLetterConsumer captures them with reason `"unknown_back_topic"`
- Actor field in dead-letter payload is `"back_router"` (distinguishable from FSM dead-letters)

---

#### 3.7.2 -- Wire CancellationToken lifecycle into M1 ledger audit trail

**Problem:** E3.2.2 creates a per-task `CancellationToken` in FSM `_route_via_orchestrator()` and stores it in `self._cancel_tokens[task_id]`. E3.2.3 replaces the ad-hoc bool check with `token.is_cancelled`. E3.2.4 makes `back_cancel_handler` call `token.cancel()`. But none of these record to the M1 ledger:

- Token CREATION is invisible -- the ledger has no record that a task was assigned a cancellation token
- Token CANCELLATION is partially visible -- FSM `_on_task_cancel` already calls `_ledger_append()` with a `TaskCancelled` event (M1 1.4.2), but after M3 refactoring the cancel flow changes from `fsm_state.cancellation_requested = True` to `token.cancel(reason)`. The ledger recording must survive this change.
- Token CLEANUP (task completes before cancel checked) is invisible -- if `completed_before_cancel=True`, this diagnostic info is lost

**What to do:**

1. Verify that FSM `_on_task_cancel` still calls `_ledger_append()` after the M3 refactoring. The `_dispatch_envelope()` flow (M2 2.5.3) wraps handlers, so `_on_task_cancel` becomes `_handle_task_cancel` called by `_dispatch_envelope`. Verify the ledger recording is inside `_handle_task_cancel`, not lost in the refactoring.

2. Enrich the `TaskCancelled` canonical event (from M1 1.1.2) with per-task token data:

   ```python
   # In FSM _handle_task_cancel (after M3 3.2.2 refactoring):
   token = self._cancel_tokens.get(task_id)
   if token:
       token.cancel(cancel_reason)
   self._ledger_append(TaskCancelledEvent(
       task_id=task_id,
       cancel_reason=cancel_reason.value if cancel_reason else "unknown",
       had_token=token is not None,
       completed_before_cancel=token.completed_before_cancel if token else False,
       **from_envelope(envelope, actor="fsm"),
   ))
   ```

3. In `_route_via_orchestrator` (where token is created per 3.2.2), add a debug-level ledger event or structured log for token creation. Full ledger event is optional (may be noisy), but at minimum a `logger.info("CancellationToken created: task_id=%s", task_id)` must exist.

4. In `cleanup_task` or task completion path, if `token.completed_before_cancel` is True, log a diagnostic warning.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (enrich _handle_task_cancel ledger event, add token creation log)
- `poc/k1_poc/events/task.py` (extend TaskCancelled schema with cancel_reason, had_token, completed_before_cancel)

**Dependency:** E3.2.2 (per-task CancellationToken), E3.2.4 (back_cancel_handler uses token), M1 1.4.2 (_ledger_append exists), M2 2.5.3 (_dispatch_envelope flow)

**Acceptance:**

- `TaskCancelled` ledger event includes cancel_reason, had_token, completed_before_cancel
- Ledger recording survives the M3 cancel flow refactoring
- Token creation is logged at INFO level

---

#### 3.7.3 -- Wire SuspensionManager unification into ledger resume-context audit

**Problem:** E3.3 elects SuspensionManager as the sole resume-context owner and deprecates the back-side `store_pending_context` / `_get_pending_context` path. After M3, the resume flow is:

```
Back suspends -> task.suspended emitted (with react_history in payload, per 3.3.4)
  -> FSM _on_task_suspended -> SuspensionManager.store_context(task_id, payload)
  -> _ledger_append(TaskSuspended event)

User answers -> task.resume arrives
  -> FSM _on_task_resume -> SuspensionManager.pop_context(task_id) -> build_resume_context()
  -> _deliver_to_back(enriched_envelope with resume_context in payload)
  -> _ledger_append(TaskResumed event)

Back resumes -> back_resume_handler reads resume_context from envelope payload (per 3.3.2)
```

The M1 ledger already records `TaskSuspended` and `TaskResumed`. But after M3:

- The `react_history` field added to the suspended payload (3.3.4) should be reflected in the ledger's `TaskSuspended` event (otherwise crash recovery can't reconstruct the react state).
- The `SuspensionManager.pop_context()` call is destructive -- it removes the context. If ledger recording happens AFTER pop, the context is available in the ledger event. If ledger recording happens BEFORE pop (in _dispatch_envelope flow), the event is recorded but doesn't include the popped context data. Verify ordering.
- The `SuspensionManager.cleanup_task()` calls (verified in 3.3.5) must NOT run before the ledger records the terminal event. Verify: `_ledger_append(TaskCompleted)` happens BEFORE `cleanup_task(task_id)`.

**What to do:**

1. In FSM `_on_task_suspended`, verify that the `react_history` from Back's new suspended payload (3.3.4) is included in the `TaskSuspended` canonical event's payload. If the current schema doesn't carry react_history, extend it:

   ```python
   self._ledger_append(TaskSuspendedEvent(
       task_id=task_id,
       suspension_type=payload.get("suspension_type"),
       question=payload.get("question"),
       has_react_history=bool(payload.get("react_history")),
       react_history_len=len(payload.get("react_history", [])),
       **from_envelope(envelope, actor="fsm"),
   ))
   ```

   (Do NOT include full react_history in ledger -- too large. Include length and flag.)

2. In FSM `_on_task_resume`, verify ordering: `pop_context()` -> build `resume_context` -> `_ledger_append(TaskResumed)` -> `_deliver_to_back()`. The ledger event must include `has_resume_context=True` and `resume_context_keys`.

3. In FSM `_on_task_complete` and `_on_task_failed`, verify: `_ledger_append()` BEFORE `cleanup_task()`. If cleanup removes SuspensionManager state before the ledger records the event, recovery is lossy.

4. Add a warning log in `SuspensionManager.cleanup_task()` if a task being cleaned up still has active context (indicates a possible ordering bug).

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (verify ordering: ledger before cleanup, enrich suspend/resume events)
- `poc/k1_poc/events/task.py` (extend TaskSuspended with has_react_history, extend TaskResumed with has_resume_context)
- `poc/k1_poc/protocols/suspension_manager.py` (warning log in cleanup_task if active context exists)

**Dependency:** E3.3.1-3.3.5 (SuspensionManager elected, back_resume_handler updated, cleanup verified), M1 1.4.2 (_ledger_append)

**Acceptance:**

- `TaskSuspended` ledger event includes `has_react_history` flag and `react_history_len`
- `TaskResumed` ledger event includes `has_resume_context` flag
- `_ledger_append()` always fires BEFORE `cleanup_task()` in terminal states
- `SuspensionManager.cleanup_task()` logs warning if cleaning active context

---

#### 3.7.4 -- Wire parallel tool safety into structured observability

**Problem:** E3.4.2 integrates `classify_tool_batch()` into `react_loop()` to split tools into parallel and sequential groups. E3.4.3 adds a config toggle `react.parallel_tools_enabled`. But the classification decision is invisible to M1's ledger and M2's observability pipeline:

- M11 (Observability) needs to know: how often does the LLM return mixed parallel/sequential batches? What is the wall-clock savings from parallel execution?
- M12 (Chaos Tests) needs to verify: under concurrent load, does the safety classifier still prevent side-effect tools from running in parallel?
- The current implementation (3.4.2) logs the execution mode but doesn't emit structured events.

**What to do:**

1. In `react_loop()`, after `classify_tool_batch()` splits tools, emit a structured log entry (not a full bus event -- tool execution is high-frequency):

   ```python
   parallel_names, sequential_names = classify_tool_batch([tc.name for tc in non_terminal])
   logger.info(
       "react_loop: tool_batch_classified  parallel=%s sequential=%s parallel_enabled=%s trace=%s",
       parallel_names,
       sequential_names,
       parallel_enabled,
       trace_id[:8] if trace_id else "",
   )
   ```

2. Track per-react-loop statistics and include in `ReactResult`:

   ```python
   @dataclass
   class ReactResult:
       # ... existing fields ...
       parallel_tool_calls: int = 0    # NEW: how many tools ran in parallel
       sequential_tool_calls: int = 0  # NEW: how many tools ran sequentially
   ```

3. In `back_handler` and `front_handler`, after react_loop returns, the ReactResult carries the parallel/sequential counts. The `_emit_back_result` (back.py L270-326) can include these in the task.complete/task.failed payload for downstream observability.

4. Add `react.parallel_tools_enabled` to the demo health check output (Phase 5 or `/api/status`):

   ```python
   checks["parallel_tools_enabled"] = get_config().react.parallel_tools_enabled
   ```

**Files to modify:**

- `poc/k1_poc/react/loop.py` (structured logging after classify_tool_batch, add counts to ReactResult)
- `poc/k1_poc/actors/back.py` (_emit_back_result includes parallel/sequential counts)
- `poc/k1_poc/demo/coordinator.py` (health check includes parallel_tools_enabled)

**Dependency:** E3.4.2 (classify_tool_batch integrated), E3.4.3 (config toggle), M2 2.5.5 (demo health pattern)

**Acceptance:**

- `classify_tool_batch` classification logged at INFO with tool names per group
- `ReactResult` carries `parallel_tool_calls` and `sequential_tool_calls` counts
- Demo health check exposes `parallel_tools_enabled` config state
- No bus event emitted per tool batch (too noisy) -- structured logs only

---

#### 3.7.5 -- Wire `actors/shared.py` into export chain and verify import hygiene

**Problem:** E3.5 creates `actors/shared.py` with `parse_envelope_payload()`, `safe_get_section()`, and `never_cancel()`. These are extracted from front.py and back.py. But:

- `actors/__init__.py` currently exports `_parse_payload` from `front.py` (line ~12) -- must now export from `shared.py`
- `fsm/controller.py` has its own `_parse_payload` (deferred to M4 per 3.5.1) -- the shared module must not create a circular import with the FSM
- `boot()` in `main.py` imports from actors -- verify no import-time side effects
- Downstream milestones (M4 SessionState, M5 Arbiter) may import `parse_envelope_payload` -- must be available at `poc.k1_poc.actors.shared`

**What to do:**

1. Update `actors/__init__.py` to export shared utilities:

   ```python
   # Shared Actor Utilities (E3.5)
   from poc.k1_poc.actors.shared import (
       parse_envelope_payload,
       safe_get_section,
       never_cancel,
   )
   ```

2. Verify NO circular imports by running:

   ```python
   python -c "from poc.k1_poc.actors.shared import parse_envelope_payload, safe_get_section, never_cancel"
   ```

   This must succeed without ImportError. The shared module should only import from `k1.bus.envelope` (for Envelope type hint) and `json` -- no imports from actors.front, actors.back, or fsm.

3. Verify `actors/shared.py` does NOT import from `poc.k1_poc.config` or `poc.k1_poc.bus.builders` -- keep it dependency-minimal.

4. Add `shared.py` to the `actors/` module docstring in `__init__.py`.

**Files to modify:**

- `poc/k1_poc/actors/__init__.py` (add shared exports)
- `poc/k1_poc/actors/shared.py` (verify minimal imports -- created by 3.5.1-3.5.3)

**Dependency:** E3.5.1-3.5.3 (shared.py exists with 3 functions)

**Acceptance:**

- `from poc.k1_poc.actors.shared import parse_envelope_payload` works
- `from poc.k1_poc.actors import parse_envelope_payload` works
- No circular imports
- shared.py imports only `json` and `k1.bus.envelope`

---

#### 3.7.6 -- Wire M3 artifacts into M1+M2 test fixtures

**Problem:** M1's E1.4.7 created `create_wired_fsm(with_ledger=True)`. M2's E2.5.6 extended it with `with_dead_letter_consumer=True`. M3 introduces:

- Per-task CancellationTokens on FSM (E3.2.2) -- tests need to create tokens
- `route_back_envelope()` as the canonical back dispatch (E3.1.1) -- tests need to call it instead of `back_handler()` directly
- `cancel_token` parameter on back handlers (E3.2.5) -- tests that call back_handler must pass it
- `actors/shared.py` utilities (E3.5) -- tests should import from shared, not from individual actors

The test fixtures must be updated so E3.6 conformance tests AND all downstream milestone tests get a fully wired system with M1+M2+M3 infrastructure.

**What to do:**

1. Extend `create_wired_fsm()` in `testing/fixtures.py`:

   ```python
   def create_wired_fsm(
       *,
       capture: bool = True,
       with_ledger: bool = True,
       with_dead_letter_consumer: bool = True,
       with_cancel_tokens: bool = True,       # NEW M3
   ) -> dict:
       # ... M1+M2 setup unchanged ...
       if with_cancel_tokens:
           # Ensure FSM has _cancel_tokens dict initialized
           assert hasattr(fsm, '_cancel_tokens'), "FSM must have _cancel_tokens after M3 3.2.2"
       return result
   ```

2. Add helper to create a test CancellationToken:

   ```python
   def create_test_cancel_token(task_id: str = "test-task-001") -> CancellationToken:
       from poc.k1_poc.protocols.cancellation import CancellationToken
       return CancellationToken(task_id=task_id)
   ```

3. Add helper to invoke back_handler with M3 signature:

   ```python
   async def invoke_back_handler(
       envelope: Envelope,
       model: Any,
       ss: Any,
       bus: IBus,
       tool_dispatcher: ToolDispatcher,
       cancel_token: CancellationToken | None = None,
   ) -> ReactResult:
       """Invoke back_handler with M3-compliant signature."""
       return await back_handler(
           envelope=envelope,
           model=model,
           ss=ss,
           bus=bus,
           tool_dispatcher=tool_dispatcher,
           cancel_token=cancel_token,
       )
   ```

4. Add helper for route_back_envelope testing:

   ```python
   async def invoke_back_router(
       envelope: Envelope,
       wired: dict,
       cancel_token: CancellationToken | None = None,
   ) -> Any:
       """Route an envelope through the M3 back router."""
       from poc.k1_poc.actors.back import route_back_envelope
       return await route_back_envelope(
           envelope=envelope,
           model=wired["model"],
           ss=wired["ss"],
           bus=wired["bus"],
           tool_dispatcher=wired["back_dispatcher"],
           cancel_token=cancel_token,
       )
   ```

5. Update `conftest.py` fixtures to include cancel_token=None as default.

**Files to modify:**

- `poc/k1_poc/testing/fixtures.py` (extend create_wired_fsm, add cancel token and back router helpers)
- `tests/poc/conftest.py` (update fixtures for M3 signatures)

**Dependency:** E3.2.2 (CancellationToken on FSM), E3.2.5 (back handler signature), E3.1.1 (route_back_envelope), M1 1.4.7 + M2 2.5.6 (existing fixtures)

**Acceptance:**

- `create_wired_fsm()` returns system with M1 ledger + M2 dead-letter + M3 cancel tokens
- `create_test_cancel_token()` helper exists
- `invoke_back_handler()` uses M3 signature
- All E3.6 conformance tests use these fixtures

---

#### 3.7.7 -- Backward compatibility: verify M1 ledger + M2 guard table survive M3 refactoring

**Problem:** M3 makes significant changes to code paths where M1 and M2 infrastructure lives:

| M3 Change | M1/M2 Code Path At Risk |
|-----------|------------------------|
| `route_back_envelope` replaces direct `back_handler` calls in consumers | M2 guard table already validated before delivery -- no regression expected, but consumer code changed |
| Per-task CancellationToken replaces `fsm_state.cancellation_requested` bool | M1 `_ledger_append` in `_on_task_cancel` must survive the refactoring |
| `back_handler` signature: `fsm_state` removed, `cancel_token` added | M1+M2 tests that call `back_handler(fsm_state=None)` must be updated |
| `SuspensionManager` as sole context owner, `store_pending_context` deprecated | M1 `_ledger_append` in `_on_task_suspended`/`_on_task_resume` must use SuspensionManager path |
| `classify_tool_batch` inserted before `asyncio.gather` in react_loop | Existing react_loop tests must pass unchanged (tool execution still works) |
| `MODE_MAX_ITERATIONS`/`CRISIS_MAX_ITERATIONS` replaced with config accessors | M2 tests importing these constants must still work (backward compat aliases) |

**What to do:**

1. Create `tests/poc/test_m03_wiring_regression.py`:

   **Test matrix (one test per M1/M2 survival point):**

   | Test | Trigger | Expected M1/M2 Artifact | M3 Change That Could Break It |
   |------|---------|------------------------|-------------------------------|
   | `test_ledger_records_after_back_routing` | Send task.dispatch through route_back_envelope | `TaskCreated` in ledger | 3.1.1-3.1.3 consumer refactoring |
   | `test_ledger_records_cancel_with_token` | Create token, call token.cancel(), deliver task.cancel | `TaskCancelled` in ledger (with cancel_reason) | 3.2.2-3.2.4 cancel flow change |
   | `test_dead_letter_on_unknown_back_topic` | Send unknown topic to route_back_envelope | DeadLetterConsumer has 1 event | 3.7.1 unknown-topic path |
   | `test_guard_table_still_rejects_invalid` | Send task.complete in LISTENING | Dead-letter (guard=DEAD_LETTER) | M3 does not touch guard table, but verify it still works |
   | `test_suspend_resume_ledger_with_suspension_manager` | Trigger suspend -> resume flow | `TaskSuspended` + `TaskResumed` in ledger | 3.3.1-3.3.5 context path unification |
   | `test_react_loop_parallel_safety_no_regression` | Run react_loop with mixed parallel/sequential tools | All tools execute, ReactResult.status in expected set | 3.4.2 classify_tool_batch insertion |
   | `test_mode_max_iterations_import_still_works` | `from poc.k1_poc.react.loop import MODE_MAX_ITERATIONS` | Import succeeds, dict non-empty | 3.4.4 stale constant replacement |
   | `test_m2_ledger_survival_tests_still_pass` | Run M2 ledger survival tests | All 8 tests pass | M3 controller.py refactoring |

2. Each test uses `create_wired_fsm()` from the updated fixtures (3.7.6).

3. This test file is the M1+M2 <-> M3 contract enforcer. If any M3 change breaks ledger recording, guard dispatch, or dead-letter pipeline, this file catches it.

**Files to create:**

- `tests/poc/test_m03_wiring_regression.py`

**Dependency:** 3.7.1-3.7.6 (all wiring issues), M1 1.4.7 (fixtures), M2 2.5.7 (M2 regression pattern)

**Acceptance:**

- All 8 regression tests pass
- M2 `test_m02_ledger_survival.py` tests still pass after M3 changes
- Zero false positives -- tests verify actual wiring, not mock behavior

---

#### 3.7.8 -- Full regression: demo smoke test with back router + cancellation + parallel safety

**Problem:** M3 changes the core consumer loop (route_back_envelope replaces direct back_handler calls), adds per-task cancellation tokens, and modifies the react loop execution strategy. The demo web app is the user-facing integration surface. If any of these changes introduce a regression, the demo breaks silently.

**What to do:**

1. Create `tests/poc/test_m03_demo_smoke.py`:

   **Scenario A: Happy path with back routing active**
   - Boot kernel via `start_kernel()` with default config
   - Send user input -> Front dispatches task -> task.dispatch arrives in back mailbox
   - Verify `route_back_envelope` routes to `back_handler` (not back_resume_handler or back_cancel_handler)
   - Verify task completes and appears in ledger
   - Verify zero dead-letters
   - Verify `/api/status` returns system_ready=True
   - Verify health check shows `parallel_tools_enabled=True`

   **Scenario B: Cancel propagation end-to-end**
   - Boot kernel
   - Send user input -> Front dispatches task -> task starts in back
   - Send "cancel that" -> Front emits task.cancel.v1
   - Verify FSM creates CancellationToken, calls token.cancel()
   - Verify back_cancel_handler receives envelope via route_back_envelope
   - Verify ledger has `TaskCancelled` with `had_token=True`
   - Verify zero dead-letters (cancel is a valid operation)

   **Scenario C: Resume flow through SuspensionManager**
   - Boot kernel
   - Send user input -> task suspends (needs clarification)
   - Verify `TaskSuspended` in ledger with `has_react_history=True`
   - Send clarification answer -> task.resume arrives
   - Verify `route_back_envelope` routes to `back_resume_handler`
   - Verify `back_resume_handler` reads resume_context from envelope payload (not fsm_state)
   - Verify `TaskResumed` in ledger with `has_resume_context=True`

   **Scenario D: Parallel safety active**
   - Boot kernel with `react.parallel_tools_enabled=True`
   - Run a task that triggers multiple tool calls
   - Verify `classify_tool_batch` was called (structured log present)
   - Verify sequential tools did NOT overlap

2. These tests exercise the full M1+M2+M3 stack: bootstrap -> bus -> FSM -> guard table -> dead-letter -> ledger -> back router -> cancellation tokens -> parallel safety -> demo endpoints.

**Files to create:**

- `tests/poc/test_m03_demo_smoke.py`

**Dependency:** 3.7.1-3.7.7 (all wiring and regression), M2 2.5.8 (demo smoke pattern)

**Acceptance:**

- All 4 scenarios pass
- Happy path has zero dead-letters
- Cancel path records to ledger with per-task token data
- Resume path uses SuspensionManager (not deprecated pending_context)
- Parallel safety classification logged in structured format

---

#### 3.7.9 -- Update M3 Implementation Order and add M3 Touchpoint Matrix

**Problem:** The M3 implementation order (above) covers E3.1-E3.6 but not E3.7 wiring. The downstream milestones (M4-M12) need to know what they inherit from M3.

**What to do:**

1. The implementation order is already updated above (step 14: 3.7.1-3.7.9 after all E3.1-E3.6).

2. Document the M3 Touchpoint Matrix below.

**No files to modify.** This is a documentation issue within v3_milestones.md.

---

### M3 Touchpoint Matrix: What M4-M12 Inherit from M3

| Milestone | M3 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M4** (SessionState) | `actors/shared.py::parse_envelope_payload()` | SessionState delta handlers import from shared, not duplicated. `safe_get_section` used by SS read paths. |
| **M4** (SessionState) | `SuspensionManager` as sole context owner | SS no longer needs `pending_context` dict on FSMTurnState. SS cleanup uses SuspensionManager.cleanup_task(). |
| **M5** (Arbiter) | `route_back_envelope()` pattern | Arbiter-dispatched tasks use the same topic router. New arbiter topics added to back router dispatch table. |
| **M5** (Arbiter) | Per-task `CancellationToken` | Arbiter can cancel individual tasks without global flag. Multi-task cancellation is per-token. |
| **M6** (HITL V3) | `SuspensionManager` canonical resume path | HITL V3 timeout/resume flows use SuspensionManager exclusively. No back-side `store_pending_context` path. |
| **M6** (HITL V3) | `back_resume_handler` reads from envelope payload | HITL resolution enrichment goes through FSM -> envelope -> back, not through fsm_state.pending_context. |
| **M7** (BackPool) | `route_back_envelope()` dispatch table | BackPool workers use route_back_envelope for per-worker topic routing. New lease/heartbeat topics added to router. |
| **M7** (BackPool) | Per-task `CancellationToken` | Worker cancellation is per-task token. Pool manager calls token.cancel() on worker eviction. |
| **M7** (BackPool) | `classify_tool_batch()` + parallel safety | Pool workers enforce parallel safety. High-concurrency pool does not let side-effect tools run in parallel across workers. |
| **M8** (Weave Policy) | `ReactResult.parallel_tool_calls` / `sequential_tool_calls` | Adaptive weave policy uses tool execution patterns as pressure signal (high parallel = low latency = less weave pressure). |
| **M9** (Ledger Migration) | Enriched `TaskCancelled`, `TaskSuspended`, `TaskResumed` events | Crash recovery uses `has_react_history`, `has_resume_context`, `cancel_reason` for accurate state reconstruction. |
| **M10** (UltraBERT) | `classify_tool_batch()` | Phase1 classification results inform which tools are safe to pre-fetch in parallel. |
| **M11** (Observability) | `ReactResult` parallel/sequential counts, structured classify_tool_batch logs | Metrics: parallel_tool_pct, sequential_tool_pct, average parallel batch size. Alert on high sequential ratio (LLM requesting side-effect tools frequently). |
| **M11** (Observability) | `route_back_envelope` dead-letter for unknown topics | Dead-letter dashboard shows back-router rejects separately from FSM guard rejects. |
| **M12** (Chaos Tests) | Per-task `CancellationToken` | Race condition tests: cancel token fired during tool execution. Verify token.check() raises TaskCancelledError between tool calls, not mid-tool. |
| **M12** (Chaos Tests) | `classify_tool_batch()` under load | Concurrent react_loops verify that parallel-safe classification is deterministic under high contention. |

**Total: 27 issues across 6 epics (E3.1-E3.6) + 9 issues in E3.7 wiring = 36 issues across 7 epics.**

---

## M4: SessionState Alignment

**Goal:** Fix split-brain risk between FSM local objects and SessionState
sections. Route cognitive writes through writer/manager path. Enable
config-driven prompt section reads.

**Gate:** TaskBridge bound to real SS sections. Control extension state
mirrored to SS. Cognitive tool writes go through writer port. Prompt builder
uses SS_READ_CONFIGS as executable read plan.

### M4 Context Table

| File | Lines | Current State | M4 Changes |
|------|------:|---------------|------------|
| `fsm/controller.py` | 1979 | `__init__` L260 creates `ConciergeControlExtension()`, L261 creates `TaskBridge()` -- both with no SS binding. `set_session_state` L396-403 stores `_ss` for reads but does NOT rebind task_bridge or control_ext. L499 calls `_control_ext.set_fsm_state()`, L785 `.set_complexity_tier()`, L868/924/1098/1103/1195 `.add/remove_active_task()`. L870 `.dispatch_task()`, L1104 `.complete_task()`, L1199 `.cancel_task()` | E4.1: modify `set_session_state` to rebind TaskBridge sections and sync ControlExtension. Add `_sync_control_to_ss()` hook. |
| `fsm/task_bridge.py` | 407 | `__init__` accepts optional `task_state`/`task_artifacts` args; creates LOCAL fallback `TaskStateSection()` / `TaskArtifactsSection()` when None (always None in practice -- controller passes nothing). Lifecycle methods (`dispatch_task`, `activate_task`, `suspend_task`, `resume_task`, `complete_task`, `fail_task`, `cancel_task`, `mark_presented`, `prune`) all write to these local instances. | E4.1.1: add `rebind(task_state_section, task_artifacts_section)` method so bootstrap can wire real SS sections. |
| `fsm/control_extension.py` | 200 | Pure in-memory wrapper with 3 fields: `_fsm_state` (str), `_active_task_ids` (list), `_complexity_tier` (str). Methods: `set_fsm_state()`, `add_active_task()`, `remove_active_task()`, `set_complexity_tier()`, `snapshot()`. Docstring says "does NOT modify ControlSection" and "POC extension is 3 fields -- not worth schema churn". NO connection to SS `control` section. | E4.1.2: add `bind_control_section(control_section)` + `sync()` that mirrors 3 fields into ControlSection metadata. |
| `sessionstate/sections/control.py` | 1270 | ControlSection (L285+) tracks `_agent_leases`, `_flow_state`, `_turn_lock`, `_intents`, `_domains`, `_safety`. Has NO fields for fsm_state, active_task_ids, complexity_tier. Has `get_metadata()` L759 that returns dict. | E4.1.2: add `set_fsm_overlay(fsm_state, active_task_ids, complexity_tier)` or use metadata sub-dict. |
| `sessionstate/sections/task_state.py` | ~400 | TaskStateSection (L114+): `dispatch()`, `update_status()` L265, `get_active()` L332, `get_by_id()` L340, `clear()` L202. Same API TaskBridge calls. | E4.1.1: no change needed -- section itself is fine; problem is TaskBridge creating a duplicate instance. |
| `sessionstate/sections/task_artifacts.py` | ~370 | TaskArtifactsSection (L87+): `add_artifact()` L190, `get_all()` L254, `evict_to_warm()` L331, `clear()` L171. Same API TaskBridge calls. | E4.1.1: no change needed -- same as task_state. |
| `sessionstate/manager.py` | 1557 | `get_section(name)` L621 returns section from HOT/WARM tier. `mutate(section, operation, data, ...)` L779 does MutationGuard preflight, `_apply_mutation` L917, SizeTracker update, pressure management. `_apply_mutation` L917-1028 dispatches to section methods. Tools bypass all of this. | E4.2: tools must call `mutate()` instead of direct section method calls. |
| `sessionstate/ports/writer.py` | 878 | IWriterPort ABC with `request_mutation(MutationRequest) -> MutationResponse`, `batch_mutations(BatchRequest) -> BatchResult`, `validate_writer(writer_id) -> WriterAuthorization`. Full dataclass hierarchy: MutationRequest, MutationResponse, BatchRequest, BatchResult. `stop_on_rejection` in BatchRequest. | E4.2, E4.3: tools and bundle tool route through this port. |
| `sessionstate/adapters/direct_writer.py` | 569 | DirectWriterAdapter implements IWriterPort. `request_mutation` L163+: check expiration -> validate writer -> MutationGuard.preflight -> manager.mutate(). `batch_mutations` L339+: iterate requests, apply sequentially, stop_on_rejection logic, cancel remaining on rejection. | E4.3: bundle tool wires through `batch_mutations`. |
| `tools/implementations.py` | 1045 | 6 cognitive tools + 3 control tools + recall/summarize/dispatch/discover/invoke/fabric. ALL cognitive tools call `ctx.session_manager.get_section("xxx")` then mutate section directly: `update_beliefs` L132 `beliefs_section.add_fact()`, `update_scoreboard` L181 `scoreboard.push_question()`, `update_clarifications` L235 `clarifications.request()`, `update_narrative` L307 `narrative.create_thread()`, `refine_affect` L379 `affect.update()`, `promote_belief` L429 `beliefs.update_confidence()`. NONE call `manager.mutate()` or IWriterPort. | E4.2: refactor all 6 cognitive tools to route writes through writer port. |
| `prompt/builder.py` | 556 | `SSReadConfig` dataclass L58-69: section, read_mode ("full"/"slim"/"skip"), history_window. `SS_READ_CONFIGS` L77-170: 10 PromptMode mappings with section lists. `build()` L270+: stage 8 (L414-415) is comment-only placeholder "SS sections placeholder -- caller provides via history_messages". | E4.4: implement `_read_ss_sections()` that executes SS_READ_CONFIGS as a read plan in stage 8. |
| `actors/front.py` | 946 | `_extract_scenario_data` L60-220: ad-hoc per-mode `_safe_get_section` calls for control (L112), narrative (L133), task_state (L152,177), clarifications (L188). L534-539: only uses SS_READ_CONFIGS for history_window extraction. `front_handler` L426+: reads affect (L331), clarifications (L341,508), task_state (L356,734), control (L367,515), history (L382). | E4.4: migrate ad-hoc reads to builder-driven execution of SS_READ_CONFIGS. |
| `kernel/bootstrap.py` | 841 | `start_kernel` L101+: creates FSM L120, wires history_sink L123-127, calls `fsm.set_session_state(session_state)` L130. Creates ToolContext with `session_manager=session_state` L134-143. Does NOT pass SS sections to TaskBridge or ControlExtension. | E4.1: add TaskBridge rebind + ControlExtension bind after set_session_state. E4.2: add writer_port to ToolContext. |
| `config/defaults.yaml` | 584 | `front.history_window_fallback: 20` L48, `front.default_tier: "LOW"` L51, `front.default_affect_confidence: 1.0` L54. No LLM-writable allowlist or system-owned section config. | E4.2.2: add `session_state.llm_writable_sections` list. |

### M4 Split-Brain & Bypass Inventory

**SS Architecture Reference (from code audit):**

- **15 total sections** in `sizetracker.py` `SECTION_BUDGETS`:
  - HOT (10): control(8KB), beliefs_active(8KB), scoreboard(6KB),
    history_active(8KB), clarifications(4KB), affective_now(4KB),
    narrative_active(8KB), meta(2KB), task_state(4KB), task_artifacts(4KB)
    -- sum = 56KB
  - WARM (5): beliefs_history(12KB), history_recent(16KB), persona(8KB),
    telemetry(4KB), artifacts_warm(8KB) -- sum = 48KB
  - Grand total of individual budgets: 104KB. Total LIMIT is 96KB
    (config-backed). Oversubscription is by design -- sections rarely
    fill to max simultaneously; pressure triggers migration/eviction.
- **Budget discrepancy**: `hot.py` L85 says narrative_active = 4KB;
  `sizetracker.py` (authoritative -- used by MutationGuard) says 8KB.
  Similarly `warm.py` says telemetry = 8KB / history_recent = 20KB, but
  sizetracker says telemetry = 4KB / history_recent = 16KB. Sizetracker
  is canonical because MutationGuard and EvictionEngine consume it.
- **Prompt API heterogeneity**: Only task_state and task_artifacts have
  `to_prompt()`. history_active has `format_for_prompt(window=N)`. All
  others expose data through section-specific getters (get_facts,
  get_referents, get_pending, get_metadata, etc.) or `to_flatbuffer()`.
  No section has `snapshot()`. See E4.4.1 section rendering table.
- **apply() dispatch**: All sections have `apply(operation, data)` method
  that dispatches to section methods. `_apply_mutation` uses this as
  fallback for operations not explicitly handled (e.g., create_thread,
  push_question, add_referent, request).
- **Factory modes**: `SessionStateFactory.create_standalone()` (SQLite),
  `create_for_testing()` (in-memory), `create_with_ports()` (production).
  Standalone already creates `DirectWriterAdapter` + `MutationGuard`.

### SessionState Ownership Matrix

**This is the source of truth.** Every section, who fills it, how, who reads
it, through what API, and what is currently broken.

**Legend:**

- **Writer ID**: who owns the write path
- **Mechanism**: how data gets into the section today
- **Reader ID**: who consumes the data
- **Read API**: what method/attribute the reader calls
- **Bug**: known divergence (SB = split-brain, BP = bypass, PH = placeholder, NI = not implemented)

---

#### HOT CORE -- 10 sections (56KB budget)

**1. control (8KB) -- NEVER EVICT**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Orchestration state: agent leases, flow state, turn lock, intents, domains, safety band. After M4: also fsm_state, active_task_ids, complexity_tier via overlay. |
| **Writer 1** | **Phase 1 (FSM)** -- designed to write intent_classification, domain_context, safety_band to SS control. **NOT IMPLEMENTED** in POC: `_run_phase1()` (controller.py L763-795) runs classification but only stores result as metadata on history entry and sets `_control_ext.set_complexity_tier()`. Zero writes reach SS control section. |
| **Writer 2** | **FSM ConciergeControlExtension** -- writes fsm_state (L499), active_task_ids (L868/924/1098/1103/1195), complexity_tier (L785). All writes are **in-memory only** on `_control_ext` object. ControlSection in SS has NO corresponding fields. **Bug: SB2** |
| **Writer 3** | **System/Manager** -- `register_agent()` via control.apply("register_agent", ...) for agent lease management. |
| **Reader 1** | **Front actor** -- `_safe_get_section(ss, "control")` at L112 (pending_results for PRESENT mode), L367/515 (domain extraction for mode resolution). Reads from SS, never sees FSM state. |
| **Reader 2** | **Back actor** -- `_get_safety_band(control)` at back.py L202: reads `control.safety.band`. |
| **Prompt API** | `get_metadata()` returns dict. NO `to_prompt()`. E4.4.1 renderer must format metadata dict. |
| **M4 Fix** | E4.1.2: bind ConciergeControlExtension to real SS ControlSection. Add `_fsm_overlay` dict. |

**2. beliefs_active (8KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Current session beliefs -- SVO triples (subject-predicate-object) with confidence scores, entity refs, mentioned time/location. |
| **Writer 1** | **Phase 1 (FSM)** -- designed to write entity extractions as initial beliefs. **NOT IMPLEMENTED** in POC. |
| **Writer 2** | **Front LLM tool `update_beliefs`** -- `beliefs_section.add_fact(subject, predicate, obj, confidence, source)` at implementations.py L132-167. Also updates existing fact confidence if SPO match found. **Bug: BP1** (bypasses MutationGuard + SizeTracker). |
| **Writer 3** | **Front LLM tool `promote_belief`** -- `beliefs.update_confidence(id, new_confidence)` at implementations.py L435-467. **Bug: BP6** (bypasses MutationGuard). |
| **Reader 1** | **Back actor** -- `_to_prompt(beliefs)` at back.py L187-192. Calls `hasattr(section, "to_prompt")` -- returns **empty string** because beliefs_active has NO `to_prompt()`. Beliefs are INVISIBLE to Back. |
| **Reader 2** | **Front actor** -- via SS_READ_CONFIGS (builder.py L78). **NOT IMPLEMENTED** (PH1). No ad-hoc read in current front.py. |
| **Reader 3** | **`summarize_context` tool** -- reads via `get_metadata()`. |
| **Prompt API** | NO `to_prompt()`. Has: `find_by_subject()`, `find_by_predicate()`, `get_fact()`, `get_pinned_fact_ids()`, `get_metadata()`, `get_entity()`, `get_mentioned_time()`, `get_mentioned_location()`. E4.4.1 renderer must format facts as SVO lines. |
| **Demotion** | beliefs_active -> beliefs_history (WARM) via MigrationEngine when HOT pressure high. |
| **M4 Fix** | E4.2.3: route writes through writer port. E4.4.1: implement beliefs renderer. |

**3. scoreboard (6KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Discourse state -- QUD stack (questions under discussion), referent resolution (pronoun -> entity), topic stack, salience map, current user intent. |
| **Writer 1** | **Phase 1 (FSM)** -- designed to write intents[], entities[], salience_map{}. **NOT IMPLEMENTED** in POC. |
| **Writer 2** | **Front LLM tool `update_scoreboard`** -- `push_question()`, `pop_question()`, `add_referent()`, `push_topic()` at implementations.py L181-227. **Bug: BP2** (bypasses MutationGuard). |
| **Reader 1** | **FSM** -- controller.py L937: reads `scoreboard.list_referents()` to inject referent map into task dispatch payload for Back actor. |
| **Reader 2** | **Back actor** -- `_get_referents(scoreboard)` at back.py L194: `scoreboard.get_referents()` for pronoun resolution during task execution. |
| **Reader 3** | **Front actor** -- via SS_READ_CONFIGS (builder.py L78). **NOT IMPLEMENTED** (PH1). |
| **Prompt API** | NO `to_prompt()`. Has: `get_referents()`, `list_referents()`, `get_metadata()`, `_qud_stack`, `_topic_stack`. `apply()` dispatches: push_question, answer_question, add_referent, set_salience, push_topic, set_user_intent. |
| **M4 Fix** | E4.2.3: route writes through writer port. E4.4.1: implement scoreboard renderer. |

**4. history_active (8KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Recent conversation turns as TypedHistoryEntry objects. Each entry has turn_number, entry_type (user/assistant/system/tool), role, text, timestamp, source, task_id, metadata. |
| **Writer** | **FSM (sole writer)** -- `_history_sink.add_turn()` at controller.py L1528-1535. Bootstrap wires at L123-127: `fsm.set_history_sink(history_section)`. FSM builds TypedHistoryEntry in `_write_history()` L536-550, pushes to SS at turn completion. Phase 1 metadata attached to user entries. |
| **Reader 1** | **Front actor** -- `_get_history_active(ss)` at front.py L375-392: reads `get_typed_entries()` for `build_chat_history()`. Used as chat message array for LLM. |
| **Reader 2** | **Back actor** -- `_get_history_entries(history)` at back.py L228-237: reads 5 recent entries via `get_typed_entries()` / `entries` / `get_all()`. |
| **Reader 3** | **FSM** -- controller.py L951: reads for narrative thread name injection. |
| **Prompt API** | `format_for_prompt(window=N)` at L1122 (NOT `to_prompt()`). Also `get_typed_entries()`. E4.4.1 renderer must use `format_for_prompt(window=config.history_window)`. |
| **Demotion** | history_active -> history_recent (WARM) via MigrationEngine. Max 10 turns in HOT, older compress and demote. |
| **No M4 change** | History write path is already clean (FSM sole writer via direct section method). No tool bypass issue. |

**5. clarifications (4KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Semantic gaps in user intent. Each Clarification has: id, agent_id, question, options, priority (NORMAL/HIGH/URGENT), related_entity, related_intent, status (pending/answered/cancelled/expired), is_blocking. |
| **Writer** | **Front LLM tool `update_clarifications`** -- `clarifications.request(agent_id, question, priority, ...)` and `clarifications.answer(id, answer)` at implementations.py L235-297. **Bug: BP3** (bypasses MutationGuard). |
| **Reader 1** | **Front actor** -- `_extract_scenario_data` L188-191: `get_top_blocking()` for CLARIFY_ASK mode. L341: `_get_clarification_state()` builds dict from pending/blocking counts. L508: reads for clarify_depth. |
| **Reader 2** | **Front actor** -- via SS_READ_CONFIGS (CLARIFY_ASK, CLARIFY_RESOLVE, INTERRUPT modes). **NOT IMPLEMENTED** (PH1). |
| **Prompt API** | NO `to_prompt()`. Has: `get_pending()`, `get_answered()`, `get_blocking()`, `get_urgent()`, `get_high_priority()`, `get_options(id)`, `get_metadata()`. `apply()` dispatches: request, answer, cancel, expire, expire_old, set_blocking, clear_blocking. |
| **M4 Fix** | E4.2.3: route writes through writer port. E4.4.1: implement clarifications renderer. |

**6. affective_now (4KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Current emotional state: primary_emotion, intensity, valence, arousal, confidence, source. Drives affect band computation which controls prompt tone. |
| **Writer 1** | **Phase 1 (FSM)** -- designed to write primary_emotion, confidence, valence, arousal from UltraBERT classification. **NOT IMPLEMENTED** in POC: `_run_phase1()` classifies but never writes to SS affective_now section. |
| **Writer 2** | **Front LLM tool `refine_affect`** -- `affect.update(emotion, intensity, valence, arousal, confidence, source)` at implementations.py L379-418. Designed as Phase 1 override (Write-then-Refine pattern). **Bug: BP5** (bypasses MutationGuard). |
| **Reader** | **Front actor** -- `_get_affect_dict(ss)` at front.py L330-336: reads section attributes to compute affect band (used by builder for tone/depth). |
| **Prompt API** | NO `to_prompt()`, NO `to_dict()` on section class. Has: `_current_emotion`, `_intensity`, `_valence`, `_arousal`, `_confidence`, `_source` attributes, plus `to_flatbuffer()`. `apply()` dispatches custom operations. |
| **M4 Fix** | E4.2.3: route writes through writer port. E4.4.1: implement affect renderer from attributes. |

**7. narrative_active (8KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Conversation thread tracking. Each NarrativeThread has: id, title, goal, status (active/paused/resolved/archived), related_entities, related_intents, turn numbers. Supports multi-thread conversations. |
| **Writer 1** | **Front LLM tool `update_narrative`** -- `narrative.create_thread()`, `.switch_to()`, `.resolve_thread()` at implementations.py L307-377. **Bug: BP4** (bypasses MutationGuard). |
| **Writer 2** | **FSM** -- `narrative.record_turn(self._turn_number)` at controller.py L1728-1730. Updates primary thread's last_active_turn. Also bypasses MutationGuard but is a lightweight update. |
| **Reader 1** | **Front actor** -- `_extract_scenario_data` L133: reads active thread name for scenario data. |
| **Reader 2** | **FSM** -- controller.py L951: reads `narrative.get_active_thread_name()` to inject thread context into task dispatch for Back. |
| **Prompt API** | NO `to_prompt()`. Has: `get_thread(id)`, `get_active_thread_name()` (via apply), `_primary_thread`, `_thread_index`. `apply()` dispatches: create_thread, switch_to, pause_thread, resolve_thread, archive_thread, update_thread, record_turn, clear. |
| **M4 Fix** | E4.2.3: route LLM writes through writer port. E4.4.1: implement narrative renderer. |

**8. meta (2KB) -- NEVER EVICT**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Session metadata: identity (session_id, user_id, device_id), lifecycle (created_at, last_active, ttl), memory usage (hot/warm/total utilization), version info (schema, protocol). |
| **Writer** | **System/Manager** -- auto-initialized during `manager.start()`. Updated by SizeTracker sync. Contains: SessionIdentity, SessionLifecycle, MemoryUsage, VersionInfo, SchemaInfo, ExtensionInfo dataclasses. NO LLM writes (system-owned). |
| **Reader** | **Manager internal** -- used in checkpoint metadata. Potentially Front via SS_READ_CONFIGS (STANDARD mode includes it as "skip" or "slim"). Currently **no actor reads meta**. |
| **Prompt API** | `to_dict()` at L167/263/413/458 (nested dataclass to_dict). `get_metadata()` L828. `get_identity()`, `get_lifecycle()`, `get_memory()`, `get_version()`. |
| **No M4 change** | System-owned, no write path issues. E4.4.1 renderer uses `get_metadata()`. |

**9. task_state (4KB) -- NEVER EVICT**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Active task tracking: each TaskStateEntry has task_id, action, status (pending/dispatched/active/suspended/completed/failed/cancelled), progress_pct, pending_hil, depends_on. Critical for HITL recovery. |
| **Writer** | **FSM/TaskBridge** -- `dispatch_task()`, `activate_task()`, `suspend_task()`, `resume_task()`, `complete_task()`, `fail_task()`, `cancel_task()`, `mark_presented()`, `prune()`. Controller calls at L870, L1104, L1199. **Bug: SB1** -- TaskBridge writes to LOCAL fallback instance, not real SS section. |
| **Reader 1** | **Front actor** -- `_extract_scenario_data` L152/177 (task status for PRESENT/WEAVE modes), L356 (task count), L734 (pending results). |
| **Reader 2** | **Back actor** -- `_to_prompt(task_state)` at back.py L187: calls `task_state.to_prompt()` which renders "[TASKS]" block. **Works correctly** (task_state has `to_prompt()`). But returns empty because SB1 means the SS instance has no tasks. |
| **Reader 3** | **Orchestrator** -- dependency checks via `get_by_id()`, `get_active()`. |
| **Prompt API** | `to_prompt()` L368 (full), `to_slim_prompt()` (active only). Also: `get_active()`, `get_by_id()`, `get_suspended()`, `count_by_status()`, `has_active_tasks()`. |
| **M4 Fix** | E4.1.1: rebind TaskBridge to real SS sections. After M4, Back sees dispatched tasks. |

**10. task_artifacts (4KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Task output artifacts: confirmation codes, receipts, summaries. Each TaskArtifactEntry has artifact_id, task_id, type (TEXT/CONFIRMATION/RECEIPT/SUMMARY/LIST/ERROR/MEDIA_REF), content, presented_at_turn. Unpresented artifacts NEVER evicted. |
| **Writer** | **FSM/TaskBridge** -- `add_artifact()` after task completion. **Bug: SB1** -- same split-brain as task_state. |
| **Reader 1** | **Back actor** -- `_to_prompt(task_artifacts)` at back.py L187: calls `task_artifacts.to_prompt()` which renders "[ARTIFACTS]" block. Returns empty due to SB1. |
| **Reader 2** | **Front actor** -- via SS_READ_CONFIGS (PRESENT, WEAVE, INTERRUPT, ERROR modes). **NOT IMPLEMENTED** (PH1). |
| **Prompt API** | `to_prompt()` L278 (full), `to_slim_prompt()` (IDs and types). Also: `get_all()`, `get_by_id()`, `get_by_task()`, `get_unpresented()`. |
| **Demotion** | task_artifacts -> artifacts_warm (WARM) after presentation + 10 turns via `evict_to_warm()`. |
| **M4 Fix** | E4.1.1: rebind TaskBridge to real SS sections. |

---

#### WARM TIER -- 5 sections (48KB budget)

**11. beliefs_history (12KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Archive of demoted beliefs from beliefs_active. Older/lower-confidence facts migrate here when HOT pressure rises. |
| **Writer** | **MigrationEngine** -- `accept_demoted()` operation via `manager.mutate("beliefs_history", "accept_demoted", data)`. Triggered by HOT pressure or turn completion. |
| **Reader** | **None currently** in actors. Designed for long-term belief recall (future: `recall_memory` tool could query). |
| **No M4 change** | System-owned write path (migration). No LLM write access. |

**12. history_recent (16KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Compressed/summarized older turns from history_active. CompressedTurn entries retain: entities, intents, key phrases, user/assistant summaries. Full text dropped. |
| **Writer** | **MigrationEngine** -- `accept_demoted()` with compressed turns. Triggered when history_active exceeds 10 turns. Also supports `add_compressed`, `add_summarized`, `set_session_summary` operations. |
| **Reader** | **None currently** in actors. Designed for context recovery on session resume. |
| **No M4 change** | System-owned write path. |

**13. persona (8KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Family/user preferences loaded at session start: family profile, dietary restrictions, payment methods, accessibility settings, session config, communication style. |
| **Writer** | **Demo coordinator** -- `persona_section.set_preference()` at coordinator.py L448-471. Loads Smith family profile, session config, active member, preloaded memories. Written once at session initialization, generally static after that. |
| **Reader 1** | **Front actor** -- `_extract_family_context(ss)` at front.py L215-279: reads `persona._preferences` to build family context (names, dietary, location, timezone, communication style). |
| **Reader 2** | **Back actor** -- `_get_persona_prefs(persona)` at back.py L215-223: reads payment_method, dietary, accessibility for task execution constraints. |
| **Prompt API** | `set_preference(key, value)`, `get(key)` or attribute access. `apply()` dispatches: add_vocabulary and custom operations. |
| **No M4 change** | Loaded at init, read-only during session. System-owned. |

**14. telemetry (4KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Turn timing data and error tracking for diagnostics. Records turn latency, phase durations, error counts. |
| **Writer** | **System/Manager** -- `manager.mutate("telemetry", "record_turn", {...})` and `"record_error"` operations. Called internally during turn processing. |
| **Reader** | **None currently** in actors. Designed for observability dashboards and perf monitoring. First to evict (lowest priority). |
| **No M4 change** | System-owned, no LLM access needed. |

**15. artifacts_warm (8KB)**

| Aspect | Detail |
|--------|--------|
| **Purpose** | Archive of evicted task artifacts from task_artifacts (HOT). Artifacts land here after being presented to user for 10+ turns. |
| **Writer** | **EvictionEngine/MigrationEngine** -- accepts evicted artifacts via `accept_demoted()`. |
| **Reader** | **None currently** in actors. Designed for artifact recall if user asks about past task results. |
| **No M4 change** | System-owned write path. |

---

### SS Data Flow Diagram (per turn)

```
User Input
    |
    v
[Phase 1 - UltraBERT] ----writes--> scoreboard (intents, entities, salience)
    |                   ----writes--> affective_now (emotion, valence, arousal)
    |                   ----writes--> control (intent, domain, safety_band)
    |                   ** ALL 3 WRITES NOT IMPLEMENTED IN POC **
    |
    v
[TurnLock released]
    |
    v
[Front LLM] ----reads----> ALL 10 HOT sections via SS_READ_CONFIGS (PH1: NOT IMPLEMENTED)
    |         ----reads----> persona (WARM, family context)
    |         ----writes---> beliefs_active   (via update_beliefs tool,    BP1)
    |         ----writes---> scoreboard       (via update_scoreboard tool, BP2)
    |         ----writes---> clarifications   (via update_clarifications,  BP3)
    |         ----writes---> narrative_active  (via update_narrative tool,  BP4)
    |         ----writes---> affective_now    (via refine_affect tool,     BP5)
    |         ----writes---> beliefs_active   (via promote_belief tool,    BP6)
    |         ** ALL WRITES BYPASS MutationGuard + SizeTracker **
    |
    v (if task dispatch)
[FSM] ----reads----> scoreboard (referent injection for Back)
    | ----reads----> narrative_active (thread name injection for Back)
    | ----writes---> task_state (via TaskBridge -- SB1: LOCAL instance)
    | ----writes---> control (via ControlExtension -- SB2: in-memory)
    | ----writes---> history_active (sole writer, clean path)
    | ----writes---> narrative_active.record_turn (lightweight)
    |
    v
[Back LLM] ----reads----> beliefs_active (to_prompt -> EMPTY, no method)
    |        ----reads----> scoreboard (get_referents -> works)
    |        ----reads----> task_state (to_prompt -> EMPTY due to SB1)
    |        ----reads----> task_artifacts (to_prompt -> EMPTY due to SB1)
    |        ----reads----> control (safety_band -> works)
    |        ----reads----> history_active (typed entries -> works)
    |        ----reads----> persona (prefs -> works)
    |
    v
[MigrationEngine] ----HOT pressure--> beliefs_active -> beliefs_history
                  ----HOT pressure--> history_active -> history_recent
                  ----turn-based---> task_artifacts -> artifacts_warm
[EvictionEngine]  ----WARM pressure--> telemetry (first), beliefs_history,
                                        history_recent, persona (last)
                  ----evicts to-----> LOCAL COLD (K1 SQLite)
```

### SS Ownership Summary Table

| # | Section | Tier | Budget | Writer(s) | Write Mechanism | Reader(s) | Prompt API | Bug(s) |
|---|---------|------|-------:|-----------|-----------------|-----------|------------|--------|
| 1 | control | HOT | 8KB | FSM/ControlExt, Phase1, System | In-memory ext (SB2), Phase1 NI | Front, Back | `get_metadata()` | SB2, Phase1 NI |
| 2 | beliefs_active | HOT | 8KB | Front LLM tools, Phase1 | Direct section bypass (BP1,BP6), Phase1 NI | Back (empty!), Front (PH1) | No `to_prompt()` | BP1, BP6, PH1 |
| 3 | scoreboard | HOT | 6KB | Front LLM tool, Phase1 | Direct section bypass (BP2), Phase1 NI | FSM, Back, Front (PH1) | No `to_prompt()` | BP2, PH1 |
| 4 | history_active | HOT | 8KB | FSM (sole writer) | `_history_sink.add_turn()` | Front, Back, FSM | `format_for_prompt(window)` | None |
| 5 | clarifications | HOT | 4KB | Front LLM tool | Direct section bypass (BP3) | Front | No `to_prompt()` | BP3, PH1 |
| 6 | affective_now | HOT | 4KB | Front LLM tool, Phase1 | Direct section bypass (BP5), Phase1 NI | Front | No `to_prompt()` | BP5, PH1 |
| 7 | narrative_active | HOT | 8KB | Front LLM tool, FSM | Direct bypass (BP4), FSM record_turn | Front, FSM | No `to_prompt()` | BP4, PH1 |
| 8 | meta | HOT | 2KB | System/Manager | Auto-init at start() | None (internal) | `get_metadata()`, `to_dict()` | None |
| 9 | task_state | HOT | 4KB | FSM/TaskBridge | Local instance (SB1) | Front, Back (empty!), Orch | `to_prompt()`, `to_slim_prompt()` | SB1 |
| 10 | task_artifacts | HOT | 4KB | FSM/TaskBridge | Local instance (SB1) | Back (empty!), Front (PH1) | `to_prompt()`, `to_slim_prompt()` | SB1 |
| 11 | beliefs_history | WARM | 12KB | MigrationEngine | `accept_demoted()` | None | `apply()` | None |
| 12 | history_recent | WARM | 16KB | MigrationEngine | `accept_demoted()` | None | `apply()` | None |
| 13 | persona | WARM | 8KB | Demo coordinator | `set_preference()` at init | Front, Back | attribute access | None |
| 14 | telemetry | WARM | 4KB | System/Manager | `record_turn()`, `record_error()` | None | `apply()` | None |
| 15 | artifacts_warm | WARM | 8KB | EvictionEngine | `accept_demoted()` | None | `apply()` | None |

### Bug Impact Summary

| Bug | Sections Affected | Impact | M4 Fix |
|-----|-------------------|--------|--------|
| **SB1** | task_state, task_artifacts | FSM dispatches tasks into void -- Front/Back see empty task list and no artifacts. Entire task lifecycle invisible. | E4.1.1 |
| **SB2** | control | FSM state, complexity tier, active task IDs invisible to Front/Back. Mode resolution uses stale data. | E4.1.2 |
| **BP1-BP6** | beliefs_active, scoreboard, clarifications, narrative_active, affective_now | All cognitive writes bypass capacity enforcement. Size tracking drifts. No migration/eviction triggered. Budget violations go undetected. System could exceed 96KB silently. | E4.2.3 |
| **PH1** | All HOT sections | SS_READ_CONFIGS defined but not executed. Front does ad-hoc reads. Adding new section to prompt requires code change per mode instead of config entry. | E4.4.1-4.4.3 |
| **Phase1 NI** | control, scoreboard, affective_now | Phase 1 classification runs but results never written to SS. Front LLM starts with empty/default values for intent, emotion, safety band. Front must infer everything from scratch. | Future (post-M4) |

| ID | Problem | Write Path | Read Path | Divergence |
|----|---------|-----------|-----------|------------|
| SB1 | TaskBridge creates local `TaskStateSection()` / `TaskArtifactsSection()` instances | FSM lifecycle methods (`controller.py` L870, L1104, L1199) write to `_task_bridge._task_state` which is a LOCAL object created at `task_bridge.py` `__init__` when no args passed | Front actor reads `task_state` from SS manager via `_safe_get_section(ss, "task_state")` at `front.py` L152,177,356,734. Back actor reads from `back.py` L181. These return DIFFERENT section instances. | Task dispatched by FSM is invisible to Front/Back actors. Prompt sees empty task_state. |
| SB2 | ConciergeControlExtension is purely in-memory | Controller writes `_control_ext.set_fsm_state()` (L499), `.set_complexity_tier()` (L785), `.add_active_task()` (L868), `.remove_active_task()` (L924,1098,1103,1195) | Front reads `control` from SS at `front.py` L112,367,515. ControlSection has `_flow_state`, `_agent_leases`, `_turn_lock` etc. but NO `fsm_state`/`active_task_ids`/`complexity_tier` fields. | Front/Back never see FSM state, complexity tier, or active task list. Mode resolution and domain extraction use stale/empty control data. |
| BP1 | `update_beliefs` bypasses MutationGuard + SizeTracker | `implementations.py` L132: `beliefs_section.add_fact()` calls section method directly | MutationGuard never checks capacity. SizeTracker not updated. No pressure management triggered. | Size tracking becomes stale. Budget overflow undetected. No migration/eviction triggered when beliefs_active grows beyond 8KB. |
| BP2 | `update_scoreboard` bypasses MutationGuard + SizeTracker | `implementations.py` L181: `scoreboard.push_question()`, `.add_referent()`, `.push_topic()` | Same bypass as BP1 | Scoreboard 6KB budget unenforced at write time. |
| BP3 | `update_clarifications` bypasses MutationGuard + SizeTracker | `implementations.py` L235: `clarifications.request()`, `.answer()` | Same bypass as BP1 | Clarifications 4KB budget unenforced. |
| BP4 | `update_narrative` bypasses MutationGuard + SizeTracker | `implementations.py` L307: `narrative.create_thread()`, `.switch_to()`, `.resolve_thread()` | Same bypass as BP1 | Narrative 8KB budget unenforced (sizetracker.py: `narrative_active` = 8192 bytes; hot.py constant is stale at 4KB). |
| BP5 | `refine_affect` bypasses MutationGuard + SizeTracker | `implementations.py` L379-L418: `affect.update()` | Same bypass as BP1 | Affective_now 4KB budget unenforced. |
| BP6 | `promote_belief` bypasses MutationGuard + SizeTracker | `implementations.py` L429+: `beliefs.update_confidence()` | Same bypass as BP1 | Confidence update skips capacity check. |
| PH1 | SS_READ_CONFIGS declared but stage 8 is placeholder | `builder.py` L77-170: 10 mode configs defined. L414-415: "SS sections placeholder" comment. Front handler L534-539 only uses it for history_window. | `front.py` L100-220: `_extract_scenario_data` does ad-hoc per-mode `_safe_get_section` reads. NOT driven by SS_READ_CONFIGS. | Adding new SS section to prompt requires code change in front.py per-mode blocks instead of config addition to SS_READ_CONFIGS. |

### E4.1 -- FSM/SessionState Binding Fixes (2 issues)

Source: WB 16.3, 16.6

| # | Issue | Source |
|---|-------|--------|
| 4.1.1 | Rebind FSM TaskBridge to real SS task_state + task_artifacts sections | WB 16.6 |
| 4.1.2 | Mirror FSM control extension state into SS control section | WB 16.6 |

---

#### 4.1.1 -- Rebind FSM TaskBridge to real SessionState sections

**Problem:** (SB1) `ConciergeController.__init__` (`controller.py` L261) calls
`TaskBridge()` with no arguments. `TaskBridge.__init__` (`task_bridge.py` L40-55)
creates LOCAL fallback `TaskStateSection()` and `TaskArtifactsSection()` instances.
`set_session_state` (`controller.py` L396-403) stores the manager as `self._ss` but
never rebinds `_task_bridge._task_state` or `_task_bridge._task_artifacts` to the
real SS sections. Result: FSM lifecycle writes (`dispatch_task` L870, `complete_task`
L1104, `cancel_task` L1199) go to local objects that Front/Back actors
(`front.py` L152/177/356/734, `back.py` L181) never see.

**Changes:**

1. **`fsm/task_bridge.py`**: add `rebind(task_state, task_artifacts)` method.
   Accepts real section instances from SS manager. Replaces `_task_state` and
   `_task_artifacts` references. Copies any tasks dispatched before rebind
   (defensive -- in practice bootstrap wires before first user input). Add
   guard: raise if called after tasks already in ACTIVE state (prevents
   mid-flight rebind data loss).

2. **`fsm/controller.py`**: modify `set_session_state` (L396-403). After
   storing `self._ss = ss`, call:

   ```python
   ts = ss.get_section("task_state")
   ta = ss.get_section("task_artifacts")
   self._task_bridge.rebind(ts, ta)
   ```

3. **`kernel/bootstrap.py`**: no change needed -- `fsm.set_session_state(session_state)`
   at L130 already calls the method that will now trigger rebind.

**Acceptance:**

- `fsm._task_bridge._task_state is session_state.get_section("task_state")` after bootstrap
- `fsm._task_bridge._task_artifacts is session_state.get_section("task_artifacts")` after bootstrap
- Front/Back actors see tasks dispatched by FSM when reading `task_state` from SS
- Test: dispatch task via FSM, read `task_state` via `session_state.get_section("task_state")`, verify task entry exists

---

#### 4.1.2 -- Mirror FSM control extension state into SS control section

**Problem:** (SB2) `ConciergeControlExtension` (`control_extension.py` L1-200)
holds 3 fields (`_fsm_state`, `_active_task_ids`, `_complexity_tier`) purely
in-memory. The docstring explicitly says "does NOT modify ControlSection" (L30).
`ControlSection` (`sections/control.py` L285+) has NO corresponding fields.
Controller calls `_control_ext.set_fsm_state()` (L499),
`.set_complexity_tier()` (L785), `.add_active_task()` (L868) etc. but Front
reads `control` from SS at `front.py` L112/367/515 and never sees these values.

**Changes:**

1. **`sessionstate/sections/control.py`**: add `_fsm_overlay` dict field to
   `ControlSection.__init__` with keys `fsm_state`, `active_task_ids`,
   `complexity_tier`. Add `set_fsm_overlay(fsm_state, active_task_ids, tier)`
   method. Include overlay in `get_metadata()` return dict.
   Note: ControlSection currently has NO `to_prompt()` method -- overlay is
   exposed via `get_metadata()` only. If E4.4.1 renderer needs prompt text
   from control, it will use `get_metadata()` to extract and format. This avoids full schema churn -- the overlay is a metadata sub-dict, not a
   schema-level field.

2. **`fsm/control_extension.py`**: add `bind_control_section(section)` that
   stores a reference to the real ControlSection. Modify each mutator
   (`set_fsm_state`, `add_active_task`, `remove_active_task`,
   `set_complexity_tier`) to call `self._section.set_fsm_overlay(...)` after
   updating the local field. If no section bound (pre-bootstrap), silently skip.

3. **`fsm/controller.py`**: in `set_session_state` (L396-403), after storing
   `self._ss`, call:

   ```python
   control = ss.get_section("control")
   self._control_ext.bind_control_section(control)
   ```

**Acceptance:**

- After bootstrap, `session_state.get_section("control").get_metadata()` includes
  `fsm_state`, `active_task_ids`, `complexity_tier`
- Front actor reading `control` section sees current FSM state
- Test: set_fsm_state("DISPATCHING"), verify control section metadata shows "DISPATCHING"
- Test: add_active_task("task-1"), verify control section metadata shows ["task-1"]

---

### E4.2 -- Write Path Enforcement (4 issues)

Source: WB 16.3, 16.5, 16.6

| # | Issue | Source |
|---|-------|--------|
| 4.2.1 | Add writer_port to ToolContext for managed writes | WB 16.6 |
| 4.2.2 | Define LLM-writable allowlist in config | WB 16.5 |
| 4.2.3 | Refactor 6 cognitive tools to route writes through writer port | WB 16.6 |
| 4.2.4 | Add runtime guard rejecting LLM writes to system-owned sections | WB 16.5 |

---

#### 4.2.1 -- Add writer_port to ToolContext for managed writes

**Problem:** `ToolContext` (`implementations.py` L78-90) has `session_manager`
but no reference to `IWriterPort`. Tools can only bypass the managed write path
because no writer port is available. `bootstrap.py` L134-143 creates ToolContext
with `session_manager=session_state` but does not pass a writer port.

**Changes:**

1. **`tools/implementations.py`**: add `writer_port: Any = None` field to
   `ToolContext` dataclass (L82). Optional for backward compatibility -- tools
   that need managed writes check `ctx.writer_port is not None`.

2. **`kernel/bootstrap.py`**: after creating `session_state` and `DirectWriterAdapter`,
   pass `writer_port=writer_adapter` to both front and back `ToolContext` instances
   (L134-143). If no writer adapter exists (standalone mode), tools fall back to
   direct section mutation with a deprecation warning.

**Acceptance:**

- `ToolContext.writer_port` is non-None after bootstrap
- `writer_port.is_connected` returns True
- Test: create ToolContext with writer_port, verify attribute present

---

#### 4.2.2 -- Define LLM-writable allowlist in config

**Problem:** (WB 16.5) There is no formal definition of which SS sections the
LLM may write to. The 6 cognitive tools write to `beliefs_active`, `scoreboard`,
`clarifications`, `narrative_active`, `affective_now` -- these are the LLM-writable
sections. System-owned sections (`control`, `task_state`, `task_artifacts`, `meta`,
all WARM sections) should never accept LLM writes. Currently nothing enforces this.

**Changes:**

1. **`config/defaults.yaml`**: add under `session_state:` key:

   ```yaml
   session_state:
     llm_writable_sections:
       - beliefs_active
       - scoreboard
       - clarifications
       - narrative_active
       - affective_now
     system_owned_sections:
       - control
       - task_state
       - task_artifacts
       - meta
       - history_active
       - beliefs_history
       - history_recent
       - persona
       - telemetry
       - artifacts_warm
   ```

2. **`config/__init__.py`** or config dataclass: add corresponding typed fields
   so `get_config().session_state.llm_writable_sections` returns a `list[str]`.

**Acceptance:**

- `get_config().session_state.llm_writable_sections` returns the 5 LLM-writable section names
- `get_config().session_state.system_owned_sections` returns the remaining 10 section names
- Test: verify allowlist + system-owned = ALL_SECTIONS (15 total from sizetracker.py, no section unclassified)

---

#### 4.2.3 -- Refactor 6 cognitive tools to route writes through writer port

**Problem:** (BP1-BP6) All 6 cognitive tools in `implementations.py` call
`ctx.session_manager.get_section("xxx")` then mutate section objects directly.
This bypasses:

- **MutationGuard preflight** (`manager.py` L826-847): capacity check skipped
- **SizeTracker update** (`manager.py` L867): byte counts stale after write
- **Pressure management** (`manager.py` L871-880): no migration/eviction triggered
- **Observability**: no MutationApproved/Rejected events emitted

Affected tools and their bypass lines:

- `update_beliefs` L132: `beliefs_section.add_fact()` / `beliefs_section.update_confidence()`
- `update_scoreboard` L181: `scoreboard.push_question()` / `.add_referent()` / `.push_topic()`
- `update_clarifications` L235: `clarifications.request()` / `.answer()`
- `update_narrative` L307: `narrative.create_thread()` / `.switch_to()` / `.resolve_thread()`
- `refine_affect` L379: `affect.update()`
- `promote_belief` L429: `beliefs.update_confidence()`

**Changes:**

Each tool must be refactored from:

```python
section = ctx.session_manager.get_section("xxx")
section.some_method(args)
```

to:

```python
from poc.k1_poc.sessionstate.ports.writer import MutationRequest
request = MutationRequest.create(
    section="xxx",
    operation="some_operation",
    data={...},
    writer_id=f"tool:{ctx.actor}",
    cognitive_trace_id=ctx.cognitive_trace_id,
)
response = ctx.writer_port.request_mutation(request)
if not response.approved:
    return ToolResult(tool_name=..., status="error", error=response.reason)
```

**Per-tool mapping:**

| Tool | Section | Current Method | Writer operation | Data shape |
|------|---------|---------------|-----------------|------------|
| `update_beliefs` | beliefs_active | `add_fact(subject, predicate, obj, confidence, source)` | "add_fact" | `{"subject": ..., "predicate": ..., "obj": ..., "confidence": ..., "source": ...}` |
| `update_beliefs` (update) | beliefs_active | `update_confidence(id, confidence)` | "update" | `{"id": ..., "confidence": ...}` |
| `update_scoreboard` | scoreboard | `push_question()`, `pop_question()`, `add_referent()`, `push_topic()` | "update" | `{"qud_push": ..., "qud_pop": ..., "referent_updates": ..., "topic_shift": ...}` |
| `update_clarifications` | clarifications | `request()`, `answer()` | "update" | `{"gaps": [...], "resolved_gaps": [...]}` |
| `update_narrative` | narrative_active | `create_thread()`, `switch_to()`, `resolve_thread()` | "update" | `{"action": ..., "thread_id": ..., "summary": ...}` |
| `refine_affect` | affective_now | `update(emotion, intensity, valence, arousal, confidence, source)` | "update" | `{"emotion": ..., "intensity": ..., "valence": ..., "arousal": ..., "confidence": ..., "source": ...}` |
| `promote_belief` | beliefs_active | `update_confidence(id, confidence)` | "update" | `{"id": ..., "confidence": ...}` |

**Note:** `_apply_mutation` in `manager.py` L917-1028 already dispatches to section
methods via operation type. It handles: "set", "append"/"add_turn", "add_fact",
"update", "record_turn", "record_error", "accept_demoted", "clear", "delete".
For all OTHER operations (e.g., "create_thread", "push_question", "add_referent",
"request"), `_apply_mutation` falls through to `sec.apply(operation, data)` -- a
generic dispatch method present on all sections (scoreboard L1137, clarifications
L1082, narrative_active L1214, etc.). This means `manager.mutate("scoreboard",
"push_question", {...})` already works via the `apply()` fallback. For complex tools
(scoreboard, clarifications, narrative) that call multiple section methods per
invocation, either:
(a) Call `manager.mutate()` once per sub-action (simple, each gets own capacity check), or
(b) Use `batch_mutations` with individual operations per sub-action.

Option (b) is preferred -- it keeps `_apply_mutation` simple and lets each sub-action
get its own capacity check.

**Acceptance:**

- All 6 cognitive tools create `MutationRequest` objects and call `writer_port.request_mutation()`
- No tool calls `ctx.session_manager.get_section()` for write purposes (read-only access OK for pre-checks)
- MutationGuard preflight runs for every cognitive write
- SizeTracker updated after every cognitive write
- Test: call update_beliefs, verify MutationGuard was invoked (mock guard, assert called)
- Test: fill beliefs_active to near capacity, call update_beliefs, verify rejection returned

---

#### 4.2.4 -- Add runtime guard rejecting LLM writes to system-owned sections

**Problem:** (WB 16.5) Even after tools are refactored to use writer port, nothing
prevents a future tool or code path from writing to `control`, `task_state`, etc.
via the writer port. The writer port should enforce the LLM-writable allowlist
at the authorization layer.

**Changes:**

1. **`sessionstate/adapters/direct_writer.py`**: in `request_mutation` (L163+),
   after writer authorization check (step 2), add section allowlist check:

   ```python
   if request.writer_id.startswith("tool:"):
       allowlist = get_config().session_state.llm_writable_sections
       if request.section not in allowlist:
           return MutationResponse.rejected(
               request_id=request.request_id,
               section=request.section,
               operation=request.operation,
               reason=f"Section '{request.section}' is system-owned, not LLM-writable",
               category=RejectionCategory.AUTHORIZATION,
           )
   ```

2. **`sessionstate/ports/writer.py`**: add `AUTHORIZATION` rejection reason
   constant for section ownership violation (already has `RejectionCategory.AUTHORIZATION`).

**Acceptance:**

- Writer port rejects `MutationRequest(section="control", writer_id="tool:front")`
- Writer port allows `MutationRequest(section="beliefs_active", writer_id="tool:front")`
- Writer port allows `MutationRequest(section="control", writer_id="fsm")` (system writer)
- Test: attempt tool write to control section, verify RejectionCategory.AUTHORIZATION returned

---

### E4.3 -- Session Bundle Tool (3 issues)

Source: WB 16.5

| # | Issue | Source |
|---|-------|--------|
| 4.3.1 | Implement update_session_bundle tool with idempotency_key | WB 16.5 |
| 4.3.2 | Wire bundle tool through writer_port.batch_mutations | WB 16.5 |
| 4.3.3 | Add stop_on_rejection semantics with partial rollback info | WB 16.5 |

---

#### 4.3.1 -- Implement update_session_bundle tool

**Problem:** (WB 16.4, 16.5) LLM cannot safely write to multiple SS sections in
a single tool call. Each cognitive tool writes to exactly one section. If the LLM
needs to update beliefs + scoreboard + narrative in one turn, it must make 3
separate tool calls. This creates a window where SS is partially updated and
increases token cost from 3 tool call/result round-trips.

WB 16.5 recommends an `update_session_bundle` tool with:

- `mutations: list[{section, operation, data}]` -- ordered list of writes
- `idempotency_key: str` -- prevents duplicate application on retry
- `stop_on_rejection: bool` -- whether to abort remaining mutations on first failure

**Changes:**

1. **`tools/implementations.py`**: add new registered tool:

   ```python
   @_register("update_session_bundle")
   def execute_update_session_bundle(args: dict, ctx: ToolContext) -> ToolResult:
   ```

   Tool validates `mutations` array, checks `idempotency_key` against a
   per-session set (stored on ToolContext or session manager), and delegates
   to `ctx.writer_port.batch_mutations()`.

2. **Tool schema**: add to `tools/schemas.py` or equivalent:

   ```json
   {
     "name": "update_session_bundle",
     "description": "Write to multiple SS sections atomically",
     "parameters": {
       "mutations": [{"section": "str", "operation": "str", "data": "object"}],
       "idempotency_key": "str",
       "stop_on_rejection": "bool (default true)"
     }
   }
   ```

3. **`tools/tool_schemas.py`** or tool allowlist config: add `update_session_bundle`
   to the COGNITIVE tool group and Front actor allowlist.

**Acceptance:**

- LLM can call `update_session_bundle` with mutations array
- Duplicate idempotency_key returns cached result without re-applying
- Test: call with 3 mutations, verify all 3 applied to SS
- Test: call with same idempotency_key twice, verify no duplicate application

---

#### 4.3.2 -- Wire bundle tool through writer_port.batch_mutations

**Problem:** The bundle tool must use `IWriterPort.batch_mutations()` (defined in
`ports/writer.py` L714+) rather than calling `request_mutation` in a loop. This
ensures batch-level authorization, consistent trace ID, and aggregate result
tracking.

**Changes:**

1. **`tools/implementations.py`** (inside `execute_update_session_bundle`):
   Build `BatchRequest` from tool args:

   ```python
   from poc.k1_poc.sessionstate.ports.writer import BatchRequest, MutationRequest
   requests = []
   for m in mutations:
       requests.append(MutationRequest.create(
           section=m["section"],
           operation=m["operation"],
           data=m["data"],
           writer_id=f"tool:{ctx.actor}",
           cognitive_trace_id=ctx.cognitive_trace_id,
       ))
   batch = BatchRequest.create(
       requests=requests,
       writer_id=f"tool:{ctx.actor}",
       cognitive_trace_id=ctx.cognitive_trace_id,
       stop_on_rejection=args.get("stop_on_rejection", True),
   )
   result = ctx.writer_port.batch_mutations(batch)
   ```

2. **`DirectWriterAdapter.batch_mutations`** (`direct_writer.py` L339+): already
   implemented with correct stop_on_rejection logic. Verify it correctly handles
   the LLM-writable allowlist guard from E4.2.4 for each sub-request.

**Acceptance:**

- Bundle tool creates `BatchRequest` and calls `writer_port.batch_mutations()`
- Each mutation in batch goes through MutationGuard individually
- `BatchResult.responses` contains per-mutation MutationResponse
- Test: batch of 3 mutations, all to LLM-writable sections, verify 3 applied
- Test: batch with 1 mutation to system-owned section, verify rejection + remaining cancelled

---

#### 4.3.3 -- Add stop_on_rejection semantics with partial rollback info

**Problem:** WB 16.5 specifies `stop_on_rejection` semantics: if any mutation
in a bundle is rejected, remaining mutations should be cancelled. The tool result
must clearly communicate which mutations succeeded and which were cancelled so
the LLM can retry or adjust.

**Changes:**

1. **`tools/implementations.py`** (inside `execute_update_session_bundle`):
   Map `BatchResult` to `ToolResult`:

   ```python
   return ToolResult(
       tool_name="update_session_bundle",
       status="ok" if result.applied_count == result.total_requests else "partial",
       data={
           "applied": result.applied_count,
           "rejected": result.rejected_count,
           "cancelled": result.cancelled_count,
           "stopped_early": result.stopped_early,
           "details": [
               {"section": r.section, "status": r.status.value, "reason": r.reason}
               for r in result.responses
           ],
       },
   )
   ```

2. **`DirectWriterAdapter.batch_mutations`** (`direct_writer.py` L339+): verify
   that when `stop_on_rejection=True` and a mutation is rejected:
   - All subsequent mutations get `MutationStatus.CANCELLED`
   - `BatchResult.stopped_early = True`
   - Already-applied mutations are NOT rolled back (not atomic -- this is
     documented behavior per `ports/writer.py` implementation notes item 3)

**Acceptance:**

- Bundle with `stop_on_rejection=True`: first rejection cancels remaining
- Bundle with `stop_on_rejection=False`: continues processing after rejection
- ToolResult includes per-mutation status detail
- Test: 3 mutations, 2nd rejected, verify 1st applied + 2nd rejected + 3rd cancelled
- Test: 3 mutations, `stop_on_rejection=False`, 2nd rejected, verify 1st + 3rd applied

---

### E4.4 -- Prompt Builder SS Integration (3 issues)

Source: WB 16.3, 16.6

| # | Issue | Source |
|---|-------|--------|
| 4.4.1 | Implement _read_ss_sections renderer in DynamicPromptBuilder | WB 16.6 |
| 4.4.2 | Wire stage 8 to execute SS_READ_CONFIGS as actual read plan | WB 16.6 |
| 4.4.3 | Migrate front_handler ad-hoc SS reads to builder-driven rendering | WB 16.6 |

---

#### 4.4.1 -- Implement _read_ss_sections renderer in DynamicPromptBuilder

**Problem:** (PH1) The design doc (`concierge_poc_design_v2.md` L2880) specifies a
`_read_ss_sections(ss, configs, affect_band)` method that iterates
`SS_READ_CONFIGS[mode]`, calls `ss.get_section(name)`, and renders each section
to text. This method does not exist in `builder.py`. Stage 8 (L414-415) is a
comment: "SS sections placeholder".

**Section rendering heterogeneity (critical constraint from code audit):**

The 10 sections appearing in `SS_READ_CONFIGS` have INCONSISTENT prompt APIs:

| Section | `to_prompt()` | `to_slim_prompt()` | `format_for_prompt()` | Other API |
|---------|:---:|:---:|:---:|-----------|
| task_state | YES (L368) | YES | - | - |
| task_artifacts | YES (L278) | YES | - | - |
| history_active | - | - | YES (L1122, accepts `window` kwarg) | `get_typed_entries()` |
| beliefs_active | - | - | - | `get_fact_count()`, `find_by_subject()`, `get_pinned_fact_ids()`, `get_metadata()` |
| scoreboard | - | - | - | `get_referents()` (back.py uses this), `push_question()`, `push_topic()`, `get_metadata()` |
| clarifications | - | - | - | `get_pending()`, `get_blocking()`, `get_urgent()`, `get_options()` |
| narrative_active | - | - | - | `get_active_thread_name()` (via apply), thread data |
| affective_now | - | - | - | Only `to_flatbuffer()` -- front.py uses custom `_get_affect_dict()` |
| control | - | - | - | `get_metadata()` (L759) -- includes fsm_overlay after E4.1.2 |
| persona | - | - | - | `get()` / attribute access (back.py reads payment_method, dietary, accessibility) |

Current ad-hoc rendering evidence:

- `back.py` L187-192: `_to_prompt(section)` checks `hasattr(section, "to_prompt")`,
  returns "" if missing. So `_to_prompt(beliefs)` returns "" -- beliefs are currently
  INVISIBLE to Back actor prompt.
- `back.py` L194-200: `_get_referents(scoreboard)` uses `section.get_referents()`.
- `front.py` L331-336: `_get_affect_dict(ss)` calls `section.to_dict()` (actually
  likely calls underlying fields -- affective_now has no `to_dict` on the section
  itself, only `to_flatbuffer()`).

**Changes:**

1. **`prompt/builder.py`**: add `SECTION_RENDERERS` dispatch table and
   `_read_ss_sections` method:

   ```python
   # Dispatch table: section_name -> (full_renderer, slim_renderer)
   # Each renderer: (section, config) -> str
   SECTION_RENDERERS: dict[str, tuple[Callable, Callable]] = {
       "task_state":       (_render_task_state_full,  _render_task_state_slim),
       "task_artifacts":   (_render_task_artifacts_full, _render_task_artifacts_slim),
       "history_active":   (_render_history_full,     _render_history_slim),
       "beliefs_active":   (_render_beliefs_full,     _render_beliefs_slim),
       "scoreboard":       (_render_scoreboard_full,  _render_scoreboard_slim),
       "clarifications":   (_render_clarifications_full, _render_clarifications_slim),
       "narrative_active": (_render_narrative_full,   _render_narrative_slim),
       "affective_now":    (_render_affect_full,      _render_affect_slim),
       "control":          (_render_control_full,     _render_control_slim),
       "persona":          (_render_persona_full,     _render_persona_slim),
   }

   def _read_ss_sections(
       self,
       ss: Any,
       configs: list[SSReadConfig],
       affect_band: str,
   ) -> str:
   ```

   For each `SSReadConfig` in `configs`:
   - Skip if `read_mode == "skip"`
   - Call `ss.get_section(config.section)` (wrapped in try/except for missing sections)
   - Look up `(full_fn, slim_fn) = SECTION_RENDERERS[config.section]`
   - For `read_mode == "full"`: call `full_fn(section, config)`
   - For `read_mode == "slim"`: call `slim_fn(section, config)`
   - Assemble as labeled blocks: `## {section_name}\n{rendered_text}`

   Renderer implementations (10 pairs of full/slim):
   - `task_state`, `task_artifacts`: delegate to `section.to_prompt()` / `section.to_slim_prompt()`
   - `history_active`: call `section.format_for_prompt(window=config.history_window)`;
     slim mode uses `window=min(5, config.history_window)`
   - `beliefs_active` full: format facts from `section.facts` property as
     "- {subject} {predicate} {object} (confidence: {conf})" lines; include entity
     refs and mentioned time/location. Slim: fact count + pinned facts only.
   - `scoreboard` full: format referents from `section.get_referents()` (if method
     exists), current topic, QUD stack. Slim: current topic + referent count.
   - `clarifications` full: format pending from `section.get_pending()` +
     blocking from `section.get_blocking()`. Slim: count of pending.
   - `narrative_active` full: active thread name, goal, related entities.
     Slim: active thread name only.
   - `affective_now` full: extract emotion, intensity, valence, arousal from
     section attributes (matching front.py's `_get_affect_dict` pattern).
     Slim: "{emotion} ({intensity})" one-liner.
   - `control` full: format `section.get_metadata()` dict including fsm_overlay
     (from E4.1.2). Slim: fsm_state + safety band only.
   - `persona` full: format from `section.get()` or attribute access for
     payment_method, dietary, accessibility. Slim: key names only.

2. **`prompt/builder.py`**: add `ss` parameter to `build()` method signature
   (currently not accepted). Default to None for backward compatibility.

**Acceptance:**

- `_read_ss_sections` renders all sections listed in SS_READ_CONFIGS for given mode
- Sections with `read_mode="skip"` produce no output
- Sections with `read_mode="slim"` produce abbreviated output
- Missing sections are silently skipped (no crash)
- Sections WITHOUT `to_prompt()` render correctly via SECTION_RENDERERS dispatch
- history_active renders via `format_for_prompt(window=N)`, NOT `to_prompt()`
- Test: mock SS manager with 3 sections (task_state with to_prompt, beliefs_active
  without to_prompt, history_active with format_for_prompt), verify all 3 render

---

#### 4.4.2 -- Wire stage 8 to execute SS_READ_CONFIGS as actual read plan

**Problem:** Stage 8 in `build()` (L414-415) is currently:

```python
# Stage 8: SS sections placeholder -- caller provides via history_messages
# Full SS read is handled by front_handler via SS_READ_CONFIGS
```

This means the prompt builder assembles everything EXCEPT SS sections, and the
caller (front_handler) must manually read and inject SS data elsewhere.

**Changes:**

1. **`prompt/builder.py`** `build()` method: replace stage 8 comment with:

   ```python
   # Stage 8: Read and render SS sections per mode config
   if ss is not None:
       ss_configs = SS_READ_CONFIGS.get(mode, [])
       ss_block = self._read_ss_sections(ss, ss_configs, affect_band)
       if ss_block:
           prompt_parts.append(ss_block)
   ```

2. Update `build()` signature to accept `ss: Any = None`.

**Acceptance:**

- When `ss` is provided, stage 8 produces rendered SS section text
- When `ss` is None, stage 8 produces nothing (backward compatible)
- Rendered SS text appears in final `system_prompt` between scenario data (stage 7) and affect modifiers (stage 9)
- Test: call `build(mode=STANDARD, ss=mock_ss)`, verify system_prompt contains beliefs_active, scoreboard, etc.

---

#### 4.4.3 -- Migrate front_handler ad-hoc SS reads to builder-driven rendering

**Problem:** `front_handler` (`front.py` L426+) currently does ad-hoc SS reads
scattered across multiple functions:

- `_extract_scenario_data` (L60-220): per-mode `_safe_get_section` for control (L112),
  narrative (L133), task_state (L152/177), clarifications (L188)
- `_extract_family_context` (L222+): reads persona (L228)
- L508: reads clarifications for clarify_depth
- L515: reads control for domain
- L534-539: reads SS_READ_CONFIGS for history_window only

After E4.4.1 and E4.4.2, the builder handles SS reads internally. Front handler
should pass `ss` to `builder.build()` and remove duplicate reads.

**Changes:**

1. **`actors/front.py`**: modify `front_handler` call to builder (L558-570):

   ```python
   context = builder.build(
       mode=mode,
       affect_band=affect_band,
       history_messages=messages,
       all_tool_schemas=all_tool_schemas or [],
       scenario_data=scenario_data,
       clarify_depth=clarify_depth,
       domain=domain,
       affect_confidence=affect_confidence,
       tier=tier,
       ss=ss,  # NEW: pass SessionStateManager
   )
   ```

2. **`actors/front.py`**: remove SS reads from `_extract_scenario_data` that
   are now handled by builder stage 8. Keep only mode-specific payload extraction
   that reads from the envelope (not from SS). Sections that scenario_data reads
   for mode resolution (control for fsm_state, task_state for status) remain as
   lightweight pre-checks -- they are read-only and do not duplicate rendering.

3. **Phased migration**: do NOT remove all ad-hoc reads in one shot. First pass:
   add `ss=ss` to builder call and verify SS sections appear in prompt. Second
   pass: remove redundant reads from `_extract_scenario_data` one mode at a time,
   verifying prompt output matches before/after.

**Acceptance:**

- `builder.build()` receives `ss` parameter from front_handler
- SS sections rendered by builder appear in system_prompt
- Scenario data extraction no longer duplicates SS reads that builder handles
- Test: compare system_prompt output with and without migration, verify equivalent content
- No behavioral change in prompt assembly (same sections, same detail levels)

---

### M4 Implementation Order

1. **4.2.2** (define LLM-writable allowlist in config -- prerequisite for guards)
2. **4.2.1** (add writer_port to ToolContext -- prerequisite for tool refactor)
3. **4.1.1** (rebind TaskBridge to real SS sections -- fixes SB1)
4. **4.1.2** (mirror control extension to SS -- fixes SB2)
5. **4.2.3** (refactor 6 cognitive tools to use writer port -- fixes BP1-BP6)
6. **4.2.4** (add runtime guard for system-owned sections)
7. **4.3.1** (implement update_session_bundle tool)
8. **4.3.2** (wire through batch_mutations)
9. **4.3.3** (stop_on_rejection semantics)
10. **4.4.1** (implement _read_ss_sections renderer)
11. **4.4.2** (wire stage 8 to execute SS_READ_CONFIGS)
12. **4.4.3** (migrate front_handler ad-hoc reads -- last, most risk)
13. **4.5.1-4.5.9** (end-to-end wiring -- AFTER all E4.1-E4.4 issues complete)

### E4.5 -- End-to-End Wiring & System Integration

Source: Bootstrap analysis, tools/implementations.py, sessionstate/adapters/direct_writer.py, sessionstate/factory.py, fsm/task_bridge.py, fsm/control_extension.py, prompt/builder.py, actors/front.py, actors/back.py, demo/coordinator.py, kernel/bootstrap.py

**Why this epic exists:** E4.1-E4.4 fix fundamental split-brain bugs (SB1, SB2), eliminate all 6 mutation guard bypasses (BP1-BP6), create the session bundle tool, and implement SS-driven prompt assembly. But these changes touch EVERY layer of the running system simultaneously: the FSM, the tool execution layer, the prompt builder, and both actors. Without explicit wiring, M4 creates:

- A TaskBridge that is rebound to SS sections but whose lifecycle events are invisible to the M1 ledger (dispatch/complete/fail/cancel now write to real SS sections -- but does `_ledger_append()` still fire in the right order?)
- Writer port mutations that go through MutationGuard but produce no ledger events (M1 records FSM mutations, not tool mutations)
- A session bundle tool that handles batch mutations but is invisible to the M2 dead-letter pipeline if an invalid section is targeted
- SS_READ_CONFIGS driven prompt assembly that must work with the M3 `actors/shared.py::parse_envelope_payload()` and the M3-modified back handler signatures
- A control section overlay (E4.1.2) that carries FSM state but is not included in demo health checks

**Every M4 artifact must plug into the cumulative M1+M2+M3 infrastructure or the four milestones exist as disconnected layers.**

**System state after M1+M2+M3 (E1.4 + E2.5 + E3.7 wiring complete) -- what M4 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created          # M1 1.4.1
  -> LedgerMiddleware in bus middleware chain             # M1 1.4.4
  -> ConciergeController(bus, router)
     -> set_ledger(writer)                               # M1 1.4.1
     -> _ledger_append() in 11 handlers                  # M1 1.4.2
     -> _try_deserialize() bridge                        # M1 1.4.3
     -> _dispatch_envelope() flow:                       # M2 2.5.3
          topic_guard -> idempotency -> guard_dispatch -> handler
     -> FULL_GUARD_TABLE + _guard_dispatch()             # M2 2.1.1-2.1.2
     -> _publish_dead_letter() with ledger recording     # M2 2.5.2
     -> IdempotencyLedger                                # M2 2.3.2
     -> decide_response_final() + ResponseFinalEvent     # M2 2.3.1, 2.5.4
     -> Per-task CancellationToken in _cancel_tokens     # M3 3.2.2
  -> route_back_envelope() replaces direct back_handler  # M3 3.1.1-3.1.3
  -> DeadLetterConsumer subscribed to bus                 # M2 2.5.1
  -> Unknown back topics -> dead-letter pipeline         # M3 3.7.1
  -> builders auto-enrich legacy dicts                   # M1 1.4.5
  -> actors/shared.py: parse_envelope_payload,
       safe_get_section, never_cancel                    # M3 3.5.1-3.5.3
  -> SuspensionManager as sole resume-context owner      # M3 3.3.1
  -> classify_tool_batch() in react_loop                 # M3 3.4.2
  -> ReactResult carries parallel/sequential counts      # M3 3.7.4
  -> Demo: ledger health + /api/ledger/stats             # M1 1.4.6
  -> Demo: dead-letter health + /api/dead-letters        # M2 2.5.5
  -> Demo: parallel_tools_enabled in health check        # M3 3.7.4
  -> Fixtures: create_wired_fsm(with_ledger,
       with_dead_letter_consumer, with_cancel_tokens)    # M1-M3 fixtures
```

**M4 artifacts that must integrate into this M1+M2+M3-wired system:**

| M4 Artifact | Where It Lives After E4.1-E4.4 | M1+M2+M3 Touchpoint It Must Connect To |
|-------------|-------------------------------|----------------------------------------|
| `TaskBridge.rebind(task_state, task_artifacts)` | `fsm/task_bridge.py` | M1 `_ledger_append()` -- task lifecycle events must still be ledger-recorded after rebind; verify `_dispatch_envelope()` flow (M2) still sequences ledger-before-mutation |
| `ControlExtension.bind_control_section()` + `set_fsm_overlay()` | `fsm/control_extension.py`, `sections/control.py` | M3 `actors/shared.py::safe_get_section()` -- Front reads via shared utility; overlay must appear in section data; demo health check should expose overlay state |
| `writer_port` on ToolContext | `tools/implementations.py`, `kernel/bootstrap.py` | M2 dead-letter -- writer rejections (system-owned section targeted by LLM tool) should be auditable; M1 ledger -- mutation approvals/rejections should be traceable |
| 6 cognitive tools refactored to `writer_port.request_mutation()` | `tools/implementations.py` | M1 ledger -- MutationGuard preflight results (approved/rejected) should feed into ledger or structured logs for M11 observability |
| `session_state.llm_writable_sections` allowlist | `config/defaults.yaml` | M2 `_guard_dispatch()` pattern -- allowlist enforcement follows the same deny-by-default philosophy as guard table |
| `DirectWriterAdapter` authorization guard for tool: writers | `direct_writer.py` | M3 test fixtures -- `create_wired_fsm()` must include writer_port so tool tests have managed writes |
| `update_session_bundle` tool with `batch_mutations` | `tools/implementations.py` | M2 IdempotencyLedger -- bundle idempotency_key should integrate with existing dedup infrastructure |
| `DynamicPromptBuilder._read_ss_sections()` + stage 8 | `prompt/builder.py` | M3 `actors/shared.py` -- Front handler now passes `ss` to builder; builder reads sections that M4 E4.1.1 rebound TaskBridge populates with real data |
| Front handler migration from ad-hoc SS reads to builder-driven | `actors/front.py` | M3 conformance tests -- emission ordering tests (E3.6.1) must still pass after front_handler refactoring |

---

#### 4.5.1 -- Wire TaskBridge rebind into M1 ledger + M2 dispatch flow verification

**Problem:** E4.1.1 adds `TaskBridge.rebind(task_state, task_artifacts)` so the FSM writes to real SS sections instead of local fallbacks. Before M4, task lifecycle writes went to local objects AND `_ledger_append()` recorded them. After M4, task lifecycle writes go to REAL SS sections. The question: does `_ledger_append()` still fire in the correct sequence?

The M2 `_dispatch_envelope()` flow (2.5.3) sequences: topic_guard -> idempotency -> guard_dispatch -> handler body (which includes `_ledger_append()` + mutation). After M4, the handler body's mutation changes from local TaskBridge write to real SS section write. The ledger append must happen BEFORE the SS mutation (so crash recovery can replay), not after.

**What to do:**

1. Verify that in every FSM handler that calls TaskBridge methods (`dispatch_task` at L870, `complete_task` at L1104, `fail_task` at L1104, `cancel_task` at L1199, `suspend_task`, `resume_task`, `mark_presented`), the `_ledger_append()` call is BEFORE the TaskBridge method call:

   ```python
   # Correct order in _handle_task_complete:
   self._ledger_append(TaskCompletedEvent(...))  # 1. Record in ledger
   self._task_bridge.complete_task(task_id, ...)  # 2. Write to SS (now real via rebind)
   ```

   If any handler has the reverse order, fix it.

2. Add a test in `test_m04_wiring_regression.py`:
   - Create wired FSM with ledger + rebound TaskBridge
   - Dispatch task via FSM
   - Verify: ledger has `TaskCreated` event AND `session_state.get_section("task_state")` has the task entry
   - Both must be present (not just one)

3. Verify the `_dispatch_envelope()` flow (M2 2.5.3) doesn't interfere with rebind. The guard table validates state-topic combinations. Task events (`task.complete`, `task.failed`, `task.cancel`) should still pass guard table validation after M4.

**Files to verify:**

- `poc/k1_poc/fsm/controller.py` (every handler calling TaskBridge methods -- verify ledger ordering)

**Files to create:**

- `tests/poc/test_m04_wiring_regression.py` (initial test)

**Dependency:** E4.1.1 (TaskBridge rebind), M1 1.4.2 (_ledger_append), M2 2.5.3 (_dispatch_envelope)

**Acceptance:**

- `_ledger_append()` fires BEFORE `TaskBridge.complete_task()` / `fail_task()` / `cancel_task()` in every handler
- Ledger event + SS section entry both present after each lifecycle operation
- M2 guard table still validates task events correctly after rebind

---

#### 4.5.2 -- Wire control section overlay into demo health check and structured diagnostics

**Problem:** E4.1.2 adds `set_fsm_overlay()` on ControlSection and `bind_control_section()` on ConciergeControlExtension. After M4, the control section's `get_metadata()` includes `fsm_state`, `active_task_ids`, `complexity_tier`. But:

- M1 1.4.6's demo health check verifies ledger, not control section overlay
- M2 2.5.5's demo health check verifies dead-letters, not control overlay
- M3 3.7.4's demo health check verifies parallel_tools_enabled, not control overlay
- The demo `/api/status` endpoint has no visibility into FSM state via SS (it reads FSM directly)

After M4, the control section overlay is the canonical SS-accessible representation of FSM state. Demo diagnostics should use it.

**What to do:**

1. Extend demo Phase 5 health check to verify control section overlay:

   ```python
   control = self.session_state.get_section("control")
   if control and hasattr(control, "get_metadata"):
       meta = control.get_metadata()
       overlay = meta.get("fsm_overlay", {})
       checks["control_overlay_present"] = bool(overlay)
       checks["control_fsm_state"] = overlay.get("fsm_state", "UNKNOWN")
       self._record("phase5", "health", "check.control_overlay",
                     f"Control overlay: fsm_state={overlay.get('fsm_state')}, "
                     f"active_tasks={len(overlay.get('active_task_ids', []))}")
   ```

2. Add `/api/session/control` endpoint to demo web app:

   ```python
   @app.get("/api/session/control")
   async def get_control_state() -> dict:
       control = _coordinator.session_state.get_section("control")
       meta = control.get_metadata() if control else {}
       return {
           "fsm_overlay": meta.get("fsm_overlay", {}),
           "safety_band": meta.get("safety_band", "unknown"),
           "agent_leases": meta.get("agent_leases", []),
       }
   ```

3. Verify that `safe_get_section(ss, "control")` (M3 `actors/shared.py`) returns a section with the overlay intact. This is a read-only operation so no M3 code changes needed -- just verify in test.

**Files to modify:**

- `poc/k1_poc/demo/coordinator.py` (Phase 5 health check extension)
- `poc/k1_poc/demo/web/app.py` (add `/api/session/control` endpoint)

**Dependency:** E4.1.2 (control overlay), M1 1.4.6 (demo health pattern), M2 2.5.5 (demo health pattern), M3 3.7.4 (demo health pattern)

**Acceptance:**

- Demo health check reports `control_overlay_present=True` after bootstrap
- `/api/session/control` returns current FSM state and active task IDs from SS
- Front actor reading control section sees overlay data

---

#### 4.5.3 -- Wire writer_port into bootstrap and expose through ToolContext

**Problem:** E4.2.1 adds `writer_port` to ToolContext. E4.2.3 refactors 6 cognitive tools to use it. But `kernel/bootstrap.py::start_kernel()` creates ToolContext at L134-143 without `writer_port`. The `_create_session_state()` function (L456-465) calls `SessionStateFactory.create_standalone()` which already creates a `DirectWriterAdapter` internally -- but this adapter is stored as `manager._writer_port`, not exposed to the caller.

Bootstrap must extract the writer_port from the session state manager and inject it into both ToolContext instances.

**What to do:**

1. In `start_kernel()`, after `session_state = _create_session_state(cfg)`, extract the writer adapter:

   ```python
   # Extract writer port for tool context (M4 4.2.1)
   writer_port = getattr(session_state, '_writer_port', None)
   if writer_port is None:
       logger.warning("SessionState has no writer_port -- tools will use direct bypass (pre-M4 compat)")
   ```

2. Pass `writer_port` to both ToolContext instances:

   ```python
   front_ctx = ToolContext(
       session_manager=session_state,
       cognitive_trace_id=f"k-front-{uuid.uuid4().hex[:6]}",
       actor="front",
       recall_fn=recall_fn,
       capability_fn=_capability_discover(capability_registry),
       invoke_fn=_capability_invoke(capability_registry),
       writer_port=writer_port,  # M4 4.5.3
   )
   ```

3. Verify `writer_port` appears on both front and back dispatchers' context objects.

4. Add to demo health check:

   ```python
   checks["writer_port_wired"] = front_ctx.writer_port is not None
   ```

**Files to modify:**

- `poc/k1_poc/kernel/bootstrap.py` (extract writer_port, inject into ToolContext)

**Dependency:** E4.2.1 (writer_port on ToolContext), bootstrap pattern established by M1-M3

**Acceptance:**

- `front_ctx.writer_port is not None` after bootstrap
- `back_ctx.writer_port is not None` after bootstrap
- Writer port is the same `DirectWriterAdapter` that `SessionStateFactory` created
- Test: boot kernel, verify `runtime.front_dispatcher.ctx.writer_port is not None`

---

#### 4.5.4 -- Wire writer_port mutation audit into M1 ledger or structured observability

**Problem:** After E4.2.3, all 6 cognitive tools route writes through `writer_port.request_mutation()`. The DirectWriterAdapter runs MutationGuard preflight, updates SizeTracker, and applies the mutation. But:

- M1's `_ledger_append()` only records FSM handler mutations (task lifecycle, user input, response final). Tool-originated mutations (beliefs, scoreboard, clarifications, narrative, affect) are NOT in the ledger.
- M11 (Observability) needs to know: how many mutations were approved vs rejected? What sections are under pressure?
- M9 (Crash Recovery) needs to replay tool mutations to reconstruct SS state.

Recording every tool mutation in the ledger is expensive and potentially noisy. Instead, use structured logging at the writer adapter layer and a lightweight summary event per turn.

**What to do:**

1. In `DirectWriterAdapter.request_mutation()` (L163+), add structured logging for every mutation decision:

   ```python
   logger.info(
       "WriterPort: mutation %s section=%s operation=%s writer=%s status=%s reason=%s",
       "APPROVED" if response.approved else "REJECTED",
       request.section,
       request.operation,
       request.writer_id,
       response.status.value,
       response.reason or "",
   )
   ```

2. Track per-turn mutation counts on the writer adapter:

   ```python
   @property
   def mutation_stats(self) -> dict:
       return {
           "total_approved": self._approved_count,
           "total_rejected": self._rejected_count,
           "by_section": dict(self._section_counts),
           "by_rejection_reason": dict(self._rejection_reasons),
       }
   ```

3. At turn completion (FSM `_on_response_final` or similar), optionally append a `TurnMutationSummary` event to the ledger with aggregate counts:

   ```python
   # In FSM _on_response_final, after decide_response_final():
   if self._ledger and hasattr(writer_port, 'mutation_stats'):
       stats = writer_port.mutation_stats
       if stats["total_approved"] > 0 or stats["total_rejected"] > 0:
           self._ledger_append(TurnMutationSummaryEvent(
               turn_number=self._turn_number,
               approved=stats["total_approved"],
               rejected=stats["total_rejected"],
               by_section=stats["by_section"],
           ))
           writer_port.reset_stats()  # Reset for next turn
   ```

4. Register `TurnMutationSummaryEvent` in M1's event registry.

**Files to modify:**

- `poc/k1_poc/sessionstate/adapters/direct_writer.py` (structured logging, mutation_stats property)
- `poc/k1_poc/fsm/controller.py` (_on_response_final adds turn summary to ledger)
- `poc/k1_poc/events/` (add TurnMutationSummaryEvent)
- `poc/k1_poc/events/registry.py` (register new event)

**Dependency:** E4.2.3 (tools use writer_port), M1 1.4.2 (_ledger_append), M2 2.5.4 (ResponseFinalEvent ledger pattern)

**Acceptance:**

- Every writer_port mutation decision is logged at INFO level
- Per-turn mutation stats tracked on writer adapter
- Turn completion appends aggregate `TurnMutationSummaryEvent` to ledger (not per-mutation -- too noisy)
- M9 crash recovery can use turn summary to detect SS state drift

---

#### 4.5.5 -- Wire session bundle idempotency into M2 IdempotencyLedger pattern

**Problem:** E4.3.1 adds `update_session_bundle` tool with its own `idempotency_key` mechanism (per-session set stored on ToolContext or session manager). M2 already established the `IdempotencyLedger` pattern for envelope deduplication. These two idempotency systems should share infrastructure or at least follow the same pattern to avoid divergence.

**What to do:**

1. Verify that the session bundle's `idempotency_key` storage is NOT a separate ad-hoc set. Instead, it should use a dedicated scope within the existing dedup infrastructure:

   ```python
   # In execute_update_session_bundle:
   # Option A: Use a session-level idempotency cache (preferred)
   if ctx.session_manager.has_seen_idempotency_key(args["idempotency_key"]):
       return ToolResult(tool_name="update_session_bundle", status="ok",
                          data={"deduplicated": True, "original_result": cached})
   ```

2. Add `idempotency_cache: dict[str, Any]` to `ToolContext` or session manager:

   ```python
   # On ToolContext:
   idempotency_cache: dict[str, ToolResult] = field(default_factory=dict)
   ```

3. The bundle tool stores its result in the cache keyed by `idempotency_key`. On duplicate key, return cached result without re-applying mutations.

4. Document the relationship with M2 IdempotencyLedger: the bundle idempotency is at the TOOL level (prevents duplicate tool calls), while IdempotencyLedger is at the ENVELOPE level (prevents duplicate bus events). They operate at different layers and do not conflict.

**Files to modify:**

- `poc/k1_poc/tools/implementations.py` (bundle tool idempotency implementation)
- `poc/k1_poc/tools/implementations.py` (add idempotency_cache to ToolContext dataclass)

**Dependency:** E4.3.1 (bundle tool), M2 2.3.2 (IdempotencyLedger pattern)

**Acceptance:**

- Bundle tool uses ToolContext.idempotency_cache for dedup
- Duplicate idempotency_key returns cached result without re-applying
- Pattern documented as distinct from M2 envelope-level IdempotencyLedger
- Test: call bundle with key "abc", call again with key "abc", verify single application

---

#### 4.5.6 -- Wire prompt builder SS integration into M3 shared utilities and back actor

**Problem:** E4.4.1-4.4.3 implement `_read_ss_sections()` renderer in the prompt builder and migrate front_handler to use builder-driven SS reads. But:

- Back actor (`actors/back.py`) also reads SS sections: `_read_ss_snapshot(ss)` at L381-400 reads beliefs, scoreboard, task_state, task_artifacts, control, persona, history. After M4, some of these sections have new data (task_state/task_artifacts via rebound TaskBridge, control via overlay). Back's snapshot function must work correctly with the enriched data.

- Back actor's `_to_prompt(section)` helper (L187-192) checks `hasattr(section, "to_prompt")` and returns "" for sections without it. After M4 E4.4.1, the builder has `SECTION_RENDERERS` that handle all sections. Back should use these renderers too (or at least the same rendering logic) instead of the ad-hoc `_to_prompt` pattern.

- M3's `actors/shared.py` extracted `parse_envelope_payload`, `safe_get_section`, `never_cancel`. After M4, `safe_get_section` is used by both actors for SS reads. The builder's `_read_ss_sections` also reads sections. These should be consistent (same error handling, same missing-section behavior).

**What to do:**

1. In `actors/back.py`, update `_read_ss_snapshot()` to verify it correctly reads from the rebound TaskBridge sections:
   - `beliefs_prompt` should now show real beliefs (not empty due to missing `to_prompt()` -- M4 builder renderers provide the format)
   - `task_state_prompt` should now show real tasks (SB1 fixed by E4.1.1)
   - `task_artifacts_prompt` should now show real artifacts (SB1 fixed)

2. Consider making Back use the same `SECTION_RENDERERS` from the prompt builder for consistency:

   ```python
   from poc.k1_poc.prompt.builder import SECTION_RENDERERS

   def _render_section_for_back(section, section_name: str) -> str:
       if section_name in SECTION_RENDERERS:
           full_fn, _ = SECTION_RENDERERS[section_name]
           return full_fn(section, SSReadConfig(section_name, "full"))
       # Fallback to to_prompt() or empty
       return section.to_prompt() if hasattr(section, "to_prompt") else ""
   ```

3. Ensure `safe_get_section()` from M3 `actors/shared.py` is used consistently in the builder's `_read_ss_sections()` for missing-section handling.

4. Add test: after TaskBridge rebind (E4.1.1), verify Back handler receives non-empty task_state and task_artifacts in its prompt.

**Files to modify:**

- `poc/k1_poc/actors/back.py` (_read_ss_snapshot updated for M4-enriched sections)
- `poc/k1_poc/prompt/builder.py` (_read_ss_sections uses safe_get_section from shared.py)

**Dependency:** E4.4.1 (SECTION_RENDERERS), E4.1.1 (TaskBridge rebind), M3 3.5.2 (safe_get_section in shared.py)

**Acceptance:**

- Back handler sees non-empty task_state and task_artifacts after M4
- Back handler's beliefs prompt is non-empty (rendered via SECTION_RENDERERS or equivalent)
- Builder and Back use consistent section rendering (same renderers or compatible output)
- `safe_get_section` used for missing-section safety in both actors and builder

---

#### 4.5.7 -- Wire M4 artifacts into M1+M2+M3 test fixtures

**Problem:** M1-M3 fixtures provide `create_wired_fsm(with_ledger, with_dead_letter_consumer, with_cancel_tokens)`. M4 adds:

- TaskBridge rebound to real SS sections (E4.1.1) -- tests need FSMs with rebound TaskBridge
- ControlExtension bound to real control section (E4.1.2) -- tests need FSMs with overlay-enabled control
- Writer port on ToolContext (E4.2.1) -- tool tests need managed write path
- LLM-writable allowlist (E4.2.2) -- guard tests need config with allowlist
- Session bundle tool (E4.3.1) -- integration tests need bundle-capable context
- Builder with SS integration (E4.4.1-4.4.2) -- prompt tests need builder with real SS

**What to do:**

1. Extend `create_wired_fsm()` in `testing/fixtures.py`:

   ```python
   def create_wired_fsm(
       *,
       capture: bool = True,
       with_ledger: bool = True,
       with_dead_letter_consumer: bool = True,
       with_cancel_tokens: bool = True,
       with_ss_binding: bool = True,       # NEW M4
       with_writer_port: bool = True,      # NEW M4
   ) -> dict:
       # ... M1+M2+M3 setup unchanged ...
       if with_ss_binding:
           # Rebind TaskBridge to real SS sections (E4.1.1)
           ts = session_state.get_section("task_state")
           ta = session_state.get_section("task_artifacts")
           fsm._task_bridge.rebind(ts, ta)
           # Bind ControlExtension to real control section (E4.1.2)
           control = session_state.get_section("control")
           fsm._control_ext.bind_control_section(control)
           result["ss_binding"] = True
       if with_writer_port:
           writer_port = getattr(session_state, '_writer_port', None)
           result["writer_port"] = writer_port
       return result
   ```

2. Add helper to create tool context with writer port:

   ```python
   def create_test_tool_context(
       session_state: Any,
       actor: str = "front",
       with_writer_port: bool = True,
   ) -> ToolContext:
       writer_port = getattr(session_state, '_writer_port', None) if with_writer_port else None
       return ToolContext(
           session_manager=session_state,
           cognitive_trace_id=f"test-{actor}-{uuid.uuid4().hex[:6]}",
           actor=actor,
           writer_port=writer_port,
       )
   ```

3. Add mutation assertion helpers:

   ```python
   def assert_mutation_approved(writer_port, section: str, count: int = 1) -> None:
       stats = writer_port.mutation_stats
       actual = stats.get("by_section", {}).get(section, 0)
       assert actual >= count, f"Expected >= {count} approved mutations to {section}, got {actual}"

   def assert_mutation_rejected(writer_port, reason: str) -> None:
       stats = writer_port.mutation_stats
       reasons = stats.get("by_rejection_reason", {})
       assert reason in reasons, f"Expected rejection reason '{reason}', got {list(reasons.keys())}"
   ```

4. Update `conftest.py` fixtures to include SS binding and writer port by default.

**Files to modify:**

- `poc/k1_poc/testing/fixtures.py` (extend create_wired_fsm, add create_test_tool_context, add mutation assertion helpers)
- `tests/poc/conftest.py` (update fixtures for M4 defaults)

**Dependency:** E4.1.1-E4.2.4 (all M4 core changes), M1 1.4.7 + M2 2.5.6 + M3 3.7.6 (existing fixtures)

**Acceptance:**

- `create_wired_fsm(with_ss_binding=True)` returns FSM with rebound TaskBridge and overlay-enabled control
- `create_test_tool_context(with_writer_port=True)` returns ToolContext with live writer port
- `assert_mutation_approved` / `assert_mutation_rejected` helpers available for all tool tests
- All M4 E4.2-E4.4 tests use these fixtures

---

#### 4.5.8 -- Backward compatibility: verify M1 ledger + M2 guard table + M3 back routing survive M4 refactoring

**Problem:** M4 makes deep changes to the FSM (TaskBridge rebind, ControlExtension bind, writer_port injection), the tool layer (6 tools refactored), and the prompt builder (stage 8 implementation). Every one of these touches code paths where M1-M3 infrastructure lives:

| M4 Change | M1/M2/M3 Code Path At Risk |
|-----------|---------------------------|
| TaskBridge rebind to real SS sections | M1 `_ledger_append` ordering in task lifecycle handlers |
| ControlExtension bind to real control section | M3 `safe_get_section(ss, "control")` reads |
| 6 cognitive tools -> writer_port | M1 ledger recording unaffected (tools don't write to ledger directly) but M2 dead-letter could be triggered if tool targets wrong section |
| `update_session_bundle` batch mutations | M2 IdempotencyLedger -- bundle must not conflict with envelope dedup |
| `DynamicPromptBuilder.build(ss=ss)` new parameter | M3 front handler tests -- builder call signature changed |
| `_read_ss_sections()` in stage 8 | M3 `_extract_scenario_data` -- some reads removed, verify no data loss |
| Front handler migration from ad-hoc reads | M3 E3.6.1 emission ordering test -- front_handler structure changed |

**What to do:**

1. Create `tests/poc/test_m04_wiring_regression.py`:

   **Test matrix:**

   | Test | Trigger | Expected M1/M2/M3 Artifact | M4 Change That Could Break It |
   |------|---------|---------------------------|-------------------------------|
   | `test_ledger_records_after_taskbridge_rebind` | Dispatch task via FSM with rebound TaskBridge | `TaskCreated` in ledger AND task in SS task_state | E4.1.1 rebind |
   | `test_ledger_records_task_complete_after_rebind` | Complete task via FSM | `TaskCompleted` in ledger AND task status=COMPLETED in SS | E4.1.1 rebind |
   | `test_control_overlay_visible_to_front` | Set FSM state to DISPATCHING, read control from SS | `fsm_state=DISPATCHING` in control metadata | E4.1.2 overlay |
   | `test_dead_letter_on_tool_write_to_system_section` | Tool attempts write to "control" via writer_port | MutationResponse.rejected with AUTHORIZATION | E4.2.4 guard |
   | `test_cognitive_tool_mutation_through_writer` | Call update_beliefs via writer_port | Belief appears in SS beliefs_active section | E4.2.3 refactor |
   | `test_guard_table_still_works_after_m4` | Send invalid event to FSM in wrong state | Dead-letter event in consumer | M4 does not touch guard table |
   | `test_back_routing_still_works_after_m4` | Send task.dispatch through route_back_envelope | back_handler called correctly | M4 does not touch back router |
   | `test_front_emission_ordering_after_builder_migration` | Run front_handler with builder SS integration | Dispatches emitted before final.response | E4.4.3 migration |
   | `test_builder_ss_integration_with_rebound_sections` | Build prompt with SS that has real tasks | System prompt contains task_state data | E4.4.2 + E4.1.1 |
   | `test_bundle_idempotency_no_conflict_with_envelope_dedup` | Send bundle, then send envelope with same trace_id | Both succeed independently | E4.3.1 + M2 2.3.2 |

2. Each test uses `create_wired_fsm(with_ss_binding=True, with_writer_port=True)` from updated fixtures (4.5.7).

**Files to create:**

- `tests/poc/test_m04_wiring_regression.py`

**Dependency:** 4.5.1-4.5.7 (all wiring issues), M1-M3 regression test patterns

**Acceptance:**

- All 10 regression tests pass
- M3 `test_m03_wiring_regression.py` tests still pass after M4 changes
- M2 `test_m02_ledger_survival.py` tests still pass after M4 changes
- Zero false positives

---

#### 4.5.9 -- Full regression: demo smoke test with SS binding + writer port + builder SS integration

**Problem:** M4 changes the FSM-to-SS binding (TaskBridge, ControlExtension), the tool mutation path (writer_port), and the prompt assembly pipeline (builder stage 8). The demo web app is the integration surface. If any change introduces a regression, the demo breaks.

**What to do:**

1. Create `tests/poc/test_m04_demo_smoke.py`:

   **Scenario A: Happy path with SS binding active**
   - Boot kernel via `start_kernel()`
   - Send user input -> Front dispatches task -> Back executes task
   - Verify: `session_state.get_section("task_state")` shows dispatched task (SB1 fixed)
   - Verify: `session_state.get_section("control").get_metadata()` shows `fsm_state` (SB2 fixed)
   - Verify: ledger has TaskCreated + TaskCompleted
   - Verify: zero dead-letters
   - Verify: `/api/session/control` returns fsm_overlay with current state

   **Scenario B: Cognitive tool mutation through writer port**
   - Boot kernel
   - Trigger Front handler -> Front LLM calls `update_beliefs`
   - Verify: mutation went through writer_port (structured log present)
   - Verify: MutationGuard preflight ran (approved)
   - Verify: SizeTracker updated (beliefs_active size increased)
   - Verify: belief appears in SS `beliefs_active` section
   - Verify: `TurnMutationSummaryEvent` appears in ledger at turn completion

   **Scenario C: Writer port rejects system-owned section write**
   - Boot kernel
   - Programmatically attempt `writer_port.request_mutation(section="control", writer_id="tool:front")`
   - Verify: rejected with AUTHORIZATION reason
   - Verify: no dead-letter (rejection is at writer layer, not bus layer)
   - Verify: system still operational

   **Scenario D: Builder SS integration renders real data**
   - Boot kernel
   - Send user input that dispatches a task
   - On next Front invocation, verify system_prompt contains rendered task_state data
   - Verify system_prompt contains beliefs_active section (rendered via SECTION_RENDERERS)
   - Verify system_prompt does NOT contain "SS sections placeholder" comment

   **Scenario E: Bundle tool end-to-end**
   - Boot kernel
   - Send user input -> Front LLM calls `update_session_bundle` with 2 mutations (beliefs + scoreboard)
   - Verify: both mutations applied through writer_port.batch_mutations
   - Verify: MutationGuard ran for each sub-mutation
   - Verify: idempotency_key cached, repeat call returns cached result

**Files to create:**

- `tests/poc/test_m04_demo_smoke.py`

**Dependency:** 4.5.1-4.5.8 (all wiring and regression), M3 3.7.8 (demo smoke pattern)

**Acceptance:**

- All 5 scenarios pass
- SB1 and SB2 confirmed fixed in running system (not just unit tests)
- BP1-BP6 confirmed fixed (mutations through writer port)
- Builder SS integration produces real section data in prompt
- Bundle tool works end-to-end with batch_mutations
- All previous demo smoke tests (M2, M3) still pass

---

### M4 Touchpoint Matrix: What M5-M12 Inherit from M4

| Milestone | M4 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M5** (Arbiter) | `ControlSection.get_metadata()` with fsm_overlay | Arbiter reads FSM state + active tasks from SS control overlay (not from FSM directly). Arbiter intent classification uses control.active_task_ids to detect inflight conflicts. |
| **M5** (Arbiter) | `writer_port` on ToolContext | Arbiter-originated mutations (e.g., re-classify intent, update scoreboard urgency) go through writer_port. No more bypass for arbiter writes. |
| **M5** (Arbiter) | `SS_READ_CONFIGS` + `_read_ss_sections()` | Arbiter may define its own read config (new PromptMode entries) that the builder renders automatically. No ad-hoc SS reads needed. |
| **M6** (HITL V3) | `TaskBridge` rebound to real SS | HITL timeout/resume reads task status from SS directly. SB1 fix means HITL sees real suspended task entries. |
| **M6** (HITL V3) | `writer_port` managed writes | HITL resolution writes (clarification answered, approval granted) go through writer_port with MutationGuard enforcement. |
| **M7** (BackPool) | `writer_port` on back ToolContext | Pool workers share writer_port for back-side cognitive writes (if any). Concurrent mutation guarding prevents pool workers from racing on section writes. |
| **M7** (BackPool) | `ControlSection.fsm_overlay.active_task_ids` | Pool manager reads active task list from SS control overlay for scheduling decisions. |
| **M8** (Weave Policy) | `_read_ss_sections()` renderers | Weave policy uses builder renderers to read narrative_active, task_state, task_artifacts for weave content assembly. Same renderers ensure consistent formatting. |
| **M8** (Weave Policy) | `TurnMutationSummaryEvent` in ledger | Adaptive weave policy reads mutation pressure (high rejected mutation count = SS under pressure = delay weave). |
| **M9** (Ledger Migration) | `TurnMutationSummaryEvent` | Crash recovery uses mutation summaries to detect SS state drift. If ledger says 5 mutations approved but SS shows only 3 applied, recovery knows state is incomplete. |
| **M9** (Ledger Migration) | TaskBridge rebind + real SS writes | Ledger replay now reflects actual SS state (not phantom local-only writes). Recovery accuracy improves dramatically. |
| **M10** (UltraBERT) | `ControlSection.fsm_overlay` | Phase 1 classification writes intent/entity/safety to control section via writer_port (not direct bypass). MutationGuard enforces capacity. |
| **M11** (Observability) | `DirectWriterAdapter.mutation_stats` | Metrics collector reads mutation stats: approved_count, rejected_count, by_section, by_rejection_reason. Alert on high rejection rate. |
| **M11** (Observability) | `SECTION_RENDERERS` dispatch table | Observability dashboard renders section snapshots using same renderers as prompt builder. Consistent formatting across prompt and diagnostics. |
| **M12** (Chaos Tests) | `writer_port` under concurrent load | Race condition tests: concurrent tool mutations through writer_port. Verify MutationGuard serializes correctly. Verify SizeTracker stays consistent under parallel writes. |
| **M12** (Chaos Tests) | `update_session_bundle` + `batch_mutations` | Chaos tests verify bundle atomicity under load: partial failures, stop_on_rejection, idempotency_key collision. |

**Total: 12 issues across 4 epics (E4.1-E4.4) + 9 issues in E4.5 wiring = 21 issues across 5 epics.**

---

## M5: Conversation Arbiter

**Goal:** Add an explicit arbitration layer that runs after Phase 1
classification and before FSM routing. The Arbiter classifies each
user input against currently inflight work and outputs a deterministic
routing decision that the FSM consumes. This replaces the keyword-based
`InterruptClassifier` with a context-aware decision engine.

**Gate:** Every user input during COMPANIONING/PROGRESSING is
arbiter-classified into one of {cancel, modify_inflight, parallel_new,
defer}. The Arbiter decision is ledger-recorded as
`conversation.intent.arbitrated` before the FSM acts on it. Multi-device
arbitration resolves conflicting signals from different devices in the
same session. All 4 arbiter classifications produce observable,
deterministic FSM routing outcomes.

**Depends on:** M4 (TaskBridge bound to real SS so Arbiter can read
active/suspended tasks), M1 (event schemas for `IntentArbitrated`).

### M5 Code Audit Reference

**Current interrupt classification (what M5 replaces):**

`InterruptClassifier` (`interrupt_handler.py` L56-115) is keyword-based.
It checks 10 cancel keywords (`cancel`, `stop`, `abort`, `nevermind`,
`never mind`, `don't bother`, `forget it`, `skip it`, `call it off`).
Returns exactly 2 values: `"cancel"` or `"chat"`. No awareness of:

- What tasks are inflight (type, domain, progress)
- Whether user input relates to an inflight task (modify vs new)
- Whether to defer (acknowledge and wait)
- What device sent the input

**Current call sites (FSM `_on_user_input` controller.py L560-762):**

| FSM State | Current Behavior | Lines | Arbiter Impact |
|-----------|-----------------|-------|----------------|
| LISTENING | Phase 1 -> deliver to Front (no interrupt check) | L710-744 | 5.3.1: enrich with routing_metadata |
| COMPANIONING | `InterruptClassifier.classify()` -> always INTERRUPT_HANDLING -> DISPATCHING | L639-671 | **5.2.1**: replace with Arbiter, branch on 4 outcomes |
| PROGRESSING | Same as COMPANIONING (identical code path) | L673-703 | **5.2.1**: same replacement |
| CLARIFYING_USER | Direct DISPATCHING (clarification answer) | L710-744 | 5.3.1: enrich metadata |
| CLARIFYING_WORKER | Stay in state, deliver to Front (HITL answer) | L618-637 | No change (HITL path is not arbiter-classified) |
| DELIVERING/WEAVING | Queue in FrontLock | L746-758 | 5.4.2: add device_id priority |

**Current Phase 1 output (available to Arbiter):**

`Phase1Result` (`phase1.py` L56-101): intents[], entities[],
salience_map{}, primary_emotion, emotion_confidence, valence, arousal,
intent_classification, domain_context, safety_band, complexity_tier.

The Arbiter receives Phase1Result directly from `_run_phase1()` (not
from SS -- Phase 1 SS writes are not implemented, see M4 Phase1 NI note).

**Inflight context (available via SS after M4):**

| Source | What | How to Read (post-M4) |
|--------|------|----------------------|
| TaskBridge (now bound to SS task_state) | Active tasks: task_id, action, status, progress_pct | `ss.get_section("task_state").get_active()` |
| SuspensionManager | Suspended tasks + HITL context | `suspension_manager.get_all_contexts()` |
| ConciergeControlExtension (now mirrored to SS control) | FSM state, active_task_ids, complexity_tier | `ss.get_section("control").get_metadata()["fsm_overlay"]` |
| FSMTurnState | pending_results (queued completions) | `turn_state.pending_results` |
| CancellationHandler | cancelled_tasks set | `cancel_handler.cancelled_tasks` |

### E5.1 -- Arbiter Decision Engine (5 issues)

Source: WB 3.B, WB 8.3, WB 13.5

| # | Issue | Source |
|---|-------|--------|
| 5.1.1 | Define ArbiterDecision enum and ArbiterResult dataclass | WB 3.B |
| 5.1.2 | Build InflightContext snapshot from TaskBridge + SuspensionManager + ControlExt | WB 3.B |
| 5.1.3 | Implement ConversationArbiter.classify() with decision table | WB 3.B, 8.3 |
| 5.1.4 | Add intent-vs-inflight similarity scoring (domain, entity, action overlap) | WB 3.B |
| 5.1.5 | Emit conversation.intent.arbitrated event to bus (uses M1 IntentArbitrated schema) | WB 4 |

---

#### 5.1.1 -- Define ArbiterDecision enum and ArbiterResult dataclass

**Problem:** The POC has no vocabulary for arbiter outcomes. `InterruptClassifier`
returns a bare string `"cancel"` or `"chat"`. V3 needs 4 distinct routing
decisions with structured metadata for each.

**Changes:**

1. **Create `poc/k1_poc/fsm/arbiter.py`** with:

   ```python
   class ArbiterDecision(str, Enum):
       CANCEL = "cancel"               # Stop a specific inflight task
       MODIFY_INFLIGHT = "modify_inflight"  # Change params of running task
       PARALLEL_NEW = "parallel_new"    # Start new work alongside inflight
       DEFER = "defer"                  # Acknowledge and wait for inflight

   @dataclass
   class ArbiterResult:
       decision: ArbiterDecision
       confidence: float               # 0.0-1.0, how certain
       target_task_id: str | None       # Which inflight task (cancel/modify)
       modification_params: dict | None # For MODIFY_INFLIGHT: what changed
       routing_metadata: dict           # Extra context for FSM/Front
       phase1: Phase1Result             # Pass-through Phase 1 classification
   ```

2. `routing_metadata` carries: `intent_class`, `domain_overlap_score`,
   `entity_overlap_score`, `safety_band`, `complexity_tier`,
   `inflight_task_count`, `pending_result_count`.

**Files to create:**

- `poc/k1_poc/fsm/arbiter.py`

**Acceptance:**

- `ArbiterDecision` has exactly 4 values
- `ArbiterResult` is JSON-serializable via `to_dict()`
- `ArbiterResult.from_dict()` round-trips correctly
- Type is importable from `poc.k1_poc.fsm.arbiter`

---

#### 5.1.2 -- Build InflightContext snapshot from runtime state

**Problem:** The Arbiter needs to know what work is in progress to classify
intent against it. Currently this information is scattered across 5 objects
in the controller: `_active_task_ids` (set), `_task_bridge` (TaskBridge),
`_suspension_manager` (SuspensionManager), `_cancel_handler`
(CancellationHandler), `_turn_state` (FSMTurnState). No unified view exists.

**Changes:**

1. **Add to `poc/k1_poc/fsm/arbiter.py`:**

   ```python
   @dataclass
   class InflightTask:
       task_id: str
       action: str              # e.g. "search_hotels", "book_flight"
       domain: str              # e.g. "travel", "health"
       status: str              # "dispatched", "active", "suspended"
       progress_pct: float      # 0.0-1.0
       dispatch_turn: int       # Turn number when dispatched
       pending_hil: bool        # True if suspended for HITL

   @dataclass
   class InflightContext:
       tasks: list[InflightTask]
       pending_results: int     # Count of queued completions
       cancelled_task_ids: set[str]
       fsm_state: str
       current_turn: int
       active_device_id: str | None  # For multi-device (E5.4)
   ```

2. **Add `build_inflight_context()` factory function** that reads:
   - `task_state` section from SS (post-M4: has real tasks) -> active tasks
   - `suspension_manager.get_all_contexts()` -> suspended task IDs
   - `cancel_handler.cancelled_tasks` -> cancelled set
   - `turn_state.pending_results` -> queue depth
   - `control_ext.fsm_state` -> current FSM state

   This is a snapshot taken at the moment of user input, before
   any routing decision.

3. **InflightContext is read-only** -- no mutations. Arbiter consumes it
   but does not modify any of the source objects.

**Files to touch:**

- `poc/k1_poc/fsm/arbiter.py` (add InflightTask, InflightContext, build_inflight_context)

**Acceptance:**

- `build_inflight_context()` returns correct snapshot when:
  - 0 tasks inflight (LISTENING, idle)
  - 1 task active (COMPANIONING, Back working)
  - 2 tasks (parallel dispatch from BUNDLED intents)
  - 1 task suspended for HITL (CLARIFYING_WORKER deferred)
- Snapshot matches real SS task_state content (not TaskBridge local copy -- M4 prerequisite)

---

#### 5.1.3 -- Implement ConversationArbiter.classify() with decision table

**Problem:** `InterruptClassifier.classify()` (`interrupt_handler.py` L96-115)
returns `"cancel"` or `"chat"` based on 10 keywords. It has zero awareness
of inflight work, zero awareness of Phase 1 classification, and no support
for modify/defer outcomes. The V3 decision table (WB 3.B) requires 4
outcomes driven by intent-vs-inflight context.

**Changes:**

1. **Add `ConversationArbiter` class to `poc/k1_poc/fsm/arbiter.py`:**

   ```python
   class ConversationArbiter:
       def classify(
           self,
           text: str,
           phase1: Phase1Result,
           inflight: InflightContext,
       ) -> ArbiterResult:
   ```

2. **Decision table (deterministic, first-match-wins):**

   | Priority | Condition | Decision | Notes |
   |----------|-----------|----------|-------|
   | 1 | `phase1.safety_band == "RED"` | `CANCEL` all | Safety override -- cancel everything |
   | 2 | `phase1.intent_classification == "cancel"` AND inflight.tasks non-empty | `CANCEL` | User explicitly wants to stop. Target = highest-progress active task, or all if "cancel everything" |
   | 3 | `phase1.intent_classification == "cancel"` AND inflight.tasks empty | `PARALLEL_NEW` | Nothing to cancel -- treat as conversational |
   | 4 | inflight.tasks non-empty AND `domain_overlap(phase1, inflight) > 0.7` AND `entity_overlap > 0.5` | `MODIFY_INFLIGHT` | User is refining the same task ("actually make that 2 nights") |
   | 5 | text matches defer patterns ("ok", "sure", "keep going", "I'll wait") AND inflight.tasks non-empty | `DEFER` | User acknowledges inflight work |
   | 6 | inflight.tasks non-empty | `PARALLEL_NEW` | Different topic while tasks run |
   | 7 | inflight.tasks empty | `PARALLEL_NEW` | No inflight context -- normal new request |

3. **POC implementation:** Keyword-based similarity scoring (domain string
   match, entity set intersection). Production replaces with Phase 1
   UltraBERT embeddings for semantic similarity.

4. **Configuration:** Add `arbiter` section to `ConciergeConfig`:
   - `domain_overlap_threshold: float = 0.7`
   - `entity_overlap_threshold: float = 0.5`
   - `defer_keywords: list[str] = ["ok", "sure", "keep going", ...]`
   - `cancel_keywords: list[str]` (migrated from InterruptClassifier)

**Files to touch:**

- `poc/k1_poc/fsm/arbiter.py` (add ConversationArbiter)
- `poc/k1_poc/config.py` (add ArbiterConfig section)

**Acceptance:**

- Arbiter returns CANCEL when user says "cancel" with active tasks
- Arbiter returns CANCEL for RED safety band regardless of text
- Arbiter returns MODIFY_INFLIGHT when domain+entity overlap thresholds met
- Arbiter returns DEFER when text matches defer patterns with active tasks
- Arbiter returns PARALLEL_NEW for unrelated topic with active tasks
- Arbiter returns PARALLEL_NEW when no tasks inflight (default path)
- All decisions are deterministic (same inputs = same output)
- Decision table is evaluated in priority order (safety first)

---

#### 5.1.4 -- Add intent-vs-inflight similarity scoring

**Problem:** The decision table (5.1.3) needs `domain_overlap()` and
`entity_overlap()` scores to distinguish MODIFY_INFLIGHT from PARALLEL_NEW.
Without these, the Arbiter cannot tell if "make it 2 nights" refers to the
running hotel search or is a completely new request.

**Changes:**

1. **Add similarity functions to `poc/k1_poc/fsm/arbiter.py`:**

   ```python
   def domain_overlap(phase1: Phase1Result, inflight: InflightContext) -> float:
       """Score 0.0-1.0 how much the new input's domain matches inflight tasks."""
       # POC: exact string match on domain_context vs task domain
       # Production: cosine similarity on UltraBERT domain embeddings

   def entity_overlap(phase1: Phase1Result, inflight: InflightContext) -> float:
       """Score 0.0-1.0 how much the new input's entities match inflight tasks."""
       # POC: Jaccard similarity on entity text sets
       # Production: entity-linking via NER model
   ```

2. **POC heuristics (keyword-based, upgradeable):**
   - `domain_overlap`: 1.0 if Phase 1 domain == any inflight task domain,
     0.5 if related (e.g., "travel" and "booking"), 0.0 otherwise.
   - `entity_overlap`: Jaccard coefficient on entity text sets.
     Phase 1 entities come from `Phase1Result.entities[]`.
     Inflight task entities come from task_state dispatch payload
     (stored as `context_snapshot.entities` in TaskDispatch).

3. **Inflight task entities:** Currently TaskDispatch (`task/dispatch.py`)
   stores `context_snapshot` dict but does NOT persist extracted entities.
   Add `entities: list[str]` field to InflightTask (populated from
   Phase 1 metadata on the turn's history entry).

**Files to touch:**

- `poc/k1_poc/fsm/arbiter.py` (add domain_overlap, entity_overlap)
- `poc/k1_poc/task/dispatch.py` (add entities to TaskDispatch if needed)

**Acceptance:**

- domain_overlap("travel", [InflightTask(domain="travel")]) == 1.0
- domain_overlap("health", [InflightTask(domain="travel")]) == 0.0
- entity_overlap(["hotel", "Napa"], ["hotel", "Napa", "3 nights"]) > 0.5
- entity_overlap(["dentist"], ["hotel", "Napa"]) == 0.0
- Scores are deterministic and bounded [0.0, 1.0]

---

#### 5.1.5 -- Emit conversation.intent.arbitrated event to bus

**Problem:** WB 4 requires `conversation.intent.arbitrated` as a canonical
V3 event. M1 issue 1.1.2 defines the `IntentArbitrated` schema (not yet
implemented). The Arbiter must emit this event after every classification
so the ledger records the routing decision before the FSM acts on it.

**Changes:**

1. **Add builder function to `poc/k1_poc/bus/builders.py`:**

   ```python
   def build_intent_arbitrated(
       payload: dict[str, Any],
       parent_id: int = 0,
   ) -> Envelope:
   ```

   Topic: `k1.arbiter.intent.v1` (registered in `bus/topics.py`).

2. **Add topic constant to `poc/k1_poc/bus/topics.py`:**

   ```python
   TOPIC_INTENT_ARBITRATED = "k1.arbiter.intent.v1"
   ```

   Add to `ALL_TOPICS`. Delivery mode: STRICT (routing decisions must
   be ordered). Add to `STRICT_TOPICS`. NOT added to
   `FRONT_SUBSCRIPTIONS` or `BACK_SUBSCRIPTIONS` -- this event is
   consumed by the ledger and observability, not by actors.

3. **Emit from ConversationArbiter.classify()** (or from the FSM after
   calling classify):

   ```python
   self._bus.publish(build_intent_arbitrated(
       payload={
           "decision": result.decision.value,
           "confidence": result.confidence,
           "target_task_id": result.target_task_id,
           "intent_class": result.phase1.intent_classification,
           "domain": result.phase1.domain_context,
           "safety_band": result.phase1.safety_band,
           "inflight_task_count": len(inflight.tasks),
           "routing_metadata": result.routing_metadata,
       },
       parent_id=envelope.envelope_id,
   ))
   ```

4. **FSM subscribes** to `TOPIC_INTENT_ARBITRATED` for observability
   logging only (no handler action -- the Arbiter result is consumed
   inline, not via pub/sub).

**Files to touch:**

- `poc/k1_poc/bus/builders.py` (add build_intent_arbitrated)
- `poc/k1_poc/bus/topics.py` (add TOPIC_INTENT_ARBITRATED, update ALL_TOPICS)
- `poc/k1_poc/fsm/controller.py` (emit after classify call)

**Acceptance:**

- `k1.arbiter.intent.v1` event published on every user input that triggers Arbiter
- Event payload includes decision, confidence, target_task_id, routing_metadata
- Event is published BEFORE FSM acts on the Arbiter result
- Event is capturable by ledger subscriber (M1 dependency)

---

### E5.2 -- FSM Interrupt Path Replacement (4 issues)

Source: WB 3.B, WB 13.5

This epic replaces the keyword-based `InterruptClassifier` with the
context-aware `ConversationArbiter` for the COMPANIONING/PROGRESSING
interrupt paths. The current code (`controller.py` L639-703) always
goes: classify("cancel"/"chat") -> INTERRUPT_HANDLING -> DISPATCHING.
After M5, the FSM branches on 4 Arbiter outcomes.

| # | Issue | Source |
|---|-------|--------|
| 5.2.1 | Wire Arbiter into _on_user_input (COMPANIONING/PROGRESSING) | WB 3.B, 13.5 |
| 5.2.2 | Handle CANCEL classification (target task selection, CANCELLING transition) | WB 3.B, 7.2 |
| 5.2.3 | Handle MODIFY_INFLIGHT classification (emit task.modify, stay COMPANIONING) | WB 3.B |
| 5.2.4 | Handle DEFER classification (acknowledge, stay COMPANIONING, no new turn) | WB 3.B |

---

#### 5.2.1 -- Wire Arbiter into _on_user_input (COMPANIONING/PROGRESSING)

**Problem:** `_on_user_input()` (`controller.py` L639-703) handles
COMPANIONING and PROGRESSING interrupts identically:

```python
# L639-671 (COMPANIONING) and L673-703 (PROGRESSING):
self._interrupt_classifier.classify(text)  # returns "cancel" or "chat"
self._turn_number += 1
self._write_history(...)
self._transition(ConciergeState.INTERRUPT_HANDLING, ...)
self._transition(ConciergeState.DISPATCHING, ...)
self._bus.publish(build_turn_started(...))
self._run_phase1(envelope)
```

The interrupt classifier result is checked but NOT used to branch behavior.
Both `"cancel"` and `"chat"` take the exact same path: INTERRUPT_HANDLING
-> DISPATCHING -> deliver to Front. The cancel intent is passed to Front
implicitly via the INTERRUPT prompt mode, where the LLM decides whether
to emit `task.cancel`. This is late-binding: the LLM re-decides what the
user wanted instead of the system making a deterministic routing choice.

**Changes:**

1. **Replace `self._interrupt_classifier.classify(text)` with Arbiter
   call in both COMPANIONING and PROGRESSING blocks:**

   ```python
   # In _on_user_input, COMPANIONING/PROGRESSING blocks:
   phase1_result = self._phase1_pipeline.classify(text)
   inflight = build_inflight_context(
       ss=self._ss,
       suspension_manager=self._suspension_manager,
       cancel_handler=self._cancel_handler,
       turn_state=self._turn_state,
       control_ext=self._control_ext,
       current_turn=self._turn_number,
   )
   arbiter_result = self._arbiter.classify(text, phase1_result, inflight)

   # Emit intent.arbitrated BEFORE acting
   self._bus.publish(build_intent_arbitrated(...))

   # Branch on decision
   if arbiter_result.decision == ArbiterDecision.CANCEL:
       self._handle_arbiter_cancel(envelope, arbiter_result)
   elif arbiter_result.decision == ArbiterDecision.MODIFY_INFLIGHT:
       self._handle_arbiter_modify(envelope, arbiter_result)
   elif arbiter_result.decision == ArbiterDecision.DEFER:
       self._handle_arbiter_defer(envelope, arbiter_result)
   else:  # PARALLEL_NEW
       self._handle_arbiter_parallel_new(envelope, arbiter_result)
   ```

2. **Add `self._arbiter = ConversationArbiter()` to `__init__`** (L260).
   The `InterruptClassifier` is kept for backward compatibility but no
   longer called in the main path.

3. **PARALLEL_NEW path == current "chat" path:** increment turn,
   write history, INTERRUPT_HANDLING -> DISPATCHING, run Phase 1
   (already done by Arbiter), deliver to Front. This preserves exact
   current behavior for the common case.

**Files to touch:**

- `poc/k1_poc/fsm/controller.py` (replace interrupt classifier calls,
  add Arbiter instance, add 4 handler methods)

**Acceptance:**

- COMPANIONING + user input goes through Arbiter, not InterruptClassifier
- PROGRESSING + user input goes through Arbiter, not InterruptClassifier
- PARALLEL_NEW produces identical FSM trace to current "chat" path
- Phase 1 runs exactly once per user input (Arbiter receives result, no duplicate call)

---

#### 5.2.2 -- Handle CANCEL classification

**Problem:** Current cancel handling is indirect. `InterruptClassifier`
returns `"cancel"`, but the FSM still routes to INTERRUPT_HANDLING ->
DISPATCHING -> Front LLM in INTERRUPT mode. Front's LLM then decides
whether to emit `task.cancel`. This adds an LLM call to what should be
a deterministic system decision. It also cannot target a specific task
when multiple are inflight.

**ReAct Loop Reality (Constraint C2):**

Back's `cancellation_check()` runs at the TOP of each ReAct iteration
(loop.py L258), NOT mid-LLM-call. When `_handle_arbiter_cancel()` sets
`fsm_state.cancellation_requested = True` and publishes `task.cancel`,
the `back_cancel_handler` (back.py L662-695) sets the flag. But if Back
is currently awaiting `model.generate(request)`, the cancel is invisible
until that LLM call returns. Worst-case latency: one full LLM call
duration (2-15s). This is inherent to the ReAct architecture and is
acceptable -- the alternative (aborting HTTP connections) creates orphaned
model state and partial tool executions.

**Changes:**

1. **Add `_handle_arbiter_cancel()` to controller:**

   ```python
   def _handle_arbiter_cancel(self, envelope, arbiter_result):
       target = arbiter_result.target_task_id
       if target:
           # Cancel specific task
           self._cancel_handler.request_cancel(target)
           self._bus.publish(build_task_cancel(
               payload={"task_id": target},
               parent_id=envelope.envelope_id,
           ))
       else:
           # Cancel all active tasks
           for task_id in list(self._active_task_ids):
               self._cancel_handler.request_cancel(task_id)
               self._bus.publish(build_task_cancel(
                   payload={"task_id": task_id},
                   parent_id=envelope.envelope_id,
               ))
       # Transition to CANCELLING
       self._transition(ConciergeState.CANCELLING, ...)
   ```

2. **Target task selection** (in Arbiter, not controller):
   - If user says "cancel the hotel search" -> match entity "hotel" to
     inflight task with domain "travel" and action containing "hotel".
   - If user says "cancel" (no specifics) -> cancel highest-progress task.
   - If user says "cancel everything" / "stop all" -> cancel all.
   - Target stored in `ArbiterResult.target_task_id`.

3. **FSM transition:** COMPANIONING -> CANCELLING (forced, same as
   current `_on_task_cancel` L1274-1290). Emit `task.cancel` to Back
   via bus (not via Front LLM).

4. **Cancel-to-Back timing:** The `task.cancel` bus event triggers
   `back_cancel_handler` which sets `fsm_state.cancellation_requested`.
   Back's ReAct loop sees this flag on the NEXT iteration boundary.
   Back exits with `ReactResult(status="cancelled")`. The controller's
   `_on_task_complete` (or `_on_task_failed`) handler then processes
   the cancellation result. No new mechanism needed -- the existing
   `back_cancel_handler` + `cancellation_check` path works correctly.

5. **History write:** Write user input with `entry_type="user"` and
   metadata `{"arbiter_decision": "cancel", "target_task_id": "..."}`.

6. **Front notification:** After CANCELLING, when task.failed(cancelled)
   arrives -> DELIVERING -> Front in CANCEL mode (existing path). User
   gets cancellation confirmation via Front, not via Arbiter. Front is
   invoked as a NEW FrontLock delivery (fresh prompt build) so the
   cancellation context is in SS when Front reads it.

**Files to touch:**

- `poc/k1_poc/fsm/controller.py` (add _handle_arbiter_cancel)

**Acceptance:**

- "cancel the hotel search" with 2 inflight tasks cancels only the hotel task
- "cancel everything" cancels all active tasks
- "cancel" with 1 task cancels that task
- No LLM call needed for cancel routing (deterministic)
- Back ReAct loop exits within 1 iteration of cancel flag being set
- Front presents cancellation confirmation via CANCEL mode after task.failed
- Cancel latency documented: up to 1 Back LLM call duration between flag set and loop exit

---

#### 5.2.3 -- Handle MODIFY_INFLIGHT classification

**Problem:** V3 needs to support "actually make that 2 nights not 3" while
a hotel search is running. Currently this goes through INTERRUPT mode where
the Front LLM might dispatch a new task or try to emit a cancel+new-dispatch.
There is no structured path for in-flight parameter modification.

**ReAct Loop Reality (Constraint C3):**

Back reads SS snapshot ONCE at task start (`_read_ss_snapshot(ss)`,
back.py L390). The system prompt, messages list, and tool schemas are
built ONCE before `react_loop()` starts. You CANNOT inject modification
parameters into a running Back loop by writing to SS or sending a bus
event that Back's handler processes -- the ReAct loop does not re-read
SS between iterations.

However, the `messages` list passed to `react_loop()` IS a mutable
Python list that the loop mutates in-place (appending assistant turns,
tool results, degenerate nudges at loop.py L283-295). An external
actor can ALSO append to this list between iterations. The loop will
see the new message on the next iteration because `messages` is the
same object reference throughout.

This is the same pattern used for:

- Degenerate nudges (loop.py L283-295): append "respond directly" message
- Last-iteration submit nudge (loop.py L273-280): append "call submit_result"
- Back thinking-aloud (loop.py L466): append assistant text message

**Strategy: Inter-iteration message injection.**

```
Timeline:
  t0: Back starts ReAct loop with messages=[sys, user, ...]
  t1: Back iteration 2 -- LLM call in progress (model.generate blocks)
  t2: User says "make that 2 nights" -> Arbiter -> MODIFY_INFLIGHT
  t3: Controller appends to Back's messages list:
      messages.append(ModelMessage(role="user", content=
        "PARAMETER UPDATE from user: change nights=2 (was 3).
         Incorporate this change into your next action."))
  t4: Back iteration 2 completes (LLM returns)
  t5: Back iteration 3 starts -- sees the injected message in messages
  t6: LLM adjusts next tool call to use nights=2
```

**Changes:**

1. **Define new event topic `k1.orchestration.task.modify.v1`** in
   `bus/topics.py`. Payload: `task_id`, `modifications` dict
   (key-value pairs of changed parameters), `source` ("arbiter"),
   `parent_envelope_id`.

2. **Add builder `build_task_modify()`** to `bus/builders.py`.

3. **Add `RunningTaskHandle` to controller for message injection:**

   ```python
   @dataclass
   class RunningTaskHandle:
       task_id: str
       messages: list[ModelMessage]  # SAME reference as react_loop's list
       dispatch_payload: dict        # Original task params
       started_at: float

   # In controller.__init__:
   self._running_tasks: dict[str, RunningTaskHandle] = {}
   ```

   Populate in `_on_task_dispatch()` when the Back handler is invoked.
   Remove in `_on_task_complete()` / `_on_task_cancel()`.

4. **Back handler must expose messages list reference:**

   Modify `back_handler()` to return the `messages` list reference
   (or accept a `RunningTaskHandle` that the controller populates).
   The simplest approach: `back_handler` stores `messages` on the
   `RunningTaskHandle` after building them (back.py L420-435), before
   entering the ReAct loop.

5. **Add `_handle_arbiter_modify()` to controller:**

   ```python
   def _handle_arbiter_modify(self, envelope, arbiter_result):
       task_id = arbiter_result.target_task_id
       mods = arbiter_result.modification_params
       handle = self._running_tasks.get(task_id)

       if handle is None:
           # Task already completed or not found -- fall back to new dispatch
           logger.warning("modify target %s not running, treating as PARALLEL_NEW", task_id)
           self._handle_arbiter_parallel_new(envelope, arbiter_result)
           return

       # Inter-iteration injection: append to running Back's messages
       mod_text = "PARAMETER UPDATE from user: " + ", ".join(
           f"{k}={v}" for k, v in mods.items()
       ) + ". Incorporate this change into your next action."
       handle.messages.append(ModelMessage(role="user", content=mod_text))

       # Also emit task.modify event for observability/ledger
       self._bus.publish(build_task_modify(
           payload={"task_id": task_id, "modifications": mods},
           parent_id=envelope.envelope_id,
       ))

       # Write history (not a turn, no turn increment)
       self._write_history(
           entry_type="modify",
           role="user",
           text=text,
           metadata={"arbiter_decision": "modify_inflight", "task_id": task_id},
       )
       # Stay in COMPANIONING -- no state transition
   ```

6. **Timing guarantee:** The injection is safe because:
   - Python's GIL ensures list.append is atomic from other coroutines.
   - The ReAct loop reads `messages` at the start of each iteration
     when building `ConciergeModelRequest` (loop.py L296-308). If the
     append happens between iterations, the next LLM call includes it.
   - If the append happens DURING an LLM call (model.generate is
     awaiting HTTP), the message is visible on the NEXT iteration
     after the current call returns.
   - Worst-case: modification takes effect 1 iteration late (same
     latency as cancel, see Constraint C2).

7. **Fallback when task not running:** If `_running_tasks[task_id]` is
   None (task completed between Arbiter decision and handler execution),
   fall back to PARALLEL_NEW (dispatch a new task with modified params).

**Files to touch:**

- `poc/k1_poc/bus/topics.py` (add TOPIC_TASK_MODIFY)
- `poc/k1_poc/bus/builders.py` (add build_task_modify)
- `poc/k1_poc/fsm/controller.py` (add RunningTaskHandle, _running_tasks,
  _handle_arbiter_modify, populate/remove in dispatch/complete handlers)
- `poc/k1_poc/actors/back.py` (expose messages list reference to controller)

**Acceptance:**

- "make that 2 nights" with hotel search inflight injects modification message
- Injected message appears in Back's next ReAct iteration (not mid-LLM-call)
- FSM stays COMPANIONING after modify (no state transition)
- Turn number does NOT increment for modify
- task.modify event emitted for observability
- History records modify entry with task_id and modification params
- If target task already completed, falls back to PARALLEL_NEW dispatch
- Python GIL guarantees append atomicity -- no lock needed

---

#### 5.2.4 -- Handle DEFER classification

**Problem:** When the user says "ok", "sure", "keep going", "I'll wait"
during COMPANIONING, the current system treats it as a chat interrupt:
INTERRUPT_HANDLING -> DISPATCHING -> Front LLM in INTERRUPT mode -> LLM
generates a response -> response.final. This is wasteful -- an LLM call
for what is essentially "don't do anything".

**Changes:**

1. **Add `_handle_arbiter_defer()` to controller:**

   ```python
   def _handle_arbiter_defer(self, envelope, arbiter_result):
       # Write history (acknowledgment, not a turn)
       self._write_history(
           entry_type="defer",
           role="user",
           text=text,
           metadata={"arbiter_decision": "defer"},
       )
       # Stay in COMPANIONING -- no state transition, no turn increment
       # Optionally emit a brief system ack (not an LLM call)
       if self._should_ack_defer():
           self._bus.publish(build_final_response(
               payload={"text": "", "is_ack": True},
               parent_id=envelope.envelope_id,
           ))
   ```

2. **No LLM call.** No turn increment. No state transition. The user's
   input is recorded in history but does not trigger any cognitive
   processing.

3. **Optional ack:** If the system should acknowledge ("Got it, still
   working on it..."), emit a lightweight `response.final` with
   `is_ack=True`. The web layer can display a brief UI indicator
   without waiting for a full LLM response.

4. **Defer with queued input:** If the user sends "ok" and then
   immediately sends a real question, the FrontLock handles the
   second input normally (queued during busy, delivered after).

**Files to touch:**

- `poc/k1_poc/fsm/controller.py` (add _handle_arbiter_defer)

**Acceptance:**

- "ok keep going" during COMPANIONING does NOT invoke LLM
- FSM stays COMPANIONING, turn number unchanged
- History records defer entry
- Subsequent user input is processed normally
- Optional ack is emitted if configured

---

### E5.3 -- FSM Normal Path Enrichment (3 issues)

Source: WB 3.B, WB 13.5, WB 17.4

For LISTENING and CLARIFYING_USER states, the Arbiter still runs but
the outcome is always PARALLEL_NEW (no inflight work to arbitrate against).
The value is in the routing metadata that enriches the envelope for Front.

| # | Issue | Source |
|---|-------|--------|
| 5.3.1 | Wire Arbiter into _on_user_input (LISTENING/CLARIFYING_USER) | WB 3.B |
| 5.3.2 | Attach ArbiterResult to history entry metadata and envelope payload | WB 13.5 |
| 5.3.3 | Make Front mode resolution consume routing_metadata from Arbiter | WB 17.4 |

---

#### 5.3.1 -- Wire Arbiter into _on_user_input (LISTENING/CLARIFYING_USER)

**Problem:** The LISTENING path (`controller.py` L710-744) runs Phase 1
and delivers to Front, but the Phase 1 result is only stored as history
metadata. Front never sees the Arbiter's routing decision, domain overlap
analysis, or complexity recommendation.

**Changes:**

1. **Modify LISTENING/CLARIFYING_USER block in `_on_user_input()`:**

   ```python
   # After Phase 1, run Arbiter (inflight will be empty for LISTENING):
   phase1_result = self._phase1_pipeline.classify(text)
   inflight = build_inflight_context(...)  # Empty for LISTENING
   arbiter_result = self._arbiter.classify(text, phase1_result, inflight)
   # Emit intent.arbitrated
   self._bus.publish(build_intent_arbitrated(...))
   # Enrich envelope with arbiter metadata for Front
   self._enrich_envelope_with_arbiter(envelope, arbiter_result)
   ```

2. **`_run_phase1()` refactored:** Currently runs Phase 1 AND delivers
   to Front. Split into: `_run_phase1()` returns Phase1Result,
   `_run_arbiter()` takes Phase1Result + InflightContext returns
   ArbiterResult, then deliver to Front. The TurnLock still gates
   Phase 1 completion before Arbiter runs.

3. **No behavioral change for LISTENING:** Arbiter returns PARALLEL_NEW
   (always, because no inflight tasks). The routing_metadata enrichment
   is purely additive -- Front gets the same STANDARD mode but with
   extra context.

**Files to touch:**

- `poc/k1_poc/fsm/controller.py` (refactor _run_phase1, add _run_arbiter)

**Acceptance:**

- LISTENING path produces identical FSM trace (LISTENING -> DISPATCHING -> ...)
- ArbiterResult metadata attached to history entry
- Arbiter event emitted even for LISTENING turns
- No regression in current test suite

---

#### 5.3.2 -- Attach ArbiterResult to history entry metadata and envelope

**Problem:** Phase 1 metadata is attached to the user history entry at
`controller.py` L790-794: `last.metadata.update(result.to_metadata())`.
The Arbiter result must be attached alongside Phase 1 data so
downstream consumers (Front, prompt builder, telemetry) can read it.

**Changes:**

1. **Extend history metadata attachment:**

   ```python
   # In _run_arbiter():
   if self._history:
       last = self._history[-1]
       if last.entry_type == "user":
           last.metadata.update(phase1_result.to_metadata())
           last.metadata["arbiter"] = arbiter_result.to_dict()
   ```

2. **Enrich envelope payload for Front delivery:**

   ```python
   def _enrich_envelope_with_arbiter(self, envelope, arbiter_result):
       payload = _parse_payload(envelope)
       payload["arbiter_decision"] = arbiter_result.decision.value
       payload["routing_metadata"] = arbiter_result.routing_metadata
       payload["complexity_tier"] = arbiter_result.phase1.complexity_tier
       payload["safety_band"] = arbiter_result.phase1.safety_band
       # Rebuild envelope with enriched payload
       return Envelope(
           topic=envelope.topic,
           payload=json.dumps(payload).encode(),
           parent_id=envelope.parent_id,
           ...
       )
   ```

3. **Front reads routing_metadata** from envelope payload. This enables
   future mode resolution enhancements (5.3.3) where INTERRUPT mode
   can distinguish "parallel new topic" from "modify running task".

**Files to touch:**

- `poc/k1_poc/fsm/controller.py` (add _enrich_envelope_with_arbiter)

**Acceptance:**

- History entry metadata contains both Phase 1 and Arbiter data
- Envelope payload delivered to Front includes arbiter_decision + routing_metadata
- Front can read `payload["arbiter_decision"]` from envelope

---

#### 5.3.3 -- Make Front mode resolution consume routing_metadata

**Problem:** `determine_mode()` (`prompt/mode.py` L230-340) resolves
mode from `fsm_state`, `envelope_topic`, `clarification_state`,
`task_state`, and `affect`. It does NOT receive Arbiter routing metadata.
With M5, the Arbiter provides enriched context that mode resolution
should consume for better decisions.

**Changes:**

1. **Add `routing_metadata` parameter to `determine_mode()`:**

   ```python
   def determine_mode(
       fsm_state: str,
       envelope_topic: str,
       clarification_state: dict | None = None,
       task_state: dict | None = None,
       affect: dict | None = None,
       routing_metadata: dict | None = None,  # NEW
   ) -> PromptMode:
   ```

2. **Use routing_metadata for INTERRUPT refinement:**
   Currently INTERRUPT_HANDLING always returns `PromptMode.INTERRUPT`.
   With Arbiter, PARALLEL_NEW during interrupt could route to STANDARD
   (the user is starting a fresh topic, not really interrupting). This
   is a future enhancement -- M5 POC passes metadata through but does
   not change mode resolution logic. The metadata is available for M8+.

3. **Front actor passes routing_metadata** from envelope payload to
   `determine_mode()` call at `front.py` L483-491.

**Files to touch:**

- `poc/k1_poc/prompt/mode.py` (add routing_metadata parameter)
- `poc/k1_poc/actors/front.py` (pass routing_metadata from envelope)

**Acceptance:**

- `determine_mode()` signature accepts routing_metadata
- Front extracts routing_metadata from envelope payload and passes to determine_mode
- No change to existing mode resolution behavior (metadata is ignored in M5 POC)
- Mode resolution tests still pass unchanged

---

### E5.4 -- Multi-Device Arbitration (4 issues)

Source: WB 6, WB 12.3, WB 13.5

Same session, overlapping user signals from different devices. The Arbiter
must resolve conflicts deterministically.

| # | Issue | Source |
|---|-------|--------|
| 5.4.1 | Add device_id to user input envelope and session tracking | WB 6 |
| 5.4.2 | Implement deterministic precedence rules for multi-device conflicts | WB 6 |
| 5.4.3 | Require confirmation for conflicting high-impact actions across devices | WB 6 |
| 5.4.4 | Expand hitl_wiring validation with arbiter multi-device checks | WB 12.3 |

---

#### 5.4.1 -- Add device_id to user input envelope and session tracking

**Problem:** `Envelope` (`k1/bus/envelope.py`) has `session_id` but no
`device_id`. The M1 `UserInputReceived` schema (issue 1.1.2) specifies
`device_id` and `input_type` fields, but neither is implemented.
`_on_user_input()` has no awareness of which device sent the input.

**Changes:**

1. **Add `device_id` field to user input envelope payload:**

   The Envelope class itself is not modified (it's a K1-level
   construct). Instead, `device_id` is a payload field:

   ```python
   # In demo/coordinator.py or web app:
   build_user_input(payload={
       "text": text,
       "session_id": session_id,
       "device_id": device_id,  # NEW
       "input_type": "text",    # NEW (text/voice/gesture)
   })
   ```

2. **Track active devices in InflightContext** (5.1.2):
   - `active_device_id`: last device that sent input
   - `device_history`: last N device_ids with timestamps

3. **Track device state in SS meta section:**

   ```python
   meta.set_active_device(device_id, timestamp)
   meta.get_active_devices() -> list[DeviceEntry]
   ```

   This requires adding a `devices` sub-dict to meta section.
   Lightweight -- just device_id + last_active_ts + input_count.

**Files to touch:**

- `poc/k1_poc/bus/builders.py` (document device_id in build_user_input)
- `poc/k1_poc/demo/coordinator.py` (pass device_id from web layer)
- `poc/k1_poc/sessionstate/sections/meta.py` (add device tracking)
- `poc/k1_poc/fsm/arbiter.py` (add device_id to InflightContext)

**Acceptance:**

- User input envelope payload includes device_id
- Meta section tracks active devices
- InflightContext includes active_device_id
- Multiple devices can send input in the same session

---

#### 5.4.2 -- Implement deterministic precedence rules

**Problem:** WB 6 defines precedence: (1) cancel/stop, (2) safety-critical,
(3) direct HITL response, (4) new unrelated request. When two devices
send conflicting signals in the same session, the system must resolve
deterministically without losing either signal.

**Changes:**

1. **Add multi-device resolution to ConversationArbiter:**

   ```python
   def resolve_device_conflict(
       self,
       current_input: ArbiterResult,
       queued_inputs: list[tuple[str, ArbiterResult]],  # (device_id, result)
   ) -> list[ArbiterResult]:
       """Return inputs in precedence order, highest priority first."""
   ```

2. **Precedence table:**

   | Priority | Signal Type | Example | Resolution |
   |----------|-------------|---------|------------|
   | 1 | Cancel/stop | "cancel everything" | Process immediately, drop lower-priority |
   | 2 | Safety-critical | RED safety band | Process immediately |
   | 3 | HITL response | Answer to pending question | Process immediately (links to suspended task) |
   | 4 | Modify inflight | "make it 2 nights" | Queue behind 1-3 |
   | 5 | New request | "what's the weather" | Queue behind 1-4 |
   | 6 | Defer | "ok keep going" | Lowest priority, process last |

3. **Integration with FrontLock:** Multi-device conflicts are resolved
   at the FrontLock queue level. `_on_user_input()` checks for pending
   inputs from other devices before routing:

   ```python
   if inflight.active_device_id and inflight.active_device_id != device_id:
       # Different device -- check precedence
       ...
   ```

**Files to touch:**

- `poc/k1_poc/fsm/arbiter.py` (add resolve_device_conflict)
- `poc/k1_poc/fsm/controller.py` (check device conflicts in _on_user_input)

**Acceptance:**

- Cancel from device B takes precedence over "search hotels" from device A
- HITL answer from device B takes precedence over new request from device A
- Same-device sequential inputs process in order (no conflict)
- Different-device same-priority inputs resolve by recency (last wins)

---

#### 5.4.3 -- Require confirmation for conflicting high-impact actions

**Problem:** WB 6 requires confirmation when different devices send
conflicting high-impact actions. Example: device A says "book the hotel"
while device B says "cancel the hotel search". Without confirmation,
the system might execute a booking the user doesn't want.

**Changes:**

1. **Define "high-impact" actions** in config:
   - Actions that cause irreversible side effects: booking, payment,
     deletion, sending messages.
   - Classification: Arbiter checks `phase1.safety_band` and action
     type from dispatch payload.

2. **Confirmation flow:**
   - Arbiter detects conflict: device A says "book" (high-impact),
     device B says "cancel" (conflicting).
   - Arbiter emits `DEFER` for BOTH inputs.
   - Arbiter emits a clarification request: "I received conflicting
     requests from two devices. Should I book the hotel (device A)
     or cancel the search (device B)?"
   - FSM transitions to CLARIFYING_USER.
   - User resolves on either device.

3. **Integration with clarifications section:**
   Use existing `update_clarifications` tool write path (post-M4:
   through writer port). Create a system-generated clarification with
   `is_blocking=True`, `priority=URGENT`.

**Files to touch:**

- `poc/k1_poc/fsm/arbiter.py` (add conflict detection and confirmation logic)
- `poc/k1_poc/fsm/controller.py` (handle DEFER-with-confirmation path)
- `poc/k1_poc/config.py` (add high_impact_actions list)

**Acceptance:**

- Conflicting high-impact actions from different devices trigger confirmation
- Both actions are deferred until user resolves
- Non-high-impact conflicts resolve by precedence (no confirmation)
- Confirmation uses existing clarification mechanism

---

#### 5.4.4 -- Expand hitl_wiring validation with multi-device checks

**Problem:** `validate_hitl_wiring()` (`protocols/hitl_wiring.py`)
validates HITL pipeline integrity. WB 12.3 recommends expanding it
with arbiter checks for multi-device conflicts. A HITL response from
device B should be validated against the pending HITL request
(which device A may have triggered).

**Changes:**

1. **Add device validation to HITL resume path:**
   - When `task.resume` arrives, check that the responding device_id
     is authorized (same session, not a stale device).
   - Log if response comes from a different device than the one that
     triggered the original HITL question.

2. **Add to `validate_hitl_wiring()`:**
   - New check: "HITL response device matches session active devices"
   - New check: "No concurrent HITL responses from multiple devices
     for the same suspended task"

3. **Guard in `_on_task_resume()` (`controller.py` L1385+):**
   - Extract device_id from resume envelope payload.
   - If multiple HITL responses arrive for the same task_id from
     different devices, accept first, discard duplicates with
     warning log.

**Files to touch:**

- `poc/k1_poc/protocols/hitl_wiring.py` (add device validation checks)
- `poc/k1_poc/fsm/controller.py` (add device_id guard in_on_task_resume)

**Acceptance:**

- validate_hitl_wiring() includes multi-device checks
- Duplicate HITL responses from different devices are deduplicated
- First valid response wins, subsequent responses logged and discarded
- No crash or deadlock on concurrent HITL responses

---

### M5 ReAct Loop Interaction Audit

The Arbiter runs in the FSM controller (synchronous, deterministic,
no LLM call). But the actions it triggers interact with Front and Back
LLM ReAct loops that are async, stateful, and cannot be interrupted
mid-generation. Every M5 issue must respect these hard constraints:

**Constraint 1: Front LLM is NEVER cancelled mid-loop.**

`front_handler` passes `cancellation_check=_never_cancel` to `react_loop()`
(front.py L650). Once Front starts a ReAct loop, it runs to completion or
budget exhaustion. The Arbiter cannot interrupt a running Front invocation.
Consequence: if the Arbiter decides CANCEL while Front is generating a
response for a previous event, the cancel action queues behind the current
Front run via FrontLock. This is correct -- the Arbiter acts at the FSM
level (cancel to Back, transition to CANCELLING), not at the Front level.

**Constraint 2: Back cancellation is checked BETWEEN iterations, not mid-call.**

`react_loop()` checks `cancellation_check()` at the TOP of each iteration
(loop.py L258: `if await cancellation_check(): return ReactResult(status="cancelled")`)
but NOT during the LLM call itself (`await model.generate(request)` blocks
until the LLM returns). If Back is on LLM call iteration 3 of 10, a cancel
flag set during that call is invisible until iteration 4 starts.

Latency: up to 1 full LLM call duration (2-15s depending on model/tier).
This is acceptable -- the alternative (aborting HTTP connections) would
create orphaned state.

**Constraint 3: Back reads SS snapshot ONCE at task start.**

`back_handler` calls `_read_ss_snapshot(ss)` (back.py L390) ONCE before
building the system prompt and entering the ReAct loop. The Back LLM's
entire context (prompt, messages, tool schemas) is frozen for the duration
of the loop. You CANNOT inject new information (modification params,
updated task state, new user context) into a running Back loop by writing
to SS or sending bus events.

Consequence for MODIFY_INFLIGHT: the `task.modify` event cannot be
consumed by a running Back loop. The modification must use one of:

| Strategy | Mechanism | Latency | Data Loss |
|----------|-----------|---------|----------|
| Cancel-and-restart | Cancel current task, dispatch new task with modified params | High (restart from scratch) | Tool results from cancelled run lost |
| Inter-iteration injection | Append synthetic message to `messages` list between iterations (same pattern as degenerate nudge, loop.py L283-295) | Low (next iteration) | None -- loop continues with new context |
| Deferred apply | Let current task complete, then dispatch follow-up task with modifications | Variable (wait for completion) | None -- but user waits |

**Chosen strategy for M5: Inter-iteration injection** (strategy 2).

The `messages` list passed to `react_loop()` is a mutable Python list.
The loop mutates it in-place (appending assistant messages, tool results,
nudges). An external event handler can ALSO append to this list between
iterations. The mechanism:

```
1. Controller receives task.modify from Arbiter
2. Controller looks up the running Back task's messages list reference
3. Controller appends a synthetic "user" message:
   {"role": "user", "content": "PARAMETER UPDATE: change nights from 3 to 2.
    Incorporate this change into your next tool call."}
4. Back's ReAct loop sees this message on the next iteration
5. The LLM adjusts its next tool call accordingly
```

This requires storing a reference to the active Back task's `messages`
list in the controller (new field on TaskBridge or a running_tasks dict).
See corrected issue 5.2.3 below.

**Constraint 4: FrontLock serializes all Front invocations.**

When Front is busy (FrontLock.busy=True), new events queue in priority
order (front_lock.py). The Arbiter's decision (e.g., PARALLEL_NEW) that
results in a Front invocation goes through FrontLock. If Front is already
processing a previous event, the new Front invocation waits.

Consequence: the Arbiter runs instantly (deterministic, no LLM), but its
effect on Front may be delayed by the current Front run. This is correct
behavior -- FrontLock prevents concurrent Front invocations.

**Constraint 5: Front prompt is built ONCE per invocation.**

`front_handler` builds system_prompt + messages + tools ONCE from the
envelope payload and SS state (front.py L483-640). If the Arbiter
enriches the envelope with `routing_metadata`, Front sees it because
it's a NEW Front invocation (not mid-loop injection). This is safe.

**Impact on M5 issues:**

| Issue | Constraint | Impact | Status |
|-------|-----------|--------|--------|
| 5.2.1 (wire Arbiter) | C4 (FrontLock) | Arbiter runs sync, Front delivery goes through FrontLock -- correct | OK |
| 5.2.2 (CANCEL) | C2 (between-iteration) | Cancel flag visible to Back only between iterations -- document latency | CORRECTED below |
| 5.2.3 (MODIFY_INFLIGHT) | C3 (SS snapshot once) | Cannot inject into running Back via SS -- use inter-iteration message injection | CORRECTED below |
| 5.2.4 (DEFER) | None | No LLM invoked -- pure FSM action | OK |
| 5.3.x (normal path) | C5 (prompt built once) | Envelope enrichment is safe -- new invocation | OK |
| 5.4.x (multi-device) | C4 (FrontLock) | Conflicting device inputs queue through FrontLock | OK |

---

### M5 Issue Execution Order

Dependencies within M5 (must be sequential):

```
5.1.1 (ArbiterDecision enum)
  |
  v
5.1.2 (InflightContext snapshot)
  |
  v
5.1.4 (similarity scoring -- needs InflightContext)
  |
  v
5.1.3 (ConversationArbiter.classify -- needs all above)
  |
  v
5.1.5 (emit event -- needs Arbiter)
  |
  +---------+---------+
  |         |         |
  v         v         v
5.2.1     5.3.1     5.4.1
(FSM      (FSM      (device_id
interrupt) normal)   tracking)
  |         |         |
  v         v         v
5.2.2     5.3.2     5.4.2
5.2.3     5.3.3     5.4.3
5.2.4               5.4.4
```

Recommended execution:

1. **5.1.1** (enum + dataclass -- foundation)
2. **5.1.2** (inflight context builder)
3. **5.1.4** (similarity scoring)
4. **5.1.3** (Arbiter.classify decision table -- core logic)
5. **5.1.5** (event emission)
6. **5.2.1** (wire into FSM interrupt path -- highest impact)
7. **5.2.2** (cancel handler)
8. **5.2.3** (modify_inflight handler)
9. **5.2.4** (defer handler)
10. **5.3.1** (wire into FSM normal path)
11. **5.3.2** (metadata enrichment)
12. **5.3.3** (Front mode resolution pass-through)
13. **5.4.1** (device_id plumbing)
14. **5.4.2** (precedence rules)
15. **5.4.3** (confirmation for conflicts)
16. **5.4.4** (hitl_wiring expansion)
17. **5.5.1-5.5.9** (end-to-end wiring -- AFTER all E5.1-E5.4 issues complete)

### E5.5 -- End-to-End Wiring & System Integration

Source: Bootstrap analysis, fsm/controller.py, fsm/interrupt_handler.py, fsm/phase1.py, bus/topics.py, bus/builders.py, prompt/mode.py, actors/front.py, actors/back.py, react/loop.py, demo/coordinator.py, sessionstate/sections/meta.py, protocols/hitl_wiring.py, config/loader.py

**Why this epic exists:** E5.1-E5.4 create a brand-new arbitration layer (ConversationArbiter), 4 new FSM handler methods, a new bus event topic, inter-iteration message injection for modify-inflight, multi-device tracking, and conflict resolution. But these changes rewire the ENTIRE user input path -- the single most critical FSM code path that every session traverses. Without explicit wiring:

- The `k1.arbiter.intent.v1` event is published to the bus but has no M2 guard table entry (guard_dispatch rejects it as unknown topic -> dead-letter storm)
- The Arbiter reads InflightContext from SS task_state (M4-bound) and control overlay (M4) but the M1 ledger has no schema for `IntentArbitrated` events (ledger silently drops them)
- `_handle_arbiter_cancel()` publishes `task.cancel` which M3's `route_back_envelope()` routes to Back, but the cancel-to-ledger ordering must be verified (M1 1.4.2 pattern: ledger BEFORE mutation)
- `RunningTaskHandle` stores messages list references for inter-iteration injection (5.2.3) but M3's parallel safety `classify_tool_batch()` doesn't know about injected messages
- `determine_mode()` gains `routing_metadata` parameter (5.3.3) but M4's `SS_READ_CONFIGS` uses PromptMode for section selection -- the new metadata doesn't affect section reads unless explicitly wired
- `device_id` tracking (5.4.1) on MetaSection adds state but M4's writer_port mutations don't carry device_id for audit trails
- Multi-device confirmation (5.4.3) creates system-generated clarifications through M4's writer_port but the demo health check doesn't verify arbiter state

**Every M5 artifact must plug into the cumulative M1+M2+M3+M4 infrastructure or the Arbiter exists as a disconnected decision engine with no system integration.**

**System state after M1+M2+M3+M4 (E1.4 + E2.5 + E3.7 + E4.5 wiring complete) -- what M5 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created             # M1 1.4.1
  -> LedgerMiddleware in bus middleware chain                # M1 1.4.4
  -> ConciergeController(bus, router)
     -> set_ledger(writer)                                  # M1 1.4.1
     -> _ledger_append() in 11 handlers                     # M1 1.4.2
     -> _try_deserialize() bridge                           # M1 1.4.3
     -> _dispatch_envelope() flow:                          # M2 2.5.3
          topic_guard -> idempotency -> guard_dispatch -> handler
     -> FULL_GUARD_TABLE + _guard_dispatch()                # M2 2.1.1-2.1.2
     -> _publish_dead_letter() with ledger recording        # M2 2.5.2
     -> IdempotencyLedger                                   # M2 2.3.2
     -> decide_response_final() + ResponseFinalEvent        # M2 2.3.1, 2.5.4
     -> Per-task CancellationToken in _cancel_tokens        # M3 3.2.2
  -> route_back_envelope() as canonical back dispatch        # M3 3.1.1-3.1.3
  -> DeadLetterConsumer subscribed to bus                    # M2 2.5.1
  -> Unknown back topics -> dead-letter pipeline             # M3 3.7.1
  -> builders auto-enrich legacy dicts                       # M1 1.4.5
  -> actors/shared.py: parse_envelope_payload,
       safe_get_section, never_cancel                        # M3 3.5.1-3.5.3
  -> SuspensionManager as sole resume-context owner          # M3 3.3.1
  -> classify_tool_batch() in react_loop                     # M3 3.4.2
  -> ReactResult carries parallel/sequential counts          # M3 3.7.4
  -> TaskBridge.rebind() to real SS task_state/task_artifacts # M4 4.1.1, 4.5.1
  -> ControlExtension.bind_control_section() + fsm_overlay   # M4 4.1.2, 4.5.2
  -> writer_port (DirectWriterAdapter) on ToolContext         # M4 4.2.1, 4.5.3
  -> 6 cognitive tools through writer_port.request_mutation() # M4 4.2.3
  -> LLM-writable allowlist in config                        # M4 4.2.2
  -> Runtime guard rejecting LLM writes to system sections   # M4 4.2.4
  -> update_session_bundle with batch_mutations              # M4 4.3.1-4.3.3
  -> SECTION_RENDERERS + _read_ss_sections() in stage 8      # M4 4.4.1-4.4.2
  -> DynamicPromptBuilder.build(ss=ss) parameter             # M4 4.4.2
  -> TurnMutationSummaryEvent in ledger at turn completion   # M4 4.5.4
  -> ToolContext.idempotency_cache for bundle dedup           # M4 4.5.5
  -> Demo: ledger health + /api/ledger/stats                 # M1 1.4.6
  -> Demo: dead-letter health + /api/dead-letters            # M2 2.5.5
  -> Demo: parallel_tools_enabled in health check            # M3 3.7.4
  -> Demo: control overlay + /api/session/control            # M4 4.5.2
  -> Demo: writer_port_wired in health check                 # M4 4.5.3
  -> Fixtures: create_wired_fsm(with_ledger,
       with_dead_letter_consumer, with_cancel_tokens,
       with_ss_binding, with_writer_port)                    # M1-M4 fixtures
```

**M5 artifacts that must integrate into this M1+M2+M3+M4-wired system:**

| M5 Artifact | Where It Lives After E5.1-E5.4 | M1+M2+M3+M4 Touchpoint It Must Connect To |
|-------------|-------------------------------|------------------------------------------|
| `ArbiterDecision` enum + `ArbiterResult` dataclass | `fsm/arbiter.py` | M1 ledger needs `IntentArbitrated` canonical event class for ledger recording |
| `InflightContext` + `build_inflight_context()` | `fsm/arbiter.py` | M4 TaskBridge rebind (reads real task_state), M4 control overlay (reads fsm_overlay), M3 SuspensionManager (reads suspended contexts) |
| `ConversationArbiter.classify()` | `fsm/arbiter.py` | M4 `ControlSection.get_metadata()["fsm_overlay"]` for active task IDs; M4 `ss.get_section("task_state").get_active()` for task details |
| `k1.arbiter.intent.v1` topic + `build_intent_arbitrated()` | `bus/topics.py`, `bus/builders.py` | M2 FULL_GUARD_TABLE needs arbiter topic entry; M2 dead-letter pipeline must not reject it; M1 LedgerMiddleware must record it |
| `_handle_arbiter_cancel()` | `fsm/controller.py` | M1 `_ledger_append(TaskCancelledEvent)` BEFORE `cancel_handler.request_cancel()`; M3 cancel_tokens propagated to Back; M3 `route_back_envelope()` delivers cancel |
| `_handle_arbiter_modify()` + `RunningTaskHandle` | `fsm/controller.py` | M3 react_loop messages list (inter-iteration injection); M1 ledger needs new `TaskModifiedEvent`; Back's react_loop (loop.py L250 cancellation check) must not treat injected message as cancellation |
| `_handle_arbiter_defer()` | `fsm/controller.py` | M1 ledger records defer as non-turn event; M4 TurnMutationSummaryEvent NOT emitted (no turn) |
| `_handle_arbiter_parallel_new()` | `fsm/controller.py` | Same as current interrupt path -- M1 ledger + M2 guard table + M3 back routing all apply unchanged |
| `_enrich_envelope_with_arbiter()` | `fsm/controller.py` | M4 `DynamicPromptBuilder.build(ss=ss)` -- builder reads enriched payload; M3 `actors/shared.py::parse_envelope_payload()` must handle new keys |
| `routing_metadata` on `determine_mode()` | `prompt/mode.py`, `actors/front.py` | M4 `SS_READ_CONFIGS` per-PromptMode section selection; future: Arbiter-specific read configs |
| `device_id` on MetaSection + InflightContext | `sessionstate/sections/meta.py`, `fsm/arbiter.py` | M4 writer_port mutations should carry device_id; M4 TurnMutationSummaryEvent should include device_id |
| `resolve_device_conflict()` | `fsm/arbiter.py` | M2 IdempotencyLedger -- conflicting device inputs must not be deduped as identical; M3 FrontLock queue priority must respect device precedence |
| Multi-device confirmation via clarification | `fsm/arbiter.py`, `fsm/controller.py` | M4 writer_port for clarification writes; M4 update_clarifications tool through managed path |
| HITL wiring device validation | `protocols/hitl_wiring.py` | M3 SuspensionManager.get_all_contexts() -- validate resume device matches suspension device |

---

#### 5.5.1 -- Register k1.arbiter.intent.v1 in M2 guard table and M1 ledger pipeline

**Problem:** E5.1.5 creates a new bus topic `k1.arbiter.intent.v1` and publishes it after every Arbiter classification. But M2's `_dispatch_envelope()` flow (2.5.3) runs: topic_guard -> idempotency -> guard_dispatch -> handler. The `FULL_GUARD_TABLE` (M2 2.1.1) maps `(state, topic) -> allowed_states`. If `k1.arbiter.intent.v1` has no entry, `_guard_dispatch()` rejects it as an unknown topic and routes to dead-letter. Every user input would generate a dead-letter event.

Additionally, M1's `LedgerMiddleware` (1.4.4) records all bus events to the ledger. The `IntentArbitrated` canonical event class must exist so the ledger records a structured event (not a raw envelope dump).

**What to do:**

1. Add `k1.arbiter.intent.v1` to `FULL_GUARD_TABLE` in `fsm/controller.py`:

   ```python
   # Arbiter intent event -- informational, allowed in any state where user input triggers it.
   # The event is emitted BY the FSM after Arbiter classification, before routing.
   # It's consumed by ledger/observability, not by FSM handlers.
   (ConciergeState.DISPATCHING, TOPIC_INTENT_ARBITRATED): [ConciergeState.DISPATCHING],
   (ConciergeState.COMPANIONING, TOPIC_INTENT_ARBITRATED): [ConciergeState.COMPANIONING],
   (ConciergeState.PROGRESSING, TOPIC_INTENT_ARBITRATED): [ConciergeState.PROGRESSING],
   (ConciergeState.LISTENING, TOPIC_INTENT_ARBITRATED): [ConciergeState.LISTENING],
   (ConciergeState.CLARIFYING_USER, TOPIC_INTENT_ARBITRATED): [ConciergeState.CLARIFYING_USER],
   ```

   The Arbiter event does NOT cause state transitions -- it's a passthrough for observability. The guard table allows it in the states where `_on_user_input` fires (the states listed in M5's code audit: LISTENING, COMPANIONING, PROGRESSING, CLARIFYING_USER).

2. Create `IntentArbitrated` canonical event class in `events/`:

   ```python
   @dataclass
   class IntentArbitrated(CanonicalEventMeta):
       decision: str           # ArbiterDecision.value
       confidence: float
       target_task_id: str | None
       intent_class: str       # Phase1 intent_classification
       domain: str             # Phase1 domain_context
       safety_band: str
       inflight_task_count: int
       device_id: str | None   # M5 5.4.1
   ```

3. Register `IntentArbitrated` in M1's event registry so `_ledger_append()` can record it.

4. Wire `_ledger_append(IntentArbitrated(...))` in the FSM immediately after `self._bus.publish(build_intent_arbitrated(...))`:

   ```python
   # In _on_user_input, after Arbiter classification:
   arbiter_result = self._arbiter.classify(text, phase1_result, inflight)
   self._bus.publish(build_intent_arbitrated({...}, parent_id=envelope.envelope_id))
   self._ledger_append(IntentArbitrated(
       decision=arbiter_result.decision.value,
       confidence=arbiter_result.confidence,
       target_task_id=arbiter_result.target_task_id,
       intent_class=phase1_result.intent_classification,
       domain=phase1_result.domain_context,
       safety_band=phase1_result.safety_band,
       inflight_task_count=len(inflight.tasks),
       device_id=inflight.active_device_id,
   ))
   ```

5. Add test: boot kernel, send user input, verify `IntentArbitrated` appears in ledger AND no dead-letter for arbiter topic.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (FULL_GUARD_TABLE entries, _ledger_append after Arbiter)
- `poc/k1_poc/events/` (IntentArbitrated canonical event)
- `poc/k1_poc/events/registry.py` (register IntentArbitrated)

**Files to create:**

- `tests/poc/test_m05_wiring_regression.py` (initial test)

**Dependency:** E5.1.5 (arbiter event), M2 2.1.1 (FULL_GUARD_TABLE), M1 1.4.2 (_ledger_append pattern), M1 1.4.4 (LedgerMiddleware)

**Acceptance:**

- `k1.arbiter.intent.v1` passes `_guard_dispatch()` without dead-letter
- Guard table allows arbiter topic in LISTENING, COMPANIONING, PROGRESSING, CLARIFYING_USER states
- `IntentArbitrated` event appears in ledger after every user input
- Ledger entry includes decision, confidence, target_task_id, device_id
- Zero dead-letters from arbiter topic under normal operation

---

#### 5.5.2 -- Wire InflightContext to read from M4-bound SS sections

**Problem:** `build_inflight_context()` (5.1.2) reads from 5 runtime objects. After M4, 2 of these have changed fundamentally:

- `task_state` section: M4 4.1.1 rebound TaskBridge writes to real SS section. `build_inflight_context()` must read from `ss.get_section("task_state")` (the bound section), NOT from `self._task_bridge` internal state. If it reads from TaskBridge, it sees the same data (because rebind connects them), but if someone creates an InflightContext from a different code path that has `ss` but not the controller's `_task_bridge`, it must still work.

- `control` section: M4 4.1.2 mirrors FSM state to control section via `set_fsm_overlay()`. `build_inflight_context()` must read `fsm_state` from `ss.get_section("control").get_metadata()["fsm_overlay"]`, NOT from `self._control_ext._fsm_state`. This ensures the Arbiter always sees the same FSM state that the prompt builder and actors see.

After M3, `SuspensionManager` is the sole resume-context owner. `build_inflight_context()` reads suspended tasks from it correctly.

**What to do:**

1. Ensure `build_inflight_context()` signature accepts `ss` (SessionStateManager) as primary source:

   ```python
   def build_inflight_context(
       ss: Any,                              # SessionStateManager (primary)
       suspension_manager: SuspensionManager, # M3 SuspensionManager
       cancel_handler: CancellationHandler,
       turn_state: FSMTurnState,
       current_turn: int,
       device_id: str | None = None,         # M5 5.4.1
   ) -> InflightContext:
       # Read from SS (M4-bound sections)
       task_state = ss.get_section("task_state")
       active_tasks = task_state.get_active() if task_state else []

       control = ss.get_section("control")
       meta = control.get_metadata() if control else {}
       overlay = meta.get("fsm_overlay", {})
       fsm_state = overlay.get("fsm_state", "UNKNOWN")
       active_task_ids_from_overlay = overlay.get("active_task_ids", [])
       ...
   ```

2. Verify that the InflightContext.tasks list correctly merges:
   - Active tasks from SS task_state (dispatched, in-progress)
   - Suspended tasks from SuspensionManager.get_all_contexts()
   - Cancelled tasks from cancel_handler.cancelled_tasks

3. Add `pending_hil` flag to InflightTask by checking if task_id appears in SuspensionManager contexts.

4. Test: create FSM with M4 SS binding (TaskBridge rebound), dispatch a task, call `build_inflight_context()`, verify it returns the correct task from SS (not from a stale local copy).

**Files to modify:**

- `poc/k1_poc/fsm/arbiter.py` (build_inflight_context reads from SS)

**Dependency:** M4 4.1.1 (TaskBridge rebind), M4 4.1.2 (control overlay), M3 3.3.1 (SuspensionManager)

**Acceptance:**

- `build_inflight_context(ss=...)` reads task_state from SS section (not TaskBridge internal)
- `build_inflight_context(ss=...)` reads fsm_state from control overlay (not ControlExtension internal)
- Suspended tasks from SuspensionManager appear with `pending_hil=True`
- InflightContext is consistent with what the prompt builder sees from the same SS

---

#### 5.5.3 -- Wire _handle_arbiter_cancel() into M1 ledger + M3 cancel token propagation

**Problem:** E5.2.2 adds `_handle_arbiter_cancel()` which calls `cancel_handler.request_cancel(task_id)` and publishes `build_task_cancel()`. But:

- M1 pattern (1.4.2): `_ledger_append()` fires BEFORE mutation. The cancel handler mutation (`request_cancel`) must follow the ledger write:

  ```python
  self._ledger_append(TaskCancelledEvent(...))  # 1. Record
  self._cancel_handler.request_cancel(task_id)   # 2. Mutate
  self._bus.publish(build_task_cancel(...))       # 3. Notify
  ```

  If the order is wrong, crash recovery (M9) loses the cancel event.

- M3 (3.2.2): Per-task `CancellationToken` in `_cancel_tokens`. The arbiter cancel must use the SAME cancel propagation path as the existing `_on_task_cancel()` handler (controller.py L1245). Currently `_on_task_cancel` sets `_cancel_handler.request_cancel()` which triggers Back's `cancellation_check()` on next iteration. The arbiter cancel must follow this exact same path -- no duplicate cancel mechanism.

- M3 (3.1.1): `route_back_envelope()` delivers `task.cancel` to Back. The arbiter cancel publishes `task.cancel` to the bus, which M3's route triggers. Verify the delivery path works when the Arbiter originates the cancel (parent_id is the user.input envelope, not a task.dispatch envelope).

**What to do:**

1. Verify `_handle_arbiter_cancel()` follows M1 ledger ordering:

   ```python
   def _handle_arbiter_cancel(self, envelope, arbiter_result):
       target = arbiter_result.target_task_id
       targets = [target] if target else list(self._active_task_ids)
       for task_id in targets:
           # M1: ledger BEFORE mutation
           self._ledger_append(TaskCancelledEvent(
               task_id=task_id,
               source="arbiter",
               arbiter_decision=arbiter_result.decision.value,
               confidence=arbiter_result.confidence,
           ))
           # M3: cancel through existing cancel handler (same path as _on_task_cancel)
           self._cancel_handler.request_cancel(task_id)
           # M3: publish task.cancel for route_back_envelope delivery
           self._bus.publish(build_task_cancel(
               payload={"task_id": task_id, "source": "arbiter"},
               parent_id=envelope.envelope_id,
           ))
       # Transition to CANCELLING
       self._transition(ConciergeState.CANCELLING, ...)
   ```

2. Verify that `route_back_envelope()` (M3 3.1.1) correctly routes `task.cancel` when `parent_id` is a user.input envelope (not the original task.dispatch). The router should match on topic, not parent lineage.

3. Verify that Back's `cancellation_check()` sees the flag set by `cancel_handler.request_cancel()` on the next ReAct iteration (M3 constraint C2: between-iteration check).

4. Add test: dispatch task -> Arbiter classifies CANCEL -> verify ledger has TaskCancelledEvent with source="arbiter" -> verify Back exits with status="cancelled" -> verify route_back_envelope delivered the cancel.

**Files to verify:**

- `poc/k1_poc/fsm/controller.py` (_handle_arbiter_cancel ledger ordering)
- `poc/k1_poc/actors/back.py` (cancel delivery path)
- `poc/k1_poc/react/loop.py` L250 (cancellation_check sees arbiter-originated cancel)

**Dependency:** E5.2.2 (arbiter cancel), M1 1.4.2 (ledger ordering), M3 3.2.2 (cancel tokens), M3 3.1.1 (route_back_envelope)

**Acceptance:**

- `_ledger_append(TaskCancelledEvent)` fires BEFORE `cancel_handler.request_cancel()`
- `TaskCancelledEvent.source` field is "arbiter" (distinguishes from LLM-originated cancel)
- `route_back_envelope()` delivers arbiter-originated `task.cancel` to Back
- Back ReAct loop exits with `status="cancelled"` within 1 iteration of flag being set
- Ledger shows: `IntentArbitrated(CANCEL)` -> `TaskCancelledEvent` -> `TaskFailed(reason=cancelled)` in order

---

#### 5.5.4 -- Wire RunningTaskHandle into M3 parallel safety and verify inter-iteration injection

**Problem:** E5.2.3 adds `RunningTaskHandle` with a reference to Back's `messages` list for inter-iteration injection. This is the most architecturally novel M5 mechanism. It must integrate with:

- M3's `classify_tool_batch()` (3.4.2): parallel safety classifies tool calls as cognitive/action/system. An injected "PARAMETER UPDATE" message is NOT a tool call -- it's a synthetic user message. The classification should be unaffected (it operates on LLM response tool_calls, not on messages). Verify this.

- M3's ReactResult: The ReAct loop returns `ReactResult` with `parallel_tool_calls` and `sequential_tool_calls` counts. An injected message does not change these counts. Verify.

- Back's `_read_ss_snapshot()` (back.py L159): reads SS ONCE at task start. The injected modification message tells the LLM to adjust parameters, but the snapshot (beliefs, referents, safety_band) is stale. This is acceptable because:
  1. The modification is about task parameters (not beliefs/safety)
  2. The LLM adjusts its NEXT tool call, not the context
  3. Re-reading SS mid-loop would break the deterministic snapshot contract

- M4's writer_port: If Back's LLM adjusts a tool call based on injected modification, the tool execution still goes through the normal tool dispatcher path. Cognitive tool writes still use writer_port. No change needed.

**What to do:**

1. Verify that `RunningTaskHandle` is populated in `_on_task_dispatch()` AFTER `route_back_envelope()` starts the Back handler:

   ```python
   # In _on_task_dispatch, after route_via_orchestrator:
   # Back handler is now running (or scheduled to run).
   # Store handle for potential modify-inflight injection.
   # NOTE: messages list reference is available only AFTER back_handler
   # builds it (back.py L416). Use a deferred population pattern:
   self._running_tasks[task_id] = RunningTaskHandle(
       task_id=task_id,
       messages=None,  # Populated by back_handler callback
       dispatch_payload=payload,
       started_at=time.monotonic(),
   )
   ```

2. Back handler must register its `messages` list with the controller:

   ```python
   # In back_handler, after building messages (back.py L416-420):
   if fsm_state and hasattr(fsm_state, 'register_messages'):
       fsm_state.register_messages(task_id, messages)
   ```

   This requires adding a `register_messages(task_id, messages)` method to `FSMTurnState` or passing a callback from the controller.

3. Verify that `classify_tool_batch()` (M3 3.4.2) is NOT affected by injected messages. The classify function operates on `response.tool_calls` from the LLM output, not on the input messages list. Injected messages only affect what the LLM SEES on the next iteration.

4. Verify Python GIL safety: `list.append()` is atomic in CPython. The controller appends to `messages` from the FSM coroutine. Back's react_loop reads `messages` in the same event loop. Since both are coroutines (not threads), there is no concurrent access -- the GIL is moot. What matters is that the append happens BETWEEN `await model.generate()` calls, which is guaranteed because the controller processes user.input events between Back iterations.

5. Add test: dispatch task -> Back starts react_loop -> controller receives modify event -> controller appends to messages -> verify next Back iteration sees the injected message.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (RunningTaskHandle population in _on_task_dispatch, register_messages callback)
- `poc/k1_poc/actors/back.py` (register messages list with controller)
- `poc/k1_poc/fsm/turn_state.py` (add register_messages if using FSMTurnState as conduit)

**Dependency:** E5.2.3 (modify_inflight), M3 3.4.2 (classify_tool_batch), M3 react_loop architecture

**Acceptance:**

- `RunningTaskHandle.messages` is the SAME list object as react_loop's messages
- `list.append()` from controller is visible to next react_loop iteration
- `classify_tool_batch()` is NOT affected by injected messages (it reads tool_calls, not messages)
- `ReactResult.parallel_tool_calls` count unchanged by injection
- If task completes before modify arrives, `_handle_arbiter_modify()` falls back to PARALLEL_NEW
- No deadlock or race condition between controller and react_loop

---

#### 5.5.5 -- Wire Arbiter envelope enrichment into M4 prompt builder and M3 shared utilities

**Problem:** E5.3.2 adds `_enrich_envelope_with_arbiter()` which injects `arbiter_decision` and `routing_metadata` into the envelope payload delivered to Front. After M4, Front reads this payload via `actors/shared.py::parse_envelope_payload()` (M3 3.5.1). The enriched payload must be compatible with:

- M3's `parse_envelope_payload()`: This function parses JSON payload from the envelope. If `arbiter_decision` or `routing_metadata` keys are present, they must not cause parsing errors. Since `parse_envelope_payload()` returns a generic dict, this should work -- but verify.

- M4's `DynamicPromptBuilder.build(ss=ss)`: The builder uses `SS_READ_CONFIGS` keyed by PromptMode to determine which SS sections to read. If `routing_metadata` includes information that should influence section selection (e.g., "this is a modify-inflight scenario, include previous task results"), the builder needs a way to consume it. For M5 POC, the builder ignores routing_metadata. But the wiring must ensure the metadata is AVAILABLE in the builder context for future use.

- E5.3.3's `determine_mode(routing_metadata=...)`: Front extracts routing_metadata from envelope and passes to mode resolution. The mode returned determines SS_READ_CONFIGS. Even though M5 doesn't change mode resolution logic, the metadata flow must be end-to-end tested.

**What to do:**

1. Verify `parse_envelope_payload()` (M3 actors/shared.py) handles extra keys gracefully:

   ```python
   payload = parse_envelope_payload(envelope)
   # payload now contains: text, session_id, device_id, arbiter_decision, routing_metadata
   # All are optional dict keys -- parse_envelope_payload returns raw dict
   ```

2. Front handler (front.py L486-491) extracts routing_metadata and passes to determine_mode:

   ```python
   payload = parse_envelope_payload(envelope)
   routing_metadata = payload.get("routing_metadata")

   mode = determine_mode(
       fsm_state=resolved_fsm_state,
       envelope_topic=envelope.topic,
       clarification_state=clarification_state,
       task_state=task_state_dict,
       affect=affect_dict,
       routing_metadata=routing_metadata,  # M5 5.3.3
   )
   ```

3. Store routing_metadata on the builder context for future use (M8+ may consume it):

   ```python
   # In DynamicPromptBuilder or front_handler:
   builder_context = {
       "routing_metadata": routing_metadata,
       "arbiter_decision": payload.get("arbiter_decision"),
   }
   ```

4. Add test: send enriched envelope through full Front handler pipeline, verify routing_metadata reaches determine_mode, verify builder produces valid prompt, verify no parse errors.

**Files to verify:**

- `poc/k1_poc/actors/shared.py` (parse_envelope_payload compatibility)
- `poc/k1_poc/actors/front.py` (routing_metadata extraction and pass-through)
- `poc/k1_poc/prompt/mode.py` (determine_mode with routing_metadata parameter)
- `poc/k1_poc/prompt/builder.py` (builder context availability)

**Dependency:** E5.3.2 (envelope enrichment), E5.3.3 (routing_metadata on determine_mode), M3 3.5.1 (parse_envelope_payload), M4 4.4.2 (builder SS integration)

**Acceptance:**

- Enriched envelope with arbiter_decision + routing_metadata parses correctly
- Front handler extracts routing_metadata and passes to determine_mode
- determine_mode returns correct mode (unchanged behavior in M5 POC)
- routing_metadata is available in builder context for future milestones
- No parse errors or missing key exceptions

---

#### 5.5.6 -- Wire device_id tracking into M4 writer_port audit trail

**Problem:** E5.4.1 adds `device_id` to user input envelope payload and tracks active devices in MetaSection. But M4's writer_port mutations (4.2.1-4.2.4) don't carry device_id. When a cognitive tool writes to SS via writer_port, the mutation's `writer_id` is `"tool:front"` or `"tool:back"`, with no indication of which device triggered the turn.

For M11 observability and M9 crash recovery, knowing which device triggered a mutation is valuable. Rather than changing the `MutationRequest` schema (which would break M4's contract), pass device_id through context.

**What to do:**

1. Add `active_device_id` to ToolContext:

   ```python
   @dataclass
   class ToolContext:
       session_manager: Any
       cognitive_trace_id: str
       actor: str
       writer_port: Any | None = None          # M4 4.2.1
       idempotency_cache: dict = field(...)     # M4 4.5.5
       active_device_id: str | None = None      # M5 5.5.6
   ```

2. In bootstrap, extract device_id from the current turn's envelope and set on ToolContext before Front invocation:

   ```python
   # In _on_user_input, before delivering to Front:
   payload = _parse_payload(envelope)
   device_id = payload.get("device_id")
   if device_id and front_ctx:
       front_ctx.active_device_id = device_id
   ```

3. In `DirectWriterAdapter.request_mutation()` (M4 4.5.4), include device_id in structured logging:

   ```python
   logger.info(
       "WriterPort: mutation %s section=%s writer=%s device=%s",
       "APPROVED" if response.approved else "REJECTED",
       request.section,
       request.writer_id,
       getattr(request, 'device_id', None) or "unknown",
   )
   ```

4. In M4's `TurnMutationSummaryEvent` (4.5.4), include device_id:

   ```python
   TurnMutationSummaryEvent(
       turn_number=self._turn_number,
       approved=stats["total_approved"],
       rejected=stats["total_rejected"],
       by_section=stats["by_section"],
       device_id=active_device_id,  # M5 5.5.6
   )
   ```

5. Update MetaSection active device tracking (5.4.1) to write through M4's writer_port (not direct section mutation):

   ```python
   # M4-compliant device tracking write:
   writer_port.request_mutation(MutationRequest(
       section="meta",
       operation="set_active_device",
       payload={"device_id": device_id, "timestamp": time.time()},
       writer_id="system:fsm",  # System-owned section, system writer
   ))
   ```

**Files to modify:**

- `poc/k1_poc/tools/implementations.py` (add active_device_id to ToolContext)
- `poc/k1_poc/fsm/controller.py` (set active_device_id on ToolContext in _on_user_input)
- `poc/k1_poc/sessionstate/adapters/direct_writer.py` (include device_id in structured log)

**Dependency:** E5.4.1 (device_id tracking), M4 4.2.1 (writer_port on ToolContext), M4 4.5.4 (TurnMutationSummaryEvent)

**Acceptance:**

- ToolContext.active_device_id set from envelope payload before Front invocation
- Writer_port structured logs include device_id
- TurnMutationSummaryEvent includes device_id
- MetaSection device tracking writes go through writer_port (not direct mutation)
- Test: send input with device_id="phone-1", verify TurnMutationSummaryEvent has device_id="phone-1"

---

#### 5.5.7 -- Wire M5 artifacts into M1-M4 test fixtures

**Problem:** M1-M4 fixtures provide `create_wired_fsm(with_ledger, with_dead_letter_consumer, with_cancel_tokens, with_ss_binding, with_writer_port)`. M5 adds:

- ConversationArbiter instance on controller (E5.1.3) -- tests need FSMs with wired Arbiter
- `k1.arbiter.intent.v1` in guard table (5.5.1) -- guard table tests need arbiter topic
- RunningTaskHandle / _running_tasks (E5.2.3) -- modify-inflight tests need handle population
- ArbiterConfig in config (5.1.3) -- tests need configurable thresholds
- device_id on ToolContext (5.5.6) -- multi-device tests need device context

**What to do:**

1. Extend `create_wired_fsm()` in `testing/fixtures.py`:

   ```python
   def create_wired_fsm(
       *,
       capture: bool = True,
       with_ledger: bool = True,
       with_dead_letter_consumer: bool = True,
       with_cancel_tokens: bool = True,
       with_ss_binding: bool = True,
       with_writer_port: bool = True,
       with_arbiter: bool = True,            # NEW M5
       arbiter_config: ArbiterConfig | None = None,  # NEW M5
   ) -> dict:
       # ... M1+M2+M3+M4 setup unchanged ...
       if with_arbiter:
           from poc.k1_poc.fsm.arbiter import ConversationArbiter
           arbiter = ConversationArbiter(config=arbiter_config or ArbiterConfig())
           fsm._arbiter = arbiter
           result["arbiter"] = arbiter
       return result
   ```

2. Add arbiter test helpers:

   ```python
   def create_test_arbiter(
       *,
       domain_overlap_threshold: float = 0.7,
       entity_overlap_threshold: float = 0.5,
   ) -> ConversationArbiter:
       config = ArbiterConfig(
           domain_overlap_threshold=domain_overlap_threshold,
           entity_overlap_threshold=entity_overlap_threshold,
       )
       return ConversationArbiter(config=config)

   def create_test_inflight_context(
       *,
       tasks: list[InflightTask] | None = None,
       fsm_state: str = "COMPANIONING",
       pending_results: int = 0,
       device_id: str | None = None,
   ) -> InflightContext:
       return InflightContext(
           tasks=tasks or [],
           pending_results=pending_results,
           cancelled_task_ids=set(),
           fsm_state=fsm_state,
           current_turn=1,
           active_device_id=device_id,
       )
   ```

3. Add assertion helpers:

   ```python
   def assert_arbiter_decision(result: ArbiterResult, expected: ArbiterDecision) -> None:
       assert result.decision == expected, (
           f"Expected Arbiter decision {expected.value}, got {result.decision.value}"
       )

   def assert_ledger_has_intent_arbitrated(ledger_store, decision: str) -> None:
       events = [e for e in ledger_store.events if isinstance(e, IntentArbitrated)]
       assert any(e.decision == decision for e in events), (
           f"No IntentArbitrated({decision}) in ledger. Found: {[e.decision for e in events]}"
       )
   ```

4. Update `conftest.py` fixtures to include Arbiter by default.

**Files to modify:**

- `poc/k1_poc/testing/fixtures.py` (extend create_wired_fsm, add create_test_arbiter, create_test_inflight_context, assertion helpers)
- `tests/poc/conftest.py` (update fixtures for M5 defaults)

**Dependency:** E5.1.1-E5.4.4 (all M5 core changes), M1-M4 fixture patterns (1.4.7, 2.5.6, 3.7.6, 4.5.7)

**Acceptance:**

- `create_wired_fsm(with_arbiter=True)` returns FSM with ConversationArbiter instance
- `create_test_arbiter()` creates Arbiter with configurable thresholds
- `create_test_inflight_context()` creates InflightContext for test scenarios
- `assert_arbiter_decision()` and `assert_ledger_has_intent_arbitrated()` available for tests
- All M5 E5.2-E5.4 tests use these fixtures

---

#### 5.5.8 -- Backward compatibility: verify M1 ledger + M2 guard table + M3 back routing + M4 SS binding survive M5 refactoring

**Problem:** M5 replaces the user input path in COMPANIONING and PROGRESSING states (controller.py L635-703). This is the most heavily wired FSM code path -- it touches M1 ledger, M2 guard dispatch, M3 cancel tokens, M3 route_back_envelope, M4 TaskBridge, and M4 control overlay. Every prior milestone's wiring runs through `_on_user_input()`.

| M5 Change | M1/M2/M3/M4 Code Path At Risk |
|-----------|-------------------------------|
| Replace `InterruptClassifier.classify()` with `Arbiter.classify()` | M2 guard_dispatch flow -- Arbiter runs BEFORE guard_dispatch routes |
| Add `_handle_arbiter_cancel()` | M1 _ledger_append ordering; M3 cancel_tokens propagation |
| Add `_handle_arbiter_modify()` + RunningTaskHandle | M3 react_loop messages integrity; M4 writer_port (tools still route through it) |
| Add `_handle_arbiter_defer()` | M1 ledger -- defer must NOT record a TurnMutationSummaryEvent (no turn) |
| Add `_handle_arbiter_parallel_new()` | Must be IDENTICAL to current interrupt path (M1+M2+M3+M4 all apply) |
| Envelope enrichment with routing_metadata | M3 parse_envelope_payload compatibility; M4 builder prompt assembly |
| New `k1.arbiter.intent.v1` bus events | M2 guard table; M2 dead-letter pipeline |
| `routing_metadata` on determine_mode | M4 SS_READ_CONFIGS (PromptMode-based section reads) |
| device_id on MetaSection | M4 writer_port -- meta section writes go through managed path |

**What to do:**

1. Create `tests/poc/test_m05_wiring_regression.py`:

   **Test matrix:**

   | Test | Trigger | Expected M1-M4 Artifact | M5 Change That Could Break It |
   |------|---------|------------------------|-------------------------------|
   | `test_parallel_new_identical_to_pre_m5_path` | Arbiter returns PARALLEL_NEW in COMPANIONING | Same FSM trace as pre-M5 interrupt path (INTERRUPT_HANDLING -> DISPATCHING) | 5.2.1 replacement |
   | `test_ledger_records_intent_arbitrated` | Any user input in COMPANIONING | `IntentArbitrated` in ledger BEFORE any FSM action | 5.5.1 |
   | `test_arbiter_cancel_ledger_ordering` | Arbiter returns CANCEL | `TaskCancelledEvent` in ledger BEFORE cancel_handler mutation | 5.5.3 |
   | `test_arbiter_cancel_route_back_delivery` | Arbiter returns CANCEL | Back receives task.cancel via route_back_envelope | 5.5.3 |
   | `test_modify_inflight_messages_injection` | Arbiter returns MODIFY_INFLIGHT | Injected message visible in next react_loop iteration | 5.5.4 |
   | `test_defer_no_turn_increment` | Arbiter returns DEFER | turn_number unchanged; no TurnMutationSummaryEvent | 5.2.4 |
   | `test_guard_table_accepts_arbiter_topic` | Arbiter emits intent.arbitrated | No dead-letter; event passes guard_dispatch | 5.5.1 |
   | `test_enriched_envelope_parses_correctly` | Enriched envelope delivered to Front | parse_envelope_payload returns dict with routing_metadata | 5.5.5 |
   | `test_determine_mode_with_routing_metadata` | Front receives enriched envelope | determine_mode returns correct mode (unchanged behavior) | 5.3.3 + 5.5.5 |
   | `test_m4_ss_binding_survives_arbiter_refactor` | TaskBridge rebound + Arbiter + user input | SS task_state has real data; control overlay has fsm_state | 5.5.2 |
   | `test_m4_writer_port_survives_arbiter_refactor` | Cognitive tool via writer_port after Arbiter path | Mutation approved through writer_port (not bypassed) | M4 4.2.3 unchanged |
   | `test_m3_back_routing_survives_arbiter_refactor` | Arbiter PARALLEL_NEW -> Front dispatches task | route_back_envelope delivers to Back correctly | M3 3.1.1 unchanged |

2. Each test uses `create_wired_fsm(with_arbiter=True, with_ss_binding=True, with_writer_port=True)` from updated fixtures (5.5.7).

**Files to create:**

- `tests/poc/test_m05_wiring_regression.py`

**Dependency:** 5.5.1-5.5.7 (all wiring issues), M1-M4 regression test patterns

**Acceptance:**

- All 12 regression tests pass
- M4 `test_m04_wiring_regression.py` tests still pass after M5 changes
- M3 `test_m03_wiring_regression.py` tests still pass after M5 changes
- PARALLEL_NEW path produces identical FSM trace to pre-M5 interrupt path
- Zero dead-letters from arbiter topic under normal operation

---

#### 5.5.9 -- Full regression: demo smoke test with Arbiter active

**Problem:** M5 replaces the user input classification path, adds 4 new FSM behaviors (cancel/modify/defer/parallel_new), adds device tracking, and enriches envelope payloads. The demo web app must exercise all 4 Arbiter outcomes.

**What to do:**

1. Create `tests/poc/test_m05_demo_smoke.py`:

   **Scenario A: Normal path (LISTENING, no inflight) -- Arbiter returns PARALLEL_NEW**
   - Boot kernel
   - Send user input "search for hotels in Napa"
   - Verify: Arbiter emits IntentArbitrated(PARALLEL_NEW) (no inflight tasks)
   - Verify: FSM follows normal LISTENING -> DISPATCHING path
   - Verify: Front dispatches task -> Back executes
   - Verify: Same behavior as pre-M5 (regression-free)

   **Scenario B: Interrupt path (COMPANIONING, task inflight) -- Arbiter returns CANCEL**
   - Boot kernel, dispatch task "search hotels"
   - While COMPANIONING, send "cancel"
   - Verify: Arbiter emits IntentArbitrated(CANCEL)
   - Verify: No Front LLM call for cancel routing (deterministic)
   - Verify: cancel_handler.request_cancel() called
   - Verify: Back exits react_loop with status="cancelled"
   - Verify: Ledger has: IntentArbitrated(CANCEL) -> TaskCancelledEvent -> TaskFailed(cancelled)

   **Scenario C: Modify inflight -- Arbiter returns MODIFY_INFLIGHT**
   - Boot kernel, dispatch task "search hotels 3 nights Napa"
   - While COMPANIONING, send "make it 2 nights"
   - Verify: Arbiter emits IntentArbitrated(MODIFY_INFLIGHT) (domain overlap > 0.7)
   - Verify: Messages list gets injected "PARAMETER UPDATE" message
   - Verify: FSM stays COMPANIONING (no state transition)
   - Verify: Turn number unchanged
   - Verify: TaskModified event emitted

   **Scenario D: Defer -- Arbiter returns DEFER**
   - Boot kernel, dispatch task
   - While COMPANIONING, send "ok keep going"
   - Verify: Arbiter emits IntentArbitrated(DEFER)
   - Verify: No LLM call
   - Verify: FSM stays COMPANIONING
   - Verify: Turn number unchanged
   - Verify: History records defer entry

   **Scenario E: Multi-device conflict**
   - Boot kernel, dispatch task from device_id="desktop-1"
   - While COMPANIONING, send "cancel" from device_id="phone-1"
   - Verify: Arbiter resolves with device precedence
   - Verify: device_id tracked in MetaSection
   - Verify: TurnMutationSummaryEvent (if any) includes device_id

   **Scenario F: Demo health check with Arbiter**
   - Boot kernel
   - Verify: health check reports `arbiter_wired=True`
   - Verify: `/api/session/arbiter` (new endpoint) returns last classification
   - Verify: All M1-M4 health checks still pass

**Files to create:**

- `tests/poc/test_m05_demo_smoke.py`

**Dependency:** 5.5.1-5.5.8 (all wiring and regression), M4 4.5.9 (demo smoke pattern)

**Acceptance:**

- All 6 scenarios pass
- Arbiter classifications are deterministic (same input = same outcome)
- No LLM call for cancel or defer (system-level routing)
- Modify-inflight injection works with running Back react_loop
- Multi-device tracking produces correct audit trail
- All previous demo smoke tests (M2, M3, M4) still pass

---

### M5 Touchpoint Matrix: What M6-M12 Inherit from M5

| Milestone | M5 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M6** (HITL V3) | `ConversationArbiter` + `InflightContext` | HITL timeout triggers re-arbitration: if user says "I changed my mind" during HITL wait, Arbiter classifies against suspended task context. `InflightContext.pending_hil=True` informs decision. |
| **M6** (HITL V3) | `_handle_arbiter_modify()` + RunningTaskHandle | HITL resolution that modifies a suspended task uses the same inter-iteration injection pattern. Resume + modify = inject modification into resumed Back loop. |
| **M6** (HITL V3) | `device_id` tracking | HITL question sent to device A, answer from device B -- validate_hitl_wiring checks device consistency (5.4.4). |
| **M7** (BackPool) | `RunningTaskHandle._running_tasks` | Pool manager uses _running_tasks to track which Back workers are active. Arbiter cancel targets specific pool worker's task. |
| **M7** (BackPool) | `resolve_device_conflict()` | Multiple devices submitting to parallel pool -- precedence rules determine which device's task gets priority scheduling. |
| **M8** (Weave Policy) | `ArbiterResult.routing_metadata` | Adaptive weave reads `routing_metadata.intent_class` to determine if weave content is relevant to current conversation trajectory. Defer -> suppress weave. CANCEL -> clear weave queue. |
| **M8** (Weave Policy) | `_handle_arbiter_defer()` pattern | Weave acknowledgment uses defer pattern: user says "not now" to weave -> arbiter-like classification -> suppress weave without LLM call. |
| **M9** (Crash Recovery) | `IntentArbitrated` in ledger | Recovery replays arbiter decisions to reconstruct FSM state. If crash happens between IntentArbitrated and TaskCancelled, recovery knows a cancel was in progress. |
| **M9** (Crash Recovery) | `RunningTaskHandle` + messages injection | Recovery cannot replay injected messages (they're in-memory list mutations). Document as acceptable data loss -- the modification must be re-issued after recovery. |
| **M10** (UltraBERT) | `domain_overlap()` + `entity_overlap()` | UltraBERT replaces keyword-based similarity with semantic embedding similarity. Arbiter's similarity functions become wrappers around UltraBERT model calls. Same interface, better accuracy. |
| **M10** (UltraBERT) | `Phase1Result` as Arbiter input | UltraBERT-enhanced Phase1Result provides richer intent/entity/domain data. Arbiter decision quality improves automatically (no Arbiter code changes needed). |
| **M11** (Observability) | `IntentArbitrated` events in ledger | Metrics dashboard: arbiter decision distribution (cancel/modify/defer/parallel_new), confidence histograms, domain overlap scores. Alert on high CANCEL rate. |
| **M11** (Observability) | `device_id` on TurnMutationSummaryEvent | Per-device mutation breakdown: which device triggers most writes? Multi-device session analytics. |
| **M12** (Chaos Tests) | `ConversationArbiter.classify()` under rapid input | Rapid-fire user inputs from multiple devices. Verify Arbiter is deterministic under load. Verify FrontLock queue handles concurrent arbiter-enriched envelopes. |
| **M12** (Chaos Tests) | `RunningTaskHandle` messages injection under load | Race test: modify-inflight injection while Back is between iterations. Verify no message duplication or loss. |

**Total: 16 issues across 4 epics (E5.1-E5.4) + 9 issues in E5.5 wiring = 25 issues across 5 epics.**

---

## M6: HITL as First-Class Blocking Sub-Task

**Goal:** Elevate HITL from scattered in-memory protocol state to a formally
modeled blocking sub-task with persisted lifecycle, validated resume, and
canonical event emission. Wire the Back resume handler into the runtime so the
LLM's ReAct loop correctly continues from prior findings without repeating
work.

**Gate:** HITL request creates a blocking sub-task record with pending_hil_id,
hil_type, hil_deadline, resume_token. Side-effect invocations blocked at L2
until resolve event. Resume requires valid resume_token and starts a NEW
react_loop() (not injection into a running loop). back_resume_handler wired
and exercised. Single context-storage path (no dual-store drift). Timeout and
cancel paths emit canonical events. Crash recovery from persisted
TaskStateEntry.pending_hil verified.

**LLM Interaction Model (from code audit):**

| Actor | Mode | HITL Phase | Tools | Iterations | What Happens |
|-------|------|------------|-------|------------|--------------|
| Back | COMPANIONING / PROGRESSING | Suspension trigger | submit_result | N/A | Calls submit_result(needs_human). ReAct loop TERMINATES (status="suspended"). Loop is DONE, not paused. |
| Front | HITL_RELAY | Question relay | 0 tools | 1 | Pure text translation of structured HILRequest to natural language. Zero tools, single pass. |
| Front | HITL_RESOLVE | Answer parsing | update_beliefs | 3 (crisis: 2) | Parses user's NL answer into structured resolution. Calls update_beliefs to persist. |
| Back | Resume | Continuation | full tier tools | remaining_budget | NEW react_loop() with prior_messages + resolution. Reads fresh SS. Gets resume_instruction per hil_type. Budget = original - tools_called (min 2). |

**Critical invariant:** Back's ReAct loop does NOT "block" or "pause." It
terminates on submit_result(needs_human). The FSM prevents new Back dispatch
for this task_id until resume. Resume starts a FRESH react_loop() call with
conversation history replayed via prior_messages.

---

### E6.1 -- HITL Sub-Task State Model

Source: WB 3.E, 5, 8.5

**Rationale:** The current HITL state is scattered across four in-memory
locations: HILCoordinator._pending_requests (dict[str, HILRequest]),
SuspensionManager._active (dict[str, SuspensionRequest]),
SuspensionManager._contexts (dict[str, dict]), and
FSMTurnState.pending_context (dict[str, dict]). There is no single
authoritative record. This epic creates a formal HILSubTask record that is
the single source of truth, wrapping HILRequest + suspension context +
ReAct snapshot into one persist-ready dataclass.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 6.1.1 | Define HILSubTask dataclass with fields: pending_hil_id (UUID), hil_type (clarification / approval / selection), hil_deadline (created_at_ns + timeout_ms), resume_token (uuid4), parent_task_id, react_snapshot (prior_messages list + tool_history list + last_iteration int), status enum (PENDING / RESOLVED / TIMED_OUT / CANCELLED). Wraps HILRequest + suspension context into one record. Implement to_persistence() and from_persistence() for crash recovery serialization. Place in protocols/hitl_persistence.py alongside existing TaskStateEntry. | WB 3.E | None (data model). Foundation for all other M6 issues. |
| 6.1.2 | Create HILSubTask in _on_task_suspended (controller.py L1292-1388). Replace the current two-step storage path -- SuspensionManager.store_context(task_id, payload) plus FSMTurnState.store_pending_context -- with single HILSubTask creation. Store the serialized HILSubTask in TaskStateEntry.pending_hil via the existing suspend(hil_request) method, extended to accept the react_snapshot. The FSM handler must capture prior_messages from the Back ReactResult.data before the loop context is lost. | WB 3.E | Eliminates dual-store drift (WB 14.4C). When Back resumes, it reads react_snapshot from ONE source. No risk of SuspensionManager._contexts and FSMTurnState.pending_context disagreeing on what the LLM saw before suspension. |
| 6.1.3 | Block side-effect invoke_capability when HILSubTask is PENDING for this task_id. Wire validate_before_invoke() (hitl_coordinator.py L~480) into the invoke_capability tool execution path in tools/implementations.py. Currently validate_before_invoke exists and returns "allow" / "block_needs_approval" / "block_red" but is never called from the tool dispatch path. On "block_needs_approval" or "block_red", return a ToolResult with status="blocked" and reason, instead of executing the capability. | WB 5 | Back LLM cannot execute side-effecting tools while a HITL is pending for this task (L2 defense-in-depth). If a stale or replayed Back loop somehow invokes a side-effecting capability, it gets a "blocked" ToolResult rather than execution. The LLM sees the block in its tool output and must call submit_result instead. |
| 6.1.4 | Validate resume_token on task.resume.v1 before dispatching to Back. Generate resume_token (uuid4) at HILSubTask creation time. Include resume_token in the TaskSuspendedEvent payload delivered to Front. Front must echo resume_token in TaskResumeEvent. In _on_task_resume (controller.py L1389-1480), compare event resume_token against HILSubTask.resume_token; reject mismatches with a warning log and no Back dispatch. | WB 5 | Prevents stale or replayed resume events from restarting Back's ReAct loop with wrong context. Without token validation, a delayed duplicate task.resume.v1 could restart a Back loop for a task that already completed or was cancelled. |
| 6.1.5 | Consolidate suspension-limit enforcement to HILSubTask creation point. Currently limits are checked in two places: SuspensionManager.suspend() checks max_concurrent (1) and per-task count (2), while HILCoordinator.handle_needs_human() checks its own max_rounds config. Merge into a single check at HILSubTask creation in _on_task_suspended. When max reached: treat submit_result(needs_human) as submit_result(complete) with data.max_hil_reached=true marker, so the Back LLM's loop exits normally instead of entering a suspension that will be immediately rejected. | WB 5 | Prevents Back LLM from entering an infinite clarification loop where it repeatedly calls submit_result(needs_human). After 2 suspensions for a task, the loop exits as "complete" and the FSM treats it as a task that could not finish with HITL assistance. |

---

### E6.2 -- Back Resume Path & ReAct Integration

Source: WB 14.4A, 14.4B, 14.4C, 8.5

**Rationale:** back_resume_handler (back.py L500-665) implements the correct
10-step resume flow: retrieve pending context, re-read SS (fresh snapshot),
build system prompt, hydrate resolution into messages with RESUME_INSTRUCTIONS
per hil_type, calculate remaining budget (original - tools_called, min 2),
select tools by tier, build cancellation callback, invoke a NEW react_loop()
with prior_messages. But this handler is NOT wired: the Back mailbox consumer
always dispatches to back_handler() regardless of envelope topic. Resume
currently goes through generic back_handler, which starts a brand-new ReAct
loop with zero history -- the LLM re-discovers capabilities, re-executes
tools, and ignores the user's answer.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 6.2.1 | Wire back_resume_handler into the Back mailbox consumer. Add topic-based routing in the Back actor's message dispatcher: if envelope topic matches "task.resume.v1", dispatch to back_resume_handler; otherwise dispatch to back_handler. Currently all Back mailbox events route to back_handler regardless of topic. The routing check must happen after envelope validation but before handler invocation. | WB 14.4A | **Highest LLM impact in M6.** Without this, Back LLM restarts from scratch on every resume -- re-discovers capabilities, re-executes all tools, ignores the user's HITL answer entirely. With this, Back LLM sees its full prior conversation (prior_messages), the user's resolution, and the resume instruction telling it to continue where it left off. |
| 6.2.2 | Unify context storage to HILSubTask (from 6.1.2). Remove SuspensionManager._contexts dict usage and FSMTurnState.pending_context dict usage for HITL flows. back_resume_handler retrieves react_snapshot from HILSubTask via TaskStateEntry.pending_hil (deserialized). _on_task_resume reads HILSubTask to build ResumeContext instead of calling suspension_manager.pop_context() then separately reading fsm_state.pending_context. Update build_resume_context() in hitl_wiring.py to accept HILSubTask directly. | WB 14.4C | Eliminates risk of Back LLM receiving stale or mismatched context on resume. With dual stores, SuspensionManager could hold one version of findings_so_far while FSMTurnState holds a different version -- Back LLM would get confused by inconsistent history. Single source makes the prior_messages authoritative. |
| 6.2.3 | Make cancellation callback mandatory for Back dispatch. When dispatching to back_handler or back_resume_handler, always pass fsm_state so the ReAct loop can check for inter-iteration cancellation. Wire the cancel check into react_loop's between-iteration checkpoint (loop.py, the point between iterations where the loop checks should_continue). This enables: (a) HITL timeout fires while a resumed Back is mid-loop -- cancel between iterations; (b) user explicitly cancels a task while Back is running -- cancel between iterations. | WB 14.4B | Enables HITL timeout to terminate a resumed Back loop between ReAct iterations rather than waiting for full loop completion. The LLM's current iteration finishes (no mid-generation cancel -- same constraint as M5 H2), but the next iteration does not start. Without this, a timed-out HITL leaves a zombie Back loop running. |
| 6.2.4 | Validate prior_messages hydration in back_resume_handler. Ensure the resume message injected into prior_messages contains: (a) the hil_type-specific RESUME_INSTRUCTIONS text from hitl_wiring.py (clarification / approval / selection each have distinct instructions); (b) the structured resolution dict from HILResponse; (c) merged_params for approval flows where user said "approve with modifications" (from hitl_pipeline.py apply_approval_modifications); (d) selected_data for selection flows (from hitl_pipeline.py resolve_selection_to_params). The Back LLM's context window must show: all prior tool calls and results as assistant/tool messages, then a new user-role message with the resume instruction + resolution. | WB 8.5 | **Second highest LLM impact.** The RESUME_INSTRUCTIONS text (hitl_wiring.py L55-80) is the ONLY mechanism telling the LLM "do NOT re-execute tools that already succeeded" and "use findings_so_far as your starting state." Without correct hydration the LLM naively repeats all prior work. For approval flows, if merged_params are missing, the LLM ignores the user's modifications (violates Invariant 8). |
| 6.2.5 | Validate remaining_budget computation: remaining = max(2, total_budget - last_iteration). Ensure back_resume_handler reads last_iteration from HILSubTask.react_snapshot.last_iteration (not guessed or defaulted to 0). The min-2 floor guarantees the LLM gets at least one tool call + one submit_result on resume. Add a warning log if remaining_budget < 3 (tight budget). Add a metric for remaining_budget distribution to detect tasks that consistently exhaust budget before suspension. | WB 8.5 | If remaining_budget is wrong (e.g., last_iteration defaults to 0 so remaining = total_budget, giving full budget), the LLM gets too many iterations and wastes tokens re-exploring. If remaining_budget is too low (e.g., computed from wrong total), the LLM hits budget exhaustion and force-text-exits via the degenerate path (loop.py forced-text fallback from M3). Min-2 prevents the zero-budget edge case where the loop immediately exits without letting the LLM act. |

---

### E6.3 -- HITL Lifecycle Events & Decision Routing

Source: WB 12.3, 12.4, 12.5

**Rationale:** The current HITL flow produces no canonical bus events between
suspension and resume. The FSM writes history entries (entry_type=
"hitl_request" and "hitl_response" in controller.py) but does not emit typed
bus events that downstream consumers (observability, ledger, audit) can
subscribe to. Each HITL decision branch -- approve / approve-with-mods /
cancel for approval; selected for selection; resolved for clarification --
needs its own event so the ledger can reconstruct the exact HITL lifecycle
and auditors can verify that side-effect approvals were obtained.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 6.3.1 | Emit hitl.requested.v1 event when HILCoordinator.handle_needs_human() creates the HILSubTask. Payload: pending_hil_id, hil_type, parent_task_id, question, options, safety_band, hil_deadline, resume_token. This is the "sub-task created" event. Emit on the bus after HILSubTask is persisted to TaskStateEntry but before Front HITL_RELAY invocation. | WB 12.3 | None directly (observability event). Enables downstream consumers to know a human is being asked a question, and to correlate the pending_hil_id with subsequent resolve/timeout events. |
| 6.3.2 | Emit hitl.resolved.v1 event when HILCoordinator.handle_user_response() processes the user's answer. Include decision_branch field with values: "clarified" (clarification flow), "approved" (approval without mods), "approved_with_mods" (approval + modifications), "cancelled" (approval cancelled), "selected" (selection flow). For approved_with_mods, include merged_params in payload. For selected, include selected_option and target. Emit after HILSubTask.status set to RESOLVED but before Back resume dispatch. | WB 12.3 | For approved_with_mods, the merged_params in this event are what Back LLM will receive in its ResumeContext. This event provides auditable proof that the user-modified params were correctly computed by apply_approval_modifications() before Back was given them. |
| 6.3.3 | Emit hitl.timed_out.v1 event from SuspensionManager._watch_timeout() when the asyncio.sleep timer fires and the HILSubTask is still PENDING. Wire timeout to auto-cancel path: set HILSubTask.status=TIMED_OUT, set TaskStateEntry.status=CANCELLED with reason="hil_timeout", notify Front of cancellation. Currently HILTimeoutEvent dataclass exists in hitl_persistence.py with to_payload() / from_payload() but is never emitted on the bus. Wire the existing dataclass to actual bus emission. | WB 12.4 | Timeout auto-cancels the task. Back LLM is never resumed for this task_id. Front receives a notification to inform the user that the question expired. Without this event, timed-out HILSubTasks remain PENDING in-memory (state leak), and no cleanup occurs. |
| 6.3.4 | Emit hitl.blocked_red.v1 event when HILCoordinator.handle_needs_human() encounters safety_band=RED (via the on_blocked_red callback). Currently on_blocked_red is a configurable callback that only logs. Wire it to emit a bus event with payload: task_id, capability_name, safety_band, reason="red_band_blocked". This proves the system correctly refused to execute a RED-band capability without any LLM bypass. | WB 12.4 | RED-band capabilities are never executed, period. The Back LLM called submit_result(needs_human) for a RED-band capability, but the coordinator blocks it entirely instead of creating an HILSubTask. The LLM's loop already terminated (via submit_result), and no resume will ever come. The event provides audit proof of the block. |

---

### E6.4 -- HITL Persistence & Crash Recovery

Source: WB 12.2.D, 9.6

**Rationale:** All current HITL state lives in-memory:
HILCoordinator._pending_requests (dict[str, HILRequest]),
SuspensionManager._active (dict[str, SuspensionRequest]),
SuspensionManager._contexts (dict[str, dict]),
SuspensionManager._timeout_tasks (dict[str, asyncio.Task]).
Process crash = total HITL state loss. hitl_persistence.py already provides
TaskStateEntry with pending_hil field, scan_for_recovery() that categorizes
SUSPENDED tasks as recoverable vs timed-out, and build_timeout_events() that
creates HILTimeoutEvent for expired tasks. The data model and recovery logic
exist; the wiring to FSM startup does not.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 6.4.1 | Persist HILSubTask to TaskStateEntry.pending_hil on every suspend. Use the existing TaskStateEntry.suspend(hil_request) method, extended to include react_snapshot (prior_messages + tool_history + last_iteration) in the serialized pending_hil dict. The react_snapshot is essential: without it, crash recovery cannot build prior_messages for Back resume, and the Back LLM would restart from scratch after a crash -- repeating every tool call. Persist the full serialized HILSubTask via to_persistence() so from_persistence() can reconstruct it on recovery. | WB 12.2.D | Without persisted react_snapshot, crash recovery rebuilds a ResumeContext with empty findings_so_far. Back LLM resumes with no conversation history, re-discovers capabilities, re-executes tools. With persisted snapshot, Back LLM resumes exactly where it left off, same as a non-crash resume. |
| 6.4.2 | Wire scan_for_recovery() (hitl_persistence.py) to FSM startup. On FSM **init** or first activation, call scan_for_recovery(task_state) passing the persisted task_state dict loaded from Session State. This function already exists and correctly categorizes SUSPENDED tasks with pending_hil into recovered (within timeout) vs timed_out (past deadline). Currently it is never called. Add the call after Session State is loaded but before the FSM begins processing new events. | WB 9.6 | Determines post-crash behavior for each suspended task: recoverable tasks get re-presented to the user (Back LLM waits for answer then resumes with full context); timed-out tasks get auto-cancelled (Back LLM is never resumed). Without this, all SUSPENDED tasks after crash are orphaned -- no resume, no cancel, no cleanup. |
| 6.4.3 | Re-present recoverable suspensions to user via Front HITL_RELAY on startup. For each recovered task_id from scan_for_recovery(), deserialize HILSubTask from TaskStateEntry.pending_hil via from_persistence(), rebuild HILRequest with adjusted hil_deadline (remaining time = original_deadline - elapsed since crash), and invoke Front in HITL_RELAY mode to re-ask the question. The user sees the question again. When they answer, the normal HITL_RESOLVE + task.resume.v1 flow executes and Back resumes with the persisted react_snapshot. | WB 9.6 | The user sees the pending question again after restart. Front LLM gets the same HITL_RELAY invocation as the original (0 tools, 1 iteration, translate question to NL). Back LLM does NOT start until the user answers -- then it resumes with full prior_messages from the persisted react_snapshot, continuing where it left off pre-crash. |
| 6.4.4 | Auto-cancel expired suspensions on startup. For each timed_out task_id from scan_for_recovery(), call build_timeout_events() (hitl_persistence.py) to create HILTimeoutEvent instances, emit them on the bus (wired in 6.3.3), set TaskStateEntry.status=CANCELLED with reason="hil_timeout_post_crash", and set HILSubTask.status=TIMED_OUT. Notify Front to inform the user that the pending question expired during downtime. Clean up any stale in-memory state that may have been partially reconstructed. | WB 9.6 | Timed-out tasks are definitively closed. Back LLM is never resumed for expired tasks -- no wasted tokens, no confusion from stale context. The user is informed via Front that the question they were asked is no longer relevant. No orphan SUSPENDED records remain in task_state. |

---

### M6 HITL ReAct Loop Lifecycle Audit

**Constraints derived from code reading (protocols/hitl.py, hitl_coordinator.py,
hitl_wiring.py, hitl_flow.py, hitl_pipeline.py, hitl_persistence.py,
suspension.py, suspension_manager.py, suspension_events.py, actors/back.py,
actors/front.py, fsm/controller.py, react/loop.py,
tools/implementations.py):**

| # | Constraint | Code Evidence | M6 Implication |
|---|-----------|---------------|----------------|
| H1 | submit_result(needs_human) TERMINATES Back's react_loop() immediately. Loop returns ReactResult(status="suspended"). The Back LLM is not "paused" -- its loop is DONE. | loop.py L487-492, implementations.py L960-1005 | M6 language says "FSM blocks dispatch for task_id" not "Back execution path blocked." The LLM is not running during suspension. |
| H2 | Resume creates a NEW react_loop() invocation with prior_messages + resolution_message appended. It is NOT injection into a running loop. | back.py L530-620 (back_resume_handler) | E6.2 wires back_resume_handler so this new-loop-with-history pattern executes. Without it, generic back_handler starts a brand-new loop with zero history. |
| H3 | Back re-reads SS on resume (fresh snapshot). SS may have changed during suspension (affect, beliefs, control updated by intervening turns). | back.py L545-555 | The Back LLM's system prompt is built from the CURRENT SS, not the pre-suspension SS. Correct: the LLM should see updated family state. The react_snapshot preserves conversation history; the system prompt reflects current state. |
| H4 | Remaining budget = max(2, total_budget - last_iteration). The min-2 floor ensures at least one tool call + one submit_result. | back.py L580-590, hitl_wiring.py build_resume_context() | E6.2.5 validates this. If budget is 0, the ReAct loop force-text-exits (degenerate path from M3). |
| H5 | RESUME_INSTRUCTIONS per hil_type are the ONLY mechanism telling the LLM not to repeat work. Three distinct instructions exist: clarification ("use findings_so_far as starting state"), approval ("do NOT call discover_capabilities again"), selection ("do NOT re-execute the discovery search"). | hitl_wiring.py L55-80 (RESUME_INSTRUCTIONS dict) | E6.2.4 validates that the correct instruction is hydrated into prior_messages. This is the highest-impact LLM interaction in M6. |
| H6 | Front HITL_RELAY has 0 tools, 1 iteration. Front HITL_RESOLVE has {update_beliefs}, 3 iterations (crisis: 2). validate_hitl_wiring() checks 14 cross-layer invariants but is NEVER called at startup. | hitl_wiring.py L320-435 (validate_hitl_wiring) | Call validate_hitl_wiring() at FSM startup. If wiring is wrong (e.g., HITL_RELAY accidentally gets tools), Front LLM could call tools in relay mode -- breaking the pure-text-translation invariant. |
| H7 | Approval modifications are merged BEFORE Back resume (Invariant 8 from hitl_pipeline.py). apply_approval_modifications() does shallow merge. Back sees merged_params in ResumeContext, not original_params. | hitl_pipeline.py L90-130 (apply_approval_modifications), L155-200 (process_approval_response) | E6.2.4 ensures merged_params flows through ResumeContext into prior_messages. If Back LLM sees original params instead of merged params, it ignores the user's "go ahead but use the Amex" modification. |
| H8 | Front HITL_RESOLVE does NOT directly emit task.resume. Front parses the user's NL answer into structured resolution via update_beliefs, then completes. The FSM extracts the resolution from Front's output and internally dispatches task.resume.v1 to Back. | hitl_wiring.py get_hitl_resolve_config() tools={update_beliefs}, controller.py_on_task_resume | The resume event is FSM-initiated, not Front-initiated. Front LLM's only job is parsing NL to structured resolution. It cannot directly trigger Back. |

---

### Recommended Execution Order

1. **6.1.1** (HILSubTask dataclass -- foundation for all other issues)
2. **6.1.2** (create HILSubTask in controller -- unify storage at creation)
3. **6.2.2** (unify context storage reads -- remove dual-store consumers)
4. **6.2.1** (wire back_resume_handler -- highest LLM impact)
5. **6.2.4** (validate prior_messages hydration -- second highest LLM impact)
6. **6.2.5** (validate remaining_budget -- prevents degenerate loops)
7. **6.1.3** (L2 side-effect blocking via validate_before_invoke)
8. **6.1.4** (resume_token validation -- prevents stale resumes)
9. **6.1.5** (suspension limits consolidation -- prevents infinite loops)
10. **6.2.3** (cancellation callback mandatory -- enables timeout cancel)
11. **6.3.1** (hitl.requested event -- observability)
12. **6.3.2** (hitl.resolved event with decision_branch -- observability)
13. **6.3.3** (hitl.timed_out event -- timeout auto-cancel path)
14. **6.3.4** (hitl.blocked_red event -- audit)
15. **6.4.1** (persist HILSubTask with react_snapshot -- crash recovery foundation)
16. **6.4.2** (wire scan_for_recovery to startup -- categorize SUSPENDED tasks)
17. **6.4.3** (re-present recoverable suspensions via HITL_RELAY)
18. **6.4.4** (auto-cancel expired suspensions with HILTimeoutEvent)

---

### E6.5 -- End-to-End Wiring & System Integration

Source: Bootstrap analysis, fsm/controller.py, actors/back.py, protocols/hitl_coordinator.py, protocols/hitl_persistence.py, protocols/hitl_wiring.py, protocols/suspension_manager.py, bus/topics.py, bus/builders.py, react/loop.py, tools/implementations.py, demo/coordinator.py, config/loader.py

**Why this epic exists:** E6.1-E6.4 create a formal HILSubTask state model, wire back_resume_handler into the Back mailbox, emit 4 new bus event topics, add resume_token validation, wire validate_before_invoke into the tool execution path, consolidate suspension limits, and add crash recovery at FSM startup. But these changes span every layer of the system -- protocol, FSM, actor, bus, tool dispatch, persistence, and recovery. Without explicit wiring:

- The 4 new bus topics (`hitl.requested.v1`, `hitl.resolved.v1`, `hitl.timed_out.v1`, `hitl.blocked_red.v1`) are published to the bus but have no M2 guard table entries (guard_dispatch rejects them as unknown topics -> dead-letter storm for every HITL flow)
- M1's LedgerMiddleware has no canonical event classes for HITL lifecycle events (ledger drops them or records raw envelope dumps instead of structured events)
- `back_resume_handler` (6.2.1) is wired for topic-based routing but M3's `route_back_envelope()` must know to route `task.resume.v1` to Back, not just `task.dispatch.v1` and `task.cancel.v1`
- HILSubTask replaces SuspensionManager._contexts as context source (6.2.2), but M5's `build_inflight_context()` reads suspended task info from SuspensionManager -- it must switch to HILSubTask
- `validate_before_invoke()` (6.1.3) checks capability contracts before execution, but M4's cognitive tools go through `writer_port.request_mutation()` not invoke_capability -- they must be excluded from L2 blocking
- `scan_for_recovery()` (6.4.2) runs at FSM startup but M4's SS binding (TaskBridge.rebind) must happen BEFORE recovery scan reads task_state from SS
- `resume_token` (6.1.4) must be included in the envelope payload flowing from FSM -> Front -> FSM -> Back, but M3's `parse_envelope_payload()` must handle the new field
- Crash recovery (6.4.3) re-presents HITL via Front HITL_RELAY, but M5's device_id tracking means the re-presented question must preserve the original device context
- `hitl.timed_out.v1` auto-cancel (6.3.3) transitions task to CANCELLED, but M5's Arbiter InflightContext must immediately see the task as cancelled (not still pending_hil)

**Every M6 artifact must plug into the cumulative M1+M2+M3+M4+M5 infrastructure or the HITL system exists as a disconnected state model with no runtime integration.**

**System state after M1+M2+M3+M4+M5 (E1.4 + E2.5 + E3.7 + E4.5 + E5.5 wiring complete) -- what M6 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created             # M1 1.4.1
  -> LedgerMiddleware in bus middleware chain                # M1 1.4.4
  -> ConciergeController(bus, router)
     -> set_ledger(writer)                                  # M1 1.4.1
     -> _ledger_append() in 11 handlers                     # M1 1.4.2
     -> _try_deserialize() bridge                           # M1 1.4.3
     -> _dispatch_envelope() flow:                          # M2 2.5.3
          topic_guard -> idempotency -> guard_dispatch -> handler
     -> FULL_GUARD_TABLE + _guard_dispatch()                # M2 2.1.1-2.1.2
     -> _publish_dead_letter() with ledger recording        # M2 2.5.2
     -> IdempotencyLedger                                   # M2 2.3.2
     -> decide_response_final() + ResponseFinalEvent        # M2 2.3.1, 2.5.4
     -> Per-task CancellationToken in _cancel_tokens        # M3 3.2.2
  -> route_back_envelope() as canonical back dispatch        # M3 3.1.1-3.1.3
  -> DeadLetterConsumer subscribed to bus                    # M2 2.5.1
  -> Unknown back topics -> dead-letter pipeline             # M3 3.7.1
  -> builders auto-enrich legacy dicts                       # M1 1.4.5
  -> actors/shared.py: parse_envelope_payload,
       safe_get_section, never_cancel                        # M3 3.5.1-3.5.3
  -> SuspensionManager as sole resume-context owner          # M3 3.3.1
  -> classify_tool_batch() in react_loop                     # M3 3.4.2
  -> ReactResult carries parallel/sequential counts          # M3 3.7.4
  -> TaskBridge.rebind() to real SS task_state/task_artifacts # M4 4.1.1, 4.5.1
  -> ControlExtension.bind_control_section() + fsm_overlay   # M4 4.1.2, 4.5.2
  -> writer_port (DirectWriterAdapter) on ToolContext         # M4 4.2.1, 4.5.3
  -> 6 cognitive tools through writer_port.request_mutation() # M4 4.2.3
  -> LLM-writable allowlist in config                        # M4 4.2.2
  -> Runtime guard rejecting LLM writes to system sections   # M4 4.2.4
  -> update_session_bundle with batch_mutations              # M4 4.3.1-4.3.3
  -> SECTION_RENDERERS + _read_ss_sections() in stage 8      # M4 4.4.1-4.4.2
  -> DynamicPromptBuilder.build(ss=ss) parameter             # M4 4.4.2
  -> TurnMutationSummaryEvent in ledger at turn completion   # M4 4.5.4
  -> ToolContext.idempotency_cache for bundle dedup           # M4 4.5.5
  -> ConversationArbiter replaces InterruptClassifier         # M5 5.5.1
  -> ArbiterDecision enum (CANCEL/MODIFY_INFLIGHT/PARALLEL_NEW/DEFER) # M5 5.2.1
  -> InflightContext from SS task_state + control overlay     # M5 5.5.2
  -> k1.arbiter.intent.v1 event in guard table + ledger      # M5 5.5.1
  -> _handle_arbiter_cancel/modify/defer/parallel_new         # M5 5.2.2-5.2.5
  -> RunningTaskHandle + _running_tasks for message injection # M5 5.5.4
  -> _enrich_envelope_with_arbiter() + routing_metadata       # M5 5.5.5
  -> device_id tracking on MetaSection + ToolContext           # M5 5.5.6
  -> resolve_device_conflict() precedence rules               # M5 5.4.2
  -> Multi-device confirmation via clarification mechanism    # M5 5.4.3
  -> Demo: ledger health + /api/ledger/stats                 # M1 1.4.6
  -> Demo: dead-letter health + /api/dead-letters            # M2 2.5.5
  -> Demo: parallel_tools_enabled in health check            # M3 3.7.4
  -> Demo: control overlay + /api/session/control            # M4 4.5.2
  -> Demo: writer_port_wired in health check                 # M4 4.5.3
  -> Demo: arbiter_wired + /api/session/arbiter              # M5 5.5.9
  -> Fixtures: create_wired_fsm(with_ledger,
       with_dead_letter_consumer, with_cancel_tokens,
       with_ss_binding, with_writer_port, with_arbiter)      # M1-M5 fixtures
```

**M6 artifacts that must integrate into this M1+M2+M3+M4+M5-wired system:**

| M6 Artifact | Where It Lives After E6.1-E6.4 | M1+M2+M3+M4+M5 Touchpoint It Must Connect To |
|-------------|-------------------------------|----------------------------------------------|
| `HILSubTask` dataclass (PENDING/RESOLVED/TIMED_OUT/CANCELLED) | `protocols/hitl_persistence.py` | M1 ledger needs canonical event classes (HILRequestedEvent, HILResolvedEvent) for structured recording; M3 SuspensionManager._contexts replaced as SOT; M5 InflightContext.pending_hil must read from HILSubTask |
| `HILSubTask` creation in `_on_task_suspended()` | `fsm/controller.py` | M1 `_ledger_append()` must fire BEFORE HILSubTask creation (record then mutate); M2 guard table must allow `task.suspended.v1` to trigger HILSubTask path; M4 TaskBridge.suspend_task() must sync with HILSubTask status |
| `hitl.requested.v1` / `hitl.resolved.v1` / `hitl.timed_out.v1` / `hitl.blocked_red.v1` topics | `bus/topics.py`, `bus/builders.py` | M2 FULL_GUARD_TABLE needs entries for all 4 topics; M2 dead-letter pipeline must not reject them; M1 LedgerMiddleware must record them; M2 IdempotencyLedger must handle HITL event dedup |
| `back_resume_handler` wired via topic routing | `actors/back.py` | M3 `route_back_envelope()` must route `task.resume.v1` to Back (currently only routes task.dispatch and task.cancel); M3 cancel tokens must propagate to resumed loop; M3 `classify_tool_batch()` applies unchanged to resumed loop |
| `validate_before_invoke()` wired to tool dispatch | `tools/implementations.py` | M4 cognitive tools via `writer_port.request_mutation()` bypass invoke_capability -- must NOT be blocked by L2 check; M4 LLM-writable allowlist is orthogonal to L2 safety check (different defense layers) |
| `resume_token` generation and validation | `fsm/controller.py` | M3 `parse_envelope_payload()` must handle resume_token field; M5 `_enrich_envelope_with_arbiter()` must preserve resume_token in enriched payloads; M5 device_id + resume_token together validate "right device, right token" |
| Consolidated suspension limits at HILSubTask creation | `fsm/controller.py` | M5 InflightContext must reflect accurate hil_suspensions_count from HILSubTask (not stale SuspensionManager count); Arbiter's classify() must see pending_hil=True when limit forces complete-instead-of-suspend |
| `scan_for_recovery()` wired to FSM startup | `fsm/controller.py` | M4 TaskBridge.rebind() must execute BEFORE recovery scan (SS sections must be live); M1 ledger must record recovery actions; M4 ControlExtension.bind_control_section() must be ready for recovery transitions |
| Re-present recoverable suspensions via HITL_RELAY | `fsm/controller.py` | M5 device_id: re-presented HITL preserves original device context; M4 DynamicPromptBuilder.build(ss=ss) builds Front HITL_RELAY prompt from current SS (post-recovery) |
| Auto-cancel expired suspensions on startup | `fsm/controller.py` | M5 InflightContext: auto-cancelled tasks must appear as CANCELLED (not pending_hil); M1 ledger records HILTimedOutEvent for each auto-cancel; M2 dead-letter: timeout events are NOT dead letters |
| Unified context storage (HILSubTask replaces dual-store) | `back.py`, `controller.py`, `hitl_wiring.py` | M3 SuspensionManager._contexts no longer used for HITL context (only for timeout watchers); M5 `build_inflight_context()` reads pending_hil from HILSubTask.to_persistence() stored on TaskStateEntry |
| Cancellation callback mandatory for Back dispatch | `back.py`, `react/loop.py` | M3 between-iteration cancellation check already exists; M6 makes it REQUIRED (not optional). M5 RunningTaskHandle cancel path must propagate through same callback |

---

#### 6.5.1 -- Register 4 HITL event topics in M2 guard table and M1 ledger pipeline

**Problem:** E6.3.1-E6.3.4 create 4 new bus topics (`hitl.requested.v1`, `hitl.resolved.v1`, `hitl.timed_out.v1`, `hitl.blocked_red.v1`) and emit them at HITL lifecycle boundaries. But M2's `_dispatch_envelope()` flow (2.5.3) runs: topic_guard -> idempotency -> guard_dispatch -> handler. If these 4 topics have no `FULL_GUARD_TABLE` entries, `_guard_dispatch()` rejects them as unknown topics and routes every HITL event to dead-letter. The entire HITL lifecycle would generate dead-letter storms.

Additionally, M1's `LedgerMiddleware` (1.4.4) records all bus events. Without canonical event classes, the ledger records raw envelope dumps instead of structured HITL events.

**What to do:**

1. Add all 4 HITL topics to `FULL_GUARD_TABLE` in `fsm/controller.py`:

   ```python
   # HITL lifecycle events -- informational, emitted BY the FSM/coordinator.
   # Allowed in states where HITL can occur (CLARIFYING_WORKER for most,
   # COMPANIONING/PROGRESSING for requested, any state for timeout).
   # These are passthrough for observability -- they do NOT cause state transitions.
   (ConciergeState.CLARIFYING_WORKER, TOPIC_HITL_REQUESTED): [ConciergeState.CLARIFYING_WORKER],
   (ConciergeState.COMPANIONING, TOPIC_HITL_REQUESTED): [ConciergeState.COMPANIONING],
   (ConciergeState.PROGRESSING, TOPIC_HITL_REQUESTED): [ConciergeState.PROGRESSING],

   (ConciergeState.CLARIFYING_WORKER, TOPIC_HITL_RESOLVED): [ConciergeState.CLARIFYING_WORKER],

   # Timeout can fire in any state (async timer)
   (ConciergeState.CLARIFYING_WORKER, TOPIC_HITL_TIMED_OUT): [ConciergeState.CLARIFYING_WORKER],
   (ConciergeState.LISTENING, TOPIC_HITL_TIMED_OUT): [ConciergeState.LISTENING],
   (ConciergeState.COMPANIONING, TOPIC_HITL_TIMED_OUT): [ConciergeState.COMPANIONING],

   # RED block can happen during task execution
   (ConciergeState.COMPANIONING, TOPIC_HITL_BLOCKED_RED): [ConciergeState.COMPANIONING],
   (ConciergeState.PROGRESSING, TOPIC_HITL_BLOCKED_RED): [ConciergeState.PROGRESSING],
   ```

   The HITL events are observability passthroughs -- they do NOT trigger FSM state transitions. The guard table allows them in states where they can logically occur.

2. Create canonical event classes in `events/`:

   ```python
   @dataclass
   class HILRequestedEvent(CanonicalEventMeta):
       pending_hil_id: str
       hil_type: str           # clarification / approval / selection
       parent_task_id: str
       safety_band: str
       hil_deadline_ms: int
       resume_token: str
       device_id: str | None   # M5 device context

   @dataclass
   class HILResolvedEvent(CanonicalEventMeta):
       pending_hil_id: str
       hil_type: str
       parent_task_id: str
       decision_branch: str    # clarified / approved / approved_with_mods / cancelled / selected
       has_merged_params: bool  # True for approved_with_mods
       device_id: str | None

   @dataclass
   class HILTimedOutEvent(CanonicalEventMeta):
       pending_hil_id: str
       hil_type: str
       parent_task_id: str
       timeout_ms: int
       elapsed_ms: int

   @dataclass
   class HILBlockedRedEvent(CanonicalEventMeta):
       task_id: str
       capability_name: str
       safety_band: str
       reason: str
   ```

3. Register all 4 in M1's event registry so `_ledger_append()` records structured events.

4. Wire `_ledger_append()` at each emission point:
   - `hitl.requested.v1`: in `_on_task_suspended` after HILSubTask creation
   - `hitl.resolved.v1`: in `_on_task_resume` after HILSubTask.status set to RESOLVED
   - `hitl.timed_out.v1`: in timeout handler after HILSubTask.status set to TIMED_OUT
   - `hitl.blocked_red.v1`: in `on_blocked_red` callback

5. Add test: trigger each HITL lifecycle event, verify it passes guard_dispatch without dead-letter, and appears as structured event in ledger.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (FULL_GUARD_TABLE entries for 4 topics, _ledger_append at 4 emission points)
- `poc/k1_poc/bus/topics.py` (TOPIC_HITL_REQUESTED, TOPIC_HITL_RESOLVED, TOPIC_HITL_TIMED_OUT, TOPIC_HITL_BLOCKED_RED constants)
- `poc/k1_poc/bus/builders.py` (build_hitl_requested, build_hitl_resolved, build_hitl_timed_out, build_hitl_blocked_red)
- `poc/k1_poc/events/` (4 canonical event classes)
- `poc/k1_poc/events/registry.py` (register 4 HITL events)

**Files to create:**

- `tests/poc/test_m06_wiring_regression.py` (initial test)

**Dependency:** E6.3.1-E6.3.4 (HITL event emission), M2 2.1.1 (FULL_GUARD_TABLE), M1 1.4.2 (_ledger_append pattern), M1 1.4.4 (LedgerMiddleware)

**Acceptance:**

- All 4 HITL topics pass `_guard_dispatch()` without dead-letter
- Guard table allows each topic in its logically valid states
- Canonical event classes exist for all 4 HITL lifecycle events
- `_ledger_append()` records structured HITL events at each lifecycle boundary
- Ledger entries include pending_hil_id, hil_type, parent_task_id, decision_branch (for resolved), device_id
- Zero dead-letters from HITL topics under normal operation

---

#### 6.5.2 -- Wire back_resume_handler into M3 route_back_envelope and verify cancel token propagation

**Problem:** E6.2.1 wires back_resume_handler via topic-based routing in the Back mailbox consumer: `task.resume.v1` dispatches to `back_resume_handler`, everything else to `back_handler`. But M3's `route_back_envelope()` (3.1.1-3.1.3) is the canonical back dispatch path used by the FSM. Currently `route_back_envelope()` handles `task.dispatch.v1` and `task.cancel.v1`. It must also route `task.resume.v1` -- otherwise the FSM calls `_deliver_to_back()` for resume envelopes, but `route_back_envelope()` may not recognize the topic and drop it.

Additionally, M3's per-task `CancellationToken` (3.2.2) must be available to the resumed Back loop. If a HITL timeout fires while Back is mid-loop after resume, the timeout handler sets the cancel flag, and the between-iteration check (loop.py L250) must see it. This requires the resumed loop to use the SAME CancellationToken that was active before suspension.

**What to do:**

1. Extend `route_back_envelope()` to handle `task.resume.v1`:

   ```python
   def route_back_envelope(envelope, mailbox_router):
       topic = envelope.topic
       if topic in (TOPIC_TASK_DISPATCH, TOPIC_TASK_RESUME):
           # Both dispatch and resume go to Back mailbox
           mailbox_router.deliver_to_back(envelope)
       elif topic == TOPIC_TASK_CANCEL:
           mailbox_router.deliver_cancel_to_back(envelope)
       else:
           # Unknown back topic -> dead-letter (M3 3.7.1)
           ...
   ```

2. Verify that `_cancel_tokens[task_id]` survives suspension. When a task is suspended (status=SUSPENDED), the CancellationToken must NOT be cleaned up. On resume, the same token is checked by the resumed react_loop's `cancellation_check()`. On HITL timeout -> cancel, the timeout handler calls `cancel_handler.request_cancel(task_id)` which sets the token's flag.

3. Verify that `back_resume_handler` receives `fsm_state` for cancel checking. Currently `back_resume_handler(envelope, model, ss, bus, tool_dispatcher, fsm_state=None)` accepts fsm_state. The mailbox routing must pass fsm_state through (same as back_handler).

4. Verify that M3's `classify_tool_batch()` (3.4.2) applies correctly in the resumed loop. The resumed `react_loop()` call passes the same `tool_dispatcher` with classify_tool_batch wired -- no additional wiring needed, but verify via test.

5. Add test: suspend task -> resume -> verify back_resume_handler is invoked (not back_handler) -> verify CancellationToken is the same object -> verify timeout-during-resume sets cancel flag visible to next iteration.

**Files to modify:**

- `poc/k1_poc/actors/back.py` (verify fsm_state passed to back_resume_handler in mailbox routing)
- `poc/k1_poc/fsm/controller.py` (verify _cancel_tokens[task_id] preserved during suspension)
- M3's route_back_envelope location (add TOPIC_TASK_RESUME handling)

**Dependency:** E6.2.1 (back_resume_handler wiring), M3 3.1.1 (route_back_envelope), M3 3.2.2 (cancel tokens), E6.2.3 (mandatory cancellation callback)

**Acceptance:**

- `route_back_envelope()` correctly routes `task.resume.v1` to Back mailbox
- `back_resume_handler` is invoked (not `back_handler`) for resume envelopes
- `_cancel_tokens[task_id]` persists across suspension/resume cycle
- HITL timeout fires mid-resumed-loop -> cancel flag set -> Back exits between iterations
- `classify_tool_batch()` applies to resumed loop tool calls
- `fsm_state` is passed to back_resume_handler for cancel checking

---

#### 6.5.3 -- Wire HILSubTask as sole context source for M5 InflightContext and M3 SuspensionManager transition

**Problem:** E6.1.2 and E6.2.2 replace the dual-store pattern (SuspensionManager._contexts + FSMTurnState.pending_context) with unified HILSubTask storage. But M5's `build_inflight_context()` (5.5.2) reads suspended task information from `SuspensionManager.get_all_contexts()` to populate `InflightContext.pending_hil` flag. After M6, this must read from HILSubTask instead.

The transition is subtle: SuspensionManager still manages timeout watchers (asyncio.Task) and active suspension tracking (_active dict). But it no longer stores ReAct context (_contexts dict). The ownership split becomes:

- **SuspensionManager**: timeout lifecycle (start/cancel timeout watchers), active suspension bookkeeping, limit enforcement
- **HILSubTask (on TaskStateEntry)**: all context data (react_snapshot, hil_type, resume_token, status, deadlines)

M5's Arbiter reads InflightContext to decide whether to cancel/modify/defer. If InflightContext.pending_hil is wrong (stale from old SuspensionManager), the Arbiter may incorrectly cancel a task that has already been resumed, or incorrectly classify MODIFY_INFLIGHT for a suspended task.

**What to do:**

1. Update `build_inflight_context()` to read pending_hil from TaskStateEntry.pending_hil (via SS task_state section) instead of SuspensionManager._contexts:

   ```python
   def build_inflight_context(ss, suspension_manager, ...):
       task_state = ss.get_section("task_state")
       for task in active_tasks:
           entry = task_state.get_entry(task.task_id) if task_state else None
           task_info = InflightTask(
               task_id=task.task_id,
               pending_hil=(entry is not None and entry.has_pending_hil),
               hil_type=entry.pending_hil.get("hil_type") if entry and entry.pending_hil else None,
               ...
           )
   ```

2. Verify that SuspensionManager._contexts is no longer written to for HITL flows. After M6, `_on_task_suspended()` creates HILSubTask and stores it on TaskStateEntry -- it does NOT call `self._suspension_manager.store_context()`. The SuspensionManager.store_context() method may still exist for non-HITL suspension use cases (if any), but HITL flows bypass it.

3. Verify that `_on_task_resume()` reads context from HILSubTask (via TaskStateEntry.pending_hil deserialized via from_persistence()) instead of `self._suspension_manager.pop_context()`. The FSM's resume path must use `HILSubTask.react_snapshot` for building ResumeContext.

4. Verify that M5's `_handle_arbiter_cancel()` and `_handle_arbiter_modify()` correctly see pending_hil status via InflightContext after the ownership switch. Test: suspend task -> Arbiter classifies new input -> InflightContext shows pending_hil=True -> Arbiter uses it in decision.

5. Add test: create HILSubTask -> verify InflightContext.pending_hil=True from TaskStateEntry -> resume task -> verify InflightContext.pending_hil=False -> verify SuspensionManager._contexts is empty throughout.

**Files to modify:**

- `poc/k1_poc/fsm/arbiter.py` (build_inflight_context reads from TaskStateEntry)
- `poc/k1_poc/fsm/controller.py` (_on_task_suspended creates HILSubTask not store_context; _on_task_resume reads from HILSubTask)
- `poc/k1_poc/protocols/hitl_wiring.py` (build_resume_context accepts HILSubTask directly per 6.2.2)

**Dependency:** E6.1.2 (HILSubTask creation), E6.2.2 (unified context storage), M5 5.5.2 (InflightContext from SS), M3 3.3.1 (SuspensionManager as SOT -- now partially superseded)

**Acceptance:**

- `build_inflight_context()` reads pending_hil from TaskStateEntry.pending_hil (not SuspensionManager._contexts)
- SuspensionManager._contexts is NOT written to during HITL flows
- `_on_task_resume()` reads HILSubTask from TaskStateEntry for ResumeContext construction
- InflightContext.pending_hil is True when HILSubTask exists and PENDING
- InflightContext.pending_hil is False after resume clears TaskStateEntry.pending_hil
- M5 Arbiter decisions correctly reflect HITL suspension state

---

#### 6.5.4 -- Wire validate_before_invoke into tool dispatch with M4 writer_port exclusion

**Problem:** E6.1.3 wires `validate_before_invoke()` (hitl_coordinator.py L416) into the `invoke_capability` tool execution path to block side-effecting capabilities when a HITL is pending. But M4 introduced `writer_port` (DirectWriterAdapter) for cognitive tools (update_beliefs, update_clarifications, etc.). These cognitive tools go through `writer_port.request_mutation()` -- they do NOT call `invoke_capability`. The L2 check must NOT block cognitive tool writes.

The tool dispatch path has two branches after M4:

- **invoke_capability path**: `ToolDispatcher.dispatch("invoke_capability", args)` -> actual capability execution -> side effects possible -> needs L2 check
- **writer_port path**: `ToolDispatcher.dispatch("update_beliefs", args)` -> `writer_port.request_mutation(section, delta)` -> SS write only -> no side effects -> skip L2 check

If `validate_before_invoke()` is naively wired to ALL tool dispatch, it would block cognitive writes during HITL (the LLM in HITL_RESOLVE mode calls `update_beliefs` to persist the user's answer -- blocking it would break HITL resolution).

**What to do:**

1. Wire `validate_before_invoke()` ONLY for `invoke_capability` tool calls in `tools/implementations.py`:

   ```python
   async def _handle_invoke_capability(args, context):
       # L2 defense-in-depth check (M6 6.1.3)
       if context.hil_coordinator is not None:
           contract = _get_capability_contract(args)
           decision = context.hil_coordinator.validate_before_invoke(
               task_id=context.task_id,
               capability_contract=contract,
               task_history=context.task_history,
           )
           if decision == "block_red":
               return ToolResult(status="blocked", reason="RED safety band")
           if decision == "block_needs_approval":
               return ToolResult(status="blocked", reason="needs_approval")
       # Proceed with capability execution...
   ```

2. Verify that M4's cognitive tools (`update_beliefs`, `update_clarifications`, `update_artifacts`, `update_preferences`, `update_scoreboard`, `submit_result`) are NOT routed through `_handle_invoke_capability`. They have their own dispatch functions in tools/implementations.py.

3. Verify that `submit_result` with `needs_human=True` still works when an HITL is pending for a DIFFERENT task. The L2 check is per-task_id. If task A has pending HITL and task B calls invoke_capability, the check should use task B's task_id (and pass, since B has no pending HITL).

4. Add `hil_coordinator` to `ToolContext` (or equivalent context object passed to tool dispatch). This requires ensuring the HILCoordinator reference is available in the Back tool execution path. The coordinator lives on the FSM; the tool dispatcher needs a reference or callback.

5. Add test: HITL pending for task -> invoke_capability blocked -> update_beliefs NOT blocked -> resolve HITL -> invoke_capability now allowed.

**Files to modify:**

- `poc/k1_poc/tools/implementations.py` (L2 check in _handle_invoke_capability only)
- `poc/k1_poc/tools/dispatcher.py` (pass hil_coordinator reference to ToolContext)

**Dependency:** E6.1.3 (validate_before_invoke), M4 4.2.1 (writer_port), M4 4.2.3 (cognitive tools via writer_port)

**Acceptance:**

- `validate_before_invoke()` is called ONLY for `invoke_capability` tool dispatch
- M4 cognitive tools (`update_beliefs` et al.) are NEVER blocked by L2 check
- `invoke_capability` returns ToolResult(status="blocked") when HITL pending for same task
- Per-task isolation: HITL pending for task A does not block task B's invoke_capability
- Front HITL_RESOLVE's `update_beliefs` call works while HITL is pending (it's parsing the answer, not executing a capability)

---

#### 6.5.5 -- Wire scan_for_recovery to FSM startup with M4 SS binding ordering

**Problem:** E6.4.2 calls `scan_for_recovery()` at FSM startup to categorize SUSPENDED tasks as recoverable vs timed-out. But M4's SS binding (TaskBridge.rebind at 4.1.1) must happen BEFORE recovery scan, because `scan_for_recovery()` reads `task_state` from persisted Session State. If SS is not yet loaded/bound, the scan sees empty task_state and skips all recovery.

The startup ordering after M1+M2+M3+M4+M5 is:

1. `start_kernel()` creates bus, ledger, middleware
2. `ConciergeController.__init__()` creates FSM state, handlers, managers
3. M4 `TaskBridge.rebind()` connects to real SS sections
4. M4 `ControlExtension.bind_control_section()` mirrors FSM state
5. M5 `ConversationArbiter.__init__()` with config

M6 recovery must happen AFTER step 4 (SS fully bound) but BEFORE the FSM begins processing new events. This is the "first activation" hook.

**What to do:**

1. Add `_recover_hitl_on_startup()` method to `ConciergeController`:

   ```python
   async def _recover_hitl_on_startup(self):
       """M6: Recover pending HITL from persisted task_state.

       Called once after SS binding is complete, before processing events.
       Uses scan_for_recovery from hitl_persistence.py (already exists).
       """
       task_state_section = self._ss.get_section("task_state") if self._ss else None
       if task_state_section is None:
           return

       task_state_dict = task_state_section.to_dict()  # persisted entries
       report = scan_for_recovery(task_state_dict)

       # Auto-cancel expired suspensions (6.4.4)
       timeout_events = build_timeout_events(report, task_state_dict)
       for evt in timeout_events:
           self._bus.publish(build_hitl_timed_out(evt.to_payload()))
           self._ledger_append(HILTimedOutEvent(
               pending_hil_id=evt.task_id,
               hil_type=evt.hil_type,
               parent_task_id=evt.task_id,
               timeout_ms=evt.timeout_ms,
               elapsed_ms=evt.elapsed_ms,
           ))
           # Set TaskStateEntry to CANCELLED
           entry = TaskStateEntry.from_dict({"task_id": evt.task_id, **task_state_dict[evt.task_id]})
           entry.cancel(reason="hil_timeout_post_crash")

       # Re-present recoverable suspensions (6.4.3)
       for task_id in report.recovered_task_ids:
           entry_dict = task_state_dict[task_id]
           hil_sub = HILSubTask.from_persistence(entry_dict["pending_hil"])
           # Adjust deadline for elapsed time during crash
           # Re-invoke Front HITL_RELAY...
   ```

2. Ensure this method is called AFTER `TaskBridge.rebind()` and `ControlExtension.bind_control_section()` have executed. The call site is in `start_kernel()` or the FSM's first-event hook.

3. Verify M1 ledger records recovery actions. Each auto-cancel emits `HILTimedOutEvent` to ledger. Each re-presentation emits `HILRequestedEvent` (re-request with adjusted deadline).

4. Verify M2 guard table: recovery-emitted events (`hitl.timed_out.v1` during startup) must pass guard_dispatch. The FSM state during startup is LISTENING (or INITIALIZING). Add guard table entry for LISTENING + HITL_TIMED_OUT if not already covered by 6.5.1.

5. Add test: persist 2 SUSPENDED tasks (one expired, one recoverable) -> restart FSM -> verify expired task auto-cancelled with ledger entry -> verify recoverable task re-presented via Front HITL_RELAY -> verify SS binding was live during recovery scan.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (_recover_hitl_on_startup, startup sequencing after SS bind)
- `poc/k1_poc/kernel/bootstrap.py` (call recovery after SS binding in start_kernel)

**Dependency:** E6.4.2-E6.4.4 (recovery logic), M4 4.1.1 (TaskBridge.rebind ordering), M1 1.4.2 (ledger recording), 6.5.1 (guard table entries for HITL topics)

**Acceptance:**

- `_recover_hitl_on_startup()` called AFTER TaskBridge.rebind() and ControlExtension.bind()
- `scan_for_recovery()` sees live SS task_state data (not empty)
- Expired tasks: auto-cancelled with `HILTimedOutEvent` in ledger and on bus
- Recoverable tasks: re-presented via Front HITL_RELAY with adjusted deadline
- Recovery events pass M2 guard_dispatch without dead-letter
- M4 SS binding verified live before recovery scan via assertion

---

#### 6.5.6 -- Wire resume_token flow through M3 parse_envelope_payload and M5 envelope enrichment

**Problem:** E6.1.4 introduces `resume_token` (UUID4) generated at HILSubTask creation time. The token flows: FSM creates it -> includes in `TaskSuspendedEvent` payload -> Front echoes it in `TaskResumeEvent` -> FSM validates match in `_on_task_resume()`. But this flow passes through M3's `parse_envelope_payload()` and M5's `_enrich_envelope_with_arbiter()`. Both must preserve resume_token without stripping or overwriting it.

The token flow traverses 4 system boundaries:

1. FSM -> Bus: `build_task_suspended(payload={..., "resume_token": token})` (M1 builder)
2. Bus -> Front: `parse_envelope_payload()` extracts payload dict (M3 shared utility)
3. Front -> Bus: Front HITL_RESOLVE emits resume event with `resume_token` echoed
4. Bus -> FSM: `_on_task_resume()` validates `payload.resume_token == HILSubTask.resume_token`

If M5's `_enrich_envelope_with_arbiter()` builds a new Envelope with modified payload (dropping resume_token), or if M3's `parse_envelope_payload()` has a field allowlist that excludes resume_token, the validation fails and no resume ever succeeds.

**What to do:**

1. Verify that `build_task_suspended()` (bus/builders.py) includes `resume_token` in its payload without stripping unknown fields. Current builder pattern: accepts `payload` dict and wraps it in Envelope. Verify no field filtering occurs.

2. Verify that M3's `parse_envelope_payload()` returns the full payload dict. Current implementation: `json.loads(envelope.payload)` -> returns raw dict. No field filtering. But verify no intermediate layer adds field validation.

3. Verify that M5's `_enrich_envelope_with_arbiter()` (5.5.5) does NOT overwrite the entire payload. It creates a new dict with added keys (`arbiter_decision`, `routing_metadata`). The pattern is `enriched = dict(payload); enriched["arbiter_decision"] = ...; enriched["routing_metadata"] = ...`. This preserves all existing keys including `resume_token`.

4. Verify that Front HITL_RESOLVE's output includes `resume_token` in the resume event payload. The FSM extracts the user's structured resolution from Front's output and builds the resume event. The `resume_token` must be copied from the original suspended event (stored in HILSubTask) into the resume event.

5. Wire `resume_token` validation in `_on_task_resume()`:

   ```python
   def _on_task_resume(self, envelope):
       payload = _parse_payload(envelope)
       task_id = payload.get("task_id", "")
       token = payload.get("resume_token")

       # Read HILSubTask from TaskStateEntry
       entry = self._get_task_entry(task_id)
       if entry and entry.pending_hil:
           expected_token = entry.pending_hil.get("resume_token")
           if token != expected_token:
               logger.warning(
                   "FSM._on_task_resume: resume_token mismatch task_id=%s "
                   "expected=%s got=%s -- rejecting stale resume",
                   task_id, expected_token, token,
               )
               return  # Reject -- no Back dispatch
       # Proceed with resume...
   ```

6. Add M5 device_id + resume_token combined validation: if both are present, the resume must come from a device with equal or higher precedence (M5 5.4.2 rules). This prevents a lower-priority device from resuming a task that was suspended by a higher-priority device.

7. Add test: create HILSubTask with resume_token -> deliver stale resume (wrong token) -> verify rejection (no Back dispatch) -> deliver correct resume -> verify Back dispatched.

**Files to verify:**

- `poc/k1_poc/bus/builders.py` (build_task_suspended preserves resume_token)
- `poc/k1_poc/actors/shared.py` (parse_envelope_payload returns full dict)
- `poc/k1_poc/fsm/controller.py` (_enrich_envelope_with_arbiter preserves resume_token;_on_task_resume validates resume_token)

**Dependency:** E6.1.4 (resume_token), M3 3.5.1 (parse_envelope_payload), M5 5.5.5 (envelope enrichment), M5 5.4.2 (device precedence)

**Acceptance:**

- `build_task_suspended()` includes resume_token in payload without stripping
- `parse_envelope_payload()` returns resume_token in parsed dict
- `_enrich_envelope_with_arbiter()` preserves resume_token in enriched payload
- Stale resume (wrong token) is rejected with warning log, no Back dispatch
- Correct resume (matching token) proceeds to Back dispatch
- Device precedence checked alongside resume_token on resume

---

#### 6.5.7 -- Extend test fixtures for HITL wiring: create_wired_fsm(with_hitl=True)

**Problem:** E6.1-E6.4 add HILSubTask, 4 new bus topics, resume_token validation, validate_before_invoke wiring, scan_for_recovery at startup, and unified context storage. Tests for all wiring issues (6.5.1-6.5.6, 6.5.8-6.5.9) need FSM instances with full HITL wiring active. The current fixture `create_wired_fsm()` supports: `with_ledger`, `with_dead_letter_consumer`, `with_cancel_tokens`, `with_ss_binding`, `with_writer_port`, `with_arbiter`. It needs `with_hitl` for M6.

**What to do:**

1. Extend `create_wired_fsm()` in `testing/fixtures.py`:

   ```python
   def create_wired_fsm(
       ...,
       with_hitl: bool = False,
   ) -> ConciergeController:
       ...
       if with_hitl:
           # Create HILCoordinator with test config
           hil_config = HILCoordinatorConfig(
               max_rounds=2,
               timeouts={"clarification": 5000, "approval": 10000, "selection": 7500},
               block_red=True,
               auto_escalate_side_effects=True,
           )
           hil_coordinator = HILCoordinator(config=hil_config, ...)
           controller.set_hil_coordinator(hil_coordinator)

           # Register HITL event topics in guard table
           # Wire validate_before_invoke to tool dispatcher
           # Wire scan_for_recovery to startup hook

           # Enable validate_hitl_wiring() call at startup
           issues = validate_hitl_wiring()
           assert not issues, f"HITL wiring issues: {issues}"
       ...
   ```

2. Add helper factories:

   ```python
   def create_test_hil_subtask(
       task_id: str = "test-task-1",
       hil_type: str = "clarification",
       status: str = "PENDING",
       resume_token: str | None = None,
       react_snapshot: dict | None = None,
   ) -> HILSubTask: ...

   def create_test_task_state_entry(
       task_id: str = "test-task-1",
       status: str = "SUSPENDED",
       pending_hil: dict | None = None,
   ) -> TaskStateEntry: ...
   ```

3. Add assertion helpers:

   ```python
   def assert_hitl_lifecycle_in_ledger(ledger, task_id, expected_events):
       """Verify HITL lifecycle events appear in ledger in order."""
       ...

   def assert_no_hitl_dead_letters(dead_letter_consumer):
       """Verify no HITL topics in dead-letter queue."""
       ...

   def assert_resume_token_valid(controller, task_id, token):
       """Verify resume_token matches HILSubTask."""
       ...
   ```

4. Call `validate_hitl_wiring()` at FSM startup in fixture. This cross-layer check (hitl_wiring.py L319-435) validates 14 invariants: HITL_RELAY has 0 tools, HITL_RESOLVE has {update_beliefs}, both have correct iterations, sections, SS reads, anti-patterns, and examples. Any misconfiguration caught at test time.

5. Update `conftest.py` fixtures to include HITL by default when relevant.

**Files to modify:**

- `poc/k1_poc/testing/fixtures.py` (extend create_wired_fsm, add create_test_hil_subtask, create_test_task_state_entry, assertion helpers)
- `tests/poc/conftest.py` (update fixtures for M6 defaults)

**Dependency:** E6.1.1 (HILSubTask), E6.3.1-E6.3.4 (HITL events), E6.1.3 (validate_before_invoke), E6.4.2 (scan_for_recovery), M1-M5 fixture patterns (1.4.7, 2.5.6, 3.7.6, 4.5.7, 5.5.7)

**Acceptance:**

- `create_wired_fsm(with_hitl=True)` returns FSM with HILCoordinator, HITL guard table entries, and validate_before_invoke wired
- `validate_hitl_wiring()` passes at startup (0 issues)
- `create_test_hil_subtask()` creates HILSubTask with configurable fields
- `create_test_task_state_entry()` creates TaskStateEntry with optional pending_hil
- `assert_hitl_lifecycle_in_ledger()` and `assert_no_hitl_dead_letters()` available for tests
- All M6 E6.5.1-E6.5.6 tests use these fixtures

---

#### 6.5.8 -- Backward compatibility: verify M1 ledger + M2 guard table + M3 back routing + M4 SS binding + M5 Arbiter survive M6 refactoring

**Problem:** M6 restructures the HITL path fundamentally: new state model (HILSubTask), new context ownership (SuspensionManager._contexts deprecated for HITL), new bus events (4 topics), new tool dispatch guard (validate_before_invoke), and new startup sequence (scan_for_recovery). Every prior milestone's wiring runs through HITL-adjacent code paths.

| M6 Change | M1/M2/M3/M4/M5 Code Path At Risk |
|-----------|----------------------------------------------|
| HILSubTask replaces dual-store | M3 SuspensionManager._contexts reads (now empty for HITL); M5 build_inflight_context reads |
| 4 new bus topics | M2 guard table -- must have entries; M2 dead-letter -- must not reject; M1 ledger -- must record |
| back_resume_handler topic routing | M3 route_back_envelope -- must route task.resume.v1; M3 cancel tokens -- must persist across suspension |
| validate_before_invoke in tool dispatch | M4 cognitive tools via writer_port -- must NOT be blocked; M4 LLM-writable allowlist -- orthogonal check |
| resume_token validation | M3 parse_envelope_payload -- must preserve; M5 envelope enrichment -- must preserve |
| scan_for_recovery at startup | M4 TaskBridge.rebind ordering -- must complete first; M1 ledger -- recovery actions ledgered |
| Consolidated suspension limits | M5 InflightContext.pending_hil -- must reflect accurate count |
| Mandatory cancellation callback | M3 between-iteration check -- must propagate to resumed loops |

**What to do:**

1. Create `tests/poc/test_m06_wiring_regression.py`:

   **Test matrix:**

   | Test | Trigger | Expected M1-M5 Artifact | M6 Change That Could Break It |
   |------|---------|------------------------|-------------------------------|
   | `test_hitl_topics_pass_guard_table` | Emit all 4 HITL topics | No dead-letters; events pass guard_dispatch | 6.5.1 (new topics) |
   | `test_hitl_events_in_ledger` | Full HITL cycle (request -> resolve) | HILRequestedEvent + HILResolvedEvent in ledger in order | 6.5.1 (ledger recording) |
   | `test_resume_routed_via_route_back_envelope` | task.resume.v1 | back_resume_handler invoked (not back_handler) | 6.5.2 (route_back_envelope) |
   | `test_cancel_token_survives_suspension` | Suspend -> resume -> timeout cancel | CancellationToken same object; cancel flag visible | 6.5.2 (cancel persistence) |
   | `test_inflight_context_reads_hil_subtask` | Suspend task -> build InflightContext | pending_hil=True from TaskStateEntry (not SuspensionManager) | 6.5.3 (context source switch) |
   | `test_validate_invoke_blocks_side_effects` | invoke_capability with HITL pending | ToolResult(status="blocked") | 6.5.4 (L2 check wired) |
   | `test_cognitive_tools_not_blocked_during_hitl` | update_beliefs during HITL_RESOLVE | Tool executes normally (not blocked) | 6.5.4 (writer_port exclusion) |
   | `test_recovery_after_ss_binding` | Persist SUSPENDED task -> restart FSM | scan_for_recovery sees live task_state | 6.5.5 (startup ordering) |
   | `test_resume_token_validation` | Stale resume_token -> correct resume_token | Stale rejected; correct proceeds | 6.5.6 (token validation) |
   | `test_m5_arbiter_with_hitl_subtask` | Suspend task -> user input -> Arbiter | InflightContext.pending_hil=True informs Arbiter decision | 6.5.3 + M5 interaction |
   | `test_m4_writer_port_unaffected_by_l2` | Cognitive tool write after M6 wiring | writer_port.request_mutation() succeeds | 6.5.4 + M4 regression |
   | `test_m3_back_routing_handles_resume` | Resume envelope via route_back_envelope | back_resume_handler dispatched; classify_tool_batch applies | 6.5.2 + M3 regression |

2. Each test uses `create_wired_fsm(with_hitl=True, with_arbiter=True, with_ss_binding=True, with_writer_port=True)` from updated fixtures (6.5.7).

**Files to create:**

- `tests/poc/test_m06_wiring_regression.py`

**Dependency:** 6.5.1-6.5.7 (all wiring issues), M1-M5 regression test patterns

**Acceptance:**

- All 12 regression tests pass
- M5 `test_m05_wiring_regression.py` tests still pass after M6 changes
- M4 `test_m04_wiring_regression.py` tests still pass after M6 changes
- HITL lifecycle events flow through guard table without dead-letters
- Cognitive tools unblocked, invoke_capability blocked when HITL pending
- InflightContext correctly reflects HILSubTask state (not stale SuspensionManager)

---

#### 6.5.9 -- Full regression: demo smoke test with HITL as first-class sub-task

**Problem:** M6 elevates HITL from scattered in-memory state to a formally modeled blocking sub-task with persisted lifecycle. The demo web app must exercise the complete HITL lifecycle including suspension, resume, timeout, crash recovery, and L2 blocking.

**What to do:**

1. Create `tests/poc/test_m06_demo_smoke.py`:

   **Scenario A: Normal HITL cycle -- clarification**
   - Boot kernel with full HITL wiring
   - Dispatch task "find restaurants in Napa"
   - Back calls submit_result(needs_human) with question about cuisine preference
   - Verify: HILSubTask created with status=PENDING, resume_token generated
   - Verify: hitl.requested.v1 emitted on bus AND recorded in ledger
   - Verify: Front HITL_RELAY invoked (0 tools, 1 iteration)
   - User answers "Italian"
   - Verify: Front HITL_RESOLVE invoked (update_beliefs tool, 3 iterations)
   - Verify: hitl.resolved.v1 emitted with decision_branch="clarified"
   - Verify: back_resume_handler invoked (NOT back_handler)
   - Verify: Back LLM sees prior_messages + resume_instruction + resolution
   - Verify: remaining_budget = max(2, total - last_iteration)
   - Verify: Back completes with results
   - Verify: Ledger shows: HILRequested -> HILResolved -> TaskComplete in order

   **Scenario B: HITL approval with modifications**
   - Boot kernel, dispatch task that requires approval
   - Back calls submit_result(needs_human, hil_type="approval") with side_effects
   - Verify: safety_band escalated GREEN -> AMBER (auto_escalate_side_effects)
   - Verify: HILSubTask.hil_type="approval"
   - User says "approve but use the Amex card"
   - Verify: apply_approval_modifications() merges params
   - Verify: hitl.resolved.v1 has decision_branch="approved_with_mods"
   - Verify: Back resume receives merged_params in ResumeContext
   - Verify: Back LLM's prior_messages contain RESUME_INSTRUCTIONS["approval"]

   **Scenario C: HITL timeout auto-cancel**
   - Boot kernel, dispatch task, trigger HITL
   - Do NOT answer within timeout
   - Verify: hitl.timed_out.v1 emitted on bus
   - Verify: HILSubTask.status=TIMED_OUT
   - Verify: TaskStateEntry.status=CANCELLED with reason="hil_timeout"
   - Verify: Back LLM is NEVER resumed for this task
   - Verify: Front notified of cancellation
   - Verify: Ledger shows: HILRequested -> HILTimedOut -> TaskCancelled in order

   **Scenario D: L2 side-effect blocking during HITL**
   - Boot kernel, dispatch task, trigger HITL (pending)
   - Attempt invoke_capability for same task (should not happen normally, but defense-in-depth)
   - Verify: validate_before_invoke returns "block_needs_approval"
   - Verify: ToolResult(status="blocked") returned to LLM
   - Verify: Cognitive tools (update_beliefs) NOT blocked

   **Scenario E: Crash recovery**
   - Boot kernel, dispatch task, trigger HITL, persist task_state with SUSPENDED + pending_hil
   - Simulate crash (stop kernel)
   - Restart kernel
   - Verify: scan_for_recovery finds SUSPENDED task
   - If within timeout: task re-presented to user via HITL_RELAY with adjusted deadline
   - If past timeout: task auto-cancelled with HILTimedOutEvent

   **Scenario F: Demo health check with HITL**
   - Boot kernel
   - Verify: health check reports `hitl_wired=True`, `validate_hitl_wiring_issues=0`
   - Verify: `/api/session/hitl` (new endpoint) returns pending HIL count and active sub-tasks
   - Verify: All M1-M5 health checks still pass

**Files to create:**

- `tests/poc/test_m06_demo_smoke.py`

**Dependency:** 6.5.1-6.5.8 (all wiring and regression), M5 5.5.9 (demo smoke pattern)

**Acceptance:**

- All 6 scenarios pass
- Full HITL lifecycle exercised: request -> resolve -> resume -> complete
- Approval modifications flow correctly to Back LLM via merged_params
- Timeout auto-cancel produces correct event trace in ledger
- L2 blocking works for invoke_capability, cognitive tools exempt
- Crash recovery re-presents or auto-cancels correctly
- All previous demo smoke tests (M2, M3, M4, M5) still pass

---

### M6 Touchpoint Matrix: What M7-M12 Inherit from M6

| Milestone | M6 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M7** (BackPool) | `HILSubTask` with `parent_task_id` | Pool manager tracks which Back worker owns a suspended task. When resume arrives, pool routes to same worker slot (or new slot if worker recycled). HILSubTask.parent_task_id identifies the pool task mapping. |
| **M7** (BackPool) | `back_resume_handler` topic routing | Pool's mailbox consumer uses same topic-based routing: task.resume.v1 -> back_resume_handler with correct worker context. Pool must pass the worker's fsm_state for cancel checking. |
| **M7** (BackPool) | `validate_before_invoke()` L2 check | Pool workers share one HILCoordinator. L2 check uses per-task_id isolation -- worker A's HITL does not block worker B's invoke_capability. Pool must pass correct task_id context to L2 check. |
| **M8** (Weave Policy) | `hitl.requested.v1` / `hitl.resolved.v1` events | Weave suppression during HITL: when hitl.requested fires, weave queue pauses for that session. When hitl.resolved fires, weave queue resumes. Prevents weave notifications interrupting HITL question flow. |
| **M8** (Weave Policy) | `HILSubTask.status` | Weave scheduler checks HILSubTask.status before scheduling proactive content. PENDING -> suppress weave. RESOLVED/TIMED_OUT -> allow weave. |
| **M9** (Crash Recovery) | `scan_for_recovery()` + `build_timeout_events()` | M9's full crash recovery protocol wraps M6's HITL-specific recovery into a comprehensive recovery sequence covering tasks, weaves, and session state. M6's scan_for_recovery becomes one step in M9's multi-phase recovery. |
| **M9** (Crash Recovery) | `HILSubTask.to_persistence()` / `from_persistence()` | M9 ensures TaskStateEntry survives across backend restarts. HILSubTask serialization is the foundation -- M9 adds WAL (write-ahead log) and checkpoint semantics around it. |
| **M9** (Crash Recovery) | `resume_token` validation | M9's recovery replays events from WAL. Duplicate task.resume.v1 events are rejected by resume_token validation (token already consumed). Prevents double-resume after crash recovery. |
| **M10** (UltraBERT) | `RESUME_INSTRUCTIONS` per hil_type | UltraBERT-enhanced Back LLM follows the same resume instructions. Better model = better adherence to "do NOT re-execute tools." Resume instruction text may be tuned for UltraBERT's instruction-following capabilities. |
| **M10** (UltraBERT) | `remaining_budget` computation | UltraBERT is more token-efficient. remaining_budget min floor (2) stays, but the model uses fewer iterations to achieve same result. Budget calculation unchanged; model efficiency improves utilization. |
| **M11** (Observability) | `hitl.requested.v1` / `hitl.resolved.v1` / `hitl.timed_out.v1` / `hitl.blocked_red.v1` events | Full HITL metrics dashboard: request rate, resolution latency (requested -> resolved), timeout rate, RED block rate. Decision branch distribution. Alerts on high timeout rate or repeated RED blocks. |
| **M11** (Observability) | `HILSubTask` lifecycle durations | Metric: time-to-resolve per hil_type. SLA tracking: what percentage of HITLs resolve within half the timeout window? Histogram of user response latency by hil_type. |
| **M11** (Observability) | `validate_before_invoke` L2 decisions | Metric: L2 block rate. How often does the Back LLM attempt side-effecting tools during HITL? High rate suggests prompt instruction gap. Alert on repeated block_red events. |
| **M12** (Chaos Tests) | `HILSubTask` state model under rapid transitions | Rapid HITL: suspend -> resolve -> suspend -> resolve in tight loop. Verify HILSubTask status transitions are atomic and correct. Verify resume_token changes on each suspension. Verify hil_suspensions_count correctly increments and limits enforce. |
| **M12** (Chaos Tests) | `scan_for_recovery()` under partial crash | Crash mid-HITL: task SUSPENDED, pending_hil partially written. Verify scan_for_recovery handles corrupt/partial pending_hil gracefully (skip with warning, not crash). |
| **M12** (Chaos Tests) | `validate_before_invoke()` under concurrent requests | Multiple concurrent invoke_capability calls for same task with HITL pending. Verify L2 check is thread-safe (or event-loop-safe) and consistently blocks all concurrent calls. |

**Total: 18 issues across 4 epics (E6.1-E6.4) + 9 issues in E6.5 wiring = 27 issues across 5 epics.**

---

## M7: BackPool + Task Lease Model

**Goal:** Replace the single Back worker bottleneck with a parallel BackPool
where each task gets an isolated worker, an exclusive lease, and a
CancellationToken bound to that lease. Enforce dependency ordering between
tasks that share a session/topic so the LLM cannot see stale tool outputs
from a predecessor that has not yet completed. Wire the Back mailbox consumer
to dispatch by topic (dispatch / resume / cancel) so the correct handler
always receives the envelope.

**Gate:** BackPool serves N concurrent tasks (configurable pool_size, default
3). Each dispatched task is assigned a TaskLease with worker_id,
lease_expires_at, and CancellationToken. Lease expiry auto-cancels abandoned
tasks. CancellationToken is propagated to react_loop (not optional). Tasks
with depends_on are held in a ready-queue until the predecessor completes.
Topic-based Back mailbox routing dispatches resume/cancel to the correct
specialized handler. Coordinator consumer no longer hardcodes back_handler for
all envelopes.

**LLM Interaction Model (from code audit):**

| Actor | Current Behavior | Problem | BackPool Behavior |
|-------|-----------------|---------|-------------------|
| Back (task 1) | Single asyncio.create_task in coordinator consumer | Task 2 waits in mailbox until task 1's react_loop finishes. Head-of-line blocking. | Task 1 and task 2 each get their own worker with independent react_loop. Both run concurrently. |
| Back (task 2, depends_on task 1) | FSM dispatches task 2 to Back immediately. No ordering. Back starts task 2 while task 1 is still running. | Task 2's LLM may call discover_capabilities for a resource that task 1 has not yet created/modified. Stale tool results. | BackPool holds task 2 in ready-queue. Task 2 dispatched to worker only after task 1 emits task.complete. |
| Back (resume) | Coordinator consumer always calls back_handler (generic). back_resume_handler is never invoked. (Fixed in M6 6.2.1 at protocol level; M7 wires it in the consumer.) | Resume goes through generic path with zero history. | Consumer topic router dispatches task.resume.v1 to back_resume_handler with full ResumeContext. |
| Back (cancel) | back_cancel_handler exists but coordinator consumer never calls it. Cancellation callback is not passed to back_handler. | Cancel flag never reaches running react_loop. Cooperative cancellation is dead code. | Consumer topic router dispatches task.cancel.v1 to back_cancel_handler. Cancellation token from TaskLease is passed to react_loop. |

**Critical invariant:** Each worker's react_loop runs in its own asyncio.Task
with its own SS snapshot (read once at task start, back.py L394-400). Workers
do NOT share mutable state. SS is the read-only context for each worker. The
FSM + TaskBridge remain the single writer for task_state and task_artifacts.
Worker isolation means two Back LLMs running concurrently cannot corrupt each
other's tool outputs or message histories.

---

### E7.1 -- BackPool Worker Management

Source: WB 3.C, 8.4

**Rationale:** The current Back execution model is a single asyncio.Task
created per envelope in the coordinator consumer (_run_back_handler, tracked
in_pending_back_tasks list). This creates head-of-line blocking: if task 1
takes 30 seconds of LLM inference, task 2 sits in the back_mailbox until
task 1 finishes (the consumer does poll and create tasks, but all tasks share
the single back_handler call path with no isolation). BackPool formalizes the
worker concept: each worker is an isolated execution context with its own
asyncio.Task, its own SS snapshot, and its own CancellationToken.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 7.1.1 | Define BackPoolConfig dataclass with fields: pool_size (int, default 3), max_concurrent_per_session (int, default 2), lease_ttl_s (float, default 300.0), reclaim_check_interval_s (float, default 30.0), enable_dependency_ordering (bool, default True). Place in a new config section under actors.back_pool. pool_size bounds the maximum number of concurrent react_loops. max_concurrent_per_session prevents one chatty session from monopolizing all workers. | WB 3.C | pool_size directly determines how many Back LLMs can think simultaneously. Too small = head-of-line blocking returns. Too large = concurrent SS reads create stale-data window (each worker reads SS once at start; if worker A changes beliefs via tool call, worker B does not see it until its own loop completes). Default 3 balances parallelism with SS consistency. |
| 7.1.2 | Implement BackPool class with worker lifecycle: acquire_worker(task_id) -> WorkerSlot, release_worker(task_id), get_active_workers() -> list[WorkerSlot]. WorkerSlot contains: task_id, worker_id (uuid4), asyncio.Task reference, created_at, lease. acquire_worker checks pool_size and max_concurrent_per_session limits. If pool is full, raise BackPoolExhausted (caller must queue). release_worker cleans up the slot and makes it available. Place in actors/back_pool.py. | WB 3.C | When pool is exhausted, the task waits in the ready-queue instead of being silently dropped or blocking the consumer loop. The LLM for that task does not start until a worker slot opens -- no partial execution, no wasted tokens. |
| 7.1.3 | Integrate BackPool into coordinator consumer (_run_back_handler). Replace the current pattern of `asyncio.create_task(self._run_back_handler(env, back_handler))` with: (a) acquire_worker(task_id); (b) create asyncio.Task with the acquired worker slot; (c) on task completion callback, release_worker(task_id). If acquire_worker raises BackPoolExhausted, push the envelope into a local overflow queue and retry on next poll cycle or when a worker is released. Remove _pending_back_tasks list tracking (replaced by BackPool.get_active_workers). | WB 3.C | This is the wiring issue. Without it, BackPool is unused. With it, each Back LLM task gets an isolated execution slot, and the consumer loop remains free for front_mailbox polling regardless of how many Back tasks are running. |
| 7.1.4 | Add pool-level observability: emit backpool.worker.acquired and backpool.worker.released events with payload (task_id, worker_id, pool_utilization = active/pool_size). Add a gauge metric for current pool utilization. Log warning when pool_utilization > 0.8 (approaching capacity). These events are observability-only (not consumed by FSM or actors). | WB 8.4 | No direct LLM impact. Enables operators to detect pool saturation before tasks start queuing. Pool utilization metric feeds into adaptive weave policy (M8) -- if pool is saturated, weave should batch more aggressively to reduce the number of concurrent tasks. |

---

### E7.2 -- Task Lease Model

Source: WB 3.C, 10

**Rationale:** The current model has no concept of task ownership or expiry.
Once back_handler starts, the only termination path is react_loop completion
(success, failure, budget exhaustion, or cancellation check). If the
asyncio.Task hangs (LLM API timeout, deadlocked tool, etc.), the task
remains "active" in _active_task_ids forever -- no reclamation, no timeout,
no cleanup. The V2 design doc explicitly deferred BackPool to production
(Decision #2), but the interface was designed for zero-change swap. The lease
model provides the missing ownership and temporal bounds.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 7.2.1 | Define TaskLease dataclass with fields: task_id, worker_id, lease_id (uuid4), granted_at_ns (monotonic), expires_at_ns (granted_at + lease_ttl_s * 1e9), cancellation_token (CancellationToken), renewed_count (int, starts at 0), status enum (ACTIVE / EXPIRED / RELEASED / CANCELLED). Implement is_expired property, renew(extension_ns) method, and to_payload() for the task.leased.v1 event (schema already defined in M1). Place in protocols/task_lease.py. | WB 3.C | The lease's cancellation_token is what gets passed to react_loop. When the lease expires, the token is cancelled (cooperative), and the Back LLM's loop exits between iterations (same mechanism as M5 H2 / M6 H1). No mid-generation kill. |
| 7.2.2 | Create TaskLease at task dispatch time inside BackPool.acquire_worker(). Bind the CancellationToken from the lease to the worker slot. Pass the lease's CancellationToken to back_handler / back_resume_handler via the fsm_state or as an explicit parameter. This replaces the current_build_cancellation_check(fsm_state) pattern in back.py which builds a weak check from an optional fsm_state that is often None. The lease token is ALWAYS present (not optional). | WB 3.C | **Highest LLM impact in M7.** Currently back_handler's cancellation_check is built from fsm_state which the coordinator consumer does NOT pass (see_run_back_handler L881-912 -- no fsm_state arg). So cancellation_check = _never_cancel. The Back LLM's react_loop NEVER checks for cancellation. With lease-bound token, every Back react_loop has a mandatory cancellation path. |
| 7.2.3 | Implement lease expiry watcher: a background asyncio.Task that periodically (reclaim_check_interval_s) scans active leases. For each expired lease: (a) cancel the CancellationToken (triggers cooperative react_loop exit); (b) wait a grace period (5s) for the loop to complete; (c) if still running, cancel the asyncio.Task directly (hard kill); (d) release the worker slot; (e) emit task.failed with reason="lease_expired" on the bus. This handles the case where a Back LLM hangs indefinitely (LLM API timeout, tool deadlock). | WB 10 | Lease expiry is the last-resort safety net. The Back LLM's react_loop gets a cooperative cancel first (between iterations). If it does not exit within grace period, the asyncio.Task is hard-cancelled (the LLM's current generation is interrupted). This prevents zombie workers from permanently consuming pool slots. Without it, a single hung task eventually fills the pool and blocks all subsequent Back dispatches. |
| 7.2.4 | Emit task.leased.v1 event when BackPool.acquire_worker() creates a TaskLease. Use the TaskLeased schema defined in M1 (task_id, worker_id, lease_expires_at). Emit on bus after lease is granted but before the worker's asyncio.Task starts. This event is the authoritative record that a specific worker owns a specific task. | WB 3.C | Observability event. Enables correlation between task_id and worker_id in logs and traces. When debugging "why did task X take 45s?", the leased event pinpoints which worker ran it and when the lease was granted. |
| 7.2.5 | Support lease renewal for long-running tasks. Add renew_lease(task_id, extension_s) to BackPool. The Back react_loop calls this between iterations if it detects it needs more time (e.g., tool returned a large result set that needs multiple iterations to process). Default extension = 60s. Max renewals = 3 (configurable). If max renewals exceeded, the lease expires normally. Log each renewal with task_id, worker_id, renewed_count, new_expires_at. | WB 10 | Prevents premature lease expiry for legitimate long-running tasks. Without renewal, a 300s lease_ttl means tasks that genuinely need 6+ minutes of LLM time get killed. With renewal, the Back LLM can request more time up to a hard ceiling (300 + 3*60 = 480s). Beyond that, the task is considered runaway. |

---

### E7.3 -- Back Mailbox Topic Router

Source: WB 14.4A, 15.5 P0-1

**Rationale:** The coordinator consumer (coordinator.py L757-800) receives ALL
Back mailbox envelopes and dispatches them identically to back_handler. There
is no topic-based routing. Three specialized handlers exist -- back_handler
(dispatch), back_resume_handler (resume), back_cancel_handler (cancel) -- but
only back_handler is ever called. subscribe_back_events (back.py L745-788)
already wires 4 topics (task.dispatch, task.cancel, task.resume,
clarification.response) to a single handler_fn. M6 E6.2.1 addresses this at
the protocol level; M7 wires it in the actual coordinator consumer.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 7.3.1 | Implement BackTopicRouter class with method route(envelope) -> handler_fn. Routing table: task.dispatch.v1 -> back_handler, task.resume.v1 -> back_resume_handler, task.cancel.v1 -> back_cancel_handler, clarification.response.v1 -> back_resume_handler (same as resume -- clarification is a HITL resolve). Default for unknown topics: log warning + discard. Place in actors/back_router.py. | WB 14.4A | Ensures the Back LLM receives the correct handler for each event type. Without this, resume events go through generic back_handler which starts a brand-new react_loop with zero history (the LLM re-discovers capabilities, ignores user's HITL answer). With this, resume events hit back_resume_handler which replays prior_messages + resolution. |
| 7.3.2 | Integrate BackTopicRouter into coordinator consumer. Replace the hardcoded `self._run_back_handler(env, back_handler)` call with: (a) router = BackTopicRouter(); (b) handler_fn = router.route(env); (c) if handler_fn is back_cancel_handler, call synchronously (no worker needed -- it only sets a flag); (d) else acquire_worker + asyncio.create_task with the routed handler_fn. This ensures cancel never consumes a pool slot and is applied immediately. | WB 14.4A | **Second highest LLM impact in M7.** The cancel handler sets fsm_state.cancellation_requested = True and records the task_id. This must happen synchronously so the next between-iteration check in the running react_loop sees the flag. If cancel is queued behind dispatch in the pool, there is a race: the task may complete before the cancel is processed. Synchronous cancel ensures immediate cooperative termination of the running Back LLM's loop. |
| 7.3.3 | Pass CancellationToken from TaskLease into back_handler and back_resume_handler. Update_run_back_handler to include fsm_state (or the lease's CancellationToken directly) so_build_cancellation_check returns a real check instead of _never_cancel. Update back_handler and back_resume_handler signatures to accept cancellation_token as an explicit parameter (alongside fsm_state). Build cancellation_check from the lease token rather than from the optional fsm_state attribute. | WB 14.4B | Completes the cancellation wiring chain: (a) lease created with token at dispatch; (b) token passed to back_handler; (c)_build_cancellation_check returns async fn that checks token.is_cancelled; (d) react_loop checks between iterations. Currently step (b) is broken -- coordinator passes no fsm_state, so_build_cancellation_check returns _never_cancel. |
| 7.3.4 | Handle late-arriving envelopes for completed/cancelled tasks. When BackTopicRouter.route() receives an envelope for a task_id whose lease is RELEASED or CANCELLED, discard the envelope with a debug log instead of dispatching to a handler. This prevents: (a) task.complete arriving after cancel (dedup -- handled by FSM, but no need to waste a worker slot); (b) stale task.resume arriving for an already-completed task (race in multi-device scenarios). | WB 3.C | Prevents the Back LLM from starting a react_loop for a task that already finished. Without this, a late resume could start a new react_loop for a completed task, wasting tokens and producing a duplicate result that the FSM must dedup. |

---

### E7.4 -- Dependency Ordering + Ready Queue

Source: WB 3.C, dispatch_task depends_on field

**Rationale:** The Front LLM can dispatch tasks with depends_on pointing to a
prior task_id (dispatch_task tool in implementations.py L612-623). Currently
the FSM dispatches the dependent task immediately to Back regardless of
whether the predecessor has completed. The Back LLM starts its react_loop and
may call tools that depend on the predecessor's side effects (e.g., "book
hotel" depends_on "check availability" -- the hotel cannot be booked if
availability has not yet been confirmed). The BackPool ready-queue holds
dependent tasks until the predecessor completes.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 7.4.1 | Implement ReadyQueue in BackPool with methods: enqueue(envelope, depends_on: str or None), dequeue_ready() -> list[Envelope], notify_completed(task_id). When an envelope with depends_on is enqueued, it waits until notify_completed(depends_on) is called. Envelopes without depends_on are immediately ready. dequeue_ready returns all envelopes whose dependencies are satisfied. Ready envelopes are dispatched to acquire_worker in FIFO order. | WB 3.C | The Back LLM for a dependent task does NOT start until the predecessor finishes. Its SS snapshot (read at start) reflects the predecessor's completed artifacts. Without ordering, the LLM reads stale SS and may call tools that fail because the predecessor's side effects have not yet been applied. Example: task "book hotel" starts before "check availability" completes -- invoke_capability fails because no availability result exists yet. |
| 7.4.2 | Wire ReadyQueue into FSM task completion path. When _on_task_complete (controller.py L1063) removes a task_id from _active_task_ids, also call backpool.ready_queue.notify_completed(task_id). This triggers dequeue_ready() which returns any dependent envelopes now eligible for dispatch. For each ready envelope, acquire_worker and start the Back react_loop. Handle the case where the predecessor was CANCELLED or FAILED: notify_completed is still called, but the dependent task's BackPool worker must check predecessor status via TaskBridge.get_task(depends_on).status and fail immediately if predecessor is not COMPLETED. | WB 3.C | If a predecessor fails, the dependent task should NOT start its react_loop. The Back LLM would waste tokens discovering that the capability it depends on was never executed. Instead, emit task.failed with reason="dependency_failed" for the dependent task. The user is informed via Front that the chain was broken. |
| 7.4.3 | Handle circular or missing dependencies. On enqueue, validate that depends_on refers to a known task_id (registered in TaskBridge). If unknown, log a warning and dispatch immediately (treat as no dependency -- the LLM put a description string in depends_on, which implementations.py L616-623 already strips to None, but a valid-looking task-id that does not exist should also be handled). Detect cycles: if task A depends_on task B and task B depends_on task A, fail both with reason="circular_dependency". | WB 3.C | Prevents deadlock where two tasks wait for each other forever, consuming pool slots. No LLM runs for either task -- both fail immediately with a clear error. The user is informed via Front. |

---

### M7 BackPool ReAct Loop Interaction Audit

**Constraints derived from code reading (actors/back.py, demo/coordinator.py,
fsm/controller.py, fsm/task_bridge.py, protocols/cancellation.py,
bus/setup.py, tools/implementations.py):**

| # | Constraint | Code Evidence | M7 Implication |
|---|-----------|---------------|----------------|
| P1 | Current Back execution is a single asyncio.create_task per envelope in coordinator consumer. No pool, no isolation, no slot management. Tasks are tracked in_pending_back_tasks list. | coordinator.py L793-800 (_run_back_handler creates asyncio.Task, appends to list) | E7.1 replaces this with BackPool.acquire_worker + WorkerSlot. The coordinator list is replaced by pool-tracked workers. |
| P2 | Coordinator consumer passes NO fsm_state to back_handler. The fsm_state parameter is None. Therefore_build_cancellation_check returns _never_cancel, and the Back LLM's react_loop NEVER checks for cancellation. | coordinator.py L883-893 (_run_back_handler signature omits fsm_state), back.py L915-932 (_build_cancellation_check returns_never_cancel when fsm_state is None) | E7.2.2 and E7.3.3 fix this by passing the lease's CancellationToken directly. Cancellation becomes mandatory, not optional. |
| P3 | Coordinator consumer always calls back_handler for every Back envelope regardless of topic. back_resume_handler and back_cancel_handler are never invoked from the consumer. | coordinator.py L628 (imports only back_handler), L796 (calls only back_handler) | E7.3.1 + E7.3.2 introduce BackTopicRouter that dispatches by envelope.topic. |
| P4 | subscribe_back_events (back.py L745-788) wires 4 topics to a SINGLE handler_fn. It does NOT do topic-based routing internally. | back.py L745-788 (all topics -> one handler_fn) | E7.3.1 replaces the single handler_fn with topic-routed dispatch. subscribe_back_events becomes the wiring point for BackTopicRouter. |
| P5 | Each Back react_loop reads SS ONCE at start (_read_ss_snapshot, back.py L394). This snapshot is not refreshed during execution. Two concurrent workers reading SS at different times see different snapshots. | back.py L394-400 (_read_ss_snapshot called once) | Worker isolation is correct by design -- each worker gets its own frozen snapshot. But dependent tasks must NOT start until the predecessor's side effects are committed to SS (via FSM TaskBridge). E7.4 enforces this. |
| P6 | TaskBridge is the single writer for task_state and task_artifacts. Back LLM NEVER writes directly -- it emits deltas to the bus. | task_bridge.py L1-20 (docstring: FSM is single writer) | BackPool workers do NOT break single-writer invariant. All task state mutations flow through FSM bus handlers. Workers only READ SS and EMIT events. |
| P7 | dispatch_task tool supports depends_on field (implementations.py L612). The field is validated to start with "task-" prefix; non-task-ID strings are stripped to None. But no runtime ordering is enforced -- both tasks are dispatched to Back simultaneously. | implementations.py L612-623 (depends_on validation), controller.py L840-990 (_on_task_dispatch dispatches immediately) | E7.4 adds the ReadyQueue that holds dependent tasks until the predecessor completes. |
| P8 | CancellationToken (protocols/cancellation.py) is a well-designed cooperative token with cancel(), check() (raises TaskCancelledError), and wait_for_cancel(). It is per-task and idempotent. But it is created by _cancel_handler.register_task() inside the FSM, not passed to the Back worker. | cancellation.py L60-130 (CancellationToken), controller.py L871 (register_task) | E7.2.1 binds CancellationToken to TaskLease. E7.2.2 passes it to back_handler. The token is no longer orphaned inside the FSM. |

---

### Recommended Execution Order

1. **7.1.1** (BackPoolConfig -- foundation for pool sizing decisions)
2. **7.2.1** (TaskLease dataclass -- foundation for ownership model)
3. **7.1.2** (BackPool class with acquire/release workers)
4. **7.2.2** (bind CancellationToken from lease to worker)
5. **7.3.1** (BackTopicRouter -- topic-based dispatch table)
6. **7.3.2** (wire router into coordinator consumer -- highest LLM impact)
7. **7.3.3** (pass CancellationToken to back_handler -- second highest impact)
8. **7.1.3** (integrate BackPool into coordinator consumer)
9. **7.2.3** (lease expiry watcher -- zombie worker cleanup)
10. **7.2.4** (task.leased.v1 event emission -- observability)
11. **7.2.5** (lease renewal for long-running tasks)
12. **7.3.4** (late-envelope discard for completed/cancelled tasks)
13. **7.4.1** (ReadyQueue for dependency ordering)
14. **7.4.2** (wire ReadyQueue into FSM task completion path)
15. **7.4.3** (circular/missing dependency detection)
16. **7.1.4** (pool-level observability metrics)

---

### E7.5 -- End-to-End Wiring: BackPool + Task Lease + Topic Router into Cumulative M1-M6 Infrastructure

Source: Wiring audit (systematic cross-milestone integration)

**Rationale:** E7.1-E7.4 build four new subsystems -- BackPool worker management, TaskLease model, BackTopicRouter, and ReadyQueue dependency ordering -- but treat each in isolation. None of the 16 issues address how these subsystems integrate with the cumulative M1+M2+M3+M4+M5+M6 infrastructure. Without explicit wiring:

- `task.leased.v1`, `backpool.worker.acquired`, `backpool.worker.released` bus topics have no M2 guard table entries (guard_dispatch rejects them -> dead-letter storm for every pool acquisition)
- M1's LedgerMiddleware has no canonical event classes for pool/lease lifecycle (ledger drops them or records raw envelope dumps)
- BackPool replaces the coordinator's `asyncio.create_task` pattern but both `coordinator.py` (L750-800) and `kernel/bootstrap.py` (L340-400) hardcode `back_handler` with no topic routing and no fsm_state -- BOTH entry points must be updated
- TaskLease binds CancellationToken to worker, but M6's mandatory cancellation callback (6.2.4) and M3's between-iteration cancel check (loop.py L250) must wire to the lease's token, not the FSM's orphan token
- ReadyQueue holds dependent tasks until predecessors complete, but M4's TaskBridge.complete_task() and M5's RunningTaskHandle.mark_complete() must notify the queue
- M6's HILSubTask suspension must interact with TaskLease: suspension preserves the lease (prevents expiry-cancel during HITL wait), resume re-acquires or retains the worker slot
- M5's ConversationArbiter cancel path sets cancellation flags on RunningTaskHandle -- this must now target the pool worker's lease token, not a standalone flag
- M5's InflightContext reads active task info -- it must now include pool worker state (worker_id, lease status) for accurate arbiter decisions

**Every M7 artifact must plug into the cumulative M1+M2+M3+M4+M5+M6 infrastructure or the BackPool exists as a disconnected execution model with no observability, no guard table protection, no lease-to-cancel propagation, and no dependency-to-completion wiring.**

**System state after M1+M2+M3+M4+M5+M6 (E1.4 + E2.5 + E3.7 + E4.5 + E5.5 + E6.5 wiring complete) -- what M7 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created             # M1 1.4.1
  -> LedgerMiddleware in bus middleware chain                # M1 1.4.4
  -> ConciergeController(bus, router)
     -> set_ledger(writer)                                  # M1 1.4.1
     -> _ledger_append() in 11+ handlers                    # M1 1.4.2
     -> _try_deserialize() bridge                           # M1 1.4.3
     -> _dispatch_envelope() flow:                          # M2 2.5.3
          topic_guard -> idempotency -> guard_dispatch -> handler
     -> FULL_GUARD_TABLE + _guard_dispatch()                # M2 2.1.1-2.1.2
     -> _publish_dead_letter() with ledger recording        # M2 2.5.2
     -> IdempotencyLedger                                   # M2 2.3.2
     -> decide_response_final() + ResponseFinalEvent        # M2 2.3.1, 2.5.4
     -> Per-task CancellationToken in _cancel_tokens        # M3 3.2.2
  -> route_back_envelope() as canonical back dispatch        # M3 3.1.1-3.1.3
  -> DeadLetterConsumer subscribed to bus                    # M2 2.5.1
  -> Unknown back topics -> dead-letter pipeline             # M3 3.7.1
  -> builders auto-enrich legacy dicts                       # M1 1.4.5
  -> actors/shared.py: parse_envelope_payload,
       safe_get_section, never_cancel                        # M3 3.5.1-3.5.3
  -> SuspensionManager (timeout lifecycle after M6)          # M3 3.3.1, M6
  -> classify_tool_batch() in react_loop                     # M3 3.4.2
  -> ReactResult carries parallel/sequential counts          # M3 3.7.4
  -> TaskBridge.rebind() to real SS task_state/task_artifacts # M4 4.1.1, 4.5.1
  -> ControlExtension.bind_control_section() + fsm_overlay   # M4 4.1.2, 4.5.2
  -> writer_port (DirectWriterAdapter) on ToolContext         # M4 4.2.1, 4.5.3
  -> 6 cognitive tools through writer_port.request_mutation() # M4 4.2.3
  -> LLM-writable allowlist in config                        # M4 4.2.2
  -> Runtime guard rejecting LLM writes to system sections   # M4 4.2.4
  -> update_session_bundle with batch_mutations              # M4 4.3.1-4.3.3
  -> SECTION_RENDERERS + _read_ss_sections() in stage 8      # M4 4.4.1-4.4.2
  -> DynamicPromptBuilder.build(ss=ss) parameter             # M4 4.4.2
  -> TurnMutationSummaryEvent in ledger at turn completion   # M4 4.5.4
  -> ToolContext.idempotency_cache for bundle dedup           # M4 4.5.5
  -> ConversationArbiter replaces InterruptClassifier         # M5 5.5.1
  -> ArbiterDecision enum (CANCEL/MODIFY_INFLIGHT/PARALLEL_NEW/DEFER) # M5 5.2.1
  -> InflightContext from SS task_state + control overlay     # M5 5.5.2
  -> k1.arbiter.intent.v1 event in guard table + ledger      # M5 5.5.1
  -> _handle_arbiter_cancel/modify/defer/parallel_new         # M5 5.2.2-5.2.5
  -> RunningTaskHandle + _running_tasks for message injection # M5 5.5.4
  -> _enrich_envelope_with_arbiter() + routing_metadata       # M5 5.5.5
  -> device_id tracking on MetaSection + ToolContext           # M5 5.5.6
  -> resolve_device_conflict() precedence rules               # M5 5.4.2
  -> Multi-device confirmation via clarification mechanism    # M5 5.4.3
  -> HILSubTask dataclass (PENDING/RESOLVED/TIMED_OUT/CANCELLED) # M6 6.1.1
  -> 4 HITL topics in guard table + 4 canonical event classes  # M6 6.5.1
  -> back_resume_handler wired via topic routing (M6 protocol) # M6 6.2.1, 6.5.2
  -> validate_before_invoke in tool dispatch (L2 check)        # M6 6.1.3, 6.5.4
  -> resume_token validation on task.resume.v1                 # M6 6.1.4, 6.5.5
  -> scan_for_recovery at FSM startup after SS binding         # M6 6.4.2, 6.5.5
  -> Consolidated suspension limits at HILSubTask creation     # M6 6.3.4
  -> Mandatory cancellation callback for Back dispatch         # M6 6.2.4, 6.5.3
  -> Demo: hitl_wired + validate_hitl_wiring + /api/session/hitl # M6 6.5.9
  -> Fixtures: create_wired_fsm(with_ledger,
       with_dead_letter_consumer, with_cancel_tokens,
       with_ss_binding, with_writer_port, with_arbiter,
       with_hitl)                                              # M1-M6 fixtures
```

**M7 artifacts that must integrate into this M1+M2+M3+M4+M5+M6-wired system:**

| M7 Artifact | Where It Lives After E7.1-E7.4 | M1+M2+M3+M4+M5+M6 Touchpoint It Must Connect To |
|-------------|-------------------------------|----------------------------------------------|
| `BackPoolConfig` dataclass (pool_size=3, max_concurrent_per_session=2, lease_ttl_s=300) | `actors/pool.py` | M4 config centralization: pool config must be loadable from same config source as LLM-writable allowlist, writer_port settings. M5 InflightContext needs pool_size for arbiter capacity decisions. |
| `BackPool` class (acquire_worker/release_worker/get_active_workers) | `actors/pool.py` | M5 RunningTaskHandle._running_tasks replaced by BackPool.get_active_workers(). M5 arbiter cancel targets pool worker's lease token via BackPool.get_worker(task_id). M6 HILSubTask resume must go through pool worker acquisition. |
| BackPool integration into coordinator consumer (replaces asyncio.create_task) | `demo/coordinator.py` L750-800, `kernel/bootstrap.py` L340-400 | BOTH entry points must be updated. Coordinator consumer and kernel bootstrap consumer currently hardcode `back_handler` with no topic routing. M7 replaces with BackPool.acquire_worker() + BackTopicRouter.route(). |
| `backpool.worker.acquired` / `backpool.worker.released` bus events | `bus/topics.py`, `bus/builders.py` | M2 FULL_GUARD_TABLE needs entries for both topics. M1 LedgerMiddleware must record them. M2 dead-letter pipeline must not reject them. |
| `TaskLease` dataclass (task_id, worker_id, lease_id, expires_at_ns, cancellation_token, status) | `protocols/lease.py` | M3 Per-task CancellationToken in _cancel_tokens must be the SAME token bound to TaskLease (not a separate orphan). M6 mandatory cancellation callback must use lease's token. M1 ledger records TaskLeasedEvent. |
| TaskLease creation at dispatch + CancellationToken binding | `fsm/controller.py` _on_task_dispatch | M3 _cancel_tokens[task_id] must point to lease's CancellationToken (single source of truth). M1_ledger_append fires TaskLeasedEvent AFTER lease creation. M2 guard table allows task.leased.v1 in COMPANIONING state. |
| `task.leased.v1` bus event | `bus/topics.py`, `bus/builders.py` | M2 FULL_GUARD_TABLE needs entry. M1 LedgerMiddleware needs canonical TaskLeasedEvent. M2 IdempotencyLedger must handle lease event dedup. |
| Lease expiry watcher (background asyncio.Task) | `actors/pool.py` or `protocols/lease.py` | M1 ledger records TaskLeaseExpiredEvent. M3 CancellationToken.cancel() called on expiry (cooperative cancel then hard kill). M6 HITL interaction: lease must NOT expire during suspension (extend or pause TTL). |
| Lease renewal for long-running tasks | `protocols/lease.py` | M1 ledger records TaskLeaseRenewedEvent. M4 TaskBridge must verify task still active before renewal. M5 InflightContext must reflect renewed lease deadline for arbiter capacity planning. |
| `BackTopicRouter` class (route(envelope) -> handler_fn) | `actors/router.py` | M6 back_resume_handler topic routing (6.2.1) is already protocol-level; M7's BackTopicRouter is the runtime dispatcher. M3 route_back_envelope() remains canonical FSM dispatch path; BackTopicRouter sits in the consumer layer AFTER route_back_envelope() delivers to Back mailbox. |
| BackTopicRouter integration into coordinator consumer | `demo/coordinator.py`, `kernel/bootstrap.py` | Both entry points must use BackTopicRouter.route() instead of hardcoded back_handler. M6 topic routing (task.resume.v1 -> back_resume_handler) is now enforced by the router, not ad-hoc consumer logic. |
| CancellationToken from TaskLease passed to back_handler/back_resume_handler | `actors/back.py` | M3 _build_cancellation_check(fsm_state) currently returns _never_cancel when fsm_state is None. M7 replaces this: lease.cancellation_token passed directly. M6 mandatory callback is this same token's check(). |
| Late-arriving envelope discard for completed/cancelled tasks | `actors/router.py` | M2 dead-letter pipeline: discarded late envelopes must be routed to dead-letter with reason="late_arrival_task_complete". M1 ledger records LateEnvelopeDiscardedEvent. |
| `ReadyQueue` (enqueue with depends_on, dequeue_ready, notify_completed) | `actors/queue.py` | M4 TaskBridge.complete_task() must call ReadyQueue.notify_completed(task_id). M5 RunningTaskHandle.mark_complete() must also notify. M2 guard table: tasks held in queue do NOT dead-letter (they are deferred, not rejected). |
| ReadyQueue wired into FSM _on_task_complete | `fsm/controller.py` | M4 TaskBridge.complete_task() syncs task_state. M7 adds ReadyQueue.notify_completed() in same handler. Triggered dependent tasks go through normal_on_task_dispatch path (full M2 guard table + M1 ledger coverage). |
| Circular/missing dependency detection | `actors/queue.py` | M2 dead-letter: tasks with circular deps must be routed to dead-letter with reason="circular_dependency". M1 ledger records DependencyFailedEvent. M4 TaskBridge must mark task as FAILED (not silently queued forever). |

---

#### 7.5.1 -- Register BackPool + Lease bus topics in M2 guard table and M1 ledger pipeline

**Problem:** E7.1.4 emits `backpool.worker.acquired` and `backpool.worker.released` events. E7.2.4 emits `task.leased.v1`. But M2's `_dispatch_envelope()` flow runs: topic_guard -> idempotency -> guard_dispatch -> handler. If these 3 topics have no `FULL_GUARD_TABLE` entries, `_guard_dispatch()` rejects them as unknown topics and routes every pool acquisition and lease event to dead-letter. Pool observability would generate a dead-letter storm.

Additionally, M1's `LedgerMiddleware` records all bus events. Without canonical event classes, the ledger records raw envelope dumps instead of structured pool/lease events.

**What to do:**

1. Add 3 new topic constants to `bus/topics.py`:

   ```python
   TOPIC_TASK_LEASED = "task.leased.v1"
   TOPIC_BACKPOOL_WORKER_ACQUIRED = "backpool.worker.acquired"
   TOPIC_BACKPOOL_WORKER_RELEASED = "backpool.worker.released"
   ```

2. Add all 3 topics to `FULL_GUARD_TABLE` in `fsm/controller.py`:

   ```python
   # BackPool lifecycle events -- informational, emitted BY the coordinator/pool.
   # These are observability passthroughs -- they do NOT cause FSM state transitions.
   # task.leased.v1 fires during COMPANIONING (dispatch creates lease).
   (ConciergeState.COMPANIONING, TOPIC_TASK_LEASED): [ConciergeState.COMPANIONING],
   (ConciergeState.PROGRESSING, TOPIC_TASK_LEASED): [ConciergeState.PROGRESSING],

   # Worker acquired/released can happen during any active-task state.
   (ConciergeState.COMPANIONING, TOPIC_BACKPOOL_WORKER_ACQUIRED): [ConciergeState.COMPANIONING],
   (ConciergeState.PROGRESSING, TOPIC_BACKPOOL_WORKER_ACQUIRED): [ConciergeState.PROGRESSING],
   (ConciergeState.CLARIFYING_WORKER, TOPIC_BACKPOOL_WORKER_ACQUIRED): [ConciergeState.CLARIFYING_WORKER],

   (ConciergeState.COMPANIONING, TOPIC_BACKPOOL_WORKER_RELEASED): [ConciergeState.COMPANIONING],
   (ConciergeState.PROGRESSING, TOPIC_BACKPOOL_WORKER_RELEASED): [ConciergeState.PROGRESSING],
   (ConciergeState.CLARIFYING_WORKER, TOPIC_BACKPOOL_WORKER_RELEASED): [ConciergeState.CLARIFYING_WORKER],
   (ConciergeState.LISTENING, TOPIC_BACKPOOL_WORKER_RELEASED): [ConciergeState.LISTENING],
   ```

3. Create canonical event classes:

   ```python
   @dataclass
   class TaskLeasedEvent(CanonicalEventMeta):
       task_id: str
       worker_id: str
       lease_id: str
       lease_ttl_s: int
       expires_at_ns: int
       pool_size: int
       active_workers: int       # pool utilization at lease time

   @dataclass
   class TaskLeaseExpiredEvent(CanonicalEventMeta):
       task_id: str
       worker_id: str
       lease_id: str
       elapsed_s: float
       renewals_used: int
       hard_killed: bool         # True if cooperative cancel timed out

   @dataclass
   class TaskLeaseRenewedEvent(CanonicalEventMeta):
       task_id: str
       worker_id: str
       lease_id: str
       renewal_count: int        # 1, 2, or 3
       new_expires_at_ns: int
       extension_s: int

   @dataclass
   class BackPoolWorkerAcquiredEvent(CanonicalEventMeta):
       worker_id: str
       task_id: str
       pool_size: int
       active_workers: int       # count AFTER acquisition
       session_id: str | None

   @dataclass
   class BackPoolWorkerReleasedEvent(CanonicalEventMeta):
       worker_id: str
       task_id: str
       pool_size: int
       active_workers: int       # count AFTER release
       release_reason: str       # "completed" | "cancelled" | "lease_expired" | "error"
   ```

4. Register all event classes in M1's event registry.

5. Add builders to `bus/builders.py`:

   ```python
   def build_task_leased(task_id, worker_id, lease_id, lease_ttl_s, ...): ...
   def build_backpool_worker_acquired(worker_id, task_id, ...): ...
   def build_backpool_worker_released(worker_id, task_id, release_reason, ...): ...
   ```

6. Wire `_ledger_append()` at each emission point:
   - `task.leased.v1`: in `_on_task_dispatch` after TaskLease creation
   - `backpool.worker.acquired`: in BackPool.acquire_worker() after slot assignment
   - `backpool.worker.released`: in BackPool.release_worker() after slot free

7. Add test: trigger each pool/lease event, verify it passes guard_dispatch without dead-letter, and appears as structured event in ledger.

**Files to modify:**

- `poc/k1_poc/bus/topics.py` (3 new topic constants)
- `poc/k1_poc/bus/builders.py` (3 new builder functions)
- `poc/k1_poc/fsm/controller.py` (FULL_GUARD_TABLE entries for 3 topics, _ledger_append at emission points)
- `poc/k1_poc/events/` (5 canonical event classes)
- `poc/k1_poc/events/registry.py` (register 5 pool/lease event classes)

**Dependency:** E7.1.4 (pool observability events), E7.2.1 (TaskLease), E7.2.4 (task.leased.v1), M2 2.1.1 (FULL_GUARD_TABLE), M1 1.4.2 (_ledger_append pattern), M1 1.4.4 (LedgerMiddleware)

**Acceptance:**

- All 3 bus topics pass `_guard_dispatch()` without dead-letter
- Guard table allows each topic in its logically valid states
- 5 canonical event classes exist for pool/lease lifecycle
- `_ledger_append()` records structured events at each lifecycle boundary
- Ledger entries include worker_id, lease_id, pool utilization, release_reason
- Zero dead-letters from pool/lease topics under normal operation

---

#### 7.5.2 -- Wire BackPool + BackTopicRouter into BOTH coordinator consumer and kernel bootstrap consumer

**Problem:** The system has TWO entry points for Back task execution:

1. `demo/coordinator.py` L750-800: `_mailbox_consumer` back section -- polls `back_mailbox`, calls `self._run_back_handler(env, back_handler)`, appends result to `_pending_back_tasks` list.
2. `kernel/bootstrap.py` L340-400: Kernel consumer loop -- polls `back_mailbox`, calls `back_handler(envelope=back_env, model=..., ss=..., bus=..., tool_dispatcher=...)`.

BOTH hardcode `back_handler` for ALL topics. BOTH pass NO `fsm_state`. BOTH use raw `asyncio.create_task` with no pool management. E7.1.3 says "integrate BackPool into coordinator consumer" but does not mention `kernel/bootstrap.py`. If only one entry point is updated, the kernel bootstrap path remains a single-worker, no-routing, no-lease, no-pool execution model.

E7.3.2 says "wire router into coordinator consumer" but again only mentions coordinator. The BackTopicRouter must sit in BOTH consumers.

**What to do:**

1. In `demo/coordinator.py` `_mailbox_consumer` back section (L750-800):

   ```python
   # BEFORE (M6 state):
   # env = await self.back_mailbox.get()
   # task = asyncio.create_task(self._run_back_handler(env, back_handler))
   # self._pending_back_tasks.append(task)

   # AFTER (M7 wiring):
   env = await self.back_mailbox.get()
   task_id = env.payload.get("task_id")

   # 1. Acquire worker from pool (blocks if pool full)
   worker_slot = await self.back_pool.acquire_worker(task_id, session_id=env.session_id)

   # 2. Create TaskLease bound to worker
   lease = TaskLease.create(
       task_id=task_id,
       worker_id=worker_slot.worker_id,
       ttl_s=self.back_pool.config.lease_ttl_s,
   )

   # 3. Route via BackTopicRouter (dispatch/resume/cancel -> correct handler)
   handler_fn = self.back_topic_router.route(env)

   # 4. Execute in worker's asyncio.Task with lease's CancellationToken
   task = asyncio.create_task(
       worker_slot.run(handler_fn, env, cancellation_token=lease.cancellation_token)
   )
   worker_slot.bind_task(task, lease)
   ```

2. In `kernel/bootstrap.py` consumer loop (L340-400) -- apply the SAME pattern:

   ```python
   # BEFORE (M6 state):
   # back_env = await runtime.back_mailbox.get()
   # await back_handler(envelope=back_env, model=..., ss=..., bus=..., tool_dispatcher=...)

   # AFTER (M7 wiring):
   back_env = await runtime.back_mailbox.get()
   task_id = back_env.payload.get("task_id")

   worker_slot = await runtime.back_pool.acquire_worker(task_id, session_id=back_env.session_id)
   lease = TaskLease.create(
       task_id=task_id,
       worker_id=worker_slot.worker_id,
       ttl_s=runtime.back_pool.config.lease_ttl_s,
   )
   handler_fn = runtime.back_topic_router.route(back_env)
   asyncio.create_task(
       worker_slot.run(handler_fn, back_env, cancellation_token=lease.cancellation_token)
   )
   ```

3. Add `back_pool` and `back_topic_router` to `KernelRuntime` (bootstrap.py L83) and to `K1DemoCoordinator.__init__` (coordinator.py):

   ```python
   # In bootstrap.py start_kernel():
   back_pool = BackPool(BackPoolConfig())
   back_topic_router = BackTopicRouter({
       TOPIC_TASK_DISPATCH: back_handler,
       TOPIC_TASK_RESUME: back_resume_handler,
       TOPIC_TASK_CANCEL: back_cancel_handler,
   })
   # ...
   runtime.back_pool = back_pool
   runtime.back_topic_router = back_topic_router
   ```

4. Import `back_resume_handler` and `back_cancel_handler` in both files (currently only `back_handler` is imported at bootstrap.py L37 and coordinator.py L628).

5. Replace `_pending_back_tasks: list[asyncio.Task]` in coordinator with `BackPool.get_active_workers()` for task tracking.

6. Add test: boot kernel via both entry points, dispatch 2 concurrent tasks, verify pool assigns different worker_ids, verify topic routing sends task.resume.v1 to back_resume_handler (not back_handler).

**Files to modify:**

- `poc/k1_poc/demo/coordinator.py` (replace _mailbox_consumer back section + _run_back_handler, add back_pool + back_topic_router attributes, import back_resume_handler + back_cancel_handler)
- `poc/k1_poc/kernel/bootstrap.py` (replace consumer loop back section, add BackPool + BackTopicRouter to KernelRuntime, import back_resume_handler + back_cancel_handler)

**Dependency:** E7.1.2 (BackPool class), E7.1.3 (coordinator integration), E7.3.1 (BackTopicRouter), E7.3.2 (router integration), 7.5.1 (guard table entries for pool events)

**Acceptance:**

- BOTH coordinator.py and kernel/bootstrap.py use BackPool.acquire_worker() + BackTopicRouter.route()
- Neither entry point hardcodes `back_handler` for all topics
- `back_resume_handler` and `back_cancel_handler` imported and routed in both files
- `_pending_back_tasks` list replaced by BackPool worker tracking
- Pool assigns unique worker_ids to concurrent tasks
- Worker count respects pool_size limit (default 3)
- Session concurrency respects max_concurrent_per_session (default 2)
- KernelRuntime has `back_pool` and `back_topic_router` attributes

---

#### 7.5.3 -- Wire TaskLease CancellationToken as single source of truth for cancel propagation

**Problem:** Three cancel mechanisms exist after M1-M6:

1. **M3's _cancel_tokens[task_id]**: CancellationToken created in FSM's `_on_task_dispatch` (controller.py L870) via `_cancel_handler.register_task(task_id)`. Lives in FSM memory.
2. **M6's mandatory cancellation callback**: `back_handler` and `back_resume_handler` receive a cancellation callback that must be checked between react_loop iterations (6.2.4).
3. **M7's TaskLease.cancellation_token**: Created when lease is assigned to worker (7.2.1-7.2.2).

Currently in the M6 state, `coordinator.py::_run_back_handler` (L870-920) passes NO `fsm_state` to `back_handler`. This means `_build_cancellation_check(fsm_state)` at back.py L915 receives `None` and returns `_never_cancel` (L930) -- a function that always returns `False`. Cooperative cancellation is entirely dead.

M7's TaskLease creates a CancellationToken, but unless it becomes the SINGLE source of truth that all three mechanisms point to, there will be three disconnected cancel paths.

**What to do:**

1. **Unify cancel token creation**: When `_on_task_dispatch` fires (controller.py L870), the FSM creates a CancellationToken via `_cancel_handler.register_task(task_id)`. This SAME token must be passed to `TaskLease.create()` in the coordinator consumer (7.5.2). Do NOT create a second token in the lease:

   ```python
   # In coordinator consumer (after 7.5.2 wiring):
   fsm_cancel_token = fsm_controller.get_cancel_token(task_id)
   lease = TaskLease.create(
       task_id=task_id,
       worker_id=worker_slot.worker_id,
       ttl_s=config.lease_ttl_s,
       cancellation_token=fsm_cancel_token,  # SAME token as FSM's
   )
   ```

2. **Wire token into back_handler/back_resume_handler**: The coordinator consumer (7.5.2) passes `lease.cancellation_token` to the handler via `worker_slot.run()`. The handler uses it for `_build_cancellation_check()`:

   ```python
   # In back_handler / back_resume_handler:
   # BEFORE: cancellation_check = _build_cancellation_check(fsm_state)
   #         -> returns _never_cancel because fsm_state is None
   # AFTER:  cancellation_check = _build_cancellation_check_from_token(cancellation_token)
   #         -> returns token.check which raises TaskCancelledError when cancelled

   async def _build_cancellation_check_from_token(token: CancellationToken):
       async def _check() -> bool:
           return token.is_cancelled
       return _check
   ```

3. **Wire M5 arbiter cancel into lease token**: M5's `_handle_arbiter_cancel` (5.2.2) currently calls `RunningTaskHandle.cancel()`. With M7, this must route through BackPool:

   ```python
   # In _handle_arbiter_cancel():
   # BEFORE: handle = self._running_tasks.get(task_id)
   #         handle.cancel()
   # AFTER:  worker = self.back_pool.get_worker_for_task(task_id)
   #         worker.lease.cancellation_token.cancel()
   #         # This triggers the SAME token checked in react_loop
   ```

4. **Wire M6 HITL timeout auto-cancel into lease token**: M6's `hitl.timed_out.v1` handler (6.3.3) transitions task to CANCELLED. The cancellation must go through the lease's token so the Back worker's react_loop sees it cooperatively:

   ```python
   # In HITL timeout handler:
   worker = self.back_pool.get_worker_for_task(task_id)
   if worker:
       worker.lease.cancellation_token.cancel()
   ```

5. **Expose FSM cancel token to coordinator**: Add `get_cancel_token(task_id) -> CancellationToken` to ConciergeController's public interface (it currently lives in `_cancel_handler` which is private).

6. **Wire lease expiry to cancel**: When lease expiry watcher (7.2.3) detects an expired lease, it calls `lease.cancellation_token.cancel()` (cooperative) then waits grace period, then hard-kills the asyncio.Task. The token is the same one the react_loop checks.

7. Add test: dispatch task -> cancel via arbiter -> verify same CancellationToken.is_cancelled is True -> verify react_loop iteration sees it -> verify lease status changes to CANCELLED.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (expose get_cancel_token, pass token to lease creation)
- `poc/k1_poc/actors/back.py` (_build_cancellation_check_from_token replacing_build_cancellation_check path, remove _never_cancel fallback for pool workers)
- `poc/k1_poc/demo/coordinator.py` (pass FSM cancel token to TaskLease)
- `poc/k1_poc/kernel/bootstrap.py` (same wiring for kernel consumer)

**Dependency:** E7.2.1 (TaskLease), E7.2.2 (bind CancellationToken), 7.5.2 (pool wired into consumers), M3 3.2.2 (per-task CancellationToken), M5 5.2.2 (arbiter cancel), M6 6.2.4 (mandatory cancellation callback)

**Acceptance:**

- Single CancellationToken per task: created in FSM, bound to TaskLease, used by react_loop
- `_never_cancel` is NEVER returned for pool-managed workers
- M5 arbiter cancel propagates through lease.cancellation_token.cancel()
- M6 HITL timeout cancel propagates through same token
- Lease expiry watcher cancels through same token
- react_loop iteration checks token.is_cancelled (not _never_cancel)
- `get_cancel_token(task_id)` exposed on ConciergeController

---

#### 7.5.4 -- Wire ReadyQueue into M4 TaskBridge completion and M5 RunningTaskHandle lifecycle

**Problem:** E7.4.1-7.4.2 create a ReadyQueue that holds tasks with `depends_on` until predecessors complete, and wire it into FSM's `_on_task_complete`. But task completion happens at multiple points in the M1-M6 stack:

1. **FSM _on_task_complete** (controller.py L1063): Discards from `_active_task_ids`, handles cancel dedup. E7.4.2 wires ReadyQueue.notify_completed() here.
2. **M4 TaskBridge.complete_task()**: Syncs task_state on SS, marks status=COMPLETED. This is the SS persistence point.
3. **M5 RunningTaskHandle.mark_complete()**: Removes task from `_running_tasks` map.
4. **M7 BackPool.release_worker()**: Returns worker slot to pool.

All four must fire ReadyQueue.notify_completed() OR there must be a single coordination point. If TaskBridge completes before ReadyQueue is notified, a dependent task may read stale SS state from the predecessor.

Additionally, M4's `tools/implementations.py::execute_dispatch_task` (L601-623) validates `depends_on` starts with "task-" but does NOT check if the dependency is registered in the ReadyQueue. If a task is dispatched with depends_on referencing a task_id that never existed, the ReadyQueue holds it forever.

**What to do:**

1. **Single notification point**: `_on_task_complete` in FSM is the canonical completion handler (it already runs after Back emits `task.complete.v1`). Wire ReadyQueue.notify_completed() here, AFTER TaskBridge.complete_task() has synced SS:

   ```python
   # In _on_task_complete (controller.py):
   async def _on_task_complete(self, envelope):
       task_id = envelope.payload["task_id"]
       # 1. Existing: cancel dedup, active_task_ids discard
       self._active_task_ids.discard(task_id)
       # 2. Existing M4: TaskBridge syncs SS
       await self._task_bridge.complete_task(task_id, result=envelope.payload)
       # 3. NEW M7: Release worker + lease
       await self._back_pool.release_worker(task_id, reason="completed")
       # 4. NEW M7: Notify ReadyQueue (may trigger dependent dispatch)
       ready_tasks = self._ready_queue.notify_completed(task_id)
       for dep_task_id in ready_tasks:
           await self._on_task_dispatch(self._ready_queue.get_deferred_envelope(dep_task_id))
       # 5. Existing M5: Remove RunningTaskHandle
       self._running_tasks.pop(task_id, None)
   ```

2. **Wire ReadyQueue into _on_task_dispatch**: When a new task arrives with `depends_on`, check ReadyQueue before dispatching to Back:

   ```python
   # In _on_task_dispatch (controller.py L840):
   depends_on = envelope.payload.get("depends_on")
   if depends_on:
       if not self._ready_queue.is_completed(depends_on):
           self._ready_queue.enqueue(envelope, depends_on=depends_on)
           self._ledger_append(TaskDeferredEvent(task_id=task_id, depends_on=depends_on))
           return  # Do NOT dispatch to Back yet
   # ... normal dispatch path (BackPool + lease + router)
   ```

3. **Validate dependency existence**: In `_on_task_dispatch`, when `depends_on` is present, verify the dependency task_id is known (either active, completed, or queued). If unknown, fail fast:

   ```python
   if depends_on and not self._is_known_task(depends_on):
       self._ledger_append(DependencyFailedEvent(task_id=task_id, depends_on=depends_on, reason="unknown_dependency"))
       await self._publish_dead_letter(envelope, reason="unknown_dependency")
       return
   ```

4. **Wire circular detection** (7.4.3) into the enqueue path: ReadyQueue.enqueue() calls `detect_cycle()` before accepting. Circular deps -> dead-letter + DependencyFailedEvent in ledger.

5. **Add canonical events**:

   ```python
   @dataclass
   class TaskDeferredEvent(CanonicalEventMeta):
       task_id: str
       depends_on: str
       queue_depth: int

   @dataclass
   class DependencyFailedEvent(CanonicalEventMeta):
       task_id: str
       depends_on: str
       reason: str  # "unknown_dependency" | "circular_dependency"
   ```

6. Register both in M2 guard table and M1 ledger.

7. Add test: dispatch task A, dispatch task B (depends_on=A), verify B is queued. Complete A, verify B auto-dispatches. Verify TaskDeferredEvent and TaskLeasedEvent for B appear in ledger in correct order.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (_on_task_complete with ReadyQueue.notify_completed + BackPool.release_worker,_on_task_dispatch with ReadyQueue.enqueue + dependency validation)
- `poc/k1_poc/events/` (TaskDeferredEvent, DependencyFailedEvent)
- `poc/k1_poc/events/registry.py` (register 2 events)
- `poc/k1_poc/bus/topics.py` (if separate topics needed for deferred/failed, or use existing task.* namespace)

**Dependency:** E7.4.1 (ReadyQueue), E7.4.2 (wire into FSM), E7.4.3 (circular detection), 7.5.1 (guard table), M4 4.1.1 (TaskBridge), M5 5.5.4 (RunningTaskHandle)

**Acceptance:**

- ReadyQueue.notify_completed() fires AFTER TaskBridge.complete_task() syncs SS
- Dependent tasks auto-dispatch through normal _on_task_dispatch path (full guard table + ledger coverage)
- Unknown dependencies fail fast with DependencyFailedEvent + dead-letter
- Circular dependencies detected and fail fast
- Deferred tasks appear in ledger with TaskDeferredEvent
- BackPool.release_worker() fires in_on_task_complete BEFORE ReadyQueue notification (free the slot before dependent uses it)
- M5 RunningTaskHandle cleanup fires AFTER ReadyQueue notification

---

#### 7.5.5 -- Wire BackPool + TaskLease with M6 HITL suspension lifecycle

**Problem:** M6's HITL model suspends a task (HILSubTask status=PENDING) and waits for human input. M7's BackPool assigns each task a worker slot with a TaskLease that has a TTL. These two systems interact at multiple points:

1. **Suspension must preserve the lease**: When Back calls `submit_result(needs_human)` and the task suspends, the worker slot is idle but the task is NOT complete. If the lease TTL expires during HITL wait (which can be minutes), the expiry watcher would cancel the task -- destroying the HITL flow.
2. **Worker slot during suspension**: The worker's react_loop has returned (it emitted needs_human). The worker slot should be RELEASED back to the pool (so other tasks can use it) but the lease must remain ACTIVE with TTL paused or extended to match M6's HITL timeout.
3. **Resume must re-acquire a worker slot**: When `task.resume.v1` arrives after HITL resolution, BackPool must acquire a new worker slot (or the same one if available) for the resumed react_loop. The resumed loop gets the SAME CancellationToken (7.5.3).
4. **HITL timeout must trigger lease cancellation**: If M6's HITL timeout fires, the lease's CancellationToken must be cancelled (7.5.3). If the worker has already been released, the token cancellation is recorded but no worker needs killing.

**What to do:**

1. **Add lease suspension state**: Extend TaskLease.status enum:

   ```python
   class LeaseStatus(str, Enum):
       ACTIVE = "active"
       SUSPENDED = "suspended"   # NEW: worker released, lease preserved
       EXPIRED = "expired"
       RELEASED = "released"
       CANCELLED = "cancelled"
   ```

2. **Wire suspension into coordinator consumer**: When Back's react_loop returns with `needs_human` result:

   ```python
   # After back_handler returns with needs_human:
   # 1. Transition lease to SUSPENDED (pauses TTL countdown)
   lease.suspend()  # Sets status=SUSPENDED, records suspension_started_at
   # 2. Release worker slot back to pool (free for other tasks)
   await self.back_pool.release_worker(task_id, reason="suspended")
   # 3. Do NOT cancel the lease -- it stays alive for resume
   # 4. Emit backpool.worker.released with release_reason="suspended"
   ```

3. **Wire resume into coordinator consumer**: When `task.resume.v1` arrives:

   ```python
   # BackTopicRouter routes to back_resume_handler path:
   # 1. Acquire new worker slot from pool
   worker_slot = await self.back_pool.acquire_worker(task_id, session_id=env.session_id)
   # 2. Resume lease (reactivate TTL from remaining or fresh TTL)
   lease.resume(new_worker_id=worker_slot.worker_id)
   # 3. Pass SAME CancellationToken to back_resume_handler
   # 4. Emit backpool.worker.acquired with note "resumed"
   ```

4. **Wire HITL timeout into lease**: M6's HITL timeout handler fires `hitl.timed_out.v1` and cancels the task. At this point:

   ```python
   # In HITL timeout handler:
   lease = self._get_lease(task_id)
   if lease and lease.status == LeaseStatus.SUSPENDED:
       lease.cancel()  # Transitions to CANCELLED, cancels token
       # No worker to kill (already released)
       self._ledger_append(TaskLeaseExpiredEvent(
           task_id=task_id, worker_id=lease.worker_id,
           lease_id=lease.lease_id, hard_killed=False,
       ))
   ```

5. **Expiry watcher must skip SUSPENDED leases**: The background lease expiry watcher (7.2.3) must NOT expire leases with status=SUSPENDED. Only ACTIVE leases count down:

   ```python
   # In expiry watcher loop:
   for lease in active_leases:
       if lease.status == LeaseStatus.SUSPENDED:
           continue  # TTL paused, skip
       if lease.is_expired():
           await self._expire_lease(lease)
   ```

6. **Wire M6's scan_for_recovery**: On startup, if a lease is found in SUSPENDED state (persisted via TaskStateEntry), verify corresponding HILSubTask exists. If HILSubTask is missing or timed out, cancel the lease.

7. Add test: dispatch task -> HITL suspension -> verify worker released, lease SUSPENDED -> resume -> verify new worker acquired, lease ACTIVE -> complete. Also: dispatch task -> HITL suspension -> timeout fires -> verify lease CANCELLED, no orphan worker.

**Files to modify:**

- `poc/k1_poc/protocols/lease.py` (LeaseStatus.SUSPENDED, suspend(), resume() methods)
- `poc/k1_poc/demo/coordinator.py` (suspension/resume wiring in consumer)
- `poc/k1_poc/kernel/bootstrap.py` (same wiring for kernel consumer)
- `poc/k1_poc/actors/pool.py` (release_worker with reason="suspended", acquire for resumed task)
- `poc/k1_poc/fsm/controller.py` (HITL timeout handler uses lease.cancel())

**Dependency:** E7.2.1 (TaskLease), E7.2.3 (expiry watcher), 7.5.2 (pool wired into consumers), 7.5.3 (cancel token unification), M6 6.1.1 (HILSubTask), M6 6.3.3 (HITL timeout), M6 6.4.2 (scan_for_recovery)

**Acceptance:**

- Lease transitions to SUSPENDED when HITL suspends task (TTL paused)
- Worker slot released during suspension (pool capacity recovered)
- Resume acquires new worker slot and reactivates lease
- SAME CancellationToken used across suspension/resume (7.5.3 guarantee)
- HITL timeout cancels SUSPENDED lease without orphan worker
- Expiry watcher skips SUSPENDED leases
- scan_for_recovery handles SUSPENDED leases found at startup
- BackPoolWorkerReleasedEvent includes release_reason="suspended" for observability

---

#### 7.5.6 -- Wire M5 ConversationArbiter + RunningTaskHandle to BackPool-aware task tracking

**Problem:** M5's ConversationArbiter (5.2.1-5.2.5) makes decisions based on `InflightContext` which reads from `_running_tasks: dict[str, RunningTaskHandle]`. M7's BackPool replaces the task tracking model: tasks are now managed by pool workers with leases. Multiple M5 mechanisms must be updated:

1. **InflightContext must include pool state**: M5's `build_inflight_context()` (5.5.2) reads active tasks from `_running_tasks`. It must now also include pool utilization (active_workers/pool_size) and lease deadlines for capacity-aware arbiter decisions.
2. **RunningTaskHandle.cancel() must route through lease token**: M5's `_handle_arbiter_cancel` (5.2.2) calls `handle.cancel()`. With M7, this must cancel the lease's CancellationToken (7.5.3 already wires this, but RunningTaskHandle must delegate).
3. **RunningTaskHandle.inject_message() must target pool worker**: M5's `_handle_arbiter_modify` (5.2.3) injects a message into the running react_loop. With M7, the message must reach the correct pool worker's react_loop (identified by worker_id).
4. **PARALLEL_NEW must check pool capacity**: M5's `_handle_arbiter_parallel_new` (5.2.5) creates a new task alongside the running one. With M7, this requires a free worker slot in BackPool. If pool is full, PARALLEL_NEW must DEFER.

**What to do:**

1. **Extend InflightContext with pool state**:

   ```python
   @dataclass
   class InflightContext:
       # ... existing M5 fields ...
       pool_active_workers: int = 0     # NEW: BackPool utilization
       pool_size: int = 3               # NEW: BackPool capacity
       pool_available: int = 3          # NEW: free worker slots
       lease_deadlines: dict[str, int] = field(default_factory=dict)  # task_id -> expires_at_ns
   ```

2. **Wire build_inflight_context to read BackPool**:

   ```python
   # In build_inflight_context():
   pool_state = back_pool.get_pool_state()  # {active: N, size: M, workers: [...]}
   context.pool_active_workers = pool_state.active
   context.pool_size = pool_state.size
   context.pool_available = pool_state.size - pool_state.active
   context.lease_deadlines = {
       w.task_id: w.lease.expires_at_ns
       for w in pool_state.workers if w.lease
   }
   ```

3. **RunningTaskHandle delegates to BackPool**: Instead of maintaining a separate `_running_tasks` dict, RunningTaskHandle becomes a thin wrapper over BackPool worker state:

   ```python
   class RunningTaskHandle:
       def __init__(self, task_id: str, back_pool: BackPool):
           self._task_id = task_id
           self._back_pool = back_pool

       def cancel(self):
           worker = self._back_pool.get_worker_for_task(self._task_id)
           if worker:
               worker.lease.cancellation_token.cancel()

       async def inject_message(self, message: str):
           worker = self._back_pool.get_worker_for_task(self._task_id)
           if worker:
               await worker.inject_message(message)
   ```

4. **PARALLEL_NEW capacity check**:

   ```python
   # In _handle_arbiter_parallel_new():
   if self._back_pool.pool_available() == 0:
       # No free worker slot -- cannot run parallel task
       self._ledger_append(ArbiterDeferredEvent(
           task_id=new_task_id, reason="pool_full",
           pool_active=self._back_pool.active_count(),
           pool_size=self._back_pool.config.pool_size,
       ))
       return ArbiterDecision.DEFER  # Downgrade PARALLEL_NEW to DEFER
   ```

5. **Wire device_id tracking**: M5's device_id on MetaSection/ToolContext (5.5.6) is per-envelope. With BackPool, each worker_slot must carry the device_id from the original dispatch envelope so that cancel/modify from a different device can be validated via `resolve_device_conflict()`.

6. Add test: 3 tasks active (pool full) -> new intent arrives -> arbiter classifies as PARALLEL_NEW -> verify downgrade to DEFER with ArbiterDeferredEvent in ledger. Also: active task -> arbiter cancel -> verify lease.cancellation_token.cancel() fires -> verify worker react_loop sees it.

**Files to modify:**

- `poc/k1_poc/protocols/arbiter.py` (InflightContext pool fields, PARALLEL_NEW capacity check)
- `poc/k1_poc/fsm/controller.py` (build_inflight_context reads BackPool, RunningTaskHandle delegates to pool)
- `poc/k1_poc/events/` (ArbiterDeferredEvent if not already present)

**Dependency:** 7.5.2 (BackPool wired into consumers), 7.5.3 (cancel token unification), M5 5.2.1-5.2.5 (arbiter decisions), M5 5.5.2 (InflightContext), M5 5.5.4 (RunningTaskHandle)

**Acceptance:**

- InflightContext includes pool_active_workers, pool_size, pool_available, lease_deadlines
- build_inflight_context reads from BackPool (not stale _running_tasks)
- RunningTaskHandle.cancel() routes through lease.cancellation_token
- RunningTaskHandle.inject_message() targets correct pool worker
- PARALLEL_NEW downgrades to DEFER when pool is full (with ledger event)
- device_id carried on worker_slot for cross-device conflict resolution
- Arbiter decisions are capacity-aware (pool utilization visible)

---

#### 7.5.7 -- Extend test fixtures: create_wired_fsm with BackPool + Lease + ReadyQueue

**Problem:** E1.4-E6.5 incrementally built `create_wired_fsm()` with keyword arguments for each subsystem. M7 adds three new subsystems (BackPool, TaskLease, ReadyQueue) that must be available in test fixtures. Without fixture support, every M7 integration test must manually construct and wire these components -- leading to inconsistent test setups and missed wiring.

**What to do:**

1. Extend `create_wired_fsm()` with M7 parameters:

   ```python
   def create_wired_fsm(
       # ... existing M1-M6 params ...
       with_ledger=False,
       with_dead_letter_consumer=False,
       with_cancel_tokens=False,
       with_ss_binding=False,
       with_writer_port=False,
       with_arbiter=False,
       with_hitl=False,
       # NEW M7 params:
       with_back_pool=False,       # Creates BackPool + BackPoolConfig
       pool_size=3,                # Override default pool_size
       with_lease=False,           # Creates TaskLease infrastructure + expiry watcher
       lease_ttl_s=300,            # Override default lease TTL
       with_ready_queue=False,     # Creates ReadyQueue for dependency ordering
       with_topic_router=False,    # Creates BackTopicRouter with dispatch/resume/cancel routing
   ) -> WiredFSMContext:
   ```

2. When `with_back_pool=True`:
   - Create `BackPoolConfig(pool_size=pool_size, lease_ttl_s=lease_ttl_s)`
   - Create `BackPool(config)`
   - Attach to FSM controller
   - Implies `with_cancel_tokens=True` (pool workers need cancel tokens)

3. When `with_lease=True`:
   - Implies `with_back_pool=True` (leases require pool workers)
   - Enable lease expiry watcher (background task)
   - Wire expiry -> cancel token propagation

4. When `with_ready_queue=True`:
   - Create `ReadyQueue()`
   - Wire into FSM's `_on_task_complete` -> `notify_completed()`
   - Wire into FSM's `_on_task_dispatch` -> dependency check

5. When `with_topic_router=True`:
   - Create `BackTopicRouter` with standard routing table
   - Implies `with_back_pool=True` (router dispatches to pool workers)

6. Add convenience combination:

   ```python
   # Full M7 wiring (all subsystems):
   ctx = create_wired_fsm(
       with_back_pool=True,
       with_lease=True,
       with_ready_queue=True,
       with_topic_router=True,
       with_hitl=True,        # M6
       with_arbiter=True,     # M5
       with_ss_binding=True,  # M4
   )
   ```

7. Return pool, lease, queue, router on `WiredFSMContext` for test access:

   ```python
   @dataclass
   class WiredFSMContext:
       # ... existing fields ...
       back_pool: BackPool | None = None
       ready_queue: ReadyQueue | None = None
       topic_router: BackTopicRouter | None = None
   ```

**Files to modify:**

- `tests/poc/conftest.py` or `tests/poc/fixtures.py` (create_wired_fsm extension)

**Dependency:** E7.1.2 (BackPool), E7.2.1 (TaskLease), E7.3.1 (BackTopicRouter), E7.4.1 (ReadyQueue), 7.5.1-7.5.6 (all wiring issues)

**Acceptance:**

- `create_wired_fsm(with_back_pool=True)` creates fully wired BackPool
- `with_lease=True` implies `with_back_pool=True` (no orphan leases)
- `with_ready_queue=True` wires into FSM completion path
- `with_topic_router=True` creates standard 3-handler routing table
- All M1-M6 fixture params still work unchanged
- WiredFSMContext exposes pool, queue, router for test assertions
- Pool, lease, queue, router are properly torn down in fixture cleanup

---

#### 7.5.8 -- Backward compatibility regression: 12 tests verifying M1-M6 wiring survives M7 refactoring

**Problem:** M7 makes deep changes to the task execution model: BackPool replaces single asyncio.create_task, BackTopicRouter replaces hardcoded back_handler dispatch, TaskLease replaces ad-hoc cancel tracking, ReadyQueue intercepts task dispatch for dependency ordering. Each of these changes touches code paths that M1-M6 wiring depends on. Without explicit regression tests, M7 refactoring could silently break:

- M1 ledger recording (does _ledger_append still fire at all 11+ points?)
- M2 guard table dispatch (does pool acquisition envelope pass guard_dispatch?)
- M3 cancel token propagation (does the unified token still work for non-pool paths?)
- M4 TaskBridge.complete_task (does it still sync SS before ReadyQueue notification?)
- M5 arbiter decisions (does InflightContext still populate correctly?)
- M6 HITL lifecycle (does suspension/resume work through pool?)

**What to do:**

1. Create `tests/poc/test_m07_wiring_regression.py` with 12 tests:

   **Test 1: M1 ledger records pool/lease events**
   - Boot with full M7 wiring
   - Dispatch task -> acquire worker -> create lease -> complete -> release
   - Verify ledger contains: TaskLeasedEvent, BackPoolWorkerAcquiredEvent, BackPoolWorkerReleasedEvent in correct order

   **Test 2: M2 guard table allows pool/lease topics**
   - Dispatch task.leased.v1, backpool.worker.acquired, backpool.worker.released envelopes
   - Verify none are dead-lettered
   - Verify FULL_GUARD_TABLE has entries for all 3 topics in correct states

   **Test 3: M3 cancel token is same object across FSM, lease, and react_loop**
   - Dispatch task, capture FSM's _cancel_tokens[task_id]
   - Verify it is the SAME object as lease.cancellation_token
   - Cancel via FSM -> verify react_loop's cancellation_check returns True
   - Cancel via lease -> verify FSM's token.is_cancelled is True

   **Test 4: M4 TaskBridge.complete_task runs BEFORE ReadyQueue.notify_completed**
   - Dispatch task A, dispatch task B (depends_on A)
   - Complete A
   - In ReadyQueue.notify_completed callback, verify SS task_state for A shows status=COMPLETED
   - Verify B's dispatch sees A's completed artifacts on SS

   **Test 5: M5 InflightContext reflects pool state**
   - Dispatch 2 tasks (pool_size=3)
   - Build InflightContext
   - Verify pool_active_workers=2, pool_size=3, pool_available=1
   - Verify lease_deadlines has 2 entries

   **Test 6: M5 arbiter cancel routes through lease token**
   - Dispatch task, get RunningTaskHandle
   - Call handle.cancel()
   - Verify lease.cancellation_token.is_cancelled is True
   - Verify BackPool worker receives cooperative cancel

   **Test 7: M6 HITL suspension preserves lease, releases worker**
   - Dispatch task -> HITL suspension
   - Verify lease.status == SUSPENDED
   - Verify pool worker slot is free (available count increased)
   - Verify lease TTL is paused (expiry watcher skips)

   **Test 8: M6 HITL resume re-acquires worker with same cancel token**
   - Dispatch task -> HITL suspension -> resume
   - Verify new worker_slot acquired
   - Verify back_resume_handler receives SAME CancellationToken
   - Verify lease.status == ACTIVE again

   **Test 9: M6 HITL timeout cancels SUSPENDED lease**
   - Dispatch task -> HITL suspension -> timeout fires
   - Verify lease.status == CANCELLED
   - Verify lease.cancellation_token.is_cancelled is True
   - Verify no orphan worker (already released on suspension)

   **Test 10: ReadyQueue dependency ordering with M2 guard table**
   - Dispatch task A, dispatch task B (depends_on A)
   - Verify B does NOT appear in BackPool (still in queue)
   - Complete A
   - Verify B auto-dispatches through _on_task_dispatch (full guard table path)
   - Verify TaskDeferredEvent and TaskLeasedEvent for B in ledger

   **Test 11: BackTopicRouter dispatches resume to back_resume_handler**
   - Create BackTopicRouter with standard routing table
   - Route envelope with topic=task.resume.v1
   - Verify handler_fn is back_resume_handler (not back_handler)
   - Route envelope with topic=task.cancel.v1
   - Verify handler_fn is back_cancel_handler

   **Test 12: Pool full + PARALLEL_NEW downgrades to DEFER**
   - Set pool_size=2, dispatch 2 tasks (pool full)
   - New intent -> arbiter classifies PARALLEL_NEW
   - Verify downgrade to DEFER
   - Verify ArbiterDeferredEvent in ledger with reason="pool_full"

2. Each test uses `create_wired_fsm(with_back_pool=True, with_lease=True, with_ready_queue=True, with_topic_router=True, with_hitl=True, with_arbiter=True, with_ss_binding=True)` from updated fixtures (7.5.7).

**Files to create:**

- `tests/poc/test_m07_wiring_regression.py`

**Dependency:** 7.5.1-7.5.7 (all wiring issues), M1-M6 regression test patterns

**Acceptance:**

- All 12 regression tests pass
- M6 `test_m06_wiring_regression.py` tests still pass after M7 changes
- M5 `test_m05_wiring_regression.py` tests still pass after M7 changes
- Pool/lease events flow through guard table without dead-letters
- Cancel token unification verified across FSM, lease, and react_loop
- ReadyQueue dependency ordering integrates with TaskBridge completion
- HITL suspension/resume interacts correctly with pool lifecycle
- Arbiter capacity-aware decisions reflect real pool state

---

#### 7.5.9 -- Full regression: demo smoke test with BackPool + Task Lease + Dependency Ordering

**Problem:** M7 replaces the single-worker Back execution model with a parallel pool, lease-based lifecycle, topic-routed dispatch, and dependency-ordered queuing. The demo web app must exercise the complete pool lifecycle including concurrent execution, lease management, dependency ordering, topic routing, cancel propagation, and interaction with M6 HITL.

**What to do:**

1. Create `tests/poc/test_m07_demo_smoke.py`:

   **Scenario A: Concurrent task execution in BackPool**
   - Boot kernel with full M7 wiring (pool_size=3)
   - Dispatch task A "find Italian restaurants in Napa"
   - Dispatch task B "check weather in Napa" (no dependency)
   - Verify: both tasks get different worker_ids
   - Verify: both react_loops run concurrently (asyncio.Task per worker)
   - Verify: BackPoolWorkerAcquiredEvent x2 in ledger with different worker_ids
   - Verify: both tasks complete independently
   - Verify: BackPoolWorkerReleasedEvent x2 in ledger with release_reason="completed"
   - Verify: pool utilization gauge shows 0 after both complete

   **Scenario B: Task Lease lifecycle**
   - Boot kernel, dispatch task with lease_ttl_s=5 (short for test)
   - Verify: TaskLeasedEvent in ledger with correct TTL
   - Verify: lease.status == ACTIVE
   - Complete task within TTL
   - Verify: lease.status == RELEASED
   - Verify: no TaskLeaseExpiredEvent in ledger

   **Scenario C: Lease expiry auto-cancel**
   - Boot kernel, dispatch task with lease_ttl_s=2 (very short)
   - Simulate slow Back LLM (react_loop takes > 2s)
   - Verify: lease expiry watcher fires
   - Verify: lease.cancellation_token.is_cancelled is True
   - Verify: react_loop cooperative cancel at next iteration check
   - Verify: TaskLeaseExpiredEvent in ledger with hard_killed=False (cooperative succeeded)
   - Verify: BackPoolWorkerReleasedEvent with release_reason="lease_expired"

   **Scenario D: Dependency ordering via ReadyQueue**
   - Boot kernel, dispatch task A "create restaurant reservation"
   - Dispatch task B "send confirmation email" (depends_on=task_A)
   - Verify: task B is in ReadyQueue (NOT dispatched to BackPool)
   - Verify: TaskDeferredEvent in ledger for task B
   - Complete task A
   - Verify: ReadyQueue auto-dispatches task B
   - Verify: task B gets worker_slot AFTER A's worker is released
   - Verify: task B's Back LLM sees A's completed artifacts on SS
   - Verify: Ledger order: TaskLeased(A) -> TaskComplete(A) -> TaskDeferred(B) -> TaskLeased(B) -> TaskComplete(B)

   **Scenario E: Topic routing -- cancel reaches correct handler**
   - Boot kernel, dispatch task
   - Verify: BackTopicRouter routes task.dispatch.v1 to back_handler
   - Send task.cancel.v1 for the running task
   - Verify: BackTopicRouter routes to back_cancel_handler (not back_handler)
   - Verify: cancel handler sets lease.cancellation_token.cancel()
   - Verify: react_loop terminates cooperatively
   - Verify: BackPoolWorkerReleasedEvent with release_reason="cancelled"

   **Scenario F: HITL suspension interacts with pool lifecycle**
   - Boot kernel (pool_size=2), dispatch task A, task A triggers HITL
   - Verify: worker released, lease SUSPENDED, pool has 1 free slot
   - Dispatch task B (uses free slot)
   - Verify: task B runs concurrently while task A awaits human
   - Resolve HITL for task A
   - Verify: task A acquires new worker slot (may need to wait if pool full)
   - Verify: back_resume_handler receives same CancellationToken
   - Verify: both tasks complete
   - Verify: Ledger shows full lifecycle: leased -> suspended -> resumed -> completed for A

2. Add demo health check assertions:

   ```python
   # Health check should report:
   assert health["backpool_wired"] is True
   assert health["backpool_pool_size"] == 3
   assert health["backpool_active_workers"] == 0  # idle
   assert health["topic_router_wired"] is True
   assert health["topic_router_routes"] == ["task.dispatch.v1", "task.resume.v1", "task.cancel.v1"]
   assert health["ready_queue_depth"] == 0
   assert health["active_leases"] == 0
   # All M1-M6 health checks still pass
   assert health["ledger_ok"] is True
   assert health["dead_letter_count"] == 0
   assert health["hitl_wired"] is True
   assert health["arbiter_wired"] is True
   assert health["writer_port_wired"] is True
   ```

**Files to create:**

- `tests/poc/test_m07_demo_smoke.py`

**Dependency:** 7.5.1-7.5.8 (all wiring and regression), M6 6.5.9 (demo smoke pattern)

**Acceptance:**

- All 6 scenarios pass
- Concurrent task execution verified with different worker_ids
- Lease lifecycle exercised: create -> active -> released/expired
- Dependency ordering holds task B until task A completes
- Topic routing dispatches resume/cancel to correct handlers (not generic back_handler)
- HITL suspension releases worker, resume re-acquires worker
- Health check reports pool, router, queue, lease status
- All previous demo smoke tests (M2, M3, M4, M5, M6) still pass

---

### M7 Touchpoint Matrix: What M8-M12 Inherit from M7

| Milestone | M7 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M8** (Weave Policy) | BackPool pressure (active_workers/pool_size ratio) | Adaptive weave policy considers pool pressure before scheduling proactive content. High pool utilization (>80%) suppresses non-urgent weave batches. Pool pressure is a first-class input to the weave scheduling function. |
| **M8** (Weave Policy) | TaskLease.expires_at_ns | Weave scheduler uses lease deadlines to estimate when workers will free up. Short remaining lease TTL suggests imminent completion -- weave can prepare batch for delivery at task completion. |
| **M8** (Weave Policy) | BackTopicRouter routing table | Weave delivery results (proactive messages) routed through same topic infrastructure. New topic `weave.batch.v1` goes through guard table. Router extensible for weave-specific handlers. |
| **M8** (Weave Policy) | ReadyQueue depth | Weave urgency downranked when ReadyQueue has pending dependent tasks (user-initiated work takes priority over proactive content). Queue depth is input to weave urgency scoring. |
| **M9** (Crash Recovery) | BackPool worker state serialization | M9's WAL (write-ahead log) must capture active pool workers and their leases at checkpoint time. On recovery, BackPool.restore_from_checkpoint() recreates worker/lease state. Orphan workers without WAL entries are force-released. |
| **M9** (Crash Recovery) | TaskLease.status (ACTIVE/SUSPENDED/CANCELLED) | M9 recovery inspects lease status: ACTIVE leases with expired TTL -> auto-cancel. SUSPENDED leases -> check HILSubTask timeout. CANCELLED leases -> confirm task marked FAILED/CANCELLED. |
| **M9** (Crash Recovery) | ReadyQueue persistence | M9 persists ReadyQueue state in WAL. On recovery, deferred tasks are re-enqueued. Dependencies re-validated against completed task set. Circular dependencies detected pre-crash remain detected post-crash. |
| **M10** (UltraBERT) | BackPool worker isolation | UltraBERT's larger context window does not change pool isolation model. Each worker still gets its own SS snapshot. UltraBERT may use more tokens per iteration but same react_loop structure. Pool_size tuning may change for UltraBERT (fewer workers needed due to better per-task quality). |
| **M10** (UltraBERT) | TaskLease.renewal for long-running tasks | UltraBERT's improved reasoning may reduce iteration count, making lease renewal less frequent. But complex multi-step tasks may INCREASE lease duration. Renewal policy unchanged; lease_ttl_s may be tuned per-model. |
| **M10** (UltraBERT) | BackTopicRouter handler registration | UltraBERT-specific back_handler may be registered in router (different model, different handler logic). Router's handler_fn is a function reference -- swapping back_handler to ultrabert_back_handler is config-driven. |
| **M11** (Observability) | BackPool metrics (worker acquired/released, utilization gauge) | Full pool dashboard: active workers over time, acquisition latency histogram, release reason distribution, pool saturation alerts. P99 worker acquisition latency SLA. |
| **M11** (Observability) | TaskLease lifecycle events (leased/expired/renewed) | Lease dashboard: active leases, expiry rate, renewal rate, average lease duration. Alert on high expiry rate (suggests lease_ttl_s too short or Back LLM too slow). |
| **M11** (Observability) | ReadyQueue depth and wait time | Queue dashboard: pending tasks, average wait time, dependency chain length distribution. Alert on queue depth > N (suggests task ordering bottleneck). |
| **M11** (Observability) | BackTopicRouter dispatch counts | Router dashboard: dispatch count per topic, routing errors, late-envelope discard rate. Verify resume/cancel topics are actually used (not zero). |
| **M12** (Chaos Tests) | BackPool under rapid acquire/release | Chaos: rapid pool cycling (acquire-release-acquire) under load. Verify no worker slot leaks, no orphan tasks, pool size invariant maintained. |
| **M12** (Chaos Tests) | TaskLease expiry under concurrent cancels | Chaos: lease expiry fires simultaneously with arbiter cancel and HITL timeout. Verify only ONE cancellation path wins (idempotent cancel). No double-free of worker slot. |
| **M12** (Chaos Tests) | ReadyQueue under circular + deep dependency chains | Chaos: 10-deep dependency chain with intermediate failures. Verify ReadyQueue correctly fails dependents of failed tasks. Verify no infinite loops in notify_completed chain. |
| **M12** (Chaos Tests) | BackTopicRouter under unknown topics | Chaos: inject envelopes with unknown topics into Back mailbox. Verify router sends to dead-letter (not crash). Verify late-envelope discard for completed tasks under rapid topic injection. |

**Total: 16 issues across 4 epics (E7.1-E7.4) + 9 issues in E7.5 wiring = 25 issues across 5 epics.**

---

## M8: Adaptive Weave Policy

**Goal:** Replace the fixed 500ms weave batch window with a context-aware
adaptive policy that considers task urgency, user activity state, emotional
context, pending result profile, and BackPool pressure before deciding HOW
and WHEN to deliver async results to the user. Introduce digest mode for
batching low-urgency results into summarized notifications. Retain fixed
500ms as a deterministic fallback when signals are unavailable.

**Gate:** Every task.complete triggers a WeavePolicy.decide() call that
outputs one of {IMMEDIATE, BATCH, DEFER, DIGEST} with a dynamic batch
window and reasoning string. The decision is emitted as
conversation.weave.decided (M1 schema) before the FSM acts. User-typing
signal suppresses non-urgent weave delivery. Digest mode compresses 3+
low-urgency results into a one-paragraph summary. Fixed batching activates
automatically when signal collection fails.

**Depends on:** M5 (Arbiter provides Phase 1 signals), M7 (BackPool
emits pool utilization metrics).

### Why Weaving Is Hard (Code Audit Findings)

**Current weave path (end-to-end):**

```
task.complete arrives
  -> FSM _on_task_complete (controller.py L1063-1175)
     -> state check via hardcoded if/elif
     -> LISTENING: PROACTIVE_WAKE -> DELIVERING -> Front PRESENT mode
     -> COMPANIONING: -> DELIVERING -> Front PRESENT mode
        (if FrontLock busy: queue in pending_results)
     -> Everything else: queue in pending_results
  -> _on_response_final (controller.py L1472-1700)
     -> check pending_results
     -> if non-empty: -> WEAVING -> _schedule_weave_flush
        -> 500ms asyncio.sleep
        -> _flush_weave_now -> drain_results -> _build_weave_envelope
        -> try_deliver -> deliver_to_front
     -> Front receives WEAVE mode envelope
        -> scenario_template: "While you were chatting, {result_count}
           task(s) completed: {results_summary}"
        -> prompt: WEAVE_PROTOCOL ("respond to topic FIRST, bridge")
        -> tools: update_beliefs, update_narrative (no dispatch, no recall)
        -> budget: 3 iterations (crisis: 2)
        -> LLM generates woven response
  -> _on_response_final again (for weave response)
     -> if more pending_results: loop (WEAVING -> WEAVING)
     -> else: LISTENING
```

**Problem 1 -- Decision is state-based, not context-aware:**

`get_weave_action(fsm_state)` in weave_state.py L81-95 returns a static
WeaveAction based ONLY on the current FSM state. It ignores:

| Missing Signal | Why It Matters | Code Location |
|----------------|---------------|---------------|
| Task urgency | A booking-about-to-expire should weave immediately; a weather check can wait. | dispatch_task urgency field exists (implementations.py L610) but never flows into weave decision |
| User typing | Interrupting mid-sentence is jarring; waiting until user pauses is natural. | RhythmController has typing_indicator as OUTPUT only (rhythm_controller.py L39). No INPUT path from UI. |
| Pending count profile | 1 result = inline weave. 5 low-urgency results = digest summary. | pending_results is a deque (turn_state.py L44) but only checked for empty/non-empty, never profiled |
| Affect band | User in crisis (grief, anger) should not be interrupted with trivial results. | affective_now section exists but weave_state.py never reads it |
| Idle duration | User idle 30s = eager weave. User mid-paragraph = defer. | No idle tracker exists |
| BackPool utilization | Pool saturated = batch more aggressively to reduce concurrent Front invocations | M7 events not yet wired |

**Problem 2 -- No digest mode:**

WB 3.D says "immediate weave vs delayed bundle vs summarized digest."
Current system has IMMEDIATE and QUEUE_WEAVE (500ms batch). No mode
exists where 5 low-urgency results are compressed into: "While you
were busy, I handled a few things: weather looks clear tomorrow, the
grocery order went through, and your library books are renewed." Instead,
the LLM receives 5 separate [ASYNC RESULT ARRIVED] blocks and must
synthesize them with only 3 iterations (2 in crisis) -- often producing
a wall of text or ignoring later results.

**Problem 3 -- Fixed 500ms is wrong for both extremes:**

| Scenario | 500ms behavior | Correct behavior |
|----------|---------------|-----------------|
| Booking expires in 2 minutes | 500ms delay is fine | IMMEDIATE (0ms) |
| User typing a long message | 500ms fires while user is mid-sentence; weave interrupts their flow | DEFER until user sends or pauses |
| 5 weather checks finish in 3s window | First completes at t=0, window fires at t=500ms with 1 result, second at t=600ms starts new window... user gets 2 separate weave messages | DIGEST with 5s window to catch all 5 results |
| User idle for 60s, 1 result arrives | 500ms delay is unnecessarily long | IMMEDIATE (user is clearly waiting) |

**Problem 4 -- Emotional dissonance unaddressed:**

The WEAVE_PROTOCOL prompt (sections.py L304-315) says "Respond to user's
CURRENT topic first, then naturally transition." But if the user's current
topic is grief ("my dad passed away last week") and the async result is
"your hotel in Napa is booked!", the LLM must thread an extremely delicate
needle. No prompt guidance addresses emotional dissonance between the
current thread affect and the async result tone. The LLM often produces
jarring transitions like "I'm so sorry about your father... and by the
way, your hotel is confirmed!"

**Problem 5 -- Multi-result ordering is FIFO:**

`pending_results` is a deque (turn_state.py L44). Results are drained in
insertion order (FIFO = completion order). No urgency-based or
domain-grouped ordering. If a hotel booking (urgent) and a weather check
(trivial) complete in that order, the LLM presents them in that order.
But if 3 travel results and 2 health results complete interleaved, the
LLM should group them by domain for a coherent narrative.

**Problem 6 -- WeaveBatcher flush callback is vestigial:**

In bootstrap.py L231-233, the flush_fn callback just logs:

```python
async def _weave_flush(results: list) -> None:
    logger.info("WeaveBatcher flush: %d results", len(results))
```

The actual delivery goes through FSM._flush_weave_now -> drain_results ->
_build_weave_envelope -> deliver_to_front. The WeaveBatcher's flush
callback is NOT in the delivery path. The WeaveBatcher and the FSM weave
flush are two separate mechanisms that overlap but do not integrate
cleanly. The FSM's_schedule_weave_flush uses its own 500ms timer
(independent of WeaveBatcher's timer).

### M8 LLM Interaction Model

| Actor | Current Behavior | Problem | Adaptive Behavior |
|-------|-----------------|---------|-------------------|
| Front (WEAVE, 1 result) | Receives 1 [ASYNC RESULT ARRIVED] block + current_thread. LLM bridges topic and presents result. 3 iterations, 2 tools. | No urgency signal. LLM does not know if result is time-critical. Same prompt for trivial weather check and urgent booking expiry. | WeavePolicy adds urgency_label to scenario_data. High urgency: "URGENT -- present this result prominently." Low urgency: "This is informational -- weave lightly." |
| Front (WEAVE, 3+ results) | Receives N [ASYNC RESULT ARRIVED] blocks. LLM tries to cover all N in one response with 3 iterations. Often ignores later results or produces wall-of-text. | No grouping, no digest. 5 results at 3 iterations = ~0.6 iterations per result. Budget exhaustion forces truncation. | DIGEST mode pre-synthesizes results into 1-2 paragraph summary BEFORE sending to LLM. LLM receives a compressed payload, not N raw blocks. Alternatively, budget increased for digest (5 iterations). |
| Front (WEAVE, emotional dissonance) | Same WEAVE_PROTOCOL for all affect states. "Respond to topic FIRST, then bridge." | Grief + hotel confirmation = jarring. Crisis + trivial result = insensitive. | WeavePolicy checks affect_band. If negative valence > 0.5: DEFER non-urgent results. If crisis: only IMMEDIATE for safety-critical results. Add EMOTIONAL_DISSONANCE prompt section for non-deferred results in negative affect. |
| Front (WEAVE during typing) | No typing signal. 500ms fires regardless. User is mid-sentence when weave arrives. | User loses train of thought. Types "what I meant was--" then system interrupts with hotel results. | User-typing signal suppresses BATCH/DIGEST delivery. Only IMMEDIATE (urgent) results break through. Timer pauses while typing signal is active, resumes on silence. |

---

### E8.1 -- Weave Signal Collector

Source: WB 3.D, 10

**Rationale:** The adaptive policy needs input signals to make decisions.
Currently the weave decision reads ONLY the FSM state (weave_state.py
get_weave_action). No infrastructure exists to collect the 6 signals that
WB 3.D requires: urgency, user typing, conversational load, pending count,
affect, and pool utilization. This epic creates the signal collection layer
that feeds the decision engine (E8.2).

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 8.1.1 | Define WeaveSignal dataclass with fields: task_urgency (str: "critical", "normal", "low"), user_typing (bool), user_idle_ms (int, milliseconds since last user message), pending_count (int), pending_urgency_profile (dict mapping urgency -> count), affect_band (str from affective_now), affect_valence (float), backpool_utilization (float, 0.0-1.0 from M7), recent_weave_count (int, weaves in last 5 minutes), fsm_state (ConciergeState). Place in protocols/weave_policy.py. WeaveSignal.from_runtime() factory reads all sources atomically from SS + controller state + BackPool metrics. | WB 3.D | WeaveSignal is not visible to the LLM. It feeds the policy engine (E8.2) which determines what the LLM sees in the WEAVE prompt. But the signal quality directly determines prompt quality: if affect_valence is wrong, the LLM gets an emotional-dissonance scenario it cannot handle gracefully. |
| 8.1.2 | Add user_typing signal path. Define UserActivityTracker class with methods: on_typing_start(), on_typing_stop(), on_user_idle_tick(). User typing status comes from the UI layer via a new bus topic k1.ui.typing.v1 (RELAXED delivery, best-effort). FSM subscribes and updates the tracker. If no UI typing signal is available (headless mode, API-only), default to user_typing=False and user_idle_ms=time_since_last_user_input. Place tracker in protocols/weave_policy.py. | WB 3.D | When user_typing=True, non-urgent weave delivery is suppressed. The LLM is NOT invoked in WEAVE mode at all (the timer pauses). This prevents the worst UX failure: LLM responds with a weave message while user is composing their next message, and the user's message arrives AFTER the weave response, creating a confusing out-of-order conversation. |
| 8.1.3 | Add idle duration tracker. UserActivityTracker maintains last_user_input_ns (set on every user.input event in FSM_on_user_input). user_idle_ms = (now_ns - last_user_input_ns) / 1e6. Threshold constants: IDLE_EAGER_MS = 10000 (10s idle = eager delivery), IDLE_BATCH_MS = 3000 (3-10s = normal batch), TYPING_SUPPRESS_MS = 500 (typing detected within 500ms = suppress). These feed the decision table in E8.2. | WB 3.D | User idle 10+ seconds signals the user is waiting for a response or disengaged. Eager delivery (shorter batch window) is appropriate. User active within 3s signals mid-conversation -- batch window should be extended to avoid interruption. This is the primary timing lever for the adaptive policy. |
| 8.1.4 | Add pending result profiler. When FSM._on_task_complete queues a result in turn_state.pending_results, also record urgency from the original dispatch payload (implementations.py L610 urgency field flows through task_state to result metadata). WeaveSignal.pending_urgency_profile = {"critical": 1, "normal": 2, "low": 0} counted from queued results. If ANY result has urgency "critical" or "urgent", signal.has_critical = True. This requires extending enqueue_result (turn_state.py L50-78) to include urgency in the queued dict. | WB 3.D | If the pending queue contains 1 critical + 2 normal results, the policy should deliver the critical result immediately and batch the normals. Without urgency profiling, all 3 results get the same 500ms window regardless of time-sensitivity. The Front LLM cannot recover from this -- it does not know which result is urgent because the WEAVE scenario template does not include urgency labels. |
| 8.1.5 | Add affect-based weave gating. WeaveSignal.from_runtime() reads affective_now section (same path as Front: _get_affect_dict in actors/front.py L365-372). Extract valence, arousal, current_emotion. If valence < -0.5 (negative affect: grief, anger, frustration): set signal.emotional_gate = "suppress_trivial" -- only critical/urgent results should be woven. If current_emotion == "crisis" or safety_band == "RED": set signal.emotional_gate = "suppress_all_non_safety" -- only safety-critical results break through. If valence >= 0 (neutral/positive): signal.emotional_gate = "open" -- all results can be woven. | WB 3.D | Directly prevents the emotional dissonance problem. The LLM in WEAVE mode never sees "your hotel is booked!" while the user is expressing grief, because the policy suppresses non-urgent results when valence is negative. The deferred results accumulate and are delivered when the user's affect improves or explicitly asks "anything else happening?" |

---

### E8.2 -- Adaptive Weave Decision Engine

Source: WB 3.D, 12.2.C, 12.4.5

**Rationale:** The current decision is a static lookup table
(get_weave_action maps FSM state to WeaveAction). The adaptive engine
replaces this with a multi-signal decision function that produces a richer
outcome (5 decisions instead of 4) with a dynamic batch window and an
auditable reasoning string. The engine is a pure function:
(WeaveSignal) -> (WeaveDecision, window_ms, reasoning). No side effects.
Easy to test, easy to tune.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 8.2.1 | Define WeaveDecision enum with 5 values: IMMEDIATE (deliver now, 0ms window), BATCH (deliver after dynamic window, 200-5000ms), DEFER (hold until user sends next message or asks), DIGEST (accumulate for 10-30s then synthesize into summary), SUPPRESS (do not deliver -- result is stale, cancelled, or emotionally inappropriate). Add WeaveDecisionResult dataclass with: decision (WeaveDecision), window_ms (int, 0 for IMMEDIATE, dynamic for BATCH/DIGEST), reasoning (str, human-readable explanation), urgency_override (bool, True if critical urgency overrode normal policy), emotional_gate_applied (bool). Place in protocols/weave_policy.py. | WB 3.D | IMMEDIATE: Front LLM invoked instantly in WEAVE mode with urgency label. BATCH: same as current 500ms path but window is dynamic. DEFER: Front LLM is NOT invoked -- results held in queue until next user turn (woven into STANDARD response as async_results_context). DIGEST: Front LLM invoked in DIGEST sub-mode with pre-synthesized summary (reduced token cost). SUPPRESS: No LLM invocation, result is logged but not presented (cancelled task results, stale results). |
| 8.2.2 | Implement WeavePolicy.decide(signal: WeaveSignal) -> WeaveDecisionResult with priority-ordered decision table. Decision rules (first-match wins): (1) signal.fsm_state == LISTENING and signal.user_idle_ms > IDLE_EAGER_MS -> IMMEDIATE. (2) signal.has_critical and signal.emotional_gate == "open" -> IMMEDIATE. (3) signal.user_typing -> DEFER (suppress until typing stops, re-evaluate). (4) signal.emotional_gate == "suppress_all_non_safety" -> SUPPRESS. (5) signal.emotional_gate == "suppress_trivial" and not signal.has_critical -> DEFER. (6) signal.pending_count >= 3 and all low urgency -> DIGEST with window_ms = 15000. (7) signal.pending_count >= 1 and signal.user_idle_ms > IDLE_BATCH_MS -> BATCH with window_ms = max(200, 500 - signal.user_idle_ms/20). (8) signal.backpool_utilization > 0.8 -> BATCH with window_ms = 2000 (pool pressure, batch more). (9) default -> BATCH with window_ms = 500 (current fixed behavior). | WB 3.D, 12.2.C | This is the core decision logic. Each rule has a clear LLM consequence. Rule 3 (typing suppression) prevents the worst UX. Rule 4-5 (emotional gating) prevents dissonance. Rule 6 (digest) prevents token waste on 5+ low-urgency results. Rule 8 (pool pressure) prevents Front saturation when many tasks complete simultaneously. Rule 9 (default) preserves current behavior as fallback. |
| 8.2.3 | Add configurable policy weights in ConciergeConfig. New section: WeavePolicyConfig with fields: idle_eager_ms (int, default 10000), idle_batch_ms (int, default 3000), typing_suppress_ms (int, default 500), digest_threshold_count (int, default 3), digest_window_ms (int, default 15000), pool_pressure_threshold (float, default 0.8), pool_pressure_batch_ms (int, default 2000), default_batch_ms (int, default 500), max_batch_ms (int, default 5000), emotional_suppress_valence (float, default -0.5), max_consecutive_defers (int, default 5). max_consecutive_defers prevents infinite deferral -- if a result has been deferred 5 times, force BATCH delivery on the 6th evaluation. | WB 10 | All thresholds are configurable. Operators can tune for their user base: families with young children (shorter idle thresholds, more immediate), elderly users (longer windows, more batching), high-anxiety users (stronger emotional gating). No code changes needed for threshold tuning. |
| 8.2.4 | Emit conversation.weave.decided event (M1 schema: WeaveDecisionMade) after every WeavePolicy.decide() call. Payload: candidate_event_id (the task.complete envelope_id that triggered the decision), decision (WeaveDecision value), reason (the reasoning string), window_ms, fsm_state, signal_snapshot (serialized WeaveSignal for debugging). Publish on bus via build_weave_decided() builder (add to bus/builders.py). Topic: k1.conversation.weave.decided.v1 (RELAXED delivery). This makes every weave decision observable, auditable, and replayable. | WB 4 | No direct LLM impact. But enables post-hoc analysis: "why did the system deliver 3 separate weave messages instead of batching?" The reasoning string in the event answers this question. Critical for tuning the policy weights (8.2.3). |

---

### E8.3 -- Dynamic Batch Window + Digest Mode

Source: WB 3.D, 12.2.C

**Rationale:** The current 500ms window (WEAVE_BATCH_WINDOW_MS in
weave_batcher.py L42, controller.py L84) is used by both WeaveBatcher and
FSM._schedule_weave_flush independently. The adaptive policy produces a
dynamic window_ms per decision. This epic replaces the fixed constant with
the policy-driven window and adds the new DIGEST delivery mode where
multiple low-urgency results are pre-synthesized before reaching the Front
LLM.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 8.3.1 | Replace fixed WEAVE_BATCH_WINDOW_MS in_schedule_weave_flush with the dynamic window_ms from WeaveDecisionResult. Currently_flush_weave_after_delay (controller.py L1845) does `await asyncio.sleep(WEAVE_BATCH_WINDOW_MS / 1000)`. Change to accept window_ms parameter from the policy decision. If window_ms == 0 (IMMEDIATE), skip the asyncio.sleep and call_flush_weave_now directly. If window_ms > 0 (BATCH or DIGEST), use the policy-specified window. Store the active window_ms in the _weave_flush_task for cancellation/re-evaluation. | WB 12.2.C | For IMMEDIATE: Front LLM is invoked with zero delay after task.complete -- the user sees the result as fast as possible. For BATCH with 2000ms window: more results may accumulate, so the LLM receives a richer batch and produces one cohesive message instead of 2 separate weave messages. For DIGEST with 15s window: the LLM receives a pre-synthesized summary (fewer tokens, fewer iterations needed). |
| 8.3.2 | Implement DEFER delivery path. When WeavePolicy returns DEFER, do NOT schedule a flush timer. Instead, mark the pending results with deferred=True and a defer_count. On the NEXT user input (_on_user_input in controller.py L700-762), check for deferred results. If present, inject them into the Front STANDARD prompt as async_results_context (the scenario_data field that is currently always "" for STANDARD mode, see front.py L203). This means the LLM naturally mentions them: "Let me help with [your question]... and by the way, [deferred result]." No separate WEAVE invocation needed. Re-evaluate the WeavePolicy on each user input to check if the deferred results should still be deferred or can now be delivered. | WB 3.D | DEFER is the most natural weave mode for mid-conversation results. The Front LLM in STANDARD mode already has the full cognitive toolset (6 tools, 6 iterations). It can weave the deferred result into its normal response much more naturally than a separate WEAVE mode invocation with only 2 tools and 3 iterations. The user does not perceive a system interruption -- the result appears as part of the assistant's natural response. |
| 8.3.3 | Implement DIGEST delivery mode. When WeavePolicy returns DIGEST with window_ms=15000, start a digest accumulation timer. All results that arrive within the digest window are collected. When the timer fires, build a DigestPayload: (a) group results by domain (from task dispatch metadata), (b) sort groups by urgency (critical first), (c) generate a 1-2 sentence summary per group using a template (no LLM call -- deterministic string formatting). Deliver the DigestPayload to Front in WEAVE mode with a modified scenario template: "Here is a brief summary of {count} background tasks..." instead of N separate [ASYNC RESULT ARRIVED] blocks. Add DigestPayload dataclass to protocols/weave_policy.py. | WB 3.D | The Front LLM receives a condensed digest instead of N raw result blocks. With 5 results: current system sends ~500 tokens of raw results; digest sends ~150 tokens of pre-grouped summary. The LLM can process this in 1-2 iterations instead of struggling with 5 blocks in 3 iterations. Quality improves because the LLM is not forced to cover N results under budget pressure. |
| 8.3.4 | Add urgency label and emotional dissonance guidance to WEAVE scenario template. Extend SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE] (scenario_templates.py L51-59) to include: urgency_label (str: "URGENT -- present prominently" or "Informational -- weave lightly" or "Summary -- present as brief update"), emotional_context (str: "User affect is positive, standard weave" or "User affect is negative -- be gentle, acknowledge their state before presenting result"). This gives the Front LLM explicit guidance for the two hardest weave cases: time-critical results and emotionally dissonant results. | WB 3.D | **Highest LLM impact in M8.** Currently the WEAVE prompt gives zero guidance on urgency or emotional state. The LLM must infer both from context, and often fails (produces jarring transitions, buries urgent results, or ignores emotional tone). With explicit labels, the LLM can adapt: "I know this is a tough time, but I wanted to let you know your hotel is confirmed -- one less thing to worry about." vs "Great news -- your hotel is booked!" Same result, radically different delivery. |
| 8.3.5 | Add result ordering before weave delivery. When _flush_weave_now (controller.py L1850) drains pending_results, sort them before building the weave envelope: (a) critical urgency first, (b) then by domain group (cluster related results together), (c) within a domain group, by completion order (FIFO). This ordering feeds into the [ASYNC RESULT ARRIVED] blocks that the Front LLM receives. The LLM presents results in the order it receives them (the prompt says "batch them into one cohesive message" but does not say "reorder" -- so input ordering determines output ordering). | WB 3.D | Related results appear adjacent in the prompt, so the LLM naturally groups them: "On the travel front: hotel confirmed, restaurant reserved. For groceries: order placed, delivery Thursday." Without ordering, the LLM receives interleaved domains and produces less coherent responses. |

---

### E8.4 -- Policy Integration, Fallback, and Observability

Source: WB 12.2.C, 13.5

**Rationale:** The adaptive policy must be wired into the FSM weave path
(replacing the static get_weave_action call sites and the fixed 500ms
timer), with a deterministic fallback to the current behavior when signals
are unavailable or the policy raises an exception. Observability metrics
track weave quality so the policy weights can be tuned empirically.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 8.4.1 | Wire WeavePolicy into FSM _on_task_complete. Replace the hardcoded state-based routing (controller.py L1063-1175) with: (a) collect WeaveSignal.from_runtime(); (b) call WeavePolicy.decide(signal); (c) branch on decision: IMMEDIATE -> PROACTIVE_WAKE/DELIVERING (same as current LISTENING path), BATCH -> queue +_schedule_weave_flush(window_ms), DEFER -> queue with deferred=True (no timer), DIGEST -> queue +_schedule_digest_flush(window_ms), SUPPRESS -> discard result (log only). Preserve the same-turn-completion suppression logic (L1118-1140) -- it runs BEFORE the policy decision (same-turn results are never woven). | WB 12.2.C | This is the primary integration point. Without it, M8 is unused. With it, every task.complete goes through the adaptive policy. The FSM trace changes from `_on_task_complete -> static if/elif` to `_on_task_complete -> WeavePolicy.decide -> branch`. All downstream LLM behavior (WEAVE mode, STANDARD+deferred, digest) flows from this decision. |
| 8.4.2 | Wire WeavePolicy re-evaluation on user_typing signal change. When UserActivityTracker detects typing_start, re-evaluate any active BATCH timer. If the policy now returns DEFER (because user_typing=True), cancel the pending flush timer and mark results as deferred. When UserActivityTracker detects typing_stop (+ 500ms debounce), re-evaluate. If the policy now returns BATCH, schedule a new flush with the policy window. This creates a responsive loop: timer starts on task.complete, pauses on typing, resumes on silence. | WB 3.D | Prevents the worst UX failure: system delivers a weave message while user is composing their next message. The user sends their message, sees the weave response that appeared before their message, gets confused about message ordering. With typing suppression, the weave waits until the user finishes typing, then delivers. The conversation flows naturally. |
| 8.4.3 | Implement deterministic fallback mode. If WeaveSignal.from_runtime() raises any exception (missing SS section, BackPool not wired, etc.), catch the error, log a warning, and fall back to the current behavior: get_weave_action(fsm_state) + fixed 500ms window. If WeavePolicy.decide() raises, same fallback. The fallback path MUST produce identical behavior to the current M0-M7 weave path -- no regressions. Add a config flag: weave_policy_enabled (bool, default True). When False, always use fallback. This enables safe rollout: deploy M8 code with policy disabled, enable per-session for A/B testing. | WB 12.2.C | Fallback ensures the LLM experience is NEVER worse than current behavior. If the adaptive policy makes a bad decision (delivers too late, suppresses too aggressively), operators can disable it per-session without a code deploy. The LLM falls back to fixed 500ms WEAVE mode, which is functional if not optimal. |
| 8.4.4 | Add weave quality observability metrics. Track per-session: (a) weave_count (total WEAVE mode invocations), (b) weave_latency_ms (time from task.complete to weave delivery), (c) digest_count (total DIGEST invocations), (d) defer_count (total DEFER decisions, including re-evaluations), (e) suppress_count (total SUPPRESS decisions), (f) user_acknowledged_weave (bool, True if user's next message references the woven result -- heuristic: check if next user input contains task-related keywords). Emit as k1.metrics.weave.v1 event at session end. These metrics feed into post-hoc policy tuning (adjusting weights in 8.2.3). | WB 10 | No direct LLM impact. But enables data-driven tuning: "users acknowledge 80% of IMMEDIATE weaves but only 30% of BATCH weaves" suggests the batch window is too long. "defer_count averages 12 per session" suggests the emotional gate is too aggressive. Without metrics, the policy is tuned by guessing. |
| 8.4.5 | Consolidate WeaveBatcher and FSM weave flush into single pathway. Currently WeaveBatcher (protocols/weave_batcher.py) and FSM._schedule_weave_flush (controller.py L1819-1855) are independent mechanisms with separate timers. WeaveBatcher's flush_fn callback in bootstrap.py just logs (vestigial). Remove the vestigial WeaveBatcher flush_fn callback. Route all weave timing through the WeavePolicy-driven _schedule_weave_flush. WeaveBatcher retains its queue management role (pending/queued lists, front_busy gating) but delegates timing decisions to WeavePolicy. Rename WeaveBatcher to WeaveQueue to clarify its role as a queue, not a policy. | WB 12.2.C | No direct LLM impact. Eliminates a confusing code path where two independent timers (WeaveBatcher._flush_after_delay and FSM._flush_weave_after_delay) could theoretically race. Simplifies the mental model: WeaveQueue manages the queue, WeavePolicy decides when to flush, FSM executes the flush. |

---

### M8 Adaptive Weave ReAct Loop Interaction Audit

**Constraints derived from code reading (protocols/weave_batcher.py,
protocols/weave_state.py, fsm/controller.py, fsm/turn_state.py,
fsm/front_lock.py, actors/front.py, prompt/mode.py, prompt/sections.py,
prompt/scenario_templates.py, experience/rhythm_controller.py,
kernel/bootstrap.py):**

| # | Constraint | Code Evidence | M8 Implication |
|---|-----------|---------------|----------------|
| W1 | Current weave decision is a static function: get_weave_action(ConciergeState) -> WeaveAction. No signal inputs, no context, no reasoning. | weave_state.py L81-95 (STATE_ACTION_TABLE dict lookup) | E8.2 replaces this with WeavePolicy.decide(WeaveSignal) which is a multi-signal function. The static table becomes the fallback (E8.4.3). |
| W2 | WeaveBatcher and FSM weave flush are independent parallel mechanisms. WeaveBatcher has its own 500ms timer and flush callback. FSM has _schedule_weave_flush with its own 500ms timer. The WeaveBatcher flush_fn is vestigial (logs only). | weave_batcher.py L253-255 (_flush_after_delay), controller.py L1845-1846 (_flush_weave_after_delay), bootstrap.py L231-233 (flush_fn just logs) | E8.4.5 consolidates into single pathway. WeaveQueue (renamed) manages queue state. FSM manages timing via WeavePolicy. |
| W3 | Front WEAVE mode has only 2 tools (update_beliefs, update_narrative) and 3 iterations. This is intentionally constrained -- WEAVE should be fast and focused. | mode.py L96-98 (TOOL_ALLOWLIST[WEAVE]), mode.py L168 (MAX_ITERATIONS[WEAVE] = 3) | E8.3.2 (DEFER) bypasses WEAVE mode entirely -- deferred results go into STANDARD mode which has 8 tools and 6 iterations. This is MORE capable, not less. Digest mode (E8.3.3) keeps WEAVE budget but with compressed input. |
| W4 | WEAVE scenario template gives zero urgency or emotional guidance. Template just says "While you were chatting, {result_count} task(s) completed" + "{results_summary}" + "current_thread: {current_thread}". | scenario_templates.py L51-59 | E8.3.4 adds urgency_label and emotional_context to the template. The LLM gets explicit instructions on tone and priority. |
| W5 | FrontLock assigns weave.batch topic the same priority (P3=RESULT) as task.complete. User input is P1 (URGENT). During WEAVING, user input is queued in FrontLock and processed AFTER the current weave response completes. | front_lock.py L55 (TOPIC_PRIORITY: weave.batch -> PRIORITY_RESULT) | No change needed. P1 > P3 means user input always takes priority over weave delivery. This is correct -- user intent should never be blocked by a weave. The typing suppression in E8.4.2 prevents the race condition where weave fires right before user sends. |
| W6 | pending_results is a simple deque with no metadata beyond task_id, result dict, and envelope_id. No urgency, no domain, no completion timestamp accessible for ordering or profiling. | turn_state.py L66-76 (enqueue_result payload: task_id, result, envelope_id, parent_id, queued_at_ns) | E8.1.4 extends enqueue_result to include urgency from dispatch metadata. E8.3.5 sorts results before building the weave envelope. |
| W7 | The WEAVING -> WEAVING self-transition handles the case where more results arrive during a weave cycle. The FSM stays in WEAVING and re-flushes. But if the policy now says DEFER for the new results, the FSM should transition to LISTENING instead of re-flushing. | transition_table.py L93-95 (WEAVING: {FINAL_RESPONSE -> LISTENING, PENDING_NON_EMPTY -> WEAVING}) | E8.4.1 re-evaluates WeavePolicy on each re-flush decision. If the new results are DEFER (e.g., user started typing during the first weave), the FSM transitions to LISTENING instead of WEAVING. This requires updating the transition table to allow WEAVING -> LISTENING on a DEFER decision (already legal via FINAL_RESPONSE trigger). |
| W8 | The Front LLM in WEAVE mode reads affective_now via_get_affect_dict (front.py L365-372) but the WEAVE prompt sections do NOT include emotional calibration beyond EMOTIONAL_CALIB (generic). No WEAVE-specific emotional guidance exists. | sections.py L540-544 (WEAVE sections: IDENTITY, WEAVE_PROTOCOL, EMOTIONAL_CALIB) | E8.3.4 adds emotional_context to the scenario data. The existing EMOTIONAL_CALIB section provides base calibration; the new emotional_context gives weave-specific dissonance guidance. |

---

### Recommended Execution Order

1. **8.1.1** (WeaveSignal dataclass -- foundation for all policy inputs)
2. **8.2.1** (WeaveDecision enum + WeaveDecisionResult -- foundation for policy output)
3. **8.2.2** (WeavePolicy.decide() decision table -- core engine)
4. **8.2.3** (WeavePolicy config weights -- tunability)
5. **8.1.3** (idle duration tracker -- primary timing lever)
6. **8.1.4** (pending result profiler -- urgency flows into weave)
7. **8.1.5** (affect-based weave gating -- emotional safety)
8. **8.3.1** (dynamic batch window in _schedule_weave_flush)
9. **8.4.1** (wire WeavePolicy into FSM _on_task_complete -- primary integration)
10. **8.3.4** (urgency + emotional labels in WEAVE prompt -- highest LLM impact)
11. **8.3.5** (result ordering before weave delivery)
12. **8.3.2** (DEFER delivery path -- natural mid-conversation weave)
13. **8.3.3** (DIGEST mode -- compressed multi-result delivery)
14. **8.1.2** (user-typing signal path -- UI integration)
15. **8.4.2** (typing-based timer pause/resume)
16. **8.2.4** (conversation.weave.decided event emission)
17. **8.4.3** (deterministic fallback mode)
18. **8.4.5** (consolidate WeaveBatcher/FSM flush into single pathway)
19. **8.4.4** (weave quality observability metrics)

---

### E8.5 -- End-to-End Wiring: Adaptive Weave Policy into Cumulative M1-M7 Infrastructure

Source: Wiring audit (systematic cross-milestone integration)

**Rationale:** E8.1-E8.4 build four new subsystems -- WeaveSignal collector, WeavePolicy decision engine, dynamic batch window + digest mode, and policy integration with fallback. They treat each as a self-contained subsystem. None of the 19 issues address how these subsystems integrate with the cumulative M1+M2+M3+M4+M5+M6+M7 infrastructure. Without explicit wiring:

- `k1.conversation.weave.decided.v1` and `k1.ui.typing.v1` bus topics have no M2 guard table entries (guard_dispatch rejects them -> dead-letter storm for every weave decision and every typing signal)
- M1's LedgerMiddleware has no canonical event class for WeaveDecisionMadeEvent (ledger drops it or records raw envelope dump instead of structured decision audit trail)
- WeaveSignal.from_runtime() reads BackPool utilization (M7 8.1.1), but M7's BackPool metrics are emitted as bus events, not as a queryable pool.get_pool_state() API -- the signal collector must read from BackPool directly, not from the bus
- WeavePolicy.decide() produces DEFER decisions, but M5's ConversationArbiter also produces DEFER decisions for interrupts. Two independent DEFER mechanisms could conflict: arbiter DEFERs the user input, policy DEFERs the weave -- both hold, neither proceeds
- DIGEST mode pre-synthesizes results before Front LLM sees them, but M4's DynamicPromptBuilder.build(ss=ss) already assembles the WEAVE prompt from scenario_templates.py. The digest payload must flow through the same builder pipeline, not bypass it
- WeavePolicy reads affect_band from affective_now (M8 8.1.5), but the same affective_now is used by M5's arbiter InflightContext. If both read at different times within the same turn, they may see different affect states
- M6's HITL suspension fires hitl.requested.v1 which should suppress all non-urgent weave delivery (HITL question flow must not be interrupted by a weave), but M8's WeavePolicy has no signal for "HITL pending"
- M7's TaskLease expiry auto-cancel produces a task.complete-equivalent event. WeavePolicy must distinguish "normal completion" from "lease expiry cancellation" -- cancelled results should be SUPPRESS, not IMMEDIATE
- The deterministic fallback (8.4.3) uses get_weave_action() (weave_state.py L81-95) + fixed 500ms. But the fallback path must still go through M2's guard table and M1's ledger -- it cannot bypass the bus infrastructure
- WeaveBatcher -> WeaveQueue renaming (8.4.5) affects bootstrap.py L231 (set_weave_batcher), controller.py (multiple references), and test fixtures -- all must be coordinated

**Every M8 artifact must plug into the cumulative M1+M2+M3+M4+M5+M6+M7 infrastructure or the adaptive weave policy exists as a disconnected decision engine with no observability, no guard table protection, no affect coordination, no HITL awareness, and no pool-aware signal collection.**

**System state after M1+M2+M3+M4+M5+M6+M7 (E1.4 + E2.5 + E3.7 + E4.5 + E5.5 + E6.5 + E7.5 wiring complete) -- what M8 inherits:**

```
kernel/bootstrap.py::start_kernel()
  -> InMemoryLedgerStore + LedgerWriter created             # M1 1.4.1
  -> LedgerMiddleware in bus middleware chain                # M1 1.4.4
  -> ConciergeController(bus, router)
     -> set_ledger(writer)                                  # M1 1.4.1
     -> _ledger_append() in 11+ handlers                    # M1 1.4.2
     -> _try_deserialize() bridge                           # M1 1.4.3
     -> _dispatch_envelope() flow:                          # M2 2.5.3
          topic_guard -> idempotency -> guard_dispatch -> handler
     -> FULL_GUARD_TABLE + _guard_dispatch()                # M2 2.1.1-2.1.2
     -> _publish_dead_letter() with ledger recording        # M2 2.5.2
     -> IdempotencyLedger                                   # M2 2.3.2
     -> decide_response_final() + ResponseFinalEvent        # M2 2.3.1, 2.5.4
     -> Per-task CancellationToken in _cancel_tokens        # M3 3.2.2
  -> route_back_envelope() as canonical back dispatch        # M3 3.1.1-3.1.3
  -> DeadLetterConsumer subscribed to bus                    # M2 2.5.1
  -> Unknown back topics -> dead-letter pipeline             # M3 3.7.1
  -> builders auto-enrich legacy dicts                       # M1 1.4.5
  -> actors/shared.py: parse_envelope_payload,
       safe_get_section, never_cancel                        # M3 3.5.1-3.5.3
  -> SuspensionManager (timeout lifecycle after M6)          # M3 3.3.1, M6
  -> classify_tool_batch() in react_loop                     # M3 3.4.2
  -> ReactResult carries parallel/sequential counts          # M3 3.7.4
  -> TaskBridge.rebind() to real SS task_state/task_artifacts # M4 4.1.1, 4.5.1
  -> ControlExtension.bind_control_section() + fsm_overlay   # M4 4.1.2, 4.5.2
  -> writer_port (DirectWriterAdapter) on ToolContext         # M4 4.2.1, 4.5.3
  -> 6 cognitive tools through writer_port.request_mutation() # M4 4.2.3
  -> LLM-writable allowlist in config                        # M4 4.2.2
  -> Runtime guard rejecting LLM writes to system sections   # M4 4.2.4
  -> update_session_bundle with batch_mutations              # M4 4.3.1-4.3.3
  -> SECTION_RENDERERS + _read_ss_sections() in stage 8      # M4 4.4.1-4.4.2
  -> DynamicPromptBuilder.build(ss=ss) parameter             # M4 4.4.2
  -> TurnMutationSummaryEvent in ledger at turn completion   # M4 4.5.4
  -> ToolContext.idempotency_cache for bundle dedup           # M4 4.5.5
  -> ConversationArbiter replaces InterruptClassifier         # M5 5.5.1
  -> ArbiterDecision enum (CANCEL/MODIFY_INFLIGHT/PARALLEL_NEW/DEFER) # M5 5.2.1
  -> InflightContext from SS task_state + control overlay     # M5 5.5.2
  -> k1.arbiter.intent.v1 event in guard table + ledger      # M5 5.5.1
  -> _handle_arbiter_cancel/modify/defer/parallel_new         # M5 5.2.2-5.2.5
  -> RunningTaskHandle + _running_tasks for message injection # M5 5.5.4
  -> _enrich_envelope_with_arbiter() + routing_metadata       # M5 5.5.5
  -> device_id tracking on MetaSection + ToolContext           # M5 5.5.6
  -> resolve_device_conflict() precedence rules               # M5 5.4.2
  -> Multi-device confirmation via clarification mechanism    # M5 5.4.3
  -> HILSubTask dataclass (PENDING/RESOLVED/TIMED_OUT/CANCELLED) # M6 6.1.1
  -> 4 HITL topics in guard table + 4 canonical event classes  # M6 6.5.1
  -> back_resume_handler wired via topic routing (M6 protocol) # M6 6.2.1, 6.5.2
  -> validate_before_invoke in tool dispatch (L2 check)        # M6 6.1.3, 6.5.4
  -> resume_token validation on task.resume.v1                 # M6 6.1.4, 6.5.5
  -> scan_for_recovery at FSM startup after SS binding         # M6 6.4.2, 6.5.5
  -> Consolidated suspension limits at HILSubTask creation     # M6 6.3.4
  -> Mandatory cancellation callback for Back dispatch         # M6 6.2.4, 6.5.3
  -> BackPool(BackPoolConfig) in coordinator + bootstrap       # M7 7.5.2
  -> BackTopicRouter (dispatch/resume/cancel routing)          # M7 7.5.2
  -> TaskLease with CancellationToken (single SOT for cancel)  # M7 7.5.3
  -> ReadyQueue for dependency ordering in _on_task_complete   # M7 7.5.4
  -> LeaseStatus.SUSPENDED for HITL suspension lifecycle       # M7 7.5.5
  -> InflightContext pool_active_workers + lease_deadlines     # M7 7.5.6
  -> RunningTaskHandle delegates to BackPool worker state      # M7 7.5.6
  -> PARALLEL_NEW downgrades to DEFER when pool full           # M7 7.5.6
  -> 3 pool/lease topics in guard table + 5 canonical events   # M7 7.5.1
  -> WeaveBatcher with vestigial flush_fn (logs only)          # bootstrap.py L231-233
  -> get_weave_action(ConciergeState) -> static WeaveAction    # weave_state.py L81-95
  -> FSM._schedule_weave_flush with FIXED 500ms               # controller.py L1830-1855
  -> FSM._on_task_complete -> state-based routing (no signals) # controller.py L1063-1175
  -> pending_results: deque with no urgency metadata           # turn_state.py L44-76
  -> WEAVE scenario template: no urgency, no emotional context # scenario_templates.py L51-59
  -> WEAVE sections: IDENTITY + WEAVE_PROTOCOL + EMOTIONAL_CALIB # sections.py L540-543
  -> Demo: backpool_wired + topic_router_wired in health check # M7 7.5.9
  -> Fixtures: create_wired_fsm(with_ledger,
       with_dead_letter_consumer, with_cancel_tokens,
       with_ss_binding, with_writer_port, with_arbiter,
       with_hitl, with_back_pool, with_lease,
       with_ready_queue, with_topic_router)                    # M1-M7 fixtures
```

**M8 artifacts that must integrate into this M1+M2+M3+M4+M5+M6+M7-wired system:**

| M8 Artifact | Where It Lives After E8.1-E8.4 | M1+M2+M3+M4+M5+M6+M7 Touchpoint It Must Connect To |
|-------------|-------------------------------|----------------------------------------------|
| `WeaveSignal` dataclass with backpool_utilization field | `protocols/weave_policy.py` | M7 BackPool.get_pool_state() must be accessible to WeaveSignal.from_runtime(). Signal reads pool_active_workers/pool_size as a float 0.0-1.0. M7 7.5.6 added pool state to InflightContext; WeaveSignal must read from the SAME BackPool instance (not duplicate). |
| `WeaveSignal.affect_band` + `affect_valence` fields | `protocols/weave_policy.py` | M5 InflightContext reads affective_now for arbiter decisions. M8 WeaveSignal reads the same section. Both must read atomically within a turn to avoid state skew. M4's_read_ss_sections() reads affective_now in stage 8 -- WeaveSignal should use the same cached read, not a separate SS access. |
| `UserActivityTracker` (typing_start/stop/idle) | `protocols/weave_policy.py` | M2 guard table must allow k1.ui.typing.v1 topic. M1 ledger does NOT record typing events (high-frequency, low-value -- use RELAXED delivery). M5 arbiter does not currently use typing signals but SHOULD check: if user is typing, DEFER is preferred over PARALLEL_NEW. |
| `WeaveDecision` enum (IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS) | `protocols/weave_policy.py` | M5 ArbiterDecision also has DEFER. When arbiter DEFERs user input AND weave policy DEFERs results, both hold. On next user input, arbiter's DEFER resolves first (user input processed), THEN weave policy re-evaluates (deferred results may now BATCH). Ordering: arbiter resolves -> weave re-evaluates. |
| `WeavePolicy.decide(signal)` replacing `get_weave_action(fsm_state)` | `protocols/weave_policy.py` | controller.py _on_task_complete (L1063-1175) currently uses hardcoded state-based routing. M8 replaces with WeavePolicy.decide(). The SAME handler also fires M7's BackPool.release_worker() and ReadyQueue.notify_completed(). Ordering: release worker -> notify queue -> collect WeaveSignal -> decide. WeaveSignal must see updated pool state (post-release). |
| `k1.conversation.weave.decided.v1` bus event | `bus/topics.py`, `bus/builders.py` | M2 FULL_GUARD_TABLE needs entry. M1 LedgerMiddleware records WeaveDecisionMadeEvent. M2 IdempotencyLedger handles dedup. This is an observability passthrough -- it does NOT cause FSM state transitions. |
| Dynamic batch window replacing fixed WEAVE_BATCH_WINDOW_MS | `fsm/controller.py` _schedule_weave_flush | controller.py L1845: `await asyncio.sleep(WEAVE_BATCH_WINDOW_MS / 1000)` becomes `await asyncio.sleep(decision.window_ms / 1000)`. M7's _on_task_complete fires before this -- ReadyQueue may auto-dispatch a dependent task that also completes, adding to pending_results mid-window. Dynamic window must handle mid-window result arrivals. |
| DEFER delivery path (deferred results injected into STANDARD mode) | `fsm/controller.py` _on_user_input | controller.py L560-770: _on_user_input in LISTENING state runs Phase 1 then Front STANDARD mode. Deferred results must be injected into the STANDARD scenario_data as async_results_context. scenario_templates.py L37 already has `{async_results_context}` in STANDARD template. M4's DynamicPromptBuilder.build() must populate this field from deferred results. |
| DIGEST mode with pre-synthesized summary | `protocols/weave_policy.py`, Front delivery | DIGEST uses Front WEAVE mode but with compressed payload. M4's DynamicPromptBuilder sees scenario_data["results_summary"] which is currently built by front.py _extract_scenario_data L105-145 from raw result blocks. DIGEST must replace raw blocks with pre-synthesized summary. The builder pipeline is unchanged; only the input data changes. |
| Urgency label + emotional context in WEAVE scenario template | `prompt/scenario_templates.py` | M4's DynamicPromptBuilder formats scenario_data using SCENARIO_DATA_TEMPLATES[WEAVE]. New fields `urgency_label` and `emotional_context` must be added to the template AND populated by front.py_extract_scenario_data (L105-145). M5 affect_band (from affective_now) feeds the emotional_context string. |
| Result ordering (urgency + domain grouping) before weave delivery | `fsm/controller.py` _flush_weave_now | controller.py L1850-1860: _flush_weave_now calls turn_state.drain_results() then_build_weave_envelope(results). Sorting must happen between drain and build. M8 extends enqueue_result (turn_state.py L66-76) to include urgency -- the sort reads this field. M4's TaskBridge stores urgency from dispatch payload on TaskStateEntry -- E8.1.4 can read it from there. |
| User-typing signal suppressing weave timer | `fsm/controller.py` | controller.py _schedule_weave_flush creates a timer task. When typing detected, the timer must be cancelled. When typing stops (+ debounce), timer restarts. M7's BackPool worker may complete a task during typing -- the result queues, policy returns DEFER, no timer starts. When typing stops, policy re-evaluates and may BATCH. This interacts with FrontLock (front_lock.py L55): if Front is busy with user input (URGENT), weave is already queued at P3. |
| WeaveBatcher -> WeaveQueue renaming | `protocols/weave_batcher.py`, `kernel/bootstrap.py`, `fsm/controller.py` | bootstrap.py L231 (set_weave_batcher), controller.py (all _weave_batcher references), test fixtures. Rename must be coordinated across all files. WeaveQueue retains queue management; timing delegation goes to WeavePolicy. |
| Deterministic fallback when policy/signals fail | `fsm/controller.py` | Fallback uses get_weave_action() + 500ms. But fallback path must still emit conversation.weave.decided.v1 event (with reasoning="fallback") through M2 guard table and M1 ledger. Fallback does NOT bypass bus infrastructure. |
| WeavePolicy re-evaluation on typing signal change | `fsm/controller.py` | Re-evaluation may change a BATCH decision to DEFER or vice versa. The cancelled timer task must not leak (asyncio.Task cleanup). M7's lease expiry watcher also cancels timers -- same cleanup pattern applies. |
| M6 HITL suppression during weave | `protocols/weave_policy.py` | When HILSubTask.status == PENDING for any task, WeaveSignal must include hitl_pending=True. WeavePolicy rule: if hitl_pending and not has_critical -> DEFER (HITL question flow takes priority). M6's hitl.requested.v1 event fires BEFORE the HITL question reaches the user -- weave suppression must activate on that event. |
| WeavePolicyConfig in centralized config | `config/` | M4 config centralization: WeavePolicyConfig must be loadable from same config source as LLM-writable allowlist, BackPoolConfig, etc. All thresholds (idle_eager_ms, digest_threshold_count, emotional_suppress_valence) in config, not hardcoded. |

---

#### 8.5.1 -- Register weave decision + typing signal bus topics in M2 guard table and M1 ledger pipeline

**Problem:** E8.2.4 emits `k1.conversation.weave.decided.v1` on every weave decision. E8.1.2 introduces `k1.ui.typing.v1` for user typing signals. But M2's `_dispatch_envelope()` flow runs: topic_guard -> idempotency -> guard_dispatch -> handler. If these topics have no `FULL_GUARD_TABLE` entries, `_guard_dispatch()` rejects them as unknown topics and routes every weave decision to dead-letter.

For typing signals specifically: these are high-frequency, low-value events (every keystroke or typing-indicator pulse). They should be recorded in the ledger at SAMPLED frequency (not every event), or excluded entirely to avoid ledger bloat.

**What to do:**

1. Add topic constants to `bus/topics.py`:

   ```python
   TOPIC_WEAVE_DECIDED = "k1.conversation.weave.decided.v1"
   TOPIC_UI_TYPING = "k1.ui.typing.v1"
   TOPIC_WEAVE_METRICS = "k1.metrics.weave.v1"
   ```

2. Add to `FULL_GUARD_TABLE` in `fsm/controller.py`:

   ```python
   # Weave policy decision -- observability passthrough in any state
   # where task completion can trigger a weave decision.
   (ConciergeState.LISTENING, TOPIC_WEAVE_DECIDED): [ConciergeState.LISTENING],
   (ConciergeState.COMPANIONING, TOPIC_WEAVE_DECIDED): [ConciergeState.COMPANIONING],
   (ConciergeState.DELIVERING, TOPIC_WEAVE_DECIDED): [ConciergeState.DELIVERING],
   (ConciergeState.WEAVING, TOPIC_WEAVE_DECIDED): [ConciergeState.WEAVING],
   (ConciergeState.PROGRESSING, TOPIC_WEAVE_DECIDED): [ConciergeState.PROGRESSING],
   (ConciergeState.DISPATCHING, TOPIC_WEAVE_DECIDED): [ConciergeState.DISPATCHING],

   # UI typing signal -- received in any state where user may type.
   # RELAXED delivery: best-effort, no state transition.
   (ConciergeState.LISTENING, TOPIC_UI_TYPING): [ConciergeState.LISTENING],
   (ConciergeState.COMPANIONING, TOPIC_UI_TYPING): [ConciergeState.COMPANIONING],
   (ConciergeState.DELIVERING, TOPIC_UI_TYPING): [ConciergeState.DELIVERING],
   (ConciergeState.WEAVING, TOPIC_UI_TYPING): [ConciergeState.WEAVING],
   (ConciergeState.DISPATCHING, TOPIC_UI_TYPING): [ConciergeState.DISPATCHING],
   (ConciergeState.CLARIFYING_USER, TOPIC_UI_TYPING): [ConciergeState.CLARIFYING_USER],
   (ConciergeState.CLARIFYING_WORKER, TOPIC_UI_TYPING): [ConciergeState.CLARIFYING_WORKER],
   ```

3. Create canonical event classes:

   ```python
   @dataclass
   class WeaveDecisionMadeEvent(CanonicalEventMeta):
       candidate_event_id: int       # envelope_id of triggering task.complete
       decision: str                 # IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS
       reason: str                   # human-readable decision reasoning
       window_ms: int                # 0 for IMMEDIATE, dynamic for others
       fsm_state: str                # state when decision was made
       signal_snapshot: dict         # serialized WeaveSignal for replay
       urgency_override: bool        # True if critical urgency overrode policy
       emotional_gate_applied: bool  # True if affect gating triggered
       fallback_used: bool           # True if deterministic fallback was used

   @dataclass
   class WeaveMetricsEvent(CanonicalEventMeta):
       session_id: str
       weave_count: int
       digest_count: int
       defer_count: int
       suppress_count: int
       avg_weave_latency_ms: float
       user_acknowledged_rate: float  # 0.0-1.0
   ```

4. Register WeaveDecisionMadeEvent in M1's event registry. WeaveMetricsEvent registered for session-end emission.

5. Typing events: add to guard table but do NOT register canonical event class for M1 ledger. Instead, typing signals update UserActivityTracker in-memory only. Rationale: typing events are high-frequency (10-50/second during active typing), recording each one would bloat the ledger. The tracker aggregates into WeaveSignal.user_typing (bool) and WeaveSignal.user_idle_ms (int) which ARE recorded as part of WeaveDecisionMadeEvent.signal_snapshot.

6. Add builder:

   ```python
   def build_weave_decided(candidate_event_id, decision, reason, window_ms, ...): ...
   ```

7. Add test: emit weave.decided.v1, verify it passes guard_dispatch. Emit ui.typing.v1, verify it passes guard_dispatch. Verify WeaveDecisionMadeEvent in ledger with signal_snapshot. Verify typing events do NOT appear in ledger.

**Files to modify:**

- `poc/k1_poc/bus/topics.py` (3 new topic constants)
- `poc/k1_poc/bus/builders.py` (build_weave_decided)
- `poc/k1_poc/fsm/controller.py` (FULL_GUARD_TABLE entries for 3 topics)
- `poc/k1_poc/events/` (WeaveDecisionMadeEvent, WeaveMetricsEvent)
- `poc/k1_poc/events/registry.py` (register 2 event classes)

**Dependency:** E8.2.4 (weave.decided event), E8.1.2 (typing signal), M2 2.1.1 (FULL_GUARD_TABLE), M1 1.4.2 (_ledger_append), M1 1.4.4 (LedgerMiddleware)

**Acceptance:**

- weave.decided.v1 and ui.typing.v1 pass guard_dispatch without dead-letter
- Guard table allows each topic in all logically valid states
- WeaveDecisionMadeEvent recorded in ledger with full signal_snapshot
- Typing events do NOT bloat ledger (in-memory tracker only)
- WeaveMetricsEvent emitted at session end
- Zero dead-letters from weave/typing topics under normal operation

---

#### 8.5.2 -- Wire WeavePolicy into FSM _on_task_complete replacing state-based routing

**Problem:** controller.py `_on_task_complete` (L1063-1175) uses hardcoded state-based routing: LISTENING -> PROACTIVE_WAKE -> DELIVERING, COMPANIONING -> DELIVERING (or queue if Front busy), everything else -> queue. This is the integration point where M8's WeavePolicy must replace the static decision. But this handler also runs M7 wiring (BackPool.release_worker + ReadyQueue.notify_completed from 7.5.4). The ordering of operations is critical: M7 pool release must happen BEFORE WeaveSignal collection so the signal sees accurate pool utilization.

Additionally, the same-turn-completion suppression (L1118-1140) must run BEFORE the policy decision -- results from tasks dispatched and completed in the same turn are never woven (they are already covered by the Front STANDARD response).

**What to do:**

1. In `_on_task_complete`, establish canonical execution order:

   ```python
   async def _on_task_complete(self, envelope):
       task_id = envelope.payload["task_id"]

       # 1. Cancel dedup (existing)
       if self._cancel_handler.is_cancelled(task_id):
           ...return

       # 2. Same-turn suppression (existing L1118-1140)
       if dispatch_turn == self._turn_number and self._state == ConciergeState.COMPANIONING:
           ...return  # Front STANDARD already covers this

       # 3. M7: Release worker + lease (7.5.4)
       await self._back_pool.release_worker(task_id, reason="completed")

       # 4. M7: TaskBridge sync (existing M4)
       self._task_bridge.complete_task(task_id)

       # 5. M7: ReadyQueue notification (7.5.4)
       ready_tasks = self._ready_queue.notify_completed(task_id)

       # 6. M5: Remove RunningTaskHandle (existing)
       self._running_tasks.pop(task_id, None)

       # 7. NEW M8: Enqueue result with urgency metadata (8.1.4)
       urgency = self._get_task_urgency(task_id)  # from dispatch payload
       self._turn_state.enqueue_result(task_id, payload, envelope, urgency=urgency)

       # 8. NEW M8: Collect WeaveSignal (reads pool state AFTER release)
       signal = WeaveSignal.from_runtime(
           fsm_state=self._state,
           turn_state=self._turn_state,
           back_pool=self._back_pool,
           ss=self._session_state,
           activity_tracker=self._activity_tracker,
           hitl_pending=self._has_pending_hitl(),
       )

       # 9. NEW M8: WeavePolicy decision
       try:
           decision = self._weave_policy.decide(signal)
       except Exception:
           decision = self._weave_fallback(signal)  # 8.4.3 fallback

       # 10. NEW M8: Emit weave.decided.v1 event (8.2.4)
       self._emit_weave_decided(decision, envelope, signal)

       # 11. NEW M8: Branch on decision
       if decision.decision == WeaveDecision.IMMEDIATE:
           self._deliver_weave_immediate(envelope)
       elif decision.decision == WeaveDecision.BATCH:
           self._schedule_weave_flush(envelope, window_ms=decision.window_ms)
       elif decision.decision == WeaveDecision.DEFER:
           self._mark_results_deferred(envelope)
       elif decision.decision == WeaveDecision.DIGEST:
           self._schedule_digest_flush(envelope, window_ms=decision.window_ms)
       elif decision.decision == WeaveDecision.SUPPRESS:
           self._suppress_result(task_id, decision.reason)

       # 12. M7: Auto-dispatch dependent tasks from ReadyQueue
       for dep_task_id in ready_tasks:
           await self._on_task_dispatch(self._ready_queue.get_deferred_envelope(dep_task_id))
   ```

2. The critical ordering guarantee: BackPool.release_worker (step 3) runs BEFORE WeaveSignal collection (step 8). This ensures the signal's backpool_utilization reflects the post-completion pool state. If the pool was at 3/3 and one task completed, the signal sees 2/3 (not 3/3).

3. ReadyQueue auto-dispatch (step 12) runs AFTER the weave decision (step 11). If a dependent task is dispatched, it will complete later and trigger its own _on_task_complete with its own WeavePolicy decision. The current result's weave decision is independent.

4. Wire `_weave_fallback()` method (8.4.3): catches exceptions from WeavePolicy.decide() and falls back to get_weave_action() + fixed 500ms:

   ```python
   def _weave_fallback(self, signal: WeaveSignal) -> WeaveDecisionResult:
       action = get_weave_action(self._state)
       if action == WeaveAction.IMMEDIATE:
           return WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE, window_ms=0, reasoning="fallback: state-based IMMEDIATE")
       return WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=500, reasoning="fallback: fixed 500ms")
   ```

5. Wire WeavePolicy instance into controller: add `set_weave_policy(policy)` method, called from bootstrap.py after policy creation.

6. Add test: dispatch task -> task completes -> verify WeavePolicy.decide() called with correct signal -> verify weave.decided.v1 emitted -> verify correct branch taken.

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (_on_task_complete rewrite with canonical ordering,_weave_fallback, set_weave_policy,_deliver_weave_immediate, _mark_results_deferred,_schedule_digest_flush, _suppress_result)
- `poc/k1_poc/kernel/bootstrap.py` (create WeavePolicy, call set_weave_policy)

**Dependency:** E8.1.1 (WeaveSignal), E8.2.1-8.2.2 (WeavePolicy.decide), E8.4.1 (primary integration), E8.4.3 (fallback), 7.5.4 (_on_task_complete M7 ordering), M4 4.5.1 (TaskBridge), M5 5.5.4 (RunningTaskHandle)

**Acceptance:**

- _on_task_complete follows canonical 12-step ordering
- BackPool.release_worker runs BEFORE WeaveSignal collection
- Same-turn suppression runs BEFORE policy decision
- WeavePolicy.decide() called for every non-suppressed task.complete
- Fallback activates on policy exception without crashing
- weave.decided.v1 emitted for every decision (including fallback)
- All 5 decision branches (IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS) reachable

---

#### 8.5.3 -- Wire WeaveSignal to read BackPool state, affect, and HITL status from canonical sources

**Problem:** WeaveSignal.from_runtime() (8.1.1) needs 6 signal categories: urgency, typing, idle, affect, pool, and pending count. Each has a canonical source in the M1-M7 stack. If from_runtime() reads from the wrong source or reads at the wrong time, the signal is stale or inconsistent.

Specific risks:

- BackPool utilization: M7's BackPool exposes get_pool_state(). M5's InflightContext also reads pool state (7.5.6). If from_runtime() creates its own BackPool query, it may race with InflightContext's read.
- Affect: M4's _read_ss_sections() reads affective_now in stage 8 (prompt assembly). WeaveSignal reads it in _on_task_complete (step 8). These are different phases of the turn -- affective_now may change between reads if Phase 1 updates it.
- HITL pending: M6's HILSubTask tracks pending status. WeaveSignal needs hitl_pending=True when ANY task has PENDING HILSubTask. This requires querying TaskBridge (M4) or the HILCoordinator (M6).

**What to do:**

1. **BackPool utilization**: WeaveSignal.from_runtime() reads directly from BackPool instance (same instance used by InflightContext). No new query mechanism needed:

   ```python
   # In WeaveSignal.from_runtime():
   pool_state = back_pool.get_pool_state()
   signal.backpool_utilization = pool_state.active / pool_state.size if pool_state.size > 0 else 0.0
   ```

2. **Affect state**: Read from the SAME affective_now section that Phase 1 wrote. Since_on_task_complete runs AFTER Phase 1 (user input -> Phase 1 -> Front -> task.complete is a later event), the affective_now is stable:

   ```python
   affect_dict = _get_affect_dict(ss)  # Same helper as front.py L329
   signal.affect_band = compute_affect_band(affect_dict).band
   signal.affect_valence = affect_dict.get("valence", 0.0)
   ```

3. **HITL pending**: Query TaskBridge for suspended tasks:

   ```python
   suspended = task_bridge.get_suspended_tasks()
   signal.hitl_pending = len(suspended) > 0
   ```

4. **Add hitl_pending to WeaveSignal dataclass** (not in E8.1.1 -- cross-milestone integration):

   ```python
   @dataclass
   class WeaveSignal:
       # ... existing E8.1.1 fields ...
       hitl_pending: bool = False  # NEW: True if any task has PENDING HILSubTask
   ```

5. **Add HITL suppression rule to WeavePolicy.decide()** (between rules 5 and 6 in E8.2.2):

   ```python
   # Rule 5.5: HITL pending suppresses non-urgent weave
   if signal.hitl_pending and not signal.has_critical:
       return WeaveDecisionResult(
           decision=WeaveDecision.DEFER,
           window_ms=0,
           reasoning="HITL question pending -- deferring non-critical results to avoid interrupting HITL flow",
       )
   ```

6. **Distinguish lease-expired results from normal completions**: M7's lease expiry auto-cancel produces a task.failed event with reason="lease_expired", NOT a task.complete. So the WeavePolicy never sees expired-lease results in_on_task_complete. However, if a task is cancelled via arbiter or HITL timeout, it produces task.failed with reason="cancelled". The existing cancel dedup (step 1 in 8.5.2) catches these. No additional WeavePolicy logic needed for lease expiry.

7. **Atomic signal collection**: All WeaveSignal fields must be collected in a single synchronous pass (no awaits between field reads) to avoid state changes mid-collection:

   ```python
   @classmethod
   def from_runtime(cls, *, fsm_state, turn_state, back_pool, ss, activity_tracker, hitl_pending):
       # All reads are synchronous -- no awaits
       pool_state = back_pool.get_pool_state()
       affect_dict = _get_affect_dict(ss)
       pending = turn_state.pending_results
       return cls(
           fsm_state=fsm_state,
           pending_count=len(pending),
           pending_urgency_profile=_profile_urgency(pending),
           has_critical=_has_critical(pending),
           affect_band=compute_affect_band(affect_dict).band,
           affect_valence=affect_dict.get("valence", 0.0),
           emotional_gate=_compute_emotional_gate(affect_dict),
           backpool_utilization=pool_state.active / max(pool_state.size, 1),
           user_typing=activity_tracker.is_typing,
           user_idle_ms=activity_tracker.idle_ms,
           recent_weave_count=turn_state.recent_weave_count,
           hitl_pending=hitl_pending,
       )
   ```

8. Add test: set BackPool to 2/3, affect valence to -0.6, HITL pending. Collect WeaveSignal. Verify backpool_utilization=0.67, affect_band="crisis" or "elevated", hitl_pending=True. Verify policy returns DEFER (HITL suppression).

**Files to modify:**

- `poc/k1_poc/protocols/weave_policy.py` (WeaveSignal.from_runtime implementation, hitl_pending field, HITL suppression rule)
- `poc/k1_poc/fsm/controller.py` (_has_pending_hitl helper, pass hitl_pending to from_runtime)

**Dependency:** E8.1.1 (WeaveSignal), E8.1.5 (affect gating), E8.2.2 (policy rules), 8.5.2 (canonical ordering), M7 7.5.6 (BackPool.get_pool_state), M6 6.1.1 (HILSubTask), M4 4.1.1 (TaskBridge)

**Acceptance:**

- WeaveSignal.from_runtime() reads BackPool, affect, HITL from canonical M7/M5/M6 sources
- No duplicate BackPool queries (same instance as InflightContext)
- Affect read is stable (no race with Phase 1 updates)
- hitl_pending=True when any task has PENDING HILSubTask
- HITL suppression defers non-critical results during HITL flow
- All signal fields collected in single synchronous pass (atomic)
- Lease-expired results are not seen in _on_task_complete (handled by task.failed)

---

#### 8.5.4 -- Wire DEFER delivery into _on_user_input and STANDARD mode prompt assembly

**Problem:** E8.3.2 defines the DEFER path: when WeavePolicy returns DEFER, results are held until the user sends their next message. On user input, deferred results are injected into the Front STANDARD prompt as `async_results_context`. But the _on_user_input handler (controller.py L560-770) has no awareness of deferred results. And the STANDARD scenario template (scenario_templates.py L33-42) includes `{async_results_context}` but front.py's `_extract_scenario_data` for STANDARD mode does not populate this field from deferred results.

**What to do:**

1. **Track deferred results in FSMTurnState**: Extend turn_state.py to maintain a separate deferred_results list alongside pending_results:

   ```python
   @dataclass
   class FSMTurnState:
       pending_results: deque[dict[str, Any]] = field(default_factory=deque)
       deferred_results: list[dict[str, Any]] = field(default_factory=list)
       # deferred_results: results where WeavePolicy returned DEFER.
       # Drained on next _on_user_input and injected into STANDARD prompt.
   ```

2. **Wire _mark_results_deferred in controller** (called from 8.5.2 step 11):

   ```python
   def _mark_results_deferred(self, envelope):
       # Move from pending to deferred
       results = self._turn_state.drain_results()
       for r in results:
           r["deferred"] = True
           r["defer_count"] = r.get("defer_count", 0) + 1
       self._turn_state.deferred_results.extend(results)
   ```

3. **Wire _on_user_input to check deferred results**: In the LISTENING -> DISPATCHING path (L702-730), after normal turn setup, check deferred_results and format them for STANDARD prompt injection:

   ```python
   # In _on_user_input, LISTENING branch, after _run_phase1(envelope):
   if self._turn_state.deferred_results:
       deferred = self._turn_state.deferred_results
       # Re-evaluate policy: should these still be deferred?
       signal = WeaveSignal.from_runtime(...)
       for r in list(deferred):
           r_signal = signal  # Same signal for all deferred results
           decision = self._weave_policy.decide(r_signal)
           if decision.decision == WeaveDecision.DEFER:
               continue  # Still deferred (e.g., emotional gate still active)
           # Else: include in async_results_context
       self._async_results_context = self._format_deferred_for_standard(deferred)
       self._turn_state.deferred_results.clear()
   ```

4. **Populate async_results_context in STANDARD scenario_data**: front.py `_extract_scenario_data` for STANDARD mode (L85-95) currently builds scenario_data with `{async_results_context}`. It must read the formatted deferred results from the envelope or controller state:

   ```python
   # In _extract_scenario_data for STANDARD mode:
   async_results = payload.get("async_results_context", "")
   return {
       "active_member": ...,
       "family_context": ...,
       "async_results_context": async_results,  # Populated from deferred results
   }
   ```

5. **Max consecutive defers**: E8.2.3 defines max_consecutive_defers=5. When a result has been deferred 5 times, force BATCH delivery on the 6th evaluation. Track defer_count per result:

   ```python
   if r.get("defer_count", 0) >= config.max_consecutive_defers:
       # Force delivery -- cannot defer indefinitely
       return WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=500, reasoning="max_consecutive_defers reached")
   ```

6. **Wire async_results_context into envelope payload**: The controller must pass deferred results context to the Front delivery path. Add it to the envelope payload or stash on the controller for _extract_scenario_data to read:

   ```python
   # In _run_phase1 or _deliver_to_front:
   if self._async_results_context:
       # Inject into the envelope payload for Front to read
       enriched_payload = {**payload, "async_results_context": self._async_results_context}
       self._async_results_context = ""  # Clear after injection
   ```

7. Add test: dispatch task -> complete -> policy returns DEFER -> user sends next message -> verify async_results_context populated in STANDARD prompt -> verify LLM sees deferred result in scenario_data -> verify deferred_results list cleared.

**Files to modify:**

- `poc/k1_poc/fsm/turn_state.py` (deferred_results list)
- `poc/k1_poc/fsm/controller.py` (_mark_results_deferred,_on_user_input deferred check, _format_deferred_for_standard, _async_results_context)
- `poc/k1_poc/actors/front.py` (_extract_scenario_data STANDARD mode reads async_results_context)

**Dependency:** E8.3.2 (DEFER delivery path), 8.5.2 (WeavePolicy in _on_task_complete), M4 4.4.2 (DynamicPromptBuilder), scenario_templates.py STANDARD template

**Acceptance:**

- Deferred results stored in FSMTurnState.deferred_results (separate from pending_results)
- _on_user_input checks deferred results and re-evaluates policy
- async_results_context populated in STANDARD scenario_data when deferred results exist
- Front LLM sees deferred results in STANDARD mode (not WEAVE mode)
- max_consecutive_defers prevents infinite deferral
- deferred_results cleared after injection into STANDARD prompt

---

#### 8.5.5 -- Wire DIGEST mode through M4 DynamicPromptBuilder and WEAVE scenario pipeline

**Problem:** E8.3.3 defines DIGEST mode: 3+ low-urgency results are pre-synthesized into a 1-2 paragraph summary before reaching the Front LLM. The digest payload flows through the same Front WEAVE mode pipeline (M4 DynamicPromptBuilder -> scenario_templates.py -> sections.py), but the input changes from N raw [ASYNC RESULT ARRIVED] blocks to a single compressed summary.

The WEAVE scenario template and _extract_scenario_data (front.py L105-145) must handle both DIGEST and normal WEAVE inputs without requiring a separate PromptMode.

**What to do:**

1. **DigestPayload construction**: When _on_task_complete decides DIGEST (8.5.2 step 11), start a digest accumulation timer. When the timer fires, build the digest:

   ```python
   def _schedule_digest_flush(self, envelope, window_ms):
       if self._digest_flush_task and not self._digest_flush_task.done():
           return  # Timer already running, results accumulate
       self._digest_flush_task = asyncio.get_running_loop().create_task(
           self._flush_digest_after_delay(envelope.envelope_id, window_ms)
       )

   async def _flush_digest_after_delay(self, parent_id, window_ms):
       await asyncio.sleep(window_ms / 1000)
       self._flush_digest_now(parent_id)

   def _flush_digest_now(self, parent_id):
       results = self._turn_state.drain_results()
       if not results:
           return
       # Group by domain (from dispatch metadata)
       grouped = self._group_results_by_domain(results)
       # Sort groups by urgency (critical first)
       sorted_groups = sorted(grouped.items(), key=lambda g: _urgency_rank(g))
       # Generate template-based summary (NO LLM call)
       summary = self._build_digest_summary(sorted_groups)
       # Build weave envelope with digest payload
       digest_envelope = self._build_weave_envelope(
           [{"digest_summary": summary, "digest_count": len(results), "is_digest": True}],
           parent_id,
       )
       if self._front_lock.try_deliver(digest_envelope):
           self._deliver_to_front(digest_envelope)
   ```

2. **Wire _extract_scenario_data to handle digest**: front.py L105-145 currently builds results_summary from raw result blocks. For digest payloads, it uses the pre-synthesized summary:

   ```python
   # In _extract_scenario_data for WEAVE mode:
   if mode == PromptMode.WEAVE:
       payload_results = payload.get("results")
       # Check if this is a digest payload
       if isinstance(payload_results, list) and len(payload_results) == 1:
           first = payload_results[0]
           if isinstance(first, dict) and first.get("is_digest"):
               return {
                   "result_count": first.get("digest_count", 0),
                   "results_summary": first.get("digest_summary", ""),
                   "current_thread": thread_name,
                   "urgency_label": "Summary -- present as brief update",
                   "emotional_context": emotional_context,
               }
       # ... normal WEAVE path (N raw blocks) ...
   ```

3. **Wire digest template guidance**: The WEAVE scenario template (8.3.4) already includes `urgency_label`. For digest, urgency_label = "Summary -- present as brief update". This tells the Front LLM to present the pre-synthesized summary as a brief aside, not a detailed breakdown.

4. **Wire digest budget**: DIGEST uses the same WEAVE iteration budget (3 iterations, 2 in crisis). The compressed input means the LLM needs fewer iterations to process (typically 1-2), but the budget is unchanged for safety.

5. **Wire result grouping to use M4 TaskBridge metadata**: The domain grouping reads task dispatch metadata (action, urgency) from TaskStateEntry via TaskBridge. This metadata was stored at dispatch time (M4 4.1.1):

   ```python
   def _group_results_by_domain(self, results):
       groups = defaultdict(list)
       for r in results:
           task_id = r.get("task_id")
           entry = self._task_bridge.get_task_entry(task_id)
           domain = entry.domain if entry else "general"
           groups[domain].append(r)
       return groups
   ```

6. Add test: 5 low-urgency results complete -> policy returns DIGEST(15000ms) -> wait 15s -> verify digest summary built -> verify Front receives single compressed summary -> verify urgency_label = "Summary" -> verify results_summary is template-generated (not N raw blocks).

**Files to modify:**

- `poc/k1_poc/fsm/controller.py` (_schedule_digest_flush,_flush_digest_after_delay,_flush_digest_now, _group_results_by_domain, _build_digest_summary)
- `poc/k1_poc/actors/front.py` (_extract_scenario_data digest handling)
- `poc/k1_poc/protocols/weave_policy.py` (DigestPayload dataclass)

**Dependency:** E8.3.3 (DIGEST mode), 8.5.2 (WeavePolicy in _on_task_complete), M4 4.4.2 (DynamicPromptBuilder), M4 4.1.1 (TaskBridge metadata)

**Acceptance:**

- Digest timer accumulates results over window_ms (default 15s)
- Results grouped by domain using TaskBridge metadata
- Template-based summary generated (no LLM call for digest synthesis)
- Front receives single compressed summary in WEAVE mode
- _extract_scenario_data correctly routes digest vs normal WEAVE
- urgency_label = "Summary" for digest payloads
- WEAVE iteration budget unchanged (3 normal, 2 crisis)

---

#### 8.5.6 -- Wire urgency + emotional context into WEAVE scenario template and M4 prompt assembly

**Problem:** E8.3.4 is the highest LLM impact issue in M8: adding urgency_label and emotional_context to the WEAVE scenario template. But the template is consumed by M4's DynamicPromptBuilder, which formats scenario_data using string.format(). The new fields must flow through the entire pipeline: enqueue_result (urgency) -> WeaveSignal (affect) -> _flush_weave_now (sort by urgency) ->_build_weave_envelope (include urgency_label) ->_extract_scenario_data (build emotional_context) -> DynamicPromptBuilder.build() (format template).

**What to do:**

1. **Extend WEAVE scenario template** (scenario_templates.py L51-59):

   ```python
   PromptMode.WEAVE: (
       "== ASYNC RESULTS ARRIVED ==\n"
       "While you were chatting with the user, {result_count} background "
       "task(s) completed:\n"
       "{results_summary}\n"
       "The user's last message was about: {current_thread}\n"
       "\n"
       "== DELIVERY GUIDANCE ==\n"
       "{urgency_label}\n"
       "\n"
       "== EMOTIONAL CONTEXT ==\n"
       "{emotional_context}\n"
       "\n"
       "Respond to user's topic FIRST, then naturally transition to the "
       "async results. Follow the delivery guidance above.\n"
   ),
   ```

2. **Wire urgency_label generation**: In front.py `_extract_scenario_data` for WEAVE mode, build urgency_label from result metadata:

   ```python
   # Determine urgency label from results
   has_critical = any(
       (r.get("result", r) if isinstance(r, dict) else {}).get("urgency") in ("critical", "urgent")
       for r in pending
   )
   if has_critical:
       urgency_label = "URGENT -- present the time-critical result(s) prominently. The user needs to know about this immediately."
   elif result_count >= 3:
       urgency_label = "Summary -- these are routine updates. Present as a brief, natural aside."
   else:
       urgency_label = "Informational -- weave this result lightly into the conversation."
   ```

3. **Wire emotional_context generation**: Read affect_band from affective_now (same helper as front.py L329-337):

   ```python
   affect_dict = _get_affect_dict(ss)
   affect_band = compute_affect_band(affect_dict)
   valence = affect_dict.get("valence", 0.0)

   if affect_band.band == "crisis":
       emotional_context = (
           "The user is in emotional distress. Be extremely gentle. "
           "Acknowledge their state before presenting any result. "
           "If the result is not safety-critical, consider deferring it entirely. "
           "Example: 'I know this is a really hard time...'"
       )
   elif valence < -0.3:
       emotional_context = (
           "The user's mood is negative (sad, frustrated, or stressed). "
           "Be sensitive. Acknowledge what they're going through before "
           "transitioning to the result. Frame results positively: "
           "'One less thing to worry about -- your hotel is confirmed.'"
       )
   elif affect_band.band == "positive":
       emotional_context = (
           "The user is in a positive mood. Match their energy. "
           "Present results enthusiastically: 'Great news -- everything went through!'"
       )
   else:
       emotional_context = (
           "User affect is neutral. Standard weave -- respond to their "
           "topic first, then naturally transition to the result."
       )
   ```

4. **Wire result sorting in _flush_weave_now** (8.3.5): The sort happens AFTER drain and BEFORE _build_weave_envelope:

   ```python
   def _flush_weave_now(self, parent_id):
       results = self._turn_state.drain_results()
       if not results:
           return
       # Sort: critical first, then by domain group, then FIFO within group
       results = self._sort_results_for_weave(results)
       weave_envelope = self._build_weave_envelope(results, parent_id)
       ...
   ```

5. **Wire urgency into enqueue_result** (8.1.4): Extend turn_state.py enqueue_result to include urgency from dispatch payload:

   ```python
   def enqueue_result(self, task_id, result, envelope, urgency="normal"):
       self.pending_results.append({
           "task_id": task_id,
           "result": result,
           "envelope_id": envelope.envelope_id,
           "parent_id": envelope.parent_id,
           "queued_at_ns": envelope.created_ns,
           "urgency": urgency,  # NEW: from dispatch metadata
       })
   ```

6. **Wire urgency retrieval from TaskBridge**: In _on_task_complete (8.5.2 step 7), read urgency from the dispatch payload stored on TaskStateEntry:

   ```python
   def _get_task_urgency(self, task_id):
       entry = self._task_bridge.get_task_entry(task_id)
       if entry and hasattr(entry, "urgency"):
           return entry.urgency
       return "normal"
   ```

7. Add test: dispatch urgent task -> complete -> verify urgency_label="URGENT..." in scenario_data. Set affect valence=-0.6 -> verify emotional_context includes "emotional distress". Verify both fields appear in formatted WEAVE prompt that Front LLM receives.

**Files to modify:**

- `poc/k1_poc/prompt/scenario_templates.py` (WEAVE template with urgency_label + emotional_context)
- `poc/k1_poc/actors/front.py` (_extract_scenario_data: urgency_label + emotional_context generation)
- `poc/k1_poc/fsm/turn_state.py` (enqueue_result with urgency parameter)
- `poc/k1_poc/fsm/controller.py` (_get_task_urgency,_sort_results_for_weave,_flush_weave_now sorting)

**Dependency:** E8.3.4 (urgency + emotional labels), E8.3.5 (result ordering), E8.1.4 (pending result profiler), 8.5.2 (_on_task_complete ordering), M4 4.4.2 (DynamicPromptBuilder), M4 4.1.1 (TaskBridge metadata)

**Acceptance:**

- WEAVE scenario template includes urgency_label and emotional_context placeholders
- urgency_label computed from result metadata: URGENT / Summary / Informational
- emotional_context computed from affective_now: crisis / negative / positive / neutral
- Results sorted by urgency before building weave envelope
- enqueue_result stores urgency from dispatch payload
- Both fields visible in formatted WEAVE prompt (DynamicPromptBuilder.build output)
- Emotional context uses same _get_affect_dict helper as existing front.py code

---

#### 8.5.7 -- Extend test fixtures: create_wired_fsm with WeavePolicy + UserActivityTracker

**Problem:** E1.4-E7.5 incrementally built `create_wired_fsm()` with keyword arguments for each subsystem. M8 adds WeavePolicy, UserActivityTracker, WeaveQueue (renamed WeaveBatcher), and WeavePolicyConfig. Without fixture support, every M8 integration test must manually construct and wire these components.

**What to do:**

1. Extend `create_wired_fsm()` with M8 parameters:

   ```python
   def create_wired_fsm(
       # ... existing M1-M7 params ...
       with_back_pool=False,
       pool_size=3,
       with_lease=False,
       lease_ttl_s=300,
       with_ready_queue=False,
       with_topic_router=False,
       # NEW M8 params:
       with_weave_policy=False,       # Creates WeavePolicy + WeavePolicyConfig
       weave_policy_enabled=True,     # Enable/disable adaptive policy
       with_activity_tracker=False,   # Creates UserActivityTracker
       with_weave_queue=False,        # Creates WeaveQueue (renamed WeaveBatcher)
       digest_threshold_count=3,      # Override digest threshold
       idle_eager_ms=10000,           # Override idle eager threshold
   ) -> WiredFSMContext:
   ```

2. When `with_weave_policy=True`:
   - Create `WeavePolicyConfig(idle_eager_ms=idle_eager_ms, digest_threshold_count=digest_threshold_count, ...)`
   - Create `WeavePolicy(config)`
   - Attach to FSM controller via `set_weave_policy(policy)`
   - Implies `with_weave_queue=True` (policy needs the queue)
   - Implies `with_activity_tracker=True` (policy needs typing/idle signals)

3. When `with_activity_tracker=True`:
   - Create `UserActivityTracker()`
   - Subscribe to k1.ui.typing.v1 on bus
   - Attach to FSM controller

4. When `with_weave_queue=True`:
   - Create `WeaveQueue()` (renamed from WeaveBatcher)
   - Attach to FSM controller via `set_weave_queue(queue)`
   - Old `set_weave_batcher()` method aliased for backward compatibility

5. Return policy, tracker, queue on `WiredFSMContext`:

   ```python
   @dataclass
   class WiredFSMContext:
       # ... existing fields ...
       weave_policy: WeavePolicy | None = None
       activity_tracker: UserActivityTracker | None = None
       weave_queue: WeaveQueue | None = None
   ```

**Files to modify:**

- `tests/poc/conftest.py` or `tests/poc/fixtures.py` (create_wired_fsm extension)

**Dependency:** E8.1.2 (UserActivityTracker), E8.2.1-8.2.2 (WeavePolicy), E8.4.5 (WeaveQueue rename), 8.5.1-8.5.6 (all wiring issues)

**Acceptance:**

- `create_wired_fsm(with_weave_policy=True)` creates fully wired WeavePolicy
- `with_activity_tracker=True` creates UserActivityTracker subscribed to bus
- `with_weave_queue=True` creates WeaveQueue (renamed WeaveBatcher)
- All M1-M7 fixture params still work unchanged
- WiredFSMContext exposes policy, tracker, queue for test assertions
- Proper teardown of activity tracker subscriptions and digest timers

---

#### 8.5.8 -- Backward compatibility regression: 12 tests verifying M1-M7 wiring survives M8 refactoring

**Problem:** M8 makes deep changes to the weave delivery path: WeavePolicy replaces static get_weave_action, dynamic window replaces fixed 500ms, DEFER bypasses WEAVE mode entirely, DIGEST compresses results, WeaveBatcher renamed to WeaveQueue. Each change touches code paths that M1-M7 wiring depends on. Without explicit regression tests, M8 refactoring could silently break:

- M1 ledger recording (does _ledger_append still fire in _on_task_complete after WeavePolicy branch?)
- M2 guard table dispatch (does weave.decided.v1 pass guard_dispatch?)
- M7 BackPool release (does release_worker still run before WeaveSignal collection?)
- M7 ReadyQueue notification (does notify_completed still fire after WeavePolicy branch?)
- M6 HITL suppression (does hitl_pending correctly suppress weave during HITL?)
- M5 arbiter DEFER + weave DEFER coordination (no deadlock)

**What to do:**

1. Create `tests/poc/test_m08_wiring_regression.py` with 12 tests:

   **Test 1: M1 ledger records WeaveDecisionMadeEvent**
   - Boot with full M8 wiring
   - Dispatch task -> complete -> WeavePolicy decides BATCH
   - Verify ledger contains WeaveDecisionMadeEvent with signal_snapshot

   **Test 2: M2 guard table allows weave.decided.v1**
   - Emit weave.decided.v1 envelope
   - Verify not dead-lettered
   - Verify FULL_GUARD_TABLE has entries in correct states

   **Test 3: M7 BackPool release runs BEFORE WeaveSignal collection**
   - Set pool_size=2, dispatch 2 tasks (pool full)
   - Task A completes
   - Verify WeaveSignal.backpool_utilization = 1/2 = 0.5 (post-release, not 2/2 = 1.0)

   **Test 4: M7 ReadyQueue notification still fires after WeavePolicy branch**
   - Dispatch task A, dispatch task B (depends_on A)
   - Task A completes -> WeavePolicy decides BATCH
   - Verify ReadyQueue.notify_completed(A) fired (B auto-dispatches)
   - Verify B dispatches to BackPool AFTER A's weave decision

   **Test 5: M6 HITL suppression defers non-critical weave**
   - Dispatch task A (triggers HITL), dispatch task B (no HITL)
   - Task B completes while A's HITL is pending
   - Verify WeaveSignal.hitl_pending=True
   - Verify WeavePolicy returns DEFER for B's result

   **Test 6: M5 arbiter DEFER + weave DEFER no deadlock**
   - Dispatch task -> task completes (result queued as DEFER)
   - User sends new input -> arbiter classifies as DEFER (e.g., complex topic)
   - Verify arbiter DEFER resolves first (user input processed)
   - Verify deferred weave results re-evaluated after arbiter resolution
   - Verify no infinite deferral loop

   **Test 7: Deterministic fallback produces same behavior as pre-M8**
   - Set weave_policy_enabled=False in config
   - Dispatch task -> complete
   - Verify get_weave_action() + 500ms used (not WeavePolicy.decide)
   - Verify weave.decided.v1 still emitted with fallback_used=True
   - Verify result delivered via WEAVE mode within ~500ms

   **Test 8: DIGEST pre-synthesis does not bypass M4 DynamicPromptBuilder**
   - 5 low-urgency results -> policy returns DIGEST(15s)
   - Wait for digest timer
   - Verify digest summary flows through _extract_scenario_data -> DynamicPromptBuilder.build()
   - Verify Front LLM receives WEAVE mode with compressed summary

   **Test 9: Urgency label visible in Front WEAVE prompt**
   - Dispatch urgent task -> complete -> verify urgency_label="URGENT..." in scenario_data
   - Dispatch normal task -> complete -> verify urgency_label="Informational..."
   - Verify both labels appear in DynamicPromptBuilder output

   **Test 10: Emotional context correct for negative affect**
   - Set affect valence=-0.6, arousal=0.8 (crisis)
   - Task completes
   - Verify emotional_context includes "emotional distress"
   - Verify WeavePolicy returns SUPPRESS for non-critical (emotional gate)

   **Test 11: DEFER results injected into STANDARD async_results_context**
   - Task completes -> DEFER
   - User sends next message
   - Verify Front receives STANDARD mode with async_results_context populated
   - Verify deferred_results cleared from FSMTurnState

   **Test 12: WeaveBatcher -> WeaveQueue rename backward compatibility**
   - Verify set_weave_batcher still works (alias to set_weave_queue)
   - Verify bootstrap.py wiring works with new name
   - Verify test fixtures work with both with_weave_queue and legacy paths

2. Each test uses `create_wired_fsm(with_weave_policy=True, with_back_pool=True, with_hitl=True, with_arbiter=True, with_ss_binding=True)` from updated fixtures (8.5.7).

**Files to create:**

- `tests/poc/test_m08_wiring_regression.py`

**Dependency:** 8.5.1-8.5.7 (all wiring issues), M1-M7 regression test patterns

**Acceptance:**

- All 12 regression tests pass
- M7 `test_m07_wiring_regression.py` tests still pass after M8 changes
- M6 `test_m06_wiring_regression.py` tests still pass after M8 changes
- WeavePolicy decisions flow through guard table without dead-letters
- BackPool release ordering verified (before signal collection)
- HITL suppression verified (defers non-critical during HITL)
- Fallback produces identical behavior to pre-M8 when policy disabled
- DEFER -> STANDARD injection verified end-to-end

---

#### 8.5.9 -- Full regression: demo smoke test with Adaptive Weave Policy

**Problem:** M8 replaces the fixed 500ms weave batch window with a context-aware adaptive policy. The demo web app must exercise the complete adaptive weave lifecycle including immediate delivery, batched delivery with dynamic window, deferred delivery, digest mode, emotional gating, typing suppression, and deterministic fallback.

**What to do:**

1. Create `tests/poc/test_m08_demo_smoke.py`:

   **Scenario A: IMMEDIATE delivery -- user idle, single result**
   - Boot kernel with full M8 wiring
   - Set user idle for 15s (> IDLE_EAGER_MS=10000)
   - Dispatch task -> complete
   - Verify: WeavePolicy returns IMMEDIATE
   - Verify: weave.decided.v1 emitted with decision="IMMEDIATE", window_ms=0
   - Verify: Front invoked in WEAVE mode with zero delay
   - Verify: urgency_label = "Informational" (normal task)
   - Verify: Ledger shows WeaveDecisionMadeEvent

   **Scenario B: BATCH delivery -- dynamic window based on idle time**
   - Boot kernel, user active (idle 2s)
   - Dispatch task -> complete
   - Verify: WeavePolicy returns BATCH with window_ms > 500 (not fixed 500)
   - Verify: Window adjusts based on user_idle_ms (shorter idle = longer window)
   - Dispatch second task -> complete within window
   - Verify: both results delivered in single WEAVE invocation
   - Verify: results_summary contains both results

   **Scenario C: DEFER delivery -- mid-conversation natural weave**
   - Boot kernel, user typing (UserActivityTracker.on_typing_start)
   - Dispatch task -> complete
   - Verify: WeavePolicy returns DEFER (typing suppression)
   - Verify: No WEAVE mode invocation while typing
   - User stops typing, sends message
   - Verify: deferred result injected into STANDARD async_results_context
   - Verify: LLM response naturally mentions the deferred result

   **Scenario D: DIGEST mode -- 5 low-urgency results batched**
   - Boot kernel
   - Dispatch 5 tasks with urgency="background" -> all complete within 3s
   - Verify: WeavePolicy returns DIGEST with window_ms=15000
   - Wait for digest timer (15s)
   - Verify: Front receives single compressed summary (not 5 raw blocks)
   - Verify: urgency_label = "Summary -- present as brief update"
   - Verify: Results grouped by domain in summary
   - Verify: LLM produces 1-2 paragraph summary (not wall-of-text)

   **Scenario E: Emotional gating -- grief + hotel booking**
   - Boot kernel, set affective_now: valence=-0.6, arousal=0.3 (sad/grief)
   - Dispatch "book hotel in Napa" task -> complete
   - Verify: WeavePolicy returns DEFER (emotional_gate="suppress_trivial", result not critical)
   - Verify: weave.decided.v1 has emotional_gate_applied=True
   - User sends next message (tone improves, valence=0.1)
   - Verify: deferred result now BATCH (emotional gate lifted)
   - Verify: emotional_context = "User affect is neutral. Standard weave."

   **Scenario F: Demo health check with weave policy**
   - Boot kernel
   - Verify: health check reports `weave_policy_wired=True`, `weave_policy_enabled=True`
   - Verify: health check reports `activity_tracker_wired=True`
   - Verify: health check reports `weave_queue_wired=True` (renamed from WeaveBatcher)
   - Verify: All M1-M7 health checks still pass
   - Verify: `weave_fallback_count=0` (no fallbacks in clean operation)

2. Add demo endpoint:

   ```python
   # /api/session/weave -- new endpoint
   # Returns: last 10 WeaveDecisionMadeEvents with signal snapshots
   # Useful for debugging why the system chose DEFER instead of BATCH
   ```

**Files to create:**

- `tests/poc/test_m08_demo_smoke.py`

**Dependency:** 8.5.1-8.5.8 (all wiring and regression), M7 7.5.9 (demo smoke pattern)

**Acceptance:**

- All 6 scenarios pass
- IMMEDIATE delivery verified with zero delay for idle user
- Dynamic BATCH window verified (not fixed 500ms)
- DEFER -> STANDARD injection verified (natural mid-conversation weave)
- DIGEST mode verified (compressed summary, domain grouping)
- Emotional gating verified (grief suppresses trivial results)
- Health check reports weave_policy_wired, activity_tracker_wired
- All previous demo smoke tests (M2, M3, M4, M5, M6, M7) still pass

---

### M8 Touchpoint Matrix: What M9-M12 Inherit from M8

| Milestone | M8 Artifact Used | How It Uses It |
|-----------|-----------------|----------------|
| **M9** (Protocol Lifecycle to Ledger) | WeaveDecisionMadeEvent in ledger | M9 makes ledger the SOT for all state. WeaveDecisionMadeEvent entries become the replay source for rebuilding weave state after crash. signal_snapshot enables exact decision replay. |
| **M9** (Protocol Lifecycle to Ledger) | Deferred results in FSMTurnState | M9 must persist deferred_results in ledger-backed state. On crash recovery, deferred results are rebuilt from ledger events (TaskComplete + WeaveDecision=DEFER -> deferred). |
| **M9** (Protocol Lifecycle to Ledger) | UserActivityTracker.last_user_input_ns | M9 persists last_user_input_ns in ledger (from user.input events). On recovery, idle_ms calculation uses ledger timestamp of last user.input, not wall clock. |
| **M10** (UltraBERT) | WEAVE scenario template with urgency_label + emotional_context | UltraBERT follows urgency/emotional guidance more precisely. Urgency_label "URGENT" produces immediate-first responses. Emotional_context "crisis" produces genuinely empathetic weave transitions. Template text may be tuned for UltraBERT instruction adherence. |
| **M10** (UltraBERT) | DigestPayload compressed summary | UltraBERT can process longer digest summaries without truncation. digest_threshold_count may increase to 5 (UltraBERT handles 5-result digest coherently). Summary quality improves with better model. |
| **M10** (UltraBERT) | WEAVE mode iteration budget (3 normal, 2 crisis) | UltraBERT may need fewer iterations for WEAVE (2 normal, 1 crisis). Policy budget can be tuned per-model via config. But DIGEST keeps budget at 3 to handle compressed multi-result delivery. |
| **M11** (Observability) | WeaveDecisionMadeEvent + signal_snapshot | Full weave decision dashboard: decision distribution (IMMEDIATE/BATCH/DEFER/DIGEST/SUPPRESS), signal correlation analysis (which signals most influence decisions), fallback rate, emotional gate trigger rate. |
| **M11** (Observability) | WeaveMetricsEvent per session | Aggregate metrics: weave_count, digest_count, defer_count, suppress_count per session. User acknowledged rate tracks UX quality. Low acknowledge rate on BATCH suggests window is wrong. |
| **M11** (Observability) | UserActivityTracker typing/idle metrics | Typing suppression effectiveness: how often does typing prevent a premature weave? Idle detection accuracy: false positive rate (user idle but actually reading). |
| **M11** (Observability) | Dynamic batch window_ms distribution | Histogram of actual batch windows used. If 90% are 500ms (default), the adaptive policy is not adapting. Compare to user satisfaction metrics. |
| **M12** (Chaos Tests) | WeavePolicy under rapid task completions | Chaos: 10 tasks complete within 100ms. Verify policy handles burst gracefully (DIGEST for bulk, no timer leak, no duplicate WEAVE invocations). Verify pending_results deque handles rapid enqueue/drain. |
| **M12** (Chaos Tests) | DEFER under infinite deferral | Chaos: emotional gate suppresses trivial results indefinitely (affect never improves). Verify max_consecutive_defers=5 forces BATCH after 5 deferrals. Verify no results silently dropped. |
| **M12** (Chaos Tests) | Typing signal under rapid toggle | Chaos: typing_start, typing_stop alternating every 100ms for 10s. Verify timer cancel/restart does not leak asyncio.Tasks. Verify debounce (500ms) prevents thrashing. |
| **M12** (Chaos Tests) | DIGEST + HITL concurrent | Chaos: digest timer running (15s window), HITL requested at t=5s. Verify digest timer pauses or defers. Verify HITL question flow not interrupted by digest flush at t=15s. |

**Total: 19 issues across 4 epics (E8.1-E8.4) + 9 issues in E8.5 wiring = 28 issues across 5 epics.**

---

## M9: Protocol Lifecycle Migration to Ledger

**Goal:** Migrate ALL protocol lifecycle state (cancel, suspend, HITL, weave,
task, history) from authoritative in-memory maps to ledger-derived projections.
After M9, every runtime state map is a cached materialization of the ledger
event stream. Crash recovery rebuilds state by replaying ledger events
instead of relying on in-memory persistence. Mixed sync/async suspension
paths consolidated into a single event-driven lifecycle API.

**Gate:** Every protocol mutation (cancel, suspend, resume, HITL start/resolve,
task state change, history write) appends a canonical event to the ledger
BEFORE updating the in-memory projection. The in-memory state can be
destroyed and rebuilt from ledger replay at any time with identical results.
SuspensionManager exposes one async lifecycle API; sync helpers are marked
as compatibility shims that delegate to the canonical path. Crash recovery
test: kill process mid-HITL, restart, replay ledger, verify HITL resumes
correctly.

**Depends on:** M1 (canonical event schemas + ledger writer + projection
reader + replay test), M2 (FSM transition contracts + dead-letter), M6 (HITL
ReAct loop lifecycle).

### Why Protocol Migration Is Hard (Code Audit Findings)

**Current protocol state -- where it lives and why it matters:**

```
Protocol State Location Map (all in-memory, all lost on crash):

CancellationHandler (cancel_handler.py)
  ._tokens: dict[str, CancellationToken]       <- active cancel tokens
  ._cancelled_tasks: set[str]                   <- dedup set for late completions
  State lost on crash: cancel tokens vanish.
  Impact: Back continues executing a task that should be cancelled.
          Late completion dedup fails -> user sees "completed" for a
          task they already cancelled.

SuspensionManager (suspension_manager.py)
  ._active: dict[str, SuspensionRequest]        <- active suspensions
  ._contexts: dict[str, dict]                   <- raw suspension payloads (sync path)
  ._suspension_counts: dict[str, int]           <- per-task suspension count
  ._timeout_tasks: dict[str, asyncio.Task]      <- timeout watchers
  State lost on crash: suspension contexts vanish.
  Impact: Back is blocked waiting for resume that never comes.
          User answered the HITL question, but the resume context
          (including ReAct history) is gone -> Back must restart from
          scratch, repeating tool calls.

HILCoordinator (hitl_coordinator.py)
  ._pending_requests: dict[str, HILRequest]     <- active HITL requests
  ._hil_counts: dict[str, int]                  <- per-task HITL round counts
  State lost on crash: HITL request metadata vanishes.
  Impact: max_rounds limit cannot be enforced after restart (count=0).
          Safety band escalation history is lost.
          Crash during approval flow -> side-effect execution without
          re-approval (safety violation).

TaskBridge -> TaskStateSection (task_bridge.py)
  ._task_state: TaskStateSection                <- per-task lifecycle entries
  State lost on crash: all task entries vanish.
  Impact: FSM has no knowledge of inflight tasks after restart.
          Active tasks continue executing in Back but FSM cannot route
          their completions (task_id not in task_state -> silently dropped).

FSM Controller (controller.py)
  ._history: list[TypedHistoryEntry]            <- conversation history
  ._active_task_ids: set[str]                   <- currently tracked tasks
  ._task_dispatch_turns: dict[str, int]         <- task->turn mapping
  State lost on crash: conversation history and all turn metadata vanish.
  Impact: Front LLM has no history context after restart.
          Same-turn-completion suppression logic fails (dispatch_turn
          unknown -> duplicate PRESENT).

FSMTurnState (turn_state.py)
  .pending_results: deque[dict]                 <- queued weave results
  State lost on crash: pending weave results vanish.
  Impact: Task results completed before crash are silently lost.
          User never sees them. No weave delivery.
```

**Problem 1 -- 6 independent in-memory stores with no coordination:**

The FSM has CancellationHandler._tokens, SuspensionManager._active,
SuspensionManager._contexts, HILCoordinator._pending_requests,
TaskBridge._task_state, and controller._history. These are six
independent dicts/sets/lists that must all be consistent. Today they are
updated independently in different handler methods. If any handler
fails mid-execution (exception between two dict updates), the stores
diverge. Example: `_on_task_suspended` stores context in
SuspensionManager._contexts (L1340) then updates TaskBridge (L1341).
If TaskBridge.suspend_task raises, the context is stored but the task
status is wrong.

**Problem 2 -- Dual suspension paths create ambiguity (WB 12.2.F):**

SuspensionManager has TWO API surfaces:

| Path | Methods | Used By | When |
|------|---------|---------|------|
| Async | suspend(), resolve() | HILCoordinator (via handle_needs_human) | When coordinator is wired |
| Sync | store_context(), pop_context() | FSM controller directly | Always (L1340: store_context) |

The FSM controller ALWAYS uses store_context/pop_context (sync path)
for the suspension payload. The HILCoordinator ALSO uses the async path
through its internal SuspensionManager. When both are active:

```python
# controller._on_task_suspended (L1340):
self._suspension_manager.store_context(task_id, payload)  # sync path

# But set_hitl_coordinator (L390) REPLACES suspension_manager:
self._suspension_manager = coordinator._suspension_mgr  # now shared
```

After set_hitl_coordinator, the controller's sync store_context and
the coordinator's async suspend() operate on the SAME SuspensionManager
instance but through different API surfaces. store_context puts payload
in `_contexts` dict. suspend() puts SuspensionRequest in `_active` dict.
These are DIFFERENT dicts. The task appears suspended in one path but
not the other.

**Problem 3 -- HILCoordinator has its own SuspensionManager:**

When set_hitl_coordinator is called (L385-394), the FSM's
_suspension_manager is REPLACED with the coordinator's internal one.
This means there is only ONE SuspensionManager at runtime. But the
coordinator creates it with on_timeout_fn bound to its own
_handle_timeout. The FSM has no visibility into timeout behavior --
if the coordinator's timeout fires, it calls _handle_timeout which
pops from _pending_requests, but the FSM is not notified. The timeout
callback in bootstrap.py (L199-215) creates a synthetic task.failed
envelope, but this goes through the bus -> FSM, not through a direct
state update. There is a window where the coordinator has cleared
the HITL state but the FSM has not yet received the failed envelope.

**Problem 4 -- TaskStateEntry.pending_hil is the only crash recovery
mechanism, and it is insufficient:**

hitl_persistence.py's TaskStateEntry has a `pending_hil` field that
stores the serialized HILRequest via `to_persistence()`. This is the
ONLY field designed for crash recovery. But:

- TaskStateEntry itself lives in TaskStateSection which is in-memory.
- pending_hil stores the HILRequest but NOT the ReAct history that
  Back needs for resume (react_history is in SuspensionRequest, not
  HILRequest). The FSM stores react_history separately in
  SuspensionManager._contexts dict (the sync path).
- On crash: TaskStateEntry.pending_hil survives (if SS was persisted
  to disk). But the react_history in _contexts is gone. Resume after
  crash = Back restarts from scratch.

**Problem 5 -- No ledger exists yet (M1 dependency):**

M1 creates: CanonicalEventMeta, LedgerWriter, ILedgerStore,
InMemoryLedgerStore, projection functions, replay test. M1 also adds
dual-write at mutation points (ledger + in-memory). M9 assumes M1
is complete and converts the in-memory stores into projections OVER
the ledger. If M1's ledger is incomplete, M9 cannot proceed.

**Problem 6 -- History is not event-sourced:**

controller._write_history (L526) directly appends TypedHistoryEntry
to self._history list. There is no event that represents a history
write. M1 issue 1.2.3 plans to emit canonical events at each
_write_history call, but the actual TypedHistoryEntry -> canonical
event mapping needs to be implemented in M9 to make history a
projection.

### M9 LLM Interaction Model

| Actor | Current Behavior | Problem | After M9 |
|-------|-----------------|---------|----------|
| Front (HITL_RELAY) | Receives suspension payload from FSM with question + options. LLM translates structured HITL to natural conversation. | If process crashes after HITL_RELAY delivery but before user response, the HITL context is lost. User's response arrives at a restarted FSM that has no record of the pending HITL. Response is silently dropped. | On restart, ledger replay rebuilds pending_requests in HILCoordinator. The timeout timer restarts with remaining time. User's response is correctly routed to the reconstructed HITL context. LLM behavior unchanged. |
| Front (HITL_RESOLVE) | Receives user's HITL answer. LLM builds resume_context with resolution + findings_so_far + tool_history. Emits task.resume. | findings_so_far (ReAct history) is in SuspensionManager._contexts (in-memory). If crash happened between suspend and resolve, this is gone. resume_context has no findings -> Back restarts from scratch, re-executing tools (wasted tokens, duplicate side effects). | ReAct history is part of the ledger event (task.suspended canonical event carries react_history in payload). On restart, project_hitl_state() rebuilds_contexts from task.suspended events. resume_context is complete. Back resumes from saved history (zero-waste). |
| Back (resume after crash) | Back receives task.resume with resume_context.findings_so_far. Back replays ReAct history and continues from last_iteration. | If findings_so_far is empty (crash lost the data), Back must re-discover capabilities, re-invoke tools, re-do everything. For approval flow: Back may call invoke_capability without re-approval (safety violation). | findings_so_far is always available (projected from ledger). hil_history is reconstructed (L2 defense check can verify prior approval existed). Back never re-executes already-approved actions without re-approval. |
| Front (deferred HITL) | _surface_deferred_hitl (L1739) checks task_bridge.get_suspended_tasks() after reaching LISTENING. If context exists in _contexts, surfaces the first pending HITL. | If process crashes after storing context but before surfacing, the deferred HITL is lost on restart. The task stays SUSPENDED forever (no timeout watcher recreated). | On restart, project_task_states() rebuilds the SUSPENDED status. project_hitl_state() rebuilds the context. _surface_deferred_hitl fires normally. Timeout watcher is recreated with remaining time. |

---

### E9.1 -- Cancel Protocol Ledger Migration

Source: WB 12.2.D, 12.5.3

**Rationale:** CancellationHandler holds cancel state in two in-memory
collections: `_tokens: dict[str, CancellationToken]` (active tokens) and
`_cancelled_tasks: set[str]` (dedup set). On crash, both are lost. A task
that was cancelled before the crash appears un-cancelled after restart.
Back continues executing. Late-completion dedup fails. This epic makes
cancel state a ledger projection: `task.cancelled` events in the ledger
determine which tasks are cancelled, and the in-memory set becomes a
cache that can be rebuilt from replay.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 9.1.1 | Make CancellationHandler a ledger projection consumer. Add constructor parameter `ledger: LedgerWriter | None`. When ledger is provided: (a)`register_task()` emits a `task.created` canonical event to ledger before adding token to _tokens. (b) `request_cancel()` emits `task.cancelled` canonical event to ledger before adding to _cancelled_tasks. (c) `confirm_cancel()` emits `task.cancel.confirmed` event (new schema) before removing from set. The in-memory_tokens and _cancelled_tasks become caches populated from both runtime calls AND ledger replay. | WB 12.2.D | No direct LLM impact. Cancel token state does not affect the LLM prompt. But crash recovery preserves the cancelled_tasks set, so the FSM correctly presents "task was cancelled" instead of presenting stale results from a zombie task. Without this, the Front LLM would present a completed-result for a task the user cancelled before the crash, which is confusing. |
| 9.1.2 | Implement cancel state projection: `project_cancel_state(events) -> (dict[str, CancellationToken], set[str])`. Input: ledger event stream filtered to task.created + task.cancelled + task.cancel.confirmed. Output: reconstructed _tokens and_cancelled_tasks. Logic: for each `task.created`, create CancellationToken. For each `task.cancelled`, mark token as cancelled and add to set. For each `task.cancel.confirmed`, remove from set. Place in `ledger/projections.py` alongside existing projections from M1. | WB 12.2.D | No direct LLM impact. Enables crash recovery for cancel protocol. |
| 9.1.3 | Add CancellationHandler.rebuild_from_events(events) method. On startup, FSM calls rebuild_from_events with the full ledger stream for the session. This replaces the current empty-dict initialization. After rebuild: _tokens contains all non-terminal tasks with correct is_cancelled state, _cancelled_tasks contains all cancelled task_ids not yet confirmed. The asyncio.Event inside CancellationToken is re-set for cancelled tokens so wait_for_cancel() works correctly on rebuilt tokens. | WB 12.2.D | No direct LLM impact. After crash recovery, any Back worker that calls token.check() on a cancelled token will correctly raise TaskCancelledError, even though the original cancel() call happened before the crash. |
| 9.1.4 | Handle late-completion dedup after crash recovery. Test scenario: (a) FSM dispatches task T1. (b) User cancels T1. (c) Process crashes. (d) On restart, ledger replay rebuilds _cancelled_tasks = {"T1"}. (e) T1 completes in Back (Back was running during crash). (f) FSM receives task.complete for T1. (g) is_cancelled(T1) returns True -> FSM correctly presents "completed despite cancel" message. Without crash recovery,_cancelled_tasks would be empty -> T1 appears as normal completion -> wrong presentation. Test in `tests/poc/test_m09_cancel_recovery.py`. | WB 12.2.D | Front LLM receives the correct presentation mode: "completed despite cancellation" (via handle_late_completion returning True) instead of normal PRESENT mode. This changes the prompt scenario_data and the LLM's response tone. |

---

### E9.2 -- Suspension Protocol Ledger Migration + API Consolidation

Source: WB 12.2.D, 12.2.F, 12.5.3

**Rationale:** SuspensionManager has the worst state-loss problem: it
holds the react_history (in_contexts via store_context) that Back needs
to resume without repeating tool calls. Lost react_history means Back
re-executes tools (wasted LLM tokens, potential duplicate side effects).
Additionally, the dual sync/async API (store_context/pop_context vs
suspend/resolve) creates ambiguity about which dict holds the authoritative
state. This epic makes suspension state a ledger projection AND
consolidates to one lifecycle API.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 9.2.1 | Make SuspensionManager a ledger projection consumer. Add constructor parameter `ledger: LedgerWriter | None`. When ledger is provided: (a) suspend() emits`task.suspended` canonical event (carrying full SuspensionRequest including react_history and tool_state) to ledger before adding to _active. (b) resolve() emits `task.resumed` canonical event (carrying SuspensionResolution) to ledger before removing from _active. (c) _watch_timeout emits `task.hil.timed_out` event to ledger when timeout fires. In-memory_active dict becomes a cached projection. | WB 12.2.D | **Critical LLM impact via crash recovery.** The task.suspended ledger event carries react_history. On crash recovery, project_suspension_state() rebuilds_active with the full SuspensionRequest including react_history. When the user responds after restart, build_resume_context() (hitl_wiring.py) gets the complete findings_so_far from the rebuilt context. Back resumes from saved history instead of from scratch. This saves O(N) LLM iterations where N = iterations completed before suspension. |
| 9.2.2 | Consolidate to single lifecycle API. Remove the sync path as the primary API. Make the async suspend/resolve path THE canonical path. Implement new sync wrappers that delegate to the canonical async path: `store_context_sync(task_id, payload)` calls `asyncio.get_event_loop().run_until_complete(self.suspend(...))` OR stores to a pending queue that is drained by the next async tick. The FSM controller (L1340) changes from `self._suspension_manager.store_context(task_id, payload)` to `await self._suspension_manager.suspend(SuspensionRequest.from_payload(payload))`. Since the FSM handler methods are sync today, this requires either: (a) making _on_task_suspended async (preferred), or (b) keeping a sync bridge that enqueues the suspend call for the next async tick. | WB 12.2.F | No direct LLM impact. Internal refactor that eliminates the dual-dict ambiguity (_active vs_contexts). After consolidation, there is ONE authoritative state: _active dict populated by suspend(), drained by resolve(). |
| 9.2.3 | Implement suspension state projection: `project_suspension_state(events) -> (dict[str, SuspensionRequest], dict[str, int])`. Input: ledger events filtered to task.suspended + task.resumed + task.hil.timed_out. Output: reconstructed_active dict (task_id -> SuspensionRequest) and_suspension_counts dict (task_id -> count). Logic: for each task.suspended, add to _active and increment count. For each task.resumed or task.hil.timed_out, remove from _active. Place in `ledger/projections.py`. | WB 12.2.D | Enables crash recovery for suspension protocol. The react_history in the projected SuspensionRequest is the critical payload for zero-waste Back resume. |
| 9.2.4 | Add SuspensionManager.rebuild_from_events(events) method. On startup, FSM calls rebuild_from_events with the session ledger stream. Rebuilds _active,_contexts (removed in 9.2.2 -- now just _active),_suspension_counts. Does NOT restart timeout watchers -- timeout restart is handled separately in 9.2.5. | WB 12.2.D | After crash recovery, SuspensionManager knows which tasks are suspended. _surface_deferred_hitl (controller.py L1739) can find them and re-present. |
| 9.2.5 | Restart timeout watchers after crash recovery. For each task in _active after rebuild, calculate remaining timeout: `remaining_ms = original_timeout_ms - (now_ms - suspended_at_ms)`. If remaining_ms <= 0, immediately trigger timeout (emit task.hil.timed_out, auto-cancel). If remaining_ms > 0, start new asyncio.Task with `asyncio.sleep(remaining_ms / 1000)`. This ensures that HITL timeouts are enforced even across process restarts. Store `suspended_at_ms` in the task.suspended canonical event payload (from SuspensionRequest.created_at_ns / 1e6). | WB 12.2.D | If a suspension had 120s timeout and the process crashed at T=60s, the restarted system gives the user the remaining 60s to respond. Without this, the timeout is never enforced after crash -> task stays SUSPENDED forever -> user confused, Back blocked indefinitely. |

---

### E9.3 -- HITL Coordinator Ledger Migration

Source: WB 12.2.D, 12.5.3

**Rationale:** HILCoordinator holds _pending_requests and _hil_counts in
memory. Lost _pending_requests means the coordinator cannot validate
that a user response matches an outstanding HITL request (the response
could be for a different HITL or a stale one). Lost _hil_counts means
the max_rounds limit resets to 0 after crash, allowing more HITL rounds
than the policy permits. Lost hil_history (in TaskStateEntry) means L2
defense-in-depth cannot verify prior approvals.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 9.3.1 | Make HILCoordinator a ledger projection consumer. Add constructor parameter `ledger: LedgerWriter | None`. When ledger is provided: (a) handle_needs_human() emits`task.hil.requested` canonical event (M1 schema) to ledger before adding to _pending_requests. (b) handle_user_response() emits `task.hil.resolved` canonical event to ledger before removing from _pending_requests. (c) _handle_timeout() emits `task.hil.timed_out` event before cleanup. (d) validate_before_invoke() reads hil_history from ledger projection instead of from TaskStateEntry.hil_history (which may be stale after crash). | WB 12.2.D | **Safety-critical LLM impact.** L2 defense-in-depth (validate_before_invoke at hitl_coordinator.py L413-464) checks hil_history for prior approvals before allowing side-effect execution. If crash loses hil_history, the L2 check sees no prior approval -> blocks execution (safe fail, but frustrating: user already approved). With ledger projection: hil_history is rebuilt from task.hil.requested + task.hil.resolved events. L2 check correctly finds the prior approval -> execution proceeds without re-asking user. |
| 9.3.2 | Implement HITL state projection: `project_hitl_state(events) -> (dict[str, HILRequest], dict[str, int], dict[str, list[dict]])`. Input: ledger events filtered to task.hil.requested + task.hil.resolved + task.hil.timed_out. Output:_pending_requests (active HITL requests),_hil_counts (per-task round counts), hil_histories (per-task HITL interaction history for L2 checks). Logic: for each task.hil.requested, add to _pending and increment count. For each task.hil.resolved, move from_pending to hil_histories. For each timed_out, remove from _pending and record timeout in history. | WB 12.2.D | Enables crash recovery for HITL protocol including L2 defense history. |
| 9.3.3 | Add HILCoordinator.rebuild_from_events(events) method. On startup, rebuilds _pending_requests, _hil_counts, and injects hil_history into TaskStateEntry (via task_bridge). Delegates timeout restart to SuspensionManager.rebuild_from_events (E9.2.4/9.2.5) since the coordinator delegates timeout management to its internal SuspensionManager. | WB 12.2.D | After crash recovery, HILCoordinator enforces correct max_rounds limits. If task T1 had 1 HITL round before crash, the count is correctly 1 after restart. The second HITL round is the last allowed, not the first (which would be incorrect without rebuild). |
| 9.3.4 | Crash recovery integration test for HITL flow. Scenario: (a) Dispatch task T1. (b) Back suspends T1 for approval (HITL round 1). (c) User approves. (d) Back invokes capability. (e) Back suspends T1 again for clarification (HITL round 2). (f) PROCESS CRASH. (g) Restart with ledger replay. (h) Verify: _pending_requests contains T1's clarification request with correct question + options. (i) Verify: _hil_counts[T1] == 2 (at limit). (j) Verify: hil_history[T1] contains the approval interaction. (k) User responds to clarification. (l) Back attempts 3rd HITL round -> SuspensionLimitExceeded (correctly enforced). (m) Verify: L2 validate_before_invoke finds the prior approval in hil_history (from ledger). Test in `tests/poc/test_m09_hitl_recovery.py`. | WB 12.2.D | Validates that all LLM-facing HITL flows work correctly after crash recovery. The Front LLM's HITL_RELAY mode receives the correct question. The Back LLM's resume receives complete findings_so_far. L2 defense prevents unsafe execution. |

---

### E9.4 -- Task State + History Ledger Migration

Source: WB 12.2.D, 3.A

**Rationale:** TaskBridge wraps TaskStateSection (in-memory). The FSM's
_history list is the conversation timeline that feeds Front's prompt
context. Both are lost on crash. After M1, dual-write exists (ledger +
in-memory). M9 makes the in-memory stores into projections: on startup
they are empty, rebuilt from ledger. During runtime they are updated
both via ledger write (source of truth) and in-memory (cache). This
epic is the culmination of the event-sourcing migration -- once task
state and history are ledger-projected, ALL mutable state in the FSM
is a projection.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 9.4.1 | Make TaskBridge a ledger projection consumer. Add ledger parameter. Each lifecycle method (dispatch_task, activate_task, suspend_task, resume_task, complete_task, fail_task, cancel_task in task_bridge.py L126-263) emits the corresponding task lifecycle canonical event to ledger BEFORE updating the in-memory TaskStateSection. The ledger write is the commitment point: if it fails, the in-memory update is skipped and the operation is rejected. Pattern: `ledger.append(TaskCompleted(...)) -> task_state.update_status(task_id, COMPLETED)`. | WB 12.2.D | No direct LLM impact on task state. But task state feeds the Front prompt's task_status_summary (scenario_data field). If task state is lost on crash, the prompt tells the LLM "no active tasks" when tasks are actually running. With ledger projection: task state is correctly rebuilt, and the LLM knows what tasks are active. |
| 9.4.2 | Implement task state projection: `project_task_states(events) -> TaskStateSection`. Input: ledger events filtered to task.created + task.progressed + task.completed + task.failed + task.cancelled + task.suspended + task.resumed. Output: reconstructed TaskStateSection with correct status, pending_hil, hil_suspensions_count for each task. Logic: apply events in sequence order, each event transitions the task's status. Place in `ledger/projections.py`. M1 defines a skeleton; M9 implements the full version with HITL fields (pending_hil, hil_suspensions_count from task.suspended/task.hil.requested events). | WB 12.2.D | Enables crash recovery for all task state including HITL fields. |
| 9.4.3 | Make FSM history ledger-projected. Replace controller._write_history (L526) with a method that emits a canonical conversation event to the ledger, THEN appends the TypedHistoryEntry to the in-memory _history list. Each history entry type maps to a canonical event type: "user_input" -> UserInputReceived, "response" -> not a separate event (derived from response.final), "hitl_request" -> HILRequested (already emitted by HILCoordinator in 9.3.1), "hitl_response" -> HILResolved (already emitted), "system" -> new ConversationSystemNote event type. The _history list becomes a projection: on startup, project_history(ledger.read_all()) produces the same list that would exist if the session ran without crashes. | WB 3.A | **Direct LLM impact.** Front reads history_active from SessionState to build the conversation context in the prompt. If history is empty after crash, the LLM has no memory of the conversation. Every response starts fresh: "Hi! How can I help?" instead of continuing where it left off. With ledger-projected history: the LLM sees the complete conversation after restart and responds naturally. This is the most user-visible improvement in M9. |
| 9.4.4 | Make pending_results (weave queue) ledger-projected. FSMTurnState.enqueue_result (turn_state.py L50-78) emits `conversation.weave.candidate` canonical event to ledger before appending to pending_results deque. drain_results emits `conversation.weave.emitted` for each drained result. On startup, project_pending_results(events) rebuilds the deque: weave.candidate events minus weave.emitted events = still-pending results. This ensures task results that completed before crash are not silently lost -- they are woven after restart. | WB 12.2.D | **Direct LLM impact via weave recovery.** If 3 tasks completed before crash and none were woven yet, those results are in pending_results. Without ledger: lost. After restart, user gets no results. With ledger projection: pending_results is rebuilt with the 3 results. When the FSM reaches LISTENING, the weave path fires and the Front LLM presents all 3 results. The user sees the complete picture. |

---

### E9.5 -- Unified Crash Recovery + Observability

Source: WB 12.2.D, 9, 13.5

**Rationale:** E9.1-E9.4 add rebuild_from_events methods to each protocol
component. This epic wires them into a unified crash recovery sequence
called during FSM startup, adds observability for the recovery process,
and provides the deterministic fallback when the ledger is unavailable.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 9.5.1 | Implement unified FSM crash recovery orchestrator. Create `poc/k1_poc/ledger/recovery.py` with class `CrashRecoveryOrchestrator`. Method: `async recover(fsm: ConciergeController, ledger: ILedgerStore, session_id: str) -> CrashRecoveryReport`. Recovery sequence (order matters): (1) Read all ledger events for session_id. (2) project_task_states -> rebuild TaskBridge._task_state. (3) project_cancel_state -> rebuild CancellationHandler. (4) project_suspension_state -> rebuild SuspensionManager (including react_history). (5) project_hitl_state -> rebuild HILCoordinator (including hil_counts, hil_history). (6) project_pending_results -> rebuild FSMTurnState.pending_results. (7) project_history -> rebuild controller._history. (8) Restart timeout watchers for active suspensions. (9) Derive FSM state from latest events (if last event was task.suspended -> CLARIFYING_WORKER, if task.completed queued -> WEAVING, etc.). Return CrashRecoveryReport with counts of recovered tasks, suspensions, pending results, and history entries. | WB 12.2.D, 9 | **Highest-impact issue in M9.** This is the single entry point for crash recovery. Without it, each protocol rebuilds independently and the FSM state must be manually reconstructed. With it: one call to `recover()` brings the entire FSM + protocols back to the pre-crash state. The LLM experience is seamless -- user continues the conversation as if nothing happened. |
| 9.5.2 | Wire recovery into bootstrap. In kernel/bootstrap.py, after FSM creation (L160-180): if ledger store exists and has events for the session, call CrashRecoveryOrchestrator.recover(). If recovery fails (corrupt ledger, schema mismatch), log error and fall back to empty-state initialization (same as today). Add config flag: `ledger.crash_recovery_enabled: true` (default true). When false, FSM starts fresh regardless of ledger content. This enables safe rollout. | WB 12.2.D | No direct LLM impact. But without this wiring, crash recovery never runs. |
| 9.5.3 | Derive FSM state from ledger on recovery. The FSM state (ConciergeState) is not explicitly stored in the ledger -- it is derived from the latest events. Decision table: (a) If last task event is task.suspended and no task.resumed followed -> CLARIFYING_WORKER. (b) If pending_results is non-empty and last response.final was processed -> WEAVING (schedule weave flush). (c) If any task is ACTIVE (task.created without task.completed/failed/cancelled) -> COMPANIONING. (d) If last event is user.input without response.final -> DISPATCHING (user message was received but not yet processed; may need replay). (e) Otherwise -> LISTENING (clean state). This derivation must match the actual FSM transition logic. Add exhaustive test coverage for each case. | WB 12.2.D | FSM state determines which prompt mode Front uses. Wrong FSM state after recovery -> wrong prompt mode -> LLM generates wrong type of response. LISTENING when should be CLARIFYING_WORKER -> user's HITL response gets a fresh STANDARD response instead of HITL_RESOLVE. COMPANIONING when should be LISTENING -> user's new topic gets queued in FrontLock instead of starting a new turn. |
| 9.5.4 | Add recovery observability. Emit `k1.ledger.recovery.completed.v1` event on bus after recovery with payload: session_id, events_replayed, tasks_recovered, suspensions_recovered, pending_results_recovered, history_entries_recovered, fsm_state_derived, recovery_duration_ms. Also emit `k1.ledger.recovery.failed.v1` if recovery fails (with error_type, error_message). These events are RELAXED delivery (observability only). Log recovery summary at INFO level. | WB 13.5 | No direct LLM impact. Enables operators to monitor recovery health. |
| 9.5.5 | Add deterministic fallback when ledger is unavailable. If ILedgerStore raises on read (corrupt DB, missing file, etc.), CrashRecoveryOrchestrator falls back to: (a) Initialize all protocols with empty state (same as current behavior). (b) If hitl_persistence data exists in SessionState (the old TaskStateEntry.pending_hil mechanism), use HILCoordinator.recover_pending_hitl() as a partial recovery. (c) Log warning: "Ledger unavailable, using degraded recovery." This ensures M9 never makes things WORSE than current behavior -- the ledger is additive. | WB 12.2.D | In degraded mode, LLM experience is identical to current (pre-M9) behavior: no crash recovery, fresh start. This is the safety net. |

---

### M9 Protocol Lifecycle ReAct Loop Interaction Audit

**Constraints derived from code reading (protocols/cancellation.py,
cancel_handler.py, cancel_events.py, suspension.py, suspension_manager.py,
suspension_events.py, hitl.py, hitl_coordinator.py, hitl_flow.py,
hitl_pipeline.py, hitl_persistence.py, hitl_wiring.py, weave_batcher.py,
weave_state.py, fsm/controller.py, fsm/task_bridge.py, fsm/turn_state.py,
kernel/bootstrap.py):**

| # | Constraint | Code Evidence | M9 Implication |
|---|-----------|---------------|----------------|
| P1 | CancellationHandler holds tokens and dedup set in pure in-memory dicts with no persistence mechanism. | cancel_handler.py L56: `self._tokens: dict[str, CancellationToken] = {}`, L57: `self._cancelled_tasks: set[str] = set()` | E9.1 adds ledger write before dict mutation. rebuild_from_events reconstructs both dicts from task.created + task.cancelled events. |
| P2 | SuspensionManager has dual state stores: _active (async path, holds SuspensionRequest) and_contexts (sync path, holds raw payload dict). When HILCoordinator is wired, both point to the same SuspensionManager instance but the FSM uses _contexts (sync) while the coordinator uses_active (async). | suspension_manager.py L88: `self._active: dict[str, SuspensionRequest] = {}`, L89: `self._contexts: dict[str, dict] = {}`. controller.py L1340: `self._suspension_manager.store_context(task_id, payload)` (sync). | E9.2.2 consolidates to single _active dict. The_contexts dict is removed (or becomes an alias for _active serialization). FSM handler converts payload to SuspensionRequest before calling suspend(). |
| P3 | react_history is stored ONLY in SuspensionManager._contexts (sync path) or SuspensionRequest.react_history (_active, async path). It is NOT in TaskStateEntry.pending_hil (which stores HILRequest, not SuspensionRequest). The FSM builds resume_context from pop_context() at L1417 which reads from_contexts. | controller.py L1417: `stored_context = self._suspension_manager.pop_context(task_id)`, L1425: `findings_so_far=stored_context.get("react_history", [])`. hitl_persistence.py L125: `suspend()` stores `hil_request.to_persistence()` which does NOT include react_history. | E9.2.1 ensures the task.suspended canonical event carries react_history in its payload. project_suspension_state() rebuilds_active with the complete SuspensionRequest including react_history. |
| P4 | HILCoordinator creates its OWN SuspensionManager (L167: `self._suspension_mgr = SuspensionManager(...)`). When set_hitl_coordinator is called (controller.py L390), the FSM's _suspension_manager is REPLACED with the coordinator's. Only ONE SuspensionManager exists at runtime. | hitl_coordinator.py L167, controller.py L390: `self._suspension_manager = coordinator._suspension_mgr` | E9.3.3's rebuild wires through HILCoordinator which delegates to its internal SuspensionManager. No need to rebuild two managers -- there is only one after set_hitl_coordinator. |
| P5 | The FSM's _on_task_suspended handler (L1298-1370) does NOT call HILCoordinator.handle_needs_human(). It directly calls_suspension_manager.store_context() and _task_bridge.suspend_task(). The HILCoordinator path (handle_needs_human) is used at a HIGHER layer (Back's submit_result). The FSM handler is the TRANSPORT-level handler that runs when the bus delivers task.suspended.v1. | controller.py L1340: `self._suspension_manager.store_context(task_id, payload)`, L1341: `self._task_bridge.suspend_task(task_id)`. No call to self._hil_coordinator.handle_needs_human(). | E9.2.2 must change the FSM handler to go through the canonical suspend() path. The handler should construct a SuspensionRequest from the payload and call suspend(). This ensures the ledger write happens (via suspend()) for every suspension, not just those initiated through HILCoordinator. |
| P6 | TypedHistoryEntry (controller.py L174) is a TypedDict with: entry_type, role, text, source, timestamp_ms, turn_number, task_id, envelope_id, parent_id, metadata. It has NO event_id or canonical metadata. It is appended to self._history list at L526 (_write_history). | controller.py L174-196 (TypedHistoryEntry TypedDict), L526-570 (_write_history). | E9.4.3 must map each TypedHistoryEntry to a canonical event type. The _history list is rebuilt from the ledger via project_history(). The projected TypedHistoryEntry must have all the same fields as the runtime one. |
| P7 | pending_results in FSMTurnState (turn_state.py L44) is a simple deque of dicts with: task_id, result, envelope_id, parent_id, queued_at_ns. No canonical event metadata. | turn_state.py L66-76: `enqueue_result()` appends `{"task_id": task_id, "result": result, ...}` | E9.4.4 emits weave.candidate on enqueue and weave.emitted on drain. Projection subtracts emitted from candidate to get pending. |
| P8 | Bootstrap wires HILCoordinator with callbacks for timeout (L199-215: builds synthetic task.failed envelope and publishes on bus). This callback creates a bus event but does NOT write to ledger. | bootstrap.py L199-215: `async def _hitl_timeout_handler(task_id): ... bus.publish(build_task_failed(...))` | E9.3.1 adds ledger write in HILCoordinator._handle_timeout() BEFORE the bus callback fires. The timeout is recorded in the ledger first, then the bus event propagates for FSM handling. |

---

### Recommended Execution Order

1. **9.4.1** (TaskBridge ledger integration -- most fundamental, all protocols depend on task state)
2. **9.4.2** (task state projection -- needed by all subsequent projections)
3. **9.1.1** (CancellationHandler ledger integration -- simplest protocol)
4. **9.1.2** (cancel state projection)
5. **9.1.3** (cancel rebuild_from_events)
6. **9.2.1** (SuspensionManager ledger integration -- carries react_history)
7. **9.2.2** (consolidate suspension API -- eliminates dual-dict ambiguity)
8. **9.2.3** (suspension state projection)
9. **9.2.4** (suspension rebuild_from_events)
10. **9.3.1** (HILCoordinator ledger integration)
11. **9.3.2** (HITL state projection)
12. **9.3.3** (HITL rebuild_from_events)
13. **9.4.3** (history ledger-projected -- depends on all event types being defined)
14. **9.4.4** (pending_results ledger-projected)
15. **9.5.1** (unified crash recovery orchestrator -- ties all rebuilds together)
16. **9.5.3** (FSM state derivation from ledger)
17. **9.5.2** (wire recovery into bootstrap)
18. **9.2.5** (restart timeout watchers -- after recovery wiring)
19. **9.1.4** (late-completion dedup recovery test)
20. **9.3.4** (HITL crash recovery integration test)
21. **9.5.4** (recovery observability events)
22. **9.5.5** (deterministic fallback when ledger unavailable)

---

## M10: UltraBERT Integration & Tier Routing

**Goal:** Replace StubPhase1Pipeline with real UltraBERT v4 (12 heads,
~20ms, 149M params) as the authoritative Phase 1 deterministic pass.
Wire all 12 head outputs into SessionState sections (control, scoreboard,
affective_now) BEFORE the Front LLM starts. Make complexity tier the
single routing authority for LOW/MEDIUM/HIGH dispatch. Implement real
HIGH-tier Orchestrator/Planner handoff (currently fails fast). Ensure
the adapter from k0/runtime/ultrabert_adapter.py is reusable in the
K1 POC via a thin K1-side integration layer.

**Gate:** StubPhase1Pipeline replaced. Every user turn runs UltraBERT
first (~20ms). All 12 head outputs persisted to SS before Front reads.
Front reads complexity_tier from SS control (not from implicit "LOW"
default). HIGH-tier tasks route to Orchestrator -> Planner -> Fabric
instead of emitting task.failed. Safety band from UltraBERT drives
CRISIS short-circuit. Fallback to stub when UltraBERT is unavailable
(GPU-less machine, import failure) with degraded-mode metric emitted.

**Depends on:** M4 (SessionState binding -- ControlExtension.bind_control_section),
M5 (Front ReAct loop reads SS), M6 (HITL lifecycle -- safety band drives
approval flow).

### Why UltraBERT Integration Is Hard (Code Audit Findings)

**Current Phase 1 pipeline -- what exists and what is missing:**

```
Phase 1 Data Flow (Current POC):

user.input arrives at FSM
    |
[_on_user_input] transitions to DISPATCHING
    |
[_run_phase1(envelope)]  <-- controller.py L774-799
    |
    +--> TurnLock.acquire("phase1")
    |
    +--> result = self._phase1_pipeline.classify(text)
    |        |
    |        +-- StubPhase1Pipeline.classify(text)  <-- phase1.py L200-240
    |        |     Returns hardcoded keywords:
    |        |       "hotel"|"flight" -> MEDIUM
    |        |       "doctor"|"dentist" -> MEDIUM
    |        |       everything else -> LOW
    |        |     NO UltraBERT. NO real classification.
    |        |     NO safety band. NO entity extraction.
    |        |     NO emotion detection. NO domain context.
    |        |
    |        +-- Phase1Result with 11 fields:
    |              intents, entities, salience_map,
    |              primary_emotion, emotion_confidence,
    |              valence, arousal, intent_classification,
    |              domain_context, safety_band, complexity_tier
    |
    +--> self._control_ext.set_complexity_tier(result.complexity_tier)
    |        |
    |        +-- ConciergeControlExtension._complexity_tier = "LOW"  (in-memory only)
    |            controller.py L785. Does NOT write to ControlSection.
    |            Phase 1 result lives ONLY in control_ext._complexity_tier
    |            and in the metadata attached to the last history entry.
    |
    +--> Attach Phase 1 metadata to last history entry
    |        |
    |        +-- last.metadata.update(result.to_metadata())
    |            Stores intent, emotion, safety_band, domain, entities
    |            BUT: only in the history entry (TypedHistoryEntry.metadata)
    |            NOT in SessionState sections.
    |
    +--> TurnLock.release()
    |
    +--> self._deliver_to_front(envelope)
         Front LLM starts. But:
           - SS control has NO intent_classification
           - SS control has NO domain_context
           - SS control has NO safety_band
           - SS control has NO complexity_tier
           - SS scoreboard has NO Phase 1 entities/salience
           - SS affective_now has NO Phase 1 emotion/valence
         Front reads stale/empty values from previous turn or defaults.
```

**Problem 1 -- StubPhase1Pipeline has no real classification:**

`phase1.py` L200-240 uses keyword matching: if "hotel" in text -> MEDIUM.
Everything else defaults to LOW. There is no UltraBERT call. The stub
was sufficient for POC architecture validation but produces wrong tiers
for real user input. A complex multi-step request like "Plan my mom's
surprise birthday party next Saturday" gets classified as LOW (no matching
keywords) when it should be HIGH (multi-domain: scheduling + family +
celebration, multi-entity, temporal ambiguity).

**Problem 2 -- Phase 1 outputs never reach SessionState:**

The whiteboard (WB 17.4-17.6) and architecture diagram (ACKING_CORE,
TWO-PHASE WRITE PER TURN) both mandate that Phase 1 writes to 3 SS
sections BEFORE Front reads. The code does NOT do this:

| Section | What WB 17.6 Requires | What Code Actually Does |
|---------|----------------------|------------------------|
| control | intent_classification, domain_context, safety.band, complexity_tier | `_control_ext.set_complexity_tier()` writes to in-memory wrapper ONLY. No write to ControlSection. ControlSection has IntentClassification, DomainContext, SafetyContext dataclasses but NO method to set them from Phase 1 output. |
| scoreboard | last_user_intent, referent seeds from NER, salience seeds | Phase 1 result has `intents[]`, `entities[]`, `salience_map{}` but `_run_phase1()` never calls `scoreboard.set_intents()` or any scoreboard method. M5 implements update_scoreboard tool for Front but that is Phase 2 (LLM), not Phase 1. |
| affective_now | current_emotion, intensity, valence, arousal, confidence | Phase 1 result has `primary_emotion`, `emotion_confidence`, `valence`, `arousal` but `_run_phase1()` never calls `affective_now.update_emotion()` or any affective method. M5 implements refine_affect tool for Front but that is Phase 2 override. |

**Problem 3 -- ConciergeControlExtension is disconnected from SS:**

`control_extension.py` explicitly says "The wrapper does NOT modify
ControlSection" (L14). It has 3 in-memory fields (_fsm_state,
_active_task_ids,_complexity_tier) that are NEVER synced to the real
ControlSection in SessionState. M4 issue 4.1.2 plans to add
`bind_control_section(section)` + `sync()` but this is NOT yet
implemented. Until that binding exists, Phase 1 writes to control_ext
are invisible to Front (which reads from SS sections).

**Problem 4 -- HIGH tier fails fast:**

`controller.py` L908-925: `_route_via_orchestrator()` checks
`record.tier == ComplexityTier.HIGH` and immediately emits
`task.failed` with reason "HIGH tier not implemented in POC".
The architecture diagram (K1 skeleton) shows HIGH should route
through Orchestrator -> Planner (4-stage pipeline) -> Fabric.
M10 must wire this path or provide a meaningful intermediate step.

**Problem 5 -- No safety-band-driven routing:**

The architecture diagram has a CRISIS_DETECTOR in the SAFETY_GATE
that should short-circuit ALL routing and trigger immediate safety
protocol. The code has NO crisis short-circuit in `_run_phase1()` or
`_on_task_dispatch()`. If UltraBERT classifies safety_band = CRISIS,
the FSM currently ignores it and dispatches normally. The HITL
protocol (M6) has SafetyBand and escalation but it operates at
the task execution level (Back ReAct loop), not at the turn-start
Phase 1 level.

**Problem 6 -- K0 adapter exists but is not wired to K1:**

`k0/runtime/ultrabert_adapter.py` (1244 lines) provides a complete
K0-side integration with:

- Singleton client management (thread-safe lazy init)
- Single-pass analysis cache (LRU/TTL, ~30ms all 12 heads)
- Result adapters: AffectResult, EntityResult, TemporalResult, ActivityResult
- Convenience functions: analyze_affect, extract_entities, classify_activity
- Full analysis: full_analysis() returns dict with all 12 head outputs

BUT: the K1 POC does not import or use this adapter. Phase 1 in the
POC uses StubPhase1Pipeline which has no dependency on UltraBERT.
The adapter is designed for K0's pipeline architecture (P02 storage,
P03 consolidation). K1 needs its own thin integration layer that:
(a) calls the adapter's `full_analysis()` for the single forward pass,
(b) maps the output dict to Phase1Result fields, and
(c) handles the fallback when UltraBERT is unavailable.

**Problem 7 -- Complexity classification is simplistic:**

The architecture diagram shows a multi-factor complexity router:

- Multi-Intent Scorer: `len(intents) + intent_types -> complexity`
- Cross-Domain Detector: `len(domains) > 1 -> complexity bump`
- Complexity Classifier: `primary_intent + multi_factors -> Tier`

The stub does keyword matching -> "MEDIUM" or "LOW". UltraBERT provides
multi-label intent (8 classes) and multi-label ingress (12 domains).
These must be combined through a rule-based complexity classifier that
implements the multi-factor scoring from the architecture diagram.

### M10 LLM Interaction Model

| Actor | Current Behavior | Problem | After M10 |
|-------|-----------------|---------|-----------|
| Front (STANDARD mode) | Reads SS control for complexity_tier. Gets "LOW" (control_ext default) or stale value. Dispatches task with tier="LOW" regardless of actual complexity. | Multi-intent, multi-domain requests get LOW budget (4 iterations). Back cannot discover enough capabilities, runs out of budget, submits partial results. User sees incomplete answer. | Front reads real complexity_tier from SS control (written by Phase 1 UltraBERT). "Plan my mom's birthday" -> MEDIUM (multi-domain). Front dispatches with tier="MEDIUM" (8 iterations). Back gets full tool set + adequate budget. Complete answer. |
| Front (cognitive tools) | update_scoreboard() writes to scoreboard. But scoreboard has NO Phase 1 seeds. Front starts scoreboard updates from empty state each turn. | Front must re-discover intents and entities from scratch via LLM reasoning. Wastes ~1 iteration on scoreboard bootstrapping that UltraBERT could have done in 20ms. | Phase 1 pre-seeds scoreboard with intents, entities, salience. Front's update_scoreboard() REFINES these seeds instead of starting from zero. Write-then-Refine pattern (WB Section 5). Front saves ~1 iteration and has better grounding for pronoun resolution. |
| Front (refine_affect) | refine_affect() overrides affective_now. But affective_now is empty at turn start. Front must first detect emotion from conversation context (expensive). | If user says something emotional but Front's LLM misses the emotion (or rounds are exhausted before refine_affect), affective_now stays empty. Tone matching fails. Response sounds robotic. | Phase 1 writes UltraBERT emotion to affective_now BEFORE Front starts. Front's refine_affect only fires when LLM detects sarcasm/nuance that UltraBERT missed (confidence > 0.8 override). Default tone matching works from turn start. |
| Back (ReAct loop) | Gets tier from dispatch payload. Tier determines tool allowlist and budget. Currently always LOW (4 iterations) unless keywords match. | Budget exhaustion on complex tasks. Back hits iteration_limit before completing multi-step workflows. No spawn_via_fabric, no execute_workflow in LOW allowlist. | Real tier classification. MEDIUM tasks get 8 iterations + spawn/workflow tools. HIGH tasks get 12 iterations + full tool set. Budget matches actual task complexity. |
| Front (dispatch_task) | Reads control_ext.complexity_tier (in-memory) to set tier in TaskDispatch. | Reads from in-memory wrapper, not from SS. If control_ext was not updated (Phase 1 skipped or failed), tier = "LOW". | Reads from SS control section which is written by Phase 1 before Front starts. Even if control_ext binding exists (M4), the SS read is authoritative. |
| Safety (CRISIS) | No crisis short-circuit. CRISIS safety band from UltraBERT is ignored at Phase 1 level. | Potentially unsafe content reaches Front LLM which generates a normal conversational response instead of triggering safety protocol. | Phase 1 checks safety_band. CRISIS -> immediate safety protocol (skip DISPATCHING, emit crisis event, trigger safety handler). RED -> flag for HIL approval. AMBER -> annotate but proceed. GREEN -> normal flow. |

---

### E10.1 -- Real UltraBERT Phase 1 Pipeline

Source: WB 17.4, 17.5, 17.6, K1 Architecture Skeleton (ACKING_CORE, TWO-PHASE WRITE)

**Rationale:** StubPhase1Pipeline returns hardcoded keywords. The architecture
requires a real UltraBERT deterministic pass (~20ms) that classifies intent,
domain, safety, emotion, entities, and complexity BEFORE the Front LLM starts.
The k0/runtime/ultrabert_adapter.py already provides the full integration with
the familyos_ultrabert library (pip-installed). This epic creates a K1-side
integration layer that bridges the K0 adapter to the Phase1Pipeline protocol.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 10.1.1 | Create `poc/k1_poc/fsm/ultrabert_phase1.py` implementing Phase1Pipeline protocol. Constructor takes optional `ultrabert_adapter` (defaults to k0/runtime import). Method `classify(text) -> Phase1Result`: (a) Call `full_analysis(text)` from the k0 adapter (single forward pass, ~20ms, all 12 heads). (b) Map output dict to Phase1Result: `result["intent"]` -> `intent_classification`, `result["ingress"]` -> `domain_context`, `result["safety"]` -> `safety_band`, `result["sentiment"]` -> map via SENTIMENT_TO_VALENCE to `valence`, `result["emotions"][0]` -> `primary_emotion`, `result["entities"]` + `result["general_entities"]` -> `entities[]`, `result["temporal"]` -> (not in Phase1Result, store in metadata). (c) If full_analysis returns None (UltraBERT unavailable): fall back to StubPhase1Pipeline.classify(text) and log warning. | WB 17.4 | **Foundational LLM impact.** Every subsequent issue depends on this. The LLM prompt for Front is built AFTER Phase 1 runs. If Phase 1 produces garbage (keyword stub), the prompt has wrong context. If Phase 1 produces real UltraBERT output, the prompt has accurate intent/domain/safety/emotion grounding. The difference between "I think you want to check weather" (wrong intent from stub) and "I understand you want to plan a birthday celebration" (correct multi-intent from UltraBERT). |
| 10.1.2 | Implement multi-factor complexity classifier inside UltraBERTPhase1Pipeline. After UltraBERT returns multi-label intent (up to 8) and multi-label ingress (up to 12 domains), compute complexity_tier using the architecture diagram's COMPLEXITY_ROUTER rules: (a) Multi-Intent Score: if `len(all_intents) > 1` -> +1 complexity. (b) Cross-Domain Score: if `len(active_domains) > 1` -> +1 complexity. (c) Intent-Type Score: if primary_intent in {"set_reminder", "seek_advice", "reflect"} and has entities with temporal ambiguity -> +1 complexity. (d) Safety escalation: if safety_band in {"RED", "CRISIS"} -> force LOW (minimize tool exposure). (e) Score mapping: 0 = LOW, 1-2 = MEDIUM, 3+ = HIGH. Make thresholds configurable via get_config().phase1.complexity_thresholds. | WB 17.5 | **Direct LLM impact.** Correct complexity tier determines Back's iteration budget (4/8/12) and tool allowlist (3/6/6 tools). Wrong tier = wrong budget. "Plan birthday party for mom" with multi-intent (scheduling + family_coordination) and multi-domain (CELEBRATION + PLANNING) scores 2 -> MEDIUM (8 iterations). Currently scored LOW (4 iterations). Back gets 2x budget and gains spawn_via_fabric + execute_workflow tools. |
| 10.1.3 | Add UltraBERT confidence-based intent thresholding. UltraBERT multi-label intent returns scores for all 8 classes. Define threshold: `INTENT_CONFIDENCE_THRESHOLD = 0.3` (configurable). Only include intents with confidence >= threshold in `all_intents[]`. For primary_intent, use argmax. For multi-label ingress, apply same threshold to domain scores. This prevents low-confidence phantom intents from inflating complexity tier. Test with edge cases: "hi" should be LOW (single intent, single domain). "Book hotel and find restaurant near doctor" should be HIGH (3 intents, 3 domains). | WB 17.4 | Prevents over-classification. Without thresholding, UltraBERT might return 5 intents with scores [0.8, 0.3, 0.1, 0.05, 0.02] and the complexity classifier counts 5 intents -> HIGH. With threshold at 0.3: only 2 intents count -> MEDIUM. Appropriate budget for the actual task. |
| 10.1.4 | Implement graceful degradation when UltraBERT is unavailable. If `full_analysis()` returns None or raises: (a) Fall back to StubPhase1Pipeline.classify() (keyword-based). (b) Set Phase1Result metadata: `{"degraded": true, "reason": "ultrabert_unavailable"}`. (c) Emit bus event `k1.phase1.degraded.v1` with payload `{session_id, turn_number, reason}` (RELAXED delivery, observability only). (d) Log at WARNING level. (e) Add config flag: `phase1.require_ultrabert: false` (default false). When true AND UltraBERT is unavailable, reject the turn with error (for production safety-critical deployments). | WB 17.4 | In degraded mode, LLM experience is identical to current stub behavior. The bus event enables M11 (Observability) to track degradation frequency. In production, if UltraBERT fails on GPU-less machine, the system still works (just with keyword classification). |

---

### E10.2 -- Phase 1 SessionState Writes (Three-Section Feed)

Source: WB 17.6, K1 Architecture Skeleton (TWO-PHASE WRITE PER TURN)

**Rationale:** Phase 1 outputs currently live ONLY in
ConciergeControlExtension (in-memory, disconnected from SS) and in
TypedHistoryEntry.metadata (not readable by Front prompt builder). The
architecture mandates that Phase 1 writes to 3 SS sections: control,
scoreboard, affective_now. Front prompt builder reads these sections to
construct the prompt. If Phase 1 does not write, Front reads stale or
empty values. This epic implements the three-section write inside
`_run_phase1()`.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 10.2.1 | Write Phase 1 outputs to SS control section. After `classify()` returns Phase1Result, `_run_phase1()` writes to ControlSection: (a) `control.set_intent(IntentClassification(primary=result.intent_classification, all_intents=result.intents))` -- requires adding `set_intent()` method to ControlSection (currently has IntentClassification dataclass but no setter). (b) `control.set_domain(DomainContext(primary_domain=result.domain_context, active_domains=[result.domain_context]))` -- requires adding `set_domain()` method. (c) `control.set_safety(SafetyContext(band=band_to_enum(result.safety_band)))` -- requires adding `set_safety()` method. (d) `control.set_complexity_tier(result.complexity_tier)` -- requires adding complexity_tier field to ControlSection metadata (or FlowState). Also update control_ext for backward compatibility. | WB 17.6 | **Critical LLM impact.** After this issue, Front's prompt builder can read `control.get_intent()` to know the classified intent BEFORE generating response. Front's prompt includes "User intent: scheduling, Domain: health, Safety: GREEN, Complexity: MEDIUM" in the system context. The LLM generates a domain-appropriate response instead of generic. |
| 10.2.2 | Write Phase 1 outputs to SS scoreboard section. After `classify()`, `_run_phase1()` writes to scoreboard: (a) `scoreboard.set_last_user_intent(result.intent_classification, confidence)` -- scoreboard already has last_user_intent field (from V2 design). Verify method exists or add it. (b) For each entity in result.entities: `scoreboard.add_referent(text=entity["text"], entity_type=entity["label"], entity_id=generated, confidence=entity.get("confidence", 0.8))` -- scoreboard has Referent concept. Verify add_referent method exists or add it. (c) For each entry in result.salience_map: `scoreboard.set_salience(entity_id, score)` -- scoreboard has salience concept. This is the Phase 1 "seed" from WB 17.6. Front's update_scoreboard() tool REFINES these seeds via the LLM (Write-then-Refine pattern). | WB 17.6 | **Direct LLM impact on pronoun resolution.** Phase 1 seeds the scoreboard with entities from UltraBERT NER: PERSON names, LOC places, KINSHIP terms. When the user says "Book her a dentist appointment", the scoreboard already has "her" -> {entity: "Mom", type: KINSHIP} from the previous turn's NER. Front's update_scoreboard() resolves the pronoun using these seeds instead of guessing. Without seeds: Front must use LLM reasoning to resolve "her" (costs 1 tool call iteration). With seeds: already resolved by Phase 1 (0 LLM cost). |
| 10.2.3 | Write Phase 1 outputs to SS affective_now section. After `classify()`, `_run_phase1()` writes to affective_now: (a) `affective_now.update_emotion(primary_emotion=result.primary_emotion, confidence=result.emotion_confidence, valence=result.valence, arousal=result.arousal)` -- affective_now section has AffectiveNowSection with these fields (from M5). Verify method exists or add it. (b) Map UltraBERT emotion scores to intensity: `intensity = max(emotion_scores.values())` if available. (c) This write is the Phase 1 deterministic emotion seed. Front's refine_affect() tool can OVERRIDE this if the LLM detects sarcasm or nuance that UltraBERT missed (confidence > 0.8 override, WB Section 5 Write-then-Refine). | WB 17.6 | **Direct LLM impact on tone matching.** The Front prompt includes affective_now in the system context ("Current emotion: worry, intensity: 0.7"). The LLM adjusts response tone accordingly (empathetic for worry, celebratory for joy). Without Phase 1 emotion write: affective_now is empty, LLM generates a neutral tone even when the user is clearly distressed. With Phase 1 write: tone matching works from the first LLM token. |
| 10.2.4 | Implement TurnLock-protected atomic write of all 3 sections. The current `_run_phase1()` acquires TurnLock, classifies, writes to control_ext, releases TurnLock. Extend this to: (a) Acquire TurnLock. (b) classify(). (c) Write control section. (d) Write scoreboard section. (e) Write affective_now section. (f) Write control_ext (backward compat). (g) Attach metadata to history entry. (h) Release TurnLock. All 3 section writes happen inside the TurnLock so Front cannot read partially-written state. If any write fails, log error but continue (partial write is better than no write). Add timing: log total Phase 1 duration including all writes (target: < 25ms with UltraBERT + 3 writes). | WB 17.5, 17.6 | No direct LLM impact beyond what 10.2.1-10.2.3 provide. This is the sequencing guarantee: Front NEVER reads Phase 1 data mid-write. |

---

### E10.3 -- Complexity-Based Tier Routing

Source: WB 17.3, 17.5, K1 Architecture Skeleton (COMPLEXITY-BASED ROUTING)

**Rationale:** The POC has tier routing structure in `_route_via_orchestrator()`
but HIGH tier immediately fails. The architecture diagram shows:
LOW -> Fabric direct, MEDIUM -> Orchestrator -> Fabric,
HIGH -> Orchestrator -> Planner -> Fabric. M10 must implement the
full routing decision tree. Additionally, Front currently reads tier
from control_ext (in-memory) not from SS control. This epic makes
the SS control section the single source of truth for tier routing.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 10.3.1 | Make Front dispatch_task read tier from SS control section. In `tools/implementations.py`, the dispatch_task tool implementation currently constructs TaskDispatch with a tier that comes from the LLM's tool call arguments (Front decides the tier). Change this: (a) If the LLM provided an explicit tier in the tool call, use it (LLM override). (b) If the LLM did not provide tier (or provided "AUTO"), read `control.get_complexity_tier()` from SS. (c) If SS has no complexity_tier (Phase 1 didn't write), default to "LOW" with warning. This ensures Front's dispatch uses Phase 1's classification by default but allows the LLM to override when it has better judgment (e.g., user said "this is simple, just do X" -> LLM overrides to LOW). | WB 17.5 | **LLM agency preserved.** The LLM can still override the tier when it disagrees with UltraBERT. "Just check the weather" with UltraBERT MEDIUM (multi-domain false positive) -> LLM overrides to LOW. But the DEFAULT is UltraBERT's classification, which is correct ~90% of the time. |
| 10.3.2 | Implement HIGH-tier Orchestrator -> Planner handoff. Replace the fail-fast branch in `_route_via_orchestrator()` (controller.py L908-925) with: (a) Build a PlanRequest from TaskDispatch (intent, constraints, context from SS). (b) Emit `k1.planner.plan_request.v1` on bus with PlanRequest payload. (c) Transition FSM to COMPANIONING (same as MEDIUM). (d) The Planner (stub or real) processes the PlanRequest through its 4-stage pipeline and emits `k1.planner.plan_committed.v1`. (e) The Orchestrator receives the CommittedPlan and executes steps via Fabric (same as MEDIUM DAG execution). If the PlannerStub is not yet implemented: create a PassthroughPlannerStub that receives PlanRequest and immediately emits a CommittedPlan with a single step (the original intent). This makes HIGH tier functionally equivalent to MEDIUM but with the correct routing path. Real Planner implementation is a later milestone. | WB 17.5 | **Indirect LLM impact.** HIGH tier currently fails. After this issue, a HIGH-complexity task like "Plan a family vacation to Goa next month including flights, hotel, activities, and budget" actually executes instead of returning "HIGH tier not implemented". Back gets 12-iteration budget and full tool set. Even with PassthroughPlannerStub, the task runs as MEDIUM (single plan step) which is better than failing. |
| 10.3.3 | Implement CRISIS safety-band short-circuit. Add safety check in `_run_phase1()` AFTER classify() and AFTER SS writes: (a) If `result.safety_band == "CRISIS"`: skip normal DISPATCHING flow. Emit `k1.safety.crisis.v1` bus event with payload {session_id, text_hash (NOT raw text), safety_scores}. Transition to a CRISIS_HANDLING state (new state or reuse DELIVERING with crisis flag). Generate a safety-protocol response (canned text, no LLM call). Log at CRITICAL level. (b) If `result.safety_band == "RED"`: annotate the dispatch envelope with `requires_safety_review: true`. The HITL protocol (M6) will intercept and request approval before side-effect execution. (c) If `result.safety_band == "AMBER"`: annotate with `safety_note: "elevated"`. Front includes safety awareness in prompt but proceeds normally. | WB 17.4 | **Safety-critical LLM impact.** CRISIS: LLM is NOT invoked at all. A canned safety-protocol response is returned immediately (e.g., crisis helpline information). This prevents the LLM from generating an inappropriate conversational response to a self-harm message. RED: LLM proceeds but all side-effect tools are blocked until HIL approval. The LLM's invoke_capability calls are intercepted. AMBER: LLM gets a safety note in the system prompt ("Note: elevated safety concern detected") which guides tone. |
| 10.3.4 | Add tier routing observability. Emit `k1.phase1.classified.v1` bus event after every Phase 1 classification with payload: {turn_number, complexity_tier, intent_primary, domain_primary, safety_band, emotion_primary, classification_latency_ms, is_degraded}. This event is RELAXED delivery (observability only). Also emit `k1.task.routed.v1` after_route_via_orchestrator with {task_id, assigned_tier, routing_path (DIRECT/ORCHESTRATOR/PLANNER), budget_limit}. These enable M11 (Observability) dashboards for tier distribution, classification accuracy, and routing patterns. | WB 17.5 | No direct LLM impact. Enables tracking of how often UltraBERT classification produces each tier and whether the LLM overrides it. |

---

### E10.4 -- UltraBERT Adapter K1 Integration Layer

Source: WB 17.4, K0 Runtime Adapter (k0/runtime/ultrabert_adapter.py)

**Rationale:** The k0/runtime/ultrabert_adapter.py (1244 lines) provides
a complete integration with the familyos_ultrabert pip package. It has
singleton management, GPU detection, single-pass caching, result adapters,
and convenience functions. K1 needs a thin integration layer that:
(a) imports the K0 adapter, (b) handles the K0->K1 mapping, (c) provides
K1-specific caching and metrics, (d) isolates K1 from K0 adapter internals.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 10.4.1 | Create `poc/k1_poc/fsm/ultrabert_bridge.py` -- thin bridge between K0 adapter and K1 Phase 1. Class `UltraBERTBridge`: (a) Constructor: `__init__(self, warmup: bool = True)` -- calls `init_ultrabert_client()` from k0 adapter on first use. (b) Method `analyze(text: str) -> dict | None` -- calls `full_analysis(text)` from k0 adapter. Adds K1-specific fields: `analyzed_at_ms`,`turn_number` (from context), `session_id`. (c) Method`is_available() -> bool` -- calls `is_ultrabert_available()` from k0 adapter. (d) Method `get_metrics() -> dict` -- returns `get_analysis_cache_metrics()` from k0 adapter + K1-local metrics (calls_count, avg_latency_ms, fallback_count). (e) Singleton pattern: module-level `_bridge` with `get_ultrabert_bridge()`. The bridge does NOT re-implement caching (K0 adapter already has LRU/TTL cache). It adds K1-level observability. | WB 17.4 | No direct LLM impact. Infrastructure layer that enables 10.1.1. |
| 10.4.2 | Wire UltraBERTBridge into bootstrap.py. In `kernel/bootstrap.py`, after FSM creation: (a) Create UltraBERTBridge(warmup=True). (b) Create UltraBERTPhase1Pipeline(bridge=bridge). (c) Replace `fsm._phase1_pipeline = StubPhase1Pipeline()` with `fsm._phase1_pipeline = UltraBERTPhase1Pipeline(bridge=bridge)`. (d) If bridge.is_available() is False, keep StubPhase1Pipeline as fallback and log warning. (e) Add config flag: `phase1.pipeline: "ultrabert"` (default) or `"stub"` (for testing without GPU). | WB 17.4 | The moment this is wired, every user turn in the POC gets real UltraBERT classification instead of keyword matching. LLM prompts get accurate intent/domain/safety/emotion context from turn 1. |
| 10.4.3 | Add UltraBERT warmup to kernel startup. In bootstrap.py, after creating UltraBERTBridge: (a) Log "UltraBERT warming up..." (b) Call `bridge.analyze("warmup text")` to trigger first-forward-pass latency. (c) Log warmup latency. The K0 adapter already does warmup internally (`_maybe_full_warmup`), but the K1 bridge should also warm up the full_analysis path (which includes JSON serialization, K1 metric tracking). Target: first real user turn sees ~20ms, not ~5000ms (model load). | WB 17.4 | Prevents first-turn latency spike. Without warmup: first user message waits ~5 seconds for model load + first forward pass. With warmup: first message sees ~20ms (same as subsequent). User experience is consistent from turn 1. |
| 10.4.4 | Integration test: UltraBERT Phase 1 end-to-end. Test scenario: (a) Create FSM with UltraBERTPhase1Pipeline wired. (b) Send user.input: "Mom called about grandma's birthday party next Saturday". (c) Verify Phase1Result: intents includes "log_memory" or "share_news", entities includes KINSHIP ("Mom", "grandma"), temporal includes DATE_REL ("next Saturday"), emotion includes "joy" or "excitement", domain includes "CELEBRATION" or "FAMILY", safety = "GREEN", complexity >= MEDIUM (multi-intent + multi-domain). (d) Verify SS sections: control.get_intent().primary matches result.intent_classification, scoreboard has referent entries for "Mom" and "grandma", affective_now.current_emotion matches result.primary_emotion. (e) Verify Front dispatch uses the correct tier from SS. Test in `tests/poc/test_m10_ultrabert_phase1.py`. Requires UltraBERT installed (skip if not available with `@pytest.mark.skipif`). | WB 17.4-17.6 | Validates the full Phase 1 -> SS -> Front -> dispatch -> Back chain. This is the acceptance test for M10. |

---

### E10.5 -- Temporal + Relation Head Integration

Source: WB 17.6, UltraBERT README (12 heads), K1 Architecture Skeleton (TIME_RESOLUTION)

**Rationale:** UltraBERT v4 has 12 heads. E10.1-E10.4 use 7 of them
(intent, ingress, safety_familyos, emotions, sentiment, ner_general,
ner_family). This epic integrates the remaining 5 heads (temporal,
relation, safety_generic, nli, embedding) which provide additional
value for K1's temporal resolution engine, family graph, and semantic
retrieval.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 10.5.1 | Feed UltraBERT temporal head output to Phase1Result and SS. (a) Add `temporal_expressions: list[dict]` field to Phase1Result. (b) In UltraBERTPhase1Pipeline.classify(), extract temporal head output: `result["temporal"]` contains spans like `{text: "next Saturday", label: "DATE_REL", start: 5, end: 7}`. Map to Phase1Result.temporal_expressions. (c) In `_run_phase1()`, write temporal expressions to SS scoreboard as metadata or to a dedicated temporal field. (d) The architecture diagram's TIME_RESOLUTION engine (Time Parser, Time Resolver, Timezone Context, Temporal Anchor) can consume these spans for temporal ambiguity resolution. Phase 1 provides the raw spans; resolution happens in a later module. | WB 17.6 | **Indirect LLM impact.** Temporal spans help Back's invoke_capability resolve time references. "next Saturday" parsed by UltraBERT -> DATE_REL span. When the Time Resolver converts this to absolute date (e.g., "2026-03-07"), Back's tool calls use the resolved date instead of passing the ambiguous string to the tool. Fewer clarification rounds. |
| 10.5.2 | Feed UltraBERT relation head output to Phase1Result and SS. (a) Add `relations: list[str]` field to Phase1Result. (b) In UltraBERTPhase1Pipeline.classify(), extract relation head: `result["relations"]` returns list like `["parent_of", "spouse_of"]`. (c) In `_run_phase1()`, write relations to SS scoreboard as relationship context. (d) These relations enrich the family graph understanding. When the user says "Mom called about grandma", the relation head detects "parent_of" between "Mom" and the user, and "grandparent_of" between "grandma" and the user. | WB 17.6 | **Indirect LLM impact.** Relations in scoreboard help Front's update_beliefs() tool identify family connections. "Mom" is not just a PERSON entity; it is "parent_of(user)". This enriches the belief graph and enables family-context-aware responses. |
| 10.5.3 | Feed UltraBERT embedding to SS for semantic similarity. (a) UltraBERT produces a 768-dim embedding for each input text. (b) Store the embedding in Phase1Result metadata (not a dedicated field -- too large for Phase1Result struct). (c) In `_run_phase1()`, write embedding to SS meta section or a dedicated embedding cache. (d) This embedding can be used by recall_memory tool (semantic search), discover_capabilities tool (semantic matching), and the Fabric Retrieval Engine (Top-K ranker). Having the embedding pre-computed by Phase 1 (already done in the single forward pass) avoids a separate embedding call later. | WB 17.6 | **Indirect LLM impact via tool quality.** recall_memory uses semantic search to find relevant memories. If the query embedding is pre-computed by Phase 1 (768-dim UltraBERT), recall returns more relevant results. Better recall -> better context in LLM prompt -> better response quality. |

---

### M10 UltraBERT Integration ReAct Loop Interaction Audit

**Constraints derived from code reading (fsm/phase1.py, fsm/controller.py,
fsm/control_extension.py, task/complexity.py, tools/dispatcher.py,
sessionstate/sections/control.py, k0/runtime/ultrabert_adapter.py,
Modeling_studio/README.md, k1_cognitive_architecture_skeleton.mmd):**

| # | Constraint | Code Evidence | M10 Implication |
|---|-----------|---------------|----------------|
| P1 | StubPhase1Pipeline.classify() returns keyword-based defaults. No UltraBERT call exists in the K1 POC. Phase1Result.complexity_tier defaults to "LOW" for everything except "hotel"/"flight"/"doctor"/"dentist" keywords. | phase1.py L200-240: keyword matching `if any(w in lower for w in ("hotel", "flight", ...))`. No import of familyos_ultrabert or k0/runtime adapter. | E10.1.1 replaces StubPhase1Pipeline with UltraBERTPhase1Pipeline that calls full_analysis(). 12 UltraBERT heads provide real classification instead of 5 keyword groups. |
| P2 | `_run_phase1()` writes to control_ext ONLY (in-memory). Does NOT write to ControlSection, ScoreboardSection, or AffectiveNowSection in SessionState. | controller.py L785: `self._control_ext.set_complexity_tier(result.complexity_tier)`. No calls to `self._ss.get_section("control")`, `self._ss.get_section("scoreboard")`, or `self._ss.get_section("affective_now")`. | E10.2.1-10.2.3 add SS section writes. E10.2.4 wraps them in TurnLock atomic block. |
| P3 | ConciergeControlExtension explicitly does NOT modify ControlSection. It is a "POC extension" with 3 in-memory fields. | control_extension.py L14: "The wrapper does NOT modify ControlSection." L18: "The POC extension is 3 fields -- not worth schema churn." | E10.2.1 adds setter methods to ControlSection (set_intent, set_domain, set_safety, set_complexity_tier). The control_ext write is kept for backward compatibility. |
| P4 | ControlSection has IntentClassification, DomainContext, SafetyContext dataclasses but NO setter methods for them. Construction initializes empty defaults. | control.py L354-360: `self._intents = IntentClassification()`, `self._domains = DomainContext()`, `self._safety = SafetyContext()`. No set_intent(), set_domain(), set_safety() methods visible. | E10.2.1 adds setter methods that update these dataclass fields and invalidate the FlatBuffer cache (`self._cache_valid = False`). |
| P5 | HIGH tier fails fast in `_route_via_orchestrator()`. Emits task.failed immediately. | controller.py L908-925: `if record.tier == ComplexityTier.HIGH: ... build_task_failed(payload={"reason": "HIGH tier not implemented in POC"})`. | E10.3.2 replaces fail-fast with Orchestrator -> Planner handoff (or PassthroughPlannerStub). |
| P6 | No safety-band-driven routing exists at Phase 1 level. _run_phase1 does not check safety_band after classification. | controller.py L774-799: _run_phase1 runs classify, writes control_ext, attaches metadata, releases TurnLock. No `if result.safety_band == "CRISIS"` check anywhere. | E10.3.3 adds CRISIS/RED/AMBER short-circuit after classify() and after SS writes. |
| P7 | K0 adapter (ultrabert_adapter.py) provides full_analysis() that returns dict with all 12 head outputs in a single forward pass (~20ms). Uses LRU/TTL cache (64 entries, 30s TTL). Thread-safe singleton. | ultrabert_adapter.py L230-244: `_get_full_analysis_result(text)` -> cache check -> `client.analyze(text)` -> cache put. Returns dict with sentiment, emotions, safety, entities, general_entities, temporal, intent, ingress, relations, embedding, latency_ms. | E10.4.1 creates UltraBERTBridge that wraps full_analysis() with K1-specific metrics. E10.1.1 maps dict output to Phase1Result. |
| P8 | UltraBERT v4 has 12 heads producing: ner_general (4 entities), ner_family (10 entities), sentiment (5 classes), emotions (44 classes), safety_generic (8 types), safety_familyos (4 bands), nli (3 classes), embedding (768-dim), temporal (6 time types), relation (15 types), intent (8 classes), ingress (12 domains). Single forward pass: ~20ms, 149M params. | Modeling_studio/README.md: "12 Task Heads", "20ms inference", "149M params". Performance table: Intent accuracy 90%, Safety band 87.5%, NER General F1 95.2%. | Phase1Result currently has 11 fields. UltraBERT produces 12 head outputs. E10.5.1-10.5.3 integrate the remaining heads (temporal, relation, embedding) that do not map to existing Phase1Result fields. |
| P9 | FRONT_TIER_ALLOWLISTS and BACK_TIER_ALLOWLISTS in dispatcher.py gate which tools each actor can use per tier. LOW Front: 8 tools. MEDIUM/HIGH Front: 9 tools (+ promote_belief). LOW Back: 4 tools. MEDIUM/HIGH Back: 6 tools (+ spawn_via_fabric + execute_workflow). CRISIS Front: 0 tools. | dispatcher.py L61-115: FRONT_TIER_ALLOWLISTS and BACK_TIER_ALLOWLISTS. BUDGET_LIMITS: LOW=5, MEDIUM=10, HIGH=20, CRISIS=3. | Correct tier classification from UltraBERT -> correct tool allowlist and budget for both Front and Back. The dispatcher already handles tier-based gating; M10 just needs to provide the correct tier. |
| P10 | The architecture diagram shows TWO-PHASE WRITE PER TURN: Phase 1 (UltraBERT, 22ms, deterministic) writes control/scoreboard/affective_now. Phase 2 (LLM with tools) refines via cognitive tools. The Write-then-Refine pattern means Phase 1 sets initial values that Phase 2 can override. | Architecture diagram comment block: "PHASE 1: UltraBERT (22ms, pre-LLM, deterministic) ... PHASE 2: LLM with Tools (post-UltraBERT, semantic understanding)". phase1.py docstring: "Write-then-Refine pattern (V2 Section 5): Phase 1 sets initial values. Front LLM may refine via cognitive tools." | E10.2.1-10.2.3 implement the Phase 1 writes. The Phase 2 refinement (cognitive tools) is already implemented in M5. M10 completes the two-phase architecture. |

---

### Recommended Execution Order

1. **10.4.1** (UltraBERTBridge -- thin K1 wrapper over K0 adapter)
2. **10.4.3** (warmup in kernel startup -- first-turn latency)
3. **10.1.1** (UltraBERTPhase1Pipeline -- replace stub with real UltraBERT)
4. **10.1.3** (confidence thresholding -- prevents over-classification)
5. **10.1.2** (multi-factor complexity classifier -- correct tier assignment)
6. **10.1.4** (graceful degradation -- fallback when UltraBERT unavailable)
7. **10.2.1** (write Phase 1 to SS control -- most critical SS feed)
8. **10.2.2** (write Phase 1 to SS scoreboard -- entity/intent seeds)
9. **10.2.3** (write Phase 1 to SS affective_now -- emotion seed)
10. **10.2.4** (TurnLock atomic write -- sequencing guarantee)
11. **10.3.1** (Front reads tier from SS control -- single source of truth)
12. **10.3.3** (CRISIS safety-band short-circuit -- safety before routing)
13. **10.3.2** (HIGH-tier Orchestrator -> Planner handoff)
14. **10.3.4** (tier routing observability events)
15. **10.4.2** (wire UltraBERTBridge into bootstrap.py)
16. **10.5.1** (temporal head integration)
17. **10.5.2** (relation head integration)
18. **10.5.3** (embedding integration for semantic search)
19. **10.4.4** (end-to-end integration test)

---

## M11: Observability & Telemetry

**Goal:** Instrument every subsystem introduced in M0-M10 with structured
metrics, canonical bus events, alert thresholds, and dashboards. Enable
regression detection before users notice degraded behavior. Cover the full
observability surface: ReAct loop fallback paths, bus delivery health, FSM
transition fidelity, SessionState mutation guard throughput, Arbiter decision
quality, HITL lifecycle tracking, BackPool utilization, Weave policy
effectiveness, Ledger write/replay health, and UltraBERT classification
quality. Every metric has a defined emission point, a canonical bus event
topic, and a consumer (dashboard, alert, or audit log).

**Gate:** All 6 metric families emitting structured events. Alert thresholds
configured for fallback-path regression, pool saturation, ledger write
latency, and HITL timeout frequency. Mode-specific Front quality metrics
active for all 10 PromptModes. Protocol lifecycle events observable
end-to-end (from Phase 1 classification through weave delivery). Telemetry
section in SS records per-turn timing breakdown. Dashboard-ready JSON event
stream consumable by external observability stack.

**Depends on:** M1 (canonical event schemas), M2 (dead-letter pipeline),
M3 (ReAct loop iteration tracking), M4 (SS mutation guard), M5 (Arbiter
decision events), M6 (HITL lifecycle events), M7 (BackPool worker events),
M8 (Weave policy decision events), M9 (Ledger write/replay infrastructure),
M10 (UltraBERT classification events).

### Why Observability Is Hard (Cross-Milestone Audit Findings)

**Every milestone M0-M10 introduces observable behavior that is currently
untracked or tracked only via ad-hoc logging. The observability surface is:**

| Milestone | Observable Behavior | Current Tracking | Gap |
|-----------|-------------------|------------------|-----|
| M0 | Bus subscription routing invariants (0.3.14), builder priority mappings (0.3.15), causal ordering (0.3.17) | Conformance tests only (pass/fail) | No runtime metric for envelope delivery latency, topic routing errors, or causal ordering violations |
| M1 | Ledger write throughput, schema validation rates, event delivery mode compliance | LedgerWriter has no metrics. SchemaValidator logs rejections but no counters. | No per-topic delivery latency. No schema validation failure rate. No ledger append latency histogram. |
| M2 | Dead-letter routing counts, guard rejection rates, response-final action accuracy, pending overflow frequency | Dead-letter reconciliation consumer (2.2.4) has counts_by_reason/counts_by_state but no bus emission | Dead-letter metrics are in-memory only. No alert on dead-letter spike. No guard rejection rate tracking. |
| M3 | ReAct iteration counts, degenerate fallback frequency, budget exhaustion rates, forced-text frequency, parallel tool safety violations, cancel propagation latency | loop.py logs at DEBUG. No structured metrics. degenerate_count tracked locally but not emitted. | No counter for how often the LLM hits budget exhaustion. No metric for forced-text fallback. No cancel-to-exit latency. |
| M4 | SS mutation guard rejection rates, cognitive tool write throughput, SizeTracker drift, budget overflow proximity | MutationGuard logs rejections. SizeTracker has section_usage_bytes but no emission. | No metric for "how close is beliefs_active to 8KB budget?" No alert on repeated mutation rejections. |
| M5 | Arbiter decision distribution, domain/entity overlap scores, multi-device conflict rates, defer frequency, PARALLEL_NEW vs MODIFY_INFLIGHT ratio | Arbiter emits conversation.intent.arbitrated (5.1.5) but no aggregated metrics | No per-session decision distribution. No alert on high defer frequency (stuck sessions). |
| M6 | HITL round counts, suspension-to-resume latency, L2 defense block rates, timeout frequency, crash recovery success rates | HITL events (6.3.1-6.3.4) emitted but no aggregation. validate_before_invoke logs but no counter. | No HITL latency histogram. No L2 block rate metric. No timeout frequency alert. |
| M7 | BackPool utilization, lease expiry frequency, worker starvation duration, dependency ordering violations, ready-queue depth | backpool.worker.acquired/released events (7.1.4) emitted. No aggregation. | No pool utilization gauge. No lease expiry counter. No ready-queue depth metric. |
| M8 | Weave decision distribution, batch window accuracy, emotional gate trigger rates, digest compression ratios, typing suppression frequency | conversation.weave.decided event (8.2.4) emitted. weave_quality metrics (8.4.4) planned. | No real-time dashboard. No alert on excessive SUPPRESS decisions. |
| M9 | Ledger write latency, replay duration, state divergence detection, crash recovery completeness | Recovery observability events (9.5.4) emitted. No per-write latency tracking. | No ledger write latency percentile. No replay correctness verification metric. |
| M10 | UltraBERT classification latency, tier distribution, safety band distribution, degradation frequency, LLM tier override rates | k1.phase1.classified.v1 and k1.task.routed.v1 events (10.3.4) emitted. k1.phase1.degraded.v1 (10.1.4) for fallback. | No tier distribution histogram. No LLM-override-vs-UltraBERT accuracy comparison. No safety band frequency alert. |

**Problem 1 -- No unified metrics emission layer:**

Each milestone emits its own bus events (conversation.intent.arbitrated,
hitl.requested, backpool.worker.acquired, conversation.weave.decided,
k1.phase1.classified, k1.ledger.recovery.completed, etc.). There is no
shared MetricsCollector that aggregates these into a per-session summary,
no standardized metric envelope schema, and no common emission pattern.
Each subsystem reinvents metrics differently.

**Problem 2 -- No alert infrastructure:**

Metrics exist as bus events but nothing evaluates them against thresholds.
A 50% budget-exhaustion rate means the LLM is consistently failing to
complete tasks, but no alert fires. A BackPool utilization of 100% for 60
seconds means all tasks are queued, but no alert fires. The telemetry SS
section (14th section, 4KB) exists but only records turn timing -- no
threshold evaluation.

**Problem 3 -- No correlation between Phase 1 classification and LLM outcome:**

UltraBERT classifies intent/tier/safety. Front/Back LLM produces a
response. There is no metric that correlates "UltraBERT said MEDIUM,
Back got 8 iterations, Back used 7 iterations, result was complete" vs
"UltraBERT said LOW, Back got 4 iterations, Back exhausted budget, result
was partial." Without this correlation, we cannot tune UltraBERT thresholds
or complexity classifier weights.

**Problem 4 -- No end-to-end turn latency breakdown:**

A single user turn passes through: user.input -> Phase 1 (~20ms) ->
Arbiter (~1ms) -> Front LLM (100-5000ms) -> FSM routing (~1ms) ->
Back LLM (200-15000ms) -> Weave policy (~1ms) -> Front WEAVE (100-3000ms)
-> response.final. There is no structured breakdown of where time is
spent. The telemetry SS section records total turn_latency but not
per-phase durations.

### M11 LLM Interaction Model

| Actor | What M11 Adds | LLM Impact |
|-------|--------------|------------|
| Front (all modes) | Per-mode quality metrics: iteration utilization, tool call count, degenerate fallback rate, forced-text rate | No direct LLM impact. Metrics are post-hoc analysis of LLM behavior. Enables tuning iteration budgets per mode. |
| Back (all tiers) | Per-tier quality metrics: budget utilization, cancel-to-exit latency, suspend-to-resume latency, tool success rate | No direct LLM impact. Enables tuning tier budgets and tool allowlists. |
| Phase 1 | Classification-to-outcome correlation: tier assigned vs budget used vs task result | No direct LLM impact. Enables tuning UltraBERT complexity classifier thresholds. |
| Weave | Weave delivery quality: user acknowledged rate, delivery latency, emotional gate effectiveness | No direct LLM impact. Enables tuning weave policy weights. |

---

### E11.1 -- Unified Metrics Emission Layer

Source: WB 15.4.C, 15.5 P2, 13.5

**Rationale:** Each subsystem (bus, FSM, actors, protocols, weave, ledger,
Phase 1) emits its own ad-hoc events. M11 needs a shared MetricsCollector
that aggregates disparate events into a standardized metric envelope,
tracks per-session counters, and provides a single query interface for
dashboards and alerts. Without this, each consumer must parse N different
event schemas to build a unified view.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 11.1.1 | Define MetricEnvelope schema and MetricsCollector class | WB 15.4.C | None |
| 11.1.2 | Implement per-session MetricAggregator with sliding windows | WB 15.4.C | None |
| 11.1.3 | Create metric bus topic namespace and emission helpers | WB 15.4.C | None |
| 11.1.4 | Wire MetricsCollector into bootstrap as bus subscriber | WB 15.4.C | None |

---

#### 11.1.1 -- Define MetricEnvelope schema and MetricsCollector class

**Problem:** No standardized metric envelope exists. Each subsystem emits
events with different payload shapes. Consumers must understand N schemas
to build dashboards.

**What to do:**

1. **Create `poc/k1_poc/obs/metrics.py`** with:

   ```python
   @dataclass
   class MetricEnvelope:
       metric_name: str           # e.g., "react_loop.degenerate_count"
       metric_type: str           # "counter", "gauge", "histogram", "summary"
       value: float               # metric value
       labels: dict[str, str]     # e.g., {"mode": "STANDARD", "actor": "front"}
       session_id: str
       turn_number: int
       timestamp_ms: int
       source_event_id: int | None  # originating bus event envelope_id

   class MetricsCollector:
       def __init__(self, session_id: str, bus: EventBus):
           self._counters: dict[str, float] = {}
           self._gauges: dict[str, float] = {}
           self._histograms: dict[str, list[float]] = {}

       def increment(self, name: str, labels: dict, value: float = 1.0): ...
       def gauge(self, name: str, labels: dict, value: float): ...
       def observe(self, name: str, labels: dict, value: float): ...
       def snapshot() -> dict[str, MetricEnvelope]: ...
       def emit_all(self): ...  # publish all pending metrics to bus
   ```

2. **Metric naming convention:** `{subsystem}.{component}.{metric_name}`.
   Examples: `react_loop.front.degenerate_count`,
   `backpool.worker.utilization`, `phase1.ultrabert.latency_ms`,
   `weave.policy.decision_count`, `ledger.append.latency_ms`.

3. **Labels are consistent across all metrics:**
   - `session_id` (always present)
   - `turn_number` (when applicable)
   - `actor` ("front" / "back" / "fsm" / "phase1")
   - `mode` (PromptMode value, for Front metrics)
   - `tier` (ComplexityTier value, for Back metrics)

**Files:** New: `poc/k1_poc/obs/metrics.py` (~150 lines)

**Acceptance:**

- MetricEnvelope is JSON-serializable via to_dict()
- MetricsCollector tracks counters, gauges, histograms
- snapshot() returns all pending metrics
- emit_all() publishes MetricEnvelopes to bus

---

#### 11.1.2 -- Implement per-session MetricAggregator with sliding windows

**Problem:** Raw metrics need aggregation for alert evaluation. A single
degenerate fallback event is informational. 10 degenerate fallbacks in
5 minutes is an alert. The aggregator computes rates, percentiles, and
sliding window summaries from raw MetricEnvelope events.

**What to do:**

1. **Add to `poc/k1_poc/obs/metrics.py`:**

   ```python
   class MetricAggregator:
       def __init__(self, window_size_s: float = 300.0):
           self._windows: dict[str, SlidingWindow] = {}

       def record(self, envelope: MetricEnvelope): ...
       def rate(self, metric_name: str, labels: dict) -> float: ...
       def percentile(self, metric_name: str, labels: dict, p: float) -> float: ...
       def summary(self) -> dict: ...

   class SlidingWindow:
       def __init__(self, window_size_ms: int):
           self._entries: deque[tuple[int, float]] = deque()  # (ts_ms, value)
       def add(self, ts_ms: int, value: float): ...
       def evict_stale(self): ...
       def count(self) -> int: ...
       def sum(self) -> float: ...
       def mean(self) -> float: ...
       def p50(self) -> float: ...
       def p95(self) -> float: ...
       def p99(self) -> float: ...
   ```

2. **Window size configurable:** Default 300s (5 minutes). Configurable
   via `obs.metrics.window_size_s` in defaults.yaml.

3. __Aggregator subscribes to all k1.metrics._ bus topics_* and auto-records
   into windows keyed by `(metric_name, frozenset(labels.items()))`.

**Files:** `poc/k1_poc/obs/metrics.py` (extend, ~100 lines)

**Acceptance:**

- SlidingWindow correctly evicts stale entries
- rate() returns events/second for a counter
- percentile() returns p50/p95/p99 for histograms
- Tests with synthetic data verify sliding window math

---

#### 11.1.3 -- Create metric bus topic namespace and emission helpers

**Problem:** Metric events need dedicated bus topics so they do not compete
with operational events (task.complete, response.final, etc.) for delivery
bandwidth. Metric events are RELAXED delivery (best-effort, no ordering
guarantee).

**What to do:**

1. **Add to `poc/k1_poc/bus/topics.py`:**

   ```python
   TOPIC_METRIC_EMITTED = "k1.metrics.emitted.v1"
   TOPIC_METRIC_ALERT = "k1.metrics.alert.v1"
   TOPIC_METRIC_SESSION_SUMMARY = "k1.metrics.session_summary.v1"
   ```

   All RELAXED delivery. Add to ALL_TOPICS.

2. **Add builder functions to `poc/k1_poc/bus/builders.py`:**

   ```python
   def build_metric_emitted(payload: dict, parent_id: int = 0) -> Envelope: ...
   def build_metric_alert(payload: dict, parent_id: int = 0) -> Envelope: ...
   def build_session_summary(payload: dict, parent_id: int = 0) -> Envelope: ...
   ```

3. **Add helper in `poc/k1_poc/obs/metrics.py`:**

   ```python
   def emit_metric(collector: MetricsCollector, name: str, type: str,
                   value: float, labels: dict, bus: EventBus): ...
   ```

   Wraps MetricEnvelope creation + bus.publish in one call.

**Files:** `poc/k1_poc/bus/topics.py` (3 lines), `poc/k1_poc/bus/builders.py` (3 builders), `poc/k1_poc/obs/metrics.py` (helper)

**Acceptance:**

- Metric topics registered in ALL_TOPICS
- Builder functions produce valid Envelopes
- emit_metric helper publishes to bus correctly

---

#### 11.1.4 -- Wire MetricsCollector into bootstrap as bus subscriber

**Problem:** MetricsCollector must be created during kernel startup and
wired as a subscriber to all subsystem events that carry metric-relevant
data. It must also be accessible to all code that needs to emit metrics.

**What to do:**

1. **In `kernel/bootstrap.py`**, after FSM creation:

   ```python
   metrics_collector = MetricsCollector(session_id=session_id, bus=bus)
   metric_aggregator = MetricAggregator(window_size_s=get_config().obs.metrics.window_size_s)
   # Subscribe aggregator to metric events
   bus.subscribe(TOPIC_METRIC_EMITTED, metric_aggregator.record)
   ```

2. **Pass collector to ToolContext, FSM, and actors** so each subsystem
   can call `collector.increment(...)` at its emission points.

3. **Add `obs` config section to defaults.yaml:**

   ```yaml
   obs:
     metrics:
       enabled: true
       window_size_s: 300.0
       emit_interval_s: 10.0  # how often to flush batch metrics
     alerts:
       enabled: true
   ```

**Files:** `poc/k1_poc/kernel/bootstrap.py` (~10 lines), `poc/k1_poc/config/defaults.yaml` (~8 lines)

**Acceptance:**

- MetricsCollector created at bootstrap
- MetricAggregator subscribes to metric events
- Config section exists and is loadable

---

### E11.2 -- ReAct Loop & Actor Telemetry

Source: WB 15.4.C, 15.5 P2

**Rationale:** The ReAct loop (react/loop.py) is the core LLM execution
engine. It has 5 fallback/failure paths that are invisible today:
(1) degenerate response (LLM returns no tool calls and no text),
(2) budget exhaustion (iteration limit hit), (3) forced-text fallback
(LLM nudged to "respond directly"), (4) validator rejection (LLM output
fails schema validation), (5) cancellation exit. Each path has different
LLM quality implications. Front and Back actors each have mode-specific
and tier-specific quality characteristics that must be tracked separately.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 11.2.1 | Instrument ReAct loop fallback paths with structured counters | WB 15.4.C | None (post-hoc) |
| 11.2.2 | Add per-mode quality metrics for Front actor | WB 15.5 P2 | None (post-hoc) |
| 11.2.3 | Add per-tier quality metrics for Back actor | WB 15.5 P2 | None (post-hoc) |
| 11.2.4 | Add end-to-end turn latency breakdown | WB 15.4.C | None (post-hoc) |

---

#### 11.2.1 -- Instrument ReAct loop fallback paths with structured counters

**Problem:** `react_loop` (loop.py L216-562) has 5 exit paths, each tracked
locally but never emitted as structured metrics:

| Exit Path | Code Location | Current Tracking | Metric Name |
|-----------|--------------|------------------|-------------|
| Degenerate | L283-295 (nudge), L303-310 (force-text) | `degenerate_count` local var, logged at DEBUG | `react_loop.{actor}.degenerate_count` |
| Budget exhausted | L270-280 (last iteration submit nudge) | `iteration == max_iterations` check, no counter | `react_loop.{actor}.budget_exhausted_count` |
| Forced-text | L303-310 | Part of degenerate path, no separate counter | `react_loop.{actor}.forced_text_count` |
| Validator rejection | L451-465 | Logged at WARNING, no counter | `react_loop.{actor}.validator_rejection_count` |
| Cancellation exit | L258 | Returns ReactResult(status="cancelled"), no counter | `react_loop.{actor}.cancel_exit_count` |
| Normal completion | L487-492 (submit_result) | Returns ReactResult(status="ok"), no counter | `react_loop.{actor}.normal_completion_count` |

**What to do:**

1. **In `react/loop.py`**, accept a `MetricsCollector` parameter (optional,
   None for backward compat).

2. **At each exit point**, emit:

   ```python
   if collector:
       collector.increment("react_loop.degenerate_count",
           labels={"actor": actor_name, "mode": mode, "tier": tier})
   ```

3. **At loop end**, emit a summary metric:

   ```python
   collector.observe("react_loop.iteration_count",
       labels={"actor": actor_name, "mode": mode, "tier": tier},
       value=iteration)
   collector.observe("react_loop.tool_call_count",
       labels={"actor": actor_name},
       value=total_tool_calls)
   collector.observe("react_loop.duration_ms",
       labels={"actor": actor_name},
       value=(end_ns - start_ns) / 1e6)
   ```

4. **Emit a bus event per loop completion:**

   ```python
   build_metric_emitted(payload={
       "metric_name": "react_loop.summary",
       "actor": actor_name,
       "mode": mode,
       "tier": tier,
       "iterations_used": iteration,
       "iterations_budget": max_iterations,
       "tool_calls": total_tool_calls,
       "exit_path": exit_path,  # "normal", "degenerate", "budget_exhausted", "forced_text", "cancelled"
       "degenerate_count": degenerate_count,
       "duration_ms": duration_ms,
   })
   ```

**Files:** `poc/k1_poc/react/loop.py` (~30 lines of instrumentation)

**Acceptance:**

- Every ReAct loop completion emits a summary metric event
- Degenerate, budget exhausted, forced-text, cancel, and normal paths each increment their counter
- Labels include actor, mode, and tier for filtering
- Test: run react_loop to budget exhaustion, verify budget_exhausted_count incremented

---

#### 11.2.2 -- Add per-mode quality metrics for Front actor

**Problem:** Front operates in 10 PromptModes (STANDARD, PRESENT, WEAVE,
INTERRUPT, CLARIFY_ASK, CLARIFY_RESOLVE, HITL_RELAY, HITL_RESOLVE, ERROR,
CANCEL). Each mode has different iteration budgets, tool allowlists, and
expected behavior patterns. There is no per-mode quality tracking.

**What to do:**

1. **In `actors/front.py`**, after `react_loop` returns, emit per-mode metrics:

   ```python
   collector.observe("front.mode.iterations_used",
       labels={"mode": mode.value}, value=result.iterations)
   collector.observe("front.mode.tool_calls",
       labels={"mode": mode.value}, value=result.tool_call_count)
   collector.increment("front.mode.invocation_count",
       labels={"mode": mode.value})
   if result.status == "degenerate":
       collector.increment("front.mode.degenerate_count",
           labels={"mode": mode.value})
   ```

2. **Track mode-specific expected vs actual behavior:**

   | Mode | Expected Tool Calls | Expected Iterations | Alert If |
   |------|-------------------|--------------------|----|
   | HITL_RELAY | 0 | 1 | tool_calls > 0 (tools should be empty) |
   | HITL_RESOLVE | 1 (update_beliefs) | 1-3 | iterations > 3 (budget inefficiency) |
   | WEAVE | 0-2 | 1-3 | degenerate (failed to weave) |
   | STANDARD | 2-6 | 3-6 | budget_exhausted + degenerate (stuck) |
   | PRESENT | 0-2 | 1-3 | iterations > 3 (should be quick) |

3. **Emit alert if HITL_RELAY has tool calls** (indicates tool allowlist
   misconfiguration -- HITL_RELAY should have empty tool set).

**Files:** `poc/k1_poc/actors/front.py` (~20 lines)

**Acceptance:**

- Per-mode invocation count, iteration count, tool call count emitted
- HITL_RELAY with tool calls triggers alert
- Test: front_handler in STANDARD mode, verify metrics emitted with mode label

---

#### 11.2.3 -- Add per-tier quality metrics for Back actor

**Problem:** Back operates at 3 tiers (LOW/MEDIUM/HIGH) with different
iteration budgets (4/8/12 from BUDGET_LIMITS in dispatcher.py) and tool
allowlists (3/6/6 tools). There is no per-tier quality tracking to
determine if tier assignments are calibrated correctly.

**What to do:**

1. **In `actors/back.py`**, after `react_loop` returns, emit per-tier metrics:

   ```python
   collector.observe("back.tier.iterations_used",
       labels={"tier": tier}, value=result.iterations)
   collector.observe("back.tier.budget_utilization",
       labels={"tier": tier}, value=result.iterations / budget_limit)
   collector.increment("back.tier.invocation_count",
       labels={"tier": tier})
   if result.status == "suspended":
       collector.increment("back.tier.suspension_count",
           labels={"tier": tier})
   ```

2. **Track budget utilization distribution:**

   | Utilization | Meaning | Action |
   |------------|---------|--------|
   | < 0.3 | Under-utilized -- tier is too high | Consider downgrading tier threshold |
   | 0.3 - 0.8 | Healthy utilization | No action |
   | 0.8 - 1.0 | Near-exhaustion -- tier may be too low | Consider upgrading tier threshold |
   | 1.0 | Exhausted -- forced-text exit | Alert: task complexity exceeds tier budget |

3. **Emit cancel-to-exit latency:** Time between CancellationToken.cancel()
   and react_loop exit. This measures how quickly the cooperative cancel
   mechanism works (expected: up to 1 LLM call duration, 2-15s).

   ```python
   if result.status == "cancelled" and cancel_token:
       collector.observe("back.cancel_to_exit_latency_ms",
           labels={"tier": tier},
           value=cancel_token.elapsed_since_cancel_ms())
   ```

**Files:** `poc/k1_poc/actors/back.py` (~25 lines)

**Acceptance:**

- Per-tier invocation count, budget utilization, suspension count emitted
- Budget utilization histogram enables tier calibration analysis
- Cancel-to-exit latency tracked for each cancelled task

---

#### 11.2.4 -- Add end-to-end turn latency breakdown

**Problem:** A single user turn passes through 7 phases. There is no
structured breakdown. The telemetry SS section records total turn_latency
but not per-phase durations.

**What to do:**

1. **Create TurnTimer dataclass in `poc/k1_poc/obs/metrics.py`:**

   ```python
   @dataclass
   class TurnTimer:
       turn_number: int
       phase1_start_ms: int = 0
       phase1_end_ms: int = 0
       arbiter_start_ms: int = 0
       arbiter_end_ms: int = 0
       front_start_ms: int = 0
       front_end_ms: int = 0
       fsm_routing_start_ms: int = 0
       fsm_routing_end_ms: int = 0
       back_start_ms: int = 0
       back_end_ms: int = 0
       weave_decision_ms: int = 0
       weave_delivery_ms: int = 0
       total_ms: int = 0

       def to_breakdown(self) -> dict: ...
       def emit(self, collector: MetricsCollector): ...
   ```

2. **Instrument each phase in FSM controller:**
   - `_run_phase1`: record phase1_start/end
   - `_run_arbiter` (M5): record arbiter_start/end
   - `_deliver_to_front`: record front_start, callback records front_end
   - `_route_via_orchestrator`: record fsm_routing_start/end
   - `_deliver_to_back`: record back_start, callback records back_end
   - `_on_task_complete` -> weave: record weave_decision/delivery

3. **At turn end (response.final)**, emit the full breakdown:

   ```python
   collector.observe("turn.total_latency_ms",
       labels={"turn": turn_number}, value=timer.total_ms)
   collector.observe("turn.phase1_latency_ms",
       labels={}, value=timer.phase1_end_ms - timer.phase1_start_ms)
   # ... for each phase
   bus.publish(build_metric_emitted(payload=timer.to_breakdown()))
   ```

4. **Write breakdown to SS telemetry section:**

   ```python
   manager.mutate("telemetry", "record_turn", timer.to_breakdown())
   ```

**Files:** `poc/k1_poc/obs/metrics.py` (TurnTimer ~60 lines), `poc/k1_poc/fsm/controller.py` (~20 lines of timing instrumentation)

**Acceptance:**

- Every turn produces a latency breakdown with per-phase milliseconds
- Breakdown is emitted as bus event AND written to SS telemetry section
- Test: simulate full turn, verify all 7 phases have non-zero durations

---

### E11.3 -- Protocol Lifecycle Observability

Source: WB 13.5, 12.3, 12.4

**Rationale:** M1-M9 define canonical bus events for protocol lifecycle
(task.created, task.completed, task.cancelled, task.suspended,
task.resumed, hitl.requested, hitl.resolved, hitl.timed_out,
hitl.blocked_red, conversation.intent.arbitrated, conversation.weave.decided,
k1.phase1.classified, k1.ledger.recovery.completed). These events are
emitted but not aggregated into operational metrics. This epic builds
the aggregation layer that converts lifecycle events into dashboards.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 11.3.1 | Build FSM transition counter from lifecycle events | WB 13.5 | None |
| 11.3.2 | Build HITL lifecycle dashboard metrics | WB 12.3 | None |
| 11.3.3 | Build Arbiter decision distribution metrics | WB 13.5 | None |
| 11.3.4 | Build Weave policy effectiveness metrics | WB 13.5 | None |

---

#### 11.3.1 -- Build FSM transition counter from lifecycle events

**Problem:** The FSM emits lifecycle events but there is no aggregated view
of FSM behavior: how often each state is visited, what the most common
transition paths are, how long the FSM spends in each state.

**What to do:**

1. **Create `poc/k1_poc/obs/fsm_metrics.py`** with FSMMetricsSubscriber
   that subscribes to all FSM-related bus topics and tracks:

   ```python
   class FSMMetricsSubscriber:
       def __init__(self, collector: MetricsCollector):
           self._state_durations: dict[str, list[float]] = {}  # state -> [duration_ms]
           self._transition_counts: dict[tuple[str,str], int] = {}  # (from,to) -> count
           self._state_entry_times: dict[str, int] = {}  # state -> entry_ms

       def on_transition(self, from_state: str, to_state: str, ts_ms: int): ...
       def emit_summary(self): ...
   ```

2. **Track per-state dwell time:** When FSM transitions from A to B, record
   `duration_ms = now - entry_time[A]`. Emit `fsm.state.dwell_ms` histogram
   with label `state=A`.

3. **Track transition frequency:** Increment `fsm.transition.count` with
   labels `from=A, to=B`. Common healthy transitions: LISTENING->DISPATCHING,
   DISPATCHING->COMPANIONING. Unusual transitions: WEAVING->WEAVING (self-loop,
   indicates multiple results arriving), CANCELLING->LISTENING (clean cancel).

4. **Detect stuck states:** If any state dwell time exceeds configurable
   threshold (default 120s for COMPANIONING, 300s for CLARIFYING_WORKER),
   emit alert: `fsm.state.stuck` with labels `state, dwell_ms`.

**Files:** New: `poc/k1_poc/obs/fsm_metrics.py` (~80 lines)

**Acceptance:**

- Per-state dwell time histogram emitted
- Per-transition count tracked
- Stuck state alert fires when COMPANIONING exceeds 120s
- Test: simulate LISTENING -> DISPATCHING -> COMPANIONING -> LISTENING cycle, verify metrics

---

#### 11.3.2 -- Build HITL lifecycle dashboard metrics

**Problem:** M6 emits hitl.requested, hitl.resolved, hitl.timed_out,
hitl.blocked_red events. These need aggregation into operational metrics:
HITL request rate, resolution latency (time from requested to resolved),
timeout rate, L2 block rate, HITL round distribution per task.

**What to do:**

1. **Create `poc/k1_poc/obs/hitl_metrics.py`** with HITLMetricsSubscriber:

   ```python
   class HITLMetricsSubscriber:
       def __init__(self, collector: MetricsCollector):
           self._request_times: dict[str, int] = {}  # pending_hil_id -> requested_at_ms

       def on_hitl_requested(self, event): ...
       def on_hitl_resolved(self, event): ...
       def on_hitl_timed_out(self, event): ...
       def on_hitl_blocked_red(self, event): ...
   ```

2. **Metrics emitted:**

   | Metric | Type | Labels | Description |
   |--------|------|--------|-------------|
   | `hitl.request_count` | counter | hil_type | Total HITL requests |
   | `hitl.resolve_latency_ms` | histogram | hil_type | Time from request to resolve |
   | `hitl.timeout_count` | counter | hil_type | HITL timeouts |
   | `hitl.timeout_rate` | gauge | | timeout_count / request_count |
   | `hitl.blocked_red_count` | counter | | RED band safety blocks |
   | `hitl.rounds_per_task` | histogram | | HITL rounds before task completion |
   | `hitl.decision_branch` | counter | branch | clarified/approved/approved_with_mods/cancelled/selected distribution |

3. **Alert thresholds:**
   - `hitl.timeout_rate > 0.3` -> alert "30% HITL requests timing out"
   - `hitl.resolve_latency_ms p95 > 60000` -> alert "users taking >60s to respond"
   - `hitl.blocked_red_count > 0` -> alert "RED safety block occurred" (always alert)

**Files:** New: `poc/k1_poc/obs/hitl_metrics.py` (~100 lines)

**Acceptance:**

- HITL resolve latency histogram tracks time from request to resolution
- Timeout rate calculated and alerted when > 30%
- Decision branch distribution tracked
- Test: emit mock hitl.requested + hitl.resolved events, verify latency calculated

---

#### 11.3.3 -- Build Arbiter decision distribution metrics

**Problem:** M5 emits conversation.intent.arbitrated events. These need
aggregation: what percentage of user inputs during COMPANIONING result in
each Arbiter decision (CANCEL, MODIFY_INFLIGHT, PARALLEL_NEW, DEFER)?
High DEFER rate indicates the user is passive. High CANCEL rate indicates
frustrated users. High MODIFY_INFLIGHT rate indicates underspecified tasks.

**What to do:**

1. **Create `poc/k1_poc/obs/arbiter_metrics.py`** with ArbiterMetricsSubscriber:

   ```python
   class ArbiterMetricsSubscriber:
       def on_intent_arbitrated(self, event):
           decision = event.payload["decision"]
           collector.increment("arbiter.decision_count",
               labels={"decision": decision, "fsm_state": event.payload.get("fsm_state", "")})
           collector.observe("arbiter.confidence",
               labels={"decision": decision},
               value=event.payload["confidence"])
           collector.observe("arbiter.inflight_task_count",
               labels={},
               value=event.payload.get("inflight_task_count", 0))
   ```

2. **Track multi-device conflict rate:** Count events where device_id differs
   from previous event's device_id within the same session. Emit
   `arbiter.multi_device_conflict_count`.

3. **Alert thresholds:**
   - `arbiter.decision_count{decision=DEFER}` / total > 0.5 -> "session stuck in defer loop"
   - `arbiter.decision_count{decision=CANCEL}` / total > 0.4 -> "high cancel rate, check UX"
   - `arbiter.confidence p50 < 0.5` -> "low arbiter confidence, check similarity scoring"

**Files:** New: `poc/k1_poc/obs/arbiter_metrics.py` (~60 lines)

**Acceptance:**

- Per-decision type count tracked
- Confidence histogram tracked
- Multi-device conflict rate calculated
- Test: emit mock arbitrated events, verify distribution

---

#### 11.3.4 -- Build Weave policy effectiveness metrics

**Problem:** M8 emits conversation.weave.decided events. These need
aggregation: what percentage of decisions are IMMEDIATE vs BATCH vs DEFER
vs DIGEST vs SUPPRESS? What is the effective batch window (decided vs
actual delivery time)? How often does the emotional gate suppress results?

**What to do:**

1. **Create `poc/k1_poc/obs/weave_metrics.py`** with WeaveMetricsSubscriber:

   ```python
   class WeaveMetricsSubscriber:
       def on_weave_decided(self, event):
           decision = event.payload["decision"]
           collector.increment("weave.decision_count",
               labels={"decision": decision})
           collector.observe("weave.window_ms",
               labels={"decision": decision},
               value=event.payload.get("window_ms", 0))
           if event.payload.get("emotional_gate_applied"):
               collector.increment("weave.emotional_gate_count",
                   labels={"decision": decision})
   ```

2. **Track delivery quality:**
   - `weave.delivery_latency_ms`: time from task.complete to response.final
     for the woven result
   - `weave.batch_size`: number of results in each weave delivery
   - `weave.digest_compression_ratio`: raw_result_tokens / digest_tokens
   - `weave.user_acknowledged_rate`: fraction of weaves followed by
     user input referencing the woven result (heuristic)

3. **Alert thresholds:**
   - `weave.decision_count{decision=SUPPRESS}` / total > 0.3 -> "excessive suppression"
   - `weave.delivery_latency_ms p95 > 30000` -> "weave delivery too slow"
   - `weave.emotional_gate_count` > 10 per session -> "frequent emotional gating"

**Files:** New: `poc/k1_poc/obs/weave_metrics.py` (~70 lines)

**Acceptance:**

- Per-decision type count tracked
- Emotional gate trigger frequency tracked
- Delivery latency histogram tracked
- Test: emit mock weave.decided events, verify distribution

---

### E11.4 -- Infrastructure Health Telemetry

Source: WB 13.5, 10

**Rationale:** The infrastructure layer (bus, ledger, BackPool, UltraBERT,
SessionState) has health characteristics that affect all higher-level
subsystems. Bus delivery latency affects all event consumers. Ledger write
latency affects crash recovery guarantees. BackPool utilization affects
task queue depth. UltraBERT latency affects Phase 1 timing. SS mutation
guard rejection rate affects cognitive tool reliability.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 11.4.1 | Add bus delivery health metrics | WB 13.5 | None |
| 11.4.2 | Add ledger write/replay health metrics | WB 13.5 | None |
| 11.4.3 | Add BackPool utilization gauge and ready-queue depth | WB 13.5 | None |
| 11.4.4 | Add UltraBERT Phase 1 classification health metrics | WB 13.5 | None |
| 11.4.5 | Add SS mutation guard throughput and rejection metrics | WB 13.5 | None |

---

#### 11.4.1 -- Add bus delivery health metrics

**Problem:** The bus delivers envelopes in STRICT or RELAXED mode but there
is no tracking of delivery latency, dropped messages, or queue depth. A
slow subscriber blocks STRICT delivery. A full queue drops RELAXED messages.

**What to do:**

1. **Instrument bus.publish()** to record:
   - `bus.publish_count` counter (labels: topic, delivery_mode)
   - `bus.delivery_latency_ms` histogram (labels: topic)
   - `bus.subscriber_count` gauge (labels: topic)
   - `bus.dropped_count` counter (labels: topic, reason)

2. **Instrument bus.subscribe()** to track subscriber health:
   - Time from publish to subscriber callback invocation
   - If subscriber raises exception: `bus.subscriber_error_count`

3. **Alert thresholds:**
   - `bus.delivery_latency_ms p95 > 100` -> "bus delivery slow"
   - `bus.dropped_count > 0` -> "bus dropping messages"
   - `bus.subscriber_error_count > 0` -> "subscriber errors"

**Files:** `poc/k1_poc/bus/setup.py` or `bus/core.py` (~20 lines of instrumentation)

**Acceptance:**

- Per-topic publish count, delivery latency, dropped count tracked
- Subscriber error count tracked
- Test: publish 100 events, verify publish_count = 100

---

#### 11.4.2 -- Add ledger write/replay health metrics

**Problem:** M9 introduces ledger write at every protocol mutation. Ledger
write latency directly impacts turn latency (writes are synchronous --
the mutation is rejected if the ledger write fails). There is no tracking
of ledger health.

**What to do:**

1. **Instrument LedgerWriter.append()** to record:
   - `ledger.append_latency_ms` histogram
   - `ledger.append_count` counter (labels: event_type)
   - `ledger.append_error_count` counter
   - `ledger.total_events` gauge

2. **Instrument CrashRecoveryOrchestrator.recover()** to record:
   - `ledger.replay_duration_ms` histogram
   - `ledger.replay_event_count` gauge
   - `ledger.replay_error_count` counter

3. **Alert thresholds:**
   - `ledger.append_latency_ms p95 > 5` -> "ledger write slow" (target < 1ms for in-memory)
   - `ledger.append_error_count > 0` -> "ledger write failures"
   - `ledger.replay_duration_ms > 5000` -> "slow recovery"

**Files:** `poc/k1_poc/ledger/writer.py` (instrument append, ~10 lines), `poc/k1_poc/ledger/recovery.py` (instrument recover, ~10 lines)

**Acceptance:**

- Ledger append latency tracked per event type
- Recovery replay duration tracked
- Test: append 100 events, verify latency histogram has 100 observations

---

#### 11.4.3 -- Add BackPool utilization gauge and ready-queue depth

**Problem:** M7 emits worker.acquired/released events but there is no
real-time gauge for pool utilization or ready-queue depth. Pool saturation
means all new tasks queue. Ready-queue depth > 0 with dependencies means
tasks are blocked.

**What to do:**

1. **Instrument BackPool** to emit continuous gauges:
   - `backpool.utilization` gauge: active_workers / pool_size (0.0-1.0)
   - `backpool.active_workers` gauge: count of currently occupied slots
   - `backpool.ready_queue_depth` gauge: count of envelopes waiting
   - `backpool.dependency_blocked_count` gauge: tasks in ready-queue
     waiting for predecessor completion

2. **Instrument lease lifecycle:**
   - `backpool.lease_expiry_count` counter
   - `backpool.lease_renewal_count` counter
   - `backpool.lease_duration_ms` histogram (from granted to released)

3. **Alert thresholds:**
   - `backpool.utilization > 0.9` for > 30s -> "pool near saturation"
   - `backpool.lease_expiry_count > 0` -> "task lease expired (potential zombie)"
   - `backpool.ready_queue_depth > 5` -> "deep ready-queue (check dependencies)"

**Files:** `poc/k1_poc/actors/back_pool.py` (~15 lines of instrumentation)

**Acceptance:**

- Pool utilization gauge updated on every acquire/release
- Ready-queue depth tracked
- Lease lifecycle metrics tracked
- Test: acquire 3 workers in pool of 3, verify utilization = 1.0

---

#### 11.4.4 -- Add UltraBERT Phase 1 classification health metrics

**Problem:** M10 emits k1.phase1.classified.v1 and k1.phase1.degraded.v1
events. These need aggregation into health metrics: classification latency
histogram, tier distribution, safety band distribution, degradation rate.

**What to do:**

1. **Subscribe to k1.phase1.classified.v1 and k1.phase1.degraded.v1:**

   ```python
   class Phase1MetricsSubscriber:
       def on_classified(self, event):
           collector.observe("phase1.latency_ms", labels={},
               value=event.payload["classification_latency_ms"])
           collector.increment("phase1.tier_count",
               labels={"tier": event.payload["complexity_tier"]})
           collector.increment("phase1.safety_band_count",
               labels={"band": event.payload["safety_band"]})
           collector.increment("phase1.intent_count",
               labels={"intent": event.payload["intent_primary"]})
       def on_degraded(self, event):
           collector.increment("phase1.degraded_count",
               labels={"reason": event.payload["reason"]})
   ```

2. **Track classification-to-outcome correlation:**
   - When task.complete arrives, look up the Phase 1 tier assignment for
     that task. Compare tier with Back's budget utilization. If tier=LOW
     and budget_utilization=1.0, record `phase1.tier_mismatch_count`.

3. **Alert thresholds:**
   - `phase1.latency_ms p95 > 50` -> "UltraBERT slow"
   - `phase1.degraded_count > 0` -> "UltraBERT degraded mode active"
   - `phase1.safety_band_count{band=CRISIS}` > 0 -> "CRISIS detected"
   - `phase1.tier_mismatch_count` / total > 0.2 -> "20% tier mismatches"

**Files:** New: `poc/k1_poc/obs/phase1_metrics.py` (~70 lines)

**Acceptance:**

- Classification latency histogram tracked
- Tier and safety band distribution tracked
- Degradation rate tracked
- Tier mismatch detection works

---

#### 11.4.5 -- Add SS mutation guard throughput and rejection metrics

**Problem:** M4 routes all cognitive tool writes through MutationGuard.
Guard rejections mean the LLM's tool call was denied (section at capacity,
unauthorized section, etc.). High rejection rates indicate SS pressure
issues or misconfigured tool behavior.

**What to do:**

1. **Instrument MutationGuard.preflight()** to record:
   - `ss.mutation.count` counter (labels: section, operation, writer_id)
   - `ss.mutation.rejected_count` counter (labels: section, reason)
   - `ss.mutation.latency_ms` histogram (labels: section)

2. **Instrument SizeTracker** to emit budget proximity gauges:
   - `ss.section.usage_bytes` gauge (labels: section)
   - `ss.section.budget_utilization` gauge (labels: section) = usage / budget
   - `ss.total.usage_bytes` gauge
   - `ss.total.budget_utilization` gauge = total / 96KB

3. **Alert thresholds:**
   - `ss.mutation.rejected_count` > 3 per turn -> "frequent mutation rejections"
   - `ss.section.budget_utilization{section=beliefs_active}` > 0.9 -> "beliefs near capacity"
   - `ss.total.budget_utilization > 0.85` -> "SS approaching 96KB limit"

**Files:** `poc/k1_poc/sessionstate/manager.py` (~15 lines), `poc/k1_poc/sessionstate/sizetracker.py` (~10 lines)

**Acceptance:**

- Per-section mutation count and rejection count tracked
- Per-section budget utilization gauge emitted
- Total SS utilization gauge emitted
- Test: fill beliefs_active to 90%, verify budget_utilization = 0.9

---

### E11.5 -- Alert Engine & Session Summary

Source: WB 15.4.C, 15.5 P2, 13.5

**Rationale:** Raw metrics need alert evaluation. A threshold crossing
should emit an alert event that operators can subscribe to. At session end,
a comprehensive summary should be emitted for post-hoc analysis.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 11.5.1 | Implement AlertEngine with configurable threshold rules | WB 15.4.C | None |
| 11.5.2 | Define alert threshold configuration in defaults.yaml | WB 15.4.C | None |
| 11.5.3 | Emit per-session observability summary at session end | WB 13.5 | None |
| 11.5.4 | Wire AlertEngine into MetricAggregator evaluation loop | WB 15.4.C | None |

---

#### 11.5.1 -- Implement AlertEngine with configurable threshold rules

**Problem:** Metrics are collected and aggregated but never evaluated
against thresholds. No alerts fire.

**What to do:**

1. **Create `poc/k1_poc/obs/alerts.py`:**

   ```python
   @dataclass
   class AlertRule:
       name: str                   # e.g., "high_degenerate_rate"
       metric_name: str            # e.g., "react_loop.front.degenerate_count"
       labels: dict[str, str]      # filter labels
       condition: str              # "rate_gt", "p95_gt", "count_gt", "gauge_gt"
       threshold: float
       window_s: float = 300.0     # evaluation window
       cooldown_s: float = 600.0   # suppress re-alerts for this period
       severity: str = "warning"   # "info", "warning", "critical"

   class AlertEngine:
       def __init__(self, rules: list[AlertRule], aggregator: MetricAggregator,
                    bus: EventBus):
           self._rules = rules
           self._last_fired: dict[str, int] = {}  # rule_name -> last_fired_ms

       def evaluate(self) -> list[AlertEvent]: ...
       def emit_alerts(self, alerts: list[AlertEvent]): ...
   ```

2. **AlertEvent emitted on bus** via `build_metric_alert()` with payload:
   rule_name, metric_name, current_value, threshold, severity, timestamp.

3. **Cooldown prevents alert storms:** Same rule does not fire more than
   once per cooldown_s.

**Files:** New: `poc/k1_poc/obs/alerts.py` (~100 lines)

**Acceptance:**

- AlertEngine evaluates rules against aggregated metrics
- Alerts emitted on bus when threshold crossed
- Cooldown prevents duplicate alerts
- Test: inject metric above threshold, verify alert fires once, not twice within cooldown

---

#### 11.5.2 -- Define alert threshold configuration in defaults.yaml

**Problem:** Alert thresholds must be configurable without code changes.

**What to do:**

1. **Add to `config/defaults.yaml` under `obs.alerts:`:**

   ```yaml
   obs:
     alerts:
       enabled: true
       rules:
         - name: high_degenerate_rate
           metric: react_loop.front.degenerate_count
           condition: rate_gt
           threshold: 0.3
           window_s: 300
           severity: warning
         - name: pool_saturation
           metric: backpool.utilization
           condition: gauge_gt
           threshold: 0.9
           window_s: 30
           severity: critical
         - name: ledger_write_slow
           metric: ledger.append_latency_ms
           condition: p95_gt
           threshold: 5.0
           severity: warning
         - name: hitl_timeout_high
           metric: hitl.timeout_rate
           condition: gauge_gt
           threshold: 0.3
           severity: warning
         - name: phase1_degraded
           metric: phase1.degraded_count
           condition: count_gt
           threshold: 0
           severity: critical
         - name: ss_near_capacity
           metric: ss.total.budget_utilization
           condition: gauge_gt
           threshold: 0.85
           severity: warning
         - name: crisis_detected
           metric: phase1.safety_band_count
           labels: {band: CRISIS}
           condition: count_gt
           threshold: 0
           severity: critical
         - name: bus_dropping_messages
           metric: bus.dropped_count
           condition: count_gt
           threshold: 0
           severity: critical
         - name: tier_mismatch_high
           metric: phase1.tier_mismatch_count
           condition: rate_gt
           threshold: 0.2
           severity: warning
         - name: session_stuck_defer
           metric: arbiter.decision_count
           labels: {decision: DEFER}
           condition: rate_gt
           threshold: 0.5
           severity: warning
         - name: excessive_weave_suppress
           metric: weave.decision_count
           labels: {decision: SUPPRESS}
           condition: rate_gt
           threshold: 0.3
           severity: warning
         - name: back_budget_exhaustion
           metric: back.tier.budget_utilization
           condition: p95_gt
           threshold: 0.95
           severity: warning
   ```

**Files:** `poc/k1_poc/config/defaults.yaml` (~50 lines)

**Acceptance:**

- All 12 alert rules defined and loadable via get_config()
- Each rule has name, metric, condition, threshold, severity
- Test: load config, verify 12 AlertRule objects created

---

#### 11.5.3 -- Emit per-session observability summary at session end

**Problem:** At session end, a comprehensive summary of all metrics should
be emitted for post-hoc analysis: total turns, total tasks, HITL count,
weave count, fallback rates, latency percentiles, alert count.

**What to do:**

1. **On session teardown** (FSM shutdown or coordinator close), collect:

   ```python
   summary = {
       "session_id": session_id,
       "total_turns": turn_count,
       "total_tasks": task_count,
       "total_hitl_requests": hitl_request_count,
       "total_weave_deliveries": weave_count,
       "react_loop": {
           "front": {
               "total_invocations": N,
               "degenerate_rate": X,
               "budget_exhaustion_rate": Y,
               "avg_iterations": Z,
               "mode_distribution": {"STANDARD": N, "WEAVE": N, ...},
           },
           "back": {
               "total_invocations": N,
               "cancel_count": N,
               "suspension_count": N,
               "tier_distribution": {"LOW": N, "MEDIUM": N, "HIGH": N},
               "avg_budget_utilization": X,
           },
       },
       "phase1": {
           "avg_latency_ms": X,
           "degraded_count": N,
           "tier_distribution": {"LOW": N, "MEDIUM": N, "HIGH": N},
           "safety_band_distribution": {"GREEN": N, "AMBER": N, "RED": N, "CRISIS": N},
       },
       "latency": {
           "turn_total_p50_ms": X,
           "turn_total_p95_ms": X,
           "phase1_p50_ms": X,
           "front_p50_ms": X,
           "back_p50_ms": X,
       },
       "alerts_fired": alert_count,
       "alert_details": [...],
   }
   ```

2. **Emit as `k1.metrics.session_summary.v1`** bus event.

3. **Write summary to SS telemetry section** as final entry.

**Files:** `poc/k1_poc/obs/metrics.py` (add session_summary method, ~50 lines)

**Acceptance:**

- Session summary emitted on bus at session end
- Summary includes all 6 metric families
- Summary written to SS telemetry section
- Test: simulate 10-turn session, verify summary has correct counts

---

#### 11.5.4 -- Wire AlertEngine into MetricAggregator evaluation loop

**Problem:** The AlertEngine needs to be periodically evaluated against
the latest aggregated metrics. Without periodic evaluation, alerts never
fire.

**What to do:**

1. **In bootstrap.py**, create an asyncio background task that evaluates
   alerts periodically:

   ```python
   async def _alert_evaluation_loop(engine: AlertEngine, interval_s: float):
       while True:
           await asyncio.sleep(interval_s)
           alerts = engine.evaluate()
           if alerts:
               engine.emit_alerts(alerts)
   ```

2. **Default evaluation interval:** 10 seconds (configurable via
   `obs.alerts.evaluation_interval_s`).

3. **Graceful shutdown:** Cancel the alert loop task on session teardown.

**Files:** `poc/k1_poc/kernel/bootstrap.py` (~10 lines)

**Acceptance:**

- Alert evaluation loop runs as background task
- Alerts evaluated every 10 seconds
- Loop cancels cleanly on shutdown
- Test: set threshold, inject metrics above threshold, verify alert fires within 10s

---

### M11 Implementation Order

1. **11.1.1** (MetricEnvelope + MetricsCollector -- foundation for everything)
2. **11.1.2** (MetricAggregator with sliding windows)
3. **11.1.3** (metric bus topics and emission helpers)
4. **11.1.4** (wire into bootstrap)
5. **11.2.1** (instrument ReAct loop fallback paths -- highest signal value)
6. **11.2.2** (Front per-mode quality metrics)
7. **11.2.3** (Back per-tier quality metrics)
8. **11.2.4** (end-to-end turn latency breakdown)
9. **11.3.1** (FSM transition counter)
10. **11.3.2** (HITL lifecycle metrics)
11. **11.3.3** (Arbiter decision metrics)
12. **11.3.4** (Weave policy metrics)
13. **11.4.1** (bus delivery health)
14. **11.4.2** (ledger write/replay health)
15. **11.4.3** (BackPool utilization + ready-queue)
16. **11.4.4** (UltraBERT Phase 1 health)
17. **11.4.5** (SS mutation guard throughput)
18. **11.5.1** (AlertEngine)
19. **11.5.2** (alert threshold config)
20. **11.5.4** (wire alert evaluation loop)
21. **11.5.3** (per-session summary -- last, requires all metrics active)

**Total: 21 issues across 5 epics.**

---

## M12: Chaos & Concurrency Validation

**Goal:** End-to-end concurrency scenario tests proving V3 correctness under
adversarial timing. Multi-device conflicts, interrupt storms, overlapping
HITL, completion races, pool exhaustion, weave bursts, ledger replay
determinism, and crash recovery verification. Each test targets a specific
race condition or concurrency hazard identified during M0-M10 implementation.
Tests exercise the FULL stack: bus -> FSM -> actors -> protocols -> ledger.

**Gate:** All 25+ chaos scenarios pass deterministically (no flaky tests).
Ledger replay matches runtime state for every scenario. Dead-letter pipeline
correctly captures orphan events. CancellationToken cooperative exit works
under concurrent task completion. HITL paths never deadlock or bypass
approvals under concurrency. Weave policy produces deterministic decisions
under burst task completions. BackPool handles exhaustion gracefully without
data loss. Multi-device arbitration resolves conflicts without silent message
drops.

**Depends on:** M0-M10 (all subsystems must be implemented), M11 (observability
metrics validate correct behavior under chaos).

### Why Chaos Testing Is Hard (Cross-Milestone Race Condition Audit)

**Every milestone M0-M10 introduces concurrency hazards that are NOT
exercised by unit tests or single-threaded integration tests. The hazards:**

| Milestone | Concurrency Hazard | Race Window | Impact If Untested |
|-----------|-------------------|-------------|-------------------|
| M0 | Bus subscription routing under concurrent publish | Between subscribe() and first publish() | Subscriber misses first event. Dead-letter not triggered. |
| M1 | Ledger writer under concurrent appends | Two protocol mutations in same millisecond | Event ordering violation. Replay produces different state. |
| M2 | FSM guard matrix under concurrent state transitions | Interrupt arrives during DELIVERING->LISTENING transition | Guard allows invalid transition. FSM enters impossible state. |
| M2 | Dead-letter under burst event emission | 100 events in 10ms with mixed valid/invalid | Dead-letter queue overflow. Valid events misrouted to DLQ. |
| M3 | Cancel during active ReAct loop iteration | Token.cancel() during model.generate() await | Cancel invisible until next iteration. Back produces one more tool call after cancel. |
| M3 | Resume routing under topic race | task.resume.v1 and task.cancel.v1 arrive simultaneously | Router dispatches both. back_resume_handler starts while back_cancel_handler sets flag. Resume loop runs 1 iteration then exits cancelled. |
| M4 | SS mutation guard under concurrent cognitive tool writes | Two tools write beliefs_active simultaneously | Both pass capacity check. Combined write exceeds budget. SizeTracker drift. |
| M4 | SizeTracker accuracy under concurrent pressure management | EvictionEngine runs while tool writes | Eviction removes entries that tool just wrote. Data loss. |
| M5 | Multi-device Arbiter under simultaneous inputs | Device A sends "book hotel" while device B sends "cancel" | Both processed. Cancel wins by priority. But device A's "book" may have started a task. Cancel must target the just-started task. |
| M5 | Interrupt storm: rapid sequential interrupts | 5 user inputs in 2 seconds during COMPANIONING | Each triggers Arbiter. FrontLock serializes Front invocations. But FSM state changes between each input. Later inputs see stale Arbiter decisions. |
| M6 | Overlapping HITL responses from multiple devices | Device A answers "yes" while device B answers "no" | First response wins. Second is discarded. But if first response triggers Back resume and second arrives during Back's react_loop... |
| M6 | HITL timeout concurrent with user response | Timeout fires at T=120s. User responds at T=119.9s. | Race: response processes, then timeout fires and cancels the already-resumed task. Or timeout fires first, then response arrives for a cancelled task. |
| M6 | Crash mid-HITL with partial ledger write | Process crashes between ledger.append(task.suspended) and SuspensionManager._active update | Ledger has the event. In-memory state does not. Restart replays correctly. But if crash between SS write and ledger write, state diverges. |
| M7 | Pool exhaustion under burst task dispatch | Front dispatches 5 tasks. Pool size = 3. | 3 tasks acquire workers. 2 queue. If first 3 fail quickly, queued tasks must be re-evaluated (predecessor may have failed). |
| M7 | Lease expiry during active LLM call | Lease expires while model.generate() is blocking | Cooperative cancel via token. But model.generate blocks. Grace period (5s). Hard kill if still blocked. Orphaned HTTP connection? |
| M7 | Dependency cycle detection under concurrent dispatch | Front dispatches A depends_on B and B depends_on A in same turn | Both enter ready-queue. Neither dependency satisfied. Deadlock if not detected. |
| M8 | Weave burst: 5 task.complete in 500ms window | All 5 arrive during COMPANIONING. Policy evaluates 5 times. | First evaluates to BATCH(500ms). Timer starts. Second arrives at T+100ms. Re-evaluate? Or accumulate? Third arrives at T+200ms. What if typing detected at T+300ms? Timer must pause. |
| M8 | Emotional gate + urgent result race | Policy suppresses (negative valence). Then a CRISIS-urgent result arrives. | Urgent overrides emotional gate. But if the suppress decision already queued a DEFER, the urgent result must promote the deferred queue to IMMEDIATE. |
| M9 | Ledger replay determinism | Same event stream replayed twice must produce identical state | Non-determinism in dict ordering, timestamp resolution, or float precision breaks deterministic replay. |
| M9 | Crash recovery with partial ledger | Process crashes mid-append | Ledger may have partial event. Reader must handle truncated entries. Recovery must skip corrupt entries and log warning. |
| M10 | UltraBERT failure during active Phase 1 | GPU runs out of memory or model hangs | Phase 1 blocks. TurnLock held. Front cannot start. User waits. Timeout needed. |
| M10 | Tier routing under classification flicker | Same text classified as MEDIUM on turn 1, LOW on turn 2 | Back started with MEDIUM budget. Second classification has no effect (task already dispatched). But if task is suspended and resumed, the new tier might apply. |

### M12 LLM Interaction Model

| Test Category | What LLM Behavior Is Validated |
|--------------|-------------------------------|
| Cancel races (E12.1) | Back LLM exits between iterations on cancel. No tool calls after cancel flag. |
| Interrupt storms (E12.2) | Front LLM invocations are serialized by FrontLock. No concurrent Front loops. |
| HITL concurrency (E12.3) | Back resume LLM gets complete prior_messages. No duplicate resumes. |
| Weave burst (E12.4) | Front WEAVE LLM gets correctly batched results. No partial batches. |
| Ledger replay (E12.5) | After replay, Front LLM sees same history as before crash. |

---

### E12.1 -- Cancel & Completion Race Tests

Source: WB 8.8, 12.5.3

**Rationale:** The most common race condition in the system is between
task cancellation and task completion. When a user cancels while Back's
ReAct loop is executing, the cancel flag is set but the loop continues
until the next iteration boundary. If the loop completes between the
cancel flag and the next iteration check, the task has both a cancel
and a completion. The FSM must handle this deterministically.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.1.1 | Test: cancel arrives during Back react_loop -- cooperative exit | WB 8.8 | Validates cancel-between-iterations works |
| 12.1.2 | Test: late task.complete after cancel with dead-letter capture | WB 12.5 | Validates dead-letter for orphan completions |
| 12.1.3 | Test: cancel during model.generate (mid-LLM-call) | WB 8.8 | Validates cancel latency = 1 LLM call |
| 12.1.4 | Test: double cancel (cancel same task twice) | WB 8.8 | Validates idempotent cancel handling |
| 12.1.5 | Test: cancel non-existent task_id | WB 8.8 | Validates graceful handling of invalid cancel |

---

#### 12.1.1 -- Test: cancel arrives during Back react_loop

**Problem:** Validate that CancellationToken cooperative cancellation works
when cancel arrives between ReAct iterations. The loop should exit on
the next iteration boundary with status="cancelled".

**Scenario:**

```
T=0ms:   FSM dispatches task T1 to Back. BackPool acquires worker.
T=1ms:   Back starts react_loop with CancellationToken from TaskLease.
T=50ms:  Iteration 1: LLM returns tool call (recall_memory). Tool executes.
T=100ms: Iteration 2 starts. cancellation_check() returns False. LLM call begins.
T=150ms: User says "cancel". Arbiter -> CANCEL. FSM calls token.cancel().
T=200ms: Iteration 2: model.generate() returns. Tool call executes.
T=250ms: Iteration 3 starts. cancellation_check() returns True.
T=251ms: react_loop returns ReactResult(status="cancelled").
T=252ms: FSM receives task.failed(reason="cancelled"). TaskBridge updates status.
```

**Assertions:**

1. react_loop returns status="cancelled" (not "ok" or "failed")
2. Iterations completed = 2 (not 3 -- loop exits at iteration 3 boundary)
3. CancellationToken.is_cancelled == True after cancel()
4. TaskStateEntry.status == "cancelled" in SS
5. No tool call in iteration 3 (loop exited before LLM call)
6. Bus event task.failed with reason="cancelled" emitted

**Files:** New: `tests/poc/test_m12_chaos_cancel.py`

**Acceptance:**

- Test passes deterministically (no flakiness from timing)
- Uses mock LLM with configurable delay to control iteration timing
- Validates all 6 assertions

---

#### 12.1.2 -- Test: late task.complete after cancel with dead-letter

**Problem:** Back completes task T1 with a result. But T1 was already
cancelled by the FSM. The task.complete event arrives AFTER task.cancelled
was processed. The completion should be captured by the dead-letter pipeline.

**Scenario:**

```
T=0:     FSM dispatches T1. Back starts.
T=100ms: User cancels T1. FSM emits task.cancel.
T=110ms: back_cancel_handler sets cancel flag.
T=200ms: Back's react_loop was already past the cancel check for this iteration.
         LLM returns. Tool executes (one extra tool call after cancel -- expected).
T=250ms: Next iteration: cancel check fires. react_loop exits with "cancelled".
T=260ms: BUT: the tool result from T=200ms included a side effect that produced
         a task.complete event (e.g., the tool was invoke_capability which
         completed before cancel propagated to it).
T=300ms: FSM receives task.complete for T1.
T=301ms: FSM checks: is_cancelled(T1) == True.
T=302ms: FSM routes task.complete to dead-letter with reason="late_completion_after_cancel".
```

**Assertions:**

1. Dead-letter receives the late completion event
2. Dead-letter entry has reason="late_completion_after_cancel"
3. FSM does NOT transition to DELIVERING (task is cancelled)
4. User does NOT see the completion result
5. Dead-letter counts_by_reason["late_completion_after_cancel"] incremented

**Files:** `tests/poc/test_m12_chaos_cancel.py` (add test)

**Acceptance:**

- Late completion routed to dead-letter, not to user
- Dead-letter counters accurate
- No FSM state corruption

---

#### 12.1.3 -- Test: cancel during model.generate (mid-LLM-call)

**Problem:** Cancel flag is set while model.generate() is actively blocking
(HTTP call to LLM API). The loop does not check cancel mid-call. This test
validates the expected latency: cancel takes effect at the NEXT iteration
boundary, not mid-call.

**Scenario:**

```
T=0:     react_loop iteration 2 starts. cancellation_check() = False.
T=1ms:   model.generate() called. Blocks for 5000ms (simulated slow LLM).
T=2500ms: Cancel flag set externally.
T=5001ms: model.generate() returns.
T=5002ms: Tool calls executed (one batch after cancel flag).
T=5003ms: Iteration 3 starts. cancellation_check() = True. Loop exits.
```

**Assertions:**

1. Cancel latency = ~5003ms - 2500ms = ~2503ms (one full LLM call duration)
2. Tool calls from iteration 2 WERE executed (unavoidable -- cancel is cooperative)
3. No tool calls from iteration 3
4. M11 metric: back.cancel_to_exit_latency_ms records ~2500ms

**Files:** `tests/poc/test_m12_chaos_cancel.py` (add test)

**Acceptance:**

- Cancel latency matches expected range (LLM call duration)
- Tool calls from the iteration that was in-flight are correctly executed
- Metric records actual latency

---

#### 12.1.4 -- Test: double cancel

**Problem:** User says "cancel" twice quickly. Both produce Arbiter CANCEL
decisions. Both emit task.cancel events. CancellationToken.cancel() must be
idempotent. back_cancel_handler must handle duplicate cancel for same task_id.

**Assertions:**

1. Second cancel() on same token is no-op
2. CancellationToken.is_cancelled still True (not flipped back)
3. No exception from duplicate cancel
4. FSM does not transition twice (CANCELLING -> CANCELLING is not in transition table)
5. Dead-letter captures the second cancel event as duplicate

**Files:** `tests/poc/test_m12_chaos_cancel.py` (add test)

**Acceptance:**

- Idempotent cancel verified
- No exception, no state corruption

---

#### 12.1.5 -- Test: cancel non-existent task_id

**Problem:** A cancel event arrives for a task_id that was never dispatched
(stale event, replay artifact, or bug). The system must handle gracefully.

**Assertions:**

1. FSM logs warning "cancel for unknown task_id"
2. No exception, no crash
3. No state corruption (active_task_ids unchanged)
4. Dead-letter captures the orphan cancel event

**Files:** `tests/poc/test_m12_chaos_cancel.py` (add test)

**Acceptance:**

- Graceful handling of unknown task_id
- Dead-letter captures orphan event

---

### E12.2 -- Interrupt Storm & Multi-Device Tests

Source: WB 8.8, 6

**Rationale:** Interrupt storms test the Arbiter + FrontLock + FSM pipeline
under rapid sequential user inputs. Multi-device tests validate that the
Arbiter correctly resolves conflicting signals from different devices in
the same session.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.2.1 | Test: interrupt storm -- 5 rapid user inputs during COMPANIONING | WB 8.8 | Validates FrontLock serialization |
| 12.2.2 | Test: multi-device conflicting inputs with Arbiter resolution | WB 6 | Validates device precedence |
| 12.2.3 | Test: multi-device HITL response race | WB 6 | Validates first-response-wins |
| 12.2.4 | Test: device conflict on high-impact action requiring confirmation | WB 6 | Validates confirmation flow |

---

#### 12.2.1 -- Test: interrupt storm -- 5 rapid user inputs during COMPANIONING

**Problem:** User (or automated test) sends 5 messages in 2 seconds while
the system is in COMPANIONING state. Each message triggers Arbiter
classification. FrontLock serializes Front invocations. The test validates
that all 5 messages are processed in order without data loss or state
corruption.

**Scenario:**

```
T=0:     FSM in COMPANIONING. Back processing task T1.
T=100ms: User input 1: "what about lunch?" -> Arbiter -> PARALLEL_NEW
T=300ms: User input 2: "actually cancel that" -> Arbiter -> CANCEL
T=500ms: User input 3: "never mind, keep going" -> Arbiter -> DEFER
T=700ms: User input 4: "can you also check weather?" -> Arbiter -> PARALLEL_NEW
T=900ms: User input 5: "make the hotel 2 nights" -> Arbiter -> MODIFY_INFLIGHT (if T1 still active)
```

**Assertions:**

1. All 5 inputs recorded in history (no message loss)
2. Arbiter decisions are consistent with input content and FSM state at time of evaluation
3. Cancel (input 2) takes precedence over parallel_new (input 1)
4. FrontLock serializes: only one Front invocation runs at a time
5. No FSM state corruption (no impossible transitions)
6. Final FSM state is deterministic given the input sequence
7. conversation.intent.arbitrated events emitted for all 5 inputs (in order)

**Files:** New: `tests/poc/test_m12_chaos_interrupt.py`

**Acceptance:**

- All 5 messages processed without loss
- Order preserved in history
- FrontLock serialization verified (no concurrent Front loops)

---

#### 12.2.2 -- Test: multi-device conflicting inputs

**Problem:** Device A sends "book the hotel" while device B sends "cancel
the hotel search" within 500ms. The Arbiter must resolve deterministically
using precedence rules (cancel > new request).

**Scenario:**

```
T=0:     COMPANIONING, Back searching hotels.
T=100ms: Device A: "go ahead and book it" -> Arbiter -> could be MODIFY_INFLIGHT or PARALLEL_NEW
T=200ms: Device B: "cancel the hotel search" -> Arbiter -> CANCEL
```

**Assertions:**

1. Cancel from device B takes precedence (priority 1 > 5)
2. Device A's "book" is deferred or discarded (depends on whether CANCEL arrived first)
3. No booking executed (cancel wins)
4. Both devices' inputs are recorded in history with device_id labels
5. Arbiter event for device B shows decision=CANCEL, device A shows decision deferred

**Files:** `tests/poc/test_m12_chaos_interrupt.py` (add test)

**Acceptance:**

- Cancel wins over conflicting action
- No side effect from the losing device's input
- Both inputs logged

---

#### 12.2.3 -- Test: multi-device HITL response race

**Problem:** HITL question is pending. Device A answers "yes" and device B
answers "no" within 100ms. Only the first response should be processed.

**Assertions:**

1. First response (chronologically) is processed
2. Second response is discarded with warning log
3. Back resumes with first response's resolution
4. No duplicate resume (second response does not start a new react_loop)
5. Discarded response logged with device_id for audit

**Files:** `tests/poc/test_m12_chaos_interrupt.py` (add test)

**Acceptance:**

- First-response-wins semantics
- No duplicate resume
- Discarded response auditable

---

#### 12.2.4 -- Test: device conflict on high-impact action

**Problem:** Device A says "book the hotel" (high-impact: payment) while
device B says "search for cheaper options" (not high-impact). Since device
A's action is high-impact and device B disagrees, confirmation is required.

**Assertions:**

1. System detects conflicting high-impact action
2. Both actions deferred
3. Clarification request emitted: "Conflicting requests from two devices..."
4. FSM transitions to CLARIFYING_USER
5. User resolves on either device
6. Resolved action executes

**Files:** `tests/poc/test_m12_chaos_interrupt.py` (add test)

**Acceptance:**

- Confirmation flow triggered for high-impact conflict
- Neither action executes until user resolves
- Resolution correctly routes to chosen action

---

### E12.3 -- HITL Concurrency & Crash Recovery Tests

Source: WB 12.5.3, 9.6

**Rationale:** HITL is the highest-stakes concurrency area. A race between
timeout and user response can cause either a task to be cancelled when the
user already answered, or a task to be resumed after it was timed out. Crash
recovery must correctly rebuild HITL state including react_history.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.3.1 | Test: HITL timeout concurrent with user response (timeout wins) | WB 12.5 | Validates timeout-cancel path |
| 12.3.2 | Test: HITL timeout concurrent with user response (response wins) | WB 12.5 | Validates response-resume path |
| 12.3.3 | Test: HITL paths never deadlock under concurrent resume+cancel | WB 9 | Validates no deadlock |
| 12.3.4 | Test: HITL approval bypass attempt under concurrency | WB 9 | Validates L2 defense |
| 12.3.5 | Test: crash mid-HITL with full ledger recovery | WB 9.6 | Validates crash recovery |
| 12.3.6 | Test: crash mid-HITL with partial ledger (corrupt entry) | WB 9.6 | Validates degraded recovery |

---

#### 12.3.1 -- Test: HITL timeout concurrent with user response (timeout wins)

**Problem:** HITL timeout fires at T=120000ms. User response arrives at
T=120100ms (100ms late). The timeout has already cancelled the task.

**Scenario:**

```
T=0:       Back suspends task T1 for HITL approval. HILSubTask created.
T=0:       Timeout watcher starts (120s).
T=120000ms: Timeout fires. HILSubTask.status -> TIMED_OUT. Task cancelled.
T=120100ms: User responds "yes, approve".
```

**Assertions:**

1. Timeout fires and task is cancelled
2. User response arrives for a TIMED_OUT HILSubTask
3. Response is discarded (resume_token mismatch or status check)
4. hitl.timed_out event emitted BEFORE the response arrives
5. User is informed that the question expired
6. No Back resume (task is cancelled)
7. Dead-letter captures the late HITL response

**Files:** New: `tests/poc/test_m12_chaos_hitl.py`

**Acceptance:**

- Timeout wins, response discarded
- No state corruption
- User informed of expiry

---

#### 12.3.2 -- Test: HITL timeout concurrent with user response (response wins)

**Problem:** User response arrives at T=119900ms (100ms before timeout).
The response should be processed and the timeout should be cancelled.

**Scenario:**

```
T=0:       Back suspends task T1. Timeout = 120s.
T=119900ms: User responds. HILCoordinator processes response.
T=119901ms: HILSubTask.status -> RESOLVED. Timeout watcher task cancelled.
T=120000ms: Timeout check runs but HILSubTask is already RESOLVED.
```

**Assertions:**

1. Response processed before timeout fires
2. Timeout watcher cancelled (asyncio.Task.cancel)
3. Back resume dispatched with correct ResumeContext
4. hitl.resolved event emitted (not hitl.timed_out)
5. Task continues normally after resume

**Files:** `tests/poc/test_m12_chaos_hitl.py` (add test)

**Acceptance:**

- Response wins, timeout cancelled
- Back resumes correctly
- No double-processing

---

#### 12.3.3 -- Test: HITL no deadlock under concurrent resume+cancel

**Problem:** While a HITL is pending, user cancels the task AND another
device responds to the HITL question simultaneously. These operations
contend for the same HILSubTask.

**Assertions:**

1. No deadlock (no infinite wait)
2. One operation wins (cancel or resume, whichever processes first)
3. The losing operation is handled gracefully (discarded or dead-lettered)
4. FSM reaches a terminal state (LISTENING or DELIVERING, not stuck)
5. No orphan asyncio.Task (timeout watcher cleaned up)

**Files:** `tests/poc/test_m12_chaos_hitl.py` (add test)

**Acceptance:**

- No deadlock under any ordering
- Clean state after resolution

---

#### 12.3.4 -- Test: HITL approval bypass attempt

**Problem:** After HITL approval, Back resumes and calls invoke_capability.
Concurrently, a second invoke_capability call attempts to execute without
approval (different task_id or corrupted hil_history). L2 defense
(validate_before_invoke) must block the unapproved call.

**Assertions:**

1. Approved invoke_capability executes (L2 check passes: hil_history has approval)
2. Unapproved invoke_capability is blocked (L2 check fails: no approval in history)
3. Blocked call returns ToolResult(status="blocked")
4. hitl.blocked_red event emitted (if RED band)
5. No side effects from blocked call

**Files:** `tests/poc/test_m12_chaos_hitl.py` (add test)

**Acceptance:**

- L2 defense blocks unapproved execution
- Approved execution proceeds
- No bypass under concurrency

---

#### 12.3.5 -- Test: crash mid-HITL with full ledger recovery

**Problem:** Process crashes after HITL suspension is written to ledger but
before the user responds. On restart, the ledger contains task.suspended
with full react_history. Recovery must rebuild HITL state and re-present
the question to the user.

**Scenario:**

```
T=0:     Task T1 dispatched. Back runs 3 iterations.
T=1000ms: Back calls submit_result(needs_human). Loop exits.
T=1001ms: FSM receives task.suspended. Ledger writes task.suspended event
          with react_history = [3 iterations of messages].
T=1002ms: Front invoked in HITL_RELAY mode. User sees question.
T=1500ms: PROCESS CRASH.
-- restart --
T=0:     CrashRecoveryOrchestrator.recover() called.
T=1ms:   Ledger replayed. project_suspension_state() rebuilds _active with
         SuspensionRequest including react_history.
T=2ms:   project_hitl_state() rebuilds _pending_requests with HILRequest.
T=3ms:   Timeout watcher restarted with remaining time.
T=4ms:   _surface_deferred_hitl() fires. Front in HITL_RELAY re-asks question.
T=5000ms: User responds.
T=5001ms: HITL_RESOLVE processes. Back resume dispatched.
T=5002ms: Back starts NEW react_loop with prior_messages from ledger-recovered
          react_history. Remaining budget = max(2, original - 3).
```

**Assertions:**

1. After crash recovery, _pending_requests contains T1's HILRequest
2. _hil_counts correctly shows the round count from before crash
3. react_history has 3 iterations of messages
4. Timeout watcher restarts with remaining time
5. User sees the question again
6. Back resumes with full prior_messages (not empty)
7. Back budget = max(2, original_budget - 3)
8. No repeated tool calls (prior_messages carry the 3 iterations)

**Files:** `tests/poc/test_m12_chaos_hitl.py` (add test)

**Acceptance:**

- Full HITL recovery after crash
- Back resumes with complete react_history
- No repeated tool executions

---

#### 12.3.6 -- Test: crash mid-HITL with partial ledger

**Problem:** Process crashes during ledger.append(task.suspended). The
entry is truncated/corrupt. On restart, the ledger reader must handle
the corrupt entry gracefully.

**Assertions:**

1. Ledger reader detects corrupt entry (truncated JSON, missing fields)
2. Corrupt entry is skipped with warning log
3. Recovery continues with remaining valid entries
4. If the corrupt entry was the only HITL event, recovery falls back to
   degraded mode (no HITL state rebuilt, task orphaned)
5. k1.ledger.recovery.failed.v1 event emitted with error details
6. No crash on corrupt ledger read

**Files:** `tests/poc/test_m12_chaos_hitl.py` (add test)

**Acceptance:**

- Corrupt ledger entry handled gracefully
- Recovery proceeds with remaining events
- No crash

---

### E12.4 -- Weave Burst & Emotional Gate Tests

Source: WB 8.8, 3.D, 12.5.5

**Rationale:** Weave delivery under burst task completions tests the adaptive
policy's ability to batch, digest, and gate results correctly. The emotional
gate must suppress non-urgent results during negative affect without losing
them. User typing during weave must pause delivery.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.4.1 | Test: 5 task completions in 500ms with adaptive weave batching | WB 8.8 | Validates batch accumulation |
| 12.4.2 | Test: urgent result overrides emotional gate during negative valence | WB 3.D | Validates urgency override |
| 12.4.3 | Test: user typing pauses weave delivery timer | WB 3.D | Validates typing suppression |
| 12.4.4 | Test: weave does not derail active conversation (user input during WEAVING) | WB 8.8 | Validates FrontLock priority |
| 12.4.5 | Test: DIGEST mode correctly compresses 5+ low-urgency results | WB 3.D | Validates digest synthesis |

---

#### 12.4.1 -- Test: 5 task completions in 500ms burst

**Problem:** 5 tasks complete within 500ms. The weave policy should batch
them rather than delivering 5 separate weave messages.

**Scenario:**

```
T=0:     COMPANIONING, Front idle, user idle 10s.
T=0ms:   Task T1 completes. WeavePolicy evaluates. BATCH(500ms) because user idle.
T=100ms: Task T2 completes. Accumulates in pending_results. Timer already running.
T=200ms: Task T3 completes. Accumulates.
T=300ms: Task T4 completes. Accumulates.
T=400ms: Task T5 completes. Accumulates.
T=500ms: Timer fires. _flush_weave_now drains all 5 results.
T=501ms: Front invoked in WEAVE mode with 5 [ASYNC RESULT ARRIVED] blocks.
```

**Assertions:**

1. Only ONE Front WEAVE invocation (not 5 separate ones)
2. All 5 results present in the weave envelope payload
3. Results ordered by urgency then domain
4. M11 metric: weave.batch_size = 5
5. M11 metric: weave.decision_count{BATCH} = 1 (not 5)

**Files:** New: `tests/poc/test_m12_chaos_weave.py`

**Acceptance:**

- Single weave delivery for burst
- All results included
- Correct ordering

---

#### 12.4.2 -- Test: urgent result overrides emotional gate

**Problem:** User is in negative affect (grief). Emotional gate suppresses
non-urgent weave delivery. But a CRISIS-urgent result (e.g., safety alert)
arrives. The urgent result must break through the gate.

**Assertions:**

1. Non-urgent results are DEFERred (emotional gate active)
2. CRISIS-urgent result classified as IMMEDIATE despite emotional gate
3. Front invoked in WEAVE mode with urgency_label = "URGENT"
4. Non-urgent results remain deferred
5. M11 metric: weave.emotional_gate_count incremented for non-urgent
6. M11 metric: urgency_override = True for urgent delivery

**Files:** `tests/poc/test_m12_chaos_weave.py` (add test)

**Acceptance:**

- Urgent overrides emotional gate
- Non-urgent correctly suppressed
- Metrics reflect both paths

---

#### 12.4.3 -- Test: user typing pauses weave delivery

**Problem:** Weave timer is running (BATCH 500ms). At T=300ms, user starts
typing. Timer should pause. When user stops typing + 500ms debounce, timer
resumes with remaining 200ms.

**Assertions:**

1. Timer pauses on typing_start signal
2. Timer resumes on typing_stop + debounce
3. Weave delivery happens at T = 300 + typing_duration + 500ms_debounce + 200ms_remaining
4. No weave delivered while user is typing
5. If user sends a message instead of stopping typing, deferred results
   injected into STANDARD mode response

**Files:** `tests/poc/test_m12_chaos_weave.py` (add test)

**Acceptance:**

- Timer correctly paused and resumed
- No delivery during typing
- Deferred injection on user message

---

#### 12.4.4 -- Test: weave does not derail active conversation

**Problem:** User sends a message while FSM is in WEAVING state. FrontLock
must prioritize user input (P1) over weave delivery (P3). The user's message
should be processed, and the weave results should be deferred or injected
into the next response.

**Assertions:**

1. User input queued in FrontLock at P1 (URGENT)
2. Current weave Front invocation completes (not interrupted)
3. User input processed as next Front invocation
4. Any remaining weave results deferred to next turn or injected as async_results_context
5. FSM transitions cleanly: WEAVING -> LISTENING -> DISPATCHING

**Files:** `tests/poc/test_m12_chaos_weave.py` (add test)

**Acceptance:**

- User input takes priority
- No derailed conversation
- Clean FSM transitions

---

#### 12.4.5 -- Test: DIGEST mode compresses results

**Problem:** 5 low-urgency results arrive with 15s digest window. The
system should group them by domain, generate a template summary, and
deliver as a single condensed payload.

**Assertions:**

1. Digest timer fires after 15s
2. Results grouped by domain (e.g., travel: 2, health: 1, shopping: 2)
3. DigestPayload contains 1-2 sentence summary per group
4. Front receives condensed payload, not 5 raw result blocks
5. M11 metric: weave.digest_compression_ratio < 0.5 (at least 50% compression)

**Files:** `tests/poc/test_m12_chaos_weave.py` (add test)

**Acceptance:**

- Digest correctly groups and compresses
- Front receives condensed payload
- Compression ratio measured

---

### E12.5 -- Ledger Replay & State Determinism Tests

Source: WB 9, 12.2.D

**Rationale:** The ledger is the single source of truth after M9. Replay
must produce identical state regardless of timing, ordering of concurrent
events within the same millisecond, or intermediate failures. These tests
validate the determinism guarantee that makes crash recovery reliable.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.5.1 | Test: ledger replay reconstructs full session state | WB 9 | Validates complete reconstruction |
| 12.5.2 | Test: ledger replay is deterministic (same input = same output) | WB 9 | Validates no non-determinism |
| 12.5.3 | Test: ledger replay with out-of-order events (within same ms) | WB 9 | Validates ordering resilience |
| 12.5.4 | Test: FSM state derivation from ledger events on recovery | WB 9 | Validates state derivation |
| 12.5.5 | Test: crash recovery end-to-end -- kill, restart, continue conversation | WB 9.6 | Validates user-facing recovery |

---

#### 12.5.1 -- Test: ledger replay reconstructs full session state

**Problem:** After a 20-turn session with 5 tasks, 2 HITL rounds, 3 weave
deliveries, and 1 cancel, replaying the ledger must reconstruct all protocol
state identically to the runtime state before the "crash."

**Scenario:**

```
1. Run a scripted 20-turn session (deterministic mock LLM).
2. After turn 20, snapshot ALL runtime state:
   - CancellationHandler._tokens, _cancelled_tasks
   - SuspensionManager._active, _suspension_counts
   - HILCoordinator._pending_requests, _hil_counts
   - TaskBridge._task_state (all task entries)
   - controller._history (all history entries)
   - FSMTurnState.pending_results
3. Read all ledger events.
4. Replay from empty state using CrashRecoveryOrchestrator.
5. Compare reconstructed state to runtime snapshot.
```

**Assertions:**

1. project_cancel_state == runtime CancellationHandler state
2. project_suspension_state == runtime SuspensionManager state
3. project_hitl_state == runtime HILCoordinator state
4. project_task_states == runtime TaskBridge._task_state
5. project_history == runtime controller._history
6. project_pending_results == runtime FSMTurnState.pending_results
7. Derived FSM state == runtime FSM state

**Files:** New: `tests/poc/test_m12_chaos_ledger.py`

**Acceptance:**

- All 7 state comparisons pass
- Test uses a scripted 20-turn session with realistic complexity

---

#### 12.5.2 -- Test: ledger replay is deterministic

**Problem:** Replaying the same ledger twice must produce byte-identical state.
Non-determinism sources: dict iteration order, set ordering, float precision,
timestamp resolution.

**Assertions:**

1. Replay 1 state == Replay 2 state (deep equality check)
2. No random UUIDs generated during replay (all IDs come from ledger events)
3. dict keys are sorted in serialization for comparison
4. Float values use fixed precision

**Files:** `tests/poc/test_m12_chaos_ledger.py` (add test)

**Acceptance:**

- Two replays produce identical state
- No sources of non-determinism

---

#### 12.5.3 -- Test: ledger replay with out-of-order events

**Problem:** Two events in the same millisecond (e.g., task.cancelled and
task.completed for different task_ids at timestamp T=500ms). Ledger stores
both with same timestamp. Replay must produce consistent state regardless
of which event is processed first.

**Assertions:**

1. Replay with event A first, then B -> state S1
2. Replay with event B first, then A -> state S2
3. S1 == S2 (order-independent for events at same timestamp targeting different task_ids)
4. For events targeting SAME task_id at same timestamp: ledger sequence number is the tiebreaker

**Files:** `tests/poc/test_m12_chaos_ledger.py` (add test)

**Acceptance:**

- Out-of-order resilience for independent events
- Sequence number tiebreaker for conflicting events

---

#### 12.5.4 -- Test: FSM state derivation from ledger on recovery

**Problem:** M9 issue 9.5.3 defines a decision table for deriving FSM
state from the latest ledger events. Each row must be tested.

**Test cases:**

| # | Last Events | Expected FSM State |
|---|------------|-------------------|
| 1 | task.suspended (no task.resumed) | CLARIFYING_WORKER |
| 2 | pending_results non-empty + response.final processed | WEAVING (schedule flush) |
| 3 | task.created (no task.completed/failed/cancelled) | COMPANIONING |
| 4 | user.input (no response.final after it) | DISPATCHING |
| 5 | Empty ledger / only response.final | LISTENING |
| 6 | task.cancelled + response.final | LISTENING |

**Assertions:**

- Each test case produces the expected FSM state
- Derived state matches what the runtime FSM would be in

**Files:** `tests/poc/test_m12_chaos_ledger.py` (add test)

**Acceptance:**

- All 6 derivation cases pass
- Derived state matches runtime behavior

---

#### 12.5.5 -- Test: crash recovery end-to-end

**Problem:** The full user-facing recovery flow: mid-conversation crash,
restart with ledger replay, user continues conversation seamlessly.

**Scenario:**

```
Phase 1 -- Normal conversation:
  Turn 1: User asks "plan a family dinner". Phase 1 classifies. Front dispatches task.
  Turn 2: Back processes. Calls discover_capabilities, invoke_capability.
  Turn 3: Back suspends for HITL approval (restaurant booking).
  Turn 4: User approves.
  Turn 5: Back resumes. Calls invoke_capability (booking confirmed).

Phase 2 -- Crash:
  Turn 6: New user input arrives. FSM receives it.
  CRASH (process killed).

Phase 3 -- Recovery:
  Restart. Ledger replayed. State rebuilt.
  Turn 6 (re-processed): User input delivered to Front.
  Turn 7: User says "what happened to my dinner reservation?"
  Front LLM sees full conversation history (turns 1-6).
  Front responds with complete context (booking confirmed, dinner planned).
```

**Assertions:**

1. After recovery, conversation history has turns 1-6
2. Task T1 status is "completed" (from before crash)
3. HITL approval history preserved (L2 defense check would pass)
4. Front's prompt includes the full conversation
5. User does not need to repeat any information
6. No duplicate tool executions

**Files:** `tests/poc/test_m12_chaos_ledger.py` (add test)

**Acceptance:**

- Seamless user experience after crash
- Complete conversation continuity
- No data loss

---

### E12.6 -- BackPool & Dependency Ordering Tests

Source: WB 3.C, 8.4, 10

**Rationale:** BackPool concurrency introduces new failure modes: pool
exhaustion, lease expiry during active work, dependency cycles, and worker
starvation. These tests validate the pool under adversarial conditions.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.6.1 | Test: pool exhaustion with graceful overflow queuing | WB 3.C | Validates no task loss |
| 12.6.2 | Test: lease expiry during active react_loop (cooperative then hard kill) | WB 10 | Validates cleanup |
| 12.6.3 | Test: dependency chain completion ordering | WB 3.C | Validates dependency wait |
| 12.6.4 | Test: circular dependency detection and fail-both | WB 3.C | Validates deadlock prevention |
| 12.6.5 | Test: predecessor failure cascading to dependent tasks | WB 3.C | Validates dependency failure |

---

#### 12.6.1 -- Test: pool exhaustion with overflow queuing

**Problem:** Pool size = 3. Front dispatches 5 tasks. First 3 acquire
workers. Tasks 4 and 5 must queue. When a worker is released, the
next queued task acquires it.

**Assertions:**

1. Tasks 1-3 acquire workers immediately
2. Tasks 4-5 enter overflow queue
3. When task 1 completes, task 4 acquires the released worker
4. When task 2 completes, task 5 acquires the released worker
5. No task lost. All 5 complete.
6. M11 metric: backpool.ready_queue_depth peaks at 2

**Files:** New: `tests/poc/test_m12_chaos_backpool.py`

**Acceptance:**

- All 5 tasks complete
- Queue depth correctly tracked
- Worker recycling works

---

#### 12.6.2 -- Test: lease expiry during active react_loop

**Problem:** Task's lease expires while model.generate() is blocking.
The lease expiry watcher cancels the CancellationToken (cooperative).
After grace period, hard-kills the asyncio.Task.

**Scenario:**

```
T=0:      Task dispatched. Lease TTL = 5s (shortened for test).
T=0.5s:   react_loop starts. Iteration 1 LLM call.
T=5s:     Lease expires. token.cancel() called.
T=5.001s: react_loop between iterations: cancel check -> exit.
          OR: LLM call still blocking (slow model).
T=10s:    Grace period (5s) exceeded. asyncio.Task.cancel() (hard kill).
```

**Assertions:**

1. Cooperative cancel attempted first (token.cancel)
2. If loop exits within grace period: clean exit, ReactResult(status="cancelled")
3. If loop does not exit within grace period: hard kill (CancelledError)
4. Worker slot released after either path
5. task.failed(reason="lease_expired") emitted
6. No orphan HTTP connections (model.generate cleanup)

**Files:** `tests/poc/test_m12_chaos_backpool.py` (add test)

**Acceptance:**

- Cooperative then hard kill sequence works
- Worker slot recovered
- No resource leak

---

#### 12.6.3 -- Test: dependency chain ordering

**Problem:** Front dispatches task A (check availability) then task B
(book hotel, depends_on=A). B must not start until A completes.

**Assertions:**

1. Task A acquires worker and starts react_loop
2. Task B enters ready-queue (dependency not satisfied)
3. Task A completes. ReadyQueue.notify_completed(A) fires.
4. Task B dequeued and acquires worker
5. Task B's SS snapshot includes A's completed artifacts
6. No out-of-order execution

**Files:** `tests/poc/test_m12_chaos_backpool.py` (add test)

**Acceptance:**

- Dependency ordering enforced
- B starts after A completes
- B sees A's results

---

#### 12.6.4 -- Test: circular dependency detection

**Problem:** Front dispatches task A (depends_on=B) and task B (depends_on=A).
Both enter ready-queue. Neither dependency can be satisfied. System must
detect the cycle and fail both tasks.

**Assertions:**

1. Cycle detected during enqueue
2. Both tasks failed with reason="circular_dependency"
3. task.failed events emitted for both
4. No deadlock (tasks do not wait forever)
5. Worker slots never acquired (tasks fail before dispatch)

**Files:** `tests/poc/test_m12_chaos_backpool.py` (add test)

**Acceptance:**

- Cycle detected immediately
- Both tasks failed cleanly
- No resource waste

---

#### 12.6.5 -- Test: predecessor failure cascades

**Problem:** Task A fails. Task B depends_on A. When A fails, B should
also fail with reason="dependency_failed".

**Assertions:**

1. Task A fails (react_loop returns status="failed")
2. ReadyQueue.notify_completed(A) fires (with failed status)
3. Task B checks predecessor status: FAILED
4. Task B failed immediately with reason="dependency_failed"
5. No react_loop started for task B (no wasted LLM tokens)

**Files:** `tests/poc/test_m12_chaos_backpool.py` (add test)

**Acceptance:**

- Failed predecessor cascades to dependents
- No LLM invocation for dependent task
- Clean failure chain

---

### E12.7 -- Infrastructure Stress Tests

Source: WB 12.5.5, 10

**Rationale:** The infrastructure layer (bus, SS, UltraBERT) must handle
stress conditions gracefully: burst bus events, SS at capacity, UltraBERT
failure during active session, concurrent SS mutations.

| # | Issue | Source | LLM Impact |
|---|-------|--------|------------|
| 12.7.1 | Test: bus burst (100 events in 10ms) with no message loss | WB 12.5.5 | Validates bus capacity |
| 12.7.2 | Test: SS at 95% capacity with concurrent cognitive tool writes | WB 12.5.5 | Validates mutation guard |
| 12.7.3 | Test: UltraBERT failure mid-session with graceful degradation | WB 10 | Validates fallback |
| 12.7.4 | Test: concurrent SS mutations from tools do not corrupt state | WB 12.5.5 | Validates section isolation |

---

#### 12.7.1 -- Test: bus burst with no message loss

**Problem:** 100 events published in 10ms. All STRICT events must be
delivered in order. All RELAXED events must be delivered (best-effort).

**Assertions:**

1. All 100 events published successfully
2. STRICT events delivered in publish order
3. No subscriber error (no exception from handler overload)
4. Bus delivery latency p95 < 50ms (even under burst)
5. No dropped messages

**Files:** New: `tests/poc/test_m12_chaos_infra.py`

**Acceptance:**

- Zero message loss under burst
- Ordering preserved for STRICT

---

#### 12.7.2 -- Test: SS at capacity with concurrent tool writes

**Problem:** beliefs_active is at 7.5KB (93% of 8KB budget). Two
cognitive tools (update_beliefs and promote_belief) write simultaneously.
MutationGuard must allow one and reject the other (capacity limit).

**Assertions:**

1. First mutation passes (within budget)
2. Second mutation rejected by MutationGuard (would exceed budget)
3. SizeTracker correctly reflects post-first-mutation size
4. No data corruption (section is internally consistent)
5. Rejected mutation returns MutationResponse with reason="capacity_exceeded"

**Files:** `tests/poc/test_m12_chaos_infra.py` (add test)

**Acceptance:**

- Concurrent writes handled without corruption
- Capacity enforcement works under concurrency

---

#### 12.7.3 -- Test: UltraBERT failure mid-session

**Problem:** UltraBERT works for turns 1-5. At turn 6, UltraBERT raises
(GPU OOM, model crash, etc.). Phase 1 must fall back to stub classifier.

**Assertions:**

1. Turns 1-5 use real UltraBERT classification
2. Turn 6: UltraBERT raises. Stub pipeline used. Warning logged.
3. k1.phase1.degraded.v1 event emitted
4. Front still receives a valid Phase1Result (from stub)
5. System continues functioning (degraded but not crashed)
6. Turn 7: if UltraBERT recovers, real classification resumes

**Files:** `tests/poc/test_m12_chaos_infra.py` (add test)

**Acceptance:**

- Graceful degradation on UltraBERT failure
- No session crash
- Recovery when UltraBERT becomes available again

---

#### 12.7.4 -- Test: concurrent SS mutations do not corrupt state

**Problem:** Two asyncio tasks write to the same SS section simultaneously
(e.g., Front's update_beliefs and FSM's task_bridge.complete_task both
running). SS section internals must be safe under concurrent access.

**Assertions:**

1. Both mutations complete without exception
2. Section state is internally consistent (no partial writes visible)
3. SizeTracker reflects both mutations
4. No data loss (both mutations applied, or one rejected by guard)

**Files:** `tests/poc/test_m12_chaos_infra.py` (add test)

**Acceptance:**

- No corruption under concurrent writes
- Internal consistency maintained

---

### M12 Implementation Order

1. **12.1.1** (cancel cooperative exit -- most fundamental race)
2. **12.1.2** (late completion dead-letter -- depends on cancel)
3. **12.1.3** (cancel mid-LLM-call -- latency validation)
4. **12.1.4** (double cancel idempotency)
5. **12.1.5** (cancel non-existent task)
6. **12.2.1** (interrupt storm -- tests Arbiter + FrontLock under load)
7. **12.2.2** (multi-device conflicts)
8. **12.2.3** (multi-device HITL race)
9. **12.2.4** (high-impact confirmation)
10. **12.3.1** (HITL timeout wins race)
11. **12.3.2** (HITL response wins race)
12. **12.3.3** (HITL no deadlock)
13. **12.3.4** (HITL approval bypass)
14. **12.3.5** (crash mid-HITL full recovery)
15. **12.3.6** (crash with partial ledger)
16. **12.4.1** (weave burst batching)
17. **12.4.2** (urgent overrides emotional gate)
18. **12.4.3** (typing pauses weave)
19. **12.4.4** (weave does not derail conversation)
20. **12.4.5** (DIGEST mode compression)
21. **12.5.1** (ledger replay full state reconstruction)
22. **12.5.2** (replay determinism)
23. **12.5.3** (replay with out-of-order events)
24. **12.5.4** (FSM state derivation)
25. **12.5.5** (crash recovery end-to-end)
26. **12.6.1** (pool exhaustion overflow)
27. **12.6.2** (lease expiry cooperative+hard)
28. **12.6.3** (dependency chain ordering)
29. **12.6.4** (circular dependency detection)
30. **12.6.5** (predecessor failure cascade)
31. **12.7.1** (bus burst no message loss)
32. **12.7.2** (SS at capacity concurrent writes)
33. **12.7.3** (UltraBERT failure mid-session)
34. **12.7.4** (concurrent SS mutations)

**Total: 34 issues across 7 epics.**

---

## Milestone Dependency Graph

```
M0 (V2 Stabilization)
 |
 v
M1 (Event Schemas + Ledger) ------+
 |                                 |
 v                                 v
M2 (FSM Hardening)           M3 (Actor/React Fixes)
 |                                 |
 v                                 v
M4 (SessionState Alignment)  M5 (Conversation Arbiter)
 |                                 |
 +----------+----------+          |
            |                      |
            v                      v
      M6 (HITL Sub-Task)    M7 (BackPool + Lease)
            |                      |
            v                      v
      M8 (Adaptive Weave)   M9 (Protocol -> Ledger)
            |                      |
            +----------+-----------+
                       |
                       v
              M10 (UltraBERT Tier)
                       |
                       v
              M11 (Observability)
                       |
                       v
              M12 (Chaos Validation)
```

Note: M2/M3 and M5/M7 can run in parallel within their tiers.

---

## Open Questions (to resolve during POC exploration)

Carried from WB 10:

- BackPool sizing and lease expiry defaults (feeds M7)
- Adaptive weave threshold tuning signals and weights (feeds M8)
- Cross-session family context boundaries and escalation rules (feeds M5)
- Memory retrieval SLOs for real-time conversational continuity (feeds M10)
- Failure strategy for IoT/event floods and degraded mode behavior (feeds M12)

---

## How to Use This Document

1. **Explore POC** -- walk the code for each milestone's scope, confirm/refine
   issue descriptions.
2. **Feed issues** -- after exploration, add acceptance criteria, file size
   estimates, and dependencies to each issue row.
3. **Sequence sprints** -- use the dependency graph to parallelize where
   possible and gate where required.
4. **Track progress** -- update status markers as work completes.
