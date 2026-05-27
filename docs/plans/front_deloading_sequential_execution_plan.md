# Front Deloading Sequential Execution Plan

Date: 2026-05-24

Source whiteboard: `whiteboard_front_deloading.md`

Status: working execution plan built sequentially from the whiteboard and codebase reality.

## Process Contract

This plan is built in ordered passes.

```text
1. Create the skeleton milestone map first.
2. Define each milestone's epic and issue headings with only the core concept.
3. Expand milestones sequentially.
4. Before expanding a milestone, run a read-only code exploration pass for that milestone.
5. When starting M(n), read the already-written M0..M(n-1) sections so the plan remains coherent end to end.
6. Do not expand later milestones from assumptions that earlier code-grounded milestones have not established.
7. Do not remove Front cognitive tools until classifier active-mode gates prove the replacement path.
```

## Skeleton Milestone Map

### M0 Detailed Plan: Baseline Evidence And Rollback Contract

Epic: freeze the current POC evidence, live measurement evidence, runtime anchors, and rollback flags before implementation.

Issue headings:

```text
M0.I1 Freeze current Front prompt compare baseline.
M0.I2 Freeze SectionUpdateClassifier POC latency and accuracy evidence.
M0.I3 Record current code anchors and ownership boundaries.
M0.I4 Define feature flags and rollback shape.
M0.I5 Preserve test discipline and targeted validation commands.
```

### M1: Typed Classifier Contract And Compiler Boundary

Epic: define the `SectionUpdateClassifier` package, schema, operation vocabulary, idempotency model, and compiler-to-writer boundary.

Issue headings:

```text
M1.I1 Define SectionUpdateInput, SectionUpdatePlan, SectionMutation, rejected candidates, validation, and overlay types.
M1.I2 Reconcile classifier operation vocabulary with SessionState section apply surfaces and MutationGuard.
M1.I3 Implement whole-plan validation and BatchRequest compiler.
M1.I4 Define idempotency, snapshot freshness, and duplicate retry behavior.
M1.I5 Implement deterministic stub and model adapter contract.
M1.I6 Add schema, compiler, vocabulary, no-op, and idempotency tests.
```

### M2: Turn Lifecycle Wiring And Apply Path

Epic: attach the classifier to the Concierge turn lifecycle without putting it back inside Front ReAct.

Issue headings:

```text
M2.I1 Build SectionUpdateInput from the finalized Front turn.
M2.I2 Add section-update request/completion boundary.
M2.I3 Apply accepted plans through writer_port only.
M2.I4 Coordinate active-mode commit before next Front snapshot.
M2.I5 Resolve MemoryWriter ordering against turn.completed.
M2.I6 Add dispatch-critical overlay/gating for Back snapshot-at-start behavior.
M2.I7 Normalize Live API turn-complete records into the same classifier input contract.
```

### M3: Foundation Quality Proof And Integration Readiness

Epic: prove SectionUpdateClassifier mutation quality with provider-backed corpus gates, freeze what is ready, and publish the integration contract M4 will consume. M3 is the foundation floor, not a separate production active-mode wall before M4.

Issue headings:

```text
M3.I1 Preserve shadow/manifest evidence surfaces.
M3.I2 Prove the staged provider corpus.
M3.I3 Lock classifier prompt/schema/runner guardrails.
M3.I4 Freeze quality evidence and known limitations.
M3.I5 Publish the exact integration contract for KernelService and Concierge.
```

### M4: Kernel Background Updater Integration And Front Deload

Epic: wire the classifier as a per-session background completed-turn updater in KernelService, remove cognitive write tools from Front, and formalize the Front prompt situation-frame contract.

Issue headings:

```text
M4.I1 Specify the per-session worker lifecycle against KernelService P1-P6.
M4.I2 Add the P5.5 worker slot, SessionInstance field, teardown, config, and health contract.
M4.I3 Convert the current Concierge active boundary into background-worker semantics.
M4.I4 Apply accepted plans through writer_port with fail-closed background diagnostics.
M4.I5 Trace temporal, SelfModel, SessionState, spatial, and grounding sources for the situation frame.
M4.I6 Write the formal Front prompt modification contract.
M4.I7 Remove cognitive write tools from Front mode allowlists while preserving rollback schemas.
M4.I8 Rewrite prompt sections and commitment text so Front consumes state instead of writing it.
M4.I9 Preserve cognitive schemas temporarily for rollback/internal comparison.
M4.I10 Implement Iteration 1 prompt seating from the formal contract.
```

### M5: Track Working, Validate, And Prove Rollback

Epic: track the integrated background-updater/no-cognitive-Front path turn by turn, validate it with targeted tests and selected live/dry probes, update stale assumptions, and prove rollback.

Issue headings:

```text
M5.I1 Define the working-tracker dashboard/report from section_update.completed and turn.completed.
M5.I2 Run targeted classifier, kernel wiring, prompt, Front, and rollback tests.
M5.I3 Update old tests that assume cognitive tools are Front-visible tools.
M5.I4 Rerun POC dry and selected live cases against the integrated path.
M5.I5 Prove rollback flags restore the previous Front cognitive tool path.
M5.I6 Record the cutover decision with evidence, waivers, and next risk controls.
```

### M6: Steady-State Cutover And Cleanup

Epic: after M5 proves the integrated path, move the system to steady state: keep the background updater as the default hidden cognitive writer, remove obsolete Front cognitive surfaces only after rollback/stability criteria, and lock the monitoring contract.

Issue headings:

```text
M6.I1 Define the stability window and rollback-removal criteria.
M6.I2 Remove obsolete Front cognitive schema/implementation surfaces only after M6 gates.
M6.I3 Collapse feature flags from migration toggles to steady-state diagnostics/model knobs.
M6.I4 Lock prompt contracts, runbooks, and evidence artifacts.
M6.I5 Keep targeted validation discipline; do not introduce broad-suite requirements.
```

## Detailed Milestones

The detailed sections below are filled sequentially. Each milestone expansion must cite the code surfaces read for that milestone and must not rely on later milestones for correctness.

### M0: Baseline Evidence And Rollback Contract

Epic: freeze baseline evidence, rollback surfaces, and active/shadow gating contracts before any Front deloading implementation starts.

M0 operating picture:

```text
M0 is not an implementation milestone.

It freezes the measuring stick and escape hatches before we move ownership.

current system evidence        classifier POC evidence        rollback surfaces
   |                              |                              |
   v                              v                              v
 prompt compare baseline       latency / accuracy facts       existing Front tools
   |                              |                              |
   +--------------+---------------+---------------+--------------+
             |                               |
             v                               v
       M1-M5 implementation can change       M0 facts do not drift
       only with explicit comparison         silently underneath it
```

M0 drift guard:

```text
Do not add classifier runtime code in M0.
Do not hide or delete Front cognitive tools in M0.
Do not treat the current Gemini 2.5 Flash Lite POC as active-write proof.
Do not broaden validation beyond targeted evidence commands.
```

M0 execution lock:

```text
Started: 2026-05-24

M0 production code edit decision:
   no runtime code edits
   no prompt allowlist edits
   no classifier package creation
   no schema deletion or tool relocation

Exact M0 edit target:
   docs/plans/front_deloading_sequential_execution_plan.md

Reason:
   M0 freezes evidence, rollback surfaces, and code anchors.
   M1-M5 may edit runtime code, but only against this frozen baseline.
```

M0 verified evidence snapshot:

```text
front_prompt_compare live_results.json aggregate:
   records=141
   errors=0
   variants=current=47,iteration1=47,iteration1_no_cognitive=47
   iteration1_no_cognitive cognitive calls=0/47

section_update_classifier live summary:
   records=12
   validation pass rate=16.7%
   batch pass rate=33.3%
   parallel pass rate=0.0%
   active mode blocked
```

M0 code-edit map for later milestones:

```text
M1 owns new classifier contract/compiler code under k1/concierge/section_update/.
M2 owns lifecycle wiring around response.final -> turn.completed coordination.
M3 owns shadow/active quality gates and observability.
M4 owns Front allowlist and prompt text cutover.
M5 owns rollback proof and final validation.

M0 does not pre-edit any of those surfaces.
```

#### M0.I1 Freeze Current Front Prompt Compare Baseline

Core concept: preserve the existing Front prompt comparison evidence so later prompt and tool-surface changes can be judged against a stable baseline.

Issue context:

```text
The future cutover needs a before/after prompt comparison.

current Front prompt variants
   |
   v
front_prompt_compare live run
   |
   v
baseline artifacts
   |
   +--> prompt size comparison
   +--> runtime error count
   +--> cognitive tool-call count
   +--> response behavior notes
   |
   v
M3/M4/M5 compare against this instead of guessing
```

What this prevents:

```text
Without this baseline, later prompt deloading can look successful just because it is shorter.
M0.I1 forces later milestones to compare size, runtime stability, tool exposure, and response behavior together.
```

Code and artifact boundaries:

```text
poc/front_prompt_compare/compare_front_prompts.py
poc/front_prompt_compare/runs/20260521_150501/summary.md
poc/front_prompt_compare/runs/20260521_150501/live_results.json
```

Current measured facts:

```text
47 use cases x 3 variants = 141 live requests
0 runtime errors in the referenced baseline
iteration1_no_cognitive produced 0 cognitive tool calls in that run
current prompt size: roughly 9.3k-9.5k estimated tokens
deloaded prompt size: roughly 4.9k-5.1k estimated tokens
```

Verified JSON aggregate:

```text
records=141
errors=0
no_cognitive_records=47
no_cognitive_cognitive_calls=0
variants=current=47,iteration1=47,iteration1_no_cognitive=47
```

Acceptance:

```text
Baseline run directory is recorded in this plan.
Known response-wording misses are documented as prompt behavior, not classifier failure.
The baseline remains available for M3/M5 comparisons.
The live_results.json aggregate is recorded so summary-table drift is detectable.
```

Targeted validation:

```powershell
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
```

#### M0.I2 Freeze SectionUpdateClassifier Latency And Accuracy Evidence

Core concept: record the live classifier POC evidence before treating any model path as active-write capable.

Issue context:

```text
POC cases
   |
   v
section_update_classifier_poc.py
   |
   +--> dry/schema behavior
   |
   +--> live Vertex gemini-2.5-flash-lite run
       |
       +--> validation pass rate
       +--> model latency
       +--> classifier E2E latency
       +--> batch vs parallel behavior
       |
       v
      active-mode gate decision
```

Current decision from evidence:

```text
16.7% validation pass rate
   |
   v
shadow-only classifier evidence
   |
   v
no active SessionState writes from this model path yet
```

What this prevents:

```text
M0.I2 prevents a future implementation from saying "the classifier exists, so active mode is ready." The measured model path must earn active-write authority through M3 gates.
```

Code and artifact boundaries:

```text
poc/section_update_classifier_poc.py
poc/section_update_classifier_cases.json
poc/section_update_classifier_runs/20260521_163606/summary.md
poc/section_update_classifier_runs/20260524_101604/summary.md
```

Current measured facts from the Vertex `gemini-2.5-flash-lite` run:

```text
records: 12
validation passes: 2
validation failures: 10
validation pass rate: 16.7%

batch:
 pass rate: 33.3% (2/6)
 model mean: 5505 ms
 model median: 4394 ms
 model p95: 8872 ms
 model max: 9080 ms

parallel:
 pass rate: 0.0% (0/6)
 model mean: 6467 ms
 model median: 7128 ms
 model p95: 8214 ms
 model max: 8216 ms
```

Interpretation:

```text
Batch remains the right V0 contract shape because it maps to BatchRequest.
Parallel/by-section provider tool calls remain diagnostic only.
gemini-2.5-flash-lite is shadow-only at current prompt/schema quality.
Active writes are blocked until no-op precision, schema validity, and section/operation precision improve.
4-9 second model latency is acceptable for async/shadow diagnostics, not for same-turn synchronous dispatch-critical paths.
```

Observed active-mode blockers:

```text
no-op precision failure: greeting_noop produced a beliefs_active mutation
schema/tool reliability failure: several cases returned no tool calls
batch vocabulary failure: clarifications.cancel_commitment is not a valid target operation
parallel mode failure: no-op tool was mixed with mutation tools
latency risk: current live model path is too slow for synchronous dispatch-critical use
```

Targeted validation:

```powershell
$env:LLM_PROVIDER='vertex'
$env:GOOGLE_GENAI_USE_VERTEXAI='True'
$env:VERTEX_MODEL='gemini-2.5-flash-lite'
$env:K1_SECTION_UPDATE_MODEL='gemini-2.5-flash-lite'
python .\poc\section_update_classifier_poc.py --live --mode both --preferred-provider vertex --preferred-model gemini-2.5-flash-lite --temperature 0 --timeout-ms 45000 --max-output-tokens 2048
```

#### M0.I3 Record Current Code Anchors And Ownership Boundaries

Core concept: freeze the current Front cognitive tool path and rollback surfaces before replacing ownership.

Issue context:

```text
current write ownership
-----------------------

Front ReAct
   |
   v
cognitive tools visible in prompt
   |
   +--> update_beliefs
   +--> update_scoreboard
   +--> update_clarifications
   +--> update_narrative
   +--> refine_affect
   +--> promote_belief
   |
   v
tool implementations / update_session_bundle
   |
   v
writer_port / SessionState


target ownership after later milestones
--------------------------------------

Front
   |
   +--> answer / clarify / dispatch / read memory
   |
   v
SectionUpdateClassifier
   |
   v
BatchRequest through writer_port
   |
   v
guarded cognitive SessionState sections
```

What this prevents:

```text
M0.I3 keeps rollback real. We preserve current tool schemas, implementations, and allowlist surfaces until M3/M4 prove the classifier can replace them.
```

Code boundaries:

```text
k1/concierge/prompt/mode.py
k1/concierge/prompt/builder.py
k1/concierge/prompt/sections.py
k1/concierge/actors/front.py
k1/concierge/fsm/controller.py
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
k1/sessionstate/config.py
k1/sessionstate/ports/writer.py
k1/sessionstate/adapters/direct_writer.py
k1/sessionstate/guard.py
```

Current ownership boundary:

```text
Front currently owns cognitive writes through prompt-seated tools.
Target owner is SectionUpdateClassifier through writer_port.
control, task_state, task_artifacts, history, telemetry, and meta remain runtime/FSM-owned.
MemoryWriter reads SessionState and writes durable memory outside SessionState.
```

Current code truth:

```text
k1/concierge/prompt/mode.py:
   active modes still seat per-section cognitive tools
   update_session_bundle is not seated in active Front modes

k1/concierge/prompt/builder.py:
   DynamicPromptBuilder._select_tools filters FRONT_TOOL_SCHEMAS by TOOL_ALLOWLIST

k1/concierge/prompt/sections.py:
   current prompt text still instructs Front on cognitive tool discipline

k1/concierge/tools/schemas_front.py:
   FRONT_TOOL_SCHEMAS exports 12 schemas, including 7 cognitive/session-write schemas

k1/concierge/tools/implementations.py:
   execute_update_session_bundle proves MutationRequest -> BatchRequest -> writer_port.batch_mutations mechanics

k1/sessionstate/config.py:
   llm_writable_sections are beliefs_active, scoreboard, clarifications, narrative_active, affective_now

k1/sessionstate/adapters/direct_writer.py:
   batch_mutations applies requests in order and can stop/cancel remaining requests
   it does not provide transactional rollback for already-applied mutations

k1/concierge/fsm/controller.py:
   response.final writes assistant history, then executes the response-final decision
   turn.completed is emitted from finalization and is a MemoryWriter trigger
```

Acceptance:

```text
Current cognitive schemas and implementations are not deleted in M0.
Current Front allowlists are not changed in M0.
The plan records that these surfaces are rollback and comparison surfaces until active classifier gates pass.
```

#### M0.I4 Define Feature Flags And Rollback Shape

Core concept: define the control names before implementation so shadow, active, degraded, and rollback behavior are explicit.

Issue context:

```text
future runtime modes
--------------------

disabled / rollback
   Front cognitive tools visible
   classifier inactive

shadow
   Front path remains authoritative
   classifier produces diagnostics only

active
   Front cognitive tools hidden
   classifier applies through writer_port after gates pass

degraded_noop
   Front cognitive tools hidden or transitional
   classifier emits diagnostics but writes nothing

offline_stub
   deterministic tests without live provider dependency
```

Rollback mental model:

```text
flag flip
   |
   v
restore old Front cognitive tool visibility
   |
   v
no schema resurrection needed
   |
   v
safe rollback path remains available during cutover
```

What this prevents:

```text
M0.I4 prevents a one-way migration. The later implementation must be mode-driven, not a deletion of the current Front write path.
```

Recommended future flags/config keys:

```text
K1_ENABLE_SECTION_UPDATE_CLASSIFIER
K1_SECTION_UPDATE_MODE=shadow|active|offline_stub|degraded_noop
K1_SECTION_UPDATE_MODEL=gemini-2.5-flash-lite
K1_FRONT_DELOAD_COGNITIVE_TOOLS
```

M0 flag semantics lock:

```text
K1_ENABLE_SECTION_UPDATE_CLASSIFIER=false
   classifier is disabled; current Front cognitive tools remain authoritative

K1_SECTION_UPDATE_MODE=shadow
   classifier may run for diagnostics only; Front cognitive writes remain authoritative

K1_SECTION_UPDATE_MODE=active
   classifier may apply only after M3 quality gates pass and M2 ordering is implemented

K1_SECTION_UPDATE_MODE=offline_stub
   deterministic local/test behavior; no live provider dependency

K1_SECTION_UPDATE_MODE=degraded_noop
   classifier emits diagnostics and writes nothing

K1_FRONT_DELOAD_COGNITIVE_TOOLS=false
   rollback/default during M0-M3; cognitive tools remain visible to Front

K1_FRONT_DELOAD_COGNITIVE_TOOLS=true
   allowed only after M4 cutover criteria; cognitive schemas still remain for rollback/internal tests
```

Acceptance:

```text
M0 only defines flag names and behavior.
No config class is required in M0.
Later implementation can roll back to existing Front cognitive tools without schema deletion.
```

#### M0.I5 Preserve Test Discipline And Targeted Validation Commands

Core concept: keep validation narrow and artifact-driven until code changes begin.

Issue context:

```text
M0 validation funnel
--------------------

evidence command from this plan
   |
   v
specific artifact or targeted test
   |
   v
recorded baseline / confidence signal
   |
   v
later milestone uses that signal

not allowed in M0:
   |
   +--> full kernel suite
   +--> full Fabric suite
   +--> unrelated cleanup tests
   +--> broad speculative validation
```

What this prevents:

```text
M0.I5 keeps this plan reproducible. We validate only the evidence and directly relevant rollback surfaces, so failures stay attributable to the deloading work.
```

Targeted commands:

```powershell
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
python .\poc\section_update_classifier_poc.py --live --mode both --preferred-provider vertex --preferred-model gemini-2.5-flash-lite --temperature 0 --timeout-ms 45000 --max-output-tokens 2048
pytest tests/k1/concierge/test_m04_e43_session_bundle.py tests/k1/concierge/test_m04_e44_prompt_ss.py -v
```

M0 validation run:

```text
2026-05-24:
   pytest tests/k1/concierge/test_m04_e43_session_bundle.py tests/k1/concierge/test_m04_e44_prompt_ss.py -v
   result: 87 passed

2026-05-24:
   git diff --check -- docs/plans/front_deloading_sequential_execution_plan.md
   result: no whitespace errors
```

Constraints:

```text
Do not run the full kernel suite.
Do not run the full Fabric suite.
Do not remove or rewrite Front cognitive tools in M0.
```

M0 blockers and contradictions:

```text
Current Gemini 2.5 Flash Lite classifier pass rate is 16.7%, which blocks active-mode use.
Current classifier latency is acceptable for async shadow evaluation but too slow for synchronous same-turn paths.
No section-update config class exists yet; M0 defines the contract but does not implement it.
update_session_bundle schema text says atomic, but DirectWriterAdapter.batch_mutations is ordered/non-transactional; M1 must require whole-plan validation before writer_port.
Front prompt text still teaches cognitive tool use; M4 owns that rewrite, not M0.
```

### M1 Detailed Plan: Typed Classifier Contract And Compiler Boundary

Epic: define a typed `SectionUpdateClassifier` contract that converts post-turn cognitive interpretation into validated `BatchRequest` data, without giving the model tool/runtime authority and without changing the Front rollback surfaces frozen in M0.

M1 operating picture:

```text
M1 builds the contract boundary, not the turn lifecycle.

classifier adapter or stub
   |
   v
SectionUpdatePlan data
   |
   v
typed schema + vocabulary registry + idempotency checks
   |
   v
whole-plan compiler
   |
   v
BatchRequest for writer_port

No Front ReAct loop.
No direct section.apply calls.
No dispatch authority.
No active lifecycle wiring yet.
```

M1 drift guard:

```text
If a change gives the model a runtime tool, it belongs outside M1 and likely violates the design.
If a change writes SessionState directly, it violates M1.
If a change compiles an invalid partial plan, it violates M1.
If a change depends on M2 lifecycle hooks, M1 has leaked into the next milestone.
```

Package decision:

```text
Use k1/concierge/section_update for the classifier package.
The classifier is attached to Concierge turn lifecycle and prompt modes.
It imports SessionState writer contracts, but model adapters do not live inside k1/sessionstate.
SessionState remains the guarded mutation substrate, not the LLM classifier owner.
```

Recommended package layout:

```text
k1/concierge/section_update/__init__.py
k1/concierge/section_update/types.py
k1/concierge/section_update/vocabulary.py
k1/concierge/section_update/plan_compiler.py
k1/concierge/section_update/idempotency.py
k1/concierge/section_update/classifier.py
k1/concierge/section_update/apply.py
k1/concierge/section_update/observability.py
```

#### M1.I1 Define Runtime-Free Contract Types

Core concept: define the data contract before model or lifecycle wiring.

Issue context:

```text
raw classifier/stub output
   |
   v
SectionUpdatePlan shape
   |
   +--> SectionUpdateInput
   +--> SectionMutation
   +--> RejectedCandidate
   +--> TurnStateOverlay
   +--> validation/status enums
   |
   v
pure data that can round-trip without runtime dependencies
```

What this prevents:

```text
M1.I1 prevents the classifier contract from becoming an ad hoc dict shared by prompt code, model code, and writer code.
It also prevents runtime imports from creeping into the schema layer.
```

Code boundaries:

```text
k1/concierge/section_update/types.py
poc/section_update_classifier_poc.py
whiteboard_front_deloading.md SectionUpdateInput / SectionUpdatePlan blocks
```

Types to define:

```text
SectionUpdateInput
SectionUpdatePlan
SectionMutation
RejectedCandidate
TurnStateOverlay
SectionUpdateValidation
ApplyTiming
CommitClass
ClassifierMode
```

Implementation notes:

```text
Types are dataclasses/enums or existing local style equivalent.
Types do not import ModelHub, Front, FSM controller, or writer implementations.
Confidence fields are bounded 0.0..1.0.
No-op is represented only as mutations=[] with validation status.
```

Acceptance:

```text
JSON/dict round-trip works for every contract type.
Malformed confidence, missing section, invalid apply_timing, and mixed no-op/write shapes fail validation.
No runtime side effects occur during type construction.
```

#### M1.I2 Reconcile Operation Vocabulary

Core concept: expose only classifier operations accepted by both `MutationGuard` and the target section `apply(...)` surface.

Issue context:

```text
llm_writable_sections
   |
   v
five cognitive sections only
   |
   +--> beliefs_active.apply(...)
   +--> scoreboard.apply(...)
   +--> clarifications.apply(...)
   +--> narrative_active.apply(...)
   +--> affective_now.apply(...)
   |
   v
intersect with MutationGuard.VALID_OPERATIONS
   |
   v
classifier operation registry
   |
   v
compiler accepts only this vocabulary
```

What this prevents:

```text
M1.I2 prevents the model from inventing operations, targeting runtime-owned sections, or using section.apply operations that the guard would later reject.
```

Code boundaries:

```text
k1/concierge/section_update/vocabulary.py
k1/sessionstate/config.py
k1/sessionstate/guard.py
k1/sessionstate/sections/beliefs_active.py
k1/sessionstate/sections/scoreboard.py
k1/sessionstate/sections/clarifications.py
k1/sessionstate/sections/narrative_active.py
k1/sessionstate/sections/affective_now.py
```

Current vocabulary reality:

| Section | V0 active classifier ops | Current guard/apply mismatch |
| --- | --- | --- |
| `beliefs_active` | `add_fact`, `update_confidence` | `pin_fact` / `unpin_fact` exist in `apply()` but fail `VALID_OPERATIONS`; keep out of V0 unless reconciled. |
| `scoreboard` | `add_referent`, `push_question`, `pop_question`, `push_topic`, `add_commitment`, `fulfill_commitment`, `cancel_commitment` | `answer_question`, `set_salience`, `set_user_intent` exist in `apply()` but fail `VALID_OPERATIONS`. |
| `clarifications` | `request`, `answer` | `cancel`, `expire`, `expire_old`, `set_blocking`, `clear_blocking`, `update_priority` exist in `apply()` but fail `VALID_OPERATIONS`. |
| `narrative_active` | `create_thread`, `switch_to`, `pause_thread`, `resolve_thread`, `archive_thread`, `update_thread` | `record_turn` is guard/apply-compatible but runtime-owned by turn recording; keep out of model-visible V0. Still reject shorthand `switch`, `resume`, `close`. |
| `affective_now` | `update` | `update_emotion`, `update_dimensions`, `set_empathy_needed`, `set_celebration_appropriate` exist in `apply()` but fail `VALID_OPERATIONS`. |

Acceptance:

```text
Vocabulary registry is derived from the five LLM-writable sections only.
Compiler rejects every non-LLM-writable SessionState section, including `control`, `temporal`, `spatial`, `grounding`, `task_state`, `task_artifacts`, `history_active`, `telemetry`, `meta`, `place_registry`, `persona`, and warm/archive sections.
Every accepted operation is proven compatible with both guard preflight and section apply path.
Rejected operations include section, operation, and reason.
```

#### M1.I3 Implement Whole-Plan Validation And BatchRequest Compiler

Core concept: convert only validated plans into `MutationRequest` / `BatchRequest`; never write directly.

Issue context:

```text
SectionUpdatePlan
   |
   v
whole-plan preflight
   |
   +--> section allowed?
   +--> operation allowed?
   +--> payload valid?
   +--> snapshot fresh?
   +--> bytes estimated?
   +--> dependencies safe?
   |
   v
if all valid: BatchRequest
if any required mutation invalid: rejected plan / no writer call
```

What this prevents:

```text
M1.I3 prevents partial dependent writes, direct section mutation, and compiler behavior that relies on DirectWriterAdapter catching errors too late.
```

Code boundaries:

```text
k1/concierge/section_update/plan_compiler.py
k1/sessionstate/ports/writer.py
k1/sessionstate/adapters/direct_writer.py
k1/concierge/tools/implementations.py execute_update_session_bundle
```

Implementation notes:

```text
Use writer_id="tool:section_update_classifier" or a nearby convention that passes existing tool writer auth.
Mirror the existing update_session_bundle path only for runtime mechanics.
Do not expose update_session_bundle as a Front ReAct tool replacement.
Estimate bytes for each mutation; do not use estimated_bytes=0 for growth operations.
Default stop_on_rejection should be true for dependent chains, and false only after whole-plan validation proves independent safe mutations.
```

Acceptance:

```text
Invalid section, invalid operation, malformed payload, stale snapshot, and forbidden target are rejected before writer_port.
Whole-plan preflight runs before any writer call.
Dependent plans are rejected entirely if any required mutation is invalid.
Batch order is stable and deterministic.
Empty mutations[] returns no-op result and does not call writer_port.
```

#### M1.I4 Define Idempotency, Snapshot Freshness, And Duplicate Retry Behavior

Core concept: define exact stale-plan and duplicate-plan behavior before active apply.

Issue context:

```text
classifier plan
   |
   +--> session_id
   +--> turn_id
   +--> snapshot_version / snapshot_epoch
   +--> classifier_version
   |
   v
plan idempotency key
   |
   +--> duplicate? return cached/no-op result
   +--> stale? reject as stale diagnostic
   +--> fresh? eligible for compile/apply
```

What this prevents:

```text
M1.I4 prevents duplicate writes from retries and prevents a slow classifier from mutating state against an old snapshot.
It also forces the current epoch gap to be solved explicitly instead of pretending last_mutation_ms is enough.
```

Code boundaries:

```text
k1/concierge/section_update/idempotency.py
k1/concierge/section_update/plan_compiler.py
k1/concierge/section_update/apply.py
k1/sessionstate/manager.py
k1/sessionstate/ports/writer.py
```

Current code reality:

```text
SessionState currently exposes timing metadata such as last_mutation_ms.
That is not enough as a public, monotonic mutation epoch for stale-plan validation.
M1 must define the epoch contract before M2 can rely on active stale rejection.
```

Contract:

```text
plan_idempotency_key = session_id:turn_id:snapshot_version:classifier_version
mutation_idempotency_key = plan_idempotency_key:index:operation_hash
duplicate invocation for the same key returns cached result and never writes twice
stale snapshot returns no-op diagnostic, no same-turn retry loop
```

Acceptance:

```text
Idempotency keys are stable for identical plans and different for changed plans.
Duplicate compile/apply attempts do not produce duplicate mutations.
Snapshot freshness failure is distinguishable from validation failure and provider failure.
Epoch gap is documented if the code does not yet expose a true mutation epoch.
```

#### M1.I5 Implement Deterministic Stub And Model Adapter Contract

Core concept: provide a testable classifier interface without making live model behavior a prerequisite for compiler tests.

Issue context:

```text
offline_stub adapter              live model adapter
   |                                |
   v                                v
deterministic SectionUpdatePlan    provider SectionUpdatePlan
   |                                |
   +---------------+----------------+
         |
         v
      same compiler path

adapters return plans only; they never write.
```

What this prevents:

```text
M1.I5 prevents live provider quality from blocking contract tests and prevents adapter code from gaining writer, dispatch, or ReAct authority.
```

Code boundaries:

```text
k1/concierge/section_update/classifier.py
k1/concierge/section_update/prompt.py
poc/section_update_classifier_poc.py
```

Implementation notes:

```text
The interface returns SectionUpdatePlan data only.
No ReAct loop.
No runtime tools.
No direct writer access.
No dispatch/capability authority.
Deterministic stub supports fixture-driven tests.
Model failures become safe no-op plus diagnostics.
```

Acceptance:

```text
Stub can emit no-op, valid plan, invalid candidate, and provider-failure shapes.
Live model adapter can be disabled by mode.
M0 Gemini 2.5 Flash Lite evidence keeps live adapter shadow-only until M3 gates pass.
```

#### M1.I6 Add Contract, Vocabulary, Compiler, And Idempotency Tests

Core concept: test the typed contract and compiler boundary before touching Front/FSM lifecycle.

Issue context:

```text
M1 tests form the contract fence.

schema tests
   |
vocabulary tests
   |
compiler tests
   |
idempotency tests
   |
stub tests
   |
   v
M2 may wire lifecycle only after this boundary is trusted
```

What this prevents:

```text
M1.I6 prevents M2 from being built on a classifier contract that only works by accident inside one live provider path.
```

New targeted tests:

```text
tests/k1/concierge/section_update/test_plan_schema.py
tests/k1/concierge/section_update/test_operation_vocabulary.py
tests/k1/concierge/section_update/test_plan_compiler.py
tests/k1/concierge/section_update/test_idempotency.py
tests/k1/concierge/section_update/test_classifier_stub.py
```

Existing targeted checks:

```text
tests/k1/sessionstate/test_guard.py
tests/k1/concierge/test_m04_e43_session_bundle.py
```

Run:

```powershell
pytest tests/k1/concierge/section_update/test_plan_schema.py tests/k1/concierge/section_update/test_operation_vocabulary.py tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py tests/k1/concierge/section_update/test_classifier_stub.py -v
pytest tests/k1/sessionstate/test_guard.py -k "valid_operations or invalid_operation" -v
pytest tests/k1/concierge/test_m04_e43_session_bundle.py -v
```

M1 implementation status, 2026-05-25:

