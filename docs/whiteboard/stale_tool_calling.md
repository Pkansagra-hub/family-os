# Whiteboard - Back Capability Discovery Scaling Discussion

**Date:** 2026-05-27
**Branch:** `feature/prompt-architecture-refactor`
**Status:** Discussion capture only. No implementation decision yet.

**Scope:** Back actor capability discovery, tool guidance, constitution/policy, IFL/Fabric external adapters, and the open problem of scaling from a few native family apps to many external apps/devices/services.

**Core question:** How should Back find and safely use the right external or native capability when tool discovery, tool guidance, constitution/policy, resource identity, query accuracy, and IFL-scale adapter catalogs all interact without collapsing into top-K search or combinatorial guide/constitution explosions?

---

## Read This First - Not A Two-Car Problem

The two-car case is only one small failure test. It is not the problem being solved.

The real problem started earlier:

```text
Back task
  -> find_capabilities(query)
  -> invoke_capability(params)
  -> submit_result
```

That flow collapses too many different questions into one query-shaped step.

The actual open problem is how FamilyOS resolves all of these at 100k-tool scale:

```text
1. What executable capabilities might be needed?
2. What tool/activity guides apply, such as calendar_activity_v1?
3. What constitution/policy modules apply before discovery and before mutation?
4. What related capability roles must be considered because policy says so?
5. What concrete resources/accounts/devices/people did the user refer to?
6. Which connected local resources exist for this actor right now?
7. Which adapters can operate on those resources?
8. What should Back ask, block, verify, or execute?
```

The two-car example only proves one thing: a rank-first search can silently hide relevant candidates. The broader failure is that the current shape cannot reliably compose discovery, guidance, constitution, resource identity, and scale.

### The Original Confusion To Preserve

The original confusion was not "how do we find both cars?" It was this:

```text
If Back first runs find_capabilities("create calendar appointment")
and gets only calendar tools,
then a later constitution says "check tasks/reminders for duplicates/conflicts,"
Back has to redo discovery or misses those tools.
```

That means guidance/constitution after discovery is too late.

But the opposite direction also fails:

```text
If Back first selects constitution + calendar_activity_v1 before discovery,
then how many constitutions/guides do we need for 5 apps x 5 tools,
and what happens at 100k tools?
```

That means guide/constitution-first selection cannot become hand-authored permutations.

The design challenge is the space between those failures:

```text
Not:
  discover one tool first, then bolt policy/guidance onto it.

Not:
  preselect a giant workflow constitution for every app/tool combination.

Needed:
  a resolver that can derive required roles, bind local resources/capabilities,
  and attach the right guidance/policy without combinatorial explosion.
```

### Constitution Vs Tool Guide

These two things are related, but they are not the same artifact.

Constitution/policy answers:

```text
What must be true before this class of action is allowed?
What reads are mandatory before writes?
What ambiguity requires HIL?
What side effects require confirmation, privacy projection, audit, or verification?
Which related role categories must be considered before mutation?
```

Example:

```text
Before writing a time-bound family commitment:
  resolve time, participants, authority, and conflict sources;
  gather known commitment/blocker signals;
  ask HIL on ambiguity/conflict/cross-member impact;
  verify after write.
```

Tool/activity guide answers:

```text
How does this bound tool or adapter work correctly?
What params does it require?
What read-before-write or read-after-write call does this adapter support?
What adapter-specific quirks, limitations, or examples should Back know?
```

Example:

```text
calendar_activity_v1 says how to use calendar list_events/create_event/get_event correctly.
It should not decide global family policy by itself.
```

The scalable design must compose constitutions and guides by effects, roles, resources, and bound adapters. It must not generate one constitution per app/tool combination.

No-permutation rule:

```text
Do not create:
  calendar+tasks+reminders constitution
  calendar+tasks+reminders+chores constitution
  calendar+tasks+health+car+Hue constitution

Do create reusable policy modules and adapter guides that the resolver composes at runtime.
```

### Collapsed Current Model

```text
             one natural-language query
                       |
                       v
           discover_capabilities(intent)
                       |
       +---------------+---------------+
       |               |               |
       v               v               v
 executable tools   guidance docs   policy hints
       |               |               |
       +---------------+---------------+
                       |
                       v
               ranked candidate list
```

Why it breaks:

```text
The same query is being asked to find executable tools,
select guidance,
infer policy,
discover related tools,
resolve resources,
and pick from a large catalog.
```

Those are different jobs. A single top-K list cannot be the authority for all of them.

### Bigger Failure Examples

Scheduling failure:

```text
User: Schedule Riley's dentist appointment Monday at 3.

Naive discovery:
  find_capabilities("create calendar appointment") -> calendar.create_event

Late constitution says:
  check tasks/reminders/school events/caregiver constraints first

Failure:
  those tools were never in the candidate universe.
```

Smart-home failure:

```text
User: Turn off the living room lights.

Reality:
  Hue group + Matter bulbs + maybe a smart plug all affect living-room lighting.

Failure:
  top-K returns Hue only, Matter never appears, Back acts on an incomplete room state.
```

Health failure:

```text
User: How did Riley sleep last night?

Reality:
  Fitbit, Apple Health, and consent/privacy policy all matter.

Failure:
  search finds Fitbit first, but authority/privacy and other health sources were not resolved.
```

Finance/payment failure:

```text
User: Pay the tutor.

Reality:
  source account, recipient identity, amount, fraud/confirmation policy,
  and supported payment rails all matter.

Failure:
  search finds a payment tool, but constitution-required confirmation and identity binding
  were not part of the candidate construction.
```

Two-car failure:

```text
User: Turn on climate control of my car.

Reality:
  Tesla and Audi are both connected resources.

Failure:
  search returns Tesla, Audi is omitted, and HIL is biased.
```

The two-car case stays useful because it is the smallest easy-to-see proof that incomplete candidate generation corrupts HIL. It is not the main domain.

---

## Four Planes - One System

This cannot be designed as four separate parts. If any plane is designed alone, Back will fail at scale.

```text
                       +--------------------------------+
                       | User / Front task envelope     |
                       +---------------+----------------+
                                       |
                                       v
+----------------------+    asks     +------------------------------+
| Plane 1              |-----------> | Plane 4                      |
| Back LLM ReAct Loop  |             | Tool search + provisioning   |
+----------+-----------+             +--------------+---------------+
           |                                        |
           | receives                               | reads/joins
           v                                        v
+----------------------+             +------------------------------+
| Prompt pack          |<------------| Plane 3                      |
| tools + policy +     |             | Standard tool contracts      |
| guides + candidates  |             | and tool design              |
+----------+-----------+             +--------------+---------------+
           ^                                        |
           |                                        | annotated by
           |                                        v
           |                         +------------------------------+
           +-------------------------| Plane 2                      |
                                     | Constitution + usage guides  |
                                     +------------------------------+
```

### Plane 1 - Back LLM ReAct Loop Design

What it owns:

```text
observe -> frame -> ask resolver/tools -> read result -> decide -> act/ask/verify -> submit
```

It decides the next step, but it should not invent the world.

### Plane 2 - Constitution And Usage Descriptions

What it owns:

```text
constitution/policy:
  what must be true before action
  when HIL/confirmation/audit/privacy/verification is required

usage guide:
  how a bound tool/adapter should be used correctly
  params, examples, quirks, read-before-write, read-after-write
```

### Plane 3 - Standard Tool Contracts And Tool Design

What it owns:

```text
tool name
input schema
output schema
side effects
resource types it acts on
permission/safety band
verification support
errors and limitations
```

### Plane 4 - Tool Search And Provision To Back

What it owns:

```text
resolve request frame
resolve resources
bind capabilities
load relevant policy/guides/contracts
return CandidateUniverse + prompt pack to Back
```

Not acceptable:

```text
return top-K tools and make Back guess the rest
```

Acceptable:

```text
return the candidate universe, completeness, policy/guidance, and exact invokable bindings
```

---

## Basic Back ReAct Loop - Tool Calling Scenario

This is the foundation process to design first.

```text
0. Receive task envelope from Front/FSM
1. Build request frame
2. Ask resolver for CandidateUniverse
3. Read candidate universe + policy/guidance
4. Decide next action
5. Invoke tool / ask HIL / request more info / block
6. Verify result when required
7. Submit result back to Front/FSM
```

ASCII flow:

```text
Front/FSM task
    |
    v
+-----------------------------+
| Back prompt: task intake     |
| - user goal                  |
| - actor/session context      |
| - safety band                |
| - available meta-tools       |
+--------------+--------------+
               |
               v
        ReAct step 1
               |
               v
call resolve_situation(user_goal)
               |
               v
+-----------------------------+
| CandidateUniverse            |
| - request_frame              |
| - resources                  |
| - capability_bindings        |
| - completeness/freshness     |
| - policy verdict             |
| - required guides/contracts  |
+--------------+--------------+
               |
               v
        ReAct step 2
               |
   +-----------+------------+-------------+
   |                        |             |
   v                        v             v
invoke_capability      ask HIL       block/submit issue
   |
   v
verify if required
   |
   v
submit_result
```

### Prompt Shape Per Step

The Back prompt should not dump the entire universe every turn. Each ReAct step gets the dynamic injection it needs.

```text
Step 0 - Task intake prompt
  static: Back role, ReAct rules, safety rules, tool-call protocol
  dynamic: user goal, Front envelope, actor, safety band, session/task ids
  tools shown: resolver/provisioning meta-tools, submit_result

Step 1 - Situation resolution prompt
  static: do not choose final tool from text search alone
  dynamic: current task, known context, missing fields
  expected call: resolve_situation or equivalent resolver

Step 2 - Candidate read prompt
  static: ranking after completeness, HIL on ambiguity
  dynamic: CandidateUniverse, completeness, omissions, policy verdict
  tools shown: inspect_binding, invoke_capability, ask/submit path

Step 3 - Tool parameter prompt
  static: obey contract schema exactly
  dynamic: selected binding, tool contract, usage guide, policy constraints
  expected call: invoke_capability with valid params

Step 4 - Verification prompt
  static: verify if policy/contract requires it
  dynamic: invocation result, verifier binding, read-after-write guidance
  expected call: verifier tool or submit_result

Step 5 - Completion prompt
  static: report what happened without leaking internal machinery
  dynamic: verified result, HIL decisions, audit notes, user-facing summary
  expected call: submit_result
```

