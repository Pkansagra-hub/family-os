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

### M3: Shadow Mode, Active Mode, And Quality Gates

Epic: run the classifier in shadow mode, then active mode, and prove mutation quality before removing Front cognitive tools.

Issue headings:

```text
M3.I1 Run shadow mode beside current Front cognitive tool writes.
M3.I2 Add mutation manifest observability if writer turn stats are too coarse.
M3.I3 Convert POC cases into golden SectionUpdatePlan expectations.
M3.I4 Validate provider/model choices, latency, and degradation behavior.
M3.I5 Enable active apply behind feature flags.
M3.I6 Enforce numeric mutation-quality gates.
```

### M4: Front Deload Cutover And Prompt Contract

Epic: after classifier active gates pass, remove cognitive write tools from Front and formalize the Front prompt situation-frame contract.

Issue headings:

```text
M4.I1 Trace current temporal, SelfModel, SessionState, and prompt grounding sources.
M4.I2 Write the formal Front prompt modification contract.
M4.I3 Remove cognitive write tools from Front mode allowlists.
M4.I4 Rewrite prompt sections that instruct cognitive tool use.
M4.I5 Preserve cognitive schemas temporarily for rollback/internal comparison.
M4.I6 Implement Iteration 1 prompt seating from the formal contract.
```

### M5: Final Validation, Rollback Proof, And Cutover

Epic: prove the full path with targeted tests, live/dry POC validation, old-test updates, and rollback proof.

Issue headings:

```text
M5.I1 Run targeted classifier contract suites.
M5.I2 Run targeted Front/prompt/Concierge regressions touched by the migration.
M5.I3 Update old tests that assume cognitive tools are Front-visible tools.
M5.I4 Rerun POC dry and selected live cases.
M5.I5 Prove rollback flags restore the previous Front cognitive tool path.
M5.I6 Declare cutover only after final criteria pass or have explicit waivers.
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

Acceptance:

```text
Baseline run directory is recorded in this plan.
Known response-wording misses are documented as prompt behavior, not classifier failure.
The baseline remains available for M3/M5 comparisons.
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
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
k1/sessionstate/config.py
k1/sessionstate/adapters/direct_writer.py
```

Current ownership boundary:

```text
Front currently owns cognitive writes through prompt-seated tools.
Target owner is SectionUpdateClassifier through writer_port.
control, task_state, task_artifacts, history, telemetry, and meta remain runtime/FSM-owned.
MemoryWriter reads SessionState and writes durable memory outside SessionState.
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
| `narrative_active` | `create_thread`, `switch_to`, `pause_thread`, `resolve_thread`, `archive_thread`, `update_thread`, `record_turn` | No major guard/apply mismatch found; still reject shorthand `switch`, `resume`, `close`. |
| `affective_now` | `update` | `update_emotion`, `update_dimensions`, `set_empathy_needed`, `set_celebration_appropriate` exist in `apply()` but fail `VALID_OPERATIONS`. |

Acceptance:

```text
Vocabulary registry is derived from the five LLM-writable sections only.
Compiler rejects `control`, `task_state`, `task_artifacts`, `history_active`, `telemetry`, `meta`, `persona`, and warm/archive sections.
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

### M3 Detailed Plan: Shadow Mode, Active Mode, And Quality Gates

Epic: run `SectionUpdateClassifier` in batch-only shadow mode beside existing Front cognitive writes, prove semantic equivalence and safety with per-turn manifests, then enable active apply behind flags only after numeric quality gates clear.

M3 operating picture:

```text
M3 is the proof ladder.

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
   +--> pass: allow active canary behind flags
```

M3 drift guard:

```text
Do not treat provider success as mutation quality.
Do not treat aggregate writer stats as semantic equivalence.
Do not remove Front cognitive tools in M3.
Do not allow active apply while the 16.7% baseline problem remains unresolved.
```

M3 non-negotiables from M0-M2:

```text
Current gemini-2.5-flash-lite pass rate is 16.7%, so it is shadow-only until gates pass.
Batch plan remains the only production V0 shape.
Parallel/by-section calls remain diagnostic and cannot drive active writes.
Front cognitive tools remain seated through M3 for comparison and rollback.
Active mode must obey M2 ordering: apply/degrade before turn.completed.
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
M3.I4 prevents accidental active writes from the wrong provider/model path or from malformed provider output.
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
Provider route mismatch blocks active apply.
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

