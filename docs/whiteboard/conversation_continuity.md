# Conversation Continuity Whiteboard

**Date:** May 15, 2026
**Status:** Whiteboard / architecture direction
**Scope:** K1 Concierge conversation continuity, Front/Back/Planner handoff, ReAct loop continuation, task retry, and tool-budget semantics
**Primary goal:** Make the conversation feel coherent in the human sense: the assistant remembers what it just committed to, can continue a task without sounding like it restarted, can repair failures honestly, and can resume work with the same operational context.

---

## 0. Executive Summary

The current failure is not just a local bug. It exposes a deeper kernel-level issue: K1 Concierge has strong components, but their cognitive state is split across actor-local loops, event payloads, SessionState summaries, and orchestration envelopes. The user experiences this as discontinuity: the assistant says "I am working on that now," then fails, then says "give it another shot" without having a first-class retry path behind those words.

There are two layers to fix:

1. **Immediate execution break:** Multi-intent tasks are routed to MEDIUM tier, then into the orchestrator's direct capability validation path. That path expects exact Fabric capability names. The Front LLM can emit natural-language capability labels. The result is `dispatch_medium.capability_not_found` before Back ever runs. LOW tier works because Back performs `discover_capabilities -> invoke_capability` at runtime.

2. **Architectural continuity gap:** Front, Back, and Orchestrator do not share a durable, compact "work context". Each loop has its own message list. Front's reasoning trace is discarded at dispatch. Back starts from trimmed history plus task JSON. Retry is not a primitive. Budgets are per-loop execution limits, not user-commitment budgets. Partial progress is not elevated to the conversation.

The solution is not "make one giant infinite ReAct loop." That would be expensive, hard to test, unsafe, and hard to recover. The kernel-grade solution is a **Conversation Continuity Kernel**: durable task lineage, compact operational scratchpads, capability binding before execution, first-class retry/resume, and budget checkpoints that preserve partial results.

In human terms: the assistant needs shared common ground, explicit commitments, repair memory, and turn-taking discipline. In kernel terms: every user-facing commitment needs a durable `WorkFrame` that survives actor boundaries.

Important grounding note: `WorkFrame`, `PlanningFrame`, `DecisionFrame`, `TaskContinuationContext`, and agent continuity envelopes in this document are **proposed continuity-kernel concepts**. They are not current dataclasses or protocols in `k1/fabric`, `k1/orchestrator`, or `k1/planner`.

---

## 0.1 Grounding Pass: Actual Fabric, Orchestrator, And Planner Reality

This section is based on a read-only pass through the wiring/state/contract markdown and code in:

- [k1/fabric](../../k1/fabric)
- [k1/orchestrator](../../k1/orchestrator)
- [k1/planner](../../k1/planner)

### Fabric reality

Fabric is a capability execution substrate, not a conversation-continuity owner.

Current code has:

- `CapabilityRequest` / `CapabilityResult` / `CapabilityContract` / `AgentContract` / `AgentResponsePayload` in [k1/fabric/types.py](../../k1/fabric/types.py).
- An AGENT provider path and `BuildAgentHandler`/agent pool machinery under [k1/fabric/providers](../../k1/fabric/providers) and [k1/fabric/core/agent_builder.py](../../k1/fabric/core/agent_builder.py).
- A Fabric-level HIL gate through `IHILPort.gate_capability()` inside [k1/fabric/fabric.py](../../k1/fabric/fabric.py), before capability execution.
- Conscience gating before HIL when a conscience port is available.
- Read-only SessionState access through `ISessionStateReader`.

Current code does **not** have:

- `AgentContinuityEnvelope`;
- `WorkFrame` inside Fabric;
- an in-agent user clarification loop;
- typed Fabric-level extraction of `AgentResponsePayload` from `CapabilityResult.data`;
- Fabric-owned cross-call conversation memory.

So the target architecture must treat Fabric as the execution/runtime layer. Continuity has to be carried by Concierge/Planner/Orchestrator payloads and session state, then passed into Fabric through existing request/context fields or new explicit contracts.

### Orchestrator reality

Orchestrator's current execution unit is a `PlanStep` inside a `CommittedPlan`, not a spawned conversational agent.

Current code has:

- MEDIUM dispatch in [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py): validates 1-2 exact Fabric capability names and executes serial `CapabilityRequest`s.
- HIGH dispatch: sends a `PlanRequest` to Planner, parks a pending plan context, then receives `k1.planner.plan.ready.v1` asynchronously.
- `CommittedPlan`, `PlanStep`, `StepResult`, `AggregatedResult`, compensation fields, and DAG execution contracts in [k1/orchestrator/types.py](../../k1/orchestrator/types.py).
- ConstraintResolver capability validation and alternative search for committed plans.
- HIL-related ports and delta hooks, but not a fully wired agent-originated clarification conversation.

Current code does **not** have:

- Orchestrator-spawned Fabric agents as a first-class runtime path;
- `WorkFrame` or `PlanningFrame` state;
- degradation from MEDIUM `capability_not_found` to Back discovery;
- a bidirectional planner dialogue during MEDIUM execution;
- user-facing suggestion events emitted by orchestrated agents.

So when this document says "orchestrated agents" as a future target, the grounded current equivalent is: orchestrated `PlanStep`s invoking named Fabric capabilities through `CapabilityRequest`.

### Planner reality

Planner is already closer to the target than the earlier whiteboard implied, but it is per-plan, not cross-conversation.

Current code has:

- A four-stage pipeline: SKETCH, EXPAND, VALIDATE, COMMIT.
- SKETCH agentic tool-use with `discover_capabilities`, `query_session_context`, `recall_long_term_memory`, and `find_prompts`.
- EXPAND tool/schema work and deterministic enrichment from `CapabilityContract`.
- VALIDATE deterministic checks plus LLM arbiter plus HIL approval for caution/unsafe plans.
- HIL clarification in SKETCH if `needs_clarification=True`.
- A headless `PlannerAgent` mailbox loop, not a chat persona.

Current code does **not** have:

- `PlanningFrame` or `DecisionFrame` state;
- cross-request planner continuity;
- ask-human points embedded in `CommittedPlan`;
- user-facing suggestions/tradeoff payloads;
- a fully correct direct schema lookup for `get_capability_schema` (current path is partly semantic and should become registry lookup).

So the target architecture should not pretend Planner already owns continuity. Planner has the ingredients: memory tools, capability discovery, schema-ish expansion, HIL, validation, and commit. The missing layer is durable continuity above and around each plan request.

### Proactivity reality

This section is based on a read-only pass through:

- [k1/concierge/_scan_temp](../../k1/concierge/_scan_temp) as stale clues;
- current Concierge FSM/session/experience code under [k1/concierge](../../k1/concierge);
- [architecture_diagrams/bridge/bridge_architecture_v2.mmd](../../architecture_diagrams/bridge/bridge_architecture_v2.mmd);
- [docs/whiteboard/whiteboard_family_apps.md](whiteboard_family_apps.md);
- K1 family tools under [k1/tools/family](../../k1/tools/family).

Current code has:

- Concierge task-completion proactivity: `task.complete -> PROACTIVE_WAKE -> DELIVERING -> Front`.
- Concierge same-turn deferred delivery: Back completes during `COMPANIONING`, FSM stores the result, then flushes it after a short delay if the user stays idle.
- Concierge proactive fill: `ExperienceLayer.tick()` can publish `k1.proactive.fill.v1` while work is running.
- HITL clarification: task suspension moves the FSM to `CLARIFYING_WORKER`; Front asks the question and resumes Back.
- K1 family tool state-sync events: mutating family tool actions emit tool-state change events for UI/app refresh.
- K1 reminders have a proactive-shaped `fire_reminder` action that includes push payload fields.
- Bridge-generated K0 proactive contracts for `k0.proactive.signal.v1` and `curiosity.intent.v1`.

Current code does **not** have:

- a K1 reminder scheduler loop that calls `fire_reminder` when due;
- an APNs/FCM/SMS notification relay consuming reminder push payloads;
- Concierge subscribing to family `tool_state.changed` as proactive candidates;
- K0 SSE transport wired end-to-end for live K0-originated proactive events;
- a K0 attention manager actively emitting `k0.proactive.signal.v1`;
- a K0-signal-to-K1-FSM adapter that converts bridge SSE signals into Concierge proactive delivery;
- one shared routing contract for Concierge proactivity, family app proactivity, notification delivery, and K0 long-horizon signals.

Important grounding: K1 is edge-first and must remain self-sufficient. K0 is an enhancement layer for long-horizon memory, pattern, and curiosity signals, not a live dependency for normal family operation.

---

## 1. Observed Failure From Screenshot And Logs

Screenshot flow:

1. User asks a social greeting. Front responds directly.
2. User asks to give Riley a bedroom-cleaning task. Front dispatches work. Back completes it. UI says the task was scheduled.
3. User asks to change it to 8:00 PM and also add a calendar event. Front dispatches a multi-intent MEDIUM task. Orchestrator fails immediately with `capability_not_found`. Back never runs.
4. User says "give a shot once again and also check if calendar is populated." Front dispatches another fresh MEDIUM task. The same orchestrator failure repeats.

Important conclusion:

- The prior Back-path fixes are not reached in turns 3 and 4.
- The phrase "give it another shot" is generated by Front in error mode. It sounds like a supported retry affordance, but the system does not have a first-class retry path.
- The UI shows continuity at the chat level, but execution state is discontinuous underneath.

---

## 2. Current Architecture Facts

### 2.1 Front Dispatch Tiering

`dispatch_task` derives tier from task shape:

- Single intent and no plan -> LOW.
- Multiple intents, `plan=True`, or `depends_on` -> MEDIUM.
- Explicit `complexity="HIGH"` with planning signals -> HIGH.

Reference: [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1045).

This is reasonable as a first heuristic, but the failure mode is severe: MEDIUM bypasses the Back actor path that knows how to discover and invoke capabilities from natural-language intent.

### 2.2 MEDIUM Orchestrator Path

MEDIUM dispatch validates capability names before execution:

- It requires 1-2 capability names.
- It queries Fabric registry by exact capability name.
- If any capability is missing, it returns `ProcessResult.FAILED`.