### Example A - Scheduling

```text
User: Schedule Riley's dentist appointment Monday at 3.
```

Bad loop:

```text
Back -> discover_capabilities("create calendar appointment")
Back -> calendar.create_event
```

Better loop:

```text
Back -> resolve_situation("Schedule Riley's dentist appointment Monday at 3")

CandidateUniverse:
  request_frame:
    operation: commitment.time_bound.create
    participant: Riley
    time: Monday 3pm

  required roles from constitution:
    temporal resolver
    participant resolver
    conflict readers
    calendar writer
    verification reader

  bound capabilities:
    calendar.list_events
    school_calendar.list_events
    tasks.list_tasks
    reminders.list_reminders
    calendar.create_event
    calendar.get_event

  verdict:
    check_conflicts_before_write
```

Then Back sees prompt pack:

```text
constitution:
  time-bound family commitment policy

usage guides:
  calendar_activity_v1
  tasks_activity_v1
  reminders_activity_v1

contracts:
  exact schemas for bound tools only
```

### Example B - Smart Home

```text
User: Turn off the living room lights.
```

CandidateUniverse:

```text
request_frame:
  operation: home.light.power.off
  location: living room

resource_candidates:
  Hue living room group
  Matter floor lamp
  Matter ceiling bulbs

bound capabilities:
  hue.set_group_state
  matter.set_device_state

policy:
  low-risk reversible household actuation

verdict:
  executable_batch_if_all_resources_confirmed
```

### Example C - Health

```text
User: How did Riley sleep last night?
```

CandidateUniverse:

```text
request_frame:
  operation: health.sleep.read
  person: Riley
  time_window: last night

resource_candidates:
  Riley Fitbit sleep source
  Riley Apple Health sleep source

policy:
  health privacy + consent gate

verdict:
  allow / ask consent / deny based on actor and policy
```

### Example D - Car Is Only One Gate

```text
User: Turn on climate control of my car.
```

CandidateUniverse:

```text
request_frame:
  operation: vehicle.climate.start
  resource_reference: my car
  actor: Alex

resource_candidates:
  Tesla Model Y
  Audi Q7

bound capabilities:
  tesla.start_climate
  audi.start_climate

verdict:
  needs_disambiguation
```

This example tests candidate completeness. It is not the whole design.

---

## Plane 1 Detail - Back LLM ReAct Loop

Purpose:

```text
Make Back a disciplined executor.
Back chooses the next step, but deterministic planes provide the world, contracts, policy, and candidates.
```

State machine:

```text
S0 Intake
  -> S1 Frame request
  -> S2 Resolve situation
  -> S3 Read CandidateUniverse
  -> S4 Decide path
  -> S5 Build tool params
  -> S6 Invoke / ask HIL / block
  -> S7 Verify if required
  -> S8 Submit result
```

ASCII loop:

```text
        +------------------+
        | S0 task intake   |
        +--------+---------+
                 |
                 v
        +------------------+
        | S1 frame request |
        +--------+---------+
                 |
                 v
        +------------------+        +--------------------------+
        | S2 resolve       |------->| Plane 4 resolver         |
        +--------+---------+        +------------+-------------+
                 |                               |
                 v                               v
        +------------------+        +--------------------------+
        | S3 read universe |<-------| CandidateUniverse pack   |
        +--------+---------+        +--------------------------+
                 |
      +----------+----------+----------------+
      |                     |                |
      v                     v                v
  invoke path            HIL path        block/ask path
      |                     |                |
      v                     v                v
  verify if needed      wait result      submit issue
      |
      v
  submit_result
```

Prompt packet by state:

```text
S0 Intake
  dynamic: user goal, Front envelope, actor, task id, safety band
  visible tools: resolve_situation, submit_result

S1 Frame request
  dynamic: known people/time/place/task hints
  output: request_frame draft or resolver call

S2 Resolve situation
  dynamic: request_frame draft
  visible tools: resolve_situation

S3 Read CandidateUniverse
  dynamic: candidates, completeness, omissions, policy verdict, available bindings
  visible tools: inspect_binding, invoke_capability, submit_result, HIL lane

S4 Decide path
  dynamic: policy gates, ambiguity, missing data, freshness
  output: invoke / HIL / ask-more / block

S5 Build tool params
  dynamic: one selected binding, exact contract, usage guide, policy constraints
  visible tools: invoke_capability

S6 Invoke / HIL / block
  dynamic: params or user-facing HIL question or block reason
  output: tool call or submit_result

S7 Verify
  dynamic: invocation result, verifier contract, read-after-write guide
  visible tools: verifier binding or submit_result

S8 Submit
  dynamic: verified outcome, audit notes, user-facing result
  visible tools: submit_result
```

What Plane 1 needs from other planes:

```text
Plane 2 -> compact policy cards + usage guide cards
Plane 3 -> exact binding contracts + schemas + verifier links
Plane 4 -> CandidateUniverse + completeness + prompt pack
```

What Plane 1 must not do:

```text
Do not invent resources.
Do not infer authority by vibes.
Do not choose a tool from top-K when completeness is unknown.
Do not mutate before required policy gates pass.
Do not ask HIL with an incomplete candidate set unless it says projection is incomplete.
```

Small example:

```text
Task: Schedule Riley dentist Monday 3pm

S1 frame:
  operation: commitment.time_bound.create
  participant: Riley
  time: Monday 3pm

S2 resolve:
  ask Plane 4 for CandidateUniverse

S3 read:
  sees conflict readers + calendar writer + policy check_conflicts_before_write

S4 decide:
  read conflicts before create_event
```

### Plane 1A - Specialized ReAct Loop Design We Discussed

Back is not a normal chat responder in this lane. Back is a governed executor running a bounded ReAct loop.

Important correction:

```text
Atomic states are controller/runtime states.
They are not one LLM call each.

If S0..S8 became eight sequential LLM calls, the design fails on latency.
```

Hard latency rule:

```text
Normal Back execution must fit in 3 LLM hops.
Hard max is 4 LLM hops for repair, HIL resume, or unusual ambiguity.

Tool execution, reads, resolver joins, validation, and verification must be parallelized
or handled deterministically outside the LLM wherever policy allows.
```

Core loop contract:

```text
observe state
  -> frame request
  -> call the next resolver/tool action when needed
  -> read observation
  -> choose next state
  -> execute / ask / block / verify / submit
```

This is a standard loop, not a shortcut or domain-specific fast path. The speed comes from packing deterministic work into tool phases and keeping the LLM hop budget small.

### Plane 1B - LLM Hop Budget

The loop must be designed around LLM hops, not the number of internal states.

Standard path:

```text
LLM Hop 1 - Frame + resolve
  input:
    Front/FSM task envelope
    actor/session/safety context
  output:
    resolve_situation(request_frame)

Tool Phase A - Resolve/provision
  runs without LLM:
    parse/normalize frame if needed
    resource lookup
    policy role lookup
    contract binding
    guide/policy/contract packing
    freshness/completeness calculation
  output:
    CandidateUniverse + PromptPack

LLM Hop 2 - Decide + act
  input:
    CandidateUniverse + PromptPack
  output one of:
    invoke_capability / batch_invoke_capabilities
    ask HIL
    submit blocked/cannot_execute

Tool Phase B - Execute/verify
  runs without LLM where contract/policy allows:
    parallel reads
    batch execution
    schema validation
    provider call
    read-after-write verification
    structured error normalization

LLM Hop 3 - Submit
  input:
    execution/verification result
  output:
    submit_result
```

Hard max path:

```text
LLM Hop 4 is allowed only for:
  HIL response resume
  recoverable parameter repair
  conflict/ambiguity after prerequisite reads
  verification failure requiring a safe decision
```

Not allowed:

```text
S0 LLM call
S1 LLM call
S2 LLM call
S3 LLM call
S4 LLM call
S5 LLM call
S6 LLM call
S7 LLM call
S8 LLM call
```

That would turn a simple action into a 60-90 second system. It is not acceptable.

### Standard Fast-Enough Loop, Not Fast Path

We are not adding domain-specific shortcuts like "if hall lights, skip governance."

We are defining the normal kernel procedure so it is fast enough by construction:

```text
One standard resolver call.
One standard candidate universe.
One standard prompt pack.
One standard action decision.
One standard execution/verification phase.
One standard submit.
```

Simple command target:

```text
User: Turn on hall lights.

Hop 1:
  Back frames request and calls resolve_situation.

Tool Phase A:
  resolver finds hall light resources,
  binds allowed light actuation tools,
  attaches low-risk reversible household policy,
  returns CandidateUniverse.

Hop 2:
  Back sees one complete low-risk executable set,
  calls batch_invoke_capabilities for all hall light bindings.

Tool Phase B:
  tools execute in parallel,
  readback verifies if available.

Hop 3:
  Back submits completed / partial / failed result.
```

Expected wall clock target:

```text
LLM latency cost:
  2 to 3 LLM calls, not 7 or 8.

Tool latency cost:
  resolver and reads parallelized where possible.
  batch execution for multiple resources.
```

### Internal States Grouped Into LLM Hops

```text
LLM Hop 1:
  S0_INTAKE
  S1_FRAME_REQUEST
  S2_RESOLVE_SITUATION tool call

Tool Phase A:
  Plane 4 resolver runs
  Plane 2 policy roles selected
  Plane 3 contracts bound
  CandidateUniverse + PromptPack returned

LLM Hop 2:
  S3_READ_CANDIDATE_UNIVERSE
  S4_DECIDE_PATH
  S5_BUILD_TOOL_PARAMS
  S6_INVOKE_OR_ASK_OR_BLOCK tool call

Tool Phase B:
  read/batch/execute/verify in parallel where allowed
  structured observation returned

LLM Hop 3:
  S7_VERIFY result interpretation if needed
  S8_SUBMIT_RESULT
```

If Hop 2 asks HIL instead of executing, the HIL response re-enters as the next observation and may consume Hop 3 or Hop 4 depending on policy.

### Parallelism Rule