```text
Status: M1.I1 through M1.I6 implemented and validated.
Scope held: no Front prompt edits, no ReAct tool removal, no lifecycle/FSM wiring, no writer implementation edits.

Added production package:
   k1/concierge/section_update/__init__.py
   k1/concierge/section_update/types.py
   k1/concierge/section_update/vocabulary.py
   k1/concierge/section_update/idempotency.py
   k1/concierge/section_update/plan_compiler.py
   k1/concierge/section_update/classifier.py
   k1/concierge/section_update/prompt.py

Added focused tests:
   tests/k1/concierge/section_update/test_plan_schema.py
   tests/k1/concierge/section_update/test_operation_vocabulary.py
   tests/k1/concierge/section_update/test_plan_compiler.py
   tests/k1/concierge/section_update/test_idempotency.py
   tests/k1/concierge/section_update/test_classifier_stub.py

Code-truth correction found during regression:
   SessionState now has 19 budgeted sections, but Concierge config still had a 10-section system_owned_sections override from the older 15-section era.
   Updated k1/concierge/config/loader.py and k1/concierge/config/defaults.yaml so all 14 non-LLM-writable sections are explicit system-owned sections.
   Updated tests/k1/concierge/test_m04_e42_write_path.py to assert 14 system-owned sections and no coverage gaps.
   Updated classifier FORBIDDEN_SECTIONS so every non-writable current SessionState section is forbidden to the classifier.

Validation run:
   python -m py_compile k1/concierge/section_update/*.py: pass
   get_errors on touched M1/config/test files: no errors
   pytest tests/k1/concierge/section_update/test_plan_schema.py tests/k1/concierge/section_update/test_operation_vocabulary.py tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py tests/k1/concierge/section_update/test_classifier_stub.py -v: 34 passed
   pytest tests/k1/sessionstate/test_guard.py -k "valid_operations or invalid_operation" -v: 33 passed, 79 deselected
   pytest tests/k1/concierge/test_m04_e43_session_bundle.py tests/k1/concierge/test_m04_e42_write_path.py tests/k1/sessionstate/test_ports.py::TestBatchRequest -v: 55 passed
   pytest tests/k1/sessionstate/test_public_types_057.py::TestNoDeepSSImports::test_no_deep_imports_in_production -v: 1 passed

Residual blocker carried forward:
   No public monotonic SessionState mutation epoch exists yet; M1 can reject known stale snapshot_version/source_epoch values supplied by lifecycle, but M2/M3 must solve the active epoch source before relying on robust stale-plan rejection.
```

M1 blockers and risks:

```text
No public monotonic SessionState mutation epoch currently exists for robust stale-plan rejection.
Current update_session_bundle uses estimated_bytes=0 patterns; classifier compiler must not inherit that for growth writes.
BatchRequest is ordered but not transactional; whole-plan validation is mandatory.
Current Gemini 2.5 Flash Lite quality is too low for active mode, so live adapter cannot be the proof of M1 correctness.
```

### M2 Detailed Plan: Turn Lifecycle Wiring And Apply Path

Epic: wire `SectionUpdateClassifier` into the Concierge turn boundary as the post-Front owner of cognitive SessionState writes, using the M1 typed plan/compiler boundary and the existing `IWriterPort` batch path, while preserving current Front cognitive tools until M3/M4 gates prove continuity.

M2 operating picture:

```text
M2 connects the M1 contract to the turn clock.

Front completes turn
   |
   v
SectionUpdateInput builder
   |
   v
classifier lifecycle boundary
   |
   +--> shadow: diagnostics only, after turn.completed
   |
   +--> active: compile/apply/degrade before turn.completed
   |
   v
writer_port only when active plan is valid
   |
   v
turn.completed / MemoryWriter / FrontLock / Back ordering
```

M2 drift guard:

```text
Do not put the classifier back inside Front ReAct.
Do not let shadow mode mutate SessionState.
Do not emit turn.completed before active apply/degrade closes.
Do not let Back start with silently missing dispatch-critical context.
```

M2 lifecycle decision:

```text
Shadow mode observes after turn completion and never blocks response finalization.
Active mode applies accepted plans before turn.completed, before MemoryWriter, and before FrontLock drains.
Both modes publish diagnostics; only active mode can mutate SessionState through writer_port.
```

Recommended M2 additions:

```text
k1/concierge/section_update/input_builder.py
k1/concierge/section_update/lifecycle.py
k1/concierge/section_update/events.py
k1/concierge/section_update/overlay.py
k1/concierge/section_update/live_api.py
```

#### M2.I1 Build SectionUpdateInput From The Finalized Front Turn

Core concept: capture the completed user/Front turn into M1 `SectionUpdateInput` without changing Front response behavior.

Issue context:

```text
completed Front turn
   |
   +--> current user text
   +--> final assistant text
   +--> tool calls / dispatch specs
   +--> prompt mode
   +--> snapshot metadata
   +--> recent context and open commitments
   |
   v
SectionUpdateInput
```

What this prevents:

```text
M2.I1 prevents the classifier from seeing only one ambiguous user message in multi-turn workflows.
It also prevents input construction from changing Front response text or mutating SessionState.
```

Code boundaries:

```text
k1/concierge/actors/front.py front_handler
k1/concierge/actors/front.py _extract_scenario_data
k1/concierge/section_update/input_builder.py
k1/concierge/section_update/types.py
```

Implementation notes:

```text
Build input after Front has final assistant text, tool calls, dispatch specs, scenario data, prompt mode, and snapshot metadata.
Include user/session/device identifiers, turn id, event timestamp, snapshot source/version, open commitments, history context, and dispatch specs.
Do not mutate SessionState while building input.
Do not let the input builder alter final response text.
Keep prompt/token compression deterministic and separately testable.
```

Acceptance:

```text
Identical Front turn data produces identical SectionUpdateInput.
Input builder works for final-response turns and dispatch turns.
Missing optional scenario fields degrade to empty/default fields, not exceptions.
Front response output remains byte-for-byte unchanged with classifier disabled.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_turn_input_builder.py -v
```

#### M2.I2 Add Section-Update Request And Completion Boundary

Core concept: add explicit lifecycle events so classifier execution is observable and separable from Front ReAct.

Issue context:

```text
turn boundary
   |
   v
section_update.requested
   |
   v
classifier / compiler / apply-or-noop
   |
   v
section_update.completed
   |
   +--> applied
   +--> no-op
   +--> rejected
   +--> stale
   +--> timed-out
   +--> provider-failed
```

What this prevents:

```text
M2.I2 prevents classifier work from becoming an invisible side effect hidden inside Front or writer code.
Every turn gets a lifecycle status that can be observed and tested.
```

Code boundaries:

```text
k1/concierge/bus/topics.py
k1/concierge/bus/builders.py
k1/concierge/section_update/events.py
k1/concierge/section_update/lifecycle.py
```

Implementation notes:

```text
Add section-update requested/completed diagnostics near existing turn.completed conventions.
Request event carries mode, turn id, snapshot version, and idempotency key.
Completion event carries no-op/validated/rejected/applied/timed-out/provider-failed status.
Do not route section-update events through Front tools.
```

Acceptance:

```text
Shadow mode can publish request/completion diagnostics without SessionState mutation.
Active mode publishes completion before turn.completed.
Event payloads do not contain raw prompt secrets or full memory dumps.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_classifier_turn_boundary.py -v
```

#### M2.I3 Apply Accepted Plans Through writer_port Only

Core concept: keep SessionState mutation centralized in the writer adapter and guard path.

Issue context:

```text
validated SectionUpdatePlan
   |
   v
BatchRequest
   |
   v
writer_port.batch_mutations
   |
   v
MutationGuard
   |
   v
DirectWriterAdapter
   |
   v
cognitive SessionState sections
```

What this prevents:

```text
M2.I3 prevents the new classifier path from bypassing the same writer and guard contracts used by existing SessionState mutations.
```

Code boundaries:

```text
k1/concierge/section_update/apply.py
k1/concierge/section_update/plan_compiler.py
k1/sessionstate/ports/writer.py
k1/sessionstate/adapters/direct_writer.py
k1/concierge/tools/implementations.py execute_update_session_bundle
```

Implementation notes:

```text
Lifecycle calls classifier -> compiler -> writer_port.batch_mutations.
No direct section.apply calls outside SessionState writer internals.
Use M1 whole-plan validation before writer call.
Use M1 idempotency key and snapshot freshness status.
Emit mutation summary status compatible with current turn mutation summaries.
```

Acceptance:

```text
No-op and invalid plans do not call writer_port.
Valid active plans call writer_port.batch_mutations exactly once.
Rejected writer result is surfaced as classifier completion status.
Mutation summary includes classifier-originated batch outcome.
```

Targeted tests:

```powershell
pytest tests/k1/concierge/section_update/test_active_apply.py -v
pytest tests/k1/concierge/test_m04_e43_session_bundle.py -v
```

#### M2.I4 Coordinate Active-Mode Commit Before Next Front Snapshot

Core concept: active classifier writes must land before the next prompt snapshot or any FrontLock replay sees state.

Issue context:

```text
active turn close
-----------------

response.final
   |
   v
history write
   |
   v
section update apply/degrade with timeout
   |
   v
section_update.completed
   |
   v
turn.completed
   |
   v
FrontLock drain / next snapshot
```

What this prevents:

```text
M2.I4 prevents the next Front turn from reading a snapshot that is missing accepted classifier writes from the previous turn.
```

Code boundaries:

```text
k1/concierge/fsm/controller.py _execute_response_final_decision
k1/concierge/fsm/controller.py _finalize_turn
k1/concierge/fsm/controller.py _emit_turn_completed
k1/concierge/fsm/controller.py _drain_front_lock_queue
k1/concierge/section_update/lifecycle.py
```

Ordering contract:

```text
Shadow:
response.final -> history write -> emit turn.completed -> drain FrontLock -> async classifier -> emit section_update.completed

Active:
response.final -> history write -> build/apply section update with timeout -> emit section_update.completed -> emit turn.completed -> drain FrontLock
```

Acceptance:

```text
Active mode waits for success, no-op, validation rejection, stale rejection, timeout, or provider failure before turn.completed.
Timeout degrades to no-op diagnostics and never retries inside the same turn.
FrontLock drains only after the active section-update boundary closes.
Disabled/shadow mode preserves existing _finalize_turn ordering.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_turn_completed_coordination.py -v
```

#### M2.I5 Resolve MemoryWriter Ordering Against turn.completed

Core concept: MemoryWriter must not persist a pre-classifier turn summary when active-mode classifier writes are intended to be durable context for the same completed turn.

Issue context:

```text
turn.completed is a downstream trigger
   |
   v
MemoryWriter / durable memory pipeline

active mode must therefore be:

classifier apply/degrade
   |
   v
turn.completed
   |
   v
MemoryWriter sees the right completed-turn state
```

What this prevents:

```text
M2.I5 prevents durable memory from recording the turn before active classifier writes have landed or explicitly degraded.
```

Code boundaries:

```text
k1/concierge/fsm/controller.py _emit_turn_completed
k1/memory_writer/pipeline/session_batch_dispatcher.py
k1/concierge/section_update/lifecycle.py
```

Specific answer:

```text
Active mode gates turn.completed until classifier apply finishes or degrades to no-op.
Shadow mode must not gate turn.completed; it publishes section-update diagnostics after the existing MemoryWriter path.
The classifier completion status should be available in active-mode turn.completed metadata if current event schema allows it; otherwise, emit adjacent diagnostics with the same turn id.
```

Acceptance:

```text
MemoryWriter sees active classifier writes before consuming turn.completed.
MemoryWriter ordering is unchanged in disabled and shadow modes.
A classifier timeout cannot block MemoryWriter indefinitely.
```

Targeted tests:

```powershell
pytest tests/k1/concierge/section_update/test_memory_writer_ordering.py -v
```

#### M2.I6 Add Dispatch-Critical Overlay And Back Snapshot Gating

Core concept: Back reads SessionState once at task start/resume, so dispatch-critical classifier deltas must be committed before Back starts or carried as an explicit overlay.

Issue context:

```text
Front dispatches task
   |
   v
classifier finds dispatch-critical context
   |
   +--> preferred: commit through writer before Back starts
   |
   +--> degraded exception: bounded TurnStateOverlay
   |
   v
Back reads one startup snapshot
```

What this prevents:

```text
M2.I6 prevents Back from starting with missing referents, facts, or clarification answers that Front/Classifier already knew were dispatch-critical.
It also prevents overlays from becoming fake durable SessionState.
```

Code boundaries:

```text
k1/concierge/fsm/controller.py _on_task_dispatch
k1/concierge/fsm/controller.py _route_via_orchestrator
k1/concierge/actors/back.py _read_ss_snapshot
k1/concierge/actors/back.py back_handler
k1/concierge/section_update/overlay.py
```

Specific answer:

```text
Default active behavior: commit dispatch-critical facts/referents/clarification answers before Back task start.
Overlay is exceptional: use only for bounded same-turn facts that cannot safely wait for the writer path.
Overlay carries explicit provenance, snapshot version, fields applied, and degraded reason when writer apply timed out.
Back must not treat overlay as durable SessionState.
```

Acceptance:

```text
Dispatch-critical plan mutations are either committed before Back snapshot or represented in TurnStateOverlay.
Back receives at most one overlay for the turn and can log whether it was durable or degraded.
Overlay cannot target runtime-owned sections or create task routing authority.
Timeout path does not start Back with silently missing critical context.
```

Targeted tests:

```powershell
pytest tests/k1/concierge/section_update/test_dispatch_overlay.py -v
pytest tests/k1/concierge/section_update/test_back_snapshot_gating.py -v
```

#### M2.I7 Normalize Live API Turn-Complete Records Into The Same Input Contract

Core concept: voice/live API pathways must feed the same `SectionUpdateInput` contract as text turns, and partial transcripts must not trigger classifier writes.

Issue context:

```text
Live API stream
   |
   +--> partial transcript: ignore for classifier writes
   +--> streaming delta: ignore for classifier writes
   +--> final/turn-complete record
      |
      v
   normalize to SectionUpdateInput
      |
      v
   same classifier path as text turns
```

What this prevents:

```text
M2.I7 prevents the classifier from writing cognitive state from unstable partial speech hypotheses or from having a separate voice-only contract.
```

Code boundaries:

```text
k1/concierge/section_update/live_api.py
k1/concierge/section_update/input_builder.py
Live API turn-complete/event handling surfaces found during implementation
```

Implementation notes:

```text
Normalize stable text, voice transcript, tool summaries, device id, timestamps, and final assistant output into SectionUpdateInput.
Ignore partial transcripts, partial hypotheses, and streaming deltas.
Require a turn-complete/final marker before classifier request.
```

Acceptance:

```text
Text and Live API paths produce the same semantic input fields for equivalent final turns.
Partial transcripts never produce writer calls.
Missing device id or timestamp produces explicit degraded diagnostics, not hidden defaults.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_live_turn_complete_contract.py -v
```

M2 blockers and risks:

```text
Classifier latency can delay active turn completion; M2 requires a strict timeout and no same-turn retry.
M1 epoch/idempotency gap must be resolved before active stale rejection can be trusted.
Back snapshot-at-start means dispatch-critical deltas cannot be shadow-only if Back needs them for the same turn.
MemoryWriter consumes turn.completed, so active ordering must be changed carefully and covered by targeted tests.
Front cognitive tools remain seated through M2 for rollback and shadow comparison.
```

M2 implementation status, 2026-05-25:

```text
Status: M2.I1 through M2.I7 implemented and validated.
Scope held: no Front cognitive tools removed. Back overlay support is bounded to explicit dispatch-critical turn context and is not merged into durable SessionState snapshots.

Added package surface:
   k1/concierge/section_update/input_builder.py
   k1/concierge/section_update/events.py
   k1/concierge/section_update/lifecycle.py
   k1/concierge/section_update/apply.py
   k1/concierge/section_update/overlay.py
   k1/concierge/section_update/live_api.py

Added controller coordination:
   k1/concierge/fsm/controller.py set_section_update_classifier(...)
   k1/concierge/fsm/controller.py register_turn_state_overlay(...)
   Active mode runs the bounded classifier/apply/degrade boundary before turn.completed and before FrontLock drains.
   Active mode records a closed boundary per turn_id so duplicate finalize paths do not retry the classifier or writer inside the same turn.
   Malformed classifier/apply failures degrade to section_update.completed diagnostics before turn.completed instead of blocking turn completion.
   Disabled/shadow modes preserve existing _finalize_turn ordering.
   Classifier execution is bounded by timeout and writer apply remains on writer_port only.
   turn.completed now carries a section_update summary for active applied/degraded boundaries before MemoryWriter consumes it.
   Back dispatch preserves one explicit turn_state_overlay and can attach one registered overlay keyed by session/turn without changing the durable SessionState snapshot.
   Live API final-turn records normalize into the same SectionUpdateInput contract; partial transcripts and deltas are ignored before classifier/writer entry.

Added MemoryWriter coordination:
   k1/memory_writer/events.py TurnCompletePayload.section_update
   k1/memory_writer/pipeline/turn_dispatcher.py preserves section_update metadata during typed deserialization.
   k1/memory_writer/pipeline/session_batch_dispatcher.py continues consuming k1.session.turn.completed.v1 after active section-update apply/degrade has closed.

Added Back overlay observation:
   k1/concierge/actors/back.py logs turn_state_overlay metadata at task start/resume while reading SessionState exactly once from the durable snapshot.

Added focused tests:
   tests/k1/concierge/section_update/test_turn_input_builder.py
   tests/k1/concierge/section_update/test_classifier_turn_boundary.py
   tests/k1/concierge/section_update/test_active_apply.py
   tests/k1/concierge/section_update/test_turn_completed_coordination.py
   tests/k1/concierge/section_update/test_memory_writer_ordering.py
   tests/k1/concierge/section_update/test_dispatch_overlay.py
   tests/k1/concierge/section_update/test_back_snapshot_gating.py
   tests/k1/concierge/section_update/test_live_turn_complete_contract.py

Bus boundary added:
   TOPIC_SECTION_UPDATE_REQUESTED = k1.internal.section_update.requested.v1
   TOPIC_SECTION_UPDATE_COMPLETED = k1.internal.section_update.completed.v1
   Builders registered with interactive priority and covered by topic/builder registry tests.

Validation run:
   get_errors on touched M2 package/bus/test files: no errors
   pytest tests/k1/concierge/section_update/test_turn_input_builder.py -v: 4 passed
   pytest tests/k1/concierge/section_update/test_classifier_turn_boundary.py -v: 5 passed
   pytest tests/k1/concierge/section_update/test_active_apply.py -v: 7 passed
   pytest tests/k1/concierge/section_update/test_turn_completed_coordination.py -v: 6 passed
   pytest tests/k1/concierge/test_m02_e23_response_final.py -v: 57 passed
   pytest tests/k1/concierge/section_update/test_classifier_turn_boundary.py tests/k1/concierge/section_update/test_active_apply.py tests/k1/concierge/section_update/test_turn_completed_coordination.py -v: 18 passed
   pytest tests/k1/concierge/section_update/test_plan_schema.py tests/k1/concierge/section_update/test_operation_vocabulary.py tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py tests/k1/concierge/section_update/test_classifier_stub.py tests/k1/concierge/section_update/test_turn_input_builder.py tests/k1/concierge/section_update/test_classifier_turn_boundary.py tests/k1/concierge/section_update/test_active_apply.py tests/k1/concierge/section_update/test_turn_completed_coordination.py -v: 56 passed
   pytest tests/k1/concierge/test_m04_e43_session_bundle.py -v: 20 passed
   pytest tests/k1/concierge/test_m01_builders.py tests/k1/concierge/test_m01_topics.py -v: 106 passed
   pytest tests/k1/concierge/section_update/test_memory_writer_ordering.py -v: 3 passed
   pytest tests/k1/concierge/section_update/test_dispatch_overlay.py -v: 3 passed
   pytest tests/k1/concierge/section_update/test_back_snapshot_gating.py -v: 3 passed
   pytest tests/k1/concierge/section_update/test_live_turn_complete_contract.py -v: 4 passed
   pytest tests/k1/concierge/section_update/test_memory_writer_ordering.py tests/k1/concierge/section_update/test_dispatch_overlay.py tests/k1/concierge/section_update/test_back_snapshot_gating.py tests/k1/concierge/section_update/test_live_turn_complete_contract.py -v: 13 passed
   pytest tests/k1/memory_writer/test_turn_dispatcher.py tests/k1/memory_writer/test_session_batch_dispatcher.py -v: 36 passed
   pytest tests/k1/concierge/section_update/test_turn_completed_coordination.py tests/k1/concierge/test_m02_e23_response_final.py -v: 63 passed
   pytest tests/k1/concierge/section_update -v: 69 passed

Next issue:
   M3 provider-backed quality proof and guardrails, then M4 background updater integration plus Front deload.
```

### M3 Detailed Plan: Classifier Quality Proof And Guardrails

Epic: prove `SectionUpdateClassifier` semantic mutation quality with per-turn manifests, golden cases, provider-backed simulated-kernel corpus runs, and fail-closed guardrails. M3 does not require a separate active-mode proof wall before M4 starts.

Execution correction for this pass: M3 quality proof stays in POC/simulated-kernel validation first. Production code may keep the M0-M2 SectionUpdate contract and boundary scaffolding, but the next architectural move is M4 background integration, not a standalone active-mode canary wall.

M3 operating picture:

```text
M3 is the quality proof ladder.

current Front cognitive writes
   |
   v
shadow classifier plan
   |
   v
per-turn mutation manifest
   |
   v
comparison against current behavior and golden cases
   |
   v
numeric quality gates
   |
   +--> fail: stay shadow/degraded
   |
   +--> pass: start M4 background integration and Front deload
```

M3 drift guard:

```text
Do not treat provider success as mutation quality.
Do not treat aggregate writer stats as semantic equivalence.
Do not remove Front cognitive tools in M3.
Do not call a focused repair subset a full-corpus pass.
Do not require a separate active-mode proof wall before M4.
```

M3 non-negotiables from M0-M2:

```text
Earlier gemini-2.5-flash-lite POC pass rate was 16.7%; do not cite that baseline as active proof.
Batch plan remains the only production V0 shape.
Parallel/by-section calls remain diagnostic and cannot drive active writes.
Front cognitive tools remain seated through M3 for comparison and rollback.
The classifier remains a background turn-boundary updater, not a Front or Back attachment.
```

Latest live POC evidence snapshot, 2026-05-26:

```text
runner: scripts/m3_live_shadow_validation.py
run_label: m3-closurefix-260526a
base_url: http://127.0.0.1:8771
output: data/m3_section_update_shadow_validation_report.json

golden_pass_rate=1.0
schema_validity=1.0
guard_vocabulary_validity=1.0
noop_precision=1.0
mutation_precision=1.0
critical_recall=1.0
shadow_golden_operation_agreement=1.0
dangerous_false_writes=0
provider_failure_degradation_rate=0.0
shadow_p95_ms=4487

active_eligible=false
failed_gates=consecutive_shadow_turns_without_dangerous_false_writes
consecutive_shadow_turns_without_dangerous_false_writes=4/100
```

Quality conclusion: the corrected live POC proves the four-turn golden mutation set, including turn-4 close acknowledgement no-op. It is early evidence only; M3 quality is judged by the staged corpus and targeted repair proofs below, not by production active-mode authorization.

POC harness corrections proven by this run:

```text
Classifier input uses per-turn pre-turn SessionState cognitive snapshots.
Run labels stay in manifest metadata and never enter user-visible turn text or expected beliefs.
Raw legacy Front session write payloads are redacted from classifier input; only non-authoritative tool-name telemetry remains.
Golden expected SectionUpdatePlan fixtures are the primary oracle; legacy Front comparison is telemetry only.
Writer-compatible add_fact payloads include data.confidence and data.source.
Ordinary corrections reject duplicate/negative/confidence-demotion candidates.
Conversational closure/acknowledgement candidates are fail-closed to no_op, not beliefs or narrative lifecycle writes.
```

100-turn corpus staging, 2026-05-26:

```text
Current sequence target: 40 no-op/forbidden/ambiguous, then 35 belief/definition/correction, then 15 scoreboard/clarification, then 10 narrative/affect.
First tranche status: 40 new noop_* golden cases added to scripts/m3_section_update_golden_cases.json.
Second tranche status: 35 new belief/definition/correction cases added: 12 belief_*, 12 definition_*, 11 correction_*.
Final tranche status: 25 new scoreboard/clarification/narrative/affect cases added: 8 scoreboard_*, 7 clarification_*, 5 narrative_*, 5 affect_*.
Active runner config: scripts/m3_live_shadow_validation_quota_config.yaml now selects the full 100-case staged corpus with max_turns=100 and max_model_calls=100.
Dry-run artifacts: data/m3_section_update_shadow_validation_noop40_dry_run_report.json, data/m3_section_update_shadow_validation_belief35_dry_run_report.json, and data/m3_section_update_shadow_validation_100_dry_run_report.json.
Latest dry-run report: run_label=m3-final25-260526a, turn_count=100, golden_fixture_validity=1.0, active_eligible=false because dry run never authorizes active apply.
Quality status: fixture/config/schema dry-run only; do not count this as live safe-shadow evidence until the cumulative live kernel run is explicitly executed.
```

Simulated-kernel provider proof path, 2026-05-26:

```text
Why: the full boot_web/FSM/WebSocket kernel can fail for reasons unrelated to SectionUpdateClassifier quality.
Runner mode: scripts/m3_live_shadow_validation.py --simulated-kernel.
What it keeps: in-memory SessionStateManager, LocalEventAdapter capture mode, DirectWriterAdapter, writer-compatible golden oracle mutations applied after each synthetic pre-turn snapshot, bus/activity metadata shaped like a completed turn, live ModelHub provider calls, manifest/evaluate_quality_gates accounting.
What it removes: boot_web, WebSocket transport, Front ReAct, full FSM progression, browser/UI, and live kernel timeout risk.
Provider routing correction: runner CLI defaults no longer let ambient LLM_PROVIDER override config preferred_provider; classify_observations re-normalizes env after POC dotenv loading so poc/chat_experience_poc/.env cannot flip the classifier from vertex to google.
Four-turn smoke: data/m3_section_update_shadow_validation_simulated4_report.json proves the simulated harness path and reports provider_id=vertex/model_id=gemini-2.5-flash-lite, but active_eligible=false because the terminal lacked Vertex project/location env for that run.
100-turn simulated provider run: data/m3_section_update_shadow_validation_100_simulated_provider_report.json, run_label=m3-sim100-260526a, completed_turns=100/100, oracle_mutation_count=60, oracle_failed_mutation_count=0, active_eligible=false.
100-turn metrics: golden_pass_rate=0.19, schema_validity=0.21, shadow_golden_operation_agreement=0.38, provider_failure_degradation_rate=0.79, dangerous_false_writes=2, consecutive_shadow_turns_without_dangerous_false_writes=82, shadow_p95_ms=1242.
Status distribution: 19 shadow_noop, 2 shadow_plan, 79 provider_failed. First provider failure was turn 22 ProviderError, followed by NoEligibleProviderError. The two dangerous false writes were turn 12 noop_forbidden_control_set_state_request and turn 18 noop_forbidden_meta_policy_question, both emitted beliefs_active.add_fact when the golden oracle expected no_op.
Quality status: simulated-kernel provider proof completed and failed. It is valid classifier/provider failure evidence, not active-mode evidence and not a replacement for later full live-kernel cutover evidence.

Throttled 100-turn simulated provider run: data/m3_section_update_shadow_validation_100_simulated_provider_throttle12b_report.json, run_label=m3-sim100-throttle12b-260526a, model-call spacing=12s, completed_turns=100/100, elapsed_s=1334.141, active_eligible=false.
Throttle result: provider_failure_degradation_rate=0.0 with 59 shadow_plan and 41 shadow_noop; the previous provider collapse was rate/pace-sensitive.
Throttled metrics: golden_fixture_validity=1.0, golden_pass_rate=0.73, schema_validity=1.0, guard_vocabulary_validity=1.0, noop_precision=0.875, mutation_precision=0.6393, critical_recall=0.65, shadow_golden_operation_agreement=0.735, dangerous_false_writes=22, consecutive_shadow_turns_without_dangerous_false_writes=0, shadow_p95_ms=2389.
Throttled mismatch shape: 27 golden mismatches. Remaining failures are classifier behavior, not provider health: 5 no-op false writes; 1 missed definition; 1 correction duplicate/over-write; all 8 scoreboard cases missed or mapped to beliefs/narrative; all 7 clarification cases missed or mapped to beliefs/scoreboard; all 5 affect cases missed or mapped to beliefs. Dominant wrong operation was beliefs_active.add_fact (53 emitted operations).

Prompt/contract repair proof for final 25 non-belief cases: data/m3_section_update_prompt_semantics_probe_provider_contract_guard_report.json, run_label=m3-prompt-contract-guard-25-260526a, model-call spacing=12s, completed_turns=25/25, elapsed_s=333.18, active_eligible=true for this slice.
Repair summary: clarified that clarifications.request is classifier-owned gap detection for underspecified actionable commands even when simulated Front did not ask aloud; added prompt and sanitizer guards for conversation-local deictic referents, topic-only focus/switch language, exact-id clarifications.answer, and first-person affect.
Repair metrics: golden_fixture_validity=1.0, golden_pass_rate=1.0, schema_validity=1.0, guard_vocabulary_validity=1.0, noop_precision=1.0, mutation_precision=1.0, critical_recall=1.0, shadow_golden_operation_agreement=1.0, dangerous_false_writes=0, consecutive_shadow_turns_without_dangerous_false_writes=25, provider_failure_degradation_rate=0.0, shadow_p95_ms=3415.
Repair operation distribution: 4 scoreboard.add_referent, 2 scoreboard.push_question, 2 scoreboard.push_topic, 7 clarifications.request, 5 narrative_active.create_thread, 5 affective_now.update.

Full 100 simulated provider contract-guard v5: data/m3_section_update_shadow_validation_100_simulated_provider_contract_guard_v5_report.json, run_label=m3-sim100-contract-guard-v5-260526a, model-call spacing=12s, completed_turns=100/100, elapsed_s=1351.001, active_eligible=false.
v5 metrics: golden_pass_rate=0.97, schema_validity=1.0, guard_vocabulary_validity=1.0, noop_precision=0.95, mutation_precision=0.9516, critical_recall=0.9833, shadow_golden_operation_agreement=0.97, provider_failure_degradation_rate=0.0, dangerous_false_writes=3, untriaged_high_risk_mismatches=3, consecutive_shadow_turns_without_dangerous_false_writes=25.
v5 failed gates: noop_precision, mutation_precision, untriaged_high_risk_mismatches, dangerous_false_writes, consecutive_shadow_turns_without_dangerous_false_writes.

Focused repair subset v5: data/m3_section_update_100_repair_subset_provider_v5_report.json, run_label=m3-repair-subset-27-v5-260526a, model-call spacing=12s, completed_turns=27/27, active_eligible=true for this focused subset.
v5 subset metrics: golden_pass_rate=1.0, noop_precision=1.0, mutation_precision=1.0, critical_recall=1.0, shadow_golden_operation_agreement=1.0, dangerous_false_writes=0, provider_failure_degradation_rate=0.0, shadow_p95_ms=1753.
v5 subset operation distribution: 5 beliefs_active.add_fact, 2 clarifications.request, 2 scoreboard.add_referent, 1 scoreboard.push_question, 1 scoreboard.push_topic, 16 no-op turns.

Focused repair subset v6: data/m3_section_update_repair_subset_v6_report.json, run_label=m3-repair-subset-3-v6-260526a, model-call spacing=12s, completed_turns=3/3, active_eligible=true for this exact failure subset.
v6 subset metrics: golden_pass_rate=1.0, noop_precision=1.0, mutation_precision=1.0, critical_recall=1.0, shadow_golden_operation_agreement=1.0, dangerous_false_writes=0, provider_failure_degradation_rate=0.0, shadow_p95_ms=4287.
v6 subset covered the three full-v5 failure classes: internal policy/meta write question, warm/archive live-state read question, and durable red/yellow lunchbox correction misrouted as a local referent.

Quality status, 2026-05-26: do not run another full 100-case loop before integration. Full v5 is sufficient risk evidence for the remaining corpus shape, and v6 proves the exact high-risk failure subset after repair. Move to M4 background integration with this known evidence package; full-corpus rerun is deferred to M5 tracker/cutover confidence if classifier prompt/schema changes again.
```

#### M3.I1 Run Shadow Mode Beside Current Front Cognitive Tool Writes

Core concept: observe classifier output next to the current Front cognitive write path without mutating SessionState.

Issue context:

```text
authoritative current path
   |
   v
Front cognitive tool writes
   |
   v
SessionState

shadow observation path
   |
   v
same completed turn input
   |
   v
classifier plan
   |
   v
manifest only, no writer call
```

What this prevents:

```text
M3.I1 prevents the classifier from getting active-write authority before it has been compared against the current working behavior.
```

Code boundaries:

```text
k1/concierge/section_update/lifecycle.py
k1/concierge/section_update/classifier.py
k1/concierge/section_update/observability.py
k1/concierge/fsm/controller.py _finalize_turn
k1/concierge/fsm/controller.py _emit_turn_completed
poc/section_update_classifier_poc.py batch tool schema
```

Implementation notes:

```text
Shadow mode runs after existing response finalization and current Front cognitive writes.
Classifier input uses the past/pre-turn SessionState cognitive snapshot for that turn, not one final shared post-run snapshot.
Live POC uniqueness must stay in manifest metadata; do not inject validation labels into user-visible turn text or expected beliefs.
Shadow mode never calls writer_port.batch_mutations.
Shadow mode records classifier plan, validation result, provider metadata, and comparison result.
Provider failure, malformed output, no tool call, or timeout becomes diagnostic no-op.
```

Shadow comparison method:

```text
Join classifier manifest and Front cognitive writes by session_id + turn_id.
Compare section, operation, canonical payload fields, no-op/write decision, confidence bucket, and commit class.
Treat Front writes as current-behavior baseline, not always as truth; high-risk disagreement requires triage.
```

Acceptance:

```text
Every eligible turn produces shadow diagnostics.
Response text and turn.completed ordering are unchanged in shadow mode.
No writer calls happen in shadow mode.
Comparison result is present even when classifier degrades to no-op.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_shadow_mode.py -v
```

#### M3.I2 Add Mutation Manifest Observability

