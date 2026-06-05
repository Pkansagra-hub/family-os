# Back Tool Contract Developer Implementation Skeleton

**Status:** Skeleton only. Fill incrementally after codebase and whiteboard research.
**Source design spine:** [back_tool_contract_whiteboard.md](back_tool_contract_whiteboard.md)
**Purpose:** Turn the whiteboard into a developer-codable implementation document, one seam at a time.

---

## 0. How To Use This Document

### Fill Rule

Fill this document one seam at a time. A section should move from heading-only to filled only after the current code path and the relevant whiteboard section have both been reviewed.

Every filled seam must separate:

```text
current runtime behavior
target runtime behavior
exact migration delta
files to read/edit/add
feature flag and fallback
proof command and negative proof
open design gaps
```

Do not use this document to restate the whole whiteboard. Link back to the whiteboard for architecture rationale and use this document for developer-codable seams.

### Research Rule

Every implementation claim must be grounded in code, probes, or a named whiteboard contract. When filling a seam, first identify the current files, functions, events, schemas, tests, and known failure behavior.

Use this order:

```text
1. Read current code reality.
2. Read the matching whiteboard contract or component section.
3. Identify what is live, what is POC-only, and what is target-only.
4. Write only the migration delta that is supported by that research.
```

If the current code reality is unclear, leave the implementation details blank and add an open design gap instead of guessing.

### Promotion Rule

A section is not promoted just because it sounds right. Promotion means the seam has enough detail for a developer to implement or review a focused change without re-deriving the architecture.

Use these statuses inside seam sections when needed:

```text
placeholder
researched_current_state
draft_target_delta
ready_for_implementation
implemented_and_proven
deferred_design_gap
```

A seam can reach `ready_for_implementation` only when it names current code anchors, proposed code homes, compatibility behavior, targeted proof, and at least one negative proof topic.

### Test Rule

Each filled implementation seam must name targeted proof commands only. Do not use broad suites as proof for narrow seams.

The command block should distinguish:

```text
Run:
  focused pytest/probe command

Do not run:
  broad kernel/fabric suites unless explicitly requested for that seam

Not run yet:
  reason, if the seam is documentation-only or not ready
```

When a seam touches LLM-visible behavior, prompt capture or redaction proof must be named as a topic even if the exact command is still deferred.

### Open Design Gap Rule

If a seam cannot be specified because the whiteboard or codebase is incomplete at that subcomponent level, do not smooth it over. Mark the seam as `deferred_design_gap` and add an entry under **Open Design Gap Register**.

Open gaps should name:

```text
gap id
affected seam
why current design is insufficient
code paths that still need research
decision owner or likely owner
blocking impact
next research action
```

This document is allowed to expose incompleteness. That is the point: developers should see where design is firm, where code is live, and where more research is required before implementation.

---

## 1. Document Scope

### In Scope

This document covers the developer implementation path for moving from the current Back/Fabric capability execution baseline toward the situated execution kernel described in the whiteboard.

In scope:

```text
current code reality for each seam
target behavior for each seam
specific edit locations and proposed new code homes
compatibility with the existing discover/invoke/submit path
feature flags, shadow mode, fallback, and rollback topics
POC-to-production promotion topics
contract skeletons needed by implementation
targeted tests, probes, and negative proof topics
open design gaps discovered during research
```

The immediate implementation frame is the first-pass migration, especially the FP-01 through FP-08 work packages, while keeping the later CC-0 through CC-10 architecture visible.

### Out Of Scope

This document does not replace the architecture whiteboard and should not duplicate its full rationale.

Out of scope:

```text
full generic-kernel theory
complete final JSON schemas before seam research
provider-specific external API protocol details
final UI behavior
large unrelated refactors
new product requirements outside the Back/Fabric/Bridge/IFL execution path
tracking every issue as a project-management board
```

When deeper architecture justification is needed, reference the whiteboard. When implementation detail is missing, record an open design gap instead of inventing a final answer.

### Current Code Reality Required Before Detail

No seam should contain implementation instructions until it has a current-state read. The current-state read must identify what exists today and where it lives.

Minimum current-state topics:

```text
files and functions involved
runtime caller and callee
input and output shape today
event topics or bus envelopes, if any
prompt-visible material, if any
policy/safety behavior today
fallback or error behavior today
existing tests or probes
known gaps or mismatch with target design
```

If a target artifact already exists only in `poc/back_tool_contract`, label it as POC-only until a production code home is chosen.

### Target Design Required Before Detail

Every seam must say what target behavior changes and which authority boundary it introduces or tightens.

Minimum target-design topics:

```text
target owner/component
target request and response artifact names
authority decision made at this seam
what the LLM may see
what must stay hidden from the LLM
freshness/completeness/policy expectations
typed failure or recovery behavior
proof evidence required before cutover
```

If the target behavior is still incomplete, keep the seam open and list the missing design decisions.

### Compatibility And Migration Rule

Migration is additive until a seam is proven. The current Front -> FSM -> Back -> discover_capabilities -> invoke_capability -> submit_result path must remain available while new resolver, binding, PromptPack, and observation seams are introduced.

Each seam must state:

```text
legacy behavior preserved
new behavior behind feature flag
shadow comparison behavior, if applicable
fallback behavior when disabled or failed
rollback target
evidence required before the new behavior becomes authority
```

Do not describe `resolve_situation`, `binding_id`, `CandidateUniverse`, or `PromptPack` as live authority unless the production code path has been implemented and proven. Until then, treat them as target contracts or POC-proven seams.

---

## 2. Current Runtime Spine

Section status: `researched_current_state` for all subsections below.

These notes describe the live runtime as read from current code. They do not claim that target artifacts such as `ResolutionEnvelope`, `CandidateUniverse`, `PromptPack`, or `binding_id` are production authority yet.

### Front Intent And Dispatch

Design status: `researched_current_state`.

Code anchors read:

```text
k1/concierge/actors/front.py
k1/concierge/tools/schemas_front.py
k1/concierge/tools/implementations.py
k1/concierge/react/loop.py
k1/concierge/task/dispatch.py
k1/concierge/prompt/builder.py
```

Current runtime flow:

```text
Front receives an Envelope
  -> resolves PromptMode from FSM/topic/session signals
  -> refreshes grounding when a grounding service is wired
  -> builds scenario_data for STANDARD, PRESENT, WEAVE, HITL, ERROR, or CANCEL modes
  -> applies OPP/selfmodel/grounding prompt enrichment when available
  -> DynamicPromptBuilder builds system prompt, messages, tools, max iterations
  -> react_loop(actor="front") runs with Front tools
  -> dispatch_task tool results are collected into ReactResult.dispatched_tasks
  -> front_handler publishes cancel dispatches first
  -> front_handler publishes normal task.dispatch events before final response
  -> front_handler publishes response.final after dispatch events
```

Current `dispatch_task` tool shape:

```text
intents[]
  action
  params optional
  domain optional
urgency: normal | urgent | background
reference_context optional
depends_on optional
plan optional
```

`execute_dispatch_task` returns a `ToolResult` with `queued`, `task_id`, and an internal `_dispatch` payload. The ReAct loop merges `_dispatch` into the collected task entry. That coupling is live today: the Front loop depends on the tool implementation stashing the full dispatch payload under `_dispatch`.

Task dispatch payloads can carry:

```text
task_id
intents[]
tier
budget_hint
safety_band
reference_context
depends_on
context_snapshot
execution_profiles
grounding_envelope_id
temporal_anchor_id
spatial_context_id
resolved_temporal_refs
resolved_spatial_refs
grounding
trace_id
```

Tier derivation at the Front tool layer is currently simple:

```text
complexity=HIGH -> HIGH
plan=true       -> MEDIUM
depends_on set  -> MEDIUM
otherwise       -> LOW
```

Prompt-visible material today includes the mode-specific Front prompt, recent chat history, scenario data, affect guidance, family context when available, selfmodel/grounding capsules when wired, and the selected Front tool schemas. Current Front tool selection can include direct capability discovery/invocation schemas in low-tier paths, so Front is not purely a dispatch-only actor in every current configuration.

Bus behavior today:

```text
cancel dispatches publish before normal dispatches
normal dispatches publish as k1.orchestration.task.dispatch.v1
final response publishes after dispatches
HITL relay/resolve modes publish HIL-specific events or legacy task.resume
all emitted envelopes are correlated with session and cognitive trace when available
```

Current gaps and caveats:

```text
Front gets only queued/task_id after dispatch_task; it does not observe Back execution in the same turn.
Tier estimation is not capability-aware.
reference_context is LLM-assembled user-world context, not execution authority.
Intent params are not validated against capability schemas before dispatch.
context_snapshot exists on TaskDispatch but is not normally populated by dispatch_task.
execution_profiles exists on TaskDispatch but is not normally populated by dispatch_task.
Cancel detection is action-string based.
The _dispatch stash is an implicit contract between execute_dispatch_task and react_loop.
```

### FSM Canonicalization And Routing

Design status: `researched_current_state`.

Code anchors read:

```text
k1/concierge/fsm/controller.py
k1/concierge/fsm/task_bridge.py
k1/concierge/task/dispatch.py
k1/concierge/orchestrator/routing.py
k1/concierge/section_update/overlay.py
k1/concierge/bus/builders.py
```

Current runtime flow:

```text
FSM receives k1.orchestration.task.dispatch.v1
  -> guard checks whether dispatch is legal in current FSM state
  -> payload is parsed into TaskDispatch
  -> TaskDispatch normalizes intents, tier, depends_on, budget_hint, and grounding mirror fields
  -> trace_id and session_id are attached to the dispatch object as loose attributes
  -> task is registered with active task sets, cancel handler, control extension, running task handle
  -> TaskBridge writes TaskCreated to the ledger and adds task_state status DISPATCHED
  -> FSM transitions to COMPANIONING when needed
  -> _route_via_orchestrator decides Back vs Orchestrator path
```

Canonical Back payload construction happens inside `_route_via_orchestrator`. It starts from `dispatch.to_dict()` and then injects or attaches:

```text
task_id
trace_id
session_id
turn_state_overlay when present
scoreboard referent fallback when reference_context is absent
narrative_thread when available
```

Grounding mirroring currently happens in `TaskDispatch.__post_init__`, before FSM canonical routing. FSM inherits the mirrored result from `TaskDispatch.to_dict()`; it does not re-run grounding mirroring as an explicit canonicalization step.

Routing behavior today:

```text
LOW
  -> canonical envelope delivered directly to Back mailbox with router.deliver(ACTOR_BACK)

MEDIUM with orchestrator wired
  -> TaskEnvelope sent through OrchestratorService path

MEDIUM without orchestrator
  -> fallback to Back mailbox

HIGH with orchestrator wired
  -> TaskEnvelope sent through OrchestratorService path, where planner/orchestrator own the plan path

HIGH without orchestrator and planner passthrough enabled
  -> stub committed_plan is created and re-routed as MEDIUM

HIGH without orchestrator and strict mode
  -> task.failed is published and OrchestratorNotWired is raised
```

Important current distinction: the canonical Back envelope is delivered only on the Back fallback path. For MEDIUM/HIGH orchestrator routes, `route_task_sync` produces a `TaskEnvelope` before some FSM-injected canonical fields are attached to the Back payload.

Current event behavior:

```text
TaskCreated ledger event is written through TaskBridge.
task.failed is published on strict HIGH/no-orchestrator failures or orchestration exceptions.
LOW delivery to Back is mailbox delivery, not a bus publish of the canonical envelope.
No task.accepted or task.routed event is emitted on the normal happy path.
```

Current gaps and caveats:

```text
There is no CanonicalizationReport.
Preserved, injected, defaulted, and discarded fields are not recorded as structured evidence.
MEDIUM/HIGH orchestrator path may not receive scoreboard fallback, narrative thread, or overlay fields added for Back fallback.
Scoreboard and narrative fallback failures are best-effort and mostly silent.
depends_on validation strips invalid values but does not return a typed diagnostic to Front.
trace_id/session_id are not TaskDispatch dataclass fields and must be manually injected by routing code.
```

### Back Intake And Prompt Assembly

Design status: `researched_current_state`.

Code anchors read:

```text
k1/concierge/actors/back.py
k1/concierge/prompt/back_prompt.py
k1/concierge/prompt/back_profiles.py
k1/concierge/tools/schemas_back.py
k1/concierge/react/history.py
```

Current runtime flow:

```text
back_handler receives the routed envelope
  -> parses task payload
  -> resolves trace_id from envelope, task, ToolContext, or generated fallback
  -> reads task_id and tier
  -> gets Back control queue when FSM exposes one
  -> rebinds the Back dispatcher for simple vs plan tier bucket
  -> binds ToolContext with trace_id, session_id, active_task_id
  -> reads SessionState snapshot once at task start
  -> computes effective safety_band from task, snapshot, or config fallback
  -> rebinds ToolContext with safety_band
  -> selects/persists execution profiles
  -> builds execution profile block
  -> builds execution grounding block from task grounding, live grounding port, or flat grounding fields
  -> rebinds ToolContext with execution_profiles
  -> builds Back system prompt
  -> builds recent Back chat history
  -> appends full task JSON as the final user message
  -> filters Back tools by tier
  -> registers running task messages for possible inter-iteration control injection
  -> creates LLMOutputValidator
  -> wires cancellation and stream callbacks
  -> calls react_loop(actor="back")
  -> optionally resolves needs_human in-process through HIL port
  -> emits task.complete, task.suspended, or task.failed after the loop returns
```

Back reads SessionState once at task start. The snapshot includes rendered or fallback summaries for:

```text
beliefs_active
scoreboard referents
task_state
task_artifacts
control safety
history_active
persona preferences
```

Prompt-visible material today:

```text
full task JSON inside the system prompt
beliefs summary
task state summary
task artifact summary
effective safety_band
persona preferences
max tool calls
available tools note
execution profile block
execution grounding block
resolved temporal refs appended to grounding text when present
recent history messages
full task JSON again as active user message
```

ToolContext binding today is incremental. `_bind_tool_context` writes directly onto `tool_dispatcher.ctx`:

```text
cognitive_trace_id
session_id
active_task_id
safety_band
active_execution_profiles
```

Tier and tool behavior today:

```text
LOW/simple
  -> recall_memory, discover_capabilities, invoke_capability, batch_invoke_capabilities, submit_result

MEDIUM/HIGH/plan
  -> LOW/simple tools plus spawn_via_fabric and execute_workflow
```

`budget_hint` can override configured tier iterations through `_budget_to_iterations`; the prompt uses this number as `max_tool_calls`.

Current gaps and caveats:

```text
Scoreboard referents are passed toward build_back_prompt but are not rendered by the current Back prompt template.
Safety band fallback can silently become GREEN when the control section is missing or malformed.
SessionState snapshot access is duck-typed and tolerant; malformed sections can degrade to empty summaries.
Grounding block construction has multiple fallback paths and can silently become empty after warnings.
No mid-loop SessionState re-read occurs except resume-style flows.
Execution profile selection does not scan free text; it depends on structured metadata/domain hints.
available_tools_note is prompt text and can drift from BACK_TIER_ALLOWLISTS if not kept aligned.
```

### Back ReAct Tool Loop

Design status: `researched_current_state`.

Code anchors read:

```text
k1/concierge/react/loop.py
k1/concierge/react/back_execution_plan.py
k1/concierge/tools/dispatcher.py
k1/concierge/tools/result_protocol.py
k1/concierge/tools/schemas_back.py
k1/concierge/task/parallel_safety.py
k1/concierge/tools/implementations.py
```

Current Back loop flow:

```text
react_loop starts with actor="back"
  -> seeds capability/discovery state from existing messages
  -> sets effective_max_iterations and hard_max_iterations
  -> resolves reasoning_effort to medium when auto
  -> uses tool_choice="auto" for Back iterations

Each iteration:
  -> checks cancellation
  -> drains BackControlEvent queue for cancel or parameter_update
  -> injects final-iteration submit_result nudge when at last iteration
  -> builds ModelHub ToolCallPayload with system prompt, messages, tools, tool_choice
  -> calls model.execute or streaming generation with timeout
  -> validates tool calls through LLMOutputValidator when present
  -> separates submit_result from other calls
  -> dispatches non-submit tool calls through ToolDispatcher
  -> appends ToolResult observations to messages
  -> injects repair/nudge messages for selected failures
  -> exits only on submit_result, HIL/safety suspension, cancellation, timeout, degenerate loop, or missing submit_result
```

Tool dispatch pipeline today:

```text
policy gate when wired
actor/tier allowlist check
tool budget check, with submit_result exempt
per-tool call limit for mutation tools
Back no-work submit_result guard
JSON Schema validation
CRISIS side-effect block
execute_tool(name, args, ctx)
tool.started/tool.completed bus events when bus is wired
execution record and call summary capture
```

Parallelism behavior:

```text
read-style tools such as recall_memory, summarize_context, discover_capabilities may run in parallel when config allows
Back action tools such as invoke_capability, batch_invoke_capabilities, spawn_via_fabric, execute_workflow, submit_result are always sequential
results are sorted back to model tool-call order before becoming observations
```

Termination behavior today:

```text
submit_result(result_type="complete") -> ReactResult(status="complete") when tool dispatch succeeds
submit_result(result_type="needs_human") -> ReactResult(status="suspended") when tool dispatch succeeds
tool-level ask-human recovery -> ReactResult(status="suspended") without requiring model submit_result
policy/safety denial observations can suspend Back immediately
budget exhaustion or no terminal submit -> ReactResult(status="missing_submit_result")
cancel events -> ReactResult(status="cancelled")
```

Loop guards today:

```text
degenerate empty response guard
pseudo-code/tool-code guard
text-without-tools nudge for Back
capability spin guard after repeated discovery/context reads without authority action
malformed tool-call nudge
repeated invalid schema strike limit
retryable error promotion after repeated same-call failures
no-work submit_result guard in ToolDispatcher
```

Current gaps and caveats:

```text
BackExecutionPlan exists but is not wired into react_loop; per-intent completion is not enforced.
submit_result mixed with other tool calls processes submit_result first and skips the other calls.
execute_submit_result validates only result_type at the tool layer.
The no-work guard treats recall_memory and summarize_context as enough prior work for complete, even when a system-of-record action was expected.
tool_choice remains auto for Back, including the first iteration.
Final-iteration submit_result is a prompt nudge, not a provider-enforced tool choice.
```

### Fabric Discovery And Invocation

Design status: `researched_current_state`.

Code anchors read:

```text
k1/concierge/tools/implementations.py
k1/concierge/tools/result_protocol.py
k1/concierge/tools/recovery_contract.py
k1/concierge/react/capability_routing.py
k1/concierge/adapters/fabric_dispatch.py
k1/fabric/fabric.py
k1/fabric/types.py
```

Current discovery flow:

```text
Back calls discover_capabilities(intent, domain optional)
  -> execute_discover_capabilities checks ToolContext capability_cache
  -> calls ctx.dispatch.discover_capabilities with top_k=10 and safety_band
  -> if domain is supplied, performs domain-filtered and unfiltered sweeps
  -> FabricDispatchAdapter forwards to FabricFacade.discover_capabilities
  -> Fabric retrieval engine returns scored capability contracts
  -> contracts are cached by exact capability name
  -> tool returns LLM-facing capability records
```

Discovery records today are plain dictionaries:

```text
name
description
domain
domains[]
score
prompt_template
activity_profile
tool_instructions
limitations[]
schema
  required_inputs[]
  optional_inputs[]
  capabilities[]
  output
  safety_band_min
```

Current invocation flow:

```text
Back calls invoke_capability(capability_name, params, session_id optional, action optional, domain optional)
  -> execute_invoke_capability normalizes selected params
  -> Front actor path is restricted by FRONT_READ_CAPABILITY_WHITELIST
  -> Back path attempts capability binding repair/validation when ToolContext is task-bound and dispatch is wired
  -> exact contract lookup is attempted from cache, lookup_capability, or discovery scan
  -> recovery_for_unsatisfied_contract checks required inputs before dispatch
  -> missing params return capability_params_incomplete with ask-human recovery data
  -> schema-satisfied request becomes CapabilityRequest
  -> ctx.dispatch.dispatch_direct sends to FabricDispatchAdapter
  -> workflow.* names can route to workflow dispatch; other names call Fabric execute
  -> CapabilityFabric executes resolve, policy/conscience, HIL gate, context build, provider execution, output validation, metrics/events
  -> CapabilityResult is mapped back into ToolResult
```

Binding behavior today:

```text
Binding runs only when ctx.actor == "back", ctx.active_task_id is set, and ctx.dispatch supports discover_capabilities.
candidate capability name is exact-lookup checked first.
invalid candidates return capability_binding_invalid_candidate with exact-name recovery options.
ambiguous discovery returns capability_binding_ambiguous with candidate choices.
not found returns capability_binding_not_found.
when binding preconditions are missing, binding is skipped and raw capability_name is forwarded.
```

Result shapes today:

```text
successful invoke_capability
  status=ok
  data.result = CapabilityResult.data or {}
  data.duration_ms
  data.status = success

failed Fabric dispatch
  status=error
  error = CapabilityResult.error.message
  data.result = {}
  data.duration_ms
  data.status = error

binding failure
  status=error
  error=capability_binding_<status>
  data includes candidates, recovery, binding, retryable=false

param preflight failure
  status=error
  error=capability_params_incomplete
  data includes schema, params, recovery ToolRecoveryContract, status=needs_human
```

Current gaps and caveats:

```text
Discovery is capability-first and top-K/ranking based, not resource-first.
Discovery records do not have a stable executable-vs-guidance record_type in the current shape.
Capability cache is an unbounded dict on ToolContext.
Binding silently skips if ToolContext is not task-bound or dispatch is incomplete.
capability_name remains the live invocation authority; binding_id is not the production authority path here.
CapabilityRequest uses fixed tier, priority, and timeout values from code, not from model args.
ToolResult hides some CapabilityResult fields such as provider_id and detailed timing.
CapabilityRequest validation is mostly deferred to lookup/Fabric resolution rather than a single local validate_or_raise call.
```

### Native Family Tool Provider Path

Design status: `researched_current_state`.

Code anchors read:

```text
k1/tools/family/bootstrap.py
k1/tools/family/registry.py
k1/tools/family/storage.py
k1/tools/family/definition.py
k1/tools/family/base.py
k1/tools/family/base_service.py
k1/tools/family/policy.py
k1/tools/family/events.py
k1/tools/family/calendar/definition.py
k1/tools/family/calendar/service.py
k1/tools/family/tasks/definition.py
k1/tools/family/tasks/service.py
k1/tools/family/reminders/definition.py
k1/fabric/manifest_translator.py
k1/fabric/providers/native_tool_provider.py
k1/fabric/types.py
```

Bootstrap and registration flow today:

```text
bootstrap_family_tools(fabric, service_classes, ...)
  -> opens K1FamilyStore SQLite connection with WAL/FK settings
  -> creates EventEmitter over SSE publisher and optional sync outbox
  -> creates ToolRegistry with shared connection, emitter, Fabric, policy
  -> registry.register_all(service_classes)
       -> each BaseToolService subclass is instantiated
       -> each service runs its adapter DDL through BaseToolService.__init__
       -> each ToolDefinition is translated into Fabric CapabilityContracts
       -> service is keyed by adapter_id in ToolRegistry
  -> creates NativeToolProvider over the live ToolRegistry
  -> registers LOCAL provider factory handler and ProviderConfig with Fabric
  -> returns FamilyToolsBundle held by kernel lifetime
```

Capability naming and contract shape today:

```text
read actions
  -> tool.read.<adapter_id>.<action_name>

write/delete/compute actions
  -> tool.execute.<adapter_id>.<action_name>
```

`manifest_translator.build_contract` creates one `CapabilityContract` per `ActionSpec`. Current contracts carry names, domain tags, description, required/optional inputs, output schema from action result fields, provider type/id/endpoint, safety band minimum, risk class, prompt template, activity profile, tool instructions, limitations, social act, and side-effect metadata.

Native invocation flow today:

```text
Fabric provider execution enters NativeToolProvider._execute
  -> _parse_capability_name extracts adapter_id and action_name
  -> ToolRegistry.get_service(adapter_id)
  -> service.DEFINITION.find_action(action_name)
  -> _build_write_context from CapabilityRequest and ExecutionContext
  -> service.dispatch(action_name, params, WriteContext)
  -> success dict maps to CapabilityResult.success_result
  -> failure dict maps to CapabilityResult.failure_result
```

`WriteContext` currently derives:

```text
user_id from request caller/caller_id or provider default
role from execution context control section, defaulting to parent for unknowns
band from request safety_band or control band or GREEN
space_id from control section or provider default
face from control section or llm
idempotency_key from params when present
trace_id/session_id from request/context
```

Family service dispatch behavior today:

```text
BaseToolService.dispatch
  -> role and min_role checks through VisibilityPolicy / role_satisfies
  -> band check through VisibilityPolicy.check_band
  -> idempotency replay for idempotent specs with idempotency_key
  -> resolve handler by action name
  -> call async or sync handler
  -> validate handler returns dict
  -> record idempotent result when applicable
  -> publish k1.tools.<adapter>.dispatch.<outcome>.v1 when bus publisher is wired
```

Adapter handlers, such as calendar and tasks, own the actual SQLite mutations. They read existing rows, apply model updates, bump versions, write with `INSERT OR REPLACE`, use soft-delete fields for deletes, and emit entity/write events through `EventEmitter` after successful writes.

Event behavior today:

```text
EventEmitter emits family.<adapter_id>.<action_name>.<kind>.v1 envelopes
envelopes include uuid, topic, timestamp, trace_id, actor, adapter, action, kind, payload
payload redaction follows ActionSpec.sse.redact_fields
SSE publish is best effort
optional K0 sync outbox enqueue is best effort
```

Result and error shape today:

```text
service success
  -> dict with success=True plus adapter-specific fields

service failure
  -> success=False, error_code, error_message

NativeToolProvider success
  -> CapabilityResult.success_result(data=service_result)

NativeToolProvider failure
  -> CapabilityResult.failure_result(error_code, error_message, retriable=False in most local validation failures)
```

Current gaps and caveats:

```text
LOCAL provider type is a string constant and not a ProviderType enum member.
CapabilityContract latency and cost fields are hardcoded by the translator.
ActionSpec.output_schema exists but build_contract derives output from action.result fields.
WriteContext.face defaults to llm unless control context overrides it.
No cross-adapter transaction boundary exists for multi-resource writes.
Adapters use soft delete; hard purge/TTL cleanup is not part of the current service layer.
NativeToolProvider/BaseToolService do not centrally validate params against ActionSpec.params before handler dispatch.
K0 sync outbox is optional and absent by default.
Read visibility behavior depends on adapter read handlers and acl helpers as well as VisibilityPolicy.
reminders.fire_reminder is system-only but no scheduler/trigger path is wired in native bootstrap.
```

### Planner And Orchestrator Path

Design status: `researched_current_state`.

Code anchors read:

```text
k1/concierge/orchestrator/routing.py
k1/concierge/fsm/controller.py
k1/orchestrator/orchestration/orchestrator_service.py
k1/orchestrator/orchestration/dag_executor.py
k1/orchestrator/orchestration/step_runner.py
k1/orchestrator/orchestration/param_resolver.py
k1/orchestrator/types.py
k1/planner/pipeline_controller.py
k1/planner/types.py
```

FSM and orchestrator entry today:

```text
Concierge FSM calls route_task_sync(task, tier)
  -> LOW produces Back dispatch record
  -> MEDIUM produces TaskEnvelope with max_fabric_calls budget
  -> HIGH produces TaskEnvelope with planner-token/fabric-call budget
  -> production entry from Concierge into Orchestrator is OrchestratorService.handle_task(envelope)
```

`OrchestratorService.handle_task` translates the Concierge-side `TaskEnvelope` into the production orchestrator `TaskEnvelope`, registers a waiter for HIGH traces, calls `process`, and waits for HIGH completion through a future that is resolved after plan execution result emission.

MEDIUM path today:

```text
_dispatch_medium
  -> validates capabilities are present and count <= 2
  -> reads safety band from state port
  -> queries Fabric registry for each capability
  -> builds CapabilityRequest with tier=MEDIUM and caller=orchestrator
  -> executes Fabric requests sequentially with per-step error isolation
  -> aggregates through AggregatedResult.from_medium
  -> emits ORCH_DAG_COMPLETED and audit
```

MEDIUM does not use Planner, `DAGExecutor`, `ParamResolver`, or WAL wave execution. It is direct orchestrator-to-Fabric execution for one or two capabilities.

HIGH planner path today:

```text
_dispatch_high
  -> reads state snapshot
  -> builds PlanRequest with intent, trace_id, context, request_id, constraints, grounding, timeout
  -> planner_port.request_plan(plan_request)
  -> stores PendingPlanContext by request_id
  -> emits ORCH_PLAN_REQUESTED
  -> returns DEFERRED

plan.ready event
  -> _on_plan_ready deserializes CommittedPlan
  -> enqueues plan into Orchestrator mailbox

_receive_plan
  -> deduplicates by plan_id
  -> correlates to PendingPlanContext by request_id
  -> re-reads fresh state snapshot
  -> validates plan through ConstraintResolver
  -> acquires ConcurrencyGuard
  -> executes DAGExecutor.execute(plan, ctx)
  -> releases guard
  -> emits aggregate result and resolves handle_task waiter
```

DAG execution today:

```text
DAGExecutor.execute
  -> builds Kahn topological waves
  -> writes PLAN_START/WAVE_COMPLETE/DAG_COMPLETE WAL entries best effort
  -> emits DAG progress deltas
  -> executes waves sequentially
  -> runs each wave's ready steps concurrently with semaphore cap
  -> ParamResolver resolves $step.result.path references before dispatch
  -> StepRunner builds CapabilityRequest for each step
  -> StepRunner executes Fabric with timeout, retries, and optional output-schema retry
  -> failed steps cancel downstream dependents
  -> compensation runs after failures when side-effect metadata supports it
  -> AggregatedResult.from_dag summarizes completion
```

HIL, errors, compensation, and results today:

```text
Planner PipelineController has HIL port hooks and stage-level cancellation checks.
Orchestrator ProcessingContext carries requires_hitl, but guard list is currently empty.
ErrorRouter classifies recoverable, degraded, and terminal errors.
DAG interrupt flag is checked between waves and after step results.
Compensation runs for completed side-effect steps when later failures require it.
AggregatedResult success means failed == 0 and cancelled == 0.
Skipped/degraded steps do not by themselves make success false.
```

Current gaps and caveats:

```text
Concierge still uses route_task_sync on the FSM hot path; async FabricOrchestratorAdapter mailbox dispatch is not the sole path.
DAGExecutor guard list is empty, so micro-replan, execution monitor, and HIL guard concepts are not live.
ConstraintResolver is injected behind a Protocol-like boundary and may be a no-op depending on bootstrap.
MEDIUM path executes capabilities sequentially, not in parallel.
OrchestratorService's DAGExecutorLike protocol and real DAGExecutor disagree on the second execute argument type.
Planner stages are injected as Any, so concrete stage availability is runtime-checked by behavior, not static type.
Crash recovery re-executes from wave 0; no resume_from_wave exists.
Pending plan timeout reaper does not cancel in-flight planner work.
Some _receive_plan early-return failures may not resolve handle_task waiters until timeout.
```

### Bridge And IFL Current Reality

Design status: `researched_current_state`.

Code anchors read:

```text
bridge/runtime.py
bridge/client.py
bridge/ports/connector_gateway_protocol.py
bridge/ports/command_port_protocol.py
bridge/connector/gateway.py
bridge/connector/contracts.py
bridge/connector/request_router.py
bridge/connector/mcp_process_manager.py
bridge/connector/real_mcp_process_manager.py
bridge/connector/token_verifier.py
bridge/connector/adapter_verifier.py
bridge/connector/crash_budget.py
bridge/connector/mcp_child.py
bridge/connector/transport/*
bridge/core/envelope_builder.py
bridge/core/health.py
bridge/sync/local_outbox.py
bridge/sync/drain_worker.py
bridge/ifl/adapters/google_calendar/server.py
bridge/ifl/adapters/google_calendar/oauth.py
bridge/ifl/adapters/google_calendar/consent.py
k1/kernel/ports/bridge_port.py
k1/fabric/ports/bridge_port.py
k1/planner/ports/bridge_port.py
poc/back_tool_contract/manifest_registration.py
poc/back_tool_contract/capability_registry.py
poc/back_tool_contract/resource_projection.py
poc/back_tool_contract/resource_registry.py
```

Live production Bridge/IFL reality today:

```text
ConnectorGateway is a concrete runtime path.
  -> TokenVerifier.verify
  -> AdapterVerifier.verify
  -> RequestRouter.dispatch
  -> MCPProcessManager.invoke

RealMCPProcessManager can spawn adapter subprocesses over stdio JSON-RPC.
It performs MCP initialize, caches tools/list, runs health pings, enforces crash budget, and can quarantine crashed adapters.

The live Google Calendar IFL adapter is a FastMCP server exposing events_list.
It can run in production OAuth mode or fixture mode through BRIDGE_GCAL_FIXTURE_PATH.
The live adapter shape is read-only events.list, not calendar write.

BridgeRuntime is a lifecycle/container skeleton with slots for command/query/sse/obs/gateway/transport/client.
Many slots are None in the current from_registry path.

LocalOutbox and DrainWorker provide offline queue/drain behavior.
K0HealthChecker and DegradedModeManager provide health/degraded/offline state support.
```

Production connector dispatch shape today:

```text
ConnectorGateway.invoke(adapter_id, tool, args, caller)
  caller = ConnectorCaller(session_id, tenant_id, space_id, user_band, capability_token, trace_id)
  -> ConnectorResult(success, data, error_code, error_message, adapter_id, tool, latency_ms, attempt_count)
```

Live IFL adapter command/result shape today:

```text
Google Calendar events_list request
  account_id
  calendar_id
  time_min
  time_max
  max_results
  single_events

Google Calendar events_list response
  events[]
  next_page_token optional
```

POC/probe-only current reality:

```text
poc/back_tool_contract/manifest_registration.py exists and translates IFL manifests into CapabilityRegistrationBatch.
poc/back_tool_contract/capability_registry.py exists and materializes a SQLite capability registry with 100k-scale support.
poc/back_tool_contract/resource_projection.py exists and returns ResourceUniverse with freshness/completeness/scope proof.
poc/back_tool_contract/resource_registry.py exists as a SQLite connected-resource registry fixture.
```

Missing POC modules in this workspace:

```text
poc/back_tool_contract/connector_dispatch.py
poc/back_tool_contract/ifl_adapter_runtime.py
poc/back_tool_contract/projection_delta.py
```

Probe scripts reference those missing modules, so M7, M8, and M10 probes are scaffolded but blocked in the current workspace unless those files are restored or created.

Manifest, projection, and event reality today:

```text
bridge/contracts/manifests contains live bridge-bus YAML manifests for K0/K1 topics.
poc/back_tool_contract/schemas/ifl_manifest.schema.json defines the POC IFL provider manifest format.
register_ifl_manifest separates guide-only templates from executable capability contracts.
ConnectedResourceRegistry and resolve_resources are POC-only and not fed by live connector events.
No live connector-result-to-ResourceProjectionDelta pipeline is wired today.
The Google Calendar IFL adapter does not emit projection deltas.
```

Current gaps and caveats:

```text
BridgeRuntime slots are not fully bound to ConnectorGateway in current kernel wiring.
K1 Bridge runtime port is lifecycle/client-oriented and does not expose the full connector-dispatch authority shape.
K1 Fabric bridge port and Planner bridge port are separate surfaces with narrower methods.
TokenVerifier is permissive and accepts any non-empty token when manifest requires capability.
DefaultRequestRouter is single-shot with no real retry/circuit behavior.
Only Google Calendar events_list is a live IFL adapter; no live external write adapter exists.
POC manifest registration and projection are not wired into production Fabric or Bridge runtime.
No live connector event projection pipeline exists.
```

### Proof And Probe Current Reality

Design status: `researched_current_state`.

Code anchors read:

```text
poc/back_tool_contract/README.md
poc/back_tool_contract/resource_projection.py
poc/back_tool_contract/resource_registry.py
poc/back_tool_contract/capability_registry.py
poc/back_tool_contract/manifest_registration.py
poc/back_tool_contract/schemas/*
scripts/_probe_common.py
scripts/probe_back_contract_proof_harness.py
scripts/probe_back_task_envelope.py
scripts/probe_resolve_situation.py
scripts/probe_resource_projection.py
scripts/probe_policy_selector.py
scripts/probe_binder.py
scripts/probe_invoke_by_binding.py
scripts/probe_bridge_dispatch.py
scripts/probe_ifl_adapter.py
scripts/probe_manifest_translator.py
scripts/probe_projection_delta.py
scripts/probe_prompt_injection.py
scripts/probe_resolution_executor.py
scripts/probe_production_back_runtime.py
scripts/probe_e2e_scenarios.py
scripts/probe_back_profiles.py
scripts/_aggregate_probe_gaps.py
```

Proof harness intent today:

```text
M0 probe expects ProofRecordWriter and proof_record_template to support:
  success proof record write
  structured failure entry write
  validation prompt record write
  missing trace_id rejection
  secret-like field redaction
  raw_catalog prompt_capture_ref rejection
  mocked E2E proof rejection
```

Critical current workspace gap:

```text
poc/back_tool_contract/proof.py is absent in this workspace.
Most probe scripts and implemented POC modules import ProofRecordWriter, proof_record_template, utc_now_iso, or copy_json from it.
Therefore most POC probe scripts are scaffolded but currently import-blocked.
```

Probe families defined today:

```text
M0   probe_back_contract_proof_harness.py
M1   probe_back_task_envelope.py
M2   probe_resolve_situation.py
M2A  probe_back_resolver_prompt_surface.py
M2B  probe_back_resolver_live_llm.py with --live
M3   probe_resource_projection.py
M3-user probe_user_message_resource_projection.py
M4   probe_policy_selector.py
M5   probe_binder.py
M6   probe_invoke_by_binding.py
M7   probe_bridge_dispatch.py
M8   probe_ifl_adapter.py
M9   probe_manifest_translator.py
M10  probe_projection_delta.py
M11  probe_prompt_injection.py with --production-provider
M12A probe_resolution_executor.py
PROD-BACK-100K probe_production_back_runtime.py
M12  probe_e2e_scenarios.py with --production-provider
live kernel probe_back_profiles.py
gap audit _aggregate_probe_gaps.py
```

Artifact and output conventions today:

```text
probe scripts commonly support --json
proof artifacts are written only with --record-proof
default artifact root is tmp/back_tool_contract/<milestone-specific-subdir>
service SQLite stores live under tmp/back_tool_contract/services
ProbeReport from scripts/_probe_common.py returns nonzero exit code on FAIL
```

Inferred proof record topics today:

```text
proof_id
milestone_id
scenario_id
component
seam
producer
consumer
trace_id
request_id
input_ref
output_ref
assertions[]
feature_flags[]
redaction_summary
rejected_fields[] when rejected
```

Live-provider distinction today:

```text
Most POC probes are intended as non-LLM contract seams.
M2B requires --live and production ModelHub/Vertex path.
M11 requires --production-provider for live submit_result validation.
M12 requires --production-provider for live end-to-end scenario validation.
Live-provider probes require evidence that llm_mock_used is absent or false.
Without live flags, live-provider probes should report blocked/not-called rather than silently passing.
```

Redaction and negative proof behavior today:

```text
resource display cards filter forbidden marker fields such as token, secret, credential, oauth, authorization.
M0 expects secret-like debug payloads to be redacted, not rejected.
M0 expects empty trace_id to be rejected.
M0 expects raw_catalog prompt_capture_ref to be rejected.
M0 expects llm_mock_used=True on E2E proof to be rejected.
M9 guidance/profile templates are retained as guide refs, not executable capability contracts.
M12A duplicate path is expected to stop behind HIL before write.
```

Current gaps and caveats:

```text
poc/back_tool_contract/proof.py is missing, blocking most probes.
Many referenced POC modules are also missing in this workspace: back_task_envelope, resolve_situation, policy_selector, capability_binder, invocation_runtime, connector_dispatch, ifl_adapter_runtime, projection_delta, prompt_injection, live_provider, e2e_scenario_gate, resolution_executor, back_prompt_surface.
Existing implemented POC modules are resource_projection, resource_registry, capability_registry, and manifest_registration.
M3 and M9 are near-runnable once proof.py exists; most other milestones remain scaffolded.
PROD-BACK-100K delegates to M12A output and is blocked while M12A is missing.
Probe artifact format under tmp/back_tool_contract is separate from phase-level kernel probe JSON consumed by _aggregate_probe_gaps.py.
No pytest wrapper convention exists for these POC probes; current convention is direct python scripts/probe_*.py --json --record-proof.
```

---

## 3. Target Runtime Spine

Section status: `draft_target_delta` for all subsections below.

These notes describe the normative target from the whiteboard. They are not live authority. The current Front -> FSM -> Back -> discover_capabilities -> invoke_capability -> submit_result path remains the compatibility spine until each seam is proven. See section 2 for current reality.

Whiteboard source: [back_tool_contract_whiteboard.md](back_tool_contract_whiteboard.md). Key labels referenced below are the Three-Tier Model, Canonical Target Flow, Contracts A through Q, and Component Contracts CC-0 through CC-10.

Authority chain invariant (KD-001), mandatory for side effects and protected reads:

```text
request_frame -> resolution -> policy -> binding -> invocation -> observation
```

Dumb-LLM axiom: an LLM cannot plan from information it does not have. Procedural pre-checks live in connector/capability constitutions and are injected, never invented by the model.

### Tier 1 Conversation Path

Design status: `draft_target_delta`.

Target owner and authority:

```text
Owner: Front LLM (intent actor / voice).
Authority: conversation, grounding clarification, user-facing presentation.
No execution authority: no capability selection, no binding_id, no connector choice, no side-effect claims.
```

What the LLM may and may not do:

```text
May: answer safe conversational turns directly.
May: call dispatch_task with user-world intents, params, domain, urgency, reference_context, depends_on, plan.
May: resolve human-language references into dispatch hints.
May not: choose a Fabric capability or pass capability_name.
May not: pass binding_id, manifests, raw catalogs, or policy verdicts.
May not: claim a side effect completed.
May not: write SessionState.
```

Target step flow:

```text
1. User speaks.
2. Front receives conversation context, safe state summary, grounding hints, Front tool surface.
3. Front decides conversation vs work.
4a. Conversation -> Front answers directly; turn ends; no Back, no Fabric.
4b. Work -> Front calls dispatch_task with user-world intent and hints only.
5. Front does not claim work is done.
6. react_loop collects dispatched_tasks.
7. front_handler publishes task.dispatch before final response.
8. FSM canonicalizes and routes to Tier 2 or Tier 3.
9. Front presents response after the outcome is known.
```

Target artifacts at this tier:

```text
dispatch_task tool call: Front's only work-dispatch surface.
TaskDispatch: Front/FSM handoff payload (current runtime object).
BackTaskEnvelope (CC-0): target intake wrapper carrying TaskDispatch plus correlation, actor/session scope, snapshot refs.
```

Front does not produce RequestFrame, CandidateUniverse, PromptPack, or BindingBundle. Those are Fabric/Plane 4 products.

Tier boundary rule:

```text
Front emits a tier hint; FSM owns the authoritative tier decision.
If the intent is obviously family-impacting or cross-resource, FSM should prefer direct Tier 3, not send it to Back to rediscover that.
```

Migration delta from current reality:

```text
Keep dispatch_task and the current TaskDispatch shape as baseline.
Add BackTaskEnvelope wrapping at the CC-0 boundary.
Do not change Front into an executor; treat any current Front direct discover/invoke path as a separate compatibility behavior to retire, not extend.
```
Open design questions:

```text
plan and top-level urgency may not survive FSM canonicalization; their effect must travel through tier, depends_on, or per-intent fields.
SafetyContext axes, RequestFrame, CandidateUniverse, PromptPack, binding_id are target-only at this tier.
Grounding metadata fields exist on TaskDispatch but are not normally produced by Front tool calls today.
```

### Tier 2 Back Direct Execution Path

Design status: `draft_target_delta`.

Target owner and authority:

```text
Owner: Back LLM (execution actor / worker), for LOW and simple MEDIUM tasks.
Scope: tasks resolvable within one connector's world with a few reads then a gated write.
May not invent resources, bindings, policies, or schemas.
Terminates only with submit_result or a typed non-completion outcome.
```

What the LLM may and may not do:

```text
May: build a RequestFrame from BackTaskEnvelope.
May: call resolve_situation(RequestFrame) and act only through allowed_next_actions.
May: call invoke_capability, or batch_invoke_capabilities for provably independent calls only.
May: ask HIL via structured HILRequest.
May: submit_result with completed, partial, needs_hil, cannot_execute, blocked, or failed.
May: promote to Tier 3 via a structured BackPromotionOutcome to FSM.
May not: skip resolve_situation for system-of-record side effects.
May not: invoke a capability not in allowed_next_actions.
May not: batch dependent calls before the first result returns.
May not: treat top-K ranking as execution authority.
May not: write SessionState or speak to the user.
```

Target step flow (Canonical Target Flow, 16 steps):

```text
1.  Front captures user-world intent.
2.  FSM canonicalizes task and state correlation.
3.  Back receives BackTaskEnvelope.
4.  Back builds RequestFrame.
5.  Back calls resolve_situation(RequestFrame).
6.  Resolver builds CandidateUniverse from local-world projection.
7.  Policy/guide authority produces PolicyBundle and GuideCards.
8.  Capability registry produces BindingBundle.
9.  Resolver returns ResolutionEnvelope plus PromptPack.
10. Back acts only through allowed_next_actions.
11. Fabric invocation executes via native provider or Bridge/IFL.
12. InvocationObservation is normalized.
13. VerificationObservation is produced when required.
14. Back submits a typed result with evidence.
15. FSM updates task/session state.
16. Front presents the response.
```

Staged disclosure within steps 5 through 10:

```text
Phase 0 deterministic, no LLM: situated projection selects connectors plausibly in scope.
Phase 1 LLM plan hop: connector summaries, connector constitutions, tool names only, no schemas.
Phase 2 bind: model commits exact tool names it will use.
Phase 3 schema disclosure: full schemas only for selected/bound tools.
Phase 4 execute/clarify/HIL: run the gated plan, verify, submit.
```

Connector constitution is the carrier for procedural pre-checks:

```text
connector: calendar
  preconditions: list_events before create/update to detect duplicates and time conflicts
  companion_resource_roles: participants, conflict_subjects, guardians
  verify: get_event read-back after write
  tools (names only): tool.read.calendar.list_events, tool.read.calendar.get_event, tool.execute.calendar.create_event
```