Back should not serially call tools when the operation is read-only or when a batch mutation is explicitly allowed.

```text
Parallelizable:
  conflict reads across calendar/tasks/reminders
  read state across Hue/Matter lights
  read health sources after consent allows
  verify multiple resources after batch execution

Not parallelizable unless policy allows:
  multiple writes with irreversible side effects
  financial transfer + confirmation + execution
  cross-user external communication
  actions requiring ordered preconditions
```

The LLM chooses the batch action. The runtime executes the batch deterministically and returns one observation.

Back should not expose private reasoning. The observable loop output should be structured:

```text
state: S3_READ_CANDIDATE_UNIVERSE
decision: NEEDS_HIL
reason_summary: multiple valid resources remain
next_action: ask_hil
```

### Atomic Loop States

```text
S0_INTAKE
  input:
    Front/FSM task envelope
    actor/session/task ids
    safety band
    available Back meta-tools

  prompt must include:
    Back role
    allowed output forms
    no direct native tool access
    must use resolver before side-effecting tool choice

  Back checks:
    is the task understandable enough to frame?
    is actor/session/safety present?
    is this Back's responsibility or should it be blocked/escalated?

  allowed next:
    S1_FRAME_REQUEST
    S8_SUBMIT_BLOCKED if envelope is invalid

S1_FRAME_REQUEST
  input:
    user goal
    recent Front context
    actor/family context summary
    temporal/spatial/person refs if provided

  prompt must include:
    extract references, do not bind tools yet
    preserve uncertainty
    do not collapse guides/policy/tools into one guess

  Back builds RequestFrameDraft:
    actor
    goal
    operation_hints
    resource_references
    people_references
    time_references
    location_references
    risk_hints
    missing_fields

  allowed next:
    S2_RESOLVE_SITUATION
    S6_ASK_MORE if frame is impossible without user input

S2_RESOLVE_SITUATION
  input:
    RequestFrameDraft
    actor
    safety band
    task context

  visible tools:
    resolve_situation
    submit_result only for unrecoverable block

  expected tool call:
    resolve_situation(request_frame, actor_scope, safety_band, task_context)

  Plane 4 must return:
    CandidateUniverse
    PromptPack
    completeness/freshness
    policy verdict
    allowed next actions

  allowed next:
    S3_READ_CANDIDATE_UNIVERSE
    S8_SUBMIT_BLOCKED if resolver fails hard

S3_READ_CANDIDATE_UNIVERSE
  input:
    CandidateUniverse
    PromptPack

  prompt must include:
    ranking is not authority
    check completeness before choosing
    respect policy verdict
    use only bound contracts/guides loaded in PromptPack

  Back checks:
    is candidate generation complete enough?
    are there zero, one, or many valid bindings?
    are there stale/offline projections?
    are there omissions that matter?
    did policy require reads before writes?
    did policy require HIL/confirmation?

  allowed next:
    S4_DECIDE_PATH
    S2_RESOLVE_SITUATION if resolver asks for refinement
    S6_ASK_HIL if ambiguity is already clear
    S8_SUBMIT_BLOCKED if policy denies

S4_DECIDE_PATH
  input:
    CandidateUniverse verdict
    policy gates
    allowed next actions

  decision matrix:
    zero bindings + marketplace available -> submit missing_capability_suggestion
    zero bindings + no path -> submit cannot_execute
    incomplete projection -> ask refresh / ask HIL / block by policy
    multiple valid resources -> ask HIL
    policy requires confirmation -> ask HIL
    policy requires prerequisite reads -> invoke read bindings first
    one safe executable binding -> build params
    verifier required after write -> remember verification obligation

  allowed next:
    S5_BUILD_TOOL_PARAMS
    S6_INVOKE_READ
    S6_ASK_HIL
    S8_SUBMIT_BLOCKED

S5_BUILD_TOOL_PARAMS
  input:
    selected binding
    exact ToolContract
    GuideCard
    PolicyCard constraints
    user/task data

  prompt must include:
    fill only schema fields
    never invent required values
    use guide examples only for shape, not facts
    if required field is missing, ask or block

  Back output:
    capability_name
    params
    missing_params if any
    verification_obligation if any

  allowed next:
    S6_INVOKE_TOOL
    S6_ASK_MORE
    S8_SUBMIT_BLOCKED

S6_INVOKE_OR_ASK_OR_BLOCK
  input options:
    valid params
    HIL question
    missing-field question
    block reason

  visible tools:
    invoke_capability for bound executable/read tools
    HIL lane / submit_result path
    submit_result for final blocked/cannot_execute

  Back rules:
    one mutation at a time unless batch is explicitly allowed
    reads can fan out only if policy allows
    writes require policy gates passed
    HIL question must include the real candidate set or state projection is incomplete

  allowed next:
    S3_READ_CANDIDATE_UNIVERSE after read results update universe
    S7_VERIFY after mutation
    S8_SUBMIT_RESULT after HIL/block/cannot_execute

S7_VERIFY
  input:
    invocation result
    verifier binding
    GuideCard read-after-write instructions
    policy verification requirement

  prompt must include:
    do not claim success until verifier passes if verifier is required
    if verifier unavailable, report degraded verification

  Back checks:
    did provider return success?
    does read-after-write confirm expected state?
    did side effects match requested operation?
    does audit need additional note?

  allowed next:
    S8_SUBMIT_RESULT
    S6_INVOKE_OR_ASK_OR_BLOCK for repair if safe
    S8_SUBMIT_BLOCKED if verification fails and repair is unsafe

S8_SUBMIT_RESULT
  input:
    final outcome
    verification status
    HIL decisions
    audit notes
    user-facing summary

  visible tools:
    submit_result

  Back output:
    status: completed / needs_hil / cannot_execute / blocked / failed / partial
    user_summary
    evidence_summary
    audit_fields
```

### Prompt Assembly Layers

Back prompt should be layered, not one giant prompt.

```text
Layer 0 - Static Back Contract
  role: governed executor
  never invent resources/contracts/authority
  use resolver before side-effecting actions
  obey safety band
  submit result through FSM

Layer 1 - ReAct State Instructions
  current state
  allowed next states
  visible tools for this state
  expected output shape

Layer 2 - Task Envelope
  user goal
  Front context
  actor/session/task ids
  temporal/spatial/person references

Layer 3 - Runtime Observation
  last tool result
  CandidateUniverse
  PromptPack
  HIL response
  invocation result

Layer 4 - Selected Cards
  PolicyCard snippets
  GuideCard snippets
  ToolContract snippets

Layer 5 - Output Schema
  tool call schema or submit_result schema
```

ASCII prompt pipeline:

```text
           +---------------------+
           | Static Back Contract|
           +----------+----------+
                      |
           +----------v----------+
           | State instruction   |
           +----------+----------+
                      |
           +----------v----------+
           | Task envelope       |
           +----------+----------+
                      |
           +----------v----------+
           | Runtime observation |
           +----------+----------+
                      |
           +----------v----------+
           | Policy/Guide/Contract cards
           +----------+----------+
                      |
           +----------v----------+
           | Expected output     |
           +---------------------+
```

### Atomic Dynamic Injection By State

```text
S0_INTAKE injects:
  TaskEnvelope only
  no CandidateUniverse yet

S1_FRAME_REQUEST injects:
  TaskEnvelope
  minimal actor/family context
  temporal/spatial/person reference hints

S2_RESOLVE_SITUATION injects:
  RequestFrameDraft
  resolver tool schema
  no executable native tool contracts yet

S3_READ_CANDIDATE_UNIVERSE injects:
  CandidateUniverse
  completeness/freshness
  omissions
  policy verdict
  allowed next actions

S4_DECIDE_PATH injects:
  CandidateUniverse summary
  PolicyCard gates
  ambiguity list
  missing data list

S5_BUILD_TOOL_PARAMS injects:
  one selected ToolContract
  one or more GuideCards for that binding
  relevant PolicyCard constraints
  user-provided facts

S6_INVOKE_OR_ASK_OR_BLOCK injects:
  final params or HIL choices or block reason
  allowed tool call only

S7_VERIFY injects:
  invocation result
  verifier contract
  expected state
  verification policy

S8_SUBMIT_RESULT injects:
  final status
  evidence summary
  user-facing summary constraints
```

### Tool Visibility By State

```text
S0 Intake:
  submit_result only for malformed/blocking envelope

S1 Frame:
  resolve_situation
  submit_result for impossible task

S2 Resolve:
  resolve_situation

S3 Read CandidateUniverse:
  inspect_binding
  submit_result
  HIL path if provided by controller

S4 Decide:
  inspect_binding
  invoke_capability only for allowed read/prerequisite bindings
  HIL path
  submit_result

S5 Build Params:
  invoke_capability for selected binding only
  submit_result for missing params/block

S6 Invoke/Ask/Block:
  invoke_capability or HIL/submit_result, not both in same atomic step

S7 Verify:
  verifier binding only
  submit_result

S8 Submit:
  submit_result only
```

### Atomic State Transitions

```text
S0 -> S1
  when task envelope is valid enough to frame

S1 -> S2
  when RequestFrameDraft exists

S1 -> S6_ASK_MORE
  when user goal is too under-specified to even resolve

S2 -> S3
  when resolve_situation returns CandidateUniverse

S2 -> S8_BLOCKED
  when resolver cannot run or actor scope is invalid

S3 -> S4
  when candidate universe is readable

S3 -> S2
  when resolver asks for refinement or projection refresh

S4 -> S6_ASK_HIL
  when ambiguity/confirmation requires human input

S4 -> S5
  when exactly one next binding is allowed

S4 -> S6_INVOKE_READ
  when required prerequisite read exists

S4 -> S8_BLOCKED
  when policy denies or capability is absent

S5 -> S6_INVOKE_TOOL
  when params validate against selected ToolContract

S5 -> S6_ASK_MORE
  when required params are missing

S6 -> S7
  after mutation that requires verification

S6 -> S3
  after prerequisite reads update the situation

S6 -> S8
  after HIL/cannot_execute/block finalization

S7 -> S8
  when verification passes or degraded verification is reportable

S7 -> S6
  when safe repair is allowed
```

### Failure And Repair Loops