Reference: [k1/orchestrator/orchestration/orchestrator_service.py](../../k1/orchestrator/orchestration/orchestrator_service.py#L1516).

This path is kernel-solid if the envelope already contains canonical capability names. It is not robust if the envelope comes from conversational LLM output.

### 2.3 Back Prompt And Scratchpad

Back builds a fresh prompt per task from:

- Back system prompt.
- last N `history_active` entries.
- task JSON.

Reference: [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L690).

Back history is intentionally trimmed. It includes user/final/HITL response entries and truncates text to 500 characters.

Reference: [k1/concierge/react/history.py](../../k1/concierge/react/history.py#L72).

This keeps Back neutral and efficient, but it means Back does not inherit Front's full operational context.

### 2.4 TaskDispatch Carries Output, Not Process

`TaskDispatch.reference_context` carries Front-resolved pronouns and references, for example `{"it": "Vineyard Inn"}`.

Reference: [k1/concierge/task/dispatch.py](../../k1/concierge/task/dispatch.py#L48).

That is the output of Front's reasoning, not the reasoning trace, evidence, failed attempt, or retry lineage.

### 2.5 Per-Task Back Dispatcher Budget

Back creates a fresh dispatcher per task tier.

Reference: [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L155).

This prevents one task from draining another task's budget. That is good isolation. But it also means there is no conversation-level budget ledger and no continuity of tool usage across retry attempts unless deliberately captured elsewhere.

### 2.6 Resume Has Real Continuity, But Only For Suspended Tasks

HITL resume is the strongest existing continuity path:

- `ResumeContext` carries `findings_so_far`, `tool_history`, `remaining_budget`, `recovery`, and `react_checkpoint`.
- Back resumes with prior messages and an instruction to continue.

References:

- [k1/concierge/protocols/hitl_wiring.py](../../k1/concierge/protocols/hitl_wiring.py#L100)
- [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L930)

This is the design pattern to generalize beyond HITL. Failed tasks and explicit retries need the same quality of continuity.

### 2.7 Dispatcher No-Work Guard

Back rejects `submit_result(complete)` if the model has not invoked any capability while there is still budget remaining.

Reference: [k1/concierge/tools/dispatcher.py](../../k1/concierge/tools/dispatcher.py#L633).

This is correct. It prevents fake success. But if the model burns budget on discovery loops or if the wrong tier bypasses Back entirely, the guard cannot produce user-facing coherence by itself.

### 2.8 Budget Exhaustion Drops Too Much Meaning

At Back budget exhaustion, `react_loop` returns `missing_submit_result` with a machine error and no first-class partial result summary.

Reference: [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L1753).

This turns an execution-management failure into a conversational failure. A human would say, "I found the task, but I could not update it yet because X." The kernel currently tends to say, "snag."

---

## 3. The Cognitive Science Frame

Human conversation feels continuous because people maintain several invisible structures:

1. **Common ground:** both sides know what has already been established.
2. **Commitments:** when someone says "I will do X," that becomes an obligation until fulfilled, cancelled, or renegotiated.
3. **Referent continuity:** words like "it," "that," "again," and "the same one" point to an active shared object.
4. **Repair:** when something fails, the next move is grounded in the failure, not a fresh unrelated attempt.
5. **Prospective memory:** the speaker remembers unfinished obligations.
6. **Epistemic status:** the speaker distinguishes known facts, assumptions, attempts, uncertainty, and blocked state.
7. **Turn-taking timing:** acknowledgements, status updates, and final answers arrive in a rhythm that matches what the user expects.

The current system has pieces of these, but they are distributed:

- `history_active` provides text continuity.
- `task_state` provides status continuity.
- `task_artifacts` provides result continuity.
- `reference_context` provides some referent continuity.
- `react_checkpoint` provides same-task HITL continuity.

The missing layer is a canonical object that says:

> "This is the active work thread, this is what the assistant promised, this is what we tried, this is what succeeded, this is what failed, this is what the next attempt should reuse, and this is how to talk about it."

---

## 4. Design Principle: Shared State, Not Shared Chain-Of-Thought

The phrase "same thought process" should not mean passing raw hidden reasoning or running one unbounded monolithic loop. In a production kernel, the safer and more testable version is:

> Share compact operational state, evidence, commitments, tool summaries, and plan checkpoints across actors.

Do not share:

- raw chain-of-thought;
- provider-specific hidden messages;
- unbounded scratchpads;
- conversational persona inside Back;
- mutable global state with no owner.

Do share:

- user goal;
- active commitment;
- current work frame;
- canonical referents;
- capability bindings;
- attempted tool calls and outcomes;
- partial results;
- blocker type;
- retry policy;
- remaining budget;
- next suggested action;
- user-facing status language.

That is how the system looks continuous while still being auditable and recoverable.

---

## 5. Proposed Architecture: Conversation Continuity Kernel

### 5.1 New Canonical Object: `WorkFrame`

Every user-facing task commitment should create or update a `WorkFrame`.

Conceptual shape:

```yaml
WorkFrame:
  work_id: work-...
  conversation_thread_id: thread-...
  user_goal: "move Riley's bedroom task to 8 PM and add/check calendar"
  visible_commitment: "I'm updating Riley's bedroom task and checking the calendar."
  owner: front
  execution_owner: back | orchestrator | planner
  status: proposed | accepted | running | blocked | suspended | partial | complete | failed | cancelled
  lineage:
    parent_work_id: work-...
    retry_of: task-...
    user_retry_phrase: "give a shot once again"
  referents:
    it: "Clean Bedroom task for Riley"
    calendar: "family calendar"
  intent_bundle:
    - action: update_task
      domain: tasks
      target: "Clean Bedroom"
      params:
        assignee: riley
        start_time: "2026-05-15T20:00:00"
    - action: list_events_or_create_event
      domain: calendar
      params:
        date: "2026-05-15"
  capability_bindings:
    - intent_index: 0
      capability_name: tool.execute.tasks.update_task
      confidence: 0.91
      binding_source: discover_capabilities
    - intent_index: 1
      capability_name: tool.read.calendar.list_events
      confidence: 0.88
      binding_source: discover_capabilities
  evidence:
    - type: tool_result
      tool: tool.read.tasks.list_tasks
      summary: "Found Riley's Clean Bedroom item at 6:00 PM."
    - type: failure
      code: capability_not_found
      summary: "MEDIUM route received non-canonical capability name."
  partial_results:
    - "Task was found."
  blockers:
    - code: missing_capability_binding
      retryable: true
      recommended_route: back_capability_discovery
  budgets:
    commitment_budget: 12
    used_calls: 3
    remaining_calls: 9
    reserve_for_submit_or_repair: 2
  speech_state:
    last_ack: "I'm working on that now."
    next_status_if_slow: "I found Riley's task and am checking the calendar now."
    final_answer_style: concise
```

This object is not a prompt. It is a kernel state contract.

### 5.2 `WorkFrame` Ownership

Ownership should be explicit:

- **Front owns the social commitment.** Front is responsible for what the user was told.
- **Back owns direct execution.** Back should remain a neutral executor.
- **Orchestrator owns multi-step scheduling and dependency management.** It should not depend on free-text capability names.
- **Planner owns high-level plan synthesis.** It emits plan structure and constraints, not conversational persona.
- **FSM owns flow state.** It decides whether the conversation is listening, companioning, delivering, clarifying, or interrupting.
- **Continuity store owns lineage and recovery context.** It is the durable substrate connecting them.

### 5.3 New Contract: `TaskContinuationContext`

Add a compact continuation block to task dispatches and retries.

This is a smaller, execution-safe sibling of `WorkFrame`:

```yaml
TaskContinuationContext:
  work_id: work-...
  retry_of_task_id: task-...
  user_goal: str
  last_visible_commitment: str
  referents: dict
  prior_attempt_summary: str
  prior_tool_summaries: list
  known_capability_candidates: list
  partial_results: list
  blockers: list
  next_route_hint: back_capability_discovery | orchestrator_exact_caps | planner
```

This should cross Front -> Back -> Orchestrator boundaries. It should be bounded, structured, and redaction-safe.

---

## 6. Execution Continuity: ReAct Loops Can End, Work Must Continue

The user is right that the loop should feel continuous. The implementation detail is subtle:

- A ReAct loop may end for actor boundaries, cost control, HITL, async delivery, or crash recovery.
- The **work episode** must not end unless the user commitment is complete, cancelled, blocked with an honest question, or explicitly deferred.

So the rule is:

> ReAct loops are disposable. WorkFrames are durable.

This gives the system human-feeling continuity without unsafe infinite loops.

### 6.1 Loop Exit Rules Should Emit Continuity Events

Every loop exit should update the active `WorkFrame`:

| Loop exit | Current behavior | Continuity behavior |
| --- | --- | --- |
| Front dispatches task | Turn ends with ack | Create/update `WorkFrame`, record visible commitment |
| Back completes | Emit task complete | Attach final results and close `WorkFrame` |
| Back needs human | Suspend task | Attach precise blocker and question |
| Back budget exhausted | Emit failure | Attach partials, tool summary, next repair route |
| Orchestrator capability_not_found | Emit failure | Rebind through capability resolver or downgrade to Back path |
| Front error response | LLM says "snag" | Must ground response in `WorkFrame.blockers` |

### 6.2 Bounded Continuation Instead Of Infinite Continuation

Do not allow unbounded "just keep thinking." Use explicit continuation limits:

- `commitment_budget`: total tool calls allowed for the user-visible commitment.
- `loop_budget`: calls allowed for a single actor invocation.
- `repair_budget`: reserved calls for checkpoint, summarize, ask human, or submit partial result.
- `handoff_budget`: tokens/calls allowed to compress state for the next actor.

The work can span multiple loops as long as each loop writes a checkpoint.

### 6.3 Conversation-Level Budget Semantics

Current per-task budgets are isolation budgets. Keep them. Add commitment budgets above them.

Example:

```yaml
User commitment: "reschedule task and add/check calendar"
commitment_budget: 12
front_budget: 3
back_budget: 7
repair_reserve: 2
```

If Back reaches `remaining_calls == repair_reserve`, it must stop normal exploration and do one of:

- submit complete;
- submit partial complete;
- submit needs_human with a precise question;
- checkpoint and request continuation;
- escalate to planner/orchestrator with evidence.

Budget exhaustion should never erase the work story.

---

## 7. Capability Binding: The Immediate Kernel Fix Direction

The immediate observed bug is capability binding.

### 7.1 Current Problem

LOW tier:

```text
Front -> dispatch_task -> Back -> discover_capabilities -> invoke_capability -> submit_result
```

MEDIUM tier:

```text
Front -> dispatch_task -> Orchestrator _dispatch_medium -> exact registry lookup -> fail
```

The MEDIUM path assumes a canonical capability envelope. The Front conversation path does not guarantee one.

### 7.2 Desired Rule

No actor should execute or validate free-text capability names as if they are registry keys.

Every task must go through one of:

1. **Bound intent:** `intent -> capability_name` resolved by capability resolver.
2. **Direct exact capability:** already canonical and registry-verified.
3. **Discovery required:** route to Back or binder before orchestrator validation.

### 7.3 Capability Binding Pipeline

```text
TaskDispatch
  -> IntentNormalizer
  -> CapabilityBinder
       - uses domains/actions/entities
       - calls registry search/discovery
       - returns canonical capability candidates
  -> RouteSelector
       - LOW direct Back
       - MEDIUM direct orchestrator only if all capabilities are canonical
       - otherwise Back discovery path or Planner
  -> Executor
```

### 7.4 MEDIUM Tier Options

Ranked options:

1. **Best long-term:** MEDIUM route accepts `IntentBundle`, not raw capability names. It calls a binder before `_dispatch_medium` registry validation.
2. **Fast safe fix:** If MEDIUM capabilities are missing or non-canonical, degrade to Back with `next_route_hint=back_capability_discovery` instead of failing.
3. **Strict schema fix:** Front's `dispatch_task` schema cannot include free-text capabilities. It emits intents only; binding happens downstream.
4. **Temporary fallback:** On `capability_not_found`, retry once through Back discovery before surfacing failure.

The kernel direction should be option 1 plus option 2 as graceful degradation.

---

### 7.5 Back Execution Profiles: Activity-Specific Guidance Without New Agents

The user concern is valid: Back already has the right universal execution loop -- find capability, inspect schema, ask the human if required details are missing, execute, verify, and submit. The missing layer is not necessarily a new Fabric agent for every domain. The missing layer is a bounded way to inject domain-specific operating guidance into Back for the current task.

Call this a **Back Execution Profile** or **Activity Prompt Pack**.

This sits between generic Back execution and full Fabric meta-agent creation:

```text
Generic Back ReAct loop
  -> always available
  -> find capability, inspect schema, HIL if needed, invoke, verify

Back Execution Profile
  -> selected per task or per intent
  -> teaches Back how to behave for calendar/tasks/reminders/email/finance/etc.
  -> does not register a new capability or agent

Fabric Meta-Agent
  -> registered specialist capability/agent
  -> own contract, tool scope, prompt template, lifecycle, output payload
  -> best for recurring, multi-step, or truly specialist work
```

#### Current Code Reality

The current code is close to supporting this, but the profile object does not exist yet.

Existing hooks:

- `TaskIntent.domain` already exists as an optional domain hint in [k1/concierge/task/intent.py](../../k1/concierge/task/intent.py).
- Front's `dispatch_task` schema already lets each intent include `domain` in [k1/concierge/tools/schemas_front.py](../../k1/concierge/tools/schemas_front.py).
- `execute_dispatch_task()` normalizes intents, derives tier, builds `TaskDispatch`, and preserves `reference_context` in [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py).
- `TaskDispatch` carries `reference_context` and `context_snapshot`, but no explicit `execution_profile` field yet in [k1/concierge/task/dispatch.py](../../k1/concierge/task/dispatch.py).
- `back_handler()` reads one SessionState snapshot, computes budget, and calls `build_back_prompt()` once before entering the ReAct loop in [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py).
- `build_back_prompt()` is a simple template-substitution path, not the Front `DynamicPromptBuilder`; this makes it a clean insertion point for a small selected profile block in [k1/concierge/prompt/back_prompt.py](../../k1/concierge/prompt/back_prompt.py).
- Back already has the right generic tools: `discover_capabilities`, `invoke_capability`, `batch_invoke_capabilities`, and `submit_result` in [k1/concierge/tools/schemas_back.py](../../k1/concierge/tools/schemas_back.py).
- `discover_capabilities` already returns ranked contracts with domains and prompt schemas, and caches capability contracts by name in [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py).
- `invoke_capability` already checks the contract for missing required params and returns a structured recovery/HIL contract before executing when inputs are incomplete.
- Fabric `CapabilityRequest.context_override` exists in [k1/fabric/types.py](../../k1/fabric/types.py), but current `CapabilityFabric._build_context()` does not pass it into `ContextBuilder.build()` in [k1/fabric/fabric.py](../../k1/fabric/fabric.py). So the first version should not depend on Fabric context override for profile propagation.

Implication: the lowest-risk implementation is to select a profile before Back prompt construction, inject a small `execution_profile_block` into Back's system prompt, and continue using Fabric discovery/schema/HIL as the authority boundary.

#### Target Contract

Conceptual profile shape:

```yaml
BackExecutionProfile:
  profile_id: calendar.v1
  display_name: Calendar Operations
  domains: [calendar, scheduling]
  trigger_actions:
    - create_event
    - update_event
    - check_calendar
    - find_availability
  capability_markers:
    - adapter:calendar
    - tool.read.calendar.*
    - tool.execute.calendar.*
  prompt_block: |
    Calendar operating protocol:
    1. Treat calendar as system-of-record state. Never answer from memory alone.
    2. For updates, list/search events first unless an exact event_id is already bound.
    3. Required facts usually include date, time, timezone, calendar/owner, title, and attendees when relevant.
    4. If multiple matching events exist, ask the user to choose.
    5. Before creating a new event, check for likely duplicates.
    6. After create/update/delete, verify by reading the event/calendar back.
    7. Do not send invitations or notify attendees unless explicitly requested or HIL-approved.
  schema_discipline:
    - discovered contract schema overrides this profile
    - ask human for missing required fields that cannot be inferred safely
  verification_steps:
    - read_back_after_write
    - summarize_final_record_id_and_time
  forbidden_patterns:
    - guessing capability names
    - creating duplicate events without checking
    - using memory as calendar truth
```

Equivalent profiles can exist for:

- `tasks.v1`: find existing task before update, disambiguate assignee/title, verify status/due time after mutation.
- `reminders.v1`: require recipient/time/timezone/recurrence, distinguish reminder from calendar event, verify scheduled reminder.
- `email.v1`: draft before send unless user explicitly asked to send, preserve recipients/subject, never impersonate, ask before external send.
- `finance.v1`: require permissioned data access, explain uncertainty, no money movement/purchase/cancellation without explicit confirmation.
- `health.v1`: no diagnosis, use records/tools as evidence, route regulated uncertainty to HIL or professional-care guidance.
- `connectors.generic.v1`: check connector availability/auth, inspect schema, respect side-effect policy, verify after mutation.

These profiles are not capability names and must not contain hardcoded capability slugs as execution authority. They are procedure, not registry truth.

#### Back Profile Selector

The selector is the hardest part because a wrong profile can steer Back toward the wrong workflow. It must be deterministic, explainable, and conservative.

Inputs:

```yaml
BackProfileSelectionInput:
  task_id: str
  tier: LOW | MEDIUM | HIGH
  intents:
    - action: str
      domain: str | null
      params: dict
  reference_context: dict
  workframe_summary: dict | null
  known_capability_bindings: list | null
  prior_failure_frame: dict | null
```

Future optional input after binding/discovery:

```yaml
  discovered_capabilities:
    - name: tool.execute.calendar.create_event
      domains: [PRODUCTIVITY, calendar]
      schema:
        capabilities: [write, adapter:calendar]
        required_inputs: [...]
```

Output:

```yaml
BackProfileSelection:
  selected_profiles:
    - profile_id: calendar.v1
      intent_indexes: [1]
      confidence: 0.86
      evidence:
        - source: intent.domain
          value: calendar
        - source: action_lexicon
          value: "add event to calendar"
  fallback_profile: system_of_record.generic.v1
  ambiguity: none | low | high
  prompt_block: str
```

Selector scoring should prefer authoritative evidence over language guesses:

| Evidence | Weight | Notes |
| --- | ---: | --- |
| Existing canonical capability binding | highest | If a bound capability domain/adapter exists, use it. |
| Discovered capability contract domain/adapter marker | highest | Registry evidence beats Front's domain guess. |
| `TaskIntent.domain` from dispatch | high | Useful but still LLM-provided. |
| WorkFrame prior route / previous successful capability | high | Strong for retries/follow-ups. |
| Action/entity lexical match | medium | "calendar", "event", "invite", "task", "remind". |
| `reference_context` keys | low-medium | Helpful for artifacts like `event_id`, `task_id`, `assignee`. |
| Global conversation domain | low | Too broad; should not dominate. |

Conservative thresholds:

```yaml
if top_score >= 0.75 and score_gap >= 0.20:
  select top profile
elif bundled task has <= 2 clear profiles:
  select per-intent profiles and label them by intent index
elif top_score >= 0.45:
  select generic system_of_record profile plus weak domain hint
else:
  select no domain profile; use generic Back prompt only
```

For bundled requests, profile selection should be per intent, not per whole task. Example: "move Riley's task to 8 PM and add a calendar event" should select:

```yaml
selected_profiles:
  - profile_id: tasks.v1
    intent_indexes: [0]
  - profile_id: calendar.v1
    intent_indexes: [1]
```

The rendered prompt block must stay compact:

```text
== ACTIVITY EXECUTION PROFILES ==
Intent 0 uses tasks.v1.
Required discipline: read/list existing task before update; disambiguate if multiple matches; verify final task state.

Intent 1 uses calendar.v1.
Required discipline: check duplicates; require date/time/timezone/calendar; verify event after write; invitations require explicit request or approval.

Registry schemas and tool recovery contracts override these profiles.
```

#### Two-Stage Selection

There are two different selector moments.

Stage A: pre-discovery selector.

```text
dispatch_task result
  -> normalized TaskIntent list
  -> BackProfileSelector.select_from_task(...)
  -> TaskDispatch carries selected profile summary
  -> back_handler builds Back prompt with execution_profile_block
```

This helps Back choose the right discovery query and workflow from the first iteration.

Stage B: post-discovery confirmation.

```text
Back calls discover_capabilities
  -> registry returns contracts with domains/schema/capability markers
  -> discovered schemas override profile assumptions
  -> if discovery contradicts the selected profile, Back follows registry evidence
```

In a later version, Stage B could emit a `BackControlEvent(event_type="profile_update")` into the running loop, because the ReAct loop already supports control events. But MVP does not need that. The first version can be simple: profile is a starting procedure; registry contracts are authority.

#### Code Insertion Plan

MVP, lowest blast radius:

1. Add `k1/concierge/prompt/back_profiles.py` with:
   - `BackExecutionProfile` dataclass;
   - static profile registry;
   - deterministic `select_back_execution_profiles(task, reference_context, workframe_summary=None)`;
   - `render_execution_profile_block(selection)`.
2. Extend `build_back_prompt()` to accept `execution_profile_block: str = ""` and inject it after the generic ReAct protocol but before tool usage rules.
3. In `back_handler()` and `back_resume_handler()`, compute the selection from the task payload before calling `build_back_prompt()`.
4. Preserve selected profile metadata in `task.reference_context._execution_profiles` or add a first-class `execution_profiles` field to `TaskDispatch`.
   - Fast path: store under `reference_context` because it already survives serialization.
   - Better path: add an explicit `execution_profiles` field to `TaskDispatch` and make `to_dict()` / `from_dict()` preserve it.
5. Add selector unit tests with synthetic tasks:
   - calendar create/check;
   - task update;
   - reminder schedule;
   - email draft/send;
   - ambiguous "schedule" task with no domain;
   - bundled task+calendar request.
6. Add Back prompt tests proving only the selected profile is injected and the block stays below a fixed token/character budget.
7. Add one integration regression for Riley task update + calendar check to prove the profile helps Back choose task/calendar discovery without making the MEDIUM routing bug worse.

Longer-term, once `WorkFrame` exists:

```text
WorkFrame.intent_bundle
  -> CapabilityBinder binds candidates
  -> BackProfileSelector uses bindings + domains + prior lineage
  -> TaskContinuationContext carries selected profile ids and evidence
  -> Back prompt receives compact profile block
```

#### Relation To Fabric Meta-Agent Creation

Back Execution Profiles should not compete with Fabric meta-agents. They answer different questions.

Use a Back profile when:

- the task is one user commitment;
- the generic Back loop can execute it with normal capability calls;
- the domain only needs procedural discipline;
- no persistent specialist identity or reusable agent contract is needed.

Use Fabric meta-agent creation when:

- the task needs a specialist worker with its own tool scope;
- multiple capabilities and prompts need to be composed into a reusable unit;
- the output should use `AgentResponsePayload` or a specialist contract;
- Planner needs to create and execute agents inside a DAG.

Example:

```text
"Move Riley's bedroom task to 8 PM and add a calendar event"
  -> Back profiles: tasks.v1 + calendar.v1

"Can I afford my diabetes medication this month?"
  -> Planner + Fabric meta-agents: diabetes_companion + budget_analyzer
```

#### Safety Invariants

1. Profiles never grant tools. Tool access still comes from Back tier allowlists and Fabric policy.
2. Profiles never authorize side effects. User request, Fabric HIL, domain safety, and capability contracts decide authority.
3. Profiles never replace schema inspection. Discovered capability schemas are authoritative.
4. Profiles never contain hidden chain-of-thought. They are explicit operating procedures.
5. Profiles must be small. If many profiles are needed, escalate to Planner or meta-agent creation.
6. Profiles must be explainable in logs: selected profile, score, evidence, and fallback reason.
7. Wrong-profile risk must fail safe: generic system-of-record behavior is better than a confident wrong domain.

#### Acceptance Tests

Back profile selector tests should pass when:

- `domain="calendar"` plus action "add event" selects `calendar.v1`.
- action "change Riley's bedroom task to 8 PM" selects `tasks.v1`, even if the word "schedule" appears.
- bundled task+calendar request selects two per-intent profiles, not one global profile.
- ambiguous "schedule it" with weak evidence selects only generic system-of-record behavior.
- canonical capability binding or discovery evidence overrides an incorrect Front-provided domain.
- profile prompt injection does not add guessed capability names.
- profile selection survives HITL resume through the original task payload.
- no selected profile can bypass Fabric HIL for external sends, purchases, finance actions, health-sensitive actions, or destructive updates.

---

## 8. First-Class Retry

Human coherence requires retry to be a real operation, not a conversational phrase.

### 8.1 New Primitive: `retry_work` Or `retry_task`

Conceptual API:

```yaml
retry_work:
  work_id: work-...
  retry_of_task_id: task-...
  user_modifications:
    - "also check if calendar is populated"
  strategy: automatic | ask_before_side_effects | dry_run_first
```

### 8.2 Retry Classification

When the user says:

- "try again"
- "give it another shot"
- "do it once more"
- "same thing but..."
- "also check..."

Front should resolve this as a continuation if there is an active or recent failed `WorkFrame`.

### 8.3 Retry Should Not Repeat The Same Fault Blindly

If the prior attempt failed with `capability_not_found` in MEDIUM route, the retry strategy should not re-enter the same exact MEDIUM path. It should set:

```yaml
next_route_hint: back_capability_discovery
blocked_route: orchestrator_medium_exact_capability_validation
```

### 8.4 Retry Should Preserve User-Facing Accountability

Bad:

```text
I'm working on that now.
I ran into a snag...
I'm working on that now.
I ran into a snag...
```

Better:

```text
I'll retry the same Riley task update, and I'll check the calendar this time too.
```

Then, if blocked:

```text
I found the previous attempt, but the scheduler route could not bind the update tool. I can retry through the task tools directly.
```

The exact wording should be tuned by Front, but the point is that Front must be grounded in retry state.

---

## 9. Error And Partial-Result Semantics

The system needs fewer generic "snag" endings.

### 9.1 Error Frames

Every task failure should produce a structured `FailureFrame`:

```yaml
FailureFrame:
  code: capability_not_found | missing_submit_result | schema_error | safety_block | user_cancelled | timeout
  layer: front | back | orchestrator | fabric | provider | tool
  retryable: true
  user_visible_summary: "I could not bind the calendar update tool."
  internal_summary: "dispatch_medium registry lookup failed for cap_name=..."
  partial_results: list
  next_repair_actions:
    - back_discover_capabilities
    - ask_user_clarification
    - escalate_to_planner
```

### 9.2 Partial Results Are First-Class

If Back discovered capabilities, found task IDs, listed calendar events, or completed one of two intents, those facts must be preserved.

Partial progress should update:

- `WorkFrame.partial_results`;
- `task_artifacts` if durable;
- `task_state` with partial status;
- Front error-mode scenario data.

### 9.3 Budget Exhaustion Must Become Repair, Not Collapse

When Back is near budget exhaustion, it should be forced toward a terminal repair action:

- `submit_result(complete)` if done;
- `submit_result(partial)` if some work is done;
- `submit_result(needs_human)` if one precise input is missing;
- `checkpoint_for_continuation` if the next actor/loop should continue.

Generic `missing_submit_result` is an internal invariant failure. It should not be the only thing Front receives.

---

## 10. Front, Back, Planner: Human-Like Coherence Without Persona Leakage

### 10.1 Front Is The Only Social Voice

Back should not become conversational. Planner should not become conversational. Human-like UX comes from Front owning:

- commitments;
- tone;
- repair language;
- emotional pacing;
- what the user has been told.

Back and Planner should produce structured facts and recommendations.

### 10.2 Back Is A Neutral Executor With Continuation Context

Back should receive enough operational state to avoid restarting:

- prior attempt summary;
- known referents;
- capability candidates;
- blocker and retry route;
- partial results;
- completed side effects.

Back should not receive persona overlays, dynamic identity blocks, or affective small-talk content.

This matches the existing M6 direction: Front gets identity and narrative continuity; Back remains executor.

### 10.3 Planner Owns Plan Deliberation, Not Social Voice

Planner should receive:

- goal;
- constraints;
- capabilities;
- evidence;
- partials;
- open questions.

Planner should return:

- plan graph;
- bound steps;
- dependencies;
- compensation strategy;
- ask-human points.

Planner should not own social messages, but Planner must still be an active participant in the work conversation. The user should experience Planner as a competent specialist working with them through Front.

That means Planner must be allowed to do the same continuity work a real planning expert would do:

- read relevant memory and prior `WorkFrame` context;
- inspect available capabilities before promising a step;
- inspect capability schemas before constructing parameters;
- identify missing required inputs;
- ask precise questions when required inputs cannot be inferred;
- propose safe defaults only when the domain permits them;
- update the plan after the user answers;
- preserve why a step is blocked, skipped, deferred, or delegated.

Planner does not talk to the user directly in its own persona. Planner emits structured `ask_user` / `missing_input` / `choice_required` points. Front turns those into natural human-facing questions and then returns the answer to Planner as a continuation event.

### 10.4 Universal Planner Interaction Contract

This is not a travel-only requirement. Trip planning is a vivid example because it exposes many missing slots, but the same pattern applies to every multi-step task: home operations, scheduling, chores, shopping, healthcare coordination, school planning, family logistics, finance workflows, and any future vertical.

Example user request:

```text
Plan a 14-day trip to Chicago for the family.
```

A human-quality Planner should not jump straight to an itinerary. It should first build a planning frame:

```yaml
PlanningFrame:
  goal: "Plan a 14-day family trip to Chicago"
  known_context:
    family_members: [alex, jordan, riley, nana_liz]
    memories_consulted:
      - dietary preferences
      - accessibility constraints
      - school/work calendar constraints
      - prior trip preferences
  capability_checks:
    - calendar.list_events: available
    - tasks.create_task: available
    - reminders.create_reminder: available
    - travel_booking.search_flights: unavailable_or_unknown
    - maps.estimate_travel_time: unavailable_or_unknown
  missing_required_inputs:
    - travel dates or date range
    - budget level
    - lodging preference
    - transportation mode
    - interests / must-see categories
  ask_user_points:
    - "What date range should I plan around?"
    - "Do you want a budget, moderate, or premium itinerary?"
    - "Should I assume kid-friendly pacing for Riley and accessibility-friendly options for Nana Liz?"
  plan_status: needs_user_input
```

Then Front should ask a compact, human question grounded in that frame. After the answer, Planner continues the same `PlanningFrame`; it does not restart.

The same contract applies to non-trip examples:

- "Organize Riley's school week" -> Planner checks school calendar, chores/tasks capabilities, reminders schema, and asks for missing deadlines.
- "Prepare for the birthday party" -> Planner checks shopping/tasks/calendar/reminders, asks budget and guest count if missing.
- "Help me get the house ready for guests" -> Planner checks chores/tasks/family availability, asks arrival time and priority rooms if missing.
- "Set up recurring medication reminders" -> Planner checks reminder schema, asks dosage/time/recipient if missing and safety policy requires it.

### 10.5 Planner Ask-User Flow

Planner should have a structured way to request missing information:

```yaml
PlannerAskUser:
  work_id: work-...
  plan_id: plan-...
  reason: missing_required_input | ambiguous_constraint | unsafe_assumption | unavailable_capability | user_choice_required
  missing_fields:
    - field: date_range
      schema_source: calendar_or_trip_plan_schema
      required: true
      inferable: false
  question:
    short: "What dates should I plan the Chicago trip for?"
    details: "I can draft the itinerary after I know the date range."
  options:
    - "Use school break"
    - "Use next available 14 days"
    - "I'll give exact dates"
  continuation_policy: resume_same_plan
```

Front owns how this is phrased, but Planner owns the reason the question exists. The answer should resume the same plan with the same memory, capability checks, schema findings, and partial plan state.

### 10.6 Planner Memory And Capability Discipline

Planner must follow a strict order for complex work:

1. Read the active `WorkFrame` and prior relevant frames.
2. Recall memory relevant to constraints, preferences, safety, and family context.
3. Discover capabilities for each intended step.
4. Inspect schemas for required inputs and output shape.
5. Bind canonical capabilities where possible.
6. Ask user only for missing information that cannot be inferred safely.
7. Produce a plan graph with executable, blocked, optional, and deferred steps.
8. Hand executable steps to Back/Orchestrator with continuation context.
9. Update the `WorkFrame` after each plan transition.

This makes Planner feel like it is working with the user, without making Planner a second chat persona.

### 10.7 Fabric Capabilities And Future Agents Must Join The Same Conversation

Grounded current reality: Orchestrator does not currently spawn conversational Fabric agents on the fly. It invokes named Fabric capabilities by building `CapabilityRequest`s from MEDIUM dispatches or `PlanStep`s. Fabric itself has AGENT provider/build-agent machinery, `AgentContract`, `AgentPool`, and `AgentResponsePayload`, but Orchestrator does not currently expose a first-class "spawn agent and keep it in the conversation" path.

Target rule:

> Any Fabric capability or future dynamic agent invoked for a user-visible commitment must not create a new conversation reality.

Today, the continuity payload can only be carried through existing request fields such as `session_id`, `trace_id`, `plan_id`, `step_id`, `caller_id`, `params`, and session snapshots. A stronger future design should introduce a bounded invocation context owned above Fabric by Concierge/Planner/Orchestrator.

Proposed future envelope:

```yaml
AgentInvocationContext:
  work_id: work-...
  plan_id: plan-...
  parent_step_id: step-...
  user_goal: str
  active_commitment: str
  relevant_memories:
    - source: memory | session_state | user_profile | family_profile
      summary: str
      sensitivity: normal | private | regulated
  constraints:
    - dietary
    - budget
    - time
    - safety
    - family_values
  capabilities_allowed:
    - read_calendar
    - send_notifications
    - create_task
  side_effect_policy:
    notify_people: ask_before_send
    spend_money: ask_before_purchase
    external_booking: ask_before_commit
    health_or_finance_advice: explain_limits_and_ask_if_needed
  missing_inputs: list
  ask_user_channel: front_hil
  output_contract:
    required:
      - findings
      - suggested_actions
      - confidence
      - user_questions
```

Current Fabric-compatible output should map to `AgentResponsePayload` when the capability is agent-backed: `answer`, `confidence`, `domain`, `sources`, `domain_data`, `follow_up_needed`, `follow_up_suggestion`, `reasoning_trace`, and `tools_used`. If the architecture needs blockers, it should add that field deliberately or carry blockers in a separate `FailureFrame`; Fabric does not currently define a `blockers` field in `AgentResponsePayload`.

The invoked capability or future agent returns structured output, never direct chat persona. Front remains the voice. Planner/Orchestrator remain the work coordinators.

### 10.8 Agent HIL And Suggestion Contract

Grounded current reality: Fabric has a pre-execution HIL gate through `IHILPort.gate_capability()`. Planner has HIL clarification in SKETCH and approval in VALIDATE. Fabric agents do not currently call an in-agent ask-user hook during execution.

Target behavior: agent-backed capabilities should be able to emit structured ask-user needs to the caller. Concierge/Planner/Orchestrator should convert those into existing HIL flows and resume the same work.

Proposed future ask-user shape:

```yaml
AgentAskUserProposal:
  work_id: work-...
  agent_id: nutrition-agent-...
  reason: missing_input | permission_required | unsafe_assumption | value_tradeoff | regulated_boundary
  question:
    short: "Can I notify everyone to ask when they will arrive home?"
    details: "I can use that to time dinner and tell you when they are 30 minutes away."
  options:
    - "Ask everyone"
    - "Ask only adults"
    - "Do not notify anyone"
  side_effect_preview:
    tool: notifications.send
    recipients: family_members
    message_summary: "Ask arrival time for dinner planning"
  continuation_policy: resume_same_workframe
```

Suggestions should be evidence-grounded and caller-deserializable. Today, the nearest existing shape is `AgentResponsePayload.follow_up_needed` plus `follow_up_suggestion` and `domain_data`. A future suggestion shape could be:

```yaml
AgentSuggestionProposal:
  work_id: work-...
  suggestion: "Make grilled chicken with mashed potatoes."
  evidence:
    - "Emma avoids lactose."
    - "Son avoids gluten."
    - "Dad is managing cholesterol."
    - "Emma and Dad both like this meal."
  tradeoffs:
    - "Use olive oil instead of butter for cholesterol and lactose constraints."
  optional_actions:
    - "Ask everyone when they will arrive home."
    - "Notify you when they are 30 minutes away."
  required_permissions:
    - send_family_notifications
```

This is how the system becomes more than a generic LLM answer. A generic chatbot says "pasta sounds good." The continuity kernel says, "given this family, this time, these health constraints, these preferences, and these tools, here is a better action and what I can do next."

### 10.9 Dinner Scenario: Household Intelligence

Scenario:

```text
Mom came from work and wants to make dinner.
```

Generic LLM answer:

```text
Pasta is a good option.
```

Continuity-kernel answer pattern:

```text
Given Emma avoids lactose, your son avoids gluten, and Dad is managing cholesterol, pasta is probably not the best default tonight. A better option is grilled chicken with mashed potatoes, using olive oil instead of butter. Emma and Dad both like that meal.

I can also ask everyone when they expect to arrive home and notify you when they are about 30 minutes away so dinner can be timed well.
```

Under the hood:

```yaml
WorkFrame:
  goal: "Help make a dinner decision after work"
  relevant_memories:
    - Emma: lactose_intolerant
    - son: gluten_intolerant
    - dad: high_cholesterol
    - family_preferences: grilled_chicken_liked_by_emma_and_dad
  agents:
    - meal_planning_agent
    - family_availability_agent
    - notification_agent
  capability_checks:
    - recipes.suggest: available_or_internal
    - family_presence.ask_arrival: available_or_notification_based
    - notifications.send: available_requires_permission
  suggested_plan:
    - choose_meal: grilled_chicken_with_mashed_potatoes
    - adapt_recipe: no_butter_low_saturated_fat_gluten_free
    - ask_arrival_times: needs_permission
    - notify_when_30_min_away: needs_permission
  hil_points:
    - permission_to_notify_family
```

This is not just "memory retrieval." It is value-aware household orchestration: memory, constraints, tools, side-effect permission, and a coherent suggestion in one flow.

### 10.10 Finance Scenario: Snapshot Plus Values-Aware Decision Support

Question:

> Who tells the user what their actual finance snapshot looks like and helps them make better decisions?

Answer:

The **Finance Decision Agent** can be invoked through Fabric, but Front must present the advice through the active `WorkFrame`. The agent reads permissioned financial data, summarizes the snapshot, identifies constraints, and proposes options aligned with family values. Front speaks the result in human language.

Scenario:

```text
Dad promised his son a PS5 if he scored above 95 percent. The son did it. Dad asks whether to buy it, but the bank account has 800 USD.
```

Generic bank chatbot answer:

```text
No. Your account balance is 800 USD.
```

Continuity-kernel answer pattern:

```text
Right now you have about 800 USD available, so buying a new PS5 outright does not look financially safe today. But there is also a family-values issue: your son kept his side of a promise that mattered to him. If you simply break the promise, he may learn that commitments are optional.

A better compromise is to explain the financial constraint honestly, rent or borrow a PS5 for two to three months, and create a savings plan for buying one when the household is stable. I can help set a reminder and a small savings target, and I can also remind you to reduce food delivery for a few weeks if you want to free up cash.
```

Under the hood:

```yaml
WorkFrame:
  goal: "Decide whether to buy PS5 after promise was fulfilled"
  relevant_memories:
    - child_values: takes_promises_seriously
    - family_rule: commitments_should_be_honored
  finance_snapshot:
    available_cash: 800
    known_obligations: unknown_or_loaded_from_finance_connector
    emergency_buffer_status: unknown
    discretionary_spend_pressure: food_delivery
  agents:
    - finance_snapshot_agent
    - family_values_agent
    - shopping_options_agent
    - savings_plan_agent
  suggested_options:
    - option: rent_or_borrow_ps5_temporarily
      reason: honors_promise_symbolically_without_large_immediate_spend
    - option: create_savings_plan
      reason: preserve_financial_stability
    - option: reduce_food_delivery_temporarily
      reason: free_discretionary_cash
  hil_points:
    - permission_to_read_finance_snapshot
    - desired_budget_limit
    - permission_to_create_savings_reminders
  boundaries:
    - not_a_bank_or_financial_advisor
    - explain_assumptions
    - do_not_move_money_without_explicit_confirmation
```

This is the difference between account chatbot logic and family operating-system logic. The bank chatbot optimizes only for balance. FamilyOS should reason over money, promises, trust, child development, household habits, timing, and available actions.

Important boundary:

- The system can summarize permissioned data and suggest tradeoffs.
- The system should not pretend to be a licensed financial advisor.
- Any money movement, purchase, subscription, cancellation, or external financial action requires explicit confirmation.

### 10.11 Decision Intelligence Layer

The examples above point to a broader layer: **Decision Intelligence**.

Decision Intelligence is what turns raw tasks into human-quality guidance. It combines:

- current user request;
- active `WorkFrame`;
- memory and preferences;
- family values;
- capability availability;
- schema requirements;
- financial/health/safety boundaries;
- side-effect permissions;
- alternative options;
- suggested next actions.

Conceptual output:

```yaml
DecisionFrame:
  work_id: work-...
  decision_question: str
  facts:
    - source: finance_connector
      summary: "Available cash is 800 USD."
    - source: memory
      summary: "Child takes promises seriously."
  constraints:
    - financial_stability
    - family_trust
    - timing
  options:
    - name: buy_now
      feasibility: low
      risks: [cash_pressure]
    - name: rent_temporarily
      feasibility: medium
      benefits: [honors_promise_partially, lower_cash_impact]
    - name: savings_plan
      feasibility: high
      benefits: [stable, teaches_follow_through]
  recommendation:
    summary: "Rent or borrow temporarily, explain the reason, and start savings."
    confidence: medium
  actions_available:
    - create_savings_reminder
    - track_food_delivery_spending
    - search_rental_options
  required_confirmations:
    - read_financial_data
    - contact_family
    - spend_money
```

Decision Intelligence should be domain-general. It is not only finance or dinner. It applies whenever the assistant must choose, advise, trade off values, or coordinate multiple agents.

### 10.12 Proactive Continuity And Notification Router

The family operating system needs proactivity, but proactivity must not mean that every subsystem speaks directly to the user.

Core distinction:

- **Conversation proactivity:** Front says something in the active chat because the user is present or the work belongs in the current session.
- **Notification proactivity:** the system sends a push/SMS/email-style notification because timing matters or the user is away.
- **State-sync proactivity:** app state changed and clients should refresh; this is not a user-facing message by itself.
- **K0 long-horizon proactivity:** K0 detects a pattern, memory gap, curiosity opportunity, or recurring family behavior and asks K1 to consider surfacing it.

These should all feed one router. They should not bypass Concierge and produce separate uncoordinated messages.

#### 10.12.1 Current Signal Sources

| Source | Current status | What it should become |
| --- | --- | --- |
| Concierge task completion | Live: `task.complete -> PROACTIVE_WAKE -> DELIVERING` | A `ProactiveCandidate` with source `concierge_task` |
| Concierge proactive fill | Live/stubbed: experience tick can emit `k1.proactive.fill.v1` | A low-priority candidate for wait/status language |
| HIL request | Live: `CLARIFYING_WORKER` flow | A blocking ask-user candidate with explicit task lineage |
| K1 family tool state changes | Live as state-sync events | Usually `record_only` or UI refresh; sometimes candidate if semantically important |
| K1 reminder fire | Action exists; scheduler/relay missing | A high-confidence notification/chat candidate |
| Calendar/tasks/chores due scans | Missing schedulers | Domain-native candidates generated by K1 family apps |
| K0 proactive signal | Contracts exist; SSE runtime not wired | Long-horizon candidate from memory/pattern layer |
| K0 curiosity intent | Contracts exist; runtime not wired | Candidate to ask/learn/fill knowledge gaps under attention budget |

#### 10.12.2 Proposed Shared Intake Contract

```yaml
ProactiveCandidate:
  candidate_id: pc-...
  source: concierge_task | k1_family_tool | k1_family_scheduler | k0_signal | planner | external_webhook
  source_event_id: str
  work_id: work-... | null
  kind: task_complete | reminder_due | calendar_upcoming | task_overdue | chore_due | curiosity | pattern | suggestion | safety | status_fill
  subject:
    type: task | reminder | event | person | household_pattern | workframe
    id: str | null
    label: str
  recipients:
    - alex
  urgency: low | normal | high | critical
  confidence: low | medium | high
  evidence:
    - source: k1_family_tools
      summary: "Riley's chore is due at 6:00 PM."
    - source: k0_memory
      summary: "Friday dinner plans often create shopping gaps."
  suggested_user_message:
    short: str
    rationale: str
  suggested_actions:
    - action: create_shopping_item
      requires_confirmation: true
    - action: send_notification
      requires_confirmation: true
  side_effects:
    - notify_people
    - create_reminder
  privacy_band: normal | private | regulated
  dedupe_key: str
  expires_at: iso8601
  preferred_surfaces:
    - chat
    - push
    - digest
```

This contract separates signal production from user delivery. A reminder, a K0 pattern, and a task completion can all be represented the same way before the system decides how or whether to surface them.

#### 10.12.3 Proposed Decision Contract

```yaml
ProactiveDecision:
  candidate_id: pc-...
  action: deliver_chat | deliver_push | batch | digest | ask_hil | suppress | record_only
  reason: str
  attention_budget:
    budget_key: alex:daily_proactive
    remaining: 2
    cost: 1
  surface:
    chat:
      front_mode: present | weave | hitl_relay
      weave_group_id: wg-...
    notification:
      channel: push | sms | email
      requires_confirmation: true
      title: str
      body: str
  continuity:
    work_id: work-...
    related_candidates:
      - pc-...
    dedupe_key: str
```

The decision router should run before Front speaks and before notification transport sends anything.

#### 10.12.4 Ownership Split

| Layer | Owns | Must not own |
| --- | --- | --- |
| K1 family tools | Domain truth: calendar, tasks, reminders, chores, settings, reminder lifecycle, due scans | Chat wording, attention budget, long-horizon pattern reasoning |
| Concierge FSM | Conversation state, interruptions, HIL state, proactive delivery state, weave batching | Domain storage or external push transport |
| Front | User-facing language, tone, acknowledgement, repair wording | Deciding domain truth from scratch |
| Planner/Orchestrator | Multi-step plan execution and capability coordination | Uncoordinated user messages outside Front |
| Notification service | APNs/FCM/SMS/email delivery for approved envelopes | Deciding whether something matters |
| K0 | Long-horizon memory, pattern detection, curiosity, gaps, cross-session intelligence | Blocking K1 or speaking directly to the user |
| Bridge | Transport and projection between K0 and K1 | Proactivity policy or user-facing decisions |

The clean model is: K1 and K0 are not two proactive speakers. They are two signal sources feeding one attention/conversation kernel.

#### 10.12.5 Example: K0 Pattern Meets K1 Family Tools

K0-originated signal:

```text
I noticed a recurring pattern: Friday dinner plans often create shopping gaps.
```

Candidate form:

```yaml
ProactiveCandidate:
  source: k0_signal
  kind: pattern
  subject:
    type: household_pattern
    label: "Friday dinner shopping gap"
  evidence:
    - source: k0_memory
      summary: "Last 4 Friday dinner plans led to missing grocery items."
    - source: k1_calendar
      summary: "Family dinner is on the calendar for Friday."
  suggested_user_message:
    short: "Friday dinner plans often create shopping gaps. Want me to check the shopping list?"
    rationale: "This pattern has repeated recently and can be handled before Friday."
  suggested_actions:
    - action: read_shopping_list
      requires_confirmation: false
    - action: suggest_missing_items
      requires_confirmation: false
    - action: add_items_to_list
      requires_confirmation: true
  preferred_surfaces: [chat, digest]
```

Possible Front wording:

```text
I noticed a recurring pattern: Friday dinner plans often create shopping gaps. Since there is a family dinner coming up, I can check the shopping list and suggest anything that looks missing.
```

If the user says yes, Back or Planner uses K1 family shopping/calendar capabilities. K0 supplied the long-horizon pattern; K1 supplies current domain truth and actions.

#### 10.12.6 Example: K1 Reminder Due

K1 family scheduler signal:

```yaml
ProactiveCandidate:
  source: k1_family_scheduler
  kind: reminder_due
  subject:
    type: reminder
    id: rem-123
    label: "Riley: soccer bag"
  recipients: [riley, alex]
  urgency: high
  evidence:
    - source: reminders
      summary: "Reminder is due at 4:30 PM."
  preferred_surfaces: [push, chat]
```

Decision examples:

- If Riley is not in active chat: `deliver_push`.
- If Alex is currently in Family Hub and asked about after-school logistics: `deliver_chat` through Front.
- If there are five low-priority reminders: `digest`.

This avoids duplicating reminder logic in Concierge. Family tools own the reminder lifecycle; Concierge owns whether it becomes conversation.

#### 10.12.7 Example: Calendar Upcoming Creates A Shopping Suggestion

K1 family apps signal:

```text
Birthday party on Saturday.
```

Candidate:

```yaml
ProactiveCandidate:
  source: k1_family_scheduler
  kind: calendar_upcoming
  subject:
    type: event
    label: "Birthday party Saturday"
  evidence:
    - source: calendar
      summary: "Birthday party event is in 2 days."
    - source: shopping
      summary: "No cake or gift item appears on the shopping list."
  suggested_user_message:
    short: "The birthday party is Saturday, and I do not see cake or gift prep on the list. Want me to add them?"
  suggested_actions:
    - action: create_shopping_items
      requires_confirmation: true
```

This is a K1-native proactive candidate. K0 is not required. If K0 later learns that this family usually forgets gift bags, K0 can add pattern evidence into the same router.

#### 10.12.8 Example: Task Completion While Idle

Back completes a task while the user is idle:

```yaml
ProactiveCandidate:
  source: concierge_task
  kind: task_complete
  work_id: work-riley-bedroom
  evidence:
    - source: back_result
      summary: "Riley's Clean Bedroom task was scheduled for 6:00 PM."
  preferred_surfaces: [chat]
```

Decision:

```yaml
ProactiveDecision:
  action: deliver_chat
  reason: "User is in active session and this completes the task they requested."
  surface:
    chat:
      front_mode: present
```

This is the current `PROACTIVE_WAKE` behavior, expressed in the proposed shared model.

#### 10.12.9 Example: Dinner After Work With Notifications

User:

```text
I just got home from work and need to make dinner.
```

Possible candidate chain:

```yaml
ProactiveCandidate:
  source: planner
  kind: suggestion
  subject:
    type: workframe
    label: "Dinner decision"
  evidence:
    - source: memory
      summary: "Emma avoids lactose."
    - source: memory
      summary: "Son avoids gluten."
    - source: memory
      summary: "Dad is managing cholesterol."
    - source: memory
      summary: "Emma and Dad like grilled chicken with mashed potatoes."
  suggested_user_message:
    short: "Pasta is probably not the best default tonight. Grilled chicken with mashed potatoes fits the family constraints better."
  suggested_actions:
    - action: ask_family_arrival_times
      requires_confirmation: true
    - action: notify_when_30_minutes_away
      requires_confirmation: true
```

Front wording:

```text
Pasta is probably not the best default tonight: Emma avoids lactose, your son avoids gluten, and Dad is managing cholesterol. Grilled chicken with mashed potatoes fits better, especially with olive oil instead of butter.

I can also ask everyone when they will arrive and let you know when they are about 30 minutes away, so dinner lands at the right time.
```

The notification side effect only happens after confirmation. The same `WorkFrame` records the dinner decision, the arrival-time ask, and any notification schedule.

#### 10.12.10 Why This Resolves The K1/K0 Tension

K1 family apps should own domain-native triggers:

- reminder due;
- calendar upcoming;
- task overdue;
- chore due;
- shopping list gap tied to a known event;
- family setting or visibility change.

K0 should own long-horizon intelligence:

- recurring pattern detection;
- cross-session memory gaps;
- curiosity prompts;
- family habit trends;
- values and preference drift;
- weak signals that are not tied to one current domain record.

Concierge should own the attention decision:

- say now;
- ask a question;
- batch;
- digest;
- push notify;
- silently record;
- suppress.

This makes K1 and K0 complementary instead of duplicative.

---

## 11. Conversation Coherence Model

For each user turn, classify the speech act before tool planning:

| Speech act | Meaning | Continuity behavior |
| --- | --- | --- |
| New request | Start a new goal | Create new `WorkFrame` |
| Follow-up | Modify active goal | Update active `WorkFrame`; enqueue control event if Back running |
| Retry | Reattempt failed/blocked goal | Reopen `WorkFrame` with lineage |
| Clarification answer | Resolve pending blocker | Resume suspended task |
| Cancel | Stop active goal | Cancel `WorkFrame` and running task |
| Status ask | User wants progress | Read `WorkFrame` and answer grounded status |
| Social turn | No work requested | Front direct response; no task mutation |

The key missing category in the observed failure is **Retry**.

---

## 12. Status And Acknowledgement Policy

`"I'm working on that now."` is safe but too generic when continuity matters.

Acknowledgements should be grounded in the active `WorkFrame`:

- New work: "I'm updating Riley's bedroom task and checking the calendar."
- Retry: "I'll retry the Riley update and include the calendar check."
- Modification while running: "Got it. I'll apply 8:00 PM to the task I'm already working on."
- Blocked: "I found the task, but I need one detail before I can change it."

This is not decoration. It is a consistency check: Front should not acknowledge a commitment that no `WorkFrame` can represent.

---

## 13. Interaction With Existing Strengthening Plan

This whiteboard extends the existing plan instead of replacing it.

### M3 ReAct Loop Strengthening

Existing M3 work gives:

- checkpoints;
- tool execution records;
- retry policy;
- control queue;
- bounded extra iteration for late modifications.

Continuity extension:

- loop exits should write `WorkFrame` checkpoints;
- retry policy should operate at both tool-call and work-frame levels;
- budget exhaustion should produce partial/repair frames;
- control queue updates should update `WorkFrame` as accepted/rejected modifications.

### M4 Weave And Conversation Attention

Existing M4 decides when async results should be delivered.

Continuity extension:

- Weave decisions should read active `WorkFrame.status`;
- user typing or active HIL should delay non-critical updates;
- result delivery should preserve thread identity: "On Riley's bedroom task..."

### M5 Ledger And Recovery

Existing M5 aims for crash recovery.

Continuity extension:

- `WorkFrame` must be ledger-replayable;
- failed/retried task lineage must recover after restart;
- the same conversation should not forget an active commitment after crash.

### M6 Memory, Identity, And Continuity

Existing M6 says: strengthen the "same mind over time" feeling without making Back conversational.

Continuity extension:

- Front prompt compression should include active/recent `WorkFrame` summaries;
- narrative continuity should include unresolved commitments;
- identity overlays remain Front-only;
- Back receives only execution-safe continuation context.

---

## 14. Previous Recommendations, Preserved And Expanded

### Recommendation 1: Fix MEDIUM routing/binding

Previous form:

- Make MEDIUM tier do `discover_capabilities` first, or fold MEDIUM into Back, or constrain Front's schema so it cannot emit free-text capability names.

Expanded form:

- Introduce a capability binding stage between `TaskDispatch` and orchestrator execution.
- Direct `_dispatch_medium` only receives canonical capability names.
- If binding fails, degrade to Back discovery or Planner with structured blockers.

### Recommendation 2: Add task continuation context

Previous form:

- Carry compact context in `TaskDispatch`: Front observations, prior task ID, tool summaries.

Expanded form:

- Add `WorkFrame` as durable state and `TaskContinuationContext` as bounded actor payload.
- Store prior attempt summaries, partial results, blockers, referents, and route hints.

### Recommendation 3: First-class retry

Previous form:

- Add `retry_task(task_id, modifications?)` so "give it another shot" maps to failed task state.

Expanded form:

- Add retry speech-act detection.
- Reopen `WorkFrame` lineage.
- Avoid known-bad route on retry.
- Preserve user modifications as deltas, not fresh independent tasks.

### Recommendation 4: Budget continuity

Previous form:

- Persist `_per_tool_counts` and `call_count` across resume/continuation when needed.

Expanded form:

- Keep per-loop budgets for isolation.
- Add commitment-level budget ledger.
- Reserve repair budget.
- Treat budget exhaustion as checkpoint/partial/ask, not generic failure.

### Recommendation 5: Partial-result rescue

Previous form:

- On budget exhaustion, synthesize partial/needs-human instead of losing work.

Expanded form:

- Every failure path emits `FailureFrame` with partial results and next repair actions.
- Front error mode must be grounded in `FailureFrame`, not a generic error scenario alone.

---

## 15. Implementation Roadmap

### Phase 0: Stop The Current Bleed

Goal: Turn 3/4 should not fail instantly before Back runs.

Actions:

1. Route MEDIUM conversational tasks through capability binding before `_dispatch_medium`.
2. Degrade `capability_not_found` to Back discovery when the source is conversational Front dispatch.
3. Add targeted live-style regression for:
   - create Riley task;
   - update it to 8 PM;
   - add/check calendar;
   - user says "try again" after synthetic first failure.

### Phase 1: WorkFrame Minimum Viable Continuity

Goal: Every visible work commitment has a durable frame.

Actions:

1. Define `WorkFrame` schema.
2. Create frame on `dispatch_task` success.
3. Update frame on task complete/failed/suspended/cancelled.
4. Put active frame summary in Front prompt scenario data.
5. Make Front ack text derive from the frame.

### Phase 2: First-Class Retry And Follow-Up

Goal: "Try again" and "also..." are not fresh blind dispatches.

Actions:

1. Add retry/follow-up speech-act classifier in Front/FSM.
2. Link retry to recent failed or blocked `WorkFrame`.
3. Add `retry_work` or `retry_task` tool/control event.
4. Preserve prior blocker and route around it.
5. Add tests for identical failure not repeating blindly.

### Phase 3: Budget And Partial Semantics

Goal: Budget failures become useful repair turns.

Actions:

1. Add commitment-level budget ledger.
2. Add repair reserve.
3. Teach Back loop to emit partial/checkpoint on near exhaustion.
4. Ensure Front error mode receives partials and blockers.
5. Test that partial work is visible after budget exhaustion.

### Phase 4: Planner/Orchestrator Continuity

Goal: Multi-step work has plan continuity and can ask the user for missing information without social leakage.

Actions:

1. Planner consumes `WorkFrame` constraints and evidence.
2. Planner reads relevant memories before drafting or executing plans.
3. Planner discovers capabilities and inspects schemas before committing to steps.
4. Planner emits structured ask-user points when required fields are missing.
5. Front relays Planner questions and resumes the same plan after the user answers.
6. Orchestrator accepts bound steps or explicit bind-required states.
7. Orchestrator `PlanStep`s and Fabric `CapabilityRequest`s carry proposed continuation context where supported by fields or params.
8. Future agent-backed Fabric capabilities serialize findings and follow-up suggestions through `AgentResponsePayload` or a new explicit result contract.
9. Capability failures route to binder, not generic task failure.
10. Compensation and partial completion update `WorkFrame`.

### Phase 4.5: Decision Intelligence

Goal: The system can make context-aware suggestions that combine memory, data, tools, and family values.

Actions:

1. Define `DecisionFrame` for tradeoff-heavy user questions.
2. Add domain boundaries for finance, health, safety, and external side effects.
3. Ensure permissioned data access before finance or private family snapshots.
4. Let Planner/Orchestrator invoke specialist capabilities, and future agent-backed capabilities, under one proposed `WorkFrame`.
5. Front presents recommendations with facts, assumptions, alternatives, and next actions.
6. Require confirmation before notifications, purchases, money movement, booking, or other external side effects.

### Phase 4.6: Proactive Continuity Router

Goal: K1 family apps, Concierge, K0 signals, and notification delivery feed one attention/conversation route instead of becoming parallel speakers.

Actions:

1. Define `ProactiveCandidate` and `ProactiveDecision` contracts.
2. Convert current Concierge `task.complete` proactive wake into a `concierge_task` candidate.
3. Convert `k1.proactive.fill.v1` into low-priority `status_fill` candidates.
4. Add a K1 family scheduler layer for reminder due, task overdue, chore due, and calendar upcoming candidates.
5. Keep `tool_state.changed` as state-sync by default; promote to proactive candidate only through explicit rules.
6. Add notification-envelope generation after the router, not inside domain tools.
7. Add the future K0 SSE translation adapter: `k0.proactive.signal.v1` / `curiosity.intent.v1` -> `ProactiveCandidate`.
8. Apply dedupe, attention budget, privacy, HIL, and surface selection before Front or notification transport receives anything.
9. Ensure K1 stays functional without K0; K0 signals enrich but do not block.

### Phase 5: Human-Feeling Conversation Polish

Goal: The system speaks with continuity.

Actions:

1. Active work summaries in Front prompt.
2. Status ask support from `WorkFrame`.
3. Grounded acks.
4. Threaded weave delivery.
5. Narrative continuity from M6 compression and identity overlays.

---

## 16. Acceptance Tests

### 16.1 Current Screenshot Regression

Test script:

1. "hey how are you doing today?"
2. "all well but thing is i was looking to give task to riley about cleaning her bedroom"
3. "can you change it to 8:00 PM because we have family dinner at that time yeah also add event to calendar that would be great"
4. Synthetic first route failure or real route if still failing.
5. "give a shot once again and also check if calendar is populated"

Pass conditions:

- Turn 3 does not fail before Back/binder has attempted capability resolution.
- Turn 4 is recognized as retry/follow-up.
- The same failed route is not repeated blindly.
- Front response references the active Riley work item.
- Final response states what changed and what was checked.

### 16.2 Continuity Frame Test

Pass conditions:

- `dispatch_task` creates `WorkFrame`.
- `task.failed` updates `WorkFrame.blockers`.
- Retry reuses `WorkFrame.work_id` or links `retry_of`.
- Front prompt includes active frame summary.

### 16.3 Budget Repair Test

Pass conditions:

- Back near budget exhaustion emits partial/checkpoint/needs-human.
- Front receives partials.
- User is not given generic snag if partial state exists.

### 16.4 Capability Binding Test

Pass conditions:

- Natural action `reschedule_task` binds to canonical `tool.execute.tasks.update_task` or a known equivalent.
- `update_calendar_event` / `create_calendar_event` binds to calendar capabilities.
- Unknown bindings produce bind-required state, not generic orchestrator failure.

### 16.5 Retry Avoids Known-Bad Route

Pass conditions:

- If prior failure is `dispatch_medium.capability_not_found`, retry route hint changes to binder/Back discovery.
- The log proves the second attempt does not call the same failing registry validation with the same free-text capability.

### 16.6 Planner Ask-User Continuity Test

Scenario:

```text
Plan a 14-day trip to Chicago for the family.
```

Pass conditions:

- Planner reads relevant memory before drafting the plan.
- Planner discovers capabilities for calendar/tasks/reminders and any travel-related providers.
- Planner inspects schemas and identifies missing required inputs.
- Planner emits a structured ask-user point instead of guessing unsafe details.
- Front asks the user a compact grounded question.
- User answer resumes the same `PlanningFrame`; the plan does not restart cold.
- The same behavior works for a non-trip workflow such as party planning, house preparation, school-week planning, or medication reminders.

### 16.7 Fabric Agent Continuity Test

Scenario:

```text
I just got home from work and need to make dinner.
```

Pass conditions:

- Orchestrator/Planner can invoke meal, family-availability, and notification capabilities, or future agent-backed capabilities, under one proposed `WorkFrame`.
- Invoked capabilities receive the same relevant dietary, preference, time, and side-effect policy context through bounded request/context fields.
- Recommendation avoids known lactose/gluten/cholesterol conflicts.
- Notification action is proposed but not sent without HIL confirmation.
- Front presents one coherent suggestion, not separate agent fragments.

### 16.8 Finance Decision Intelligence Test

Scenario:

```text
My son scored above 95 percent like I promised. Should I buy him a PS5?
```

Pass conditions:

- Finance agent asks permission or uses already-permissioned finance snapshot.
- Recommendation mentions available cash, obligations/unknowns, and uncertainty.
- Family-values context is included if known: the child takes promises seriously.
- The system offers alternatives such as renting/borrowing temporarily or creating a savings plan.
- No purchase, account action, or external financial side effect occurs without explicit confirmation.
- Front presents the recommendation as decision support, not as licensed financial advice.

### 16.9 Proactive Candidate Router Test

Scenario:

```text
Back completes a task while the user is idle, a reminder is due, and K0 emits a recurring Friday dinner shopping-gap signal.
```

Pass conditions:

- Each source becomes a `ProactiveCandidate` with source, kind, evidence, dedupe key, urgency, and preferred surfaces.
- `tool_state.changed` events remain state-sync unless an explicit promotion rule turns them into candidates.
- Attention budget prevents all three from interrupting the user separately.
- Front receives at most one coherent chat delivery or a deliberate digest.
- Notification transport receives only approved `ProactiveDecision` notification envelopes.
- K0 signal enriches or suggests; it does not block K1-native reminder/task delivery.

### 16.10 K1/K0 Proactivity Boundary Test

Scenario:

```text
Friday dinner is on the calendar, shopping list is missing likely items, and K0 has learned that Friday dinners often create shopping gaps.
```

Pass conditions:

- K1 calendar/shopping state supplies current domain truth.
- K0 supplies only pattern evidence.
- Concierge router merges them into one candidate or one delivery.
- Front says something like: "I noticed a recurring pattern: Friday dinner plans often create shopping gaps. Want me to check the list?"
- Adding items requires confirmation.
- The same flow works if K0 is offline, using only K1 current state and weaker confidence.

---

## 17. What Not To Do

Do not solve continuity by:

- making Back conversational;
- making Planner a second chat persona;
- letting Fabric capabilities or future dynamically spawned agents speak as disconnected mini-assistants;
- appending raw Front message history into every Back prompt;
- creating one unbounded ReAct loop for the whole session;
- increasing budgets until failures disappear;
- letting Front promise retries that are not represented in state;
- letting Planner silently guess missing required schema fields;
- hard-coding the Planner flow for travel instead of making it task-general;
- giving financial or health-flavored recommendations without data provenance, uncertainty, and permission boundaries;
- performing side effects such as notifications, bookings, purchases, or money movement without explicit confirmation;
- letting K1 family tools, K0, notification transport, and Concierge each speak to the user through separate channels;
- treating every `tool_state.changed` event as user-facing proactivity;
- making K1 depend on live K0 for reminders, calendar events, tasks, chores, or local family app operation;
- sending push notifications directly from domain tools without an attention/privacy/HIL decision;
- relying on LLM memory to infer failed task lineage;
- treating `history_active` text as the source of truth for work state.

These are attractive shortcuts, but they produce non-determinism, cost spikes, and more hidden failure modes.

---

## 18. Kernel Invariants For Coherent Conversation

1. **No visible commitment without a durable frame.**
2. **No retry without lineage.**
3. **No orchestrator execution without canonical capability binding.**
4. **No budget exhaustion without partial/checkpoint/repair output.**
5. **No actor handoff without bounded continuation context.**
6. **No user-facing error without a structured failure frame.**
7. **No Front ack that cannot be mapped to executable state.**
8. **No Back persona. Front owns the relationship; Back owns execution.**
9. **No Planner persona. Planner owns plan state, missing inputs, and ask-user points.**
10. **No raw chain-of-thought sharing. Share operational summaries.**
11. **No dropped active work on crash, refresh, websocket reconnect, or retry.**
12. **No plan execution before memory, capability, and schema checks for complex work.**
13. **No guessing required fields when Planner can ask a precise question through Front.**
14. **No Fabric capability or future spawned agent outside the active proposed `WorkFrame`.**
15. **No agent suggestion without evidence, assumptions, and side-effect policy.**
16. **No private finance, health, or family snapshot without permissioned data access.**
17. **No external side effect without explicit confirmation.**
18. **No proactive source may bypass the shared attention/conversation router.**
19. **No notification transport decides what matters; it only delivers approved envelopes.**
20. **No K0 dependency for K1-native family app operation. K0 enriches; K1 remains self-sufficient.**
21. **No state-sync event becomes user-facing proactivity without an explicit promotion rule.**
22. **No duplicate proactive delivery across chat, push, digest, and K0 signal paths.**

---

## 19. Final Architectural Verdict

The user's review is directionally correct: the system needs continuity that spans Front, Back, Planner, budgets, retries, and failures. The exact implementation should not be a single endless ReAct loop. It should be a durable continuity substrate.

The immediate screen failure is a MEDIUM-tier capability-binding/routing problem. The deeper product failure is that a user-visible promise does not have a durable cognitive object behind it. Once every promise has a `WorkFrame`, every task has lineage, every failure has a repair frame, and every actor receives bounded continuation context, the system will start to feel less like separate loops and more like one coherent assistant.

The kernel-level target is:

```text
Human says something
  -> Front interprets speech act and commitment
  -> WorkFrame records shared common ground
  -> Binder resolves executable capability truth
  -> Planner reads memory/capabilities/schemas when planning is needed
  -> Planner asks through Front when required information is missing
  -> Orchestrator invokes Fabric capabilities, and future agent-backed capabilities, inside the same proposed continuity context
  -> DecisionFrame captures tradeoffs, values, evidence, and actions when advice is needed
  -> Domain/K0/progress signals become ProactiveCandidates instead of direct messages
  -> ProactiveDecision chooses chat, push, digest, ask, suppress, or record-only
  -> Back/Planner/Orchestrator execute with continuation context
  -> Every exit updates the WorkFrame
  -> Front speaks from the WorkFrame
```

That is the architecture that makes the conversation feel like talking to a competent human, while keeping the kernel auditable, bounded, recoverable, and testable.