Core concept: aggregate writer turn stats are not enough to prove shadow-vs-Front equivalence, so M3 needs a per-turn mutation manifest.

Issue context:

```text
classifier result
   |
   +--> plan metadata
   +--> provider/model metadata
   +--> validation status
   +--> section.operation list
   +--> latency and timeout data
   +--> rejected candidates
   +--> Front comparison status
   |
   v
mutation manifest
   |
   v
quality gate input
```

What this prevents:

```text
M3.I2 prevents a release claim based only on "some mutations happened" rather than "the right mutations happened for the right turn."
```

Code boundaries:

```text
k1/concierge/section_update/observability.py
k1/concierge/events/mutation.py
k1/sessionstate/ports/writer.py
k1/sessionstate/adapters/direct_writer.py
k1/concierge/fsm/controller.py _emit_turn_mutation_summary
```

Manifest fields:

```text
plan_id
turn_id
session_id
mode
status
classifier_version
snapshot_version
snapshot_epoch
provider_id
model_id
trace_id
model_latency_ms
classifier_e2e_ms
timeout_ms
plan_confidence
mutation_count
sections
operations
validation_errors
rejected_candidates
degradation_reason
idempotency_keys
batch_success_rate
front_cognitive_tool_names
comparison_status
false_positive_count
false_negative_count
dangerous_mismatch_count
```

Acceptance:

```text
Manifest can reconstruct why each classifier plan was accepted, rejected, degraded, applied, or compared as mismatch.
Manifest does not include raw secrets or full prompt/memory dumps.
Manifest can be generated in shadow, active, degraded_noop, and offline_stub modes.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_mutation_manifest.py -v
```

#### M3.I3 Convert POC Cases Into Golden SectionUpdatePlan Expectations

Core concept: make the POC cases deterministic contract tests for the typed M1 plan and compiler.

Issue context:

```text
POC cases
   |
   v
expected SectionUpdatePlan fixtures
   |
   +--> expected no-op/write decision
   +--> expected sections
   +--> expected operations
   +--> expected canonical payload keys
   |
   v
deterministic golden tests
```

What this prevents:

```text
M3.I3 prevents live model output from being the only proof of correctness and gives the compiler a fixed regression target.
```

Code boundaries:

```text
poc/section_update_classifier_cases.json
poc/section_update_classifier_poc.py parse_tool_plan / validate_plan behavior
k1/concierge/section_update/types.py
k1/concierge/section_update/plan_compiler.py
tests/k1/concierge/section_update/golden_cases/
```

Implementation notes:

```text
Each POC case gets an expected no-op/write classification.
Expected writes specify section, operation, canonical payload keys, and commit class.
Golden tests assert typed plan validity, vocabulary validity, compiler output, and no forbidden sections.
Do not require live provider calls for golden tests.
```

Acceptance:

```text
100% schema validity on golden expected plans.
0 forbidden sections.
0 invalid operations.
Exact expected no-op/write behavior for all baseline cases.
Compiler output is deterministic for every golden plan.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_golden_section_update_cases.py -v
```

#### M3.I4 Validate Provider, Model, Latency, And Degradation Behavior

Core concept: provider routing and model behavior must be measured and bounded before active use.

Issue context:

```text
preferred provider/model config
   |
   v
ModelHub route
   |
   +--> correct route and batch tool call: validate output
   |
   +--> wrong route / no tool call / malformed JSON / timeout
            |
            v
         degraded_noop
```

What this prevents:

```text
M3.I4 prevents background classifier evidence from being polluted by the wrong provider/model path or malformed provider output.
```

Code boundaries:

```text
k1/concierge/section_update/classifier.py
k1/concierge/section_update/observability.py
poc/section_update_classifier_poc.py live ModelHub request path
k1/config/providers/vertex.manifest.yaml
poc/section_update_classifier_runs/20260524_101604/summary.md
```

Provider behavior:

```text
Preferred route: vertex + gemini-2.5-flash-lite.
Route mismatch, missing tool call, malformed JSON, timeout, provider error, and validation failure all become degraded_noop unless running offline_stub tests.
No same-turn retry in active lifecycle.
Batch tool choice only.
Provider/model IDs are recorded in every manifest.
```

Acceptance:

```text
Provider route mismatch blocks quality credit and background apply.
Timeout returns safe no-op with degradation_reason.
Live adapter can be forced off by mode.
Validation summary reports model latency and classifier E2E latency.
```

Targeted tests and measurement:

```powershell
pytest tests/k1/concierge/section_update/test_provider_validation.py -v
$env:LLM_PROVIDER='vertex'
$env:GOOGLE_GENAI_USE_VERTEXAI='True'
$env:VERTEX_MODEL='gemini-2.5-flash-lite'
$env:K1_SECTION_UPDATE_MODEL='gemini-2.5-flash-lite'
python .\poc\section_update_classifier_poc.py --live --mode batch --preferred-provider vertex --preferred-model gemini-2.5-flash-lite --temperature 0 --timeout-ms 45000 --max-output-tokens 2048
```

#### M3.I5 Freeze Quality Evidence And Known Limitations

Core concept: M3 exits with auditable evidence, known failures, and a clear decision record for M4. It does not create a separate active-mode canary wall before Front deloading work starts.

Issue context:

```text
provider run reports + manifests + repair subsets
   |
   +--> full corpus result
   +--> focused repair evidence
   +--> mismatch taxonomy
   +--> guardrail/test coverage
   |
   v
M4 background integration decision record
```

What this prevents:

```text
M3.I5 prevents a green focused repair subset from being misread as full-corpus proof, and prevents the old active-mode gate from blocking M4 integration planning.
```

Code boundaries:

```text
scripts/m3_live_shadow_validation.py
data/m3_section_update_*_report.json
data/m3_section_update_prompt_semantics_probe_audit.md
docs/plans/front_deloading_sequential_execution_plan.md
```

Evidence behavior:

```text
Full corpus reports decide whether M3 quality is complete.
Focused repair subset reports prove specific failure classes are repaired.
Both are preserved with run_label, provider/model, operation counts, and failed_gates.
M4 can start once the quality state is understood; full proof still matters before declaring M3 complete.
```

Acceptance:

```text
Evidence doc records latest full 100 result and latest focused repair result separately.
Known high-risk mismatch classes map to prompt/schema/sanitizer tests.
Plan says background integration is next, not active-mode proof as a separate milestone.
Rollback surfaces remain available because schemas/implementations are not deleted in M3.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_classifier_stub.py tests/k1/concierge/section_update/test_m3_live_shadow_validation_runner.py -q
```

#### M3.I6 Enforce Numeric Mutation-Quality Gates

Core concept: hidden cognitive writes need measurable quality. Gates decide M3 completion and background-updater readiness; they are not a separate active-mode ceremony before M4.

Issue context:

```text
golden results + shadow manifests + live measurements
   |
   v
quality gate evaluator
   |
   +--> schema/guard validity
   +--> no-op precision
   +--> mutation precision
   +--> critical recall
   +--> dangerous false writes
   +--> latency/degradation rates
   |
   v
M3 quality complete? yes/no
```

What this prevents:

```text
M3.I6 prevents subjective "looks good" judgment from replacing measurable safety criteria for hidden cognitive writes.
```

Code boundaries:

```text
k1/concierge/section_update/quality_gates.py
k1/concierge/section_update/observability.py
poc/section_update_classifier_runs/20260524_101604/summary.md
poc/front_prompt_compare/runs/20260521_150501/summary.md
```

Required full-corpus quality gates:

```text
golden pass rate >= 95%
schema validity = 100%
guard/vocabulary validity = 100%
forbidden section/op rate = 0%
no-op precision >= 98%
mutation precision >= 97%
critical recall >= 90%
shadow section-operation agreement with current Front writes >= 90%
untriaged high-risk mismatches = 0
dangerous false writes = 0
100-case staged corpus has 0 dangerous false writes before M3 is declared complete
```

Latency and degradation gates:

```text
shadow p95 <= 10s
provider failure/degradation rate <= 1% over validation window
timeout path always safe no-op
no same-turn retry loop
```

Acceptance:

```text
Quality gate evaluator can fail the build/test run from manifest summaries.
Gate report records evidence artifact paths and provider/model identity.
Background apply must remain disabled or diagnostic-only for failing high-risk classes until guardrails are added.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_quality_gates.py -v
```

M3 blockers and risks:

```text
Latest four-turn live POC no longer fails golden/schema/guard/no-op/mutation quality gates.
Latest full 100 v5 still fails with 3 dangerous false writes; latest 3-case v6 focused repair subset passes all gates for those exact failure classes.
Per user direction on 2026-05-26, stop rerunning the 100-case loop now and move to M4 integration; carry the full-v5 failure shape as tracked risk.
1-5 second classifier latency is acceptable for asynchronous background maintenance but unsafe for synchronous same-turn gating without a timeout/degrade boundary.
Legacy Front operation mismatch is expected on some turns and remains telemetry only; golden SectionUpdatePlan comparison is the primary oracle.
Batch apply is not transactional, so M1 whole-plan validation remains mandatory before background apply.
M1 snapshot epoch/idempotency must be real before stale rejection can be trusted.
```

### M4 Detailed Plan: Background Updater Integration And Front Deload

Epic: after M3 quality is understood, wire `SectionUpdateClassifier` as a background completed-turn updater and cut Front over from ReAct-owned cognitive writes to classifier-owned SessionState mutation. Front remains voice, clarification, presentation, memory read, routing, dispatch, HIL, PRESENT, and WEAVE.

M4 operating picture:

```text
M4 changes Front's job and adds the background updater lane.

M3 quality evidence understood
   |
   v
Background SectionUpdateClassifier consumes completed turns
   |
   +--> validates plan/snapshot/schema
   +--> applies accepted cognitive writes through writer_port
   +--> no-op diagnostics on provider/schema/stale/guard failure
   |
   v
Front prompt contract changes
   |
   +--> Front consumes situation frame
   +--> Front keeps memory-read / dispatch / capability tools
   +--> Front loses visible cognitive write tools
   |
   v
SectionUpdateClassifier owns hidden cognitive writes as background maintenance
   |
   v
old cognitive schemas remain hidden for rollback/internal comparison
```

M4 drift guard:

```text
Do not delete cognitive schemas or implementations.
Do not remove recall, summary, dispatch, discovery, or safe capability tools from Front.
Do not make classifier mechanics visible to the user.
Do not attach the classifier to Front ReAct or Back execution.
```

M4 start gate:

```text
Do not start M4 allowlist removal from a failing or unknown classifier quality state.
Focused repair subsets are evidence for fixes, not full proof by themselves.
Do not delete cognitive schemas or implementations in M4.
Rollback must be able to restore old Front cognitive tool visibility by flag/config change.
```

#### M4.I1 Specify The Per-Session Worker Lifecycle Against KernelService P1-P6

Core concept: M4 is the first integration floor. The classifier foundation exists; now the plan must say exactly where the background updater lives in the kernel session lifecycle and which already-built ports it consumes.

Source surfaces read for this issue:

```text
k1/kernel/service.py _create_session_tier2
   P1: session_bus, session_router, front/back mailboxes
   P2: SessionStateManager, DirectWriterAdapter, AsyncSSMBridge
   P3: per-session Fabric and event/delta/model adapters
   P3.5/P3.6/P3.7/P3.8: SelfModel, temporal, spatial, grounding handles
   P4: ConciergeRuntime with PortBundle(writer=ss_writer)
   P5: MemoryWriterService
   P6: SessionInstance assembly and _sessions registration

k1/kernel/session.py SessionInstance
   currently stores bus, router, session_state, fabric, concierge, memory_writer,
   dispatchers, contexts, ledger, self_model, temporal, spatial, grounding.
   It does not yet store a section_update_worker.

k1/kernel/service.py destroy_session
   tears down in reverse order after popping _sessions; current reverse order stops
   MemoryWriter before Concierge, then HIL/Fabric/SessionState/Bus.
```

Worker ownership decision:

```text
Owner: KernelService per-session tier.
Instance count: one worker per SessionInstance.
Scope: session_bus only, never kernel bus.
Inputs: turn.completed envelopes, SessionState read surface, writer_port, ModelHub, classifier config.
Outputs: section_update.requested/completed diagnostics, writer_port BatchRequest apply results.
Forbidden attachment points: Front react_loop, Back actor/tool execution, user-visible prompt text.
```

Why the worker belongs at the kernel/session floor:

```text
KernelService already owns the only place where all required ports are present together:
session_bus from P1, ssm + ss_writer from P2, model_hub from tier 1, Concierge from P4,
MemoryWriter from P5, and SessionInstance teardown from P6.

Concierge knows turn semantics, but KernelService owns lifecycle, startup failure cleanup,
multi-session isolation, health, and teardown. Therefore M4 should create a per-session
background worker in KernelService and let Concierge remain the turn publisher.
```

Construction simulation:

```text
Floor 0, M3 foundation:
   classifier prompt/schema/runner/guards exist and have evidence.

Floor 1, M4 kernel frame:
   build one SectionUpdateBackgroundWorker per session and store it on SessionInstance.

Floor 2, M4 Concierge turn feed:
   worker consumes completed-turn records emitted by Concierge, not Front tool calls.

Floor 3, M4 writer/apply lane:
   worker validates/compiles/applies accepted plans through writer_port only.

Floor 4, M4 Front deload:
   hide cognitive tools and rewrite prompt once the background lane is wired and observable.
```

Acceptance:

```text
Spec names every source port the worker consumes and where it is created.
Spec says the classifier is per-session, not global.
Spec says the worker uses session_bus, not kernel bus.
Spec says SessionInstance gains an optional section_update_worker field.
Spec says startup failure cleanup mirrors neighboring P5/P6 cleanup style.
```

#### M4.I2 Add The P5.5 Worker Slot, SessionInstance Field, Teardown, Config, And Health Contract

Core concept: define and implement the first KernelService construction floor for the hidden background updater.

Implementation checkpoint, 2026-05-26:

```text
Landed first M4 floor:
   k1/concierge/section_update/worker.py
      SectionUpdateBackgroundWorker
      SectionUpdateWorkerConfig
      SectionUpdateWorkerStats
      turn.completed subscription, bounded queue, requested/completed diagnostics,
      shadow/degraded/background_apply modes, writer_port apply boundary, stats snapshot.

   k1/kernel/service.py
      P5.5 worker slot after MemoryWriter start and before SessionInstance assembly.
      set_section_update_classifier(...) injection point for future provider adapter wiring.
      destroy_session stops the worker before MemoryWriter teardown.
      health_check exposes section_update_workers readiness when the feature is enabled.

   k1/kernel/session.py
      optional section_update_worker field.

   k1/concierge/config/kernel.py
      enable_section_update_worker default False.
      section_update_worker_mode default off.
      section_update_worker_timeout_ms, section_update_worker_queue_max,
      section_update_classifier_version.
```

Issue context:

```text
_create_session_tier2
    |
    +--> P1 session_bus exists
    +--> P2 ssm + ss_writer exist
    +--> P4 ConciergeRuntime exists and has writer in PortBundle
    +--> P5 MemoryWriter exists and starts
    |
    v
P5.5 SectionUpdateBackgroundWorker starts and subscribes to completed turns
    |
    v
P6 SessionInstance stores section_update_worker and session enters _sessions
```

Exact source anchors and what to look for:

```text
k1/kernel/service.py _create_session_tier2:
   Look at P2 for ss_writer.bind_manager(ssm, ssm.mutation_guard).
   Look at P4 for PortBundle(writer=ss_writer).
   Look at P5 for session_memory_writer creation and await session_memory_writer.start().
   Insert P5.5 after MemoryWriter start succeeds and before SessionInstance construction.

k1/kernel/session.py SessionInstance:
   Add section_update_worker: Any = None next to background/session helpers.

k1/kernel/service.py destroy_session:
   Stop section_update_worker before MemoryWriter teardown, because the worker can still hold
   pending classification/apply work and needs writer_port/session_bus alive during its own stop.

k1/concierge/config/kernel.py KernelConfig:
   Add migration flags and model knobs here; no section_update flags currently exist.
```

P5.5 worker contract:

```text
Create only when section_update_enabled or section_update_mode is not off/disabled.
Constructor receives session_id, session_bus, ssm/state reader, writer_port, model_hub,
classifier adapter/factory, idempotency store, config, and logger/metrics hooks.
start() subscribes to k1.session.turn.completed.v1 and creates any worker task/queue.
stop() unsubscribes, cancels/drains pending background work according to mode, and never writes after stop begins.
```

Config contract:

```text
enable_section_update_worker: bool = False during migration default.
section_update_worker_mode: off|shadow|degraded_noop|background_apply|offline_stub.
section_update_provider: vertex by provider proof default.
section_update_model: gemini-2.5-flash-lite by current M3 evidence.
section_update_worker_timeout_ms: classifier call deadline for background work.
section_update_worker_queue_max: bounded queue to prevent turn-completed backlog.
front_deload_cognitive_tools: bool = False until M4 allowlist/prompt change is validated.
```

