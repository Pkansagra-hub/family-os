# Generic Situated Execution Kernel

**Subtitle:** Back, Fabric, Bridge, IFL, Policy, PromptPack, And Capability Binding

**Date:** 2026-05-27
**Branch:** `feature/prompt-architecture-refactor`
**Status:** Living design whiteboard, promoted to future-facing design spec spine.
**Scope:** Generic situated-execution kernel contracts, with FamilyOS Concierge/K1/Fabric/Bridge/IFL as the first concrete instantiation. This includes the current Concierge Back actor prompt, Back ReAct loop, Back meta-tools, Fabric capability discovery, K1 native family tools, Bridge/IFL connector handoff, and the exact data contracts the Back LLM receives before invoking tools.
**Kernel framing:** This is not only a household assistant design. FamilyOS is the proof domain; the target is a reusable kernel that can be instantiated for any domain where an LLM actor must resolve resources, policy, tool contracts, and execution authority before taking action.

**Core question:** When Back tries to find and execute capabilities, what does it actually see, what code path supplies that information, and why can execution still feel hard even when the tool exists?

**Spec question:** What stable domain-neutral contracts should let an LLM execution actor, resolver, policy layer, capability registry, connector gateway, adapter runtime, guide-card system, and prompt-injection layer evolve independently while still producing reliable domain execution?

---

## Reading Guide

This document has two layers:

```text
Current-state proof
  Verified runtime facts, current discovery/invocation paths, issue register,
  probes, and observed failure modes.

Future-state spec
  Vocabulary, plane contracts, component contracts, runtime artifacts,
  resolver design, prompt injection timing, scenario gates, and acceptance criteria.
```

Do not read the current `discover_capabilities -> invoke_capability` path as the final design. It is the live baseline that must keep working during migration. The target design moves execution authority to situated resolution:

```text
Current baseline:
  Back discovers top-K capability records
  Back chooses exact capability name
  Back invokes by capability_name

Target design:
  FSM routes by tier before execution authority is granted
  Tier 1: Front converses or asks; no execution authority
  Tier 2: Back resolves one connector through staged constitution/name/schema disclosure
  Tier 3: Planner expands multi-resource plans and Orchestrator executes DAG-gated reads/writes
  Fabric/Bridge/IFL execute only through normalized component contracts
```

Document map:

```text
0. Three-Tier Contract-Bound Execution Model
  The target architecture and the dumb-LLM axiom. Later sections must conform to this tier ownership.

0A. Human Runtime Walkthrough
  Plain-language flow for Front ReAct, Back ReAct, Back promotion, Planner/Orchestrator execution, and Fabric across all tiers.

1. Current Mental Model
  The live Back/Fabric/native-tools path and why it is hard.

2. Verified Runtime Facts
  What probes and code paths prove today.

3. Issue Register / Fix Order
  Known failure modes and migration priorities.

4. Current Front-To-Back Handoff Audit
  What Front currently passes, what FSM/Back add, and what is missing for the target resolver design.

5. Proposed Plan
  Normative vocabulary and conceptual design direction.

6. Formal Intersection Surfaces
  Plane-level API contracts.

7. Component-Wise Contract Layer
  Runtime handshakes between Back, Fabric, Bridge, IFL, prompt injection, and the prove-before-promote milestone plan.

8. Plane Standards / Runtime Artifacts
  ReAct loop, policy cards, tool contracts, resolver, CandidateUniverse, PromptPack.

9. Scenario Gates / Evaluation Criteria / Open Decisions
  What must be true before implementation is accepted.

10. Sequential Component Atom Inventory
  Bottom-up decomposition of the execution path into smallest design atoms,
  first-pass implementation boundaries, and current-code proof slices.
```

The first nine sections define the kernel architecture. Section 10 decomposes that architecture into implementation atoms and first-pass proof slices.

Coherence rule for future edits:

```text
If a section says Back should choose from top-K, it is describing current baseline only.
If a section says Back should execute side effects, it applies only to Tier 2 unless it explicitly hands off to Planner/Orchestrator.
If a section assigns cross-resource conflict discovery to Back, it is stale and must be read as Tier 3 Planner/Orchestrator work.
If a section says a model should "know" what to check, the missing contract is a connector/capability constitution.
If a section mentions tools, capabilities, connectors, adapters, or resources, it must use the Standard Vocabulary section below.
If a section uses FamilyOS/K1/Concierge names, it must be clear whether the name is an implementation example or a kernel-level role.
```

Normative precedence:

```text
1. Three-Tier Contract-Bound Execution Model defines tier ownership and the dumb-LLM axiom.
2. Executive Thesis and Proposed Plan define the target architecture.
3. Contract A through Contract Q define the normative data model.
4. Component-Wise Contract Layer defines runtime boundary expectations.
5. Implementation Decomposition 01 decomposes implementation atoms but does not override tier ownership or Contracts A-Q.
6. Current Mental Model, Verified Runtime Facts, Current-State Probe Evidence, and Issue Register describe the live baseline only.
7. Design Committee Deliberation Log is historical rationale; later normative sections override it.
```

### Non-Goals

This document does not fully specify:

```text
provider-specific adapter protocols
final UI behavior
durable proof database schema
complete connector marketplace policy
all domain ontology definitions
all verifier implementations
all execution-budget SLOs
```

It specifies the kernel contracts and authority boundaries those pieces must obey.

---

## Executive Thesis

**Section mode:** target normative architecture.

Back execution should become a governed, resource-first, contract-bound loop:

```text
User / Front task
  -> Back RequestFrame
  -> Fabric resolve_situation
     local-world resources
     policy/guide cards
     capability bindings
     freshness/completeness proof
  -> Back bounded ReAct decision
  -> Fabric invocation
  -> Bridge connector dispatch
  -> IFL adapter execution
  -> deterministic verification where required
  -> submit_result
```

This is not mainly a better search problem. It is a candidate-universe, contract-binding, and prompt-injection problem.

The central migration is:

```text
from: text query -> top-K catalog result -> LLM chooses -> invoke
to:   task frame -> local world -> bound capabilities -> governed action
```

### Canonical Target Flow

> Note: the 16 steps below describe the **Tier 2** (single-connector, Back-direct) path. For family-impacting / cross-resource tasks the flow escalates to **Tier 3** (Planner + Orchestrator). See "Three-Tier Contract-Bound Execution Model" for tier ownership; steps 5–10 here are the Tier-2 instance of the staged connector→constitution→tools→schema disclosure.

```text
1. Front captures user-world intent.
2. FSM canonicalizes task and state correlation.
3. Back receives BackTaskEnvelope.
4. Back builds RequestFrame.
5. Back calls resolve_situation.
6. Resolver builds CandidateUniverse from local-world projection.
7. Policy/guide authority produces PolicyBundle and GuideCards.
8. Capability registry produces BindingBundle.
9. Resolver returns ResolutionEnvelope + PromptPack.
10. Back acts only through allowed_next_actions.
11. Fabric invocation executes through native provider or Bridge/IFL.
12. InvocationObservation is normalized.
13. VerificationObservation is produced when required.
14. Back submits completed/blocked/failed/cannot_execute with evidence.
15. FSM updates task/session state.
16. Front presents user-facing response.
```

### Generic Kernel Thesis

The design committee position is that the reusable product here is not a calendar agent, household agent, or FamilyOS-specific Back actor. The reusable product is a domain-neutral execution kernel:

```text
Intent actor
  -> state authority
  -> execution actor
  -> situated resolver
  -> policy and guide authority
  -> capability registry
  -> connector gateway
  -> adapter runtime
  -> verifier
  -> proof harness
```

Current repository names map to those kernel roles:

```text
Front             -> intent actor
FSM               -> state authority and task router
Back              -> LLM execution actor
Fabric resolver   -> situated resolution authority
Policy/guide layer-> governance authority
Fabric registry   -> capability contract authority
Bridge            -> connector gateway
IFL adapter       -> adapter runtime
Proof harness     -> promotion and evidence authority
```

Domain instances provide the parts that vary:

```text
domain ontology
resource kinds
operation taxonomy
policy cards
guide cards
connector manifests
adapter implementations
verifier strategies
HIL question language
scenario gates
```

Kernel contracts provide the parts that must not vary across domains:

```text
request framing before resolution
resource completeness before ranking
binding before side effect
policy gate before mutation or disclosure
prompt cards instead of raw catalogs
normalized observation before retry
verification before completed submit when required
proof record before promotion
```

### Decision Summary

The committee passes converged on these non-negotiable kernel invariants:

```text
1. FamilyOS is the proof domain, not the kernel boundary.
2. Memory, ranking, salience, and planner output may seed resolution but cannot authorize execution.
3. Protected reads are governed actions.
4. Every side effect requires resource proof, policy gate, binding, invocation observation, and verification when required.
5. PromptPack is the model context contract, not just prompt text.
6. Connector catalog visibility is not execution authority.
7. Safety bands must be split into explicit axes before provider dispatch.
8. Budget exhaustion must produce typed partial/HIL/retry/block/cannot_execute outcomes.
```

---

## Three-Tier Contract-Bound Execution Model

**Section mode:** target normative architecture. This section is authoritative and supersedes any earlier framing in this document that treats Back as the sole governed executor. Where prose elsewhere assigns multi-resource conflict coordination to Back's ReAct loop, read it through the tier ownership defined here.

### The Dumb-LLM Principle (design axiom)

The single hardest constraint, and the one this whole document exists to satisfy:

```text
An LLM cannot plan from information it does not have.
It cannot infer a check it was never told to perform.
```

When a user says `add Riley's picnic Saturday, dad is taking her`, no model — Front, Back, or Planner — can know on its own that this utterance implies:

```text
- check Jordan's schedule (dad is committed -> driver conflict)
- check Nana Liz's schedule (secondary guardian impact)
- check the requesting user's schedule (own commitments)
- check Riley's chores at that time (chore conflict)
- check Riley's tasks/homework due at that time (commitment conflict)
- only then create the event, gated behind those reads
```

The model will not produce these steps unless something it was handed already declares them. Therefore the procedural knowledge — *what to check before a family-impacting mutation, and whose resources are in scope* — must be **carried in contracts and injected**, never left for the LLM to invent. This is the difference between "a better prompt" and "a contract-bound system." We are not making the LLM smarter; we are making the context it receives carry the plan.

Two rejected ways to carry this knowledge, and the adopted one:

```text
Rejected A: hand-write a giant dynamic Back prompt per scenario.
  Fails: with tools and apps constantly added, the dynamic prompt set
  becomes unmaintainable. Knowledge rots and drifts from the tools.

Rejected B: dump every tool's full schema into discovery and hope the
  LLM stitches the right multi-resource plan from raw records.
  Fails: token blow-up, brittle, and still no source for "check chores".

Adopted: the knowledge lives ON the connector/capability contract as a
  constitution (preconditions + companion-resource requirements), is
  disclosed progressively, and is expanded into an explicit plan by the
  tier that owns planning. Knowledge ships with the tool, not the prompt.
```

### The Three Tiers (already built — we are contract-binding them)

The repository already routes by complexity. This is not new machinery; the whiteboard's job is to make each tier **explicitly contract-bound**. Source diagrams:

```text
architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd  (complexity router, DISPATCHING)
k1/concierge/concierge_unified.mmd                               (Front/Back two minds, tiers)
k1/orchestrator/orchestrator.mmd                                 (deterministic DAG, reads-before-writes)
k1/planner/planner_v2.mmd                                        (SKETCH->EXPAND->VALIDATE->COMMIT)
```

Routing (verbatim from DISPATCHING): `Route: LOW -> Back, MED -> Orchestrator, HIGH -> Planner`.

```text
TIER 1 — Conversation (user <-> Front)
  Actor:   Front LLM (voice). No tools that mutate the world.
  Owns:    intent capture, grounding questions, presentation.
  Contract surface: none executable. Front never resolves capabilities.
  Maps to: Concierge FRONT_ACTOR.

TIER 2 — Single-connector governed execution (Front + Back)
  Actor:   Back LLM (worker), LOW/simple-MEDIUM tasks.
  Input to Back is NOT a flat catalog. Back receives, per task class, a
  small set of CONNECTOR records (e.g. calendar) — each carrying:
    - the connector constitution (preconditions: "check duplication,
      check conflicts before create")
    - the connector's tool NAMES (~10), NO full schemas yet
  Back plans against connector constitutions, names the exact tools it
  will use, and ONLY THEN are the schemas for those selected tools fed in.
  Owns:    tasks resolvable within one connector's world with at most a
           couple of reads then a gated write. Direct invoke_capability.
  Maps to: Concierge BACK_ACTOR ReAct loop + Fabric resolve.

TIER 3 — Multi-resource coordinated mutation (Planner + Orchestrator)
  Trigger: family-impacting / cross-resource / conflict-bearing tasks
           (the Riley picnic case). Back/Front escalate to HIGH tier.
  Planner: expands the utterance into an explicit multi-step plan with
           dependencies (SKETCH -> EXPAND -> VALIDATE -> COMMIT). EXPAND
           already enriches each step from the CapabilityContract:
           has_side_effects, compensation, required_context,
           safety_band_min, timeout_ms.
  Orchestrator: executes the plan deterministically. Dependency edges +
           PARAM_RESOLVER ($step.result refs) force reads-before-writes;
           CONDITIONAL_EVAL skips/branches on conflict; SAGA compensates.
  Owns:    the impact-set fan-out, conflict detection across calendars +
           chores + tasks, and the gated write(s).
  Maps to: Planner planner_v2.mmd + Orchestrator orchestrator.mmd.
```

The critical correction to earlier sections: the dentist/picnic conflict scenario is **Tier 3**, not a Back ReAct responsibility. Back does not iteratively discover and sequence five reads then a write. Back recognizes the task class is family-impacting and escalates; the Planner builds the plan skeleton and the Orchestrator gates it. "Resolution Must Provision A Tool Set, Not Only One Tool" is correct — but the provisioning and sequencing happen in Tier 3's EXPAND/DAG, not inside one Back loop.

### Progressive Disclosure (connector -> constitution -> tools -> schema)

Resolution is **staged**, not a single dump. This is what keeps the dumb LLM grounded without token blow-up and without brittle top-K guessing:

```text
Phase 0 (deterministic, no LLM): situated projection.
  From the household's local world, select the few CONNECTORS plausibly
  in scope for this task class (e.g. calendar, tasks, chores, family
  members). Cost O(local), not O(100k catalog).

Phase 1 (LLM plan hop): connector + constitution disclosure.
  Hand the model connector summaries + their constitutions + tool NAMES.
  The constitution is where "before create: check duplication, check
  conflicts, check participants' chores/tasks" lives. The model now has
  the information required to plan — because we gave it.

Phase 2 (bind): the model commits exact tool names it will use.

Phase 3 (schema disclosure): feed full schemas ONLY for the bound tools.

Phase 4 (execute / clarify / HIL): run the gated plan; verify; submit.
```

Tier 2 runs this within one connector. Tier 3 runs the same staging across multiple connectors, where Phase 1's "plan" becomes the Planner's ExpandedPlan and Phase 4 becomes the Orchestrator DAG.

### The Connector/Capability Constitution Is the Knowledge Carrier

This is the contract that makes the Dumb-LLM Principle satisfiable. Per connector (and refinable per capability), declared once and versioned with the connector — not per app/tool permutation:

```text
connector: calendar
  constitution:
    preconditions:
      - before create/update: list_events to detect duplicates
      - before create/update: detect time conflicts in scope
    companion_resources (impact set, declared as ROLE TYPES):
      - participants:        whose calendars are implicated
      - conflict_subjects:   whose chores/tasks must be read
      - guardians:           secondary-impact members
    verify:
      - after write: get_event read-back
    tools (names only at Phase 1):
      tool.read.calendar.list_events
      tool.read.calendar.get_event
      tool.execute.calendar.create_event
      ...
```

Ownership of the impact set is a **hybrid**, and the kernel stays domain-agnostic:

```text
domain ontology declares the ROLE TYPES   (participants, conflict_subjects, guardians)
grounding / LLM fills WHO                  (Riley -> Jordan, Nana Liz, requesting user)
the resolver PROVES the concrete set       (resolve member ids + their resource handles)
```

So "check Riley's chores and everyone's schedules" is not a model guess and not a hand-written prompt — it is the calendar connector's declared `companion_resources`, instantiated by grounding, proven by the resolver, expanded by the Planner, and gated by the Orchestrator.

### Conflict Detection Needs a Cross-Resource Read Model

The one genuinely missing capability behind Tier 3: answering "is Riley free Saturday 2pm" requires unioning **calendar events + chores + tasks/homework**, queryable by `(person, time-window)` across adapters — not three siloed per-app reads the LLM must remember to issue. This query shape is the local-world-projection capability Tier 3 depends on; without it, the dumb LLM is blind and silently degrades to single-tool behavior.

### Top-K vs Situated Projection (reconciliation)