```text
Resolver returns incomplete projection:
  Back does not pick best guess.
  Back asks for refresh, asks HIL with incomplete-projection wording, or blocks.

Multiple valid resources:
  Back asks HIL with all candidates.

Policy requires prerequisite read:
  Back invokes read tools first, then returns to S3/S4.

Tool params missing:
  Back asks user only for missing fields.

Tool invocation fails recoverably:
  Back reads structured error, repairs params if guide/contract allows, retries within limit.

Tool invocation fails non-recoverably:
  Back submits failed/cannot_execute with evidence summary.

Verifier fails:
  Back does not claim success.
  Back either repairs safely or submits verification_failed.
```

### Example Atomic Walkthrough - Scheduling

```text
User: Schedule Riley's dentist appointment Monday at 3.

S0 intake:
  goal present, actor present, safety band present

S1 frame:
  operation_hint: commitment.time_bound.create
  participant: Riley
  time_ref: Monday 3pm
  resource_ref: family calendar implied

S2 resolve:
  call resolve_situation(frame)

S3 read universe:
  required roles from policy:
    temporal resolver
    conflict readers
    writer
    verifier
  bindings:
    calendar.list_events
    tasks.list_tasks
    reminders.list_reminders
    calendar.create_event
    calendar.get_event
  verdict:
    prerequisite_reads_required

S4 decide:
  invoke conflict readers first

S6 invoke reads:
  calendar.list_events, tasks.list_tasks, reminders.list_reminders

S3 read updated universe:
  no conflict or conflict found

S4 decide:
  if no conflict -> S5 build create_event params
  if conflict -> S6 ask HIL

S5 build params:
  title, start, end, attendees from user/context

S6 invoke:
  calendar.create_event

S7 verify:
  calendar.get_event returned expected event

S8 submit:
  completed + verified summary
```

### Example Atomic Walkthrough - Living Room Lights

```text
User: Turn off the living room lights.

S1 frame:
  operation_hint: home.light.power.off
  location_ref: living room

S2 resolve:
  local resources in living room:
    Hue group
    Matter floor lamp
    Matter ceiling bulbs
  policy:
    low-risk reversible actuation
  verdict:
    executable_batch_if_complete

S4 decide:
  if completeness is complete_for_living_room_lights -> invoke batch
  if projection partial/offline -> ask/refresh/block based on policy

S6 invoke:
  hue.set_group_state(off)
  matter.set_device_state(off)

S7 verify:
  read light states if verifier available

S8 submit:
  completed or partially_completed with exact failed resources
```

### Plane 1 Open Questions

```text
1. Should Back see one high-level resolve_situation tool or separate resolve_resources/bind_capabilities tools?
2. Should Plane 1 state be deterministic outside the LLM, with the LLM only choosing allowed actions inside a state?
3. What is the retry limit for recoverable tool invocation errors?
4. Can Back call multiple read tools in one atomic step, or must batch reads be a separate batch_invoke_capabilities binding?
5. How should HIL responses re-enter the loop: as a new Front envelope or as a Back observation?
6. Should incomplete projection always block side effects, or can policy allow explicit user confirmation?
7. How much of CandidateUniverse should be injected when it is large?
8. What fields are mandatory in RequestFrameDraft before resolver call?
9. Does Back own parameter repair, or should Plane 4/contract validators repair before invocation?
10. How does Back distinguish user-facing summary from audit/evidence summary?
11. Should verification failure trigger automatic repair, or always HIL for side-effecting writes?
12. How are long-running tool jobs represented in the ReAct loop?
13. How does Back avoid repeating resolver calls with the same frame when no new information changed?
14. What prompt budget policy decides which PolicyCards/GuideCards/ToolContracts are included?
15. How does the loop handle multi-step workflows without turning into an unbounded autonomous planner?
16. What is the hard wall-clock target for simple household actions such as hall lights?
17. Which verification obligations can run inside Tool Phase B without another LLM hop?
18. Does batch_invoke_capabilities support mixed providers, partial failure, and per-resource verification?
19. When prerequisite reads complete, can the controller update CandidateUniverse deterministically before Hop 2 resumes?
20. What telemetry records LLM hop count, tool phase time, and total task latency for every Back task?
```

---

## Plane 2 Detail - Constitution And Usage Descriptions

Purpose:

```text
Tell Back and the resolver what rules apply and how bound tools should be used.
Do not become a giant workflow-permutation library.
```

Artifacts:

```text
PolicyCard
  id
  applies_when
  required_roles
  gates: allow / ask / deny / verify
  HIL triggers
  audit requirements
  privacy projection
  freshness requirements

GuideCard
  id
  bound_tool_or_family
  how_to_call
  param construction notes
  read-before-write sequence
  read-after-write verifier
  limitations and examples
```

ASCII relation:

```text
                 +----------------------+
request_frame -->| policy selector      |
                 +----------+-----------+
                            |
                            v
                    PolicyCard(s)
                            |
                            v
                 required roles / gates

                 +----------------------+
bound binding -->| guide selector       |
                 +----------+-----------+
                            |
                            v
                     GuideCard(s)
```

Constitution vs guide:

```text
Constitution:
  before writing commitment.time_bound, gather conflict signals and ask HIL on ambiguity

Guide:
  for calendar.create_event, pass title/start/end/attendees and verify with calendar.get_event
```

What Plane 2 needs from other planes:

```text
Plane 1 -> request frame and current decision state
Plane 3 -> contract metadata: effects, resource kind, verification support, safety band
Plane 4 -> bound candidates so only relevant guides are loaded
```

What Plane 2 provides to other planes:

```text
Plane 1 -> prompt-sized policy/guide snippets
Plane 3 -> required metadata hooks contracts must expose
Plane 4 -> role requirements and policy constraints for binding
```

No-permutation rule:

```text
Do not write:
  calendar+task+reminder+school+car constitution

Compose:
  time_bound_commitment_policy
  family_visibility_policy
  conflict_check_policy
  adapter guides for bound tools only
```

Small example:

```text
Request frame:
  operation: commitment.time_bound.create

PolicyCard says:
  required_roles: conflict_readers, writer, verifier
  gate: check_conflicts_before_write

GuideCards load after binding:
  calendar_activity_v1
  tasks_activity_v1
  reminders_activity_v1
```

---

## Plane 3 Detail - Standard Tool Contracts And Tool Design

Purpose:

```text
Make every tool bindable, governable, invokable, and verifiable.
The contract must be machine-readable enough that Back does not guess.
```

Minimum contract shape:

```text
ToolContract
  name
  provider / adapter id
  operation
  resource_kind
  resource_instance_binding
  input_schema
  output_schema
  side_effects
  safety_band
  permissions
  freshness requirements
  verifier capability
  errors
  limitations
```

ASCII contract card:

```text
+------------------------------------+
| tool.execute.calendar.create_event |
+------------------------------------+
| operation: commitment.create        |
| resource_kind: calendar             |
| input: title, start, end, attendees |
| effect: writes time-bound event     |
| safety: GREEN/MEDIUM by context     |
| verifier: calendar.get_event        |
| guide: calendar_activity_v1         |
+------------------------------------+
```

Contract must support binding:

```text
resource kind + operation + actor authority
  -> compatible tool bindings
```

Contract must support prompting:

```text
selected binding
  -> exact schema
  -> examples
  -> limitations
  -> verifier
```

What Plane 3 needs from other planes:

```text
Plane 1 -> what Back must know at invocation time
Plane 2 -> policy hooks, guide links, required verification metadata
Plane 4 -> binding/query needs: resource kind, operation, authority, freshness
```

What Plane 3 provides to other planes:

```text
Plane 1 -> contract snippets for selected bindings
Plane 2 -> effects/risk metadata for policy selection
Plane 4 -> machine-readable binding metadata
```

Bad contract:

```text
name: create_event
description: creates events in calendar
```

Good contract:

```text
name: tool.execute.calendar.create_event
operation: commitment.time_bound.create
resource_kind: calendar.event_store
requires: title, start, end
effects: writes_family_visible_commitment
verifier: tool.read.calendar.get_event
guide: calendar_activity_v1
policy_hooks: time_bound_commitment, family_visibility
```

---

## Plane 4 Detail - Tool Search And Provision To Back

Purpose:

```text
Do not return a naked ranked list.
Build the runtime package Back needs to act safely.
```

Core flow:

```text
request_frame
  -> policy role requirements
  -> resource resolution
  -> capability binding
  -> contract/guide/policy loading
  -> CandidateUniverse + PromptPack
```

ASCII resolver:

```text
                 +---------------------+
                 | request_frame       |
                 +----------+----------+
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
  +---------------+ +---------------+ +----------------+
  | policy roles  | | resources     | | operation      |
  | from Plane 2  | | local world   | | affordances    |
  +-------+-------+ +-------+-------+ +--------+-------+
          |                 |                  |
          +-----------------+------------------+
                            |
                            v
                   +----------------+
                   | bindings       |
                   +--------+-------+
                            |
                            v
                   +----------------+
                   | PromptPack     |
                   | candidates     |
                   | contracts      |
                   | guides/policy  |
                   +----------------+
```

CandidateUniverse shape:

```text
CandidateUniverse
  request_frame
  resource_candidates
  capability_bindings
  completeness
  freshness
  omissions
  policy_verdict
  required_guides
  required_contracts
  next_allowed_actions
```

PromptPack shape:

```text
PromptPack
  compact policy cards
  selected guide cards
  selected contract cards
  candidate universe summary
  allowed meta-tools for next step
```

What Plane 4 needs from other planes:

```text
Plane 1 -> request_frame, actor, safety band, task context
Plane 2 -> policy role requirements and guide lookup rules
Plane 3 -> searchable/bindable contract metadata
```

What Plane 4 provides to other planes:

```text
Plane 1 -> CandidateUniverse + PromptPack
Plane 2 -> evidence of which policies/guides were selected
Plane 3 -> binding failures that reveal contract gaps
```

Bad output:

```text
top_k:
  1. calendar.create_event score 0.91
  2. calendar_activity_v1 score 0.88
```

Good output:

```text
CandidateUniverse:
  operation: commitment.time_bound.create
  required_roles:
    conflict_readers: calendar.list_events, tasks.list_tasks, reminders.list_reminders
    writer: calendar.create_event
    verifier: calendar.get_event
  completeness: complete_for_connected_commitment_sources
  verdict: check_conflicts_before_write
  prompt_pack: policy + bound guides + exact contracts
```

---

## Four-Plane Handshake - One Execution Turn

```text
Plane 1 Back:
  "I need to resolve this task."
        |
        v
Plane 4 resolver:
  asks Plane 2 what policy roles apply
  asks Plane 3 what contracts can satisfy those roles
  joins with local resources and authority
        |
        v
Plane 4 returns:
  CandidateUniverse + PromptPack
        |
        v
Plane 1 Back:
  invokes, asks HIL, blocks, verifies, or submits
```

If one plane is weak:

```text
Plane 1 weak -> Back guesses or skips gates
Plane 2 weak -> policy/guidance arrives too late or explodes combinatorially
Plane 3 weak -> tools cannot be bound, verified, or prompted safely
Plane 4 weak -> search returns top-K instead of truthful candidate universe
```

---

## Human Quick Map

Short version:

```text
For Back execution, top-K plus vector search is the wrong center of gravity.

It is built for:
  "show me likely matches"

But our problem is:
  "construct the truthful candidate universe before action"
```

For side effects, this is not mainly a search problem. It is a binding problem.

Back should not start from a ranked list of tool names. Back needs a situated runtime answer:

```text
Who is asking?
What did they refer to?
What real resources could that refer to?
Which of those resources are visible or controllable?
What operation is requested?
Which capabilities can perform that operation on each resource?
Is the candidate set complete enough?
What policy, HIL, guidance, or verifier applies?
```

### Old Center Of Gravity

```text
User text
   |
   v
semantic/vector search over tool catalog
   |
   v
ranked top-K tool list
   |
   v
Back picks one
   |
   v
invoke tool
```

Why this fails:

```text
The ranked list can hide a materially relevant candidate.
It can hide a related tool required by constitution, a second adapter for the same room,
a second health source, a second payment rail, or a second resource instance.
HIL after that is biased because the user is asked about only what search happened to show.
```

### New Center Of Gravity

```text
User text
   |
   v
situation frame
   |
   v
resource universe
   |
   v
operation binding
   |
   v
policy / HIL / freshness verdict
   |
   v
Back acts or asks
```

This is the core shift:

```text
Old model:
  user text -> semantic search -> ranked tool list -> Back picks

New model:
  user text -> situation frame -> resource universe -> operation binding -> policy verdict -> Back acts or asks
```

### Minimal Failure Test - Two Cars

This is not the main problem. It is a small, easy-to-see test that exposes why incomplete candidate generation makes HIL and execution unsafe.

User says:

```text
Turn on climate control of my car.
```

Bad start:

```text
discover_capabilities("turn on climate control of my car")
```

Why it is bad:

```text
It searches descriptions of tools.
It may return Tesla first.
It may omit Audi.
It does not prove what "my car" means in this household.
```

Better start:

```text
resolve resource phrase: "my car"
actor: Alex
resource kind: vehicle
operation hint: climate.start
```

Then the runtime asks the connected-resource projection:

```text
vehicles accessible to Alex:
  - Tesla Model Y
  - Audi Q7
```

Then it binds operations:

```text
Tesla Model Y -> tool.execute.transport.tesla.start_climate
Audi Q7       -> tool.execute.transport.audi.start_climate
```

Then it returns a verdict:

```text
needs_disambiguation
```

Only now does HIL make sense:

```text
Which car should I warm up: Tesla Model Y or Audi Q7?
```

### 100k Tools Does Not Mean Search 100k Tools

The big insight:

```text
Execution should usually search the actor's local world projection first,
not the global catalog of every possible IFL adapter/tool.
```

The global catalog may contain 100k tools or more. Everyday execution usually concerns the current household world:

```text
connected cars
connected lights
connected calendars
linked health accounts
linked finance accounts
family people
places
rooms
devices
lists
feeds
```

That local world may be hundreds or thousands of resources, but it is not the entire marketplace.

Use the global catalog for:

```text
adapter installation
missing-capability suggestions
developer/operator browsing
documentation lookup
fallback exploration
```

Use the local world projection for:

```text
actual Back execution
HIL candidate sets
authority checks
resource disambiguation
side-effect binding
```

### CandidateUniverse, Not Top-K

The replacement primitive is not `top_k`. It is something like `CandidateUniverse`.

Example shape:

```json
{
  "request_frame": {
    "operation": "vehicle.climate.start",
    "resource_reference": "my car",
    "actor": "Alex"
  },
  "resource_candidates": [
    "vehicle.tesla.model_y",
    "vehicle.audi.q7"
  ],
  "capability_bindings": [
    ["vehicle.tesla.model_y", "tool.execute.transport.tesla.start_climate"],
    ["vehicle.audi.q7", "tool.execute.transport.audi.start_climate"]
  ],
  "completeness": "complete_for_actor_visible_connected_vehicles",
  "verdict": "needs_disambiguation"
}
```

In this artifact, `completeness` matters more than `score`.

### Four Indexes, Not One Semantic Index

The new model likely needs several small runtime indexes instead of one semantic/vector index:

```text
Resource index
  actor -> visible resources
  resource kind -> instances
  aliases -> resources
  location / room / member -> resources

Affordance index
  resource kind + operation -> capabilities
  resource instance -> adapter capabilities

Authority / policy index
  actor + resource + operation -> allow / ask / deny

Freshness / completeness index
  projection -> fresh / stale / offline / partial
  adapter -> connected / degraded / offline
```

ASCII view:

```text
                       +-------------------------+
                       |  User request           |
                       |  "warm up my car"      |
                       +-----------+-------------+
                                   |
                                   v
                       +-------------------------+
                       |  Situation frame        |
                       |  actor, refs, operation |
                       +-----------+-------------+
                                   |
                 +-----------------+-----------------+
                 |                 |                 |
                 v                 v                 v
       +------------------+ +------------------+ +------------------+
       | Resource index   | | Authority index | | Freshness index  |
       | my car -> cars   | | can Alex act?   | | is view fresh?   |
       +--------+---------+ +--------+---------+ +--------+---------+
                |                    |                    |
                +--------------------+--------------------+
                                     |
                                     v
                       +-------------------------+
                       |  Candidate resources    |
                       |  Tesla, Audi            |
                       +-----------+-------------+
                                   |
                                   v
                       +-------------------------+
                       |  Affordance index       |
                       |  climate.start bindings |
                       +-----------+-------------+
                                   |
                                   v
                       +-------------------------+
                       |  CandidateUniverse      |
                       |  verdict: ask user      |
                       +-------------------------+
```

### Where Vector Search Still Belongs

Vector search can still be useful. It is demoted, not deleted.

Good uses:

```text
fuzzy synonym help
tool-guide / docs lookup
marketplace browsing
ranking already-complete candidates for display
low-risk exploratory suggestions
```

Bad uses:

```text
deciding the candidate universe
hiding Audi because Tesla ranked higher
deciding authority, ownership, consent, or HIL options
acting as the only path to side-effect tools
```

Hard line:

```text
Ranking is allowed after completeness, never before completeness.
Any design that can return Tesla while silently omitting Audi fails the search model.
```

### Back's Future Question

Back should not ask:

```text
What tool matches this sentence?
```

Back should ask:

```text
resolve_situation(user_goal)
-> candidate universe
-> verdict
```

Then Back can decide:

```text
one safe binding       -> execute
multiple valid options -> ask HIL
policy needs approval  -> ask confirmation
projection incomplete  -> report/refresh/ask
blocked                -> submit blocked result
```

---

## Why This Whiteboard Exists

The earlier Back tool audit proved that the current runtime path works end to end:

```text
Back meta-tool -> discover_capabilities -> invoke_capability -> Fabric -> provider -> native/external tool
```

But the follow-up discussion exposed a deeper problem: the current `discover_capabilities(intent, domain)` shape is too small for a real FamilyOS runtime with IFL-connected cars, health apps, smart-home systems, finance apps, shopping services, calendars, reminders, and future third-party/company adapters.

The problem is not just "calendar prompt contract appears in discovery." That is a symptom. The larger problem is capability discovery under ambiguity, resource identity, policy, and scale.

---

## Grounded Starting Facts

### Current Back tool model

Back does not receive every app/device capability as a direct LLM function. It receives a small set of meta-tools, especially:

- `discover_capabilities`
- `invoke_capability`
- `batch_invoke_capabilities`
- `submit_result`

The live audit is captured in [back_tool_contract_whiteboard.md](back_tool_contract_whiteboard.md).

### Current prompt/profile issue

Prompt/activity contracts such as `calendar_activity_v1` are guidance/profile objects. They are not executable tools.

The current discovery path can return these records beside executable capabilities, which can make Back see a guidance contract as a candidate tool. The user pointed out this is wrong: guidance belongs with tool usage after a tool or activity context is selected, not as a selectable capability.

### IFL/Fabric architecture expectation

The IFL/Fabric diagrams already expect scale beyond local family apps:

- [interkernel_fabric_layer.mmd](../../architecture_diagrams/bridge/interkernel_fabric_layer.mmd) describes company-signed IFL adapters for devices, banks, health, transport, shopping, education, communication, sensors, fitness, and more.
- [bridge_architecture.mmd](../../architecture_diagrams/bridge/bridge_architecture.mmd) places Bridge as the connector/security gateway for all external services.
- [fabric_new.mmd](../../k1/fabric/fabric_new.mmd) positions Fabric as K1's capability registry, retrieval, resolution, and execution layer.

The current manifest idea includes category, type, description, schemas, safety band, permissions, latency, and events. That is necessary, but not sufficient for the new discovery problem.

---

## Conversation Ledger

### 1. User's first correction: guidance is not a capability

User said `calendar_activity_v1` does not need to be inside `find_capabilities` at all. It is tool guidance. The planned direction was that this guidance and future constitution/tooling material would be injected into Back when a tool is selected.

Captured issue:

```text
find_capabilities should find executable things.
calendar_activity_v1 should guide use of calendar tools.
```