Health contract:

```text
KernelService.health_check should expose per-session worker state when present:
   running/stopped
   mode
   queue_depth
   last_completed_turn_id
   last_status
   last_error_code
   applied_count/rejected_count/noop_count/provider_failed_count

Health is diagnostic. A failed background worker does not fail the user-visible turn,
but should fail readiness for completed deload cutover in M5.
```

Startup/teardown failure semantics:

```text
P5.5 start failure:
   If section_update_mode is off/shadow/degraded_noop, fail closed to no worker and log diagnostics.
   If section_update_mode is background_apply and configured as required, abort session create and run reverse cleanup.

P5.5 stop failure:
   destroy_session continues collecting errors, matching existing MemoryWriter/Concierge teardown style.
   Worker stop must happen before SessionStateManager stop and before session_bus close.
```

Acceptance:

```text
SessionInstance exposes section_update_worker for teardown and inspection.
Worker start/stop lifecycle appears in KernelService lifecycle logs as P5.5_complete and P5.5_teardown_complete.
Worker is absent when disabled and present when enabled in targeted KernelService wiring tests.
No full kernel suite is required for this milestone.
```

Targeted tests to create or update:

```powershell
pytest tests/k1/concierge/section_update/test_background_worker.py -v
pytest tests/k1/kernel/test_service.py -k "optional_fields_default_none or section_update_worker" -v
```

Latest targeted validation:

```text
pytest tests/k1/concierge/section_update/test_background_worker.py -v
   3 passed

pytest tests/k1/kernel/test_service.py -k "optional_fields_default_none or section_update_worker" -v
   2 passed, 437 deselected
```

#### M4.I3 Convert The Current Concierge Active Boundary Into Background-Worker Semantics

Core concept: Concierge already has section-update hooks, but the current names and mode shape are synchronous active-boundary language. M4 must reuse the good contracts and move the ownership out to the background worker.

Implementation checkpoint, 2026-05-26:

```text
Landed controller ownership correction:
   k1/concierge/fsm/controller.py
      normal worker-owned modes are disabled|shadow|background_apply|degraded_noop and do not gate turn.completed.
      old active mode is accepted only as a legacy alias for explicit sync_overlay.
      _finalize_turn now calls _run_sync_section_update_overlay_boundary, then emits turn.completed, then drains FrontLock.
      turn.completed payload now includes prompt_mode and fsm_state for the background worker input path.

   tests/k1/concierge/section_update/test_turn_completed_coordination.py
      reframed active-boundary tests as sync_overlay compatibility tests.
      added coverage that worker-owned modes do not publish requested/completed from the controller.

   tests/k1/concierge/section_update/test_memory_writer_ordering.py
      confirms worker-owned modes leave MemoryWriter ordering unchanged while sync_overlay remains explicit compatibility.
```

Source surfaces read for this issue:

```text
k1/concierge/fsm/controller.py set_section_update_classifier
   currently accepts disabled|shadow|active and says active is the only mode gating turn.completed.

k1/concierge/fsm/controller.py _finalize_turn
   currently calls _run_active_section_update_boundary(envelope), then _emit_turn_completed, then _drain_front_lock_queue.

k1/concierge/fsm/controller.py _run_active_section_update_boundary
   currently builds input, publishes requested, classifies blocking, applies through writer_port,
   publishes completed, and degrades on exceptions before turn.completed.

k1/concierge/fsm/controller.py _build_section_update_input
   already delegates to build_section_update_input with user_text, assistant_text, fsm_state,
   prompt_mode, classifier_version, and timeout constraints.

k1/concierge/fsm/controller.py _emit_turn_completed
   publishes k1.session.turn.completed.v1 with turn_id, session_id, cognitive_trace_id,
   user_message, assistant_response, timestamp_ms, turn_number, and optional section_update summary.
```

Integration decision:

```text
Do not keep the normal path as synchronous active gating.
The normal M4 mode is background_apply: turn.completed is emitted and the worker consumes it.
The old active boundary becomes one of two things:
   1. a compatibility/diagnostic path behind a non-default flag, or
   2. a same-turn dispatch-critical overlay path only when explicitly required.
```

Concrete refactor spec:

```text
Rename concepts in docs/tests from active to background_apply for the normal integrated lane.
Keep build_section_update_input as the shared input builder.
Keep SectionUpdateCompletionStatus and requested/completed payload builders.
Move classify/apply orchestration out of _finalize_turn normal path and into the worker.
Keep _emit_turn_completed as the publisher of completed-turn records.
Do not publish classifier internals to Front prompt text or Back task payload unless using explicit overlay.
```

Turn payload requirements for the worker:

```text
Required fields from _emit_turn_completed:
   turn_id
   session_id
   cognitive_trace_id
   user_message
   assistant_response
   timestamp_ms
   turn_number

Additional fields to add if needed for better quality/replay:
   prompt_mode
   fsm_state
   input_snapshot_version
   input_snapshot_source_epoch
   front_tool_call_summaries redacted to names/counts only
   section_update_trace_id
```

Snapshot rule:

```text
M3 evidence used per-turn cognitive snapshots. M4 must be explicit about the runtime snapshot it passes.
Preferred runtime rule: include snapshot_version/source_epoch in the turn-completed-derived input and reject stale apply through PlanCompiler.
If only current post-turn snapshot is available in M4, record that as a known limitation and measure drift in M5.
```

Acceptance:

```text
Normal turn completion does not call the classifier inside Front ReAct or Back execution.
Background worker can build the same SectionUpdateInput shape as the existing controller helper.
Old active boundary tests are either renamed/reframed to background_apply or kept as explicit sync-overlay tests.
No hidden classifier failure prevents response.final or user-visible response delivery.
```

Targeted tests to create or update:

```powershell
pytest tests/k1/concierge/section_update/test_turn_completed_background_worker.py -v
pytest tests/k1/concierge/section_update/test_turn_input_builder.py -v
pytest tests/k1/concierge/section_update/test_turn_completed_coordination.py -v
```

Latest targeted validation:

```text
pytest tests/k1/concierge/section_update/test_turn_completed_coordination.py -v
   6 passed

pytest tests/k1/concierge/section_update/test_memory_writer_ordering.py -v
   3 passed

pytest tests/k1/concierge/section_update/test_turn_input_builder.py -v
   4 passed
```

#### M4.I4 Apply Accepted Plans Through writer_port With Fail-Closed Background Diagnostics

Core concept: applying a plan is not a worker privilege. The worker only reaches the already-built compiler and writer_port path, and every unsafe condition becomes diagnostic no-op or rejection.

Implementation checkpoint, 2026-05-26:

```text
Landed fail-closed background diagnostics:
   k1/concierge/section_update/lifecycle.py
      classify_section_update_blocking now rejects malformed classifier returns with diagnostics code invalid_schema.

   k1/concierge/section_update/worker.py
      queue overflow publishes requested/completed diagnostics with code queue_full when turn input can be built.
      background_apply rejects invalid schema without writer_port calls.
      completed diagnostics include provider_id and model_id from worker config.

   k1/concierge/section_update/events.py
      requested/completed payloads carry provider_id/model_id without mutation payload bodies.

   k1/concierge/config/kernel.py and k1/kernel/service.py
      section_update_provider and section_update_model config are passed into worker diagnostics.
```

Source surfaces read for this issue:

```text
k1/concierge/section_update/apply.py apply_section_update_plan
k1/concierge/section_update/plan_compiler.py PlanCompiler
k1/concierge/section_update/events.py SectionUpdateCompletionStatus and payload builders
k1/concierge/section_update/lifecycle.py run_shadow_section_update and classify_section_update_blocking
k1/concierge/bus/topics.py TOPIC_SECTION_UPDATE_REQUESTED and TOPIC_SECTION_UPDATE_COMPLETED
k1/concierge/bus/builders.py build_section_update_requested and build_section_update_completed
k1/concierge/tools/implementations.py old cognitive tools using ctx.writer_port for rollback comparison
```

Background apply algorithm, in spec form:

```text
1. Receive turn.completed on the session_bus.
2. Build SectionUpdateInput from the turn payload plus SessionState snapshot/projection.
3. Publish section_update.requested with mode=background_apply or mode=shadow.
4. Run classifier with configured provider/model/timeout.
5. If provider fails, times out, emits no tool call, emits invalid schema, or confidence is too low:
       publish section_update.completed with provider_failed/timed_out/degraded_noop and do not call writer_port.
6. If a plan exists, compile with PlanCompiler and idempotency store.
7. If compile rejects stale/duplicate/invalid/forbidden target:
       publish section_update.completed with rejected/stale/duplicate and do not call writer_port.
8. If compile requires no writer call:
       publish no-op/shadow_noop and do not call writer_port.
9. If compile produces BatchRequest:
       call writer_port exactly once.
10. Publish section_update.completed with applied/writer_rejected/writer_failed and compact writer summary.
```

Failure taxonomy to track:

```text
provider_failed
timed_out
invalid_schema
no_tool_call
low_confidence_noop
forbidden_section_or_operation
stale_snapshot
duplicate_plan_or_mutation
writer_unavailable
writer_rejected
writer_failed
applied
shadow_plan
shadow_noop
```

Observability payload requirements:

```text
Every completed event should include:
   turn_id, session_id, cognitive_trace_id, mode, classifier_version, provider_id, model_id
   status, mutation_count, rejected_candidate_count, elapsed_ms
   plan_id, plan_idempotency_key, snapshot_version, snapshot_source_epoch where available
   diagnostics as compact code/message records
   writer_summary with section/operation counts but no private raw payload leakage in normal logs
```

Backpressure and idempotency rules:

```text
Worker queue is bounded. On overflow, emit degraded_noop/queue_full and skip the turn.
Processed turn ids are tracked per session so duplicate turn.completed events do not double-write.
PlanCompiler/idempotency remains the authoritative duplicate mutation guard.
Retries are off by default for same-turn work; no same-turn retry loop.
```

Acceptance:

```text
writer_port is called zero times for shadow/degraded/invalid/stale/duplicate/provider-failed cases.
writer_port is called exactly once for one accepted compiled BatchRequest.
section_update.completed exists for every requested turn, including failures.
Logs and events expose enough status to build the M5 working tracker.
```

Targeted tests to create or update:

```powershell
pytest tests/k1/concierge/section_update/test_background_worker.py -v
pytest tests/k1/concierge/section_update/test_plan_compiler.py -v
pytest tests/k1/concierge/section_update/test_idempotency.py -v
pytest tests/k1/concierge/section_update/test_worker_observability.py -v
```

Latest targeted validation:

```text
pytest tests/k1/concierge/section_update/test_background_worker.py -v
   5 passed

pytest tests/k1/concierge/section_update/test_classifier_turn_boundary.py -v
   5 passed

pytest tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py -v
   11 passed
```

#### M4.I5 Trace Current Temporal, SelfModel, SessionState, And Prompt Grounding Sources

Core concept: prove that Front receives enough situation frame as prompt context before removing cognitive write chores.

Issue context:

```text
grounding sources
   |
   +--> NOW / temporal context
   +--> active member / SelfModel
   +--> affect and conscience projection
   +--> SessionState cognitive projection
   +--> compressed history / dispatch context
   |
   v
prompt builder
   |
   v
Front situation frame
```

What this prevents:

```text
M4.I5 prevents the cutover from making Front lighter but less situated.
Front loses write chores only after its read/projection context is proven intact.
```

Code boundaries:

```text
k1/concierge/prompt/builder.py
k1/concierge/prompt/sections.py
k1/concierge/actors/front.py _extract_scenario_data
k1/concierge/actors/front.py front_handler
temporal/spatial/SelfModel grounding sources found during implementation
```

Implementation notes:

```text
Trace compressed_context stripping/replacement.
Trace identity_block, grounding_capsule, grounding_projection, active member, NOW, affect, conscience, and SessionState rendered blocks.
Document which blocks are required for final answer voice and which are only cognitive update hints.
Remove mutation chores from Front prompt only after replacement situation frame is present.
```

Current code trace checkpoint, 2026-05-26:

```text
Browser/device source chain:
   ui/web/static/app.js _browserDeviceContext
      sends timezone, locale, surface, profile_timezone, profile_location, browser geolocation status/fix
   ui/web/app.py _handle_user_message and device_context websocket branch
      forwards device_context before each user turn and on explicit device_context messages
   ui/web/coordinator.py _record_device_context
      writes DeviceContextSnapshot to KernelService.device_context_port
   k1/kernel/service.py S2.7/S2.8
      wires the same InMemoryDeviceContextPort into Temporal and Spatial bundles

Kernel/session source chain:
   k1/kernel/service.py S2.6/S2.7/S2.8/S2.9
      builds SelfModel, Temporal, Spatial, and Grounding service bundles
   k1/kernel/service.py P3.5/P3.6/P3.7/P3.8
      builds per-session SelfModelHandle, TemporalHandle, SpatialHandle, and GroundingHandle
   k1/concierge/factory.py _construct_concierge
      passes temporal/spatial/grounding through PortBundle and calls runtime setters before start
   k1/kernel/service.py P3.5 pre-start install
      installs SelfModel policy gate and attaches SelfModelHandle to ConciergeRuntime
   k1/concierge/session.py _front_consumer
      calls front_handler with temporal, spatial, grounding, self_model, and opp_pipeline

Front handler prompt source chain:
   k1/concierge/actors/front.py front_handler
      resolves PromptMode from FSM state, event topic, clarification/task/affect state, and routing metadata
      reads affective_now for affect band and tool/filter decisions
      builds scenario_data by mode from envelope payload and SessionState
      refreshes grounding for the turn and builds the Front GroundingProjection
      builds chat messages from history_active plus current/event turn text
      calls OppPipeline.on_pre_prompt_build for compressed_context and identity_block
      calls self_model.render_capsule for the SelfModel GroundingCapsule
      calls DynamicPromptBuilder.build with ss, scenario_data, grounding_capsule, grounding_projection

DynamicPromptBuilder prompt assembly chain:
   Stage 0 strips compressed_context and identity_block out of scenario_data
      so neither leaks through generic scenario formatting
   Stage 1-7 add mode sections, examples, affect/domain/depth blocks, anti-patterns, and scenario template data
   Stage 8 reads SessionState sections per SS_READ_CONFIGS; temporal is intentionally filtered out
      if compressed_context exists, history_active is omitted and compressed_context replaces it
   Stage 9.5 promotes live situation-frame blocks directly after IDENTITY:
      active member from GroundingCapsule self_block + space_graph_block
      NOW/PLACE from GroundingProjection render_now_block/render_place_block
      fallback NOW from temporal SessionState only if GroundingProjection rendering is absent
      AFFECT STATE from affect band/modifiers plus affective_now raw fields
      CONSCIENCE from GroundingCapsule conscience_block
      identity_block after promoted live blocks
      REFERENCE PROFILE from remaining capsule preferences/hobbies/goals/routines/context/freshness
   Tool selection happens after prompt assembly through get_tool_allowlist and all_tool_schemas filtering.

Required situation-frame/read blocks:
   IDENTITY grounding protocol and output identity boundaries
   ACTIVE MEMBER [self]/[space]
   NOW and PLACE
   AFFECT STATE plus affective_now SessionState renderer
   CONSCIENCE
   REFERENCE PROFILE capsule body
   SessionState projections: beliefs_active, scoreboard, clarifications, narrative_active, control,
      persona, task_state, task_artifacts, history_active or compressed_context depending on mode/input
   scenario templates for task result, weave, HITL, error, cancel, active member, and async result context
   chat messages from history_active plus current/event turn text

Cognitive write chores/hints, not grounding sources:
   REACT_RHYTHM and REACT_RHYTHM_REDUCED tool-loop write instructions
   COGNITIVE_DISCIPLINE and COGNITIVE_DISCIPLINE_REDUCED
   COMMITMENT_TRACKING update_scoreboard instructions
   MODE_EXAMPLES that demonstrate update_beliefs/update_scoreboard/update_clarifications/update_narrative
   prompt.mode TOOL_ALLOWLIST cognitive entries
   tools.schemas_front cognitive schemas and tools.implementations cognitive writer handlers
```

Trace conclusion:

```text
Current situation-frame blocks are not coupled to Front tool schema visibility.
The builder receives grounding_capsule, grounding_projection, ss, compressed_context, and identity_block
as prompt inputs before _select_tools filters the actual model tool surface.

Therefore M4.I6-I8 can remove cognitive write instructions/allowlist entries without deleting:
   active member grounding
   temporal/spatial NOW and PLACE grounding
   affect/conscience grounding
   SessionState read projection
   compressed conversation context
   dynamic identity overlay

Do not delete or collapse the read/projection inputs during cognitive tool removal.
```