The Executive Thesis rejects "top-K catalog -> LLM chooses." That rejection applies to **execution-time resolution**, where we use the situated local-world projection + connector constitutions. Semantic top-K (the Planner's `discover_capabilities`) remains legitimate only for **cold/global discovery** (install, first-contact, "is there any tool that could do X"). Execution never searches 100k tools; it resolves the household's already-projected connectors.

### Problems In The Earlier Draft This Section Resolves

```text
- Single-actor collapse: Back was made the universal executor; tiers restore correct ownership.
- Mis-assigned conflict scenario: the picnic case is Tier 3 (Planner+Orchestrator), not Back.
- "Where does the dumb LLM learn what to check": connector constitution carries it.
- Flat one-shot provisioning: replaced by staged connector->constitution->tools->schema disclosure.
- Top-K contradiction: scoped to cold discovery vs situated execution.
- Unbound diagrams: each tier now maps to its existing .mmd and the fields already present.
- Impact-set ownership: hybrid ontology(role types) + grounding(who) + resolver(proof).
```

---

## Human Runtime Walkthrough - ReAct Loops, Promotion, Planner, Orchestrator, Fabric

**Section mode:** target normative architecture in plain language.

This section says what actually happens at runtime. It deliberately uses normal language because the important part is ownership, not clever terminology.

Core rule:

```text
The model never gets blamed for not knowing a rule the system did not give it.
Every loop either receives the information it needs, asks for it, or promotes/blocks.
```

### 1. Front ReAct Loop - From User Turn To Task Dispatch

Front is the voice. It talks to the user. It does not execute real-world side effects and does not resolve Fabric capabilities.

What happens:

```text
1. User says something.
2. Front receives conversation context, safe state summary, current grounding hints, and its Front tool surface.
3. Front decides whether this is conversation or work.
4. If it is conversation, Front answers directly and the turn ends.
5. If it is work, Front calls dispatch_task with user-world facts only:
     user goal
     extracted params
     people/time/place hints
     reference_context
     dependency hints
     rough tier/plan hint if obvious
6. Front does not say the work is complete.
7. Front's tool result is collected after the loop.
8. Front/FSM emits a TaskDispatch onto the event bus.
```

What Front must not do:

```text
Front must not choose a Fabric capability.
Front must not pass binding ids.
Front must not stuff connector manifests or schemas into reference_context.
Front must not claim a side effect happened.
```

The handoff from Front is intentionally human-world shaped:

```text
"schedule Riley dentist Monday 3pm"
not
"invoke tool.execute.calendar.create_event with params ..."
```

### 2. FSM Routing - The First Authority Split

The FSM is the state and routing authority. It turns Front's dispatch into a canonical task and decides where the task should go first.

What happens:

```text
1. FSM parses the TaskDispatch.
2. FSM preserves task id, trace id, actor/session scope, grounding refs, safety seed, and dependencies.
3. FSM computes or preserves the tier.
4. FSM writes task state. Front and Back do not write SessionState directly.
5. FSM routes:
     Tier 1: stay with Front / ask / answer
     Tier 2: send BackTaskEnvelope to Back
     Tier 3: send TaskEnvelope to Orchestrator/Planner path
```

If the task is already obviously family-impacting or cross-resource, Back should not receive it just to rediscover that fact. The preferred route is direct Tier 3.

### 3. Back ReAct Loop - When Front Dispatches To Back

Back is the Tier 2 worker. It executes bounded single-connector work. It has no personality, does not speak to the user, and terminates only with `submit_result` or a typed non-completion outcome.

What Back sees at loop start:

```text
Back sees:
  canonical task JSON
  actor/session/task ids
  one SessionState snapshot
  grounding refs
  safety context seed
  Back meta-tools

Back does not see:
  all app schemas
  raw connector manifests
  credentials
  global 100k tool catalog
  authority to write SessionState
```

Back loop in human language:

```text
ReAct hop 1 - orient
  Back reads the task and builds a RequestFrame:
    "What is the user trying to do? Who/what/time/place are referenced?
     Is this simple enough for my tier?"

Tool phase 1 - resolve
  Back calls resolve_situation(RequestFrame).
  Fabric/Plane 4 returns a ResolutionEnvelope:
    local-world candidates
    connector constitution cards
    tool names, not full schemas yet
    policy/freshness/completeness verdicts
    allowed_next_actions

ReAct hop 2 - decide tier and tool intent
  Back reads the allowed actions.
  If the resolver says "Tier 2 executable", Back chooses the exact tool names/bindings it needs.
  If the resolver says "Tier 3 required", Back promotes instead of improvising.

Tool phase 2 - bind selected tools
  Fabric binds selected names to binding ids and returns schemas only for those bindings.

ReAct hop 3 - read/check/ask/write
  Back follows the connector constitution:
    run required reads
    check duplicates/conflicts inside the connector scope
    ask HIL if required
    invoke write only if allowed

Tool phase 3 - execute and verify
  Fabric executes reads/writes through native provider or Bridge/IFL.
  Fabric returns normalized observations and verification results.

ReAct hop 4 - finish
  Back calls submit_result with completed, partial, blocked, failed, or cannot_execute.
  Back includes evidence. It does not narrate to the user.
```

The important part is that Back's loop is not a free-form hunt. Each model hop is bounded by what the resolver said is legal.

Back is allowed to do this:

```text
"The calendar connector constitution says I must list events before create.
I have the list_events binding and create_event binding.
I will list first, then create only if no duplicate/conflict appears."
```

Back is not allowed to do this:

```text
"The user said calendar, so I found a create_event-looking tool and called it."
```

### 4. How Back Promotes To Planner/Orchestrator

Back does not promote because it has a vague feeling that a task is hard. Back promotes because the task no longer fits the Tier 2 contract.

Promotion triggers:

```text
Resolver says target_tier = tier3.
Connector constitution declares companion_resource roles.
The task needs a cross-resource impact set.
The task needs a PlanGraph / dependency graph.
The write depends on several prerequisite reads across connectors.
The task needs compensation, conditional branches, or multi-step HIL.
The local projection is incomplete and policy says Back cannot continue directly.
```

Concrete example:

```text
User: Add Riley's picnic Saturday, dad is taking her.

Back/Fabric resolves:
  calendar write requested
  participant: Riley
  caregiver/driver mentioned: dad/Jordan
  connector constitution requires companion_resource checks
  companion resources include calendars, chores, homework/tasks, caregiver schedules
  required work crosses the single-connector Tier 2 boundary

Verdict:
  allowed_next_action = promote_to_tier3
```

Back's promotion action is a structured handoff, not a direct call into Planner:

```text
BackPromotionOutcome
  task_id
  trace_id
  request_frame_ref
  resolution_id
  target_tier: tier3
  escalation_reason
  candidate_universe_ref
  connector_constitution_refs[]
  companion_resource_roles[]
  known_missing_fields[]
  unresolved_questions[]
```

Back submits that outcome to the FSM. Back does not write SessionState and does not call Planner as a tool.

Then:

```text
1. FSM records that the Back path promoted the task.
2. FSM emits/updates a Tier 3 TaskEnvelope for Orchestrator.
3. Orchestrator receives the task.
4. If the task needs planning, Orchestrator sends a PlanRequest to Planner.
```

The human-language rule:

```text
Back can say, "This is not my tier, and here is the evidence."
Back cannot say, "I will personally coordinate every calendar, chore, homework, and caregiver check."
```

### 5. Once Promoted - Planner FSM Creates The Plan

Planner is the Tier 3 planning mind. It may use LLM calls, but it does not execute capabilities and does not write SessionState.

Planner receives a PlanRequest containing the user goal plus the evidence gathered so far:

```text
request frame
candidate universe refs
connector constitution refs
companion_resource roles
policy constraints
known missing fields
trace/task/session correlation
```

Planner FSM in human language:

```text
IDLE
  No active plan.

SKETCHING
  Planner drafts the rough shape of the work:
    read Riley's calendar
    read Riley's chores/homework/tasks
    read Jordan's calendar
    read requesting user's calendar
    detect conflicts
    ask if conflict/missing field
    create event only after checks pass

EXPANDING
  Planner turns rough steps into concrete StepFrames:
    exact operation hints
    resource references
    Fabric capability candidates or binding refs
    required artifacts
    dependency edges
    verifier requirements

VALIDATING
  Planner validates the plan:
    dependencies form a DAG
    each step has a valid capability path or a known missing capability
    writes depend on required reads
    HIL is inserted where policy requires it
    no step asks Orchestrator to guess

COMMITTING
  Planner performs deterministic commit with no LLM.
  The result is a CommittedPlan.

COMPLETED / FAILED / CANCELLED
  Planner emits plan.ready, plan.failed, or plan.cancelled.
```

Planner output is not authority to execute by itself. It is a committed plan that Orchestrator can walk.

### 6. Orchestrator Executes The Promoted Plan

Orchestrator is the Tier 3 deterministic executor. It has no LLM and no personality. It does not invent steps. It walks the committed DAG.

What Orchestrator does:

```text
1. Receives CommittedPlan.
2. Builds execution waves from dependency edges.
3. Executes steps whose dependencies are satisfied.
4. Runs independent read steps in parallel when policy allows.
5. Waits for read results before dependent write steps.
6. Resolves params like $read_step.result.event_id only after that step completed.
7. Evaluates conditional edges at wave boundaries.
8. Sends every executable step to Fabric.
9. Handles retry, HIL, compensation, cancellation, or micro-replan if needed.
10. Aggregates results and sends the outcome back to Concierge/FSM.
```

For the Riley picnic example:

```text
Wave 1 - prerequisite reads
  read Riley calendar
  read Riley chores
  read Riley homework/tasks
  read Jordan calendar
  read requesting user's calendar

Wave 2 - conflict evaluation
  combine read observations
  decide conflict / no conflict / missing data

Wave 3A - if conflict
  ask HIL or propose alternatives

Wave 3B - if no conflict
  create calendar event

Wave 4 - verify
  read back created event
  collect audit evidence

Final
  return AggregatedResult to Concierge/FSM
```

The key point:

```text
The LLM may help create the plan.
The Orchestrator enforces the order.
Fabric executes the capabilities.
FSM owns durable task state.
Front tells the user what happened.
```

### 7. Fabric's Role Across All Three Tiers

Fabric is the capability and execution authority layer. It is not Front, not Back, not Planner, and not Orchestrator.

Fabric owns these jobs:

```text
Capability registry
  Stores admitted capabilities from native family tools, Bridge/IFL connectors,
  workflows, and agents.

Contract authority
  Knows capability names, schemas, effects, safety requirements, verifier refs,
  policy hooks, and connector constitution refs.

Situated resolution / binding support
  Helps build CandidateUniverse, BindingBundle, PromptPack, and allowed_next_actions.

Invocation runtime
  Validates params, safety, policy, freshness, idempotency, and binding validity.

Provider dispatch
  Sends execution to native K1 family tools or Bridge/IFL connector gateway.

Observation normalization
  Converts provider-specific results/errors into InvocationObservation,
  ErrorObservation, RecoveryDirective, and VerificationObservation.
```

Fabric in Tier 1:

```text
Tier 1 is conversation. Fabric does not execute side effects.
Front may use safe conversation/read context that policy already allows, but it does not resolve or invoke capabilities.
If the user asks for work, Front dispatches. Execution authority starts after routing.
```

Fabric in Tier 2:

```text
Back calls Fabric-facing meta-tools.
Fabric resolves the local situation.
Fabric returns connector constitution cards, tool names, binding ids, selected schemas, and allowed actions.
Fabric executes the selected read/write/verifier capabilities.
Fabric returns normalized observations to Back.
Back submits the result.
```

Fabric in Tier 3:

```text
Planner uses Fabric contracts and binding information to produce valid plan steps.
Planner does not execute Fabric capabilities.
Orchestrator calls Fabric for every DAG step.
Fabric executes each step through native providers or Bridge/IFL.
Fabric returns results to Orchestrator, not to a free-form LLM loop.
Orchestrator uses those results to advance waves, branch, compensate, verify, or aggregate.
```

Fabric must never become a hiding place for model guesses:

```text
Fabric may bind a proved resource to a proved capability.
Fabric may reject stale, unsafe, unbound, or schema-invalid requests.
Fabric may normalize errors and tell the actor the next legal move.
Fabric must not silently pick a missing person, connector, resource, or policy answer for the model.
```

### 8. Short End-To-End Stories

Tier 1 story:

```text
User: What did we decide about Riley's birthday theme?
Front reads safe conversation context and answers.
No Back. No Planner. No Orchestrator. No Fabric side effect.
```

Tier 2 story:

```text
User: Add dentist appointment for Riley Monday at 3.
Front dispatches task.
FSM routes LOW/Tier 2.
Back builds RequestFrame and calls resolve_situation.
Fabric returns calendar connector constitution and tool names.
Back selects list_events/create_event/get_event.
Fabric returns schemas for those selected tools.
Back lists events, sees no duplicate/conflict, creates event, verifies read-back.
Back submit_result.
FSM records outcome.
Front tells user it is done.
```

Tier 3 story:

```text
User: Add Riley's picnic Saturday, dad is taking her.
Front dispatches task.
FSM routes HIGH/Tier 3, or Back promotes after resolver proves companion resources.
Planner sketches and expands reads for calendars, chores, homework/tasks, and caregiver schedules.
Planner validates and commits a DAG.
Orchestrator executes read waves through Fabric.
If conflicts exist, Orchestrator asks HIL or triggers a planner micro-replan.
If no conflicts exist, Orchestrator executes the calendar write through Fabric.
Fabric verifies.
Orchestrator returns AggregatedResult.
FSM records outcome.
Front tells user what happened.
```

---

## Current Mental Model

**Section mode:** current proof.

This section describes the live baseline, not the target authority model.

Back does not receive every app tool as a direct LLM function declaration. Back receives a small set of meta-tools. The real app/native tools live behind Fabric capability contracts. In the current baseline, Back must discover candidate capability names, copy an exact registry-owned `capability_name`, construct schema-valid params, invoke that capability, observe the result, and finally call `submit_result`.

This creates a two-layer tool model:

1. **Callable Back meta-tools:** what the LLM provider receives as function schemas.
2. **Discovered capabilities:** legacy records returned by `discover_capabilities`; these are not directly callable functions until Back passes their exact `name` into `invoke_capability` or `batch_invoke_capabilities`.

The spine exists end to end. The hard part is the contract discipline in the middle: discovery returns a mixed catalog, schemas are exact, param transformation is not always automatic, safety-band semantics differ across layers, and the loop relies on soft nudges for termination.

Target reading: this current path remains a compatibility spine. Execution authority moves to the tier router, connector/capability constitutions, situated resolution, binding ids, Planner/Orchestrator DAGs for Tier 3, and PromptPack staging. Any section below that treats the baseline `discover_capabilities` record as execution authority is describing a migration risk, not the final design.

---

## Foundation - Tiered Tool Calling Scenario

**Section mode:** current proof plus target orientation.

This design cannot be solved by optimizing one piece at a time. Contract-bound execution has four planes that must be designed as one system under the three-tier router:

```text
Plane 1: Execution-actor loop design (Back for Tier 2; Planner+Orchestrator boundary for Tier 3)
Plane 2: Governance, policy, and guide-card authority
Plane 3: Standard tool contracts and tool design
Plane 4: Situated resolution and provisioning
```

If any one plane is designed in isolation, the execution tier becomes unstable:

```text
good loop + bad projection        -> actor cannot see the right local world
good projection + bad contracts   -> actor sees resources but cannot bind safely
good contracts + no constitution  -> actor lacks the checks it must perform
good constitution + bad routing   -> Back is asked to do Planner/Orchestrator work
```

### Basic Scenario

Example proof domain:

```text
FamilyOS scheduling.
```

Kernel class:

```text
time-bound system-of-record mutation with prerequisite reads, missing required field,
HIL, binding, invocation, and verification.
```

User asks:

```text
Add dentist appointment for Riley on Monday.
```

Back should not think in one step:

```text
find calendar tool -> create event -> submit_result
```

The tier router must classify the task before deciding which execution spine applies:

```text
Tier 2 if:
  single connector, bounded prerequisite reads, no cross-resource impact set,
  no multi-party conflict analysis, no dependency graph beyond simple read->write.

Tier 3 if:
  family-impacting scheduling, participant/caregiver impact, chores/homework/task
  conflicts, multiple connectors, dependent writes, compensation, or any plan DAG.
```

Tier 2 Back spine:

```text
1. Understand task class
  simple scheduling / single connector / system-of-record mutation

2. Resolve grounding
  who is Riley, which Monday, timezone, household context

3. Receive connector constitution and tool names
  not full schemas; the constitution declares duplicate/conflict preconditions

4. Commit exact tool names
  selected read/write/verifier names become binding candidates

5. Receive schemas for selected tools only

6. Read/check before mutation
  duplicate and conflict checks declared by the connector constitution

7. Ask HIL when required
  missing required fields, connector-local conflict, risk, policy uncertainty

8. Execute mutation
  exact binding/capability name, schema-valid params, governed order

9. Verify mutation
  read back created/updated object where contract requires it

10. Submit result
  structured result/artifacts/semantic context, no user-facing chatter
```

Tier 3 Planner/Orchestrator spine:

```text
1. Expand impact set from connector constitution and domain ontology
  participants, guardians, conflict_subjects, companion resources

2. Planner produces PlanGraph / ExpandedPlan
  read Riley calendar, read Riley chores/homework/tasks, read caregiver schedules,
  detect conflicts, ask HIL if needed, write only after reads pass

3. Orchestrator executes deterministic DAG waves
  prerequisite reads before writes, conditional branches on conflict, compensation if needed

4. Verification and result aggregation
  read-after-write and evidence collection before Front presentation
```

The dumb-LLM rule is enforced here: the model sees the check list because the connector constitution and domain ontology supplied it. If the system did not disclose chores/homework/caregiver checks, the model cannot be blamed for missing them.

### Constitution Is Not Per-Tool Permutation

The system must not create one constitution for every combination of apps and tools. With 5 apps and 5 tools, combinations already explode; with 100k tools it is impossible.

The scalable shape is layered composition:

```text
global execution constitution
  -> task-class constitution
       -> domain constitution
            -> connector constitution
                 -> capability/tool contract
                      -> provider/runtime policy
```

Example:

```text
global Back constitution:
  Grounding first. Reads may parallelize when policy allows and protected-read gating is satisfied. Writes and dependent side effects remain sequenced. Submit structured results.

task-class constitution: scheduling mutation
  Resolve time/person/place. Read availability. Detect conflicts. HIL if missing/conflict.

domain constitution: calendar
  Calendar events are time-bound commitments. Writes require duplicate/conflict checks and read-back verification.

connector constitution: com.google.calendar / native calendar
  Phase 1 exposes connector summary, preconditions, companion_resource roles, and tool names.
  It does not expose full schemas until Back/Planner commits selected tools.

tool contract: tool.execute.calendar.create_event
  Required: title, start, end. Optional: attendees, location, notes, visibility.
```

So `calendar_activity_v1` is not a selectable capability. It is domain/task guidance that can be attached to executable calendar capabilities or injected after the resolver has identified a scheduling/calendar task class and the relevant connector constitution.

### Resolution Must Provision A Tool Set, Not Only One Tool

For governed execution, situated resolution cannot only answer:

```text
what tool creates a calendar event?
```

It must answer:

```text
what executable tool set and guidance are needed for this task class?
```

For scheduling, provisioning may include:

```text
primary write:
  tool.execute.calendar.create_event

required reads:
  tool.read.calendar.list_events

  tool.read.calendar.get_event

related checks:
  tool.read.tasks.list_tasks

  tool.read.reminders.list_reminders

runtime grounding:
  temporal projection
  identity/person projection
  spatial/place projection when relevant
```

This avoids duplicating discovery later when the constitution says “read tasks first.” The provisioning layer must return the execution bundle in the correct tier shape:

```text
Tier 2:
  one connector constitution + selected tool names + schemas only after bind

Tier 3:
  joined connector constitutions + companion_resource roles + PlanGraph/DAG dependencies
```

### Process Shape To Design Toward

```text
Front/FSM receives task
  -> route tier
    Tier 1: Front answers / asks, no execution authority
    Tier 2: Back gets staged connector constitution and executes one-connector path
    Tier 3: Planner builds PlanGraph and Orchestrator executes dependency-gated DAG
  -> situated resolver provisions the tier-appropriate bundle
    connector constitutions
    executable candidates / bindings
    required read/check roles
    domain/task guidance
    contract schemas only after selection/binding
    policy/HIL rules
  -> execution actor runs only against allowed_next_actions
    read/check
    analyze
    ask HIL or mutate
    verify
    submit_result / aggregate result
```

Resolution adopted by the Proposed Plan below:

```text
Current path remains discover_capabilities for compatibility and catalog retrieval.
Execution authority moves to resolve_situation(task_frame), which returns
CandidateUniverse + PromptPack + allowed next actions.
```

This keeps the live tool spine intact while giving the future runtime a deterministic execution boundary.

---

## Verified Runtime Facts

**Section mode:** current proof.

### BTC-A1 - Back prompt assembly is task-scoped and uses live SessionState

`back_handler` reads a one-shot SessionState snapshot, computes the effective safety band, selects execution profiles, builds execution grounding, then calls `build_back_prompt(...)`. See [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L980) and [k1/concierge/prompt/back_prompt.py](../../k1/concierge/prompt/back_prompt.py#L411).

The prompt receives:

- Full task JSON.
- Beliefs summary.
- Active task summary.
- Completed/artifact summary.
- Legacy scalar `safety_band` mapped later into `SafetyContext` axes.
- Persona preferences.
- Max tool calls.
- Available-tools note.
- Execution profile block.
- Execution grounding block.

Status: **The prompt is not a generic static prompt. It is the live Back system prompt plus task and state context.**

### BTC-A2 - Back LLM gets meta-tools, not the entire native app surface

Back tool schemas are defined in [k1/concierge/tools/schemas_back.py](../../k1/concierge/tools/schemas_back.py#L286). LOW/simple tier exposes:

- `recall_memory`
- `discover_capabilities`
- `invoke_capability`
- `batch_invoke_capabilities`
- `submit_result`

MEDIUM/HIGH/plan tier adds:

- `spawn_via_fabric`
- `execute_workflow`

The live probe confirmed LOW/simple model-visible schemas:

```text
recall_memory, discover_capabilities, invoke_capability,
batch_invoke_capabilities, submit_result
```

Status: **Back must use meta-tools to access app tools. Calendar/tasks/reminders/etc. are not first-class LLM function declarations in the Back request.**

### BTC-A3 - Discovery returns rich capability records, not only names

`execute_discover_capabilities` builds a `ToolResult` with capability dictionaries in [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1362). Each record can include:

- `name`
- `description`
- `domain`
- `domains`
- `score`
- `prompt_template`
- `activity_profile`
- `tool_instructions`
- `limitations`
- `schema`

The `schema` is generated by `_capability_prompt_schema(...)` in [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L253) and includes:

- `required_inputs`
- `optional_inputs`
- `capabilities`
- `output`
- `safety_band_min`

Status: **Back receives enough information to choose and invoke tools, but the information is mixed and requires careful reasoning.**

### BTC-A4 - Native family tools register through Fabric contracts

K1 native family tools live under [k1/tools/family](../../k1/tools/family). The core adapters are:

- `calendar`
- `tasks`
- `reminders`
- `chores`
- `shopping`
- `family_settings`

At boot, `KernelService._bootstrap_family_tools()` resolves service classes, calls `bootstrap_family_tools(...)`, registers each action as a `CapabilityContract`, then registers `NativeToolProvider` under provider type `LOCAL` / provider id `k1_native_tools`. See [k1/tools/family/bootstrap.py](../../k1/tools/family/bootstrap.py#L115) and [k1/fabric/manifest_translator.py](../../k1/fabric/manifest_translator.py#L129).

Capability naming convention:

- Reads: `tool.read.<adapter_id>.<action_name>`
- Writes/deletes/compute: `tool.execute.<adapter_id>.<action_name>`

Status: **Family tools are correctly surfaced as Fabric capabilities when `enable_family_tools=True` and service paths are configured.**

### BTC-A5 - Invocation path is live end to end

The verified live path is:

```text
Back LLM tool call
  -> ToolDispatcher.dispatch(...)
  -> execute_invoke_capability(...)
  -> FabricDispatchAdapter.dispatch_direct(...)
  -> CapabilityFabric.execute(...)
  -> NativeToolProvider._execute(...)
  -> BaseToolService.dispatch(...)
  -> adapter method, SQLite write/read, SSE/audit events
```

`NativeToolProvider` parses `tool.read.*` / `tool.execute.*` names and dispatches to the matching family adapter service in [k1/fabric/providers/native_tool_provider.py](../../k1/fabric/providers/native_tool_provider.py#L192).

Live probe result with `tool.execute.calendar.create_event`, GREEN safety band, and schema-valid params:

```json
{
  "status": "ok",
  "error": null,
  "data": {
    "result": {
      "success": true,
      "event_id": "a638149fa1bc4a1fb1790d72cfaa25f6",
      "version": 1
    },
    "duration_ms": 128,
    "status": "success"
  }
}
```

Status: **The Back -> Fabric -> NativeToolProvider -> calendar service path works.**

---

## End-To-End Discovery Flow

**Section mode:** current proof.

This section intentionally documents the legacy discovery path. In the target design, this path is not execution authority for side effects or protected reads. The target authority path is `resolve_situation` with staged connector constitution disclosure, binding, PromptPack, and tier-aware allowed actions.

### Step 1 - Back receives task dispatch

Back receives `k1.orchestration.task.dispatch.v1` and `route_back_envelope(...)` invokes `back_handler`. See [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L1660).

### Step 2 - Back binds task-scoped dispatcher context

`back_handler` creates a task-scoped Back dispatcher with `_maybe_rebind_back_dispatcher(...)`, then binds trace id, session id, task id, safety band, and execution profiles into `ToolContext`. See [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L238) and [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L112).

This matters because capability binding only runs for Back when `ctx.actor == "back"`, `ctx.active_task_id` is set, and `ctx.dispatch` is wired.

### Step 3 - Legacy Back prompt tells model to discover, not invent names

The current Back prompt explicitly says `discover_capabilities(intent, domain)` is the system-of-record discovery tool and that Back must copy registry names exactly. See [k1/concierge/prompt/back_prompt.py](../../k1/concierge/prompt/back_prompt.py#L260).

Important prompt rule:

```text
Never skip discovery on a guess, on a generic noun, or on a verb the user spoke.
When in doubt: discover.
```

Target prompt rule:

```text
For execution authority, never skip resolve_situation.
Discovery may help catalog lookup, docs, or missing-capability suggestions.
It must not authorize side effects, protected reads, or cross-resource plans.
```

### Step 4 - LLM calls `discover_capabilities`

`ToolDispatcher.dispatch(...)` validates allowlist, budget, schema, policy gate, and CRISIS side-effect constraints, then calls `execute_tool(...)`. See [k1/concierge/tools/dispatcher.py](../../k1/concierge/tools/dispatcher.py#L477).

For discovery, `execute_discover_capabilities(...)`:

1. Requires an `intent` string.
2. Uses a per-session cache by `(intent.lower(), domain.lower())`.
3. Calls `ctx.dispatch.discover_capabilities(intent=intent, domain=domain, top_k=10, safety_band=ctx.safety_band)`.
4. If a domain is supplied, performs both a domain-filtered collection and an unfiltered collection.
5. Deduplicates by exact capability `name`.
6. Converts each `CapabilityContract` into the LLM-facing record.

Status: **Discovery intentionally returns both domain-specific and global candidates. This increases recall but adds noise. In the target path, this is acceptable for catalog retrieval but not for execution-time authority.**

### Step 5 - Fabric discovery searches capability contracts

`FabricDispatchAdapter.discover_capabilities(...)` forwards to Fabric in [k1/concierge/adapters/fabric_dispatch.py](../../k1/concierge/adapters/fabric_dispatch.py#L369). Fabric returns scored capabilities from its registry/retrieval stack.

The returned contract metadata comes from family tool `ActionSpec` values via `manifest_translator.build_contract(...)`. See [k1/fabric/manifest_translator.py](../../k1/fabric/manifest_translator.py#L129).

### Step 6 - Back observes candidate records

Example live discovery for calendar task:

```text
discover=create a calendar event for Riley soccer practice tomorrow at 5pm
domain=calendar
count=19

cap=calendar_activity_v1
domains=calendar/family/coordination
score=0.325
fields=
profile=calendar.v1
template=

cap=tool.execute.calendar.create_event
domains=family/calendar/coordination/scheduling/availability/external_calendar
score=0.125
fields=title,start,end
profile=calendar.v1
template=calendar_activity_v1
```

Example live discovery for reminder task:

```text
discover=add a reminder 1 hour before the event
domain=reminders
count=18

cap=reminders_activity_v1
domains=reminders/family/coordination
score=0.325
fields=
profile=reminders.v1
template=

cap=tool.execute.reminders.create_reminder
domains=family/reminders/coordination/alerting/notification/scheduler
score=0.125
fields=title,recipient,trigger
profile=reminders.v1
template=reminders_activity_v1
```

Status: **The right executable capabilities are present, but activity/profile records can rank above executable actions. This is evidence that execution must move to situated projection and binding, not evidence that a stronger ranker can safely own execution.**

---

## End-To-End Invocation Flow

**Section mode:** current proof.

This is the current Tier-2 compatibility path. Target invocation prefers `binding_id` from a `ResolutionEnvelope`; `capability_name` remains a compatibility fallback only when the binding authority has proven the legacy native tool path.

### Step 1 - Back chooses exact capability name

Back must call:

```json
{
  "capability_name": "tool.execute.calendar.create_event",
  "params": {
    "title": "Riley Soccer Practice",
    "start": "2026-05-18T17:00:00",
    "end": "2026-05-18T18:00:00",
    "attendees": ["Riley"]
  }
}
```

It cannot call a generic name like `calendar.create_event`, cannot invoke `calendar_activity_v1`, and cannot invent slugs.

### Step 2 - Dispatcher validates the Back meta-tool call

`ToolDispatcher.dispatch(...)` checks:

- Self-model policy gate if wired.
- Actor/tier allowlist.
- Tool budget.
- Per-tool call limits.
- Back no-work guard for early `submit_result(complete)`.
- JSON schema validation for the meta-tool args.
- CRISIS side-effect blocking.

See [k1/concierge/tools/dispatcher.py](../../k1/concierge/tools/dispatcher.py#L477).

### Step 3 - `execute_invoke_capability` validates and binds the capability

`execute_invoke_capability(...)` in [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1487):

1. Normalizes a small set of params.
2. For Back, calls `_bind_capability_for_back_action(...)` if context is fully bound.
3. Looks up the exact capability contract.
4. Runs `recovery_for_unsatisfied_contract(...)` to check required inputs.
5. Builds `CapabilityRequest` with prompt metadata and execution profiles.
6. Calls `ctx.dispatch.dispatch_direct(...)`.

### Step 4 - Param completeness can stop invocation before Fabric execution

Live failure when Back supplied `duration_minutes` but no `end`:

```json
{
  "status": "error",
  "error": "capability_params_incomplete",
  "data": {
    "status": "needs_human",
    "capability_name": "tool.execute.calendar.create_event",
    "schema": {
      "required_inputs": ["title", "start", "end"]
    },
    "params": {
      "title": "Riley Soccer Practice",
      "start": "2026-05-18T17:00:00",
      "duration_minutes": 60,
      "attendees": ["Riley"]
    },
    "recovery": {
      "action": "ask_human",
      "missing_fields": ["end"]
    }
  }
}
```

Status: **The tool contract is exact, but Back needs deterministic task-to-contract transforms for common shapes like `duration_minutes -> end`.**

### Step 5 - Fabric and NativeToolProvider execute schema-valid requests

If params are schema-valid, Fabric resolves the contract, runs policy/HIL/context build, creates the provider, and calls `NativeToolProvider._execute(...)`.

`NativeToolProvider` builds a `WriteContext`, then calls the adapter's `BaseToolService.dispatch(...)`. See [k1/fabric/providers/native_tool_provider.py](../../k1/fabric/providers/native_tool_provider.py#L285) and [k1/tools/family/base_service.py](../../k1/tools/family/base_service.py#L104).

Status: **When the request is GREEN and schema-valid, execution works.**

---

## What Information From Tools Is Provided To Back LLM?

Current baseline: Back receives three different information layers.

Target model: Back receives staged information by disclosure phase:

```text
Phase 1: connector summaries + connector constitutions + tool names only
Phase 2: committed selected tool names / binding candidates
Phase 3: schemas only for selected/bound tools
Phase 4: invocation, verification, recovery, or HIL observations
```

The baseline layers below are useful proof of what exists, but they are too broad for target execution-time context.

### Layer 1 - Meta-tool function declarations

These are provider-native function/tool schemas for `recall_memory`, `discover_capabilities`, `invoke_capability`, `batch_invoke_capabilities`, and `submit_result`.

This is the only layer the LLM can directly call by function name.

### Layer 2 - Capability discovery records

These are data returned by `discover_capabilities` in the current baseline. They include executable capability names and contract metadata. They are not callable function declarations by themselves.

Target correction: discovery records must not be the execution-time schema disclosure unit. The resolver should first expose connector constitution cards and tool names. Full schemas move into `selected_schema_cards` only after tool selection/binding.

Baseline record example:

```json
{
  "name": "tool.execute.calendar.create_event",
  "description": "Create a calendar event...",
  "domain": "family",
  "domains": ["family", "calendar", "coordination"],
  "score": 0.125,
  "prompt_template": "calendar_activity_v1",
  "activity_profile": "calendar.v1",
  "tool_instructions": "Examples: ...",
  "limitations": ["..."],
  "schema": {
    "required_inputs": [
      {"name": "title", "type": "string", "description": "Short event name."},
      {"name": "start", "type": "datetime", "description": "Event start (ISO 8601)."},
      {"name": "end", "type": "datetime", "description": "Event end (ISO 8601, strictly > start)."}
    ],
    "optional_inputs": [...],
    "capabilities": ["write", "adapter:calendar"],
    "output": {...},
    "safety_band_min": "GREEN"
  }
}
```

### Layer 3 - Invocation result observations

After `invoke_capability`, Back observes a `ToolResult` such as:

```json
{
  "tool_name": "invoke_capability",
  "status": "ok",
  "data": {
    "result": {
      "success": true,
      "event_id": "...",
      "version": 1
    },
    "duration_ms": 128,
    "status": "success"
  }
}
```

For failures, Back sees structured errors such as `capability_params_incomplete`, `dispatch_not_wired`, `capability_binding_invalid_candidate`, `capability_binding_ambiguous`, provider errors, HIL recovery contracts, or safety/policy denials.

---

## Tool Surface Map

### `k1/tools/family`

Primary native app surface. Each adapter declares actions in a `definition.py` file and implements handlers in `service.py`.

Important native adapters:

- [k1/tools/family/calendar](../../k1/tools/family/calendar)
- [k1/tools/family/tasks](../../k1/tools/family/tasks)
- [k1/tools/family/reminders](../../k1/tools/family/reminders)
- [k1/tools/family/chores](../../k1/tools/family/chores)
- [k1/tools/family/shopping](../../k1/tools/family/shopping)
- [k1/tools/family/family_settings](../../k1/tools/family/family_settings)

### `k1/tools/wasm_modules`

WASM module executors exist for utility-style tools such as date calculation and unit conversion. These are not `BaseToolService` family adapters and do not enumerate through the native family `ToolRegistry`.

### `k1/tools/mcp_servers`

MCP surface exists, but live raw kernel probe logged missing MCP config:

```text
Failed to load MCP config: MCP config not found: k1\connectors\mcp_servers.yaml
```

Status: **For the current Back/native-tools question, family tools are the concrete live path. MCP requires separate config validation.**

### Bridge / IFL connector surface

Bridge and IFL are the target external connector path for real-world apps, devices, and services. They are not supposed to become direct Back LLM tools.

Target relationship:

```text
Back meta-tool
  -> Fabric capability binding/invocation
    -> Bridge ConnectorGateway
      -> IFL adapter runtime
        -> external app/device/service
```

Bridge/IFL must provide connector security, credential handling, adapter dispatch, event ingestion, resource projection deltas, and manifest-to-contract registration. Back should see only the staged target surface: connector summaries/constitutions and tool names before binding, selected schemas after binding, PromptPack cards, bindings, and normalized invocation observations.

Status: **Bridge/IFL is the future external connector authority path. It should feed Fabric contracts and local-world projection, not expand Back's raw LLM tool list.**

---

## Loop Stability Observations

### BTC-L1 - Last iteration is a nudge, not a hard constraint

On Back's final iteration, `react_loop` appends a user message telling the model it must call `submit_result`, but tool choice remains automatic. See [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L1420).

Status: **Helpful but soft. The model can still fail to call `submit_result`.**

### BTC-L2 - Mixed `submit_result` plus other tools skips work

If the LLM returns `submit_result` alongside other tool calls, the loop warns and processes `submit_result` first; other tools are skipped. See [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L1815).

Status: **This is a strong signal of model confusion and can create false completion if not guarded by result semantics.**

### BTC-L3 - Capability spin guard is soft

If Back repeatedly discovers/recalls but never invokes, a one-time nudge tells it to stop discovering and invoke exact names. See [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L2070).

Status: **The guard helps, but cannot force authority execution.**

### BTC-L4 - No-work guard can be bypassed by memory/context work

`ToolDispatcher` rejects `submit_result(complete)` before any invoke/batch/recall/context work. But after `recall_memory`, a model can still submit complete without authoritative capability execution. See [k1/concierge/tools/dispatcher.py](../../k1/concierge/tools/dispatcher.py#L630).

Status: **The guard is directionally correct, but system-of-record tasks need a stricter authority-attempt invariant.**

---

## Issue Register

**Section mode:** current proof and migration blockers.

### BTC-001 - Discovery mixes executable tools with activity/profile contracts

**Finding:** Live discovery returned `calendar_activity_v1` and `reminders_activity_v1` above executable capabilities. These records have profile metadata and no required fields, but are not the actual family-tool action Back should invoke.

**Risk:** Back may choose a guidance/profile record or spend reasoning budget separating guidance from executable actions.

**Needed:** Mark discovery records with `record_type` or `kind` such as `executable_capability`, `activity_profile`, `workflow`, `agent`, `read_capability`, `write_capability`. This is a compatibility cleanup. The target execution fix is to stop asking ranked discovery records to carry authority; use situated resolution, connector constitutions, and binding bundles instead.

### BTC-002 - Discovery ranking does not make action selection easy

**Finding:** Live calendar discovery ranked `calendar_activity_v1` at `0.325`, while `tool.execute.calendar.create_event` was `0.125`; many calendar actions shared the same score.

**Risk:** The model must infer from names and schemas rather than ranking. This increases loops and wrong choices.

**Needed:** Do not make ranking the execution fix. A deterministic display order can help readability, but target authority must come from completeness proof, connector constitution, policy bundle, and binding id. `recommended` / `primary_candidate` is presentation only after the candidate universe is complete for scope.

### BTC-003 - Task params and capability schema can be near-miss mismatches

**Finding:** The sample task had `duration_minutes`; the calendar contract requires `end`. Live invocation returned `capability_params_incomplete` and asked the human for `end`, even though `end` is computable from `start + duration_minutes`.

**Risk:** Back escalates to HIL unnecessarily and loses autonomy.

**Needed:** Deterministic param normalization for common contract transforms, especially:

- `duration_minutes` + `start` -> `end`
- names like `Riley` -> normalized member slug/reference where appropriate
- reminder offset + created event id -> event-offset trigger
- user spoken date/time -> ISO temporal fields using temporal refs

### BTC-004 - Safety-band semantics conflict across Fabric and family tools

**Finding:** Fabric `SecurityContext.check_band` treats bands like permission levels: `AMBER >= GREEN` passes. Family `VisibilityPolicy.check_band` treats bands like current risk state: GREEN and AMBER can run AMBER-min actions, but RED/CRISIS block AMBER-min actions; AMBER blocked a GREEN-min calendar write in live probe. See [k1/fabric/policy/security_context.py](../../k1/fabric/policy/security_context.py#L203) and [k1/tools/family/policy.py](../../k1/tools/family/policy.py#L43).

**Live proof:** `tool.execute.calendar.create_event` with schema-valid params failed under AMBER with:

```text
Band 'AMBER' below min_band 'GREEN' for 'create_event'
```

The same request succeeded under GREEN.

**Risk:** Back can discover a capability, pass Fabric, then fail in the native provider due to different band semantics.

**Needed:** Resolve semantics. Either rename one layer's concept or map Back task safety into the correct native family write band before invoking. This is a root-cause issue.

**Committee target solution:** Split the overloaded band into separate kernel axes:

```text
actor_clearance
task_risk_state
operation_risk_class
autonomy_level
runtime_block_state
provider_runtime_band mapped with evidence
```

Back and PromptPack should reason over kernel safety semantics. Fabric/native/connector
providers may keep their own band labels only behind explicit `SafetyMappingEvidence`.

### BTC-005 - Dependent multi-tool work cannot always be batched

**Finding:** `batch_invoke_capabilities` is efficient for independent invocations. Calendar event + reminder is often dependent because the reminder needs the event id returned by calendar creation.

**Risk:** Back may batch calendar creation and reminder creation before it has `event_id`, causing invalid reminder params or weaker linkage.

**Needed:** Prompt/contract rule: batch only independent calls. For dependent calls, invoke first capability, observe result, then invoke dependent capability.

### BTC-006 - Tool instructions are discover-time only

**Finding:** `tool_instructions` and `limitations` are included in discovery records, but invocation mainly forwards prompt metadata, execution profiles, and params through `CapabilityRequest`.

**Risk:** If the model does not retain discovery instructions in context, invocation does not re-display them.

**Needed:** Consider carrying selected discovery contract summary into `invoke_capability` observations or context override, especially when binding corrects/chooses a capability.

### BTC-007 - Back prompt asks for exact names, but recovery errors are still cognitively dense

**Finding:** Binding and param-completeness errors return structured recovery data, but the model must parse nested `data.recovery`, `candidates`, and `schema` fields.

**Risk:** Back can waste iterations retrying similar invalid calls.

**Needed:** Normalize recovery observations into a smaller, model-facing directive field like `next_tool_call` or `retry_plan`.

### BTC-008 - Self-model policy gate affects raw kernel probes

**Finding:** Raw `KernelService` probes do not seed the coordinator-style actor projection. With self-model enabled, manual Back dispatch can fail closed in `ConciergePolicyGate` with `UnknownActorError: actor:<session_id> not in projection store`.

**Risk:** Probe results can look like Back/Fabric failure when the issue is missing self-model seed in the probe environment.

**Needed:** Keep self-model opt-in for raw probes or add a coordinator-backed probe mode that seeds actor projections like the web runtime.

### BTC-009 - Raw probes emit non-blocking observability/topic warnings

**Finding:** Direct Back dispatcher probes emitted FSM dead letters for `k1.tool.started.v1` / `k1.tool.completed.v1` because the FSM was in `LISTENING`, and emitted an unknown-topic warning for `k1.tool_state.changed.v1` while still delivering.

**Risk:** These can distract from the actual tool contract result.

**Needed:** Probe mode should either subscribe/capture tool lifecycle topics directly or annotate these warnings as expected in direct-dispatch probes.

### BTC-010 - Role and space defaults can mask missing caller context

**Finding:** `NativeToolProvider._build_write_context(...)` defaults unrecognized/missing role to `parent` and missing face to `llm`. See [k1/fabric/providers/native_tool_provider.py](../../k1/fabric/providers/native_tool_provider.py#L285).

**Risk:** Back calls can succeed with overly permissive defaults in probes or degraded session contexts.

**Needed:** Make caller role, space id, and face explicit in Back/Fabric requests for production paths; use permissive defaults only in test mode.

### BTC-011 - Back is still treated as the universal executor in older sections

**Finding:** Several baseline sections describe Back as framing, discovering, sequencing prerequisite reads, mutating, verifying, and submitting for tasks that may actually be family-impacting or cross-resource.

**Risk:** The design asks the Tier-2 worker to do Tier-3 planning and orchestration. The model then has to invent impact-set expansion and dependency ordering from missing context.

**Needed:** Route by tier before execution authority. Back owns Tier 2 single-connector execution. Planner and Orchestrator own Tier 3 multi-resource plans and dependency-gated execution.

### BTC-012 - Connector constitution is not yet a contract artifact in the baseline

**Finding:** The baseline returns capability records and tool instructions, but the procedural checks live in prose or prompt text rather than on connector/capability contracts.

**Risk:** The LLM cannot know to check duplicates, conflicts, chores, homework, caregivers, or verifier paths unless the system explicitly gives it that knowledge at planning time.

**Needed:** Add connector/capability constitution fields for preconditions, companion_resource roles, verifier requirements, schema disclosure phase, and HIL triggers. PromptPack should render compact cards from those fields, not from ad hoc prompt text.

### BTC-013 - Tier 3 needs a cross-resource time-window read model

**Finding:** Scheduling conflicts currently appear as per-tool reads (`calendar`, `tasks`, `reminders`, `chores`) rather than a single query shape over `(person, time-window)`.

**Risk:** The model must remember every companion resource to read, and omissions look like success.

**Needed:** Add a local-world projection query that can return commitments by person/time-window across calendars, chores, tasks/homework, reminders, and relevant caregivers. Tier 3 Planner uses this read model to build and validate the PlanGraph.

### BTC-014 - PlanGraph cannot be optional for Tier 3

**Finding:** Contract L currently says PlanGraph is optional. That is true for Tier 2 but false for family-impacting, multi-resource, dependency-bearing work.

**Risk:** Without a mandatory PlanGraph for Tier 3, reads-before-writes remains a prompt hope instead of an orchestrator-enforced dependency graph.

**Needed:** Make PlanGraph mandatory for Tier 3 and optional only for Tier 2. Every Tier-3 executable StepFrame must resolve through CandidateUniverse, PolicyBundle, BindingBundle, and allowed_next_actions before Orchestrator execution.

---

## Fix Order

### 1. Bind the tier router to execution authority

The first architectural fix is ownership: LOW/simple tasks may reach Back, MEDIUM/HIGH family-impacting or cross-resource tasks must route to Orchestrator/Planner. Without this, every other fix still asks Back to invent a plan it was not given.

### 2. Add connector/capability constitution artifacts

Connector constitutions must carry preconditions, duplicate/conflict checks, companion_resource roles, HIL triggers, verifier requirements, and staged schema-disclosure rules. This is where the dumb LLM learns what must be checked.

### 3. Resolve band semantics

This is the sharpest verified runtime blocker. A schema-valid GREEN-min native action failed under AMBER. Treat Back task `safety_band` as a legacy scalar in the current path, then map it into explicit SafetyContext axes before `NativeToolProvider` sees the request.

### 4. Separate executable discovery from guidance/profile records

Compatibility Back needs a cleaner result set when the intent is system-of-record execution. Either hide profile contracts from `discover_capabilities`, mark them clearly, or add `executable_only` / `action_only` filtering. Target execution should not depend on this ranking path for authority.

### 5. Add deterministic param adapters for native family tools

Start with calendar and reminders:

- Calendar: `duration_minutes` -> `end`.
- Calendar attendees: human names -> member references/slugs.
- Reminder: offset from event -> `trigger={kind:"event_offset", event_id, offset_minutes}`.
- Reminder recipient: human names -> member references/slugs.

### 6. Make dependent execution explicit

Tier 2 Back and Tier 3 Planner/Orchestrator contracts must state that dependent calls are sequenced. Calendar event creation must complete before a linked reminder can use the new `event_id`; Tier 3 encodes that as a PlanGraph dependency.

### 7. Harden loop termination for Back

Consider stronger loop rules:

- Reject mixed `submit_result` plus other tools unless `submit_result` is last and no unexecuted side-effect tools remain.
- On last Back iteration, force `tool_choice="submit_result"` if provider supports it.
- Require authority invocation attempt before `submit_result(complete)` for system-of-record tasks, even if `recall_memory` happened.

### 8. Improve recovery observation shape

Compress nested recovery payloads into model-facing retry directives. The current data is structurally rich but cognitively heavy.

---

### Issue-To-Contract Mapping

```text
BTC-001 mixed executable/guidance records
  Contracts C, D, F, G: capability kind separation, binding authority, CandidateUniverse, PromptPack.

BTC-002 schema/param transformation
  Contracts D, H, J: binding schema refs, InvocationRequest, RecoveryDirective.

BTC-003 dependent execution
  Contracts L, H, M: PlanGraph sequencing, invocation observations, verification obligations.

BTC-004 safety-band mismatch
  Contract O: SafetyContext and SafetyMappingEvidence.

BTC-005 batching dependent work
  Contracts L and H: StepFrame dependencies and per-binding batch observations.

BTC-006 discover-time-only instructions
  Contracts G and J: PromptPack cards and RecoveryDirective/injection timing.

BTC-007 dense recovery errors
  Contract J: ErrorObservation and RecoveryDirective.

BTC-008 self-model probe gate
  Contracts A, N, P: RequestFrame actor scope, trace/authority evidence, protected-read/actor policy.

BTC-009 probe lifecycle warnings
  Contracts N and Q: trace evidence and ProofRecord classification.

BTC-010 role/space permissive defaults
  Contracts A, D, O: explicit actor scope, binding constraints, safety mapping.

BTC-011 Back treated as universal executor
  Three-tier model, Contract A, Contract E, Contract L: route tier, escalation reason, allowed actions, PlanGraph/DAG ownership.

BTC-012 connector constitution missing
  Contracts C, D, F, G and Plane 2: precondition rules, companion_resource roles, connector constitution cards, staged disclosure.

BTC-013 cross-resource time-window read model missing
  Contracts F, L, M and Plane 4: impact set candidates, cross-resource read requirements, PlanGraph prerequisite reads, verification.

BTC-014 PlanGraph optional for Tier 3
  Contract L and Orchestrator boundary: mandatory Tier-3 PlanGraph, StepFrame dependencies, deterministic execution waves.
```

---

## Current Baseline Verdict

Back's tool contract path is wired, but the model is being asked to solve too much contract interpretation dynamically:

- It must distinguish meta-tools from discovered capabilities.
- It must ignore profile/guidance records as executable targets.
- It must copy exact registry names.
- It must transform task payloads into strict capability schemas.
- It must understand dependent sequencing.
- It must decide tier ownership from prompt context instead of a contract-bound router.
- It must infer procedural checks that should live on connector constitutions.
- It lacks a cross-resource `(person, time-window)` read model for family-impacting schedules.
- It can be asked to perform PlanGraph work inside a ReAct loop.
- It must recover from nested errors under a small iteration budget.
- It can hit cross-layer safety-band disagreement even after doing everything else right.

The system should make the correct action path more deterministic before expecting the LLM to be stable: route the tier, disclose connector constitutions, prove the local world, bind capabilities, and only then expose schemas or execute.

---

## Current Front-To-Back Handoff Audit

**Section mode:** current proof plus migration boundary.

This pass answers a narrower integration question: what does the Front LLM actually give Back today, and what more is required for the target `RequestFrame -> resolve_situation -> CandidateUniverse -> PromptPack -> binding/invocation` design?

Short answer:

```text
The user's intuition is mostly right:
  Back starts with dispatch_task output plus a one-shot SessionState snapshot.

But the live path is slightly richer:
  Front/FSM/runtime also add task_id, tier, budget, trace/session correlation,
  optional grounding metadata, fallback referents, narrative thread, task overlay,
  execution profile selection, and Back ToolContext bindings.
```

The important gap is also clear:

```text
Current handoff passes task intent and local context.
Target handoff needs execution authority artifacts:
  RequestFrame
  CandidateUniverse
  PromptPack
  scope proof
  binding ids
  policy/freshness/completeness verdicts
  allowed next actions
```

### Current Runtime Path

```text
User input envelope
  -> front_handler
     DynamicPromptBuilder builds Front prompt and tool list
  -> Front LLM calls dispatch_task(...)
  -> execute_dispatch_task returns ToolResult.data._dispatch
  -> react_loop collects result.dispatched_tasks[]
  -> front_handler post-loop emits build_task_dispatch(...)
  -> FSM._on_task_dispatch parses payload into TaskDispatch
  -> FSM._route_via_orchestrator canonicalizes payload
     LOW     -> Back mailbox
     MEDIUM  -> Orchestrator when wired, otherwise fallback path
     HIGH    -> Orchestrator or strict failure / passthrough fallback depending config
  -> route_back_envelope
  -> back_handler
  -> build_back_prompt + Back ReAct loop
```

Primary code path:

- Front tool schema: [k1/concierge/tools/schemas_front.py](../../k1/concierge/tools/schemas_front.py#L352)
- Front tool implementation: [k1/concierge/tools/implementations.py](../../k1/concierge/tools/implementations.py#L1225)
- Front result collection: [k1/concierge/react/loop.py](../../k1/concierge/react/loop.py#L2008)
- Front dispatch emission: [k1/concierge/actors/front.py](../../k1/concierge/actors/front.py#L1644)
- TaskDispatch dataclass: [k1/concierge/task/dispatch.py](../../k1/concierge/task/dispatch.py#L37)
- FSM canonical routing: [k1/concierge/fsm/controller.py](../../k1/concierge/fsm/controller.py#L2801)
- Back handler: [k1/concierge/actors/back.py](../../k1/concierge/actors/back.py#L976)
- Back prompt builder: [k1/concierge/prompt/back_prompt.py](../../k1/concierge/prompt/back_prompt.py#L411)

### What Front LLM Can Put In `dispatch_task` Today

The current Front-facing `dispatch_task` schema exposes:

```text
dispatch_task
  intents[]
    action
    params
    domain optional
  urgency: normal | urgent | background
  reference_context
  depends_on
  plan
```

The implementation also tolerates fields such as `safety_band` and `complexity`, but those are not part of the visible public Front tool schema today.

What Front can express well today:

```text
user wants an action
natural-language or capability-like action label
structured params extracted from the conversation
domain hint
resolved pronouns / artifact references / general context
simple urgency hint
dependency on an earlier task id
planner escalation hint through plan=true or complexity=HIGH
```

What Front cannot directly express today:

```text
RequestFrame
actor_scope / resource scope proof
candidate resource universe
connector/resource identities
freshness/completeness verdict
policy bundle
guide/contract PromptPack
binding_id
prior_resolution_id
allowed_next_actions
verification obligations
normalized recovery directives
```

### What `execute_dispatch_task` Adds

`execute_dispatch_task(...)` turns the LLM tool call into a `TaskDispatch`-shaped payload.

It adds or derives:

```text
task_id
tier
budget_hint through TaskDispatch
legacy scalar safety_band default GREEN unless supplied; target path maps this into SafetyContext axes before provider dispatch
per-intent urgency normalization
depends_on validation
plan-derived tier escalation
```

Tier derivation today:

```text
complexity=HIGH  -> HIGH
plan=true        -> MEDIUM
depends_on set   -> MEDIUM
otherwise        -> LOW
```

It does not populate:

```text
context_snapshot
execution_profiles
grounding_envelope_id
temporal_anchor_id
spatial_context_id
resolved_temporal_refs
resolved_spatial_refs
grounding
```

Those fields exist on `TaskDispatch`, but the Front LLM schema and this tool implementation do not currently populate them as normal tool-call outputs.

### What `front_handler` Adds After The LLM Tool Call

After ReAct completes, `front_handler` emits task dispatches before the final response. For each normal dispatch it adds:

```text
tier canonicalization
budget_hint
trace_id
```

When a grounding handle/projection exists, it also attaches:

```text
grounding_envelope_id
temporal_anchor_id
spatial_context_id
resolved_temporal_refs
resolved_spatial_refs
grounding projection payload
```

It mirrors grounding metadata into `reference_context.grounding` so Back can still orient from the task JSON even if a later consumer only reads reference context.

This means current dispatch payload is a mixed product of:

```text
Front LLM output
  intents, params, reference_context, depends_on, plan, urgency

Front tool implementation
  task_id, tier, legacy scalar safety_band, budget_hint

Front actor runtime
  trace_id, optional grounding projection and propagation metadata
```

### What The FSM Changes Before Back Sees The Task

The FSM receives the Front-emitted envelope, parses it into `TaskDispatch`, then builds a canonical Back-bound dispatch payload.

It preserves TaskDispatch-owned fields:

```text
task_id
intents
tier
budget_hint
safety_band (legacy scalar)
reference_context
depends_on
context_snapshot if present
execution_profiles if present
grounding_envelope_id if present
temporal_anchor_id if present
spatial_context_id if present
resolved_temporal_refs if present
resolved_spatial_refs if present
grounding if present
```

It also attaches runtime context:

```text
trace_id
session_id
turn-state overlay when available
narrative_thread when available
fallback reference_context from scoreboard referents if Front omitted it
```

Important narrowing seam:

```text
Top-level fields that are not part of TaskDispatch are not guaranteed to
survive FSM canonicalization.

Examples:
  plan
  dispatch-level urgency

Their effect can survive indirectly through tier, depends_on, or per-intent
urgency, but Back should not rely on the original top-level fields being
present after routing.
```

This is a good reason to treat `TaskDispatch` or a future `BackTaskEnvelope` as the source-of-truth handoff contract, not the raw Front tool-call arguments.

### What Back Receives At Loop Start

Back receives the canonical task payload plus envelope correlation headers. `back_handler` then builds a task-scoped execution context.

Back task JSON can include:

```text
task_id
intents[]
  action
  params
  domain optional
  urgency optional when non-default / preserved
tier
budget_hint
safety_band (legacy scalar)
reference_context optional
depends_on optional
context_snapshot optional
execution_profiles optional
grounding_envelope_id optional
temporal_anchor_id optional
spatial_context_id optional
resolved_temporal_refs optional
resolved_spatial_refs optional
grounding optional
trace_id optional
session_id optional
narrative_thread optional
turn-state overlay optional
```

Back also gets correlation and runtime bindings outside the JSON body:

```text
Envelope headers:
  session_id
  request_id
  cognitive_trace_id
  parent_id

ToolContext bindings:
  actor=back
  active_task_id
  session_id
  cognitive_trace_id
  safety_band (legacy scalar)
  active_execution_profiles
```

Back reads SessionState once at task start:

```text
beliefs_active
scoreboard referents
task_state
task_artifacts
control safety band (legacy scalar view)
history_active
persona preferences
```

Back does not read during each ReAct iteration. On resume, Back re-reads SessionState to capture changes made while suspended.

Back prompt receives:

```text
full task JSON
beliefs summary
task_state summary
task_artifacts summary
safety_band (legacy scalar)
persona preferences
max tool calls
available tools note
execution profile block
execution grounding block
resolved temporal refs when present
```

The active Back chat messages are:

```text
recent history window
user message containing json.dumps(task, indent=2)
```

So the Back LLM sees the dispatch payload twice in effect: once inside the system prompt's task block and once as the active task JSON message.

### Current Strengths

The current handoff already has useful architectural bones:

```text
Front does not talk to the user and execute in the same actor.
Back does not write SessionState directly.
FSM remains the routing and task-state authority.
TaskDispatch has future-ready optional grounding/context fields.
Grounding metadata can be propagated without making the Front LLM invent it.
Back gets a task-scoped ToolContext with task id, trace id, safety, and profiles.
Back prompt receives both task JSON and selective SessionState context.
Fallback scoreboard referents protect against missing Front reference_context.
```

### Current Missing Pieces For The Target Design

The missing pieces are not mostly more text in `reference_context`. The target design needs explicit execution authority contracts.

#### Missing Request Frame

Today, Back reconstructs intent from:

```text
TaskDispatch.intents
reference_context
SS snapshot
grounding block
history window
```

Target requires a first-class frame:

```text
RequestFrame
  user_goal
  task_kind
  operation_hints
  actor_scope
  household_or_space_scope
  resource_reference_hints
  temporal_reference_hints
  spatial_reference_hints
  constraints
  safety_context
  autonomy/trust context
  source_turn_id
  idempotency_key
```

This frame can be derived from TaskDispatch + envelope headers + SessionState/grounding handles. It should not require the Front LLM to know Fabric or connector internals.

#### Missing Candidate Universe

Today, Back calls `discover_capabilities(intent, domain)` and gets top-K capability records.

Target requires Contract F `CandidateUniverse` as the only canonical schema owner. This audit section names the missing concepts only:

```text
resource_candidates[]
capability_bindings[]
scope_proof
omissions[]
exclusions[]
projection_version
freshness verdict
completeness verdict
allowed_next_actions[]
```

This is the difference between "search found a tool" and "the system proved which local resources and bindings are in scope."

#### Missing PromptPack

Today, Back receives a static Back prompt plus discovery-time capability records.

Target requires Contract G `PromptPack` as the only canonical schema owner. This audit section names the missing prompt concepts only:

```text
policy cards
guide cards
contract cards
resource cards
verification cards
HIL option cards
forbidden actions
allowed_next_actions[]
allowed_tool_calls[]
```

This should be injected after resolution, not guessed by Front and not copied from raw connector manifests.

#### Missing Binding Authority

Today, Back invokes by exact `capability_name`.

Target should prefer:

```text
binding_id
  joins actor + resource + capability + policy + schema + freshness
```

Compatibility can keep `capability_name` for current native tools, but the future path needs `binding_id` so Back cannot accidentally act on the wrong resource when multiple connectors expose similar capabilities.

#### Missing Normalized Recovery

Today, Back sees useful but nested tool errors such as contract incompleteness, policy denial, or binding ambiguity.

Target requires:

```text
ErrorObservation
RecoveryDirective
  retry_with_params optional
  ask_human optional
  choose_candidate optional
  block_reason optional
  verify_required optional
```

The model should not have to reverse-engineer the next legal move from dense nested payloads.

### Required Integration Additions

The right migration keeps Front small and makes Fabric/Plane 4 responsible for execution authority.

#### 1. Keep Front's dispatch surface user-world oriented

Front should continue to pass:

```text
intents
params
domain hints
reference_context
resolved human references
temporal/spatial language hints when available
safety/autonomy/trust context if the Front/FSM owns it
dependency and cancellation/modification hints
```

Front should not be asked to pass:

```text
binding_id
CandidateUniverse
connector manifests
raw capability catalogs
policy verdicts
scope proof
```

Those belong to Fabric resolution, Bridge/IFL projection, and policy components.

#### 2. Introduce a concrete `BackTaskEnvelope` / `RequestFrame` boundary

The next contract should make CC-0 concrete:

```text
BackTaskEnvelope
  task_dispatch
  envelope_correlation
  actor_scope
  grounding_snapshot_refs
  turn_overlay_ref
  session_snapshot_ref
  request_frame optional
  previous_resolution_id optional
```

The `RequestFrame` can be built by FSM or by Back pre-loop. The key is that it becomes a typed object, not an implied prompt convention.

#### 3. Add `resolve_situation` before capability choice

Back should call a resolver tool for system-of-record execution tasks:

```text
resolve_situation(request_frame)
  -> ResolutionEnvelope
       CandidateUniverse
       PromptPack
       allowed_next_actions
       policy/freshness/completeness verdicts
```

`discover_capabilities` can remain as compatibility/catalog retrieval, but it should stop being the authority path when a resolver result is available.

#### 4. Inject PromptPack after resolution

Back prompt timing should move from one large start prompt to a staged pattern:

```text
loop_start:
  task + SS snapshot + grounding + instruction to build RequestFrame

after_resolution:
  PromptPack + CandidateUniverse summary + allowed next actions

after_invocation:
  InvocationObservation + VerificationObservation + RecoveryDirective
```

This matches CC-10 and prevents Front from overloading `reference_context` with execution policy.

#### 5. Preserve current TaskDispatch fields during migration

Do not break current dispatches. The safe migration path is additive:

```text
Current TaskDispatch fields stay valid.
Optional request_frame_id / resolution_id refs can be added.
Optional grounding/resource snapshot refs can be added.
Back can choose resolver path when present and legacy discover/invoke otherwise.
```

#### 6. Tighten canonicalization rules

The FSM canonicalization step should be treated as a contract boundary. Fields that matter to Back should either be:

```text
part of TaskDispatch / BackTaskEnvelope
or deliberately discarded with a documented reason
```

This avoids accidental loss of fields like top-level `plan` and dispatch-level `urgency`.

### Legacy-To-Target Migration Map

```text
TaskDispatch
  Current role: Front/FSM task handoff payload.
  Target role: compatibility input to BackTaskEnvelope and RequestFrame construction.

Back task JSON
  Current role: model-visible execution task plus legacy scalar safety_band.
  Target role: compatibility body; execution authority moves to RequestFrame and ResolutionEnvelope.

discover_capabilities
  Current role: mixed catalog/discovery source for Back.
  Target role: catalog retrieval, docs lookup, fuzzy support, and missing-capability suggestion.

capability_name invocation
  Current role: exact string used by invoke_capability.
  Target role: compatibility fallback after binding_id authority is available.

ToolContext.safety_band
  Current role: legacy scalar passed into Fabric/native provider path.
  Target role: input to SafetyContext mapping with SafetyMappingEvidence before provider dispatch.

Prompt text/tool_instructions
  Current role: model-visible guidance returned during discovery.
  Target role: compact PromptPack cards sourced from Contract G.
```

### Integration Verdict

Current Front-to-Back handoff is sufficient for the live baseline:

```text
Front dispatches task intent.
FSM routes and enriches.
Back receives task JSON + SS snapshot.
Back discovers and invokes capabilities through Fabric meta-tools.
```

It is not sufficient for the designed resolver system because it lacks execution authority artifacts:

```text
No typed RequestFrame.
No complete local-world CandidateUniverse.
No binding ids.
No scope/freshness/completeness proof.
No PromptPack injection after resolution.
No allowed-next-action envelope.
No normalized recovery directive.
```

The clean boundary is:

```text
Front passes user-world intent and resolved references.
FSM/Back constructs RequestFrame and maintains task/correlation authority.
Fabric resolves resources, bindings, policy, and PromptPack.
Back executes only through the resolver's allowed actions and bound invocation contracts.
```

### Handoff Object Relationship

```text
TaskDispatch
  Current Front/FSM user-world task contract.
  Contains intents, params, references, tier, dependencies, grounding handles, and legacy scalar safety_band.
  Does not contain execution authority.

BackTaskEnvelope
  Target Back intake wrapper.
  Carries TaskDispatch, envelope correlation, actor/session scope, snapshot refs, and optional RequestFrame refs.
  Preserves compatibility while making the handoff explicit.

RequestFrame
  Target resolver input.
  Normalizes user goal, actor scope, operation hints, resource hints, constraints, SafetyContext, privacy/autonomy context, and idempotency.
  It is derived by FSM/Back from TaskDispatch plus state/grounding refs, not invented by Front as connector internals.

ResolutionEnvelope
  Target resolver output.
  Carries CandidateUniverse, PromptPack, PolicyBundle refs, BindingBundle refs, verdicts, freshness/completeness proof, and allowed_next_actions[].
  It is the authority package Back consumes before HIL, invocation, block, or submit.
```

---

## Proposed Plan

**Section mode:** target normative.

This section folds the durable design work from [stale_tool_calling.md](stale_tool_calling.md) into this canonical whiteboard. The stale board remains useful discussion history; this section is the structured plan to carry forward.

### Standard Vocabulary

This vocabulary is normative for tiered execution, Back tool calling, Planner/Orchestrator handoff, Fabric capability binding, and Bridge/IFL connector design.

Committee refinement:

```text
In the generic kernel, these names describe roles and contracts, not only FamilyOS
modules. FamilyOS Concierge/K1/Fabric/Bridge/IFL are the first implementation names.
Future domains should instantiate the same role model rather than forking the core
execution contract.
```

#### DomainInstantiationPack

Purpose:

```text
Describe what a domain contributes to the generic situated-execution kernel.
The pack should make a domain executable without changing core resolver, policy,
binding, prompt, invocation, or proof envelopes.
```

Shape:

```text
DomainInstantiationPack
  domain_id
  domain_name
  domain_version
  ontology_refs[]
  resource_kind_defs[]
  operation_taxonomy_refs[]
  policy_card_refs[]
  guide_card_refs[]
  capability_manifest_refs[]
  connector_manifest_refs[]
  verifier_refs[]
  hil_template_refs[]
  scenario_gate_refs[]
  scenario_gate_class_map[]
  data_classification_rules[]
  extension_namespaces[]
  promotion_requirements[]
```

Examples:

```text
family.household
  resources: people, calendars, tasks, chores, vehicles, rooms, lights, health feeds
  operations: schedule, remind, assign, purchase, control, read status
  policies: guardian consent, child privacy, household authority, freshness gates

enterprise.it_ops
  resources: incidents, services, deployments, dashboards, credentials, runbooks
  operations: diagnose, page, rollback, scale, create ticket, query logs
  policies: on-call authority, change window, audit, break-glass, blast radius

health.clinical_ops
  resources: patients, encounters, orders, care plans, messages, lab results
  operations: review, draft, route, schedule, notify, reconcile
  policies: consent, clinician role, PHI disclosure, double-check, audit retention

finance.advisory_ops
  resources: accounts, transactions, budgets, portfolios, documents, approvals
  operations: read balance, classify, draft recommendation, request approval, execute transfer
  policies: suitability, dual control, transfer limits, disclosure, immutable audit
```

Kernel rule:

```text
A DomainInstantiationPack may add resource kinds, operations, policies, guides,
manifests, verifiers, and scenario gates. It may not remove request framing,
situated resolution, policy selection, capability binding, side-effect idempotency,
prompt boundary rules, normalized observations, verification duties, or proof gates.
```

Scenario gate rule:

```text
Domain scenario gates must map to kernel gate classes, not only product stories.
Required gate classes for an execution-authority domain should include:
  time-bound or stateful mutation with prerequisite reads
  protected read / disclosure side effect
  partial projection across multiple resources or providers
  missing capability separated from catalog suggestion
  ambiguous resource selection with multiple valid bindings
  policy confirmation before irreversible or high-blast-radius action
```

Ontology rule:

```text
ResourceKindDef
  kind_id
  display_name
  identity_fields[]
  owner_scope_fields[]
  alias_fields[]
  connector_scope_fields[]
  supported_operation_refs[]
  data_classification_default
  freshness_requirements_by_effect_class
  verifier_expectations_by_effect_class
  policy_hook_refs[]
  extension_namespace

OperationDef
  operation_id
  display_name
  user_verb_aliases[]
  effect_class: read | protected_read | write | delete | external_send | subscribe | compute
  applicable_resource_kinds[]
  required_roles[]
  required_policy_hooks[]
  required_verifier_refs[]
  idempotency_required
  confirmation_default
  freshness_requirement

DomainAliasRule
  alias_id
  applies_to_resource_kind
  source_fields[]
  normalized_identity_field
  ambiguity_behavior: ask_hil | rank_after_completeness | block
```

Kernel rule:

```text
Domain packs may let the model propose operation hints, but execution authority starts only
after the resolver maps those hints to OperationDef and concrete ResourceCandidate records.
Text labels, aliases, and salience are never sufficient identity for invocation.
```

Open questions for this contract:

```text
OQ-DIP-001: Does each domain pack need a machine-checkable ontology schema first,
or can ontology refs begin as versioned markdown plus typed resource_kind_defs?
  Working solution: allow markdown refs during early design, but require typed
  resource_kind_defs before the pack can promote to execution authority.

OQ-DIP-002: Should scenario gates live in the pack or in the proof harness?
  Working solution: packs declare scenario_gate_refs; the proof harness owns execution,
  result recording, and promotion verdicts.

OQ-DIP-003: Can one task use multiple domain packs?
  Working solution: yes, but the resolver must produce one joined CandidateUniverse with
  explicit ownership of each resource, policy, binding, and verifier. Cross-domain joins
  cannot hide omissions or downgrade policy.
```

#### Core Terms

```text
Tool
  An LLM-callable function exposed to an actor such as Back.
  Back tools are meta-tools that let the LLM reach Fabric or finish work.

  Examples:
    resolve_situation
    inspect_binding
    invoke_capability
    batch_invoke_capabilities
    submit_result

  Not examples:
    Tesla start climate
    Hue set brightness
    Google Calendar create event
```

```text
Capability
  A Fabric-registered contract for a readable/executable operation.
  Capabilities are not directly shown to the LLM as provider function schemas.
  Back reaches them through tools such as invoke_capability.

  Examples:
    tool.execute.transport.tesla.start_climate
    tool.execute.home.hue.set_brightness
    tool.read.health.fitbit.sleep_score
    tool.execute.calendar.google.create_event
```

```text
Connector
  A real-world app/service/device integration connected to FamilyOS.
  The connector is what the user thinks they connected: Tesla, Hue,
  Google Calendar, Chase, Fitbit, Outlook, Instacart.

  A connector exposes:
    resource inventory
    capability manifest
    event streams
    auth/permission scopes
    health/freshness state
    rate/circuit limits
```

```text
Adapter
  The technical runtime implementation behind a connector.
  Existing diagrams often say adapter where product language says connector.

  Hosting modes:
    company_hosted
    wasm_sandboxed

  Examples:
    com.tesla.vehicle IFL adapter
    com.philips.hue IFL adapter
    local MQTT WASM adapter
```

```text
Resource
  A concrete object/account/device/list/feed/person-scoped thing exposed by a connector.
  Resources are what users refer to in the world.

  Examples:
    Alex's Tesla Model Y
    Alex's Audi Q7
    Living room Hue group
    Riley's Fitbit sleep source
    Household grocery list
    Google school calendar feed
```

```text
CapabilityBinding
  A resolved link between task role, resource, actor authority, policy verdict,
  and exact Fabric capability contract.

  Example:
    role: vehicle_climate_writer
    resource: Alex's Tesla Model Y
    capability: tool.execute.transport.tesla.start_climate
    verdict: needs_disambiguation until user chooses vehicle
```

```text
allowed_next_actions
  Resolver-owned decision surface for the current state.
  These are semantic next moves such as invoke_binding, run_prerequisite_read,
  ask_hil, refresh_projection, block, or submit_result.

  allowed_next_actions[] is the authority list Back must obey after resolution.
```

```text
allowed_tool_calls
  Prompt/runtime tool-call surface for the current Back ReAct step.
  These are concrete LLM-callable function names such as resolve_situation,
  invoke_capability, batch_invoke_capabilities, and submit_result.

  allowed_tool_calls[] constrains the provider tool schema; it does not replace
  allowed_next_actions[] as the semantic authority list.
```

#### Ownership

```text
Back LLM tools
  Owner: Concierge / Back ToolDispatcher / Back schemas.
  Purpose: LLM-callable control surface.

Fabric capabilities
  Owner: Capability Fabric registry and providers.
  Source: native family tools, MCP/WASM tools, workflows, agents, or IFL connector manifests.

Connectors
  Owner: Bridge / IFL ConnectorGateway and AdapterRegistry.
  Purpose: auth, manifest ingestion, health, rate limits, dispatch, inbound events.

Resources
  Owner: local world projection composed from Bridge/IFL, K1 family tools,
  K0 tool state, and SessionState grounding where relevant.

Policies and guides
  Owner: Plane 2 policy/constitution/guide system.
  Purpose: decide gates, roles, HIL, privacy, verification, and tool use guidance.
```

#### Standard Sentence Rules

Use these sentences consistently:

```text
Back calls a tool.
Fabric invokes a capability.
A connector exposes capabilities and resources.
An adapter implements connector runtime dispatch.
A resource is the concrete thing being acted on.
A binding joins actor + resource + capability + policy + schema.
```

Avoid these sentences:

```text
Back calls the Tesla capability directly.
calendar_activity_v1 is a capability.
Tesla is the resource.
Top-K found the tool, so the resource is resolved.
```

Corrected language:

```text
Back calls invoke_capability.
Fabric invokes tool.execute.transport.tesla.start_climate.
The Tesla connector exposes a climate-start capability.
Alex's Tesla Model Y is the resource candidate.
calendar_activity_v1 is a guide card, not an executable capability.
```

#### Naming Standard

Back tool names:

```text
snake_case meta-tools
  resolve_situation
  inspect_binding
  invoke_capability
  batch_invoke_capabilities
  submit_result
```

External IFL capability names:

```text
tool.{read|execute|subscribe}.{category}.{connector_slug}.{action}

Examples:
  tool.execute.transport.tesla.start_climate
  tool.execute.home.hue.set_brightness
  tool.read.finance.chase.check_balance
  tool.read.health.fitbit.sleep_score
```

Connector ids:

```text
Use stable connector ids from signed manifests.
Prefer reverse-DNS ids for manifests and registry identity.

Examples:
  com.tesla.vehicle
  com.philips.hue
  com.google.calendar
  com.chase.banking
```

Resource ids:

```text
Resource ids must identify the concrete instance, not only the connector.

Examples:
  resource.transport.com.tesla.vehicle.alex_model_y
  resource.transport.com.audi.vehicle.alex_q7
  resource.home.com.philips.hue.living_room_group
  resource.health.com.fitbit.riley_sleep
```

Current native family capabilities such as `tool.execute.calendar.create_event` remain valid local/native names. Future external connector capabilities should include the connector segment. Compatibility aliases are allowed, but the canonical contract should preserve connector identity.

#### End-To-End Vocabulary Flow

```text
User task
  -> Front/FSM dispatches TaskEnvelope
  -> FSM routes tier
       Tier 1: Front converses / asks
       Tier 2: Back calls resolve_situation / invoke_capability / submit_result
       Tier 3: Planner produces PlanGraph; Orchestrator executes DAG through Fabric
  -> Plane 4 builds CandidateUniverse and staged PromptPack
  -> Fabric binds CapabilityContracts
  -> Bridge ConnectorGateway dispatches to Connector/Adapter when external
  -> Connector acts on Resource in real app/service/device
  -> Fabric returns CapabilityResult / InvocationObservation
  -> Back or Orchestrator verifies / asks HIL / aggregates result by tier
  -> FSM applies outcome and Front presents
```

Concrete example:

```text
User:
  Turn on climate control of my car.

Back tool:
  resolve_situation(task_frame)

Connector resources:
  Tesla connector -> Alex's Tesla Model Y
  Audi connector  -> Alex's Audi Q7

Fabric capabilities:
  tool.execute.transport.tesla.start_climate
  tool.execute.transport.audi.start_climate

CandidateUniverse verdict:
  needs_disambiguation

HIL question:
  Which car should I warm up: Tesla Model Y or Audi Q7?
```

#### Architecture Grounding

The vocabulary above follows the current architecture files:

```text
Bridge / IFL diagrams:
  Bridge owns IConnectorGatewayPort, adapter registry, credentials,
  manifest ingestion, health, rate limits, dispatch, and inbound events.

Fabric diagram:
  Fabric owns capability contracts, registry, retrieval, exact-name execution,
  provider resolution, context building, output validation, and capability results.

Concierge diagrams:
  Back owns LLM-facing meta-tools and ReAct termination through submit_result.
  Back does not own connector auth, connector inventory, or external dispatch.
  Front owns user-facing voice and Tier 1 conversation.

Planner / Orchestrator diagrams:
  Planner owns Tier 3 SKETCH, EXPAND, VALIDATE, COMMIT.
  Orchestrator owns deterministic DAG execution, dependency waves, conditional evaluation,
  compensation, HIL resume, and result aggregation.

KernelService:
  S4 builds Bridge before S3 shared Fabric because Fabric needs Bridge adapters.
  S8 family tools register native capabilities into shared Fabric.
  Per-session Fabric reuses the shared registry and re-registers native provider.
```

### Problem Resolution

The current Back execution shape collapses too many jobs into one query-like tool call:

```text
Back task
  -> discover_capabilities(intent/domain)
  -> invoke_capability(capability_name, params)
  -> submit_result
```

That shape is a Tier-2 compatibility baseline. It is not the target for family-impacting, cross-resource, or dependency-bearing work.

That shape asks one ranked discovery result to answer all of these at once:

```text
1. What did the user ask to do?
2. Which people, places, accounts, devices, lists, feeds, or resources were referenced?
3. Which local resources are visible or controllable by this actor right now?
4. Which operation is requested over those resources?
5. Which capability contracts can perform that operation?
6. Which policy/constitution modules apply before reads, writes, HIL, or block?
7. Which tool/activity guides apply after concrete bindings exist?
8. What exact invokable bindings, params, verifier, and next action should Back use?
```

The resolution is to stop treating execution discovery as plain semantic search. The proposed center of gravity is:

```text
Tier routing + Situated Capability Resolution
```

Execution actors should not ask:

```text
What tool matches this sentence?
```

Execution actors should ask through the resolver boundary:

```text
resolve_situation(task_frame)
  -> CandidateUniverse
  -> PromptPack
  -> policy/freshness/completeness verdict
  -> allowed next actions
```

For Tier 3, this situated resolution feeds Planner EXPAND and Orchestrator DAG execution instead of a single Back ReAct action.

This does not delete semantic/vector search. It demotes it:

```text
Allowed:
  fuzzy synonym help
  guide/docs lookup
  marketplace/catalog browsing
  ranking already-complete candidates for display
  low-risk exploratory suggestions

Not allowed as authority:
  deciding the candidate universe for side effects
  hiding a relevant resource because it scored lower
  deciding actor authority, ownership, consent, or HIL choices
```

Hard invariant:

```text
Ranking is allowed after candidate completeness.
Ranking is not allowed before candidate completeness.
```

### What Is Explicitly Not The Plan

```text
Not:
  make top_k bigger
  improve descriptions and hope ranking fixes it
  inject calendar_activity_v1 after a narrow calendar-only discovery
  write a constitution for every app/tool combination
  let HIL patch an incomplete candidate universe
  ask Back to perform Tier 3 multi-resource planning in prompt text
```

Why those fail:

```text
top_k can still hide the materially relevant tool/resource
late guidance cannot recover candidates never discovered
permutation constitutions explode at 100k tools
HIL only works when the real ambiguity is visible
```

The plan is:

```text
1. Frame the request.
2. Route the tier.
3. Resolve local world/resource candidates and connector constitutions.
4. Bind operations to concrete capabilities.
5. Compose policy/guidance/contracts with staged schema disclosure.
6. Return CandidateUniverse + PromptPack.
7. Let Tier 2 Back execute, ask, block, verify, or submit inside a bounded ReAct loop.
8. Let Tier 3 Planner/Orchestrator expand and execute dependency-gated PlanGraphs.
```

### Four Planes - One System

Tiered execution must be designed across four planes together:

```text
Plane 1: Execution actor loop design (Back for Tier 2; Planner/Orchestrator boundary for Tier 3)
Plane 2: Governance, policy, and guide-card authority
Plane 3: Standard tool contracts and tool design
Plane 4: Situated resolution and provisioning
```

Human map:

```text
                       +--------------------------------+
                       | User / Front task envelope     |
                       +---------------+----------------+
                                       |
                                       v
+----------------------+    asks     +------------------------------+
| Plane 1              |-----------> | Plane 4                      |
| Execution actor loop |             | Resolve + provisioning       |
+----------+-----------+             +--------------+---------------+
           |                                        |
           | receives                               | reads/joins
           v                                        v
+----------------------+             +------------------------------+
| PromptPack           |<------------| Plane 3                      |
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

Plane responsibilities:

```text
Plane 1 - Execution actor loop
  Owns: observe, frame, decide, invoke/ask/block, verify, submit/aggregate by tier.
  Tier 2 owner: Back.
  Tier 3 owner split: Planner creates committed plan, Orchestrator executes DAG.
  Must not invent resources, contracts, authority, or policy.

Plane 2 - Governance, policy, and guide-card authority
  Owns: policy gates, HIL rules, read-before-write, verification duties,
  privacy/authority/freshness requirements, connector constitutions, companion_resource roles,
  and adapter/domain usage guides.

Plane 3 - Tool contracts
  Owns: invokable names, schemas, outputs, effects, resource binding metadata,
  safety requirements, verifier links, errors, limitations, and schema disclosure phase.

Plane 4 - Situated resolution and provisioning
  Owns: request framing support, resource resolution, capability binding,
  policy/guide/contract selection, connector constitution staging,
  completeness/freshness, and PromptPack return.
```

If one plane is weak:

```text
Plane 1 weak -> Back guesses or skips gates
Plane 2 weak -> policy arrives late or becomes combinatorial
Plane 3 weak -> tools cannot be bound, invoked, or verified safely
Plane 4 weak -> search returns top-K instead of a truthful candidate universe
```

### Formal Intersection Surfaces

The four planes should be designed simultaneously by defining their intersections, not by letting one plane own the internals of another plane.

Rule:

```text
Each plane may evolve its internal model freely.
Each plane must honor the shared boundary contracts.
```

The boundary contracts are the product surface. The plane internals are implementation detail.

```text
Plane 1 internal loop can change
  if it still consumes ResolutionEnvelope and emits Invocation/HIL/Submit actions.

Plane 2 policy engine can change
  if it still accepts PolicySelectionRequest and emits PolicyBundle.

Plane 3 registry/contract store can change
  if it still accepts BindingRequest and emits BindingBundle/ToolContract cards.

Plane 4 resolver can change
  if it still accepts ResolveSituationRequest and emits ResolutionEnvelope.
```

#### Surface Map

```text
S1: Plane 1 -> Plane 4
  ResolveSituationRequest
  Purpose: ask for a faithful execution universe, not a ranked list.

S2: Plane 4 -> Plane 2
  PolicySelectionRequest
  Purpose: derive required roles, gates, HIL rules, freshness, privacy, verification.

S3: Plane 4 -> Plane 3
  BindingRequest
  Purpose: bind operation/resource/policy roles to executable contracts.

S4: Plane 4 -> Plane 1
  ResolutionEnvelope
  Purpose: return CandidateUniverse + PromptPack + allowed next actions.

S5: Plane 1 -> Execution runtime / Fabric
  InvocationRequest or BatchInvocationRequest
  Purpose: invoke only bound/allowed capabilities with schema-valid params.

S6: Execution runtime -> Plane 1
  InvocationObservation / VerificationObservation
  Purpose: return normalized result, failure, verifier, and repair information.

S7: Plane 1 -> FSM/HIL/Front
  HILRequest / SubmitResult
  Purpose: ask the human or finish the Back task without leaking internal machinery.
```

Handshake diagram:

```text
                +----------------------+
                | Plane 1 Back loop    |
                +----------+-----------+
                           |
                           | S1 ResolveSituationRequest
                           v
                +----------------------+
                | Plane 4 resolver     |
                +----+-------------+---+
                     |             |
       S2 policy     |             | S3 binding
                     v             v
          +----------------+   +----------------+
          | Plane 2        |   | Plane 3        |
          | Policy/Guides  |   | Tool Contracts |
          +-------+--------+   +-------+--------+
                  |                    |
                  +---------+----------+
                            |
                            v
                +----------------------+
                | ResolutionEnvelope   |
                | CandidateUniverse    |
                | PromptPack           |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Plane 1 action       |
                | invoke / HIL / block |
                | verify / submit      |
                +----------------------+
```

### API Contract Design Rules

**Section mode:** target normative contracts. Contract A through Contract Q define canonical schema ownership unless a contract explicitly says otherwise.

These contracts must be future-proof without blocking plane design.

```text
1. Version every boundary envelope.
2. Use stable required fields and additive optional fields.
3. Preserve unknown extension fields across hops when possible.
4. Represent uncertainty explicitly; do not hide it in low confidence text.
5. Reference large artifacts by id, and include compact cards for prompt use.
6. Separate local execution resolution from global catalog retrieval.
7. Separate concrete resources from capabilities, adapters, and guides.
8. Include provenance, freshness, and scope proof on every resolution.
9. Include omissions/exclusions, not only positive matches.
10. Let missing future metadata degrade conservatively instead of crashing the plane.
```

Envelope base shape:

```text
ApiEnvelope<T>
  contract_name
  schema_version
  trace_id
  task_id
  actor_ref
  safety_context
  created_at
  expires_at optional
  payload: T
  extensions optional
```

Compatibility rules:

```text
Minor version:
  additive fields only
  old readers ignore unknown fields
  new writers preserve old required fields

Major version:
  breaking field rename/removal/semantic change
  requires adapter or compatibility shim

Extensions:
  namespaced keys only
  never required for core V0 execution correctness
  may improve ranking, UX, or adapter-specific behavior
```

### Contract A - RequestFrame

Purpose:

```text
Represent what Back thinks the task is before binding tools.
It is not a tool choice.
It is not a policy verdict.
```

Shape:

```text
RequestFrame
  frame_id
  request_id
  trace_id
  task_id
  session_id
  route_tier_hint: tier1 | tier2 | tier3 | unknown
  escalation_reason optional
  user_goal
  actor_ref
  household_or_space_scope
  operation_hints[]
  resource_references[]
  people_references[]
  time_references[]
  location_references[]
  impact_set_hints[]
  temporal_snapshot_ref optional
  spatial_snapshot_ref optional
  grounding_snapshot_ref optional
  constraints[]
  risk_hints[]
  missing_fields[]
  prior_resolution_id optional
  provenance
  confidence
  extensions
```

Example:

```json
{
  "frame_id": "rf_...",
  "request_id": "req_...",
  "trace_id": "trace_...",
  "task_id": "task_...",
  "session_id": "session_...",
  "user_goal": "Turn on climate control of my car.",
  "actor_ref": "person.alex",
  "household_or_space_scope": "family.default",
  "operation_hints": ["vehicle.climate.start"],
  "resource_references": [
    {"text": "my car", "kind_hint": "vehicle", "scope_hint": "actor_owned_or_accessible"}
  ],
  "missing_fields": [],
  "confidence": "medium"
}
```

Future-proofing:

```text
Operation hints may use namespaced vocabularies.
Unknown namespaces are allowed but cannot authorize side effects by themselves.
Resource references stay as references until Plane 4 resolves them.
```

### Contract B - ResolveSituationRequest

Purpose:

```text
Plane 1 asks Plane 4 for a situated execution universe.
```

Shape:

```text
ResolveSituationRequest
  request_frame
  actor_scope
  safety_context
  resolution_mode: execution | catalog | diagnostic
  target_tier: tier2 | tier3 | unknown
  disclosure_phase: connector_summary | tool_name_selection | schema_binding | execution
  connector_scope_hints[]
  freshness_policy
  prompt_budget
  previous_resolution_id optional
  required_outputs optional
  extensions
```

Rules:

```text
resolution_mode=execution must not return naked top-K as authority.
For disclosure_phase=connector_summary, the resolver returns connector constitutions and tool names, not full schemas.
For disclosure_phase=schema_binding, schemas are returned only for selected/bound tools.
freshness_policy decides whether stale/partial projections can produce HIL or must block.
previous_resolution_id enables refinement without repeating the same work.
```

### Contract C - PolicySelectionRequest And PolicyBundle

Purpose:

```text
Plane 4 asks Plane 2 what rules apply to the framed situation and candidate roles.
Plane 2 returns compact, composable cards and machine-readable gates.
```

Request shape:

```text
PolicySelectionRequest
  request_frame
  actor_scope
  candidate_resource_kinds[] optional
  operation_hints[]
  effect_hints[]
  connector_constitution_refs[] optional
  companion_resource_role_hints[] optional
  safety_context
  known_freshness
  extensions
```

Response shape:

```text
PolicyBundle
  policy_bundle_id
  required_roles[]
  precondition_rules[]
  companion_resource_roles[]
  gates[]
  hil_triggers[]
  verifier_requirements[]
  freshness_requirements[]
  privacy_requirements[]
  protected_read_requirements[]
  disclosure_requirements[]
  data_classification_requirements[]
  redaction_requirements[]
  audit_requirements[]
  retention_requirements[]
  policy_cards[]
  guide_selection_rules[]
  extensions
```

Rules:

```text
Read-only does not mean policy-free. Protected reads may require the same actor,
consent, disclosure, redaction, audit, and verifier discipline as writes.
PolicyBundle must distinguish mutation gates from disclosure gates.
PolicyBundle must declare whether a result may be shown to the model, shown to the user,
stored only by ref, summarized only, or blocked entirely.
If data classification is missing for a sensitive-looking resource kind, the bundle must
default to conservative protected-read handling.
```

Example required roles:

```text
commitment.time_bound.create
  required_roles:
    temporal_resolver
    participant_resolver
    conflict_reader
    writer
    verifier
```

Future-proofing:

```text
Policy returns roles and gates, not hard-coded tool names.
Policy may declare companion resource roles, but the resolver proves the concrete people/resources.
New domains can add PolicyCards without changing Plane 1.
Plane 4 binds roles to tools/resources later.
```

### Contract D - BindingRequest And BindingBundle

Purpose:

```text
Plane 4 asks Plane 3 to bind operation/resource/policy roles to executable capabilities.
```

Request shape:

```text
BindingRequest
  request_frame
  resource_candidates[]
  required_roles[]
  connector_constitutions[]
  selected_tool_names[] optional
  schema_disclosure_phase: names_only | selected_schemas | execution
  operation_hints[]
  actor_scope
  safety_context
  authority_constraints[]
  freshness_constraints[]
  extensions
```

Response shape:

```text
BindingBundle
  binding_bundle_id
  connector_cards[]
  tool_name_cards[]
  bindings[]
  unbound_roles[]
  contract_cards[]
  selected_schema_cards[]
  schema_disclosure_plan
  guide_refs[]
  verifier_links[]
  binding_diagnostics[]
  extensions
```

Binding shape:

```text
CapabilityBinding
  binding_id
  role
  resource_id optional
  capability_name
  contract_ref
  input_schema_ref
  output_schema_ref
  effect_summary
  safety_requirement
  authority_verdict
  verifier_ref optional
  guide_refs[]
  freshness_state
  limitations[]
```

Future-proofing:

```text
Bindings reference contracts by id and version.
Tool names may be disclosed before schemas; executable schemas are disclosed only after selection/binding.
Provider-specific fields live in namespaced extensions.
If a future adapter cannot provide verifier support, the binding must say so explicitly.
```

### Contract E - ResolutionEnvelope

Purpose:

```text
Plane 4 returns the whole situated package the execution tier needs for the next step.
```

Shape:

```text
ResolutionEnvelope
  resolution_id
  request_frame
  candidate_universe
  prompt_pack
  policy_bundle_ref
  binding_bundle_ref
  completeness
  freshness
  verdict
  allowed_next_actions[]
  diagnostics
  extensions
```

Verdict examples:

```text
executable
needs_prerequisite_reads
needs_disambiguation
needs_confirmation
missing_required_params
blocked_by_policy
missing_capability
incomplete_world_projection
stale_projection
cannot_execute
```

Rule:

```text
Plane 1 can act only through allowed_next_actions[].
If allowed_next_actions[] is empty, Plane 1 must block or submit cannot_execute.
```

### Contract F - CandidateUniverse

Canonical schema owner: this contract owns the authoritative CandidateUniverse field names. Earlier and later sections may summarize CandidateUniverse for readability, but they must not define a second schema.

Purpose:

```text
Represent the resolved world for this task, including scope proof and uncertainty.
```

Shape:

```text
CandidateUniverse
  universe_id
  scope_proof
  connector_candidates[]
  resource_candidates[]
  impact_set_candidates[]
  companion_resource_roles[]
  cross_resource_read_requirements[]
  capability_bindings[]
  required_roles[]
  plan_graph_ref optional
  omissions[]
  exclusions[]
  completeness
  freshness
  policy_verdict
  allowed_next_actions[]
  expires_at
```

Scope proof shape:

```text
ScopeProof
  projection_sources[]
  projection_version
  actor_scope
  resource_scope
  connector_scope[]
  companion_resource_scope[]
  time_window_scope optional
  resource_kinds_considered[]
  freshness_state
  completeness_claim
  omissions[]
  exclusions[]
  resolver_version
```

Resource candidate shape:

```text
ResourceCandidate
  resource_id
  resource_kind
  display_label
  connector_id optional
  provider_id optional
  adapter_id optional
  owner_scope
  actor_authority_summary
  aliases[]
  provenance_refs[]
  data_classification
  freshness_state
  availability_state
  supported_operation_refs[]
  affordance_refs[]
  policy_hook_refs[]
  verifier_refs[]
  confidence
  ambiguity_group optional
  limitations[]
```

Resource identity rules:

```text
resource_id is the concrete identity used for binding and proof.
display_label is prompt/user text only.
aliases help resolution but never replace resource_id.
connector_id names the integration; it is not the resource.
provider_id or adapter_id names runtime dispatch; it is not the resource.
data_classification travels with the candidate so protected-read policy can run before disclosure.
```

Completeness states:

```text
complete_for_scope
complete_for_known_connected_resources
partial_projection
stale_projection
unknown_completeness
not_applicable
```

Omission/exclusion shape:

```text
CandidateOmission
  kind: resource | capability | policy | guide | verifier
  id optional
  reason
  severity: info | warning | blocking
  user_visible_summary optional
```

### Contract G - PromptPack

Canonical schema owner: this contract owns the authoritative PromptPack field names. Prompt-injection and runtime-artifact sections describe timing and summaries only; they must not define a second schema.

Purpose:

```text
Give Back a compact, state-specific view without dumping Plane 2/3/4 internals.
```

Shape:

```text
PromptPack
  prompt_pack_id
  react_state
  target_tier
  disclosure_phase
  source_refs[]
  source_versions[]
  candidate_summary
  connector_constitution_cards[]
  tool_name_cards[]
  policy_cards[]
  guide_cards[]
  contract_cards[]
  selected_schema_cards[]
  decision_surface
  uncertainty_markers[]
  omission_summary[]
  option_budget
  context_load_shedding_summary optional
  allowed_tool_calls[]
  forbidden_tool_calls[]
  allowed_next_actions[]
  forbidden_next_actions[]
  hil_options optional
  stale_card_policy
  redaction_summary
  output_schema
  max_tool_calls
  expires_at
```

Rules:

```text
PromptPack is prompt-sized.
PromptPack is not the source of truth; refs point to authoritative contracts.
Plane 1 follows PromptPack for the current state only.
Plane 4 can regenerate PromptPack after reads, HIL, or projection refresh.
Phase-1 PromptPack exposes connector constitutions and tool names only.
Full schemas appear only in selected_schema_cards after the model/runtime has committed selected tools or bindings.
PromptPack must name the legal decision surface, not only the available function schemas.
PromptPack must expose uncertainty as typed fields, not only prose.
PromptPack may elide low-priority candidates only if it records counts, reasons, and inspect/refresh refs.
PromptPack must mark stale cards. A stale card cannot authorize a side-effecting action.
PromptPack must include redaction evidence showing that raw catalogs, secrets, full manifests, and provider payloads did not cross into model context.
Allowed actions must be explainable by source_refs, policy refs, binding refs, or RecoveryDirective refs.
Forbidden actions must be runtime-enforced by the dispatcher, not only described in prompt text.
Memory salience, ranking, and confidence are presentation signals only; they are never execution authority.
```

LLM researcher note:

```text
The model should deliberate over a small, typed decision surface:

  invoke this binding
  run this prerequisite read
  ask this HIL question
  refresh this projection
  submit cannot_execute / blocked / failed

The model should not deliberate over raw global catalog search results, connector
credentials, arbitrary provider payloads, or hidden policy machinery. If the correct
next action cannot be represented in allowed_next_actions, the resolver contract is
incomplete and the model should not be asked to improvise.
```

### Contract H - InvocationRequest And InvocationObservation

Purpose:

```text
Invoke only allowed bindings and return normalized observations to Back.
```

Request shape:

```text
InvocationRequest
  resolution_id
  binding_id or capability_name
  params
  idempotency_key
  actor_ref
  safety_context
  policy_gate_refs[]
  expected_effect
  verifier_requested
  extensions
```

Observation shape:

```text
InvocationObservation
  invocation_id
  binding_id
  status: success | partial | failed | denied | needs_hil | retryable
  provider_status
  result_summary
  artifacts[]
  structured_result
  errors[]
  recovery_directive optional
  verifier_obligation optional
  verification_observation optional
  audit_fields
  extensions
```

Rules:

```text
Invocation must validate params against the selected contract.
Reads may parallelize when policy allows and protected-read gating is satisfied.
Writes and dependent side effects remain sequenced unless policy and data dependencies prove independence.
Side-effecting calls require idempotency_key.
Invocation success does not imply verified completion unless VerificationObservation says so.
```

### Contract I - HILRequest And HILResponse

Purpose:

```text
Ask the human only after the candidate set is faithful enough, or explicitly disclose projection incompleteness.
```

Request shape:

```text
HILRequest
  hil_id
  resolution_id
  reason: disambiguation | confirmation | missing_field | policy_gate | incomplete_projection
  question
  presentation_constraints[]
  choices[] optional
  missing_fields[] optional
  candidate_refs[] optional
  policy_gate_refs[] optional
  disclosure_summary optional
  risk_summary optional
  incomplete_projection_disclosure optional
  expires_at optional
```

Response shape:

```text
HILResponse
  hil_id
  response_id
  resolution_id
  actor_ref
  selected_candidate_refs[] optional
  provided_fields[] optional
  confirmation: approve | deny | modify | ask_later optional
  consent_grants[] optional
  user_constraints[] optional
  freeform_text optional
  captured_at
  expires_at optional
  provenance
```

Presentation constraints:

```text
HIL question text should use user/domain language, not internal component names.
Choices must be stable by candidate_ref even when display labels are similar.
If projection is incomplete, the question must say what may be missing.
If action is high-risk or irreversible, the question must state material effect and target resource.
If data is protected, the question must state what disclosure or consent is being requested.
```

Rules:

```text
If reason=disambiguation, choices must come from CandidateUniverse.
If CandidateUniverse is incomplete, question must say the projection is incomplete.
HIL must not present a top-ranked guess as the whole world.
HIL may satisfy missing fields, disambiguation, confirmation, or consent only when policy allows it.
HIL cannot override hard policy deny, missing connector scope, missing capability, or absent verifier requirements.
HILResponse resumes through previous_resolution_id unless the current ResolutionEnvelope explicitly remains valid.
```

### Contract J - SubmitResult

Purpose:

```text
Finish the Back task with structured outcome, evidence, and audit data.
```

Shape:

```text
SubmitResult
  task_id
  resolution_id optional
  status: completed | partial | needs_hil | cannot_execute | blocked | failed
  user_summary
  evidence_summary
  artifacts[]
  authority_actions_attempted[]
  verification_status
  unresolved_items[]
  audit_fields
  extensions
```

Rule:

```text
For system-of-record tasks, completed requires either verified authority action
or an explicit reason why verification is not available and policy allows degraded completion.
```

### Contract K - ErrorObservation And RecoveryDirective

Purpose:

```text
Normalize failures so Back receives a small next-action directive instead of raw nested runtime errors.
```

Shape:

```text
ErrorObservation
  error_id
  source_component: back | fabric | bridge | ifl | provider | policy | verifier
  code
  severity: info | warning | blocking | terminal
  retryability: retryable | retryable_after_refresh | retryable_after_hil | not_retryable
  user_visible_summary optional
  internal_summary_ref optional
  related_binding_id optional
  related_resource_id optional
  related_capability_name optional
  missing_fields[] optional
  policy_gate_refs[] optional
  recovery_directive optional
  audit_fields
  extensions
```

Recovery directive shape:

```text
RecoveryDirective
  action:
    ask_hil
    retry_with_params
    refresh_projection
    run_prerequisite_read
    choose_from_candidates
    block_and_submit
    cannot_execute
  reason
  allowed_tool_calls[]
  suggested_params_patch optional
  required_fields[] optional
  candidate_refs[] optional
```

Rules:

```text
Raw provider/connector exceptions are stored by reference, not injected directly.
Back sees the normalized directive and compact evidence.
Terminal errors must include whether submit_result should be blocked, failed, or cannot_execute.
```

### Contract L - PlanGraph And StepFrame

Purpose:

```text
Represent task decomposition and dependencies without granting execution authority.
PlanGraph is optional for Tier 2 single-connector work.
PlanGraph is mandatory for Tier 3 family-impacting, cross-resource, dependency-bearing, or compensating work.
Every executable StepFrame still needs situated resolution before invocation.
```

Shape:

```text
PlanGraph
  plan_id
  trace_id
  task_id
  route_tier: tier2 | tier3
  producer: front | back | planner | deterministic_runtime
  planner_owner optional
  execution_owner: back | orchestrator
  user_goal
  step_frames[]
  dependency_edges[]
  global_constraints[]
  unresolved_questions[]
  risk_hints[]
  provenance
  confidence
  extensions

StepFrame
  step_id
  parent_plan_id
  step_goal
  step_kind: read | protected_read | write | delete | external_send | compute | hil | verify | submit
  operation_hints[]
  resource_references[]
  required_artifacts[]
  produces_artifacts[]
  policy_hints[]
  verifier_hints[]
  can_parallelize_with[]
  must_follow[]
  request_frame_ref optional
  resolution_id optional
  status: proposed | resolving | executable | blocked | needs_hil | completed | failed
```

Dependency edge shape:

```text
PlanDependencyEdge
  from_step_id
  to_step_id
  dependency_type: artifact | hil_response | verifier_result | projection_refresh | policy_approval | ordering_only
  required_artifact_refs[] optional
  blocking: true | false
  reason
```

Rules:

```text
PlanGraph cannot authorize side effects or protected reads.
Tier 3 cannot execute without a PlanGraph or equivalent committed DAG.
For Tier 3, Planner owns SKETCH/EXPAND/VALIDATE/COMMIT and Orchestrator owns deterministic execution waves.
StepFrame.operation_hints are hints until mapped to OperationDef by the resolver.
StepFrame.resource_references are references until mapped to ResourceCandidate records.
Only steps with a ResolutionEnvelope verdict and allowed_next_action may invoke.
Dependent writes are sequenced unless policy and data dependencies prove independence.
Cross-resource scheduling writes must depend on prerequisite reads for all companion_resource roles in scope.
Batch invocation must report per binding and must preserve step ids in observations.
If a step fails, downstream dependent steps become blocked, not guessed.
```

### Contract M - VerificationPlan And VerificationObservation

Purpose:

```text
Prove or explicitly limit completion after reads, writes, deletes, external sends, or
protected disclosures. Verification is the evidence bridge between provider observation
and submit_result status.
```

Plan shape:

```text
VerificationPlan
  verification_plan_id
  resolution_id
  binding_id
  invocation_id optional
  verifier_ref
  verifier_method: read_after_write | output_schema | state_compare | audit_receipt | external_receipt | policy_attestation | none_available
  expected_effect
  expected_resource_state optional
  readback_capability_ref optional
  max_staleness
  retry_policy
  degraded_completion_policy optional
  required_for_submit_status: completed | partial | audit_only
```

Observation shape:

```text
VerificationObservation
  verification_id
  verification_plan_id
  invocation_id optional
  binding_id
  status: verified | degraded_verified | failed | inconclusive | skipped_by_policy | unavailable
  observed_effect
  observed_resource_state_ref optional
  audit_receipt_ref optional
  mismatch_summary optional
  stale_read_summary optional
  degraded_reason optional
  policy_ref optional
  recovery_directive optional
  user_visible_summary optional
  proof_refs[]
```

Rules:

```text
Verifier requirements come from ToolContract, PolicyBundle, BindingBundle, or DomainInstantiationPack.
Timing rule: VerificationPlan is selected before invocation. VerificationObservation is produced after invocation. InvocationObservation alone cannot produce submit_result(completed) for mutations that require verification.
Back may request invocation; it does not decide whether verification is required.
If verification fails or is inconclusive, submit_result(completed) is blocked unless policy explicitly allows degraded completion.
Verification observations must be safe summaries plus refs; raw provider payloads stay behind refs.
Readback freshness must be reported. A stale readback cannot silently verify a fresh write.
```

### Contract N - TraceContext And AuthorityDecisionRecord

Purpose:

```text
Make every authority seam reconstructable from redacted evidence. This contract ties
request framing, resolution, prompt injection, binding, invocation, verification, HIL,
and submit_result into one replayable chain.
```

Trace shape:

```text
TraceContext
  trace_id
  request_id
  task_id optional
  session_id optional
  actor_ref
  parent_trace_id optional
  frame_id optional
  plan_id optional
  step_id optional
  resolution_id optional
  policy_bundle_id optional
  binding_bundle_id optional
  binding_id optional
  invocation_id optional
  verification_id optional
  bridge_request_id optional
  ifl_request_id optional
  prompt_pack_id optional
  prompt_capture_id optional
  created_at
```

Authority decision shape:

```text
AuthorityDecisionRecord
  decision_id
  trace_context
  component
  decision_type: allow | ask_hil | deny | block | refresh | invoke | verify | degraded_complete | cannot_execute
  input_refs[]
  output_refs[]
  policy_refs[]
  binding_refs[]
  resource_refs[]
  prompt_refs[]
  omitted_refs[]
  forbidden_action_refs[]
  reason_codes[]
  user_visible_summary optional
  redaction_evidence_ref optional
  created_at
```

Prompt capture shape:

```text
PromptCaptureRecord
  prompt_capture_id
  trace_context
  phase
  prompt_pack_id optional
  card_ids[]
  allowed_tool_calls[]
  forbidden_tool_calls[]
  allowed_next_actions[]
  forbidden_next_actions[]
  safe_summary_ref
  full_prompt_ref optional
  prompt_hash
  redaction_evidence_ref
  retention_policy_ref
```

Redaction evidence shape:

```text
RedactionEvidence
  redaction_evidence_id
  trace_context
  scanned_artifact_refs[]
  forbidden_classes_checked[]
  redaction_counts_by_class
  raw_payload_refs_retained[]
  prompt_visible_leak_count
  verdict: pass | fail | blocked
  failure_refs[] optional
```

Rules:

```text
Every boundary envelope carries or references TraceContext.
Every authority decision records allow/deny/ask/block/refresh/invoke/verify outcome.
Prompt replay records safe summaries and refs, not forbidden material.
RedactionEvidence fail blocks promotion and may block runtime response depending policy.
Non-actions are recorded with the same seriousness as actions.
```

### Contract O - SafetyContext And SafetyMappingEvidence

Purpose:

```text
Prevent overloaded safety labels from silently changing meaning across Back, policy,
Fabric, native providers, Bridge, IFL, and external adapters.
```

Safety context shape:

```text
SafetyContext
  actor_clearance
  task_risk_state
  autonomy_level
  operation_risk_class
  runtime_block_state
  protected_read_class optional
  disclosure_class optional
  confirmation_required
  escalation_policy_refs[]
  hard_block_reason optional
  domain_safety_extensions optional
```

Safety mapping shape:

```text
SafetyMappingEvidence
  mapping_id
  trace_context
  source_component
  target_component
  kernel_safety_context_ref
  provider_runtime_band optional
  provider_permission_scope optional
  provider_risk_mode optional
  mapping_rule_ref
  mapping_verdict: mapped | blocked | unsupported | degraded
  reason
  policy_refs[]
```

Rules:

```text
actor_clearance answers who is allowed.
task_risk_state answers how risky the current situation is.
operation_risk_class answers how consequential the requested operation is.
autonomy_level answers how much the system may do without user confirmation.
runtime_block_state answers whether execution is currently blocked regardless of clearance.
Provider runtime bands must be mapped from kernel axes with SafetyMappingEvidence.
If mapping is missing or unsupported, side effects and protected reads degrade conservatively.
```

### Contract P - ManifestAdmissionRecord

Purpose:

```text
Separate catalog discovery from executable connector admission. A marketplace or catalog
manifest may describe a useful adapter, but it cannot mint executable bindings until the
connector trust and admission path passes.
```

Shape:

```text
ManifestAdmissionRecord
  admission_id
  trace_context
  manifest_id
  connector_id
  adapter_id
  publisher_id
  signature_status: valid | invalid | missing | expired
  trust_tier: first_party | verified_partner | local_dev | untrusted | revoked
  sandbox_mode: company_hosted | wasm_sandboxed | local_only | blocked
  requested_auth_scopes[]
  approved_auth_scopes[]
  resource_model_refs[]
  capability_template_refs[]
  event_topic_refs[]
  data_classification_summary
  permission_review_status: approved | needs_review | denied
  admission_verdict: admitted | catalog_only | denied | revoked
  revocation_policy_ref optional
  diagnostics[]
```

Rules:

```text
Only admitted manifests can produce executable provider routes and CapabilityBindings.
catalog_only manifests may appear in marketplace suggestions, docs, or missing_capability explanations.
denied or revoked manifests cannot appear in allowed_next_actions.
Admission must preserve connector_id and adapter_id through registration, projection, and dispatch.
Credential revocation or trust revocation must stale or remove affected resources before future side effects.
```

### Contract Q - ExecutionBudget

Purpose:

```text
Bound LLM hops, prompt material, resolver fanout, connector calls, verifier calls, latency,
and retries so execution stays predictable at 100k-tool scale.
```

Shape:

```text
ExecutionBudget
  budget_id
  trace_context
  max_llm_hops
  max_tool_calls
  max_resolver_ms
  max_invocation_ms
  max_total_ms
  max_prompt_tokens
  max_prompt_cards
  max_candidate_cards
  max_schema_chars
  max_observation_chars
  max_connector_fanout
  max_verifier_fanout
  max_retries
  budget_exhaustion_policy: ask_hil | partial | cannot_execute | retry_later | block
```

Budget observation shape:

```text
BudgetObservation
  budget_id
  trace_context
  llm_hops_used
  tool_calls_used
  resolver_ms_used
  invocation_ms_used
  total_ms_used
  prompt_tokens_used
  prompt_cards_used
  candidate_cards_shown
  candidates_elided
  connector_fanout_used
  verifier_fanout_used
  retries_used
  exhausted: true | false
  exhaustion_reason optional
```

Rules:

```text
Budget exhaustion must be typed and visible in ResolutionEnvelope or InvocationObservation.
PromptPack may elide context only with omission counts, reasons, and inspect/refresh refs.
Connector fanout must be bounded by resource scope and policy; no global connector sweep for ordinary execution.
Retries must be bounded and idempotent for side effects.
Completed submit cannot hide budget exhaustion that prevented required resolution or verification.
```

### Intersection Invariants

These invariants bind all four planes without freezing their internals.

```text
I1. Plane 1 never invents resources, bindings, policy authority, or contract schemas.
I2. Plane 2 returns policy roles/gates, not provider-specific execution plans.
I3. Plane 3 returns executable contracts and binding metadata, not global family policy.
I4. Plane 4 composes planes 2 and 3 with local world state; it does not replace them.
I5. Candidate completeness is explicit before ranking or HIL.
I6. PromptPack is compact and state-specific; authoritative data remains referenced.
I7. All side-effecting invocations carry actor, safety, policy, idempotency, and audit context.
I8. Unknown future fields must not break old readers unless the major version changes.
I9. Missing metadata causes conservative verdicts, not silent success.
I10. Catalog search may assist resolution, but cannot be execution authority for resource-bound side effects.
I11. Memory, belief, referent salience, and planner output can seed resolution; none of them authorize execution.
I12. Salience and ranking are presentation mechanisms after completeness, not candidate-universe construction mechanisms.
I13. HIL can resolve visible ambiguity or missing fields; it cannot repair a hidden or incomplete candidate universe unless incompleteness is disclosed.
I14. Every PromptPack has source refs, versions, redaction evidence, and expiry. Stale prompt material cannot authorize new side effects.
I15. Every allowed model action must be traceable to a resolver verdict, policy gate, binding, verifier duty, or recovery directive.
I16. Every authority seam must be replayable from redacted proofs: what was asked, what was visible, what was omitted, what was allowed, what was forbidden, and what was invoked.
I17. Domain packs may add ontology and policy, but cannot weaken the core authority chain for side effects or protected reads.
I18. Local provider deployments may collapse processes, but must not collapse authority roles in the contract.
I19. Resource display labels, aliases, connector ids, provider ids, and adapter ids are not execution identity. Binding and proof use stable resource_id plus typed OperationDef mapping.
I20. PlanGraph and workflow templates can organize work, but each executable StepFrame must resolve through CandidateUniverse, PolicyBundle, BindingBundle, and allowed_next_actions before invocation.
I21. Provider success is not verified completion. Required verification must produce VerificationObservation or an explicit degraded-completion policy before submit_result(completed).
I22. Every authority decision emits a replayable AuthorityDecisionRecord linked by TraceContext. Non-actions and refusals are proof artifacts, not missing logs.
I23. HIL can clarify, confirm, or consent only inside policy. It cannot override hard denial, hidden incompleteness, missing connector scope, missing capability, or required verification.
I24. Safety labels are axis-specific. Actor clearance, task risk, operation risk, autonomy, runtime block state, and provider runtime band must not share one ambiguous field.
I25. Marketplace or catalog discovery cannot mint execution authority. External connector capabilities become executable only after ManifestAdmissionRecord admits the manifest and projection discovers concrete resources.
I26. Budgets are contract inputs and proof outputs. Budget exhaustion must produce typed partial, HIL, retry_later, block, or cannot_execute outcomes, never silent success.
```

### Contract Evolution Without Blocking Plane Design

The contracts should define boundaries, not cages.

```text
Stable now:
  envelope metadata
  RequestFrame
  PlanGraph / StepFrame for multi-step work
  CandidateUniverse
  PromptPack
  PolicyBundle
  BindingBundle
  InvocationObservation
  VerificationPlan / VerificationObservation
  TraceContext / AuthorityDecisionRecord
  SafetyContext / SafetyMappingEvidence
  ManifestAdmissionRecord
  ExecutionBudget / BudgetObservation
  ErrorObservation / RecoveryDirective
  SubmitResult

Allowed to evolve behind the seam:
  LLM loop implementation
  policy selection engine
  guide storage format
  contract registry backend
  resource projection owner
  semantic/vector/catalog retrieval internals
  provider-specific adapter behavior
```

Future additions should be additive:

```text
new resource namespaces
new operation namespaces
new PolicyCard types
new GuideCard types
new verifier types
new freshness states
new authority models
new marketplace/catalog links
```

Breaking changes require a major version:

```text
renaming core fields
changing verdict semantics
removing scope proof
removing actor/safety context from side-effect calls
making extension fields required for core execution
```

Design target:

```text
The API contracts should make the four planes meet cleanly.
They should not force all four planes to be finished before any one plane can improve.
```

### Component-Wise Contract Layer

**Section mode:** target normative boundaries.

Yes: plane API contracts are necessary but not sufficient. The next standard is component-wise contracts.

Plane contracts answer:

```text
What information must cross the conceptual plane boundary?
```

Component contracts answer:

```text
Which runtime component asks?
Which runtime component answers?
What exactly is requested?
What exactly is returned?
What is injected into Back's prompt, and when?
What failures are allowed, blocked, retried, or escalated to HIL?
```

Without component contracts, a correct plane design can still fail at runtime because Back, Fabric, Bridge, IFL, and prompt assembly can each interpret the same word differently.

#### How To Design Small Components Before Coding

This is the point where design can feel fake if we are not careful. The goal is not to
invent hypothetical classes, file names, or internal algorithms before code exists. The
goal is to design the smallest runtime seam so clearly that coding becomes a proof step,
not a guessing step.

Pre-code component design means:

```text
Describe the black box.
Name the caller and callee.
Name the one thing crossing the boundary.
Name the response.
Name what must never be inferred.
Name the failure shapes.
Name the proof that would convince us the seam works.
```

It does not mean:

```text
Pretend we already know every class.
Freeze the storage schema before the POC teaches us.
Write pseudo-code for internals that may change.
Design a giant subsystem as one component.
Treat natural-language design as production truth without proof.
```

##### Component Atom

The smallest useful design unit is a component atom:

```text
ComponentAtom
  one caller
  one callee
  one request envelope
  one response envelope
  one authority question
  one prompt/security boundary
  one failure family
  one proof scenario
```

If a component has more than one independent caller, more than one authority question,
or more than one unrelated failure family, it is probably too large and should be split.

Good smallest atoms:

```text
TaskDispatch -> BackTaskEnvelope canonicalizer
RequestFrame builder
ResolveSituation tool surface
ResourceUniverse projection reader
PolicyBundle selector
BindingBundle builder
PromptPack builder
InvocationRequest preflight validator
SafetyContext mapper
VerificationPlan runner
HILRequest builder
AuthorityDecisionRecord writer
```

Too large as first design atoms:

```text
The whole resolver
All of Bridge
All of policy
All prompt injection
All external connectors
End-to-end execution
```

Those large systems are real, but they should be composed from component atoms.

##### Natural-Language Design Packet

For each component atom, write a design packet in natural language before code:

```text
1. Component name
   A short noun phrase. Example: RequestFrame Builder.

2. Why it exists
   The specific ambiguity, failure, or authority gap it removes.

3. Caller -> callee
   Who asks, who answers, and where the seam sits.

4. Input in plain English
   What the caller gives it, without pretending final code structure is known.

5. Output in plain English
   What the callee promises back.

6. Request envelope sketch
   Field names only when they carry contract meaning.

7. Response envelope sketch
   Field names only when they carry contract meaning.

8. Authority rule
   What this component may decide, and what it must not decide.

9. Prompt boundary
   What the LLM may see, what it sees by ref only, and what never crosses upward.

10. Failure semantics
    The expected non-happy paths and their typed outcomes.

11. Proof scenario
    The smallest concrete example that exercises the seam.

12. Negative proof
    One thing that must fail in a known way.

13. Open questions
    What we deliberately do not know yet.

14. POC notes
    What the first probe would need to observe, not the full production implementation.
```

##### Mind Map Shape

For confusing components, draw the natural-language mind map before writing schemas:

```text
ComponentAtom
  why
    what bug or uncertainty does it remove?
  owner
    who is allowed to decide here?
  input
    what facts arrive?
    what refs arrive?
    what context arrives?
  output
    what decision or artifact leaves?
    what proof leaves?
  authority
    what can it authorize?
    what can it only suggest?
    what must it never decide?
  prompt boundary
    visible summary
    refs only
    forbidden material
  failure
    missing input
    ambiguous input
    stale input
    policy blocked
    unsupported capability
    budget exhausted
  proof
    happy path
    negative path
    replay evidence
```

##### Anti-Hypothetical Rule

When a design sentence starts sounding like made-up implementation, rewrite it as a
contract sentence.

```text
Too hypothetical:
  The resolver will use a ResolverManager class that calls a PolicyService and stores
  candidate rows in a resolver_cache table.

Better pre-code design:
  The resolver must return a CandidateUniverse containing resources, omissions,
  exclusions, freshness, completeness, policy verdict, and binding refs. The first POC
  may keep this in memory; storage is an implementation decision until M3/M10 prove it.
```

```text
Too hypothetical:
  The PromptPack builder will trim tokens with a ranking algorithm.

Better pre-code design:
  PromptPack must expose allowed actions, uncertainty markers, omission summary, source
  refs, expiry, and redaction evidence. If candidates are elided, it must record counts,
  reasons, and inspect/refresh refs. The ranking method can evolve behind that contract.
```

##### Smallest-First Design Order

Design the smallest components in this order:

```text
1. Boundary atom
   What crosses from one owner to another?

2. Authority atom
   What decision is made at that boundary?

3. Evidence atom
   What proof records the decision?

4. Prompt atom
   What compact view, if any, reaches the model?

5. Failure atom
   What happens when the decision cannot be made?
```

Example for CC-0:

```text
Boundary atom:
  Front/FSM task payload -> BackTaskEnvelope.

Authority atom:
  FSM/Back pre-loop decides what task fields are preserved, promoted, or discarded.

Evidence atom:
  canonicalization_report records preserved/promoted/discarded fields and reasons.

Prompt atom:
  Back sees task summary and refs, not raw internal routing noise.

Failure atom:
  missing trace_id, actor_ref, safety_context, or grounding refs produces a conservative
  envelope diagnostic rather than silent field loss.
```

##### Promotion Rule For Pre-Code Designs

Pre-code designs have status levels:

```text
sketch
  natural-language packet only; useful for discussion, not production truth.

draft_contract
  request/response/failure/proof shapes are explicit enough for a POC.

poc_observed
  a targeted probe exercised the seam and produced ProofRecord / FailureEntry.

promoted_contract
  the whiteboard has been updated to match what the POC actually proved.
```

So designing before code is not guessing the future. It is writing the smallest possible
truth claim that code must later prove or falsify.

#### Component Design And POC Milestone Plan

This whiteboard is the canonical design surface, but no component becomes part of the main design only because it was written down. Each component milestone must prove the component with a small POC in the same milestone.

Milestone rule:

```text
one component or one boundary
  -> design draft on this whiteboard
  -> POC / probe / focused test
  -> failure capture
  -> iteration
  -> passing evidence
  -> promote final design back into this whiteboard
```

No design-only milestone:

```text
If a component has no POC proof, it remains a proposal.
If a POC fails, the failure is written down and the design is changed.
If the POC passes, the verified contract is promoted into the main component section.
```

Every component milestone must include these artifacts:

```text
1. Current-state read
   code paths, owners, existing schemas, prompt surfaces, event topics, and tests/probes.

2. Draft component contract
   request shape, response shape, invariants, failure semantics, security/prompt boundary,
   telemetry ids, migration compatibility, and example payloads.

3. POC scope
   the smallest runnable proof that exercises the real component seam.
   Prefer real code path probes over mocked-only assertions when possible.

4. Targeted test/probe command
   one explicit command or script for the milestone.
   Do not use broad suites as proof for a narrow component.

5. Failure log
   observed failure, root cause, whether the contract or implementation was wrong,
   and what changed before the next attempt.

6. Pass criteria
   exact observable conditions required before promotion.

7. Promotion patch
   update this whiteboard with the verified contract, diagrams, examples,
   limitations, migration notes, and remaining open decisions.
```

Standard component section template:

```text
Component name
  Design status: sketch | draft_contract | poc_observed | promoted_contract
  Owner
  Runtime boundary
  Component atom type: boundary | authority | evidence | prompt | failure
  Why it exists
  Current baseline
  Target contract
  Natural-language behavior
  Request schema
  Response schema
  Invariants
  Failure semantics
  Negative proof
  Prompt/security boundary
  Telemetry/audit ids
  Feature flag
  Shadow mode behavior
  Rollback behavior
  Compatibility adapter behavior
  POC scenario
  Targeted proof command
  Failure log
  Pass criteria
  Promotion notes
```

#### Kernel Role Projection For Component Contracts

Committee rule:

```text
Each CC milestone must be described twice:
  1. Kernel role boundary.
  2. Current FamilyOS implementation boundary.

The kernel boundary is the reusable design.
The FamilyOS boundary is the proof implementation.
If those two diverge, the milestone must say whether the generic contract or the
implementation adapter is being changed.
```

Projection map:

```text
CC-0 Front / FSM -> Back ReAct Runtime
  Kernel role boundary:
    Intent actor + state authority -> execution actor.
  FamilyOS implementation boundary:
    Front + Concierge FSM -> Back actor.
  Generic contract concern:
    Preserve task intent, actor scope, correlation, grounding refs, safety context,
    and canonicalization report before the execution actor frames the request.

CC-1 Back ReAct Runtime -> Fabric Situated Resolver
  Kernel role boundary:
    Execution actor -> situated resolution authority.
  FamilyOS implementation boundary:
    Back ToolDispatcher -> Fabric resolver.
  Generic contract concern:
    The execution actor asks for a faithful execution universe before choosing a
    capability, operation route, or side-effecting action.

CC-2 Resolver -> Local-World Resource Projection
  Kernel role boundary:
    Situated resolution authority -> resource projection authority.
  FamilyOS implementation boundary:
    Fabric resolver -> local-world projection from K1 stores, SessionState, Bridge,
    IFL, and optional K0 sync.
  Generic contract concern:
    Resolve concrete resources with freshness, completeness, omissions, exclusions,
    and scope proof.

CC-3 Resolver -> Policy / Guide Selector
  Kernel role boundary:
    Situated resolution authority -> governance authority.
  FamilyOS implementation boundary:
    Fabric resolver -> policy and guide selector.
  Generic contract concern:
    Produce roles, gates, HIL triggers, privacy rules, verifier duties, and compact
    guide cards without choosing provider-specific commands.

CC-4 Resolver -> Capability Contract Registry
  Kernel role boundary:
    Situated resolution authority -> capability contract authority.
  FamilyOS implementation boundary:
    Fabric resolver -> Fabric capability registry.
  Generic contract concern:
    Bind resource roles and operation intents to exact executable contracts, contract
    versions, schemas, verifier refs, and unbound-role diagnostics.

CC-5 Back ReAct Runtime -> Fabric Invocation Runtime
  Kernel role boundary:
    Execution actor -> invocation authority.
  FamilyOS implementation boundary:
    Back ToolDispatcher -> Fabric invocation runtime.
  Generic contract concern:
    Invoke only allowed bindings with schema-valid params, policy refs, expected effect,
    idempotency key, and normalized observation output.

CC-6 Fabric Invocation Runtime -> Bridge ConnectorGateway
  Kernel role boundary:
    Invocation authority -> connector gateway authority.
  FamilyOS implementation boundary:
    Fabric invocation runtime -> Bridge ConnectorGateway.
  Generic contract concern:
    Keep credentials, connector scopes, rate limits, circuit state, request signing, and
    gateway audit below the LLM prompt boundary.

CC-7 Bridge ConnectorGateway -> IFL Adapter Runtime
  Kernel role boundary:
    Connector gateway authority -> adapter runtime authority.
  FamilyOS implementation boundary:
    Bridge ConnectorGateway -> IFL adapter runtime.
  Generic contract concern:
    Translate normalized connector dispatch into provider protocol execution and return
    normalized status, readback, safe summaries, raw refs, and projection deltas.

CC-8 IFL Manifest -> Fabric Capability Registration
  Kernel role boundary:
    Domain or connector manifest -> capability contract authority.
  FamilyOS implementation boundary:
    IFL manifest translator -> Fabric capability registration.
  Generic contract concern:
    Preserve connector identity while generating resource models, capability contracts,
    provider routes, event contracts, guide refs, and registration diagnostics.

CC-9 Bridge / IFL Events -> Local-World Projection
  Kernel role boundary:
    Adapter event stream -> resource projection authority.
  FamilyOS implementation boundary:
    Bridge/IFL events -> local-world projection store.
  Generic contract concern:
    Apply resource deltas with versioning, freshness, availability, conflict handling,
    privacy filtering, and replayable proof.

CC-10 Back Prompt Injection Timing
  Kernel role boundary:
    Prompt assembly authority -> execution actor model context.
  FamilyOS implementation boundary:
    Back prompt builder and ReAct loop -> Back LLM request messages.
  Generic contract concern:
    Inject only phase-appropriate compact cards, observations, allowed actions, and
    recovery directives while enforcing forbidden actions outside the prompt text.
```

Committee open question for the ladder:

```text
OQ-CC-001: Should the kernel define a single abstract ExecutionActor, or separate
IntentActor, PlannerActor, and ExecutorActor interfaces?
  Working solution: define ExecutionActor as the authority-carrying runtime interface.
  IntentActor and PlannerActor may exist, but neither can bypass situated resolution.

OQ-CC-002: Should connector gateway and adapter runtime be separate kernel roles in
domains where the provider is local code, not an external service?
  Working solution: yes. Local providers may collapse the deployment, but the authority
  boundary remains useful for secrets, rate limits, audit, protocol normalization, and
  raw payload isolation.
```

Milestone order:

```text
M0 - Common proof harness and trace vocabulary
  Prove: a component POC can record request, response, trace_id, failure, and pass criteria.

M1 - CC-0 Front / FSM -> Back ReAct Runtime
  Prove: Front dispatch becomes a canonical BackTaskEnvelope / RequestFrame seed without losing grounding, referents, task id, trace id, or safety context.

M2 - CC-1 Back ReAct Runtime -> Fabric Situated Resolver
  Prove: Back can ask resolve_situation and receive ResolutionEnvelope + CandidateUniverse + PromptPack + allowed_next_actions before choosing a capability.

M3 - CC-2 Resolver -> Local-World Resource Projection
  Prove: a user-world reference such as "my car" or "Riley's calendar" returns complete scoped resource candidates with freshness and scope proof.

M4 - CC-3 Resolver -> Policy / Guide Selector
  Prove: policy returns roles, gates, HIL triggers, verifier requirements, and compact guide cards without choosing provider-specific commands.

M5 - CC-4 Resolver -> Capability Contract Registry
  Prove: resolved resources and policy roles bind to exact capability contracts, contract cards, verifier links, and unbound-role diagnostics.

M6 - CC-5 Back ReAct Runtime -> Fabric Invocation Runtime
  Prove: Back invokes through resolution_id + binding_id, Fabric validates params/policy, and returns normalized InvocationObservation / RecoveryDirective.

M7 - CC-6 Fabric Invocation Runtime -> Bridge ConnectorGateway
  Prove: Fabric dispatches through Bridge without exposing secrets, Bridge enforces connector scope/rate/circuit policy, and returns normalized connector observation.

M8 - CC-7 Bridge ConnectorGateway -> IFL Adapter Runtime
  Prove: Bridge sends IflCommandEnvelope, adapter returns IflResultEnvelope, and raw provider details stay behind refs.

M9 - CC-8 IFL Manifest -> Fabric Capability Registration
  Prove: an admitted manifest creates resource model contracts, capability contracts, provider routes, event contracts, and guide refs while preserving connector identity and rejecting untrusted executable registration.

M10 - CC-9 Bridge / IFL Events -> Local-World Projection
  Prove: resource projection deltas update freshness/version state and are visible to later resolution without a live connector call when fresh enough.

M11 - CC-10 Back Prompt Injection Timing
  Prove: PromptPack and observations are injected at the correct ReAct phase, with allowed/forbidden actions enforced and no raw catalogs/secrets in prompt.

M12 - End-to-end scenario gate
  Prove: one real household scenario crosses CC-0 through CC-10, fails at least one controlled recovery path during development, iterates, then passes with traceable evidence.
```

Promotion gate for every milestone:

```text
Design is promoted only when:
  POC passes.
  Failure log is updated, even if the final run passed.
  Targeted proof command is recorded.
  At least one relevant negative proof is recorded.
  Prompt/redaction checks pass when the milestone touches model-visible material.
  Protected-read and disclosure checks pass when the milestone touches sensitive data.
  Whiteboard contract reflects what actually passed.
  Remaining gaps are explicit and do not hide behind future implementation language.
```

The final design should therefore grow from proven slices:

```text
component proposal
  -> POC truth
  -> corrected component contract
  -> promoted whiteboard design
  -> next component
```

#### Component Ladder

```text
Front / Concierge FSM
  -> Back ReAct runtime
    -> Fabric situated resolver
      -> local-world resource projection
      -> policy / guide selector
      -> capability contract registry
    -> Fabric invocation runtime
      -> provider selector
      -> Bridge ConnectorGateway
        -> IFL adapter runtime
          -> external app / device / service
```

Runtime rule:

```text
Back may ask Fabric for situated resolution and bound invocation.
Back may not ask Bridge or IFL directly.

Fabric may ask Bridge to dispatch a connector operation.
Fabric may not own connector credentials or adapter protocol details.

Bridge may ask IFL adapters to execute/read/subscribe.
Bridge must not ask Back to interpret adapter protocol failures.

IFL adapters may talk to external services.
IFL adapters must return normalized observations and projection deltas.
```

End-to-end component sequence:

```text
Front/FSM        Back ReAct        Fabric Resolver        Fabric Invoke        Bridge Gateway        IFL Adapter        External App
  |                 |                   |                      |                   |                   |                  |
  | TaskEnvelope    |                   |                      |                   |                   |                  |
  |---------------->|                   |                      |                   |                   |                  |
  |                 | ResolveSituation  |                      |                   |                   |                  |
  |                 |------------------>|                      |                   |                   |                  |
  |                 |                   | read projection      |                   |                   |                  |
  |                 |                   | select policy/guides |                   |                   |                  |
  |                 |                   | bind capabilities    |                   |                   |                  |
  |                 | ResolutionEnvelope + PromptPack             |                   |                   |                  |
  |                 |<------------------|                      |                   |                   |                  |
  |                 | InvocationRequest |                      |                   |                   |                  |
  |                 |-------------------------------------------->|                   |                   |                  |
  |                 |                   |                      | ConnectorDispatch |                   |                  |
  |                 |                   |                      |------------------>|                   |                  |
  |                 |                   |                      |                   | IflCommand        |                  |
  |                 |                   |                      |                   |------------------>|                  |
  |                 |                   |                      |                   |                   | protocol call     |
  |                 |                   |                      |                   |                   |----------------->|
  |                 |                   |                      |                   |                   | result/readback   |
  |                 |                   |                      |                   |                   |<-----------------|
  |                 |                   |                      |                   | IflResult         |                  |
  |                 |                   |                      |                   |<------------------|                  |
  |                 |                   |                      | ConnectorObs      |                   |                  |
  |                 |                   |                      |<------------------|                   |                  |
  |                 | InvocationObservation / VerificationObservation          |                   |                  |
  |                 |<--------------------------------------------|                   |                   |                  |
  | SubmitResult    |                   |                      |                   |                   |                  |
  |<----------------|                   |                      |                   |                   |                  |
```

What never crosses upward into the prompt:

```text
connector secrets
OAuth/API tokens
raw provider stack traces
full manifests
full global capability catalog
unbounded connector payloads
```

What must cross upward as compact evidence:

```text
scope proof
candidate resources
binding ids
policy verdict
freshness verdict
allowed_next_actions[]
normalized invocation/verification observations
audit receipt refs
```

#### CC-0 - Front / FSM To Back ReAct Runtime

Purpose:

```text
Start or resume a Back execution loop from a Front-dispatched task.
```

Front/FSM asks Back:

```text
BackTaskEnvelope
  task_id
  session_id
  actor_ref
  user_goal
  task_kind
  dispatch_reason
  active_session_snapshot_ref
  temporal_snapshot_ref
  spatial_snapshot_ref
  grounding_snapshot_ref
  safety_context
  prior_task_state optional
  hil_response optional
  cancellation_or_modification optional
```

Back returns:

```text
BackTaskOutcome
  task_id
  status: completed | partial | needs_hil | cannot_execute | blocked | failed
  submit_result optional
  hil_request optional
  artifacts[]
  task_state_delta[]
  audit_fields
```

Rule:

```text
Back returns deltas/outcomes. Concierge remains Single Writer to SessionState.
```

#### CC-1 - Back ReAct Runtime To Fabric Situated Resolver

Purpose:

```text
Back asks for the execution universe before selecting a capability.
```

Back asks Fabric:

```text
ResolveSituationRequest
  request_frame
  actor_scope
  safety_context
  resolution_mode: execution
  freshness_policy
  prompt_budget
  previous_resolution_id optional
  required_outputs:
    candidate_universe
    prompt_pack
    allowed_next_actions
```

Fabric returns:

```text
ResolutionEnvelope
  resolution_id
  candidate_universe
  prompt_pack
  completeness
  freshness
  verdict
  allowed_next_actions[]
  diagnostics
```

Failure semantics:

```text
Fabric returns a conservative verdict, not an exception-shaped prompt puzzle.

Allowed non-executable verdicts:
  needs_disambiguation
  needs_confirmation
  missing_required_params
  blocked_by_policy
  missing_capability
  incomplete_world_projection
  stale_projection
  cannot_execute
```

Hard rule:

```text
Back must not use discover_capabilities top-K as execution authority when CC-1 is available.
```

#### CC-2 - Fabric Situated Resolver To Local-World Resource Projection

Purpose:

```text
Fabric needs concrete resources before binding capabilities.
```

Fabric asks projection:

```text
ResolveResourcesRequest
  trace_id
  actor_scope
  household_or_space_scope
  resource_references[]
  resource_kind_hints[]
  operation_hints[]
  connector_scope optional
  freshness_policy
  include_unavailable: true
```

Projection returns:

```text
ResourceUniverse
  projection_version
  projection_sources[]
  resources[]
  unavailable_resources[]
  ambiguous_references[]
  omissions[]
  exclusions[]
  freshness
  completeness
  scope_proof
```

Projection sources can include:

```text
Bridge / IFL adapter registry
Bridge connector health and credential state
K0 synced connector/resource state
K1 native family tool store
SessionState temporal/spatial/grounding context
recent connector event deltas
```

Rule:

```text
Resource resolution returns concrete resource candidates. It does not return invokable capability names as a substitute for resources.
```

#### CC-3 - Fabric Situated Resolver To Policy / Guide Selector

Purpose:

```text
Fabric asks which gates and compact guidance apply to this situation.
```

Fabric asks Plane 2:

```text
PolicySelectionRequest
  request_frame
  actor_scope
  resource_kinds[]
  operation_hints[]
  effect_hints[]
  safety_context
  known_freshness
  candidate_resource_refs[] optional
```

Policy selector returns:

```text
PolicyBundle
  required_roles[]
  gates[]
  hil_triggers[]
  verifier_requirements[]
  freshness_requirements[]
  privacy_requirements[]
  audit_requirements[]
  policy_cards[]
  guide_selection_rules[]
```

Rule:

```text
Policy selector returns role/gate requirements. It does not pick provider-specific connector commands.
```

#### CC-4 - Fabric Situated Resolver To Capability Contract Registry

Purpose:

```text
Fabric binds resolved resources and policy roles to exact executable capability contracts.
```

Fabric asks registry:

```text
BindingRequest
  request_frame
  resource_candidates[]
  required_roles[]
  operation_hints[]
  actor_scope
  safety_context
  authority_constraints[]
  freshness_constraints[]
```

Registry returns:

```text
BindingBundle
  binding_bundle_id
  bindings[]
  unbound_roles[]
  contract_cards[]
  guide_refs[]
  verifier_links[]
  binding_diagnostics[]
```

Rule:

```text
A binding is the only standard path from resolved resource to executable capability.
Back should invoke binding_id when available, not hand-copy provider names from prose.
```

#### CC-5 - Back ReAct Runtime To Fabric Invocation Runtime

Purpose:

```text
Back asks Fabric to execute only a bound and allowed capability.
```

Back asks Fabric:

```text
InvocationRequest
  resolution_id
  binding_id
  params
  idempotency_key
  actor_ref
  safety_context
  policy_gate_refs[]
  expected_effect
  verifier_requested
```

Fabric returns:

```text
InvocationObservation
  invocation_id
  binding_id
  status: success | partial | failed | denied | needs_hil | retryable
  provider_status
  result_summary
  structured_result
  artifacts[]
  verifier_obligation optional
  verification_observation optional
  recovery_directive optional
  audit_fields
```

Rules:

```text
Fabric validates params against the bound contract before provider dispatch.
Fabric enforces policy gate refs and safety requirements before side effects.
Fabric normalizes provider/Bridge errors before Back sees them.
Back receives observations, not raw connector stack traces.
```

#### CC-6 - Fabric Invocation Runtime To Bridge ConnectorGateway

Purpose:

```text
Fabric asks Bridge to dispatch a connector operation while Bridge owns connector security.
```

Fabric asks Bridge:

```text
ConnectorDispatchRequest
  trace_id
  invocation_id
  connector_id
  adapter_id
  resource_id
  capability_name
  operation
  params
  actor_ref
  actor_scope
  safety_context
  policy_gate_refs[]
  idempotency_key
  timeout_ms
  verifier_requested
```

Bridge must provide:

```text
credential lookup by handle, never prompt-visible secrets
connector authorization and scope checks
adapter lookup
rate limit and circuit breaker enforcement
request signing / token attachment
audit receipt
offline/queued/degraded behavior decision
normalized dispatch result
projection delta when resource state changes
```

Bridge returns:

```text
ConnectorDispatchObservation
  bridge_request_id
  status: success | partial | denied | unavailable | queued | failed | retryable
  connector_id
  adapter_id
  resource_id
  external_correlation_id optional
  normalized_result
  raw_result_ref optional
  projection_delta optional
  verifier_result optional
  retry_after optional
  audit_receipt
  error_code optional
  error_summary optional
```

Rules:

```text
Fabric never receives connector secrets.
Bridge never asks Back to choose credentials or adapter protocol paths.
Bridge may queue only when the capability contract and policy allow queued execution.
```

#### CC-7 - Bridge ConnectorGateway To IFL Adapter Runtime

Purpose:

```text
Bridge asks the adapter implementation to perform the connector-specific read/write/subscribe.
```

Bridge asks IFL adapter:

```text
IflCommandEnvelope
  ifl_schema_version
  trace_id
  bridge_request_id
  manifest_id
  connector_id
  adapter_id
  resource_ref
  action
  params
  auth_context_ref
  idempotency_key
  timeout_ms
  expected_effect
  readback_requested
```

IFL adapter returns:

```text
IflResultEnvelope
  ifl_schema_version
  trace_id
  bridge_request_id
  status: success | partial | denied | unavailable | queued | failed | retryable
  remote_status
  remote_correlation_id optional
  normalized_payload
  raw_payload_ref optional
  resource_state_delta optional
  readback_payload optional
  error_code optional
  error_summary optional
  retry_after optional
```

Rules:

```text
IFL adapter speaks app/device/service protocol.
Bridge receives normalized IFL envelopes.
Fabric receives Bridge observations.
Back receives Fabric observations.
```

#### CC-8 - IFL Manifest To Fabric Capability Registration

Purpose:

```text
Connector manifests must become Fabric-readable capability contracts and resource models.
```

ManifestTranslator consumes:

```text
IflManifest
  manifest_id
  connector_id
  adapter_id
  signing_info
  resource_models[]
  capability_templates[]
  event_topics[]
  auth_scopes[]
  safety_metadata
  verifier_affordances[]
  freshness_guarantees
```

ManifestTranslator emits:

```text
CapabilityRegistrationBatch
  capability_contracts[]
  resource_model_contracts[]
  event_contracts[]
  provider_routes[]
  guide_refs[]
  registration_diagnostics[]
```

Rules:

```text
Capability registration preserves connector identity.
Resource model registration preserves concrete resource identity fields.
Prompt/activity guide cards are tagged as guidance, not executable capabilities.
```

#### CC-9 - Bridge / IFL Events To Local-World Projection

Purpose:

```text
Resource freshness and availability should update outside the immediate tool call path.
```

Bridge/IFL emits:

```text
ResourceProjectionDelta
  trace_id optional
  connector_id
  adapter_id
  resource_id
  event_topic
  observed_at
  freshness_state
  state_patch
  availability
  credential_state optional
  source_receipt
```

Projection returns or stores:

```text
ProjectionApplyObservation
  projection_version
  accepted
  rejected_fields[]
  conflict_resolution
  freshness
```

Rule:

```text
Plane 4 resolution should prefer this projection over live connector probing when it is fresh enough for the requested effect class.
```

#### CC-10 - Back Prompt Injection Timing Contract

Purpose:

```text
Define what Back prompt asks for, and what runtime observations are injected at each ReAct phase.
```

Prompt injection envelope:

```text
PromptInjectionEnvelope
  injection_id
  task_id
  react_iteration
  phase
  source_refs[]
  compact_cards[]
  observations[]
  allowed_tool_calls[]
  forbidden_tool_calls[]
  max_next_tool_calls
  expires_at optional
```

Injection schedule:

```text
Phase: loop_start
  Inject:
    stable Back executor role
    Back meta-tool declarations
    task envelope summary
    current SessionState task snapshot
    execution grounding block
  Execution actor should ask:
    build RequestFrame, then resolve_situation for execution tasks

Phase: after_request_frame
  Inject:
    compact RequestFrame
    known missing fields
    allowed resolver modes
  Execution actor should ask:
    resolve_situation unless the task is already impossible or purely memory-only

Phase: after_resolution
  Inject:
    PromptPack
    CandidateUniverse summary
    allowed next actions
    policy cards
    guide cards
    contract cards
    HIL options if needed
  Execution actor should ask:
    invoke bound read/write, ask HIL, block, or submit cannot_execute

Phase: after_invocation
  Inject:
    InvocationObservation
    VerificationObservation if available
    recovery directive
    updated allowed next actions
  Execution actor should ask:
    verify, retry if allowed, ask HIL if required, or submit_result

Phase: after_hil_response
  Inject:
    HILResponse
    prior resolution_id
    changed user constraints
  Execution actor should ask:
    resolve_situation again with previous_resolution_id, or invoke if the prior envelope explicitly remains valid

Phase: final_iteration
  Inject:
    termination requirement
    submit_result schema
    unresolved obligations
  Execution actor should ask:
    submit_result with completed, partial, blocked, failed, or cannot_execute
```

Prompt timing diagram:

```text
          static prompt
               |
               v
       +----------------+
       | loop_start     |
       | task + state   |
       +-------+--------+
               |
               v
       Back builds RequestFrame
               |
               v
             +----------------------+
             | after_request_frame  |
             | compact frame        |
             +----------+-----------+
               |
               v
       Back calls resolve_situation
               |
               v
             +----------------------+
             | after_resolution     |
             | PromptPack           |
             | candidates           |
             | policies             |
             | bindings             |
             +----------+-----------+
               |
     +---------+----------+
     |                    |
     v                    v
 invoke/read/write     ask HIL/block
     |                    |
     v                    v
+------------+      +--------------+
| after_inv  |      | after_hil    |
| obs+verify |      | answer+delta |
+-----+------+      +------+-------+
      |                    |
      +----------+---------+
                 |
                 v
          +-------------+
          | final_iter  |
          | submit only |
          +-------------+
```

Prompt ownership map:

```text
Static Back prompt owns:
  executor identity, hard prohibitions, meta-tool rules, submit_result duty.

PromptInjectionEnvelope owns:
  current task state, current resolver output, current allowed actions,
  compact policy/guide/contract cards, and observation summaries.

Tool observations own:
  exact runtime results, normalized errors, recovery directives, verification results.

SessionState owns:
  durable conversation/task state. Back reads snapshots but does not write directly.
```

Rules:

```text
The static Back system prompt stays small and stable.
Dynamic execution truth enters through PromptInjectionEnvelope and tool observations.
PromptPack is injected only after situated resolution.
Guide cards are injected only when their capability/resource binding is relevant.
Full registries and manifests are never dumped into the prompt.
Every injected card carries an id/version/ref so runtime can audit what Back saw.
```

#### Component Contract Acceptance Checklist

Every runtime component contract must define:

```text
caller
callee
request envelope
response envelope
required ids: trace_id, task_id, actor_ref when applicable
authority context
safety context
freshness semantics
retry/idempotency semantics
HIL escalation semantics
audit fields
normalized error codes
prompt injection effect, if any
```

No component contract is complete until it answers:

```text
What can the caller safely do next?
What must the caller never infer?
What evidence proves the callee considered the correct scope?
What gets hidden from the LLM for safety/scale?
What compact observation gets shown to the LLM for decision-making?
```

### Plane 1 - Proposed Execution Actor Loop Standard

Back is a governed Tier-2 executor, not a general chat responder and not the Tier-3 planner. It should run a bounded ReAct loop over deterministic observations from the other planes. Tier-3 tasks use Planner and Orchestrator: Planner commits the PlanGraph, Orchestrator executes deterministic dependency waves, and Back does not improvise that plan in prompt text.

Tier 2 Back loop:

```text
0. Receive task envelope from Front/FSM
1. Build RequestFrame
2. Resolve situation through Plane 4 using staged connector disclosure
3. Read CandidateUniverse + PromptPack
4. Commit selected tools/bindings when required
5. Receive selected schemas only
6. Invoke read/write, ask HIL, ask for missing fields, block, or submit
7. Verify result when required
8. Submit result back to Front/FSM
```

Tier 3 loop boundary:

```text
0. FSM routes HIGH / cross-resource task
1. Planner SKETCH/EXPAND/VALIDATE/COMMIT produces PlanGraph
2. Orchestrator executes committed DAG waves through Fabric
3. Reads and protected reads complete before dependent writes
4. Conditional evaluation, HIL, compensation, verification, and aggregation run deterministically
5. FSM/Front receive task outcome or HIL prompt
```

ASCII execution flow:

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
call resolve_situation(task_frame)
               |
               v
+-----------------------------+
| CandidateUniverse            |
| - request_frame              |
| - resource_candidates        |
| - capability_bindings        |
| - completeness/freshness     |
| - policy verdict             |
| - guides/contracts           |
+--------------+--------------+
               |
               v
        ReAct step 2
               |
   +-----------+------------+-------------+
   |                        |             |
   v                        v             v
invoke/read/write      ask HIL       block/submit issue
   |
   v
verify if required
   |
   v
submit_result
```

Hop budget:

```text
Normal path:
  LLM Hop 1 - frame + call resolver
  Tool Phase A - deterministic resolve/provision
  LLM Hop 2 - decide + act/ask/block
  Tool Phase B - deterministic execute/verify where allowed
  LLM Hop 3 - submit

Hard max:
  LLM Hop 4 only for HIL resume, repair, post-read conflict, or verification failure.
```

Not acceptable:

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

That would make ordinary household actions too slow. Internal states may exist, but they must be grouped into few LLM hops.

Prompt assembly should be layered:

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
           | Policy/Guide/       |
           | Contract cards      |
           +----------+----------+
                      |
           +----------v----------+
           | Expected output     |
           +---------------------+
```

Plane 1 non-negotiables:

```text
Do not invent resources.
Do not infer authority by vibes.
Do not mutate before required policy gates pass.
Do not choose a tool from top-K when completeness is unknown.
Do not ask biased HIL from an incomplete candidate universe.
Do not submit success before authority execution and verification obligations are handled.
Do not keep a Tier 3 task inside Back when companion_resource roles or dependency edges are present.
```

### Plane 2 - Proposed Governance And Guide-Card Standard

Plane 2 is not a library of giant workflows. It is a composable set of policy and guide cards.
Connector/capability constitutions live here as versioned policy/guide material that can be rendered into PromptPack cards.

Distinction:

```text
Constitution / policy:
  What must be true before this class of action is allowed?
  What reads are mandatory before writes?
  What ambiguity requires HIL?
  What side effects require confirmation, audit, privacy projection, or verification?

Tool/activity guide:
  How does this bound tool or adapter work correctly?
  What params does it require?
  What read-before-write or read-after-write pattern does it support?
  What adapter quirks, limitations, and examples should Back know?
```

No-permutation rule:

```text
Do not create:
  calendar+tasks+reminders constitution
  calendar+tasks+reminders+chores constitution
  calendar+tasks+health+car+Hue constitution

Do create:
  global_back_execution_policy
  time_bound_commitment_policy
  family_visibility_policy
  conflict_check_policy
  health_privacy_policy
  financial_transfer_policy
  adapter/domain guides for bound tools only
```

Composable shape:

```text
global Back constitution
  -> task-class policy
       -> domain policy
            -> bound tool/activity guide
                 -> provider/runtime policy
```

Policy and guide card flow:

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

Minimal card shapes:

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
  disclosure_phase
  how_to_call
  param construction notes
  read-before-write sequence
  read-after-write verifier
  limitations
  examples
```

Example:

```text
RequestFrame:
  operation: commitment.time_bound.create

PolicyCard:
  required_roles: temporal_resolver, participant_resolver, conflict_readers, writer, verifier
  companion_resource_roles: participants, conflict_subjects, guardians
  gate: check_conflicts_before_write

Bound GuideCards:
  calendar_activity_v1
  tasks_activity_v1
  reminders_activity_v1
```

### Plane 3 - Proposed Tool Contract Standard

Every executable capability must be bindable, governable, invokable, and verifiable without Back guessing from prose.

Minimum contract shape:

```text
ToolContract
  name
  provider / adapter id
  operation
  resource_kind
  resource_instance_binding
  connector_constitution_ref
  input_schema
  output_schema
  schema_disclosure_phase
  side_effects
  safety_band / risk metadata
  permissions
  freshness requirements
  verifier capability
  guide ids
  policy hooks
  errors
  limitations
```

Human-readable contract card:

```text
+------------------------------------+
| tool.execute.calendar.create_event |
+------------------------------------+
| operation: commitment.create        |
| resource_kind: calendar.event_store |
| input: title, start, end, attendees |
| effect: writes time-bound event     |
| safety: GREEN/MEDIUM by context     |
| verifier: calendar.get_event        |
| guide: calendar_activity_v1         |
+------------------------------------+
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

Contract requirements for IFL-scale adapters:

```text
Must expose resource model, not only action text.
Must expose supported operations by resource kind or resource instance.
Must expose readback/verifier path when side effects are claimed.
Must expose authority/permission requirements in machine-readable form.
Must expose freshness/offline/degraded semantics.
Must distinguish executable capability from guide/profile/workflow/catalog record.
Must expose connector/capability constitution refs for preconditions, companion resources, HIL, and verification.
```

### Plane 4 - Proposed Situated Resolution And Provisioning Standard

Plane 4 is the replacement center of gravity for execution resolution.

Old center:

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

New center:

```text
User text
   |
   v
tier decision + situation frame
   |
   v
connector constitution staging
  |
  v
resource universe + impact set
   |
   v
operation binding
   |
   v
policy / HIL / freshness verdict
   |
   v
execution actor acts, asks, blocks, or escalates by tier
```

Resolver flow:

```text
request_frame
  -> tier ownership check
  -> policy role requirements
  -> connector constitution selection
  -> local world/resource resolution
  -> impact set and companion_resource expansion
  -> operation/affordance binding
  -> authority/privacy/freshness checks
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

Runtime indexes needed:

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

Human map for resource-first resolution:

```text
                       +-------------------------+
                       | User request            |
                       | "warm up my car"        |
                       +-----------+-------------+
                                   |
                                   v
                       +-------------------------+
                       | Situation frame         |
                       | actor, refs, operation  |
                       +-----------+-------------+
                                   |
                 +-----------------+-----------------+
                 |                 |                 |
                 v                 v                 v
       +------------------+ +------------------+ +------------------+
       | Resource index   | | Authority index  | | Freshness index  |
       | my car -> cars   | | can Alex act?    | | is view fresh?   |
       +--------+---------+ +--------+---------+ +--------+---------+
                |                    |                    |
                +--------------------+--------------------+
                                     |
                                     v
                       +-------------------------+
                       | Candidate resources     |
                       | Tesla, Audi             |
                       +-----------+-------------+
                                   |
                                   v
                       +-------------------------+
                       | Affordance index        |
                       | climate.start bindings  |
                       +-----------+-------------+
                                   |
                                   v
                       +-------------------------+
                       | CandidateUniverse       |
                       | verdict: ask user       |
                       +-------------------------+
```

### Runtime Artifact - CandidateUniverse

The execution tier should receive a structured universe, not a naked ranked list.

This is a prompt/runtime summary of Contract F, not a second schema.

Shape:

```text
CandidateUniverse
  resolution_id
  request_frame
  scope_proof
  connector_candidates[]
  resource_candidates[]
  impact_set_candidates[]
  companion_resource_roles[]
  cross_resource_read_requirements[]
  capability_bindings[]
  plan_graph_ref optional
  completeness
  freshness
  omissions / exclusions
  policy_verdict
  required_guides
  required_contracts
  allowed_next_actions[]
```

Example:

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

The important field is not `score`. The important field is `scope_proof`, plus omissions and uncertainty.

### Runtime Artifact - PromptPack

PromptPack is the prompt-sized subset the execution actor needs for the next step.

This is a prompt/runtime summary of Contract G, not a second schema.

Shape:

```text
PromptPack
  candidate universe summary
  connector constitution cards
  tool name cards
  compact PolicyCards
  selected GuideCards
  selected ToolContracts
  selected schemas only after binding/selection
  HIL/confirmation wording constraints
  allowed_tool_calls[] for this state
  allowed_next_actions[] summary
```

Rule:

```text
Do not dump the entire catalog into Back.
Inject only what the current ReAct state needs.
At connector_summary phase, do not inject full schemas.
At schema_binding phase, inject schemas only for selected/bound tools.
```

### Proposed Meta-Tool Direction

Current collapsed tool:

```text
discover_capabilities(intent, domain)
```

Candidate future surface:

```text
resolve_situation(task_frame)
  -> tier-aware CandidateUniverse + staged PromptPack

inspect_binding(binding_id)
  -> exact schema, guide, policy, verifier, limitations

invoke_capability(binding_id or capability_name, params)
  -> deterministic execution through Fabric/Bridge/provider

batch_invoke_capabilities(bindings, params_by_binding)
  -> deterministic parallel read/batch execution where policy allows

submit_result(...)
  -> final Back/FSM result
```

Internal decomposition can exist without forcing Back to call every step manually:

```text
resolve_request_frame
resolve_resources
bind_capabilities
select_policy_guides
build_prompt_pack
```

Guideline:

```text
Tier 2 Back should see one high-level resolver when possible.
The runtime can decompose resolution deterministically inside Plane 4.
Planner/Orchestrator may consume the same resolver output for Tier 3 instead of routing it through Back.
```

### Catalog Retrieval Vs Execution Resolution

Today `discover_capabilities` is doing too much. Split the concept:

```text
Catalog Retrieval
  Search a large tool/prompt/adapter catalog.
  Optimized for recall/relevance.
  Top-K is acceptable.
  Use for marketplace, docs, development, missing-capability suggestions.

Execution Resolution
  Resolve a user action against the actor's current world.
  Optimized for completeness, authority, freshness, policy, and auditability.
  Top-K is not acceptable as authority.
  Use for Back side-effecting and resource-bound execution.
```

100k tools rule:

```text
Do not search 100k global tools for ordinary execution.
Resolve the actor's local world projection first.
Use the global catalog second for install/suggestion/docs/fallback.
```

### Scenario Gates

Every proposed model must pass these gates before implementation is accepted.

```text
Scenario 1 - Scheduling hidden conflicts
  User: Schedule Riley's dentist appointment Monday at 3.
  Reality: calendar, chores, homework/tasks, school events, and caregiver constraints may matter.
  Expected: Tier 3 route; connector constitution declares companion_resource roles;
  Planner expands prerequisite reads; Orchestrator gates calendar write behind conflict reads.

Scenario 2 - Living room lights across systems
  User: Turn off the living room lights.
  Reality: Hue and Matter resources are in the same room.
  Expected: all in-scope living-room light resources are surfaced or projection is partial.

Scenario 3 - Health privacy
  User: How did Riley sleep last night?
  Reality: Fitbit and Apple Health may both exist; consent may be required.
  Expected: privacy/authority gate before disclosure; complete candidate sources if allowed.

Scenario 4 - Payment / finance
  User: Pay the tutor.
  Reality: payer account, recipient identity, amount, rail, fraud, and confirmation matter.
  Expected: identity and confirmation policy before transfer.

Scenario 5 - Two cars
  User: Turn on climate control of my car.
  Reality: Tesla and Audi are both connected and controllable.
  Expected: both resources appear or resolver reports incomplete projection.

Scenario 6 - Missing capability
  User: Start the sprinklers.
  Reality: no irrigation adapter connected; marketplace has one.
  Expected: local execution says no connected capability; global catalog suggestion is separate.
```

Two-car test is only one gate:

```text
If a model can return Tesla while silently omitting Audi, it fails.
Passing the car test alone is not enough.
```

#### Cross-Domain Scenario Analogues

These analogues make the gates kernel-shaped instead of FamilyOS-shaped. They are not a
replacement for the household fixtures; they are pressure tests for the same contracts in
other domains.

```text
Kernel gate class A - time-bound system-of-record mutation with prerequisite reads

FamilyOS fixture:
  Schedule Riley's dentist appointment Monday at 3.

Enterprise IT analogue:
  Schedule the production search deploy Monday at 3.
  Reality: change window, service freeze, on-call coverage, incident state, and rollback
  runbook may matter.
  Expected: resolver derives prerequisite reads before creating the change record or
  deployment task; policy may require approval or a different window.

Clinical operations analogue:
  Schedule the patient follow-up next Monday afternoon.
  Reality: clinician availability, clinic location, patient consent/contact rules, referral
  status, and insurance authorization may matter.
  Expected: protected scheduling policy and availability reads precede write; missing
  details produce HIL instead of a guessed appointment.
```

```text
Kernel gate class B - protected read / disclosure side effect

FamilyOS fixture:
  How did Riley sleep last night?

Finance analogue:
  Show me the client's available cash and recent transfers.
  Reality: account visibility, advisory role, customer consent, data classification, and
  audit retention matter.
  Expected: protected-read gate before model or user disclosure; raw transactions stay
  behind refs unless policy allows compact summaries.

Enterprise HR analogue:
  Show me this employee's compensation history.
  Reality: manager role, HR policy, jurisdiction, and audit requirements matter.
  Expected: disclosure gate may block, ask for justification, or return a redacted summary.
```

```text
Kernel gate class C - partial projection across multiple providers

FamilyOS fixture:
  Turn off the living room lights.

Enterprise IT analogue:
  Restart all API workers in the checkout service.
  Reality: Kubernetes pods, legacy VMs, autoscaling groups, and regional failover workers
  may all be in scope.
  Expected: all in-scope worker resources are surfaced or projection is explicitly partial;
  resolver must not restart only the first provider it found.

Robotics/facilities analogue:
  Lock all loading dock doors.
  Reality: badge system, smart locks, offline doors, and manual override status may differ.
  Expected: unavailable/offline doors are visible as omissions or unavailable resources;
  HIL or cannot_execute discloses incomplete projection.
```

```text
Kernel gate class D - missing capability with catalog suggestion separated from execution

FamilyOS fixture:
  Start the sprinklers.

Enterprise IT analogue:
  Rotate the vendor API key in AcmeCRM.
  Reality: AcmeCRM connector is not installed, but a marketplace adapter exists.
  Expected: local execution returns missing_capability; catalog suggestion is separate and
  cannot execute the rotation.

Education analogue:
  Send the official transcript to the scholarship portal.
  Reality: student record system is connected, but scholarship portal connector is absent.
  Expected: resolver can read local eligibility only if policy allows; submission action is
  missing_capability with install/request workflow separate from execution.
```

```text
Kernel gate class E - ambiguous resource selection with multiple valid bindings

FamilyOS fixture:
  Turn on climate control of my car.

Enterprise IT analogue:
  Restart the API service.
  Reality: staging, canary, and production API services are all visible to the actor.
  Expected: CandidateUniverse shows all valid resources and asks disambiguation or applies
  a policy-approved default only when the default is explicit and auditable.

Finance analogue:
  Move cash to the reserve account.
  Reality: multiple reserve accounts and rails are available.
  Expected: HIL choices come from CandidateUniverse; no transfer happens from a ranked guess.
```

```text
Kernel gate class F - policy confirmation before irreversible or high-blast-radius action

FamilyOS fixture:
  Pay the tutor.

Enterprise IT analogue:
  Roll back production to the previous release.
  Reality: blast radius, active incident, approval policy, and rollback verifier matter.
  Expected: policy confirmation and verifier obligations are explicit before mutation.

Legal operations analogue:
  File this contract with the counterparty.
  Reality: final approval, privileged content, filing destination, and version identity matter.
  Expected: policy verifies approved final document and asks confirmation before external send.
```

Scenario gate promotion rule:

```text
FamilyOS M12 proves the first concrete fixture pack.
Generic-kernel status requires at least two non-household analogue fixtures to be drafted
with request frame, candidate universe expectation, policy expectation, binding expectation,
expected non-action path, and proof assertions.
```

### Candidate Model Judgment

```text
Model A - Tune semantic top-K harder
  Status: supporting primitive only.
  Rejected as the main execution discovery model.

Model B - Resource-first situated resolution
  Status: strong candidate for side-effecting/resource-bound execution.
  Needs resource projection ownership and manifest requirements.

Model C - Capability-first with expansion
  Status: possible migration bridge.
  Not sufficient unless backed by resource/affordance indexes.

Model D - Policy-first role binding
  Status: required for governance.
  Must compose with resource resolution, not replace it.

Model E - Local world first, global catalog second
  Status: likely non-negotiable principle.
  Needs local projection freshness and sync semantics.

Model F - LLM proposes, runtime verifies completeness
  Status: useful interaction pattern.
  Not a replacement for deterministic candidate enumeration.
```

Current lean:

```text
Execution path:
  local world projection first
  connector constitution first
  resource-first candidate enumeration
  impact-set expansion for companion resources
  capability binding second
  policy/guidance attached before execution
  schema disclosure only after selected binding
  ranking only after completeness

Supporting path:
  semantic/vector search for fuzzy parse help, docs, marketplace, and low-risk exploration
```

### Phased Implementation Direction

This is the proposed order of design and implementation work. Exact schemas can still evolve, but each phase must preserve the vocabulary, ownership, authority, freshness, prompt-injection, and audit rules defined above.

```text
Phase 0 - Keep current Back/Fabric path alive
  Preserve meta-tool spine: discover/invoke/batch/submit.
  Keep probes and issue register as regression truth.

Phase 1 - Bind tier routing to authority
  Make LOW/MEDIUM/HIGH routing explicit in RequestFrame/ResolutionEnvelope.
  Ensure family-impacting and cross-resource tasks route to Planner/Orchestrator.

Phase 2 - Add connector/capability constitutions
  Add preconditions, companion_resource roles, verifier duties, HIL triggers,
  and schema disclosure phase to connector/capability contract material.

Phase 3 - Separate record kinds
  Mark executable capability vs guide/profile/workflow/catalog record.
  Ensure Back execution discovery can request executable/bindable records only.

Phase 4 - Define core artifacts
  RequestFrame
  CandidateUniverse
  PromptPack
  PolicyCard
  GuideCard
  ToolContract
  BindingContract

Phase 5 - Add resource/affordance metadata
  Add resource_kind, operation, resource binding, verifier, policy hooks,
  freshness, authority, and guide ids to executable contracts and manifests.

Phase 6 - Prototype Plane 4 resolver
  Start with local K1 family tools and connected-resource projection shape.
  Return CandidateUniverse for scheduling, lights, health, car, and missing capability scenarios.

Phase 7 - Wire Back loop to resolver output for Tier 2
  Add resolve_situation or prepare_execution as the execution authority.
  Inject PromptPack by ReAct state and disclosure phase.
  Keep LLM hop budget to 3 normal / 4 hard max.

Phase 8 - Wire Planner/Orchestrator to resolver output for Tier 3
  Feed connector constitutions and cross-resource read requirements into PlanGraph EXPAND.
  Execute prerequisite reads and writes through Orchestrator DAG waves.

Phase 9 - Harden execution and verification
  Enforce policy/HIL gates.
  Verify writes where contract requires it.
  Record omissions, exclusions, freshness, and scope proof.

Phase 10 - Demote global discovery to catalog retrieval
  Keep semantic/vector search for docs, marketplace, suggestions, and development.
  Do not use top-K as side-effect execution authority.
```

#### Runtime Migration Control Plane

Every implementation slice must declare its operational controls before it can promote
from proposal to proven design.

```text
Required per seam:
  feature_flag
  default state
  shadow mode behavior
  fallback path
  rollback command or config path
  legacy comparison fields
  proof command
  failure log location
  prompt capture behavior if model-visible
  redaction scan behavior if sensitive
```

Feature flag spine:

```text
CC-TIER route authority flag
  Enables explicit Tier 1/2/3 route ownership before execution authority.
  Fallback: current TaskDispatch tier heuristic, with cross-resource tasks conservatively routed HIGH or cannot_execute.

CC-0 envelope canonicalization flag
  Enables BackTaskEnvelope / RequestFrame seed emission.
  Fallback: current TaskDispatch canonical payload.

CC-1 resolver tool flag
  Enables resolve_situation before capability choice.
  Fallback: discover_capabilities catalog retrieval and legacy invoke path.

CC-1A connector constitution flag
  Enables connector/capability constitution cards and schema disclosure phase.
  Fallback: current tool_instructions/limitations treated as guidance only, not authority.

CC-2 projection resolver flag
  Enables ResourceUniverse from joined local-world projection.
  Fallback: native-family-only resource assumptions or cannot_execute for external resources.

CC-3 policy bundle flag
  Enables PolicyBundle roles, protected-read gates, redaction requirements, and guide selection.
  Fallback: current safety/context policies plus conservative protected-read blocking.

CC-4 binding bundle flag
  Enables binding_id authority.
  Fallback: capability_name compatibility only for proven native tools.

CC-5 invocation observation flag
  Enables InvocationObservation / RecoveryDirective normalization.
  Fallback: legacy ToolResult with compatibility wrapper and conservative submit behavior.

CC-5A Tier-3 PlanGraph execution flag
  Enables Planner committed PlanGraph -> Orchestrator DAG execution for family-impacting/cross-resource tasks.
  Fallback: do not collapse Tier 3 into Back; return needs_planner_or_cannot_execute.

CC-6 bridge gateway dispatch flag
  Enables connector dispatch through Bridge security boundary.
  Fallback: no external side effect; return missing_capability or unavailable.

CC-7 IFL command envelope flag
  Enables normalized adapter command/result envelope.
  Fallback: connector disabled for authority execution.

CC-8 manifest registration flag
  Enables connector manifest to capability/resource/event registration.
  Fallback: manifest visible only as catalog/doc suggestion, not executable authority.

CC-9 projection delta flag
  Enables event-driven resource freshness updates.
  Fallback: projection stale/unknown, forcing refresh/HIL/block by policy.

CC-10 prompt injection flag
  Enables phase-specific PromptInjectionEnvelope and allowed/forbidden action enforcement.
  Fallback: static Back prompt plus legacy tool observations, with resolver authority disabled.

CC-10 governs timing and injection behavior, not PromptPack schema ownership.
PromptPack schema ownership remains Contract G.
```

Shadow comparison record:

```text
ShadowComparisonRecord
  trace_id
  task_id
  scenario_id
  legacy_path_result_ref
  resolver_path_result_ref
  request_frame_hash
  candidate_universe_diff
  policy_verdict_diff
  binding_diff
  allowed_action_diff
  prompt_redaction_diff
  invocation_param_diff
  submit_status_diff
  user_summary_diff
  recommended_cutover: yes | no | blocked
  blocker_codes[]
```

Cutover rule:

```text
No new seam becomes authority because it works once.
It becomes authority only after targeted proof, negative proof, shadow comparison, rollback
verification, and whiteboard promotion all agree.
```

### Evaluation Criteria

Use these as acceptance criteria for the proposed design.

```text
Candidate completeness
  all materially relevant in-scope candidates appear, or incompleteness is explicit

Resource identity correctness
  concrete resources are distinct from tools, providers, and adapters

Authority and privacy correctness
  actor visibility/permission is checked before HIL or execution

Protected-read correctness
  sensitive read results are gated before model or user disclosure

Prompt boundary correctness
  raw catalogs, secrets, full manifests, raw provider payloads, and stack traces are absent from prompt captures

Freshness and offline behavior
  projection state is fresh/stale/offline/partial and visible to Back

Policy composition
  reusable policies compose without per-combination constitutions

Contract exactness
  Back receives exact invokable names, schemas, errors, verifier, and limits

Scale
  ordinary execution uses local world projection, not global 100k-tool search

Auditability
  runtime can explain considered candidates, exclusions, omissions, and verdict

Replayability
  proof records reconstruct what the model saw, what was omitted, what was forbidden, and why an action was legal or blocked

Negative proof coverage
  relevant forbidden actions, stale projections, missing bindings, and redaction failures are tested before promotion

HIL quality
  user is asked about the real ambiguity, not a biased top-ranked guess

Migration cost
  new resolver can coexist with existing Fabric invocation while discovery is refactored

Runtime cutover correctness
  feature flags, shadow comparison, rollback behavior, and compatibility adapters are proven before authority cutover
```

### Kernel / Implementation Open Decision Register

Use this register to keep committee deliberations honest. Do not mix a reusable kernel
decision with a FamilyOS proof-domain implementation detail.

```text
KERNEL decisions
  Affect every domain instantiation unless explicitly versioned otherwise.
  Examples: authority chain, envelope fields, prompt boundary, protected reads,
  binding before side effects, replay proof, and versioning rules.

IMPLEMENTATION decisions
  Affect the current FamilyOS proof path or a specific runtime adapter.
  Examples: K1 storage layout, Concierge FSM canonicalization internals,
  native family tool names, probe scripts, and feature flags.

CROSS-DOMAIN decisions
  Begin as patterns observed in one domain, then require at least one non-household
  analogue before promotion to kernel law.
```

Current decision register:

```text
KD-001 Authority chain
  Class: KERNEL
  Question: Is request_frame -> resolution -> policy -> binding -> invocation -> observation mandatory?
  Working decision: yes for side effects and protected reads.
  Promotion condition: M12 proves at least one side-effect path and one protected-read path.

KD-002 Prompt boundary
  Class: KERNEL
  Question: Are raw catalogs, secrets, full manifests, and provider payloads ever prompt-visible?
  Working decision: no; only compact cards, refs, safe summaries, and redaction evidence cross.
  Promotion condition: M11 and M12 include prompt capture redaction proof.

KD-003 Candidate completeness before ranking
  Class: KERNEL
  Question: Can ranking decide the candidate universe?
  Working decision: no; ranking can order already-complete candidates for display.
  Promotion condition: M3 and M12 prove omissions/exclusions for incomplete projection cases.

KD-004 DomainInstantiationPack minimum
  Class: KERNEL
  Question: What must a domain provide before execution authority is enabled?
  Working decision: resource kinds, operation taxonomy, policies, guides, manifests,
  verifiers, data classification rules, HIL templates, and scenario gates.
  Promotion condition: first FamilyOS pack plus one non-household analogue draft.

ID-001 FamilyOS native capability compatibility
  Class: IMPLEMENTATION
  Question: How long do tool.execute.calendar.create_event style native names remain valid?
  Working decision: keep compatibility until resolver-by-binding path is shadowed and proven.
  Promotion condition: M6 and M12 prove binding_id invocation while legacy invoke still works.

ID-002 K1 projection persistence
  Class: IMPLEMENTATION
  Question: Which store owns concrete resource projection versions in the first proof path?
  Working decision: unresolved; M3/M10 must propose the minimal store shape.
  Promotion condition: projection deltas update version/freshness and later resolution reads them.

ID-003 Concierge canonicalization report
  Class: IMPLEMENTATION
  Question: Where is the canonicalization report produced: FSM, Back pre-loop, or shared utility?
  Working decision: unresolved; CC-0 proof should choose the smallest additive seam.
  Promotion condition: M1 proves no task/correlation/grounding/safety loss.

XD-001 Non-household scenario analogues
  Class: CROSS-DOMAIN
  Question: Which M12 scenarios prove the kernel is not household-only?
  Working decision: draft analogues for scheduling/write, protected read, partial projection,
  missing capability, ambiguous resource selection, and high-blast-radius confirmation.
  Status: drafted in Cross-Domain Scenario Analogues.
  Promotion condition: at least two non-household analogues become runnable proof fixtures
  with request frame, CandidateUniverse expectation, policy expectation, binding expectation,
  expected non-action path, and proof assertions.

XD-002 Protected reads across domains
  Class: CROSS-DOMAIN
  Question: Are protected reads a family/health issue or a general kernel issue?
  Working decision: general kernel issue because finance, legal, enterprise, education,
  identity, location, and health all have read-disclosure side effects.
  Promotion condition: PolicyBundle proof includes protected_read_requirements and disclosure gates.
```

### Architecture-Grounded Answers To Open Questions

The architecture diagrams and KernelService wiring answer several questions enough to standardize the API shape.

```text
1. Connected resource inventory
   It is a joined local-world projection, not a single table owned only by Fabric.

   Bridge / IFL owns connector registry, manifests, credentials, adapter health,
   inbound events, and external dispatch.

   K0 can persist/sync long-lived connector state and history.

   K1 needs an execution-ready local projection so Plane 4 can resolve resources
   without a global semantic search round trip.

   Fabric owns capability contracts and provider execution, then consumes the
   joined projection during binding.
```

```text
2. Minimum IFL manifest/resource metadata
   A connector manifest must declare more than executable actions.

   Required minimum:
     connector_id
     adapter_id / provider route
     capability templates
     resource kinds
     resource discovery/readback endpoints
     resource identity fields
     actor/account/household scoping fields
     auth scopes
     event topics
     safety/risk/effect metadata
     freshness guarantees
     verifier/read-after-write affordances
```

```text
3. Back resolver tool surface
   Back should primarily see one high-level execution-authority tool:

     resolve_situation(task_frame)

   Plane 4 may internally call many resolvers, registries, policy selectors,
   and projection readers. Those internals should not leak into Back unless a
   debugging or expert mode explicitly asks for them.
```

```text
4. Mandatory RequestFrame fields
   Minimum before execution resolution:

     request_id / trace_id / session_id
     actor_ref and household/space scope
     user_goal / task text
     normalized intent and operation hint, if known
     referenced people/resources/accounts/places/times, with provenance
     safety band and privacy context
     temporal/spatial grounding snapshot ids
     in-flight task context and cancellation/modification state
     prior resolution_id, if this is a retry
```

```text
5. CandidateUniverse completeness proof
   CandidateUniverse must include ScopeProof:

     projection sources used
     connector ids considered
     resource kinds considered
     actor/household/account scope
     freshness timestamps
     explicit omissions
     explicit exclusions with reasons
     unsupported-but-relevant gaps
     resolver version

   Completeness is therefore not "we found top 10". It is "within this proven
   scope, these are the candidate resources/capabilities and these are the
   things excluded or unavailable."
```

```text
6. Freshness and side effects
   GREEN fresh + complete:
     side effects may proceed if policy permits.

   Stale but known resource:
     safe reads may proceed; side effects need refresh, verifier, or HIL policy.

   Partial/offline projection:
     side effects are blocked unless the contract explicitly supports queued
     execution and the user accepts the offline behavior.

   Unknown freshness:
     no destructive or irreversible side effects.
```

```text
7. PolicyCard and GuideCard selection
   Select by task class, effect class, resource kind, connector/provider family,
   and exact bound capability.

   PromptPack should inject only compact cards needed for current state:

     global Back policy
     task/effect policy
     resource/domain policy
     bound capability guide
     active HIL/verification rule

   Long docs stay in retrieval; PromptPack carries the state-specific summary.
```

```text
8. Avoiding repeated resolver calls
   ResolutionEnvelope should carry:

     resolution_id
     request_frame_hash
     projection_version
     freshness_state
     prior_resolution_id
     allowed_next_actions

   Back should call resolve_situation again only when new information appears,
   the projection changed, a HIL answer arrived, or execution changed state.
```

```text
9. Verification without another LLM hop
   Verification obligations belong in ToolContract and PolicyCard, not Back prose.

   Deterministic checks should run after invocation when contracts declare them:

     read-after-write verifier capability
     output schema validation
     resource state comparison
     audit receipt presence
     provider success/failure code mapping

   The LLM interprets unusual outcomes; it should not decide whether verification
   was required.
```

```text
10. Batch execution shape
   Batch execution should report per binding, not only one global success flag.

   Required fields per item:

     binding_id
     provider_id
     resource_id
     capability_name
     invocation status
     verifier status
     retryability
     HIL/block reason
     user-visible summary fragment

   Mixed providers are allowed as a future target. If unsupported by an early
   runtime, the batch tool must split or return a structured unsupported reason.
```

```text
11. Telemetry
   Record enough to reconstruct the task path:

     trace_id
     request_id
     resolution_id
     Back ReAct iteration count
     LLM hop count
     resolver latency
     Fabric invocation latency
     connector/provider latency
     total task latency
     considered candidates
     omissions/exclusions
     freshness verdict
     policy/HIL verdict
     verification verdict
```

```text
12. discover_capabilities migration
   discover_capabilities survives, but its job changes.

   It remains valid for:
     catalog browsing
     docs/guide lookup
     fuzzy development search
     planner exploration
     explaining available integrations

   It must not be execution authority for side-effect tasks. Execution authority
   moves to resolve_situation plus exact capability binding.
```

### Spec Readiness Checklist

This whiteboard is acceptable as a future design spec only if each future implementation section can answer these checks.

```text
Terminology check
  Does it distinguish Tool, Capability, Connector, Adapter, Resource, Binding, Provider, Contract, and PromptPack?

Current-vs-target check
  Does it say whether it describes the live discover/invoke baseline or the target resolve/bind/invoke path?

Authority check
  Does every side-effect path prove actor, resource, policy, safety, idempotency, and audit context?

Completeness check
  Does every resolution path include scope proof, omissions, exclusions, freshness, and projection version?

Prompt boundary check
  Does the LLM see compact cards and observations instead of raw catalogs, manifests, credentials, or connector stack traces?

Protected-read check
  Does the policy path gate sensitive disclosure before model or user exposure?

Verification check
  Does every system-of-record mutation declare whether read-after-write verification is required, unavailable, or policy-degraded?

HIL quality check
  Are HIL choices sourced from CandidateUniverse, and does the question disclose incomplete projection when relevant?

Planning check
  Does every executable StepFrame resolve through CandidateUniverse, PolicyBundle, BindingBundle, and allowed_next_actions before invocation?

Safety semantics check
  Does the design separate actor clearance, task risk, operation risk, autonomy, runtime block state, and provider runtime band?

Connector admission check
  Does every external executable connector capability come from an admitted manifest, not a catalog-only suggestion?

Budget check
  Does budget exhaustion produce typed partial/HIL/retry_later/block/cannot_execute outcomes rather than silent success?

Migration check
  Can the design coexist with current Back meta-tools while discover_capabilities is demoted to catalog retrieval?

Telemetry check
  Can trace_id / request_id / resolution_id reconstruct the whole path from Front task to IFL result?

Replay check
  Can AuthorityDecisionRecord, PromptCaptureRecord, RedactionEvidence, and VerificationObservation replay what happened without raw forbidden material?

Failure check
  Are errors normalized into ErrorObservation + RecoveryDirective before Back sees them?
```

Implementation cut line:

```text
V0 implementation may be narrow in supported domains, but it is a production-shaped kernel foundation.
V0 implementation may not be vague about ownership, authority, freshness, tier routing, connector constitution, or prompt injection.

If a domain cannot satisfy the checklist, it should return cannot_execute or missing_capability rather than pretending a top-K result is enough.
```

### Remaining API Decisions

```text
1. Exact persistence schema for the joined local-world projection.
2. Exact ManifestTranslator output for connector resource models and capability templates.
3. Exact ResolutionEnvelope JSON schema and versioning rules.
4. Exact Back tool set names for V1: resolve_situation only, or resolve_situation + inspect_binding.
5. Exact compatibility mapping from current native names to connector-aware capability names.
6. Exact DomainInstantiationPack schema and validation level for V0.
7. Exact ResourceKindDef and OperationDef schemas for the first proof domain.
8. Exact PlanGraph producer and storage boundary for multi-step tasks.
9. Exact VerificationPlan methods supported in V0 and degraded-completion policy shape.
10. Exact TraceContext propagation and AuthorityDecisionRecord storage location.
11. Exact SafetyContext mapping from current GREEN/AMBER/RED runtime labels into kernel axes.
12. Exact ManifestAdmissionRecord trust tiers and connector revocation behavior.
13. Exact ExecutionBudget defaults for LLM hops, prompt cards, resolver fanout, connector fanout, verifier fanout, and latency.
14. Exact HIL presentation constraints and HILResponse resume behavior for Front/FSM integration.
15. Exact negative proof fixtures required for each CC milestone before promotion.
```

### Proposed Bottom Line

Execution authority should move from this:

```text
text query -> top-K tool list -> Back chooses -> invoke
```

to this:

```text
task frame
  -> tier route
  -> connector constitution / staged disclosure
  -> local world/resource universe
  -> impact set when companion resources apply
  -> operation/capability binding
  -> policy/guidance/contract prompt pack
  -> Tier 2 bounded Back ReAct or Tier 3 Planner/Orchestrator DAG
  -> governed execution / HIL / block / cannot_execute
  -> verification
  -> submit_result / task outcome
```

The core primitive is not search result ranking. The core primitive is a faithful candidate universe with scope proof, connector-carried procedural knowledge, and tier-correct execution ownership.

---

## Implementation Decomposition 01 - Sequential Component Atom Inventory

**Section mode:** implementation decomposition.

**Status:** tier-aware inventory draft.

Implementation warning: SCA atoms are an inventory, not implementation tickets. They expose seams, authority questions, and proof questions. Implementation tickets should be cut only after an atom has a design packet, request/response/failure shape, and proof plan.

This section starts the bottom-up component design work. The task here is not to finish
each component contract yet. The task is to find the smallest design atoms required for
the complete path from a Front user request to tier routing, Tier 2 Back execution or
Tier 3 Planner/Orchestrator execution, tool-chain dispatch, verification,
`submit_result` / task outcome, and final response to Front/FSM.

This is the first tier-aware inventory. During production proof design, some atoms will split further. Splitting is
allowed. Hiding an authority boundary inside a larger component is not allowed.

### Inventory Rule

Each atom below should eventually become one design packet using the standard component
template above.

```text
SequentialComponentAtom
  atom_id
  name
  phase
  caller -> callee
  primary artifact crossing the seam
  authority question
  proof question
```

Minimum bar for being listed as a separate atom:

```text
It has a distinct caller/callee seam, or
it makes a distinct authority decision, or
it changes what the LLM can see, or
it creates evidence needed for replay, or
it can fail independently and needs a typed recovery path.
```

### Full Sequential Flow Spine

```text
User turn
  -> Front ingress
  -> Front prompt/context assembly
  -> Front LLM dispatch_task call
  -> dispatch_task validation and normalization
  -> Front dispatch emission
  -> FSM canonicalization and routing
  -> tier authority decision
     Tier 1: Front asks/answers and no execution authority is minted
     Tier 2: BackTaskEnvelope intake
       -> Back prompt loop_start
       -> RequestFrame construction
       -> resolve_situation with staged connector constitution disclosure
       -> resource projection
       -> policy/guide/connector constitution selection
       -> capability binding
       -> CandidateUniverse + PromptPack
       -> Back ReAct decision
       -> invocation request
     Tier 3: Planner/Orchestrator envelope intake
       -> RequestFrame / planning context construction
       -> resolve_situation with connector constitutions + impact set
       -> Planner SKETCH/EXPAND/VALIDATE/COMMIT PlanGraph
       -> Orchestrator DAG wave execution
  -> Fabric invocation runtime
  -> native provider or Bridge/IFL connector path
  -> external app/device/service when applicable
  -> normalized observation
  -> verification/recovery/HIL loop when required
  -> submit_result / BackTaskOutcome / Orchestrator AggregatedResult
  -> FSM SessionState write
  -> Front/user-facing response envelope
```

### Phase A - User Turn To Front Intent Actor

```text
SCA-001 UserTurnEnvelopeIngress
  Caller -> callee: UI/API transport -> Front ingress runtime.
  Artifact: UserTurnEnvelope.
  Authority question: what raw user turn is eligible to become an intent-actor request?
  Proof question: can trace_id, request_id, session_id, actor hint, locale, timezone, and raw user text survive intake?

SCA-002 ActorAndSessionResolver
  Caller -> callee: Front ingress runtime -> identity/session lookup.
  Artifact: ActorSessionContext.
  Authority question: who is speaking, in which session, and under what actor scope?
  Proof question: does missing or ambiguous actor/session context fail closed before task dispatch?

SCA-003 DeviceAndLocaleContextBuilder
  Caller -> callee: Front ingress runtime -> device/context provider.
  Artifact: DeviceLocaleContext.
  Authority question: what timezone, locale, modality, and client constraints may influence interpretation?
  Proof question: are temporal/spatial defaults explicit rather than inferred later by Back?

SCA-004 FrontStateSnapshotReader
  Caller -> callee: Front actor -> SessionState read model.
  Artifact: FrontSafeStateSnapshot.
  Authority question: what current state may the intent actor see?
  Proof question: can protected or execution-only material be excluded from Front prompt context?

SCA-005 FrontGroundingContextCollector
  Caller -> callee: Front actor -> grounding providers.
  Artifact: FrontGroundingContext.
  Authority question: which referents, temporal hints, spatial hints, and recent artifacts are safe as intent context?
  Proof question: can user-world references be preserved without minting execution authority?

SCA-006 FrontPromptContextAssembler
  Caller -> callee: Front actor -> prompt builder.
  Artifact: FrontPromptContext.
  Authority question: what should the Front LLM see to decide whether to answer, ask, or dispatch?
  Proof question: does the prompt include user-world context but exclude raw tool catalogs and execution bindings?

SCA-007 FrontToolSurfaceSelector
  Caller -> callee: Front actor -> Front tool registry.
  Artifact: FrontToolSurface.
  Authority question: which Front tools are callable in this turn?
  Proof question: is `dispatch_task` visible only with its user-world schema, not Back/Fabric internals?

SCA-008 FrontLLMCallEnvelopeBuilder
  Caller -> callee: Front actor -> LLM gateway.
  Artifact: FrontLLMCallEnvelope.
  Authority question: what exact messages and tools are sent to the model?
  Proof question: can PromptCaptureRecord reconstruct Front-visible context safely?

SCA-009 FrontLLMToolCallParser
  Caller -> callee: LLM gateway -> Front ReAct loop.
  Artifact: FrontToolCallBatch.
  Authority question: which model-emitted calls are syntactically valid tool calls?
  Proof question: are malformed, mixed, or unsupported calls rejected before dispatch_task runs?

SCA-010 FrontAnswerVsDispatchGate
  Caller -> callee: Front ReAct loop -> Front action router.
  Artifact: FrontActionDecision.
  Authority question: should this turn answer directly, ask user, or dispatch task execution?
  Proof question: can Front avoid claiming execution completion for tasks that require Back authority?
```

### Phase B - Front `dispatch_task` To FSM Task Authority

```text
SCA-011 DispatchTaskSchemaValidator
  Caller -> callee: Front ReAct loop -> `dispatch_task` implementation.
  Artifact: ValidatedDispatchTaskArgs.
  Authority question: are intents, params, reference_context, depends_on, urgency, and plan flags valid user-world data?
  Proof question: are Fabric binding ids, raw connector ids, and policy verdicts rejected from Front-supplied args?

SCA-012 IntentListNormalizer
  Caller -> callee: `dispatch_task` implementation -> intent normalizer.
  Artifact: NormalizedIntentList.
  Authority question: what user goals become one or more execution intents?
  Proof question: can multiple intents preserve order, dependencies, domain hints, and per-intent urgency?

SCA-013 ReferenceContextNormalizer
  Caller -> callee: `dispatch_task` implementation -> reference context normalizer.
  Artifact: NormalizedReferenceContext.
  Authority question: which pronouns, people names, artifact refs, and grounding hints are carried forward?
  Proof question: does normalization preserve uncertainty instead of converting hints into resource ids?

SCA-014 DispatchTierEstimator
  Caller -> callee: `dispatch_task` implementation -> tier/budget estimator.
  Artifact: TierBudgetHint.
  Authority question: should the task route LOW, MEDIUM, HIGH, plan, or dependency-aware execution?
  Proof question: do plan/dependency hints survive even if the raw `plan` field is later discarded?

SCA-015 DispatchSafetySeedBuilder
  Caller -> callee: `dispatch_task` implementation -> safety seed builder.
  Artifact: DispatchSafetySeed.
  Authority question: what initial safety/autonomy/risk information is known before FSM canonicalization?
  Proof question: can current GREEN/AMBER/RED labels be mapped later without semantic loss?

SCA-016 TaskIdAndCorrelationAssigner
  Caller -> callee: `dispatch_task` implementation -> id generator.
  Artifact: TaskCorrelationSeed.
  Authority question: what stable task id and trace correlation identify this dispatched work?
  Proof question: can every later artifact chain back to the initial user turn?

SCA-017 DispatchTaskToolResultBuilder
  Caller -> callee: `dispatch_task` implementation -> Front ReAct loop.
  Artifact: DispatchTaskToolResult.
  Authority question: what does Front observe after dispatching, before Back has executed?
  Proof question: does ToolResult avoid telling the user the task is completed?

SCA-018 FrontDispatchedTaskCollector
  Caller -> callee: Front ReAct loop -> Front post-loop dispatcher.
  Artifact: DispatchedTaskCollection.
  Authority question: which tool results become actual task envelopes after the Front loop ends?
  Proof question: are duplicate or contradictory dispatches detected before FSM ingestion?

SCA-019 GroundingMetadataMirror
  Caller -> callee: Front actor -> task dispatch payload builder.
  Artifact: GroundingMirrorFields.
  Authority question: which grounding handles are copied into both typed fields and reference_context?
  Proof question: can Back recover grounding refs even if one consumer reads only reference_context?

SCA-020 FrontTaskEnvelopeEmitter
  Caller -> callee: Front actor -> event bus / FSM mailbox.
  Artifact: FrontTaskEnvelope.
  Authority question: what exact event asks the state authority to route work?
  Proof question: does emitted payload preserve task id, trace id, intent list, tier, safety seed, grounding, and dependencies?
```

### Phase C - FSM Canonicalization And Back Routing

```text
SCA-021 TaskDispatchEnvelopeParser
  Caller -> callee: FSM event consumer -> TaskDispatch parser.
  Artifact: ParsedTaskDispatch.
  Authority question: is the incoming Front payload a valid task dispatch?
  Proof question: do malformed or version-mismatched dispatches fail with typed diagnostics?

SCA-022 TaskDispatchCanonicalizer
  Caller -> callee: FSM -> canonical task builder.
  Artifact: CanonicalTaskDispatch.
  Authority question: what fields become source-of-truth for Back?
  Proof question: are preserved, promoted, defaulted, and discarded fields recorded?

SCA-023 CanonicalizationReportWriter
  Caller -> callee: FSM canonicalizer -> proof/audit stream.
  Artifact: CanonicalizationReport.
  Authority question: why did each meaningful field survive or disappear?
  Proof question: can top-level `plan`, dispatch-level urgency, grounding refs, and unknown extensions be audited?

SCA-024 FSMReferenceFallbackAttacher
  Caller -> callee: FSM -> scoreboard/referent read model.
  Artifact: FallbackReferenceContext.
  Authority question: what fallback referents may be attached if Front omitted reference_context?
  Proof question: are fallback referents marked as hints, not execution authority?

SCA-025 NarrativeThreadAttacher
  Caller -> callee: FSM -> narrative/task overlay provider.
  Artifact: NarrativeThreadContext.
  Authority question: what recent narrative/task context should Back receive?
  Proof question: does narrative context stay separate from durable resource identity?

SCA-026 RouteTierDecisionMaker
  Caller -> callee: FSM -> route/orchestrator decision logic.
  Artifact: RouteDecision.
  Authority question: should this canonical task go to Back directly, planner/orchestrator, or fail/pause?
  Proof question: can LOW/MEDIUM/HIGH behavior be replayed from task facts and config?

SCA-027 BackMailboxEnvelopeBuilder
  Caller -> callee: FSM -> Back mailbox/router.
  Artifact: BackRouteEnvelope.
  Authority question: what envelope headers and body are given to Back?
  Proof question: do session_id, request_id, cognitive_trace_id, parent_id, task_id, and canonical task body align?

SCA-028 FSMTaskStateTransitionRecorder
  Caller -> callee: FSM -> SessionState writer.
  Artifact: TaskStateRouteDelta.
  Authority question: how is the task marked as routed/active without Back writing state directly?
  Proof question: can SessionState replay show Front dispatched and FSM routed before Back started?

SCA-029 BackRouteEventPublisher
  Caller -> callee: FSM -> Back route handler.
  Artifact: BackRouteEvent.
  Authority question: what starts or resumes Back execution?
  Proof question: does duplicate route delivery remain idempotent by task id and trace id?
```

### Phase D - Back Intake And Request Framing

```text
SCA-030 BackRouteEnvelopeReader
  Caller -> callee: Back route handler -> Back actor.
  Artifact: BackRouteEnvelopeRead.
  Authority question: what task and headers does Back actually receive?
  Proof question: can Back reject missing task_id, session_id, trace_id, or actor context before prompt assembly?

SCA-031 BackSessionSnapshotReader
  Caller -> callee: Back actor -> SessionState read model.
  Artifact: BackSessionSnapshot.
  Authority question: what current state may the execution actor see at loop start?
  Proof question: is the one-shot snapshot explicitly versioned and trace-linked?

SCA-032 BackToolContextBinder
  Caller -> callee: Back actor -> ToolDispatcher context.
  Artifact: BackToolContext.
  Authority question: what actor, task id, session id, safety seed, execution profiles, and dispatch handle bind tool calls?
  Proof question: do Back tools fail closed when active_task_id or dispatch handle is missing?

SCA-033 ExecutionProfileSelector
  Caller -> callee: Back actor -> profile selector.
  Artifact: ActiveExecutionProfiles.
  Authority question: what execution profile limits, modes, or tool availability apply?
  Proof question: can LOW/simple and MEDIUM/HIGH/plan tool surfaces be explained from task facts?

SCA-034 SafetyContextMapper
  Caller -> callee: Back actor -> safety mapper.
  Artifact: KernelSafetyContextSeed.
  Authority question: how are current runtime safety labels mapped into actor_clearance, task_risk_state, operation_risk_class, autonomy_level, and runtime_block_state?
  Proof question: does the known GREEN/AMBER semantic conflict become impossible to hide?

SCA-035 BackTaskEnvelopeBuilder
  Caller -> callee: Back actor -> Back intake adapter.
  Artifact: BackTaskEnvelope.
  Authority question: what canonical execution envelope starts Back work?
  Proof question: does it preserve task intent, actor scope, correlation, grounding refs, safety context, and prior state refs?

SCA-036 BackTaskEnvelopeValidator
  Caller -> callee: Back intake adapter -> Back ReAct runtime.
  Artifact: BackTaskEnvelopeValidation.
  Authority question: is the Back task envelope sufficient to begin execution reasoning?
  Proof question: do missing actor_ref, safety_context, grounding refs, or invalid prior_resolution_id produce typed diagnostics?

SCA-037 BackLoopStartPromptInjector
  Caller -> callee: Back actor -> Back LLM request builder.
  Artifact: LoopStartPromptInjectionEnvelope.
  Authority question: what static role, task summary, state snapshot, grounding block, and meta-tool surface reach the Back model?
  Proof question: are raw catalogs, secrets, and unbounded state excluded from loop_start?

SCA-038 BackReActBudgetInitializer
  Caller -> callee: Back ReAct runtime -> budget manager.
  Artifact: BackLoopBudget.
  Authority question: how many LLM hops, tool calls, prompt cards, resolver calls, and retries are allowed?
  Proof question: does budget exhaustion produce typed outcomes instead of silent completion?

SCA-039 RequestFrameBuilder
  Caller -> callee: Back ReAct runtime -> request framing component.
  Artifact: RequestFrame.
  Authority question: what does Back think the user is asking before tools are bound?
  Proof question: can user_goal, operation_hints, actor_scope, constraints, temporal/spatial refs, and missing_fields be reconstructed from the BackTaskEnvelope?

SCA-040 RequestFrameValidator
  Caller -> callee: request framing component -> Back ReAct runtime.
  Artifact: RequestFrameValidation.
  Authority question: is the frame ready for resolution, HIL, cannot_execute, or memory-only handling?
  Proof question: are missing fields explicit rather than buried in prose?

SCA-041 StepFrameSeedBuilder
  Caller -> callee: Back ReAct runtime -> planner/step seed component.
  Artifact: OptionalStepFrameSeeds.
  Authority question: does this task need decomposition before resolution?
  Proof question: can multi-step hints be represented without authorizing execution?
```

### Phase E - Resolve Situation Entry

```text
SCA-042 ResolveSituationToolSchema
  Caller -> callee: Back tool schema registry -> Back LLM provider.
  Artifact: `resolve_situation` tool declaration.
  Authority question: what can the model ask the resolver to do?
  Proof question: is resolution_mode explicit and incapable of returning top-K as execution authority?

SCA-043 ResolveSituationRequestBuilder
  Caller -> callee: Back ReAct runtime -> ToolDispatcher.
  Artifact: ResolveSituationRequest.
  Authority question: what request_frame, actor_scope, safety_context, freshness_policy, prompt_budget, and previous_resolution_id are sent?
  Proof question: can the request be replayed without raw prompt text?

SCA-044 ResolverToolDispatchGate
  Caller -> callee: ToolDispatcher -> resolver runtime.
  Artifact: ResolverDispatchDecision.
  Authority question: may Back call resolve_situation now under actor tier, budget, and policy?
  Proof question: are repeated resolver calls bounded and traceable?

SCA-045 PreviousResolutionRefResolver
  Caller -> callee: resolver runtime -> resolution store/cache.
  Artifact: PriorResolutionContext.
  Authority question: is this a new resolution, refinement, HIL resume, or stale retry?
  Proof question: are expired or mismatched prior_resolution_id values rejected?

SCA-046 ResolverBudgetAllocator
  Caller -> callee: resolver runtime -> budget manager.
  Artifact: ResolverExecutionBudget.
  Authority question: how much time, fanout, candidate count, and prompt budget can this resolution use?
  Proof question: can partial_projection or retry_later cite exact budget exhaustion?

SCA-047 ResolveRequestedDecisionRecorder
  Caller -> callee: resolver runtime -> authority ledger.
  Artifact: AuthorityDecisionRecord(resolve_requested).
  Authority question: what authority boundary was crossed by asking Plane 4 to resolve?
  Proof question: can replay distinguish a resolution request from an invocation request?
```

### Phase F - Resolver Resource Universe Construction

```text
SCA-048 OperationHintNormalizer
  Caller -> callee: resolver runtime -> operation taxonomy.
  Artifact: NormalizedOperationHints.
  Authority question: what user-world verbs map to possible OperationDef ids?
  Proof question: are unknown operations treated as hints or missing_capability, not authority?

SCA-049 DomainInstantiationPackSelector
  Caller -> callee: resolver runtime -> domain pack registry.
  Artifact: SelectedDomainPacks.
  Authority question: which domain ontology, resource kinds, operation defs, policies, guides, and scenario rules apply?
  Proof question: can FamilyOS be selected as proof domain without becoming kernel-hardcoded?

SCA-050 ResourceKindHintMapper
  Caller -> callee: resolver runtime -> ontology/resource-kind mapper.
  Artifact: ResourceKindHints.
  Authority question: which resource kinds are relevant enough to search or declare missing?
  Proof question: does `calendar`, `car`, `Riley`, or `school` map to typed resource-kind hints without choosing a resource?

SCA-051 ActorScopeResolver
  Caller -> callee: resolver runtime -> identity/household/space scope reader.
  Artifact: ActorScope.
  Authority question: what resources may this actor see, mutate, or ask about?
  Proof question: are missing role/space defaults avoided or explicitly marked as degraded?

SCA-052 TemporalReferenceResolver
  Caller -> callee: resolver runtime -> temporal projection.
  Artifact: TemporalResolutionSet.
  Authority question: what concrete time refs can be used for scheduling, reminders, freshness, or constraints?
  Proof question: does `Monday`, `tomorrow`, or `after school` resolve with timezone and uncertainty?

SCA-053 PeopleReferenceResolver
  Caller -> callee: resolver runtime -> member/person projection.
  Artifact: PeopleResolutionSet.
  Authority question: which people refs are in scope as participants, owners, recipients, or consent subjects?
  Proof question: does `Riley` become a candidate person ref without silently assuming the wrong child/adult?

SCA-054 SpatialReferenceResolver
  Caller -> callee: resolver runtime -> spatial/place projection.
  Artifact: SpatialResolutionSet.
  Authority question: which places, rooms, vehicles, locations, or geofences are relevant?
  Proof question: are vague locations marked ambiguous before connector dispatch?

SCA-055 ResourceProjectionQueryBuilder
  Caller -> callee: resolver runtime -> local-world projection authority.
  Artifact: ResolveResourcesRequest.
  Authority question: what exact projection query should prove the candidate universe?
  Proof question: does the query include actor scope, resource kinds, references, operation hints, connector scope, and freshness policy?

SCA-056 ProjectionSourceFanoutPlanner
  Caller -> callee: local-world projection authority -> projection source registry.
  Artifact: ProjectionSourcePlan.
  Authority question: which sources may be read for this resolution under budget and policy?
  Proof question: can fanout be bounded without hiding blocking omissions?

SCA-057 SessionStateProjectionReader
  Caller -> callee: projection authority -> SessionState snapshot/projection.
  Artifact: SessionProjectionSlice.
  Authority question: what session-local referents, task artifacts, and grounding refs can seed candidates?
  Proof question: are session hints labeled separately from resource authority?

SCA-058 K1NativeProjectionReader
  Caller -> callee: projection authority -> K1 native family stores/tools.
  Artifact: NativeResourceProjectionSlice.
  Authority question: what calendars, tasks, reminders, chores, shopping lists, settings, and family resources are locally known?
  Proof question: are resource ids and freshness/version state carried, not just display labels?

SCA-059 BridgeProjectionReader
  Caller -> callee: projection authority -> Bridge connector/resource projection.
  Artifact: BridgeResourceProjectionSlice.
  Authority question: what external connector resources are connected, available, fresh, stale, revoked, or unavailable?
  Proof question: do credential state and connector health appear as candidate facts or omissions?

SCA-060 K0SyncProjectionReader
  Caller -> callee: projection authority -> optional K0/local sync projection.
  Artifact: K0ProjectionSlice.
  Authority question: what synced edge/local state may contribute to candidates?
  Proof question: is K0 data freshness and ownership explicit before use?

SCA-061 ProjectionFreshnessEvaluator
  Caller -> callee: projection authority -> freshness rules.
  Artifact: ProjectionFreshnessVerdict.
  Authority question: is the projection fresh enough for the requested effect class?
  Proof question: can stale_projection, partial_projection, and complete_for_scope be distinguished?

SCA-062 ResourceCandidateIdentityNormalizer
  Caller -> callee: projection authority -> identity normalizer.
  Artifact: ResourceCandidateSet.
  Authority question: what concrete resources exist after merging projection sources?
  Proof question: are display_label, alias, connector_id, adapter_id, provider_id, and resource_id kept distinct?

SCA-063 ResourceAmbiguityGrouper
  Caller -> callee: projection authority -> ambiguity detector.
  Artifact: AmbiguityGroups.
  Authority question: which resource candidates are mutually plausible referents?
  Proof question: can `my car` produce Tesla and Audi candidates without ranking one as the whole universe?

SCA-064 ProjectionOmissionRecorder
  Caller -> callee: projection authority -> omission/exclusion recorder.
  Artifact: CandidateOmissionsAndExclusions.
  Authority question: what relevant sources, resources, capabilities, policies, or verifiers were missing or excluded?
  Proof question: do omissions become visible in CandidateUniverse and PromptPack summaries?

SCA-065 ScopeProofBuilder
  Caller -> callee: projection authority -> resolver runtime.
  Artifact: ScopeProof.
  Authority question: what proves that the candidate set covers the intended actor/resource scope?
  Proof question: can replay show sources considered, versions, actor scope, resource scope, completeness claim, omissions, and exclusions?

SCA-066 ResourceUniverseBuilder
  Caller -> callee: projection authority -> resolver runtime.
  Artifact: ResourceUniverse.
  Authority question: what resource universe is available for binding?
  Proof question: does it return resources, unavailable resources, ambiguity, freshness, completeness, and scope proof together?
```

### Phase G - Policy, Guide, Binding, And PromptPack Assembly

```text
SCA-067 PolicySelectionRequestBuilder
  Caller -> callee: resolver runtime -> policy/guide authority.
  Artifact: PolicySelectionRequest.
  Authority question: what policy question is asked for this actor, operation, resource kind, effect, safety context, and freshness state?
  Proof question: are protected reads and disclosures included, not only writes?

SCA-068 PolicyBundleSelector
  Caller -> callee: policy/guide authority -> resolver runtime.
  Artifact: PolicyBundle.
  Authority question: which roles, gates, HIL triggers, privacy rules, audit rules, and verifier requirements apply?
  Proof question: does policy return gates and roles without choosing provider-specific commands?

SCA-069 ProtectedReadClassifier
  Caller -> callee: policy authority -> data classification rules.
  Artifact: ProtectedReadVerdict.
  Authority question: can this read or summary be shown to the model/user?
  Proof question: are sensitive data classes gated before PromptPack construction?

SCA-070 GuideCardSelector
  Caller -> callee: policy/guide authority -> guide card registry.
  Artifact: SelectedGuideCards.
  Authority question: what compact guidance applies after resource and operation context is known?
  Proof question: are activity/profile cards marked guidance, not executable capabilities?

SCA-071 HILTriggerBuilder
  Caller -> callee: policy authority -> HIL contract builder.
  Artifact: HILTriggerSet.
  Authority question: what must be asked of the user before action can proceed?
  Proof question: do HIL triggers cite candidate refs, policy gates, missing fields, risk, or incomplete projection?

SCA-072 VerificationRequirementBuilder
  Caller -> callee: policy authority -> verifier catalog.
  Artifact: VerificationRequirements.
  Authority question: what verification is required before submit_result(completed)?
  Proof question: can read-after-write, audit receipt, external receipt, and degraded verification be distinguished?

SCA-073 BindingRequestBuilder
  Caller -> callee: resolver runtime -> capability contract registry.
  Artifact: BindingRequest.
  Authority question: which operation/resource/policy roles need executable contracts?
  Proof question: are resource candidates and required roles passed together, not separately guessed by the model?

SCA-074 CapabilityRegistryExecutableQuery
  Caller -> callee: capability registry -> registered capability store.
  Artifact: ExecutableCapabilityMatches.
  Authority question: what exact executable contracts can satisfy the roles?
  Proof question: are guidance/profile/catalog-only records excluded from executable bindings?

SCA-075 ContractCardBuilder
  Caller -> callee: capability registry -> resolver runtime.
  Artifact: ContractCards.
  Authority question: what compact schema/effect/output information should reach PromptPack?
  Proof question: can Back understand required params without seeing full registries or manifests?

SCA-076 CapabilityBindingJoiner
  Caller -> callee: capability registry -> resolver runtime.
  Artifact: CandidateCapabilityBindings.
  Authority question: which actor + resource + operation + policy + contract joins are legal candidates?
  Proof question: does each binding carry resource_id, capability_name, contract_ref, schema refs, authority verdict, verifier refs, and freshness state?

SCA-077 BindingAuthorityValidator
  Caller -> callee: resolver runtime -> policy/contract/freshness validators.
  Artifact: BindingValidationVerdict.
  Authority question: which candidate bindings can appear in allowed_next_actions?
  Proof question: are stale, policy-blocked, unverified, missing-scope, or unsafe bindings excluded with diagnostics?

SCA-078 UnboundRoleDiagnosticWriter
  Caller -> callee: resolver runtime -> diagnostics builder.
  Artifact: UnboundRoleDiagnostics.
  Authority question: which required roles could not be bound and why?
  Proof question: can missing capability be separated from missing connector, policy block, stale projection, and unsupported operation?

SCA-079 BindingBundleBuilder
  Caller -> callee: resolver runtime -> Back/Fabric boundary.
  Artifact: BindingBundle.
  Authority question: what binding package can Back later invoke from?
  Proof question: does the bundle include bindings, unbound roles, contract cards, guide refs, verifier links, and diagnostics?

SCA-080 CandidateUniverseBuilder
  Caller -> callee: resolver runtime -> Back/Fabric boundary.
  Artifact: CandidateUniverse.
  Authority question: what complete situated world does Back use for this ReAct phase?
  Proof question: are scope proof, candidates, bindings, required roles, omissions, exclusions, completeness, freshness, policy verdict, allowed actions, and expiry present?

SCA-081 CompletenessBeforeRankingGate
  Caller -> callee: resolver runtime -> candidate presentation ranker.
  Artifact: RankingEligibilityVerdict.
  Authority question: is the candidate universe complete enough to rank for model/user display?
  Proof question: can ranking be blocked when completeness is unknown or partial?

SCA-082 AllowedNextActionBuilder
  Caller -> callee: resolver runtime -> Back decision surface.
  Artifact: AllowedNextActions.
  Authority question: what may Back legally do next?
  Proof question: can each action cite a policy gate, binding, HIL trigger, verifier duty, or recovery directive?

SCA-083 PromptPackRedactionScanner
  Caller -> callee: resolver runtime -> redaction/protected material scanner.
  Artifact: RedactionEvidence.
  Authority question: what material is forbidden from model context?
  Proof question: does prompt_visible_leak_count remain zero for secrets, raw manifests, raw provider payloads, and protected data?

SCA-084 PromptPackBuilder
  Caller -> callee: resolver runtime -> Back prompt injection runtime.
  Artifact: PromptPack.
  Authority question: what compact decision surface should Back see now?
  Proof question: does PromptPack include cards, allowed/forbidden actions, uncertainty, omissions, source refs, expiry, and output schema within budget?

SCA-085 ResolutionEnvelopeBuilder
  Caller -> callee: resolver runtime -> Back ReAct runtime.
  Artifact: ResolutionEnvelope.
  Authority question: what complete response ends situated resolution?
  Proof question: do resolution_id, request_frame, CandidateUniverse, PromptPack, policy/binding refs, completeness, freshness, verdict, and diagnostics travel together?

SCA-086 ResolveResultDecisionRecorder
  Caller -> callee: resolver runtime -> authority ledger.
  Artifact: AuthorityDecisionRecord(resolve_result).
  Authority question: what did the resolver allow, block, ask, refresh, or declare missing?
  Proof question: can every allowed and forbidden next action be replayed from redacted refs?
```

### Phase H - Back ReAct Decision After Resolution

```text
SCA-087 AfterResolutionPromptInjector
  Caller -> callee: Back ReAct runtime -> Back LLM request builder.
  Artifact: AfterResolutionPromptInjectionEnvelope.
  Authority question: how does PromptPack enter the model context at the right phase?
  Proof question: does Back see allowed_next_actions and relevant cards only after resolution?

SCA-088 BackModelActionParser
  Caller -> callee: LLM gateway -> Back ReAct runtime.
  Artifact: BackModelAction.
  Authority question: what tool call or submit action did the model choose?
  Proof question: can invalid, mixed, duplicated, or out-of-phase actions be detected?

SCA-089 AllowedActionRuntimeEnforcer
  Caller -> callee: Back ReAct runtime -> ToolDispatcher.
  Artifact: AllowedActionDecision.
  Authority question: is the chosen model action legal under the current ResolutionEnvelope?
  Proof question: are forbidden actions blocked by runtime, not only discouraged by prompt text?

SCA-090 InvocationRequestBuilder
  Caller -> callee: Back ReAct runtime -> Fabric invocation runtime.
  Artifact: InvocationRequest.
  Authority question: what bound capability is Back asking Fabric to execute?
  Proof question: does the request carry resolution_id, binding_id, params, idempotency_key, actor_ref, safety_context, policy refs, and expected effect?

SCA-091 InvocationParamCompletionAdapter
  Caller -> callee: Back ReAct runtime -> deterministic param adapter.
  Artifact: ParamPatchProposal.
  Authority question: can near-miss task params be safely transformed before invocation?
  Proof question: does `duration_minutes + start -> end` happen deterministically with evidence, while ambiguous transforms ask HIL?

SCA-092 InvocationPreflightValidator
  Caller -> callee: Back/Fabric boundary -> invocation runtime.
  Artifact: InvocationPreflightVerdict.
  Authority question: is the invocation complete enough to leave the model boundary?
  Proof question: are missing params, stale resolution, expired binding, missing idempotency, and policy mismatch caught before provider dispatch?

SCA-093 BatchIndependenceValidator
  Caller -> callee: Back ReAct runtime -> batch invocation guard.
  Artifact: BatchInvocationEligibility.
  Authority question: may multiple bindings execute together?
  Proof question: are dependent writes such as event creation then reminder creation forced to sequence?

SCA-094 HILRequestBuilder
  Caller -> callee: Back ReAct runtime -> FSM/HIL channel.
  Artifact: HILRequest.
  Authority question: what exactly must the user clarify, confirm, consent to, or provide?
  Proof question: do choices come from CandidateUniverse and disclose incomplete projection when relevant?

SCA-095 CannotExecuteOrBlockedSubmitPlanner
  Caller -> callee: Back ReAct runtime -> submit_result builder.
  Artifact: TerminalNonExecutionPlan.
  Authority question: when should Back stop and report cannot_execute or blocked?
  Proof question: can missing capability, policy block, stale projection, and budget exhaustion produce distinct user summaries and evidence?
```

### Phase I - Fabric Invocation Runtime

```text
SCA-096 InvokeCapabilityToolDispatchGate
  Caller -> callee: ToolDispatcher -> Fabric invocation runtime.
  Artifact: InvokeDispatchDecision.
  Authority question: may this Back actor invoke this binding/capability now?
  Proof question: are actor tier, tool budget, crisis block, no-work guard, and schema validation enforced?

SCA-097 BindingLookupAndStalenessChecker
  Caller -> callee: Fabric invocation runtime -> binding store/resolution refs.
  Artifact: BindingInvocationContext.
  Authority question: is the binding still valid for this actor, resource, policy, and freshness state?
  Proof question: does expired or mismatched resolution_id block side effects?

SCA-098 ContractParamSchemaValidator
  Caller -> callee: Fabric invocation runtime -> contract registry.
  Artifact: ContractParamValidation.
  Authority question: do params satisfy the bound contract schema exactly?
  Proof question: are missing `end`, wrong recipient, unknown resource id, or invalid trigger shape returned as normalized recovery?

SCA-099 PolicyGateRevalidator
  Caller -> callee: Fabric invocation runtime -> policy authority.
  Artifact: InvocationPolicyVerdict.
  Authority question: do policy gate refs still permit the side effect or protected read?
  Proof question: does user confirmation, consent, role, and protected-read status remain fresh at invocation time?

SCA-100 SafetyMappingEvidenceBuilder
  Caller -> callee: Fabric invocation runtime -> provider/runtime safety mapper.
  Artifact: SafetyMappingEvidence.
  Authority question: how does kernel SafetyContext map to native provider or connector runtime fields?
  Proof question: does GREEN/AMBER/RED compatibility mapping record source, target, rule, verdict, and block reason?

SCA-101 IdempotencyKeyValidator
  Caller -> callee: Fabric invocation runtime -> idempotency store.
  Artifact: IdempotencyDecision.
  Authority question: is this side-effect request new, duplicate, retry, or conflicting?
  Proof question: can repeated Back tool calls avoid duplicate external writes?

SCA-102 ProviderRouteSelector
  Caller -> callee: Fabric invocation runtime -> provider registry.
  Artifact: ProviderRouteDecision.
  Authority question: should invocation go to native K1 provider, Bridge connector path, workflow runtime, or unsupported path?
  Proof question: can current native family tools coexist with future connector-aware routes?

SCA-103 InvocationAuditBeginRecorder
  Caller -> callee: Fabric invocation runtime -> authority ledger/audit sink.
  Artifact: AuthorityDecisionRecord(invoke_begin).
  Authority question: what side-effect or protected-read attempt is about to leave Fabric?
  Proof question: can replay see params summary, binding refs, policy refs, idempotency key, and target route without secrets?

SCA-104 NativeProviderRequestBuilder
  Caller -> callee: Fabric invocation runtime -> NativeToolProvider.
  Artifact: NativeCapabilityRequest.
  Authority question: how is a bound invocation represented for local family tools?
  Proof question: does caller role, face, space id, safety mapping, and audit context avoid permissive hidden defaults?

SCA-105 NativeWriteContextBuilder
  Caller -> callee: NativeToolProvider -> family tool service.
  Artifact: NativeWriteContext.
  Authority question: what local write/read context reaches the adapter service?
  Proof question: are actor role, household/space, safety, trace id, and audit info explicit?

SCA-106 NativeServiceDispatcher
  Caller -> callee: NativeToolProvider -> BaseToolService adapter.
  Artifact: NativeServiceResult.
  Authority question: which local adapter action executes the request?
  Proof question: can calendar/tasks/reminders/chores/shopping/settings responses normalize into InvocationObservation?

SCA-107 ConnectorDispatchRequestBuilder
  Caller -> callee: Fabric invocation runtime -> Bridge ConnectorGateway.
  Artifact: ConnectorDispatchRequest.
  Authority question: how does Fabric ask Bridge to execute without owning secrets or protocol details?
  Proof question: does request include connector_id, adapter_id, resource_id, operation, params, actor scope, policy refs, idempotency, timeout, and verifier request?
```

### Phase J - Bridge And IFL External Connector Path

```text
SCA-108 BridgeCredentialHandleResolver
  Caller -> callee: Bridge ConnectorGateway -> credential vault/handle store.
  Artifact: ConnectorAuthContextRef.
  Authority question: which credential handle may be used for this actor, connector, scope, and resource?
  Proof question: does no secret cross upward to Fabric, Back, PromptPack, or logs?

SCA-109 ConnectorScopePermissionChecker
  Caller -> callee: Bridge ConnectorGateway -> connector permission model.
  Artifact: ConnectorScopeVerdict.
  Authority question: do approved auth scopes permit the requested action on this resource?
  Proof question: are missing, revoked, expired, or insufficient scopes returned as normalized denial?

SCA-110 ConnectorRateAndCircuitLimiter
  Caller -> callee: Bridge ConnectorGateway -> rate/circuit manager.
  Artifact: ConnectorDispatchCapacityVerdict.
  Authority question: may this connector be called now?
  Proof question: can unavailable, queued, retry_after, and circuit_open states be represented without provider stack traces?

SCA-111 AdapterRuntimeSelector
  Caller -> callee: Bridge ConnectorGateway -> adapter registry.
  Artifact: AdapterRuntimeRoute.
  Authority question: which admitted adapter implementation handles this connector action?
  Proof question: are catalog-only, untrusted, revoked, or missing adapters blocked before execution?

SCA-112 ConnectorDispatchAuditRecorder
  Caller -> callee: Bridge ConnectorGateway -> audit sink.
  Artifact: ConnectorAuditReceiptStart.
  Authority question: what connector action is being attempted below Fabric?
  Proof question: can audit replay show connector_id, adapter_id, resource_id, action, scope verdict, and idempotency without secrets?

SCA-113 IflCommandEnvelopeBuilder
  Caller -> callee: Bridge ConnectorGateway -> IFL adapter runtime.
  Artifact: IflCommandEnvelope.
  Authority question: what normalized command is sent into provider-specific protocol code?
  Proof question: does envelope carry auth_context_ref, resource_ref, expected_effect, timeout, readback_requested, and idempotency_key?

SCA-114 AdapterAuthContextLinker
  Caller -> callee: IFL adapter runtime -> secret/runtime auth layer.
  Artifact: AdapterRuntimeAuthContext.
  Authority question: how does the adapter gain auth material without exposing it above the adapter boundary?
  Proof question: are auth failures normalized and secrets never serialized into raw payload refs?

SCA-115 IflProtocolExecutor
  Caller -> callee: IFL adapter runtime -> external app/device/service.
  Artifact: ProviderProtocolCall.
  Authority question: what provider API/device command is actually executed?
  Proof question: are provider method, remote correlation id, timeout, retryability, and expected effect recorded below prompt boundary?

SCA-116 ProviderResponseNormalizer
  Caller -> callee: IFL adapter runtime -> Bridge ConnectorGateway.
  Artifact: NormalizedProviderResult.
  Authority question: how does raw provider response become kernel-safe status and payload?
  Proof question: do success, partial, denied, unavailable, queued, failed, retryable, and readback states normalize consistently?

SCA-117 RawPayloadRefWriter
  Caller -> callee: IFL adapter runtime -> raw payload store.
  Artifact: RawPayloadRef.
  Authority question: where can raw provider payload be retained safely if needed?
  Proof question: can Back/PromptPack receive only safe summaries and refs?

SCA-118 IflResultEnvelopeBuilder
  Caller -> callee: IFL adapter runtime -> Bridge ConnectorGateway.
  Artifact: IflResultEnvelope.
  Authority question: what normalized adapter result returns to Bridge?
  Proof question: does it include status, remote_status, correlation id, normalized payload, raw ref, resource delta, readback, error code, summary, and retry_after?

SCA-119 ConnectorDispatchObservationBuilder
  Caller -> callee: Bridge ConnectorGateway -> Fabric invocation runtime.
  Artifact: ConnectorDispatchObservation.
  Authority question: what result can Fabric trust from Bridge?
  Proof question: does observation include bridge_request_id, connector/resource ids, normalized result, projection delta, audit receipt, verifier result, and safe error summary?

SCA-120 ResourceProjectionDeltaEmitter
  Caller -> callee: Bridge/IFL path -> local-world projection authority.
  Artifact: ResourceProjectionDelta.
  Authority question: what resource state changed or became stale after connector execution?
  Proof question: can later resolution observe the delta without live connector probing when fresh enough?
```

### Phase K - Observation, Verification, Recovery, And HIL Resume

```text
SCA-121 FabricObservationNormalizer
  Caller -> callee: Fabric invocation runtime -> Back ReAct runtime.
  Artifact: NormalizedInvocationObservationDraft.
  Authority question: how do native and Bridge results become one observation shape?
  Proof question: can Back reason over status, artifacts, structured_result, recovery, and verifier obligations without provider-specific branches?

SCA-122 ErrorObservationBuilder
  Caller -> callee: Fabric invocation runtime -> recovery normalizer.
  Artifact: ErrorObservation.
  Authority question: what error happened, where, how severe, and whether retry/HIL/refresh is legal?
  Proof question: are raw exceptions stored by ref while Back sees compact source_component, code, severity, retryability, and summary?

SCA-123 RecoveryDirectiveBuilder
  Caller -> callee: recovery normalizer -> Back ReAct runtime.
  Artifact: RecoveryDirective.
  Authority question: what is the next legal move after a failure or incomplete result?
  Proof question: can ask_hil, retry_with_params, refresh_projection, run_prerequisite_read, choose_from_candidates, block_and_submit, and cannot_execute be distinct?

SCA-124 VerificationPlanSelector
  Caller -> callee: Fabric invocation runtime -> verifier catalog/policy.
  Artifact: VerificationPlan.
  Authority question: what verification is required for this invocation before completion?
  Proof question: does Back not decide verification requirements by prose?

SCA-125 VerificationExecutionRequestBuilder
  Caller -> callee: verifier runner -> readback/audit/external receipt source.
  Artifact: VerificationExecutionRequest.
  Authority question: what evidence source proves expected effect?
  Proof question: are read-after-write, output schema, state compare, audit receipt, external receipt, and policy attestation separated?

SCA-126 VerificationObservationBuilder
  Caller -> callee: verifier runner -> Fabric/Back runtime.
  Artifact: VerificationObservation.
  Authority question: what was proven, degraded, failed, inconclusive, skipped, or unavailable?
  Proof question: does completed submit block when verification is required but failed or inconclusive?

SCA-127 InvocationObservationBuilder
  Caller -> callee: Fabric invocation runtime -> Back ReAct runtime.
  Artifact: InvocationObservation.
  Authority question: what final invocation observation should Back see?
  Proof question: does it include invocation_id, binding_id, status, provider_status, summary, artifacts, structured result, errors, recovery, verification, and audit fields?

SCA-128 AfterInvocationPromptInjector
  Caller -> callee: Back ReAct runtime -> Back LLM request builder.
  Artifact: AfterInvocationPromptInjectionEnvelope.
  Authority question: what observation/recovery/verification facts enter the model after a tool result?
  Proof question: are raw provider payloads and secrets still excluded while next legal actions are clear?

SCA-129 HILResponseIngestor
  Caller -> callee: FSM/Front HIL channel -> Back/FSM resume path.
  Artifact: HILResponse.
  Authority question: what human answer resumes execution?
  Proof question: can selected_candidate_refs, provided_fields, confirmation, consent, constraints, and freeform text be separated?

SCA-130 HILResumeResolutionGate
  Caller -> callee: Back ReAct runtime -> resolver runtime.
  Artifact: HILResumeResolveRequest.
  Authority question: may the previous ResolutionEnvelope be reused, or must resolution run again?
  Proof question: do HIL answers recheck policy, freshness, and bindings before invocation when needed?

SCA-131 BudgetObservationUpdater
  Caller -> callee: Back/Fabric/Bridge runtimes -> budget manager.
  Artifact: BudgetObservation.
  Authority question: how much budget has been consumed across LLM, resolver, invocation, connector, verifier, and retries?
  Proof question: is exhausted budget visible in observations and submit_result?

SCA-132 AuthorityDecisionLedgerWriter
  Caller -> callee: all authority seams -> authority ledger.
  Artifact: AuthorityDecisionRecord.
  Authority question: what allowed, denied, asked, refreshed, invoked, verified, degraded, or could not execute?
  Proof question: can a reviewer reconstruct non-actions and actions from redacted evidence?
```

### Phase L - Submit Result And Final Response To Front

```text
SCA-133 SubmitResultIntentBuilder
  Caller -> callee: Back ReAct runtime -> submit_result tool.
  Artifact: SubmitResultDraft.
  Authority question: what final status is Back proposing?
  Proof question: does status distinguish completed, partial, needs_hil, cannot_execute, blocked, and failed?

SCA-134 SubmitResultSchemaValidator
  Caller -> callee: ToolDispatcher -> submit_result implementation.
  Artifact: SubmitResultValidation.
  Authority question: is the submitted result structurally valid?
  Proof question: are user_summary, evidence_summary, artifacts, authority_actions_attempted, verification_status, and unresolved_items present as required?

SCA-135 CompletionAuthorityGate
  Caller -> callee: submit_result implementation -> authority/proof guard.
  Artifact: CompletionAuthorityVerdict.
  Authority question: may this task be marked completed?
  Proof question: is completed blocked unless authority action or approved degraded verification exists for system-of-record tasks?

SCA-136 MixedSubmitAndToolGuard
  Caller -> callee: Back ReAct runtime -> tool call scheduler.
  Artifact: MixedActionVerdict.
  Authority question: did the model try to submit while also asking for more work?
  Proof question: are unexecuted side-effect calls prevented from being skipped behind premature submit_result?

SCA-137 FinalIterationTerminationEnforcer
  Caller -> callee: Back ReAct runtime -> Back LLM/tool scheduler.
  Artifact: TerminationDirective.
  Authority question: how does the loop force a structured terminal result when budget ends?
  Proof question: can final iteration produce partial/blocked/failed/cannot_execute instead of silent no-op?

SCA-138 BackTaskOutcomeBuilder
  Caller -> callee: Back actor -> FSM route/outcome consumer.
  Artifact: BackTaskOutcome.
  Authority question: what should the state authority receive from Back?
  Proof question: does Back return deltas/outcomes, not direct SessionState writes?

SCA-139 FSMBackOutcomeConsumer
  Caller -> callee: FSM -> SessionState writer.
  Artifact: BackOutcomeApplyRequest.
  Authority question: how should Back outcome update task state?
  Proof question: can FSM validate status, artifacts, HIL request, unresolved items, and audit refs before writing?

SCA-140 SessionStateDeltaApplier
  Caller -> callee: FSM -> SessionState store.
  Artifact: SessionStateDelta.
  Authority question: what durable state changes result from the Back outcome?
  Proof question: does Single Writer discipline hold for task completion, artifacts, HIL pending state, and summaries?

SCA-141 ArtifactRegistrar
  Caller -> callee: FSM/state authority -> artifact store.
  Artifact: TaskArtifactRecord.
  Authority question: what created/read/verified artifacts are durable and user-visible?
  Proof question: are raw payload refs, provider ids, safe summaries, and verification refs classified separately?

SCA-142 UserSummarySanitizer
  Caller -> callee: FSM/Front response path -> disclosure/redaction policy.
  Artifact: UserVisibleSummary.
  Authority question: what can be shown to the user after Back execution?
  Proof question: are protected-read, partial, failed, blocked, and degraded-verification summaries policy-safe?

SCA-143 FrontResponseEnvelopeBuilder
  Caller -> callee: FSM/Front response path -> UI/API transport.
  Artifact: FrontResponseEnvelope.
  Authority question: what final response or HIL prompt returns to Front/user?
  Proof question: does it carry status, summary, next question if any, artifact refs, and trace correlation?

SCA-144 UIEventPublisher
  Caller -> callee: Front/FSM response path -> client/event stream.
  Artifact: UserFacingEvent.
  Authority question: what event should the UI render?
  Proof question: can completion, partial, blocked, failed, HIL, and queued states render without exposing internals?

SCA-145 EndToEndProofBundleFinalizer
  Caller -> callee: proof harness -> evidence store.
  Artifact: EndToEndProofBundle.
  Authority question: what evidence proves this whole request path?
  Proof question: can trace_id reconstruct Front intake, dispatch, FSM route, Back frame, resolution, prompt pack, invocation, verification, submit_result, and response?
```

### Supporting Background Atoms Required By The Sequential Path

These atoms may not run during every user turn, but the sequential path depends on them.
They still need their own design packets because they mint contracts, projections, and
policy material used by live execution.

```text
SCA-B01 DomainInstantiationPackLoader
  Provides domain ontology, resource kinds, operation defs, policy refs, guide refs, manifests, verifiers, and scenario gates.

SCA-B02 ResourceKindDefValidator
  Proves each resource kind has stable identity fields, owner scope fields, alias rules, supported operations, data classification, freshness, and verifier expectations.

SCA-B03 OperationDefValidator
  Proves user verbs map to typed effect classes, resource kinds, policy hooks, verifier refs, idempotency requirements, and confirmation defaults.

SCA-B04 PolicyCardRegistry
  Stores and versions policy cards used by PolicyBundle selection.

SCA-B05 GuideCardRegistry
  Stores and versions guide cards that may enter PromptPack only after relevance is proven.

SCA-B06 ManifestAdmissionGate
  Converts catalog or marketplace manifests into admitted, catalog_only, denied, or revoked status before executable registration.

SCA-B07 ManifestTrustAndSignatureVerifier
  Proves connector manifests are signed, trusted, permission-reviewed, and scoped before execution authority.

SCA-B08 ManifestToCapabilityTranslator
  Emits capability contracts, resource models, event contracts, provider routes, guide refs, and registration diagnostics while preserving connector identity.

SCA-B09 CapabilityContractVersionRegistry
  Provides exact schema/effect/output/version refs for binding and invocation.

SCA-B10 ProviderRouteRegistry
  Maps capability contracts to native providers, Bridge routes, workflow runtimes, or blocked/missing providers.

SCA-B11 ConnectorHealthProjectionIngestor
  Updates availability, credential state, rate/circuit state, and freshness for connector resources outside user turns.

SCA-B12 BridgeEventProjectionIngestor
  Applies Bridge/IFL resource deltas into local-world projection with versioning and conflict handling.

SCA-B13 ProjectionConflictResolver
  Decides how conflicting projection slices merge, reject fields, or mark ambiguity.

SCA-B14 PromptCaptureRecorder
  Records prompt ids, prompt hashes, safe summaries, card ids, allowed/forbidden actions, and redaction refs for replay.

SCA-B15 RedactionPolicyScanner
  Scans model-visible artifacts for forbidden secrets, protected data, raw manifests, raw provider payloads, and retention violations.

SCA-B16 ProofRecordWriter
  Records targeted POC inputs, outputs, pass criteria, failures, negative proofs, and promotion notes for each atom.

SCA-B17 FailureEntryWriter
  Records observed failures, root cause, design correction, implementation correction, and whether the atom contract changed.

SCA-B18 FeatureFlagAndShadowModeController
  Controls legacy discover/invoke, resolver shadow comparison, binding authority cutover, rollback, and proof preservation.

SCA-B19 CompatibilityAliasMapper
  Maps current native names such as `tool.execute.calendar.create_event` to connector-aware or binding-aware names without hiding missing evidence.

SCA-B20 ScenarioGateFixtureRunner
  Runs FamilyOS and cross-domain gates that prove component atoms in realistic end-to-end flows.
```

### Code-Grounded First Expansion Order

Code read date: 2026-05-29.

Current code already has a working Front -> FSM -> Back -> discover/bind/invoke ->
submit_result path. The first design expansion must therefore wrap and clarify that path;
it must not add a new runtime service chain just to satisfy the future architecture shape.

Current anchors:

```text
Front dispatch emission:
  k1/concierge/actors/front.py
    _sync_dispatch_reference_context
    front_handler post-loop normal_dispatches emission

Canonical task contract:
  k1/concierge/task/dispatch.py
    TaskDispatch.from_dict
    TaskDispatch.to_dict
    _mirror_grounding_into_reference_context

FSM canonical route:
  k1/concierge/fsm/controller.py
    _on_task_dispatch
    _route_via_orchestrator
    _attach_turn_state_overlay_to_dispatch

Back intake:
  k1/concierge/actors/back.py
    _bind_tool_context
    _effective_task_safety_band
    _build_execution_grounding_block
    back_handler

Back tools / Fabric compatibility path:
  k1/concierge/tools/implementations.py
    execute_discover_capabilities
    _bind_capability_for_back_action
    _request_prompt_metadata
    execute_invoke_capability
    execute_submit_result

Current binding analogue:
  k1/concierge/react/capability_routing.py
    CapabilityBindingRequest
    CapabilityBindingResult
    bind_capability

Dispatcher and completion guards:
  k1/concierge/tools/dispatcher.py
    ToolDispatcher.dispatch
  k1/concierge/react/loop.py
    submit_result terminal handling
  k1/concierge/actors/back.py
    _emit_back_result
```

First-pass rule:

```text
Design the minimum structural components needed to make the existing system legible,
traceable, and less fragile while preserving every planned room in the blueprint.

Do not remove future components from the design.
Do not pretend the first pass is the whole bungalow.
Do not add heavy runtime implementations before their load-bearing seams are proven.

The first pass builds the foundation, walls, doors, windows, roofline, and service conduits.
Later passes install the full interior systems, finishes, garden, and expansion details.
Every deferred component must have a reserved socket, doorway, conduit, or contract placeholder
so the later build can attach without breaking the structure.
```

#### Structural First-Pass Order

The SCA list remains the full bungalow blueprint. The first implementation design batch
does not delete rooms from that blueprint. It groups atoms that are separate in the future
kernel but already colocated in current code, while reserving explicit attachment points
for the later dedicated components.

```text
FP-01 FSM Canonical Dispatch Boundary
  Covers: SCA-022, SCA-023.
  Current code home: FSM._route_via_orchestrator.
  Why merged: canonical payload and canonicalization report are one seam today.

FP-02 Back Execution Envelope Seed
  Covers: SCA-035.
  Current code home: back_handler + _bind_tool_context.
  Why kept small: Back already receives a dict task plus envelope headers; no new envelope bus type first pass.

FP-03 RequestFrame Seed
  Covers: SCA-039, SCA-043.
  Current code home: back_handler task JSON + future helper around discover/invoke args.
  Why grouped now: resolve_situation does not exist yet; first pass builds a frame that can feed legacy discovery and reserves the resolver doorway.

FP-04 Legacy Capability Universe And Prompt Cards
  Covers: SCA-055, SCA-065, SCA-080, SCA-084 in compatibility form.
  Current code home: execute_discover_capabilities + bind_capability + _request_prompt_metadata.
  Why grouped now: there is no resource projection service yet; first pass partitions and records current capability evidence while reserving resource, scope-proof, candidate-universe, and prompt-pack sockets.

FP-05 Invocation Request And Preflight
  Covers: SCA-090, SCA-092.
  Current code home: execute_invoke_capability.
  Why merged: current preflight and CapabilityRequest construction are already adjacent.

FP-06 Invocation Observation Normalizer
  Covers: SCA-127.
  Current code home: execute_invoke_capability ToolResult construction.
  Why grouped now: Back sees ToolResult today; normalize that observation while reserving the later VerificationObservation doorway.

FP-07 Submit Result Authority Boundary
  Covers: SCA-133, SCA-135.
  Current code home: execute_submit_result + ToolDispatcher no-work guard + _emit_back_result.
  Why merged: submit_result does not emit events; Back actor owns event emission after ReactResult.

FP-08 End-To-End Proof Slice
  Covers: SCA-145.
  Current code home: existing targeted tests/probes and call summaries.
  Why grouped now: use existing pytest/probe evidence while reserving the later persistent proof-ledger conduit.
```

#### Reserved Components For Later Passes

These are not removed. They are named parts of the bungalow that must remain in the plan.
The first pass must leave structural attachment points for them, but it should not install
their full runtime machinery before the current load-bearing path is proven.

```text
RSV-01 Full local-world resource projection store
  Reserved by: FP-04.
  First-pass socket: LegacyCapabilityUniverse must not claim resource completeness and must expose where ResourceUniverse will attach.

RSV-02 Full ScopeProof with connector completeness claims
  Reserved by: FP-04.
  First-pass socket: request/capability evidence must carry trace_id, task_id, actor/safety hints, omissions, and diagnostics.

RSV-03 Model-visible resolve_situation meta-tool
  Reserved by: FP-03.
  First-pass socket: RequestFrameSeed and LegacyResolveCompatibilityRequest define the future input shape.

RSV-04 PolicyBundle service
  Reserved by: FP-04 and FP-05.
  First-pass socket: legacy safety_band, protected-read notes, recovery, and capability limitations remain explicit rather than buried in prose.

RSV-05 BindingBundle persistence layer
  Reserved by: FP-04 and FP-05.
  First-pass socket: CapabilityBindingResult remains the compatibility binding artifact and must be carried in failures/observations.

RSV-06 Bridge/IFL connector execution path redesign
  Reserved by: FP-05 and FP-06.
  First-pass socket: CapabilityRequest and CapabilityResult stay the bridge-facing seam; native provider remains the proof path.

RSV-07 Read-after-write VerificationPlan runner
  Reserved by: FP-06 and FP-07.
  First-pass socket: InvocationObservationLite and submit_result evidence_summary leave room for verifier status.

RSV-08 Persistent AuthorityDecisionRecord store
  Reserved by: FP-01 through FP-08.
  First-pass socket: canonicalization_report, ToolDispatcher execution_history, tool_call_summaries, and proof slice preserve replay facts.

RSV-09 PromptCaptureRecord full retention policy
  Reserved by: FP-02, FP-03, and FP-04.
  First-pass socket: prompt-visible material remains bounded to task JSON, execution grounding, discovery cards, and tool observations.

RSV-10 Cross-domain DomainInstantiationPack validation
  Reserved by: FP-03 and FP-04.
  First-pass socket: RequestFrameSeed and LegacyCapabilityUniverse use domain-neutral terms even while FamilyOS is the proof domain.
```

Build discipline:

```text
Foundation pass:
  Prove the current path and reserve the future seams.

Interior systems pass:
  Promote reserved sockets into dedicated services when the seam has POC proof.

Finishing pass:
  Add stronger replay, verification, cross-domain validation, richer policy, and connector depth.

No pass may remove a previously planned component without an explicit architectural deletion record.
```

### V0 Scope Guard

```text
V0 may support a narrow FamilyOS proof path, but it must be production-shaped.
V0 may not leave ownership, authority, freshness, tier routing, connector constitution, prompt injection, safety mapping, or verification semantics vague.
Reserved blueprint components remain in the architecture even when their first implementation socket is a deferred production-shaped proof socket.
```

Production proof note: end-to-end LLM-facing proof must use the production provider/model path and production validation prompts. Mocked LLM responses, canned model outputs, and transcript replay can support debugging, but they cannot promote an execution-authority seam.

### Batch 01 Component Designs - Current-Code Minimum

**Section mode:** first-pass implementation plan.

#### FP-01 - FSM Canonical Dispatch Boundary

Design status: draft_contract.

Component atom coverage:

```text
SCA-022 TaskDispatchCanonicalizer
SCA-023 CanonicalizationReportWriter
```

Current code anchor:

```text
k1/concierge/fsm/controller.py
  _on_task_dispatch parses Front envelope into TaskDispatch.
  _route_via_orchestrator rebuilds canonical_payload from dispatch.to_dict().
  FSM then injects trace_id, session_id, overlay, scoreboard fallback, and narrative_thread.
```

Why it exists:

```text
The live path already canonicalizes by constructing TaskDispatch and serializing it back
through to_dict(). That is good. The weak point is silent field loss: fields outside
TaskDispatch, such as top-level plan or ad-hoc dispatch metadata, can disappear unless
they are explicitly reattached.
```

First-pass contract:

```text
Input:
  raw_front_dispatch_payload
  parsed_task_dispatch
  incoming_envelope_headers
  optional_overlay
  optional_scoreboard_referents
  optional_narrative_thread

Output:
  canonical_back_dispatch_payload
  canonicalization_report
```

Canonical payload minimum fields:

```text
task_id
intents
tier
budget_hint
safety_band (legacy scalar)
trace_id when available
session_id when available
reference_context when available or fallback-injected
depends_on when present
execution_profiles when present
grounding_envelope_id when present
temporal_anchor_id when present
spatial_context_id when present
resolved_temporal_refs when present
resolved_spatial_refs when present
grounding when present
turn_state_overlay when present
narrative_thread when present
```

Canonicalization report minimum fields:

```text
task_id
trace_id
preserved_fields[]
injected_fields[]
discarded_fields[]
defaulted_fields[]
fallback_fields[]
notes[]
```

First-pass invariants:

```text
TaskDispatch remains the canonical bus payload object.
Unknown fields are not rejected in first pass.
Unknown fields that disappear are reported, not silently treated as impossible.
FSM remains the state/routing authority.
The report is evidence only; it does not change routing.
```

What not to add first pass:

```text
No new schema enforcement service.
No rejection of unknown Front fields.
No validation of intents[].params against capability schemas.
No second grounding normalizer after TaskDispatch._mirror_grounding_into_reference_context.
```

Failure semantics:

```text
TaskDispatch.from_dict failure -> existing task dispatch invalid path.
Missing task_id/intents/tier -> existing parse/dispatch failure behavior.
Field discarded -> report note, not runtime failure.
Missing trace_id/session_id -> use existing envelope fallback behavior and report default/fallback.
```

POC proof target:

```text
Given a Front dispatch payload with task_id, plan, urgency, reference_context,
grounding fields, trace_id, and an overlay, the canonical payload delivered to Back
preserves TaskDispatch-owned fields, reattaches overlay, injects trace/session, and
reports plan/urgency as discarded or indirect.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/concierge/fsm/test_task_dispatch_payload.py tests/k1/concierge/task/test_dispatch_grounding_fields.py tests/k1/concierge/test_grounding_dispatch_contract.py -v
```

#### FP-02 - Back Execution Envelope Seed

Design status: draft_contract.

Component atom coverage:

```text
SCA-035 BackTaskEnvelopeBuilder
```

Current code anchor:

```text
k1/concierge/actors/back.py
  back_handler reads task = _parse_payload(envelope).
  trace_id falls back through envelope, task, ToolContext, generated back id.
  _bind_tool_context binds trace_id, session_id, active_task_id, legacy scalar safety_band, execution_profiles.
  _read_ss_snapshot reads SessionState once at task start.
```

Why it exists:

```text
Back currently receives a task dict plus envelope headers plus a ToolContext binding.
That is already the practical BackTaskEnvelope. The first design pass should name this
bundle and make its required fields explicit without introducing a new bus envelope type.
```

First-pass contract:

```text
BackExecutionEnvelopeSeed
  task_payload
  envelope_trace_id
  envelope_session_id
  envelope_request_id
  active_task_id
  effective_safety_band (legacy scalar)
  execution_profiles
  ss_snapshot_ref: in-memory snapshot for this handler invocation
  execution_grounding_block
```

Minimum behavior:

```text
Parse task payload once.
Bind ToolContext before ReAct.
Read SessionState once at task start.
Compute effective safety band once as a legacy scalar compatibility value.
Render execution grounding block from task grounding or live grounding fallback.
Pass task JSON as the Back user message.
```

First-pass invariants:

```text
No mid-loop SessionState reread.
ToolContext.cognitive_trace_id/session_id/active_task_id must be bound before tools run.
ToolContext.safety_band must be bound as a legacy scalar before invoke_capability can create CapabilityRequest.
Back still returns outcomes; it does not write SessionState directly.
```

What not to add first pass:

```text
No new BackTaskEnvelope bus topic.
No new durable envelope store.
No second SS read in RequestFrameBuilder.
No duplicate safety-band computation inside invoke builders.
```

Failure semantics:

```text
Missing trace_id -> existing fallback creates back-<uuid> trace and report should mark fallback.
Missing session_id -> ToolContext binds empty session today; first pass records degraded context, not failure.
Missing task_id -> Back can still log/emit failure through existing path, but proof should make this visible.
Invalid safety_band legacy scalar -> normalized to configured default through existing helper.
```

POC proof target:

```text
Given a canonical Back dispatch envelope, ToolContext has trace_id, session_id,
active_task_id, legacy scalar safety_band, and execution_profiles before react_loop starts.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/concierge/tools/test_task_dispatch_execution_profiles.py tests/k1/concierge/test_tool_fabric_port_wiring.py -v
```

#### FP-03 - RequestFrame Seed

Design status: draft_contract.

Component atom coverage:

```text
SCA-039 RequestFrameBuilder
SCA-043 ResolveSituationRequestBuilder
```

Current code anchor:

```text
k1/concierge/actors/back.py
  Back prompt receives task JSON plus execution grounding block.

k1/concierge/tools/implementations.py
  execute_discover_capabilities consumes intent/domain.
  execute_invoke_capability consumes capability_name/params/domain/action/intent.
```

Why it exists:

```text
The future RequestFrame is useful, but current Back does not have resolve_situation.
First pass should define a RequestFrameSeed that can be derived from the existing task
payload and used to produce legacy discover_capabilities inputs.
```

First-pass contract:

```text
RequestFrameSeed
  task_id
  trace_id
  session_id
  user_goal
  operation_hints[]
  domain_hints[]
  params_by_intent[]
  reference_context
  temporal_grounding_refs
  spatial_grounding_refs
  actor_scope_hint optional
  safety_band (legacy scalar)
  missing_fields[]
```

Legacy resolve request compatibility:

```text
LegacyResolveCompatibilityRequest
  intent: compact string from user_goal + operation_hints + relevant params
  domain: primary domain hint when present
  safety_band: ToolContext.safety_band (legacy scalar)
  trace_id
  task_id
```

First-pass invariants:

```text
RequestFrameSeed is a derived artifact, not a new source of truth.
It must not invent resource ids, binding ids, policy verdicts, or connector scope.
It can feed discover_capabilities, bind_capability, and prompt/debug evidence.
```

What not to add first pass:

```text
Do not install the model-visible resolve_situation tool yet; reserve its input shape through RequestFrameSeed.
Do not install a new Fabric resolver service yet; reserve the resolver doorway.
Do not claim CandidateUniverse completeness beyond legacy capability evidence.
Do not run resource projection query fanout yet; reserve the projection socket.
```

Failure semantics:

```text
No intents -> cannot build user_goal and should use existing task dispatch invalid path.
Missing domain -> allowed; discover_capabilities already performs unfiltered search.
Missing params -> allowed; contract preflight will return capability_params_incomplete.
Ambiguous user_goal -> preserve uncertainty in missing_fields or notes; do not guess.
```

POC proof target:

```text
Given a current TaskDispatch for a calendar event, derive a RequestFrameSeed whose
legacy intent/domain inputs reproduce the current discover_capabilities behavior.
```

Targeted proof command candidate:

```powershell
python scripts/probe_back_prompt_surface.py --json --log-level CRITICAL --prompt-preview-chars 500
```

#### FP-04 - Legacy Capability Universe And Prompt Cards

Design status: draft_contract.

Component atom coverage:

```text
SCA-055 ResourceProjectionQueryBuilder, compatibility only
SCA-065 ScopeProofBuilder, compatibility only
SCA-080 CandidateUniverseBuilder, capability-universe only
SCA-084 PromptPackBuilder, prompt-card only
```

Current code anchor:

```text
k1/concierge/tools/implementations.py
  execute_discover_capabilities performs domain-filtered then unfiltered search, dedupes by name,
  caches CapabilityContract objects, and returns LLM-facing records.

k1/concierge/react/capability_routing.py
  bind_capability verifies exact capability names or returns ambiguity/invalid-candidate recovery.

k1/concierge/tools/implementations.py
  _request_prompt_metadata derives prompt_template, activity_profile, context_override,
  execution_profiles, and prompt_variables.
```

Why it exists:

```text
The future CandidateUniverse is resource-first. Current code is capability-first.
The first pass should not fake a resource universe that does not exist. It should build
a LegacyCapabilityUniverse from current discovery/binding evidence and clearly label it
as capability evidence, not resource completeness.
```

First-pass contract:

```text
LegacyCapabilityUniverse
  task_id
  trace_id
  request_frame_seed_ref optional
  intent
  domain
  capabilities[]
    name
    record_type: executable_capability | guidance_profile | workflow_or_agent | unknown
    domains[]
    score
    schema optional
    prompt_template optional
    activity_profile optional
    tool_instructions optional
    limitations[]
  exact_contract_cache_refs[]
  omissions[]
  diagnostics[]
```

Prompt cards minimum:

```text
LegacyPromptCards
  primary_executable_candidates[]
  guidance_cards[]
  required_inputs_by_candidate
  limitations_by_candidate
  execution_profile_cards[]
  forbidden_notes[]
```

First-pass invariants:

```text
The universe may classify capability records.
It must not claim resource completeness.
It must not hide guidance/profile records as executable actions.
It must preserve exact capability names for current invoke_capability.
It must reuse ctx.capability_cache rather than adding a new store.
```

What not to add first pass:

```text
Do not install the full ResourceUniverse implementation yet; reserve where it attaches.
Do not claim full ScopeProof completeness yet; reserve trace/scope/omission fields.
Do not require Bridge/IFL projection yet; reserve connector projection as a later source.
Do not install the PolicyBundle service yet; reserve policy/protected-read/limitation fields.
Do not add a new ranking algorithm beyond deterministic classification/executable-first display.
```

Failure semantics:

```text
No capabilities -> missing_capability compatibility diagnostic.
Only guidance/profile records -> no executable capability diagnostic.
Multiple executable candidates -> preserve ambiguity for bind_capability/HIL path.
Exact requested capability not found -> existing capability_binding_invalid_candidate or needs_discovery.
```

POC proof target:

```text
Given current calendar discovery output where `calendar_activity_v1` can rank above
`tool.execute.calendar.create_event`, classify the former as guidance_profile and the
latter as executable_capability without changing Fabric retrieval internals.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/concierge/react/test_capability_binder.py tests/k1/concierge/prompt/test_back_prompt_capability_names.py -v
```

#### FP-05 - Invocation Request And Preflight

Design status: draft_contract.

Component atom coverage:

```text
SCA-090 InvocationRequestBuilder
SCA-092 InvocationPreflightValidator
```

Current code anchor:

```text
k1/concierge/tools/implementations.py
  execute_invoke_capability normalizes params, binds capability for Back,
  looks up exact contract, runs recovery_for_unsatisfied_contract, builds CapabilityRequest,
  and calls ctx.dispatch.dispatch_direct.
```

Why it exists:

```text
The first real execution boundary is already inside execute_invoke_capability.
The design should extract that boundary conceptually, not add a second invocation service.
```

First-pass contract:

```text
InvocationRequestSeed
  capability_name
  params
  session_id
  trace_id
  caller: concierge
  caller_id: concierge.back
  safety_band (legacy scalar)
  prompt_template optional
  context_override optional
  binding_result optional
  contract_ref optional
```

Preflight minimum:

```text
capability_name present
Back binding status is bound when binding is available
exact contract lookup attempted
required inputs satisfied through recovery_for_unsatisfied_contract
ToolContext.dispatch is wired unless allow_dispatch_passthrough is explicitly true
safety_band legacy scalar is taken from ToolContext, not defaulted silently in the builder
```

First-pass invariants:

```text
No side effect after capability_params_incomplete.
No side effect after capability_binding_* failure.
No side effect when dispatch_not_wired and passthrough disabled.
CapabilityRequest construction remains the bridge to current Fabric.
```

What not to add first pass:

```text
No binding_id requirement yet.
No idempotency store yet.
No dependent batch validator yet beyond documentation.
No provider-specific safety mapper here; record the need and keep current legacy safety_band threading.
```

Failure semantics:

```text
Missing capability_name -> existing error.
Binding invalid/ambiguous/not_found -> capability_binding_<status> ToolResult.
Missing required inputs -> capability_params_incomplete with recovery schema.
Fabric dispatch exception -> ToolResult status error with duration_ms.
Dispatch not wired -> dispatch_not_wired error unless explicit passthrough.
```

POC proof target:

```text
Given `duration_minutes` without `end`, preflight returns capability_params_incomplete
and does not call Fabric. Given schema-valid calendar params and dispatch wired, it builds
CapabilityRequest with trace/session/safety and dispatches once.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/concierge/test_tool_fabric_port_wiring.py tests/unit/concierge/tools/test_dispatch_passthrough_gate.py -v
```

#### FP-06 - Invocation Observation Normalizer

Design status: draft_contract.

Component atom coverage:

```text
SCA-127 InvocationObservationBuilder
```

Current code anchor:

```text
k1/concierge/tools/implementations.py
  execute_invoke_capability wraps CapabilityResult into ToolResult:
    data.result
    data.duration_ms
    data.status
    error
```

Why it exists:

```text
Back already sees ToolResult. First pass should normalize the shape inside that existing
observation rather than introducing VerificationObservation or a new observation bus.
```

First-pass contract:

```text
InvocationObservationLite
  capability_name
  status: success | error | needs_human
  result
  error optional
  duration_ms
  binding optional
  recovery optional
  retryable optional
```

First-pass invariants:

```text
Observation is model-visible through tool result.
Raw provider exceptions remain compact error summaries.
Binding failures and param failures use the same observation family as dispatch failures.
```

What not to add first pass:

```text
Do not install separate VerificationObservation yet; reserve the verifier doorway in InvocationObservationLite.
Do not add raw provider payload refs unless current Fabric already supplies them.
Do not install the Bridge connector observation shape yet; reserve the connector observation socket.
Do not install audit ledger persistence yet; preserve replay facts through current summaries.
```

Failure semantics:

```text
CapabilityResult.success true -> ToolResult status ok and data.status success.
CapabilityResult.success false -> ToolResult status error and compact error.
Preflight failures -> ToolResult error before dispatch.
```

POC proof target:

```text
All invoke_capability outcomes that Back sees have duration_ms, status, error/result,
and recovery/binding when relevant, with no side-effect dispatch on preflight failures.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/concierge/react/test_back_capability_execution_kernel.py tests/k1/concierge/react/test_back_clarification_capture.py -v
```

#### FP-07 - Submit Result Authority Boundary

Design status: draft_contract.

Component atom coverage:

```text
SCA-133 SubmitResultIntentBuilder
SCA-135 CompletionAuthorityGate
```

Current code anchor:

```text
k1/concierge/tools/implementations.py
  execute_submit_result validates result_type and returns _submission.

k1/concierge/tools/dispatcher.py
  ToolDispatcher.dispatch has the Back no-work guard for submit_result(complete).

k1/concierge/react/loop.py
  submit_result is terminal; if mixed with other tool calls, submit_result is processed first.

k1/concierge/actors/back.py
  _emit_back_result converts ReactResult into task.complete/task.suspended/task.failed.
```

Why it exists:

```text
Completion is already split correctly: submit_result validates terminal intent, while
Back actor emits bus events after the ReAct loop returns. The design should strengthen
that boundary without adding another submit event path.
```

First-pass contract:

```text
SubmitResultSeed
  result_type: complete | needs_human
  final_answer optional
  results[] optional
  artifacts_created[] optional
  hil_type optional
  question optional
  options[] optional
  side_effects optional
  confidence optional
  blockers optional
  suggested_next_action optional
  semantic_context optional
  presentation_guidance optional
```

Completion authority minimum:

```text
submit_result schema valid
Back no-work guard preserved
tool_call_summaries emitted with completion frame
task.complete emitted only by _emit_back_result after ReactResult complete
task.suspended emitted only for needs_human/legacy suspension path
task.failed emitted for cancelled, budget_exhausted, missing_submit_result, loop_degenerate
```

First-pass invariants:

```text
submit_result tool does not publish bus events.
Back actor remains the bus emission owner.
Front/user-facing text is not emitted by Back directly.
For current system-of-record work, complete should follow authority attempt evidence from tool_call_summaries.
```

What not to add first pass:

```text
No new SubmitResult schema replacing current result_type.
No new status enum beyond complete/needs_human inside the tool.
No verification-required completion gate until VerificationPlan exists.
No second mixed-submit scheduler; keep current warning and terminal processing.
```

Failure semantics:

```text
Invalid result_type -> submit_result ToolResult error and ReAct retry.
submit_result complete before authority/context work -> existing no-work guard error.
Missing submit_result by loop end -> existing missing_submit_result failure path.
Budget exhausted -> existing task.failed path.
```

POC proof target:

```text
Back complete produces one task.complete event through _emit_back_result with frame and
tool_call_summaries. Invalid submit_result args are fed back to the LLM for retry.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/concierge/react/test_back_capability_execution_kernel.py tests/k1/concierge/react/test_front_dispatch_terminates.py -v
```

#### FP-08 - End-To-End Proof Slice

Design status: sketch.

Component atom coverage:

```text
SCA-145 EndToEndProofBundleFinalizer
```

Current code anchor:

```text
Existing proof sources:
  bus envelope correlation headers
  canonical task payload
  ToolDispatcher call history and execution_history
  Back tool_call_summaries
  ReactResult status/data
  task.complete/task.suspended/task.failed payloads
```

Why it exists:

```text
The first batch needs evidence that the current path is contract-clean before adding
more kernel layers. A lightweight proof slice can be assembled from existing runtime
artifacts and targeted tests/probes.
```

First-pass contract:

```text
EndToEndProofSlice
  trace_id
  task_id
  front_dispatch_payload_ref or safe summary
  canonical_payload_summary
  back_context_summary
  discovery_summary optional
  binding_summary optional
  invocation_summary optional
  submit_summary
  emitted_topic
  failures[]
  negative_proofs[]
```

First-pass invariants:

```text
Proof slice may be test/probe output first.
No new durable proof database is required.
Each proof must include at least one negative path relevant to the component.
```

What not to add first pass:

```text
Do not install the AuthorityDecisionRecord storage service yet; reserve replay facts in the proof slice.
Do not install PromptCaptureRecord retention policy yet; reserve prompt-visible summaries and refs.
Do not install the full replay engine yet; keep proof data reconstructable enough for targeted probes.
Do not install the cross-domain gate runner yet; preserve domain-neutral fields for later validation.
```

POC proof target:

```text
One targeted test/probe proves: Front dispatch payload -> FSM canonical payload ->
Back context binding -> discover/bind/invoke preflight or dispatch -> submit_result ->
emitted task topic, with trace_id/task_id preserved.
```

Targeted proof command candidate:

```powershell
pytest tests/k1/integration/test_dispatch_task_bus_hop.py tests/k1/concierge/test_tool_fabric_port_wiring.py tests/k1/concierge/react/test_capability_binder.py -v
```

### Inventory Acceptance Gate

This inventory is ready for the next design pass only when every atom has one of these
outcomes:

```text
keep
  Atom is truly one seam or one authority decision.

merge
  Atom has no independent caller/callee, authority question, prompt effect, evidence output, or failure family.

split
  Atom contains more than one authority question or more than one independent failure family.

defer
  Atom is required eventually but not required for the first FamilyOS proof path.
```

No atom should be promoted from this inventory directly into implementation. Promotion path:

```text
inventory atom
  -> natural-language design packet
  -> draft request/response/failure/proof shape
  -> POC probe
  -> failure entry
  -> corrected contract
  -> promoted component design
```

---

## Appendix A - Design Committee Deliberation Log

**Section mode:** historical rationale.

Status note:
  Some open questions in this log are later resolved by the normative sections.
  The normative sections override the historical pass status.

### Pass 1 - Generic Kernel Orientation

Committee lenses applied in this pass:

```text
LLM research lens:
  Reduce choices exposed to the model. The model should deliberate over allowed next actions,
  not over raw catalogs, connector secrets, or unbounded provider payloads.

Cognitive architecture lens:
  Separate memory, belief, referent salience, and execution authority. Remembering a thing
  is not authority to mutate it. HIL can resolve visible uncertainty, but cannot repair a
  hidden or incomplete candidate universe.

AI systems architecture lens:
  Make each authority boundary explicit and replayable. The resolver owns situation truth,
  policy owns gates, registry owns contracts, gateway owns connector security, adapters own
  provider protocol, and proof owns promotion evidence.

Developer/runtime lens:
  Keep the migration additive. Current FamilyOS names and native tools remain valid as the
  first implementation, but every new field should either be domain-neutral or clearly
  namespaced as an implementation extension.
```

Committee decisions for this pass:

```text
CD-001
  Treat FamilyOS as proof domain, not as the contract boundary.

CD-002
  Preserve current component names in examples because they anchor real code paths,
  but define their kernel-role equivalents before adding new contracts.

CD-003
  Do not let domain packs add execution shortcuts. Domain packs may add ontology,
  policies, guides, manifests, adapters, and verifiers, but side effects still pass
  through request frame -> resolution -> policy -> binding -> invocation -> observation.

CD-004
  Use generic names in core envelopes and place domain-specific fields in namespaced
  extensions. A future medical, legal, enterprise, robotics, finance, education, or
  home domain should not require rewriting the core contract model.
```

Open questions raised by the committee:

```text
OQ-001: What is the minimal DomainInstantiationPack?
  Working solution:
    ontology, resource kinds, operation taxonomy, policy cards, guide cards,
    connector manifests, verifier catalog, HIL language templates, scenario gates.

OQ-002: Where does planning live in a generic kernel?
  Working solution:
    planners may produce task graphs and dependency hints, but they cannot grant execution
    authority. Every executable step still resolves through the situated kernel.

OQ-003: How do we prevent FamilyOS examples from hardening into generic assumptions?
  Working solution:
    every promoted contract must distinguish core fields from domain extensions, and each
    scenario gate should eventually have at least one non-household analogue.

OQ-004: What is the boundary between memory and authority?
  Working solution:
    memory can propose referents and priors; the resolver must still prove resource scope,
    freshness, actor authority, and policy eligibility before side effects.

OQ-005: How do domains with no physical resources fit?
  Working solution:
    treat documents, records, cases, tickets, datasets, accounts, models, policies, and
    workflows as resources. The kernel does not require devices; it requires concrete
    acted-on objects with authority and verification semantics.
```

Status after Pass 1:

```text
Done:
  Add a DomainInstantiationPack contract near the Standard Vocabulary section.
  Add a kernel-role map to the component contract layer so CC-0 through CC-10 are not FamilyOS-only.

Resolved later in this document:
  Non-household scenario analogues are added under Cross-Domain Scenario Analogues.
  Kernel/implementation separation is added under Kernel / Implementation Open Decision Register.
```

### Pass 2 - Model Context, Cognitive Authority, And Replayability

Hats worn in this pass:

```text
LLM researcher:
  The model should receive a decision surface, not a database dump. PromptPack must
  explicitly enumerate allowed actions, forbidden actions, uncertainty, omitted context,
  stale cards, and source refs so the model cannot accidentally convert salience into
  authority.

Cognitive architect:
  The kernel needs a hard separation between memory, belief, referent salience, planning,
  and execution authority. A remembered referent can seed resolution, but only resolver
  proof can authorize action over the concrete resource.

AI systems architect:
  Every authority seam must be replayable. Later review should reconstruct what the model
  saw, what it was not allowed to do, what the resolver omitted, which policy made the
  gate decision, and which binding made the invocation legal.
```

Committee decisions for this pass:

```text
CD-005
  PromptPack is a Model Context Contract. It is not just text injected into the prompt;
  it is the bounded decision surface for one ReAct phase.

CD-006
  Salience, ranking, and memory confidence cannot authorize execution. They may influence
  presentation order only after CandidateUniverse completeness and policy eligibility are
  established.

CD-007
  Every model-visible action must be backed by a source ref, binding ref, policy ref,
  or recovery directive. If an action cannot be explained by those refs, it is not legal.

CD-008
  Replayability is a kernel requirement, not an observability nice-to-have. The proof
  harness must be able to replay the decision surface without recovering raw secrets,
  full manifests, or provider payloads.
```

Open questions raised by this pass:

```text
OQ-006: How many options should the model see at once?
  Working solution:
    PromptPack owns an option budget. It may elide low-salience candidates only after
    recording counts, omission reasons, and refs that allow inspection or refresh.

OQ-007: Where does model uncertainty live?
  Working solution:
    Uncertainty belongs in typed fields: completeness, freshness, ambiguity, missing
    params, policy uncertainty, verifier uncertainty, and recovery directives. It should
    not live only in prose.

OQ-008: How do we replay a prompt safely?
  Working solution:
    Store PromptPack ids, card ids, source refs, redaction counts, and safe summaries.
    Raw provider payloads, credentials, secrets, and full manifests stay behind refs.
```

### Pass 3 - Protected Reads, Redaction Gates, And Negative Proof

Hats worn in this pass:

```text
Security/privacy/policy architect:
  Treat protected reads as seriously as writes. A disclosure can be a side effect even
  when no external provider state changes. Privacy, consent, role, retention, and audit
  requirements must be machine-readable before the model sees sensitive summaries.

Evaluation/proof engineer:
  Passing happy-path probes are not enough. Every milestone needs at least one forced
  negative proof showing that forbidden data, forbidden actions, stale cards, missing
  bindings, or incomplete candidate universes are rejected in the expected way.
```

Committee decisions for this pass:

```text
CD-009
  Protected reads are governed actions. Health, finance, legal, education, child data,
  location, identity, and enterprise secrets may require policy gates before disclosure
  even when the underlying capability is read-only.

CD-010
  Redaction is not a best-effort prompt-cleaning step. Redaction requirements belong in
  PolicyBundle and PromptPack evidence, and failures are promotion blockers.

CD-011
  Every milestone promotion requires negative evidence. A proof run that only shows the
  intended path works is insufficient for a generic kernel.

CD-012
  Auditability includes non-actions. The proof system must record why the kernel refused,
  blocked, asked HIL, refreshed projection, or submitted cannot_execute.
```

Open questions raised by this pass:

```text
OQ-009: Which reads are protected by default in a new domain?
  Working solution:
    DomainInstantiationPack must declare data classification rules. Until those rules
    exist, protected-read policy defaults to conservative for personal, financial,
    health, legal, identity, location, credential, child, and enterprise-secret data.

OQ-010: Is redaction owned by policy, prompt assembly, gateway, or proof?
  Working solution:
    Policy declares requirements, gateway/adapter classify raw material, prompt assembly
    performs model-context redaction, and proof verifies the captured prompt and stored
    refs. No single layer is trusted alone.

OQ-011: What counts as a negative proof?
  Working solution:
    At minimum: one forbidden prompt material test, one forbidden action test, one stale
    or incomplete projection test, and one missing authority/binding test for each
    milestone where those risks are relevant.
```

### Pass 4 - Kernel Decisions Versus Proof-Domain Decisions

Hat worn in this pass:

```text
Domain-kernel architect:
  Keep the reusable kernel small and strict. Let domains add ontology, resources,
  policies, guides, manifests, verifiers, and scenario gates, but do not let a proof
  domain hard-code shortcuts into core envelopes.
```

Committee decision for this pass:

```text
CD-013
  Open decisions must be labeled as kernel, implementation, or cross-domain. A question
  about FamilyOS naming, K1 stores, or native family tools should not silently become a
  generic kernel rule. A question about authority, prompt boundary, protected reads, or
  side-effect invocation should not be downgraded to FamilyOS-only.
```

Open question raised by this pass:

```text
OQ-012: When does a proof-domain solution become a kernel rule?
  Working solution:
    Promote it only when it is required by at least two materially different domains or
    by a non-negotiable authority boundary. Otherwise keep it as a domain extension or
    implementation adapter detail.
```

### Pass 5 - Scenario Gates As Kernel Proof, Not Demo Stories

Hats worn in this pass:

```text
Scenario/evaluation architect:
  Scenario gates are not examples for a slide. They are adversarial proof fixtures. Each
  gate should force one kernel invariant: completeness, protected read, missing capability,
  policy confirmation, disambiguation, stale projection, recovery, or prompt boundary.

Domain-kernel architect:
  A FamilyOS scenario becomes a kernel scenario only when its structure survives translation
  into a materially different domain. The words change; the authority shape should not.
```

Committee decisions for this pass:

```text
CD-014
  Every M12 scenario gate must name its kernel proof class. Example: scheduling hidden
  conflicts is not about calendars; it is a time-bound system-of-record mutation with
  prerequisite reads and conflict policy.

CD-015
  At least two non-household analogues must exist before the whiteboard claims the kernel
  is generic. The analogues do not need implementation in the first FamilyOS POC, but they
  must be specific enough to pressure the contracts.

CD-016
  A scenario gate passes only if it records the expected non-action path too. Missing
  capability, policy block, protected read denial, stale projection refresh, and HIL are
  first-class outcomes, not failures of the scenario design.
```

Open questions raised by this pass:

```text
OQ-013: Should every domain pack define its own M12 gate set?
  Working solution:
    Yes. The kernel defines gate classes; each DomainInstantiationPack contributes concrete
    gate fixtures. FamilyOS is the first fixture pack, not the universal scenario set.

OQ-014: What is the minimum cross-domain proof for generic-kernel status?
  Working solution:
    One side-effect mutation analogue, one protected-read analogue, one missing-capability
    analogue, and one partial-projection/disambiguation analogue across at least two
    non-household domains.
```

### Pass 6 - Runtime Migration, Flags, And Rollback Discipline

Hats worn in this pass:

```text
Runtime/developer architect:
  A correct contract still fails production if it cannot be shipped in slices. Every seam
  needs a feature flag, shadow mode, targeted proof command, rollback behavior, and a way
  to compare legacy discover/invoke behavior against resolver/binding behavior.

Developer experience lens:
  Engineers need to know which file or seam they are proving, which command proves it,
  which logs matter, and how to turn the new path off without deleting evidence.
```

Committee decisions for this pass:

```text
CD-017
  Every CC milestone must declare feature flag, shadow mode, rollback behavior, and
  targeted proof command before implementation begins.

CD-018
  Shadow mode is mandatory before authority cutover. The resolver may observe and compare
  while legacy discover/invoke remains authority, but it must not silently change outcomes.

CD-019
  Rollback must return to the last proven parent contract. Rollback may disable authority
  for a new seam, but it must preserve proof records and failure logs.

CD-020
  Compatibility adapters are allowed only when they emit deprecation/proof evidence. A
  compatibility shim that hides missing binding_id, missing policy, or missing projection
  evidence is a contract violation.
```

Open questions raised by this pass:

```text
OQ-015: Where should feature flags live?
  Working solution:
    Feature flags are implementation-specific, but each CC contract must name the flag and
    fallback path in its promotion notes.

OQ-016: What does shadow comparison measure?
  Working solution:
    Compare verdict, candidate universe, allowed actions, chosen binding, protected-read
    gate, prompt redaction, invocation params, submit status, and user-visible summary.
```

### Pass 7 - Ontology, Resource Identity, And Operation Taxonomy

Hats worn in this pass:

```text
Ontology/data architect:
  A generic kernel cannot run on free-text resource names. Each domain needs typed resource
  kinds, stable identity fields, alias rules, operation definitions, effect classes, and
  data classification rules before execution authority is enabled.

Resolver architect:
  CandidateUniverse should expose concrete ResourceCandidate records, not just strings or
  display labels. The model may see compact labels, but the resolver must carry identity,
  provenance, freshness, authority, and affordance evidence.
```

Committee decisions for this pass:

```text
CD-021
  Resource identity is a kernel concern. Domain packs may define resource kinds, but every
  ResourceCandidate must distinguish resource_id, connector/provider identity, owner or
  scope, aliases, freshness, data class, and available operations.

CD-022
  Operation taxonomy must separate user verbs from executable effects. "Pay", "send",
  "file", "restart", and "schedule" are user-world language; kernel operations must name
  effect class, resource kind, verifier expectations, and policy hooks.

CD-023
  Display labels are never identity. The model may reason over labels, but invocation and
  proof must use stable ids and versioned refs.
```

Open questions raised by this pass:

```text
OQ-017: How strict must resource_kind_defs be in early V0?
  Working solution:
    V0 may start with narrow typed definitions for proven resources only. Unknown resource
    kinds return missing_capability or cannot_execute rather than falling back to text-only
    execution authority.

OQ-018: Can operation_hints be LLM-proposed?
  Working solution:
    Yes, as hints with provenance and confidence. Resolver maps hints to domain operation
    definitions before policy, binding, or side effects.
```

### Pass 8 - Planning Without Authority Leakage

Hats worn in this pass:

```text
Planner/workflow architect:
  Planning is useful for decomposition, dependencies, and sequencing, but it must not grant
  execution authority. A plan step that mutates state is still just a proposed step until
  that step resolves resources, policy, bindings, and verification obligations.

Distributed systems architect:
  Dependent side effects must be represented as data dependencies, not optimistic batches.
  A later step may depend on artifact ids, verifier output, HIL responses, or projection
  deltas from earlier steps.
```

Committee decisions for this pass:

```text
CD-024
  PlanGraph is advisory until each executable step passes situated resolution. A planner
  can propose StepFrames; it cannot create bindings, skip policy, or batch dependent writes.

CD-025
  Batch invocation is legal only for independent bindings whose params do not depend on
  prior side-effect artifacts and whose policy allows parallel execution.

CD-026
  The kernel must represent step dependencies explicitly: artifact dependency, HIL
  dependency, verifier dependency, projection refresh dependency, and policy approval
  dependency.
```

Open questions raised by this pass:

```text
OQ-019: Is PlanGraph part of Plane 1 or a separate planner plane?
  Working solution:
    Treat PlanGraph as an optional input artifact consumed by the execution actor. It may
    be produced by Front, PlannerActor, Back pre-loop, or deterministic planner code, but
    each executable step still resolves through Plane 4.

OQ-020: Can a workflow template pre-bind capabilities?
  Working solution:
    No for execution authority. A template may reference roles and operation defs, but
    bindings are minted by the resolver against current resources, policy, and freshness.
```

### Pass 9 - Verification As First-Class Evidence

Hats worn in this pass:

```text
Verifier/assurance architect:
  Provider success is not the same as verified system-of-record state. The kernel needs a
  formal verification plan and observation so completed submit can cite evidence instead
  of trusting provider prose or model interpretation.

Reliability engineer:
  Verification must support degraded outcomes. Some providers cannot read back, some reads
  are stale, some verifiers fail independently, and some policies may allow partial or
  degraded completion only when the limitation is explicit.
```

Committee decisions for this pass:

```text
CD-027
  VerificationPlan is created before side-effect invocation when the contract or policy
  requires verification. It names the verifier, method, expected state, and degraded policy.

CD-028
  VerificationObservation is separate from InvocationObservation. Invocation says what the
  provider reported; verification says what the kernel proved after the provider report.

CD-029
  submit_result(completed) for system-of-record mutation must cite successful verification
  or a policy-approved degraded-completion reason.
```

Open questions raised by this pass:

```text
OQ-021: Can the LLM decide whether verification is required?
  Working solution:
    No. ToolContract, PolicyBundle, and BindingBundle decide. The model may interpret an
    unusual verifier failure only after receiving VerificationObservation.

OQ-022: How should unavailable verification be represented?
  Working solution:
    As explicit degraded_verification with policy ref, risk summary, and submit limits;
    never as implicit success.
```

### Pass 10 - Traceability, Replay, And Authority Ledger

Hats worn in this pass:

```text
Observability architect:
  A generic execution kernel must reconstruct why an action was allowed, denied, retried,
  or submitted. Logs are not enough; each authority decision needs a typed record.

Audit/proof engineer:
  Replay must work from redacted evidence. The proof path should reconstruct the model's
  decision surface without recovering credentials, raw provider payloads, or full manifests.
```

Committee decisions for this pass:

```text
CD-030
  TraceContext travels through every boundary envelope. Component-local ids are allowed,
  but they must chain back to trace_id and request_id.

CD-031
  AuthorityDecisionRecord is emitted for allow, ask_hil, deny, block, refresh, invoke,
  verify, degraded completion, and cannot_execute decisions.

CD-032
  Prompt replay uses PromptCaptureRecord and RedactionEvidence. It should prove what the
  model saw and what was withheld without storing forbidden material inline.
```

Open questions raised by this pass:

```text
OQ-023: Is AuthorityDecisionRecord part of proof harness or runtime?
  Working solution:
    Runtime emits it at authority seams; proof harness stores and evaluates it.

OQ-024: How much prompt material should be retained?
  Working solution:
    Retain compact card ids, safe summaries, source refs, redaction counts, allowed and
    forbidden actions, and hashes. Store full prompt text only when redaction scan passes
    and retention policy allows it.
```

### Pass 11 - HIL As Governed Interaction, Not Escape Hatch

Hats worn in this pass:

```text
Human-factors architect:
  HIL questions must be honest, bounded, and answerable. They should not expose internal
  machinery, hide projection incompleteness, or ask the user to compensate for missing
  resolver proof.

Policy architect:
  HIL can grant clarification, confirmation, consent, or missing values only within policy.
  HIL does not override role, law, connector scope, or missing capability constraints.
```

Committee decisions for this pass:

```text
CD-033
  HILRequest choices for disambiguation must come from CandidateUniverse and carry stable
  candidate refs, not only display labels.

CD-034
  HILResponse must resume through previous_resolution_id or a still-valid ResolutionEnvelope.
  A user answer cannot be pasted straight into invocation params without rechecking policy,
  freshness, and bindings when those may have changed.

CD-035
  HIL wording must disclose incomplete projection and material risk. It must not make the
  system sound more certain than the resolver evidence allows.
```

Open questions raised by this pass:

```text
OQ-025: Can HIL override policy denial?
  Working solution:
    No. HIL can satisfy policy gates that explicitly allow user confirmation or consent;
    it cannot override hard deny, missing connector scope, or missing capability.

OQ-026: Should HIL questions expose technical ids?
  Working solution:
    No for normal user-facing text. The HILRequest carries candidate refs for runtime and
    proof, while the question uses domain language and safe labels.
```

### Pass 12 - Safety Semantics Deconfliction

Hats worn in this pass:

```text
Safety/policy architect:
  The kernel must not overload one band label to mean permission level, risk state,
  autonomy mode, and provider minimum all at once. Those are different axes and must be
  represented separately before policy or provider dispatch.

Runtime compatibility architect:
  FamilyOS has a verified AMBER/GREEN semantic conflict. The generic contract should make
  that class of bug structurally hard by requiring explicit mapping into provider-native
  safety fields.
```

Committee decisions for this pass:

```text
CD-036
  safety_context must separate actor_clearance, task_risk_state, autonomy_level,
  operation_risk_class, and runtime_block_state.

CD-037
  Provider-specific safety bands are adapter/runtime fields. Fabric policy may map into
  them, but Back and PromptPack should reason over kernel safety semantics.

CD-038
  If a provider or native adapter uses incompatible band semantics, the compatibility
  adapter must emit mapping evidence before dispatch. Silent pass-through is forbidden.
```

Open questions raised by this pass:

```text
OQ-027: Should current GREEN/AMBER/RED labels survive in the kernel?
  Working solution:
    They may survive as domain/runtime labels, but core contracts should name the axis:
    actor_clearance, task_risk_state, operation_risk_class, autonomy_level, or block_state.

OQ-028: Where does safety mapping occur?
  Working solution:
    PolicyBundle decides kernel gates; Fabric invocation maps kernel safety to provider
    runtime safety fields and records SafetyMappingEvidence before dispatch.
```

### Pass 13 - Connector Trust, Manifest Admission, And Marketplace Separation

Hats worn in this pass:

```text
Connector platform architect:
  A connector suggestion is not an executable connector. Marketplace search may discover
  adapters, but execution authority starts only after manifest admission, trust checks,
  permission scopes, resource discovery, and capability registration.

Supply-chain security architect:
  Signed manifests, adapter provenance, permission scope review, sandbox mode, and revocation
  behavior must be represented before a connector can contribute bindings.
```

Committee decisions for this pass:

```text
CD-039
  Manifest admission precedes Fabric capability registration for external connectors.
  CapabilityRegistrationBatch from an unadmitted manifest is catalog-only, not executable.

CD-040
  Missing capability may point to catalog or marketplace suggestions, but those suggestions
  must not appear as local executable bindings until connector admission and resource
  projection complete.

CD-041
  Connector revocation or credential loss must remove or stale relevant resource candidates
  and bindings before the next side-effect resolution.
```

Open questions raised by this pass:

```text
OQ-029: Does manifest admission belong to Bridge or Fabric?
  Working solution:
    Bridge owns connector trust, credentials, adapter runtime, and manifest admission;
    Fabric consumes only admitted capability/resource/event contracts for execution.

OQ-030: Can an untrusted connector be visible to Back?
  Working solution:
    Only as catalog suggestion or cannot_execute explanation. It cannot appear in
    allowed_next_actions or binding authority.
```

### Pass 14 - Scale, Latency, And Budget Discipline

Hats worn in this pass:

```text
Performance/scale architect:
  The kernel cannot rely on human patience or unlimited context. Resolver fanout, PromptPack
  size, LLM hops, connector calls, verifier calls, and HIL waits need explicit budgets.

LLM systems architect:
  Prompt budget is not only token count. It controls option count, card count, schema size,
  observation size, and whether the model sees enough to decide without seeing too much.
```

Committee decisions for this pass:

```text
CD-042
  ExecutionBudget is part of the request/resolution contract. Budget exhaustion must return
  a typed verdict such as partial_projection, needs_hil, cannot_execute, or retry_later.

CD-043
  PromptPack must shed context deterministically using priority and omission summaries.
  It may not silently drop candidate resources that affect authority.

CD-044
  Connector fanout and verifier fanout are policy-controlled. Reads may parallelize when
  policy allows and protected-read gating is satisfied. Writes and dependent side effects
  remain sequenced.
```

Open questions raised by this pass:

```text
OQ-031: What is the V0 latency target?
  Working solution:
    V0 should record latency budgets and actuals before enforcing hard SLOs. Promotion gates
    should fail on unbounded loops, unbounded prompt growth, or unbounded connector fanout.

OQ-032: Can budget exhaustion still produce useful output?
  Working solution:
    Yes, but only as partial, cannot_execute, needs_hil, or retry_later with explicit
    omissions. Budget exhaustion cannot produce silent completed authority.
```

---

## Appendix B - Current-State Probe Evidence

**Section mode:** current proof evidence.

Default Back prompt/tool surface probe:

```powershell
python scripts\probe_back_prompt_surface.py --json --log-level CRITICAL --prompt-preview-chars 500
```

Key live summary:

```text
metaTools=recall_memory,discover_capabilities,invoke_capability,batch_invoke_capabilities,submit_result
calendar discovery count=19
reminders discovery count=18
```

Direct invocation proof:

- Missing `end`: `capability_params_incomplete` with recovery asking for `end`.
- Schema-valid params + AMBER: `band_denied`.
- Schema-valid params + GREEN: `ok`, calendar event created.