Target artifacts at this tier:

```text
BackTaskEnvelope (CC-0)
RequestFrame (Contract A)
ResolveSituationRequest (Contract B)
ResolutionEnvelope (Contract E)
CandidateUniverse (Contract F)
PromptPack (Contract G)
PolicyBundle (Contract C)
BindingBundle (Contract D)
InvocationRequest / InvocationObservation (Contract H)
VerificationObservation (Contract M)
SubmitResult (Contract J)
BackPromotionOutcome (Tier 3 escalation)
```

Tier escalation rules (Back must promote to Tier 3 when):

```text
resolver returns target_tier=tier3 or verdict=needs_tier3.
connector constitution declares companion_resource roles spanning connectors.
task needs a cross-resource (person, time-window) impact set.
task needs a PlanGraph / dependency graph.
write depends on prerequisite reads across multiple connectors.
task needs compensation, conditional branches, or multi-step HIL.
local projection is incomplete and policy forbids direct continuation.
```

Promotion is a structured BackPromotionOutcome submitted to FSM. Back does not call Planner as a tool and does not write SessionState.

Migration delta from current reality:

```text
Keep discover_capabilities -> capability_name -> invoke_capability -> submit_result as compatibility spine.
Add resolve_situation -> ResolutionEnvelope -> allowed_next_actions as the target authority path.
Demote top-K discovery to catalog assistance, not execution authority.
Replace name-repair binding with BindingBundle authority over time.
```

Open design questions:

```text
resolve_situation, ResolutionEnvelope, CandidateUniverse, PromptPack, BindingBundle are target-only today.
Safety-band conflict (BTC-004) needs SafetyContext axes plus SafetyMappingEvidence before provider dispatch.
Deterministic param adapters (BTC-003), e.g. duration_minutes to end, are not yet implemented.
PromptPack staging (names then selected schemas) is target; current discovery returns full schemas.
PlanGraph is optional for Tier 2 single-connector work.
```

### Tier 3 Planner And Orchestrator Path

Design status: `draft_target_delta`.

Target owners and authority:

```text
Planner (plan mind, may use LLM): owns SKETCH -> EXPAND -> VALIDATE -> COMMIT; produces CommittedPlan / PlanGraph; does not execute or write SessionState.
Orchestrator (deterministic, no LLM): owns DAG execution, wave ordering, conditional branches, compensation, HIL resume, AggregatedResult; invents no steps.
Trigger: family-impacting, cross-resource, participant/conflict-bearing, multi-connector, compensating, or dependency-bearing tasks.
```

What the LLM may and may not do:

```text
Planner LLM may: sketch work shape, expand into StepFrames with references, dependency edges, verifier requirements.
Planner LLM may not: execute capabilities, write SessionState, or treat a CommittedPlan as execution authority by itself.
Orchestrator has no LLM: it builds waves, resolves $step.result only after the step completes, dispatches steps, evaluates conditional edges, applies compensation, and returns AggregatedResult.
```

Target step flow:

```text
Trigger:
  FSM routes Tier 3 directly for obvious family-impacting tasks, OR Back promotes a BackPromotionOutcome.
  FSM emits/updates a Tier 3 TaskEnvelope; Orchestrator builds a PlanRequest to Planner.

Planner FSM:
  SKETCHING: draft the rough impact shape.
  EXPANDING: produce concrete StepFrames, capability candidates/binding refs, dependency edges, verifier requirements, companion impact set.
  VALIDATING: no cycles, writes depend on required reads, HIL inserted where policy requires, no step asks Orchestrator to guess, every step has a valid capability path or known-missing capability.
  COMMITTING: deterministic commit producing CommittedPlan.
  emit plan.ready / plan.failed / plan.cancelled.

Orchestrator execution:
  receives CommittedPlan, validates, correlates by request_id, acquires concurrency guard.
  builds Kahn waves from dependency edges.
  Wave 1 prerequisite reads (parallel when policy allows).
  Wave 2 conflict/decision evaluation from observations.
  Wave 3A HILRequest if conflict, or Wave 3B governed write if clear.
  Wave 4 verification read-back plus audit evidence.
  resolves $step.result only after upstream completion.
  applies compensation when side-effect metadata supports it.
  returns AggregatedResult; FSM records outcome; Front presents response.
```

Target artifacts at this tier:

```text
BackPromotionOutcome
PlanRequest (current live object)
PlanGraph (Contract L) mandatory for Tier 3
StepFrame and PlanDependencyEdge (Contract L)
CommittedPlan (current live object)
CandidateUniverse (Contract F) with cross_resource_read_requirements
InvocationObservation (Contract H) per step
VerificationObservation (Contract M) before completed
AggregatedResult (Orchestrator output)
```

Boundary and invariants:

```text
PlanGraph is mandatory for Tier 3; optional only for Tier 2 (Contract L; whiteboard overrides the optional marker).
Invariant I20: each executable StepFrame must resolve through CandidateUniverse, PolicyBundle, BindingBundle, allowed_next_actions before invocation.
Reads may parallelize when policy allows; writes and dependent side effects stay sequenced.
Orchestrator resolves dependent params only after upstream completion; it does not guess or batch dependent steps.
Compensation requires the tool contract to declare a compensation capability.
```

Migration delta from current reality:

```text
Keep current MEDIUM direct-orchestrator and HIGH planner+orchestrator routing as baseline.
Add connector-constitution-driven tier decisioning so routing is not only complexity/plan hints.
Add CandidateUniverse-backed StepFrame resolution and mandatory PlanGraph for Tier 3.
Keep route_task_sync working while async dispatch and guard registration mature.
```

Open design questions:

```text
BTC-009/BTC-013: no connector constitution / CandidateUniverse / cross-resource (person, time-window) projection exists yet to prove the impact set before planning.
BTC-014: Contract L marks PlanGraph optional; whiteboard normatively requires it for Tier 3.
Companion_resource role types in domain ontology are not yet contract artifacts (BTC-012).
DAGExecutor guard list is empty today, so micro-replan/monitor/HIL guards are not live.
OQ-CC-001: single ExecutionActor vs separate IntentActor/PlannerActor/ExecutorActor remains open.
```

### Resolver Authority Path

Design status: `draft_target_delta`.

Target owner and authority:

```text
Component: Plane 4 Fabric Situated Resolver (CC-1 through CC-4).
Decision: the only legal source of what Back may do next.
It builds CandidateUniverse, selects policy/guide material, binds capabilities, and returns allowed_next_actions.
discover_capabilities top-K is demoted to catalog retrieval, not execution authority.
```

Request and response artifacts:

```text
ResolveSituationRequest (Contract B):
  request_frame (RequestFrame, Contract A)
  actor_scope
  safety_context (Contract O axes)
  resolution_mode: execution | catalog | diagnostic
  target_tier: tier2 | tier3 | unknown
  disclosure_phase: connector_summary | tool_name_selection | schema_binding | execution
  freshness_policy, prompt_budget, previous_resolution_id

ResolutionEnvelope (Contract E):
  resolution_id, request_frame (echoed)
  candidate_universe (Contract F)
  prompt_pack (Contract G)
  policy_bundle_ref, binding_bundle_ref
  completeness, freshness
  verdict
  allowed_next_actions, diagnostics

CandidateUniverse (Contract F):
  universe_id, scope_proof (ScopeProof)
  connector_candidates, resource_candidates
  impact_set_candidates, companion_resource_roles, cross_resource_read_requirements
  capability_bindings, plan_graph_ref (Tier 3)
  omissions, exclusions, completeness, freshness, policy_verdict, allowed_next_actions, expires_at
```

Resolver internally calls CC-2 ResolveResourcesRequest, CC-3 PolicySelectionRequest, and CC-4 BindingRequest.

LLM visibility:

```text
Visible: CandidateUniverse summary (labels, binding names, allowed actions, omission summary) via PromptPack.
Visible: resource binding references and compact policy gate cards.
Hidden: full ScopeProof, full PolicyBundle, raw manifests, credentials, raw provider payloads.
Classified resources are gated by protected-read policy before disclosure.
```

Freshness, completeness, and policy expectations:

```text
Candidate completeness must be established before ranking (Invariant I5).
Omissions and exclusions are explicit, never silence.
completeness must be a typed state; unknown_completeness blocks side effects and protected reads by default.
stale projection blocks non-read side effects unless policy allows queued execution.
ScopeProof.projection_sources must enumerate every source considered for replay.
Memory/belief/planner output may seed resolution but cannot authorize execution (I11, I12).
```

Typed failure and recovery (verdicts):

```text
ambiguous reference -> needs_disambiguation with HIL options.
missing params -> missing_required_params with unresolved questions.
no admitted capability -> missing_capability.
policy hard-deny -> blocked_by_policy.
partial/stale projection -> incomplete_world_projection or stale_projection.
cross-resource companions present -> promote_to_tier3.
budget exhausted -> cannot_execute with BudgetObservation (Contract Q).
```

Proof evidence required before cutover:

```text
M3: user-world reference returns ResourceUniverse with ScopeProof, resource_id, freshness, omissions, completeness.
M4: PolicyBundle includes roles, gates, hil_triggers, verifier and protected-read requirements without choosing provider commands.
M5: BindingBundle includes bound CapabilityBinding records and unbound_roles diagnostics.
M12: one real household scenario crosses CC-1..CC-4 with a ShadowComparisonRecord recommending cutover.
Negative proof: incomplete projection reports omissions; policy block is distinct from missing capability; stale projection blocks side effects with a typed reason.
```

Open design questions:

```text
ID-002: which store owns concrete resource projection versions in the first proof path.
Exact ResolutionEnvelope JSON schema and versioning (API Decision 3).
Exact DomainInstantiationPack and ResourceKindDef/OperationDef schemas for V0 (API Decisions 6, 7; OQ-DIP-001).
```

### Binding Authority Path

Design status: `draft_target_delta`.

Target owner and authority:

```text
Component: Plane 3 Fabric Capability Contract Registry (CC-4).
Decision: which actor + resource + operation + policy roles join to an exact CapabilityContract.
binding_id is the standard authorization token for a side-effecting invocation.
capability_name remains a compatibility fallback for proven native tools only (ID-001).
```

Request and response artifacts:

```text
BindingRequest (Contract D):
  request_frame, resource_candidates, required_roles (from PolicyBundle)
  connector_constitutions, selected_tool_names (schema_binding phase only)
  schema_disclosure_phase: names_only | selected_schemas | execution
  operation_hints, actor_scope, safety_context, authority_constraints, freshness_constraints

BindingBundle (Contract D):
  binding_bundle_id, connector_cards, tool_name_cards (names only at Phase 1)
  bindings[] each CapabilityBinding: binding_id, role, resource_id, capability_name, contract_ref,
    input_schema_ref, output_schema_ref, effect_summary, safety_requirement, authority_verdict,
    verifier_ref, guide_refs, freshness_state, limitations
  unbound_roles, contract_cards, selected_schema_cards, schema_disclosure_plan
  guide_refs, verifier_links, binding_diagnostics
```

Staged disclosure (binding-authoritative, not presentation-optional):

```text
Phase 0 no LLM: projection selects connectors in scope.
Phase 1: connector summaries, constitution preconditions, tool names only, no schemas.
Phase 2: model commits exact tool names; they become binding candidates.
Phase 3: selected_schema_cards populated only for bound tools.
Phase 4: governed invocation via binding_id.
Stale CapabilityBinding must block invocation via BindingValidationVerdict (SCA-077).
```

LLM visibility:

```text
Visible: tool_name_cards (Phase 1), selected_schema_cards (after commit), binding_id token, unbound_roles diagnostics.
Hidden: contract_ref/input_schema_ref internals, provider routing tables, connector_id routing.
data_classification surfaces only as gate text.
```

Typed failure and recovery:

```text
unbindable role -> unbound_roles entry (missing_capability, missing_connector, policy_block, stale_projection, unsupported_operation).
stale binding at invocation -> InvocationPreflightVerdict blocks; RecoveryDirective.action=refresh_projection.
legacy name not found -> capability_binding_invalid_candidate with choose_from_candidates.
legacy name ambiguous -> capability_binding_ambiguous with candidates.
schema invalid -> capability_params_incomplete with missing_fields and suggested_params_patch.
catalog-only manifest as executable -> blocked; ManifestAdmissionRecord.admission_verdict=catalog_only (Contract P).
BTC-004 safety-band conflict -> SafetyMappingEvidence (Contract O) before NativeToolProvider dispatch; fallback maps to degraded with conservative block.
```

Proof evidence required before cutover:

```text
M5: resolved resources and roles bind to exact contracts, contract cards, verifier links, unbound-role diagnostics.
ID-001: compatibility proven when binding_id and capability_name coexist in M6 with a ShadowComparisonRecord.
Negative proof: catalog-only manifest produces no executable binding; a guidance_profile record is classified guidance and excluded from bindings.
```

Open design questions:

```text
ID-001: how long native capability_name values remain valid.
Exact Back tool set for V1: resolve_situation only, or resolve_situation + inspect_binding (API Decision 4).
Exact compatibility mapping from native names to connector-aware names (API Decision 5).
Exact SafetyContext mapping from GREEN/AMBER/RED to kernel axes (API Decision 11).
BTC-004 resolution via SafetyMappingEvidence is target, not yet implemented.
```

### PromptPack Injection Path

Design status: `draft_target_delta`.

Target owner and authority:

```text
Component: Plane 4 resolver plus CC-10 Back Prompt Injection Timing.
Decision: what Back sees at each ReAct phase.
PromptPack (Contract G) is the only legitimate route for compact policy/guide/contract/binding cards into model context.
Raw catalogs, full manifests, secrets, and provider payloads never cross upward.
Allowed/forbidden actions are runtime-enforced by the dispatcher, not prompt-text suggestions.
```

Artifacts:

```text
PromptInjectionEnvelope (CC-10):
  injection_id, task_id, react_iteration, phase
  source_refs, compact_cards, observations
  allowed_tool_calls, forbidden_tool_calls, max_next_tool_calls, expires_at

PromptPack (Contract G):
  prompt_pack_id, react_state, target_tier, disclosure_phase
  source_refs, source_versions, candidate_summary
  connector_constitution_cards, tool_name_cards (names only at Phase 1)
  policy_cards, guide_cards, contract_cards
  selected_schema_cards (full schemas only at schema_binding)
  decision_surface, uncertainty_markers, omission_summary
  option_budget, context_load_shedding_summary
  allowed_tool_calls, forbidden_tool_calls, allowed_next_actions, forbidden_next_actions
  hil_options, stale_card_policy, redaction_summary (RedactionEvidence, Contract N)
  output_schema, max_tool_calls, expires_at
```

Phase-specific injection schedule (CC-10):

```text
loop_start: Back executor role, meta-tool declarations, task envelope summary, SessionState task snapshot, grounding block. No PromptPack, no schemas.
after_request_frame: compact RequestFrame, known missing_fields, allowed resolver modes.
after_resolution: full PromptPack (constitution cards, tool name cards, policy cards, guide cards, contract cards, CandidateUniverse summary, allowed_next_actions). No schemas yet.
after_tool_selection (schema_binding): selected_schema_cards for bound tools only.
after_invocation: InvocationObservation, VerificationObservation if available, RecoveryDirective, updated allowed_next_actions.
after_hil_response: HILResponse, prior resolution_id, changed constraints.
final_iteration: termination requirement, submit_result schema, unresolved obligations.
```

LLM visibility:

```text
Visible: constitution cards, tool name cards (names only), policy cards, relevant guide cards, allowed/forbidden actions, omission and uncertainty markers, selected schemas after binding.
Hidden: raw global catalog, full policy documents, secrets, full manifests, raw provider payloads (RawPayloadRef).
RedactionEvidence verdict referenced; prompt_visible_leak_count must be 0.
```

Staleness and omission invariants:

```text
A stale card cannot authorize a side-effecting action and must not appear in allowed_next_actions.
Budget-driven elision must be recorded in omission_summary; silent elision is forbidden (Invariant I14).
Every PromptPack carries source_refs and source_versions for replay via PromptCaptureRecord (Contract N).
expires_at governs the whole pack; regenerate after expiry, HIL response, or projection refresh.
PromptPack is not source of truth; authoritative contracts live in Plane 3.
RedactionEvidence must pass with prompt_visible_leak_count=0 before promotion (KD-002, M11).
```

Typed failure and recovery:

```text
expired pack at invoke -> InvocationPreflightVerdict stale_resolution; RecoveryDirective.action=refresh_projection.
forbidden tool call -> dispatcher blocks at runtime; ErrorObservation source_component=back.
RedactionEvidence verdict=fail -> blocks promotion; may block runtime response per policy.
budget exhaustion before full schema injection -> typed cannot_execute or partial with BudgetObservation.
guide card injected before relevance -> must not happen; gated by GuideCardSelector.
```

Proof evidence required before cutover:

```text
M11: PromptPack and observations injected at correct ReAct phase; allowed/forbidden actions enforced at runtime; no raw catalogs or secrets in prompt captures.
PromptCaptureRecord produced for every model-visible injection with redaction_evidence_ref and prompt_hash.
Negative proof: stale card injected into an invocation produces a typed block, not silent success.
Negative proof: a forbidden tool call is blocked by the dispatcher, not only discouraged in text.
```

Open design questions:

```text
Exact ExecutionBudget defaults for prompt cards and fanout (API Decision 13).
Full PromptCaptureRecord retention policy (RSV-09).
CC-10 owns injection timing; PromptPack schema ownership stays Contract G; do not conflate.
BTC-006: carry selected discovery contract summaries into after_resolution injection rather than re-discovering.
```

### Invocation Observation And Verification Path

Design status: `draft_target_delta`.

Target owner and authority:

```text
Component: Fabric Invocation Runtime (CC-5), VerificationPlan runner (Contract M), normalized observation path back to Back.
Fabric validates params against the bound contract, enforces policy gate refs, maps SafetyContext, checks idempotency, dispatches to native provider or Bridge/IFL, returns a normalized InvocationObservation.
Provider success is not verified completion; VerificationObservation is a separate artifact required for submit_result(completed) when the contract/policy/binding declares verification.
```

Request and response artifacts:

```text
InvocationRequest (Contract H):
  resolution_id, binding_id (preferred) or capability_name (fallback)
  params (validated against input_schema_ref), idempotency_key (required for side effects)
  actor_ref, safety_context, policy_gate_refs, expected_effect, verifier_requested

InvocationObservation (Contract H):
  invocation_id, binding_id
  status: success | partial | failed | denied | needs_hil | retryable
  provider_status, result_summary, artifacts, structured_result
  errors (ErrorObservation), recovery_directive (RecoveryDirective)
  verifier_obligation, verification_observation, audit_fields

VerificationPlan (Contract M):
  verification_plan_id, resolution_id, binding_id, invocation_id, verifier_ref
  verifier_method: read_after_write | output_schema | state_compare | audit_receipt | external_receipt | policy_attestation | none_available
  expected_effect, expected_resource_state, readback_capability_ref
  max_staleness, retry_policy, degraded_completion_policy
  required_for_submit_status: completed | partial | audit_only

VerificationObservation (Contract M):
  verification_id, status: verified | degraded_verified | failed | inconclusive | skipped_by_policy | unavailable
  observed_effect, observed_resource_state_ref, audit_receipt_ref
  mismatch_summary, stale_read_summary, degraded_reason, policy_ref, recovery_directive, proof_refs

ErrorObservation / RecoveryDirective (Contract K):
  source_component, code, severity, retryability
  action: ask_hil | retry_with_params | refresh_projection | run_prerequisite_read | choose_from_candidates | block_and_submit | cannot_execute
  suggested_params_patch, required_fields, candidate_refs
```

LLM visibility:

```text
Visible: result_summary, safe structured_result, error user_visible_summary/code/severity/retryability, recovery_directive, verification status and user_visible_summary and mismatch_summary.
Hidden: audit_fields internals, raw stack traces (RawPayloadRef), observed_resource_state_ref contents, audit_receipt_ref contents, secrets/tokens, SafetyMappingEvidence internals.
```

Freshness, completeness, and verification expectations:

```text
VerificationPlan is selected before invocation; VerificationObservation is produced after.
status=success alone cannot produce submit_result(completed) for mutations requiring verification.
read-after-write names the exact readback capability; stale readback cannot silently verify a fresh write.
if verification is unavailable, status=unavailable and completed requires explicit degraded_completion_policy and degraded_reason; silent degraded completion is forbidden (Invariant I21).
reads may parallelize when policy allows; dependent invocations are sequenced via BatchIndependenceValidator (SCA-093).
policy gate refs are re-checked at invocation time (SCA-099).
all side-effecting invocations carry idempotency_key; duplicates after success are no-ops (SCA-101).
```

Typed failure and recovery:

```text
incomplete params -> failed (preflight) -> retry_with_params + suggested_params_patch.
stale binding/resolution -> denied -> refresh_projection.
policy deny -> denied -> block_and_submit or ask_hil.
idempotency conflict in flight -> retryable -> retry_with_params.
provider unavailable -> failed/retryable -> retry_later or block_and_submit.
safety-band mismatch (BTC-004) -> denied via SafetyMappingEvidence -> block_and_submit.
verification failed/inconclusive -> completed blocked; recovery from observation.
budget exhausted -> cannot_execute (BudgetObservation).
terminal error -> failed severity terminal -> block_and_submit or cannot_execute.
```

Proof evidence required before cutover:

```text
M6: Back invokes via resolution_id + binding_id; Fabric validates params and policy; InvocationObservation and RecoveryDirective are normalized before Back sees them.
M7: Fabric dispatches through Bridge without exposing secrets; ConnectorDispatchObservation returned.
M8: Bridge sends IflCommandEnvelope; adapter returns IflResultEnvelope; raw details stay behind RawPayloadRef.
Verification: read_after_write plan selected before create_event; readback runs after success; completed blocked if readback stale/missing.
SafetyMappingEvidence M6: BTC-004 band conflict produces a mapping record; AMBER task on GREEN-min op maps to pass or typed denied with hard_block_reason.
Negative proof: duration_minutes without end -> capability_params_incomplete with recovery, no provider dispatch; duplicate idempotency_key after success is a no-op.
```

Open design questions:

```text
Exact VerificationPlan methods and degraded_completion_policy for V0 (API Decision 9).
Exact TraceContext propagation and AuthorityDecisionRecord storage (API Decision 10; RSV-08).
Exact ManifestAdmissionRecord trust tiers and mid-session revocation behavior (API Decision 12).
BTC-005 BatchIndependenceValidator V0 scope and enforcement mode.
RSV-07: full read-after-write VerificationPlan runner deferred; V0 reserves the verifier_obligation socket.
OQ-CC-002: connector gateway vs adapter runtime as separate kernel roles for local providers.
```

---

## 4. Legacy To Target Migration Map

### TaskDispatch To BackTaskEnvelope

### Back Task JSON To RequestFrame

### discover_capabilities To resolve_situation

### capability_name To binding_id

### ToolResult To InvocationObservation

### submit_result To SubmitResult Authority Gate

### Legacy Safety Band To SafetyContext

---

## 5. Seam Index

### Seam 00 - Feature Flags, Shadow Mode, And Rollback

### Seam 01 - Front Dispatch Contract

### Seam 02 - FSM Canonical Dispatch Boundary

### Seam 03 - Back Execution Envelope Seed

### Seam 04 - RequestFrame Seed

### Seam 05 - resolve_situation Tool Surface

### Seam 06 - Resolver Entry And ResolutionEnvelope

### Seam 07 - Local World Resource Projection

### Seam 08 - Connector And Capability Constitution

### Seam 09 - PolicyBundle And Guide Cards

### Seam 10 - BindingBundle And Capability Registry

### Seam 11 - CandidateUniverse

### Seam 12 - PromptPack And Prompt Injection Timing

### Seam 13 - Allowed Next Action Runtime Enforcement

### Seam 14 - InvocationRequest And Preflight

### Seam 15 - Invocation Param Normalization

### Seam 16 - Native Provider Compatibility Path

### Seam 17 - Bridge ConnectorGateway Path

### Seam 18 - IFL Adapter Runtime Path

### Seam 19 - Manifest Admission And Capability Registration

### Seam 20 - Projection Delta Ingestion

### Seam 21 - ErrorObservation And RecoveryDirective

### Seam 22 - VerificationPlan And VerificationObservation

### Seam 23 - HIL Request And Resume

### Seam 24 - SubmitResult Authority Boundary

### Seam 25 - FSM Outcome Application And Front Presentation

### Seam 26 - Trace, Audit, Prompt Capture, And Proof Records

### Seam 27 - End-To-End Scenario Gates

---

## 6. Seam Detail Template

Use this template for every seam section after research.

### Seam ID And Name

### Design Status

### Current Code Reality

### Target Behavior

### Files To Read

### Files To Edit

### New Files To Add

### Data Contracts

### Feature Flag

### Shadow Mode

### Fallback Behavior

### Step By Step Implementation Topics

### Negative Proof Topics

### Targeted Test Or Probe Command

### Open Design Questions

### Done Means

---

## 7. First Pass Work Packages

### FP-01 - FSM Canonical Dispatch Boundary

### FP-02 - Back Execution Envelope Seed

### FP-03 - RequestFrame Seed

### FP-04 - Legacy Capability Universe And Prompt Cards

### FP-05 - Invocation Request And Preflight

### FP-06 - Invocation Observation Normalizer

### FP-07 - Submit Result Authority Boundary

### FP-08 - End-To-End Proof Slice

---

## 8. Reserved Future Components

### Full Local World Resource Projection Store

### Full ScopeProof

### Model Visible resolve_situation Tool

### PolicyBundle Service

### BindingBundle Persistence Layer

### Bridge And IFL Connector Execution Path

### Read After Write Verification Runner

### Persistent AuthorityDecisionRecord Store

### PromptCaptureRecord Retention Policy

### Cross Domain DomainInstantiationPack Validation

---

## 9. Production Code Home Map

### Concierge Task And Routing Code

### Back Actor And ReAct Code

### Back Tool Schema And Tool Implementation Code

### Fabric Resolver Code

### Fabric Binding And Registry Code

### Fabric Invocation Runtime Code

### Native Family Tool Code

### Bridge Code

### IFL Code

### Contract Schema Code

### Test And Probe Code

---

## 10. POC Promotion Map

### Proof Harness POC

### BackTaskEnvelope POC

### Resolver Prompt Surface POC

### Resolve Situation POC

### Resource Projection POC

### Policy Selector POC

### Binder POC

### Invoke By Binding POC

### Bridge Dispatch POC

### IFL Adapter POC

### Manifest Registration POC

### Projection Delta POC

### Prompt Injection POC

### Resolution Executor POC

### Production Back Runtime POC

---

## 11. Contract Skeletons To Fill

### RequestFrame

### ResolveSituationRequest

### ResolutionEnvelope

### CandidateUniverse

### PromptPack

### PolicyBundle

### BindingBundle

### InvocationRequest

### InvocationObservation

### ErrorObservation

### RecoveryDirective

### VerificationPlan

### VerificationObservation

### HILRequest

### HILResponse

### SubmitResult

### SafetyContext

### TraceContext

### AuthorityDecisionRecord

---

## 12. Scenario Gates To Fill

### Simple Tier 2 Calendar Write

### Missing Required Field

### Duplicate Or Conflict Blocks Write

### Cross Resource Tier 3 Scheduling

### Protected Read Disclosure Gate

### Ambiguous Resource Selection

### Stale Projection Refresh Or Block

### Missing Capability

### Connector Credential Missing

### Bridge Rate Limit Or Circuit Open

### Verification Failure

### Prompt Redaction Failure

---

## 13. Test And Probe Index

### Per Seam Targeted Commands

### Negative Proof Commands

### Live Provider Commands

### Commands Not To Run

---

## 14. Open Design Gap Register

### Kernel Gaps

### FamilyOS Implementation Gaps

### Bridge And IFL Gaps

### Prompt And LLM Gaps

### Policy And Safety Gaps

### Verification Gaps

### Proof And Observability Gaps

---

## 15. Incremental Fill Log

### Research Passes

### Design Decisions

### Promoted Sections

### Deferred Sections

### Rejected Approaches