Acceptance:

```text
Front prompt still contains temporal grounding, active member grounding, affect/conscience grounding, and relevant SessionState projection.
No required grounding source is coupled to cognitive write tool visibility.
Prompt snapshot tests can detect accidental removal of core situation frame blocks.
```

Targeted tests:

```powershell
pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m6_e3_dynamic_identity.py tests/k1/concierge/actors/test_front_spatial_projection.py -v
pytest tests/k1/concierge/prompt/test_builder_grounding.py -v
```

#### M4.I6 Write The Formal Front Prompt Modification Contract

Core concept: replace “write cognitive state through tools” instructions with “consume state projection and answer/route correctly.”

Issue context:

```text
old prompt posture
   |
   v
Front answers + updates hidden cognitive state

new prompt posture
   |
   v
Front answers / clarifies / routes / reads memory
   |
   v
classifier handles hidden cognitive updates after the turn
```

What this prevents:

```text
M4.I6 prevents prompt text from reintroducing the exact cognitive chores that the architecture moved to the classifier.
```

Code boundaries:

```text
k1/concierge/prompt/sections.py COGNITIVE_DISCIPLINE
k1/concierge/prompt/sections.py REACT_RHYTHM and REACT_RHYTHM_REDUCED
k1/concierge/prompt/sections.py COMMITMENT_TRACKING, INTERRUPT_RULES, ANTI_PATTERNS_FULL, MODE_EXAMPLES
k1/concierge/prompt/mode.py TOOL_ALLOWLIST and conditional refine_affect/promote_belief
k1/concierge/prompt/builder.py prompt assembly
whiteboard_front_deloading.md Front prompt contract sections
```

M4.I6 implementation boundary, 2026-05-26:

```text
Do not create a new prompt version or a parallel front_prompt_contract.md for M4.I6.
Modify the existing whiteboard_front_deloading.md Iteration 1 target prompt and
Actual Iteration 1 prompt only.

M4.I5 current Front prompt sources read before writing the contract:
   SelfModel/GroundingCapsule active actor, visible space, conscience, reference profile
   GroundingProjection NOW and PLACE rendered before tool selection
   SessionState read projections from DynamicPromptBuilder SS_READ_CONFIGS
   OPP compressed_context replacing history_active when present
   OPP dynamic identity block appended after promoted live blocks
   scenario_data/current event and chat history
   Front tool selection after prompt assembly

Runtime sections.py still contains old cognitive write instructions until M4.I7/M4.I8.
M4.I6 locks the replacement contract; it does not remove runtime allowlists or schemas.
```

Formal Front prompt contract:

```text
Front may:
- answer naturally in the family-facing voice
- ask clarifying questions
- call recall_memory
- call summarize_context
- call dispatch_task
- call discover_capabilities
- call allowed safe invoke_capability
- use rendered situation-frame blocks for grounding

Front must not:
- call or request SessionState cognitive writes
- mutate beliefs_active, scoreboard, clarifications, narrative_active, or affective_now
- invent missing state when the situation frame does not contain it
- treat classifier diagnostics as user-visible text
- perform task routing through cognitive state writes

Front receives:
- final user turn and recent history context
- NOW/time and device/session metadata
- active member / SelfModel projection
- affect and conscience projection
- SessionState cognitive projections rendered by runtime
- dispatch specs and capability context when present
```

Acceptance:

```text
No Iteration 1 contract prompt text instructs Front to call update_beliefs, update_scoreboard, update_clarifications, update_narrative, refine_affect, promote_belief, or update_session_bundle.
Prompt still explicitly tells Front how to answer, clarify, dispatch, and use memory read tools.
Prompt does not imply the classifier is user-visible.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_front_prompt_contract.py -v
```

#### M4.I7 Remove Cognitive Write Tools From Front Mode Allowlists

Core concept: hide write tools from deloaded Front contexts once the background worker path is wired and observable.

Issue context:

```text
Front active tool context after cutover
   |
   +--> keep recall_memory
   +--> keep summarize_context
   +--> keep dispatch_task
   +--> keep discover_capabilities
   +--> keep invoke_capability where safe
   |
   +--> hide update_beliefs
   +--> hide update_scoreboard
   +--> hide update_clarifications
   +--> hide update_narrative
   +--> hide refine_affect
   +--> hide promote_belief
```

What this prevents:

```text
M4.I7 prevents Front from continuing to own cognitive writes after the background updater becomes the hidden owner, while preserving the tools Front still needs to do its actual job.
```

Code boundaries:

```text
k1/concierge/prompt/mode.py TOOL_ALLOWLIST and conditional mode additions
k1/concierge/prompt/builder.py _select_tools
k1/concierge/tools/schemas_front.py
```

Remove from Front-visible active allowlists:

```text
update_beliefs
update_scoreboard
update_clarifications
update_narrative
refine_affect
promote_belief
```

Affected Front modes to verify:

```text
STANDARD
CLARIFY_ASK
CLARIFY_RESOLVE
HITL_RESOLVE
PRESENT
WEAVE
CANCEL
INTERRUPT
ERROR
```

Retain visible Front tools:

```text
recall_memory
summarize_context
dispatch_task
discover_capabilities
invoke_capability
```

Acceptance:

```text
Active Front tool context contains no cognitive write tools.
Dispatch/capability/memory-read tools remain available where previously allowed.
Disabled/rollback mode can restore the old allowlist without code deletion.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_front_tool_allowlist_cutover.py -v
```

#### M4.I8 Rewrite Prompt Sections That Instruct Cognitive Tool Use

Core concept: revise the prompt wording so Front is no longer responsible for deciding or narrating hidden cognitive updates.

Issue context:

```text
COGNITIVE_DISCIPLINE before cutover
   |
   v
instructions to maintain/update hidden state

COGNITIVE_DISCIPLINE after cutover
   |
   v
instructions to consume rendered state and avoid hidden writes
```

What this prevents:

```text
M4.I8 prevents a confusing state where the tools are hidden but the prompt still tells Front to perform hidden update work.
```

Code boundaries:

```text
k1/concierge/prompt/sections.py
k1/concierge/prompt/builder.py
poc/front_prompt_compare/compare_front_prompts.py
```

Implementation notes:

```text
Rewrite COGNITIVE_DISCIPLINE from a tool-calling instruction into a state-consumption instruction.
Remove phrasing that asks Front to update, promote, refine, or maintain cognitive state.
Keep instructions for final answer quality, clarification, dispatch, capability discovery, and memory recall.
Preserve the shorter Iteration 1 prompt posture measured in M0 as the target direction.
```

Acceptance:

```text
Prompt text contains no cognitive write tool names in deloaded Front mode.
Prompt text contains no hidden update todo list for Front.
Prompt compare still runs without runtime errors.
```

Targeted validation:

```powershell
pytest tests/k1/concierge/section_update/test_front_prompt_contract.py -v
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
```

#### M4.I9 Preserve Cognitive Schemas Temporarily For Rollback/Internal Comparison

Core concept: hide Front-visible cognitive tools without deleting schemas or implementations.

Issue context:

```text
cognitive schemas and implementations
   |
   +--> remain registered in code
   +--> remain callable for rollback/internal tests
   +--> remain named in comparison manifests
   |
   v
mode/allowlist gates decide Front visibility
```

What this prevents:

```text
M4.I9 prevents the migration from becoming irreversible. Rollback should be a flag transition, not a code resurrection.
```

Code boundaries:

```text
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
k1/concierge/prompt/mode.py
k1/concierge/section_update/lifecycle.py
```

Rollback preservation strategy:

```text
Keep cognitive schemas registered in code.
Keep update_session_bundle and old cognitive implementations intact.
Hide tools through mode/allowlist gating only.
Keep shadow/internal comparison able to reference old tool names in manifests.
Rollback flips K1_FRONT_DELOAD_COGNITIVE_TOOLS=false or equivalent and restores prior Front visible tools.
```

Acceptance:

```text
Schemas for old cognitive tools still import and validate.
Implementations still exist for rollback tests.
Active Front cannot see them when cutover flag is enabled.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_cognitive_schema_rollback_surface.py -v
```

#### M4.I10 Implement Iteration 1 Prompt Seating From The Formal Contract

Core concept: seat the deloaded prompt as the default cutover prompt shape once M3 gates pass and M4 allowlists are hidden.

Issue context:

```text
M0 no-cognitive prompt baseline
   |
   v
formal M4 prompt contract
   |
   v
Iteration 1 cutover prompt seating
   |
   +--> no visible cognitive write tools
   +--> situation frame still present
   +--> dispatch and response behavior preserved
   |
   v
prompt compare and targeted prompt tests
```

What this prevents:

```text
M4.I10 prevents the deloaded prompt from being a vague shorter prompt. It must be the measured baseline plus the formal situation-frame contract.
```

Code boundaries:

```text
k1/concierge/prompt/sections.py
k1/concierge/prompt/builder.py
k1/concierge/prompt/mode.py
poc/front_prompt_compare/compare_front_prompts.py
poc/front_prompt_compare/runs/20260521_150501/summary.md
```

Implementation notes:

```text
Use the M0 no-cognitive baseline as the prompt-size and tool-surface comparison anchor.
Keep output behavior focused on final response, clarification, dispatch, and capability use.
Do not make classifier mechanics visible to the user.
Do not add a new prompt section that reintroduces hidden cognitive chores.
```

Acceptance:

```text
Iteration 1 prompt seating exposes no cognitive write tools.
Prompt includes the required situation frame.
Front dispatch metadata still propagates.
Front final response tests remain targeted and green.
```

Targeted tests:

```powershell
pytest tests/k1/concierge/section_update/test_front_tool_allowlist_cutover.py tests/k1/concierge/section_update/test_front_prompt_contract.py -v
pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m6_e3_dynamic_identity.py tests/k1/concierge/actors/test_front_spatial_projection.py -v
```

M4 blockers and risks:

```text
M4 should not proceed from unknown classifier quality, but it does not wait for a separate active-mode gate.
Commitment tracking semantics currently flow through update_scoreboard; classifier must own equivalent behavior before cutover.
Prompt grounding regressions can make Front feel less situated even if classifier writes are correct.
Deleting schemas instead of hiding allowlists would break rollback; preserve schemas and implementations.
Background updater failure must degrade to diagnostic no-op, not user-visible turn failure.
```

### M5 Detailed Plan: Final Validation, Rollback Proof, And Cutover

Epic: prove the Front-deloading cutover is reversible, observable, and practical: Front no longer sees cognitive write tools by default, the background updater owns hidden cognitive writes through writer_port, failures degrade to diagnostics/no-op, and rollback restores the current Front tool contract without deleting schemas or implementations.

M5 operating picture:

```text
M5 is the release proof, not a new design phase.

contract tests
   |
prompt/lifecycle regressions
   |
old-test reconciliation
   |
POC dry/live evidence
   |
rollback flag matrix
   |
   v
cutover decision
   |
   +--> pass: background-updater deload / cutover record
   |
   +--> fail: shadow/degraded only or rollback
```

M5 drift guard:

```text
Do not run broad suites to compensate for unclear evidence.
Do not declare hidden cognitive write ownership complete while M3 gates fail.
Do not update legacy tests to hide rollback regressions.
Do not waive schema/guard validity or forbidden-section/op gates.
```

M5 release posture:

```text
No full kernel suite.
No full Fabric suite.
Run only targeted contract, prompt, lifecycle, writer, POC, and rollback validation.
If M3 gates are not green, final state is diagnostic-only background work or rollback, not completed deload cutover.
```

#### M5.I1 Define The Working-Tracker Dashboard/Report From section_update.completed And turn.completed

Core concept: after M4 builds the floors, M5 proves the building is standing by tracking the integrated path turn by turn. This is not a broad test sweep; it is evidence from the exact event and lifecycle surfaces M4 wires.

Source surfaces read for this issue:

```text
k1/concierge/fsm/controller.py _emit_turn_completed
   publishes k1.session.turn.completed.v1 with turn_id, session_id, cognitive_trace_id,
   user_message, assistant_response, timestamp_ms, and turn_number.

k1/concierge/section_update/events.py
   builds section_update.requested/completed payloads with status, plan, compile,
   writer_summary, diagnostics, and elapsed_ms.

k1/concierge/bus/topics.py
   TOPIC_TURN_COMPLETED, TOPIC_SECTION_UPDATE_REQUESTED, TOPIC_SECTION_UPDATE_COMPLETED.

k1/kernel/service.py health_check and lifecycle logs
   source for worker alive/stopped, P5.5 lifecycle, and per-session health summary.
```

Tracker report shape:

```text
For each session_id:
   mode
   worker_running
   queue_depth
   last_turn_id_seen
   last_turn_id_completed
   turn_completed_count
   section_update_requested_count
   section_update_completed_count
   missing_completion_count
   applied_count
   shadow_noop_count
   degraded_noop_count
   provider_failed_count
   timed_out_count
   rejected_count
   stale_count
   duplicate_count
   writer_rejected_count
   writer_failed_count
   p50/p95 classifier_elapsed_ms
   p50/p95 end_to_end_worker_elapsed_ms
```

Per-turn evidence row:

```text
turn_id
session_id
cognitive_trace_id
turn_number
prompt_mode if available
fsm_state if available
section_update_mode
provider_id
model_id
status
mutation_count
rejected_candidate_count
plan_id
plan_idempotency_key
snapshot_version
snapshot_source_epoch
diagnostic_codes
writer_summary section/operation counts
```

What to look for while validating:

```text
Every turn.completed has either a matching section_update.completed or an intentional mode=off reason.
No background_apply turn lacks a terminal status.
No provider/schema/guard failure reaches writer_port.
No cognitive tool appears in the deloaded Front tool context.
No user-visible answer includes classifier mechanics or diagnostics.
Rollback mode restores old Front-visible cognitive tools and disables background writer calls.
```

Acceptance:

```text
M5 has a report artifact path, not just console logs.
Report distinguishes Front deload failures from classifier quality failures.
Report can prove 0 cognitive Front tool calls and 0 unsafe writer calls for selected validation turns.
Report records whether the full M3 100-case v5 corpus was rerun or deliberately reused.
```

Targeted tests/probes to create or update:

```powershell
pytest tests/k1/concierge/section_update/test_worker_observability.py -v
pytest tests/k1/concierge/section_update/test_front_no_cognitive_tool_calls.py -v
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
```

#### M5.I2 Run Targeted Classifier, Kernel Wiring, Prompt, Front, And Rollback Tests

Core concept: prove M1-M4 classifier contract, compiler, kernel lifecycle, prompt, Front tool visibility, and rollback behavior with narrow tests.

Issue context:

```text
classifier release fence
   |
   +--> schema/type tests
   +--> vocabulary tests
   +--> compiler tests
   +--> idempotency tests
   +--> stub tests
   +--> quality gate tests
   |
   v
eligible for lifecycle/prompt release checks
```

What this prevents:

```text
M5.I2 prevents release validation from skipping the core contract and relying only on end-to-end happy paths.
```

Code boundaries:

```text
k1/concierge/section_update/types.py
k1/concierge/section_update/vocabulary.py
k1/concierge/section_update/plan_compiler.py
k1/concierge/section_update/idempotency.py
k1/concierge/section_update/classifier.py
k1/concierge/section_update/lifecycle.py
k1/concierge/section_update/quality_gates.py
k1/sessionstate/guard.py
k1/sessionstate/ports/writer.py
k1/sessionstate/adapters/direct_writer.py
```

Acceptance:

```text
Schema/type validation is deterministic.
Invalid section/op rejects before writer_port.
Whole-plan validation prevents partial dependent background apply.
Idempotency prevents duplicate writes.
Quality gates block completed hidden-write ownership when evidence is missing or failing.
```

Targeted command:

```powershell
pytest tests/k1/concierge/section_update/test_plan_schema.py tests/k1/concierge/section_update/test_operation_vocabulary.py tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py tests/k1/concierge/section_update/test_classifier_stub.py tests/k1/concierge/section_update/test_quality_gates.py -v
pytest tests/k1/sessionstate/test_guard.py -k "valid_operations or invalid_operation" -v
```

##### M5.I2 Runtime Regression Pack: Front, Prompt, And Concierge

Core concept: prove M2/M4 lifecycle and Front cutover behavior without broad suites.

Issue context:

```text
changed runtime surfaces
   |
   +--> turn input builder
   +--> section-update lifecycle events
   +--> background apply/degrade ordering
   +--> Back overlay/gating
   +--> Front prompt contract
   +--> Front tool allowlist
   |
   v
targeted regression pack
```

What this prevents:

```text
M5.I2 prevents a cutover that passes classifier tests but breaks the actual Concierge turn ordering or Front prompt contract.
```

Code boundaries:

```text
k1/concierge/fsm/controller.py
k1/concierge/actors/front.py
k1/concierge/actors/back.py
k1/concierge/prompt/mode.py
k1/concierge/prompt/builder.py
k1/concierge/prompt/sections.py
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
```

Acceptance:

```text
Background apply either writes accepted mutations or emits diagnostic no-op without failing the user-visible turn.
Shadow mode never mutates SessionState.
Front prompt still receives grounding blocks.
Front deloaded tool context omits cognitive write tools only when deload flag is active.
Back dispatch-critical overlay/gating behavior is explicit and tested.
```

Targeted command:

```powershell
pytest tests/k1/concierge/section_update/test_turn_input_builder.py tests/k1/concierge/section_update/test_classifier_turn_boundary.py tests/k1/concierge/section_update/test_background_apply.py tests/k1/concierge/section_update/test_turn_completed_coordination.py tests/k1/concierge/section_update/test_dispatch_overlay.py tests/k1/concierge/section_update/test_back_snapshot_gating.py -v
pytest tests/k1/concierge/section_update/test_front_tool_allowlist_cutover.py tests/k1/concierge/section_update/test_front_prompt_contract.py tests/k1/concierge/section_update/test_cognitive_schema_rollback_surface.py -v
pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m6_e3_dynamic_identity.py tests/k1/concierge/actors/test_front_spatial_projection.py -v
```

#### M5.I3 Update Old Tests That Assume Cognitive Tools Are Front-Visible Tools

Core concept: legacy tests should distinguish rollback-callable schemas from Front-visible tools.

Issue context:

```text
old test assumption
   |
   v
"cognitive tool exists" == "Front can see it"

new test split
   |
   +--> schema exists
   +--> implementation callable for rollback/internal paths
   +--> active Front allowlist hides write tools
   +--> rollback flag restores visibility
```

What this prevents:

```text
M5.I3 prevents tests from forcing the old architecture back into the prompt while still protecting rollback behavior.
```

Code boundaries:

```text
tests/k1/concierge/test_m04_e43_session_bundle.py
tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py
tests/k1/concierge/test_m03_e34_parallel_safety.py
tests/k1/concierge/test_m03_e36_conformance.py
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
k1/concierge/prompt/mode.py
```

Old-test update strategy:

```text
Replace assertions that cognitive write tools must always be Front-visible.
Assert schemas still exist and validate.
Assert implementations remain callable through rollback/internal paths.
Assert active deloaded Front allowlist hides cognitive write tools.
Assert rollback flag restores prior Front-visible allowlist.
```

Acceptance:

```text
Tests no longer encode permanent Front exposure of cognitive write tools.
Tests still protect rollback and writer-path behavior.
Tests prove update_session_bundle remains available for rollback/internal comparison.
```

Targeted command:

```powershell
pytest tests/k1/concierge/test_m04_e43_session_bundle.py tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py tests/k1/concierge/test_m03_e34_parallel_safety.py tests/k1/concierge/test_m03_e36_conformance.py -v
```

#### M5.I4 Rerun POC Dry And Selected Live Cases

Core concept: produce final evidence artifacts for classifier shape, model latency/quality, and prompt deload behavior.

Issue context:

```text
final evidence refresh
   |
   +--> dry classifier batch run
   +--> selected live Vertex batch run
   +--> prompt compare dry run
   |
   v
artifact paths recorded in cutover decision
```

What this prevents:

```text
M5.I4 prevents final cutover from relying on stale POC evidence or on the accidental wrong-provider run noted in M0.
```

Code and artifact boundaries:

```text
poc/section_update_classifier_poc.py
poc/section_update_classifier_cases.json
poc/section_update_classifier_runs/
poc/front_prompt_compare/compare_front_prompts.py
poc/front_prompt_compare/runs/20260521_150501/summary.md
```

Acceptance:

```text
Dry classifier run passes schema/validation checks for golden cases.
Selected live Vertex run records provider/model identity, validation pass rate, model latency, and E2E latency.
Prompt compare dry run records no cognitive tool exposure and no runtime errors.
If live pass rate remains below M3 gates, completed hidden-write ownership is blocked or explicitly waived.
```

Targeted commands:

```powershell
python .\poc\section_update_classifier_poc.py --mode batch
$env:LLM_PROVIDER='vertex'
$env:GOOGLE_GENAI_USE_VERTEXAI='True'
$env:VERTEX_MODEL='gemini-2.5-flash-lite'
$env:K1_SECTION_UPDATE_MODEL='gemini-2.5-flash-lite'
python .\poc\section_update_classifier_poc.py --live --mode batch --preferred-provider vertex --preferred-model gemini-2.5-flash-lite --temperature 0 --timeout-ms 45000 --max-output-tokens 2048
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
```

#### M5.I5 Prove Rollback Flags Restore The Previous Front Cognitive Tool Path

Core concept: rollback must be a flag/config transition, not a schema or code resurrection exercise.

Issue context:

```text
runtime state matrix
   |
   +--> rollback/current: Front tools visible, classifier inactive
   +--> shadow: Front tools hidden/transitional, manifests only
   +--> degraded_noop: diagnostics only
   +--> background_apply: fail-closed writer_port apply after completed turn
   +--> offline_stub: deterministic tests
   |
   v
same codebase can move between states without schema deletion
```

What this prevents:

```text
M5.I5 prevents the release from becoming one-way. If background updater deload misbehaves, the old Front-visible cognitive path must still be restorable.
```

Code boundaries:

```text
k1/concierge/prompt/mode.py
k1/concierge/prompt/builder.py
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
k1/concierge/section_update/lifecycle.py
```

Flag matrix:

| State | `K1_FRONT_DELOAD_COGNITIVE_TOOLS` | `K1_SECTION_UPDATE_MODE` | Expected behavior |
| --- | --- | --- | --- |
| Rollback/current | `0` | `off` or disabled | Front-visible cognitive tools restored; classifier inactive. |
| Shadow deload | `1` | `shadow` | Front hides cognitive tools; classifier manifests only; no writer calls. |
| Degraded no-op | `1` | `degraded_noop` | Front hides cognitive tools; classifier emits diagnostics; no writer calls. |
| Background apply | `1` | `background_apply` | Front hides cognitive tools; accepted classifier mutations apply through writer_port; failures emit diagnostic no-op. |
| Offline tests | either | `offline_stub` | Deterministic stub only; no live provider dependency. |

Rollback proof checklist:

```text
Cognitive schemas import and validate.
Cognitive implementations still exist.
Rollback/current flags expose old tools to Front.
Deload flags hide old tools from Front.
update_session_bundle rollback/internal path remains callable.
Switching out of background_apply prevents writer calls from classifier lifecycle.
```

Targeted command:

```powershell
pytest tests/k1/concierge/section_update/test_feature_flags.py tests/k1/concierge/section_update/test_cognitive_schema_rollback_surface.py tests/k1/concierge/section_update/test_front_tool_allowlist_cutover.py -v
pytest tests/k1/concierge/test_m04_e42_write_path.py tests/k1/concierge/test_m04_e43_session_bundle.py -v
```

#### M5.I6 Declare Cutover Only After Final Criteria Pass Or Have Explicit Waivers

Core concept: make the release decision mechanical and evidence-backed.

Issue context:

```text
cutover decision record
   |
   +--> targeted test results
   +--> quality gate report
   +--> live/dry POC artifacts
   +--> prompt compare artifacts
   +--> rollback flag proof
   +--> known waivers, if any
   |
   v
decision: background_apply / shadow-only / degraded / rollback
```

What this prevents:

```text
M5.I6 prevents a vague release call. The system either has evidence for background-updater deload or it explicitly ships shadow/degraded/rollback behavior.
```

Final cutover criteria:

```text
All M1-M5 targeted tests pass.
M3 numeric gates pass from manifest/golden evidence.
Selected live classifier run meets provider, latency, and quality gates.
Prompt compare shows no cognitive tool exposure and no runtime errors.
Rollback flag matrix passes.
No high-risk shadow mismatch remains untriaged.
No dangerous false writes are observed in the required shadow window.
```

Waiver rules:

```text
Background hidden-write ownership cannot be globally waived while quality gates fail.
Per-session or per-environment background_apply waiver requires rollback proof, manifest logging, and explicit owner signoff.
Latency waiver cannot remove timeout/degraded-noop behavior.
Schema/guard validity and forbidden-section/op gates are not waivable.
```

Acceptance:

```text
Cutover record names evidence artifact paths, command outputs, provider/model ID, flags, and known waivers.
If criteria fail, ship shadow/degraded deload only or roll back to current Front cognitive tools.
```

Final targeted validation command list:

```powershell
pytest tests/k1/concierge/section_update/test_plan_schema.py tests/k1/concierge/section_update/test_operation_vocabulary.py tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py tests/k1/concierge/section_update/test_classifier_stub.py tests/k1/concierge/section_update/test_quality_gates.py -v
pytest tests/k1/concierge/section_update/test_turn_input_builder.py tests/k1/concierge/section_update/test_classifier_turn_boundary.py tests/k1/concierge/section_update/test_background_apply.py tests/k1/concierge/section_update/test_turn_completed_coordination.py tests/k1/concierge/section_update/test_dispatch_overlay.py tests/k1/concierge/section_update/test_back_snapshot_gating.py -v
pytest tests/k1/concierge/section_update/test_front_tool_allowlist_cutover.py tests/k1/concierge/section_update/test_front_prompt_contract.py tests/k1/concierge/section_update/test_cognitive_schema_rollback_surface.py tests/k1/concierge/section_update/test_feature_flags.py -v
pytest tests/k1/sessionstate/test_guard.py -k "valid_operations or invalid_operation" -v
pytest tests/k1/concierge/test_m04_e42_write_path.py tests/k1/concierge/test_m04_e43_session_bundle.py tests/k1/concierge/test_m04_e44_prompt_ss.py -v
pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m6_e3_dynamic_identity.py tests/k1/concierge/actors/test_front_spatial_projection.py -v
pytest tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py tests/k1/concierge/test_m03_e34_parallel_safety.py tests/k1/concierge/test_m03_e36_conformance.py -v
python .\poc\section_update_classifier_poc.py --mode batch
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
```

M5 blockers and risks:

```text
Full-corpus classifier quality is not yet green until the v5 100-case rerun proves the repaired guardrails.
Operation vocabulary must remain exactly aligned with MutationGuard and section apply surfaces.
Batch writer semantics are not transactional, so whole-plan validation proof is release-critical.
Legacy tests may need careful rewriting to protect rollback instead of preserving old Front-visible behavior.
```

### M6 Detailed Plan: Steady-State Cutover And Cleanup

Epic: once M5 proves the integrated background-updater/no-cognitive-Front path, move from migration mode to steady state. M6 is cleanup after evidence, not a prerequisite for M4 or M5 integration work.

M6 operating picture:

```text
M5 cutover record
    |
    +--> background updater healthy
    +--> Front deloaded tool context stable
    +--> rollback proof exists
    +--> quality evidence accepted or waived
    |
    v
steady-state decision
    |
    +--> keep rollback if stability evidence is not enough
    +--> remove obsolete Front cognitive surfaces only after M6 gates
    |
    v
locked runbook + monitoring + cleanup commit list
```

M6 drift guard:

```text
Do not delete rollback surfaces during M4 or M5.
Do not require M6 cleanup before integrated M4/M5 validation.
Do not remove diagnostic shadow mode; keep it for future model/prompt regressions.
Do not run broad kernel/fabric suites as the definition of M6 safety.
Do not delete update_session_bundle or any internal schema until a separate audit proves it is not used for rollback/internal tools.
```

#### M6.I1 Define The Stability Window And Rollback-Removal Criteria

Core concept: remove migration scaffolding only after the integrated path has real evidence, not because the plan wants symmetry.

Stability evidence options:

```text
Minimum acceptable evidence before rollback removal:
   100 integrated validation turns with 0 dangerous false writes, or
   an explicitly named deployment/staging window with 0 rollback invocations and 0 unsafe writer calls, or
   an explicit owner waiver that keeps rollback surfaces instead of deleting them.

For no-user or pre-deployment environments:
   M6 cleanup can be deferred. M4/M5 completion may leave rollback flags and schemas intact.
```

Acceptance:

```text
Cutover record names the stability window, evidence artifact, and rollback decision.
Rollback removal is denied if M5 tracker has missing completions, unsafe writer calls, or unresolved high-risk mismatches.
If stability evidence is insufficient, M6 records "cleanup deferred" rather than forcing deletion.
```

#### M6.I2 Remove Obsolete Front Cognitive Schema/Implementation Surfaces Only After Gates

Core concept: deletion is the last floor. First hide, validate, and run with rollback; only then remove old Front cognitive write surfaces.

Deletion candidates to audit:

```text
k1/concierge/tools/schemas_front.py
   UPDATE_BELIEFS_SCHEMA
   UPDATE_SCOREBOARD_SCHEMA
   UPDATE_CLARIFICATIONS_SCHEMA
   UPDATE_NARRATIVE_SCHEMA
   REFINE_AFFECT_SCHEMA
   PROMOTE_BELIEF_SCHEMA
   FRONT_TOOL_SCHEMAS cognitive entries

k1/concierge/tools/implementations.py
   execute_update_beliefs
   execute_update_scoreboard
   execute_update_clarifications
   execute_update_narrative
   execute_refine_affect
   execute_promote_belief

k1/concierge/tools/parallelism.py
   cognitive write grouping assumptions

k1/concierge/protocols/hitl_wiring.py
   HITL_RESOLVE assumptions that update_beliefs is Front-visible
```

Keep until separately audited:

```text
update_session_bundle
internal writer contracts
section_update classifier schemas
MutationGuard operation vocabulary
rollback evidence reports
shadow/diagnostic event builders
```

Acceptance:

```text
No deloaded Front mode references deleted tool names.
No tests require the deleted tools to be Front-visible.
Rollback removal is documented; if rollback must remain, schemas stay hidden but present.
```

#### M6.I3 Collapse Feature Flags From Migration Toggles To Steady-State Controls

Core concept: migration flags should not become permanent ambiguity. After M6 gates, the default path is background updater ownership; diagnostics and model knobs remain.

Flag disposition:

```text
front_deload_cognitive_tools:
   migration flag; collapse to true/default-on after rollback removal.

section_update_enabled:
   migration flag; collapse to true/default-on only after M6 gates.

section_update_mode:
   keep as operational control with allowed values background_apply, shadow, degraded_noop, off.
   off remains an incident rollback until old Front cognitive surfaces are deleted; after deletion, off means no hidden cognitive writes.

section_update_provider / section_update_model:
   keep as model routing knobs for future provider swaps.

section_update_shadow_only or equivalent:
   keep for diagnostics/comparison after model or prompt changes.
```

Acceptance:

```text
Config defaults express the steady-state path clearly.
Operators can still force shadow/degraded_noop for incident investigation.
No flag combination exposes cognitive write tools to Front after rollback surfaces are removed.
```

#### M6.I4 Lock Prompt Contracts, Runbooks, And Evidence Artifacts

Core concept: after cleanup, future contributors should not accidentally rebuild the old Front cognitive tool posture.

Artifacts to lock:

```text
docs/architecture/front_prompt_contract.md
docs/architecture/front_prompt_grounding_sources.md
docs/runbooks/section_update_background_worker.md
data/m3_section_update_*_report.json evidence references
M5 cutover/working-tracker report path
```

Runbook must include:

```text
How to identify provider_failed vs writer_rejected vs forbidden target.
How to switch to shadow/degraded_noop.
How to rerun the focused repair subset and full 100-case corpus.
How to verify Front tool context has no cognitive write tools.
How to decide whether rollback removal is still safe.
```

Acceptance:

```text
Docs name the background updater as the hidden cognitive writer.
Docs say Front consumes situation frame and does not write cognitive SessionState.
Docs say Back is not the classifier owner.
Docs keep spatial/grounding skeleton caveats accurate.
```

#### M6.I5 Keep Targeted Validation Discipline

Core concept: M6 cleanup should be proven by the surfaces it touches. Do not replace precision with a broad suite.

Targeted validation after cleanup:

```powershell
pytest tests/k1/concierge/section_update/test_background_apply.py tests/k1/concierge/section_update/test_worker_observability.py -v
pytest tests/k1/concierge/section_update/test_front_tool_allowlist_cutover.py tests/k1/concierge/section_update/test_front_prompt_contract.py -v
pytest tests/k1/concierge/section_update/test_cognitive_schema_rollback_surface.py -v
pytest tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py tests/k1/concierge/test_m03_validator.py -v
pytest tests/k1/kernel/test_service.py -k "section_update_worker or session_instance" -v
```

Acceptance:

```text
Cleanup does not reintroduce Front cognitive tool visibility.
Background updater still emits requested/completed diagnostics.
Kernel session lifecycle still starts/stops cleanly with the worker enabled and disabled.
Rollback deletion or deferral is explicit in the cutover record.
```