#### M3.I5 Enable Active Apply Behind Feature Flags

Core concept: active writes are permitted only when the mode is explicit and M3 quality gates are satisfied.

Issue context:

```text
runtime flags + gate report
   |
   +--> disabled: current Front path
   +--> shadow: manifest only
   +--> degraded_noop: diagnostics only
   +--> offline_stub: deterministic tests
   +--> active + gates pass
            |
            v
         compile/apply before turn.completed
```

What this prevents:

```text
M3.I5 prevents active apply from becoming the accidental default just because the classifier package exists.
```

Code boundaries:

```text
k1/concierge/section_update/lifecycle.py
k1/concierge/section_update/apply.py
k1/concierge/section_update/plan_compiler.py
k1/sessionstate/ports/writer.py
k1/sessionstate/adapters/direct_writer.py
k1/concierge/fsm/controller.py _execute_response_final_decision
```

Feature flag behavior:

```text
K1_ENABLE_SECTION_UPDATE_CLASSIFIER=false -> disabled, current Front path unchanged
K1_SECTION_UPDATE_MODE=shadow -> classifier diagnostics only, no writer calls
K1_SECTION_UPDATE_MODE=active -> compile/apply before turn.completed if gates are satisfied
K1_SECTION_UPDATE_MODE=offline_stub -> deterministic test adapter only
K1_SECTION_UPDATE_MODE=degraded_noop -> no writer calls, emit diagnostics
```

Acceptance:

```text
Valid active plans call writer_port.batch_mutations exactly once.
Shadow, degraded, invalid, stale, duplicate, timed-out, and provider-failed plans call writer_port zero times.
Active mode closes with applied, no-op, rejected, stale, duplicate, timed-out, or provider-failed status before turn.completed.
Rollback to disabled/shadow does not require schema deletion.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_active_apply.py tests/k1/concierge/section_update/test_feature_flags.py -v
```

#### M3.I6 Enforce Numeric Mutation-Quality Gates

Core concept: active mode is blocked until measured quality exceeds the current POC baseline by a large, explicit margin.

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
active eligible? yes/no
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

Required active-mode gates:

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
100 consecutive shadow turns with 0 dangerous false writes before active canary
```

Latency and degradation gates:

```text
shadow p95 <= 10s
active boundary timeout <= 1500ms
provider failure/degradation rate <= 1% over validation window
timeout path always safe no-op
no same-turn retry loop
```

Acceptance:

```text
Quality gate evaluator can fail the build/test run from manifest summaries.
Active mode refuses to apply when gates are missing or failing.
Gate report records evidence artifact paths and provider/model identity.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_quality_gates.py -v
```

M3 blockers and risks:

```text
Current 16.7% Gemini 2.5 Flash Lite validation pass rate blocks active mode.
4-9 second live model latency is acceptable for shadow diagnostics but unsafe for synchronous active without timeout.
Existing writer summaries are aggregate; manifest work is required before quality claims are credible.
Batch apply is not transactional, so M1 whole-plan validation remains mandatory before any M3 active attempt.
M1 snapshot epoch/idempotency must be real before active stale rejection can be trusted.
```

### M4 Detailed Plan: Front Deload Cutover And Prompt Contract

Epic: after M3 gates pass, cut Front over from ReAct-owned cognitive writes to classifier-owned SessionState mutation, so Front becomes voice, clarification, presentation, memory read, and routing while `SectionUpdateClassifier` owns cognitive write intent for `beliefs_active`, `scoreboard`, `clarifications`, `narrative_active`, and `affective_now`.

M4 operating picture:

```text
M4 changes Front's job after evidence says it is safe.

M3 gates pass
   |
   v
Front prompt contract changes
   |
   +--> Front consumes situation frame
   +--> Front keeps memory-read / dispatch / capability tools
   +--> Front loses visible cognitive write tools
   |
   v
SectionUpdateClassifier owns hidden cognitive writes
   |
   v