### 2. Assistant proposal: executable discovery plus execution card

Assistant suggested:

```text
discover_capabilities -> executable capabilities only
prepare/select capability -> execution card with guidance/constitution
invoke_capability -> execute
```

The distinction proposed was:

- Constitution: general execution law.
- Activity/tool profile: adapter/domain usage guide.
- Capability contract: executable tool schema and metadata.

### 3. User rejection: late constitution duplicates discovery and misses other tools

User rejected the narrow version. If Back first discovers only calendar capabilities, and then a constitution says "check task tools for duplicates/conflicts," the task tool was never discovered.

Important failure mode:

```text
discover("create calendar appointment") returns calendar tools.
constitution later says tasks/reminders may matter.
Back now has to redo discovery or may never find the relevant non-calendar tool.
```

Conclusion from rejection:

```text
Constitution/guidance cannot be a late decorative prompt after a narrow tool search.
It must influence what needs to be discovered or bound.
```

### 4. Assistant proposal: activity/effect classification before discovery

Assistant suggested moving above tool discovery:

```text
understand activity/effect class
load governing constitution/policy
derive required capability roles
discover tools for each role
bind concrete tools
plan execution
execute governed graph
```

Example for scheduling:

```text
activity: scheduling.commitment.create
required roles:
  - temporal resolver
  - participant resolver
  - commitment readers
  - calendar writer
  - verification reader
optional roles:
  - reminder writer
  - task reader
```

### 5. User rejection: this still smells calendar-shaped and vocabulary explodes

User challenged the proposal with IFL/external scenarios:

- car tool via IFL
- health tool
- external apps like Hue lights
- many other tools/services

User's concern:

```text
This kind of typing vocabulary becomes a web of things after 100 tools.
At 100k tools, hand-written categories, constitutions, and tool usage guides do not scale.
```

### 6. Assistant proposal: small primitive facets plus namespaced domain vocabularies

Assistant suggested a capability-passport direction:

```text
operation: read | search | subscribe | create | update | delete | actuate | communicate | purchase | navigate
effect: data.read | data.write | physical_environment.change | physical_security.change | financial_transfer | health_sensitive_read
risk: privacy | money | physical_safety | security | reversibility | cross_member_impact | external_world_side_effect
resource namespace: matter.home.light | vehicle.lock | fhir.observation.heart_rate | schema.org.Event | etc.
```

The idea was that constitutions govern stable effect/risk facets, while tool guides explain adapter quirks.

### 7. User rejection: even facets do not solve resource ambiguity and missing adapters

User rejected agreement again with a concrete scenario:

```text
User says: "turn on climate control of my car"
User has 2 cars.
HIL exists, but discovery returns Tesla first and Audi never appears.
```

This changes the problem shape.

The issue is not only taxonomy. It is incomplete candidate discovery under ambiguous resource identity. A system cannot ask useful HIL if it never discovered the second relevant resource/tool. "Tesla came first" is not a valid answer if Audi was also connected and compatible.

User explicitly reframed the problem:

```text
Think of this as a new problem we are solving.
It does not fit into any bucket of problems solved in the past or typical software engineering ones.
```

---

## What Is Not Agreed

These directions are not accepted as sufficient:

### Not sufficient: natural-language capability search as the main resolver

`discover_capabilities(intent="turn on climate control of my car")` cannot be the core authority. Semantic retrieval may rank Tesla first and omit Audi, especially when top-k, description quality, or embeddings bias one adapter.

### Not sufficient: prompt guidance after tool selection

If guidance arrives after a narrow discovery, it cannot recover missing candidate tools or resources without redoing discovery. It is too late to shape the search space.

### Not sufficient: per-app constitution

Calendar constitution, car constitution, health constitution, Hue constitution, and every combination of them does not scale.

### Not sufficient: one flat global ontology

A giant manually curated vocabulary of every tool/resource/action also becomes a web of things. It fails when the adapter universe grows.

### Not sufficient: HIL as a patch for incomplete discovery

HIL can resolve ambiguity only after the system has discovered the relevant alternatives. If Tesla appears and Audi never appears, HIL cannot repair the missing candidate.

---

## New Problem Statement

Back capability discovery is not just tool search.

It is situated resolution across at least four different target spaces:

1. **Resource discovery:** What real-world objects/accounts/people/places/devices could the user mean?
2. **Operation discovery:** What action is requested over those resources?
3. **Capability binding:** Which connected tools/adapters can perform that operation on each candidate resource?
4. **Policy/guidance loading:** What rules, approvals, privacy projections, and usage guides apply before execution?

The current meta-tool model collapses these into one operation:

```text
discover_capabilities(intent, domain)
```

That is too lossy for IFL scale.

---

## Concrete Failure: Two Cars

User request:

```text
Turn on climate control of my car.
```

Household reality:

```text
Alex has access to two cars:
  - Tesla Model Y through Tesla adapter
  - Audi Q7 through Audi adapter
```

Bad current-style flow:

```text
Back asks discover_capabilities("turn on climate control of my car")
Fabric retrieval returns tool.execute.transport.tesla.start_climate
Audi is absent because semantic rank/top-k/provider text favored Tesla
Back asks HIL: "Should I turn on the Tesla?"
```

Why this is wrong:

```text
The system did not discover the true ambiguity.
The HIL question is biased by incomplete candidate generation.
The user may have meant Audi, but Audi was never in the frame.
```

Correct required shape:

```text
Resolve "my car" against user/family/connected-resource projection.
Find all accessible vehicle resources, not just one adapter capability.
For each candidate vehicle, bind compatible climate-control capabilities.
If more than one candidate remains, ask HIL with all real candidates.
Only execute after disambiguation and policy gate.
```

Possible Back observation:

```json
{
  "resource_candidates": [
    {"resource_id": "vehicle.tesla.model_y", "display": "Tesla Model Y", "owner_or_scope": "Alex"},
    {"resource_id": "vehicle.audi.q7", "display": "Audi Q7", "owner_or_scope": "Alex"}
  ],
  "operation": "vehicle.climate.start",
  "bound_capabilities": [
    {"resource_id": "vehicle.tesla.model_y", "capability": "tool.execute.transport.tesla.start_climate"},
    {"resource_id": "vehicle.audi.q7", "capability": "tool.execute.transport.audi.start_climate"}
  ],
  "verdict": "needs_disambiguation"
}
```

This is different from normal top-k tool retrieval.

---

## Concept Distinctions

### Capability contract

Concrete invokable operation.

Examples:

- `tool.execute.transport.tesla.start_climate`
- `tool.execute.transport.audi.start_climate`
- `tool.read.health.fitbit.sleep_score`
- `tool.execute.home.hue.set_brightness`

Contract should describe schema, provider, permissions, side effects, safety band, and machine-readable metadata.

### Resource instance

A concrete thing in the household/world that the user may refer to.

Examples:

- Alex's Tesla Model Y
- Alex's Audi Q7
- Living room Hue group
- Riley's Fitbit account
- Household grocery list
- Google Calendar feed for school events

Resource instances are not the same as tools. A single adapter can expose many resources; many adapters can expose equivalent operations for different resources.

### Adapter manifest

Company-signed IFL declaration of capabilities, permissions, events, schemas, and adapter identity.

At scale, the manifest likely needs more than descriptions. It may need to declare resource models, operation templates, supported resource kinds, and discovery/readback paths.

### Tool/activity guide

Usage guidance for a tool family or adapter.

Examples:

- `calendar_activity_v1`
- future vehicle climate guide
- future health read/privacy guide
- future smart-home lighting guide

It should explain how to use a bound capability correctly, not decide global policy.

### Constitution/policy

Executable household/system law.

It decides authority, approval, privacy, freshness requirements, and safe mutation boundaries. It should not micromanage every tool or adapter.

### HIL

Human-in-loop resolution or approval.

HIL is valid only when the system has built a faithful candidate set or knows what remains unknown. It should not mask incomplete discovery.

---

## Emerging Architecture Tension

The existing Fabric diagram describes high-scale registry/retrieval targets, including 100k contracts, semantic retrieval, hard filters, and soft ranking.

That is still not enough for this problem if retrieval starts from free text and top-k tools. The new requirement is candidate completeness for situated resources.

The runtime needs to know:

```text
Who is asking?
What resource phrase did they use?
Which resources are visible/owned/controllable by that actor?
Which adapters expose operations over those resources?
Which candidates were excluded and why?
Does the ambiguity require HIL?
```

This is closer to a resource/capability graph than a search box.

---

## Possible Directions To Discuss Next

These are not final decisions. They are candidate directions for the next design round.

### Direction A - Resource-first discovery

Before finding tools, resolve resource phrases:

```text
"my car" -> all vehicles accessible to caller
"living room lights" -> all light resources in living room
"Alex's sleep" -> health data resources for Alex, subject to consent
```

Then bind operations to resources:

```text
vehicle + climate_start -> Tesla/Audi climate capabilities
light_group + set_state -> Hue/Matter capabilities
health_sleep + read_window -> Fitbit/Apple/Oura capabilities
```

### Direction B - Separate resource registry from capability registry

Fabric currently indexes capability contracts. IFL/Bridge may also need a connected-resource projection:

```text
ResourceRegistry:
  resource_id
  owner/scope
  adapter_id
  resource_kind
  aliases
  location
  current availability
  supported operations
```

Capability binding would join resource registry + capability registry.

### Direction C - Exhaustive hard-filter candidate generation before ranking

For real-world side effects, do not rely on top-k semantic ranking to generate candidates.

Instead:

```text
1. Hard filter connected resources by actor scope and requested resource kind.
2. Hard filter capabilities by operation compatibility.
3. Only then rank for defaults or presentation.
```

This prevents "Tesla ranked first, Audi omitted" when both are compatible.

### Direction D - HIL after candidate completeness

HIL should receive the candidate set, not just one top-ranked guess:

```text
I found two cars I can control: Tesla Model Y and Audi Q7. Which one should I warm up?
```

If the system cannot guarantee completeness, it should say so internally and choose a conservative path.

### Direction E - Open vocabulary with kernel-level invariants

Avoid both extremes:

```text
Bad: one flat manually curated universe vocabulary.
Bad: totally unconstrained vendor strings.
```