old cognitive schemas remain hidden for rollback/internal comparison
```

M4 drift guard:

```text
Do not start M4 before M3 gates pass.
Do not delete cognitive schemas or implementations.
Do not remove recall, summary, dispatch, discovery, or safe capability tools from Front.
Do not make classifier mechanics visible to the user.
```

M4 start gate:

```text
Do not start M4 allowlist removal until M3 active-mode gates pass.
Do not delete cognitive schemas or implementations in M4.
Rollback must be able to restore old Front cognitive tool visibility by flag/config change.
```

#### M4.I1 Trace Current Temporal, SelfModel, SessionState, And Prompt Grounding Sources

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
M4.I1 prevents the cutover from making Front lighter but less situated.
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

Acceptance:

```text
Front prompt still contains temporal grounding, active member grounding, affect/conscience grounding, and relevant SessionState projection.
No required grounding source is coupled to cognitive write tool visibility.
Prompt snapshot tests can detect accidental removal of core situation frame blocks.
```

Targeted tests:

```powershell
pytest tests/k1/concierge/test_m6_e1_episodic_compression.py tests/k1/concierge/test_m6_e3_dynamic_identity.py tests/k1/concierge/actors/test_front_spatial_projection.py -v
```

#### M4.I2 Write The Formal Front Prompt Modification Contract

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
M4.I2 prevents prompt text from reintroducing the exact cognitive chores that the architecture moved to the classifier.
```

Code boundaries:

```text
k1/concierge/prompt/sections.py COGNITIVE_DISCIPLINE
k1/concierge/prompt/builder.py prompt assembly
whiteboard_front_deloading.md Front prompt contract sections
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
No prompt text instructs Front to call update_beliefs, update_scoreboard, update_clarifications, update_narrative, refine_affect, promote_belief, or update_session_bundle.
Prompt still explicitly tells Front how to answer, clarify, dispatch, and use memory read tools.
Prompt does not imply the classifier is user-visible.
```

Targeted test:

```powershell
pytest tests/k1/concierge/section_update/test_front_prompt_contract.py -v
```

#### M4.I3 Remove Cognitive Write Tools From Front Mode Allowlists

Core concept: hide write tools from active Front contexts only after M3 gates pass.

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
M4.I3 prevents Front from continuing to own cognitive writes after classifier active gates pass, while preserving the tools Front still needs to do its actual job.
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

#### M4.I4 Rewrite Prompt Sections That Instruct Cognitive Tool Use

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
M4.I4 prevents a confusing state where the tools are hidden but the prompt still tells Front to perform hidden update work.
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
Prompt text contains no cognitive write tool names in active cutover mode.
Prompt text contains no hidden update todo list for Front.
Prompt compare still runs without runtime errors.
```

Targeted validation:

```powershell
pytest tests/k1/concierge/section_update/test_front_prompt_contract.py -v
python .\poc\front_prompt_compare\compare_front_prompts.py --no-cognitive-tools --simulate-classifier --output-dir .\poc\front_prompt_compare\runs
```

#### M4.I5 Preserve Cognitive Schemas Temporarily For Rollback/Internal Comparison

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
M4.I5 prevents the migration from becoming irreversible. Rollback should be a flag transition, not a code resurrection.
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

#### M4.I6 Implement Iteration 1 Prompt Seating From The Formal Contract

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
M4.I6 prevents the deloaded prompt from being a vague shorter prompt. It must be the measured baseline plus the formal situation-frame contract.
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
M4 is blocked until M3 quality gates pass; otherwise cognitive tool removal would hide the only working write path.
Commitment tracking semantics currently flow through update_scoreboard; classifier must own equivalent behavior before cutover.
Prompt grounding regressions can make Front feel less situated even if classifier writes are correct.
Deleting schemas instead of hiding allowlists would break rollback; preserve schemas and implementations.
```

### M5 Detailed Plan: Final Validation, Rollback Proof, And Cutover

Epic: prove the Front-deloading cutover is reversible, observable, and safe: Front no longer sees cognitive write tools by default, SectionUpdate remains shadow-only until M3 gates pass, active apply is ordered before `turn.completed`, and rollback restores the current Front tool contract without deleting schemas or implementations.

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
   +--> pass: active canary / cutover record
   |
   +--> fail: shadow/degraded only or rollback