Possible middle:

- Small kernel invariants: operation class, side-effect class, risk class, actor authority, reversibility, resource ownership, verification support.
- Namespaced external semantics: Matter, FHIR, vehicle OEM namespaces, schema.org, banking/open-finance schemas, vendor-specific extension namespaces.
- Unknown or weakly typed adapters fail conservative, especially for side effects.

### Direction F - Discovery should expose omissions and uncertainty

Back needs observations that show not only what was found, but whether discovery was complete:

```json
{
  "candidate_generation": "resource_first",
  "completeness": "complete_for_connected_vehicle_resources",
  "excluded": [
    {"adapter": "fordpass", "reason": "not_connected"},
    {"adapter": "audi", "reason": "connected_but_capability_unavailable"}
  ]
}
```

This turns discovery into an auditable runtime step instead of a hidden ranking result.

---

## Open Questions

1. Where should connected resource inventory live: Bridge IFL registry, Fabric registry, K1 local projection, K0 device/event history, or a joined projection?
2. Should IFL manifests declare only capability templates, or also resource discovery/readback endpoints?
3. How does K1 maintain a local edge-first resource projection when K0/cloud/adapter endpoints are offline?
4. Should `discover_capabilities` be split into separate tools such as `resolve_resources`, `bind_capability_roles`, and `inspect_capability_contract`?
5. How does Back know when discovery is complete enough for HIL or execution?
6. How should unknown/weakly typed adapters be handled without blocking harmless use cases forever?
7. How do we prevent semantic/vector ranking from hiding a relevant adapter or resource?
8. What is the minimal manifest/passport metadata required before FamilyOS allows an adapter into governed execution?
9. How do tool guides remain useful without becoming a combinatorial workflow-guide explosion?
10. What part belongs in deterministic runtime code versus Back's LLM reasoning?

---

## Current Working Conclusion

The problem is not solved by adding `calendar_activity_v1` to Back's prompt, nor by hiding prompt contracts from discovery, nor by writing more app-specific constitutions.

Those are local repairs.

The larger unsolved problem is:

```text
How does FamilyOS perform complete, policy-aware, guidance-aware,
resource-aware capability binding across a huge open IFL/Fabric tool universe
before asking the user or executing a side effect?
```

The two-car example is one minimal failure test. Any design that can return Tesla while silently omitting Audi is not good enough, but that is only one form of the larger bug. The same class of failure appears when calendar discovery misses tasks/reminders required by constitution, when smart-home discovery misses Matter resources, when health discovery misses privacy/consent sources, or when payment discovery misses identity/confirmation requirements.

---

## Scenario Tests, Not The Whole Problem

Use this scenario as one test among many:

```text
User: "Turn on climate control of my car."

Reality:
  - User has access to Tesla and Audi.
  - Both adapters are connected through IFL.
  - Both expose climate-control capability.
  - User did not specify which car.

Required behavior:
  - Discover both cars as resources.
  - Bind both climate-control capabilities.
  - Ask HIL with both choices unless context disambiguates.
  - Do not let semantic top-k hide either candidate.
```

Do not read this as a car-specific design. It is a compact proof that rank-first search can create a false execution world.

---

## New Rejection - Top-K / Vector Search Is The Wrong Primitive

After reviewing the current Fabric retrieval model, the user rejected the whole `top_k + vector/semantic search` premise for Back execution discovery.

Current implemented/documented retrieval shape:

```text
query text
-> embed
-> hard filter
-> soft rank
-> top-K truncate
-> return scored capability contracts
```

Relevant current code/docs:

- [fabric_new.mmd](../../k1/fabric/fabric_new.mmd) describes the Fabric retrieval pipeline as `Embed -> HardFilter -> SoftRanker -> TopKSelector`.
- [retrieval_engine.py](../../k1/fabric/retrieval/retrieval_engine.py) implements `discover_capabilities(domain, intent, safety_band, session_context, top_k)` around that 4-step pipeline.
- [top_k_selector.py](../../k1/fabric/retrieval/top_k_selector.py) defaults to K=10 and caps K at 25.
- [discover_capabilities.yaml](../../k1/contracts/tools/discover_capabilities.yaml) describes discovery as semantic retrieval with `max_top_k_25`.

Why this is a non-fit for the Back execution use case:

```text
Top-K optimizes relevance display.
Back execution needs candidate completeness.

Vector search optimizes fuzzy recall over descriptions.
Back execution needs faithful resolution over actual connected resources and authority.

Ranking chooses what looks most similar.
Back must know every materially relevant candidate before asking HIL or mutating state.
```

The problem is not that K is too small. Increasing K from 10 to 25 to 100 does not fix the class of bug. If the retrieval process is rank-first, a relevant but poorly described, lower-scoring, newly connected, or less common adapter can still be hidden.

Anchor failure:

```text
"turn on climate control of my car"

If Tesla ranks high and Audi ranks low or is not semantically recalled,
Back observes a false world: "Tesla is the candidate."

The real world is: "There are at least two accessible cars, and the request is ambiguous."
```

This makes semantic top-K unsafe as the authoritative discovery path for side-effecting or resource-bound actions.

---

## Search Model We Need To Invent

Working name:

```text
Situated Capability Resolution
```

This is not search in the classic information-retrieval sense. It is a runtime resolution process that must construct a faithful candidate universe before ranking or asking the user.

The model should start from three separate observations:

1. **Utterance frame:** What did the user ask to do, and what references did they use?
2. **World projection:** What resources, accounts, devices, people, places, schedules, and adapters are visible to this actor right now?
3. **Action affordance graph:** Which operations can be performed on which resources through which capabilities, under which policy constraints?

Then resolution becomes:

```text
parse request frame
-> resolve resource references against world projection
-> enumerate candidate resources exhaustively within authority/visibility scope
-> infer requested operation over those resources
-> bind operation to all compatible capabilities per resource
-> evaluate policy/freshness/consent/approval gates
-> return one of:
     executable binding
     needs_disambiguation
     needs_confirmation
     blocked_by_policy
     incomplete_world_projection
```

Ranking can still exist, but only after candidate completeness is established. It is a presentation/defaulting tool, not the authority.

---

## Candidate Completeness Before Ranking

The new invariant should be:

```text
For resource-bound or side-effecting actions, the resolver must enumerate all in-scope candidate resources before selecting or ranking a tool.
```

Example:

```text
Request: "turn on climate control of my car"

Step 1: resolve "my car"
  candidate resources:
    - Tesla Model Y
    - Audi Q7

Step 2: bind operation "vehicle.climate.start"
  candidate bindings:
    - Tesla Model Y -> tool.execute.transport.tesla.start_climate
    - Audi Q7 -> tool.execute.transport.audi.start_climate

Step 3: verdict
  needs_disambiguation because two valid bindings remain
```

This is not top-K. It is set construction with proof of scope.

---

## New Required Runtime Artifact - Candidate Universe

Back should not receive a naked ranked list. It should receive a structured candidate universe:

```json
{
  "resolution_id": "...",
  "request_frame": {
    "operation": "vehicle.climate.start",
    "resource_reference": "my car",
    "actor": "Alex"
  },
  "scope_proof": {
    "resource_projection": "k1_local_connected_resources",
    "projection_freshness": "fresh",
    "authority_scope": "actor_visible_and_controllable_resources"
  },
  "resource_candidates": [
    {"resource_id": "vehicle.tesla.model_y", "display": "Tesla Model Y"},
    {"resource_id": "vehicle.audi.q7", "display": "Audi Q7"}
  ],
  "capability_bindings": [
    {"resource_id": "vehicle.tesla.model_y", "capability": "tool.execute.transport.tesla.start_climate"},
    {"resource_id": "vehicle.audi.q7", "capability": "tool.execute.transport.audi.start_climate"}
  ],
  "verdict": "needs_disambiguation",
  "omissions": []
}
```

The important field is not `score`. The important field is `scope_proof` plus omissions/uncertainty.

---

## What Vector Search May Still Be Used For

Vector/semantic search is not banned from the system. It is demoted.

Allowed uses:

- Fuzzy synonym expansion when parsing an utterance.
- Finding documentation or tool guides after a binding exists.
- Suggesting candidate domains for low-risk exploratory tasks.
- Ranking already-complete candidate sets for UI presentation.
- Developer/operator search across a large catalog.

Not allowed as authority:

- Do not use vector top-K as the only way to discover resources for a side effect.
- Do not let vector rank hide a materially relevant resource or adapter.
- Do not let semantic similarity decide actor authority, ownership, consent, or HIL candidate sets.

---

## Potential Shape Of The Replacement Meta-Tools

Current Back has one collapsed tool:

```text
discover_capabilities(intent, domain)
```

Candidate replacement or expansion:

```text
resolve_request_frame(user_goal, context_refs)
  -> operation candidates, resource references, ambiguity markers

resolve_resources(resource_reference, operation_hint, actor_scope)
  -> all visible/authorized candidate resources plus freshness/completeness

bind_capabilities(operation, resource_candidates, policy_constraints)
  -> all executable bindings or missing-capability diagnostics

inspect_binding(binding_id)
  -> schema, usage guide, policy card, confirmation/HIL requirements

execute_binding(binding_id, params)
  -> deterministic invocation through Fabric/Bridge/provider
```

This does not mean Back must call five tools every time. The runtime can package common paths into one higher-level resolver. The key is that the internals are not rank-first search.

---

## Design Constraint Added - One Gate, Not The Whole Problem

Any proposed search/discovery model must pass the two-car test, but passing it is not sufficient by itself:

```text
Given two connected controllable vehicles, and an utterance that says "my car",
the resolver must surface both candidates or explicitly report that the connected-resource projection is incomplete.
```

If a model can still produce only Tesla because Tesla ranked higher than Audi, it fails.

It must also pass the broader gates already named in this whiteboard: calendar/tasks/reminders hidden conflicts, Hue/Matter room resources, health privacy/consent, finance/payment confirmation, and missing-capability separation between local execution and global marketplace search.

---

## Design Discipline Added - Pros/Cons Before System Design

The current idea is still broad. We should not jump from "top-K is wrong" directly into a new architecture.

Next phase must be:

```text
1. Enumerate candidate search/resolution models.
2. Gauge pros and cons against concrete failure scenarios.
3. Decide which invariants are non-negotiable.
4. Only then design runtime components, APIs, schemas, and Back tools.
```

This whiteboard should keep every suggestion and rejection in one place so the design does not drift into a fashionable but untested architecture.

---

## Candidate Models To Evaluate

These are not final proposals. They are candidate shapes to compare.

### Model A - Keep Semantic Top-K, Tune It Harder

Shape:

```text
discover_capabilities(intent, domain, top_k=N)
-> bigger K
-> better embeddings
-> better descriptions
-> maybe reranker
```

Pros:

- Minimal change from current Fabric retrieval implementation.
- Good for marketplace browsing, developer search, and low-risk exploratory discovery.
- Fast and already aligned with current `RetrievalEngine` code.
- Easy to explain and test as information retrieval.

Cons:

- Still rank-first, not completeness-first.
- Can still omit Audi if Tesla ranks higher and Audi is outside the cutoff or not semantically recalled.
- Does not model resource identity, ownership, actor scope, freshness, or HIL completeness.
- Cannot be the authoritative path for side-effecting actions.

Current judgment:

```text
Useful supporting primitive.
Rejected as the main Back execution discovery model.
```

### Model B - Resource-First Situated Capability Resolution

Shape:

```text
user request
-> parse resource references and operation hints
-> enumerate actor-visible resources
-> bind capabilities to each candidate resource
-> evaluate policy/freshness
-> act, ask, block, or report incomplete projection
```

Pros:

- Directly addresses the two-car failure.
- HIL is based on actual candidate resources, not one ranked guess.
- Separates resource identity from tool identity.
- Works naturally with IFL connected-resource projections.
- Gives Back a truthful `CandidateUniverse` instead of a naked ranked list.

Cons:

- Requires a resource projection/index that may not exist yet.
- Requires adapters/manifests to expose resources and supported operations, not just capability descriptions.
- Needs clear freshness semantics for offline/stale adapters.
- Harder than search; it is a runtime resolution layer.
- Requires careful boundary between LLM interpretation and deterministic resource enumeration.

Current judgment:

```text
Strong candidate for side-effecting/resource-bound actions.
Needs more design around resource projection ownership and manifest requirements.
```

### Model C - Capability-First With Expansion And Completeness Checks

Shape:

```text
semantic search gets initial capabilities
-> expand sideways by resource kind/provider/category
-> discover all sibling capabilities/resources
-> then ask/act
```

Example:

```text
Tesla climate capability found
-> infer operation vehicle.climate.start
-> expand to all connected vehicle climate capabilities
-> include Audi before HIL
```

Pros:

- Easier migration from current Fabric retrieval.
- Semantic search can still help identify the operation family.
- May work when resource projection is incomplete but capability metadata is good.
- Can be introduced as a guard around current `discover_capabilities`.

Cons:

- Still depends on initial semantic recall finding something useful.
- Expansion rules can become another hidden taxonomy problem.
- If metadata is weak, expansion misses candidates.
- It is a patch around rank-first discovery, not a clean replacement.

Current judgment:

```text
Possible migration bridge.
Not sufficient as the final model unless expansion is backed by resource/affordance indexes.
```

### Model D - Policy/Constitution-First Role Binding

Shape:

```text
classify requested effect/risk
-> load policy/constitution modules
-> derive required capability roles
-> bind tools/resources for each role
```

Pros:

- Good for high-risk workflows where policy determines mandatory reads, approvals, and verification.
- Prevents late constitution surprise, such as discovering calendar only and later needing task/reminder checks.
- Aligns with "governed execution runtime" direction.

Cons:

- Can become too abstract if roles are invented before resource reality is known.
- Risks building a large policy vocabulary too early.
- Does not by itself solve "my car" unless it joins with resource resolution.
- May overcomplicate low-risk direct actions.

Current judgment:

```text
Needed for governance.
Should probably compose with resource-first binding, not replace it.
```

### Model E - Local World Projection First, Global Catalog Second

Shape:

```text
Execution discovery searches the actor's connected world projection first.
Global 100k tool/catalog search is used only for installation, missing-capability suggestions, docs, or fallback.
```

Pros:

- Avoids searching 100k tools for everyday execution.
- Matches edge-first K1: local projection should know connected household resources.
- Naturally handles "my car," "living room lights," "Riley's watch," and "school calendar."
- Global catalog does not pollute execution candidate sets.

Cons:

- Requires a durable local projection with sync/freshness semantics.
- Needs adapter onboarding to populate resources, aliases, ownership, and supported operations.
- Fails or degrades if projection is stale, incomplete, or not hydrated.

Current judgment:

```text
Likely non-negotiable principle.
Need design for projection ownership: Bridge, Fabric, K1 local store, or joined service.
```

### Model F - LLM Planner Chooses, Runtime Verifies Completeness

Shape:

```text
Back/Planner proposes likely resources and tools.
Deterministic resolver verifies no materially relevant candidate was omitted.
```

Pros:

- Uses LLM strengths for fuzzy language, intent, and contextual inference.
- Keeps deterministic safety around candidate completeness.
- May reduce rigid schemas in early versions.

Cons:

- Verification still needs the resource/affordance indexes.
- If the runtime cannot prove completeness, the LLM proposal is not enough.
- Must avoid letting LLM confidence replace scope proof.

Current judgment:

```text
Promising as an interaction pattern.
Not a replacement for deterministic candidate enumeration.
```

---

## Evaluation Criteria

Every candidate model should be scored against these criteria before implementation.

### Candidate completeness

Does it surface all materially relevant candidates in the actor's current world?

Test:

```text
Two connected cars, same operation, ambiguous "my car" reference.
Expected: both cars appear or resolver reports incomplete projection.
```

### Resource identity correctness

Does it distinguish concrete resources from tools and providers?

Bad:

```text
Tesla app = my car.
```

Good:

```text
vehicle.tesla.model_y is one candidate resource exposed through Tesla adapter.
```

### Authority and privacy correctness

Does it filter by actor authority and visibility before HIL/execution?

Example:

```text
Alex may control household Hue lights.
Alex may not read Riley's health data without consent/guardian policy.
```

### Freshness and offline behavior

Can it explain whether the world projection is fresh, stale, partial, or offline?

Example verdicts:

```text
complete_for_connected_vehicle_resources
partial_projection_adapter_offline
stale_projection_requires_confirmation
```

### Policy composition

Can it compose global household constitution, domain policy, adapter limitations, and tool guide without writing combinatorial workflows?

### Scale

Does it avoid searching the whole 100k-tool catalog for common local execution?

### Auditability

Can the runtime explain what it considered, what it excluded, and why?

### UX/HIL quality

Does it ask the user about the real ambiguity instead of a biased or incomplete guess?

Bad:

```text
Should I turn on the Tesla?
```

Good:

```text
Which car should I warm up: Tesla Model Y or Audi Q7?
```

### Migration cost

Can it coexist with current `discover_capabilities` and Fabric execution while we add the new resolver?

---

## Test Scenarios For Pros/Cons

Use these scenarios to break proposed designs before coding.

### Scenario 1 - Two Cars

```text
User: Turn on climate control of my car.
Reality: Tesla and Audi both connected and controllable.
Expected: needs_disambiguation with both cars.
```

Purpose:

```text
Tests resource candidate completeness and rank-before-completeness failure.
```

### Scenario 2 - One Car, Adapter Offline

```text
User: Warm up my car.
Reality: one Tesla connected, adapter status stale/offline.
Expected: incomplete/stale projection or HIL depending policy; no silent claim of execution.
```

Purpose:

```text
Tests freshness semantics.
```

### Scenario 3 - Living Room Lights Across Multiple Systems

```text
User: Turn off the living room lights.
Reality: Hue bulbs and Matter bulbs in same room.
Expected: all living-room light resources bound; either grouped execution or HIL if grouping is ambiguous.
```

Purpose:

```text
Tests cross-adapter resource grouping without global top-K search.
```

### Scenario 4 - Health Data Privacy

```text
User: How did Riley sleep last night?
Reality: Fitbit and Apple Health available; caller may or may not have caregiver permission.
Expected: authority/privacy gate before data disclosure; complete candidate health sources if allowed.
```

Purpose:

```text
Tests policy before capability use and sensitive-data projection.
```

### Scenario 5 - Scheduling With Hidden Conflict Sources

```text
User: Schedule Riley's dentist appointment Monday at 3.
Reality: calendar, tasks, school events, and caregiver constraints may all produce conflicts.
Expected: policy/constitution derives required conflict-source reads before write.
```

Purpose:

```text
Tests constitution/role binding beyond a single domain tool search.
```

### Scenario 6 - Missing Capability Suggestion

```text
User: Start the sprinklers.
Reality: no irrigation adapter connected; marketplace has Rachio adapter available.
Expected: execution resolver says no connected capability; optional global catalog suggestion is separate.
```

Purpose:

```text
Tests separation between local execution and global marketplace search.
```

---

## Initial Pros/Cons Leaning

Current lean, not decision:

```text
Execution path:
  local world projection first
  resource-first candidate enumeration
  capability binding second
  policy/guidance attached after binding but before execution
  ranking only after completeness

Supporting path:
  semantic/vector search remains for fuzzy parse help, documentation, marketplace, and low-risk exploration
```

This suggests the future system may have two separate products hiding under today's `discover_capabilities` name:

```text
1. Catalog Retrieval
   Search a large tool/prompt/adapter catalog.
   Optimized for recall/relevance.
   Top-K is acceptable.

2. Execution Resolution
   Resolve a user action against the actor's current world.
   Optimized for completeness, authority, and auditability.
   Top-K is not acceptable as the authority.
```

---

## Do Not Design Yet - Required Next Step

Before designing APIs/classes, we need to compare the candidate models against the test scenarios above and decide:

1. Which criteria are hard invariants?
2. Which scenarios are V0 gates?
3. Where the connected-resource projection lives.
4. What metadata IFL adapters must provide.
5. Whether Back sees multiple lower-level tools or one high-level resolver observation.
6. How current `discover_capabilities` survives as catalog retrieval without being used as execution authority.