```

M5 drift guard:

```text
Do not run broad suites to compensate for unclear evidence.
Do not declare active cutover while M3 gates fail.
Do not update legacy tests to hide rollback regressions.
Do not waive schema/guard validity or forbidden-section/op gates.
```

M5 release posture:

```text
No full kernel suite.
No full Fabric suite.
Run only targeted contract, prompt, lifecycle, writer, POC, and rollback validation.
If M3 gates are not green, final state is shadow/degraded, not active cutover.
```

#### M5.I1 Run Targeted Classifier Contract Suites

Core concept: prove M1-M3 classifier contract, compiler, lifecycle, quality, and provider behavior with narrow tests.

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
M5.I1 prevents release validation from skipping the core contract and relying only on end-to-end happy paths.
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
Whole-plan validation prevents partial dependent active apply.
Idempotency prevents duplicate writes.
Quality gates block active mode when evidence is missing or failing.
```

Targeted command:

```powershell
pytest tests/k1/concierge/section_update/test_plan_schema.py tests/k1/concierge/section_update/test_operation_vocabulary.py tests/k1/concierge/section_update/test_plan_compiler.py tests/k1/concierge/section_update/test_idempotency.py tests/k1/concierge/section_update/test_classifier_stub.py tests/k1/concierge/section_update/test_quality_gates.py -v
pytest tests/k1/sessionstate/test_guard.py -k "valid_operations or invalid_operation" -v
```

#### M5.I2 Run Targeted Front, Prompt, And Concierge Regressions Touched By The Migration

Core concept: prove M2/M4 lifecycle and Front cutover behavior without broad suites.

Issue context:

```text
changed runtime surfaces
   |
   +--> turn input builder
   +--> section-update lifecycle events
   +--> active apply ordering
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
Active apply closes before turn.completed.
Shadow mode never mutates SessionState.
Front prompt still receives grounding blocks.
Front active tool context omits cognitive write tools only when deload flag is active.
Back dispatch-critical overlay/gating behavior is explicit and tested.
```

Targeted command:

```powershell
pytest tests/k1/concierge/section_update/test_turn_input_builder.py tests/k1/concierge/section_update/test_classifier_turn_boundary.py tests/k1/concierge/section_update/test_active_apply.py tests/k1/concierge/section_update/test_turn_completed_coordination.py tests/k1/concierge/section_update/test_dispatch_overlay.py tests/k1/concierge/section_update/test_back_snapshot_gating.py -v
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
If live pass rate remains below M3 gates, active cutover is blocked.
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
   +--> active canary: gated apply before turn.completed
   +--> offline_stub: deterministic tests
   |
   v
same codebase can move between states without schema deletion
```

What this prevents:

```text
M5.I5 prevents the release from becoming one-way. If active cutover misbehaves, the old Front-visible cognitive path must still be restorable.
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
| Active canary | `1` | `active` | Allowed only after M3 gates pass; apply/degrade before turn.completed. |
| Offline tests | either | `offline_stub` | Deterministic stub only; no live provider dependency. |

Rollback proof checklist:

```text
Cognitive schemas import and validate.
Cognitive implementations still exist.
Rollback/current flags expose old tools to Front.
Deload flags hide old tools from Front.
update_session_bundle rollback/internal path remains callable.
Switching out of active mode prevents writer calls from classifier lifecycle.
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
decision: active / shadow-only / degraded / rollback
```

What this prevents:

```text
M5.I6 prevents a vague release call. The system either has evidence for active cutover or it explicitly ships shadow/degraded/rollback behavior.
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
Active mode cannot be globally waived while quality gates fail.
Per-session active canary waiver requires rollback proof, manifest logging, and explicit owner signoff.
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
pytest tests/k1/concierge/section_update/test_turn_input_builder.py tests/k1/concierge/section_update/test_classifier_turn_boundary.py tests/k1/concierge/section_update/test_active_apply.py tests/k1/concierge/section_update/test_turn_completed_coordination.py tests/k1/concierge/section_update/test_dispatch_overlay.py tests/k1/concierge/section_update/test_back_snapshot_gating.py -v
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
Current live classifier quality is too low for active cutover until M3 gates improve.
Operation vocabulary must remain exactly aligned with MutationGuard and section apply surfaces.
Batch writer semantics are not transactional, so whole-plan validation proof is release-critical.
Legacy tests may need careful rewriting to protect rollback instead of preserving old Front-visible behavior.
```
